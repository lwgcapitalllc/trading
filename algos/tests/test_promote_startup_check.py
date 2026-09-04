"""The promote preview must refuse a configuration that would kill the bot on restart.

🔴 **WHY THIS FILE EXISTS.** On 2026-08-28 the re-entry was switched on for `sos_fade_demo`,
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

BOT_CONFIG = _REPO / "algos" / "markets" / "fx" / "instances" / "sos_fade_demo" / "config.json"


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
        strategy_package="sos_fade",
        strategy_class="SosFadeStrategy",
        strategy_params=params,
        deployed_dir=tmp_path / "deployed",
    )


def test_the_verify_subprocess_really_ships_the_startup_facts(tmp_path):
    """Not "my parser handles a dict" — the real snapshot, the real subprocess, the real payload.

    🔴 **IT PINNED THE SHIPPED BOT'S SETTINGS BY VALUE UNTIL 2026-09-02, AND THAT WENT RED THE DAY
    SOMEBODY CHANGED ONE.** It read `exec_secondary is False` and `exec_sec_tp1_pct == 50.0` — both
    true of the config that day and neither one this test's subject. **A test that hardcodes a
    setting reddens on a deliberate settings change and teaches the next reader to edit the
    assertion**, which is how a real red gets waved through. What it is actually about is the
    SHIPPING: that a real subprocess against a real staged snapshot returns real facts.

    ⚠ **So the expected values are read from the config file itself** — and the one thing that
    cannot be read from there is asserted hard: a field NO rule looks at still has to travel, or a
    rule that grows a field tomorrow reads a `getattr` default and is wrong in the direction of
    saying yes.
    """
    cfg = _cfg(tmp_path)
    staging, _n = promote.stage(cfg, promote.repo_trees(cfg))
    ok, detail = promote.verify(cfg, staging)
    assert ok, detail
    startup = json.loads(detail)["startup"]

    want = _live_params()
    assert startup["settings"]["exec_secondary"] is want["exec_secondary"]
    assert startup["settings"]["exec_sec_tp1_pct"] == want["exec_sec_tp1_pct"]
    # Asked of the built STRATEGY, not read off the file — so it must AGREE with the file.
    assert (startup["fast_feed_minutes"] is None) is (not want["exec_secondary"]), (
        "the strategy and its config disagree about whether this bot wants a second feed"
    )
    assert startup["has_make_dual_clock"] is True

    # Read by nothing in `startup_refusals`, which is exactly why it is here.
    assert startup["settings"]["exec_sl_custom"] == want["exec_sl_custom"], (
        "every field must travel, not just the ones a check reads today"
    )
    assert not startup["opaque"], f"unexpected non-plain settings: {startup['opaque']}"
    assert promote.startup_refusals(startup, cfg.timeframe) == [], (
        "the SHIPPED config must start — if this reddens, read it before touching the test"
    )


def test_the_config_that_killed_the_bot_now_STARTS(tmp_path):
    """The 2026-08-28 outage config, replayed against the real snapshot — and it is CLEAN now.

    🔴 **THIS TEST ASSERTED A REFUSAL FROM 2026-09-01 TO 2026-09-02 AND NOW ASSERTS THE ABSENCE
    OF ONE. Read what changed, because the two readings are opposites.** Three separate reasons
    to refuse this config have been retired in that window: its 50% bank (the bank path landed),
    a rung taking the whole position (the full-exit path landed), and the blanket
    *"needs a SECOND bar stream"* (the re-entry's own order path landed). Nothing was softened to
    get here — each refusal went when the capability it stood in for existed.

    ⚠ **Clean here means WOULD START, never WOULD WORK.** No re-entry order has ever reached a
    broker. Rule 9.

    ⚠ **The file's headline property is proved by the test below, not by this one** — the preview
    still has to refuse what the restart refuses, and a test that only ever sees an empty list
    cannot show that.
    """
    cfg = _cfg(tmp_path, exec_secondary=True)
    staging, _n = promote.stage(cfg, promote.repo_trees(cfg))
    ok, detail = promote.verify(cfg, staging)
    assert ok, "it still IMPORTS and BUILDS — that was always the point"
    startup = json.loads(detail)["startup"]
    assert startup["fast_feed_minutes"] == 5, "the strategy asks for its own fill clock"
    assert startup["has_make_dual_clock"] is True, "and it can merge the two streams"
    # ⚠ This bot's config states the GAP trigger (`exec_sec_trigger = "FVG in zone"`), whose 50%
    # bank leaves a runner. An earlier comment here claimed it runs the RECLAIM. It does not, and
    # every published re-entry figure was measured as though it did — see the strategy's notes.
    assert promote.startup_refusals(startup, cfg.timeframe) == []


def test_the_preview_still_refuses_what_the_restart_refuses(tmp_path):
    """The property this whole file exists for, driven through the REAL subprocess and snapshot.

    ⚠ **It needs a config that is genuinely still refused, and it must be re-pointed at one
    whenever the last one becomes supported** — which has now happened three times in two days.
    The force-close on an opposite structure break is today's: its fill carries the same tag an
    ordinary stop-out does, so nothing can tell the bridge which happened, and refusing is the
    answer until the strategy gives that exit its own tag.

    🔴 **If this test is ever the one that reddens because its config became supported, the fix is
    to point it at another refusal — never to delete it.** A file whose every case expects an
    empty list has stopped testing the thing it was written for.
    """
    cfg = _cfg(tmp_path, exec_close_opp_sos=True)
    staging, _n = promote.stage(cfg, promote.repo_trees(cfg))
    ok, detail = promote.verify(cfg, staging)
    assert ok, "it IMPORTS and BUILDS — which is exactly why the preview used to bless it"
    startup = json.loads(detail)["startup"]
    assert startup["settings"]["exec_close_opp_sos"] is True
    refusals = promote.startup_refusals(startup, cfg.timeframe)
    assert any("exec_close_opp_sos" in r for r in refusals), refusals


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
    """⚠ Note `exec_secondary` is OFF in this payload, and that is the point — a strategy can want
    a second stream for some other reason, and the merge rule is not about the re-entry."""
    out = promote.startup_refusals(_startup(fast_feed_minutes=5, has_make_dual_clock=False), "M15")
    assert any("make_dual_clock" in r for r in out), out


def test_a_re_entry_switched_ON_with_no_fill_clock_is_refused_by_the_preview():
    """🔴 **THE HOLE THIS FILE HAD FOR AS LONG AS IT EXISTED, opened up by lifting the blanket
    refusal on 2026-09-02.** The feed checks here ran `if minutes is not None`, so a config asking
    for a re-entry from a strategy that offers no fill clock produced no refusal at all — and the
    restart would not have refused it either. It was invisible while `assert_supported` turned
    away every `exec_secondary` config before the feed questions were even reached.

    ⚠ Both surfaces now ask ONE function, which is the only reason they cannot answer differently.

    MUTATION: restore the `if minutes is not None` gate around the seam check and this goes red.
    """
    out = promote.startup_refusals(
        _startup(settings={**_startup()["settings"], "exec_secondary": True}),
        "M15",
    )
    assert any("offers no fill clock" in r for r in out), out


def test_a_strategy_that_RAISED_when_asked_is_reported_rather_than_read_as_no_feed():
    """Rule 1 again, one level down: "it has no second feed" and "asking blew up" are different
    answers and must not print the same."""
    out = promote.startup_refusals(_startup(fast_feed_error="ValueError: boom"), "M15")
    assert any("raised ValueError: boom" in r for r in out), out


def test_a_RAISE_is_not_reported_as_a_strategy_with_no_fill_clock():
    """🔴 **The same two answers, now colliding one layer up — and the collision is REAL.** The
    verify subprocess reports `fast_feed_minutes: None` after an exception, which is the identical
    value a strategy with no fill clock produces. Run the seam check on it and a strategy that HAS
    a fill clock and blew up when asked is told it does not have one, which sends the reader to
    write a method that is already there.

    MUTATION: drop the `else` in `startup_refusals` so the seam check runs on the error path too,
    and this goes red with both sentences printed.
    """
    out = promote.startup_refusals(
        _startup(
            settings={**_startup()["settings"], "exec_secondary": True},
            fast_feed_error="ValueError: boom",
        ),
        "M15",
    )
    assert any("raised ValueError: boom" in r for r in out), out
    assert not any("offers no fill clock" in r for r in out), out


def test_every_refusal_is_reported_at_once_not_one_per_round_trip():
    out = promote.startup_refusals(
        _startup(
            settings={**_startup()["settings"], "exec_secondary": True, "fill_model": "tick"},
            fast_feed_minutes=7,
        ),
        "M15",
    )
    assert len(out) >= 2, out
