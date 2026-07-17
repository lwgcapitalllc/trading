"""A4 — the local sweep. Run one strategy over N parameter sets, in memory, across CPU cores.

**Why this exists.** NT8 and MT5 optimize by driving their own terminal on the VPS: one physical
Strategy Analyzer / Strategy Tester, one job at a time, held under a platform lock while the grid
runs. A Python strategy has no terminal — it is `engines/` + a strategy package + a cached bar
frame. So its optimizer is a function, not a job on a remote machine: no lock, no deploy, no
compile, and the bars are loaded ONCE for the whole grid instead of re-read per combo.

**What it is not.** It does not know what a "grid" is (min/max/step is the LAB's contract — the lab
expands it and hands us the combos), it does not score, rank, or pick a winner (`objectives.py` and
`_pick_best_run` already do that for every runner), and it does not touch a database. It runs
configs and reports KPIs. That keeps the one thing that is genuinely new here — replaying fast —
separate from the lab lenses that already exist.

**Configs arrive fully built** (`Combo.config`), not as raw param dicts. The caller owns the
JSON→dataclass coercion it already does for single runs, so there is exactly one place that knows
how a lab param dict becomes a strategy config.

**Fill model.** Sweep in `fill_model="bar"` (the default) and validate the winner in tick mode.
Tick mode re-pulls and re-walks real ticks per combo: on the 365d 15m XAUUSD run a single pass is
~1,100s vs ~10s in bar mode, so a 100-combo grid is ~31 hours vs ~2 minutes — while real fills
moved that run's net by 1.3%. Pay the 1.3% once, on the winner, not 100 times on combos you throw
away.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclasses.dataclass(frozen=True)
class Combo:
    """One point in the sweep: the params that varied (the label) + the config to actually run."""

    params: Dict[str, Any]
    config: Any


# Per-worker state. A process pool initializer fills this ONCE per worker, so the bar frame and the
# strategy import are paid per-worker rather than per-combo.
_W: Dict[str, Any] = {}


def _init_worker(monorepo_root: str, module_path: str, df, capital: float) -> None:
    """Runs once per worker process. Its args are plain values (str/float/DataFrame) on purpose:
    they are unpickled BEFORE this body runs, so they must not need `sys.path` to already be set.
    Task args (the Combos, carrying a strategy config class) are unpickled after — by then the path
    below is in place and the strategy package imports cleanly, on spawn as well as fork."""
    import importlib

    if monorepo_root and monorepo_root not in sys.path:
        sys.path.insert(0, monorepo_root)
    entry = getattr(importlib.import_module(module_path), "LAB_STRATEGY")
    _W.update(strategy_cls=entry["strategy"], df=df, capital=capital)


def _run_in_worker(combo: Combo) -> dict:
    return _replay_one(_W["strategy_cls"], _W["df"], _W["capital"], combo)


def _replay_one(strategy_cls, df, capital: float, combo: Combo) -> dict:
    """Replay the whole frame under one config and return {params, kpis}.

    Each combo gets a FRESH strategy and a FRESH engine stack. Reusing either across combos would
    carry state from the previous parameter set into the next one — the results would be a function
    of grid order, which is the kind of bug that produces a plausible number and no error.
    """
    from backtest.output import build_kpis
    from backtest.replay import EngineStack, iter_bars

    strategy = strategy_cls(combo.config, initial_capital=capital)
    if len(df.index) > 1:
        strategy.execution.bar_ms = int(df.index.to_series().diff().min().total_seconds() * 1000)

    stack = EngineStack(strategy.engine_config())
    for bar in iter_bars(df):
        strategy.step(stack.step(bar))

    trades = strategy.execution.trades
    return {"params": dict(combo.params),
            "kpis": build_kpis(trades, initial_capital=capital)}


def default_workers(n_combos: int) -> int:
    """One worker per core, never more than there are combos, always ≥ 1.

    Leaves a core free when the box has several: this runs inside the command-center backend, and a
    sweep that pins every core makes the UI it is reporting progress to unresponsive.
    """
    cores = os.cpu_count() or 1
    return max(1, min(n_combos, cores - 1 if cores > 2 else cores))


def run_sweep(
    *,
    module_path: str,
    df,
    combos: Sequence[Combo],
    initial_capital: float = 10_000.0,
    monorepo_root: Optional[str] = None,
    max_workers: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> List[dict]:
    """Replay `df` once per combo and return [{params, kpis}] — one row per combo, in combo order.

    `module_path` is the strategy package (e.g. "strategies.python.mpc_sos_fade"); workers read its
    `LAB_STRATEGY` for the strategy class. `progress(done, total)` is called from the collecting
    thread only. `should_cancel()` is polled between completions — a cancelled sweep returns the
    rows finished so far rather than raising, because a partial grid is still a real answer.
    """
    combos = list(combos)
    if not combos:
        return []

    total = len(combos)
    workers = max_workers if max_workers is not None else default_workers(total)
    root = monorepo_root or str(_monorepo_root())

    if workers <= 1:
        return _sweep_serial(module_path, root, df, combos, initial_capital, progress, should_cancel)

    results: List[Optional[dict]] = [None] * total
    done = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(root, module_path, df, initial_capital)) as pool:
        futures = {pool.submit(_run_in_worker, c): i for i, c in enumerate(combos)}
        pending = set(futures)
        while pending:
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in finished:
                results[futures[fut]] = fut.result()
                done += 1
                if progress is not None:
                    progress(done, total)
            if should_cancel is not None and should_cancel():
                for fut in pending:
                    fut.cancel()
                break

    return [r for r in results if r is not None]


def _sweep_serial(module_path, root, df, combos, capital, progress, should_cancel) -> List[dict]:
    """The single-worker path — also what the tests drive, since it needs no pickling or spawn."""
    import importlib

    if root and root not in sys.path:
        sys.path.insert(0, root)
    entry = getattr(importlib.import_module(module_path), "LAB_STRATEGY")
    strategy_cls = entry["strategy"]

    out: List[dict] = []
    for i, combo in enumerate(combos, 1):
        if should_cancel is not None and should_cancel():
            break
        out.append(_replay_one(strategy_cls, df, capital, combo))
        if progress is not None:
            progress(i, len(combos))
    return out


def _monorepo_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
