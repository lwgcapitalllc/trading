"""The de-brand migration moves lab rows off the retired strategy ids, and refuses before writing.

It runs against the REAL schema (`fresh_db` builds it through `init_db`), with the app's own
foreign-key enforcement on, so a step taken in the wrong order raises here the way it would on a
live database rather than passing against a table with no constraints.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_debrand_ids.py"
_spec = importlib.util.spec_from_file_location("migrate_debrand_ids", _SCRIPT)
mig = importlib.util.module_from_spec(_spec)
# A dataclass looks its own module up in sys.modules while the class is being built.
sys.modules[_spec.name] = mig
_spec.loader.exec_module(mig)


def _insert(conn: sqlite3.Connection, table: str, **values) -> None:
    """Insert one row, filling every NOT NULL column the caller did not name with a filler of its
    type — so the test states only the fields it is about and still satisfies the real schema."""
    for _cid, name, ctype, notnull, default, pk in conn.execute(f'PRAGMA table_info("{table}")'):
        if name in values or not notnull or default is not None or pk:
            continue
        values[name] = 0 if ("INT" in ctype.upper() or "REAL" in ctype.upper()) else "x"
    cols = ", ".join(f'"{c}"' for c in values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', tuple(values.values()))


@pytest.fixture
def lab(fresh_db, tmp_path):
    """An old SOS Fade row with version history and one run, the new row the scanner made, an
    untouched run on another strategy, and a stack whose solo book is filed under the old id."""
    conn = mig.connect(fresh_db)
    for sid in ("mpc_sos_fade", "sos_fade", "extreme_leg"):
        _insert(conn, "strategies", id=sid, name=sid, class_name=sid, runner="python")
    for v in (1, 2):
        _insert(
            conn, "strategy_versions", strategy_id="mpc_sos_fade", version=v, source_hash=f"h{v}"
        )
    _insert(conn, "backtest_runs", run_id="old_run", strategy_id="mpc_sos_fade")
    _insert(conn, "backtest_runs", run_id="other_run", strategy_id="extreme_leg")
    conn.commit()
    results = tmp_path / "reports"
    (results / "st_1" / "solo" / "mpc_sos_fade").mkdir(parents=True)
    (results / "st_1" / "solo" / "mpc_sos_fade" / "equity_curve.json").write_text("[]")
    return conn, results


def _strategy_of(conn, run_id):
    return conn.execute(
        "SELECT strategy_id FROM backtest_runs WHERE run_id = ?", (run_id,)
    ).fetchone()[0]


def test_apply_moves_the_run_and_removes_the_retired_rows(lab):
    """Mutations killed: dropping the run UPDATE (the strategy delete then raises on the foreign
    key), dropping the version delete (same), and skipping the folder rename."""
    conn, results = lab
    mig.apply(conn, mig.plan(conn, results))
    assert _strategy_of(conn, "old_run") == "sos_fade"
    assert _strategy_of(conn, "other_run") == "extreme_leg"
    assert (
        conn.execute("SELECT COUNT(*) FROM strategies WHERE id = 'mpc_sos_fade'").fetchone()[0] == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM strategy_versions WHERE strategy_id = 'mpc_sos_fade'"
        ).fetchone()[0]
        == 0
    )
    assert (results / "st_1" / "solo" / "sos_fade" / "equity_curve.json").is_file()
    assert not (results / "st_1" / "solo" / "mpc_sos_fade").exists()


def test_a_dry_run_reports_the_work_and_writes_nothing(lab):
    conn, results = lab
    p = mig.plan(conn, results)
    assert p.moves == {("backtest_runs", "mpc_sos_fade"): 1}
    assert p.versions == {"mpc_sos_fade": 2}
    assert p.strategies == ["mpc_sos_fade"]
    assert len(p.folders) == 1
    assert _strategy_of(conn, "old_run") == "mpc_sos_fade"
    assert (results / "st_1" / "solo" / "mpc_sos_fade").exists()


def test_a_second_apply_finds_nothing_to_do(lab):
    conn, results = lab
    mig.apply(conn, mig.plan(conn, results))
    again = mig.plan(conn, results)
    assert again.empty and not again.refusals


def test_it_refuses_when_the_new_id_was_never_scanned_and_writes_nothing(lab):
    """Moving a run onto an id with no strategy row would break the foreign key, or worse, leave a
    run filed under a strategy the lab cannot resolve. Mutation killed: dropping the check."""
    conn, results = lab
    conn.execute("DELETE FROM strategies WHERE id = 'sos_fade'")
    conn.commit()
    p = mig.plan(conn, results)
    assert any("Scan Strategies" in r for r in p.refusals)
    with pytest.raises(RuntimeError, match="refused"):
        mig.apply(conn, p)
    assert _strategy_of(conn, "old_run") == "mpc_sos_fade"
    assert (results / "st_1" / "solo" / "mpc_sos_fade").exists()


def test_it_refuses_a_folder_already_present_under_the_new_name(lab):
    """Renaming onto an existing folder would merge two stacks' solo books or fail half way.
    Mutation killed: dropping the existence check."""
    conn, results = lab
    (results / "st_1" / "solo" / "sos_fade").mkdir()
    p = mig.plan(conn, results)
    assert any("already exists" in r for r in p.refusals)
    with pytest.raises(RuntimeError):
        mig.apply(conn, p)
    assert _strategy_of(conn, "old_run") == "mpc_sos_fade"


def test_a_failed_database_write_puts_the_folders_back(lab, monkeypatch):
    """The folders move first; if the transaction then fails they must return, or the solo book
    is filed under an id the database never adopted. Mutation killed: dropping the revert."""
    conn, results = lab
    p = mig.plan(conn, results)
    monkeypatch.setattr(mig, "RENAMES", {**mig.RENAMES, "mpc_sos_fade": None})
    with pytest.raises(sqlite3.IntegrityError):
        mig.apply(conn, p)
    assert (results / "st_1" / "solo" / "mpc_sos_fade").exists()
    assert not (results / "st_1" / "solo" / "sos_fade").exists()
    assert _strategy_of(conn, "old_run") == "mpc_sos_fade"


def test_the_backup_holds_the_database_as_it_was(lab, tmp_path):
    conn, results = lab
    dest = tmp_path / "lab.db.bak"
    mig.backup(conn, dest)
    mig.apply(conn, mig.plan(conn, results))
    saved = sqlite3.connect(str(dest))
    assert (
        saved.execute("SELECT strategy_id FROM backtest_runs WHERE run_id = 'old_run'").fetchone()[
            0
        ]
        == "mpc_sos_fade"
    )
    with pytest.raises(FileExistsError):
        mig.backup(conn, dest)


def test_main_writes_nothing_without_apply_and_refuses_apply_without_a_backup(lab, fresh_db):
    conn, results = lab
    assert mig.main(["--db", str(fresh_db), "--results", str(results)]) == 0
    assert mig.main(["--db", str(fresh_db), "--results", str(results), "--apply"]) == 2
    assert _strategy_of(conn, "old_run") == "mpc_sos_fade"
