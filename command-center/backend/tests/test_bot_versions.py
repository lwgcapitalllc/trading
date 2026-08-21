"""What a bot's VERSION means, and the ways this could report a number nobody should act on.

The subject is `services/bot_versions.py`. Most of these are about REFUSING rather than
computing: the page draws a big amber "you are N behind" banner with a deploy button under it,
so a wrong N is a wrong destructive action, and a fabricated 0 is the most dangerous value in
the file because it reads as *up to date*.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest import mock

import config as cfg
import pytest
from services import bot_versions as bv

_REPO = Path(cfg.MONOREPO_ROOT)


# ── the agreement with promote.py ───────────────────────────────────────────────


def test_the_counted_trees_are_the_trees_promote_actually_copies():
    """`trees_for` mirrors `algos/tools/promote.py::repo_trees`, checked by READING it.

    A tree that is COPIED into the snapshot but not COUNTED here is a change that deploys
    while the page says you are up to date — silent, and wrong in the reassuring direction.
    The subsystem rule forbids importing across into `algos/`, so this greps the file the way
    `test_notification_routing.py` greps the Telegram senders.
    """
    src = (_REPO / "algos" / "tools" / "promote.py").read_text(encoding="utf-8")
    body = src.split("def repo_trees", 1)[1].split("\ndef ", 1)[0]
    assert body.strip(), "could not find repo_trees in promote.py — the guard is vacuous"

    # promote.py names the strategy tree via `cfg.strategy_package` and the rest as literals.
    literals = set(re.findall(r'Path\("([a-z_]+)"\)', body)) | set(
        re.findall(r'"([a-z_]+)"\s*/', body)
    )
    shared = {t for t in literals if t not in {"strategies", "python"}}
    assert shared, "found no shared tree literals in repo_trees — the parse broke, not the code"

    counted = set(bv.trees_for("anything"))
    for tree in shared:
        assert tree in counted, (
            f"promote.py copies {tree!r} into the snapshot and bot_versions does not count it, "
            "so a change there would deploy while the page reads 'up to date'"
        )
    assert "strategies/python/anything" in counted


def test_a_bot_with_no_strategy_package_counts_nothing():
    """Not `["engines", "backtest"]` — a version for a bot whose strategy is unknown is a
    number about somebody else's code."""
    assert bv.trees_for("") == []


# ── versions are real counts, not guesses ───────────────────────────────────────


def test_a_version_is_the_count_of_commits_touching_the_trees():
    trees = bv.trees_for("mpc_sos_fade")
    out = subprocess.run(
        ["git", "-C", str(_REPO), "rev-list", "--count", "HEAD", "--", *trees],
        capture_output=True,
        text=True,
        check=True,
    )
    assert bv.version_at("HEAD", trees) == int(out.stdout.strip())


def test_an_older_commit_has_a_lower_version_than_head():
    """The whole banner rests on subtracting two of these, so the ordering is the contract."""
    trees = bv.trees_for("mpc_sos_fade")
    head = bv.version_at("HEAD", trees)
    older = bv.version_at("HEAD~50", trees)
    assert older is not None and head is not None
    assert older < head


def test_a_commit_this_clone_has_never_seen_is_None_not_zero():
    """`0` would render as *up to date*. A fresh clone that has not fetched the deployed commit
    must say it cannot answer — the same rule `mt5_link` and `grid_sensitivity_score` follow."""
    assert bv.version_at("0" * 40, bv.trees_for("mpc_sos_fade")) is None


def test_has_commit_is_false_for_a_commit_that_is_not_here():
    assert bv.has_commit("0" * 40) is False
    assert bv.has_commit("") is False
    assert bv.has_commit("HEAD") is True


# ── compare() refuses rather than reporting a comparison it cannot make ─────────


def test_a_bot_that_has_never_been_promoted_is_not_comparable():
    r = bv.compare("mpc_sos_fade", "", {})
    assert r["comparable"] is False
    assert r["versions_behind"] is None
    assert "never been promoted" in r["reason"]


def test_an_unfetched_deployed_commit_is_not_comparable_and_names_the_fix():
    r = bv.compare("mpc_sos_fade", "0" * 40, {})
    assert r["comparable"] is False
    assert r["versions_behind"] is None
    assert "Pull" in r["reason"]


