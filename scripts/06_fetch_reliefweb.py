"""
06_fetch_reliefweb.py — Polycrise Sentinel
============================================
Fetches health cluster situation reports and policy documents from the
ReliefWeb API (fully open, no API key required).

For each study country during polycrise years, this script fetches
documents that describe governmental and international health system
responses — the raw material for LLM classification in Script 07.

ReliefWeb API docs: https://apidoc.reliefweb.int/

Document types fetched:
  - Situation reports
  - Policy documents
  - Assessments
  - Guidelines / guidance

Output:
  data/processed/reliefweb_docs.json   — raw API responses
  data/processed/reliefweb_docs.csv    — flattened, one row per document
"""

import os, sys, json, time
import urllib.request, urllib.parse
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (DATA_PROCESSED, ISO3_LIST, ISO3_META,
                    RW_MAX_DOCS_PER_COUNTRY, RW_FIELDS, RELIEFWEB_APPNAME)

RAW_DOCS_JSON = os.path.join(DATA_PROCESSED, "reliefweb_docs.json")
DOCS_CSV      = os.path.join(DATA_PROCESSED, "reliefweb_docs.csv")
INDEX_CSV     = os.path.join(DATA_PROCESSED, "polycrise_index.csv")

def check_reliefweb_appname():
    if not RELIEFWEB_APPNAME:
        print(
            "\n⚠  RELIEFWEB_APPNAME not set.\n"
            "   ReliefWeb now requires a registered appname for all API access.\n"
            "   Register free (instant) at:\n"
            "     https://apidoc.reliefweb.int/parameters#appname\n"
            "   Then:\n"
            "     export RELIEFWEB_APPNAME='your-appname'\n"
            "   and re-run this script.\n"
        )
        sys.exit(1)


RW_BASE = "https://api.reliefweb.int/v1/reports"

# Themes to focus on: health, governance, humanitarian coordination
FOCUS_THEMES = [
    "Health", "Coordination", "Public Health", "Epidemic and Pandemic",
    "Humanitarian Financing",
]


def get_polycrise_country_years() -> dict[str, list[int]]:
    """
    Load the polycrise index and return {iso3: [polycrise_years]} mapping.
    Falls back progressively if no polycrise years are identified:
      1. Try polycrise_index.csv strict threshold
      2. Fall back to top-PEI country-years (top 20% of PEI scores)
      3. Fall back to all study countries + all years
    """
    from config import STUDY_YEARS

    if os.path.exists(INDEX_CSV):
        df = pd.read_csv(INDEX_CSV)

        # First try: strict polycrise years
        poly = df[df["is_polycrise_year"] == 1]
        if not poly.empty:
            mapping = poly.groupby("iso3")["year"].apply(list).to_dict()
            print(f"  Loaded polycrise years for {len(mapping)} countries from index.")
            return mapping

        # Second try: top-20% PEI years (works even with incomplete dimensions)
        threshold = df["PEI"].quantile(0.80)
        top_pei   = df[df["PEI"] >= threshold]
        if not top_pei.empty:
            mapping = top_pei.groupby("iso3")["year"].apply(list).to_dict()
            print(
                f"  No strict polycrise years found (incomplete dimensions?).\n"
                f"  Falling back to top-20% PEI years — {len(top_pei)} country-years, "
                f"{len(mapping)} countries (PEI ≥ {threshold:.3f})."
            )
            return mapping

    # Final fallback: all countries, all years
    print("  ⚠ Using all countries and years as fallback.")
    return {iso3: STUDY_YEARS for iso3 in ISO3_LIST}


