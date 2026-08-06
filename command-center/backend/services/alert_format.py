"""alert_format.py — the house shape for this app's Telegram messages.

⚠ **A deliberate MIRROR of `algos/shared/alert_format.py`.** `command-center/` and `algos/` are
independent by repo rule: they may share a data FILE and may not import each other's code. So the
shape is implemented twice and pinned by `tests/test_alert_format.py`, which reads the other file
and compares the contract string rather than trusting a comment.

The shape, and the reasoning that produced it, live in that file's docstring. The short version:

    <icon> <LABEL> · <subject>
    <the facts, grouped>
    <what to do about it>

* the LABEL is the whole message in two words — it is what a lock screen shows;
* a message ends with the consequence, and "nothing to do" counts as one;
* no timestamp: Telegram already prints the send time in the reader's own local clock;
* plain text, never Markdown — a lone underscore in `mpc_sos_fade` makes Telegram reject the
  whole message.
"""

from __future__ import annotations

from typing import Iterable, Optional

__all__ = ["alert", "joined", "SPEC"]

#: Must match `algos/shared/alert_format.SPEC` exactly. The test compares them.
SPEC = "<icon> <LABEL> · <subject>\\n<facts>\\n<what to do>"


def alert(icon: str, label: str, subject: str = "", *lines: str) -> str:
    """One message, in the house shape. Empty lines are dropped rather than rendered blank, so a
    caller may pass a value it might not have without branching."""
    head = f"{icon} {label}"
    if subject:
        head = f"{head} · {subject}"
    body = [str(x).strip() for x in lines if x is not None and str(x).strip()]
    return "\n".join([head, *body])


def joined(parts: Iterable[Optional[str]], sep: str = " · ") -> str:
    """Facts that belong on one line, with the missing ones simply absent."""
    return sep.join([str(p) for p in parts if p is not None and str(p).strip()])
