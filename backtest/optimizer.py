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


def _rebuild_combo(params: Dict[str, Any], module_name: str, qualname: str, values: dict):
    """Rebuild a Combo in the WORKER, resolving the config class through the worker's own import.

    Paired with `Combo.__reduce__`. Kept module-level because pickle has to be able to name it.
    """
    import importlib

    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return Combo(params=params, config=obj(**values))


@dataclasses.dataclass(frozen=True)
class Combo:
    """One point in the sweep: the params that varied (the label) + the config to actually run."""

    params: Dict[str, Any]
    config: Any

    def __reduce__(self):
        """Cross a process boundary as FIELD VALUES plus the config class's NAME, never as a
        reference to the parent's class object.

        🔴 A dataclass instance pickles by reference, and the backend REPLACES strategy classes
        while a sweep is in flight: `services/strategy_import.py` drops and re-imports the whole
        `strategies.python` namespace before every scan and every run, so that what you read is
        what is on disk. A grid builds its configs from one import and then spends minutes loading
        bars; anything that re-imports in that window makes the name stop resolving to the object
        the combos hold, and the whole sweep dies at the first pickle with "it's not the same
        object as". Measured 2026-09-20: grid `opt_2d74db78e9`, 108 combos, zero ran.

        Rebuilding is also the HONEST model. A worker is a separate process that imports the
        package itself; it never shared a class object with the parent, and the old behaviour only
        worked when the two happened to be looking at the same one.

        ⚠ `init=False` fields are NOT carried — the class recomputes them in `__post_init__`, and
        a derived value shipped as a keyword would raise. ⚠ The field VALUES still pickle normally,
        so a config holding a nested instance of another re-imported class has the same problem one
        level down; nothing here does today, and the failure would name that class.
        Anything that is not a dataclass falls back to ordinary pickling.
        """
        if not dataclasses.is_dataclass(self.config):
            return (self.__class__, (self.params, self.config))
        cls = type(self.config)
        values = {
            f.name: getattr(self.config, f.name) for f in dataclasses.fields(self.config) if f.init
        }
        return (_rebuild_combo, (self.params, cls.__module__, cls.__qualname__, values))


# Per-worker state. A process pool initializer fills this ONCE per worker, so the bar frame and the
# strategy import are paid per-worker rather than per-combo.
_W: Dict[str, Any] = {}


def _init_worker(
    monorepo_root: str,
    module_path: str,
    df,
    capital: float,
    cost_profile=None,
    extract=None,
    fast_df=None,
) -> None:
    """Runs once per worker process. Its args are plain values (str/float/DataFrame) on purpose:
    they are unpickled BEFORE this body runs, so they must not need `sys.path` to already be set.
    Task args (the Combos, carrying a strategy config class) are unpickled after — by then the path
    below is in place and the strategy package imports cleanly, on spawn as well as fork."""
    import importlib

    if monorepo_root and monorepo_root not in sys.path:
        sys.path.insert(0, monorepo_root)
    entry = importlib.import_module(module_path).LAB_STRATEGY
    _W.update(
        strategy_cls=entry["strategy"],
        df=df,
        fast_df=fast_df,
        capital=capital,
        cost_profile=cost_profile,
        extract=extract,
    )


def _run_in_worker(combo: Combo) -> dict:
    return _replay_one(
        _W["strategy_cls"],
        _W["df"],
        _W["capital"],
        combo,
        _W.get("cost_profile"),
        _W.get("extract"),
        _W.get("fast_df"),
    )


