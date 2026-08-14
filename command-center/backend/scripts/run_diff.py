#!/usr/bin/env python3
"""run_diff.py — why do these two runs disagree?

Read-only. Point it at two run ids and it answers ONE question before any other:
were these two runs measured on the same basis? Only then does it show what the
strategy config differed by, and only then the results.

    python3 command-center/backend/scripts/run_diff.py <run_a> <run_b>
    python3 command-center/backend/scripts/run_diff.py --list [N]

Exit 0 when the two share a measurement basis, 1 when they do not (so it can
gate a comparison), 2 on a usage error.

WHY THIS EXISTS
---------------
A run's numbers are a function of two different things: the PARAMS (the idea you
were testing) and the BASIS (the window, the costs, the broker, the sizing that
decide what those params were measured against). When two runs disagree, the
useful question is which of the two moved — and this app has shipped the same
defect three times by carrying the params forward and dropping the basis: the
Tuning workbench, the Stress Test children, and the stack rerun each launched a
child WITHOUT the parent's `cost_layers` / `broker_profile` / `sizing_mode`.
Measured at the time: profit factor 1.499 charged against 1.581 free, on
identical params and an identical 17 trades. The difference column became the
thing that lied.

So the basis is printed FIRST and a difference there is stated as a refusal,
not as a footnote under a table of deltas.

THREE THINGS THIS DELIBERATELY WILL NOT DO
------------------------------------------
1. It never treats a NULL `cost_layers` as `[]`. NULL means the row predates
   layered costs and keeps the old contract — charge whatever commission and
   slippage the row itself states — while `[]` means charge nothing. They are
   different runs and `services/python_runner.py::_cost_profile` branches on
   exactly that distinction.
2. It never reports a missing total R as 0.0. Per-trade `r` has only been
   written since 2026-08-03; a run without it has not been measured at zero, it
   has not been measured. Measured on this lab: 10 of 16 completed runs carry
   it on every trade and 6 carry it on none, so the answer is per-run and never
   a partial sum.
3. It never leads with a net-dollar delta. Two runs that differ in sizing (or
   that compounded from different balances) produce dollar figures that are not
   comparable even when every trade is identical — the shared-stack audit
   measured 99 identical trades at +17.8674R reading $21,064 solo and
   $47,758,999 in a stack. R is printed first for that reason and dollars are
   labelled when the basis moved.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "lab.db"

# The fields that decide WHAT A RUN IS MEASURED ON. A difference in any of
# these means the two results answer different questions, whatever the params
# say. Keep this list in step with `stress_tester.child_measurement_fields()`
# and `python_runner._cost_profile` — those decide what a child inherits, this
# decides what a reader is warned about, and they are the same set.
BASIS_FIELDS = [
    "strategy_id",
    "runner",
    "instrument",
    "bar_type",
    "bar_value",
    "start_date",
    "end_date",
    "cost_layers",
    "broker_profile",
    "commission_per_side",
    "slippage_ticks",
    "sizing_mode",
    "manual_risk_pct",
]

RESULT_FIELDS = [
    ("trade_count", "trades"),
    ("profit_factor", "profit factor"),
    ("win_rate", "win rate"),
    ("max_drawdown_pct", "max drawdown %"),
    ("net_pnl", "net P&L $"),
]


def fetch_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,))
    return cur.fetchone()


def render_cost_layers(raw) -> str:
    """NULL, [] and a populated list are THREE answers, never two.

    NULL is a row written before layered costs existed: it keeps the legacy
    contract and charges whatever commission and slippage the row states, which
    is not the same as charging nothing. Rendering both as "none" is the exact
    collapse `_cost_profile` refuses to make.
    """
    if raw is None:
        return "unrecorded (pre-layer run — charges the commission/slippage stated on the row)"
    try:
        layers = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return f"unparseable ({raw!r})"
    if not layers:
        return "[] (explicitly free)"
    return "+".join(str(x) for x in layers)


def render(field: str, value) -> str:
    if field == "cost_layers":
        return render_cost_layers(value)
    if value is None:
        return "unset"
    return str(value)


def total_r(path: str | None) -> tuple[float | None, str]:
    """Sum per-trade R, or say why it cannot be summed.

    Returns (value, note). A run whose points carry no `r` returns None — never
    0.0, which would read as a measured flat result.
    """
    if not path:
        return None, "no equity curve recorded"
    try:
        points = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        return None, f"equity curve unreadable ({exc.__class__.__name__})"
    trades = [p for p in points if isinstance(p, dict)]
    with_r = [p["r"] for p in trades if p.get("r") is not None]
    if not with_r:
        return None, "not recorded (run predates per-trade R)"
    if len(with_r) != len(trades):
        # A partial sum is a number that looks whole. Refuse rather than
        # silently summing the subset that happens to carry the field.
        return None, f"partial ({len(with_r)} of {len(trades)} trades carry R)"
    return sum(with_r), ""


def params_of(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["params"]) or {}
    except (TypeError, ValueError):
        return {}


def diff_basis(a: sqlite3.Row, b: sqlite3.Row) -> list[tuple[str, str, str]]:
    out = []
    for field in BASIS_FIELDS:
        va, vb = render(field, a[field]), render(field, b[field])
        if va != vb:
            out.append((field, va, vb))
    return out


def diff_params(a: sqlite3.Row, b: sqlite3.Row) -> list[tuple[str, str, str]]:
    pa, pb = params_of(a), params_of(b)
    out = []
    for key in sorted(set(pa) | set(pb)):
        va = pa.get(key, "<absent>")
        vb = pb.get(key, "<absent>")
        if va != vb:
            out.append((key, str(va), str(vb)))
    return out


def print_table(rows: list[tuple[str, str, str]], head: tuple[str, str, str]) -> None:
    all_rows = [head] + rows
    w0 = max(len(r[0]) for r in all_rows)
    w1 = max(len(r[1]) for r in all_rows)
    print(f"  {head[0]:<{w0}}  {head[1]:<{w1}}  {head[2]}")
    print(f"  {'-' * w0}  {'-' * w1}  {'-' * len(head[2])}")
    for name, va, vb in rows:
        print(f"  {name:<{w0}}  {va:<{w1}}  {vb}")


def cmd_list(conn: sqlite3.Connection, limit: int) -> int:
    cur = conn.execute(
        "SELECT run_id, strategy_id, instrument, start_date, end_date, trade_count, "
        "cost_layers, created_at FROM backtest_runs WHERE status = 'complete' "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    if not rows:
        print("No completed runs.")
        return 0
    for r in rows:
        layers = render_cost_layers(r["cost_layers"])
        print(
            f"{r['run_id']}  {r['strategy_id']:<24} {r['instrument']:<10} "
            f"{r['start_date']} -> {r['end_date']}  {r['trade_count'] or 0:>4} trades  {layers}"
        )
    return 0


def cmd_diff(conn: sqlite3.Connection, id_a: str, id_b: str) -> int:
    a, b = fetch_run(conn, id_a), fetch_run(conn, id_b)
    for rid, row in ((id_a, a), (id_b, b)):
        if row is None:
            print(f"No run {rid}. Use --list to see completed runs.", file=sys.stderr)
            return 2

    print(f"A = {id_a}   ({a['status']})")
    print(f"B = {id_b}   ({b['status']})")

    basis = diff_basis(a, b)
    print("\n=== MEASUREMENT BASIS ===")
    if not basis:
        print("  Same on all", len(BASIS_FIELDS), "fields. The two are comparable.")
    else:
        print(
            f"  {len(basis)} of {len(BASIS_FIELDS)} fields differ. "
            "These decide what each run was measured ON,"
        )
        print("  so the result delta below is NOT the difference between the two ideas —")
        print("  it is that difference plus whatever these changed.\n")
        print_table(basis, ("field", "A", "B"))

    params = diff_params(a, b)
    print("\n=== PARAMS ===")
    if not params:
        print("  Identical.")
    else:
        print_table(params, ("param", "A", "B"))

    print("\n=== RESULT ===")
    ra, note_a = total_r(a["equity_curve_path"])
    rb, note_b = total_r(b["equity_curve_path"])
    # R first: it is the one figure a change of position size cannot move.
    sa = f"{ra:+.4f}" if ra is not None else f"n/a — {note_a}"
    sb = f"{rb:+.4f}" if rb is not None else f"n/a — {note_b}"
    rows = [("total R", sa, sb)]
    for field, label in RESULT_FIELDS:
        rows.append((label, render(field, a[field]), render(field, b[field])))
    print_table(rows, ("metric", "A", "B"))

    if basis:
        moves_dollars = {
            "sizing_mode",
            "manual_risk_pct",
            "cost_layers",
            "broker_profile",
            "commission_per_side",
            "slippage_ticks",
        }
        changed = {f for f, _, _ in basis}
        if changed & moves_dollars:
            print(
                "\n  Net P&L is not comparable here — "
                + ", ".join(sorted(changed & moves_dollars))
                + " changed, and each of those moves the dollars without moving the idea."
            )
        print("\n  VERDICT: not a like-for-like comparison. Re-run B on A's basis first.")
        return 1

    print("\n  VERDICT: same basis, so the result difference is the params' doing.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="*", help="two run ids to compare")
    ap.add_argument(
        "--list",
        nargs="?",
        type=int,
        const=20,
        metavar="N",
        help="list the N most recent completed runs (default 20)",
    )
    ap.add_argument("--db", default=str(DB_PATH), help="lab.db path")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"No lab.db at {db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if args.list is not None:
            return cmd_list(conn, args.list)
        if len(args.runs) != 2:
            ap.print_usage(sys.stderr)
            print("\nGive two run ids, or --list to see them.", file=sys.stderr)
            return 2
        return cmd_diff(conn, args.runs[0], args.runs[1])
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
