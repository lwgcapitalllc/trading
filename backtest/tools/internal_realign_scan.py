#!/usr/bin/env python3
"""internal_realign_scan.py — how often does the internal-realignment setup appear?

Aaron's playbook, read off a 2026-08-05/07 XAUUSD chart (2026-08-11):

    EXTERNAL structure (15m) is bullish — a bullish SOS, then bullish BOS, bullish
    BOS. Then external flips DOWN with a bearish SOS. That is a deviation, not a new
    trend: the higher-order read is still up.

    Drop to the INTERNAL structure on a lower timeframe. Inside the deviation it goes
    bearish too — an iBOS down, then a bearish iSOS. Then internal turns first: a
    bullish iSOS REALIGNS the internal read with the original external bullish one.

    Enter long on that internal bullish iSOS — immediately, or on a retracement — with
    the stop behind the last bearish internal shift of structure. The external bullish
    SOS that reclaims the old high comes LATER; the trade front-runs it.

🔴 **LONGS ONLY — the short mirror is NOT implemented.** The playbook is symmetric and this
tool is not, so every count and every hit rate below describes the bull case alone. That
is stated here rather than left implicit because XAUUSD trends UP across this window, so
the side that IS implemented is the flattering one: a null on longs is therefore the
stronger null, and a positive result on longs would have needed the shorts before it could
be believed at all. Implement the mirror before quoting this tool on the setup as a whole.

This tool COUNTS those occurrences and measures their GEOMETRY — how far the entry sits
from the stop, and whether the external reclaim the setup anticipates actually arrived.
It does not size them, charge them or score them in R. There is no P&L number here,
deliberately: "how many are there, and does the anticipated move follow" is the question
being asked, and answering it with an equity curve would smuggle in a dozen decisions
nobody has made yet — entry model, exit ladder, risk. That is stage 1 work and this is
the pass before it. See docs/STRATEGY_WORKFLOW.md.

WHY TWO BAR FRAMES — this is the finding that made the tool necessary:

  The canonical engine emits external AND internal structure from ONE stream, so the
  obvious build is one 15m engine reading both. MEASURED on the charted window, that
  does not reproduce the chart: the 15m engine's external stream matches Aaron's marks
  exactly (BOS 4179.44, BOS 4267.67, bear SOS 4242.99 -> LL 4223.39, bull SOS 4304.07),
  while its INTERNAL stream over the same four days carries three iSL swings and ZERO
  iBOS/iSOS. The internal structure on the chart is a LOWER TIMEFRAME's own internal
  stream. So the setup is inherently dual-frame and the tool replays two engines.

  ⚠ The consequence reaches past this tool: `backtest.optimizer.run_sweep` replays a
  SINGLE frame and refuses a dual-frame strategy outright (see CLAUDE.md, 2026-08-07).
  A strategy built on this shape cannot be swept by the existing optimizer without work.

⚠ INTERNAL TRACKING RESETS ON AN EXTERNAL BREAK. engine.py `_process_internal` wipes the
internal state machine on any external BOS/SOS *of its own frame* and re-seeds it on the
next confirmed external swing. On the lower frame that frame's own external breaks are
frequent, so an internal sequence can be erased mid-way through the setup. That is not a
bug to route around — it is the engine's rule, and how often it truncates a candidate is
one of the things worth knowing, so the scan reports `reset_truncated` rather than
silently re-deriving internal structure some other way.

⚠ WHICH STREAM COUNTS AS "INTERNAL" IS THE MOST LOAD-BEARING CHOICE HERE, and the two
readings give OPPOSITE answers. `--internal-source external` reads the lower frame's own
swing structure, which is what "internal" means relative to a 15m external, and is what
the chart shows: every rung positive, M5 +5.0% over control. `--internal-source internal`
reads the engine's `InternalEvents`, which is the sub-structure of the lower frame ITSELF,
one level further down, and is wiped by that frame's own external breaks on 81% of
candidates: every rung negative. Default is `external`.

Usage:
    python3 backtest/tools/internal_realign_scan.py
    python3 backtest/tools/internal_realign_scan.py --cascade M5 --target-r 3
    python3 backtest/tools/internal_realign_scan.py --internal-source internal
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import random
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from market_structure import Bar, StructureEngine  # noqa: E402

CACHE = _ROOT / "backtest" / "cache"
UTC = dt.timezone.utc

# Minutes per cached frame. M5 is not cached and is RESAMPLED from M1 — see `_load`.
_TF_MINUTES = {"M1": 1, "M2": 2, "M3": 3, "M5": 5, "M10": 10,
               "M15": 15, "M30": 30, "H1": 60, "H4": 240}


# --------------------------------------------------------------------------------------
# Bars
# --------------------------------------------------------------------------------------

def _read_csv(path: Path) -> list[tuple[dt.datetime, float, float, float, float]]:
    if not path.exists():
        raise SystemExit(f"no cached bars at {path}")
    rows = []
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append((
                dt.datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC),
                float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
            ))
    return rows


def _resample(rows, minutes: int):
    """Bucket M1 bars into `minutes`-wide bars, aligned to the hour.

    ⚠ A bucket is emitted only when the NEXT bar starts a new bucket, so a partly-filled
    trailing bucket is dropped rather than published as a complete bar — the live-bar
    trap `_drop_forming_tail` exists for on the export side. Gaps (weekends, holidays)
    simply produce no bucket; nothing is interpolated, because an invented bar is a bar
    the structure engine would break structure on.
    """
    out, cur, cur_key = [], None, None
    for stamp, o, h, l, c in rows:
        key = stamp.replace(second=0, microsecond=0)
        key = key.replace(minute=(key.minute // minutes) * minutes)
        if key != cur_key:
            if cur is not None:
                out.append(cur)
            cur, cur_key = (key, o, h, l, c), key
        else:
            cur = (cur[0], cur[1], max(cur[2], h), min(cur[3], l), c)
    if cur is not None:
        out.append(cur)
    return out


def _gap_report(rows, minutes: int, label: str) -> None:
    """Say out loud how contiguous the frame is.

    🔴 This exists because the cached XAUUSD M5 file LOOKS complete and is not: 26,886
    bars spanning 2023-02-10 -> 2026-08-07, where a contiguous M5 frame over that span
    would hold ~260,000. The cache stores only the ranges somebody fetched, so the file
    is a handful of islands. Feeding that to a streaming state machine does not fail —
    it silently builds structure across a hole, breaking levels that no bar ever
    traded through, and every count downstream is then measured on a history that never
    happened. A frame is reported, never silently accepted.
    """
    if len(rows) < 2:
        return
    step = dt.timedelta(minutes=minutes)
    # A weekend is a legitimate hole; anything past ~3 days is not.
    holes = 0
    worst = dt.timedelta(0)
    for a, b in zip(rows, rows[1:]):
        d = b[0] - a[0]
        if d > step:
            holes += 1
            worst = max(worst, d)
    span_bars = (rows[-1][0] - rows[0][0]) / step
    density = len(rows) / span_bars if span_bars else 0.0
    print(f"  {label}: {len(rows):,} bars  {rows[0][0]:%Y-%m-%d}..{rows[-1][0]:%Y-%m-%d}  "
          f"density {density:.1%} of a contiguous frame  gaps {holes:,}  worst {worst.days}d")


def _load(symbol: str, tf: str, prefer_resample: bool = True):
    """Load a frame, preferring a RESAMPLE from contiguous M1 over a sparse cached file.

    M1 is the only intraday frame here fetched end to end (2,334,222 bars, 2020-01-01
    onward). The M5/M30 caches are partial. So for any sub-M15 frame the honest source is
    M1, resampled — see `_gap_report` for what the alternative costs.
    """
    minutes = _TF_MINUTES[tf]
    direct = CACHE / f"{symbol}__{tf}.csv"
    if prefer_resample and minutes < 15:
        rows = _resample(_read_csv(CACHE / f"{symbol}__M1.csv"), minutes)
        _gap_report(rows, minutes, f"{tf} (resampled from M1)")
        return rows
    rows = _read_csv(direct)
    _gap_report(rows, minutes, tf)
    return rows


# --------------------------------------------------------------------------------------
# Pass 1 — replay each frame once
# --------------------------------------------------------------------------------------

class Frame:
    """One bar frame plus its engine's per-bar output. Nothing here decides whether a
    pattern occurred — that is the matcher's job, and keeping the two apart is what lets
    every variant share one replay."""

    def __init__(self, label: str = "", minutes: int = 0) -> None:
        self.label = label
        self.minutes = minutes
        self.time: list[dt.datetime] = []
        self.high: list[float] = []
        self.low: list[float] = []
        self.close: list[float] = []
        # (bar_index, kind) with kind in {bull_bos, bull_sos, bear_bos, bear_sos}.
        # NOTE an SOS bar raises its plain BOS flag too (engine.py sets bull_bos then
        # bull_sos on a CHoCH), so a bullish SOS appears under BOTH kinds.
        self.ext: list[tuple[int, str, float | None]] = []
        # bar_index -> the HH/LH price reclassified on that break bar. On a bearish SOS
        # this is the external high that STOOD before the deviation — the level the
        # setup's anticipated reclaim has to take out, so it is the setup's own target
        # and the only non-arbitrary one available.
        self.broken_high: dict[int, float] = {}
        self.broken_low: dict[int, float] = {}
        # (bar_index, kind, price) for the INTERNAL stream, same four kinds.
        self.internal: list[tuple[int, str, float | None]] = []
        # Bars on which internal state was wiped by an external break of THIS frame.
        self.int_resets: set[int] = set()


def replay(rows, label: str = "", minutes: int = 0) -> Frame:
    """Feed every bar through the structure engine, contiguously.

    Bars are fed including weekends: the engine is a streaming state machine, so
    filtering the frame before the replay would silently corrupt structure rather than
    fail loudly. Any date window is applied to the RESULT, not to the input.
    """
    f = Frame(label, minutes)
    eng = StructureEngine()
    for i, (stamp, o, h, l, c) in enumerate(rows):
        ev = eng.update(Bar(index=i, open=o, high=h, low=l, close=c))
        e, n = ev.external, ev.internal

        f.time.append(stamp)
        f.high.append(h)
        f.low.append(l)
        f.close.append(c)

        broke = False
        for kind in ("bull_bos", "bull_sos", "bear_bos", "bear_sos"):
            if getattr(e, kind):
                broke = True
                f.ext.append((i, kind, getattr(e, kind.replace("_sos", "_bos") + "_price", None)))
        if broke:
            f.int_resets.add(i)
        if e.broken_high_label and e.broken_high_price is not None:
            f.broken_high[i] = e.broken_high_price
        if e.broken_low_label and e.broken_low_price is not None:
            f.broken_low[i] = e.broken_low_price

        for kind in ("bull_bos", "bull_sos", "bear_bos", "bear_sos"):
            if getattr(n, kind):
                f.internal.append((i, kind, getattr(n, kind + "_price", None)))
    return f


# --------------------------------------------------------------------------------------
# Pass 2 — match the sequence
# --------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------
# Pass 2 — match the sequence
# --------------------------------------------------------------------------------------

# The internal sequence Aaron reads on the 5m, for a LONG setup (the deviation is DOWN):
#
#   iBOS bull  — price bounces inside the deviation
#   iSOS bear  — that bounce fails and makes the low; the internal's OWN false break
#   iSOS bull  — it recovers; the internal has realigned with the external bull trend
#
# The SHORT mirror is the same three with every direction flipped. Both are the strategy;
# neither is an extension of the other.
_PATTERNS = {
    # name        the ordered sequence of (kind, direction) the stream must produce
    "strict":   (("bos", +1), ("sos", -1), ("sos", +1)),
    "opposing": (("sos", -1), ("sos", +1)),
    "any":      (("any", -1), ("sos", +1)),
    # Entry DELAYED by one confirmation: the realignment must be followed by a further
    # with-trend internal break before the entry is taken. Tests "we are early", which is
    # what the long side's worst-at-1R failure signature points at.
    "confirmed": (("any", -1), ("sos", +1), ("any", +1)),
}


def _resolve(ltf: Frame, i: int, d: int, stop: float, target: float, horizon: int):
    """Did price reach `target` or `stop` first, walking forward from bar `i`?

    `d` is +1 for a long, -1 for a short. ONE implementation, shared by the real setups
    and by the control — a control scored by a second copy of this rule is not a control,
    because any drift between the two copies reads as edge.

    Both levels inside ONE bar is unresolvable at bar resolution (the tape order is
    unknown) and is scored a LOSS. That rule applies to the control too, or the
    comparison is rigged in the setup's favour.
    """
    for jj in range(i + 1, min(i + horizon, len(ltf.time))):
        if d > 0:
            hit_stop, hit_targ = ltf.low[jj] <= stop, ltf.high[jj] >= target
        else:
            hit_stop, hit_targ = ltf.high[jj] >= stop, ltf.low[jj] <= target
        if hit_stop or hit_targ:
            return "win" if (hit_targ and not hit_stop) else "loss"
    return None


def control(rows, horizon_hrs: float, per_setup: int = 40, seed: int = 7):
    """Random entries matched to the real setups on DIRECTION, STOP DISTANCE and R:R.

    🔴 Without this the whole scan is worthless. XAUUSD went 1,200 -> 4,300 across the
    window, so a long-side rule risking $10 to make $10 wins over half its bets by DRIFT
    ALONE. `tools/trigger_edge.py` exists because of exactly that, and its control landing
    on theoretical breakeven is what certifies a harness before any result is read off it.

    Matched on R:R as well as stop distance, which is a departure from trigger_edge's
    fixed-ATR control: this setup's target is the external extreme that stood before the
    deviation, so its reward:risk varies per setup and a single fixed R:R would answer a
    different question from the population being compared.
    """
    rnd = random.Random(seed)
    out = []
    for r in rows:
        # Each row fires on its OWN cascade rung, so its control must be drawn there too.
        ltf, d = r["frame"], r["dir"]
        horizon = int(horizon_hrs * 60 / ltf.minutes)
        lo, hi = 200, len(ltf.time) - horizon - 1
        if hi <= lo:
            continue
        for _ in range(per_setup):
            i = rnd.randrange(lo, hi)
            entry = ltf.close[i]
            stop = entry - d * r["stop_dist"]
            target = entry + d * r["stop_dist"] * r["reward_risk"]
            out.append((_resolve(ltf, i, d, stop, target, horizon), r["reward_risk"]))
    return out


def _ltf_index_at(ltf: Frame, stamp: dt.datetime, lo: int = 0) -> int:
    """First LTF bar at or after `stamp`."""
    i, n = lo, len(ltf.time)
    while i < n and ltf.time[i] < stamp:
        i += 1
    return i


def _match_pattern(stream, j0: int, j_end: int, d: int, steps):
    """Walk the internal stream and require `steps` IN ORDER inside the window.

    Returns (trigger_bar, last_counter_bar) or None. `last_counter_bar` is the bar of the
    most recent COUNTER-direction internal break before the trigger — the leg the final
    shift reversed, which is what anchors the stop.

    ⚠ The steps must occur in order but need NOT be adjacent: other internal breaks may
    sit between them. Requiring adjacency would make the pattern a statement about the
    engine's label density rather than about price.
    """
    si = 0
    last_counter = None
    for idx, ikind, _p in stream:
        if idx < j0:
            continue
        if idx > j_end:
            break
        kind, sign = ("sos", +1) if ikind.endswith("_sos") else ("bos", +1)
        sign = +1 if ikind.startswith("bull") else -1
        # remember the newest counter-direction break for the stop anchor
        if sign == -d:
            last_counter = idx
        want_kind, want_sign = steps[si]
        ok = (sign == want_sign * d) and (want_kind == "any" or want_kind == kind)
        if ok:
            si += 1
            if si == len(steps):
                return idx, last_counter
    return None


def find(htf: Frame, frames, budget_hrs: float, pattern: str,
         horizon_hrs: float = 168.0, target_r: float = 0.0,
         internal_source: str = "internal", sides=(+1, -1), wide_stop: bool = False):
    """For each external false break, walk the cascade and look for the internal sequence.

    LONG  (d=+1): external trend BULLISH, then a bearish SOS = the false break. Target is
                  the external HIGH that stood before it.
    SHORT (d=-1): the exact mirror — external trend BEARISH, a bullish SOS is the false
                  break, target is the external LOW that stood before it.

    Both sides are the strategy. Measuring only longs on an instrument that trended up for
    the whole window measures the drift as much as the setup.
    """
    steps = _PATTERNS[pattern]
    out = []
    for d in sides:
        trig_kind = "bear_sos" if d > 0 else "bull_sos"
        trend_kinds = ("bull_bos", "bull_sos") if d > 0 else ("bear_bos", "bear_sos")
        counter_kinds = ("bear_bos", "bear_sos") if d > 0 else ("bull_bos", "bull_sos")

        for k, (bi, kind, _bp) in enumerate(htf.ext):
            if kind != trig_kind:
                continue
            prior = [e for e in htf.ext[:k] if e[1] in trend_kinds]
            if not prior:
                continue
            last_trend = prior[-1]
            # ⚠ `e[0] < bi` is load-bearing. A CHoCH bar raises BOTH its plain BOS and its
            # SOS flag, so this SOS's own twin sits in the slice and every candidate would
            # disqualify ITSELF — which reads exactly like "the setup never happens".
            between = [e for e in htf.ext[:k]
                       if last_trend[0] < e[0] < bi and e[1] in counter_kinds]
            if between:
                continue

            dev_stamp = htf.time[bi]
            ext_target = (htf.broken_high.get(bi) if d > 0 else htf.broken_low.get(bi))

            for ltf in frames:
                budget_bars = int(budget_hrs * 60 / ltf.minutes)
                horizon_bars = int(horizon_hrs * 60 / ltf.minutes)
                j0 = _ltf_index_at(ltf, dev_stamp)
                if j0 >= len(ltf.time):
                    continue
                j_end = min(j0 + budget_bars, len(ltf.time) - 1)

                stream = ltf.internal if internal_source == "internal" else ltf.ext
                hit = _match_pattern(stream, j0, j_end, d, steps)
                if hit is None:
                    continue  # no such sequence on this rung — drop a frame
                trigger, last_counter = hit

                entry = ltf.close[trigger]
                # Stop — behind the last COUNTER-direction internal shift: the extreme of
                # the internal leg the final shift just reversed.
                # `--wide-stop` anchors at the whole deviation instead of the internal
                # leg — a much wider stop, tested because the long side fails at 1R.
                anchor = j0 if (wide_stop or last_counter is None) else last_counter
                if d > 0:
                    level = min(ltf.low[anchor:trigger + 1])
                else:
                    level = max(ltf.high[anchor:trigger + 1])
                stop_dist = (entry - level) * d
                if stop_dist <= 0:
                    continue

                if target_r > 0:
                    target = entry + d * stop_dist * target_r
                else:
                    target = ext_target
                    if target is None or (target - entry) * d <= 0:
                        break
                outcome = _resolve(ltf, trigger, d, level, target, horizon_bars)

                out.append({
                    "dir": d,
                    "rung": ltf.label,
                    "frame": ltf,
                    "time": ltf.time[trigger],
                    "entry": entry,
                    "stop": level,
                    "target": target,
                    "stop_dist": stop_dist,
                    "reward_risk": (target - entry) * d / stop_dist,
                    "hrs_to_trigger": (trigger - j0) * ltf.minutes / 60.0,
                    "resolved": outcome is not None,
                    "won": outcome == "win",
                })
                break  # first rung that produces the sequence wins the setup
    return sorted(out, key=lambda r: r["time"])


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------

def _median(xs):
    return statistics.median(xs) if xs else float("nan")


def _score(rows, horizon_hrs: float, indent: str = "  "):
    res = [r for r in rows if r["resolved"]]
    if not res:
        print(f"{indent}{len(rows)} setups, none resolved inside the horizon")
        return
    won = [r for r in res if r["won"]]
    wr = len(won) / len(res)
    exp = sum(r["reward_risk"] for r in won) / len(res) - (len(res) - len(won)) / len(res)
    print(f"{indent}median stop ${_median([r['stop_dist'] for r in rows]):.2f}   "
          f"median R:R {_median([r['reward_risk'] for r in rows]):.2f}R   "
          f"median {_median([r['hrs_to_trigger'] for r in rows]):.1f}h to trigger")
    print(f"{indent}reached target     {len(won)}/{len(res)} ({wr:.1%})   "
          f"expectancy {exp:+.3f}R")
    ctrl = [c for c in control(rows, horizon_hrs) if c[0] is not None]
    if not ctrl:
        return
    cwon = [c for c in ctrl if c[0] == "win"]
    cwr = len(cwon) / len(ctrl)
    cexp = sum(c[1] for c in cwon) / len(ctrl) - (len(ctrl) - len(cwon)) / len(ctrl)
    se = (wr * (1 - wr) / len(res)) ** 0.5 if len(res) > 1 else 0.0
    z = (wr - cwr) / se if se else 0.0
    print(f"{indent}control (n={len(ctrl):,})   {cwr:.1%} hit rate   {cexp:+.3f}R")
    print(f"{indent}EDGE               {wr-cwr:+.1%} hit rate ({z:+.1f} sigma)   "
          f"{exp-cexp:+.3f}R expectancy")


def report(rows, label: str, frames, budget_hrs: float, horizon_hrs: float) -> None:
    print(f"\n=== {label} ===")
    if not rows:
        print("  NO OCCURRENCES — the sequence never completed inside the window.")
        return
    span = (rows[-1]["time"] - rows[0]["time"]).days / 365.25
    rate = f" ({len(rows)/span:.1f}/yr)" if span > 0 else ""
    longs = [r for r in rows if r["dir"] > 0]
    shorts = [r for r in rows if r["dir"] < 0]
    print(f"  {len(rows)} setups over {span:.1f} yrs{rate}   "
          f"{len(longs)} long / {len(shorts)} short")

    for name, sub in (("LONG", longs), ("SHORT", shorts)):
        if not sub:
            continue
        print(f"\n  == {name}: {len(sub)} setups ==")
        _score(sub, horizon_hrs, indent="    ")
        for f in frames:
            rung = [r for r in sub if r["rung"] == f.label]
            if rung:
                print(f"    -- rung {f.label}: {len(rung)} --")
                _score(rung, horizon_hrs, indent="      ")

    if longs and shorts:
        print(f"\n  == BOTH SIDES POOLED: {len(rows)} setups ==")
        _score(rows, horizon_hrs, indent="    ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--htf", default="M15")
    ap.add_argument("--cascade", default="M5",
                    help="internal frames tried in order; the first that matches wins")
    ap.add_argument("--pattern", choices=tuple(_PATTERNS), default="strict",
                    help="strict = iBOS with-trend, iSOS counter, iSOS with-trend; "
                         "opposing = just the two opposing iSOS; any = any counter break "
                         "then a with-trend iSOS")
    ap.add_argument("--window-hrs", type=float, default=24.0)
    ap.add_argument("--horizon-hrs", type=float, default=168.0)
    ap.add_argument("--internal-source", choices=("internal", "external"),
                    default="internal",
                    help="the engine's own iBOS/iSOS stream (what the chart draws), or "
                         "the lower frame's external swings")
    ap.add_argument("--target-r", type=float, default=0.0)
    ap.add_argument("--side", choices=("both", "long", "short"), default="both")
    ap.add_argument("--wide-stop", action="store_true",
                    help="anchor the stop at the whole deviation, not the internal leg")
    args = ap.parse_args()

    print(f"loading {args.symbol} {args.htf} + cascade {args.cascade} …", flush=True)
    htf = replay(_load(args.symbol, args.htf), args.htf, _TF_MINUTES[args.htf])
    frames = [replay(_load(args.symbol, tf), tf, _TF_MINUTES[tf])
              for tf in [t.strip() for t in args.cascade.split(",") if t.strip()]]
    sides = {"both": (+1, -1), "long": (+1,), "short": (-1,)}[args.side]

    rows = find(htf, frames, args.window_hrs, args.pattern,
                horizon_hrs=args.horizon_hrs, target_r=args.target_r,
                internal_source=args.internal_source, sides=sides,
                wide_stop=args.wide_stop)
    label = (f"{args.symbol}  ext {args.htf}  int {args.cascade} "
             f"[{args.internal_source}]  pattern={args.pattern}")
    report(rows, label, frames, args.window_hrs, args.horizon_hrs)


if __name__ == "__main__":
    main()
