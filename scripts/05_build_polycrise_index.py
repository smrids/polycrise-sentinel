"""
05_build_polycrise_index.py — Polycrise Sentinel
==================================================
Merges the four crisis dimension scores and computes the composite
Polycrise Exposure Index (PEI) for each country-year.

Inputs (from data/processed/):
  acled_annual.csv    — conflict_score (0–1)
  emdat_annual.csv    — disaster_score (0–1)
  imf_annual.csv      — economic_score (0–1)
  who_gho_annual.csv  — health_shock   (0–1)

Polycrise Exposure Index:
  PEI = Σ (weight_i × score_i)
  Weights defined in config.POLYCRISE_WEIGHTS.

Polycrise threshold:
  A country-year is classified as a "polycrise year" if ≥ 3 of the 4
  crisis dimensions exceed their 75th percentile simultaneously.
  This operationalises simultaneity — the defining feature of a polycrise.

Outputs:
  data/processed/polycrise_index.csv   — full panel with PEI and crisis flags
  outputs/polycrise_heatmap.png        — country × year heatmap of PEI
  outputs/polycrise_summary.xlsx       — summary statistics
"""

import os, sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (DATA_PROCESSED, OUTPUTS, POLYCRISE_WEIGHTS,
                    ISO3_META, START_YEAR, END_YEAR)

PROC_OUT     = os.path.join(DATA_PROCESSED, "polycrise_index.csv")
HEATMAP_OUT  = os.path.join(OUTPUTS, "polycrise_heatmap.png")
SUMMARY_OUT  = os.path.join(OUTPUTS, "polycrise_summary.xlsx")

# Crisis threshold: upper quartile of each dimension
POLYCRISE_THRESH_QUANTILE = 0.75
# Number of dimensions that must exceed threshold simultaneously
POLYCRISE_N_DIMS = 3


def load_all() -> pd.DataFrame:
    """Load all processed dimension files and create a full country-year panel."""
    iso3s = list(ISO3_META.keys())
    years = list(range(START_YEAR, END_YEAR + 1))

    # Full panel (so missing data is explicit, not dropped)
    panel = pd.MultiIndex.from_product(
        [iso3s, years], names=["iso3", "year"]
    ).to_frame(index=False)

    files = {
        "conflict": os.path.join(DATA_PROCESSED, "acled_annual.csv"),
        "disaster": os.path.join(DATA_PROCESSED, "emdat_annual.csv"),
        "economic": os.path.join(DATA_PROCESSED, "imf_annual.csv"),
        "health":   os.path.join(DATA_PROCESSED, "who_gho_annual.csv"),
    }

    score_cols = {
        "conflict": "conflict_score",
        "disaster": "disaster_score",
        "economic": "economic_score",
        "health":   "health_shock",
    }

    for key, path in files.items():
        if not os.path.exists(path):
            print(f"  ⚠ {path} not found — {key} score will be NaN")
            panel[score_cols[key]] = np.nan
            continue
        df = pd.read_csv(path, usecols=lambda c: c in ["iso3", "year", score_cols[key]])
        panel = panel.merge(df[["iso3", "year", score_cols[key]]], on=["iso3", "year"], how="left")

    return panel, score_cols


