"""Deploy jobs kept ON DISK, so a backend restart mid-deploy is REPORTED instead of forgotten.

🔴 **THE FAILURE (2026-09-24).** Jobs lived in memory only. The backend restarts on any `.py` edit
under `backend/` (`uvicorn --reload`), and one did mid-deploy of the LIVE SOS Fade bot to v394: the
job, its steps and the fact that a deploy had ever been asked for all vanished. The page went back
to offering Deploy as if nothing had happened, and the bot stayed on v365 with nothing anywhere
saying so. The old note here — *"a restart loses the progress readout, never the deploy"* — was
wrong: the deploy runs from THIS process's thread, so it dies with it.

**Now every change to a job is written here, and on start-up any job still marked running is
closed as `failed` with the step it was on and what that means for the bot** — the same per-step
wording a timeout gets, because the question the reader has is the same: did it land or not?

⚠ **Written whole each time (`.tmp` → `os.replace`)** — the backend's rule for any file another
read may catch half-written.
⚠ **Off when the path is empty** — the test suite sets `CC_PROMOTE_JOBS_FILE=""` so parallel
workers never share, or read, the real file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "promote_jobs.json"


def path() -> Path | None:
    raw = os.environ.get("CC_PROMOTE_JOBS_FILE")
    if raw is None:
        return _DEFAULT
    return Path(raw) if raw else None


def _plain(o):
    dump = getattr(o, "model_dump", None)
    if dump is None:
        raise TypeError(f"cannot save a {type(o).__name__}")
    return dump()


def save(jobs: dict[str, dict], where: Path | None = None) -> None:
    """Write every job. Never raises — a readout that cannot be saved must not fail the deploy
    it is reporting on."""
    target = where or path()
    if target is None:
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(jobs, default=_plain), encoding="utf-8")
        os.replace(tmp, target)
    except (OSError, TypeError, ValueError):
        pass


def load(interrupted: callable, where: Path | None = None) -> dict[str, dict]:
    """Every saved job, with any still `running` closed as failed.

    `interrupted(stage)` words what an interruption at that step means for the bot; `stage` is
    the step that was active, or `None` if none had started. Unreadable → no jobs, which only
    loses a readout."""
    source = where or path()
    if source is None:
        return {}
    try:
        jobs = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(jobs, dict):
        return {}
    for job in jobs.values():
        if job.get("status") != "running":
            continue
        stages = job.get("stages", {})
        active = next((k for k, s in stages.items() if s.get("state") == "active"), None)
        # The last moment the job is KNOWN to have been alive — never the restart's own time,
        # which would stretch the job's duration over however long the backend was down.
        ended = max(
            [job.get("started") or 0]
            + [t for s in stages.values() for t in (s.get("started"), s.get("ended")) if t]
        )
        for s in stages.values():
            if s.get("state") == "active":
                s["state"], s["ended"] = "failed", s.get("started")
            elif s.get("state") == "pending":
                s["state"] = "skipped"
        job["status"], job["error"], job["ended"] = "failed", interrupted(active), ended
    return jobs
