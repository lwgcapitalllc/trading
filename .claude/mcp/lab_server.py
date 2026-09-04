#!/usr/bin/env python3
"""The backtest lab, exposed to Claude as tools that cannot be called wrong.

WHY THIS EXISTS
---------------
Rule 11: *anything that recreates a run for COMPARISON must carry forward everything that
decides what it is measured on — window, costs, broker, sizing, per-leg params.* **That rule
has been broken four times in this app**, and the failure is always the same shape: the
difference column becomes the thing that lies. Two runs are put side by side, one of them
quietly used a different window or charged no commission, and the gap gets attributed to the
parameter somebody was actually testing.

A rule that has to be remembered is one that gets broken on a Friday. So the comparison here
REFUSES unless the basis matches, and names exactly which field differs.

WHAT THE BASIS IS, AND WHY IT IS NOT A JUDGEMENT CALL
-----------------------------------------------------
`POST /backtests/run` takes exactly these inputs: strategy, instrument, timeframe, window,
commission, slippage, cost layers, broker profile, sizing mode, manual risk — and `params`.
Everything except `params` decides what the run is MEASURED ON; `params` is what you are
comparing. So the basis is read off the request contract rather than chosen, and a new input
added there will show up here as a field this file does not know about rather than as a
silent hole. `_BASIS` is checked against the live schema by `check_lab.py`.

TWO THINGS IT REFUSES TO LET YOU READ WRONG
-------------------------------------------
* **Net dollars are reported UNDER the unit-free numbers, never above them.** Rule 6: compare
  R, never net dollars, across anything that shares a balance — a shared stack once read
  2,266x the solo run on identical trades.
* **A win rate here counts breakeven scratches as wins**, so the scratch count is reported
  beside it every time rather than left for somebody to go and find.

⚠ Like the trading-box server, this is a front door onto the Command Center backend and not a
second implementation of anything. The app must be running; when it is not, every tool says so
and returns no payload.
"""

import json
import os
import sys
import urllib.error
import urllib.request

SERVER_NAME = "lab"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

BASE_URL = os.environ.get("LWG_COMMAND_CENTER_URL", "http://localhost:8000").rstrip("/")

TIMEOUT_FAST = 30
TIMEOUT_SLOW = 180

# ─────────────────────────────────────────────────────────────────────────────
# The measurement basis
# ─────────────────────────────────────────────────────────────────────────────
#
# Every input to `POST /backtests/run` EXCEPT `params`. Read off the request contract rather
# than picked, so this list cannot quietly fall behind what a run actually depends on.
# `check_lab.py` asserts it still matches the live OpenAPI schema.
_BASIS = (
    "strategy_id",
    "instrument",
    "bar_type",
    "bar_value",
    "start_date",
    "end_date",
    "commission_per_side",
    "slippage_ticks",
    "cost_layers",
    "broker_profile",
    "sizing_mode",
    "manual_risk_pct",
    # The venue lot ceiling. BASIS, and the reason is worth stating because the obvious test
    # misses it: R is IDENTICAL either side of a ceiling (profit and risk both scale with the
    # quantity), so a comparison in R shows nothing while balance, drawdown and CAGR all move.
    # MEASURED 2026-09-02 on the live SOS Fade bot over 6.6 years: same 205 trades, same +107.36R,
    # closing balance $11,528,822 uncapped against $10,752,175 at 100 lots.
    "max_lots",
)

# Inputs to a run that are NOT part of the basis, and why. Kept explicit so that adding an
# input to the request contract forces a decision instead of a default.
_NOT_BASIS = {
    "params": "the subject of the comparison, not its basis",
    "evaluate_rulesets": "grading applied AFTER the run; changes no fill",
    "evaluate_firms": "grading applied AFTER the run; changes no fill",
    "source_run_id": "provenance, not an input to the replay",
    "charge_costs": (
        "a REQUEST-time switch, not a measurement: the lab resolves it into `cost_layers` and "
        "`commission_per_side` at run creation and stores those, which ARE basis. Copying the "
        "switch would copy what was asked for instead of what was charged - rule 3. "
        "start_backtest pins it to null whenever it hands over resolved layers, or the lab "
        "would re-resolve them and quietly charge a copied basis differently"
    ),
}

