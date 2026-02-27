"""
Multi-State Awarded Tenders Scraper
====================================
Scrapes "Awarded Bids" (AOC) from NIC GePNIC portals across Indian states.
State URLs are loaded from  →  states_config.json  (must be in the same folder)

Usage:
    python tender_scraper.py

You will be prompted to:
  1. Select a state from the menu
  2. Enter year and month
  3. Solve the CAPTCHA in the visible browser window
"""

import json
import time
import os
import re
import sys
import warnings
import traceback
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ─────────────────────────────────────────────────────────────
# CONFIG LOADER
# ─────────────────────────────────────────────────────────────

CONFIG_FILE = os.path.join(os.getcwd(),'Sources/TENDERS/scripts/scraper/States_config.JSON')

def load_states(config_path: str = CONFIG_FILE) -> dict:
    """Load state registry from the JSON config file."""
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("    Make sure 'states_config.json' is in the same folder as this script.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convert list → dict keyed by id for easy lookup
    return {entry["id"]: entry for entry in data["states"]}


# GePNIC awarded-bids status ID (same on every NIC portal)
AWARDED_STATUS_ID    = "6"
AWARDED_STATUS_LABEL = "AOC Award of Contract"

# Common geckodriver locations; extend if yours differs
GECKO_PATH = input("Enter the full path to your geckodriver executable: ").strip()
if not os.path.isfile(GECKO_PATH):
    raise FileNotFoundError("Geckodriver not found at the provided path.")

# ─────────────────────────────────────────────────────────────
# UTILITY HELPERS
# ─────────────────────────────────────────────────────────────

def sanitize_filename(text: str) -> str:
    """Strip characters that are illegal in file/folder names."""
    return re.sub(r'[<>:"/\\|?*₹,\n\r\t]', '', text).replace(' ', '_')


def wait_for(browser, xpath: str, timeout: int = 10):
    """Wait up to `timeout` seconds for an element and return it."""
    return WebDriverWait(browser, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )


def select_dropdown(browser, xpath: str, value: str):
    """Select an <option> in a <select> dropdown by its value attribute."""
    element = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )
    Select(element).select_by_value(value)


def table_to_dataframe(table_element) -> pd.DataFrame:
    """Convert a Selenium <table> WebElement into a pandas DataFrame."""
    rows = table_element.find_elements(By.TAG_NAME, "tr")
    data = []
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td") or \
                row.find_elements(By.TAG_NAME, "th")
        data.append([c.text.strip() for c in cells])

    if not data:
        return pd.DataFrame()

    header    = data[0]
    rows_data = data[1:] if header else data
    return pd.DataFrame(rows_data, columns=header) if header else pd.DataFrame(data)