def test_a_bot_deployed_at_head_is_zero_behind_and_comparable():
    r = bv.compare("mpc_sos_fade", "HEAD", {})
    assert r["comparable"] is True
    assert r["versions_behind"] == 0
    assert r["changes"] == []


def test_behind_never_goes_negative():
    """A deployment AHEAD of this clone (somebody else promoted from a machine that had pulled)
    must read 0, not a negative count — the banner's copy has no sensible form for -3."""
    r = bv.compare("mpc_sos_fade", "HEAD~50", {})
    assert r["versions_behind"] is not None and r["versions_behind"] > 0
    r2 = bv.compare("mpc_sos_fade", "HEAD", {})
    assert r2["versions_behind"] == 0


def test_the_change_list_matches_the_version_gap():
    """The number in the headline and the list under it are two renderings of one fact; if they
    disagree the banner argues with itself."""
    r = bv.compare("mpc_sos_fade", "HEAD~50", {})
    assert r["comparable"] is True
    assert len(r["changes"]) == r["versions_behind"]


def test_every_change_names_the_tree_it_touched():
    """`areas` is what lets the banner separate *the strategy's own rules changed* from *a shared
    engine moved underneath it*, and NOTHING pinned it until 2026-08-15.

    🔴 It was found untested by MUTATION, during the rewrite that turned `changes_between` from
    one `git show` per commit into a single `git log --name-only`: forcing `areas = []` left all
    49 tests in these two files GREEN. So the field the module docstring explains at length was
    free to break in silence, and the only thing standing behind that rewrite was a one-off
    diff against the old implementation's output.

    Two properties, and the second is the one a wrong pathspec breaks:

    * every change names at least one tree — a commit reached this list BECAUSE it touched one,
      so an empty `areas` means the file list was not read rather than that nothing was touched;
    * every named tree is one of the bot's own — a widened pathspec (`engines` matching a
      top-level FILE of that name, a missing `tree + "/"` test) shows up here and nowhere else.
    """
    trees = bv.trees_for("mpc_sos_fade")
    r = bv.compare("mpc_sos_fade", "HEAD~50", {})
    assert r["changes"], "no changes to check — widen the range"
    assert any(not c.get("merge") for c in r["changes"]), "only merges in range — widen it"
    for c in r["changes"]:
        if c.get("merge"):
            # A merge prints no file list under `--name-only`, so it names no tree BY
            # CONSTRUCTION. It stays in the list because the headline count includes it, and
            # it carries `merge: True` so an empty `areas` here is a stated fact rather than a
            # failed read. ⚠ Asserting the flag, not just skipping: without it this branch
            # would also swallow the widened-pathspec bug the test below exists to catch.
            assert c["areas"] == [], f"{c['commit']} is flagged a merge but named trees"
            continue
        assert c["areas"], f"{c['commit']} names no tree: {c['subject']}"
        assert set(c["areas"]) <= set(trees), f"{c['commit']} names a foreign tree: {c['areas']}"


def test_the_change_list_is_ONE_git_process_per_range():
    """The whole point of the 2026-08-15 rewrite, pinned so it cannot regress quietly.

    🔴 The old form fanned out one `git show --name-only` PER COMMIT. That is invisible in a
    result — the output was byte-identical over all 172 commits of this repo's history — and it
    made both this endpoint and the suite around it slower on every commit anybody pushed:
    MEASURED at 1,080 subprocesses and 51.8s of a 53.7s run of `test_bot_version.py`.

    ⚠ **This counts PROCESSES, not seconds.** A wall-clock assertion is a flaky test on a busy
    laptop and says nothing on a fast one; the defect was never the speed, it was the fan-out.
    """
    calls: list[tuple] = []
    real = subprocess.run

    def _counting_run(args, **kwargs):
        if args and args[0] == "git":
            calls.append(tuple(args))
        return real(args, **kwargs)

    with mock.patch.object(subprocess, "run", _counting_run):
        changes = bv.changes_between("HEAD~50", "HEAD", bv.trees_for("mpc_sos_fade"))

    assert changes, "no changes to check — widen the range"
    assert len(calls) == 1, f"{len(calls)} git processes for {len(changes)} commits: {calls}"


