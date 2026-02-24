import geopandas as gpd
import rasterstats
import rasterio
import os 
import numpy as np 
import pandas as pd
from pathlib import Path
import glob

# ===== 1. Paths =====
path = Path.cwd() / "Sources" / "NASADEM"
geojson_path = glob.glob(os.path.join(Path.cwd(),"*_subdistricts.geojson"))

sub_gdf = gpd.read_file(geojson_path)

# ===== 2. DEM raster =====
dem_raster = rasterio.open(path / "data" / "NASADEM_DEM_30.tif")
dem_raster_array = dem_raster.read(1)

mean_dicts = rasterstats.zonal_stats(
    sub_gdf.to_crs(dem_raster.crs),
    dem_raster_array,
    affine=dem_raster.transform,
    stats=['mean'],
    nodata=dem_raster.nodata,
    geojson_out=True
)

dfs = [pd.DataFrame([rc['properties']]) for rc in mean_dicts]
dem_zonal_stats_df = pd.concat(dfs).reset_index(drop=True)
dem_zonal_stats_df = dem_zonal_stats_df.rename(columns={'mean': 'elevation_mean'})

# ===== 3. Slope raster =====
slope_raster = rasterio.open(path / "data" / "NASADEM_SLOPE_30.tif")
slope_raster_array = slope_raster.read(1)

mean_dicts = rasterstats.zonal_stats(
    sub_gdf.to_crs(slope_raster.crs),
    slope_raster_array,
    affine=slope_raster.transform,
    stats=['mean'],
    nodata=slope_raster.nodata,
    geojson_out=True
)

dfs = [pd.DataFrame([rc['properties']]) for rc in mean_dicts]
slope_zonal_stats_df = pd.concat(dfs).reset_index(drop=True)
slope_zonal_stats_df = slope_zonal_stats_df.rename(columns={'mean': 'slope_mean'})

# ===== 4. Merge and save =====
zonal_stats_df = pd.merge(
    dem_zonal_stats_df,
    slope_zonal_stats_df[['object_id', 'slope_mean']],
    on='object_id',
    how='left'
)

output_dir = path / "data" / "variables" / "elevation"
output_dir.mkdir(parents=True, exist_ok=True)

zonal_stats_df.to_csv(output_dir / "elevation.csv", index=False)
print(" Zonal statistics saved to:", output_dir / "elevation.csv")
