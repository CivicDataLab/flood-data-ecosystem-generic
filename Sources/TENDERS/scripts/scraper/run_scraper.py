"""
Runner Script for Multi-State Awarded Tenders Scraper
=======================================================
Loops through a range of years/months and runs tender_scraper.py
for each combination.

Usage:
    python run_scraper.py

Edit the STATE_ID, YEAR_RANGE, and MONTH_RANGE below before running.
"""

import subprocess
import os

# ─────────────────────────────────────────────────────────────
# CONFIGURATION — Edit these before running
# ─────────────────────────────────────────────────────────────

# Python executable in your conda/virtual environment
PYTHON_EXE = input("enter the path to your python executable : ").strip()

# Path to the scraper script (same folder as this runner by default)
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_recent_tenders_tender_status.py")

# Year range to scrape  (range(2024, 2026) = 2024 and 2025)
YEAR_RANGE  = range(2025, 2026)

# Month range to scrape  (range(1, 13) = all months)
MONTH_RANGE = range(6, 8)

# ─────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Tender Scraper — Batch Runner")
    print("=" * 55)

    # Validate paths
    if not os.path.exists(PYTHON_EXE):
        print(f" Python executable not found:\n   {PYTHON_EXE}")
        print("   Update PYTHON_EXE at the top of this script.")
        return

    if not os.path.exists(SCRIPT_PATH):
        print(f"Scraper script not found:\n  {SCRIPT_PATH}")
        print("   Make sure tender_scraper.py is in the same folder as this runner.")
        return

    total = len(YEAR_RANGE) * len(MONTH_RANGE)
    run   = 0

    for year in YEAR_RANGE:
        for month in MONTH_RANGE:
            run += 1
            year_str  = str(year)
            month_str = str(month)

            print(f"\n[{run}/{total}]  ▶  Year: {year_str}  |  Month: {month_str.zfill(2)}")
            print("─" * 40)

            try:
                subprocess.call([
                    PYTHON_EXE,
                    SCRIPT_PATH,
                    year_str,
                    month_str
                ])
            except KeyboardInterrupt:
                print("\n Interrupted by user. Stopping batch run.")
                return
            except Exception as e:
                print(f"Error running scraper for {year_str}/{month_str}: {e}")
                print("   Continuing to next month…")
                continue

    print("\n" + "=" * 55)
    print(f" Batch complete — {run} month(s) processed.")
    print("=" * 55)


if __name__ == "__main__":
    main()