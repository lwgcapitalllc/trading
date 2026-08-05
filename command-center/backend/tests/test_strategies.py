"""
Strategy scanning — current contract.

The scanner reads from `<MONOREPO_ROOT>/strategies/**` : 1 NinjaTrader .cs (ORB; VWAP_MR
and Momentum deleted 2026-06-21) + 1 MT5 .mq5 (LondonBreakout; MeanReversion deleted
2026-06-22) + 2 Python packages, each declaring LAB_STRATEGY (mpc_sos_fade 2026-07-16,
mpc_bleg 2026-07-24; mpc_bos deleted 2026-08-04). NT8 and Python strategies get a
suggested_instrument; MT5 does not. Param types span int/double/bool (NT8), string (MT5),
and all four off a dataclass (Python).

`EXPECTED_CLASS_NAMES` is the single place the roster is stated — every count below is
`len()` of it, never a repeated literal. Adding a strategy is then a one-line edit here
instead of three failing tests that each have to be traced back to the same cause.

⚠ **That is only true of the counts INSIDE this file.** `1946f8b` deleted the unfinished
`mpc_bos` port and its message says "and its roster line with it" — meaning the one in
`backtest/tools/run_report.py`, which that commit correctly called "the ONLY live
reference". This roster is a SECOND one, in another subsystem, and it was missed: three
tests here failed from that day until 2026-08-05. **A roster stated once per file is still
stated N times across the repo** — when you delete a strategy, grep for its class name, not
just its package path.
"""

import textwrap
import pytest

EXPECTED_CLASS_NAMES = {
    "ORB",
    "LondonBreakout",
    "MpcSosFadeStrategy",
    "MpcBLegStrategy",
}

SYNTHETIC_CS = textwrap.dedent("""\
    public class SyntheticStrat : Strategy
    {{
        [NinjaScriptProperty]
        [Range(5, {range_max})]
        [Display(Name = "Period", GroupName = "Strategy", Order = 1)]
        public int Period {{ get; set; }}

        protected override void OnStateChange()
        {{
            if (State == State.SetDefaults)
            {{
                Description = "Synthetic test strategy";
                Period = 20;
            }}
        }}
    }}
""")


# ── Cold start ─────────────────────────────────────────────────────────────────

def test_scan_adds_every_strategy(client):
    r = client.post("/strategies/scan")
    assert r.status_code == 200
    data = r.json()
    assert data["added"] == len(EXPECTED_CLASS_NAMES)
    assert data["updated"] == 0


def test_scan_returns_correct_class_names(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    assert len(strategies) == len(EXPECTED_CLASS_NAMES)
    assert {s["class_name"] for s in strategies} == EXPECTED_CLASS_NAMES


def test_strategies_have_populated_param_schema(client):
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    for s in strategies:
        schema = s["param_schema"]
        assert isinstance(schema, list) and len(schema) > 0, \
            f"{s['class_name']} has empty param_schema"
        for p in schema:
            assert p.get("name")
            assert isinstance(p.get("type"), str) and p["type"]


def test_nt8_strategies_have_suggested_instrument(client):
    """NT8 strategies get an inferred instrument; MT5 (LondonBreakout) legitimately has none."""
    client.post("/strategies/scan")
    strategies = client.get("/strategies").json()
    nt8 = [s for s in strategies if s.get("runner", "ninjatrader") == "ninjatrader"]
    assert len(nt8) == 1
    for s in nt8:
        assert s["suggested_instrument"], f"{s['class_name']} missing suggested_instrument"


# ── Idempotence ────────────────────────────────────────────────────────────────

def test_second_scan_is_idempotent(client):
    client.post("/strategies/scan")
    r = client.post("/strategies/scan")
    data = r.json()
    assert data["added"] == 0
    assert data["updated"] == 0
    assert data["skipped"] == len(EXPECTED_CLASS_NAMES)


# ── Param-schema + hash update on source change ───────────────────────────────

def _write_synthetic(tmp_path, range_max):
    nt8_dir = tmp_path / "strategies" / "ninjatrader"
    nt8_dir.mkdir(parents=True, exist_ok=True)
    cs_file = nt8_dir / "SyntheticStrat.cs"
    cs_file.write_text(SYNTHETIC_CS.format(range_max=range_max))
    return cs_file


def test_range_change_updates_param_schema(fresh_db, monkeypatch, tmp_path):
    """Editing a [Range] in a .cs and rescanning updates the stored schema."""
    import config as cfg
    from services import lab_db, strategy_scanner

    cs_file = _write_synthetic(tmp_path, range_max=60)
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)

    result1 = strategy_scanner.scan_strategies()
    assert result1["added"] == 1
    period_v1 = next(p for p in lab_db.get_strategy("syntheticstrat")["param_schema"]
                     if p["name"] == "Period")
    assert period_v1["max"] == 60

    cs_file.write_text(SYNTHETIC_CS.format(range_max=120))
    result2 = strategy_scanner.scan_strategies()
    assert result2["updated"] == 1
    assert result2["added"] == 0
    period_v2 = next(p for p in lab_db.get_strategy("syntheticstrat")["param_schema"]
                     if p["name"] == "Period")
    assert period_v2["max"] == 120


