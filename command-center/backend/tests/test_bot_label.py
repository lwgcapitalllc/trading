"""A message from this app says which ACCOUNT KIND a bot is on — `SOS Fade · LIVE`.

**Why (2026-09-11).** The demo copies of the two live bots were named "SOS Fade (demo)" and
"Extreme Leg (demo)" for a day, so a Telegram message could tell them apart. Aaron: *"it's a
generic strategy, not a demo specific strategy."* The names are the strategy alone now, and a
message that names only "SOS Fade" would not say whether real money moved — so `_bot_label` adds
LIVE or demo off the account the bot's config names, the same rule the bots' own messages follow
on the box (`algos/shared/bot_state.labelled`).

Pinned here: the registry answers (never the hardcoded `account_type`), a benched or unclassifiable
bot keeps its plain name, nothing on this path can raise inside an announcement, and the start /
stop / restart / promote / settings / move messages actually use it.
"""

from __future__ import annotations

import pytest
from routers import bots

_LIVE, _DEMO = 34957946, 700152905


@pytest.fixture
def world(monkeypatch):
    """Two copies of one strategy — one per account kind — against a stubbed config and registry,
    so nothing here moves when a real bot does."""
    configs = {"sos_fade_demo": {"account": _LIVE}, "sos_fade_2": {"account": _DEMO}}

    def read(key):
        if key not in configs:
            raise bots.HTTPException(status_code=404, detail="no config")
        return configs[key]

    monkeypatch.setattr(bots, "_read_instance_config", read)
    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live", _DEMO: "demo"})
    monkeypatch.setattr(
        bots, "_KEY_DISPLAY", {"sos_fade_demo": "SOS Fade", "sos_fade_2": "SOS Fade"}
    )
    return configs


def test_the_label_says_LIVE_or_demo_off_the_account(world):
    assert bots._bot_label("sos_fade_demo") == "SOS Fade · LIVE"
    assert bots._bot_label("sos_fade_2") == "SOS Fade · demo"


def test_a_BENCHED_bot_keeps_the_plain_name_never_the_hardcoded_kind(world):
    """A bot on no account has no account to derive a kind from, and the registry's hardcoded
    `account_type` is a guess — tagging it "demo" would be a claim nothing measured."""
    world["sos_fade_2"] = {"account": None}
    assert bots._bot_label("sos_fade_2") == "SOS Fade"


def test_an_UNREGISTERED_account_keeps_the_plain_name(world):
    world["sos_fade_2"] = {"account": 111}
    assert bots._bot_label("sos_fade_2") == "SOS Fade"


def test_an_unreadable_config_or_registry_costs_the_tag_never_the_message(world, monkeypatch):
    assert bots._bot_label("no_such_bot") == "no_such_bot"

    def boom():
        raise RuntimeError("registry unreadable")

    monkeypatch.setattr(bots, "_registered_kinds", boom)
    assert bots._bot_label("sos_fade_demo") == "SOS Fade"


class _Sent(list):
    """The texts, plus WHICH bot each one said it was about (`routed`) — the half that decides
    which account's health channel it lands in (2026-09-13)."""

    def __init__(self):
        super().__init__()
        self.routed: list = []


@pytest.fixture
def sent(world, monkeypatch):
    out = _Sent()

    def _record(text, **kw):
        out.append(text)
        out.routed.append(kw.get("bot_key"))

    monkeypatch.setattr(bots, "_notify_telegram", _record)
    monkeypatch.setattr(bots, "_launch_bot", lambda key: "")
    monkeypatch.setattr(bots, "_kill_bot", lambda key: "")
    monkeypatch.setattr(bots, "_suppress_stop_alert", lambda key: None)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    return out


@pytest.mark.parametrize(
    "route,head",
    [
        (bots.start_bot, "▶️ STARTING · SOS Fade · LIVE"),
        (bots.stop_bot, "⏹ STOPPED · SOS Fade · LIVE"),
        (bots.restart_bot, "🔄 RESTARTING · SOS Fade · LIVE"),
    ],
)
def test_a_one_bot_action_announces_which_KIND_of_account_it_touched(sent, route, head):
    """MUTATION: put `_KEY_DISPLAY.get(...)` back in these routes -> red. Pressing Stop on the live
    bot and on its demo copy must not read the same in the health room."""
    route("sos_fade_demo")
    assert sent[-1].splitlines()[0] == head


@pytest.mark.parametrize("route", [bots.start_bot, bots.stop_bot, bots.restart_bot])
def test_a_one_bot_action_is_ROUTED_to_that_bots_account(sent, route):
    """🔴 Each account may name its own health channel (2026-09-13), and a stop pressed on the
    brother's live bot belongs in his room, not Aaron's. MUTATION: drop `bot_key=bot_key` from the
    route's `_notify_telegram` call -> red."""
    route("sos_fade_demo")
    assert sent.routed[-1] == "sos_fade_demo"


def test_the_demo_copy_is_announced_as_demo(sent):
    bots.stop_bot("sos_fade_2")
    assert sent[-1].splitlines()[0] == "⏹ STOPPED · SOS Fade · demo"
