"""The third answer a broker call can give.

🔴 **Rule 1 of the root `CLAUDE.md`, given a value.** "It did not happen" and "I could not find
out whether it happened" are different facts with opposite safe responses: the first says try
again, the second says do NOT try again until you know. Before 2026-08-25 both arrived as
`None`, the retry loop could not tell them apart, and one limit order became five positions.

⚠ **It lives in its own module, with no imports, deliberately.** It was first defined inside
`mt5_ops.py`, and importing it into `bridge.py` pulled the whole broker module into the bridge's
import graph — which reordered `sys.path` and made a DIFFERENT `fleet_halt` win, breaking three
unrelated test modules with a circular-import error that named neither file. A shared vocabulary
type must not carry a dependency, or it stops being shareable.
"""


class _Unknown:
    """Falsy on purpose: an old `if ticket:` call site degrades to the conservative reading
    rather than to a crash. Anything that must act on the difference tests `is UNKNOWN`."""

    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()
