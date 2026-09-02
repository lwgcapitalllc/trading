"""
Tests for backfill.py's --top-up mode — the scheduled path that keeps the calendar cache current.

No network: every case here stops at the DECISION (which month to resume from, whether there is
anything to do at all, or refuse), which is the part that was missing and the part that can go
quietly wrong. The fetch itself is the history source's job and is covered by test_history_parser.py
on a saved sample.

Watched RED against HEAD (8bd0ceae, 2026-09-01): 9 of the 12 fail there on the missing
`coverage_end_ms` / `_top_up_start_ms` / `_coverage_is_current`. The three argparse cases PASS
against HEAD by accident and are worth naming rather than counting as evidence — `--from` was
required and `--top-up`/`--if-stale` unknown, so all three argv shapes exited 2 for reasons that had
nothing to do with the rule being pinned. Everything is therefore pinned by mutation as well. Seven
mutations, each watched kill its test:

  * `coverage_end_ms` returns the range's START instead of its end       -> 5 fail
  * `_top_up_start_ms` returns the coverage-end instant instead of the
    first instant of its month (backfill would skip the part-month)      -> 2 fail
  * the clamp against today is dropped, so a cache reaching into next
    month never re-fetches the month still publishing its results        -> 1 fail
  * the exactly-one-of --from/--top-up guard is deleted                  -> 2 fail
  * `_coverage_is_current` calls an EMPTY cache current, turning the
    refusal into a silent skip                                           -> 1 fail
  * `_coverage_is_current` compares with > instead of >=                 -> 1 fail
  * the --if-stale/--top-up guard is deleted (that run went to the
    network, which is exactly what the guard is there to prevent)        -> 1 fail
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from news import EventStore, Impact, NewsEvent

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "backfill.py"


def _load_backfill():
    spec = importlib.util.spec_from_file_location("news_backfill_under_test", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


backfill = _load_backfill()


def _ms(y, m, d, hh=0, mm=0):
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)


def _store_covering(tmp_path, lo, hi):
    store = EventStore(tmp_path / "events.json")
    store.upsert(
        [NewsEvent(timestamp_ms=lo, currency="USD", impact=Impact.HIGH, title="X")],
        covered_ranges=[(lo, hi)],
    )
    return store


def test_coverage_end_ms_reports_the_latest_covered_instant(tmp_path):
    store = _store_covering(tmp_path, _ms(2026, 1, 1), _ms(2026, 7, 31, 23, 59))
    assert store.coverage_end_ms() == _ms(2026, 7, 31, 23, 59)


def test_coverage_end_ms_is_none_on_an_empty_store(tmp_path):
    assert EventStore(tmp_path / "nope.json").coverage_end_ms() is None


def test_resumes_from_the_month_coverage_ends_in(tmp_path):
    """A cache ending mid-July resumes at 1 July, not at the 15th — the month is fetched whole."""
    store = _store_covering(tmp_path, _ms(2021, 1, 1), _ms(2026, 7, 15, 9, 30))
    assert backfill._top_up_start_ms(store, _ms(2026, 9, 1)) == _ms(2026, 7, 1)


def test_clamps_to_the_current_month(tmp_path):
    """Coverage already reaching into next month must still re-fetch THIS one.

    The current month is the one whose released figures are still filling in, so a top-up that
    started after it would freeze those rows at whatever they were on the day it was fetched.
    """
    store = _store_covering(tmp_path, _ms(2021, 1, 1), _ms(2026, 10, 31, 23, 59))
    assert backfill._top_up_start_ms(store, _ms(2026, 9, 12)) == _ms(2026, 9, 1)


def test_refuses_rather_than_guessing_a_start_date_on_an_empty_cache(tmp_path):
    """Rule: a default start date is a hardcode with better manners. None means REFUSE."""
    store = EventStore(tmp_path / "nope.json")
    assert backfill._top_up_start_ms(store, _ms(2026, 9, 1)) is None


@pytest.mark.parametrize("argv", [[], ["--from", "2026-08", "--top-up"]])
def test_exactly_one_of_from_or_top_up_is_required(argv):
    """Neither, or both, is a user error caught before any network call."""
    with pytest.raises(SystemExit) as exc:
        backfill.main(argv)
    assert exc.value.code == 2


def test_coverage_running_up_to_now_is_current(tmp_path):
    """Nothing to fetch, and the answer is reached without a network call."""
    store = _store_covering(tmp_path, _ms(2021, 1, 1), _ms(2026, 9, 30, 23, 59))
    assert backfill._coverage_is_current(store, _ms(2026, 9, 12)) is True


def test_coverage_stopping_before_now_is_not_current(tmp_path):
    """The banner's case: the cache ends last month, so the top-up must actually run."""
    store = _store_covering(tmp_path, _ms(2021, 1, 1), _ms(2026, 7, 31, 23, 59))
    assert backfill._coverage_is_current(store, _ms(2026, 9, 1)) is False


def test_coverage_ending_exactly_now_is_current(tmp_path):
    """The boundary is inclusive — an instant already covered is not a reason to re-fetch."""
    store = _store_covering(tmp_path, _ms(2021, 1, 1), _ms(2026, 9, 12))
    assert backfill._coverage_is_current(store, _ms(2026, 9, 12)) is True


def test_an_empty_cache_is_never_current(tmp_path):
    """Empty means everything is missing, so --if-stale must not turn the refusal into a skip."""
    store = EventStore(tmp_path / "nope.json")
    assert backfill._coverage_is_current(store, _ms(2026, 9, 1)) is False


def test_if_stale_is_meaningless_without_top_up():
    with pytest.raises(SystemExit) as exc:
        backfill.main(["--from", "2026-08", "--if-stale"])
    assert exc.value.code == 2
