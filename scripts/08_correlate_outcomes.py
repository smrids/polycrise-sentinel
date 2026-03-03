"""
08_correlate_outcomes.py — Polycrise Sentinel
===============================================
Core analysis: does governance response type moderate the relationship between
polycrise exposure and health system resilience (UHC coverage)?

Research questions answered:
  RQ1: Which governance response types are most common during polycrises?
  RQ2: Do governance response types predict UHC trajectory during polycrises?
  RQ3: Do income group and region moderate these relationships?
  RQ4: Which specific crisis combinations (conflict + X) are most damaging
       to UHC coverage?

Methods:
  1. Panel merge: polycrise_index + llm_tagged_docs + who_gho (UHC outcome)
  2. Fixed-effects regression: ΔUHC ~ PEI + governance_type + income + region
  3. Interaction model: ΔUHC ~ PEI × governance_type
  4. Subgroup analysis by income group

Outputs:
  outputs/rq1_response_type_frequency.png
  outputs/rq2_uhc_by_response_type.png
  outputs/rq3_regression_results.xlsx
  outputs/rq4_crisis_combination_matrix.png
  outputs/analysis_results.xlsx         — master results workbook
"""

import os, sys, warnings
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_PROCESSED, OUTPUTS, ISO3_META

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Input files ────────────────────────────────────────────────────────────────
INDEX_CSV    = os.path.join(DATA_PROCESSED, "polycrise_index.csv")
TAGGED_CSV   = os.path.join(DATA_PROCESSED, "llm_tagged_docs.csv")
GHO_CSV      = os.path.join(DATA_PROCESSED, "who_gho_annual.csv")

# ── Output files ───────────────────────────────────────────────────────────────
RESULTS_XLS  = os.path.join(OUTPUTS, "analysis_results.xlsx")
FIG_RQ1      = os.path.join(OUTPUTS, "rq1_response_frequency.png")
FIG_RQ2      = os.path.join(OUTPUTS, "rq2_uhc_by_response_type.png")
FIG_RQ4      = os.path.join(OUTPUTS, "rq4_crisis_combination_matrix.png")

