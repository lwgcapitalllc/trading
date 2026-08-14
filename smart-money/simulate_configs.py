#!/usr/bin/env python3
"""
simulate_configs.py — Config grid search against cached DB trades.

Requalifies every wallet in the trades table under hundreds of config
combinations to find which parameter set yields the most qualified traders.

No API calls. Reads data/smart_money.db only.
Typically completes in 5–15 seconds.

Usage:
    python simulate_configs.py                        # default grid, top 40 results
    python simulate_configs.py --min-qualify 10       # show configs with ≥N qualifiers
    python simulate_configs.py --detail               # show wallets passing best config
    python simulate_configs.py --export               # write reports/sim_results.json + .csv
    python simulate_configs.py --apply-best           # patch config.json with best config

The script also prints a "funnel breakdown" for the best config so you can
see exactly which filter is cutting the most candidates.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "smart_money.db"
CONFIG_PATH = Path(__file__).parent / "config" / "config.json"
BOT_CFG_PATH = Path(__file__).parent / "config" / "templates" / "bot.json"
REPORTS_DIR = Path(__file__).parent / "reports"


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────


def load_wallet_trades() -> dict[str, list[dict]]:
    """Load all trades from DB, grouped by wallet address."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT w.address, t.close_ts, t.pnl, t.is_win, t.instrument,
               t.hold_time_seconds
        FROM trades t
        JOIN wallets w ON w.id = t.wallet_id
        ORDER BY t.wallet_id, t.close_ts ASC
    """).fetchall()
    conn.close()

    by_wallet: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_wallet[r["address"]].append(dict(r))
    return dict(by_wallet)


# ─────────────────────────────────────────────────────────────────────────────
# Pre-compute per-wallet stats (done once; grid search reuses these)
# ─────────────────────────────────────────────────────────────────────────────


def _build_monthly_windows(trades: list[dict], window_days: int = 30) -> list[dict]:
    """Non-overlapping windows anchored from oldest trade."""
    window_ms = window_days * 86_400 * 1_000
    ws = trades[0]["close_ts"]
    windows = []
    while ws <= trades[-1]["close_ts"]:
        we = ws + window_ms
        bucket = [t for t in trades if ws <= t["close_ts"] < we]
        if bucket:
            wins = sum(1 for t in bucket if t["is_win"])
            week_set = {
                datetime.fromtimestamp(t["close_ts"] / 1000, tz=timezone.utc).isocalendar()[:2]
                for t in bucket
            }
            windows.append(
                {
                    "wr": wins / len(bucket),
                    "tc": len(bucket),
                    "active_weeks": len(week_set),
                }
            )
        ws = we
    return windows


def precompute(trades: list[dict], now_ms: int) -> dict:
    """
    Compute every metric a config filter could need, once.
    Returned dict is used directly in apply_config().
    """
    tc = len(trades)
    wins = sum(1 for t in trades if t["is_win"])
    overall_wr = wins / tc if tc > 0 else 0.0

    oldest_ts = trades[0]["close_ts"]
    newest_ts = trades[-1]["close_ts"]
    span_days = (newest_ts - oldest_ts) / 86_400_000
    days_inactive = (now_ms - newest_ts) / 86_400_000

    total_pnl = sum(t["pnl"] for t in trades)

    # Monthly windows (30-day buckets)
    windows = _build_monthly_windows(trades)

    # Peak drawdown over full period
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cum += t["pnl"]
        if cum > peak:
            peak = cum
        if peak > 0:
            dd = (peak - cum) / peak
            if dd > max_dd:
                max_dd = dd

    # Single-trade PnL concentration
    total_abs = sum(abs(t["pnl"]) for t in trades)
    worst_share = max(abs(t["pnl"]) for t in trades) / total_abs if total_abs > 0 else 0.0

    # Average hold time
    with_hold = [t for t in trades if t.get("hold_time_seconds") is not None]
    avg_hold_hours = (
        sum(t["hold_time_seconds"] for t in with_hold) / len(with_hold) / 3600 if with_hold else 0.0
    )

    # Instrument diversity
    pnl_by_inst: dict[str, float] = defaultdict(float)
    for t in trades:
        pnl_by_inst[t["instrument"]] += t["pnl"]
    n_instruments = len(pnl_by_inst)
    total_pos_pnl = sum(v for v in pnl_by_inst.values() if v > 0)
    top_inst_conc = (
        max(pnl_by_inst.values()) / total_pos_pnl if total_pos_pnl > 0 and pnl_by_inst else 0.0
    )

    return {
        "trade_count": tc,
        "overall_wr": overall_wr,
        "span_days": span_days,
        "days_inactive": days_inactive,
        "total_pnl": total_pnl,
        "windows": windows,
        "peak_dd": max_dd,
        "worst_trade_share": worst_share,
        "avg_hold_hours": avg_hold_hours,
        "n_instruments": n_instruments,
        "top_inst_conc": top_inst_conc,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Filter application
# ─────────────────────────────────────────────────────────────────────────────

FILTER_NAMES = [
    "trade_count",
    "span",
    "recency",
    "net_profit",
    "overall_wr",
    "strike",
    "drawdown",
    "trade_conc",
    "hold_time",
    "instruments",
]


def apply_config(s: dict, cfg: dict) -> tuple[bool, str | None]:
    """
    Apply a config dict to pre-computed wallet stats `s`.
    Returns (qualifies, fail_stage).
    fail_stage is one of FILTER_NAMES or None.
    """
    if s["trade_count"] < cfg["min_trades"]:
        return False, "trade_count"
    if s["span_days"] < cfg["min_span_days"]:
        return False, "span"
    if cfg["max_inactive_days"] > 0 and s["days_inactive"] > cfg["max_inactive_days"]:
        return False, "recency"
    if s["total_pnl"] <= 0:
        return False, "net_profit"
    if s["overall_wr"] < cfg["min_overall_wr"]:
        return False, "overall_wr"

    # Per-window strike system
    consec_below = 0
    consec_above = 0
    disqualified = False
    for w in s["windows"]:
        if w["wr"] >= cfg["min_window_wr"]:
            consec_below = 0
            consec_above += 1
            if disqualified and consec_above >= 2:
                disqualified = False
        else:
            consec_above = 0
            consec_below += 1
            if consec_below >= cfg["consec_disq"]:
                disqualified = True
    if disqualified:
        return False, "strike"

    if s["peak_dd"] > cfg["max_drawdown"]:
        return False, "drawdown"
    if s["worst_trade_share"] > cfg["max_trade_conc"]:
        return False, "trade_conc"
    if s["avg_hold_hours"] > cfg["max_hold_hours"]:
        return False, "hold_time"
    if s["n_instruments"] < cfg["min_instruments"]:
        return False, "instruments"

    return True, None


# ─────────────────────────────────────────────────────────────────────────────
# Grid definition
# ─────────────────────────────────────────────────────────────────────────────


def build_grid(profile: str = "default") -> list[dict]:
    """
    Generate all config combinations to test.

    profile="default"  — standard human/mixed grid (3,780 combos)
      Fixed: max_hold_hours=72, max_trade_conc=0.40, min_instruments=1
      Varied: min_window_wr, min_overall_wr, max_inactive_days,
              min_span_days, min_trades, max_drawdown

    profile="bot"      — bot/algo-specific grid (~8,640 combos)
      Adds variation of max_hold_hours (key bot differentiator) and
      max_trade_conc (specialist single-instrument bots).
      Uses tighter recency and shorter span ranges for sprint traders.
    """
    if profile == "bot":
        return _build_bot_grid()

    min_window_wrs = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    min_overall_wrs = [0.30, 0.40, 0.50, 0.55, 0.60]
    max_inactive_days_options = [0, 30, 60, 90, 180, 365]
    min_span_days_options = [30, 60, 90]
    min_trades_options = [50, 100]
    max_drawdowns = [0.20, 0.30, 0.50]

    configs = []
    for mwr, mowr, mid, msd, mt, mdd in product(
        min_window_wrs,
        min_overall_wrs,
        max_inactive_days_options,
        min_span_days_options,
        min_trades_options,
        max_drawdowns,
    ):
        configs.append(
            {
                "min_window_wr": mwr,
                "min_overall_wr": mowr,
                "max_inactive_days": mid,
                "min_span_days": msd,
                "min_trades": mt,
                "max_drawdown": mdd,
                "max_trade_conc": 0.40,
                "max_hold_hours": 72,
                "min_instruments": 1,
                "consec_disq": 2,
            }
        )
    return configs


def _build_bot_grid() -> list[dict]:
    """
    Bot-specific grid. Key additions vs default:
      - max_hold_hours varied: [4, 12, 24, 48, 72] — the primary bot differentiator
      - max_trade_conc varied: [0.40, 1.0] — specialist single-instrument bots
      - min_span_days tighter: [14, 21, 30, 45, 60] — sprint traders
      - max_inactive_days tighter: [0, 14, 21, 30, 45] — must be currently running
      - max_drawdown wider range: [0.20, 0.30, 0.40, 0.50]
    Total: 5×3×5×5×2×4×5×2 = 15,000 combos (~10s runtime)
    """
    min_window_wrs = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    min_overall_wrs = [0.30, 0.40, 0.50]
    max_inactive_days_options = [0, 14, 21, 30, 45]
    min_span_days_options = [14, 21, 30, 45, 60]
    min_trades_options = [50, 100]
    max_drawdowns = [0.20, 0.30, 0.40, 0.50]
    max_hold_hours_options = [4, 12, 24, 48, 72]
    max_trade_conc_options = [0.40, 1.0]

    configs = []
    for mwr, mowr, mid, msd, mt, mdd, mhh, mtc in product(
        min_window_wrs,
        min_overall_wrs,
        max_inactive_days_options,
        min_span_days_options,
        min_trades_options,
        max_drawdowns,
        max_hold_hours_options,
        max_trade_conc_options,
    ):
        configs.append(
            {
                "min_window_wr": mwr,
                "min_overall_wr": mowr,
                "max_inactive_days": mid,
                "min_span_days": msd,
                "min_trades": mt,
                "max_drawdown": mdd,
                "max_hold_hours": mhh,
                "max_trade_conc": mtc,
                "min_instruments": 1,
                "consec_disq": 2,
            }
        )
    return configs


# ─────────────────────────────────────────────────────────────────────────────
# Grid runner
# ─────────────────────────────────────────────────────────────────────────────


def run_grid(wallet_stats: dict[str, dict], configs: list[dict]) -> list[dict]:
    """
    Run every config over every wallet. Returns list of result dicts sorted
    by (qualifier_count DESC, min_window_wr DESC).
    """
    results = []
    for cfg in configs:
        qualified = []
        fail_counts: dict[str, int] = defaultdict(int)

        for addr, s in wallet_stats.items():
            ok, stage = apply_config(s, cfg)
            if ok:
                qualified.append(addr)
            else:
                fail_counts[stage] += 1

        results.append(
            {
                "qualified": len(qualified),
                "qualified_addrs": qualified,
                "fail_counts": dict(fail_counts),
                "cfg": cfg,
            }
        )

    results.sort(key=lambda r: (-r["qualified"], -r["cfg"]["min_window_wr"]))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def _fmt_days(v: int) -> str:
    return "off" if v == 0 else f"{v}d"


def print_table(
    results: list[dict], top_n: int = 40, min_qualify: int = 0, profile: str = "default"
):
    """Print a ranked table of the top configs."""
    filtered = [r for r in results if r["qualified"] >= min_qualify]
    filtered = filtered[:top_n]

    if not filtered:
        print(f"\n  No configs produced ≥{min_qualify} qualified traders.")
        return

    is_bot = profile == "bot"
    hold_col = f"{'Hold':>5}  " if is_bot else ""
    conc_col = f"{'TrdConc':>7}  " if is_bot else ""
    header = (
        f"{'Rank':>4}  {'Q':>4}  "
        f"{'WinWR':>6}  {'OvrWR':>6}  {'Inact':>5}  "
        f"{'Span':>5}  {'Trades':>6}  {'MaxDD':>5}  "
        f"{hold_col}{conc_col}"
        f"  Fail (recency|span|strike|wr|dd|hold|other)"
    )
    print(f"\n{header}")
    print("─" * len(header))

    for rank, r in enumerate(filtered, 1):
        c = r["cfg"]
        fc = r["fail_counts"]
        fail_str = (
            f"recency={fc.get('recency', 0)}"
            f" span={fc.get('span', 0)}"
            f" strike={fc.get('strike', 0)}"
            f" wr={fc.get('overall_wr', 0)}"
            f" dd={fc.get('drawdown', 0)}"
            f" hold={fc.get('hold_time', 0)}"
            f" net={fc.get('net_profit', 0)}"
            f" tc={fc.get('trade_count', 0)}"
        )
        hold_val = f"{c['max_hold_hours']:>3}h   " if is_bot else ""
        conc_val = (
            f"{'off':>7}  "
            if c.get("max_trade_conc", 0) >= 1.0
            else f"{_fmt_pct(c.get('max_trade_conc', 0.4)):>7}  "
        )
        conc_str = conc_val if is_bot else ""
        print(
            f"{rank:>4}  {r['qualified']:>4}  "
            f"{_fmt_pct(c['min_window_wr']):>6}  "
            f"{_fmt_pct(c['min_overall_wr']):>6}  "
            f"{_fmt_days(c['max_inactive_days']):>5}  "
            f"{c['min_span_days']:>4}d  "
            f"{c['min_trades']:>5}+  "
            f"{_fmt_pct(c['max_drawdown']):>5}  "
            f"{hold_val}{conc_str}"
            f"  {fail_str}"
        )


def print_detail(result: dict, wallet_stats: dict[str, dict]):
    """Print details for each wallet that qualified under the given config."""
    cfg = result["cfg"]
    addrs = result["qualified_addrs"]
    if not addrs:
        print("\n  No wallets qualified.")
        return

    print(f"\n{'─' * 72}")
    print(f"  Detail for best config — {len(addrs)} qualifiers")
    print(
        f"  Config: min_window_wr={_fmt_pct(cfg['min_window_wr'])}  "
        f"min_overall_wr={_fmt_pct(cfg['min_overall_wr'])}  "
        f"max_inactive={_fmt_days(cfg['max_inactive_days'])}  "
        f"span>={cfg['min_span_days']}d  "
        f"trades>={cfg['min_trades']}  "
        f"max_dd={_fmt_pct(cfg['max_drawdown'])}"
    )
    print(f"{'─' * 72}")
    print(
        f"  {'Address':>14}  {'Trades':>6}  {'OvrWR':>6}  "
        f"{'Span':>6}  {'Inactive':>8}  {'PnL':>10}  {'MaxDD':>6}  Windows"
    )

    for addr in sorted(addrs, key=lambda a: -wallet_stats[a]["overall_wr"]):
        s = wallet_stats[addr]
        win_rates = [f"{w['wr']:.0%}" for w in s["windows"]]
        print(
            f"  {addr[:12]}…  "
            f"{s['trade_count']:>6}  "
            f"{s['overall_wr']:>6.1%}  "
            f"{s['span_days']:>5.0f}d  "
            f"{s['days_inactive']:>7.0f}d  "
            f"${s['total_pnl']:>9,.0f}  "
            f"{s['peak_dd']:>5.1%}  "
            f"[{', '.join(win_rates)}]"
        )


def export_results(results: list[dict], top_n: int = 100):
    """Export top configs to reports/sim_results.json and .csv."""
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = REPORTS_DIR / f"sim_results_{ts}.json"
    export_data = []
    for r in results[:top_n]:
        export_data.append(
            {
                "qualified": r["qualified"],
                "config": r["cfg"],
                "fail_counts": r["fail_counts"],
            }
        )
    json_path.write_text(json.dumps(export_data, indent=2))
    print(f"\n  JSON → {json_path}")

    # CSV
    csv_path = REPORTS_DIR / f"sim_results_{ts}.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "qualified",
                "min_window_wr",
                "min_overall_wr",
                "max_inactive_days",
                "min_span_days",
                "min_trades",
                "max_drawdown",
                "fail_trade_count",
                "fail_span",
                "fail_recency",
                "fail_net_profit",
                "fail_overall_wr",
                "fail_strike",
                "fail_drawdown",
                "fail_trade_conc",
                "fail_hold_time",
            ],
        )
        writer.writeheader()
        for rank, r in enumerate(results[:top_n], 1):
            c = r["cfg"]
            fc = r["fail_counts"]
            writer.writerow(
                {
                    "rank": rank,
                    "qualified": r["qualified"],
                    "min_window_wr": c["min_window_wr"],
                    "min_overall_wr": c["min_overall_wr"],
                    "max_inactive_days": c["max_inactive_days"],
                    "min_span_days": c["min_span_days"],
                    "min_trades": c["min_trades"],
                    "max_drawdown": c["max_drawdown"],
                    "fail_trade_count": fc.get("trade_count", 0),
                    "fail_span": fc.get("span", 0),
                    "fail_recency": fc.get("recency", 0),
                    "fail_net_profit": fc.get("net_profit", 0),
                    "fail_overall_wr": fc.get("overall_wr", 0),
                    "fail_strike": fc.get("strike", 0),
                    "fail_drawdown": fc.get("drawdown", 0),
                    "fail_trade_conc": fc.get("trade_conc", 0),
                    "fail_hold_time": fc.get("hold_time", 0),
                }
            )
    print(f"  CSV  → {csv_path}")


def patch_config(best_cfg: dict, profile: str = "default"):
    """Apply the best config's parameters back to the appropriate config file."""
    target = BOT_CFG_PATH if profile == "bot" else CONFIG_PATH
    with target.open() as f:
        cfg = json.load(f)

    cfg["qualification"]["min_win_rate"] = best_cfg["min_window_wr"]
    cfg["qualification"]["min_overall_win_rate"] = best_cfg["min_overall_wr"]
    cfg["qualification"]["max_inactive_days"] = best_cfg["max_inactive_days"]
    cfg["qualification"]["min_trades"] = best_cfg["min_trades"]
    cfg["qualification"]["max_drawdown"] = best_cfg["max_drawdown"]
    cfg["lookback"]["minimum_days"] = best_cfg["min_span_days"]
    if profile == "bot":
        cfg["qualification"]["max_avg_hold_hours"] = best_cfg["max_hold_hours"]
        cfg["qualification"]["max_single_trade_pnl_share"] = best_cfg["max_trade_conc"]

    with target.open("w") as f:
        json.dump(cfg, f, indent=2)
    print(f"\n  ✓ Patched {target}")


