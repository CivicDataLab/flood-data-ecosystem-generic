# Bhuvan Flood Inundation Pipeline

Extract flood inundation data from ISRO Bhuvan's WMS layers and compute subdistrict-level zonal statistics.

---

## Two Ways to Run

There are two approaches available. Both produce the same final output — per-state, per-month inundation CSVs — but differ in dependencies and how much control you want over each step.

| | Standalone (`bhuvan_standalone.py`) | Manual (`manual_gdal_scripts/`) |
|---|---|---|
| **Best for** | Quick runs, new users | Full control, debugging each step |
| **Key dependencies** | `netCDF4`, `xarray`, `rioxarray`, `Pillow`, `requests`, `BeautifulSoup` | GDAL system install, Firefox + geckodriver, `selenium` |
| **How it works** | Downloads PNG tiles, stitches, converts to GeoTIFF, runs zonal stats — all in one script | Five separate scripts, each handling one stage |
| **Watermark removal** | Built-in (handled during tile stitching) | Separate `remove_watermark.py` step |
| **Date fetching** | Plain HTTP request — no browser needed | Selenium headless Firefox |
| **Config** | `bhuvan_config.json` (auto-created) | `DEFAULT_STATE_CONFIG` dict inside each script |

---

## Option A — Standalone Script

### Prerequisites

```bash
pip install requests beautifulsoup4 lxml pillow numpy netCDF4 xarray rioxarray \
            rasterio rasterstats geopandas pandas joblib natsort
```

> `netCDF4`, `xarray`, `rioxarray`, `joblib`, and `natsort` are optional — the script degrades gracefully if they are missing, but GeoTIFF output and parallel tile downloading will be disabled.

### Quickstart

```bash
# First run: create the config file
python bhuvan_standalone.py --init-config

# List available states and their cached date counts
python bhuvan_standalone.py --list-states

# Fetch and cache available dates for a state
python bhuvan_standalone.py --state "Assam" --fetch-dates

# Process all cached dates for a state
python bhuvan_standalone.py --state "Assam"

# Process specific dates only
python bhuvan_standalone.py --state "Assam" --dates "2024_15_08_18,2024_16_08_06"

# Process and generate zonal stats CSVs (requires a subdistrict shapefile)
python bhuvan_standalone.py --state "Assam" --shapefile /path/to/assam_subdistrict.shp

# Specify a custom output directory
python bhuvan_standalone.py --state "Bihar" --output /data/bihar_flood
```

### All CLI flags

| Flag | Short | Description |
|------|-------|-------------|
| `--state` | `-s` | State name to process (required for processing) |
| `--dates` | `-d` | Comma-separated date strings to process |
| `--output` | `-o` | Output directory (default: `bhuvan_data/<state>/`) |
| `--fetch-dates` | `-f` | Fetch fresh dates from Bhuvan via HTTP |
| `--list-states` | `-l` | Print all configured states and their cached date counts |
| `--show-dates` | | Print cached dates for the given `--state` |
| `--init-config` | | Write `bhuvan_config.json` with default state configs |
| `--shapefile` | | Path to subdistrict shapefile for zonal stats CSV output |

### Output structure

```
bhuvan_data/<state_name>/
├── Tiles/                            ← temporary per-tile PNGs (cleared after stitching)
├── vert/                             ← temporary vertical column strips (cleared after stitching)
├── PNGs/
│   └── <date>.png                    ← binary inundation mask
├── NCs/                              ← intermediate NetCDF files (removed after TIFF creation)
├── tiffs/
│   └── <date>.tif                    ← final GeoTIFF per date
├── stitched_monthly/
│   └── stitched_<year>_<month>.tif   ← monthly cumulative raster
└── csv/
    └── inundation_pct_<year>_<month>.csv
```

### How it works internally

