#!/usr/bin/env python3
"""killzone_reversal.py — does price TURN INSIDE a kill zone, and does the turn hold?

**This is not the question `killzone_profile.py` answers, and the difference is why that
tool could not see this pattern at all.**

  killzone_profile.py   measures the leg from 03:00 NY to the window's **CLOSE**, then
                        looks FORWARD from the window. A turn inside the zone is part of
                        its "leg into the window" — it is averaged INTO the thing being
                        faded, so it is structurally invisible.
  this tool             measures the leg that ends at the window's **OPEN**, then asks
                        what happened INSIDE the window: where the extreme printed, how
                        much came back, whether the zone closed against the leg.

Aaron's description, 2026-09-15: price is running in one direction, the zone's time
arrives, and price turns — "not sometimes it's not directly the candle after, it could be
within the zone. Somewhere within the zone." The turn is then either a short retrace that
resumes the original direction, or a turn that keeps going. **Both are measured, and kept
apart**, because a strategy that wants the first needs a fixed target and one that wants
the second needs a trail — and the mix decides which is even buildable.

⚠ **A turn inside a 30-60 minute window is NOT a finding on its own.** Price pulls back
inside nearly every window of the day; that is what price does. So every statistic here is
also computed for every OTHER window of the same LENGTH across the day, and a zone is only
interesting where it beats that distribution. Without the baseline this report is
astrology — the same reason the sibling tool carries one.

⚠ **Bars must be SMALLER than the zone.** The 11:45 zone is 30 minutes: on M15 that is two
candles and "where inside the zone did it turn" cannot be answered at all. Default is M5.
The bar count per zone is printed on every run so a too-coarse choice is visible rather
than silently averaged away.

⚠ **The measurement half reads a bar's high and low without knowing their ORDER**, so an
in-zone "turn" on a single bar may be the wick, not a sequence. That is honest for a
SHAPE statistic and dishonest for a trade, which is why the two trades priced here reuse
`killzone_profile._fade_trade` — one fill model, stop wins any ambiguous bar, and the
entry is delayed one bar behind its trigger (the order delay every fill model here is
built on).

Stdlib only, reads the cached broker bars off disk, touches no engine — the same
deliberate isolation the sibling tools use, so any edge it finds is an edge in the CLOCK
and cannot have been inherited from the structure stack.

Usage:
    python3 backtest/tools/killzone_reversal.py
    python3 backtest/tools/killzone_reversal.py --tf M1 --window 11:45-12:15
    python3 backtest/tools/killzone_reversal.py --start 2024-09-01        # the 2-year look
    python3 backtest/tools/killzone_reversal.py --out backtest/reports/kz_reversal
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.tools.killzone_profile import (  # noqa: E402
    DAY_END,
    DEFAULT_SERVER,
    FADE_EXIT,
    PRE_LEG_START,
    _fade_trade,
    _mean,
    _median,
    _pct,
    _slice,
    load_days,
    parse_window,
)

# The three kill zones, as the canonical engine defines them (engines/sessions/engine.py):
# 10:00-10:59, 11:45-12:14, 13:00-13:30 NY. Written here as half-open [start, end) spans,
# which is the same rule `_slice` applies, so these cover exactly the flagged bars.
KZ_WINDOWS = ("10:00-11:00", "11:45-12:15", "13:00-13:45")

# A day needs this FRACTION of its 03:00-17:00 bars to count. Derived from the timeframe
# rather than pinned: the sibling tool's flat `MIN_BARS_IN_DAY = 40` was calibrated on M15
# (56 bars in that span) and would wave through a two-thirds-empty M5 day, which is a half
# session measured as a whole one.
_MIN_DAY_COVERAGE = 0.70

# The baseline sweeps comparison windows across this span. It starts after PRE_LEG_START so
# every comparison window has a real leg in front of it, and ends early enough that the
# window plus its forward horizon still fit inside the day.
_BASE_FIRST = dt.time(4, 0)
_BASE_LAST = dt.time(15, 0)


def _tf_minutes(tf: str) -> int:
    t = tf.upper().strip()
    if t.startswith("M") and t[1:].isdigit():
        return int(t[1:])
    if t.startswith("H") and t[1:].isdigit():
        return 60 * int(t[1:])
    raise SystemExit(f"unrecognised timeframe {tf!r} — expected M1/M5/M15/M30/H1")


def _shift(t: dt.time, minutes: int) -> dt.time:
    total = t.hour * 60 + t.minute + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return dt.time(total // 60, total % 60)


def _span_minutes(a: dt.time, b: dt.time) -> int:
    return (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)


# ---------------------------------------------------------------------------
# days


def qualifying_days(days: dict, tf_min: int) -> list[tuple[dt.date, list, float]]:
    """(date, bars, ADR20) per usable weekday, ADR from PRIOR days only.

    Mirrors the ADR convention in `killzone_profile.profile_days` — 20-day mean of the
    03:00-17:00 range, at least 5 days of history, no lookahead. Kept local rather than
    imported because that one is interleaved with that tool's own per-day filters; the
    definition is identical and is cross-checked in `--verify`.
    """
    need = int(_MIN_DAY_COVERAGE * (_span_minutes(PRE_LEG_START, DAY_END) / tf_min))
    hist: list[float] = []
    out = []
    for date in sorted(days):
        if date.weekday() >= 5:
            continue
        bars = days[date]
        core = _slice(bars, PRE_LEG_START, DAY_END)
        if len(core) < need:
            continue
        adr = statistics.fmean(hist[-20:]) if len(hist) >= 5 else None
        hist.append(max(b.high for b in core) - min(b.low for b in core))
        if adr and adr > 0:
            out.append((date, bars, adr))
    return out


# ---------------------------------------------------------------------------
# the measurement


def measure_zone(
    date: dt.date,
    bars: list,
    adr: float,
    ws: dt.time,
    we: dt.time,
    lookback_min: int,
    min_leg_adr: float,
    target_r: float,
) -> dict | None:
    """One row: the leg into the zone, the turn inside it, and what followed."""
    zb = _slice(bars, ws, we)
    if len(zb) < 2:
        return None
    ap = _slice(bars, _shift(ws, -lookback_min), ws)
    if not ap:
        return None

    zone_open = zb[0].open
    leg = zone_open - ap[0].open
    leg_adr = abs(leg) / adr
    if leg_adr < min_leg_adr or leg == 0:
        return None
    d = 1 if leg > 0 else -1

    zone_high = max(b.high for b in zb)
    zone_low = min(b.low for b in zb)
    zone_close = zb[-1].close

    # The extreme in the LEG's direction is the candidate turning point.
    if d > 0:
        ei = max(range(len(zb)), key=lambda i: zb[i].high)
        ext = zb[ei].high
        counter = ext - min(b.low for b in zb[ei:])
    else:
        ei = min(range(len(zb)), key=lambda i: zb[i].low)
        ext = zb[ei].low
        counter = max(b.high for b in zb[ei:]) - ext
    counter_extreme = ext - counter * d

    row = {
        "date": date.isoformat(),
        "year": date.year,
        "bars_in_zone": len(zb),
        "leg_dir": d,
        "leg_adr": leg_adr,
        "ext_adr": (ext - zone_open) * d / adr,
        "counter_adr": counter / adr,
        "counter_pct_leg": counter / abs(leg),
        "gave_back_half": counter >= 0.5 * abs(leg),
        "gave_back_all": counter >= abs(leg),
        "closed_against": (zone_close - zone_open) * d < 0,
        # 0.0 = the extreme printed on the zone's first bar, 1.0 = on its last.
        "turn_pos": ei / (len(zb) - 1),
        "turn_early": ei / (len(zb) - 1) <= 1 / 3,
        "turn_late": ei / (len(zb) - 1) >= 2 / 3,
    }

    # --- after the zone, which happened FIRST — measured at EQUAL DISTANCE both ways.
    #
    # 🔴 The obvious version of this test is rigged and it was written that way first:
    # comparing "price retook the zone's extreme" against "price ran past the in-zone
    # counter-extreme" puts the two thresholds at DIFFERENT distances from the zone's
    # close, so after a deep turn the counter side sits inches away and wins ~62% of the
    # time on geometry alone. It looked like reversal persistence. It was a ruler.
    #
    # The fair question uses one distance for both sides: taking the zone's extreme as the
    # stop, does the turn pay ONE unit of that same risk before the extreme is retaken?
    # A coin flip here is 50%, and that is the number to read.
    risk = abs(zone_close - ext)
    outcome = "no_risk"
    if risk > 0:
        target = zone_close - d * risk
        outcome = "neither"
        for b in _slice(bars, we, DAY_END):
            hit_stop = b.high >= ext if d > 0 else b.low <= ext
            hit_target = b.low <= target if d > 0 else b.high >= target
            if hit_stop and hit_target:
                # One bar holding both says nothing about their order. Naming it beats
                # picking the flattering one.
                outcome = "ambiguous"
                break
            if hit_stop:
                outcome = "leg_resumed"
                break
            if hit_target:
                outcome = "reversal_paid"
                break
    row["after"] = outcome
    row["after_reversal_paid"] = outcome == "reversal_paid"
    row["after_leg_resumed"] = outcome == "leg_resumed"
    row["risk_adr"] = risk / adr

    # --- excursions from the zone's close, stated from the TURN's point of view
    for h in (1, 2, 4):
        fwd = _slice(bars, we, min(_shift(we, 60 * h), DAY_END))
        if not fwd:
            row[f"turn_mfe_{h}h_adr"] = None
            row[f"turn_mae_{h}h_adr"] = None
            continue
        hi = max(b.high for b in fwd)
        lo = min(b.low for b in fwd)
        row[f"turn_mfe_{h}h_adr"] = ((zone_close - lo) if d > 0 else (hi - zone_close)) / adr
        row[f"turn_mae_{h}h_adr"] = ((hi - zone_close) if d > 0 else (zone_close - lo)) / adr

    # --- trade A: take the turn at the zone's close, stop beyond the zone's extreme
    a = _fade_trade(bars, we, zone_close, zone_high, zone_low, d, target_r)
    row.update({"zc_dir": a["fade_dir"], "zc_r": a["fade_r"], "zc_outcome": a["fade_outcome"]})

    # --- trade B: take it INSIDE the zone, on the first close back through the zone's open
    row.update(_reclaim_trade(bars, zb, zone_open, d, target_r))
    return row


def _reclaim_trade(bars: list, zb: list, zone_open: float, d: int, target_r: float) -> dict:
    """Enter inside the zone: first bar that CLOSES back through the zone's open against
    the leg. Stop at the running extreme as it stood on that bar — not the whole zone's,
    which would be lookahead.

    Filled one bar behind the trigger, so the trigger bar's own wick can neither stop nor
    target it. A trigger on the zone's last bar fills on the first bar after the zone,
    which is correct rather than special-cased: the rule does not know it is at an edge.
    """
    blank = {"rc_dir": 0, "rc_r": None, "rc_outcome": "", "rc_pos": None}
    run_high = float("-inf")
    run_low = float("inf")
    for i, b in enumerate(zb):
        run_high = max(run_high, b.high)
        run_low = min(run_low, b.low)
        back_through = b.close < zone_open if d > 0 else b.close > zone_open
        if not back_through:
            continue
        nxt = next((x for x in bars if x.t > b.t), None)
        if nxt is None:
            return blank
        out = _fade_trade(bars, nxt.t, b.close, run_high, run_low, d, target_r)
        return {
            "rc_dir": out["fade_dir"],
            "rc_r": out["fade_r"],
            "rc_outcome": out["fade_outcome"],
            "rc_pos": i / (len(zb) - 1),
        }
    return blank


def build_rows(days_list, ws, we, lookback_min, min_leg_adr, target_r) -> list[dict]:
    rows = []
    for date, bars, adr in days_list:
        row = measure_zone(date, bars, adr, ws, we, lookback_min, min_leg_adr, target_r)
        if row:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# reporting


def _trade_line(label: str, rows: list[dict], key: str, floor: int = 30) -> None:
    live = [r for r in rows if r.get(key) is not None]
    if len(live) < floor:
        print(f"  {label:<34}{len(live):>7}   (under {floor} — not reported)")
        return
    wins = [r for r in live if r[key] > 0]
    print(
        f"  {label:<34}{len(live):>7}{100 * len(wins) / len(live):>8.1f}%"
        f"{statistics.fmean(r[key] for r in live):>+9.3f}{sum(r[key] for r in live):>+9.1f}"
    )


def report_zone(rows: list[dict], win: str, symbol: str, tf: str, target_r: float) -> None:
    ups = sum(1 for r in rows if r["leg_dir"] > 0)
    print(f"\n{'=' * 88}")
    print(
        f"  {symbol} {tf} — ZONE {win} New York — {rows[0]['bars_in_zone']} bars per zone — "
        f"{len(rows)} qualifying days"
    )
    print(f"  {rows[0]['date']} → {rows[-1]['date']}")
    print(f"{'=' * 88}")
    print(
        f"\n  leg into the zone    up {100 * ups / len(rows):.1f}%   "
        f"down {100 * (len(rows) - ups) / len(rows):.1f}%   "
        f"median size {_median(rows, 'leg_adr'):.1%} of ADR20"
    )

    print("\nDID IT TURN INSIDE THE ZONE")
    print(
        f"  pushed on, in the leg's direction   {_mean(rows, 'ext_adr'):>6.1%} ADR20  "
        f"(median {_median(rows, 'ext_adr'):.1%})"
    )
    print(
        f"  came back against the leg           {_mean(rows, 'counter_adr'):>6.1%} ADR20  "
        f"(median {_median(rows, 'counter_adr'):.1%})"
    )
    print(f"  gave back half the leg or more      {_pct(rows, 'gave_back_half'):>6.1f}% of days")
    print(f"  gave back the WHOLE leg or more     {_pct(rows, 'gave_back_all'):>6.1f}% of days")
    print(f"  zone CLOSED against the leg         {_pct(rows, 'closed_against'):>6.1f}% of days")
    print(
        f"  the extreme printed                 {_mean(rows, 'turn_pos'):>6.0%} through the zone  "
        f"(first third {_pct(rows, 'turn_early'):.0f}%, last third {_pct(rows, 'turn_late'):.0f}%)"
    )

    print("\nAFTER THE ZONE — WHICH HAPPENED FIRST, at equal distance both ways")
    print("  (the turn paying one unit of risk, vs the zone's extreme being retaken)")
    counts = defaultdict(int)
    for r in rows:
        counts[r["after"]] += 1
    labels = {
        "reversal_paid": "the turn paid 1x risk first",
        "leg_resumed": "the leg resumed first",
        "neither": "neither, by 17:00",
        "ambiguous": "one bar held both — unknowable",
        "no_risk": "no measurable risk distance",
    }
    for key in ("reversal_paid", "leg_resumed", "neither", "ambiguous", "no_risk"):
        n = counts[key]
        if n:
            print(f"  {labels[key]:<36}{100 * n / len(rows):>6.1f}%  ({n})")
    print(
        f"\n  reversal's reach, from the zone's close   "
        f"+2h {_mean(rows, 'turn_mfe_2h_adr'):.1%} ADR for / "
        f"{_mean(rows, 'turn_mae_2h_adr'):.1%} against"
    )

    print(
        f"\nTRADE THE TURN — against the leg, stop beyond the zone's extreme, "
        f"{target_r:g}R, flat {FADE_EXIT:%H:%M}"
    )
    print(f"  {'entry':<34}{'trades':>7}{'win%':>8}{'expR':>9}{'totR':>9}")
    _trade_line("at the zone's close", rows, "zc_r")
    _trade_line("on a reclaim inside the zone", rows, "rc_r")

    big = sorted(rows, key=lambda r: r["leg_adr"])
    cut = len(big) // 4
    print("\n  the same two, split by how hard price was running into the zone")
    _trade_line("zone close — smallest quarter", big[:cut], "zc_r")
    _trade_line("zone close — biggest quarter", big[-cut:], "zc_r")
    _trade_line("reclaim — smallest quarter", big[:cut], "rc_r")
    _trade_line("reclaim — biggest quarter", big[-cut:], "rc_r")

    print("\nBY YEAR")
    print(
        f"  {'year':<6}{'days':>6}{'gaveBack50%':>13}{'closedAgnst':>13}"
        f"{'revPaid%':>10}{'zcExpR':>9}{'rcExpR':>9}"
    )
    years = defaultdict(list)
    for r in rows:
        years[r["year"]].append(r)
    for y in sorted(years):
        g = years[y]
        zc = [r for r in g if r["zc_r"] is not None]
        rc = [r for r in g if r["rc_r"] is not None]
        zc_e = statistics.fmean(r["zc_r"] for r in zc) if zc else float("nan")
        rc_e = statistics.fmean(r["rc_r"] for r in rc) if rc else float("nan")
        print(
            f"  {y:<6}{len(g):>6}{_pct(g, 'gave_back_half'):>12.1f}%"
            f"{_pct(g, 'closed_against'):>12.1f}%{_pct(g, 'after_reversal_paid'):>9.1f}%"
            f"{zc_e:>+9.3f}{rc_e:>+9.3f}"
        )


def report_baseline(base: list[dict], marks: set[str]) -> None:
    print(f"\n{'=' * 88}")
    print("  EVERY WINDOW OF THE DAY, SAME LENGTH — the base rate a zone has to beat")
    print(f"{'=' * 88}")
    print(
        f"  {'window':<14}{'days':>6}{'gaveBack50%':>13}{'closedAgnst':>13}"
        f"{'revPaid%':>10}{'zcExpR':>9}{'rcExpR':>9}"
    )
    for b in base:
        mark = "   <<< KILL ZONE" if b["window"] in marks else ""
        print(
            f"  {b['window']:<14}{b['days']:>6}{b['gave_back_half']:>12.1f}%"
            f"{b['closed_against']:>12.1f}%{b['rev_paid']:>9.1f}%"
            f"{b['zc_exp']:>+9.3f}{b['rc_exp']:>+9.3f}{mark}"
        )
    zc = [b["zc_exp"] for b in base if b["zc_exp"] == b["zc_exp"]]
    rc = [b["rc_exp"] for b in base if b["rc_exp"] == b["rc_exp"]]
    if zc and rc:
        print(
            f"\n  across all {len(base)} windows: zone-close entry median "
            f"{statistics.median(zc):+.3f}R, reclaim median {statistics.median(rc):+.3f}R"
        )


def sweep_baseline(days_list, length_min, lookback_min, min_leg_adr, target_r, step) -> list[dict]:
    """The same measurement on every same-length window of the day. This is the whole
    defence against reporting that price wiggles."""
    out = []
    minute = _BASE_FIRST.hour * 60
    last = _BASE_LAST.hour * 60
    while minute <= last:
        ws = dt.time(minute // 60, minute % 60)
        we = _shift(ws, length_min)
        minute += step
        if _span_minutes(we, DAY_END) < 60:
            continue
        rows = build_rows(days_list, ws, we, lookback_min, min_leg_adr, target_r)
        if len(rows) < 100:
            continue
        zc = [r["zc_r"] for r in rows if r["zc_r"] is not None]
        rc = [r["rc_r"] for r in rows if r["rc_r"] is not None]
        out.append(
            {
                "window": f"{ws:%H:%M}-{we:%H:%M}",
                "days": len(rows),
                "gave_back_half": _pct(rows, "gave_back_half"),
                "closed_against": _pct(rows, "closed_against"),
                "rev_paid": _pct(rows, "after_reversal_paid"),
                "zc_exp": statistics.fmean(zc) if zc else float("nan"),
                "rc_exp": statistics.fmean(rc) if len(rc) >= 30 else float("nan"),
            }
        )
    return out


# ---------------------------------------------------------------------------


def scalp_rows(days_list, ws, we, lookback_min: int) -> list[dict]:
    """The trade Aaron actually described (2026-09-15): in at the zone's open, OUT at the
    zone's close. A time exit, no target, no stop — the hold is the zone.

    🔴 **None of the other measurements in this file price this trade**, and the difference is
    not a detail. They stop at the zone's extreme, target 2R, and stay in until 16:00; this
    one is flat inside the hour and cannot be stopped out, so its costs are a rounding error
    against a $10 move where they were a third of the edge against a tight stop. **A null on
    one exit says nothing about another.**

    Reports the move in DOLLARS as well as ADR, because a scalp is judged against the spread
    and the spread is quoted in dollars. ⚠ Gold's "100 pips" is read here as **$10.00** — one
    pip = $0.10 on `XAUUSD` — and every figure names its unit so the reading is checkable.
    """
    out = []
    for date, bars, adr in days_list:
        zb = _slice(bars, ws, we)
        if len(zb) < 2:
            continue
        ap = _slice(bars, _shift(ws, -lookback_min), ws)
        if not ap:
            continue
        o = zb[0].open
        c = zb[-1].close
        hi = max(b.high for b in zb)
        lo = min(b.low for b in zb)
        leg = o - ap[0].open
        d = 1 if leg > 0 else (-1 if leg < 0 else 0)
        out.append(
            {
                "date": date.isoformat(),
                "year": date.year,
                "adr": adr,
                "leg_dir": d,
                "open_usd": o,
                "range_usd": hi - lo,
                "move_usd": c - o,
                "reach_usd": max(hi - o, o - lo),
                # What each direction rule collects, held open-to-close of the zone.
                "fade_usd": -(c - o) * d if d else None,
                "follow_usd": (c - o) * d if d else None,
                # The ceilings: perfect direction, and perfect direction plus perfect timing.
                "perfect_usd": abs(c - o),
                "range_ge_10": (hi - lo) >= 10.0,
                "move_ge_10": abs(c - o) >= 10.0,
            }
        )
    return out


def report_scalp(rows: list[dict], win: str, lookback_min: int) -> None:
    n = len(rows)
    print(f"\n{'=' * 96}")
    print(f"  SCALP THE ZONE — in at {win.split('-')[0]} NY, OUT at {win.split('-')[1]}, {n} days")
    print(f"{'=' * 96}")
    print("\n  WHAT IS ON THE TABLE  (gold dollars; 100 pips = $10.00)")
    print(
        f"    the zone's range            median ${_median(rows, 'range_usd'):.2f}   "
        f"mean ${_mean(rows, 'range_usd'):.2f}"
    )
    print(
        f"    open-to-close move          median ${statistics.median(abs(r['move_usd']) for r in rows):.2f}   "
        f"mean ${_mean(rows, 'perfect_usd'):.2f}"
    )
    print(
        f"    reach from the open         median ${_median(rows, 'reach_usd'):.2f}   "
        f"mean ${_mean(rows, 'reach_usd'):.2f}"
    )
    print(f"    range was $10 or more       {_pct(rows, 'range_ge_10'):.1f}% of days")
    print(f"    open-to-close $10 or more   {_pct(rows, 'move_ge_10'):.1f}% of days")

    print(f"\n  WHAT A DIRECTION RULE COLLECTS  (leg = the {lookback_min}min run-up into the zone)")
    print(f"    {'rule':<34}{'days':>7}{'win%':>8}{'mean$':>10}{'median$':>10}{'total$':>12}")
    for label, key in (
        ("fade the leg, out at the close", "fade_usd"),
        ("follow the leg, out at the close", "follow_usd"),
    ):
        live = [r for r in rows if r.get(key) is not None]
        wins = [r for r in live if r[key] > 0]
        print(
            f"    {label:<34}{len(live):>7}{100 * len(wins) / len(live):>7.1f}%"
            f"{_mean(live, key):>+10.2f}{_median(live, key):>+10.2f}"
            f"{sum(r[key] for r in live):>+12.0f}"
        )
    print(
        f"    {'KNOWING the direction (ceiling)':<34}{n:>7}{100.0:>7.1f}%"
        f"{_mean(rows, 'perfect_usd'):>+10.2f}{_median(rows, 'perfect_usd'):>+10.2f}"
        f"{sum(r['perfect_usd'] for r in rows):>+12.0f}"
    )


def direction_rules(days_list, ws, we, lookback_min: int) -> dict[str, list[dict]]:
    """Hunt for a rule that knows WHICH WAY to take the zone's scalp.

    🔴 **This is the only question left and the scalp measurement is what reduced it to
    one.** Held open-to-close of the 10:00 zone, knowing the direction is worth **+$5.81 a
    day** on gold while the 2-hour leg predicts it at **±$0.27** — so the move is real, the
    cost is a rounding error against it, and 100% of the problem is the sign.

    Every rule here is pure clock-and-price on purpose: no engine, so a negative cannot be
    blamed on the structure stack and a positive is a clean reason to then reach for one.
    ⚠ **Nine rules are tested and every one is reported, winners and losers.** A search
    reports its own width or it is not a search — and each is run against every hour of the
    day, because the control for "this rule makes money at 10:00" is the same rule at 11:00.
    """
    rules: dict[str, list[dict]] = defaultdict(list)
    for _date, bars, adr in days_list:
        zb = _slice(bars, ws, we)
        if len(zb) < 3:
            continue
        ap = _slice(bars, _shift(ws, -lookback_min), ws)
        pre30 = _slice(bars, _shift(ws, -30), ws)
        core_so_far = _slice(bars, PRE_LEG_START, ws)
        if not ap or not pre30 or len(core_so_far) < 3:
            continue

        z_open = zb[0].open
        z_close = zb[-1].close
        leg = z_open - ap[0].open
        d_leg = 1 if leg > 0 else (-1 if leg < 0 else 0)
        d_pre30 = 1 if pre30[-1].close > pre30[0].open else -1
        first = zb[0]
        d_first = 1 if first.close > first.open else (-1 if first.close < first.open else 0)

        # Where in the day's range so far is price standing as the zone opens?
        hi = max(b.high for b in core_so_far)
        lo = min(b.low for b in core_so_far)
        pos = (z_open - lo) / (hi - lo) if hi > lo else 0.5

        # Entry at the zone's open, or after its first bar has closed for rules that read it.
        e0, e1 = z_open, first.close

        def add(name, d, entry):
            if d:
                rules[name].append(
                    {"pnl": d * (z_close - entry), "adr": adr, "leg_adr": abs(leg) / adr}
                )

        add("follow the 2h leg", d_leg, e0)
        add("fade the 2h leg", -d_leg, e0)
        add("follow the last 30min", d_pre30, e0)
        add("fade the last 30min", -d_pre30, e0)
        add("follow the zone's 1st bar", d_first, e1)
        add("fade the zone's 1st bar", -d_first, e1)
        # Standing high in the day's range -> sell it; standing low -> buy it.
        add(
            "fade the day's range position",
            (-1 if pos > 0.7 else 1) if pos > 0.7 or pos < 0.3 else 0,
            e0,
        )
        add(
            "follow the day's range position",
            (1 if pos > 0.7 else -1) if pos > 0.7 or pos < 0.3 else 0,
            e0,
        )
        # Only when the run into the zone was unusually hard.
        if abs(leg) / adr >= 0.35:
            add("fade an overextended leg", -d_leg, e0)
    return rules


def report_direction(days_list, windows, lookback_min, step) -> None:
    """Each rule at the zone, beside the median of that same rule across every hour."""
    for win in windows:
        ws, we = parse_window(win)
        length = _span_minutes(ws, we)
        at_zone = direction_rules(days_list, ws, we, lookback_min)

        controls: dict[str, list[float]] = defaultdict(list)
        minute = _BASE_FIRST.hour * 60
        while minute <= _BASE_LAST.hour * 60:
            bws = dt.time(minute // 60, minute % 60)
            minute += max(step, 60)
            bwe = _shift(bws, length)
            if (bws, bwe) == (ws, we):
                continue
            for name, rows in direction_rules(days_list, bws, bwe, lookback_min).items():
                if len(rows) >= 100:
                    controls[name].append(statistics.fmean(r["pnl"] for r in rows))

        print(f"\n{'=' * 96}")
        print(f"  A DIRECTION RULE FOR {win} NY — in at the open, out at the close, $ per trade")
        print(f"{'=' * 96}")
        print(
            f"  {'rule':<32}{'days':>7}{'win%':>8}{'mean$':>9}{'total$':>10}"
            f"{'otherHrs$':>11}{'edge$':>8}"
        )
        for name in sorted(at_zone, key=lambda k: -statistics.fmean(r["pnl"] for r in at_zone[k])):
            rows = at_zone[name]
            if len(rows) < 100:
                continue
            mean = statistics.fmean(r["pnl"] for r in rows)
            wins = sum(1 for r in rows if r["pnl"] > 0)
            ctrl = statistics.median(controls[name]) if controls.get(name) else float("nan")
            print(
                f"  {name:<32}{len(rows):>7}{100 * wins / len(rows):>7.1f}%{mean:>+9.2f}"
                f"{sum(r['pnl'] for r in rows):>+10.0f}{ctrl:>+11.2f}{mean - ctrl:>+8.2f}"
            )
        print(
            "\n  'otherHrs$' is the SAME rule's median across every other hour — the control.\n"
            "  9 rules x every hour is a wide search: believe the 'edge$' column only where it\n"
            "  is large, and never a rule that only works at one hour by a few cents."
        )


def pivot_rate(days_list, ws, we, half_width: int) -> float:
    """Percent of days on which a LOCAL swing extreme formed inside the window.

    Direction-agnostic on purpose. "Price turns at these times" does not say which way, and
    a turn you can only name afterwards is still tradeable IF the turn itself is real: you
    wait for the confirmation and take whichever side it hands you. This is the honest
    version of the claim, so it gets measured on its own rather than folded into a fade.

    A pivot is a bar whose high is the highest — or low the lowest — of the `half_width`
    bars each side of it. ⚠ It is therefore only knowable `half_width` bars LATE, which is
    why this is a SHAPE statistic and no trade is priced off it here.
    """
    hits = 0
    counted = 0
    for _date, bars, _adr in days_list:
        core = _slice(bars, PRE_LEG_START, DAY_END)
        if len(core) < 2 * half_width + 3:
            continue
        counted += 1
        for i in range(half_width, len(core) - half_width):
            b = core[i]
            if not (ws <= b.t < we):
                continue
            around = core[i - half_width : i + half_width + 1]
            if b.high >= max(x.high for x in around) or b.low <= min(x.low for x in around):
                hits += 1
                break
    return 100 * hits / counted if counted else float("nan")


def grid_row(days_list, ws, we, lookback, min_leg, target_r) -> dict:
    rows = build_rows(days_list, ws, we, lookback, min_leg, target_r)
    if len(rows) < 100:
        return {}
    zc = [r["zc_r"] for r in rows if r["zc_r"] is not None]
    rc = [r["rc_r"] for r in rows if r["rc_r"] is not None]
    return {
        "days": len(rows),
        "gave_back_half": _pct(rows, "gave_back_half"),
        "rev_paid": _pct(rows, "after_reversal_paid"),
        "zc_exp": statistics.fmean(zc) if zc else float("nan"),
        "rc_exp": statistics.fmean(rc) if len(rc) >= 30 else float("nan"),
    }


def report_grid(days_list, windows, lookbacks, min_leg, target_r, step) -> None:
    """The decisive table: every zone at every definition of "running in one direction",
    each one printed BESIDE the all-day median for that same definition.

    🔴 **The lookback is a free parameter and a null result resting on one value of it is
    weak.** Checking Aaron's 2026-09-08 example by hand found the 120-minute leg calling the
    second zone an UP move while the day was plainly trending DOWN — the lookback had caught
    the first zone's bounce, not the trend. A real effect survives the yardstick changing;
    an artefact does not. ⚠ Every cell is compared to its OWN base rate, never to zero,
    and the cell count is printed so a lucky cell can be discounted as one of many.
    """
    print(f"\n\n{'=' * 96}")
    print("  EVERY ZONE, EVERY DEFINITION OF THE LEG — each beside the all-day median for that leg")
    print(f"{'=' * 96}")
    print(
        f"  {'zone':<14}{'leg':>6}{'days':>7}{'gaveBk50':>10}{'revPaid':>9}"
        f"{'zcExpR':>9}{'vs med':>9}{'rcExpR':>9}{'vs med':>9}"
    )
    cells = 0
    for lb in lookbacks:
        base = sweep_baseline(days_list, 60, lb, min_leg, target_r, step)
        med_zc = statistics.median([b["zc_exp"] for b in base if b["zc_exp"] == b["zc_exp"]])
        med_rc = statistics.median([b["rc_exp"] for b in base if b["rc_exp"] == b["rc_exp"]])
        for win in windows:
            ws, we = parse_window(win)
            g = grid_row(days_list, ws, we, lb, min_leg, target_r)
            if not g:
                continue
            cells += 1
            print(
                f"  {win:<14}{lb:>5}m{g['days']:>7}{g['gave_back_half']:>9.1f}%"
                f"{g['rev_paid']:>8.1f}%{g['zc_exp']:>+9.3f}{g['zc_exp'] - med_zc:>+9.3f}"
                f"{g['rc_exp']:>+9.3f}{g['rc_exp'] - med_rc:>+9.3f}"
            )
        print(
            f"  {'':<14}{'':>6}{'':>7}{'all-day median for this leg →':>36}{med_zc:>+9.3f}{'':>9}{med_rc:>+9.3f}"
        )
    print(f"\n  {cells} cells tested. A search this wide produces positive cells by construction —")
    print("  read the 'vs med' columns, and only believe one that holds across several legs.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M5", help="must be SMALLER than the zone (default M5)")
    ap.add_argument("--server", default=DEFAULT_SERVER, help="broker cache partition")
    ap.add_argument(
        "--window",
        action="append",
        help="NY zone under test, repeatable (default: all three kill zones)",
    )
    ap.add_argument("--start", help="YYYY-MM-DD, default = all cached history")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument(
        "--lookback",
        type=int,
        default=120,
        help="minutes of run-up that define the leg INTO the zone (default 120)",
    )
    ap.add_argument(
        "--min-leg",
        type=float,
        default=0.10,
        help="the leg must be at least this much ADR20 to count as 'running' (default 0.10)",
    )
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--baseline-step", type=int, default=30, help="minutes between base windows")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument(
        "--direction",
        action="store_true",
        help="search for a rule that predicts WHICH WAY to scalp the zone",
    )
    ap.add_argument(
        "--scalp",
        action="store_true",
        help="price the time-exit scalp: in at the zone's open, out at its close",
    )
    ap.add_argument(
        "--grid",
        help="comma-separated leg lookbacks in minutes, e.g. 30,60,120,240 — "
        "each zone priced at each, beside that leg's own all-day median",
    )
    ap.add_argument(
        "--pivots",
        type=int,
        metavar="HALFWIDTH",
        help="also report how often a local swing extreme forms inside each window, "
        "against every window of the day (bars each side, e.g. 6)",
    )
    ap.add_argument("--out", help="directory for the per-day CSVs")
    args = ap.parse_args()

    tf_min = _tf_minutes(args.tf)
    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None
    days = load_days(args.symbol, args.tf, start, end, server=args.server)
    days_list = qualifying_days(days, tf_min)
    if not days_list:
        raise SystemExit("no days survived the coverage filter — check the timeframe and range")

    windows = args.window or list(KZ_WINDOWS)
    print(
        f"\n{args.symbol} {args.tf} on {args.server} — {len(days_list)} usable days "
        f"({days_list[0][0]} → {days_list[-1][0]})"
    )
    print(
        f"leg = the {args.lookback}-minute run-up ending at the zone's OPEN, "
        f"at least {args.min_leg:.0%} of ADR20"
    )

    all_rows: dict[str, list[dict]] = {}
    for win in windows:
        ws, we = parse_window(win)
        if _span_minutes(ws, we) <= tf_min:
            raise SystemExit(f"{args.tf} bars are not smaller than the {win} zone — use a finer tf")
        rows = build_rows(days_list, ws, we, args.lookback, args.min_leg, args.target_r)
        if not rows:
            print(f"\n{win}: no qualifying days")
            continue
        all_rows[win] = rows
        report_zone(rows, win, args.symbol, args.tf, args.target_r)

    if not args.no_baseline and all_rows:
        lengths = {_span_minutes(*parse_window(w)) for w in all_rows}
        for length in sorted(lengths):
            marks = {w for w in all_rows if _span_minutes(*parse_window(w)) == length}
            base = sweep_baseline(
                days_list, length, args.lookback, args.min_leg, args.target_r, args.baseline_step
            )
            if base:
                print(f"\n\n### {length}-minute windows")
                report_baseline(base, marks)

    if args.scalp:
        for win in windows:
            ws, we = parse_window(win)
            rows = scalp_rows(days_list, ws, we, args.lookback)
            if rows:
                report_scalp(rows, win, args.lookback)
        # Every hour of the day, so "a $10 move is available here" can be checked against
        # whether a $10 move is available anywhere.
        length = _span_minutes(*parse_window(windows[0]))
        print(
            f"\n\n  EVERY {length}-MINUTE WINDOW — is the 10:00 hour bigger, or is gold just big?"
        )
        print(
            f"    {'window':<14}{'medRange$':>11}{'range≥$10':>11}{'fadeMean$':>11}{'followMean$':>13}"
        )
        minute = _BASE_FIRST.hour * 60
        while minute <= _BASE_LAST.hour * 60:
            ws = dt.time(minute // 60, minute % 60)
            we = _shift(ws, length)
            minute += max(args.baseline_step, 60)
            rows = scalp_rows(days_list, ws, we, args.lookback)
            if len(rows) < 100:
                continue
            fade = [r for r in rows if r["fade_usd"] is not None]
            mark = "   <<<" if f"{ws:%H:%M}-{we:%H:%M}" in set(windows) else ""
            print(
                f"    {f'{ws:%H:%M}-{we:%H:%M}':<14}{_median(rows, 'range_usd'):>10.2f}"
                f"{_pct(rows, 'range_ge_10'):>10.1f}%{_mean(fade, 'fade_usd'):>+11.2f}"
                f"{_mean(fade, 'follow_usd'):>+13.2f}{mark}"
            )

    if args.direction:
        report_direction(days_list, windows, args.lookback, max(args.baseline_step, 60))

    if args.grid:
        lookbacks = [int(x) for x in args.grid.split(",") if x.strip()]
        report_grid(
            days_list, windows, lookbacks, args.min_leg, args.target_r, max(args.baseline_step, 60)
        )

    if args.pivots:
        print(f"\n\n{'=' * 96}")
        print(
            f"  DOES A LOCAL TURN FORM HERE AT ALL — swing extreme with {args.pivots} bars "
            f"each side ({args.pivots * tf_min}min)"
        )
        print(f"{'=' * 96}")
        print("  direction-agnostic: a turn you can only name afterwards still counts here")
        print(f"\n  {'window':<16}{'pivot formed inside':>22}")
        length = _span_minutes(*parse_window(windows[0]))
        marks = set(windows)
        seen = []
        minute = _BASE_FIRST.hour * 60
        while minute <= _BASE_LAST.hour * 60:
            ws = dt.time(minute // 60, minute % 60)
            seen.append((f"{ws:%H:%M}-{_shift(ws, length):%H:%M}", ws, _shift(ws, length)))
            minute += max(args.baseline_step, 60)
        for win in windows:
            ws, we = parse_window(win)
            seen.append((win, ws, we))
        for label, ws, we in sorted(set(seen), key=lambda x: x[1]):
            rate = pivot_rate(days_list, ws, we, args.pivots)
            mark = "   <<< KILL ZONE" if label in marks else ""
            print(f"  {label:<16}{rate:>21.1f}%{mark}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for win, rows in all_rows.items():
            name = f"kz_{win.replace(':', '').replace('-', '_')}.csv"
            with (out / name).open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        print(f"\nper-day rows → {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
