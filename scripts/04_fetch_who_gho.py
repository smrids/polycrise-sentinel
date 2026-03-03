"""
04_fetch_who_gho.py — Polycrise Sentinel
==========================================
Fetches health system performance indicators from the WHO Global Health
Observatory (GHO) open API — no API key required.

API docs: https://www.who.int/data/gho/info/gho-odata-api

Indicators fetched:
  UHC_INDEX_REPORTED    — UHC Service Coverage Index (primary outcome)
  HWFP_0000000026       — Health workforce: doctors per 10,000
  HWFP_0000000030       — Health workforce: nurses per 10,000
  WHS4_100              — Hospital beds per 10,000
  WHS7_156              — Out-of-pocket health expenditure as % of current HE
  FINPROTECTION_CATA_TOT_10_POP  — Catastrophic health expenditure (>10% income)

The UHC_INDEX_REPORTED is our primary health system outcome variable —
we will correlate polycrise exposure and governance response against
changes in this indicator over time.

Output:
  data/raw/who_gho_raw.json
  data/processed/who_gho_annual.csv
"""

import os, sys, json, time
import urllib.request, urllib.parse
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_RAW, DATA_PROCESSED, ISO3_LIST, START_YEAR, END_YEAR

RAW_OUT  = os.path.join(DATA_RAW,       "who_gho_raw.json")
PROC_OUT = os.path.join(DATA_PROCESSED, "who_gho_annual.csv")

GHO_BASE = "https://ghoapi.azureedge.net/api"

INDICATORS = {
    "UHC_INDEX_REPORTED":              "uhc_index",
    "HWF_0001":                        "doctors_per10k",
    "HWF_0006":                        "nurses_per10k",
    "WHS6_102":                        "hospital_beds_per10k",
    "GHED_OOPSCHE_SHA2011":            "oop_expenditure_pct",
    "FINPROTECTION_CATA_TOT_10_POP":   "catastrophic_health_exp_pct",
}


def fetch_indicator(indicator: str, iso3_list: list[str]) -> list[dict]:
    """
    Fetch one GHO indicator for all study countries.
    Fetches all data (no country filter to avoid URL length limits)
    and filters in Python.
    """
    print(f"  Fetching {indicator} …")
    all_records = []
    # No $top param — GHO returns all data in one call (rejects $top > API limit)
    url = f"{GHO_BASE}/{indicator}"
    iso_set = set(iso3_list)
    pages   = 0
    try:
        while url and pages < 20:   # guard against infinite pagination
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.loads(r.read())
            records = data.get("value", [])
            # Filter to study countries in Python
            all_records.extend(
                r for r in records if r.get("SpatialDim") in iso_set
            )
            # GHO uses @odata.nextLink for pagination
            url  = data.get("@odata.nextLink")
            pages += 1
            time.sleep(0.3)
        return all_records
    except Exception as e:
        print(f"  ⚠ Error fetching {indicator}: {e}")
        return []


def parse_gho_records(records: list[dict], friendly: str) -> pd.DataFrame:
    """Parse GHO OData records into a clean long DataFrame."""
    rows = []
    for r in records:
        try:
            iso3 = r.get("SpatialDim", "")
            year = int(r.get("TimeDim", 0))
            val  = r.get("NumericValue")
            if iso3 and START_YEAR <= year <= END_YEAR and val is not None:
                rows.append({"iso3": iso3, "year": year, friendly: float(val)})
        except (ValueError, TypeError):
            continue
    df = pd.DataFrame(rows)
    if not df.empty:
        # Average if multiple data points per country-year (e.g. sex-disaggregated)
        df = df.groupby(["iso3", "year"])[friendly].mean().reset_index()
    return df


def compute_health_shock(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute a health_shock indicator = year-on-year decline in UHC index.
    A decline flags acute health system stress; this is combined in the
    polycrise index as the health shock component.
    """
    df = df.sort_values(["iso3", "year"])
    df["uhc_prev_year"] = df.groupby("iso3")["uhc_index"].shift(1)
    df["uhc_change"]    = df["uhc_index"] - df["uhc_prev_year"]

    # health_shock = magnitude of decline (0 if UHC improved or stable)
    df["health_shock_raw"] = (-df["uhc_change"]).clip(lower=0)
    mn, mx = df["health_shock_raw"].min(), df["health_shock_raw"].max()
    df["health_shock"] = (df["health_shock_raw"] - mn) / (mx - mn + 1e-9)

    return df


def main():
    os.makedirs(DATA_RAW,       exist_ok=True)
    os.makedirs(DATA_PROCESSED, exist_ok=True)

    print("Fetching WHO GHO indicators (no API key required) …\n")

    all_raw = {}
    dfs     = []

    for indicator, friendly in INDICATORS.items():
        records = fetch_indicator(indicator, ISO3_LIST)
        all_raw[indicator] = records
        df_ind = parse_gho_records(records, friendly)
        print(f"    → {len(df_ind)} country-year observations")
        if not df_ind.empty:
            dfs.append(df_ind)
        time.sleep(0.5)

    with open(RAW_OUT, "w") as f:
        json.dump(all_raw, f)
    print(f"\n✓ Raw GHO JSON saved → {RAW_OUT}")

    if not dfs:
        print("⚠ No GHO data returned.")
        sys.exit(1)

    # Merge all indicators
    df_merged = dfs[0]
    for df_ind in dfs[1:]:
        df_merged = df_merged.merge(df_ind, on=["iso3", "year"], how="outer")

    # Compute health shock from UHC trajectory
    if "uhc_index" in df_merged.columns:
        df_merged = compute_health_shock(df_merged)
    else:
        df_merged["health_shock"] = np.nan
        print("  ⚠ UHC index not available — health_shock will be NaN")

    df_merged.to_csv(PROC_OUT, index=False)
    print(f"✓ WHO GHO indicators saved → {PROC_OUT}  ({len(df_merged):,} rows)")
    print(df_merged.describe())

    if "uhc_index" in df_merged.columns:
        print("\nUHC index range by country (latest available year):")
        latest = df_merged.sort_values("year").groupby("iso3").last()[
            ["year", "uhc_index"]
        ].sort_values("uhc_index")
        print(latest.to_string())


if __name__ == "__main__":
    main()
