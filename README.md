# Polycrise Sentinel 🛡️

**Governance Response to Polycrises and Health System Resilience**
*A data-driven analysis pipeline for HSR2026 — Sub-theme 1: Politics and Polycrises*

---

## The Research Gap

Health systems facing *simultaneous* overlapping crises — a polycrise — behave differently than systems facing sequential single crises. Yet most polycrise analysis relies on retrospective qualitative case studies. No study has systematically:

1. **Quantified** the simultaneity of crises across countries and time
2. **Classified** governance response patterns at scale using AI
3. **Linked** response type to health system outcome trajectories

This pipeline does all three, using only open data.

---

## Research Questions

| # | Question | Method |
|---|---|---|
| RQ1 | What governance response types dominate during polycrises? | LLM classification of ReliefWeb documents |
| RQ2 | Do response types predict UHC coverage trajectories? | Descriptive statistics + confidence intervals |
| RQ3 | Which response patterns are most protective of health system function? | Fixed-effects OLS regression |
| RQ4 | Which crisis combinations (conflict + disaster + economic) are most damaging? | Crisis combination matrix |

---

## Data Sources (All Open)

| Source | What it measures | API? |
|---|---|---|
| [ACLED](https://developer.acleddata.com/) | Armed conflict events, fatalities | ✅ Free key required |
| [EM-DAT](https://www.emdat.be/) | Natural disasters, deaths, affected | ⬇️ Manual download (free) |
| [IMF DataMapper](https://www.imf.org/external/datamapper/api/v1/) | GDP growth, inflation, unemployment | ✅ No key needed |
| [WHO GHO](https://ghoapi.azureedge.net/api/) | UHC index, health workforce, OOP spending | ✅ No key needed |
| [ReliefWeb](https://apidoc.reliefweb.int/) | Situation reports, policy documents | ✅ Free appname required |

---

## Pipeline Architecture

```
ACLED API ──────────────────┐
EM-DAT (manual download) ───┤  Scripts 01–04   data/processed/
IMF DataMapper API ──────────┤─────────────────►  *_annual.csv files
WHO GHO API ────────────────┘
                                    │
                             Script 05
                        Polycrise Exposure Index
                         (PEI, 0–1 per country-year)
                                    │
                      ┌─────────────┘
                 Script 06
           ReliefWeb policy docs
          (fetched for polycrise years)
                      │
                 Script 07
          LLM Governance Classification
          (CENTRALISE / PARTNER / INTEGRATE / ...)
                      │
                 Script 08
           Statistical Analysis + Figures
           outputs/ ← heatmaps, regression tables, charts
```

---

## Governance Response Taxonomy

Derived from the literature on health system governance and crisis response:

| Code | Meaning |
|---|---|
| `CENTRALISE` | National government takes direct command of health response |
| `DECENTRALISE` | Authority delegated to sub-national levels |
| `INTEGRATE` | Multi-sector coordination across ministries/sectors |
| `PARTNER` | International partners (UN, NGOs) lead response |
| `INFORMAL` | Community/civil society/informal health workers mobilised |
| `RESTRICT` | Rights-limiting containment measures |
| `UNCLEAR` | Insufficient information |

Secondary tags capture financing shifts, service continuity, equity framings, and digital tool use.

---

## Setup

### 1. Install dependencies

```bash
cd polycrise-sentinel
pip install -r requirements.txt
```

### 2. Set API credentials

```bash
# Required only for ACLED (Script 01)
export ACLED_EMAIL="your.email@example.com"
export ACLED_KEY="your-acled-api-key"

# Required for ReliefWeb (Script 06) — register free appname:
# https://apidoc.reliefweb.int/parameters#appname
export RELIEFWEB_APPNAME="your-appname"

# Required only if using OpenAI backend for LLM (Script 07)
export OPENAI_API_KEY="sk-..."
```

**ACLED registration:** https://developer.acleddata.com/ (free, instant)

### 3. Download EM-DAT manually

1. Register free at https://www.emdat.be/
2. Download the Public dataset as Excel
3. Save to `data/raw/emdat_public.xlsx`

### 4. Run the pipeline

```bash
# Full pipeline
python run_pipeline.py

# Skip data fetching (if you already have processed files)
python run_pipeline.py --skip-acled --skip-emdat --skip-imf --skip-gho

# Analysis only (after all data is processed and LLM tagged)
python run_pipeline.py --analysis-only
```

### 5. Run individual stages

```bash
python scripts/03_fetch_imf.py        # IMF only (no API key needed — try this first)
python scripts/04_fetch_who_gho.py    # WHO GHO only (no API key needed)
python scripts/05_build_polycrise_index.py  # Build index from whatever is available
python scripts/08_correlate_outcomes.py     # Analysis only
```

---

## LLM Backend Options

Edit `config.py`:

```python
# Use OpenAI (gpt-4o-mini) — fast, cheap (~$0.001/doc), requires API key
LLM_BACKEND  = "openai"
OPENAI_MODEL = "gpt-4o-mini"

# OR use Ollama (local, fully free, requires Ollama installed)
LLM_BACKEND  = "ollama"
OLLAMA_MODEL = "qwen3:8b"
```

---

## Output Files

```
outputs/
  polycrise_heatmap.png            — Country × year PEI heatmap
  rq1_response_frequency.png       — Governance type distribution
  rq2_uhc_by_response_type.png     — UHC change by response type
  rq4_crisis_combination_matrix.png — Crisis combo impacts
  polycrise_summary.xlsx           — Country + region summaries
  governance_response_summary.xlsx — LLM classification results
  analysis_results.xlsx            — Full regression + RQ outputs

data/processed/
  polycrise_index.csv              — Core panel: PEI per country-year
  reliefweb_docs.csv               — Fetched policy documents
  llm_tagged_docs.csv              — Documents + governance classifications
```

---

## Country Sample (30 Countries, 2010–2024)

Covers all income groups and WHO regions, selected to maximise polycrise variability:

- **Sub-Saharan Africa:** Nigeria, Ethiopia, Kenya, DR Congo, Zambia, Zimbabwe, South Africa
- **MENA:** Syria, Yemen, Lebanon, Sudan, Turkey
- **South/SE Asia:** Bangladesh, Myanmar, Pakistan, Philippines, Indonesia, India
- **LAC:** Haiti, Venezuela, Colombia, Honduras, Guatemala, Mexico, Brazil
- **Eastern Europe:** Ukraine, Georgia, Armenia
- **High-income comparators:** Greece, United States

---

## Conference Framing (HSR2026)

**Sub-theme 1 — Politics and Polycrises:** This study directly operationalises "polycrise" as a measurable, systematic concept and provides the first cross-national evidence on which governance responses protect health systems — directly actionable for health diplomacy and global governance reform.

**Potential abstract title:**
> *"Governing through storms: An AI-assisted analysis of health system governance responses to polycrises across 30 countries, 2010–2024"*

---

## Citation / Acknowledgements

Data sources must be cited per their terms:
- ACLED: Raleigh et al. (2010) + current year
- EM-DAT: Guha-Sapir et al., CRED/UCLouvain
- IMF: International Monetary Fund, World Economic Outlook Database
- WHO GHO: World Health Organization, Global Health Observatory
- ReliefWeb: UN OCHA ReliefWeb
