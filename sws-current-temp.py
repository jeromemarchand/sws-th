#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2024 Jerome Marchand

import argparse
import datetime as dt
import re
import socket

verbose = False

def vprint(*args, **kwargs):
    if verbose:
        print(*args, **kwargs)

def convertFtoC(temp):
    return round((temp - 32) / 1.8, 1)

def convertCtoF(temp):
    return round(temp * 1.8 + 32, 1)

sensors = {}

# Local server
HOST = "127.0.0.0"
PORT = 12345

def read_socket():
    s = socket.socket()
    s.connect((HOST, PORT))
    message = s.recv(4096).decode()
    s.close()
    return message

def read_file(ifile):
    return open(ifile, 'r', encoding="utf-8").read()

def process_message(m, sensors, configsensors):
    l = re.compile(r'(\d{4}-\d\d-\d\d \d\d:\d\d)\s*(\d* \d)\s*(-?\d*.\d)([CF]) (\d*)%( (.*))?')
    s = re.compile(r'(\d*) (\d)')
    for line in m.splitlines():
        if line[0] == '#':
            # TODO: uses regex to allow blank char before '#'?
            continue
        vprint(f'Processing line: {line}')
        m = l.match(line)
        if not m:
            print(f"Line doesn't match: {line}")
        sensor = m.group(2)
        if configsensors:
            mm = s.match(sensor)
            sensorid = (mm.group(1), mm.group(2))
            if sensorid not in configsensors:
                vprint(f'Skipping unknown sensor: {sensor}')
                continue
            else:
                sensor = configsensors[sensorid]

        vprint(f'Date: {m.group(1)} Sensor: {sensor} Temp: {m.group(3)}{m.group(4)} Hum: {m.group(5)} \"{m.group(7)}\"')
        time = dt.datetime.fromisoformat(m.group(1));

        # Update the sensor if the data is more  recent
        # Prefer Celsius to Farenheit
        if not (sensor in sensors) or (sensors[sensor]['time'] < time) or ((sensors[sensor]['time'] == time) and (sensors[sensor]['unit'] == 'F') and  (m.group(4) == 'C')):
            sensors[sensor] = {'temp':float(m.group(3)), 'unit':m.group(4),
                               'humidity':float(m.group(5)), 'time':time, 'low_power':m.group(7)}

    return sensors

def main():
    parser = argparse.ArgumentParser(description='Extract latest temperatures')
    parser.add_argument('-c', '--configfile',
                        help='config file (default: none)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="be more verbose")
    parser.add_argument('-o', '--output', help="set output file")
    parser.add_argument('ifile', nargs='?', help="input file")
    parser.add_argument('-s', '--socket', action='store_true', help="connect to local socket")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-C', '--celcius', action='store_true', help="converts to Celsius")
    group.add_argument('-F', '--fahrenheit', action='store_true', help="converts to Fahrenheit")
    args = parser.parse_args()

    global verbose
    verbose = args.verbose

    if args.configfile:
        configsensors = {}
        with open(args.configfile, 'r', encoding="utf-8") as f:
            l = re.compile(r'\s*(\d*)\s*(\d)\s*(.*)\n?')
            for line in f:
                if line[0] == '#' or line == '\n':
                    # ignore comments or empty lines
                    continue
                m = l.match(line)
                if not m:
                    print(f"Line doesn't match \"{line}\"")
                configsensors[(m.group(1), m.group(2))] = m.group(3);
                vprint(f'Named sensor: {m.group(3)}')
    else:
        configsensors = None

    sensors = {};
    if args.socket:
        sensors = process_message(read_socket(), sensors, configsensors) 
    if args.ifile:
        sensors = process_message(read_file(args.ifile), sensors, configsensors)
    elif not args.socket:
        print("Error: no input\n")
        exit();

    if args.output:
        f = open(args.output, "w", encoding="utf-8")
    else:
        f = None
    print("<table>", file=f)
    for sensor in configsensors.values():
        fresh = False
        vprint(f'Processing sensor: {sensor}')
        if sensor not in sensors:
            vprint(f'Missing data for sensor: {sensor}')
            s = {'temp':' ----', 'unit':'?', 'humidity':'----', 'time':'----', 'low_power':''}
        else:
            s = sensors[sensor]
            tl = dt.datetime.combine(dt.date.today(), dt.time()) - dt.timedelta(minutes=15)
            if s['time'] > tl:
                fresh = True
        if s['low_power'] == "Low Power":
            print("  <tr bgcolor=\"#FF9\">", file=f)
        elif fresh:
            print("  <tr>", file=f)
        else:
            print("  <tr bgcolor=\"#EDD\">", file=f)
        if args.celcius and s['unit'] == 'F':
            temp = convertFtoC(s['temp'])
            unit = 'C'
        elif args.fahrenheit and s['unit'] == 'C':
            temp = convertCtoF(s['temp'])
            unit = 'F'
        else:
            temp = s['temp']
            unit =s['unit']
        print(f"    <td>{sensor:10}:</td> <td>{temp:5}&deg;{unit}</td> <td>{s['humidity']:4} %</td> <td>{s['time']}</td>", file=f)
        print("  </tr>", file=f)
    print("</table>", file=f)

if __name__ == '__main__':
    main()
