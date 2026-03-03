"""
agent/agent.py — Funding Opportunity Agent Orchestrator
========================================================
Coordinates all fetchers → deduplicates against seen state →
sends an email alert for anything new.

Usage (one-shot):
    python -m agent.agent

Or invoked by the scheduler in run_agent.py.
"""

import json
import logging
import sys
from datetime import datetime

from agent import config_agent as cfg
from agent import state as state_mgr
from agent.emailer import send_alert

log = logging.getLogger(__name__)

# ── Lazy imports of fetchers (only import enabled sources) ─────────────────────

def _get_fetchers() -> list[tuple[str, object]]:
    """Return list of (source_key, fetch_fn) for enabled sources."""
    pairs = []
    if cfg.ENABLED_SOURCES.get("grants_gov"):
        from agent.fetchers import grants_gov
        pairs.append(("grants_gov", grants_gov.fetch))
    if cfg.ENABLED_SOURCES.get("who"):
        from agent.fetchers import who
        pairs.append(("who", who.fetch))
    if cfg.ENABLED_SOURCES.get("gates"):
        from agent.fetchers import gates
        pairs.append(("gates", gates.fetch))
    if cfg.ENABLED_SOURCES.get("wellcome"):
        from agent.fetchers import wellcome
        pairs.append(("wellcome", wellcome.fetch))
    if cfg.ENABLED_SOURCES.get("reliefweb"):
        from agent.fetchers import reliefweb
        pairs.append(("reliefweb", reliefweb.fetch))
    if cfg.ENABLED_SOURCES.get("eu_health"):
        from agent.fetchers import eu_health
        pairs.append(("eu_health", eu_health.fetch))
    if cfg.ENABLED_SOURCES.get("simpler_grants"):
        from agent.fetchers import simpler_grants
        pairs.append(("simpler_grants", simpler_grants.fetch))
    if cfg.ENABLED_SOURCES.get("un_portal"):
        from agent.fetchers import un_portal
        pairs.append(("un_portal", un_portal.fetch))
    return pairs


# ── Dashboard helper ──────────────────────────────────────────────────────────

def _save_dashboard_json(opportunities: list[dict], timestamp: str) -> None:
    """Write all fetched opportunities to docs/opportunities.json for the web dashboard."""
    docs_dir = cfg.ROOT_DIR / "docs"
    docs_dir.mkdir(exist_ok=True)
    by_source: dict[str, int] = {}
    for o in opportunities:
        src = o.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    payload = {
        "last_updated": timestamp,
        "total": len(opportunities),
        "by_source": by_source,
        "opportunities": opportunities,
    }
    out = docs_dir / "opportunities.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("Dashboard JSON saved → %s (%d opportunities)", out, len(opportunities))


# ── Main run function ──────────────────────────────────────────────────────────

def run(dry_run: bool = False, save_json: bool = False) -> int:
    """
    Execute a full scan cycle.

    Parameters
    ----------
    dry_run : bool
        If True, fetch and filter but do NOT send the email (useful for testing).
    save_json : bool
        If True, write all fetched opportunities to docs/opportunities.json
        for the GitHub Pages dashboard.

    Returns
    -------
    int
        Number of new opportunities found.
    """
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    log.info("══ Funding Agent run started at %s ══", timestamp)
    log.info("Keywords (%d): %s", len(cfg.KEYWORDS), ", ".join(cfg.KEYWORDS[:5]) + ("…" if len(cfg.KEYWORDS) > 5 else ""))

    if not cfg.KEYWORDS:
        log.warning("No keywords configured — set ALERT_KEYWORDS or use defaults.")

    fetchers = _get_fetchers()
    if not fetchers:
        log.error("All sources are disabled. Enable at least one source.")
        return 0

    all_raw: list[dict] = []   # every opportunity fetched (for dashboard)
    all_new: list[dict] = []   # only opportunities not seen before (for email)

    for source_key, fetch_fn in fetchers:
        try:
            log.info("── Fetching: %s", source_key)
            raw = fetch_fn(cfg.KEYWORDS)
            all_raw.extend(raw)
            new = state_mgr.filter_new(raw, source_key)
            all_new.extend(new)
        except Exception as exc:
            log.error("Unhandled error in fetcher '%s': %s", source_key, exc, exc_info=True)

    if save_json:
        _save_dashboard_json(all_raw, timestamp)

    total = len(all_new)
    log.info("══ Total new opportunities found: %d ══", total)

    if total == 0:
        log.info("Nothing new — no email sent.")
        return 0

    # Sort by source then title for a clean email
    all_new.sort(key=lambda o: (o.get("source", ""), o.get("title", "")))

    if dry_run:
        log.info("[DRY RUN] Would send email for %d opportunities:", total)
        for o in all_new:
            log.info("  [%s] %s", o.get("source"), o.get("title"))
        return total

    success = send_alert(all_new)
    if not success:
        log.error("Email delivery failed — opportunities were still marked as seen.")
    return total


# ── CLI entry-point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    dry = "--dry-run" in sys.argv
    count = run(dry_run=dry)
    sys.exit(0)
