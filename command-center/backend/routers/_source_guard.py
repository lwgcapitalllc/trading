"""Refuse a solo run of a strategy that has no setups of its own.

A strategy flagged `requires_source` does not find trades. It arms off ANOTHER leg's closed
trades, so it only exists as a leg inside a stack, added under the parent whose losses it
follows (`routers/stacks.py` → `recovery_parent`).

🔴 THE FAILURE THIS EXISTS TO PREVENT IS SILENT. Handed no source, the rule runs happily over
the whole frame and returns an EMPTY book — which on every page in this app is indistinguishable
from a rule that found no setups. There is no error, no warning and no zero-division; just a run
that completes, grades, and reads as a measurement of the rule's worth. That is rule 1 in the
repo's own list: never let "found nothing" and "was never asked" be the same value.

⚠ The two frontend pickers already hide it (`Strategies.tsx` list, `StackConfigModal.tsx`) and
its detail page disables its Run button — but a disabled button is a LABEL, and rule 7 says a
label is a claim about code somewhere else. This is that code. Every endpoint that CREATES a
solo job from a strategy id calls this before inserting a row.

⚠ It is deliberately generic — it reads the flag, never the strategy id. The next dependent rule
inherits the refusal by declaring `requires_source` in its package, with no router change.

⚠ Retry, rerun and stress-test paths are NOT guarded, and that is not an oversight: each acts on
a row that already exists, and no such row can be created once every creation path refuses. It
was checked rather than assumed — the runs table held zero rows for the flagged strategy when
this landed. Adding a creation path means adding this call to it.
"""

from typing import Any, Mapping, Optional

from fastapi import HTTPException

MESSAGE = (
    "'{name}' has no setups of its own — it only trades after another strategy loses, so on "
    "its own it would produce an empty result that looks exactly like a rule that found "
    "nothing. Add it inside a stack, ticked under the strategy whose losses it should recover."
)


def refuse_if_needs_source(strategy: Optional[Mapping[str, Any]]) -> None:
    """Raise 400 if `strategy` cannot be run on its own. A missing row is somebody else's 404."""
    if not strategy:
        return
    if not strategy.get("requires_source"):
        return
    name = strategy.get("name") or strategy.get("id") or "This rule"
    raise HTTPException(400, MESSAGE.format(name=name))
