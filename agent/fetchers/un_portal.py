"""
agent/fetchers/un_portal.py — UN Partner Portal CFEI Fetcher
============================================================
Monitors the UN Partner Portal (https://www.unpartnerportal.org) for
open Calls for Expressions of Interest (CFEI) from UN agencies.

Authentication
--------------
The UN Partner Portal is a members-only platform for Civil Society
Organizations (CSOs) and NGOs to partner with UN agencies.

To use this fetcher:
1. Register your organization at https://www.unpartnerportal.org
2. Log in and obtain your API token from your profile/settings page
3. Set the environment variable:
       export UN_PORTAL_TOKEN=<your-token>

If UN_PORTAL_TOKEN is not set, this fetcher skips gracefully.

API
---
Endpoint: GET /api/v1/calls-for-expressions-of-interest/
Auth:      Authorization: Token <token>
Filters:   ?status=open&is_published=true
"""

import logging
import os
import time

import requests

SOURCE  = "UN Partner Portal"
API_URL = "https://www.unpartnerportal.org/api/v1/calls-for-expressions-of-interest/"
TOKEN   = os.getenv("UN_PORTAL_TOKEN", "")

log = logging.getLogger(__name__)


def _matches(text: str, keywords: list[str]) -> bool:
    tl = text.lower()
    if not keywords:
        return True
    return any(kw.lower() in tl for kw in keywords)


def fetch(keywords: list[str]) -> list[dict]:
    if not TOKEN:
        log.info(
            "[%s] Skipping — UN_PORTAL_TOKEN not set. "
            "Register at https://www.unpartnerportal.org, log in, "
            "then copy your API token and set the env var.",
            SOURCE,
        )
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()

    headers = {
        "Authorization":  f"Token {TOKEN}",
        "Accept":         "application/json",
        "User-Agent":     "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {
        "status":        "open",
        "is_published":  "true",
        "page_size":     50,
        "ordering":      "-created",
    }

    url: str | None = API_URL
    page = 0
    while url and page < 5:   # max 5 pages (250 results)
        try:
            resp = requests.get(url, headers=headers, params=params if page == 0 else None, timeout=25)
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                log.error(
                    "[%s] Authentication failed — verify your UN_PORTAL_TOKEN is valid.", SOURCE
                )
            else:
                log.warning("[%s] HTTP error on page %d: %s", SOURCE, page, e)
            break
        except requests.RequestException as e:
            log.warning("[%s] Request failed on page %d: %s", SOURCE, page, e)
            break

        items  = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        url    = data.get("next") if isinstance(data, dict) else None   # DRF pagination

        for item in items:
            cfei_id   = str(item.get("id", ""))
            title     = item.get("title", "") or item.get("project_title", "Untitled")
            agency    = item.get("agency", "") or item.get("created_by_agency", "UN Agency")
            if isinstance(agency, dict):
                agency = agency.get("name", "UN Agency")
            deadline  = (item.get("deadline_date") or item.get("deadline", ""))[:10]
            descr     = (item.get("description") or item.get("goal") or "")[:400]
            cfei_url  = (
                item.get("url") or
                f"https://www.unpartnerportal.org/cfei/direct/{cfei_id}/overview"
            )

            combined = title + " " + descr
            if keywords and not _matches(combined, keywords):
                continue
            if not cfei_id or cfei_id in seen_ids:
                continue
            seen_ids.add(cfei_id)

            results.append({
                "id":          cfei_id,
                "title":       title,
                "agency":      str(agency),
                "deadline":    deadline,
                "url":         cfei_url,
                "source":      SOURCE,
                "description": descr,
            })

        page += 1
        time.sleep(0.5)

    log.info("[%s] Fetched %d keyword-matching CFEIs.", SOURCE, len(results))
    return results
