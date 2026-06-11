"""
audit_mt5_data_quality.py

Audits the QUALITY of historical data your MT5 / PU Prime demo actually serves,
so you know whether you can backtest confidently at 15-minute and below.

This is a read-only companion to download_mt5_history.py. It downloads nothing
permanently and changes nothing — it asks the broker what it has and reports.

Run this ON THE VPS, against the dedicated lab MT5 install at C:\\MT5_Lab.

It answers four questions, per symbol, that decide low-timeframe testing confidence:
  1. TICKS  - does the broker serve real tick data, and how far back?
  2. BARS   - how deep is M1/M5/M15 bar history actually?
  3. SPREAD - what is the real bid/ask spread right now, in points and as a
              fraction of a typical scalp target?
  4. GAPS   - are there obvious holes in the recent low-timeframe series?

The single most important line in the output is the TICKS one. If real ticks
go back far enough, you can model fills honestly at low timeframes. If not,
M5/M15 backtests rely on MT5 inventing the price path inside each bar, which
flatters fast strategies — and Dukascopy tick data becomes the better source.

Usage:
    python audit_mt5_data_quality.py
    python audit_mt5_data_quality.py --symbols XAUUSD,EURUSD
    python audit_mt5_data_quality.py --tick-probe-days 365   # how far back to test ticks

Expects:
- MetaTrader5 package installed (pip install MetaTrader5)
- MT5 installed at C:\\MT5_Lab\\terminal64.exe
- MT5 logged into the demo account you'll actually backtest against
"""

import argparse
import sys
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Run: pip install MetaTrader5")
    sys.exit(1)


# ============================================================
# Configuration  (mirrors download_mt5_history.py)
# ============================================================

MT5_PATH = r"C:\MT5_Lab\terminal64.exe"

SYMBOLS = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "GBPJPY",
    "NAS100",
]

SUFFIX_CANDIDATES = ["", ".s", ".m", ".raw", "#", "."]

# Low-timeframe bars are where the data quality question actually bites.
BAR_TIMEFRAMES = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
}

# How far back to probe for tick availability, in days, oldest-first checkpoints.
# We test progressively older windows to find the real tick history edge.
DEFAULT_TICK_PROBE_CHECKPOINTS = [7, 30, 90, 180, 365, 730]

# A rough "typical scalp target" per instrument, in price terms, used only to
# express spread as a fraction of a trade's target. Conservative round numbers.
# (Spread / target) is the honest "how much of my edge does spread eat" number.
TYPICAL_TARGET = {
    "XAUUSD": 2.0,     # ~$2 move
    "XAGUSD": 0.05,
    "EURUSD": 0.0010,  # 10 pips
    "GBPUSD": 0.0010,
    "GBPJPY": 0.10,    # 10 pips (JPY pair)
    "USDJPY": 0.10,
    "NAS100": 10.0,    # 10 index points
}


# ============================================================
# Connection  (same pattern as download_mt5_history.py)
# ============================================================


def init_mt5():
    print(f"Connecting to MT5 at {MT5_PATH}...")
    if not mt5.initialize(path=MT5_PATH):
        print(f"ERROR: Failed to initialize MT5: {mt5.last_error()}")
        return False

    info = mt5.terminal_info()
    if info is None:
        print("ERROR: terminal_info() returned None - MT5 not properly connected")
        return False

    account = mt5.account_info()
    if account is None:
        print("ERROR: account_info() returned None - not logged into an account")
        print("Log into a demo account in MT5 first, then re-run.")
        return False

    print(f"  Connected. Terminal data path: {info.data_path}")
    print(f"  Account: #{account.login} ({account.server}) - {account.name}")
    print()
    return True


def resolve_symbol(symbol):
    for suffix in SUFFIX_CANDIDATES:
        candidate = symbol + suffix
        if mt5.symbol_info(candidate) is not None:
            return candidate
    return None


