"""
WorldPopDataFetcher - Interactive Version
- Uses WorldPop SDI advanced API (https://api.worldpop.org/v1/services)
- Supports datasets: wpgppop (total pop) and wpgpas (age-sex pyramid)
- Handles async tasks (/tasks/{taskid}) with polling + exponential backoff
- Geometry simplification + coordinate truncation to avoid payload-too-large (413)
"""

import os
import json
import time
import logging
import requests
from pathlib import Path
from shapely.geometry import shape, mapping

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_YEAR = "2020"

# Base data directory — single source of truth
BASE_DATA_DIR = Path(os.getcwd()) / "Sources" / "WORLDPOP" / "data"


class WorldPopDataFetcher:
    def __init__(
        self,
        dataset,
        base_url="https://api.worldpop.org/v1",
        year=DEFAULT_YEAR,
        output_dir=None,
        api_key=None,
        simplify_tolerance=0.01,
        truncate_precision=None,
        async_threshold=1500,
    ):
        """
        Initialize WorldPop data fetcher.
        
        Args:
            dataset (str): Dataset identifier ('wpgppop' or 'wpgpas'). Required to
                           resolve the correct output directory at initialisation time.
            base_url (str): Base URL for WorldPop API
            year (str/int): Year for data retrieval
            output_dir (str/Path): Output directory for data files. If None, resolved
                                   automatically based on dataset type.
            api_key (str, optional): API key for WorldPop (if required)
            simplify_tolerance (float): Tolerance for geometry simplification
            truncate_precision (int, optional): Decimal places for coordinate truncation
            async_threshold (int): Payload size threshold (bytes) to trigger async requests
        """
        self.base_url = base_url.rstrip("/")
        self.year = str(year)
        self.dataset = dataset
        self.api_key = api_key
        self.simplify_tolerance = simplify_tolerance
        self.truncate_precision = truncate_precision
        self.async_threshold = async_threshold

        # Resolve output directory based on dataset type
        if output_dir is None:
            if dataset == "wpgpas":
                output_dir = BASE_DATA_DIR / "agesexstructure"
            else:  # wpgppop
                output_dir = BASE_DATA_DIR / "variables" / "sum_population"
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using output directory: {self.output_dir}")

    # ---------- Geometry helpers ----------
    def simplify_geometry(self, geojson, tolerance=None):
        """
        Simplify geometry to reduce payload size.
        
        Args:
            geojson (dict): GeoJSON FeatureCollection
            tolerance (float, optional): Simplification tolerance
        
        Returns:
            dict: Simplified GeoJSON
        """
        tol = tolerance if tolerance is not None else self.simplify_tolerance
        
        if "features" not in geojson or len(geojson["features"]) == 0:
            logger.warning("No features in GeoJSON to simplify")
            return geojson
        
        feature = geojson["features"][0]
        geom = shape(feature["geometry"])
        simplified = geom.simplify(float(tol), preserve_topology=True)
        feature["geometry"] = mapping(simplified)
        
        return geojson

    def truncate_coordinates(self, geojson, precision=None):
        """
        Round coordinates to specified precision to reduce payload size.
        
        Args:
            geojson (dict): GeoJSON FeatureCollection
            precision (int, optional): Number of decimal places
        
        Returns:
            dict: GeoJSON with truncated coordinates
        """
        if precision is None:
            precision = self.truncate_precision
        if precision is None:
            return geojson

        def _trunc(x):
            return round(float(x), precision)

        feature = geojson["features"][0]
        geom_type = feature["geometry"]["type"]
        coords = feature["geometry"]["coordinates"]

        if geom_type == "Polygon":
            feature["geometry"]["coordinates"] = [
                [[_trunc(x) for x in pt] for pt in ring] 
                for ring in coords
            ]
        elif geom_type == "MultiPolygon":
            feature["geometry"]["coordinates"] = [
                [[[_trunc(x) for x in pt] for pt in ring] for ring in poly] 
                for poly in coords
            ]
        else:
            logger.warning(f"Unsupported geometry type for truncation: {geom_type}")

        return geojson

    def _prepare_geojson(self, geojson_path):
        """
        Load, simplify, and optionally truncate geometry.
        
        Args:
            geojson_path (str/Path): Path to GeoJSON file
        
        Returns:
            tuple: (geojson_dict, geojson_string)
        """
        with open(geojson_path, "r", encoding="utf-8") as fh:
            gj = json.load(fh)

        if "features" not in gj or len(gj["features"]) == 0:
            raise ValueError("GeoJSON must be a FeatureCollection with at least one feature")

        gj = self.simplify_geometry(gj, tolerance=self.simplify_tolerance)

        if self.truncate_precision is not None:
            gj = self.truncate_coordinates(gj, precision=self.truncate_precision)

        geojson_str = json.dumps(gj, separators=(",", ":"))
        
        return gj, geojson_str

    # ---------- API helpers ----------
    def _build_params(self, dataset, year, geojson_str, runasync):
        """
        Build query parameters for API request.
        
        Args:
            dataset (str): Dataset identifier (wpgppop or wpgpas)
            year (str): Year for data
            geojson_str (str): JSON string of geometry
            runasync (bool): Whether to run asynchronously
        
        Returns:
            dict: Query parameters
        """
        params = {
            "dataset": dataset,
            "year": str(year),
            "geojson": geojson_str,
            "runasync": "true" if runasync else "false",
        }
        if self.api_key:
            params["key"] = self.api_key
        return params

    def _poll_task(self, task_id, max_attempts=20, initial_delay=2.0, max_delay=60.0):
        """
        Poll task status endpoint with exponential backoff.
        
        Args:
            task_id (str): Task identifier
            max_attempts (int): Maximum polling attempts
            initial_delay (float): Initial delay between polls (seconds)
            max_delay (float): Maximum delay between polls (seconds)
        
        Returns:
            dict or None: Task response with data or None if failed
        """
        task_url = f"{self.base_url}/tasks/{task_id}"
        attempt = 0
        delay = float(initial_delay)

        while attempt < max_attempts:
            logger.info(f"Polling task {task_id} (attempt {attempt + 1}/{max_attempts})")
            
            try:
                resp = requests.get(task_url, timeout=30)
                
                if resp.status_code == 413:
                    logger.error("Task status endpoint returned 413: Payload too large")
                    return None
                
                resp.raise_for_status()
                j = resp.json()
                
            except requests.RequestException as e:
                logger.warning(f"Polling request failed: {e}. Retrying after {delay:.1f}s")
                time.sleep(delay)
                attempt += 1
                delay = min(delay * 2, max_delay)
                continue

            status = j.get("status")
            
            if status == "finished":
                logger.info(f"Task {task_id} finished successfully")
                return j
            
            if status == "failed":
                error_msg = j.get("error_message", "Unknown error")
                logger.error(f"Task {task_id} failed: {error_msg}")
                return None

            logger.debug(f"Task {task_id} status: {status}. Sleeping {delay:.1f}s")
            time.sleep(delay)
            attempt += 1
            delay = min(delay * 2, max_delay)

        logger.error(f"Task {task_id} did not finish after {max_attempts} attempts")
        return None

    def _make_api_call(self, geojson, dataset, year=None, runasync=None, max_poll_attempts=20):
        """
        Make API call to WorldPop stats endpoint.
        
        Args:
            geojson (dict): GeoJSON geometry
            dataset (str): Dataset identifier
            year (str, optional): Year for data
            runasync (bool, optional): Force async mode
            max_poll_attempts (int): Maximum polling attempts for async tasks
        
        Returns:
            dict or None: API response with data or None if failed
        """
        year = str(year or self.year)
        
        geojson_str = json.dumps(geojson, separators=(",", ":"))
        if runasync is None:
            runasync = len(geojson_str) > self.async_threshold
        
        params = self._build_params(dataset, year, geojson_str, runasync)
        stats_url = f"{self.base_url}/services/stats"
        
        logger.info(f"Requesting {dataset} for year {year}. runasync={runasync}")
        logger.debug(f"Payload size: {len(geojson_str)} bytes")

        try:
            resp = requests.get(stats_url, params=params, timeout=90)
            
            if resp.status_code == 413:
                logger.error("HTTP 413: Payload too large. Try increasing simplification or truncation.")
                return None
            
            resp.raise_for_status()
            resp_json = resp.json()
            
        except requests.RequestException as e:
            logger.error(f"Request exception calling stats: {e}")
            return None

        if "taskid" in resp_json:
            task_id = resp_json["taskid"]
            logger.info(f"Got taskid {task_id}. Polling for completion...")
            return self._poll_task(task_id, max_attempts=max_poll_attempts)

        if "data" in resp_json:
            logger.info("Received data in synchronous response")
            return resp_json

        logger.error(f"Unexpected response format: {resp_json}")
        return None

    # ---------- Save helpers ----------
    def _save_population_data(self, data, year):
        """
        Save total population data to CSV.
        Filename: sum_population_{year}.csv
        
        Args:
            data (dict): API response data
            year (str): Year for data
        """
        out = self.output_dir / f"sum_population_{year}.csv"

        rows = data.get("data", {})
        total = rows.get("total_population", "N/A")
        
        with open(out, "w", newline="", encoding="utf-8") as fh:
            fh.write("total_population\n")
            fh.write(f"{total}\n")
        
        logger.info(f"Saved population totals to {out}")

    def _save_pyramid_data(self, data, district, year):
        """
        Save age-sex pyramid data to CSV.
        Filename: {object_id}_agesexpyramid_{year}.csv

        Args:
            data (dict): API response data
            district (str): object_id / subdistrict identifier
            year (str): Year for data
        """
        if not data or "data" not in data or "agesexpyramid" not in data["data"]:
            logger.error(f"No agesexpyramid in returned data for {district}")
            logger.debug(f"Full response: {data}")
            return
        
        out = self.output_dir / f"{district}_agesexpyramid_{year}.csv"
        rows = data["data"]["agesexpyramid"]
        
        with open(out, "w", newline="", encoding="utf-8") as fh:
            fh.write("class,age,male,female\n")
            for r in rows:
                cls = r.get("class", "")
                age = r.get("age", "")
                male = r.get("male", "")
                female = r.get("female", "")
                fh.write(f"{cls},{age},{male},{female}\n")
        
        logger.info(f"Saved age-sex pyramid to {out}")

    # ---------- Public method ----------
    def fetch_worldpop_data(self, geojson_path, dataset="wpgpas", year=None):
        """
        Fetch WorldPop data for a given geometry.
        
        Args:
            geojson_path (str/Path): Path to GeoJSON file
            dataset (str): Dataset identifier ('wpgppop' or 'wpgpas')
            year (str/int, optional): Year for data retrieval
        
        Returns:
            bool: True if successful, False otherwise
        """
        district = Path(geojson_path).stem
        year = str(year or self.year)
        logger.info(f"Processing {district} (dataset={dataset}, year={year})")
        
        try:
            geojson, geojson_str = self._prepare_geojson(geojson_path)

            if len(geojson_str) > 8000:
                logger.warning(f"Large payload ({len(geojson_str)} bytes). Applying stronger simplification.")
                geojson = self.simplify_geometry(geojson, tolerance=self.simplify_tolerance * 10)
                
                if self.truncate_precision is None:
                    geojson = self.truncate_coordinates(geojson, precision=3)
                
                geojson_str = json.dumps(geojson, separators=(",", ":"))
                logger.info(f"Reduced payload to {len(geojson_str)} bytes")

            resp = self._make_api_call(geojson, dataset=dataset, year=year)

            if not resp:
                logger.error(f"No valid response for {district}")
                return False

            if dataset == "wpgppop":
                self._save_population_data(resp, year)
            elif dataset == "wpgpas":
                self._save_pyramid_data(resp, district, year)
            else:
                logger.warning(f"Unrecognized dataset: {dataset}. Saving raw JSON response.")
                outfile = self.output_dir / f"{district}_{dataset}_{year}.json"
                with open(outfile, "w", encoding="utf-8") as fh:
                    json.dump(resp, fh, indent=2)
                logger.info(f"Wrote raw response to {outfile}")

            return True

        except Exception as e:
            logger.exception(f"Error processing {district}: {e}")
            return False


