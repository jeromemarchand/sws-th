#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2022, 2023 Jerome Marchand

import matplotlib.pyplot as plt
import matplotlib
import argparse
import datetime as dt
import re

verbose = False

def vprint(*args, **kwargs):
    if verbose:
        print(*args, **kwargs)

sensors = {}

def main():
    parser = argparse.ArgumentParser(description='Plot Meteodata data')
    parser.add_argument('-c', '--configfile',
                        help='config file (default: none)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="be more verbose")
    dategroup = parser.add_mutually_exclusive_group()
    dategroup.add_argument('-f', '--fromdate',
                        help="only plot data after date")
    # -f and -t must be able to work together
    # mutually exclusive group does not work entirely here
    parser.add_argument('-t', '--todate',
                        help="only plot data before date")
    dategroup.add_argument('-n', '--today', action='store_true',
                        help="only plot data from today")
    dategroup.add_argument('-y', '--yesterday', action='store_true',
                        help="only plot data from yesterday")
    dategroup.add_argument('-l', '--last', type=int,
                        help="only plot data from last N days (i.e. 24 hour periods)")

    parser.add_argument('-b', '--backend',
                        help="set matplotlib backend")
    parser.add_argument('-o', '--output',
                        help="set outputfile for file backend")
    
    parser.add_argument('ifile', help="input file")
    args = parser.parse_args()

    global verbose
    from_date = None
    to_date = None
    verbose = args.verbose

    if args.fromdate:
        from_date = dt.datetime.fromisoformat(args.fromdate)

    if args.todate:
        to_date = dt.datetime.fromisoformat(args.todate)

    if args.today:
        from_date = dt.datetime.combine(dt.date.today(), dt.time())
    if args.yesterday:
        to_date = dt.datetime.combine(dt.date.today(), dt.time())
        from_date = to_date - dt.timedelta(days=1)
    if args.last:
        from_date = dt.datetime.today() - dt.timedelta(days=args.last)

    if args.backend:
        matplotlib.use(args.backend)
        
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

    with open(args.ifile, 'r', encoding="utf-8") as f:
        l = re.compile(r'(\d{4}-\d\d-\d\d \d\d:\d\d)\s*(\d* \d)\s*(-?\d*.\d)C (\d*)%')
        s = re.compile(r'(\d*) (\d)')
        for line in f:
            if line[0] == '#':
                # TODO: uses regex to allow blank char before '#'?
                continue
            vprint(f'Processing line: {line}')
            m = l.match(line)
            if not m:
                print("Line doesn't match")
            sensor = m.group(2)
            if args.configfile:
                mm = s.match(sensor)
                sensorid = (mm.group(1), mm.group(2))
                if sensorid not in configsensors:
                    # ignore unknown sensors
                    continue
                else:
                    sensor = configsensors[sensorid]
            
            vprint(f'Date: {m.group(1)} Sensor: {sensor} Temp: {m.group(3)} Hum: {m.group(4)}')
            #time = dt.datetime.strptime(m.group(1), DATE_FMT);
            time = dt.datetime.fromisoformat(m.group(1));
            if to_date and time > to_date:
                vprint('Skip out of range sample: too recent')
                continue
            if from_date and time < from_date:
                vprint('Skip out of range sample: too old')
                continue

            if sensor not in sensors:
                sensors[sensor] = {'temp':{}, 'humidity':{}}
            sensors[sensor]['temp'][time] = float(m.group(3))
            sensors[sensor]['humidity'][time] = float(m.group(4))

    plt.rcParams["figure.figsize"] = (8,12)
    fig, axs = plt.subplots(2, 1)
    axs[0].set_ylabel('T°C')
    axs[0].set_ylim(bottom=-10, top=40)
    axs[0].yaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator(5))
    axs[0].xaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator(6))
    axs[0].grid(which='major', alpha=0.5)
    axs[0].grid(which='minor', alpha=0.2, linestyle=':')
    axs[1].set_ylabel('Hum. %')
    axs[1].set_ylim(bottom=0, top=100)
    axs[1].yaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator(4))
    axs[1].xaxis.set_minor_locator(matplotlib.ticker.AutoMinorLocator(6))
    axs[1].grid(which='major', alpha=0.5)
    axs[1].grid(which='minor', alpha=0.2, linestyle=':')
    for sensor in configsensors.values():
        vprint(f'Processing sensor: {sensor}')
        if sensor not in sensors:
            vprint(f'No data from sensor {sensor}: skip')
            continue
        s = sensors[sensor]
        axs[0].plot(list(s['temp'].keys()),
                    list(s['temp'].values()), label = 'T°C ' + sensor)
        axs[1].plot(list(s['humidity'].keys()),
                    list(s['humidity'].values()), label = 'Hum % ' + sensor)

    axs[0].legend()
    axs[1].legend()

    if args.output:
        plt.savefig(args.output)
    else:
        plt.show()


if __name__ == '__main__':
    main()
