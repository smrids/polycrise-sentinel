"""
07_llm_classify_responses.py — Polycrise Sentinel
===================================================
Uses an LLM to classify each ReliefWeb document by governance response type.

This is the methodological heart of the project: a systematic, reproducible
taxonomy of how governments and health systems respond to polycrises.

Governance Response Taxonomy (6 mutually exclusive primary types):
  CENTRALISE      — National government takes direct command of response
  DECENTRALISE    — Response authority delegated to sub-national level
  INTEGRATE       — Multi-sector coordination (health + other ministries)
  PARTNER         — International partners/NGOs take primary response role
  INFORMAL        — Community/informal sector mobilised
  RESTRICT        — Rights-limiting measures (lockdowns, curfews, import bans)

Secondary tags (can co-occur):
  FINANCE_EXPAND   — Emergency health financing released
  FINANCE_CONTRACT — Health budget cut or diverted
  SERVICE_SCALE_UP — Health service capacity expanded
  SERVICE_DISRUPTED — Health service continuity disrupted
  EQUITY_MENTIONED  — Equity/vulnerable groups explicitly addressed
  DIGITAL_USED      — Digital tools, data systems, telemedicine used

Supports two LLM backends (configured in config.py):
  - openai  (gpt-4o-mini by default — fast, cheap, good)
  - ollama  (qwen3:8b — fully local, free, slower)

Output:
  data/processed/llm_tagged_docs.csv   — documents + classifications
  outputs/governance_response_summary.xlsx
"""

import os, sys, json, time, re
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (DATA_PROCESSED, OUTPUTS, LLM_BACKEND, OPENAI_KEY,
                    OPENAI_MODEL, OLLAMA_MODEL, LLM_CHECKPOINT_DIR,
                    CLASSIFY_EVERY)

DOCS_CSV      = os.path.join(DATA_PROCESSED, "reliefweb_docs.csv")
TAGGED_CSV    = os.path.join(DATA_PROCESSED, "llm_tagged_docs.csv")
SUMMARY_OUT   = os.path.join(OUTPUTS, "governance_response_summary.xlsx")

# ── Taxonomy ───────────────────────────────────────────────────────────────────
PRIMARY_TYPES = [
    "CENTRALISE", "DECENTRALISE", "INTEGRATE",
    "PARTNER", "INFORMAL", "RESTRICT", "UNCLEAR",
]
SECONDARY_TAGS = [
    "FINANCE_EXPAND", "FINANCE_CONTRACT",
    "SERVICE_SCALE_UP", "SERVICE_DISRUPTED",
    "EQUITY_MENTIONED", "DIGITAL_USED",
]

CLASSIFICATION_PROMPT = """\
You are an expert health systems analyst. Read the following situation report or policy document excerpt and classify the governance response described.

DOCUMENT:
Country: {country}
Date: {date}
Title: {title}
Body: {body}

CLASSIFICATION TASK:
1. PRIMARY RESPONSE TYPE — Assign exactly ONE from:
   CENTRALISE     = National government takes direct command of health response
   DECENTRALISE   = Response authority explicitly delegated to subnational level
   INTEGRATE      = Multi-sector coordination (health + other ministries/sectors)
   PARTNER        = International partners, NGOs, or UN agencies lead the response
   INFORMAL       = Community mobilisation, informal health workers, or civil society lead
   RESTRICT       = Rights-limiting containment measures (lockdowns, quarantine, bans)
   UNCLEAR        = Insufficient information to classify

2. SECONDARY TAGS — Apply ALL that apply (can be empty list):
   FINANCE_EXPAND     = Emergency health financing explicitly released or increased
   FINANCE_CONTRACT   = Health budget cut, frozen, or diverted to other sectors
   SERVICE_SCALE_UP   = Health service capacity, facilities, or workforce expanded
   SERVICE_DISRUPTED  = Health services disrupted, inaccessible, or suspended
   EQUITY_MENTIONED   = Equity, vulnerable groups, or marginalised populations explicitly addressed
   DIGITAL_USED       = Digital tools, health information systems, or telemedicine deployed

3. CONFIDENCE — Rate 1-5 (5 = very confident, 1 = very uncertain)

4. BRIEF RATIONALE — 1-2 sentences explaining your primary classification.

Respond ONLY with valid JSON in exactly this format:
{{
  "primary_type": "CENTRALISE",
  "secondary_tags": ["SERVICE_SCALE_UP", "FINANCE_EXPAND"],
  "confidence": 4,
  "rationale": "The document describes the Ministry of Health issuing national directives..."
}}
"""


