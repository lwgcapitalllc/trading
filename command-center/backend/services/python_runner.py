"""In-process runner for `runner="python"` strategies — the local counterpart to the NT8/MT5 agents.

**Why there is no agent.** NT8 and MT5 exist only on the VPS, so those runners are HTTP clients over
a remote terminal. A Python strategy has no terminal: it is `backtest/` + `engines/` + a strategy
package, all importable right here, running against the same cached broker bars the data layer
already pulls. Shipping it to the VPS to run would add a network hop, a deploy step, and a compile
step to a thing that needs none of them.

**What it must still do.** Every caller (`backtest_runner`'s polling loop, the retry paths, the
sweep and optimizer runners) talks to runners through `runner_dispatch` and expects the agent job
contract: submit returns a job id, status is polled until "complete", then results are fetched. So
this module reproduces that contract exactly — `start_backtest` / `job_status` / `job_results` /
`cancel_job` — with a thread instead of a VPS. Callers stay runner-agnostic; nothing above this
line learns that Python runs locally.

Jobs live in memory: a lab restart loses in-flight Python jobs, which is the same outcome the VPS
runners already have (`reset_stale_runs()` marks the orphaned rows failed on boot). Persisting them
would be inventing a durability guarantee the rest of the lab doesn't make.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

import config as cfg

# Stdlib-only, imports nothing from services — safe at module scope despite this module sitting
# inside the runner_dispatch import cycle.
from services import run_feeds, strategy_import

_MONOREPO = Path(cfg.MONOREPO_ROOT)
if str(_MONOREPO) not in sys.path:
    sys.path.insert(0, str(_MONOREPO))

# job_id -> job dict. Guarded by _LOCK: the worker thread writes while a request thread polls.
_JOBS: Dict[str, dict] = {}
_LOCK = threading.Lock()

# How many FINISHED jobs keep their full payload. Nothing ever removed an entry here, so every
# python backtest and every optimizer grid held its whole `results` / `combos` structure in the
# backend process until somebody restarted it — a day of tuning is hundreds of megabytes retained
# for data no caller can still ask for (`_handle_complete` fetches results exactly once).
#
# ⚠ The eviction drops the heavy payloads and KEEPS the status metadata, rather than deleting the
# entry. `job_status` answers "unknown python job" with `failed_error` for a missing id, so a
# straight delete would turn "this finished an hour ago" into "this failed" for any late poller.
# A shed job's `job_results` still raises, which is correct: the data is genuinely gone.
_MAX_FINISHED_PAYLOADS = 12

_TF_MINUTES = {"D1": 1440, "H4": 240, "H1": 60, "M30": 30, "M15": 15, "M5": 5, "M1": 1}

# The balance every python backtest starts from. It is a CONSTANT, and it was a bare `10_000`
# behind a `spec.get("deposit")` that nothing in this app has ever set — so the number read as
# configurable while being fixed. It is named here because the run page needs to agree with it:
# a self-sizing strategy compounds off this balance, so it is the only honest denominator for a
# percentage drawdown, and the page must read it back off the run's own equity curve rather than
# off the evaluated ruleset's `account_size` (which is a different account entirely).
# ⚠ Changing it re-scales the dollars of every future run. R is unaffected.
_DEFAULT_CAPITAL = 10_000.0


# The cost layers a run may switch on, in the order the UI shows them. Every one is OFF by
# default — Aaron's call (2026-08-02): the baseline run stays frictionless so it stays directly
# comparable to the TradingView Strategy Tester, and each cost is something you deliberately
# turned on rather than something the lab decided for you.
COST_LAYERS = ("spread", "swap", "commission", "slippage", "bid_ask_fills")


def _cost_profile(spec: dict):
    """The run's `AccountProfile`, or None when the run charges nothing.

    **This is the seam that was missing until 2026-08-01.** The lab collected
    `commission_per_side` and `slippage_ticks` at run creation, stored them on the row, showed
    them on the page — and nothing ever read them, so every Python run was frictionless while
    reporting a cost profile it had not applied. The tell in the data was 52 losing trades each
    losing EXACTLY 10.00% of prior equity, which no cost model can produce.

    **Layered since 2026-08-02.** `cost_layers` names which costs to charge and `broker_profile`
    says whose measured facts to charge them from — so the two costs we genuinely KNOW, the spread
    and the overnight swap, stop being unpriced without anyone having to type a number. The one
    unknowable cost keeps its own switch and its own typed figure on purpose: slippage is a
    property of a live account that no amount of history can measure, so it must never ride along
    with the measured ones.

    Four facts the numbers are interpreted against, all stated rather than assumed:

    * **`commission_per_side` is dollars per LOT per side**, a lot being `contract_size` units
      (100 oz for gold — `AccountProfile`'s default, and the unit every broker quotes gold
      commission in). It is NOT per unit: reading $3.00 as per-ounce would charge 100x.
    * **`slippage_ticks` is charged on MARKET exits only** and only in bar mode. A resting limit
      does not slip, and tick mode measures the real thing off the tape — see
      `Execution._charge_slippage`.
    * **`spread` and `swap` come from the BROKER PROFILE, never from the request.** Both are
      measurements (`backtest/fills.py` records the tick counts behind each spread and the
      Specification window behind each swap), and a number the operator can type is a number that
      can silently disagree with the broker. Picking `puprime_standard` instead of the default
      `vantage_demo` moves the spread 0.22 → 0.32, because those are two different measurements.
      (This line said 0.33 until 2026-08-14; `b03aacd` re-measured Standard to 0.32 on
      2026-08-10 and the prose was the stale half. The number lives in `backtest/fills.py`.)
    * **`bid_ask_fills` REPLACES the spread cost, it does not add to it** — see
      `Execution._charge_spread`. It is also the ONLY layer that can change which trades exist,
      which is why it is its own switch, and it implies `spread`: modelling the ask with no
      spread is a no-op wearing a label.

    ⚠ **`cost_layers` absent (None) means a PRE-LAYER run and keeps the old behaviour** — charge
    whatever commission and slippage that row stated. An explicit `[]` means charge nothing.
    Collapsing the two would silently re-price every stored run the moment it was retried.
    """
    from backtest.fills import PROFILES, AccountProfile

    commission = float(spec.get("commission_per_side") or 0.0)
    slippage = int(spec.get("slippage_ticks") or 0)
    layers = spec.get("cost_layers")

    if layers is None:  # pre-2026-08-02 row — the old contract, untouched
        if commission <= 0 and slippage <= 0:
            return None
        return AccountProfile(
            name="lab", commission_per_side_per_lot=commission, slippage_ticks=slippage, swap=None
        )

    on = {str(x) for x in layers}
    unknown = on - set(COST_LAYERS)
    if unknown:
        raise ValueError(
            f"unknown cost layer(s) {sorted(unknown)} — known layers are {list(COST_LAYERS)}. "
            f"A layer nobody reads would be charged as nothing while the page said otherwise."
        )
    if not on:
        return None  # explicit "charge nothing": no charge path entered

    broker = spec.get("broker_profile") or "vantage_demo"
    if broker not in PROFILES:
        raise ValueError(
            f"broker_profile {broker!r} unknown — the spread and swap are read off a real "
            f"account, so it must be one of: {sorted(PROFILES)}"
        )
    base = PROFILES[broker]

    bid_ask = "bid_ask_fills" in on
    return AccountProfile(
        name=f"lab:{broker}",
        commission_per_side_per_lot=commission if "commission" in on else 0.0,
        contract_size=base.contract_size,
        mintick=base.mintick,
        latency_ms=base.latency_ms,
        swap=base.swap if "swap" in on else None,
        slippage_ticks=slippage if "slippage" in on else 0,
        spread=base.spread if ("spread" in on or bid_ask) else 0.0,
        bid_ask_fills=bid_ask,
    )


def _timeframe_minutes(spec: dict) -> int:
    """The NT8 job_spec's bar_type/bar_value in minutes — the same mapping `_nt8_to_mt5_spec` uses.

    Delegates to `run_feeds` rather than repeating the mapping. It was a hand-copy shared
    with `history_limits`, and while those two never disagreed, the FEED LIST beside it did
    — which is the whole reason `run_feeds` exists.
    """
    return run_feeds.timeframe_minutes(spec.get("bar_type", "Minute"), spec.get("bar_value"))


def _set(job_id: str, **fields) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields, updated_at=time.time())


def _shed_old_payloads_locked() -> None:
    """Drop `results`/`combos` from all but the newest `_MAX_FINISHED_PAYLOADS` finished jobs.

    Caller must hold `_LOCK`. Running jobs are never touched — a job still working needs its
    accumulators, and its payload is the one thing that cannot be recomputed.
    """
    finished = [
        j
        for j in _JOBS.values()
        if j["status"] != "running" and (j.get("results") or j.get("combos"))
    ]
    if len(finished) <= _MAX_FINISHED_PAYLOADS:
        return
    finished.sort(key=lambda j: j["updated_at"], reverse=True)
    for job in finished[_MAX_FINISHED_PAYLOADS:]:
        job["results"] = None
        job["combos"] = None
        job["payload_shed"] = True


def start_backtest(job_spec: dict) -> dict:
    """Submit a Python backtest. Returns {job_id, status} immediately; the work runs on a thread."""
    job_id = job_spec.get("job_id") or f"py_{int(time.time() * 1000)}"
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "pct": 1,
            "message": "starting…",
            "created_at": time.time(),
            "updated_at": time.time(),
            "results": None,
            "error": None,
            "cancelled": False,
            "log": [],
        }
        _shed_old_payloads_locked()
    t = threading.Thread(target=_run, args=(job_id, job_spec), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "running"}


def _run(job_id: str, spec: dict) -> None:
    try:
        _execute(job_id, spec)
    except Exception as exc:  # noqa: BLE001 — a worker thread must never die silently
        _set(
            job_id,
            status="failed_error",
            pct=100,
            message=str(exc),
            error=f"{exc}\n{traceback.format_exc()}",
        )


def _cancelled(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        return bool(job and job["cancelled"])


def _execute(job_id: str, spec: dict) -> None:
    from backtest.data.source import BarSource
    from backtest.output import build_results
    from backtest.replay import build_strategy

    class_name = spec.get("strategy_class")
    found = _resolve(class_name)
    if found is None:
        raise ValueError(f"no Python strategy class named {class_name!r}")
    _, entry = found

    symbol = spec.get("instrument")
    if not symbol:
        raise ValueError("job_spec.instrument is required")
    tf = _timeframe_minutes(spec)

    # 🔴 THE PERCENTAGE IS THE FRACTION OF THE BARS DONE, near enough to say so out loud.
    # Loading owns 0–2, the bar loop owns 2–98, writing results owns the rest. It used to be
    # 5 / 15 / 15–94 / 95, and the UI drew three evenly-spaced stages over it — so the first
    # fifteen points (a few seconds of loading) took half the bar's width and the 156,721-bar
    # loop crawled through the other half. Any split here is a claim about how long each part
    # takes; keeping loading down to two points means the claim is roughly true and the bar
    # moves at one speed from end to end.
    _set(job_id, pct=1, message=f"Loading {symbol} {tf}m bars…")
    df = BarSource().load(symbol, tf, spec["start_date"], spec["end_date"])
    if df.empty:
        raise ValueError(
            f"no bars for {symbol} {tf}m over [{spec['start_date']}, {spec['end_date']}]"
        )

    config = _build_config(entry["config"], spec.get("params") or {}, symbol)
    capital = float(spec.get("deposit") or _DEFAULT_CAPITAL)
    strategy = build_strategy(
        entry["strategy"], config, initial_capital=capital, cost_profile=_cost_profile(spec)
    )

    # ONE question, asked of `run_feeds` by both this runner and the pre-flight floor check.
    # It used to be `getattr(config, "exec_secondary", False)` right here and nowhere else,
    # so `history_limits` bounded the chart timeframe alone and a run whose 1m feed could not
    # reach the requested start date passed validation and died at 8%. Asked of the CONFIG,
    # not the raw spec: a strategy default the spec never overrode is only visible post-merge.
    # ⚠ The FLAG, not `1 in required_timeframes(...)` — a 1m-chart run puts 1 in the feed
    # set by itself and would take this branch with the secondary off.
    if run_feeds.uses_secondary(config):
        # Secondary (1m sniper) re-entry is on → replay 15m PRIMARY + 1m SECONDARY on one clock
        # (strategy.run_dual). Needs a 1m feed alongside the base frame.
        # ⚠ This used to say the broker serves ~35 days of M1 and to pick a recent window. That
        # was a GUESS nobody had checked and it is FALSE — measured against the live terminal on
        # 2026-08-06, Vantage XAUUSD M1 runs back to 2018-09-14, the same depth as the M15. The
        # cost of the wrong figure was not a bad run, it was that this feature went unmeasured
        # for three weeks because the only windows anyone believed reachable were too short for a
        # setup this rare to fire in. A 1m window is SLOW to load and replay, not unavailable.
        _set(job_id, pct=2, message=f"Loading {symbol} 1m bars for the re-entry…")
        df1m = BarSource().load(symbol, 1, spec["start_date"], spec["end_date"])
        if df1m.empty:
            raise ValueError(
                f"exec_secondary is on but no 1m bars loaded for {symbol} over "
                f"[{spec['start_date']}, {spec['end_date']}] — check the broker serves 1m history "
                f"for this window (or turn the secondary off)."
            )
        _set(job_id, pct=2, message=f"Testing {len(df):,} × 15m + {len(df1m):,} × 1m bars…")

        def _prog(i: int, n: int) -> None:
            _set(
                job_id,
                pct=min(98, 2 + int(i / n * 96)),
                message=f"Testing 1m bar {i:,} of {n:,}",
            )

        strategy.run_dual(df, df1m, progress=_prog, should_cancel=lambda: _cancelled(job_id))
    else:
        _set(job_id, pct=2, message=f"Testing {len(df):,} bars…")
        _replay(job_id, strategy, df, len(df))

    if _cancelled(job_id):
        _set(job_id, status="failed_cancelled", pct=100, message="cancelled")
        return

    # Passes that need the FINISHED book, not one bar — today the loss recovery. `_replay` below
    # reproduces the strategy's own bar loop rather than calling `run()`, so it does NOT get
    # `run()`'s finalize for free: without this line `exec_recovery` would be a toggle the form
    # renders, the config carries, and nothing consumes. `run_dual` finalizes itself, and the
    # pass is idempotent, so calling it here is safe on both paths. Guarded because the runner
    # serves every python strategy and only this one has the hook.
    if hasattr(strategy, "finalize"):
        strategy.finalize(df)

    _set(job_id, pct=99, message="Building results…")
    # `blocks` / `misses` are optional on the execution layer — a strategy that records no
    # refusals or near-misses (or an older one) yields an empty list, never a missing key.
    results = build_results(
        strategy.execution.trades,
        point_value=config.point_value,
        initial_capital=capital,
        blocked=getattr(strategy.execution, "blocks", None),
        missed=getattr(strategy.execution, "misses", None),
    )
    _set(
        job_id,
        status="complete",
        pct=100,
        results=results,
        message=f"{len(strategy.execution.trades)} trades",
    )


def _replay(job_id: str, strategy, df, total: int) -> None:
    """Drive the strategy bar-by-bar, reporting progress and honouring cancellation.

    `MpcSosFadeStrategy.run()` is the normal entry point, but it is a closed loop with no seam for
    either — so the loop is reproduced here over the same public API it uses. A long tick-mode run
    is minutes of work; a progress bar frozen at 15% and a Stop button that does nothing are not
    acceptable for that.
    """
    from backtest.replay import EngineStack, iter_bars

    if len(df.index) > 1:
        strategy.execution.bar_ms = int(df.index.to_series().diff().min().total_seconds() * 1000)

    stack = EngineStack(strategy.engine_config())
    # ⚠ 1/500th of the run, not 1/100th. `_set` is a dict update under a lock, so the cost is
    # nothing; the granularity is what the person watching sees. At 1% steps a 156,721-bar run
    # moved the bar 100 times over several minutes and looked frozen between jumps.
    step = max(1, total // 500)
    for bar in iter_bars(df):
        if bar.index % step == 0:
            if _cancelled(job_id):
                return
            _set(
                job_id,
                pct=min(98, 2 + int(bar.index / total * 96)),
                message=f"Testing bar {bar.index:,} of {total:,}",
            )
        strategy.step(stack.step(bar))


def _resolve(class_name: str) -> Optional[tuple]:
    """Find the Python strategy package declaring `class_name` → (package_name, LAB_STRATEGY).

    The job contract every runner is handed identifies a strategy by `strategy_class` — the NT8
    class, the MQL5 class, and here the strategy class's `__name__`, which is exactly what
    `strategy_scanner._parse_python_package` stored as `class_name`. So resolution is by class name,
    not by package id: the dispatcher must not need to know that Python strategies happen to also
    have a package.

    Import failures are skipped rather than raised — the same rule the scanner follows, so one
    half-finished package under strategies/python/ cannot break runs for every other strategy.

    ⚠ THE CACHED MODULES ARE DROPPED FIRST, once, before the loop. This backend is long-running, so
    `import_module` would otherwise pin whatever was on disk when it last booted — and a backtest
    replaying a strategy the repo no longer contains is a result that looks entirely normal and
    describes code nobody can read. Purging per package would be worse than not purging: mpc_bleg
    imports mpc_sos_fade and sorts before it. See `services/strategy_import.py`.
    """
    if not class_name:
        return None
    pkg_root = _MONOREPO / "strategies" / "python"
    if not pkg_root.is_dir():
        return None
    strategy_import.purge_strategy_modules()
    for pkg_dir in sorted(pkg_root.iterdir()):
        if not (pkg_dir / "__init__.py").is_file():
            continue
        try:
            mod = strategy_import.import_strategy_package(pkg_dir.name, _MONOREPO)
        except Exception:
            continue
        spec = getattr(mod, "LAB_STRATEGY", None)
        if not isinstance(spec, dict) or "config" not in spec or "strategy" not in spec:
            continue
        if spec["strategy"].__name__ == class_name:
            return pkg_dir.name, spec
    return None


def _build_config(config_cls, params: dict, symbol: str) -> Any:
    """Build the strategy's config dataclass from the lab's param dict.

    Unknown keys are DROPPED rather than passed through: the lab's params can carry leftovers from
    a previous schema or another runner, and a dataclass raises TypeError on an unexpected keyword —
    which would fail the run for a param the strategy doesn't even read. Values are coerced to each
    field's declared type because the lab stores params as JSON, where every number is a float and
    a bool may arrive as 0/1.
    """
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(config_cls)}
    kwargs = {}
    for name, value in params.items():
        f = fields.get(name)
        if f is None or value is None:
            continue
        kwargs[name] = _coerce(value, f.type)
    # The symbol is a run fact, not a tunable — the lab already knows it, so tick mode should
    # never need it typed into the param form as well.
    if "symbol" in fields and not kwargs.get("symbol"):
        kwargs["symbol"] = symbol
    return config_cls(**kwargs)


def _coerce(value, hint):
    hint = hint.strip() if isinstance(hint, str) else getattr(hint, "__name__", "")
    try:
        if hint == "bool":
            return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")
        if hint == "int":
            return int(float(value))
        if hint == "float":
            return float(value)
        if hint == "str":
            return str(value)
    except (TypeError, ValueError):
        return value
    return value


def job_status(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return {
                "status": "failed_error",
                "pct": 100,
                "message": f"unknown python job {job_id}",
                "updated_at": time.time(),
            }
        out = {
            "status": job["status"],
            "pct": job["pct"],
            "message": job["message"],
            "updated_at": job["updated_at"],
            "error": job["error"],
        }
        # Sweep jobs only: drives the optimizer's live completed_runs. Absent on single
        # backtests, which have no combo count — the poller skips a missing key.
        if job.get("total_count"):
            out["completed_count"] = job["completed_count"]
            out["total_count"] = job["total_count"]
        return out


def job_results(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise RuntimeError(f"unknown python job {job_id}")
    if job.get("payload_shed"):
        raise RuntimeError(
            f"python job {job_id} finished but its results have been shed to free memory "
            f"({_MAX_FINISHED_PAYLOADS} newer jobs have run since). Re-run it."
        )
    if job["status"] != "complete" or job["results"] is None:
        raise RuntimeError(f"python job {job_id} has no results (status={job['status']})")
    return job["results"]


def cancel_job(job_id: str) -> dict:
    """Ask a running job to stop. Cooperative: the replay loop checks the flag on its next tick,
    which is why there is no thread-kill here — a half-killed replay would leave engine state that
    looks valid but isn't."""
    _set(job_id, cancelled=True, message="cancelling…")
    return {"job_id": job_id, "status": "cancelling"}


