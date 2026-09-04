"""scripts/run_diff.py — the basis check, on rows built to isolate one field.

WHY THIS FILE EXISTS, AND IT IS THE WHOLE POINT
-----------------------------------------------
`run_diff.py`'s load-bearing refusal is that a NULL `cost_layers` is NOT `[]`.
NULL is a row written before layered costs existed and keeps the legacy
contract — charge whatever commission and slippage the row itself states —
while `[]` means charge nothing. `services/python_runner.py::_cost_profile`
branches on exactly that, so two runs differing only in this really were
measured on different footings.

**No pair of REAL runs in the lab can prove that guard bites.** `cost_layers`
and `broker_profile` landed in the same change and have moved together on every
stored row, so on live data something else always differs too and the verdict
would read "not comparable" even with the guard disarmed. Measured at the time
these tests were written: 11 of 19 completed runs are NULL, and not one NULL/[]
pair is otherwise identical. That is what a synthetic row is for — it isolates
the one field, which real history refuses to.

NON-VACUITY. A fail-watch against HEAD is vacuous here (the module is new), so
each test names the MUTATION that turns it red. The two that matter:

  * collapse the NULL branch of `render_cost_layers` into "[] (explicitly free)"
    → `test_two_runs_differing_only_in_cost_layers_are_not_comparable` goes red,
    and this is the mutation that had no real-data counterexample.
  * make `total_r` return 0.0 instead of None when no trade carries `r`
    → `test_a_run_with_no_recorded_R_does_not_report_zero` goes red.

Every mutation listed was RUN, not reasoned about.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.run_diff as rd  # noqa: E402

# The columns run_diff reads. Built from the REAL schema (via lab_db.init_db)
# rather than hand-rolled, so a basis field added to the table cannot silently
# leave this file testing a shape production no longer has.
BASE_ROW = {
    "strategy_id": "sos_fade",
    "instrument": "XAUUSD",
    "params": json.dumps({"exec_risk_pct": 12.5}),
    "bar_type": "Minute",
    "bar_value": 15,
    "start_date": "2020-01-01",
    "end_date": "2026-08-01",
    "commission_per_side": 0.0,
    "slippage_ticks": 0,
    "status": "complete",
    "created_at": 1_700_000_000,
    "runner": "python",
    "sizing_mode": "consistent",
    "trade_count": 160,
    "profit_factor": 3.088,
    "win_rate": 0.6625,
    "net_pnl": 49_204_855.53,
    "max_drawdown_pct": 45.57,
}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A real lab.db schema at a temp path, with a strategies row to hang runs off."""
    from services import lab_db

    db = tmp_path / "lab.db"
    monkeypatch.setattr(lab_db, "DB_PATH", db)
    lab_db.init_db()

    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT OR REPLACE INTO strategies (id, name, class_name, source_path, scanned_at, runner) "
        "VALUES ('sos_fade','SOS Fade','MpcSosFade','strategies/python/sos_fade',1,'python')"
    )
    conn.commit()
    conn.close()
    return db


def insert_run(db: Path, run_id: str, **overrides) -> None:
    row = dict(BASE_ROW, run_id=run_id, **overrides)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn = sqlite3.connect(db)
    conn.execute(f"INSERT INTO backtest_runs ({cols}) VALUES ({marks})", list(row.values()))
    conn.commit()
    conn.close()


def write_curve(tmp_path: Path, run_id: str, points: list[dict]) -> str:
    d = tmp_path / run_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "equity_curve.json"
    p.write_text(json.dumps(points))
    return str(p)


def run_diff(db: Path, a: str, b: str, capsys) -> tuple[int, str]:
    # Drive the real entry point, so argv parsing and the read-only connection
    # are exercised too — not just the diff functions underneath them.
    sys.argv = ["run_diff.py", a, b, "--db", str(db)]
    code = rd.main()
    return code, capsys.readouterr().out


# ── the basis check ───────────────────────────────────────────────────────────


def test_two_runs_differing_only_in_cost_layers_are_not_comparable(lab, capsys):
    """THE test this file exists for. Real history cannot express this pair.

    MUTATION: return "[] (explicitly free)" from the `raw is None` branch of
    `render_cost_layers` → the field drops out of the diff, the two rows look
    identical on all 13 basis fields, and the verdict flips to comparable.
    Run, and it went red.
    """
    insert_run(lab, "aaaa", cost_layers=None)  # pre-layer row
    insert_run(lab, "bbbb", cost_layers="[]")  # explicitly free

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert code == 1, "a differing basis must exit non-zero so it can gate"
    assert "1 of 13 fields differ" in out, out
    assert "cost_layers" in out
    assert "not a like-for-like comparison" in out


def test_two_runs_with_the_same_basis_are_comparable(lab, capsys):
    """The control. Without it the test above passes against a script that
    calls everything incomparable.

    MUTATION: make `diff_basis` always append one row → this goes red.
    """
    insert_run(lab, "aaaa", cost_layers="[]")
    insert_run(lab, "bbbb", cost_layers="[]", params=json.dumps({"exec_risk_pct": 10.0}))

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert code == 0, out
    assert "Same on all 13 fields" in out
    assert "exec_risk_pct" in out, "the param that really differs must still be reported"
    assert "the result difference is the params' doing" in out


