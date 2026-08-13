#!/usr/bin/env python3
"""alert_rate.py — how many Telegram messages would the signals channel actually send?

**Run this before switching the signals channel on for ANY strategy, and again after any
entry-logic change.** The volume is the whole question: a channel that is noise is one nobody
reads on the day it matters, and that is why `reporter.py` was deleted rather than fixed
(`algos/CLAUDE.md`).

It drives the REAL pipeline — the strategy's `live_setups()` contract, the transition layer in
`algos/live/setup_alerts.py`, and the formatters in `algos/live/alerts.py` — with the sender
replaced by a collector. So it counts the messages that would be SENT, not the transitions that
happen underneath them, and those two numbers are very different:

🔴 **MEASURED 2026-08-13 on `mpc_sos_fade`, 155,807 M15 bars (2020-01-01 → 2026-08-06): the
resting-limit alert fires 665 times on raw `None -> _Pending` transitions and 332 times per
SETUP.** A limit is rebuilt every bar and cleared when not armed, so one setup flickers in and out
of `RESTING` repeatedly. `docs/LIVE_SETUP_ALERTS.md` had INFERRED ~3/month for that message and
flagged the guess as the thing most likely to make the channel unreadable; the real figure is
4.2/month, and reading the raw transitions would have given 8.4. **This is the tool that turns
that estimate into a measurement.**

⚠ **The figures are a fact about ONE strategy, ONE instrument and ONE window.** A new bot's rate
is its own question.

⚠ **Warm-up snapshots are DROPPED, not counted.** They belong to the bars before the window, and
the live runner discards them for the same reason (`runner.warm`).

Usage:
    python backtest/tools/alert_rate.py --strategy mpc_sos_fade --start 2020-01-01
    python backtest/tools/alert_rate.py --show 5        # ...and print sample threads
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "algos" / "live", _ROOT / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Every Python strategy, including the ones that do NOT implement the contract — asking about one
# of those returns an honest REFUSAL naming why, which is more useful than argparse rejecting the
# name as if the strategy did not exist.
_STRATEGIES = {
    "mpc_sos_fade": "strategies.python.mpc_sos_fade",
    "mpc_bleg": "strategies.python.mpc_bleg",
    "mpc_bos": "strategies.python.mpc_bos",
    "mpc_realign": "strategies.python.mpc_realign",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Signals-channel message volume, by real replay.")
    ap.add_argument("--strategy", default="mpc_sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--show", type=int, default=0, help="print this many sample threads")
    args = ap.parse_args(argv)

    import datetime as dt
    import importlib

    from backtest.data.source import BarSource
    from backtest.replay import EngineStack, iter_bars
    from backtest.setups import implements_contract

    from setup_alerts import SetupAlerts

    mod = importlib.import_module(_STRATEGIES[args.strategy])
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]

    end = args.end or dt.date.today().isoformat()
    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, end)
    if df.empty:
        print("no bars — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    cfg = ConfigCls(fill_model="bar", symbol=args.symbol)
    if hasattr(cfg, "exec_secondary"):
        # Single-stream replay; the 1m re-entry needs `run_dual`. Same call `run_sweep` makes.
        cfg = dataclasses.replace(cfg, exec_secondary=False)
    strat = StrategyCls(config=cfg, initial_capital=10_000.0)

    if not implements_contract(strat.execution):
        # 🔴 REFUSE rather than reporting zero. A strategy that cannot answer and a strategy with
        # nothing to say would otherwise print the same table, and the zero would read as "this
        # bot is quiet" — root CLAUDE.md rule 1.
        print(f"\n{type(strat.execution).__name__} does not implement live_setups(), so this "
              f"strategy can produce NO setup alerts at all.\nThat is not a rate of zero — it is "
              f"an unanswerable question. See docs/LIVE_SETUP_ALERTS.md §2.")
        return 2

    sent: list = []
    ids = {"n": 0}

    def collect(text, kind, reply_to=None):
        ids["n"] += 1
        sent.append({"id": ids["n"], "text": text, "reply_to": reply_to})
        return ids["n"]

    alerts = SetupAlerts(send=collect, log=None)

    print(f"replaying {args.strategy} (warmup {args.warmup}) ...", flush=True)
    stack = EngineStack(strat.engine_config())
    for i, bar in enumerate(iter_bars(df)):
        state = stack.step(bar)
        sig = strat.signals.update(state)
        seq = strat.sequence.update(sig)
        strat.execution.step(sig, seq)
        if i >= args.warmup:
            alerts.on_bar(strat)
        else:
            strat.execution.drain_setups()      # warm-up setups are not this run's

    months = (df.index[-1] - df.index[0]).days / 30.44
    heads = Counter(m["text"].split("\n")[0].split(" · ")[0] for m in sent)
    threads = defaultdict(list)
    for m in sent:
        threads[m["reply_to"] or m["id"]].append(m)

    print("\n" + "=" * 72)
    print(f"{args.strategy}  {args.symbol} {args.tf}m  "
          f"{df.index[0].date()} -> {df.index[-1].date()}   ({months:.1f} months)")
    print("=" * 72)
    print(f"\n{'message':<34}{'count':>8}{'per month':>12}")
    for head, n in heads.most_common():
        print(f"  {head:<32}{n:>8}{n / months:>12.1f}")
    print(f"  {'-' * 30}")
    print(f"  {'TOTAL':<32}{len(sent):>8}{len(sent) / months:>12.1f}")
    print(f"\n{len(threads)} setups announced — one Telegram thread each "
          f"({len(threads) / months:.1f}/month)")
    if len(sent):
        days = months * 30.44 / len(sent)
        print(f"roughly one message every {days:.1f} days")

    trades = len(strat.execution.trades)
    roots = len(threads)
    if roots:
        print(f"\n{trades} of {roots} announced setups became trades "
              f"({100.0 * trades / roots:.0f}%) — the rest are the reason the wording says "
              f"SETUP FORMING rather than POTENTIAL TRADE.")

    # ── THE INVARIANT: every trade must have been announced first ────────────────────────────
    #
    # Aaron's requirement, 2026-08-13: *"the same trade signals that are going to the LWG Capital
    # Algo trades group will originate from the signals that are going to this new group."* A fill
    # with no signal thread behind it is the failure mode of the `tradeable` filter — suppress one
    # setup too many and a real trade arrives in the trades chat having never been announced, with
    # nothing anywhere saying a message was skipped.
    #
    # ⚠ It is checked by COUNT of ENTERED messages against closed trades, because the alert layer
    # is handed no trade id. A trade whose setup opened during WARM-UP is legitimately unannounced
    # — those snapshots are discarded rather than posted — so the tolerance is stated, not zero.
    entered = sum(1 for m in sent if m["text"].startswith("✅"))
    missing = trades - entered
    print(f"\nINVARIANT — every trade was announced first:")
    print(f"  {trades} trades closed, {entered} announced as ENTERED")
    if missing <= 0:
        print(f"  ✅ HOLDS — no trade reached the broker without a signal thread.")
    elif missing <= 1:
        print(f"  ✅ HOLDS — {missing} unannounced, which is the warm-up boundary: a setup that "
              f"opened before the window began is discarded rather than posted.")
    else:
        print(f"  🔴 BROKEN — {missing} trades had NO signal thread. The `tradeable` filter is "
              f"suppressing setups that go on to trade. Do not ship this.")

    for root in list(threads)[-args.show:] if args.show else []:
        print("\n" + "-" * 72)
        for m in threads[root]:
            pre = "  ↳ " if m["reply_to"] else ""
            print(pre + m["text"].replace("\n", "\n  " + " " * len(pre)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
