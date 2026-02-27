"""
Tender Variable Export Script
================================
Merges block-geotagged tenders with sub-district GeoJSON geometry,
then exports monthly CSVs for each variable type:
  1. Total awarded value
  2. Scheme-wise awarded value
  3. Response-type-wise awarded value

Auto-detects whether the GeoJSON uses 'block_name', 'sdtname', or both,
and sets the merge key on the right side accordingly — consistent with
geocode_tenders.py and block_geocode_tenders.py.
"""

import os
import re
import glob
import warnings
import pandas as pd
import geopandas as gpd

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────

data_path = os.path.join(os.getcwd(), 'Sources', 'TENDERS', 'data') + os.sep

# Sub-districts GeoJSON
geojson_files = glob.glob(os.path.join(os.getcwd(), 'Maps', 'Geojson', '*_subdistricts.geojson'))
if not geojson_files:
    raise FileNotFoundError("No *_subdistricts.geojson found under Maps/Geojson/")
od_gdf = gpd.read_file(geojson_files[0])
print(f"GeoJSON loaded   →  {od_gdf.shape[0]} rows  |  {geojson_files[0]}")

# Block-geotagged tenders
tenders_path = os.path.join(data_path, 'floodtenders_blockgeotagged.csv')
flood_df = pd.read_csv(tenders_path, keep_default_na=False)
print(f"Tenders loaded   →  {flood_df.shape[0]} rows")


# ─────────────────────────────────────────────────────────────
# 2. AUTO-DETECT SUB-DISTRICT COLUMN IN GeoJSON
#    Same logic as geocode_tenders.py and block_geocode_tenders.py.
#    Sets SUB_COL (primary) and FALLBACK_COL (secondary, may be None).
#    The merge right-key uses SUB_COL to join BLOCK_FINALISED.
# ─────────────────────────────────────────────────────────────

HAS_BLOCK = 'block_name' in od_gdf.columns
HAS_SDT   = 'sdtname'    in od_gdf.columns

if HAS_BLOCK and HAS_SDT:
    SUB_COL      = 'block_name'
    FALLBACK_COL = 'sdtname'
    print("Both 'block_name' and 'sdtname' found in GeoJSON.")
    print("     Primary merge key  : block_name")
    print("     Fallback key       : sdtname")

elif HAS_BLOCK:
    SUB_COL      = 'block_name'
    FALLBACK_COL = None
    print("Column detected: 'block_name' → merge key = block_name")

elif HAS_SDT:
    SUB_COL      = 'sdtname'
    FALLBACK_COL = None
    print("Column detected: 'sdtname' → merge key = sdtname")

else:
    raise ValueError(
        "GeoJSON has neither 'block_name' nor 'sdtname'.\n"
        "Available columns: " + str(list(od_gdf.columns))
    )

print(f"   Merging tenders on BLOCK_FINALISED ↔ GeoJSON '{SUB_COL}'\n")


# ─────────────────────────────────────────────────────────────
# 3. MERGE TENDERS WITH GEODATAFRAME
#    Left-join on [district, block/sdt] so every tender row
#    is kept even if no geometry match is found.
#    If primary merge yields low coverage, retry on fallback.
# ─────────────────────────────────────────────────────────────

def do_merge(df: pd.DataFrame, gdf: gpd.GeoDataFrame, sub_col: str) -> pd.DataFrame:
    """Merge tenders df with gdf on district + sub_col."""
    return df.merge(
        gdf,
        left_on=['DISTRICT_FINALISED', 'BLOCK_FINALISED'],
        right_on=['dtname', sub_col],
        how='left'
    )

merged = do_merge(flood_df, od_gdf, SUB_COL)

# If primary merge leaves most rows unmatched AND a fallback exists, try fallback
if FALLBACK_COL:
    primary_match_rate = merged['object_id'].notna().mean()
    print(f"   Primary merge match rate  : {primary_match_rate*100:.1f}%")
    if primary_match_rate < 0.5:
        print(f"   ⚠️  Low match rate — retrying merge with fallback '{FALLBACK_COL}'…")
        merged_fb = do_merge(flood_df, od_gdf, FALLBACK_COL)
        fb_match_rate = merged_fb['object_id'].notna().mean()
        print(f"   Fallback merge match rate : {fb_match_rate*100:.1f}%")
        if fb_match_rate > primary_match_rate:
            print(f"Using fallback merge ('{FALLBACK_COL}' gave better coverage).")
            merged = merged_fb
        else:
            print(f" Keeping primary merge ('{SUB_COL}' gave equal or better coverage).")
    else:
        print(f"Primary merge accepted.")

