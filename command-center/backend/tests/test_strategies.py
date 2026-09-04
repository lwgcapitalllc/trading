"""
Strategy scanning — current contract.

The scanner reads from `<MONOREPO_ROOT>/strategies/**` : 1 NinjaTrader .cs (ORB; VWAP_MR
and Momentum deleted 2026-06-21) + 1 MT5 .mq5 (LondonBreakout; MeanReversion deleted
2026-06-22) + Python packages, each declaring LAB_STRATEGY (sos_fade 2026-07-16,
b_leg 2026-07-24, bos deleted 2026-08-04 and re-added 2026-08-07,
realign 2026-08-13, the loss-recovery leg 2026-08-21, extreme_leg 2026-09-01).
⚠ The count used to be written out here as a number and it said FOUR while the roster below
held six — a second statement of the same fact, in the same file, going stale exactly the way
the callout further down warns about. `len(EXPECTED_CLASS_NAMES)` is the count. NT8 and Python strategies get a suggested_instrument; MT5 does
not. Param types span int/double/bool (NT8), string (MT5), and all four off a dataclass
(Python).

`EXPECTED_CLASS_NAMES` is the single place the roster is stated — every count below is
`len()` of it, never a repeated literal. Adding a strategy is then a one-line edit here
instead of three failing tests that each have to be traced back to the same cause.

⚠ **That is only true of the counts INSIDE this file.** `1946f8b` deleted the unfinished
`bos` port and its message says "and its roster line with it" — meaning the one in
`backtest/tools/run_report.py`, which that commit correctly called "the ONLY live
reference". This roster is a SECOND one, in another subsystem, and it was missed: three
tests here failed from that day until 2026-08-05. **A roster stated once per file is still
stated N times across the repo** — when you delete a strategy, grep for its class name, not
just its package path.
"""

import textwrap

