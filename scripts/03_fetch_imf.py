"""
03_fetch_imf.py — Polycrise Sentinel
======================================
Fetches economic stress indicators from the IMF DataMapper API (no key needed).

Indicators fetched:
  - NGDP_RPCH  : Real GDP growth rate (%)
  - GGX_NGDP   : General government expenditure as % of GDP
  - BCA_NGDPD  : Current account balance as % of GDP
  - LUR        : Unemployment rate (%)
  - PCPIPCH    : Inflation rate (CPI, %)

Economic stress score:
  Captures fiscal contraction + economic shock severity.
  score = normalised( GDP_contraction + inflation_shock + unemployment_shock )

API docs: https://www.imf.org/external/datamapper/api/v1/

Output:
  data/raw/imf_raw.json
  data/processed/imf_annual.csv
"""

import os, sys, json, time
import urllib.request
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_RAW, DATA_PROCESSED, ISO3_LIST, START_YEAR, END_YEAR

RAW_OUT  = os.path.join(DATA_RAW,       "imf_raw.json")
PROC_OUT = os.path.join(DATA_PROCESSED, "imf_annual.csv")

IMF_BASE = "https://www.imf.org/external/datamapper/api/v1"

INDICATORS = {
    "NGDP_RPCH": "gdp_growth_pct",
    "GGX_NGDP":  "govt_expenditure_gdp_pct",
    "BCA_NGDPD": "current_account_gdp_pct",
    "LUR":        "unemployment_rate",
    "PCPIPCH":   "inflation_rate",
}


def fetch_indicator(indicator: str) -> dict:
    """Fetch all countries × years for one IMF indicator."""
    url = f"{IMF_BASE}/{indicator}"
    print(f"  Fetching {indicator} …")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ⚠ Error fetching {indicator}: {e}")
        return {}


def parse_indicator(raw: dict, indicator: str, friendly_name: str,
                    iso3_list: list[str]) -> pd.DataFrame:
    """Parse IMF JSON response into long-format DataFrame for study countries."""
    values_block = raw.get("values", {}).get(indicator, {})
    rows = []
    for iso3 in iso3_list:
        # IMF uses ISO2 internally but also accepts ISO3 in some endpoints.
        # The DataMapper API returns data keyed by ISO3.
        country_data = values_block.get(iso3, {})
        for year_str, val in country_data.items():
            try:
                year = int(year_str)
                if START_YEAR <= year <= END_YEAR:
                    rows.append({"iso3": iso3, "year": year, friendly_name: val})
            except ValueError:
                continue
    return pd.DataFrame(rows)


def compute_economic_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive an economic stress score from the merged indicators.

    Logic:
      - GDP contraction: negative growth → stress; cap at -15%
      - Inflation shock: >20% inflation → stress; log-scaled
      - Unemployment shock: >10% → stress; scaled
    """
    df = df.copy()

    # GDP contraction: higher when growth is more negative
    # Clamp between -15 and +15, then invert so lower growth = higher stress
    df["gdp_growth_pct"]      = df["gdp_growth_pct"].clip(-15, 15)
    df["gdp_stress"]          = (-df["gdp_growth_pct"] + 15) / 30   # 0–1

    # Inflation shock: log-scaled, 0 at 0%, 1 at 100%+ inflation
    df["inflation_rate"]      = df["inflation_rate"].clip(0, 200)
    df["inflation_stress"]    = np.log1p(df["inflation_rate"]) / np.log1p(200)

    # Unemployment: 0 at 0%, 1 at 30%+
    df["unemployment_rate"]   = df["unemployment_rate"].fillna(0).clip(0, 30)
    df["unemployment_stress"] = df["unemployment_rate"] / 30

    df["raw_score"] = (
        0.5 * df["gdp_stress"]
        + 0.3 * df["inflation_stress"]
        + 0.2 * df["unemployment_stress"]
    )

    mn, mx = df["raw_score"].min(), df["raw_score"].max()
    df["economic_score"] = (df["raw_score"] - mn) / (mx - mn + 1e-9)

    return df[["iso3", "year", "gdp_growth_pct", "inflation_rate",
               "unemployment_rate", "govt_expenditure_gdp_pct",
               "current_account_gdp_pct", "economic_score"]]


def main():
    os.makedirs(DATA_RAW,       exist_ok=True)
    os.makedirs(DATA_PROCESSED, exist_ok=True)

    print("Fetching IMF DataMapper indicators (no API key required) …\n")

    all_raw = {}
    dfs     = []

    for indicator, friendly in INDICATORS.items():
        raw = fetch_indicator(indicator)
        all_raw[indicator] = raw
        df_ind = parse_indicator(raw, indicator, friendly, ISO3_LIST)
        if not df_ind.empty:
            dfs.append(df_ind)
        time.sleep(0.5)

    # Save raw JSON
    with open(RAW_OUT, "w") as f:
        json.dump(all_raw, f)
    print(f"\n✓ Raw IMF JSON saved → {RAW_OUT}")

    if not dfs:
        print("⚠ No IMF data returned. Check ISO3 codes and network.")
        sys.exit(1)

    # Merge all indicators on iso3 + year
    df_merged = dfs[0]
    for df_ind in dfs[1:]:
        df_merged = df_merged.merge(df_ind, on=["iso3", "year"], how="outer")

    # Fill missing indicators with panel median (better than 0)
    for col in ["gdp_growth_pct", "inflation_rate", "unemployment_rate",
                "govt_expenditure_gdp_pct", "current_account_gdp_pct"]:
        if col in df_merged.columns:
            df_merged[col] = df_merged[col].fillna(df_merged[col].median())
        else:
            df_merged[col] = 0.0

    df_score = compute_economic_score(df_merged)
    df_score.to_csv(PROC_OUT, index=False)

    print(f"✓ Economic stress scores saved → {PROC_OUT}  ({len(df_score):,} rows)")
    print(df_score.describe())

    top = df_score.nlargest(10, "economic_score")[
        ["iso3", "year", "gdp_growth_pct", "inflation_rate", "economic_score"]
    ]
    print("\nTop 10 country-years by economic stress:")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
