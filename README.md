# SWS TH Weather Station

This is the software for a basic weather station I build around Sencor
SWS TH2850-2999-3851-5150 remote temperature and humidity sensors, a
RF433 receptor and a Seeed Studio XIAO nRF52840 board.

Temperature and humidity data is collected on the board from the
sensors thanks to the RF433 module. It is send to the weather station
server over Bluetooth.

This is a home project that just aim at fulfilling my personal
need. Don't expect professional coding standard or ease of use. You
need some basic Arduino development knowledge to make it
work. Nevertheless, I thought it might be of interest to someone
beside myself.

The code could be reused with some change for other Arduino compatible
boards.  I imagine that some of the data collection code could be used
for other sensors as well. At least, I can receive data from unknown
sensors in my neighborhood, that uses the same or a very similar
protocol. You'll have to check that by yourself.

The use of Bluetooth to communicate with the server might be an
overkill and in retrospect USB would have been enough. On an earlier
version of the project, I used the RF433 module directly on a
RaspberryPi. It suffered for a poor range which is why I chose a board
with a Bluetooth chip. As it turned out, the range of 433 MHz
communication with the same RF433 module improved significantly with
the Arduino board compared to RPi. I didn't investigated
why. Ironically, I have more range issue with BLE now.