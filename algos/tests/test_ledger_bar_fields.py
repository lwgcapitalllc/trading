"""The per-bar decision record must carry the BAR, whatever shape the signal has.

🔴 **The defect this file exists for, found 2026-09-07 by reading the live record of a bot
nobody had read yet.** `Ledger.bar()` reads every field defensively — `getattr(sig, ..., None)`
— so that a strategy with an unfamiliar decision shape logs what it has instead of crashing the
bot. That choice is right and stays. What it also did was read the three BAR facts flat off the
signal, and only ONE of the two live shapes answers flat:

| bot | what `signals.update()` returns | `time_ms` | `index` | `close` |
|---|---|---|---|---|
| `sos_fade_demo` | its own signal object | flat ✅ | flat ✅ | flat ✅ |
| `extreme_leg_demo` | the engine stack's `BarState`, handed straight past by `PassThroughSignals` | on `.bar`, and named `timestamp_ms` ❌ | on `.bar` ❌ | on `.bar` ❌ |

**MEASURED on the committed record before the fix, 2026-09-07:** `extreme_leg_demo` wrote **196
of 196** rows that day with `bar_time`, `bar_index` and `close` all null, while `sos_fade_demo`
wrote **66 of 66** with all three populated. The extreme leg computes all three every bar — they
were never reaching the record.

⚠ **Why it matters more than a thin log line: this is the only record of a refusal that exists.**
No broker statement contains a setup that was declined, and the whole point of the file is to
answer *why did it not trade*. A row that cannot say which bar it describes, or where price was,
cannot be lined up against a chart — so the answer is there and unreadable.

⚠ **It never affected trading.** The record is written after the strategy has decided and is read
by nobody in the decision path; `bridge.sync` is driven by the decision object.

🔴 **The transferable rule is rule 1, and this is the cheapest possible illustration of it.**
`getattr(x, name, None)` collapses *this object does not have that field* into *that field's
value is None*. Both write `null`. A bot writing 196 blank rows a day and a bot on a quiet
market look identical in the file, and the file is the only witness. `_bar_field` returns a
private sentinel so the two stay separable inside the module, and the caller flattens it to the
record's single null on purpose — the SCHEMA has one null, the CODE must not.

**Watched RED (rule 12), each against its own named case:**

| mutation in `ledger.py` | what goes red |
|---|---|
| drop `"timestamp_ms"` from the `bar_time` names | `test_a_nested_signal_lands_its_bar_time` |
| drop `getattr(sig, "bar", None)` from the holders tuple | the three `nested` cases |
| put `.bar` before `sig` in the holders tuple | `test_a_flat_signal_is_never_read_through_its_bar` **and** `test_a_flat_none_is_kept_and_does_not_fall_through` |
| return `None` instead of `_MISSING` when nothing answers | `test_an_absent_field_is_missing_not_none` |
| revert `_bar_or_none` to the old flat `getattr` | every `nested` case |

🔴 **THE MAP ABOVE WAS RUN, NOT REASONED, AND RUNNING IT CHANGED THE TESTS.** Two rows were
written from inspection and both were wrong. The `.bar`-before-`sig` mutation reddens TWO cases,
not one. Worse, the `_MISSING` → `None` mutation **survived the whole file** as first written:
every case here reads the RECORD, `_bar_or_none` flattens the sentinel to `None` on the way
there, and so the two behaviours produce byte-identical rows. **A distinction that exists one
layer below the assertions is a distinction the assertions cannot make** — the same shape as a
scaling test written against a scale of exactly 1. The sentinel is pinned at the layer it lives
on (`test_an_absent_field_is_missing_not_none`), or it is decoration that would be deleted by
the next person who noticed nothing depended on it.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

# MetaTrader5 is Windows-only and imported lazily. A stub keeps this runnable on the Mac.
sys.modules.setdefault("MetaTrader5", types.SimpleNamespace())

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ledger import _MISSING, Ledger, _bar_field  # noqa: E402


def _flat_signal(**over):
    """`sos_fade_demo`'s shape: the bar's facts sit on the signal itself."""
    fields = {"time_ms": 1788479100000, "index": 5003, "close": 4480.08}
    fields.update(over)
    return SimpleNamespace(**fields)


def _nested_signal():
    """`extreme_leg_demo`'s shape: the engine stack's `BarState`, whose bar is one level down
    and whose timestamp carries the OTHER name. Deliberately carries no flat attribute at all —
    a double that answered both would not be able to fail the way production did."""
    return SimpleNamespace(
        bar=SimpleNamespace(timestamp_ms=1788479100000, index=5003, close=4480.08),
        snapshot=object(),
    )


def _write_bar(tmp_path, sig):
    led = Ledger(tmp_path, "a_bot")
    led.bar(SimpleNamespace(), sig, SimpleNamespace())
    rows = [
        json.loads(line)
        for f in sorted(tmp_path.glob("decisions-*.jsonl"))
        for line in f.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 1, rows
    return rows[0]


# ── the shape that already worked, which must not move by a byte ─────────────


def test_a_flat_signal_still_lands_all_three(tmp_path):
    row = _write_bar(tmp_path, _flat_signal())
    assert row["bar_time"] == 1788479100000
    assert row["bar_index"] == 5003
    assert row["close"] == 4480.08


def test_a_flat_signal_is_never_read_through_its_bar(tmp_path):
    """Flat wins. A signal carrying BOTH must report its own values, or the fix would silently
    re-point the live bot's own record at a different object."""
    sig = _flat_signal()
    sig.bar = SimpleNamespace(timestamp_ms=1, index=2, close=3.0)
    row = _write_bar(tmp_path, sig)
    assert (row["bar_time"], row["bar_index"], row["close"]) == (1788479100000, 5003, 4480.08)


