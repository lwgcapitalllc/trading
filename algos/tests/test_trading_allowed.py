"""Whether the account may trade, read every poll — `runner.trading_block` and the check around it.

🔴 **Written after 2026-09-11.** PU Prime had put live account 34957946 on read-only until it held
the ECN minimum deposit; every order from 12:45 AM to 7:30 AM CDT came back refused (10017), and
nothing on any screen said trading was off until the bot halted at 7:45. The terminal can report
that an account may not trade, and nothing asked it.

Every test names the mutation that turns it red; each was RUN.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bridge import BridgeState  # noqa: E402
from runner import LiveRunner, trading_block  # noqa: E402

_TERM_ON = SimpleNamespace(trade_allowed=True)
_FULL = SimpleNamespace(trade_mode=4)


def _acct(**kw):
    """What `mt5.account_info()` answers, with both trade flags on unless a test says otherwise."""
    return SimpleNamespace(**{"trade_allowed": True, "trade_expert": True, **kw})


# ── the decision ─────────────────────────────────────────────────────────────────────────


def test_every_flag_yes_is_allowed():
    assert trading_block(_acct(), _TERM_ON, _FULL, "XAUUSD.p") == (True, None)


@pytest.mark.parametrize(
    "account,terminal,symbol,words",
    [
        (_acct(trade_allowed=False), _TERM_ON, _FULL, "read-only"),
        (_acct(trade_expert=False), _TERM_ON, _FULL, "automated trading"),
        (_acct(), SimpleNamespace(trade_allowed=False), _FULL, "AutoTrading"),
        (_acct(), _TERM_ON, SimpleNamespace(trade_mode=3), "XAUUSD.p on close only"),
        (_acct(), _TERM_ON, SimpleNamespace(trade_mode=0), "XAUUSD.p on disabled"),
    ],
)
def test_each_way_trading_stops_is_named(account, terminal, symbol, words):
    """Four different fixes, so four different sentences. Red under: any one check dropped."""
    allowed, why = trading_block(account, terminal, symbol, "XAUUSD.p")

    assert allowed is False
    assert words in why


def test_a_flag_that_cannot_be_read_is_UNKNOWN_never_allowed():
    """Rule 1 — an older build, or a terminal that did not answer. Red under: reading a missing
    flag as yes (an account nothing could see would be reported able to trade)."""
    assert trading_block(SimpleNamespace(), _TERM_ON, _FULL, "X") == (None, None)
    assert trading_block(_acct(), None, _FULL, "X") == (None, None)
    assert trading_block(_acct(), _TERM_ON, None, "X") == (None, None)


def test_a_NO_outranks_a_flag_that_could_not_be_read():
    """An unreadable flag must never hide one that said no. Red under: answering unknown first."""
    allowed, why = trading_block(SimpleNamespace(trade_allowed=False), None, None, "X")

    assert allowed is False
    assert "read-only" in why


# ── the check the loop runs ──────────────────────────────────────────────────────────────


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, kind, **kw):
        self.events.append((kind, kw))


def _runner(monkeypatch, *, account, terminal=_TERM_ON, symbol=_FULL, observed=1):
    """A bare runner whose terminal reports `account` / `terminal` / `symbol`. `observed` is the
    account the terminal said it is on, off the same call as the balance; `cfg.account` is 1."""
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(
        bot_key="bot",
        display_name="Bot",
        account=1,
        symbol="XAUUSD.p",
        strategy_version=1,
        strategy_package="p",
        promoted_commit="abc",
        promoted_at="2026-09-12",
        is_frozen=True,
    )
    r._observed_account = observed
    r._observed_info = account
    r.ledger = _Ledger()
    r.alerts, r.logged = [], []
    r.log = SimpleNamespace(
        error=lambda m, *a, **k: r.logged.append(m),
        info=lambda m, *a, **k: r.logged.append(m),
        warning=lambda m, *a, **k: r.logged.append(m),
    )
    r._notify_health = lambda m, **_k: r.alerts.append(m)
    mt5 = SimpleNamespace(terminal_info=lambda: terminal, symbol_info=lambda _s: symbol)
    monkeypatch.setitem(sys.modules, "MetaTrader5", mt5)
    return r


def test_trading_OFF_is_said_ONCE_and_recorded(monkeypatch):
    """Red under: saying it on every poll (a message every ten seconds is muted by noon); under
    not recording it (the record is where an audit finds why no order reached the broker); and
    under dropping the warning that a trade triggering meanwhile halts the bot."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))
    for _ in range(3):
        r._check_trading_allowed()

    assert len(r.alerts) == 1
    assert "TRADING OFF" in r.alerts[0] and "read-only" in r.alerts[0]
    assert "halts" in r.alerts[0] and "restart" in r.alerts[0]
    assert [k for k, _ in r.ledger.events] == ["trading_disabled"]
    assert (r._trade_allowed, "read-only" in r._trade_block) == (False, True)


