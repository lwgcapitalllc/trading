"""Plan a settings copy from a graded stress test onto a DEMO bot.

**The one job: turn "apply this stress test to this bot" into a LIST A HUMAN READS, and make
the list and the write the same thing.** Every function here is pure — no HTTP, no SSH, no file
write — so the list can be tested directly rather than through a browser. `routers/bots.py` does
the reading and writing at the edges.

🔴 **WHY A STRESS TEST AND NOT A BACKTEST (Aaron's call, 2026-09-06).** A backtest is one path
through history: it says what happened once. The stress test is what asks whether that result
survives being shaken — reshuffled trade order, held-out windows, and each setting nudged to see
if the result moves. That last phase is the one that matters here: **a knife-edge setting
backtests beautifully and cannot be told apart from a robust one by its equity curve.** Pushing
one to a bot is the failure this gate exists to catch.
⚠ **It costs nothing in fidelity.** A stress test carries no settings of its own — it reads its
parent run's and perturbs COPIES into child runs (`stress_tester._run_child_backtest`). So the
settings this module writes are the parent run's, and a button on either page would write the
same values.

🔴 **DEMO ONLY, and that is the whole point of the stage.** Aaron's pipeline is backtest → stress
test → demo → live. If this could target a live bot the two stages would be one button with two
labels. The bot registry carries `account_type` with **no default** and validates it
(`routers/bots.py::BotReg`), so this is a fact about the bot rather than a naming convention —
`b_leg_demo` is not demo because of its key.

⚠ **A plan NEVER writes.** `plan_import` returns what would change; the caller decides. That
split is why the preview and the apply cannot disagree: they are the same call, and the apply
writes exactly `plan.changes`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# 🔴 Imported, never re-implemented. This is the filter that carries the 2026-09-04 incident
# where a bot was written a setting its strategy does not declare and refused to start on every
# attempt. A second copy of it is a second answer, and the copy is the one that goes stale — see
# the repo rule against a second implementation of anything canonical. The leading underscore is
# `bot_accounts`'s own; it is imported rather than duplicated deliberately.
from services.bot_accounts import _only_declared

# Grades that get a loud warning rather than a refusal. **WARN, NEVER BLOCK — Aaron's call,
# 2026-09-06.** Blocking a low grade sounds safe and fights this repo's own design intent: few
# high-quality setups is the target, so a low trade count is normal here and the stress test
# refuses below 100 trades outright. A gate that cannot be reached by a legitimate config is a
# gate people route around.
_WEAK_GRADES = frozenset({"D", "F"})


@dataclass
class SettingChange:
    """One setting that would move, with both ends of the move.

    ⚠ Both `current` and `proposed` are carried even when one is `None`: a setting the bot does
    not state yet is a different fact from one it states as null, and collapsing them is how a
    preview stops describing the write.
    """

    name: str
    current: Any
    proposed: Any


@dataclass
class ImportPlan:
    """What applying this stress test to this bot would do.

    `blocked` is a REASON, not a bool — a caller that only knows "no" cannot tell the user which
    rule said no.
    """

    blocked: Optional[str] = None
    changes: list[SettingChange] = field(default_factory=list)
    # Settings the run carries that the bot's strategy does not declare. Named, never silently
    # dropped: a setting that vanishes without a word is a setting the reader thinks they applied.
    dropped_notes: list[str] = field(default_factory=list)
    # In the run and already equal on the bot.
    unchanged_count: int = 0
    # On the bot and NOT mentioned by the run — they keep their current values. Reported because
    # "apply this run" reads as "the bot now matches this run", and for a bot that pins 116
    # settings against a run that names fewer, that is not what happens.
    untouched: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not self.changes


def _tf_minutes(bar_type: str, bar_value: Any) -> Optional[int]:
    """Minutes per bar, or **None when it cannot be told** — never a guess.

    ⚠ `None` here means *cannot ask*, and the caller must warn rather than report agreement. A
    tick or range bar has no minute count at all, and silently comparing one to `M15` would
    report a match between two things that were never the same shape.
    """
    if bar_value is None:
        return None
    try:
        n = int(bar_value)
    except (TypeError, ValueError):
        return None
    unit = (bar_type or "").strip().lower()
    if unit in ("minute", "minutes", "min", "m"):
        return n
    if unit in ("hour", "hours", "h"):
        return n * 60
    if unit in ("day", "daily", "d"):
        return n * 1440
    return None


def _bot_tf_minutes(timeframe: str) -> Optional[int]:
    """`"M15"` → 15. **None when it cannot be told**, same rule as above."""
    tf = (timeframe or "").strip().upper()
    if not tf or len(tf) < 2:
        return None
    unit, digits = tf[0], tf[1:]
    if not digits.isdigit():
        return None
    n = int(digits)
    return {"M": n, "H": n * 60, "D": n * 1440}.get(unit)


def _same(a: Any, b: Any) -> bool:
    """Equality that does not report a change where a human sees none.

    ⚠ **`1` and `1.0` are the same setting value and must not appear in the list.** A preview
    padded with numeric-type noise is one nobody reads to the end, and the settings here arrive
    from JSON on one side and a dataclass on the other, so the two spellings are routine.
    ⚠ **Booleans are NOT folded into numbers.** `True == 1` in Python, and a toggle flipping
    between the two is a real change on a bot even though the arithmetic agrees.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def plan_import(
    *,
    run_params: dict,
    bot_params: dict,
    declared: Optional[set],
    account_type: str,
    grade: Optional[str],
    graded: bool,
    run_instrument: str = "",
    bot_symbol: str = "",
    run_bar_type: str = "",
    run_bar_value: Any = None,
    bot_timeframe: str = "",
) -> ImportPlan:
    """The whole decision, as data.

    `graded` is separate from `grade` on purpose: **a stress test that could not be graded
    returns `grade=None`, which is a first-class outcome and not a failure**
    (`services/grading.compute_grade`). Folding the two would let *"nothing graded it"* render as
    *"it passed"*, which is this repo's *no data vs cannot ask* rule arriving on a live bot.
    """
    plan = ImportPlan()

    # ── the one refusal ──────────────────────────────────────────────────────────────────
    if account_type != "demo":
        plan.blocked = (
            f"this bot trades a {account_type or 'unknown'} account, and this control only ever "
            f"writes to a demo bot. Going from demo to live is the next stage and a separate "
            f"decision."
        )
        return plan

    if not run_params:
        plan.blocked = (
            "the stress test's run recorded no settings, so there is nothing to copy. A run with "
            "no stored settings cannot be reproduced either — do not hand-copy from the page."
        )
        return plan

    # ── what may be written at all ───────────────────────────────────────────────────────
    writable, notes = _only_declared(dict(run_params), declared)
    plan.dropped_notes = list(notes)

    for name in sorted(writable):
        proposed = writable[name]
        if name in bot_params and _same(bot_params[name], proposed):
            plan.unchanged_count += 1
            continue
        plan.changes.append(
            SettingChange(name=name, current=bot_params.get(name), proposed=proposed)
        )

    plan.untouched = sorted(set(bot_params) - set(writable))

    # ── warnings: every one of these is LOUD and none of them refuses ────────────────────
    if not graded:
        plan.warnings.append(
            "this stress test has not been graded, so nothing here has judged the settings. "
            "Not graded is not the same as passed."
        )
    elif grade is None:
        plan.warnings.append(
            "this stress test finished without a grade — its ruleset states no drawdown limit, "
            "so there was no bar to grade it against. Read the reasons on the test itself."
        )
    elif grade in _WEAK_GRADES:
        plan.warnings.append(
            f"this stress test graded {grade}. That is the grade the shake-out gives a result it "
            f"does not trust to repeat."
        )

    if run_instrument and bot_symbol and run_instrument.strip() != bot_symbol.strip():
        plan.warnings.append(
            f"the run was measured on {run_instrument} and this bot trades {bot_symbol}. The "
            f"settings will be written anyway; the numbers behind them describe a different "
            f"instrument."
        )

    run_tf = _tf_minutes(run_bar_type, run_bar_value)
    bot_tf = _bot_tf_minutes(bot_timeframe)
    if run_tf is None or bot_tf is None:
        plan.warnings.append(
            f"could not compare the run's bar size ({run_bar_value or '?'} {run_bar_type or '?'}) "
            f"with the bot's ({bot_timeframe or '?'}), so nothing here has checked that they "
            f"match."
        )
    elif run_tf != bot_tf:
        plan.warnings.append(
            f"the run was measured on {run_tf}-minute bars and this bot trades {bot_tf}-minute "
            f"bars. The settings will be written anyway; the numbers behind them describe a "
            f"different chart."
        )

    if plan.untouched:
        plan.warnings.append(
            f"{len(plan.untouched)} settings this bot states are not mentioned by the run and "
            f"keep their current values, so the bot will not end up identical to the run."
        )

    return plan
