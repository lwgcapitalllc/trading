"""
Bots router — /bots/*

Read endpoints:
  GET  /bots/snapshot                  — full VPS state via batched SSH
  GET  /bots/{bot_name}/log            — last N lines of stdout log
  GET  /bots/{bot_name}/params         — what this bot is configured with (read-only)

Runtime config:
  PATCH /bots/{bot_name}/runtime       — the levers allowed to move on a RUNNING bot
                                         (risk % only — see services/bot_params.py)

Global control actions (all bots):
  POST /bots/start                     — run SYS_STARTUP task
  POST /bots/stop                      — terminate each registered bot + delete lock
  POST /bots/restart                   — stop + 3s + start

  (There is no /bots/emergency route. This list claimed one until 2026-08-04; it was
   removed at some point and the docstring kept advertising it.)

Per-bot control actions:
  POST /bots/{bot_name}/start          — schtasks /run /tn {task_name}
  POST /bots/{bot_name}/stop           — wmic terminate by commandline match
  POST /bots/{bot_name}/restart        — per-bot stop + 3s + start
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import threading
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import config as cfg
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from models import (
    BotAccountAssign,
    BotAccountBot,
    BotAccountCapUpdate,
    BotAccountGroup,
    BotAccountPassword,
    BotAccountRegistration,
    BotAccountRegistrationWrite,
    BotDeployedVersion,
    BotParamsView,
    BotPromoteRequest,
    BotPromoteResult,
    BotRuntimeUpdate,
    BotSnapshot,
    BotStatus,
    BotVersionCompare,
    JobStatus,
    ProcessStatus,
    TelegramUser,
    TelegramUserCreate,
    TelegramUserRoleUpdate,
)
from services import bot_account_registry, bot_accounts, bot_params, bot_versions, lab_db, notify
from services.alert_format import alert, joined
from services.notify import send_telegram_id

router = APIRouter(prefix="/bots", tags=["bots"])

VPS_HOST = cfg.SSH_ALIAS

# ── The bot registry ──────────────────────────────────────────────────────────
#
# ONE record per live bot. Everything below it is DERIVED.
#
# 🔴 There were nine parallel dicts here until 2026-08-04, keyed three different ways (task
# name, bot key, state-file section), and registering a bot meant editing all nine. Missing
# one produced a confident wrong answer rather than an error, which is the shape that makes
# this expensive:
#
#   - no `_TASK_ACCT_TYPE` entry ⇒ `.get(task, "demo")` rendered a **LIVE bot as demo**,
#     defeating the live tinting, the "N of these are LIVE accounts" warning on the fleet
#     dialog, and the demo/live filter all at once.
#   - no `_SUPPRESS_KEYS` entry ⇒ "Stop all N bots" skipped that bot **and reported
#     success**, because `_stop_procs` iterated the crash-alert map rather than the bots.
#
# So the registry is a dataclass with **no default for `account_type`**: forgetting it is a
# TypeError at import, which is loud, and at the only moment when it costs nothing. The
# rest default off the bot key, because that is genuinely how `algos/live/` names things —
# but every one can be overridden for a bot that does not follow the convention.
#
# ⚠ `BOT_MPC_SOS_FADE` IS NOT A REAL SCHEDULED TASK. `task` is a task name because that is
# how the retired panel was keyed, but the live bot has no `BOT_*` task of its own: it boots
# through SYS_STARTUP → startup_coordinator.py, and the command center starts it through
# that same coordinator over WMI. `_parse_tasks` therefore never returns a status for it,
# which is harmless — the PROCESS LIST is authoritative (see `get_snapshot`).
#
# All first-attempt bots deleted 2026-06-22 (see algos/docs/BOT_DEPLOYMENT_INFRA.md);
# the suite restarted from scratch 2026-07-31 (algos/CLAUDE.md → "CLEAN SLATE").

_VPS_INSTANCES = r"C:\trading\algos\markets\fx\instances"


@dataclass
class BotReg:
    """Every fact this router needs about one registered bot.

    `key` is also the string matched against the VPS process commandline
    (`runner.py --bot mpc_sos_fade_demo`) — the script name identifies the FLEET, only the
    key identifies the bot, because every live bot IS `runner.py`.
    """

    task: str
    key: str
    display: str
    account_type: str  # "demo" | "live" — deliberately no default
    instance_dir: str = ""  # ⇒ key
    log_file: str = ""  # ⇒ <key>.log, which is what algos/live/runner.py writes
    suppress_key: str = ""  # ⇒ key; the short key written to stop_suppress.json
    config_section: str = "strategy_params"
    state_section: str = ""  # ⇒ state_<key>; bots SHARING a bot_state.json share this
    state_file: str = ""  # ⇒ <instances>\<instance_dir>\bot_state.json
    # ⇒ <instances>\<instance_dir>\review.json — the hourly log review's standing flag.
    # PER BOT even when two bots share a bot_state.json, because a review is about one bot's
    # own health record and merging two into one file would make "which bot needs attention"
    # unanswerable from the file that is supposed to answer it.
    review_file: str = ""

    def __post_init__(self):
        if self.account_type not in ("demo", "live"):
            raise ValueError(
                f"{self.key}: account_type must be 'demo' or 'live', not {self.account_type!r}"
            )
        self.instance_dir = self.instance_dir or self.key
        self.log_file = self.log_file or f"{self.key}.log"
        self.suppress_key = self.suppress_key or self.key
        self.state_section = self.state_section or f"state_{self.key}"
        self.state_file = self.state_file or rf"{_VPS_INSTANCES}\{self.instance_dir}\bot_state.json"
        self.review_file = self.review_file or rf"{_VPS_INSTANCES}\{self.instance_dir}\review.json"

    @property
    def config_path(self) -> Path:
        return (
            cfg.MONOREPO_ROOT
            / "algos"
            / "markets"
            / "fx"
            / "instances"
            / self.instance_dir
            / "config.json"
        )


_BOTS: list[BotReg] = [
    BotReg(
        task="BOT_MPC_SOS_FADE",
        key="mpc_sos_fade_demo",
        display="MPC SOS Fade",
        account_type="demo",
    ),
    # ON THE BENCH (`account: null` in its instance config), and registered here anyway — that
    # pairing is the point. Registration is what makes a bot ADDRESSABLE: it is what puts it on
    # the Accounts tab so it can be added to an account from the browser, and it is what makes
    # its version, its params and its state readable. Whether it TRADES is a different question,
    # answered by its account, and `startup_coordinator` skips a bot that has none.
    #
    # ⚠ It reads STOPPED on the Monitor tab and that is correct rather than a gap: it is not
    # running, nothing has started it, and nothing will until somebody assigns it.
    # ⚠ It is deliberately NOT in `algos/notifications/monitor.py` or `deadman.py`. Those alarm
    # on a bot that is not running, which is this bot's normal state — registering it there would
    # ring the one alarm that has to stay quiet until it means something.
    BotReg(task="BOT_MPC_BLEG", key="mpc_bleg_demo", display="MPC B-LEG", account_type="demo"),
]

# ── Derived views. Never edit one of these — add a BotReg above. ──────────────
_BOT_DISPLAY_ORDER = [b.task for b in _BOTS]
_BY_TASK: dict[str, BotReg] = {b.task: b for b in _BOTS}
_BY_KEY: dict[str, BotReg] = {b.key: b for b in _BOTS}

# ⚠ `SYS_REPORTER` and `SYS_PNLTRACKER` were removed 2026-08-05 with the scripts behind
# them (see `algos/CLAUDE.md`). They had rendered here as DISABLED jobs "waiting for a bot
# registry", which reads as a feature switched off rather than one that does nothing:
# both carried an empty registry inherited from the four bots deleted 2026-06-22.
_SYS_DISPLAY_NAMES = {
    "SYS_TELEGRAM": "Telegram",
    "SYS_MONITOR": "Monitor",
    "SYS_DEADMAN": "Dead-man switch",
    "SYS_LOGBACKUP": "Log backup",
}
_DISPLAY_NAMES = {**{b.task: b.display for b in _BOTS}, **_SYS_DISPLAY_NAMES}
_TASK_BOT_KEYS = {b.task: b.key for b in _BOTS}
_KEY_DISPLAY = {b.key: b.display for b in _BOTS}

# The jobs this page reports on. Every entry must have a task in `_SYS_TASK_BY_JOB` below
# — a name with no task resolves to a permanent UNKNOWN, which reads as a job the page
# cannot see rather than one it never asked about.
_SCHEDULED_JOBS = [
    JobStatus(name="Monitor", schedule="every 1 min", status="UNKNOWN"),
    JobStatus(name="Dead-man switch", schedule="every 5 min", status="UNKNOWN"),
    JobStatus(name="Log backup", schedule="daily 00:30", status="UNKNOWN"),
]
_SYS_TASK_BY_JOB = {v: k for k, v in _SYS_DISPLAY_NAMES.items()}

# Crash-alert suppress keys — must match telegram_bot.py / monitor.py.
_SUPPRESS_KEYS: dict[str, str] = {b.key: b.suppress_key for b in _BOTS}

# ⚠ The risk-cap block that stood here is GONE (2026-08-05), along with
# `algos/shared/thresholds.json` and `bot_state.BOT_THRESHOLDS`. Those numbers were the P&L
# tracker's daily-goal / daily-cap / weekly-cap ALERT levels, and with that job deleted
# nothing read them and nothing ever enforced them — so rendering them here put a cap on
# the page that the bot would trade straight through. **An alert is not a limit.** The live
# bot's real risk lever is `strategy_params.exec_risk_pct` in its instance config (see the
# runtime panel below); a genuine cap has to live in `algos/live/runner.py`, where it can
# refuse a trade.


# ── Per-bot config file mapping ───────────────────────────────────────────────
# Derived from the registry — bot_key → the instance config.json path and the strategy
# section name. Kept as a dict because several call sites read `["path"]` / `["section"]`.
_BOT_INSTANCE_MAP: dict[str, dict] = {
    b.key: {"path": b.config_path, "section": b.config_section} for b in _BOTS
}


def _read_instance_config(bot_key: str) -> dict:
    info = _BOT_INSTANCE_MAP.get(bot_key)
    if not info or not info["path"].exists():
        raise HTTPException(status_code=404, detail=f"Config file not found for '{bot_key}'")
    return json.loads(info["path"].read_text(encoding="utf-8"))


def _write_instance_config(bot_key: str, data: dict) -> None:
    # ensure_ascii=False: the file is written as UTF-8 and its `_`-prefixed prose keys are
    # the reasoning behind every value in it. Escaping those to — turns the one part a
    # human actually reads into noise, and this file is edited by hand far more often than
    # it is written from here.
    info = _BOT_INSTANCE_MAP[bot_key]
    info["path"].write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git_commit_push(file_paths: list[Path] | Path, message: str, docs_reason: str) -> str:
    """Stage files, commit if dirty, push. Returns output summary.

    🔴 **`docs_reason` is REQUIRED, and without it this function could not commit at all between
    2026-08-04 and 2026-08-12.** The repo's `commit-msg` hook refuses any commit whose changed
    files' owning CLAUDE.md is not in the same commit, and an instance config under
    `algos/markets/fx/instances/` is owned by `algos/CLAUDE.md`. Nothing here stages that file —
    nor could it, since the hook exists to demand a PARAGRAPH a human wrote — so every deploy this
    router performs died at `git commit` and surfaced as **500 "git push failed"**. Measured, not
    reasoned about: the hook was run against a staged instance config and refused with exit 1, and
    the last commit this app ever made is dated 2026-07-30, five days before the hook landed.

    ⚠ **The fix is the hook's own in-band escape, deliberately NOT `--no-verify` and NOT a new
    exemption.** `--no-verify` is forbidden here precisely because it leaves no trace, and an
    exemption for `*/instances/*.json` would also wave through a HUMAN hand-editing one — which is
    the case the hook is right about, and is exactly what today's account move needed. A
    `DOCS: none - <reason>` line asks the caller to say why in the log, where the next person
    reads it.

    ⚠ **It has no default.** A default reason is boilerplate the moment a second caller copies it,
    and the whole value of this line is that it is specific to what was written.

    **This is the third time a rule fired on a robot's commit and silently stopped the job** —
    `algos/tools/ledger_sync.py` twice on 2026-08-05. A hook has no human to read its message when
    the committer is a program: it does not nag, it stops the work and reports something else.
    """
    if not docs_reason or len(docs_reason.strip()) < 10:
        # Guarded here rather than left to the hook: the hook's refusal arrives as a
        # CalledProcessError two lines later and is reported to the browser as "git push failed",
        # which names the wrong step. This says what is actually wrong, to the developer.
        raise ValueError(
            "docs_reason must say something — the commit-msg hook requires at least "
            "ten characters after 'DOCS: none -'"
        )
    message = f"{message}\n\nDOCS: none - {docs_reason.strip()}"
    root = str(cfg.MONOREPO_ROOT)
    paths = [file_paths] if isinstance(file_paths, Path) else file_paths
    rels = [str(p.relative_to(cfg.MONOREPO_ROOT)) for p in paths]
    for rel in rels:
        subprocess.run(["git", "-C", root, "add", rel], check=True, capture_output=True, timeout=15)
    status = subprocess.run(
        ["git", "-C", root, "status", "--porcelain"] + rels,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if not status.stdout.strip():
        return "nothing to commit"
    subprocess.run(
        ["git", "-C", root, "commit", "-m", message], check=True, capture_output=True, timeout=15
    )
    out = subprocess.run(
        ["git", "-C", root, "push", "origin", "main"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (out.stdout + out.stderr).strip()


def _notify_telegram(text: str):
    """Send a Telegram notification. Never raises.

    Delegates to `services/notify.py` — this router used to carry its own copy of the token,
    chat id and urllib call, which is how the credential ended up committed in six places at
    once. One sender, one credential lookup.

    Everything this router announces is HEALTH: started, stopped, restarted, promoted, runtime
    params applied. None of them is a fill — the live bot sends those itself, from the box, and
    it is the only thing here that can. So this helper hardcodes the kind rather than taking one,
    which is what stops a new endpoint from quietly putting an operational message in the room
    that carries trades.

    Returns Telegram's message id (None on any failure), so a caller can make later messages
    REPLY to this one. Nothing has to use it — every existing call site ignores it — but the
    deploy sequence does, because its three messages come from two different machines and a
    thread is the only thing that says they are one event.
    """
    return send_telegram_id(text, notify.HEALTH)


def _suppress_stop_alert(bot_key: str) -> None:
    """Write bot key to stop_suppress.json so the crash monitor skips alerting.
    Mirrors algo.py suppress_stop_alert(). MUST be called before killing the process.
    """
    suppress_key = _SUPPRESS_KEYS.get(bot_key)
    if not suppress_key:
        return
    _ssh(
        f'python -c "'
        f"import json,pathlib;"
        f"p=pathlib.Path(r'C:/trading/algos/stop_suppress.json');"
        f"k=json.loads(p.read_text()) if p.exists() else [];"
        f"k.append('{suppress_key}') if '{suppress_key}' not in k else None;"
        f'p.write_text(json.dumps(k))"'
    )


class VpsUnreachable(RuntimeError):
    """The SSH call itself failed — no answer came back at all.

    That is NOT the same as an answer which happens to be empty, and everything on the Bots
    page depends on the difference. `wmic … get commandline` prints nothing when no bot is
    running, and a dead tunnel also prints nothing — so while both arrived as `""`,
    `get_snapshot` reported **every bot STOPPED with a null balance and no error anywhere**.
    A confident wrong answer, on the one page whose job is to tell you whether the bots are
    up. Measured 2026-08-04: a broken `ssh` exits **255 with empty stdout and raises no
    exception**, so the old body returned `""` and the caller could not tell.

    Same rule as `mt5_link` and `mt5_connected` one layer up, and the repo's standing one:
    *no data* and *cannot ask* must never be the same value.
    """


def _ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", VPS_HOST, cmd],
        capture_output=True,
        timeout=30,
    )
    # Windows stdout is cp1252; decode with replacement so non-UTF-8 chars
    # (arrows, dashes, degree signs) don't raise UnicodeDecodeError → 500.
    out = result.stdout.decode("utf-8", errors="replace").strip()

    # OpenSSH reserves 255 for its OWN failures — host unresolvable, connection refused,
    # auth rejected, tunnel dead. A remote command that merely fails reports its own code:
    # `type` on a missing file exits 1, a `wmic … call terminate` that matched nothing
    # likewise, and those are ORDINARY here — half the commands in this module end in
    # `2>nul` precisely because failing is the normal case. So 255 is the only code read as
    # "we never got an answer", and only with empty stdout, so a remote program that
    # genuinely exits 255 after printing something is still believed.
    if result.returncode == 255 and not out:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        raise VpsUnreachable(err or f"ssh to {VPS_HOST} failed and said nothing")
    return out


_MARKER_RE = re.compile(r"(?<!\n)(===[A-Z0-9_]+===)")


def _parse_sections(raw: str, initial_section: str) -> dict[str, str]:
    # Put a glued marker back on its own line before splitting. `type` on Windows emits no
    # trailing newline, so a marker echoed after it arrives welded to the file's last
    # character — `}===TELEGRAM_START===` — and the startswith test below silently misses
    # it, merging two sections into one unparseable blob with no error anywhere.
    #
    # The FETCH command already guards this with `echo.` (see _fetch_vps_snapshot). This is
    # the second line of defence, because the failure is invisible: no exception, no empty
    # result, just a bot that shows RUNNING and reports nothing about itself. The pattern
    # is deliberately narrow (upper-case marker names only) so a `===` inside real payload
    # data cannot be mistaken for one.
    raw = _MARKER_RE.sub(r"\n\1", raw)

    sections: dict[str, str] = {}
    current = initial_section
    buf: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("==="):
            sections[current] = "\n".join(buf).strip()
            current = stripped.strip("=").strip().lower().replace(" ", "_")
            buf = []
        else:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


def _fetch_vps_snapshot() -> dict[str, str]:
    """Single batched VPS fetch — replicates algo.py's fetch_vps_snapshot()."""
    cmd1 = (
        "wmic process where \"name='python.exe'\" get commandline /format:list 2>nul"
        " & echo ===TASKS==="
        " & schtasks /query /fo CSV /nh 2>nul"
    )
    sections = _parse_sections(_ssh(cmd1), "procs")

    # One `type` per registered instance's bot_state.json, plus the Telegram start marker.
    # Built from _BOT_STATE_SECTIONS so adding a bot never means editing this string —
    # the two drifting apart is how a registered bot silently reports no state forever.
    # Two cmd quirks, both of which silently merged sections rather than erroring:
    #
    # 1. `type X 2>nul`, never `if exist X (type X)`. A trailing `& next` BINDS to the
    #    if-block, so ONE missing state file swallows every section after it.
    # 2. `echo.` before every marker. `type` does not emit a trailing newline, so the next
    #    marker lands on the same line as the file's last character — `}===TELEGRAM_START===`
    #    — which `_parse_sections` does not recognise as a marker (it tests startswith).
    #    Both sections then merge into one unparseable blob and the bot silently reports no
    #    state at all. This only appears once a state file has CONTENT, so it cannot be
    #    caught before a bot has run once.
    parts = [
        f"echo. & echo ==={s.upper()}=== & type {_BOT_STATE_PATHS[s]} 2>nul"
        for s, _ in _BOT_STATE_SECTIONS
    ]
    # The hourly review's flag, one per bot. It rides on the SAME connection for the same
    # reason the state files do — a second ssh round trip per bot is the cost this batching
    # exists to avoid. Missing is the normal case and means "nothing to review", so the
    # `2>nul` swallowing it is correct rather than lossy.
    parts += [
        f"echo. & echo ==={_review_section(b.key).upper()}=== & type {b.review_file} 2>nul"
        for b in _BOTS
    ]
    parts.append(
        "echo. & echo ===TELEGRAM_START=== & type C:\\trading\\algos\\telegram_start.json 2>nul"
    )
    sections.update(_parse_sections(_ssh(" & ".join(parts)), "state_main"))
    return sections