# ─────────────────────────────────────────────────────────────────────────────
# Funnel breakdown for a single config
# ─────────────────────────────────────────────────────────────────────────────


def print_funnel(cfg: dict, wallet_stats: dict[str, dict]):
    """
    Show a step-by-step funnel for a given config — how many wallets survive
    each filter in sequence.
    """
    filters_seq = [
        ("min_trades", lambda s: s["trade_count"] >= cfg["min_trades"]),
        ("min_span", lambda s: s["span_days"] >= cfg["min_span_days"]),
        (
            "recency",
            lambda s: (
                cfg["max_inactive_days"] == 0 or s["days_inactive"] <= cfg["max_inactive_days"]
            ),
        ),
        ("net_profit", lambda s: s["total_pnl"] > 0),
        ("overall_wr", lambda s: s["overall_wr"] >= cfg["min_overall_wr"]),
        (
            "strike_sys",
            lambda s: not _strike_disq(s["windows"], cfg["min_window_wr"], cfg["consec_disq"]),
        ),
        ("drawdown", lambda s: s["peak_dd"] <= cfg["max_drawdown"]),
        ("trade_conc", lambda s: s["worst_trade_share"] <= cfg["max_trade_conc"]),
        ("hold_time", lambda s: s["avg_hold_hours"] <= cfg["max_hold_hours"]),
        ("instruments", lambda s: s["n_instruments"] >= cfg["min_instruments"]),
    ]

    pool = list(wallet_stats.values())
    total = len(pool)
    print(f"\n  Funnel for best config (starts: {total} wallets)")
    print(f"  {'Filter':<16}  {'Remaining':>10}  {'Removed':>8}  {'Drop%':>6}")
    print(f"  {'─' * 16}  {'─' * 10}  {'─' * 8}  {'─' * 6}")

    for label, fn in filters_seq:
        before = len(pool)
        pool = [s for s in pool if fn(s)]
        after = len(pool)
        removed = before - after
        pct = removed / total * 100 if total > 0 else 0
        print(f"  {label:<16}  {after:>10,}  {removed:>8,}  {pct:>5.1f}%")


