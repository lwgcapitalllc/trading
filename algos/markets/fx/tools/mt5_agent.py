"""
MT5 Agent — HTTP bridge for MetaTrader 5 backtests and historical data.

Runs persistently on the VPS alongside the NT8 agent (nt8_agent.py).
MT5 terminal must be running for full functionality; the agent starts
and returns a degraded status if MT5 is not yet connected.

Port: 8766  (NT8 agent uses 8765)

Endpoints — Step 1 (this build):
    GET  /health                         → ping; running_jobs count
    GET  /status                         → MT5 connection + account info
    GET  /symbol_info                    → broker contract spec: spread, swap, digits, contract size
    GET  /data_availability              → earliest→latest served bar per timeframe (M1..H4)
    GET  /historical_data                → M1–M30/H1/H4/daily OHLC bars
    GET  /ticks                          → real bid/ask tick history (the A2 fill model's feed)
    GET  /files/strategies               → list .mq5/.ex5 in MT5 Experts folder
    GET  /agent-log                      → agent log tail

Timestamps: every timestamp this agent returns is TRUE UTC. MT5 reports broker-server local time
(EET/EEST, UTC+2/+3); `broker_clock.py` converts. Do not reintroduce `utcfromtimestamp` on an MT5
`time` field — that was the 2-3h bug that silently misplaced every session/liquidity boundary.

Endpoints — Step 7 (MT5 Strategy Tester driver):
    POST /backtests                      → trigger a backtest run
    GET  /backtests/{job_id}             → poll status
    GET  /backtests/{job_id}/results     → fetch final results JSON
    GET  /backtests/{job_id}/log         → job log tail
    POST /jobs/{job_id}/cancel           → cancel a running job

Endpoints — Step 9 (MT5 deployment):
    POST   /files/strategies/{filename}  → upload a .mq5 file
    DELETE /files/strategies/{filename}  → delete a file
    POST   /compile                      → trigger MetaEditor compile
    GET    /compile/{job_id}             → poll compile status

SSH tunnel from Mac:
    ssh -N -L 8766:localhost:8766 forexvps
    curl http://localhost:8766/health

Startup (Windows Task Scheduler, suggested task name: MT5Agent):
    cmd /c python C:\\trading\\algos\\markets\\fx\\tools\\mt5_agent.py
"""

from __future__ import annotations

import csv
import datetime
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import broker_clock

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("ERROR: flask not installed. Run: pip install flask")
    sys.exit(1)

try:
    import MetaTrader5 as mt5

    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

PORT = 8766
MAX_UPLOAD_BYTES = 256 * 1024  # 256 KB — MQL5 files are typically 5–50 KB


# Task Scheduler on Windows disconnects stdout/stderr; writing to the broken
# handle raises OSError. Replace with devnull so Flask and our code can print
# freely without raising.
def _fix_stdio() -> None:
    for _attr in ("stdout", "stderr"):
        _s = getattr(sys, _attr, None)
        if _s is None:
            try:
                setattr(sys, _attr, open(os.devnull, "w"))
            except Exception:
                pass
        else:
            try:
                _s.write("")
                _s.flush()
            except Exception:
                try:
                    setattr(sys, _attr, open(os.devnull, "w"))
                except Exception:
                    pass


_fix_stdio()

app = Flask(__name__)

_agent_log: list[str] = []
_jobs: dict[str, dict] = {}
_compile_jobs: dict[str, dict] = {}
_lock = threading.Lock()

# Detected at first successful MT5 connection; None until then.
_experts_dir: Optional[Path] = None

_terminal_path: Optional[Path] = None  # cached tester executable path
_lab_bound = False  # True once the API is bound to MT5_Lab (logged once)
_BACKTEST_TIMEOUT = 300  # seconds before force-kill
_REPORT_POLL_INTERVAL = 5  # seconds between report-file polls


# ── Timeframe constants ────────────────────────────────────────────────────────


def _tf_const(name: str) -> Optional[int]:
    """Resolve a timeframe name to an MT5 constant. Returns None if unavailable."""
    if not MT5_AVAILABLE:
        return None
    _map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "daily": mt5.TIMEFRAME_D1,
    }
    return _map.get(name.upper() if name.upper() in _map else name)


# ── Logging helpers ────────────────────────────────────────────────────────────


def _alog(msg: str):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    with _lock:
        _agent_log.append(entry)
        if len(_agent_log) > 1000:
            _agent_log.pop(0)
    try:
        print(entry, flush=True)
    except Exception:
        pass


# ── MT5 connection ─────────────────────────────────────────────────────────────

_mt5_lock = threading.Lock()

# Max tick rows /ticks will serialise in one response. Gold runs ~100-230k ticks/day, so this is
# roughly a fortnight of gold — comfortably under the point where the JSON response itself becomes
# the bottleneck. Over the cap the endpoint refuses (413) instead of truncating: a silently short
# tick window yields fills that look real and aren't.
_TICK_ROW_CAP = 3_000_000


def _lab_terminal_exe() -> Optional[Path]:
    """
    Resolve the MT5_Lab terminal64.exe for the Python-API connection.

    Resolution order — TERMINAL_PATH, then MT5_DATA_DIR's origin.txt, then the
    baked-in C:\\MT5_Lab default (the canonical lab install path also hardcoded
    by algos/tools/download_mt5_history.py and audit_mt5_data_quality.py). All
    three point at the lab terminal; it deliberately NEVER falls back to a
    running terminal — that is exactly the MT5_FFT leak we are closing. Returns
    None only if no lab terminal64.exe exists at any of these locations.
    """
    dirs: list[Path] = []

    env = os.environ.get("TERMINAL_PATH", "")
    if env:
        p = Path(env)
        dirs.append(p if p.is_dir() else p.parent)

    data_dir_env = os.environ.get("MT5_DATA_DIR", "")
    if data_dir_env:
        origin = Path(data_dir_env) / "origin.txt"
        if origin.is_file():
            try:
                terminal_dir = Path(origin.read_text(encoding="utf-8", errors="replace").strip())
                if terminal_dir.is_dir():
                    dirs.append(terminal_dir)
            except Exception:
                pass

    # Baked-in default — the canonical lab install. Keeps the data pull pinned to
    # MT5_Lab even when the VPS env vars are unset (they currently are).
    dirs.append(Path(r"C:\MT5_Lab"))

    for d in dirs:
        t = d / "terminal64.exe"
        if t.is_file():
            return t
    return None


def _ensure_mt5() -> tuple[bool, Optional[str]]:
    """
    Ensure the Python API is connected to the MT5_Lab terminal — and ONLY that.
    Returns (ok, error_message).

    All backtest price/tick data must come from the account logged into
    MT5_Lab. The connection is pinned to the lab terminal64.exe resolved from
    the environment; if a different terminal (e.g. a live bot terminal such as
    MT5_FFT) is already attached, it is dropped and re-bound to the lab. If the
    lab terminal cannot be resolved or bound, the call FAILS — it never silently
    attaches to whatever terminal answers first.
    """
    global _lab_bound
    if not MT5_AVAILABLE:
        return False, "MetaTrader5 package not installed"

    lab_exe = _lab_terminal_exe()
    if lab_exe is None:
        return False, (
            "Cannot locate the MT5_Lab terminal — set TERMINAL_PATH or "
            "MT5_DATA_DIR so the backtest binds to MT5_Lab. Refusing to "
            "connect to an unknown terminal."
        )
    lab_dir = str(lab_exe.parent).lower()

    def _connected_dir() -> str:
        info = mt5.terminal_info()
        return str(Path(getattr(info, "path", "") or "")).lower() if info else ""

    with _mt5_lock:
        if not mt5.initialize(path=str(lab_exe)):
            return False, f"MT5 init failed for lab terminal {lab_exe}: {mt5.last_error()}"

        # Guard: if initialize() reused a pre-existing connection to a different
        # terminal, drop it and re-bind to the lab terminal exactly once.
        if _connected_dir() != lab_dir:
            mt5.shutdown()
            if not mt5.initialize(path=str(lab_exe)):
                return False, f"MT5 init failed for lab terminal {lab_exe}: {mt5.last_error()}"
            if _connected_dir() != lab_dir:
                mt5.shutdown()
                return False, (
                    f"Refusing to run: MT5 connected to {_connected_dir() or 'an unknown terminal'}, "
                    f"not the lab terminal at {lab_dir}. Close other MT5 terminals "
                    f"or check TERMINAL_PATH / MT5_DATA_DIR."
                )

        if not _lab_bound:
            acc = mt5.account_info()
            if acc is not None:
                _alog(
                    f"MT5 data bound to MT5_Lab: account {getattr(acc, 'login', '?')} "
                    f"on {getattr(acc, 'server', '?')} ({lab_exe})"
                )
            else:
                _alog(f"MT5 data bound to MT5_Lab terminal {lab_exe} (no account logged in)")
            _lab_bound = True
        return True, None


def _get_lab_data_dir() -> Optional[Path]:
    """
    Find the non-portable AppData directory for MT5_Lab without launching it.

    Resolution order:
    1. MT5_DATA_DIR env var — explicit override, always wins.
    2. Scan APPDATA/MetaQuotes/Terminal/*/origin.txt for the folder that
       matches TERMINAL_PATH. Works when the agent runs as the same user
       who owns the MT5_Lab installation.
    """
    explicit = os.environ.get("MT5_DATA_DIR", "")
    if explicit:
        p = Path(explicit)
        if p.is_dir():
            _alog(f"Lab data dir (MT5_DATA_DIR): {p}")
            return p

    terminal_path = os.environ.get("TERMINAL_PATH", "")
    if not terminal_path:
        return None
    target = str(Path(terminal_path)).lower()
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    base = Path(appdata) / "MetaQuotes" / "Terminal"
    if not base.is_dir():
        return None
    for folder in base.iterdir():
        origin = folder / "origin.txt"
        if origin.is_file():
            try:
                if origin.read_text(encoding="utf-8", errors="replace").strip().lower() == target:
                    _alog(f"Lab data dir (origin.txt scan): {folder}")
                    return folder
            except Exception:
                pass
    return None


def _detect_experts_dir() -> Optional[Path]:
    """
    Detect and cache the MT5 Experts folder path.

    Resolution order:
    1. MT5_DATA_DIR env var + "/MQL5/Experts" — works without MT5 running.
    2. terminal_info().data_path — requires a live MT5 connection.
    """
    global _experts_dir
    if _experts_dir is not None:
        return _experts_dir

    # Env var path — no MT5 connection needed
    explicit = os.environ.get("MT5_DATA_DIR", "")
    if explicit:
        p = Path(explicit) / "MQL5" / "Experts"
        if p.exists():
            _experts_dir = p
            _alog(f"MT5 Experts dir (MT5_DATA_DIR): {_experts_dir}")
            return _experts_dir

    # Live terminal_info() fallback
    ok, _ = _ensure_mt5()
    if not ok:
        return None
    with _mt5_lock:
        info = mt5.terminal_info()
    if info is None:
        return None
    data_path = getattr(info, "data_path", None)
    if not data_path:
        return None
    path = Path(data_path) / "MQL5" / "Experts"
    if path.exists():
        _experts_dir = path
        _alog(f"MT5 Experts dir (terminal_info): {_experts_dir}")
    return _experts_dir


