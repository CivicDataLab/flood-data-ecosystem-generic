import ee
import geemap
import geopandas as gpd
import os
import time
import glob
import sys

# ===== CONFIG =====
SERVICE_ACCOUNT = input("enter your service account name :  ")
KEY_PATH = input("enter the path to your json key:  ")
PROJECT = input("enter your project name :  ")
GCS_BUCKET = input("enter your GCS bucket name:  ")  # ensure this exists and SA has Storage Object Admin
GCS_PREFIX = input("enter your GCS bucket prefix:  ")           # folder-like prefix inside the bucket
GEOJSON_FILE = glob.glob(os.path.join(os.getcwd(), "*_subdistricts.geojson"))
if not GEOJSON_FILE:
    print("Error: File not found ")
    sys.exit(1)
sub_gdf = gpd.read_file(GEOJSON_FILE)


SCALE = 30
MAXPIX = 1e13

# 1. Initialize EE 
credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_PATH)
ee.Initialize(credentials, project=PROJECT)
print("Earth Engine initialized for project:", PROJECT)

# 2. Load  shapefile 
if sub_gdf.crs is None or sub_gdf.crs.to_epsg() != 4326:
   sub_gdf = sub_gdf.to_crs(4326)
# dissolve to single geometry and simplify a bit (reduces export request size)
sub_gdf = sub_gdf.dissolve().reset_index(drop=True)
print(" Loaded and dissolved UP shapefile")

#  3. Convert to EE geometry 
up_fc = geemap.geopandas_to_ee(sub_gdf)
geom_union = up_fc.geometry()                     
geom_simple = geom_union.simplify(maxError=100)   
region_rect = geom_union.bounds()                 # use bounds as region to keep payload small
region_coords = region_rect.getInfo()['coordinates']
print("Converted to EE geometry (union + simplified)")

# ===== 4. Prepare images =====
nasadem = ee.Image('NASA/NASADEM_HGT/001').select('elevation')
elevation = nasadem.clip(geom_union)  # clip with full geometry so mask is correct
slope = ee.Terrain.slope(nasadem).clip(geom_union)
print("NASADEM elevation and slope ready")

# ===== 5. Export to Cloud Storage =====
try:
    dem_task = ee.batch.Export.image.toCloudStorage(
        image=elevation,
        description='NASADEM_DEM_30',
        bucket=GCS_BUCKET,
        fileNamePrefix=f'{GCS_PREFIX}/NASADEM_DEM_30',
        region=region_coords,
        scale=SCALE,
        maxPixels=MAXPIX,
        fileFormat='GeoTIFF'
    )
    dem_task.start()
    print(f"DEM export started. Task ID: {dem_task.id}")
except Exception as e:
    print("Failed to start DEM export:", e)

try:
    slope_task = ee.batch.Export.image.toCloudStorage(
        image=slope,
        description='NASADEM_SLOPE_30',
        bucket=GCS_BUCKET,
        fileNamePrefix=f'{GCS_PREFIX}/NASADEM_SLOPE_30',
        region=region_coords,
        scale=SCALE,
        maxPixels=MAXPIX,
        fileFormat='GeoTIFF'
    )
    slope_task.start()
    print(f"Slope export started. Task ID: {slope_task.id}")
except Exception as e:
    print("Failed to start slope export:", e)

# ===== 6. Small helper: how to monitor tasks =====
print("\n Monitor tasks with:")
print("""
import ee
ee.Initialize(ee.ServiceAccountCredentials('{}', '{}'), project='{}')
for t in ee.data.getTaskList():
    print(t['id'], t['metadata'].get('description'), t['metadata'].get('state'))
""".format(SERVICE_ACCOUNT, KEY_PATH, PROJECT))

print("\nExports submitted. When tasks show COMPLETED, files will be in:")
print(f"  gs://{GCS_BUCKET}/{GCS_PREFIX}/")
