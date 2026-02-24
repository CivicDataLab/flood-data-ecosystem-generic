# Map Exporter - NIC Admin Boundaries Downloader

## Overview

This script automatically downloads administrative boundary data for Indian states from the National Informatics Centre (NIC) ArcGIS server and exports them as GeoJSON files. It retrieves state, district, subdistrict, and village-level boundaries and clips them precisely to the selected state's extent.

## Features

- Downloads boundaries from official NIC admin2024 layer
-  Retrieves 4 administrative levels:
  - State boundary
  - District boundaries
  - Subdistrict (Block/Tehsil) boundaries
  - Village boundaries
- Automatic spatial clipping to state extent
- Exports in GeoJSON format (EPSG:4326)
- Handles pagination for large datasets
- Error handling with helpful feedback 

## Data Source

**NIC ArcGIS REST Service:**
```
https://webgis1.nic.in/nicstreet/rest/services/admin2024/MapServer/
```

**Layer Information:**
- Layer 9: State Boundaries (`stname` field)
- Layer 10: District Boundaries
- Layer 11: Subdistrict Boundaries
- Layer 12: Village Boundaries

## Prerequisites

### Required Python Packages
```bash
pip install geopandas requests
```

**Dependencies:**
- `geopandas` >= 0.10.0
- `requests` >= 2.25.0
- `pandas` >= 1.3.0
- `shapely` >= 1.7.0

## Usage

### Basic Usage
```bash
python map_exporter.py --state "Assam"
```

### Specify Output Directory
```bash
python download_boundaries.py --state "Bihar" --outdir /path/to/output
```

### Configuration in Script

Alternatively, edit the configuration section in the script:
 Run simply:
```bash
python map_exporter.py
```

## Output Files

The script generates 4 GeoJSON files per state:

| File Name | Description | Layer |
|-----------|-------------|-------|
| `{state}_state.geojson` | State boundary polygon | Layer 9 |
| `{state}_districts.geojson` | All districts within state | Layer 10 |
| `{state}_subdistricts.geojson` | All subdistricts/blocks within state | Layer 11 |
| `{state}_villages.geojson` | All villages within state | Layer 12 |

**Example for Assam:**
```
Maps/Geojson/
├── assam_state.geojson
├── assam_districts.geojson
├── assam_subdistricts.geojson
└── assam_villages.geojson
```

## Valid State Names

The script accepts official state names as per NIC admin2024 layer:

- Andhra Pradesh
- Arunachal Pradesh
- Assam
- Bihar
- Chhattisgarh
- Goa
- Gujarat
- Haryana
- Himachal Pradesh
- Jharkhand
- Karnataka
- Kerala
- Madhya Pradesh
- Maharashtra
- Manipur
- Meghalaya
- Mizoram
- Nagaland
- Odisha
- Punjab
- Rajasthan
- Sikkim
- Tamil Nadu
- Telangana
- Tripura
- Uttar Pradesh
- Uttarakhand
- West Bengal
- Andaman and Nicobar Islands
- Chandigarh
- Dadra and Nagar Haveli and Daman and Diu
- Delhi
- Jammu and Kashmir
- Ladakh
- Lakshadweep
- Puducherry

**Note:** State names are case-insensitive. If you enter an invalid name, the script will display a list of valid options.

## How It Works

### Processing Pipeline
```
┌─────────────────────────────────────────────────────────────┐
│ 1. Query State Boundary (Layer 9)                          │
│    ↓                                                        │
│ 2. Calculate Bounding Box                                  │
│    ↓                                                        │
│ 3. Query Districts within Bounding Box (Layer 10)          │
│    ↓                                                        │
│ 4. Clip Districts to Exact State Boundary                  │
│    ↓                                                        │
│ 5. Query Subdistricts within Bounding Box (Layer 11)       │
│    ↓                                                        │
│ 6. Clip Subdistricts to Exact State Boundary               │
│    ↓                                                        │
│ 7. Query Villages within Bounding Box (Layer 12)           │
│    ↓                                                        │
│ 8. Clip Villages to Exact State Boundary                   │
│    ↓                                                        │
│ 9. Export All Layers as GeoJSON                            │
└─────────────────────────────────────────────────────────────┘
```

### Key Functions

#### `arcgis_query_geojson()`
Queries the ArcGIS REST API with automatic pagination support for large datasets.

**Parameters:**
- `layer_id`: Layer number (9, 10, 11, or 12)
- `where`: SQL WHERE clause (default: "1=1")
- `geometry`: Bounding box for spatial filter
- `geometry_type`: Geometry type (e.g., "esriGeometryEnvelope")

#### `shapely_to_ee()`
Converts Shapely geometries to Earth Engine-compatible format.

#### `fetch_distinct_state_names()`
Retrieves list of all valid state names from the API.

## Example Output
```
Downloading boundaries for: Assam
Output directory: /home/user/Maps/Geojson
--------------------------------------------------
Fetching state boundary...
✓ Saved: /home/user/Maps/Geojson/assam_state.geojson
Fetching districts...
✓ Saved: /home/user/Maps/Geojson/assam_districts.geojson
Fetching subdistricts...
✓ Saved: /home/user/Maps/Geojson/assam_subdistricts.geojson
Fetching villages (this may take a while)...
✓ Saved: /home/user/Maps/Geojson/assam_villages.geojson
--------------------------------------------------
SUCCESS! All files downloaded:
  - /home/user/Maps/Geojson/assam_state.geojson
  - /home/user/Maps/Geojson/assam_districts.geojson
  - /home/user/Maps/Geojson/assam_subdistricts.geojson
  - /home/user/Maps/Geojson/assam_villages.geojson
```

## Performance Considerations

### Processing Time

| Administrative Level | Typical Feature Count | Approx. Time |
|---------------------|----------------------|--------------|
| State | 1 | < 5 seconds |
| Districts | 10-75 | 10-30 seconds |
| Subdistricts | 50-500 | 30-90 seconds |
| Villages | 1,000-50,000 | 2-15 minutes |

**Note:** Village-level data may take longer for large states due to high feature counts.