# ── Global error handler ──────────────────────────────────────────────────────

import traceback as _traceback


@app.errorhandler(Exception)
def _unhandled(exc):
    tb = _traceback.format_exc()
    _alog(f"UNHANDLED EXCEPTION in {exc.__class__.__name__}: {exc}\n{tb}")
    return jsonify({"error": str(exc)}), 500


# ── CORS ──────────────────────────────────────────────────────────────────────


@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def _options(path):
    return "", 204


# ── Step 1 endpoints ───────────────────────────────────────────────────────────


@app.route("/health")
def health():
    running = sum(1 for j in _jobs.values() if j["status"] == "running")
    return jsonify({"status": "ok", "running_jobs": running})


@app.route("/status")
def status():
    """MT5 connection status and account info."""
    result: dict = {
        "mt5_connected": False,
        "mt5_available": MT5_AVAILABLE,
        "account": None,
        "server": None,
        "terminal_path": None,
        "experts_path": str(_experts_dir) if _experts_dir else None,
        "error": None,
    }
    if not MT5_AVAILABLE:
        result["error"] = "MetaTrader5 package not installed"
        return jsonify(result)

    ok, err = _ensure_mt5()
    if not ok:
        result["error"] = err
        return jsonify(result)

    with _mt5_lock:
        info = mt5.terminal_info()
        acc = mt5.account_info()

    result["mt5_connected"] = True
    if info:
        result["terminal_path"] = getattr(info, "path", None)
        data_path = getattr(info, "data_path", None)
        if data_path and not result["experts_path"]:
            ep = Path(data_path) / "MQL5" / "Experts"
            result["experts_path"] = str(ep)
    if acc:
        result["account"] = getattr(acc, "login", None)
        result["server"] = getattr(acc, "server", None)

    # Try to populate experts_dir if not yet detected
    _detect_experts_dir()
    return jsonify(result)


def _resolve_symbol(symbol: str) -> Optional[str]:
    """Return the broker's ACTUAL name for `symbol`, trying it as given then with any suffix
    stripped (PU Prime 'XAUUSD.s' vs Vantage 'XAUUSD'). Selects it into Market Watch so its spec
    and history are readable. None if the terminal carries no such symbol. Caller holds _mt5_lock."""
    candidates = [symbol]
    root = symbol.split(".")[0]
    if root and root != symbol:
        candidates.append(root)
    for cand in candidates:
        if mt5.symbol_select(cand, True) and mt5.symbol_info(cand) is not None:
            return cand
    return None


@app.route("/symbol_info")
def symbol_info():
    """Broker contract spec for a symbol — the cost model's ground truth, read off MT5 not guessed.

    Query param: symbol (e.g. XAUUSD). Returns the resolved broker name, digits, point, contract
    size, min/step volume, the terminal's live spread (in points AND price), and the swap long/short
    values straight off the symbol's Specification — everything a cost profile needs, no estimates.
    """
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    ok, err = _ensure_mt5()
    if not ok:
        return jsonify({"error": err}), 503

    with _mt5_lock:
        used = _resolve_symbol(symbol)
        if used is None:
            return jsonify({"error": f"symbol not found on this terminal: {symbol}"}), 404
        info = mt5.symbol_info(used)
        tick = mt5.symbol_info_tick(used)

    point = float(getattr(info, "point", 0.0) or 0.0)
    spread_points = int(getattr(info, "spread", 0) or 0)
    result = {
        "requested": symbol,
        "symbol": used,
        "description": getattr(info, "description", None),
        "digits": int(getattr(info, "digits", 0) or 0),
        "point": point,
        "contract_size": float(getattr(info, "trade_contract_size", 0.0) or 0.0),
        "volume_min": float(getattr(info, "volume_min", 0.0) or 0.0),
        "volume_step": float(getattr(info, "volume_step", 0.0) or 0.0),
        "volume_max": float(getattr(info, "volume_max", 0.0) or 0.0),
        "spread_points": spread_points,  # terminal's current spread, integer points
        "spread_price": spread_points * point,  # the same spread in price terms
        "swap_long": float(getattr(info, "swap_long", 0.0) or 0.0),
        "swap_short": float(getattr(info, "swap_short", 0.0) or 0.0),
        "swap_mode": int(getattr(info, "swap_mode", 0) or 0),
        "swap_rollover3days": int(
            getattr(info, "swap_rollover3days", 0) or 0
        ),  # MT5 day-of-week of triple swap
        "currency_base": getattr(info, "currency_base", None),
        "currency_profit": getattr(info, "currency_profit", None),
        "currency_margin": getattr(info, "currency_margin", None),
        "bid": (float(getattr(tick, "bid", 0.0) or 0.0) if tick else None),
        "ask": (float(getattr(tick, "ask", 0.0) or 0.0) if tick else None),
    }
    _alog(
        f"symbol_info: {used} spread={spread_points}pt swap L/S={result['swap_long']}/{result['swap_short']}"
    )
    return jsonify(result)


@app.route("/data_availability")
def data_availability():
    """How much history the broker actually SERVES per timeframe — the real bound on a backtest window.

    Query params: symbol (e.g. XAUUSD); timeframes (CSV, default M1,M5,M15,M30,H1,H4). For each TF:
    earliest and latest bar time (TRUE UTC) and the span in days. Cheap by design — it reads one bar
    from each end (oldest at/after 2000, and newest), never a full history pull.
    """
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    tf_names = [
        t.strip()
        for t in request.args.get("timeframes", "M1,M5,M15,M30,H1,H4").split(",")
        if t.strip()
    ]

    ok, err = _ensure_mt5()
    if not ok:
        return jsonify({"error": err}), 503

    epoch0 = datetime.datetime(2000, 1, 1)
    out: dict = {}
    with _mt5_lock:
        used = _resolve_symbol(symbol)
        if used is None:
            return jsonify({"error": f"symbol not found on this terminal: {symbol}"}), 404
        for name in tf_names:
            tf = _tf_const(name)
            if tf is None:
                out[name] = {"error": f"unknown timeframe: {name}"}
                continue
            first = mt5.copy_rates_from(
                used, tf, epoch0, 1
            )  # oldest bar at/after 2000 = start of history
            last = mt5.copy_rates_from_pos(used, tf, 0, 1)  # newest bar
            if first is None or len(first) == 0 or last is None or len(last) == 0:
                out[name] = {"earliest": None, "latest": None, "span_days": 0}
                continue
            t0 = broker_clock.to_utc(broker_clock.broker_naive_from_epoch(first[0]["time"]))
            t1 = broker_clock.to_utc(broker_clock.broker_naive_from_epoch(last[0]["time"]))
            out[name] = {
                "earliest": t0.isoformat(),
                "latest": t1.isoformat(),
                "span_days": (t1 - t0).days,
            }
    _alog(
        "data_availability: "
        + used
        + " -> "
        + ", ".join(f"{k}:{v.get('span_days', '?')}d" for k, v in out.items())
    )
    return jsonify({"symbol": used, "timeframes": out})


@app.route("/historical_data")
def historical_data():
    """
    Fetch OHLC bars from MT5.

    Query params:
        symbol      — e.g. EURUSD, XAUUSD
        timeframe   — M1 | M5 | M15 | M30 | H1 | H4 | D1 | daily
        start_date  — YYYY-MM-DD
        end_date    — YYYY-MM-DD (inclusive)

    Response:
        {"bars": [{"time": "ISO", "open": f, "high": f, "low": f, "close": f}, ...],
         "symbol": "EURUSD", "timeframe": "H1", "count": N}
    """
    symbol = request.args.get(
        "symbol", ""
    ).strip()  # preserve case — broker symbols are case-sensitive (e.g. "GBPJPY.s")
    timeframe = request.args.get("timeframe", "H1")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date required (YYYY-MM-DD)"}), 400

    tf = _tf_const(timeframe)
    if tf is None:
        return jsonify(
            {"error": f"Unknown timeframe: {timeframe!r}. Use M1, M5, M15, M30, H1, H4, D1, daily"}
        ), 400

    ok, err = _ensure_mt5()
    if not ok:
        return jsonify({"error": err}), 503

    try:
        dt_from = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        # end_date is inclusive — add one day so the last day is included
        dt_to = datetime.datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(days=1)
    except ValueError as exc:
        return jsonify({"error": f"Invalid date: {exc}"}), 400

    # Try the symbol as given, then its root (suffix stripped). Broker terminals vary: some carry
    # "GBPJPY.s", others plain "GBPJPY" — always-uppercasing or always-stripping breaks one or the
    # other. symbol_select is benign (data-only) and is what makes a not-yet-watched symbol readable.
    candidates = [symbol]
    root = symbol.split(".")[0]
    if root and root != symbol:
        candidates.append(root)

    # Query a day wider on each side, then filter in TRUE UTC below. The range we hand MT5 is
    # matched against its BROKER-local stamps, but our contract is "bars whose true-UTC time is in
    # [start_date, end_date]" — and those differ by 2-3h. Without the pad, converting to true UTC
    # would silently drop the last 2-3h of end_date while the data layer recorded the full range as
    # fetched (a cache-coverage hole that never re-fetches). Pad + filter makes the contract exact.
    rates = None
    used = symbol
    with _mt5_lock:
        for cand in candidates:
            mt5.symbol_select(cand, True)
            r = mt5.copy_rates_range(
                cand, tf, dt_from - datetime.timedelta(days=1), dt_to + datetime.timedelta(days=1)
            )
            if r is not None and len(r) > 0:
                rates, used = r, cand
                break

    if rates is None or len(rates) == 0:
        err_info = mt5.last_error() if MT5_AVAILABLE else ("", "")
        return jsonify(
            {
                "error": f"MT5 returned no data for {symbol} {timeframe}",
                "mt5_error": str(err_info),
            }
        ), 404

    bars = [b for b in _rates_to_bars(rates) if start_date <= b["time"][:10] <= end_date]
    _alog(f"historical_data: {used} {timeframe} [{start_date}, {end_date}] -> {len(bars)} bars")
    return jsonify({"bars": bars, "symbol": used, "timeframe": timeframe, "count": len(bars)})


