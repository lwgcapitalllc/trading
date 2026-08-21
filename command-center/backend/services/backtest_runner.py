"""
Async background poller for VPS backtest jobs.
Spawned as an asyncio.Task from the backtests router after POSTing to the VPS agent.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sys
import time
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from services import evaluator, lab_db, runner_dispatch, sizing_pipeline, worthiness

# Add engines/ to sys.path so we can import from trading/engines/regime/
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from regime import classify_regime

from services.metrics import (
    apply_canonical_sharpe,
    max_drawdown_pct,
    profit_concentration_pct,
    scratch_count,
    trade_concentration_pct,
)
from services.ohlc_fetcher import get_ohlc

log = logging.getLogger("backtest_runner")


# ── NT8 Trades CSV parser ──────────────────────────────────────────────────────


def _parse_dollar(s: str) -> float:
    """'($2448.00)' → -2448.0, '$594.00' → 594.0"""
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        try:
            return -float(s[1:-1])
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_nt8_dt(s: str) -> Optional[datetime]:
    """Parse an NT8 export timestamp ('MM/DD/YYYY hh:mm:ss AM' or 24h) to a UTC datetime.
    The VPS NinjaTrader Time zone is UTC (Tools → Options → General), so a naive value IS UTC —
    no offset applied. Returns None if the field is blank/unparseable."""
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def parse_trades_csv(csv_text: str) -> tuple[list[dict], list[dict]]:
    """Parse NT8 Trades export CSV.
    Returns (equity_curve, daily_pnl) ready for JSON serialisation."""
    reader = csv.DictReader(io.StringIO(csv_text))
    equity_curve: list[dict] = []
    daily_map: dict[str, float] = {}

    for row in reader:
        try:
            trade_num = int(float(row.get("Trade number", 0) or 0))
        except (ValueError, TypeError):
            continue

        cum_pnl = _parse_dollar(row.get("Cum. net profit", "0"))
        profit = _parse_dollar(row.get("Profit", "0"))
        direction = (row.get("Market pos.", "") or "").strip()
        exit_name = (row.get("Exit name", "") or "").strip()

        # Per-trade size (contracts) — tolerant of header naming; null if not exported.
        size: Optional[int] = None
        qty_raw = next((row.get(c) for c in ("Quantity", "Qty", "Contracts") if row.get(c)), None)
        if qty_raw:
            try:
                size = int(float(str(qty_raw).replace(",", "").strip()))
            except (ValueError, TypeError):
                size = None

        exit_dt = _parse_nt8_dt(row.get("Exit time", ""))
        exit_date = exit_dt.strftime("%Y-%m-%d") if exit_dt else None
        # Trade OPEN time in UTC epoch ms — what the news filter tests against (did the trade enter
        # inside a news window?). Null on old runs re-parsed without an Entry time column.
        entry_dt = _parse_nt8_dt(row.get("Entry time", ""))
        entry_ms = int(entry_dt.timestamp() * 1000) if entry_dt else None

        equity_curve.append(
            {
                "index": trade_num,
                "equity": round(cum_pnl, 2),
                "date": exit_date,
                "entry_ms": entry_ms,
                "direction": direction or None,
                "profit": round(profit, 2),
                "exit_name": exit_name or None,
                "size": size,
            }
        )

        if exit_date:
            daily_map[exit_date] = round(daily_map.get(exit_date, 0.0) + profit, 2)

    daily_pnl = [{"date": d, "pnl": v} for d, v in sorted(daily_map.items())]
    return equity_curve, daily_pnl


_POLL_INTERVAL = 5  # seconds between agent polls
_STALL_WARN_SEC = 120  # 2 min — warn but keep polling
_STALL_KILL_SEC = 600  # 10 min with NO HEARTBEAT — cancel job, mark failed_timeout

# A job that is heartbeating is WORKING, however long it takes. This used to be the same
# constant as the stall kill, so every backtest carried a hard 10-minute ceiling and a healthy
# 11-minute run was killed with the message "No heartbeat for 0s" — a false diagnosis pointing
# at the agent. The longest completed run in the lab is 275s today, so the old ceiling had not
# yet bitten; a tick-mode run, a wider window or a slower box would have crossed it silently.
_MAX_RUNTIME_SEC = 6 * 3600

_LAB_PROGRESS_PATH = Path(__file__).parent.parent / "data" / "lab_progress.json"
_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
LAB_RESULTS_DIR = _LAB_RESULTS_DIR


# ── Progress file helpers ──────────────────────────────────────────────────────


def _write_progress(data: dict) -> None:
    _LAB_PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAB_PROGRESS_PATH.write_text(json.dumps(data, default=str))


def read_progress() -> dict:
    try:
        return json.loads(_LAB_PROGRESS_PATH.read_text())
    except Exception:
        return {"status": "idle", "pct": 0, "message": ""}


def clear_progress() -> None:
    _write_progress({"status": "idle", "pct": 0, "message": ""})


def write_job_progress(job_id: str, pct: int, message: str, started_at: float) -> None:
    _write_progress(
        {
            "job_id": job_id,
            "status": "running",
            "pct": pct,
            "message": message,
            "started_at": str(started_at),
            "updated_at": str(time.time()),
        }
    )


# ── Failure path ───────────────────────────────────────────────────────────────


def _fail(run_id: str, job_id: str, status: str, error_msg: str) -> None:
    lab_db.update_run_status(run_id, status, error_msg)
    _write_progress(
        {
            "job_id": job_id,
            "status": status,
            "pct": 0,
            "message": error_msg,
            "error_message": error_msg,
            "updated_at": str(time.time()),
            "heartbeat_age_seconds": 0.0,
        }
    )


def _write_or_clear(path: Path, payload: list) -> None:
    """Write the payload, or DELETE the file when there is nothing to write.

    An optional artefact's absence is what makes its layer vanish from the chart, so leaving a
    previous attempt's file behind is not a stale number — it is the old run's data rendered as
    this one's.
    """
    if payload:
        path.write_text(json.dumps(payload, default=str))
    elif path.exists():
        path.unlink()


def run_was_cancelled(run_id: str) -> bool:
    """Has something else already ended this run?

    The DB row is the single lock source, so it is also the single place a cancellation is
    recorded. `POST /runs/{id}/stop` writes `failed_cancelled` and this poller reads it back —
    without that read the poller kept going, and when the agent eventually finished,
    `_handle_complete` wrote KPIs and `complete` straight over the cancelled row. The user saw
    a run they had stopped come back to life with results.

    An unreadable row answers False: the poller carrying on is recoverable, abandoning a live
    run because sqlite was momentarily busy is not.
    """
    try:
        row = lab_db.get_run(run_id)
    except Exception:  # noqa: BLE001 — a poll must not die on a read
        return False
    if not row:
        return False
    return row.get("status") != "running"


# ── Regime classification helper ──────────────────────────────────────────────

_WARMUP_DAYS = 50  # fetch this many extra days before backtest start for classifier warmup
_WINDOW_SIZE = 34  # classifier needs 34 bars to produce a non-UNKNOWN label


def _fetch_regime_dfs(
    instrument: str,
    warmup_start: str,
    end_date: str,
    runner: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df_short, df_long) for classify_regime().

    ninjatrader — daily via yfinance; same df passed for both short and long.
    mt5         — H1 for short, H4 for long; fetched from MT5 agent via tunnel.
    python      — H1/H4 from the backtest cache: the SAME bars the run replayed.

    50 calendar days of warmup gives ~214 H4 bars for the intraday paths (>> 34 needed) so
    every path produces real labels from day 1 of the backtest.

    Why python does NOT fall back to yfinance: the yfinance path maps XAUUSD.s → GC=F, i.e. it
    would label a spot-gold run's regimes off Yahoo's gold FUTURES daily bars — a different
    instrument on a different feed at a coarser resolution than the run traded. Wrong labels
    are worse than honest UNKNOWNs, since they silently drive the regime filter and overlays.
    """
    if runner in ("mt5", "python"):
        try:
            h1 = get_ohlc(instrument, warmup_start, end_date, timeframe="H1", runner=runner)
            h4 = get_ohlc(instrument, warmup_start, end_date, timeframe="H4", runner=runner)
            if not h1.empty and not h4.empty:
                return h1, h4
        except Exception as exc:
            log.warning("%s H1/H4 fetch failed for %s: %s", runner, instrument, exc)
        if runner == "python":
            empty = pd.DataFrame(columns=["open", "high", "low", "close"])
            return empty, empty
        # MT5 falls back to yfinance daily (same path as ninjatrader) — works for all
        # forex symbols now that INSTRUMENT_YFINANCE_MAP covers XAUUSD, EURUSD, etc.
    daily = get_ohlc(instrument, warmup_start, end_date)
    return daily, daily


