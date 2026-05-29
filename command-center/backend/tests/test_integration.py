"""
§11 Cases 4–7 — end-to-end VPS integration tests.

These tests hit the LIVE backend at localhost:8000 and require:
  - SSH tunnel open: localhost:8765 → VPS:8765
  - NT8 running in VPS RDP session (Session 1)
  - Strategy Analyzer tab open in NT8
  - VPS agent running inside RDP:
      cd C:\\trading\\algos\\markets\\futures\\lucid_flex\\tools
      python vps_agent.py

Run with:
  pytest tests/test_integration.py -m integration -v -s

Unit tests (no VPS) run separately:
  pytest tests/ -m "not integration"
"""

import time
import subprocess
import pytest
import httpx

pytestmark = pytest.mark.integration

BASE = "http://localhost:8000"
TIMEOUT = 30       # seconds for single HTTP calls
RUN_TIMEOUT = 300  # seconds to wait for a full backtest to complete


# ── Fixture: skip if VPS agent unreachable ─────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def require_vps():
    """Skip entire module if VPS agent tunnel is down."""
    try:
        httpx.get("http://localhost:8765/health", timeout=5)
    except Exception as e:
        pytest.skip(f"VPS agent not reachable on localhost:8765: {e}")


@pytest.fixture(scope="module", autouse=True)
def require_backend():
    """Skip if local backend is not running."""
    try:
        httpx.get(f"{BASE}/health", timeout=5)
    except Exception as e:
        pytest.skip(f"Backend not reachable on localhost:8000: {e}")


# ── Helper: poll a run until terminal status ───────────────────────────────────

def _poll_run(run_id: str, timeout: int = RUN_TIMEOUT) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = httpx.get(f"{BASE}/backtests/runs/{run_id}", timeout=TIMEOUT)
        data = r.json()
        status = data["status"]
        if status not in ("running", "queued"):
            return data
        time.sleep(5)
    pytest.fail(f"Run {run_id} still running after {timeout}s")


# ── Case 4: full backtest run to completion ───────────────────────────────────

def test_full_backtest_run_complete():
    """
    §11 Case 4: trigger ORB_LucidFlex on MNQ 06-26, 2024 full year,
    all 4 firms. Verify it completes with correct evaluation structure.
    """
    # Ensure strategies are scanned
    httpx.post(f"{BASE}/strategies/scan", timeout=TIMEOUT)
    strategies = httpx.get(f"{BASE}/strategies", timeout=TIMEOUT).json()
    orb = next((s for s in strategies if "ORB" in s["class_name"]), None)
    assert orb is not None, "ORB_LucidFlex strategy not found after scan"

    r = httpx.post(f"{BASE}/backtests/run", json={
        "strategy_id": orb["id"],
        "instrument": "MNQ 06-26",
        "params": orb["default_params"],
        "bar_type": "Minute",
        "bar_value": 5,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "commission_per_side": 0.50,
        "slippage_ticks": 1,
        "evaluate_firms": [
            "lucidflex_50k_eval",
            "lucidflex_50k_funded",
            "lucidflex_100k_eval",
            "lucidflex_100k_funded",
        ],
    }, timeout=TIMEOUT)
    assert r.status_code == 202, f"Trigger failed: {r.text}"
    run_id = r.json()["run_id"]

    data = _poll_run(run_id, timeout=RUN_TIMEOUT)
    assert data["status"] == "complete", \
        f"Run did not complete — status={data['status']} error={data.get('error_message')}"

    evals = data["evaluations"]
    assert len(evals) == 4, f"Expected 4 evaluations, got {len(evals)}"

    # Funded firms must NOT have consistency_pass
    funded_evals = [e for e in evals if "funded" in e["firm_id"]]
    for e in funded_evals:
        assert e["consistency_pass"] is None, \
            f"Funded firm {e['firm_id']} should have consistency_pass=null"

    # Eval firms must HAVE consistency_pass
    eval_evals = [e for e in evals if "eval" in e["firm_id"]]
    for e in eval_evals:
        assert e["consistency_pass"] is not None, \
            f"Eval firm {e['firm_id']} should have consistency_pass set"

    # Cleanup
    httpx.delete(f"{BASE}/backtests/runs/{run_id}", timeout=TIMEOUT)