# Derived from the registry. `(section, [bot keys in that bot_state.json])` — one entry per
# FILE, and the value is a list because a single bot_state.json can hold several bot keys
# (two bots sharing an instance dir share a `state_section`, and this groups them).
_BOT_STATE_SECTIONS: list[tuple[str, list[str]]] = [
    (section, [b.key for b in _BOTS if b.state_section == section])
    for section in dict.fromkeys(b.state_section for b in _BOTS)
]

# section → the VPS path `_fetch_vps_snapshot` types. Windows paths throughout — never
# anything derived from this Mac's filesystem.
_BOT_STATE_PATHS: dict[str, str] = {b.state_section: b.state_file for b in _BOTS}


def _review_section(bot_key: str) -> str:
    """The snapshot section name for one bot's review flag. Derived, never restated — the
    fetch and the parse must agree, and the way they drift is a flag that is fetched and then
    looked for under a different name, i.e. silently always absent."""
    return f"review_{bot_key}"


def _parse_reviews(snap: dict[str, str]) -> dict[str, dict]:
    """{bot key: review flag} for every bot that has one.

    ⚠ An absent section means NOTHING TO REVIEW, and a malformed one is dropped. Neither is
    reported as a fault here on purpose: this page must not invent an alarm out of its own
    plumbing failing, and the review job's own absence is visible where it belongs — as a
    DISABLED `SYS_LOGREVIEW` in the scheduled-jobs list below.
    """
    out: dict[str, dict] = {}
    for b in _BOTS:
        raw = (snap.get(_review_section(b.key)) or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("findings"):
            out[b.key] = data
    return out


def _parse_bot_states(snap: dict[str, str]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for section, keys in _BOT_STATE_SECTIONS:
        raw = snap.get(section, "")
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for k in keys:
                if k in data:
                    states[k] = data[k]
        except Exception:
            pass
    return states


def _parse_tasks(snap: dict[str, str]) -> dict[str, str]:
    """Return {task_name: status} from schtasks CSV."""
    tasks: dict[str, str] = {}
    for line in snap.get("tasks", "").splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        # schtasks reports the task's PATH, not its name — `\SYS_MONITOR`, with a leading
        # backslash (and `\Folder\Name` if one is ever nested). Matching the raw value
        # against _DISPLAY_NAMES therefore never hit, so this returned {} and EVERY job on
        # the Bots page read UNKNOWN from the day the router was written.
        name = parts[0].strip('"').lstrip("\\").rsplit("\\", 1)[-1]
        status = parts[2].strip('"')
        if name in _DISPLAY_NAMES:
            tasks[name] = status
    return tasks


def _is_python_running(snap: dict[str, str], script_fragment: str) -> bool:
    return script_fragment.lower() in snap.get("procs", "").lower()


def _uptime_seconds(state: dict) -> int | None:
    # bot_state.py writes "started" as a Unix timestamp float (time.time()).
    # Fall back to ISO string fields used by older/alternate state writers.
    raw = state.get("started") or state.get("started_at") or state.get("start_time")
    if not raw:
        return None
    try:
        if isinstance(raw, (int, float)) and raw > 0:
            return int(_time.time() - raw)
        # ISO string fallback
        start = datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - start).total_seconds())
    except Exception:
        return None


