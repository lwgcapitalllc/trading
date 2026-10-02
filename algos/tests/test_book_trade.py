"""`algos/tools/book_trade.py` — book a trade the bot never closed, off the broker's own deals.

Built 2026-10-02 for T369292543: a re-entry that only existed because of a restart bug, which the
live SOS Fade bot halted on and Aaron closed by hand. Each refusal below is asserted BY NAME —
`test_close_orphans.py` records why asserting merely that *something* refused is vacuous.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
TICKET = 369292543
OPENED = {
    "kind": "trade",
    "event": "opened",
    "ticket": TICKET,
    "dir": "bullish",
    "symbol": "XAUUSD.p",
    "intent": "secondary",
    "lots": 0.18,
    "price": 4152.53,
    "intended_price": 4159.79,
    "risk_usd": 128.34,
}


class FakeMT5:
    def __init__(self, open_now=False, deals=None):
        self._open = open_now
        self._deals = (
            deals
            if deals is not None
            else (
                SimpleNamespace(entry=0, price=4152.53, profit=0.0, swap=0.0, commission=-1.26),
                SimpleNamespace(entry=1, price=4152.80, profit=4.86, swap=0.0, commission=0.0),
            )
        )

    def initialize(self, path=None):
        return True

    def shutdown(self):
        pass

    def account_info(self):
        return SimpleNamespace(login=34957946, server="PUPrime-Live")

    def positions_get(self, ticket=None):
        return (SimpleNamespace(ticket=TICKET),) if self._open else ()

    def history_deals_get(self, position=None):
        return self._deals


@pytest.fixture
def tool(tmp_path, monkeypatch):
    def _load(fake, rows=(OPENED,)):
        monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
        monkeypatch.syspath_prepend(str(TOOLS))
        import close_orphans

        monkeypatch.setattr(close_orphans, "INSTANCES", tmp_path / "instances")
        spec = importlib.util.spec_from_file_location(
            "book_trade_under_test", TOOLS / "book_trade.py"
        )
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.co = close_orphans
        d = close_orphans.INSTANCES / "sos_fade_demo"
        (d / "ledger").mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text(json.dumps({"mt5_path": "X", "account": 34957946}))
        (d / "ledger" / "decisions-2026-10-02.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows)
        )
        return m

    return _load


def _run(m, monkeypatch, *extra):
    argv = ["book_trade.py", "--bot", "sos_fade_demo", "--ticket", str(TICKET), "--why", "bug"]
    monkeypatch.setattr(sys, "argv", argv + list(extra))
    try:
        m.main()
        return None
    except SystemExit as e:
        return str(e)


def _rows(m):
    d = m.co.INSTANCES / "sos_fade_demo" / "ledger"
    return [json.loads(x) for f in sorted(d.glob("*.jsonl")) for x in f.read_text().splitlines()]


def test_books_the_close_off_the_deals_and_marks_it_not_strategy(tool, monkeypatch):
    """MUTATION: net only the closing deal (drop the entry commission) -> pnl 4.86, red."""
    m = tool(FakeMT5())
    assert _run(m, monkeypatch, "--write", "--not-strategy") is None
    closed = [r for r in _rows(m) if r.get("event") == "closed"][0]
    assert closed["pnl_usd"] == pytest.approx(3.60)
    assert closed["price"] == 4152.80
    assert closed["r"] == pytest.approx(3.60 / 128.34)
    assert closed["intent"] == "secondary" and closed["reason"] == "closed_by_you"
    mark = [r for r in _rows(m) if r.get("event") == "trade_not_strategy_performance"][0]
    assert mark["ticket"] == TICKET and mark["counts_as_strategy_performance"] is False


def test_is_read_only_without_write(tool, monkeypatch):
    m = tool(FakeMT5())
    assert _run(m, monkeypatch) is None
    assert [r.get("event") for r in _rows(m)] == ["opened"]


def test_refuses_a_ticket_with_no_opened_row(tool, monkeypatch):
    m = tool(FakeMT5(), rows=())
    assert "no 'opened' row" in _run(m, monkeypatch, "--write")


def test_refuses_to_book_twice(tool, monkeypatch):
    """MUTATION: drop the already-booked check -> a second closed row, red."""
    m = tool(FakeMT5(), rows=(OPENED, {**OPENED, "event": "closed"}))
    assert "already booked" in _run(m, monkeypatch, "--write")


def test_refuses_a_position_still_open(tool, monkeypatch):
    m = tool(FakeMT5(open_now=True))
    assert "still OPEN" in _run(m, monkeypatch, "--write")


def test_unreadable_deals_refuse_rather_than_book_a_zero(tool, monkeypatch):
    """Rule 1: no deals is *could not ask*, never a scratch. MUTATION: default net to 0 -> red."""
    m = tool(FakeMT5(deals=()))
    assert "could not be read" in _run(m, monkeypatch, "--write")
    assert [r.get("event") for r in _rows(m)] == ["opened"]
