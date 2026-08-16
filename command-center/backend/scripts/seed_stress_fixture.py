"""Seed one Monte-Carlo-only stress test, so `frontend/tests/stress.spec.ts` has a real payload.

🔴 WHY THIS EXISTS. That suite mocks eleven states the live box cannot produce — a compounding run
graded on percent, a walk-forward that crashed, a shift whose child backtest failed — and it builds
every one of them by MUTATING A REAL `/stress-tests/{id}` RESPONSE rather than by hand-writing a
fixture. That discipline is right (a hand-written fixture drifts from the Pydantic model and then
tests a shape the server never sends) and it has one cost: **the suite needs at least one stress
test to exist in the lab.**

On 2026-08-16 the `stress_tests` table held ZERO rows, and all eleven checks failed with
`no stress tests in the lab to mutate` — a whole feature's regression suite silently switched off,
against a page whose own audit found 24 defects. The suite was not wrong and neither was the page.
This script is the missing half: **the fixture is restorable in one command rather than by
remembering how the feature is driven.**

What it does, and what it deliberately does NOT do:

- Monte Carlo ONLY. No walk-forward and no sensitivity, so it spawns no child backtests, touches
  no VPS, and takes no platform lock. Seconds, not the ~70 minutes a full test costs.
- ⚠ **The Telegram sender is stubbed.** Completion notifies `notify.HEALTH`, and a fixture is not a
  result anybody asked to be told about — an ops channel that pings for test scaffolding is one
  people mute, and a muted channel is worth less than none.
- ⚠ It runs the REAL `run_stress_test_task`, not a shortcut. A row written by a shortcut would be a
  hand-written fixture wearing a database row's clothes, which is the exact thing the suite avoids.
- ⚠ It REFUSES when the lab already holds one — the suite takes whichever row is first, so a second
  is not a second fixture, just noise on the user's Stress Tests page. Pass `--force` to add one
  anyway.
- The row is a normal lab artefact: it shows on the Stress Tests page and is deleted from there.

Run from the backend dir (any COMPLETE run with >= 100 trades will do; it defaults to the one with
the most trades, which is the only property the suite cares about):

    python3 scripts/seed_stress_fixture.py
    python3 scripts/seed_stress_fixture.py --run 831ec44195ce
"""

import argparse
import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import lab_db, notify  # noqa: E402
from services.stress_tester import (  # noqa: E402
    MIN_TRADES_FOR_STRESS,
    phases_requested,
    run_stress_test_task,
)


def _pick_run() -> str:
    """The complete run with the most trades. Trade count is the ONLY thing the gate reads."""
    eligible = [
        r
        for r in lab_db.list_runs(status="complete")
        if (r.get("trade_count") or 0) >= MIN_TRADES_FOR_STRESS
    ]
    if not eligible:
        raise SystemExit(
            f"No complete run in the lab has the {MIN_TRADES_FOR_STRESS} trades a stress test "
            f"needs. Run a longer backtest first — this is the same floor the API enforces, and "
            f"it is about the Monte Carlo tail percentiles, not about this script."
        )
    return max(eligible, key=lambda r: r["trade_count"])["run_id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run", help="run_id to stress; defaults to the completed run with most trades"
    )
    ap.add_argument("--force", action="store_true", help="seed even if the lab already holds one")
    args = ap.parse_args()

    existing = lab_db.list_stress_tests()
    if existing and not args.force:
        print(
            f"The lab already holds {len(existing)} stress test(s) — `stress.spec.ts` mutates "
            f"whichever comes first, so it is already covered. Nothing to do (use --force to add "
            f"one anyway)."
        )
        return

    run_id = args.run or _pick_run()
    run = lab_db.get_run(run_id)
    if not run or run.get("status") != "complete":
        raise SystemExit(f"{run_id} is not a complete run")
    trades = run.get("trade_count") or 0
    if trades < MIN_TRADES_FOR_STRESS:
        raise SystemExit(f"{run_id} has {trades} trades; the floor is {MIN_TRADES_FOR_STRESS}")

    # A fixture is not a result. See the module docstring.
    notify.send_telegram = lambda *a, **k: None

    st_id = uuid.uuid4().hex[:16]
    lab_db.insert_stress_test(
        {
            "stress_test_id": st_id,
            "run_id": run_id,
            "ruleset_id": None,
            "status": "running",
            "created_at": int(time.time()),
            "num_simulations": 10_000,
            "num_bootstrap": 1_000,
            "walk_forward_windows": 5,
            "phases_requested": phases_requested(False, False),
        }
    )
    print(f"seeding from run {run_id} ({trades} trades) → stress test {st_id}")
    asyncio.run(run_stress_test_task(st_id, False, False))

    row = lab_db.get_stress_test(st_id)
    status = (row or {}).get("status")
    if status != "complete":
        raise SystemExit(
            f"stress test finished {status!r}, not 'complete' — the fixture is no good"
        )
    # ⚠ `grade` is None with no ruleset, and that is CORRECT, not a failure: every grade is a
    # statement about drawdown against a limit, and an unconstrained ruleset states none. The
    # suite's "a completed test with no letter says NOT GRADED" check wants exactly this row.
    print(f"done — status={status} grade={(row or {}).get('grade')!r}")
    print("`cd ../frontend && npx playwright test tests/stress.spec.ts` should now be 11 green.")


if __name__ == "__main__":
    main()
