"""The broker's tradeable universe — the grouping, and the three-state that guards it.

🔴 **WATCHED RED, and the map is RUN rather than reasoned** (see `/prove`). Each mutation below was
applied to `services/broker_symbols.py`, the suite re-run, and the failing test names recorded:

  `_clean_group`: strip any trailing dotted word (`\\.\\w+$`) ..... test_a_dotted_group_name_survives
  `classify`: check commodities before metals ................... test_every_group_on_the_live_terminal
  `classify`: fall back to "Other" instead of the broker label .. test_an_unrecognised_group_keeps_the_brokers_own_name
  `_shape`: treat every trade_mode as tradable .................. test_a_restricted_symbol_is_kept_and_marked
  `_unavailable`: return `[]` instead of `None` ................. test_an_unreachable_agent_is_not_an_empty_broker
  `universe`: cache on a constant key instead of the identity ... test_a_terminal_that_changed_account_is_refetched
  `_attached`: a missing `mt5_connected` reads as connected ..... test_a_status_that_never_mentions_the_connection
  `classify`: judge the outermost folder alone (as shipped) .... test_a_nested_folder_is_read_not_just_the_outermost_one
  `_group_segments`: drop the last segment unconditionally ..... test_a_flat_path_is_one_folder_not_a_bare_symbol
  `_group_segments`: keep the symbol leaf as a folder .......... test_the_symbol_itself_never_decides_the_class
  `classify`: try folders outermost-first instead of deepest ... test_the_deepest_folder_wins_because_it_is_the_most_specific

⚠ **The first row is the reason this file exists at all.** The trimmer that turns `Forex .p` into
`Forex` was written as "drop a trailing dotted word", which silently renamed PU Prime's `US.24H`
group — 62 round-the-clock share CFDs — to a category called `US`. Nothing failed. It produced a
plausible label that tells the reader nothing, which is the worse half of getting it wrong, and it
was caught by printing the real terminal's groups rather than by reading the regex.
"""

import pytest
from services import broker_symbols as bs


@pytest.fixture(autouse=True)
def _clean_cache():
    bs.clear_cache()
    yield
    bs.clear_cache()


# ── The grouping ───────────────────────────────────────────────────────────────

#: Every FOLDER PATH the attached PU Prime demo actually carries, read off the terminal
#: 2026-09-07 as `(path, symbol, asset class)`.
#:
#: 🔴 **THESE WERE FLATTENED, AND THE FLATTENING HID A LIVE DEFECT FOR A DAY.** The first version
#: of this fixture wrote every group as a single folder plus a symbol — `247 Product\\SPCXUSD` —
#: while the terminal actually nests three deep: `247 Product\\Stocks\\US\\SPCXUSD`. The
#: classifier judged only the outermost folder, so 93 US and Asian shares were filed under a chip
#: called *247 Product* and were unreachable from *Shares*; **all 36 tests passed the whole time**,
#: because a two-segment fixture cannot exercise a bug that needs three.
#:
#: ⚠ **This repo's rule 13 is "a fixture more capable than production hides the defect". This is
#: the same rule from the other end: a fixture SIMPLER than production hides it just as well**, and
#: is harder to notice, because nothing about a tidy path looks like a claim.
LIVE_PATHS = [
    ("Forex .p", "AUDCAD.p", "Forex"),
    ("Forex", "EURUSD", "Forex"),
    ("Gold .p", "XAUUSD.p", "Metals"),
    ("Silver .p", "XAGUSD.p", "Metals"),
    ("Oil.p", "CL-OIL.p", "Energy"),
    ("Commodities.s", "COPPER-Cs", "Commodities"),
    ("Indices", "FRA40ft", "Indices"),
    ("Indices-JP.s", "Nikkei225.s", "Indices"),
    ("Equity-US", "AAPL", "Shares"),
    ("Equity-EU", "DHL", "Shares"),
    ("Equity-UK", "ABDN", "Shares"),
    ("ETFs\\ETF-C", "ARKG", "ETFs"),
    ("ETFs\\ETF-R", "BITQ", "ETFs"),
    ("ETFs\\ETFs-Crypto", "ARKB", "ETFs"),
    ("Cryptos", "BCHUSD", "Crypto"),
    ("Bonds", "EURIBOR3M", "Bonds"),
    ("247 Product\\Stocks\\US", "SPCXUSD", "Shares"),
    ("247 Product\\Stocks\\CN", "CXMTUSD", "Shares"),
    ("247 Product\\Stocks\\HK", "MINIMAXUSD", "Shares"),
    ("247 Product\\ETFs", "DRAMUSD", "ETFs"),
    ("US.24H", "TSLA.24H", "US.24H"),
]


