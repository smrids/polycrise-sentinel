"""
agent/fetchers/wellcome.py — Wellcome Trust Funding Schemes Fetcher
====================================================================
Discovers open funding schemes by parsing Wellcome's XML sitemap
(https://wellcome.org/sitemap.xml?page=1 and page=2) and extracting
URLs under /research-funding/schemes/ that are NOT marked as closed.

The Wellcome funding pages are Next.js SPAs (no RSS, no public API)
so sitemap-based discovery is the most reliable approach.
"""

import hashlib
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

SOURCE      = "Wellcome Trust"
SITEMAP_URL = "https://wellcome.org/sitemap.xml"
BASE_URL    = "https://wellcome.org"
SCHEME_PREFIX   = "/research-funding/schemes/"
log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _slug_to_title(slug: str) -> str:
    """Convert a URL slug like 'seed-awards-science' → 'Seed Awards Science'."""
    return re.sub(r"[-_]", " ", slug).title()


def _matches(text: str, keywords: list[str]) -> bool:
    tl = text.lower()
    # Wellcome schemes are all research/health — treat as match if no keywords
    if not keywords:
        return True
    return any(kw.lower() in tl for kw in keywords)


def fetch(keywords: list[str]) -> list[dict]:
    results: list[dict] = []
    seen_urls: set[str] = set()

    for page_num in [1, 2]:
        try:
            resp = requests.get(
                f"{SITEMAP_URL}?page={page_num}",
                headers=HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml-xml")
            locs = [loc.get_text() for loc in soup.find_all("loc")]

            for loc in locs:
                # Only scheme pages, not closed ones
                if SCHEME_PREFIX not in loc:
                    continue
                if loc in seen_urls:
                    continue
                # Extract the scheme slug (last segment of URL)
                scheme_slug = loc.rstrip("/").split("/")[-1]
                if not scheme_slug:
                    continue
                # Skip items explicitly marked as closed
                if scheme_slug.endswith("-closed") or "-closed-" in scheme_slug:
                    continue

                title = _slug_to_title(scheme_slug)
                # Keyword-filter on title (all Wellcome schemes are health-related)
                if keywords and not _matches(title, keywords):
                    continue

                seen_urls.add(loc)
                opp_id = hashlib.md5(loc.encode()).hexdigest()
                results.append({
                    "id":          opp_id,
                    "title":       f"Wellcome Trust — {title}",
                    "agency":      "Wellcome Trust",
                    "deadline":    "",
                    "url":         loc,
                    "source":      SOURCE,
                    "description": f"Active Wellcome funding scheme: {title}. Visit the URL for eligibility and deadlines.",
                })
        except requests.RequestException as e:
            log.warning("[%s] Sitemap page %d fetch failed: %s", SOURCE, page_num, e)
        time.sleep(0.5)

    log.info("[%s] Fetched %d open schemes from sitemap.", SOURCE, len(results))
    return results