def test_a_flat_none_is_kept_and_does_not_fall_through(tmp_path):
    """The rule-1 case, and the only one a careless fix gets wrong. A field that EXISTS and
    holds None is a measured None — it must be written as None, not treated as unanswered and
    resolved from somewhere else."""
    sig = _flat_signal(close=None)
    sig.bar = SimpleNamespace(timestamp_ms=1, index=2, close=999.0)
    row = _write_bar(tmp_path, sig)
    assert row["close"] is None
    assert row["bar_time"] == 1788479100000


# ── the shape that wrote 196 blank rows a day ────────────────────────────────


def test_a_nested_signal_lands_its_bar_time(tmp_path):
    """Named separately from the other two because it is the one that ALSO needs the alias —
    the nested bar calls it `timestamp_ms`, and a fix that only learned to look one level down
    would still leave this field null."""
    assert _write_bar(tmp_path, _nested_signal())["bar_time"] == 1788479100000


def test_a_nested_signal_lands_its_bar_index(tmp_path):
    assert _write_bar(tmp_path, _nested_signal())["bar_index"] == 5003


def test_a_nested_signal_lands_its_close(tmp_path):
    assert _write_bar(tmp_path, _nested_signal())["close"] == 4480.08


# ── a shape nobody has built yet ─────────────────────────────────────────────


def test_a_signal_answering_neither_writes_nulls_and_does_not_crash(tmp_path):
    """The defensive read is the reason this module survives an unfamiliar strategy, and that
    property is load-bearing: a ledger that can crash the loop it observes is worse than a
    ledger missing a column. A third shape must still get a row."""
    row = _write_bar(tmp_path, SimpleNamespace(something_else=1))
    assert row["bar_time"] is None
    assert row["bar_index"] is None
    assert row["close"] is None
    assert row["kind"] == "bar"


# ── the sentinel, pinned at the layer it actually lives on ───────────────────


def test_an_absent_field_is_missing_not_none():
    """The rule-1 distinction, asserted where it EXISTS. `_bar_or_none` flattens both to the
    record's single null, so no assertion about a written row can tell these apart — which is
    why the first version of this file passed a mutation that deleted the sentinel outright."""
    assert _bar_field(SimpleNamespace(), "close") is _MISSING
    assert _bar_field(SimpleNamespace(close=None), "close") is None


def test_the_record_flattens_both_to_one_null(tmp_path):
    """And the flattening is deliberate, not an oversight: the SCHEMA has one null. Pinning it
    stops somebody 'fixing' the asymmetry by leaking a sentinel into the JSON, where every
    reader of the file would then meet an object it cannot parse."""
    absent = _write_bar(tmp_path / "a", SimpleNamespace())
    (tmp_path / "b").mkdir()
    measured = _write_bar(tmp_path / "b", SimpleNamespace(time_ms=None, index=None, close=None))
    assert absent["close"] is None
    assert measured["close"] is None


def test_a_signal_whose_bar_is_none_does_not_crash(tmp_path):
    """`getattr(sig, "bar", None)` can return an actual None — a strategy that has the attribute
    and has not filled it yet. Iterating it must be skipped, not dereferenced."""
    row = _write_bar(tmp_path, SimpleNamespace(bar=None))
    assert row["bar_time"] is None
    assert row["kind"] == "bar"