# ── the settings diff ───────────────────────────────────────────────────────────


def test_a_changed_default_is_reported_with_both_values():
    before = "@dataclass\nclass C:\n    a: str = 'Off'\n"
    after = "@dataclass\nclass C:\n    a: str = 'On'\n"
    assert bv._dataclass_defaults(before)["a"] == "Off"
    assert bv._dataclass_defaults(after)["a"] == "On"


def test_a_field_declared_twice_with_different_defaults_refuses_to_guess():
    """`mpc_bleg` subclasses `mpc_sos_fade`'s config and overrides fields. Picking one silently
    would describe the wrong bot, so the value becomes UNPARSED and renders as '?'."""
    src = (
        "@dataclass\nclass Base:\n    a: bool = False\n"
        "@dataclass\nclass Sub(Base):\n    a: bool = True\n"
    )
    assert bv._dataclass_defaults(src)["a"] is bv._UNPARSED


def test_a_field_declared_twice_with_the_SAME_default_is_not_poisoned():
    src = (
        "@dataclass\nclass Base:\n    a: bool = False\n"
        "@dataclass\nclass Sub(Base):\n    a: bool = False\n"
    )
    assert bv._dataclass_defaults(src)["a"] is False


def test_a_non_literal_default_is_refused_rather_than_evaluated():
    """This parses source out of an arbitrary historical commit. `ast.literal_eval` cannot run
    a call, and nothing here may fall back to `eval` — that would execute that commit's code."""
    src = "@dataclass\nclass C:\n    a: dict = field(default_factory=dict)\n"
    assert bv._dataclass_defaults(src)["a"] is bv._UNPARSED


def test_the_parser_never_executes_the_source_it_reads():
    """Belt and braces on the rule above: a module with a side effect at import time must not
    fire. If this ever fails, something switched `ast` for `exec`/`import`."""
    src = (
        "import pathlib\n"
        "pathlib.Path('/tmp/bot_versions_must_never_write_this').write_text('x')\n"
        "@dataclass\nclass C:\n    a: int = 1\n"
    )
    assert bv._dataclass_defaults(src)["a"] == 1
    assert not Path("/tmp/bot_versions_must_never_write_this").exists()


def test_unparseable_source_is_empty_rather_than_raising():
    assert bv._dataclass_defaults("class C:\n  this is not python\n") == {}


def test_a_setting_the_config_pins_is_reported_as_stated():
    """A pinned setting cannot move on a promote. It is still returned, because *your bot is
    holding this still* is the reassuring half of the same question — and filtering it out
    leaves the reader unable to tell 'not affected' from 'not checked'."""
    changes = bv.setting_changes("mpc_sos_fade", "HEAD~50", "HEAD", {"exec_secondary": False})
    assert changes is not None
    pinned = [c for c in changes if c["name"] == "exec_secondary"]
    if pinned:  # only if that default actually moved in-range
        assert pinned[0]["stated"] is True


def test_a_new_setting_says_it_is_new_rather_than_claiming_it_was_off():
    """`was: ""` + `is_new` — the deployed version had no such lever at all, which is not the
    same as having it switched off, and 'Off' would be a lie in the reassuring direction."""
    changes = bv.setting_changes("mpc_sos_fade", "HEAD~50", "HEAD", {})
    assert changes is not None
    for c in changes:
        assert (c["was"] == "") == c["is_new"], c


def test_setting_labels_come_from_the_strategys_own_meta_file():
    """The page's wording is the STRATEGY's, copied. A name→sentence mapping written in this
    app would be a second claim about what a setting does."""
    meta = bv._param_meta("mpc_sos_fade")
    assert meta, "the meta file did not parse — every label would silently fall back to the key"
    assert meta["exec_time_stop_mode"]["label"] == "Time stop"


def test_a_setting_with_no_meta_entry_falls_back_to_its_key_rather_than_blank():
    changes = bv.setting_changes("mpc_sos_fade", "HEAD~50", "HEAD", {})
    assert changes is not None
    for c in changes:
        assert c["label"], f"{c['name']} rendered a blank label"


