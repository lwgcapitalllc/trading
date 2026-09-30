"""The fast structure feed replayed from a recording (`PlayedStructure1m`) and the store behind it
(`backtest/replay/recorded.py`).

What is locked: a replay hands the dual clock EXACTLY what a live `Structure1m` would have, on the
same bar, including the confirmed swing the clock reads off the feed; it refuses a bar out of
sequence; and the store misses when the bars, the settings or the engine source change.

Proven by mutation, 2026-09-27: serving `_outputs[index + 1]` turns
`test_a_replay_is_the_live_feed_bar_for_bar` red; dropping the sequence check turns
`test_a_replay_refuses_a_bar_out_of_sequence` red; dropping the source digest from `key()` turns
`test_the_store_misses_when_the_engine_source_changes` red.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))

from backtest.replay import recorded  # noqa: E402
from strategies.python.sos_fade.secondary import (  # noqa: E402
    PlayedStructure1m,
    RecordingStructure1m,
    Structure1m,
)


def _walk(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 2600 + np.cumsum(rng.normal(0, 1.5, n))
    high = close + rng.uniform(0.1, 2.0, n)
    low = close - rng.uniform(0.1, 2.0, n)
    open_ = np.r_[close[0], close[:-1]]
    idx = pd.date_range("2025-01-01", periods=n, freq="1min", name="time")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def _feed(feed, df):
    out = []
    for i, (o, h, l, c) in enumerate(df[["open", "high", "low", "close"]].itertuples(index=False)):
        m = feed.update(i, o, h, l, c)
        out.append((m, feed.conf_high, feed.conf_low))
    return out


def test_a_replay_is_the_live_feed_bar_for_bar():
    df = _walk()
    live = _feed(Structure1m(major_length=5), df)
    rec = RecordingStructure1m(major_length=5)
    assert _feed(rec, df) == live  # recording changes nothing
    assert _feed(PlayedStructure1m(rec.outputs), df) == live
    assert any(m.new_bull_sos or m.new_bear_sos for m, _, _ in live), "the walk must have SOS events"


def test_a_replay_refuses_a_bar_out_of_sequence():
    df = _walk(50)
    rec = RecordingStructure1m(major_length=5)
    _feed(rec, df)
    played = PlayedStructure1m(rec.outputs)
    played.update(0, 1, 1, 1, 1)
    with pytest.raises(RuntimeError):
        played.update(2, 1, 1, 1, 1)
    with pytest.raises(RuntimeError):
        PlayedStructure1m(rec.outputs[:3]).update(3, 1, 1, 1, 1)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(recorded, "_STORE_DIR", tmp_path / "streams")
    src = tmp_path / "engine.py"
    src.write_text("LENGTH = 1\n")
    return src


def test_the_store_round_trips_and_misses_on_different_bars_or_settings(store):
    df = _walk(40)
    k = recorded.key("s", df, {"major_length": 5}, [store])
    rec = RecordingStructure1m(major_length=5)
    _feed(rec, df)
    recorded.save(k, rec.outputs)
    assert recorded.load(k) == rec.outputs
    moved = df.copy()
    moved.iloc[-1, moved.columns.get_loc("close")] += 0.01
    assert recorded.key("s", moved, {"major_length": 5}, [store]) != k
    assert recorded.key("s", df, {"major_length": 6}, [store]) != k


def test_the_store_misses_when_the_engine_source_changes(store):
    df = _walk(40)
    k = recorded.key("s", df, {}, [store])
    store.write_text("LENGTH = 2\n")
    assert recorded.key("s", df, {}, [store]) != k


def test_a_missing_source_or_corrupt_file_recomputes(store, tmp_path):
    df = _walk(40)
    assert recorded.key("s", df, {}, [tmp_path / "gone.py"]) is None
    k = recorded.key("s", df, {}, [store])
    recorded._STORE_DIR.mkdir(parents=True)
    (recorded._STORE_DIR / f"{k}.pkl").write_bytes(b"not a pickle")
    assert recorded.load(k) is None
