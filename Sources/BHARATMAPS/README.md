# BharatMaps Infrastructure Analysis Workflow

## Overview

This workflow processes infrastructure data (roads, railways, schools, and healthcare facilities) for Indian states and calculates statistics at the subdistrict level. The process involves downloading data from ESRI Living Atlas, clipping it to state boundaries, and computing spatial statistics.


## Prerequisites

### Required Software

- **QGIS** >= 3.16 (for data download and clipping)
- **Python** >= 3.8
- **Python Packages:**
```bash
  pip install geopandas pandas shapely
```

### Required Data

- **State subdistrict boundary file**: `{state_name}_subdistricts.geojson`
  - Location: `Maps/Geojson/`
  - Must be in EPSG:4326 (WGS84) coordinate system

---

## Directory Structure
```
project/
├── Maps/
│   └── Geojson/
│       └── {state}_subdistricts.geojson          # Input: Subdistrict boundaries
│
├── Sources/
│   └── BHARATMAPS/
│       └── data/
│           ├── RawData/                          # Raw downloaded data
│           │   ├── BharatMaps_HealthCenters.geojson
│           │   ├── BharatMaps_Schools.geojson
│           │   ├── BharatMaps_RoadsLengths.geojson
│           │   └── BharatMaps_RailLengths.geojson
│           │
│           └── variables/                         # Output statistics
│               ├── Schools/Schools.csv
│               ├── HealthCenters/HealthCentres.csv
│               ├── RoadLengths/
│               │   └── RoadLengths.csv
│               └── RailLengths/
│                   └── RailLengths.csv
│
├── scripts/
│   ├── qgis_scripts/                             # QGIS download scripts
│   │   ├── healthcare_qgis_clipping.py
│   │   ├── schools_qgis_clipping.py
│   │   ├── road_qgis_clipping.py
│   │   └── rail_qgis_clipping.py
│   │
│   └── analysis/                                 # Analysis scripts
│       ├── schools_per_sub.py
│       ├── healthcentres_per_sub.py
│       ├── roads_per_sub.py
│       └── rails_per_sub.py
│
└── README.md
```

---

## Workflow Overview
```
┌────────────────────────────────────────────────────────────────┐
│ STEP 1: Download & Clip Data (QGIS)                          │
├────────────────────────────────────────────────────────────────┤
│ Input:  State boundary (GeoJSON)                              │
│ Process: Download from ESRI → Clip to boundary → Save         │
│ Output: BharatMaps_{Infrastructure}.geojson in RawData/       │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│ STEP 2: Calculate Statistics (Python)                         │
├────────────────────────────────────────────────────────────────┤
│ Input:  Raw GeoJSON files + Subdistrict boundaries            │
│ Process: Spatial join → Count/sum → Aggregate                 │
│ Output: CSV files with statistics per subdistrict             │
└────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Download and Clip Data

You can obtain the raw infrastructure data in **two ways**:

### Option A: Using QGIS Scripts (Recommended)

#### Method 1: QGIS Python Console

1. **Open QGIS Desktop**

2. **Open Python Console**:
   - Navigate to: `Plugins` → `Python Console`
   - Or press `Ctrl + Alt + P` (Windows/Linux) or `Cmd + Alt + P` (Mac)

3. **Open the Script Editor**:
   - Click the "Show Editor" button in the Python Console
   - Or press `Ctrl + Shift + E`

4. **Load and Run Script**:
   - Open script: `scripts/qgis_scripts/download_health_centers.py`
   - Click "Run Script" button (▶)
   - When prompted, enter the **absolute path** to your subdistrict boundary file:
```
     Example: /home/user/project/Maps/Geojson/bihar_subdistricts.geojson
```

5. **Wait for completion**:
   - The script will download all healthcare facilities for India
   - Clip them to your state boundary
   - Save the output to the same directory as your boundary file

6. **Move output file**:
```bash
   mv /path/to/Maps/Geojson/BharatMaps_HealthCenters.geojson \
      /path/to/Sources/BHARATMAPS/data/RawData/
