"""
agent/fetchers/reliefweb.py — ReliefWeb Funding Calls Fetcher
=============================================================
Uses the ReliefWeb API (no auth required) to retrieve funding opportunity
reports, appeals and calls for proposals tagged with health-related themes.
API docs: https://apidoc.rwlabs.org/
"""

import hashlib
import logging
import time

import requests

SOURCE   = "ReliefWeb"
API_URL  = "https://api.reliefweb.int/v1/reports"
# ReliefWeb requires a *registered* appname.
# Register at: https://apidoc.reliefweb.int/registration
# Then set: export RELIEFWEB_APPNAME=<your-registered-name>
import os
APP_NAME = os.getenv("RELIEFWEB_APPNAME", "ridhismriti-research-8yzpu")
log = logging.getLogger(__name__)


def fetch(keywords: list[str]) -> list[dict]:
    results: list[dict] = []
    seen_ids: set[str] = set()

    if not APP_NAME:
        log.info(
            "[%s] Skipping — RELIEFWEB_APPNAME not set. "
            "Register at https://apidoc.reliefweb.int/registration "
            "then set the env var.", SOURCE
        )
        return []

    for kw in keywords[:8]:   # limit API calls — pick most specific keywords
        try:
            payload = {
                "filter": {
                    "field": "body",
                    "value": kw,
                },
                "fields": {
                    "include": ["id", "title", "url", "date.created",
                                "source.name", "body", "file"]
                },
                "sort": ["date.created:desc"],
                "limit": 10,
            }
            resp = requests.post(
                API_URL,
                params={"appname": APP_NAME},
                json=payload,
                timeout=25,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", []):
                fields = item.get("fields", {})
                opp_id = str(item.get("id") or
                             hashlib.md5(fields.get("title", kw).encode()).hexdigest())
                if opp_id in seen_ids:
                    continue
                seen_ids.add(opp_id)
                sources = fields.get("source", [])
                agency  = sources[0]["name"] if sources else "ReliefWeb"
                results.append({
                    "id":          opp_id,
                    "title":       fields.get("title", "Untitled"),
                    "agency":      agency,
                    "deadline":    "",
                    "url":         fields.get("url", f"https://reliefweb.int/node/{opp_id}"),
                    "source":      SOURCE,
                    "description": (fields.get("body") or "")[:400],
                })
        except requests.RequestException as e:
            log.warning("[%s] Request failed for '%s': %s", SOURCE, kw, e)
        time.sleep(0.5)

    log.info("[%s] Fetched %d opportunities.", SOURCE, len(results))
    return results
