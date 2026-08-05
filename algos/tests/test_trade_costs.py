"""A closed live trade must record what it COST, not just what the price did.

**Why this file exists.** G5 in `docs/LIVE_TRADING_PIPELINE.md` — *PU Prime's spread, swap,
commission and minimum stop distance are assumed, never measured* — is the reason the bot was
armed on the demo account on 2026-08-05. Every cost figure in this repo was measured on
VANTAGE, and the bot trades PU Prime; the 2026-08-04 shadow diff already showed the two feeds
differ by a systematic 4-5 cents. A live trade is the only thing that can settle it.

🔴 **It could not have settled anything as the code stood.** `mt5_ops.get_deal_result` returns
MT5's `d.profit`, which is the PRICE MOVE ONLY, and it reads the CLOSING deal alone — so swap
was dropped and commission, normally booked on the ENTRY deal, was never even looked at. The
first live trade would have written a P&L that disagreed with the account balance, under a
field name (`pnl_usd`) that gives a reader no reason to suspect it. That is this repo's
signature defect: a number that is correct about a narrower question than the one being asked.

The tests below are mostly about the ways a cost field can be wrong while looking fine —
booking a credit as a charge, reading absence as zero, and netting so early that the parts
can never be recovered.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# MetaTrader5 is Windows-only. `mt5_ops` imports it at module scope, and the source-inspection
# tests at the bottom of this file need the module object — so it gets the same stub
# `test_bar_stream_holes.py` uses.
sys.modules.setdefault("MetaTrader5", types.SimpleNamespace(
    TIMEFRAME_M1=1, TIMEFRAME_M5=5, TIMEFRAME_M15=15, TIMEFRAME_M30=30,
    TIMEFRAME_H1=60, TIMEFRAME_H4=240, TIMEFRAME_D1=1440))

_REPO = Path(__file__).resolve().parent.parent.parent
for p in (str(Path(__file__).resolve().parent), str(_REPO),
          str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if p not in sys.path:
        sys.path.insert(0, p)

from test_live_bridge import (_bridge, _Dec, _FakeExecution,  # noqa: E402
                              _FakeMt5Ops, _Pos, _Sig)


class _CostyOps(_FakeMt5Ops):
    """An `mt5_ops` that can answer the cost question, the way the real one now can."""

    def __init__(self, breakdown):
        super().__init__()
        self.breakdown = breakdown
        self.breakdown_calls = 0

    def get_deal_breakdown(self, ticket):
        self.breakdown_calls += 1
        return self.breakdown


def _close_with(breakdown, *, lots=0.42, entry=3290.0, stop=3280.0):
    """Adopt an open position, then close it, and hand back the ledger's `closed` row."""
    ops = _CostyOps(breakdown) if breakdown is not None else _FakeMt5Ops()
    ops.positions = [_Pos(901, 0, entry, lots, stop)]
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b.sync(_Dec(stop=stop), _Sig())
    ops.positions = []
    ops.deal = (3320.0, 1260.0)          # the GROSS-only answer, still available
    ex._pos_dir = 0
    b.sync(_Dec(), _Sig())
    return [kw for k, kw in ledger.rows if k == "closed"][0], ops, notes


def _bd(**kw):
    base = {"close_price": 3320.0, "gross_usd": 1260.0, "swap_usd": 0.0,
            "commission_usd": 0.0, "net_usd": 1260.0, "deals": 2}
    base.update(kw)
    base["net_usd"] = base["gross_usd"] + base["swap_usd"] + base["commission_usd"]
    return base


# ── the parts are kept, not just the total ───────────────────────────────────────

def test_the_closed_record_carries_gross_swap_and_commission_separately():
    """The whole point. A single netted number cannot be taken apart afterwards, so a study of
    'what does this broker actually charge' has to be able to read the parts per trade."""
    closed, _, _ = _close_with(_bd(swap_usd=-14.0, commission_usd=-7.0))
    assert closed["gross_usd"] == 1260.0
    assert closed["swap_usd"] == -14.0
    assert closed["commission_usd"] == -7.0