def _rates_to_bars(rates) -> list[dict]:
    """Convert MT5 rates structured array to a list of bar dicts.

    `time` is TRUE UTC. MT5's `time` field is broker-server local (EET/EEST, UTC+2/+3), so it
    goes through `broker_clock.to_utc` — stamping it as UTC directly is the bug compare_feeds.py
    caught (every bar 2-3h off, silently wrecking every time-driven engine). See broker_clock.py.

    `volume` is MT5's **tick_volume** — the number of price changes in the bar, NOT contracts
    traded. That is the honest field for a CFD: `real_volume` is 0 on every broker here because
    there is no exchange behind the quote, and reading it would hand every consumer a confident
    zero. Tick volume is also precisely what TradingView plots as `volume` on the same chart,
    which is the series `engines/vwap/` was validated against at Pine parity — so the line this
    feeds and the line on Aaron's chart are computed from the same numbers.

    ⚠ Added 2026-08-06, and it is why `cache.FEED_VERSION` went to 3. Bars fetched before this
    carry no volume at all, so they are re-pulled rather than merged with bars that do.
    """
    bars = []
    for r in rates:
        ts = broker_clock.to_utc(broker_clock.broker_naive_from_epoch(r["time"]))
        bars.append(
            {
                "time": ts.isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["tick_volume"]),
            }
        )
    return bars


def _parse_bound(token: str, *, end: bool) -> tuple[datetime.datetime, bool]:
    """Parse a /ticks bound: a bare date (whole-day semantics) or a full ISO datetime.

    Returns (instant, was_date_only). A bare `end` date means "through the end of that day", so it
    resolves to the following midnight — keeping the endpoint's original inclusive-date contract
    while the datetime form is exact and end-exclusive.
    """
    token = token.strip()
    if len(token) == 10:
        d = datetime.datetime.strptime(token, "%Y-%m-%d")
        return (d + datetime.timedelta(days=1) if end else d), True
    return datetime.datetime.fromisoformat(token), False