def _build_window(df: pd.DataFrame, entry_date: str, intraday: bool) -> pd.DataFrame:
    """Return the tail(_WINDOW_SIZE) window of df up to and including entry_date.

    For daily bars, cutoff = midnight of entry_date (index <= cutoff includes that day).
    For intraday bars, cutoff = midnight of the next day (index < day_end includes all
    bars on entry_date, including late-evening bars that would be missed by <= midnight).
    """
    if intraday:
        day_end = pd.Timestamp(entry_date) + pd.Timedelta(days=1)
        return df[df.index < day_end].tail(_WINDOW_SIZE)
    cutoff = pd.Timestamp(entry_date)
    return df[df.index <= cutoff].tail(_WINDOW_SIZE)


def _tag_daily_pnl_with_regime(
    instrument: str,
    start_date: str,
    end_date: str,
    daily_pnl: list[dict],
    runner: str = "ninjatrader",
) -> list[dict]:
    """
    Fetch OHLC for the backtest period (extended back by _WARMUP_DAYS for warmup),
    then classify each daily_pnl entry by running the rolling 34-bar window through
    classify_regime(). Returns the daily_pnl list with 'regime_tag' added to every entry.

    runner="ninjatrader" — daily OHLC via yfinance; classify_regime(daily, daily).
    runner="mt5"         — H1 + H4 via MT5 agent; classify_regime(h1, h4).
    runner="python"      — H1 + H4 from the backtest cache (the bars the run replayed).
    """
    warmup_start = (date.fromisoformat(start_date) - timedelta(days=_WARMUP_DAYS)).isoformat()
    intraday = runner in ("mt5", "python")  # both fetch H1/H4, not daily bars

    try:
        df_short, df_long = _fetch_regime_dfs(instrument, warmup_start, end_date, runner)
    except Exception as exc:
        log.warning(
            "OHLC fetch failed for %s [%s, %s]: %s — all regime_tags = UNKNOWN",
            instrument,
            start_date,
            end_date,
            exc,
        )
        return [{**entry, "regime_tag": "UNKNOWN"} for entry in daily_pnl]

    if df_long.empty:
        log.warning(
            "No OHLC rows for %s [%s, %s] — all regime_tags = UNKNOWN",
            instrument,
            start_date,
            end_date,
        )
        return [{**entry, "regime_tag": "UNKNOWN"} for entry in daily_pnl]

    result = []
    for entry in daily_pnl:
        entry_date = entry.get("date")
        if not entry_date:
            result.append({**entry, "regime_tag": "UNKNOWN"})
            continue

        try:
            window_short = _build_window(df_short, entry_date, intraday)
            window_long = _build_window(df_long, entry_date, intraday)
        except Exception:
            result.append({**entry, "regime_tag": "UNKNOWN"})
            continue

        if len(window_long) < _WINDOW_SIZE or len(window_short) < _WINDOW_SIZE:
            result.append({**entry, "regime_tag": "UNKNOWN"})
            continue

        try:
            label = classify_regime(window_short, window_long)
        except Exception as exc:
            log.warning("classify_regime failed for %s on %s: %s", instrument, entry_date, exc)
            label = "UNKNOWN"

        result.append({**entry, "regime_tag": label})

    tagged = sum(1 for r in result if r.get("regime_tag") != "UNKNOWN")
    log.info(
        "Regime classification (%s): %d/%d days tagged (instrument=%s)",
        runner,
        tagged,
        len(result),
        instrument,
    )
    return result


