"""
01_fetch_acled.py — Polycrise Sentinel
=======================================
Fetches armed conflict event data from the ACLED API for the study countries
and computes an annual conflict intensity score per country-year.

ACLED API docs: https://developer.acleddata.com/
Free registration required at: https://developer.acleddata.com/

⚠  NOTE: ACLED deprecated the old key-based API on 15 September 2025.
   Authentication is now OAuth token-based (email + password → Bearer token).
   See: https://developer.acleddata.com/api-authentication-guide

Setup:
  export ACLED_EMAIL="you@email.com"
  export ACLED_PASSWORD="your-acled-account-password"

Output:
  data/raw/acled_raw.csv          — all events
  data/processed/acled_annual.csv — country-year conflict score

Conflict intensity score (per country-year):
  score = log1p( fatalities + 0.5 * battles + 0.25 * protests )
  Normalised 0–1 across the full panel.
"""

import os, sys, time, json
import pandas as pd
import numpy as np
import requests

# Allow running from any working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (ACLED_EMAIL, ACLED_PASSWORD, DATA_RAW, DATA_PROCESSED,
                    ISO3_LIST, START_YEAR, END_YEAR)

RAW_OUT  = os.path.join(DATA_RAW,       "acled_raw.csv")
PROC_OUT = os.path.join(DATA_PROCESSED, "acled_annual.csv")

# New API endpoints (post-Sep 2025 website relaunch)
ACLED_AUTH_URL = "https://acleddata.com/oauth/token"   # form-encoded POST
ACLED_BASE     = "https://acleddata.com/api/acled/read" # GET with Bearer token

# ACLED event-type groupings
CONFLICT_TYPES = ["Battles", "Explosions/Remote violence", "Violence against civilians"]
UNREST_TYPES   = ["Protests", "Riots"]

# Module-level token cache so we only authenticate once per run
_bearer_token: str | None = None


def check_credentials():
    if not ACLED_EMAIL or not ACLED_PASSWORD:
        print(
            "\n⚠  ACLED credentials not found in environment.\n"
            "   The old ACLED_KEY system was deprecated on 15 Sep 2025.\n"
            "   Register/login at https://developer.acleddata.com/ then:\n"
            "     export ACLED_EMAIL='you@email.com'\n"
            "     export ACLED_PASSWORD='your-account-password'\n"
            "   and re-run this script.\n"
        )
        sys.exit(1)


