import glob
import os
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterstats

# Validate command-line arguments
if len(sys.argv) < 3:
    print("Usage: python script.py <year> <month>")
    sys.exit(1)

year = str(sys.argv[1])
month = str(sys.argv[2])
print(f"Processing: {year}-{month}")

tic = time.perf_counter()
path = os.getcwd() + "/Sources/BHUVAN/"

# Load geodata
geojson_files = glob.glob(os.path.join(os.getcwd() + "/Maps/Geojson/*_subdistrict"))
if not geojson_files:
    print("Error: No subdistrict GeoJSON files found!")
    sys.exit(1)
assam_rc_gdf = gpd.read_file(geojson_files[0])

# Find all matching TIFF files
files1 = glob.glob(path + "data/tiffs/removed_watermarks/" + year + "_??_" + month + "*.tif")
files2 = glob.glob(path + "data/tiffs/removed_watermarks/" + year + "_??-??_" + month + "*.tif")
files = files1 + files2

if not files:
    print(f"Error: No files found for {year}-{month}")
    sys.exit(1)

print(f"Number of maps available for the month: {len(files)}")

# Read first raster
with rasterio.open(files[0]) as raster:
    raster_array = raster.read(1).astype(np.int32)  # Changed to int32 to prevent overflow
    meta = raster.meta.copy()
    transform = raster.transform
    crs = raster.crs

# Accumulate remaining rasters
for file in files[1:]:
    with rasterio.open(file) as src:
        arr = src.read(1).astype(np.int32)
        raster_array += arr

# Update metadata for output
meta.update({
    "compress": "deflate",
    "count": 1,
    "dtype": "int32",  # Match the array dtype
    "nodata": -1,
})

# Save stitched raster (SINGLE WRITE)
output_path = path + f"data/tiffs/stitched_monthly/stitched_{year}_{month}.tif"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with rasterio.open(output_path, "w", **meta) as dst:
    dst.write(raster_array, 1)

# CALCULATE ZONAL STATISTICS
def count_nonzero(x):
    return np.count_nonzero(x.compressed())

mean_dicts = rasterstats.zonal_stats(
    assam_rc_gdf.to_crs(crs),
    raster_array,
    affine=transform,
    stats=["count"],
    nodata=-1,
    add_stats={"count_nonzero": count_nonzero},
    geojson_out=True,
)

dfs = []
for rc in mean_dicts:
    dfs.append(pd.DataFrame([rc["properties"]]))

zonal_stats_df = pd.concat(dfs).reset_index(drop=True)
zonal_stats_df["inundation_pct"] = (
    zonal_stats_df["count_nonzero"] / zonal_stats_df["count"]
)

# CALCULATE INTENSITY
intensity_array = np.divide(raster_array, raster_array.max())

def nonzero_mean(x):
    x = x.compressed()
    nonzero_values = x[x != 0]
    return np.mean(nonzero_values) if len(nonzero_values) > 0 else 0

mean_dicts = rasterstats.zonal_stats(
    assam_rc_gdf.to_crs(crs),
    intensity_array,
    affine=transform,
    stats=["mean", "sum"],
    nodata=-1,
    add_stats={"intensity_mean_nonzero": nonzero_mean},
    geojson_out=True,
)

dfs = []
for rc in mean_dicts:
    dfs.append(pd.DataFrame([rc["properties"]]))

intensity_df = pd.concat(dfs).reset_index(drop=True)
intensity_df.rename(
    columns={"mean": "intensity_mean", "sum": "intensity_sum"}, inplace=True
)

zonal_stats_df = pd.merge(
    zonal_stats_df,
    intensity_df[["intensity_mean", "intensity_mean_nonzero", "intensity_sum", "object_id"]],
    on="object_id",
)

zonal_stats_df = zonal_stats_df[[
    "object_id",
    "count",
    "count_nonzero",
    "inundation_pct",
    "intensity_mean",
    "intensity_mean_nonzero",
    "intensity_sum",
]]

zonal_stats_df.columns = [
    "object_id",
    "count_bhuvan_pixels",
    "count_inundated_pixels",
    "inundation_pct",
    "inundation_intensity_mean",
    "inundation_intensity_mean_nonzero",
    "inundation_intensity_sum",
]

# Save results
output_dir = path + "data/variables/inundation_pct"
os.makedirs(output_dir, exist_ok=True)

zonal_stats_df.to_csv(
    f"{output_dir}/inundation_pct_{year}_{month}.csv",
    index=False,
)

toc = time.perf_counter()
print(f"Time Taken: {toc - tic:.2f} seconds")