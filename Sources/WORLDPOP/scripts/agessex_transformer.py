import pandas as pd
import re
from pathlib import Path
import os

# -------------------------------------------------------------------
# PATHS – update these if needed
# -------------------------------------------------------------------
worldpop_dir = os.path.join(os.getcwd(),"Sources/WORLDPOP/data")  # Folder containing worldpopstats_YYYY.csv
demographic_dir = os.path.join(os.getcwd(),"Sources/WORLDPOP/data/agesexstructure")  # Folder containing demographic data by year folders

# Output directory for processed WorldPop files
output_dir = worldpop_dir
output_dir.mkdir(exist_ok=True, parents=True)


# -------------------------------------------------------------------
# CORE FUNCTIONS FOR CLASSIFICATIONS 
# -------------------------------------------------------------------
def calculate_population_statistics(demographic_file: Path):
    """
    Calculate mean sex ratio, aged population, and young population
    for a single demographic file.

    Expected columns in demographic_file:
      - 'male'
      - 'female'
      - 'class'
    """
    df = pd.read_csv(demographic_file)

    # Total male and female population
    total_male = df["male"].sum()
    total_female = df["female"].sum()

    # Mean sex ratio (F/M)
    mean_sex_ratio = total_female / total_male if total_male > 0 else 0

    # Aged population (classes 65, 70, 75, 80)
    aged_population = (
        df[df["class"].isin([65, 70, 75, 80])][["male", "female"]].sum().sum()
    )

    # Young population (classes 0, 1)
    young_population = (
        df[df["class"].isin([0, 1])][["male", "female"]].sum().sum()
    )

    return mean_sex_ratio, aged_population, young_population


def normalize_name(name: str) -> str:
    """
    Normalize subdistrict names:
      - replace '-' with space
      - collapse multiple spaces
      - replace spaces with underscores
      - convert to UPPERCASE
    """
    name = name.replace("-", " ")
    name = re.sub(r"\s+", " ", name.strip())
    return name.replace(" ", "_").upper()


def process_yearly_data(year: int):
    """
    For a given year, attach demographic statistics (sex ratio, aged pop,
    young pop) to the corresponding worldpopstats_{year}.csv file.

    """
    # ----------------------------------------------------------------
    # 1. Load WorldPop data
    # ----------------------------------------------------------------
    worldpop_file = worldpop_dir / f"worldpopstats_{year}.csv"
    if not worldpop_file.exists():
        print(f"WorldPop file not found for year {year}: {worldpop_file}")
        return

    print(f"\nProcessing year {year} from {worldpop_file}")
    worldpop_df = pd.read_csv(worldpop_file)

    # Sanity checks
    required_cols = ["object_id", "sdtname"]
    missing = [c for c in required_cols if c not in worldpop_df.columns]
    if missing:
        raise KeyError(f"Missing columns in {worldpop_file}: {missing}")

    # Optional: normalized subdistrict name (handy for debugging/joining)
    worldpop_df["subdistrict_name_norm"] = worldpop_df["sdtname"].apply(normalize_name)

    # ----------------------------------------------------------------
    # 2. Loop over subdistricts and compute stats from demographic CSVs
    # ----------------------------------------------------------------
    statistics = []
    demographic_year_dir = demographic_dir / str(year)

    if not demographic_year_dir.exists():
        print(f"Demographic folder for {year} not found: {demographic_year_dir}")
        # Still proceed but everything will be None
        demographic_year_dir.mkdir(parents=True, exist_ok=True)

    for row in worldpop_df.itertuples(index=False):
        object_id = row.object_id
        subdistrict_norm = row.subdistrict_name_norm

        demographic_file = demographic_year_dir / f"{object_id}_agesexpyramid_{year}.csv"

        if demographic_file.exists():
            mean_sex_ratio, aged_population, young_population = calculate_population_statistics(
                demographic_file
            )
        else:
            print(f"Demographic file not found: {demographic_file}")
            mean_sex_ratio, aged_population, young_population = None, None, None

        statistics.append(
            {
                "object_id": object_id,
                "subdistrict_name_norm": subdistrict_norm,
                "mean_sex_ratio": mean_sex_ratio,
                "sum_aged_population": aged_population,
                "sum_young_population": young_population,
            }
        )

    stats_df = pd.DataFrame(statistics)

    # ----------------------------------------------------------------
    # 3. Merge stats back into worldpop_df on object_id
    # ----------------------------------------------------------------
    updated_worldpop_df = worldpop_df.merge(
        stats_df,
        on=["object_id", "subdistrict_name_norm"],
        how="left",
        suffixes=("", "_dem")
    )

    # If you don't want the normalized name in the final file, drop it:
    # updated_worldpop_df = updated_worldpop_df.drop(columns=["subdistrict_name_norm"])

    # ----------------------------------------------------------------
    # 4. Save updated file
    # ----------------------------------------------------------------
    updated_worldpop_file = output_dir / f"worldpopstats_{year}.csv"
    updated_worldpop_df.to_csv(updated_worldpop_file, index=False)
    print(f"Processed data saved to {updated_worldpop_file}")


# -------------------------------------------------------------------
# MAIN LOOP
# -------------------------------------------------------------------
if __name__ == "__main__":
    for year in [2017, 2018, 2019, 2020]:
        process_yearly_data(year)