1. **Date fetching** — makes a plain HTTP GET to the Bhuvan flood tool URL and parses date `<div>` elements with BeautifulSoup. Dates are cached in `bhuvan_config.json` so subsequent runs do not need to re-fetch.
2. **Tile download** — `generate_bboxes()` divides the state bounding box into a grid of 256×256 WMS tiles. `download_tile()` fetches each one and validates it is a real PNG (not a WMS error XML). If `joblib` is installed, tiles are downloaded in parallel across all CPU cores.
3. **Watermark removal** — during stitching, `remove_watermark_from_array()` sets all grayscale pixels (R == G == B) to white, eliminating the Bhuvan logo without a separate step.
4. **Stitching** — tiles are first merged vertically into column strips, then horizontally into a single full-state PNG. The result is binarised: any non-white pixel becomes `1` (inundated), white becomes `0`.
5. **NetCDF → GeoTIFF** — the PNG is saved as a NetCDF4 file with proper lat/lon coordinates, then converted to a georeferenced GeoTIFF via `rioxarray`. The intermediate `.nc` is deleted automatically.
6. **Zonal statistics** — if `--shapefile` is provided, all TIFFs for each year/month are stacked, `rasterstats.zonal_stats` is run for both extent and intensity, and the results are written to CSV.

---

## Option B — Manual GDAL Scripts

Located in `manual_gdal_scripts/`. Run the five scripts in this order:

```
get_dates.py → gdal_wms.py → remove_watermark.py → run_transformer.py → transformer.py
```

### Prerequisites

**System:**
- GDAL with `gdal_translate` and `gdal.Warp` available on `PATH`
- Firefox + geckodriver installed at `/snap/bin/firefox.geckodriver`

**Python:**
```bash
pip install selenium geopandas numpy pandas rasterio rasterstats
```

**Directory layout:**
```
<project_root>/
├── manual_gdal_scripts/
│   ├── get_dates.py
│   ├── gdal_wms.py
│   ├── remove_watermark.py
│   ├── run_transformer.py
│   └── transformer.py
└── Maps/
    └── Geojson/
        └── <state>_subdistrict       ← subdistrict boundary file for zonal stats
```

---

### Step 1 — `get_dates.py`

Launches a headless Firefox browser and scrapes the available flood map dates for a state directly from the Bhuvan portal iframe.

```bash
python manual_gdal_scripts/get_dates.py
```

1. Prints a numbered list of configured states.
2. You select a state by name or number.
3. The script switches into the Bhuvan iframe, selects the state dropdown, and reads all date `<div>` elements.
4. Prints the formatted date strings to the console.

**Example output:**
```
  1. Andhra Pradesh
  2. Assam
  ...

Enter state name (or number): 2

Fetching dates for: Assam ...

Dates found (9):
  2025_21_09_18
  2025_20_09_10
  2025_19_09_10
  ...
```

**Note:** Copy the date strings you want — you will select them interactively in Step 2.

---

### Step 2 — `gdal_wms.py`

Downloads the Bhuvan WMS layer for each chosen date and warps it to a compressed GeoTIFF using the state's bounding box.

```bash
python manual_gdal_scripts/gdal_wms.py
```

1. Prompts for state selection.
2. Scrapes available dates for that state.
3. Lets you select which dates to download:
   - `all` — every date
   - `1,3,5` — specific dates by number
   - `2-6` — a range
4. For each date, runs `gdal_translate` to create a WMS XML descriptor, then `gdal.Warp` to write a tiled, DEFLATE-compressed GeoTIFF. Already-downloaded TIFFs are skipped automatically.

**Output:** `Sources/BHUVAN/<state>/tiffs/<date>.tif`

---

### Step 3 — `remove_watermark.py`

Removes the Bhuvan watermark/logo pixels from each downloaded GeoTIFF so they do not inflate inundation pixel counts in later steps.

```bash
python manual_gdal_scripts/remove_watermark.py
```

Point the script at the `tiffs/` folder for your state. Cleaned files are written to `tiffs/removed_watermarks/`.

> **Important:** This step must be completed before Step 4. Both `run_transformer.py` and `transformer.py` read exclusively from the `removed_watermarks/` subfolder.

---

### Step 4 — `run_transformer.py`

Iterates over every year/month combination you specify and calls `transformer.py` as a subprocess for each month that has at least one TIFF available.

