#!/usr/bin/env python3
"""sweep_confluence.py — which liquidity sweeps carry a directional bias, and which don't?

Aaron's question (2026-08-08), building on `session_relay_scan.py`: he is after a
SEQUENTIAL confluence system — the same read, done over and over — and wants to know
whether a session sweep and a DAILY sweep landing together precede a reversal, and more
broadly which combinations of session / daily / weekly / H4 liquidity precede one.

WHAT THIS MEASURES, AND WHAT IT REFUSES TO

It measures a BIAS: after price grabs liquidity, does it tend to go the other way? It
does that with the crudest tradeable framing available, on purpose —

    a sell-side sweep is a LONG. Entry at the sweep bar's close, stop under the swept
    extreme, target a multiple of that risk, resolved bar by bar over a fixed horizon.
    A bar holding both stop and target books the STOP.

No structure filter, no fair-value gap, no fib, no entry model, no sizing. Every one of
those would improve the numbers and none of them is what is being asked. The question is
whether the SWEEP carries information — if it does not, no confluence stacked on top of
it will rescue it.

THE CONTROL IS THE POINT

"63% of daily sweeps reverse" is not a finding until you know what an ordinary bar does
under the identical trade construction. So this samples NON-sweep bars the same way and
prints them as `control` in the same table. Every bucket is to be read against that row
and against `ALL sweeps`, never on its own. A bucket that merely matches the control has
no edge, however good its win rate looks.

READ THE BUCKET TABLE AS A WHOLE, NOT AS A LEADERBOARD

Every combination present in the data is printed, including the ones that lose and the
ones with too few observations to mean anything (flagged `thin`). The tool prints how
many buckets it tested. Picking the top row of a table of twenty and calling it an edge
is how a study talks itself into one — the `H1 / H2` split columns are there so a bucket
that only worked in one half of the history is visible as such.

⚠ OBSERVATIONS ARE NOT INDEPENDENT. Sweeps cluster; two events four bars apart in the
same session are largely the same trade. Nothing here blocks an overlapping event,
because blocking them would let a `session-only` event mask a `session+daily` one and
corrupt the very comparison being made. The per-bucket `gap` column is the median bars
between consecutive events, so the correlation is visible rather than assumed.

Usage:
    python3 backtest/tools/sweep_confluence.py
    python3 backtest/tools/sweep_confluence.py --cluster-bars 0        # same-bar only
    python3 backtest/tools/sweep_confluence.py --target-r 3 --horizon 192
    python3 backtest/tools/sweep_confluence.py --out backtest/reports/sweep_confluence
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from liquidity import LiquidityEngine              # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402
from sessions import SessionEngine                 # noqa: E402

CACHE = _ROOT / "backtest" / "cache"
UTC = dt.timezone.utc

# The four liquidity FAMILIES a sweep can belong to. The engine's own `kind` string, kept
# verbatim so this tool can never disagree with the engine about what a level is.
#   session  Asia / London / NY high & low   (wick through)
#   daily    PDH / PDL                        (wick through)
#   weekly   PWH / PWL                        (body close through)
#   h4       the previous-H4 sweep targets    (wick through)
FAMILIES = ("session", "daily", "weekly", "h4")


# --------------------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------------------

class Frame:
    """The bar arrays plus everything the three engines said, indexed by bar."""

    def __init__(self) -> None:
        self.time: list[dt.datetime] = []
        self.high: list[float] = []
        self.low: list[float] = []
        self.close: list[float] = []
        self.atr: list[float] = []
        # bar index -> the swept levels on that bar, split by side
        self.swept_low: dict[int, list] = defaultdict(list)
        self.swept_high: dict[int, list] = defaultdict(list)
        # bar index -> the session(s) running
        self.sessions: dict[int, tuple[str, ...]] = {}
        # bar index -> "bull_sos" / "bear_sos" fired here
        self.sos: dict[int, set[str]] = defaultdict(set)
        # bar index -> structure direction going INTO this bar (+1 up, -1 down, 0 unknown)
        self.struct_dir: list[int] = []


def replay(symbol: str, tf: str) -> Frame:
    """One contiguous pass. The engines are streaming state machines built from completed
    prior periods, so the frame is never pre-filtered — a gap would corrupt the levels
    silently rather than raise."""
    path = CACHE / f"{symbol}__{tf}.csv"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path}")

    f = Frame()
    structure, liq, sess_eng = StructureEngine(), LiquidityEngine(), SessionEngine()
    prev_close: float | None = None
    tr_run: float | None = None       # Wilder ATR(14), running
    direction = 0

    with path.open(newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            stamp = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            o, h, l, c = (float(row["open"]), float(row["high"]),
                          float(row["low"]), float(row["close"]))
            ts_ms = int(stamp.timestamp() * 1000)

            ext = structure.update(Bar(index=i, open=o, high=h, low=l, close=c)).external
            sess = sess_eng.update(i, ts_ms, h, l)
            liq_ev = liq.update(i, ts_ms, h, l, c)

            # Wilder ATR(14) on true range. Seeded on the first bar with the bar range.
            tr = h - l if prev_close is None else max(h - l, abs(h - prev_close), abs(l - prev_close))
            tr_run = tr if tr_run is None else (tr_run * 13 + tr) / 14
            prev_close = c

            f.time.append(stamp)
            f.high.append(h)
            f.low.append(l)
            f.close.append(c)
            f.atr.append(tr_run)
            f.struct_dir.append(direction)   # BEFORE this bar's break is applied

            if ext.bull_sos:
                f.sos[i].add("bull_sos")
                direction = 1
            if ext.bear_sos:
                f.sos[i].add("bear_sos")
                direction = -1

            f.sessions[i] = tuple(n for n, on in (("Asia", sess.in_asia),
                                                  ("London", sess.in_london),
                                                  ("NY", sess.in_ny)) if on)
            for lvl in liq_ev.mitigated:
                if lvl.kind == "pwc":       # a reference close, never a swept level
                    continue
                (f.swept_low if lvl.side == "low" else f.swept_high)[i].append(lvl)
    return f


# --------------------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------------------

def _families(frame: Frame, i: int, cluster: int, bullish: bool) -> tuple[set[str], list[str]]:
    """Which liquidity families were swept at bar `i` or in the `cluster` bars before it.

    The lookback is what makes "together" mean something looser than "on the same bar" —
    at the default 16 bars (4h on M15) a daily low taken at the London open and a session
    low taken an hour later count as one grab. `--cluster-bars 0` restricts it to the
    same bar.
    """
    table = frame.swept_low if bullish else frame.swept_high
    fams: set[str] = set()
    names: list[str] = []
    for j in range(max(0, i - cluster), i + 1):
        for lvl in table.get(j, ()):
            fams.add(lvl.kind)
            names.append(lvl.name)
    return fams, names


def _fade(frame: Frame, i: int, bullish: bool, cluster: int, horizon: int,
          target_r: float, min_atr_frac: float) -> dict | None:
    """The crude fade. Returns None when the trade is unmeasurable rather than guessing.

    The stop sits beyond the swept EXTREME of the cluster window, so it is the price that
    says the grab failed. A near-zero risk would manufacture enormous R from one tick of
    noise — this repo has been bitten by exactly that arithmetic (`qty = risk / dist`) —
    so anything tighter than `min_atr_frac` of ATR(14) is REFUSED and counted, never
    silently clamped to a workable number.
    """
    entry = frame.close[i]
    lo = max(0, i - cluster)
    if bullish:
        stop = min(frame.low[lo:i + 1])
        risk = entry - stop
    else:
        stop = max(frame.high[lo:i + 1])
        risk = stop - entry

    if risk <= 0:
        return None
    if frame.atr[i] > 0 and risk < min_atr_frac * frame.atr[i]:
        return {"skipped": "risk_too_tight"}
    if i + horizon >= len(frame.close):
        return None                      # not enough forward bars to resolve honestly

    side = 1 if bullish else -1
    target = entry + side * risk * target_r
    for j in range(i + 1, i + horizon + 1):
        hit_stop = frame.low[j] <= stop if bullish else frame.high[j] >= stop
        hit_target = frame.high[j] >= target if bullish else frame.low[j] <= target
        if hit_stop:                     # stop wins a bar holding both — the pessimistic
            return {"r": -1.0, "outcome": "stop"}   # read, and the only honest one on bars
        if hit_target:
            return {"r": target_r, "outcome": "target"}
    drift = side * (frame.close[i + horizon] - entry) / risk
    return {"r": drift, "outcome": "timed_out"}


def _sos_follows(frame: Frame, i: int, bullish: bool, window: int) -> bool:
    """Did structure actually FLIP the way the sweep implies, within `window` bars?

    This is the bridge to the sequential playbook: a sweep with a bias is interesting, a
    sweep that reliably produces the opposing SOS is a setup trigger.
    """
    want = "bull_sos" if bullish else "bear_sos"
    return any(want in frame.sos.get(j, ()) for j in range(i + 1, min(i + window + 1, len(frame.close))))


def build_events(frame: Frame, args) -> tuple[list[dict], Counter]:
    """Every bar on which liquidity was taken, priced, tagged and measured."""
    events: list[dict] = []
    skips: Counter = Counter()

    for bullish in (True, False):
        table = frame.swept_low if bullish else frame.swept_high
        for i in sorted(table):
            fams, names = _families(frame, i, args.cluster_bars, bullish)
            if not fams:
                continue
            res = _fade(frame, i, bullish, args.cluster_bars, args.horizon,
                        args.target_r, args.min_atr_frac)
            if res is None:
                skips["unmeasurable"] += 1
                continue
            if "skipped" in res:
                skips[res["skipped"]] += 1
                continue
            events.append({
                "time": frame.time[i],
                "index": i,
                "direction": "long" if bullish else "short",
                "bucket": "+".join(sorted(fams, key=FAMILIES.index)),
                "families": fams,
                "levels": " ".join(sorted(set(names))),
                "sessions": "+".join(frame.sessions.get(i, ())) or "none",
                # Was the grab AGAINST the prevailing structure? A sell-side sweep in an
                # up-trend is a pullback into demand; in a down-trend it is continuation.
                "with_trend": (frame.struct_dir[i] == (1 if bullish else -1)),
                "sos_follows": _sos_follows(frame, i, bullish, args.sos_bars),
                "r": res["r"],
                "outcome": res["outcome"],
            })

    # TWO controls, because one of them is not a fair comparison and it took a run to see it.
    #
    #   control-any  any bar that swept nothing. The obvious control, and it is BIASED in
    #                the sweeps' favour being read as a fair fight: a sweep bar has by
    #                definition just printed a fresh extreme, so its stop sits on a brand
    #                new low, while a random bar's close sits anywhere in its range. That
    #                compares stop PLACEMENT as much as it compares liquidity.
    #
    #   control-ext  a bar that made a fresh `cluster`-bar extreme and swept NO tracked
    #                level. Same geometry as a sweep, same stop placement, no liquidity.
    #                This is the control that isolates the variable being studied, and it
    #                is the one to read the table against.
    swept_bars = set(frame.swept_low) | set(frame.swept_high)
    for bullish in (True, False):
        series = frame.low if bullish else frame.high
        pick = min if bullish else max
        for i in range(args.cluster_bars, len(frame.close), args.control_every):
            # Only bar `i` itself must be sweep-free. Requiring the whole cluster window
            # clean was tried first and yielded n=7 over eight years — because an H4 level
            # is taken somewhere in almost every 4-hour window, which is itself the
            # finding that makes `h4` the working baseline rather than a confluence.
            if i in swept_bars:
                continue
            # Did this bar itself make the window's extreme? That is what a sweep bar does,
            # and matching it is what makes the control a control rather than a different
            # trade with a different stop.
            fresh = series[i] == pick(series[max(0, i - args.cluster_bars):i + 1])
            res = _fade(frame, i, bullish, args.cluster_bars, args.horizon,
                        args.target_r, args.min_atr_frac)
            if res is None or "skipped" in res:
                continue
            events.append({
                "time": frame.time[i], "index": i,
                "direction": "long" if bullish else "short",
                "bucket": "control-ext" if fresh else "control-any",
                "families": set(), "levels": "",
                "sessions": "+".join(frame.sessions.get(i, ())) or "none",
                "with_trend": (frame.struct_dir[i] == (1 if bullish else -1)),
                "sos_follows": _sos_follows(frame, i, bullish, args.sos_bars),
                "r": res["r"], "outcome": res["outcome"],
            })

    events.sort(key=lambda e: e["index"])
    return events, skips


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------

def _stats(rows: list[dict]) -> dict:
    rs = [r["r"] for r in rows]
    gaps = [b["index"] - a["index"] for a, b in zip(rows, rows[1:])]
    return {
        "n": len(rs),
        "win": 100 * sum(1 for r in rs if r > 0) / len(rs),
        "exp": statistics.fmean(rs),
        "tot": sum(rs),
        "sos": 100 * sum(1 for r in rows if r["sos_follows"]) / len(rows),
        "gap": int(statistics.median(gaps)) if gaps else 0,
    }


def _split_exp(rows: list[dict], mid: dt.datetime) -> tuple[float, float]:
    """Expectancy in the first vs second half of the history. A bucket that only worked in
    one half is a bucket that has not been tested — this is the cheapest possible check
    and it is here because the table invites cherry-picking."""
    a = [r["r"] for r in rows if r["time"] < mid]
    b = [r["r"] for r in rows if r["time"] >= mid]
    return (statistics.fmean(a) if a else float("nan"),
            statistics.fmean(b) if b else float("nan"))


def report(frame: Frame, events: list[dict], skips: Counter, args) -> None:
    live = [e for e in events if not e["bucket"].startswith("control")]
    controls = [e for e in events if e["bucket"].startswith("control")]
    mid = frame.time[len(frame.time) // 2]

    print()
    print("=" * 96)
    print("LIQUIDITY SWEEP CONFLUENCE — does a grab carry a directional bias?")
    print("=" * 96)
    print(f"  {args.symbol} {args.tf}  {len(frame.time):,} bars  "
          f"({frame.time[0]:%Y-%m-%d} -> {frame.time[-1]:%Y-%m-%d}, UTC)")
    print(f"  fade: entry at the sweep close, stop beyond the swept extreme, "
          f"target {args.target_r:g}R, horizon {args.horizon} bars")
    print(f"  cluster window {args.cluster_bars} bars   min risk {args.min_atr_frac:g}xATR14   "
          f"SOS window {args.sos_bars} bars")
    print(f"  sweep events {len(live):,}   controls {len(controls):,}   "
          f"refused {sum(skips.values()):,} {dict(skips) or ''}")
    print(f"  history split at {mid:%Y-%m-%d} for the H1/H2 columns")

    h4_share = 100 * sum(1 for e in live if "h4" in e["families"]) / max(1, len(live))
    print(f"  NOTE h4 levels are present in {h4_share:.0f}% of all sweeps — the previous-H4 "
          f"target regenerates every 4h,")
    print("       so treat 'h4' as background, not confluence. The MARGINAL block below "
          "is what answers the question.")

    for direction in ("long", "short"):
        rows = [e for e in live if e["direction"] == direction]
        ctrl = [e for e in controls if e["direction"] == direction]
        buckets = defaultdict(list)
        for e in rows:
            buckets[e["bucket"]].append(e)

        print()
        side = "sell-side grabs, faded LONG" if direction == "long" else "buy-side grabs, faded SHORT"
        print(f"  {direction.upper()}  ({side})")
        print(f"    {'':<28}{'n':>7}{'win%':>7}{'exp R':>8}{'total R':>9}"
              f"{'H1 exp':>8}{'H2 exp':>8}{'SOS%':>7}{'gap':>6}")

        def line(label: str, rs: list[dict]) -> None:
            if not rs:
                return
            s = _stats(rs)
            h1, h2 = _split_exp(rs, mid)
            thin = "  thin" if s["n"] < args.min_n else ""
            print(f"    {label:<28}{s['n']:>7}{s['win']:>7.1f}{s['exp']:>8.3f}{s['tot']:>9.1f}"
                  f"{h1:>8.3f}{h2:>8.3f}{s['sos']:>7.1f}{s['gap']:>6}{thin}")

        line("ALL sweeps", rows)
        for cname in ("control-ext", "control-any"):
            line(f"{cname} (baseline)", [e for e in ctrl if e["bucket"] == cname])

        # ── The direct question, asked as a MARGINAL rather than as a bucket ──
        # "Does a daily sweep add anything to a session sweep?" is only answerable by
        # holding the session sweep fixed and toggling the daily one. A bucket table
        # cannot say it, because every bucket differs in more than one way at once.
        print(f"    {'-' * 78}")
        print(f"    MARGINAL — does adding the daily level to a session grab change anything?")
        sess = [e for e in rows if "session" in e["families"]]
        line("session, NO daily", [e for e in sess if "daily" not in e["families"]])
        line("session + daily", [e for e in sess if "daily" in e["families"]])
        dly = [e for e in rows if "daily" in e["families"]]
        line("daily, NO session", [e for e in dly if "session" not in e["families"]])

        # ── SOS%, and the trap that has to be stepped around to read it ──
        #
        # A bullish SOS is a CHoCH: the engine only raises it when structure was already
        # DOWN. So "sell-side sweep while the trend is down" has a structurally higher
        # SOS% than "…while the trend is up" for a reason that has nothing to do with
        # liquidity — in the second case the event is close to impossible. Comparing the
        # two would be near-tautological and would read as a strong finding.
        #
        # The valid comparison holds the trend state FIXED and varies the confluence.
        against = [e for e in rows if not e["with_trend"]]
        print(f"    {'-' * 78}")
        print(f"    AGAINST-TREND ONLY — the stratum where an opposing SOS can actually fire.")
        print(f"    Confluence varies, trend state held fixed, so SOS% is comparable down "
              f"this block.")
        line("h4 only (baseline)", [e for e in against if e["families"] == {"h4"}])
        line("session, NO daily", [e for e in against
                                   if "session" in e["families"] and "daily" not in e["families"]])
        line("session + daily", [e for e in against if {"session", "daily"} <= e["families"]])

        print(f"    {'-' * 78}")
        print(f"    every bucket present (h4 is background — see the note above)")
        for name in sorted(buckets, key=lambda b: -_stats(buckets[b])["exp"]):
            line(name, buckets[name])

    print(f"\n  {len({e['bucket'] for e in live})} distinct buckets tested per direction — "
          f"read the table whole, not its top row.")


def write_csv(events: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["time", "index", "direction", "bucket", "levels", "sessions",
            "with_trend", "sos_follows", "r", "outcome"]
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for e in events:
            w.writerow({**e, "time": f"{e['time']:%Y-%m-%d %H:%M}"})
    print(f"  wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--cluster-bars", type=int, default=16,
                    help="how many bars back still counts as 'together' (default 16 = 4h)")
    ap.add_argument("--horizon", type=int, default=96, help="bars to resolve the fade (default 96 = 1 day)")
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--min-atr-frac", type=float, default=0.25,
                    help="refuse a fade whose stop is tighter than this x ATR(14)")
    ap.add_argument("--sos-bars", type=int, default=48,
                    help="bars in which an opposing SOS counts as 'structure confirmed'")
    ap.add_argument("--control-every", type=int, default=97,
                    help="sample one no-sweep control bar every N bars (97 is prime, so it "
                         "does not lock onto the 96-bar day and sample one clock time)")
    ap.add_argument("--min-n", type=int, default=100, help="below this a bucket is flagged thin")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    frame = replay(args.symbol, args.tf)
    events, skips = build_events(frame, args)
    report(frame, events, skips, args)
    if args.out:
        write_csv(events, args.out)


if __name__ == "__main__":
    main()
