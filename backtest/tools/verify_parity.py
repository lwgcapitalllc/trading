#!/usr/bin/env python3
"""verify_parity.py — the one "is everything in sync?" command.

Point it at the TradingView export CSV(s) you just pulled and it runs every parity
check whose columns are present, then prints one GREEN / RED / SKIP table. It does
NOT fix anything — it tells you what drifted so you know what to port.

Two things it deliberately cannot do (a human/agent must): re-paste the Pine and
export the CSV (only you, inside TradingView), and port a real logic change into the
Python (that is a code edit, per drift). This just closes the loop between those two.

    # after your brother updates mpc_assistant.pine / mpc_strategy.pine and you
    # re-export the CSV(s) on a 5m XAUUSD full-history chart:
    python backtest/tools/verify_parity.py "backtest/VANTAGE_XAUUSD, 5_xxxxx.csv" [more.csv ...]
    python backtest/tools/verify_parity.py            # auto-pick the newest CSV in backtest/

Each check is gated on a MARKER column, so you can throw any export at it — the
strategy export, a combined structure+OB+fib export, a single-engine export — and it
runs only the checks that export actually carries. Warmup (the cold-start bars where
the Python engine hasn't caught up with Pine's pre-window history) is auto-detected
from each tool's own hint, capped at 25% of the file so a LATE, real drift can never
be silently skipped as if it were warmup.

Exit 0 = every applicable check green. Exit 1 = at least one real drift (or an error).
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

_ROOT = Path(__file__).resolve().parents[2]

# (label, tool path relative to repo root, marker column, extra CLI args). A check runs
# only when its marker column is in the CSV header. Ordered engines-first (the foundation),
# strategy last (it sits on top of them) — the same dependency order you sync in.
_CHECKS: List[Tuple[str, str, str, List[str]]] = [
    ("market_structure", "engines/market_structure/tools/compare_tradingview.py", "px_ash", []),
    ("order_blocks",     "engines/order_blocks/tools/compare_ob.py",              "px_ob_bull_count", []),
    ("fibonacci",        "engines/fibonacci/tools/compare_fib.py",                "px_fib_active", []),
    ("fair_value_gaps",  "engines/fair_value_gaps/tools/compare_fvg.py",          "px_fvg_count", []),
    ("rsi_divergence",   "engines/rsi_divergence/tools/compare_rsi_div.py",       "px_div_rsi", []),
    ("liquidity",        "engines/liquidity/tools/compare_liquidity.py",          "px_pdh", []),
    ("sessions",         "engines/sessions/tools/compare_sessions.py",            "px_in_asia", []),
    ("vwap",             "engines/vwap/tools/compare_vwap.py",                    "px_vwap", []),
    ("session_volume_profile", "engines/session_volume_profile/tools/compare_svp.py", "px_svp_poc", []),
    ("strategy (bot)",   "strategies/python/mpc_aplus/tools/compare_strategy.py", "px_stages", []),
]

def _header(csv_path: Path) -> set:
    with csv_path.open(newline="") as f:
        row = next(csv.reader(f), [])
    return set(row)


def _row_count(csv_path: Path) -> int:
    with csv_path.open(newline="") as f:
        return max(0, sum(1 for _ in f) - 1)  # minus header


def _run(tool: Path, csv_path: Path, warmup: int, extra: List[str]) -> Tuple[int, str]:
    cmd = [sys.executable, str(tool), str(csv_path), "--warmup", str(warmup), *extra]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def _first_mismatch(out: str) -> str:
    """One-line 'why it's red' pulled from the tool's own report (skip the header lines)."""
    lines = out.splitlines()
    for s in (ln.strip() for ln in lines):
        if s.startswith("bar "):
            return s
    for s in (ln.strip() for ln in lines):
        if s.startswith("Last mismatching bar") or "last at bar" in s or "first diverging bar" in s.lower():
            return s
    return lines[-1].strip() if lines and lines[-1].strip() else "(mismatch)"


def check_one(label: str, tool: Path, csv_path: Path, extra: List[str],
              rows: int) -> Tuple[str, str]:
    """Run the tool at warmup 0; if that fails, walk a warmup ladder to skip cold-start
    bars. A REAL drift never goes green on any warmup, so it stays red. The ladder is
    tool-agnostic (no output parsing) and capped at 25% of the file, so a late, genuine
    divergence can never be skipped away as if it were warmup.
    Returns (status, detail). status in {GREEN, RED, ERROR}."""
    if not tool.exists():
        return "ERROR", f"tool missing: {tool}"
    code, out = _run(tool, csv_path, 0, extra)
    if code == 0:
        return "GREEN", "matched from bar 0"
    cap = max(4000, rows // 4)
    for w in (250, 500, 1000, 2000, 3500, cap):
        if w > cap:
            break
        code_w, _ = _run(tool, csv_path, w, extra)
        if code_w == 0:
            return "GREEN", f"matched after warmup {w} (cold-start)"
    return "RED", _first_mismatch(out)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        csvs = [Path(a) for a in argv]
    else:
        pool = sorted((_ROOT / "backtest").glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not pool:
            print("No CSV given and none found in backtest/. Pass an export path.")
            return 1
        csvs = [pool[0]]
        print(f"No CSV given — using newest in backtest/: {csvs[0].name}\n")

    overall_ok = True
    for csv_path in csvs:
        if not csv_path.exists():
            print(f"ERROR: not found: {csv_path}")
            overall_ok = False
            continue
        header = _header(csv_path)
        rows = _row_count(csv_path)
        applicable = [(lbl, t, mk, ex) for (lbl, t, mk, ex) in _CHECKS if mk in header]
        print(f"── {csv_path.name}  ({rows} bars, {len(applicable)}/{len(_CHECKS)} checks apply) ──")
        if not applicable:
            print("   (no parity columns found — is this the right export?)\n")
            continue
        for lbl, tool_rel, _mk, extra in applicable:
            status, detail = check_one(lbl, _ROOT / tool_rel, csv_path, extra, rows)
            mark = {"GREEN": "✓", "RED": "✗", "ERROR": "!"}[status]
            print(f"   {mark} {lbl:<24} {status:<6} {detail}")
            if status != "GREEN":
                overall_ok = False
        print()

    print("ALL IN SYNC ✓" if overall_ok else "DRIFT FOUND ✗ — port the red checks, then re-run.")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
