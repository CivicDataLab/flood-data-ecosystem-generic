"""
Tender Block-Level Geo-Tagging Script
=======================================
For each district, matches tender text against villages, blocks/sub-districts,
gram panchayats and sub-districts to assign block-level geography.

Auto-detects whether the villages GeoJSON uses:
  - 'block_name' only
  - 'sdtname' only
  - both (block_name = primary, sdtname = fallback / sub-district tier)

Input  : floodtenders_districtgeotagged.csv  (output of geocode_tenders.py)
Output : floodtenders_blockgeotagged.csv
"""

import os
import re
import glob
import warnings
import pandas as pd
import geopandas as gpd
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────

# Villages CSV (converted from GeoJSON in the previous script)
vil_path = glob.glob(os.path.join(os.getcwd(), 'Maps', 'Geojson', '*_villages.csv'))
if not vil_path:
    raise FileNotFoundError("No CSV found under Maps/Geojson/ — run geocode_tenders.py first.")
OD_VILLAGES = pd.read_csv(vil_path[0], encoding='utf-8').dropna()
print(f"Villages loaded  →  {OD_VILLAGES.shape[0]} rows")

# Sub-districts GeoJSON (for geometry if needed downstream; attributes used here)
subdistrict_files = glob.glob(os.path.join(os.getcwd(), 'Maps', 'Geojson', '*_subdistricts.geojson'))
if subdistrict_files:
    OD_SUB = gpd.read_file(subdistrict_files[0])
    print(f"Sub-districts loaded  →  {OD_SUB.shape[0]} rows")
else:
    OD_SUB = None
    print("No *_subdistricts.geojson found — sub-district geometry not loaded.")

# District-tagged tenders
tenders_path = os.path.join(
    os.getcwd(), 'Sources', 'TENDERS', 'data', 'floodtenders_districtgeotagged.csv'
)
tenders_df = pd.read_csv(tenders_path, keep_default_na=False)
print(f"Tenders loaded   →  {tenders_df.shape[0]} rows\n")


# ─────────────────────────────────────────────────────────────
# 2. AUTO-DETECT AVAILABLE COLUMNS
#    Determines which sub-district / block column(s) exist and
#    sets HAS_BLOCK, HAS_SDT, SUB_COL, FALLBACK_COL accordingly.
# ─────────────────────────────────────────────────────────────

DISTRICT_COL = 'dtname'
HAS_BLOCK    = 'block_name' in OD_VILLAGES.columns
HAS_SDT      = 'sdtname'    in OD_VILLAGES.columns
HAS_GP       = 'gp_name'    in OD_VILLAGES.columns
HAS_VILLAGE  = 'vilnam_soi' in OD_VILLAGES.columns

if HAS_BLOCK and HAS_SDT:
    SUB_COL      = 'block_name'
    FALLBACK_COL = 'sdtname'
    print(" Both 'block_name' and 'sdtname' present.")
    print("     Primary sub-unit  : block_name")
    print("     Fallback sub-unit : sdtname")

elif HAS_BLOCK:
    SUB_COL      = 'block_name'
    FALLBACK_COL = None
    print("Only 'block_name' present — using as sole sub-district column.")

elif HAS_SDT:
    SUB_COL      = 'sdtname'
    FALLBACK_COL = None
    print("Only 'sdtname' present — using as sole sub-district column.")

else:
    raise ValueError(
        "GeoJSON has neither 'block_name' nor 'sdtname'.\n"
        "Available columns: " + str(list(OD_VILLAGES.columns))
    )

print(f"   HAS_GP={HAS_GP}  |  HAS_VILLAGE={HAS_VILLAGE}\n")


# ─────────────────────────────────────────────────────────────
# 3. NOISE REMOVAL HELPERS
# ─────────────────────────────────────────────────────────────

# Strings to strip from place names before matching
NOISE_SUBSTRINGS = ["(pt)", "\n", "("]
NOISE_PATTERN    = "|".join(map(re.escape, NOISE_SUBSTRINGS))

# Village names that are too generic to be useful
SKIP_VILLAGES = {'RIVER', 'NO', 'TOWN', 'FOREST', 'HILL', 'CANAL'}

def clean_place_name(name: str) -> str:
    """Lowercase, remove noise patterns and extra whitespace."""
    name = str(name).lower()
    name = re.sub(NOISE_PATTERN, ' ', name)
    return name.strip()

