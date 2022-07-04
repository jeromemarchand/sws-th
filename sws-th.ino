/*
 * Read data from temperature sensor Sencor SWS TH2850-2999-3851-5150
 * with a RF433 module
 *
 */
#include <ArduinoBLE.h>
#include <limits.h>
//#include <stdlib.h>

#include "sws-th.h"

#undef DEBUG
#ifdef DEBUG

#define SCREEN_WIDTH 128
#define print(...)   Serial.print(__VA_ARGS__)
#define println(...) Serial.println(__VA_ARGS__)

unsigned long general_error = 0;
unsigned long dataframe1_error = 0;
unsigned long dataframe1_ok = 0;
unsigned long dataframe2_error = 0;
unsigned long dataframe2_ok = 0;
volatile bool buffer_full = false;

inline void inc_general_error() {
	general_error++;
}
inline void inc_dataframe1_error() {
	dataframe1_error++;
}
inline void inc_dataframe1_ok() {
	dataframe1_ok++;
}
inline void inc_dataframe2_error() {
	dataframe2_error++;
}
inline void inc_dataframe2_ok() {
	dataframe2_ok++;
}
inline void error_stat() {
	print("General error: ");
	print(general_error);
	print(" Read error type 1: ");
	print(dataframe1_error);
	print(" / ");
	print(dataframe1_ok);
	print(" type 2: ");
	print(dataframe2_error);
	print(" / ");
	print(dataframe2_ok);
	println("");
}

#define FREERAM_FREQ 60
extern "C" char* sbrk(int incr);
unsigned long last_freeram = 0;
int freeRam() {
	char top;

	return &top - reinterpret_cast<char*>(sbrk(0));
}

void display_freeram() {
	print(F("- SRAM left: "));
	println(freeRam());
}

#else

inline void print(...) {}
inline void println(...) {}
inline void inc_general_error() {}
inline void inc_dataframe1_error() {}
inline void inc_dataframe1_ok() {}
inline void inc_dataframe2_error() {}
inline void inc_dataframe2_ok() {}
inline void error_stat() {}
inline void display_freeram() {}

#endif


void switchled() {
	if(digitalRead(LED_BUILTIN) == HIGH)
		digitalWrite(LED_BUILTIN, LOW);
	else
		digitalWrite(LED_BUILTIN, HIGH);
}

void blink() {
	digitalWrite(LED_BUILTIN, LOW);
	delay(150);
	digitalWrite(LED_BUILTIN, HIGH);
}

void panic() {
	while(true) {
		blink();
		delay(150);
	}
}

#define DATA_PIN 0
#define RING_BUFFER_SIZE 4096
#define DATASZ1 128 /* max value, may vary */ 
#define MIN_DATASZ1 36
#define DATASZ2 41
#define SYNC_SEQ_LEN 8
#define MAX_DATASZ MAX(DATASZ1, DATASZ2)

#define VALUES 9
#define VALUE0_MIN 200
#define VALUE0_MAX 330
#define VALUE1_MIN 420
#define VALUE1_MAX 560
#define VALUE2_MIN 680
#define VALUE2_MAX 800
#define VALUE3_MIN 950
#define VALUE3_MAX 1200
#define VALUE4_MIN 1900
#define VALUE4_MAX 2100
#define VALUE5_MIN 2400
#define VALUE5_MAX 2500
#define VALUE6_MIN 2900
#define VALUE6_MAX 3100
#define VALUE7_MIN 3300
#define VALUE7_MAX 3500
#define VALUE8_MIN 3800
#define VALUE8_MAX 4200

#define IS_VALUE(B) \
inline bool is_value##B (unsigned long d) { \
	return d > VALUE##B##_MIN && d < VALUE##B##_MAX; \
}

IS_VALUE(0);
IS_VALUE(1);
IS_VALUE(2);
IS_VALUE(3);
IS_VALUE(4);
IS_VALUE(5);
IS_VALUE(6);
IS_VALUE(7);
IS_VALUE(8);

struct entry {
	unsigned long timestamp;
	short temp;
	unsigned char ident;
	unsigned char channel;
	unsigned char humidity;
};

void set_entry(struct entry *e, unsigned char ident, unsigned char channel,
	       unsigned long timestamp, short temp, unsigned char humidity) {
	e->ident = ident;
	e->channel = channel;
	e->timestamp = timestamp;
	e->temp = temp;
	e->humidity = humidity;
}

inline short int12toshort(short x) {
	return x & 0x800 ? x | 0xf000 : x;
}

unsigned long age(unsigned long old, unsigned long current) {
	if (current >= old)
		return current - old;
	else /* Overflow detected */
		return ULONG_MAX / 1000 - old + current;
}