_USERS_FILE_VPS = r"C:\trading\algos\users.json"
_USERS_PY_PATH = "C:/trading/algos/users.json"

# Markers the VPS echoes back, so "no file" and "no answer" are different values here too.
_USERS_ABSENT = "===USERS_ABSENT==="
_USERS_WRITTEN = "===USERS_WRITTEN==="


class UsersFileUnreadable(RuntimeError):
    """We could not establish what users.json currently holds.

    Every write here is a READ-MODIFY-WRITE of the whole file, so a failed read is not a
    read-shaped inconvenience — it is a delete. `_read_users_vps` used to answer `{}` for a
    missing file, an unreadable file, a locked file, a corrupt file and a dead SSH alike,
    and `add_user` then wrote `{"users": {the one new user}}`, **silently removing everyone
    else**. Remove and role-change happened to be safe (they 404 on an empty dict); add was
    the one that destroys.

    So the absent case is now the ONLY one that answers `{}` — it is the genuine first-user
    path, and the VPS says so in its own words rather than by returning nothing.
    """


def _read_users_vps() -> dict:
    """Read users.json off the VPS, or raise. Never guesses `{}`.

    `type x 2>nul` cannot express the difference between "no such file" and "could not read
    it", which is exactly the difference that matters, so this asks Python on the far end.
    """
    raw = _ssh(
        f'python -c "import pathlib,sys;'
        f"p=pathlib.Path(r'{_USERS_PY_PATH}');"
        f"sys.stdout.write(p.read_text(encoding='utf-8') if p.exists() else '{_USERS_ABSENT}')\""
    ).strip()

    if raw == _USERS_ABSENT:
        return {}
    if not raw:
        # The one-liner itself failed (no python on PATH, file locked mid-read). Empty is
        # not an answer — a bare `{}` here is how the file gets emptied.
        raise UsersFileUnreadable(f"the VPS returned nothing for {_USERS_FILE_VPS}")
    try:
        data = json.loads(raw)
    except Exception as e:
        raise UsersFileUnreadable(f"{_USERS_FILE_VPS} did not parse: {e}") from e
    users = data.get("users")
    if not isinstance(users, dict):
        raise UsersFileUnreadable(f"{_USERS_FILE_VPS} has no `users` object")
    return users


def _write_users_vps(users: dict) -> None:
    """Back the file up, write it, and confirm the write happened.

    The backup exists because this replaces the whole file from a dict assembled in this
    process; if that dict is ever wrong, `users.json.bak` is the only copy of who had
    access. The confirmation exists because a remote Python traceback exits non-zero with
    empty stdout, which `_ssh` correctly does NOT treat as a connection failure — so without
    a marker to look for, a failed write reports success.
    """
    payload = json.dumps({"users": users}, indent=2, ensure_ascii=True)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    out = _ssh(
        f'python -c "import base64,pathlib,shutil;'
        f"p=pathlib.Path(r'{_USERS_PY_PATH}');"
        f"p.exists() and shutil.copy2(p, p.with_name(p.name + '.bak'));"
        f"p.write_text(base64.b64decode(b'{b64}').decode(), encoding='utf-8');"
        f"print('{_USERS_WRITTEN}')\""
    )
    if _USERS_WRITTEN not in out:
        raise UsersFileUnreadable(
            f"the write to {_USERS_FILE_VPS} was not confirmed — it may be unchanged"
        )


# Every users endpoint is a read-modify-write of the WHOLE file, so two of them overlapping
# means the second one's read can predate the first one's write and silently undo it. FastAPI
# runs sync endpoints in a threadpool, so they genuinely can overlap. One lock, held across
# the read AND the write, is the whole fix — the operations are short and there is exactly
# one file.
_USERS_LOCK = threading.Lock()


def _users_or_502() -> dict:
    """Every users endpoint reads through here, so a read failure can never reach a write.

    502 rather than 500: nothing is wrong with this backend, we could not get an answer out
    of the VPS — and the caller needs to know it was not told "there are no users".
    """
    try:
        return _read_users_vps()
    except VpsUnreachable as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach the VPS — {e}")
    except UsersFileUnreadable as e:
        raise HTTPException(status_code=502, detail=str(e))


def _save_users_or_502(users: dict) -> None:
    try:
        _write_users_vps(users)
    except VpsUnreachable as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach the VPS — {e}")
    except UsersFileUnreadable as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/users", response_model=list[TelegramUser])
def list_users():
    users = _users_or_502()
    return [TelegramUser(chat_id=k, **v) for k, v in users.items()]


@router.post("/users", status_code=201)
def add_user(body: TelegramUserCreate):
    with _USERS_LOCK:
        users = _users_or_502()
        if body.chat_id in users:
            raise HTTPException(status_code=409, detail="User already exists")
        users[body.chat_id] = {
            "name": body.name,
            "role": body.role,
            "added": date.today().isoformat(),
        }
        _save_users_or_502(users)
    return {"status": "ok"}


def _refuse_last_admin(users: dict, after: dict) -> None:
    """Refuse a change that would leave nobody with the `admin` role.

    `admin` is the only role that carries `/stop`, `/restart`, `/emergency` and `/resume`
    (`algos/notifications/telegram_bot.py` → `ROLE_COMMANDS`), so a users.json with no admin
    means **nobody can stop a bot from Telegram**.

    ⚠ The bot's `ADMIN_CHAT` fallback does NOT cover this. It only fires when users.json is
    MISSING or unparseable — a file that exists and lists everyone as `readonly` is read as
    written, so the primary admin loses the commands too. Checked rather than assumed.
    """
    if any(u.get("role") == "admin" for u in users.values()) and not any(
        u.get("role") == "admin" for u in after.values()
    ):
        raise HTTPException(
            status_code=409,
            detail="That would leave no admin. Nobody could stop a bot from Telegram — "
            "promote someone else first.",
        )


@router.delete("/users/{chat_id}")
def remove_user(chat_id: str):
    with _USERS_LOCK:
        users = _users_or_502()
        if chat_id not in users:
            raise HTTPException(status_code=404, detail="User not found")
        after = {k: v for k, v in users.items() if k != chat_id}
        _refuse_last_admin(users, after)
        _save_users_or_502(after)
    return {"status": "ok"}


@router.patch("/users/{chat_id}")
def update_user_role(chat_id: str, body: TelegramUserRoleUpdate):
    with _USERS_LOCK:
        users = _users_or_502()
        if chat_id not in users:
            raise HTTPException(status_code=404, detail="User not found")
        after = {k: dict(v) for k, v in users.items()}
        after[chat_id]["role"] = body.role
        _refuse_last_admin(users, after)
        _save_users_or_502(after)
    return {"status": "ok"}


@router.get("/snapshot", response_model=BotSnapshot)
def get_snapshot():
    try:
        snap = _fetch_vps_snapshot()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except VpsUnreachable as e:
        # Named separately from the generic failure below because this is the one the page
        # used to render as "every bot stopped". An unanswerable question must arrive as an
        # error, never as a snapshot full of confident STOPPEDs.
        raise HTTPException(status_code=502, detail=f"Cannot reach the VPS — {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS fetch failed: {e}")

    bot_states = _parse_bot_states(snap)
    reviews = _parse_reviews(snap)
    task_statuses = _parse_tasks(snap)
    now = datetime.now(timezone.utc)

    bots: list[BotStatus] = []
    for task_name in _BOT_DISPLAY_ORDER:
        bot_key = _TASK_BOT_KEYS.get(task_name, "")
        state = bot_states.get(bot_key, {})

        # THE PROCESS LIST IS AUTHORITATIVE, and now the code says so too — it used to read
        # `task_status == "Running" or running_in_procs`, i.e. the exact opposite of the
        # comment sitting above it, which is the kind of disagreement nobody re-reads.
        #
        # Every other signal here can claim RUNNING for a dead bot. `bot_state.json` is
        # never updated after a hard kill, so it says "running" indefinitely. And the
        # scheduled task answers a different question altogether: a bot boots through
        # SYS_STARTUP → startup_coordinator.py, which EXITS once it has spawned the bot, so
        # the task is "Running" only while the launcher runs and "Ready" for the entire life
        # of the bot it started. Reading that as the bot's status is backwards.
        #
        # `task_status` is still parsed and still shown for the SYS_* jobs below, where it
        # IS the question being asked.
        status = "RUNNING" if _is_python_running(snap, bot_key) else "STOPPED"

        total_pnl = state.get("total_pnl_pct")
        if total_pnl is not None:
            try:
                total_pnl = float(total_pnl)
            except Exception:
                total_pnl = None

        bots.append(
            BotStatus(
                key=bot_key,
                name=_DISPLAY_NAMES.get(task_name, task_name),
                # An MT5 login is an INT everywhere it matters — LiveConfig.account is typed
                # int and BotMT5.connect compares it numerically to refuse the wrong account.
                # It is only a string for display, so the coercion belongs here and nowhere
                # upstream: making the registries hold strings to satisfy a label would put a
                # display concern inside the account guard.
                account=str(state.get("account") or ""),
                # From the registry, which cannot omit it — `account_type` has no default on
                # BotReg, so a bot registered without one is a TypeError at import. The old
                # `.get(task, "demo")` defaulted in the dangerous direction: a LIVE bot
                # rendered as demo, losing the amber tinting, the "N of these are LIVE
                # accounts" warning on every fleet dialog, and its place in the demo/live filter.
                account_type=_BY_TASK[task_name].account_type,
                balance=state.get("balance"),
                # Read with a THREE-way result on purpose: True, False, or "the bot never said".
                # `state.get("mt5_link")` on a bot that predates the field returns None, and
                # coercing that to False would paint a healthy bot as disconnected — the same
                # rule `mt5_connected` follows on the sidebar's MT5 dot.
                mt5_link=state.get("mt5_link") if status == "RUNNING" else None,
                # ⚠ NOT gated on `status == "RUNNING"`, unlike `mt5_link` above. A review is about
                # what the RECORD says happened, and the findings that matter most — it crashed, it
                # was killed, it refused to start — are precisely the ones you can only read once
                # the bot is no longer running. Hiding the flag on a stopped bot would suppress the
                # explanation at the exact moment somebody wants it.
                review=reviews.get(bot_key),
                status=status,
                uptime_seconds=_uptime_seconds(state) if status == "RUNNING" else None,
                total_pnl_pct=total_pnl,
                day_locked=bool(state.get("day_locked", False)),
                lock_reason=state.get("lock_reason") or None,
                last_updated=state.get("last_updated") or None,
            )
        )

    # Scheduled jobs
    jobs: list[JobStatus] = []
    for job in _SCHEDULED_JOBS:
        # Derived from _SYS_DISPLAY_NAMES rather than restated, so a job cannot be listed
        # under a name this loop then fails to resolve to a task.
        task_key = _SYS_TASK_BY_JOB.get(job.name)
        t_status = task_statuses.get(task_key, "") if task_key else ""
        # "Disabled" is its own answer, not a STOPPED — a task somebody switched off is not
        # a task that failed, and showing it as merely stopped reads as a fault to go fix.
        # ⚠ All three of these SHOULD be enabled today: the two that were legitimately off
        # ("waiting for a bot registry") were deleted 2026-08-05, so a DISABLED here now
        # means somebody turned a live watchdog off.
        if t_status == "Running":
            status = "RUNNING"
        elif t_status == "Disabled":
            status = "DISABLED"
        elif t_status:
            status = "STOPPED"
        else:
            status = "UNKNOWN"
        jobs.append(JobStatus(name=job.name, schedule=job.schedule, status=status))

    # Telegram
    tg_raw = snap.get("telegram_start", "")
    tg_status = "UNKNOWN"
    if tg_raw:
        try:
            tg_data = json.loads(tg_raw)
            tg_status = "RUNNING" if tg_data.get("running") else "STOPPED"
        except Exception:
            pass
    if _is_python_running(snap, "telegram"):
        tg_status = "RUNNING"

    telegram = ProcessStatus(name="Telegram", status=tg_status)

    return BotSnapshot(fetched_at=now, bots=bots, scheduled_jobs=jobs, telegram=telegram)


