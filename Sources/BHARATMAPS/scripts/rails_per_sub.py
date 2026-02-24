import geopandas as gpd
import pandas as pd
import os
import glob

# =================================================
# CONFIG
# =================================================
cwd = os.getcwd()

# Paths
GEOJSON_DIR = os.path.join(cwd, 'Maps/Geojson')
RAILS_FILE = os.path.join(cwd, 'Sources/BHARATMAPS/data/RawData/BharatMaps_RailLenghths.geojson')
OUTPUT_DIR = os.path.join(cwd, 'Sources/BHARATMAPS/data/variables/RailLength')

# =================================================
# AUTO-DETECT STATE FROM SUBDISTRICT FILE
# =================================================
print("Searching for subdistrict file...")

# Find all files with '_subdistricts' in the name
subdistrict_files = glob.glob(os.path.join(GEOJSON_DIR, '*_subdistricts.geojson'))

if not subdistrict_files:
    raise FileNotFoundError(f"No subdistrict files found in {GEOJSON_DIR}")

if len(subdistrict_files) > 1:
    print("⚠️ Multiple subdistrict files found:")
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

# Load rails
rails_gdf = gpd.read_file(RAILS_FILE)
print(f"✓ Loaded {len(rails_gdf)} rail segments")

# Load subdistricts
subdist_gdf = gpd.read_file(subdistrict_file)
print(f"✓ Loaded {len(subdist_gdf)} subdistricts for {state_name.upper()}")

# =================================================
# INSPECT AND PREPARE DATA
# =================================================
print("\nInspecting rail data columns...")
print(f"Available columns: {rails_gdf.columns.tolist()}")

# Find length column (different naming conventions)
possible_length_cols = ['LENGTH', 'length', 'Length', 'len', 'distance', 'rail_length']
length_col = None

for col in possible_length_cols:
    if col in rails_gdf.columns:
        length_col = col
        break

# If no length column found, calculate from geometry
if length_col is None:
    print(" No length column found. Calculating from geometry...")
    # Reproject to projected CRS for accurate length calculation (meters)
    rails_temp = rails_gdf.to_crs(epsg=32644)  # UTM Zone 44N for India
    rails_gdf['calculated_length'] = rails_temp.geometry.length / 1000  # Convert to km
    length_col = 'calculated_length'
    print(f"✓ Calculated length column: {length_col}")
else:
    print(f"✓ Using existing length column: {length_col}")

# Find count column (if exists)
possible_count_cols = ['COUNT', 'count', 'Count', 'rail_count', 'segment_count']
count_col = None

for col in possible_count_cols:
    if col in rails_gdf.columns:
        count_col = col
        break

if count_col is None:
    print("⚠️ No count column found. Will count segments instead.")

# =================================================
# FIND SUBDISTRICT ID COLUMN
# =================================================
possible_id_cols = ['id', 'object_id', 'OBJECTID', 'subdist_id', 'sdtcode']
possible_name_cols = ['name', 'sdtname', 'subdistrict', 'subdist_name']

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
    raise ValueError(f"Could not find ID column. Available: {subdist_gdf.columns.tolist()}")

if name_col is None:
    print("⚠️ No name column found. Will use ID only.")

print(f"✓ Using subdistrict ID column: {id_col}")
if name_col:
    print(f"✓ Using subdistrict name column: {name_col}")

# =================================================
# SPATIAL JOIN
# =================================================
print("\nPerforming spatial join...")

# Match CRS
rails_gdf = rails_gdf.to_crs(subdist_gdf.crs)

# Spatial join: rails within subdistricts
rails_in_subdist = gpd.sjoin(
    rails_gdf,
    subdist_gdf,
    how="left",
    predicate="within"
)

print(f"✓ Spatial join complete")
print(f"✓ Matched {rails_in_subdist[f'{id_col}_right'].notna().sum()} rail segments to subdistricts")

# =================================================
# CALCULATE RAIL STATISTICS PER SUBDISTRICT
# =================================================
print("\nCalculating rail statistics per subdistrict...")

# Prepare aggregation dictionary
agg_dict = {
    length_col: 'sum'  # Total rail length
}

# Add count if column exists
if count_col:
    agg_dict[count_col] = 'sum'

# Group by subdistrict
rail_stats = (
    rails_in_subdist.groupby(f"{id_col}_right")
    .agg(agg_dict)
    .reset_index()
)

# Rename columns
rename_dict = {
    f"{id_col}_right": id_col,
    length_col: 'total_rail_length_km'
}

if count_col:
    rename_dict[count_col] = 'rail_segment_count'
else:
    # Count segments manually
    segment_counts = (
        rails_in_subdist.groupby(f"{id_col}_right")
        .size()
        .reset_index(name='rail_segment_count')
    )
    rail_stats = rail_stats.merge(segment_counts, left_on=f"{id_col}_right", right_on=f"{id_col}_right")
    rename_dict[f"{id_col}_right"] = id_col

rail_stats = rail_stats.rename(columns=rename_dict)

# Merge with subdistrict names if available
if name_col:
    subdist_info = subdist_gdf[[id_col, name_col]].drop_duplicates()
    rail_stats = rail_stats.merge(subdist_info, on=id_col, how='left')
    # Reorder columns
    cols = [id_col, name_col, 'total_rail_length_km', 'rail_segment_count']
    rail_stats = rail_stats[cols]

# Add state column
rail_stats['state'] = state_name

# Round length to 2 decimal places
rail_stats['total_rail_length_km'] = rail_stats['total_rail_length_km'].round(2)

print(f"✓ Calculated rail statistics for {len(rail_stats)} subdistricts")

# =================================================
# MERGE WITH ALL SUBDISTRICTS (INCLUDING ZEROS)
# =================================================
print("\nMerging with all subdistricts...")

# Get all subdistrict IDs
all_subdists = subdist_gdf[[id_col] + ([name_col] if name_col else [])].copy()

# Merge with rail stats (left join to keep all subdistricts)
final_stats = all_subdists.merge(
    rail_stats[[id_col, 'total_rail_length_km', 'rail_segment_count', 'state']],
    on=id_col,
    how='left'
)

# Fill NaN with 0 (subdistricts with no rails)
final_stats['total_rail_length_km'] = final_stats['total_rail_length_km'].fillna(0)
final_stats['rail_segment_count'] = final_stats['rail_segment_count'].fillna(0).astype(int)
final_stats['state'] = final_stats['state'].fillna(state_name)

print(f"✓ Final dataset includes all {len(final_stats)} subdistricts")

# =================================================
# SAVE OUTPUT
# =================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)

output_file = os.path.join(OUTPUT_DIR, f'RailLengths.csv')
final_stats.to_csv(output_file, index=False)

print(f"\nResults saved to: {output_file}")
