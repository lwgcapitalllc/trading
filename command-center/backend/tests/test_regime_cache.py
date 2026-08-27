"""The regime map is a pure function of the bars and the classifier, and is cached on both.

MEASURED on the live cache before this existed: **98.5 seconds** to turn 50,548 H1+H4 rows into
2,066 date->label strings, recomputed in full on EVERY run of the same window — and a second
identical call cost the same again. On a 3.5-minute backtest that was half the wall clock, and
the tuning loop re-runs one window over and over. After: **2.27s**, and the map is byte-identical
(0 of 2,066 days disagree, verified against a baseline captured before the change).

🔴 **THE WHOLE POINT IS THAT A HIT IS IMPOSSIBLE UNLESS THE INPUTS ARE BYTE-IDENTICAL.** A regime
label is an input to how a run is READ - the overlays, the per-regime table, the optimizer's
regime filter - so a stale label is silent and wrong in the direction nobody checks. These tests
are about the KEY far more than about the speed.

**WATCHED RED by mutation, named per test.** A fail-watch against HEAD is vacuous (the cache did
not exist, so every test would fail on a missing attribute); each test names the mutation that
turns it red instead.
"""

import json

import pandas as pd
import pytest
from services import backtest_runner as br


def _frame(n: int, seed: float = 0.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    base = [100.0 + seed + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [b + 1 for b in base],
            "low": [b - 1 for b in base],
            "close": [b + 0.5 for b in base],
        },
        index=idx,
    )


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Every test gets its own cache dir. Without this they share the real one and a hit from
    a previous test is indistinguishable from the behaviour under test."""
    monkeypatch.setattr(br, "_REGIME_CACHE_DIR", tmp_path / "regime_cache")


# ── the key ───────────────────────────────────────────────────────────────────


def test_the_same_inputs_give_the_same_key():
    a = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
    )
    b = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
    )
    assert a is not None and a == b


def test_ONE_CHANGED_BAR_CHANGES_THE_KEY():
    """🔴 The staleness guard. A window ending today is still filling and the broker back-fills
    history, so a date-keyed cache would serve yesterday's answer for bars that have since moved.
    MUTATION: drop the OHLC columns from the fingerprint - this goes red, the others stay green."""
    a = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
    )
    b = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40, seed=0.001), _frame(20)
    )
    assert a != b


def test_one_extra_bar_changes_the_key():
    a = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
    )
    b = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(41), _frame(20)
    )
    assert a != b


@pytest.mark.parametrize(
    ("field", "value"),
    [("instrument", "EURUSD"), ("runner", "mt5"), ("start", "2024-02-01"), ("end", "2024-07-01")],
)
def test_every_stated_input_is_in_the_key(field, value):
    args = dict(instrument="XAUUSD.p", runner="python", start="2024-01-01", end="2024-06-01")
    a = br._regime_cache_key(
        args["instrument"], args["runner"], args["start"], args["end"], _frame(40), _frame(20)
    )
    args[field] = value
    b = br._regime_cache_key(
        args["instrument"], args["runner"], args["start"], args["end"], _frame(40), _frame(20)
    )
    assert a != b, f"{field} is not in the cache key"


def test_THE_CLASSIFIERS_OWN_SOURCE_IS_IN_THE_KEY(tmp_path, monkeypatch):
    """🔴 Edit the rule and every stored label must stop matching. A cached label produced by a
    superseded classifier is exactly the silent wrongness this repo keeps paying for.
    MUTATION: drop the `read_bytes` line from the key. It reddens THIS test **and**
    `test_a_key_that_cannot_be_taken_is_None_not_a_partial_one` - that was RUN, not reasoned, and
    the second one is a correct catch rather than a leak: the same line is what raises when the
    classifier cannot be read, which is what makes the key refuse instead of going partial."""
    a = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
    )

    fake = tmp_path / "classifier.py"
    fake.write_text("# a different rule\n")

    class _Mod:
        __file__ = str(fake)

    monkeypatch.setattr(br, "classifier_module", _Mod)
    b = br._regime_cache_key(
        "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
    )
    assert a != b


def test_a_key_that_cannot_be_taken_is_None_not_a_partial_one(monkeypatch):
    """⚠ A key that quietly drops one of its inputs still LOOKS like a key and would serve stale
    labels for ever. Refusing costs 98 seconds and cannot be wrong."""

    class _Broken:
        __file__ = "/no/such/classifier.py"

    monkeypatch.setattr(br, "classifier_module", _Broken)
    assert (
        br._regime_cache_key(
            "XAUUSD.p", "python", "2024-01-01", "2024-06-01", _frame(40), _frame(20)
        )
        is None
    )


# ── read / write, and failing OPEN ────────────────────────────────────────────


def test_a_stored_map_reads_back_exactly():
    key = "k" * 40
    br._regime_cache_write(key, {"2024-01-02": "TRENDING", "2024-01-03": "RANGING"})
    assert br._regime_cache_read(key) == {"2024-01-02": "TRENDING", "2024-01-03": "RANGING"}


def test_no_key_means_no_shortcut_in_BOTH_directions():
    """A None key must neither read nor write. Writing under a None key is how one window's map
    ends up served for another."""
    assert br._regime_cache_read(None) is None
    br._regime_cache_write(None, {"2024-01-02": "TRENDING"})
    assert not (br._REGIME_CACHE_DIR.exists() and any(br._REGIME_CACHE_DIR.iterdir()))


def test_a_CORRUPT_cache_file_is_a_MISS_not_a_crash():
    """⚠ Fails OPEN. A truncated or half-written file must cost the 98 seconds, never the run.
    MUTATION: remove the try/except from `_regime_cache_read` - this goes red."""
    key = "c" * 40
    br._REGIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (br._REGIME_CACHE_DIR / f"{key}.json").write_text("{not json at all")
    assert br._regime_cache_read(key) is None


def test_a_WELL_FORMED_file_of_the_WRONG_SHAPE_is_a_miss():
    """A JSON file that parses but is not a date->label map is not a cache hit, whatever wrote it.
    Serving it would hand a run a calendar of the wrong type and fail somewhere further away."""
    key = "s" * 40
    br._REGIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (br._REGIME_CACHE_DIR / f"{key}.json").write_text(json.dumps({"2024-01-02": ["TRENDING"]}))
    assert br._regime_cache_read(key) is None


def test_an_empty_map_is_never_STORED():
    """`build_date_regime_map` returns {} when the fetch failed or the frame was empty - a
    statement that it could not answer, not that the window has no regimes. Storing it would
    make one bad fetch permanent."""
    key = "e" * 40
    br._regime_cache_write(key, {})
    assert br._regime_cache_read(key) is None


def test_an_UNWRITABLE_cache_dir_still_answers(monkeypatch):
    """The cache is a shortcut for next time, never part of producing THIS run's answer."""

    def _boom(*a, **k):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(br.Path, "mkdir", _boom)
    br._regime_cache_write("f" * 40, {"2024-01-02": "TRENDING"})  # must not raise
