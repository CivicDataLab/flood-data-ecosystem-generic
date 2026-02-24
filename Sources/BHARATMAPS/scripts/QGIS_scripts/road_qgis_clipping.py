import os
import json
import urllib.request
import urllib.parse
import time
import traceback
from qgis.core import QgsProject,QgsVectorLayer,QgsVectorFileWriter
import processing

# ---------------------------------------------------------
# 1. Ask user for boundary file (GeoJSON or SHP) in your repo
# ---------------------------------------------------------
boundary_path = input("\nEnter the absolute path of the GeoJSON boundary file: ").strip() #input your absoluete boundary path

if not os.path.exists(boundary_path):
    raise Exception(f"File not found: {boundary_path}")

print(f"✔ Using boundary file: {boundary_path}")

boundary_layer = QgsVectorLayer(boundary_path, "boundary", "ogr")
if not boundary_layer.isValid():
    raise Exception("Could not load boundary layer.")

QgsProject.instance().addMapLayer(boundary_layer)

target_crs = boundary_layer.crs()

# ---------------------------------------------------------
# 2. Load road layers from Bharat Maps 2024 (admin2024)
#    Road and Rail group:
#    National Highway (16), State Highway (17), Major Road (18)
# ---------------------------------------------------------
base_url = "https://webgis1.nic.in/nicstreet/rest/services/admin2024/MapServer"

def load_road_layer(layer_id: int, name: str) -> QgsVectorLayer:
    uri = f"url={base_url}/{layer_id}?f=json&crs=EPSG:4326"
    lyr = QgsVectorLayer(uri, name, "arcgisfeatureserver")
    if not lyr.isValid():
        raise Exception(f"Could not load layer {name} (id {layer_id}).")
    QgsProject.instance().addMapLayer(lyr)
    return lyr

national = load_road_layer(16, "National_Highway")
state    = load_road_layer(17, "State_Highway")
major    = load_road_layer(18, "Major_Road")
corridor = load_road_layer(15, "GQ NS EW corridors")

# ---------------------------------------------------------
# 3. Reproject each road layer to boundary CRS (if needed)
# ---------------------------------------------------------
def ensure_crs(layer: QgsVectorLayer, crs) -> QgsVectorLayer:
    if layer.crs() == crs:
        return layer
    res = processing.run(
        "native:reprojectlayer",
        {
            "INPUT": layer,
            "TARGET_CRS": crs,
            "OUTPUT": "memory:"
        }
    )
    return res["OUTPUT"]

national_fix = ensure_crs(national, target_crs)
state_fix    = ensure_crs(state, target_crs)
major_fix    = ensure_crs(major, target_crs)
corridor_fix = ensure_crs(major, target_crs)

# ---------------------------------------------------------
# 4. Merge the four  road layers
# ---------------------------------------------------------
merge_result = processing.run(
    "native:mergevectorlayers",
    {
        "LAYERS": [national_fix, state_fix, major_fix, corridor_fix],
        "CRS": target_crs,
        "OUTPUT": "memory:"
    }
)
merged_roads = merge_result["OUTPUT"]

# ---------------------------------------------------------
# 5. Clip merged roads by boundary
# ---------------------------------------------------------
clip_result = processing.run(
    "native:clip",
    {
        "INPUT": merged_roads,
        "OVERLAY": boundary_layer,
        "OUTPUT": "memory:"
    }
)
clipped_roads = clip_result["OUTPUT"]

# ---------------------------------------------------------
# 6. Save as GeoJSON in same folder as boundary
# ---------------------------------------------------------
output_dir = os.path.dirname(boundary_path) #move the file into the raw data section of the bharatmaps 
output_geojson = os.path.join(output_dir, "BharatMaps_RoadLengths.geojson") 

context = QgsProject.instance().transformContext()

err, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
    clipped_roads,
    output_geojson,
    context,
    target_crs,
    driverName="GeoJSON"
)

if err != QgsVectorFileWriter.NoError:
    print("Problem saving GeoJSON.")
else:
    print(" Done! Merged & clipped road layer saved as:")
    print(output_geojson)
