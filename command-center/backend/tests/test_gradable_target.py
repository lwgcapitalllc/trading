"""A stress test grades a RESULT, and a result is a single run OR a whole stack.

`stress_tests.run_id` was NOT NULL, so there was nowhere to record that the thing being
graded is a stack replayed on one shared account — which is why a stack could not be stress
tested at all. Pointing at the stack's FIRST LEG would have satisfied the foreign key and
named one strategy as the subject of a portfolio result: a field that reads as answered and
is not.

⚠ Every case here runs against a real database built by `lab_db.init_db`, on both paths —
a fresh build and a migrated one. This file already records what happens when only one is
checked: the schema works on the machine that ran the migration and is broken everywhere
else.
"""

from __future__ import annotations

import sqlite3

import pytest
from services import lab_db


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "fresh.db")
    lab_db.init_db()
    return sqlite3.connect(lab_db.DB_PATH)


def _downgrade(extra_col: str | None = None) -> None:
    """Put the database back to the pre-2026-09-06 `stress_tests` shape.

    🔴 DERIVED from the table that is actually there — every column it has today, minus
    `stack_id`, with `run_id` back to NOT NULL — never a typed-out list. A hand-written
    old table is a fixture LESS CAPABLE than production: the first version of this file
    had one, and a later migration in `init_db` died on a column it did not carry, which
    reads as a bug in the code under test rather than in the fixture.
    """
    c = sqlite3.connect(lab_db.DB_PATH)
    info = c.execute("PRAGMA table_info(stress_tests)").fetchall()
    pieces, names = [], []
    for _cid, name, ctype, notnull, dflt, pk in info:
        if name == "stack_id":
            continue
        piece = f"{name} {ctype or 'TEXT'}"
        if pk:
            piece += " PRIMARY KEY"
        if notnull or name == "run_id":
            piece += " NOT NULL"
        if dflt is not None:
            piece += f" DEFAULT {dflt}"
        pieces.append(piece)
        names.append(name)
    if extra_col:
        pieces.append(f"{extra_col} TEXT")
    carried = ", ".join(names)
    c.executescript(f"""
        PRAGMA foreign_keys=OFF;
        BEGIN;
        CREATE TABLE stress_tests_old ({", ".join(pieces)});
        INSERT INTO stress_tests_old ({carried}) SELECT {carried} FROM stress_tests;
        DROP TABLE stress_tests;
        ALTER TABLE stress_tests_old RENAME TO stress_tests;
        COMMIT;
    """)
    c.commit()
    c.close()


