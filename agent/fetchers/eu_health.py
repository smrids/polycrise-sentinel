"""
agent/fetchers/eu_health.py — EU Funding & Tenders Portal Fetcher
=================================================================
Queries the public EU Funding & Tenders Portal Search API (SEDIA) for
health-related open calls (EU4Health, Horizon Europe Health cluster, etc.)

API endpoint: POST https://api.tech.ec.europa.eu/search-api/prod/rest/search
  - apiKey=SEDIA and text= must be passed as URL query parameters
  - No registration needed; returns open EU funding calls

NOTE: Results may be empty when no EU health calls are currently open.
The agent will log INFO and skip silently in that case.
"""

import hashlib
import logging
import time

import requests

SOURCE  = "EU Funding & Tenders Portal"
API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
log = logging.getLogger(__name__)


def _matches(text: str, keywords: list[str]) -> bool:
    tl = text.lower()
    return any(kw.lower() in tl for kw in keywords)


def fetch(keywords: list[str]) -> list[dict]:
    results: list[dict] = []
    seen_ids: set[str] = set()

    # Build a combined query — limit first 6 keywords to keep URL manageable
    query_terms = " OR ".join(f'"{kw}"' for kw in keywords[:6])

    try:
        resp = requests.post(
            API_URL,
            params={
                "apiKey":      "SEDIA",
                "text":        query_terms or "global health",
                "pageNumber":  0,
                "pageSize":    20,
                "language":    "en",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("results", []):
            md = item.get("metadata", {})
            title    = (md.get("title")              or [""])[0]
            ident    = (md.get("identifier")         or [""])[0]
            deadline = (md.get("deadlineDate")       or [""])[0]
            hyper    = (md.get("hyperlink")          or [""])[0]
            descr    = (md.get("description")        or [""])[0]
            prog     = (md.get("frameworkProgramme") or [""])[0]

            combined = title + " " + descr
            if keywords and not _matches(combined, keywords):
                continue

            opp_id = ident or hashlib.md5((title + deadline).encode()).hexdigest()
            if opp_id in seen_ids:
                continue
            seen_ids.add(opp_id)

            url = hyper or (
                f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
                f"screen/opportunities/topic-search;callCode={ident}"
            )
            results.append({
                "id":          opp_id,
                "title":       title,
                "agency":      f"European Commission — {prog}" if prog else "European Commission",
                "deadline":    deadline[:10] if deadline else "",
                "url":         url,
                "source":      SOURCE,
                "description": descr[:400],
            })

    except requests.RequestException as e:
        log.warning("[%s] API request failed: %s", SOURCE, e)
    except (KeyError, ValueError) as e:
        log.warning("[%s] Unexpected response format: %s", SOURCE, e)

    if not results:
        log.info("[%s] No open health calls found (may be correct if no calls are active).", SOURCE)

    time.sleep(0.5)
    log.info("[%s] Fetched %d opportunities.", SOURCE, len(results))
    return results

