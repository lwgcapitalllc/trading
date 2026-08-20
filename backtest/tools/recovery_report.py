#!/usr/bin/env python3
"""recovery_report.py — replay a strategy, then replay the loss-recovery rule over its losses.

    python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14

Prints the primary alone and the primary plus recovery, both COSTED, and prices the addition
against the only honest alternative — turning `exec_risk_pct` up on the strategy you already own.

⚠ Both sides carry costs. Charging the recovery leg and not the primary is rule 11 broken: the
run you re-create for comparison has to carry everything that decides what it is measured on, and
the primary's median hold is 0.3 days against the recovery's ~4, so the bias is not small.

⚠ Every number this prints is a LAB finding. There is no Pine twin and no parity gate.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "engines"), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


import itertools  # noqa: E402

from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402


class CachedStructure(LossRecoveryEngine):
    """The engine with its structure replay done once for a whole grid.

    Every variant in a sweep shares `major_length`, so the canonical engine would return
    byte-identical events on each pass and 144 replays of 186,910 bars buy nothing. ⚠ The shared
    length is ASSERTED rather than assumed — a variant that changed it would otherwise be handed
    another config's structure and score a rule nobody ran.
    """

    def __init__(self, config, cache):
        super().__init__(config)
        self._cache = cache

    def _replay_structure(self, bars):
        assert self.config.major_length == self._cache[0], "grid changed major_length"
        return self._cache[1]


def curve(seq, risk_pct):
    """Compounded balance multiple and peak-to-trough drawdown for a sequence of R."""
    bal = peak = 1.0
    dd = 0.0
    for r in seq:
        bal = max(bal * (1.0 + (risk_pct / 100.0) * r), 1e-9)
        peak = max(peak, bal)
        dd = max(dd, 1.0 - bal / peak)
    return sum(seq), bal, 100.0 * dd


def risk_for_dd(seq, target_dd):
    """The risk % whose max drawdown equals `target_dd`. Bisection, because compounding at a
    fixed fraction is non-linear and there is no closed form."""
    lo, hi = 0.01, 60.0
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        if curve(seq, mid)[2] < target_dd:
            lo = mid
        else:
            hi = mid
    return lo, curve(seq, lo)[1]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", type=int, default=15)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--risk-pct", type=float, default=10.0, help="the primary's risk per trade")
    ap.add_argument("--profile", default="puprime_ecn", help="cost profile, or 'none'")
    ap.add_argument(
        "--size",
        type=float,
        default=None,
        help="recovery size as a fraction of normal risk (default: config's 0.25)",
    )
    ap.add_argument(
        "--longs-only",
        action="store_true",
        help="⚠ FITTED: this cut was chosen after seeing which direction won",
    )
    ap.add_argument("--sweep", action="store_true", help="sweep recovery size in 5%% steps")
    ap.add_argument(
        "--search",
        action="store_true",
        help="the actual SEARCH: every stop placement the engines can name, then every way of "
        "trailing what survives — including banking a partial at +1R and letting the rest run",
    )
    ap.add_argument(
        "--stops",
        action="store_true",
        help="where should the stop GO: the break leg, or the losing trade's own entry? Prints "
        "the stop in DOLLARS beside every result, plus a percent-ratchet sweep",
    )
    ap.add_argument(
        "--soft-curve",
        action="store_true",
        help="the soft stop alone, in fine steps, split into halves — is the best value a "
        "plateau or a spike?",
    )
    ap.add_argument(
        "--exits",
        action="store_true",
        help="grid the EXIT rules instead: soft stop, structural invalidation, early "
        "breakeven step, and the lock trigger/destination split",
    )
    args = ap.parse_args()

    from strategies.python.mpc_sos_fade import LAB_STRATEGY

    bars = BarSource().load(args.symbol, args.tf, args.start, args.end)
    S, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    cfg = dataclasses.replace(C(fill_model="bar", symbol=args.symbol), exec_secondary=False)
    strat = S(config=cfg, initial_capital=10_000.0)
    strat.run(bars, warmup=args.warmup)
    trades = strat.execution.trades
    idx = bars.index

    prof = None if args.profile == "none" else PROFILES[args.profile]

    def cost_r(direction, i0, j, risk_price):
        """swap + spread + commission for one trade, in R. Lot size cancels out of the ratio."""
        if prof is None or prof.swap is None:
            return 0.0
        sw = prof.swap
        n = 0
        day = idx[i0].date()
        while day < idx[j].date():
            day += timedelta(days=1)
            if day.weekday() >= 5:  # the broker books no rollover at the weekend
                continue
            n += 3 if day.weekday() == sw.triple_weekday else 1
        return (
            (sw.per_lot_per_night(direction) * n) / (risk_price * sw.contract_size)
            - prof.spread / risk_price
            - 2.0 * prof.commission_per_side_per_lot / (risk_price * sw.contract_size)
        )

    base = sorted(
        (idx[t.exit_index], t.r + cost_r(t.dir, t.entry_index, t.exit_index, t.stop_distance))
        for t in trades
    )
    bseq = [r for _, r in base]
    e0, b0, dd0 = curve(bseq, args.risk_pct)
    gross0 = sum(t.r for t in trades)
    losses = [t for t in trades if t.r < -cfg.exec_scratch_r]
    print(f"{args.symbol} {args.tf}m  {args.start} → {args.end}   {len(bars):,} bars")
    print(f"cost profile: {args.profile}\n")
    print(f"PRIMARY  {len(trades)} trades, {len(losses)} losses")
    print(
        f"  gross {gross0:+.1f}R → net {e0:+.1f}R    {b0:,.0f}x @ {args.risk_pct:g}%   maxDD {dd0:.1f}%\n"
    )

    rcfg = RecoveryConfig(
        enabled=True,
        both_directions=not args.longs_only,
        risk_fraction=args.size if args.size is not None else RecoveryConfig().risk_fraction,
        scratch_r=cfg.exec_scratch_r,
    )
    recs = LossRecoveryEngine(rcfg).run(bars, trades)
    pend = LossRecoveryEngine(rcfg).pending(bars, trades)
    # Costed at FULL size, then scaled — so a size sweep does not re-walk the bars.
    costed = [
        (idx[t.exit_index], t.r + cost_r(t.direction, t.entry_index, t.exit_index, t.risk))
        for t in recs
    ]
    wins = sum(1 for _, r in costed if r > 0)
    holds = sorted((t.exit_index - t.entry_index) for t in recs)
    print(f"RECOVERY  {len(recs)} trades  ({len(pend)} losses never got their CHoCH)")
    print(
        f"  net at FULL size {sum(r for _, r in costed):+.1f}R   win {100 * wins / max(len(recs), 1):.0f}%   "
        f"median hold {holds[len(holds) // 2] if holds else 0} bars"
    )
    locked = sum(1 for t in recs if t.locked)
    print(f"  {locked} of {len(recs)} reached +{rcfg.lock_at_r:g}R and locked the recovery in\n")

    if args.stops or args.search:
        cache = (rcfg.major_length, LossRecoveryEngine(rcfg)._replay_structure(bars))
        f = rcfg.risk_fraction
        # The round trip in PRICE units — what a stop has to clear before the signal says anything.
        rt = (
            0.0
            if prof is None
            else prof.spread + 2.0 * prof.commission_per_side_per_lot / prof.swap.contract_size
        )

        def measure(**kw):
            v = dataclasses.replace(rcfg, **kw)
            eng = CachedStructure(v, cache)
            rs = eng.run(bars, trades)
            ref = eng.refused(bars, trades)
            cs = [
                (idx[t.exit_index], t.r + cost_r(t.direction, t.entry_index, t.exit_index, t.risk))
                for t in rs
            ]
            vals = [r for _, r in cs]
            stops = sorted(t.risk for t in rs)
            med = stops[len(stops) // 2] if stops else float("nan")
            lv = [r for r in vals if r < 0]
            seq = [r for _, r in sorted(base + [(ts, r * f) for ts, r in cs])]
            e, b, dd = curve(seq, args.risk_pct)
            _, bb = risk_for_dd(bseq, dd)
            return {
                "n": len(rs),
                "ref": len(ref),
                "stop": med,
                "cost": 100.0 * rt / med if med else float("nan"),
                "net": sum(vals),
                "win": 100.0 * sum(1 for r in vals if r > 0) / max(len(vals), 1),
                "avg_loss": sum(lv) / max(len(lv), 1),
                "dd": dd,
                "ratio": b / bb,
            }

        hdr = (
            f"  {'variant':<34} {'took':>5} {'refused':>8} {'med stop':>9} {'cost/R':>7} "
            f"{'net R':>8} {'win':>5} {'avg loss':>9} {'maxDD':>7} {'vs dial':>8}"
        )

        def row(label, m):
            print(
                f"  {label:<34} {m['n']:>5} {m['ref']:>8} ${m['stop']:>8.2f} {m['cost']:>6.1f}% "
                f"{m['net']:>+7.1f}R {m['win']:>4.0f}% {m['avg_loss']:>+8.2f}R {m['dd']:>6.1f}% "
                f"{m['ratio']:>7.2f}x"
            )

        if args.search:
            print(f"1. WHERE THE STOP GOES — everything else shipped.  round trip = ${rt:.2f}\n")
            print(hdr)
            row("break leg  (shipped)", measure())
            for f_ in (0.75, 0.5, 0.25):
                row(f"break leg x {f_:g}", measure(stop_mode="leg_frac", stop_leg_frac=f_))
            row("last confirmed swing", measure(stop_mode="swing"))
            row("the CHoCH bar's own extreme", measure(stop_mode="signal_bar"))
            for m_ in (1.0, 1.5, 2.0, 3.0):
                row(f"{m_:g} x ATR(14)   [control]", measure(stop_mode="atr", stop_atr_mult=m_))
            row("the losing trade's entry", measure(stop_mode="loss_entry"))

            print("\n\n2. NOT ENDING AT EXACTLY +1R — on the shipped break-leg stop\n")
            print(hdr)
            row("lock 1R->1R + swings (shipped)", measure())
            for fr in (0.25, 0.5, 0.75):
                row(
                    f"take {fr:.0%} at +1R, rest to breakeven",
                    measure(partial_at_r=1.0, partial_frac=fr, lock_at_r=1.0, lock_to_r=0.0),
                )
            row(
                "take 50% at +1R, rest keeps +1R stop",
                measure(partial_at_r=1.0, partial_frac=0.5),
            )
            for fr in (0.5,):
                for pa in (0.75, 1.5, 2.0):
                    row(
                        f"take {fr:.0%} at +{pa:g}R, rest to breakeven",
                        measure(partial_at_r=pa, partial_frac=fr, lock_to_r=0.0),
                    )
            for m_ in (1.0, 2.0, 3.0, 4.0):
                row(
                    f"lock 1R->1R + {m_:g} ATR chandelier",
                    measure(trail_atr_mult=m_, trail_swings=False),
                )
            row(
                "take 50% at +1R + 3 ATR chandelier",
                measure(
                    partial_at_r=1.0,
                    partial_frac=0.5,
                    lock_to_r=0.0,
                    trail_atr_mult=3.0,
                    trail_swings=False,
                ),
            )

            print("\n\n3. THE BEST STOPS x THE BEST EXITS\n")
            print(hdr)
            stops = {
                "break leg": {},
                "leg x0.5": dict(stop_mode="leg_frac", stop_leg_frac=0.5),
                "swing": dict(stop_mode="swing"),
                "2 ATR": dict(stop_mode="atr", stop_atr_mult=2.0),
            }
            exits = {
                "lock+swings": {},
                "50% at 1R -> BE + swings": dict(partial_at_r=1.0, partial_frac=0.5, lock_to_r=0.0),
                "50% at 1R -> BE + 3ATR": dict(
                    partial_at_r=1.0,
                    partial_frac=0.5,
                    lock_to_r=0.0,
                    trail_atr_mult=3.0,
                    trail_swings=False,
                ),
                "soft cut -0.3R + lock": dict(soft_stop_r=0.3),
            }
            out = []
            for sn, sk in stops.items():
                for en, ek in exits.items():
                    out.append((f"{sn}  |  {en}", measure(**sk, **ek)))
            for label, m in sorted(out, key=lambda x: -x[1]["net"]):
                row(label, m)

            print("\n🔴 `med stop` and `cost/R` come BEFORE the R column. R = profit / stop, so a")
            print("   model that makes small stops inflates every R without earning a dollar.")
            print("⚠ The ATR rows are the CONTROL — structure-blind by construction. A structural")
            print("   stop that cannot beat them is not being paid for its structure.")
            print("\n⚠ LAB ONLY — no Pine twin, no parity gate, not wired to any bot.")
            return 0

        print(f"WHERE THE STOP GOES.  round trip = ${rt:.2f} in price\n")
        print(hdr)
        row("break leg  (shipped)", measure())
        row("losing trade's entry", measure(stop_mode="loss_entry"))
        print()
        for sv in (0.5, 0.3):
            row(f"break leg + soft cut -{sv:g}R", measure(soft_stop_r=sv))
            row(f"loss entry + soft cut -{sv:g}R", measure(stop_mode="loss_entry", soft_stop_r=sv))

        print("\n\nTHE PERCENT RATCHET, on each stop\n")
        print(hdr)
        for mode in ("structural", "loss_entry"):
            tag = "break leg" if mode == "structural" else "loss entry"
            row(f"{tag} + swing trail (shipped)", measure(stop_mode=mode))
            for pct in (0.05, 0.1, 0.25, 0.5, 1.0):
                row(
                    f"{tag} + {pct:g}% ratchet, no swings",
                    measure(stop_mode=mode, trail_pct=pct, trail_swings=False),
                )
            print()

        print("🔴 Read `med stop` and `cost/R` BEFORE the R column. R = profit / stop, so a model")
        print("   that makes small stops inflates every R in the book without earning a dollar.")
        print("⚠ `refused` is not `pending` — the CHoCH DID arrive; the stop was unusable.")
        print("\n⚠ LAB ONLY — no Pine twin, no parity gate, not wired to any bot.")
        return 0

    if args.soft_curve:
        cache = (rcfg.major_length, LossRecoveryEngine(rcfg)._replay_structure(bars))
        f = rcfg.risk_fraction
        mid = idx[len(bars) // 2]

        print("THE SOFT STOP ALONE — everything else shipped\n")
        print(
            f"  {'cut at':>8} {'net R':>8} {'1st half':>9} {'2nd half':>9} {'less top 5':>11} "
            f"{'win':>6} {'balance':>9} {'maxDD':>7} {'vs dial':>7}"
        )
        steps = [None] + [x / 100 for x in range(15, 105, 5)]
        for sv in steps:
            v = dataclasses.replace(rcfg, soft_stop_r=sv)
            rs = CachedStructure(v, cache).run(bars, trades)
            cs = [
                (idx[t.exit_index], t.r + cost_r(t.direction, t.entry_index, t.exit_index, t.risk))
                for t in rs
            ]
            vals = [r for _, r in cs]
            h1 = sum(r for ts, r in cs if ts < mid)
            h2 = sum(r for ts, r in cs if ts >= mid)
            seq = [r for _, r in sorted(base + [(ts, r * f) for ts, r in cs])]
            e, b, dd = curve(seq, args.risk_pct)
            _, bb = risk_for_dd(bseq, dd)
            label = "structural" if sv is None else f"-{sv:g}R"
            # Delete the five biggest winners. A rule whose whole result is a handful of trades
            # has been measured on those trades, not on the rule.
            top5 = sum(vals) - sum(sorted(vals)[-5:])
            print(
                f"  {label:>8} {sum(vals):>+7.1f}R {h1:>+8.1f}R {h2:>+8.1f}R {top5:>+10.1f}R "
                f"{100.0 * sum(1 for r in vals if r > 0) / max(len(vals), 1):>5.0f}% "
                f"{b:>8,.0f}x {dd:>6.1f}% {b / bb:>6.2f}x"
            )
        print("\n  Both halves positive at every step is the thing to look for. A single tall")
        print("  step between two short ones is a coincidence this record happens to contain.")
        print("\n⚠ LAB ONLY — no Pine twin, no parity gate, not wired to any bot.")
        return 0

    if args.exits:
        cache = (rcfg.major_length, LossRecoveryEngine(rcfg)._replay_structure(bars))
        f = rcfg.risk_fraction

        def score(**kw):
            v = dataclasses.replace(rcfg, **kw)
            rs = CachedStructure(v, cache).run(bars, trades)
            cs = [
                (idx[t.exit_index], t.r + cost_r(t.direction, t.entry_index, t.exit_index, t.risk))
                for t in rs
            ]
            vals = [r for _, r in cs]
            losses_v = [r for r in vals if r < 0]
            seq = [r for _, r in sorted(base + [(ts, r * f) for ts, r in cs])]
            e, b, dd = curve(seq, args.risk_pct)
            _, bb = risk_for_dd(bseq, dd)
            return {
                "n": len(rs),
                "net": sum(vals),
                "win": 100.0 * sum(1 for r in vals if r > 0) / max(len(vals), 1),
                "avg_loss": sum(losses_v) / max(len(losses_v), 1),
                "worst": min(vals) if vals else 0.0,
                "bal": b,
                "dd": dd,
                "ratio": b / bb,
            }

        def row(label, m):
            print(
                f"  {label:<34} {m['net']:>+7.1f}R {m['win']:>5.0f}% {m['avg_loss']:>+7.2f}R "
                f"{m['worst']:>+7.2f}R {m['bal']:>9,.0f}x {m['dd']:>6.1f}% {m['ratio']:>6.2f}x"
            )

        hdr = (
            f"  {'variant':<34} {'net R':>8} {'win':>6} {'avg loss':>8} {'worst':>8} "
            f"{'balance':>9} {'maxDD':>7} {'vs dial':>7}"
        )
        shipped = score()
        print("ONE LEVER AT A TIME — everything else at the shipped default\n")
        print(hdr)
        row("shipped  (structural, lock 1→1)", shipped)
        print()
        for v in (0.75, 0.5, 0.4, 0.3, 0.25):
            row(f"soft stop  cut at -{v:g}R", score(soft_stop_r=v))
        print()
        row("exit on opposite CHoCH", score(invalidate_on_choch=True))
        print()
        for a, t in ((0.5, 0.0), (0.5, 0.25), (0.75, 0.0), (1.0, 0.5)):
            row(f"early step  at +{a:g}R → +{t:g}R", score(be_at_r=a, be_to_r=t))
        print()
        for a, t in ((1.5, 1.0), (2.0, 1.0), (2.0, 1.5), (1.0, 0.5)):
            row(f"lock  at +{a:g}R → +{t:g}R", score(lock_at_r=a, lock_to_r=t))

        print("\n\nEVERY COMBINATION — top 15 by return per unit of drawdown\n")
        soft = [None, 0.75, 0.5, 0.4, 0.3, 0.25]
        inval = [False, True]
        bes = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.25), (0.75, 0.0)]
        locks = [(1.0, 1.0), (1.5, 1.0), (2.0, 1.0)]
        out = []
        for sv, iv, (ba, bt), (la, lt) in itertools.product(soft, inval, bes, locks):
            m = score(
                soft_stop_r=sv,
                invalidate_on_choch=iv,
                be_at_r=ba,
                be_to_r=bt,
                lock_at_r=la,
                lock_to_r=lt,
            )
            label = (
                f"{'struct' if sv is None else f'-{sv:g}R':>6} "
                f"{'choch' if iv else '  ·  ':>5} "
                f"{'·' if ba == 0 else f'be {ba:g}→{bt:g}':>8} "
                f"lock {la:g}→{lt:g}"
            )
            out.append((m["ratio"], label, m))
        out.sort(key=lambda x: -x[0])
        print(hdr)
        for _, label, m in out[:15]:
            row(label, m)
        print(f"\n  {len(out)} combinations. Shipped scores {shipped['ratio']:.2f}x.")
        print("\n⚠ LAB ONLY — no Pine twin, no parity gate, not wired to any bot.")
        print("⚠ Every row above is FITTED to this record by construction — a grid picks its own")
        print("  winner. Read the LEVER table for what each rule does; read the grid for whether")
        print("  the best combination is a cliff or a plateau.")
        return 0

    sizes = [x / 100 for x in range(5, 105, 5)] if args.sweep else [rcfg.risk_fraction]
    print(
        f"  {'size':>6} {'net R':>9} {'balance':>11} {'maxDD':>7} {'primary at that DD':>20} {'':>8}"
    )
    for f in sizes:
        seq = [r for _, r in sorted(base + [(ts, r * f) for ts, r in costed])]
        e, b, dd = curve(seq, args.risk_pct)
        br, bb = risk_for_dd(bseq, dd)
        ratio = b / bb
        tag = "recovery" if ratio > 1 else "primary "
        flag = " ≤ today's DD" if dd <= dd0 + 1e-9 else ""
        print(
            f"  {f:>5.0%} {e:>+8.1f}R {b:>10,.0f}x {dd:>6.1f}% "
            f"{br:>6.2f}% → {bb:>9,.0f}x  {tag} {max(ratio, 1 / ratio):.2f}x{flag}"
        )

    if not args.sweep:
        print("\n  (--sweep for the full size curve)")
    print("\n⚠ LAB ONLY — no Pine twin, no parity gate, not wired to any bot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
