#!/usr/bin/env python3
"""
Download NIC admin2024 boundaries for a given state and export as GeoJSON:
- state.geojson
- state_districts.geojson
- states_subdistricts.geojson
- states_villages.geojson

Source service:
https://webgis1.nic.in/nicstreet/rest/services/admin2024/MapServer/
Layers:
- State Boundary: 9  (field: stname)
- District boundary: 10
- Subdistrict boundary: 11
- Village boundary: 12
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

try:
    import geopandas as gpd
except ImportError as e:
    raise SystemExit("Missing dependency: geopandas. Install with: pip install geopandas") from e


# ============================================
# CONFIGURATION - EDIT THESE VALUES
# ============================================
STATE_NAME = input("enter your state name :  ") 
base_dir = os.getcwd()
OUTPUT_DIR = os.path.join(base_dir,"/Maps/Geojson")
# ============================================


BASE_URL = "https://webgis1.nic.in/nicstreet/rest/services/admin2024/MapServer"

STATE_LAYER = 9
DISTRICT_LAYER = 10
SUBDISTRICT_LAYER = 11
VILLAGE_LAYER = 12 

MAX_RECORD_COUNT = 2000  # service maxRecordCount is 2000


def _escape_sql_string(s: str) -> str:
    # ArcGIS REST uses SQL-like where clauses; escape single quotes
    return s.replace("'", "''")


def arcgis_query_geojson(
    layer_id: int,
    where: str = "1=1",
    geometry: Optional[str] = None,
    geometry_type: Optional[str] = None,
    spatial_rel: str = "esriSpatialRelIntersects",
    in_sr: int = 4326,
    out_sr: int = 4326,
    out_fields: str = "*",
    return_geometry: bool = True,
    timeout: int = 60,
    sleep_s: float = 0.1,
) -> Dict[str, Any]:
    """
    Query an ArcGIS REST layer and return GeoJSON FeatureCollection.
    Uses pagination (resultOffset/resultRecordCount).
    """
    url = f"{BASE_URL}/{layer_id}/query"
    session = requests.Session()

    all_features: List[Dict[str, Any]] = []
    offset = 0

    while True:
        data = {
            "f": "geojson",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "outSR": str(out_sr),
            "resultOffset": str(offset),
            "resultRecordCount": str(MAX_RECORD_COUNT),
        }

        if geometry is not None and geometry_type is not None:
            data.update(
                {
                    "geometry": geometry,
                    "geometryType": geometry_type,
                    "spatialRel": spatial_rel,
                    "inSR": str(in_sr),
                }
            )

        # POST avoids URL-length issues and is generally safer for complex queries
        resp = session.post(url, data=data, timeout=timeout)
        resp.raise_for_status()

        try:
            fc = resp.json()
        except json.JSONDecodeError:
            raise RuntimeError(f"Non-JSON response from server for layer {layer_id}: {resp.text[:500]}")

        if "error" in fc:
            raise RuntimeError(f"ArcGIS error for layer {layer_id}: {fc['error']}")

        features = fc.get("features", [])
        all_features.extend(features)

        # If fewer than max, we're done
        if len(features) < MAX_RECORD_COUNT:
            break

        offset += MAX_RECORD_COUNT
        time.sleep(sleep_s)

    # Return a FeatureCollection-like dict
    return {"type": "FeatureCollection", "features": all_features}


def fetch_distinct_state_names(timeout: int = 60) -> List[str]:
    """
    Fetch distinct state names from layer 9 (stname).
    """
    url = f"{BASE_URL}/{STATE_LAYER}/query"
    resp = requests.post(
        url,
        data={
            "f": "json",
            "where": "1=1",
            "outFields": "stname",
            "returnDistinctValues": "true",
            "returnGeometry": "false",
            "outSR": "4326",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS error fetching distinct state names: {data['error']}")
    names = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes", {})
        if "stname" in attrs and attrs["stname"]:
            names.append(str(attrs["stname"]))
    return sorted(set(names))


def main() -> int:
    # Use hardcoded values from configuration section
    state_input = STATE_NAME.strip()
    outdir = os.path.abspath(OUTPUT_DIR)
    
    # Create output directory if it doesn't exist
    os.makedirs(outdir, exist_ok=True)
    
    print(f"Downloading boundaries for: {state_input}")
    print(f"Output directory: {outdir}")
    print("-" * 50)

    if not state_input:
        print("ERROR: State name cannot be empty. Please edit STATE_NAME in the script.", file=sys.stderr)
        return 2

    # 1) Fetch the state polygon from layer 9 using stname
    print("Fetching state boundary...")
    state_sql = f"UPPER(stname)=UPPER('{_escape_sql_string(state_input)}')"
    state_fc = arcgis_query_geojson(STATE_LAYER, where=state_sql)

    if not state_fc["features"]:
        # Helpful fallback: list valid names
        print(f'ERROR: No match for state="{state_input}"', file=sys.stderr)
        try:
            valid = fetch_distinct_state_names()
            print("Valid state names include:", file=sys.stderr)
            for name in valid:
                print(f"  - {name}", file=sys.stderr)
        except Exception:
            print("Also failed to fetch valid state names.", file=sys.stderr)
        return 1

    gdf_state = gpd.GeoDataFrame.from_features(state_fc, crs="EPSG:4326")
    # If multiple (shouldn't happen), dissolve into one
    state_geom = gdf_state.unary_union
    gdf_state = gpd.GeoDataFrame(gdf_state.drop(columns="geometry", errors="ignore"), geometry=[state_geom], crs="EPSG:4326")

    # Export state
    state_name_lower = state_input.lower().replace(" ", "_")
    state_path = os.path.join(outdir, f"{state_name_lower}_state.geojson")
    gdf_state.to_file(state_path, driver="GeoJSON")
    print(f"✓ Saved: {state_path}")

    # 2) Use state bbox to query districts/subdistricts/villages
    minx, miny, maxx, maxy = gdf_state.total_bounds
    bbox_str = f"{minx},{miny},{maxx},{maxy}"

    # Districts
    print("Fetching districts...")
    dist_fc = arcgis_query_geojson(
        DISTRICT_LAYER,
        where="1=1",
        geometry=bbox_str,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,
    )
    gdf_dist = gpd.GeoDataFrame.from_features(dist_fc, crs="EPSG:4326")
    if not gdf_dist.empty:
        gdf_dist = gpd.clip(gdf_dist, gdf_state)
    dist_path = os.path.join(outdir, f"{state_name_lower}_districts.geojson")
    gdf_dist.to_file(dist_path, driver="GeoJSON")
    print(f"✓ Saved: {dist_path}")

    # Subdistricts
    print("Fetching subdistricts...")
    subdist_fc = arcgis_query_geojson(
        SUBDISTRICT_LAYER,
        where="1=1",
        geometry=bbox_str,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,
    )
    gdf_subdist = gpd.GeoDataFrame.from_features(subdist_fc, crs="EPSG:4326")
    if not gdf_subdist.empty:
        gdf_subdist = gpd.clip(gdf_subdist, gdf_state)
    subdist_path = os.path.join(outdir, f"{state_name_lower}_subdistricts.geojson")
    gdf_subdist.to_file(subdist_path, driver="GeoJSON")
    print(f"✓ Saved: {subdist_path}")

    # Villages
    print("Fetching villages (this may take a while)...")
    vil_fc = arcgis_query_geojson(
        VILLAGE_LAYER,
        where="1=1",
        geometry=bbox_str,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,      
    )
    gdf_vil = gpd.GeoDataFrame.from_features(vil_fc, crs="EPSG:4326")
    if not gdf_vil.empty:
        gdf_vil = gpd.clip(gdf_vil, gdf_state)
    vil_path = os.path.join(outdir, f"{state_name_lower}_villages.geojson")
    gdf_vil.to_file(vil_path, driver="GeoJSON")
    print(f"✓ Saved: {vil_path}")

    print("-" * 50)
    print("SUCCESS! All files downloaded:")
    print(f"  - {state_path}")
    print(f"  - {dist_path}")
    print(f"  - {subdist_path}")
    print(f"  - {vil_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())