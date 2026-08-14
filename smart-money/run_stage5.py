"""
Stage 5 — Unified Candidate Pool & Final Report
Independently rerunnable. Steps 5.1 through 5.3.

Reads all qualified and scored wallets from the database (populated by Stages 1–4),
merges them, applies transparency weighting, re-ranks, and exports the final report.

Usage:
  python run_stage5.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import database as db
from ranking.unified_pool import UnifiedPool
from run_logger import StageLogger

CONFIG_PATH = Path(__file__).parent / "config" / "config.json"


def run_stage5(config: dict) -> dict:
    logger = StageLogger("5-unified")
    run_id = db.start_run("stage5")
    logger.info("Stage 5 — Unified Candidate Pool & Final Report starting")

    db.init_db()

    pool_builder = UnifiedPool(config, logger)

    # Step 5.1: Merge, weight, re-rank
    unified_pool = pool_builder.build()
    logger.info(f"Unified pool: {len(unified_pool)} candidates across all sources")

    if not unified_pool:
        logger.warning("Unified pool is empty — ensure Stages 1–4 have completed successfully")
        db.finish_run(run_id, counts={"total_qualified": 0})
        return {}

    # Step 5.2: Generate final report
    final_report = pool_builder.generate_final_report(unified_pool)

    # Step 5.3: Export all outputs
    pool_builder.export_json(final_report)
    pool_builder.export_csv(unified_pool)
    pool_builder.export_markdown(final_report, unified_pool)

    # Export unified disqualified log
    all_disq = db.get_disqualified()
    disq_path = (
        Path(__file__).parent / config["output"]["reports_dir"] / "all_disqualified_final.json"
    )
    with open(disq_path, "w", encoding="utf-8") as f:
        json.dump(all_disq, f, indent=2, default=str)
    logger.info(f"All disqualified log → {disq_path} ({len(all_disq)} entries)")

    db.finish_run(run_id, counts={"total_qualified": len(unified_pool)})
    logger.print_summary()

    # Print shortlist to console for immediate review
    logger.info("\n" + "=" * 60)
    logger.info("FINAL TOP 5 SHORTLIST:")
    for candidate in final_report.get("shortlist_top_5", []):
        logger.info(
            f"  #{candidate['unified_rank']} | {candidate['source']:12s} | "
            f"Score: {candidate['adjusted_composite_score']:.1f} | "
            f"{candidate['address'][:20]}…"
        )
    logger.info("=" * 60)

    return final_report


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    run_stage5(config)


if __name__ == "__main__":
    main()
