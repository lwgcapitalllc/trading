"""The word a strategy's own trades wear on the price chart.

🔴 The panel hard-coded `A+` — `sos_fade`'s word for ITS setup — and painted it on EVERY
strategy's primary trades, so three other bots' charts carried a fourth bot's label. Nothing was
broken and nothing went red: a wrong label renders exactly as confidently as a right one, which is
rule 7 in its quietest form.

⚠ A fail-watch against HEAD is vacuous for the column and the scanner key (neither existed), so
every test here names the MUTATION that turns it red in its own docstring.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import config as cfg
import pytest
from services import chart_spec, lab_db, strategy_import, strategy_scanner


@pytest.fixture
def isolated_strategy_imports():
    """Purge and restore `strategies.*`, so a probe package in tmp_path cannot be shadowed by the
    real tree and cannot outlive this test. Same reasoning as
    `tests/test_strategy_import_freshness.py`, where it is explained at length."""
    before = dict(sys.modules)
    for name in [n for n in sys.modules if n == "strategies" or n.startswith("strategies.")]:
        del sys.modules[name]
    path_before = list(sys.path)
    yield
    for name in [n for n in sys.modules if n not in before]:
        del sys.modules[name]
    sys.modules.update(before)
    sys.path[:] = path_before


def _probe_pkg(tmp_path: Path, declaration: str) -> Path:
    """A minimal package declaring LAB_STRATEGY with whatever `chart_tag` line is passed."""
    pkg = tmp_path / "strategies" / "python" / "tag_probe"
    pkg.mkdir(parents=True)
    (tmp_path / "strategies" / "__init__.py").write_text("")
    (tmp_path / "strategies" / "python" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Cfg:\n"
        "    mode: str = 'Off'\n"
        "class Strat:\n"
        "    pass\n"
        "LAB_STRATEGY = {'name': 'Tag Probe', 'config': Cfg, 'strategy': Strat,\n"
        f"                {declaration}}}\n"
    )
    return pkg


def _row(tmp_path, declaration: str) -> dict:
    pkg = _probe_pkg(tmp_path, declaration)
    strategy_import.purge_strategy_modules()
    row, err = strategy_scanner._parse_python_package(pkg, tmp_path)
    assert err is None, err
    return row


# ── the package declares it ──────────────────────────────────────────────────
def test_the_declaring_package_has_its_tag_carried_off_the_module():
    """Driven against the REAL package rather than a probe, so it also pins that the declaration
    actually landed. RED by dropping the `chart_tag` key from the scanner's row dict — the column
    then stores NULL for every strategy and every chart falls back to the A+ bot's word, which is
    the behaviour this whole mechanism replaces."""
    pkg = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "extreme_leg"
    row, err = strategy_scanner._parse_python_package(pkg, Path(cfg.MONOREPO_ROOT))
    assert err is None, err
    assert row["chart_tag"] == "XLEG"


def test_a_package_that_declares_nothing_carries_None():
    """The half that would go unnoticed: a key defaulting to any string makes every undeclared
    strategy wear a tag its package never asked for, which is the defect with a different word in
    it.

    ⚠ **It pointed at `sos_fade` until that bot declared its own `A+` on 2026-09-02, and it
    went RED — correctly.** It is repointed at `loss_recovery`, which declares none DELIBERATELY:
    its trades carry `kind="recovery"`, so the renderer tags them `REC` down a different branch and
    a `chart_tag` there could never be read. That is a real case rather than a premise edited to
    keep a test green — the one package that must stay untagged, for a reason.
    RED by defaulting the scanner's key to a string."""
    pkg = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "loss_recovery"
    row, err = strategy_scanner._parse_python_package(pkg, Path(cfg.MONOREPO_ROOT))
    assert err is None, err
    assert row["chart_tag"] is None


@pytest.mark.parametrize(
    "declaration", ["'chart_tag': '   '", "'chart_tag': 7", "'chart_tag': None"]
)
def test_a_blank_or_non_string_declaration_is_None_and_never_reaches_the_chart(
    tmp_path, isolated_strategy_imports, declaration
):
    """`None` is the answer *this package declared no tag*, and the chart falls back on it. A blank
    string reads as *this package asked for an empty chip* in some checks and as no tag in others —
    the same 'no' / 'cannot ask' collapse rule 1 is about.

    RED by passing a bare `spec.get("chart_tag")` straight through: a whitespace-only declaration
    then reaches the column and the chart draws an empty chip where the tag should be."""
    assert _row(tmp_path, declaration)["chart_tag"] is None


def test_a_real_declaration_survives_the_probe_path_too(tmp_path, isolated_strategy_imports):
    """Non-vacuity for the three cases above: without this, a scanner returning None for EVERY
    declaration would satisfy all of them. RED by returning None unconditionally."""
    assert _row(tmp_path, "'chart_tag': 'PROBE'")["chart_tag"] == "PROBE"


