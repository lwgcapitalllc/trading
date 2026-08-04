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
        if "deployed.json" in cmd:
            return json.dumps(state["deployed"]) if state["deployed"] else ""
        return (f"{state['head']}\n===AHEAD===\n{state['ahead']}\n"
                f"===SHOW===\n{state['show']}")

    monkeypatch.setattr(bots, "_ssh", _ssh)
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {
        "state_mpc_sos_fade": json.dumps(
            {"mpc_sos_fade_demo": {"source_hash": state["running_hash"]}})})
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