def build_regime_timeline_and_tag(
    instrument: str,
    start_date: str,
    end_date: str,
    daily_pnl: list[dict],
    runner: str = "ninjatrader",
) -> tuple[list[dict], list[dict]]:
    """
    Classify EVERY trading day in [start_date, end_date] once, then tag daily_pnl from
    that same map. Returns (regime_timeline, tagged_daily_pnl).

    Why the whole calendar and not just the traded days: regime is a property of the
    MARKET on a date, not of a run. Tagging only the days a run happened to trade left the
    charts with no label for every quiet stretch — so the regime bands were drawn by
    carrying the last traded day's tag forward, and two runs of the same strategy over the
    same window disagreed about what regime the market was in. The timeline is the honest
    answer and both charts read it.

    Cheaper than the old per-entry pass too: one classification per trading day, reused.
    """
    date_map = build_date_regime_map(instrument, start_date, end_date, runner)
    if not date_map:
        log.warning(
            "No regime map for %s [%s, %s] — all regime_tags = UNKNOWN",
            instrument,
            start_date,
            end_date,
        )
        return [], [{**entry, "regime_tag": "UNKNOWN"} for entry in daily_pnl]

    timeline = [{"date": d, "regime": r} for d, r in sorted(date_map.items())]
    days = [t["date"] for t in timeline]

    tagged = []
    for entry in daily_pnl:
        day = entry.get("date")
        label = date_map.get(day) if day else None
        if label is None and day:
            # A P&L day the bar feed has no bar for (a Sunday-open forex fill, a broker
            # holiday). Carry the last classified day — the same window the per-entry
            # classifier would have built, since it looks back from that date anyway.
            i = bisect_right(days, day) - 1
            label = date_map[days[i]] if i >= 0 else "UNKNOWN"
        tagged.append({**entry, "regime_tag": label or "UNKNOWN"})

    tagged_n = sum(1 for r in tagged if r.get("regime_tag") != "UNKNOWN")
    log.info(
        "Regime classification (%s): %d calendar days, %d/%d P&L days tagged (instrument=%s)",
        runner,
        len(timeline),
        tagged_n,
        len(tagged),
        instrument,
    )
    return timeline, tagged


