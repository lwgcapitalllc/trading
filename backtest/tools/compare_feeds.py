"""compare_feeds.py — how closely does the PU Prime (MT5) feed line up with a
TradingView export of the same symbol/timeframe/window?

This is NOT a logic-parity check (that's `compare_strategy.py`, which replays
TradingView's *own* bars through the Python and must hit exit 0). This is a
DATA-parity check: two different broker feeds will never be tick-identical, so
the job here is to *measure* the gap, not eliminate it, and to catch the one
difference that silently breaks the session/liquidity engines — a **clock
offset** (MT5 returns broker-server time; if it isn't true UTC, every session
window fires in the wrong place).

It reports three things:
  1. Clock offset — the whole-hour shift that best aligns the two timestamp
     grids. 0 = aligned. Anything else is a real finding to fix before demo.
  2. Coverage — how many bars match, and how many are TradingView-only / MT5-only.
  3. OHLC drift — mean/max absolute price difference on the matched bars, and the
     mean as a fraction of price (gold's ~$0.30 spread is normal; a structural
     mismatch is not).

Usage (needs the MT5 agent up + the SSH tunnel to localhost:8766 — see
backtest/CLAUDE.md):
    python backtest/tools/compare_feeds.py --csv tv_export.csv --symbol XAUUSD.s

The pure alignment math (parse / infer-tf / detect-offset / diff) is importable
and unit-tested offline; only `main` touches the network.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# backtest/ is a top-level package; make it importable when run as a script.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.data import SERVED_TF, BarCache, BarSource, Mt5Agent  # noqa: E402

_OHLC = ["open", "high", "low", "close"]


# --------------------------------------------------------------- parsing ------
def parse_tv_csv(path: str | Path) -> pd.DataFrame:
    """Read a TradingView 'Export chart data' CSV into the canonical bar frame
    (DatetimeIndex 'time' as naive UTC + float OHLC). Handles an ISO `time`
    column (tz-aware or not) and a unix-seconds `time` column."""
    raw = pd.read_csv(path)
    lower = {c.strip().lower(): c for c in raw.columns}

    def col(name: str) -> str:
        if name in lower:
            return lower[name]
        for low, orig in lower.items():
            if low.endswith(name) or name in low:
                return orig
        raise SystemExit(f"ERROR: column '{name}' not found in CSV header: {list(raw.columns)}")

    tcol = col("time")
    times = raw[tcol]
    if pd.api.types.is_numeric_dtype(times):
        idx = pd.to_datetime(times, unit="s", utc=True)
    else:
        idx = pd.to_datetime(times, utc=True)
    idx = idx.dt.tz_convert("UTC").dt.tz_localize(None)  # naive UTC, our convention

    out = pd.DataFrame({c: raw[col(c)].astype("float64") for c in _OHLC})
    out.index = pd.DatetimeIndex(idx, name="time")
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def infer_timeframe(df: pd.DataFrame) -> tuple[str, int]:
    """Infer (tf_name, minutes) from the median bar spacing, snapped to the
    nearest served timeframe."""
    if len(df) < 2:
        raise SystemExit("ERROR: need at least 2 bars to infer the timeframe.")
    minutes = int(round(df.index.to_series().diff().dropna().dt.total_seconds().median() / 60))
    name = min(SERVED_TF, key=lambda k: abs(SERVED_TF[k] - minutes))
    return name, SERVED_TF[name]


# ------------------------------------------------------------- alignment ------
def _epoch_minutes(df: pd.DataFrame) -> set[int]:
    return {int(v // 1_000_000_000 // 60) for v in df.index.view("int64")}


def detect_offset(tv: pd.DataFrame, mt5: pd.DataFrame, max_hours: int = 14) -> tuple[int, int]:
    """Return (best_shift_hours, matched_bars). `best_shift_hours` is how many
    whole hours MT5 must move to line up with TradingView: 0 = aligned; a
    negative value means MT5 timestamps run that many hours AHEAD of TradingView
    (broker server = UTC+N when TV is UTC).

    Scored by PRICE agreement, not just timestamp overlap: when MT5 spans a wide
    range, many shifts fully cover a small TV window, so timestamps alone can't
    tell the offset apart — but only the physically-correct shift makes the two
    feeds' closes agree. Best = smallest mean |Δclose| over matched bars (needing
    a meaningful match count), ties broken toward more matches then smaller shift."""
    floor = max(3, len(tv) // 4)
    best_key: tuple[float, int, int] | None = None
    best_shift, best_matched = 0, 0
    for h in range(-max_hours, max_hours + 1):
        shifted = mt5.copy()
        shifted.index = shifted.index + pd.Timedelta(hours=h)
        common = tv.index.intersection(shifted.index)
        if len(common) < floor:
            continue
        diff = float((tv.loc[common, "close"] - shifted.loc[common, "close"]).abs().mean())
        key = (round(diff, 6), -len(common), abs(h))
        if best_key is None or key < best_key:
            best_key, best_shift, best_matched = key, h, len(common)
    return best_shift, best_matched


@dataclass
class OffsetChunk:
    start: str  # chunk start date (YYYY-MM-DD)
    shift_hours: int  # MT5->TV shift that best aligns this chunk
    overlap: int  # matched bars in the chunk at that shift


def offset_profile(tv: pd.DataFrame, mt5: pd.DataFrame, chunks: int = 8) -> list[OffsetChunk]:
    """Detect the clock offset in `chunks` equal time-spans across the window.
    A broker whose server clock follows DST (MetaTrader's usual UTC+2/UTC+3)
    shows TWO offsets across a window that crosses a DST boundary — a single
    global shift would then mis-align half the data. This surfaces that."""
    t0, t1 = tv.index[0], tv.index[-1]
    edges = pd.date_range(t0, t1, periods=chunks + 1)
    out: list[OffsetChunk] = []
    for a, b in zip(edges[:-1], edges[1:]):
        tvs = tv[(tv.index >= a) & (tv.index < b)]
        if len(tvs) < 2:
            continue
        # Compare the TV chunk against the FULL MT5 frame: MT5 is offset in
        # absolute time, so slicing it to the same wall-clock window would erase
        # the very offset we're measuring.
        shift, overlap = detect_offset(tvs, mt5)
        out.append(OffsetChunk(start=a.date().isoformat(), shift_hours=shift, overlap=overlap))
    return out


def dst_correct(tv: pd.DataFrame, mt5: pd.DataFrame, profile: list[OffsetChunk]) -> pd.DataFrame:
    """Align MT5 to TV per bar under a possibly-variable offset. For each distinct
    offset in the profile, shift MT5 by it and match to TV; each TV bar keeps the
    offset whose price is closest (the physically-correct one — a wrong DST offset
    lands on a different-time bar and mismatches). Returns MT5 OHLC re-indexed onto
    the TV timestamps it truly corresponds to."""
    shifts = sorted({c.shift_hours for c in profile}) or [0]
    best: dict[pd.Timestamp, tuple[float, pd.Series]] = {}
    for s in shifts:
        shifted = mt5.copy()
        shifted.index = shifted.index + pd.Timedelta(hours=s)
        common = tv.index.intersection(shifted.index)
        for ts in common:
            cd = abs(float(tv.at[ts, "close"]) - float(shifted.at[ts, "close"]))
            if ts not in best or cd < best[ts][0]:
                best[ts] = (cd, shifted.loc[ts])
    if not best:
        return mt5.iloc[0:0].copy()
    idx = sorted(best.keys())
    data = {c: [float(best[ts][1][c]) for ts in idx] for c in _OHLC}
    return pd.DataFrame(data, index=pd.DatetimeIndex(idx, name="time"))


@dataclass
class FeedDiff:
    tv_bars: int
    mt5_bars: int
    matched: int
    tv_only: int
    mt5_only: int
    shift_hours: int
    mean_abs: dict  # per-OHLC-column mean absolute price diff
    max_abs: dict  # per-OHLC-column max absolute price diff
    mean_abs_pct: float  # close mean-abs-diff as a fraction of mean close


def align_and_diff(tv: pd.DataFrame, mt5: pd.DataFrame, shift_hours: int) -> FeedDiff:
    """Shift MT5 by `shift_hours`, inner-join on timestamp, and measure the OHLC
    gap on the matched bars."""
    mt5s = mt5.copy()
    mt5s.index = mt5s.index + pd.Timedelta(hours=shift_hours)

    joined = tv.join(mt5s, how="inner", lsuffix="_tv", rsuffix="_mt5")
    matched = len(joined)
    mean_abs, max_abs = {}, {}
    for c in _OHLC:
        d = (joined[f"{c}_tv"] - joined[f"{c}_mt5"]).abs()
        mean_abs[c] = float(d.mean()) if matched else 0.0
        max_abs[c] = float(d.max()) if matched else 0.0
    mean_close = float(joined["close_tv"].mean()) if matched else 0.0
    pct = (mean_abs["close"] / mean_close) if mean_close else 0.0

    return FeedDiff(
        tv_bars=len(tv),
        mt5_bars=len(mt5),
        matched=matched,
        tv_only=len(tv) - matched,
        mt5_only=len(mt5) - matched,
        shift_hours=shift_hours,
        mean_abs=mean_abs,
        max_abs=max_abs,
        mean_abs_pct=pct,
    )


def format_report(diff: FeedDiff, profile: list[OffsetChunk], symbol: str, tf_name: str) -> str:
    shifts = sorted({c.shift_hours for c in profile})
    lines = [
        f"Feed comparison — {symbol} {tf_name}",
        "-" * 52,
        f"  TradingView bars : {diff.tv_bars}",
        f"  MT5 bars         : {diff.mt5_bars}",
        "",
        "  CLOCK OFFSET (MT5 vs TradingView)",
    ]
    if shifts == [0]:
        lines.append("    aligned (0h) across the whole window — timestamp grids match")
    elif len(shifts) == 1:
        ahead = -shifts[0]
        lines.append(f"    MISALIGNED — MT5 runs a constant {ahead:+d}h vs TradingView.")
        lines.append(
            "    Fix the agent's UTC conversion before trusting session/liquidity engines."
        )
    else:
        aheads = ", ".join(f"{-s:+d}h" for s in shifts)
        lines.append(f"    MISALIGNED + VARIABLE — MT5 runs {aheads} vs TradingView")
        lines.append(
            "    across the window: a broker server clock on DST (MetaTrader UTC+2/UTC+3)."
        )
        lines.append("    The agent MUST convert broker time to true UTC, DST-aware, before demo.")
        for c in profile:
            lines.append(f"      from {c.start}: {-c.shift_hours:+d}h")
    lines += [
        "",
        "  COVERAGE (after per-chunk offset correction)",
        f"    matched  : {diff.matched}",
        f"    TV-only  : {diff.tv_only}",
        f"    MT5-only : {diff.mt5_only}",
        "",
        "  OHLC DRIFT (matched bars, price units — true feed gap, offset removed)",
    ]
    for c in _OHLC:
        lines.append(f"    {c:<6} mean |Δ| {diff.mean_abs[c]:.4f}   max |Δ| {diff.max_abs[c]:.4f}")
    lines.append(f"    close mean |Δ| = {diff.mean_abs_pct * 100:.4f}% of price")
    return "\n".join(lines)


# ------------------------------------------------------------------- CLI ------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare an MT5 feed to a TradingView export.")
    ap.add_argument("--csv", required=True, help="TradingView 'Export chart data' CSV")
    ap.add_argument("--symbol", default="XAUUSD.s", help="MT5 broker symbol (default XAUUSD.s)")
    ap.add_argument("--agent-url", default="http://localhost:8766", help="MT5 agent base URL")
    ap.add_argument(
        "--warn-pct",
        type=float,
        default=0.05,
        help="fail (exit 2) if close drift exceeds this %% of price (default 0.05)",
    )
    args = ap.parse_args(argv)

    tv = parse_tv_csv(args.csv)
    tf_name, _ = infer_timeframe(tv)
    start = tv.index[0].date().isoformat()
    end = tv.index[-1].date().isoformat()
    print(f"TradingView export: {len(tv)} bars, {tf_name}, {start} → {end}")

    source = BarSource(Mt5Agent(base_url=args.agent_url), BarCache())
    mt5 = source.load(args.symbol, tf_name, start, end)
    if mt5.empty:
        print("ERROR: MT5 returned no bars for that window.", file=sys.stderr)
        return 1

    profile = offset_profile(tv, mt5)
    corrected = dst_correct(tv, mt5, profile)  # each bar shifted by its own chunk's offset
    diff = align_and_diff(tv, corrected, 0)  # true feed gap, clock offset removed
    print(format_report(diff, profile, args.symbol, tf_name))

    shifts = {c.shift_hours for c in profile}
    if shifts and shifts != {0}:
        return 2  # a clock offset exists — a real agent bug to fix before demo
    if diff.mean_abs_pct * 100 > args.warn_pct:
        print(
            f"\nWARNING: close drift {diff.mean_abs_pct * 100:.4f}% exceeds "
            f"{args.warn_pct}% — investigate (wrong symbol? feed issue?)."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
