#!/usr/bin/env python3
"""Proves the trading-box server refuses what it must, and never lies about what it knows.

Three properties, and the second is the one that would cost money if it broke:

  1. The dangerous operations are ABSENT from the menu, not merely discouraged.
  2. A guarded operation refuses WITHOUT TOUCHING THE NETWORK. A refusal that had already
     fired the request would be theatre, and nothing about the returned text would show it.
  3. When the Command Center cannot be reached, every tool says so and returns NO payload.
     Never let "no" and "cannot ask" be the same value -- a dead terminal once read as a
     quiet market and a bot sat blind for 50 minutes with every dashboard green.

WATCHED RED by mutation, 2026-08-21:
  * dropping the confirm check in `tool_request_stop` reddens exactly the 6 no-confirm and
    wrong-confirm cases, and the "a refusal makes no network call" assertion fires first;
  * making `_cannot_ask` return `{"running": False}` reddens exactly the 4 cannot-ask cases;
  * adding a "kill" entry to TOOLS reddens exactly the absent-by-construction case.

Run: python3 .claude/mcp/check_tradingbox.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tradingbox_server as tb  # noqa: E402 - path must be set first, repo-wide convention

failures = []


def check(label, cond, detail=""):
    if not cond:
        failures.append(f"{label}{(' - ' + detail) if detail else ''}")


class Tripwire:
    """Stands in for the network. Any call at all is a failure for the refusal tests."""

    def __init__(self):
        self.calls = []

    def __call__(self, path, method="GET", timeout=None, body=None):
        self.calls.append((method, path))
        return {"never": "should reach here"}, None


# ── 1. the dangerous forms are absent, not discouraged ───────────────────────
names = {t["name"] for t in tb.TOOLS}
banned = {
    "kill",
    "kill_bot",
    "taskkill",
    "fleet_stop",
    "stop_all",
    "restart",
    "restart_bot",
    "delete_lock",
    "clear_lock",
    "set_account",
    "set_password",
    "add_user",
    "remove_user",
    "start_agent",
    "start_bot",
    "run_task",
}
check(
    "no dangerous tool is on the menu",
    not (names & banned),
    f"found {sorted(names & banned)}",
)
check("the menu is the 7 intended tools", len(tb.TOOLS) == 7, f"got {len(tb.TOOLS)}")
for t in tb.TOOLS:
    check(f"{t['name']} has a schema", isinstance(t.get("inputSchema"), dict))
    check(f"{t['name']} has a description", bool(t.get("description")))

# ── 2. guarded operations refuse, and refuse BEFORE the network ──────────────
GUARDED = [
    ("request_stop", "stop mpc_sos_fade_demo"),
    ("promote", "promote mpc_sos_fade_demo"),
]
BAD_CONFIRMS = [
    None,  # omitted entirely
    "",  # empty
    "yes",  # something else
    "stop",  # the verb alone
    "stop mpc_bleg_demo",  # right verb, WRONG BOT
    "STOP MPC_SOS_FADE_DEMO",  # case must match
]
for name, good in GUARDED:
    for bad in BAD_CONFIRMS:
        wire = Tripwire()
        real, tb._api = tb._api, wire
        try:
            args = {"bot": "mpc_sos_fade_demo"}
            if bad is not None:
                args["confirm"] = bad
            out = tb.call_tool(name, args)
        finally:
            tb._api = real
        check(f"{name} refuses confirm={bad!r}", out.get("refused") is True, str(out)[:120])
        check(f"{name} says it did not ask, confirm={bad!r}", out.get("asked") is False)
        check(
            f"{name} makes NO network call when refusing, confirm={bad!r}",
            wire.calls == [],
            f"called {wire.calls}",
        )

    # the right phrase must actually get through, or the guard is just an off switch
    wire = Tripwire()
    real, tb._api = tb._api, wire
    try:
        tb.call_tool(name, {"bot": "mpc_sos_fade_demo", "confirm": good})
    finally:
        tb._api = real
    check(f"{name} proceeds on the exact phrase", len(wire.calls) == 1, f"calls={wire.calls}")
    check(
        f"{name} uses POST",
        wire.calls and wire.calls[0][0] == "POST",
        f"calls={wire.calls}",
    )


# ── 3. unreachable app: "cannot ask", never a falsy answer ───────────────────
def dead(path, method="GET", timeout=None, body=None):
    return None, tb._cannot_ask("the Command Center is not answering (test)")


LIES = ("running", "alive", "connected", "ok", "healthy", "status")
for name, args in [
    ("box_status", {}),
    ("bot_version", {"bot": "mpc_sos_fade_demo"}),
    ("bot_log", {"bot": "mpc_sos_fade_demo"}),
    ("promote_preview", {"bot": "mpc_sos_fade_demo"}),
]:
    real, tb._api = tb._api, dead
    try:
        out = tb.call_tool(name, args)
    finally:
        tb._api = real
    check(f"{name} reports cannot-ask", out.get("asked") is False, str(out)[:140])
    check(f"{name} gives a reason", bool(out.get("reason")))
    check(
        f"{name} invents no answer while unreachable",
        not (set(out) & set(LIES)),
        f"leaked {sorted(set(out) & set(LIES))}",
    )

# ── 4. a missing ledger day is not a quiet day ───────────────────────────────
out = tb.call_tool("bot_decisions", {"bot": "mpc_sos_fade_demo", "date": "1999-01-01"})
check("a missing ledger day reports cannot-ask", out.get("asked") is False, str(out)[:140])
check("a missing ledger day reports no records count", "records" not in out)

# ── 5. the watchdog word is explained, never passed through bare ─────────────
check(
    "an armed watchdog is not reported as simply stopped",
    "armed" in tb._WATCHDOG_MEANING["STOPPED"],
)
check(
    "a switched-off watchdog is called out",
    "SWITCHED OFF" in tb._WATCHDOG_MEANING["DISABLED"],
)

# ── 6. an unknown tool, and a crashing tool, both read as cannot-ask ─────────
out = tb.call_tool("no_such_tool", {})
check("an unknown tool reads as cannot-ask", out.get("asked") is False)
out = tb.call_tool("bot_version", {})  # missing required arg
check("a missing argument reads as cannot-ask", out.get("asked") is False, str(out)[:120])

if failures:
    print(f"\n{len(failures)} trading-box check(s) FAILED:\n")
    for f in failures:
        print("  FAIL  " + f)
    sys.exit(1)
print("trading box OK - menu, refusals, cannot-ask and ledger absence all checked")