def test_the_headline_pnl_is_the_NET_number():
    """`pnl_usd` has to mean what the balance did, or the live record and the account statement
    disagree with nothing on the page to explain why."""
    closed, _, _ = _close_with(_bd(swap_usd=-14.0, commission_usd=-7.0))
    assert closed["pnl_usd"] == pytest.approx(1239.0)


def test_R_is_computed_from_the_net_not_the_gross():
    """A scratch that is +0.02R on price and negative after an overnight swap is a LOSS, and
    the exit alert leads with WIN/LOSS off this number.

    Asserted as a RATIO against the same trade priced gross, rather than against a hand-figured
    dollar risk — the fake's contract size is its own business, and hardcoding it here would
    make this test fail for a reason that has nothing to do with costs."""
    net, _, _ = _close_with(_bd(gross_usd=420.0, swap_usd=-40.0))
    gross, _, _ = _close_with(_bd(gross_usd=420.0))
    assert net["r_multiple"] == pytest.approx(gross["r_multiple"] * 380.0 / 420.0)
    assert net["r_multiple"] < gross["r_multiple"]


# ── a credit is not a charge ─────────────────────────────────────────────────────

def test_a_positive_swap_stays_positive():
    """🔴 Gold's SHORT swap is a real CREDIT — measured at +26.98 points/night over the 6.5-year
    replay, where shorts were PAID 2.14R while longs paid 8.55R. The command center booked
    exactly this credit as a charge on 2026-08-03 with `-Math.abs(cost_usd)` and overstated
    fees by 25%. A cost field that cannot be positive cannot measure a broker that pays you."""
    closed, _, _ = _close_with(_bd(swap_usd=+31.5))
    assert closed["swap_usd"] == +31.5
    assert closed["pnl_usd"] == pytest.approx(1291.5)


def test_a_credit_can_carry_a_trade_from_loss_to_profit():
    """Stated as an outcome rather than a sign, because a sign bug that only ever makes numbers
    smaller is easy to read past for months."""
    closed, _, _ = _close_with(_bd(gross_usd=-20.0, swap_usd=+31.5))
    assert closed["pnl_usd"] > 0


# ── absence is never zero ────────────────────────────────────────────────────────

def test_an_ops_handle_that_cannot_answer_falls_back_instead_of_crashing():
    """The plain `_FakeMt5Ops` has no `get_deal_breakdown` — and neither does an older
    `mt5_ops` on a box that has not pulled. Losing the cost breakdown is a bad day; raising out
    of the EXIT path and losing the record that the trade closed at all is a much worse one."""
    closed, _, _ = _close_with(None)
    assert closed["pnl_usd"] == 1260.0          # the old gross-only answer
    assert closed["swap_usd"] is None


def test_costs_are_None_rather_than_zero_when_they_could_not_be_read():
    """`None` means the broker could not be ASKED. Zero means it charged nothing. Collapsing
    the two is the exact defect that left a live bot blind for 50 minutes on 2026-08-04 —
    'no data' and 'cannot ask' must never be the same value."""
    closed, _, _ = _close_with(None)
    for field in ("gross_usd", "swap_usd", "commission_usd"):
        assert closed[field] is None, f"{field} must be None, not 0.0"


def test_a_breakdown_reporting_no_deals_is_treated_as_not_found():
    """`deals: 0` is what an unreachable terminal returns, and its zeros would otherwise be
    written down as a trade that cost nothing — a fabricated measurement, which is worse than a
    missing one because nothing downstream can tell."""
    closed, _, _ = _close_with(_bd(gross_usd=0.0, deals=0))
    assert closed["swap_usd"] is None
    assert closed["pnl_usd"] == 1260.0          # fell back to get_deal_result


# ── entry slippage rides on the same row ─────────────────────────────────────────

def test_the_closed_row_repeats_the_fill_and_the_intended_price():
    """Entry slippage is the OTHER half of G5 — what the spread actually costs on a resting
    limit. Joining open and closed rows by ticket works, but it fails silently for any trade
    whose open record predates a log rotation, and a cost study that quietly drops its oldest
    trades is worse than one that refuses to run."""
    closed, _, _ = _close_with(_bd())
    assert closed["entry_price"] == 3290.0
    assert "intended_price" in closed


