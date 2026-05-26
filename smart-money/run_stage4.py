"""
Stage 4 — Forex Expansion via Myfxbook & FX Blue
Independently rerunnable. Steps 4.1 through 4.7.

Prerequisites: set MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD, FX_BLUE_SESSION.
Runs cross-referencing between platforms, applies forex-specific rules,
and exports ranked forex candidate profiles.

Usage:
  python run_stage4.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import database as db
from run_logger import StageLogger
from forex.myfxbook import MyfxbookScanner
from forex.fx_blue import FxBlueScanner
from profiler.filters import QualificationGate
from profiler.scorer import CompositeScorer
from profiler.reporter import build_wallet_profile, StageReporter
from profiler.hyperliquid_profiler import HyperliquidProfiler

CONFIG_PATH = Path(__file__).parent / "config" / "config.json"


def _cross_reference_forex(
    myfxbook_accounts: list[dict],
    fx_blue_accounts: list[dict],
    config: dict,
    logger: StageLogger,
) -> list[dict]:
    """
    Step 4.4: Cross-reference Myfxbook and FX Blue accounts.
    Accounts on both platforms have survivorship bias flag removed.
    Accounts on only one platform get a yellow flag.
    Returns merged list with 'dual_verified' and 'survivorship_flag' keys.
    """
    myfxbook_ids = {a["address"] for a in myfxbook_accounts}
    fx_blue_ids = {a["address"] for a in fx_blue_accounts}

    all_accounts: list[dict] = []

    for acct in myfxbook_accounts:
        dual = acct["address"] in fx_blue_ids
        all_accounts.append({
            **acct,
            "dual_verified": dual,
            "survivorship_flag": not dual,
            "source": "myfxbook",
        })

    for acct in fx_blue_accounts:
        if acct["address"] not in myfxbook_ids:
            all_accounts.append({
                **acct,
                "dual_verified": False,
                "survivorship_flag": True,
                "source": "fx_blue",
            })

    dual_count = sum(1 for a in all_accounts if a["dual_verified"])
    logger.info(f"Cross-reference: {dual_count} dual-verified, {len(all_accounts)-dual_count} single-platform")
    return all_accounts


def _apply_forex_specific_rules(
    account: dict, config: dict, logger: StageLogger
) -> tuple[bool, str | None]:
    """
    Step 4.5: Forex-specific additional disqualification rules.
    Returns (passes, reason_if_failed).
    """
    # Single platform → yellow flag, not disqualification
    if account.get("survivorship_flag") and config["forex"]["single_platform_yellow_flag"]:
        logger.warning(f"{account['address'][:12]}… — single-platform survivorship flag noted")

    # Accounts created within 6 months of best performance window → disqualify
    created_months = account.get("account_age_days", 0) / 30
    disq_window = config["forex"]["disqualify_created_within_best_window_months"]
    if created_months < disq_window:
        reason = (
            f"Account created within {created_months:.1f} months of best performance window "
            f"(< {disq_window} month threshold)"
        )
        return False, reason

    return True, None


def run_stage4(config: dict) -> list[dict]:
    logger = StageLogger("4-forex")
    run_id = db.start_run("stage4")
    logger.info("Stage 4 — Forex Expansion starting")

    db.init_db()

    # Steps 4.1–4.2: Myfxbook
    myfxbook_scanner = MyfxbookScanner(config, logger)
    myfxbook_accounts = myfxbook_scanner.scan()
    logger.info(f"Myfxbook: {len(myfxbook_accounts)} candidates")

    # Step 4.3: FX Blue
    fx_blue_scanner = FxBlueScanner(config, logger)
    fx_blue_accounts = fx_blue_scanner.scan()
    logger.info(f"FX Blue: {len(fx_blue_accounts)} candidates")

    if not myfxbook_accounts and not fx_blue_accounts:
        logger.warning("No forex sources configured — Stage 4 produced no results")
        db.finish_run(run_id, counts={"total_scanned": 0})
        return []

    # Step 4.4: Cross-reference
    all_forex = _cross_reference_forex(myfxbook_accounts, fx_blue_accounts, config, logger)

    gate = QualificationGate(config, logger)
    scorer = CompositeScorer(config, logger)
    profiler = HyperliquidProfiler(config, logger)

    qualifying: list[dict] = []

    for account in all_forex:
        address = account["address"]
        source = account["source"]
        trades = account.get("trades", [])

        if not trades:
            reason = "No trades after parsing"
            db.log_disqualified(address, source, reason)
            continue

        # Step 4.5: Forex-specific rules
        forex_ok, forex_reason = _apply_forex_specific_rules(account, config, logger)
        if not forex_ok:
            db.log_disqualified(address, source, forex_reason)
            logger.log_disqualified(address, forex_reason)
            continue

        wallet_id = db.upsert_wallet(
            address=address,
            source=source,
            trade_count=len(trades),
            account_age_days=account.get("account_age_days"),
        )
        db.insert_trades(wallet_id, trades)

        # Standard qualification (Steps 1.4–1.5 applied identically)
        qualifies, windows, disq_reason = gate.evaluate(address, trades, source=source)
        db.insert_monthly_windows(wallet_id, windows)

        if not qualifies:
            db.log_disqualified(address, source, disq_reason)
            continue

        score = scorer.compute(trades, windows)

        # Dual-verified accounts weighted higher (score bonus)
        if account.get("dual_verified") and config["forex"]["dual_platform_bias_removal"]:
            score["composite_score"] = min(100.0, score["composite_score"] * 1.05)

        yellow_flags = sum(1 for w in windows if w["strike_level"] == 1)
        if account.get("survivorship_flag"):
            yellow_flags += 1  # count single-platform as a flag

        qualifying.append({
            "wallet": {**account, "id": wallet_id},
            "trades": trades,
            "windows": windows,
            "score": score,
            "yellow_flags": yellow_flags,
        })

    # Step 4.6: Rank and export
    qualifying.sort(key=lambda e: e["score"]["composite_score"], reverse=True)
    for i, e in enumerate(qualifying, 1):
        e["score"]["rank"] = i
        db.upsert_score(e["wallet"]["id"], {
            "win_rate_consistency": e["score"]["win_rate_consistency"],
            "risk_adjusted_return": e["score"]["risk_adjusted_return"],
            "exit_efficiency": e["score"]["exit_efficiency"],
            "trade_frequency": e["score"]["trade_frequency"],
            "instrument_day_consistency": e["score"]["instrument_day_consistency"],
            "composite_score": e["score"]["composite_score"],
            "rank": e["score"]["rank"],
            "lookback_tier": e["score"]["lookback_tier"],
        })

    top_n = config["output"]["top_n_profiles"]
    profiles: list[dict] = []
    for entry in qualifying[:top_n]:
        balance_series = profiler.reconstruct_balance_series(entry["trades"])
        balance_stats = profiler.compute_balance_stats(balance_series)
        profile = build_wallet_profile(
            wallet=entry["wallet"],
            trades=entry["trades"],
            windows=entry["windows"],
            score=entry["score"],
            balance_stats=balance_stats,
            yellow_flags=entry.get("yellow_flags", 0),
        )
        profiles.append(profile)

    reporter = StageReporter(config, logger)
    run_counts = {"total_scanned": len(all_forex), "total_qualified": len(qualifying)}
    reporter.export_json(profiles, stage="stage4")
    reporter.export_csv(profiles, stage="stage4")
    reporter.export_markdown_summary(profiles, stage="stage4", run_counts=run_counts)

    db.finish_run(run_id, counts={"total_scanned": len(all_forex), "total_qualified": len(qualifying)})
    logger.print_summary()
    return profiles


def main():
    parser = argparse.ArgumentParser(description="Run Stage 4 — Forex (Myfxbook + FX Blue)")
    args = parser.parse_args()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    run_stage4(config)


if __name__ == "__main__":
    main()
