"""
VPS Agent — job-keyed HTTP bridge for NinjaTrader 8 backtests.

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
    GET  /results                   -- reads lucid_flex_results.csv
    POST /run-backtests             -- returns 410 Gone

Startup — agent is managed automatically via the \LucidFlexAgent scheduled task:
    ssh forexvps "schtasks /run /tn LucidFlexAgent"   # start/restart from Mac

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
CFG_PATH   = SCRIPT_DIR / "backtest_config.json"
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


def _file_info(p: Path) -> dict:
    st = p.stat()
    import datetime
    return {
        "filename":    p.name,
        "size_bytes":  st.st_size,
        "modified_at": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
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


NT8_CUSTOM_DLL = NT8_DOCS / "bin" / "Custom" / "NinjaTrader.Custom.dll"


def _open_ns_editor(dt):
    """Open NinjaScript Editor via NT8 Control Center's New menu.
    Returns the editor window.  Raises RuntimeError if it can't be opened."""
    # Check if it's already open
    try:
        ed = dt.window(title_re=".*NinjaScript Editor.*")
        ed.wait("visible", timeout=2)
        return ed
    except Exception:
        pass

    # Open via Control Center "New" menu — same pattern as SA
    cc = None
    for cc_pattern in [".*NinjaTrader 8.*", ".*Control Center.*"]:
        try:
            cc = dt.window(title_re=cc_pattern, control_type="Window")
            if cc.exists(timeout=1):
                break
        except Exception:
            continue
    if cc is None:
        raise RuntimeError("Could not find NT8 Control Center window")

    cc.set_focus()
    time.sleep(0.3)
    cc.child_window(title="New", control_type="MenuItem").click_input()
    time.sleep(0.8)
    dt.window(title="NinjaScript Editor", control_type="MenuItem").click_input()
    time.sleep(3.0)
    ed = dt.window(title_re=".*NinjaScript Editor.*")
    ed.wait("visible", timeout=10)
    return ed


def _run_compile(compile_job_id: str):
    """
    Open the NT8 NinjaScript Editor (or reuse the existing one), press F5
    to compile all strategies, and confirm success by watching the
    NinjaTrader.Custom.dll modification time.
    """
    _alog(f"Compile job {compile_job_id[:8]}: starting")
    _compile_jobs[compile_job_id]["status"] = "running"
    start_ts = time.time()

    pre_mtime = NT8_CUSTOM_DLL.stat().st_mtime if NT8_CUSTOM_DLL.exists() else 0

    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys

        dt = Desktop(backend="uia")
        ed = _open_ns_editor(dt)
        ed.set_focus()
        time.sleep(0.5)
        send_keys("{F5}")
        _alog(f"Compile job {compile_job_id[:8]}: F5 sent to NinjaScript Editor")
    except Exception as e:
        _compile_jobs[compile_job_id].update({
            "status": "failed",
            "errors": [f"Could not trigger compile: {e}"],
            "warnings": [],
            "completed_at": time.time(),
        })
        _alog(f"Compile job {compile_job_id[:8]}: setup error — {e}")
        return

    # Poll NinjaTrader.Custom.dll mtime — NT8 always rewrites it on successful compile.
    # Timeout 90 s to give the compiler time for large strategy sets.
    deadline = start_ts + 90
    while time.time() < deadline:
        time.sleep(3)
        if NT8_CUSTOM_DLL.exists() and NT8_CUSTOM_DLL.stat().st_mtime > pre_mtime:
            _compile_jobs[compile_job_id].update({
                "status": "success",
                "errors": [],
                "warnings": [],
                "completed_at": time.time(),
            })
            elapsed = round(time.time() - start_ts, 1)
            _alog(f"Compile job {compile_job_id[:8]}: success in {elapsed}s")
            return

    # Timed out — dll didn't update, likely a compile error.
    _compile_jobs[compile_job_id].update({
        "status": "failed",
        "errors": [
            "Compile did not complete within 90 s. "
            "Check the NinjaScript Editor output panel for errors."
        ],
        "warnings": [],
        "completed_at": time.time(),
    })
    _alog(f"Compile job {compile_job_id[:8]}: timed out (dll not updated)")


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
    runner    = str(SCRIPT_DIR / "vps_backtest_runner.py")
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


def _classify_failure(job_id: str, log_text: str, returncode: int):
    lt     = log_text.lower()
    status = "failed_unknown"
    if "compile error" in lt or "compilation failed" in lt:
        status = "failed_compile"
    elif "no data" in lt or "no historical data" in lt or "insufficient data" in lt:
        status = "failed_no_data"
    elif "strategy analyzer" not in lt and returncode != 0:
        status = "failed_nt_crash"
    elif "timed out" in lt or "timeout" in lt:
        status = "failed_timeout"
    elif returncode != 0:
        status = "failed_runtime"
    _jupdate(job_id, status=status,
             message=status.replace("_", " ").title(),
             error=f"Exit code {returncode}")
    _alog(f"Job {job_id} classified as {status}")


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
    path = NT8_DOCS / "lucid_flex_results.csv"
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


@app.route("/clear-results", methods=["POST"])
def clear_results():
    path = NT8_DOCS / "lucid_flex_results.csv"
    try:
        path.unlink(missing_ok=True)
        _alog("Results cleared.")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    _alog(f"VPS Agent starting on port {PORT}...")
    _alog(f"Config: {CFG_PATH}")
    _alog("NT8 must be running with Strategy Analyzer open.")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
