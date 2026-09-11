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


# Step 19's selection - ONE SPEC AT A TIME since 2026-09-11. Mutation map, RUN through
# `python -m scripts.testing.mutate` (9 planted, 9 killed): following App.tsx's route to every
# page; a variable `goto` read as no visit; the query string kept on a visit; a route pattern with
# no end anchor (so /runs/x/tune matched the run page); the recording left out of a spec's sources;
# an unknown path beside a known one read as the known one (SURVIVED first - see that test); the
# shared build input no longer running every spec; the none-means-all guard dropped; and the fast
# runner handing Playwright every spec's name instead of none.
BROWSER = 19
FE = "command-center/frontend"
BOTS_SPECS = {f"{FE}/tests/bots-accounts.spec.ts", f"{FE}/tests/bots-version.spec.ts"}
CHART_SPEC = f"{FE}/tests/vwap.spec.ts"


def _specs(sel):
    """The offline specs a selection runs: every one of them when the step runs whole."""
    chosen = sel.parts.get(BROWSER)
    return set(rules.offline_specs()) if chosen is None else chosen


def test_a_change_the_bots_page_can_run_reaches_ONLY_the_bots_specs(real):
    # 🔴 The Bots page is where the everyday loop lives, and it must not pay for the chart specs.
    for path in (
        f"{FE}/src/pages/Bots/index.tsx",  # the page itself
        f"{FE}/src/hooks/useBots.ts",  # what it reads through
        f"{FE}/tests/bots-accounts.spec.ts",  # a spec
    ):
        sel = _sel(real, path)
        assert BROWSER in sel.steps, path
        assert _specs(sel) <= BOTS_SPECS, (path, _specs(sel) - BOTS_SPECS)


def test_a_change_the_chart_can_run_reaches_the_chart_specs_and_NOT_the_bots_ones(real):
    for path in (
        f"{FE}/src/pages/BacktestDetail.tsx",
        f"{FE}/src/components/ChartPanel/index.tsx",  # lazily imported, `import(...)`
        f"{FE}/tests/recordings/chart-sos-fade.json",
    ):
        sel = _sel(real, path)
        assert CHART_SPEC in _specs(sel), path
        assert not (_specs(sel) & BOTS_SPECS), path


def test_the_shell_and_the_harness_reach_EVERY_offline_spec(real):
    for path in (
        f"{FE}/src/App.tsx",  # the shell every page renders inside
        f"{FE}/tests/offlineApp.ts",  # the harness, reached through the specs' own imports
        f"{FE}/vite.config.ts",  # the build every spec loads
    ):
        sel = _sel(real, path)
        assert BROWSER in sel.steps, path
        assert _specs(sel) == set(rules.offline_specs()), path


def test_a_shared_input_beside_a_page_edit_still_runs_EVERY_spec(real):
    # Changed files are walked in path order, so both orders are exercised: the shared input first
    # (index.html sorts before src/), and last (vite.config.ts sorts after it).
    for shared in (f"{FE}/index.html", f"{FE}/vite.config.ts"):
        sel = _sel(real, f"{FE}/src/pages/Bots/index.tsx", shared)
        assert sel.parts.get(BROWSER, "absent") is None, shared  # the whole step, not the Bots two


def test_a_recording_reaches_only_the_specs_that_replay_it(real):
    sel = _sel(real, f"{FE}/tests/recordings/chart-b-leg.json")
    assert _specs(sel) == {f"{FE}/tests/bleg-fibs.spec.ts"}


def test_a_page_no_offline_spec_opens_does_not_run_them(real):
    # App.tsx imports every page, and following that edge would run every spec for any edit.
    sel = _sel(real, f"{FE}/src/pages/StressTestDetail.tsx")
    assert BROWSER not in sel.steps
    assert {3, 12} <= sel.steps  # the page is still typechecked and colour-checked


def test_every_offline_spec_opens_a_page_the_route_table_names():
    """None means "I could not read where this spec goes, so run it for every page" - safe, but a
    spec that ALWAYS falls back has silently given up its selection."""
    for spec in rules.offline_specs():
        assert rules.pages_visited(rules._text(spec)), f"{spec}: no page resolved"


def test_a_visit_is_matched_to_its_OWN_route():
    fe = f"{FE}/src/pages"
    visit = rules.pages_visited
    assert visit("page.goto(`/backtests/runs/${RUN}`)") == {f"{fe}/BacktestDetail.tsx"}
    assert visit("page.goto('/bots?tab=monitor')") == {f"{fe}/Bots/index.tsx"}
    # The tune page sits one segment deeper and is a different page, not a prefix of this one.
    assert visit("page.goto(`/backtests/runs/${RUN}/tune`)") == {f"{fe}/TuningWorkbench.tsx"}


def test_a_visit_that_cannot_be_read_runs_the_spec_for_every_page():
    assert rules.pages_visited("await page.goto(url)") is None  # held in a variable
    assert rules.pages_visited("page.goto('/bots'); page.goto(somewhere)") is None  # one unread
    # No route serves it. ⚠ Beside a KNOWN visit, or the check cannot fail: alone, "no page found"
    # already comes back as None, so dropping the rule changed nothing (mutation SURVIVED).
    assert rules.pages_visited("page.goto('/bots'); page.goto('/no-such-page')") is None


def test_the_fast_runner_hands_playwright_only_the_chosen_specs():
    from scripts.testing.fast import _step_job

    step = next(s for s in rules.STEPS if s.id == BROWSER)
    part = _step_job(step, "python", {CHART_SPEC})
    assert part.cmd[-1] == "tests/vwap.spec.ts" and part.detail
    whole = _step_job(step, "python", {t for t, _ in step.parts})
    assert whole.cmd == list(step.cmd)  # every spec: no file arguments, and none left out
    assert _step_job(step, "python", None).cmd == list(step.cmd)


def test_the_runner_finds_the_same_offline_specs_the_playwright_config_does():
    config = (rules.REPO / "command-center/frontend/playwright.config.ts").read_text()
    assert f".includes('{rules.OFFLINE_MARKER}')" in config
    names = {p.rsplit("/", 1)[1] for p in rules.offline_specs()}
    assert {"bots-accounts.spec.ts", "bots-version.spec.ts"} <= names
    step = next(s for s in rules.STEPS if s.id == BROWSER)
    assert step.heavy and "--project=offline" in step.cmd