EXPECTED_CLASS_NAMES = {
    "ORB",
    "LondonBreakout",
    "SosFadeStrategy",
    "BLegStrategy",
    # Re-added 2026-08-08 with the `bos` port's Python side (2026-08-07). This roster has now
    # gone stale in BOTH directions — a deleted strategy left behind, then a new one not added —
    # which is the callout above earning its keep for the second time.
    "BosStrategy",
    # Added 2026-08-21 with the loss-recovery LEG. FOURTH time these three tests have gone red for
    # this one cause. ⚠ This entry is not like the others: `RecoveryLeg` is a RULE, not a strategy
    # — it has no setups and arms off another leg's closed trades, so it carries
    # `requires_source` and every picker filters it out. It is still SCANNED and still needs a row
    # in `strategies`, because a stack leg's run row references one.
    "RecoveryLeg",
    # Added 2026-08-14. `strategies/python/realign` landed 2026-08-13 (e87c304) and its
    # roster line did not — the THIRD time these three tests have gone red for this one cause,
    # and the second time in the "new strategy not added" direction. `RealignStrategy`
    # subclasses `SosFadeStrategy`, so grepping for the base class name would not have found
    # it either: the thing to grep for is `LAB_STRATEGY`, which is what the scanner reads.
    "RealignStrategy",
    # Added 2026-09-01 with `strategies/python/extreme_leg` — the FIFTH time these three tests
    # have gone red for this one cause, and the third in the "new strategy not added" direction.
    # ⚠ It went red on the SAME COMMIT that added the package this time, rather than days later,
    # and only because the whole suite was run before committing. The callout at the top of this
    # file is the fix that keeps not working: a roster stated once per file is still stated N times
    # across the repo, and nothing makes anyone read this one.
    "ExtremeLegStrategy",
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
        assert isinstance(schema, list) and len(schema) > 0, (
            f"{s['class_name']} has empty param_schema"
        )
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
    period_v1 = next(
        p for p in lab_db.get_strategy("syntheticstrat")["param_schema"] if p["name"] == "Period"
    )
    assert period_v1["max"] == 60

    cs_file.write_text(SYNTHETIC_CS.format(range_max=120))
    result2 = strategy_scanner.scan_strategies()
    assert result2["updated"] == 1
    assert result2["added"] == 0
    period_v2 = next(
        p for p in lab_db.get_strategy("syntheticstrat")["param_schema"] if p["name"] == "Period"
    )
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

    lab_db.upsert_strategy(
        {
            "id": "pystrat",
            "name": "Py",
            "class_name": "PyStrategy",
            "source_path": "strategies/python/pystrat",
            "scanned_at": int(time.time()),
            "runner": "python",
        }
    )

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

    lab_db.upsert_strategy(
        {
            "id": "orbtest",
            "name": "ORB",
            "class_name": "ORB",
            "source_path": "strategies/ninjatrader/ORB.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )

    called = []
    monkeypatch.setattr(
        strategy_scanner.runner_dispatch, "delete_strategy_file", lambda fn: called.append(fn)
    )

    res = strategy_scanner.remove_strategy("orbtest")
    assert called == ["ORB.cs"]  # the filename, not the path
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
    lab_db.upsert_strategy(
        {
            "id": "pystrat",
            "name": "Py Strat",
            "class_name": "PyStrategy",
            "source_path": "strategies/python/pystrat",
            "scanned_at": int(time.time()),
            "runner": "python",
            "param_schema": [
                {"name": "lookback", "type": "int", "default": 5},
                {"name": "risk_pct", "type": "float", "default": 1.0},
                {"name": "enabled", "type": "bool", "default": True},
                {"name": "mode", "type": "str", "default": "a"},
            ],
        }
    )


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
    lab_db.upsert_strategy(
        {
            "id": "orbtest",
            "name": "ORB",
            "class_name": "ORB",
            "source_path": "strategies/ninjatrader/ORB.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )

    r = client.get("/strategy-files/sync-status")
    assert r.status_code == 200, r.text
    ids = {row["strategy_id"] for row in r.json()["statuses"]}
    assert "pystrat" not in ids
    assert "orbtest" in ids


# ── An unreachable agent is a REPORTED gap, never a dead endpoint ─────────────
# Before 2026-08-06 any NT8 failure raised a 502 that took every row with it —
# and a row with no sync object renders no status pill and a Run button, so a
# strategy that needed deploying looked ready to run.


def _break_nt8(monkeypatch):
    from services import runner_dispatch

    def boom():
        raise RuntimeError(
            "VPS agent /files/strategies: Remote end closed connection without response"
        )

    monkeypatch.setattr(runner_dispatch, "list_strategy_files", boom)


def test_sync_status_survives_a_dead_nt8_agent_and_names_it(client, tmp_path, monkeypatch):
    import time

    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "orbtest",
            "name": "ORB",
            "class_name": "ORB",
            "source_path": "strategies/ninjatrader/ORB.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )
    _break_nt8(monkeypatch)

    r = client.get("/strategy-files/sync-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nt8_error"] and "Remote end closed" in body["nt8_error"]
    rows = {row["strategy_id"]: row for row in body["statuses"]}
    assert "orbtest" in rows, "the rows must survive — they are what the page renders"


def test_an_unreachable_agent_leaves_presence_UNKNOWN_not_false(client, tmp_path, monkeypatch):
    """`file_exists_on_vps: False` is the positive claim that the deployment is
    GONE. Reporting it because nobody answered would invent an alarm; reporting
    `True` would invent a reassurance. It has to be None."""
    import time

    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "orbtest",
            "name": "ORB",
            "class_name": "ORB",
            "source_path": "strategies/ninjatrader/ORB.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )
    _break_nt8(monkeypatch)

    row = next(
        r
        for r in client.get("/strategy-files/sync-status").json()["statuses"]
        if r["strategy_id"] == "orbtest"
    )
    assert row["file_exists_on_vps"] is None
    assert row["in_sync"] is None


def test_deploy_state_still_answers_with_the_agent_down(client, tmp_path, monkeypatch):
    """`needs_deploy` comes from the LOCAL hash and this app's own deploy record,
    so it is answerable with the box switched off — which is the whole reason the
    rows are still served. A strategy that needs deploying must not render a Run
    button just because the VPS is unreachable."""
    import time

    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "orbtest",
            "name": "ORB",
            "class_name": "ORB",
            "source_path": "strategies/ninjatrader/ORB.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )
    _break_nt8(monkeypatch)

    row = next(
        r
        for r in client.get("/strategy-files/sync-status").json()["statuses"]
        if r["strategy_id"] == "orbtest"
    )
    # Never deployed through the tracked path → deployed hash is NULL → needs deploy.
    assert row["needs_deploy"] is True


def test_the_file_list_reports_which_platform_failed(client, monkeypatch):
    _break_nt8(monkeypatch)
    body = client.get("/strategy-files").json()
    assert body["nt8_error"]
    # An empty list with an error is a different fact from an empty list without
    # one — that distinction is what stopped the Deployed tab claiming "No files
    # deployed" over an unreachable box.
    assert body["files"] == [] or all(f["platform"] == "MT5" for f in body["files"])


# ── Deploy refuses what it cannot deploy ──────────────────────────────────────


def test_deploying_a_python_strategy_is_a_400_not_a_500(client, tmp_path, monkeypatch):
    """A python strategy's `source_path` is a PACKAGE DIRECTORY. `read_bytes()` on
    it raised IsADirectoryError — an unhandled 500 on a request whose honest
    answer is "that is not a thing this endpoint does". Latent while the UI never
    offered the button, which is exactly the kind of endpoint something else
    calls later."""
    _add_python_strategy(tmp_path, monkeypatch)
    r = client.post("/strategies/pystrat/deploy")
    assert r.status_code == 400, r.text
    assert "not deployed" in r.json()["detail"].lower()


def test_a_deploy_job_is_not_readable_from_another_strategys_url(client):
    """The path names a strategy, so it has to mean one."""
    r = client.get("/strategies/orbtest/deploy/does-not-exist")
    assert r.status_code == 404


# ── An orphan is a standing fact, not a scan result ───────────────────────────


def test_a_strategy_whose_source_is_gone_is_flagged_on_the_row(client, tmp_path, monkeypatch):
    """The Reconcile control used to be gated on the last SCAN's output, so an
    orphan was invisible on a fresh page load until somebody happened to press
    Scan. Whether a file exists on disk is answerable at any moment."""
    import time

    import config as cfg
    from services import lab_db

    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)
    lab_db.upsert_strategy(
        {
            "id": "ghost",
            "name": "Ghost",
            "class_name": "Ghost",
            "source_path": "strategies/ninjatrader/Ghost.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )
    rows = {r["id"]: r for r in client.get("/strategies").json()}
    assert rows["ghost"]["is_orphan"] is True


def test_a_strategy_whose_source_exists_is_not_an_orphan(client, tmp_path, monkeypatch):
    import time

    import config as cfg
    from services import lab_db

    src = tmp_path / "strategies" / "ninjatrader"
    src.mkdir(parents=True)
    (src / "Real.cs").write_text("// present")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)
    lab_db.upsert_strategy(
        {
            "id": "real",
            "name": "Real",
            "class_name": "Real",
            "source_path": "strategies/ninjatrader/Real.cs",
            "scanned_at": int(time.time()),
            "runner": "ninjatrader",
        }
    )
    rows = {r["id"]: r for r in client.get("/strategies").json()}
    assert rows["real"]["is_orphan"] is False


# ── A package that cannot be imported is REPORTED, never silently skipped ─────


def test_a_broken_python_package_is_named_in_the_scan_warnings(tmp_path, monkeypatch, fresh_db):
    """Returning a bare None made a broken package indistinguishable from one
    that simply is not a lab strategy: the row kept its stale param schema,
    `needs_scan` stayed true for ever, and the scan reported success with
    "0 updated"."""
    import config as cfg
    from services import strategy_scanner

    pkg = tmp_path / "strategies" / "python" / "brokenstrat"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("this is not valid python (((")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)

    result = strategy_scanner.scan_strategies()
    assert any("brokenstrat" in w for w in result["warnings"]), result["warnings"]


def test_a_package_that_is_simply_not_a_strategy_warns_about_nothing(
    tmp_path, monkeypatch, fresh_db
):
    """A helper package under strategies/python/ is the NORMAL state, not a
    fault — warning about it would train the reader to ignore the list."""
    import config as cfg
    from services import strategy_scanner

    pkg = tmp_path / "strategies" / "python" / "helpers"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VALUE = 1\n")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", tmp_path)

    result = strategy_scanner.scan_strategies()
    assert result["warnings"] == []
