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

import pytest

_LIVE = Path(__file__).resolve().parent.parent / "live"
sys.path.insert(0, str(_LIVE))
import live_config  # noqa: E402
from ledger import Ledger  # noqa: E402


# ── ledger ────────────────────────────────────────────────────────────────────
def _rows(directory: Path):
    return [json.loads(l) for f in sorted(directory.glob("*.jsonl"))
            for l in f.read_text().splitlines()]


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
    """Rotation is by day so the backup job commits a file that can never be appended to again
    — a commit racing a write is how a log ends up with a half line in it."""
    Ledger(tmp_path, "botA").event("x")
    assert len(list(tmp_path.glob("decisions-????-??-??.jsonl"))) == 1


def test_a_write_failure_never_raises(tmp_path, monkeypatch):
    """A log that can take down the loop it observes is worse than a missing line."""
    led = Ledger(tmp_path, "botA")
    monkeypatch.setattr(Path, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    led.event("x")          # must not raise


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
        ticket=1, direction="LONG", symbol="XAUUSD", lots=0.4,
        price=3289.7, stop=3280.0, intended_price=3290.0)
    row = _rows(tmp_path)[0]
    assert row["price"] == 3289.7 and row["intended_price"] == 3290.0
    assert row["slippage"] == pytest.approx(-0.3)


def test_slippage_is_none_when_there_was_no_intended_price(tmp_path):
    """A market close has no resting price to compare against — reporting 0 slippage there
    would read as a perfect fill."""
    Ledger(tmp_path, "botA").trade_opened(
        ticket=1, direction="LONG", symbol="XAUUSD", lots=0.4, price=3289.7, stop=3280.0)
    assert _rows(tmp_path)[0]["slippage"] is None


# ── instance config ───────────────────────────────────────────────────────────
def _write_cfg(tmp_path, **overrides):
    body = {"bot_key": "b1", "mt5_path": "C:/MT5/terminal64.exe", "account": 123,
            "server": "Demo", "symbol": "XAUUSD", "magic": 770115}
    body.update(overrides)
    d = tmp_path / "b1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(body))
    return body


def test_a_missing_config_names_the_path_and_the_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    with pytest.raises(FileNotFoundError, match="instance.template.json"):
        live_config.load("nope")


def test_an_unknown_key_is_a_hard_error(tmp_path, monkeypatch):
    """A typo'd key is a setting that reads as applied and is not — on a live bot that is a
    parameter nobody chose. Loud beats convenient."""
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_cfg(tmp_path, risk_pct=2.0)          # not a LiveConfig field
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
    assert cfg.strategy_class == "MpcSosFadeStrategy"
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
