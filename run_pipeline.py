#!/usr/bin/env python3
"""
run_pipeline.py — Polycrise Sentinel
======================================
Master pipeline orchestrator. Runs all 8 stages in sequence.

Usage:
    python run_pipeline.py [OPTIONS]

Options:
    --skip-acled    Skip Stage 1  (use existing acled_annual.csv)
    --skip-emdat    Skip Stage 2  (use existing emdat_annual.csv)
    --skip-imf      Skip Stage 3  (use existing imf_annual.csv)
    --skip-gho      Skip Stage 4  (use existing who_gho_annual.csv)
    --skip-index    Skip Stage 5  (use existing polycrise_index.csv)
    --skip-rw       Skip Stage 6  (use existing reliefweb_docs.csv)
    --skip-llm      Skip Stage 7 and run Stage 8 without governance classifications
                    (RQ1/RQ2 are skipped; RQ3/RQ4 still run)
    --analysis-only Run Stage 8 only (all prior outputs must exist)
"""

import sys, os, time, subprocess, argparse

ROOT    = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
PYTHON  = sys.executable


def banner(title: str):
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")


def run_stage(label: str, script: str, skip: bool = False, extra_args: list | None = None):
    if skip:
        print(f"\n  ⏭  Skipping {label}")
        return

    banner(label)
    t0     = time.time()
    cmd    = [PYTHON, os.path.join(SCRIPTS, script)] + (extra_args or [])
    result = subprocess.run(cmd)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n✗  {label} failed (exit {result.returncode}). Pipeline aborted.")
        sys.exit(result.returncode)
    print(f"\n✓  {label} completed in {elapsed:.1f}s")


def check_prerequisite(path: str, label: str):
    if not os.path.exists(path):
        print(f"✗  Required file not found for --skip: {path}")
        print(f"   Remove --skip-{label} or run the preceding stage first.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Polycrise Sentinel — full pipeline")
    parser.add_argument("--skip-acled",   action="store_true")
    parser.add_argument("--skip-emdat",   action="store_true")
    parser.add_argument("--skip-imf",     action="store_true")
    parser.add_argument("--skip-gho",     action="store_true")
    parser.add_argument("--skip-index",   action="store_true")
    parser.add_argument("--skip-rw",      action="store_true")
    parser.add_argument("--skip-llm",     action="store_true")
    parser.add_argument("--analysis-only",action="store_true",
                        help="Run only Stage 8 — all prior outputs must exist")
    args = parser.parse_args()

    if args.analysis_only:
        args.skip_acled = args.skip_emdat = args.skip_imf  = True
        args.skip_gho   = args.skip_index = args.skip_rw   = True
        args.skip_llm   = True

    proc = os.path.join(ROOT, "data", "processed")

    print("=" * 70)
    print("  POLYCRISE SENTINEL — FULL ANALYSIS PIPELINE")
    print("  Governance Response to Polycrises and Health System Resilience")
    print("=" * 70)

    # ── Stage 1: ACLED conflict ────────────────────────────────────────────────
    if args.skip_acled:
        check_prerequisite(os.path.join(proc, "acled_annual.csv"), "acled")
    run_stage(
        "Stage 1 / 8 — Fetch ACLED Conflict Data",
        "01_fetch_acled.py",
        skip=args.skip_acled,
    )

    # ── Stage 2: EM-DAT disasters ──────────────────────────────────────────────
    if args.skip_emdat:
        check_prerequisite(os.path.join(proc, "emdat_annual.csv"), "emdat")
    run_stage(
        "Stage 2 / 8 — Process EM-DAT Disaster Data",
        "02_process_emdat.py",
        skip=args.skip_emdat,
    )

    # ── Stage 3: IMF economic ─────────────────────────────────────────────────
    if args.skip_imf:
        check_prerequisite(os.path.join(proc, "imf_annual.csv"), "imf")
    run_stage(
        "Stage 3 / 8 — Fetch IMF Economic Stress Data",
        "03_fetch_imf.py",
        skip=args.skip_imf,
    )

    # ── Stage 4: WHO GHO ──────────────────────────────────────────────────────
    if args.skip_gho:
        check_prerequisite(os.path.join(proc, "who_gho_annual.csv"), "gho")
    run_stage(
        "Stage 4 / 8 — Fetch WHO GHO Health System Indicators",
        "04_fetch_who_gho.py",
        skip=args.skip_gho,
    )

    # ── Stage 5: Polycrise Index ──────────────────────────────────────────────
    if args.skip_index:
        check_prerequisite(os.path.join(proc, "polycrise_index.csv"), "index")
    run_stage(
        "Stage 5 / 8 — Build Polycrise Exposure Index",
        "05_build_polycrise_index.py",
        skip=args.skip_index,
    )

    # ── Stage 6: ReliefWeb documents ─────────────────────────────────────────
    if args.skip_rw:
        check_prerequisite(os.path.join(proc, "reliefweb_docs.csv"), "rw")
    run_stage(
        "Stage 6 / 8 — Fetch ReliefWeb Policy Documents",
        "06_fetch_reliefweb.py",
        skip=args.skip_rw,
    )

    # ── Stage 7: LLM Classification ──────────────────────────────────────────
    # NOTE: llm_tagged_docs.csv is *optional* — stage 8 will skip RQ1/RQ2 if absent.
    run_stage(
        "Stage 7 / 8 — LLM Governance Response Classification",
        "07_llm_classify_responses.py",
        skip=args.skip_llm,
    )

    # ── Stage 8: Analysis ─────────────────────────────────────────────────────
    analysis_args = ["--no-llm"] if args.skip_llm else []
    run_stage(
        "Stage 8 / 8 — Correlate Outcomes and Generate Figures",
        "08_correlate_outcomes.py",
        extra_args=analysis_args,
    )

    banner("PIPELINE COMPLETE")
    print(f"  Outputs → {os.path.join(ROOT, 'outputs')}/")
    print(f"  Processed data → {proc}/\n")


if __name__ == "__main__":
    main()
