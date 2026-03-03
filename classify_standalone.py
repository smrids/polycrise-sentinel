"""
classify_standalone.py — Polycrise Sentinel  (self-contained, no config.py needed)
====================================================================================
Classifies ReliefWeb governance documents using an LLM.

SETUP (pick one backend):

  Option A — OpenAI (fast, ~$0.03 for 434 docs with gpt-4o-mini):
    pip install openai pandas openpyxl
    Set OPENAI_API_KEY below (or export it as env var)

  Option B — Ollama (free, local, needs GPU for speed):
    pip install pandas openpyxl
    ollama pull qwen3:8b && ollama serve   # in a separate terminal
    Set LLM_BACKEND = "ollama" below

INPUT:  reliefweb_docs.csv        (copy from data/processed/)
OUTPUT: llm_tagged_docs.csv       (put back into data/processed/)
        llm_checkpoints/          (auto-resumes if interrupted)
"""

import os, sys, json, time, re
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — edit these before running
# ═══════════════════════════════════════════════════════════════════════════════

LLM_BACKEND   = "openai"       # "openai" or "ollama"

# OpenAI settings (only needed if LLM_BACKEND = "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")   # or paste key directly: "sk-..."
OPENAI_MODEL   = "gpt-4o-mini"

# Ollama settings (only needed if LLM_BACKEND = "ollama")
OLLAMA_MODEL   = "qwen3:8b"
OLLAMA_URL     = "http://localhost:11434"

# File paths (relative to this script's directory)
DOCS_CSV       = "reliefweb_docs.csv"       # input
TAGGED_CSV     = "llm_tagged_docs.csv"      # output
CHECKPOINT_DIR = "llm_checkpoints"

# Save checkpoint every N documents (so interruptions lose at most N docs)
CHECKPOINT_EVERY = 10

# ═══════════════════════════════════════════════════════════════════════════════
# TAXONOMY
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# LLM BACKENDS
# ═══════════════════════════════════════════════════════════════════════════════

def classify_openai(prompt: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        print("Run: pip install openai")
        sys.exit(1)
    key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    if not key:
        print("Set OPENAI_API_KEY in this script or: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model           = OPENAI_MODEL,
        messages        = [{"role": "user", "content": prompt}],
        temperature     = 0,
        response_format = {"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def classify_ollama(prompt: str) -> dict:
    import requests as _req
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream":   False,
        "options":  {"temperature": 0},
        "think":    False,   # qwen3: suppress <think> block for speed
    }
    try:
        resp = _req.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    except _req.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_URL}. "
            "Run 'ollama serve' in another terminal."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")

    raw_text = resp.json()["message"]["content"]
    # Strip residual <think>…</think> in case think=false is ignored
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    # Extract the first JSON object
    json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON found in Ollama response:\n{raw_text[:400]}")
    return json.loads(json_match.group())


def classify_document(row: pd.Series) -> dict:
    prompt = CLASSIFICATION_PROMPT.format(
        country = row.get("country", "Unknown"),
        date    = row.get("date", "Unknown"),
        title   = row.get("title", ""),
        body    = str(row.get("body_snippet", ""))[:2500],
    )
    if LLM_BACKEND == "openai":
        return classify_openai(prompt)
    elif LLM_BACKEND == "ollama":
        return classify_ollama(prompt)
    else:
        raise ValueError(f"Unknown LLM_BACKEND '{LLM_BACKEND}'. Use 'openai' or 'ollama'.")


def validate_result(result: dict) -> dict:
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

# ═══════════════════════════════════════════════════════════════════════════════
# CHECKPOINTING
# ═══════════════════════════════════════════════════════════════════════════════

def load_checkpoint() -> dict:
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    path = os.path.join(CHECKPOINT_DIR, "governance_classifications.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_checkpoint(results: dict):
    path = os.path.join(CHECKPOINT_DIR, "governance_classifications.json")
    with open(path, "w") as f:
        json.dump(results, f)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if not os.path.exists(DOCS_CSV):
        print(f"ERROR: '{DOCS_CSV}' not found in current directory.")
        print("Copy reliefweb_docs.csv from data/processed/ next to this script.")
        sys.exit(1)

    df = pd.read_csv(DOCS_CSV)
    df_classify = df[df["body_length"] > 100].copy().reset_index(drop=True)

    print(f"Polycrise Sentinel — Stage 7: LLM Governance Classification")
    print(f"=" * 60)
    print(f"Backend : {LLM_BACKEND}  (model: {OPENAI_MODEL if LLM_BACKEND == 'openai' else OLLAMA_MODEL})")
    print(f"Input   : {DOCS_CSV}  ({len(df)} total, {len(df_classify)} with body text)")
    print(f"Output  : {TAGGED_CSV}")
    print()

    checkpoint = load_checkpoint()
    already_done = len(checkpoint)
    if already_done:
        print(f"Resuming: {already_done} documents already classified.\n")

    errors = []
    for idx, row in df_classify.iterrows():
        doc_id = str(row["id"])
        if doc_id in checkpoint:
            continue

        label = f"[{idx + 1}/{len(df_classify)}]"
        print(f"{label} {row.get('iso3','')} | {row.get('date','')} | {str(row.get('title',''))[:55]}", end=" … ", flush=True)

        for attempt in range(3):
            try:
                raw    = classify_document(row)
                result = validate_result(raw)
                checkpoint[doc_id] = result
                print(f"✓ {result['primary_type']} (conf={result['confidence']})")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"✗ FAILED: {e}")
                    checkpoint[doc_id] = {
                        "primary_type": "UNCLEAR", "secondary_tags": [],
                        "confidence": 0, "rationale": f"Error: {e}",
                    }
                    errors.append({"id": doc_id, "error": str(e)})
                else:
                    time.sleep(3)

        if (idx + 1) % CHECKPOINT_EVERY == 0:
            save_checkpoint(checkpoint)
            print(f"  ── checkpoint saved ({len(checkpoint)} docs) ──")

    save_checkpoint(checkpoint)
    print(f"\n✓ Final checkpoint saved ({len(checkpoint)} docs total).")

    # Merge back into dataframe
    df_classify["primary_type"]   = df_classify["id"].astype(str).map(
        lambda x: checkpoint.get(x, {}).get("primary_type", "UNCLEAR"))
    df_classify["secondary_tags"] = df_classify["id"].astype(str).map(
        lambda x: ", ".join(checkpoint.get(x, {}).get("secondary_tags", [])))
    df_classify["confidence"]     = df_classify["id"].astype(str).map(
        lambda x: checkpoint.get(x, {}).get("confidence", 0))
    df_classify["rationale"]      = df_classify["id"].astype(str).map(
        lambda x: checkpoint.get(x, {}).get("rationale", ""))

    df_classify.to_csv(TAGGED_CSV, index=False)
    print(f"✓ Output saved → {TAGGED_CSV}  ({len(df_classify):,} rows)")

    print("\nPrimary type distribution:")
    print(df_classify["primary_type"].value_counts().to_string())

    if errors:
        print(f"\n⚠  {len(errors)} docs failed — re-run to retry (checkpoint will resume).")

    print(f"\nDone! Copy '{TAGGED_CSV}' back to data/processed/ and run Stage 8.")


if __name__ == "__main__":
    main()
