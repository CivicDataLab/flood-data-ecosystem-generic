from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options

DEFAULT_STATE_CONFIG = {
    "andhra pradesh": {
        "code": "ap",
        "dropdown_value": "id101_0",
        "dropdown_id": "minus101",
        "bbox": {
            "lat_south": 12.6240111221884,
            "lat_north": 19.166912968171886,
            "lon_west": 76.76056909718027,
            "lon_east": 84.76146375590628
        }
    },
    "assam": {
        "code": "as",
        "dropdown_value": "id100_0",
        "dropdown_id": "minus100",
        "bbox": {
            "lat_south": 24.13613519737949,
            "lat_north": 27.971475095719736,
            "lon_west": 89.69860048177071,
            "lon_east": 96.01787644941203
        }
    },
    "bihar": {
        "code": "br",
        "dropdown_value": "id102_0",
        "dropdown_id": "minus102",
        "bbox": {
            "lat_south": 24.28600646908134,
            "lat_north": 27.521777474925372,
            "lon_west": 83.32021588676227,
            "lon_east": 88.29379581022933
        }
    },
    "delhi": {
        "code": "dl",
        "dropdown_value": "id103_0",
        "dropdown_id": "minus103",
        "bbox": {
            "lat_south": 28.40466759134758,
            "lat_north": 28.883499628015024,
            "lon_west": 76.83889215307885,
            "lon_east": 77.34757046984508
        }
    },
    "haryana": {
        "code": "hr",
        "dropdown_value": "id120_0",
        "dropdown_id": "minus120",
        "bbox": {
            "lat_south": 27.652270970850193,
            "lat_north": 30.92854286936908,
            "lon_west": 74.4732586523917,
            "lon_east": 77.60459126643798
        }
    },
    "karnataka": {
        "code": "ka",
        "dropdown_value": "id123_0",
        "dropdown_id": "minus123",
        "bbox": {
            "lat_south": 11.594470724629366,
            "lat_north": 18.47772646632495,
            "lon_west": 74.05399340093027,
            "lon_east": 78.58770234537053
        }
    },
    "kerala": {
        "code": "kl",
        "dropdown_value": "id119_0",
        "dropdown_id": "minus119",
        "bbox": {
            "lat_south": 8.293018226041038,
            "lat_north": 12.795534473801288,
            "lon_west": 74.864337099569,
            "lon_east": 77.41239641495655
        }
    },
    "madhya pradesh": {
        "code": "mp",
        "dropdown_value": "id114_0",
        "dropdown_id": "minus114",
        "bbox": {
            "lat_south": 21.07068852460483,
            "lat_north": 26.86956164910599,
            "lon_west": 74.02938199029161,
            "lon_east": 82.81261164695366
        }
    },
    "maharashtra": {
        "code": "mh",
        "dropdown_value": "id105_0",
        "dropdown_id": "minus105",
        "bbox": {
            "lat_south": 15.606085184614516,
            "lat_north": 22.030269372833256,
            "lon_west": 72.64199057033973,
            "lon_east": 80.8976843176878
        }
    },
    "manipur": {
        "code": "mn",
        "dropdown_value": "id111_0",
        "dropdown_id": "minus111",
        "bbox": {
            "lat_south": 23.83284842270268,
            "lat_north": 25.692090243182655,
            "lon_west": 92.96943383723556,
            "lon_east": 94.7448900623007
        }
    },
    "meghalaya": {
        "code": "ml",
        "dropdown_value": "id113_0",
        "dropdown_id": "minus113",
        "bbox": {
            "lat_south": 25.02779536088338,
            "lat_north": 26.119405765138833,
            "lon_west": 89.81954538642361,
            "lon_east": 92.8029146664425
        }
    },
    "odisha": {
        "code": "od",
        "dropdown_value": "id104_0",
        "dropdown_id": "minus104",
        "bbox": {
            "lat_south": 17.8,
            "lat_north": 22.6,
            "lon_west": 81.3,
            "lon_east": 87.5
        }
    },
    "punjab": {
        "code": "pb",
        "dropdown_value": "id122_0",
        "dropdown_id": "minus122",
        "bbox": {
            "lat_south": 29.542070143897313,
            "lat_north": 32.511562574200106,
            "lon_west": 73.87977595920648,
            "lon_east": 76.94146149757219
        }
    },
    "tamil nadu": {
        "code": "tn",
        "dropdown_value": "id112_0",
        "dropdown_id": "minus112",
        "bbox": {
            "lat_south": 8.07770441572396,
            "lat_north": 13.56462819768922,
            "lon_west": 76.23298312565383,
            "lon_east": 80.34654672836902
        }
    },
    "telangana": {
        "code": "tg",
        "dropdown_value": "id117_0",
        "dropdown_id": "minus117",
        "bbox": {
            "lat_south": 15.836003294146044,
            "lat_north": 19.91680698568637,
            "lon_west": 77.23576101930497,
            "lon_east": 81.32264131455234
        }
    },
    "tripura": {
        "code": "tr",
        "dropdown_value": "id118_0",
        "dropdown_id": "minus118",
        "bbox": {
            "lat_south": 22.938351491654313,
            "lat_north": 24.53186712630424,
            "lon_west": 91.14919851765178,
            "lon_east": 92.3320574461437
        }
    },
    "uttar pradesh": {
        "code": "up",
        "dropdown_value": "id103_0",
        "dropdown_id": "minus103",
        "bbox": {
            "lat_south": 23.8,
            "lat_north": 30.5,
            "lon_west": 77.0,
            "lon_east": 84.7
        }
    },
    "west bengal": {
        "code": "wb",
        "dropdown_value": "id104_0",
        "dropdown_id": "minus104",
        "bbox": {
            "lat_south": 21.527081529657302,
            "lat_north": 27.221067412233854,
            "lon_west": 85.81967347336501,
            "lon_east": 89.88260219031282
        }
    },
}