def save_dataframe(df: pd.DataFrame, filepath: str):
    """Save a DataFrame to CSV, creating parent directories as needed."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f" Saved → {filepath}")


# ─────────────────────────────────────────────────────────────
# BROWSER SETUP
# ─────────────────────────────────────────────────────────────

def create_browser(headless: bool = False):
    """
    Launch Firefox (preferred) or fall back to Chrome.
    headless=False keeps the window visible so the user can solve the CAPTCHA.
    """
    for gecko_path in GECKO_PATH:
        if os.path.exists(gecko_path) or gecko_path == "geckodriver":
            try:
                opts = FirefoxOptions()
                if headless:
                    opts.add_argument("--headless")
                service = FirefoxService(gecko_path)
                browser = webdriver.Firefox(service=service, options=opts)
                print(" Browser: Firefox")
                return browser
            except Exception:
                continue

    try:
        opts = ChromeOptions()
        if headless:
            opts.add_argument("--headless")
        browser = webdriver.Chrome(options=opts)
        print("Browser: Chrome")
        return browser
    except Exception as e:
        print(f"Could not launch Firefox or Chrome.\n  Error: {e}")
        print("  Make sure geckodriver (Firefox) or chromedriver (Chrome) is installed.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────
# CAPTCHA HANDLER  (manual — user types the answer)
# ─────────────────────────────────────────────────────────────

def solve_captcha(browser):
    """
    Waits for the CAPTCHA image, then asks the user to type
    the solution in the terminal. Retries automatically on failure.
    """
    WebDriverWait(browser, 15).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="captchaImage"]'))
    )

    print("\n A CAPTCHA is now visible in the browser window.")
    answer = input("   Type the CAPTCHA characters and press Enter: ").strip()

    box = wait_for(browser, '//*[@id="captchaText"]')
    box.clear()
    box.send_keys(answer)
    browser.find_element(By.ID, "Search").click()

    while True:
        time.sleep(1.5)
        errors = browser.find_elements(By.CLASS_NAME, "error")
        if not errors or "Invalid Captcha" not in errors[0].text:
            print(" CAPTCHA accepted.")
            return
        print("Invalid CAPTCHA — please try again.")
        answer = input("   Re-type the CAPTCHA: ").strip()
        box = wait_for(browser, '//*[@id="captchaText"]')
        box.clear()
        box.send_keys(answer)
        browser.find_element(By.ID, "Search").click()


# ─────────────────────────────────────────────────────────────
# DATE RANGE FILLER
# ─────────────────────────────────────────────────────────────

MONTH_LAST_DAY = {0:31, 1:28, 2:31, 3:30, 4:31, 5:30,
                  6:31, 7:31, 8:30, 9:31, 10:30, 11:31}

def set_date_range(browser, year: str, month: str):
    """
    Fills the From / To date pickers.
    Sets range = 1st → last day of the *previous* calendar month.
    GePNIC month dropdowns are 0-indexed (0 = January).
    """
    prev_month_idx = int(month) - 1
    last_day       = str(MONTH_LAST_DAY[prev_month_idx])
    pm_str         = str(prev_month_idx)

    # FROM date
    wait_for(browser,
        '//*[@id="frmSearchFilter"]/table/tbody/tr/td/table/tbody/tr/td'
        '/table/tbody/tr/td/table/tbody/tr[4]/td/table/tbody/tr/td'
        '/table/tbody/tr[3]/td[2]/a'
    ).click()
    time.sleep(0.4)
    select_dropdown(browser,
        '//*[@id="Body"]/div[2]/div[1]/table/tbody/tr/td[2]/select', pm_str)
    select_dropdown(browser,
        '//*[@id="Body"]/div[2]/div[1]/table/tbody/tr/td[3]/select', year)
    browser.find_element(By.XPATH, "//td[text()='1']").click()

    # TO date
    wait_for(browser,
        '//*[@id="frmSearchFilter"]/table/tbody/tr/td/table/tbody/tr/td'
        '/table/tbody/tr/td/table/tbody/tr[4]/td/table/tbody/tr/td'
        '/table/tbody/tr[3]/td[4]/a'
    ).click()
    time.sleep(0.4)
    select_dropdown(browser,
        '//*[@id="Body"]/div[3]/div[1]/table/tbody/tr/td[2]/select', pm_str)
    select_dropdown(browser,
        '//*[@id="Body"]/div[3]/div[1]/table/tbody/tr/td[3]/select', year)
    browser.find_elements(By.XPATH, f"//td[text()='{last_day}']")[-1].click()

    print(f"Date range: 1/{int(pm_str)+1}/{year}  →  {last_day}/{int(pm_str)+1}/{year}")


# ─────────────────────────────────────────────────────────────
# SCRAPING CORE
# ─────────────────────────────────────────────────────────────

def scrape_all_pages(browser, output_folder: str, year: str, month: str):
    """
    Iterates through every result page, extracts each table into
    a DataFrame, then saves one combined CSV at the end.
    """
    wait       = WebDriverWait(browser, 10)
    all_frames = []
    page_num   = 0

    while True:
        page_num += 1
        print(f"\n Page {page_num}…", end=" ", flush=True)

        try:
            table_elem = wait.until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="tabList"]'))
            )
        except Exception:
            print("⚠️  Results table not found — search returned 0 results.")
            break

        df = table_to_dataframe(table_elem)
        if df.empty:
            print("empty — stopping.")
            break

        all_frames.append(df)
        print(f"{len(df)} rows.")

        next_elems = browser.find_elements(By.XPATH, '//*[@id="loadNext"]')
        next_href  = next_elems[0].get_attribute("href") if next_elems else ""
        if not next_href:
            print("All pages scraped.")
            break

        browser.get(next_href)
        time.sleep(1)

    if all_frames:
        combined  = pd.concat(all_frames, ignore_index=True)
        filename  = f"awarded_tenders_{year}_{month}.csv"
        save_dataframe(combined, os.path.join(output_folder, filename))
        print(f"\nTotal records scraped: {len(combined)}")
    else:
        print("\n No data scraped for this period.")


# ─────────────────────────────────────────────────────────────
# STATE SELECTION MENU
# ─────────────────────────────────────────────────────────────

def show_state_menu(states: dict) -> dict:
    """Print the numbered state menu and return the chosen state entry."""
    print("\n" + "─" * 45)
    print("  Select a State Portal")
    print("─" * 45)
    for key, val in states.items():
        print(f"  [{key:>2}]  {val['name']}")
    print("─" * 45)

    while True:
        choice = input("\nEnter state number: ").strip()
        if choice in states:
            return states[choice]
        print(f"'{choice}' is not valid. Please enter a number from the list above.")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print(" Multi-State Awarded Tenders Scraper")
    print("=" * 55)

    # 1. Load config
    states = load_states()
    print(f"Loaded {len(states)} states from states_config.json")

    # 2. Pick state
    state = show_state_menu(states)

    if state["url"] is None:
        base_url = input(
            "Enter the full portal URL (e.g. https://yourtenders.gov.in/nicgep/app): "
        ).strip()
    else:
        base_url = state["url"]

    state_name = state["name"]
    print(f"\Portal : {base_url}")

    # 3. Year & month
    year  = input("Year  (e.g. 2024)       : ").strip()
    month = input("Month (e.g. 6 for June) : ").strip()
    month_padded = month.zfill(2)

    # 4. Output folder
    folder_name   = sanitize_filename(f"{state_name}_{year}_{month_padded}_awarded")
    output_folder = os.path.join(os.getcwd(), "scraped_tenders", folder_name)
    os.makedirs(output_folder, exist_ok=True)
    print(f"\n  📁  Output : {output_folder}")

    # 5. Launch browser
    browser = create_browser(headless=False)

    try:
        # 6. Open portal
        browser.get(base_url)
        time.sleep(2)
        print(f"Opened portal for {state_name}")

        # 7. Set tender status = AOC (Awarded)
        select_dropdown(browser, '//*[@id="tenderStatus"]', AWARDED_STATUS_ID)
        print(f" Status : {AWARDED_STATUS_LABEL}")

        # 8. Set date range
        set_date_range(browser, year, month)

        # 9. Solve CAPTCHA
        solve_captcha(browser)

        # 10. Scrape
        print(f"\nScraping {state_name} — {month_padded}/{year}…")
        scrape_all_pages(browser, output_folder, year, month_padded)

        print(f"\n Done!  Data saved to:\n   {output_folder}\n")

    except Exception:
        print("\n Unexpected error:")
        traceback.print_exc()

    finally:
        input("Press Enter to close the browser… ")
        browser.quit()


if __name__ == "__main__":
    main()