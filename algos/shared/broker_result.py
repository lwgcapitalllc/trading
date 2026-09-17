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


# ── Which broker rejections are worth sending again ──────────────────────────────────────────
#
# 🔴 **From MetaTrader 5's own list of trade server return codes** (MQL5 reference → Constants →
# Codes of Errors and Warnings → Trade Server Return Codes), not guessed. Added 2026-09-16 after
# `sos_fade_demo`'s limit came back 10031 "Request rejected due to absence of network
# connection" and waited a whole 15-minute bar to be placed again.
#
# TRANSIENT — the order was refused because of the moment, not because of the order:
#   10004 REQUOTE            requote
#   10020 PRICE_CHANGED      prices changed
#   10021 PRICE_OFF          there are no quotes to process the request
#   10024 TOO_MANY_REQUESTS  too frequent requests
#   10028 LOCKED             request locked for processing
#   10031 CONNECTION         no connection with the trade server
#
# ⚠ **Deliberately NOT here:** 10012 TIMEOUT — the outcome is UNKNOWN, and the placement code
# reconciles it against the order book rather than sending again (the 2026-08-25 five-positions
# incident). 10006 REJECT and 10011 ERROR — unspecific, so a retry is a guess. Everything about
# the order itself (10014 invalid volume, 10015 invalid price, 10016 invalid stops, 10019 no
# money, 10017 trade disabled, 10018 market closed, 10027 AutoTrading off, 10030 filling mode,
# 10033/10034/10040 limits reached, ...) is PERMANENT: the same order gets the same answer.
RETCODE_REQUOTE = 10004
RETCODE_PRICE_CHANGED = 10020
RETCODE_PRICE_OFF = 10021
RETCODE_TOO_MANY_REQUESTS = 10024
RETCODE_LOCKED = 10028
RETCODE_CONNECTION = 10031

TRANSIENT_RETCODES = frozenset(
    {
        RETCODE_REQUOTE,
        RETCODE_PRICE_CHANGED,
        RETCODE_PRICE_OFF,
        RETCODE_TOO_MANY_REQUESTS,
        RETCODE_LOCKED,
        RETCODE_CONNECTION,
    }
)


def is_transient(retcode) -> bool:
    """True only for a KNOWN temporary rejection. No retcode at all (no reply) is not one."""
    return retcode in TRANSIENT_RETCODES
