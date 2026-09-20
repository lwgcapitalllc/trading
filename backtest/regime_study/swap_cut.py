#!/usr/bin/env python3
"""swap_cut.py — replay the extreme leg with the CANDIDATE reading in place of the shipped one.

WHY THIS EXISTS. `backtest/notes/regime-grading.md` compares the shipped market cut ON against
OFF and finds it free but unproven. The open question it leaves is the direct one: if the
candidate reading (`backtest/regime_study/candidate.py`) refused instead, would the money or
the worst losing run be better? That cannot be answered by filtering an exported trade list,
because with one position slot a refused setup lets the NEXT one in — the book is not a subset
(root `CLAUDE.md`, Run 12). Only a real replay answers it, so this runs one.

🔴 **NO STRATEGY FILE IS TOUCHED.** The strategy holds its market cut as an instance attribute
built in its own `__init__`, exposing `on_bar`, `on_htf_bar` and `ask`. This swaps that one
object after construction and changes nothing else, so the candidate can never reach a live
bot by being here — a bot builds its own.

🔴 **THE REFUSAL RULE IS PRE-REGISTERED, HERE, BEFORE THE RUN.** The candidate names three
bands on each of two scales and the study found NO ordering among the nine cells on money, so
picking the band that scores best after the fact would be fitting to 170 trades. The rule is
the STRUCTURAL analogue of the shipped one: the shipped cut refuses the market it calls
TRANSITIONING — the ambiguous middle — so this refuses the middle third of the persistence
scale, `NEUTRAL`. One rule, chosen for what it mirrors, not for what it scores.

⚠ **UNKNOWN ALLOWS**, exactly as the shipped cut does, and is counted separately. A filter that
refused whenever it could not see would be a different strategy on thin data.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402
from backtest.regime_study.candidate import LOOKBACK, band_of, persistence_percentile  # noqa: E402
from backtest.replay.build import build_strategy  # noqa: E402
from backtest.replay.registry import load  # noqa: E402
from backtest.tools.trade_export import finished_trades  # noqa: E402

REFUSE, ALLOW, UNKNOWN = "REFUSE", "ALLOW", "UNKNOWN"

# The persistence reading needs its rolling window (240) plus its ranking history (1000), so a
# shorter buffer would make the cut answer UNKNOWN forever and quietly become no cut at all.
_KEEP = LOOKBACK + 400

# The band this cut refuses. See the docstring: chosen for what it MIRRORS, before the run.
REFUSED_BAND = "NEUTRAL"


class CandidateCut:
    """Refuse a setup while the candidate reading calls persistence middling.

    Same three-way protocol as `strategies/python/extreme_leg/filters.py` — REFUSE, ALLOW or
    UNKNOWN, never a bool — and the same counters, so a cut that was never wired up cannot look
    like a cut that allowed everything.
    """

    def __init__(self) -> None:
        self._bars: deque = deque(maxlen=_KEEP)
        self.asked = 0
        self.refused = 0
        self.unknown_count = 0

    def on_bar(self, o: float, h: float, low: float, c: float) -> None:
        self._bars.append((o, h, low, c))

    def on_htf_bar(self, o: float, h: float, low: float, c: float) -> None:
        # The candidate reads ONE scale of bars by design. The higher frame is accepted and
        # dropped so this object is drop-in for the shipped cut rather than needing the
        # strategy to know which cut it is holding.
        return

    def ask(self) -> str:
        self.asked += 1
        df = pd.DataFrame(list(self._bars), columns=["open", "high", "low", "close"])
        band = band_of(persistence_percentile(df, lookback=LOOKBACK), ("LOW", "NEUTRAL", "HIGH"))
        if band is None:
            self.unknown_count += 1
            return UNKNOWN
        if band == REFUSED_BAND:
            self.refused += 1
            return REFUSE
        return ALLOW


def replay(symbol: str, tf: str, start: str, end: str, warmup: int, *, cut: str) -> list[dict]:
    """One replay of the extreme leg under `cut`: 'off', 'shipped' or 'candidate'."""
    spec = load("extreme_leg")
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]
    df = BarSource().load(symbol, tf, start, end)
    if df.empty:
        raise SystemExit("no bars returned — is the MT5 agent tunnel up?")
    import dataclasses

    cfg = dataclasses.replace(ConfigCls(symbol=symbol), skip_transitioning=(cut != "off"))
    strat = build_strategy(StrategyCls, cfg, initial_capital=10_000.0)
    if cut == "candidate":
        strat.cut_regime = CandidateCut()
    print(f"  [{cut}] {len(df):,} bars {df.index[0]} -> {df.index[-1]}", flush=True)
    strat.run(df, warmup=warmup)
    print(
        f"  [{cut}] cut asked {strat.cut_regime.asked}, refused "
        f"{strat.cut_regime.refused}, unknown {strat.cut_regime.unknown_count}",
        flush=True,
    )
    return finished_trades(strat, df)


def worst_run(rows: list[dict]) -> float:
    """Deepest peak-to-trough stretch of the R curve, in R. Positive number."""
    peak = run = 0.0
    worst = 0.0
    for r in rows:
        if r["r"] is None:
            continue
        run += r["r"]
        peak = max(peak, run)
        worst = max(worst, peak - run)
    return worst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="5")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--out-dir", default=None, help="write each book as CSV here")
    args = ap.parse_args(argv)

    books = {}
    for cut in ("off", "shipped", "candidate"):
        books[cut] = replay(args.symbol, args.tf, args.start, args.end, args.warmup, cut=cut)

    print("\n| cut | trades | sumR | avgR | worst losing run |")
    print("|---|---|---|---|---|")
    for cut, rows in books.items():
        rs = [r["r"] for r in rows if r["r"] is not None]
        total = sum(rs)
        avg = total / len(rs) if rs else float("nan")
        print(f"| {cut} | {len(rows)} | {total:+.1f} | {avg:+.2f} | {worst_run(rows):.2f}R |")

    if args.out_dir:
        import csv

        d = Path(args.out_dir)
        d.mkdir(parents=True, exist_ok=True)
        for cut, rows in books.items():
            with (d / f"xleg_{cut}.csv").open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["entry_utc", "r", "dir", "exit_reason"])
                w.writeheader()
                w.writerows(rows)
        print(f"\nbooks -> {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
