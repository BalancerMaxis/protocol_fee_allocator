import os
import json
import csv

# create a CSV file named combined_fees.csv to put data into
csvfile = open("combined_fees.csv", "w")
writer = csv.writer(csvfile)
# write the header row
writer.writerow(["period", "chain", "swept"])
# for each file named fess_YYYY_MM_DD_YYYY_MM_DD.json in the current directory
for file in os.listdir("."):
    if file.startswith("fees_") and file.endswith(".json"):
        with open(file, "r") as f:
            data = json.load(f)
            for chain, swept in data.items():
                if isinstance(swept, int):
                    swept = float(swept / 1e6)
                writer.writerow(
                    [file.replace("fees_", "").replace(".json", ""), chain, swept]
                )

## close csv file
csvfile.close()