# ── it survives the round trip through the strategies table ──────────────────
def test_the_tag_survives_the_round_trip_and_an_upsert_can_CLEAR_it(tmp_path, monkeypatch):
    """Storing it is half the contract; being able to REMOVE it is the other half. A package that
    drops its declaration must stop tagging, or the column keeps asserting a word nobody declares
    any more — a strategy row outliving the source it describes.

    RED by dropping `chart_tag` from the upsert's ON CONFLICT clause: the first write lands and the
    second silently keeps the old value."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "lab.db")
    lab_db.init_db()
    row = {
        "id": "probe",
        "name": "Probe",
        "class_name": "Probe",
        "source_path": "strategies/python/probe",
        "scanned_at": 0,
        "runner": "python",
    }
    lab_db.upsert_strategy({**row, "chart_tag": "XLEG"})
    assert lab_db.get_strategy("probe")["chart_tag"] == "XLEG"
    lab_db.upsert_strategy({**row})  # the package dropped its declaration
    assert lab_db.get_strategy("probe")["chart_tag"] is None


def test_the_column_exists_on_a_FRESH_database_as_well_as_a_migrated_one(tmp_path, monkeypatch):
    """This backend's own standing note: a column added to only ONE of the migration list and the
    CREATE TABLE works perfectly on whichever machine you tested and is missing on the other.

    RED by removing the ALTER from the migration list — an existing database never gains the
    column and every read of it raises instead of answering."""
    monkeypatch.setattr(lab_db, "DB_PATH", tmp_path / "fresh.db")
    lab_db.init_db()
    with sqlite3.connect(tmp_path / "fresh.db") as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(strategies)")}
    assert "chart_tag" in cols


# ── the STACK is the case it exists for ──────────────────────────────────────
def test_the_builder_stamps_the_tag_on_EVERY_trade():
    """The stamping itself, at the seam the stack depends on. RED by dropping the `tag` key from
    the dict `_build_trades` appends — every trade then arrives untagged and every chart, single or
    stacked, falls back to the A+ bot's word."""
    curve = [
        {
            "entry_ms": 1_600_000_000_000,
            "exit_ms": 1_600_000_600_000,
            "direction": "Long",
            "profit": 10.0,
            "entry_price": 100.0,
            "exit_price": 101.0,
            "kind": "primary",
        },
        {
            "entry_ms": 1_600_001_000_000,
            "exit_ms": 1_600_001_600_000,
            "direction": "Short",
            "profit": -5.0,
            "entry_price": 101.0,
            "exit_price": 102.0,
            "kind": "primary",
        },
    ]
    built = chart_spec._build_trades(curve, [], "XLEG")
    assert len(built) == 2
    assert [t.get("tag") for t in built] == ["XLEG", "XLEG"]


def test_no_tag_means_the_KEY_IS_ABSENT_rather_than_empty():
    """Absent is what the panel reads as *fall back to `PRIMARY_TAG`*. A key present and empty
    would render a blank chip instead. RED by stamping `tag` unconditionally."""
    curve = [
        {
            "entry_ms": 1,
            "exit_ms": 2,
            "direction": "Long",
            "profit": 1.0,
            "entry_price": 1.0,
            "exit_price": 2.0,
            "kind": "primary",
        }
    ]
    assert "tag" not in chart_spec._build_trades(curve, [], None)[0]


