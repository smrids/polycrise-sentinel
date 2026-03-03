"""
agent/fetchers/who.py — WHO Funding Calls Fetcher
==================================================
Uses two approaches:
1. WHO JSON News API  (https://www.who.int/api/news/newsitems) — keyword-filtered
2. WHO Emergencies Funding page  (https://www.who.int/emergencies/funding)

Falls back gracefully to an empty list on any network or parse error.
"""

import hashlib
import logging
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCE      = "WHO"
BASE_URL    = "https://www.who.int"
NEWS_API    = "https://www.who.int/api/news/newsitems"
FUNDING_PAGES = [
    "/emergencies/funding",
]
log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _matches(text: str, keywords: list[str]) -> bool:
    tl = text.lower()
    return any(kw.lower() in tl for kw in keywords)


def _fetch_news_api(keywords: list[str]) -> list[dict]:
    """Query WHO JSON API for news items and keyword-filter results."""
    results: list[dict] = []
    try:
        resp = requests.get(
            NEWS_API,
            params={"sf_culture": "en", "rows": 50, "CultureIso": "en"},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        for item in resp.json().get("value", []):
            title     = item.get("Title", "")
            item_url  = item.get("ItemDefaultUrl", "")
            pub_date  = item.get("PublicationDateAndTime", "")[:10]
            news_type = item.get("NewsType", "")
            if keywords and not _matches(title + " " + news_type, keywords):
                continue
            full_url = urljoin(BASE_URL, item_url) if item_url else BASE_URL
            opp_id   = item.get("Id") or hashlib.md5(full_url.encode()).hexdigest()
            results.append({
                "id":          str(opp_id),
                "title":       title,
                "agency":      "World Health Organization",
                "deadline":    "",
                "url":         full_url,
                "source":      SOURCE,
                "description": f"{news_type} — {pub_date}" if news_type else pub_date,
            })
    except requests.RequestException as e:
        log.warning("[%s] News API request failed: %s", SOURCE, e)
    return results


def _scrape_page(path: str, keywords: list[str]) -> list[dict]:
    url = BASE_URL + path
    results: list[dict] = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup.find_all("a", href=True):
            title    = tag.get_text(separator=" ").strip()
            href     = tag["href"]
            full_url = urljoin(BASE_URL, href)
            if len(title) < 20 or (keywords and not _matches(title, keywords)):
                continue
            if any(s in href for s in ["#", "mailto:", "tel:", "/social"]):
                continue
            opp_id = hashlib.md5(full_url.encode()).hexdigest()
            results.append({
                "id":          opp_id,
                "title":       title,
                "agency":      "World Health Organization",
                "deadline":    "",
                "url":         full_url,
                "source":      SOURCE,
                "description": "",
            })
    except requests.RequestException as e:
        log.warning("[%s] Could not fetch %s: %s", SOURCE, path, e)
    return results


def fetch(keywords: list[str]) -> list[dict]:
    seen_ids: set[str] = set()
    results:  list[dict] = []

    for opp in _fetch_news_api(keywords):
        if opp["id"] not in seen_ids:
            seen_ids.add(opp["id"])
            results.append(opp)

    for path in FUNDING_PAGES:
        for opp in _scrape_page(path, keywords):
            if opp["id"] not in seen_ids:
                seen_ids.add(opp["id"])
                results.append(opp)
        time.sleep(0.5)

    log.info("[%s] Fetched %d keyword-matching items.", SOURCE, len(results))
    return results
