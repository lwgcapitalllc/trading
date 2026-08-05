"""
test_calendar.py — the live News Calendar tab's data layer.

The interesting half of this file is `test_no_polarity_key_is_dead`. `_LOWER_IS_BETTER` is a claim
about ONE provider's vocabulary, and until 2026-08-05 nothing checked it: the list had been written
against Forex Factory's naming while the tab reads TradingView, so six of its eleven keys matched
nothing at all and `Core PCE Price Index MoM` — HIGH impact, USD — was coloured the opposite way to
CPI on the same screen. A dead key is silent by construction, so it needs a test that fails the
build rather than a reader who happens to notice.

`fixtures/tradingview_titles.txt` is 811 real event titles harvested over ~275 days of the live
feed. It is the vocabulary the list is matched against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services import calendar_service as cal

_FIXTURE = Path(__file__).parent / "fixtures" / "tradingview_titles.txt"


def _corpus() -> list[tuple[str, str, str]]:
    """[(impact, currency, title)] from the harvested fixture."""
    rows = []
    for line in _FIXTURE.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        impact, currency, title = line.split("\t", 2)
        rows.append((impact, currency, title))
    return rows


def _titles() -> list[str]:
    return [t for _, _, t in _corpus()]


# ── The dead-key guard ──────────────────────────────────────────────────────────


def test_the_fixture_is_a_real_corpus():
    """If this shrinks to a handful of rows the guard below stops meaning anything."""
    assert len(_titles()) > 500


@pytest.mark.parametrize("key", cal._LOWER_IS_BETTER)
def test_no_polarity_key_is_dead(key):
    """Every key must match at least one REAL title.

    A key that matches nothing is not harmless — it is the shape the whole defect took. It reads as
    coverage ("we handle jobless claims") while the events it was meant to cover fall through to the
    default. If this fails, the feed renamed something: find what it calls the event now, do not
    delete the test.
    """
    matches = [t for t in _titles() if cal._lower_is_better(t) and _matches_only(key, t)]
    assert matches, f"polarity key {key!r} matches nothing in the real corpus"


def _matches_only(key: str, title: str) -> bool:
    import re

    return re.search(r"\b" + re.escape(key), title.lower()) is not None


# ── The specific prints that were wrong ─────────────────────────────────────────


@pytest.mark.parametrize(
    "title",
    [
        "Core PCE Price Index MoM",   # HIGH impact USD — the one that was backwards
        "Core PCE Price Index YoY",
        "PCE Price Index MoM",
        "PCE Prices QoQ Adv",
        "Inflation Rate YoY",
        "Core Inflation Rate MoM",
        "CPI",
        "Tokyo Core CPI YoY",
        "PPI MoM",
        "Core PPI YoY",
        "Michigan Inflation Expectations Prel",
        "ECB Consumer Inflation Expectations",
        "ISM Manufacturing Prices",
        "ISM Services Prices",
        "Philly Fed Prices Paid",
        "Import Prices MoM",
        "Producer & Import Prices YoY",
        "Raw Materials Prices MoM",
        "Initial Jobless Claims",
        "Continuing Jobless Claims",
        "Unemployment Rate",
        "U-6 Unemployment Rate",
        "EIA Crude Oil Stocks Change",
        "EIA Natural Gas Stocks Change",
        "EIA Gasoline Stocks Change",
        "Business Inventories MoM",
        "Wholesale Inventories MoM",
        "Employment Cost Index QoQ",
        "Unit Labour Costs QoQ Prel",
        "Wage Price Index YoY",
    ],
)
def test_lower_is_better(title):
    assert cal._lower_is_better(title), f"{title} should be lower-is-better"


@pytest.mark.parametrize(
    "title",
    [
        "Non Farm Payrolls",
        "GDP Growth Rate QoQ Adv",
        "Retail Sales MoM",
        "ISM Manufacturing PMI",
        "Michigan Consumer Sentiment Prel",
        "Balance of Trade",
        "Building Permits",
        "Durable Goods Orders MoM",
        "Industrial Production YoY",
        "Fed Interest Rate Decision",
        "Housing Starts",
        "Personal Spending MoM",
    ],
)
def test_higher_is_better(title):
    assert not cal._lower_is_better(title), f"{title} should be higher-is-better"


def test_the_two_inflation_prints_agree_with_each_other():
    """The reported defect, stated as a test: a hot CPI and a hot PCE must colour the SAME.

    They sit rows apart in one table answering one question, and before 2026-08-05 a 0.4% actual
    against a 0.3% forecast printed red on CPI and green on Core PCE.
    """
    cpi = cal._surprise("CPI", "0.4%", "0.3%")
    pce = cal._surprise("Core PCE Price Index MoM", "0.4%", "0.3%")
    assert cpi == pce == "miss"

    cool_cpi = cal._surprise("CPI", "0.2%", "0.3%")
    cool_pce = cal._surprise("Core PCE Price Index MoM", "0.2%", "0.3%")
    assert cool_cpi == cool_pce == "beat"


# ── Word-boundary matching ──────────────────────────────────────────────────────


@pytest.mark.parametrize("title", ["Shipping Index", "Shopping Centre Sales", "Happiness Index"])
def test_a_substring_inside_a_word_does_not_match(title):
    """`ppi` used to be a bare substring, which matches "Shi-ppi-ng". Zero real titles hit it, so
    this was theory rather than a live bug — but the left word boundary costs nothing and the next
    key added to that list might not be so lucky."""
    assert not cal._lower_is_better(title)


# ── Number parsing ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2.6%", 2.6),
        ("-0.3%", -0.3),
        ("168K", 168.0),
        ("$-3.018", -3.018),
        ("C$1.25", 1.25),
        ("¥-1,234", -1234.0),
        ("1,750K", 1750.0),
        ("4.4", 4.4),
        ("", None),
        (None, None),
        ("n/a", None),
    ],
)
def test_num(raw, expected):
    assert cal._num(raw) == expected


def test_surprise_needs_both_sides():
    assert cal._surprise("CPI", None, "0.3%") is None
    assert cal._surprise("CPI", "0.4%", None) is None
    assert cal._surprise("CPI", "0.3%", "0.3%") == "inline"


# ── Window guards ───────────────────────────────────────────────────────────────


def test_iso_to_ms_accepts_z_offset_and_bare_date():
    assert cal.iso_to_ms("2026-08-05T00:00:00Z") == 1785888000000
    assert cal.iso_to_ms("2026-08-05T00:00:00+00:00") == 1785888000000
    assert cal.iso_to_ms("2026-08-05") == 1785888000000


def test_iso_to_ms_rejects_rubbish():
    with pytest.raises(ValueError):
        cal.iso_to_ms("last tuesday")


def test_backwards_window_is_a_value_error():
    with pytest.raises(ValueError):
        cal.get_calendar(from_ms=2_000, to_ms=1_000)


def test_absurd_window_is_a_value_error():
    with pytest.raises(ValueError):
        cal.get_calendar(from_ms=0, to_ms=cal._MAX_SPAN_MS + 1)


# ── Upstream failures are RuntimeError (→ 502), never ValueError (→ 400) ────────


def _blow_up(exc):
    class _Boom:
        def __init__(self, *a, **k):
            pass

        def fetch_window(self, *a, **k):
            raise exc

    return _Boom


@pytest.mark.parametrize(
    "exc",
    [
        __import__("json").JSONDecodeError("Expecting value", "", 0),  # an HTML error page
        TimeoutError("timed out"),                                     # a read timeout
        RuntimeError("TradingView calendar fetch failed"),             # what the source raises
        KeyError("result"),                                            # a shape change
    ],
)
def test_every_upstream_failure_is_a_runtime_error(monkeypatch, exc):
    """A ValueError escaping here becomes a 400 — "your request was malformed" for somebody else's
    outage. JSONDecodeError IS a ValueError, which is exactly how that used to happen."""
    monkeypatch.setattr(cal, "TradingViewSource", _blow_up(exc))
    cal._cache.clear()
    with pytest.raises(RuntimeError):
        cal.get_calendar(from_ms=0, to_ms=86_400_000)


# ── Cache ───────────────────────────────────────────────────────────────────────


def test_the_cache_is_bounded(monkeypatch):
    """Every week a reader pages to mints a key. Nothing used to remove one."""
    calls = {"n": 0}

    class _Fake:
        def __init__(self, *a, **k):
            pass

        def fetch_window(self, *a, **k):
            calls["n"] += 1

            class _R:
                events: list = []

            return _R()

    monkeypatch.setattr(cal, "TradingViewSource", _Fake)
    cal._cache.clear()
    for i in range(cal._CACHE_MAX * 3):
        cal._fetch_window_cached(i * 1000, i * 1000 + 500, ("US",))
    assert len(cal._cache) <= cal._CACHE_MAX
    assert calls["n"] == cal._CACHE_MAX * 3


def test_a_repeat_window_is_served_from_cache(monkeypatch):
    calls = {"n": 0}

    class _Fake:
        def __init__(self, *a, **k):
            pass

        def fetch_window(self, *a, **k):
            calls["n"] += 1

            class _R:
                events: list = []

            return _R()

    monkeypatch.setattr(cal, "TradingViewSource", _Fake)
    cal._cache.clear()
    cal._fetch_window_cached(0, 500, ("US",))
    cal._fetch_window_cached(0, 500, ("US",))
    assert calls["n"] == 1


# ── The currency roster ─────────────────────────────────────────────────────────
#
# The page's chips are DERIVED from this now rather than hand-copied beside it. The guard is the
# same shape as the dead-key test above: the build fails if the two namespaces drift, because the
# failure mode is otherwise invisible — a bloc with no mapping simply never gets a chip, and a
# currency that cannot be filtered looks exactly like a week that had no events for it.


def test_every_queried_country_maps_to_a_currency():
    unmapped = [c for c in cal.DEFAULT_COUNTRIES if c not in cal._COUNTRY_CURRENCY]
    assert not unmapped, (
        f"country codes with no currency: {unmapped}. Add them to _COUNTRY_CURRENCY — an "
        f"unmapped bloc falls back to its own code and renders a chip that matches no event."
    )


def test_the_roster_is_the_currencies_the_feed_actually_returns():
    """Measured, not asserted from the map: every currency on the chip row appears in the real
    corpus, and every currency in the corpus has a chip. A roster is a claim about the feed."""
    roster = set(cal.currencies_for())
    seen = {cur for _imp, cur, _title in _corpus()}
    assert not (seen - roster), f"the feed returns currencies with no chip: {sorted(seen - roster)}"
    assert not (roster - seen), f"chips for currencies the feed never returns: {sorted(roster - seen)}"


def test_the_roster_follows_the_query_not_a_constant():
    assert cal.currencies_for(("US", "JP")) == ["USD", "JPY"]
    assert cal.currencies_for(("gb",)) == ["GBP"]


def test_an_unmapped_code_is_visible_rather_than_dropped():
    # Silently narrowing the roster is the defect this replaced; falling back to the code itself
    # puts something odd on screen instead of nothing at all.
    assert cal.currencies_for(("US", "ZZ")) == ["USD", "ZZ"]


def test_the_roster_is_deduped_and_ordered():
    assert cal.currencies_for(("US", "US", "EU")) == ["USD", "EUR"]
