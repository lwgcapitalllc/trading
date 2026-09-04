"""`algos/tools/close_orphans.py` — the recovery tool must not repeat the fault it recovers from.

**Every case here was watched RED by mutation**, and one of them was watched red only after it
was FIXED, which is the part worth recording:

| mutation | goes red |
|---|---|
| decide from the retcode instead of re-reading the account (`if rc != 10009`) | `test_timeout_that_landed_is_recorded_not_retried` |
| drop the keep-ticket guard (`if False:`) | `test_refuses_when_the_keep_ticket_is_not_open` |
| drop the account assertion | `test_refuses_a_terminal_on_another_account` |

⚠ **The keep-ticket case was VACUOUS on its first writing and passed against its own bug.** It
asserted only that *some* refusal happened, and with a bogus `--keep` the doomed count changes
from 4 to 5, so the CONFIRM-PHRASE check refuses first and the test was green either way. It now
asserts the refusal BY NAME. Without the guard the tool closes all five, including the position
the bot is managing — a bot left holding a ticket the broker does not have, which halts it
forever. **Assert the refusal you mean, not that something refused.**

The fake terminal deliberately models the incident's exact shape (`timeout_but_lands`): the reply
never comes back, and the broker acted anyway. A fixture that cannot produce that state cannot
test the only thing this tool is for.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "close_orphans.py"
KEEP = 345453758
PHRASE = "close 4 unmanaged positions on sos_fade_demo"


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC, ORDER_FILLING_FOK = 1, 2

    def __init__(self, login=700152905, positions=None, close_works=True, timeout_but_lands=False):
        self._login = login
        self._pos = list(positions or [])
        self._close_works = close_works
        self._timeout_but_lands = timeout_but_lands
        self.sends = []

    def initialize(self, path=None):
        return True

    def shutdown(self):
        pass

    def last_error(self):
        return (1, "Success")

    def account_info(self):
        return SimpleNamespace(
            login=self._login, server="PUPrime-Demo", balance=9995.01, equity=13441.54
        )

    def positions_get(self, symbol=None, ticket=None):
        return tuple(self._pos)

    def symbol_info_tick(self, sym):
        return SimpleNamespace(bid=4644.20, ask=4644.42)

    def order_send(self, req):
        self.sends.append(req)
        if self._timeout_but_lands:
            # The incident's exact shape: no reply came back, and the broker DID act.
            self._pos = [p for p in self._pos if p.ticket != req["position"]]
            return SimpleNamespace(retcode=10012, comment="Request timeout")
        if self._close_works:
            self._pos = [p for p in self._pos if p.ticket != req["position"]]
            return SimpleNamespace(retcode=10009, comment="Done")
        return SimpleNamespace(retcode=10004, comment="Requote")

    def history_deals_get(self, position=None):
        return (SimpleNamespace(profit=683.20, swap=13.07, commission=-0.80),)


def _pos(ticket, lots, stop):
    return SimpleNamespace(
        ticket=ticket,
        type=1,
        volume=lots,
        price_open=4661.5,
        sl=stop,
        price_current=4644.42,
        profit=683.20,
        swap=13.07,
        magic=770115,
        time=1787695818,
        symbol="XAUUSD.p",
    )


def _five():
    return [
        _pos(KEEP, 0.39, 4686.74),
        _pos(345454163, 0.39, 4686.74),
        _pos(345455484, 0.40, 4686.32),
        _pos(345456052, 0.40, 4686.32),
        _pos(345483451, 0.40, 4686.32),
    ]


@pytest.fixture
def tool(tmp_path, monkeypatch):
    """Load the tool against a fake terminal and a throwaway instance dir.

    `INSTANCES` is redirected at `tmp_path` so a test can never append to the real bot's ledger —
    and so the suite stays parallel-safe, which a fixed path would break.
    """

    def _load(fake):
        monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
        spec = importlib.util.spec_from_file_location("close_orphans_under_test", TOOL)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.INSTANCES = tmp_path / "instances"
        d = m.INSTANCES / "sos_fade_demo"
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text(
            json.dumps(
                {"mt5_path": "X", "account": 700152905, "symbol": "XAUUSD.p", "magic": 770115}
            )
        )
        return m

    return _load


def _run(m, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["close_orphans.py"] + argv)
    try:
        m.main()
        return None
    except SystemExit as e:
        return str(e)


def _rows(m):
    d = m.INSTANCES / "sos_fade_demo" / "ledger"
    out = []
    for f in sorted(d.glob("*.jsonl")):
        out += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return out


def test_refuses_a_terminal_on_another_account(tool, monkeypatch):
    """Rule 16: a startup check establishes a fact that is then free to change. The terminal
    switched accounts under a running bot here once already."""
    f = FakeMT5(login=700107749, positions=_five())
    out = _run(
        tool(f),
        ["--bot", "sos_fade_demo", "--keep", str(KEEP), "--close", "--confirm", PHRASE],
        monkeypatch,
    )
    assert out and "WRONG TERMINAL" in out
    assert f.sends == []


def test_refuses_when_the_keep_ticket_is_not_open(tool, monkeypatch):
    """Without this the tool closes EVERY position, the bot's own included, and the bot is then
    holding a ticket the broker does not have — which halts it permanently.

    Note the confirm phrase says FIVE: with a bogus keep nothing is kept, so a phrase saying four
    would be refused for the wrong reason and this test would pass against its own bug.
    """
    f = FakeMT5(positions=_five())
    out = _run(
        tool(f),
        [
            "--bot",
            "sos_fade_demo",
            "--keep",
            "999",
            "--close",
            "--confirm",
            "close 5 unmanaged positions on sos_fade_demo",
        ],
        monkeypatch,
    )
    assert out and "is not open under this magic" in out
    assert f.sends == []


def test_refuses_a_wrong_confirm_phrase(tool, monkeypatch):
    f = FakeMT5(positions=_five())
    out = _run(
        tool(f),
        ["--bot", "sos_fade_demo", "--keep", str(KEEP), "--close", "--confirm", "yes"],
        monkeypatch,
    )
    assert out and "REFUSING" in out
    assert f.sends == []


def test_is_read_only_without_close(tool, monkeypatch):
    f = FakeMT5(positions=_five())
    _run(tool(f), ["--bot", "sos_fade_demo", "--keep", str(KEEP)], monkeypatch)
    assert f.sends == []


def test_closes_the_others_and_marks_them_as_not_performance(tool, monkeypatch):
    f = FakeMT5(positions=_five())
    m = tool(f)
    _run(
        m,
        [
            "--bot",
            "sos_fade_demo",
            "--keep",
            str(KEEP),
            "--close",
            "--confirm",
            PHRASE,
            "--why",
            "duplicate orders from a broker timeout",
        ],
        monkeypatch,
    )
    assert len(f.sends) == 4
    assert {p.ticket for p in f._pos} == {KEEP}
    marked = [r for r in _rows(m) if r.get("event") == "unmanaged_position_closed"]
    assert len(marked) == 4
    # The flag is the entire point of the tool: these tickets live in the broker's deal history
    # forever, and anything totalling the account will find them.
    assert all(r["counts_as_strategy_performance"] is False for r in marked)
    assert KEEP not in {r["ticket"] for r in marked}
    incident = [r for r in _rows(m) if r.get("event") == "unmanaged_positions_incident"]
    assert len(incident) == 1 and incident[0]["kept_ticket"] == KEEP


def test_timeout_that_landed_is_recorded_not_retried(tool, monkeypatch):
    """🔴 THE ONE THAT MATTERS. A close whose reply never came back, but which the broker
    honoured, must be read off the ACCOUNT and recorded as closed. Deciding from the return code
    is precisely what turned one order into five positions."""
    f = FakeMT5(positions=_five(), timeout_but_lands=True)
    m = tool(f)
    _run(
        m,
        ["--bot", "sos_fade_demo", "--keep", str(KEEP), "--close", "--confirm", PHRASE],
        monkeypatch,
    )
    assert len(f.sends) == 4, "it re-sent on a timeout, which IS the incident"
    assert len([r for r in _rows(m) if r.get("event") == "unmanaged_position_closed"]) == 4
    assert {p.ticket for p in f._pos} == {KEEP}


def test_a_close_that_really_failed_is_reported_and_not_retried(tool, monkeypatch):
    f = FakeMT5(positions=_five(), close_works=False)
    m = tool(f)
    _run(
        m,
        ["--bot", "sos_fade_demo", "--keep", str(KEEP), "--close", "--confirm", PHRASE],
        monkeypatch,
    )
    assert len(f.sends) == 4 and len(f._pos) == 5
    assert [r for r in _rows(m) if r.get("event") == "unmanaged_position_closed"] == []
