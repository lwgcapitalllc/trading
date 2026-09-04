#!/usr/bin/env python3
"""rso_scan.py — find RETAIL SHAKE OUT (RSO) setups on cached bars, and draw them.

The setup, long (short is the exact mirror — see `invert()`):

    A  the EARLY BREAK   structure breaks up. `bull_sos` on the trade frame. The low the
                         break launched from (`bull_bos_low`) is the ORIGIN — early buyers'
                         stops sit under it.
    B  the SHAKE OUT     a bar's LOW drops under that origin. Those buyers are out. A WICK,
                         not a close: a close-through is a real trend failure, not a stop run.
    C  the REAL BREAK    the next `bull_sos`, and it must be AGGRESSIVE — candle range at
                         least `--impulse-atr` x ATR(14). Entry is C's close.

    stop    under the lowest low between A and C, minus a buffer
    target  `--min-rr` x risk

⚠ NOT A STRATEGY AND NOT A BACKTEST. No costs, no position slot, no session rules, no bias
filter, no discount filter. Outcomes are "which came first, stop or target" on a bar walk,
which is optimistic on the bars that touch both. Every number here is a rough count.

🔴 WHAT IS DELIBERATELY MISSING, because leaving it out is the honest version. `docs/FB_SPEC.md`
gates RSO on a 4H bias and an HTF discount filter. Both are HIGHER-TIMEFRAME reads, and
`backtest/optimizer.run_sweep` replays a SINGLE frame — so a three-stream version cannot be swept
today. This tool measures the TRIGGER alone. A trigger prior is not a strategy result, and this
repo has already been bitten by treating one as the other (`internal_realign_scan.py` had the
short side's SIGN wrong against a real replay). Take counts from here; take anything
exit-sensitive from a replay.

THE CONTROL IS THE POINT. "34% of shake outs work" means nothing until you know what an ordinary
bar does under the identical trade construction. `--control N` samples random entries matched on
direction, stop distance and target distance, and prints a z-score. Read every row against it.

🔴 MEASURED 2026-08-16, FIRST RUN: THIS TRIGGER CANNOT FIRE AS SPECIFIED, AND THAT IS THE RESULT.

Over 186,759 XAUUSD M15 bars (2018-09-13 → 2026-08-13) it produced **ZERO entries**, under both
readings of the origin level. The funnel says exactly where and it is not a coding accident:

    A · early break (bull_sos)      847        846
      trap big enough               847        846
    B · shake out                    16         24      <- origin "leg" / origin "swing"
    C · aggressive real break         0          0
    ENTRY                             0          0

**The binding constraint is C.** RSO as written needs TWO `bull_sos` events inside ~32 bars
(`--fail-window` 20 + `--confirm-window` 12). Measured event density on this frame:

    EXTERNAL   SOS   847   BOS 2,242     one SOS per 220 bars
    INTERNAL   SOS   575   BOS 1,419     one SOS per 325 bars

One SOS per 220 bars. Two inside 32 is not a rare setup, it is an arithmetic near-impossibility,
and dropping to the internal stream makes it WORSE rather than better (575 < 847) — so the
obvious fix is not a fix. This is the same shape `strategies/python/realign/CLAUDE.md` already
records: *"a single-engine M15 run gives only 9 setups in 5.6 years… the two-frame build is not a
refinement; without it there is no strategy to measure."*

⚠ **AARON'S OWN INDICATOR ALREADY SOLVES THIS AND THE SPEC DID NOT COPY IT.**
`indicators/engines/mss_sweeps.pine` fires on a **RECLAIM** — price wicks through the armed
level and simply CLOSES BACK — not on a second structure break. A reclaim happens on the next bar
or two; a second SOS may never happen at all. That one substitution is the difference between a
live indicator that signals and this scan's zero. **Before any RSO code is written, §4.6's event C
has to be re-specified as a reclaim, and `--confirm-window` re-measured against it.**

⚠ Do NOT read the zero as "RSO has no edge". Nothing was tested. A trigger that never fires has
not been measured — it has been mis-specified, which is a different and cheaper problem.

Usage:
  python backtest/tools/rso_scan.py --tf M15 --side both --control 40 --chart 4
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "backtest" / "cache"
sys.path.insert(0, str(ROOT / "engines"))

from market_structure import Bar, StructureEngine  # noqa: E402

UTC = dt.timezone.utc


@dataclass
class Bars:
    t: list = field(default_factory=list)
    o: list = field(default_factory=list)
    h: list = field(default_factory=list)
    l: list = field(default_factory=list)
    c: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.t)


def load(symbol: str, tf: str, start: str | None, end: str | None) -> Bars:
    path = CACHE / f"{symbol}__{tf}.csv"
    if not path.exists():
        sys.exit(f"no cache at {path}")
    b = Bars()
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            ts = row["time"]
            if start and ts < start:
                continue
            if end and ts > end:
                continue
            b.t.append(dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC))
            b.o.append(float(row["open"]))
            b.h.append(float(row["high"]))
            b.l.append(float(row["low"]))
            b.c.append(float(row["close"]))
    return b


def atr(b: Bars, length: int = 14) -> list:
    """Wilder's ATR — same seeding as the engines (sma seed, then recurse)."""
    out: list = [None] * len(b)
    trs, rma, alpha = [], None, 1.0 / length
    for i in range(len(b)):
        tr = (
            b.h[i] - b.l[i]
            if i == 0
            else max(b.h[i] - b.l[i], abs(b.h[i] - b.c[i - 1]), abs(b.l[i] - b.c[i - 1]))
        )
        if rma is None:
            trs.append(tr)
            if len(trs) == length:
                rma = sum(trs) / length
        else:
            rma = alpha * tr + (1 - alpha) * rma
        out[i] = rma
    return out


