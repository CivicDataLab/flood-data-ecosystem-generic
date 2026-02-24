import pandas as pd
import geopandas as gpd
import os
import glob

# =================================================
# CONFIG
# =================================================
cwd = os.getcwd()

# Paths
GEOJSON_DIR = os.path.join(cwd, 'Maps/Geojson')
HEALTH_CENTRES_FILE = os.path.join(cwd, 'Sources/BHARATMAPS/data/RawData/BharatMaps_HealthCenters.geojson')
OUTPUT_DIR = os.path.join(cwd, 'Sources/BHARATMAPS/data/variables')

# =================================================
# AUTO-DETECT STATE FROM SUBDISTRICT FILE
# =================================================
print("Searching for subdistrict file...")

# Find all files with '_subdistricts' in the name
subdistrict_files = glob.glob(os.path.join(GEOJSON_DIR, '*_subdistricts.geojson'))

if not subdistrict_files:
    raise FileNotFoundError(f"No subdistrict files found in {GEOJSON_DIR}")

if len(subdistrict_files) > 1: #better to keep only file with subdistrict boundary
    print("Multiple subdistrict files found:")
    for f in subdistrict_files:
        print(f"  - {os.path.basename(f)}")
    print(f"Using first file: {os.path.basename(subdistrict_files[0])}")

# Take the first file
subdistrict_file = subdistrict_files[0]

# Extract state name from filename
# Format: {state_name}_subdistricts.geojson
filename = os.path.basename(subdistrict_file)
state_name = filename.replace('_subdistricts.geojson', '')

print(f"✓ Detected state: {state_name}")
print(f"✓ Subdistrict file: {filename}")

# =================================================
# LOAD DATA
# =================================================
print("\nLoading data...")

# Load health centres
health_centres_gdf = gpd.read_file(HEALTH_CENTRES_FILE)
print(f"✓ Loaded {len(health_centres_gdf)} health centres")

# Load subdistricts
subdist_gdf = gpd.read_file(subdistrict_file)
print(f"✓ Loaded {len(subdist_gdf)} subdistricts for {state_name.upper()}")

# =================================================
# SPATIAL JOIN
# =================================================
print("\nPerforming spatial join...")

# Ensure same CRS
health_centres_gdf = health_centres_gdf.to_crs(subdist_gdf.crs)

# Spatial join: which health centres are in which subdistricts
health_centres_in_subdist = gpd.sjoin(
    subdist_gdf, 
    health_centres_gdf, 
    how="left", 
    predicate="contains"
)

print(f"✓ Spatial join complete")

# =================================================
# COUNT HEALTH CENTRES PER SUBDISTRICT
# =================================================
print("\nCounting health centres per subdistrict...")

# Identify ID and name columns (may vary by data source)
# Common column names for subdistrict ID/name
possible_id_cols = ['id', 'object_id', 'OBJECTID', 'subdist_id', 'sdtcode']
possible_name_cols = ['name', 'sdtname', 'subdistrict', 'subdist_name']

# Find which columns exist
id_col = None
name_col = None

for col in possible_id_cols:
    if col in subdist_gdf.columns:
        id_col = col
        break

for col in possible_name_cols:
    if col in subdist_gdf.columns:
        name_col = col
        break

if id_col is None:
    raise ValueError(f"Could not find ID column. Available columns: {subdist_gdf.columns.tolist()}")

if name_col is None:
    raise ValueError(f"Could not find name column. Available columns: {subdist_gdf.columns.tolist()}")

print(f"✓ Using ID column: {id_col}")
print(f"✓ Using name column: {name_col}")

# Group and count
health_centres_count = (
    health_centres_in_subdist
    .groupby([id_col, name_col])
    .size()
    .reset_index(name='health_centres_count')
)

# Add state name column
health_centres_count['state'] = state_name

print(f"✓ Counted health centres for {len(health_centres_count)} subdistricts")

# =================================================
# SAVE OUTPUT
# =================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)

output_file = os.path.join(OUTPUT_DIR,'HealthCenters.csv')
health_centres_count.to_csv(output_file, index=False)

print(f"\n Results saved to: {output_file}")
