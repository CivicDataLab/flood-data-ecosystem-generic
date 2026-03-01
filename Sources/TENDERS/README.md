# Flood Tender Analysis Pipeline

A Python pipeline that ingests raw government tender CSVs, identifies flood-related tenders, classifies and geo-tags them to district and block level, and exports aggregated variable CSVs ready for spatial analysis.

---

## Project Structure

```
Sources/TENDERS/
├── scripts/
│   ├── count_tenders.py
│   ├── flood_tenders.py
│   ├── geocode_district.py
│   ├── geocode_Subdistrict.py
│   └── transformer.py
├── data/
│   ├── monthly_tenders/                   ← raw input CSVs (one per month)
│   ├── flood_tenders/                     ← flood-filtered CSVs (one per month)
│   ├── flood_tenders_all.csv              ← combined flood tenders
│   ├── floodtenders_districtgeotagged.csv ← district-tagged output
│   ├── floodtenders_blockgeotagged.csv    ← block/sub-district-tagged output
│   └── variables/                         ← final aggregated variable CSVs
│       └── <variable_name>/
│           └── <variable_name>_<YYYY_MM>.csv
└── Keywords_config.json                   ← keyword lists for filtering & classification

Maps/
└── Geojson/
    ├── *_villages.geojson                 ← village-level geography
    └── *_subdistricts.geojson             ← sub-district geometry for merging
```

---

## Prerequisites — Scraper

Before running any script in this pipeline, you must first run the scripts in the **`scraper/`** folder. The scraper is responsible for fetching and downloading the raw monthly tender data that this pipeline depends on.

```
Sources/scraper/         ← run all scripts here first
      ↓
Sources/TENDERS/scripts/ ← then run this pipeline
```

Ensure the scraper has completed successfully and that `data/monthly_tenders/` is populated with CSV files before proceeding.

---

## Pipeline Overview

Run the scripts in order:

```
count_tenders.py
      ↓
flood_tenders.py
      ↓
geocode_district.py
      ↓
geocode_Subdistrict.py
      ↓
transformer.py
```

---

## Scripts

### 1. `count_tenders.py`
Consolidates all monthly raw CSVs into a single file and prints summary counts.

- **Input:** `data/monthly_tenders/*.csv`
- **Output:** `data/all_tenders.csv`
- **Prints:** total tender count and count of `Status = "Accepted-AOC"` tenders

---

### 2. `flood_tenders.py`
Filters tenders for flood relevance using keyword matching, then classifies each tender.

- **Input:** `data/monthly_tenders/*.csv`, `Keywords_config.json`
- **Output:** `data/flood_tenders/<filename>.csv` (one per month), `data/flood_tenders_all.csv`

**Classification columns added:**

| Column | Description |
|---|---|
| `is_flood_tender` | Boolean — matched at least one positive keyword and no negative keywords |
| `Season` | Pre-Monsoon (Mar–May) / Monsoon (Jun–Sep) / Post-Monsoon (Oct–Feb) |
| `Scheme` | Matched government scheme name (e.g. PMGSY, MGNREGS) |
| `Erosion` | Boolean flag — tender relates to erosion works |
| `Roads_Bridges_Embkt` | Boolean flag — tender relates to roads, bridges or embankments |
| `Response Type` | Immediate Measures / Repair and Restoration / Preparedness Measures / Others |

Keyword lists for all classifications are loaded from `Keywords_config.json`. Tenders from excluded departments are dropped.

---

### 3. `geocode_district.py`
Geo-tags each flood tender to a district using three independent text signals.

- **Input:** `data/flood_tenders_all.csv`, `Maps/Geojson/*_villages.geojson`
- **Output:** `data/floodtenders_districtgeotagged.csv`

**Signals used:**

| Signal | Source field |
|---|---|
| A | `location` column (fuzzy match) |
| B | `tender_externalreference` (regex match) |
| C | `tender_title` + `Work Description` (regex match) |

Signals are reconciled into `DISTRICT_FINALISED`:
- All signals agree → district name
- No signal matches → `NA`
- Signals disagree → `CONFLICT`

The script auto-detects whether the GeoJSON uses `block_name`, `sdtname`, or both for sub-district lookups.

---

### 4. `geocode_Subdistrict.py`
For each district, matches tender text against villages, blocks, gram panchayats and sub-districts to assign block-level geography.

- **Input:** `data/floodtenders_districtgeotagged.csv`, `Maps/Geojson/*.csv` (villages), `Maps/Geojson/*_subdistricts.geojson`
- **Output:** `data/floodtenders_blockgeotagged.csv`

**Columns added:**

| Column | Description |
|---|---|
| `tender_villages` | Village name(s) matched in tender text |
| `tender_block` | Block inferred via village match |
| `tender_subdistrict` | Sub-district matched |
| `gp` | Gram Panchayat matched |
| `tender_block_location` | Block matched directly from tender text |
| `BLOCK_FINALISED` | Authoritative block/sub-district assignment |

The script processes tenders district-by-district to reduce false matches across district boundaries. Tenders with `DISTRICT_FINALISED = NA` or `CONFLICT` are passed through unmatched.

---

### 5. `transformer.py`
Merges block-geotagged tenders with sub-district GeoJSON geometry and exports aggregated monthly variable CSVs.

- **Input:** `data/floodtenders_blockgeotagged.csv`, `Maps/Geojson/*_subdistricts.geojson`
- **Output:** `data/variables/<variable_name>/<variable_name>_<YYYY_MM>.csv`

**Variables exported:**

| Variable | Description |
|---|---|
| `total_tender_awarded_value` | Sum of awarded value per sub-district per month |
| `<scheme>_tenders_awarded_value` | Awarded value by scheme (one variable per scheme) |
| `<response_type>_tenders_awarded_value` | Awarded value by response type (one variable per type) |

Each output CSV contains `object_id` (sub-district geometry ID) and the variable value, suitable for direct joining with the GeoJSON for mapping.

---

## Configuration — `Keywords_config.json`

All keyword lists are stored in a single JSON file co-located with the scripts. Keys expected:

```json
{
  "flood_filter": {
    "positive": ["flood", "inundation", "embankment", ...],
    "negative": ["drought", "irrigation", ...]
  },
  "exclusion_departments": ["Dept A", "Dept B", ...],
  "scheme_keywords": ["pmgsy", "mgnregs", ...],
  "erosion_keywords": ["erosion", "scouring", ...],
  "roads_bridges_embankments_keywords": ["bridge", "culvert", ...],
  "response_type": {
    "immediate_measures": ["emergency", "relief", ...],
    "repair_restoration": ["repair", "restoration", ...],
    "preparedness_measures": ["desilting", "maintenance", ...]
  }
}
```

---

## Requirements

```
pandas
geopandas
python-dateutil
tqdm
```

Install with:
```bash
pip install pandas geopandas python-dateutil tqdm
```

---

## GeoJSON Column Compatibility

All scripts auto-detect whether the input GeoJSON uses `block_name`, `sdtname`, or both as the sub-district identifier. No manual configuration is needed — the pipeline adapts at runtime and logs which column is being used.