def invert(b: Bars) -> Bars:
    """Mirror prices so the LONG code detects SHORTS.

    Same trick, and the same reason, as `loaded_level_scan.py`: a hand-written bearish branch is
    exactly where a port gets a sign backwards, and this repo has already paid for that once.
    high and low SWAP because negating flips which of the two is larger. ATR is unchanged — true
    range is invariant under negation.

    ⚠ This assumes `StructureEngine` is sign-symmetric, which is an ASSUMPTION about somebody
    else's state machine, not a fact about arithmetic. `--verify-mirror` checks it: bear_sos count
    on real bars must equal bull_sos count on inverted bars. Run it before believing a short row.
    """
    return Bars(b.t, [-x for x in b.o], [-x for x in b.l], [-x for x in b.h], [-x for x in b.c])


def structure_breaks(b: Bars, origin_mode: str = "swing") -> tuple[dict, dict]:
    """Replay the canonical engine. Returns {bar: flags} and {bar: origin price}.

    The engine is fed CONTIGUOUSLY — it is a streaming state machine, so filtering the frame
    before the replay corrupts structure rather than failing loudly.

    ⚠ `origin_mode` was thought to be the whole argument. MEASURED 2026-08-16, IT IS NOT — see
    the 🔴 block at the top of this file. Both readings produce ZERO entries.

    `"leg"` is what `docs/FB_SPEC.md` §4.6 asks for: `origin = bull_bos_low`, which the engine
    documents as *"the swing low the impulse launched from"* — the FAR end of the whole break leg.
    `"swing"` is the PROTECTED SWING, the most recent pullback-confirmed swing low standing when
    the break fired. That is the level `indicators/engines/mss_sweeps.pine` actually arms
    ("the iHL under a bull iBOS"). It is much closer to price, and it moved the shake-out count
    from 16 to 24 out of ~847 — a real improvement on a step that was never the binding one.
    """
    eng = StructureEngine()
    flags: dict = {}
    origins: dict = {}
    last_swing_low: float | None = None
    for i in range(len(b)):
        ext = eng.update(Bar(index=i, open=b.o[i], high=b.h[i], low=b.l[i], close=b.c[i])).external
        fired = {f for f in ("bull_bos", "bull_sos", "bear_bos", "bear_sos") if getattr(ext, f)}
        if fired and "bull_sos" in fired:
            origin = ext.bull_bos_low if origin_mode == "leg" else last_swing_low
            if origin is not None:
                origins[i] = origin
        if fired:
            flags[i] = fired
        # AFTER the break test, so a swing confirmed on the break bar cannot become its own origin.
        if ext.new_swing_low and ext.new_swing_low_price is not None:
            last_swing_low = ext.new_swing_low_price
    return flags, origins


@dataclass
class Setup:
    dir: str
    a_bar: int
    origin: float
    b_bar: int = 0
    c_bar: int = 0
    entry: float = 0.0
    stop: float = 0.0
    swept: float = 0.0
    target: float = 0.0
    exit_bar: int = 0
    outcome: str = ""
    rr: float = 0.0


def unmirror(s: Setup) -> Setup:
    s.dir = "short"
    for f in ("origin", "entry", "stop", "swept", "target"):
        setattr(s, f, -getattr(s, f))
    return s


