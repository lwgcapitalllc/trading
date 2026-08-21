#!/usr/bin/env python3
"""recovery_stack.py — the strategy and its loss-recovery leg on ONE account.

    python backtest/tools/recovery_stack.py --start 2018-09-14 --end 2026-08-14

**The question this exists to answer, and why the lab could not.** The Command Center toggle
(`exec_recovery`) appends recovery trades to a finished book: they size off the running balance,
but the primary never sizes off THEM. So recovery profit sits beside the curve instead of lifting
it, and over a run that compounds thousands of times an early gain is rounding by the end.
Measured on run `236e206d0142`, the identical trades are worth **+3.8%** that way against **+44.8%**
on one compounding balance. **A real account is one balance. That toggle answers a question nobody
asked, and it always will — the design is deliberate, so that flipping it cannot move a
parity-gated A+ trade.**

This tool answers the real one. Both legs go through `backtest/portfolio/` — one balance every leg
sizes against, one live risk budget they compete for, one merged clock, and a contention log of
every shrink and refusal. It prints three views and they are three different claims:

  * **solo** — each leg alone on its own full account. The control, and an UPPER BOUND.
  * **screen** — the two solo runs added together. Nothing could block anything; also an upper
    bound, and NOT what an account does.
  * **shared** — one balance, one budget. The only row that describes an account you could open.

⚠ Every number is a LAB finding. This rule has no Pine twin and no parity gate.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "engines"), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from loss_recovery import RecoveryConfig  # noqa: E402
from loss_recovery.leg import RecoveryLeg, RecoveryLegConfig  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402
from backtest.portfolio.account import PortfolioAccount, SoloAccount  # noqa: E402
from backtest.portfolio.legs import StrategyLeg, build_leg  # noqa: E402
from backtest.portfolio.simulator import simulate  # noqa: E402
from backtest.replay.loop import iter_bars  # noqa: E402
from backtest.replay.stack import EngineStack  # noqa: E402

PRIMARY, RECOVERY = "aplus", "recovery"


class RecoveryStrategyLeg(StrategyLeg):
    """`StrategyLeg` for a leg that has to be told the frame's horizon.

    The recovery's time stop is measured in DAYS, so it needs the bar rate and the frame's last
    index — facts about the run, not about the rule. A strategy leg gets its bar duration set for
    it here for the same reason.
    """

    def __init__(self, name: str, strategy, df) -> None:
        super().__init__(name, strategy, df)
        per_day = 86_400_000.0 / max(int(strategy.execution.bar_ms) or 1, 1)
        strategy.set_horizon(len(df.index) - 1, per_day)


def _bars_per_day(df) -> float:
    step = df.index.to_series().diff().min().total_seconds()
    return 86_400.0 / step if step else 96.0


def build_legs(cfg_primary, rule, df, *, account, capital, profile, strategy_cls):
    """Both legs bound to `account`, with the recovery WATCHING the primary's live trade list.

    🔴 The watch is the whole coupling and it must be the LIST OBJECT, not a copy: the recovery
    arms when a primary trade closes, so it reads a list that grows under it. A copy taken here
    would be empty forever and the leg would produce an empty book that reads exactly like a rule
    that found no setups.
    """
    strategy = build_leg(
        PRIMARY,
        strategy_cls,
        cfg_primary,
        df,
        account=account,
        initial_capital=capital,
        cost_profile=profile,
    )
    rec = RecoveryLeg(
        RecoveryLegConfig(
            rule=rule,
            point_value=cfg_primary.point_value,
            unit_risk_pct=cfg_primary.exec_risk_pct,
            major_length=strategy.strategy.engine_config().major_length,
            bars_per_day=_bars_per_day(df),
        ),
        initial_capital=capital,
        cost_profile=profile,
        account=account,
        leg=RECOVERY,
    )
    rec.watch(strategy.strategy.execution.trades)
    return strategy, RecoveryStrategyLeg(RECOVERY, rec, df)


def total_r(trades) -> float:
    """Sum of R. 🔴 The invariant that says a SIZING change was a sizing change and nothing else.

    R is normalised to each trade's own risk, so moving a leg onto a shared balance re-sizes every
    position and must leave every R byte-identical. A shared-vs-solo R difference is either the cap
    genuinely biting (and then it is in the refusal log) or a decision moved — and the second is a
    bug wearing the first's clothes. Compare R, never net dollars, across anything sharing a
    balance.
    """
    return sum(float(t.r) for t in trades)


def curve(trades, capital):
    """Closing balance and peak-to-trough drawdown over the CLOSED-trade balance."""
    bal = peak = capital
    dd = 0.0
    for t in sorted(trades, key=lambda x: (x.exit_ms, x.entry_ms)):
        bal += t.pnl_usd
        peak = max(peak, bal)
        dd = max(dd, (peak - bal) / peak if peak > 0 else 0.0)
    return bal, 100 * dd


def solo(strategy_cls, cfg, df, capital, profile, rule=None):
    """One leg alone on its own full account — the control every comparison needs.

    Without it a difference in the shared book mixes *the cap bit* with *the shared balance
    re-sized everything*, and nothing afterwards separates the two.
    """
    acct = SoloAccount(balance=capital)
    if rule is None:
        leg = build_leg(
            PRIMARY,
            strategy_cls,
            cfg,
            df,
            account=acct,
            initial_capital=capital,
            cost_profile=profile,
        )
        for bar in iter_bars(df):
            leg.step(bar)
        return leg.strategy.execution.trades
    # The recovery alone still needs a primary to lose — run one on a private account so the
    # source book exists, and let only the recovery book onto the account being measured.
    src_acct = SoloAccount(balance=capital)
    src = build_leg(
        PRIMARY,
        strategy_cls,
        cfg,
        df,
        account=src_acct,
        initial_capital=capital,
        cost_profile=profile,
    )
    rec = RecoveryLeg(
        RecoveryLegConfig(
            rule=rule,
            point_value=cfg.point_value,
            unit_risk_pct=cfg.exec_risk_pct,
            major_length=src.strategy.engine_config().major_length,
            bars_per_day=_bars_per_day(df),
        ),
        initial_capital=capital,
        cost_profile=profile,
        account=acct,
        leg=RECOVERY,
    )
    rec.watch(src.strategy.execution.trades)
    rec.set_horizon(len(df.index) - 1, _bars_per_day(df))
    stack = EngineStack(rec.stack_config())
    for bar in iter_bars(df):
        src.step(bar)
        rec.step(stack.step(bar))
    return rec.execution.trades


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", type=int, default=15)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--risk-cap-pct",
        type=float,
        default=10.0,
        help="account-level cap, PERCENT of the live balance",
    )
    ap.add_argument(
        "--aplus-risk-pct",
        type=float,
        default=None,
        help="override the strategy's own per-trade risk %%. 🔴 The lever that decides "
        "this whole question: A+ ships at 10%% and the cap defaults to 10%%, so "
        "A+ ALONE fills the budget and any second leg can only subtract. Lower "
        "this (or raise the cap) to ask whether the recovery is worth ROOM, "
        "rather than whether it is worth taking room off A+.",
    )
    ap.add_argument(
        "--on-contention",
        choices=("share", "refuse"),
        default="share",
        help="THE RULE, stated rather than implied. 'share' grants a later entry "
        "whatever room is left (the account's shrink-to-fit). 'refuse' turns any "
        "entry that cannot be granted in full into an outright refusal, which is "
        "the repo's 'risk is never layered' reading. Both land in the refusal "
        "log; neither is silent.",
    )
    ap.add_argument(
        "--size",
        type=float,
        default=None,
        help="recovery risk as a fraction of a normal trade (default: the rule's)",
    )
    ap.add_argument(
        "--profile",
        default="puprime_ecn",
        help="cost tier, or 'none'. A run that prices nothing must say so.",
    )
    args = ap.parse_args()

    from strategies.python.mpc_sos_fade import LAB_STRATEGY

    S, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    profile = None if args.profile == "none" else PROFILES[args.profile]
    over = {"exec_secondary": False, "exec_recovery": False}
    if args.aplus_risk_pct is not None:
        over["exec_risk_pct"] = args.aplus_risk_pct
    cfg = dataclasses.replace(C(fill_model="bar", symbol=args.symbol), **over)
    rule = RecoveryConfig(
        enabled=True,
        scratch_r=cfg.exec_scratch_r,
        risk_fraction=args.size if args.size is not None else RecoveryConfig().risk_fraction,
    )
    cap = args.capital
    print(f"{args.symbol} {args.tf}m  {args.start} → {args.end}   {len(df):,} bars")
    print(
        f"cost profile: {args.profile}   account cap: {args.risk_cap_pct:g}%   "
        f"A+ risk: {cfg.exec_risk_pct:g}%   "
        f"recovery size: {rule.risk_fraction:g}x of that "
        f"(= {cfg.exec_risk_pct * rule.risk_fraction:g}%)"
    )
    head = cfg.exec_risk_pct * (1.0 + rule.risk_fraction)
    if head > args.risk_cap_pct:
        print(
            f"⚠ both legs at full size want {head:g}% against a {args.risk_cap_pct:g}% cap — "
            f"the budget CANNOT hold them, so every overlap shrinks A+ by construction."
        )
    print()

    # ── solo controls ────────────────────────────────────────────────────────────────────
    solo_p = solo(S, cfg, df, cap, profile)
    solo_r = solo(S, cfg, df, cap, profile, rule=rule)
    bp, dp = curve(solo_p, cap)
    br, dr = curve(solo_r, cap)
    print(
        f"{'SOLO  A+ alone':38} {len(solo_p):4} trades   ${bp:14,.0f}  {bp / cap:9,.0f}x  "
        f"maxDD {dp:5.1f}%   {total_r(solo_p):+8.2f}R"
    )
    print(
        f"{'SOLO  recovery alone':38} {len(solo_r):4} trades   ${br:14,.0f}  {br / cap:9,.0f}x  "
        f"maxDD {dr:5.1f}%   {total_r(solo_r):+8.2f}R"
    )
    bs, ds = curve(list(solo_p) + list(solo_r), cap)
    print(
        f"{'SCREEN  both, private accounts':38} {len(solo_p) + len(solo_r):4} trades   "
        f"${bs:14,.0f}  {bs / cap:9,.0f}x  maxDD {ds:5.1f}%   ⚠ upper bound\n"
    )

    # ── the shared account ───────────────────────────────────────────────────────────────
    # 🔴 THE CONCURRENCY RULE, and it is a CHOICE this tool makes visible rather than a default
    # nobody can see. `entry_floor_pct` is the account's own knob for it: an entry granted less
    # than that fraction of the balance in risk is refused outright instead of trickled in. Set
    # it to the leg's own full risk and "shrunk" becomes impossible — every contested entry is
    # either granted in full or refused, which is *risk is never layered*. Left at 0 it is
    # shrink-to-fit. **No second allocator is written here**: the account is the canonical one.
    if args.on_contention == "refuse":
        # 🔴 REFUSED, rather than answered wrongly. `entry_floor_pct` is ONE number for the whole
        # account, and the two legs risk different amounts — A+ 10%, the recovery 2.5%. A floor
        # high enough to make A+ all-or-nothing (10%) is also higher than everything the recovery
        # ever asks for, so it refuses the recovery on EVERY setup whatever the room. MEASURED:
        # 64 recovery refusals, 0 recovery trades, identical output at a 10% and a 12.5% cap —
        # a table that looks like an allocator verdict and is a floor banning one leg outright.
        # Expressing "refuse the later one when the budget is full" needs a PER-LEG floor, which
        # is a change to the shared account the lab also drives. Not a default to slip in at the
        # end of an afternoon.
        raise SystemExit(
            "--on-contention refuse is NOT IMPLEMENTED and will not be faked.\n"
            "  The account carries one entry floor for every leg, and these legs risk different\n"
            "  amounts (A+ 10%, recovery 2.5%). Any floor that makes A+ all-or-nothing also\n"
            "  refuses every recovery entry outright, so the run reports an allocator decision\n"
            "  that is really a size ban — 64 refusals, 0 trades, and the same answer at a 10%\n"
            "  and a 12.5% cap.\n"
            "  It needs a per-leg floor on PortfolioAccount. Use --on-contention share, and read\n"
            "  the shrink counts in its refusal log as the size of what a refusal rule would\n"
            "  instead have blocked."
        )
    floor = 0.0
    account = PortfolioAccount(
        balance=cap, risk_cap_pct=args.risk_cap_pct / 100.0, entry_floor_pct=floor
    )
    lp, lr = build_legs(
        cfg, rule, df, account=account, capital=cap, profile=profile, strategy_cls=S
    )
    res = simulate([lp, lr], account)
    shared_p = res.per_leg[PRIMARY]
    shared_r = res.per_leg[RECOVERY]
    bsh, dsh = curve(res.trades, cap)
    only_p, dop = curve(shared_p, cap)
    print(f"{'SHARED  A+ leg':38} {len(shared_p):4} trades{'':40}{total_r(shared_p):+8.2f}R")
    print(f"{'SHARED  recovery leg':38} {len(shared_r):4} trades{'':40}{total_r(shared_r):+8.2f}R")
    print(
        f"{'SHARED  one balance, one budget':38} {len(res.trades):4} trades   "
        f"${bsh:14,.0f}  {bsh / cap:9,.0f}x  maxDD {dsh:5.1f}%"
    )
    print(
        f"\nA+ alone (solo control)   ${bp:,.0f}   →   with the recovery leg   ${bsh:,.0f}   "
        f"({100 * (bsh / bp - 1):+.1f}%)"
    )
    print(
        f"drawdown {dp:.1f}% → {dsh:.1f}%   (A+'s own trades inside the shared run: "
        f"${only_p:,.0f}, maxDD {dop:.1f}%)"
    )

    # ── what sharing cost ────────────────────────────────────────────────────────────────
    shrunk = [c for c in res.contention if not c.get("blocked")]
    blocked = [c for c in res.contention if c.get("blocked")]
    # 🔴 The invariant, checked and PRINTED rather than assumed. See `total_r`.
    for name, sh, so in ((PRIMARY, shared_p, solo_p), (RECOVERY, shared_r, solo_r)):
        d = total_r(sh) - total_r(so)
        verdict = (
            "R unchanged — sizing moved, no decision did"
            if abs(d) < 5e-3
            else f"R MOVED by {d:+.2f} — the cap bit, or a decision changed. "
            f"Read the refusal log below before believing anything above."
        )
        print(f"  {name:9} shared {total_r(sh):+8.2f}R vs solo {total_r(so):+8.2f}R   {verdict}")

    print(
        f"\nCONCURRENCY RULE: {args.on_contention.upper()}"
        + (
            "  (a contested entry takes whatever room is left)"
            if floor == 0.0
            else f"  (an entry that cannot be granted in full is REFUSED; floor {100 * floor:g}%)"
        )
    )
    for leg_name in (PRIMARY, RECOVERY):
        b = sum(1 for c in blocked if c.get("leg") == leg_name)
        k = sum(1 for c in shrunk if c.get("leg") == leg_name)
        print(f"  {leg_name:9} REFUSED because the budget was full: {b:4}   shrunk: {k:4}")
    skipped = len(lr.strategy.execution.skipped_concurrent)
    print(f"  {RECOVERY:9} setups skipped because the leg already held one: {skipped:4}")
    # x100: the account stores this as a FRACTION of the balance, and the cap beside it is a
    # percent. Printing the two in different units put "0.1%" next to "cap 10%" when the book was
    # sitting exactly ON the cap.
    peak = 100 * account.peak_reserved_pct
    print(
        f"  peak open risk {peak:.1f}% of balance against a {args.risk_cap_pct:g}% cap; "
        f"most legs holding at once {account.peak_concurrent}"
    )
    if peak > args.risk_cap_pct + 1e-9:
        # ⚠ Not a hole in the cap, and worth saying so before somebody reads it as one. The cap is
        # applied AT FILL against the balance at that moment; the reservation is then a fixed
        # dollar figure while the balance keeps moving. A losing trade elsewhere shrinks the
        # denominator, so the same reservation reads as a larger share afterwards.
        print(
            f"  * peak exceeds the cap by {peak - args.risk_cap_pct:.1f} points. The cap binds "
            f"AT FILL against the balance THEN; a later loss shrinks the balance under a "
            f"reservation already granted. Nothing was granted over the cap."
        )
    # ⚠ Never let the cap read as enforced on the strength of an empty log — a reservation falls
    # to zero at breakeven, so a book that carried two full positions all day can log nothing.
    if not res.contention:
        print("  ⚠ nothing was refused. That is NOT proof the cap bound — check the peak above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