def clean_tender_slug(text: str) -> str:
    """Keep only alphanumeric + spaces from a tender text field."""
    return re.sub(r'[^a-zA-Z0-9 \n\.]', ' ', str(text))

def word_in_slug(word: str, slug: str) -> bool:
    """True if `word` appears as a whole word in `slug`."""
    return bool(re.search(r'\b' + re.escape(word.strip()) + r'\b', slug.lower()))


# ─────────────────────────────────────────────────────────────
# 4. BUILD PER-DISTRICT LOOKUP DICTIONARIES
#    Called once per district inside the main loop.
#    Adapts to whichever columns are available.
# ─────────────────────────────────────────────────────────────

def build_district_lookups(district_df: pd.DataFrame) -> dict:
    """
    Given the rows for one district, build:
      - village_dict   { village_name  → {village_id, block/sdt, gp, dtname} }
      - sub_dict       { block/sdt name → {dtname, sdtname (if fallback)} }
      - fallback_dict  { sdtname → {dtname} }  — only when both cols present
      - gp_dict        { gp_name → {dtname} }  — only when gp_name present
    """
    village_dict  = {}
    sub_dict      = {}
    fallback_dict = {}
    gp_dict       = {}

    for _, row in district_df.iterrows():

        # ── Village ──
        if HAS_VILLAGE and row.get('vilnam_soi'):
            vname = re.sub(r'[^a-zA-Z]', '', str(row['vilnam_soi'])).upper()
            if vname and vname not in SKIP_VILLAGES:
                entry = {
                    'village_id': row.get('objectid', ''),
                    'dtname':     row[DISTRICT_COL],
                }
                if HAS_BLOCK:
                    entry['block_name'] = row.get('block_name', '')
                if HAS_SDT:
                    entry['sdtname'] = row.get('sdtname', '')
                if HAS_GP:
                    entry['gp_name'] = row.get('gp_name', '')
                village_dict[vname] = entry

        # ── Primary sub-unit (block_name or sdtname) ──
        sub_val = row.get(SUB_COL, '')
        if pd.notna(sub_val) and sub_val:
            entry = {'dtname': row[DISTRICT_COL]}
            if FALLBACK_COL:
                entry['sdtname'] = row.get(FALLBACK_COL, '')
            sub_dict[str(sub_val)] = entry

        # ── Fallback sub-unit (sdtname when block_name is primary) ──
        if FALLBACK_COL:
            fb_val = row.get(FALLBACK_COL, '')
            if pd.notna(fb_val) and fb_val:
                fallback_dict[str(fb_val)] = {'dtname': row[DISTRICT_COL]}

        # ── Gram Panchayat ──
        if HAS_GP:
            gp_val = row.get('gp_name', '')
            if pd.notna(gp_val) and gp_val:
                gp_dict[str(gp_val)] = {'dtname': row[DISTRICT_COL]}

    return {
        'villages':  village_dict,
        'sub':       sub_dict,
        'fallback':  fallback_dict,
        'gp':        gp_dict,
    }


# ─────────────────────────────────────────────────────────────
# 5. MATCH A SINGLE TENDER ROW
#    Returns a dict of matched geographic fields.
# ─────────────────────────────────────────────────────────────

def match_tender(row, lookups: dict) -> dict:
    """
    Matches a tender row against the district's lookup dictionaries.
    Returns a dict with keys: tender_villages, tender_block,
    tender_subdistrict, tender_gp, tender_block_location.
    """
    tender_slug = clean_tender_slug(
        str(row.get('tender_externalreference', '')) + ' ' +
        str(row.get('tender_title', ''))             + ' ' +
        str(row.get('Work Description', ''))
    )

    tender_villages      = []
    tender_block         = ''
    tender_subdistrict   = ''
    tender_gp            = ''
    tender_block_location = ''

    # ── Match villages ──
    for vname, vdata in lookups['villages'].items():
        if not re.search(r'[a-zA-Z]', vname):
            continue
        vname_clean = re.sub(r"[\[\]]", '', vname)
        if word_in_slug(clean_place_name(vname_clean), tender_slug):
            tender_villages.append(vname_clean)
            # Village gives us block/sdt
            if HAS_BLOCK and vdata.get('block_name'):
                tender_block = vdata['block_name']
            elif HAS_SDT and vdata.get('sdtname'):
                tender_subdistrict = vdata['sdtname']
            if HAS_GP and vdata.get('gp_name'):
                tender_gp = vdata['gp_name']

    # ── Match primary sub-unit (block or sdt) ──
    for sub_name, sub_data in lookups['sub'].items():
        if word_in_slug(clean_place_name(sub_name), tender_slug):
            if SUB_COL == 'block_name':
                tender_block_location = sub_name
                if not tender_block:
                    tender_block = sub_name
                if FALLBACK_COL and sub_data.get('sdtname'):
                    tender_subdistrict = sub_data['sdtname']
            else:
                # SUB_COL is sdtname
                tender_subdistrict = sub_name
            break

    # ── Match fallback sub-unit (sdtname when block is primary) ──
    if FALLBACK_COL and not tender_subdistrict:
        for fb_name in lookups['fallback']:
            if word_in_slug(clean_place_name(fb_name), tender_slug):
                tender_subdistrict = fb_name
                break

    # ── Match Gram Panchayat ──
    if HAS_GP and not tender_gp:
        for gp_name in lookups['gp']:
            if word_in_slug(clean_place_name(gp_name), tender_slug):
                tender_gp = gp_name
                break

    return {
        'tender_villages':       str(tender_villages)[1:-1],
        'tender_block':          tender_block,
        'tender_subdistrict':    tender_subdistrict,
        'gp':                    tender_gp,
        'tender_block_location': tender_block_location,
    }


