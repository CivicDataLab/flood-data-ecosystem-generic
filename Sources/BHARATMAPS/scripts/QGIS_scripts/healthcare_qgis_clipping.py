# Paste this into QGIS Python Console (Editor) and Run or create a qgis environment and run the code 
import os
import json
import urllib.request
import urllib.parse
import time
import traceback
from qgis.core import QgsVectorLayer, QgsProject, QgsVectorFileWriter, QgsCoordinateReferenceSystem
import processing

try:
    # =================================================
    # USER INPUT
    # =================================================
    print("="*60)
    print("ESRI Healthcare Facilities Downloader & Clipper")
    print("="*60)
    
    # Get boundary path from user
    boundary_path = input("\nEnter the absolute path of the GeoJSON boundary file: ").strip()
    
    # Remove quotes if user copied path with quotes
    boundary_path = boundary_path.strip('"').strip("'")
    
    if not os.path.exists(boundary_path):
        raise FileNotFoundError(f"Boundary file not found: {boundary_path}")
    
    # Validate it's a GeoJSON file
    if not boundary_path.lower().endswith('.geojson'):
        raise ValueError(f"File must be a GeoJSON file. Got: {os.path.basename(boundary_path)}")
    
    out_dir = os.path.dirname(boundary_path)
    print(f"✓ Boundary path: {boundary_path}")
    print(f"✓ Output directory: {out_dir}")

    # =================================================
    # DOWNLOAD FROM ESRI REST SERVICE
    # =================================================
    print("\n" + "-"*60)
    print("Downloading healthcare facilities from ESRI Living Atlas...")
    print("-"*60)
    
    rest_base = "https://livingatlas.esri.in/server1/rest/services/Health/IN_HealthcareFacility/MapServer/0"
    batch_size = 1000
    offset = 0
    all_features = []
    
    print(f"→ Fetching in batches of {batch_size}...")

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
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP error {e.code} at offset {offset}: {e.reason}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error at offset {offset}: {e.reason}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response at offset {offset}: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to download page at offset {offset}: {e}")

        # Check for service errors
        if "error" in geo:
            raise RuntimeError(f"Service error: {geo['error']}")

        features = geo.get("features", [])
        n = len(features)
        
        if n > 0:
            print(f"Fetched {n} features (offset {offset}, total so far: {len(all_features) + n})")
            all_features.extend(features)
        else:
            print(f" No more features (stopped at offset {offset})")
            break

        # If fewer than batch_size returned, we've got everything
        if n < batch_size:
            break

        offset += batch_size
        time.sleep(0.2)  # Polite pause to avoid overwhelming the server

    if len(all_features) == 0:
        raise RuntimeError("No features downloaded from service. The service may be empty or unavailable.")

    print(f"\n✓ Total healthcare facilities downloaded: {len(all_features)}")

    # =================================================
    # SAVE RAW GEOJSON
    # =================================================
    print("\n" + "-"*60)
    print("Saving raw GeoJSON...")
    print("-"*60)
    
    # Build combined FeatureCollection
    combined = {
        "type": "FeatureCollection",
        "features": all_features
    }

    raw_out = os.path.join(out_dir, "health_facilities_raw.geojson")
    
    try:
        with open(raw_out, "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False, indent=2)
        print(f"✓ Saved raw health GeoJSON to: {raw_out}")
    except Exception as e:
        raise RuntimeError(f"Failed to save raw GeoJSON: {e}")

    # =================================================
    # LOAD RAW LAYER INTO QGIS
    # =================================================
    print("\n" + "-"*60)
    print("Loading layers into QGIS...")
    print("-"*60)
    
    raw_layer = QgsVectorLayer(raw_out, "health_facilities_raw", "ogr")
    if not raw_layer.isValid():
        raise RuntimeError(f"Could not load raw GeoJSON as valid layer: {raw_out}")
    
    QgsProject.instance().addMapLayer(raw_layer)
    print(f"✓ Raw health layer loaded: {raw_layer.featureCount()} features")

    # =================================================
    # LOAD BOUNDARY LAYER
    # =================================================
    boundary_layer = QgsVectorLayer(boundary_path, "boundary", "ogr")
    if not boundary_layer.isValid():
        raise RuntimeError(f"Could not load boundary layer: {boundary_path}")
    
    QgsProject.instance().addMapLayer(boundary_layer)
    print(f"✓ Boundary layer loaded: {boundary_layer.featureCount()} features")
    print(f"  CRS: {boundary_layer.crs().authid()}")

    # =================================================
    # ENSURE CRS COMPATIBILITY
    # =================================================
    if raw_layer.crs().authid() != boundary_layer.crs().authid():
        print(f"\n⚠️ CRS mismatch detected:")
        print(f"  Health layer: {raw_layer.crs().authid()}")
        print(f"  Boundary layer: {boundary_layer.crs().authid()}")
        print(f"  → QGIS will handle reprojection during clip")

    # =================================================
    # CLIP OPERATION
    # =================================================
    print("\n" + "-"*60)
    print("Running clip operation...")
    print("-"*60)
    
    try:
        clip_result = processing.run(
            "native:clip",
            {
                "INPUT": raw_layer,
                "OVERLAY": boundary_layer,
                "OUTPUT": "memory:"
            }
        )
        clipped = clip_result["OUTPUT"]
    except Exception as e:
        raise RuntimeError(f"Clip operation failed: {e}")

    if clipped.featureCount() == 0:
        print("\n⚠️ WARNING: Clip operation resulted in 0 features!")
        print("   Possible reasons:")
        print("   - Boundary and health facilities don't overlap")
        print("   - CRS mismatch (though QGIS should handle this)")
        print("   - Invalid geometries")
        print("\n   Saving anyway for inspection...")
    else:
        print(f"✓ Clipped layer created: {clipped.featureCount()} features")
    
    QgsProject.instance().addMapLayer(clipped)
    clipped.setName("health_facilities_clipped")

    # =================================================
    # SAVE CLIPPED OUTPUT
    # =================================================
    print("\n" + "-"*60)
    print("Saving clipped output...")
    print("-"*60)
    
    clipped_out = os.path.join(out_dir, "BharatMaps_HealthCenters.geojson")
    
    # Use writeAsVectorFormatV3 for better compatibility
    context = QgsProject.instance().transformContext()
    
    save_options = QgsVectorFileWriter.SaveVectorOptions()
    save_options.driverName = "GeoJSON"
    save_options.fileEncoding = "UTF-8"
    
    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        clipped,
        clipped_out,
        context,
        save_options
    )
    
    if error[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Failed to save clipped output: {error[1]} (error code: {error[0]})")
    
    print(f"✓ Clipped healthcare facilities saved to:") #save it to rawdata foler in bharatmaps foler 
    print(f"  {clipped_out}")
    
    