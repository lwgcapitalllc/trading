"""The overnight-cost watch fires on the EVENT, and stays quiet the rest of the time.

🔴 **WHY THIS FILE EXISTS.** This watcher's normal state is silence, so a working one and a dead
one look identical from outside for weeks. Every test here drives a path that is invisible in
ordinary operation:

  - it SPEAKS when the broker re-quotes, and on the FIRST reading (which establishes the series);
  - it stays QUIET when nothing moved — the state that must not be reachable by accident;
  - it keeps "the lab refuses to charge this tier" apart from a number (rule 1);
  - it REFUSES a tier the lab has never heard of rather than comparing against nothing.

⚠ **The quiet test is the load-bearing one.** If `assess` could return "nothing moved" for a
reading that did move, this tool's output would be indistinguishable from a crashed task.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (
    str(_REPO),
    str(_REPO / "algos" / "tools"),
    str(_REPO / "algos" / "live"),
    str(_REPO / "algos" / "shared"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import watch_broker_costs as watch  # noqa: E402

READING = {
    "long": -80.54,
    "short": 32.67,
    "symbol": "XAUUSD.p",
    "swap_mode": 1,
    "rollover_3days": 3,
}
LAB = {"long": -79.60, "short": 30.25}


# ── what the lab holds ────────────────────────────────────────────────────────────────
def test_a_measured_tier_comes_back_as_numbers():
    assert watch.lab_swap("puprime_ecn") == {"long": -79.60, "short": 30.25}


def test_a_tier_NOBODY_HAS_READ_comes_back_as_the_sentinel_not_a_number():
    """🔴 Rule 1. "the lab refuses to charge this tier" and "the lab charges 0.00" are different
    claims, and turning the first into the second would invent agreement with any broker reading
    that happened to be near zero. RED if the sentinel is converted to a float or to None."""
    got = watch.lab_swap("puprime_cent")
    assert got == {"long": watch.UNMEASURED, "short": watch.UNMEASURED}
    assert not isinstance(got["long"], float)


def test_two_brokers_do_not_share_one_number():
    """The whole point of naming the tier. Vantage and PU Prime are different measurements, and
    reporting one as the other is the error this repo has already paid for twice."""
    assert watch.lab_swap("vantage_demo") != watch.lab_swap("puprime_ecn")


def test_a_tier_the_lab_has_never_heard_of_is_REFUSED():
    """There is nothing to compare against, so the honest answer is to stop. Guessing a tier
    would report a drift against a number this bot's account has no relationship to."""
    with pytest.raises(SystemExit) as e:
        watch.lab_swap("not_a_real_tier")
    assert "PROFILES" in str(e.value)


# ── did the broker move ───────────────────────────────────────────────────────────────
def test_an_UNCHANGED_reading_says_nothing_moved():
    """The quiet path, and the one that must not be reachable by accident — silence here is
    indistinguishable from a crashed scheduled task, so it has to be earned."""
    v = watch.assess(READING, {"long": -80.54, "short": 32.67}, LAB)
    assert v["moved"] == {}
    assert v["first_reading"] is False


def test_a_MOVED_reading_names_the_side_and_the_size():
    """A count would not do. Gold CHARGES longs and PAYS shorts, so which side moved decides
    whether the change is a cost or a credit."""
    v = watch.assess(READING, {"long": -81.18, "short": 31.29}, LAB)
    assert set(v["moved"]) == {"long", "short"}
    assert v["moved"]["long"]["was"] == -81.18
    assert v["moved"]["long"]["now"] == -80.54
    assert v["moved"]["long"]["by"] == pytest.approx(0.64)


def test_ONE_side_moving_is_reported_as_one_side():
    """A single netted number would hide it: the credit moved 8% while the charge moved 1% on the
    2026-09-02 reading, and this strategy's scratch arithmetic rests on that credit."""
    v = watch.assess(READING, {"long": -80.54, "short": 31.29}, LAB)
    assert set(v["moved"]) == {"short"}


def test_NO_PREVIOUS_READING_is_not_the_same_as_nothing_moved():
    """🔴 Rule 1 again, and the failure is total: a watcher whose first act is silence cannot be
    told from one that never ran. The first reading is also the only thing that establishes the
    series. RED if `previous is None` falls through to the unchanged path."""
    v = watch.assess(READING, None, LAB)
    assert v["first_reading"] is True
    assert v["moved"] == {}


# ── how far the lab is ────────────────────────────────────────────────────────────────
def test_the_gap_to_the_lab_is_reported_per_side():
    v = watch.assess(READING, {"long": -80.54, "short": 32.67}, LAB)
    assert v["lab_gap"]["long"]["held"] == -79.60
    assert v["lab_gap"]["long"]["pct"] == pytest.approx(1.167, abs=0.01)
    assert v["lab_gap"]["short"]["pct"] == pytest.approx(7.41, abs=0.01)


def test_an_unmeasured_tier_has_NO_gap_rather_than_a_zero_one():
    """Nothing to be adrift from. A 0% here would read as "the lab is exactly right"."""
    v = watch.assess(READING, None, {"long": watch.UNMEASURED, "short": watch.UNMEASURED})
    assert v["lab_gap"]["long"]["pct"] is None
    assert v["lab_gap"]["long"]["held"] == watch.UNMEASURED


