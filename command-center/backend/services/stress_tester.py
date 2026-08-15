"""
Stress tester — Monte Carlo (Step 2), walk-forward, sensitivity (Step 3).
Pure Python + numpy for MC. Walk-forward/sensitivity trigger NT8 via VPS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from services import lab_db, notify
from services.alert_format import alert, joined
from services.metrics import (
    apply_canonical_sharpe,
    daily_sharpe,
    effective_dd_limit_pct,
    effective_dd_limit_usd,
)

log = logging.getLogger("stress_tester")

# Strong references to fire-and-forget background tasks. `asyncio.create_task` does NOT keep one:
# the loop holds a task only while one of its callbacks is scheduled, so a task sitting in a long
# `await` is collectable and can vanish mid-flight — leaving a row `running` for ever with nothing
# in the log. Documented CPython behaviour, not a theory.
_BACKGROUND_TASKS: set = set()

_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
_POLL_INTERVAL = 5
_STALL_KILL_SEC = 600

# Minimum trade count to run ANY stress test. A single flat floor: below this the whole test is
# blocked, not just walk-forward. Rationale — the page's output is the A-F grade, and the grade
# leans on Monte Carlo TAIL percentiles (A = worst-1% drawdown, B = worst-5%), which at small
# samples are decided by one or two unlucky trades. So a sub-100 grade is false confidence, the
# same disease as the 134,540% walk-forward number. Walk-forward (5 windows × 70/30 IS/OOS) is
# only a coin flip below ~100 trades too. 100 is the floor; ~150-200 is comfortable.
MIN_TRADES_FOR_STRESS = 100

# Walk-forward IS→OOS degradation guards. `1 - OOS/IS` is unstable when the in-sample Sharpe is
# near zero (a flat in-sample window blows the ratio up), so windows below the floor are excluded
# as not-assessable and each surviving window is clamped to a sane band before averaging.
_WF_IS_SHARPE_FLOOR = 0.1  # below this the in-sample window had no real edge to degrade from
_WF_DEG_CLAMP = (-1.0, 2.0)  # per-window degradation bounded to [-100%, +200%]
# Minimum closed trades on EACH side of a window for its Sharpe to mean anything. 20 is the point
# below which a single trade is worth more than 5% of the sample, so the ratio `1 - OOS/IS` reports
# one trade's luck as a robustness verdict. Deliberately a flat count, not a fraction of the run:
# the question is whether THIS window has enough evidence, which does not depend on how big the
# whole backtest was.
_WF_MIN_TRADES_PER_WINDOW = 20


def _clamp_wf_degradation(deg: float) -> float:
    lo, hi = _WF_DEG_CLAMP
    return max(lo, min(hi, deg))


# ── What a child run is MEASURED on ───────────────────────────────────────────


def _json_list(raw) -> Optional[list]:
    """A stored JSON list, or None when the column was never written.

    `lab_db.get_run` does not decode `cost_layers`, so it arrives as raw JSON TEXT. Reading it
    without this returns a STRING, and a string handed to the runner as `cost_layers` iterates
    its characters — every real layer name fails to match while 's', 'p', 'r'… all appear
    charged. Same trap `routers/backtests._json_list` exists for.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, list) else None


def child_measurement_fields(source_run: dict) -> dict:
    """Everything that decides what a run is MEASURED on, read off the baseline row.

    🔴 Walk-forward and sensitivity children carried only `commission_per_side` and
    `slippage_ticks` until 2026-08-05 — no `cost_layers`, no `broker_profile`, no `sizing_mode`.
    `python_runner._cost_profile` reads all three off the job spec, so stress-testing a run that
    charged spread and swap produced children measured on a FREE BOOK, and then:

      • sensitivity scored `|child_pf - baseline_pf| / baseline_pf` — a charged baseline against
        free children, so the cost gap was reported as the parameter's fragility;
      • walk-forward compared a charged whole-period Sharpe against free window Sharpes.

    This is the identical defect the tuning workbench carried until the day before, and the rule
    it left behind: a page (or a phase) whose whole job is COMPARING must carry forward everything
    that decides what a run is measured on, or the difference column becomes the thing that lies.

    ⚠ `cost_layers` NULL stays NULL. A child of a pre-layer run must retry on the pre-layer
    contract, exactly as `POST /runs/{id}/retry` does — `[]` would be a NEW claim ("charge
    nothing") about a row that never made one.
    """
    return {
        "cost_layers": _json_list(source_run.get("cost_layers")),
        "broker_profile": source_run.get("broker_profile"),
        "sizing_mode": source_run.get("sizing_mode") or "consistent",
        "manual_risk_pct": source_run.get("manual_risk_pct"),
    }


# ── Which series is safe to shuffle ────────────────────────────────────────────

# A dollar P&L series may be shuffled only if it is STATIONARY — i.e. a trade from late in the run
# could equally have happened early. That holds when position size is constant, and fails whenever
# size scales with the account: a strategy risking a % of equity, or any run the lab's own sizing
# engine sized in consistent/bullet/manual mode. Then a late trade's dollars encode an account
# balance that did not exist yet, and shuffling builds paths the account could never have taken.
#
# Measured on run 06f7eece0db1 (self-sizing, 10% risk, $10k → $382k): median |trade| ran $222 in the
# first third to $3,913 in the last, a 17.7x drift, and the shuffle reported a worst-1% drawdown of
# $41,970 — four times the account it started with. Shuffling that run's PERCENT returns instead
# (drift 1.4x) gives $359,886. The old number was not merely imprecise, it was UNREACHABLE, and it
# understated the real tail by ~8x.
#
# The choice is made from the DATA, never from a strategy flag or a config field, so it needs no
# knowledge of which strategy ran and cannot be tuned per strategy. A fixed-size run keeps the
# dollar model and its numbers do not move at all.
_DRIFT_MIN_TRADES = 30  # below this, thirds are too small to judge drift from
_DRIFT_TRIGGER = 2.0  # dollar trade size must at least double across the run to look non-stationary


def _median_abs(values: np.ndarray) -> float:
    return float(np.median(np.abs(values)))