def scan(
    b: Bars,
    *,
    min_trap_atr: float,
    impulse_atr: float,
    fail_window: int,
    confirm_window: int,
    min_rr: float,
    stop_buf_atr: float,
    max_hold: int,
    origin_mode: str = "swing",
) -> tuple[list, dict, dict]:
    a14 = atr(b, 14)
    flags, origins = structure_breaks(b, origin_mode)
    sos_bars = sorted(origins)

    done: list = []
    funnel = {1: 0, 2: 0, 3: 0, 4: 0}
    # WHY a candidate died. Without this a funnel collapse has no cause and the first reading of
    # it is a guess — the lesson `loaded_level_scan.py` learnt the hard way.
    drops = {
        "trap too small": 0,
        "no shake out in window": 0,
        "no real break in window": 0,
        "break not aggressive": 0,
        "risk <= 0": 0,
        "live at end of data": 0,
    }
    n = len(b)

    for a in sos_bars:
        origin = origins[a]
        atr_a = a14[a]
        if not atr_a:
            continue
        funnel[1] += 1

        # A must be a genuine trap, not a wiggle: the leg it launched from has to be real.
        if (b.h[a] - origin) < min_trap_atr * atr_a:
            drops["trap too small"] += 1
            continue
        funnel[2] += 1

        # B — the shake out. A WICK under the origin, never a close through it.
        bb = None
        for j in range(a + 1, min(a + 1 + fail_window, n)):
            if b.c[j] < origin:  # closed through and stayed: a real failure, not a stop run
                break
            if b.l[j] < origin:
                bb = j
                break
        if bb is None:
            drops["no shake out in window"] += 1
            continue
        funnel[3] += 1

        # C — the real break. The next bull_sos, and it must be aggressive.
        cc = next((k for k in sos_bars if bb < k <= bb + confirm_window), None)
        if cc is None:
            drops["no real break in window"] += 1
            continue
        if (b.h[cc] - b.l[cc]) < impulse_atr * (a14[cc] or 0.0):
            drops["break not aggressive"] += 1
            continue
        funnel[4] += 1

        swept = min(b.l[a : cc + 1])
        entry = b.c[cc]
        stop = swept - stop_buf_atr * (a14[cc] or 0.0)
        risk = entry - stop
        if risk <= 0:
            drops["risk <= 0"] += 1
            continue
        target = entry + min_rr * risk

        s = Setup(
            dir="long",
            a_bar=a,
            origin=origin,
            b_bar=bb,
            c_bar=cc,
            entry=entry,
            stop=stop,
            swept=swept,
            target=target,
            rr=min_rr,
        )
        for j in range(cc + 1, min(cc + 1 + max_hold, n)):
            if b.l[j] <= stop:  # a bar holding both books the LOSS
                s.outcome, s.exit_bar = "stop", j
                break
            if b.h[j] >= target:
                s.outcome, s.exit_bar = "target", j
                break
        if not s.outcome:
            drops["live at end of data"] += 1
            continue
        done.append(s)

    return done, funnel, drops


def control(b: Bars, setups: list, reps: int, long_: bool, seed: int = 7) -> dict:
    """Matched random entries — same direction, same stop distance, same target distance."""
    import random

    rng = random.Random(seed)
    n = len(b)
    hits = trials = 0
    exp_sum = 0.0
    real = [s for s in setups if (s.dir == "long") == long_]
    if not real:
        return {}
    for s in real:
        risk = abs(s.entry - s.stop)
        reward = abs(s.target - s.entry)
        if risk <= 0:
            continue
        for _ in range(reps):
            i = rng.randrange(50, max(51, n - 2))
            e = b.c[i]
            stop = e - risk if long_ else e + risk
            targ = e + reward if long_ else e - reward
            for j in range(i + 1, min(i + 400, n)):
                stopped = b.l[j] <= stop if long_ else b.h[j] >= stop
                hit = b.h[j] >= targ if long_ else b.l[j] <= targ
                if stopped:
                    trials += 1
                    exp_sum -= 1.0
                    break
                if hit:
                    trials += 1
                    hits += 1
                    exp_sum += reward / risk
                    break
    if not trials:
        return {}
    p = hits / trials
    rp = sum(1 for s in real if s.outcome == "target") / len(real)
    rexp = sum((s.rr if s.outcome == "target" else -1.0) for s in real) / len(real)
    se = (p * (1 - p) / len(real)) ** 0.5
    return {
        "n": trials,
        "real_hit": rp,
        "rand_hit": p,
        "real_exp": rexp,
        "rand_exp": exp_sum / trials,
        "edge": (rp - p) * 100,
        "z": (rp - p) / se if se else 0.0,
    }


