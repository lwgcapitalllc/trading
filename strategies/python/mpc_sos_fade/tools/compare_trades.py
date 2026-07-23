"""compare_trades.py — the A+ TRADE-LIST reconciliation.

Answers one question: **did we take the same trades TradingView took?**

Reads TradingView's "List of trades" export (Strategy Tester → Export) and a lab run's
`equity_curve.json`, pairs the two trade lists up by ENTRY TIME, and prints what matched,
what only TradingView took, and what only we took — plus the per-trade P&L gap on the
matched ones.

How this differs from its sibling `compare_strategy.py`:

    compare_strategy.py   LOGIC parity  — replays TradingView's OWN bars through the bot
                                          and diffs the per-bar decision stream. Proves the
                                          engines agree. Needs the instrumented
                                          `mpc_strategy_export.pine` decision-stream export.
    compare_trades.py     RESULT parity — diffs the two finished trade lists. Proves the
                                          whole pipeline (feed + engines + fills + costs)
                                          lands in the same place. Needs only the ordinary
                                          Strategy Tester trade export, which is what you
                                          actually have when a backtest looks wrong.

Use this one FIRST — it tells you whether the gap is *which trades* (a logic/engine
problem → go run compare_strategy.py) or *how much each trade made* (a feed, fill, or
cost problem → the engines are fine).

Two structural differences it handles for you:

  * **TradingView counts each TP rung as its own trade.** A 3-rung position exports as
    three "Trade number"s sharing one entry. They are regrouped into one position, so
    123 TV rows become 41 positions against our 40.
  * **TradingView stamps times in the chart's EXCHANGE timezone**, our runs in UTC epoch ms.
    Default `--tz Etc/GMT+4` = a FIXED UTC-4: the Vantage XAUUSD chart does NOT observe US
    DST, so America/New_York shifts every winter trade by an hour and the pairing goes
    fuzzy. If your chart's exchange differs, the run prints the offset to pass instead.

Usage:
    python compare_trades.py <tv_trades.csv> <equity_curve.json> [--tz Etc/GMT+4]
                             [--tol-min 90] [--json out.json]

Exit 0 = every trade paired. Exit 1 = at least one unmatched trade on either side.

Stdlib only (csv/json/zoneinfo) — no pandas, unlike compare_strategy.py, because a trade
list is small and this wants to run anywhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

# TradingView's own header names, so a renamed column fails loudly instead of silently
# comparing zeros.
_C_NUM = "Trade number"
_C_TYPE = "Type"
_C_TIME = "Date and time"
_C_SIGNAL = "Signal"
_C_PRICE = "Price USD"
_C_QTY = "Size (qty)"
_C_PNL = "Net PnL USD"
_C_COMM = "Commission USD"


class Position:
    """One economic trade: an entry plus every rung that closed it."""

    def __init__(self, entry_ms: int, direction: str, entry_price: float):
        self.entry_ms = entry_ms
        self.direction = direction
        self.entry_price = entry_price
        self.exit_ms: Optional[int] = None
        self.pnl = 0.0
        self.commission = 0.0
        self.qty = 0.0
        self.legs: List[str] = []

    @property
    def entry_iso(self) -> str:
        return datetime.utcfromtimestamp(self.entry_ms / 1000).strftime("%Y-%m-%d %H:%M")


def _f(row: Dict[str, str], key: str) -> float:
    raw = (row.get(key) or "").replace(",", "").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def load_tv(path: Path, tz: str) -> List[Position]:
    """Parse a TradingView trade export into positions, regrouping the TP rungs.

    Rows come newest-first and interleaved (exit row before its entry row), so nothing here
    may depend on file order: positions are keyed by (entry time, direction) and the exit
    time is taken as the LAST leg to close.
    """
    zone = ZoneInfo(tz)
    # utf-8-sig: TradingView writes a BOM, which would otherwise corrupt the first header.
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path}: no rows")
    missing = [c for c in (_C_NUM, _C_TYPE, _C_TIME, _C_PRICE, _C_PNL) if c not in rows[0]]
    if missing:
        raise SystemExit(f"{path}: not a TradingView trade export — missing {missing}")

    # Pass 1: each TV "trade number" is one rung — collect its entry and its exit.
    rungs: Dict[str, Dict[str, Dict[str, str]]] = {}
    for row in rows:
        kind = (row[_C_TYPE] or "").lower()
        side = "entry" if kind.startswith("entry") else "exit" if kind.startswith("exit") else None
        if side:
            rungs.setdefault(row[_C_NUM], {})[side] = row

    # Pass 2: fold rungs that share an entry back into one position.
    out: Dict[tuple, Position] = {}
    for num, pair in rungs.items():
        entry, exit_ = pair.get("entry"), pair.get("exit")
        if not entry:
            continue
        if not exit_:
            print(f"  note: TV trade {num} is still open at the end of the window — skipped")
            continue
        direction = "Long" if "long" in (entry[_C_TYPE] or "").lower() else "Short"
        entry_ms = _to_ms(entry[_C_TIME], zone)
        key = (entry_ms, direction)
        pos = out.get(key)
        if pos is None:
            pos = out[key] = Position(entry_ms, direction, _f(entry, _C_PRICE))
        exit_ms = _to_ms(exit_[_C_TIME], zone)
        pos.exit_ms = max(pos.exit_ms or 0, exit_ms)
        pos.pnl += _f(exit_, _C_PNL)
        pos.commission += _f(entry, _C_COMM) + _f(exit_, _C_COMM)
        pos.qty += _f(entry, _C_QTY)
        pos.legs.append(exit_.get(_C_SIGNAL, "?"))
    return sorted(out.values(), key=lambda p: p.entry_ms)


def _to_ms(stamp: str, zone: ZoneInfo) -> int:
    """'2025-07-24 22:15' in the chart's exchange timezone → UTC epoch ms.

    The offset is resolved per-timestamp rather than once, so a DST-observing exchange is
    handled correctly too — a year-long window always spans a DST flip.
    """
    dt = datetime.strptime(stamp.strip()[:16], "%Y-%m-%d %H:%M").replace(tzinfo=zone)
    return int(dt.timestamp() * 1000)


def load_ours(path: Path) -> List[Position]:
    """Parse a lab run's equity_curve.json (each point is already one position)."""
    points = json.loads(path.read_text())
    out: List[Position] = []
    for p in points:
        if p.get("entry_ms") is None:
            raise SystemExit(
                f"{path}: point #{p.get('index')} has no entry_ms — rerun the backtest "
                "(older runs did not record entry times, so nothing can be paired)"
            )
        pos = Position(int(p["entry_ms"]), p.get("direction", "?"), p.get("entry_price", 0.0))
        pos.exit_ms = p.get("exit_ms")
        pos.pnl = p.get("profit", 0.0)
        pos.qty = p.get("size", 0.0)
        pos.legs = [leg.get("reason", "?") for leg in p.get("legs", [])]
        out.append(pos)
    return sorted(out, key=lambda p: p.entry_ms)


