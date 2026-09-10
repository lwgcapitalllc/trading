"""scan_terminals.py — ask every MT5 terminal on this box WHO IT IS LOGGED INTO.

    python algos/tools/scan_terminals.py            # JSON for every terminal, for the app
    python algos/tools/scan_terminals.py --pretty   # the same, readable, for a human
    python algos/tools/scan_terminals.py --probe "C:\\MT5_Scalper\\terminal64.exe"

**Why this exists.** The Command Center's account list is entirely HAND-TYPED and nothing ever
checks it against this machine. On 2026-09-10 that list claimed a terminal for account 700107749
that is not logged into it, and a third terminal had been logged into a different account for a
day with no part of the system able to see it. **A stored claim nobody checks is this repo's
oldest and most expensive shape**, and an account is the worst place to keep one: it decides
whose balance a bot sizes against.

**It reads. It never writes, never logs in, and never launches a terminal.**

  * `mt5.login()` is not called and must never be added here. It CHANGES what a terminal is
    logged into, so one stray call re-points a terminal under a running bot. `mt5_ops.connect`
    owns that, and it owns it because a bot is entitled to move its own terminal. A scanner is
    not. There is a test that greps this file for the call.
  * `mt5.initialize(path=...)` LAUNCHES the terminal at that path when it is not already up.
    So this only ever probes terminals it has first seen RUNNING in the process list. A terminal
    that is down is reported as down.
  * A terminal a BOT owns is never probed at all — see `--skip-owned`. Attaching to the live
    bots' terminal to satisfy a report is not a trade this tool is entitled to make.

🔴 **The three states are kept apart and must not collapse into two** (the rule this repo keeps
paying for). For every terminal, exactly one of:

  * probed          — `account` is what the broker itself answered
  * not running     — no process, so the question COULD NOT BE ASKED
  * owned by a bot  — deliberately not asked; the bot is the one that reports this account

`account: null` therefore never means "no account". It means nobody asked, and the reason is in
the same record. A consumer that reads a null here as an empty terminal is reading a coin flip.

⚠ **`kind` comes from the broker's own answer, never from the server name.** MT5 reports a
demo/real/contest flag per account; "PUPrime-Demo" happens to contain the word demo and
"ICMarkets-Live02" happens to contain live, and neither is a fact about the account. The
dangerous direction here is unmistakable: guessing demo for an account that is real is how a
bot gets pointed at somebody's money.

⚠ **The symbol suffix is MEASURED off the terminal's own instrument list, not guessed.** A broker
quotes `XAUUSD`, `XAUUSD.p`, `XAUUSD.s` or `XAUUSDm` and only that terminal knows which.

🔴 **It is the suffix COMMON TO EVERY probe instrument, and the first version — "each base must
resolve to exactly one variant" — could never have answered on a real broker.** PU Prime offers
`XAUUSD.crp`, `XAUUSD.p` and `XAUUSD247`, and `EURUSD` alongside `EURUSD.p`; every base is
ambiguous on its own, so that rule abstained on all four and reported nothing measurable. It
was not wrong in the dangerous direction, but **a check that always refuses is decoration**, and
it would have shipped looking careful. The variants each base offers are intersected instead:
gold rules out bare, the majors rule out the gold-only tags, and `.p` is what survives.

⚠ **Refusing is still the answer when the intersection is empty OR larger than one.** A broker
quoting every instrument both bare and suffixed leaves a genuine CHOICE, and this tool does not
make choices about which instrument a bot trades — it names the candidates and stops. Rebasing a
live symbol onto a guessed suffix is a wrong-symbol order, not a cosmetic error.

⚠ **Each terminal is probed in its OWN SUBPROCESS.** The MT5 python binding attaches a PROCESS to
one terminal, and `shutdown()` then `initialize()` against a second is documented as unreliable
and was not going to be trusted with an account number. The parent enumerates and re-invokes
itself once per terminal with `--probe`, so a probe that hangs, crashes or takes the interpreter
down with it costs exactly one terminal's answer and the rest of the scan still reports.

⚠ **Output is ASCII only.** The console on this box is cp1252 and one non-ASCII character raises
mid-print, which turns a completed scan into an exit 1 with a traceback — that has already cost
`broker_facts.py` a full run.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

REPO = Path(__file__).resolve().parent.parent.parent
INSTANCES = REPO / "algos" / "markets" / "fx" / "instances"

# One probe gets this long before the parent gives up on it and records that it could not ask.
# A terminal mid-reconnect can block `initialize` indefinitely, and a scan that hangs forever is
# a scan whose caller times out with NO answer for any terminal rather than one.
PROBE_TIMEOUT_S = 45

# How recent a bot's heartbeat must be for the account it reports to count as CURRENT. It must equal
# `notifications/deadman.py::HEARTBEAT_STALE_SECS` — the floor both watchdogs use for "stalled" —
# and `test_scan_terminals.py` fails if the two ever differ, because a third opinion on how old is
# too old is how two monitors come to disagree about the same bot.
HEARTBEAT_FRESH_S = 5 * 60

# The bases used to measure the suffix. They must agree. Gold is first because it is what this
# repo trades; the majors are there so a metals-only naming quirk cannot decide it alone.
_SUFFIX_BASES = ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY")

# MT5's own account flag. 0 = demo, 1 = contest, 2 = real. Anything else is unrecognised and is
# reported as unrecognised rather than folded into the nearest neighbour.
_TRADE_MODE = {0: "demo", 1: "contest", 2: "live"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------------
# Enumerating what is on the box
# --------------------------------------------------------------------------------------------


def running_terminals() -> list[dict]:
    """Every `terminal64.exe` currently running, with its install path and pid.

    This is the ONLY list that may be probed. `wmic` is used because it is what the rest of this
    repo already reaches for on this box, so there is one thing to replace when it finally goes.
    """
    out = subprocess.run(
        [
            "wmic",
            "process",
            "where",
            "name='terminal64.exe'",
            "get",
            "executablepath,processid",
        ],
        capture_output=True,
        timeout=30,
    )
    text = out.stdout.decode("cp1252", errors="replace")
    found = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("executablepath"):
            continue
        m = re.match(r"^(.*terminal64\.exe)\s+(\d+)\s*$", line, re.IGNORECASE)
        if not m:
            continue
        found.append({"exe": m.group(1).strip(), "pid": int(m.group(2))})
    return found


def installed_terminals() -> list[str]:
    """Every install this box has a data folder for, running or not.

    Each terminal's data folder names the install it belongs to in `origin.txt`, so the tree
    under `%APPDATA%\\MetaQuotes\\Terminal` is a self-describing index of installs. It is read
    rather than guessed from a `C:\\MT5_*` glob because two of the installs on this box live
    under Program Files and a glob would silently miss them.

    Reading this file cannot start a terminal, which is the whole reason the down ones can be
    listed at all.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    root = Path(appdata) / "MetaQuotes" / "Terminal"
    if not root.is_dir():
        return []
    installs = []
    for child in root.iterdir():
        origin = child / "origin.txt"
        try:
            if not origin.is_file():
                continue
            path = _decode_origin(origin.read_bytes())
        except OSError:
            continue
        if path:
            installs.append(path)
    return sorted(set(installs))