def job_log(job_id: str, lines: int = 200) -> str:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return f"unknown python job {job_id}"
    out = [f"[{job['status']}] {job['message']}"]
    if job["error"]:
        out.append(job["error"])
    return "\n".join(out[-lines:])


def health() -> dict:
    """Always up — it is this process. Included so the dispatcher can treat it like the agents."""
    with _LOCK:
        running = sum(1 for j in _JOBS.values() if j["status"] == "running")
    return {"status": "ok", "running_jobs": running}


# ── native optimization (A4) ──────────────────────────────────────────────────
#
# The NT8/MT5 optimizers are remote jobs: submit a spec, poll, then harvest a combo grid. There is
# no terminal here, so "native" means `backtest.optimizer.run_sweep` on this box's cores. The job
# contract is identical either way, so `optimization_runner` needs no Python-specific branch.


def start_native_optimization(opt_spec: dict) -> dict:
    """Submit a Python grid sweep. Same contract as the agents' /native-optimize."""
    job_id = opt_spec.get("job_id") or f"pyopt_{int(time.time() * 1000)}"
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "pct": 1,
            "message": "expanding grid…",
            "created_at": time.time(),
            "updated_at": time.time(),
            "results": None,
            "error": None,
            "cancelled": False,
            "log": [],
            "combos": None,
            "completed_count": 0,
            "total_count": 0,
        }
        _shed_old_payloads_locked()
    threading.Thread(target=_run_opt, args=(job_id, opt_spec), daemon=True).start()
    return {"job_id": job_id, "status": "running"}


