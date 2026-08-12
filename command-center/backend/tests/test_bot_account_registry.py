"""The registry of broker accounts a bot can be put ON.

🔴 **Written because grouping bots by account could only ever see accounts a bot was ALREADY on.**
That derivation is right and must stay — two bots naming one account are sharing a balance whether
or not anybody grouped them — but it left the first bot on a NEW account unmovable from the page,
and `set_bot_account` said so out loud: *"no registered bot trades account N, so there is no
account here to join."* The 2026-08-12 move onto the PU Prime ECN demo was a hand-edited config on
the VPS for exactly that reason.

⚠ **A fail-watch against HEAD is vacuous for all of these — the module did not exist.** Every
non-vacuity claim below is by MUTATION, and each docstring names the mutation and the behaviour it
turns red.

The two rules worth reading before editing anything here:

  * **The registry states what an ACCOUNT is; the bots state what they are doing on it.** There is
    no risk cap in a registry row, deliberately, because the cap is stored per instance and the
    bots are what read it — a copy here would be a second answer that can drift from them.
  * **A fact the registry does not carry is REPORTED, never guessed.** An account with no recorded
    symbol suffix leaves the bot's symbol alone and says so, because guessing produces a bot that
    connects, warms up and receives no bars — indistinguishable from a quiet market.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import bot_account_registry as reg  # noqa: E402
from services import bot_accounts as ba           # noqa: E402

_PROFILES = {"puprime_ecn", "puprime_standard", "vantage_demo"}


def _acct(**kw):
    base = dict(account=700152905, label="PU Prime ECN demo", broker="PU Prime", tier="ECN",
                kind="demo", server="PUPrime-Demo", mt5_path=r"C:\MT5_FFT\terminal64.exe",
                symbol_suffix=".p", account_profile="puprime_ecn")
    base.update(kw)
    return reg.RegisteredAccount(**base)


def _file(tmp_path, rows=()):
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"_README": "prose", "accounts": list(rows)}), encoding="utf-8")
    return p


# ── reading ───────────────────────────────────────────────────────────────────
def test_a_missing_registry_is_EMPTY_and_an_unreadable_one_RAISES(tmp_path):
    """MUTATION: return `{"accounts": []}` on a parse failure → this goes red.

    They are opposite states and collapsing them is destructive rather than merely wrong: every
    write is a read-modify-write of the WHOLE file, so answering "empty" for a file that exists
    and could not be parsed drops every account in it and reports success. Same shape as the
    `users.json` read that could delete every Telegram user (2026-08-04).
    """
    assert reg.load_accounts(tmp_path / "nothing.json") == []

    broken = tmp_path / "accounts.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="could not be parsed"):
        reg.load_accounts(broken)


def test_a_file_that_is_not_a_registry_is_refused_rather_than_overwritten(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(reg.RegistryError, match="not an account registry"):
        reg.upsert_account(p, _acct(), _PROFILES)


def test_an_unknown_field_on_a_stored_row_is_dropped_rather_than_raising(tmp_path):
    """A registry written by a newer version of this app must not stop an older one LISTING
    accounts. The write path is strict, so nothing can be introduced from the page unchecked."""
    p = _file(tmp_path, [{"account": 1, "server": "S", "something_new": True}])
    assert [a.account for a in reg.load_accounts(p)] == [1]


# ── writing ───────────────────────────────────────────────────────────────────
def test_upsert_REPLACES_the_row_so_a_cleared_field_is_cleared(tmp_path):
    """MUTATION: merge into the existing row instead of replacing → red.

    A merge makes removing a symbol suffix inexpressible from the page: the absent value and the
    unchanged value become the same request.
    """
    p = _file(tmp_path)
    reg.upsert_account(p, _acct(), _PROFILES)
    reg.upsert_account(p, _acct(symbol_suffix=None, tier=""), _PROFILES)
    stored = reg.account_by_number(p, 700152905)
    assert stored.symbol_suffix is None and stored.tier == ""
    assert len(reg.load_accounts(p)) == 1


def test_a_hand_written_prose_key_on_a_row_SURVIVES_a_write_from_the_page(tmp_path):
    """MUTATION: drop the prose carry-over → red. The page cannot express these keys, so a write
    from it must not delete an explanation somebody left for the next reader."""
    p = _file(tmp_path, [{"account": 700152905, "server": "PUPrime-Demo",
                          "_why": "measured on 2026-08-10"}])
    reg.upsert_account(p, _acct(), _PROFILES)
    row = json.loads(p.read_text())["accounts"][0]
    assert row["_why"] == "measured on 2026-08-10"
    assert row["account_profile"] == "puprime_ecn"


def test_removing_an_account_that_is_not_there_answers_False(tmp_path):
    p = _file(tmp_path, [{"account": 1, "server": "S"}])
    assert reg.remove_account(p, 2) is False
    assert reg.remove_account(p, 1) is True
    assert reg.load_accounts(p) == []


# ── validation ────────────────────────────────────────────────────────────────
def test_an_account_with_no_server_is_refused(tmp_path):
    """An account number IS a login on a server and the pair is the identity. Half of it is a
    connection failure at startup with a message about credentials."""
    with pytest.raises(reg.RegistryError, match="needs a server"):
        reg.upsert_account(_file(tmp_path), _acct(server=""), _PROFILES)


def test_a_kind_outside_demo_and_live_is_refused(tmp_path):
    """The page tints a live account and warns before every fleet action on one, so an
    unrecognised value drops both silently."""
    with pytest.raises(reg.RegistryError, match="demo"):
        reg.upsert_account(_file(tmp_path), _acct(kind="Demo"), _PROFILES)


def test_an_unmeasured_cost_profile_is_refused(tmp_path):
    """MUTATION: skip the profile check → red. A name nothing can price is a backtest that
    refuses and a live config claiming a broker it cannot name."""
    with pytest.raises(reg.RegistryError, match="not a measured cost profile"):
        reg.upsert_account(_file(tmp_path), _acct(account_profile="puprime_eecn"), _PROFILES)


def test_the_profile_check_is_SKIPPED_when_the_roster_could_not_be_loaded(tmp_path):
    """`None` is the caller saying it could not supply the roster, which is a different thing
    from an empty roster — an empty set would refuse every profile name there is."""
    stored, created = reg.upsert_account(_file(tmp_path), _acct(account_profile="anything"), None)
    assert created and stored.account_profile == "anything"


# ── assignability ─────────────────────────────────────────────────────────────
def test_an_account_with_no_terminal_is_NOT_assignable(tmp_path):
    """MUTATION: make `assignable` always True → the refusal below goes red.

    A bot connects by attaching to a running terminal already logged into the account it claims to
    trade. Without one the move is written, committed, pushed and pulled, and then fails at
    `connect()` with a message about CREDENTIALS — pointing the reader at the password rather than
    at the missing terminal. It is a real state: the two tier-probe accounts were logged into
    MT5_Lab for minutes to read a spread, and MT5_Lab drives the backtest agent.
    """
    a = _acct(mt5_path="")
    assert a.assignable is False
    assert "no terminal" in a.unassignable_reason
    with pytest.raises(ValueError, match="no terminal"):
        ba.assign_plan("bot", 700152905, registered=a, current_symbol="XAUUSD.s")


# ── the symbol is REBASED, and that is the field 2026-08-12 forgot ────────────
def test_the_symbol_is_rebased_onto_the_accounts_suffix():
    """🔴 MUTATION: drop `symbol` from the plan → red, and this is the defect that made the ECN
    move manual. PU Prime quotes gold as `XAUUSD.s` on Standard and `XAUUSD.p` on Prime and ECN,
    so writing the login and leaving the symbol produces a bot pointed at a symbol its terminal
    does not quote. NOTHING ERRORS: it connects, warms up and receives no bars."""
    plan = ba.assign_plan("bot", 700152905, registered=_acct(), current_symbol="XAUUSD.s")
    assert plan.fields["symbol"] == "XAUUSD.p"
    assert plan.param_fields["symbol"] == "XAUUSD.p"
    assert plan.param_fields["account_profile"] == "puprime_ecn"
    assert plan.fields["mt5_path"] == r"C:\MT5_FFT\terminal64.exe"


def test_the_INSTRUMENT_is_the_bots_and_only_the_SUFFIX_is_the_accounts():
    """MUTATION: copy a peer's whole symbol instead of rebasing → red.

    Two bots on one account can legitimately trade gold and a currency pair. Copying whichever
    symbol happened to be there would rewrite one onto the other's market — a bot that starts
    cleanly, connects cleanly and trades the wrong instrument.
    """
    plan = ba.assign_plan("bot", 700152905, registered=_acct(), current_symbol="EURUSD.s")
    assert plan.fields["symbol"] == "EURUSD.p"


def test_a_broker_that_quotes_BARE_symbols_strips_the_suffix():
    """`""` and `None` are different answers: empty means this broker uses bare names."""
    assert reg.rebase_symbol("XAUUSD.s", "") == "XAUUSD"
    assert reg.rebase_symbol("XAUUSD.s", None) is None


def test_an_account_with_NO_recorded_suffix_leaves_the_symbol_alone_and_SAYS_SO():
    """MUTATION: fall back to stripping the suffix when none is recorded → red.

    Unrecorded is not "no suffix". Guessing here is the silent failure the rebase exists to
    prevent, so the plan carries a note and the endpoint returns it.
    """
    plan = ba.assign_plan("bot", 700152905, registered=_acct(symbol_suffix=None),
                          current_symbol="XAUUSD.s")
    assert "symbol" not in plan.fields
    assert any("no symbol suffix" in n for n in plan.notes)


def test_a_symbol_that_already_matches_is_not_rewritten():
    """A no-op write still produces a commit, a push and a VPS pull."""
    plan = ba.assign_plan("bot", 700152905, registered=_acct(), current_symbol="XAUUSD.p")
    assert "symbol" not in plan.fields


# ── the cap still comes from the BOTS, never from the registry ────────────────
def test_the_first_bot_on_an_account_lands_UNCAPPED_and_is_told_so():
    """MUTATION: carry the bot's existing cap onto the new account → red.

    The bot's own value describes the account it is LEAVING, so carrying it states a ceiling for
    this account that nobody set. Uncapped is the honest state of a one-bot account, and the note
    is what stops it being a surprise when a second bot joins.
    """
    plan = ba.assign_plan("bot", 700152905, registered=_acct(), current_symbol="XAUUSD.s")
    assert plan.fields["account_risk_cap_pct"] is None
    assert any("UNCAPPED" in n for n in plan.notes)


def test_joining_an_account_that_HAS_bots_still_adopts_THEIR_cap():
    """The registry holds no cap and must not — this is the half that proves it still comes from
    the instance configs, which are what a bot actually reads."""
    cfgs = {"a": {"bot_key": "a", "account": 700152905, "server": "PUPrime-Demo",
                  "symbol": "XAUUSD.p", "magic": 1, "strategy_package": "p",
                  "account_risk_cap_pct": 10.0, "strategy_params": {"exec_risk_pct": 10.0}}}
    target = ba.group_by_account(cfgs)[0]
    plan = ba.assign_plan("bot", 700152905, target=target, registered=_acct(),
                          current_symbol="XAUUSD.s")
    assert plan.fields["account_risk_cap_pct"] == 10.0


def test_an_unregistered_account_that_a_bot_trades_still_works_and_says_what_is_missing():
    """Backwards compatibility, and the note is the point: the move happens, and the reader is
    told the symbol and the cost profile could not be carried."""
    cfgs = {"a": {"bot_key": "a", "account": 700107749, "server": "PUPrime-Demo",
                  "symbol": "XAUUSD.s", "magic": 1, "strategy_package": "p",
                  "account_risk_cap_pct": None, "strategy_params": {"exec_risk_pct": 10.0}}}
    target = ba.group_by_account(cfgs)[0]
    plan = ba.assign_plan("bot", 700107749, target=target, current_symbol="XAUUSD.p")
    assert plan.fields["server"] == "PUPrime-Demo"
    assert plan.adopt_terminal_from == "a"
    assert any("not in the account registry" in n for n in plan.notes)


def test_an_account_nothing_knows_about_is_refused_outright():
    with pytest.raises(ValueError, match="neither registered nor traded"):
        ba.assign_plan("bot", 424242, current_symbol="XAUUSD.s")


# ── the API ───────────────────────────────────────────────────────────────────
@pytest.fixture
def registry(tmp_path, monkeypatch):
    from routers import bots as bots_router
    p = _file(tmp_path)
    monkeypatch.setattr(bots_router, "_registry_path", lambda: p)
    return p


def test_the_registry_endpoint_lists_accounts_without_a_password_anywhere(
        client, registry, monkeypatch):
    """🔴 There is NO endpoint that returns a password and there must not be one. The page needs
    one bit — will this move be able to connect — and that bit is answerable without the secret
    leaving the box."""
    from routers import bots as bots_router
    reg.upsert_account(registry, _acct(), _PROFILES)
    monkeypatch.setattr(bots_router, "_accounts_with_a_password", lambda: {700152905})

    r = client.get("/bots/accounts/registry")
    assert r.status_code == 200
    body = r.json()
    assert [a["account"] for a in body] == [700152905]
    assert body[0]["has_password"] is True
    assert body[0]["assignable"] is True
    assert "password" not in json.dumps(body).lower().replace("has_password", "")


def test_an_unreachable_VPS_leaves_has_password_UNKNOWN_rather_than_FALSE(
        client, registry, monkeypatch):
    """MUTATION: return `set()` instead of `None` when the box cannot be asked → red.

    Rendering an unanswered question as "no password" sends the reader to re-enter one that is
    already there, and refuses a move that would have worked. The repo's oldest rule: never let
    "no" and "cannot ask" be the same value.
    """
    from routers import bots as bots_router
    reg.upsert_account(registry, _acct(), _PROFILES)
    monkeypatch.setattr(bots_router, "_accounts_with_a_password", lambda: None)

    body = client.get("/bots/accounts/registry").json()
    assert body[0]["has_password"] is None


def test_registering_an_account_writes_it_and_does_not_need_the_vps(
        client, registry, monkeypatch):
    from routers import bots as bots_router
    monkeypatch.setattr(bots_router, "_accounts_with_a_password", lambda: set())

    r = client.put("/bots/accounts/registry/700152905", json={
        "account": 700152905, "label": "ECN", "server": "PUPrime-Demo",
        "mt5_path": r"C:\MT5_FFT\terminal64.exe", "symbol_suffix": ".p",
        "account_profile": "puprime_ecn", "deploy": False})
    assert r.status_code == 200, r.text
    assert reg.account_by_number(registry, 700152905).symbol_suffix == ".p"


def test_a_body_naming_a_different_account_from_the_path_is_a_400(client, registry):
    r = client.put("/bots/accounts/registry/700152905",
                   json={"account": 999, "server": "S", "deploy": False})
    assert r.status_code == 400


def test_unregistering_an_account_a_bot_still_trades_is_REFUSED(client, registry, monkeypatch):
    """MUTATION: drop the in-use check → red. The bot would go on trading an account this page
    can no longer describe, and it would then be filed under one with no server, no terminal and
    no symbol suffix."""
    from routers import bots as bots_router
    reg.upsert_account(registry, _acct(account=700152905), _PROFILES)

    group = ba.AccountGroup(account=700152905, server="PUPrime-Demo", kind="account",
                            bots=[ba.AccountBot(key="mpc_sos_fade_demo", display="A",
                                                symbol="XAUUSD.p", magic=1,
                                                strategy_package="p")])
    monkeypatch.setattr(bots_router, "_account_groups", lambda: [group])

    r = client.delete("/bots/accounts/registry/700152905")
    assert r.status_code == 409
    assert "mpc_sos_fade_demo" in r.json()["detail"]
    assert reg.account_by_number(registry, 700152905) is not None


def test_a_password_for_an_unregistered_account_is_a_404(client, registry):
    """A credential for an account nothing knows about can be neither checked nor used."""
    r = client.put("/bots/accounts/registry/424242/password", json={"password": "x"})
    assert r.status_code == 404


def test_moving_a_bot_to_an_account_with_no_stored_password_is_REFUSED(
        client, registry, monkeypatch):
    """MUTATION: drop the password pre-check → the move is written, committed, pushed and pulled,
    and fails at the next start. That discovery loop is what this page exists to remove.

    ⚠ It refuses on a DEFINITE no. The test above pins the other half: `None` means the box could
    not be asked and must not refuse anything.
    """
    from routers import bots as bots_router
    reg.upsert_account(registry, _acct(), _PROFILES)
    monkeypatch.setattr(bots_router, "_bot_is_running", lambda key: False)
    monkeypatch.setattr(bots_router, "_accounts_with_a_password", lambda: set())

    r = client.patch("/bots/mpc_bleg_demo/account",
                     json={"account": 700152905, "deploy": False})
    assert r.status_code == 409
    assert "password" in r.json()["detail"].lower()
