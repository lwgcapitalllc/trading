"""RealignExecution — the Realign order layer.

A thin SUBCLASS of `sos_fade.execution.Execution`, the same shape as `BLegExecution`:
everything from the fill onward — the TP ladder, the three-phase stop staging, the runner
trail, %-risk sizing, R grading, the shared-account seam, the cost model — is inherited
unchanged. Only ENTRY placement differs.

🔴 **THE ENTRY IS A MARKET ORDER, WHICH IS NEW IN THIS REPO.** A+ and B-LEG both rest a
LIMIT at a named price; this fork enters at the close of the bar the realignment confirms
on. The consequences are worth stating because two of them cut the other way from every
existing measurement here:

  * There is no fill uncertainty. A resting limit fills or does not, which is what the
    jitter audit found dominates A+'s trade-list stability (~6% of trades change on five
    cents of feed difference). A market entry has none of that.
  * It PAYS THE SPREAD, both ways. A+'s limit entries largely avoid it — measured, the
    flat spread charge costs A+ 5.7R while the bid/ask fill model costs it nothing, since
    the burden lands only on the exit side. That does NOT transfer here. Cost on this
    fork is a real entry-side charge and must never be assumed away from A+'s numbers.

⚠ The A+ diagnostic markers are off, same call `b_leg` makes: BLOCKED codes and MISSED
confluences both answer "how far did this **A+** setup get", and A+ never places an order
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

    def step(self, sig, seq, state):  # type: ignore[override]
        self._state = state
        return super().step(sig, seq)

    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        st = self._state
        if st is None or st.trigger_dir == 0:
            return

        d = st.trigger_dir
        if (d > 0 and not cfg.realign_longs) or (d < 0 and not cfg.realign_shorts):
            return

        # ── the slower-trend gate ────────────────────────────────────────────────
        # ⚠ `trend_dir == 0` means the slow frame has not spoken yet, NOT "no trend".
        #   Refusing there is deliberate: passing everything during warm-up is a filter
        #   that reports itself as on while doing nothing, which is the shape this repo
        #   keeps getting bitten by. Off (`realign_trend_minutes is None`) never sets the
        #   attribute at all, so nothing is gated.
        if cfg.realign_trend_minutes is not None:
            if getattr(self, "trend_dir", 0) != d:
                return

        # The entry is THIS bar's close — the bar the realignment confirmed on.
        entry = sig.close
        sl = st.trigger_stop - d * cfg.realign_sl_buf_tk * cfg.mintick
        dist = (entry - sl) * d
        if dist <= 0:
            return

        # The minimum-stop guard is inherited and is the reason it matters here: qty is
        # risk / dist, so a stop collapsing onto the entry balloons the position. This
        # fork's stops are structural and can be genuinely tight.
        if not self._min_stop_ok(dist, entry):
            return

        qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist

        # TP1 / TP2 off the DEVIATION leg: the pre-deviation extreme is the far end, the
        # stop side is the near end. TP2 = the extreme itself (the setup's own claim),
        # TP1 = the midpoint. The runner rides past TP2 on the inherited trail.
        target = st.trigger_target
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
            if reward < cfg.realign_min_rr * dist:
                return

        pend = _Pending(dir=d, edge=entry, qty=qty, sl=sl, tp1=tp1, tp2=tp2,
                        sos_bar=None, fib=None)
        # Market fill: open immediately at this bar's close rather than resting the order.
        self._open_position(pend, entry, sig, dec)

    def _min_stop_ok(self, dist: float, price: float) -> bool:
        """The inherited minimum-stop floor, read through this fork's own entry path.

        Mirrors `exec_min_stop_mode` / `exec_min_stop_val`. Kept as a small local helper
        rather than reaching into the parent's A+-shaped block, which is entangled with
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