def ensure_visible(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    if not info.visible:
        mt5.symbol_select(symbol, True)
    return True


# ============================================================
# 1. TICKS — the question this whole audit exists to answer
# ============================================================


def audit_ticks(symbol, checkpoints):
    """
    Find how far back real ticks are actually served.
    Returns (deepest_days_with_ticks, detail_rows).
    Uses COPY_TICKS_ALL so we get real bid/ask ticks, not synthesized.
    """
    detail = []
    deepest = 0
    now = datetime.now()
    for days in checkpoints:
        # Probe a narrow 1-day window starting `days` ago. If ticks come back
        # there, the broker genuinely holds ticks at least that far.
        start = now - timedelta(days=days)
        end = start + timedelta(days=1)
        ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
        count = 0 if ticks is None else len(ticks)
        has = count > 0
        detail.append((days, count, has))
        if has:
            deepest = max(deepest, days)
    return deepest, detail


# ============================================================
# 2. BARS — actual depth at low timeframes
# ============================================================


def audit_bar_depth(symbol):
    """For each low timeframe, report the oldest bar actually available."""
    rows = []
    now = datetime.now()
    for tf_name, tf_const in BAR_TIMEFRAMES.items():
        # Ask for a very wide window; broker returns only what it has.
        rates = mt5.copy_rates_range(symbol, tf_const,
                                     now - timedelta(days=1100), now)
        if rates is None or len(rates) == 0:
            rows.append((tf_name, 0, None))
            continue
        oldest = datetime.fromtimestamp(rates[0]["time"])
        days_deep = (now - oldest).days
        rows.append((tf_name, len(rates), days_deep))
    return rows


# ============================================================
# 3. SPREAD — real, current bid/ask
# ============================================================


def audit_spread(symbol):
    """Report current spread in points and as a fraction of a typical target."""
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None or tick.bid == 0:
        return None
    spread_price = tick.ask - tick.bid
    point = info.point
    spread_points = spread_price / point if point else 0
    base = symbol
    for suf in SUFFIX_CANDIDATES:
        if symbol.endswith(suf) and suf:
            base = symbol[: -len(suf)]
            break
    target = TYPICAL_TARGET.get(base) or TYPICAL_TARGET.get(symbol)
    frac = (spread_price / target) if target else None
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "spread_price": spread_price,
        "spread_points": spread_points,
        "target": target,
        "frac_of_target": frac,
    }


# ============================================================
# 4. GAPS — obvious holes in recent low-tf data
# ============================================================


def audit_gaps(symbol):
    """
    Look at the most recent ~5 days of M5 bars and count gaps larger than
    a normal weekend/session break. Crude but catches missing-session holes.
    """
    now = datetime.now()
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5,
                                 now - timedelta(days=7), now)
    if rates is None or len(rates) < 10:
        return None
    times = [r["time"] for r in rates]
    # Expected step is 300s (5 min). Count intraday gaps > 1 hour that aren't
    # the weekend (weekend gap is legitimate; >1h midweek is suspect).
    suspicious = 0
    for i in range(1, len(times)):
        step = times[i] - times[i - 1]
        if step > 3600:  # more than an hour between consecutive 5-min bars
            dt = datetime.fromtimestamp(times[i - 1])
            # crude weekend check: Friday (4) gaps are expected
            if dt.weekday() != 4:
                suspicious += 1
    return {"bars": len(rates), "suspicious_gaps": suspicious}


