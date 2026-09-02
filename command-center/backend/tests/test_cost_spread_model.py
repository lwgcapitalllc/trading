"""The SPREAD has two models, and "costs ON" must pick one the strategies can actually run.

Moving the fill and charging a flat round-trip fee are ALTERNATIVE models of one cost, never
layers. `charged_layers` resolves to the moved-fill model because it is the better one — it is the
only layer that can change WHICH setups fill. A strategy that implements only the flat model
refuses a moved-fill profile at construction, so before 2026-09-02 turning costs ON for such a
strategy was not a worse measurement, it was NO measurement: the job died seconds in with a stack
trace while the page's switch said costs were being charged.

Every case here was watched RED by mutation; each names its own in its docstring.
"""

from routers import _costs


def _flat():
    """A strategy row that can only price the spread as a flat charge."""
    return {"id": "mpc_extreme_leg", "supports_bid_ask_fills": False}


def _moves():
    return {"id": "mpc_sos_fade", "supports_bid_ask_fills": True}


def _resolve(strategies, charge=True, slippage=0):
    return _costs.resolve_costs(
        runner="python",
        charge_costs=charge,
        broker_profile="puprime_ecn",
        cost_layers=None,
        commission_per_side=0.0,
        slippage_ticks=slippage,
        strategies=strategies,
    )[0]


def test_a_strategy_that_cannot_move_fills_is_charged_the_FLAT_spread_instead():
    """RED by dropping the swap in `resolve_costs` — the strategy then refuses the profile at
    construction and the run dies mid-job under a switch that says costs are on."""
    layers = _resolve([_flat()])
    assert "spread" in layers
    assert "bid_ask_fills" not in layers


def test_the_spread_is_SWAPPED_never_ADDED_so_it_is_not_billed_twice():
    """RED by appending the flat layer instead of replacing — the two never stack, and a book that
    pays the spread inside its fills AND again as a fee is a number no account can produce."""
    layers = _resolve([_flat()])
    assert not ("spread" in layers and "bid_ask_fills" in layers)


def test_the_OTHER_costs_are_untouched_so_the_switch_still_means_what_it_says():
    """RED by returning only the spread layer. The fallback changes the spread's MODEL; it must
    never quietly make a charged run cheaper."""
    flat = _resolve([_flat()])
    moved = _resolve([_moves()])
    assert set(flat) - {"spread"} == set(moved) - {"bid_ask_fills"}
    assert "commission" in flat and "swap" in flat


def test_an_ordinary_strategy_still_gets_the_moved_fill_model():
    """RED by returning the flat layer unconditionally — that downgrades every charged run in the
    lab to a model that cannot change which setups fill, and nothing on any page would say so."""
    assert "bid_ask_fills" in _resolve([_moves()])


def test_a_caller_with_NO_opinion_is_not_silently_downgraded():
    """RED by treating an empty/None strategy list as "cannot move fills". A caller that passes
    nothing has stated nothing, and guessing the weaker model changes what a run is measured on."""
    assert "bid_ask_fills" in _resolve(None)
    assert "bid_ask_fills" in _resolve([])


def test_an_UNDECLARED_strategy_counts_as_able_to_move_fills():
    """RED by defaulting a missing key to False. Every package but one declares nothing, and they
    all model moved fills — the absent key must mean the majority answer, not the exception."""
    assert "bid_ask_fills" in _resolve([{"id": "whatever"}])


def test_a_whole_STACK_falls_back_together_when_ONE_leg_cannot():
    """RED by testing only the first leg. Legs sharing one account measured under two different
    fill models is not a portfolio, it is two experiments added up."""
    layers = _resolve([_moves(), _flat(), _moves()])
    assert "spread" in layers
    assert "bid_ask_fills" not in layers


def test_costs_OFF_is_still_nothing_charged_whatever_the_strategy_declares():
    """RED by appending the flat layer instead of replacing it — that appends unconditionally,
    so a run that asked to be charged NOTHING comes back paying a spread. The swap form cannot,
    because it maps over a list that is empty when costs are off."""
    assert _resolve([_flat()], charge=False) == []


def test_a_stated_slippage_guess_still_rides_along_on_the_flat_model():
    """RED by returning early once the spread is swapped, which would drop the one cost somebody
    typed out loud."""
    assert "slippage" in _resolve([_flat()], slippage=2)