# ---------- Interactive CLI ----------
def get_year_input():
    """Get year from user with validation."""
    while True:
        year_input = input("\nEnter the year for data retrieval (e.g., 2020): ").strip()
        if year_input.isdigit() and 2000 <= int(year_input) <= 2030:
            return int(year_input)
        else:
            print("Invalid year. Please enter a year between 2000 and 2030.")


def get_dataset_input():
    """Get dataset choice from user with validation."""
    print("\n" + "="*70)
    print("Available Datasets")
    print("="*70)
    print("1. wpgpas  - Age-Sex Pyramid data")
    print("   • Provides demographic breakdown by age groups and gender")
    print(f"   • Output: Sources/WORLDPOP/data/agesexstructure/{{object_id}}_agesexpyramid_{{year}}.csv")
    print()
    print("2. wpgppop - Total Population data")
    print("   • Provides total population count")
    print(f"   • Output: Sources/WORLDPOP/data/variables/sum_population/sum_population_{{year}}.csv")
    print("="*70)
    
    while True:
        choice = input("\nEnter your choice (1 for wpgpas, 2 for wpgppop): ").strip()
        
        if choice == "1":
            return "wpgpas"
        elif choice == "2":
            return "wpgppop"
        elif choice.lower() in ["wpgpas", "wpgppop"]:
            return choice.lower()
        else:
            print("Invalid choice. Please enter 1, 2, 'wpgpas', or 'wpgppop'.")


