"""
reporter.py — Daily Performance Reporter
Sends a Telegram message per bot at 4:00pm Texas time.

Covers:
  - Today's trades (W/L/BE), P&L, drawdown
  - Starting and ending balance, total growth
  - Last 30 trades: win rate, profit factor, avg R, Calmar
  - Bot uptime for the day
  - AI-driven suggestions based on performance patterns

Run via Task Scheduler daily at 4pm Texas time.
Install: pip install requests psutil

Usage:
    python reporter.py              # report all bots
    python reporter.py --bot bot1   # one bot only
    python reporter.py --test       # verify Telegram connection
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
TELEGRAM_CHAT  = "429207285"
ALGOS_ROOT     = Path("C:/algos")
TEXAS          = ZoneInfo("America/Chicago")

BOTS = {
    "smc_trend": {
        "name":      "Bot SMC Trend",
        "emoji":     "📈",
        "script":    "bot_smc_trend.py",
        "trades":    ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_trades.json",
        "daily":     ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_daily.json",
        "equity":    ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "log":       ALGOS_ROOT / "markets/fx/instances/gold_main/bot_smc_trend.log",
        "daily_cap": 10.0,
    },
    "mean_reversion": {
        "name":      "Bot Mean Reversion",
        "emoji":     "↩️",
        "script":    "bot_mean_reversion.py",
        "trades":    ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_trades.json",
        "daily":     ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_daily.json",
        "equity":    ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "log":       ALGOS_ROOT / "markets/fx/instances/gold_main/bot_mean_reversion.log",
        "daily_cap": 10.0,
    },
    "scalper": {
        "name":      "Bot Scalper",
        "emoji":     "⚡",
        "script":    "bot_scalper.py",
        "trades":    ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_trades.json",
        "daily":     ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_daily.json",
        "equity":    ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "log":       ALGOS_ROOT / "markets/fx/instances/gold_scalper/bot_scalper.log",
        "daily_cap": 8.0,
    },
    "fft": {
        "name":      "Bot FFT",
        "emoji":     "🎯",
        "script":    "bot_fft.py",
        "trades":    ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_trades.json",
        "daily":     ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_daily.json",
        "equity":    ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "log":       ALGOS_ROOT / "markets/fx/instances/gold_fft/bot_fft.log",
        "daily_cap": 5.0,
    },
}


# =============================================================================
# HELPERS
# =============================================================================

def load_json(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def send_telegram(message: str) -> bool:
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def is_bot_running(script_name: str) -> bool:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"name='python.exe'",
             "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script_name in result.stdout
    except Exception:
        return False


def get_bot_uptime(log_path: Path) -> str:
    """Read log to find when bot last started today."""
    if not log_path.exists():
        return "unknown"
    today = datetime.now(TEXAS).date().isoformat()
    start_time = None
    try:
        with open(log_path, errors="replace") as f:
            for line in f:
                if today[:10] not in line:
                    continue
                if ("STARTING" in line or
                        ("Balance" in line and "Risk" in line) or
                        ("Balance" in line and "AI:" in line)):
                    try:
                        ts = line.split("|")[0].strip()[:19]
                        start_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                        break  # First match only
                    except Exception:
                        continue
    except Exception:
        return "unknown"

    if not start_time:
        return "not started today"

    now_utc  = datetime.utcnow()
    delta    = now_utc - start_time
    hours    = int(delta.total_seconds() // 3600)
    minutes  = int((delta.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"


def get_today_trades(trades: list) -> list:
    today = datetime.now(TEXAS).date().isoformat()
    return [t for t in trades
            if t.get("closed_at") and t["closed_at"][:10] == today
            and t.get("outcome") in ("win", "loss", "breakeven")]


def get_today_daily(daily) -> dict:
    today = datetime.now(TEXAS).date().isoformat()
    records = daily if isinstance(daily, list) else []
    for r in reversed(records):
        if r.get("date") == today:
            return r
    return {}


def calc_metrics(trades: list) -> dict:
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "breakevens": 0,
                "win_rate": 0.0, "avg_r_win": 0.0, "avg_r_loss": 0.0,
                "profit_factor": 0.0, "avg_r": 0.0}
    wins  = [t for t in trades if t["outcome"] == "win"]
    losses= [t for t in trades if t["outcome"] == "loss"]
    bes   = [t for t in trades if t["outcome"] == "breakeven"]
    wr    = [t.get("r_multiple", 0) for t in wins]
    lr    = [abs(t.get("r_multiple", 0)) for t in losses]
    pf    = sum(wr) / sum(lr) if sum(lr) > 0 else 999.0
    avg_r = sum(t.get("r_multiple", 0) for t in trades) / len(trades)
    return {
        "total":         len(trades),
        "wins":          len(wins),
        "losses":        len(losses),
        "breakevens":    len(bes),
        "win_rate":      len(wins) / len(trades) * 100,
        "avg_r_win":     round(sum(wr)/len(wr), 2) if wr else 0.0,
        "avg_r_loss":    round(sum(lr)/len(lr), 2) if lr else 0.0,
        "profit_factor": round(pf, 2),
        "avg_r":         round(avg_r, 2),
    }


def calc_calmar(equity) -> float:
    records = equity if isinstance(equity, list) else []
    if len(records) < 2:
        return 0.0
    bals  = [e.get("balance", e.get("equity", 0)) for e in records]
    start = bals[0]
    end   = bals[-1]
    if start == 0:
        return 0.0
    ret   = (end - start) / start * 100
    peak  = bals[0]
    max_dd = 0.0
    for b in bals:
        peak   = max(peak, b)
        dd     = (peak - b) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
    if max_dd == 0:
        return 999.0
    days      = len(records)
    ann_ret   = ret * (365 / days) if days > 0 else ret
    return round(ann_ret / max_dd, 2)


def generate_suggestions(bot_key, today_m, all_m, daily_record, calmar) -> list:
    cfg = BOTS[bot_key]
    s   = []
    wr  = all_m["win_rate"]
    pf  = all_m["profit_factor"]
    dd  = daily_record.get("max_drawdown_pct", 0)
    max_open = daily_record.get("max_simultaneous_open", 0)

    if all_m["total"] >= 10:
        if wr < 40:
            s.append(f"Win rate {wr:.0f}% is low — raise confluence score or AI threshold.")
        elif wr > 70:
            s.append(f"Win rate {wr:.0f}% is strong — consider slightly increasing risk % to compound faster.")
        if pf < 1.3:
            s.append(f"Profit factor {pf:.2f} is weak — avg loss too large. Tighten SL or take profits sooner.")
        elif pf > 2.5:
            s.append(f"Profit factor {pf:.2f} is excellent. Strategy edge is working well.")

    if dd > cfg["daily_cap"] * 0.7:
        s.append(f"Max drawdown {dd:.1f}% is near the {cfg['daily_cap']:.0f}% cap. Consider reducing risk % on volatile days.")
    if max_open >= 5:
        s.append(f"{max_open} simultaneous positions today — high exposure. Consider capping concurrent trades.")
    if calmar > 0 and calmar < 2.0:
        s.append(f"Calmar {calmar:.2f} below 2.0 target. Focus on reducing drawdown — tighten trailing stops.")
    elif calmar >= 3.0:
        s.append(f"Calmar {calmar:.2f} above 3.0 — this can be safely leveraged when ready for live trading.")
    if today_m["total"] == 0:
        s.append("No trades today. Check if market conditions were unsuitable or entry criteria need loosening.")
    if today_m["total"] > 0 and today_m["wins"] == 0 and today_m["losses"] == 0:
        s.append("All trades ended at breakeven — TPs may be too far away for current volatility.")
    if not s:
        s.append("Performance healthy. No adjustments needed today.")
    return s


def format_report(bot_key: str) -> str:
    cfg          = BOTS[bot_key]
    trades       = load_json(cfg["trades"])
    daily        = load_json(cfg["daily"])
    equity       = load_json(cfg["equity"])
    today_trades = get_today_trades(trades)
    daily_rec    = get_today_daily(daily)
    recent       = [t for t in trades if t.get("outcome") in ("win","loss","breakeven")][-30:]
    today_m      = calc_metrics(today_trades)
    all_m        = calc_metrics(recent)
    calmar       = calc_calmar(equity)
    uptime       = get_bot_uptime(cfg["log"])
    running      = is_bot_running(cfg["script"])

    bals      = [e.get("balance", e.get("equity", 0))
                 for e in (equity if isinstance(equity, list) else [])]
    start_bal = bals[0]  if bals else 0
    end_bal   = bals[-1] if bals else 0
    growth    = ((end_bal - start_bal) / start_bal * 100) if start_bal else 0
    today_pnl = daily_rec.get("final_pnl_pct", 0)
    today_dd  = daily_rec.get("max_drawdown_pct", 0)
    today_usd = end_bal * (today_pnl / 100) if end_bal else 0

    perf_emoji = "🟢" if today_pnl > 2 else "🟡" if today_pnl > 0 else "⚪" if today_pnl == 0 else "🔴"
    status_str = "🟢 RUNNING" if running else "🔴 STOPPED"
    calmar_e   = "✅" if calmar >= 3.0 else "⚠️" if calmar >= 2.0 else "❌"
    now_tx     = datetime.now(TEXAS)

    lines = [
        f"{cfg['emoji']} *{cfg['name']}*",
        f"📅 {now_tx.strftime('%A %b %d %Y')} | {status_str} | ⏱ up {uptime}",
        f"",
        f"*── TODAY ──*",
        f"{perf_emoji} P\\&L: {today_pnl:+.2f}% (${today_usd:+.2f})",
        f"📊 Trades: {today_m['total']} "
        f"({today_m['wins']}W / {today_m['losses']}L / {today_m['breakevens']}BE)",
        f"📉 Max drawdown: {today_dd:.1f}%",
        f"",
        f"*── BALANCES ──*",
        f"Account start: ${start_bal:,.2f}",
        f"Current:       ${end_bal:,.2f}",
        f"Total growth:  {growth:+.1f}%",
        f"",
        f"*── LAST 30 TRADES ──*",
        f"Win rate: {all_m['win_rate']:.0f}% | PF: {all_m['profit_factor']:.2f}",
        f"Avg win: +{all_m['avg_r_win']:.2f}R | Avg loss: \\-{all_m['avg_r_loss']:.2f}R",
        f"Calmar: {calmar:.2f} {calmar_e}",
        f"",
        f"*── SUGGESTIONS ──*",
    ]
    for i, s in enumerate(generate_suggestions(bot_key, today_m, all_m, daily_rec, calmar), 1):
        lines.append(f"{i}\\. {s}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot",   help="smc_trend/mean_reversion/scalper/fft")
    parser.add_argument("--test",  action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Send report even on weekends")
    args = parser.parse_args()

    # Skip reports on weekends — gold markets are closed
    # Use --force to override (e.g. from /report telegram command)
    now_tx     = datetime.now(TEXAS)
    is_weekend = now_tx.weekday() >= 5  # 5=Saturday, 6=Sunday
    if is_weekend and not args.test and not args.force:
        print(f"Weekend — markets closed. No report sent ({now_tx.strftime('%A')})")
        send_telegram(
            f"📊 Weekend report skipped — gold markets are closed\\.\n"
            f"Send /report to request one anyway\\."
        )
        return

    if args.test:
        ok = send_telegram(
            "✅ *LWG Capital Reporter*\n"
            "Connection confirmed\\. Daily reports at 4pm Texas time\\."
        )
        print("Test OK" if ok else "Test FAILED")
        return

    targets = [args.bot] if args.bot and args.bot in BOTS else list(BOTS.keys())

    now_tx = datetime.now(TEXAS)
    send_telegram(
        f"📊 *LWG Capital — Daily Summary*\n"
        f"📅 {now_tx.strftime('%A %b %d %Y — %I:%M %p CT')}"
    )
    for bot_key in targets:
        if bot_key not in BOTS:
            continue
        if not BOTS[bot_key]["trades"].exists() and not BOTS[bot_key]["log"].exists():
            continue
        msg = format_report(bot_key)
        send_telegram(msg)
        print(f"Sent {BOTS[bot_key]['name']}")


if __name__ == "__main__":
    main()
