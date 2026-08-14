"""The dev server's uvicorn invocation carries the flags it cannot run safely without.

This is a grep test over `start.sh`, and it exists because the thing it guards is INVISIBLE when
it breaks. Without `--timeout-graceful-shutdown` a reload can leave the app dead with port 8000
still bound: the reloader asks the worker to stop and waits for it, the worker's own shutdown waits
for open connections to close, and the Vite dev server holds a keep-alive POOL to that port — an
idle keep-alive socket never closes on its own, so the wait never ends. Measured on this box:
19 held sockets, `touch main.py`, and /health went from 200 in 19ms to a hard timeout with the same
worker PID alive at 0% CPU twenty seconds later. Nothing logs it and nothing recovers it.

⚠ Every assertion below is paired with a check that the grep MATCHED SOMETHING. A grep test that
finds nothing passes for ever, which is how a renamed file turns a guard into decoration — the same
vacuous-check trap the notification-routing sweeps and the Stress Test browser suite both hit.
"""

from pathlib import Path

START_SH = Path(__file__).resolve().parents[2] / "start.sh"


def _uvicorn_line() -> str:
    lines = [
        ln.strip()
        for ln in START_SH.read_text().splitlines()
        if ln.strip().startswith("uvicorn ") and "main:app" in ln
    ]
    # Non-vacuity: if start.sh stops launching uvicorn this way, fail here rather than
    # silently asserting over an empty string.
    assert len(lines) == 1, (
        f"expected exactly one uvicorn launch line in start.sh, found {len(lines)}"
    )
    return lines[0]


def test_start_sh_exists():
    assert START_SH.is_file(), f"{START_SH} is the file every other check here reads"


def test_dev_server_bounds_its_graceful_shutdown():
    """Without a ceiling, one reload can wedge the app with the port still bound."""
    line = _uvicorn_line()
    assert "--timeout-graceful-shutdown" in line, (
        "start.sh must bound uvicorn's graceful shutdown — an idle keep-alive socket from the "
        "Vite proxy otherwise blocks the worker's exit for ever and the reloader never replaces it"
    )


def test_the_shutdown_ceiling_clears_the_slowest_request():
    """A ceiling under the slowest real request would cut it off, which is its own defect.

    The slowest measured request on this app is a cold ChartSpec build at 7.6s.
    """
    parts = _uvicorn_line().split()
    idx = parts.index("--timeout-graceful-shutdown")
    seconds = int(parts[idx + 1])
    assert 8 <= seconds <= 60, (
        f"graceful shutdown ceiling is {seconds}s — it must clear the 7.6s cold ChartSpec build "
        "and still be short enough that a wedged reload is noticed as a pause, not a hang"
    )


def test_reload_is_still_on():
    """The pairing is the point: this whole failure only exists because --reload is used."""
    assert "--reload" in _uvicorn_line()