# ─────────────────────────────────────────────────────────────
# 6. MAIN LOOP — Process each district
# ─────────────────────────────────────────────────────────────

MASTER_DFs = []

for FOCUS_DISTRICT in tqdm(OD_VILLAGES[DISTRICT_COL].unique(), desc="Districts"):

    # Build lookups for this district only
    district_rows = OD_VILLAGES[OD_VILLAGES[DISTRICT_COL] == FOCUS_DISTRICT]
    lookups       = build_district_lookups(district_rows)

    # Filter tenders to this district
    district_tenders = tenders_df[tenders_df['DISTRICT_FINALISED'] == FOCUS_DISTRICT].copy()

    if district_tenders.empty:
        continue

    # Apply matching row-by-row and expand results into columns
    results = district_tenders.apply(lambda row: match_tender(row, lookups), axis=1)
    results_df = pd.DataFrame(results.tolist(), index=district_tenders.index)

    district_tenders = pd.concat([district_tenders, results_df], axis=1)
    MASTER_DFs.append(district_tenders)

# Append unmatched rows (NA / CONFLICT districts) without geo fields
unmatched = tenders_df[tenders_df['DISTRICT_FINALISED'].isin(['NA', 'CONFLICT'])].copy()
for col in ['tender_villages', 'tender_block', 'tender_subdistrict', 'gp', 'tender_block_location']:
    unmatched[col] = ''
MASTER_DFs.append(unmatched)

MASTER_DF = pd.concat(MASTER_DFs, ignore_index=True)
print(f"\naMatching complete  →  {len(MASTER_DF)} total rows")


# ─────────────────────────────────────────────────────────────
# 7. BLOCK FINALISATION
#    Resolves tender_block vs tender_block_location into one
#    authoritative BLOCK_FINALISED column.
#    Logic:
#      - Start with tender_block_location (matched from slug directly)
#      - Fall back to tender_block (inferred via village match)
#      - If both match → use either (they agree)
#    When only sdtname exists, BLOCK_FINALISED = tender_subdistrict.
# ─────────────────────────────────────────────────────────────

def finalise_block(row) -> str:
    loc   = str(row.get('tender_block_location', '')).strip()
    block = str(row.get('tender_block', '')).strip()
    sdt   = str(row.get('tender_subdistrict', '')).strip()

    if SUB_COL == 'block_name':
        # Prefer the location-matched block; fall back to village-inferred block
        if loc:
            return loc
        if block:
            return block
        # Last resort: use sub-district
        return sdt
    else:
        # No block column at all — use sub-district as the finest grain
        return sdt

MASTER_DF['BLOCK_FINALISED'] = MASTER_DF.apply(finalise_block, axis=1)
print(f"   BLOCK_FINALISED filled for {(MASTER_DF['SUB_FINALISED'] != '').sum()} rows")


# ─────────────────────────────────────────────────────────────
# 8. SAVE OUTPUT
# ─────────────────────────────────────────────────────────────

output_path = os.path.join(
    os.getcwd(),
    'Sources', 'TENDERS', 'data',
    'floodtenders_blockgeotagged.csv'
)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
MASTER_DF.to_csv(output_path, index=False)
print(f"\n Output saved → {output_path}")
