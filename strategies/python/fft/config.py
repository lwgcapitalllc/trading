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