def compute_pei(panel: pd.DataFrame, score_cols: dict) -> pd.DataFrame:
    weights = POLYCRISE_WEIGHTS

    # Weighted composite index — treat NaN as 0 (conservative)
    panel["PEI"] = (
        weights["conflict_score"] * panel["conflict_score"].fillna(0)
        + weights["disaster_score"] * panel["disaster_score"].fillna(0)
        + weights["economic_score"] * panel["economic_score"].fillna(0)
        + weights["health_shock"]   * panel["health_shock"].fillna(0)
    )

    # Per-dimension polycrise threshold (75th percentile of non-zero obs)
    thresholds = {}
    for key, col in score_cols.items():
        if col in panel.columns:
            vals = panel[col].dropna()
            thresholds[col] = vals.quantile(POLYCRISE_THRESH_QUANTILE)
            panel[f"{col}_flag"] = (panel[col] >= thresholds[col]).astype(int)
        else:
            thresholds[col]      = np.nan
            panel[f"{col}_flag"] = 0

    flag_cols = [f"{col}_flag" for col in score_cols.values()]
    panel["n_crises_above_threshold"] = panel[flag_cols].sum(axis=1)
    panel["is_polycrise_year"] = (
        panel["n_crises_above_threshold"] >= POLYCRISE_N_DIMS
    ).astype(int)

    # Add metadata
    panel["income_group"] = panel["iso3"].map(lambda x: ISO3_META.get(x, {}).get("income", ""))
    panel["region"]       = panel["iso3"].map(lambda x: ISO3_META.get(x, {}).get("region", ""))
    panel["country_name"] = panel["iso3"].map(lambda x: ISO3_META.get(x, {}).get("name", x))

    print("\nPolycrise dimension thresholds (75th percentile):")
    for col, t in thresholds.items():
        print(f"  {col:<30} {t:.3f}")

    n_poly = panel["is_polycrise_year"].sum()
    pct    = 100 * n_poly / len(panel)
    print(f"\nPolycrise years identified: {n_poly} / {len(panel)} ({pct:.1f}%)")

    return panel


def plot_heatmap(panel: pd.DataFrame):
    """Country × year heatmap of the Polycrise Exposure Index."""
    pivot = panel.pivot(index="country_name", columns="year", values="PEI")
    pivot = pivot.sort_values(pivot.columns[-1], ascending=False)

    fig, ax = plt.subplots(figsize=(18, 12))
    sns.heatmap(
        pivot,
        cmap="YlOrRd",
        vmin=0, vmax=1,
        ax=ax,
        linewidths=0.3,
        linecolor="white",
        cbar_kws={"label": "Polycrise Exposure Index (0–1)"},
    )
    ax.set_title(
        "Polycrise Exposure Index by Country and Year (2010–2024)\n"
        "Composite of conflict, disaster, economic shock, and health system stress",
        fontsize=13, pad=14,
    )
    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=45, labelsize=9)
    ax.tick_params(axis="y", labelsize=9)

    plt.tight_layout()
    plt.savefig(HEATMAP_OUT, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Heatmap saved → {HEATMAP_OUT}")


def main():
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    os.makedirs(OUTPUTS, exist_ok=True)

    print("Building Polycrise Exposure Index …\n")
    panel, score_cols = load_all()
    panel = compute_pei(panel, score_cols)

    panel.to_csv(PROC_OUT, index=False)
    print(f"✓ Polycrise index saved → {PROC_OUT}  ({len(panel):,} rows)")

    # Summary tables
    poly_by_country = (
        panel.groupby("iso3")[["is_polycrise_year", "PEI"]]
             .agg(polycrise_years=("is_polycrise_year", "sum"),
                  mean_PEI=("PEI", "mean"))
             .reset_index()
             .sort_values("polycrise_years", ascending=False)
    )
    poly_by_region = (
        panel.groupby("region")[["is_polycrise_year", "PEI"]]
             .agg(polycrise_years=("is_polycrise_year", "sum"),
                  mean_PEI=("PEI", "mean"),
                  n_country_years=("PEI", "count"))
             .reset_index()
    )

    with pd.ExcelWriter(SUMMARY_OUT, engine="openpyxl") as xls:
        panel.to_excel(xls,              sheet_name="Full Panel",       index=False)
        poly_by_country.to_excel(xls,   sheet_name="By Country",       index=False)
        poly_by_region.to_excel(xls,    sheet_name="By Region",        index=False)

    print(f"✓ Summary workbook saved → {SUMMARY_OUT}")

    print("\nTop 10 countries by total polycrise years:")
    print(poly_by_country.head(10).to_string(index=False))

    try:
        plot_heatmap(panel)
    except Exception as e:
        print(f"  ⚠ Heatmap failed: {e}  (non-fatal)")


if __name__ == "__main__":
    main()
