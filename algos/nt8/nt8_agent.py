"""
NT8 Agent — job-keyed HTTP bridge for NinjaTrader 8 backtests.

Runs persistently in the RDP session on the VPS. NT8 + Strategy Analyzer must
be open before any /backtest job is submitted.

New endpoints (job-keyed):
    POST /backtest                  -- submit a job, returns {job_id} 202
    GET  /jobs/<job_id>/status      -- job state dict (no log)
    GET  /jobs/<job_id>/results     -- parsed result JSON
    GET  /jobs/<job_id>/log         -- job log tail
    POST /jobs/<job_id>/cancel      -- mark job cancelled
    GET  /nt-health                 -- NT8 process + SA window check
    GET  /nt-compile-status         -- last compile result from NT8 log
    GET  /nt-log                    -- NT8 log tail
    GET  /agent-log                 -- agent's own log tail

Legacy endpoints (kept for backward compat):
    GET  /health                    -- ping (now includes running_jobs count)
    GET  /status                    -- old running flag + agent log
    GET  /results                   -- reads nt8_results.csv
    POST /run-backtests             -- returns 410 Gone

Startup — agent is managed automatically via the \NT8Agent scheduled task:
    ssh forexvps "schtasks /run /tn NT8Agent"   # start/restart from Mac

The task runs in the active RDP session (interactive desktop), which is required
for pywinauto UI automation. NT8 + Strategy Analyzer must already be open.

Access from Mac via SSH tunnel:
    ssh -N -L 8765:localhost:8765 forexvps
    curl http://localhost:8765/health
"""

import sys
import csv
import json
import time
import uuid
import threading
import subprocess
from pathlib import Path

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("ERROR: flask not installed. Run: pip install flask")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
PORT       = 8765
NT8_DOCS   = Path.home() / "Documents" / "NinjaTrader 8"
NT8_LOG    = NT8_DOCS / "log"

app = Flask(__name__)

_agent_log: list = []
_jobs: dict      = {}   # job_id → job dict
_lock            = threading.Lock()


# ── Logging helpers ───────────────────────────────────────────────────────────

def _alog(msg: str):
    ts    = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    with _lock:
        _agent_log.append(entry)
        if len(_agent_log) > 1000:
            _agent_log.pop(0)
    print(entry, flush=True)


def _jlog(job_id: str, msg: str):
    ts    = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    _alog(f"[{job_id[:8]}] {msg}")
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["log"].append(entry)
            if len(_jobs[job_id]["log"]) > 500:
                _jobs[job_id]["log"].pop(0)


def _jupdate(job_id: str, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)
            _jobs[job_id]["updated_at"] = time.time()


# ── CORS ──────────────────────────────────────────────────────────────────────

@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>",             methods=["OPTIONS"])
def _options(path):
    return "", 204


# ── Observability ─────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    running = sum(1 for j in _jobs.values() if j["status"] == "running")
    return jsonify({"status": "ok", "running_jobs": running})


def _enum_window_titles() -> list[str]:
    """Enumerate top-level window titles via raw ctypes — no COM, no pywinauto."""
    import ctypes
    titles: list[str] = []
    buf = ctypes.create_unicode_buffer(512)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _):
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value:
            titles.append(buf.value)
        return True

    ctypes.windll.user32.EnumWindows(_cb, None)
    return titles


@app.route("/nt-health")
def nt_health():
    """Process-level check (tasklist) + SA window check (EnumWindows via ctypes)."""
    result = {"nt8_running": False, "sa_visible": False, "error": None}
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq NinjaTrader.exe", "/NH"],
            text=True, timeout=10, stderr=subprocess.DEVNULL,
        )
        result["nt8_running"] = "NinjaTrader.exe" in out
    except Exception as e:
        result["error"] = str(e)
        return jsonify(result)
    try:
        titles = _enum_window_titles()
        result["sa_visible"] = any("Strategy Analyzer" in t for t in titles)
    except Exception as e:
        result["error"] = f"win32: {e}"
    return jsonify(result)


