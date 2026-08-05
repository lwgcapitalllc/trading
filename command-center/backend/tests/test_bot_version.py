"""Which version a bot is ACTUALLY running.

Aaron's requirement, in his words: *"I wanna see the version of the bot that is running, so
I can know exactly what version, and you could know too, so we could look at configs or
parameters from that version so we're not confused."*

The card this endpoint feeds used to read the tracked `config.json`. That was fine while a
bot imported its code straight out of the repo — the file and the deployment were the same
thing. Since 2026-08-03 a bot runs a frozen snapshot, so the two are routinely different and
`config.json` describes what SHOULD be deployed, not what is.

**A version display that can be wrong is worse than none**, because it is the thing you check
before deciding anything. So the tests below are mostly about the three ways the truth can
disagree with itself — the snapshot edited in place, a promote that has not been restarted
into, and settings changed since deploy — and pin that each one is SURFACED rather than
quietly reconciled.
"""

import json

import pytest

from routers import bots


DEPLOYED = {
    "strategy_source_hash": "e42a95c96bb27b2868eee7b1e4f78e4c",
    "promoted_commit": "677e7ce",
    "promoted_at": "2026-08-04",
    "strategy_package": "mpc_sos_fade",
    "strategy_class": "MpcSosFadeStrategy",
    "strategy_version": 0,
    "strategy_params": {"exec_risk_pct": 10.0, "exec_sl_level": "0.886"},
    "files": 93,
}


@pytest.fixture
def vps(monkeypatch):
    """Script the VPS: the deployment record, the git facts, and the live process's report."""
    state = {
        "deployed": dict(DEPLOYED),
        "head": "677e7ce",
        "ahead": "0",
        "show": "  on disk  : e42a95c9 matches",
        "running_hash": "e42a95c96bb2",
        "config_params": dict(DEPLOYED["strategy_params"]),
    }

    def _ssh(cmd: str) -> str:
        state.setdefault("cmds", []).append(cmd)
        if "deployed.json" in cmd:
            return json.dumps(state["deployed"]) if state["deployed"] else ""
        # One command carries every remaining fact, `bot_state.json` included — see
        # test_the_running_hash_costs_no_extra_round_trip below. The state section is
        # answered only when the command actually asked for it, so a bot with no registered
        # state file gets what the real VPS would give it: nothing.
        out = (f"{state['head']}\n===AHEAD===\n{state['ahead']}\n"
               f"===SHOW===\n{state['show']}")
        if "bot_state.json" in cmd:
            live = json.dumps({"mpc_sos_fade_demo": {"source_hash": state["running_hash"]}})
            out += f"\n===STATE===\n{live}"
        return out

    monkeypatch.setattr(bots, "_ssh", _ssh)

    def _no_snapshot():
        raise AssertionError(
            "/version fetched the whole fleet snapshot again — two SSH commands returning "
            "every process, every scheduled task and every bot's state, to read one string"
        )

    monkeypatch.setattr(bots, "_fetch_vps_snapshot", _no_snapshot)
    monkeypatch.setattr(bots, "_read_instance_config",
                        lambda k: {"strategy_params": state["config_params"]})
    return state


def test_it_reports_the_deployed_version_not_the_config_file(vps):
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.frozen is True
    assert v.hash == DEPLOYED["strategy_source_hash"]
    assert v.commit == "677e7ce"
    assert v.promoted_at == "2026-08-04"
    assert v.files == 93


def test_the_params_are_the_ones_that_version_was_deployed_with(vps):
    """The reason the record keeps a copy at all. `config.json` is edited between promotes —
    the runtime panel writes `exec_risk_pct` to it on a running bot — so it cannot answer
    "what settings is this version running" afterwards."""
    vps["config_params"]["exec_risk_pct"] = 2.0
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.params["exec_risk_pct"] == 10.0        # as deployed
    assert v.params_drift == ["exec_risk_pct"]      # and the difference is named


def test_an_unpromoted_bot_is_reported_as_not_frozen(vps):
    """The dangerous state, and it must be loud: the bot is importing from the repo, so a
    pull changes what it trades and can stop it starting."""
    vps["deployed"] = {}
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.frozen is False
    assert v.hash == ""


def test_a_repo_that_has_moved_past_the_deployment_is_visible(vps):
    """Not a problem — that is the feature. But you cannot decide whether to promote without
    being able to see it."""
    vps["head"] = "b390214"
    vps["ahead"] = "12"
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.repo_commit == "b390214"
    assert v.commits_ahead == 12


def test_a_snapshot_edited_in_place_is_flagged(vps):
    """Editing the deployed files directly goes around promote, so the record no longer
    describes them. `--show` re-hashes the disk, which is what catches it."""
    vps["show"] = "  on disk  : 11111111 SNAPSHOT MODIFIED"
    assert bots.get_bot_version("MPC SOS Fade").snapshot_ok is False


