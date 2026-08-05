"""ledger.py — the live trade log. One JSONL line per event, append-only.

**What it is for.** Aaron's standing requirement: *"if I ask you why did this not work, you
could go look at your logs and reference them."* A broker report says a trade lost money. It
cannot say which confluences were present, which gate refused the setup on the bar before, what
the stop was staged to, or that the limit rested for nine bars and was never touched. None of
that is recoverable after the fact — if it is not written as it happens, the question is
unanswerable forever.

**Three record types**, all in one file so the order of events is the order of the file:

- `bar`     — one per closed bar the bot processed. The strategy's decision for that bar: the
              A+ stage per side, the entry edges, the veto, the live stop. Small and
              high-volume; this is the stream that lets a later question be answered at all.
- `trade`   — opened / closed, with the BROKER's real fill, and on close the P&L in dollars
              and in R plus the exit reason.
- `event`   — anything else worth a permanent record: startup with the version pin, halts,
              reconciliation results, refused orders.

**Why not the lab's `decision_log.py`.** That module's `TradeDecision` is the right shape for a
signal's gate-by-gate story and it explicitly exists to be identical in backtest and live —
but it lives under `command-center/backend/services/`, and `algos/` may not import from there.
The rows written here are deliberately a SUPERSET of its schema so the two can be merged later
without a migration; if the module is ever promoted to a shared top-level location, this file
becomes a thin adapter over it.

**Rotation is by day, on purpose.** `decisions-YYYY-MM-DD.jsonl`. The daily backup job commits
yesterday's file once it can never be appended to again, so a commit can never race a write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class Ledger:
    def __init__(self, directory: Path, bot_key: str) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bot_key = bot_key

    def _path(self, when: datetime) -> Path:
        return self.dir / f"decisions-{when.strftime('%Y-%m-%d')}.jsonl"

    def _write(self, kind: str, payload: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        row = {"ts": now.isoformat(timespec="seconds"),
               "bot": self.bot_key, "kind": kind, **payload}
        try:
            with self._path(now).open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
        except Exception as e:
            # A log that can crash the loop it observes is worse than a missing line.
            print(f"ledger: write failed ({e}) — dropped {kind} record")

    # ── the per-bar stream ───────────────────────────────────────────────────
    def bar(self, dec, sig, seq, extra: Optional[dict] = None) -> None:
        """One closed bar's decision. Fields are read defensively (`getattr`) so a strategy
        with a different `Decision` shape logs what it has instead of crashing the bot — this
        module must not know what an A+ stage is in order to keep working."""
        self._write("bar", {
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
        self._write("blocked", {
            "dir": block.dir, "bar_time": block.time_ms, "edge": block.edge,
            "sos_bar": block.sos_bar, "codes": list(block.codes),
            "labels": block.labels, "reasons": block.reasons,
        })

    def missed(self, miss) -> None:
        """A setup that died partway — met some confluences and never became a trade."""
        self._write("missed", {
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
        self._write("trade", {
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
        self._write("trade", {
            "event": "closed", "ticket": ticket, "dir": direction, "symbol": symbol,
            "lots": lots, "price": price, "pnl_usd": pnl_usd,
            "gross_usd": gross_usd, "swap_usd": swap_usd, "commission_usd": commission_usd,
            "entry_price": entry_price, "intended_price": intended_price,
            "entry_slippage": ((entry_price - intended_price)
                               if entry_price and intended_price else None),
            "r": r_multiple, "reason": reason, "held_bars": held_bars,
        })

    # ── everything else ──────────────────────────────────────────────────────
    def event(self, name: str, **fields: Any) -> None:
        self._write("event", {"event": name, **fields})