def _legacy(tmp_path, monkeypatch):
    """A database carrying the OLD shape, then migrated — what a real machine has on disk."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "legacy.db")
    lab_db.init_db()
    _downgrade()
    lab_db.init_db()
    return sqlite3.connect(lab_db.DB_PATH)


def _cols(conn):
    return {r[1]: r for r in conn.execute("PRAGMA table_info(stress_tests)")}


# ── The shape, on both paths ──────────────────────────────────────────────────


@pytest.mark.parametrize("build", [_fresh, _legacy])
def test_a_stress_test_can_name_a_STACK(tmp_path, monkeypatch, build):
    """Watched RED against HEAD on the legacy path (the column does not exist) and on the
    fresh path (`run_id` is NOT NULL, so a stack-only row is refused)."""
    conn = build(tmp_path, monkeypatch)
    cols = _cols(conn)
    assert "stack_id" in cols
    assert cols["run_id"][3] == 0, "run_id must be nullable — a stack has no single run"
    conn.execute(
        "INSERT INTO stress_tests (stress_test_id, stack_id, status, created_at) "
        "VALUES ('st_1', 'stk_1', 'running', 1)"
    )


@pytest.mark.parametrize("build", [_fresh, _legacy])
def test_EXACTLY_ONE_target_is_enforced_by_the_DATABASE(tmp_path, monkeypatch, build):
    """Both-set and neither-set are refused. A row naming both would let two readers
    disagree about what was graded; a row naming neither is a grade of nothing.

    ⚠ Watched RED by dropping the CHECK from both the CREATE and the rebuild.
    """
    conn = build(tmp_path, monkeypatch)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO stress_tests (stress_test_id, run_id, stack_id, status, created_at) "
            "VALUES ('st_both', 'r1', 'stk_1', 'running', 1)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO stress_tests (stress_test_id, run_id, stack_id, status, created_at) "
            "VALUES ('st_neither', NULL, NULL, 'running', 1)"
        )


@pytest.mark.parametrize("build", [_fresh, _legacy])
def test_the_stack_index_exists_on_BOTH_paths(tmp_path, monkeypatch, build):
    """It cannot live in the main schema script — that script also runs against a database
    whose table predates the column, and an index on a missing column kills the whole
    script and every migration below it. So it is asserted in the migration, on the
    rebuild path AND on the already-migrated early return.

    ⚠ Watched RED by deleting it from the early-return branch: the fresh case goes red
    alone, which is exactly the asymmetry this file exists to catch.
    """
    conn = build(tmp_path, monkeypatch)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='stress_tests'"
        )
    }
    assert "idx_stress_tests_stack" in names


# ── What the rebuild must not lose ────────────────────────────────────────────


def test_the_rebuild_CARRIES_EVERY_COLUMN_and_every_row(tmp_path, monkeypatch):
    """🔴 The `optimizations` rebuild in this module lists its columns BY HAND, and the ones
    somebody forgot were silently DROPPED on every fresh database. This one reads them off
    the table, so a column added by a later migration cannot be lost — proven with a column
    the rebuild has never heard of.

    ⚠ Watched RED by replacing the derived list with a hardcoded four columns.
    """
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "carry.db")
    lab_db.init_db()
    _downgrade(extra_col="a_column_a_later_migration_added")

    c = sqlite3.connect(lab_db.DB_PATH)
    c.execute(
        "INSERT INTO stress_tests (stress_test_id, run_id, status, created_at, grade, "
        "a_column_a_later_migration_added) VALUES ('st_old','r_old','complete',99,'B','keep me')"
    )
    c.commit()
    before = {r[1] for r in c.execute("PRAGMA table_info(stress_tests)")}
    c.close()

    lab_db.init_db()
    c = sqlite3.connect(lab_db.DB_PATH)
    after = {r[1] for r in c.execute("PRAGMA table_info(stress_tests)")}
    assert before - after == set(), f"the rebuild dropped {before - after}"
    assert "a_column_a_later_migration_added" in after
    # ⚠ `grade` is deliberately NOT asserted: `_restamp_stress_tests` re-grades every stored
    # row on startup and correctly clears a letter it cannot re-derive. Pinning it here would
    # make this test fail on another migration's correct behaviour.
    assert c.execute(
        "SELECT run_id, stack_id, num_simulations, a_column_a_later_migration_added "
        "FROM stress_tests WHERE stress_test_id = 'st_old'"
    ).fetchone() == ("r_old", None, 10000, "keep me")


def test_the_rebuild_KEEPS_the_NOT_NULLs_it_is_not_lifting(tmp_path, monkeypatch):
    """Only `run_id` loses its NOT NULL. Carrying the constraints across wholesale is what
    stops a rebuild quietly relaxing the rest of the table.

    ⚠ Watched RED by dropping the `name != "run_id"` guard, which lifts every NOT NULL.
    """
    conn = _legacy(tmp_path, monkeypatch)
    cols = _cols(conn)
    assert cols["status"][3] == 1
    assert cols["created_at"][3] == 1
    assert cols["num_simulations"][3] == 1
    assert cols["num_simulations"][4] == "10000", "the default must survive the rebuild"


def test_running_it_TWICE_changes_nothing(tmp_path, monkeypatch):
    """It runs on every startup. A rebuild that fired each time would rewrite the table
    forever, and a bug in it would be a bug on every boot rather than once."""
    conn = _legacy(tmp_path, monkeypatch)
    conn.execute(
        "INSERT INTO stress_tests (stress_test_id, stack_id, status, created_at) "
        "VALUES ('st_keep', 'stk_1', 'running', 1)"
    )
    conn.commit()
    before = _cols(conn)
    conn.close()

    lab_db.init_db()
    conn = sqlite3.connect(lab_db.DB_PATH)
    assert _cols(conn) == before
    assert conn.execute(
        "SELECT stack_id FROM stress_tests WHERE stress_test_id = 'st_keep'"
    ).fetchone() == ("stk_1",)