def build_date_regime_map(
    instrument: str,
    start_date: str,
    end_date: str,
    runner: str = "ninjatrader",
) -> dict[str, str]:
    """
    Fetch OHLC for the given range (with warmup) and classify each trading day.
    Returns {date_str: regime_label} for all dates within [start_date, end_date].
    Intended for optimizer scoring — called once per optimization, not once per child run.

    runner="ninjatrader" — daily OHLC; iterates over daily bar timestamps.
    runner="mt5"         — H1+H4 OHLC; collects distinct dates from H4 bars,
                           builds intraday windows at end of each day.
    """
    warmup_start = (date.fromisoformat(start_date) - timedelta(days=_WARMUP_DAYS)).isoformat()
    intraday = runner in ("mt5", "python")  # both fetch H1/H4, not daily bars

    try:
        df_short, df_long = _fetch_regime_dfs(instrument, warmup_start, end_date, runner)
    except Exception as exc:
        log.warning("build_date_regime_map: OHLC fetch failed for %s: %s", instrument, exc)
        return {}

    if df_long.empty:
        return {}

    result: dict[str, str] = {}

    if intraday:
        # Use H4 bar dates as the set of "trading days" to classify (H4 has fewer
        # bars than H1, so iterating over it is the natural anchor).
        trading_dates = sorted(
            {str(ts.date()) for ts in df_long.index if start_date <= str(ts.date()) <= end_date}
        )
        for date_str in trading_dates:
            window_short = _build_window(df_short, date_str, intraday=True)
            window_long = _build_window(df_long, date_str, intraday=True)
            if len(window_long) < _WINDOW_SIZE or len(window_short) < _WINDOW_SIZE:
                result[date_str] = "UNKNOWN"
            else:
                try:
                    result[date_str] = classify_regime(window_short, window_long)
                except Exception:
                    result[date_str] = "UNKNOWN"
    else:
        for ts in df_long.index:
            date_str = str(ts.date())
            if date_str < start_date or date_str > end_date:
                continue
            window = df_long[df_long.index <= ts].tail(_WINDOW_SIZE)
            if len(window) < _WINDOW_SIZE:
                result[date_str] = "UNKNOWN"
            else:
                try:
                    result[date_str] = classify_regime(window, window)
                except Exception:
                    result[date_str] = "UNKNOWN"

    log.info(
        "build_date_regime_map (%s): %d trading days classified for %s [%s, %s]",
        runner,
        len(result),
        instrument,
        start_date,
        end_date,
    )
    return result


# ── Completion path ────────────────────────────────────────────────────────────