#if DEBUG >= 1
void print_entry(struct entry *e) {
	print(e->ident);
	print("/");
	print(e->channel);
	print(":\t");
	print(e->timestamp);
	print("s\t");
	print(e->temp);
	print("dC\t");
	print(e->humidity);
	println("%");
}
#else
void print_entry(struct entry *e) {}
#endif

int irq = digitalPinToInterrupt(DATA_PIN);
unsigned long timings[RING_BUFFER_SIZE];
volatile char dataframe[MAX_DATASZ];
volatile int dataframesz;
volatile int data_ready = 0;
unsigned long last_cleanup = 0;

BLEService TempSensor(SERVICE_TEMPSENSOR_UUID);
BLECharacteristic Temperature(CHAR_TEMPERATURE_UUID, BLERead | BLEIndicate,
			      9, true);

char duration_to_bit(unsigned long d)
{
	if (is_value0(d))
		return '0';
	else if (is_value1(d))
		return '1';
	else if (is_value2(d))
		return '2';
	else if (is_value3(d))
		return '3';
	else if (is_value4(d))
		return '4';
	else if (is_value5(d))
		return '5';
	else if (is_value6(d))
		return '6';
	else if (is_value7(d))
		return '7';
	else if (is_value8(d))
		return '8';
	else if (d <= VALUE0_MIN)
		return '.';
	else if (d >=  VALUE8_MAX)
		return '_';
	else
		return '?';
}

inline unsigned int index_sub(unsigned int idx, int i)
{
	return (idx + RING_BUFFER_SIZE - i) % RING_BUFFER_SIZE;
}

/* Dataframe1 sync sequence is 81 */
bool is_sync1(unsigned int idx)
{
	return is_value1(timings[idx]) &&
		is_value8(timings[index_sub(idx, 1)]);
}

/* Sync sequence is 22222222 (x8) */
bool is_sync2(unsigned int idx)
{
	for (int i = 0; i < SYNC_SEQ_LEN; i++)
		if (!is_value2(timings[index_sub(idx, i)]))
			return false;
	return true;
}

void handler()
{
	static unsigned long duration = 0;
	static unsigned long lastTime = 0;
	static unsigned int ring_index = 0;
	static int datacount = 0;
	static int in_dataframe = 0;
	/* A bit is coded by two impulsions, the first one is the
	 * significant bit and the second is for synchronisation */
	static bool is_bit; 

	if (data_ready) {
		return;
	}

	unsigned long time = micros();
	duration = time - lastTime;
	lastTime = time;

	ring_index = (ring_index + 1) % RING_BUFFER_SIZE;
	timings[ring_index] = duration;

	if (in_dataframe == 1) {
		is_bit = !is_bit;
		if (is_bit) {
			if (is_value3(duration))
				dataframe[datacount++] = 0;
			else if (is_value4(duration))
				dataframe[datacount++] = 1;
			else if (is_value8(duration)) {
				if (datacount < MIN_DATASZ1)
					/* Only consider dataframe1 of some size */
					goto dataframe1_error;
				/* All dataframe is read */
				in_dataframe = 0;
				dataframesz = datacount;
				datacount = 0;
				inc_dataframe1_ok();
				data_ready = 1;
			} else
				goto dataframe1_error;

		} else
			/* Sync impulsion is always short */
			if (!is_value1(duration)) {
			dataframe1_error:
				/* Error */
				in_dataframe = 0;
				datacount = 0;
				inc_dataframe1_error();
			}

	} else if (in_dataframe == 2) {
		is_bit = !is_bit;
		if (is_bit) {
			if (is_value0(duration))
				dataframe[datacount++] = 0;
			else if (is_value1(duration))
				dataframe[datacount++] = 1;
			else
				goto dataframe2_error;
		} else {
			/* Sync impulsion is always the opposite of the bit one */
			if (is_value0(duration)) {
				if (dataframe[datacount-1] == 0)
					goto dataframe2_error;
			} else if (is_value1(duration)) {
				if (dataframe[datacount-1] == 1)
					goto dataframe2_error;
			} else {
			dataframe2_error:
				in_dataframe = 0;
				datacount = 0;
				inc_dataframe2_error();
			}
		}
		if (datacount == DATASZ2 && !is_bit) {
			/* All dataframe received, including the last sync impuls */
			in_dataframe = 0;
			dataframesz = datacount;
			datacount = 0;
			inc_dataframe2_ok();
			data_ready = 2;
		}
	} else if (is_sync1(ring_index)) {
		in_dataframe = 1;
		is_bit = false; /* Next impulsion is a bit */
	} else if (is_sync2(ring_index)) {
		in_dataframe = 2;
		is_bit = false;
	}

#ifdef DEBUG
	if (ring_index == RING_BUFFER_SIZE - 1)
		buffer_full = true;
#endif
}