def get_geojson_directory():
    """Get GeoJSON directory from user."""
    default_dir = BASE_DATA_DIR / "Scraper_data" / "Geojson_shapefiles"
    
    print(f"\nGeoJSON directory:")
    print(f"Default: {default_dir}")
    geojson_input = input("Press Enter for default or enter custom path: ").strip()
    
    if geojson_input:
        return geojson_input
    return str(default_dir)


def get_api_key():
    """Get optional API key from user."""
    print("\n" + "-"*70)
    print("API Key (optional)")
    print("-"*70)
    print("Most WorldPop API requests work without an API key.")
    print("If you have one, enter it below. Otherwise, just press Enter.")
    
    api_key_input = input("\nEnter API key or press Enter to skip: ").strip()
    return api_key_input if api_key_input else None


def confirm_settings(year, dataset, geojson_dir, api_key):
    """Display settings and get confirmation."""
    if dataset == "wpgpas":
        out_dir = f"Sources/WORLDPOP/data/agesexstructure/"
    else:
        out_dir = f"Sources/WORLDPOP/data/variables/sum_population/"

    print("\n" + "="*70)
    print("Configuration Summary")
    print("="*70)
    print(f"Year:                {year}")
    print(f"Dataset:             {dataset}")
    print(f"GeoJSON Directory:   {geojson_dir}")
    print(f"API Key:             {'Set' if api_key else 'Not set (using free tier)'}")
    print(f"Output Directory:    {out_dir}")
    print("="*70)
    
    while True:
        confirm = input("\nProceed with these settings? (yes/no): ").strip().lower()
        if confirm in ['yes', 'y']:
            return True
        elif confirm in ['no', 'n']:
            return False
        else:
            print("Please enter 'yes' or 'no'.")