```

7. **Repeat for other infrastructure**:

#### Method 2: Standalone QGIS Python Environment

If you prefer running scripts outside QGIS GUI:
```bash
# Activate QGIS Python environment
# Linux/Mac:
export PYTHONPATH=/usr/share/qgis/python:$PYTHONPATH
export LD_LIBRARY_PATH=/usr/lib/qgis:$LD_LIBRARY_PATH

# Windows (adjust path to your QGIS installation):
set PYTHONPATH=C:\Program Files\QGIS 3.28\apps\qgis\python;%PYTHONPATH%

# Run script
python scripts/qgis_scripts/healthcare_qgis_clipping.py
```

---

### Option B: Manual Download in QGIS

If you prefer a GUI approach:

1. **Add ESRI Living Atlas Layer**:
   - In QGIS, go to `Layer` → `Add Layer` → `Add ArcGIS REST Server Layer`
   - URL: `https://livingatlas.esri.in/server1/rest/services/Health/IN_HealthcareFacility/MapServer`
   - Click `Connect` → Select layer → `Add`

2. **Load Your Boundary**:
   - `Layer` → `Add Layer` → `Add Vector Layer`
   - Select your `{state}_subdistricts.geojson`

3. **Clip Infrastructure to Boundary**:
   - Go to `Vector` → `Geoprocessing Tools` → `Clip`
   - **Input layer**: Healthcare facility layer
   - **Overlay layer**: Your state boundary
   - **Output**: Save as `BharatMaps_HealthCenters.geojson` in `Sources/BHARATMAPS/data/RawData/`

4. **Repeat for other datasets**:
   - Schools: `https://livingatlas.esri.in/server1/rest/services/Education/IN_Schools/MapServer`
   - Roads: `https://livingatlas.esri.in/server1/rest/services/Transportation/IN_Roads/MapServer`
   - Railways: `https://livingatlas.esri.in/server1/rest/services/Transportation/IN_Railways/MapServer`

---

## Step 2: Calculate Statistics

Once you have all raw GeoJSON files in `Sources/BHARATMAPS/data/RawData/`, run the Python analysis scripts.

### Prerequisites

Ensure your directory structure is set up:
```
Sources/BHARATMAPS/data/
├── RawData/
│   ├── BharatMaps_HealthCenters.geojson  ✓
│   ├── BharatMaps_Schools.geojson        ✓
│   ├── BharatMaps_Roads.geojson          ✓
│   └── BharatMaps_Rails.geojson          ✓
Maps/Geojson/
└── {state}_subdistricts.geojson          ✓
```

### Run Analysis Scripts

Navigate to your project directory and run:

#### 1. Calculate Schools per Subdistrict
```bash
python scripts/schools_per_sub.py
```

**Output**: `Sources/BHARATMAPS/data/variables/Schools/Schools.csv`

**Columns**:
- `object_id` or `id`: Subdistrict ID
- `sdtname` or `name`: Subdistrict name
- `schools_count`: Number of schools
- `state`: State name

---

#### 2. Calculate Healthcare Centers per Subdistrict
```bash
python scripts/healthcentres_per_sub.py
```

**Output**: `Sources/BHARATMAPS/data/variables/HealthCenters/HealthCenters.csv`

**Columns**:
- `object_id`: Subdistrict ID
- `sdtname`: Subdistrict name
- `health_centres_count`: Number of healthcare facilities
- `state`: State name

---

#### 3. Calculate Road Lengths per Subdistrict
```bash
python scripts/roads_per_sub.py
```

**Output**: `Sources/BHARATMAPS/data/variables/RoadLengths/RoadLengths.csv`

**Columns**:
- `object_id`: Subdistrict ID
- `sdtname`: Subdistrict name
- `total_road_length_km`: Total road length in kilometers
- `road_segment_count`: Number of road segments
- `state`: State name
- `road_density` (if available): km of road per km²

---

#### 4. Calculate Railway Lengths per Subdistrict
```bash
python scripts/rails_per_sub.py
```

**Output**: `Sources/BHARATMAPS/data/variables/RailLengths/RailLengths.csv`

**Columns**:
- `object_id`: Subdistrict ID
- `sdtname`: Subdistrict name
- `total_rail_length_km`: Total railway length in kilometers
- `rail_segment_count`: Number of railway segments
- `state`: State name

