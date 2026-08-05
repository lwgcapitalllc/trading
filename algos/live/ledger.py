"""ledger.py — the live record. Append-only JSONL, **two streams that never overlap.**

**What it is for.** Aaron's standing requirement: *"if I ask you why did this not work, you
could go look at your logs and reference them."* A broker report says a trade lost money. It
cannot say which confluences were present, which gate refused the setup on the bar before, what
the stop was staged to, or that the limit rested for nine bars and was never touched. None of
that is recoverable after the fact — if it is not written as it happens, the question is
unanswerable forever.

## Two files, two questions

Split 2026-08-05 on Aaron's instruction — *"I need them to be very clear, and I need nothing to
be overlapping on each other."* One file per day per stream:

| file | answers | holds |
|---|---|---|
| `decisions-YYYY-MM-DD.jsonl` | **why did it trade, or not trade?** | `bar`, `blocked`, `missed`, `trade`, and the broker-facing order events |
| `health-YYYY-MM-DD.jsonl` | **is the process alive and behaving?** | starts, stops, crashes, link outages, re-warms, config changes, halts, and a periodic `pulse` |

**The dividing line is the SUBJECT, not the severity.** A record about a setup or an order goes
to decisions; a record about the process that runs them goes to health. That is why
`order_refused` (the broker declined a real order) is a decision and `halted` (the bridge
stopped placing anything) is health — one is an answer to *why is there no trade on that
setup*, the other to *why is there no trading at all*.

⚠ **Routing is one dict, `_DECISION_EVENTS`, and it is TEST-ENFORCED.** `test_ledger_streams.py`
greps every `ledger.event("...")` call in `algos/live/` and fails if the name is not classified.
A new event that nobody routed would land in health by default and read as a process fault; the
point of the guard is that adding one makes you choose, rather than discovering the choice
later from a file that quietly grew a stranger. It is the same shape as the calendar's
matches-nothing guard: a list of magic strings that nobody checks is a claim nobody is checking.

## Why the health stream exists at all

The text log (`<bot>.log`) already carries tracebacks, and it is still the place to read one.
But it is prose: it cannot be counted, joined, or diffed, and *nothing about it distinguishes a
bot that stopped from a bot nobody looked at.* The health stream is the machine-readable half —
every lifecycle transition, plus a `pulse` on a fixed cadence so that **a gap in the file is
itself the evidence.** A stall leaves no error line anywhere; it leaves a missing pulse.

**`last_run_status()` is the silent-death detector.** A process killed with `taskkill /f`, or by
the box losing power, writes nothing at all — that is what makes it silent. So the NEXT startup
reads back the previous run's last lifecycle record: anything other than `shutdown` means the
last run died without saying so, and the startup record says which. It is the only way a hard
kill can ever leave a trace, because the trace has to be written by somebody still alive.

## Rotation

Both streams rotate by **UTC day**, and the day is taken from the wall clock at write time, so a
process running across midnight rolls onto the new file with no restart and no rename (renaming
a file Windows holds open fails with a sharing violation — see `tools/log_backup.py`).

`tools/log_backup.py` reports which days are closed and `tools/ledger_sync.py` commits them from
the Mac, **twice a day**. A file for TODAY is still being appended to, so a copy of it can end
in a torn line; the sync truncates that line rather than committing a half-record. See those
modules for why the VPS does not push for itself.

**Why not the lab's `decision_log.py`.** That module's `TradeDecision` is the right shape for a
signal's gate-by-gate story and it explicitly exists to be identical in backtest and live —
but it lives under `command-center/backend/services/`, and `algos/` may not import from there.
The rows written here are deliberately a SUPERSET of its schema so the two can be merged later
without a migration; if the module is ever promoted to a shared top-level location, this file
becomes a thin adapter over it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DECISIONS = "decisions"
HEALTH = "health"

# The filename shapes this package writes. `tools/log_backup.py` imports these rather than
# restating them — one definition of what a ledger file is called, or the backup job and the
# writer drift and the drift shows up as a day that silently never gets committed.
STREAM_RE = re.compile(r"^(decisions|health)-(\d{4})-(\d{2})-(\d{2})\.jsonl$")

# 🔴 The routing table. An event named here goes to the DECISION stream; everything else goes to
# HEALTH. Default-to-health is deliberate: an unclassified event is a process observation until
# somebody says otherwise, and health is the file you open when something is wrong.
#
# ⚠ Adding a `ledger.event("...")` call anywhere in `algos/live/` without adding its name here
# FAILS `test_ledger_streams.py`. That is the point — the choice is made when the event is
# written, by the person who knows what it means.
_DECISION_EVENTS = {
    # the broker's answer to an order the strategy asked for
    "order_placed",
    "order_refused",
    "order_too_small",
    "stop_moved",
    "dry_run_action",
    # a position that existed before this process did, so the strategy never chose it
    "warmup_position_skipped",
}

# Lifecycle records that mark the boundary of a RUN. `last_run_status()` reads back the most
# recent one to decide whether the previous process ended on purpose.
_RUN_END = "shutdown"
_RUN_BOUNDARY = {"startup", "startup_failed", "version_mismatch", _RUN_END}


class Ledger:
    def __init__(self, directory: Path, bot_key: str) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bot_key = bot_key

    def _path(self, stream: str, when: datetime) -> Path:
        return self.dir / f"{stream}-{when.strftime('%Y-%m-%d')}.jsonl"

    def _write(self, stream: str, kind: str, payload: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        row = {"ts": now.isoformat(timespec="seconds"),
               "bot": self.bot_key, "kind": kind, **payload}
        try:
            with self._path(stream, now).open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except Exception as e:
            # A log that can crash the loop it observes is worse than a missing line.
            print(f"ledger: write failed ({e}) — dropped {kind} record")

    # ── the decision stream: why did it trade, or not ────────────────────────
    def bar(self, dec, sig, seq, extra: Optional[dict] = None) -> None:
        """One closed bar's decision. Fields are read defensively (`getattr`) so a strategy
        with a different `Decision` shape logs what it has instead of crashing the bot — this
        module must not know what an A+ stage is in order to keep working."""
        self._write(DECISIONS, "bar", {
            "bar_time": getattr(sig, "time_ms", None),
            "bar_index": getattr(sig, "index", None),
            "close": getattr(sig, "close", None),
            "l_stage": getattr(dec, "l_stage", None),
            "s_stage": getattr(dec, "s_stage", None),
            "long_armed": getattr(dec, "long_armed", None),
            "short_armed": getattr(dec, "short_armed", None),
            "long_edge": getattr(dec, "long_edge", None),
            "short_edge": getattr(dec, "short_edge", None),
            "long_veto": getattr(dec, "long_veto", None),
            "short_veto": getattr(dec, "short_veto", None),
            "stop": getattr(dec, "stop", None),
            "tp1": getattr(dec, "tp1", None),
            "tp2": getattr(dec, "tp2", None),
            "l_sos_bar": getattr(seq, "l_sos_bar", None),
            "s_sos_bar": getattr(seq, "s_sos_bar", None),
            "l_arm_src": getattr(seq, "l_arm_src", None),
            "s_arm_src": getattr(seq, "s_arm_src", None),
            **(extra or {}),
        })

    def blocked(self, block) -> None:
        """A setup the strategy had READY and one of its own rules refused. The lab surfaces
        these on the price chart; live they are the answer to "why didn't it take that"."""
        self._write(DECISIONS, "blocked", {
            "dir": block.dir, "bar_time": block.time_ms, "edge": block.edge,
            "sos_bar": block.sos_bar, "codes": list(block.codes),
            "labels": block.labels, "reasons": block.reasons,
        })

    def missed(self, miss) -> None:
        """A setup that died partway — met some confluences and never became a trade."""
        self._write(DECISIONS, "missed", {
            "dir": miss.dir, "bar_time": miss.time_ms, "edge": getattr(miss, "edge", None),
            "met": getattr(miss, "met", None), "of": getattr(miss, "of", None),
            "near": getattr(miss, "near", None),
            "labels": getattr(miss, "labels", None), "reasons": getattr(miss, "reasons", None),
        })

    # ── trades ───────────────────────────────────────────────────────────────
    def trade_opened(self, *, ticket: int, direction: str, symbol: str, lots: float,
                     price: float, stop: float, tp1: float = 0.0, tp2: float = 0.0,
                     intended_price: float = 0.0, risk_pct: Optional[float] = None,
                     confluences: Optional[dict] = None) -> None:
        """`price` is the BROKER's fill; `intended_price` is where the strategy rested its
        limit. Both are recorded because the gap between them is the only honest measure of
        live-vs-backtest execution quality, and it is invisible if only one is kept.

        `risk_pct` is the sizing setting IN EFFECT for this trade. It can be changed under
        a running bot from the command center (`algos/live/runner._maybe_reload_runtime`),
        so without it a later reader has no way to explain why trade 14 was 0.05 lots and
        trade 15 was 0.02 — and the live-vs-lab comparison, which is the entire reason this
        ledger exists, becomes unreadable at exactly the point it starts to matter.
        """
        self._write(DECISIONS, "trade", {
            "event": "opened", "ticket": ticket, "dir": direction, "symbol": symbol,
            "lots": lots, "price": price, "intended_price": intended_price,
            "slippage": (price - intended_price) if intended_price else None,
            "stop": stop, "tp1": tp1, "tp2": tp2, "risk_pct": risk_pct,
            "confluences": confluences or {},
        })

    def trade_closed(self, *, ticket: int, direction: str, symbol: str, price: float,
                     pnl_usd: float, r_multiple: Optional[float], reason: str,
                     lots: float = 0.0, held_bars: Optional[int] = None,
                     gross_usd: Optional[float] = None, swap_usd: Optional[float] = None,
                     commission_usd: Optional[float] = None,
                     entry_price: Optional[float] = None,
                     intended_price: Optional[float] = None) -> None:
        """Record a closed trade, with its COSTS kept apart from its price move.

        `pnl_usd` is NET — gross + swap + commission — because that is what the balance did.
        The parts ride alongside it rather than replacing it: a netted figure cannot be taken
        apart later, and G5 (PU Prime's spread, swap and commission are assumed, never
        measured) is answered by accumulating these per trade. Every cost field is
        `Optional` and `None` means the broker could not be ASKED, never that the cost was
        zero — the same rule `mt5_link` follows.

        `entry_price`/`intended_price` are repeated here from the OPEN record on purpose.
        Entry slippage is a per-trade fact and the two halves of a trade are separate lines in
        a JSONL file; joining them by ticket to answer "what did the fill cost us" works, but
        it fails silently for any trade whose open record predates a log rotation, and a cost
        study that quietly drops its oldest trades is worse than one that cannot run.
        """
        self._write(DECISIONS, "trade", {
            "event": "closed", "ticket": ticket, "dir": direction, "symbol": symbol,
            "lots": lots, "price": price, "pnl_usd": pnl_usd,
            "gross_usd": gross_usd, "swap_usd": swap_usd, "commission_usd": commission_usd,
            "entry_price": entry_price, "intended_price": intended_price,
            "entry_slippage": ((entry_price - intended_price)
                               if entry_price and intended_price else None),
            "r": r_multiple, "reason": reason, "held_bars": held_bars,
        })

    # ── everything else, routed by name ──────────────────────────────────────
    def event(self, name: str, **fields: Any) -> None:
        """One event, sent to whichever stream it is ABOUT. See `_DECISION_EVENTS`."""
        stream = DECISIONS if name in _DECISION_EVENTS else HEALTH
        self._write(stream, "event", {"event": name, **fields})

    def pulse(self, **fields: Any) -> None:
        """A periodic "still here, and here is how it is going" record.

        ⚠ **This is the one record whose ABSENCE is the signal.** Every other line here is
        written because something happened, so a quiet bot and a dead bot produce identical
        files — which is precisely how the terminal-link outage on 2026-08-04 went unnoticed
        for 50 minutes with the heartbeat ticking and the page saying RUNNING. A fixed cadence
        means a gap in the series is a measurable fact rather than an absence of evidence.

        It is deliberately NOT the same thing as `bot_state.json`'s heartbeat: that file is
        overwritten in place and holds only NOW, so it can tell you the bot is blind and can
        never tell you for how long, or that it happened at all once it recovers.
        """
        self._write(HEALTH, "pulse", fields)

    # ── reading back ─────────────────────────────────────────────────────────
    def last_run_status(self) -> Optional[Dict[str, Any]]:
        """How did the PREVIOUS run end? `None` if there is no earlier run on record.

        Returns the last run-boundary record found, newest file first. A result whose `event`
        is not `shutdown` means the previous process never got to say goodbye — killed,
        crashed, or the box went down — and the caller records that on its own startup line.

        ⚠ **Every failure here returns `None`, and `None` means UNKNOWN, never "clean".** An
        unreadable file must not be able to produce the reassuring answer; the caller
        distinguishes the two, the same rule `mt5_link` follows.
        """
        for path in sorted(self.dir.glob("health-*.jsonl"), reverse=True):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    # A torn last line is expected on a file copied mid-write. Skip it and
                    # keep walking back rather than declaring the whole day unreadable.
                    continue
                if row.get("event") in _RUN_BOUNDARY:
                    return row
        return None

    def previous_run_was_clean(self) -> Optional[bool]:
        """`True` shut down on purpose, `False` died without a word, `None` nothing on record."""
        last = self.last_run_status()
        if last is None:
            return None
        return last.get("event") == _RUN_END
