#!/usr/bin/env python3
"""A fixed menu of trading-box operations, exposed to Claude over MCP.

WHY THIS EXISTS
---------------
Every VPS interaction used to be a Windows command inside a quoted string inside an SSH
command. Three problems, and the third is the one that costs money:

  1. The quoting is where the mistakes live.
  2. It returns Windows console text, which is expensive to read and easy to misread.
  3. NOTHING STOPS THE WRONG COMMAND BEING TYPED. `taskkill /f /im python.exe` killed the
     live bot for three days. It is forbidden by a rule in a document, which is a rule that
     lives in somebody's memory.

This server replaces the open-ended shell with a menu. The destructive forms are not on it,
so they cannot be reached by accident, a typo, or a confused agent. Same idea as
`browser_guard.js`: move the refusal out of memory and into something that cannot be talked
out of it.

WHAT IT IS NOT
--------------
Not a second implementation of anything. Every live fact comes from the Command Center
backend, which already owns the SSH, the MT5 reads and the promote logic. This is a thin,
typed front door onto it. The one thing read locally is the committed decision ledger,
because that is a file in this repo and no service is involved.

⚠ THAT MEANS THE APP MUST BE RUNNING. When it is not, every tool says so in those words and
returns no answer at all -- see the rule below.

THE RULE THIS FILE IS BUILT AROUND
----------------------------------
🔴 Never let "no" and "cannot ask" be the same value. A dead terminal once read as a quiet
market and a bot sat blind for 50 minutes with every dashboard green. So every reply here
carries `asked`: false means the question never reached the box, and the payload is absent
rather than empty. A caller cannot mistake silence for an answer.

WHAT IS DELIBERATELY ABSENT
---------------------------
No hard kill. No fleet kill. No lock deletion. No broker-account edit, no password change,
no Telegram user management, no agent start, no restart. Some of those exist in the app's
own API and are reachable in its UI by a person who meant it. None of them are reachable
from here, and adding one is a decision somebody has to make on purpose.

Run `python3 .claude/mcp/check_tradingbox.py` to prove the refusals still hold.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

SERVER_NAME = "tradingbox"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

# The Command Center backend. Overridable so a second machine on a different port is a config
# change rather than an edit.
BASE_URL = os.environ.get("LWG_COMMAND_CENTER_URL", "http://localhost:8000").rstrip("/")

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_ROOT = REPO_ROOT / "algos" / "ledger_archive"

# A slow SSH hop sits behind most of these. The app's own timeouts are longer than a snappy
# HTTP call would justify, and a timeout that fires early turns a working box into a scary
# "cannot ask".
TIMEOUT_FAST = 30
TIMEOUT_SLOW = 120


# ─────────────────────────────────────────────────────────────────────────────
# Talking to the app
# ─────────────────────────────────────────────────────────────────────────────


def _cannot_ask(reason: str, **extra):
    """The only shape a failed question may take. `asked: false` and NO payload.

    Returning `{"running": false}` when the app is down would be a lie in the most expensive
    direction available: it reads as "the bot is stopped".
    """
    out = {"asked": False, "reason": reason}
    out.update(extra)
    return out


def _api(path: str, method: str = "GET", timeout: int = TIMEOUT_FAST, body=None):
    """Call the Command Center. Returns (payload, None) or (None, cannot_ask_dict)."""
    url = f"{BASE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        return None, _cannot_ask(
            f"the Command Center answered HTTP {e.code} for {path}",
            detail=detail,
        )
    except urllib.error.URLError as e:
        return None, _cannot_ask(
            f"the Command Center is not answering at {BASE_URL} ({e.reason}). "
            "Start it with ./go from the repo root, then ask again. "
            "This is NOT a statement about the bot -- the question never left this machine.",
        )
    except Exception as e:  # noqa: BLE001 - any failure here is still "cannot ask"
        return None, _cannot_ask(f"could not reach the Command Center: {e}")
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return raw, None


# ─────────────────────────────────────────────────────────────────────────────
# Translating what the app says into what it MEANS
# ─────────────────────────────────────────────────────────────────────────────

# 🔴 The app collapses two different schtasks states into one word. `schtasks` reports
# "Ready" for a task that is enabled and armed -- the normal state of a once-a-minute
# watchdog for 59 seconds out of every 60 -- and the snapshot maps it to "STOPPED".
# MEASURED 2026-08-21: SYS_DEADMAN read STOPPED on the page while the box reported
# `Status: Ready, Scheduled Task State: Enabled, Last Result: 0`.
# Reporting that word onward unexplained would tell a reader their dead-man switch is off.
_WATCHDOG_MEANING = {
    "RUNNING": "executing right now",
    "ARMED": "enabled and waiting for its next trigger - the healthy state",
    "DISABLED": "SWITCHED OFF - somebody disabled it; this is the one that needs attention",
    "STOPPED": (
        "an unrecognised schtasks state - not armed, not running, not disabled. Worth "
        "looking at, and impossible to see before 2026-08-21 because a healthy armed task "
        "reported the same word."
    ),
    "UNKNOWN": "the app could not read the task list",
}


def _iso_age(ts: str):
    """Seconds since an ISO timestamp, or None. A stale answer is a different thing from no
    answer, and only a timestamp separates them."""
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - t).total_seconds())
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


def tool_box_status(_args):
    """Bots, watchdogs and terminals in one answer, each labelled with what it is about."""
    snap, err = _api("/bots/snapshot", timeout=TIMEOUT_SLOW)
    if err:
        return err
    health, herr = _api("/system/health", timeout=TIMEOUT_SLOW)

    bots = []
    for b in snap.get("bots", []):
        bots.append(
            {
                "bot": b.get("key"),
                "running": b.get("status") == "RUNNING",
                "status_word": b.get("status"),
                # This account is the BOT's, read from the record the bot itself writes.
                "bot_account": b.get("account") or None,
                "account_type": b.get("account_type"),
                "balance": b.get("balance"),
                # Three-way on purpose: the bot may never have said.
                "mt5_link": b.get("mt5_link"),
                "uptime_seconds": b.get("uptime_seconds"),
                "day_locked": b.get("day_locked"),
                "lock_reason": b.get("lock_reason"),
                "state_age_seconds": _iso_age(b.get("last_updated")),
            }
        )

    watchdogs = [
        {
            "job": j.get("name"),
            "schedule": j.get("schedule"),
            "reported": j.get("status"),
            "meaning": _WATCHDOG_MEANING.get(j.get("status"), "unrecognised status"),
        }
        for j in snap.get("scheduled_jobs", [])
    ]

    # 🔴 Two different MT5 terminals live on that box and the app's health payload names
    # neither. Its `mt5_account` is the DATA terminal the backtest agent drives -- not the
    # live bot's. Reading one as the other is how you conclude the live bot moved accounts.
    if herr:
        terminals = herr
    else:
        terminals = {
            "data_terminal": {
                "what_it_is": (
                    "the terminal the backtest data agent is attached to. NOT the live bot's "
                    "terminal, and a different login here is normal."
                ),
                "account": health.get("mt5_account"),
                "server": health.get("mt5_server"),
                "connected": health.get("mt5_connected"),
            },
            "note": (
                "each bot's own account is in the bots list above, from the record that bot "
                "writes itself."
            ),
            "ssh_tunnel": health.get("ssh_tunnel"),
            "vps_reachable": health.get("vps_reachable"),
            "checked_age_seconds": _iso_age(health.get("checked_at")),
        }

    return {
        "asked": True,
        "bots": bots,
        "watchdogs": watchdogs,
        "terminals": terminals,
        "telegram": (snap.get("telegram") or {}).get("status"),
        "fetched_at": snap.get("fetched_at"),
    }


def tool_bot_version(args):
    """Which frozen snapshot a bot is actually running. A pull cannot move this; only a
    promote can, so this is the only honest answer to 'what code is live'."""
    bot = args["bot"]
    v, err = _api(f"/bots/{bot}/version", timeout=TIMEOUT_SLOW)
    if err:
        return err
    params = v.get("params") or {}
    return {
        "asked": True,
        "bot": bot,
        "frozen": v.get("frozen"),
        "content_hash": v.get("hash"),
        "built_from_commit": v.get("commit"),
        "promoted_at": v.get("promoted_at"),
        "strategy_package": v.get("strategy_package"),
        "strategy_version": v.get("strategy_version"),
        "file_count": v.get("files"),
        "param_count": len(params),
        "params": params,
    }


def tool_bot_log(args):
    """The tail of a bot's own log."""
    bot = args["bot"]
    lines = int(args.get("lines", 60))
    lines = max(1, min(lines, 500))
    out, err = _api(f"/bots/{bot}/log?lines={lines}", timeout=TIMEOUT_SLOW)
    if err:
        return err
    text = out if isinstance(out, str) else json.dumps(out)
    got = text.splitlines()
    return {
        "asked": True,
        "bot": bot,
        "lines_requested": lines,
        # Rule 3: report what came back, never what was asked for.
        "lines_returned": len(got),
        "log": "\n".join(got[-lines:]),
    }