@app.route("/ticks")
def ticks():
    """Real bid/ask tick history — the honest intrabar path for the fill model (A2).

    Query: symbol, start_date, end_date — each either YYYY-MM-DD (whole day, inclusive) or a full
    ISO datetime "YYYY-MM-DDTHH:MM:SS" (exact instant; end is EXCLUSIVE) in TRUE UTC.
    Response: {"ticks": [{"time": ISO-true-UTC, "bid": f, "ask": f}, ...], "symbol": s, "count": n}

    **Always prefer the datetime form.** Gold runs ~690k ticks/day = ~43MB of JSON and ~90s on the
    wire (measured 2026-07-14); a whole-day pull to resolve one ambiguous 5-minute bar is ~99.6%
    waste. The fill model needs ticks only for the few bars where a target and a stop are both in
    range, so it asks for those windows and nothing else (~2k ticks, well under a second).

    `time` is TRUE UTC (via broker_clock), same as /historical_data — tick stamps come off the same
    broker-local clock. Tick timestamps carry milliseconds (`time_msc`); we use that, not the
    second-resolution `time` field, because two ticks in one second are exactly what decides whether
    a limit or a stop fills first.

    Volume warning: gold runs ~100-230k ticks/DAY. A month is millions of rows, so this endpoint is
    deliberately per-window and the caller (backtest.data) is expected to fetch lazily and cache. A
    range that would exceed `_TICK_ROW_CAP` is refused with 413 rather than being silently truncated
    — a truncated tick window would produce fills that look real and are not.
    """
    symbol = request.args.get("symbol", "").strip()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date required (YYYY-MM-DD)"}), 400

    ok, err = _ensure_mt5()
    if not ok:
        return jsonify({"error": err}), 503

    try:
        dt_from, _ = _parse_bound(start_date, end=False)
        dt_to, _ = _parse_bound(end_date, end=True)
    except ValueError as exc:
        return jsonify({"error": f"Invalid date: {exc}"}), 400
    if dt_to <= dt_from:
        return jsonify({"error": "end must be after start"}), 400

    candidates = [symbol]
    root = symbol.split(".")[0]
    if root and root != symbol:
        candidates.append(root)

    # The bounds above are TRUE UTC, but copy_ticks_range matches BROKER-local stamps. Pad by more
    # than the largest possible offset so the window can't be clipped, then filter exactly below.
    pad = datetime.timedelta(hours=max(broker_clock.STD_OFFSET, broker_clock.DST_OFFSET) + 1)
    raw = None
    used = symbol
    with _mt5_lock:
        for cand in candidates:
            mt5.symbol_select(cand, True)
            # COPY_TICKS_ALL — every tick, not just those that moved the bid or the ask.
            t = mt5.copy_ticks_range(cand, dt_from - pad, dt_to + pad, mt5.COPY_TICKS_ALL)
            if t is not None and len(t) > 0:
                raw, used = t, cand
                break

    if raw is None or len(raw) == 0:
        # A genuinely empty window is normal (weekend/holiday) and is NOT an error — the caller
        # must be able to tell "no ticks here" from "the pull failed". Phase-0 found tick history
        # is deep but patchy, so a 404 here would make a thin day look like a broken symbol.
        _alog(f"ticks: {symbol} [{start_date}, {end_date}] -> 0 (empty window)")
        return jsonify({"ticks": [], "symbol": symbol, "count": 0})

    if len(raw) > _TICK_ROW_CAP:
        return jsonify(
            {
                "error": f"tick window too large: {len(raw)} rows > cap {_TICK_ROW_CAP}. "
                f"Request a shorter date range.",
                "rows": int(len(raw)),
                "cap": _TICK_ROW_CAP,
            }
        ), 413

    ticks_out = []
    for t in raw:
        msc = int(t["time_msc"])
        ts = broker_clock.to_utc(broker_clock.broker_naive_from_epoch(msc // 1000)).replace(
            microsecond=(msc % 1000) * 1000
        )
        if not (dt_from <= ts < dt_to):  # half-open, in TRUE UTC
            continue
        ticks_out.append({"time": ts.isoformat(), "bid": float(t["bid"]), "ask": float(t["ask"])})

    _alog(f"ticks: {used} [{start_date}, {end_date}) -> {len(ticks_out)} ticks")
    return jsonify({"ticks": ticks_out, "symbol": used, "count": len(ticks_out)})


@app.route("/files/strategies")
def list_strategy_files():
    """List .mq5 and .ex5 files in the MT5 Experts folder."""
    experts = _detect_experts_dir()
    if experts is None:
        # Return empty list rather than error — MT5 may not be running yet
        return jsonify([])
    try:
        files = []
        for ext in ("*.mq5", "*.ex5"):
            for p in sorted(experts.glob(ext)):
                files.append(_file_info(p))
        return jsonify(files)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _file_info(p: Path) -> dict:
    st = p.stat()
    return {
        "filename": p.name,
        "size_bytes": st.st_size,
        "modified_at": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
        "platform": "MT5",
    }


@app.route("/agent-log")
def agent_log():
    lines = int(request.args.get("lines", 200))
    with _lock:
        tail = list(_agent_log[-lines:])
    return jsonify({"log": "\n".join(tail)})


# ── Strategy Tester driver (Step 7) ───────────────────────────────────────────
# .ini approach: write tester.ini + .set inputs file, launch metatester64.exe
# (preferred — no single-instance lock with live terminal) or terminal64.exe,
# using SW_MINIMIZE to prevent headless hang, poll for .htm report, parse with
# stdlib HTMLParser. Result shape matches NT8 BacktestResult for downstream compat.


def _get_tester_exe() -> Optional[Path]:
    """
    Locate terminal64.exe for the lab MT5 installation. Resolution order:
    1. TERMINAL_PATH env var — explicit terminal directory, always wins.
    2. MT5_DATA_DIR env var — read origin.txt to resolve the terminal directory.
       This is the normal production path: Task Scheduler sets MT5_DATA_DIR to the
       MT5_Lab AppData folder; origin.txt inside it contains 'C:\\MT5_Lab'.
    3. Auto-detect via terminal_info().path — last resort only. Since
       _ensure_mt5() is now pinned to MT5_Lab, this too resolves to the lab
       terminal (never a live bot terminal such as MT5_FFT / MT5_Scalper).
    """
    global _terminal_path
    if _terminal_path is not None:
        return _terminal_path

    dirs: list[Path] = []

    env = os.environ.get("TERMINAL_PATH", "")
    if env:
        p = Path(env)
        dirs.append(p if p.is_dir() else p.parent)

    if not dirs:
        data_dir_env = os.environ.get("MT5_DATA_DIR", "")
        if data_dir_env:
            origin = Path(data_dir_env) / "origin.txt"
            if origin.is_file():
                try:
                    terminal_dir = Path(
                        origin.read_text(encoding="utf-8", errors="replace").strip()
                    )
                    if terminal_dir.is_dir():
                        dirs.append(terminal_dir)
                        _alog(f"Terminal dir (origin.txt): {terminal_dir}")
                except Exception:
                    pass

    if not dirs:
        ok, _ = _ensure_mt5()
        if ok:
            with _mt5_lock:
                info = mt5.terminal_info()
            if info:
                raw = getattr(info, "path", None)
                if raw:
                    dirs.append(Path(raw))
                    _alog(
                        f"WARNING: falling back to connected terminal {raw} — set TERMINAL_PATH or MT5_DATA_DIR to use the lab terminal"
                    )

    for d in dirs:
        t = d / "terminal64.exe"
        mt = d / "metatester64.exe"
        if t.is_file():
            _terminal_path = t
        elif mt.is_file():
            _terminal_path = mt
        if _terminal_path:
            _alog(f"Tester exe: {_terminal_path}")
            return _terminal_path

    return None


def _tester_data_dir(tester_exe: Path) -> Path:
    """Return the MT5 data directory for MT5_Lab (AppData, not the exe dir).
    Uses _get_lab_data_dir() which scans origin.txt without requiring a running terminal.
    Falls back to tester_exe.parent only as a last resort."""
    lab_dir = _get_lab_data_dir()
    if lab_dir:
        return lab_dir
    return tester_exe.parent


def _write_set_file(data_dir: Path, job_id: str, inputs: dict) -> str:
    """Write EA input parameters to a .set file; return the filename."""
    dest = data_dir / "MQL5" / "Profiles" / "Tester"
    dest.mkdir(parents=True, exist_ok=True)
    filename = f"bt_{job_id[:8]}.set"
    (dest / filename).write_text(
        "\n".join(f"{k}={v}" for k, v in inputs.items()),
        encoding="utf-8",
    )
    return filename


def _write_set_file_with_ranges(
    data_dir: Path,
    job_id: str,
    inputs: dict,
    param_ranges: dict,
) -> str:
    """
    Write EA input parameters with optimization ranges to a .set file.

    For ranged params, writes MT5's compact optimization format:
        ParamName=currentValue||1||minValue||step||maxValue
    Fixed inputs write plain key=value.
    """
    dest = data_dir / "MQL5" / "Profiles" / "Tester"
    dest.mkdir(parents=True, exist_ok=True)
    filename = f"opt_{job_id[:8]}.set"

    # MT5 set file format: value||start||step||stop||Y  (Y = optimize, N = fixed)
    def _range_line(k: str, current, lo, step, hi) -> str:
        return f"{k}={current}||{lo}||{step}||{hi}||Y"

    lines = []
    for k, v in inputs.items():
        if k in param_ranges:
            spec = param_ranges[k]
            if isinstance(spec, dict):
                lo, hi, step = spec["min"], spec["max"], spec["step"]
            elif isinstance(spec, list) and len(spec) > 1:
                lo, hi = spec[0], spec[-1]
                step = round(spec[1] - spec[0], 8) if len(spec) > 1 else 1
            else:
                lo = hi = spec[0] if isinstance(spec, list) and spec else spec
                step = 1
            lines.append(_range_line(k, v, lo, step, hi))
        else:
            lines.append(f"{k}={v}")
    # Write ranged params not in inputs (excluded from fixed_params by the optimization
    # runner so they don't collide with the range spec).
    for k, spec in param_ranges.items():
        if k not in inputs:
            if isinstance(spec, dict):
                lo, hi, step = spec["min"], spec["max"], spec["step"]
            elif isinstance(spec, list) and len(spec) > 1:
                lo, hi = spec[0], spec[-1]
                step = round(spec[1] - spec[0], 8) if len(spec) > 1 else 1
            else:
                lo = hi = spec[0] if isinstance(spec, list) and spec else spec
                step = 1
            lines.append(_range_line(k, lo, lo, step, hi))
    (dest / filename).write_text("\n".join(lines), encoding="utf-8")
    return filename


def _write_tester_ini(
    ini_path: Path,
    *,
    expert: str,
    set_filename: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    model: int,
    deposit: float,
    currency: str,
    leverage: int,
    report_prefix: str,
    optimization: int = 0,
    forward_mode: int = 0,
) -> None:
    """Write MT5 [Tester] section config file. Dates converted to YYYY.MM.DD."""

    def _dot(d: str) -> str:
        return d.replace("-", ".")

    ini_path.write_text(
        "[Tester]\n"
        f"Expert={expert}\n"
        f"ExpertParameters={set_filename}\n"
        f"Symbol={symbol}\n"
        f"Period={period}\n"
        f"Model={model}\n"
        f"FromDate={_dot(from_date)}\n"
        f"ToDate={_dot(to_date)}\n"
        f"ForwardMode={forward_mode}\n"
        f"Report={report_prefix}\n"
        "ReplaceReport=1\n"
        "ShutdownTerminal=1\n"
        f"Deposit={deposit}\n"
        f"Currency={currency}\n"
        f"Leverage=1:{leverage}\n"
        "Visual=0\n"
        f"Optimization={optimization}\n",
        encoding="utf-8",
    )


def _launch_tester(tester_exe: Path, ini_path: Path) -> "subprocess.Popen[bytes]":
    """Launch tester with SW_MINIMIZE. Fully hidden processes hang on Strategy Tester init."""
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 6  # SW_MINIMIZE
    return subprocess.Popen(
        [str(tester_exe), f"/config:{ini_path}"],
        startupinfo=startupinfo,
    )


def _kill_by_name(name: str) -> None:
    """Force-kill all processes with the given name (Windows only)."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(["taskkill", "/f", "/im", name], capture_output=True, timeout=10)
    except Exception:
        pass


def _kill_by_path(exe_path: Path) -> bool:
    """Kill the specific terminal64.exe at exe_path (not other MT5 instances).

    Uses PowerShell MainModule.FileName filter so only MT5_Lab is killed —
    live bot terminals (MT5_Scalper, MT5_FFT, PU Prime) run from different
    paths and are not affected.  Returns True if a process was found and killed.
    """
    if sys.platform != "win32":
        return False
    exe_str = str(exe_path).replace("'", "\\'")
    script = (
        f"$p = Get-Process -Name terminal64 -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.MainModule.FileName -eq '{exe_str}' }}; "
        f"if ($p) {{ $p | Stop-Process -Force; exit 0 }} else {{ exit 1 }}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0:
            time.sleep(4)  # let the terminal release the single-instance lock
            return True
    except Exception:
        pass
    return False


def _col_idx(hdr: list[str], names: list[str]) -> int:
    """Return first matching column index in a header row; -1 if not found."""
    for n in names:
        try:
            return hdr.index(n)
        except ValueError:
            pass
    return -1


def _cell_float(row: list[str], idx: int) -> float:
    """Extract a float from a table cell by index; returns 0.0 on any error."""
    if idx < 0 or idx >= len(row):
        return 0.0
    try:
        return float(row[idx].strip().replace(" ", "").replace(",", ""))
    except ValueError:
        return 0.0


class _TableParser(HTMLParser):
    """Extract all HTML tables as list[list[list[str]]]."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] = []
        self._row: list[str] = []
        self._cell = ""
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = ""
            self._in_cell = True

    def handle_endtag(self, tag):
        if tag == "table":
            if self._table:
                self.tables.append(self._table)
        elif tag == "tr":
            if self._row:
                self._table.append(self._row)
        elif tag in ("td", "th"):
            self._row.append(self._cell.strip())
            self._in_cell = False

    def handle_data(self, data):
        if self._in_cell:
            self._cell += data


# "DAILY" is how the ohlc_fetcher calls it; D1 is what the .ini expects.
_TF_PERIOD = {
    "DAILY": "D1",
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D1",
}


def _parse_mt5_report(html: str) -> dict:
    """Parse MT5 Strategy Tester .htm report into a BacktestResult-compatible dict."""
    tp = _TableParser()
    tp.feed(html)

    # Flat KPI map — all (label, value) pairs from every row in every table.
    # Each KPI row has multiple pairs (e.g. 3 side-by-side per row), so iterate
    # through all even/odd index pairs. Strip trailing colons from labels.
    kpis: dict[str, str] = {}
    for table in tp.tables:
        for row in table:
            for i in range(0, len(row) - 1, 2):
                k = row[i].strip().rstrip(":")
                v = row[i + 1].strip() if i + 1 < len(row) else ""
                if k:
                    kpis[k] = v

    def _f(key: str, default: float = 0.0) -> float:
        raw = kpis.get(key, "")
        # Values like "99.28 (0.97%)" — take only the part before "("
        val = raw.split("(")[0].strip().replace(" ", "").replace(",", "")
        try:
            return float(val.rstrip("%"))
        except ValueError:
            return default

    net_pnl = _f("Total Net Profit")
    gross_profit = _f("Gross Profit")
    gross_loss = abs(_f("Gross Loss"))
    pf_raw = _f("Profit Factor")
    profit_factor = pf_raw if pf_raw > 0 else (gross_profit / gross_loss if gross_loss else 0.0)
    max_dd = _f("Equity Drawdown Maximal") or _f("Balance Drawdown Maximal")
    sharpe = _f("Sharpe Ratio")
    total_trades = int(_f("Total Trades"))

    # Win rate: use "Profit Trades (% of total)" which always appears; fall back to "Win Trades"
    win_trades = 0
    for key in ("Profit Trades (% of total)", "Win Trades"):
        val = kpis.get(key, "")
        m = re.match(r"^(\d+)", val.replace(" ", ""))
        if m:
            win_trades = int(m.group(1))
            break
    win_rate = win_trades / total_trades if total_trades > 0 else 0.0

    # Deals table: scan ALL rows of every table to find the one with Time + Balance + Direction headers.
    # The Deals header is not always the first row — in MT5 reports it follows an Orders section.
    trades: list[dict] = []
    equity_curve: list[dict] = []
    daily_map: dict[str, float] = {}

    found = False
    for table in tp.tables:
        if found:
            break
        for hdr_idx, hdr in enumerate(table):
            if "Balance" not in hdr or "Time" not in hdr:
                continue

            i_time = _col_idx(hdr, ["Time", "Open Time"])
            # "Direction" col = "in"/"out" (entry vs exit); "Type" col = "buy"/"sell" (long vs short).
            # Keep them separate so we can filter by Direction and map Long/Short from Type.
            i_dir = _col_idx(hdr, ["Direction", "Type"])  # non-empty → trade row
            i_type = _col_idx(hdr, ["Type"])  # buy/sell → Long/Short
            i_vol = _col_idx(hdr, ["Volume", "Size", "Lots"])
            i_price = _col_idx(hdr, ["Price", "Open Price"])
            i_profit = _col_idx(hdr, ["Profit"])
            i_balance = _col_idx(hdr, ["Balance"])

            if i_time < 0 or i_balance < 0:
                continue

            for row in table[hdr_idx + 1 :]:
                if len(row) <= max(i_time, i_balance):
                    continue
                raw_time = row[i_time].strip()
                if not raw_time:
                    continue
                try:
                    ts = datetime.datetime.strptime(raw_time[:16], "%Y.%m.%d %H:%M")
                except ValueError:
                    continue

                balance = _cell_float(row, i_balance)
                if balance == 0.0:
                    continue

                equity_curve.append({"date": ts.isoformat(), "equity": balance})

                direction = row[i_dir].strip().lower() if 0 <= i_dir < len(row) else ""
                profit = _cell_float(row, i_profit)

                # Skip balance/deposit rows (no direction) — they inflate daily_pnl
                if not direction:
                    continue

                # Use the Type column (buy/sell) for Long/Short when it's a separate column;
                # fall back to direction (covers reports where Type IS the only direction col).
                trade_type = (
                    row[i_type].strip().lower()
                    if 0 <= i_type < len(row) and i_type != i_dir
                    else direction
                )

                day = ts.date().isoformat()
                daily_map[day] = daily_map.get(day, 0.0) + profit

                trades.append(
                    {
                        "time": ts.isoformat(),
                        "direction": trade_type,  # "buy"/"sell" → mapped to Long/Short by backend
                        "volume": _cell_float(row, i_vol),
                        "price": _cell_float(row, i_price),
                        "profit": profit,
                    }
                )
            found = True
            break

    daily_pnl = [{"date": d, "pnl": round(p, 2)} for d, p in sorted(daily_map.items())]

    return {
        "net_pnl": round(net_pnl, 2),
        "profit_factor": round(profit_factor, 4),
        "win_rate": round(win_rate, 4),
        "max_drawdown": round(max_dd, 2),
        "sharpe": round(sharpe, 4),
        "trade_count": total_trades,
        "trades": trades,
        "equity_curve": equity_curve,
        "daily_pnl": daily_pnl,
    }


_ENGINE_TRADES_COLS = (
    "index",
    "entry_time",
    "exit_time",
    "direction",
    "entry_price",
    "exit_price",
    "stop_distance",
    "point_value",
    "commission_per_side",
    "exit_reason",
)


def _engine_trades_path(data_dir: Path) -> Path:
    """Terminal-data-dir location of the per-trade record (runner→engine contract).
    Kept as the forward-compat anchor, but a SINGLE backtest does NOT land here — see
    _engine_trades_candidates for why."""
    return data_dir / "MQL5" / "Files" / "engine_trades.csv"


def _engine_trades_candidates(data_dir: Path) -> list[Path]:
    """Every path a gated-layer EA's engine_trades.csv can land in.

    The EA writes with FILE_CSV (no FILE_COMMON). Under a single backtest the EA runs in a
    local tester *agent* whose sandbox is %APPDATA%\\MetaQuotes\\Tester\\<hash>\\Agent-*\\
    MQL5\\Files — NOT the terminal data dir. So the file never appears in data_dir\\MQL5\\Files
    (that path only ever sees opt_results.csv, which OnTesterPass writes from the collecting
    terminal, not the agent sandbox). Return the terminal path first (forward-compat) then
    every tester-agent sandbox match, oldest→newest by glob order."""
    cands = [_engine_trades_path(data_dir)]
    # data_dir = ...\MetaQuotes\Terminal\<hash>  →  tester base = ...\MetaQuotes\Tester
    tester_base = data_dir.parent.parent / "Tester"
    if tester_base.is_dir():
        cands.extend(tester_base.glob("*/Agent-*/MQL5/Files/engine_trades.csv"))
    return cands


def _read_engine_trades(data_dir: Path) -> list[dict]:
    """Read engine_trades.csv (the per-trade record a reshaped EA emits) into the dict
    shape services.sizing_pipeline.RawTrade.from_record expects. Returns [] when no file
    is present — a unit-size (un-reshaped) EA writes none, and the sized path then stays
    dormant exactly as on the NT8 side. Best-effort: any parse error yields []."""
    existing = [p for p in _engine_trades_candidates(data_dir) if p.is_file()]
    if not existing:
        return []
    # Multiple stale sandboxes can coexist; the freshest is this run's.
    path = max(existing, key=lambda p: p.stat().st_mtime)
    rows: list[dict] = []
    try:
        # EA writes FILE_ANSI, but the content is pure ASCII (numbers, ISO timestamps,
        # Long/Short, plain exit reasons), so utf-8 decodes it exactly. Python has no
        # "ansi" codec; utf-8 + errors=replace matches every other reader in this file.
        with path.open("r", newline="", encoding="utf-8", errors="replace") as fh:
            for rec in csv.DictReader(fh):
                if not rec.get("entry_time") or not rec.get("exit_time"):
                    continue
                rows.append(
                    {
                        "index": int(float(rec["index"])),
                        "entry_time": rec["entry_time"].strip(),
                        "exit_time": rec["exit_time"].strip(),
                        "direction": rec["direction"].strip(),
                        "entry_price": float(rec["entry_price"]),
                        "exit_price": float(rec["exit_price"]),
                        "stop_distance": float(rec["stop_distance"]),
                        "point_value": float(rec["point_value"]),
                        "commission_per_side": float(rec.get("commission_per_side", 0) or 0),
                        "exit_reason": (rec.get("exit_reason") or "").strip().strip('"'),
                    }
                )
    except Exception:
        return []
    return rows


def _read_mt5_journal(data_dir: Path, lines: int = 30) -> str:
    """Read the most recent MT5 journal log from <data_dir>/logs/. Returns empty string on any failure."""
    logs_dir = data_dir / "logs"
    if not logs_dir.is_dir():
        return ""
    today = datetime.date.today().strftime("%Y%m%d")
    log_file = logs_dir / f"{today}.log"
    if not log_file.is_file():
        candidates = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return ""
        log_file = candidates[-1]
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    except Exception:
        return ""


_OPT_TIMEOUT = 7200  # 2 hours for optimization runs


def _read_opt_progress(data_dir: Path) -> str:
    """Return the latest 'processing X %' or 'AutoTesting' line from the terminal log, or ''."""
    logs_dir = data_dir / "logs"
    if not logs_dir.is_dir():
        return ""
    today = datetime.date.today().strftime("%Y%m%d")
    log_file = logs_dir / f"{today}.log"
    if not log_file.is_file():
        candidates = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return ""
        log_file = candidates[-1]
    try:
        raw = log_file.read_bytes()
        text = (
            raw.decode("utf-16")
            if raw[:2] in (b"\xff\xfe", b"\xfe\xff")
            else raw.decode("utf-8", errors="replace")
        )
        for line in reversed(text.splitlines()):
            lo = line.lower()
            if "processing" in lo or "autotesting" in lo or "optimization" in lo:
                # strip the leading log-line prefix (e.g. "KR\t0\t01:09:36\tAutoTesting\t")
                parts = line.split("\t", 4)
                return parts[-1].strip() if len(parts) >= 5 else line.strip()
    except Exception:
        pass
    return ""


def _parse_mt5_optimization_report(html: str, param_names: list[str]) -> list[dict]:
    """
    Parse MT5 Strategy Tester optimization HTML report into a list of combos.

    MT5 optimization results table: header row contains standard KPI columns
    (Profit, Drawdown, Trades, etc.) plus one column per EA input param.
    Rows are combinations sorted by optimization criterion (best first).

    NOTE: HTML report format varies by MT5 version. Needs VPS validation.
    Returns empty list if the optimization results table is not found.
    """
    tp = _TableParser()
    tp.feed(html)

    _KPI_COLS = {
        "profit": "net_pnl",
        "drawdown": "max_drawdown",
        "profit factor": "profit_factor",
        "expected payoff": "expected_payoff",
        "trades": "trade_count",
        "factor": "profit_factor",
    }

    param_names_lower = {p.lower(): p for p in param_names}

    for table in tp.tables:
        if len(table) < 2:
            continue
        hdr = [h.strip() for h in table[0]]
        hdr_lower = [h.lower() for h in hdr]

        # Identify param and KPI column indices
        param_col_map: dict[str, int] = {}
        kpi_col_map: dict[str, int] = {}
        for i, h in enumerate(hdr_lower):
            for plow, porig in param_names_lower.items():
                if plow == h or plow in h:
                    param_col_map[porig] = i
            for kw, kname in _KPI_COLS.items():
                if kw in h and kname not in kpi_col_map:
                    kpi_col_map[kname] = i

        if not param_col_map:
            continue  # not the optimization results table

        combos = []
        for row in table[1:]:
            if len(row) < 2:
                continue
            params: dict = {}
            for pname, cidx in param_col_map.items():
                if cidx < len(row):
                    try:
                        v = float(row[cidx].replace(",", "").strip())
                        params[pname] = int(v) if v == int(v) else v
                    except (ValueError, OverflowError):
                        params[pname] = row[cidx]

            kpis: dict = {}
            for kname, cidx in kpi_col_map.items():
                if cidx < len(row):
                    try:
                        v = float(row[cidx].replace(",", "").replace("%", "").strip())
                        kpis[kname] = round(abs(v) if kname == "max_drawdown" else v, 4)
                    except (ValueError, OverflowError):
                        pass

            if params:
                combos.append({"params": params, "kpis": kpis})

        if combos:
            return combos

    return []


def _parse_mt5_forward_sections(html: str) -> tuple[dict, dict]:
    """
    Parse an MT5 Strategy Tester forward-test HTML report.

    Returns (is_kpis, oos_kpis) — standard KPI dicts for the in-sample and
    out-of-sample (forward) periods.

    MT5 writes the IS summary first, then a second summary block labeled
    "Forward" for the OOS period. Both follow the same table structure as a
    regular single-backtest report. If the forward section is missing, oos_kpis
    is empty.
    """
    tp = _TableParser()
    tp.feed(html)

    def _extract_kpis(tables: list[list[list[str]]]) -> dict:
        kpis_raw: dict[str, str] = {}
        for table in tables:
            for row in table:
                for i in range(0, len(row) - 1, 2):
                    k = row[i].strip().rstrip(":")
                    v = row[i + 1].strip() if i + 1 < len(row) else ""
                    if k:
                        kpis_raw[k] = v

        def _f(key: str) -> float:
            raw = kpis_raw.get(key, "")
            val = raw.split("(")[0].strip().replace(" ", "").replace(",", "")
            try:
                return float(val.rstrip("%"))
            except ValueError:
                return 0.0

        gross_profit = _f("Gross Profit")
        gross_loss = abs(_f("Gross Loss"))
        pf_raw = _f("Profit Factor")
        pf = pf_raw if pf_raw > 0 else (gross_profit / gross_loss if gross_loss else 0.0)
        total_trades = int(_f("Total Trades"))

        win_trades = 0
        for key in ("Profit Trades (% of total)", "Win Trades"):
            val = kpis_raw.get(key, "")
            m = re.match(r"^(\d+)", val.replace(" ", ""))
            if m:
                win_trades = int(m.group(1))
                break

        return {
            "net_pnl": round(_f("Total Net Profit"), 2),
            "max_drawdown": round(
                abs(_f("Equity Drawdown Maximal") or _f("Balance Drawdown Maximal")), 2
            ),
            "profit_factor": round(pf, 4),
            "trade_count": total_trades,
            "win_rate": round(win_trades / total_trades, 4) if total_trades > 0 else 0.0,
            "sharpe": round(_f("Sharpe Ratio"), 4),
        }

    # Find the "Forward" section boundary in the table list.
    # MT5 renders the forward section after a header containing "Forward" text.
    # Heuristic: scan raw HTML for "forward" keyword positions, then split tables.
    html_lower = html.lower()
    fwd_idx = html_lower.find("forward testing")
    if fwd_idx == -1:
        fwd_idx = html_lower.find("forward</")
    if fwd_idx == -1:
        fwd_idx = html_lower.find(">forward<")

    if fwd_idx == -1:
        return _extract_kpis(tp.tables), {}

    # Re-parse HTML up to forward boundary (IS section) and from it (OOS section)
    tp_is = _TableParser()
    tp_is.feed(html[:fwd_idx])
    tp_oos = _TableParser()
    tp_oos.feed(html[fwd_idx:])

    return _extract_kpis(tp_is.tables), _extract_kpis(tp_oos.tables)


def _extract_input_params(html: str, param_names: list[str]) -> dict:
    """Extract EA input parameter values from a single bt_*.htm pass report.

    MT5 optimization writes one bt_XXXXXXXX.htm per pass. Each file is a full
    single-backtest report that contains the EA inputs as name/value pairs in a
    table. This function scans all tables for those pairs and returns the values
    for the params we care about.
    """
    tp = _TableParser()
    tp.feed(html)
    kv: dict[str, str] = {}
    for table in tp.tables:
        for row in table:
            for i in range(0, len(row) - 1, 2):
                k = row[i].strip().rstrip(":")
                v = row[i + 1].strip() if i + 1 < len(row) else ""
                if k:
                    kv[k] = v
    params: dict = {}
    for pname in param_names:
        if pname in kv:
            raw = kv[pname].replace(",", "").strip()
            try:
                v = float(raw)
                params[pname] = int(v) if v == int(v) else v
            except ValueError:
                params[pname] = raw
    return params


_F_PARAM_DEFAULTS: dict = {
    "f_AccountSize": 10000.0,
    "f_RiskPerTradePct": 1.0,
    "f_DailyLossCap": 500.0,
    "f_DailyHaltFraction": 0.5,
    "f_MaxConsecutiveLosses": 0,
    "f_DailyProfitTarget": 0.0,
    "f_DailyProfitLockPct": 0.0,
}

_OPT_KPI_COLS = frozenset(
    {
        "net_pnl",
        "profit_factor",
        "max_drawdown",
        "trade_count",
        "win_trades",
        "sharpe",
        "gross_profit",
        "gross_loss",
    }
)


def _parse_opt_csv(csv_path: Path, param_ranges: dict) -> list[dict]:
    """Parse opt_results.csv written by OnTesterPass into combos list."""
    import csv as csv_mod

    results: list[dict] = []
    try:
        text = csv_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return results
    reader = csv_mod.DictReader(text.splitlines())
    for row in reader:
        params: dict = {}
        kpis: dict = {}
        for col, val in row.items():
            col = col.strip()
            try:
                fval = float(val)
            except (ValueError, TypeError):
                continue
            if col in _OPT_KPI_COLS:
                kpis[col] = fval
            else:
                # Preserve int type for params that are integer-valued
                params[col] = int(fval) if fval == int(fval) else fval

        # Only keep ranged params in the combo params dict (matches how sequential worked)
        combo_params = {k: params[k] for k in param_ranges if k in params}
        trade_count = int(kpis.get("trade_count", 0))
        win_trades = int(kpis.get("win_trades", 0))
        results.append(
            {
                "params": combo_params,
                "kpis": {
                    "net_pnl": kpis.get("net_pnl", 0.0),
                    "profit_factor": kpis.get("profit_factor", 0.0),
                    "max_drawdown": kpis.get("max_drawdown", 0.0),
                    "trade_count": trade_count,
                    "win_rate": win_trades / trade_count if trade_count > 0 else 0.0,
                    "sharpe": kpis.get("sharpe", 0.0),
                },
            }
        )
    return results


def _run_mt5_optimization(job_id: str, spec: dict) -> None:
    """Native MT5 optimization using Optimization=1 + MQL5 frame callbacks.

    Launches a single terminal with Optimization=1 — MT5 runs all combos
    across multiple CPU cores.  The EA's OnTester() sends each combo's params
    and KPIs as a frame; OnTesterPass() in the collecting terminal appends rows
    to opt_results.csv in MQL5/Files.  We read that CSV when the terminal exits.
    """

    def jl(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        with _lock:
            _jobs[job_id]["log"].append(f"[{ts}] {msg}")
        _alog(f"[opt:{job_id[:8]}] {msg}")

    def fail(msg: str) -> None:
        with _lock:
            _jobs[job_id].update({"status": "failed", "error": msg, "process": None})
        jl(f"FAILED: {msg}")

    tester_exe = _get_tester_exe()
    if tester_exe is None:
        fail("Cannot locate terminal64.exe.")
        return

    data_dir = _tester_data_dir(tester_exe)

    strategy_class = spec.get("strategy_class", "")
    symbol = spec.get("symbol", "")
    timeframe = _TF_PERIOD.get(spec.get("timeframe", "H1").upper(), "H1")
    from_date = spec.get("from_date", "")
    to_date = spec.get("to_date", "")
    model = int(spec.get("model", 0))
    deposit = float(spec.get("deposit", 100000))
    currency = spec.get("currency", "USD")
    leverage = int(spec.get("leverage", 100))
    inputs = dict(spec.get("inputs", {}))
    param_ranges = spec.get("param_ranges", {})

    if not all([strategy_class, symbol, from_date, to_date]):
        fail("Missing required fields: strategy_class, symbol, from_date, to_date")
        return
    if not param_ranges:
        fail("param_ranges cannot be empty for optimization")
        return

    ex5 = data_dir / "MQL5" / "Experts" / f"{strategy_class}.ex5"
    if not ex5.is_file():
        fail(f"EA not found: {ex5}. Deploy and compile first.")
        return

    # Inject fallback foundational defaults so workers produce real trade results
    # even when no ruleset is attached (raw-mode optimization).
    for k, default in _F_PARAM_DEFAULTS.items():
        if k in inputs and (inputs[k] is None or float(inputs[k]) < 0):
            inputs[k] = default

    # Estimate combo count for progress reporting
    total = 1
    for rng in param_ranges.values():
        if isinstance(rng, dict):
            lo, hi, step = float(rng["min"]), float(rng["max"]), float(rng["step"])
            n = max(1, round((hi - lo) / step) + 1)
        elif isinstance(rng, list):
            n = len(rng)
        else:
            n = 1
        total *= n

    jl(f"MT5 native optimization: {strategy_class} {symbol} {timeframe} [{from_date} -> {to_date}]")
    jl(f"Param ranges: {list(param_ranges.keys())} → ~{total} combos (Optimization=1)")

    tester_dir = data_dir / "MQL5" / "Profiles" / "Tester"
    reports_dir = data_dir / "reports"
    tester_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    set_filename = _write_set_file_with_ranges(data_dir, job_id, inputs, param_ranges)
    stem = f"nopt_{job_id[:8]}"
    ini_path = data_dir / f"{stem}.ini"
    csv_out = data_dir / "MQL5" / "Files" / "opt_results.csv"

    csv_out.unlink(missing_ok=True)

    _write_tester_ini(
        ini_path,
        expert=strategy_class,
        set_filename=set_filename,
        symbol=symbol,
        period=timeframe,
        from_date=from_date,
        to_date=to_date,
        model=model,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        report_prefix=f"reports\\{stem}",
        optimization=1,
        forward_mode=0,
    )

    _kill_by_path(tester_exe)
    time.sleep(2)

    try:
        proc = _launch_tester(tester_exe, ini_path)
    except Exception as exc:
        ini_path.unlink(missing_ok=True)
        fail(f"Launch failed: {exc}")
        return

    with _lock:
        _jobs[job_id].update({"process": proc, "total_count": total})

    jl(f"Launched PID {proc.pid} — waiting up to 7200s for {total} combos …")

    deadline = time.time() + 7200
    while time.time() < deadline:
        with _lock:
            if _jobs[job_id].get("status") == "cancelled":
                proc.terminate()
                ini_path.unlink(missing_ok=True)
                return
        if proc.poll() is not None:
            break
        # Report live row count so the frontend progress bar moves
        if csv_out.exists():
            try:
                rows = (
                    sum(
                        1
                        for _ in csv_out.read_text(encoding="utf-8", errors="replace").splitlines()
                    )
                    - 1
                )
                rows = max(0, rows)
            except Exception:
                rows = 0
            pct = min(99, int(rows / total * 100)) if total > 0 else 0
            with _lock:
                _jobs[job_id]["pct"] = pct
                _jobs[job_id]["message"] = f"{rows}/{total} combos"
                _jobs[job_id]["completed_count"] = rows
        time.sleep(3)
    else:
        proc.terminate()
        ini_path.unlink(missing_ok=True)
        fail("Optimization timed out after 7200s")
        return

    ini_path.unlink(missing_ok=True)
    time.sleep(2)

    if not csv_out.exists():
        fail(
            "opt_results.csv not written — OnTesterPass may not have fired. "
            "Ensure the strategy .ex5 is compiled from the latest source."
        )
        return

    results = _parse_opt_csv(csv_out, param_ranges)
    jl(f"Complete — {len(results)}/{total} combos parsed from opt_results.csv")

    if not results:
        fail("opt_results.csv exists but contained no parseable rows.")
        return

    with _lock:
        _jobs[job_id].update(
            {
                "status": "done",
                "pct": 100,
                "completed_count": len(results),
                "result": {"combos": results, "combo_count": len(results)},
                "process": None,
            }
        )


def _run_mt5_forward_test(job_id: str, spec: dict) -> None:
    """Worker thread: run MT5 Strategy Tester in forward (IS+OOS split) mode."""

    def jl(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        with _lock:
            _jobs[job_id]["log"].append(f"[{ts}] {msg}")
        _alog(f"[fwd:{job_id[:8]}] {msg}")

    def fail(msg: str) -> None:
        with _lock:
            _jobs[job_id].update({"status": "failed", "error": msg, "process": None})
        jl(f"FAILED: {msg}")

    tester_exe = _get_tester_exe()
    if tester_exe is None:
        fail("Cannot locate tester exe.")
        return

    data_dir = _tester_data_dir(tester_exe)

    strategy_class = spec.get("strategy_class", "")
    symbol = spec.get("symbol", "")
    timeframe = _TF_PERIOD.get(spec.get("timeframe", "H1").upper(), "H1")
    from_date = spec.get("from_date", "")
    to_date = spec.get("to_date", "")
    model = int(spec.get("model", 0))
    deposit = float(spec.get("deposit", 100000))
    currency = spec.get("currency", "USD")
    leverage = int(spec.get("leverage", 100))
    inputs = spec.get("inputs", {})
    # ForwardMode: 2=1/2, 3=1/3, 4=1/4 of period is OOS. Default: 3 (33% OOS ≈ 30% target).
    oos_pct = int(spec.get("oos_pct", 30))
    if oos_pct >= 50:
        forward_mode = 2
    elif oos_pct >= 33:
        forward_mode = 3
    else:
        forward_mode = 4

    if not all([strategy_class, symbol, from_date, to_date]):
        fail("Missing required fields")
        return

    ex5 = data_dir / "MQL5" / "Experts" / f"{strategy_class}.ex5"
    if not ex5.is_file():
        fail(f"EA not found: {ex5}")
        return

    jl(
        f"MT5 forward test: {strategy_class} {symbol} {timeframe} [{from_date} -> {to_date}]  forward_mode={forward_mode}"
    )

    try:
        set_filename = _write_set_file(data_dir, job_id, inputs)
        reports_dir = data_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_stem = f"fwd_{job_id[:8]}"
        report_file = reports_dir / f"{report_stem}.htm"
        report_prefix = f"reports\\{report_stem}"
        ini_path = data_dir / f"fwd_{job_id[:8]}.ini"
        _write_tester_ini(
            ini_path,
            expert=strategy_class,
            set_filename=set_filename,
            symbol=symbol,
            period=timeframe,
            from_date=from_date,
            to_date=to_date,
            model=model,
            deposit=deposit,
            currency=currency,
            leverage=leverage,
            report_prefix=report_prefix,
            optimization=0,
            forward_mode=forward_mode,
        )
        _kill_by_path(tester_exe)
        proc = _launch_tester(tester_exe, ini_path)
    except Exception as exc:
        fail(f"Setup/launch failed: {exc}")
        return

    with _lock:
        _jobs[job_id]["process"] = proc
    jl(f"Launched {tester_exe.name} (pid={proc.pid}) — forward mode={forward_mode}")

    deadline = time.time() + _BACKTEST_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            time.sleep(2)
            break
        time.sleep(_REPORT_POLL_INTERVAL)
    else:
        try:
            proc.kill()
        except Exception:
            pass
        fail(f"Forward test timed out after {_BACKTEST_TIMEOUT}s")
        return

    with _lock:
        if _jobs[job_id].get("status") == "cancelled":
            return

    if not report_file.is_file():
        alts = sorted(reports_dir.glob(f"{report_stem}*.htm"), key=lambda p: p.stat().st_mtime)
        report_file = alts[-1] if alts else None  # type: ignore[assignment]

    if report_file is None or not report_file.is_file():  # type: ignore[union-attr]
        fail("Forward test finished but no report file found.")
        return

    try:
        raw_bytes = report_file.read_bytes()  # type: ignore[union-attr]
        html_text = (
            raw_bytes.decode("utf-16")
            if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff")
            else raw_bytes.decode("utf-8", errors="replace")
        )
        is_kpis, oos_kpis = _parse_mt5_forward_sections(html_text)
    except Exception as exc:
        fail(f"Forward test report parsing failed: {exc}")
        return

    _kill_by_path(tester_exe)

    for p in [ini_path, data_dir / "MQL5" / "Profiles" / "Tester" / set_filename]:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    jl(f"Complete — IS pnl={is_kpis.get('net_pnl')}  OOS pnl={oos_kpis.get('net_pnl')}")

    with _lock:
        _jobs[job_id].update(
            {
                "status": "done",
                "result": {
                    "is_kpis": is_kpis,
                    "oos_kpis": oos_kpis,
                    "forward_mode": forward_mode,
                },
                "process": None,
            }
        )


def _run_backtest(job_id: str, spec: dict) -> None:
    """Worker thread: configure, launch, poll, parse, store result."""

    def jl(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        with _lock:
            _jobs[job_id]["log"].append(f"[{ts}] {msg}")
        _alog(f"[job:{job_id[:8]}] {msg}")

    def fail(msg: str) -> None:
        with _lock:
            _jobs[job_id].update({"status": "failed", "error": msg, "process": None})
        jl(f"FAILED: {msg}")

    tester_exe = _get_tester_exe()
    if tester_exe is None:
        fail("Cannot locate metatester64.exe / terminal64.exe. Set TERMINAL_PATH env var.")
        return

    data_dir = _tester_data_dir(tester_exe)
    jl(f"Data dir: {data_dir}")

    strategy_class = spec.get("strategy_class", "")
    symbol = spec.get("symbol", "")  # preserve broker suffix case (e.g. XAUUSD.s on PU Prime)
    timeframe = _TF_PERIOD.get(spec.get("timeframe", "H1").upper(), "H1")
    from_date = spec.get("from_date", "")
    to_date = spec.get("to_date", "")
    model = int(spec.get("model", 0))
    deposit = float(spec.get("deposit", 10000))
    currency = spec.get("currency", "USD")
    leverage = int(spec.get("leverage", 100))
    inputs = spec.get("inputs", {})

    if not all([strategy_class, symbol, from_date, to_date]):
        fail("Missing required fields: strategy_class, symbol, from_date, to_date")
        return

    ex5 = data_dir / "MQL5" / "Experts" / f"{strategy_class}.ex5"
    if not ex5.is_file():
        fail(f"EA not found: {ex5}. Deploy and compile the strategy first (Step 9).")
        return

    jl(f"Backtest: {strategy_class} {symbol} {timeframe} [{from_date} -> {to_date}]")

    try:
        set_filename = _write_set_file(data_dir, job_id, inputs)
        jl(f"Set file: {set_filename}")

        reports_dir = data_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_stem = f"bt_{job_id[:8]}"
        report_file = reports_dir / f"{report_stem}.htm"
        # MT5 resolves Report= relative to the data directory, not the exe directory.
        # Use a relative path so MT5 writes <data_dir>/reports/<stem>.htm.
        report_prefix = f"reports\\{report_stem}"

        ini_path = data_dir / f"tester_{job_id[:8]}.ini"
        _write_tester_ini(
            ini_path,
            expert=strategy_class,
            set_filename=set_filename,
            symbol=symbol,
            period=timeframe,
            from_date=from_date,
            to_date=to_date,
            model=model,
            deposit=deposit,
            currency=currency,
            leverage=leverage,
            report_prefix=report_prefix,
        )
        jl(f"Config: {ini_path}")

        # Clear any stale per-trade record so a reshaped EA's engine_trades.csv reflects
        # only this run (a failed/empty run must not ship the prior run's trades). Clears
        # every candidate — the terminal path AND each tester-agent sandbox — since a single
        # backtest writes to the sandbox, not data_dir\MQL5\Files.
        for stale in _engine_trades_candidates(data_dir):
            try:
                stale.unlink(missing_ok=True)
            except Exception:
                pass

        killed = _kill_by_path(tester_exe)
        if killed:
            jl(f"Closed existing {tester_exe.name} instance before launch")
        proc = _launch_tester(tester_exe, ini_path)
    except Exception as exc:
        fail(f"Setup/launch failed: {exc}")
        return

    with _lock:
        _jobs[job_id]["process"] = proc
    jl(f"Launched {tester_exe.name} (pid={proc.pid})")

    # Poll until process exits or timeout
    deadline = time.time() + _BACKTEST_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            jl(f"Process exited (returncode={proc.returncode})")
            time.sleep(2)  # let MT5 flush the report to disk before reading
            break
        time.sleep(_REPORT_POLL_INTERVAL)
    else:
        jl(f"Timeout after {_BACKTEST_TIMEOUT}s - force-killing tester (pid={proc.pid})")
        try:
            proc.kill()
        except Exception:
            pass
        # Only kill metatester64 by name — never terminal64, which may be running live bots
        _kill_by_name("metatester64.exe")
        fail(f"Backtest timed out after {_BACKTEST_TIMEOUT}s")
        return

    with _lock:
        if _jobs[job_id].get("status") == "cancelled":
            return

    # MT5 sometimes appends a digit when a same-named report already exists
    if not report_file.is_file():
        alts = sorted(reports_dir.glob(f"{report_stem}*.htm"), key=lambda p: p.stat().st_mtime)
        report_file = alts[-1] if alts else None  # type: ignore[assignment]

    if report_file is None or not report_file.is_file():  # type: ignore[union-attr]
        journal = _read_mt5_journal(data_dir)
        detail = f"\nMT5 journal (last lines):\n{journal}" if journal else ""
        fail(f"Backtest finished but no report file found. Check symbol, dates, and EA.{detail}")
        return

    jl(f"Report: {report_file.name}")  # type: ignore[union-attr]

    try:
        raw_bytes = report_file.read_bytes()  # type: ignore[union-attr]
        # MT5 writes HTML reports as UTF-16 LE (BOM ff fe). Detect and decode correctly.
        if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
            html_text = raw_bytes.decode("utf-16")
        else:
            html_text = raw_bytes.decode("utf-8", errors="replace")
        result = _parse_mt5_report(html_text)
    except Exception as exc:
        fail(f"Report parsing failed: {exc}")
        return

    # If the EA was reshaped to the gated-layer rules it wrote the per-trade record
    # (the runner→engine contract). Ship it so the backend sizes the run offline; a
    # unit-size EA writes none and the key stays absent (sized path dormant), exactly
    # like the NT8 side. The report itself remains the unit-size reference.
    engine_trades = _read_engine_trades(data_dir)
    if engine_trades:
        result["engine_trades"] = engine_trades
        jl(f"engine_trades: shipped {len(engine_trades)} rows for offline sizing")

    jl(
        f"Complete - pnl={result['net_pnl']:.2f}  "
        f"trades={result['trade_count']}  "
        f"pf={result['profit_factor']:.2f}"
    )

    # Kill the terminal in case ShutdownTerminal=1 didn't take effect
    _kill_by_path(tester_exe)

    for p in [ini_path, data_dir / "MQL5" / "Profiles" / "Tester" / set_filename]:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    with _lock:
        _jobs[job_id].update({"status": "done", "result": result, "process": None})


@app.route("/backtests", methods=["POST"])
def start_backtest():
    """
    POST /backtests
    Body: {strategy_class, symbol, timeframe?, from_date, to_date,
           model?, deposit?, currency?, leverage?, inputs?}
    Returns 202: {job_id, status: "running"}
    """
    body = request.get_json(force=True, silent=True) or {}
    missing = [f for f in ["strategy_class", "symbol", "from_date", "to_date"] if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    job_id = body.get("job_id") or str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "created_at": int(time.time()),
            "spec": body,
            "log": [],
            "process": None,
            "error": None,
            "result": None,
        }

    threading.Thread(target=_run_backtest, args=(job_id, body), daemon=True).start()
    _alog(f"Backtest job {job_id[:8]} queued: {body.get('strategy_class')} {body.get('symbol')}")
    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/backtests/<job_id>")
def backtest_status(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    with _lock:
        snap = {k: v for k, v in job.items() if k not in ("log", "process", "result", "spec")}
    return jsonify(snap)


@app.route("/backtests/<job_id>/results")
def backtest_results(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    status = job.get("status")
    if status == "running":
        return jsonify({"error": "Job still running", "status": "running"}), 202
    if status != "done":
        return jsonify({"error": job.get("error", "Job failed"), "status": status}), 422
    with _lock:
        result = dict(job.get("result") or {})
    return jsonify({"job_id": job_id, "runner": "mt5", **result})


@app.route("/backtests/<job_id>/log")
def backtest_log(job_id: str):
    lines = int(request.args.get("lines", 200))
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    with _lock:
        tail = list(job.get("log", [])[-lines:])
    return jsonify({"log": "\n".join(tail)})


@app.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.get("status") != "running":
        return jsonify({"error": "Job not running", "status": job.get("status")}), 409

    with _lock:
        proc = job.get("process")
        _jobs[job_id]["status"] = "cancelled"
        _jobs[job_id]["error"] = "Cancelled by user"
        _jobs[job_id]["process"] = None

    if proc is not None:
        try:
            proc.kill()
        except Exception:
            pass
    # Only kill metatester64 by name — never terminal64, which may be running live bots
    _kill_by_name("metatester64.exe")
    _alog(f"Job {job_id[:8]} cancelled")
    return jsonify({"ok": True})


# ── MT5 Native Optimizer (Step 4) ────────────────────────────────────────────


@app.route("/native-optimize", methods=["POST"])
def start_native_optimize():
    """
    POST /native-optimize
    Body: {job_id, strategy_class, symbol, timeframe?, from_date, to_date,
           model?, deposit?, inputs (fixed params), param_ranges (ranged params)}
    Runs MT5 Strategy Tester in Optimization mode (Optimization=1 in ini).
    """
    body = request.get_json(force=True, silent=True) or {}
    job_id = body.get("job_id") or str(uuid.uuid4())
    missing = [f for f in ["strategy_class", "symbol", "from_date", "to_date"] if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    if not body.get("param_ranges"):
        return jsonify({"error": "param_ranges cannot be empty"}), 400

    with _lock:
        if job_id in _jobs and _jobs[job_id]["status"] == "running":
            return jsonify({"error": "Job already running"}), 409
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "pct": 0,
            "message": "Starting MT5 optimization",
            "created_at": int(time.time()),
            "spec": body,
            "log": [],
            "process": None,
            "error": None,
            "result": None,
        }
    _alog(f"MT5 opt job {job_id[:8]} queued: {body.get('strategy_class')} {body.get('symbol')}")
    threading.Thread(target=_run_mt5_optimization, args=(job_id, body), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/backtests/<job_id>/native-opt-results")
def native_opt_results(job_id: str):
    """Return MT5 optimization result combos list after job completes."""
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    status = job.get("status")
    if status == "running":
        return jsonify({"error": "Job still running", "status": "running"}), 202
    if status != "done":
        return jsonify({"error": job.get("error", "Job failed"), "status": status}), 422
    with _lock:
        result = dict(job.get("result") or {})
    return jsonify({"job_id": job_id, "runner": "mt5", **result})


@app.route("/native-walkforward", methods=["POST"])
def start_native_walkforward():
    """
    POST /native-walkforward
    Body: {job_id, strategy_class, symbol, timeframe?, from_date, to_date,
           inputs (flat param dict), oos_pct? (default 30)}
    Runs MT5 Strategy Tester with ForwardMode set based on oos_pct.
    """
    body = request.get_json(force=True, silent=True) or {}
    job_id = body.get("job_id") or str(uuid.uuid4())
    missing = [f for f in ["strategy_class", "symbol", "from_date", "to_date"] if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    with _lock:
        if job_id in _jobs and _jobs[job_id]["status"] == "running":
            return jsonify({"error": "Job already running"}), 409
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "created_at": int(time.time()),
            "spec": body,
            "log": [],
            "process": None,
            "error": None,
            "result": None,
        }
    _alog(f"MT5 forward job {job_id[:8]} queued: {body.get('strategy_class')} {body.get('symbol')}")
    threading.Thread(target=_run_mt5_forward_test, args=(job_id, body), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/backtests/<job_id>/native-wf-results")
def native_wf_results(job_id: str):
    """Return MT5 forward test IS/OOS results after job completes."""
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    status = job.get("status")
    if status == "running":
        return jsonify({"error": "Job still running", "status": "running"}), 202
    if status != "done":
        return jsonify({"error": job.get("error", "Job failed"), "status": status}), 422
    with _lock:
        result = dict(job.get("result") or {})
    return jsonify({"job_id": job_id, "runner": "mt5", **result})


# ── Step 9: MT5 deployment ────────────────────────────────────────────────────


def _find_metaeditor() -> Optional[Path]:
    """Locate metaeditor64.exe — same directory as terminal64.exe."""
    candidates: list[Path] = []
    env = os.environ.get("METAEDITOR_PATH", "")
    if env:
        candidates.append(Path(env))
    tester = _get_tester_exe()
    if tester is not None:
        candidates.append(tester.parent / "metaeditor64.exe")
    for p in candidates:
        if p.exists():
            return p
    return None


def _read_compile_log(log_path: Path) -> list[str]:
    """Read a MetaEditor compile log into stripped non-empty lines.

    MetaEditor writes the log as UTF-16 (with BOM); fall back to UTF-8.
    Returns [] if the file is missing or unreadable.
    """
    if not log_path.is_file():
        return []
    try:
        raw = log_path.read_bytes()
    except Exception:
        return []
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _run_compile(job_id: str, experts_dir: Path) -> None:
    """Compile every .mq5 in the Experts folder and verify each produced a new binary.

    MetaEditor's exit code is unreliable and the directory form (/compile:<dir>)
    can silently no-op, reporting success while leaving a stale .ex5 in place.
    So we compile each explicit .mq5 file path (/compile:<file> /log), then confirm
    the matching .ex5 actually exists and its mtime advanced past the value recorded
    before the compile. A file whose .ex5 mtime did not move is a hard failure with
    its compiler log lines surfaced — never reported as success. This mirrors the NT8
    agent, which confirms its compile by NinjaTrader.Custom.dll mtime.
    """
    with _lock:
        _compile_jobs[job_id]["started_at"] = time.time()

    meta = _find_metaeditor()
    if meta is None:
        with _lock:
            _compile_jobs[job_id].update(
                {
                    "status": "failed",
                    "errors": [
                        "metaeditor64.exe not found — set METAEDITOR_PATH or ensure it is in the MT5 terminal directory"
                    ],
                    "completed_at": time.time(),
                }
            )
        return

    sources = sorted(experts_dir.glob("*.mq5"))
    if not sources:
        with _lock:
            _compile_jobs[job_id].update(
                {
                    "status": "failed",
                    "errors": [f"No .mq5 files found in {experts_dir}"],
                    "completed_at": time.time(),
                }
            )
        return

    errors: list[str] = []
    warnings: list[str] = []
    compiled: list[str] = []
    try:
        for src in sources:
            ex5 = src.with_suffix(".ex5")
            log_path = src.with_suffix(".log")
            # Record the binary's mtime BEFORE — this is the authoritative
            # success signal, not MetaEditor's exit code.
            pre_mtime = ex5.stat().st_mtime if ex5.exists() else 0.0
            log_path.unlink(missing_ok=True)

            subprocess.run(
                [str(meta), f"/compile:{src}", "/log"],
                timeout=120,
                capture_output=True,
            )

            log_lines = _read_compile_log(log_path)
            post_mtime = ex5.stat().st_mtime if ex5.exists() else 0.0

            if ex5.exists() and post_mtime > pre_mtime:
                compiled.append(src.name)
                # Match real warning lines only — MQL5 format is
                # "file(line,col) : warning 123: message". The trailing summary
                # line "Result: 0 errors, 0 warnings, ..." also contains the word
                # "warning", so a bare substring check false-positives on a clean
                # build. Require the ": warning" token, mirroring the ": error" check below.
                for ln in log_lines:
                    if ": warning" in ln.lower():
                        warnings.append(f"{src.name}: {ln}")
            else:
                # mtime did not advance → no new binary was produced (silent no-op
                # or a compile error). Surface the compiler log so the failure is loud.
                errors.append(f"{src.name}: .ex5 not updated — no new binary produced")
                err_lines = [
                    ln for ln in log_lines if ": error" in ln.lower() or "error(s)" in ln.lower()
                ]
                errors.extend(f"{src.name}: {ln}" for ln in (err_lines or log_lines[-10:]))

            log_path.unlink(missing_ok=True)

        status = "success" if not errors else "failed"
        with _lock:
            _compile_jobs[job_id].update(
                {
                    "status": status,
                    "errors": errors,
                    "warnings": warnings,
                    "compiled": compiled,
                    "completed_at": time.time(),
                }
            )
        _alog(
            f"Compile {job_id[:8]}: {status} — {len(compiled)} binary(ies) updated, {len(errors)} error line(s)"
        )
    except subprocess.TimeoutExpired:
        with _lock:
            _compile_jobs[job_id].update(
                {
                    "status": "failed",
                    "errors": errors + ["MetaEditor compile timed out (120 s)"],
                    "completed_at": time.time(),
                }
            )
    except Exception as exc:
        with _lock:
            _compile_jobs[job_id].update(
                {"status": "failed", "errors": errors + [str(exc)], "completed_at": time.time()}
            )


@app.route("/files/strategies/<filename>", methods=["POST"])
def upload_strategy_file(filename: str):
    if not filename.endswith(".mq5"):
        return jsonify({"error": "Only .mq5 files are allowed"}), 400

    experts = _detect_experts_dir()
    if experts is None:
        return jsonify({"error": "MT5 Experts folder not found — is MT5 running?"}), 503

    dest = experts / filename
    overwrite = request.form.get("overwrite", "false").lower() == "true"
    if dest.exists() and not overwrite:
        return jsonify({"error": f"{filename} already exists on VPS"}), 409

    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "Missing 'file' in multipart body"}), 400

    content = f.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return jsonify({"error": f"File exceeds 256 KB limit ({len(content)} bytes)"}), 400

    try:
        dest.write_bytes(content)
    except IOError as exc:
        return jsonify({"error": f"Write failed: {exc}"}), 423

    _alog(f"Uploaded {filename} ({len(content)} bytes)")
    return jsonify(_file_info(dest)), 201


@app.route("/files/strategies/<filename>", methods=["DELETE"])
def delete_strategy_file(filename: str):
    if not filename.endswith((".mq5", ".ex5")):
        return jsonify({"error": "Only .mq5 or .ex5 files may be deleted"}), 400

    experts = _detect_experts_dir()
    if experts is None:
        return jsonify({"error": "MT5 Experts folder not found — is MT5 running?"}), 503

    target = experts / filename
    if not target.exists():
        return jsonify({"error": f"{filename} not found"}), 404

    try:
        target.unlink()
    except IOError as exc:
        return jsonify({"error": f"File locked: {exc}"}), 423

    _alog(f"Deleted {filename}")
    return jsonify({"ok": True, "filename": filename})


@app.route("/compile", methods=["POST"])
def trigger_compile():
    experts = _detect_experts_dir()
    if experts is None:
        return jsonify({"error": "MT5 Experts folder not found — is MT5 running?"}), 503

    job_id = str(uuid.uuid4())
    with _lock:
        _compile_jobs[job_id] = {
            "compile_job_id": job_id,
            "status": "running",
            "errors": [],
            "warnings": [],
            "started_at": None,
            "completed_at": None,
        }

    threading.Thread(target=_run_compile, args=(job_id, experts), daemon=True).start()
    _alog(f"Compile job {job_id[:8]} started (Experts: {experts})")
    return jsonify({"compile_job_id": job_id, "status": "running"}), 202


@app.route("/compile/<compile_job_id>")
def compile_status(compile_job_id: str):
    with _lock:
        job = _compile_jobs.get(compile_job_id)
    if job is None:
        return jsonify({"error": "Compile job not found"}), 404
    return jsonify(job)


# ── Startup ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _alog(f"MT5 Agent starting on port {PORT}...")
    if not MT5_AVAILABLE:
        _alog("WARNING: MetaTrader5 package not installed - run: pip install MetaTrader5")
        _alog("Historical data and backtests will return 503 until the package is installed.")
    else:
        ok, err = _ensure_mt5()
        if ok:
            _alog("MT5 connection established")
            _detect_experts_dir()
        else:
            _alog(f"MT5 not connected at startup: {err}")
            _alog("Start MT5 terminal and restart the agent to connect.")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