def test_trading_BACK_ON_is_said_once_too(monkeypatch):
    """Silence is only safe because recovery speaks. Red under: dropping the recovery message."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))
    r._check_trading_allowed()
    r._observed_info = _acct()
    r._check_trading_allowed()
    r._check_trading_allowed()

    assert len(r.alerts) == 2
    assert "TRADING BACK ON" in r.alerts[1]
    assert [k for k, _ in r.ledger.events] == ["trading_disabled", "trading_restored"]


def _recovered(monkeypatch, bridge):
    """Trading goes off and comes back, on a runner whose order side is `bridge`."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))
    r.bridge = bridge
    r._check_trading_allowed()
    r._observed_info = _acct()
    r._check_trading_allowed()
    return r


def test_trading_back_on_over_a_HALTED_bot_says_restart_it_never_nothing_to_do(monkeypatch):
    """A halt latches (only a restart clears it), and a trade triggering while orders were refused
    is what halts one — so an all-clear here stops somebody looking at a bot that places nothing.
    Red under: dropping the halted branch (it says "Nothing to do." over a halted bot)."""
    halted = SimpleNamespace(state=BridgeState.HALTED, halt_reason="MT5 holds none")
    r = _recovered(monkeypatch, halted)

    assert len(r.alerts) == 2
    assert "STILL HALTED" in r.alerts[1] and "Restart it" in r.alerts[1]
    assert "MT5 holds none" in r.alerts[1]
    assert "Nothing to do" not in r.alerts[1]
    assert [k for k, _ in r.ledger.events] == ["trading_disabled", "trading_restored"]


def test_trading_back_on_over_a_LIVE_bot_is_the_plain_all_clear(monkeypatch):
    """The control — an alert that always warns is one nobody reads. Red under: saying STILL
    HALTED whatever state the order side is in."""
    r = _recovered(monkeypatch, SimpleNamespace(state=BridgeState.LIVE, halt_reason=None))

    assert "TRADING BACK ON" in r.alerts[1] and "Nothing to do" in r.alerts[1]
    assert "HALTED" not in r.alerts[1]


def test_a_halt_with_no_recorded_reason_never_prints_None(monkeypatch):
    """Red under: putting the reason in unconditionally — "(None)" in a message a person acts on
    reads as a reason."""
    r = _recovered(monkeypatch, SimpleNamespace(state=BridgeState.HALTED, halt_reason=None))

    assert "STILL HALTED" in r.alerts[1] and "None" not in r.alerts[1]


def test_a_healthy_account_says_NOTHING(monkeypatch):
    """An alert on the normal state is one people learn to scroll past. Red under: announcing
    that trading is on at every start."""
    r = _runner(monkeypatch, account=_acct())
    r._check_trading_allowed()

    assert r.alerts == [] and r.ledger.events == []
    assert r._trade_allowed is True