def tool_bot_decisions(args):
    """What a bot decided on one day, from the committed ledger.

    Read from disk, not from the box: `algos/tools/ledger_sync.py` commits this record twice a
    day and it is the only copy of what the bot decided, including every setup it REFUSED. No
    broker statement contains that.
    """
    bot = args["bot"]
    day = args.get("date") or date.today().isoformat()
    path = LEDGER_ROOT / bot / "ledger" / f"decisions-{day}.jsonl"
    if not path.exists():
        # Not "no decisions" -- the file is absent, which is a different fact and usually
        # means the sync has not run yet or the bot did not run that day.
        available = []
        d = LEDGER_ROOT / bot / "ledger"
        if d.is_dir():
            available = sorted(p.name[10:-6] for p in d.glob("decisions-*.jsonl"))[-7:]
        return _cannot_ask(
            f"no ledger file on disk for {bot} on {day}. The sync may not have run yet.",
            path=str(path.relative_to(REPO_ROOT)),
            most_recent_days_available=available,
        )

    kinds, entries, refusals, errors = {}, [], [], 0
    total = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            errors += 1
            continue
        k = rec.get("kind", "?")
        kinds[k] = kinds.get(k, 0) + 1
        if k in ("entry", "fill", "exit", "order"):
            entries.append(rec)
        elif k in ("refused", "refusal", "blocked", "veto"):
            refusals.append(rec)

    return {
        "asked": True,
        "bot": bot,
        "date": day,
        "records": total,
        "unparsable_lines": errors,
        "kind_counts": kinds,
        "trade_events": entries[:40],
        "refusals": refusals[:40],
        "note": (
            "'bar' records are the routine per-bar snapshot. A day of only 'bar' records means "
            "the bot ran and took nothing, which is the intended behaviour most days."
        ),
    }


