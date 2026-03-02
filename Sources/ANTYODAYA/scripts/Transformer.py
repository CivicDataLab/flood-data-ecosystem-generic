import pandas as pd
from shapely.geometry import Point
import geopandas as gpd
import rasterio
import glob
from rasterstats import zonal_stats
import os

# ---------------------------------------------------------
# 1. CONFIG
# ---------------------------------------------------------
state_code =  input("enter the name of the state  :  ")# enter the state your working on 
base_dir = os.getcwd()

antyodaya_file = os.path.join(
    base_dir, "Sources/ANTYODAYA/data/antyodaya_village_dataset_with_revenue_circle.xlsx"
)

revenue_circle_file = glob.glob(os.path.join(base_dir, 'Maps/Geojson/*_subdistricts.geojson'))
if not revenue_circle_file:
    raise FileNotFoundError("No subdistricts geojson found")
revenue_circle_file = revenue_circle_file[0]

bharat_maps_file = glob.glob(os.path.join(base_dir, 'Maps/Geojson/*_villages.geojson'))
if not bharat_maps_file:
    raise FileNotFoundError("No villages geojson found")
bharat_maps_file = bharat_maps_file[0]

output_tagged = os.path.join(
    base_dir, f"Sources/ANTYODAYA/data/MissionAntyodaya2020_{state_code}_taggedRC.csv"
)

output_vul = os.path.join(
    base_dir, f"Sources/ANTYODAYA/data/MissionAntyodaya2020_{state_code}_vul.csv"
)

urban_shape_file = glob.glob(os.path.join(base_dir,"Maps/Geojson/*_urban.geojson")
)

worldpop_raster_file = os.path.join(
    base_dir,"Sources/ANTYODAYA/data/rasters/*_pop_*.tif"
)

output_antyodaya_variables = os.path.join(
    base_dir,
    "Sources/ANTYODAYA/data/variables/antyodaya/antyodaya_variables.csv"
)

os.makedirs(os.path.dirname(output_antyodaya_variables), exist_ok=True)

# ---------------------------------------------------------
# 2. FUNCTIONS
# ---------------------------------------------------------

def load_antyodaya(path):
    df = pd.read_excel(path)
    return df


def create_geopoints(df):
    geom = [Point(xy) for xy in zip(df.village_longitude, df.village_latitude)]
    return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")


def load_revenue_circles(path):
    return gpd.read_file(path)


def spatial_join_points_polygons(points_gdf, polygons_gdf):
    if points_gdf.crs != polygons_gdf.crs:
        points_gdf = points_gdf.to_crs(polygons_gdf.crs)
    return gpd.sjoin(points_gdf, polygons_gdf, how="left", predicate="within")


def load_bharat_maps(path):
    return gpd.read_file(path)


def fix_untagged_with_bharat_maps(result, polygons_gdf, bharat_maps_villages):

    untagged = result[result.revenue_ci.isna()]
    tagged = result.dropna(subset=["revenue_ci"])

    untagged_bm = bharat_maps_villages[
        bharat_maps_villages.vil_lgd.isin(untagged.village_code.to_list())
    ].copy()

    untagged_bm["geometry"] = untagged_bm.geometry.centroid
    untagged_bm = untagged_bm.to_crs(polygons_gdf.crs)

    untagged_bm = gpd.sjoin(
        untagged_bm, polygons_gdf, how="left", predicate="within"
    )

    untagged_fixed = pd.merge(
        untagged.drop(["object_id", "revenue_ci"], axis=1),
        untagged_bm[["vil_lgd", "object_id", "revenue_ci"]],
        left_on="village_code",
        right_on="vil_lgd",
        how="left"
    )[untagged.columns]

    return pd.concat([tagged, untagged_fixed], ignore_index=True)


def compute_urban_population(urban_gdf, worldpop_raster):

    urban_gdf = urban_gdf.to_crs(worldpop_raster.crs)

    stats = zonal_stats(
        urban_gdf,
        worldpop_raster.read(1),
        affine=worldpop_raster.transform,
        stats=["sum"],
        nodata=worldpop_raster.nodata,
        geojson_out=True
    )

    dfs = [pd.DataFrame([f["properties"]]) for f in stats]
    pop_df = pd.concat(dfs, ignore_index=True)
    pop_df.rename(columns={"sum": "sum_population"}, inplace=True)

    return pop_df


