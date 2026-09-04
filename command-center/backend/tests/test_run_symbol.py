"""The BROKER decides how an instrument is spelled, and the run records the resolved name.

Reported from the screen 2026-08-26: a run asked for `XAUUSD` against the PU Prime ECN profile,
and PU Prime quotes gold as `XAUUSD.p`. The symptom was `MT5 agent returned no bars ... across 4
chunk(s)` raised four layers down in the bar loader, naming the window and the timeframe and
never the one field that was wrong. Every python strategy here suggests a bare name — correctly,
because a strategy does not belong to a broker — so the mismatch was one dropdown away at all
times.

**WATCHED RED against HEAD — 13 of these 14 failed, and the reasons below were READ OFF THE RUN,
never reasoned about.** (Method: the five changed source files copied aside, `git checkout --`
back to HEAD, whole file run, then restored.)

  * 8 fail `AttributeError: module 'services.python_runner' has no attribute 'run_symbol'`
  * 3 fail `AttributeError: 'AccountProfile' object has no attribute 'symbol_suffix'`
  * 2 fail `KeyError: 'symbol_suffix'` — the endpoint served no such field
  * 1 fails `AssertionError: assert 'XAUUSD' == 'XAUUSD.p'` — the reported defect itself, caught
    at the stored row

⚠ **`test_the_rebase_is_the_LIVE_sides_and_not_a_second_copy` is the ONE that stays green on
HEAD, and that is the point of it** — it pins a helper that already existed and must not be
duplicated. It is a guard against a future second implementation, not a test of this change, and
it would be dishonest to count it among the ones that went red.
"""

import pytest
from services import python_runner

from backtest.fills import PROFILES

# ── the resolution itself ─────────────────────────────────────────────────────


def test_a_bare_name_takes_the_brokers_suffix():
    """The reported bug, in one line."""
    assert python_runner.run_symbol("XAUUSD", "puprime_ecn") == "XAUUSD.p"


def test_another_brokers_suffix_is_REPLACED_not_appended():
    """A rerun carries the symbol it was made on. Appending would build `XAUUSD.s.p`, which no
    terminal quotes — so the base is what travels and the suffix is what the broker supplies."""
    assert python_runner.run_symbol("XAUUSD.s", "puprime_ecn") == "XAUUSD.p"


def test_a_broker_that_quotes_bare_names_STRIPS_a_suffix():
    """Vantage's `""` is a measurement, not an absence: it quotes bare names, so a PU Prime
    symbol arriving here must lose its suffix rather than keep it."""
    assert python_runner.run_symbol("XAUUSD.p", "vantage_demo") == "XAUUSD"


def test_resolving_twice_changes_nothing():
    """Idempotence is what makes it safe to resolve at creation AND to re-resolve on a rerun."""
    once = python_runner.run_symbol("XAUUSD", "puprime_ecn")
    assert python_runner.run_symbol(once, "puprime_ecn") == once


def test_a_broker_whose_naming_NOBODY_RECORDED_leaves_the_symbol_alone():
    """🔴 Rule 1, and the reason `symbol_suffix` is three-state. Nobody here has logged into the
    Cent tier, so its naming is UNRECORDED — which must not take the same value as "quotes bare
    names". Rebasing on a guess would hand the terminal a symbol nobody has ever seen it quote,
    and the failure would look identical to the bug this whole change fixes."""
    assert PROFILES["puprime_cent"].symbol_suffix is None
    assert python_runner.run_symbol("XAUUSD.p", "puprime_cent") == "XAUUSD.p"


@pytest.mark.parametrize("broker", [None, "", "no_such_broker"])
def test_an_unknown_or_absent_broker_leaves_the_symbol_alone(broker):
    """Every pre-2026-08-02 row states no broker profile. Those must keep replaying exactly the
    symbol they were made on — inventing one here would rewrite history."""
    assert python_runner.run_symbol("XAUUSD", broker) == "XAUUSD"


# ── the registry the resolution reads ─────────────────────────────────────────


def test_every_profile_states_its_symbol_naming_or_admits_it_has_not():
    """Three states and no fourth: a real suffix, `""` for a broker measured to quote bare names,
    or None for one nobody has logged into. A stray value (`"p"` with no dot, whitespace) would
    resolve confidently to a symbol that does not exist."""
    for key, p in PROFILES.items():
        assert p.symbol_suffix is None or isinstance(p.symbol_suffix, str), key
        if p.symbol_suffix:
            assert p.symbol_suffix.startswith("."), f"{key}: {p.symbol_suffix!r}"
            assert p.symbol_suffix.strip() == p.symbol_suffix, key


def test_the_two_puprime_raw_tiers_agree_with_the_live_bot():
    """MEASURED 2026-08-08 across three logins, and re-confirmed on the ECN terminal 2026-08-26.
    The live bot trades `XAUUSD.p` on 700152905; if this table ever disagreed with that, the lab
    would be replaying a different symbol from the one being traded."""
    assert PROFILES["puprime_ecn"].symbol_suffix == ".p"
    assert PROFILES["puprime_prime"].symbol_suffix == ".p"
    assert PROFILES["puprime_standard"].symbol_suffix == ".s"


def test_the_rebase_is_the_LIVE_sides_and_not_a_second_copy():
    """Never build a second implementation. The live side has rebased a bot's symbol onto its
    account since 2026-08-12; the lab reuses that exact function, so the two cannot drift into
    disagreeing about what gold is called."""
    from services.bot_account_registry import rebase_symbol

    assert rebase_symbol("XAUUSD", ".p") == "XAUUSD.p"
    assert rebase_symbol("XAUUSD", None) is None