def tool_promote_preview(args):
    """What a promote WOULD change. Changes nothing itself."""
    bot = args["bot"]
    out, err = _api(f"/bots/{bot}/promote/preview", method="POST", timeout=TIMEOUT_SLOW)
    if err:
        return err
    return {"asked": True, "bot": bot, "preview": out}


# ── the two that can change something ────────────────────────────────────────
#
# Both take a confirmation phrase that names the bot and the action. ⚠ Say plainly what that
# is worth: it is a SPEED BUMP against a slip, not a wall against intent -- the same honesty
# the browser guard is documented with. Its value is that neither can happen as a side effect
# of a tool call that looked like a read.


def _confirm_ok(args, want: str):
    return str(args.get("confirm", "")).strip() == want


def tool_request_stop(args):
    """Ask a bot to stop, the graceful way.

    The app writes `stop.request`, waits for the process to go, and escalates only for a bot
    that ignored it. That ordering is the point: a hard kill denies the bot its shutdown
    record, and the next startup then reports "the previous run ended without shutting down"
    -- the silent-death detector, firing on a stop somebody performed deliberately.
    """
    bot = args["bot"]
    want = f"stop {bot}"
    if not _confirm_ok(args, want):
        return {
            "asked": False,
            "refused": True,
            "reason": (
                f"this stops a bot that may be live. Re-call with confirm exactly '{want}' "
                "once the person you are working with has said to."
            ),
        }
    out, err = _api(f"/bots/{bot}/stop", method="POST", timeout=TIMEOUT_SLOW)
    if err:
        return err
    return {
        "asked": True,
        "bot": bot,
        "result": out,
        "next": (
            "confirm it actually went before saying it stopped -- call box_status again. "
            "It will not come back on its own."
        ),
    }


