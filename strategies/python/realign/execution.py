"""RealignExecution — the Realign order layer.

A thin SUBCLASS of `sos_fade.execution.Execution`, the same shape as `BLegExecution`:
everything from the fill onward — the TP ladder, the three-phase stop staging, the runner
trail, %-risk sizing, R grading, the shared-account seam, the cost model — is inherited
unchanged. Only ENTRY placement differs.

🔴 **THE SHIPPED ENTRY IS A MARKET ORDER, WHICH IS NEW IN THIS REPO.** SOS Fade and B-LEG both
rest a LIMIT at a named price; this fork enters at the close of the bar the realignment
confirms on. The consequences are worth stating because two of them cut the other way from
every existing measurement here:

  * There is no fill uncertainty. A resting limit fills or does not, which is what the
    jitter audit found dominates SOS Fade's trade-list stability (~6% of trades change on five
    cents of feed difference). A market entry has none of that.
  * It PAYS THE SPREAD, both ways. SOS Fade's limit entries largely avoid it — measured, the
    flat spread charge costs SOS Fade 5.7R while the bid/ask fill model costs it nothing, since
    the burden lands only on the exit side. That does NOT transfer here. Cost on this
    fork is a real entry-side charge and must never be assumed away from SOS Fade's numbers.

⚠ **`realign_entry_mode="retest"` rests a limit instead, and it is OFF by default.** It is the
structural answer to the second bullet, it is what Aaron's brother's real trades do, and it
takes the first bullet's fill uncertainty back on in exchange. It reuses the INHERITED fill
path (`_try_entry_fill`) — the placement differs and nothing else does. See the config for
what is measured about it and what is not.

⚠ The SOS Fade diagnostic markers are off, same call `b_leg` makes: BLOCKED codes and MISSED
confluences both answer "how far did this **SOS Fade** setup get", and SOS Fade never places an order
in this fork, so both would describe a trade that was never on the table.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from sos_fade.execution import Execution, _Pending  # noqa: E402


class RealignExecution(Execution):
    _state = None          # set by step() before the parent calls _place_entries
    _records_misses = False

    #: Bar index the resting retest limit was placed on. None = nothing resting.
    _retest_bar = None
    #: Why the last trigger was refused, in words — REPORTING ONLY (`setups.py`). None = none.
    refusal = None
    #: Triggers refused because the retest had no level to rest at. REPORTING — but it is
    #: the number that tells "the retest works" apart from "the lookup dropped trades".
    retest_no_level = 0
    #: The strategy that owns this order layer — set by `RealignStrategy.__init__`. The live
    #: `step` hands the bar back to it.
    _strategy = None

    #: 🔴 **HOW THIS ORDER LAYER OPENS A POSITION, read by `algos/live/` and nothing else.** The
    #: shipped entry fills inside the emulator at the bar's close, so *emulator in a position,
    #: broker flat* is latency the bridge must catch up, not the resting-limit divergence it must
    #: halt on. Inheriting SOS Fade's "resting" would halt the bot on its first trade.
    #: ⚠ **The retest mode rests a limit and is NOT live-capable under this declaration** — the
    #: live `step` below refuses it.
    entry_style = "market"

    def step(self, sig, seq):  # type: ignore[override]
        """One bar, through the live contract. See `strategies/python/live_contract.py`.

        🔴 **It DELEGATES to the strategy's own `step` and adds nothing.** The 15m frame, the
        tracker and this order layer run there in an order that is part of the strategy; running
        them again here would be a second implementation of what the parity gate checks.
        ⚠ `sig` IS the bar state (`PassThroughSignals`); `seq` is always None.
        """
        if self._strategy is None:
            raise RuntimeError(
                "RealignExecution.step() needs the strategy that owns it; build the strategy "
                "rather than the execution on its own.")
        if self._cfg.realign_entry_mode != "market":
            # A resting retest limit under a "market" declaration is the one state the bridge
            # cannot tell from a divergence — it would place a market order for a limit.
            raise RuntimeError(
                f"realign's entry mode is {self._cfg.realign_entry_mode!r}; only the market "
                "entry is live-capable. Set it to 'market' for a live bot.")
        return self._strategy.step(sig)

    # ── pre-trade setup snapshots (backtest/setups.py) — reporting only ───────
    # 🔴 **Overrides the SOS Fade ones it inherits.** Those describe SOS Fade's three confluences,
    # a setup this fork never trades; `_records_misses = False` switched them off. This bot's own
    # setup is the armed false break — `setups.py`.
    @property
    def reports_setups(self) -> bool:
        return self._strategy is not None

    def live_setups(self):
        """What the strategy's setup watch holds. Read AFTER `step()`."""
        return self._strategy.setup_watch.live_setups()

    def drain_setups(self):
        """`live_setups()`, then forget the ended ones. The live runner calls it once per bar."""
        return self._strategy.setup_watch.drain_setups()

    def step_bar(self, sig, seq, state):
        """One bar of the SOS Fade order layer, with this fork's setup state. Called by the strategy."""
        self._state = state
        dec = super().step(sig, seq)
        # 🔴 AFTER the parent's Phase A, and the order is the whole correctness argument.
        # Cancelling a resting limit on the bar its stop was breached, BEFORE that bar has
        # been offered to the fill path, deletes exactly the trades that would have lost —
        # price dipped to the limit and carried on to the stop is a real, losing trade, and
        # erasing it flatters the row in the one direction nobody audits. The limit gets its
        # fill attempt first; only a bar that did NOT fill can kill the setup.
        self._expire_retest(sig)
        self._arm_weekend_flat(sig)
        return dec

    #: 1 — this fork's flat exit is a market order filled at the NEXT bar's open, so the window
    #: must leave a bar of room. See `_arm_weekend_flat`.
    _flat_exit_delay_bars = 1

    def _flat_closes_now(self, sig) -> bool:
        """Never on this bar's close — see `_arm_weekend_flat`.

        The parent flattens at the bar's CLOSE. This fork enters at market and takes every exit
        at the next bar's open, so it arms a request instead and books the exit through the same
        path a stop or a target takes. Answering True here as well would close the position twice
        by two routes, and the two routes grade different R.
        """
        return False

    def _arm_weekend_flat(self, sig) -> None:
        """Request a close before the break, if the switch is on and we are in the window.

        🔴 **THE FRIDAY TEST AND THE CLOCK BOTH MOVED OUT TO `strategies/python/time_flat.py`.**
        What used to live here was a second opinion about when the market closes, sitting beside
        the parent's daily one, and the two could drift. It is now one shared rule with three
        positions — and `realign_strategy.pine` has had exactly that three-position input
        (`flatMode`) since it was written, so the Python side has stopped being the odd one out.

        ⚠ **What this method still owns is the TIMING of the exit, and that is a real difference
        from the parent.** Set AFTER the parent's step, so it lands in `_pending_close` for the
        NEXT bar's open — this fork enters at market and exits the same way. The parent's daily
        path closes at THIS bar's close instead. Both are deliberate; see the parent's `step`.

        ⚠ **On the last bar before the break there is no next bar**, so a position armed too late
        rides the gap — the one case the rule exists to prevent. The shared rule refuses a window
        that is not larger than one bar, which is the guard, and 15 minutes on the 5m frame leaves
        three bars of room.
        """
        if self._pos_dir == 0:
            return
        if self._pending_close is not None:
            return                      # something already decided this bar; do not override it
        if self._flat_due(sig):
            self._pending_close = ("weekend-flat", "TIME")

    def _expire_retest(self, sig) -> None:
        """Age out or invalidate a resting retest limit. No-op for the market entry."""
        if self._retest_bar is None:
            return
        pend = self._pend_long if self._pend_long is not None else self._pend_short
        if pend is None:                      # filled (or refused) — nothing left to manage
            self._retest_bar = None
            return
        age = sig.index - self._retest_bar
        if age < 1:
            return                            # placed this bar; it has not been offered yet
        dead = age >= self._cfg.realign_retest_bars
        if not dead:
            # The setup invalidated before it was ever entered: price reached the stop
            # without ever trading the limit. Filling after this books a trade the rule
            # refuses — the structure it was resting on is gone.
            dead = (sig.low <= pend.sl) if pend.dir > 0 else (sig.high >= pend.sl)
        if dead:
            self._pend_long = self._pend_short = None
            self._retest_bar = None

    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        st = self._state
        # REPORTING ONLY — why this bar's trigger did not become a trade, for the signals room
        # (`setups.py`). Written before each refusal below and read by nothing that decides.
        self.refusal = None
        if st is None or st.trigger_dir == 0:
            return

        d = st.trigger_dir
        if (d > 0 and not cfg.realign_longs) or (d < 0 and not cfg.realign_shorts):
            self.refusal = "that side is switched off"
            return

        # ── the slower-trend gate ────────────────────────────────────────────────
        # ⚠ `trend_dir == 0` means the slow frame has not spoken yet, NOT "no trend".
        #   Refusing there is deliberate: passing everything during warm-up is a filter
        #   that reports itself as on while doing nothing, which is the shape this repo
        #   keeps getting bitten by. Off (`realign_trend_minutes is None`) never sets the
        #   attribute at all, so nothing is gated.
        if cfg.realign_trend_minutes is not None:
            if getattr(self, "trend_dir", 0) != d:
                self.refusal = "the slower trend is not with the trade"
                return

        # ── the N-day momentum gate ──────────────────────────────────────────────
        # Refuses a trade WITH the bigger move. `None` = not enough completed days yet, and is
        # refused for the same reason as the trend gate's 0. Pine refusal code 7.
        if cfg.realign_mom_days is not None:
            m = getattr(self, "mom_dir", None)
            if m is None or m == d:
                self.refusal = (f"the {cfg.realign_mom_days}-day momentum is with the trade — "
                                "this setup only fades it" if m == d
                                else f"not enough days yet for the {cfg.realign_mom_days}-day "
                                "momentum read")
                return

        # ── where the order goes ─────────────────────────────────────────────────
        if cfg.realign_entry_mode == "market":
            # The entry is THIS bar's close — the bar the realignment confirmed on.
            entry = sig.close
        else:
            if cfg.realign_retest_at == "level":
                if st.trigger_level is None:
                    # No attributable structure level, so no price to rest at. Counted and
                    # refused rather than substituted with the close: a silent fallback
                    # would make this a market entry on part of the book and the row would
                    # be measuring a blend of the two things it exists to tell apart.
                    self.retest_no_level += 1
                    self.refusal = "no structure level to rest the retest at"
                    return
                entry = st.trigger_level
            else:
                entry = (st.trigger_stop + sig.close) / 2.0
            # A limit only rests if price still has to come BACK to it. One already at or
            # through the market is not a retest — it would fill at the next bar's open and
            # quietly re-become the market entry, at a worse price and under another name.
            if (entry - sig.close) * d >= 0:
                self.refusal = "price is already past the retest level"
                return

        sl = st.trigger_stop - d * cfg.realign_sl_buf_tk * cfg.mintick
        dist = (entry - sl) * d
        if dist <= 0:
            self.refusal = "the stop is not behind the entry"
            return

        # The minimum-stop guard is inherited and is the reason it matters here: qty is
        # risk / dist, so a stop collapsing onto the entry balloons the position. This
        # fork's stops are structural and can be genuinely tight.
        if not self._min_stop_ok(dist, entry):
            self.refusal = "the stop is tighter than the minimum-stop setting"
            return

        qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist

        # TP1 / TP2 off the DEVIATION leg: the pre-deviation extreme is the far end, the
        # stop side is the near end. TP2 = the extreme itself (the setup's own claim),
        # TP1 = the midpoint. The runner rides past TP2 on the inherited trail.
        target = st.trigger_target
        if cfg.realign_tp_r is not None:
            # A FIXED take-profit: bank the whole trade at N x its own risk. The config
            # refuses unless `exec_tp1_pct` is 100, so nothing survives the first rung —
            # tp2 is set equal so no stage is priced off a target that no longer applies.
            tp1 = tp2 = entry + d * cfg.realign_tp_r * dist
        else:
            tp2 = target
            tp1 = entry + (target - entry) * 0.5

        # ── the reward-to-risk floor ─────────────────────────────────────────────
        # Stop and target are set INDEPENDENTLY here — the stop is the counter-move
        # extreme, the target is the pre-deviation external high — so R:R at entry
        # varies from -3.68 to 14.92 across the book and is known right here.
        # ⚠ `None` means no filter and is NOT 0.0: at 0.0 this reproduces the Pine's
        #   `tgtLong > close` guard, which this Python has never had. See the config.
        if cfg.realign_min_rr is not None:
            reward = (target - entry) * d
            # 🔴 `reward <= 0` is refused whatever the floor, as the Pine's strict `tgtLong > px`
            #    does. With the floor at 0.0 this read `reward < 0` until 2026-09-16 and took a
            #    retest whose limit sat EXACTLY on the target — a trade with no reward, which the
            #    third parity export caught on 2026-08-07 08:30 (limit and target both 4304.13).
            if reward <= 0 or reward < cfg.realign_min_rr * dist:
                self.refusal = "the reward-to-risk is below the floor"
                return

        pend = _Pending(dir=d, edge=entry, qty=qty, sl=sl, tp1=tp1, tp2=tp2,
                        sos_bar=None, fib=None)
        if cfg.realign_entry_mode == "market":
            # Market fill: open immediately at this bar's close rather than resting the order.
            if self._open_position(pend, entry, sig, dec):
                # 🔴 The stop goes out WITH a market order, so the live bridge reads it off this
                # bar's decision — and the parent states the stop only on bars that START in a
                # position. Left unset, the bridge refuses the order for having no stop and the
                # bot halts. Reporting only on a replay: nothing reads `dec.stop` back.
                dec.stop = self._current_stop()
            else:
                self.refusal = "the order was refused — no size, or no room under the account's risk cap"
            return
        # Rest the limit and let the INHERITED fill path take it — `_try_entry_fill` already
        # prices a limit against the bar, pays the ask on a long, and gives a gap the better
        # fill. A second fill path here would be a second implementation of the one thing in
        # this file that is already right.
        # ⚠ A newer trigger deliberately REPLACES an older resting order: the setup it was
        # waiting on has been overtaken by a fresher one on the same structure.
        if d > 0:
            self._pend_long, self._pend_short = pend, None
        else:
            self._pend_short, self._pend_long = pend, None
        self._retest_bar = sig.index

    def _min_stop_ok(self, dist: float, price: float) -> bool:
        """The inherited minimum-stop floor, read through this fork's own entry path.

        Mirrors `exec_min_stop_mode` / `exec_min_stop_val`. Kept as a small local helper
        rather than reaching into the parent's SOS Fade-shaped block, which is entangled with
        fib edges this fork does not compute.
        """
        cfg = self._cfg
        mode = getattr(cfg, "exec_min_stop_mode", "Off")
        val = getattr(cfg, "exec_min_stop_val", 0.0)
        if mode == "Off" or val <= 0:
            return True
        if mode == "% of price":
            return dist >= price * val / 100.0
        if mode == "Fixed $":
            return dist >= val
        if mode == "x ATR(14)":
            # No ATR is computed on this path; refusing on a floor we cannot evaluate
            # would silently block every trade, and passing would report a filter as on
            # and doing nothing. Neither is acceptable, so say so.
            raise NotImplementedError(
                "exec_min_stop_mode='x ATR(14)' is not wired in realign — use "
                "'% of price' or 'Fixed $', or switch the guard Off deliberately.")
        raise ValueError(f"unknown exec_min_stop_mode {mode!r}")