# ── which terminal the page can NAME ──────────────────────────────────────────
#
# Recording a login is not decoration: `_is_attached` falls back to "both sides blank" when either
# side has no account, so a profile with no login can never be confirmed as the attached one. With
# Standard and Prime blank, pointing the lab at either reported "cannot tell which terminal is
# connected" about a terminal it could name exactly — and that notice is the only thing standing
# between a reader and a run charged on the wrong tier.
#
# **WATCHED RED by mutation** (both `account=` lines deleted from `PROFILES`, whole file run):
# `test_every_tier_we_have_LOGGED_INTO_records_its_login` and the Standard and Prime cases of
# `test_the_page_names_the_attached_tier_on_a_SHARED_server` fail; the ECN case stays green
# because its login was already recorded. ⚠ The other two below are GUARDS, not tests of this
# change — they are green either way on purpose, and counting them as red would be a lie.


def test_every_tier_we_have_LOGGED_INTO_records_its_login():
    """MEASURED 2026-08-08: MT5_Lab was signed into all three PU Prime demos in turn to read their
    swaps and symbols. A tier we have the numbers for must carry the login they came from."""
    assert PROFILES["puprime_standard"].account == 700119432
    assert PROFILES["puprime_prime"].account == 700152904
    assert PROFILES["puprime_ecn"].account == 700152905


def test_the_tier_NOBODY_has_logged_into_still_records_nothing():
    """⚠ The counterpart, and it is the field working rather than an omission. Inventing a login
    for Cent would let it claim to be the attached terminal on a server it shares with three
    others — the 2.7x spread error arriving through the front door."""
    assert PROFILES["puprime_cent"].account is None


@pytest.mark.parametrize(
    ("account", "expected"),
    [(700119432, "puprime_standard"), (700152904, "puprime_prime"), (700152905, "puprime_ecn")],
)
def test_the_page_names_the_attached_tier_on_a_SHARED_server(
    client, monkeypatch, account, expected
):
    """🔴 All three logins live on `PUPrime-Demo`, so the SERVER cannot separate them — only the
    account can. Exactly one profile may come back attached, and it must be the right one."""
    from services import mt5_agent_client

    monkeypatch.setattr(
        mt5_agent_client,
        "status",
        lambda: {"mt5_connected": True, "server": "PUPrime-Demo", "account": account},
    )
    rows = client.get("/backtests/broker-profiles").json()
    assert [r["id"] for r in rows if r["attached"]] == [expected]


def test_a_login_nobody_recorded_leaves_the_page_saying_it_CANNOT_TELL(client, monkeypatch):
    """Attached to a PU Prime login none of these profiles claims: nothing may report attached.
    A blank is "cannot tell", never "matches anything" — guessing here would bless a tier."""
    from services import mt5_agent_client

    monkeypatch.setattr(
        mt5_agent_client,
        "status",
        lambda: {"mt5_connected": True, "server": "PUPrime-Demo", "account": 999999999},
    )
    rows = client.get("/backtests/broker-profiles").json()
    assert [r["id"] for r in rows if r["attached"]] == []


# ── what reaches the page and the row ─────────────────────────────────────────


def test_the_profiles_endpoint_serves_the_naming_it_resolves_by(client, monkeypatch):
    """The Run modal has to be able to show the resolved symbol BEFORE the run starts. It reads
    the same field the resolver reads, so the page and the runner cannot state different symbols
    — the failure this lab has already hit three times with numbers.

    ⚠ The agent is stubbed rather than left to `_no_live_vps`, because that guard raises a
    BaseException on purpose and this endpoint's `attached` probe catches `Exception`."""
    from services import mt5_agent_client

    monkeypatch.setattr(
        mt5_agent_client,
        "status",
        lambda: {"mt5_connected": True, "server": "PUPrime-Demo", "account": 700152905},
    )
    rows = {r["id"]: r for r in client.get("/backtests/broker-profiles").json()}
    assert rows["puprime_ecn"]["symbol_suffix"] == ".p"
    assert rows["vantage_demo"]["symbol_suffix"] == ""
    assert rows["puprime_cent"]["symbol_suffix"] is None


def test_the_naming_is_served_even_with_the_tunnel_DOWN(client, monkeypatch):
    """A broker's symbol naming is a RECORDED fact, not a live read, so it must survive an
    unreachable agent. If it did not, the page would fall back to showing the typed name at
    exactly the moment nobody can check it against a terminal."""
    from services import mt5_agent_client

    def _down():
        raise RuntimeError("tunnel down")

    monkeypatch.setattr(mt5_agent_client, "status", _down)
    rows = {r["id"]: r for r in client.get("/backtests/broker-profiles").json()}
    assert rows["puprime_ecn"]["symbol_suffix"] == ".p"
    assert rows["puprime_ecn"]["attached"] is False, "cannot ask must never read as attached"


def test_the_stored_run_records_the_RESOLVED_symbol(client):
    """🔴 Rule 3: never record what you REQUESTED as what you RECEIVED. The row is what the detail
    page, a rerun, the re-price endpoint and every comparison read back — so a row storing the
    typed name while the runner replayed another symbol is a row nothing can audit."""
    client.post("/strategies/scan")
    strat = next(
        s for s in client.get("/strategies").json() if s["class_name"] == "SosFadeStrategy"
    )

    r = client.post(
        "/backtests/run",
        json={
            "strategy_id": strat["id"],
            "instrument": "XAUUSD",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "evaluate_firms": [],
            "broker_profile": "puprime_ecn",
        },
    )
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]

    detail = client.get(f"/backtests/runs/{run_id}").json()
    assert detail["instrument"] == "XAUUSD.p"
