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
import logging
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
from alert_format import alert, joined, money  # noqa: E402
from fleet_halt import read_fleet_halt  # noqa: E402  (algos/shared/fleet_halt.py)

_stop_requested = False

# How often a lost terminal link is retried. `BotMT5.connect()` already burns up to ~40s on its
# own five attempts, so this is a floor between those bursts rather than the poll interval —
# reconnecting is the only thing left to do, but hammering a terminal that is mid-restart just
# fills the log with the same failure.
_LINK_RETRY_SECONDS = 30


# How often the health stream gets a `pulse` record. 15 minutes is one M15 bar, so a quiet
# session still leaves a regular mark and a stall is visible as a gap of known size rather than
# as an absence somebody has to interpret.
_PULSE_SECONDS = 15 * 60


def _handle_signal(signum, frame):
    global _stop_requested
    _stop_requested = True


class DailyFileHandler(logging.Handler):
    """A file handler that writes to `<bot>-YYYY-MM-DD.log`, chosen per record.

    **It never renames or moves a file**, which is the whole reason it exists rather than
    `TimedRotatingFileHandler`: the roll happens by opening a different name, so a file the bot
    (or a zip job, or an editor) is holding open is never touched. Renaming an open file on
    Windows raises a sharing violation — `tools/log_backup.py` carries the same rule for the
    same reason, stated there as *"logs are COPIED, never rotated"*.

    The date comes from UTC to match the ledger streams, so one day's text log and one day's
    JSONL cover exactly the same window and can be read side by side.
    """

    def __init__(self, directory, bot_key: str) -> None:
        super().__init__()
        self.dir = Path(directory)
        self.bot_key = bot_key
        self._day = ""
        self._stream = None

    def _target(self, day: str) -> Path:
        return self.dir / f"{self.bot_key}-{day}.log"

    def emit(self, record) -> None:
        try:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if day != self._day or self._stream is None:
                if self._stream is not None:
                    self._stream.close()
                self.dir.mkdir(parents=True, exist_ok=True)
                self._stream = self._target(day).open("a", encoding="utf-8", errors="replace")
                self._day = day
            self._stream.write(self.format(record) + "\n")
            self._stream.flush()
        except Exception:
            # A logger that can take the bot down is worse than a missing line — the same rule
            # `Ledger._write` follows. `handleError` respects `logging.raiseExceptions`.
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
        finally:
            self._stream = None
            super().close()


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
        # Set before anything can fail, because `run()`'s exit record reads it on EVERY path —
        # including the ones that never reach the loop.
        self._started_at = time.time()
        # 0.0, not `now`: the first poll should pulse immediately rather than leave the health
        # stream silent for the first quarter hour of a run, which is exactly the window a
        # start-up problem shows up in.
        self._last_pulse_at = 0.0
        # Link-outage bookkeeping. `_link_lost_at` is None whenever the link is believed good,
        # so it doubles as the "have I already alerted" flag — an outage must be announced once,
        # not every ten seconds for an hour.
        self._link_lost_at: float | None = None
        self._link_retry_at = 0.0
        # The fleet halt LATCHES — see `algos/shared/fleet_halt.py`. Once this is True the bot
        # places nothing for the rest of the process, even if the flag is cleared underneath it,
        # so a flapping or intermittently-unreadable filesystem cannot toggle a live book on and
        # off unattended. Clearing the flag and RESTARTING is the resume path.
        self._fleet_halted = False
        # Stamped from the file `cfg` was just read from, so `_cfg_mtime` always describes
        # the config actually in memory and the first poll sees no phantom change.
        try:
            self._cfg_mtime = live_config.config_path(cfg.bot_key).stat().st_mtime
        except OSError:
            self._cfg_mtime = 0.0

    # ── setup ────────────────────────────────────────────────────────────────
    def _make_logger(self):
        """This bot's own logger: a UTF-8 file **per UTC day** in its instance dir, plus stdout.

        **Both streams are forced to UTF-8, and that is a correctness fix.** A Windows console
        is cp1252 and cannot encode the arrows and dashes these messages are written with. When
        that happens `logging` does not raise — it DISCARDS the message and prints a
        UnicodeEncodeError traceback where the line should have been (seen on the VPS,
        2026-07-31, on the "Warmed N bars" line). The log is the audit trail behind "why did
        this trade not work", so a character it cannot encode has to degrade to a replacement
        glyph, never take the whole line with it.

        **One file per day, and it rolls without renaming anything.** `DailyFileHandler` picks
        its path from the UTC date at write time and reopens when that changes, so a bot running
        across midnight lands in the new day's file on its own. The stock
        `TimedRotatingFileHandler` renames the live file at the roll, and renaming a file
        Windows holds open fails with a sharing violation — the same trap
        `tools/log_backup.py` records, which is why that job COPIES logs rather than rotating
        them. Choosing the name instead of moving the file sidesteps it entirely.

        Daily files are what make the text log backup-able at all: a single ever-growing
        `<bot>.log` has no point at which a copy is final, so it could never be committed as a
        day's record, only re-zipped whole every night.

        It deliberately does NOT use `bots/bot_utils.setup_logging`. That helper keys off
        `_instance_dir` and `_config_path`, which this package has no reason to invent — the
        call here passed neither, so it raised and fell through to the fallback on every single
        run, meaning the "shared logging" it advertised never once happened. It also clears the
        ROOT handlers for the whole process. Logging is a dozen lines; a shared helper you have
        to lie to is not sharing.
        """
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
        for h in (DailyFileHandler(self.cfg.instance_dir, self.cfg.bot_key),
                  logging.StreamHandler(sys.stdout)):
            h.setFormatter(fmt)
            log.addHandler(h)
        log.propagate = False          # the root logger is not this package's to write through
        return log

    def _notify(self, text: str, kind: str, reply_to=None):
        """Every message this bot sends goes to ITS OWN configured destination — the routing is
        per instance, not global, so two bots on two accounts never share one feed unless their
        configs say to. Empty values fall back to the shared default.

        `kind` is `notify.TRADE` or `notify.HEALTH` and decides WHICH of this bot's two rooms it
        lands in. Almost everything this class sends is HEALTH; the two TRADE messages are the
        entry and the exit, and they are both sent by the bridge.

        Returns Telegram's message id so a later message can reply to this one — that is how a
        trade's exit lands under its own entry instead of loose in the feed. None on any failure,
        which the bridge treats as "no thread to reply to" rather than an error.
        """
        try:
            from notify import send_telegram_id, TRADE
            return send_telegram_id(
                text, kind,
                chat_id=(self.cfg.telegram_chat_id if kind == TRADE
                         else self.cfg.telegram_health_chat),
                token_key=self.cfg.telegram_token_key,
                reply_to=reply_to)
        except Exception as e:
            self.log.warning(f"Telegram send failed: {e}")
            return None

    def _notify_health(self, text: str):
        """The overwhelming majority of this class's messages. Named so a call site reads as a
        routing decision rather than as a default nobody chose."""
        from notify import HEALTH
        return self._notify(text, HEALTH)

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
            self._notify_health(alert(
                "🔌", "NO MT5 LINK", self.cfg.display_name,
                "Lost its connection to the terminal — still running, but seeing no market at all.",
                f"Retrying every {_LINK_RETRY_SECONDS}s. If it does not come back, check "
                f"MetaTrader on the VPS."))

        if now - self._link_retry_at < _LINK_RETRY_SECONDS:
            return
        self._link_retry_at = now

        if not self.connect():
            self.log.warning("Reconnect failed — will retry.")
            return

        # Carry any OPEN position across the rebuild. Without this a link outage while a trade
        # was open left the broker holding a position the fresh emulator knew nothing about, and
        # the bridge halted on the next bar — the bot surviving the outage and then being stopped
        # by its own recovery.
        self.bridge.stage_rewarm()
        self.strategy, _ = self._build_strategy()
        self.bridge._ex = self.strategy.execution
        self.warm()
        self.bridge.apply_restore(announce=False)
        self.bridge.begin_live()

        down = now - self._link_lost_at
        self._link_lost_at = None
        self.log.info(f"MT5 link restored after {down / 60:.1f} min — engines re-warmed.")
        self.ledger.event("mt5_link_restored", down_seconds=round(down))
        self._notify_health(alert(
            "🟢", "RECONNECTED", self.cfg.display_name,
            f"Back on the terminal after {down / 60:.0f} minutes. It re-warmed on the bars it "
            f"missed.",
            "Nothing to do."))

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

    def _log_risk_cap(self) -> None:
        """Report the account-level cap's state at every start, capped or not.

        Both states have to be SAID. A cap that is set and a cap that is absent produce identical
        behaviour on an account holding nothing, so the only moment the difference is legible is
        before anything has happened — and "I thought the cap was on" is exactly the belief that
        makes an uncapped second bot feel safe. It goes to the HEALTH stream because it describes
        the machinery, not a setup.
        """
        cap = self.cfg.account_risk_cap_pct
        per_trade = getattr(getattr(self.strategy, "config", None), "exec_risk_pct", None)
        if cap is None:
            self.log.warning(
                f"Account risk cap: NONE. This bot risks {per_trade}% per trade and nothing "
                f"limits what the ACCOUNT carries — correct for a one-bot account, and it means "
                f"a second bot here would stack its risk on top of this one's. See G10.")
        else:
            self.log.info(f"Account risk cap: {cap}% of the live balance, across every bot on "
                          f"this account (this bot risks {per_trade}% per trade).")
        self.ledger.event("risk_cap", account_cap_pct=cap, per_trade_pct=per_trade)

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

        # 🔴 DISCARD what the warm-up recorded, or the decision LEDGER fills with history.
        #
        # `execution.step` appends every blocked and missed setup it sees to `execution.blocks`
        # / `.misses`, and it has no idea whether it is being replayed or traded — it is the
        # same object either way, which is the property that earns Pine parity and is not
        # going to change. `_drain_records()` then writes whatever is sitting there on the
        # FIRST LIVE BAR, stamped with the live timestamp. So each start dumped 5,000 bars of
        # history into the ledger as though the bot had refused those setups today.
        #
        # MEASURED on the real record before this landed, and it was not a corner case — it
        # was ALL of it: across 2026-07-31, 08-04 and 08-05, **560 blocked/missed rows and not
        # one of them from the day it was written**, ages 6 to 75 days, and ~430 of the 560
        # were duplicates because every restart re-dumped the same warm-up (5 starts on 08-05
        # → every setup written 5 times).
        #
        # ⚠ **The damage is to the one record nothing else holds.** No broker statement
        # contains a refusal, so this file is the only evidence of what the bot declined —
        # and "what did it refuse today" was answerable only by comparing each row's own
        # `bar_time` against its `ts`, which nothing did.
        #
        # ⚠ Discarding is right rather than tagging them: a warm-up setup is not a decision
        # this bot made, it is history it replayed to build state, and a backtest already
        # reports it properly. Keeping them under a flag would leave every consumer needing
        # to know about the flag.
        ex = self.strategy.execution
        dropped = len(getattr(ex, "blocks", [])) + len(getattr(ex, "misses", []))
        if hasattr(ex, "blocks"):
            ex.blocks.clear()
        if hasattr(ex, "misses"):
            ex.misses.clear()

        self.log.info(
            f"Warmed {len(df)} bars ({df.index[0]} → {df.index[-1]}) in {time.time()-t0:.1f}s")
        # `replayed_setups` is COUNTED rather than silently dropped: a number that falls to
        # zero is how anyone notices the strategy stopped recording refusals at all.
        self.ledger.event("warmed", bars=len(df), first=str(df.index[0]),
                          last=str(df.index[-1]), replayed_setups=dropped)
        self.reanchor_equity("after warm-up")
        return df

    def reanchor_equity(self, why: str) -> None:
        """Point the emulator's balance back at the REAL account.

        🔴 **This is the second half of the 2026-08-07 oversizing incident, and on its own it
        was a 2.2x error.** `Execution` sizes every order off `self.equity`, which is the
        emulator's own compounding balance. Warm-up replays 5,000 bars THROUGH that emulator,
        and its simulated trades book onto that same balance — so after warming, a bot given a
        real $2,000 was sizing against ~$4,423 of profit it had imagined. Its own orders gave it
        away: every one risked $442.30, which is 10% of a balance that did not exist.

        ⚠ **The warm-up's P&L is not a small error to carry, it is a category error.** Those
        trades never happened. The emulator replays them to build engine state — structure legs,
        fib anchors, gap lists — and its equity curve is a side effect of that, not a record.

        ⚠ **Called only when FLAT**, which is the same seam a runtime config change uses
        (`bridge.is_flat`). Nothing is sized between trades, so re-anchoring there can never
        change a position already open or an order already resting — and it guarantees the next
        order is sized off the truth.

        ⚠ **A balance we cannot read leaves the emulator alone.** Writing a zero, or a stale
        cached figure, would size the next trade off a fabricated number — which is exactly the
        failure being fixed, arriving through the fix.
        """
        ex = getattr(self.strategy, "execution", None)
        account = getattr(ex, "_account", None)
        if account is None:
            return
        _, balance = self.probe_link()
        if not balance:
            self.log.warning(
                f"Could not read the account balance to re-anchor equity {why}; the strategy "
                f"keeps its own ({getattr(account, 'balance', '?')}). Sizing may be refused "
                f"until this clears.")
            return
        was = float(getattr(account, "balance", 0.0))
        if abs(was - balance) < 0.005:
            return
        account.balance = float(balance)
        self.log.info(f"Equity re-anchored to the account {why}: "
                      f"{was:,.2f} → {balance:,.2f}")
        self.ledger.event("equity_reanchored", was=was, now=float(balance), why=why)

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

        ⚠ **The match needs BOTH the runner script and the key, and the key alone is not enough.**
        Every live bot is `runner.py`, so the script identifies the FLEET and only the key
        identifies the bot — matching the script *alone* would stop a second, different bot from
        ever starting. But the key alone matches **`startup_coordinator.py --bot <key>`**, which
        is the process that just launched this one and is still alive while it boots: in
        single-bot mode the coordinator Popens the runner and exits, so this check races it and
        would sometimes refuse to start the very bot it was asked for. **The identical defect,
        one level up, made the command center's Start button a permanent no-op** — found
        2026-08-05 and fixed in `startup_coordinator.bot_is_running` the same way. Only the PAIR
        identifies a running bot.

        ⚠ **The PID exclusion stays as well as the pair, not instead of it.** They cover
        different impostors: the PID rule stops this process matching itself, the pair stops it
        matching its own launcher. Either alone leaves one of the two open.

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
            if f"--bot {self.cfg.bot_key}" not in line or "runner.py" not in line:
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
        """Start, run, and record HOW IT ENDED — on every path this process chooses.

        🔴 **The exit record is what makes a silent death detectable, and it only works if it
        is exhaustive.** Until 2026-08-05 only the clean Ctrl-C path wrote `shutdown`: a failed
        connect (3), a halted bridge (4) and ten consecutive loop errors (6) all returned with
        nothing said, so "the last run wrote no shutdown" meant *killed, crashed, OR one of
        three ordinary refusals* — which is no signal at all. Now every deliberate return
        writes one with its reason and exit code, so the invariant is exact:

            **no `shutdown` record ⇒ the process was killed or the box died.**

        That is the ONLY way a `taskkill /f` or a power cut can leave a trace, because the trace
        has to be written by something still alive — the next startup, reading back.
        """
        code = 0
        reason = "clean"
        try:
            code, reason = self._run()
            return code
        except BaseException as e:                       # noqa: BLE001 — re-raised below
            # KeyboardInterrupt and SystemExit are BaseExceptions and are how this process most
            # often ends by hand. They are an ENDING, not a crash to be swallowed, so the record
            # is written and the exception continues on its way.
            code, reason = 1, f"{type(e).__name__}: {e}"
            raise
        finally:
            self._record_exit(code, reason)

    def _record_exit(self, code: int, reason: str) -> None:
        """Write the run's closing line. Best-effort by design — a logging failure must not be
        able to change the exit code of a trading process."""
        try:
            self.ledger.event("shutdown", exit_code=code, reason=reason,
                              uptime_seconds=round(time.time() - self._started_at))
        except Exception as e:                           # pragma: no cover - defensive
            self.log.warning(f"Could not write the shutdown record: {e}")

    def _run(self) -> tuple[int, str]:
        # ── on the bench? ─────────────────────────────────────────────────────
        # `account: null` means this bot is registered and deliberately not on any account, which
        # is what the Bots page writes when you remove it from one. It is checked FIRST, ahead of
        # the version pin and the process guard, because every one of those describes a bot that
        # is trying to trade and this one is not: refusing later would report a version problem or
        # a credentials problem for a bot whose actual state is "nobody has assigned it".
        #
        # ⚠ It is an ORDINARY ending, not a fault — exit 0, and no Telegram alert. A benched bot
        # is a deliberate configuration, and the boot task plus the watchdog would otherwise raise
        # the same alarm on every attempt for as long as it stayed on the bench. The coordinator
        # skips it before reaching this point; this is the backstop for anything that starts a
        # runner directly.
        if self.cfg.account is None:
            self.log.warning(
                f"{self.cfg.bot_key} is not assigned to an account (account: null), so there is "
                f"nothing for it to trade. Assign it on the command center's Bots → Accounts "
                f"tab, then start it.")
            self.ledger.event("not_assigned")
            return 0, "not assigned to an account"
        if self.already_running():
            # Not a failure — the bot IS running, just not as this process. It is still an
            # exit worth recording: a start that declined to start is exactly the event
            # somebody is looking for when they ask why a restart "did nothing".
            return 0, "another copy of this bot is already running"
        commit = current_commit(self.cfg.repo_root)
        try:
            self._bind_code()
            self.source_hash = verify_pin(
                self.cfg.source_roots, self.cfg.strategy_source_hash,
                frozen=self.cfg.is_frozen, bot_key=self.cfg.bot_key)
        except (VersionMismatch, RuntimeError) as e:
            self.log.error(str(e))
            self.ledger.event("version_mismatch", detail=str(e))
            self._notify_health(alert(
                "⛔", "WILL NOT START", self.cfg.display_name,
                "The code on disk is not the version this bot was promoted to run, so it "
                "refused to start.",
                "It is down and will stay down. Promote it again, or restore the snapshot."))
            return 2, "version pin mismatch"
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
        # 🔴 How the PREVIOUS run ended, recorded on this run's first line. `None` means
        # nothing on record (first ever start, or an unreadable file) and is NOT the same as
        # clean — an unreadable health file must never produce the reassuring answer.
        prev_clean = self.ledger.previous_run_was_clean()
        if prev_clean is False:
            last = self.ledger.last_run_status() or {}
            self.log.warning(
                f"The previous run of this bot ended WITHOUT a shutdown record — its last "
                f"lifecycle line was {last.get('event')!r} at {last.get('ts')}. It was killed, "
                f"it crashed, or the box went down. Nothing else records that.")

        self.ledger.event("startup", version=self.cfg.strategy_version, hash=self.source_hash,
                          commit=commit, dry_run=self.dry_run, symbol=self.cfg.symbol,
                          timeframe=self.cfg.timeframe, account=self.cfg.account,
                          mt5_path=self.cfg.mt5_path,
                          previous_run_clean=prev_clean, pid=os.getpid())

        # BEFORE anything else can take time. A stop request left behind by a previous run
        # would otherwise stop this one seconds after boot, which reads as a bot refusing to
        # start — see `clear_stop_request`.
        self.clear_stop_request()

        if not self.connect():
            self.log.error("Could not connect to MT5 — see the attempts above.")
            return 3, "could not connect to MT5"

        try:
            self.strategy, scfg = self._build_strategy()
            self.feed = BarFeed(self.mt5, self.cfg.timeframe, self.cfg.symbol)
            self.bridge = OrderBridge(self.mt5, self.strategy.execution, self.ledger, self.log,
                                      notify=self._notify, dry_run=self.dry_run,
                                      margin_safety_pct=self.cfg.margin_safety_pct,
                                      account_risk_cap_pct=self.cfg.account_risk_cap_pct,
                                      instance_dir=self.cfg.instance_dir)
            # SAY which state the account-level cap is in, every start. An absent guard is
            # silent by construction, and "no cap" and "a cap that is not working" look
            # identical from outside — the same reason `deadman.py --status` reports an unset
            # URL rather than exiting quietly. It is a HEALTH record, not a decision.
            self._log_risk_cap()
            self.bridge.adopt_broker_state()
            if self.bridge.state is BridgeState.HALTED:
                return 4, "bridge halted while adopting the broker's state"
            self.warm()
            # AFTER the warm-up, never before: `warm()` replays 5,000 bars through this same
            # emulator and opens imaginary trades of its own, so a position applied earlier
            # would be overwritten by a fiction. `adopt_broker_state` above has already proved
            # the record matches what the broker holds; this is the moment it takes effect.
            self.bridge.apply_restore()
            if self.bridge.state is BridgeState.HALTED:
                return 4, "bridge halted while restoring its open position"
            self.bridge.begin_live()
        except Exception as e:
            self.log.error(f"Startup failed: {e}\n{traceback.format_exc()}")
            self.ledger.event("startup_failed", error=str(e))
            self._notify_health(alert(
                "⛔", "WILL NOT START", self.cfg.display_name,
                f"Startup failed: {e}",
                "It is down and will stay down until someone looks at it."))
            return 5, f"startup failed: {e}"

        self._notify_health(alert(
            "🟢", "ONLINE", self.cfg.display_name,
            joined([
                "Trading live" if not self.dry_run else "Dry run — it will place no orders",
                f"{self.cfg.symbol} {self.cfg.timeframe}",
                # `probe_link` is the ONE way this class asks for a balance — it returns None
                # when the terminal cannot be reached, and `money()` renders that as "unknown"
                # rather than $0.00. A startup banner reporting a fabricated zero would be the
                # blind-terminal defect of 2026-08-04 all over again, in the first message the
                # bot ever sends.
                money(self.probe_link()[1]),
            ]),
            f"v{self.cfg.strategy_version} ({self.source_hash[:8]}) · account {self.cfg.account}"))

        return self._loop()

    def _loop(self) -> tuple[int, str]:
        import bot_state
        self.log.info(f"Watching for closed {self.cfg.timeframe} bars "
                      f"(poll {self.cfg.poll_seconds}s). Ctrl-C to stop.")
        bot_state.set_started(self.cfg.bot_key)
        consecutive_errors = 0

        # 🔴 A bar that RAISED while being processed is a hole in the stream, and until
        # 2026-08-05 it was an INVISIBLE one. `BarFeed.new_bars` advances `last_bar_time`
        # when it hands the rows out, not when the caller finishes with them — so an
        # exception in `_on_bar` left the bookmark past a bar the engines never saw.
        # `gap_bars()` then reported 0 (it compares against that same bookmark), the next
        # poll returned nothing, and the bar was gone for good. **Measured against the real
        # `BarFeed`: one fresh bar handed out, bookmark advanced, gap_bars 0, next call
        # empty.** The engines are a streaming state machine, so from that point on every
        # structure and fib reading is computed over a market history that never happened —
        # exactly what `new_bars`' own docstring says must not be allowed to happen silently.
        #
        # It could not surface anywhere either: the outer handler only alerts at TEN
        # CONSECUTIVE loop errors, and one lost bar is one error.
        #
        # Re-delivering the bar is NOT the fix. `_on_bar` steps the strategy and then mirrors
        # its intent onto the broker, so a failure part-way through leaves the engines already
        # advanced; replaying it would step them twice, which is the same desync from the other
        # side. The one recovery that is known-good is the one the gap branch below already
        # uses — rebuild and re-warm from history — so a bar error routes into it.
        stream_broken = False
        bar_errors = 0

        while not _stop_requested:
            try:
                # A stop asked for from OUTSIDE this process. See `stop_requested_on_disk`.
                if self._stop_file_present():
                    self.log.info("Stop requested by file — shutting down cleanly.")
                    break

                # The FLEET switch, checked before any bar is read so no order can be placed on
                # the poll that sees it. Deliberately NOT a `break`: this halts ORDERS, not the
                # process, so the bot keeps observing, keeps its heartbeat and keeps writing its
                # ledger while it is muzzled — and anything already open keeps its broker stop.
                self._check_fleet_halt()

                # FIRST, before anything reads a bar. Every data call below returns an empty
                # frame on a dead link, which is indistinguishable from a market that simply
                # has not printed a bar yet — so asking the bars whether the terminal is alive
                # is a question they cannot answer. See `probe_link`.
                link_up, balance = self.probe_link()
                if not link_up:
                    self._recover_link()
                else:
                    gap = self.feed.gap_bars()
                    if gap > 4 or stream_broken:
                        # See the module docstring: a hole in the stream is a different market
                        # history, not a recoverable lag. Two ways to get one, and they are
                        # reported apart because they mean different things — bars we never
                        # ASKED for (the bot was asleep, the link was down) versus a bar we
                        # were handed and DROPPED, which is a defect on this side.
                        why = (f"{gap} bars missed" if gap > 4
                               else "a bar raised while being processed")
                        self.log.warning(f"{why} — re-warming the engines rather "
                                         f"than resuming with a hole in the stream.")
                        self.ledger.event("rewarm", missed_bars=gap,
                                          after_bar_error=stream_broken)
                        # Same reason as `_recover_link`: a hole in the stream must not cost the
                        # open trade. The re-warm rebuilds the ENGINES from real bars, which is
                        # right; the emulator's own book is handed across intact.
                        self.bridge.stage_rewarm()
                        self.strategy, _ = self._build_strategy()
                        self.bridge._ex = self.strategy.execution
                        self.warm()
                        self.bridge.apply_restore(announce=False)
                        self.bridge.begin_live()
                        stream_broken = False

                    for _, row in self.feed.new_bars().iterrows():
                        try:
                            self._on_bar(row)
                            bar_errors = 0
                        except Exception as e:
                            # BREAK, never continue: the bookmark is already past this bar, so
                            # the rows after it would be fed to engines carrying a hole. Let
                            # the re-warm above rebuild the state on the next poll instead.
                            stream_broken = True
                            bar_errors += 1
                            self.log.error(
                                f"Bar {row.name} raised ({bar_errors}): {e}\n"
                                f"{traceback.format_exc()}")
                            self.ledger.event("bar_error", error=str(e),
                                              bar=str(row.name), count=bar_errors)
                            if bar_errors == 1:
                                # Once per outage, on the transition — the re-warm clears the
                                # counter as soon as a bar lands cleanly, so a recurrence after
                                # a real recovery alerts again. Repeating it every poll is how
                                # a channel that also carries trade alerts gets muted.
                                self._notify_health(alert(
                                    "⚠️", "DROPPED A BAR", self.cfg.display_name,
                                    f"Failed to process the {row.name} bar, so it is re-warming "
                                    f"the engines on the history it missed.",
                                    f"Reason: {e}"))
                            if bar_errors >= 10:
                                self._notify_health(alert(
                                    "⛔", "STOPPING", self.cfg.display_name,
                                    "Ten bars in a row failed to process and re-warming is not "
                                    "fixing it, so it is shutting itself down.",
                                    f"Last error: {e}"))
                                return 6, f"10 consecutive bar errors, last: {e}"
                            break

                    self._maybe_reload_runtime()
                    # Same FLAT seam as the reload above, for the same reason: between trades
                    # nothing is sized, so the emulator's balance can be pulled back onto the
                    # broker's without touching an open position or a resting order. It costs
                    # one account read per bar and it is what keeps the drift that produced the
                    # 2026-08-07 oversizing from accumulating over a long run.
                    if self.bridge and self.bridge.is_flat:
                        self.reanchor_equity("flat between trades")

                # Stamped on BOTH paths, and carrying the link state. A blind bot must still
                # look alive to the watchdog — it IS alive, and a missing stamp would report it
                # as the wrong failure — but the state file has to say which of the two it is,
                # or a blank balance is again the only symptom of a bot that cannot see.
                self._heartbeat(bot_state, link_up=link_up, balance=balance)
                self._maybe_pulse(link_up=link_up, balance=balance)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                self.log.error(f"Loop error ({consecutive_errors}): {e}\n{traceback.format_exc()}")
                self.ledger.event("loop_error", error=str(e), count=consecutive_errors)
                if consecutive_errors >= 10:
                    self._notify_health(alert(
                        "⛔", "STOPPING", self.cfg.display_name,
                        "Ten passes of its main loop failed in a row, so it is shutting itself "
                        "down rather than running blind.",
                        f"Last error: {e}"))
                    return 6, f"10 consecutive loop errors, last: {e}"
            time.sleep(self.cfg.poll_seconds)

        self.log.info("Stop requested — shutting down.")
        # Consume the request, so the file cannot outlive the stop it asked for. The startup
        # clear is the real guard; this only keeps the instance directory honest between runs.
        self.clear_stop_request()
        self._notify_health(alert(
            "⏹", "STOPPED", self.cfg.display_name,
            "Shut down cleanly. It will not come back on its own."))
        try:
            self.mt5.disconnect()
        except Exception:
            pass
        # `run()`'s `finally` writes the shutdown record for every path, this one included —
        # writing it here too would put two closing lines on the one clean exit and make the
        # count of runs disagree with the count of stops.
        return 0, "stop requested"

    # ── being asked to stop, from outside this process ───────────────────────
    #
    # 🔴 **Why a FILE and not a signal.** Every deliberate stop in this system was a
    # `wmic ... call terminate`, i.e. a hard kill — so the bot never wrote a `shutdown` record,
    # and the NEXT startup reported *"the previous run ended WITHOUT a shutdown record — it was
    # killed, it crashed, or the box went down."* That sentence is the silent-death detector,
    # and it was firing on every single restart anybody performed on purpose. **An alarm that
    # fires when you press the button is an alarm you stop reading**, and it was steadily
    # eroding the one signal that tells you a bot died without saying so.
    #
    # Windows has no usable SIGTERM for a console process (`taskkill` without `/f` posts
    # WM_CLOSE, which a Python console app never sees), so a file is the portable answer — and
    # it fits what this loop already is: something that polls its own instance directory every
    # `poll_seconds` and already re-reads its config from there.
    #
    # ⚠ **A STALE request must never kill a fresh bot**, which is the one way this could be
    # worse than the kill it replaces: a stop file left behind by a crash, a failed shutdown or
    # an aborted SSH call would stop every subsequent start seconds after boot, and the bot
    # would look like it was refusing to run. `clear_stop_request()` is called at startup,
    # BEFORE the loop, so the file only ever means "somebody asked while this process was
    # alive".
    STOP_FILE = "stop.request"

    def stop_file_path(self) -> Path:
        return self.cfg.instance_dir / self.STOP_FILE

    def clear_stop_request(self) -> None:
        """Remove any stop request left over from a previous run. Always safe to call."""
        try:
            p = self.stop_file_path()
            if p.exists():
                p.unlink()
                self.log.info(f"Cleared a stale {self.STOP_FILE} from a previous run.")
        except OSError as e:
            # Not fatal, and deliberately not a refusal to start: the worst case is one clean
            # shutdown immediately after boot, which is visible and recoverable. Refusing to
            # start a trading bot because a marker file would not delete is worse.
            self.log.warning(f"Could not clear {self.STOP_FILE}: {e}")

    def _stop_file_present(self) -> bool:
        try:
            return self.stop_file_path().exists()
        except OSError:
            # An unreadable instance directory is not a stop request. Guessing True here would
            # let a transient filesystem error take a live bot down.
            # ⚠ This defaults the OPPOSITE way to `_check_fleet_halt` below, deliberately. A false
            # STOP ends the process; a false HALT only refuses new orders while the bot stays
            # alive with its positions protected. Each default is safe against the failure ITS
            # path causes — see `algos/shared/fleet_halt.py` for the table.
            return False

    def _check_fleet_halt(self) -> None:
        """Halt this bot if the fleet switch is pulled — or if it cannot be READ.

        Latches: once halted, this returns early forever, so clearing the flag under a running bot
        does not quietly put it back in the market. The alert therefore fires exactly once per
        process, which is what stops a switch left on over a weekend from filling the health room.
        """
        if self._fleet_halted:
            return
        reading = read_fleet_halt()
        if not reading.halted:
            return
        self._fleet_halted = True
        self.log.error(f"FLEET HALT ({reading.kind}): {reading.reason}")
        self.ledger.event("fleet_halt", reason=reading.reason, readable=reading.readable)
        if self.bridge is not None:
            # Routed through the bridge rather than a second flag of our own, so there is ONE
            # place that answers "may this bot place an order" and one halt reason a reader can
            # find. A second gate here would be a second thing to keep in step.
            self.bridge.halt(f"fleet halt — {reading.reason}")
        # HEALTH, not TRADE: this is the machinery refusing to trade, and it must not sit in the
        # room that is only opened when a fill arrives.
        self._notify_health(alert(
            "⛔", "FLEET HALT", self.cfg.display_name,
            reading.reason,
            "It keeps running and keeps its open positions and their stops. Clear the flag and "
            "restart the bots to resume — clearing it alone will not."))

    def _maybe_pulse(self, *, link_up: bool | None, balance: float | None) -> None:
        """Write a `pulse` to the health stream on a fixed cadence.

        ⚠ **The cadence is the feature.** Every other record here is written because something
        happened, so a quiet weekend and a wedged process produce identical files. A pulse every
        `_PULSE_SECONDS` means the health stream has a known rhythm, and a missing beat is a
        measurable fact — which is what the 50-minute blind outage on 2026-08-04 had no way to
        leave behind. It carries the same values the heartbeat writes to `bot_state.json`,
        because that file is overwritten in place: it can say the bot is blind NOW and can never
        say for how long, or that it happened at all once it recovers.
        """
        now = time.time()
        if now - self._last_pulse_at < _PULSE_SECONDS:
            return
        self._last_pulse_at = now
        self.ledger.pulse(
            link=bool(link_up), balance=balance,
            bridge_state=self.bridge.state.value if self.bridge else None,
            position=bool(getattr(self.bridge, "_pos_ticket", 0)) if self.bridge else None,
            last_bar=str(self.feed.last_bar_time) if self.feed and self.feed.last_bar_time
            else None,
            bars_seen=self._bar_index,
            gap_bars=self.feed.gap_bars() if self.feed else None,
            uptime_seconds=round(now - self._started_at),
            dry_run=self.dry_run,
        )

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
            self._notify_health(alert(
                "⚠️", "SETTINGS NOT APPLIED", self.cfg.display_name,
                f"Its config changed on disk but the new values were refused, so it is still "
                f"trading the ones it started with.",
                f"Refused: {detail}",
                "Restart it to take them."))
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
        self._notify_health(alert(
            "⚙️", "SETTINGS APPLIED", self.cfg.display_name,
            detail,
            "Applied straight away — the bot was flat. Nothing to do."))

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

        # Overall P&L, and it is written HERE because this is the only process that can
        # measure it. It used to be `pnl_tracker.py`'s, and that job was deleted 2026-08-05
        # having carried an empty bot registry since June — so `total_pnl_pct` had NO writer
        # while the Bots page's "Overall P&L" column and Telegram's /balance both defaulted
        # it to 0.0. A live bot up 5% reported dead flat, in two places, with nothing on
        # either screen able to say the number was never measured.
        #
        # ⚠ `None` when the balance is unknown, NEVER 0.0. A blind terminal returns no
        # balance (see `probe_link`), and 0.0 there is the claim "flat" — the same
        # fabricated-vs-measured collapse `mt5_link` exists to prevent, one field over.
        total_pct = None
        if balance is not None:
            bot_state.ensure_starting_balance(self.cfg.bot_key, balance)
            start = bot_state.read_bot(self.cfg.bot_key).get("starting_balance")
            if start:
                total_pct = round((balance - float(start)) / float(start) * 100, 2)

        try:
            bot_state.write_bot(self.cfg.bot_key, {
                "status": self.bridge.state.value,
                "heartbeat": time.time(),
                "balance": balance,
                "total_pnl_pct": total_pct,
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
