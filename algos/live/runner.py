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

**The terminal link is PROBED every poll, because losing it looks exactly like a quiet market.**
Measured on the VPS 2026-08-04: MetaTrader auto-updated itself — `terminal64.exe` was rewritten
at 02:57:53 and the new process started two seconds later — and the running bot's IPC handle died
with the old one. It then sat for 50 minutes across a live session having seen nothing, because
every failure on that path returns an ABSENCE rather than raising: `copy_rates_from_pos` returns
None, so `get_candles` hands back an empty frame, which `new_bars` reads as *no bar has closed*
and `gap_bars` reads as *no gap*; `account_info` returns None, so the heartbeat wrote a null
balance. The loop kept stamping its heartbeat, so the watchdog saw a healthy bot and the Bots page
said RUNNING. **The only visible symptom in the entire system was a blank balance.**

So the loop asks `account_info()` first, every poll. It is the right probe precisely because it
is UNAMBIGUOUS — a quiet market and a dead terminal produce the same empty bar frame, but
`account_info()` answers whenever the link is alive, whatever the market is doing. A lost link
is logged, alerted once, and reconnected; and because the outage IS a hole in the bar stream, the
recovery re-warms through the same path a `gap_bars` overrun takes rather than resuming.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "shared"), str(_REPO / "strategies" / "python"),
           str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_config                    # noqa: E402  (algos/live/live_config.py)
from bridge import OrderBridge, BridgeState, assert_supported  # noqa: E402
from feed import BarFeed              # noqa: E402
from ledger import Ledger             # noqa: E402
from version import verify_pin, current_commit, VersionMismatch  # noqa: E402

_stop_requested = False

