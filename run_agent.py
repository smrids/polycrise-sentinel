"""
run_agent.py — Polycrise Sentinel: Funding Opportunity Agent
============================================================
Entry point with a daily scheduler.

QUICK START
-----------
1. Copy .env.example → .env and fill in credentials:
       cp .env.example .env
       nano .env

2. Activate your virtual environment:
       source .venv/bin/activate

3. Install dependencies:
       pip install -r requirements.txt

4. Load your env vars:
       export $(grep -v '^#' .env | xargs)

5. Test with a dry-run (no email sent):
       python run_agent.py --dry-run

6. Run once immediately (sends real email):
       python run_agent.py --now

7. Start the daily scheduler (keeps running, fires at ALERT_SCHEDULE_TIME):
       python run_agent.py

ENVIRONMENT VARIABLES
---------------------
  ALERT_EMAIL_FROM      Gmail sender  (required)
  ALERT_EMAIL_PASSWORD  App Password  (required)
  ALERT_EMAIL_TO        Recipient(s), comma-separated  (required)
  ALERT_SCHEDULE_TIME   HH:MM 24h daily run time  [default: 08:00]
  ALERT_KEYWORDS        Comma-separated keywords   [see config_agent.py]

  Source toggles (set to "false" to disable):
  ALERTS_GRANTS_GOV, ALERTS_WHO, ALERTS_GATES,
  ALERTS_WELLCOME, ALERTS_RELIEFWEB, ALERTS_EU_HEALTH
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Load .env if present ───────────────────────────────────────────────────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
        print(f"Loaded environment from {_env_file}")
    except ImportError:
        pass   # python-dotenv optional; user can source .env manually

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent / "outputs" / "agent.log",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("run_agent")

# ── Import agent AFTER env vars are loaded ─────────────────────────────────────
from agent.agent import run
from agent.config_agent import SCHEDULE_TIME


def _scheduler_loop(dry_run: bool) -> None:
    """Run via APScheduler — fires once daily at SCHEDULE_TIME."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error(
            "APScheduler is not installed. "
            "Run: pip install apscheduler  or use `--now` for a one-shot run."
        )
        sys.exit(1)

    hour, minute = SCHEDULE_TIME.split(":")
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        lambda: run(dry_run=dry_run),
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id="funding_agent",
        name="Global Health Funding Agent",
        replace_existing=True,
    )
    log.info(
        "Scheduler started — will run daily at %s UTC. Press Ctrl+C to stop.",
        SCHEDULE_TIME,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Polycrise Sentinel — Global Health Funding Alert Agent"
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run one scan immediately then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and filter but do NOT send any email.",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save all fetched opportunities to docs/opportunities.json (for the web dashboard).",
    )
    args = parser.parse_args()

    # Ensure outputs/ exists for the log file
    Path(__file__).parent.joinpath("outputs").mkdir(exist_ok=True)

    save_json = getattr(args, "save_json", False)

    if args.now or args.dry_run:
        log.info("Running one-shot scan (dry_run=%s, save_json=%s)…", args.dry_run, save_json)
        count = run(dry_run=args.dry_run, save_json=save_json)
        log.info("Done — %d new opportunities found.", count)
    else:
        _scheduler_loop(dry_run=False)


if __name__ == "__main__":
    main()