def main():
    """Main function with interactive user input."""
    print("\n" + "="*70)
    print("WorldPop Data Fetcher - Interactive Mode")
    print("="*70)
    
    try:
        year = get_year_input()
        dataset = get_dataset_input()
        geojson_dir = get_geojson_directory()
        api_key = get_api_key()
        
        if not confirm_settings(year, dataset, geojson_dir, api_key):
            print("\nConfiguration cancelled. Exiting.")
            return
        
        print("\n" + "="*70)
        print("Initializing WorldPop Data Fetcher...")
        print("="*70)
        
        fetcher = WorldPopDataFetcher(
            dataset=dataset,
            year=year,
            api_key=api_key,
            simplify_tolerance=0.01,
            truncate_precision=3,
            async_threshold=10000,
            output_dir=None,  # Resolved automatically from dataset type
        )

        geojson_path = Path(geojson_dir)
        
        if not geojson_path.exists():
            logger.error(f"GeoJSON directory not found: {geojson_path}")
            return

        files = sorted(geojson_path.glob("*.geojson"))
        
        if not files:
            logger.warning(f"No GeoJSON files found in {geojson_path}")
            return
        
        logger.info(f"Found {len(files)} GeoJSON file(s)")

        print(f"\nReady to process {len(files)} file(s)")
        proceed = input("Start processing? (yes/no): ").strip().lower()
        
        if proceed not in ['yes', 'y']:
            print("\nProcessing cancelled. Exiting.")
            return

        print("\n" + "="*70)
        print("Processing Started")
        print("="*70 + "\n")
        
        success_count = 0
        failed_files = []
        
        for idx, gj in enumerate(files, 1):
            object_id = gj.stem

            # Determine expected output path for existence check
            if dataset == "wpgpas":
                expected_csv = fetcher.output_dir / f"{object_id}_agesexpyramid_{year}.csv"
            else:
                expected_csv = fetcher.output_dir / f"sum_population_{year}.csv"

            logger.info(f"[{idx}/{len(files)}] Processing: {gj.name}")
            
            if expected_csv.exists():
                logger.info(f"Output file already exists and will be replaced if fetch succeeds: {expected_csv.name}")

            success = fetcher.fetch_worldpop_data(str(gj), dataset=dataset, year=year)
            
            if success:
                success_count += 1
                logger.info(f"Successfully processed {gj.name}")
            else:
                failed_files.append(gj.name)
                logger.error(f"Failed to process {gj.name}")
            
            time.sleep(0.5)

        print("\n" + "="*70)
        print("Processing Complete!")
        print("="*70)
        print(f"Successfully processed: {success_count}/{len(files)}")
        print(f"Output directory: {fetcher.output_dir}")
        
        if failed_files:
            print(f"\nFailed files ({len(failed_files)}):")
            for f in failed_files:
                print(f"   - {f}")
            proceed_retry = input("\nRetry failed files? (yes/no): ").strip().lower()
            if proceed_retry in ['yes', 'y']:
                for filename in failed_files:
                    gj_path = geojson_path / filename
                    success = fetcher.fetch_worldpop_data(str(gj_path), dataset=dataset, year=year)
                    if success:
                        logger.info(f"Retry succeeded: {filename}")
                    else:
                        logger.error(f"Retry failed: {filename}")
        else:
            print("\nAll files processed successfully!")
        
        print("="*70 + "\n")

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user. Exiting...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()