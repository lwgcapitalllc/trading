"""The promote preview must refuse a configuration that would kill the bot on restart.

🔴 **WHY THIS FILE EXISTS.** On 2026-08-28 the re-entry was switched on for `mpc_sos_fade_demo`,
`promote.py --dry-run` printed *"verified: the snapshot imports and builds with the promoted
parameters"*, and the bot would not come back up — down until the setting was reverted. Importing
and building is not running: every startup refusal lives in `algos/live/`, which the staged
snapshot does not even contain, and nothing before a restart reached one.

⚠ **The first two tests drive the REAL `verify()` subprocess against a REAL staged snapshot**,
not a hand-written payload. A dict I typed myself would prove only that my parser reads my own
dict — and this repo has already paid for a fixture more capable than production. They are slow
(a subprocess plus a strategy import) and that is the price of them being worth anything.
"""

import json
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "algos" / "tools"))
sys.path.insert(0, str(_REPO / "algos" / "live"))

import promote  # noqa: E402

BOT_CONFIG = _REPO / "algos" / "markets" / "fx" / "instances" / "mpc_sos_fade_demo" / "config.json"


def _live_params():
    return dict(json.loads(BOT_CONFIG.read_text())["strategy_params"])


def _cfg(tmp_path, **over):
    """A promote config shaped like the live bot's, staging into a throwaway directory.

    ⚠ `deployed_dir` points at tmp_path on purpose — `stage()` writes a sibling `deployed.new/`,
    and a test must never put one beside a real bot's live snapshot.
    """
    params = _live_params()
    params.update(over)
    return types.SimpleNamespace(
        bot_key="test_bot",
        symbol="XAUUSD.p",
        timeframe="M15",
        strategy_package="mpc_sos_fade",
        strategy_class="MpcSosFadeStrategy",
        strategy_params=params,
        deployed_dir=tmp_path / "deployed",
    )


def test_the_verify_subprocess_really_ships_the_startup_facts(tmp_path):
    """Not "my parser handles a dict" — the real snapshot, the real subprocess, the real payload."""
    cfg = _cfg(tmp_path)
    staging, _n = promote.stage(cfg, promote.repo_trees(cfg))
    ok, detail = promote.verify(cfg, staging)
    assert ok, detail
    startup = json.loads(detail)["startup"]
    assert startup["fast_feed_minutes"] is None, "the shipped bot asks for no second feed"
    assert startup["has_make_dual_clock"] is True
    assert startup["settings"]["exec_secondary"] is False
    assert startup["settings"]["exec_sec_tp1_pct"] == 50.0, (
        "every field must travel, not just the ones a check reads today"
    )
    assert not startup["opaque"], f"unexpected non-plain settings: {startup['opaque']}"
    assert promote.startup_refusals(startup, cfg.timeframe) == []


def test_the_config_that_killed_the_bot_is_now_refused_by_the_preview(tmp_path):
    """The 2026-08-28 outage, replayed. This exact config previewed GREEN and would not start."""
    cfg = _cfg(tmp_path, exec_secondary=True)
    staging, _n = promote.stage(cfg, promote.repo_trees(cfg))
    ok, detail = promote.verify(cfg, staging)
    assert ok, "it still IMPORTS and BUILDS — that was always the point"
    startup = json.loads(detail)["startup"]
    assert startup["fast_feed_minutes"] == 5, "the strategy now asks for its own fill clock"
    refusals = promote.startup_refusals(startup, cfg.timeframe)
    assert refusals, "the preview must refuse what the restart refuses"
    # ⚠ **The SECOND-FEED refusal, and which one fires is worth reading carefully.** This bot's
    # config states the GAP trigger (`exec_sec_trigger = "FVG in zone"`), whose 50% bank leaves a
    # runner — so since the bank path landed on 2026-09-01 that is no longer a reason to refuse,
    # and what remains is the missing second ENTRY. Point the same bot at the RECLAIM trigger and
    # a different refusal fires first, because its 100% is a full exit the bridge still cannot do.
    # ⚠ An earlier version of this comment claimed this bot runs the reclaim. It does not, and
    # every published re-entry figure was measured as though it did — see the strategy's notes.
    assert any("SECOND bar stream" in r for r in refusals), refusals
    assert not any("WHOLE position off at a price" in r for r in refusals), (
        "the gap trigger's half-bank leaves a runner and is supported now"
    )


# ── the rule itself, driven directly ──────────────────────────────────────────
def _startup(**over):
    s = {
        "settings": {
            "exec_tp1_pct": 0.0,
            "exec_tp2_pct": 0.0,
            "fill_model": "bar",
            "exec_secondary": False,
            "exec_short_hold": False,
            "exec_scale_in": False,
        },
        "opaque": [],
        "fast_feed_minutes": None,
        "fast_feed_error": None,
        "has_make_dual_clock": True,
    }
    s.update(over)
    return s


def test_a_missing_payload_is_NOT_ASKED_and_not_a_pass():
    """Rule 1. An older snapshot ships no startup facts; [] here means the question was not put,
    and `main` prints exactly that rather than a clean bill of health."""
    assert promote.startup_refusals({}, "M15") == []


def test_a_fill_clock_MT5_has_no_timeframe_for_is_refused():
    out = promote.startup_refusals(_startup(fast_feed_minutes=7), "M15")
    assert any("No MT5 timeframe is 7 minutes long" in r for r in out), out


def test_a_fill_clock_that_is_not_faster_than_the_primary_is_refused():
    out = promote.startup_refusals(_startup(fast_feed_minutes=15), "M15")
    assert any("is not FASTER than" in r for r in out), out


def test_a_strategy_that_wants_a_feed_but_cannot_merge_it_is_refused():
    out = promote.startup_refusals(_startup(fast_feed_minutes=5, has_make_dual_clock=False), "M15")
    assert any("make_dual_clock" in r for r in out), out


def test_a_strategy_that_RAISED_when_asked_is_reported_rather_than_read_as_no_feed():
    """Rule 1 again, one level down: "it has no second feed" and "asking blew up" are different
    answers and must not print the same."""
    out = promote.startup_refusals(_startup(fast_feed_error="ValueError: boom"), "M15")
    assert any("raised ValueError: boom" in r for r in out), out


def test_every_refusal_is_reported_at_once_not_one_per_round_trip():
    out = promote.startup_refusals(
        _startup(
            settings={**_startup()["settings"], "exec_secondary": True, "fill_model": "tick"},
            fast_feed_minutes=7,
        ),
        "M15",
    )
    assert len(out) >= 2, out
