#!/usr/bin/env python3
"""h4_sweep_optimize.py — take the edge `h4_sweep_profile.py` FOUND and try to make it pay.

The profile study established two things and this tool starts from both:

  1. Continuation after an H4 sweep is dead — it flips sign between the halves. Closed.
  2. The FADE is real: +0.073R gross over 1,464 trades, same sign in both halves, on both
     level definitions. It just does not clear costs at the geometry that study used.

So the question here is not "is there an edge" — it is "what geometry monetises the one
we measured". The profile only ever varied the entry retrace, and EVERY value it tried
(0.5 / 0.618 / 0.786) makes the stop SMALLER, which pushes cost drag the wrong way on an
edge whose entire problem is cost. And every exit was a fixed R ceiling, which SOS Fade Run 9
already proved caps exactly what pays. Both of those are opened up here.

It imports the event builder and the single trade implementation from
`h4_sweep_profile.py` — there is one simulator, so a sweep result and a published study
number cannot drift apart.

Scoring, and why each column is here:

  exp R net    per-trade expectancy AFTER a round-trip cost. The only expectancy worth
               reading — the stop is a few dollars of gold and a fixed cost is a large
               slice of 1R.
  1st / 2nd    the halves. A sign flip is regime, not edge; this repo has been fooled by
               one before (bos Runs 3-4) and rows that flip are flagged, not ranked.
  sum R        total, in R. Never dollars — a fixed-%-risk strategy compounds, so a
               dollar ranking measures recency.
  equity ×     what `--risk-pct` of equity per trade compounds to over the window, and
               the max drawdown ON THAT CURVE. This is the "does it actually make money"
               column. A big multiple next to a 70% drawdown is not a strategy.

Usage:
    command-center/backend/.venv/bin/python backtest/tools/h4_sweep_optimize.py geometry
    ... exit --top 25
    ... filter
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import replace
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.tools.h4_sweep_profile import (  # noqa: E402
    M15Index,
    TradePlan,
    build_rows,
    load_bars,
    pivot_levels,
    prev_levels,
    run_trade,
    table,
)

HORIZONS = (1, 2, 4, 8)


# ---------------------------------------------------------------------------
# scoring


def score(
    rows: list[dict], h4, m15: M15Index, plan: TradePlan, cost: float, risk_pct: float, mid: int
) -> dict | None:
    """Replay one plan over one event set and reduce it to a row of the results table."""
    taken = []
    for r in rows:
        t = run_trade(r, h4, m15, plan, cost)
        if t and t.get("r") is not None:
            taken.append((r, t))
    if len(taken) < 20:
        return None

    taken.sort(key=lambda p: p[0]["time"])
    nets = [t["r_net"] for _, t in taken]
    h1 = [t["r_net"] for r, t in taken if r["year"] < mid]
    h2 = [t["r_net"] for r, t in taken if r["year"] >= mid]

    # Compounding curve at a fixed % of equity per trade — the honest "profit" read, and
    # the only place drawdown means anything. R alone hides the fact that a 60% drawdown
    # at 2% risk and at 10% risk are different businesses.
    eq, peak, dd = 1.0, 1.0, 0.0
    for n in nets:
        eq *= 1.0 + risk_pct / 100.0 * n
        if eq <= 0:
            eq, dd = 0.0, 1.0
            break
        peak = max(peak, eq)
        dd = max(dd, 1.0 - eq / peak)

    years = (taken[-1][0]["year"] - taken[0][0]["year"]) or 1
    return {
        "n": len(taken),
        "per_yr": len(taken) / years,
        "win": 100 * sum(1 for x in nets if x > 0) / len(nets),
        "exp": statistics.fmean(nets),
        "sum": sum(nets),
        "h1": statistics.fmean(h1) if h1 else float("nan"),
        "h2": statistics.fmean(h2) if h2 else float("nan"),
        "n1": len(h1),
        "n2": len(h2),
        "equity": eq,
        "dd": 100 * dd,
        "robust": bool(h1 and h2 and statistics.fmean(h1) > 0 and statistics.fmean(h2) > 0),
    }


def render(results: list[tuple[str, dict]], top: int, risk_pct: float) -> str:
    ranked = sorted(results, key=lambda p: p[1]["sum"], reverse=True)[:top]
    body = []
    for label, s in ranked:
        body.append(
            [
                ("✅ " if s["robust"] else "⚠ ") + label,
                str(s["n"]),
                f"{s['per_yr']:.0f}",
                f"{s['win']:.0f}",
                f"{s['exp']:+.3f}",
                f"{s['sum']:+.1f}",
                f"{s['h1']:+.3f}/{s['n1']}",
                f"{s['h2']:+.3f}/{s['n2']}",
                f"{s['equity']:.2f}x",
                f"{s['dd']:.0f}%",
            ]
        )
    return table(
        [
            "config",
            "n",
            "/yr",
            "win %",
            "exp R net",
            "sum R",
            "1st half",
            "2nd half",
            f"equity @{risk_pct:g}%",
            "max DD",
        ],
        body,
    )


# ---------------------------------------------------------------------------
# phases


def phase_geometry(base: TradePlan):
    """Where does 1R come from? The profile only shrank it; these grow it.

    `entry_mode="market"` takes the confirmation close and risks the whole leg — worst
    price, biggest 1R, always fills. A shallow retrace sits between that and the old 0.5.
    An ATR stop decouples risk from the leg entirely.
    """
    yield "market entry · stop=leg", replace(base, entry_mode="market", stop_model="leg")
    for rt in (0.236, 0.382, 0.5):
        yield (
            f"limit {rt} · stop=leg",
            replace(base, entry_mode="limit", retrace=rt, stop_model="leg"),
        )
    for mult in (1.0, 1.5, 2.0):
        yield (
            f"market entry · stop={mult}×ATR",
            replace(base, entry_mode="market", stop_model="atr", stop_atr=mult),
        )
        yield (
            f"limit 0.382 · stop={mult}×ATR",
            replace(base, entry_mode="limit", retrace=0.382, stop_model="atr", stop_atr=mult),
        )


def phase_exit(base: TradePlan):
    """Fixed ceilings vs runners. SOS Fade Run 9 measured that a hard TP costs 20%+ of net
    because the handful of trades that go far carry the book; Run 8 measured that a
    ratchet trail banked 43% → 53% of each run at identical drawdown. Both are tested
    here rather than assumed to transfer."""
    # Ranked monotonically up to 24 on the first run, so the ladder is extended until it
    # turns over. A grid whose winner sits on its own edge has not been searched.
    # Every variant sets the trail EXPLICITLY. Inheriting it from `base` made the
    # "no trail" rows silent duplicates of the 1% ones on the first run — the two were
    # byte-identical in the output, which is what gave it away.
    flat = dict(trail_mode="none", trail_val=0.0, be_at_r=0.0)
    for h in (4, 8, 12, 24, 36, 48, 72):
        for tr in (1.0, 2.0, 3.0, 5.0):
            yield f"h{h} · fixed {tr:g}R", replace(base, horizon=h, target_r=tr, **flat)
        yield f"h{h} · runner, no trail", replace(base, horizon=h, target_r=0.0, **flat)
        for tv in (0.5, 1.0, 2.0, 3.0):
            yield (
                f"h{h} · runner, {tv:g}% trail",
                replace(base, horizon=h, target_r=0.0, be_at_r=0.0, trail_mode="pct", trail_val=tv),
            )
        for tv in (1.0, 2.0, 3.0, 4.0):
            yield (
                f"h{h} · runner, {tv:g}×ATR trail",
                replace(base, horizon=h, target_r=0.0, be_at_r=0.0, trail_mode="atr", trail_val=tv),
            )
        yield (
            f"h{h} · runner, BE@1R, 1% trail",
            replace(base, horizon=h, target_r=0.0, be_at_r=1.0, trail_mode="pct", trail_val=1.0),
        )


FILTERS = {
    "all": lambda r: True,
    "wick only": lambda r: r["sweep_class"] == "wick",
    "break only": lambda r: r["sweep_class"] == "break",
    "Asia sweep": lambda r: r["session"] == "Asia",
    "London sweep": lambda r: r["session"] == "London",
    "NY sweep": lambda r: r["session"] == "NY",
    "London+NY": lambda r: r["session"] in ("London", "NY"),
    "high sweep (short)": lambda r: r["side"] == "high",
    "low sweep (long)": lambda r: r["side"] == "low",
    "with H4 trend": lambda r: r["trend_agrees"] is False,  # fade runs WITH trend when
    # the sweep ran against it
    "against H4 trend": lambda r: r["trend_agrees"] is True,
    "deep poke": lambda r: (r["depth_atr"] or 0) >= 0.25,
    "shallow poke": lambda r: (r["depth_atr"] or 0) < 0.25,
}


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("phase", choices=["geometry", "exit", "filter", "detail"])
    ap.add_argument(
        "--filters", default="all", help="detail phase: comma-joined filter names, ANDed together"
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--cost", type=float, default=0.30)
    ap.add_argument("--risk-pct", type=float, default=2.0)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--defs", default="prev,pivot2,pivot3")
    # The phase-2/3 baseline: set from what phase 1 wins, via flags, so no winner is
    # hardcoded into the file and a re-run cannot silently inherit a stale choice.
    ap.add_argument("--entry-mode", default="market")
    ap.add_argument("--retrace", type=float, default=0.382)
    ap.add_argument("--stop-model", default="leg")
    ap.add_argument("--stop-atr", type=float, default=1.0)
    ap.add_argument("--horizon", type=int, default=12)
    ap.add_argument("--target-r", type=float, default=0.0)
    ap.add_argument("--trail-mode", default="pct")
    ap.add_argument("--trail-val", type=float, default=1.0)
    ap.add_argument("--be-at-r", type=float, default=0.0)
    args = ap.parse_args()

    h4 = load_bars(args.symbol, "H4")
    m15 = M15Index(load_bars(args.symbol, "M15"))

    defs = {}
    for name in args.defs.split(","):
        name = name.strip()
        levels = (
            prev_levels(h4) if name == "prev" else pivot_levels(h4, int(name.removeprefix("pivot")))
        )
        rows = build_rows(h4, levels, HORIZONS)
        defs[name] = [r for r in rows if r["is_sweep"]]

    years = sorted({r["year"] for rs in defs.values() for r in rs})
    mid = years[len(years) // 2]

    base = TradePlan(
        direction=-1,
        entry_mode=args.entry_mode,
        retrace=args.retrace,
        stop_model=args.stop_model,
        stop_atr=args.stop_atr,
        horizon=args.horizon,
        target_r=args.target_r,
        trail_mode=args.trail_mode,
        trail_val=args.trail_val,
        be_at_r=args.be_at_r,
    )

    print(f"# H4 sweep — phase: {args.phase}")
    print(
        f"\n{args.symbol} · {len(h4)} H4 bars · fade direction · cost ${args.cost:g} "
        f"round trip · {args.risk_pct:g}% risk/trade · halves split at {mid}"
    )
    print("\n✅ = positive in BOTH halves. ⚠ = one half negative — regime, not edge.\n")

    results: list[tuple[str, dict]] = []
    if args.phase == "detail":
        # One config, broken out by YEAR. The half-split cannot test a long-vs-short skew
        # on gold, because BOTH halves of 2018-2026 are the same bull market — only the
        # individual flat/down years can. This is that view.
        names = [n.strip() for n in args.filters.split(",")]
        for dname, rows in defs.items():
            sub = [r for r in rows if all(FILTERS[n](r) for n in names)]
            print(f"\n## {dname} · {' + '.join(names)} · {base}\n")
            per_year = []
            for y in sorted({r["year"] for r in sub}):
                s = score(
                    [r for r in sub if r["year"] == y], h4, m15, base, args.cost, args.risk_pct, mid
                )
                if s:
                    per_year.append((str(y), s))
                else:
                    yr = [r for r in sub if r["year"] == y]
                    ts = [
                        t
                        for t in (run_trade(r, h4, m15, base, args.cost) for r in yr)
                        if t and t.get("r") is not None
                    ]
                    if ts:
                        rs = [t["r_net"] for t in ts]
                        per_year.append(
                            (
                                f"{y} (small n)",
                                {
                                    "n": len(ts),
                                    "per_yr": len(ts),
                                    "win": 100 * sum(1 for x in rs if x > 0) / len(rs),
                                    "exp": statistics.fmean(rs),
                                    "sum": sum(rs),
                                    "h1": float("nan"),
                                    "h2": float("nan"),
                                    "n1": 0,
                                    "n2": 0,
                                    "equity": 1.0,
                                    "dd": 0.0,
                                    "robust": False,
                                },
                            )
                        )
            body = [
                [lbl, str(s["n"]), f"{s['win']:.0f}", f"{s['exp']:+.3f}", f"{s['sum']:+.1f}"]
                for lbl, s in per_year
            ]
            print(table(["year", "n", "win %", "exp R net", "sum R net"], body))
            total = score(sub, h4, m15, base, args.cost, args.risk_pct, mid)
            if total:
                print(
                    f"\n**Total: {total['n']} trades · {total['exp']:+.3f} exp R net · "
                    f"{total['sum']:+.1f}R · {total['equity']:.2f}x @{args.risk_pct:g}% "
                    f"· {total['dd']:.0f}% max DD**"
                )
        return 0

    if args.phase == "filter":
        for dname, rows in defs.items():
            for fname, fn in FILTERS.items():
                sub = [r for r in rows if fn(r)]
                s = score(sub, h4, m15, base, args.cost, args.risk_pct, mid)
                if s:
                    results.append((f"{dname} · {fname}", s))
        print(f"Baseline plan: {base}\n")
    else:
        gen = phase_geometry if args.phase == "geometry" else phase_exit
        for dname, rows in defs.items():
            for label, plan in gen(base):
                s = score(rows, h4, m15, plan, args.cost, args.risk_pct, mid)
                if s:
                    results.append((f"{dname} · {label}", s))

    print(render(results, args.top, args.risk_pct))
    robust = [r for r in results if r[1]["robust"] and r[1]["sum"] > 0]
    print(f"\n{len(robust)} of {len(results)} configs are net-positive in BOTH halves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