@pytest.mark.parametrize("folder,symbol,expected", LIVE_PATHS)
def test_every_group_on_the_live_terminal(folder, symbol, expected):
    assert bs.classify(f"{folder}\\{symbol}") == expected


def test_a_dotted_group_name_survives():
    """🔴 The regression this whole file was written around.

    `US.24H` is a GROUP NAME whose tail is not an account tier, and trimming it produces `US` — a
    category with no meaning that looks perfectly fine on screen. Only a one- or two-letter
    lowercase tail is a tier.
    """
    assert bs.classify("US.24H\\TSLA.24H") == "US.24H"
    assert bs.classify("Forex .p\\EURUSD.p") == "Forex"
    assert bs.classify("Commodities.s\\COPPER-Cs") == "Commodities"


def test_a_nested_folder_is_read_not_just_the_outermost_one():
    """🔴 93 instruments were unreachable from the chip that names them.

    `247 Product` states no asset class; the `Stocks` folder inside it does, and it was fetched
    every time and thrown away before the rules ran. A reader hunting Apple checked *Shares* and
    did not find it.
    """
    assert bs.classify("247 Product\\Stocks\\US\\AAPLUSD") == "Shares"
    assert bs.classify("247 Product\\ETFs\\SPYUSD") == "ETFs"


def test_the_deepest_folder_wins_because_it_is_the_most_specific():
    """Two folders in one path can each name a class. The inner one is the finer answer."""
    assert bs.classify("Commodities\\Precious Metals\\XAUUSD") == "Metals"
    assert bs.classify("Equity-US\\ETFs\\SPY") == "ETFs"


def test_the_symbol_itself_never_decides_the_class():
    """The last path segment is a SYMBOL, not a folder.

    `Forex\\XAUUSD` is one broker filing gold in its forex book. Reading the leaf would answer
    Metals off the symbol's own spelling — a classification from the name rather than from
    anything the broker said.
    """
    assert bs.classify("Forex\\XAUUSD") == "Forex"
    assert bs.classify("Equity-US\\GOLDMAN") == "Shares"


def test_a_flat_path_is_one_folder_not_a_bare_symbol():
    """Dropping the last segment unconditionally would leave nothing to classify."""
    assert bs.classify("Cryptos") == "Crypto"
    assert bs.classify("Bonds") == "Bonds"


def test_an_unrecognised_group_keeps_the_brokers_own_name():
    """A group the broker gives no type for keeps its own label, and must not merge with another.

    ⚠ **`US.24H` is the live case and is NOT a classification failure to patch by hand.** Its 62
    symbols sit flat under that one folder — no sub-folder, no type word anywhere in the path — so
    the broker states nothing, and its own label at least tells the reader it is a round-the-clock
    book. An invented class would be a guess wearing a measurement's clothes.
    """
    assert bs.classify("US.24H\\TSLA.24H") == "US.24H"
    assert bs.classify("Tokenised\\X") == "Tokenised"
    assert bs.classify("US.24H\\Y") != bs.classify("Tokenised\\Z")


def test_a_symbol_with_no_path_is_ungrouped_not_blank():
    assert bs.classify("") == "Ungrouped"


