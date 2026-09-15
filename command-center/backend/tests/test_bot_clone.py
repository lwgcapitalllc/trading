"""A fresh copy of an existing bot: trading logic carried, account and history reset."""

from __future__ import annotations

from services import bot_clone as bc


def _source():
    return {
        "bot_key": "sos_fade_demo",
        "display_name": "SOS Fade",
        "account": 34957946,
        "mt5_path": r"C:\MT5_Aaron\terminal64.exe",
        "server": "PUPrime-Live",
        "symbol": "XAUUSD.p",
        "magic": 770115,
        "strategy_package": "sos_fade",
        "strategy_params": {"exec_risk_pct": 5.0},
        "strategy_source_hash": "abc123",
        "promoted_commit": "5c53b0d",
        "promoted_at": "2026-07-31",
        "strategy_version": 7,
        "telegram_chat_id": "-100999",
        "telegram_token_key": "aaron_bot",
        "account_risk_cap_pct": 10.0,
        "sizing_basis_adjustment": -4518.23,
        "initial_capital": 2000,
        "warmup_bars": 5000,
        "timeframe": "M15",
        "_measured": "five days of ticks on account 34957946",
    }


# ── next_key: a rising number, never a hand-picked suffix ─────────────────────────────────────
def test_next_key_skips_taken_suffixes():
    assert bc.next_key({"sos_fade_demo", "sos_fade_2"}, "sos_fade") == "sos_fade_1"
    assert bc.next_key({"sos_fade_1", "sos_fade_2"}, "sos_fade") == "sos_fade_3"


def test_next_key_starts_at_one_for_a_brand_new_strategy():
    assert bc.next_key(set(), "new_strategy") == "new_strategy_1"


# ── next_magic: the smallest free order tag, checked globally ─────────────────────────────────
def test_next_magic_starts_at_the_floor_when_nothing_is_used():
    assert bc.next_magic(set()) == bc._MAGIC_FLOOR


def test_next_magic_finds_the_smallest_free_number():
    used = {bc._MAGIC_FLOOR, bc._MAGIC_FLOOR + 1, 770115, 770125}
    assert bc.next_magic(used) == bc._MAGIC_FLOOR + 2


def test_next_magic_ignores_a_zero_or_missing_magic():
    assert bc.next_magic({0, None}) == bc._MAGIC_FLOOR


# ── clone_config: strategy logic carried, account and history reset ───────────────────────────
def test_clone_carries_the_trading_logic_settings():
    cloned = bc.clone_config(_source(), "sos_fade_3", 770130, "2026-09-14")
    assert cloned["strategy_package"] == "sos_fade"
    assert cloned["display_name"] == "SOS Fade"
    assert cloned["symbol"] == "XAUUSD.p"
    assert cloned["timeframe"] == "M15"
    assert cloned["warmup_bars"] == 5000
    assert cloned["strategy_params"] == {"exec_risk_pct": 5.0}


def test_clone_resets_every_account_and_deployment_fact():
    cloned = bc.clone_config(_source(), "sos_fade_3", 770130, "2026-09-14")
    assert cloned["bot_key"] == "sos_fade_3"
    assert cloned["magic"] == 770130
    assert cloned["account"] is None
    assert cloned["mt5_path"] == ""
    assert cloned["server"] == ""
    assert cloned["strategy_source_hash"] == ""
    assert cloned["promoted_commit"] == ""
    assert cloned["promoted_at"] == ""
    assert cloned["strategy_version"] == 0
    assert cloned["telegram_chat_id"] == ""
    assert cloned["telegram_token_key"] == ""
    assert cloned["account_risk_cap_pct"] is None
    assert cloned["sizing_basis_adjustment"] == 0.0
    assert cloned["initial_capital"] == 0


def test_clone_drops_every_prose_key_and_writes_one_new_note():
    source = _source()
    cloned = bc.clone_config(source, "sos_fade_3", 770130, "2026-09-14")
    prose_kept = [k for k in cloned if k.startswith("_") and k != "_cloned_from"]
    assert prose_kept == []
    assert "sos_fade_demo" in cloned["_cloned_from"]
    assert "2026-09-14" in cloned["_cloned_from"]
    # The source's own account-specific measurement never survives onto the clone's note.
    assert "34957946" not in cloned["_cloned_from"]


def test_clone_carries_a_field_it_has_never_seen():
    """A strategy setting added after this module was written is copied by default — the failure
    direction that matters is a field silently dropped, not one carried forward."""
    source = _source()
    source["some_future_strategy_setting"] = "a value nobody has told this function about"
    cloned = bc.clone_config(source, "sos_fade_3", 770130, "2026-09-14")
    assert cloned["some_future_strategy_setting"] == "a value nobody has told this function about"


def test_clone_does_not_mutate_the_source():
    source = _source()
    cloned = bc.clone_config(source, "sos_fade_3", 770130, "2026-09-14")
    cloned["strategy_params"]["exec_risk_pct"] = 999.0
    assert source["strategy_params"]["exec_risk_pct"] == 5.0
