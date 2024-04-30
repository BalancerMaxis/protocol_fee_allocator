import os
import pandas as pd

# This script combines all the incentives_ csvs in the directory specified into a single csv.
# It adds a column that includes the important part of the string from the file it came from in each row of the csv.


# Directory containing the CSV files
directory = 'fee_allocator/allocations'

# Initialize an empty DataFrame to store combined data
combined_data = pd.DataFrame()

# Iterate over files in the directory
for filename in os.listdir(directory):
    if filename.startswith("incentives_") and filename.endswith(".csv"):
        # Extract the date string from the filename without the ".csv" extension
        date_string = filename.replace("incentives_","").replace(".csv", "")
        # Read the CSV file
        df = pd.read_csv(os.path.join(directory, filename))
        # Add a new column for the date string
        df['date string'] = date_string
        # Append the data to the combined DataFrame
        combined_data = pd.concat([combined_data, df])

# Write the combined data to a single CSV file
combined_data.to_csv(os.path.join(directory, 'combined_incentives.csv'), index=False)
