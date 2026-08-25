"""Move a FLAT bar/tick cache into its broker's folder — the one-time migration for the
2026-08-24 partition.

    python backtest/tools/file_cache_by_broker.py --server VantageMarkets-Demo --dry-run
    python backtest/tools/file_cache_by_broker.py --server VantageMarkets-Demo

**Why this is a tool a human runs, and not an automatic migration.** The flat cache carries no
record of which broker filled it — that is the entire defect being fixed. Guessing would write
the very claim the partition exists to stop anyone making: a folder labelled with a broker whose
prices may never have been in it. So the server name is a REQUIRED argument, and typing it is a
person asserting a fact they know.

⚠ **It refuses to merge into an existing partition.** If `cache/<server>/` already holds a file
this would overwrite, the tool stops and names it. Two different pulls landing in one folder is
the same silent mixing at one level down.

⚠ **It moves, never copies** — gold's tick cache alone is ~1 GB here, and a copy would leave a
flat shadow that a future reader could mistake for live data.

⚠ **Nothing re-pulls if you skip this.** An unmigrated flat cache is simply invisible to the new
layout: every read is a miss and the bars come down again, correctly, from whatever broker is
attached. The cost of skipping is time, never a wrong number — which is the direction this repo
wants a migration to fail in.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.data.cache import _default_cache_dir, _safe  # noqa: E402

#: A flat cache entry is one of these. Anything else in the cache dir is left alone — the
#: partition folders themselves, and any file a future feature parks there.
_BAR_SUFFIXES = (".csv", ".meta.json", ".ranges.json", ".lock")


def _flat_entries(base: Path) -> list[Path]:
    """Top-level cache files that belong to a broker, plus the flat `ticks/` folder."""
    out = [p for p in sorted(base.glob("*")) if p.is_file() and p.name.endswith(_BAR_SUFFIXES)]
    ticks = base / "ticks"
    if ticks.is_dir():
        out.append(ticks)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--server",
        required=True,
        help="the MT5 server name these bars came from, e.g. VantageMarkets-Demo. "
        "Read it off the agent's /status, or MT5's Journal tab.",
    )
    ap.add_argument("--cache-dir", default=None, help="override the cache base dir")
    ap.add_argument("--dry-run", action="store_true", help="say what would move, move nothing")
    args = ap.parse_args(argv)

    base = Path(args.cache_dir) if args.cache_dir else _default_cache_dir()
    if not base.is_dir():
        print(f"no cache at {base} — nothing to file")
        return 0

    dest = base / _safe(args.server)
    entries = _flat_entries(base)
    if not entries:
        print(f"no flat cache entries in {base} — already filed, or nothing pulled yet")
        return 0

    # Refuse BEFORE moving anything: a half-done migration is worse than none, because the
    # partition would then hold a subset that looks complete.
    clashes = [e.name for e in entries if (dest / e.name).exists()]
    if clashes:
        print(f"REFUSING: {dest} already holds {len(clashes)} of these entries:", file=sys.stderr)
        for name in clashes[:10]:
            print(f"  {name}", file=sys.stderr)
        print(
            "Two pulls merging into one folder is the same silent mixing this partition "
            "exists to stop. Resolve by hand.",
            file=sys.stderr,
        )
        return 1

    total = sum(
        sum(f.stat().st_size for f in e.rglob("*") if f.is_file())
        if e.is_dir()
        else e.stat().st_size
        for e in entries
    )
    print(f"{len(entries)} entries, {total / 1e9:.2f} GB")
    print(f"  from {base}")
    print(f"  to   {dest}")
    if args.dry_run:
        for e in entries:
            print(f"  would move {e.name}")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    for e in entries:
        shutil.move(str(e), str(dest / e.name))
        print(f"  moved {e.name}")

    # COPIED, not moved, and it is the one exception. `history_floors.json` is keyed
    # `(server, symbol, timeframe)` INSIDE the file, so it is already multi-broker and the flat
    # copy stays correct for anything else that reads the base dir. Leaving the partition without
    # it would silently re-probe every floor — minutes of agent calls to re-learn a fact that is
    # sitting right there, and this repo has already paid for a binary search it did not need.
    floors = base / "history_floors.json"
    if floors.is_file() and not (dest / floors.name).exists():
        shutil.copy2(str(floors), str(dest / floors.name))
        print(f"  copied {floors.name} (multi-broker by key — the flat copy stays valid)")

    print(f"done — {args.server} history now lives in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