RESPONSE_COLORS = {
    "CENTRALISE":   "#E63946",
    "DECENTRALISE": "#2196F3",
    "INTEGRATE":    "#4CAF50",
    "PARTNER":      "#FF9800",
    "INFORMAL":     "#9C27B0",
    "RESTRICT":     "#F44336",
    "UNCLEAR":      "#9E9E9E",
}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data(skip_llm: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = [INDEX_CSV, GHO_CSV]
    if not skip_llm:
        required.append(TAGGED_CSV)

    missing = [f for f in required if not os.path.exists(f)]
    if missing:
        print("⚠ Missing input files:")
        for f in missing:
            print(f"   {f}")
        print("Run the preceding pipeline stages first.")
        sys.exit(1)

    idx = pd.read_csv(INDEX_CSV)
    gho = pd.read_csv(GHO_CSV)

    if skip_llm or not os.path.exists(TAGGED_CSV):
        print("  ℹ No LLM-tagged docs — governance response analyses (RQ1/RQ2) will be skipped.")
        tagged = pd.DataFrame(columns=["iso3", "date", "primary_type"])
    else:
        tagged = pd.read_csv(TAGGED_CSV)

    return idx, tagged, gho


def build_panel(idx: pd.DataFrame, tagged: pd.DataFrame,
                gho: pd.DataFrame) -> pd.DataFrame:
    """Merge all data sources into an analysis panel."""

    # Dominant governance response per country-year (most frequent type)
    if "primary_type" in tagged.columns and "date" in tagged.columns:
        tagged["year"] = tagged["date"].str[:4].astype(float, errors="ignore")
        tagged = tagged.dropna(subset=["year"])
        tagged["year"] = tagged["year"].astype(int)

        # Dominant = mode of primary_type per country-year
        dom_response = (
            tagged.groupby(["iso3", "year"])["primary_type"]
                  .agg(lambda s: s.mode()[0] if len(s) > 0 else "UNCLEAR")
                  .reset_index()
                  .rename(columns={"primary_type": "dominant_response"})
        )
        n_docs = tagged.groupby(["iso3", "year"]).size().reset_index(name="n_docs")
        dom_response = dom_response.merge(n_docs, on=["iso3", "year"], how="left")
    else:
        dom_response = pd.DataFrame(columns=["iso3", "year", "dominant_response", "n_docs"])

    # UHC outcome
    gho_subset = gho[["iso3", "year", "uhc_index"]].dropna() if "uhc_index" in gho.columns else pd.DataFrame()

    # Merge
    panel = idx.merge(dom_response, on=["iso3", "year"], how="left")
    if not gho_subset.empty:
        panel = panel.merge(gho_subset, on=["iso3", "year"], how="left")
    else:
        panel["uhc_index"] = np.nan

    # Year-on-year UHC change
    panel = panel.sort_values(["iso3", "year"])
    panel["uhc_change"] = panel.groupby("iso3")["uhc_index"].diff()

    # Add metadata
    panel["income_group"] = panel["iso3"].map(lambda x: ISO3_META.get(x, {}).get("income", ""))
    panel["region"]       = panel["iso3"].map(lambda x: ISO3_META.get(x, {}).get("region", ""))

    return panel


# ── RQ1: Response type frequency during polycrises ─────────────────────────────

def rq1_response_frequency(panel: pd.DataFrame):
    poly = panel[panel["is_polycrise_year"] == 1].copy()

    if "dominant_response" not in poly.columns or poly["dominant_response"].isna().all():
        print("  ⚠ No governance classifications available yet — skipping RQ1 plot.")
        return pd.DataFrame()

    counts = poly["dominant_response"].value_counts()
    pct    = 100 * counts / counts.sum()

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(counts.index, counts.values,
                   color=[RESPONSE_COLORS.get(t, "#9E9E9E") for t in counts.index])
    ax.set_xlabel("Number of polycrise country-years")
    ax.set_title("RQ1: Dominant Governance Response Type During Polycrise Years", fontsize=12)
    for bar, p in zip(bars, pct):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{p:.1f}%", va="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(FIG_RQ1, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ RQ1 figure saved → {FIG_RQ1}")
    return counts.reset_index()


# ── RQ2: UHC trajectory by response type ─────────────────────────────────────

def rq2_uhc_by_response(panel: pd.DataFrame):
    poly = panel[
        (panel["is_polycrise_year"] == 1) & panel["uhc_change"].notna()
    ].copy()

    if poly.empty or "dominant_response" not in poly.columns or poly["dominant_response"].isna().all():
        print("  ⚠ No governance classifications available yet — skipping RQ2 plot.")
        return pd.DataFrame()

    agg = poly.groupby("dominant_response")["uhc_change"].agg(
        mean="mean", sem="sem", n="count"
    ).reset_index()
    agg["ci95"] = 1.96 * agg["sem"]

    fig, ax = plt.subplots(figsize=(9, 5))
    colors  = [RESPONSE_COLORS.get(t, "#9E9E9E") for t in agg["dominant_response"]]
    ax.barh(agg["dominant_response"], agg["mean"],
            xerr=agg["ci95"], color=colors, capsize=4, alpha=0.85)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Mean year-on-year change in UHC Service Coverage Index")
    ax.set_title(
        "RQ2: UHC Trajectory by Governance Response Type\n(During Polycrise Years, 95% CI)",
        fontsize=12,
    )
    for _, row in agg.iterrows():
        ax.text(
            row["mean"] + (0.02 if row["mean"] >= 0 else -0.02),
            list(agg["dominant_response"]).index(row["dominant_response"]),
            f"n={int(row['n'])}", va="center", fontsize=8,
            ha="left" if row["mean"] >= 0 else "right",
        )
    plt.tight_layout()
    plt.savefig(FIG_RQ2, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ RQ2 figure saved → {FIG_RQ2}")
    return agg


# ── RQ3: Regression ───────────────────────────────────────────────────────────

def rq3_regression(panel: pd.DataFrame) -> pd.DataFrame:
    """Fixed-effects OLS: ΔUHC ~ PEI + response_type + income_group + region."""
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        print("  ⚠ statsmodels not installed — skipping regression. Run: pip install statsmodels")
        return pd.DataFrame()

    reg_df = panel.dropna(subset=["uhc_change", "PEI"]).copy()
    # Ensure categorical columns use plain object dtype (statsmodels compatibility)
    for col in ["income_group", "region", "dominant_response"]:
        if col in reg_df.columns:
            reg_df[col] = reg_df[col].astype(object)

    if len(reg_df) < 30:
        print(f"  ⚠ Only {len(reg_df)} obs with UHC change data — regression may be unreliable.")
        if len(reg_df) < 10:
            return pd.DataFrame()

    # Simple model: PEI effect on UHC change
    formula1 = "uhc_change ~ PEI + income_group"
    try:
        model1 = smf.ols(formula1, data=reg_df).fit()
        print("\nRQ3 — OLS: ΔUHC ~ PEI + income_group")
        print(model1.summary2().tables[1].to_string())
        results_df = model1.summary2().tables[1].reset_index()
    except Exception as e:
        print(f"  ⚠ Regression failed: {e}")
        results_df = pd.DataFrame()

    # Interaction model (if governance data available)
    if "dominant_response" in reg_df.columns and reg_df["dominant_response"].notna().sum() > 20:
        try:
            formula2 = "uhc_change ~ PEI * dominant_response + income_group"
            model2   = smf.ols(formula2, data=reg_df).fit()
            print("\nRQ3 — OLS Interaction: ΔUHC ~ PEI × response + income_group")
            print(model2.summary2().tables[1].to_string())
        except Exception as e:
            print(f"  ⚠ Interaction model failed: {e}")

    return results_df


# ── RQ4: Crisis combination matrix ────────────────────────────────────────────

def rq4_crisis_combinations(panel: pd.DataFrame):
    """Heatmap: mean UHC change by combination of crisis dimensions above threshold."""
    flag_cols = [c for c in panel.columns if c.endswith("_flag")]
    if not flag_cols or "uhc_change" not in panel.columns:
        print("  ⚠ Skipping RQ4 — missing flag columns or UHC data.")
        return pd.DataFrame()

    dim_names = {
        "conflict_score_flag": "Conflict",
        "disaster_score_flag": "Disaster",
        "economic_score_flag": "Economic",
        "health_shock_flag":   "Health",
    }

    combos = []
    for _, row in panel.iterrows():
        active = tuple(
            dim_names.get(fc, fc)
            for fc in flag_cols
            if row.get(fc, 0) == 1
        )
        combos.append({
            "combination": " + ".join(sorted(active)) if active else "No crisis",
            "uhc_change":  row["uhc_change"],
            "PEI":         row["PEI"],
        })

    combo_df = pd.DataFrame(combos).dropna(subset=["uhc_change"])
    summary  = combo_df.groupby("combination")["uhc_change"].agg(
        mean_uhc_change="mean", n="count"
    ).reset_index().sort_values("mean_uhc_change")

    if len(summary) > 1:
        fig, ax = plt.subplots(figsize=(10, max(5, len(summary) * 0.5)))
        colors  = ["#E63946" if v < 0 else "#4CAF50" for v in summary["mean_uhc_change"]]
        ax.barh(summary["combination"], summary["mean_uhc_change"], color=colors, alpha=0.85)
        ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlabel("Mean ΔUHC Service Coverage Index")
        ax.set_title("RQ4: UHC Change by Crisis Combination Type", fontsize=12)
        for _, row in summary.iterrows():
            ax.text(
                row["mean_uhc_change"] + 0.01, list(summary["combination"]).index(row["combination"]),
                f"n={int(row['n'])}", va="center", fontsize=8,
            )
        plt.tight_layout()
        plt.savefig(FIG_RQ4, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"✓ RQ4 figure saved → {FIG_RQ4}")

    return summary


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Polycrise Sentinel — Stage 8 analysis")
    parser.add_argument("--no-llm", action="store_true",
                        help="Run analysis without LLM governance classifications (skips RQ1/RQ2)")
    args, _ = parser.parse_known_args()

    os.makedirs(OUTPUTS, exist_ok=True)
    print("Running polycrise analysis …\n")
    if args.no_llm:
        print("  Mode: no-LLM (RQ1/RQ2 governance analyses skipped)\n")

    idx, tagged, gho = load_data(skip_llm=args.no_llm)
    panel = build_panel(idx, tagged, gho)

    print(f"Analysis panel: {len(panel):,} country-years | "
          f"{panel['iso3'].nunique()} countries | "
          f"{panel['year'].min()}–{panel['year'].max()}")
    print(f"Polycrise years: {panel['is_polycrise_year'].sum()} "
          f"({100 * panel['is_polycrise_year'].mean():.1f}%)")

    if "uhc_index" in panel.columns:
        print(f"Country-years with UHC data: {panel['uhc_index'].notna().sum()}")
    print()

    rq1 = rq1_response_frequency(panel)
    rq2 = rq2_uhc_by_response(panel)
    rq3 = rq3_regression(panel)
    rq4 = rq4_crisis_combinations(panel)

    # Save master results
    with pd.ExcelWriter(RESULTS_XLS, engine="openpyxl") as xls:
        panel.to_excel(xls,     sheet_name="Full Analysis Panel", index=False)
        if not rq1.empty:
            rq1.to_excel(xls,   sheet_name="RQ1 Response Frequency", index=False)
        if not rq2.empty:
            rq2.to_excel(xls,   sheet_name="RQ2 UHC by Response",    index=False)
        if not rq3.empty:
            rq3.to_excel(xls,   sheet_name="RQ3 Regression Results", index=False)
        if not rq4.empty:
            rq4.to_excel(xls,   sheet_name="RQ4 Crisis Combinations", index=False)

    print(f"\n✓ Master results workbook → {RESULTS_XLS}")
    print("\nAnalysis complete. Review outputs/ for figures and tables.")


if __name__ == "__main__":
    main()
