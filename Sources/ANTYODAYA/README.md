# Mission Antyodaya Data Pipeline

This pipeline downloads village-level data from the Mission Antyodaya portal, spatially tags each village to a Revenue Circle, and computes district-level vulnerability indicators.

---

## Step 1 — Download Data from Mission Antyodaya Portal

1. Go to **[https://missionantyodaya.dord.gov.in/rawData2022.html](https://missionantyodaya.dord.gov.in/rawData2022.html)**

2. Fill in the form as follows:

   | Field | Value |
   |---|---|
   | **Data Type** | Mission Antyodaya 2022–2023 |
   | **State** | Select your desired state |
   | **Districts** | Select All Districts |
   | **Name** | Your full name |
   | **Organisation** | Your organisation name |
   | **Email ID** | Your email address |
   | **Purpose of Use** | Describe your intended use (e.g. "Research / GIS analysis") |

3. Submit the form and download the Excel file (`.xlsx`) that is provided. Note down the full path to this file on your machine — you will need it when running `main.py`.

---

## Step 2 — Prerequisites

Make sure you have the following Python packages installed:

```bash
pip install pandas geopandas openpyxl shapely rasterio rasterstats
```

Your project directory should be structured as follows before running any scripts:

```
project/
│
├── Maps/
│   └── Geojson/
│       ├── <state>_state.geojson       
├── Sources/
│   ├── ANTYODAYA/
│   │   ├── data/                              # Created automatically by the scripts
│   │   └── scripts/
│   │       └── fetcher_raster.py              # WorldPop download + clip script
│   └── WORLDPOP/
│       ├── ind_ppp_2020_UNadj_constrained.tif # Downloaded automatically by fetcher_raster.py
│       └── <state>_pop_2020.tif               # Clipped output from fetcher_raster.py
│
├── main.py
└── transformer.py
```

---

## Step 3 — Download and Clip WorldPop Raster (`fetcher_raster.py`)

Before running the main pipeline, you need a WorldPop population raster clipped to your state boundary. `fetcher_raster.py` handles this automatically — it downloads the raster directly from WorldPop and clips it to your state GeoJSON.

Always run this from the **project root**, not from inside the scripts folder:

```bash
cd /path/to/your/project
python Sources/ANTYODAYA/scripts/fetcher_raster.py
```

Or with explicit arguments:

```bash
python Sources/ANTYODAYA/scripts/fetcher_raster.py --year 2020 --state-geojson Maps/Geojson/odisha_state.geojson
```

**What it does internally:**

- Resolves your state boundary from `Maps/Geojson/*_state.geojson`.
- Downloads the WorldPop UN-adjusted constrained population raster for India (`ind_ppp_{year}_UNadj_constrained.tif`) from `data.worldpop.org` into `Sources/WORLDPOP/`. Falls back to the unconstrained raster if the constrained one is unavailable for that year. Skips the download entirely if the file already exists.
- Reprojects the state boundary to match the raster CRS if they differ.
- Clips the full India raster to your state boundary using `rasterio`.
- Saves the clipped output as `Sources/WORLDPOP/<statename>_pop_<year>.tif`.

> **Note:** The full India raster is ~400 MB — the initial download will take a few minutes depending on your connection. Subsequent runs skip the download and go straight to clipping.

**Arguments:**

| Argument | Default | Description |
|---|---|---|
| `--year` | `2020` | Year of WorldPop data |
| `--state-geojson` | `Maps/Geojson/*_state.geojson` | Path or glob to state boundary GeoJSON |
| `--raster-dir` | `Sources/ANTYODAYA/data/rasters` | Where to store the downloaded raster |
| `--output` | `Sources/ANTYODAYA/data/<state>_pop_<year>.tif` | Output path for the clipped raster |

---

## Step 4 — Run `main.py`

`main.py` is the script in the pipeline to be run after the fetcher_raster.py. It reads the raw Antyodaya Excel file, converts each village record into a geographic point using its latitude/longitude, and spatially joins it to a Revenue Circle polygon. Villages that don't fall inside any polygon are then re-matched using their official village boundary centroid from the Bharat Maps GeoJSON.

```bash
python main.py
```

When prompted, paste the full path to the Antyodaya `.xlsx` file you downloaded in Step 1:

```
Enter the path of the antodaya file: /path/to/your/downloaded_file.xlsx
```

**What it does internally:**

- Loads the Antyodaya Excel file and creates a GeoDataFrame of village points.
- Loads the `*_villages.geojson` file from `Maps/Geojson/` as the Revenue Circle reference layer.
- Performs a spatial join — each village point is matched to the Revenue Circle polygon it falls within.
- For any village that couldn't be matched (point falls outside all polygons), it looks up the village's official boundary from the Bharat Maps GeoJSON, takes its centroid, and retries the spatial join.
- Writes two output files to `Sources/ANTYODAYA/data/`:
  - `antyodaya_village_dataset_with_revenue_circle.xlsx` — all villages with their tagged Revenue Circle.
  - `MissionAntyodaya2020_<state>_taggedRC.csv` — full tagged dataset.
  - `MissionAntyodaya2020_<state>_vul.csv` — a trimmed file with only the columns needed for vulnerability analysis.

---

## Step 5 — Run `transformer.py`

`transformer.py` is the script to be run after main.py. It takes the tagged village data produced by `main.py` and aggregates it up to the Revenue Circle level, combining rural Antyodaya indicators with urban population estimates from the WorldPop raster.

```bash
python transformer.py
```

When prompted, enter the state code (a short abbreviation used in your file names, e.g. `OD` for Odisha, `JH` for Jharkhand):

```
Enter the name of the state: OD
```

**What it does internally:**

- **Loads tagged village data** from the CSV produced by `main.py`.
- **Loads urban settlement shapes** from `Sources/ANTYODAYA/data/<state>_urban_shapes/` and overlays them on the WorldPop raster to estimate the total urban population in each Revenue Circle.
- **Derives urban household indicators** from the population estimate using fixed multipliers (average household size of 4.3, urban electricity access rate of 20 households per unit, etc.).
- **Aggregates rural vulnerability indicators** from the village-level Antyodaya data up to the Revenue Circle level. The indicators processed are:
  - Net sown area (hectares)
  - Domestic electricity availability (hours/day, encoded into a numeric score)
  - Telephone service availability
  - Householdswith piped water connections
  - Households without sanitary latrines
- **Combines rural and urban estimates** for each indicator at the Revenue Circle level and computes percentages and averages.
- **Writes the final output** to `Sources/ANTYODAYA/data/variables/antyodaya/antyodaya_variables.csv` — one row per Revenue Circle, with all vulnerability variables ready for downstream modelling or mapping.

---

## Output Files Summary

| File | Script | Description |
|---|---|---|
| `<state>_pop_<year>.tif` | `fetcher_raster.py` | WorldPop raster clipped to state boundary |
| `antyodaya_village_dataset_with_revenue_circle.xlsx` | `main.py` | Village-level data with Revenue Circle tags |
| `MissionAntyodaya2020_<state>_taggedRC.csv` | `main.py` | Full tagged dataset as CSV |
| `MissionAntyodaya2020_<state>_vul.csv` | `main.py` | Trimmed file with vulnerability input columns only |
| `antyodaya_variables.csv` | `transformer.py` | Revenue Circle-level aggregated vulnerability variables |

---

## Notes

- If `glob` finds multiple GeoJSON files matching the pattern in `Maps/Geojson/`, only the first match is used. Make sure only one file per pattern exists in that folder.
- The WorldPop file must be the `.tif` raster — not the `.tif.aux.xml` sidecar file.
- All intermediate and output directories are created automatically if they do not exist.