class ScanRefused(RuntimeError):
    """The scan may not run, so NOTHING was attached to.

    Always a statement about this tool's own footing, never about a terminal. A caller that
    turns it into "no accounts found" has converted a refusal into a measurement.
    """


def _decode_origin(raw: bytes) -> str:
    """The install path out of an `origin.txt`, whatever encoding the terminal wrote it in.

    🔴 **MT5 writes this file as UTF-16, and reading it as UTF-8 does not fail — it produces a
    string with a null byte between every character.** That string is not a path, so it matches
    no running terminal, so every install on the box appeared TWICE in the first real scan: once
    correctly from the process list, and once as a garbled phantom reporting itself not running.
    A phantom that says "could not be asked" is the worst possible shape for this tool, because
    that is exactly what a genuinely-down terminal says.

    ⚠ **`errors="replace"` is what hid it.** It turned an encoding fault into plausible-looking
    text and let the scan exit 0. The lesson is the repo's own: a decode that cannot fail is a
    decode whose failures you will read as data.

    ⚠ **The byte-order mark is not the test — a null inside the text is.** Keying only on the
    mark fixes exactly the file that was in front of us and leaves a mark-less UTF-16 decoding to
    the same garbage, which is the shape of fix that reads as done and is not. No real path
    contains a null, so that is the symptom worth branching on.
    """
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
        if "\x00" in text:
            # A UTF-16 file with no byte-order mark. The mark is what the terminal on this box
            # happens to write, and keying only on it means the fix holds for exactly the file
            # that was in front of us. A null INSIDE the text is the symptom itself, and it is
            # the thing worth branching on: no real path contains one.
            wide = "utf-16-le" if raw[1:2] == b"\x00" else "utf-16-be"
            text = raw.decode(wide, errors="replace")
    # A trailing null terminator survives decoding and makes the path match nothing, so it goes
    # LAST and applies to every branch above.
    return text.strip().strip("\x00").strip()


