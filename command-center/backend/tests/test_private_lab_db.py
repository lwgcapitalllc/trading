"""Every test is on its own lab database, whether it asked for one or not (`_private_lab_db`).

The backstop is autouse, so its failure mode is silence: a guard that never ran and a guard that
works look identical from a green suite - which is how a test came to write two runs and a stack
into the live app's database. These drive it directly.

⚠ The planter in `scripts/testing/mutate.py` refuses a conftest (pytest reads it from disk), so
each mutation below was run in a throwaway `git worktree` copy.
"""

from __future__ import annotations

from pathlib import Path

from services import lab_db

REAL_LAB = Path(lab_db.__file__).resolve().parents[1] / "data" / "lab.db"


def test_a_test_that_asks_for_nothing_is_not_on_the_real_lab(tmp_path):
    """⚠ Watched RED by deleting the autouse fixture: the path is the live app's `data/lab.db`."""
    assert Path(lab_db.DB_PATH).resolve() != REAL_LAB.resolve()
    assert Path(lab_db.DB_PATH).parent == tmp_path


def test_the_private_database_is_a_BUILT_one():
    """A test that forgot to ask gets a working, empty lab rather than a file with no tables -
    the same schema and seeded rulesets `fresh_db` hands out.

    ⚠ Watched RED by pointing the fixture at an empty file instead of copying the template.
    """
    assert lab_db.list_rulesets(), "no seeded rulesets - the private database was never built"
    assert lab_db.get_strategy("anything") is None


def test_a_fresh_clone_fixture_still_starts_from_NOTHING(tmp_path):
    """Some tests build a database at `tmp_path / "lab.db"` from nothing, to prove what a fresh
    clone gets. The backstop must not have put a finished schema there first, or those tests
    would exercise the migration path and still pass.

    ⚠ Watched RED by naming the private file `lab.db`.
    """
    assert not (tmp_path / "lab.db").exists()


def test_fresh_db_still_wins_and_hands_back_its_path(fresh_db):
    """`fresh_db` is set up after the autouse fixture, so its patch is the one in force."""
    assert Path(lab_db.DB_PATH) == fresh_db
    assert fresh_db.name == "lab.db"