def _refuse_unreplayable(config, fast_df=None, strategy_cls=None) -> None:
    """Refuse a config this sweep structurally cannot run.

    A sweep replays ONE frame unless the caller HANDS IT A SECOND (`fast_df`, added 2026-09-20).
    `sos_fade`'s `exec_secondary` (default ON since 2026-08-07) needs that second stream via
    `run_dual`; without it there is nowhere here to get one. The
    dangerous option is not refusing — it is replaying single-stream, because every combo then
    comes back primary-only and is ranked against a baseline that HAS re-entries, and the winner
    is handed to a validation run that does too. That is a comparison whose two sides were
    measured on different books, which is this repo's most-repeated defect.

    Same call `reprice.py` makes about `bid_ask_fills`: a thing this shape cannot compute is
    REFUSED and NAMED, never approximated.
    """
    if getattr(config, "exec_secondary", False) and fast_df is None:
        raise ValueError(
            "exec_secondary is on and a sweep cannot run it: the 1m re-entry needs a second bar "
            "stream (run_dual) and this replays one frame. Every combo would be primary-only "
            "while the run it is compared against is not. Set exec_secondary=False for the "
            "sweep, or give the sweep a 1m frame."
        )
    if (
        getattr(config, "exec_secondary", False)
        and strategy_cls is not None
        and not hasattr(strategy_cls, "run_dual")
    ):
        # A fast frame was supplied to a strategy that has no second-stream driver. Refusing
        # rather than ignoring the frame: silently replaying single-stream is the exact failure
        # the branch above exists to stop, and arriving at it by the other road makes it no safer.
        raise ValueError(
            f"{getattr(strategy_cls, '__name__', strategy_cls)} sets exec_secondary=True and a "
            f"fast frame was supplied, but it has no run_dual() to step the second stream. Every "
            f"combo would be primary-only."
        )