def test_metals_win_over_commodities_because_the_more_specific_answer_is_more_useful():
    """A broker filing gold under "Precious Metals - Commodities" says both. Order decides."""
    assert bs.classify("Precious Metals Commodities\\XAUUSD") == "Metals"


def test_a_short_key_is_matched_as_a_word_not_a_substring():
    """`fx` inside a longer word is not a currency group."""
    assert bs.classify("FX Majors\\EURUSD") == "Forex"
    assert bs.classify("Effects\\WEIRD") == "Effects"


# ── The universe, and the three-state ──────────────────────────────────────────


def _agent(monkeypatch, *, status=None, symbols=None, status_exc=None, symbols_exc=None):
    def _status():
        if status_exc:
            raise status_exc
        return status

    def _symbols(tradable_only=False):
        if symbols_exc:
            raise symbols_exc
        return symbols

    monkeypatch.setattr(bs.mt5_agent_client, "status", _status)
    monkeypatch.setattr(bs.mt5_agent_client, "symbols", _symbols)


CONNECTED = {"mt5_connected": True, "server": "PUPrime-Demo", "account": 700152905}


def _raw(symbol, path, mode=4, desc=""):
    return {
        "symbol": symbol,
        "path": path,
        "description": desc,
        "trade_mode": mode,
        "trade_mode_label": {4: "full", 0: "disabled", 3: "close only"}.get(mode, "?"),
        "digits": 5,
        "contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "volume_max": 100.0,
    }


def test_an_unreachable_agent_is_not_an_empty_broker(monkeypatch):
    """🔴 Rule 1, in the place it would hurt most.

    An empty list renders as "this broker offers nothing", which is a product statement about a
    network failure. `symbols` must be None so a caller CANNOT accidentally render it as a list.
    """
    _agent(monkeypatch, status_exc=RuntimeError("MT5 agent /status: connection refused"))
    out = bs.universe()
    assert out["available"] is False
    assert out["symbols"] is None
    assert out["count"] is None
    assert "connection refused" in out["reason"]


def test_a_disconnected_terminal_cannot_be_asked(monkeypatch):
    """The agent answers happily while the terminal behind it is logged out — a different fact."""
    _agent(monkeypatch, status={"mt5_connected": False, "error": "terminal not logged in"})
    out = bs.universe()
    assert out["available"] is False
    assert out["symbols"] is None
    assert "logged in" in out["reason"]


def test_a_status_that_never_mentions_the_connection_cannot_be_asked(monkeypatch):
    """🔴 Written because a mutation SURVIVED the first version of this file.

    `test_a_disconnected_terminal_cannot_be_asked` passes an explicit `False`, which `is False` and
    `is not True` both catch — so the two readings were indistinguishable and the suite was green
    either way. The case that separates them is a status dict with the key MISSING: the agent
    answered, and it did not say. That is "cannot tell", and rule 1 is that it must never take the
    same value as "connected".
    """
    _agent(monkeypatch, status={"server": "PUPrime-Demo", "account": 1})
    out = bs.universe()
    assert out["available"] is False
    assert out["symbols"] is None


def test_a_terminal_that_cannot_name_its_server_cannot_be_asked(monkeypatch):
    """A blank server would key the cache identically for every outage — see `_attached`."""
    _agent(monkeypatch, status={"mt5_connected": True, "server": "", "account": 1})
    assert bs.universe()["available"] is False


def test_a_terminal_returning_no_list_is_not_a_broker_with_no_symbols(monkeypatch):
    _agent(monkeypatch, status=CONNECTED, symbols={"symbols": None})
    out = bs.universe()
    assert out["available"] is False
    assert out["symbols"] is None


