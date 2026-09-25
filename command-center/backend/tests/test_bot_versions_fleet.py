"""The fleet version read (`GET /bots/versions`, 2026-09-24) — the Bots page rows' only source.

The rows asked `/bots/{bot}/version` once per bot; they now read every bot at once. The one
property that matters is that the two reads can NEVER disagree about a bot — the page writes each
fleet answer into the same cache entry the bot's panel reads. So this scripts one box, asks it
both ways, and requires the answers to be identical, bot for bot.

MUTATION: pass another bot's `ahead` into a build → red on the bot whose count moved.
MUTATION: leave a bot with no deployment record out of the fleet answer → red on the key set.
"""

import json
import re

import pytest
from routers import bots
from services import bot_versions

BASE = {
    "strategy_source_hash": "e42a95c96bb27b2868eee7b1e4f78e4c",
    "promoted_commit": "677e7ce",
    "promoted_at": "2026-08-04",
    "strategy_package": "sos_fade",
    "strategy_class": "SosFadeStrategy",
    "strategy_version": 0,
    "strategy_params": {"exec_risk_pct": 5.0},
    "files": 93,
}


@pytest.fixture
def box(monkeypatch):
    keys = [b.key for b in bots._BOTS]
    assert len(keys) >= 2, "needs at least two bot folders to tell them apart"
    # Each bot its own answer, so a mix-up between bots shows: a different commit count ahead,
    # a different running hash, and one bot with NO deployment record at all.
    deployed = {k: dict(BASE, files=90 + i) for i, k in enumerate(keys)}
    deployed[keys[-1]] = {}
    ahead = {k: str(i) for i, k in enumerate(keys)}
    running = {k: f"hash{i:08d}" for i, k in enumerate(keys)}

    def state_json(k):
        return json.dumps({k: {"source_hash": running[k]}})

    def _ssh(cmd: str) -> str:
        if "===DEPLOYED_" in cmd:  # the fleet read, first call
            out = "677e7ce"
            for k in keys:
                u = k.upper()
                out += f"\n===DEPLOYED_{u}===\n{json.dumps(deployed[k]) if deployed[k] else ''}"
                if f"===STATE_{u}===" in cmd:
                    out += f"\n===STATE_{u}===\n{state_json(k)}"
                if f"===STARTS_{u}===" in cmd:
                    out += f"\n===STARTS_{u}===\n"
            return out
        if "===AHEAD_" in cmd:  # the fleet read, second call
            return "".join(
                f"\n===AHEAD_{k.upper()}===\n{ahead[k]}"
                for k in keys
                if f"AHEAD_{k.upper()}" in cmd
            )
        m = re.search(r"\\([a-z0-9_]+)\\deployed\.json", cmd)
        if m:  # the one-bot read, first call
            return json.dumps(deployed[m.group(1)]) if deployed[m.group(1)] else ""
        k = re.search(r"\\([a-z0-9_]+)\\bot_state\.json", cmd).group(1)
        out = f"677e7ce\n===AHEAD===\n{ahead[k]}\n===STATE===\n{state_json(k)}"
        if "===STARTS===" in cmd:
            out += "\n===STARTS===\n"
        return out

    monkeypatch.setattr(bots, "_ssh", _ssh)
    monkeypatch.setattr(bots, "_read_instance_config", lambda k: {"strategy_params": {}})
    # The comparison against this repo is the same code either way; a fixed answer keeps the
    # test about the BOX half, which is the half the fleet read reassembles.
    monkeypatch.setattr(bot_versions, "compare", lambda *a: {"comparable": False, "reason": "x"})
    return keys


def test_every_bot_reads_the_same_in_the_fleet_as_on_its_own(box):
    fleet = bots.get_bot_versions()
    assert set(fleet) == set(box), "a bot the box answered for was left out"
    for k in box:
        assert fleet[k] == bots.get_bot_version(k), k


def test_the_fleet_read_costs_two_round_trips_whatever_the_fleet(box, monkeypatch):
    calls = []
    real = bots._ssh
    monkeypatch.setattr(bots, "_ssh", lambda cmd: calls.append(cmd) or real(cmd))
    bots.get_bot_versions()
    assert len(calls) == 2