def tool_promote(args):
    """Move a bot onto the current code. The only thing that changes what a bot trades."""
    bot = args["bot"]
    want = f"promote {bot}"
    if not _confirm_ok(args, want):
        return {
            "asked": False,
            "refused": True,
            "reason": (
                f"this changes what a bot trades. Run promote_preview first, then re-call "
                f"with confirm exactly '{want}' once the person you are working with has said to."
            ),
        }
    out, err = _api(f"/bots/{bot}/promote", method="POST", timeout=TIMEOUT_SLOW)
    if err:
        return err
    return {
        "asked": True,
        "bot": bot,
        "result": out,
        "next": "check bot_version to confirm which snapshot is now live.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

_BOT_ARG = {
    "type": "string",
    "description": "The bot's key, e.g. mpc_sos_fade_demo. Never its display name.",
}

TOOLS = [
    {
        "name": "box_status",
        "description": (
            "Are the bots alive, on which account, with what balance, and are the watchdogs "
            "armed. One call. Says 'cannot ask' rather than guessing when the Command Center "
            "is not running."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "fn": tool_box_status,
    },
    {
        "name": "bot_version",
        "description": (
            "Which frozen code snapshot a bot is actually running, and every parameter it "
            "carries. A git pull cannot move this - only a promote can."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"bot": _BOT_ARG},
            "required": ["bot"],
            "additionalProperties": False,
        },
        "fn": tool_bot_version,
    },
    {
        "name": "bot_log",
        "description": "The tail of a bot's own log file on the trading box.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bot": _BOT_ARG,
                "lines": {"type": "integer", "description": "1-500, default 60."},
            },
            "required": ["bot"],
            "additionalProperties": False,
        },
        "fn": tool_bot_log,
    },
    {
        "name": "bot_decisions",
        "description": (
            "What a bot decided on a given day, from the committed ledger - including the "
            "setups it refused, which no broker statement contains. Defaults to today."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bot": _BOT_ARG,
                "date": {"type": "string", "description": "YYYY-MM-DD. Defaults to today."},
            },
            "required": ["bot"],
            "additionalProperties": False,
        },
        "fn": tool_bot_decisions,
    },
    {
        "name": "promote_preview",
        "description": "What promoting a bot WOULD change. Changes nothing.",
        "inputSchema": {
            "type": "object",
            "properties": {"bot": _BOT_ARG},
            "required": ["bot"],
            "additionalProperties": False,
        },
        "fn": tool_promote_preview,
    },
    {
        "name": "request_stop",
        "description": (
            "Ask a bot to stop gracefully. REFUSES unless confirm is exactly 'stop <bot>'. "
            "Only ask for this when the person you are working with has said to."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bot": _BOT_ARG,
                "confirm": {"type": "string", "description": "Must be exactly 'stop <bot>'."},
            },
            "required": ["bot"],
            "additionalProperties": False,
        },
        "fn": tool_request_stop,
    },
    {
        "name": "promote",
        "description": (
            "Move a bot onto the current code - the only thing that changes what it trades. "
            "REFUSES unless confirm is exactly 'promote <bot>'. Run promote_preview first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bot": _BOT_ARG,
                "confirm": {"type": "string", "description": "Must be exactly 'promote <bot>'."},
            },
            "required": ["bot"],
            "additionalProperties": False,
        },
        "fn": tool_promote,
    },
]

_BY_NAME = {t["name"]: t for t in TOOLS}


def call_tool(name: str, args: dict):
    """Dispatch. Kept importable so the check script drives the real path."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return {"asked": False, "reason": f"no such tool: {name}"}
    try:
        return tool["fn"](args or {})
    except KeyError as e:
        return {"asked": False, "reason": f"missing required argument: {e}"}
    except Exception as e:  # noqa: BLE001 - a crash must still read as "cannot ask"
        return {"asked": False, "reason": f"the tool failed: {type(e).__name__}: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# The MCP wire, over stdio
# ─────────────────────────────────────────────────────────────────────────────
#
# Hand-rolled on the standard library on purpose. The official SDK needs Python 3.10 and every
# interpreter in this repo is 3.9.6, so using it would mean a new runtime before a new tool.
# The protocol surface actually needed is four messages.


def _write(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _result(mid, result):
    _write({"jsonrpc": "2.0", "id": mid, "result": result})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method, mid = msg.get("method"), msg.get("id")

        if method == "initialize":
            _result(
                mid,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        elif method == "tools/list":
            _result(
                mid,
                {
                    "tools": [
                        {k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS
                    ]
                },
            )
        elif method == "tools/call":
            p = msg.get("params") or {}
            out = call_tool(p.get("name", ""), p.get("arguments") or {})
            _result(
                mid,
                {
                    "content": [{"type": "text", "text": json.dumps(out, indent=2, default=str)}],
                    # A refusal or a cannot-ask is a real answer, not a transport error, so it
                    # is not flagged isError -- the caller must read the payload either way.
                    "isError": False,
                },
            )
        elif method == "ping":
            _result(mid, {})
        elif mid is not None:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
        # notifications (no id) need no reply


if __name__ == "__main__":
    main()