def test_a_healthy_pull_names_the_terminal_it_was_read_from(monkeypatch):
    """Rule 3. Only one terminal is attached, so the list must say which one it describes."""
    _agent(
        monkeypatch,
        status=CONNECTED,
        symbols={"symbols": [_raw("EURUSD.p", "Forex .p\\EURUSD.p")], "total_on_terminal": 1},
    )
    out = bs.universe()
    assert out["available"] is True
    assert out["server"] == "PUPrime-Demo"
    assert out["account"] == 700152905
    assert out["count"] == 1


def test_a_restricted_symbol_is_kept_and_marked(monkeypatch):
    """A restriction on the ACCOUNT is not a statement about the instrument's HISTORY.

    59 of the live terminal's 1,085 are disabled, close-only or long-only — including its entire
    bare forex group. They stay listed because they are still replayable, and they say what they
    are rather than being silently dropped.
    """
    _agent(
        monkeypatch,
        status=CONNECTED,
        symbols={
            "symbols": [
                _raw("EURUSD", "Forex\\EURUSD", mode=0),
                _raw("EURUSD.p", "Forex .p\\EURUSD.p", mode=4),
            ],
            "total_on_terminal": 2,
        },
    )
    out = bs.universe()
    assert out["count"] == 2
    by = {s["symbol"]: s for s in out["symbols"]}
    assert by["EURUSD"]["tradable"] is False
    assert by["EURUSD"]["trade_mode_label"] == "disabled"
    assert by["EURUSD.p"]["tradable"] is True


def test_classes_are_counted_and_ordered_liquid_first(monkeypatch):
    """667 share names must not sit between the reader and gold."""
    _agent(
        monkeypatch,
        status=CONNECTED,
        symbols={
            "symbols": [
                _raw("AAPL", "Equity-US\\AAPL"),
                _raw("XAUUSD.p", "Gold .p\\XAUUSD.p"),
                _raw("EURUSD.p", "Forex .p\\EURUSD.p"),
                _raw("SPCXUSD", "247 Product\\SPCXUSD"),
            ],
            "total_on_terminal": 4,
        },
    )
    labels = [c["label"] for c in bs.universe()["classes"]]
    assert labels == ["Forex", "Metals", "Shares", "247 Product"]


def test_the_venue_lot_ceiling_travels_with_the_symbol(monkeypatch):
    """Rule 17's number is part of what a run is measured on, so it is served, not looked up."""
    _agent(
        monkeypatch,
        status=CONNECTED,
        symbols={"symbols": [_raw("XAUUSD.p", "Gold .p\\XAUUSD.p")], "total_on_terminal": 1},
    )
    assert bs.universe()["symbols"][0]["volume_max"] == 100.0


def test_a_terminal_that_changed_account_is_refetched(monkeypatch):
    """🔴 Rule 16: a startup check establishes a fact that is then free to change.

    The terminal has already switched accounts under a running bot once here. A universe cached
    against a constant key would keep serving the previous broker's instruments under the new
    account's name — every symbol plausible, none of them checked.
    """
    calls = {"n": 0}
    state = {"status": dict(CONNECTED)}

    def _status():
        return state["status"]

    def _symbols(tradable_only=False):
        calls["n"] += 1
        return {"symbols": [_raw("EURUSD.p", "Forex .p\\EURUSD.p")], "total_on_terminal": 1}

    monkeypatch.setattr(bs.mt5_agent_client, "status", _status)
    monkeypatch.setattr(bs.mt5_agent_client, "symbols", _symbols)

    bs.universe()
    bs.universe()
    assert calls["n"] == 1, "the second call must be served from cache"

    state["status"] = {"mt5_connected": True, "server": "VantageMarkets-Demo", "account": 42}
    out = bs.universe()
    assert calls["n"] == 2, "a different terminal must not be served the previous one's universe"
    assert out["server"] == "VantageMarkets-Demo"


# ── The blip, and the list we already hold ────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """The retry's sleep is real; the tests must not pay for it."""
    monkeypatch.setattr(bs, "_PROBE_BACKOFF_S", 0)


