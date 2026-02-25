import glob
import os
import subprocess
from datetime import date, timedelta

cwd = os.getcwd()
# print(cwd)
path = os.getcwd() + "/Sources/BHUVAN/"
script_path = cwd + "/Sources/BHUVAN/scripts/transformer.py"
PY = input("\n Enter the path of your python interpreter:  ")
print(path)
for year in [2021,2022,2023,2024]: #years that you want to run 
    print(year)
    year = str(year)
    for month in [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
    ]:
        files1 = glob.glob(
            path + "data/tiffs/removed_watermarks/" + year + "_??_" + month + "*.tif"
        )
        files2 = glob.glob(
            path + "data/tiffs/removed_watermarks/" + year + "_??-??_" + month + "*.tif"
        )
        # files3 = glob.glob(
        #     path + "data/tiffs/removed_watermarks/" + year + "_??_??_" + month + "*.tif"
        # )
        files = files1 + files2
        if len(files) == 0:
            print(f"No files for the month {month}")
            continue
        else:
            print("Number of images:", len(files))
            subprocess.call([PY, script_path, year, month]) # instead of the "python3" put the path the of the python complier you are using 
