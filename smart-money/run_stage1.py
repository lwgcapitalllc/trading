"""
Stage 1 — Hyperliquid Scanner & Profiler
Independently rerunnable entrypoint. Steps 1.1 through 1.8.

Usage:
  python run_stage1.py
  python run_stage1.py --win-rate 0.75   # override min win rate
  python run_stage1.py --dry-run         # skip API calls, use cached DB data

All outputs land in smart-money/reports/stage1_*.
Database is updated on every run (idempotent — reruns overwrite prior results).
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so all imports resolve
sys.path.insert(0, str(Path(__file__).parent))

import database as db
from run_logger import StageLogger
from run_progress import ProgressWriter
from scanner.hyperliquid import HyperliquidClient, HyperliquidScanner
from profiler.hyperliquid_profiler import HyperliquidProfiler
from profiler.filters import QualificationGate
from profiler.scorer import CompositeScorer
from profiler.reporter import build_wallet_profile, StageReporter


CONFIG_PATH     = Path(__file__).parent / "config" / "config.json"
TEMPLATES_DIR   = Path(__file__).parent / "config" / "templates"
VALID_PROFILES  = ["bot", "human"]


def load_config(profile: str = None, win_rate_override: float = None) -> dict:
    """
    Load pipeline config. Priority:
      1. --profile bot|human  → loads config/templates/{profile}.json
      2. default              → loads config/config.json
    win_rate_override applies on top of whichever config is loaded.
    """
    if profile:
        if profile not in VALID_PROFILES:
            raise ValueError(f"Unknown profile '{profile}'. Valid: {VALID_PROFILES}")
        config_path = TEMPLATES_DIR / f"{profile}.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Profile template not found: {config_path}")
    else:
        config_path = CONFIG_PATH

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    if win_rate_override is not None:
        config["qualification"]["min_win_rate"] = win_rate_override
    return config


def _build_watchlist_entry(
    address: str, trades: list[dict], disq_reason: str, profiler
) -> dict:
    from collections import defaultdict
    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    span_days = (
        int((max(t["close_ts"] for t in trades) - min(t["close_ts"] for t in trades)) / (86_400 * 1_000))
        if len(trades) > 1 else 0
    )
    inst_counts: dict[str, int] = defaultdict(int)
    inst_pnl: dict[str, float] = defaultdict(float)
    for t in trades:
        inst_counts[t["instrument"]] += 1
        inst_pnl[t["instrument"]] += t["pnl"]
    top_instruments = sorted(inst_counts, key=inst_counts.get, reverse=True)[:5]

    balance_series = profiler.reconstruct_balance_series(trades)
    balance_stats = profiler.compute_balance_stats(balance_series)

    return {
        "address": address,
        "source": "hyperliquid",
        "disq_reason": disq_reason,
        "span_days": span_days,
        "trade_count": len(trades),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "total_pnl": round(sum(t["pnl"] for t in trades), 2),
        "net_growth_pct": balance_stats.get("net_growth_pct"),
        "peak_drawdown_pct": balance_stats.get("peak_drawdown_pct"),
        "avg_win_usd": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0.0,
        "avg_loss_usd": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0.0,
        "top_instruments": [
            {"instrument": k, "trade_count": inst_counts[k], "total_pnl": round(inst_pnl[k], 2)}
            for k in top_instruments
        ],
    }


def run_stage1(config: dict, dry_run: bool = False) -> list[dict]:
    progress = ProgressWriter()
    run_id = progress.start(stage=1, stage_name="Hyperliquid scan")

    logger = StageLogger("1-hyperliquid")
    db.init_db()
    db_run_id = db.start_run("stage1")
    logger.info("=" * 60)
    logger.info("Stage 1 — Hyperliquid Scanner & Profiler starting")
    logger.info(f"Config: min_trades={config['qualification']['min_trades']}, "
                f"min_win_rate={config['qualification']['min_win_rate']:.0%}, "
                f"max_drawdown={config['qualification']['max_drawdown']:.0%}")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Step 1.1–1.2: Scan leaderboard, apply initial filters
    # ------------------------------------------------------------------
    hl_cfg = config["hyperliquid"]
    client = HyperliquidClient(
        rate_limit_delay=hl_cfg["rate_limit_delay_seconds"],
        max_retries=hl_cfg["max_retries"],
        backoff_factor=hl_cfg["retry_backoff_factor"],
        timeout=hl_cfg["timeout_seconds"],
    )
    scanner = HyperliquidScanner(client, config, logger)

    if dry_run:
        logger.info("DRY RUN: loading wallets from database instead of API")
        passed_initial = []
        for row in db.get_ranked_wallets(source="hyperliquid"):
            passed_initial.append({
                "address": row["address"],
                "source": "hyperliquid",
                "trade_count": row["trade_count"],
                "account_age_days": row["account_age_days"],
                "fills": [],  # no fills in dry run
            })
        failed_initial = []
    else:
        progress.update(pct=0, phase="fetching leaderboard", message="Fetching leaderboard…")

        # Rolling window of the last 25 scanned addresses — written to progress.json
        # so the frontend can render a live matrix-style feed.
        _recent_scan: list[dict] = []

        def _scan_progress(
            wallets_scanned: int,
            wallets_total: int,
            address: str = "",
            result: str = "",
        ) -> None:
            if address:
                _recent_scan.append({"a": address, "s": "pass" if result == "passed" else "fail"})
                if len(_recent_scan) > 25:
                    _recent_scan.pop(0)
            progress.update(
                pct=int(wallets_scanned / max(wallets_total, 1) * 10),
                phase="scanning wallets",
                message=f"Scanning wallet {wallets_scanned} / {wallets_total}",
                wallets_scanned=wallets_scanned,
                wallets_total=wallets_total,
                recent_addresses=list(_recent_scan),
            )

        passed_initial, failed_initial = scanner.run(on_progress=_scan_progress)

    logger.set("total_scanned", logger.get("total_scanned") or len(passed_initial) + len(failed_initial))

    # Persist disqualified from initial filter and collect for this run's report
    current_disqualified: list[dict] = []
    for w in failed_initial:
        reason = w.get("reason", "initial filter")
        db.log_disqualified(w["address"], "hyperliquid", reason)
        current_disqualified.append({"address": w["address"], "source": "hyperliquid", "reason": reason})

    logger.info(f"Step 1.2 complete — {len(passed_initial)} wallets pass initial filters")

    total_wallets = len(passed_initial)
    progress.update(
        pct=10,
        phase="profiling wallets",
        message=f"Fetched {total_wallets} wallets from leaderboard",
        wallets_total=total_wallets,
    )

    # ------------------------------------------------------------------
    # Steps 1.3–1.5: Profile + filter each wallet
    # ------------------------------------------------------------------
    profiler = HyperliquidProfiler(config, logger)
    gate = QualificationGate(config, logger)
    qualifying: list[dict] = []
    watchlist: list[dict] = []

    for i, wallet in enumerate(passed_initial):
        progress.update(
            pct=10 + int(i / max(total_wallets, 1) * 70),
            phase="profiling wallets",
            message=f"Profiling wallet {i + 1} / {total_wallets}",
            wallets_scanned=i,
            wallets_total=total_wallets,
            qualified_so_far=len(qualifying),
            disqualified_so_far=i - len(qualifying),
        )
        address = wallet["address"]

        # Step 1.3: Parse fills into matched trades
        trades = profiler.profile_wallet(wallet)
        if not trades:
            reason = "No matched trades after fill parsing"
            db.log_disqualified(address, "hyperliquid", reason)
            logger.log_disqualified(address, reason)
            current_disqualified.append({"address": address, "source": "hyperliquid", "reason": reason})
            continue

        # Persist wallet + trades
        wallet_id = db.upsert_wallet(
            address=address,
            source="hyperliquid",
            trade_count=wallet.get("trade_count"),
            account_age_days=wallet.get("account_age_days"),
            first_seen_ts=wallet.get("first_seen_ts"),
        )
        db.insert_trades(wallet_id, trades)

        # Steps 1.4–1.5: Win rate windows + disqualification filters
        qualifies, windows, disq_reason = gate.evaluate(address, trades, source="hyperliquid")
        db.insert_monthly_windows(wallet_id, windows)

        if not qualifies:
            db.log_disqualified(address, "hyperliquid", disq_reason)
            current_disqualified.append({"address": address, "source": "hyperliquid", "reason": disq_reason})
            # Preserve short-history wallets with notable performance for manual review
            if disq_reason and disq_reason.startswith("Trading span"):
                _watchlist_entry = _build_watchlist_entry(address, trades, disq_reason, profiler)
                watchlist.append(_watchlist_entry)
                logger.info(
                    f"Watchlist: {address[:10]}… — "
                    f"PnL ${_watchlist_entry['total_pnl']:,.0f}, "
                    f"WR {_watchlist_entry['win_rate']:.0%}, "
                    f"span {_watchlist_entry['span_days']}d"
                )
            continue

        logger.increment("passed_disqualification_filter")
        yellow_flags = sum(1 for w in windows if w["strike_level"] == 1)
        qualifying.append({
            "wallet": {**wallet, "id": wallet_id, "source": "hyperliquid"},
            "trades": trades,
            "windows": windows,
            "yellow_flags": yellow_flags,
        })

    logger.info(f"Step 1.5 complete — {len(qualifying)} wallets pass all qualification filters")
    logger.set("passed_win_rate_filter", len(qualifying))
    progress.update(
        pct=80,
        phase="scoring",
        message=f"{len(qualifying)} wallets qualified — scoring",
        wallets_scanned=total_wallets,
        wallets_total=total_wallets,
        qualified_so_far=len(qualifying),
        disqualified_so_far=total_wallets - len(qualifying),
    )

    # ------------------------------------------------------------------
    # Step 1.6: Score all qualifying wallets
    # ------------------------------------------------------------------
    scorer = CompositeScorer(config, logger)
    scored: list[dict] = []

    for entry in qualifying:
        score = scorer.compute(entry["trades"], entry["windows"])
        scored.append({**entry, "score": score})

    # Rank and persist scores
    scored = scorer.rank_wallets([{**e, **e["score"]} for e in scored])
    # re-attach score to each entry after ranking
    scored_by_address = {e.get("address") or e["wallet"]["address"]: e for e in scored}

    # Rebuild scored list with proper structure
    final_scored: list[dict] = []
    for entry in qualifying:
        address = entry["wallet"]["address"]
        score_entry = scored_by_address.get(address, {})
        score = scorer.compute(entry["trades"], entry["windows"])
        score["rank"] = score_entry.get("rank")
        final_scored.append({**entry, "score": score})

    # Sort by composite descending
    final_scored.sort(key=lambda e: e["score"]["composite_score"], reverse=True)
    for i, e in enumerate(final_scored, 1):
        e["score"]["rank"] = i

    # Persist scores
    for entry in final_scored:
        wallet_id = entry["wallet"]["id"]
        score = entry["score"]
        db.upsert_score(wallet_id, {
            "win_rate_consistency": score["win_rate_consistency"],
            "risk_adjusted_return": score["risk_adjusted_return"],
            "exit_efficiency": score["exit_efficiency"],
            "trade_frequency": score["trade_frequency"],
            "instrument_day_consistency": score["instrument_day_consistency"],
            "composite_score": score["composite_score"],
            "rank": score["rank"],
            "lookback_tier": score["lookback_tier"],
        })

    logger.info(f"Step 1.6 complete — all {len(final_scored)} wallets scored and ranked")
    progress.update(pct=88, phase="building profiles", message=f"Building {len(final_scored)} wallet profiles")

    # ------------------------------------------------------------------
    # Step 1.7: Build wallet intelligence reports
    # ------------------------------------------------------------------
    from profiler.hyperliquid_profiler import HyperliquidProfiler as _P
    _profiler = _P(config, logger)

    top_n = config["output"]["top_n_profiles"]
    top_wallets = final_scored[:top_n]
    profiles: list[dict] = []

    for entry in top_wallets:
        balance_series = _profiler.reconstruct_balance_series(entry["trades"])
        balance_stats = _profiler.compute_balance_stats(balance_series)
        profile = build_wallet_profile(
            wallet=entry["wallet"],
            trades=entry["trades"],
            windows=entry["windows"],
            score=entry["score"],
            balance_stats=balance_stats,
            yellow_flags=entry.get("yellow_flags", 0),
        )
        profiles.append(profile)
        logger.log_qualified(entry["wallet"]["address"], entry["score"]["composite_score"])

    # ------------------------------------------------------------------
    # Step 1.8: Export outputs
    # ------------------------------------------------------------------
    progress.update(pct=95, phase="exporting", message="Writing output files")
    reporter = StageReporter(config, logger, run_id=run_id)
    run_counts = {
        "total_scanned": logger.get("total_scanned"),
        "passed_initial_filter": len(passed_initial),
        "passed_qualification": len(qualifying),
        "total_qualified": len(final_scored),
        "top_profiles_built": len(profiles),
    }

    # Use only this run's disqualified list — not the full DB history.
    # db.get_disqualified() returns all-time records, which would inflate the
    # UI display and mix in stale data from previous runs with different configs.
    reporter.export_run_dir(profiles, current_disqualified, run_counts)
    reporter.export_json(profiles, stage="stage1")
    reporter.export_csv(profiles, stage="stage1")
    reporter.export_markdown_summary(profiles, stage="stage1", run_counts=run_counts)
    reporter.export_disqualified_log(current_disqualified, stage="stage1")

    # Export watchlist — short-history wallets with notable performance
    if watchlist:
        watchlist.sort(key=lambda w: w.get("total_pnl", 0), reverse=True)
        reporter.export_watchlist(watchlist, stage="stage1")

    # Finalise run log
    db.finish_run(
        db_run_id,
        counts={
            "total_scanned": logger.get("total_scanned"),
            "passed_initial_filter": len(passed_initial),
            "passed_win_rate_filter": len(qualifying),
            "passed_disqualification_filter": len(qualifying),
            "total_qualified": len(final_scored),
        },
        notes=f"Top {len(profiles)} profiles exported",
    )

    progress.complete()
    logger.print_summary()

    # Auto-calibrate: too few → suggest threshold relaxation
    if len(final_scored) < config["pool_calibration"]["thin_pool_threshold"]:
        fallback_wr = config["pool_calibration"]["thin_pool_fallback_win_rate"]
        logger.warning(
            f"Pool size {len(final_scored)} < {config['pool_calibration']['thin_pool_threshold']}. "
            f"Consider rerunning with --win-rate {fallback_wr}"
        )

    if len(final_scored) > config["pool_calibration"]["large_pool_threshold"]:
        tighter_dd = config["pool_calibration"]["large_pool_tighter_drawdown"]
        logger.warning(
            f"Pool size {len(final_scored)} > {config['pool_calibration']['large_pool_threshold']}. "
            f"Consider tightening max_drawdown to {tighter_dd:.0%} in config."
        )

    return profiles


def main():
    parser = argparse.ArgumentParser(description="Run Stage 1 — Hyperliquid scanner and profiler")
    parser.add_argument(
        "--profile", choices=VALID_PROFILES, default=None,
        help="Config profile to use: 'bot' (rapid growth, algo) or 'human' (conservative). "
             "Omit to use config/config.json.",
    )
    parser.add_argument("--win-rate", type=float, default=None,
                        help="Override min_win_rate threshold (e.g. 0.75)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip API calls and use wallets already in the database")
    args = parser.parse_args()

    config = load_config(profile=args.profile, win_rate_override=args.win_rate)
    run_stage1(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
