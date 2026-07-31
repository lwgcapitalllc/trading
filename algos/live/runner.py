"""runner.py — the live bar loop for one Python strategy on one MT5 terminal.

    connect → verify the version pin → warm the engines → wait for a closed bar
            → step the strategy → reconcile the broker → heartbeat → repeat

**Run it:**

    python algos/live/runner.py --bot mpc_sos_fade_demo --dry-run     # places nothing
    python algos/live/runner.py --bot mpc_sos_fade_demo --live        # places orders

`--dry-run` is the DEFAULT and `--live` must be typed. Nothing about arming a bot that sends
real orders should be reachable by forgetting a flag.

**Why the strategy object is built once and kept.** The canonical engines are stateful streaming
state machines — structure, fibs, liquidity, sessions all accumulate. Rebuilding them per bar
would restart the market's history every 15 minutes. So warmup replays N historical bars through
the same `MpcSosFadeStrategy` the backtest uses, and every live bar is one more `step()` on it.
The bot is running the identical object the lab replays, which is what makes a live result
comparable to a backtest result at all.

**Warmup is not optional and its depth is not arbitrary.** The liquidity engine needs previous
WEEK levels; the RSI engine needs `rsi_valid_bars` (100); the structure engine needs enough
history to have confirmed swings. 5,000 M15 bars is about seven trading weeks and costs a few
seconds. Too little warmup does not error — it produces a strategy that quietly disagrees with
the backtest for its first few days, which is the hardest class of bug to notice.

**A gap in the bar stream re-warms rather than resumes.** If the process was asleep (VPS
hiccup, terminal reconnect) long enough to miss bars, the engines' state no longer corresponds
to the market's history. Feeding them the newest bar as if nothing happened produces a state
machine that is wrong in a way it can never recover from. Re-warming is cheap; being subtly
wrong for a week is not.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
# `algos/bots` is here for bot_utils (shared logging). It is easy to leave out — the suite never
# constructed a LiveRunner, so a missing entry surfaced only on the VPS, at __init__, before the
# bot could log or notify anything about why it died.
for _p in (str(_REPO), str(_REPO / "algos" / "shared"), str(_REPO / "algos" / "bots"),
           str(_REPO / "strategies" / "python"), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_config                    # noqa: E402  (algos/live/live_config.py)
from bridge import OrderBridge, BridgeState, assert_supported  # noqa: E402
from feed import BarFeed              # noqa: E402
from ledger import Ledger             # noqa: E402
from version import verify_pin, current_commit, VersionMismatch  # noqa: E402

_stop_requested = False


def _handle_signal(signum, frame):
    global _stop_requested
    _stop_requested = True


class LiveRunner:
    def __init__(self, cfg, *, dry_run: bool = True) -> None:
        self.cfg = cfg
        self.dry_run = dry_run
        self.log = self._make_logger()
        self.ledger = Ledger(cfg.instance_dir / "ledger", cfg.bot_key)
        self.mt5 = None
        self.strategy = None
        self.stack = None
        self.feed = None
        self.bridge = None
        self.source_hash = ""

    # ── setup ────────────────────────────────────────────────────────────────
    def _make_logger(self):
        """Shared bot logging if it is importable, plain file+stdout logging if it is not.

        The import lives INSIDE the try on purpose. It sat outside once, so a `bot_utils` that
        could not be imported killed the runner in `__init__` — before it had a logger to say so
        with, before the version pin, before anything. A logging dependency must never be able to
        stop a bot; the fallback below writes the same file to the same place.
        """
        cfg_dict = {"instance_dir": str(self.cfg.instance_dir)}
        try:
            import bot_utils
            return bot_utils.setup_logging(self.cfg.bot_key, cfg_dict)
        except Exception:
            import logging
            self.cfg.instance_dir.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
                handlers=[logging.FileHandler(self.cfg.instance_dir / f"{self.cfg.bot_key}.log",
                                              encoding="utf-8"),
                          logging.StreamHandler(sys.stdout)])
            return logging.getLogger(self.cfg.bot_key)

    def _notify(self, text: str) -> None:
        """Every message this bot sends goes to ITS OWN configured destination — the routing is
        per instance, not global, so two bots on two accounts never share one feed unless their
        configs say to. Empty values fall back to the shared default."""
        try:
            from notify import send_telegram
            send_telegram(text,
                          chat_id=self.cfg.telegram_chat_id,
                          token_key=self.cfg.telegram_token_key)
        except Exception as e:
            self.log.warning(f"Telegram send failed: {e}")

    def _build_strategy(self):
        """Import the strategy package, build its config from the INSTANCE file only, and
        construct it. `strategy_params` is applied by name so an unknown key is a hard error —
        a typo'd parameter that silently keeps the default is a bot trading settings nobody
        chose."""
        import importlib
        pkg = importlib.import_module(self.cfg.strategy_package)
        lab = getattr(pkg, "LAB_STRATEGY", None)
        if not lab:
            raise RuntimeError(
                f"{self.cfg.strategy_package} declares no LAB_STRATEGY, so the live runner "
                f"cannot resolve its strategy or config class.")
        cls, cfg_cls = lab["strategy"], lab["config"]
        if cls.__name__ != self.cfg.strategy_class:
            raise RuntimeError(
                f"Config names strategy_class={self.cfg.strategy_class!r} but package "
                f"{self.cfg.strategy_package} provides {cls.__name__!r}.")

        known = set(cfg_cls.__dataclass_fields__)
        unknown = sorted(set(self.cfg.strategy_params) - known)
        if unknown:
            raise RuntimeError(
                f"Unknown strategy_params in the instance config: {', '.join(unknown)}. "
                f"They would be ignored, so the bot would trade settings you did not choose.")

        params = dict(self.cfg.strategy_params)
        params.setdefault("symbol", self.cfg.symbol)
        scfg = cfg_cls(**params)
        assert_supported(scfg)

        capital = self.cfg.initial_capital
        if not capital:
            import MetaTrader5 as mt5
            info = mt5.account_info()
            capital = float(info.balance) if info else 0.0
            if not capital:
                raise RuntimeError("Could not read the account balance, and initial_capital is "
                                   "0 — the strategy would size every trade off nothing.")
        self.log.info(f"Sizing against account balance ${capital:,.2f}")
        return cls(scfg, initial_capital=capital), scfg

    def connect(self) -> bool:
        from mt5_ops import BotMT5
        creds = live_config.account_credentials(self.cfg.account)
        if not creds:
            self.log.error(
                f"No credentials for MT5 account {self.cfg.account}. Add an 'mt5_accounts' "
                f"entry to algos/credentials.json (see credentials.template.json).")
            return False
        creds["server"] = creds["server"] or self.cfg.server
        self.mt5 = BotMT5(self.cfg.symbol, self.cfg.magic, self.cfg.bot_key,
                          {"mt5_path": self.cfg.mt5_path}, creds, self.log)
        return self.mt5.connect()

    def warm(self):
        """Replay history through the strategy WITHOUT acting on any of it."""
        from backtest.replay import EngineStack, iter_bars

        df = self.feed.history(self.cfg.warmup_bars)
        if len(df) < 200:
            raise RuntimeError(
                f"Only {len(df)} bars of {self.cfg.timeframe} history available for "
                f"{self.cfg.symbol}. The engines cannot warm on that — check the symbol name "
                f"first (a wrong broker suffix returns nothing and looks exactly like this).")
        self.stack = EngineStack(self.strategy.engine_config())
        self.strategy.execution.bar_ms = self.feed.bar_seconds * 1000
        t0 = time.time()
        bar = None
        for bar in iter_bars(df):
            state = self.stack.step(bar)
            sig = self.strategy.signals.update(state)
            seq = self.strategy.sequence.update(sig)
            self.strategy.execution.step(sig, seq)
        self._bar_index = bar.index          # live bars count on from here — see _on_bar
        self.feed.mark_seen(df)
        self.log.info(
            f"Warmed {len(df)} bars ({df.index[0]} → {df.index[-1]}) in {time.time()-t0:.1f}s")
        self.ledger.event("warmed", bars=len(df), first=str(df.index[0]), last=str(df.index[-1]))
        return df

    # ── the loop ─────────────────────────────────────────────────────────────
    def run(self) -> int:
        commit = current_commit(self.cfg.repo_root)
        try:
            self.source_hash = verify_pin(self.cfg.strategy_dir, self.cfg.strategy_source_hash)
        except VersionMismatch as e:
            self.log.error(str(e))
            self.ledger.event("version_mismatch", detail=str(e))
            self._notify(f"⛔️ *{self.cfg.display_name}* refused to start — the strategy code on "
                         f"disk is not the version it was promoted to run.")
            return 2
        if not self.cfg.strategy_source_hash:
            self.log.warning(
                f"UNPINNED: this bot has no strategy_source_hash, so a `git pull` can change "
                f"what it trades without anyone noticing. Running hash {self.source_hash}. "
                f"Promote it to pin.")

        self.log.info(
            f"{self.cfg.display_name} | {self.cfg.strategy_class} v{self.cfg.strategy_version} "
            f"| hash {self.source_hash[:12]} | commit {commit or '?'} "
            f"| {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.ledger.event("startup", version=self.cfg.strategy_version, hash=self.source_hash,
                          commit=commit, dry_run=self.dry_run, symbol=self.cfg.symbol,
                          timeframe=self.cfg.timeframe, account=self.cfg.account,
                          mt5_path=self.cfg.mt5_path)

        if not self.connect():
            self.log.error("Could not connect to MT5 — see the attempts above.")
            return 3

        try:
            self.strategy, scfg = self._build_strategy()
            self.feed = BarFeed(self.mt5, self.cfg.timeframe, self.cfg.symbol)
            self.bridge = OrderBridge(self.mt5, self.strategy.execution, self.ledger, self.log,
                                      notify=self._notify, dry_run=self.dry_run)
            self.bridge.adopt_broker_state()
            if self.bridge.state is BridgeState.HALTED:
                return 4
            self.warm()
            self.bridge.begin_live()
        except Exception as e:
            self.log.error(f"Startup failed: {e}\n{traceback.format_exc()}")
            self.ledger.event("startup_failed", error=str(e))
            self._notify(f"⛔️ *{self.cfg.display_name}* failed to start: {e}")
            return 5

        self._notify(
            f"🟢 *{self.cfg.display_name}* online\n"
            f"{self.cfg.symbol} {self.cfg.timeframe} · account {self.cfg.account}\n"
            f"v{self.cfg.strategy_version} ({self.source_hash[:8]})"
            + ("\n_dry run — no orders will be placed_" if self.dry_run else ""))

        return self._loop()

    def _loop(self) -> int:
        import bot_state
        self.log.info(f"Watching for closed {self.cfg.timeframe} bars "
                      f"(poll {self.cfg.poll_seconds}s). Ctrl-C to stop.")
        bot_state.set_started(self.cfg.bot_key)
        consecutive_errors = 0

        while not _stop_requested:
            try:
                gap = self.feed.gap_bars()
                if gap > 4:
                    # See the module docstring: a hole in the stream is a different market
                    # history, not a recoverable lag.
                    self.log.warning(f"{gap} bars missed — re-warming the engines rather than "
                                     f"resuming with a hole in the stream.")
                    self.ledger.event("rewarm", missed_bars=gap)
                    self.strategy, _ = self._build_strategy()
                    self.bridge._ex = self.strategy.execution
                    self.warm()
                    self.bridge.begin_live()

                for _, row in self.feed.new_bars().iterrows():
                    self._on_bar(row)

                self._heartbeat(bot_state)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                self.log.error(f"Loop error ({consecutive_errors}): {e}\n{traceback.format_exc()}")
                self.ledger.event("loop_error", error=str(e), count=consecutive_errors)
                if consecutive_errors >= 10:
                    self._notify(f"⛔️ *{self.cfg.display_name}* stopping — 10 consecutive loop "
                                 f"errors. Last: {e}")
                    return 6
            time.sleep(self.cfg.poll_seconds)

        self.log.info("Stop requested — shutting down.")
        self.ledger.event("shutdown")
        self._notify(f"⏹ *{self.cfg.display_name}* stopped")
        try:
            self.mt5.disconnect()
        except Exception:
            pass
        return 0

    def _on_bar(self, row) -> None:
        """One closed bar: engines → strategy → broker → log. This ordering is the whole
        contract — the broker is reconciled only AFTER the strategy has seen the same bar."""
        from backtest.replay import ReplayBar

        ts = row.name
        # The index must keep COUNTING ON from where warmup stopped. The strategy compares bar
        # indices — the sweep→SOS staleness window, the one-trade-per-leg latches, the FVG cap —
        # so restarting it at 0 would make every stale setup look fresh and re-arm legs that
        # have already traded.
        self._bar_index += 1
        bar = ReplayBar(index=self._bar_index,
                        timestamp_ms=int(ts.value // 1_000_000), time=ts,
                        open=float(row["open"]), high=float(row["high"]),
                        low=float(row["low"]), close=float(row["close"]))

        state = self.stack.step(bar)
        sig = self.strategy.signals.update(state)
        seq = self.strategy.sequence.update(sig)
        dec = self.strategy.execution.step(sig, seq)

        self.ledger.bar(dec, sig, seq)
        self._drain_records()
        self.bridge.sync(dec, sig)

        if self.bridge.state is BridgeState.HALTED:
            self.log.error("Bridge halted — the loop will keep observing but place nothing.")

    def _drain_records(self) -> None:
        """Write any blocked/missed setups the strategy recorded on this bar, then forget them —
        the strategy accumulates them for a whole backtest, which would grow without bound in a
        process meant to run for months."""
        ex = self.strategy.execution
        for b in getattr(ex, "blocks", []):
            self.ledger.blocked(b)
        for m in getattr(ex, "misses", []):
            self.ledger.missed(m)
        if hasattr(ex, "blocks"):
            ex.blocks.clear()
        if hasattr(ex, "misses"):
            ex.misses.clear()

    def _heartbeat(self, bot_state) -> None:
        try:
            import MetaTrader5 as mt5
            info = mt5.account_info()
            bot_state.write_bot(self.cfg.bot_key, {
                "status": self.bridge.state.value,
                "balance": float(info.balance) if info else None,
                "account": self.cfg.account,
                "symbol": self.cfg.symbol,
                "version": self.cfg.strategy_version,
                "source_hash": self.source_hash[:12],
                "dry_run": self.dry_run,
                "last_bar": str(self.feed.last_bar_time) if self.feed.last_bar_time else None,
                "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
        except Exception as e:
            self.log.warning(f"Heartbeat write failed: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a Python strategy live on an MT5 terminal.")
    ap.add_argument("--bot", required=True, help="bot_key — the instance dir under "
                                                 "algos/markets/fx/instances/")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="(default) run everything, send no orders")
    mode.add_argument("--live", action="store_true",
                      help="actually place orders — must be typed explicitly")
    args = ap.parse_args(argv)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    cfg = live_config.load(args.bot)
    import os
    os.environ.setdefault("BROKER_TZ_OFFSETS", cfg.broker_tz_offsets)
    return LiveRunner(cfg, dry_run=not args.live).run()


if __name__ == "__main__":
    sys.exit(main())
