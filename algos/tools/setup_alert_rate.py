#!/usr/bin/env python3
"""setup_alert_rate.py — what ANY bot's signals room would have said, and proof it moves no trade.

Builds the strategy the way the live runner does (`runner._build_strategy`: the package's
`LAB_STRATEGY`, the instance's own `strategy_params`), steps it through the live contract
(`signals` → `sequence` → `execution.step`) over the broker's cached bars, and feeds its setups
through the REAL alert layer (`algos/live/setup_alerts.py`) with a counting sender — so the
messages counted are the ones the live bot would post. Then it replays the same bars with the
strategy's setup watch switched off.

Prints, and EXITS 1 if any of 1, 2, 4 or 5 fails:
  1. REPORTING ONLY  the trade list is identical with the watch on and off
  2. ANNOUNCED       every trade had its setup's ENTERED reply
  3. VOLUME          roots and messages a month, the share of roots that became trades
  4. RE-ENTRY WARNED every re-entry fill came after a RE-ENTRY POSSIBLE for the same setup,
                     with the lead time (median and minimum)
  5. RE-ENTRY NOISE  warnings per actual re-entry, at most `--max-warn-ratio` (default 4)

🔴 **A bot whose strategy trades on a second, faster clock is replayed on BOTH (2026-10-02)** —
the lab's own `run_dual`, with the alert layer asked after every fast bar, exactly as the live
runner asks it. Its re-entries arm and fill on that clock, so a 15-minute-only replay cannot see
them at all. Checks 4 and 5 exist for those bots and are skipped, and said to be, for the rest.
⚠ A message's time is the CLOSE of the fast bar it was sent after; the live bot sends a first
trade's close on the 15-minute bar itself, so live leads are this or a little longer, never shorter.

⚠ A strategy whose setup watch is not a `setup_watch` attribute with an `observe` method (SOS
Fade's is built into its order layer) cannot be switched off from here, so check 1 is skipped
and SAID to be skipped. `backtest/tools/alert_rate.py` is the older SOS Fade / extreme-leg tool.

Run it for every new bot that reports setups, and after any change to a bot's entry logic.

Usage:
  python algos/tools/setup_alert_rate.py fft_1
  python algos/tools/setup_alert_rate.py realign_1 --start 2024-01-01
  python algos/tools/setup_alert_rate.py sos_fade_demo --bars <M15.csv> --fast-bars <M1.csv>
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "strategies" / "python", ROOT / "algos" / "live"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

INSTANCES = ROOT / "algos" / "markets" / "fx" / "instances"
CACHE = ROOT / "backtest" / "cache"
MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240}


def build(cfg: dict):
    """The runner's construction, minus the broker: same class, same params, by name."""
    pkg = importlib.import_module(cfg["strategy_package"])
    lab = pkg.LAB_STRATEGY
    cls, cfg_cls = lab["strategy"], lab["config"]
    if cls.__name__ != cfg["strategy_class"]:
        sys.exit(f"{cfg['strategy_package']} provides {cls.__name__}, not {cfg['strategy_class']}")
    params = dict(cfg["strategy_params"])
    params.setdefault("symbol", cfg["symbol"])
    return cls(cfg_cls(**params), initial_capital=10_000.0)


def replay(cfg: dict, df, *, watch: bool, alerts=None):
    from backtest.replay import EngineStack, iter_bars

    s = build(cfg)
    s.execution.bar_ms = MINUTES[cfg["timeframe"]] * 60_000
    if not watch:
        s.setup_watch.observe = lambda *a, **k: None
    stack = EngineStack(s.engine_config())
    for bar in iter_bars(df):
        sig = s.signals.update(stack.step(bar))
        s.execution.step(sig, s.sequence.update(sig))
        if alerts is not None:
            alerts.on_bar(s)
    return s


def uses_fast_clock(s) -> bool:
    """Does this strategy trade on a second, faster clock? Asked of the strategy's own config."""
    if not callable(getattr(s, "run_dual", None)):
        return False
    from strategies.python.sos_fade.dual_clock import uses_fast_clock as ask

    return bool(ask(s.config))


def fast_minutes(s) -> int:
    from strategies.python.sos_fade.dual_clock import fast_tf_minutes

    return fast_tf_minutes(s.config)


def load(path: Path, start, end):
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[df["time"] >= start]
    if end:
        df = df[df["time"] < end]
    return df.set_index("time").astype(float)


#: The re-entry triggers. A fast-clock fill from any other source is not a re-entry.
REENTRY_SRCS = ("gap", "reclaim", "Structure shift")


