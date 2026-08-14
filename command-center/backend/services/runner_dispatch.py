"""
Dispatcher + NT8 agent client.

This module serves two roles:
  1. NT8 agent client — typed HTTP wrapper over nt8_agent.py at
     http://localhost:8765 (via SSH tunnel). All NT8-specific calls
     (_get/_post, nt_health, nt_log, export_trades, compile, etc.) live here.
  2. Runner dispatcher — start_backtest, job_status, job_results, job_log,
     and cancel_job route to either this module (ninjatrader) or
     mt5_agent_client (mt5) based on the strategy's runner field.

All callers import `runner_dispatch` and call the same functions regardless of
runner. The dispatcher is transparent to every call site.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Optional

import config as cfg

from services import lab_db, mt5_agent_client, python_runner

_TIMEOUT = 10  # seconds for all agent calls


def _get(path: str, timeout: int = _TIMEOUT) -> dict:
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent {path}: {exc}") from exc


def _post(path: str, body: Optional[dict] = None, timeout: int = _TIMEOUT) -> dict:
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent POST {path}: {exc}") from exc


# ── Observability ─────────────────────────────────────────────────────────────


def health() -> dict:
    return _get("/health", timeout=5)


def nt_health() -> dict:
    return _get("/nt-health", timeout=8)


def nt_compile_status() -> dict:
    return _get("/nt-compile-status", timeout=8)


def agent_log(lines: int = 100) -> str:
    try:
        data = _get(f"/agent-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def nt_log(lines: int = 100) -> str:
    try:
        data = _get(f"/nt-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


# ── Foundational config injection ────────────────────────────────────────────


def build_foundational_params(ruleset: dict) -> dict:
    """Return the strategy-param key/value pairs sourced from a ruleset's foundational config.

    These map directly to [Category("Foundational")] NinjaScriptProperty names.
    Call inject_foundational() rather than this directly.

    Only cost + time facts remain. Account size, risk %, daily-loss, halt-fraction,
    consecutive-loss, profit-target and lock-in were removed 2026-06-21 when ORB was reshaped
    to the gated-layer rules: the strategy no longer sizes or self-halts (the dynamic sizing &
    gating engine owns those), so those NinjaScriptProperties no longer exist to inject into.
    """
    days = ruleset.get("days_of_week_allowed") or []
    return {
        "CommissionPerSide": float(ruleset.get("default_commission_per_side") or 0),
        "ForceFlatTimeET": ruleset.get("force_flat_time_et") or "",
        "EarliestEntryTimeET": ruleset.get("earliest_entry_time_et") or "",
        "LatestEntryTimeET": ruleset.get("latest_entry_time_et") or "",
        "DaysOfWeekAllowed": ",".join(days) if isinstance(days, list) else (days or ""),
    }


def inject_foundational(user_params: dict, ruleset: Optional[dict]) -> dict:
    """Merge foundational config from ruleset into user-provided strategy params.

    Primary ruleset rule: only the primary (first evaluate) ruleset injects config.
    User-provided strategy-logic params override foundational if names collide
    (the UI prevents this in practice by hiding foundational params from users).
    Returns user_params unchanged when ruleset is None (backward compat for
    strategies that don't use foundational config, or runs with no evaluate list).
    """
    if ruleset is None:
        return user_params
    merged = build_foundational_params(ruleset)
    merged.update(user_params)
    return merged


# ── Runner dispatcher ─────────────────────────────────────────────────────────


def _resolve_runner(job_id: str, explicit_runner: Optional[str] = None) -> str:
    """Return the runner for a job, preferring an explicit value over a DB lookup.

    Falls back to "ninjatrader" when the job_id isn't in the DB (legacy rows
    predate the runner column on strategies, or the strategy was deleted).
    """
    if explicit_runner:
        return explicit_runner
    run = lab_db.get_run(job_id)
    if run and run.get("runner"):
        return run["runner"]
    return "ninjatrader"


# ── Job control ───────────────────────────────────────────────────────────────


def _nt8_to_mt5_spec(spec: dict) -> dict:
    """
    Translate the NT8-style job_spec to the MT5 agent's expected format.
    NT8: instrument, params, start_date/end_date, bar_type/bar_value
    MT5: symbol, inputs, from_date/to_date, timeframe, deposit, currency, leverage

    job_id is passed through so the MT5 agent stores the job under our run_id —
    without this the agent generates its own UUID and status polls return 404.
    """
    bar_type = spec.get("bar_type", "Minute")
    bar_value = int(spec.get("bar_value") or 60)

    if bar_type == "Day":
        timeframe = "D1"
    elif bar_type == "Minute":
        if bar_value >= 240:
            timeframe = "H4"
        elif bar_value >= 60:
            timeframe = "H1"
        elif bar_value >= 30:
            timeframe = "M30"
        elif bar_value >= 15:
            timeframe = "M15"
        elif bar_value >= 5:
            timeframe = "M5"
        else:
            timeframe = "M1"
    else:
        timeframe = "H1"

    params = spec.get("params", {})
    # Derive deposit — guard against -1 sentinel value (means "not injected yet")
    _f_acct = params.get("f_AccountSize") or params.get("AccountSize")
    deposit = float(_f_acct if _f_acct and _f_acct > 0 else 10000)

    # MeanReversion.mq5 (and all MT5 EAs) call ValidateFoundationalParams() in OnInit and
    # return INIT_FAILED if any f_ param is still at its sentinel value of -1.
    # MT5 backtests have no ruleset, so inject_foundational is never called — provide
    # sensible standalone defaults here. Strip -1 sentinel f_ values from params before
    # merging so they don't override the defaults we just built.
    foundational_defaults = {
        "f_AccountSize": deposit,
        "f_RiskPerTradePct": 1.0,
        "f_DailyLossCap": round(deposit * 0.05, 2),
        "f_DailyHaltFraction": 0.6,
        "f_MaxConsecutiveLosses": 0,  # 0 = disabled
        "f_DailyProfitTarget": 0,  # 0 = disabled
        "f_DailyProfitLockPct": 0,  # 0 = disabled
        "f_BrokerToEtOffsetHours": 99,  # 99 = auto-detect
        "f_CommissionPerSide": float(spec.get("commission_per_side") or 0),
        "f_SlippageTicks": int(spec.get("slippage_ticks") or 0),
    }
    # Only fill standalone defaults for foundational params THIS strategy declares.
    # `params` carries the strategy's scanned inputs, so an f_ key absent here is one
    # the EA doesn't have. Injecting it anyway (e.g. MeanReversion's
    # f_BrokerToEtOffsetHours into LondonBreakout) writes an unknown input into the
    # .set file. MT5 tolerates a lone unknown, but a set file polluted with several is
    # treated as mismatched and the optimizer silently degrades to a single backtest
    # (no opt_results.csv). Strategies always pass their declared f_ params (at the -1
    # sentinel before injection), so a missing key genuinely means "not an EA input".
    foundational_defaults = {k: v for k, v in foundational_defaults.items() if k in params}
    # Drop -1 sentinel f_ values so foundational_defaults fill in instead
    safe_params = {
        k: v
        for k, v in params.items()
        if not (k.startswith("f_") and isinstance(v, (int, float)) and v < 0)
    }
    inputs = {**foundational_defaults, **safe_params}

    return {
        "job_id": spec.get("job_id"),
        "strategy_class": spec["strategy_class"],
        "symbol": spec["instrument"],
        "timeframe": timeframe,
        "from_date": spec["start_date"],
        "to_date": spec["end_date"],
        "model": 1,  # OHLC on M1 — same results as Model=0 for bar-close strategies, ~10x faster
        "deposit": deposit,
        "currency": "USD",
        "leverage": 100,
        "inputs": inputs,
    }


def _nt8_opt_to_mt5_opt_spec(opt_spec: dict) -> dict:
    """
    Translate an NT8-style native optimization spec to the MT5 agent's format.

    NT8 spec: instrument, param_ranges, fixed_params, start_date, end_date, bar_type/bar_value
    MT5 spec: symbol, param_ranges (same), inputs (fixed), from_date, to_date, timeframe
    """
    base = _nt8_to_mt5_spec(
        {
            "job_id": opt_spec.get("job_id"),
            "strategy_class": opt_spec["strategy_class"],
            "instrument": opt_spec["instrument"],
            "bar_type": opt_spec.get("bar_type", "Minute"),
            "bar_value": opt_spec.get("bar_value", 60),
            "start_date": opt_spec["start_date"],
            "end_date": opt_spec["end_date"],
            "commission_per_side": opt_spec.get("commission_per_side", 0),
            "slippage_ticks": opt_spec.get("slippage_ticks", 0),
            "params": opt_spec.get("fixed_params", {}),
        }
    )
    base["param_ranges"] = opt_spec.get("param_ranges", {})
    return base


def start_native_optimization(opt_spec: dict, runner: str = "ninjatrader") -> dict:
    """
    Submit a native optimizer job.

    Routes to NT8 agent (POST /native-optimize) or MT5 agent based on runner.
    opt_spec must include: job_id, strategy_class, instrument, start_date, end_date,
    param_ranges ({name: {min, max, step} | [val, ...]}) and fixed_params ({name: value}).
    """
    if runner == "python":
        return python_runner.start_native_optimization(opt_spec)
    if runner == "mt5":
        return mt5_agent_client.start_native_optimization(_nt8_opt_to_mt5_opt_spec(opt_spec))
    return _post("/native-optimize", opt_spec, timeout=30)


def native_opt_results(job_id: str, runner: str = "ninjatrader") -> dict:
    """Fetch the native optimizer result grid (combos + KPIs) after job completes."""
    if runner == "python":
        return python_runner.native_opt_results(job_id)
    if runner == "mt5":
        return mt5_agent_client.native_opt_results(job_id)
    return _get(f"/jobs/{job_id}/native-opt-results")


def _nt8_wf_to_mt5_wf_spec(wf_spec: dict) -> dict:
    """Translate NT8-style WF spec to MT5 agent format (single IS/OOS split)."""
    base = _nt8_to_mt5_spec(
        {
            "job_id": wf_spec.get("job_id"),
            "strategy_class": wf_spec["strategy_class"],
            "instrument": wf_spec["instrument"],
            "bar_type": wf_spec.get("bar_type", "Minute"),
            "bar_value": wf_spec.get("bar_value", 60),
            "start_date": wf_spec["start_date"],
            "end_date": wf_spec["end_date"],
            "commission_per_side": wf_spec.get("commission_per_side", 0),
            "slippage_ticks": wf_spec.get("slippage_ticks", 0),
            "params": wf_spec.get("params", {}),
        }
    )
    base["oos_pct"] = wf_spec.get("oos_pct", 30)
    return base


def start_native_walkforward(wf_spec: dict, runner: str = "ninjatrader") -> dict:
    """
    Submit a native walk-forward job.

    Routes to NT8 (POST /native-walkforward) or MT5 (POST /native-walkforward) based on runner.
    wf_spec must include: job_id, strategy_class, instrument, start_date, end_date,
    params (flat dict of all fixed param values), and optionally oos_pct (default 30).
    """
    if runner == "mt5":
        return mt5_agent_client.start_native_walkforward(_nt8_wf_to_mt5_wf_spec(wf_spec))
    return _post("/native-walkforward", wf_spec, timeout=30)


def native_wf_results(job_id: str, runner: str = "ninjatrader") -> dict:
    """Fetch native walk-forward results after job completes."""
    if runner == "mt5":
        return mt5_agent_client.native_wf_results(job_id)
    return _get(f"/jobs/{job_id}/native-wf-results")


def start_backtest(job_spec: dict, runner: str = "ninjatrader") -> dict:
    """Submit a backtest job. Routes to the NT8 agent, the MT5 agent, or the in-process Python
    runner based on runner. Python needs no spec translation — it reads the NT8-shaped spec
    directly, which is why there is no `_nt8_to_python_spec`."""
    if runner == "ninjatrader":
        return _post("/backtest", job_spec, timeout=30)
    elif runner == "mt5":
        return mt5_agent_client.start_backtest(_nt8_to_mt5_spec(job_spec))
    elif runner == "python":
        return python_runner.start_backtest(job_spec)
    else:
        raise ValueError(f"Unknown runner: {runner!r}")


def _normalize_mt5_status(raw: dict) -> dict:
    """
    MT5 agent uses "done"/"cancelled"; polling loop expects "complete"/"failed_*".
    Sets updated_at to now so the heartbeat stall detector sees a live agent response.
    """
    status = raw.get("status", "running")
    if status == "done":
        status = "complete"
    elif status == "cancelled":
        status = "failed_cancelled"
    running = status not in ("complete", "failed_cancelled")
    pct = 100 if status == "complete" else max(5, min(99, raw.get("pct") or 5))
    message = (
        raw.get("message")
        or (raw.get("error") or "")
        or ("MT5 optimization running…" if running else "")
    )
    return {
        "status": status,
        "pct": pct,
        "message": message,
        "completed_count": raw.get("completed_count"),
        "total_count": raw.get("total_count"),
        "updated_at": str(time.time()),
        "error": raw.get("error"),
    }


def job_status(job_id: str, runner: Optional[str] = None) -> dict:
    resolved = _resolve_runner(job_id, runner)
    if resolved == "mt5":
        return _normalize_mt5_status(mt5_agent_client.job_status(job_id))
    if resolved == "python":
        return python_runner.job_status(job_id)  # already the NT8 status shape
    return _get(f"/jobs/{job_id}/status")


def _normalize_mt5_results(raw: dict) -> dict:
    """MT5 agent returns KPIs flat; translate to the NT8 nested {kpis, equity_curve, daily_pnl} shape."""
    _KPI_KEYS = {"net_pnl", "profit_factor", "win_rate", "max_drawdown", "sharpe", "trade_count"}
    trades = raw.get("trades", [])

    # Compute avg_win / avg_loss from the trades list (MT5 agent doesn't report these)
    profits = [t["profit"] for t in trades if "profit" in t]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    kpis = {k: raw[k] for k in _KPI_KEYS if k in raw}
    if wins:
        kpis["avg_win"] = round(sum(wins) / len(wins), 2)
    if losses:
        kpis["avg_loss"] = round(sum(losses) / len(losses), 2)

    # MT5 emits 2 deal-rows per trade: an entry deal (profit=0, direction=position direction)
    # and an exit deal (profit=realized P&L, direction=opposite of position direction).
    # Build ONE equity point per CLOSED trade by accumulating realized P&L, rather than
    # overlaying direction onto the agent's raw balance curve by timestamp. Timestamp-matching
    # was lossy: MT5 timestamps are minute-resolution, so two trades closing in the same minute
    # collapsed onto one point and the breakdown undercounted (long+short < trade_count).
    # Walk deals in time order, treating profit==0 as an entry (carries the position direction)
    # and profit!=0 as the exit that closes it. One directional point per exit ⇒ long+short
    # always equals trade_count. Pending entries are held in a FIFO queue so overlapping
    # positions (two opened before either closes) pair first-opened-first-closed instead of
    # the later entry clobbering the earlier; for one-at-a-time strategies the queue never
    # exceeds depth 1, so this matches simple alternating entry/exit exactly.
    _DIR = {"buy": "Long", "sell": "Short"}
    _OPP = {"buy": "sell", "sell": "buy"}
    raw_curve = raw.get("equity_curve", [])
    opening = raw_curve[0].get("equity", 0.0) if raw_curve else 0.0
    start_ts = raw_curve[0].get("date", "") if raw_curve else ""

    equity_curve: list[dict] = [{"index": 0, "date": start_ts, "equity": opening}]
    balance = opening
    pending_entries: list[dict] = []
    for t in sorted(trades, key=lambda x: x.get("time", "")):
        profit = t.get("profit") or 0.0
        if profit == 0.0:
            pending_entries.append(t)
            continue
        # Position direction comes from the entry deal; if no entry is pending, the exit deal's
        # direction is the opposite of the position direction, so invert it as a fallback.
        entry = pending_entries.pop(0) if pending_entries else None
        entry_dir = (entry or {}).get("direction", "").lower()
        if not entry_dir:
            entry_dir = _OPP.get(
                (t.get("direction") or "").lower(), (t.get("direction") or "").lower()
            )
        balance = round(balance + profit, 2)
        equity_curve.append(
            {
                "index": len(equity_curve),
                "date": t.get("time", ""),
                "equity": balance,
                "direction": _DIR.get(entry_dir, entry_dir.capitalize()),
                "profit": profit,
                # Per-trade size = MT5 volume (lots). Stored, but NOT a futures-contract count —
                # the contract-cap check treats MT5 as not_applicable.
                "size": t.get("volume"),
            }
        )

    out = {
        "kpis": kpis,
        "equity_curve": equity_curve,
        "daily_pnl": raw.get("daily_pnl", []),
        "trades": trades,
    }
    # Pass the per-trade record through when a reshaped EA emitted it (the runner→engine
    # contract). backtest_runner._handle_complete sizes the run offline only when this key
    # is present; a unit-size EA ships none, so the sized path stays dormant — same gate
    # as the NT8 side. Kept at the top level (not under kpis), exactly where NT8 puts it.
    engine_trades = raw.get("engine_trades")
    if engine_trades:
        out["engine_trades"] = engine_trades
    return out


def job_results(job_id: str, runner: Optional[str] = None) -> dict:
    resolved = _resolve_runner(job_id, runner)
    if resolved == "mt5":
        return _normalize_mt5_results(mt5_agent_client.job_results(job_id))
    if resolved == "python":
        # backtest.output already emits the lab's {equity_curve, daily_pnl, kpis, engine_trades}
        # shape, so there is deliberately no _normalize_python_results — nothing to translate.
        return python_runner.job_results(job_id)
    return _get(f"/jobs/{job_id}/results")


def job_log(job_id: str, lines: int = 200, runner: Optional[str] = None) -> str:
    resolved = _resolve_runner(job_id, runner)
    if resolved == "python":
        return python_runner.job_log(job_id, lines)
    if resolved == "mt5":
        return mt5_agent_client.job_log(job_id, lines)
    try:
        data = _get(f"/jobs/{job_id}/log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def cancel_job(job_id: str, runner: Optional[str] = None) -> dict:
    resolved = _resolve_runner(job_id, runner)
    if resolved == "mt5":
        return mt5_agent_client.cancel_job(job_id)
    if resolved == "python":
        return python_runner.cancel_job(job_id)
    return _post(f"/jobs/{job_id}/cancel")


def export_trades() -> dict:
    """Call /export-trades on the VPS agent. Returns {ok, csv, total_lines, log}.
    Longer timeout because the export automation takes ~12-15s."""
    return _get("/export-trades", timeout=60)


# ── Strategy file management ──────────────────────────────────────────────────


def list_strategy_files() -> list[dict]:
    return _get("/files/strategies")


def upload_strategy_file(filename: str, content: bytes, overwrite: bool) -> dict:
    if filename.endswith(".mq5"):
        return mt5_agent_client.upload_strategy_file(filename, content, overwrite)
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
    boundary = uuid.uuid4().hex
    body_parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
        content,
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\n'
        f"{'true' if overwrite else 'false'}\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(body_parts)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Upload {filename}: HTTP {exc.code} — {exc.read().decode()}") from exc
    except Exception as exc:
        raise RuntimeError(f"Upload {filename}: {exc}") from exc


def delete_strategy_file(filename: str) -> dict:
    if filename.endswith((".mq5", ".ex5")):
        return mt5_agent_client.delete_strategy_file(filename)
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Delete {filename}: HTTP {exc.code} — {exc.read().decode()}") from exc
    except Exception as exc:
        raise RuntimeError(f"Delete {filename}: {exc}") from exc


def trigger_compile() -> dict:
    return _post("/compile", timeout=10)


def get_compile_status(compile_job_id: str) -> dict:
    return _get(f"/compile/{compile_job_id}", timeout=10)