def get_bearer_token() -> str:
    """
    Obtain an OAuth Bearer token from ACLED using email + password.
    Auth endpoint: POST https://acleddata.com/oauth/token
    Body: application/x-www-form-urlencoded with username, password,
          grant_type='password', client_id='acled'
    Token is cached for the duration of the run (valid 24 h).
    Uses requests library (required — urllib is blocked by Cloudflare).
    """
    global _bearer_token
    if _bearer_token:
        return _bearer_token

    print("  Authenticating with ACLED (OAuth) …", end=" ", flush=True)

    resp = requests.post(
        ACLED_AUTH_URL,
        data={
            "username":   ACLED_EMAIL,
            "password":   ACLED_PASSWORD,
            "grant_type": "password",
            "client_id":  "acled",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"\n✗  ACLED authentication failed (HTTP {resp.status_code}): {resp.text[:300]}")
        sys.exit(1)

    token = resp.json().get("access_token")
    if not token:
        print(f"\n✗  Could not extract token from ACLED auth response: {resp.json()}")
        sys.exit(1)

    _bearer_token = token
    print("OK")
    return token


def fetch_country(iso3: str, token: str) -> list[dict]:
    """
    Fetch ALL ACLED events for one country across the full study period
    (START_YEAR–END_YEAR) in a single paginated request sequence.

    Using one date-range call per country (30 calls total) instead of one
    call per country-year (450 calls) is far more efficient and resilient.
    Date filtering: event_date=YYYY-01-01|YYYY-12-31&event_date_where=BETWEEN
    """
    from config import ISO3_META
    country_name = ISO3_META.get(iso3, {}).get("name", iso3)

    all_events = []
    page = 1
    page_size = 5000
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    date_range = f"{START_YEAR}-01-01|{END_YEAR}-12-31"

    while True:
        params = {
            "country":          country_name,
            "event_date":       date_range,
            "event_date_where": "BETWEEN",
            "limit":            page_size,
            "page":             page,
            "fields":           "event_date|event_type|sub_event_type|country|fatalities|year",
            "_format":          "json",
        }
        try:
            resp = requests.get(ACLED_BASE, params=params, headers=headers, timeout=30)
        except Exception as e:
            print(f"\n    ⚠ Network error ({iso3} page {page}): {e}")
            break

        if resp.status_code == 401:
            global _bearer_token
            _bearer_token = None
            print(f"\n    ⚠ 401 Unauthorized ({iso3} page {page}) — token expired.")
            break
        if resp.status_code != 200:
            print(f"\n    ⚠ ACLED HTTP {resp.status_code} for {iso3} page {page}: {resp.text[:120]}")
            break

        batch = resp.json().get("data", [])
        all_events.extend(batch)
        print(f"    page {page}: {len(batch)} events (total so far: {len(all_events)})", end="\r", flush=True)

        if len(batch) < page_size:   # reached last page
            break
        page += 1
        time.sleep(0.5)

    return all_events


def compute_conflict_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates raw events to country-year and computes a conflict intensity score.
    NOTE: fatalities are masked to 0 on ACLED free-tier accounts; the score
    therefore weights event-type counts (conflict vs. unrest events) instead.
    """
    df["is_conflict"] = df["event_type"].isin(CONFLICT_TYPES).astype(int)
    df["is_unrest"]   = df["event_type"].isin(UNREST_TYPES).astype(int)
    df["fatalities"]  = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0)

    agg = df.groupby(["iso3", "year"]).agg(
        n_events          = ("event_type", "count"),
        n_conflict_events = ("is_conflict", "sum"),
        n_unrest_events   = ("is_unrest", "sum"),
        total_fatalities  = ("fatalities", "sum"),
    ).reset_index()

    # Conflict score: weight violence events > unrest > fatalities
    # (fatalities = 0 on free tier, so primary signal is event counts)
    agg["raw_score"] = np.log1p(
        agg["total_fatalities"]
        + 2.0 * agg["n_conflict_events"]
        + 0.5 * agg["n_unrest_events"]
    )

    # Normalise to 0–1 across the full panel
    mn, mx = agg["raw_score"].min(), agg["raw_score"].max()
    agg["conflict_score"] = (agg["raw_score"] - mn) / (mx - mn + 1e-9)

    return agg[["iso3", "year", "n_events", "n_conflict_events",
                "n_unrest_events", "total_fatalities", "conflict_score"]]


def main():
    check_credentials()
    os.makedirs(DATA_RAW,       exist_ok=True)
    os.makedirs(DATA_PROCESSED, exist_ok=True)

    # OAuth: obtain Bearer token once for the whole run
    token = get_bearer_token()

    # Checkpoint: append-mode — each country's rows are appended immediately
    # so a small, fast write per country replaces one giant rewrite of all data.
    checkpoint = os.path.join(DATA_RAW, "acled_raw.csv")
    if os.path.exists(checkpoint):
        df_existing = pd.read_csv(checkpoint, usecols=["iso3"])
        done_countries = set(df_existing["iso3"].unique())
        print(f"  Resuming from checkpoint: {len(done_countries)} countries already done.")
    else:
        done_countries = set()

    remaining = [iso3 for iso3 in ISO3_LIST if iso3 not in done_countries]
    # Also skip COD if it had 0 events (empty rows never written — re-flag it)
    print(f"Fetching ACLED data for {len(remaining)} countries "
          f"({START_YEAR}–{END_YEAR}) …\n")

    for i, iso3 in enumerate(remaining, 1):
        from config import ISO3_META
        name = ISO3_META.get(iso3, {}).get("name", iso3)
        print(f"  [{i}/{len(remaining)}] {name} ({iso3}) …")
        events = fetch_country(iso3, token)
        for e in events:
            e["iso3"] = iso3
        n = len(events)
        print(f"    → {n:,} events fetched for {iso3}")

        if events:
            df_chunk = pd.DataFrame(events)
            # Append to checkpoint; write header only when file is new
            write_header = not os.path.exists(checkpoint)
            df_chunk.to_csv(checkpoint, mode="a", header=write_header, index=False)

        # If 0 events (like COD on free tier), write a placeholder row so this
        # country is not re-fetched on the next resume.
        if n == 0:
            placeholder = pd.DataFrame([{"iso3": iso3, "event_date": None,
                                          "year": None, "event_type": "NO_DATA",
                                          "fatalities": 0}])
            write_header = not os.path.exists(checkpoint)
            placeholder.to_csv(checkpoint, mode="a", header=write_header, index=False)

        time.sleep(1.0)

    print()

    # Read the full checkpoint for score computation
    if not os.path.exists(checkpoint):
        print("No events returned. Check API credentials and network.")
        sys.exit(1)

    df_raw = pd.read_csv(checkpoint)
    # Drop placeholder rows for countries with no data
    df_raw = df_raw[df_raw["event_type"] != "NO_DATA"].copy()
    df_raw["year"] = pd.to_numeric(df_raw["year"], errors="coerce")
    df_raw.to_csv(RAW_OUT, index=False)
    print(f"✓ Raw events saved → {RAW_OUT}  ({len(df_raw):,} rows)")

    df_annual = compute_conflict_score(df_raw)
    df_annual.to_csv(PROC_OUT, index=False)
    print(f"✓ Annual conflict scores saved → {PROC_OUT}  ({len(df_annual):,} rows)")
    print(df_annual.sort_values("conflict_score", ascending=False).head(10)
          [["iso3", "year", "n_conflict_events", "n_unrest_events", "conflict_score"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