def test_a_DIFFERENT_reason_is_said_again(monkeypatch):
    """Two causes need two fixes. Red under: keying the once-only rule on off-or-on alone."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))
    r._check_trading_allowed()
    r._observed_info = _acct()
    sys.modules["MetaTrader5"].terminal_info = lambda: SimpleNamespace(trade_allowed=False)
    r._check_trading_allowed()

    assert len(r.alerts) == 2
    assert "AutoTrading" in r.alerts[1]


def test_could_not_ask_leaves_what_was_said_standing(monkeypatch):
    """Rule 1 again: an unreadable flag is not a recovery. Red under: reading unknown as allowed
    (it would announce TRADING BACK ON off a terminal that did not answer)."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))
    r._check_trading_allowed()
    r._observed_info = SimpleNamespace()
    r._check_trading_allowed()

    assert len(r.alerts) == 1
    assert r._trade_allowed is None


def test_another_accounts_flags_are_never_reported_as_this_bots(monkeypatch):
    """On another account that is the identity halt's business (rule 16). Red under: dropping the
    account check."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False), observed=999)
    r._check_trading_allowed()

    assert r.alerts == []
    assert r._trade_allowed is None


def test_a_terminal_read_that_raises_is_COULD_NOT_ASK(monkeypatch):
    """A terminal that raised did not answer, so the verdict is unknown — not the last one kept.
    Red under: narrowing the except around the terminal reads (the raise skips the verdict, which
    stays whatever it was; on this bare runner it is never set at all)."""
    r = _runner(monkeypatch, account=_acct())

    def _boom():
        raise RuntimeError("IPC recv failed")

    sys.modules["MetaTrader5"].terminal_info = _boom
    r._check_trading_allowed()

    assert r._trade_allowed is None


def test_a_failure_while_REPORTING_never_reaches_the_loop(monkeypatch):
    """It runs on every pass ahead of the bars, so a raise here would skip reading them. Red under:
    narrowing the outer except (a ledger that cannot write takes the pass down)."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))

    def _full_disk(*_a, **_k):
        raise OSError("No space left on device")

    r.ledger.event = _full_disk
    r._check_trading_allowed()

    assert r._trade_allowed is False


def test_the_account_flags_come_off_the_SAME_call_as_the_balance(monkeypatch):
    """Rule 10: the flags qualify the account the balance belongs to. Red under: not keeping the
    reading (the check would read nothing, or a previous poll's)."""
    r = LiveRunner.__new__(LiveRunner)
    r.log = SimpleNamespace(warning=lambda *a, **k: None)
    info = SimpleNamespace(balance=10312.48, login=34957946, trade_allowed=False, trade_expert=True)
    monkeypatch.setitem(sys.modules, "MetaTrader5", SimpleNamespace(account_info=lambda: info))

    assert r.probe_link() == (True, 10312.48)
    assert r._observed_info is info


def test_a_dead_link_leaves_no_stale_account_reading(monkeypatch):
    """Red under: keeping the previous poll's reading when the link dies."""
    r = LiveRunner.__new__(LiveRunner)
    r.log = SimpleNamespace(warning=lambda *a, **k: None)
    r._observed_info = _acct()
    monkeypatch.setitem(sys.modules, "MetaTrader5", SimpleNamespace(account_info=lambda: None))

    assert r.probe_link() == (False, None)
    assert r._observed_info is None


class _State:
    def __init__(self):
        self.written = {}

    def write_bot(self, _key, updates):
        self.written.update(updates)

    def ensure_starting_balance(self, *_a, **_k):
        pass


def test_the_heartbeat_carries_it_for_the_page_and_nothing_on_a_dead_link(monkeypatch):
    """Red under: dropping the fields from the write; and under writing them on a dead link, where
    the last reading describes a terminal nobody can reach."""
    r = _runner(monkeypatch, account=_acct(trade_allowed=False))
    r.bridge = SimpleNamespace(state=SimpleNamespace(value="live"))
    r.source_hash, r.dry_run = "0123456789abcdef", False
    r.feed = SimpleNamespace(last_bar_time=None)
    r._check_trading_allowed()
    st = _State()

    r._heartbeat(st, link_up=True, balance=10312.48)
    assert st.written["trade_allowed"] is False
    assert "read-only" in st.written["trade_block"]

    r._heartbeat(st, link_up=False, balance=None)
    assert (st.written["trade_allowed"], st.written["trade_block"]) == (None, None)
