# NASADEM Elevation and Slope Data Processing Workflow

This workflow downloads NASADEM (NASA Digital Elevation Model) data for a region of interest, calculates slope, and extracts zonal statistics for administrative boundaries using Google Earth Engine and Google Cloud Storage.

---

## Overview

This workflow performs the following operations:

1. **nasadem.py** Retreives the DEM files from GEE and stores it in the google storage bucket
2. **download_nasadem.py** Downloads the file from google storage bucket to your local path
3. **slope.py** slope from the elevation data
4. **transformer.py** zonal statistics (mean elevation and slope) for administrative boundaries (subdistricts) a CSV file with elevation and slope statistics per subdistrict

---

## Prerequisites

### Software Requirements

- Python 3.8+
- Google Cloud Account (with billing enabled)
- Google Earth Engine account

### Python Libraries
```bash
pip install earthengine-api google-cloud-storage rasterio geopandas rasterstats numpy pandas
```

### Data Requirements

- Administrative boundary shapefile (GeoJSON format) for your area of interest (e.g., Bihar subdistricts)
- Google Cloud project with billing enabled - free tier 

---

## Google Cloud Setup

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Create Project**
3. Enter:
   - **Project name**: `nasadem-project-idsdrr` (or your preferred name)
   - **Organization**: Choose your org or "No organization" (for personal accounts)
4. Click **Create**

### 2. Create a Service Account

1. Navigate to **IAM & Admin** → **Service Accounts**
2. Click **+ Create Service Account**
3. Enter:
   - **Name**: `nasadem-service-acct`
   - **ID**: Auto-fills as `nasadem-service-acct@nasadem-project-idsdrr.iam.gserviceaccount.com`
   - **Description**: "Service account for NASADEM export to GCS"
4. Click **Create and Continue**

### 3. Assign IAM Roles

Under "Grant this service account access to project," add the following roles:

- **Storage Admin** → Full access to upload, list, and download files in Cloud Storage
- **Viewer** (optional) → Read-only access to project resources
- **Earth Engine Resource Writer** (optional) → Allows Earth Engine exports

Click **Continue** → **Done**

### 4. Create and Download JSON Key

1. On the Service Account list, find your new account
2. Click the **three dots** (⋮) → **Manage Keys**
3. Select **Add Key** → **Create new key** → **JSON**
4. A JSON key file (e.g., `nasadem-project-idsdrr-bf0ff5b49ce8.json`) will download automatically
5. Move the file to a secure location:
```
   /path/to/your/credentials/nasadem-project-idsdrr-bf0ff5b49ce8.json
```

### 5. Enable Required APIs