def test_a_promote_not_yet_restarted_into_is_visible(vps):
    """The most misleading state available: the new code is on disk, the OLD code is still
    trading, and every file on the box says the new version. Only the live process knows."""
    vps["running_hash"] = "aaaabbbbcccc"
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.running_hash == "aaaabbbbcccc"
    assert not v.hash.startswith(v.running_hash)     # what the UI warns on


# ── What counts as drift ──────────────────────────────────────────────────────
#
# `params_drift` answers "has anybody changed a setting since this version was deployed?".
# It used to compare `deployed.get(k, current_value) != current_value` over the CURRENT keys
# only, which is blind in both directions — and blind hardest on the case that matters.

def test_a_setting_added_since_the_promote_is_drift(vps):
    """The old form defaulted a missing deployed key to the current value, so it compared
    equal: a knob the deployment has never heard of reported no drift at all."""
    vps["config_params"]["exec_tp1_pct"] = 30.0
    assert bots.get_bot_version("MPC SOS Fade").params_drift == ["exec_tp1_pct"]


def test_a_setting_removed_since_the_promote_is_drift(vps):
    """Only `current` was iterated, so a param deleted from config.json was never looked at.
    The bot still runs the deployed value; the file no longer says what it is."""
    del vps["config_params"]["exec_sl_level"]
    assert bots.get_bot_version("MPC SOS Fade").params_drift == ["exec_sl_level"]


def test_a_null_value_is_not_mistaken_for_an_absent_one(vps):
    """`None` is a value a param can legitimately hold. Reading it as "not set" would report
    drift on a bot nobody touched — the same missing-vs-null rule `mt5_link` follows."""
    vps["deployed"]["strategy_params"] = dict(vps["deployed"]["strategy_params"])
    vps["deployed"]["strategy_params"]["exec_min_stop_val"] = None
    vps["config_params"]["exec_min_stop_val"] = None
    assert bots.get_bot_version("MPC SOS Fade").params_drift == []


def test_an_unchanged_bot_reports_no_drift(vps):
    assert bots.get_bot_version("MPC SOS Fade").params_drift == []


# ── Where the running hash comes from ─────────────────────────────────────────

def test_the_running_hash_costs_no_extra_round_trip(vps):
    """It used to come from a second `_fetch_vps_snapshot()` — two commands returning every
    python process, every scheduled task and every bot's state file, issued to read ONE
    string. Measured: /version 8.5s, ~5s of it that snapshot. The Configure tab's fleet
    strip fires one per bot, so the cost multiplied by the fleet.

    The fixture makes `_fetch_vps_snapshot` raise, so this is enforced rather than counted.
    """
    bots.get_bot_version("MPC SOS Fade")
    assert len(vps["cmds"]) == 2, f"expected deployed.json + one combined read, got {vps['cmds']}"
    assert "bot_state.json" in vps["cmds"][1]


def test_the_state_file_is_resolved_from_the_registry_not_hardcoded():
    """`get_bot_version` named `state_mpc_sos_fade` outright, so any second bot got a blank
    running hash — which reads as "the live process agrees" and makes the restart-pending
    warning permanently impossible to fire. The fleet strip would then report a confident
    "0 restart pending" across a fleet it cannot see."""
    for _task, key in bots._TASK_BOT_KEYS.items():
        assert bots._bot_state_path(key), f"no bot_state.json registered for {key}"
    assert bots._bot_state_path("a_bot_nobody_registered") is None


def test_a_bot_with_no_registered_state_file_reports_an_empty_hash_not_a_crash(vps, monkeypatch):
    """Blank is the honest answer when there is nothing to read — and the UI treats a blank
    running hash as "not asked", which is why it must never be filled in with a guess."""
    monkeypatch.setattr(bots, "_bot_state_path", lambda _k: None)
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.running_hash == ""


def test_a_matching_running_hash_is_not_a_warning(vps):
    """The process reports a 12-char prefix of the full hash. Comparing them as equals would
    warn on every healthy bot, and a warning that is always on is not a warning."""
    v = bots.get_bot_version("MPC SOS Fade")
    assert v.hash.startswith(v.running_hash)


def test_an_unreadable_record_does_not_crash_the_page(vps, monkeypatch):
    """A corrupt file must degrade to "unpromoted", not take out the whole Bots page."""
    monkeypatch.setattr(bots, "_ssh", lambda cmd: "{not json" if "deployed.json" in cmd
                        else "abc1234\n===AHEAD===\n0\n===SHOW===\n")
    assert bots.get_bot_version("MPC SOS Fade").frozen is False
