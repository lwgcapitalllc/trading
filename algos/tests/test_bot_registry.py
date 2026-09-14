"""Which bots exist, and which process is which bot — `algos/shared/bot_registry.py`.

**A bot IS its instance folder.** Every roster that starts, watches, names or reviews a bot reads
`discover()`; until 2026-09-13 there were five hand-kept lists, each omission silent and each
failing differently (`algos/CLAUDE.md` → *A bot IS its folder*).

The process half (`is_runner_line`) is driven over `fixtures/runner_lines.json`, the ONE list of
cases the Command Center's twin (`routers/bots.py::_is_bot_runner`) is driven over too — the two
may not import each other, so the cases are the shared artifact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "shared"))
import bot_registry as reg  # noqa: E402

_CASES = Path(__file__).resolve().parent / "fixtures" / "runner_lines.json"


def _bot(root: Path, key: str, body=None) -> Path:
    d = root / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(body if body is not None else {"bot_key": key}))
    return d


# ── which bots exist ─────────────────────────────────────────────────────────────
def test_a_bot_is_a_folder_holding_a_config(tmp_path):
    _bot(tmp_path, "b_bot")
    _bot(tmp_path, "a_bot")
    assert reg.discover(tmp_path) == {"a_bot": tmp_path / "a_bot", "b_bot": tmp_path / "b_bot"}


def test_a_folder_without_a_config_is_not_a_bot(tmp_path):
    """A watcher once CREATED a folder named after a renamed bot to write its liveness record into
    (2026-09-04). Counting it would register a bot that cannot start.
    MUTATION: drop the `config.json` test -> red."""
    _bot(tmp_path, "real")
    (tmp_path / "left_behind").mkdir()
    assert set(reg.discover(tmp_path)) == {"real"}


def test_a_folder_whose_name_is_not_a_key_is_not_a_bot(tmp_path):
    """A key names a folder, a process argument, a Telegram label and a section in the Command
    Center's batched read, so it is held to the one alphabet all four take without quoting."""
    for name in ("Capital", "1starts_with_digit", "has-dash", "x"):
        _bot(tmp_path, name)
    _bot(tmp_path, "fine_1")
    assert set(reg.discover(tmp_path)) == {"fine_1"}


def test_an_UNREADABLE_config_is_still_a_bot(tmp_path):
    """Its folder says it exists; what it cannot say is its account — and every watcher treats
    *cannot read the config* as *keep watching, loudly*. Dropping it here would quietly stop
    watching a live bot whose file has a typo. MUTATION: require a parseable config -> red."""
    d = _bot(tmp_path, "typo_bot")
    (d / "config.json").write_text("{not json")
    assert set(reg.discover(tmp_path)) == {"typo_bot"}


def test_a_folder_that_cannot_be_listed_is_not_an_empty_registry(tmp_path):
    """Rule 1 / rule 8: an empty registry answers every question confidently and wrongly — a
    watchdog handed one watches nothing and says nothing. MUTATION: return {} on the error -> red."""
    with pytest.raises(reg.RegistryUnreadable):
        reg.discover(tmp_path / "does_not_exist")


def test_an_empty_folder_IS_an_empty_registry(tmp_path):
    """The other half: a folder that was read and holds no bot answers `{}`, not an error."""
    assert reg.discover(tmp_path) == {}


def test_read_config_answers_None_never_an_empty_dict(tmp_path):
    """*This bot states nothing* and *we could not find out* are different answers."""
    d = _bot(tmp_path, "b", {})
    assert reg.read_config(d) == {}
    (d / "config.json").write_text("[1, 2]")
    assert reg.read_config(d) is None
    assert reg.read_config(tmp_path / "missing") is None


def test_the_display_name_falls_back_to_the_key(tmp_path):
    assert (
        reg.display_name(_bot(tmp_path, "named", {"display_name": " SOS Fade "}), "named")
        == "SOS Fade"
    )
    assert reg.display_name(_bot(tmp_path, "blank", {"display_name": "  "}), "blank") == "blank"
    assert reg.display_name(tmp_path / "gone", "gone") == "gone"


def test_the_real_bot_folders_are_found():
    """The repo's own folders: a non-empty list, every key well formed."""
    found = reg.discover()
    assert found, "no bot folders found in the repo"
    assert all(reg.KEY_PATTERN.match(k) for k in found)


# ── which process is which bot ───────────────────────────────────────────────────
def _cases():
    doc = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = doc["cases"]
    assert len(cases) >= 10, "the shared cases parsed as near-empty - this would pass for free"
    return cases


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["why"][:60])
def test_every_shared_process_line_case(case):
    """MUTATION: match the key as a substring -> red on the `sos_fade_20` case.
    MUTATION: drop the runner-script test -> red on the coordinator / promote / watcher cases."""
    assert reg.is_runner_line(case["line"], case["key"]) is case["is_runner"], case["why"]


def test_the_shared_cases_carry_BOTH_answers():
    """A list of cases that all say yes certifies a matcher that says yes to everything."""
    answers = {c["is_runner"] for c in _cases()}
    assert answers == {True, False}


def test_runner_keys_names_only_the_bots_actually_running():
    procs = "\n".join(
        [
            "CommandLine",
            "python.exe C:\\trading\\algos\\live\\runner.py --bot sos_fade_20 --live",
            "python.exe C:\\trading\\algos\\live\\runner.py --bot sos_fade_demo --live",
            "python.exe C:\\trading\\algos\\tools\\promote.py --bot sos_fade_2",
        ]
    )
    assert reg.runner_keys(procs, ["sos_fade_2", "sos_fade_20", "sos_fade_demo"]) == {
        "sos_fade_20",
        "sos_fade_demo",
    }


def test_an_empty_key_is_never_a_runner():
    assert reg.is_runner_line("python.exe runner.py --bot  --live", "") is False
