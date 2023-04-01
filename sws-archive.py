#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2023 Jerome Marchand

import argparse
import datetime as dt
from dateutil.relativedelta import relativedelta
import re
import lzma
import shutil

def vprint(*args, **kwargs):
    if verbose:
        print(*args, **kwargs)

def archive(s, month):
    fname = ifile + f'.{month.year}-{month.month:02d}.xz'
    f = open(fname, 'wb')
    vprint(f'Compressing {fname}')
    f.write(lzma.compress(s.encode('utf-8')))
    f.close()

def main():
    parser = argparse.ArgumentParser(description='Archive Meteodata file')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='be more verbose')
    dategroup = parser.add_mutually_exclusive_group()
    dategroup.add_argument('-m', '--month', action='store_true',
                        help='split file by months (default)')
    dategroup.add_argument('-y', '--year', action='store_true',
                        help='split file by year')

    parser.add_argument('-b', '--backup', action='store_true',
                        help='backup original file')

    parser.add_argument('ifile', help='input file')
    args = parser.parse_args()

    global verbose
    global ifile
    verbose = args.verbose
    ifile = args.ifile

    if args.backup:
        vprint(f'Backup file: {ifile}.bak')
        shutil.copyfile(ifile, ifile + '.bak')

    by_year = args.year
    last_month = dt.date(dt.date.today().year, dt.date.today().month, 1) + relativedelta(months=-1)
    dont_archive = False
    working_month = None
    next_working_month = None
    out = ''

    with open(ifile, 'r', encoding='utf-8') as f:
        l = re.compile(r'(?P<date>\d{4}-\d\d-\d\d) (\d\d:\d\d)\s*(\d* \d)\s*(-?\d*.\d)C (\d*)%')
        for line in f:
            if line[0] == '#':
                # TODO: uses regex to allow blank char before '#'?
                out += line
                continue

            m = l.match(line)
            if not m:
                print("Line doesn't match")

            d = dt.date.fromisoformat(m.group('date'));

            if not dont_archive and d >= last_month:
                # From now on, keep the data uncompressed,
                # it's going back to the input file
                dont_archive = True
                if working_month:
                    archive(out, working_month)
                    out = ''
                vprint('Don\'t archive this month or the last: exit')

            if not working_month:
                working_month = dt.date(d.year, d.month, 1)
                next_working_month = working_month + relativedelta(months=+1)

            if not dont_archive and d >= next_working_month:
                archive(out, working_month)
                working_month = dt.date(d.year, d.month, 1)
                next_working_month = working_month + relativedelta(months=+1)
                out = ''

            out+= line

    f.close()
    f = open(ifile, 'w', encoding='utf-8')
    f.write(out)
    f.close()


if __name__ == '__main__':
    main()
