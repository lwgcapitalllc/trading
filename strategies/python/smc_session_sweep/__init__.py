"""The session-sweep Python port — the decision core and its parity gate.

🔴 **No `LAB_STRATEGY` here, deliberately.** Declaring one registers a strategy the lab cannot
replay: this strategy reads THREE bar streams (1m confirmation, 5m zones, 15m direction) and
`backtest/` replays two. A registry that answers confidently and wrongly is rule 8. The two
honest routes out are in this package's CLAUDE.md.
"""

from .config import SessionSweepConfig
from .core import BarInput, BarOutput, SessionSweepCore

__all__ = ["SessionSweepConfig", "SessionSweepCore", "BarInput", "BarOutput"]
