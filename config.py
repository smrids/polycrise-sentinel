"""
config.py — Polycrise Sentinel
================================
Central configuration: paths, API keys, country list, date range.

HOW TO SET API CREDENTIALS (never hard-code them):
  export ACLED_EMAIL="you@email.com"
  export ACLED_PASSWORD="your-acled-account-password"
  export OPENAI_API_KEY="sk-..."     # only needed for Script 07 if using OpenAI

NOTE: ACLED moved to OAuth token-based auth in Sep 2025.
  The old ACLED_KEY query-param system is no longer valid.
  Login credentials (email + password) are now used to obtain
  a Bearer token programmatically via the ACLED auth endpoint.

Register for free at:
  - ACLED:   https://developer.acleddata.com/
  - EM-DAT:  https://www.emdat.be/  (manual CSV download — no API key)
  - IMF:     No key needed
  - WHO GHO: No key needed
  - ReliefWeb: No key needed
"""

import os

# ── Directories ────────────────────────────────────────────────────────────────
ROOT_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_RAW       = os.path.join(ROOT_DIR, "data", "raw")
DATA_PROCESSED = os.path.join(ROOT_DIR, "data", "processed")
OUTPUTS        = os.path.join(ROOT_DIR, "outputs")

# ── API credentials (from environment variables) ───────────────────────────────
ACLED_EMAIL    = os.getenv("ACLED_EMAIL", "")
ACLED_PASSWORD = os.getenv("ACLED_PASSWORD", "")   # replaces old ACLED_KEY (deprecated Sep 2025)
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")

# ── Study parameters ───────────────────────────────────────────────────────────
STUDY_YEARS    = list(range(2010, 2025))   # 2010–2024 inclusive
START_YEAR     = 2010
END_YEAR       = 2024

# ── Country sample ─────────────────────────────────────────────────────────────
# 30 countries covering all income groups and regions.
# ISO3 codes used consistently across all scripts.
COUNTRIES = [
    # Sub-Saharan Africa (LMIC/LIC)
    {"iso3": "NGA", "name": "Nigeria",           "income": "LMIC",  "region": "SSA"},
    {"iso3": "ETH", "name": "Ethiopia",          "income": "LIC",   "region": "SSA"},
    {"iso3": "KEN", "name": "Kenya",             "income": "LMIC",  "region": "SSA"},
    {"iso3": "COD", "name": "DR Congo",          "income": "LIC",   "region": "SSA"},
    {"iso3": "ZMB", "name": "Zambia",            "income": "LMIC",  "region": "SSA"},
    {"iso3": "ZWE", "name": "Zimbabwe",          "income": "LMIC",  "region": "SSA"},
    # Middle East & North Africa
    {"iso3": "SYR", "name": "Syria",             "income": "LMIC",  "region": "MENA"},
    {"iso3": "YEM", "name": "Yemen",             "income": "LIC",   "region": "MENA"},
    {"iso3": "LBN", "name": "Lebanon",           "income": "LMIC",  "region": "MENA"},
    {"iso3": "SDN", "name": "Sudan",             "income": "LIC",   "region": "MENA"},
    # South & Southeast Asia
    {"iso3": "BGD", "name": "Bangladesh",        "income": "LMIC",  "region": "SASIA"},
    {"iso3": "MMR", "name": "Myanmar",           "income": "LMIC",  "region": "SASIA"},
    {"iso3": "PAK", "name": "Pakistan",          "income": "LMIC",  "region": "SASIA"},
    {"iso3": "PHL", "name": "Philippines",       "income": "LMIC",  "region": "SEASIA"},
    {"iso3": "IDN", "name": "Indonesia",         "income": "UMIC",  "region": "SEASIA"},
    # Latin America & Caribbean
    {"iso3": "HTI", "name": "Haiti",             "income": "LIC",   "region": "LAC"},
    {"iso3": "VEN", "name": "Venezuela",         "income": "UMIC",  "region": "LAC"},
    {"iso3": "COL", "name": "Colombia",          "income": "UMIC",  "region": "LAC"},
    {"iso3": "HND", "name": "Honduras",          "income": "LMIC",  "region": "LAC"},
    {"iso3": "GTM", "name": "Guatemala",         "income": "UMIC",  "region": "LAC"},
    # Eastern Europe / Post-Soviet
    {"iso3": "UKR", "name": "Ukraine",           "income": "LMIC",  "region": "EEU"},
    {"iso3": "GEO", "name": "Georgia",           "income": "UMIC",  "region": "EEU"},
    {"iso3": "ARM", "name": "Armenia",           "income": "UMIC",  "region": "EEU"},
    # Upper-middle / comparators
    {"iso3": "ZAF", "name": "South Africa",      "income": "UMIC",  "region": "SSA"},
    {"iso3": "TUR", "name": "Turkey",            "income": "UMIC",  "region": "MENA"},
    {"iso3": "MEX", "name": "Mexico",            "income": "UMIC",  "region": "LAC"},
    # High-income (stressed systems — e.g. COVID, political crisis)
    {"iso3": "GRC", "name": "Greece",            "income": "HIC",   "region": "EUR"},
    {"iso3": "USA", "name": "United States",     "income": "HIC",   "region": "NAM"},
    {"iso3": "BRA", "name": "Brazil",            "income": "UMIC",  "region": "LAC"},
    {"iso3": "IND", "name": "India",             "income": "LMIC",  "region": "SASIA"},
]

ISO3_LIST  = [c["iso3"] for c in COUNTRIES]
ISO3_META  = {c["iso3"]: c for c in COUNTRIES}

# ── Polycrise index weights (tunable) ─────────────────────────────────────────
POLYCRISE_WEIGHTS = {
    "conflict_score":   0.35,   # ACLED armed conflict intensity
    "disaster_score":   0.25,   # EM-DAT natural disaster severity
    "economic_score":   0.25,   # IMF GDP contraction + fiscal stress
    "health_shock":     0.15,   # WHO epidemic/pandemic overlay
}

# ── LLM settings ──────────────────────────────────────────────────────────────
LLM_BACKEND        = "ollama"     # "openai" | "ollama"
OPENAI_MODEL       = "gpt-4o-mini"
OLLAMA_MODEL       = "qwen3:8b"
LLM_CHECKPOINT_DIR = os.path.join(DATA_PROCESSED, "llm_checkpoints")
CLASSIFY_EVERY     = 20   # save checkpoint every N documents

# ── ReliefWeb fetch settings ──────────────────────────────────────────────────
# Register a free appname at: https://apidoc.reliefweb.int/parameters#appname
# Then: export RELIEFWEB_APPNAME='your-appname'
RELIEFWEB_APPNAME       = os.getenv("RELIEFWEB_APPNAME", "")
RW_MAX_DOCS_PER_COUNTRY = 30
RW_FIELDS = ["title", "body", "date", "country", "source", "theme"]
