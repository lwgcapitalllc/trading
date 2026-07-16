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

    strategy_id = spec.get("strategy")
    entry = _lab_strategy(strategy_id)
    if entry is None:
        raise ValueError(f"no Python strategy registered as {strategy_id!r}")

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

    _set(job_id, pct=15, message=f"replaying {len(df):,} bars…")
    strategy = entry["strategy"](config, initial_capital=capital)
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

    `MpcAplusStrategy.run()` is the normal entry point, but it is a closed loop with no seam for
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


def _lab_strategy(strategy_id: str) -> Optional[dict]:
    """Look up a registered Python strategy's LAB_STRATEGY dict by its lab id."""
    import importlib

    if not strategy_id:
        return None
    try:
        mod = importlib.import_module(f"strategies.python.{strategy_id}")
    except Exception:
        return None
    spec = getattr(mod, "LAB_STRATEGY", None)
    return spec if isinstance(spec, dict) and "config" in spec else None


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
        return {"status": job["status"], "pct": job["pct"], "message": job["message"],
                "updated_at": job["updated_at"], "error": job["error"]}


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