def fetch_docs_for_country(iso3: str, years: list[int],
                           max_docs: int) -> list[dict]:
    """Fetch ReliefWeb reports mentioning health system response for one country."""
    country_name = ISO3_META.get(iso3, {}).get("name", iso3)
    year_filter  = [str(y) for y in years]

    payload = json.dumps({
        "filter": {
            "operator": "AND",
            "conditions": [
                {
                    "field":  "country.iso3",
                    "value":  iso3,
                },
                {
                    "field":  "date.original",
                    "value": {
                        "from": f"{min(years)}-01-01T00:00:00+00:00",
                        "to":   f"{max(years)}-12-31T23:59:59+00:00",
                    },
                },
                {
                    "operator": "OR",
                    "conditions": [
                        {"field": "theme.name", "value": t}
                        for t in FOCUS_THEMES
                    ],
                },
            ],
        },
        "fields": {
            "include": RW_FIELDS + ["id", "url"]
        },
        "limit":  max_docs,
        "sort":   ["date.original:desc"],   # ReliefWeb API expects "field:order" strings
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{RW_BASE}?appname={RELIEFWEB_APPNAME}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            response = json.loads(r.read())
        return response.get("data", [])
    except Exception as e:
        print(f"    ⚠ ReliefWeb error ({iso3}): {e}")
        return []


def flatten_doc(doc: dict, iso3: str) -> dict:
    """Flatten a ReliefWeb API document object into a simple dict."""
    fields = doc.get("fields", {})

    # Extract plain text body (strip HTML if present)
    body = fields.get("body", "") or ""
    if "<" in body:
        import re
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()

    # Truncate body to 3000 chars for LLM input (saves tokens)
    body_snippet = body[:3000]

    return {
        "id":           doc.get("id", ""),
        "iso3":         iso3,
        "country":      ISO3_META.get(iso3, {}).get("name", iso3),
        "title":        fields.get("title", ""),
        "date":         fields.get("date", {}).get("original", "")[:10] if isinstance(fields.get("date"), dict) else str(fields.get("date", "")),
        "source":       ", ".join(s.get("name", "") for s in fields.get("source", [])),
        "theme":        ", ".join(t.get("name", "") for t in fields.get("theme", [])),
        "url":          fields.get("url", ""),
        "body_snippet": body_snippet,
        "body_length":  len(body),
    }


def main():
    check_reliefweb_appname()
    os.makedirs(DATA_PROCESSED, exist_ok=True)

    country_years = get_polycrise_country_years()

    all_docs     = []
    all_docs_raw = {}

    total = len(country_years)
    for i, (iso3, years) in enumerate(country_years.items(), 1):
        print(f"  [{i}/{total}] {ISO3_META.get(iso3, {}).get('name', iso3)} "
              f"({iso3}) — polycrise years: {years}")

        docs_raw = fetch_docs_for_country(iso3, years, RW_MAX_DOCS_PER_COUNTRY)
        all_docs_raw[iso3] = docs_raw

        for doc in docs_raw:
            all_docs.append(flatten_doc(doc, iso3))

        print(f"         → {len(docs_raw)} documents fetched")
        time.sleep(0.5)   # polite rate-limit

    # Save raw
    with open(RAW_DOCS_JSON, "w") as f:
        json.dump(all_docs_raw, f)
    print(f"\n✓ Raw docs JSON saved → {RAW_DOCS_JSON}")

    if not all_docs:
        print("⚠ No documents returned. Check network and filter criteria.")
        return

    df = pd.DataFrame(all_docs)
    df.to_csv(DOCS_CSV, index=False)

    print(f"✓ Flattened docs CSV saved → {DOCS_CSV}  ({len(df):,} documents)")
    print(f"\n  Documents with non-empty body: {(df['body_length'] > 100).sum()}")
    print(f"  Countries covered: {df['iso3'].nunique()}")
    print(f"  Year range: {df['date'].str[:4].min()} – {df['date'].str[:4].max()}")
    print(f"\n  Theme breakdown:")
    theme_counts = (
        df["theme"].str.split(", ").explode()
          .value_counts().head(10)
    )
    print(theme_counts.to_string())


if __name__ == "__main__":
    main()
