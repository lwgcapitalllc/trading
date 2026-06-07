"""
Parse lucid_flex_results.csv and print a formatted pass/fail evaluation table.

Usage:
    python analyze.py [--results path/to/lucid_flex_results.csv]
    python analyze.py --results lucid_flex_results.csv
"""

import csv
import sys
import os
import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CSV = SCRIPT_DIR / "lucid_flex_results.csv"
DEFAULT_CFG = SCRIPT_DIR / "backtest_config.json"

# ANSI colours
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def load_thresholds(cfg_path):
    try:
        with open(cfg_path) as f:
            return json.load(f).get("thresholds", {})
    except Exception:
        return {}


def verdict(row, thresh):
    """
    Returns (label, colour) based on thresholds.
    KEEP / WARN / DISCARD
    """
    net    = float(row["net_pnl"])
    dd     = float(row["max_drawdown"])
    pf     = float(row["profit_factor"])
    trades = int(row["trades"])

    min_pf    = thresh.get("min_profit_factor", 1.5)
    min_tr    = thresh.get("min_trades", 150)
    max_dd    = thresh.get("max_drawdown", 1500)
    warn_pf   = thresh.get("warn_profit_factor", 1.2)
    warn_tr   = thresh.get("warn_trades", 50)

    discard_reasons = []
    if net <= 0:                  discard_reasons.append("net loss")
    if pf < warn_pf:              discard_reasons.append(f"PF<{warn_pf}")
    if trades < warn_tr:          discard_reasons.append(f"trades<{warn_tr}")
    if dd > max_dd * 1.5:         discard_reasons.append(f"DD>${max_dd*1.5:.0f}")

    warn_reasons = []
    if pf < min_pf:               warn_reasons.append(f"PF<{min_pf}")
    if trades < min_tr:           warn_reasons.append(f"trades<{min_tr}")
    if dd > max_dd:               warn_reasons.append(f"DD>${max_dd:.0f}")

    if discard_reasons:
        return f"DISCARD  ({', '.join(discard_reasons)})", RED
    elif warn_reasons:
        return f"WARN     ({', '.join(warn_reasons)})", YELLOW
    else:
        return "KEEP", GREEN


def fmt(val, fmt_str, prefix=""):
    try:
        return f"{prefix}{float(val):{fmt_str}}"
    except Exception:
        return str(val)


def print_table(rows, thresh):
    COL_W = [20, 14, 10, 10, 8, 8, 8, 30]
    headers = ["Strategy", "Instrument", "Net P&L", "Max DD", "PF", "Win%", "Trades", "Verdict"]

    sep = "+" + "+".join("-" * w for w in COL_W) + "+"
    header_row = "|" + "|".join(
        f" {h:<{COL_W[i]-1}}" for i, h in enumerate(headers)
    ) + "|"

    print()
    print(f"{BOLD}LucidFlex Backtest Results{RESET}")
    print(sep)
    print(f"{BOLD}{header_row}{RESET}")
    print(sep)

    for row in rows:
        vstr, colour = verdict(row, thresh)
        cells = [
            row.get("strategy", ""),
            row.get("instrument", ""),
            fmt(row.get("net_pnl", 0), ".0f", "$"),
            fmt(row.get("max_drawdown", 0), ".0f", "$"),
            fmt(row.get("profit_factor", 0), ".3f"),
            fmt(row.get("win_pct", 0), ".1f") + "%",
            row.get("trades", "0"),
            vstr,
        ]
        line = "|" + "|".join(
            f" {str(c):<{COL_W[i]-1}}" for i, c in enumerate(cells)
        ) + "|"
        print(f"{colour}{line}{RESET}")

    print(sep)
    print()
    print(f"  {GREEN}KEEP{RESET}    — PF>{thresh.get('min_profit_factor',1.5)}, net positive, DD<${thresh.get('max_drawdown',1500)}, trades>{thresh.get('min_trades',150)}")
    print(f"  {YELLOW}WARN{RESET}    — marginal on one or more metrics; needs closer look")
    print(f"  {RED}DISCARD{RESET} — net loss, very low PF, or far too few trades")
    print()


def consistency_check(rows):
    """Rough consistency check: flag if any single combo dominates profit."""
    nets = [(r.get("strategy","") + " " + r.get("instrument",""), float(r.get("net_pnl",0)))
            for r in rows if float(r.get("net_pnl",0)) > 0]
    if not nets:
        return
    total = sum(n for _, n in nets)
    if total <= 0:
        return
    print(f"{BOLD}LucidFlex 50% Consistency Check{RESET}")
    for name, n in sorted(nets, key=lambda x: -x[1]):
        pct = n / total * 100
        flag = f" {YELLOW}<-- >50% of total profit, watch consistency rule{RESET}" if pct > 50 else ""
        print(f"  {name:<35} ${n:>8.0f}  ({pct:.1f}%){flag}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(DEFAULT_CSV))
    parser.add_argument("--config",  default=str(DEFAULT_CFG))
    args = parser.parse_args()

    if not os.path.exists(args.results):
        print(f"Results file not found: {args.results}")
        print("Run backtests first, then SCP the results file here.")
        sys.exit(1)

    thresh = load_thresholds(args.config)

    rows = []
    with open(args.results, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("Results file is empty.")
        sys.exit(1)

    print_table(rows, thresh)
    consistency_check(rows)


if __name__ == "__main__":
    main()
