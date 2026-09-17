"""The account results view — `services/account_history.py` and `GET /bots/accounts/{n}/history`.

Every test here was WATCHED RED before it was trusted. The deal files do not exist anywhere yet
(the bot change that writes them is unpromoted), so no test can fail against an older version of
this code — each was proven by MUTATING the service in place, running the file, and restoring it.
The mutation that turned each one red is named in its docstring.

The fixture account (111) opens with a $10,000 deposit, takes a bot trade, receives a second
$5,000 deposit, takes a manual trade, and carries a CREDIT deal that must be ignored. Account 222
shares a deal ticket number space with it and must never leak in. Times are written on the
broker SERVER's clock (UTC+3 in September), exactly as MT5 books them.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from services import account_history as ah
from services import broker_clock

ACCOUNT = 111
OTHER = 222


def _server_ms(y, mo, d, h, mi=0) -> int:
    """A server wall-clock time written as though it were UTC — how MT5 stamps a deal."""
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def _utc_ms(y, mo, d, h, mi=0) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def _deal(
    ticket,
    when,
    *,
    type_,
    entry=0,
    pos=0,
    vol=0.0,
    price=0.0,
    profit=0.0,
    commission=0.0,
    swap=0.0,
    fee=0.0,
    account=ACCOUNT,
    bot="sos_fade_1",
    symbol="XAUUSD.p",
):
    return {
        "bot": bot,
        "kind": "deal",
        "account": account,
        "ticket": ticket,
        "order": ticket + 1000,
        "time": when // 1000,
        "time_msc": when,
        "type": type_,
        "entry": entry,
        "magic": 7,
        "position_id": pos,
        "reason": 3,
        "volume": vol,
        "price": price,
        "commission": commission,
        "swap": swap,
        "profit": profit,
        "fee": fee,
        "symbol": symbol,
        "comment": "",
        "external_id": "",
    }


def _deals(bot="sos_fade_1", account=ACCOUNT, offset=0):
    kw = {"bot": bot, "account": account}
    rows = [
        _deal(1, _server_ms(2026, 9, 1, 9), type_=2, profit=10_000.0, **kw),
        _deal(
            2,
            _server_ms(2026, 9, 1, 13) + 20_000,
            type_=0,
            entry=0,
            pos=500,
            vol=0.1,
            price=2000.0,
            commission=-0.5,
            **kw,
        ),
        _deal(
            3,
            _server_ms(2026, 9, 1, 15),
            type_=1,
            entry=1,
            pos=500,
            vol=0.1,
            price=2010.0,
            profit=100.0,
            commission=-0.5,
            **kw,
        ),
        _deal(4, _server_ms(2026, 9, 2, 9), type_=2, profit=5_000.0, **kw),
        _deal(
            5,
            _server_ms(2026, 9, 2, 13),
            type_=1,
            entry=0,
            pos=600,
            vol=0.2,
            price=2020.0,
            commission=-1.0,
            **kw,
        ),
        _deal(
            6,
            _server_ms(2026, 9, 2, 16),
            type_=0,
            entry=1,
            pos=600,
            vol=0.2,
            price=2030.0,
            profit=-200.0,
            swap=-3.0,
            commission=-1.0,
            **kw,
        ),
        _deal(7, _server_ms(2026, 9, 2, 17), type_=3, profit=999.0, **kw),
    ]
    for r in rows:
        r["ticket"] += offset
    return rows


# The bot's own record of trade 500: opened 5s after the entry deal's UTC time (10:00:20).
OPENED_500 = {
    "ts": "2026-09-01T10:00:25+00:00",
    "bot": "sos_fade_1",
    "kind": "trade",
    "event": "opened",
    "ticket": 500,
    "dir": "LONG",
    "price": 2000.0,
    "stop": 1990.0,
    "tp1": 2030.0,
    "tp2": 0.0,
    "lots": 0.1,
    "risk_usd": 100.0,
}


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


@pytest.fixture
def archive(tmp_path):
    """Two bots on account 111, both holding the SAME history, and a third on account 222."""
    root = tmp_path / "ledger_archive"
    _write(root / "sos_fade_1/ledger/deals-2026-09-01.jsonl", _deals("sos_fade_1")[:3])
    _write(root / "sos_fade_1/ledger/deals-2026-09-02.jsonl", _deals("sos_fade_1")[3:])
    _write(root / "extreme_leg_1/ledger/deals-2026-09-01.jsonl", _deals("extreme_leg_1"))
    _write(root / "other/ledger/deals-2026-09-01.jsonl", _deals("other", account=OTHER, offset=100))
    _write(
        root / "sos_fade_1/ledger/decisions-2026-09-01.jsonl",
        [{"ts": "2026-09-01T09:00:00+00:00", "kind": "bar"}, OPENED_500],
    )
    return root


def _bars(tf, *_):
    if tf == "M1":
        return (
            [
                {
                    "time": _utc_ms(2026, 9, 1, 9, 59),
                    "open": 1,
                    "high": 2500.0,
                    "low": 1500.0,
                    "close": 1,
                },
                # Straddles the 10:00:20 entry, so it holds prices from before it — never counts.
                {
                    "time": _utc_ms(2026, 9, 1, 10, 0),
                    "open": 1,
                    "high": 2400.0,
                    "low": 1600.0,
                    "close": 1,
                },
                {
                    "time": _utc_ms(2026, 9, 1, 10, 30),
                    "open": 2001,
                    "high": 2012.0,
                    "low": 1995.0,
                    "close": 2005,
                },
                {
                    "time": _utc_ms(2026, 9, 1, 11, 59),
                    "open": 2008,
                    "high": 2011.0,
                    "low": 2007.0,
                    "close": 2010,
                },
                # Opens AT the exit, so it holds prices from after it — must never count.
                {
                    "time": _utc_ms(2026, 9, 1, 12, 0),
                    "open": 2010,
                    "high": 2100.0,
                    "low": 1900.0,
                    "close": 2010,
                },
            ],
            None,
            "PUPrime-Demo",
        )
    return (
        [{"time": _utc_ms(2026, 9, 1, 0), "open": 1, "high": 2, "low": 0.5, "close": 1.5}],
        None,
        "PUPrime-Demo",
    )


def _loader(symbol, tf, start, end):
    return _bars(tf)


def _build(archive_root, *, box=None, box_error="ssh refused", loader=_loader, contract_size=100.0):
    return ah.build_history(
        ACCOUNT,
        box=box,
        box_error=box_error,
        archive=ah.read_archive(archive_root),
        contract_size=contract_size,
        load_bars=loader,
        now_ms=0,
    )


def test_two_bots_writing_the_same_history_count_each_deal_once(archive):
    """RED when `account_deals` stopped de-duplicating (every row kept): the two bot folders
    doubled every deal — fourteen counted, and the balance read twice itself."""
    out = _build(archive)
    assert out["deal_count"] == 7
    assert len(out["equity"]) == 2
    assert out["balance"] == pytest.approx(14_894.0)


def test_rows_read_on_another_account_never_reach_this_one(archive):
    """RED when the account filter was removed from `account_deals`: account 222's seven deals
    (their own tickets) joined this account's, doubling the capital and the trades."""
    out = _build(archive)
    assert out["deal_count"] == 7
    assert out["capital_in"] == pytest.approx(15_000.0)
    other = ah.build_history(
        OTHER,
        box=None,
        box_error="x",
        archive=ah.read_archive(archive),
        contract_size=100.0,
        load_bars=None,
        now_ms=0,
    )
    assert other["deal_count"] == 7