# ── LLM backends ───────────────────────────────────────────────────────────────

def classify_openai(prompt: str) -> dict:
    """Call OpenAI API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Run: pip install openai")
    if not OPENAI_KEY:
        raise ValueError(
            "OPENAI_API_KEY not set. Run: export OPENAI_API_KEY='sk-...'\n"
            "Or switch LLM_BACKEND to 'ollama' in config.py for free local inference."
        )
    client = OpenAI(api_key=OPENAI_KEY)
    response = client.chat.completions.create(
        model    = OPENAI_MODEL,
        messages = [{"role": "user", "content": prompt}],
        temperature = 0,
        response_format = {"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def classify_ollama(prompt: str) -> dict:
    """
    Call local Ollama via its REST API (http://localhost:11434).
    Uses requests (already installed) — no 'ollama' Python package needed.
    think=false disables the chain-of-thought scratchpad for speed & clean JSON.
    """
    import requests as _req
    payload = {
        "model":  OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0},
        "think": False,   # qwen3: suppress <think> block
    }
    try:
        resp = _req.post("http://localhost:11434/api/chat",
                         json=payload, timeout=120)
    except _req.exceptions.ConnectionError:
        raise RuntimeError(
            "Cannot reach Ollama at http://localhost:11434. "
            "Make sure Ollama is running: 'ollama serve' (or the app is open)."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")

    raw_text = resp.json()["message"]["content"]
    # Strip any residual <think>…</think> in case think=false isn't honoured
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON in Ollama response:\n{raw_text[:400]}")
    return json.loads(json_match.group())


def classify_document(row: pd.Series) -> dict:
    """Build prompt and call the configured LLM backend."""
    prompt = CLASSIFICATION_PROMPT.format(
        country = row.get("country", "Unknown"),
        date    = row.get("date", "Unknown"),
        title   = row.get("title", ""),
        body    = row.get("body_snippet", "")[:2500],
    )
    if LLM_BACKEND == "openai":
        return classify_openai(prompt)
    elif LLM_BACKEND == "ollama":
        return classify_ollama(prompt)
    else:
        raise ValueError(f"Unknown LLM_BACKEND: '{LLM_BACKEND}'. Use 'openai' or 'ollama'.")


def validate_result(result: dict) -> dict:
    """Ensure result conforms to taxonomy; fill defaults on failure."""
    primary = result.get("primary_type", "UNCLEAR")
    if primary not in PRIMARY_TYPES:
        primary = "UNCLEAR"

    secondary = [t for t in result.get("secondary_tags", []) if t in SECONDARY_TAGS]

    return {
        "primary_type":  primary,
        "secondary_tags": secondary,
        "confidence":    int(result.get("confidence", 1)),
        "rationale":     str(result.get("rationale", ""))[:500],
    }


# ── Checkpointing ──────────────────────────────────────────────────────────────

def load_checkpoint(checkpoint_dir: str) -> dict[str, dict]:
    """Load previously classified doc IDs → results."""
    os.makedirs(checkpoint_dir, exist_ok=True)
    ckpt_file = os.path.join(checkpoint_dir, "governance_classifications.json")
    if os.path.exists(ckpt_file):
        with open(ckpt_file) as f:
            return json.load(f)
    return {}


def save_checkpoint(checkpoint_dir: str, results: dict[str, dict]):
    ckpt_file = os.path.join(checkpoint_dir, "governance_classifications.json")
    with open(ckpt_file, "w") as f:
        json.dump(results, f)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    os.makedirs(OUTPUTS, exist_ok=True)
    os.makedirs(LLM_CHECKPOINT_DIR, exist_ok=True)

    if not os.path.exists(DOCS_CSV):
        print(f"⚠ {DOCS_CSV} not found. Run 06_fetch_reliefweb.py first.")
        sys.exit(1)

    df = pd.read_csv(DOCS_CSV)

    # Only classify documents with meaningful body text
    df_classify = df[df["body_length"] > 100].copy().reset_index(drop=True)
    print(f"Documents to classify: {len(df_classify)} (of {len(df)} total)")
    print(f"LLM backend: {LLM_BACKEND} "
          f"({'model: ' + OPENAI_MODEL if LLM_BACKEND == 'openai' else 'model: ' + OLLAMA_MODEL})\n")

    # Load checkpoint
    checkpoint = load_checkpoint(LLM_CHECKPOINT_DIR)
    print(f"Resuming: {len(checkpoint)} documents already classified.")

    errors = []
    for idx, row in df_classify.iterrows():
        doc_id = str(row["id"])
        if doc_id in checkpoint:
            continue   # already done

        progress = f"[{idx + 1}/{len(df_classify)}]"
        print(f"{progress} {row['iso3']} | {row['date']} | {row['title'][:60]}", end=" … ")

        for attempt in range(3):
            try:
                raw_result  = classify_document(row)
                validated   = validate_result(raw_result)
                checkpoint[doc_id] = validated
                print(f"✓ {validated['primary_type']} (conf={validated['confidence']})")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"✗ FAILED after 3 attempts: {e}")
                    checkpoint[doc_id] = {
                        "primary_type": "UNCLEAR", "secondary_tags": [],
                        "confidence": 0, "rationale": f"Error: {e}",
                    }
                    errors.append({"id": doc_id, "error": str(e)})
                else:
                    time.sleep(3)

        # Periodic checkpoint save
        if (idx + 1) % CLASSIFY_EVERY == 0:
            save_checkpoint(LLM_CHECKPOINT_DIR, checkpoint)
            print(f"  ── checkpoint saved ({len(checkpoint)} docs) ──")

    save_checkpoint(LLM_CHECKPOINT_DIR, checkpoint)
    print(f"\n✓ Final checkpoint saved.")

    # Merge classifications back into dataframe
    df_classify["primary_type"]   = df_classify["id"].astype(str).map(
        lambda x: checkpoint.get(x, {}).get("primary_type", "UNCLEAR"))
    df_classify["secondary_tags"] = df_classify["id"].astype(str).map(
        lambda x: ", ".join(checkpoint.get(x, {}).get("secondary_tags", [])))
    df_classify["confidence"]     = df_classify["id"].astype(str).map(
        lambda x: checkpoint.get(x, {}).get("confidence", 0))
    df_classify["rationale"]      = df_classify["id"].astype(str).map(
        lambda x: checkpoint.get(x, {}).get("rationale", ""))

    df_classify.to_csv(TAGGED_CSV, index=False)
    print(f"✓ Tagged docs saved → {TAGGED_CSV}  ({len(df_classify):,} rows)")

    # Summary
    print("\nPrimary type distribution:")
    print(df_classify["primary_type"].value_counts().to_string())

    type_by_country = pd.crosstab(df_classify["iso3"], df_classify["primary_type"])
    secondary_counts = (
        df_classify["secondary_tags"].str.split(", ").explode().value_counts()
    )

    with pd.ExcelWriter(SUMMARY_OUT, engine="openpyxl") as xls:
        df_classify.to_excel(xls,         sheet_name="Tagged Documents",     index=False)
        type_by_country.to_excel(xls,     sheet_name="Types by Country",     index=True)
        secondary_counts.to_frame("count").to_excel(xls, sheet_name="Secondary Tags", index=True)

    print(f"✓ Governance summary saved → {SUMMARY_OUT}")
    if errors:
        print(f"\n⚠ {len(errors)} documents failed classification — review checkpoint.")


if __name__ == "__main__":
    main()