def bot_terminals() -> dict[str, list[str]]:
    """Which install each registered bot points at, keyed by lowercased install DIRECTORY.

    A bot's own instance config is the only statement of intent that exists on this box, and a
    terminal named by one is a terminal this tool does not touch.

    🔴 **A MISSING instances directory REFUSES THE WHOLE SCAN rather than answering "nobody owns
    anything".** Those two are the same value and opposite facts, and the difference is which
    terminals become eligible to attach to: an empty answer here makes every terminal on the box
    fair game, including the one two armed bots are trading through. **This tool is only safe
    while it can read the list of terminals it must not touch, so when it cannot read that list
    it does not scan.** Caught the honest way, by copying the script somewhere convenient and
    running it from outside the repo, where it cheerfully proposed to probe the live terminal.

    ⚠ **One UNREADABLE config is a different case and IS tolerated**: the directory was found, so
    every other bot's claim is still known, and the cost is a single terminal probed that need
    not have been. That is a judgement about one file, not a blind spot over the whole box.
    """
    if not INSTANCES.is_dir():
        raise ScanRefused(
            f"no instance directory at {INSTANCES}, so the terminals that bots trade through "
            f"cannot be known - refusing to scan rather than attaching to all of them"
        )
    owned: dict[str, list[str]] = {}
    for cfg in sorted(INSTANCES.glob("*/config.json")):
        try:
            raw = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        path = str(raw.get("mt5_path") or "").strip()
        if not path:
            continue
        owned.setdefault(_install_dir(path), []).append(cfg.parent.name)
    return owned


