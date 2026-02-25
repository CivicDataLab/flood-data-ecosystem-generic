# Paste into QGIS Python Console (Editor) and Run
import os
import json
import urllib.request
import urllib.parse
import time
import traceback
from qgis.core import  QgsProject, QgsVectorLayer,QgsVectorFileWriter
import processing

try:
    # ----------------- USER INPUT -----------------
    boundary_path = input("\nEnter the absolute path of the GeoJSON boundary file: ").strip() # -> enter the absolute boundary path
    if not os.path.exists(boundary_path):
        raise FileNotFoundError(f"Boundary not found: {boundary_path}")
    out_dir = os.path.dirname(boundary_path)
    print("✔ Boundary path:", boundary_path)

    # ----------------- REST endpoint (schools layer 0) -----------------
    rest_base = "https://webgis1.nic.in/nicstreet/rest/services/school/location/MapServer/0"
    batch_size = 1000
    offset = 0
    all_features = []
    print("→ Downloading school features in pages...")

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "outSR": "4326",
            "resultOffset": str(offset),
            "resultRecordCount": str(batch_size)
        }
        query_url = rest_base + "/query?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(query_url, timeout=60) as resp:
                data = resp.read().decode("utf-8")
                geo = json.loads(data)
        except Exception as e:
            raise RuntimeError(f"Failed to download page at offset {offset}: {e}")

        feats = geo.get("features") or []
        n = len(feats)
        print(f"  Fetched {n} features (offset {offset})")
        if n == 0:
            break

        all_features.extend(feats)
        if n < batch_size:
            break
        offset += batch_size
        time.sleep(0.2)  # polite pause

    if len(all_features) == 0:
        raise RuntimeError("No features downloaded from service.")

    # ----------------- Save raw GeoJSON to disk -----------------
    raw_out = os.path.join(out_dir, "schools_raw.geojson")
    combined = {"type": "FeatureCollection", "features": all_features}
    with open(raw_out, "w", encoding="utf-8") as f:
        json.dump(combined, f)
    print("✔ Saved raw schools GeoJSON to:", raw_out)

    # ----------------- Load raw as layer -----------------
    raw_layer = QgsVectorLayer(raw_out, "schools_raw", "ogr")
    if not raw_layer.isValid():
        raise RuntimeError("Loaded raw GeoJSON is invalid.")
    QgsProject.instance().addMapLayer(raw_layer)
    print("✔ Raw schools layer loaded into QGIS as 'schools_raw'")

    # ----------------- Load boundary -----------------
    boundary_layer = QgsVectorLayer(boundary_path, "boundary", "ogr")
    if not boundary_layer.isValid():
        raise RuntimeError("Could not load boundary layer.")
    QgsProject.instance().addMapLayer(boundary_layer)
    print("✔ Boundary layer loaded into QGIS as 'boundary'")

    # ----------------- Reproject raw layer to match boundary CRS (if needed) -----------------
    target_crs = boundary_layer.crs()
    if raw_layer.crs() != target_crs:
        print(f"Reprojecting raw layer from {raw_layer.crs().authid()} to {target_crs.authid()}")
        reproj = processing.run(
            "native:reprojectlayer",
            {
                "INPUT": raw_layer,
                "TARGET_CRS": target_crs.toWkt(),
                "OUTPUT": "memory:"
            }
        )
        raw_fixed = reproj["OUTPUT"]
        QgsProject.instance().addMapLayer(raw_fixed)
    else:
        raw_fixed = raw_layer

    # ----------------- Clip schools by user boundary -----------------
    print("→ Running clip operation...")
    clip_result = processing.run(
        "native:clip",
        {
            "INPUT": raw_fixed,
            "OVERLAY": boundary_layer,
            "OUTPUT": "memory:"
        }
    )
    clipped = clip_result["OUTPUT"]
    QgsProject.instance().addMapLayer(clipped)
    print("✔ Clipped layer added to project (in-memory)")

    # ----------------- Save clipped output -----------------
    clipped_out = os.path.join(out_dir, "schools_clipped.geojson") # move the save geojson tot he raw data section in the repo
    context = QgsProject.instance().transformContext()
    err, err_msg, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        clipped,
        clipped_out,
        context,
        target_crs,
        driverName="GeoJSON"
    )
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Problem saving clipped output: {err_msg} (err code {err})")
    print("🎉 SUCCESS! Clipped schools saved at:")
    print("   ", clipped_out)

except Exception as e:
    print("Script failed:")
    print(str(e))
    traceback.print_exc()
