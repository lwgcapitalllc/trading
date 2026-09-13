"""Move lab rows off the four strategy ids the 2026-09-03 de-brand retired.

The rename moved `strategies/python/mpc_sos_fade` to `sos_fade`, and likewise `mpc_bleg` to
`b_leg`, `mpc_bos` to `bos` and `mpc_realign` to `realign`. A strategy's lab id IS its package
folder, so every clone's database kept rows pointing at the old ids, and a Retry of such a run asks
the runner for a class the code no longer has: "no Python strategy class named 'MpcSosFadeStrategy'".
`docs/DEBRAND_RENAME_PLAN.md` section 4.2 is the plan.

🔴 **That plan's SQL was itself caught by the rename's find-and-replace** and now reads
`WHERE strategy_id = 'sos_fade'` — moving rows onto the id they already have. Typed as written it
does nothing and reports success. This script carries the old ids as data instead.

What it does, after a backup, in one transaction:

  * runs and optimizations filed under an old id move to the new id. Their settings are unchanged:
    every stored key is still declared by today's configs (checked on the one unmigrated clone,
    2026-09-13, 9 runs, 0 undeclared keys);
  * a dependent stack leg's recorded parent moves to the new id;
  * the old ids' version history and strategy rows are deleted. The scanner owns the new rows.

Each stack's `reports/lab/<stack>/solo/<id>/` folder is keyed by strategy id, so it is renamed too.

⚠ **All or nothing.** Every refusal is checked before the first write: a new id the scanner has not
registered, or a solo folder already present under the new name, refuses the whole run.
⚠ **The folders are renamed first and put back if the database write fails**, so the two never
disagree about which id a stack's solo book is filed under.
⚠ **Dry run by default**; `--apply` writes and needs `--backup`, which it will not overwrite.
Idempotent: a second apply finds nothing to do.

Run from the backend dir (the app may stay up):
    .venv/bin/python scripts/migrate_debrand_ids.py
    .venv/bin/python scripts/migrate_debrand_ids.py --apply --backup ~/lab.db.pre-debrand
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

RENAMES = {
    "mpc_sos_fade": "sos_fade",
    "mpc_bleg": "b_leg",
    "mpc_bos": "bos",
    "mpc_realign": "realign",
}

_BACKEND = Path(__file__).resolve().parent.parent
DEFAULT_DB = _BACKEND / "data" / "lab.db"
DEFAULT_RESULTS = _BACKEND / "reports" / "lab"

# (table, column) holding a strategy id that must MOVE to the new id.
_MOVES = (
    ("backtest_runs", "strategy_id"),
    ("optimizations", "strategy_id"),
    ("stack_members", "source"),
)


@dataclass
class Plan:
    moves: dict = field(default_factory=dict)  # (table, old) -> rows
    versions: dict = field(default_factory=dict)  # old -> rows
    strategies: list = field(default_factory=list)  # old ids with a row
    folders: list = field(default_factory=list)  # (old path, new path)
    refusals: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.moves or self.versions or self.strategies or self.folders)


def connect(db_path: Path) -> sqlite3.Connection:
    """The same foreign-key enforcement the app runs with, so a wrong step order raises."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _count(conn: sqlite3.Connection, table: str, column: str, value: str) -> int:
    if column not in _columns(conn, table):
        return 0
    sql = f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" = ?'
    return conn.execute(sql, (value,)).fetchone()[0]


def plan(conn: sqlite3.Connection, results_dir: Path) -> Plan:
    p = Plan()
    for old, new in RENAMES.items():
        moving = 0
        for table, column in _MOVES:
            n = _count(conn, table, column, old)
            if n:
                p.moves[(table, old)] = n
                moving += n
        versions = _count(conn, "strategy_versions", "strategy_id", old)
        if versions:
            p.versions[old] = versions
        if _count(conn, "strategies", "id", old):
            p.strategies.append(old)
        if moving and not _count(conn, "strategies", "id", new):
            p.refusals.append(
                f"'{old}' has {moving} row(s) to move, but '{new}' is not registered in the lab. "
                "Press Scan Strategies, then run this again."
            )
        for src in sorted(results_dir.glob(f"*/solo/{old}")):
            dst = src.with_name(new)
            if dst.exists():
                p.refusals.append(f"{src} cannot be renamed: {dst} already exists.")
            else:
                p.folders.append((src, dst))
    return p


def apply(conn: sqlite3.Connection, p: Plan) -> None:
    if p.refusals:
        raise RuntimeError("refused: " + " | ".join(p.refusals))
    renamed = []
    try:
        for src, dst in p.folders:
            src.rename(dst)
            renamed.append((src, dst))
        with conn:
            for old, new in RENAMES.items():
                for table, column in _MOVES:
                    if column in _columns(conn, table):
                        sql = f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?'
                        conn.execute(sql, (new, old))
                conn.execute("DELETE FROM strategy_versions WHERE strategy_id = ?", (old,))
                conn.execute("DELETE FROM strategies WHERE id = ?", (old,))
    except Exception:
        for src, dst in reversed(renamed):
            dst.rename(src)
        raise


def backup(conn: sqlite3.Connection, path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"{path} already exists; pick another backup path.")
    dst = sqlite3.connect(str(path))
    try:
        conn.backup(dst)
    finally:
        dst.close()


def describe(p: Plan) -> list:
    lines = []
    for (table, old), n in sorted(p.moves.items()):
        lines.append(f"move {n} {table} row(s): {old} -> {RENAMES[old]}")
    for old, n in sorted(p.versions.items()):
        lines.append(f"delete {n} version-history row(s) of {old}")
    for old in p.strategies:
        lines.append(f"delete strategy row {old}")
    for src, dst in p.folders:
        lines.append(f"rename {src} -> {dst.name}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--apply", action="store_true", help="write; without it nothing changes")
    ap.add_argument("--backup", type=Path, help="where to copy the database first (required)")
    args = ap.parse_args(argv)

    conn = connect(args.db)
    p = plan(conn, args.results)
    for line in describe(p):
        print(line)
    if p.refusals:
        for r in p.refusals:
            print("REFUSED:", r)
        return 2
    if p.empty:
        print("Nothing to migrate.")
        return 0
    if not args.apply:
        print("Dry run: nothing written. Add --apply --backup <path> to write.")
        return 0
    if args.backup is None:
        print("REFUSED: --apply needs --backup <path>.")
        return 2
    backup(conn, args.backup.expanduser())
    print(f"backup written: {args.backup.expanduser()}")
    apply(conn, p)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
