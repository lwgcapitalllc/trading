"""The two tools around the selector: the in-memory bug planter and the full run's blind-spot report.

Both exist to catch the selector or a test lying in the reassuring direction, so both are tested for
the reassuring answer they must NOT give.

Mutation map, RUN 2026-09-10 through mutate.py itself (4 planted, 4 killed):
  the planted source never served to the child     -> the_test_can_see_is_killed
  a red run read as survived                        -> the_test_can_see_is_killed
  backend failures not rebased onto the repo        -> reads_failures_per_suite
  blind spots never reported                        -> names_a_failure_the_fast_tier_would_have_skipped

And for the per-spec offline step, RUN 2026-09-11 (3 planted, 3 killed):
  a failing spec's name not read off the log        -> reads_WHICH_offline_spec_failed
  a progress line read as a failure                 -> reads_WHICH_offline_spec_failed
  a spec the fast tier left out not reported        -> names_an_offline_spec_the_fast_tier_LEFT_OUT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.testing import manifest, mutate, stamp


def _tiny_project(tmp_path: Path) -> Path:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "test_calc.py").write_text(
        "import calc\n\ndef test_add():\n    assert calc.add(2, 3) == 5\n"
    )
    return tmp_path


def test_a_planted_bug_the_test_can_see_is_killed(tmp_path, monkeypatch):
    proj = _tiny_project(tmp_path)
    monkeypatch.chdir(proj)
    monkeypatch.syspath_prepend(str(proj))
    rc = mutate.run(
        proj / "calc.py",
        "return a + b",
        "return a - b",
        ["-p", "no:cacheprovider", str(proj / "test_calc.py"), "--rootdir", str(proj)],
    )
    assert rc == 0


def test_a_planted_bug_nothing_checks_survives(tmp_path, monkeypatch):
    proj = _tiny_project(tmp_path)
    (proj / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef unused():\n    return 1\n"
    )
    monkeypatch.chdir(proj)
    rc = mutate.run(
        proj / "calc.py",
        "return 1",
        "return 2",
        [str(proj / "test_calc.py"), "--rootdir", str(proj)],
    )
    assert rc == 1  # nothing reads unused(), so the tests cannot see it - and must say so


def test_a_mutation_that_cannot_be_planted_runs_nothing(tmp_path):
    proj = _tiny_project(tmp_path)
    assert mutate.run(proj / "calc.py", "not in the file", "x", ["unused"]) == 2


def test_a_bug_planted_in_a_TEST_file_is_refused_never_reported_as_survived(tmp_path, monkeypatch):
    """pytest reads test modules and conftest from disk, so the in-memory plant never reaches them.
    Before the refusal this returned 1 - SURVIVED - for a bug that would have turned the test red:
    the false survivor that sent two real kills on 2026-09-10 looking for coverage that was there."""
    proj = _tiny_project(tmp_path)
    (proj / "conftest.py").write_text("X = 1\n")
    monkeypatch.chdir(proj)
    args = ["-p", "no:cacheprovider", str(proj / "test_calc.py"), "--rootdir", str(proj)]
    assert mutate.run(proj / "test_calc.py", "== 5", "== 6", args) == 2
    assert mutate.run(proj / "conftest.py", "X = 1", "X = 2", args) == 2


def test_the_planted_bug_never_touches_the_file_on_disk(tmp_path, monkeypatch):
    proj = _tiny_project(tmp_path)
    before = (proj / "calc.py").read_text()
    monkeypatch.chdir(proj)
    mutate.run(
        proj / "calc.py",
        "return a + b",
        "return a - b",
        [str(proj / "test_calc.py"), "--rootdir", str(proj)],
    )
    assert (proj / "calc.py").read_text() == before


def test_the_blind_spot_report_reads_failures_per_suite(tmp_path):
    log = tmp_path / "full.log"
    log.write_text(
        "  [1/18] engines / backtest ...\n"
        "FAILED engines/vwap/tests/test_engine.py::test_x - AssertionError\n"
        "  [2/18] command-center backend ...\n"
        "FAILED tests/test_calendar.py::test_y - boom\n"
        "  [6/18] documentation-size guard ...\n"
        "  ✗ documentation-size guard (21 cases)\n"
    )
    fails = stamp._failures(log)
    assert fails[1] == {"engines/vwap/tests/test_engine.py"}
    assert fails[2] == {"command-center/backend/tests/test_calendar.py"}  # rebased to the repo
    assert 6 in fails


def test_the_blind_spot_report_names_a_failure_the_fast_tier_would_have_skipped(
    tmp_path, monkeypatch, capsys
):
    tree = manifest.current()
    changed_doc = "CLAUDE.md"  # selects nothing, so ANY failing test is one the fast tier skipped
    old = dict(tree)
    old[changed_doc] = "0" * 40
    monkeypatch.setattr(manifest, "load_green", lambda tier: {"manifest": old, "tier": "fast"})
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"manifest": tree, "env": manifest.env_key(sys.executable)}))
    log = tmp_path / "full.log"
    log.write_text(
        "  [1/18] engines / backtest ...\n"
        "FAILED engines/vwap/tests/test_engine.py::test_x - AssertionError\n"
    )
    stamp._blindspots(log, snap)
    out = capsys.readouterr().out
    assert "BLIND SPOT" in out and "engines/vwap/tests/test_engine.py" in out


FE = "command-center/frontend"
# The offline browser step's output as Playwright prints it: a "[n/N]" progress line for EVERY
# check, and a numbered header for each FAILURE only (format copied off a real red run).
_BROWSER_LOG = (
    "  [19/19] offline browser specs (the Bots page, recorded answers) ...\n"
    "[2/27] [offline] › tests/bots-version.spec.ts:40:1 › a check that passed\n"
    "  1) [offline] › tests/chart-paging.spec.ts:111:1 › a jump applies a BOUNDED window \n"
    "  ✗ offline browser specs (command-center/frontend, --project=offline)\n"
)


def test_the_blind_spot_report_reads_WHICH_offline_spec_failed(tmp_path):
    log = tmp_path / "full.log"
    log.write_text(_BROWSER_LOG)
    # The progress line for the passing check is not a failure; the numbered header is.
    assert stamp._failures(log)[19] == {f"{FE}/tests/chart-paging.spec.ts"}


def test_the_blind_spot_report_names_an_offline_spec_the_fast_tier_LEFT_OUT(
    tmp_path, monkeypatch, capsys
):
    """The fast tier ran step 19 for a Bots-page edit - but only the Bots specs. A chart spec failing
    in the full run is then a spec it skipped, and reporting "step 19 ran" would hide that."""
    tree = manifest.current()
    old = dict(tree)
    old[f"{FE}/src/pages/Bots/index.tsx"] = "0" * 40
    monkeypatch.setattr(manifest, "load_green", lambda tier: {"manifest": old, "tier": "fast"})
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"manifest": tree, "env": manifest.env_key(sys.executable)}))
    log = tmp_path / "full.log"
    log.write_text(_BROWSER_LOG)
    stamp._blindspots(log, snap)
    out = capsys.readouterr().out
    assert "BLIND SPOT" in out and f"{FE}/tests/chart-paging.spec.ts" in out


def test_an_offline_spec_the_fast_tier_DID_run_is_not_a_blind_spot(tmp_path, monkeypatch, capsys):
    tree = manifest.current()
    old = dict(tree)
    old[f"{FE}/src/pages/BacktestDetail.tsx"] = "0" * 40  # reaches the chart specs
    monkeypatch.setattr(manifest, "load_green", lambda tier: {"manifest": old, "tier": "fast"})
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"manifest": tree, "env": manifest.env_key(sys.executable)}))
    log = tmp_path / "full.log"
    log.write_text(_BROWSER_LOG)
    stamp._blindspots(log, snap)
    assert "BLIND SPOT" not in capsys.readouterr().out
