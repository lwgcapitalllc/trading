"""The fast tier's rules, held to the real repo.

🔴 **The rules restate the full runner's step list, and a restated list drifts.** A step added to
`scripts/run_all_tests.sh` and not to `rules.py` is a check the everyday command silently stops
running. These tests read the runner itself and go red the moment the two disagree.
"""

from __future__ import annotations

import re

import pytest

from scripts.testing import manifest, rules
from scripts.testing.fast import build_graph
from scripts.testing.selection import select

RUNNER = (rules.REPO / "scripts" / "run_all_tests.sh").read_text(encoding="utf-8")


def test_every_step_of_the_full_runner_is_known_to_the_fast_tier():
    labels = re.findall(r"\[(\d+)/(\d+)\]", RUNNER)
    ids = {int(n) for n, _ in labels}
    totals = {int(m) for _, m in labels}
    known = set(rules.PYTEST_STEPS) | {rules.GATE_STEP} | {s.id for s in rules.STEPS}
    assert len(totals) == 1, f"the runner disagrees with itself about its step count: {totals}"
    assert ids == known, f"runner steps {sorted(ids)} vs rules {sorted(known)}"
    assert max(ids) == totals.pop()
    assert len({s.id for s in rules.STEPS}) == len(rules.STEPS)


def test_step_one_hands_pytest_exactly_the_root_suites_folders():
    line = next(ln for ln in RUNNER.splitlines() if "-m pytest " in ln and "cd " not in ln)
    folders = line.split("-m pytest", 1)[1].split("-q", 1)[0].split()
    root = next(s for s in rules.SUITES if s.name == "root")
    assert tuple(folders) == root.dirs


def test_every_step_script_and_command_file_exists():
    for step in rules.STEPS:
        if step.script:
            assert (rules.REPO / step.script).is_file(), step.script
        cwd = rules.REPO / step.cwd if step.cwd else rules.REPO
        for arg in step.cmd:
            if arg.endswith((".py", ".js", ".mjs")):
                assert (cwd / arg).is_file(), f"step {step.id}: {arg}"
    for component, gate in rules.gates():
        assert (rules.REPO / gate).is_file() and (rules.REPO / component).is_dir()


@pytest.fixture(scope="module")
def real():
    tree = manifest.current()
    return build_graph(tree)


def _sel(graph, *paths):
    return select(graph, rules, {p: "modified" for p in paths})


def test_an_engine_change_reaches_its_tests_and_its_gate(real):
    sel = _sel(real, "engines/vwap/engine.py")
    assert "engines/vwap/tests/test_engine.py" in sel.tests["root"]
    assert "engines/vwap" in sel.gates
    assert not sel.everything


def test_a_router_change_reaches_every_client_test_and_not_the_whole_backend(real):
    backend_suite = next(s for s in rules.SUITES if s.name == "backend")
    conftest = "command-center/backend/tests/conftest.py"
    tests = [t for t in real.py if backend_suite.owns(t)]
    client_users = {t for t in tests if "client" in real.fixtures_used(conftest, t)}
    sel = _sel(real, "command-center/backend/routers/calendar.py")
    picked = set(sel.tests["backend"])
    # The real conftest imports the app inside ONE fixture: every test using it can reach any
    # router, and a test that neither uses it nor imports the router cannot.
    assert client_users and client_users <= picked
    assert (
        "command-center/backend/tests/test_calendar.py" not in picked
    )  # the service, not the router
    assert len(picked) < len(tests)


def test_a_doc_change_runs_nothing(real):
    sel = _sel(real, "CLAUDE.md")
    assert sel.empty() and not sel.everything


def test_a_pine_change_runs_the_pine_steps_and_no_pytest_suite_wholesale(real):
    pine = next(
        p for p in real.files if p.startswith("strategies/tradingview/") and p.endswith(".pine")
    )
    sel = _sel(real, pine)
    assert {14, 16, 18} <= sel.steps
    assert not sel.everything


def test_a_frontend_source_change_runs_the_typecheck_and_the_node_checks_only(real):
    sel = _sel(real, "command-center/frontend/src/App.tsx")
    assert {3, 8, 9, 10, 11, 12} <= sel.steps
    # rules.py reads App.tsx (it walks the app from it for step 19), so the fast tier's own tests
    # can see the change; nothing else in either python suite can.
    assert all(t.startswith("scripts/testing/tests/") for t in sel.tests["root"])
    assert not sel.tests["backend"] and not sel.gates


# Step 19's selection. Mutation map (2026-09-11, `python -m scripts.testing.mutate`, 5 planted, 5
# killed): following App.tsx's routes to every page; dropping the specs as roots; not resolving
# `@/`; the step no longer heavy; a marker the config does not use.
BROWSER = 19


def test_a_change_the_bots_page_can_run_reaches_the_offline_browser_specs(real):
    fe = "command-center/frontend"
    for path in (
        f"{fe}/src/pages/Bots/index.tsx",  # the page itself
        f"{fe}/src/hooks/useBots.ts",  # what it reads through
        f"{fe}/src/App.tsx",  # the shell it renders inside
        f"{fe}/tests/bots-accounts.spec.ts",  # a spec
        f"{fe}/tests/offlineApp.ts",  # the harness, reached through the specs' own imports
    ):
        assert BROWSER in _sel(real, path).steps, path


def test_a_change_to_another_page_does_not_run_them(real):
    # App.tsx imports every page, and following that edge would run the Bots specs for any edit.
    sel = _sel(real, "command-center/frontend/src/pages/BacktestDetail.tsx")
    assert BROWSER not in sel.steps
    assert {3, 12} <= sel.steps  # the page is still typechecked and colour-checked


def test_the_runner_finds_the_same_offline_specs_the_playwright_config_does():
    config = (rules.REPO / "command-center/frontend/playwright.config.ts").read_text()
    assert f".includes('{rules.OFFLINE_MARKER}')" in config
    names = {p.rsplit("/", 1)[1] for p in rules.offline_specs()}
    assert {"bots-accounts.spec.ts", "bots-version.spec.ts"} <= names
    step = next(s for s in rules.STEPS if s.id == BROWSER)
    assert step.heavy and "--project=offline" in step.cmd
