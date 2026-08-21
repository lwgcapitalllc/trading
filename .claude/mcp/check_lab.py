#!/usr/bin/env python3
"""Proves the lab server refuses a comparison that cannot be trusted.

Four properties:

  1. `_BASIS` still covers every input to a run. Read out of `BacktestRunRequest` in this
     repo — not out of a running app and not out of a copy — so ADDING an input to a run
     turns red here until somebody decides whether it changes what the run is measured on.
     🔴 This is the one that keeps the rest honest: a basis that silently falls behind lets
     two runs differ in a way the comparison cannot see, which is exactly rule 11's failure.
  2. A comparison REFUSES when any single basis field differs — checked one field at a time,
     so a rule covering eleven of twelve cannot pass.
  3. The override still WARNS, and the warning is the first key in the payload rather than
     appended where it scrolls past.
  4. Net dollars never lead, and the scratch count always travels with the win rate.

WATCHED RED by mutation, 2026-08-21:
  * dropping `broker_profile` from `_BASIS` reddens the contract check AND that field's
    refusal case, and nothing else;
  * making the override drop the WARNING key reddens exactly the two override cases;
  * moving `net_pnl` above the unit-free metrics reddens exactly the ordering case.

Run: python3 .claude/mcp/check_lab.py
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lab_server as lab  # noqa: E402 - path first, repo-wide convention

REPO = Path(__file__).resolve().parents[2]
MODELS = REPO / "command-center" / "backend" / "models.py"

failures = []


def check(label, cond, detail=""):
    if not cond:
        failures.append(f"{label}{(' - ' + detail) if detail else ''}")


# ── 1. the basis still covers the whole request contract ─────────────────────
tree = ast.parse(MODELS.read_text(encoding="utf-8"))
model = next(
    (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "BacktestRunRequest"),
    None,
)
check("BacktestRunRequest was found in models.py", model is not None)
if model:
    fields = {
        n.target.id
        for n in model.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    known = set(lab._BASIS) | set(lab._NOT_BASIS)
    check(
        "every run input is classified as basis or explicitly not",
        fields <= known,
        f"unclassified: {sorted(fields - known)} - decide whether each changes what a run is "
        "measured on, then add it to _BASIS or _NOT_BASIS with a reason",
    )
    check(
        "the basis names no field a run does not have",
        set(lab._BASIS) <= fields,
        f"stale: {sorted(set(lab._BASIS) - fields)}",
    )
    check(
        "basis and not-basis do not overlap",
        not (set(lab._BASIS) & set(lab._NOT_BASIS)),
    )

# ── 2. one differing basis field is enough to refuse ─────────────────────────
BASE_RUN = {
    "run_id": "aaa",
    "strategy_id": "mpc_sos_fade",
    "instrument": "XAUUSD",
    "bar_type": "Minute",
    "bar_value": 15,
    "start_date": "2020-01-01",
    "end_date": "2026-08-20",
    "commission_per_side": 0.0,
    "slippage_ticks": 0,
    "cost_layers": [],
    "broker_profile": "vantage_demo",
    "sizing_mode": "consistent",
    "manual_risk_pct": None,
    "params": {"exec_risk_pct": 10},
    "trade_count": 213,
    "win_rate": 0.64,
    "scratch_count": 45,
    "net_pnl": 51_059_825.66,
    "max_drawdown_pct": 37.78,
}
DIFFERENT = {
    "strategy_id": "mpc_bleg",
    "instrument": "EURUSD",
    "bar_type": "Hour",
    "bar_value": 5,
    "start_date": "2021-01-01",
    "end_date": "2025-01-01",
    "commission_per_side": 2.25,
    "slippage_ticks": 1,
    "cost_layers": ["spread"],
    "broker_profile": "pu_ecn",
    "sizing_mode": "manual",
    "manual_risk_pct": 2.0,
}
check(
    "every basis field is exercised by this test",
    set(DIFFERENT) == set(lab._BASIS),
    f"missing {sorted(set(lab._BASIS) - set(DIFFERENT))}",
)


def with_api(runs):
    """Stand in for the lab: return run records by id."""

    def fake(path, method="GET", timeout=None, body=None):
        rid = path.rsplit("/", 1)[-1]
        return runs.get(rid), None

    return fake


for field, other_value in DIFFERENT.items():
    a = dict(BASE_RUN, run_id="aaa")
    b = dict(BASE_RUN, run_id="bbb", **{field: other_value})
    real, lab._api = lab._api, with_api({"aaa": a, "bbb": b})
    try:
        out = lab.call_tool("compare_runs", {"run_a": "aaa", "run_b": "bbb"})
        ovr = lab.call_tool(
            "compare_runs", {"run_a": "aaa", "run_b": "bbb", "i_know_the_basis_differs": True}
        )
    finally:
        lab._api = real
    check(f"a differing {field} is refused", out.get("refused") is True, str(out)[:120])
    check(f"the refusal names {field}", field in (out.get("basis_differs") or {}))
    check(f"the override on {field} still warns", "WARNING" in ovr, str(ovr)[:100])
    check(
        f"the warning about {field} is the FIRST key, not appended",
        next(iter(ovr)) == "WARNING",
        f"first key was {next(iter(ovr))}",
    )

# ── 3. an identical basis compares, and reports the params that moved ────────
a = dict(BASE_RUN, run_id="aaa")
b = dict(BASE_RUN, run_id="bbb", params={"exec_risk_pct": 12.5}, trade_count=164)
real, lab._api = lab._api, with_api({"aaa": a, "bbb": b})
try:
    out = lab.call_tool("compare_runs", {"run_a": "aaa", "run_b": "bbb"})
finally:
    lab._api = real
check("a matching basis is not refused", out.get("refused") is False, str(out)[:140])
check("no warning on a clean comparison", "WARNING" not in out)
check(
    "the param that moved is named",
    (out.get("params_that_differ") or {}).get("exec_risk_pct") is not None,
    str(out.get("params_that_differ"))[:120],
)
check(
    "the change in a metric is computed",
    out["results"]["trade_count"].get("change") == -49,
    str(out["results"]["trade_count"]),
)

# ── 4. net dollars never lead, and scratches travel with the win rate ────────
keys = list(lab._HEADLINE)
check("net_pnl is not one of the unit-free headline metrics", "net_pnl" not in keys)
check(
    "the win rate is followed by the scratch count",
    keys.index("scratch_count") == keys.index("win_rate") + 1,
    f"order was {keys}",
)
h = lab._headline_of(BASE_RUN)
check("net_pnl is reported last", list(h)[-2] == "net_pnl", f"order was {list(h)}")
check(
    "the breakeven-scratch caveat travels with every result",
    any("scratch" in n for n in h["_reading_notes"]),
)
check(
    "a frictionless run says so",
    any("CHARGED NOTHING" in n for n in h["_reading_notes"]),
)
costed = lab._headline_of(dict(BASE_RUN, commission_per_side=2.25))
check(
    "a costed run does not claim to be frictionless",
    not any("CHARGED NOTHING" in n for n in costed["_reading_notes"]),
)


# ── 5. unreachable lab: cannot-ask, no invented answer ───────────────────────
def dead(path, method="GET", timeout=None, body=None):
    return None, lab._cannot_ask("the lab is not answering (test)")


for name, args in [
    ("list_runs", {}),
    ("get_run", {"run_id": "aaa"}),
    ("compare_runs", {"run_a": "aaa", "run_b": "bbb"}),
    ("copy_run_basis", {"run_id": "aaa"}),
]:
    real, lab._api = lab._api, dead
    try:
        out = lab.call_tool(name, args)
    finally:
        lab._api = real
    check(f"{name} reports cannot-ask", out.get("asked") is False, str(out)[:120])
    check(f"{name} invents nothing", not (set(out) & {"results", "runs", "refused"}))

if failures:
    print(f"\n{len(failures)} lab check(s) FAILED:\n")
    for f in failures:
        print("  FAIL  " + f)
    sys.exit(1)
print("lab OK - basis contract, per-field refusals, warning placement and reading order checked")
