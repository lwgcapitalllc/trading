"""The trade ledger and the instance config.

The ledger is what makes "why did this trade not work" answerable months later, so the two
things it must never do are lose a record and crash the loop that writes it.

The instance config is what keeps a live bot isolated from lab experiments, so the thing IT
must never do is accept a key it will then ignore.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_LIVE = Path(__file__).resolve().parent.parent / "live"
sys.path.insert(0, str(_LIVE))
import live_config  # noqa: E402
from ledger import Ledger  # noqa: E402


# ── ledger ────────────────────────────────────────────────────────────────────
def _rows(directory: Path):
    return [
        json.loads(l) for f in sorted(directory.glob("*.jsonl")) for l in f.read_text().splitlines()
    ]


def test_every_record_carries_a_timestamp_bot_and_kind(tmp_path):
    Ledger(tmp_path, "botA").event("startup", version=3)
    row = _rows(tmp_path)[0]
    assert row["bot"] == "botA" and row["kind"] == "event" and row["event"] == "startup"
    assert row["ts"].endswith("+00:00") or "T" in row["ts"]


def test_records_append_in_order(tmp_path):
    led = Ledger(tmp_path, "botA")
    led.event("one")
    led.event("two")
    assert [r["event"] for r in _rows(tmp_path)] == ["one", "two"]


def test_the_file_is_named_by_day(tmp_path):
    """Rotation is by day so a closed file can never be appended to again — a commit racing a
    write is how a log ends up with a half line in it.

    Both streams rotate on the same boundary (see `test_ledger_streams.py`); this pins that the
    naming is per-day at all, from the side that reads the files back.
    """
    led = Ledger(tmp_path, "botA")
    led.event("x")  # health
    led.bar(SimpleNamespace(), SimpleNamespace(time_ms=1), SimpleNamespace())  # decisions
    assert len(list(tmp_path.glob("health-????-??-??.jsonl"))) == 1
    assert len(list(tmp_path.glob("decisions-????-??-??.jsonl"))) == 1


def test_a_write_failure_never_raises(tmp_path, monkeypatch):
    """A log that can take down the loop it observes is worse than a missing line."""
    led = Ledger(tmp_path, "botA")
    monkeypatch.setattr(Path, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    led.event("x")  # must not raise


def test_bar_records_read_a_decision_defensively(tmp_path):
    """The ledger must not know what an A+ stage IS. A strategy with a different Decision shape
    logs what it has rather than crashing the bot."""

    class _Bare:
        pass

    Ledger(tmp_path, "botA").bar(_Bare(), _Bare(), _Bare())
    row = _rows(tmp_path)[0]
    assert row["kind"] == "bar" and row["l_stage"] is None


def test_a_trade_record_keeps_both_the_intended_and_the_real_price(tmp_path):
    """The gap between them is the only honest measure of live execution quality, and it is
    invisible if only one is kept."""
    Ledger(tmp_path, "botA").trade_opened(
        ticket=1,
        direction="LONG",
        symbol="XAUUSD",
        lots=0.4,
        price=3289.7,
        stop=3280.0,
        intended_price=3290.0,
    )
    row = _rows(tmp_path)[0]
    assert row["price"] == 3289.7 and row["intended_price"] == 3290.0
    assert row["slippage"] == pytest.approx(-0.3)


def test_slippage_is_none_when_there_was_no_intended_price(tmp_path):
    """A market close has no resting price to compare against — reporting 0 slippage there
    would read as a perfect fill."""
    Ledger(tmp_path, "botA").trade_opened(
        ticket=1, direction="LONG", symbol="XAUUSD", lots=0.4, price=3289.7, stop=3280.0
    )
    assert _rows(tmp_path)[0]["slippage"] is None


# ── instance config ───────────────────────────────────────────────────────────
def _write_cfg(tmp_path, **overrides):
    body = {
        "bot_key": "b1",
        "mt5_path": "C:/MT5/terminal64.exe",
        "account": 123,
        "server": "Demo",
        "symbol": "XAUUSD",
        "magic": 770115,
    }
    body.update(overrides)
    d = tmp_path / "b1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(body))
    return body


def _write_sibling(tmp_path, key, **overrides):
    """A SECOND instance directory, so the per-account guards have something to compare against."""
    body = {
        "bot_key": key,
        "mt5_path": "C:/MT5/terminal64.exe",
        "account": 123,
        "server": "Demo",
        "symbol": "XAUUSD",
        "magic": 880226,
    }
    body.update(overrides)
    d = tmp_path / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(body))
    return body


# ── the account-level risk cap must mean ONE thing per account ────────────────
def test_two_bots_on_one_account_may_state_the_same_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2", account_risk_cap_pct=10.0)
    assert live_config.load("b1").account_risk_cap_pct == 10.0


def test_two_bots_on_one_account_may_both_be_uncapped(tmp_path, monkeypatch):
    """`null` everywhere is a coherent account: uncapped, honestly, which is what a one-bot
    account has always been."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path)
    _write_sibling(tmp_path, "b2")
    assert live_config.load("b1").account_risk_cap_pct is None