async def _handle_complete(
    run_id: str,
    job_id: str,
    strategy_id: str,
    instrument: str,
    firm_ids: list[str],
    started_at: float = 0.0,
) -> None:
    try:
        result = await asyncio.to_thread(runner_dispatch.job_results, job_id)
    except Exception as exc:
        _fail(run_id, job_id, "failed_unknown", f"Could not fetch results from agent: {exc}")
        return

    # Re-check AFTER the fetch, not only before it. The poller's own check happens once every
    # five seconds; this await is where a Stop lands most often, and everything below writes.
    if await asyncio.to_thread(run_was_cancelled, run_id):
        log.info("run %s: cancelled while results were being fetched — discarding them", run_id)
        return

    kpis = result.get("kpis", {})
    equity_curve = result.get("equity_curve", [])
    daily_pnl = result.get("daily_pnl", [])

    # ── Dynamic sizing — only when the runner shipped the per-trade engine export ──
    # A reshaped strategy (ORB) runs at unit size and emits the runner→engine contract
    # records as result["engine_trades"]. When present, THAT is the real run: the firm's
    # contract ladder is enforced and the run is sized per ruleset (each firm's ladder/
    # floor differ). The first ruleset is the headline; each ruleset is graded against its
    # OWN sized P&L below. Native (unit-size) runs carry no engine_trades → unchanged.
    # A SELF-SIZING strategy already applied its own risk % to every trade, so its results ARE
    # the real run. Re-sizing it would throw that away and, worse, leave the KPI cards (engine-
    # sized) disagreeing with the equity chart (strategy-sized) on the same page. Its risk knob
    # is a strategy param — editable per run and sweepable in the optimizer — not a lab mode.
    strategy_row = lab_db.get_strategy(strategy_id) or {}
    self_sizing = bool(strategy_row.get("self_sizing"))

    sized_by_ruleset = None
    engine_trades = result.get("engine_trades") or []
    if engine_trades and firm_ids and not self_sizing:
        rulesets = [r for r in (lab_db.get_ruleset(fid) for fid in firm_ids) if r]
        if rulesets:
            # Per-run mode chosen at run creation; fall back to consistent for old/invalid rows.
            run_row = lab_db.get_run(run_id) or {}
            mode = run_row.get("sizing_mode") or sizing_pipeline.MODE_CONSISTENT
            manual_pct = run_row.get("manual_risk_pct")
            if mode not in sizing_pipeline.MODES:
                mode = sizing_pipeline.MODE_CONSISTENT
            # Manual with no % is a broken row, not a reason to crash the run: fall back to the
            # automatic mode rather than raise out of the completion path.
            if mode == sizing_pipeline.MODE_MANUAL and not manual_pct:
                log.warning(
                    "run %s: sizing_mode=manual with no manual_risk_pct — using consistent", run_id
                )
                mode = sizing_pipeline.MODE_CONSISTENT
            sized_by_ruleset = sizing_pipeline.size_run_for_rulesets(
                run_id,
                engine_trades,
                rulesets,
                mode=mode,
                instrument=instrument,
                strategy=strategy_id,
                manual_risk_pct=manual_pct,
            )
            primary = rulesets[0]["id"]
            kpis = dict(sized_by_ruleset[primary]["kpis"])
            daily_pnl = sized_by_ruleset[primary]["daily_pnl"]
            # equity_curve stays the agent's unit-size reference (contract-cap is informational;
            # the engine already enforces the real ladder). A sized equity curve is a later UI item.

    # persist JSON files
    run_dir = _LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    equity_path = run_dir / "equity_curve.json"
    daily_pnl_path = run_dir / "daily_pnl.json"
    equity_path.write_text(json.dumps(equity_curve, default=str))
    daily_pnl_path.write_text(json.dumps(daily_pnl, default=str))

    # Blocked setups — signals the strategy's own toggles refused, which place no order and
    # so appear in NO trade list. Only runners that report them write the file (Python today);
    # its absence is what makes the chart's Blocked layer vanish for an NT8/MT5 run.
    #
    # ⚠ An EMPTY result must REMOVE a stale file, never leave it. `if blocked:` alone meant a
    # rerun that refused nothing kept the previous attempt's refusals on disk, and the chart
    # drew them over the new run's candles as though this run had produced them.
    blocked = result.get("blocked_setups") or []
    _write_or_clear(run_dir / "blocked_setups.json", blocked)

    # Missed setups — the companion question: not "which ready trade was refused" but "how far
    # did this setup get before it died". Same optionality, same reason.
    missed = result.get("missed_setups") or []
    _write_or_clear(run_dir / "missed_setups.json", missed)

    # Regime tagging — happens BEFORE DB update so the run stays "running" during tagging,
    # letting the frontend show the Tagging milestone step in the progress bar.
    if daily_pnl:
        run_row = lab_db.get_run(run_id)
        _write_progress(
            {
                "job_id": job_id,
                "job_type": "backtest",
                "status": "running",
                "strategy_id": strategy_id,
                "instrument": instrument,
                "pct": 96,
                "message": "Tagging regimes…",
                "started_at": str(started_at) if started_at else None,
                "updated_at": str(time.time()),
                "heartbeat_age_seconds": 0.0,
                "error_message": None,
            }
        )
        regime_timeline, tagged_pnl = await asyncio.to_thread(
            build_regime_timeline_and_tag,
            instrument,
            (run_row or {}).get("start_date", ""),
            (run_row or {}).get("end_date", ""),
            daily_pnl,
            (run_row or {}).get("runner", "ninjatrader"),
        )
        daily_pnl_path.write_text(json.dumps(tagged_pnl, default=str))
        # The full-calendar regime timeline — every trading day in the window, not just the
        # days this run traded. Both equity charts draw their bands from it.
        (run_dir / "regime_timeline.json").write_text(json.dumps(regime_timeline, default=str))

    # Canonical Sharpe — shared daily-√252 value (consistent across every run path),
    # preserving the platform's own value as platform_sharpe and flagging low sample.
    apply_canonical_sharpe(kpis, daily_pnl)
    # Profit concentration (overfit detector) — null on runs with no positive profit. The equity
    # curve is what tells it whether this run COMPOUNDED; without it the figure measures account
    # growth instead of clustering. The basis is stored beside the number so the row says which.
    kpis["profit_concentration_pct"], kpis["profit_concentration_basis"] = profit_concentration_pct(
        daily_pnl, equity_curve
    )
    # The three companions to numbers that are true and get misread (2026-08-01) — the drawdown
    # as a percent of the PEAK it fell from (the list page had dollars only, and $1.7M against
    # $14M of profit reads as 12% where the honest figure is 56%), how many "wins" were really
    # scratches, and how much of the gross a handful of trades made. All three are stored rather
    # than computed on the page because the RUNS LIST is where runs get compared, and it holds no
    # equity curves. See services/metrics.py for each one's reasoning.
    kpis["max_drawdown_pct"] = max_drawdown_pct(equity_curve)
    kpis["scratch_count"] = scratch_count(equity_curve)
    kpis["trade_concentration_pct"] = trade_concentration_pct(equity_curve)
    lab_db.update_run_complete(
        run_id,
        kpis,
        {
            "equity_curve": str(equity_path),
            "trades": None,
            "daily_pnl": str(daily_pnl_path),
        },
    )

    if sized_by_ruleset:
        # Grade each ruleset against its OWN sized run (different ladder → different P&L).
        for rid in firm_ids:
            s = sized_by_ruleset.get(rid)
            if s:
                evaluator.evaluate_run(run_id, [rid], s["kpis"], equity_curve, s["daily_pnl"])
    else:
        evaluator.evaluate_run(run_id, firm_ids, kpis, equity_curve, daily_pnl)

    w = worthiness.score_run_after_evals(
        run_id,
        firm_ids,
        kpis.get("profit_factor"),
        kpis.get("max_drawdown"),
        kpis.get("trade_count"),
    )
    if w:
        lab_db.update_run_worthiness(run_id, w[0], w[1], w[2])

    # Auto-trigger Monte Carlo stress test on Tier 1 results
    if w and w[0] == "TIER_1_STRESS_TEST":
        from services import stress_tester

        asyncio.create_task(stress_tester.trigger_auto_stress_test(run_id, firm_ids))

    _write_progress(
        {
            "job_id": job_id,
            "job_type": "backtest",
            "status": "complete",
            "strategy_id": strategy_id,
            "instrument": instrument,
            "pct": 100,
            "message": "Complete",
            "started_at": None,
            "updated_at": str(time.time()),
            "heartbeat_age_seconds": 0.0,
            "error_message": None,
        }
    )


