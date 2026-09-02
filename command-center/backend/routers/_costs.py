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
"""

from __future__ import annotations

from fastapi import HTTPException
from services import python_runner

__all__ = ["resolve_costs"]


def resolve_costs(
    *,
    runner: str,
    charge_costs: bool | None,
    broker_profile: str | None,
    cost_layers: list[str] | None,
    commission_per_side: float,
    slippage_ticks: int | None,
) -> tuple[list[str] | None, float]:
    """`(cost_layers, commission_per_side)` as they must be STORED on the row.

    Raises `HTTPException(400)` for a broker whose spread or swap has never been measured —
    refusing is the answer, because the alternative is charging a sibling tier's number and PU
    Prime's tiers measured 2.7x apart.
    """
    if runner != "python" or charge_costs is None:
        return cost_layers, commission_per_side
    try:
        resolved = list(python_runner.charged_layers(broker_profile)) if charge_costs else []
    except python_runner.UnpricedBrokerError as exc:
        raise HTTPException(400, str(exc))
    if charge_costs and int(slippage_ticks or 0) > 0:
        resolved = [*resolved, "slippage"]
    return resolved, python_runner.measured_commission(broker_profile)