def pair(tv: List[Position], ours: List[Position], tol_min: int) -> tuple:
    """Greedy nearest-entry pairing within `tol_min`, same direction.

    Entry TIME is the identity, not entry price: the two feeds are different brokers, so the
    prices legitimately differ by cents while the bar that triggered the entry is the same.
    """
    tol_ms = tol_min * 60_000
    used = [False] * len(ours)
    matched, tv_only = [], []
    for t in tv:
        best, best_gap = -1, tol_ms + 1
        for i, o in enumerate(ours):
            if used[i] or o.direction != t.direction:
                continue
            gap = abs(o.entry_ms - t.entry_ms)
            if gap < best_gap:
                best, best_gap = i, gap
        if best >= 0:
            used[best] = True
            matched.append((t, ours[best]))
        else:
            tv_only.append(t)
    return matched, tv_only, [o for i, o in enumerate(ours) if not used[i]]


def _utc_offset_hours(tz: str) -> int:
    """The zone's offset from UTC in whole hours, sampled mid-year (only used for the hint)."""
    return int(datetime(2026, 6, 1, tzinfo=ZoneInfo(tz)).utcoffset().total_seconds() // 3600)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tv_csv", type=Path, help="TradingView 'List of trades' export")
    ap.add_argument("equity_json", type=Path, help="reports/lab/<run_id>/equity_curve.json")
    ap.add_argument("--tz", default="Etc/GMT+4",
                    help="the chart's exchange timezone. Default is a FIXED UTC-4 (Etc/GMT+4 is "
                         "UTC MINUS 4 — the POSIX sign is inverted), which is what the Vantage "
                         "XAUUSD chart uses; it does not observe US DST (default: %(default)s)")
    ap.add_argument("--tol-min", type=int, default=90,
                    help="how far apart two entries may be and still be the same trade (default: %(default)s min)")
    ap.add_argument("--json", type=Path, help="also write the full pairing to this file")
    args = ap.parse_args()

    tv = load_tv(args.tv_csv, args.tz)
    ours = load_ours(args.equity_json)
    matched, tv_only, ours_only = pair(tv, ours, args.tol_min)

    tv_pnl = sum(p.pnl for p in tv)
    our_pnl = sum(p.pnl for p in ours)
    print(f"\nTradingView : {len(tv):>3} trades   net {tv_pnl:>+12,.2f}   ({args.tv_csv.name})")
    print(f"Ours        : {len(ours):>3} trades   net {our_pnl:>+12,.2f}   ({args.equity_json.parent.name})")
    print(f"Paired      : {len(matched):>3}   TV-only {len(tv_only)}   ours-only {len(ours_only)}\n")

    if matched:
        print(f"{'#':>3} {'entry (UTC)':16} {'dir':5} {'TV pnl':>11} {'our pnl':>11} {'diff':>11} "
              f"{'entry Δ':>8} {'TV px':>9} {'our px':>9}")
        for i, (t, o) in enumerate(matched, 1):
            print(f"{i:>3} {t.entry_iso:16} {t.direction:5} {t.pnl:>+11,.2f} {o.pnl:>+11,.2f} "
                  f"{o.pnl - t.pnl:>+11,.2f} {(o.entry_ms - t.entry_ms)//60000:>7}m "
                  f"{t.entry_price:>9,.2f} {o.entry_price:>9,.2f}")
        # The matched-set gap is the honest apples-to-apples number: it excludes the trades
        # only one side took, so it isolates fills/costs/sizing from signal disagreement.
        # A whole-hour bias on every pairing means the timezone is wrong, not the trades —
        # say so rather than letting it read as sloppy matching.
        offs = sorted((o.entry_ms - t.entry_ms) // 60000 for t, o in matched)
        median = offs[len(offs) // 2]
        if median and median % 60 == 0:
            hrs = median // 60
            print(f"\n  note: every pairing is off by ~{hrs:+d}h — the chart's exchange timezone is not "
                  f"{args.tz}. Re-run with --tz Etc/GMT{-(hrs - _utc_offset_hours(args.tz)):+d}.")
        gap = sum(o.pnl - t.pnl for t, o in matched)
        print(f"\nMatched-set P&L gap: {gap:+,.2f}  "
              f"(the rest of the {our_pnl - tv_pnl:+,.2f} total gap is the unpaired trades)")

    for label, group in (("ONLY TRADINGVIEW TOOK", tv_only), ("ONLY WE TOOK", ours_only)):
        if group:
            print(f"\n{label} ({len(group)}):")
            for p in group:
                print(f"  {p.entry_iso}  {p.direction:5} {p.pnl:>+11,.2f}  @{p.entry_price:,.2f}  {'/'.join(p.legs)}")

    if args.json:
        args.json.write_text(json.dumps({
            "matched": [{"entry": t.entry_iso, "dir": t.direction, "tv_pnl": t.pnl, "our_pnl": o.pnl}
                        for t, o in matched],
            "tv_only": [{"entry": p.entry_iso, "dir": p.direction, "tv_pnl": p.pnl} for p in tv_only],
            "ours_only": [{"entry": p.entry_iso, "dir": p.direction, "our_pnl": p.pnl} for p in ours_only],
        }, indent=2))
        print(f"\nwrote {args.json}")

    ok = not tv_only and not ours_only
    print(f"\n{'GREEN — every trade paired' if ok else 'RED — unpaired trades above'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
