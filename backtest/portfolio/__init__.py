"""backtest.portfolio — stacking several strategies onto one account.

Two views, two questions (see command-center/docs/PORTFOLIO_STACKING.md):

  * `combine`  — the cheap SCREEN. Add up finished standalone runs. Answers "do these
    strategies smooth each other out?" (correlation, diversification drawdown). Idealized:
    it assumes every leg traded a full account and never got blocked, so it OVERSTATES the
    stack. A candidate screen, not the demo result.
  * `run_stack` — the shared-account SIMULATOR, the truth. The legs run together on ONE
    balance and ONE live risk budget: a loss on one leg shrinks the next trade of the other,
    and an entry with no room left is shrunk or refused. Every shrink and refusal is logged.
    It also replays each leg SOLO on the same bars, because without that control a difference
    is a mixture of "the cap bit" and "the shared balance re-sized everything".

Pure, offline-testable, importable without the app.
"""

from __future__ import annotations

from .account import PortfolioAccount, SoloAccount
from .combine import Leg, combine_runs, leg_from_result
from .runner import LegSpec, StackRun, contention_summary, run_stack

__all__ = [
    "Leg", "combine_runs", "leg_from_result",
    "PortfolioAccount", "SoloAccount",
    "LegSpec", "StackRun", "run_stack", "contention_summary",
]
