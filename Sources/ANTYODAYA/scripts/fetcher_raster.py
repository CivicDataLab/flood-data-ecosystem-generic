"""
worldpop_state_raster_batch.py
-------------------------------
Downloads the WorldPop India population raster directly from
data.worldpop.org and clips it to each state boundary GeoJSON.

Run from project root:
    python Sources/ANTYODAYA/scripts/worldpop_state_raster_batch.py

Python 3.8+ | Dependencies: geopandas, rasterio, requests

Memory/payload handling:
  - India raster is streamed in chunks (never fully loaded during download)
  - Clipped array is deleted from RAM immediately after writing to disk
  - Output is written as tiled GeoTIFF (256x256 blocks) so downstream tools
    like rasterstats and QGIS read only the blocks they need, not the whole file
  - BIGTIFF=IF_SAFER handles outputs larger than 4GB automatically
"""

import gc
import glob
import logging
import urllib.request
import requests
import rasterio
import rasterio.mask
import geopandas as gpd
from pathlib import Path

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

DEFAULT_YEAR = 2020

BASE_DIR     = Path.cwd()
GEOJSON_GLOB = str(BASE_DIR / "Maps" / "Geojson" / "*_state.geojson")
ANTODAYA_DIR = BASE_DIR / "Sources" / "ANTYODAYA"
OUTPUT_DIR   =ANTODAYA_DIR / "data" / "rasters"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ANTODAYA_DIR.mkdir(parents=True, exist_ok=True)

CONSTRAINED_URL   = "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/{year}/BSGM/IND/ind_ppp_{year}_UNadj_constrained.tif"
UNCONSTRAINED_URL = "https://data.worldpop.org/GIS/Population/Global_2000_2020/{year}/IND/ind_ppp_{year}_UNadj.tif"

CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks during download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# STEP 1 — DOWNLOAD INDIA RASTER (streamed in chunks)
# ---------------------------------------------------------------------

def download_india_raster(year: int) -> Path:
    """
    Download the full India WorldPop raster in 4MB chunks —
    never loads the full 466MB into memory at once.
    Tries constrained first, falls back to unconstrained.
    Skips download if file already exists.
    """
    constrained_dest   =ANTODAYA_DIR/ f"ind_ppp_{year}_UNadj_constrained.tif"
    unconstrained_dest = ANTODAYA_DIR/ f"ind_ppp_{year}_UNadj.tif"

    if constrained_dest.exists():
        logger.info(f"Already downloaded: {constrained_dest.name} — skipping.")
        return constrained_dest
    if unconstrained_dest.exists():
        logger.info(f"Already downloaded: {unconstrained_dest.name} — skipping.")
        return unconstrained_dest

    def _stream_download(url, dest):
        head = requests.head(url, timeout=15)
        if head.status_code != 200:
            logger.warning(f"URL not available ({head.status_code}): {url}")
            return None

        total_bytes = int(head.headers.get("content-length", 0))
        size_mb = total_bytes / 1024 / 1024
        logger.info(f"Downloading ({size_mb:.0f} MB): {url}")

        downloaded = 0
        try:
            with requests.get(url, stream=True, timeout=(30, 300)) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            fh.write(chunk)
                            downloaded += len(chunk)
                            if total_bytes:
                                pct = downloaded / total_bytes * 100
                                print(f"\r  {dest.name}: {pct:.1f}%  ({downloaded // 1024 // 1024} MB)", end="", flush=True)
            print()  # newline after progress
            logger.info(f"Download complete: {dest}")
            return dest
        except Exception as e:
            if dest.exists():
                dest.unlink()  # remove partial file
            logger.error(f"Download failed: {e}")
            return None

    result = _stream_download(CONSTRAINED_URL.format(year=year), constrained_dest)
    if result:
        return result

    logger.info("Constrained raster unavailable — trying unconstrained...")
    result = _stream_download(UNCONSTRAINED_URL.format(year=year), unconstrained_dest)
    if result:
        return result

    raise RuntimeError(
        f"Could not download WorldPop raster for year {year}. "
        "Check your internet connection and try again."
    )