flood_tenders_geotagged_df = merged
print(f"   Merged shape: {flood_tenders_geotagged_df.shape}\n")


# ─────────────────────────────────────────────────────────────
# 4. CLEAN AWARDED VALUE COLUMN
# ─────────────────────────────────────────────────────────────

# Rename the rupee column regardless of encoding of ₹
rupee_col = [c for c in flood_tenders_geotagged_df.columns if 'Awarded' in c and 'Price' in c]
if rupee_col:
    flood_tenders_geotagged_df.rename(columns={rupee_col[0]: 'Awarded Value'}, inplace=True)
elif 'Awarded Value' not in flood_tenders_geotagged_df.columns:
    raise KeyError("Could not find 'Awarded Price' column. Available: "
                   + str(list(flood_tenders_geotagged_df.columns)))

flood_tenders_geotagged_df['Awarded Value'] = (
    flood_tenders_geotagged_df['Awarded Value']
    .astype(str)
    .str.replace(',', '', regex=False)
    .str.strip()
    .replace('', '0')
    .astype(float)
)
print(f"'Awarded Value' cleaned. Non-zero rows: "
      f"{(flood_tenders_geotagged_df['Awarded Value'] > 0).sum()}")


# ─────────────────────────────────────────────────────────────
# 5. HELPER — Save monthly variable CSVs
# ─────────────────────────────────────────────────────────────

def sanitize_varname(name: str) -> str:
    """Make a string safe to use as a folder/file name."""
    return re.sub(r'[<>:"/\\|?*₹,\n\r\t ]', '_', str(name)).strip('_')


def save_variable_monthly(variable_df: pd.DataFrame, variable_name: str, base_path: str):
    """
    Groups by month and saves one CSV per month under:
        base_path/variables/<variable_name>/<variable_name>_<year_month>.csv
    Creates the folder if it doesn't exist.
    """
    var_folder = os.path.join(base_path, 'variables', variable_name)
    os.makedirs(var_folder, exist_ok=True)

    for year_month in variable_df['month'].unique():
        monthly = variable_df[variable_df['month'] == year_month][['object_id', variable_name]]
        out_file = os.path.join(var_folder, f"{variable_name}_{year_month}.csv")
        monthly.to_csv(out_file, index=False)

    print(f"'{variable_name}'  →  {variable_df['month'].nunique()} monthly file(s) saved.")


# ─────────────────────────────────────────────────────────────
# 6. EXPORT VARIABLES
# ─────────────────────────────────────────────────────────────

GROUP_COLS = ['month', 'object_id']

# ── 6a. Total awarded value ──
var_name = 'total_tender_awarded_value'
agg_df   = (
    flood_tenders_geotagged_df
    .groupby(GROUP_COLS)[['Awarded Value']]
    .sum()
    .reset_index()
    .rename(columns={'Awarded Value': var_name})
)
save_variable_monthly(agg_df, var_name, data_path)


# ── 6b. Scheme-wise awarded value ──
if 'Scheme' in flood_tenders_geotagged_df.columns:
    print("\nExporting scheme-wise variables…")
    for scheme in flood_tenders_geotagged_df['Scheme'].dropna().unique():
        scheme_df  = flood_tenders_geotagged_df[flood_tenders_geotagged_df['Scheme'] == scheme]
        var_name   = sanitize_varname(str(scheme)) + '_tenders_awarded_value'
        agg_df     = (
            scheme_df
            .groupby(GROUP_COLS)[['Awarded Value']]
            .sum()
            .reset_index()
            .rename(columns={'Awarded Value': var_name})
        )
        save_variable_monthly(agg_df, var_name, data_path)
else:
    print("'Scheme' column not found — skipping scheme-wise export.")


# ── 6c. Response-type-wise awarded value ──
if 'Response Type' in flood_tenders_geotagged_df.columns:
    print("\nExporting response-type-wise variables…")
    for resp_type in flood_tenders_geotagged_df['Response Type'].dropna().unique():
        resp_df  = flood_tenders_geotagged_df[flood_tenders_geotagged_df['Response Type'] == resp_type]
        var_name = sanitize_varname(str(resp_type)) + '_tenders_awarded_value'
        agg_df   = (
            resp_df
            .groupby(GROUP_COLS)[['Awarded Value']]
            .sum()
            .reset_index()
            .rename(columns={'Awarded Value': var_name})
        )
        save_variable_monthly(agg_df, var_name, data_path)
else:
    print("Response Type' column not found — skipping response-type-wise export.")

