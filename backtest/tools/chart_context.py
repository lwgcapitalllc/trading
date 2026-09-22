"""chart_context.py — what the canonical engines DREW, bar by bar, for a replay chart.

A blind replay page (`blind_replay.py`) shows structure breaks, swing labels and liquidity levels.
Those must be the ones the engines printed while the study ran — never a second detection — so
this records them off each `EngineStack.step` snapshot. Strategy-agnostic: feed it any stack's
snapshots in bar order.

  breaks  (bar, bar of the swing broken, price, "BOS"|"SOS", "bull"|"bear", "ext"|"int")
  swings  (bar it became known, swing bar, price, HH|HL|LH|LL, "ext"|"int")
  levels  id -> [name, price, bar created, bar taken | None, bar evicted | None, rule]

⚠ **A level's "taken" bar is the bar the engine REPORTED it, at that bar's close.** A replay cut
inside a bar must decide for itself whether the part of the bar it shows had reached the level —
see `fft_blind_deck.py`, which checks the minutes up to the cut.

The logic is the one `loaded_level_confluence._record_context` has used since 2026-09-16; that tool
still carries its own copy (moving it is a change to a tool with its own validated deck).
"""

from __future__ import annotations

from dataclasses import dataclass, field

_INT_LABEL = {"iHH": "HH", "iLL": "LL", "iLH": "LH", "iHL": "HL"}  # iSH / iSL (the seed) skipped
LEVEL_KINDS = frozenset({"daily", "weekly", "session", "h4"})


@dataclass
class ChartContext:
    kinds: frozenset = LEVEL_KINDS
    breaks: list = field(default_factory=list)
    swings: list = field(default_factory=list)
    levels: dict = field(default_factory=dict)

    def record(self, i: int, snap) -> None:
        x, n, liq = snap.structure.external, snap.structure.internal, snap.liquidity
        if x.bull_bos and x.bull_bos_price is not None:
            loc = x.bull_bos_h_loc if x.bull_bos_h_loc is not None else i
            self.breaks.append(
                (i, loc, x.bull_bos_price, "SOS" if x.bull_sos else "BOS", "bull", "ext")
            )
        if x.bear_bos and x.bear_bos_price is not None:
            loc = x.bear_bos_l_loc if x.bear_bos_l_loc is not None else i
            self.breaks.append(
                (i, loc, x.bear_bos_price, "SOS" if x.bear_sos else "BOS", "bear", "ext")
            )
        if n is not None:
            for bull in (True, False):
                if not ((n.bull_bos or n.bull_sos) if bull else (n.bear_bos or n.bear_sos)):
                    continue
                sos = bool(n.bull_sos if bull else n.bear_sos)
                if bull:
                    px, loc = (
                        (n.bull_sos_price, n.bull_sos_loc)
                        if sos
                        else (n.bull_bos_price, n.bull_bos_loc)
                    )
                else:
                    px, loc = (
                        (n.bear_sos_price, n.bear_sos_loc)
                        if sos
                        else (n.bear_bos_price, n.bear_bos_loc)
                    )
                if px is not None and loc is not None:
                    self.breaks.append(
                        (i, loc, px, "SOS" if sos else "BOS", "bull" if bull else "bear", "int")
                    )
        for lab, px, at in (
            (x.broken_high_label, x.broken_high_price, x.broken_high_index),
            (x.broken_low_label, x.broken_low_price, x.broken_low_index),
        ):
            if lab in ("HH", "LH", "HL", "LL") and px is not None and at is not None:
                self.swings.append((i, at, px, lab, "ext"))
        if n is not None:
            for lab, px, at in (
                (
                    n.swing_high_label if n.new_swing_high else None,
                    n.new_swing_high_price,
                    n.new_swing_high_index,
                ),
                (
                    n.swing_low_label if n.new_swing_low else None,
                    n.new_swing_low_price,
                    n.new_swing_low_index,
                ),
                (n.demoted_high_label, n.demoted_high_price, n.demoted_high_index),
                (n.demoted_low_label, n.demoted_low_price, n.demoted_low_index),
            ):
                if lab in _INT_LABEL and px is not None and at is not None:
                    self.swings.append((i, at, px, _INT_LABEL[lab], "int"))
        if liq is None:
            return
        for v in liq.created:
            if v.kind in self.kinds and v.side in ("high", "low"):
                self.levels[v.id] = [v.name, v.price, i, None, None, v.rule]
        for v in liq.mitigated:
            if v.id in self.levels and self.levels[v.id][3] is None:
                self.levels[v.id][3] = i
        for v in liq.evicted:
            if v.id in self.levels and self.levels[v.id][4] is None:
                self.levels[v.id][4] = i