def test_source_hash_updates_on_change(fresh_db, monkeypatch, tmp_path):
    import config as cfg
    from services import lab_db, strategy_scanner

    _write_synthetic(tmp_path, range_max=60)
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)
    strategy_scanner.scan_strategies()
    hash_v1 = lab_db.get_strategy_hash("syntheticstrat")

    _write_synthetic(tmp_path, range_max=90)
    strategy_scanner.scan_strategies()
    hash_v2 = lab_db.get_strategy_hash("syntheticstrat")
    assert hash_v1 != hash_v2


# ── remove_strategy: the VPS delete must skip local-only runners ──────────────

def test_remove_python_strategy_never_calls_the_vps(fresh_db, monkeypatch):
    """A python strategy is a package that runs in-process — it is never deployed, so removing
    it must not ask the agent to delete a file. Regression: reconcile passed the package DIR
    name to the NT8 agent, which replied "Only .cs files are allowed" and surfaced a warning
    about a file that never existed."""
    import time
    from services import lab_db, strategy_scanner

    lab_db.upsert_strategy({
        "id": "pystrat", "name": "Py", "class_name": "PyStrategy",
        "source_path": "strategies/python/pystrat", "scanned_at": int(time.time()),
        "runner": "python",
    })

    def _boom(_filename):
        raise AssertionError("the VPS agent must not be called for a python strategy")

    monkeypatch.setattr(strategy_scanner.runner_dispatch, "delete_strategy_file", _boom)

    res = strategy_scanner.remove_strategy("pystrat")
    assert res["removed"] is True
    assert res["vps_error"] is None
    assert lab_db.get_strategy("pystrat") is None


def test_remove_nt8_strategy_still_deletes_the_vps_file(fresh_db, monkeypatch):
    """The python skip must not disarm the delete for runners that DO deploy."""
    import time
    from services import lab_db, strategy_scanner

    lab_db.upsert_strategy({
        "id": "orbtest", "name": "ORB", "class_name": "ORB",
        "source_path": "strategies/ninjatrader/ORB.cs", "scanned_at": int(time.time()),
        "runner": "ninjatrader",
    })

    called = []
    monkeypatch.setattr(strategy_scanner.runner_dispatch, "delete_strategy_file",
                        lambda fn: called.append(fn))

    res = strategy_scanner.remove_strategy("orbtest")
    assert called == ["ORB.cs"]          # the filename, not the path
    assert res["vps_deleted"] is True


# ── A python strategy's source_path is a DIRECTORY, not a file ────────────────
# Both endpoints below assumed a file and called read_text() on the package dir
# (IsADirectoryError → 500). sync-status took every OTHER strategy down with it.

def _add_python_strategy(tmp_path, monkeypatch):
    import time
    import config as cfg
    from services import lab_db

    pkg = tmp_path / "strategies" / "python" / "pystrat"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)
    lab_db.upsert_strategy({
        "id": "pystrat", "name": "Py Strat", "class_name": "PyStrategy",
        "source_path": "strategies/python/pystrat", "scanned_at": int(time.time()),
        "runner": "python",
        "param_schema": [
            {"name": "lookback", "type": "int", "default": 5},
            {"name": "risk_pct", "type": "float", "default": 1.0},
            {"name": "enabled", "type": "bool", "default": True},
            {"name": "mode", "type": "str", "default": "a"},
        ],
    })


def test_param_types_reads_the_schema_for_python(client, tmp_path, monkeypatch):
    """No source file to parse — the scanner already typed these off the config dataclass.
    Only int/float are returned: the optimizer's grid can only sweep numbers."""
    _add_python_strategy(tmp_path, monkeypatch)
    r = client.get("/strategies/pystrat/param-types")
    assert r.status_code == 200, r.text
    assert r.json() == {"lookback": "int", "risk_pct": "double"}


def test_sync_status_skips_python_and_still_reports_the_others(client, tmp_path, monkeypatch):
    """A python strategy has no deployed file, so it gets no row — and its presence must not
    break the report for NT8/MT5 strategies."""
    import time
    from services import lab_db

    _add_python_strategy(tmp_path, monkeypatch)
    lab_db.upsert_strategy({
        "id": "orbtest", "name": "ORB", "class_name": "ORB",
        "source_path": "strategies/ninjatrader/ORB.cs", "scanned_at": int(time.time()),
        "runner": "ninjatrader",
    })

    r = client.get("/strategy-files/sync-status")
    assert r.status_code == 200, r.text
    ids = {row["strategy_id"] for row in r.json()}
    assert "pystrat" not in ids
    assert "orbtest" in ids
