"""FftConfig — every setting of the FFT (first fib touch) bot, as a dataclass.

The rules are `docs/FFT_SPEC.md`. Every field here is one row of that spec's settings table, and
the defaults ARE version 1 — the checklist the students trade (`backtest/notes/fft_ledger.md` →
*The game plan as it stands*).

⚠ **THERE IS NO PINE FILE BEHIND THIS, AND THAT IS A DECISION, NOT A GAP.** Every other port's
config mirrors a TradingView input panel so a parity gate can configure it from an export. FFT runs
on 1-minute bars and the user cannot export 1-minute data from TradingView (2026-09-21), so the
proof is the trade-by-trade match against the study instead — `tools/compare_study.py`. That tool
reads THIS file's defaults, so a default changed here is a different strategy from the one the
study measured, and the match will say so.

⚠ **Only measured alternatives are offered.** Every choice below was run by
`backtest/tools/fft_first_touch_study.py`; sniper entries, gaps, sessions, kill zones, news and
scale-in were measured too and are deliberately NOT settings (ledger → *Tested and NOT profitable*).
"""

from __future__ import annotations

from dataclasses import dataclass

STOP_LEVELS = ("1.0", "88.6")
TARGETS = ("TP2 38.2", "TP1 50")
SIZE_MODES = ("Risk % of equity", "Fixed contracts")

# "Overextended": the 15m trend has made this many continuation BOS since its shift, or more.
OVEREXTENDED_15M_BOS = 4

# The label each choice resolves to on the canonical Structure fib's ladder.
LEVEL_KEY = {"1.0": "1.0", "88.6": "E4", "TP2 38.2": "TP2", "TP1 50": "TP1"}


@dataclass
class FftConfig:
    # ── What trades ──────────────────────────────────────────────────────────
    exec_longs: bool = True
    exec_shorts: bool = True
    size_mode: str = "Risk % of equity"
    # 5% — the user, 2026-09-21: "the FFT strategy is going to be at 5%, just like every other
    # trade". It scales the LOT only; the trade list and every R figure are unchanged by it.
    exec_risk_pct: float = 5.0
    fixed_qty: float = 1.0

    # ── The frames' gates (spec rules 2-5, 9) ────────────────────────────────
    # Continuation BOS the 5m trend may have made since its shift. 0 = the FIRST leg — the one
    # split that held in every window the study measured. -1 = any number.
    max_bos: int = 0
    req_15m: bool = True
    # Skip a setup when the 15m trend behind it has made 4+ continuation BOS since its shift — "the
    # 15m is overextended" (the user, 2026-09-21, from the 02-04 and 03-27 losses). OFF by the
    # user's decision: weak in both windows (2020-25 11 trades at 55%, last year 8 at 62%) but as a
    # skip +1.3R / −0.1R, p 0.08 — not past the luck bar. Here so it can be switched on and so the
    # forward log grades it either way (`tools/forward_log.py`). The 4 is the only cut measured.
    skip_15m_overextended: bool = False
    # Trade ONLY a setup whose pullback takes a day / session / H4 level on its own side before the
    # fill — the A+ sweep label as a filter (the user, 2026-09-22). OFF: the label's lead (2020-25
    # 45/157 trades +0.37R vs +0.07R, p .01; last year 8/34) was found on the same bars it would be
    # judged on. Decided at PLACEMENT from what is already known: a level taken since the extreme,
    # or a live level between price and the 61.8 that the fill itself must take.
    only_sweep: bool = False
    # A sweep setup trades at this multiple of the normal size (the user, 2026-09-22: "love it").
    # 1.5 because it measured best for profit per drawdown: 2020-26, ECN, 5%, every setup taken —
    # 1x +27.7R / DD 4.1R (6.7), 1.5x +36.3R / 5.0R (7.2), 2x +44.9R / 6.4R (7.0), sweep-only
    # 17.2R / 3.2R (5.4). ⚠ In-sample: the sweep lead was found on those bars. 1.0 = off; above
    # 2.0 is refused, past anything measured. ⚠ On a shared account the half-size floor is half of
    # THIS size, so a crowded account refuses a sweep setup below 3.75% of room, not 2.5%.
    sweep_risk_x: float = 1.5
    req_1m_against: bool = True
    skip_closure_legs: bool = True

    # ── Entry, stop, target ──────────────────────────────────────────────────
    # The entry is ALWAYS a limit at the fib's 61.8 — the rule itself. The 70.2 fill the study
    # also measured (fills 56% as often, no better) is deliberately not offered: it is a different
    # order lifecycle (wait for 70.2 after the 61.8 touch), not a different price.
    stop_level: str = "1.0"
    target: str = "TP2 38.2"
    # Trade the leg's SECOND 61.8 touch once the first trade reached TP1 and closed. OFF: it added
    # drawdown as fast as profit (2020-25 return per drawdown 6.1 with it vs 6.4 without, on 28
    # trades). With it off the setup is still RECORDED, as a miss, so the forward log can judge it.
    second_touch: bool = False

    # ── Platform facts — not rules ───────────────────────────────────────────
    point_value: float = 1.0
    symbol: str = "XAUUSD"
    # The broker whose bid/ask the bot judges its OWN fills against when nothing hands it a cost
    # profile — which is the LIVE bot: the runner builds every strategy with none. "" = the chart's
    # bid, as the cost-free study. A profile name = that broker's measured costs with bid/ask fills
    # on, exactly what `tools/compare_study.py` priced the costed gate with: a buy limit fills only
    # when the ASK reaches it, and a short's stop and target trigger on the ask — as the broker does.
    # 🔴 Without it a live FFT HALTS: 23 of 76 buys in 2020-25 touched the 61.8 on the bid in a
    # minute the ask did not (0 of 16 in the last year), so the emulator held a trade the broker had
    # not filled and the bridge's agreement check stops the bot (2026-09-21). A run that passes its
    # own cost profile (the lab) keeps that one; this is used only when there is none.
    fill_profile: str = ""

    def __post_init__(self) -> None:
        # Refuse rather than fall back: every choice is matched by exact string, so a typo would
        # otherwise run a different level while the strategy page still showed the one typed.
        for name, value, allowed in (
            ("stop level", self.stop_level, STOP_LEVELS),
            ("target", self.target, TARGETS),
            ("size mode", self.size_mode, SIZE_MODES),
        ):
            if value not in allowed:
                raise ValueError(f"FFT {name} is {value!r}, which is not one of {allowed}")
        if self.max_bos < -1:
            raise ValueError(f"max 5m continuation BOS is {self.max_bos}; use -1 for any number")
        if not (self.exec_longs or self.exec_shorts):
            raise ValueError(
                "FFT has both longs and shorts switched off, so it can never trade — it would run "
                "and look like a market with no setups in it"
            )
        if self.size_mode == "Risk % of equity" and self.exec_risk_pct <= 0:
            raise ValueError(f"risk per trade is {self.exec_risk_pct}%; it must be above zero")
        if not 1.0 <= self.sweep_risk_x <= 2.0:
            raise ValueError(
                f"sweep setup size is {self.sweep_risk_x}x; it must be 1.0 (off) to 2.0 — sizing a "
                f"setup DOWN is not what it is for, and nothing past 2x was measured"
            )