def test_an_unknown_package_refuses_instead_of_returning_an_empty_diff():
    """`[]` means 'nothing changed'. A package whose config.py cannot be read must not say so."""
    assert bv.setting_changes("no_such_package", "HEAD~50", "HEAD", {}) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, "On"),
        (False, "Off"),
        (36.0, "36"),
        (0.382, "0.382"),
        ("Off", "Off"),
    ],
)
def test_values_render_the_way_the_banner_prints_them(value, expected):
    assert bv._render(value) == expected


def test_an_unparsed_value_renders_as_a_question_mark_not_as_a_number():
    assert bv._render(bv._UNPARSED) == "?"


# ── what the VPS can actually REACH ─────────────────────────────────────────────
#
# 🔴 MEASURED 2026-08-14: a successful deploy of mpc_sos_fade_demo landed v164 while the
# backtester read v165, because the single commit between them was unpushed. The promote pulls
# on the VPS, so the remote — not this laptop's HEAD — is the ceiling on what can be deployed.
# Every number on the banner was correct and nothing on it explained why pressing Deploy again
# would change nothing.


def test_a_bot_with_no_trees_cannot_be_asked_what_is_unpushed():
    """`None`, never `[]`. An empty list is the claim *everything is pushed*, and there is no
    such measurement for a bot whose code we cannot name."""
    assert bv.unpushed_commits([]) is None


def test_no_upstream_reads_as_UNKNOWN_rather_than_all_pushed(monkeypatch):
    """A detached HEAD or a branch tracking nothing cannot answer this. Returning `[]` would put
    a silent all-clear on the one line that explains a deploy landing short."""
    monkeypatch.setattr(bv, "_git", lambda *a: None if a[0] == "rev-parse" else "")
    assert bv.unpushed_commits(["engines"]) is None


def test_an_upstream_that_holds_everything_is_an_empty_list_not_None(monkeypatch):
    """The other half of the same rule: *measured, nothing outstanding* is a real answer and has
    to be distinguishable from *could not ask*."""
    calls = {"rev-parse": "origin/main\n", "log": ""}
    monkeypatch.setattr(bv, "_git", lambda *a: calls.get(a[0]))
    assert bv.unpushed_commits(["engines"]) == []


def test_unpushed_commits_are_listed_one_per_line(monkeypatch):
    """The banner renders the COUNT and puts the subjects on the tooltip, so a blank-line artefact
    would inflate the count the reader acts on."""
    log = "6a71a9f feat(signals): announce on the retrace\n\n72405c1 fix(signals): wording\n"
    monkeypatch.setattr(bv, "_git", lambda *a: "origin/main\n" if a[0] == "rev-parse" else log)
    got = bv.unpushed_commits(["engines"])
    assert got == [
        "6a71a9f feat(signals): announce on the retrace",
        "72405c1 fix(signals): wording",
    ]


def test_it_asks_only_about_THIS_BOTS_trees(monkeypatch):
    """A commit to `algos/live/` is unpushed code that this bot does not run — counting it would
    tell the reader to push before a deploy that is already complete."""
    seen: list[tuple] = []

    def fake(*a):
        seen.append(a)
        return "origin/main\n" if a[0] == "rev-parse" else ""

    monkeypatch.setattr(bv, "_git", fake)
    bv.unpushed_commits(["strategies/python/mpc_sos_fade", "engines", "backtest"])
    log = next(a for a in seen if a[0] == "log")
    assert "--" in log
    assert log[log.index("--") + 1 :] == ("strategies/python/mpc_sos_fade", "engines", "backtest")


def test_compare_carries_the_unpushed_list_so_the_banner_can_explain_a_short_deploy():
    """It rides on every `compare()` result, INCLUDING the ones that refuse — a bot that has
    never been promoted is exactly where 'push first' is worth saying before the first deploy."""
    r = bv.compare("mpc_sos_fade", "", {})
    assert "unpushed_commits" in r
    r2 = bv.compare("mpc_sos_fade", "HEAD", {})
    assert "unpushed_commits" in r2