def bot_reports(now: float | None = None) -> dict[str, int | None]:
    """The account each bot's OWN heartbeat says its terminal is on, keyed by bot — or `None`.

    🔴 **This is what lets the Command Center ask the box ONCE.** It used to fetch the whole fleet
    snapshot over a second SSH call — process list, scheduled tasks, every state, review and ledger
    file — to read this one number per bot. Read here, on the box, it arrives in the same answer as
    the terminals, taken at the same moment, so a bot restarting between two trips cannot make the
    two halves of one scan describe different states.

    ⚠ **Only a FRESH heartbeat counts, and that is a rule the two-call version never had.** A
    stopped bot's state file still holds the last account it saw — yesterday's fact, readable today,
    looking exactly like a current one. So the reading is used only when the heartbeat written with
    it is younger than `HEARTBEAT_FRESH_S`; otherwise the bot "could not say".

    ⚠ **The HEARTBEAT, never `max(heartbeat, started)`**, which is the right rule for "has it
    stalled" and the wrong one here: a bot that has just restarted has a fresh `started` and a file
    still holding the PREVIOUS run's account until its first heartbeat overwrites it.

    ⚠ `None` for every failure — unreadable file, no entry, no field, stale — because each of them
    means the same thing to the reader: this bot did not say. It is never a zero and never the
    configured account (the list lives in the same repo, so that would check the list against
    itself). The file is replaced whole, never emptied and refilled (`shared/bot_state.py`), so a
    read cannot catch it half-written.
    """
    now = time.time() if now is None else now
    reports: dict[str, int | None] = {}
    if not INSTANCES.is_dir():
        return reports
    for cfg in sorted(INSTANCES.glob("*/config.json")):
        bot = cfg.parent.name
        reports[bot] = None
        try:
            state = json.loads((cfg.parent / "bot_state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entry = state.get(bot) if isinstance(state, dict) else None
        if not isinstance(entry, dict):
            continue
        beat = entry.get("heartbeat")
        seen = entry.get("observed_account")
        if not isinstance(beat, (int, float)) or now - beat > HEARTBEAT_FRESH_S:
            continue
        if isinstance(seen, int) and not isinstance(seen, bool) and seen > 0:
            reports[bot] = seen
    return reports


def _install_dir(exe_or_dir: str) -> str:
    r"""The install FOLDER for a path that may name either the folder or the exe inside it.

    Instance configs store the exe, `origin.txt` stores the folder, and the process list stores
    the exe. Comparing those raw is how a terminal a bot owns gets probed anyway, so every
    comparison in this file goes through here.

    🔴 **It uses `ntpath` rather than `pathlib`, and that is load-bearing rather than fussy.**
    These are always WINDOWS paths - the box is Windows - but this module is imported by tests
    that run on a Mac, where `pathlib` does not treat a backslash as a separator at all. There,
    `Path(r"C:\MT5_FFT\terminal64.exe").parent` is `.`, so EVERY terminal on the box collapses
    to one key and every bot appears to own the same install. `ntpath` gives Windows semantics on
    any host, so the answer does not depend on which machine is asking.

    ⚠ **The failure this avoids is the dangerous kind: silent, and green.** Collapsing the keys
    made all three bots look like owners of a single terminal, which reads as MORE terminals
    protected, not fewer - so nothing looks wrong until the one install that actually matters
    hashes to a key nobody claimed. Found by printing the mapping instead of asserting it was
    fine.
    """
    p = str(exe_or_dir or "").strip().rstrip("\\/")
    if p.lower().endswith("terminal64.exe"):
        p = ntpath.dirname(p)
    return p.lower().rstrip("\\/")


# --------------------------------------------------------------------------------------------
# Probing ONE terminal — this half runs in its own subprocess
# --------------------------------------------------------------------------------------------


def _measure_suffix(mt5) -> tuple[str | None, str]:
    """The suffix this broker puts on its instruments, or `None` when it cannot be measured.

    Returns `(suffix, how)`. `""` is a real answer meaning this broker quotes bare symbols;
    `None` means unrecorded. The two are different and the registry already treats them so.
    """
    try:
        symbols = mt5.symbols_get()
    except Exception as e:  # noqa: BLE001 - a binding fault must not lose the account we DID read
        return None, f"instrument list unavailable ({e})"
    if not symbols:
        return None, "the terminal returned no instruments"

    names = [s.name for s in symbols]
    seen: dict[str, set[str]] = {}
    for base in _SUFFIX_BASES:
        pat = re.compile(r"^" + re.escape(base) + r"([.\-_A-Za-z0-9]*)$")
        hits = {m.group(1) for m in (pat.match(n) for n in names) if m}
        if hits:
            seen[base] = hits

    if not seen:
        return None, "none of the probe instruments were found on this terminal"

    # The suffix this broker puts on EVERY probe instrument. See the docstring: one instrument's
    # variants cannot decide it, but the variant they all share can.
    common = set.intersection(*seen.values())
    found = ", ".join(
        f"{b}[{'|'.join(sorted(x or '(bare)' for x in v))}]" for b, v in sorted(seen.items())
    )
    if not common:
        return (
            None,
            f"the probe instruments share no common suffix, so nothing is recorded: {found}",
        )
    if len(common) > 1:
        offered = "|".join(sorted(x or "(bare)" for x in common))
        return None, (
            f"this broker quotes every probe instrument under more than one suffix ({offered}), "
            f"so which one to trade is a CHOICE rather than a measurement: {found}"
        )
    suffix = common.pop()
    return suffix, f"common to {','.join(sorted(seen))} on this terminal"


def probe(exe: str) -> dict:
    """Attach to an already-running terminal and report who it is logged into.

    Every failure path returns a record carrying `error` and a null account, because the caller
    must be able to tell "asked and got nothing" from "never asked" and from "no account". None
    of them raise: one unreadable terminal may not take the scan down.
    """
    record: dict = {
        "exe": exe,
        "install": _install_dir(exe),
        "probed": False,
        "account": None,
        "server": None,
        "kind": None,
        "company": None,
        "currency": None,
        "leverage": None,
        "symbol_suffix": None,
        "symbol_suffix_how": None,
        "error": None,
    }
    try:
        import MetaTrader5 as mt5  # noqa: N813 - the vendor's own casing
    except ImportError as e:
        record["error"] = f"the MetaTrader5 package is not importable here ({e})"
        return record

    try:
        if not mt5.initialize(path=exe):
            record["error"] = f"could not attach to {exe}: {mt5.last_error()}"
            return record
        try:
            info = mt5.account_info()
            if info is None:
                record["error"] = (
                    "attached, but the terminal reports no account - it is running and not "
                    "logged in"
                )
                return record
            mode = getattr(info, "trade_mode", None)
            record.update(
                probed=True,
                account=int(info.login),
                server=str(info.server),
                kind=_TRADE_MODE.get(mode),
                company=str(getattr(info, "company", "") or ""),
                currency=str(getattr(info, "currency", "") or ""),
                leverage=int(getattr(info, "leverage", 0) or 0),
            )
            if record["kind"] is None:
                record["error"] = (
                    f"the terminal reports an unrecognised account mode ({mode!r}), so whether "
                    f"this is real money is UNKNOWN"
                )
            suffix, how = _measure_suffix(mt5)
            record["symbol_suffix"] = suffix
            record["symbol_suffix_how"] = how
        finally:
            mt5.shutdown()
    except Exception as e:  # noqa: BLE001 - see the docstring; one terminal may not kill the scan
        record["error"] = f"{type(e).__name__}: {e}"
    return record


# --------------------------------------------------------------------------------------------
# The scan
# --------------------------------------------------------------------------------------------


def _run_probe_subprocess(exe: str) -> dict:
    """Probe one terminal in a fresh interpreter, so a hang or a crash costs one answer."""
    try:
        out = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--probe", exe],
            capture_output=True,
            timeout=PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {
            "exe": exe,
            "install": _install_dir(exe),
            "probed": False,
            "account": None,
            "error": f"the probe did not answer within {PROBE_TIMEOUT_S}s, so it was given up on",
        }
    text = out.stdout.decode("utf-8", errors="replace").strip()
    try:
        return json.loads(text)
    except ValueError:
        err = out.stderr.decode("utf-8", errors="replace").strip()
        return {
            "exe": exe,
            "install": _install_dir(exe),
            "probed": False,
            "account": None,
            "error": f"the probe printed nothing readable - {err or 'it said nothing at all'}",
        }


def scan(skip_owned: bool = True) -> dict:
    """Every terminal on this box and, where it could be asked, who it is logged into."""
    try:
        owned = bot_terminals()
    except ScanRefused as e:
        # `asked: False` at the top level, for the same reason every record below carries its own
        # three states: a caller must never read a refusal as an empty box.
        return {"asked": False, "scanned_at": _now(), "reason": str(e), "terminals": []}
    running = {_install_dir(t["exe"]): t for t in running_terminals()}
    reports = bot_reports()
    installed = {_install_dir(p): p for p in installed_terminals()}

    terminals = []
    for key in sorted(set(running) | set(installed) | set(owned)):
        proc = running.get(key)
        bots = sorted(owned.get(key, []))
        # `key` is what the caller JOINS on and `install` is what a person READS. They were one
        # field until the first real scan spelled the same terminal three ways in one report -
        # the exe for an owned one, a lowercased directory for a probed one, and the original
        # casing for a stopped one. The consumer of this is the Command Center matching these
        # against terminal paths typed by hand into the account list, and a join that depends on
        # which branch produced the row is a join that works until it quietly does not.
        base = {
            "key": key,
            "install": installed.get(key)
            or _install_dir(str(running.get(key, {}).get("exe", "")))
            or key,
            "exe": running.get(key, {}).get("exe"),
            "pid": proc["pid"] if proc else None,
            "running": proc is not None,
            "owned_by_bots": bots,
        }
        if proc is None:
            terminals.append(
                {
                    **base,
                    "state": "not_running",
                    "probed": False,
                    "account": None,
                    "reason": "no terminal process for this install, so it could not be asked",
                }
            )
            continue
        if bots and skip_owned:
            terminals.append(
                {
                    **base,
                    "state": "owned_by_bot",
                    # Raw per-bot readings, `None` = that bot could not say. The JUDGEMENT — do they
                    # agree, is one enough — stays in the Command Center, next to its tests.
                    "reported_by_bots": {b: reports.get(b) for b in bots},
                    "probed": False,
                    "account": None,
                    "reason": (
                        "a bot trades through this terminal, so it was deliberately not "
                        "attached to; that bot reports its own account"
                    ),
                }
            )
            continue
        # The probe reports its own idea of identity; the scan's is authoritative, so those keys
        # are dropped rather than allowed to overwrite the join key.
        found = {
            k: v
            for k, v in _run_probe_subprocess(proc["exe"]).items()
            if k not in ("key", "install", "exe")
        }
        terminals.append({**base, "state": "probed", **found})

    return {"asked": True, "scanned_at": _now(), "terminals": terminals}


def _pretty(result: dict) -> str:
    if not result.get("asked"):
        return f"SCAN REFUSED - {result.get('reason')}"
    lines = [f"scanned {result['scanned_at']}", ""]
    for t in result["terminals"]:
        head = f"  {t['install']}"
        if t["state"] == "probed" and t.get("account"):
            kind = (t.get("kind") or "UNKNOWN MODE").upper()
            lines.append(f"{head}\n      #{t['account']} on {t['server']}  [{kind}]")
            lines.append(f"      suffix {t.get('symbol_suffix')!r} - {t.get('symbol_suffix_how')}")
        else:
            lines.append(f"{head}\n      {t.get('reason') or t.get('error')}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe", metavar="EXE", help="probe ONE terminal and print its record")
    ap.add_argument("--pretty", action="store_true", help="readable output for a human")
    ap.add_argument(
        "--include-bot-terminals",
        action="store_true",
        help="also attach to terminals a bot trades through (off by default, and deliberately)",
    )
    args = ap.parse_args(argv)

    if args.probe:
        print(json.dumps(probe(args.probe)))
        return 0
    result = scan(skip_owned=not args.include_bot_terminals)
    print(_pretty(result) if args.pretty else json.dumps(result))
    # A refusal exits non-zero so a caller that only checks the exit code still notices. The
    # payload says so too, because the opposite mistake - a caller reading only the code and
    # discarding the reason - is how "could not ask" becomes "nothing there".
    return 0 if result.get("asked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