def draw(b: Bars, s: Setup, out: Path, pad: int = 40) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    lo_i = max(0, s.a_bar - pad)
    hi_i = min(len(b) - 1, (s.exit_bar or s.c_bar) + pad // 2)
    idx = range(lo_i, hi_i + 1)
    fig, ax = plt.subplots(figsize=(19.2, 9.6), dpi=100)
    wid = (mdates.date2num(b.t[lo_i + 1]) - mdates.date2num(b.t[lo_i])) * 0.7

    for i in idx:
        x = mdates.date2num(b.t[i])
        up = b.c[i] >= b.o[i]
        col = "#ffffff" if up else "#d62728"
        ax.plot([x, x], [b.l[i], b.h[i]], color="#333", lw=0.8, zorder=2)
        ax.add_patch(
            plt.Rectangle(
                (x - wid / 2, min(b.o[i], b.c[i])),
                wid,
                max(abs(b.c[i] - b.o[i]), 1e-9),
                facecolor=col,
                edgecolor="#333",
                lw=0.8,
                zorder=3,
            )
        )

    def hline(y, color, label, ls="-"):
        ax.axhline(y, color=color, ls=ls, lw=1.6, zorder=1)
        ax.annotate(
            f"{label}  {y:,.2f}",
            xy=(1.002, y),
            xycoords=("axes fraction", "data"),
            color=color,
            fontsize=11,
            fontweight="bold",
            va="center",
        )

    hline(s.origin, "#6b46a8", "ORIGIN")
    hline(s.entry, "#111111", "ENTRY")
    hline(s.stop, "#d62728", "STOP", ls="--")
    hline(s.target, "#2e7d32", "TARGET")

    def mark(bar, y, text, color, dy):
        ax.annotate(
            text,
            xy=(mdates.date2num(b.t[bar]), y),
            xytext=(mdates.date2num(b.t[bar]), y + dy),
            color=color,
            fontsize=11,
            fontweight="bold",
            ha="center",
            arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
        )

    span = max(b.h[i] for i in idx) - min(b.l[i] for i in idx)
    mark(s.a_bar, b.h[s.a_bar], "A · early break", "#6b46a8", span * 0.07)
    mark(s.b_bar, b.l[s.b_bar], "B · SHAKE OUT", "#d62728", -span * 0.07)
    mark(s.c_bar, b.h[s.c_bar], "C · real break → ENTRY", "#2e7d32", span * 0.09)
    ax.axvspan(
        mdates.date2num(b.t[s.c_bar]) - wid,
        mdates.date2num(b.t[s.c_bar]) + wid,
        color="#2e7d32",
        alpha=0.12,
        zorder=0,
    )

    ax.set_title(
        f"{s.dir.upper()}  ·  {b.t[s.a_bar]:%Y-%m-%d %H:%M} → {b.t[s.exit_bar]:%d %b %H:%M}"
        f"  ·  {s.rr:.1f}R planned  ·  {s.outcome.upper()}",
        fontsize=15,
        fontweight="bold",
        loc="left",
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    ax.set_xlim(mdates.date2num(b.t[lo_i]) - wid, mdates.date2num(b.t[hi_i]) + wid * 14)
    ax.grid(axis="y", color="#eee", zorder=0)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--tf", default="M15")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--min-trap-atr", type=float, default=0.5)
    p.add_argument("--impulse-atr", type=float, default=1.0)
    p.add_argument("--fail-window", type=int, default=20)
    p.add_argument("--confirm-window", type=int, default=12)
    p.add_argument("--min-rr", type=float, default=2.0)
    p.add_argument("--stop-buf-atr", type=float, default=0.05)
    p.add_argument("--max-hold", type=int, default=400)
    p.add_argument(
        "--origin",
        choices=["swing", "leg"],
        default="swing",
        help="swing = the protected swing the break left behind (what mss_sweeps arms); "
        "leg = FB_SPEC \u00a74.6's bull_bos_low, which measured ZERO entries",
    )
    p.add_argument("--side", choices=["long", "short", "both"], default="both")
    p.add_argument("--control", type=int, default=0, help="reps per setup (try 40)")
    p.add_argument("--chart", type=int, default=0, help="render N examples")
    p.add_argument("--outdir", default="backtest/reports/rso")
    p.add_argument(
        "--verify-mirror",
        action="store_true",
        help="prove the engine is sign-symmetric before trusting a short row",
    )
    a = p.parse_args()

    b = load(a.symbol, a.tf, a.start, a.end)
    if len(b) < 200:
        sys.exit(f"only {len(b)} bars")
    print(f"\n{len(b):,} {a.tf} bars   {b.t[0]:%Y-%m-%d} → {b.t[-1]:%Y-%m-%d}")

    if a.verify_mirror:
        fr, _ = structure_breaks(b)
        fi, _ = structure_breaks(invert(b))
        real_bear = sum(1 for v in fr.values() if "bear_sos" in v)
        inv_bull = sum(1 for v in fi.values() if "bull_sos" in v)
        ok = real_bear == inv_bull
        print(
            f"\nMIRROR CHECK   bear_sos on real = {real_bear:,}   bull_sos on inverted = {inv_bull:,}"
            f"   → {'SYMMETRIC' if ok else '🔴 NOT SYMMETRIC — do not trust the short side'}"
        )
        if not ok:
            sys.exit(1)

    kw = dict(
        min_trap_atr=a.min_trap_atr,
        impulse_atr=a.impulse_atr,
        fail_window=a.fail_window,
        confirm_window=a.confirm_window,
        min_rr=a.min_rr,
        stop_buf_atr=a.stop_buf_atr,
        max_hold=a.max_hold,
        origin_mode=a.origin,
    )

    setups, funnel, drops = [], {1: 0, 2: 0, 3: 0, 4: 0}, {}
    if a.side in ("long", "both"):
        s, f, d = scan(b, **kw)
        setups += s
        for k in funnel:
            funnel[k] += f[k]
        for k, v in d.items():
            drops[k] = drops.get(k, 0) + v
    if a.side in ("short", "both"):
        s, f, d = scan(invert(b), **kw)
        setups += [unmirror(x) for x in s]
        for k in funnel:
            funnel[k] += f[k]
        for k, v in d.items():
            drops[k] = drops.get(k, 0) + v

    print(
        f"\nFUNNEL  (min trap {a.min_trap_atr} ATR, impulse {a.impulse_atr} ATR, "
        f"min RR {a.min_rr}, side {a.side}, origin {a.origin})"
    )
    for k, lab in (
        (1, "A · early break (bull_sos)"),
        (2, "  trap big enough"),
        (3, "B · shake out (wick under origin)"),
        (4, "C · aggressive real break"),
    ):
        print(f"  {k} {lab:<38} {funnel[k]:>7,}")
    print(f"  5 ENTRY taken{'':<32} {len(setups):>7,}")

    print("\nWHY CANDIDATES DIED")
    for k, v in sorted(drops.items(), key=lambda kv: -kv[1]):
        if v:
            print(f"  {k:<32} {v:>7,}")

    if setups:
        w = sum(1 for s in setups if s.outcome == "target")
        nl = sum(1 for s in setups if s.dir == "long")
        rsum = sum((s.rr if s.outcome == "target" else -1.0) for s in setups)
        print(f"\nOUTCOMES  {len(setups)} trades  ({nl}L / {len(setups) - nl}S)")
        print(f"  target {w}   stop {len(setups) - w}")
        print(
            f"  hit rate {w / len(setups):.1%}   ·   R sum {rsum:+.1f}   ·   "
            f"median planned {statistics.median(s.rr for s in setups):.1f}R"
        )

    if a.control:
        for lab, lng, bars in (("long", True, b), ("short", False, b)):
            if a.side not in ("both", lab):
                continue
            r = control(bars, setups, a.control, lng)
            if not r:
                continue
            print(
                f"\nCONTROL · {lab}   ({r['n']:,} random entries, matched on direction + "
                f"stop distance + target distance)"
            )
            print(f"  real     hit {r['real_hit']:6.1%}   expectancy {r['real_exp']:+.3f}R")
            print(f"  random   hit {r['rand_hit']:6.1%}   expectancy {r['rand_exp']:+.3f}R")
            print(f"  edge over control  {r['edge']:+.1f} pts   z {r['z']:+.2f}")

    if a.chart and setups:
        out = ROOT / a.outdir
        out.mkdir(parents=True, exist_ok=True)
        wins = [s for s in setups if s.outcome == "target"]
        loss = [s for s in setups if s.outcome == "stop"]
        nw = max(1, a.chart // 2)
        picks = wins[:nw] + loss[: a.chart - nw] or setups[: a.chart]
        print()
        for i, s in enumerate(picks, 1):
            f = out / f"rso_{i}_{b.t[s.c_bar]:%Y%m%d_%H%M}_{s.dir}_{s.outcome}.png"
            draw(b if s.dir == "long" else b, s, f)
            print(f"  drew {f.relative_to(ROOT)}   {s.rr:.1f}R  {s.outcome}")


if __name__ == "__main__":
    main()
