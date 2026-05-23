"""
LucidFlex VPS Agent — HTTP server that runs in the RDP session on the VPS.

Because NT8 runs in the RDP session and SSH creates an isolated session,
pywinauto cannot reach NT8 over SSH directly. This agent runs persistently
inside the RDP session and accepts commands via HTTP, bridging the gap.

Endpoints:
    GET  /health          -- ping
    POST /run-backtests   -- run all combos via pywinauto (background)
    GET  /status          -- log tail + running flag
    GET  /results         -- parsed CSV as JSON

Usage on VPS (run from RDP terminal, NT8 must be open with Strategy Analyzer):
    python C:\\algos\\markets\\futures\\lucid_flex\\tools\\vps_agent.py

Access from Mac via SSH tunnel:
    ssh -N -L 8765:localhost:8765 forexvps
    curl http://localhost:8765/health
"""

import sys
import os
import json
import csv
import time
import threading
import subprocess
from pathlib import Path

try:
    from flask import Flask, jsonify
except ImportError:
    print("ERROR: flask not installed. Run: pip install flask")
    sys.exit(1)

SCRIPT_DIR   = Path(__file__).parent
CFG_PATH     = SCRIPT_DIR / "backtest_config.json"
PORT         = 8765

app = Flask(__name__)

_log: list = []
_running   = False
_lock      = threading.Lock()


def _log_append(msg: str):
    ts    = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    with _lock:
        _log.append(entry)
        if len(_log) > 500:
            _log.pop(0)
    print(entry, flush=True)


def _load_config():
    with open(CFG_PATH) as f:
        return json.load(f)


# ── CORS (React app on localhost:5173 → agent on localhost:8765) ──────────

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


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "running": _running})


@app.route("/status")
def status():
    with _lock:
        return jsonify({"running": _running, "log": list(_log[-200:])})


@app.route("/run-backtests", methods=["POST"])
def run_backtests():
    global _running
    with _lock:
        if _running:
            return jsonify({"error": "Already running"}), 409
        _running = True

    threading.Thread(target=_run_bg, daemon=True).start()
    return jsonify({"status": "started"})


def _run_bg():
    global _running
    runner = str(SCRIPT_DIR / "vps_backtest_runner.py")
    cfg    = str(CFG_PATH)
    _log_append("Starting backtest runner...")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", runner, "--config", cfg],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            _log_append(line.rstrip())
        proc.wait()
        if proc.returncode == 0:
            _log_append("Backtests complete.")
        else:
            _log_append(f"Runner exited with code {proc.returncode}")
    except Exception as e:
        _log_append(f"ERROR: {e}")
    finally:
        with _lock:
            _running = False


@app.route("/results")
def get_results():
    cfg  = _load_config()
    user = cfg["vps_user"]
    path = Path(rf"C:\Users\{user}") / cfg["results_remote_path"].replace("/", "\\")
    if not path.exists():
        return jsonify({"error": "No results file yet", "rows": []}), 404
    rows = []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return jsonify({"rows": rows})


@app.route("/clear-results", methods=["POST"])
def clear_results():
    cfg  = _load_config()
    user = cfg["vps_user"]
    path = Path(rf"C:\Users\{user}") / cfg["results_remote_path"].replace("/", "\\")
    try:
        path.unlink(missing_ok=True)
        _log_append("Results cleared.")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    _log_append(f"LucidFlex Agent starting on port {PORT}...")
    _log_append(f"Config: {CFG_PATH}")
    _log_append("NT8 must be running with Strategy Analyzer open.")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
