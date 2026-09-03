from pathlib import Path
from datetime import date

def create_folder(path):
    # check if folder exists
    if not Path(path).exists():
        Path(path).mkdir(parents=True, exist_ok=True)
    else:
        print(f"Folder {path} already exists")

def list_files(path):
    """ list all files in folder"""
    # ignore .DS_Store and sorted
    pfiles = [f for f in Path(path).iterdir() if f.is_file() and not f.name.startswith(".")]
    return sorted(pfiles)

def subset_files(fileslist, start_date, end_date):
    subset = []

    # determine minimum of maximum date
    for f in fileslist:
        file_date = f.name.split("_")[0]
        file_year = file_date[:4]
        file_month = file_date[4:6]
        file_day = file_date[6:]

        # create date object
        date_obj = date(int(file_year), int(file_month), int(file_day))

        if date_obj >= start_date and date_obj <= end_date:
            subset.append(f)

    return subset