def test_each_LEG_of_a_stack_keeps_its_OWN_tag_through_the_merge(monkeypatch):
    """🔴 THE CASE THE WHOLE MECHANISM EXISTS FOR, and the first implementation got it wrong. A
    stack merges N legs' trades into ONE list — so a tag carried on the SPEC cannot survive, and
    every leg's trades would wear whichever single tag the merged spec happened to hold. That is
    the hard-coded-`A+` defect one level down and HARDER to see, because the chips would look
    per-strategy without being it, which is the exact thing a reader stacks two bots to tell apart.

    ⚠ **Each leg's trades are built through the REAL `_build_trades`, not hand-written with a tag
    already on them.** An earlier version of this test handed the merge pre-tagged dicts and was
    VACUOUS — it proved a dict copy preserves keys, and stayed green under the mutation it was
    written to catch. RED now by dropping the stamp: both legs come back untagged."""
    legs = {"run_a": ("sos_fade", "A+"), "run_b": ("extreme_leg", "XLEG")}
    curve = [
        {
            "entry_ms": 1_600_000_000_000,
            "exit_ms": 1_600_000_600_000,
            "direction": "Long",
            "profit": 10.0,
            "entry_price": 100.0,
            "exit_price": 101.0,
            "kind": "primary",
        }
    ]

    def fake_spec(run_id, refresh=False):
        _sid, tag = legs[run_id]
        return {
            "instrument": "XAUUSD.p",
            "baseTimeframe": "M5",
            "brokerGmtOffsetHours": 0,
            "sessions": [],
            "historyStartMs": 0,
            "candles": [{"timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1}],
            "trades": chart_spec._build_trades(curve, [], tag),
            "blocks": [],
            "misses": [],
            "missNoise": [],
            "overlays": [],
            "indicators": [],
        }

    monkeypatch.setattr(
        lab_db,
        "list_stack_runs",
        lambda sid: [
            {"run_id": r, "strategy_id": s, "strategy_name": s, "status": "complete"}
            for r, (s, _t) in legs.items()
        ],
    )
    monkeypatch.setattr(chart_spec, "build_chart_spec", fake_spec)

    merged = chart_spec.build_stack_chart_spec("st_probe")
    by_layer = {t["layer"]: t.get("tag") for t in merged["trades"]}
    assert by_layer == {"sos_fade": "A+", "extreme_leg": "XLEG"}, (
        "each leg's trades must keep their OWN strategy's word on a merged chart"
    )


# ── the chart reads it ───────────────────────────────────────────────────────
def test_the_chart_reads_the_declaring_strategys_tag(monkeypatch):
    """RED by hardcoding a tag in `_chart_tag`, or by returning the strategy id — both of which
    render as a perfectly plausible chip."""
    monkeypatch.setattr(lab_db, "get_strategy", lambda sid: {"chart_tag": "XLEG"})
    assert chart_spec._chart_tag("extreme_leg") == "XLEG"


@pytest.mark.parametrize(
    "row", [None, {}, {"chart_tag": None}, {"chart_tag": "  "}, {"chart_tag": 3}]
)
def test_anything_but_a_real_word_is_None_so_the_panel_falls_back(monkeypatch, row):
    """The panel distinguishes ABSENT (fall back to the A+ word) from a declared tag, so a blank or
    non-string value must arrive as absent rather than as a tag rendering an empty chip.

    RED by returning `str(tag)` unconditionally — `None` then reaches the chart as the word
    'None', which is exactly the kind of label a reader takes at face value."""
    monkeypatch.setattr(lab_db, "get_strategy", lambda sid: row)
    assert chart_spec._chart_tag("probe") is None


def test_a_missing_strategy_id_asks_nothing():
    """⚠ **THIS ONE CANNOT GO RED TODAY AND IS KEPT AS A FORWARD GUARD — the mutation was RUN.**
    Deleting the `if not strategy_id` early-out leaves it GREEN, because `lab_db.get_strategy`
    answers `None` for both a null and an empty id rather than raising (measured, not assumed). So
    the guard saves a pointless query and is not today load-bearing, and an earlier draft of this
    docstring claimed a mutation that does not bite.

    It is kept because the answer must stay `None` if that lookup ever starts refusing a null id —
    a chart losing its tags over a run with no strategy would be a silent regression."""
    assert chart_spec._chart_tag(None) is None
    assert chart_spec._chart_tag("") is None


def test_a_label_lookup_can_never_cost_the_whole_chart(monkeypatch):
    """Every other lookup in `chart_spec` is best-effort for the same reason: a chart that refuses
    to build because a LABEL could not be read has traded a missing word for a missing chart.

    RED by removing the try/except — the exception then propagates out of `build_chart_spec`."""

    def boom(_sid):
        raise sqlite3.OperationalError("no such column: chart_tag")

    monkeypatch.setattr(lab_db, "get_strategy", boom)
    assert chart_spec._chart_tag("probe") is None


def test_build_chart_spec_actually_PASSES_the_tag_to_the_builder():
    """🔴 THE WIRING, and it was the one hole the other tests left. `_build_trades` stamping the tag
    and `_chart_tag` resolving it are both covered — nothing asserted that `build_chart_spec` hands
    the second to the first. MEASURED: dropping the argument from that call left all 19 other tests
    GREEN while every chart shipped untagged trades.

    That is this backend's own recorded failure shape — a value computed, declared and read, with
    the CONSTRUCTOR never filling it (the `python` lock scope, 2026-08-06). Nothing is missing from
    the response, so no shape check can catch it.

    Read off the SOURCE rather than driven, because `build_chart_spec` needs a run row, candles, an
    equity curve and six overlay engines; a test that stubbed all of that would be asserting against
    its own scaffolding. RED by removing `trade_tag` from the call."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(chart_spec.build_chart_spec)))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_build_trades"
    ]
    assert calls, "build_chart_spec no longer calls _build_trades — re-aim this test"
    assert all(len(c.args) >= 3 for c in calls), (
        "build_chart_spec must pass the resolved tag into _build_trades, or every trade on every "
        "chart ships untagged and silently falls back to the A+ bot's word"
    )
