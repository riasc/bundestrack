# Standard
from pathlib import Path
from datetime import date

# class

import utility
import abstimmung



def main():
    datapath = Path("data")

    legper = 20 # legislative period

    start = date(2024,11,30)
    end = date(2025,1,31)









    # list files in data folder (under period)
    files = utility.list_files(datapath / f"{legper}")
    subset_files = utility.subset_files(files, start, end)

    print(subset_files)

    vote = abstimmung.NamentlicheAbstimmung(subset_files)








    # create datafolder for the period
    #utility.create_folder(datapath / f"{legper}")






main()
