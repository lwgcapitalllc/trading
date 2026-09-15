#!/usr/bin/env python3
"""killzone_edge_search.py — which engine, if any, knows which way the 10:00 zone will go?

Reads the per-day table `killzone_features.py` writes and tests every engine's state as a
DIRECTION signal for a scalp: in at the snapshot bar's open, out at a fixed NY time.

🔴 **The protocol is fixed BEFORE the numbers are read, because a search this wide finds
something by construction.**
  1. DISCOVERY is 2018-2023 only. Every signal x variant x exit is ranked there.
  2. A cell is a CANDIDATE only if its discovery t-statistic clears `--t-min` (default 2.5 —
     well above the ~2.0 that one cell in twenty clears by chance).
  3. Candidates are then scored ONCE on 2024-2026, which nothing in step 1 has seen. Only a
     candidate that keeps its sign and stays significant there is reported as FOUND.
  4. Costs are charged on every trade: the ECN account's measured $0.12 spread plus $1/side/lot
     commission = **$0.14 per ounce round trip** (`backtest/fills.py` → `puprime_ecn`).
The cell count is printed, so any single number can be discounted as one of many.

⚠ **P&L is scored in ADR units, reported in dollars.** Gold went from ~$1,200 to ~$4,400 over
the sample, so a dollar figure weights the recent years ~3.5x; ADR-normalising makes 2019 and
2025 count the same. The dollar column is what a trade is worth at TODAY's price level.

Usage:
    python3 backtest/tools/killzone_edge_search.py
    python3 backtest/tools/killzone_edge_search.py --features backtest/reports/kz_features/f1145.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import math
import statistics
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_END = dt.date(2023, 12, 31)
COST_USD = 0.14
EXITS = ("c_1015", "c_1030", "c_1100", "c_1215", "c_1300", "c_1600")


def _f(x):
    if x in (None, "", "None"):
        return None
    if x in ("True", "False"):
        return x == "True"
    try:
        return float(x)
    except ValueError:
        return x


def load(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return [{k: _f(v) for k, v in r.items()} for r in csv.DictReader(fh)]


def _sg(x):
    return 0 if x is None else (1 if x > 0 else (-1 if x < 0 else 0))


def signals(r: dict) -> dict[str, int]:
    """Every engine's state mapped to +1 long / -1 short / 0 no view. Each signal is also
    tested INVERTED by the caller, so "follow" and "fade" are both on the table and neither
    is favoured by how the mapping happens to be written."""
    p, adr = r["p_prev"], r["adr"]
    s = {
        "structure M5 trend": _sg(r["ms_m5"]),
        "structure M15 trend": _sg(r["ms_m15"]),
        "structure H1 trend": _sg(r["ms_h1"]),
        "price vs session VWAP": _sg(p - r["vwap"]) if r["vwap"] else 0,
        "price vs Asia POC": _sg(p - r["poc"]) if r["poc"] else 0,
        "morning move 03:00->open": _sg(r["o_at"] - r["m_open"]),
        "2h move 08:00->open": _sg(r["o_at"] - r["o08"]),
        "yesterday's direction": _sg(r["pd_close"] - r["pd_open"]) if r["pd_open"] else 0,
        "vs yesterday's range": (1 if p > r["pdh"] else (-1 if p < r["pdl"] else 0))
        if r["pdh"]
        else 0,
        "standing in a gap (FVG)": 1
        if r["in_bull_fvg"] and not r["in_bear_fvg"]
        else (-1 if r["in_bear_fvg"] and not r["in_bull_fvg"] else 0),
        "gap count bull vs bear": _sg((r["fvg_n_bull"] or 0) - (r["fvg_n_bear"] or 0)),
        "standing in an order block": 1
        if r["in_bull_ob"] and not r["in_bear_ob"]
        else (-1 if r["in_bear_ob"] and not r["in_bull_ob"] else 0),
        "order block count bull vs bear": _sg((r["ob_n_bull"] or 0) - (r["ob_n_bear"] or 0)),
        "morning swept a low / a high": 1
        if r["am_swept_low"] and not r["am_swept_high"]
        else (-1 if r["am_swept_high"] and not r["am_swept_low"] else 0),
        "RSI above/below 50": _sg((r["rsi"] or 50) - 50) if r["rsi"] is not None else 0,
        "RSI stretched (>70 / <30)": (1 if r["rsi"] > 70 else (-1 if r["rsi"] < 30 else 0))
        if r["rsi"] is not None
        else 0,
        "RSI divergence": 1
        if r["rsi_bull_div"] and not r["rsi_bear_div"]
        else (-1 if r["rsi_bear_div"] and not r["rsi_bull_div"] else 0),
        "last candle pattern": 1
        if r["cs_bull"] and not r["cs_bear"]
        else (-1 if r["cs_bear"] and not r["cs_bull"] else 0),
    }
    # Nearer liquidity pulls: closer to the level above -> expect up.
    if r["liq_above"] and r["liq_below"]:
        s["nearer liquidity side"] = 1 if (r["liq_above"] - p) < (p - r["liq_below"]) else -1
    else:
        s["nearer liquidity side"] = 0
    if r["eqh_above"] and r["eql_below"]:
        s["nearer equal highs/lows"] = 1 if (r["eqh_above"] - p) < (p - r["eql_below"]) else -1
    else:
        s["nearer equal highs/lows"] = 0
    # 🔴 THE CONTROL. A coin flip seeded by the date: it knows nothing, so wherever it lands in
    # the ranking is this search's noise floor. A real signal has to beat it clearly — and if
    # the coin ever reads as FOUND, the protocol is broken, not the market.
    # ⚠ Not `hash()`: Python salts string hashes per process, so the coin would land
    # differently on every run and a control that moves is not a control.
    s["CONTROL: coin flip"] = 1 if hashlib.md5(r["date"].encode()).digest()[0] & 1 else -1
    return s


def _t(v):
    if len(v) < 30:
        return float("nan")
    sd = statistics.stdev(v)
    return statistics.fmean(v) / (sd / math.sqrt(len(v))) if sd > 0 else float("nan")


def score(rows, pick, exit_col):
    """pick(row) -> direction. Returns {'dis': [adr pnl], 'oos': [...], 'oos_usd': [...]}."""
    out = defaultdict(list)
    for r in rows:
        d = pick(r)
        x = r.get(exit_col)
        if not d or x is None:
            continue
        usd = d * (x - r["o_at"]) - COST_USD
        k = "dis" if dt.date.fromisoformat(r["date"]) <= DISCOVERY_END else "oos"
        out[k].append(usd / r["adr"])
        out[k + "_usd"].append(usd)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--features", default="backtest/reports/kz_features/features_1000.csv")
    ap.add_argument("--t-min", type=float, default=2.5)
    ap.add_argument("--show", type=int, default=25, help="rows of the discovery ranking to print")
    args = ap.parse_args()

    rows = load(_ROOT / args.features)
    for r in rows:
        r["_sig"] = signals(r)
    names = list(rows[0]["_sig"])

    cells = []
    for name in names:
        for variant, mult in (("follow", 1), ("fade", -1)):
            for ex in EXITS:
                sc = score(rows, lambda r, n=name, m=mult: m * r["_sig"][n], ex)
                if len(sc["dis"]) < 100:
                    continue
                cells.append((name, variant, ex, sc))

    n_dis = sum(1 for r in rows if dt.date.fromisoformat(r["date"]) <= DISCOVERY_END)
    print(
        f"\n{len(rows)} days  (discovery {n_dis}, unseen {len(rows) - n_dis})  cost ${COST_USD:.2f}/oz round trip"
    )
    print(f"{len(cells)} cells = {len(names)} signals x follow/fade x {len(EXITS)} exits\n")

    cells.sort(key=lambda c: -_t(c[3]["dis"]))
    print(f"TOP {args.show} BY DISCOVERY t  (2018-2023) — then the SAME cell on 2024-2026, unseen")
    print(
        f"  {'signal':<32}{'rule':<7}{'exit':<7}{'nDis':>6}{'dis%ADR':>9}{'tDis':>6}{'nOOS':>6}{'oos%ADR':>9}{'tOOS':>6}{'oos$':>8}"
    )
    for name, var, ex, sc in cells[: args.show]:
        print(
            f"  {name:<32}{var:<7}{ex[2:]:<7}{len(sc['dis']):>6}{100 * statistics.fmean(sc['dis']):>+8.2f}%"
            f"{_t(sc['dis']):>+6.1f}{len(sc['oos']):>6}"
            f"{100 * statistics.fmean(sc['oos']) if sc['oos'] else float('nan'):>+8.2f}%"
            f"{_t(sc['oos']):>+6.1f}{statistics.fmean(sc['oos_usd']) if sc['oos_usd'] else float('nan'):>+8.2f}"
        )

    ctrl = [c for c in cells if c[0].startswith("CONTROL")]
    if ctrl:
        best = max(ctrl, key=lambda c: _t(c[3]["dis"]))
        rank = cells.index(best) + 1
        print(
            f"\nNOISE FLOOR — the coin flip's best cell ranks #{rank} of {len(cells)} "
            f"(discovery t {_t(best[3]['dis']):+.1f}, unseen t {_t(best[3]['oos']):+.1f}). "
            "Anything ranked near it is indistinguishable from chance."
        )

    cand = [c for c in cells if _t(c[3]["dis"]) >= args.t_min]
    print(f"\nCANDIDATES (discovery t >= {args.t_min}): {len(cand)}")
    found = [c for c in cand if _t(c[3]["oos"]) >= 2.0]
    for name, var, ex, sc in cand:
        verdict = "FOUND" if (name, var, ex, sc) in found else "failed on unseen years"
        print(
            f"  {name} ({var}, exit {ex[2:]}): unseen t {_t(sc['oos']):+.1f}, ${statistics.fmean(sc['oos_usd']):+.2f}/trade — {verdict}"
        )

    # A vote of the best discovery signals — the honest way to combine without hand-picking.
    for ex in ("c_1100",):
        ranked = sorted([c for c in cells if c[2] == ex], key=lambda c: -_t(c[3]["dis"]))
        seen, top = set(), []
        for name, var, _, sc in ranked:
            if name not in seen and _t(sc["dis"]) > 1.0:
                seen.add(name)
                top.append((name, 1 if var == "follow" else -1))
            if len(top) == 5:
                break
        for k in (3, 5):
            use = top[:k]
            if len(use) < k:
                continue

            def vote(r, use=use):
                v = sum(m * r["_sig"][n] for n, m in use)
                return _sg(v)

            sc = score(rows, vote, ex)
            print(
                f"\nVOTE of the top {k} discovery signals, exit {ex[2:]}: "
                + ", ".join(f"{n} ({'follow' if m > 0 else 'fade'})" for n, m in use)
            )
            print(
                f"  discovery t {_t(sc['dis']):+.1f} ({len(sc['dis'])} trades)   "
                f"unseen t {_t(sc['oos']):+.1f} ({len(sc['oos'])} trades, "
                f"${statistics.fmean(sc['oos_usd']):+.2f}/trade after costs)"
            )
    print(
        f"\n⚠ {len(cells)} cells: at t>=2.0 about {0.025 * len(cells):.0f} would pass discovery by luck."
        " Only 'FOUND' — significant on years nobody tuned on — counts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