def test_two_different_caps_on_one_account_are_refused(tmp_path, monkeypatch):
    """Whichever bot asks decides the ceiling, so the account's real cap is the largest of them
    — the least protective, chosen by nothing."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2", account_risk_cap_pct=20.0)
    with pytest.raises(ValueError, match="disagreement"):
        live_config.load("b1")


def test_a_capped_bot_beside_an_uncapped_one_is_refused(tmp_path, monkeypatch):
    """The shape that would otherwise look fine and be the worst of the three: the uncapped bot
    fills the account freely while the capped one is refused, so the guard only handicaps the
    bot that was configured correctly."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2")  # no cap at all
    with pytest.raises(ValueError, match="no cap"):
        live_config.load("b1")


def test_the_refusal_names_both_bots_and_both_values(tmp_path, monkeypatch):
    """An account-wide refusal has to say which file to edit; 'they disagree' is not actionable
    when the fix is in a sibling directory nobody was looking at."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2", account_risk_cap_pct=20.0)
    with pytest.raises(ValueError) as e:
        live_config.load("b1")
    msg = str(e.value)
    assert "b1" in msg and "b2" in msg and "10.0%" in msg and "20.0%" in msg


# ── the BENCH: account is null, and both per-account guards must stand down ───
#
# Added 2026-08-09 so the command center can take a bot OFF an account. `None == None`, so
# without an exemption every one of these guards fires between two bots that are not trading.


def test_a_benched_bot_loads_with_no_account(tmp_path, monkeypatch):
    """`account: null` is a supported state, not a malformed file — it is what "remove this bot
    from the account" writes, and the bot has to be loadable so it can be promoted and read."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account=None)
    assert live_config.load("b1").account is None


def test_the_account_KEY_is_still_required(tmp_path, monkeypatch):
    """MUTATION: drop "account" from `load`'s required list -> red.

    Deliberately unassigned and somebody forgot the account are different mistakes with
    different fixes, and only the second should refuse to load."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    body = _write_cfg(tmp_path)
    del body["account"]
    (tmp_path / "b1" / "config.json").write_text(json.dumps(body))
    with pytest.raises(ValueError, match="missing required key"):
        live_config.load("b1")


def test_two_benched_bots_with_different_caps_both_load(tmp_path, monkeypatch):
    """MUTATION: remove `if account is None: return` from `_assert_account_cap_agrees` -> red.

    There is no budget for them to disagree about. Without the exemption a benched bot could be
    blocked from loading by ANOTHER benched bot's leftover cap — and worse, assigning it to a
    capped account would be refused by whichever unrelated benched sibling sorted first."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account=None, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2", account=None, account_risk_cap_pct=20.0)
    assert live_config.load("b1").account_risk_cap_pct == 10.0


def test_two_benched_bots_may_share_a_magic(tmp_path, monkeypatch):
    """MUTATION: remove `if account is None: return` from `_assert_magic_is_unique` -> red.

    The rule is about two bots reading one terminal's order book; a bot on no account reads
    nothing. It re-arms the moment either is assigned, which is when it matters."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account=None, magic=880226)
    _write_sibling(tmp_path, "b2", account=None, magic=880226)
    assert live_config.load("b1").magic == 880226


def test_a_benched_sibling_does_not_disturb_a_bot_that_IS_on_an_account(tmp_path, monkeypatch):
    """The live case this protects: benching one bot must not take the account's remaining bot
    off the box at its next restart."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2", account=None, account_risk_cap_pct=None, magic=880226)
    assert live_config.load("b1").account_risk_cap_pct == 10.0