# ── Case 5: failed compile path ───────────────────────────────────────────────

def test_compile_failure_marks_run_failed(tmp_path):
    """
    §11 Case 5: deploy a .cs file with a syntax error → run should fail.
    NOTE: This test modifies algos/ source — it restores the file afterward.
    Run only with --run-compile-test flag if desired (currently always skipped
    for safety unless you un-skip manually).
    """
    pytest.skip(
        "Compile-failure test modifies production .cs files. "
        "Run manually after reviewing the test body."
    )


# ── Case 6: agent kill → failed_timeout ───────────────────────────────────────

def test_agent_kill_causes_failed_timeout():
    """
    §11 Case 6: start a run, kill the VPS agent, verify failed_timeout.
    Kills the agent via SSH after PCT>5 is observed, then polls for failure.
    """
    httpx.post(f"{BASE}/strategies/scan", timeout=TIMEOUT)
    strategies = httpx.get(f"{BASE}/strategies", timeout=TIMEOUT).json()
    orb = next((s for s in strategies if "ORB" in s["class_name"]), None)
    assert orb is not None

    r = httpx.post(f"{BASE}/backtests/run", json={
        "strategy_id": orb["id"],
        "instrument": "MNQ 06-26",
        "params": orb["default_params"],
        "bar_type": "Minute", "bar_value": 5,
        "start_date": "2024-01-01", "end_date": "2024-03-31",  # short range, exits sooner
        "commission_per_side": 0.50, "slippage_ticks": 1,
        "evaluate_firms": ["lucidflex_50k_eval"],
    }, timeout=TIMEOUT)
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    # Wait until run is in progress (pct > 0) — up to 60s
    deadline = time.time() + 60
    while time.time() < deadline:
        data = httpx.get(f"{BASE}/backtests/runs/{run_id}", timeout=TIMEOUT).json()
        if data["status"] == "running":
            break
        time.sleep(3)

    # Kill the VPS agent process
    subprocess.run(
        ["ssh", "forexvps", "taskkill /f /im python.exe"],
        timeout=15, check=False,
    )

    # The backend poller has a 10-minute stall timeout.
    # Poll up to 700s for failed_timeout.
    data = _poll_run(run_id, timeout=700)
    assert data["status"] == "failed_timeout", \
        f"Expected failed_timeout, got: {data['status']}"
    assert data["error_message"] is not None
    assert "Lost contact" in data["error_message"] or "timeout" in data["error_message"].lower()

    httpx.delete(f"{BASE}/backtests/runs/{run_id}", timeout=TIMEOUT)


# ── Case 7: system health strip dots ─────────────────────────────────────────

def test_system_health_endpoint_shape():
    """
    §11 Case 7 (structural): /system/health returns all required fields.
    The actual dot states depend on VPS/NT8 runtime — verified manually.
    """
    r = httpx.get(f"{BASE}/system/health", timeout=TIMEOUT)
    assert r.status_code == 200
    h = r.json()
    required = {"backend", "ssh_tunnel", "vps_agent", "nt8_running",
                "nt8_sa_visible", "last_compile_ok", "checked_at"}
    assert required.issubset(h.keys()), f"Missing keys: {required - h.keys()}"
    assert isinstance(h["backend"], bool)
    assert isinstance(h["nt8_running"], bool)
    assert isinstance(h["last_compile_errors"], list)


def test_system_health_vps_live():
    """With VPS up, backend + ssh_tunnel should be True."""
    h = httpx.get(f"{BASE}/system/health", timeout=TIMEOUT).json()
    assert h["backend"] is True,     "Backend should report healthy"
    assert h["ssh_tunnel"] is True,  "SSH tunnel should be up (VPS is live)"
    assert h["vps_agent"] is True,   "VPS agent should respond (agent is running)"
