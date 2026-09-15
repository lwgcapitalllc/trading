"""Cloning a real bot into a fresh, unassigned copy — the one new write on the deploy path, and
the guard that has to cover it exactly like every other instance-config write.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from routers import bots

from tests.conftest import LiveVpsCall


def test_clone_is_refused_by_the_live_config_guard_by_default():
    """`_no_live_bot_config` is autouse and must cover this new write exactly like every
    existing one — a test that forgets to stub it must never be able to leave a real folder
    behind under `algos/markets/fx/instances/`."""
    with pytest.raises(LiveVpsCall):
        bots.clone_bot("sos_fade_demo")


def test_clone_of_an_unknown_bot_is_a_404_with_no_write_attempted():
    """The 404 has to land before the guarded write, or this path would need stubbing too."""
    with pytest.raises(HTTPException) as exc:
        bots.clone_bot("a_bot_that_does_not_exist")
    assert exc.value.status_code == 404


def test_clone_creates_a_fresh_benched_copy(tmp_path):
    """End to end against a throwaway instances root: cloning a real bot produces a real folder,
    benched, with a fresh key and magic, carrying the source's trading logic and none of its
    history."""
    source_folder = tmp_path / "pkg_demo"
    source_folder.mkdir()
    source_config = {
        "bot_key": "pkg_demo",
        "display_name": "PKG",
        "account": 111,
        "server": "S",
        "symbol": "XAUUSD.p",
        "magic": 770200,
        "strategy_package": "pkg",
        "strategy_params": {"exec_risk_pct": 3.0},
        "_measured": "a note that belongs to account 111 only",
    }
    (source_folder / "config.json").write_text(json.dumps(source_config))

    real_root = bots._INSTANCES_ROOT
    bots._INSTANCES_ROOT = tmp_path
    bots._REGISTRY_SIG = None
    try:
        bots._refresh_bots()
        assert "pkg_demo" in bots._BY_KEY

        def fake_write(bot_key, data):
            path = tmp_path / bot_key / "config.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))

        with patch("routers.bots._write_instance_config", side_effect=fake_write):
            result = bots.clone_bot("pkg_demo")
            bots._REGISTRY_SIG = None
            bots._refresh_bots()

        assert result.bot_key == "pkg_1"
        assert result.display_name == "PKG"
        assert "pkg_1" in bots._BY_KEY

        on_disk = json.loads((tmp_path / "pkg_1" / "config.json").read_text())
        assert on_disk["account"] is None
        assert on_disk["strategy_params"] == {"exec_risk_pct": 3.0}
        assert on_disk["magic"] != 770200
        assert "_measured" not in on_disk
        assert "pkg_demo" in on_disk["_cloned_from"]
    finally:
        bots._INSTANCES_ROOT = real_root
        bots._REGISTRY_SIG = None
        bots._refresh_bots()

    # The real fleet is back — proof the throwaway root left nothing behind on this one.
    assert "pkg_demo" not in bots._BY_KEY
    assert "sos_fade_demo" in bots._BY_KEY


def test_clone_can_be_called_by_display_name_too():
    """`_resolve_bot` accepts a key or a display name everywhere else in this router; the clone
    route goes through the same resolver rather than assuming a raw key. B-LEG's is the one
    display name on the real fleet naming just one bot — every other name is shared by a live
    and a demo copy and `_resolve_bot` refuses those (409), which is a different thing to prove."""
    with pytest.raises(LiveVpsCall):
        # Refused by the write guard, same as the key form — proves resolution happened first.
        bots.clone_bot("B-LEG")