# ── Accounts — which bots share a balance, and the ceiling over it ────────────
#
# Registered BEFORE the `/{bot_name}/…` routes by convention, though nothing here is
# ambiguous: these are literal segments and the per-bot routes all carry a trailing verb.
#
# ⚠ These endpoints do NOT touch the VPS. Grouping and the cap are read from the instance
# configs in the repo, which is what the bots read too — so this is fast enough to poll and
# answers while the box is unreachable. Whether a bot is RUNNING is a different question with
# a different source (the snapshot), and the page joins the two on `key` rather than making
# this endpoint take an SSH round trip it does not need.


def _account_groups() -> list:
    """Read every registered bot's config and group by account.

    An unreadable config is passed through as `None` rather than dropped: a bot missing from
    its account reads as an account with fewer bots on it, which is the most reassuring wrong
    answer available on a page about how much risk is on.
    """
    configs: dict[str, dict | None] = {}
    for reg in _BOTS:
        try:
            configs[reg.key] = _read_instance_config(reg.key)
        except Exception:
            configs[reg.key] = None
    return bot_accounts.group_by_account(configs, {b.key: b.display for b in _BOTS})


@router.get("/accounts", response_model=list[BotAccountGroup])
def list_bot_accounts():
    """Which bots share a trading account, and what ceiling that account is under.

    A stack on the live side is READ, not configured: two bots naming the same `account` are
    trading one balance whether or not anybody grouped them. See `services/bot_accounts.py`.
    """
    return [
        BotAccountGroup(
            account=g.account,
            server=g.server,
            kind=g.kind,
            bots=[BotAccountBot(**vars(b)) for b in g.bots],
            risk_cap_pct=g.risk_cap_pct,
            cap_agrees=g.cap_agrees,
            cap_unknown=g.cap_unknown,
            stacked=g.stacked,
            cap_takes_turns=g.cap_takes_turns,
            magic_clash=g.magic_clash,
        )
        for g in _account_groups()
    ]


def _registry_path():
    return bot_account_registry.registry_path(cfg.MONOREPO_ROOT)


# The VPS copy of the git-ignored credentials file. A password written from this page lands
# HERE and nowhere else — never in `accounts.json`, never in git, never in a log line.
_VPS_CREDENTIALS = r"C:\trading\algos\credentials.json"
_CREDS_WRITTEN = "===CREDS_WRITTEN==="


def _known_profiles() -> set[str] | None:
    """The measured cost profiles an account may name.

    `None` when the roster cannot be loaded, which makes `upsert_account` SKIP that check rather
    than accept an unchecked name silently — the caller states the gap instead of the validator
    guessing. In practice this always resolves; the lab runner imports the same module.
    """
    try:
        from backtest.fills import PROFILES

        return set(PROFILES)
    except Exception:
        return None


def _accounts_with_a_password() -> set[int] | None:
    """Which registered accounts the VPS credentials file holds a login for.

    ⚠ **It returns the KEYS, never the values, and there is no endpoint that returns a password.**
    The page needs one bit per account — will this move be able to connect — and that bit is
    answerable without the secret leaving the box.

    ⚠ **`None` means the VPS could not be asked, and it must not be rendered as "no password".**
    A move refused because the page believed a real credential was missing sends the reader to
    re-enter a password that was already there.
    """
    try:
        out = _ssh(
            f'python -c "import json,pathlib;'
            f"d=json.loads(pathlib.Path(r'{_VPS_CREDENTIALS}').read_text());"
            f"print(' '.join((d.get('mt5_accounts') or {{}}).keys()))\" 2>nul"
        )
    except Exception:
        return None
    nums = set()
    for tok in out.split():
        try:
            nums.add(int(tok))
        except ValueError:
            continue
    return nums


