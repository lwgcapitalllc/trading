"""backtest.portfolio — stacking several strategies onto one account.

Two views, two questions (see command-center/docs/PORTFOLIO_STACKING.md):

  * `combine`  — the cheap SCREEN. Add up finished standalone runs. Answers "do these
    strategies smooth each other out?" (correlation, diversification drawdown). Idealized:
    it assumes every leg traded a full account and never got blocked, so it OVERSTATES the
    stack. A candidate screen, not the demo result.
  * (later) the shared-account SIMULATOR — the truth. Legs fight for one live risk budget.

Only the combine screen exists today. Pure, offline-testable, importable without the app.
"""

from __future__ import annotations

from .combine import Leg, combine_runs, leg_from_result

__all__ = ["Leg", "combine_runs", "leg_from_result"]