# How often a lost terminal link is retried. `BotMT5.connect()` already burns up to ~40s on its
# own five attempts, so this is a floor between those bursts rather than the poll interval —
# reconnecting is the only thing left to do, but hammering a terminal that is mid-restart just
# fills the log with the same failure.
_LINK_RETRY_SECONDS = 30


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
        # Link-outage bookkeeping. `_link_lost_at` is None whenever the link is believed good,
        # so it doubles as the "have I already alerted" flag — an outage must be announced once,
        # not every ten seconds for an hour.
        self._link_lost_at: float | None = None
        self._link_retry_at = 0.0
        # Stamped from the file `cfg` was just read from, so `_cfg_mtime` always describes
        # the config actually in memory and the first poll sees no phantom change.
        try:
            self._cfg_mtime = live_config.config_path(cfg.bot_key).stat().st_mtime
        except OSError:
            self._cfg_mtime = 0.0

    # ── setup ────────────────────────────────────────────────────────────────
    def _make_logger(self):
        """This bot's own logger: a UTF-8 file in its instance dir, plus stdout.

        **Both streams are forced to UTF-8, and that is a correctness fix.** A Windows console
        is cp1252 and cannot encode the arrows and dashes these messages are written with. When
        that happens `logging` does not raise — it DISCARDS the message and prints a
        UnicodeEncodeError traceback where the line should have been (seen on the VPS,
        2026-07-31, on the "Warmed N bars" line). The log is the audit trail behind "why did
        this trade not work", so a character it cannot encode has to degrade to a replacement
        glyph, never take the whole line with it.

        It deliberately does NOT use `bots/bot_utils.setup_logging`. That helper keys off
        `_instance_dir` and `_config_path`, which this package has no reason to invent — the
        call here passed neither, so it raised and fell through to the fallback on every single
        run, meaning the "shared logging" it advertised never once happened. It also clears the
        ROOT handlers for the whole process. Logging is a dozen lines; a shared helper you have
        to lie to is not sharing.
        """
        import logging

        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass          # already wrapped, or redirected to something without reconfigure

        self.cfg.instance_dir.mkdir(parents=True, exist_ok=True)
        log = logging.getLogger(self.cfg.bot_key)
        if log.handlers:      # constructing a second runner must not double every line
            return log
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        for h in (logging.FileHandler(self.cfg.instance_dir / f"{self.cfg.bot_key}.log",
                                      encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)):
            h.setFormatter(fmt)
            log.addHandler(h)
        log.propagate = False          # the root logger is not this package's to write through
        return log

    def _notify(self, text: str, reply_to=None):
        """Every message this bot sends goes to ITS OWN configured destination — the routing is
        per instance, not global, so two bots on two accounts never share one feed unless their
        configs say to. Empty values fall back to the shared default.

        Returns Telegram's message id so a later message can reply to this one — that is how a
        trade's exit lands under its own entry instead of loose in the feed. None on any failure,
        which the bridge treats as "no thread to reply to" rather than an error.
        """
        try:
            from notify import send_telegram_id
            return send_telegram_id(text,
                                    chat_id=self.cfg.telegram_chat_id,
                                    token_key=self.cfg.telegram_token_key,
                                    reply_to=reply_to)
        except Exception as e:
            self.log.warning(f"Telegram send failed: {e}")
            return None

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

    # ── the terminal link ────────────────────────────────────────────────────
    def probe_link(self) -> tuple[bool, float | None]:
        """Is this process still talking to the terminal? Returns (link_up, balance).

        **`account_info()` is the probe, and the choice matters more than it looks.** The
        obvious probe is "did we get any bars", and it is the wrong one: an empty bar frame is
        what a QUIET MARKET produces as well as a dead terminal, so a check built on it either
        cries wolf out of hours or — the way it actually shipped — treats a dead link as a quiet
        market forever. `account_info()` has no such ambiguity. It answers whenever the link is
        alive, at 3am on a Sunday as readily as mid-session, so `None` means exactly one thing.

        The balance comes back from the same call because it is the same question. Reading it
        separately is what let the two answers disagree: the heartbeat wrote `balance: null` for
        50 minutes while the loop reported itself healthy.
        """
        import MetaTrader5 as mt5
        try:
            info = mt5.account_info()
        except Exception as e:
            # An exception here is a dead link too, not a different event. It is logged rather
            # than raised because the caller's answer is the same either way — reconnect.
            self.log.warning(f"Balance read failed: {e}")
            return False, None
        if info is None:
            return False, None
        return True, float(info.balance)

    def _recover_link(self) -> None:
        """Announce a lost link once, then keep trying to get it back.

        **The re-warm is not optional and is the whole reason this cannot just call
        `connect()`.** However long the outage lasted, that many bars closed without reaching the
        engines — which is precisely the condition `gap_bars() > 4` already exists for, arriving
        by a different route. Resuming on the next bar would leave structure, fibs and liquidity
        carrying a market history that never happened. So recovery walks the identical path:
        rebuild the strategy, re-warm, hand the fresh execution object to the bridge.

        **What it deliberately does NOT do is reason about an open position.** If the broker holds
        one and the rebuilt emulator does not, `OrderBridge._agrees` sees the disagreement on the
        next bar and HALTS — which is the correct outcome and is already built. Teaching this
        method to adopt or close a position would be a second, less tested answer to a question
        the bridge already answers conservatively.
        """
        now = time.time()
        if self._link_lost_at is None:
            self._link_lost_at = now
            self.log.error(
                "MT5 link lost — the terminal is not answering this process. No bars are "
                "arriving and the strategy is NOT seeing the market until it reconnects. The "
                "usual cause is the terminal restarting itself after an auto-update.")
            self.ledger.event("mt5_link_lost", last_bar=str(self.feed.last_bar_time))
            self._notify(
                f"⚠️ *{self.cfg.display_name}* lost its MT5 connection.\n"
                f"It is not seeing bars until it reconnects. Retrying.")

        if now - self._link_retry_at < _LINK_RETRY_SECONDS:
            return
        self._link_retry_at = now

        if not self.connect():
            self.log.warning("Reconnect failed — will retry.")
            return

        self.strategy, _ = self._build_strategy()
        self.bridge._ex = self.strategy.execution
        self.warm()
        self.bridge.begin_live()

        down = now - self._link_lost_at
        self._link_lost_at = None
        self.log.info(f"MT5 link restored after {down / 60:.1f} min — engines re-warmed.")
        self.ledger.event("mt5_link_restored", down_seconds=round(down))
        self._notify(f"✅ *{self.cfg.display_name}* reconnected to MT5 after "
                     f"{down / 60:.0f} min. Engines re-warmed.")

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

    def _bind_code(self) -> None:
        """Point every subsequent import at this bot's own code, before anything imports it.

        A promoted bot imports out of `instances/<bot>/deployed/`, so the repo working tree
        cannot reach it. The paths go to the FRONT of `sys.path`, ahead of the repo entries
        `runner.py` added at module import.

        The `sys.modules` check is the load-bearing part. `sys.path` only decides where a name
        is looked up the FIRST time; anything already imported from the repo stays imported, and
        the freeze would be silently half-applied — the worst outcome available, because the
        startup log would still say "frozen". Nothing in `algos/live/` imports these at module
        scope (checked), so this is a guard against a future import creeping upward, not a
        theoretical worry.
        """
        if not self.cfg.is_frozen:
            return
        leaked = sorted(m for m in sys.modules
                        if m == self.cfg.strategy_package
                        or m.split(".")[0] in ("engines", "backtest")
                        or m.startswith(f"{self.cfg.strategy_package}."))
        if leaked:
            raise RuntimeError(
                f"Cannot freeze this deployment: {', '.join(leaked)} was already imported from "
                f"the repo before the snapshot was bound. The bot would run a mix of deployed "
                f"and repo code while reporting the deployed version. Move that import later.")
        for p in reversed(self.cfg.import_paths):
            sys.path.insert(0, str(p))

    # ── one bot, one process ─────────────────────────────────────────────────
    def already_running(self) -> bool:
        """Is another process ALREADY running this bot? Then this one must not start.

        **Two copies of one bot is the worst duplicate in this system.** They share an account,
        a magic number and a strategy, so they see the same setup on the same bar and each sizes
        a full position off it — double the risk, from a state neither can see. Worse, the
        bridge reconciles against `get_open_positions()` filtered by MAGIC, so each would find
        the other's position and read it as its own; `adopt_broker_state` HALTS on an unknown
        position at startup, which is the only reason this is survivable at all.

        **Measured 2026-08-04:** `schtasks /run /tn SYS_STARTUP` on a box where the bot was
        already up produced exactly this — two `runner.py --bot mpc_sos_fade_demo` processes,
        four minutes apart, with nothing anywhere reporting it. `startup_coordinator` now skips
        a running bot, which is the primary fix; this is the backstop, and it is the one that
        covers the paths the coordinator does not own — the command center, the watchdog, and a
        hand-typed command.

        ⚠ **Matched on `--bot <key>`, not on the script name.** Every live bot is `runner.py`,
        so the script identifies the FLEET; only the key identifies the bot. Matching the script
        would stop a SECOND, different bot from ever starting.

        ⚠ **An unreadable process list answers False and lets this one start.** The opposite
        default would let one bad `wmic` call keep a dead bot down indefinitely, and "cannot
        tell" must not become "refuse forever" for the process whose absence is silent.
        """
        import subprocess
        try:
            r = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "processid,commandline"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception as e:
            self.log.warning(f"Could not check for another copy of this bot ({e}) — starting anyway")
            return False
        me = str(os.getpid())
        for line in r.stdout.splitlines():
            if f"--bot {self.cfg.bot_key}" not in line:
                continue
            pid = line.strip().split()[-1]
            if pid.isdigit() and pid != me:
                self.log.error(
                    f"{self.cfg.display_name} is already running as PID {pid}. Refusing to start "
                    f"a second copy — two processes on one account would both size a full "
                    f"position off the same setup. Stop that one first if this is deliberate.")
                return True
        return False

    # ── the loop ─────────────────────────────────────────────────────────────
    def run(self) -> int:
        if self.already_running():
            return 0        # not a failure — the bot IS running, just not as this process
        commit = current_commit(self.cfg.repo_root)
        try:
            self._bind_code()
            self.source_hash = verify_pin(
                self.cfg.source_roots, self.cfg.strategy_source_hash,
                frozen=self.cfg.is_frozen, bot_key=self.cfg.bot_key)
        except (VersionMismatch, RuntimeError) as e:
            self.log.error(str(e))
            self.ledger.event("version_mismatch", detail=str(e))
            self._notify(f"⛔️ *{self.cfg.display_name}* refused to start — the deployed code is "
                         f"not the version it was promoted to run.")
            return 2
        if not self.cfg.strategy_source_hash:
            self.log.warning(
                f"UNPINNED: this bot has no strategy_source_hash, so nothing checks what it is "
                f"running. Hash {self.source_hash}. Promote it to pin.")
        if not self.cfg.is_frozen:
            # Not fatal — a bot has to run unfrozen once to be promotable. But it is the state
            # that let a `git pull` kill the live bot for three days, so it is never silent.
            self.log.warning(
                f"NOT FROZEN: importing from the repo working tree ({self.cfg.repo_root}), so a "
                f"`git pull` or a lab edit changes what this bot trades. Promote it with "
                f"`python algos/tools/promote.py --bot {self.cfg.bot_key}`.")

        self.log.info(
            f"{self.cfg.display_name} | {self.cfg.strategy_class} v{self.cfg.strategy_version} "
            f"| hash {self.source_hash[:12]} | commit {commit or '?'} "
            f"| {'frozen' if self.cfg.is_frozen else 'REPO'} "
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
                # FIRST, before anything reads a bar. Every data call below returns an empty
                # frame on a dead link, which is indistinguishable from a market that simply
                # has not printed a bar yet — so asking the bars whether the terminal is alive
                # is a question they cannot answer. See `probe_link`.
                link_up, balance = self.probe_link()
                if not link_up:
                    self._recover_link()
                else:
                    gap = self.feed.gap_bars()
                    if gap > 4:
                        # See the module docstring: a hole in the stream is a different market
                        # history, not a recoverable lag.
                        self.log.warning(f"{gap} bars missed — re-warming the engines rather "
                                         f"than resuming with a hole in the stream.")
                        self.ledger.event("rewarm", missed_bars=gap)
                        self.strategy, _ = self._build_strategy()
                        self.bridge._ex = self.strategy.execution
                        self.warm()
                        self.bridge.begin_live()

                    for _, row in self.feed.new_bars().iterrows():
                        self._on_bar(row)

                    self._maybe_reload_runtime()

                # Stamped on BOTH paths, and carrying the link state. A blind bot must still
                # look alive to the watchdog — it IS alive, and a missing stamp would report it
                # as the wrong failure — but the state file has to say which of the two it is,
                # or a blank balance is again the only symptom of a bot that cannot see.
                self._heartbeat(bot_state, link_up=link_up, balance=balance)
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

    def _maybe_reload_runtime(self) -> None:
        """Pick up a runtime config change without restarting — but only while FLAT.

        The command center writes `exec_risk_pct` into this bot's instance config, commits,
        and the VPS pulls it. Nothing tells the bot; it notices the file changed.

        Three rules, in order, and each one exists because of a specific way this could go
        wrong:

        1. **Only `live_config.RUNTIME_RELOADABLE` may be applied.** If ANYTHING else moved
           — a strategy param, the account, the symbol, the version pin — the change is
           REFUSED and left on disk. That is the case where a `git pull` carrying unrelated
           strategy edits reaches a running bot, and quietly absorbing it is precisely what
           the source-hash pin exists to prevent. A restart is required, so the pin is
           re-checked and the engines re-warm on the code that is actually there.
        2. **Applied only when flat, by REBUILDING the strategy.** The config is a frozen
           dataclass shared by every component, so applying a change means constructing a
           fresh strategy and replaying history into it — the same thing a bar gap already
           does. That is why flat matters: a rebuild discards the emulator's position
           state, so doing it mid-trade would orphan a live position. Being flat also makes
           every trade attributable to exactly ONE configuration, which is what keeps the
           live-vs-lab diff readable.
        3. **The mtime is consumed only when the file is actually handled** — applied or
           refused. A pending change stays pending across polls instead of being noticed
           once and forgotten, which would leave the bot running old settings while the UI
           showed the new ones.
        """
        try:
            mtime = live_config.config_path(self.cfg.bot_key).stat().st_mtime
        except OSError:
            return                                   # file briefly missing mid-write
        if mtime == self._cfg_mtime:
            return

        try:
            fresh = live_config.load(self.cfg.bot_key)
        except Exception as e:
            # Do NOT consume the mtime: a half-written file re-reads cleanly next poll.
            self.log.warning(f"Config changed but could not be parsed ({e}) — ignoring it "
                             f"for now and staying on the settings already loaded.")
            return

        allowed, blocked = self._config_delta(fresh)
        if blocked:
            self._cfg_mtime = mtime                  # handled: refused, do not re-warn
            detail = ", ".join(f"{k}: {a!r} → {b!r}" for k, a, b in blocked)
            self.log.error(
                f"Config changed in ways that CANNOT be applied to a running bot: {detail}. "
                f"Still running the settings loaded at startup. Restart the bot to take "
                f"them (the version pin and the engine warmup are re-checked on restart).")
            self.ledger.event("config_change_refused", changes=detail)
            self._notify(f"⚠️ {self.cfg.display_name} — config changed on disk but was NOT "
                         f"applied:\n{detail}\n\nStill running the startup settings. "
                         f"Restart the bot to take them.")
            return

        if not allowed:
            self._cfg_mtime = mtime                  # cosmetic edit (a comment, a note)
            return

        if not self.bridge.is_flat:
            self.log.info("Runtime config change is waiting for the bot to be flat "
                          f"({', '.join(k for k, _, _ in allowed)}).")
            return                                   # mtime NOT consumed — retry next poll

        self._cfg_mtime = mtime
        detail = ", ".join(f"{k} {a} → {b}" for k, a, b in allowed)

        # REBUILD, do not mutate. `SosFadeConfig` is a frozen dataclass and ONE instance is
        # shared by signals, sequence, execution and the secondary arm — so there is no
        # attribute to set, and reaching past `frozen` with object.__setattr__ would leave
        # four components able to disagree about their own settings. Frozen is the property
        # that makes a run reproducible; the reload respects it rather than defeating it.
        #
        # This is the same path a bar gap already takes, for the same reason: throw the
        # strategy away and replay history into a fresh one. It costs a warmup (~3s for
        # 5,000 bars, measured on the VPS) and only ever runs while flat, so there is no
        # position to lose and no bar to miss at a 10s poll.
        self.cfg = fresh
        self.strategy, _ = self._build_strategy()
        self.bridge._ex = self.strategy.execution
        self.warm()
        self.bridge.begin_live()

        self.log.info(f"Runtime config applied while flat (strategy rebuilt): {detail}")
        self.ledger.event("config_applied", changes=detail)
        self._notify(f"⚙️ {self.cfg.display_name} — {detail}\nApplied; the bot was flat.")

    def _config_delta(self, fresh):
        """Split what changed into (reloadable, blocked).

        Compares the WHOLE config, not just strategy params — a changed account number or
        symbol is exactly as disqualifying as a changed fib level, and is the more
        dangerous of the two because it looks like plumbing rather than strategy.
        """
        allowed, blocked = [], []
        for name, new in fresh.strategy_params.items():
            old = self.cfg.strategy_params.get(name)
            if old == new:
                continue
            (allowed if name in live_config.RUNTIME_RELOADABLE
             else blocked).append((name, old, new))
        for name in set(self.cfg.strategy_params) - set(fresh.strategy_params):
            blocked.append((name, self.cfg.strategy_params[name], None))

        for name in ("account", "server", "symbol", "magic", "timeframe",
                     "mt5_path", "strategy_package", "strategy_class",
                     "strategy_source_hash"):
            old, new = getattr(self.cfg, name), getattr(fresh, name)
            if old != new:
                blocked.append((name, old, new))
        return allowed, blocked

    def _heartbeat(self, bot_state, *, link_up: bool | None = None,
                   balance: float | None = None) -> None:
        """Stamp that the loop turned, then record what it saw.

        `heartbeat` is the field SYS_MONITOR reads to catch a process that is ALIVE but no
        longer stepping. Nothing wrote it until 2026-07-31, and the monitor's check reads a
        missing key as 0 and then compares 0 > 300 — so it never fired. A frozen bot still
        answers `wmic`, so it showed RUNNING on the Bots page, in Telegram and in the task
        list while doing nothing. That is the failure the watchdog exists for, and it was
        the one failure it could not see.

        The balance lookup is deliberately OUTSIDE the write and best-effort: a broker read
        that throws must not be able to swallow the stamp. An MT5 outage already has its own
        louder path (`new_bars()` raises → loop_error → a named alert at 10), and letting it
        also suppress the heartbeat would just add a second, vaguer alert for the same event.

        ⚠ **`mt5_link` exists because a null balance is not a diagnosis.** The loop hands both
        values in from its own `probe_link` call — one question, one answer, written together —
        so a blank balance on the Bots page can always be attributed. Read alone, `balance:
        null` is indistinguishable between "the terminal is gone" and "nobody has asked yet",
        and the first of those went unnoticed for 50 minutes on 2026-08-04 for exactly that
        reason. The default `link_up=None` means UNSTATED, never "down": callers that only want
        a stamp (and every pre-2026-08-04 test) still probe here rather than record a failure
        nobody measured.
        """
        if link_up is None:
            link_up, balance = self.probe_link()

        try:
            bot_state.write_bot(self.cfg.bot_key, {
                "status": self.bridge.state.value,
                "heartbeat": time.time(),
                "balance": balance,
                "mt5_link": bool(link_up),
                "account": self.cfg.account,
                "symbol": self.cfg.symbol,
                "version": self.cfg.strategy_version,
                "source_hash": self.source_hash[:12],
                # WHICH VERSION IS RUNNING, reported by the process that is running it.
                # Aaron's requirement, and the reason it has to come from here rather than from
                # reading a file on the VPS: `config.json` states intent and the repo moves under
                # it, so either one can describe a version that is not the one in memory. These
                # four are what the live process actually loaded, so "look at the params for
                # that version" has an unambiguous answer.
                "promoted_commit": self.cfg.promoted_commit,
                "promoted_at": self.cfg.promoted_at,
                "frozen": self.cfg.is_frozen,
                "strategy_package": self.cfg.strategy_package,
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