def _run_opt(job_id: str, spec: dict) -> None:
    try:
        _execute_opt(job_id, spec)
    except Exception as exc:  # noqa: BLE001 — a worker thread must never die silently
        _set(
            job_id,
            status="failed_error",
            pct=100,
            message=str(exc),
            error=f"{exc}\n{traceback.format_exc()}",
        )


def _execute_opt(job_id: str, spec: dict) -> None:
    from backtest.data.source import BarSource
    from backtest.optimizer import Combo, run_sweep

    # The lab owns what a grid IS (min/max/step), and expands it the same way for every runner.
    # Imported lazily: optimization_runner imports runner_dispatch, which imports this module.
    from services.optimization_runner import expand_grid

    class_name = spec.get("strategy_class")
    found = _resolve(class_name)
    if found is None:
        raise ValueError(f"no Python strategy class named {class_name!r}")
    pkg_name, entry = found

    symbol = spec.get("instrument")
    if not symbol:
        raise ValueError("opt_spec.instrument is required")
    tf = _timeframe_minutes(spec)

    # `param_sets` is an EXPLICIT list of configurations, used instead of expanding a grid. It
    # exists for stress-test sensitivity, which is one-param-at-a-time: it wants
    # [{A: a1}, {A: a2}, {B: b1}, {B: b2}], and `expand_grid` would return their CARTESIAN PRODUCT
    # — a different, much larger experiment answering a different question.
    #
    # ⚠ It shares this path deliberately rather than calling `run_sweep` from the caller. The cost
    # profile is built HERE, by `_cost_profile`, from the same spec fields a single run uses — and a
    # second call site building its own is exactly how the stress tester came to measure its
    # children on a free book while their parent was charged (2026-08-05). One reader, one place.
    explicit = spec.get("param_sets")
    if explicit:
        param_sets = [dict(ps) for ps in explicit]
    else:
        param_sets = expand_grid(spec.get("param_ranges") or {})
    if not param_sets:
        raise ValueError("param_sets was empty and param_ranges expanded to no combinations")

    _set(
        job_id,
        total_count=len(param_sets),
        message=f"loading {symbol} {tf}m bars for {len(param_sets)} combos…",
        pct=5,
    )
    df = BarSource().load(symbol, tf, spec["start_date"], spec["end_date"])
    if df.empty:
        raise ValueError(
            f"no bars for {symbol} {tf}m over [{spec['start_date']}, {spec['end_date']}]"
        )

    fixed = spec.get("fixed_params") or {}
    capital = float(spec.get("deposit") or _DEFAULT_CAPITAL)
    combos = [
        Combo(params=ps, config=_build_config(entry["config"], {**fixed, **ps}, symbol))
        for ps in param_sets
    ]

    def _progress(done: int, total: int) -> None:
        _set(
            job_id,
            completed_count=done,
            total_count=total,
            pct=min(95, 5 + int(done / total * 90)),
            message=f"combo {done} / {total}",
        )

    _set(job_id, pct=8, message=f"sweeping {len(combos)} combos…")
    rows = run_sweep(
        module_path=f"strategies.python.{pkg_name}",
        df=df,
        combos=combos,
        initial_capital=capital,
        monorepo_root=str(_MONOREPO),
        progress=_progress,
        should_cancel=lambda: _cancelled(job_id),
        cost_profile=_cost_profile(spec),
    )

    if _cancelled(job_id):
        _set(job_id, status="failed_cancelled", pct=100, message="cancelled")
        return
    _set(job_id, status="complete", pct=100, combos=rows, message=f"{len(rows)} combos complete")


def native_opt_results(job_id: str) -> dict:
    """The finished combo grid — {combos: [{params, kpis}]}, the agents' shape."""
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise RuntimeError(f"unknown python job {job_id}")
    if job.get("payload_shed"):
        raise RuntimeError(
            f"python opt {job_id} finished but its grid has been shed to free memory "
            f"({_MAX_FINISHED_PAYLOADS} newer jobs have run since). Re-run it."
        )
    if job["status"] != "complete" or job["combos"] is None:
        raise RuntimeError(f"python opt {job_id} has no combos (status={job['status']})")
    return {"combos": job["combos"]}