def test_a_deposit_is_a_marker_and_never_a_profit(archive):
    """RED when nothing counted as money moved (FLOW_TYPES emptied): both deposits fell into the
    balance adjustments, no flow was listed, and the capital put in read $0."""
    out = _build(archive)
    assert out["capital_in"] == pytest.approx(15_000.0)
    assert out["trading_pnl"] == pytest.approx(-106.0)
    assert [f["amount"] for f in out["flows"]] == [10_000.0, 5_000.0]
    assert sum(p["profit"] for p in out["equity"]) == pytest.approx(-106.0)
    # Growth with the deposit taken out: +0.99% then −205 on 15,099.
    assert out["twr_pct"] == pytest.approx((1.0099 * 14_894 / 15_099 - 1) * 100, abs=1e-3)


def test_the_rebuilt_balance_reconciles_and_credit_is_ignored(archive):
    """RED when CREDIT was counted as money (the `continue` on DEAL_CREDIT removed): the balance
    rebuilt to 15,893 and `reconciled` went False, because the credit is in no bucket."""
    out = _build(archive)
    every = ah.account_deals(ah.read_archive(archive)[0], ACCOUNT)
    direct = sum(ah._money(d) for d in every if d["type"] != ah.DEAL_CREDIT)
    assert out["balance"] == pytest.approx(direct)
    assert out["reconciled"] is True
    assert out["capital_in"] + out["trading_pnl"] + out["adjustments_total"] + out[
        "open_position_costs"
    ] == pytest.approx(out["balance"])


def test_a_zero_target_is_no_target(archive):
    """RED when `_target` returned the raw float: the chart then carried a target at price 0.0.
    ⚠ It SURVIVED that mutation at first — the list that collects the targets also dropped falsy
    values, so two places decided one thing. The collector now keeps anything `_target` returns."""
    out = _build(archive)
    bot_trade = next(t for t in out["chart"]["trades"] if t["id"] == "500")
    assert bot_trade["stopPrice"] == 1990.0
    assert bot_trade["tpTargets"] == [{"price": 2030.0, "banks": True}]