class Recorder:
    """The sender handed to the REAL alert layer: keeps every message with its time and setup.

    `now` is set by the replay before each ask; `about` by the `_handle` wrapper below, so each
    message is filed under the setup it was sent for without parsing the text."""

    def __init__(self):
        self.posts = []  # (ms, setup key, text)
        self.now = None
        self.about = None

    def send(self, text, *_, reply_to=None, **__):
        self.posts.append((self.now, self.about, text))
        return len(self.posts)


def alert_layer(cfg: dict, rec: Recorder, bot: str):
    from setup_alerts import SetupAlerts

    sa = SetupAlerts(send=rec.send, display=cfg.get("display_name", bot), digits=2)
    handle = sa._handle

    def tracked(snap):
        rec.about = snap.key
        handle(snap)

    sa._handle = tracked
    return sa


def replay_dual(cfg: dict, df, dff, *, watch: bool, alerts=None, rec=None, fills=None):
    """The lab's own two-clock replay (`run_dual`), the alert layer asked after every fast bar.

    `fills` collects `(fill bar open ms, side, setup key)` for every RE-ENTRY fill, keyed off the
    setup the CLOCK says is live — independently of the watch, so a watch that named the wrong
    setup shows up as an unwarned fill rather than agreeing with itself."""
    s = build(cfg)
    if not watch:
        s.execution.reentry_watch.observe = lambda *a, **k: None
    tf_ms = fast_minutes(s) * 60_000
    ex = s.execution

    def on_fast(bar, step, clock):
        if alerts is not None:
            rec.now = int(bar.timestamp_ms) + tf_ms
            alerts.on_bar(s)
        if fills is not None and step.filled_dir is not None and ex.entry_src in REENTRY_SRCS:
            seq = clock.last_seq
            sos = seq.l_sos_bar if step.filled_dir > 0 else seq.s_sos_bar
            key = ex._setup_key(step.filled_dir > 0, sos, ex._bar_ms.get(sos)) + ":re"
            fills.append((int(bar.timestamp_ms), step.filled_dir, key))

    s.run_dual(df, dff, on_fast=on_fast)
    return s


def book(s):
    return [
        (t.dir, t.entry_ms, t.entry_price, t.exit_ms, t.exit_price, t.qty, t.exit_reason, t.kind)
        for t in s.execution.trades
    ]


def _head(text: str) -> str:
    return text.split("\n")[0]