# ── Main poller ────────────────────────────────────────────────────────────────


async def run_backtest_job(
    run_id: str,
    job_id: str,
    strategy_id: str,
    instrument: str,
    firm_ids: list[str],
    runner: str = "ninjatrader",
) -> None:
    started_at = time.time()
    stall_warned = False

    _write_progress(
        {
            "job_id": job_id,
            "job_type": "backtest",
            "runner": runner,
            "status": "running",
            "strategy_id": strategy_id,
            "instrument": instrument,
            "pct": 0,
            # Python runs in this process — there is no VPS to wait for.
            "message": "Starting…" if runner == "python" else "Waiting for VPS…",
            "started_at": str(started_at),
            "updated_at": str(started_at),
            "heartbeat_age_seconds": 0.0,
            "error_message": None,
        }
    )

    # A python run happens IN THIS PROCESS — there is no agent to be polite to, and `job_status`
    # is a dict read behind a lock. Polling it every 5s meant the progress bar could only move
    # 5 seconds at a time however finely the runner reported, so a smooth number arrived at the
    # screen in steps. Everything else here is an HTTP call to a machine over a tunnel and keeps
    # the original interval.
    poll_interval = 1 if runner == "python" else _POLL_INTERVAL

    while True:
        await asyncio.sleep(poll_interval)

        # Stop pressed (or the row ended some other way) — leave the row and the progress file
        # exactly as the canceller wrote them. Anything written from here would be a report on
        # a run nobody is waiting for, and `complete` would overwrite `failed_cancelled`.
        if await asyncio.to_thread(run_was_cancelled, run_id):
            log.info("run %s: no longer running — poller standing down", run_id)
            return

        try:
            status_data = await asyncio.to_thread(runner_dispatch.job_status, job_id)
        except Exception as exc:
            elapsed = time.time() - started_at
            if elapsed > _STALL_KILL_SEC:
                _fail(
                    run_id,
                    job_id,
                    "failed_timeout",
                    f"Lost contact with VPS agent after {elapsed:.0f}s: {exc}",
                )
                return
            # transient network error — keep trying
            continue

        status = status_data.get("status", "running")
        pct = status_data.get("pct", 0)
        message = status_data.get("message", "")
        updated_at = status_data.get("updated_at", time.time())

        now = time.time()
        try:
            heartbeat_age = now - float(updated_at)
        except Exception:
            heartbeat_age = 0.0

        if heartbeat_age > _STALL_WARN_SEC and not stall_warned:
            stall_warned = True
            message = f"[STALL] No agent heartbeat for {int(heartbeat_age)}s"

        _write_progress(
            {
                "job_id": job_id,
                "job_type": "backtest",
                "status": "running" if not status.startswith("failed") else status,
                "strategy_id": strategy_id,
                "instrument": instrument,
                "pct": pct,
                "message": message,
                "started_at": str(started_at),
                "updated_at": str(now),
                "heartbeat_age_seconds": heartbeat_age,
                "error_message": None,
            }
        )

        if status == "complete":
            await _handle_complete(run_id, job_id, strategy_id, instrument, firm_ids, started_at)
            return

        if status.startswith("failed"):
            _fail(run_id, job_id, status, status_data.get("error") or message)
            return

        # Kill if the agent has gone quiet, or if the job has run past the hard runtime ceiling.
        # The two are DIFFERENT diagnoses and must not share a message: a stall points at the
        # agent, a timeout points at the window being too big for the ceiling. They used to
        # share both the constant and the wording, so a healthy 11-minute run was reported as
        # having no heartbeat for 0 seconds.
        elapsed = now - started_at
        stalled = heartbeat_age > _STALL_KILL_SEC
        overran = elapsed > _MAX_RUNTIME_SEC
        if stalled or overran:
            try:
                await asyncio.to_thread(runner_dispatch.cancel_job, job_id)
            except Exception:
                pass
            reason = (
                f"No heartbeat for {int(heartbeat_age)}s — job cancelled"
                if stalled
                else f"Still running after {elapsed / 3600:.1f}h (ceiling {_MAX_RUNTIME_SEC // 3600}h)"
                f" — job cancelled. The agent was alive throughout; this window is too large for"
                f" the runtime ceiling."
            )
            _fail(run_id, job_id, "failed_timeout", reason)
            return
