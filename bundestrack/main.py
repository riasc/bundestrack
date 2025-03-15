# Standard
from pathlib import Path
from datetime import date

# class

import utility
import abstimmung



def main():
    datapath = Path("data")

    legper = 20 # legislative period

    start = date(2021,10,26)
    end = date(2025,1,31)

    # list files in data folder (under period)


    vote = abstimmung.NamentlicheAbstimmung(datapath, 20, start, end)



    # create datafolder for the period
    #utility.create_folder(datapath / f"{legper}")






main()