def reentry_report(rec: Recorder, fills, max_ratio: float, show: int) -> bool:
    """Checks 4 and 5. Returns True when both pass."""
    import statistics

    first_warn = {}
    for ms, key, text in rec.posts:
        if "RE-ENTRY POSSIBLE" in _head(text) and key not in first_warn:
            first_warn[key] = ms
    leads, unwarned = [], []
    for ms, side, key in fills:
        warned = first_warn.get(key)
        if warned is None or warned > ms:
            unwarned.append((ms, side, key, warned))
        else:
            leads.append((ms - warned) / 60_000)
    n_fill, n_warn = len(fills), len(first_warn)
    print(
        f"4. re-entry warned: {n_fill - len(unwarned)} of {n_fill} re-entry fills came after a "
        f"RE-ENTRY POSSIBLE for the same setup"
    )
    if leads:
        print(
            f"   lead before the fill bar opened: median {statistics.median(leads):.0f} min, "
            f"minimum {min(leads):.0f} min, maximum {max(leads):.0f} min"
        )
        short = sum(1 for x in leads if x < 5)
        print(f"   {short} of {len(leads)} had less than 5 minutes")
    for ms, side, key, warned in unwarned[:10]:
        when = pd.Timestamp(ms, unit="ms")
        print(
            f"   UNWARNED {'long' if side > 0 else 'short'} fill at {when} — {key} "
            f"(warning {'never sent' if warned is None else pd.Timestamp(warned, unit='ms')})"
        )
    ratio = n_warn / n_fill if n_fill else float("inf") if n_warn else 0.0
    print(
        f"5. re-entry noise: {n_warn} warnings for {n_fill} re-entries = {ratio:.2f} per "
        f"re-entry (limit {max_ratio:g})"
    )
    why = Counter(
        text.split("\n")[-1][:90] for _, _, text in rec.posts if "NO RE-ENTRY" in _head(text)
    )
    for k, v in why.most_common(8):
        print(f"   {v:6d}  {k}")
    shown = 0
    for key in list(first_warn)[: max(show, 0) * 4]:
        if shown >= show:
            break
        thread = [(ms, t) for ms, k, t in rec.posts if k == key]
        print(f"   ── {key}")
        for ms, t in thread:
            print(f"      {pd.Timestamp(ms, unit='ms')}  " + t.replace("\n", "\n" + " " * 28))
        shown += 1
    return not unwarned and (n_fill == 0 or ratio <= max_ratio)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bot", help="the bot's key, e.g. fft_1")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--bars", type=Path, default=None, help="a bar CSV (time,open,high,low,close)")
    ap.add_argument(
        "--fast-bars", type=Path, default=None, help="the second clock's bar CSV, when it has one"
    )
    ap.add_argument("--max-warn-ratio", type=float, default=4.0)
    ap.add_argument("--show", type=int, default=0, help="print this many re-entry threads")
    a = ap.parse_args()

    cfg = json.loads((INSTANCES / a.bot / "config.json").read_text())
    server = cfg["server"].replace("-", "_")
    sym = cfg["symbol"].replace(".", "_")
    bars = a.bars or CACHE / server / f"{sym}__{cfg['timeframe']}.csv"
    if not bars.exists():
        sys.exit(f"no cached bars at {bars} — pass --bars")
    df = load(bars, a.start, a.end)

    probe = build(cfg)
    rec = Recorder()
    sa = alert_layer(cfg, rec, a.bot)
    if not sa.supported(probe):
        sys.exit(f"{cfg['strategy_class']} does not report setups — nothing to measure")
    dual = uses_fast_clock(probe)
    fills = []
    if dual:
        fast_tf = f"M{fast_minutes(probe)}"
        fbars = a.fast_bars or CACHE / server / f"{sym}__{fast_tf}.csv"
        if not fbars.exists():
            sys.exit(
                f"this bot trades on a {fast_tf} clock too; no cached bars at {fbars} — "
                f"pass --fast-bars"
            )
        dff = load(fbars, a.start, a.end)
        on = replay_dual(cfg, df, dff, watch=True, alerts=sa, rec=rec, fills=fills)
        failed = on.execution.reentry_watch.failed
        if failed:
            print(f"the re-entry watch FAILED during the replay: {failed}")
            return 1
        same = book(on) == book(replay_dual(cfg, df, dff, watch=False))
        what = "the re-entry watch"
    else:
        on = replay(cfg, df, watch=True, alerts=sa)
        switchable = callable(getattr(getattr(on, "setup_watch", None), "observe", None))
        same = book(on) == book(replay(cfg, df, watch=False)) if switchable else None
        what = "the watch"

    posts = [t for _, _, t in rec.posts]
    kinds = Counter(_head(p) for p in posts)
    roots = sum(v for k, v in kinds.items() if "SETUP FORMING" in k)
    entered = sum(v for k, v in kinds.items() if k.startswith("✅ ENTERED"))
    trades = sum(1 for t in on.execution.trades if t.kind != "secondary")
    months = (df.index[-1] - df.index[0]).days / 30.44

    print(
        f"{a.bot}: {len(df):,} {cfg['timeframe']} bars, {df.index[0]} -> {df.index[-1]} "
        f"({months:.1f} months)"
        + (f", replayed on both clocks ({len(dff):,} {fast_tf} bars)" if dual else "")
    )
    print(
        "1. reporting only: "
        + (
            "SKIPPED — this strategy's watch cannot be switched off from here"
            if same is None
            else f"{'SAME' if same else 'DIFFERENT'} — {len(on.execution.trades)} trades with "
            f"{what} on and off"
        )
    )
    print(f"2. announced: {entered} ENTERED replies for {trades} first trades")
    print(
        f"3. {roots} roots ({roots / months:.1f} a month), {entered / max(roots, 1):.0%} became "
        f"trades; {len(posts)} messages ({len(posts) / months:.1f} a month)"
    )
    for k, v in kinds.most_common():
        print(f"   {v:6d}  {k}")
    reasons = Counter(p.split("\n")[-1][:90] for p in posts if "NO TRADE" in _head(p))
    if reasons:
        print("   why no trade:")
        for k, v in reasons.most_common(8):
            print(f"   {v:6d}  {k}")
    reentry_ok = True
    if dual:
        reentry_ok = reentry_report(rec, fills, a.max_warn_ratio, a.show)
    else:
        print("4-5. re-entry checks: SKIPPED — this bot has no second clock, so no re-entry")
    return 0 if same is not False and entered == trades and reentry_ok else 1


if __name__ == "__main__":
    sys.exit(main())
