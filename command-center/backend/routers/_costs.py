"""What a run is CHARGED, resolved once for every endpoint that creates one.

🔴 **This exists because the alternative is a copy.** The block it replaces lived in
`routers/backtests.py` and the stack path needed the identical thing — and this app has already
shipped the same defect three times by copying a measurement basis instead of sharing it (the
tuning workbench, the stress-test children, the stack rerun each carried a parent's PARAMS and
not its costs, then put the two side by side). A second copy of this policy would drift the same
way, and the symptom is a comparison table where the cost gap reads as the feature under test.

The rules it enforces, each of which fails silently if it moves:

* **Resolved at CREATION, never inside a runner** — rule 3. The stored `cost_layers` is what the
  detail page, the re-price endpoint, the stress tester and every retry read back, so it has to
  be the resolved set rather than the request's intent.
* **PYTHON-ONLY.** NT8 and MT5 have no layer contract and must keep storing `None`; writing `[]`
  for them announces a deliberately frictionless run over a tester that really charged.
* **`None` means the caller has no opinion** and leaves what it was given alone — which is what a
  retry of a row written before this switch existed must do. A retry reproduces the run it is
  retrying, not today's default.
* **Commission comes off the ACCOUNT, not the form** — a measured fact per tier, so the row
  records the figure that was billed rather than one somebody typed beside three measurements.
* **Slippage stays OPT-IN inside "costs on"** — it is the one cost nobody has measured, so it is
  added only when a tick count was actually stated, which is somebody saying the guess out loud.
* **The SPREAD'S MODEL bends to what the strategies can run; the spread itself never goes away.**
  See below.

🔴 **THE SPREAD HAS TWO MODELS AND "COSTS ON" USED TO ASSUME ONE OF THEM (fixed 2026-09-02).**
Moving the fill (buys at the ask, sells at the bid) and charging a flat round-trip fee are
ALTERNATIVE models of one cost, never layers — bill both and the spread is paid twice. `costs ON`
resolves to the moved-fill model, which is the better one: it is the only layer that can change
WHICH setups fill. But a strategy that implements only the flat model refuses a moved-fill profile
at construction, so for such a strategy **`costs ON` was not a worse measurement, it was NO
measurement** — the job died seconds in with a stack trace while the page's switch said costs were
being charged. That is this repo's rule 1 arriving in a new place: *cannot be run* and *ran with
costs* must never be reachable from the same switch, and here the second was simply unavailable.

So when any strategy in the run declares it cannot move fills, the spread is charged FLAT instead.
⚠ **The same three costs are still billed** — the switch means what it says and no run silently
goes cheaper. ⚠ **A whole STACK falls back together if ONE leg cannot**, because legs sharing one
account measured on two different fill models is not a portfolio, it is two experiments added up.
⚠ **The stored layers record which model was used**, so a comparison across the two refuses on
basis rather than reading the gap as the strategy's doing — that is the property that makes this
safe, and it is why the fallback swaps the layer rather than quietly leaving `bid_ask_fills` on
the row. ⚠ **It is NOT a free pass**: the flat model cannot change which setups fill, so such a
strategy's charged trade LIST is still its gross trade list. Say that out loud when comparing it
to one that moves fills.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from fastapi import HTTPException
from services import python_runner

__all__ = ["resolve_costs"]


def _spread_model_for(strategies: Sequence[Mapping[str, Any]] | None) -> str:
    """`"bid_ask_fills"` unless some strategy here can only price the spread flat.

    ⚠ Reads the declaration, never a strategy id — the next package that prices the spread flat
    inherits this by declaring it, with no change here. That is the same call `_source_guard`
    makes and for the same reason.
    ⚠ `None` (no strategies passed) keeps the moved-fill model: a caller with no opinion must not
    silently downgrade what a run is measured on.
    """
    for strat in strategies or ():
        if not strat.get("supports_bid_ask_fills", True):
            return "spread"
    return "bid_ask_fills"


def resolve_costs(
    *,
    runner: str,
    charge_costs: bool | None,
    broker_profile: str | None,
    cost_layers: list[str] | None,
    commission_per_side: float,
    slippage_ticks: int | None,
    strategies: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[list[str] | None, float]:
    """`(cost_layers, commission_per_side)` as they must be STORED on the row.

    Raises `HTTPException(400)` for a broker whose spread or swap has never been measured —
    refusing is the answer, because the alternative is charging a sibling tier's number and PU
    Prime's tiers measured 2.7x apart.

    `strategies` is every strategy this run will execute — one for a solo run, every leg for a
    stack. It decides only which of the spread's two models is charged; see the module docstring.
    """
    if runner != "python" or charge_costs is None:
        return cost_layers, commission_per_side
    try:
        resolved = list(python_runner.charged_layers(broker_profile)) if charge_costs else []
    except python_runner.UnpricedBrokerError as exc:
        raise HTTPException(400, str(exc))
    # The spread's MODEL, swapped in place so the row records which one was actually charged.
    # ⚠ A swap, never an addition: the two never stack, and appending would bill the spread twice.
    model = _spread_model_for(strategies)
    if model != "bid_ask_fills":
        resolved = [model if layer == "bid_ask_fills" else layer for layer in resolved]
    if charge_costs and int(slippage_ticks or 0) > 0:
        resolved = [*resolved, "slippage"]
    return resolved, python_runner.measured_commission(broker_profile)