def test_a_manual_trade_has_no_stop_and_no_r(archive):
    """RED when `r_multiple` returned 0.0 for a missing stop: the manual trade's R read 0."""
    out = _build(archive)
    manual = next(t for t in out["chart"]["trades"] if t["id"] == "600")
    assert "stopPrice" not in manual and manual["tag"] == "Manual"
    rs = {p["index"]: p["r"] for p in out["equity"]}
    assert rs[1] == pytest.approx(0.99)  # (100 − 1) / the bot's own $100 risk
    assert rs[2] is None
    assert out["manual_trades"] == 1


def test_a_dead_box_falls_back_to_the_archive_and_says_so(archive):
    """RED when the fallback note was dropped (`source_note` forced to None): the archive's answer
    then looked exactly like a live one."""
    out = _build(archive, box=None, box_error="Connection refused")
    assert out["source"] == "archive"
    assert (
        "could not be reached" in out["source_note"] and "Connection refused" in out["source_note"]
    )
    assert out["newest_deal_ms"] == broker_clock.server_ms_to_utc_ms(_server_ms(2026, 9, 2, 17))

    live = _build(archive, box=(_deals(), [OPENED_500]), box_error=None)
    assert live["source"] == "box" and live["source_note"] is None


def test_no_file_anywhere_is_an_explicit_empty_state(tmp_path):
    """RED when the empty branch was removed: `max()` of no deals raised instead of answering."""
    out = _build(tmp_path / "nothing", box=([], []), box_error=None)
    assert out["status"] == "no_history"
    assert out["source"] is None
    assert "no deal history" in out["reason"]
    assert "balance" not in out and "equity" not in out


def test_the_worst_and_best_price_stop_at_the_exit(archive):
    """RED when the upper bound was dropped (the 12:00 bar's 2100/1900, after the exit, came in),
    and RED when any OVERLAPPING bar was kept (the 10:00 bar straddling the 10:00:20 entry read
    2400/1600). ⚠ The second SURVIVED at first: the entry sat exactly on a minute, so no bar could
    straddle it. The entry now lands 20s into its minute."""
    out = _build(archive)
    trade = next(t for t in out["chart"]["trades"] if t["id"] == "500")
    assert trade["maePrice"] == 1995.0
    assert trade["mfePrice"] == 2012.0
    # $ excursions ride the equity point: (2012 − 2000) × 0.1 × 100.
    first = out["equity"][0]
    assert first["favorable"] == pytest.approx(120.0)
    assert first["adverse"] == pytest.approx(-50.0)


def test_deal_times_are_converted_off_the_server_clock(archive):
    """RED when `deal_utc_ms` returned the server time unchanged: every trade sat 3h late."""
    out = _build(archive)
    trade = next(t for t in out["chart"]["trades"] if t["id"] == "500")
    assert trade["entryTime"] == _utc_ms(2026, 9, 1, 10) + 20_000
    assert trade["exitTime"] == _utc_ms(2026, 9, 1, 12)


def test_an_opened_record_far_from_the_entry_is_not_this_trade(archive):
    """RED when the match window was ignored: a record a day away gave trade 500 its stop."""
    far = dict(OPENED_500, ts="2026-09-03T10:00:00+00:00")
    out = _build(archive.parent / "empty", box=(_deals(), [far]), box_error=None)
    trade = next(t for t in out["chart"]["trades"] if t["id"] == "500")
    assert "stopPrice" not in trade
    assert out["unmatched_plans"] == 1


# ── The route ──────────────────────────────────────────────────────────────────────────────


def test_the_route_reads_the_box_and_falls_back_when_it_is_down(client, archive, monkeypatch):
    """RED when `_read_box_history` ignored the marker check: a reply with no marker was read as
    the box answering, so the page claimed a live source it never had."""
    from routers import bots

    monkeypatch.setattr(ah, "ARCHIVE", archive)
    monkeypatch.setattr(ah.read_archive, "__defaults__", (archive,))
    monkeypatch.setattr(ah, "bar_loader", lambda server: _loader)
    monkeypatch.setattr(bots, "_history_sources", lambda account: ("PUPrime-Demo", 100.0))
    ah._cache.clear()

    monkeypatch.setattr(bots, "_ssh", lambda cmd: "")
    body = client.get(f"/bots/accounts/{ACCOUNT}/history").json()
    assert body["source"] == "archive"
    assert "marker" in body["source_note"]

    raw = (
        ah.BOX_MARKER
        + "\n"
        + "\n".join(
            r"C:\trading\x\ledger\deals-2026-09-01.jsonl:" + json.dumps(d) for d in _deals()
        )
    )
    monkeypatch.setattr(bots, "_ssh", lambda cmd: raw)
    body = client.get(f"/bots/accounts/{ACCOUNT}/history?refresh=true").json()
    assert body["source"] == "box"
    assert body["equity"][0]["twr_equity"] == pytest.approx(10_099.0)
    assert body["chart"]["trades"][0]["pnl"] == pytest.approx(99.0)

    def down(cmd):
        raise bots.VpsUnreachable("Connection timed out")

    monkeypatch.setattr(bots, "_ssh", down)
    body = client.get(f"/bots/accounts/{ACCOUNT}/history?refresh=true").json()
    assert body["source"] == "archive" and "Connection timed out" in body["box_error"]
    ah._cache.clear()


