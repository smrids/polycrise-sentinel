"""
agent/fetchers/grants_gov.py — Grants.gov API Fetcher
======================================================
Uses the public Grants.gov REST API (no API key required).
Docs: https://api.grants.gov/v1/api/search2
"""

import hashlib
import logging
import time

import requests

SOURCE = "Grants.gov"
API_URL = "https://api.grants.gov/v1/api/search2"
_HEADERS = {"Content-Type": "application/json"}
log = logging.getLogger(__name__)


def _normalize_date(raw: str) -> str:
    """Convert MMDDYYYY → YYYY-MM-DD if needed."""
    if not raw:
        return ""
    raw = str(raw).strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[4:8]}-{raw[0:2]}-{raw[2:4]}"
    return raw


def fetch(keywords: list[str]) -> list[dict]:
    """
    Search Grants.gov for posted/forecasted opportunities matching keywords.
    Returns a deduplicated list of opportunity dicts.
    """
    seen_ids: set[str] = set()
    results: list[dict] = []

    for kw in keywords:
        try:
            payload = {
                "keyword": kw,
                "oppStatuses": "posted|forecasted",
                "rows": 25,
                "startRecordNum": 0,
                "sortBy": "openDate|desc",
            }
            resp = requests.post(API_URL, headers=_HEADERS, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            hits = (
                data.get("data", {}).get("oppHits", [])
                or data.get("oppHits", [])
                or []
            )
            for opp in hits:
                opp_id = str(opp.get("id") or opp.get("oppNumber") or
                             hashlib.md5(opp.get("title", kw).encode()).hexdigest())
                if opp_id in seen_ids:
                    continue
                seen_ids.add(opp_id)
                results.append({
                    "id":            opp_id,
                    "title":         opp.get("title", "Untitled"),
                    "agency":        opp.get("agencyName") or opp.get("agencyCode", ""),
                    "deadline":      _normalize_date(opp.get("closeDate", "")),
                    "award_ceiling": opp.get("awardCeiling", ""),
                    "url":           f"https://www.grants.gov/search-results-detail/{opp_id}",
                    "source":        SOURCE,
                    "description":   (opp.get("synopsis") or opp.get("description") or "")[:400],
                })

        except requests.RequestException as e:
            log.warning("[%s] Request failed for keyword '%s': %s", SOURCE, kw, e)
        time.sleep(0.3)   # polite rate limit

    log.info("[%s] Fetched %d opportunities.", SOURCE, len(results))
    return results
