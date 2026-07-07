#!/usr/bin/env python3
"""
compare_svp.py — parity check: TradingView Pine export vs Python SVP engine.

Purpose
-------
Prove the Python engine in svp/ produces the same Asia POC / "MV" line as the source-of-truth SESSION
VOLUME PROFILE block in mpc_assistant.pine (line ~2554) and its MV confirmation slot (line ~2772), on
real candles. It feeds each bar (timestamp + open/high/low/close + volume) through SvpEngine and diffs
the current POC, the form pulse and the sweep state against the px_* columns the Pine build in
indicators/svp_export.pine plotted, bar by bar.

What is compared (per bar, after --warmup)
------------------------------------------
  * px_svp_poc    — the current Asia POC price (abs tolerance, na-aware). Deterministic: same formula,
                    same session H/L + volume → bit-identical, so the tolerance is tight. A whole-row
                    jump (~range/100 on gold) means the POC ROW diverged, not float noise.
  * px_svp_formed — 1 on the bar a fresh POC forms (pulse). Pine-validated.
  * px_svp_swept  — mv_swept, 1 once price has straddled the current POC since it formed. Pine-validated.

Volume
------
The engine is FED the volume from the export's `px_volume` column (falling back to a native `volume`
column), so both sides use the identical volume series — no data-source mismatch.

No calibration knob
-------------------
Unlike VWAP / liquidity, the SVP anchor is the ASIA SESSION (2000-0500 GMT-4, a fixed offset —
season-independent), not the trading-day boundary, so there is no --htf-rollover to sweep. The Asia
window comes from the composed, already-Pine-validated sessions engine.

Warmup
------
If the export opens MID-Asia-session, Pine's svpNew never fires for that partial session (its
na-history guard) so Pine builds no profile, while the composed sessions engine opens a session at
bar 0 and would form a spurious early POC. Skip past the first full Asia close with --warmup; the tool
prints the last mismatching bar to help pick it. From the first fresh in-window Asia open on, both
sides match.

Usage
-----
    python3 engines/session_volume_profile/tools/compare_svp.py path/to/svp_export.csv
    python3 engines/session_volume_profile/tools/compare_svp.py svp_export.csv --warmup 300

Exit 0 if every compared field matches on every warm bar, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from session_volume_profile import SvpEngine

PRICE_FIELDS = ["px_svp_poc"]
FLAG_FIELDS = ["px_svp_formed", "px_svp_swept"]
ALL_FIELDS = PRICE_FIELDS + FLAG_FIELDS

_SECONDS_CEILING = 10 ** 11


def _num(s):
    if s is None:
        return None
    s = s.strip()
    if s == "" or s.lower() in ("na", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_ms(raw):
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        v = int(raw)
        return v * 1000 if v < _SECONDS_CEILING else v
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _resolve_columns(header):
    lower = {h.lower().strip(): h for h in header}

    def find(name, required=True):
        col = lower.get(name)
        if col is None and required:
            raise SystemExit(f"ERROR: column {name!r} not found in export. Header: {header}")
        return col

    cols = {"time": find("time"), "open": find("open"),
            "high": find("high"), "low": find("low"), "close": find("close")}
    # volume input: prefer the explicit px_volume column, fall back to a native volume column
    cols["volume"] = find("px_volume", False) or find("volume", False)
    if cols["volume"] is None:
        raise SystemExit("ERROR: no volume column ('px_volume' or 'volume') found in export. "
                         f"Header: {header}")
    for fld in ALL_FIELDS:
        cols[fld] = find(fld)
    return cols


def _load_rows(path, cols):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    tcol = cols["time"]
    keys = []
    for r in rows:
        try:
            keys.append(_to_ms(r.get(tcol)))
        except Exception:
            keys.append(None)
    if all(k is not None for k in keys) and keys != sorted(keys):
        rows = [r for _, r in sorted(zip(keys, rows), key=lambda p: p[0])]
    return rows


def _values_match(field, py_val, pine_val, tol):
    if py_val is None and pine_val is None:
        return True
    if py_val is None or pine_val is None:
        return False
    if field in PRICE_FIELDS:
        return abs(py_val - pine_val) <= tol      # POC price — deterministic, tight tolerance
    return int(round(py_val)) == int(round(pine_val))    # formed / swept flags


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="CSV exported from TradingView with svp_export.pine on the chart")
    ap.add_argument("--tolerance", type=float, default=1e-6, help="abs tolerance for the POC price (default 1e-6)")
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars in the report (still fed to the engine)")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    engine = SvpEngine()
    compared_fields = [f for f in ALL_FIELDS if cols.get(f) is not None]

    total = 0
    per_field_mismatch = {fld: 0 for fld in compared_fields}
    detailed = []
    last_mismatch_bar = None

    for i, row in enumerate(rows):
        o = _num(row[cols["open"]])
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (o, h, l, c):
            continue
        vol = _num(row[cols["volume"]])
        ts_ms = _to_ms(row[cols["time"]])

        ev = engine.update(i, ts_ms, o, h, l, c, vol)
        py = {"px_svp_poc": ev.poc,
              "px_svp_formed": 1 if ev.formed else 0,
              "px_svp_swept": 1 if ev.swept else 0}
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in compared_fields:
            pine_val = _num(row[cols[fld]])
            if not _values_match(fld, py[fld], pine_val, args.tolerance):
                per_field_mismatch[fld] += 1
                bar_mismatches.append((fld, py[fld], pine_val))
        if bar_mismatches:
            last_mismatch_bar = i
            if len(detailed) < args.max_report:
                detailed.append((i, row[cols["time"]], bar_mismatches))

    mismatched_fields = {f: n for f, n in per_field_mismatch.items() if n}
    print(f"Compared {total} bars ({args.warmup} warmup skipped) across {len(compared_fields)} fields.")
    if not mismatched_fields:
        print("PARITY OK — every field matches on every warm bar.")
        return 0

    print(f"MISMATCH — {sum(mismatched_fields.values())} field-mismatches; last at bar {last_mismatch_bar}.")
    print("Per-field mismatch counts:")
    for fld, n in sorted(mismatched_fields.items(), key=lambda p: -p[1]):
        print(f"  {fld}: {n}")
    print(f"\nFirst {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, t, fields in detailed:
        for fld, pv, xv in fields:
            print(f"  bar {idx} @ {t}  {fld}: {pv} vs {xv}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
