#!/usr/bin/env python3
"""The parity gate — replay a real TradingView export through the Python port and diff it.

    python strategies/python/smc_session_sweep/tools/compare_smc_session_sweep.py \\
        "engines/VANTAGE_XAUUSD, 5_73331.csv" --warmup 500

**Exit 0 means the two implementations AGREE on every compared bar.** It does NOT mean either is
right, and it says nothing at all about a branch neither side entered — which is why this tool
always prints the block-code histogram, the closed-trade count and the decoded config. A guard
that fired zero times was validated by nothing.

**What each column is compared AGAINST, so this file can never quietly agree with the port it is
checking:** every `px_*` column is the PINE's own plotted value, read from the CSV, diffed
against the value the port computed for the same bar from bars alone. Four columns are FED to the
port rather than compared — `px_dir`, `px_dir_shifts`, `px_conf_dir`, `px_conf_shifts` — because
the 15-minute and 1-minute structure streams cannot be derived from a 5-minute chart at all. They
are listed in the report as fed, not as passed, and `engines/market_structure/` is what proves
them. The previous-day and previous-week levels are fed for the same reason: they cross a
`request.security` boundary with lookahead on.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.smc_session_sweep.config import SessionSweepConfig  # noqa: E402
from strategies.python.smc_session_sweep.core import BarInput, SessionSweepCore  # noqa: E402

#: Fed to the port, never compared. Each one names WHY, so nobody promotes it to evidence.
FED = {
    "px_dir": "15m structure — not derivable from a 5m chart",
    "px_dir_shifts": "15m structure — not derivable from a 5m chart",
    "px_conf_dir": "1m structure — not derivable from a 5m chart",
    "px_conf_shifts": "1m structure — not derivable from a 5m chart",
    "px_pdh": "request.security 'D' with lookahead on",
    "px_pdl": "request.security 'D' with lookahead on",
    "px_pwh": "request.security 'W' with lookahead on",
    "px_pwl": "request.security 'W' with lookahead on",
}

#: Compared as exact integers — a bitfield or an enum, where "close" is meaningless.
EXACT = ("px_sess", "px_state", "px_poi_bits", "px_blk_l", "px_blk_s",
         "px_pend_dir", "px_pos_dir", "px_exec")

#: Compared as prices, to the tick.
PRICE = ("px_pool_hi", "px_pool_lo", "px_swp_hi", "px_swp_lo",
         "px_poi_bull_t", "px_poi_bull_b", "px_poi_bear_t", "px_poi_bear_b",
         "px_arm_top", "px_arm_bot",
         "px_ent_l", "px_stp_l", "px_dist_l", "px_t1_l", "px_t2_l",
         "px_ent_s", "px_stp_s", "px_dist_s", "px_t1_s", "px_t2_s",
         "px_min_stop", "px_fill", "px_stop_live", "px_sl", "px_tp1", "px_tp2",
         "px_atr14")

#: Compared to the venue's quantity step. ⚠ It was a 0.1% RELATIVE tolerance until 2026-09-20 and
#: that tolerance was hiding a real defect on every trade: the port kept the full float where
#: TradingView truncates to the lot step. A tolerance wide enough to pass a wrong answer is an
#: accommodation written to match the port, which is the one thing a comparator may never be.
QTY = ("px_qty",)

#: An R multiple compounds every earlier rounding; a tick of entry price moves its last digit.
SOFT = ("px_closed_r",)

#: Features whose code a green run may or may not have RUN. A rule that never fired in the
#: window was validated by nothing, however green the exit code — so this table prints on every
#: run beside the block histogram, and a zero is reported as a hole rather than a pass.
EXEC_FEATURES = {
    1: "a fill",
    2: "a position closed",
    4: "the first target reached",
    8: "breakeven on an opposite shift",
    16: "the two-leg exit ladder armed",
    32: "the time stop",
    64: "a long armed",
    128: "a short armed",
}

STATE_FEATURES = {
    128: "the confirmation confirmed a short",
    256: "the confirmation confirmed a long",
    8192: "a new shift on the confirmation timeframe",
    16384: "the at-the-zone entry mode",
    32768: "the no-gap entry mode",
    65536: "price touched an armed zone",
    262144: "a resting order cancelled",
}

BLOCK_WHY = {
    0: "armed",
    1: "that direction is switched off",
    2: "the direction timeframe is not on this side",
    3: "outside a session that trades",
    4: "the previous session's level has not been taken",
    5: "no change of character on the confirmation timeframe yet",
    6: "no untouched gap left on this side of price",
    7: "the gap is beyond the max-distance filter",
    8: "the stop it needs is under the minimum-stop floor",
    9: "no target far enough away to be worth the risk",
    10: "already in a trade, an order waiting, or this session already traded",
    11: "outside the execution hours",
}


def _f(v):
    if v is None or v == "":
        return float("nan")
    try:
        return float(v)
    except ValueError:
        return float("nan")


def _same(a: float, b: float, tol: float) -> bool:
    na_a = a != a
    na_b = b != b
    if na_a or na_b:
        return na_a and na_b
    return abs(a - b) <= tol


def load(path: Path):
    """Read the export, and refuse the two shapes that make a diff meaningless."""
    rows = list(csv.DictReader(path.open()))
    if not rows:
        raise SystemExit(f"{path}: no rows")

    # TradingView appends the still-forming live bar with its plotted series blank. Trim a
    # TRAILING run of those; a blank row in the MIDDLE is a broken export and is refused.
    def blank(r):
        return r.get("px_state", "") in ("", None)

    end = len(rows)
    while end > 0 and blank(rows[end - 1]):
        end -= 1
    trimmed = len(rows) - end
    rows = rows[:end]
    holes = [i for i, r in enumerate(rows) if blank(r)]
    if holes:
        raise SystemExit(
            f"{path}: {len(holes)} blank row(s) inside the export (first at row {holes[0] + 2}). "
            "That is a broken export, not a live bar — re-export it."
        )
    return rows, trimmed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="?", default="engines/VANTAGE_XAUUSD, 5_73331.csv")
    ap.add_argument("--warmup", type=int, default=500,
                    help="bars replayed but NOT compared, so engine warm-up is not read as a defect")
    ap.add_argument("--max-report", type=int, default=12)
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.is_absolute():
        path = _ROOT / path
    rows, trimmed = load(path)

    cfg = SessionSweepConfig.from_export(rows[len(rows) // 2])
    core = SessionSweepCore(cfg)

    mismatches = {}
    compared = 0
    blk_hist = Counter()
    feat_hist = Counter()
    pine_trades = 0
    port_trades = 0

    for i, r in enumerate(rows):
        b = BarInput(
            time_ms=int(float(r["time"])) * 1000,
            open=_f(r["open"]), high=_f(r["high"]), low=_f(r["low"]), close=_f(r["close"]),
            dir_dir=int(_f(r["px_dir"])) if r["px_dir"] else 0,
            dir_shifts=int(_f(r["px_dir_shifts"])) if r["px_dir_shifts"] else 0,
            conf_dir=int(_f(r["px_conf_dir"])) if r["px_conf_dir"] else 0,
            conf_shifts=int(_f(r["px_conf_shifts"])) if r["px_conf_shifts"] else 0,
            pdh=_f(r["px_pdh"]), pdl=_f(r["px_pdl"]), pwh=_f(r["px_pwh"]), pwl=_f(r["px_pwl"]),
        )
        out = core.step(b)

        if int(_f(r["px_exec"])) & 2:
            pine_trades += 1
        if out.px_exec & 2:
            port_trades += 1

        if i < args.warmup:
            continue
        compared += 1
        blk_hist[int(_f(r["px_blk_s"]))] += 1
        blk_hist[int(_f(r["px_blk_l"]))] += 1
        pine_exec = int(_f(r["px_exec"]))
        pine_state = int(_f(r["px_state"]))
        for bit, label in EXEC_FEATURES.items():
            if pine_exec & bit:
                feat_hist[label] += 1
        for bit, label in STATE_FEATURES.items():
            if pine_state & bit:
                feat_hist[label] += 1

        for col in EXACT:
            if not _same(_f(r[col]), float(getattr(out, col)), 0.0):
                mismatches.setdefault(col, []).append((i, r["time"], r[col], getattr(out, col)))
        for col in PRICE:
            if not _same(_f(r[col]), float(getattr(out, col)), cfg.tick_size * 1.5):
                mismatches.setdefault(col, []).append((i, r["time"], r[col], getattr(out, col)))
        for col in QTY:
            if not _same(_f(r[col]), float(getattr(out, col)), cfg.qty_step / 100):
                mismatches.setdefault(col, []).append((i, r["time"], r[col], getattr(out, col)))
        for col in SOFT:
            pine = _f(r[col])
            port = float(getattr(out, col))
            tol = max(abs(pine) * 1e-3, 1e-6) if pine == pine else 0.0
            if not _same(pine, port, tol):
                mismatches.setdefault(col, []).append((i, r["time"], r[col], getattr(out, col)))

    # ── the report ────────────────────────────────────────────────────────────────────
    print(f"export        {path.name}")
    print(f"bars          {len(rows)} read, {args.warmup} warm-up, {compared} COMPARED"
          + (f", {trimmed} blank live bar(s) trimmed" if trimmed else ""))
    print(f"window        {rows[0]['time']} -> {rows[-1]['time']} (unix seconds)")
    print("config        " + ", ".join(
        f"{k}={v}" for k, v in sorted(vars(cfg).items())
        if k not in ("tick_size", "initial_capital")))
    print(f"trades closed pine {pine_trades}, port {port_trades}")
    print("fed, not compared:")
    for k, why in FED.items():
        print(f"              {k:<16} {why}")
    print("block codes seen (pine, both sides, compared bars only):")
    for code, n in sorted(blk_hist.items()):
        mark = "  ⚠ NEVER FIRED" if n == 0 else ""
        print(f"              {code:>2} x{n:<7} {BLOCK_WHY.get(code, '?')}{mark}")
    print("features EXERCISED by this export (pine, compared bars only):")
    for label in list(EXEC_FEATURES.values()) + list(STATE_FEATURES.values()):
        n = feat_hist.get(label, 0)
        print(f"              x{n:<7} {label}" + ("   ⚠ NEVER RAN — a green gate says nothing about it" if n == 0 else ""))
    missing = [c for c in BLOCK_WHY if c not in blk_hist]
    if missing:
        print(f"              ⚠ never fired, so proven by nothing: {missing}")

    if not mismatches:
        print("\nPARITY GREEN — every compared column agrees on every compared bar.")
        print("⚠ Green about THIS export's config only, and silent about the fed streams above.")
        return 0

    print(f"\nPARITY RED — {len(mismatches)} column(s) disagree.")
    for col, hits in sorted(mismatches.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  {col}: {len(hits)} bar(s), first {args.max_report}:")
        for bar, t, pine, port in hits[:args.max_report]:
            print(f"    bar {bar:<6} t={t}  pine={pine!s:<14} port={port!s:<14}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
