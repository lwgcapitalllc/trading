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

_MONOREPO = Path(cfg.MONOREPO_ROOT)
if str(_MONOREPO) not in sys.path:
    sys.path.insert(0, str(_MONOREPO))

# job_id -> job dict. Guarded by _LOCK: the worker thread writes while a request thread polls.
_JOBS: Dict[str, dict] = {}
_LOCK = threading.Lock()

_TF_MINUTES = {"D1": 1440, "H4": 240, "H1": 60, "M30": 30, "M15": 15, "M5": 5, "M1": 1}


def _timeframe_minutes(spec: dict) -> int:
    """The NT8 job_spec's bar_type/bar_value in minutes — the same mapping `_nt8_to_mt5_spec` uses."""
    bar_type = spec.get("bar_type", "Minute")
    bar_value = int(spec.get("bar_value") or 15)
    if bar_type == "Day":
        return 1440
    if bar_type != "Minute":
        return 60
    return max(1, bar_value)


def _set(job_id: str, **fields) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields, updated_at=time.time())


def start_backtest(job_spec: dict) -> dict:
    """Submit a Python backtest. Returns {job_id, status} immediately; the work runs on a thread."""
    job_id = job_spec.get("job_id") or f"py_{int(time.time() * 1000)}"
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "pct": 1,
            "message": "starting…", "created_at": time.time(), "updated_at": time.time(),
            "results": None, "error": None, "cancelled": False, "log": [],
        }
    t = threading.Thread(target=_run, args=(job_id, job_spec), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "running"}


def _run(job_id: str, spec: dict) -> None:
    try:
        _execute(job_id, spec)
    except Exception as exc:                       # noqa: BLE001 — a worker thread must never die silently
        _set(job_id, status="failed_error", pct=100, message=str(exc),
             error=f"{exc}\n{traceback.format_exc()}")


def _cancelled(job_id: str) -> bool:
    with _LOCK:
        job = _JOBS.get(job_id)
        return bool(job and job["cancelled"])


def _execute(job_id: str, spec: dict) -> None:
    from backtest.data.source import BarSource
    from backtest.output import build_results

    class_name = spec.get("strategy_class")
    found = _resolve(class_name)
    if found is None:
        raise ValueError(f"no Python strategy class named {class_name!r}")
    _, entry = found

    symbol = spec.get("instrument")
    if not symbol:
        raise ValueError("job_spec.instrument is required")
    tf = _timeframe_minutes(spec)

    _set(job_id, pct=5, message=f"loading {symbol} {tf}m bars…")
    df = BarSource().load(symbol, tf, spec["start_date"], spec["end_date"])
    if df.empty:
        raise ValueError(f"no bars for {symbol} {tf}m over "
                         f"[{spec['start_date']}, {spec['end_date']}]")

    config = _build_config(entry["config"], spec.get("params") or {}, symbol)
    capital = float(spec.get("deposit") or 10_000)
    strategy = entry["strategy"](config, initial_capital=capital)

    if getattr(config, "exec_secondary", False):
        # Secondary (1m sniper) re-entry is on → replay 15m PRIMARY + 1m SECONDARY on one clock
        # (strategy.run_dual). Needs a 1m feed alongside the base frame; the broker serves ~35 days
        # of M1, so a secondary run must be a recent window (an old one loads no 1m → clear error).
        _set(job_id, pct=8, message=f"loading {symbol} 1m bars for the secondary…")
        df1m = BarSource().load(symbol, 1, spec["start_date"], spec["end_date"])
        if df1m.empty:
            raise ValueError(
                f"exec_secondary is on but no 1m bars loaded for {symbol} over "
                f"[{spec['start_date']}, {spec['end_date']}] — the broker serves ~35 days of M1, "
                f"so choose a more recent window (or turn the secondary off).")
        _set(job_id, pct=15, message=f"replaying {len(df):,} × 15m + {len(df1m):,} × 1m…")

        def _prog(i: int, n: int) -> None:
            _set(job_id, pct=min(94, 15 + int(i / n * 79)), message=f"1m bar {i:,} / {n:,}")

        strategy.run_dual(df, df1m, progress=_prog, should_cancel=lambda: _cancelled(job_id))
    else:
        _set(job_id, pct=15, message=f"replaying {len(df):,} bars…")
        _replay(job_id, strategy, df, len(df))

    if _cancelled(job_id):
        _set(job_id, status="failed_cancelled", pct=100, message="cancelled")
        return

    _set(job_id, pct=95, message="building results…")
    results = build_results(strategy.execution.trades, point_value=config.point_value,
                            initial_capital=capital)
    _set(job_id, status="complete", pct=100, results=results,
         message=f"{len(strategy.execution.trades)} trades")


