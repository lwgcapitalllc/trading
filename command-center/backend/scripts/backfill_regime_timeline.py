"""
Backfill the full-calendar regime timeline onto existing completed runs.

Runs that completed before `regime_timeline.json` existed only ever had regime labels on the
days they TRADED, so the equity charts had to carry the last traded day's tag across every
quiet stretch — and two runs of the same strategy over the same window disagreed about what
regime the market was in. This writes the honest timeline (every trading day in the run's
window, classified once) into each run's report dir.

Unlike backfill_metrics.py this is NOT file-derivable — it fetches OHLC for the window and
runs the canonical classifier — so it's a separate, opt-in script.

Idempotent: a run that already has a non-empty regime_timeline.json is skipped unless --force.
OHLC comes from the same cached fetchers the live path uses, so re-runs are cheap.

Run from the backend dir:  python3 scripts/backfill_regime_timeline.py [--force] [--run-id ID]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import lab_db
from services.backtest_runner import LAB_RESULTS_DIR, build_regime_timeline_and_tag


def backfill(force: bool = False, only_run_id: str | None = None) -> dict:
    conn = lab_db._connect()
    rows = conn.execute(
        "SELECT run_id, instrument, start_date, end_date, runner, daily_pnl_path "
        "FROM backtest_runs WHERE status = 'complete'"
    ).fetchall()
    conn.close()

    written = skipped = failed = 0
    for row in rows:
        run_id = row["run_id"]
        if only_run_id and run_id != only_run_id:
            continue

        run_dir = LAB_RESULTS_DIR / run_id
        out = run_dir / "regime_timeline.json"
        if out.exists() and not force:
            try:
                if json.loads(out.read_text()):
                    skipped += 1
                    continue
            except Exception:
                pass  # unreadable → rewrite it

        if not (row["start_date"] and row["end_date"]):
            skipped += 1
            continue

        daily_pnl = []
        if row["daily_pnl_path"] and Path(row["daily_pnl_path"]).exists():
            try:
                daily_pnl = json.loads(Path(row["daily_pnl_path"]).read_text())
            except Exception:
                daily_pnl = []

        try:
            timeline, tagged = build_regime_timeline_and_tag(
                row["instrument"],
                row["start_date"],
                row["end_date"],
                daily_pnl,
                row["runner"] or "ninjatrader",
            )
        except Exception as exc:
            print(f"  ✗ {run_id}: {exc}")
            failed += 1
            continue

        if not timeline:
            print(
                f"  ✗ {run_id}: no OHLC for {row['instrument']} "
                f"[{row['start_date']} → {row['end_date']}]"
            )
            failed += 1
            continue

        run_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(timeline, default=str))
        # Re-tag daily_pnl off the same map so the table and the bands can't disagree.
        if daily_pnl and row["daily_pnl_path"]:
            Path(row["daily_pnl_path"]).write_text(json.dumps(tagged, default=str))
        print(f"  ✓ {run_id}: {len(timeline)} days ({row['instrument']})")
        written += 1

    return {"written": written, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    run_id = None
    if "--run-id" in args:
        run_id = args[args.index("--run-id") + 1]
    print(f"Backfilling regime timelines (force={force}, run_id={run_id or 'all'})…")
    print(backfill(force=force, only_run_id=run_id))