# ============================================================
# Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="Audit MT5 data quality for low-timeframe testing")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbol list (default: a representative set)")
    parser.add_argument("--tick-probe-days", type=int, default=None,
                        help="Deepest tick checkpoint to test, in days (default up to 730)")
    args = parser.parse_args()

    target_symbols = ([s.strip() for s in args.symbols.split(",")]
                      if args.symbols else SYMBOLS)

    checkpoints = list(DEFAULT_TICK_PROBE_CHECKPOINTS)
    if args.tick_probe_days:
        checkpoints = [d for d in checkpoints if d <= args.tick_probe_days]
        if args.tick_probe_days not in checkpoints:
            checkpoints.append(args.tick_probe_days)
        checkpoints.sort()

    print("=" * 72)
    print("LWG Capital - MT5 Data QUALITY Audit (read-only)")
    print("=" * 72)
    print("  Question: can I backtest confidently at 15-minute and below?")
    print(f"  Symbols:  {len(target_symbols)}")
    print()

    if not init_mt5():
        sys.exit(1)

    resolved = {}
    for symbol in target_symbols:
        actual = resolve_symbol(symbol)
        if actual is None:
            print(f"  WARN  {symbol}: not found on this broker")
        else:
            ensure_visible(actual)
            resolved[symbol] = actual
    print()

    if not resolved:
        print("ERROR: No symbols resolved.")
        mt5.shutdown()
        sys.exit(1)

    for symbol, actual in resolved.items():
        print("-" * 72)
        print(f"SYMBOL: {actual}")
        print("-" * 72)

        # 1. TICKS — the headline
        deepest, tick_detail = audit_ticks(actual, checkpoints)
        print("  TICKS (real bid/ask history — the decisive one):")
        for days, count, has in tick_detail:
            mark = "yes" if has else "NO"
            print(f"      {days:>4}d ago: {count:>8} ticks in a 1-day probe   [{mark}]")
        if deepest == 0:
            print("      VERDICT: no real ticks served -> M5/M15 fills would be "
                  "INVENTED from bars. Dukascopy strongly advised.")
        elif deepest < 90:
            print(f"      VERDICT: ticks only ~{deepest}d back -> too shallow for "
                  "robust low-tf testing. Dukascopy advised for depth.")
        else:
            print(f"      VERDICT: real ticks at least ~{deepest}d back -> usable "
                  "for low-tf testing; validate spread below.")
        print()

        # 2. BARS
        print("  BAR DEPTH (how far low-tf history actually goes):")
        for tf_name, n, days_deep in audit_bar_depth(actual):
            if n == 0:
                print(f"      {tf_name:<4}: none")
            else:
                print(f"      {tf_name:<4}: {n:>8} bars, oldest ~{days_deep}d back")
        print()

        # 3. SPREAD
        sp = audit_spread(actual)
        print("  SPREAD (current, real bid/ask):")
        if sp is None:
            print("      could not read a live tick (market closed?) - re-run during session")
        else:
            print(f"      bid {sp['bid']}  ask {sp['ask']}  "
                  f"spread {sp['spread_price']:.5f} ({sp['spread_points']:.0f} points)")
            if sp["frac_of_target"] is not None:
                pct = sp["frac_of_target"] * 100
                flag = "  <- heavy: spread eats a big slice of each scalp" if pct > 25 else ""
                print(f"      vs a ~{sp['target']} typical target: "
                      f"spread = {pct:.0f}% of target{flag}")
        print()

        # 4. GAPS
        gaps = audit_gaps(actual)
        print("  GAPS (recent M5, last 7d):")
        if gaps is None:
            print("      not enough recent M5 data to check")
        else:
            note = "  clean" if gaps["suspicious_gaps"] == 0 else "  <- holes present"
            print(f"      {gaps['bars']} bars, {gaps['suspicious_gaps']} "
                  f"suspicious midweek gaps{note}")
        print()

    print("=" * 72)
    print("HOW TO READ THIS:")
    print("  - The TICKS verdict is the decision. Real ticks deep enough = you can")
    print("    test low timeframes on broker data. Shallow/none = use Dukascopy.")
    print("  - SPREAD as % of target tells you how much edge each scalp must overcome.")
    print("  - Whatever you use, still hold strategies to a pessimistic slippage buffer")
    print("    ON TOP of real spread before trusting a result.")
    print("=" * 72)

    mt5.shutdown()


if __name__ == "__main__":
    main()