def _replay(job_id: str, strategy, df, total: int) -> None:
    """Drive the strategy bar-by-bar, reporting progress and honouring cancellation.

    `MpcSosFadeStrategy.run()` is the normal entry point, but it is a closed loop with no seam for
    either — so the loop is reproduced here over the same public API it uses. A long tick-mode run
    is minutes of work; a progress bar frozen at 15% and a Stop button that does nothing are not
    acceptable for that.
    """
    from backtest.replay import EngineStack, iter_bars

    if len(df.index) > 1:
        strategy.execution.bar_ms = int(
            df.index.to_series().diff().min().total_seconds() * 1000)

    stack = EngineStack(strategy.engine_config())
    step = max(1, total // 100)
    for bar in iter_bars(df):
        if bar.index % step == 0:
            if _cancelled(job_id):
                return
            _set(job_id, pct=min(94, 15 + int(bar.index / total * 79)),
                 message=f"bar {bar.index:,} / {total:,}")
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
    """
    import importlib

    if not class_name:
        return None
    pkg_root = _MONOREPO / "strategies" / "python"
    if not pkg_root.is_dir():
        return None
    for pkg_dir in sorted(pkg_root.iterdir()):
        if not (pkg_dir / "__init__.py").is_file():
            continue
        try:
            mod = importlib.import_module(f"strategies.python.{pkg_dir.name}")
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
            return {"status": "failed_error", "pct": 100,
                    "message": f"unknown python job {job_id}", "updated_at": time.time()}
        out = {"status": job["status"], "pct": job["pct"], "message": job["message"],
               "updated_at": job["updated_at"], "error": job["error"]}
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
            "job_id": job_id, "status": "running", "pct": 1,
            "message": "expanding grid…", "created_at": time.time(), "updated_at": time.time(),
            "results": None, "error": None, "cancelled": False, "log": [],
            "combos": None, "completed_count": 0, "total_count": 0,
        }
    threading.Thread(target=_run_opt, args=(job_id, opt_spec), daemon=True).start()
    return {"job_id": job_id, "status": "running"}


def _run_opt(job_id: str, spec: dict) -> None:
    try:
        _execute_opt(job_id, spec)
    except Exception as exc:                       # noqa: BLE001 — a worker thread must never die silently
        _set(job_id, status="failed_error", pct=100, message=str(exc),
             error=f"{exc}\n{traceback.format_exc()}")


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

    param_sets = expand_grid(spec.get("param_ranges") or {})
    if not param_sets:
        raise ValueError("param_ranges expanded to no combinations")

    _set(job_id, total_count=len(param_sets),
         message=f"loading {symbol} {tf}m bars for {len(param_sets)} combos…", pct=5)
    df = BarSource().load(symbol, tf, spec["start_date"], spec["end_date"])
    if df.empty:
        raise ValueError(f"no bars for {symbol} {tf}m over "
                         f"[{spec['start_date']}, {spec['end_date']}]")

    fixed = spec.get("fixed_params") or {}
    capital = float(spec.get("deposit") or 10_000)
    combos = [Combo(params=ps, config=_build_config(entry["config"], {**fixed, **ps}, symbol))
              for ps in param_sets]

    def _progress(done: int, total: int) -> None:
        _set(job_id, completed_count=done, total_count=total,
             pct=min(95, 5 + int(done / total * 90)), message=f"combo {done} / {total}")

    _set(job_id, pct=8, message=f"sweeping {len(combos)} combos…")
    rows = run_sweep(module_path=f"strategies.python.{pkg_name}", df=df, combos=combos,
                     initial_capital=capital, monorepo_root=str(_MONOREPO),
                     progress=_progress, should_cancel=lambda: _cancelled(job_id))

    if _cancelled(job_id):
        _set(job_id, status="failed_cancelled", pct=100, message="cancelled")
        return
    _set(job_id, status="complete", pct=100, combos=rows,
         message=f"{len(rows)} combos complete")


def native_opt_results(job_id: str) -> dict:
    """The finished combo grid — {combos: [{params, kpis}]}, the agents' shape."""
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise RuntimeError(f"unknown python job {job_id}")
    if job["status"] != "complete" or job["combos"] is None:
        raise RuntimeError(f"python opt {job_id} has no combos (status={job['status']})")
    return {"combos": job["combos"]}
