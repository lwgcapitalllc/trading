"""`GET /backtests/runs/{id}/repriced` — switching costs on for a run that already happened.

The arithmetic is proven against a real replay in `backtest/tests/test_reprice.py`; what is tested
here is the SEAM. Three things about it would each mislead silently if broken: recovering the
starting balance from the curve, reporting a layer that cannot be re-priced instead of dropping it,
and captioning a figure that is accurate rather than exact.
"""

import json
import time

import pytest


def _curve(tmp_path, rows):
    p = tmp_path / "equity_curve.json"
    p.write_text(json.dumps(rows))
    return str(p)


def _point(
    i,
    *,
    equity,
    profit,
    entry=2000.0,
    stop=1990.0,
    size=10.0,
    legacy=False,
    entry_ms=1_700_000_000_000,
    exit_ms=1_700_003_600_000,
):
    row = {
        "index": i,
        "equity": equity,
        "profit": profit,
        "entry_price": entry,
        "stop_price": stop,
        "size": size,
        "direction": "Long",
        "legs": [],
        "entry_ms": entry_ms,
        "exit_ms": exit_ms,
    }
    if not legacy:
        risk = abs(entry - stop) * size
        row.update({"r": profit / risk, "risk_usd": risk})
    return row


@pytest.fixture
def priced_run(fresh_db, tmp_path):
    """A completed python run with a two-trade curve starting from $10,000."""
    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "s1",
            "name": "S",
            "class_name": "S",
            "runner": "python",
            "source_path": "strategies/python/s/__init__.py",
            "scanned_at": int(time.time()),
            "default_params": {},
            "param_schema": [],
        }
    )
    run_id = "repriceabc123"
    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": "s1",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "status": "running",
            "created_at": int(time.time()),
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "cost_layers": [],
            "broker_profile": "vantage_demo",
        }
    )
    rows = [_point(1, equity=11_000.0, profit=1_000.0), _point(2, equity=10_500.0, profit=-500.0)]
    lab_db.update_run_complete(
        run_id, {"net_pnl": 500.0, "trade_count": 2}, {"equity_curve": _curve(tmp_path, rows)}
    )
    return run_id


def test_no_layers_returns_the_run_exactly_as_stored(client, priced_run):
    """The page's OFF state must reproduce the run it is showing, or the toggle would change the
    numbers just by existing."""
    r = client.get(f"/backtests/runs/{priced_run}/repriced")
    assert r.status_code == 200
    body = r.json()
    assert body["layers"] == [] and body["total_cost_usd"] == 0.0
    assert body["final_equity"] == pytest.approx(10_500.0)
    assert body["is_exact"] is True


def test_the_starting_balance_is_recovered_from_the_curve_not_assumed(client, priced_run):
    """There is no deposit column, and defaulting to $10k would rescale every dollar on the page
    for any run that started somewhere else while leaving R correct — the hardest kind of wrong to
    notice. `equity` is cumulative and anchored on it, so the first point states it exactly."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced").json()
    assert body["initial_capital"] == pytest.approx(10_000.0)


def test_charging_the_spread_moves_the_money_but_not_the_trade_count(client, priced_run):
    """A flat charge re-prices trades; it never adds or removes one. The R it takes off is
    `spread / stop-distance` per trade — $0.22 over a $10 stop = 0.022R each — which is the
    size-independent identity the whole re-pricer rests on, arriving here through the API."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced?layers=spread").json()
    assert len(body["trades"]) == 2
    assert body["total_cost_usd"] > 0
    assert body["final_equity"] < 10_500.0
    # Stored R is +10.0 then -5.0 (a $1,000 win and a $500 loss on $100 of risk).
    assert body["sum_r"] == pytest.approx(5.0 - 2 * (0.22 / 10.0))


def test_every_layer_is_priced_even_with_none_ticked(client, priced_run):
    """The pill shows what turning a layer on would COST before you turn it on — the same
    discipline the news filter's rows follow. The first build had no per-layer figure at all and
    every row read '0 trades', a hardcoded placeholder that looked like real data."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced").json()
    assert body["layers"] == []
    assert set(body["layer_cost_r"]) == {"spread", "commission", "swap"}
    assert body["layer_cost_r"]["spread"] > 0


def test_the_per_layer_prices_sum_to_the_total(client, priced_run):
    """They are in R precisely so they can. In dollars they could not — charging one layer changes
    the balance and so every later position's size — and rows that don't add up to the total under
    them read as a bug whether or not they are one."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced?layers=spread,commission,swap").json()
    assert sum(body["layer_cost_r"].values()) == pytest.approx(body["total_cost_r"])


