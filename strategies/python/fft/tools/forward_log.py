#!/usr/bin/env python3
"""forward_log.py — grade FFT's four unproven leads on every trade the bot takes, going forward.

The leads (backtest/notes/fft_ledger.md → *Mining the losers*) were found on 2020-26 gold, so that
data can no longer prove them. This tool grades them on trades AFTER they were found — the demo
account's period — without any of them being switched on:

  lead 1   skip after 4+ 15m BOS    each trade whose 15m trend had made 4+ continuation BOS since
                                    its shift is marked; the tally shows the total R without them.
  lead 2   Asia entries take TP1    each trade entered 18:00-02:59 New York is re-scored as if it
                                    had taken TP1: +reward-to-TP1 if TP1 printed before the stop.
  lead 3   a sweep before entry     each trade is marked if the pullback took a session / day /
                                    4-hour level on its side, not taken before, between the leg's
                                    extreme and the touch (the corrected label, 2026-09-21); the
                                    tally shows the sweep trades against the rest.
  lead 4   an equal level ahead     each trade is marked if an active 5m equal high (buy) / equal
                                    low (sell) sat between the 61.8 and TP2 at the touch — 11 of
                                    11 won 2020-26, not past the luck bar (2026-09-22, the ledger's
                                    *best trades* section); the tally shows them against the rest.

⚠ **This is a REPLAY, not a log the trading box writes.** The bot is deterministic and matched to
the study trade for trade (`compare_study.py`), so replaying the demo period's 1-minute bars
through it gives the trades it took. Nothing extra runs live. It replays the RAW bars, as the lab
and the live bot see them — no reopen-spike clip. A trade the live bot took and this replay does
not (a missed fill, a restart) is the one thing it cannot see; check the list against the
account's history.

⚠ **"TP1 printed before the stop" follows the study's walk**: the fill minute counts only if the
order filled at that minute's open, and a minute reaching both TP1 and the stop is the stop.
R is cost-free: the leads are compared against the same trades, so costs mostly cancel.

Usage:
  python strategies/python/fft/tools/forward_log.py --start 2026-09-21
  python strategies/python/fft/tools/forward_log.py --start 2026-09-21 --end 2026-12-31 --csv out.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for _p in (ROOT, ROOT / "strategies" / "python"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

CACHE = ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"
WARMUP_DAYS = 31  # the study's warm-up: the 15m trend and the 5m fib need it
ASIA = lambda h: h >= 18 or h < 3  # noqa: E731 — 18:00-02:59 New York, the lead's own window


def session(h: int) -> str:
    return "Asia" if ASIA(h) else "London" if h < 8 else "New York" if h < 17 else "break"


def tp1_first(df: pd.DataFrame, t, tp1: float) -> bool:
    """Did TP1 print before the trade ended, by the study's walk? A win at TP2 passed TP1 on the
    way; a stop needs a minute strictly between the fill and the stop minute (the fill minute
    only when filled at its open) to reach TP1."""
    if t.exit_reason == "target":
        return True
    h, lo, o = df["high"].to_numpy(), df["low"].to_numpy(), df["open"].to_numpy()
    first = t.entry_index if abs(o[t.entry_index] - t.entry_price) < 1e-9 else t.entry_index + 1
    for j in range(first, t.exit_index):
        if (h[j] >= tp1) if t.dir > 0 else (lo[j] <= tp1):
            return True
    return False


def rows(start: str, end: str | None, csv: Path) -> list[dict]:
    import fft
    from fft.config import OVEREXTENDED_15M_BOS

    t0 = pd.Timestamp(start)
    df = pd.read_csv(csv, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[df["time"] >= t0 - pd.Timedelta(days=WARMUP_DAYS)]
    if end:
        df = df[df["time"] < pd.Timestamp(end)]
    df = df.set_index("time").astype(float)
    if df.empty or df.index[-1] < t0:
        sys.exit(f"no 1-minute bars at or after {start} in {csv}")
    s = fft.FftStrategy().run(df)
    cut = int(t0.value // 10**6)
    out = []
    for t in s.execution.trades:
        if t.entry_ms < cut:
            continue
        lv = dict(t.fib.levels)
        tp1 = lv[0.5]
        got = [x for x in s.touches if x.traded and x.dir == t.dir and x.ts_ms <= t.entry_ms]
        n15 = got[-1].nbos15 if got else -1
        swept = bool(got[-1].swept) if got else False
        eqt = bool(got[-1].eq_target) if got else False
        ny = pd.Timestamp(t.entry_ms, unit="ms", tz="UTC").tz_convert("America/New_York")
        first = tp1_first(df, t, tp1)
        r1 = abs(tp1 - t.entry_price) / t.stop_distance
        asia = ASIA(ny.hour)
        out.append(
            dict(
                entry_ny=ny.strftime("%a %Y-%m-%d %H:%M"),
                side="buy" if t.dir > 0 else "sell",
                result=t.exit_reason,
                r=round(t.r, 3),
                bos15=n15,
                session=session(ny.hour),
                sweep=swept,
                eq_ahead=eqt,
                tp1_first=first,
                lead1_skip=n15 >= OVEREXTENDED_15M_BOS,
                lead2_r=round((r1 if first else -1.0) if asia else t.r, 3),
            )
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", required=True, help="grade trades entered on or after this date")
    ap.add_argument("--end", default=None)
    ap.add_argument("--bars", type=Path, default=CACHE, help="a 1-minute bar CSV (time,o,h,l,c)")
    ap.add_argument("--csv", type=Path, default=None, help="also write the rows here")
    a = ap.parse_args()
    got = rows(a.start, a.end, a.bars)
    if not got:
        print(f"no FFT trades on or after {a.start}")
        return 0
    df = pd.DataFrame(got)
    with pd.option_context("display.width", 200, "display.max_rows", None):
        print(df.to_string(index=False))
    base = df.r.sum()
    l1 = df[~df.lead1_skip]
    print(f"\n{len(df)} trades, {int((df.r > 0).sum())} won, total {base:+.2f}R (cost-free)")
    print(
        f"lead 1 — skip after 4+ 15m BOS: {int(df.lead1_skip.sum())} marked "
        f"({int((df[df.lead1_skip].r > 0).sum())} won); without them {l1.r.sum():+.2f}R "
        f"({l1.r.sum() - base:+.2f}R)"
    )
    print(
        f"lead 2 — Asia entries take TP1: {int((df.session == 'Asia').sum())} Asia trades; "
        f"total {df.lead2_r.sum():+.2f}R ({df.lead2_r.sum() - base:+.2f}R)"
    )
    sw, rest = df[df.sweep], df[~df.sweep]
    print(
        f"lead 3 — a sweep before the entry: {len(sw)} trades, {int((sw.r > 0).sum())} won, "
        f"{sw.r.mean() if len(sw) else 0:+.3f}R a trade vs {rest.r.mean() if len(rest) else 0:+.3f}R "
        f"for the other {len(rest)}"
    )
    eq, other = df[df.eq_ahead], df[~df.eq_ahead]
    print(
        f"lead 4 — an equal level between the entry and TP2: {len(eq)} trades, "
        f"{int((eq.r > 0).sum())} won, {eq.r.mean() if len(eq) else 0:+.3f}R a trade vs "
        f"{other.r.mean() if len(other) else 0:+.3f}R for the other {len(other)}"
    )
    if a.csv:
        df.to_csv(a.csv, index=False)
        print(f"written to {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