def _strike_disq(windows: list[dict], min_wr: float, consec_disq: int) -> bool:
    """Return True if the strike system disqualifies this wallet."""
    consec_below = 0
    consec_above = 0
    disqualified = False
    for w in windows:
        if w["wr"] >= min_wr:
            consec_below = 0
            consec_above += 1
            if disqualified and consec_above >= 2:
                disqualified = False
        else:
            consec_above = 0
            consec_below += 1
            if consec_below >= consec_disq:
                disqualified = True
    return disqualified


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Config grid simulation")
    parser.add_argument(
        "--profile",
        choices=["default", "bot"],
        default="default",
        help="Grid profile: 'default' (human/mixed) or 'bot' (algo/sprint traders). "
        "Bot grid also varies max_hold_hours and max_trade_conc.",
    )
    parser.add_argument(
        "--min-qualify", type=int, default=0, help="Only show configs with ≥N qualified wallets"
    )
    parser.add_argument(
        "--top-n", type=int, default=40, help="Number of top configs to display (default 40)"
    )
    parser.add_argument(
        "--detail", action="store_true", help="Show individual wallets passing the best config"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write top 100 configs to reports/sim_results.{json,csv}",
    )
    parser.add_argument(
        "--apply-best",
        action="store_true",
        help="Patch the appropriate config file with the best config found "
        "(config.json for default, bot.json for --profile bot)",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}")
        print("  Run a full pipeline scan first: python run_stage1.py")
        sys.exit(1)

    # ── Load & pre-compute ──────────────────────────────────────────────────
    print("Loading trades from DB…", end=" ", flush=True)
    t0 = time.time()
    wallet_trades = load_wallet_trades()
    now_ms = int(time.time() * 1000)

    wallet_stats: dict[str, dict] = {}
    for addr, trades in wallet_trades.items():
        if not trades:
            continue
        trades_sorted = sorted(trades, key=lambda t: t["close_ts"])
        wallet_stats[addr] = precompute(trades_sorted, now_ms)

    print(f"{len(wallet_stats)} wallets loaded in {time.time() - t0:.1f}s")

    # ── Build grid ──────────────────────────────────────────────────────────
    grid = build_grid(profile=args.profile)
    profile_label = f"[{args.profile} profile]"
    print(f"Running {len(grid):,} config combinations… {profile_label}", end=" ", flush=True)
    t1 = time.time()
    results = run_grid(wallet_stats, grid)
    print(f"done in {time.time() - t1:.1f}s")

    # ── Best config summary ─────────────────────────────────────────────────
    best = results[0]
    bc = best["cfg"]
    print(f"\n{'═' * 72}")
    print(f"  BEST CONFIG [{args.profile}] → {best['qualified']} qualified traders")
    hold_str = f"  max_hold={bc['max_hold_hours']}h" if args.profile == "bot" else ""
    conc_str = (
        f"  max_conc={'off' if bc.get('max_trade_conc', 0) >= 1 else _fmt_pct(bc.get('max_trade_conc', 0.4))}"
        if args.profile == "bot"
        else ""
    )
    print(
        f"  min_window_wr={_fmt_pct(bc['min_window_wr'])}  "
        f"min_overall_wr={_fmt_pct(bc['min_overall_wr'])}  "
        f"max_inactive={_fmt_days(bc['max_inactive_days'])}  "
        f"span>={bc['min_span_days']}d  "
        f"trades>={bc['min_trades']}  "
        f"max_dd={_fmt_pct(bc['max_drawdown'])}"
        f"{hold_str}{conc_str}"
    )
    print(f"{'═' * 72}")

    # Funnel for best config
    print_funnel(bc, wallet_stats)

    # ── Top configs table ───────────────────────────────────────────────────
    print_table(results, top_n=args.top_n, min_qualify=args.min_qualify, profile=args.profile)

    # ── Current config comparison ───────────────────────────────────────────
    ref_path = BOT_CFG_PATH if args.profile == "bot" else CONFIG_PATH
    with ref_path.open() as f:
        current_cfg = json.load(f)
    q = current_cfg["qualification"]
    current = {
        "min_window_wr": q["min_win_rate"],
        "min_overall_wr": q.get("min_overall_win_rate", 0.0),
        "max_inactive_days": q.get("max_inactive_days", 0),
        "min_span_days": current_cfg["lookback"]["minimum_days"],
        "min_trades": q["min_trades"],
        "max_drawdown": q["max_drawdown"],
        "max_trade_conc": q["max_single_trade_pnl_share"],
        "max_hold_hours": q["max_avg_hold_hours"],
        "min_instruments": q.get("min_instruments", 1),
        "consec_disq": current_cfg["strike_system"]["disqualify_consecutive_months"],
    }
    ok_count = sum(1 for _, s in wallet_stats.items() if apply_config(s, current)[0])
    print(f"\n  Current {ref_path.name} → {ok_count} qualified traders")

    # ── Optional detail ─────────────────────────────────────────────────────
    if args.detail:
        print_detail(best, wallet_stats)

    # ── Optional export ─────────────────────────────────────────────────────
    if args.export:
        export_results(results, top_n=100)

    # ── Optional patch ──────────────────────────────────────────────────────
    if args.apply_best:
        target_name = "bot.json" if args.profile == "bot" else "config.json"
        print(f"\n  Apply best config to {target_name}? [y/N] ", end="")
        ans = input().strip().lower()
        if ans == "y":
            patch_config(bc, profile=args.profile)
        else:
            print("  Skipped.")

    print()


if __name__ == "__main__":
    main()