def test_a_dropped_request_is_asked_again_before_the_terminal_is_written_off(monkeypatch):
    """🔴 Reported from the screen 2026-09-07 over a terminal that was connected the whole time.

    The tunnel drops a single request now and then — an immediate "Remote end closed connection
    without response", not a timeout — and with one attempt that blip was indistinguishable from a
    dead terminal. The same terminal answered 30 probes out of 30 a minute later.
    """
    calls = {"n": 0}

    def _status():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("MT5 agent /status: Remote end closed connection without response")
        return CONNECTED

    monkeypatch.setattr(bs.mt5_agent_client, "status", _status)
    monkeypatch.setattr(
        bs.mt5_agent_client,
        "symbols",
        lambda tradable_only=False: {
            "symbols": [_raw("XAUUSD.p", "Gold .p\\XAUUSD.p")],
            "total_on_terminal": 1,
        },
    )
    out = bs.universe()
    assert out["available"] is True
    assert calls["n"] == 2


def test_a_terminal_saying_it_is_disconnected_is_NOT_asked_twice(monkeypatch):
    """That is a real answer, and asking again is just being slower about believing it.

    Only a TRANSPORT failure is worth a second ask.
    """
    calls = {"n": 0}

    def _status():
        calls["n"] += 1
        return {"mt5_connected": False, "error": "terminal not logged in"}

    monkeypatch.setattr(bs.mt5_agent_client, "status", _status)
    assert bs.universe()["available"] is False
    assert calls["n"] == 1


def test_a_blip_serves_the_list_we_already_hold_rather_than_a_blank_panel(monkeypatch):
    """🔴 THE DEFECT THIS FIXES: 1,085 instruments read seconds earlier were thrown away.

    The identity check runs before the cache is consulted — it has to, because the terminal can
    switch accounts underneath us — and the first version RETURNED at that point. So one dropped
    request told the reader the broker could not be reached, on a terminal that was connected.
    """
    state = {"up": True}

    def _status():
        if not state["up"]:
            raise RuntimeError("MT5 agent /status: Remote end closed connection without response")
        return CONNECTED

    monkeypatch.setattr(bs.mt5_agent_client, "status", _status)
    monkeypatch.setattr(
        bs.mt5_agent_client,
        "symbols",
        lambda tradable_only=False: {
            "symbols": [_raw("XAUUSD.p", "Gold .p\\XAUUSD.p")],
            "total_on_terminal": 1,
        },
    )

    good = bs.universe()
    assert good["available"] is True and good["stale"] is False

    state["up"] = False
    out = bs.universe()
    assert out["symbols"] is not None, "the list we already hold beats a blank panel"
    assert out["available"] is True
    assert out["stale"] is True, "and it must never pass as a fresh read"
    assert "Remote end closed" in out["reason"]
    # ⚠ It still names the terminal it was READ FROM — that is what lets a reader notice the
    # account moved during the gap, which is the one real hazard of serving it at all.
    assert out["server"] == "PUPrime-Demo"
    assert out["account"] == 700152905
    assert out["fetched_at"]


def test_a_blip_with_NOTHING_held_is_still_a_refusal(monkeypatch):
    """No cache, no answer. The stale path must not invent a list it never read."""
    _agent(monkeypatch, status_exc=RuntimeError("MT5 agent /status: connection refused"))
    out = bs.universe()
    assert out["available"] is False
    assert out["symbols"] is None
    assert out["stale"] is False


def test_refresh_skips_the_cache(monkeypatch):
    calls = {"n": 0}

    def _symbols(tradable_only=False):
        calls["n"] += 1
        return {"symbols": [_raw("EURUSD.p", "Forex .p\\EURUSD.p")], "total_on_terminal": 1}

    monkeypatch.setattr(bs.mt5_agent_client, "status", lambda: CONNECTED)
    monkeypatch.setattr(bs.mt5_agent_client, "symbols", _symbols)

    bs.universe()
    bs.universe(refresh=True)
    assert calls["n"] == 2
