"""BosExecution — the BOS order layer.

The BOS trades through the EXACT SAME fill / stop-staging / %-risk-sizing / R-grading
machinery as the A+ bot: everything from `_open_position` onward is direction- and
setup-agnostic (it only reads a resting `_Pending`'s edge/sl/tp/qty). So this is a SUBCLASS of
`mpc_sos_fade.execution.Execution` that replaces only what the BOS fork genuinely changes.

Three things differ from `mpc_strategy.pine` and nothing else (the Pine's own header says so):

  1. **the arm is a BOS after an SOS** — no sweep arming, no sweep confluence. `BosTracker`
     owns that; this class reads its `BosState`.
  2. **divergence is a KILL, not a veto-with-exemption** — live, both directions, no post-SOS
     exemption. It blocks the entry, PULLS a resting limit, and optionally closes an open trade.
  3. **the stop model is a dropdown** (`bos_sl_model`) instead of a fib-level dropdown.

Plus one thing the A+ ladder does not have at all: **a THIRD take-profit rung**. The A+ ladder
is TP1 / TP2 / runner; this fork adds TP3 at fib 0.000 (the leg extreme) and defaults it to
100%, so at the shipped settings there is no runner — the whole position leaves at TP3 or at
the ratcheting stop. `_remaining_brackets` is overridden for exactly that.

Entries, staging, trail and sizing are the A+ ladder, unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.execution import BlockedSetup, Execution, _Pending  # noqa: E402

# ── BOS block codes (Pine `f_blkCode` / `f_blkWhy`, 3971-3985) ────────────────────
# The NUMBERS are the Pine's and the meanings are NOT the A+'s — code 5 is the per-regime cap
# here and the HTF breakout filter there. That is why this fork carries its own tables rather
# than reusing the parent's: two code sets sharing one dict is how a chart tag comes to name
# the wrong rule.
# ⚠ Code 7 is APPENDED rather than slotted in at its precedence position, deliberately, so
# codes 1-6 keep the meaning every earlier run and every screenshot already gave them. Only its
# place in the ORDER moved — VWAP is a market-context refusal, so it reports alongside the HTF
# bias gate and ahead of the counting gates below it.
_BOS_BLOCK_LABEL = {
    1: "Direction off",
    2: "Final hour",
    3: "Divergence KILL",
    4: "HTF bias",
    5: "Max trades per regime",
    6: "Stop too tight",
    7: "Session VWAP",
}
_BOS_BLOCK_REASON = {
    1: "'Trade longs' / 'Trade shorts' is OFF for this side.",
    2: "Final-hour rule — no new entries 16:00-18:00 New York, ahead of the daily close.",
    3: "Divergence KILL — an opposing divergence is live, or RSI is at an extreme. For a "
    "continuation that is the fakeout signature.",
    4: "HTF bias requirement — your Weekly / Daily bias gate is not satisfied.",
    5: "Max trades per regime reached — standing down until the next SOS.",
    6: "Minimum stop distance — the stop sits closer to the entry than your floor, so this "
    "position would be oversized and noise-sensitive.",
    7: "Session VWAP — price is not closing on the trend's own side of the line. Re-checked "
    "every bar, so this setup can still arm if price closes back across before the leg dies.",
}
# Pine's `f_blkCode` precedence, as the ORDER the codes are emitted in.
_BOS_PRECEDENCE = ("dir_off", "late", "veto", "htf_bias", "vwap", "capped", "tight")
_BOS_CODE_OF = {
    "dir_off": 1,
    "late": 2,
    "veto": 3,
    "htf_bias": 4,
    "vwap": 7,
    "capped": 5,
    "tight": 6,
}


class BosBlockedSetup(BlockedSetup):
    """A `BlockedSetup` reading the BOS code tables instead of the A+ ones.

    Subclassed rather than parameterised because `build_blocked_setups` duck-types on
    `labels` / `reasons`, so overriding the two properties is the whole change — and it keeps
    the A+ tables unreachable from here, which is the point.
    """

    @property
    def labels(self) -> List[str]:
        return [_BOS_BLOCK_LABEL.get(c, "Blocked") for c in self.codes]

    @property
    def reasons(self) -> List[str]:
        return [_BOS_BLOCK_REASON.get(c, "") for c in self.codes]


class BosExecution(Execution):
    """BOS-only execution. Reuses the parent's whole broker emulator and exit ladder."""

    _bos = None  # set by step() before the parent reaches _entry_edges / _place_entries
    _records_misses = False
    #   The parent's MISSED-setup watch answers "how far did this **A+** setup get before it
    #   died" — it counts the sweep arm, the SOS and the 0.5-0.886 zone, none of which this
    #   fork's setup has. Left on, it would report the near-misses of a trade that was never on
    #   the table. A BOS version is new design work (the tracker already records a death REASON
    #   per leg, which is the raw material), not a port. Same call `mpc_bleg` makes.

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tp3: Optional[float] = None  # the third rung, frozen at placement
        self._atr_bar: Optional[int] = None  # `prime_atr`'s once-per-bar guard
        self._bar_index: Optional[int] = None  # this bar, for the moving stop's fill-bar guard
        self._tracker = None  # set by the strategy; `record_fill` target
        self._bos_blk_keys: List[Optional[tuple]] = [None, None]

    # ── ATR, computed once and read by BOTH layers ───────────────────────────────
    def prime_atr(self, sig) -> Optional[float]:
        """Advance Pine's `ta.atr(14)` for this bar and return it.

        The tracker needs the ATR (F2 / F3) and this class needs it (the ATR stop model and the
        `x ATR(14)` min-stop floor), and in the Pine `atr14` is a single series computed once at
        the top of the execution block. `Execution._update_atr` already reproduces it exactly,
        Wilder warmup included, so the alternative was a second implementation in `bos.py` —
        one question, two answers, which is the defect this repo names most often.

        The strategy calls this BEFORE the tracker; `_update_atr` is then a no-op when the
        parent's `step` reaches it on the same bar. **The guard is what makes that safe**: two
        Wilder steps on one bar would advance the average at double rate and silently produce a
        different ATR from the Pine's on every bar after the first.
        """
        self._update_atr(sig)
        return self._atr

    def _update_atr(self, sig) -> None:  # type: ignore[override]
        if self._atr_bar == sig.index:
            return
        self._atr_bar = sig.index
        super()._update_atr(sig)

    # ── per bar ──────────────────────────────────────────────────────────────────
    def step(self, sig, seq, bos):  # type: ignore[override]
        self._bos = bos
        self._bar_index = sig.index
        dec = super().step(sig, seq)

        # §4a — the divergence KILL on an OPEN trade (Pine 4283-4285 / 4294-4295). Set AFTER
        # the parent's own Phase B, which is where `strategy.close()` sits in the Pine: it is a
        # market order decided at this bar's close and filled at the next bar's OPEN, which is
        # exactly what `_pending_close` means to the parent's Phase A.
        # ⚠ CONFIRMED divergence only, never extreme RSI — an overbought reading is the normal
        # state of a healthy long continuation, and closing on it would flatten the runner on
        # every winner. The entry BLOCK still reads both (`_veto`), exactly as the spec says.
        if (
            self._cfg.bos_close_opp_div
            and self._cfg.show_div
            and self._pos_dir != 0
            and self._pending_close is None
        ):
            opposing = sig.bear_div_active if self._pos_dir > 0 else sig.bull_div_active
            if opposing:
                self._pending_close = ("opp-div", "CLOSE")
        return dec

    # ── the divergence KILL, as a gate ───────────────────────────────────────────
    def _veto(self, sig) -> Tuple[bool, bool]:
        """Pine `bosVetoL` / `bosVetoS` (3785-3786).

        ⚠ This is NOT the parent's `sos_aware_veto`, and the difference is the whole of item 2
        in the module docstring: the A+ veto is judged at the SOS and carries an exemption, so a
        divergence that armed the fade cannot then refuse it. A continuation setup has the
        opposite relationship to divergence — an opposing one is the fakeout signature — so this
        is LIVE, re-read on every bar the limit rests. A divergence appearing during the retrace
        therefore PULLS the order, and one going stale lets it be placed again.

        ⚠ It reads `show_div` alone, not `show_div and div_veto`: the Pine gates it on `showDiv`
        only. `Signals.veto_on` is the A+'s combination and would be the wrong flag here.
        """
        if not self._cfg.show_div:
            return False, False
        return (sig.bear_div_active or sig.veto_rsi_ob, sig.bull_div_active or sig.veto_rsi_os)

    # ── the entry ladder (Pine 3652-3775) ────────────────────────────────────────
    def _entry_edges(self, sig, seq) -> Tuple[Optional[float], Optional[float]]:  # type: ignore[override]
        """Where a limit would rest on each side, or None.

        ⚠ `seq` is accepted to match the parent's signature (2026-08-10) and is DELIBERATELY
        unread. The parent grew it for `exec_nogap_arm`, which gates the A+ no-FVG fallback on
        what armed the SOS — this fork's setup has no SOS arm at all, so honouring that lever
        here would gate a BOS entry on a confluence its own Pine never looks for. The parameter
        is kept rather than dropped because the parent calls this by name from `step()`, and a
        2-arg override is a `TypeError` on the first bar — which is exactly how this was found.

        The A+ ladder verbatim, priced off the BOS anchor leg instead of the SOS leg, and the
        FIRST source that prices the leg wins:

          1. FVG edge (clamped to the band's shallow end; whole gap past it with deep-only on)
          2. Method 3 — a deep gap re-prices onto the nearest fib SHALLOWER than it
          3. Sniper Zone — only on a leg with no qualifying gap, and only a zone anchored at or
             after THIS BOS's bar
          4. a gap STRADDLING the shallow end -> the limit rests exactly at that line
          5. the plain fib — unless `exec_req_fvg` says no gap means no trade

        ⚠ AT THE SHIPPED DEFAULTS ONLY RULE 5 RUNS. `bos_use_fvg` defaulted OFF on 2026-08-07
        because the gap-priced half of the book was the losing half, so the four gap rules are
        dead code at the defaults and live code the moment anyone flips that switch — which is
        why they are ported rather than dropped.
        """
        bos = self._bos
        if bos is None:
            return None, None
        cfg = self._cfg
        long_edge = short_edge = None

        l_on = bos.long.on and bos.l_ready
        s_on = bos.short.on and bos.s_ready
        l_top, s_top = bos.l_top, bos.s_top
        lv, sv = bos.l_levels, bos.s_levels

        # ── 1 + 2: a gap inside the band, optionally re-priced onto a fib ──
        if cfg.bos_use_fvg:
            for top, bot, is_bull, _born in sig.fvgs:
                if (
                    l_on
                    and is_bull
                    and bot <= l_top
                    and top >= lv[0.886]
                    and (not cfg.exec_fvg_deep_only or top <= l_top)
                ):
                    df = (
                        self._deep_fib_edge(bot, top, True, lv[0.618], lv[0.702], lv[0.786])
                        if cfg.exec_deep_fib
                        else None
                    )
                    e = min(top, l_top) if df is None else df
                    # `max` for a long: of two candidate prices, the SHALLOWER is the one price
                    # reaches FIRST, and a resting limit is filled by whichever it reaches first.
                    long_edge = e if long_edge is None else max(long_edge, e)
                if (
                    s_on
                    and not is_bull
                    and top >= s_top
                    and bot <= sv[0.886]
                    and (not cfg.exec_fvg_deep_only or bot >= s_top)
                ):
                    df = (
                        self._deep_fib_edge(bot, top, False, sv[0.618], sv[0.702], sv[0.786])
                        if cfg.exec_deep_fib
                        else None
                    )
                    e = max(bot, s_top) if df is None else df
                    short_edge = e if short_edge is None else min(short_edge, e)

        # ── 3: the Sniper Zone stands in for a missing gap ──
        # `sz_bar >= bos.long.bar` is the load-bearing half: a zone left over from an EARLIER
        # leg would otherwise price this one, which is a limit resting on geometry that belongs
        # to a break the strategy has already moved on from.
        if (
            cfg.bos_use_fvg
            and cfg.exec_conf_sz2
            and cfg.exec_conf_sz
            and sig.sniper_zone_top is not None
            and sig.sniper_zone_bot is not None
            and sig.sz_bar is not None
        ):
            if (
                long_edge is None
                and l_on
                and sig.sz_bullish
                and bos.long.bar is not None
                and sig.sz_bar >= bos.long.bar
            ):
                e = min(sig.sniper_zone_bot, l_top)
                if e >= lv[0.886]:
                    long_edge = e
            if (
                short_edge is None
                and s_on
                and not sig.sz_bullish
                and bos.short.bar is not None
                and sig.sz_bar >= bos.short.bar
            ):
                e = max(sig.sniper_zone_top, s_top)
                if e <= sv[0.886]:
                    short_edge = e

        # ── 4: the least-favorable gap entry — a gap straddling the shallow end ──
        if cfg.bos_use_fvg and cfg.exec_fvg_50:
            for top, bot, is_bull, _born in sig.fvgs:
                if long_edge is None and l_on and is_bull and bot <= l_top and top >= l_top:
                    long_edge = l_top
                if short_edge is None and s_on and not is_bull and bot <= s_top and top >= s_top:
                    short_edge = s_top

        # ── 5: the plain fib ──
        if not (cfg.bos_use_fvg and cfg.exec_req_fvg):
            if long_edge is None and l_on:
                long_edge = self._plain_fib(lv, l_top, bull=True)
            if short_edge is None and s_on:
                short_edge = self._plain_fib(sv, s_top, bull=False)

        return long_edge, short_edge

    def _plain_fib(self, levels: dict, top: Optional[float], *, bull: bool) -> Optional[float]:
        """Pine `lFibEntry` / `sFibEntry` (3697-3700) — the chosen level, CLAMPED to the band's
        shallow end. Picking 0.382 while the band still stops at 0.5 quietly gives you 0.5,
        rather than an entry outside the band every other rule enforces."""
        raw = levels.get(float(self._cfg.bos_entry_fib))
        if raw is None or top is None:
            return raw
        return min(raw, top) if bull else max(raw, top)

    @staticmethod
    def _deep_fib_edge(
        gap_bot: float, gap_top: float, bull: bool, p3: float, p4: float, p5: float
    ) -> Optional[float]:
        """Pine `f_deepFibEdge` (3676-3682) — Method 3.

        The entry price for a DEEP gap whose NEAR EDGE sits past 0.618, or None when the near
        edge is shallower (those keep the exact-edge entry). ⚠ ONLY the near edge decides it: a
        real gap is often tall enough to span 0.702 and 0.786, and what its body crosses is
        irrelevant — the question is which fib price will reach FIRST.
        """
        if bull and gap_top < p3:
            return p3 if gap_top >= p4 else (p4 if gap_top >= p5 else p5)
        if not bull and gap_bot > p3:
            return p3 if gap_bot <= p4 else (p4 if gap_bot <= p5 else p5)
        return None

    # ── the stop model (Pine `f_bosSlRaw` / `f_bosSl`, 3842-3856) ────────────────
    def _bos_stop(
        self, sig, entry: float, levels: dict, broken: Optional[float], *, bull: bool
    ) -> Optional[float]:
        cfg = self._cfg
        model = cfg.bos_sl_model
        if model == "Broken swing level":
            raw = broken
        elif model == "Fib 0.886":
            raw = levels.get(0.886)
        elif model == "Last confirmed swing":
            raw = sig.last_conf_low if bull else sig.last_conf_high
        elif model == "ATR":
            if self._atr is None:
                # The ATR warmup. Pine's arithmetic against `na` yields `na`, `slDist` is then
                # `na`, and `qty > 0` is falsy — so the first 13 bars refuse rather than pass.
                return None
            raw = entry - cfg.bos_sl_atr * self._atr if bull else entry + cfg.bos_sl_atr * self._atr
        else:
            raw = levels.get(1.0)
        if raw is None:
            return None
        buf = cfg.exec_sl_buf_tk * cfg.mintick
        return raw - buf if bull else raw + buf

    # ── entry depth -> the TP ladder (Pine 3862-3868 + 3891-3900) ────────────────
    @staticmethod
    def _tier(edge: Optional[float], levels: dict, *, bull: bool) -> int:
        """2 DEEP (0.618 or deeper) · 1 STANDARD (between 0.5 and 0.618) · 0 SHALLOW.

        Depth is DERIVED from where the limit actually landed, never chosen, and the rule it
        enforces is that **TP1 must never be a level the entry already rests at or past** — or
        the trade "hits TP1" on its own fill bar, stages the stop to breakeven and dies a
        scratch. So each depth gets its own two lower rungs.

        ⚠ It tests fib 0.5 (`levels[0.5]`), NOT the band's configurable shallow end. The two
        differ once `bos_entry_top` is opened to 0.382, and the Pine tests 0.5 — because tier 0
        exists precisely to describe an entry SHALLOWER than 0.5.
        """
        if edge is None:
            return 1
        if bull:
            return 2 if edge <= levels[0.618] else (0 if edge > levels[0.5] else 1)
        return 2 if edge >= levels[0.618] else (0 if edge < levels[0.5] else 1)

    def _targets(self, tier: int, levels: dict, leg, *, bull: bool):
        """TP1 / TP2 / TP3 for a tier. TP3 is ALWAYS fib 0.000 — the leg's own extreme — and
        only the two rungs below it move, one step per depth:

            DEEP     (entry 0.618+)   TP1 0.500  TP2 0.382
            STANDARD (entry at 0.5)   TP1 0.382  TP2 0.236
            SHALLOW  (entry at 0.382) TP1 0.236  TP2 0.118

        ⚠ The measured-move TP3 is built from the BOS LEG's own high/low, not from the anchor
        ladder — so it is the same price under either `bos_fib_anchor`, exactly as the Pine
        computes it. It is ignored when it would land at or behind TP2.
        """
        tp1 = levels[0.5] if tier == 2 else (levels[0.382] if tier == 1 else levels[0.236])
        tp2 = levels[0.382] if tier == 2 else (levels[0.236] if tier == 1 else levels[0.118])
        tp3 = levels[0.0]
        if self._cfg.bos_tp3_measured and leg.high is not None and leg.low is not None:
            span = leg.high - leg.low
            measured = leg.high + span if bull else leg.low - span
            if (measured > tp2) if bull else (measured < tp2):
                tp3 = measured
        return tp1, tp2, tp3

    # ── the arm (Pine `longArmed` / `shortArmed`, 3876-3877) ────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:  # type: ignore[override]
        cfg = self._cfg
        bos = self._bos
        self._pend_long = self._pend_short = None
        if bos is None:
            return

        late, _htf_l, _htf_s, bias_l, bias_s = self._bar_gates(sig)
        veto_l, veto_s = self._veto(sig)
        dec.long_veto, dec.short_veto = veto_l, veto_s

        long_armed = (
            cfg.exec_longs
            and bos.long.on
            and bos.l_ready
            and long_edge is not None
            and not late
            and not bias_l
            and not bos.vwap_block_l
            and (not veto_l or not cfg.bos_respect_veto)
            and bos.traded_l < cfg.bos_max_per_regime
            and self._pos_dir == 0
            and (self._traded_sos_l is None or bos.long.bar != self._traded_sos_l)
        )
        short_armed = (
            cfg.exec_shorts
            and bos.short.on
            and bos.s_ready
            and short_edge is not None
            and not late
            and not bias_s
            and not bos.vwap_block_s
            and (not veto_s or not cfg.bos_respect_veto)
            and bos.traded_s < cfg.bos_max_per_regime
            and self._pos_dir == 0
            and (self._traded_sos_s is None or bos.short.bar != self._traded_sos_s)
        )
        dec.long_armed, dec.short_armed = long_armed, short_armed

        self._record_bos_blocks(
            sig, dec, bos, long_edge, short_edge, late, bias_l, bias_s, veto_l, veto_s
        )

        # deliberate deviation (real runs only): no NEW entry inside the flat-by-close window
        if cfg.flat_by_close and self._in_flat_window(sig):
            long_armed = short_armed = False

        if long_armed:
            self._pend_long = self._build_pending(sig, bos.long, bos.l_levels, long_edge, bull=True)
        if short_armed:
            self._pend_short = self._build_pending(
                sig, bos.short, bos.s_levels, short_edge, bull=False
            )

    def _build_pending(self, sig, leg, levels: dict, edge: float, *, bull: bool):
        """The order, or None when the setup is refused on PRICE rather than on a toggle."""
        cfg = self._cfg
        broken = leg.high if bull else leg.low
        stop = self._bos_stop(sig, edge, levels, broken, bull=bull)
        if stop is None:
            return None
        dist = (edge - stop) if bull else (stop - edge)
        if not self._stop_clears_floor(dist, edge):
            return None
        # Pine `f_qty` refuses on non-positive equity rather than returning a negative size:
        # margin here is 500x, so a loss is not bounded by the account, and once equity goes
        # negative `equity * risk% / dist` is negative — which Pine ABORTS the whole run on
        # ("Invalid `qty` value"), reporting an error instead of the blown account that caused
        # it. Refusing is both the honest simulation and what lets the run finish.
        if self.equity <= 0:
            return None
        tier = self._tier(edge, levels, bull=bull)
        tp1, tp2, tp3 = self._targets(tier, levels, leg, bull=bull)
        qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
        if qty <= 0:
            return None
        pend = _Pending(1 if bull else -1, edge, qty, stop, tp1, tp2, leg.bar)
        # TP3 rides beside the order rather than inside `_Pending`, which is the A+ ladder's
        # two-rung shape and is shared with the other two bots. Widening that dataclass for a
        # rung only this fork has would put a `tp3` field on every A+ and B-LEG order that can
        # only ever be None.
        pend.bos_tp3 = tp3  # type: ignore[attr-defined]
        return pend

    # ── the fill: TP3 and the per-regime counter ────────────────────────────────
    def _open_position(self, pend, fill_price, sig, dec, kind: str = "primary") -> bool:  # type: ignore[override]
        opened = super()._open_position(pend, fill_price, sig, dec, kind=kind)
        if opened:
            self._tp3 = getattr(pend, "bos_tp3", None)
            # F6's counter lives on the TRACKER, which owns the regime — a second copy here is
            # how the cap and the arm would come to disagree about whether it had been reached.
            if self._tracker is not None:
                self._tracker.record_fill(pend.dir)
        return opened

    def _remaining_brackets(self) -> List[Tuple[str, Optional[float], float]]:  # type: ignore[override]
        """TP1 -> TP2 -> TP3 -> runner, with each rung's qty as a percentage of the ORIGINAL
        position (Pine `qty_percent`).

        ⚠ A rung sized 0% is SKIPPED, never placed — the parent already handles that for TP1/TP2
        by computing a zero portion, and the same arithmetic covers TP3. In the Pine it is an
        explicit guard because `strategy.exit(qty_percent = 0)` falls back to closing the WHOLE
        position at that limit, the exact opposite of "bank nothing here". The TP PRICES still
        drive the staged stop whatever the rung sizes are, which is what makes the shipped
        0/0/100 a ratcheting hold rather than an unprotected one.
        """
        cfg = self._cfg
        d = self._pos_dir
        prefix = "L" if d > 0 else "S"
        p1 = self._qty * cfg.exec_tp1_pct / 100.0
        p2 = self._qty * cfg.exec_tp2_pct / 100.0
        p3 = self._qty * cfg.exec_tp3_pct / 100.0
        out: List[Tuple[str, Optional[float], float]] = []
        remaining = self._qty - self._filled_qty
        done = 0.0
        for name, target, portion in (
            ("TP1", self._tp1, p1),
            ("TP2", self._tp2, p2),
            ("TP3", self._tp3, p3),
        ):
            if target is None or remaining <= 1e-12:
                done += portion
                continue
            if self._filled_qty < (done + portion) - 1e-12:
                already = max(0.0, self._filled_qty - done)
                q = min(portion - already, remaining)
                if q > 1e-12:
                    out.append((f"{prefix}-{name}", target, q))
                    remaining -= q
            done += portion
        if remaining > 1e-12:
            out.append((f"{prefix}-RUN", None, remaining))
        return out

    # ── the MOVING stop (Pine `f_moveStop`, 4234-4248) ──────────────────────────
    def _move_stop(self) -> Optional[float]:
        """A trail that runs from the bar AFTER the fill, not from TP2.

        ⚠ DEAD ON THE FILL BAR, on purpose and for the same reason the whole staging block is:
        `_max_fav` is seeded from the ENTRY PRICE, and the fill bar's favourable extreme is
        where price was on its way INTO the resting limit — before the trade existed. Trailing
        off it would stage a stop the trade never earned, which is `BUG_exit_fill_price_mismatch`
        arriving through a second door.
        """
        cfg = self._cfg
        if cfg.bos_move_stop == "Off" or self._max_fav is None:
            return None
        if self._entry_index is None or self._bar_index is None:
            return None
        if self._bar_index <= self._entry_index:
            return None
        d = self._pos_dir
        if cfg.bos_move_stop == "$ of price":
            v = cfg.bos_move_stop_val
            return self._max_fav - v if d > 0 else self._max_fav + v
        swing = self._trail_swing_lo if d > 0 else self._trail_swing_hi
        if swing is None:
            return None
        buf = cfg.bos_move_stop_val * cfg.mintick
        return swing - buf if d > 0 else swing + buf

    def _current_stop(self) -> float:  # type: ignore[override]
        """The staged stop, then the moving stop applied on top — TIGHTER ONLY.

        `max` for a long / `min` for a short is what guarantees it can never loosen breakeven
        or the TP2 floor, so the two trails compose rather than one overriding the other.
        """
        base = super()._current_stop()
        move = self._move_stop()
        if move is None:
            return base
        return max(base, move) if self._pos_dir > 0 else min(base, move)

    # ── blocked setups, with this fork's own code set ───────────────────────────
    def _record_bos_blocks(
        self, sig, dec, bos, long_edge, short_edge, late, bias_l, bias_s, veto_l, veto_s
    ) -> None:
        """Pine 3993-4009 — a setup price and the engine had READY that one of your own toggles
        refused. It places no order, so it is in no trade list; this is its only channel.

        "Ready" deliberately omits every toggle gate — those ARE the blockers being reported.
        It asserts only what price and the engine decide: a live BOS leg, a priced ladder, an
        edge to rest on, flat, and this leg not already traded.

        ONE DELIBERATE DEVIATION FROM THE PINE, the same one the A+ layer takes: every rule
        refusing the setup is recorded, not just the first. The Pine reports one code because a
        chart tag has room for one line; the lab wants to filter by reason, and "blocked by the
        VWAP filter" must stay true when the final hour was also blocking it. The Pine's
        precedence is kept as the ORDER, so `codes[0]` is exactly what `f_blkCode` would have
        returned alone.
        """
        cfg = self._cfg
        for slot, (bull, leg, levels, edge, bias, veto) in enumerate(
            (
                (True, bos.long, bos.l_levels, long_edge, bias_l, veto_l),
                (False, bos.short, bos.s_levels, short_edge, bias_s, veto_s),
            )
        ):
            ready = (
                (bos.l_ready if bull else bos.s_ready)
                and leg.on
                and edge is not None
                and self._pos_dir == 0
                and (
                    (self._traded_sos_l if bull else self._traded_sos_s) is None
                    or leg.bar != (self._traded_sos_l if bull else self._traded_sos_s)
                )
            )
            if not ready or leg.bar is None:
                continue
            # The min-stop refusal happens at placement; recomputed here so a setup refused on
            # PRICE gets a record like every other refusal. A stop that cannot be priced at all
            # (the ATR warmup) reads as "not tight" — the same way `na` propagates through the
            # Pine's `<` comparison, refusing the entry WITHOUT tagging it.
            stop = self._bos_stop(sig, edge, levels, leg.high if bull else leg.low, bull=bull)
            tight = False
            if stop is not None:
                dist = (edge - stop) if bull else (stop - edge)
                tight = self._stop_is_tight(dist, edge)
            flags = {
                "dir_off": not (cfg.exec_longs if bull else cfg.exec_shorts),
                "late": late,
                "veto": veto and cfg.bos_respect_veto,
                "htf_bias": bias,
                "vwap": bos.vwap_block_l if bull else bos.vwap_block_s,
                "capped": (bos.traded_l if bull else bos.traded_s) >= cfg.bos_max_per_regime,
                "tight": tight,
            }
            codes = [_BOS_CODE_OF[k] for k in _BOS_PRECEDENCE if flags[k]]
            if not codes:
                continue
            # Pine's dedupe (`bosBar*10 + code`), generalised to the full reason SET: one record
            # per setup per distinct COMBINATION, so a leg blocked for twenty bars is one
            # record, while a leg that picks up (or sheds) a second blocker is a genuinely
            # different refusal and gets its own.
            key = (int(leg.bar), tuple(codes))
            if key == self._bos_blk_keys[slot]:
                continue
            self._bos_blk_keys[slot] = key
            self.blocks.append(
                BosBlockedSetup(
                    dir=1 if bull else -1,
                    index=sig.index,
                    time_ms=sig.time_ms,
                    codes=codes,
                    edge=float(edge),
                    sos_bar=int(leg.bar),
                )
            )