1. Go to [API Library](https://console.cloud.google.com/apis/library)
2. Search and enable the following APIs:
   - **Earth Engine API**
   - **Google Cloud Storage JSON API**
   - **Google Cloud Storage API**
   - **Cloud Resource Manager API** (optional)

### 6. Create a Google Cloud Storage Bucket

1. Go to [Google Cloud Storage](https://console.cloud.google.com/storage)
2. Click **Create Bucket**
3. Enter:
   - **Bucket name**: `nasadem-up-exports` (must be globally unique, lowercase)
   - **Region**: `asia-south1` (Mumbai region, ideal for India-based processing)
   - **Storage class**: Standard
   - **Access control**: Uniform
   - **Retention policy**: None
4. Click **Create**

Your bucket URL will be: `gs://nasadem-up-exports`

### 7. Grant Service Account Access to the Bucket

1. Go to your bucket's **Permissions** tab
2. Click **Grant Access**
3. Add:
   - **New Principal**: `nasadem-service-acct@nasadem-project-idsdrr.iam.gserviceaccount.com`
   - **Role**: Storage Admin (or Storage Object Admin)
4. Click **Save**

### 8. Register the Cloud Project with Earth Engine

1. Go to [Earth Engine Configuration](https://code.earthengine.google.com/)
2. Select your project → `nasadem-project-idsdrr`
3. Click **Register Project**
4. Choose **Non-commercial / Research Use**
5. Accept the terms and click **Confirm**

> **Note**: Google Earth Engine and 5 GB storage are free tier, but you must enable billing to access GCS buckets.

---

## Installation

1. Clone or download this repository
2. Install required Python packages:
```bash
pip install earthengine-api google-cloud-storage rasterio geopandas rasterstats numpy pandas
```

3. Organize your project structure:
```
project/
├── credentials/
│   └── nasadem-project-idsdrr-bf0ff5b49ce8.json
├── scripts/
│   ├── nasadem.py
│   ├── download_nasadem.py
│   ├── slope.py
│   └── transformer.py
├── Maps/
│   └── Geojson/
│       └── {selected_state}_subdistricts.geojson
└── data/
    └── nasadem/
```

---

## Workflow Steps

### Step 1: Export Data from Earth Engine (`nasadem.py`)

This script exports NASADEM elevation and slope data from Google Earth Engine to your GCS bucket.

**What it does:**
- Authenticates with Google Earth Engine using your service account
- Defines the area of interest (e.g., Bihar)
- Exports elevation (DEM) and slope rasters to Google Cloud Storage
- Tasks are submitted to Earth Engine and run asynchronously

**Configuration:**

Edit the following variables in `nasadem.py`:
```python
SERVICE_ACCOUNT_EMAIL = "nasadem-service-acct@nasadem-project-idsdrr.iam.gserviceaccount.com"
JSON_KEY_PATH = "/path/to/your/nasadem-project-idsdrr-bf0ff5b49ce8.json"
PROJECT_ID = "nasadem-project-idsdrr"
BUCKET_NAME = "nasadem-up-exports"
FOLDER_PREFIX = "nasadem_exports/"
```

**Run:**
```bash
python scripts/nasadem.py
```

**Expected Output:**
- Task submission confirmations
- Files exported to `gs://nasadem-up-exports/nasadem_exports/`

---

### Step 2: Download Files from GCS (`download_nasadem.py`)

This script downloads the exported TIFF files from Google Cloud Storage to your local machine.

**What it does:**
- Authenticates with GCS using the service account JSON key
- Connects to your specified bucket
- Lists all files matching the folder prefix
- Downloads elevation and slope GeoTIFF files to a local directory

**Configuration:**

Edit the following variables in `download_nasadem.py`:
```python
SERVICE_ACCOUNT_JSON = "/path/to/your/nasadem-project-idsdrr-bf0ff5b49ce8.json"
BUCKET_NAME = "nasadem-up-exports"
FOLDER_PREFIX = "nasadem_exports/"
LOCAL_DOWNLOAD_DIR = "./data/nasadem/"
```

**Run:**
```bash
python scripts/download_nasadem.py
```

**Expected Output:**
- Downloaded files in `./data/nasadem/`:
  - `NASADEM_DEM_30.tif` (elevation)
  - `NASADEM_SLOPE_30.tif` (slope, if exported)

---

### Step 3: Calculate Slope from DEM (`slope.py`)

This script calculates slope from the elevation raster if you need to generate it locally.

**What it does:**
- Opens the NASADEM elevation GeoTIFF
- Calculates the gradient (rate of change) in X and Y directions using `np.gradient()`
- Computes slope angle in radians, then converts to degrees
- Saves the slope raster as a new GeoTIFF file

**Configuration:**

Edit the following variables in `slope.py`:
```python
DEM_PATH = "./data/nasadem/NASADEM_DEM_30.tif"
OUTPUT_SLOPE_PATH = "./data/nasadem/NASADEM_SLOPE_30.tif"
```

**Run:**
```bash
python scripts/slope.py
```

**Expected Output:**
- `NASADEM_SLOPE_30.tif` in `./data/nasadem/`

---

### Step 4: Extract Zonal Statistics (`transformer.py`)

This script extracts mean elevation and slope values for each administrative boundary (subdistrict).

**What it does:**
- Loads the administrative boundary shapefile (GeoJSON)
- Opens both elevation and slope rasters
- Uses `rasterstats.zonal_stats()` to compute mean values for each polygon
- Merges elevation and slope statistics into a single DataFrame
- Exports the results as a CSV file

**Configuration:**

Edit the following variables in `transformer.py`:
```python
NASADEM_DIR = "./data/nasadem/"
SHAPEFILE_PATH = "./Maps/Geojson/bihar_subdistricts.geojson"
OUTPUT_CSV = "./data/nasadem/elevation.csv"
```

**Run:**
```bash
python scripts/transformer.py
```

**Expected Output:**
- `elevation.csv` containing:
  - `object_id`: Unique identifier for each subdistrict
  - `elevation_mean`: Mean elevation (meters)
  - `slope_mean`: Mean slope (degrees)

---

## Output

### Final CSV Structure

| object_id | elevation_mean | slope_mean |
|-----------|---------------|------------|
| 1         | 45.3          | 2.1        |
| 2         | 78.6          | 3.5        |
| 3         | 120.4         | 5.2        |
| ...       | ...           | ...        |

### Directory Structure After Completion
```
project/
├── data/
│   └── nasadem/
│       ├── NASADEM_DEM_30.tif
│       ├── NASADEM_SLOPE_30.tif
│       └── elevation.csv
└── scripts/
    ├── nasadem.py
    ├── download_nasadem.py
    ├── slope.py
    └── transformer.py
```

---

## Troubleshooting

### Issue: "No files found in bucket"

**Solution:**
- Check that Earth Engine export tasks completed successfully in the [Earth Engine Code Editor](https://code.earthengine.google.com/)
- Verify bucket name and folder prefix are correct
- Ensure service account has proper permissions

### Issue: "Authentication failed"

**Solution:**
- Verify JSON key file path is correct
- Ensure service account has necessary IAM roles
- Check that APIs are enabled in Google Cloud Console

### Issue: "Billing must be enabled"

**Solution:**
- Go to [Google Cloud Billing](https://console.cloud.google.com/billing)
- Enable billing for your project
- Note: Earth Engine and 5 GB storage are free tier

### Issue: "Missing shapefile or raster"

**Solution:**
- Verify file paths in each script
- Ensure GeoJSON and TIFF files exist in specified directories
- Check file permissions

### Issue: "Zonal statistics returning NaN values"

**Solution:**
- Verify that shapefile and raster CRS (coordinate reference systems) match or are properly transformed
- Check that polygon boundaries overlap with raster extent
- Ensure nodata values are properly defined in raster metadata

---

## Notes

- **Coordinate Reference System**: NASADEM data uses EPSG:4326 (WGS84)
- **Resolution**: 30 meters (~0.00027 degrees)
- **Free Tier**: Google Earth Engine and 5 GB Cloud Storage are free, but billing must be enabled
- **Processing Time**: Earth Engine exports may take several minutes to hours depending on area size

---

## License

This workflow is for research and non-commercial use. Ensure compliance with:
- [Google Earth Engine Terms of Service](https://earthengine.google.com/terms/)
- [NASA Data Use Policy](https://www.nasa.gov/about/highlights/HP_Privacy.html)

---

## Contact

For questions or issues, please contact: [your-email@example.com]

---

## References

- [Google Earth Engine Documentation](https://developers.google.com/earth-engine)
- [NASADEM Documentation](https://lpdaac.usgs.gov/products/nasadem_hgtv001/)
- [Rasterstats Documentation](https://pythonhosted.org/rasterstats/)
- [Rasterio Documentation](https://rasterio.readthedocs.io/)