def _write_account_password(account: int, password: str) -> None:
    """Store one MT5 password in the VPS credentials file.

    ⚠ **The secret goes over STDIN, never in argv.** An argument is visible in the process list
    on the VPS and in this machine's own — base64 would not help, since it is an encoding rather
    than a secret. `_write_users_vps` next door can use argv because a Telegram chat id is not a
    credential; this cannot.

    ⚠ **It read-modify-writes the whole file, so a failed READ must never become a write.** The
    remote script refuses on a parse failure rather than starting from `{}` — that is the shape
    that could delete every other credential on the box, and it is the `users.json` defect of
    2026-08-04 with far worse consequences.

    ⚠ **The write is CONFIRMED by a marker.** A remote Python traceback exits non-zero with empty
    stdout, which `_ssh` correctly does not read as a connection failure — so without a marker a
    failed write reports success, and the next start fails with "no credentials" for an account
    the page says is configured.
    """
    script = (
        "import json,pathlib,sys,shutil;"
        f"p=pathlib.Path(r'{_VPS_CREDENTIALS}');"
        "d=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {};"
        "a=d.setdefault('mt5_accounts',{});"
        "pw=sys.stdin.read();"
        f"a[{str(account)!r}]=dict(a.get({str(account)!r}) or {{}}, password=pw);"
        "p.exists() and shutil.copy2(p,p.with_name(p.name+'.bak'));"
        "p.write_text(json.dumps(d,indent=2),encoding='utf-8');"
        f"print({_CREDS_WRITTEN!r})"
    )
    result = subprocess.run(
        ["ssh", VPS_HOST, f'python -c "{script}"'],
        input=password.encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    out = result.stdout.decode("utf-8", errors="replace")
    if _CREDS_WRITTEN not in out:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        raise HTTPException(
            status_code=502,
            detail=f"the password write to {_VPS_CREDENTIALS} was not confirmed, so the account "
            f"may have no credentials — {err or 'the VPS said nothing'}",
        )


def _registration(entry, bot_keys: list[str], with_password: set[int] | None):
    return BotAccountRegistration(
        **{k: v for k, v in vars(entry).items()},
        assignable=entry.assignable,
        unassignable_reason=entry.unassignable_reason,
        has_password=None if with_password is None else (entry.account in with_password),
        bot_keys=bot_keys,
    )


@router.get("/accounts/registry", response_model=list[BotAccountRegistration])
def list_registered_accounts():
    """The accounts a bot can be put on.

    🔴 **This is what an account move needed and did not have.** Grouping bots by account is
    DERIVED and must stay derived — two bots naming one account are sharing a balance whether or
    not anybody grouped them — but that derivation could only ever see accounts some bot was
    already on. So the FIRST bot on a new account was unmovable from this page, and the 2026-08-12
    ECN move was a hand-edited config on the VPS because of it.

    ⚠ **The registry does not hold the risk cap and never will.** The cap is stored per instance
    because a bot reads only its own config, so `GET /bots/accounts` reports what the bots say and
    refuses when they disagree. A copy here would be a second answer.

    ⚠ **`has_password` degrades to `None` rather than failing the request.** The registry is a
    local file and is always readable; only the credential check needs the box. A 502 for the
    whole list would hide four accounts because one bit could not be measured.
    """
    try:
        entries = bot_account_registry.load_accounts(_registry_path())
    except bot_account_registry.RegistryError as e:
        raise HTTPException(status_code=500, detail=str(e))

    on_account: dict[int, list[str]] = {}
    for g in _account_groups():
        if g.kind == "account" and g.account is not None:
            on_account[g.account] = [b.key for b in g.bots]

    with_password = _accounts_with_a_password()
    return [_registration(e, on_account.get(e.account, []), with_password) for e in entries]


@router.put("/accounts/registry/{account}", response_model=BotAccountRegistration)
def register_account(account: int, body: BotAccountRegistrationWrite):
    """Add a broker account, or replace the registered facts about one.

    ⚠ **It REPLACES the row rather than merging**, so a field cleared on the page is cleared on
    disk — a merge makes removing a symbol suffix inexpressible, because the absent value and the
    unchanged value become the same request.

    ⚠ **The password, if one is sent, goes to a DIFFERENT FILE on a different machine** — the
    git-ignored `algos/credentials.json` on the VPS — and it is written BEFORE the registry is
    committed. That order is deliberate: a registered account with no credentials is a visible,
    fixable state that the list reports, while a pushed registry row whose password write failed
    afterwards would read as complete.
    """
    if account != body.account:
        raise HTTPException(
            status_code=400, detail=f"path account {account} does not match body {body.account}"
        )

    entry = bot_account_registry.RegisteredAccount(
        account=body.account,
        label=body.label,
        broker=body.broker,
        tier=body.tier,
        kind=body.kind,
        server=body.server,
        mt5_path=body.mt5_path,
        symbol_suffix=body.symbol_suffix,
        account_profile=body.account_profile,
        note=body.note,
    )

    if body.password:
        _write_account_password(account, body.password)

    try:
        stored, created = bot_account_registry.upsert_account(
            _registry_path(), entry, _known_profiles()
        )
    except bot_account_registry.RegistryError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if body.deploy:
        _deploy_registry(
            f"accounts: {'registered' if created else 'updated'} "
            f"{account} ({body.label or body.server}) [command center]"
        )

    with_password = _accounts_with_a_password()
    bots_here = [b.key for g in _account_groups() if g.account == account for b in g.bots]
    return _registration(stored, bots_here, with_password)


@router.delete("/accounts/registry/{account}")
def unregister_account(account: int, deploy: bool = True):
    """Forget a broker account.

    ⚠ **Refused while a bot still names it.** The bot would go on trading an account this page
    could no longer describe — and the next reader would see it filed under an account with no
    server, no terminal and no symbol suffix. Bench or move the bot first.

    ⚠ **It does NOT touch the credentials file.** Deleting a password is a separate, irreversible
    action against a file this endpoint has no business rewriting as a side effect.
    """
    bots_here = [
        b.key
        for g in _account_groups()
        if g.kind == "account" and g.account == account
        for b in g.bots
    ]
    if bots_here:
        raise HTTPException(
            status_code=409,
            detail=f"{', '.join(bots_here)} still trade account {account}. Move or bench them "
            f"first — unregistering it would leave them on an account this page cannot "
            f"describe.",
        )
    try:
        removed = bot_account_registry.remove_account(_registry_path(), account)
    except bot_account_registry.RegistryError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not removed:
        raise HTTPException(status_code=404, detail=f"account {account} is not registered")

    if deploy:
        _deploy_registry(f"accounts: unregistered {account} [command center]")
    return {"status": "ok", "account": account, "deployed": deploy}


@router.put("/accounts/registry/{account}/password")
def set_account_password(account: int, body: BotAccountPassword):
    """Store this account's MT5 password on the VPS.

    **Write-only, by design.** There is no read counterpart and there must not be one: the page
    needs to know whether a password EXISTS, which `GET /accounts/registry` answers as a boolean,
    and nothing beyond that. The secret travels over stdin (never argv, which is visible in a
    process list) into the git-ignored `algos/credentials.json`, keyed by the account number — the
    same place `live_config.account_credentials` reads it from, so the bot needs no change.
    """
    if bot_account_registry.account_by_number(_registry_path(), account) is None:
        raise HTTPException(
            status_code=404,
            detail=f"account {account} is not registered. Register it first — a password for an "
            f"account nothing knows about cannot be checked or used.",
        )
    _write_account_password(account, body.password)
    return {"status": "ok", "account": account, "has_password": True}


def _deploy_registry(message: str) -> None:
    """Commit, push and pull the registry onto the VPS. It is git-tracked and holds no secrets."""
    try:
        _git_commit_push(
            _registry_path(),
            message,
            "the broker-account registry was edited from the Bots page; it carries no code and "
            "no secrets, and the change is named in the message",
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"git push failed: {e.stderr.decode(errors='replace')}"
        )
    try:
        _ssh("cd C:\\trading && git pull origin main")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")


@router.patch("/accounts/{account}/risk-cap")
def set_account_risk_cap(account: int, update: BotAccountCapUpdate):
    """Set the account-level risk cap on EVERY bot trading this account.

    **One write, N files.** The cap is an account-level fact stored per instance, because an
    instance config is the only file a bot reads — so the only safe way to change it is to
    change it everywhere at once. `live_config._assert_account_cap_agrees` refuses to start a
    bot into a half-applied state, which makes a partial write loud rather than silent; this
    endpoint's job is to never produce one.

    ⚠ **It NEVER reports the cap as applied.** `account_risk_cap_pct` is not in
    `live_config.RUNTIME_RELOADABLE` — the bridge reads it and holds live order state, so it is
    picked up at startup and nowhere else. The response says `restart_required` and names the
    bots, because a cap that is written and not running is the one state that reads as protected
    and is not.
    """
    groups = {g.account: g for g in _account_groups()}
    group = groups.get(account)
    if group is None:
        raise HTTPException(status_code=404, detail=f"No registered bot trades account {account}")

    try:
        targets = bot_accounts.cap_change_plan(group, update.risk_cap_pct)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    bot_keys = [b.key for b in group.bots]
    if not targets:
        # Nothing to write, and therefore nothing to restart — but the bots may still be
        # RUNNING on an older value, which this endpoint cannot see and must not imply.
        return {
            "status": "ok",
            "changed": False,
            "updated": [],
            "restart_required": False,
            "bots": bot_keys,
            "detail": "Every bot on this account already states that cap.",
        }

    paths = []
    for key in targets:
        data = _read_instance_config(key)
        if update.risk_cap_pct is None:
            data["account_risk_cap_pct"] = None
        else:
            data["account_risk_cap_pct"] = float(update.risk_cap_pct)
        _write_instance_config(key, data)
        paths.append(_BOT_INSTANCE_MAP[key]["path"])

    cap_s = "no cap" if update.risk_cap_pct is None else f"{update.risk_cap_pct}%"
    changed = f"account {account} risk cap → {cap_s} ({', '.join(targets)})"

    if not update.deploy:
        return {
            "status": "ok",
            "changed": True,
            "deployed": False,
            "updated": targets,
            "restart_required": True,
            "bots": bot_keys,
            "detail": changed,
        }

    try:
        _git_commit_push(
            paths,
            f"risk cap: {changed} [command center]",
            "account-level risk cap written to every instance config on the account by the "
            "Bots page; an operational deployment, and the numbers are in the message",
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"git push failed: {e.stderr.decode(errors='replace')}"
        )
    try:
        out = _ssh("cd C:\\trading && git pull origin main")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")

    _notify_telegram(
        alert(
            "⚙️",
            "ACCOUNT RISK CAP",
            f"account {account}",
            f"Cap {cap_s} written to {len(targets)} bot(s).",
            "Restart them — the cap only applies at startup.",
        )
    )
    return {
        "status": "ok",
        "changed": True,
        "deployed": True,
        "updated": targets,
        "restart_required": True,
        "bots": bot_keys,
        "detail": changed,
        "output": out,
    }


@router.patch("/{bot_name}/account")
def set_bot_account(bot_name: str, update: BotAccountAssign):
    """Put this bot ON an account, or take it OFF one.

    **This is add-and-remove for a live stack, and it is a config write rather than a membership
    record** — the same reasoning `services/bot_accounts.py` opens with. Two bots naming one
    account ARE sharing a balance, so "add B-LEG to this account" can only mean one thing: write
    that account into B-LEG's config. There is nothing else to update, and nothing that can
    disagree with it afterwards.

    ⚠ **It writes FOUR fields, not one** — account, server, terminal path, risk cap — and
    `assign_plan` explains why each is load-bearing. The cap is the one that bites: a bot joining
    an account while stating a different cap does not merely misconfigure itself, it takes every
    bot already on that account off the box at their next restart, because
    `live_config._assert_account_cap_agrees` refuses the whole account.

    ⚠ **A RUNNING bot is refused (409).** Its config was read at startup, so the file change
    cannot reach the live process — the page would show it under a new account while it went on
    trading the old one, which is a screen lying about a live position rather than a stale
    setting. Stop it, move it, start it.

    ⚠ **It never reports the move as in effect**, for the cap endpoint's reason: `account` is not
    in `live_config.RUNTIME_RELOADABLE` and could not be, so the response says `restart_required`
    and the bot has to be started before any of this is true on the box.
    """
    _, bot_key = _resolve_bot(bot_name)

    if _bot_is_running(bot_key):
        raise HTTPException(
            status_code=409,
            detail=f"{bot_key} is running, so its account cannot be changed — it read its config "
            f"at startup and would go on trading the old account while this page showed "
            f"the new one. Stop it first, then move it.",
        )

    groups = _account_groups()
    current = next((g for g in groups if any(b.key == bot_key for b in g.bots)), None)
    if current is not None and current.kind == "unknown":
        raise HTTPException(
            status_code=409,
            detail=f"{bot_key}'s config could not be read, so there is nothing safe to write "
            f"over. Fix the file first.",
        )

    target = None
    registered = None
    if update.account is not None:
        target = next(
            (g for g in groups if g.kind == "account" and g.account == update.account), None
        )
        try:
            registered = bot_account_registry.account_by_number(_registry_path(), update.account)
        except bot_account_registry.RegistryError as e:
            raise HTTPException(status_code=500, detail=str(e))
        if target is None and registered is None:
            raise HTTPException(
                status_code=404,
                detail=f"Account {update.account} is not registered and no bot trades it, so "
                f"nothing here knows its server, its terminal or its symbol suffix. Add "
                f"it under Accounts first.",
            )
        if registered is not None and not registered.assignable:
            raise HTTPException(status_code=409, detail=registered.unassignable_reason)

        # ⚠ Refused on a DEFINITE no, never on an unanswered question. A bot on an account with
        # no stored password cannot connect, and finding that out at the next start — after a
        # commit, a push and a VPS pull — is exactly the discovery loop this page exists to
        # remove. `None` means the VPS could not be asked, and refusing on it would send the
        # reader to re-enter a password that is already there.
        with_password = _accounts_with_a_password()
        if with_password is not None and update.account not in with_password:
            raise HTTPException(
                status_code=409,
                detail=f"No MT5 password is stored for account {update.account}, so {bot_key} "
                f"could not log in. Set it under Accounts, then move the bot.",
            )

    data = _read_instance_config(bot_key)

    try:
        plan = bot_accounts.assign_plan(
            bot_key,
            update.account,
            target=target,
            registered=registered,
            current_symbol=str(data.get("symbol") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if plan.adopt_terminal_from and not plan.fields.get("mt5_path"):
        # The registry names the terminal directly; this is the fallback for an account that is
        # traded by a bot and not registered. Read off a PEER rather than trusting this bot's own
        # `mt5_path`, which describes wherever it used to be — a terminal not logged into the
        # account the bot now claims is a connection refusal with a message about credentials.
        peer = _read_instance_config(plan.adopt_terminal_from)
        if peer.get("mt5_path"):
            data["mt5_path"] = peer["mt5_path"]
    was = data.get("account")
    data.update(plan.fields)
    if plan.param_fields:
        # `strategy_params` is where the symbol and the cost profile live for the STRATEGY, and
        # both have to move with the account. Merged rather than replaced — every other key in
        # there is the bot's tuning and has nothing to do with which account it is on.
        params = dict(data.get("strategy_params") or {})
        params.update(plan.param_fields)
        data["strategy_params"] = params
    _write_instance_config(bot_key, data)

    where = "the bench" if update.account is None else f"account {update.account}"
    changed = f"{bot_key} → {where} (was {was if was is not None else 'the bench'})"

    if not update.deploy:
        return {
            "status": "ok",
            "changed": True,
            "deployed": False,
            "bot": bot_key,
            "account": update.account,
            "restart_required": True,
            "detail": changed,
            "notes": plan.notes,
        }

    path = _BOT_INSTANCE_MAP[bot_key]["path"]
    try:
        _git_commit_push(
            path,
            f"bots: {changed} [command center]",
            "a bot moved between accounts from the Bots page; an operational deployment, "
            "and the move is named in the message",
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"git push failed: {e.stderr.decode(errors='replace')}"
        )
    try:
        out = _ssh("cd C:\\trading && git pull origin main")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")

    _notify_telegram(
        alert(
            "⚙️",
            "BOT MOVED",
            bot_key,
            f"Now on {where}."
            + (
                ""
                if update.account is None
                else f" Risk cap {plan.fields.get('account_risk_cap_pct') or 'none'}."
            ),
            "It is not trading it yet — start the bot to apply."
            if update.account is not None
            else "It will not start until it is on an account again.",
        )
    )
    # ⚠ `notes` is what could NOT be carried — an account with no recorded symbol suffix, or one
    # that is not registered at all. It is served rather than swallowed because the failure it
    # describes is silent on the box: a bot pointed at a symbol its terminal does not quote
    # connects, warms up and receives no bars, which reads exactly like a quiet market.
    return {
        "status": "ok",
        "changed": True,
        "deployed": True,
        "bot": bot_key,
        "account": update.account,
        "restart_required": True,
        "detail": changed,
        "notes": plan.notes,
        "output": out,
    }


@router.get("/{bot_name}/log", response_class=PlainTextResponse)
def get_bot_log(bot_name: str, lines: int = 500):
    """Read the last N lines of a bot's stdout log over SSH."""
    task_name, bot_key = _resolve_bot(bot_name)
    reg = _BY_KEY[bot_key]
    log_path = rf"{_VPS_INSTANCES}\{reg.instance_dir}\{reg.log_file}"

    try:
        raw = _ssh(f"type {log_path} 2>nul")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")

    if not raw:
        return f"Log file not found or empty: {log_path}"

    log_lines = raw.splitlines()
    return "\n".join(log_lines[-lines:])


# ── Control actions ───────────────────────────────────────────────────────────
#
# All actions run over SSH.
#   stop  = kill each registered BOT process + delete the MT5 lock
#   start = run SYS_STARTUP scheduled task
#   restart = stop then start (with a 3-second gap)
#   emergency = kill the bots immediately, no lock cleanup (fastest path)
#
# Each endpoint returns { "status": "ok"|"error", "output": "<ssh stdout>" }.
# A 502 is raised when the SSH call itself fails or times out.

_LOCK_PATH = r"C:\trading\algos\mt5_connect.lock"
_STARTUP_TN = "SYS_STARTUP"


# How long a bot gets to notice its stop file and shut itself down before it is killed.
# It polls every `poll_seconds` (10 on the live bot) and then has to disconnect MT5 and write
# its records, so this is roughly three polls plus slack. Long enough that the graceful path is
# the one that normally runs; short enough that Stop still feels like a button.
_GRACEFUL_STOP_SECONDS = 30
_STOP_POLL_SECONDS = 3


def _instance_dir(bot_key: str) -> str:
    return f"C:\\trading\\algos\\markets\\fx\\instances\\{bot_key}"


# How long a thread root stays usable. A promote's stop-and-start is seconds; anything older
# is a leftover from a restart that never completed, and threading tomorrow's ONLINE under
# yesterday's deploy is worse than not threading it at all.
#
# 🔴 This is the `stop.request` lesson, and it is the ONE way this feature could be worse than
# no feature: a file left in an instance directory outlives the thing it describes. There it was
# a stale request stopping a healthy bot; here it is a stale id quietly mis-parenting every
# lifecycle message a bot ever sends. Two guards, and the expiry is the one that cannot be
# forgotten — the bot DELETES the file once it has used it, and ignores one this old regardless.
_ALERT_THREAD_TTL_SECONDS = 900


def _set_alert_thread(bot_key: str, message_id) -> None:
    """Tell the bot which message its next lifecycle alerts should reply to.

    The bot runs on the VPS and this runs on a laptop, so the id has to travel — and the
    instance directory is the channel those two already share (`stop.request`, `bot_state.json`,
    `review.json`). One extra file, written on the connection the promote is already using.

    ⚠ **Never raises and never blocks the promote.** A deploy that failed because a Telegram
    convenience could not be written would be a spectacularly bad trade. A missing file simply
    means the two replies arrive unthreaded, which is exactly today's behaviour.

    ⚠ **A message id of 0 or None is NOT written** — `send_telegram_id` returns 0 for "delivered
    but the id was unreadable", and writing that would ask the bot to reply to message zero.
    """
    if not message_id:
        return
    payload = json.dumps(
        {"message_id": int(message_id), "expires_at": _time.time() + _ALERT_THREAD_TTL_SECONDS}
    )
    # Over STDIN, not argv — the JSON carries braces and quotes, and `^`-escaping those through
    # cmd is the kind of quoting that works until the day a value changes shape. The same
    # one-liner-plus-stdin shape `_write_account_password` uses, minus the marker: this write is
    # a convenience and a caller must never learn about its failure by having the promote fail.
    try:
        subprocess.run(
            [
                "ssh",
                VPS_HOST,
                f'{_PYTHON_EXE} -c "import sys,pathlib;'
                f"pathlib.Path(r'{_instance_dir(bot_key)}')"
                f".joinpath('alert_thread.json').write_text(sys.stdin.read())\"",
            ],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
    except Exception as e:  # pragma: no cover - a dead box is already reported by the promote
        print(f"bots: could not write the alert thread for {bot_key}: {e}")


def _bot_is_running(bot_key: str) -> bool:
    """Is this bot's runner process alive on the VPS right now?

    ⚠ An unreadable process list answers **True**, so the caller escalates to a kill rather
    than reporting a stop that may not have happened. Of the two wrong answers here, "kill a
    process that was already gone" is harmless and "report a live trading bot as stopped" is not.
    """
    try:
        out = _ssh(
            f"wmic process where \"name='python.exe' and commandline like "
            f"'%--bot {bot_key}%'\" get processid 2>nul"
        )
    except Exception:
        return True
    return any(ch.isdigit() for ch in out)


def _kill_bot(bot_key: str) -> str:
    """Stop ONE bot — by ASKING first, and killing only if it does not go.

    🔴 **Why asking matters, and it is not politeness.** This used to be a bare
    `wmic ... call terminate`, i.e. a hard kill, so the bot never got to write its `shutdown`
    record — and the next startup dutifully reported *"the previous run ended WITHOUT a
    shutdown record: it was killed, it crashed, or the box went down."* That sentence is the
    **silent-death detector** (`algos/CLAUDE.md` → *The daily record*), and it was firing on
    every restart anybody performed deliberately. **An alarm that fires when you press the
    button is one you learn to scroll past**, and the thing it exists to catch is the one
    failure in this system that leaves no other trace. Aaron read exactly that chip on
    2026-08-07 and asked why a healthy bot was flagged.

    So: write `<instance>/stop.request`, wait for the process to go, and escalate to the kill
    only on a bot that ignored it (wedged, blocked in an MT5 call, or running code that predates
    the file). The escalation is not a fallback nobody exercises — it is the honest answer for a
    bot that cannot shut itself down, and the return value says which path ran.

    **Never `taskkill /f /im python.exe`.** That kills every Python process on the VPS: the
    trading bot, the Telegram bot, the MT5 backtest agent and the NT8 agent. It is how Stop
    took the whole box down, and on 2026-07-31 it is what killed the live bot — which then
    stayed dead for three days, because at the time nothing restarted it. It also silently
    breaks any in-flight lab backtest, since both agents are Python too.

    The bot key is already this repo's process identity — `monitor.is_running` matches on the
    same string, because `runner.py` is the entrypoint for EVERY live bot and the script name
    alone cannot tell two of them apart. Verified on the VPS 2026-08-04: this terminated the
    bot and left the Telegram bot and both agents running on their original PIDs.
    """
    steps = [_ssh(f"echo stop > {_instance_dir(bot_key)}\\stop.request")]

    waited = 0
    while waited < _GRACEFUL_STOP_SECONDS:
        _time.sleep(_STOP_POLL_SECONDS)
        waited += _STOP_POLL_SECONDS
        if not _bot_is_running(bot_key):
            steps.append(f"{bot_key} shut down cleanly after {waited}s")
            # ⚠ Remove the request even on the happy path. The bot clears it too, but a stop
            # file that outlives its stop would halt the NEXT start seconds after boot, and a
            # bot that will not stay up is a far worse failure than a slow Stop.
            steps.append(_ssh(f"del {_instance_dir(bot_key)}\\stop.request 2>nul"))
            return "\n".join(s for s in steps if s).strip()

    steps.append(f"{bot_key} did not stop within {_GRACEFUL_STOP_SECONDS}s — terminating")
    steps.append(
        _ssh(
            f"wmic process where \"name='python.exe' and commandline like '%--bot {bot_key}%'\" "
            f"call terminate 2>nul"
        )
    )
    steps.append(_ssh(f"del {_instance_dir(bot_key)}\\stop.request 2>nul"))
    return "\n".join(s for s in steps if s).strip()


def _stop_procs(clear_lock: bool = True) -> str:
    """Stop every registered bot, and nothing else. Returns combined SSH output.

    Iterates the BOT REGISTRY. It used to iterate `_SUPPRESS_KEYS` — the crash-alert map —
    which happened to hold the same keys and did not have to: a bot registered without a
    suppress entry was skipped by "Stop all N bots" **and the button reported success**,
    with the count on it coming from the registry the loop was not using.
    """
    outs = [_kill_bot(b.key) for b in _BOTS]
    if clear_lock:
        # Only meaningful once the bots are actually gone — a live bot re-creates it.
        outs.append(_ssh(f"del {_LOCK_PATH} 2>nul"))
    return "\n".join(o for o in outs if o).strip()


def _start_task() -> str:
    """Fire SYS_STARTUP scheduled task.  Returns SSH output."""
    return _ssh(f"schtasks /run /tn {_STARTUP_TN}")


@router.post("/start")
def start_bots():
    """Run the SYS_STARTUP scheduled task on the VPS."""
    try:
        out = _start_task()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    _notify_telegram(alert("▶️", "STARTING", "All bots", "Requested from the command center."))
    return {"status": "ok", "output": out}


@router.post("/stop")
def stop_bots():
    """Delete the MT5 lock file and kill all python.exe processes on the VPS."""
    try:
        for _b in _BOTS:
            _suppress_stop_alert(_b.key)
        out = _stop_procs()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    _notify_telegram(
        alert(
            "⏹",
            "STOPPED",
            "All bots",
            "Stopped from the command center. They will not come back on their own.",
        )
    )
    return {"status": "ok", "output": out}


@router.post("/restart")
def restart_bots():
    """Stop all bots, wait 3 s, then run SYS_STARTUP."""
    try:
        for _b in _BOTS:
            _suppress_stop_alert(_b.key)
        stop_out = _stop_procs()
        _time.sleep(3)
        start_out = _start_task()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    _notify_telegram(alert("🔄", "RESTARTING", "All bots", "Requested from the command center."))
    return {"status": "ok", "output": f"{stop_out}\n{start_out}".strip()}


# ── Per-bot control actions ───────────────────────────────────────────────────
#
# Routes registered AFTER the literal /start|stop|restart|emergency paths so
# FastAPI matches the literals first (no ambiguity).


def _resolve_bot(ref: str) -> tuple[str, str]:
    """Return `(task_name, bot_key)` for a **bot key or a display name**, else 404.

    The key is tried FIRST and is the identifier new callers should use. Every route here
    was keyed on the DISPLAY NAME — a label, chosen for a human, and therefore the one field
    somebody will eventually change: renaming "MPC SOS Fade" would have broken every
    bookmark, the Configure tab's `?bot=` selection, and any script anyone had written,
    while the bot itself was untouched. The key is what identifies the process on the VPS
    (`runner.py --bot <key>`), so it is already the stable name; it just was not reachable
    from here.

    Display names keep working, and deliberately so: the frontend renders bots off
    `BotStatus.name` and there is no version of this worth a flag day. The rule for new code
    is simply "pass the key".

    ⚠ Key before name, never the other way round. If a future bot's display name happened to
    equal another bot's key, name-first would silently route one bot's Stop to the other —
    and `test_bot_registry.py` cannot rule that out, because the two namespaces are free.
    """
    reg = _BY_KEY.get(ref)
    if reg is None:
        reg = next((b for b in _BOTS if b.display.lower() == ref.lower()), None)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"Bot '{ref}' not found")
    return reg.task, reg.key


_COORDINATOR = r"C:\trading\algos\bots\startup_coordinator.py"
# WMI does not inherit the user's PATH — must use the full Python executable path.
_PYTHON_EXE = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"


# Use wmic process call create so startup_coordinator runs under WMI — not
# under the SSH job object — meaning the bot it spawns survives when SSH closes.
# Direct SSH call kills children via job-object teardown despite CREATE_NEW_PROCESS_GROUP.
def _launch_bot(bot_key: str) -> str:
    """Fire startup_coordinator.py --bot <key> via WMI and return wmic output."""
    return _ssh(f'wmic process call create "{_PYTHON_EXE} {_COORDINATOR} --bot {bot_key}" 2>nul')


# ── Which version is deployed, and promoting a new one ────────────────────────
#
# Aaron's requirement: "I wanna see the version of the bot that is running, so I can know
# exactly what version, and you could know too, so we could look at configs or parameters
# from that version so we're not confused."
#
# Everything here reads the VPS, never the local repo. The local repo is where NEW versions
# are built; it says nothing about what is deployed, and until 2026-08-03 the two were the
# same files — which is exactly the confusion being removed.

_VPS_REPO = r"C:\trading"  # `_VPS_INSTANCES` is defined with the registry, which needs it
_PROMOTE_PY = r"C:\trading\algos\tools\promote.py"


def _bot_state_path(bot_key: str) -> str | None:
    """The VPS `bot_state.json` holding this bot's entry, resolved from the SAME registry the
    snapshot fetch uses.

    `get_bot_version` used to name `state_mpc_sos_fade` outright, so every OTHER bot got a
    blank `running_hash` — which reads as "the live process agrees with the deployment
    record" and makes the *restart pending* warning permanently impossible to trigger. The
    fleet strip on the Configure tab then reports a confident **0 restart pending** across a
    fleet it cannot see, which is worse than showing nothing.
    """
    for section, keys in _BOT_STATE_SECTIONS:
        if bot_key in keys:
            return _BOT_STATE_PATHS.get(section)
    return None


def _deployed_json(bot_key: str) -> dict:
    raw = _ssh(f"type {_VPS_INSTANCES}\\{bot_key}\\deployed.json 2>nul")
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


@router.get("/{bot_name}/version", response_model=BotDeployedVersion)
def get_bot_version(bot_name: str):
    """What this bot is actually running, plus how far the repo has moved past it."""
    _, bot_key = _resolve_bot(bot_name)
    rec = _deployed_json(bot_key)

    # ONE round trip for every fact on this card. `--show` re-hashes the snapshot on disk,
    # which is the tamper check: the record can only be trusted if the files still match it.
    #
    # The bot's own `bot_state.json` rides along on the same connection. It used to come
    # from a second `_fetch_vps_snapshot()` — a two-command fleet-wide fetch (every python
    # process, every scheduled task, every bot's state file) issued to read ONE string.
    # MEASURED before: /version 8.5s, of which the snapshot was ~5s; the Configure tab's
    # fleet strip fires one of these per bot, so the waste multiplied by the fleet.
    state_path = _bot_state_path(bot_key)
    cmd = (
        f"cd {_VPS_REPO} & git rev-parse --short HEAD"
        f" & echo. & echo ===AHEAD=== & git rev-list --count {rec.get('promoted_commit') or 'HEAD'}..HEAD"
        f" & echo. & echo ===SHOW=== & {_PYTHON_EXE} {_PROMOTE_PY} --bot {bot_key} --show 2>nul"
    )
    if state_path:
        # `echo.` before the marker for the reason `_fetch_vps_snapshot` documents: `type`
        # emits no trailing newline, so a marker after it arrives welded to the previous
        # section and `_parse_sections` silently merges the two.
        cmd += f" & echo. & echo ===STATE=== & type {state_path} 2>nul"

    raw = _ssh(cmd)
    parts = _parse_sections(raw, "head")
    try:
        ahead = int(parts.get("ahead", "0").strip().splitlines()[-1])
    except (ValueError, IndexError):
        ahead = 0

    # The live PROCESS's own report. If this disagrees with deployed.json, a promote has
    # happened since the bot started and it is still running the OLD code — the single most
    # misleading state this page can be in, so it is surfaced rather than reconciled away.
    running_hash = ""
    try:
        state = json.loads(parts.get("state", "").strip() or "{}")
        running_hash = (state.get(bot_key) or {}).get("source_hash", "") or ""
    except Exception:
        pass

    # Settings config.json states differently from what was deployed. Not an error — the
    # runtime panel writes exec_risk_pct to config.json on a running bot — but it is the gap
    # between "what the file says" and "what is trading", which is the whole point of this.
    drift: list[str] = []
    deployed_params = rec.get("strategy_params") or {}
    # Read once and shared with the version comparison below, which needs to know which
    # settings this bot PINS — a default that moved in the repo cannot reach a bot whose
    # config states a value for it.
    current_params: dict = {}
    try:
        current_params = _read_instance_config(bot_key).get("strategy_params", {}) or {}
    except HTTPException:
        pass
    if deployed_params:
        try:
            current = current_params
            # Compared over the UNION of both key sets, through a sentinel.
            #
            # The old form was `deployed_params.get(k, v) != v` over `current` alone, which
            # is blind in both directions and blind hardest in the case that matters: a
            # setting ADDED to config.json since the promote defaults to its own value and
            # compares equal, so a knob the deployment never heard of reports no drift. A
            # setting REMOVED from config.json was never looked at either, because only
            # `current` was iterated.
            #
            # The sentinel rather than `.get(k)`: a param whose value is legitimately `None`
            # must not read as absent. Same rule as `mt5_link` — missing and null are
            # different answers.
            missing = object()
            keys = set(deployed_params) | set(current)
            drift = sorted(
                k for k in keys if deployed_params.get(k, missing) != current.get(k, missing)
            )
        except HTTPException:
            pass

    # How far behind the deployment is, in a number a human can act on. Computed against the
    # LOCAL repo — this backend and the backtester run the same working tree, so "the version
    # in my backtester" is a question only this machine can answer. It is best-effort: the
    # version card is still worth rendering when git cannot be read.
    try:
        comparison = BotVersionCompare(
            **bot_versions.compare(
                rec.get("strategy_package", ""),
                rec.get("promoted_commit", ""),
                current_params,
            )
        )
    except Exception:
        comparison = None

    return BotDeployedVersion(
        frozen=bool(rec),
        hash=rec.get("strategy_source_hash", ""),
        commit=rec.get("promoted_commit", ""),
        promoted_at=rec.get("promoted_at", ""),
        strategy_package=rec.get("strategy_package", ""),
        strategy_class=rec.get("strategy_class", ""),
        # `None`, not 0 — a deployment made before promote.py stamped a real version has no
        # answer here, and 0 is a version somebody could genuinely be on.
        strategy_version=rec.get("strategy_version"),
        files=rec.get("files", 0),
        params=deployed_params,
        repo_commit=parts.get("head", "").strip().splitlines()[0] if parts.get("head") else "",
        commits_ahead=ahead,
        snapshot_ok="SNAPSHOT MODIFIED" not in parts.get("show", ""),
        running_hash=running_hash,
        params_drift=drift,
        compare=comparison,
    )


_PROMOTE_OK = "===PROMOTE_OK==="
_PROMOTE_FAIL = "===PROMOTE_FAILED==="
# `promote.py` prints `##VERSIONS <from> <to>` — the version the bot IS on and the one this
# deploy moves it to, each a bare int or `?`. Parsed rather than scraped out of the prose for
# the reason the OK/FAIL markers exist: a reworded `print` must not change what this reads.
_VERSION_MARK = "##VERSIONS"
_PROMOTE_UNKNOWN = (
    "\n⚠ promote.py did not report an exit status. Nothing here can say whether it "
    "deployed — check the VPS before assuming either way."
)


def _vlabel(n: int | None) -> str:
    """`v165`, or `v?`. **Never `v0` for an unknown** — 0 is a version somebody could be on,
    and it is the exact value that misreported this field for its whole life."""
    return "v?" if n is None else f"v{n}"


def _parse_versions(out: str) -> tuple[int | None, int | None]:
    """The `##VERSIONS <from> <to>` line promote.py prints, as two ints.

    ⚠ **`None` on every side that could not be counted, and on a missing line entirely** — a
    deployment made before the marker existed, or a `rev-list` the VPS could not run. The
    caller words the message around what it has rather than printing `v0`, which is the value
    that has been misreporting this field since it was declared.
    """
    for line in reversed(out.splitlines()):
        if not line.startswith(_VERSION_MARK):
            continue
        parts = line.split()
        if len(parts) != 3:
            return None, None

        def num(tok: str) -> int | None:
            try:
                return int(tok)
            except ValueError:
                return None

        return num(parts[1]), num(parts[2])
    return None, None


def _run_promote(
    bot_key: str, *, dry_run: bool, pull: bool, allow_dirty: bool
) -> tuple[bool | None, str, tuple[int | None, int | None]]:
    """Run promote.py on the VPS. Returns `(ok, output, versions)`; `ok` is **None** when the
    run did not report one, which is a third answer and never rounded to False silently.

    🔴 The result used to be sniffed out of the PROSE — `"pinned" in out` for a promote,
    `"dry run" in out` for a preview. `promote.py` has always returned a real exit code (0
    on success, 1 on a dirty tree / a snapshot that does not import / a missing source
    tree), and it was being thrown away in favour of a substring: rewording one `print`
    silently flips the verdict, and a FAILURE whose message happens to contain the word
    reads as a success. On the one action in this router that changes what a bot trades.
    """
    steps = []
    if pull:
        steps.append(f"cd {_VPS_REPO} & git pull origin main")
    flags = " --dry-run" if dry_run else ""
    flags += " --allow-dirty" if allow_dirty else ""
    steps.append(f"{_PYTHON_EXE} {_PROMOTE_PY} --bot {bot_key}{flags}")
    # `if errorlevel 1`, never `echo %errorlevel%`: cmd expands `%VAR%` at PARSE time, so on
    # a single command line that prints the code from BEFORE promote.py ran — which is the
    # trap that makes an exit-code check look like it works and always answer 0.
    steps.append(f"if errorlevel 1 (echo {_PROMOTE_FAIL}) else (echo {_PROMOTE_OK})")

    out = _ssh(" & ".join(steps))
    if _PROMOTE_FAIL in out:
        ok: bool | None = False
    elif _PROMOTE_OK in out:
        ok = True
    else:
        ok = None
    clean = "\n".join(
        ln
        for ln in out.splitlines()
        if _PROMOTE_OK not in ln and _PROMOTE_FAIL not in ln and not ln.startswith(_VERSION_MARK)
    ).strip()
    return ok, clean, _parse_versions(out)


@router.post("/{bot_name}/promote/preview", response_model=BotPromoteResult)
def preview_bot_promote(bot_name: str, req: BotPromoteRequest):
    """Stage and verify a promote WITHOUT deploying it. The running bot is untouched.

    A real preview, not a file count: it copies the trees, imports the strategy out of the
    copy, builds it with the promoted parameters, and reports which settings would change —
    then deletes the staging. Those are the two questions worth answering before deploying
    ("does it import", "what changes"), and neither can be answered without staging.
    """
    _, bot_key = _resolve_bot(bot_name)
    try:
        ok, out, _ = _run_promote(bot_key, dry_run=True, pull=req.pull, allow_dirty=req.allow_dirty)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    if ok is None:
        return BotPromoteResult(ok=False, output=out + _PROMOTE_UNKNOWN)
    return BotPromoteResult(ok=ok, output=out)


@router.post("/{bot_name}/promote", response_model=BotPromoteResult)
def promote_bot(bot_name: str, req: BotPromoteRequest):
    """Deploy the current VPS code to this bot, then restart it onto the new version.

    This is the ONLY action that changes what a bot trades. A pull does not, a restart does
    not, a lab experiment does not — see `algos/live/version.py`.
    """
    _, bot_key = _resolve_bot(bot_name)
    try:
        reported, out, versions = _run_promote(
            bot_key, dry_run=False, pull=req.pull, allow_dirty=req.allow_dirty
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")

    # An unreported result is NOT a success, and it is not a plain failure either — the
    # promote may have deployed. It must not restart the bot on a maybe, and it must not
    # send the "promoted" alert either, so it takes the false branch with the doubt spelled
    # out in the output rather than resolved in silence.
    if reported is None:
        return BotPromoteResult(ok=False, output=out + _PROMOTE_UNKNOWN, restarted=False)

    ok = reported
    restarted = False
    if ok:
        # 🔴 SENT BEFORE THE RESTART, and the ordering is the feature rather than a detail.
        # A deploy produces THREE messages from TWO machines — this one, then the bot's own
        # STOPPED and ONLINE — and Aaron read them as three unrelated events. Threading them
        # needs a ROOT, and the root has to exist before the thing it is the root of: the bot
        # writes STOPPED the moment it notices its stop file, seconds from here.
        #
        # ⚠ Nothing is lost by moving it. `restarted` was never a MEASUREMENT — it was set to
        # `ok and req.restart` unconditionally after the kill — so the old placement bought no
        # extra knowledge, and the wording now states the INTENT ("restarting it now"), which
        # the two replies then confirm or fail to.
        was_v, now_v = versions
        moved = (
            f"{_vlabel(was_v)} → {_vlabel(now_v)}"
            if (was_v is not None or now_v is not None)
            else ""
        )
        root = _notify_telegram(
            alert(
                "📦",
                "PROMOTED",
                _KEY_DISPLAY.get(bot_key, bot_key),
                joined([moved, "deployed"]) or "The new code is deployed.",
                "Restarting it now." if req.restart else "Restart it to pick the new version up.",
            )
        )
        if req.restart:
            _set_alert_thread(bot_key, root)
    if ok and req.restart:
        # Kill it and let SYS_MONITOR bring it back — that path is exercised every time the
        # watchdog fires, so it is the one most likely to work. The suppress key is NOT
        # written: this stop is meant to be undone, immediately.
        _kill_bot(bot_key)
        _time.sleep(2)
        _launch_bot(bot_key)
        restarted = True
    return BotPromoteResult(ok=ok, output=out, restarted=restarted)


# ── Reading and changing a bot's settings ─────────────────────────────────────
#
# 🔴 DELETED 2026-08-04: `GET /{bot}/config`, `PATCH /{bot}/config`, `PATCH /{bot}/caps`
# (recover with `git show 407d716^:command-center/backend/routers/bots.py`). All three had
# NO consumer — their frontend hooks existed and nothing rendered them — and two of them
# restarted a LIVE TRADING BOT to do it. That is a hazard sitting on the API with no page
# in front of it to notice.
#
#   * `PATCH /config` wrote ARBITRARY sections into the instance config — including
#     `strategy` — then committed, pushed, pulled and restarted the bot into them. It went
#     straight around `bot_params.RUNTIME_EDITABLE`, the allowlist whose entire job is to
#     say which lever may move under a running bot. A backdoor around a safety rule is
#     worse than no rule, because the rule is what everybody reads.
#   * `PATCH /caps` did the same restart to write `thresholds.json` for `SYS_PNLTRACKER`,
#     a task that is DISABLED, plus a loop over `_CAP_CONFIG_FIELDS` — which is empty by
#     design, because `algos/live/` has no daily-cap or weekly-cap field to write. Every
#     restart it caused was for nothing. **Its whole subject is gone now: the tracker, the
#     task and `thresholds.json` were deleted 2026-08-05 (see `_SYS_DISPLAY_NAMES`).**
#   * `GET /config` is `GET /params` with fewer labels.
#
# What replaced them, and why each is the safer shape: `/params` reads (and never writes),
# and `/runtime` writes ONLY the reloadable set and **does not restart** — the bot re-reads
# its own config and applies the change while FLAT.


@router.get("/{bot_name}/params", response_model=BotParamsView)
def get_bot_params(bot_name: str):
    """Everything this bot is configured with — what it trades, on which account, at which
    version, and with which parameters. Read-only.

    This is the answer to "what is that bot actually running?", which previously required
    an SSH session and a JSON file. Labels come from the LAB's scanned schema for the same
    strategy, so a knob is described identically here and in the Run modal.
    """
    _, bot_key = _resolve_bot(bot_name)
    data = _read_instance_config(bot_key)
    section = _BOT_INSTANCE_MAP[bot_key]["section"]

    # Cosmetic only — a strategy the lab has never scanned still renders every parameter
    # under its raw field name rather than dropping it.
    schema = None
    try:
        row = lab_db.get_strategy(data.get("strategy_package", ""))
        schema = (row or {}).get("param_schema")
    except Exception:
        pass

    return BotParamsView(**bot_params.build_view(bot_key, data, schema, section))


@router.patch("/{bot_name}/runtime")
def save_bot_runtime(bot_name: str, update: BotRuntimeUpdate):
    """Change the levers that are allowed to move on a running bot.

    Today that is `exec_risk_pct` alone — see `services/bot_params.py` for why the strategy
    parameters are deliberately not in this set.

    **The bot is NOT restarted.** It re-reads its own config at the top of a loop and
    applies the change only while FLAT (`algos/live/runner.py::_maybe_reload_runtime`), so
    a resize can never land mid-trade and leave a position being managed by rules that
    would not have opened it. That is also why this endpoint does not need to know whether
    a trade is open — the bot does, and it is the one holding the position.
    """
    _, bot_key = _resolve_bot(bot_name)
    info = _BOT_INSTANCE_MAP[bot_key]
    section = info["section"]

    try:
        values = bot_params.validate_runtime(update.values)
    except bot_params.RuntimeUpdateError as e:
        raise HTTPException(status_code=400, detail=str(e))

    data = _read_instance_config(bot_key)
    params = data.setdefault(section, {})
    before = {k: params.get(k) for k in values}
    if all(params.get(k) == v for k, v in values.items()):
        return {"status": "ok", "changed": False, "detail": "Already at those values."}

    params.update(values)
    _write_instance_config(bot_key, data)

    changed = ", ".join(f"{k} {before[k]} → {v}" for k, v in values.items())
    if not update.deploy:
        return {"status": "ok", "changed": True, "deployed": False, "detail": changed}

    try:
        _git_commit_push(
            info["path"],
            f"runtime: {bot_name} — {changed} [command center]",
            "runtime strategy params written from the Bots page; an operational "
            "deployment, and the fields are named in the message",
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"git push failed: {e.stderr.decode(errors='replace')}"
        )
    try:
        out = _ssh("cd C:\\trading && git pull origin main")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")

    display = _KEY_DISPLAY.get(bot_key, bot_key)
    # Plain text, no Markdown: bot keys and param names are full of underscores, and
    # Telegram drops the WHOLE message on an unbalanced entity rather than escaping it.
    _notify_telegram(
        alert(
            "⚙️",
            "SETTINGS CHANGED",
            display,
            changed,
            "It will apply at the next bar the bot is flat.",
        )
    )
    return {"status": "ok", "changed": True, "deployed": True, "detail": changed, "output": out}


@router.post("/{bot_name}/start")
def start_bot(bot_name: str):
    """Launch a single bot via startup_coordinator.py --bot <key> (via WMI).
    Individual BOT_* scheduled tasks are Disabled — schtasks /run does nothing.
    """
    _, bot_key = _resolve_bot(bot_name)
    try:
        out = _launch_bot(bot_key)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(alert("▶️", "STARTING", display, "Requested from the command center."))
    return {"status": "ok", "output": out}


@router.post("/{bot_name}/stop")
def stop_bot(bot_name: str):
    """Kill only the python.exe process whose commandline contains this bot's key."""
    _, bot_key = _resolve_bot(bot_name)
    try:
        _suppress_stop_alert(bot_key)  # must run before kill so monitor skips crash alert
        out = _kill_bot(bot_key)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(
        alert(
            "⏹",
            "STOPPED",
            display,
            "Stopped from the command center. It will not come back on its own.",
        )
    )
    return {"status": "ok", "output": out}


@router.post("/{bot_name}/restart")
def restart_bot(bot_name: str):
    """Kill this bot's process, wait 3 s, then relaunch via startup_coordinator --bot."""
    _, bot_key = _resolve_bot(bot_name)
    try:
        _suppress_stop_alert(bot_key)  # must run before kill so monitor skips crash alert
        stop_out = _kill_bot(bot_key)
        _time.sleep(3)
        start_out = _launch_bot(bot_key)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(alert("🔄", "RESTARTING", display, "Requested from the command center."))
    return {"status": "ok", "output": f"{stop_out}\n{start_out}".strip()}
