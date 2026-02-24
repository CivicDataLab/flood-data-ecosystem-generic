# WorldPop Population Data Pipeline

## Overview

Population and housing census data are critical baseline inputs for disaster risk reduction planning. However, census data aggregated at administrative units are difficult to integrate with other spatial datasets. [WorldPop](https://www.worldpop.org/) (Lloyd et al., 2019) uses machine learning to correlate population densities with geographic covariate layers, disaggregating census counts into 100m × 100m grid cells via Random Forest-based asymmetric redistribution.

This pipeline downloads, processes, and projects WorldPop population estimates for every subdistrict  in the state of interest , producing annual variable files ready for use in the IDS-DRR model.

---

## Data Source

IDS-DRR uses the [Unconstrained individual countries 2000–2020 UN adjusted (100m resolution)](https://hub.worldpop.org/geodata/listing?id=29) population count estimates from WorldPop for years 2017–2020.

The **top-down, unconstrained** estimation method assumes no settlement dataset is complete enough to identify all residential areas globally. Census databases are disaggregated to produce non-zero population allocations for every land grid cell, adjusted to match UN national population estimates.

For years beyond 2020, the pipeline extrapolates using linear regression trained on the 2015–2020 estimates, following the [linear extrapolation method described by MEASURE Evaluation](https://www.measureevaluation.org/resources/training/online-courses-and-resources/non-certificate-courses-and-mini-tutorials/population-analysis-for-planners/lesson-6.html). All rasters are cropped to the extent of the state before processing.

---

## Output Variables

The following variables are computed for each revenue circle in Assam:

| Variable | Description |
|---|---|
| `sum_population` | Total population within the the subdistrict |
| `mean_sex_ratio` | Number of females per 1,000 males |
| `sum_aged_population` | Total population aged 65 and above (age classes 65, 70, 75, 80) |
| `sum_young_population` | Total population aged 0–4 (age classes 0, 1) |

---

## Project Structure

```
.
├── scripts/
│   ├── geojson_processor.py
│   ├── worldpop_data_fetcher.py
│   ├── agesex_transformer.py
│   ├── zonalstats.py
│   ├── projections.py
│   └── transformer.py
│
└── Sources/WORLDPOP/
    └── data/
        ├── worldpopstats_YYYY.csv        # Per-year stats files (one per year)
        ├── agesexstructure/
        │   └── YYYY/
        │       └── {object_id}_agesexpyramid_YYYY.csv
        ├── Scraper_data/
        │   └── Geojson_shapefiles/
        │       └── {object_id}.geojson
        ├── {variable}_projections.csv    # Output of projections.py
        └── variables/
            └── {variable}/
                └── {variable}_YYYY.csv  # Final model-ready files
```

---

## Scripts

### 1. `geojson_processor.py`

**Purpose:** Prepares subdistrict boundary files for use in API calls and spatial processing.

Reads the raw subdistrict GeoJSON files from `Maps/Geojson/`, converts any `MultiPolygon` geometries to single `Polygon` geometries (retaining the largest polygon where multiple parts exist), simplifies coordinates to reduce file size, and writes one `.geojson` file per subdistrict — keyed by `object_id` — into the scraper data directory.

```
Input:  Maps/Geojson/*_subdistricts.geojson
Output: Sources/WORLDPOP/data/Scraper_data/Geojson_shapefiles/{object_id}.geojson
```

---

### 2. `worldpop_data_fetcher.py`

**Purpose:** Fetches population data from the WorldPop API for each subdistrict geometry.

Runs interactively, prompting the user to select a year and a dataset type. Two datasets are supported:

- **`wpgpas`** — Age-sex pyramid: returns a demographic breakdown by age group and sex
- **`wpgppop`** — Total population: returns an aggregate population count

The script reads the processed GeoJSON files produced by `geojson_processor.py`, constructs the API payload (handling geometry simplification and coordinate truncation to avoid HTTP 413 payload errors), and submits requests to the WorldPop stats endpoint. Long-running requests are handled via async polling with exponential backoff. Results are saved as CSV files, one per subdistrict per year.

```
Input:  Sources/WORLDPOP/data/Scraper_data/Geojson_shapefiles/{object_id}.geojson
Output: Sources/WORLDPOP/data/agesexstructure/{year}/{object_id}_agesexpyramid_{year}.csv
        Sources/WORLDPOP/data/agesexstructure/{year}/{object_id}_wpgppop_{year}.csv
```

**Usage:** Run interactively — the script will prompt for year, dataset, and directory.

```bash
python3 worldpop_data_fetcher.py
```

---

### 3. `agesex_transformer.py`

**Purpose:** Computes demographic statistics from the age-sex pyramid CSVs and merges them into the master stats file for each year.

For each revenue circle, reads the `{object_id}_agesexpyramid_{year}.csv` file produced by `worldpop_data_fetcher.py` and calculates:

- `mean_sex_ratio`: females per 1,000 males across all age groups
- `sum_aged_population`: total population in age classes 65, 70, 75, and 80
- `sum_young_population`: total population in age classes 0 and 1

These statistics are merged back into the corresponding `worldpopstats_{year}.csv` file on `object_id` and the file is updated in place.

```
Input:  Sources/WORLDPOP/data/agesexstructure/{year}/{object_id}_agesexpyramid_{year}.csv
        Sources/WORLDPOP/data/worldpopstats_{year}.csv
Output: Sources/WORLDPOP/data/worldpopstats_{year}.csv  (updated in place)
```

**Usage:**

```bash
python3 agesex_transformer.py
```

---

### 4. `projections.py`

**Purpose:** Extrapolates a given variable beyond the observed data range using linear regression.

Reads all `worldpopstats_*.csv` files, concatenates them into a single time-series dataframe, and fits a `LinearRegression` model per `object_id` on the specified variable. Projects values for each future year and appends results to `{variable}_projections.csv`. Takes the target variable as a command-line argument.

```
Input:  Sources/WORLDPOP/data/worldpopstats_*.csv
Output: Sources/WORLDPOP/data/{variable}_projections.csv
```

**Usage:**

```bash
python3 projections.py sum_aged_population
python3 projections.py mean_sex_ratio
python3 projections.py sum_young_population
python3 projections.py sum_population
```

---

### 5. `transformer.py`

**Purpose:** Produces the final model-ready variable files, one CSV per variable per year, covering all observed and projected years.

Reads all `worldpopstats_*.csv` files (observed years) and all `*_projections.csv` files (projected years), merges them, and splits the combined dataset by variable and year. Each output file contains only `object_id` and the variable value for that year, written to `data/variables/{variable}/{variable}_{year}.csv`.

```
Input:  Sources/WORLDPOP/data/worldpopstats_*.csv
        Sources/WORLDPOP/data/*_projections.csv
Output: Sources/WORLDPOP/data/variables/{variable}/{variable}_{year}.csv
```

**Usage:**

```bash
python3 transformer.py
```

---

## Pipeline Execution Order

Run the scripts in the following order for a complete pipeline run:

```
geojson_processor.py        →   Prepare subdistrict boundaries
    ↓
worldpop_data_fetcher.py    →   Fetch age-sex and population data from WorldPop API
    ↓
agesex_transformer.py       →   Compute demographic stats and update worldpopstats files
    ↓
projections.py              →   Extrapolate each variable to future years (run per variable)
    ↓
transformer.py              →   Generate final variable files for model input
```

---

## Dependencies

```
pandas
numpy
scikit-learn
shapely
requests
pathlib
glob
```