"""
Tender District Geo-Tagging Script
====================================
Matches tender records to districts using three independent signals:
  1. External Reference field
  2. Tender Title + Work Description
  3. Location field

The script auto-detects whether the GeoJSON uses 'block_name' or 'sdtname'
as the sub-district identifier and builds lookup dictionaries accordingly.

Each signal tries to match at district → block/sdtname level (in that order).
A final weightage step reconciles all signals into DISTRICT_FINALISED.
"""

import os
import re
import glob
import pandas as pd
import geopandas as gpd
from difflib import SequenceMatcher

# ─────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────

tenders_path = os.path.join(os.getcwd(), 'Sources', 'TENDERS', 'data', 'flood_tenders_all.csv')
tenders_df   = pd.read_csv(tenders_path)
csv_path =  glob.glob(os.path.join(os.getcwd(),'Maps/csv/*_villages.csv'))
OD_VILLAGES = pd.read_csv(csv_path, encoding='utf-8').dropna()
print(f"Villages loaded  →  {OD_VILLAGES.shape[0]} rows | saved at: {csv_path}")


# ─────────────────────────────────────────────────────────────
# 2. AUTO-DETECT SUB-DISTRICT COLUMN
#    Checks whether the GeoJSON has 'block_name' or 'sdtname'
#    and sets SUB_COL accordingly. Raises clearly if neither exists.
# ─────────────────────────────────────────────────────────────

DISTRICT_COL = 'dtname'   # district column — assumed constant across states

if 'block_name' in OD_VILLAGES.columns and 'sdtname' in OD_VILLAGES.columns:
    # Both present — prefer block_name but keep sdtname as fallback
    SUB_COL      = 'block_name'
    FALLBACK_COL = 'sdtname'
    print(" Both 'block_name' and 'sdtname' found → using 'block_name' as primary, 'sdtname' as fallback.")

elif 'block_name' in OD_VILLAGES.columns:
    SUB_COL      = 'block_name'
    FALLBACK_COL = None
    print(" Column detected: 'block_name'")

elif 'sdtname' in OD_VILLAGES.columns:
    SUB_COL      = 'sdtname'
    FALLBACK_COL = None
    print("Column detected: 'sdtname'")

else:
    raise ValueError(
        "GeoJSON has neither 'block_name' nor 'sdtname'. "
        "Available columns: " + str(list(OD_VILLAGES.columns))
    )

print(f"   SUB_COL = '{SUB_COL}'  |  FALLBACK_COL = '{FALLBACK_COL}'")


# ─────────────────────────────────────────────────────────────
# 3. BUILD LOOKUP DICTIONARIES  (only unambiguous mappings)
# ─────────────────────────────────────────────────────────────

def build_unique_dict(df: pd.DataFrame, key_col: str, val_col: str) -> dict:
    """
    Returns { key → district } keeping only rows where the key
    maps to exactly ONE district (ambiguous keys are dropped).
    """
    if key_col not in df.columns:
        return {}
    return (
        df[[key_col, val_col]]
        .dropna()
        .drop_duplicates()
        .drop_duplicates(subset=[key_col], keep=False)
        .set_index(key_col)[val_col]
        .to_dict()
    )

# Primary sub-district dict (block_name OR sdtname)
sub_dict     = build_unique_dict(OD_VILLAGES, SUB_COL, DISTRICT_COL)
# Fallback dict (sdtname when block_name is primary; empty otherwise)
fallback_dict = build_unique_dict(OD_VILLAGES, FALLBACK_COL, DISTRICT_COL) if FALLBACK_COL else {}
# Village dict
villages_dict = build_unique_dict(OD_VILLAGES, 'vilnam_soi', DISTRICT_COL)

# Unique name lists for matching
od_districts  = OD_VILLAGES[DISTRICT_COL].dropna().unique().tolist()
od_sub_names  = list(sub_dict.keys())
od_fb_names   = list(fallback_dict.keys())   # empty if no fallback

# Log ambiguous sub-district names that were excluded
ambiguous = (
    OD_VILLAGES[[SUB_COL, DISTRICT_COL]]
    .drop_duplicates()
    .dropna()
    .pipe(lambda df: df[df.duplicated(SUB_COL, keep=False)])
)
print(f"   Ambiguous {SUB_COL} entries excluded from matching: {ambiguous[SUB_COL].nunique()}")

# Fuzzy match candidates — prefer sdtname for fuzzy (more specific)
FUZZY_COL = FALLBACK_COL if FALLBACK_COL else SUB_COL
fuzzy_candidates = OD_VILLAGES[FUZZY_COL].dropna().unique()
print(f"   Fuzzy matching column: '{FUZZY_COL}' ({len(fuzzy_candidates)} candidates)\n")


