# Paste this into QGIS Python Console (Editor) and Run or create a qgis environment and run the code 
import os
import json
import urllib.request
import urllib.parse
import time
import traceback
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsVectorFileWriter, QgsField,
    QgsFeature, QgsGeometry, QgsFields, QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant
import processing

def download_featurelayer_geojson_paged(base_layer_url, batch_size=1000, timeout=60):
    """Download features from an ArcGIS Feature/MapServer layer using paged requests, return FeatureCollection dict."""
    offset = 0
    all_feats = []
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "outSR": "4326",
            "resultOffset": str(offset),
            "resultRecordCount": str(batch_size)
        }
        url = base_layer_url + "/query?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            geo = json.loads(data)
        feats = geo.get("features") or []
        all_feats.extend(feats)
        print(f"  downloaded {len(feats)} features (offset {offset})")
        if len(feats) < batch_size:
            break
        offset += batch_size
        time.sleep(0.15)
    return {"type": "FeatureCollection", "features": all_feats}

try:
    # ---------- USER INPUT ----------
    boundary_path = input("\nEnter the absolute path of the GeoJSON boundary file: ").strip() # -> the absolute path of the geojson file 
    if not os.path.exists(boundary_path):
        raise FileNotFoundError(f"Boundary not found: {boundary_path}")
    out_dir = os.path.dirname(boundary_path)
    print("✔ Boundary:", boundary_path)

    # ---------- Load boundary ----------
    boundary_layer = QgsVectorLayer(boundary_path, "boundary", "ogr")
    if not boundary_layer.isValid():
        raise RuntimeError("Could not load boundary layer.")
    QgsProject.instance().addMapLayer(boundary_layer)
    target_crs = boundary_layer.crs()

    # ---------- Attempt to load railway via ArcGIS provider ----------
    base_url = "https://webgis1.nic.in/nicstreet/rest/services/admin2024/MapServer"
    railway_id = 20  # adjust if needed
    provider_uri = f"url={base_url}/{railway_id}?f=json&crs=EPSG:4326"
    railway_layer = QgsVectorLayer(provider_uri, "Railway_remote", "arcgisfeatureserver")

    if railway_layer.isValid():
        print("✔ Loaded railway via arcgisfeatureserver provider")
        QgsProject.instance().addMapLayer(railway_layer)
        rail_src = railway_layer
    else:
        print("⚠ arcgisfeatureserver provider failed — falling back to paged HTTP download")
        # Download GeoJSON paged
        fc = download_featurelayer_geojson_paged(base_url + f"/{railway_id}")
        raw_path = os.path.join(out_dir, "railway_raw_download.geojson")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(fc, f)
        print("✔ Saved raw railway GeoJSON to", raw_path)
        rail_src = QgsVectorLayer(raw_path, "Railway_raw", "ogr")
        if not rail_src.isValid():
            raise RuntimeError("Downloaded railway GeoJSON could not be loaded by OGR.")

        QgsProject.instance().addMapLayer(rail_src)

    # ---------- Reproject railway to match boundary CRS if needed ----------
    if rail_src.crs() != target_crs:
        print(f"Reprojecting railway from {rail_src.crs().authid()} to {target_crs.authid()}")
        reproj_res = processing.run(
            "native:reprojectlayer",
            {"INPUT": rail_src, "TARGET_CRS": target_crs.toWkt(), "OUTPUT": "memory:"}
        )
        railway_fixed = reproj_res["OUTPUT"]
    else:
        railway_fixed = rail_src

    QgsProject.instance().addMapLayer(railway_fixed)

    # ---------- Clip railway by boundary ----------
    clip_res = processing.run(
        "native:clip",
        {"INPUT": railway_fixed, "OVERLAY": boundary_layer, "OUTPUT": "memory:"}
    )
    railway_clipped = clip_res["OUTPUT"]
    QgsProject.instance().addMapLayer(railway_clipped)
    print("✔ Clipped railway features:", railway_clipped.featureCount())

    # ---------- Prepare fields for lengths ----------
    provider = railway_clipped.dataProvider()
    fld_names = [f.name() for f in railway_clipped.fields()]
    if "len_km" not in fld_names:
        provider.addAttributes([QgsField("len_km", QVariant.Double)])
    if "total_km" not in fld_names:
        provider.addAttributes([QgsField("total_km", QVariant.Double)])
    railway_clipped.updateFields()

    idx_len = railway_clipped.fields().indexFromName("len_km")
    idx_tot = railway_clipped.fields().indexFromName("total_km")

    # ---------- Compute lengths in a metric CRS (EPSG:3857) ----------
    # Reproject clipped to EPSG:3857 for accurate meter lengths
    meas_crs = QgsCoordinateReferenceSystem("EPSG:3857")
    meas_reproj = processing.run(
        "native:reprojectlayer",
        {"INPUT": railway_clipped, "TARGET_CRS": meas_crs.toWkt(), "OUTPUT": "memory:"}
    )["OUTPUT"]
    total_m = 0.0

    railway_clipped.startEditing()
    # iterate by feature id mapping to ensure correspondence
    meas_features = {f.id(): f for f in meas_reproj.getFeatures()}
    for feat in railway_clipped.getFeatures():
        fid = feat.id()
        mf = meas_features.get(fid)
        if mf is None:
            # fallback: try matching by geometry WKT (slower)
            geom = feat.geometry()
            # set length zero if not found
            length_m = 0.0
        else:
            length_m = mf.geometry().length()
        total_m += length_m
        # update feature length
        feat[idx_len] = (length_m / 1000.0) if length_m is not None else None
        railway_clipped.updateFeature(feat)

    total_km = total_m / 1000.0

    # write total_km to all features
    for feat in railway_clipped.getFeatures():
        feat[idx_tot] = total_km
        railway_clipped.updateFeature(feat)

    railway_clipped.commitChanges()

    print(f"✔ Total railway length inside boundary: {total_km:.3f} km")

    # ---------- Save as GeoJSON ----------
    out_file = os.path.join(out_dir, "BharatMaps_RailLengths.geojson")
    ctx = QgsProject.instance().transformContext()
    err, err_msg, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        railway_clipped, out_file, ctx, target_crs, driverName="GeoJSON"
    )
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Error saving output: {err_msg} (code {err})")
    print("🎉 Saved output to:", out_file)

except Exception as e:
    print("Script failed:")
    print(str(e))
    traceback.print_exc()
