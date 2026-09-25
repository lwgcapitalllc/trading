"""Deploy jobs, one FILE each — the record a deploy's own process writes and the backend reads.

🔴 **WHY A DEPLOY RUNS IN ITS OWN PROCESS (2026-09-24).** A deploy ran on a thread inside the
backend, and the backend restarts on any `.py` edit under `backend/` (`uvicorn --reload`). It did,
twice in one day, mid-deploy: once on the LIVE SOS Fade bot (the deploy to v394 simply never
happened) and once on demo Realign (cut off during its pull). A deploy stops and starts a live
bot, so it must never die halfway because somebody saved a file. It now runs in a separate process
(`services/promote_worker.py`, started in its own session so a restart of the backend does not
take it down), and this file is how the two talk.

**One file per job, and one writer at a time.** The backend writes the file ONCE, when it creates
the job; from then on only the job's own process writes it, until it ends. The backend writes a
running job again only when that process is provably gone (`settle_if_dead`). So there is no
read-modify-write of a shared file across processes to lose an update in.

**A job is RUNNING while its process is alive** (`alive`). Not the status field alone: a job whose
process died — the machine rebooted, the process crashed — still says `running` on disk, and would
otherwise hold its bot locked for ever. Such a job is closed as failed at the step it was on.

⚠ **Off when the folder is empty** (`CC_PROMOTE_JOBS_DIR=""`) — nothing is saved and nothing read.
The test suite points it at a per-test temporary folder instead, so parallel workers never share.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "promote_jobs"

# A job whose process has not written its pid yet is taken as alive for this long after it was
# created — the process is still importing. Past it, a pid-less running job is a launch that died.
LAUNCH_GRACE_S = 90

# The words in the process's command line that prove a pid is STILL this job's process and not an
# unrelated one that inherited the number (`alive`).
WORKER_MARK = "promote_worker"


def folder() -> Path | None:
    raw = os.environ.get("CC_PROMOTE_JOBS_DIR")
    if raw is None:
        return _DEFAULT
    return Path(raw) if raw else None


def _plain(o):
    dump = getattr(o, "model_dump", None)
    if dump is None:
        raise TypeError(f"cannot save a {type(o).__name__}")
    return dump()


def _path(job_id: str) -> Path | None:
    base = folder()
    return None if base is None else base / f"{job_id}.json"


def log_path(job_id: str) -> Path | None:
    """Where the job's process writes its own output — read when a deploy dies unexplained."""
    base = folder()
    return None if base is None else base / f"{job_id}.log"


def write(job: dict) -> None:
    """Write one job whole (`.tmp` → `os.replace`). Never raises: a record that cannot be written
    must not fail the deploy it is recording."""
    target = _path(job["job_id"])
    if target is None:
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, default=_plain), encoding="utf-8")
        os.replace(tmp, target)
    except (OSError, TypeError, ValueError):
        pass


def read(job_id: str) -> dict | None:
    target = _path(job_id)
    if target is None:
        return None
    try:
        job = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return job if isinstance(job, dict) else None


def all_jobs() -> list[dict]:
    base = folder()
    if base is None or not base.is_dir():
        return []
    out = []
    for f in base.glob("*.json"):
        job = read(f.stem)
        if job is not None:
            out.append(job)
    return out


def _pid_is_worker(pid: int) -> bool:
    """Is `pid` alive AND still a deploy process? A pid is reused by the system once its process
    ends, so being alive alone could be a stranger holding the number."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # alive, owned by someone else — the command line decides
    except OSError:
        return False
    try:
        cmd = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return True  # could not ask; the pid is alive — never free a bot on a guess
    return WORKER_MARK in cmd


def alive(job: dict, now: float | None = None) -> bool:
    """Is this job still running — its status says so AND its process is still there?"""
    if job.get("status") != "running":
        return False
    pid = job.get("pid")
    if pid is None:
        return ((now or time.time()) - (job.get("started") or 0)) < LAUNCH_GRACE_S
    return _pid_is_worker(int(pid))


def close_dead(job: dict, reason: Callable[[str | None], str]) -> dict:
    """Close a job whose process is gone as failed, at the step it was on. `reason(stage)` words
    what that means for the bot. Returns the job as closed."""
    stages = job.get("stages", {})
    active = next((k for k, s in stages.items() if s.get("state") == "active"), None)
    # The last moment the job is KNOWN to have been alive — never now, which would stretch its
    # duration over however long nobody looked.
    ended = max(
        [job.get("started") or 0]
        + [t for s in stages.values() for t in (s.get("started"), s.get("ended")) if t]
    )
    for s in stages.values():
        if s.get("state") == "active":
            s["state"], s["ended"] = "failed", s.get("started")
        elif s.get("state") == "pending":
            s["state"] = "skipped"
    job["status"], job["error"], job["ended"] = "failed", reason(active), ended
    return job


def settle_if_dead(job: dict, reason: Callable[[str | None], str]) -> dict:
    """The job as it really stands: a `running` job whose process is gone is closed and written
    back. Safe to write, because a dead process can no longer write it."""
    if job.get("status") == "running" and not alive(job):
        job = close_dead(job, reason)
        write(job)
    return job


def running_bots(reason: Callable[[str | None], str]) -> dict[str, str]:
    """{bot key: "deploying"} for every job whose process is still at work — the claim a deploy
    holds on its bot, read off disk so it outlives a restart of the backend."""
    out: dict[str, str] = {}
    for job in all_jobs():
        if (
            job.get("status") == "running"
            and settle_if_dead(job, reason).get("status") == "running"
        ):
            out[job["bot"]] = "deploying"
    return out


def latest_for(bot_key: str, reason: Callable[[str | None], str]) -> dict | None:
    mine = [j for j in all_jobs() if j.get("bot") == bot_key]
    if not mine:
        return None
    return settle_if_dead(max(mine, key=lambda j: j.get("started") or 0), reason)


def prune(cap: int) -> None:
    """Keep at most `cap` jobs: the OLDEST finished ones go first, a running one never does."""
    jobs = all_jobs()
    finished = sorted(
        (j for j in jobs if j.get("status") != "running"), key=lambda j: j.get("started") or 0
    )
    extra = len(jobs) - cap
    for j in finished[: max(0, extra)]:
        for p in (_path(j["job_id"]), log_path(j["job_id"])):
            try:
                if p is not None:
                    p.unlink()
            except OSError:
                pass