# ── The clock rule is a MIRROR, and this is what keeps it one ──────────────────────────────


def _algos_clock():
    path = (
        Path(__file__).resolve().parents[3]
        / "algos"
        / "markets"
        / "fx"
        / "tools"
        / "broker_clock.py"
    )
    spec = importlib.util.spec_from_file_location("_algos_broker_clock", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_server_clock_mirror_agrees_with_the_bots_rule_every_hour():
    """RED when this file's summer-time start moved to the EU rule (last Sunday of March): 504
    hours of March 2026 then disagreed with the algos original."""
    theirs = _algos_clock()
    start = datetime(2025, 10, 20, 0, 30)
    for h in range(0, 24 * 200):
        naive = start + timedelta(hours=h)
        assert broker_clock.to_utc(naive) == theirs.to_utc(naive), naive
        server_ms = int((naive - datetime(1970, 1, 1)).total_seconds() * 1000) + 250
        want = theirs.to_utc(theirs.broker_naive_from_epoch(server_ms // 1000))
        want_ms = int((want - datetime(1970, 1, 1)).total_seconds() * 1000) + 250
        assert broker_clock.server_ms_to_utc_ms(server_ms) == want_ms


def test_the_money_per_price_unit_resolves_in_a_process_that_loaded_nothing_else():
    """RED with the `python_runner` import removed from `_history_sources`: in a fresh process the
    backtest package was not on the import path, so every R without the bot's own risk and every
    dollar excursion came back empty. Found by driving the page, not by the suite — the full app
    had loaded another router first, which is exactly what hid it.

    ⚠ Reads the committed account registry (demo 700152905, `puprime_ecn`) — a fact on disk."""
    import subprocess
    import sys

    backend = Path(__file__).resolve().parents[1]
    code = "from routers import bots; print(bots._history_sources(700152905)[1])"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120
    )
    assert out.stdout.strip().splitlines()[-1] == "100.0", out.stderr[-500:]


def test_the_rebuilt_balance_is_checked_against_the_broker_only_on_this_account():
    """RED when the account filter was dropped: another account's balance graded this one."""
    from services.account_history import broker_balance_check as check

    states = {
        "other": {"observed_account": 1, "balance": 50.0},
        "mine": {"observed_account": 7, "balance": 1000.004},
    }
    assert check(states, 7, 1000.0) == {"broker_balance": 1000.0, "broker_balance_matches": True}
    assert check(states, 7, 990.0)["broker_balance_matches"] is False
    assert check(states, 9, 1000.0)["broker_balance_matches"] is None
    assert check(None, 7, 1000.0)["broker_balance_matches"] is None
    assert check({"x": {"observed_account": 7, "balance": None}}, 7, 1.0)["broker_balance"] is None


def test_a_trade_the_record_marks_as_not_the_strategys_stays_in_the_balance_only():
    """RED when `attach_plans` ignored the marker: the 2026-08-25 duplicate-order incident's four
    positions ($3,344.80) scored as manual trades in the account's strategy figures."""
    from services.account_history import attach_plans, parse_rows

    raw = "\n".join(
        [
            'x:{"kind": "event", "event": "unmanaged_positions_incident",'
            ' "counts_as_strategy_performance": false, "tickets": [11, 12], "why": "dupes"}',
            'x:{"kind": "event", "event": "trade_not_strategy_performance",'
            ' "counts_as_strategy_performance": false, "ticket": 13, "why": "hand"}',
            'x:{"kind": "event", "event": "order_placed", "ticket": 14}',
        ]
    )
    _, opens = parse_rows(raw)
    positions = [{"ticket": t, "entry_ms": 0} for t in (11, 12, 13, 14)]
    attach_plans(positions, opens)
    assert [p["excluded"] for p in positions] == ["dupes", "dupes", "hand", None]
    assert all(p["bot"] is None and p["stop"] is None for p in positions)
