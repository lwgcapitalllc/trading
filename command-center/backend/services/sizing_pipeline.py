"""
Wiring between a runner's per-trade export and the pure sizing engine.

Turns the enriched per-trade records a runner emits (the RawTrade contract) into the engine,
runs it in the chosen mode, and persists the audit log + day-by-day timeline + size-correct
daily P&L to the run's report dir. It exposes the engine's daily_pnl so the EXISTING
services.evaluator.evaluate_run grades the SIZED run — no second grader.

This is the FS/IO layer. services.sizing_engine stays pure (no DB, no files).

The runner→engine contract (one dict per signal, the keys RawTrade.from_record reads):
  index, entry_time, exit_time, direction (+1/-1 or 'Long'/'Short'), entry_price, exit_price,
  stop_distance (risk per contract, price points), point_value, commission_per_side?, exit_reason?
ORB (and later the MT5 strategies) must write exactly these; the NT8/MT5 agent exports them.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from services.sizing_engine import RawTrade, run_engine, EngineResult, MODE_CONSISTENT, MODE_BULLET

_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"


def engine_result_to_kpis(result: EngineResult) -> dict:
    """Derive the canonical KPI dict the existing graders read from a SIZED engine run.

    The engine emits sized trades + daily P&L but no KPI summary; ``evaluator.evaluate_run``
    needs ``net_pnl`` and ``worthiness.score_run_after_evals`` needs ``profit_factor`` /
    ``max_drawdown`` / ``trade_count``. This rebuilds that summary from the real sized P&L so
    the sized run is graded on the same KPI shape a native (unit-size) run produces.

    KPI keys mirror runner_dispatch._KPI_KEYS: net_pnl, profit_factor, win_rate, max_drawdown,
    trade_count (+ avg_win/avg_loss). max_drawdown is a POSITIVE magnitude — the largest
    peak-to-trough decline in closed-trade cumulative P&L (worthiness takes abs either way).
    Skipped/blocked signals (contracts == 0) are not trades and never count.
    """
    taken = [t for t in result.sized_trades if not t.skipped and t.contracts > 0]
    pnls = [t.net_pnl for t in taken]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    # PF: undefined with no losses → use gross_win as a finite stand-in (0.0 if no wins either),
    # matching how a no-loss native run reports rather than emitting inf.
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if gross_win else 0.0)

    # Max drawdown over the closed-trade equity walk (sized trades in index order).
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(taken, key=lambda x: x.index):
        equity += t.net_pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    kpis: dict = {
        "net_pnl": round(result.net_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "win_rate": round(len(wins) / len(taken), 4) if taken else 0.0,
        "max_drawdown": round(max_dd, 2),
        "trade_count": len(taken),
    }
    if wins:
        kpis["avg_win"] = round(gross_win / len(wins), 2)
    if losses:
        kpis["avg_loss"] = round(sum(losses) / len(losses), 2)
    return kpis


def engine_result_to_equity_curve(result: EngineResult) -> list[dict]:
    """Per-firm SIZED trade-by-trade equity curve, in the frontend EquityPoint shape.

    Each firm sizes the SAME signals differently and skips different trades on halt/breach days,
    so the sized trade sequence — and its cumulative equity, drawdown and long/short split —
    differs per firm. This rebuilds that curve from the sized trades so BacktestDetail can drive
    the per-firm Drawdown chart, Long-vs-Short breakdown, Calmar, Max DD % and Z-Score off it.
    Skipped/blocked signals (contracts == 0) are not trades and are excluded.
    """
    taken = sorted(
        (t for t in result.sized_trades if not t.skipped and t.contracts > 0),
        key=lambda x: x.index,
    )
    curve: list[dict] = []
    equity = 0.0
    for i, t in enumerate(taken, start=1):
        equity += t.net_pnl
        curve.append({
            "index": i,
            "equity": round(equity, 2),
            "date": t.day,
            "direction": "Long" if t.direction > 0 else "Short",
            "profit": round(t.net_pnl, 2),
        })
    return curve


def is_micro_instrument(instrument: str) -> bool:
    """CME micro-contract naming heuristic — M-prefixed roots are micros (MNQ, MES, MGC)."""
    return (instrument or "").upper().startswith("M")


def _size(run_id: str, trade_records: list[dict], ruleset: dict, *,
          mode: str, instrument: str, strategy: str) -> EngineResult:
    """Build RawTrades from the export and run the pure engine — no persistence."""
    trades = [RawTrade.from_record(r) for r in trade_records]
    return run_engine(
        trades, ruleset, is_micro=is_micro_instrument(instrument), mode=mode,
        instrument=instrument, account_id=run_id, strategy=strategy,
        ruleset_id=ruleset.get("id"))


def run_sizing_engine(run_id: str, trade_records: list[dict], ruleset: dict, *,
                      mode: str = MODE_CONSISTENT, instrument: str = "", strategy: str = "",
                      results_dir: Optional[str | Path] = None) -> EngineResult:
    """Build RawTrades from the export, run the engine, persist artifacts, return the result.

    The caller then feeds ``result.daily_pnl`` to ``evaluator.evaluate_run`` for the verdict.
    """
    result = _size(run_id, trade_records, ruleset, mode=mode,
                   instrument=instrument, strategy=strategy)
    _persist(run_id, result, results_dir)
    return result


def size_run_for_rulesets(run_id: str, trade_records: list[dict], rulesets: list[dict], *,
                          mode: str = MODE_CONSISTENT, instrument: str = "", strategy: str = "",
                          results_dir: Optional[str | Path] = None) -> dict:
    """Size the run once PER ruleset and return grade-ready outputs for each.

    Each prop firm has its own contract ladder and drawdown floor, so the correct
    contract size — and therefore the sized P&L — differs per ruleset. The run is
    sized separately against each.

    The FIRST ruleset is the **primary**: its sized artifacts (decisions, timeline,
    daily P&L) are persisted under the run's headline filenames (engine_timeline.json etc.)
    and become the run's headline. EVERY ruleset's sized KPIs + daily P&L + day-by-day
    timeline are ALSO written to ``ruleset_sizing.json`` (one map keyed by ruleset id), so
    the UI can switch the numbers AND the sized/breakdown charts per firm.

    Returns ``{ruleset_id: {"kpis": dict, "daily_pnl": list, "result": EngineResult}}``.
    """
    out: dict = {}
    for i, ruleset in enumerate(rulesets):
        rid = ruleset.get("id")
        if i == 0:
            res = run_sizing_engine(run_id, trade_records, ruleset, mode=mode,
                                    instrument=instrument, strategy=strategy,
                                    results_dir=results_dir)
        else:
            res = _size(run_id, trade_records, ruleset, mode=mode,
                        instrument=instrument, strategy=strategy)
        out[rid] = {"kpis": engine_result_to_kpis(res), "daily_pnl": res.daily_pnl, "result": res}

    _persist_ruleset_sizing(run_id, out, results_dir)
    return out


def _persist_ruleset_sizing(run_id: str, sized: dict, results_dir: Optional[str | Path]) -> None:
    """Write per-ruleset sized KPIs + daily P&L + timeline so the UI can render each firm.

    One file, ``ruleset_sizing.json``, mapping ruleset id → {kpis, daily_pnl, timeline}.
    The timeline is the same day-by-day record persisted for the primary, per ruleset.
    """
    base = Path(results_dir) if results_dir else _LAB_RESULTS_DIR
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        rid: {
            "kpis": s["kpis"],
            "daily_pnl": s["daily_pnl"],
            "timeline": [asdict(d) for d in s["result"].timeline],
            "equity_curve": engine_result_to_equity_curve(s["result"]),
        }
        for rid, s in sized.items()
    }
    (run_dir / "ruleset_sizing.json").write_text(json.dumps(payload, default=str))


def _persist(run_id: str, result: EngineResult, results_dir: Optional[str | Path]) -> None:
    base = Path(results_dir) if results_dir else _LAB_RESULTS_DIR
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # The audit log — one JSON object per line (decisions are already dicts).
    lines = "".join(json.dumps(d, default=str) + "\n" for d in result.decisions)
    (run_dir / "decisions.jsonl").write_text(lines)

    (run_dir / "engine_timeline.json").write_text(
        json.dumps([asdict(d) for d in result.timeline], default=str))
    (run_dir / "engine_daily_pnl.json").write_text(
        json.dumps(result.daily_pnl, default=str))