# ─────────────────────────────────────────────────────────────
# 4. HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Lowercase, strip noise words and non-alpha characters."""
    text = str(text).lower()
    for word in ['village', 'district', 'dist', 'block']:
        text = text.replace(word, ' ')
    return re.sub(r'[^a-zA-Z\s]', ' ', text).strip()


def fuzzy_match(text: str, threshold: float = 0.80) -> str | None:
    """
    Fuzzy-match `text` against fuzzy_candidates (sdtname or block_name).
    Returns the best match name if score ≥ threshold, else None.
    """
    scores     = [SequenceMatcher(None, text, c.lower().strip()).ratio() for c in fuzzy_candidates]
    best_score = max(scores) if scores else 0
    if best_score >= threshold:
        return fuzzy_candidates[scores.index(best_score)]
    return None


def regex_match_district(slug: str) -> str | None:
    """
    Match a text slug to a district via tiers (highest → lowest specificity):
      Tier 1 — district name     (exact word-boundary)
      Tier 2 — primary sub col   (block_name or sdtname → district)
      Tier 3 — fallback sub col  (sdtname if block_name was primary)
    Returns district name or None.
    """
    slug = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(slug)).lower()

    # Tier 1 — district
    for district in od_districts:
        if re.search(r'\b' + re.escape(district.lower().strip()) + r'\b', slug):
            return district

    # Tier 2 — primary sub-district column
    for name in od_sub_names:
        if re.search(r'\b' + re.escape(name.lower().strip()) + r'\b', slug):
            return sub_dict[name]

    # Tier 3 — fallback sub-district column (if available)
    for name in od_fb_names:
        if re.search(r'\b' + re.escape(name.lower().strip()) + r'\b', slug):
            return fallback_dict[name]

    return None


# ─────────────────────────────────────────────────────────────
# 5. SIGNAL A — Location column  (fuzzy match → cleaned location)
# ─────────────────────────────────────────────────────────────

def match_location_fuzzy(location: str) -> str:
    cleaned = clean_text(location)
    match   = fuzzy_match(cleaned)
    return match if match else location

tenders_df['location_cleaned'] = tenders_df['location'].apply(match_location_fuzzy)
print("Signal A — Location fuzzy matching done.")


# ─────────────────────────────────────────────────────────────
# 6. SIGNAL B — External Reference field
# ─────────────────────────────────────────────────────────────

def extract_district_from_ref(ref) -> str | None:
    if pd.isna(ref):
        return None
    identifier = str(ref).split('/')[0].lower()
    if 'rgr' in identifier:
        identifier = identifier.split('rgr')[0].strip()
    return regex_match_district(identifier)

tenders_df['tender_district_externalReference'] = (
    tenders_df['tender_externalreference'].apply(extract_district_from_ref)
)
print("Signal B — External reference matching done.")


# ─────────────────────────────────────────────────────────────
# 7. SIGNAL C — Tender Title + Work Description
# ─────────────────────────────────────────────────────────────

def extract_district_from_title(row) -> str | None:
    slug = str(row.get('tender_title', '')) + ' ' + str(row.get('Work Description', ''))
    return regex_match_district(slug)

tenders_df['tender_district_title_description'] = tenders_df.apply(
    extract_district_from_title, axis=1
)
print("Signal C — Title + description matching done.")


# ─────────────────────────────────────────────────────────────
# 8. SIGNAL D — Location column (regex on cleaned location)
# ─────────────────────────────────────────────────────────────

tenders_df['tender_district_location'] = tenders_df['location_cleaned'].apply(
    regex_match_district
)
print("Signal D — Location regex matching done.")


# ─────────────────────────────────────────────────────────────
# 9. WEIGHTAGE — Reconcile all signals into DISTRICT_FINALISED
# ─────────────────────────────────────────────────────────────

def reconcile_districts(row) -> str:
    """
    Gather all non-null signal values.
    - 1 unique district  → use it
    - 0 values           → 'NA'
    - 2+ different       → 'CONFLICT'
    """
    signals = [
        row['tender_district_externalReference'],
        row['tender_district_title_description'],
        row['tender_district_location'],
    ]
    found = {s for s in signals if pd.notna(s)}

    if len(found) == 1:
        return found.pop()
    elif len(found) == 0:
        return 'NA'
    else:
        return 'CONFLICT'

tenders_df['DISTRICT_FINALISED'] = tenders_df.apply(reconcile_districts, axis=1)
print("Weightage reconciliation done.")


# ─────────────────────────────────────────────────────────────
# 10. SAVE OUTPUT
# ─────────────────────────────────────────────────────────────

output_path = os.path.join(
    os.getcwd(),
    'Sources', 'TENDERS', 'data',
    'floodtenders_districtgeotagged.csv'
)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
tenders_df.to_csv(output_path, index=False)
print(f"\n Output saved → {output_path}")

