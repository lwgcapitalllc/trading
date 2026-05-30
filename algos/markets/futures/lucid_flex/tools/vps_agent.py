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

Usage on VPS (run from RDP terminal, NT8 must be open with Strategy Analyzer):
    python C:\\trading\\algos\\markets\\futures\\lucid_flex\\tools\\vps_agent.py

Access from Mac via SSH tunnel:
    ssh -N -L 8765:localhost:8765 forexvps
    curl http://localhost:8765/health
"""

import sys
import csv
import json
import time
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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
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
        item = sa.child_window(title=strategy, control_type="MenuItem", found_index=0)
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
    Switches Display→Trades, right-clicks grid, presses 'e' for Export immediately
    (before the context menu can dismiss), handles the Export As dialog, and
    returns the full CSV content.
    """
    import os
    out_dir  = NT8_DOCS / "lab_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / "trades_export.csv")
    log = []

    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys

        dt  = Desktop(backend="uia")
        sa  = dt.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        log.append("SA found")

        # Step 1: switch Display → Trades
        sa.child_window(auto_id="dmsDisplay").click_input()
        time.sleep(1.0)
        sa.child_window(title="Trades", control_type="MenuItem", found_index=0).click_input()
        time.sleep(0.8)
        log.append("Display switched to Trades")

        # Step 2: right-click inside the trades panel of the SA window.
        # Use SA window coords directly — grid.rectangle() returns (0,0,0,0) for
        # virtual elements and causes right-click to land on the desktop.
        import pywinauto.mouse as _mouse

        sa.set_focus()
        time.sleep(0.2)
        sa_rect = sa.rectangle()
        sa_w    = sa_rect.right  - sa_rect.left
        sa_h    = sa_rect.bottom - sa_rect.top
        # Trades grid is the left ~60% of SA; click at 25% across, 55% down
        rc_x = sa_rect.left + sa_w // 4
        rc_y = sa_rect.top  + int(sa_h * 0.55)
        _mouse.right_click(coords=(rc_x, rc_y))
        time.sleep(0.4)
        _alog(f"export-trades: right-clicked SA at ({rc_x},{rc_y})")
        log.append(f"Right-clicked SA trades area at ({rc_x},{rc_y})")

        # Step 3b: find Export... in the WPF context menu.
        # NT8 uses WPF so its context menus are NOT class #32768 (native Win32).
        # They live in NT8's own element tree — scan for MenuItem elements.
        nt8        = sa.top_level_parent()
        export_el  = None
        menu_items = []
        for el in nt8.descendants():
            try:
                txt = (el.window_text() or "").strip()
                ct  = str(getattr(el.element_info, "control_type", ""))
                if ct == "MenuItem" and txt:
                    menu_items.append(txt)
                    if txt.startswith("Export") and export_el is None:
                        export_el = el
            except Exception:
                pass
        log.append(f"Menu items found: {menu_items}")

        if export_el is None:
            send_keys("{ESCAPE}")
            return jsonify({"error": "Export MenuItem not found in NT8 tree", "log": log, "menu_items": menu_items})

        export_el.click_input()
        log.append("Clicked Export")
        time.sleep(0.5)

        # Step 4: Export As dialog
        dlg = dt.window(title="Export As")
        dlg.wait("visible", timeout=10)
        log.append(f"Dialog: '{dlg.window_text()}'")

        # Find the filename Edit field — try auto_id first, then first Edit control
        fname = None
        for aid in ["1148", "fileNameTextBox", "FILENAME"]:
            try:
                f = dlg.child_window(auto_id=aid, control_type="Edit")
                if f.exists(timeout=0.3):
                    fname = f
                    log.append(f"Filename field via auto_id={aid}")
                    break
            except Exception:
                pass
        if fname is None:
            fname = dlg.child_window(control_type="Edit", found_index=0)
            log.append("Filename field via first Edit")

        # set_edit_text is more reliable than type_keys in file dialogs
        fname.click_input()
        time.sleep(0.1)
        fname.set_edit_text(out_path)
        time.sleep(0.2)

        # Click Save explicitly rather than relying on Enter key
        try:
            dlg.child_window(title="Save", control_type="Button").click_input()
            log.append("Clicked Save button")
        except Exception:
            send_keys("{ENTER}")
            log.append("Pressed Enter (Save fallback)")
        time.sleep(0.8)

        # If file already exists NT8 shows a "Confirm Save As" overwrite dialog — dismiss it
        for confirm_title in ["Confirm Save As", "Confirm", "Save As"]:
            try:
                confirm = dt.window(title=confirm_title)
                if confirm.exists(timeout=1.5):
                    for btn in ["Yes", "OK"]:
                        try:
                            confirm.child_window(title=btn, control_type="Button").click_input()
                            log.append(f"Overwrite confirmed ({btn})")
                            break
                        except Exception:
                            pass
                    break
            except Exception:
                pass

        time.sleep(1.0)
        log.append(f"Saved to {out_path}")

        # Step 5: read and return the full CSV
        if not os.path.exists(out_path):
            return jsonify({"error": "CSV was not written to disk", "log": log})

        with open(out_path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        lines = content.splitlines()
        log.append(f"CSV lines: {len(lines)}")
        return jsonify({"ok": True, "log": log, "total_lines": len(lines),
                        "header": lines[0] if lines else "", "csv": content})

    except Exception as e:
        import traceback
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