def get_state_choice():
    """Prompt the user to pick a state from the available list."""
    available_states = sorted(DEFAULT_STATE_CONFIG.keys())
    print("\nAvailable states:")
    for i, state in enumerate(available_states, start=1):
        print(f"  {i:2}. {state.title()}")

    while True:
        choice = input("\nEnter state name (or number): ").strip().lower()

        # Allow selection by number
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_states):
                return available_states[idx]
            else:
                print(f"Invalid number. Please enter a number between 1 and {len(available_states)}.")
        elif choice in DEFAULT_STATE_CONFIG:
            return choice
        else:
            print(f"'{choice}' not found. Please try again.")


def get_dates_for_state(state_name):
    config = DEFAULT_STATE_CONFIG[state_name]
    dropdown_value = config["dropdown_value"]
    dropdown_id    = config["dropdown_id"]

    bhuvan_url = "https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=flood"

    firefox_options = Options()
    firefox_options.headless = True

    service = Service('/snap/bin/firefox.geckodriver')
    driver = webdriver.Firefox(service=service, options=firefox_options)

    try:
        driver.get(bhuvan_url)

        # Wait until the iframe and dropdown are ready instead of a bare sleep
        wait = WebDriverWait(driver, 15)
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "toolid")))
        wait.until(EC.presence_of_element_located((By.ID, "rf")))

        # Extra pause — site resets to Delhi a few seconds after load
        time.sleep(5)

        state_dropdown_element = Select(driver.find_element("id", "rf"))
        state_dropdown_element.select_by_value(dropdown_value)

        # Wait for the date container to appear after selection
        wait.until(EC.presence_of_element_located((By.ID, dropdown_id)))
        element = driver.find_element("id", dropdown_id)
        elements = element.find_elements(By.TAG_NAME, "div")

        dates = []
        for e in elements:
            date = e.text.strip()
            if not date:
                continue

            date = date.replace("/", "_").replace("Hr", "").replace("-", "_")
            date_parts = date.split("_")

            if len(date_parts) == 4:
                day, month, year, hour = date_parts
                new_date_string = f"{year}_{day}_{month}_{hour}"
            elif len(date_parts) == 3:
                day, month, year = date_parts
                new_date_string = f"{year}_{day}_{month}"
            else:
                print(f"Unexpected date format, skipping: {date!r}")
                continue

            dates.append(new_date_string)

        return dates

    finally:
        driver.quit()


if __name__ == "__main__":
    state_name = get_state_choice()
    print(f"\nFetching dates for: {state_name.title()} ...")
    dates = get_dates_for_state(state_name)
    print(f"\nDates found ({len(dates)}):")
    for d in dates:
        print(f"  {d}")