def test_a_layer_this_broker_does_not_charge_prices_at_zero(client, priced_run):
    """Vantage demo charges no commission, and that is a FINDING rather than a missing number —
    the UI renders it as 'none on this account' instead of an ambiguous 0.00R."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced").json()
    assert body["layer_cost_r"]["commission"] == 0.0


def test_a_layer_that_cannot_be_repriced_is_REPORTED_not_dropped(client, priced_run):
    """`bid_ask_fills` changes which setups fill, so no arithmetic over a stored trade list can
    produce it. Silently ignoring it would show a spread-only number under a bid/ask label — the
    exact defect this whole area was rebuilt to end. A 400 would be wrong too: the question is
    reasonable and the honest answer is 'that one needs a re-run'."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced?layers=spread,bid_ask_fills").json()
    assert body["needs_rerun"] == ["bid_ask_fills"]
    assert body["layers"] == ["spread"]


def test_slippage_also_needs_a_rerun(client, priced_run):
    body = client.get(f"/backtests/runs/{priced_run}/repriced?layers=slippage").json()
    assert body["needs_rerun"] == ["slippage"] and body["layers"] == []


def test_swap_is_returned_but_flagged_as_not_exact(client, priced_run):
    """Its real charge depends on which BARS existed — holiday closures supersede a rollover and
    the curve records trades, never the bar stream. Measured at 0.03% of R on the reference run:
    worth showing, not worth claiming as exact."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced?layers=swap").json()
    assert body["layers"] == ["swap"]
    assert body["is_exact"] is False
    assert body["approximate_layers"] == ["swap"]


def test_a_run_predating_the_stored_r_is_flagged_as_derived(client, fresh_db, tmp_path):
    """Old runs re-price to ~0.02%, which is fine to show and not fine to present as exact."""
    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "s2",
            "name": "S",
            "class_name": "S",
            "runner": "python",
            "source_path": "x",
            "scanned_at": int(time.time()),
            "default_params": {},
            "param_schema": [],
        }
    )
    lab_db.insert_run(
        {
            "run_id": "legacyrun999",
            "strategy_id": "s2",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": int(time.time()),
        }
    )
    rows = [_point(1, equity=11_000.0, profit=1_000.0, legacy=True)]
    lab_db.update_run_complete(
        "legacyrun999",
        {"net_pnl": 1000.0, "trade_count": 1},
        {"equity_curve": _curve(tmp_path, rows)},
    )

    body = client.get("/backtests/runs/legacyrun999/repriced?layers=spread").json()
    assert body["derived_basis"] is True and body["is_exact"] is False


def test_the_broker_defaults_to_the_one_the_run_was_made_against(client, priced_run):
    """Re-pricing at a different broker's measured spread than the run used would compare two
    things that were never comparable — and the two profiles here differ by 50%."""
    body = client.get(f"/backtests/runs/{priced_run}/repriced?layers=spread").json()
    assert body["broker_profile"] == "vantage_demo"
    other = client.get(
        f"/backtests/runs/{priced_run}/repriced?layers=spread&broker=puprime_standard"
    ).json()
    assert other["broker_profile"] == "puprime_standard"
    assert other["total_cost_usd"] > body["total_cost_usd"]  # 0.33 vs 0.22


def test_an_unknown_broker_is_a_400(client, priced_run):
    r = client.get(f"/backtests/runs/{priced_run}/repriced?layers=spread&broker=nope")
    assert r.status_code == 400


def test_a_missing_run_is_a_404(client):
    assert client.get("/backtests/runs/nosuchrun/repriced").status_code == 404


def test_a_run_with_no_stored_curve_refuses_rather_than_returning_an_empty_book(client, seeded_run):
    """NT8/MT5 runs and any run whose curve file is gone. Returning an empty, zero-cost report
    would render as 'costs changed nothing', which is a claim about a run nobody measured."""
    r = client.get(f"/backtests/runs/{seeded_run}/repriced?layers=spread")
    assert r.status_code == 400 and "equity curve" in r.json()["detail"]


# ── a layer the RUN already charged ────────────────────────────────────────────────────────────
#
# The hazard here is silent and expensive: the stored trades were MEASURED with that cost baked in,
# so charging it again bills one cost twice and produces a plausible number rather than an error.
# Nothing downstream can catch it — the page would simply be wrong by a believable amount.


@pytest.fixture
def spread_charged_run(fresh_db, tmp_path):
    """The same run, but launched with `spread` already charged at replay time."""
    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "s2",
            "name": "S2",
            "class_name": "S2",
            "runner": "python",
            "source_path": "strategies/python/s2/__init__.py",
            "scanned_at": int(time.time()),
            "default_params": {},
            "param_schema": [],
        }
    )
    run_id = "alreadyspread01"
    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": "s2",
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "status": "running",
            "created_at": int(time.time()),
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "cost_layers": ["spread"],
            "broker_profile": "vantage_demo",
        }
    )
    # Held THREE DAYS, unlike the base fixture's one-hour trades: swap only charges on a rollover
    # crossed, so an intraday trade prices it at exactly 0.0 and could not tell "this layer was
    # refused" apart from "this layer costs nothing here".
    hold = 3 * 86_400_000
    rows = [
        _point(1, equity=11_000.0, profit=1_000.0, exit_ms=1_700_000_000_000 + hold),
        _point(2, equity=10_500.0, profit=-500.0, exit_ms=1_700_000_000_000 + hold),
    ]
    lab_db.update_run_complete(
        run_id, {"net_pnl": 500.0, "trade_count": 2}, {"equity_curve": _curve(tmp_path, rows)}
    )
    return run_id


def test_a_layer_the_run_already_charged_is_never_charged_twice(client, spread_charged_run):
    """Ticking `spread` on a run that already charged it must change NOTHING.

    Not "change a little" — the cost is in the stored trades, so the honest re-price of it is a
    no-op. Before this, the endpoint read the request and never the run, so it happily billed a
    second spread and moved every number on the page by a completely believable amount.
    """
    r = client.get(f"/backtests/runs/{spread_charged_run}/repriced?layers=spread")
    assert r.status_code == 200
    body = r.json()
    assert body["layers"] == [], "spread must not be re-applied on top of the run's own charge"
    assert body["total_cost_usd"] == 0.0 and body["total_cost_r"] == 0.0
    assert body["already_charged"] == ["spread"], "and it must SAY so rather than silently ignoring"


def test_an_already_charged_layer_is_reported_even_when_nothing_is_ticked(
    client, spread_charged_run
):
    """The UI renders those rows as already-on, so the field describes the RUN, not the request.
    Keyed off `wanted` it would be empty until the user ticked a row that then did nothing —
    a checkbox indistinguishable from a broken one."""
    body = client.get(f"/backtests/runs/{spread_charged_run}/repriced").json()
    assert body["already_charged"] == ["spread"]


def test_an_already_charged_layer_is_priced_at_zero_not_at_what_it_would_cost(
    client, spread_charged_run
):
    """`layer_cost_r` answers "what does turning this on cost from here", and the answer is nothing.
    Quoting its standalone price would invite exactly the double charge the endpoint refuses."""
    body = client.get(f"/backtests/runs/{spread_charged_run}/repriced").json()
    assert body["layer_cost_r"]["spread"] == 0.0
    assert body["layer_cost_r"]["swap"] != 0.0, "an un-charged layer still quotes its real price"


def test_a_layer_the_run_did_not_charge_still_prices_normally(client, spread_charged_run):
    """The refusal is per-LAYER. A run that charged the spread can still be re-priced for swap."""
    body = client.get(f"/backtests/runs/{spread_charged_run}/repriced?layers=spread,swap").json()
    assert body["layers"] == ["swap"]
    assert body["already_charged"] == ["spread"]
    assert body["total_cost_r"] != 0.0


def test_cost_layers_is_read_as_JSON_not_iterated_as_a_string(client, spread_charged_run):
    """`cost_layers` is stored as raw JSON TEXT. `set(row["cost_layers"])` iterates its CHARACTERS,
    so every real layer name fails to match while 's', 'p', 'r'… all appear to be charged — the
    refusal would silently stop working and the double charge would come straight back."""
    body = client.get(f"/backtests/runs/{spread_charged_run}/repriced?layers=swap").json()
    assert body["already_charged"] == ["spread"], "a character-set would not contain 'spread'"
    assert body["layers"] == ["swap"], "...and would have matched 's'/'w'/'a'/'p' against swap"
