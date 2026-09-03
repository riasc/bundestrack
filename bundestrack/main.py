# Standard
import argparse
from pathlib import Path
from datetime import date

# class

import utility
import abstimmung


def parse_date(s):
    return date.fromisoformat(s)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", type=int, default=20, help="legislative period")
    parser.add_argument("--start", type=parse_date, default=date(2000, 1, 1))
    parser.add_argument("--end", type=parse_date, default=date(2100, 1, 1))
    args = parser.parse_args()

    datapath = Path("data")

    vote = abstimmung.NamentlicheAbstimmung(datapath, args.period, args.start, args.end)



main()