@app.route("/nt-compile-status")
def nt_compile_status():
    """Best-effort parse of the most recent NT8 log for compile results."""
    result = {"ok": None, "at": None, "errors": [], "checked_at": time.time()}
    try:
        logs = sorted(NT8_LOG.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not logs:
            result["errors"] = ["No NT8 log files found"]
            return jsonify(result)
        lines = logs[0].read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
        errors, last_ok = [], None
        for line in reversed(lines):
            ll = line.lower()
            if "compile error" in ll or "compilation failed" in ll:
                errors.append(line.strip())
                if len(errors) >= 10:
                    break
            elif "compilation succeeded" in ll or "compile succeeded" in ll:
                last_ok = line.strip()
                break
        result["ok"]     = len(errors) == 0 and last_ok is not None
        result["errors"] = errors
        result["at"]     = last_ok
    except Exception as e:
        result["errors"] = [str(e)]
    return jsonify(result)


@app.route("/nt-log")
def nt_log():
    lines = int(request.args.get("lines", 200))
    try:
        logs = sorted(NT8_LOG.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not logs:
            return jsonify({"log": ""})
        content = logs[0].read_text(encoding="utf-8", errors="replace").splitlines()
        return jsonify({"log": "\n".join(content[-lines:])})
    except Exception as e:
        return jsonify({"log": f"Error reading NT8 log: {e}"})


@app.route("/agent-log")
def agent_log():
    lines = int(request.args.get("lines", 200))
    with _lock:
        tail = list(_agent_log[-lines:])
    return jsonify({"log": "\n".join(tail)})


# ── Strategy file management ──────────────────────────────────────────────────

STRATEGIES_DIR   = NT8_DOCS / "bin" / "Custom" / "Strategies"
MAX_UPLOAD_BYTES = 256 * 1024  # 256 KB — NinjaScript files are typically 5–30 KB


def _is_locked(filepath: Path) -> bool:
    """Try to open the file for writing; IOError means NT8 has it locked."""
    try:
        with open(filepath, "r+b"):
            pass
        return False
    except IOError:
        return True


def _file_info(p: Path, platform: str = "NT8") -> dict:
    st = p.stat()
    import datetime
    return {
        "filename":    p.name,
        "size_bytes":  st.st_size,
        "modified_at": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
        "platform":    platform,
    }


@app.route("/files/strategies")
def list_strategy_files():
    try:
        files = [_file_info(p) for p in sorted(STRATEGIES_DIR.glob("*.cs"))]
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/files/strategies/<filename>", methods=["POST"])
def upload_strategy_file(filename):
    if not filename.endswith(".cs"):
        return jsonify({"error": "Only .cs files are allowed"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file in request"}), 400

    f = request.files["file"]
    content = f.read()

    if len(content) > MAX_UPLOAD_BYTES:
        return jsonify({"error": f"File exceeds 256 KB limit ({len(content)} bytes)"}), 400

    overwrite = request.form.get("overwrite", "false").lower() in ("true", "1", "yes")
    dest = STRATEGIES_DIR / filename

    if dest.exists():
        if not overwrite:
            return jsonify({"error": "File already exists", "filename": filename}), 409
        if _is_locked(dest):
            return jsonify({
                "error": "File is in use by NT8. Stop the running strategy or close it from charts before redeploying."
            }), 423

    dest.write_bytes(content)
    _alog(f"Uploaded {filename} ({len(content)} bytes, overwrite={overwrite})")
    return jsonify(_file_info(dest))


@app.route("/files/strategies/<filename>", methods=["DELETE"])
def delete_strategy_file(filename):
    if not filename.endswith(".cs"):
        return jsonify({"error": "Only .cs files are allowed"}), 400

    dest = STRATEGIES_DIR / filename
    if not dest.exists():
        return jsonify({"error": "File not found"}), 404

    if _is_locked(dest):
        return jsonify({
            "error": "File is in use by NT8. Stop the running strategy or close it from charts first."
        }), 423

    dest.unlink()
    _alog(f"Deleted {filename}")
    return jsonify({"deleted": True, "filename": filename})


# ── Compile (pywinauto F5) ────────────────────────────────────────────────────

_compile_jobs: dict = {}   # compile_job_id → result dict


def _run_compile(compile_job_id: str):
    """
    Launch nt8_compile_runner.py as a subprocess so pywinauto COM is
    initialized in a fresh process (same pattern as the backtest runner).
    """
    _alog(f"Compile job {compile_job_id[:8]}: starting")
    _compile_jobs[compile_job_id]["status"] = "running"

    runner = SCRIPT_DIR / "nt8_compile_runner.py"
    errors, warnings = [], []
    status = "running"

    try:
        # Explicitly set the interactive desktop so pywinauto can move the mouse.
        # Without this, piped subprocesses get no desktop access and click_input fails.
        si = subprocess.STARTUPINFO()
        si.lpDesktop = "winsta0\\default"
        proc = subprocess.Popen(
            [sys.executable, "-u", str(runner)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            startupinfo=si,
        )
        for line in proc.stdout:
            line = line.rstrip()
            _alog(f"[compile {compile_job_id[:8]}] {line}")
            if line.startswith("STATUS:"):
                status = line[7:]
            elif line.startswith("ERROR:"):
                errors.append(line[6:])
            elif line.startswith("WARNING:"):
                warnings.append(line[8:])
        proc.wait()
        if status == "running":
            status = "failed" if proc.returncode != 0 else "success"
    except Exception as e:
        status = "failed"
        errors.append(f"Runner launch failed: {e}")

    _compile_jobs[compile_job_id].update({
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "completed_at": time.time(),
    })
    _alog(f"Compile job {compile_job_id[:8]}: {status} ({len(errors)} errors)")


@app.route("/compile", methods=["POST"])
def trigger_compile():
    compile_job_id = str(uuid.uuid4())
    _compile_jobs[compile_job_id] = {
        "compile_job_id": compile_job_id,
        "status": "running",
        "errors": [],
        "warnings": [],
        "started_at": time.time(),
        "completed_at": None,
    }
    threading.Thread(target=_run_compile, args=(compile_job_id,), daemon=True).start()
    return jsonify({"compile_job_id": compile_job_id}), 202


@app.route("/compile/<compile_job_id>")
def compile_status(compile_job_id):
    job = _compile_jobs.get(compile_job_id)
    if not job:
        return jsonify({"error": "Compile job not found"}), 404
    return jsonify(job)


# ── Job control ───────────────────────────────────────────────────────────────

@app.route("/native-optimize", methods=["POST"])
def start_native_optimize():
    """
    Submit a native optimizer job.

    Body: same shape as /backtest but with param_ranges and fixed_params instead
    of a flat params dict.  job_id is required; the runner switches SA to
    Optimization mode and executes the full param grid in one NT8 pass.
    """
    spec   = request.get_json(silent=True) or {}
    job_id = spec.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id required"}), 400
    required = ["strategy_class", "instrument", "start_date", "end_date"]
    missing  = [k for k in required if k not in spec]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    if not spec.get("param_ranges"):
        return jsonify({"error": "param_ranges cannot be empty"}), 400
    with _lock:
        if job_id in _jobs and _jobs[job_id]["status"] == "running":
            return jsonify({"error": "Job already running"}), 409
        _jobs[job_id] = {
            "job_id":     job_id,
            "status":     "running",
            "pct":        0,
            "message":    "Starting native optimizer...",
            "started_at": time.time(),
            "updated_at": time.time(),
            "log":        [],
            "result":     None,
            "error":      None,
        }
    _alog(f"Native opt job {job_id} submitted: {spec['strategy_class']} on {spec['instrument']}")
    threading.Thread(target=_run_native_opt_job, args=(job_id, spec), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/jobs/<job_id>/native-opt-results")
def native_opt_results(job_id):
    """Return the native optimizer result grid (list of combos with params + KPIs)."""
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "running":
        return jsonify({"error": "Job still running"}), 202
    results_path = NT8_DOCS / "lab_results" / job_id / "native_opt_result.json"
    if not results_path.exists():
        return jsonify({"error": "No native opt result file", "status": job["status"]}), 404
    try:
        return jsonify(json.loads(results_path.read_text(encoding="utf-8")))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/native-walkforward", methods=["POST"])
def start_native_walkforward():
    """
    Submit a native walk-forward job.

    Body: job_id, strategy_class, instrument, start_date, end_date, params (flat dict),
    wf_windows (default 5), oos_pct (default 30).
    All params are run as fixed values — no re-optimization per IS window.
    """
    spec   = request.get_json(silent=True) or {}
    job_id = spec.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id required"}), 400
    required = ["strategy_class", "instrument", "start_date", "end_date"]
    missing  = [k for k in required if k not in spec]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    with _lock:
        if job_id in _jobs and _jobs[job_id]["status"] == "running":
            return jsonify({"error": "Job already running"}), 409
        _jobs[job_id] = {
            "job_id":     job_id,
            "status":     "running",
            "pct":        0,
            "message":    "Starting native walk-forward...",
            "started_at": time.time(),
            "updated_at": time.time(),
            "log":        [],
            "result":     None,
            "error":      None,
        }
    _alog(f"Native WF job {job_id} submitted: {spec['strategy_class']} on {spec['instrument']}")
    threading.Thread(target=_run_native_wf_job, args=(job_id, spec), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/jobs/<job_id>/native-wf-results")
def native_wf_results(job_id):
    """Return the native walk-forward result (per-window IS/OOS metrics)."""
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "running":
        return jsonify({"error": "Job still running"}), 202
    results_path = NT8_DOCS / "lab_results" / job_id / "native_wf_result.json"
    if not results_path.exists():
        return jsonify({"error": "No native WF result file", "status": job["status"]}), 404
    try:
        return jsonify(json.loads(results_path.read_text(encoding="utf-8")))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/backtest", methods=["POST"])
def start_backtest():
    spec   = request.get_json(silent=True) or {}
    job_id = spec.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id required"}), 400
    required = ["strategy_class", "instrument", "start_date", "end_date"]
    missing  = [k for k in required if k not in spec]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    with _lock:
        if job_id in _jobs and _jobs[job_id]["status"] == "running":
            return jsonify({"error": "Job already running"}), 409
        _jobs[job_id] = {
            "job_id":     job_id,
            "status":     "running",
            "pct":        0,
            "message":    "Starting...",
            "started_at": time.time(),
            "updated_at": time.time(),
            "log":        [],
            "result":     None,
            "error":      None,
        }
    _alog(f"Job {job_id} submitted: {spec['strategy_class']} on {spec['instrument']}")
    threading.Thread(target=_run_job, args=(job_id, spec), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/jobs/<job_id>/status")
def job_status(job_id):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    with _lock:
        snap = {k: v for k, v in job.items() if k != "log"}
    return jsonify(snap)


@app.route("/jobs/<job_id>/results")
def job_results(job_id):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] == "running":
        return jsonify({"error": "Job still running"}), 202
    results_path = NT8_DOCS / "lab_results" / job_id / "result.json"
    if not results_path.exists():
        return jsonify({"error": "No result file", "status": job["status"]}), 404
    try:
        return jsonify(json.loads(results_path.read_text(encoding="utf-8")))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/jobs/<job_id>/log")
def job_log(job_id):
    lines = int(request.args.get("lines", 200))
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    with _lock:
        tail = list(job["log"][-lines:])
    return jsonify({"log": "\n".join(tail)})


@app.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "running":
        return jsonify({"error": "Job not running", "status": job["status"]}), 409
    _jupdate(job_id, status="failed_timeout", error="Cancelled by user", message="Cancelled")
    _alog(f"Job {job_id} cancelled by user")
    return jsonify({"ok": True})


# ── Background job runner ─────────────────────────────────────────────────────

def _run_job(job_id: str, spec: dict):
    runner    = str(SCRIPT_DIR / "nt8_backtest_runner.py")
    spec_dir  = NT8_DOCS / "lab_results" / job_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / "job_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    cmd = [sys.executable, "-u", runner,
           "--job-id", job_id,
           "--job-spec", str(spec_path)]
    _jlog(job_id, f"CMD: {' '.join(cmd)}")
    _jupdate(job_id, pct=5, message="Runner started")

    # Heartbeat — keeps updated_at fresh so the backend can detect stalls
    stop_hb = threading.Event()
    def _heartbeat():
        while not stop_hb.wait(30):
            with _lock:
                if _jobs.get(job_id, {}).get("status") == "running":
                    _jobs[job_id]["updated_at"] = time.time()
    threading.Thread(target=_heartbeat, daemon=True).start()

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            line = line.rstrip()
            _jlog(job_id, line)
            if line.startswith("PCT:"):
                try:
                    parts = line.split(":", 2)
                    pct   = int(parts[1])
                    msg   = parts[2] if len(parts) > 2 else ""
                    _jupdate(job_id, pct=pct, message=msg)
                except Exception:
                    pass
        proc.wait()
    except Exception as e:
        stop_hb.set()
        _jupdate(job_id, status="failed_runtime", error=str(e),
                 message=f"Runner launch failed: {e}")
        _alog(f"Job {job_id} launch error: {e}")
        return
    finally:
        stop_hb.set()

    # If cancel() was called mid-run, leave the status it set
    if _jobs.get(job_id, {}).get("status") != "running":
        return

    results_path = spec_dir / "result.json"
    if proc.returncode == 0 and results_path.exists():
        _jupdate(job_id, status="complete", pct=100, message="Complete")
        _alog(f"Job {job_id} complete")
    else:
        with _lock:
            log_text = "\n".join(_jobs.get(job_id, {}).get("log", []))
        _classify_failure(job_id, log_text, proc.returncode)


def _run_native_wf_job(job_id: str, spec: dict):
    """Background runner for /native-walkforward — same pattern as _run_native_opt_job."""
    runner    = str(SCRIPT_DIR / "nt8_backtest_runner.py")
    spec_dir  = NT8_DOCS / "lab_results" / job_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / "job_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    cmd = [sys.executable, "-u", runner,
           "--mode", "native-walkforward",
           "--job-id", job_id,
           "--job-spec", str(spec_path)]
    _jlog(job_id, f"CMD: {' '.join(cmd)}")
    _jupdate(job_id, pct=5, message="Native walk-forward started")

    stop_hb = threading.Event()
    def _heartbeat():
        while not stop_hb.wait(30):
            with _lock:
                if _jobs.get(job_id, {}).get("status") == "running":
                    _jobs[job_id]["updated_at"] = time.time()
    threading.Thread(target=_heartbeat, daemon=True).start()

    try:
        si = subprocess.STARTUPINFO()
        si.lpDesktop = "winsta0\\default"
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            startupinfo=si,
        )
        for line in proc.stdout:
            line = line.rstrip()
            _jlog(job_id, line)
            if line.startswith("PCT:"):
                try:
                    parts = line.split(":", 2)
                    pct   = int(parts[1])
                    msg   = parts[2] if len(parts) > 2 else ""
                    _jupdate(job_id, pct=pct, message=msg)
                    if pct == 100:
                        wf_results_path_early = spec_dir / "native_wf_result.json"
                        if wf_results_path_early.exists():
                            _jupdate(job_id, status="complete", pct=100, message="Complete")
                            _alog(f"Native WF job {job_id} complete (PCT:100)")
                except Exception:
                    pass
        proc.wait()
    except Exception as e:
        stop_hb.set()
        _jupdate(job_id, status="failed_runtime", error=str(e),
                 message=f"Runner launch failed: {e}")
        _alog(f"Native WF job {job_id} launch error: {e}")
        return
    finally:
        stop_hb.set()

    if _jobs.get(job_id, {}).get("status") != "running":
        return

    results_path = spec_dir / "native_wf_result.json"
    if proc.returncode == 0 and results_path.exists():
        _jupdate(job_id, status="complete", pct=100, message="Complete")
        _alog(f"Native WF job {job_id} complete")
    else:
        with _lock:
            log_text = "\n".join(_jobs.get(job_id, {}).get("log", []))
        _classify_failure(job_id, log_text, proc.returncode)


def _run_native_opt_job(job_id: str, spec: dict):
    """Background runner for /native-optimize — same pattern as _run_job."""
    runner    = str(SCRIPT_DIR / "nt8_backtest_runner.py")
    spec_dir  = NT8_DOCS / "lab_results" / job_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / "job_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    cmd = [sys.executable, "-u", runner,
           "--mode", "native-optimize",
           "--job-id", job_id,
           "--job-spec", str(spec_path)]
    _jlog(job_id, f"CMD: {' '.join(cmd)}")
    _jupdate(job_id, pct=5, message="Native optimizer started")

    stop_hb = threading.Event()
    def _heartbeat():
        while not stop_hb.wait(30):
            with _lock:
                if _jobs.get(job_id, {}).get("status") == "running":
                    _jobs[job_id]["updated_at"] = time.time()
    threading.Thread(target=_heartbeat, daemon=True).start()

    try:
        si = subprocess.STARTUPINFO()
        si.lpDesktop = "winsta0\\default"
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            startupinfo=si,
        )
        for line in proc.stdout:
            line = line.rstrip()
            _jlog(job_id, line)
            if line.startswith("PCT:"):
                try:
                    parts = line.split(":", 2)
                    pct   = int(parts[1])
                    msg   = parts[2] if len(parts) > 2 else ""
                    _jupdate(job_id, pct=pct, message=msg)
                    # Mark complete immediately when PCT:100 arrives and results
                    # file exists — don't wait for subprocess exit.  On Windows,
                    # inherited pipe handles can keep the write-end open after
                    # os._exit(0), so the for-loop may never see EOF.
                    if pct == 100:
                        results_path_early = spec_dir / "native_opt_result.json"
                        if results_path_early.exists():
                            _jupdate(job_id, status="complete", pct=100, message="Complete")
                            _alog(f"Native opt job {job_id} complete (PCT:100)")
                except Exception:
                    pass
        proc.wait()
    except Exception as e:
        stop_hb.set()
        _jupdate(job_id, status="failed_runtime", error=str(e),
                 message=f"Runner launch failed: {e}")
        _alog(f"Native opt job {job_id} launch error: {e}")
        return
    finally:
        stop_hb.set()

    if _jobs.get(job_id, {}).get("status") != "running":
        return

    results_path = spec_dir / "native_opt_result.json"
    if proc.returncode == 0 and results_path.exists():
        _jupdate(job_id, status="complete", pct=100, message="Complete")
        _alog(f"Native opt job {job_id} complete")
    else:
        with _lock:
            log_text = "\n".join(_jobs.get(job_id, {}).get("log", []))
        _classify_failure(job_id, log_text, proc.returncode)


def _classify_failure(job_id: str, log_text: str, returncode: int):
    lt     = log_text.lower()
    status = "failed_unknown"
    if "compile error" in lt or "compilation failed" in lt:
        status = "failed_compile"
    elif "not found in nt8" in lt or ("strategy" in lt and "not found" in lt):
        status = "failed_strategy_not_found"
    elif "no data" in lt or "no historical data" in lt or "insufficient data" in lt:
        status = "failed_no_data"
    elif "strategy analyzer" not in lt and returncode != 0:
        status = "failed_nt_crash"
    elif "timed out" in lt or "timeout" in lt:
        status = "failed_timeout"
    elif returncode != 0:
        status = "failed_runtime"

    # Extract the last ERROR: line from the log as the human-readable message
    error_lines = [l for l in log_text.splitlines() if "ERROR:" in l]
    error_msg = error_lines[-1].split("ERROR:", 1)[-1].strip() if error_lines else f"Exit code {returncode}"

    _jupdate(job_id, status=status,
             message=status.replace("_", " ").title(),
             error=error_msg)
    _alog(f"Job {job_id} classified as {status}: {error_msg}")


# ── Legacy endpoints ──────────────────────────────────────────────────────────

@app.route("/status")
def legacy_status():
    running = any(j["status"] == "running" for j in _jobs.values())
    with _lock:
        return jsonify({"running": running, "log": list(_agent_log[-200:])})


@app.route("/run-backtests", methods=["POST"])
def legacy_run_backtests():
    return jsonify({"error": "Deprecated. Use POST /backtest with job_id."}), 410


@app.route("/results")
def legacy_results():
    path = NT8_DOCS / "nt8_results.csv"
    if not path.exists():
        return jsonify({"error": "No results file yet", "rows": []}), 404
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return jsonify({"rows": rows})


# ── Diagnostic endpoints ──────────────────────────────────────────────────────

@app.route("/diagnose")
def diagnose():
    try:
        titles = _enum_window_titles()
        return jsonify({"windows": titles})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/dump-sa")
def dump_sa():
    try:
        from pywinauto import Desktop
        sa = Desktop(backend="uia").window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        controls = []
        for el in sa.descendants():
            title = el.window_text()
            aid   = el.element_info.automation_id
            ctype = el.element_info.control_type
            if title or aid:
                controls.append({"title": title, "control_type": ctype, "auto_id": aid})
        return jsonify({"controls": controls})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/select-and-dump")
def select_and_dump():
    strategy = request.args.get("strategy", "")
    if not strategy:
        return jsonify({"error": "Pass ?strategy=StrategyName"}), 400
    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
        sa = Desktop(backend="uia").window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        selector = sa.child_window(auto_id="NinjaScriptSelector")
        selector.click_input()
        time.sleep(1.5)
        # Try SA subtree first; fall back to Desktop (WPF popup moves top-level after first run)
        try:
            item = sa.child_window(title=strategy, control_type="MenuItem", found_index=0)
            if not item.exists(timeout=0.5):
                raise Exception("not in SA subtree")
        except Exception:
            item = Desktop(backend="uia").window(title=strategy, control_type="MenuItem", found_index=0)
        item.click_input()
        time.sleep(2.0)
        controls = []
        for el in sa.descendants():
            title = el.window_text()
            aid   = el.element_info.automation_id
            ctype = el.element_info.control_type
            if title or aid:
                controls.append({"title": title, "control_type": ctype, "auto_id": aid})
        return jsonify({"strategy": strategy, "controls": controls})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/export-trades")
def export_trades():
    """
    Export all trades from NT8 Strategy Analyzer Trades grid to CSV.

    Two-pass right-click: pass 1 opens the context menu and scans the NT8 UIA
    tree for the Export menu item's absolute screen coordinates (menu closes
    during the scan — that's fine). Pass 2 re-opens the menu and immediately
    clicks the discovered coordinates. No caching — absolute coordinates drift
    if the SA window moves between calls, causing misclicks on adjacent items.
    """
    log = []

    def _dismiss_export_dialog(dt):
        for title in ["Export As", "Confirm Save As", "Confirm"]:
            try:
                w = dt.window(title=title)
                if w.exists(timeout=0.1):
                    for btn in ["Cancel", "No", "OK"]:
                        try:
                            w.child_window(title=btn, control_type="Button").click_input()
                            return
                        except Exception:
                            pass
                    w.close()
            except Exception:
                pass

    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
        import pywinauto.mouse as _mouse

        dt = Desktop(backend="uia")
        _dismiss_export_dialog(dt)
        time.sleep(0.1)

        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        try:
            sa.restore()
            time.sleep(0.3)
        except Exception:
            pass
        log.append("SA found")

        # Switch Display → Trades
        sa.child_window(auto_id="dmsDisplay").click_input()
        time.sleep(0.5)
        sa.child_window(title="Trades", control_type="MenuItem", found_index=0).click_input()
        time.sleep(0.3)
        log.append("Display switched to Trades")

        sa.set_focus()
        time.sleep(0.1)
        sa_rect = sa.rectangle()
        rc_x = sa_rect.left + (sa_rect.right  - sa_rect.left) // 4
        rc_y = sa_rect.top  + int((sa_rect.bottom - sa_rect.top) * 0.55)

        # Pass 1: open context menu, scan NT8 UIA tree for Export item coordinates.
        # The scan dismisses the WPF popup via focus events — that's expected.
        # We capture the absolute position before the menu closes.
        nt8 = sa.top_level_parent()
        export_coords = None
        menu_items    = []
        _mouse.right_click(coords=(rc_x, rc_y))
        for el in nt8.descendants():
            try:
                txt = (el.window_text() or "").strip()
                ct  = str(getattr(el.element_info, "control_type", ""))
                if ct == "MenuItem" and txt:
                    menu_items.append(txt)
                    if txt.startswith("Export") and export_coords is None:
                        r = el.rectangle()
                        if r.width() > 5:
                            export_coords = ((r.left + r.right) // 2,
                                             (r.top  + r.bottom) // 2)
                            break
            except Exception:
                pass
        log.append(f"Menu items: {menu_items}, Export coords: {export_coords}")

        if export_coords is None:
            send_keys("{ESCAPE}")
            return jsonify({"error": "Export... not found", "log": log, "menu_items": menu_items})

        # Pass 2: re-open menu and immediately click Export at the discovered position.
        _mouse.right_click(coords=(rc_x, rc_y))
        time.sleep(0.4)
        _mouse.click(coords=export_coords)
        log.append(f"Clicked Export at {export_coords}")

        # Step 3: Export As dialog — Enter saves, second Enter handles overwrite confirm.
        time.sleep(0.8)
        send_keys("{ENTER}")
        time.sleep(0.3)
        send_keys("{ENTER}")

        time.sleep(0.4)

        # Always close the Export As dialog before returning (clean state for next run)
        _dismiss_export_dialog(dt)

        # Step 5: find the most recently created CSV in Documents (NT8 default save location)
        docs = Path.home() / "Documents"
        csvs = sorted(docs.glob("NinjaTrader Grid*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not csvs:
            return jsonify({"error": "No NinjaTrader Grid CSV found in Documents", "log": log})
        out_path = str(csvs[0])
        log.append(f"Found CSV: {csvs[0].name}")

        with open(out_path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        lines = content.splitlines()
        log.append(f"CSV lines: {len(lines)}")
        return jsonify({"ok": True, "log": log, "total_lines": len(lines),
                        "header": lines[0] if lines else "", "csv": content})

    except Exception as e:
        import traceback
        try:
            _dismiss_export_dialog(dt)
        except Exception:
            pass
        return jsonify({"error": str(e), "traceback": traceback.format_exc(), "log": log})


@app.route("/probe-display")
def probe_display():
    """Click dmsDisplay, wait, dump what's visible in SA + Desktop. Use to confirm Trades item type."""
    try:
        from pywinauto import Desktop
        dt  = Desktop(backend="uia")
        sa  = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        nt8 = sa.top_level_parent()

        display_ctrl = sa.child_window(auto_id="dmsDisplay")
        rect = str(display_ctrl.rectangle())
        display_ctrl.click_input()
        time.sleep(1.2)

        results = {"dmsDisplay_rect": rect, "found_in_sa": [], "found_in_nt8": [], "found_in_desktop": [], "new_windows": []}

        wins_before = {w.handle for w in dt.windows()}

        for label, root, key in [("sa", sa, "found_in_sa"), ("nt8", nt8, "found_in_nt8")]:
            for el in root.descendants():
                try:
                    txt = (el.window_text() or "").strip()
                    if txt:
                        results[key].append({
                            "text": txt,
                            "control_type": str(getattr(el.element_info, "control_type", "?")),
                            "auto_id": (el.automation_id() or "").strip(),
                        })
                except Exception:
                    pass

        wins_after  = {w.handle for w in dt.windows()}
        new_handles = wins_after - wins_before
        for hwnd in new_handles:
            try:
                popup = dt.window(handle=hwnd)
                popup_info = {"title": popup.window_text(), "children": []}
                for el in popup.descendants():
                    try:
                        txt = (el.window_text() or "").strip()
                        if txt:
                            popup_info["children"].append({
                                "text": txt,
                                "control_type": str(getattr(el.element_info, "control_type", "?")),
                                "auto_id": (el.automation_id() or "").strip(),
                            })
                    except Exception:
                        pass
                results["new_windows"].append(popup_info)
            except Exception as e:
                results["new_windows"].append({"error": str(e)})

        # Close the dropdown
        display_ctrl.click_input()
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})


_BACKTEST_TYPE_AID = "StrategyAnalyzerTabPropertiesPropertyGridEditorBacktestType"


def _switch_to_opt_mode_and_select(sa, strategy: str, dt) -> str:
    """Switch SA to Optimize mode, select strategy, return observed BacktestType value."""
    bt_combo = sa.child_window(auto_id=_BACKTEST_TYPE_AID, control_type="ComboBox")
    bt_combo.select("Optimize")
    time.sleep(0.5)
    val_before_select = bt_combo.selected_text() if hasattr(bt_combo, "selected_text") else bt_combo.window_text()
    _alog(f"[diag] BacktestType after set (before strategy select): {val_before_select!r}")

    selector = sa.child_window(auto_id="NinjaScriptSelector")
    selector.click_input()
    time.sleep(1.5)
    try:
        item = sa.child_window(title=strategy, control_type="MenuItem", found_index=0)
        if not item.exists(timeout=0.5):
            raise Exception("not in SA subtree")
    except Exception:
        item = dt.window(title=strategy, control_type="MenuItem", found_index=0)
    item.click_input()
    time.sleep(3.0)

    try:
        val_after_select = bt_combo.selected_text() if hasattr(bt_combo, "selected_text") else bt_combo.window_text()
    except Exception:
        val_after_select = "read-failed"
    _alog(f"[diag] BacktestType after strategy select: {val_after_select!r}")
    return val_after_select


@app.route("/combo-items")
def combo_items():
    """
    Diagnostic: list all items in a ComboBox by AutomationId.

    Query params:
        ?aid=StrategyAnalyzerTabPropertiesPropertyGridEditorBacktestType
    """
    aid = request.args.get("aid", "")
    if not aid:
        return jsonify({"error": "Pass ?aid=AutomationId"}), 400
    try:
        from pywinauto import Desktop
        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        combo = sa.child_window(auto_id=aid, control_type="ComboBox")
        combo.expand()
        time.sleep(0.3)
        items = []
        for el in combo.descendants(control_type="ListItem"):
            items.append({"title": el.window_text(), "aid": el.element_info.automation_id})
        combo.collapse()
        current = combo.window_text()
        return jsonify({"aid": aid, "current": current, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/test-bt-switch")
def test_bt_switch():
    """
    Diagnostic: try every method to switch BacktestType, return a log of what worked.

    Query params:
        ?value=Optimize   (default: Optimize)
    """
    BT_AID   = "StrategyAnalyzerTabPropertiesPropertyGridEditorBacktestType"
    BT_ORDER = ["Backtest", "Optimize", "WalkForward", "WalkForwardAnchored", "MultiObjective", "AiGenerate"]
    target   = request.args.get("value", "Optimize")
    log      = []

    def L(msg):
        _alog(f"[test-bt-switch] {msg}")
        log.append(msg)

    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
        dt   = Desktop(backend="uia")
        sa   = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        ctrl = sa.child_window(auto_id=BT_AID, control_type="ComboBox")
        if not ctrl.exists(timeout=2.0):
            return jsonify({"error": "BacktestType combo not found", "log": log})

        L(f"combo exists; window_text={ctrl.window_text()!r}")

        # Attempt 1: select()
        try:
            ctrl.select(target)
            L(f"A1 select('{target}') SUCCESS")
            return jsonify({"winner": "select()", "log": log})
        except Exception as e:
            L(f"A1 select() FAIL: {e}")

        # Attempt 2: expand + ctrl.descendants
        try:
            ctrl.expand()
            time.sleep(0.4)
            items = ctrl.descendants(control_type="ListItem")
            L(f"A2 expand+descendants: {[i.window_text() for i in items]}")
            for item in items:
                if item.window_text() == target:
                    item.click_input()
                    L(f"A2 click_input SUCCESS")
                    return jsonify({"winner": "expand+descendants", "log": log})
            try:
                ctrl.collapse()
            except Exception:
                ctrl.type_keys('{ESC}')
            L("A2 item not found in descendants")
        except Exception as e:
            L(f"A2 FAIL: {e}")

        # Attempt 3: expand + search all windows
        try:
            ctrl.expand()
            time.sleep(0.4)
            wins = dt.windows()
            L(f"A3 searching {len(wins)} windows")
            found = False
            for win in wins:
                try:
                    items = win.descendants(control_type="ListItem")
                    if items:
                        labels = [i.window_text() for i in items]
                        L(f"  win={win.window_text()!r} items={labels}")
                        for item in items:
                            if item.window_text() == target:
                                item.click_input()
                                L("A3 click_input SUCCESS")
                                found = True
                                break
                except Exception:
                    pass
                if found:
                    return jsonify({"winner": "expand+all-windows", "log": log})
            try:
                ctrl.type_keys('{ESC}')
            except Exception:
                pass
            L("A3 item not found in any window")
        except Exception as e:
            L(f"A3 FAIL: {e}")

        # Attempt 4: keyboard via ctrl.type_keys
        try:
            idx = BT_ORDER.index(target)
            ctrl.click_input()
            time.sleep(0.2)
            ctrl.type_keys('{F4}')
            time.sleep(0.4)
            ctrl.type_keys('{HOME}')
            time.sleep(0.1)
            for _ in range(idx):
                ctrl.type_keys('{DOWN}')
                time.sleep(0.08)
            ctrl.type_keys('{ENTER}')
            time.sleep(0.3)
            L(f"A4 keyboard HOME+{idx}xDOWN+ENTER sent")
            return jsonify({"winner": "keyboard-ctrl", "log": log, "note": "check SA visually"})
        except Exception as e:
            L(f"A4 FAIL: {e}")

        # Attempt 5: send_keys system-wide
        try:
            idx = BT_ORDER.index(target)
            ctrl.set_focus()
            time.sleep(0.2)
            send_keys('{F4}')
            time.sleep(0.4)
            send_keys('{HOME}')
            time.sleep(0.1)
            for _ in range(idx):
                send_keys('{DOWN}')
                time.sleep(0.08)
            send_keys('{ENTER}')
            time.sleep(0.3)
            L(f"A5 send_keys HOME+{idx}xDOWN+ENTER sent")
            return jsonify({"winner": "send_keys", "log": log, "note": "check SA visually"})
        except Exception as e:
            L(f"A5 FAIL: {e}")

        return jsonify({"winner": None, "log": log})
    except Exception as e:
        return jsonify({"error": str(e), "log": log})


@app.route("/opt-param-groups")
def opt_param_groups():
    """
    Diagnostic: in Optimize mode, map every Group control title to its child
    txtBox value and any sibling ComboBox value.  Returns the full param→range
    layout so we know which display name maps to which param.

    Query params:
        ?strategy=ORB  (required)
    """
    strategy = request.args.get("strategy", "")
    if not strategy:
        return jsonify({"error": "Pass ?strategy=StrategyName"}), 400
    try:
        from pywinauto import Desktop
        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        _switch_to_opt_mode_and_select(sa, strategy, dt)

        # Flat ordered dump — Group labels and txtBox values are siblings.
        # Capture every element; post-process to pair each Group label with
        # the next txtBox (or ComboBox) that follows it in document order.
        all_els = list(sa.descendants())
        entries = []
        for i, el in enumerate(all_els):
            ct    = str(el.element_info.control_type)
            aid   = el.element_info.automation_id or ""
            title = el.window_text() or ""
            if ct in ("Group", "Edit", "ComboBox") or aid == "txtBox":
                entries.append({"idx": i, "type": ct, "aid": aid, "title": title})

        # Build param rows: each Group with a real title precedes its range control
        rows = []
        i = 0
        while i < len(entries):
            e = entries[i]
            if e["type"] == "Group" and e["title"] and e["title"] not in (
                "General", "Misc", "Strategy parameters", "Data Series",
                "Time frame", "Setup", "Historical fill processing",
                "Optimize", "Order handling", "Order properties", "template",
            ):
                row = {"label": e["title"], "idx": e["idx"], "txtbox_value": None,
                       "combo_value": None, "combo_items": []}
                # Peek ahead for the next Edit or ComboBox
                j = i + 1
                while j < len(entries) and entries[j]["type"] == "Group":
                    j += 1
                if j < len(entries):
                    nxt = entries[j]
                    if nxt["type"] == "Edit":
                        row["txtbox_value"] = nxt["title"]
                    elif nxt["type"] == "ComboBox":
                        row["combo_value"] = nxt["title"]
                        # Get combo items
                        try:
                            real_el = all_els[nxt["idx"]]
                            real_el.expand()
                            time.sleep(0.2)
                            row["combo_items"] = [
                                li.window_text()
                                for li in real_el.descendants(control_type="ListItem")
                            ]
                            real_el.collapse()
                        except Exception:
                            pass
                rows.append(row)
            i += 1
        return jsonify({"strategy": strategy, "rows": rows})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/backtest-type-check")
def backtest_type_check():
    """
    Diagnostic: switch to Optimization mode, select strategy, report BacktestType
    value before and after strategy selection.  Answers: does strategy selection
    reset BacktestType back to Backtest?

    Query params:
        ?strategy=ORB   (required)
    """
    strategy = request.args.get("strategy", "")
    if not strategy:
        return jsonify({"error": "Pass ?strategy=StrategyName"}), 400
    try:
        from pywinauto import Desktop
        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)

        bt_combo = sa.child_window(auto_id=_BACKTEST_TYPE_AID, control_type="ComboBox")
        try:
            initial = bt_combo.selected_text() if hasattr(bt_combo, "selected_text") else bt_combo.window_text()
        except Exception:
            initial = "read-failed"

        final = _switch_to_opt_mode_and_select(sa, strategy, dt)
        return jsonify({"initial": initial, "after_set": "Optimization", "after_strategy_select": final})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/opt-set-ranges-dry-run", methods=["POST"])
def opt_set_ranges_dry_run():
    """
    Diagnostic: switch SA to Optimize mode, select a strategy, then set the
    provided param ranges using the real _set_range_in_grid / _build_opt_grid_map
    logic from nt8_backtest_runner.  After setting, re-read the txtBox values
    to confirm what was written.  Does NOT click Run.

    Body JSON:
        {
            "strategy": "ORB",
            "param_ranges": {
                "ORMinutes":  {"min": 5,   "max": 60,  "step": 5},
                "TpMultiple": {"min": 0.5, "max": 5.0, "step": 0.5}
            },
            "param_display_names": {}   // optional explicit overrides
        }
    """
    body     = request.get_json(force=True, silent=True) or {}
    strategy = body.get("strategy", "")
    if not strategy:
        return jsonify({"error": "Pass 'strategy' in body"}), 400
    try:
        import sys
        sys.path.insert(0, str(SCRIPT_DIR))
        from nt8_backtest_runner import _build_opt_grid_map, _set_range_in_grid, _match_display_name
        from pywinauto import Desktop

        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        _switch_to_opt_mode_and_select(sa, strategy, dt)

        grid_map    = _build_opt_grid_map(sa)
        explicit    = body.get("param_display_names", {})
        param_ranges = body.get("param_ranges", {})

        results = []
        for name, rspec in param_ranges.items():
            if isinstance(rspec, dict):
                lo, hi, step = rspec["min"], rspec["max"], rspec["step"]
            elif isinstance(rspec, list) and rspec:
                lo, hi = rspec[0], rspec[-1]
                step = round(rspec[1] - rspec[0], 8) if len(rspec) > 1 else 1
            else:
                lo = hi = rspec; step = 1

            ok = _set_range_in_grid(grid_map, name, lo, hi, step, explicit)
            # Read back the written value
            written = None
            if ok:
                matched_key = _match_display_name(name, grid_map, explicit)
                if matched_key:
                    try:
                        written = grid_map[matched_key].window_text()
                    except Exception:
                        pass
            results.append({"param": name, "ok": ok, "written": written,
                            "expected": f"{lo};{hi};{step}"})

        return jsonify({"strategy": strategy, "grid_map_keys": list(grid_map.keys()),
                        "results": results})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/optimize-mode-dump")
def optimize_mode_dump():
    """
    Diagnostic: switch SA to Optimization mode, select a strategy, and dump all
    control AutomationIds.  Use to discover the exact IDs for param range fields
    before running the native optimizer for real.

    Query params:
        ?strategy=ORB   (required)
        ?all=1          include controls with no title AND no aid (default: skip them)
    """
    strategy = request.args.get("strategy", "")
    include_all = request.args.get("all", "0") == "1"
    if not strategy:
        return jsonify({"error": "Pass ?strategy=StrategyName"}), 400
    try:
        from pywinauto import Desktop
        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)

        final_bt = _switch_to_opt_mode_and_select(sa, strategy, dt)

        # Dump all controls, preserving order (reflects visual layout)
        controls = []
        for el in sa.descendants():
            title = el.window_text()
            aid   = el.element_info.automation_id
            ctype = str(el.element_info.control_type)
            if include_all or title or aid:
                controls.append({"title": title, "control_type": ctype, "auto_id": aid})
        return jsonify({
            "strategy": strategy,
            "backtest_type_after_select": final_bt,
            "total": len(controls),
            "controls": controls,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/opt-param-click-dump")
def opt_param_click_dump():
    """
    Diagnostic: in Optimization mode with a strategy loaded, click on a specific
    param cell, wait for the UI to update, then dump all new controls.

    Use this to discover the AutomationIds that appear when a param is selected
    for range editing (the Start/End/Increment sub-controls, if any).

    Query params:
        ?strategy=ORB   (required)
        ?param=ORMinutes  (required — the NinjaScript property name)
    """
    strategy   = request.args.get("strategy", "")
    param_name = request.args.get("param", "")
    if not strategy or not param_name:
        return jsonify({"error": "Pass ?strategy=X&param=Y"}), 400
    try:
        from pywinauto import Desktop
        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)

        # Must be in Optimization mode before clicking
        _switch_to_opt_mode_and_select(sa, strategy, dt)

        pfx = f"{strategy}PropertyGridEditorPDEX"
        param_aid = f"{pfx}_{param_name}"

        # Snapshot controls BEFORE click
        def _snap():
            out = {}
            for el in sa.descendants():
                aid   = el.element_info.automation_id or ""
                title = el.window_text() or ""
                ctype = str(el.element_info.control_type or "")
                if aid or title:
                    out[f"{aid}||{title}||{ctype}"] = {
                        "auto_id": aid, "title": title, "control_type": ctype
                    }
            return out

        before = _snap()

        # Click the param cell
        try:
            ctrl = sa.child_window(auto_id=param_aid)
            ctrl.click_input()
            _alog(f"[diag] Clicked {param_aid}")
        except Exception as e:
            return jsonify({"error": f"Could not click {param_aid}: {e}"})

        time.sleep(1.5)
        after = _snap()

        new_keys = set(after.keys()) - set(before.keys())
        new_controls = [after[k] for k in sorted(new_keys)]
        changed = [
            after[k] for k in (set(after.keys()) & set(before.keys()))
            if after[k]["title"] != before[k]["title"]
        ]

        return jsonify({
            "param_aid":      param_aid,
            "new_controls":   new_controls,
            "changed_titles": changed,
            "total_before":   len(before),
            "total_after":    len(after),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/export-grid-test")
def export_grid_test():
    """
    Diagnostic: right-click SA at ?y_pct=N (default 15) and report what menu
    items are found. If Export... is present, optionally click it (?do_export=1)
    and return the first line of the resulting CSV so we can verify the format.
    """
    import glob as _glob
    from pywinauto import mouse as _mouse, Desktop
    y_pct     = float(request.args.get("y_pct", 15))
    do_export = request.args.get("do_export", "0") == "1"
    try:
        dt = Desktop(backend="uia")
        sa = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=5)
        r  = sa.rectangle()
        sw = r.right  - r.left
        sh = r.bottom - r.top
        cx = r.left + int(sw * 0.25)
        cy = r.top  + int(sh * y_pct / 100)
        _alog(f"[export-grid-test] right-click at ({cx},{cy}) = ({25}%x, {y_pct}%y)")
        _mouse.right_click(coords=(cx, cy))
        time.sleep(0.5)
        nt8 = sa.top_level_parent()
        items = []
        export_coords = None
        for el in nt8.descendants():
            txt = (el.window_text() or "").strip()
            ct  = str(getattr(el.element_info, "control_type", ""))
            if ct == "MenuItem" and txt:
                er = el.rectangle()
                items.append(f"{txt}@{er.width()}x{er.height()}")
                if txt.startswith("Export") and er.width() > 5 and export_coords is None:
                    export_coords = ((er.left + er.right) // 2, (er.top + er.bottom) // 2)
        csv_first_line = None
        if do_export and export_coords:
            before_csvs = set(_glob.glob(str(Path.home() / "Documents" / "NinjaTrader Grid*.csv")))
            _mouse.right_click(coords=(cx, cy))
            time.sleep(0.4)
            _mouse.click(coords=export_coords)
            time.sleep(0.8)
            from pywinauto.keyboard import send_keys as _sk
            _sk("{ENTER}")
            time.sleep(0.3)
            _sk("{ENTER}")
            time.sleep(1.5)
            after_csvs = set(_glob.glob(str(Path.home() / "Documents" / "NinjaTrader Grid*.csv")))
            new_csvs = sorted(after_csvs - before_csvs, key=lambda p: p)
            if new_csvs:
                try:
                    with open(new_csvs[-1], encoding="utf-8-sig") as f:
                        csv_first_line = f.readline().strip()
                except Exception as e:
                    csv_first_line = f"read error: {e}"
        return jsonify({
            "click_pos": {"x": cx, "y": cy, "x_pct": 25, "y_pct": y_pct},
            "menu_items": items,
            "export_coords": export_coords,
            "csv_first_line": csv_first_line,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/clear-results", methods=["POST"])
def clear_results():
    path = NT8_DOCS / "nt8_results.csv"
    try:
        path.unlink(missing_ok=True)
        _alog("Results cleared.")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    _alog(f"NT8 Agent starting on port {PORT}...")
    _alog("NT8 must be running with Strategy Analyzer open.")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