def derive_urban_household_indicators(pop_df):

    pop_df["urban_hhd"] = pop_df["sum_population"] / 4.3

    urban_hhd = pop_df.groupby("object_id")[["urban_hhd"]].sum().reset_index()
    urban_hhd["urban_electricity"] = urban_hhd["urban_hhd"] * 20
    urban_hhd["urban_tele"] = urban_hhd["urban_hhd"] * 3
    urban_hhd["urban_hhd_pipe"] = urban_hhd["urban_hhd"] * 0.1873
    urban_hhd["urban_no_sanitation"] = urban_hhd["urban_hhd"] * 0.063

    return urban_hhd


def export_outputs(result_final):

    result_final.to_csv(output_tagged, index=False)

    result_final[
        [
            "gp_code", "village_code", "object_id", "revenue_ci",
            "net_sown_area_in_hac", "total_hhd",
            "availablility_hours_of_domestic_electricity",
            "availability_of_telephone_services",
            "total_hhd_having_piped_water_connection",
            "total_hhd_not_having_sanitary_latrines"
        ]
    ].to_csv(output_vul, index=False)


def build_rc_level_vulnerability_variables(
    urban_hhd,
    gdf_polygons
):
    """
    Builds Revenue-Circle level vulnerability variables using:
    - Rural Antyodaya vulnerability file
    - Urban household estimates
    """

    print("Loading vulnerability CSV...")
    vul_df = pd.read_csv(output_vul)

    # --------------------------------------------------
    # 1. Rural households & net sown area
    # --------------------------------------------------

    vul_df = vul_df.rename(columns={"total_hhd": "rural_hhd"})

    rural_hhd = (
        vul_df.groupby("object_id")[["rural_hhd"]]
        .sum()
        .reset_index()
    )

    net_sown_area_in_hac_rc = (
        vul_df.groupby("object_id")[["net_sown_area_in_hac"]]
        .sum()
        .reset_index()
    )

    # --------------------------------------------------
    # 2. Total households (urban + rural)
    # --------------------------------------------------

    total_hhd = urban_hhd.merge(
        rural_hhd, on="object_id", how="outer"
    ).fillna(0)

    total_hhd["total_hhd"] = (
        total_hhd["urban_hhd"] + total_hhd["rural_hhd"]
    )

    # --------------------------------------------------
    # 3. Electricity vulnerability
    # --------------------------------------------------

    electricity_dict = {1: 2.5, 2: 6, 3: 10, 4: 12, 5: 0}

    elect_df = vul_df.replace(
        {"availablility_hours_of_domestic_electricity": electricity_dict}
    )[
        ["object_id", "rural_hhd", "availablility_hours_of_domestic_electricity"]
    ]

    elect_df["rural_electricity"] = (
        elect_df["rural_hhd"]
        * elect_df["availablility_hours_of_domestic_electricity"]
    )

    elect_df = (
        elect_df.groupby("object_id")[["rural_hhd", "rural_electricity"]]
        .sum()
        .reset_index()
    )

    rc_electricity = elect_df.merge(
        urban_hhd, on="object_id", how="outer"
    ).fillna(0)

    rc_electricity["total_electricity"] = (
        rc_electricity["rural_electricity"]
        + rc_electricity["urban_electricity"]
    )

    rc_electricity["total_hhd"] = (
        rc_electricity["rural_hhd"]
        + rc_electricity["urban_hhd"]
    )

    rc_electricity["avg_electricity"] = (
        rc_electricity["total_electricity"]
        / rc_electricity["total_hhd"]
    )

    # --------------------------------------------------
    # 4. Telephone vulnerability
    # --------------------------------------------------

    telephone_df = vul_df.copy()
    telephone_df["rural_tele"] = (
        telephone_df["rural_hhd"]
        * telephone_df["availability_of_telephone_services"]
    )

    telephone_df = (
        telephone_df.groupby("object_id")[["rural_hhd", "rural_tele"]]
        .sum()
        .reset_index()
    )

    rc_tele = telephone_df.merge(
        urban_hhd[["object_id", "urban_hhd", "urban_tele"]],
        on="object_id",
        how="outer"
    ).fillna(0)

    rc_tele["total_tele"] = rc_tele["rural_tele"] + rc_tele["urban_tele"]
    rc_tele["total_hhd"] = rc_tele["rural_hhd"] + rc_tele["urban_hhd"]
    rc_tele["avg_tele"] = (rc_tele["total_tele"] / rc_tele["total_hhd"]).round()

    # --------------------------------------------------
    # 5. Piped water vulnerability
    # --------------------------------------------------

    pipe_df = (
        vul_df.groupby("object_id")[["total_hhd_having_piped_water_connection"]]
        .sum()
        .reset_index()
    )

    pipe_df = pipe_df.merge(
        urban_hhd[["object_id", "urban_hhd_pipe"]],
        on="object_id",
        how="outer"
    ).fillna(0)

    pipe_df["rc_piped_hhds"] = (
        pipe_df["urban_hhd_pipe"]
        + pipe_df["total_hhd_having_piped_water_connection"]
    )

    pipe_df = pipe_df.merge(
        total_hhd[["object_id", "total_hhd"]],
        on="object_id"
    )

    pipe_df["rc_piped_hhds_pct"] = (
        100 * pipe_df["rc_piped_hhds"] / pipe_df["total_hhd"]
    )

    # --------------------------------------------------
    # 6. Sanitation vulnerability
    # --------------------------------------------------

    nosan_df = (
        vul_df.groupby("object_id")[["total_hhd_not_having_sanitary_latrines"]]
        .sum()
        .reset_index()
    )

    nosan_df = nosan_df.merge(
        urban_hhd[["object_id", "urban_no_sanitation"]],
        on="object_id",
        how="outer"
    ).fillna(0)

    nosan_df["rc_nosanitation_hhds"] = (
        nosan_df["urban_no_sanitation"]
        + nosan_df["total_hhd_not_having_sanitary_latrines"]
    )

    nosan_df = nosan_df.merge(
        total_hhd[["object_id", "total_hhd"]],
        on="object_id"
    )

    nosan_df["rc_nosanitation_hhds_pct"] = (
        100 * nosan_df["rc_nosanitation_hhds"] / nosan_df["total_hhd"]
    )

    # --------------------------------------------------
    # 7. Assemble Antyodaya master variable table
    # --------------------------------------------------

    antyodaya_master_df = net_sown_area_in_hac_rc.merge(
        rc_electricity[["object_id", "avg_electricity"]],
        on="object_id",
        how="outer"
    )

    antyodaya_master_df = antyodaya_master_df.merge(
        rc_tele[["object_id", "avg_tele"]],
        on="object_id",
        how="outer"
    )

    antyodaya_master_df = antyodaya_master_df.merge(
        pipe_df[["object_id", "rc_piped_hhds_pct"]],
        on="object_id",
        how="outer"
    )

    antyodaya_master_df = antyodaya_master_df.merge(
        nosan_df[["object_id", "rc_nosanitation_hhds_pct"]],
        on="object_id",
        how="outer"
    )

    antyodaya_master_df = gdf_polygons.merge(
        antyodaya_master_df, on="object_id", how="outer"
    )

    antyodaya_master_df = antyodaya_master_df.merge(
        total_hhd[["object_id", "total_hhd"]],
        on="object_id"
    )

    antyodaya_master_df["total_hhd"] = (
        antyodaya_master_df["total_hhd"].round(0)
    )

    # --------------------------------------------------
    # 8. Final cleanup
    # --------------------------------------------------

    antyodaya_variables_df = antyodaya_master_df.drop(
        columns=[
            "geometry", "district_1", "revenue_cr",
            "HQ", "area", "are_new"
        ],
        errors="ignore"
    )

    return antyodaya_variables_df


# ---------------------------------------------------------
# 3. MAIN PIPELINE
# ---------------------------------------------------------

def main():

    anta = load_antyodaya(antyodaya_file)
    gdf_points = create_geopoints(anta)

    revenue_polygons = load_revenue_circles(revenue_circle_file)
    result = spatial_join_points_polygons(gdf_points, revenue_polygons)

    bharat_maps = load_bharat_maps(bharat_maps_file)
    result_final = fix_untagged_with_bharat_maps(result, revenue_polygons, bharat_maps)

    export_outputs(result_final)

    urban_shapes = gpd.read_file(urban_shape_file)
    worldpop = rasterio.open(worldpop_raster_file)

    pop_df = compute_urban_population(urban_shapes, worldpop)
    urban_hhd = derive_urban_household_indicators(pop_df)

    antyodaya_vars = build_rc_level_vulnerability_variables(
        urban_hhd, revenue_polygons
    )

    antyodaya_vars.to_csv(output_antyodaya_variables, index=False)

    print("Pipeline completed successfully")


if __name__ == "__main__":
    main()