# ---------------------------------------------------------------------
# STEP 2 — CLIP TO STATE BOUNDARY
# ---------------------------------------------------------------------

def clip_to_state(india_raster: Path, geojson_path: str, year: int) -> Path:
    """
    Clip the India raster to a state boundary GeoJSON.

    Memory handling:
      - clipped_array is deleted from RAM immediately after writing
      - gc.collect() forces Python to release the memory
      - Output is tiled (256x256) so downstream tools read blocks not the full file
      - BIGTIFF=IF_SAFER auto-handles files > 4GB
    """
    state_name  = Path(geojson_path).stem.replace("_state", "")
    output_path = OUTPUT_DIR / f"{state_name}_pop_{year}.tif"

    if output_path.exists():
        logger.info(f"Already clipped: {output_path.name} — skipping.")
        return output_path

    logger.info(f"Clipping raster for: {state_name}")

    state_gdf = gpd.read_file(geojson_path)
    if state_gdf.crs is None:
        logger.warning(f"{Path(geojson_path).name} has no CRS — assuming EPSG:4326")
        state_gdf = state_gdf.set_crs("EPSG:4326")

    with rasterio.open(india_raster) as src:

        if state_gdf.crs != src.crs:
            logger.info(f"Reprojecting boundary: {state_gdf.crs} → {src.crs}")
            state_gdf = state_gdf.to_crs(src.crs)

        geometries = list(state_gdf.dissolve().geometry)

        nodata_val = src.nodata if src.nodata is not None else -99999

        clipped_array, clipped_transform = rasterio.mask.mask(
            src,
            geometries,
            crop=True,
            nodata=nodata_val,
            filled=True,
        )

        logger.info(f"Clipped shape: {clipped_array.shape} | dtype: {clipped_array.dtype}")

        meta = src.meta.copy()
        meta.update({
            "driver":     "GTiff",
            "height":     clipped_array.shape[1],
            "width":      clipped_array.shape[2],
            "transform":  clipped_transform,
            "nodata":     nodata_val,
            "compress":   "deflate",
            "dtype":      clipped_array.dtype,
            "tiled":      True,        # 256x256 blocks — downstream tools read only
            "blockxsize": 256,         # what they need, not the whole array
            "blockysize": 256,
            "BIGTIFF":    "IF_SAFER",  # auto BigTIFF if output exceeds 4GB
        })

        with rasterio.open(output_path, "w", **meta) as dst:
            dst.write(clipped_array)

        # Free RAM immediately — large states can be several hundred MB
        del clipped_array
        gc.collect()

    logger.info(f"Saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():

    year_input = input("Enter year (press Enter for default 2020): ").strip()
    year = int(year_input) if year_input else DEFAULT_YEAR

    geojson_files = sorted(glob.glob(GEOJSON_GLOB))
    if not geojson_files:
        logger.error(f"No state GeoJSON files found at: {GEOJSON_GLOB}")
        logger.error("Make sure Maps/Geojson/ contains *state.geojson files.")
        return

    logger.info(f"Found {len(geojson_files)} state GeoJSON file(s):")
    for gj in geojson_files:
        logger.info(f"  {Path(gj).name}")

    # Download India raster once — reused for all states
    logger.info("\n--- Downloading India raster ---")
    try:
        india_raster = download_india_raster(year)
    except RuntimeError as e:
        logger.error(str(e))
        return

    # Clip to each state boundary
    logger.info("\n--- Clipping to state boundary ---")
    success = []
    failed  = []

    for idx, gj in enumerate(geojson_files, 1):
        state_name = Path(gj).stem.replace("_state", "")
        logger.info(f"\n[{idx}/{len(geojson_files)}] {state_name}")
        try:
            out = clip_to_state(india_raster, gj, year)
            success.append(out)
        except Exception as e:
            logger.error(f"Failed to clip {state_name}: {e}")
            failed.append(state_name)

if __name__ == "__main__":
    main()