def test_populated_layers_are_distinct_from_explicitly_free(lab, capsys):
    """`["spread","swap"]` vs `[]` is the case a reader would notice anyway —
    pinned so a "simplification" of render_cost_layers cannot collapse the pair
    it is easy to get right while breaking the pair it is easy to get wrong.
    """
    insert_run(lab, "aaaa", cost_layers=json.dumps(["spread", "swap"]))
    insert_run(lab, "bbbb", cost_layers="[]")

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert code == 1
    assert "spread+swap" in out
    assert "explicitly free" in out


def test_the_three_cost_layer_states_render_differently():
    """The guard at the function, independent of any row.

    MUTATION: any two of these three collapsing → red.
    """
    null = rd.render_cost_layers(None)
    empty = rd.render_cost_layers("[]")
    charged = rd.render_cost_layers(json.dumps(["spread"]))

    assert len({null, empty, charged}) == 3, (null, empty, charged)
    assert "unrecorded" in null, "NULL must say it was never recorded, not that it was free"


def test_a_basis_change_that_moves_dollars_says_so(lab, capsys):
    """Net P&L is not comparable across a sizing or cost change even when every
    trade is identical. The script must SAY that rather than leave the reader to
    subtract two numbers that do not belong on one axis.

    MUTATION: drop the `moves_dollars` block → red.
    """
    insert_run(lab, "aaaa", sizing_mode="consistent")
    insert_run(lab, "bbbb", sizing_mode="manual", manual_risk_pct=2.0)

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert code == 1
    assert "Net P&L is not comparable" in out
    assert "sizing_mode" in out


# ── R, and the two ways it must refuse ────────────────────────────────────────


def test_a_run_with_no_recorded_R_does_not_report_zero(lab, tmp_path, capsys):
    """Per-trade `r` has only been written since 2026-08-03. A run without it
    has not been measured at zero — it has not been measured.

    MUTATION: `return 0.0, ""` instead of `None` when nothing carries `r` → red.
    """
    curve = write_curve(tmp_path, "aaaa", [{"index": 1, "profit": 100.0}])
    insert_run(lab, "aaaa", cost_layers="[]", equity_curve_path=curve)
    insert_run(lab, "bbbb", cost_layers="[]", equity_curve_path=curve)

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert "not recorded" in out
    assert "+0.0000" not in out, "a missing R must never render as a measured zero"
    assert code == 0


def test_a_partially_recorded_R_refuses_rather_than_summing_the_subset(lab, tmp_path, capsys):
    """A partial sum is the dangerous shape: it looks like a whole number.

    MUTATION: drop the `len(with_r) != len(trades)` branch → the run reports
    +1.0000 over two trades, and this goes red.
    """
    curve = write_curve(
        tmp_path,
        "aaaa",
        [
            {"index": 1, "r": 1.0},
            {"index": 2},  # same run, no r on this trade
        ],
    )
    insert_run(lab, "aaaa", cost_layers="[]", equity_curve_path=curve)
    insert_run(lab, "bbbb", cost_layers="[]", equity_curve_path=curve)

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert "partial (1 of 2 trades carry R)" in out
    assert "+1.0000" not in out


def test_a_fully_recorded_R_is_summed(lab, tmp_path, capsys):
    """Without this the two refusals above would pass against a `total_r` that
    never returns a number at all.
    """
    curve = write_curve(tmp_path, "aaaa", [{"index": 1, "r": 1.5}, {"index": 2, "r": -0.5}])
    insert_run(lab, "aaaa", cost_layers="[]", equity_curve_path=curve)
    insert_run(lab, "bbbb", cost_layers="[]", equity_curve_path=curve)

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert "+1.0000" in out, out


def test_an_unreadable_equity_curve_is_named_not_swallowed(lab, tmp_path, capsys):
    """A file that exists and cannot be parsed is a different fact from a run
    that recorded nothing, and both must be distinguishable from a real 0.0.
    """
    bad = tmp_path / "aaaa" / "equity_curve.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json")
    insert_run(lab, "aaaa", cost_layers="[]", equity_curve_path=str(bad))
    insert_run(lab, "bbbb", cost_layers="[]")

    code, out = run_diff(lab, "aaaa", "bbbb", capsys)

    assert "unreadable" in out
    assert "no equity curve recorded" in out, "the other side's absence must read differently"


# ── the field list is a claim about the schema ────────────────────────────────


def test_every_basis_field_exists_on_the_runs_table(lab):
    """BASIS_FIELDS names columns, and this pins that every name is real.

    ⚠ A typo does NOT fail silently — `sqlite3.Row["nope"]` raises IndexError,
    checked rather than assumed — so the script crashes on every comparison
    instead of quietly calling two different runs comparable. That is the safe
    direction, and it is why this test earns its place on a different argument
    from the one it was first written with: it names the bad field, where the
    IndexError surfaces inside `diff_basis` with nothing saying which name is
    wrong.

    MUTATION: add "cost_layerz" to BASIS_FIELDS → red (with 8 others, since the
    crash reaches every test that runs a diff).
    """
    conn = sqlite3.connect(lab)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(backtest_runs)")}
    conn.close()

    missing = [f for f in rd.BASIS_FIELDS if f not in cols]
    assert not missing, f"BASIS_FIELDS names columns that do not exist: {missing}"


def test_a_missing_run_is_a_usage_error_not_a_comparison(lab, capsys):
    insert_run(lab, "aaaa", cost_layers="[]")
    sys.argv = ["run_diff.py", "aaaa", "nope", "--db", str(lab)]
    assert rd.main() == 2
