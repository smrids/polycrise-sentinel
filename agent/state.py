"""
agent/state.py — Seen-Opportunity State Manager
================================================
Persists a set of opportunity IDs (one per source) to a JSON file so
the agent only emails truly new postings and never repeats an alert.
"""

import json
import logging
from pathlib import Path
from agent.config_agent import STATE_FILE

log = logging.getLogger(__name__)


def _load() -> dict[str, list[str]]:
    """Return the full state dict {source_name: [id, ...]}."""
    p = Path(STATE_FILE)
    if p.exists():
        try:
            with p.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read state file: %s — starting fresh.", e)
    return {}


def _save(state: dict[str, list[str]]) -> None:
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(state, f, indent=2)


def filter_new(opportunities: list[dict], source: str) -> list[dict]:
    """
    Given a list of opportunity dicts (each with an 'id' key),
    return only those not previously seen, then persist the updated state.
    """
    state = _load()
    seen: set[str] = set(state.get(source, []))

    new_opps = [o for o in opportunities if str(o["id"]) not in seen]

    if new_opps:
        # Mark all newly found IDs as seen
        all_ids = seen | {str(o["id"]) for o in new_opps}
        state[source] = sorted(all_ids)
        _save(state)
        log.info("[%s] %d new / %d already seen", source, len(new_opps), len(seen))
    else:
        log.info("[%s] No new opportunities.", source)

    return new_opps


def mark_all_seen(opportunities: list[dict], source: str) -> None:
    """Force-mark a list of opportunities as seen without filtering."""
    state = _load()
    seen: set[str] = set(state.get(source, []))
    seen |= {str(o["id"]) for o in opportunities}
    state[source] = sorted(seen)
    _save(state)
