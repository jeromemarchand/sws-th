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

def main():
    parser = argparse.ArgumentParser(description='Extract latest temperatures')
    parser.add_argument('-c', '--configfile',
                        help='config file (default: none)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="be more verbose")
    parser.add_argument('-o', '--output', help="set output file")
    parser.add_argument('ifile', nargs='?', help="input file")
    parser.add_argument('-s', '--socket', action='store_true', help="connect to local socket")
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

    if args.socket:
        message = read_socket()
    elif args.ifile:
        message = read_file(args.ifile)
    else:
        print("Error: no input\n")
        exit();

    if True:
        l = re.compile(r'(\d{4}-\d\d-\d\d \d\d:\d\d)\s*(\d* \d)\s*(-?\d*.\d)([CF]) (\d*)%')
        s = re.compile(r'(\d*) (\d)')
        for line in message.splitlines():
            if line[0] == '#':
                # TODO: uses regex to allow blank char before '#'?
                continue
            vprint(f'Processing line: {line}')
            m = l.match(line)
            if not m:
                print(f"Line doesn't match: {line}")
            sensor = m.group(2)
            if args.configfile:
                mm = s.match(sensor)
                sensorid = (mm.group(1), mm.group(2))
                if sensorid not in configsensors:
                    vprint(f'Skipping unknown sensor: {sensor}')
                    continue
                else:
                    sensor = configsensors[sensorid]

            vprint(f'Date: {m.group(1)} Sensor: {sensor} Temp: {m.group(3)}{m.group(4)} Hum: {m.group(5)}')
            time = dt.datetime.fromisoformat(m.group(1));

            # The file is in chronological order: just replace old value if there is one
            # Don't replace Celsius by Farenheit
            if m.group(4) == 'C' or not (sensor in sensors):
                sensors[sensor] = {'temp':float(m.group(3)), 'unit':m.group(4),
                                   'humidity':float(m.group(5)), 'time':time}

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
            s = {'temp':' ----', 'unit':'?', 'humidity':'----', 'time':'----'}
        else:
            s = sensors[sensor]
            tl = dt.datetime.combine(dt.date.today(), dt.time()) - dt.timedelta(minutes=15)
            if s['time'] > tl:
                fresh = True
        if fresh:
            print("  <tr>", file=f)
        else:
            print("  <tr bgcolor=\"#EDD\">", file=f)
        print(f"    <td>{sensor:10}:</td> <td>{s['temp']:5}&deg;{s['unit']}</td> <td>{s['humidity']:4} %</td> <td>{s['time']}</td>", file=f)
        print("  </tr>", file=f)
    print("</table>", file=f)

if __name__ == '__main__':
    main()