def _drift(values: np.ndarray) -> float:
    """Median |value| of the last third over the first third. 1.0 = stationary."""
    n = len(values)
    first = _median_abs(values[: n // 3])
    last = _median_abs(values[2 * n // 3 :])
    if first <= 0 or last <= 0:
        return 1.0
    return last / first


def choose_shuffle_series(
    trade_pnls: list[float], balances: Optional[list[float]]
) -> tuple[np.ndarray, str, float]:
    """Pick the series whose distribution is stable across the run.

    Returns (values, model, start_balance) where model is "dollars" (values are P&L, compose by
    addition) or "returns" (values are per-trade fractional returns, compose by compounding).

    Defaults to "dollars" — today's behaviour — and only switches when the data says the dollar
    series drifted AND the account's own growth is what explains that drift. If trade size doubled
    while the balance stayed flat (a volatility regime, not compounding), both series drift by the
    same factor, neither is more stable, and the dollar model is kept.
    """
    pnls = np.asarray(trade_pnls, dtype=np.float64)
    if balances is None or len(balances) != len(pnls) or len(pnls) < _DRIFT_MIN_TRADES:
        return pnls, "dollars", 0.0

    bal = np.asarray(balances, dtype=np.float64)
    if not np.all(np.isfinite(bal)) or np.any(bal <= 0):
        return pnls, "dollars", 0.0

    returns = pnls / bal
    # A return of -100% or worse wipes the account out; compounding past it is meaningless.
    if np.any(1.0 + returns <= 0):
        return pnls, "dollars", 0.0

    dollar_drift = _drift(pnls)
    return_drift = _drift(returns)
    if dollar_drift < _DRIFT_TRIGGER:
        return pnls, "dollars", 0.0
    # Compare distance from 1.0 in LOG space so growth and shrinkage are weighed symmetrically —
    # a fixed-size strategy on a doubling account has flat dollars and halving returns, and must
    # keep the dollar model.
    if abs(np.log(return_drift)) >= abs(np.log(dollar_drift)):
        return pnls, "dollars", 0.0
    return returns, "returns", float(bal[0])


# ── Monte Carlo ────────────────────────────────────────────────────────────────


def run_monte_carlo(
    trade_pnls: list[float],
    ruleset: Optional[dict] = None,
    num_reshuffles: int = 10_000,
    num_bootstrap: int = 1_000,
    num_path_samples: int = 100,
    balances: Optional[list[float]] = None,
) -> dict:
    """Vectorised Monte Carlo on trade PnL list. Returns percentile stats + sampled paths.

    `balances` is the account balance BEFORE each trade, in the same order. When supplied it lets
    the simulation detect a compounding run and shuffle returns rather than dollars — see
    choose_shuffle_series. Omit it and the dollar model is used, exactly as before.
    """
    if not trade_pnls:
        raise ValueError("No trades to simulate")

    values, model, start_bal = choose_shuffle_series(trade_pnls, balances)
    n = len(values)
    rng = np.random.default_rng()

    def _paths(idx: np.ndarray) -> np.ndarray:
        """Cumulative P&L (not balance) per simulated path, so every downstream stat is unchanged.

        Dollars compose by addition; returns compose by compounding off the real starting balance
        and are then expressed back as cumulative P&L.
        """
        drawn = values[idx]
        if model == "returns":
            return start_bal * np.cumprod(1.0 + drawn, axis=1) - start_bal
        return np.cumsum(drawn, axis=1)

    # Vectorised reshuffles: argsort(random) produces a random permutation per row
    idx_rs = np.argsort(rng.random((num_reshuffles, n)), axis=1)
    equity_rs = _paths(idx_rs)
    peak_rs = np.maximum.accumulate(equity_rs, axis=1)
    final_pnl_rs = equity_rs[:, -1]
    max_dd_rs = np.max(peak_rs - equity_rs, axis=1)

    # Vectorised bootstrap (sample with replacement)
    idx_bs = rng.integers(0, n, size=(num_bootstrap, n))
    equity_bs = _paths(idx_bs)
    peak_bs = np.maximum.accumulate(equity_bs, axis=1)
    final_pnl_bs = equity_bs[:, -1]
    max_dd_bs = np.max(peak_bs - equity_bs, axis=1)

    all_dds = np.concatenate([max_dd_rs, max_dd_bs])

    # The SAME drawdowns expressed against the account, as a percent. A dollar drawdown is only
    # comparable to a fixed dollar limit while the account stays near the size that limit was
    # written for, and a compounding account does not: on run 06f7eece0db1 the dollar view reported
    # a 100% breach of TOTAL RUIN across simulations that were never once wiped out.
    #
    # Each point is measured against the peak the balance had reached BY THAT POINT — the standard
    # definition — not against the path's final peak, which would understate an early collapse.
    #
    # Only the compounding model has a balance series of its own (it is simulated off the real
    # starting balance). A fixed-size run's percent would need an account size the simulation is
    # not given, so it reports None and is graded in dollars, exactly as before. `dd_basis` names
    # which of the two the grade should read.
    dd_basis = "percent" if model == "returns" else "dollars"

    def _dd_pct(equity: np.ndarray) -> np.ndarray:
        balance = equity + start_bal
        peaks = np.maximum.accumulate(balance, axis=1)
        return np.max((peaks - balance) / peaks, axis=1) * 100.0

    all_dds_pct: Optional[np.ndarray] = None
    if model == "returns" and start_bal > 0:
        all_dds_pct = np.concatenate([_dd_pct(equity_rs), _dd_pct(equity_bs)])

    # Final-PnL percentiles come from the BOOTSTRAP pool only: it resamples WITH replacement, so it
    # answers "what if the trades themselves had come out differently", which is the question a
    # p5/p1 outcome is asking. Reshuffles answer a different one ("what if the same trades arrived
    # in another order") and are used for drawdown, which order genuinely changes.
    # (Under the dollar model reshuffles are also order-invariant in sum, so including them would
    # collapse these three percentiles onto the net total. That is no longer true under the returns
    # model — compounding is order-dependent — but the pool split is kept, because the reason above
    # is the durable one and it holds for both models.)
    median_final_pnl = float(np.percentile(final_pnl_bs, 50))
    pct5_final_pnl = float(np.percentile(final_pnl_bs, 5))  # worst 5% outcome by PnL
    pct1_final_pnl = float(np.percentile(final_pnl_bs, 1))  # worst 1% outcome by PnL
    median_max_dd = float(np.percentile(all_dds, 50))
    pct5_max_dd = float(np.percentile(all_dds, 95))  # 95th pct = worst-5% drawdown
    pct1_max_dd = float(np.percentile(all_dds, 99))  # 99th pct = worst-1% drawdown

    pct_of = (
        (lambda q: float(np.percentile(all_dds_pct, q)))
        if all_dds_pct is not None
        else (lambda q: None)
    )
    median_max_dd_pct = pct_of(50)
    pct5_max_dd_pct = pct_of(95)
    pct1_max_dd_pct = pct_of(99)

    # None = NOT ASSESSABLE, and it is the correct answer whenever there is no rule to test against
    # (no ruleset at all, or one with no drawdown limit — the "Unconstrained" row by design).
    # These used to default to 0.0, which is a claim, not an absence: the page reported "0%
    # probability of breaching" and "0% probability of passing" about the same run, and the second
    # reads as "this strategy never passes" when nothing was ever measured. Both fields are already
    # nullable in the DB and the frontend renders null as "—".
    prob_breach: Optional[float] = None
    prob_pass_eval: Optional[float] = None
    if ruleset:
        # Personal/demo: max_loss_eod = 0 is a sentinel (no trailing EOD rule), and the
        # old `or daily_loss_cap` fallback would wrongly use the per-day cap as a
        # whole-run limit. The helper translates their real drawdown rule
        # (max_drawdown_from_peak_pct of account_size) into the dollar limit MC measures.
        max_loss = effective_dd_limit_usd(ruleset)
        profit_target = ruleset.get("profit_target") or 0
        rtype = ruleset.get("ruleset_type", "prop_eval")
        # Breach probability MUST be measured on the basis the grade uses, or the headline number
        # and the letter contradict each other. On a compounding run the percent basis also gives
        # a no-limit ruleset something real to be tested against — total ruin — instead of nothing.
        limit_pct = effective_dd_limit_pct(ruleset)
        on_percent = dd_basis == "percent" and all_dds_pct is not None and limit_pct is not None
        if on_percent:
            prob_breach = float(np.mean(all_dds_pct > limit_pct))
        elif max_loss > 0 and dd_basis == "dollars":
            prob_breach = float(np.mean(all_dds > max_loss))
        if rtype == "prop_eval" and profit_target > 0 and (on_percent or max_loss > 0):
            # Pass = hit target AND never breach drawdown, per path. Use the BOOTSTRAP pool only:
            # reshuffle final PnLs are all the net total (order-invariant), so pairing all_pnls
            # with the target collapses the PnL test to a single value and skews the probability.
            # Bootstrap resamples vary both PnL and drawdown, so the pass rate is real.
            #
            # 🔴 The drawdown half is tested on the SAME BASIS as `prob_breach`. It was hardcoded
            # to the dollar comparison, so on a compounding run the two headline probabilities on
            # one card came off two different measurements: `prob_breach` said 4% against a percent
            # limit while `prob_pass_eval` said 0% because the dollar drawdowns of a grown account
            # blew through a limit written for its opening size. That is the exact contradiction
            # `dd_basis` exists to prevent, surviving in the one place it was not applied.
            if on_percent:
                dd_bs_pct = _dd_pct(equity_bs)
                within = dd_bs_pct <= limit_pct
            else:
                within = max_dd_bs <= max_loss
            prob_pass_eval = float(np.mean((final_pnl_bs >= profit_target) & within))
        elif rtype in ("prop_funded", "demo", "personal") and prob_breach is not None:
            # personal/demo have no profit-target requirement (profit_target = 0 sentinel) — per
            # spec they behave identically. "Pass" = never breached the drawdown rule. Without
            # personal here it fell through both branches and defaulted to 0.0, so a good personal
            # strategy would have reported 0% pass regardless of quality.
            # Keyed on prob_breach rather than max_loss so it also covers the percent basis, where
            # a no-limit ruleset is tested against ruin and there is no dollar limit to check.
            prob_pass_eval = 1.0 - prob_breach

    sampled_paths = equity_rs[:num_path_samples].tolist()

    dd_hist, dd_edges = np.histogram(all_dds, bins=50)
    # Final-PnL histogram uses the bootstrap pool to match the corrected percentiles —
    # reshuffles are order-invariant in sum and would spike the histogram at the net total.
    pnl_hist, pnl_edges = np.histogram(final_pnl_bs, bins=50)
    distribution = {
        "max_dd": {"counts": dd_hist.tolist(), "edges": dd_edges.tolist()},
        "final_pnl": {"counts": pnl_hist.tolist(), "edges": pnl_edges.tolist()},
    }
    # The SAME drawdowns as a percent, so the chart can be drawn on the basis the grade read. The
    # histogram was dollars-only, so on a compounding run the one picture of the drawdown
    # distribution — with a dollar limit line over it — was in the unit the letter had ignored.
    if all_dds_pct is not None:
        pct_hist, pct_edges = np.histogram(all_dds_pct, bins=50)
        distribution["max_dd_pct"] = {"counts": pct_hist.tolist(), "edges": pct_edges.tolist()}

    return {
        "median_final_pnl": round(median_final_pnl, 2),
        "pct5_final_pnl": round(pct5_final_pnl, 2),
        "pct1_final_pnl": round(pct1_final_pnl, 2),
        "median_max_dd": round(median_max_dd, 2),
        "pct5_max_dd": round(pct5_max_dd, 2),
        "pct1_max_dd": round(pct1_max_dd, 2),
        # The same drawdowns against the account. None on a fixed-size run, which has no balance
        # series of its own — see the dd_basis note above.
        "median_max_dd_pct": None if median_max_dd_pct is None else round(median_max_dd_pct, 2),
        "pct5_max_dd_pct": None if pct5_max_dd_pct is None else round(pct5_max_dd_pct, 2),
        "pct1_max_dd_pct": None if pct1_max_dd_pct is None else round(pct1_max_dd_pct, 2),
        # Which of the two the grade must read. Persisted, because a grade computed on the wrong
        # basis is wrong silently.
        "dd_basis": dd_basis,
        "prob_breach": None if prob_breach is None else round(prob_breach, 4),
        "prob_pass_eval": None if prob_pass_eval is None else round(prob_pass_eval, 4),
        # Which series the shuffle used. Not persisted — logged by the caller so a compounding run
        # is never silently re-modelled without it appearing anywhere.
        "shuffle_model": model,
        "sampled_paths": sampled_paths,
        "distribution": distribution,
    }


# ── Walk-forward helpers ───────────────────────────────────────────────────────


def _split_windows(start_date: str, end_date: str, n_windows: int) -> list[dict]:
    """Split the run's period into N windows, each 70% in-sample / 30% out-of-sample.

    ⚠ The two halves do NOT share a day. `is_end` used to equal `oos_start`, so the split date was
    backtested on BOTH sides — a day the "unseen" half had already seen. One day out of hundreds is
    immaterial to the numbers and is still a bar on the wrong side of the only line this phase draws.
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    total_days = (end - start).days
    if total_days < n_windows * 10:
        raise ValueError(f"Date range too short for {n_windows} walk-forward windows")
    window_days = total_days // n_windows
    windows = []
    for i in range(n_windows):
        w_start = start + timedelta(days=i * window_days)
        w_end = (start + timedelta(days=(i + 1) * window_days)) if i < n_windows - 1 else end
        split = w_start + timedelta(days=int(window_days * 0.7))
        windows.append(
            {
                "window": i + 1,
                "is_start": w_start.isoformat(),
                "is_end": split.isoformat(),
                "oos_start": (split + timedelta(days=1)).isoformat(),
                "oos_end": w_end.isoformat(),
            }
        )
    return windows


def _compute_sharpe(equity_curve_data: list[dict]) -> float:
    """Daily-returns Sharpe from an equity curve's per-trade rows (aggregated by date)."""
    # Aggregate per-trade profit into daily P&L first — Sharpe is a DAILY-returns metric.
    # (Previously this annualized per-trade mean/std as if each trade were a day.)
    daily: dict[str, float] = {}
    for t in equity_curve_data:
        d = t.get("date") or ""
        if not d:
            continue
        daily[d] = daily.get(d, 0.0) + (t.get("profit", 0.0) or 0.0)
    # Dated path — go through daily_sharpe so flat days inside the window are zero-filled, the
    # same canonical definition every run-completion path uses. A walk-forward window is a
    # contiguous calendar span, so its flat days are real observations.
    return daily_sharpe([{"date": d, "pnl": v} for d, v in daily.items()])


def _is_foundational(p: dict) -> bool:
    """Foundational params are injected config, not tunable strategy logic — excluded from
    sensitivity perturbation (and its time estimate). Keyed on the scanner category, with the
    MQL5 'f_' prefix as a defensive fallback for schemas missing the category field."""
    return p.get("category") == "foundational" or (p.get("name") or "").startswith("f_")


def _numeric(v):
    """The value as a float, or None when it is not a number. Booleans are deliberately excluded —
    `float(False)` is 0.0, so a numeric param sitting at 0 would satisfy a `{flag: false}` gate."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _same_value(actual, want) -> bool:
    """🔴 NUMBERS COMPARE AS NUMBERS.

    A fib level is the string `"1.0"` in a dropdown and the number `1.0` in the Custom box, and
    JS's `String(1.0)` is `"1"` — so a stringified compare says a Custom level of 1.0 is not 1.0.
    Python's `str(1.0)` is `"1.0"`, so THIS side happened to be right while the editor was wrong:
    two evaluators of one rule disagreeing in silence, which is the whole reason both now share
    this function's shape. Anything non-numeric falls back to the stringified compare, which is
    what `show_if` has always used and why `1` and `"1"` match.
    """
    a, b = _numeric(actual), _numeric(want)
    if a is not None and b is not None:
        return a == b
    return str(actual) == str(want)


def _cond_holds(cond: Optional[dict], read) -> bool:
    """Every condition holds. Shared by `show_if` and `disable_if`, exactly as the editor's
    `condHolds` shares it — the two evaluators must not drift, so they have one shape each side."""
    if not cond:
        return False
    for key, want in cond.items():
        actual = read(key)
        if isinstance(want, list):
            if not any(_same_value(actual, x) for x in want):
                return False
        elif not _same_value(actual, want):
            return False
    return True


def _reader_for(schema: list, base_params: dict):
    """Reads a param's EFFECTIVE value, resolving a dropdown's `custom_from` escape hatch.

    Mirrors `ParamEditor.readerFor`. Without it a dropdown set to Custom = 1.0 and the same
    dropdown set to 1.0 would gate differently, and the editor and the lab would disagree about
    which params are live.
    """
    by_name = {p.get("name"): p for p in schema if p.get("name")}

    def raw(name):
        return base_params.get(name, (by_name.get(name) or {}).get("default"))

    def visible(sib):
        return not sib.get("show_if") or _cond_holds(sib["show_if"], raw)

    def read(name):
        p = by_name.get(name)
        sib_name = (p or {}).get("custom_from")
        if sib_name and sib_name != name:
            sib = by_name.get(sib_name)
            # The sibling is visible exactly when its typed value is the one in force. A sibling
            # with no `show_if` is always in force — that is a schema error rather than a case to
            # handle, and the editor reads it the same way, so the two never disagree.
            if sib and visible(sib):
                return raw(sib_name)
        return raw(name)

    return read


def param_is_reachable(p: dict, base_params: dict, schema: Optional[list] = None) -> bool:
    """False when this run's params leave the param unable to move the result.

    A setting behind a switch the run has turned off CANNOT move the result — shifting it books a
    guaranteed 0% change, which reads as "tested, rock solid" for a parameter the strategy never
    read. That is the same false-reassurance shape as the no-op shifts below, arriving from the
    schema rather than from arithmetic, and it is the one the value-equality dedupe cannot catch
    (the value really does change; only the outcome cannot).

    THREE gates, and all three produce that same guaranteed 0% or an unactionable result:
      - `show_if` OFF — the editor would not even display the row;
      - `disable_if` HOLDING — the row is displayed and greyed, because its states cannot differ
        in this configuration;
      - SETTLED (`hidden` and still on its default) — the row is off the editor entirely. The
        shift is not a no-op here, which is exactly why it has to be excluded: sensitivity would
        rank a parameter high and send the reader looking for a control that no page renders.

    ⚠ The settled gate mirrors `ParamEditor.settled`, NOT `p.hidden` — a hidden param sitting AWAY
    from its default is shown on screen again, so it must be perturbed again too. Gating on
    `hidden` alone would silently drop a param the reader can see and edit.

    Mirrors `ParamEditor.visible` / `isInert` exactly, including the stringified comparison, the
    "any of these" array form and the `custom_from` resolution, so the lab perturbs precisely the
    set the lab would let you edit. ⚠ `schema` is what makes `custom_from` resolvable — omit it
    and a dropdown reading Custom = 1.0 gates differently here than it does on screen.
    """
    read = _reader_for(schema or [], base_params) if schema else base_params.get
    if p.get("show_if") and not _cond_holds(p["show_if"], read):
        return False
    if _is_settled(p, base_params):
        return False
    return not _cond_holds(p.get("disable_if"), read)


def _is_settled(p: dict, base_params: dict) -> bool:
    """`hidden` AND still on its default — the two halves of `ParamEditor.settled`."""
    if not p.get("hidden"):
        return False
    default = p.get("default")
    if default is None:
        return False
    name = p.get("name")
    if name not in base_params:
        return False
    return _same_value(base_params[name], default)


def perturbable_params(strategy: Optional[dict], base_params: dict) -> list[dict]:
    """The params sensitivity will actually perturb — numeric, present, non-foundational, reachable.
    Single source of truth for the run loop AND the UI time estimate, so the two cannot drift."""
    schema = (strategy or {}).get("param_schema") or []
    return [
        p
        for p in schema
        if p.get("type") in ("int", "float", "double")
        and p.get("name") in base_params
        and not _is_foundational(p)
        and param_is_reachable(p, base_params, schema)
    ]


def sensitivity_param_count(strategy: Optional[dict], base_params: dict) -> int:
    return len(perturbable_params(strategy, base_params))


def shifted_value(param: dict, baseline_val, factor: float):
    """`(value, refusal)` — the shifted value, or None plus a plain-English refusal.

    ⚠ **The schema's `min`/`max` are respected, and an out-of-range shift is REFUSED rather than
    clamped.** `exec_sl_custom` is a fib ratio bounded (0, 1.0] sitting at 0.886, so its +25% shift
    is 1.1075 — which the strategy's own `__post_init__` raises on, failing the child run and
    losing the shift with nothing on screen to say why. Clamping to the bound instead would run a
    backtest at +12.8% under a label reading `+25%`, i.e. a magnitude that is not the one stated —
    this repo's signature defect. Refusing is the honest option, and the refusal is reported.
    """
    try:
        new_val = baseline_val * factor
    except TypeError:
        return (None, "value is not numeric")
    if param.get("type") == "int":
        new_val = int(round(new_val))
    lo, hi = param.get("min"), param.get("max")
    if lo is not None and new_val < lo:
        return (None, f"below the parameter's minimum of {lo}")
    if hi is not None and new_val > hi:
        return (None, f"above the parameter's maximum of {hi}")
    return (new_val, None)


def sensitivity_shift_count(runner: str) -> int:
    """Shifts per param: MT5 runs ±10% (2), NT8 runs ±10%/±25% (4). Matches SHIFTS below."""
    return 2 if runner == "mt5" else 4


def _mins_per_job(runner: str) -> float:
    """Minutes per child backtest, by runner. Python replays locally off a warm cache — a job is
    seconds, not minutes — so quoting it the NT8 figure told the user to expect ~30x the real wait.
    Stated once and used by BOTH phase estimates; the walk-forward estimate was hardcoded to the
    NT8 number regardless of runner."""
    return 0.2 if runner == "python" else 1.5 if runner == "mt5" else 5.0


def _estimate_wf_duration_min(n_windows: int, runner: str = "ninjatrader") -> int:
    return max(1, int(n_windows * 2 * _mins_per_job(runner)))  # 2 backtests per window


def _estimate_sens_duration_min(
    n_params: int, runner: str = "ninjatrader", source_run: Optional[dict] = None
) -> int:
    """Wall-clock minutes for the sensitivity phase.

    Two corrections, both from a real measurement rather than a constant.

    ⚠ **A per-job constant is wrong by construction, because the cost scales with the WINDOW.**
    `_mins_per_job` says 0.2 min for python — true for a short backtest, and a 6.6-year M15 replay
    (~165k bars) measured **69s per child, 65-71s across children**. The modal therefore quoted
    ~12 minutes for a job that would have taken ~69. So when the source run's own duration is on
    the record, use it: it is the same replay over the same bars, which is exactly the reasoning
    the optimizer modal's estimate already uses.

    ⚠ **The python path runs them in PARALLEL**, so the serial sum is no longer the wall clock —
    dividing by the worker count is the difference between 69 minutes and about 7."""
    n_jobs = n_params * sensitivity_shift_count(runner)
    per_job = _mins_per_job(runner)
    if source_run:
        started, completed = source_run.get("started_at"), source_run.get("completed_at")
        # `is not None`, never truthiness — a timestamp of 0 is a value, not an absence, and
        # `if started` would silently drop it back to the constant.
        if started is not None and completed is not None and completed > started:
            per_job = max(per_job, (completed - started) / 60.0)

    workers = 1
    if runner == "python" and n_jobs:
        try:
            from backtest.optimizer import default_workers

            workers = default_workers(n_jobs)
        except Exception:
            workers = 1
    # Ceiling, not floor: N jobs over W workers takes ceil(N/W) rounds, and rounding down promises
    # a wait the machine cannot meet.
    rounds = math.ceil(n_jobs / workers) if workers else n_jobs
    return max(1, int(math.ceil(rounds * per_job)))


def phases_requested(include_walk_forward: bool, include_sensitivity: bool) -> list[str]:
    """What was ASKED for — the ONE definition, used at creation and again at the end.

    ⚠ Written when the row is INSERTED, not when the task finishes. It is the only thing that
    separates "walk-forward was never requested" from "walk-forward ran and produced nothing":
    `walk_forward_summary IS NULL` means both, and grading reads a NULL as not-run, i.e. neither
    credit nor penalty. Recorded at the end it is missing for the entire run — so the page has to
    guess which phases are coming while a test is live, and a task killed mid-flight (a backend
    restart is enough) leaves no record of what was asked for at all."""
    phases = ["monte_carlo"]
    if include_walk_forward:
        phases.append("walk_forward")
    if include_sensitivity:
        phases.append("sensitivity")
    return phases


def sensitivity_plan(
    numeric_params: list, base_params: dict, shifts: list
) -> tuple[list[dict], list[str]]:
    """The one-param-at-a-time shift list, and what was refused. PURE — no DB, no backtests.

    Split out of the run loop so the DECISIONS (which shifts are worth running) are testable
    without running anything, and so the serial and parallel executors cannot disagree about what
    the experiment IS. Returns `[{param, label, value}]` in the order they should run, plus the
    human-readable skip reasons.

    ⚠ It is deliberately NOT a grid. Sensitivity moves ONE parameter at a time from the baseline;
    the cartesian product of the same shifts is a different and far larger experiment answering a
    different question."""
    plan: list[dict] = []
    skipped: list[str] = []
    for param in numeric_params:
        pname = param["name"]
        baseline_val = base_params[pname]
        seen_vals: set = set()
        for shift_label, factor in shifts:
            new_val, refusal = shifted_value(param, baseline_val, factor)
            if refusal is not None:
                skipped.append(f"{pname} {shift_label} ({refusal})")
                continue
            # A perturbation landing back on the baseline TESTS NOTHING — it re-runs the identical
            # backtest and books a 0% delta, which reads as "rock solid" when the truth is "never
            # measured". Two common causes: the param is 0 (0 x 1.10 == 0), or an int rounds
            # straight back (pivot width 5: +10% -> 6 and +25% -> 6, so four shifts probe two
            # values). Measured on 630cefbebd8347db: 43 of 60 backtests were exact re-runs.
            if new_val == baseline_val or new_val in seen_vals:
                skipped.append(f"{pname} {shift_label} (={new_val})")
                continue
            seen_vals.add(new_val)
            plan.append({"param": pname, "label": shift_label, "value": new_val})
    return plan, skipped


def walk_forward_feasibility(trade_count: int, n_windows: int) -> tuple[bool, str]:
    """Can this many trades support this many windows? `(ok, why-not)`.

    Pure arithmetic, and it is knowable BEFORE ten backtests run: each window's out-of-sample half
    is 30% of 1/N of the run, and a window whose either side closes fewer than
    `_WF_MIN_TRADES_PER_WINDOW` trades is excluded as not-assessable. When EVERY window will be
    thin, the whole phase can only return "not assessable" — which then caps the grade at B.

    Measured on the lab's own numbers: at 5 windows the out-of-sample halves of a 126-trade run
    closed 6, 6, 6, 12 and 8 trades, every one under the floor. Clearing it at 5 windows needs
    roughly 5 x 20 / 0.3 ≈ 333 trades, and the strategies here run 126-165 — so the shipped default
    guaranteed an unassessable walk-forward, every time, with nothing on screen saying so.
    """
    if n_windows < 1:
        return (False, "Walk-forward needs at least one window")
    oos_per_window = trade_count / n_windows * 0.3
    if oos_per_window >= _WF_MIN_TRADES_PER_WINDOW:
        return (True, "")
    max_windows = int(trade_count * 0.3 // _WF_MIN_TRADES_PER_WINDOW)
    fix = (
        f"Use {max_windows} window(s) or fewer"
        if max_windows >= 1
        else f"This run needs about {int(_WF_MIN_TRADES_PER_WINDOW / 0.3)} trades for even one "
        f"window to be assessable"
    )
    return (
        False,
        (
            f"{n_windows} windows over {trade_count} trades leaves about "
            f"{oos_per_window:.0f} out-of-sample trades each, under the {_WF_MIN_TRADES_PER_WINDOW} "
            f"needed for a Sharpe to mean anything — the walk-forward will report 'not assessable' "
            f"and cap the grade at B. {fix}."
        ),
    )


def is_cancelled(stress_test_id: str) -> bool:
    """Has the row been cancelled out from under this task?

    Checked between children, so a cancel stops the REMAINING work rather than only relabelling the
    row. The optimizer's cancel shipped without this and kept every core busy after 'cancelling',
    then overwrote its own cancelled status with `complete` when the work finished."""
    st = lab_db.get_stress_test(stress_test_id)
    return bool(st and str(st.get("status", "")).startswith("failed"))


# ── VPS child-run helper (mirrors sweep_runner._run_one) ──────────────────────


def _sens_child_row(ctx: dict, entry: dict, child_id: str) -> dict:
    """The lab row for one sensitivity shift. Shared by both executors so a child cannot come out
    differently depending on which one ran it — including `measured_on`, the baseline's physics."""
    src = ctx["source_run"]
    return {
        "run_id": child_id,
        "strategy_id": src["strategy_id"],
        "instrument": src["instrument"],
        "params": {**ctx["base_params"], entry["param"]: entry["value"]},
        "bar_type": src["bar_type"],
        "bar_value": src["bar_value"],
        "start_date": src["start_date"],
        "end_date": src["end_date"],
        "commission_per_side": src["commission_per_side"],
        "slippage_ticks": src["slippage_ticks"],
        "status": "running",
        "created_at": int(time.time()),
        "stress_test_id": ctx["stress_test_id"],
        "walk_forward_window_id": f"sens_{entry['param']}_{entry['label']}",
        "runner": ctx["runner"],
        **ctx["measured_on"],
    }


async def _run_shifts_serial(plan: list, ctx: dict) -> list[dict]:
    """One child backtest at a time.

    This is the path for NT8 and MT5, and it is not a fallback — each drives ONE physical terminal,
    so there is nothing to parallelise and firing concurrent jobs at a single Strategy Tester would
    be actively harmful. It is also the path any runner takes when the pool cannot be used."""
    out = []
    for entry in plan:
        if is_cancelled(ctx["stress_test_id"]):
            break
        child_id = uuid.uuid4().hex[:16]
        lab_db.insert_run_stress_test_child(_sens_child_row(ctx, entry, child_id))
        src = ctx["source_run"]
        job_spec = {
            "job_id": child_id,
            "strategy_class": ctx["strategy"]["class_name"],
            "instrument": src["instrument"],
            "params": {**ctx["base_params"], entry["param"]: entry["value"]},
            "bar_type": src["bar_type"],
            "bar_value": src["bar_value"],
            "start_date": src["start_date"],
            "end_date": src["end_date"],
            "commission_per_side": src["commission_per_side"],
            "slippage_ticks": src["slippage_ticks"],
            **ctx["measured_on"],
        }
        ok = await _run_child_backtest(child_id, job_spec, ctx["runner"])
        child = lab_db.get_run(child_id) if ok else None
        out.append(
            {
                "entry": entry,
                "run_id": child_id,
                "ok": ok,
                "pf": (child or {}).get("profit_factor"),
                "pnl": (child or {}).get("net_pnl") or 0.0,
            }
        )
    return out


async def _run_shifts_pooled(plan: list, ctx: dict) -> list[dict]:
    """Every shift in ONE sweep across this box's cores. Python runner only.

    🔴 **Why a process pool and not `asyncio.gather` over the existing per-child path.**
    `python_runner.start_backtest` runs each backtest on a THREAD, and an engine replay is pure
    Python stepping one bar at a time — GIL-bound. Gathering N of those is the obvious fix, would
    look like it worked, and would buy almost nothing. MEASURED before this change: 69s per child
    (65-71s across children, i.e. compute-bound, not I/O), 60 shifts, ~69 minutes on ONE core of a
    12-core box, while `backtest/optimizer.run_sweep` had been fanning optimizer grids across every
    core the whole time.

    ⚠ It submits through `runner_dispatch` -> `python_runner`, NOT by calling `run_sweep` here,
    because `_cost_profile` lives there. A second caller building its own cost profile is exactly
    how the children came to be measured on a free book while their parent was charged.

    ⚠ Rows are matched back by `(param, value)`, never by INDEX: `run_sweep` compacts its result
    list on cancellation, so a cancelled sweep returns fewer rows than combos and index-matching
    would silently attribute one shift's numbers to a different parameter. `sensitivity_plan`
    dedupes values per param, so the pair is unique."""
    from services import runner_dispatch

    src = ctx["source_run"]
    ids = {(e["param"], e["value"]): uuid.uuid4().hex[:16] for e in plan}
    for entry in plan:
        lab_db.insert_run_stress_test_child(
            _sens_child_row(ctx, entry, ids[(entry["param"], entry["value"])])
        )

    job_id = f"sens_{ctx['stress_test_id']}"
    spec = {
        "job_id": job_id,
        "strategy_class": ctx["strategy"]["class_name"],
        "instrument": src["instrument"],
        "bar_type": src["bar_type"],
        "bar_value": src["bar_value"],
        "start_date": src["start_date"],
        "end_date": src["end_date"],
        "commission_per_side": src["commission_per_side"],
        "slippage_ticks": src["slippage_ticks"],
        "fixed_params": ctx["base_params"],
        "param_sets": [{e["param"]: e["value"]} for e in plan],
        **ctx["measured_on"],
    }
    await asyncio.to_thread(runner_dispatch.start_native_optimization, spec, "python")

    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        if is_cancelled(ctx["stress_test_id"]):
            try:
                await asyncio.to_thread(runner_dispatch.cancel_job, job_id, "python")
            except Exception:
                pass
            break
        try:
            sd = await asyncio.to_thread(runner_dispatch.job_status, job_id, "python")
        except Exception:
            continue
        if not str(sd.get("status", "running")).startswith("running"):
            break

    rows = []
    try:
        res = await asyncio.to_thread(runner_dispatch.native_opt_results, job_id, "python")
        rows = res.get("combos") or []
    except Exception as exc:
        log.warning("Sensitivity %s: could not read sweep results — %s", ctx["stress_test_id"], exc)

    by_key = {}
    for row in rows:
        params = row.get("params") or {}
        if len(params) == 1:
            ((pname, val),) = params.items()
            by_key[(pname, val)] = row.get("kpis") or {}

    out = []
    for entry in plan:
        child_id = ids[(entry["param"], entry["value"])]
        kpis = by_key.get((entry["param"], entry["value"]))
        if kpis is None:
            # Never written as a zero-KPI "complete" row: a shift the sweep did not return was not
            # measured, and a complete row reading 0 would be scored as "this parameter does
            # nothing" — the most reassuring answer available for an absent measurement.
            lab_db.update_run_status(
                child_id, "failed_unknown", "sweep returned no result for this shift"
            )
            out.append({"entry": entry, "run_id": child_id, "ok": False, "pf": None, "pnl": 0.0})
            continue
        # ⚠ No equity_curve / daily_pnl: a sweep worker returns KPIs only. Nothing reads a
        # sensitivity child's curve (scoring uses profit factor and net P&L, and the UI never
        # navigates to one), so the paths are NULL rather than pointing at files that do not
        # exist. A canonical Sharpe is likewise not computed — there is no daily series to
        # compute it from, and inventing one would be a fabricated measurement.
        lab_db.update_run_complete(
            child_id, kpis, {"equity_curve": None, "trades": None, "daily_pnl": None}
        )
        out.append(
            {
                "entry": entry,
                "run_id": child_id,
                "ok": True,
                "pf": kpis.get("profit_factor"),
                "pnl": kpis.get("net_pnl") or 0.0,
            }
        )
    return out


async def _run_child_backtest(run_id: str, job_spec: dict, runner: str = "ninjatrader") -> bool:
    """Start a VPS backtest and poll to completion. Returns True on success."""
    from services import runner_dispatch

    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        return False

    started_at = time.time()
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            sd = await asyncio.to_thread(runner_dispatch.job_status, run_id)
        except Exception:
            if time.time() - started_at > _STALL_KILL_SEC:
                lab_db.update_run_status(run_id, "failed_timeout", "Lost VPS contact")
                return False
            continue

        status = sd.get("status", "running")
        if status == "complete":
            try:
                result = await asyncio.to_thread(runner_dispatch.job_results, run_id)
                kpis = result.get("kpis", {})
                equity_curve = result.get("equity_curve", [])
                daily_pnl = result.get("daily_pnl", [])
                run_dir = _RESULTS_DIR / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                eq_path = run_dir / "equity_curve.json"
                dp_path = run_dir / "daily_pnl.json"
                eq_path.write_text(json.dumps(equity_curve, default=str))
                dp_path.write_text(json.dumps(daily_pnl, default=str))
                apply_canonical_sharpe(kpis, daily_pnl)  # consistent daily-√252 Sharpe
                lab_db.update_run_complete(
                    run_id,
                    kpis,
                    {
                        "equity_curve": str(eq_path),
                        "trades": None,
                        "daily_pnl": str(dp_path),
                    },
                )
            except Exception as exc:
                lab_db.update_run_status(
                    run_id, "failed_unknown", f"Could not fetch results: {exc}"
                )
                return False
            return True

        if status.startswith("failed"):
            lab_db.update_run_status(run_id, status, sd.get("error") or "")
            return False

        if time.time() - started_at > _STALL_KILL_SEC:
            from services import runner_dispatch as vc

            try:
                await asyncio.to_thread(vc.cancel_job, run_id)
            except Exception:
                pass
            lab_db.update_run_status(run_id, "failed_timeout", "Stalled")
            return False


# ── Walk-forward runner ────────────────────────────────────────────────────────

_NATIVE_WF_STALL_SEC = 3600  # 1 hour


async def _run_native_walk_forward(
    stress_test_id: str,
    st: dict,
    source_run: dict,
    strategy: dict,
) -> bool:
    """
    Drive NT8's built-in Walk Forward mode for a strategy with fixed params.
    One VPS call instead of N orchestrated backtests.
    """
    import numpy as np

    from services import runner_dispatch

    job_id = f"nwf_{stress_test_id}"
    wf_windows = st.get("walk_forward_windows", 5)

    spec = {
        "job_id": job_id,
        "strategy_class": strategy["class_name"],
        "instrument": source_run["instrument"],
        "bar_type": source_run["bar_type"],
        "bar_value": source_run["bar_value"],
        "start_date": source_run["start_date"],
        "end_date": source_run["end_date"],
        "commission_per_side": source_run["commission_per_side"],
        "slippage_ticks": source_run["slippage_ticks"],
        "params": source_run.get("params", {}),
        "wf_windows": wf_windows,
        "oos_pct": 30,
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_native_walkforward, spec)
    except Exception as exc:
        log.warning(
            "Native WF submit failed for stress_test %s: %s — falling back to serial",
            stress_test_id,
            exc,
        )
        return False

    started_at = time.time()
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            sd = await asyncio.to_thread(runner_dispatch.job_status, job_id)
        except Exception:
            if time.time() - started_at > _NATIVE_WF_STALL_SEC:
                log.error("Native WF %s lost VPS contact", job_id)
                return False
            continue

        status = sd.get("status", "running")
        if status == "complete":
            break
        if status.startswith("failed"):
            log.warning("Native WF %s failed: %s — falling back to serial", job_id, status)
            return False
        if time.time() - started_at > _NATIVE_WF_STALL_SEC:
            try:
                await asyncio.to_thread(runner_dispatch.cancel_job, job_id)
            except Exception:
                pass
            log.error("Native WF %s timed out", job_id)
            return False

    try:
        result = await asyncio.to_thread(runner_dispatch.native_wf_results, job_id)
    except Exception as exc:
        log.warning("Native WF %s results fetch failed: %s", job_id, exc)
        return False

    windows_raw = result.get("windows", [])
    if not windows_raw:
        return False

    # Pair IS and OOS rows by window number and compute Sharpe degradation.
    by_window: dict[int, dict] = {}
    for row in windows_raw:
        w = row.get("window", 0)
        if w not in by_window:
            by_window[w] = {}
        by_window[w][row.get("type", "")] = row

    summary = []
    degradations = []
    for w_num in sorted(by_window):
        pair = by_window[w_num]
        is_row = pair.get("is", {})
        oos_row = pair.get("oos", {})
        is_pnl = is_row.get("net_pnl")
        oos_pnl = oos_row.get("net_pnl")
        # Derive a simple per-window Sharpe proxy from PF (no trade-level data from native WF).
        is_pf = is_row.get("profit_factor") or 0.0
        oos_pf = oos_row.get("profit_factor") or 0.0
        # IS→OOS degradation on PF (consistent with how cumulative mode uses Sharpe)
        if is_pf > 0:
            degradations.append(max(0.0, 1.0 - oos_pf / is_pf))
        summary.append(
            {
                "window": w_num,
                "is_pnl": round(is_pnl, 2) if is_pnl is not None else None,
                "oos_pnl": round(oos_pnl, 2) if oos_pnl is not None else None,
                "is_pf": round(is_pf, 4),
                "oos_pf": round(oos_pf, 4),
                # Sharpe fields expected by the existing WF summary schema
                "is_sharpe": None,
                "oos_sharpe": None,
            }
        )

    # No window had IS PF > 0, so IS→OOS degradation isn't assessable. Store None (not 0.0) —
    # matching the serial path's fix-#4 convention. 0.0 would read as "0% degradation = solid
    # robustness" for a strategy that was unprofitable in every in-sample window; None lets
    # grading treat it as not-run (neither credit nor penalty) and the UI show "n/a".
    avg_deg = float(np.mean(degradations)) if degradations else None
    lab_db.update_stress_test_walk_forward(stress_test_id, summary, avg_deg)
    return True


async def run_walk_forward_task(stress_test_id: str) -> tuple[bool, Optional[str]]:
    """
    Run walk-forward windows. Uses NT8 native WF mode when the source run comes from
    a native optimization (one data load, all windows); falls back to N orchestrated
    backtests for standalone single runs.

    Returns `(ok, error)`. **`ok=False` means the phase RAN AND FAILED, which is not the same fact
    as "walk-forward was not requested"** — grading must be able to tell them apart, so the caller
    passes the distinction through rather than letting a NULL summary stand for both. Until
    2026-08-05 this returned a bare bool that the caller discarded: a walk-forward that crashed
    left `walk_forward_summary` NULL, grading read that as *not run*, and the test could be handed
    an **A** with the caveat "walk-forward not run — grade may improve with full analysis". It had
    run; it had failed; and the letter said the opposite of what happened.

    ⚠ It sets NO terminal status of its own. It used to stamp `failed_wf_split` / `failed_no_run`,
    which the sensitivity phase and then grading immediately overwrote — so the row ended
    `complete` while still carrying the failure's `error_message` in the red box. The orchestrator
    owns the row's status; this function reports.

    WHAT THIS MEASURES, precisely: the SAME fixed parameters are run on each window's in-sample and
    out-of-sample halves — nothing is re-tuned between them. So a large IS→OOS drop means the edge
    did not hold up in the later period; it does NOT show that the parameters were overfitted,
    because no fitting happens here for the out-of-sample half to be blind to. Detecting overfit
    would need the optimizer re-run on each in-sample half and its winner tested on the OOS half.
    """
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        return (False, "Stress test row disappeared")

    source_run = lab_db.get_run(st["run_id"])
    if not source_run:
        return (False, "Source run not found")

    strategy = lab_db.get_strategy(source_run["strategy_id"])
    if not strategy:
        return (False, "Strategy not found")

    runner = strategy.get("runner", "ninjatrader")

    # Native WF path: used when source run has optimization_id (winner from native opt).
    # ⚠ It FALLS THROUGH to the serial path when it fails — the docstring promised that fallback
    # since the day it was written and the code returned the failure instead, so a native WF that
    # could not be submitted ended the whole phase rather than being re-run window by window.
    if source_run.get("optimization_id") and runner == "ninjatrader":
        if await _run_native_walk_forward(stress_test_id, st, source_run, strategy):
            return (True, None)
        log.info("Native WF unavailable for %s — running the windows serially", stress_test_id)

    try:
        windows = _split_windows(
            source_run["start_date"],
            source_run["end_date"],
            st.get("walk_forward_windows", 5),
        )
    except ValueError as exc:
        return (False, str(exc))

    # The baseline's own physics — costs, broker, sizing. Every window is measured on them or the
    # IS→OOS comparison is between two different books. See child_measurement_fields.
    measured_on = child_measurement_fields(source_run)

    summary = []
    failed_periods: list[str] = []
    for w in windows:
        if is_cancelled(stress_test_id):
            return (False, "cancelled")
        window_data = {
            "window": w["window"],
            "is_pnl": None,
            "oos_pnl": None,
            "is_sharpe": None,
            "oos_sharpe": None,
            "is_trades": None,
            "oos_trades": None,
        }

        for period_type, p_start, p_end in [
            ("is", w["is_start"], w["is_end"]),
            ("oos", w["oos_start"], w["oos_end"]),
        ]:
            if is_cancelled(stress_test_id):
                return (False, "cancelled")
            child_id = uuid.uuid4().hex[:16]
            wf_tag = f"wf_{w['window']}_{period_type}"
            lab_db.insert_run_stress_test_child(
                {
                    "run_id": child_id,
                    "strategy_id": source_run["strategy_id"],
                    "instrument": source_run["instrument"],
                    "params": source_run.get("params", {}),
                    "bar_type": source_run["bar_type"],
                    "bar_value": source_run["bar_value"],
                    "start_date": p_start,
                    "end_date": p_end,
                    "commission_per_side": source_run["commission_per_side"],
                    "slippage_ticks": source_run["slippage_ticks"],
                    "status": "running",
                    "created_at": int(time.time()),
                    "stress_test_id": stress_test_id,
                    "walk_forward_window_id": wf_tag,
                    "runner": runner,
                    **measured_on,
                }
            )

            job_spec = {
                "job_id": child_id,
                "strategy_class": strategy["class_name"],
                "instrument": source_run["instrument"],
                "params": source_run.get("params", {}),
                "bar_type": source_run["bar_type"],
                "bar_value": source_run["bar_value"],
                "start_date": p_start,
                "end_date": p_end,
                "commission_per_side": source_run["commission_per_side"],
                "slippage_ticks": source_run["slippage_ticks"],
                **measured_on,
            }
            ok = await _run_child_backtest(child_id, job_spec, runner)
            if not ok:
                # A period that never produced a result is RECORDED, not silently dropped. Its
                # window keeps None on that side, which excludes it from the average — and the
                # count is what lets the caller say "3 of 10 periods failed" instead of reporting
                # a degradation off whatever survived.
                failed_periods.append(wf_tag)
                continue

            child = lab_db.get_run(child_id)
            if not child:
                failed_periods.append(wf_tag)
                continue

            # No curve on disk = the Sharpe could not be COMPUTED, which is not the claim
            # "the Sharpe was zero". It used to write 0.0, which excludes the window from the
            # average either way (0.0 fails the IS floor) but then draws a real zero bar on the
            # chart for a period nothing was measured on.
            eq_path = child.get("equity_curve_path")
            sharpe: Optional[float] = None
            if eq_path and Path(eq_path).exists():
                eq_data = json.loads(Path(eq_path).read_text())
                sharpe = round(_compute_sharpe(eq_data), 4)
            pnl = child.get("net_pnl") or 0.0

            if period_type == "is":
                window_data["is_pnl"] = round(pnl, 2)
                window_data["is_sharpe"] = sharpe
                window_data["is_trades"] = child.get("trade_count") or 0
            else:
                window_data["oos_pnl"] = round(pnl, 2)
                window_data["oos_sharpe"] = sharpe
                window_data["oos_trades"] = child.get("trade_count") or 0

        summary.append(window_data)

    # Compute avg IS→OOS Sharpe degradation, but ONLY over windows with a MEANINGFUL positive
    # IS Sharpe. 1 - OOS/IS is interpretable as "degradation" only when the in-sample window had
    # a real edge to degrade from:
    #   - IS Sharpe <= 0          → no in-sample edge; a negative denominator flips the sign (a
    #                               worse OOS reads as an *improvement*).
    #   - 0 < IS Sharpe < floor   → a near-zero denominator explodes the ratio. A window that
    #                               broke even in-sample (Sharpe ~0.002) once produced a 539,229%
    #                               per-window value and a 134,540% average. Require a floor so a
    #                               flat window is excluded as not-assessable, not amplified.
    # Each surviving window is also clamped to a sane band so one noisy small-sample window (a
    # couple of trades) can't blow up the mean. If no window qualifies, degradation is not
    # assessable → store None (UI shows "n/a", grading treats as not-run, never "solid").
    #
    # A window is ALSO excluded when either side closed too few trades to support a Sharpe at all.
    # This is the same honesty rule as the floor above, applied to sample size instead of magnitude:
    # both sides of `1 - OOS/IS` are mean/variance estimates, and over a handful of trades one trade
    # dominates both. Measured on stress test 630cefbebd8347db (126 trades over 5 years, split 5
    # ways): the out-of-sample halves closed 6, 6, 6, 12 and 8 trades, window 1 produced a Sharpe of
    # -3.66 and window 5 +2.66 off six trades each, and averaging them was reported as "38.6%
    # degradation" — false precision on noise.
    #
    # Refusing is the right answer AND an actionable one: `walk_forward_windows` is a user setting,
    # so the fix is fewer, longer windows, not a looser test.
    thin = [
        w["window"]
        for w in summary
        if (w.get("is_trades") or 0) < _WF_MIN_TRADES_PER_WINDOW
        or (w.get("oos_trades") or 0) < _WF_MIN_TRADES_PER_WINDOW
    ]
    degradations = [
        _clamp_wf_degradation(1.0 - (w.get("oos_sharpe") or 0) / w["is_sharpe"])
        for w in summary
        if w.get("is_sharpe") and w["is_sharpe"] >= _WF_IS_SHARPE_FLOOR and w["window"] not in thin
    ]
    avg_deg = float(np.mean(degradations)) if degradations else None
    if thin:
        log.info(
            "Walk-forward %s: %d of %d window(s) excluded — under %d trades on one side "
            "(windows %s). Re-run with fewer walk_forward_windows for a longer sample each.",
            stress_test_id,
            len(thin),
            len(summary),
            _WF_MIN_TRADES_PER_WINDOW,
            ", ".join(str(w) for w in thin),
        )

    lab_db.update_stress_test_walk_forward(stress_test_id, summary, avg_deg)

    # Every period failing is a FAILED phase, not a clean summary of nothing. Reported as an error
    # so the row can say so; a partial failure keeps the summary (the windows that ran are real)
    # and is named in the log.
    if failed_periods and len(failed_periods) >= 2 * len(windows):
        return (
            False,
            f"every walk-forward backtest failed ({len(failed_periods)} of "
            f"{2 * len(windows)} periods)",
        )
    if failed_periods:
        log.warning(
            "Walk-forward %s: %d of %d period backtests failed (%s)",
            stress_test_id,
            len(failed_periods),
            2 * len(windows),
            ", ".join(failed_periods),
        )
    return (True, None)


# ── Sensitivity runner ─────────────────────────────────────────────────────────


async def run_sensitivity_task(stress_test_id: str) -> tuple[bool, Optional[str]]:
    """Run ±10%/±25% param perturbations sequentially through NT8. Updates DB when done.

    Returns `(ok, error)` for the same reason walk-forward does: **ran-and-failed and never-ran are
    different facts and must not share a value.** A phase that produced nothing used to leave
    `sensitivity_summary` NULL, which grading reads as *not run* — neither credit nor penalty —
    so a crashed sensitivity phase cost the test nothing and said nothing.

    THE METRIC IS PROFIT FACTOR, not net P&L (changed 2026-07-30). Two reasons, and the second is
    the load-bearing one:

    1. Net P&L is a DOLLAR figure, so any parameter that scales position size swamps every real
       robustness signal by arithmetic alone. On stress test 630cefbebd8347db the score was 85.8%
       and came entirely from `exec_risk_pct` — turning risk up 25% turns profit up ~25%, which is
       multiplication, not fragility. Scored on profit factor the same run reads 12.6%, and the
       most sensitive setting becomes `aplus_window`, which is an actual strategy choice.
    2. The OTHER sensitivity path — `_apply_grid_sensitivity_if_available`, used when the source run
       came from an optimizer — has ALWAYS reported a profit-factor drop, and both paths write the
       same `sensitivity_max_degradation` field and are judged against the same grading thresholds.
       So one strategy could get two different verdicts depending on which path produced its score.
       Whatever the right metric is, the two must agree; this makes them agree.

    Magnitude is ABSOLUTE (`|new - base| / base`), keeping the old behaviour that a shift which
    IMPROVES the result is just as much evidence the result moves. The grid path measures a one-
    sided drop; both are a fraction of profit factor, which is what the shared threshold needs.
    """
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        return (False, "Stress test row disappeared")

    source_run = lab_db.get_run(st["run_id"])
    if not source_run:
        return (False, "Source run not found")

    strategy = lab_db.get_strategy(source_run["strategy_id"])
    if not strategy:
        return (False, "Strategy not found")

    runner = strategy.get("runner", "ninjatrader")
    base_params: dict = source_run.get("params") or {}
    param_schema: list = strategy.get("param_schema") or []

    if not base_params or not param_schema:
        # None, not 0.0 — nothing was measured, and 0.0 would report "no parameter moved the
        # result", the most reassuring answer available, on a strategy with no parameters to move.
        # This is a SUCCESSFUL run of the phase: it asked the question and the honest answer is
        # "there is nothing here to perturb", which grading already treats as not-assessable.
        lab_db.update_stress_test_sensitivity(stress_test_id, {}, None)
        return (True, None)

    # Only perturb numeric STRATEGY-LOGIC params — the same set the optimizer tunes — and only
    # those the run can actually REACH (see param_is_reachable). Foundational params (injected
    # config: account size, risk %, commission) are not tunable and many sit at the -1 sentinel.
    numeric_params = perturbable_params(strategy, base_params)
    unreachable = [
        p["name"]
        for p in param_schema
        if p.get("type") in ("int", "float", "double")
        and p.get("name") in base_params
        and not _is_foundational(p)
        and not param_is_reachable(p, base_params)
    ]
    if unreachable:
        log.info(
            "Sensitivity %s: %d param(s) skipped — their own show_if gate is off in this run, "
            "so no shift of them can change the result: %s",
            stress_test_id,
            len(unreachable),
            ", ".join(unreachable),
        )

    # Baseline metrics. Profit factor is the scored one (see the docstring); net P&L is kept
    # alongside it purely so a shift's dollar effect is still visible on the record.
    baseline_pnl = source_run.get("net_pnl") or 0.0
    baseline_pf = source_run.get("profit_factor")
    # A baseline profit factor that is missing, zero or infinite gives nothing to measure a change
    # against. That is NOT-ASSESSABLE, and it must be reported as None rather than 0.0 — a 0.0 here
    # would read as "no parameter moved the result", the most reassuring possible answer, on a run
    # where nothing was actually measured. Grading treats a None the same as not-run.
    pf_usable = baseline_pf is not None and np.isfinite(baseline_pf) and baseline_pf > 0
    if not pf_usable:
        log.warning(
            "Sensitivity %s: baseline profit factor is %r — degradation is not assessable",
            stress_test_id,
            baseline_pf,
        )

    # MT5 runs one VPS job at a time — 4 shifts × N params = very long queues.
    # Use 2 shifts for slow runners; ±10% is sufficient to flag parameter sensitivity.
    if runner == "mt5":
        SHIFTS = [("+10%", 1.10), ("-10%", 0.90)]
    else:
        SHIFTS = [("+10%", 1.10), ("-10%", 0.90), ("+25%", 1.25), ("-25%", 0.75)]
    # The baseline's own physics. `degradation` divides a CHILD's profit factor by the BASELINE's,
    # so a child measured on a different cost model reports the cost gap as the parameter's
    # fragility. See child_measurement_fields.
    measured_on = child_measurement_fields(source_run)

    # WHAT to run (pure) is decided before anything runs, so the two executors cannot disagree
    # about the experiment, and the decisions are testable without a backtest.
    plan, skipped = sensitivity_plan(numeric_params, base_params, SHIFTS)

    ctx = {
        "stress_test_id": stress_test_id,
        "source_run": source_run,
        "strategy": strategy,
        "runner": runner,
        "base_params": base_params,
        "measured_on": measured_on,
    }
    # HOW to run it. The pool is python-only and that is not a limitation to lift later: NT8 and
    # MT5 each drive one physical terminal, so their shifts have nothing to run in parallel ON.
    if runner == "python" and plan:
        results = await _run_shifts_pooled(plan, ctx)
    else:
        results = await _run_shifts_serial(plan, ctx)

    if is_cancelled(stress_test_id):
        return (False, "cancelled")

    sensitivity: dict = {}
    max_degradation: Optional[float] = None
    failed_shifts: list[str] = []

    for res in results:
        entry = res["entry"]
        pname, shift_label = entry["param"], entry["label"]
        child_pf = res["pf"]
        pnl_delta = (res["pnl"] or 0.0) - baseline_pnl
        if not res["ok"]:
            failed_shifts.append(f"{pname} {shift_label}")

        # `degradation` is the SCORED field and the same key the grid path writes, so the chart
        # renders and labels both paths identically. None = this shift could not be measured (the
        # child failed, or a profit factor was missing/infinite) — never 0.0, which would claim the
        # parameter was tested and did nothing.
        #
        # `pf_delta_pct` is the SAME measurement with its SIGN kept. The score has to be a magnitude
        # — a shift that moves the result is evidence either way, and grading needs one number to
        # threshold — but a chart drawing a magnitude has to invent a direction, and the page drew
        # every one of them as a LOSS. Direction is data; it belongs here, not in a renderer.
        degradation = None
        pf_delta_pct = None
        if pf_usable and child_pf is not None and np.isfinite(child_pf):
            pf_delta_pct = (child_pf - baseline_pf) / baseline_pf * 100.0
            degradation = abs(child_pf - baseline_pf) / baseline_pf

        sensitivity.setdefault(pname, {})[shift_label] = {
            "run_id": res["run_id"],
            "new_value": entry["value"],
            "degradation": None if degradation is None else round(degradation, 4),
            "pf_delta_pct": None if pf_delta_pct is None else round(pf_delta_pct, 2),
            "profit_factor": child_pf,
            # Dollar effect, kept for reference only. NOT read by grading or the chart.
            "pnl_delta": round(pnl_delta, 2),
        }

        if degradation is not None:
            max_degradation = (
                degradation if max_degradation is None else max(max_degradation, degradation)
            )

    if skipped:
        log.info(
            "Sensitivity %s: skipped %d perturbation(s) that could test nothing: %s",
            stress_test_id,
            len(skipped),
            ", ".join(skipped),
        )

    # What was NOT measured travels with what was. A page reporting "12 params tested" over a phase
    # that quietly refused 30 shifts is describing coverage that never happened — the same reason
    # the optimizer logs what its caps dropped.
    coverage = {
        "params_perturbed": len(sensitivity),
        "shifts_run": sum(len(v) for v in sensitivity.values()),
        "shifts_skipped": skipped,
        "shifts_failed": failed_shifts,
        "params_unreachable": unreachable,
    }
    lab_db.update_stress_test_sensitivity(
        stress_test_id,
        sensitivity,
        None if max_degradation is None else round(max_degradation, 4),
        coverage,
    )

    # Every shift that ran having failed is a FAILED phase. Some failing is reported, not fatal.
    if failed_shifts and not sensitivity:
        return (False, f"every sensitivity backtest failed ({len(failed_shifts)} shifts)")
    if failed_shifts:
        log.warning(
            "Sensitivity %s: %d shift backtest(s) failed (%s)",
            stress_test_id,
            len(failed_shifts),
            ", ".join(failed_shifts),
        )
    return (True, None)


# ── Grid sensitivity injection (Step 3A) ──────────────────────────────────────


async def _apply_grid_sensitivity_if_available(st: dict, stress_test_id: str) -> bool:
    """
    If the source run came from a native optimization that already has grid sensitivity,
    populate the stress test's sensitivity fields from that data — no NT8 backtests.
    Returns True if sensitivity was applied.
    """
    run = lab_db.get_run(st["run_id"])
    if not run:
        return False
    opt_id = run.get("optimization_id")
    if not opt_id:
        return False
    opt = lab_db.get_optimization(opt_id)
    if not opt:
        return False
    score = opt.get("grid_sensitivity_score")
    summary_raw = opt.get("grid_sensitivity_summary")
    if score is None or summary_raw is None:
        return False

    try:
        import json as _json

        summary = _json.loads(summary_raw) if isinstance(summary_raw, str) else summary_raw
    except Exception:
        return False

    lab_db.update_stress_test_sensitivity(stress_test_id, summary, float(score))
    return True


# ── Telegram grade notification ───────────────────────────────────────────────


def _fire_grade_notification(
    stress_test_id: str, run: dict, st: dict, grade: Optional[str], reasons: list[str]
) -> None:
    strategy = lab_db.get_strategy(run.get("strategy_id", ""))
    strat_name = (
        (strategy.get("name") or strategy.get("class_name") or "Unknown") if strategy else "Unknown"
    )
    instrument = run.get("instrument", "?")
    prob_pass = st.get("prob_pass_eval")
    p1_dd = st.get("pct1_max_dd")

    # The house shape (`services/alert_format.py`): icon, LABEL, subject, grouped facts, then
    # the thing to act on. Plain text — a strategy name is full of underscores and Telegram drops
    # the whole message on an unbalanced Markdown entity.
    facts = [
        # `grade` is None when the ruleset states no drawdown limit, so nothing could be graded.
        # "not graded" is the honest word; "Grade: None" reads as a crash.
        f"Grade {grade}" if grade else "Not graded — the ruleset states no drawdown limit",
    ]
    if prob_pass is not None:
        facts.append(f"{round(prob_pass * 100, 1)}% pass probability")
    # Quote the drawdown in the unit the GRADE read. This always printed dollars, so on a
    # compounding run the message quoted a figure the letter beside it had not looked at.
    if st.get("dd_basis") == "percent" and st.get("pct1_max_dd_pct") is not None:
        facts.append(f"worst-1% drawdown {st['pct1_max_dd_pct']:.1f}%")
    elif p1_dd is not None:
        facts.append(f"worst-1% drawdown ${p1_dd:,.0f}")

    tail = []
    failures = st.get("phase_failures") or {}
    if failures:
        # A phase that RAN AND CRASHED leaves a NULL summary, which grading reads as "not run"
        # and does not penalise. Saying so is the difference between a caveat and a fiction.
        tail.append(
            "Phase failed: " + ", ".join(failures) + " — the grade does not account for it."
        )
    if reasons:
        tail.append("Why: " + "; ".join(reasons[:3]))

    notify.send_telegram(
        alert("🧪", "STRESS TEST", f"{strat_name} {instrument}", joined(facts), *tail),
        notify.HEALTH,
    )


# ── Main stress test background task ──────────────────────────────────────────


async def run_stress_test_task(
    stress_test_id: str,
    include_walk_forward: bool = False,
    include_sensitivity: bool = False,
) -> None:
    """Background coroutine: MC → (optionally WF → sensitivity) → grade."""
    from services.grading import compute_grade

    try:
        st = lab_db.get_stress_test(stress_test_id)
        if not st:
            return

        run = lab_db.get_run(st["run_id"])
        if not run:
            lab_db.update_stress_test_status(
                stress_test_id, "failed_no_run", "Source run not found"
            )
            return

        eq_path = run.get("equity_curve_path")
        if not eq_path or not Path(eq_path).exists():
            lab_db.update_stress_test_status(
                stress_test_id, "failed_no_data", "No equity curve data"
            )
            return

        equity_curve = json.loads(Path(eq_path).read_text())
        trade_pnls = [t["profit"] for t in equity_curve if t.get("profit") is not None]
        if not trade_pnls:
            lab_db.update_stress_test_status(
                stress_test_id, "failed_no_trades", "No trades in equity curve"
            )
            return

        # Balance BEFORE each trade, so the simulation can tell a compounding run from a fixed-size
        # one (see choose_shuffle_series). `equity` is the balance AFTER the trade on every runner's
        # curve, so the opening balance is equity - profit. Built in the same pass as the P&L list so
        # the two stay index-aligned; a curve missing `equity` yields None and the dollar model.
        balances: Optional[list[float]] = [
            t["equity"] - t["profit"]
            for t in equity_curve
            if t.get("profit") is not None and t.get("equity") is not None
        ]
        if len(balances) != len(trade_pnls):
            balances = None

        ruleset = lab_db.get_ruleset(st["ruleset_id"]) if st.get("ruleset_id") else None

        # ── Monte Carlo ──
        mc = await asyncio.to_thread(
            run_monte_carlo,
            trade_pnls,
            ruleset,
            st.get("num_simulations", 10_000),
            st.get("num_bootstrap", 1_000),
            100,
            balances,
        )
        log.info(
            "Stress test %s: Monte Carlo shuffled the %s series over %d trades",
            stress_test_id,
            mc.pop("shuffle_model", "dollars"),
            len(trade_pnls),
        )

        st_dir = _RESULTS_DIR / stress_test_id
        st_dir.mkdir(parents=True, exist_ok=True)
        paths_file = st_dir / "equity_paths.json"
        dist_file = st_dir / "distribution.json"
        paths_file.write_text(json.dumps(mc.pop("sampled_paths"), default=str))
        dist_file.write_text(json.dumps(mc.pop("distribution"), default=str))

        # ⚠ The row moves to the NEXT phase, never straight to `complete`. Marking it complete
        # here released the market lock mid-test and made a crash between phases invisible to
        # `reset_stale_stress_tests` — see lab_db.update_stress_test_mc.
        after_mc = (
            "running_wf"
            if include_walk_forward
            else ("running_sens" if include_sensitivity else "complete")
        )
        lab_db.update_stress_test_mc(
            stress_test_id,
            mc,
            {
                "equity_paths_path": str(paths_file),
                "distribution_path": str(dist_file),
            },
            next_status=after_mc,
        )

        # Already written at creation (see `phases_requested`); recomputed here only so the
        # end-of-run write carries both fields together.
        requested = phases_requested(include_walk_forward, include_sensitivity)
        phase_failures: dict[str, str] = {}

        # ── Step 3A: inject grid sensitivity if available (no NT8 backtests) ──
        grid_sens_applied = False
        if not include_sensitivity:
            grid_sens_applied = await _apply_grid_sensitivity_if_available(st, stress_test_id)

        # ── Walk-forward ──
        if include_walk_forward and not is_cancelled(stress_test_id):
            lab_db.update_stress_test_status(stress_test_id, "running_wf")
            ok, err = await run_walk_forward_task(stress_test_id)
            if not ok:
                phase_failures["walk_forward"] = err or "walk-forward failed"
                log.warning("Stress test %s: walk-forward failed — %s", stress_test_id, err)

        # ── Sensitivity (perturbation backtests) ──
        if include_sensitivity and not grid_sens_applied and not is_cancelled(stress_test_id):
            lab_db.update_stress_test_status(stress_test_id, "running_sens")
            ok, err = await run_sensitivity_task(stress_test_id)
            if not ok:
                phase_failures["sensitivity"] = err or "sensitivity failed"
                log.warning("Stress test %s: sensitivity failed — %s", stress_test_id, err)

        lab_db.update_stress_test_phases(stress_test_id, requested, phase_failures)

        # A cancelled test is NOT graded. Grading it would overwrite `failed_cancelled` with
        # `complete` and hand out a letter off half a test — which is exactly what the optimizer's
        # cancel did before 2026-08-04 (the finished job overwrote its own cancelled status).
        if is_cancelled(stress_test_id):
            log.info("Stress test %s was cancelled — not grading", stress_test_id)
            return

        # ── Grade ──
        st_updated = lab_db.get_stress_test(stress_test_id)
        if st_updated and ruleset:
            has_sens = include_sensitivity or grid_sens_applied
            grade, reasons = compute_grade(
                st_updated,
                st_updated.get("walk_forward_summary") if include_walk_forward else None,
                st_updated.get("sensitivity_summary") if has_sens else None,
                ruleset,
                wf_failed="walk_forward" in phase_failures,
                sens_failed="sensitivity" in phase_failures,
            )
            lab_db.update_stress_test_grade(stress_test_id, grade, reasons)
            _fire_grade_notification(stress_test_id, run, st_updated, grade, reasons)
        else:
            # No ruleset means no letter is possible, which is not a failure — but a phase that
            # died still has to be visible, so it goes in the row's own error field rather than
            # being lost with the reasons a grade would have carried.
            lab_db.update_stress_test_status(
                stress_test_id,
                "complete",
                "; ".join(f"{k}: {v}" for k, v in phase_failures.items()) or None,
            )

    except Exception as exc:
        lab_db.update_stress_test_status(stress_test_id, "failed_error", str(exc))
        log.exception("Stress test %s failed", stress_test_id)


# ── Auto-trigger (called by backtest_runner and optimization_runner) ───────────


async def trigger_auto_stress_test(run_id: str, ruleset_ids: list[str]) -> None:
    """MC-only auto-trigger after Tier 1 backtest or optimizer winner."""
    # Sample-size floor — Tier 1 only requires >= 50 trades, so this also skips the auto Monte
    # Carlo for Tier 1 runs with 50-99 trades, where its tail percentiles aren't trustworthy.
    run = lab_db.get_run(run_id) or {}
    if (run.get("trade_count") or 0) < MIN_TRADES_FOR_STRESS:
        log.info(
            "Auto stress test skipped for %s: only %s trades (< %d)",
            run_id,
            run.get("trade_count"),
            MIN_TRADES_FOR_STRESS,
        )
        return

    primary_ruleset_id = None
    if ruleset_ids:
        candidates = [lab_db.get_ruleset(rid) for rid in ruleset_ids]
        candidates = [r for r in candidates if r]
        if candidates:
            # Personal/demo rows carry max_loss_eod = 0 (sentinel) and must not win the
            # strictest pick. Prefer prop rows; fall back to personal only when the run
            # was evaluated against personal rulesets alone.
            prop = [r for r in candidates if r.get("ruleset_type") not in ("personal", "demo")]
            pool = prop or candidates
            primary = min(pool, key=lambda r: r.get("max_loss_eod") or float("inf"))
            primary_ruleset_id = primary["id"]

    st_id = uuid.uuid4().hex[:16]
    lab_db.insert_stress_test(
        {
            "stress_test_id": st_id,
            "run_id": run_id,
            "ruleset_id": primary_ruleset_id,
            "status": "running",
            "created_at": int(time.time()),
        }
    )
    # Fire and forget (no walk-forward for auto-triggers — MC only). The reference is HELD:
    # `asyncio.create_task` alone does not keep one, so a long-awaiting task is collectable and can
    # disappear mid-flight, leaving the row `running` for ever.
    task = asyncio.create_task(run_stress_test_task(st_id, False, False))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