```bash
python manual_gdal_scripts/run_transformer.py
```

1. Prompts for state selection.
2. Prompts for years to process (`all` for 2019–2024, `2021,2023`, or `2021-2024`).
3. Prompts for the Python interpreter path — press Enter to use the currently active environment.
4. For each year × month, globs `removed_watermarks/` for matching files. If found, calls `transformer.py <year> <month> <state_name>` and reports its exit code.

**Example:**
```
── 2024 ──────────────────────────
  07: no files, skipping.
  08: 3 file(s) found — running transformer...
  09: 2 file(s) found — running transformer...
```

---

### Step 5 — `transformer.py`

Called automatically by `run_transformer.py`. Can also be run directly for a single month.

```bash
python manual_gdal_scripts/transformer.py <year> <month> <state_name>
# e.g.
python manual_gdal_scripts/transformer.py 2024 08 assam
```

1. Loads the state's subdistrict GeoJSON from `Maps/Geojson/`.
2. Finds all cleaned TIFFs matching the year/month pattern.
3. Sums them into a monthly composite raster (skipped if it already exists).
4. Runs `rasterstats.zonal_stats` twice — once for inundation extent (pixel counts) and once for intensity (normalised pixel values).
5. Merges results and saves a CSV.

**Output:** `Sources/BHUVAN/<state>/data/variables/inundation_pct/inundation_pct_<year>_<month>.csv`

---

## Output Columns (Both Approaches)

| Column | Description |
|--------|-------------|
| `object_id` | Subdistrict identifier from the boundary file |
| `count_bhuvan_pixels` | Total pixels overlapping the subdistrict |
| `count_inundated_pixels` | Pixels with a non-zero inundation value |
| `inundation_pct` | `count_inundated_pixels / count_bhuvan_pixels` |
| `inundation_intensity_mean` | Mean normalised pixel value across all pixels |
| `inundation_intensity_mean_nonzero` | Mean normalised pixel value across inundated pixels only |
| `inundation_intensity_sum` | Sum of normalised pixel values |

---

## Adding a New State

**Standalone:** Run `--init-config` once, then edit `bhuvan_config.json` directly. The required fields are the same as below.

**Manual scripts:** Edit the `DEFAULT_STATE_CONFIG` dictionary in both `get_dates.py` and `gdal_wms.py`:

```python
"state name": {
    "code": "xx",                # two-letter code used in WMS layer names
    "dropdown_value": "idXXX_0", # value of the state's <option> on the Bhuvan dropdown
    "dropdown_id": "minusXXX",   # id of the <div> containing the date list
    "bbox": {
        "lat_south": ...,
        "lat_north": ...,
        "lon_west":  ...,
        "lon_east":  ...,
    }
}
```

Then place the matching boundary file at `Maps/Geojson/<state_name>_subdistrict` (manual) or pass it via `--shapefile` (standalone).

---

## Troubleshooting

| Symptom | Approach | Likely cause | Fix |
|---------|----------|-------------|-----|
| All tiles invalid, 0 valid TIFFs | Standalone | WMS layer name wrong for that date | Verify the date string format; check the layer exists on the Bhuvan portal |
| `GeoTIFF output disabled` warning | Standalone | `xarray`/`rioxarray` not installed | `pip install xarray rioxarray` |
| Slow tile downloads | Standalone | `joblib` not installed, running serially | `pip install joblib` |
| `NoSuchElementException` on dropdown | Manual | Page reset to Delhi before Selenium acted | Increase `time.sleep(5)` in `get_dates.py` |
| `gdal_translate` non-zero exit | Manual | WMS layer does not exist for that date | Check the date string and state code |
| `gdal.Warp` returns `None` | Manual | Corrupt or empty XML descriptor | Delete the `.xml` file and re-run `gdal_wms.py` |
| No files in `removed_watermarks/` | Manual | Watermark step skipped | Run `remove_watermark.py` before `run_transformer.py` |
| Zonal stats merge fails on `object_id` | Both | Boundary file missing that column | Check attribute names in your boundary file and update the merge key in the script |