# ── the slippage arithmetic, against the REAL ledger ─────────────────────────────
#
# The bridge tests above use a fake ledger that records the kwargs it was handed, which is the
# right shape for asking "did the bridge pass the costs on" and the wrong one for asking "is
# the derived field right" — the derivation lives in `Ledger.trade_closed`, so these drive it
# directly.

def _row(tmp_path, **kw):
    from ledger import Ledger
    import json
    led = Ledger(tmp_path, "bot")
    base = dict(ticket=1, direction="LONG", symbol="XAUUSD.s", price=3320.0,
                pnl_usd=10.0, r_multiple=1.0, reason="tp")
    base.update(kw)
    led.trade_closed(**base)
    # Found by glob rather than by rebuilding the filename: the ledger owns its own day-rollover
    # rule, and a test that re-derives the name would pass at 23:59 and fail at 00:01.
    line = next(l for f in sorted(tmp_path.glob("decisions-*.jsonl"))
                for l in f.read_text().splitlines() if '"closed"' in l)
    return json.loads(line)


def test_slippage_is_derived_from_the_fill_and_the_intention(tmp_path):
    """The measurement G5 is actually after on the entry side: a resting limit either filled
    where it was placed or it did not, and the difference is what this broker's book cost."""
    row = _row(tmp_path, entry_price=3290.4, intended_price=3290.0)
    assert row["entry_slippage"] == pytest.approx(0.4)


def test_slippage_is_None_when_there_was_no_intended_price_to_compare(tmp_path):
    """An adopted position — one the bot found rather than placed — has no intended price, and
    reporting 0.00 slippage for it would claim a perfect fill nobody ever measured."""
    row = _row(tmp_path, entry_price=3290.4, intended_price=None)
    assert row["entry_slippage"] is None


def test_the_cost_fields_default_to_None_on_the_ledger_itself(tmp_path):
    """Belt and braces on the layer that writes the file: a caller that omits them must not
    produce a record claiming the trade was free."""
    row = _row(tmp_path)
    for field in ("gross_usd", "swap_usd", "commission_usd"):
        assert row[field] is None


# ── the breakdown reader itself ──────────────────────────────────────────────────

def test_the_breakdown_sums_every_deal_not_just_the_closing_one():
    """Commission is charged on the ENTRY deal. Reading only the closing deal — which is what
    `get_deal_result` does — loses the entry-side commission entirely, which is exactly the
    half a 'zero commission' broker claim would hide."""
    import inspect
    import mt5_ops
    src = inspect.getsource(mt5_ops.BotMT5.get_deal_breakdown)
    before_closing_filter = src.split("closing =")[0]
    assert "d.entry == 1" not in before_closing_filter, \
        "the sums must run over every deal of the position, before any closing-deal filter"
    assert "mine" in before_closing_filter


def test_the_breakdown_reports_how_many_deals_it_summed():
    """Without a count there is no way to tell an empty answer from a free trade."""
    import inspect
    import mt5_ops
    assert '"deals"' in inspect.getsource(mt5_ops.BotMT5.get_deal_breakdown)


def test_the_breakdown_does_not_abs_the_swap():
    """The 2026-08-03 command-center bug in one line: `-abs(cost)` cannot represent a credit,
    and gold's short swap is one."""
    import inspect
    import mt5_ops
    src = inspect.getsource(mt5_ops.BotMT5.get_deal_breakdown)
    assert "abs(" not in src.split('"""')[-1], "a cost field must be able to be positive"


def test_get_deal_result_is_left_alone():
    """Five other callers unpack its 2-tuple. Widening it to smuggle costs into `pnl` would
    silently redefine every one of them, including the batch-close paths."""
    import inspect
    import mt5_ops
    sig = inspect.signature(mt5_ops.BotMT5.get_deal_result)
    assert list(sig.parameters) == ["self", "ticket"]
    assert "GROSS" in (mt5_ops.BotMT5.get_deal_result.__doc__ or ""), \
        "its docstring must say the number is gross, or the next reader repeats this bug"
