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
ROADS_FILE = os.path.join(cwd, 'Sources/BHARATMAPS/data/RawData/BharatMaps_RoadLengths.geojson')
OUTPUT_DIR = os.path.join(cwd, 'Sources/BHARATMAPS/data/variables/RoadLengths')

# =================================================
# AUTO-DETECT STATE FROM SUBDISTRICT FILE
# =================================================
print("Searching for subdistrict file...")

# Find all files with '_subdistricts' in the name
subdistrict_files = glob.glob(os.path.join(GEOJSON_DIR, '*_subdistricts.geojson'))

if not subdistrict_files:
    raise FileNotFoundError(f" No subdistrict files found in {GEOJSON_DIR}")

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

# Load roads
roads_gdf = gpd.read_file(ROADS_FILE)
print(f"✓ Loaded {len(roads_gdf)} road segments")

# Load subdistricts
subdist_gdf = gpd.read_file(subdistrict_file)
print(f"✓ Loaded {len(subdist_gdf)} subdistricts for {state_name.upper()}")

# =================================================
# INSPECT AND PREPARE DATA
# =================================================
print("\nInspecting road data columns...")
print(f"Available columns: {roads_gdf.columns.tolist()}")

# Find length column (different naming conventions)
possible_length_cols = ['LENGTH', 'length', 'Length', 'len', 'distance', 'road_length', 'shape_length']
length_col = None

for col in possible_length_cols:
    if col in roads_gdf.columns:
        length_col = col
        break

# If no length column found, calculate from geometry
if length_col is None:
    print("No length column found. Calculating from geometry...")
    # Reproject to projected CRS for accurate length calculation (meters)
    roads_temp = roads_gdf.to_crs(epsg=32644)  # UTM Zone 44N for India
    roads_gdf['calculated_length'] = roads_temp.geometry.length / 1000  # Convert to km
    length_col = 'calculated_length'
    print(f"✓ Calculated length column: {length_col}")
else:
    print(f"✓ Using existing length column: {length_col}")

# =================================================
# FIND SUBDISTRICT ID AND NAME COLUMNS
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

# Align CRS
roads_gdf = roads_gdf.to_crs(subdist_gdf.crs)

# Spatial join: roads within subdistricts
roads_in_subdist = gpd.sjoin(
    roads_gdf,
    subdist_gdf,
    how="left",
    predicate="within"
)

print(f"✓ Spatial join complete")
print(f"✓ Matched {roads_in_subdist[f'{id_col}_right'].notna().sum()} road segments to subdistricts")

# =================================================
# CALCULATE ROAD STATISTICS PER SUBDISTRICT
# =================================================
print("\nCalculating road statistics per subdistrict...")

# Group by subdistrict and sum road lengths
road_stats = (
    roads_in_subdist.groupby(f"{id_col}_right")[length_col]
    .sum()
    .reset_index()
    .rename(columns={
        f"{id_col}_right": id_col,
        length_col: "total_road_length_km"
    })
)

# Count road segments per subdistrict
segment_counts = (
    roads_in_subdist.groupby(f"{id_col}_right")
    .size()
    .reset_index(name='road_segment_count')
    .rename(columns={f"{id_col}_right": id_col})
)

# Merge length and count
road_stats = road_stats.merge(segment_counts, on=id_col, how='left')

# Merge with subdistrict names if available
if name_col:
    subdist_info = subdist_gdf[[id_col, name_col]].drop_duplicates()
    road_stats = road_stats.merge(subdist_info, on=id_col, how='left')
    # Reorder columns
    cols = [id_col, name_col, 'total_road_length_km', 'road_segment_count']
    road_stats = road_stats[cols]

# Add state column
road_stats['state'] = state_name

# Round length to 2 decimal places
road_stats['total_road_length_km'] = road_stats['total_road_length_km'].round(2)

print(f"✓ Calculated road statistics for {len(road_stats)} subdistricts")

# =================================================
# MERGE WITH ALL SUBDISTRICTS (INCLUDING ZEROS)
# =================================================
print("\nMerging with all subdistricts...")

# Get all subdistrict IDs
all_subdists = subdist_gdf[[id_col] + ([name_col] if name_col else [])].copy()

# Merge with road stats (left join to keep all subdistricts)
final_stats = all_subdists.merge(
    road_stats[[id_col, 'total_road_length_km', 'road_segment_count', 'state']],
    on=id_col,
    how='left'
)

# Fill NaN with 0 (subdistricts with no roads)
final_stats['total_road_length_km'] = final_stats['total_road_length_km'].fillna(0)
final_stats['road_segment_count'] = final_stats['road_segment_count'].fillna(0).astype(int)
final_stats['state'] = final_stats['state'].fillna(state_name)

print(f"✓ Final dataset includes all {len(final_stats)} subdistricts")

# =================================================
# SAVE OUTPUT
# =================================================
os.makedirs(OUTPUT_DIR, exist_ok=True)

output_file = os.path.join(OUTPUT_DIR, f'road_lengths_{state_name}.csv')
final_stats.to_csv(output_file, index=False)

print(f"\nResults saved to: {output_file}")

