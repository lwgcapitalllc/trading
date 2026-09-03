"""compare_bleg.py — the B-LEG LOGIC-PARITY check.

The B-LEG twin of `mpc_sos_fade/tools/compare_strategy.py`. Reads a TradingView
"Export chart data" CSV of `strategies/tradingview/mpc_b_leg_strategy_export.pine` — the instrumented
B-LEG strategy that plots its per-bar DECISION STREAM plus the B-LEG TRACKER's own state
plus every input toggle as a column — replays the export's OWN bars through the Python bot
configured to the SAME toggles, and diffs the two streams bar by bar.

Exit 0 = the Python makes the identical decisions as the Pine. On a mismatch it names the
FIRST bar and field that diverged.

This is LOGIC parity (same decisions on the SAME candles), NOT feed parity (whether MT5's
candles match TradingView's — that is `backtest/tools/compare_feeds.py`). Logic parity
replays TradingView's own bars, so the broker feed is irrelevant here.

WHY IT IS A SEPARATE TOOL rather than a flag on compare_strategy.py: the two bots diff
DIFFERENT fields. In the B-LEG fork A+ never places an order (it only holds priority), so
`px_dec_bits`'s arm bits are the B-LEG arm, `px_edge` is the frozen band's 0.5 edge rather
than an FVG edge, and TP1/TP2 are computed off the band instead of read from fib levels.
Diffing `long_armed` here would test a decision that never happens. What IS shared — the
packed cfg_* decoding — is imported, not duplicated.

Usage:
    python compare_bleg.py <export.csv> [--warmup N] [--price-tol 0.01] [--r-tol 0.02]

Stdlib + pandas, same as the A+ harness.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

# ── make the bot importable standalone (CLI / CI), same shim as strategy.py ──
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_bleg import BLegConfig, MpcBLegStrategy  # noqa: E402
from mpc_sos_fade.tools.compare_strategy import (  # noqa: E402
    config_from_export as _config_from_export,
    engine_config_from_export as _engine_config_from_export,
    EqExemptUnknown,
    load_export,
    NothingToCompare,
    timeframe_refusal,
    unsettled_tail,
)

# How many bars at the END of an export cannot be compared.
#
# 🔴 **DERIVED from the structure engine's own pivot length, never typed as a number here.** Swings
# come from `ta.pivothigh(high, majorLength, majorLength)`, which cannot confirm a pivot until
# `majorLength` further bars exist — so on an export pulled from a LIVE chart the final
# `majorLength` bars have unsettled structure on the Pine side, and Python is entitled to a
# different answer there. MEASURED 2026-09-02: a fresh export ran green on every bar except the
# last 10, and trimming 10 turned the whole run green.
#
# ⚠ **A number typed here would go stale silently the day `major_length` moves** — the gate would
# then either nag about settled bars or, far worse, stop checking bars that had settled.
#
# 🔴 **IT IS A FLOOR, NOT THE ANSWER, AND SIZING THE WHOLE TAIL TO IT LEFT THIS GATE RED
# (2026-09-03).** The swing lookahead covers unconfirmed PIVOTS. It does not cover this fork's
# other unsettled dependency: it inherits A+'s DAY-HIGH liquidity line, which is time-based, and on
# a fresh export the two sides disagreed **65 bars** from the end — four times outside a 15-bar
# tail. Python placed a new Day High at 2026-09-03 00:45 and swept it while Pine still pointed at
# the previous one; ~230 COMPLETED day boundaries in the same export agreed exactly, which is what
# says settling rather than a bug. `unsettled_tail` (A+'s, imported rather than copied) returns the
# export's final calendar day floored by this constant.
#
# ⚠ **A+ hit this first and the lesson generalises both ways: a sibling gate's tail constant is
# sized to ITS unsettled dependency and does not transfer.** Neither does a bar count fitted to one
# export — that hides the next real drift beginning inside the tail.
UNCONFIRMED_TAIL = MpcBLegStrategy.engine_config().major_length


def config_from_export(df: pd.DataFrame, base: Optional[BLegConfig] = None) -> BLegConfig:
    """Decode a BLegConfig from the export's cfg_* columns.

    Delegates every shared column to the A+ decoder (one packing scheme, one decoder —
    both export Pines plot cfg_* identically on purpose), then reads this fork's only
    extra input. `allow_bleg=True` because the B-LEG export always ships execBLeg ON:
    the A+ decoder refuses that, correctly, since the A+ bot cannot make those trades.
    """
    cfg = _config_from_export(df, base or BLegConfig(), allow_bleg=True)
    if len(df) == 0:
        return cfg
    row = df.iloc[0]
    if "cfg_bleg_days" in df.columns and not pd.isna(row["cfg_bleg_days"]):
        from dataclasses import replace
        cfg = replace(cfg, bleg_max_days=float(row["cfg_bleg_days"]))
    else:
        print("WARNING: no cfg_bleg_days column — the B-LEG staleness cap is assumed to be at "
              "its default. Re-export off the current mpc_b_leg_strategy_export.pine.")
    return cfg


def _expand(df: pd.DataFrame) -> pd.DataFrame:
    """Unpack the export's packed columns into the flat names the diff loop reads.
    Mirrors mpc_b_leg_strategy_export.pine's PARITY EXPORT scheme exactly."""
    df = df.copy()
    if "px_dec_bits" in df.columns:
        b = df["px_dec_bits"].fillna(0).round().astype("int64")
        df["px_long_armed"] = (b & 1) != 0
        df["px_short_armed"] = (b & 2) != 0
        df["px_entry_dir"] = b.map(lambda x: 1 if x & 4 else (-1 if x & 8 else 0))
    if "px_stages" in df.columns:
        s = df["px_stages"].fillna(0).round().astype("int64")
        df["px_l_stage"] = s // 10
        df["px_s_stage"] = s % 10
    if "bl_bits" in df.columns:
        b = df["bl_bits"].fillna(0).round().astype("int64")
        df["bl_l_on"] = (b & 1) != 0
        df["bl_l_tap"] = (b & 2) != 0
        df["bl_s_on"] = (b & 4) != 0
        df["bl_s_tap"] = (b & 8) != 0
    if "bl_bars" in df.columns:
        b = df["bl_bars"].fillna(0).round().astype("int64")
        # stored as (bar+1) per slot so 0 means "none" and the packing never goes negative
        df["bl_l_bar"] = (b // 1_000_000).map(lambda x: None if x == 0 else x - 1)
        df["bl_s_bar"] = (b % 1_000_000).map(lambda x: None if x == 0 else x - 1)
    # TradingView leaves the final (still-forming) bar's plotted series blank, so its packed
    # columns read as 0 and would look like a real "nothing armed / no leg live". Mark it and
    # skip it, rather than reporting a phantom mismatch on the last row.
    marker = "px_dec_bits" if "px_dec_bits" in df.columns else "bl_bits"
    df["_px_present"] = df[marker].notna()
    return df


# What gets diffed. The B-LEG's own arm + band prices, the shared trade stream, and the A+
# stages (the B leg arms off the A+ sequence's death, so an A+ stage drift is where a B-LEG
# mismatch USUALLY originates — diffing it turns "a trade differs" into "the upstream moved").
_BOOL = ["px_long_armed", "px_short_armed", "bl_l_on", "bl_l_tap", "bl_s_on", "bl_s_tap"]
_INT = ["px_l_stage", "px_s_stage", "px_entry_dir", "bl_l_bar", "bl_s_bar"]
# The two _INT columns that hold a BAR INDEX rather than a value — see _bar_index_offset.
_BAR_COLS = ("bl_l_bar", "bl_s_bar")


def _bar_index_offset(ex: pd.DataFrame, bleg_states) -> Tuple[int, int]:
    """Measure the chart-origin offset between Pine's bar index and Python's.

    Pine's `bar_index` counts from the first bar the CHART loaded; the Python tracker
    counts from the first row of the EXPORT. When TradingView exports its whole loaded
    history the two origins coincide and the raw indices match — which is why every run
    before 2026-07-31 was green without this. When the export is a SUBSET (the normal
    case once a chart has scrolled back, and what a 6k-bar export off a 21k-bar chart
    is), every `bl_*_bar` is off by one constant, and diffing raw reports a mismatch on
    every armed bar while the logic is bar-for-bar identical.

    So the origin is MEASURED, never assumed: the most common (pine - python) difference
    over every bar where both sides name an armed bar. This normalises a coordinate
    system; it does not soften the check. A real drift in WHICH bar armed produces a
    MINORITY offset, so those bars still fail the diff. Returns (offset, stray_count) —
    stray > 0 means more than one offset was seen, which is itself the drift signal.
    """
    seen: Counter = Counter()
    present = ex["_px_present"].tolist()
    cols = {c: ex[c].tolist() for c in _BAR_COLS if c in ex.columns}
    n = min(len(present), len(bleg_states))
    for i in range(n):
        if not present[i]:
            continue
        st = bleg_states[i]
        for col, py_attr in (("bl_l_bar", "l_bar"), ("bl_s_bar", "s_bar")):
            if col not in cols:
                continue
            a, b = getattr(st, py_attr), cols[col][i]
            if a is None or b is None or pd.isna(b):
                continue
            seen[int(b) - int(a)] += 1
    if not seen:
        return 0, 0
    offset, hits = seen.most_common(1)[0]
    return offset, sum(seen.values()) - hits
_PRICE = ["px_edge", "px_stop", "px_entry_price", "px_tp1", "px_tp2",
          "px_exit_tp1", "px_exit_tp2", "px_exit_run",
          "bl_l_top", "bl_l_bot", "bl_l_inv", "bl_l_tgt",
          "bl_s_top", "bl_s_bot", "bl_s_inv", "bl_s_tgt"]


def _py_row(dec, bleg) -> dict:
    """One bar of the Python side, in the export's column names."""
    # `Fill.dir` is the signed direction; `Fill.qty` is NOT signed. Reading qty's sign here
    # made every short look like a long — caught by the first real export, and NOT by the
    # round-trip test, because the test's encoder had the identical bug so the two agreed.
    entry_dir = next((f.dir for f in dec.fills if f.kind == "entry"), 0)
    exits = {"px_exit_tp1": None, "px_exit_tp2": None, "px_exit_run": None}
    for f in dec.fills:
        if f.kind != "exit":
            continue
        oid = f.order_id or ""
        if "TP1" in oid:
            exits["px_exit_tp1"] = f.price
        elif "TP2" in oid:
            exits["px_exit_tp2"] = f.price
        else:
            exits["px_exit_run"] = f.price
    edge = dec.long_edge if dec.long_armed else (dec.short_edge if dec.short_armed else None)
    return dict(
        px_long_armed=bool(dec.long_armed), px_short_armed=bool(dec.short_armed),
        px_entry_dir=entry_dir, px_l_stage=dec.l_stage, px_s_stage=dec.s_stage,
        px_edge=edge, px_stop=dec.stop,
        px_entry_price=next((f.price for f in dec.fills if f.kind == "entry"), None),
        px_tp1=dec.tp1, px_tp2=dec.tp2,
        px_closed_r=dec.closed_r,
        bl_l_on=bleg.l_on, bl_l_tap=bleg.l_tap, bl_l_bar=bleg.l_bar,
        bl_s_on=bleg.s_on, bl_s_tap=bleg.s_tap, bl_s_bar=bleg.s_bar,
        bl_l_top=bleg.l_top, bl_l_bot=bleg.l_bot, bl_l_inv=bleg.l_inv, bl_l_tgt=bleg.l_tgt,
        bl_s_top=bleg.s_top, bl_s_bot=bleg.s_bot, bl_s_inv=bleg.s_inv, bl_s_tgt=bleg.s_tgt,
        **exits,
    )


def compare(df: pd.DataFrame, decisions, bleg_states, warmup: int = 0,
            price_tol: float = 0.01, r_tol: float = 0.02,
            tail: int = 0, tail_is_default: bool = True) -> List[str]:
    """Diff the Pine export against the Python stream. Returns the mismatch list (empty
    = exit 0). Bars are aligned by POSITION — `run(bars, warmup=0)` keeps one decision per
    CSV row, and `warmup` only suppresses REPORTING, so a cold-start engine cannot mask a
    late drift by shifting the alignment.

    `tail` drops the final N bars, and it is the same idea as `warmup` at the other end of the
    export: the structure engine's swings come from `ta.pivothigh(high, majorLength, majorLength)`,
    which needs `majorLength` bars of LOOKAHEAD, so the last `majorLength` bars of any export taken
    from a live chart cannot have confirmed pivots yet. Pine and Python are entitled to disagree
    there and the disagreement means nothing.

    🔴 **This is a REPORTING window, never a shortened replay** — every bar is still stepped, so a
    real drift that starts inside the tail and would have persisted still shows on the next export.
    ⚠ **It is announced on every run, including a clean one.** A silently-trimmed comparison that
    prints PARITY OK is a gate claiming ground it never covered.
    """
    ex = _expand(df)
    msgs: List[str] = []
    bar_offset, strays = _bar_index_offset(ex, bleg_states)
    if bar_offset:
        print(f"NOTE: the export starts at Pine bar_index {bar_offset} (a partial chart export), "
              f"so bl_l_bar/bl_s_bar are compared relative to that origin.")
    if strays:
        print(f"WARNING: {strays} armed-bar reading(s) do not sit at the measured offset — "
              f"that is real drift, not the origin, and they are reported below.")
    n = min(len(ex), len(decisions), len(bleg_states))
    tail = max(0, int(tail))
    if tail:
        why = ("the export's final calendar day, whose daily liquidity levels cannot have settled, "
               "and it covers the unconfirmed swings too" if tail_is_default
               else "asked for on the command line")
        print(f"NOTE: the last {tail} bars are NOT compared — they are {why}. "
              f"Pass --tail 0 to diff them anyway.")
    # ⚠ REFUSE rather than clamp. Clamping to `max(warmup, n - tail)` reads as safer and is not:
    # it turns an over-wide tail into an empty loop and a confident PARITY OK over zero bars.
    # A+'s gate shipped that bug for one afternoon; this is the same guard, not a second one.
    if n - tail <= warmup:
        raise NothingToCompare(
            f"warmup {warmup} + tail {tail} leaves no bars of the {n} in this export to diff. "
            f"Lower one of them, or export more history.")
    n -= tail
    for i in range(warmup, n):
        row = ex.iloc[i]
        if not row["_px_present"]:
            continue
        py = _py_row(decisions[i], bleg_states[i])
        when = pd.to_datetime(row["time"], unit="s") if "time" in ex.columns else i
        for col in _BOOL:
            if col not in ex.columns:
                continue
            if bool(row[col]) != bool(py[col]):
                msgs.append(f"bar {i} {when} {col}: py={py[col]} pine={row[col]}")
        for col in _INT:
            if col not in ex.columns:
                continue
            a, b = py[col], row[col]
            if (a is None) != (b is None or pd.isna(b)):
                msgs.append(f"bar {i} {when} {col}: py={a} pine={b}")
            elif a is not None and b is not None and not pd.isna(b):
                # a bar index is reported in the EXPORT's coordinates, so it reads the same
                # as every other "bar N" in this output whether or not the chart was partial
                pine = int(b) - (bar_offset if col in _BAR_COLS else 0)
                if int(a) != pine:
                    msgs.append(f"bar {i} {when} {col}: py={a} pine={pine}")
        for col in _PRICE:
            if col not in ex.columns:
                continue
            a, b = py[col], row[col]
            b = None if b is None or pd.isna(b) else float(b)
            if (a is None) != (b is None):
                msgs.append(f"bar {i} {when} {col}: py={a} pine={b}")
            elif a is not None and abs(a - b) > price_tol:
                msgs.append(f"bar {i} {when} {col}: py={a} pine={b}")
        if "px_closed_r" in ex.columns:
            a = py["px_closed_r"]
            b = row["px_closed_r"]
            b = None if b is None or pd.isna(b) else float(b)
            if (a is None) != (b is None):
                msgs.append(f"bar {i} {when} px_closed_r: py={a} pine={b}")
            elif a is not None and abs(a - b) > r_tol:
                msgs.append(f"bar {i} {when} px_closed_r: py={a} pine={b}")
        if msgs:
            break        # first divergence is the only useful one — everything after it is downstream
    return msgs


def run_parity(path, warmup: int = 0, price_tol: float = 0.01, r_tol: float = 0.02,
               base_config: Optional[BLegConfig] = None,
               eq_exempt: Optional[bool] = None,
               tail: Optional[int] = None) -> List[str]:
    """Load, configure, replay, diff. Returns the mismatch list (empty = exit 0).

    ⚠ The replay is always the FULL export — `tail` narrows only what is COMPARED, so the engine
    state carried into the compared bars is the state the whole export produced.
    """
    df = load_export(path)
    cfg = config_from_export(df, base_config)
    bars = df[["open", "high", "low", "close"]].copy()
    # The EQ/FVG coupling comes off the export, not off this fork's pin — the two Pines genuinely
    # disagree about it (A+ ships it on, this fork off), so reading it is what makes the agreement
    # measured rather than two defaults that happen to line up. Shared decoder, same as cfg_*.
    eng = _engine_config_from_export(df, MpcBLegStrategy.engine_config(), eq_exempt)
    # keep all bars aligned to CSV rows
    strat = MpcBLegStrategy(cfg).run(bars, engine_config=eng, warmup=0)
    tail_is_default = tail is None
    if tail_is_default:
        tail = unsettled_tail(df, eng)
    return compare(df, strat.decisions, strat.bleg_states, warmup, price_tol, r_tol,
                   tail, tail_is_default)


def main() -> int:
    ap = argparse.ArgumentParser(description="B-LEG strategy logic-parity check (Python vs Pine export)")
    ap.add_argument("csv", help="mpc_b_leg_strategy_export.pine chart-data CSV")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars (engine cold-start)")
    ap.add_argument("--price-tol", type=float, default=0.01, help="price match tolerance (default 1 tick)")
    ap.add_argument("--r-tol", type=float, default=0.02, help="R match tolerance")
    ap.add_argument("--eq-exempt", choices=("on", "off"), default=None,
                    help="state whether the chart ran `eqExemptFvg` (a gap on an EQ level "
                         "surviving the FVG cap). Only needed for an export with no "
                         "cfg_eq_exempt column — i.e. taken before 2026-08-06.")
    ap.add_argument("--tail", type=int, default=None,
                    help=f"skip the last N bars (default {UNCONFIRMED_TAIL} = the structure "
                         f"pivot's lookahead; an export off a LIVE chart cannot have confirmed "
                         f"swings there). 0 diffs them anyway.")
    ap.add_argument("--allow-fast-timeframe", action="store_true",
                    help="diff an export from a chart faster than 15m anyway. Only correct "
                         "if the inherited engine pins have been changed to match what that "
                         "chart's Pine ran.")
    a = ap.parse_args()

    # 🔴 THIS FORK INHERITS THE PARENT'S 15m GAP PINS, so it inherits the parent's exposure:
    # below 15m the Pine runs a different gap set from the one the Python replays, and any
    # diff would be comparing two differently-configured runs. Refused, never reported as a
    # mismatch — see the long note in `mpc_sos_fade/tools/compare_strategy.py`.
    # ⚠ MEASURED 2026-08-23, and the measurement cuts the other way here: the 20,573-bar M5
    # export this bot went green on was ALSO green with the sub-15m pair, so the difference
    # provably decided nothing on that run — a B-LEG entry rests on the frozen band, not on a
    # gap. **That is why the green stands and why this check still had to be added**: "it did
    # not bite this time" is a fact about one export, and the next one gets no such promise.
    _tfDf = load_export(Path(a.csv))
    _tf = None if a.allow_fast_timeframe else timeframe_refusal(_tfDf)
    if _tf is not None:
        print(f"CANNOT DIFF - {_tf.replace('mpc_strategy_export.pine', 'mpc_b_leg_strategy_export.pine')}")
        return 2

    eq = None if a.eq_exempt is None else (a.eq_exempt == "on")
    try:
        msgs = run_parity(Path(a.csv), a.warmup, a.price_tol, a.r_tol, eq_exempt=eq, tail=a.tail)
    except EqExemptUnknown as exc:
        print(f"CANNOT DIFF — {exc}")
        return 2
    except NothingToCompare as exc:
        print(f"CANNOT DIFF — {exc}")
        return 2
    if not msgs:
        # The window is stated in the SUCCESS line, not only in the note above it. A reader who
        # scrolls to the verdict must not be able to read "every bar" as covering bars nobody
        # compared — that is the shape of every over-claiming green this repo has recorded.
        # ⚠ `a.tail` is None when it was DERIVED from the export, so the count is recomputed here
        # rather than read off the args — and the reason no longer says "swings", which stopped
        # being the whole story when the tail became the final calendar day.
        _n = len(_tfDf)
        _tail = unsettled_tail(_tfDf) if a.tail is None else max(0, int(a.tail))
        span = f"from {a.warmup} on"
        if _tail > 0:
            span = (f"from {a.warmup} to the last {_tail} (unsettled tail, not compared)")
        print(f"PARITY OK — Python == Pine on every bar {span} "
              f"({max(0, _n - _tail - a.warmup)} bars compared).")
        return 0
    print("PARITY MISMATCH — first diverging bar:")
    for m in msgs[:10]:
        print(" ", m)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
