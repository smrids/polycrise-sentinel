"""
02_process_emdat.py — Polycrise Sentinel
=========================================
Processes the EM-DAT global disaster database to produce a country-year
natural disaster severity score.

EM-DAT does NOT have a public API — you must download the data manually:
  1. Go to https://www.emdat.be/
  2. Register for free
  3. Download the "Public" dataset as Excel (.xlsx)
  4. Save it to:  data/raw/emdat_public.xlsx

This script then processes that file.

Output:
  data/processed/emdat_annual.csv — country-year disaster severity score

Disaster severity score (per country-year):
  raw = log1p( total_deaths + 0.01 * total_affected + 0.001 * total_damage_usd )
  Normalised 0–1 across the full panel.
"""

import os, sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_RAW, DATA_PROCESSED, ISO3_LIST, START_YEAR, END_YEAR

EMDAT_FILE = os.path.join(DATA_RAW, "emdat_public.xlsx")
PROC_OUT   = os.path.join(DATA_PROCESSED, "emdat_annual.csv")

# EM-DAT disaster types to include (excluding technological/industrial)
DISASTER_TYPES = [
    "Earthquake", "Flood", "Storm", "Extreme temperature",
    "Drought", "Landslide", "Volcanic activity", "Wildfire",
    "Epidemic",   # includes disease outbreaks
]


def load_emdat(path: str) -> pd.DataFrame:
    """Load and normalise EM-DAT Excel into a clean DataFrame."""
    print(f"Loading EM-DAT from {path} …")
    # Custom EM-DAT exports (e.g. from the post-2024 portal) have no metadata
    # header rows — data begins at row 0.  The legacy public download used
    # header=6; we auto-detect by checking for 'ISO' in the first-row columns.
    df_probe = pd.read_excel(path, header=0, nrows=0)
    header_row = 0 if "ISO" in df_probe.columns else 6
    df = pd.read_excel(path, header=header_row)

    # Standardise column names (lowercase, spaces → underscores)
    df.columns = df.columns.str.strip().str.lower().str.replace(r"[\s/]+", "_", regex=True)

    # Key columns vary by EM-DAT version — handle all known variants.
    # Custom export uses 'start_year' (not 'year') and 'iso' (not 'iso3').
    col_map = {
        "iso":                              "iso3",
        "iso_code":                         "iso3",
        "country_iso":                      "iso3",
        "year":                             "year",
        "start_year":                       "year",   # custom export column name
        "disaster_type":                    "disaster_type",
        "total_deaths":                     "total_deaths",
        "no._affected":                     "total_affected",
        "total_affected":                   "total_affected",
        "total_damage_('000_us$)":          "total_damage_kUSD",
        "total_damage,_adjusted_('000_us$)": "total_damage_kUSD",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Remove duplicate column names that arise when both the raw and adjusted
    # damage columns map to the same target name (keep last = adjusted value,
    # which is inflation-corrected and better for cross-year comparison).
    df = df.loc[:, ~df.columns.duplicated(keep="last")]

    # Ensure required columns exist
    for col in ["iso3", "year", "disaster_type"]:
        if col not in df.columns:
            raise ValueError(
                f"Column '{col}' not found. Columns available: {list(df.columns)}\n"
                "Check the EM-DAT Excel format matches expectations."
            )

    for col in ["total_deaths", "total_affected", "total_damage_kUSD"]:
        if col not in df.columns:
            df[col] = 0

    return df


def compute_disaster_score(df: pd.DataFrame) -> pd.DataFrame:
    """Filter, aggregate, and normalise disaster impact."""
    df = df[
        df["iso3"].isin(ISO3_LIST)
        & df["year"].between(START_YEAR, END_YEAR)
        & df["disaster_type"].isin(DISASTER_TYPES)
    ].copy()

    for col in ["total_deaths", "total_affected", "total_damage_kUSD"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    agg = df.groupby(["iso3", "year"]).agg(
        n_disasters       = ("disaster_type", "count"),
        total_deaths      = ("total_deaths", "sum"),
        total_affected    = ("total_affected", "sum"),
        total_damage_kUSD = ("total_damage_kUSD", "sum"),
    ).reset_index()

    # Raw score: deaths weighted most, then affected population, then economic damage
    agg["raw_score"] = np.log1p(
        agg["total_deaths"]
        + 0.01  * agg["total_affected"]
        + 0.001 * agg["total_damage_kUSD"] * 1000   # convert kUSD → USD
    )

    mn, mx = agg["raw_score"].min(), agg["raw_score"].max()
    agg["disaster_score"] = (agg["raw_score"] - mn) / (mx - mn + 1e-9)

    return agg[["iso3", "year", "n_disasters", "total_deaths",
                "total_affected", "total_damage_kUSD", "disaster_score"]]


def main():
    os.makedirs(DATA_PROCESSED, exist_ok=True)

    if not os.path.exists(EMDAT_FILE):
        print(
            f"\n⚠  EM-DAT file not found at:\n   {EMDAT_FILE}\n\n"
            "   To download:\n"
            "     1. Go to https://www.emdat.be/ and register (free)\n"
            "     2. Download the Public dataset as Excel\n"
            "     3. Save it to data/raw/emdat_public.xlsx\n"
            "   Then re-run this script.\n"
        )
        sys.exit(1)

    df_raw   = load_emdat(EMDAT_FILE)
    df_score = compute_disaster_score(df_raw)
    df_score.to_csv(PROC_OUT, index=False)

    print(f"✓ Disaster scores saved → {PROC_OUT}  ({len(df_score):,} rows)")
    print(df_score.describe())

    # Highest-scoring country-years
    top = df_score.nlargest(10, "disaster_score")[
        ["iso3", "year", "n_disasters", "total_deaths", "disaster_score"]
    ]
    print("\nTop 10 country-years by disaster severity:")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
