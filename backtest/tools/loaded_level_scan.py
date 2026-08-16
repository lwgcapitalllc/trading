"""loaded_level_scan.py — find "Loaded Level" (Da Vinci) setups on cached bars.

A FIRST-PASS scanner for the model in `docs/DAVINCI_MODEL_SPEC.md`. It exists to answer two
questions before anything is built properly:

  1. How OFTEN does this fire? If "loaded" describes most swing levels it is not a filter.
  2. What do real instances look like? — it renders them so they can be checked by eye.

⚠ NOT A STRATEGY AND NOT A BACKTEST. No costs, no position slot, no queueing, no session rules,
no re-entry cap. Outcomes here are "which came first, stop or target" on a bar-by-bar walk, which
is optimistic on the bars where both are touched. Treat every number it prints as a rough count,
never as an edge.

The level lifecycle (the whole model):
  FRESH     a pivot just printed, never revisited
  LOADED    a later pivot came back within `tol` and did NOT break it → orders rest beyond it
  CONSUMED  price traded through it → a "liquidity block", where a stop goes

Usage:
  python backtest/tools/loaded_level_scan.py --tf M15 --start 2024-01-01 --chart 3
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "backtest" / "cache"


# ─────────────────────────────── bars ───────────────────────────────


@dataclass
class Bars:
    t: list
    o: list
    h: list
    l: list
    c: list

    def __len__(self) -> int:
        return len(self.t)


def load(symbol: str, tf: str, start: str | None, end: str | None) -> Bars:
    path = CACHE / f"{symbol}__{tf}.csv"
    if not path.exists():
        sys.exit(f"no cache at {path}")
    t, o, h, l, c = [], [], [], [], []
    with path.open() as f:
        for row in csv.DictReader(f):
            ts = row["time"]
            if start and ts < start:
                continue
            if end and ts > end:
                continue
            t.append(datetime.fromisoformat(ts))
            o.append(float(row["open"]))
            h.append(float(row["high"]))
            l.append(float(row["low"]))
            c.append(float(row["close"]))
    return Bars(t, o, h, l, c)


def atr(b: Bars, length: int = 50) -> list:
    """Wilder's ATR — matches the engines' `_Rma` seeding (sma seed, then recurse)."""
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


def pivots(b: Bars, n: int) -> tuple[list, list]:
    """Strict pivots, confirmed `n` bars late — the semantics the validated engines port.

    Returns two lists indexed by CONFIRMATION bar; each holds the pivot's (bar, price) or None.
    """
    ph: list = [None] * len(b)
    pl: list = [None] * len(b)
    for i in range(n, len(b) - n):
        win = range(i - n, i + n + 1)
        if all(b.h[i] > b.h[j] for j in win if j != i):
            ph[i + n] = (i, b.h[i])
        if all(b.l[i] < b.l[j] for j in win if j != i):
            pl[i + n] = (i, b.l[i])
    return ph, pl


# ─────────────────────────────── setups ───────────────────────────────


@dataclass
class Setup:
    dir: str  # "long" | "short"
    arm_bar: int
    block_bar: int
    block: float  # the consumed extreme — where the stop hides
    loaded_bar: int = 0
    loaded: float = 0.0  # the level the entry sweeps
    induce_bar: int = 0
    el_bar: int = 0
    el: float = 0.0  # engineered level — the target
    entry_bar: int = 0
    entry: float = 0.0
    stop: float = 0.0
    exit_bar: int = 0
    outcome: str = ""  # "target" | "stop" | "open"
    rr: float = 0.0
    stage: int = 1  # how far it got, for the funnel
    notes: list = field(default_factory=list)


def invert(b: Bars) -> Bars:
    """Mirror prices so the LONG code detects SHORTS.

    A short setup is the exact mirror of a long one — `docs/DAVINCI_MODEL_SPEC.md` says so and
    every source video says so. Writing the bearish branch by hand is exactly where a port
    silently gets a sign backwards (the ⚠ at the top of that spec, and it has already cost this
    repo once — see `e87c304`, "the tool that counted it got one side's sign wrong"). So the bars
    are negated and the SAME long code runs over them.

    high and low SWAP because negating flips which of the two is larger. ATR is unchanged: true
    range is invariant under negation, so the tolerance means the same thing on both sides.
    """
    return Bars(b.t, [-x for x in b.o], [-x for x in b.l], [-x for x in b.h], [-x for x in b.c])


def unmirror(s: Setup) -> Setup:
    """Map a setup found on inverted bars back to real prices. `rr` is a ratio — unchanged."""
    s.dir = "short"
    for f in ("block", "loaded", "el", "entry", "stop"):
        setattr(s, f, -getattr(s, f))
    return s


def scan(
    b: Bars,
    *,
    pivot_len: int,
    tol_mult: float,
    buf_mult: float,
    min_rr: float,
    expiry: int,
    max_hold: int,
) -> tuple[list, dict, dict]:
    a = atr(b, 50)
    ph, pl = pivots(b, pivot_len)

    prev_ph: tuple | None = None  # most recent confirmed pivot high (bar, price)
    prev_pl: tuple | None = None
    loaded_lows: list = []  # (bar, price) levels holding sell-side liquidity
    loaded_highs: list = []

    live: Setup | None = None
    done: list = []
    funnel = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    # WHY a setup died. Without this the funnel shows a collapse with no cause, and the first
    # reading of it was wrong — see the tool's docstring note on the stage-4 drop.
    drops = {
        "expired": 0,
        "block broken": 0,
        "rr below floor": 0,
        "risk <= 0": 0,
        "live at end of data": 0,
    }

    for i in range(len(b)):
        tol = (a[i] or 0.0) * tol_mult
        if tol <= 0:
            continue

        # ── level lifecycle ──────────────────────────────────────────
        if pl[i]:
            bar, px = pl[i]
            # LOADED: this low came back near the previous one and did NOT break it
            if prev_pl and 0 <= px - prev_pl[1] <= tol:
                loaded_lows.append((prev_pl[0], prev_pl[1]))
            prev_pl = (bar, px)
        if ph[i]:
            bar, px = ph[i]
            if prev_ph and 0 <= prev_ph[1] - px <= tol:
                loaded_highs.append((prev_ph[0], prev_ph[1]))
            prev_ph = (bar, px)

        # CONSUMED: a loaded low traded through → arm a long, that push is the block
        consumed = [lv for lv in loaded_lows if b.l[i] < lv[1]]
        if consumed and live is None:
            for lv in consumed:
                loaded_lows.remove(lv)
            live = Setup(dir="long", arm_bar=i, block_bar=i, block=b.l[i])
            funnel[1] += 1
            continue
        for lv in consumed:
            loaded_lows.remove(lv)

        if live is None:
            continue

        # the block keeps deepening while price is still pushing down
        if live.stage == 1 and b.l[i] < live.block:
            live.block, live.block_bar = b.l[i], i

        if i - live.arm_bar > expiry and live.stage < 5:
            live.notes.append("expired")
            drops["expired"] += 1
            live = None
            continue

        # ── step 2 · a level loads above the block ───────────────────
        if live.stage == 1:
            fresh = [lv for lv in loaded_lows if lv[0] > live.arm_bar and lv[1] > live.block]
            if fresh:
                live.loaded_bar, live.loaded = fresh[-1]
                live.stage = 2
                funnel[2] += 1

        # ── step 3 · inducement — a prior high gets taken ────────────
        elif live.stage == 2:
            if b.l[i] < live.block:
                drops["block broken"] += 1
                live = None
                continue
            if prev_ph and b.h[i] > prev_ph[1] and i > live.loaded_bar:
                live.induce_bar = i
                live.stage = 3
                funnel[3] += 1

        # ── step 4 · the target is built ─────────────────────────────
        elif live.stage == 3:
            if b.l[i] < live.block:
                drops["block broken"] += 1
                live = None
                continue
            above = [lv for lv in loaded_highs if lv[0] >= live.loaded_bar and lv[1] > b.c[i]]
            if above:
                live.el_bar, live.el = above[-1]
                live.stage = 4
                funnel[4] += 1

        # ── step 5 · entry — the loaded low is stabbed ───────────────
        elif live.stage == 4:
            if b.l[i] < live.block:
                drops["block broken"] += 1
                live = None
                continue
            if b.l[i] < live.loaded:
                entry = live.loaded
                stop = live.block - (a[i] or 0.0) * buf_mult
                risk = entry - stop
                if risk <= 0:
                    drops["risk <= 0"] += 1
                    live = None
                    continue
                rr = (live.el - entry) / risk
                if rr < min_rr:  # the liquidity block's VETO
                    live.notes.append(f"rr {rr:.1f} below floor")
                    drops["rr below floor"] += 1
                    live = None
                    continue
                live.entry_bar, live.entry, live.stop, live.rr = i, entry, stop, rr
                live.stage = 5
                funnel[5] += 1
                # walk forward for the outcome
                live.outcome, live.exit_bar = "open", min(i + max_hold, len(b) - 1)
                for j in range(i + 1, min(i + max_hold, len(b))):
                    if b.l[j] <= stop:
                        live.outcome, live.exit_bar = "stop", j
                        break
                    if b.h[j] >= live.el:
                        live.outcome, live.exit_bar = "target", j
                        break
                done.append(live)
                live = None

    if live is not None:
        drops["live at end of data"] += 1
    return done, funnel, drops


# ─────────────────────────────── control ───────────────────────────────


def control(b: Bars, setups: list, *, seed: int = 7, reps: int = 40) -> dict:
    """Score a MATCHED RANDOM control against the real setups.

    🔴 THE CONTROL IS THE TOOL — the same rule `trigger_edge.py` carries, and this scanner needed
    it more, not less. XAUUSD ran ~1,200 → ~4,300 across the cached window, so ANY long-biased
    rule shows a profit here and a harness with no control will happily report one. The question
    is never "did longs win", it is "did they beat a random long with the same stop and the same
    target".

    Each real setup is replayed `reps` times from a RANDOM bar, holding three things fixed:
      · direction        — else the control is just the drift with a different name
      · stop DISTANCE    — a tighter stop is hit more often, whatever the signal says
      · target DISTANCE  — so the planned R, and therefore the breakeven hit rate, is identical

    Only the ENTRY BAR is randomised. That isolates "when" from "how far", which is the only
    thing the model claims to know.

    Returns the control hit rate and expectancy, and the z of the real result against it.
    """
    import random

    rng = random.Random(seed)
    n = len(b)

    real_wins = sum(1 for s in setups if s.outcome == "target")
    real_n = sum(1 for s in setups if s.outcome in ("target", "stop"))

    hits = trials = 0
    exp_sum = 0.0
    for s in setups:
        if s.outcome not in ("target", "stop"):
            continue
        risk = abs(s.entry - s.stop)
        reward = abs(s.el - s.entry)
        if risk <= 0:
            continue
        long_ = s.dir == "long"
        for _ in range(reps):
            i = rng.randrange(50, max(51, n - 2))
            e = b.c[i]
            stop = e - risk if long_ else e + risk
            targ = e + reward if long_ else e - reward
            for j in range(i + 1, min(i + 400, n)):
                stopped = b.l[j] <= stop if long_ else b.h[j] >= stop
                hit = b.h[j] >= targ if long_ else b.l[j] <= targ
                # Stop first: a bar holding both books the LOSS, same as the real scan.
                if stopped:
                    trials += 1
                    exp_sum -= 1.0
                    break
                if hit:
                    trials += 1
                    hits += 1
                    exp_sum += reward / risk
                    break

    if not trials or not real_n:
        return {}
    p = hits / trials
    # z of the real win count against the control rate — the harness's own significance test
    import math

    sd = math.sqrt(max(real_n * p * (1 - p), 1e-12))
    z = (real_wins - real_n * p) / sd
    return {
        "ctrl_hit": p,
        "ctrl_exp": exp_sum / trials,
        "trials": trials,
        "real_hit": real_wins / real_n,
        "z": z,
    }


# ─────────────────────────────── chart ───────────────────────────────


def draw(b: Bars, s: Setup, out: Path, pad: int = 40) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    lo = max(0, s.arm_bar - pad)
    hi = min(len(b) - 1, s.exit_bar + 15)
    xs = range(lo, hi + 1)

    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=150)
    for i in xs:
        up = b.c[i] >= b.o[i]
        col = "#111827" if up else "#dc2626"
        ax.plot([i, i], [b.l[i], b.h[i]], color=col, lw=0.7, zorder=2)
        ax.add_patch(
            Rectangle(
                (i - 0.34, min(b.o[i], b.c[i])),
                0.68,
                max(abs(b.c[i] - b.o[i]), 1e-9),
                facecolor="#ffffff" if up else "#dc2626",
                edgecolor=col,
                lw=0.7,
                zorder=3,
            )
        )

    def hline(y, c, label, ls="-"):
        ax.hlines(y, lo, hi, color=c, lw=1.6, linestyles=ls, zorder=4)
        ax.text(hi, y, f"  {label}", color=c, fontsize=8.5, va="center", fontweight="bold")

    hline(s.el, "#15803d", f"TARGET  {s.el:.2f}")
    hline(s.loaded, "#6d28d9", f"LOADED LOW / ENTRY  {s.entry:.2f}")
    hline(s.block, "#dc2626", f"BLOCK  {s.block:.2f}", ls="--")
    hline(s.stop, "#dc2626", f"STOP  {s.stop:.2f}", ls=":")

    def mark(bar, y, txt, c, dy):
        ax.annotate(
            txt,
            (bar, y),
            xytext=(bar, y + dy),
            color=c,
            fontsize=8.5,
            fontweight="bold",
            ha="center",
            arrowprops=dict(arrowstyle="->", color=c, lw=1.2),
            zorder=6,
        )

    rng = max(b.h[i] for i in xs) - min(b.l[i] for i in xs)
    mark(s.block_bar, b.l[s.block_bar], "1 · ARM\nblock created", "#dc2626", -rng * 0.09)
    mark(s.loaded_bar, b.l[s.loaded_bar], "2 · loads", "#6d28d9", -rng * 0.05)
    if s.induce_bar:
        mark(s.induce_bar, b.h[s.induce_bar], "3 · inducement", "#b45309", rng * 0.06)
    mark(s.el_bar, b.h[s.el_bar], "4 · target built", "#15803d", rng * 0.05)
    mark(s.entry_bar, s.entry, "5 · ENTRY", "#6d28d9", -rng * 0.13)
    ax.scatter([s.entry_bar], [s.entry], s=55, color="#6d28d9", zorder=7)

    won = s.outcome == "target"
    ax.axvspan(s.entry_bar, s.exit_bar, color="#15803d" if won else "#dc2626", alpha=0.07, zorder=1)

    ticks = [i for i in xs if i % max(1, (hi - lo) // 9) == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([b.t[i].strftime("%d %b\n%H:%M") for i in ticks], fontsize=7.5)
    ax.set_xlim(lo - 1, hi + 1)
    ax.tick_params(axis="y", labelsize=7.5)
    ax.grid(axis="y", color="#e5e7eb", lw=0.5)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_title(
        f"XAUUSD  ·  {b.t[s.arm_bar]:%Y-%m-%d %H:%M} → {b.t[s.exit_bar]:%d %b %H:%M}"
        f"   ·   {s.rr:.1f}R planned   ·   {s.outcome.upper()}",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=12,
    )
    fig.tight_layout()
    fig.savefig(out, facecolor="white")
    plt.close(fig)


# ─────────────────────────────── cli ───────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--tf", default="M15")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--pivot-len", type=int, default=2)
    p.add_argument("--tol-mult", type=float, default=0.5, help="ATR(50) x this = 'respects'")
    p.add_argument("--buf-mult", type=float, default=0.10)
    p.add_argument("--min-rr", type=float, default=2.0)
    p.add_argument("--expiry", type=int, default=200)
    p.add_argument("--max-hold", type=int, default=400)
    p.add_argument("--chart", type=int, default=0, help="render the N best-RR winners")
    p.add_argument("--outdir", default="backtest/reports/loaded_level")
    p.add_argument("--side", choices=("long", "short", "both"), default="both")
    p.add_argument(
        "--control",
        type=int,
        default=0,
        help="reps per setup for the matched random control (try 40)",
    )
    args = p.parse_args()

    b = load(args.symbol, args.tf, args.start, args.end)
    print(f"{len(b):,} {args.tf} bars   {b.t[0]:%Y-%m-%d} → {b.t[-1]:%Y-%m-%d}")

    kw = dict(
        pivot_len=args.pivot_len,
        tol_mult=args.tol_mult,
        buf_mult=args.buf_mult,
        min_rr=args.min_rr,
        expiry=args.expiry,
        max_hold=args.max_hold,
    )

    longs, f_l, d_l = scan(b, **kw)
    # SHORTS are the same code on mirrored bars — see invert(). Never a hand-written branch.
    bi = invert(b)
    shorts, f_s, d_s = scan(bi, **kw)
    shorts = [unmirror(s) for s in shorts]

    if args.side == "long":
        setups, funnel, drops = longs, f_l, d_l
    elif args.side == "short":
        setups, funnel, drops = shorts, f_s, d_s
    else:
        setups = sorted(longs + shorts, key=lambda s: s.entry_bar)
        funnel = {k: f_l[k] + f_s[k] for k in f_l}
        drops = {k: d_l[k] + d_s[k] for k in d_l}

    print(f"\nFUNNEL  (tol = ATR(50) x {args.tol_mult}, min RR {args.min_rr}, side {args.side})")
    names = {
        1: "1 armed (loaded level consumed)",
        2: "2 a level loaded past the block",
        3: "3 inducement",
        4: "4 target built",
        5: "5 ENTRY taken",
    }
    for k in sorted(funnel):
        extra = ""
        if args.side == "both":
            extra = f"   (L {f_l[k]:,} / S {f_s[k]:,})"
        print(f"  {names[k]:<38} {funnel[k]:>6,}{extra}")

    print("\nWHY SETUPS DIED")
    for k, v in sorted(drops.items(), key=lambda kv: -kv[1]):
        if v:
            print(f"  {k:<38} {v:>6,}")

    if not setups:
        print("\nno completed setups")
        return
    wins = [s for s in setups if s.outcome == "target"]
    losses = [s for s in setups if s.outcome == "stop"]
    opens = [s for s in setups if s.outcome == "open"]
    net = len(wins) * 0 + sum(s.rr for s in wins) - len(losses)
    print(
        f"\nOUTCOMES  {len(setups)} trades"
        f"  ({sum(1 for s in setups if s.dir == 'long')}L / "
        f"{sum(1 for s in setups if s.dir == 'short')}S)"
    )
    print(f"  target {len(wins):>4}   stop {len(losses):>4}   still open {len(opens):>4}")
    if wins or losses:
        print(
            f"  hit rate {len(wins) / (len(wins) + len(losses)) * 100:.1f}%"
            f"   ·   planned R sum {net:+.1f}   ·   median planned {sorted(s.rr for s in setups)[len(setups) // 2]:.1f}R"
        )

    if args.control:
        for name, group in (
            ("long", [s for s in setups if s.dir == "long"]),
            ("short", [s for s in setups if s.dir == "short"]),
            ("all", setups),
        ):
            if not group:
                continue
            c = control(b, group, reps=args.control)
            if not c:
                continue
            exp_real = sum(s.rr for s in group if s.outcome == "target") - sum(
                1 for s in group if s.outcome == "stop"
            )
            n_res = sum(1 for s in group if s.outcome in ("target", "stop"))
            print(
                f"\nCONTROL · {name}   ({c['trials']:,} random entries, matched on "
                f"direction + stop distance + target distance)"
            )
            print(
                f"  real     hit {c['real_hit'] * 100:5.1f}%   expectancy {exp_real / n_res:+.3f}R"
            )
            print(f"  random   hit {c['ctrl_hit'] * 100:5.1f}%   expectancy {c['ctrl_exp']:+.3f}R")
            print(
                f"  edge over control  {(c['real_hit'] - c['ctrl_hit']) * 100:+.1f} pts   z {c['z']:+.2f}"
            )

    if args.chart:
        out = ROOT / args.outdir
        out.mkdir(parents=True, exist_ok=True)
        # deliberately a MIX — a model shown only on its winners has no known hit rate
        n_w = max(1, args.chart // 2)
        picks = sorted(wins, key=lambda s: -s.rr)[:n_w] + losses[: args.chart - n_w]
        picks = picks or setups[: args.chart]
        for n, s in enumerate(picks, 1):
            f = out / f"setup_{n}_{b.t[s.entry_bar]:%Y%m%d_%H%M}_{s.outcome}.png"
            draw(b, s, f)
            print(f"  drew {f.relative_to(ROOT)}   {s.rr:.1f}R  {s.outcome}")


if __name__ == "__main__":
    main()
