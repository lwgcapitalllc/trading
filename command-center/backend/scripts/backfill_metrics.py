"""
One-time backfill of file-derivable metrics onto existing completed runs.

Recomputes ONLY what can be derived from already-stored result files (equity_curve.json,
daily_pnl.json). Anything not derivable stays as-is (null) — never fabricated.

Idempotent and safe to re-run:
  * Sharpe trio (sharpe / platform_sharpe / sharpe_low_sample): the canonical-Sharpe
    substitution moves the platform value into platform_sharpe and writes the daily-√252
    value. This runs ONLY when platform_sharpe IS NULL (not yet backfilled). That null guard
    is what makes a second pass a no-op — otherwise it would move the already-canonical value
    into platform_sharpe and corrupt it.
  * profit_concentration_pct: deterministic recompute from daily_pnl → same value every run.
  * contract_cap_status (on evaluations): recomputed via the shared evaluator helper from the
    run's stored sizes. Deterministic, and ONLY the contract_cap_status column is written —
    the verdict and every other evaluation field are left untouched (no re-grading of history).

Run from the backend dir:  python3 scripts/backfill_metrics.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import lab_db
from services.metrics import daily_sharpe, profit_concentration_pct, SHARPE_LOW_SAMPLE_DAYS
from services.evaluator import compute_contract_cap_status


def _load_json(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def backfill(dry_run: bool = False) -> dict:
    conn = lab_db._connect()
    runs = conn.execute(
        "SELECT run_id, sharpe, platform_sharpe, net_pnl, max_drawdown, runner, instrument, "
        "       equity_curve_path, daily_pnl_path "
        "FROM backtest_runs WHERE status = 'complete'"
    ).fetchall()

    stats = {
        "complete_runs": len(runs),
        "sharpe_backfilled": 0,
        "sharpe_already_done": 0,
        "concentration_set": 0,
        "concentration_null": 0,
        "no_daily_file": 0,
        "contract_status_updated": 0,
        "contract_status_changed": 0,
        "runs_without_evals": 0,
    }

    for r in runs:
        run = dict(r)
        run_id = run["run_id"]
        daily_pnl = _load_json(run["daily_pnl_path"])

        # ── Part A: run-row fields from daily_pnl ──────────────────────────────
        if daily_pnl is None:
            stats["no_daily_file"] += 1
        else:
            conc = profit_concentration_pct(daily_pnl)
            stats["concentration_set" if conc is not None else "concentration_null"] += 1
            sets, params = ["profit_concentration_pct = ?"], [conc]

            if run["platform_sharpe"] is None:   # not yet backfilled → safe to move/compute
                sets += ["platform_sharpe = ?", "sharpe = ?", "sharpe_low_sample = ?"]
                params += [run["sharpe"], daily_sharpe(daily_pnl),
                           1 if len(daily_pnl) < SHARPE_LOW_SAMPLE_DAYS else 0]
                stats["sharpe_backfilled"] += 1
            else:
                stats["sharpe_already_done"] += 1

            if not dry_run:
                conn.execute(
                    f"UPDATE backtest_runs SET {', '.join(sets)} WHERE run_id = ?",
                    (*params, run_id),
                )

        # ── Part B: contract_cap_status on this run's evaluations ──────────────
        evals = conn.execute(
            "SELECT eval_id, ruleset_id, contract_cap_status FROM evaluations WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        if not evals:
            stats["runs_without_evals"] += 1
            continue

        equity = _load_json(run["equity_curve_path"]) or []
        trade_sizes = [t.get("size") for t in equity if t.get("size") is not None]
        runner = run.get("runner") or "ninjatrader"
        instrument = run.get("instrument") or ""

        for ev in evals:
            ev = dict(ev)
            ruleset = lab_db.get_ruleset(ev["ruleset_id"])
            if ruleset is None:
                continue
            status, _ = compute_contract_cap_status(
                ruleset.get("max_contracts"), runner, instrument, trade_sizes
            )
            stats["contract_status_updated"] += 1
            if status != ev["contract_cap_status"]:
                stats["contract_status_changed"] += 1
            if not dry_run:
                conn.execute(
                    "UPDATE evaluations SET contract_cap_status = ? WHERE eval_id = ?",
                    (status, ev["eval_id"]),
                )

    if not dry_run:
        conn.commit()
    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    lab_db.init_db()  # ensure schema/columns exist before touching anything
    stats = backfill(dry_run=dry_run)

    mode = "DRY RUN — no writes" if dry_run else "applied"
    print(f"\nBackfill ({mode}):")
    print(f"  completed runs scanned         : {stats['complete_runs']}")
    print(f"  ── Sharpe trio ─────────────────")
    print(f"    backfilled (platform was null): {stats['sharpe_backfilled']}")
    print(f"    skipped (already backfilled)  : {stats['sharpe_already_done']}")
    print(f"  ── Profit concentration ────────")
    print(f"    set (had positive profit)     : {stats['concentration_set']}")
    print(f"    null (no positive profit)     : {stats['concentration_null']}")
    print(f"  ── Skipped (no daily_pnl file)  : {stats['no_daily_file']}")
    print(f"  ── Contract-cap status ─────────")
    print(f"    evaluations refreshed         : {stats['contract_status_updated']}")
    print(f"    of which value changed        : {stats['contract_status_changed']}")
    print(f"    runs with no evaluations      : {stats['runs_without_evals']}")
    print()


if __name__ == "__main__":
    main()
