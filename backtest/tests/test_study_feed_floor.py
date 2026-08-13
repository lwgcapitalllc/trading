"""The cache-version guard on the three clock-based study tools is a FLOOR, not an equality.

`killzone_profile.py`, `killzone_sweep.py` and `h4_sweep_profile.py` all do session
arithmetic in New York time, so they refuse a cache written in the broker-local-timestamp
era (feed_version 1) rather than report a plausible-looking lie. That instinct is right and
must stay.

🔴 What is tested here is the shape of the comparison, because all three shipped it as
`if version != 2` — an equality — and were therefore BRICKED the day `FEED_VERSION` went to
3. v2 → v3 added the VOLUME column and moved no timestamp (see `backtest/data/cache.py`),
and these tools read price and the clock only, so v3 is strictly better input than the v2
they demanded. Three studies sat unrunnable, and their refusal message blamed broker-local
timestamps — pointing the reader at a 186k-bar re-pull to fix one character.

⚠ These tests were watched RED before being committed. Mutating `<` back to `!=` in either
tool turns exactly the v3 case red and leaves v1, v2 and the missing-key case green, which
is the failure the bug actually produced. Mutating the guard away entirely turns the v1 and
missing-key cases red. Neither case can pass vacuously: each asserts a specific verdict, so
a guard that always refused and a guard that never refused both fail.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load(name: str):
    """Load a tool by path, REGISTERED in sys.modules before it executes.

    The registration is not tidiness: `h4_sweep_profile` defines dataclasses, and
    dataclasses resolves a string annotation through `sys.modules[cls.__module__]`. An
    unregistered module makes that lookup return None and the import dies in the stdlib,
    which reads as a failure of the thing under test rather than of the loader.
    """
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub_cache(tmp_path: Path, tf: str, meta: dict | None) -> Path:
    """A cache dir holding one syntactically valid bar file and the sidecar under test.

    The bars are deliberately minimal: the guard must fire before any of them is parsed,
    so a tool that reached the CSV at all would fail on the content rather than pass.
    """
    (tmp_path / f"XAUUSD__{tf}.csv").write_text(
        "time,open,high,low,close\n2026-01-02 10:00:00,2000,2001,1999,2000.5\n"
    )
    if meta is not None:
        (tmp_path / f"XAUUSD__{tf}.meta.json").write_text(json.dumps(meta))
    return tmp_path


# (feed_version written to the sidecar, must the tool refuse it, why)
_CASES = [
    (1, True, "broker-local timestamp era — every session boundary would be wrong"),
    (2, False, "the era the original pin demanded"),
    (3, False, "v3 added volume and moved no timestamp"),
    (4, False, "a future bump must not brick a clock-only study again"),
]


@pytest.mark.parametrize("tool,fn,tf", [
    ("killzone_profile", "load_days", "M15"),
    ("h4_sweep_profile", "load_bars", "H4"),
])
@pytest.mark.parametrize("version,must_refuse,why", _CASES)
def test_the_version_guard_is_a_floor(tmp_path, tool, fn, tf, version, must_refuse, why):
    mod = _load(tool)
    mod.CACHE = _stub_cache(tmp_path, tf, {"feed_version": version, "has_volume": version >= 3})

    kwargs = {"start": None, "end": None} if tool == "killzone_profile" else {}
    try:
        getattr(mod, fn)("XAUUSD", tf, **kwargs)
        refused = False
    except SystemExit:
        refused = True

    assert refused is must_refuse, (
        f"{tool} feed_version {version}: expected "
        f"{'a refusal' if must_refuse else 'to run'} — {why}"
    )


@pytest.mark.parametrize("tool,fn,tf", [
    ("killzone_profile", "load_days", "M15"),
    ("h4_sweep_profile", "load_bars", "H4"),
])
def test_a_sidecar_with_no_version_is_treated_as_the_version_1_era(tmp_path, tool, fn, tf):
    """A sidecar predating the key is a v1-era file, the same default `cache.py` applies.

    Read as `.get("feed_version")` with no default it lands as None, and `None < 2` raises
    a TypeError instead of refusing — a crash where a diagnostic belongs.
    """
    mod = _load(tool)
    mod.CACHE = _stub_cache(tmp_path, tf, {"has_volume": False})

    kwargs = {"start": None, "end": None} if tool == "killzone_profile" else {}
    with pytest.raises(SystemExit):
        getattr(mod, fn)("XAUUSD", tf, **kwargs)


@pytest.mark.parametrize("tool,fn,tf", [
    ("killzone_profile", "load_days", "M15"),
    ("h4_sweep_profile", "load_bars", "H4"),
])
def test_a_missing_bar_file_says_so_rather_than_blaming_the_version(tmp_path, tool, fn, tf):
    """The no-bars case must not be answered with the version message.

    Rule 5 — ask what a diagnostic is reporting ON. These two failures have different
    fixes (pull bars vs re-pull bars), so they must never share one sentence.
    """
    mod = _load(tool)
    mod.CACHE = tmp_path  # empty

    kwargs = {"start": None, "end": None} if tool == "killzone_profile" else {}
    with pytest.raises(SystemExit) as exc:
        getattr(mod, fn)("XAUUSD", tf, **kwargs)

    assert "feed_version" not in str(exc.value)
    assert "no cached bars" in str(exc.value)
