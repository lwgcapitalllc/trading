"""A refused setup must be written whatever shape the strategy gives it — and never cost the bar.

🔴 **The defect this file exists for, found 2026-09-11 on the LIVE account.** `Ledger.blocked()`
read SOS Fade's refusal fields by name — `block.time_ms`, `block.edge`, `block.codes`. The extreme
leg's refusal is a different class with different names:

| bot | refusal class | timestamp | price | rules |
|---|---|---|---|---|
| `sos_fade_demo` | `sos_fade.execution.BlockedSetup` | `time_ms` | `edge` | `codes` (a list) |
| `extreme_leg_demo` | `extreme_leg.execution.Blocked` | `ts_ms` | `entry_price` | one `code`, one `reason` |

So every extreme-leg refusal raised `'Blocked' object has no attribute 'time_ms'` — and the
refusal is written BEFORE the broker is reconciled (`runner._settle_primary`), so the raise
**aborted the whole bar before its broker check, then re-warmed the bot**. MEASURED on the live
record: `bar_error` at 2026-09-11 05:45:09 UTC, `rewarm after_bar_error: true` ten seconds later,
and no `blocked` row anywhere for it.

⚠ **The refusal itself was lost too** — this file is the only record of a declined setup; no
broker statement contains one.

⚠ **These use the two strategies' REAL refusal classes**, never a stand-in. The defect WAS a
shape difference, and a double built from what the test author believes the shape to be is a
double that cannot fail the way production did (rule 13).

**Watched RED (rule 12), each against its own named case:**

| mutation in `ledger.py` | what goes red |
|---|---|
| drop `"ts_ms"` from `bar_time`'s names | `test_the_extreme_legs_refusal_is_WRITTEN_not_raised` |
| drop `"entry_price"` from `edge`'s names | the same |
| read `codes` only (no singular fallback) | the same |
| let the singular win over a CARRIED empty plural | `test_an_empty_codes_list_stays_empty_and_never_becomes_rule_0` |
| drop the `except` around `blocked`'s payload | `test_a_refusal_field_that_RAISES_is_written_as_unreadable` |
| drop the `except` around `missed`'s payload | `test_a_miss_field_that_RAISES_is_written_as_unreadable` |
| drop `"ts_ms"` from `missed`'s `bar_time` | `test_a_miss_carrying_the_other_timestamp_name_lands_it` |
| revert `blocked()` to the direct attribute reads | the incident case AND the runner case |
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

# MetaTrader5 is Windows-only and imported lazily. A stub keeps this runnable on the Mac; the
# runner's feed reads these timeframe constants at import.
sys.modules.setdefault(
    "MetaTrader5",
    types.SimpleNamespace(
        TIMEFRAME_M1=1,
        TIMEFRAME_M5=5,
        TIMEFRAME_M15=15,
        TIMEFRAME_M30=30,
        TIMEFRAME_H1=60,
        TIMEFRAME_H4=240,
        TIMEFRAME_D1=1440,
    ),
)

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (
    str(_REPO),
    str(_REPO / "algos" / "live"),
    str(_REPO / "algos" / "shared"),
    str(_REPO / "strategies" / "python"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from extreme_leg.execution import BLK_NEWS, BLOCK_TEXT  # noqa: E402
from extreme_leg.execution import Blocked as ExtremeBlocked  # noqa: E402
from ledger import Ledger  # noqa: E402
from runner import LiveRunner  # noqa: E402
from sos_fade.execution import BlockedSetup, MissedSetup  # noqa: E402

_T = 1788505500000  # 2026-09-11 05:45 UTC, the bar the live record lost


def _rows(tmp_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for f in sorted(tmp_path.glob("decisions-*.jsonl"))
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _payload(row: dict) -> list:
    """The record minus the three stamps every row carries — as ORDERED pairs, so a row whose
    fields moved position counts as a row that moved."""
    return [(k, v) for k, v in row.items() if k not in ("ts", "bot", "kind")]


def _extreme_refusal() -> ExtremeBlocked:
    return ExtremeBlocked(5003, _T, 1, BLOCK_TEXT[BLK_NEWS], BLK_NEWS, 4300.0, 4290.0, 4330.0)


# ── the incident ─────────────────────────────────────────────────────────────


def test_the_extreme_legs_refusal_is_WRITTEN_not_raised(tmp_path):
    Ledger(tmp_path, "extreme_leg_demo").blocked(_extreme_refusal())
    (row,) = _rows(tmp_path)
    assert row["kind"] == "blocked"
    assert row["dir"] == 1
    assert row["bar_time"] == _T
    assert row["edge"] == 4300.0
    assert row["codes"] == [BLK_NEWS]
    assert row["reasons"] == [BLOCK_TEXT[BLK_NEWS]]
    # Fields this strategy does not carry are the record's one null — never invented.
    assert row["sos_bar"] is None
    assert row["labels"] is None


def test_the_bar_that_carried_an_extreme_leg_refusal_reaches_its_broker_check(tmp_path):
    """The incident's real cost, asserted through the REAL call path rather than the ledger
    alone: the refusal is recorded BEFORE `bridge.sync`, so a raise there skipped the broker
    reconcile for the whole bar. A test that drove only `Ledger.blocked` would prove the writer
    and nothing about whether the bar survives it."""
    r = LiveRunner.__new__(LiveRunner)
    ex = SimpleNamespace(blocks=[_extreme_refusal()], misses=[])
    r.strategy = SimpleNamespace(execution=ex)
    r.ledger = Ledger(tmp_path, "extreme_leg_demo")
    synced = []
    r.bridge = SimpleNamespace(sync=lambda dec, sig: synced.append(dec), state=None)
    r.setup_alerts = None
    r.log = SimpleNamespace(error=lambda *a, **k: None)

    dec = SimpleNamespace()
    r._settle_primary(SimpleNamespace(dec=dec, sig=SimpleNamespace(), seq=SimpleNamespace()))

    assert synced == [dec], "the bar never reached its broker check"
    assert ex.blocks == [], "the refusal was not drained, so the next bar writes it again"
    assert [row["kind"] for row in _rows(tmp_path)] == ["bar", "blocked"]


# ── the shape that already worked, which must not move by a byte ─────────────


def test_sos_fades_refusal_row_does_not_move_by_a_byte(tmp_path):
    b = BlockedSetup(dir=-1, index=10, time_ms=_T, codes=[3, 7], edge=4321.5, sos_bar=9)
    Ledger(tmp_path, "sos_fade_demo").blocked(b)
    (row,) = _rows(tmp_path)
    # What the old direct reads wrote, in the order they wrote it.
    assert _payload(row) == [
        ("dir", -1),
        ("bar_time", _T),
        ("edge", 4321.5),
        ("sos_bar", 9),
        ("codes", [3, 7]),
        ("labels", b.labels),
        ("reasons", b.reasons),
    ]


def test_an_empty_codes_list_stays_empty_and_never_becomes_rule_0(tmp_path):
    """The rule-1 case. SOS Fade's `code` is a PROPERTY answering 0 when `codes` is empty, so a
    reader that fell through to the singular would record a refusal by a rule nobody applied."""
    b = BlockedSetup(dir=1, index=1, time_ms=_T, codes=[], edge=1.0, sos_bar=0)
    Ledger(tmp_path, "sos_fade_demo").blocked(b)
    (row,) = _rows(tmp_path)
    assert row["codes"] == []


def test_sos_fades_miss_row_does_not_move_by_a_byte(tmp_path):
    m = MissedSetup(
        dir=1,
        index=12,
        time_ms=_T,
        met=3,
        code=2,
        arm_text="Sweep · Day Low",
        arm_met=True,
        zone=True,
        zone_time_ms=_T - 900_000,
        zone_turn_ms=_T - 450_000,
        fvg=False,
        edge=4310.25,
        near=True,
    )
    Ledger(tmp_path, "sos_fade_demo").missed(m)
    (row,) = _rows(tmp_path)
    assert _payload(row) == [
        ("dir", 1),
        ("bar_time", _T),
        ("edge", 4310.25),
        ("met", 3),
        ("of", getattr(m, "of", None)),
        ("near", True),
        ("labels", getattr(m, "labels", None)),
        ("reasons", getattr(m, "reasons", None)),
    ]


# ── shapes nobody has built yet ──────────────────────────────────────────────


def test_a_refusal_of_no_known_shape_still_gets_a_row(tmp_path):
    Ledger(tmp_path, "a_bot").blocked(SimpleNamespace(something_else=1))
    (row,) = _rows(tmp_path)
    assert row["kind"] == "blocked"
    assert all(v is None for k, v in _payload(row))


def test_a_miss_carrying_the_other_timestamp_name_lands_it(tmp_path):
    Ledger(tmp_path, "a_bot").missed(SimpleNamespace(dir=-1, ts_ms=_T))
    (row,) = _rows(tmp_path)
    assert (row["dir"], row["bar_time"]) == (-1, _T)


class _Raises:
    """A record whose field RAISES rather than being absent — a property computing off state it
    does not have. `getattr(obj, name, default)` only absorbs AttributeError, so this is the one
    shape the name fallbacks cannot cover."""

    dir = 1

    @property
    def time_ms(self):
        raise RuntimeError("no bar yet")


def test_a_refusal_field_that_RAISES_is_written_as_unreadable(tmp_path):
    Ledger(tmp_path, "a_bot").blocked(_Raises())
    (row,) = _rows(tmp_path)
    assert row["kind"] == "blocked", "the refusal vanished from the only file that records it"
    assert "no bar yet" in row["unreadable"]


def test_a_miss_field_that_RAISES_is_written_as_unreadable(tmp_path):
    Ledger(tmp_path, "a_bot").missed(_Raises())
    (row,) = _rows(tmp_path)
    assert row["kind"] == "missed"
    assert "no bar yet" in row["unreadable"]
