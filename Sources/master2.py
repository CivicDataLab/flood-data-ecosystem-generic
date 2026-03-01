import pandas as pd
import os
import glob
import geopandas as gpd
import warnings
warnings.filterwarnings("ignore")

# ==============================
# Paths
# ==============================
variables_data_path = os.path.join(os.getcwd(), 'Sources/master/')

od_sd_files = glob.glob(os.path.join(os.getcwd(), 'Maps/Geojson/*_subdistricts.geojson'))
if not od_sd_files:
    raise FileNotFoundError("No *_subdistricts.geojson file found")

od_sd = od_sd_files[0]
state_sd = gpd.read_file(od_sd)

# ==============================
# Date Input
# ==============================
start_date = input("Enter start date (YYYY-MM-DD): ").strip()
end_date = input("Enter end date (YYYY-MM-DD): ").strip()

try:
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    if end_date < start_date:
        raise ValueError("End date must be after start date.")

    date_range = pd.date_range(start=start_date, end=end_date, freq='MS')

except Exception as e:
    raise ValueError(f"Invalid date input: {e}")

formatted_dates = [date.strftime('%Y_%m') for date in date_range]

# ==============================
# Base Master Frame Creation
# ==============================
name_col = 'block_name' if 'block_name' in state_sd.columns else 'sdtname'
area_col = 'block_area' if 'block_area' in state_sd.columns else 'st_area'

dfs = []
for year_month in formatted_dates:
    df = state_sd[[name_col, 'object_id', area_col, 'dtname']].copy()
    df.columns = ['subdistrict_name', 'object_id', 'block_area', 'district']
    df['timeperiod'] = year_month
    dfs.append(df)

master_df = pd.concat(dfs).reset_index(drop=True)

# ==============================
# Monthly Variables
# ==============================
monthly_variables = [
    'total_tender_awarded_value',
    'RIDF_tenders_awarded_value',
    'Preparedness Measures_tenders_awarded_value',
    'Immediate Measures_tenders_awarded_value',
    'Others_tenders_awarded_value',
    'rainfall',
    'runoff',
    'inundation'
]

for variable in monthly_variables:
    print(f"Merging: {variable}")
    variable_df = pd.read_csv(os.path.join(variables_data_path, variable + '.csv'))
    variable_df = variable_df.drop_duplicates()
    master_df = master_df.merge(variable_df,
                                on=['object_id', 'timeperiod'],
                                how='left')
    master_df = master_df.drop(columns=master_df.filter(regex='_x$|_y$').columns)

# ==============================
# Annual Variables
# ==============================
master_df['year'] = master_df['timeperiod'].str[:4].astype(int)

annual_variables = [
    'mean_sex_ratio',
    'sum_aged_population',
    'sum_young_population',
    'sum_population'
]

for variable in annual_variables:
    print(f"Merging annual: {variable}")
    variable_df = pd.read_csv(os.path.join(variables_data_path, variable + '.csv'))
    variable_df = variable_df.rename(columns={'timeperiod': 'year'})
    master_df = master_df.merge(variable_df,
                                on=['object_id', 'year'],
                                how='left')

# ==============================
# One-time Variables
# ==============================
onetime_variables = [
    'Schools',
    'RailLengths',
    'RoadLengths',
    'HealthCenters',
    'slope_elevation',
    'antyodaya_variables',
    'drainage_density',
    'distance_from_river',
    'distance_from_sea'
]

master_df['year'] = ''

for variable in onetime_variables:
    print(f"Merging one-time: {variable}")
    variable_df = pd.read_csv(os.path.join(variables_data_path, variable + '.csv'))
    variable_df['year'] = ''
    master_df = master_df.merge(variable_df,
                                on=['object_id', 'year'],
                                how='left')
    master_df = master_df.drop(columns=master_df.filter(regex='_y$').columns)
    master_df.columns = master_df.columns.str.replace('_x$', '', regex=True)

# ==============================
# Imputations
# ==============================

# Rainfall
for col in ['max_rain', 'mean_rain', 'sum_rain']:
    if col in master_df.columns:
        master_df[col] = master_df[col].fillna(
            master_df.groupby('object_id')[col].transform('mean')
        )

# Runoff
for col in ['Sum_Runoff', 'Peak_Runoff', 'Mean_Daily_Runoff']:
    if col in master_df.columns:
        master_df[col] = master_df[col].fillna(
            master_df.groupby('object_id')[col].transform('mean')
        )

# Antyodaya variables
district_impute_cols = [
    'block_nosanitation_hhds_pct',
    'block_piped_hhds_pct',
    'avg_electricity',
    'net_sown_area_in_hac'
]

for col in district_impute_cols:
    if col in master_df.columns:
        master_df[col] = master_df[col].fillna(
            master_df.groupby('district')[col].transform('mean')
        )

if 'avg_tele' in master_df.columns:
    master_df['avg_tele'] = master_df['avg_tele'].fillna(
        master_df.groupby('district')['avg_tele'].transform('median')
    )

# Final fallback
master_df = master_df.fillna(0)

# Remove merge suffix leftovers
master_df = master_df.loc[:, ~master_df.columns.str.endswith('_x')]
master_df = master_df.loc[:, ~master_df.columns.str.endswith('_y')]

# ==============================
# Save Output
# ==============================
master_folder = input("Enter the path to RiskscoreModel data folder: ").strip()

if not os.path.isdir(master_folder):
    raise FileNotFoundError("Folder does not exist")

file_path = os.path.join(master_folder, "MASTER_VARIABLES.csv")

master_df.to_csv(file_path, index=False)

print(f"\nFile saved at: {file_path}")
print(f"Final shape: {master_df.shape}")