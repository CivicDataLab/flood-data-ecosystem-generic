"""
Flood Tender Filter & Classification Script
=============================================
Reads monthly tender CSVs, filters flood-related tenders using keywords,
then classifies them by Season, Scheme, Erosion, Roads/Bridges/Embankments,
and Response Type.

All keywords and department exclusions are loaded from:
    keywords_config.json  (must be in the same folder as this script)

Output per monthly file : Sources/TENDERS/data/flood_tenders/<filename>.csv
Combined output          : Sources/TENDERS/data/flood_tenders_all.csv
"""

import os
import re
import json
import glob
import dateutil.parser
import pandas as pd

# ─────────────────────────────────────────────────────────────
# 1. LOAD CONFIG
# ─────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Keywords_config.json')

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(
        f"keywords_config.json not found at: {CONFIG_PATH}\n"
        "Make sure it sits in the same folder as this script."
    )

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

# Unpack all keyword lists from config
POSITIVE_KEYWORDS   = list(set(CONFIG['flood_filter']['positive']))   # deduplicate
NEGATIVE_KEYWORDS   = CONFIG['flood_filter']['negative']
EXCL_DEPARTMENTS    = CONFIG['exclusion_departments']
SCHEME_KEYWORDS     = set(CONFIG['scheme_keywords'])
EROSION_KW          = CONFIG['erosion_keywords']
ROADS_BRIDGES_KW    = CONFIG['roads_bridges_embankments_keywords']
IMMEDIATE_KW        = CONFIG['response_type']['immediate_measures']
REPAIR_KW           = CONFIG['response_type']['repair_restoration']
PREPAREDNESS_KW     = CONFIG['response_type']['preparedness_measures']

print(f"  Config loaded from: {CONFIG_PATH}")
print(f"   Positive keywords     : {len(POSITIVE_KEYWORDS)}")
print(f"   Negative keywords     : {len(NEGATIVE_KEYWORDS)}")
print(f"   Scheme keywords       : {len(SCHEME_KEYWORDS)}")
print(f"   Exclusion departments : {len(EXCL_DEPARTMENTS)}\n")


# ─────────────────────────────────────────────────────────────
# 2. HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def build_keyword_dict(keyword_list: list) -> dict:
    """Initialise a count dict with 0 for every keyword."""
    return {kw: 0 for kw in keyword_list}


def make_tender_slug(row) -> str:
    """Concatenate and clean the key tender text fields into one searchable string."""
    raw = (
        str(row.get('tender_externalreference', '')) + ' ' +
        str(row.get('tender_title', ''))             + ' ' +
        str(row.get('Work Description', ''))
    )
    return re.sub(r'[^a-zA-Z0-9 \n\.]', ' ', raw)


def keyword_counts(slug: str, keywords: list) -> dict:
    """Return {keyword: count} for every keyword in `keywords` against `slug`."""
    return {
        kw: len(re.findall(r'\b%s\b' % re.escape(kw.lower()), slug.lower()))
        for kw in keywords
    }


def flood_filter(row) -> tuple:
    """
    Determine whether a tender is flood-related.
    Returns (is_flood_tender: str, positive_kw_dict: str, negative_kw_dict: str)
    """
    slug = make_tender_slug(row)

    pos_counts = keyword_counts(slug, POSITIVE_KEYWORDS)
    neg_counts = keyword_counts(slug, NEGATIVE_KEYWORDS)

    is_flood = any(v > 0 for v in pos_counts.values())

    # Any negative keyword match overrides
    if any(v > 0 for v in neg_counts.values()):
        is_flood = False

    return str(is_flood), str(pos_counts), str(neg_counts)


def classify_season(published_date_str: str) -> str:
    """Classify a tender date into Pre-Monsoon / Monsoon / Post-Monsoon."""
    try:
        month = dateutil.parser.parse(published_date_str).month
    except Exception:
        return "Unknown"
    if 3 <= month <= 5:
        return "Pre-Monsoon"
    elif 6 <= month <= 9:
        return "Monsoon"
    else:
        return "Post-Monsoon"


def identify_scheme(row) -> str:
    """Match a tender slug against known scheme keywords (set intersection)."""
    slug = make_tender_slug(row).lower()
    tokens = set(re.split(r'[-.,()_\s/]\s*', slug))
    matches = tokens & SCHEME_KEYWORDS
    return list(matches)[0].upper() if matches else ''


def flag_keywords(slug: str, keywords: list) -> bool:
    """True if any keyword from the list appears in the slug."""
    return any(
        len(re.findall(r'\b%s\b' % re.escape(kw.lower()), slug.lower())) > 0
        for kw in keywords
    )