def test_a_different_account_may_carry_a_different_cap(tmp_path, monkeypatch):
    """The ceiling is per ACCOUNT — the broker scopes exposure by login — so two accounts with
    two caps is the ordinary case, not a clash."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    _write_sibling(tmp_path, "b2", account=999, account_risk_cap_pct=20.0)
    assert live_config.load("b1").account_risk_cap_pct == 10.0


def test_an_unreadable_sibling_does_not_stop_a_healthy_bot(tmp_path, monkeypatch):
    """Same call as the magic guard: a half-written instance directory must not take a running
    account off the box. The cost is that a clash hiding inside a broken file is missed, and a
    broken file fails loudly on its own next start anyway."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, account_risk_cap_pct=10.0)
    d = tmp_path / "b2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text("{not json")
    assert live_config.load("b1").account_risk_cap_pct == 10.0


def test_a_missing_config_names_the_path_and_the_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    with pytest.raises(FileNotFoundError, match="instance.template.json"):
        live_config.load("nope")


def test_an_unknown_key_is_a_hard_error(tmp_path, monkeypatch):
    """A typo'd key is a setting that reads as applied and is not — on a live bot that is a
    parameter nobody chose. Loud beats convenient."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, risk_pct=2.0)  # not a LiveConfig field
    with pytest.raises(ValueError, match="risk_pct"):
        live_config.load("b1")


def test_a_missing_required_key_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    body = _write_cfg(tmp_path)
    body.pop("magic")
    (tmp_path / "b1" / "config.json").write_text(json.dumps(body))
    with pytest.raises(ValueError, match="magic"):
        live_config.load("b1")


def test_readme_keys_are_ignored(tmp_path, monkeypatch):
    """The template carries `_`-prefixed prose so the file explains itself on the VPS, where
    nobody has the repo docs open."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, _README="hello", _magic="what magic is for")
    assert live_config.load("b1").magic == 770115


def test_display_name_defaults_to_the_bot_key(tmp_path, monkeypatch):
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path)
    assert live_config.load("b1").display_name == "b1"


def test_the_shipped_template_loads(tmp_path, monkeypatch):
    """The template is the setup path — if it does not parse, the first thing anyone does with
    this package fails."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    (tmp_path / "b1").mkdir()
    template = json.loads((_LIVE / "instance.template.json").read_text())
    template["account"] = 123
    (tmp_path / "b1" / "config.json").write_text(json.dumps(template))
    cfg = live_config.load("b1")
    assert cfg.strategy_class == "SosFadeStrategy"
    assert cfg.timeframe == "M15"


# ── Telegram routing is PER BOT ─────────────────────────────────────────────────────────────
# Two bots can trade two accounts on two terminals; they must be able to report into two
# different places, as two different Telegram identities, or every deployment shares one feed.


def test_telegram_routing_defaults_to_the_shared_group(tmp_path, monkeypatch):
    """Empty means "use the shared default", so an existing single-bot setup needs no keys."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path)
    cfg = live_config.load("b1")
    assert cfg.telegram_chat_id == ""
    assert cfg.telegram_token_key == ""


def test_each_bot_can_name_its_own_chat_and_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, telegram_chat_id="-1009999", telegram_token_key="telegram_token_bleg")
    cfg = live_config.load("b1")
    assert cfg.telegram_chat_id == "-1009999"
    assert cfg.telegram_token_key == "telegram_token_bleg"


def test_an_instance_config_names_a_token_key_never_a_token(tmp_path, monkeypatch):
    """The instance config is an ordinary JSON file on the VPS — the one thing it must never
    hold is the secret itself. The field is a POINTER into the credentials file, so a leaked
    instance config leaks routing, not access."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    with pytest.raises(ValueError, match="telegram_token"):
        _write_cfg(tmp_path, telegram_token="123456:AAHsecretlookingvalue")
        live_config.load("b1")