def test_a_profile_that_charges_no_swap_is_its_own_state():
    """`swap=None` on a profile means "charge nothing" DELIBERATELY — not unmeasured, and not a
    number. Three states, and the message says which."""
    v = watch.assess(READING, None, {"long": None, "short": None})
    assert v["lab_gap"]["long"]["held"] is None
    assert v["lab_gap"]["long"]["pct"] is None


# ── what the message says ─────────────────────────────────────────────────────────────
def test_the_message_carries_BOTH_numbers_on_every_side():
    """The broker's reading and the lab's are different questions and a reader acts on the
    second. Reporting only the move would leave "so what is being charged?" unanswered."""
    v = watch.assess(READING, {"long": -81.18, "short": 31.29}, LAB)
    text = watch.summarise(v, "mpc_sos_fade_demo", "puprime_ecn")
    assert "-80.54" in text and "+32.67" in text  # the broker now
    assert "-79.60" in text and "+30.25" in text  # what backtests charge
    assert "puprime_ecn" in text and "XAUUSD.p" in text


def test_the_message_says_NOTHING_WAS_CHANGED():
    """The tool does not re-price, and a message that did not say so would read as though the
    lab had been updated — after which nobody does it."""
    v = watch.assess(READING, {"long": -81.18, "short": 31.29}, LAB)
    assert "Nothing has been changed" in watch.summarise(v, "bot", "puprime_ecn")


def test_the_first_reading_message_does_not_claim_a_move():
    v = watch.assess(READING, None, LAB)
    text = watch.summarise(v, "bot", "puprime_ecn")
    assert "FIRST READING" in text
    assert "MOVED" not in text


def test_an_unmeasured_tier_is_SAID_rather_than_shown_as_a_number():
    v = watch.assess(READING, None, {"long": watch.UNMEASURED, "short": watch.UNMEASURED})
    assert "refuses to charge" in watch.summarise(v, "bot", "puprime_cent")


# ── the state file ────────────────────────────────────────────────────────────────────
def test_a_corrupt_state_file_reads_as_NO_previous_reading(tmp_path):
    """The two failure directions are not equal. An extra message is an annoyance; treating an
    unreadable file as "already up to date" would swallow the message this tool exists to send."""
    p = tmp_path / "broker_costs_watch.json"
    p.write_text("{not json", encoding="utf-8")
    assert watch._load_state(p) == {}


def test_a_missing_state_file_reads_as_NO_previous_reading(tmp_path):
    assert watch._load_state(tmp_path / "nothing.json") == {}


# ── the two defects found by RUNNING it (2026-09-03) ──────────────────────────────────
#
# Neither was visible from reading the file, and one of them made the whole alarm unreachable.
# Both are pinned here because both are silent in production: the first refuses on a config that
# is perfectly correct, the second turns the tool's own failure back into the silence it exists
# to break.
def test_the_account_profile_is_found_where_the_live_bot_actually_puts_it():
    """🔴 MEASURED: it refused on `mpc_sos_fade_demo`'s own config, which plainly names a tier —
    the key sits under the strategy params, not at the top level. RED if only the top level is
    read. ⚠ Asserted against the REAL config on disk, not a fixture: a fixture would have been
    written to the shape I assumed, which is exactly how this shipped."""
    import broker_facts

    cfg = broker_facts.load_instance("mpc_sos_fade_demo")
    key = watch.profile_key_for(cfg)
    assert key == "puprime_ecn"
    assert watch.lab_swap(key)["long"] is not watch.UNMEASURED


def test_a_terminal_that_CANNOT_BE_READ_still_raises_the_alarm(monkeypatch):
    """🔴 THE ONE THAT MATTERED. `broker_facts.attach()` raises `SystemExit` for every reason the
    terminal cannot be read — not running, not logged in, logged into the WRONG ACCOUNT — and
    `SystemExit` is not an `Exception`, so a bare `except Exception` let all three past. MEASURED
    before the fix: the message reached stderr and NO alert was sent, which is precisely the
    silence this watcher exists to break. RED if the handler stops naming SystemExit."""
    sent = []
    monkeypatch.setattr(watch, "_send", lambda text, dry: sent.append(text))
    monkeypatch.setattr(watch, "_health", lambda bot, **f: None)

    def cannot_attach(cfg):
        raise SystemExit("could not attach to C:\\MT5_FFT: terminal not running")

    monkeypatch.setattr(watch, "read_live", cannot_attach)

    rc = watch.main(["--bot", "mpc_sos_fade_demo"])
    assert rc == 1, "a watch that cannot run must not report success"
    assert len(sent) == 1, "the failure was silent — the alarm cannot fire"
    assert "NOT RUNNING" in sent[0]
    assert "terminal not running" in sent[0], "the alarm must name the cause, not just ring"


def test_an_ordinary_exception_still_raises_the_alarm(monkeypatch):
    """The control for the case above — widening to SystemExit must not have dropped the plain
    path. Both failures leave the watch not watching, so both have to speak."""
    sent = []
    monkeypatch.setattr(watch, "_send", lambda text, dry: sent.append(text))
    monkeypatch.setattr(watch, "_health", lambda bot, **f: None)
    monkeypatch.setattr(
        watch, "read_live", lambda cfg: (_ for _ in ()).throw(RuntimeError("the terminal lied"))
    )

    assert watch.main(["--bot", "mpc_sos_fade_demo"]) == 1
    assert len(sent) == 1 and "the terminal lied" in sent[0]