def classify_response_type(row) -> tuple:
    """
    Classify tender into one of:
      Immediate Measures / Repair and Restoration / Preparedness Measures / Others

    Priority: Immediate > Repair > Preparedness > Others
    Returns (response_type, subhead_dict_str)
    """
    slug = make_tender_slug(row)

    imm_counts  = keyword_counts(slug, IMMEDIATE_KW)
    rep_counts  = keyword_counts(slug, REPAIR_KW)
    prep_counts = keyword_counts(slug, PREPAREDNESS_KW)

    if any(v > 0 for v in imm_counts.values()):
        response_type = "Immediate Measures"
        subhead = {k: v for k, v in imm_counts.items() if v > 0}
    elif any(v > 0 for v in rep_counts.values()):
        response_type = "Repair and Restoration"
        subhead = {k: v for k, v in rep_counts.items() if v > 0}
    elif any(v > 0 for v in prep_counts.values()):
        response_type = "Preparedness Measures"
        subhead = {k: v for k, v in prep_counts.items() if v > 0}
    else:
        response_type = "Others"
        subhead = {}

    return response_type, str(subhead)


# ─────────────────────────────────────────────────────────────
# 3. PROCESS EACH MONTHLY CSV
# ─────────────────────────────────────────────────────────────

data_path   = os.path.join(os.getcwd(), 'Sources', 'TENDERS', 'data', 'monthly_tenders') + os.sep
output_path = os.path.join(os.getcwd(), 'Sources', 'TENDERS', 'data', 'flood_tenders')
os.makedirs(output_path, exist_ok=True)

csvs = glob.glob(data_path + '*.csv')
if not csvs:
    raise FileNotFoundError(f"No CSVs found in: {data_path}")

print(f"Found {len(csvs)} monthly CSV(s) to process.\n")

for csv_path in csvs:
    # Normalise path separators for cross-platform safety
    csv_path = csv_path.replace("\\", "/")
    filename = csv_path.split("/")[-1]
    print(f"{'─'*50}")
    print(f"Processing: {filename}")

    input_df = pd.read_csv(csv_path)
    input_df = input_df.drop_duplicates()

    # ── Flood filter ──
    results = input_df.apply(flood_filter, axis=1)
    input_df['is_flood_tender']      = [r[0] for r in results]
    input_df['positive_keywords_dict'] = [r[1] for r in results]
    input_df['negative_keywords_dict'] = [r[2] for r in results]

    # ── Keep only flood tenders, exclude irrelevant departments ──
    tenders_df = input_df[
        (input_df['is_flood_tender'] == 'True') &
        (~input_df['Department'].isin(EXCL_DEPARTMENTS))
    ].copy()

    print(f"  Flood-related tenders : {tenders_df.shape[0]}")
    if tenders_df.empty:
        print("No flood tenders found — skipping.\n")
        continue

    # ── Season classification ──
    tenders_df['Season'] = tenders_df['Published Date'].apply(classify_season)

    # ── Scheme identification ──
    tenders_df['Scheme'] = tenders_df.apply(identify_scheme, axis=1)

    # ── Erosion flag ──
    tenders_df['Erosion'] = tenders_df.apply(
        lambda row: flag_keywords(make_tender_slug(row), EROSION_KW), axis=1
    )

    # ── Roads / Bridges / Embankments flag ──
    tenders_df['Roads_Bridges_Embkt'] = tenders_df.apply(
        lambda row: flag_keywords(make_tender_slug(row), ROADS_BRIDGES_KW), axis=1
    )

    # ── Response type classification ──
    response_results = tenders_df.apply(classify_response_type, axis=1)
    tenders_df['Response Type']  = [r[0] for r in response_results]
    tenders_df['Flood Response - Subhead'] = [r[1] for r in response_results]

    # ── Save monthly output ──
    out_file = os.path.join(output_path, filename)
    tenders_df.to_csv(out_file, encoding='utf-8', index=False)
    print(f"Saved → {out_file}")

    # ── Response type breakdown ──
    print("  Response type breakdown:")
    for rtype, count in tenders_df['Response Type'].value_counts().items():
        print(f"    {rtype:<30} : {count}")
    print()


# ─────────────────────────────────────────────────────────────
# 4. COMBINE ALL MONTHLY FILES INTO ONE MASTER CSV
# ─────────────────────────────────────────────────────────────

all_csvs = glob.glob(os.path.join(output_path, '*.csv'))
dfs = []

for csv_path in all_csvs:
    csv_path = csv_path.replace("\\", "/")
    month    = csv_path.split("/")[-1][:7]   # e.g. "2024_06"
    df    = pd.read_csv(csv_path)
    df['month'] = month
    dfs.append(df)

if dfs:
    master_df = pd.concat(dfs, ignore_index=True)
    master_path = os.path.join(os.getcwd(), 'Sources', 'TENDERS', 'data', 'flood_tenders_all.csv')
    master_df.to_csv(master_path, index=False)
    print(f"{'='*50}")
    print(f"Master file saved → {master_path}")
    print(f"   Total flood tenders : {len(master_df)}")
    print(f"   Months covered      : {master_df['month'].nunique()}")
    print(f"{'='*50}")
else:
    print("No flood tender CSVs found to combine.")