void setup()
{
	pinMode(DATA_PIN, INPUT);
	pinMode(LED_BUILTIN, OUTPUT);
	blink();
#ifdef DEBUG
	Serial.begin(115200);
	while (!Serial && millis() < 10000);
	if (!Serial)
		panic();
	println("Started.");
#endif

	attachInterrupt(irq, handler, CHANGE);
	/* Now activate the BLE device.  It will start continuously transmitting BLE
	   advertising packets and will be visible to remote BLE central devices
	   until it receives a new connection */
	if (!BLE.begin()) {
		panic();
	}
	blink();

	// set advertised local name and service UUID:
	BLE.setDeviceName(DEVICE_NAME);
	BLE.setLocalName(DEVICE_NAME);
	BLE.setAdvertisedService(TempSensor);

	TempSensor.addCharacteristic(Temperature);
	BLE.addService(TempSensor);
	Temperature.setValue("DEADBEEF");
	// Build scan response data packet
	//BLEAdvertisingData scanData;
	//scanData.setLocalName("FOOBAR Temperature");
	// Copy set parameters in the actual scan response packet
	//BLE.setScanResponseData(scanData);

	BLE.advertise();
	println("advertising ...");
	blink();
}

void loop()
{
	unsigned long current_time = millis() / 1000;
	BLEDevice central = BLE.central();

	if (central) {
		static unsigned long last_time = 0;
		if (current_time - last_time  >= 10) {
			print("Connected to central: ");
			println(central.address());
			last_time = current_time;
		}
	}
	if (data_ready) {
		noInterrupts();
		switchled();
		int humidity, temp_deci, ident, channel;
		unsigned char data_u4[MAX_DATASZ / 4 + 1];
		
		memset(data_u4, 0, dataframesz / 4 + 1);
		
		print("Received ");
		print(dataframesz);
		print(" bits dataframe of type ");
		print(data_ready);
		print(" at ");
		print(current_time);
		println("s.");
		error_stat();

		for (int i = 0; i < dataframesz; i++) {
			data_u4[i / 4] += (dataframe[i] << (3 - (i % 4)));
		}

#if DEBUG >= 2
		for (int i = 0; i < dataframesz; i++) {
			print((int)dataframe[i]);
			if ((i % 4) == 3)
				print(' ');
		}
		println("");

		for (int i = 0; i < dataframesz / 4; i++) {
			print(data_u4[i]);
			print(' ');
		}
		println("");
#endif

		if (data_ready == 1) {
			if(data_u4[6] != 0xf) {
				inc_general_error();
				println("Unexpected value for bits 24-27");
			}
		}
			
		ident = (data_u4[0] << 4) + data_u4[1];
		channel  = (data_u4[2] & 0x3);
		temp_deci = int12toshort((data_u4[3] << 8) +
					 (data_u4[4] << 4) +
					 data_u4[5]);
		if (data_ready == 1) {
			/* Channel number coded from zero */
			channel++;
			humidity = (data_u4[7] << 4) + data_u4[8];
		} else {
			temp_deci -= 900;
			humidity = (data_u4[6] << 4) + data_u4[7];
		}

		print(ident);
		print(": ch");
		print(channel);
		print("\t");
		print(temp_deci / 10);
		print(".");
		print(abs(temp_deci % 10));
		if (data_ready ==1) {
			print("C\t");
		} else {
			float t_celcius = ((float)temp_deci - 320) / 18;
			print("F\t");
			print(t_celcius);
			print("C\t");
		}
		print(humidity);
		println("%");

		if (data_ready ==1) {
			static struct entry last = {0, 0, 0, 0, 0};
			struct entry e;

			set_entry(&e, ident, channel, current_time,
				  temp_deci, humidity);
			print_entry(&e);

			/* Only update non duplicate value */
			if ((e.ident == last.ident) &&
			    (e.channel == last.channel) &&
			    (age(last.timestamp, e.timestamp) < 2)) {
				if ((e.temp != last.temp) ||
				    (e.humidity != last.humidity)) {
					println("Values dont match:");
					print_entry(&last);
					inc_general_error();
				}
			} else
				Temperature.setValue((uint8_t*)&e, 9);
			memcpy(&last, &e, sizeof(struct entry));
		}
		data_ready = 0;
		switchled();
		interrupts();
	}
#ifdef DEBUG
	if (age(last_freeram, current_time) > FREERAM_FREQ) {
		display_freeram();
		last_freeram = current_time;
	}
#endif
#if DEBUG >= 3
	if (buffer_full) {
		for (int i = 0; i < RING_BUFFER_SIZE; i++) {
			unsigned long d = timings[i];
			print(duration_to_bit(d));
			if ( (i+1) % SCREEN_WIDTH == 0)
				println("");
		}
		buffer_full = false;
	}
#endif
}

