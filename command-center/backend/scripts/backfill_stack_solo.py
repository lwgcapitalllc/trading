"""Backfill the artefacts a shared stack was never asked to keep, for stacks replayed before
2026-08-10 — the SOLO CONTROL books, and each leg's BLOCKED and MISSED setups.

Both come out of one `run_stack` call, which is why they share a script: the replay is the expensive
part and running it twice to write two files would be the only wasteful way to do this.

`run_stack` has always replayed each leg alone as a control, and `_persist` kept only two scalars
from it (`solo_r`, `solo_closing_balance`). The trades were discarded — so a stack could not answer
"what would the rest of this have made if that strategy never existed", and the page composed that
answer out of the SHARED trades instead. Those are sized off a balance every leg compounded onto,
which is how MPC B-LEG came to read $47,758,999 on a stack and $21,064 standalone over the same
window, on the same 99 trades, at the same 17.8674R.

⚠ This RE-RUNS the replay — it does not recover anything from disk, because nothing was written.
It is `1 + legs` full replays (`run_stack` builds the shared book first), which is the same work a
Rerun does; the difference is that this leaves every stored row, KPI and leg curve untouched and
writes only the missing artefacts.

⚠ **The blocked / missed setups come from the SHARED replay, the solo book from the CONTROL** — the
same split `_persist` uses. A block recorded in the solo replay would sit on a chart beside trades
it never competed with.

⚠ It REFUSES to overwrite a solo book that already exists unless `--force`. A stack replayed after
this landed has the real thing on disk, and re-deriving it from today's code would silently swap a
stored measurement for a fresh one.

Run from the backend dir:
    python3 scripts/backfill_stack_solo.py --stack st_94aeb25f0c
    python3 scripts/backfill_stack_solo.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import lab_db, portfolio_runner  # noqa: E402
from services.portfolio_runner import _LAB_RESULTS_DIR  # noqa: E402


def _settings_for(stack_id: str) -> dict | None:
    s = lab_db.get_stack_settings(stack_id)
    if not s or s.get("mode") != "shared":
        return None
    return dict(s)


def backfill(stack_id: str, *, force: bool = False) -> str:
    # `python_runner` is what puts the monorepo root on `sys.path`, so it has to be imported before
    # anything reaches for `backtest.*` — importing them the other way round is a ModuleNotFoundError.
    from services.python_runner import (
        _build_config,
        _cost_profile,
        _resolve,
        _timeframe_minutes,
        bar_server,
    )

    from backtest.data.source import BarSource
    from backtest.output import build_results
    from backtest.portfolio import LegSpec, run_stack

    settings = _settings_for(stack_id)
    if settings is None:
        return f"{stack_id}: not a shared stack — skipped"

    rows = lab_db.list_stack_runs(stack_id)
    if not rows or any(r["status"] != "complete" for r in rows):
        return f"{stack_id}: legs are not all complete — skipped"

    # ⚠ **The skip is PER ARTEFACT, not per stack.** This script writes two unrelated things now,
    # and a stack can legitimately have one and not the other — the solo books were backfilled
    # earlier the same day, the diagnostics were not. An all-or-nothing guard would make the second
    # backfill impossible without `--force`, i.e. without also re-deriving a stored measurement.
    have_solo = {
        r["strategy_id"] for r in rows if portfolio_runner.solo_book(stack_id, r["strategy_id"])[0]
    }
    have_diag = {
        r["strategy_id"]
        for r in rows
        if (_LAB_RESULTS_DIR / r["run_id"] / "blocked_setups.json").exists()
        or (_LAB_RESULTS_DIR / r["run_id"] / "missed_setups.json").exists()
    }
    if not force and len(have_solo) == len(rows) and len(have_diag) == len(rows):
        return f"{stack_id}: already has everything — skipped (use --force to re-derive)"

    symbol = settings["instrument"]
    tf = _timeframe_minutes(settings)
    # Same pin as the live stack runner: the bar cache is broker-partitioned, so a backfill that
    # resolved the attached terminal would derive a stack's solo legs from another broker's prices.
    df = BarSource(server=bar_server(settings)).load(
        symbol, tf, settings["start_date"], settings["end_date"]
    )
    if df.empty:
        return f"{stack_id}: no bars for {symbol} {tf}m — skipped"

    profile = _cost_profile(settings)
    specs = []
    for r in rows:
        strat = lab_db.get_strategy(r["strategy_id"])
        if not strat:
            return f"{stack_id}: strategy {r['strategy_id']!r} is no longer registered — skipped"
        found = _resolve(strat["class_name"])
        if found is None:
            return f"{stack_id}: no Python strategy class named {strat['class_name']!r} — skipped"
        _, entry = found
        # The leg's OWN stored params, including the pins the router wrote onto the child run, so
        # the control replays the same configuration the shared book did rather than today's
        # defaults. Reading `strategy.default_params` here is the "inherited label was not true"
        # defect this repo already recorded on the optimizer.
        params = r.get("params") or {}
        if isinstance(params, str):
            import json as _json

            params = _json.loads(params)
        config = _build_config(entry["config"], params, symbol)
        specs.append(
            LegSpec(
                name=r["strategy_id"],
                strategy_cls=entry["strategy"],
                config=config,
                df=df,
                cost_profile=profile,
            )
        )

    run = run_stack(
        specs,
        balance=float(settings["account_size"]),
        risk_cap_pct=float(settings["risk_cap_pct"]) / 100.0,
        entry_floor_pct=float(settings.get("entry_floor_pct") or 0.0) / 100.0,
    )

    sdir = portfolio_runner.stack_dir(stack_id)
    sdir.mkdir(parents=True, exist_ok=True)
    run_id_of = {r["strategy_id"]: r["run_id"] for r in rows}
    written = []
    for spec in specs:
        pv = getattr(spec.config, "point_value", 1.0)
        parts = []

        if force or spec.name not in have_solo:
            trades = run.solo_per_leg.get(spec.name, [])
            results = build_results(trades, point_value=pv, initial_capital=run.opening_balance)
            portfolio_runner._write_solo(sdir, spec.name, results)
            parts.append(
                f"solo {len(trades)} trades, "
                f"{sum(getattr(t, 'r', 0.0) for t in trades):+.4f}R, "
                f"${run.solo_closing.get(spec.name, 0.0):,.2f}"
            )

        if force or spec.name not in have_diag:
            # The leg's own diagnostic layers, off the SHARED book. `build_results` is called
            # separately from the solo one because these belong to a different replay — reusing it
            # would file the control's refusals against the shared trade list.
            shared = build_results(
                run.per_leg.get(spec.name, []),
                point_value=pv,
                initial_capital=run.opening_balance,
                blocked=run.blocked_per_leg.get(spec.name),
                missed=run.missed_per_leg.get(spec.name),
            )
            portfolio_runner.write_leg_diagnostics(run_id_of[spec.name], shared)
            # ⚠ **The leg's cached `chart_spec.json` has to go with them.** It is built from these
            # files and then cached for ever, so writing the artefacts without dropping the cache
            # leaves the chart serving a spec that predates them — the reader would see the backfill
            # report a number and the layer still be missing, which reads as the backfill failing.
            (_LAB_RESULTS_DIR / run_id_of[spec.name] / "chart_spec.json").unlink(missing_ok=True)
            parts.append(
                f"{len(shared.get('blocked_setups') or [])} blocked, "
                f"{len(shared.get('missed_setups') or [])} missed"
            )

        written.append(f"{spec.name} ({' · '.join(parts) or 'nothing to do'})")
    return f"{stack_id}: wrote {' · '.join(written)}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stack", help="one stack id")
    ap.add_argument("--all", action="store_true", help="every shared stack")
    ap.add_argument("--force", action="store_true", help="overwrite an existing solo book")
    args = ap.parse_args()

    if args.all:
        ids = [s["stack_id"] for s in lab_db.list_stacks()]
    elif args.stack:
        ids = [args.stack]
    else:
        ap.error("pass --stack <id> or --all")

    for sid in ids:
        print(backfill(sid, force=args.force), flush=True)


if __name__ == "__main__":
    main()
