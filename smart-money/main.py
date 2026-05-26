"""
Smart Money Replication System — Full Pipeline Orchestrator

Runs all stages in sequence: 1 → 2 (validation pause) → 3 → 4 → 5.
Each stage is independently rerunnable via its own run_stageN.py script.

Usage:
  python main.py                  # full pipeline (pauses at Stage 2 for manual validation)
  python main.py --skip-stage2    # skip manual validation pause (automated mode)
  python main.py --stages 1 5     # run only specific stages
  python main.py --win-rate 0.75  # override win rate threshold for Stage 1

Run individual stages:
  python run_stage1.py
  python run_stage2.py
  python run_stage3.py
  python run_stage4.py
  python run_stage5.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import database as db
from run_logger import get_logger

CONFIG_PATH = Path(__file__).parent / "config" / "config.json"

_log = get_logger("main")


def load_config(win_rate_override: float = None) -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    if win_rate_override is not None:
        config["qualification"]["min_win_rate"] = win_rate_override
        _log.info(f"Win rate override applied: {win_rate_override:.0%}")
    return config


def _banner(stage_name: str):
    _log.info("")
    _log.info("=" * 70)
    _log.info(f"  {stage_name}")
    _log.info("=" * 70)


def run_full_pipeline(config: dict, stages: list[int], skip_stage2: bool = False):
    db.init_db()

    results: dict[int, object] = {}

    # ── Stage 1: Hyperliquid ─────────────────────────────────────────────────
    if 1 in stages:
        _banner("Stage 1 — Hyperliquid Scanner & Profiler")
        from run_stage1 import run_stage1
        results[1] = run_stage1(config)
        _log.info(f"Stage 1 complete — {len(results[1])} profiles built")

    # ── Stage 2: Validate & Calibrate ───────────────────────────────────────
    if 2 in stages:
        _banner("Stage 2 — Validate & Calibrate")
        from run_stage2 import run_stage2
        run_stage2(config)

        if not skip_stage2:
            _log.info("\nStage 2 complete. Please review the validation report above.")
            _log.info("When satisfied, press ENTER to continue to Stage 3.")
            _log.info("(Run with --skip-stage2 to bypass this pause in automated mode)")
            try:
                input("\n>>> Press ENTER to continue to Stage 3, or Ctrl+C to stop: ")
            except KeyboardInterrupt:
                _log.info("\nPipeline paused after Stage 2. Resume by running Stage 3 directly:")
                _log.info("  python run_stage3.py")
                sys.exit(0)

    # ── Stage 3: Solana & Ethereum ───────────────────────────────────────────
    if 3 in stages:
        _banner("Stage 3 — Solana & Ethereum On-Chain")
        from run_stage3 import run_stage3
        results[3] = run_stage3(config)
        _log.info(f"Stage 3 complete — {len(results[3])} on-chain profiles built")

    # ── Stage 4: Forex ───────────────────────────────────────────────────────
    if 4 in stages:
        _banner("Stage 4 — Forex (Myfxbook & FX Blue)")
        from run_stage4 import run_stage4
        results[4] = run_stage4(config)
        _log.info(f"Stage 4 complete — {len(results[4])} forex profiles built")

    # ── Stage 5: Unified Pool & Final Report ─────────────────────────────────
    if 5 in stages:
        _banner("Stage 5 — Unified Candidate Pool & Final Report")
        from run_stage5 import run_stage5
        results[5] = run_stage5(config)
        _log.info("Stage 5 complete — final report generated")

    _banner("Pipeline Complete")
    _log.info("All outputs are in smart-money/reports/")
    _log.info("Run log is in smart-money/data/smart_money.log")

    run_log = db.get_run_log()
    _log.info(f"\nRun history ({len(run_log)} total runs):")
    for run in run_log[:5]:
        duration = (run["completed_at"] or 0) - run["started_at"]
        _log.info(
            f"  {run['stage']:20s} | qualified={run['total_qualified']:>4} | "
            f"elapsed={duration}s"
        )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Smart Money Replication System — Full Pipeline"
    )
    parser.add_argument(
        "--stages", nargs="+", type=int, default=[1, 2, 3, 4, 5],
        help="Which stages to run (e.g. --stages 1 2 3)"
    )
    parser.add_argument(
        "--skip-stage2", action="store_true",
        help="Skip manual validation pause after Stage 2"
    )
    parser.add_argument(
        "--win-rate", type=float, default=None,
        help="Override min_win_rate in config (e.g. 0.75)"
    )
    args = parser.parse_args()

    config = load_config(win_rate_override=args.win_rate)
    run_full_pipeline(config, stages=args.stages, skip_stage2=args.skip_stage2)


if __name__ == "__main__":
    main()