def _replay_one(
    strategy_cls,
    df,
    capital: float,
    combo: Combo,
    cost_profile=None,
    extract=None,
    fast_df=None,
) -> dict:
    """Replay the whole frame under one config and return {params, kpis}.

    Each combo gets a FRESH strategy and a FRESH engine stack. Reusing either across combos would
    carry state from the previous parameter set into the next one — the results would be a function
    of grid order, which is the kind of bug that produces a plausible number and no error.

    `extract` is an optional callable handed the FINISHED strategy, whose return value is attached
    to the row as `extra`. It exists so a caller needing something the KPI dict does not carry —
    an out-of-sample split needs each trade's own entry time, and `build_kpis` reports totals — can
    have it WITHOUT reproducing this function. That matters more than it looks: this is not
    `strategy.run()`, it sets `bar_ms` off the frame and calls `finalize` afterwards, and a second
    bar loop that forgets either is wrong in silence (see `backtest/CLAUDE.md`). Omit it and the
    row is byte-identical to what it has always been.
    """
    from backtest.output import build_kpis
    from backtest.replay import EngineStack, build_strategy, frame_minutes, iter_bars

    _refuse_unreplayable(combo.config, fast_df, strategy_cls)
    strategy = build_strategy(
        strategy_cls,
        combo.config,
        initial_capital=capital,
        cost_profile=cost_profile,
        timeframe_minutes=frame_minutes(df),
    )
    # TWO-STREAM COMBO. When the config wants the re-entry layer and the caller supplied the
    # second frame, the strategy's OWN dual driver runs the combo — the merge rule lives in
    # `dual_clock.DualClock` and a second copy of *which bar steps when* is the exact shape that
    # has already produced two silent disagreements in this repo.
    # ⚠ It sets `bar_ms` and calls `finalize` itself, so this path must NOT do either again —
    # which is why it returns here rather than falling through to the single-stream loop below.
    # ⚠ `warmup=0`, matching the single-stream path, which steps the whole frame. A sweep grades
    # combos against each other and every one of them is graded on the same bars.
    if getattr(combo.config, "exec_secondary", False) and fast_df is not None:
        strategy.run_dual(df, fast_df, warmup=0)
        trades = strategy.execution.trades
        row = {"params": dict(combo.params), "kpis": build_kpis(trades, initial_capital=capital)}
        if extract is not None:
            row["extra"] = extract(strategy)
        return row

    if len(df.index) > 1:
        strategy.execution.bar_ms = int(df.index.to_series().diff().min().total_seconds() * 1000)

    stack = EngineStack(strategy.engine_config())
    for bar in iter_bars(df):
        strategy.step(stack.step(bar))

    # This drives the bar loop itself rather than calling `run()`, so it does NOT inherit run()'s
    # end-of-book passes. Without this a sweep over a finished-book feature (sos_fade's
    # `exec_recovery` today) would grade every combo on a book missing those trades and rank them
    # confidently — the combos would differ in a field nothing consumed. Guarded because this
    # optimizer is strategy-agnostic and only some strategies have the hook; idempotent, so a
    # strategy whose run() already finalized is unaffected.
    if hasattr(strategy, "finalize"):
        strategy.finalize(df)

    trades = strategy.execution.trades
    row = {"params": dict(combo.params), "kpis": build_kpis(trades, initial_capital=capital)}
    # The key is ABSENT when nobody asked, never None: a row carrying `extra: None` cannot be told
    # apart from one whose extractor genuinely found nothing, which is the "no" vs "cannot ask"
    # distinction root rule 1 is about.
    if extract is not None:
        row["extra"] = extract(strategy)
    return row


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
    cost_profile=None,
    extract: Optional[Callable[[Any], Any]] = None,
    fast_df=None,
) -> List[dict]:
    """Replay `df` once per combo and return [{params, kpis}] — one row per combo, in combo order.

    `module_path` is the strategy package (e.g. "strategies.python.sos_fade"); workers read its
    `LAB_STRATEGY` for the strategy class. `progress(done, total)` is called from the collecting
    thread only. `should_cancel()` is polled between completions — a cancelled sweep returns the
    rows finished so far rather than raising, because a partial grid is still a real answer.

    `cost_profile` is an optional `backtest.fills.AccountProfile` charged into every combo's P&L.
    It must be threaded here rather than left to the caller: a sweep that silently ignored the
    run's stated costs would rank combos on a frictionless book and then hand the winner to a
    validation run that is not — which is the same defect this parameter exists to close on the
    single-run path. It is a frozen dataclass, so it pickles to the worker processes unchanged.

    `fast_df` is the SECOND bar frame, for a strategy whose config asks for a faster stream
    (sos_fade's `exec_secondary`). Supplied, each such combo runs through the strategy's own
    `run_dual` and books the same re-entries a single run does; omitted, a config that wants one
    is REFUSED rather than replayed single-stream — see `_refuse_unreplayable`. It must cover the
    same window as `df`, and it pickles to the workers exactly as `df` does.

    `extract` is an optional callable handed each combo's FINISHED strategy; its return value
    arrives on that row as `extra`. It must be a module-level function — it is pickled to the
    workers — and it should return small, plain data, since whatever it builds is shipped back
    from another process. Omit it and every row is exactly what it has always been.
    """
    combos = list(combos)
    if not combos:
        return []
    # Fail before a pool is spawned. `_replay_one` refuses too (it is the seam every combo goes
    # through, serial or pooled), but there it raises inside a WORKER — the message survives, and
    # a grid that dies one combo in after starting N processes reads like a crash rather than a
    # refusal. Checking combo 0 is enough: a sweep varies params, never the strategy.
    # Checking combo 0 is enough: a sweep varies params, never the strategy. `strategy_cls` is
    # deliberately NOT available here — this function is handed a module path, not a class, and
    # importing the strategy in the parent just to type-check it would undo the one-import-per-
    # worker property. The run_dual check therefore happens in the worker, at `_replay_one`.
    _refuse_unreplayable(combos[0].config, fast_df)

    total = len(combos)
    workers = max_workers if max_workers is not None else default_workers(total)
    root = monorepo_root or str(_monorepo_root())

    if workers <= 1:
        return _sweep_serial(
            module_path,
            root,
            df,
            combos,
            initial_capital,
            progress,
            should_cancel,
            cost_profile,
            extract,
            fast_df,
        )

    results: List[Optional[dict]] = [None] * total
    done = 0
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_worker,
        initargs=(root, module_path, df, initial_capital, cost_profile, extract, fast_df),
    ) as pool:
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


def _sweep_serial(
    module_path,
    root,
    df,
    combos,
    capital,
    progress,
    should_cancel,
    cost_profile=None,
    extract=None,
    fast_df=None,
) -> List[dict]:
    """The single-worker path — also what the tests drive, since it needs no pickling or spawn."""
    import importlib

    if root and root not in sys.path:
        sys.path.insert(0, root)
    entry = importlib.import_module(module_path).LAB_STRATEGY
    strategy_cls = entry["strategy"]

    out: List[dict] = []
    for i, combo in enumerate(combos, 1):
        if should_cancel is not None and should_cancel():
            break
        out.append(_replay_one(strategy_cls, df, capital, combo, cost_profile, extract, fast_df))
        if progress is not None:
            progress(i, len(combos))
    return out


def _monorepo_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
