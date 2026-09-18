"""Grade the market-condition engine — the scoreboard that has to exist before it can be improved.

**Why this package exists.** `engines/regime/` has shipped for months with no measurement of any
kind behind it. The only evidence it has ever produced is one bot's drawdown improving over 40
refusals, which is well inside what luck produces. Without a scoreboard, any change to it is a
guess dressed as an improvement, and the repo's own history says a guess that looks fine is the
expensive kind.

**The reframe this package is built on.** A market condition is latent — there is no true label,
so "is the classifier accurate" is not a question with an answer. Two questions that DO have
answers replace it:

  Grader A (`grade_market.py`)  does a reading of the market predict what the market does next?
  Grader B (`grade_bot.py`)    conditioned on that reading, did a given bot make or lose money?

Grader A runs on tens of thousands of bars and can tell signal from noise. Grader B runs on a few
hundred trades and mostly cannot — which is exactly why both are here, and why every number in
either carries a range rather than a point estimate.

**Nothing here changes any engine, strategy or bot.** It reads bars and a finished trade list and
writes a report. The engine's own arithmetic is imported, never re-implemented, so the thing being
graded is the thing that ships.
"""

from . import forward, grade_bot, grade_market, measures, stats

__all__ = ["forward", "grade_bot", "grade_market", "measures", "stats"]
