"""The bar and tick caches are filed per BROKER, and an unknown broker refuses.

**Watched RED by MUTATION (2026-08-24), not by importing a name that did not exist.** Reverting
the feature outright only produced an ImportError, which proves the symbol is new and nothing
about whether these assertions can catch the defect. So the partition was mutated in place
instead, twice:

* `broker_cache_dir` returning the base dir unchanged — i.e. the exact flat layout this replaces.
  `test_two_servers_do_not_share_bars` and `test_ticks_are_filed_per_broker` both fail, and on the
  right assertion: *"broker B served broker A's cached ticks", 0 == 1*. Broker B never asked the
  agent, because broker A's data was already sitting there.
* The empty-server refusal removed and replaced with a `default` folder — the plausible-looking
  fallback somebody will propose the first time the agent hiccups.
  `test_unknown_server_refuses` and `test_broker_cache_dir_refuses_empty_server` both fail on
  DID NOT RAISE. That is rule 1: "cannot ask" must never collapse into a default.

⚠ The point is NOT that a path string contains a broker name — that would pass against a cosmetic
rename. Every test here asserts that one broker's DATA cannot reach another broker's replay.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.data.cache import UnknownBrokerError, broker_cache_dir  # noqa: E402
from backtest.data.mt5_agent import Mt5AgentError  # noqa: E402
from backtest.data.source import BarSource  # noqa: E402
from backtest.data.ticks import TickSource  # noqa: E402


class _Agent:
    """A terminal on one named server, serving three M15 bars a day apart."""

    def __init__(self, server: str, base_price: float):
        self.server = server
        self.base_price = base_price
        self.bar_calls = 0
        self.tick_calls = 0

    def status(self) -> dict:
        return {"server": self.server, "account": 1, "mt5_connected": True}

    def bars(self, symbol, tf_name, start_date, end_date):  # noqa: ARG002
        self.bar_calls += 1
        idx = pd.date_range(
            start=f"{start_date} 00:00", end=f"{end_date} 23:59", freq="15min", name="time"
        )
        n = len(idx)
        return pd.DataFrame(
            {
                "open": [self.base_price] * n,
                "high": [self.base_price + 1] * n,
                "low": [self.base_price - 1] * n,
                "close": [self.base_price] * n,
                "volume": [10.0] * n,
            },
            index=idx,
        )

    def ticks(self, symbol, start_iso, end_iso):  # noqa: ARG002
        self.tick_calls += 1
        return [
            {
                "time": "2024-01-02T00:00:00+00:00",
                "bid": self.base_price,
                "ask": self.base_price + 0.1,
            }
        ]


def _load(agent, tmp_path, monkeypatch):
    """A bare `BarSource()` — no injected cache — pointed at a scratch cache root."""
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    src = BarSource(agent=agent)
    # The floor probe is a different feature with its own tests; stub it so a scratch cache
    # with no probe file does not turn these into a test of `history.py`.
    monkeypatch.setattr(src.floors, "assert_window", lambda *a, **k: None)
    return src.load("XAUUSD", "15", "2024-01-02", "2024-01-02")


def test_two_servers_do_not_share_bars(tmp_path, monkeypatch):
    """The whole point. Broker B must fetch for itself, not read broker A's frame.

    RED before the partition: B's `bar_calls` stayed 0 and it returned A's prices.
    """
    a = _Agent("VantageMarkets-Demo", 2000.0)
    b = _Agent("PUPrime-Demo", 2500.0)

    df_a = _load(a, tmp_path, monkeypatch)
    assert a.bar_calls == 1 and float(df_a["close"].iloc[0]) == 2000.0

    df_b = _load(b, tmp_path, monkeypatch)
    assert b.bar_calls == 1, "broker B served broker A's cached bars"
    assert float(df_b["close"].iloc[0]) == 2500.0, "broker B replayed broker A's prices"


def test_same_server_still_reuses_its_own_cache(tmp_path, monkeypatch):
    """The partition must not defeat caching — a second run on the SAME broker hits the file."""
    a = _Agent("VantageMarkets-Demo", 2000.0)
    _load(a, tmp_path, monkeypatch)
    _load(a, tmp_path, monkeypatch)
    assert a.bar_calls == 1, "the same broker re-fetched instead of reading its own cache"


def test_unknown_server_refuses(tmp_path, monkeypatch):
    """A terminal that cannot name its broker gets a refusal, never a shared folder."""
    blank = _Agent("", 2000.0)
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    with pytest.raises(UnknownBrokerError):
        BarSource(agent=blank).load("XAUUSD", "15", "2024-01-02", "2024-01-02")


def test_broker_cache_dir_refuses_empty_server(tmp_path):
    for blank in ("", "   "):
        with pytest.raises(UnknownBrokerError):
            broker_cache_dir(tmp_path, blank)


def test_injected_cache_is_honoured(tmp_path, monkeypatch):
    """An explicit cache is a deliberate statement about where these bars live — and it is what
    every other test in this package passes, so breaking it would be invisible here and loud
    everywhere else."""
    from backtest.data.cache import BarCache

    pinned = tmp_path / "pinned"
    a = _Agent("", 2000.0)  # blank server would REFUSE if the injection were ignored
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    src = BarSource(agent=a, cache=BarCache(pinned))
    monkeypatch.setattr(src.floors, "assert_window", lambda *args, **kw: None)
    src.load("XAUUSD", "15", "2024-01-02", "2024-01-02")
    assert (pinned / "XAUUSD__M15.csv").is_file()


def test_ticks_are_filed_per_broker(tmp_path, monkeypatch):
    """A tick decides whether a stop or a target came first. One broker's stream must never
    answer that question for another broker's replay.

    RED before the partition: B's `tick_calls` stayed 0.
    """
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    a = _Agent("VantageMarkets-Demo", 2000.0)
    b = _Agent("PUPrime-Demo", 2500.0)

    TickSource(a).window("XAUUSD", 1704153600000, 1704153601000)
    assert a.tick_calls == 1

    got = TickSource(b).window("XAUUSD", 1704153600000, 1704153601000)
    assert b.tick_calls == 1, "broker B served broker A's cached ticks"
    assert got and got[0].bid == 2500.0, "broker B replayed broker A's tick prices"


# ── A RERUN READS THE BROKER THE RUN WAS MADE ON (2026-08-24) ────────────────
#
# 🔴 Reported from the screen: *"when we click rerun charged it should still rerun against the
# broker that the data originated from — otherwise all of my backtests will be broken."* The cost
# account was already carried; the BARS were not. Before the partition an unpinned rerun read the
# old broker's bars whatever was attached — wrong, but in the silent direction. After it, an
# unpinned rerun looks in the ATTACHED broker's folder, misses, and pulls the run's window from a
# terminal that may not even quote its symbol.


def test_a_pinned_source_reads_its_OWN_brokers_bars(tmp_path, monkeypatch):
    """The whole fix. Broker A's cached bars are served while broker B is attached.

    RED by MUTATION: ignore `server=` in `_partition` and this fails — the pinned source lands in
    B's empty folder, fetches, and returns B's prices.
    """
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    a = _Agent("VantageMarkets-Demo", 2000.0)
    src_a = BarSource(agent=a)
    monkeypatch.setattr(src_a.floors, "assert_window", lambda *args, **kw: None)
    src_a.load("XAUUSD", "15", "2024-01-02", "2024-01-02")
    assert a.bar_calls == 1

    # Now the terminal is broker B, and a rerun of A's run asks for A's window.
    b = _Agent("PUPrime-Demo", 2500.0)
    src = BarSource(agent=b, server="VantageMarkets-Demo")
    monkeypatch.setattr(src.floors, "assert_window", lambda *args, **kw: None)
    df = src.load("XAUUSD", "15", "2024-01-02", "2024-01-02")
    assert float(df["close"].iloc[0]) == 2000.0, "the rerun replayed the attached broker's prices"
    assert b.bar_calls == 0, "the rerun pulled from the wrong terminal"


def test_a_pinned_source_needs_NO_agent_when_the_window_is_cached(tmp_path, monkeypatch):
    """A cached window must replay with the terminal unreachable — a property this package
    already had and the pin must not cost. It is why the terminal is checked at FETCH time and
    not at partition time.

    RED by MUTATION: move `_assert_pin_matches_terminal` into `_partition` and this fails, because
    a dead agent then blocks a replay that needs nothing from it.
    """
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    a = _Agent("VantageMarkets-Demo", 2000.0)
    src_a = BarSource(agent=a)
    monkeypatch.setattr(src_a.floors, "assert_window", lambda *args, **kw: None)
    src_a.load("XAUUSD", "15", "2024-01-02", "2024-01-02")

    class _DeadAgent(_Agent):
        def status(self):
            raise Mt5AgentError("terminal unreachable")

    dead = _DeadAgent("", 0.0)
    src = BarSource(agent=dead, server="VantageMarkets-Demo")
    monkeypatch.setattr(src.floors, "assert_window", lambda *args, **kw: None)
    df = src.load("XAUUSD", "15", "2024-01-02", "2024-01-02")
    assert float(df["close"].iloc[0]) == 2000.0


def test_a_pinned_source_REFUSES_to_fetch_from_the_wrong_broker(tmp_path, monkeypatch):
    """The half that keeps the cache honest, and the one worth most.

    A fetch here would merge one broker's bars into another's history PERMANENTLY and invisibly —
    the file is one CSV per (symbol, timeframe) and nothing in a bar records where it came from.
    Refusing is the answer; the message names both brokers and the two real ways out.

    RED by MUTATION: drop the `_assert_pin_matches_terminal` call from the fetch loop and this
    fails — the pinned run silently serves the wrong broker's prices.
    """
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path))
    b = _Agent("PUPrime-Demo", 2500.0)
    src = BarSource(agent=b, server="VantageMarkets-Demo")  # nothing cached for Vantage
    monkeypatch.setattr(src.floors, "assert_window", lambda *args, **kw: None)
    with pytest.raises(UnknownBrokerError) as exc:
        src.load("XAUUSD", "15", "2024-01-02", "2024-01-02")
    assert "VantageMarkets-Demo" in str(exc.value) and "PUPrime-Demo" in str(exc.value)
    assert b.bar_calls == 0, "it asked the wrong terminal for bars before refusing"