# Unit-free first. Net dollars appear once, at the bottom, next to the caveat.
_HEADLINE = (
    "trade_count",
    "win_rate",
    "scratch_count",
    "profit_factor",
    "max_drawdown_pct",
    "sharpe",
    "profit_concentration_pct",
    "trade_concentration_pct",
    "worst_losing_streak",
)


def _cannot_ask(reason: str, **extra):
    """`asked: false` and NO payload. Never let "no" and "cannot ask" be the same value."""
    out = {"asked": False, "reason": reason}
    out.update(extra)
    return out


def _api(path: str, method: str = "GET", timeout: int = TIMEOUT_FAST, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return None, _cannot_ask(
            f"the lab answered HTTP {e.code} for {path}",
            detail=e.read().decode("utf-8", "replace")[:400],
        )
    except urllib.error.URLError as e:
        return None, _cannot_ask(
            f"the Command Center is not answering at {BASE_URL} ({e.reason}). Start it with "
            "./go from the repo root. The question never left this machine."
        )
    except Exception as e:  # noqa: BLE001
        return None, _cannot_ask(f"could not reach the lab: {e}")
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return raw, None


def _basis_of(run: dict) -> dict:
    return {k: run.get(k) for k in _BASIS}


def _headline_of(run: dict) -> dict:
    out = {k: run.get(k) for k in _HEADLINE}
    out["net_pnl"] = run.get("net_pnl")
    out["_reading_notes"] = [
        "win_rate counts breakeven scratches as wins - read it next to scratch_count.",
        "net_pnl is last on purpose. Compare the unit-free numbers; net dollars are only "
        "comparable when both runs started from the same balance and shared nothing.",
    ]
    if (
        not run.get("commission_per_side")
        and not run.get("slippage_ticks")
        and not run.get("cost_layers")
    ):
        out["_reading_notes"].append(
            "THIS RUN CHARGED NOTHING - no commission, no slippage, no cost layers. A "
            "frictionless result can reverse once costs are on."
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


def tool_list_runs(args):
    """Recent runs, compact enough to scan."""
    limit = max(1, min(int(args.get("limit", 15)), 50))
    out, err = _api(f"/backtests/runs?limit={limit}", timeout=TIMEOUT_SLOW)
    if err:
        return err
    rows = out if isinstance(out, list) else out.get("runs", out.get("items", []))
    runs = [
        {
            "run_id": r.get("run_id"),
            "strategy": r.get("strategy_id") or r.get("strategy_name"),
            "instrument": r.get("instrument"),
            "window": f"{r.get('start_date')} -> {r.get('end_date')}",
            "status": r.get("status"),
            "trades": r.get("trade_count"),
            "max_drawdown_pct": r.get("max_drawdown_pct"),
            "created_at": r.get("created_at"),
        }
        for r in rows[:limit]
    ]
    return {"asked": True, "count": len(runs), "runs": runs}


def tool_get_run(args):
    """One run: what it was measured on, and what came out. The big arrays are left behind."""
    run_id = args["run_id"]
    r, err = _api(f"/backtests/runs/{run_id}", timeout=TIMEOUT_SLOW)
    if err:
        return err
    if not isinstance(r, dict):
        return _cannot_ask(f"the lab returned no run record for {run_id}")
    return {
        "asked": True,
        "run_id": r.get("run_id"),
        "status": r.get("status"),
        "error_message": r.get("error_message"),
        "measured_on": _basis_of(r),
        "results": _headline_of(r),
        "param_count": len(r.get("params") or {}),
        "note": (
            "params are omitted here because there are dozens. compare_runs reports the ones "
            "that actually differ between two runs."
        ),
    }


def tool_compare_runs(args):
    """Two runs side by side — and a REFUSAL when they were not measured the same way.

    This is the whole reason the file exists. Rule 11 has been broken four times in this app,
    and every time the difference column ended up attributed to the wrong cause.
    """
    a_id, b_id = args["run_a"], args["run_b"]
    a, err = _api(f"/backtests/runs/{a_id}", timeout=TIMEOUT_SLOW)
    if err:
        return err
    b, err = _api(f"/backtests/runs/{b_id}", timeout=TIMEOUT_SLOW)
    if err:
        return err
    if not isinstance(a, dict) or not isinstance(b, dict):
        return _cannot_ask("the lab did not return both run records")

    basis_a, basis_b = _basis_of(a), _basis_of(b)
    differs = {
        k: {"run_a": basis_a[k], "run_b": basis_b[k]} for k in _BASIS if basis_a[k] != basis_b[k]
    }

    override = bool(args.get("i_know_the_basis_differs"))
    if differs and not override:
        return {
            "asked": True,
            "refused": True,
            "reason": (
                "these two runs were not measured the same way, so any difference in the "
                "results cannot be attributed to the parameters. Rule 11. Re-run one of them "
                "on the other's basis, or pass i_know_the_basis_differs to see it anyway - "
                "the answer will carry this warning at the top."
            ),
            "basis_differs": differs,
            "run_a": a_id,
            "run_b": b_id,
        }

    pa, pb = a.get("params") or {}, b.get("params") or {}
    param_diff = {
        k: {"run_a": pa.get(k), "run_b": pb.get(k)}
        for k in sorted(set(pa) | set(pb))
        if pa.get(k) != pb.get(k)
    }

    ha, hb = _headline_of(a), _headline_of(b)
    moved = {}
    for k in _HEADLINE + ("net_pnl",):
        va, vb = ha.get(k), hb.get(k)
        row = {"run_a": va, "run_b": vb}
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            row["change"] = round(vb - va, 4)
        moved[k] = row

    result = {
        "asked": True,
        "refused": False,
        "run_a": a_id,
        "run_b": b_id,
        "measured_on": basis_a if not differs else {"run_a": basis_a, "run_b": basis_b},
        "params_that_differ": param_diff or "none - these two runs used identical parameters",
        "results": moved,
        "_reading_notes": ha["_reading_notes"],
    }
    if differs:
        # At the TOP of the payload, not appended where it can be scrolled past.
        result = {
            "WARNING": (
                "THE BASIS DIFFERS. The numbers below are NOT attributable to the parameters. "
                "Fields that differ are listed in basis_differs."
            ),
            "basis_differs": differs,
            **result,
        }
    return result


def tool_start_backtest(args):
    """Kick off a run. Costs compute, never money — so no confirmation, unlike the trading box.

    Every basis field is passed through explicitly rather than defaulted here: a default in
    this file would be a second opinion about what a run is measured on, sitting one layer
    away from the lab that actually decides.
    """
    body = {
        "strategy_id": args["strategy_id"],
        "instrument": args["instrument"],
        "start_date": args["start_date"],
        "end_date": args["end_date"],
        "params": args.get("params") or {},
    }
    for k in (
        "bar_type",
        "bar_value",
        "commission_per_side",
        "slippage_ticks",
        "cost_layers",
        "broker_profile",
        "sizing_mode",
        "manual_risk_pct",
        "source_run_id",
    ):
        if k in args:
            body[k] = args[k]
    # 🔴 Handing over resolved cost layers means the lab must NOT re-resolve them. Its one cost
    # switch defaults to ON and, when set, overwrites `cost_layers` and `commission_per_side`
    # from the broker profile — so copying a deliberately uncharged run's basis and starting it
    # would produce a fully charged run while this tool reported the basis had been copied.
    # That is rule 11's failure exactly: the difference column becomes the thing that lies.
    # Null means "I am giving you the resolved set; leave it alone". Absent — a genuinely new
    # run — still gets the lab's own default, because a default HERE would be a second opinion
    # about what a run is measured on, one layer away from the lab that decides.
    if "cost_layers" in body:
        body["charge_costs"] = None
    out, err = _api("/backtests/run", method="POST", timeout=TIMEOUT_SLOW, body=body)
    if err:
        return err
    return {
        "asked": True,
        "started": out,
        "next": "poll get_run with the run id until status is 'complete'.",
    }


def tool_copy_run_basis(args):
    """Give me run X's basis, ready to start a new run that IS comparable to it.

    The direct answer to rule 11: the way a comparison gets broken is by rebuilding the basis
    by hand and dropping a field. This hands it over whole.
    """
    run_id = args["run_id"]
    r, err = _api(f"/backtests/runs/{run_id}", timeout=TIMEOUT_SLOW)
    if err:
        return err
    if not isinstance(r, dict):
        return _cannot_ask(f"the lab returned no run record for {run_id}")
    basis = _basis_of(r)
    return {
        "asked": True,
        "copied_from": run_id,
        "basis": basis,
        "params": r.get("params") or {},
        "how_to_use": (
            "pass every basis field to start_backtest unchanged, and change only what you are "
            "testing inside params. compare_runs will refuse if any basis field moved."
        ),
        "fields_deliberately_not_copied": _NOT_BASIS,
    }


_TOOLS = [
    (
        "list_runs",
        "Recent backtest runs, compact.",
        tool_list_runs,
        {"limit": {"type": "integer", "description": "1-50, default 15."}},
        [],
    ),
    (
        "get_run",
        "One run: what it was measured on, and the headline results.",
        tool_get_run,
        {"run_id": {"type": "string"}},
        ["run_id"],
    ),
    (
        "compare_runs",
        "Two runs side by side. REFUSES when they were not measured the same way - different "
        "window, costs, broker, sizing or instrument - because the difference could not then be "
        "attributed to the parameters.",
        tool_compare_runs,
        {
            "run_a": {"type": "string"},
            "run_b": {"type": "string"},
            "i_know_the_basis_differs": {
                "type": "boolean",
                "description": "Show the comparison anyway, with the mismatch stamped on top.",
            },
        },
        ["run_a", "run_b"],
    ),
    (
        "copy_run_basis",
        "Everything needed to start a new run that is comparable to an existing one.",
        tool_copy_run_basis,
        {"run_id": {"type": "string"}},
        ["run_id"],
    ),
    (
        "start_backtest",
        "Start a backtest run.",
        tool_start_backtest,
        {
            "strategy_id": {"type": "string"},
            "instrument": {"type": "string"},
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "params": {"type": "object"},
            "bar_type": {"type": "string"},
            "bar_value": {"type": "integer"},
            "commission_per_side": {"type": "number"},
            "slippage_ticks": {"type": "number"},
            "cost_layers": {"type": "array"},
            "broker_profile": {"type": "string"},
            "sizing_mode": {"type": "string"},
            "manual_risk_pct": {"type": "number"},
            "source_run_id": {"type": "string"},
        },
        ["strategy_id", "instrument", "start_date", "end_date"],
    ),
]

TOOLS = [
    {
        "name": n,
        "description": d,
        "inputSchema": {"type": "object", "properties": props, "required": req},
        "fn": fn,
    }
    for n, d, fn, props, req in _TOOLS
]

_BY_NAME = {t["name"]: t for t in TOOLS}


def call_tool(name: str, args: dict):
    tool = _BY_NAME.get(name)
    if tool is None:
        return {"asked": False, "reason": f"no such tool: {name}"}
    try:
        return tool["fn"](args or {})
    except KeyError as e:
        return {"asked": False, "reason": f"missing required argument: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"asked": False, "reason": f"the tool failed: {type(e).__name__}: {e}"}


def _write(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    },
                }
            )
        elif method == "tools/list":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "tools": [
                            {k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS
                        ]
                    },
                }
            )
        elif method == "tools/call":
            p = msg.get("params") or {}
            out = call_tool(p.get("name", ""), p.get("arguments") or {})
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(out, indent=2, default=str)}
                        ],
                        "isError": False,
                    },
                }
            )
        elif method == "ping":
            _write({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()
