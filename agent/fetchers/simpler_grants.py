"""
agent/fetchers/simpler_grants.py — Simpler Grants.gov API Fetcher
=================================================================
Uses the new Simpler Grants.gov REST API (alpha version).
API docs: https://api.simpler.grants.gov/docs
Spec:     https://api.simpler.grants.gov/openapi.json

Authentication
--------------
Requires a free API key.  Register at https://simpler.grants.gov then set:
    export SIMPLER_GRANTS_API_KEY=<your-key>

If SIMPLER_GRANTS_API_KEY is not set, this fetcher skips gracefully.

Why use this alongside grants_gov.py?
--------------------------------------
- Simpler Grants uses a newer, richer schema with more metadata fields
  (award ceiling, estimated program funding, funding categories, etc.)
- Its search uses full-text OR/AND operators — better keyword relevance
- Eventually this will supersede the legacy api.grants.gov endpoint
"""

import logging
import os
import time

import requests

SOURCE  = "Simpler Grants.gov"
API_URL = "https://api.simpler.grants.gov/v1/opportunities/search"
API_KEY = os.getenv("SIMPLER_GRANTS_API_KEY", "")

log = logging.getLogger(__name__)


def fetch(keywords: list[str]) -> list[dict]:
    if not API_KEY:
        log.info(
            "[%s] Skipping — SIMPLER_GRANTS_API_KEY not set. "
            "Register at https://simpler.grants.gov then set the env var.",
            SOURCE,
        )
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()

    # Search once with all keywords joined by OR for efficiency
    query = " OR ".join(f'"{kw}"' for kw in keywords[:10]) if keywords else "global health"

    try:
        payload = {
            "query": query,
            "query_operator": "OR",
            "pagination": {
                "page_offset": 1,
                "page_size": 25,
                "order_by": "post_date",
                "sort_direction": "descending",
            },
            "filters": {
                "opportunity_status": {"one_of": ["posted", "forecasted"]},
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept":        "application/json",
            "X-API-Key":     API_KEY,
        }
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for opp in data.get("data", []):
            opp_id   = str(opp.get("opportunity_id") or opp.get("legacy_opportunity_id", ""))
            title    = opp.get("opportunity_title", "Untitled")
            agency   = opp.get("agency_name") or opp.get("top_level_agency_name", "")
            number   = opp.get("opportunity_number", "")
            summary  = opp.get("summary") or {}

            # summary is a nested object with close_date, description, etc.
            close_date   = ""
            description  = ""
            award_ceil   = ""
            if isinstance(summary, dict):
                close_date  = summary.get("close_date", "") or ""
                description = summary.get("summary_description", "") or ""
                award_ceil  = summary.get("award_ceiling", "") or ""

            if not opp_id or opp_id in seen_ids:
                continue
            seen_ids.add(opp_id)

            url = (
                f"https://simpler.grants.gov/opportunity/{opp.get('legacy_opportunity_id', opp_id)}"
            )
            results.append({
                "id":            opp_id,
                "title":         title,
                "agency":        agency,
                "deadline":      str(close_date)[:10] if close_date else "",
                "award_ceiling": str(award_ceil) if award_ceil else "",
                "url":           url,
                "source":        SOURCE,
                "description":   str(description)[:400],
            })

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            log.error(
                "[%s] Authentication failed — check your SIMPLER_GRANTS_API_KEY.", SOURCE
            )
        else:
            log.warning("[%s] HTTP error: %s", SOURCE, e)
    except requests.RequestException as e:
        log.warning("[%s] Request failed: %s", SOURCE, e)

    time.sleep(0.5)
    log.info("[%s] Fetched %d opportunities.", SOURCE, len(results))
    return results
