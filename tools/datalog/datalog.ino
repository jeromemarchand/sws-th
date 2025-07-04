// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * Copyright (c) 2022 Jerome Marchand
 *
 * Sniff RF 433 data from sws-th sensors
 */

// ring buffer size has to be large enough to fit
// data between two successive sync signals

#define RING_BUFFER_SIZE 512
#define SYNC_LENGTH 9000
#define SEP_LENGTH 500
#define BIT1_LENGTH 4000
#define BIT0_LENGTH 2000
#define SCREEN_WIDTH 128


/*
  Symbols:      0    1    2     3     4     5     6     7     8     9     A      B
  Delay (ms): 250, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 7500, 10000
  Limits:   180, 350, 610, 850, 1200, 1750, 2250, 2750, 3450, 4500, 6100, 8650, 12000
 */

#define NVALUES 12
const char symbols[NVALUES+2] = {'.', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', '_'};
unsigned short limits[NVALUES+1] = {180, 350, 610, 850, 1200, 1750, 2250, 2750, 3450, 4500, 6100, 8650, 12000};

#define DATA_PIN 2

int irq = digitalPinToInterrupt(DATA_PIN);
volatile unsigned short timings[RING_BUFFER_SIZE];
volatile bool received = false;


char duration_to_symbol(unsigned short d)
{
	for (int i = 0; i <= NVALUES; i++)
		if (d < limits[i])
			return symbols[i];
	return symbols[NVALUES+1];
}

void print_bit(unsigned short d)
{
	Serial.print(duration_to_symbol(d));
}

void handler()
{
	static unsigned long duration = 0;
	static unsigned long lastTime = 0;
	static unsigned int ringIndex = 0;

	long time = micros();
	//int value = digitalRead(DATA_PIN);
	duration = time - lastTime;
	lastTime = time;
	if (ringIndex == RING_BUFFER_SIZE - 1) {
		received = true;
		noInterrupts();
	}

	ringIndex = (ringIndex + 1) % RING_BUFFER_SIZE;
	timings[ringIndex] = (unsigned short) duration;
}

void setup()
{
	Serial.begin(115200);
	pinMode(DATA_PIN, INPUT);
	attachInterrupt(irq, handler, CHANGE);
	while (!Serial);
	Serial.println("Started.");
}

void loop()
{
	if (received == true) {
		int i;
		//noInterrupts();

		for (i = 0; i < RING_BUFFER_SIZE; i++) {
			unsigned short d = timings[i];
			print_bit(d);
			if ( (i+1) % SCREEN_WIDTH == 0)
				Serial.println("");
		}

		received = false;
		interrupts();
	}
}
