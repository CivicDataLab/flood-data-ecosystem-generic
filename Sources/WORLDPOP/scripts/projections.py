import pandas as pd
import glob
import numpy as np
from sklearn.linear_model import LinearRegression
import os
path = os.path.join(os.getcwd(), "Sources", "WORLDPOP")
print(path)
import sys
global projected_variable
projected_variable = sys.argv[1]

# -------------------------------------------------------------------
# FILE SEARCH
# -------------------------------------------------------------------

def flatten(l):
    return [item for sublist in l for item in sublist]

files = glob.glob(os.path.join(os.getcwd(), "Sources/WORLDPOP/data/worldpopstats_*.csv"))
dfs = []
for file in files:
    print("file: "+ file)
    df = pd.read_csv(file)
    df['year'] = int(file.split('_')[-1][:-4])
    dfs.append(df)

master_df = pd.concat(dfs)
master_df = master_df.sort_values(by='year').reset_index(drop=True)

# -------------------------------------------------------------------
# DATA PROJECTION TILL 2025 
# -------------------------------------------------------------------
def extrapolate_variable(rc_data):
    years = np.array(rc_data['year'].tolist())
    values = np.array(rc_data[projected_variable].tolist())

    years = years.reshape(-1, 1)
    values = values.reshape(-1, 1)

    model = LinearRegression()
    model.fit(years, values)

    projection_years = np.array([2021, 2022, 2023, 2024, 2025]) #add according to the years you want to prject
    projection_years = projection_years.reshape(-1, 1)

    projected_values = model.predict(projection_years)
    return flatten(projected_values)

# -------------------------------------------------------------------
# GROUPING THE DATA BY STATE FOR THE EXTRAPOLATED YERAS 
# -------------------------------------------------------------------
extrapolated_data = master_df.groupby('object_id').apply(extrapolate_variable)

# Create a new DataFrame from the extrapolated data
extrapolated_df = pd.DataFrame(extrapolated_data.tolist(), columns=['2021', '2022', '2023','2024','2025'])
extrapolated_df.index = extrapolated_data.index
extrapolated_df = extrapolated_df.reset_index()

extrapolated_df = pd.melt(extrapolated_df, id_vars=['object_id'], var_name='year', value_name=projected_variable)

# Add state and years columns to the extrapolated DataFrame
#extrapolated_df['object_id'] = df['object_id'].unique()
#extrapolated_df['year'] = [2021, 2022, 2023]

# Reorder the columns
#extrapolated_df = extrapolated_df[['year', 'object_id', 2021, 2022, 2023]]

extrapolated_df.to_csv(path+'data/'+projected_variable+'_projections.csv', index=False)