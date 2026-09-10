"""pine_constants.py — read a value out of a Pine source, so Python can be CHECKED against the Pine
rather than trusted to match it.

Pine has no import, and the indicator locks most of its tuning values as plain constants
(`int eqMax = 14`), so the one way to hold a Python default to the Pine is to read the Pine:

    pine_value("eqMax")                     -> 14
    pine_value("divValidBars", RSI_EXPORT)  -> 100            an `input.int(...)` default
    pine_value("fvgRequireClose")           -> (False, True)  a `cond ? a : b` split, in that order

⚠ EXACTLY ONE declaration must match, or it raises. A reader that finds two can only guess which one
the chart runs, and a guess is what this exists to replace. A reassignment (`:=`) is never read.
⚠ Tests only. No engine, tool or bot imports this at run time, so it is in no deployed snapshot.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple, Union

REPO = Path(__file__).resolve().parents[1]
MPC = REPO / "indicators" / "engines" / "mpc_jarvis.pine"

Value = Union[int, float, bool]
_LITERAL = re.compile(r"^(-?\d+(?:\.\d+)?|true|false)$")


def _literal(token: str) -> Value:
    if token == "true":
        return True
    if token == "false":
        return False
    return float(token) if "." in token else int(token)


def _resolve(expr: str, source: Path) -> Value:
    """A literal, the default of an `input.*(...)` call, or a name to look up in the same file."""
    expr = expr.strip()
    if _LITERAL.match(expr):
        return _literal(expr)
    call = re.match(r"^input\.(?:int|float|bool)\(\s*([^,)]+)", expr)
    if call:
        return _resolve(call.group(1), source)
    if re.match(r"^[A-Za-z_]\w*$", expr):
        value = pine_value(expr, source)
        if isinstance(value, tuple):
            raise ValueError(f"{source.name}: {expr!r} is itself a timeframe split")
        return value
    raise ValueError(f"{source.name}: cannot read {expr!r} as a value")


def pine_value(name: str, source: Path = MPC) -> Union[Value, Tuple[Value, Value]]:
    """What `name` is declared as in `source` — see the module docstring for the three shapes."""
    text = source.read_text(encoding="utf-8")
    declaration = re.compile(
        r"^\s*(?:var\s+|const\s+)?(?:int|float|bool|string)?\s*"
        + re.escape(name)
        + r"\s*=(?!=)\s*(.+?)\s*(?://.*)?$",
        re.M,
    )
    found = [m.group(1) for m in declaration.finditer(text)]
    if len(found) != 1:
        raise ValueError(
            f"{source.name}: {len(found)} declarations of {name!r}, expected exactly one"
        )
    split = re.match(r"^[^?]+\?\s*([^:]+?)\s*:\s*(.+)$", found[0])
    if split:
        return (_resolve(split.group(1), source), _resolve(split.group(2), source))
    return _resolve(found[0], source)
