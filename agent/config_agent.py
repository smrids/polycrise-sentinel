"""
agent/config_agent.py — Funding Alert Agent Configuration
==========================================================
All settings are read from environment variables so no credentials
are ever hard-coded. Copy .env.example → .env and fill in the values,
then:  source .env   (or use python-dotenv by importing this module).

Required env vars
-----------------
ALERT_EMAIL_FROM      Gmail sender address  (e.g. you@gmail.com)
ALERT_EMAIL_PASSWORD  Gmail App Password    (16-char, spaces ok)
ALERT_EMAIL_TO        Comma-separated recipient(s)

Optional env vars
-----------------
ALERT_SCHEDULE_TIME   HH:MM (24h) for daily run  [default: 08:00]
ALERT_KEYWORDS        Comma-separated keywords    [default list below]
"""

import os

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_FROM     = os.getenv("ALERT_EMAIL_FROM", "")
EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")   # Gmail App Password
EMAIL_TO_RAW   = os.getenv("ALERT_EMAIL_TO", "")
EMAIL_TO       = [e.strip() for e in EMAIL_TO_RAW.split(",") if e.strip()]

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ── Schedule ──────────────────────────────────────────────────────────────────
SCHEDULE_TIME = os.getenv("ALERT_SCHEDULE_TIME", "08:00")   # HH:MM, 24-hour

# ── Keywords ──────────────────────────────────────────────────────────────────
_default_keywords = (
    "global health,public health,maternal health,child health,"
    "malaria,tuberculosis,HIV,neglected tropical diseases,"
    "pandemic,epidemic,health system,immunization,nutrition,"
    "mental health,WASH,water sanitation,emergency health"
)
KEYWORDS: list[str] = [
    kw.strip()
    for kw in os.getenv("ALERT_KEYWORDS", _default_keywords).split(",")
    if kw.strip()
]

# ── Sources toggle ────────────────────────────────────────────────────────────
# Set any of these env vars to "false" to disable a source.
ENABLED_SOURCES: dict[str, bool] = {
    "grants_gov":      os.getenv("ALERTS_GRANTS_GOV",      "true").lower() != "false",
    "who":             os.getenv("ALERTS_WHO",              "true").lower() != "false",
    "gates":           os.getenv("ALERTS_GATES",            "true").lower() != "false",
    "wellcome":        os.getenv("ALERTS_WELLCOME",         "true").lower() != "false",
    "reliefweb":       os.getenv("ALERTS_RELIEFWEB",        "true").lower() != "false",
    "eu_health":       os.getenv("ALERTS_EU_HEALTH",        "true").lower() != "false",
    "simpler_grants":  os.getenv("ALERTS_SIMPLER_GRANTS",   "true").lower() != "false",
    "un_portal":       os.getenv("ALERTS_UN_PORTAL",        "true").lower() != "false",
}

# ── State file ────────────────────────────────────────────────────────────────
import pathlib
ROOT_DIR   = pathlib.Path(__file__).parent.parent
STATE_FILE = ROOT_DIR / "data" / "processed" / "agent_seen_opportunities.json"
