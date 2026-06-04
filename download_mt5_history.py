"""
download_mt5_history.py

Downloads historical OHLC data for the LWG Capital lab into a specific MT5 instance.

Run this ON THE VPS, against the dedicated lab MT5 install at C:\\MT5_Lab.

Per-timeframe windows are sized to what PU Prime demo actually serves:
  M5:  240 days  (broker limit ~270)
  M15: 720 days  (broker limit ~730)
  H1:  3 years
  H4:  3 years
  D1:  3 years

Usage:
    python download_mt5_history.py
    python download_mt5_history.py --symbols EURUSD,GBPUSD    # limit symbols
    python download_mt5_history.py --verify          # check existing data, don't re-download

Expects:
- MetaTrader5 package installed (pip install MetaTrader5)
- MT5 installed at C:\\MT5_Lab\\terminal64.exe
- MT5 logged into a demo account that has access to the listed symbols
"""

import argparse
import sys
import time
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Run: pip install MetaTrader5")
    sys.exit(1)


# ============================================================
# Configuration
# ============================================================

# Path to the dedicated lab MT5 install
MT5_PATH = r"C:\MT5_Lab\terminal64.exe"

# Symbols to download
SYMBOLS = [
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "GBPJPY",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "EURGBP",
    "NAS100",
]

# Per-timeframe configuration: (mt5_constant, days_back, label)
# Days are sized to what PU Prime demo serves with a small safety margin
TIMEFRAME_CONFIG = {
    "M5":  (mt5.TIMEFRAME_M5,  240),    # ~8 months (limit ~270d)
    "M15": (mt5.TIMEFRAME_M15, 720),    # ~2 years (limit ~730d)
    "H1":  (mt5.TIMEFRAME_H1,  1095),   # 3 years
    "H4":  (mt5.TIMEFRAME_H4,  1095),   # 3 years
    "D1":  (mt5.TIMEFRAME_D1,  1095),   # 3 years
}

# Rough expected bar counts (per the windows above) for verification
EXPECTED_BARS = {
    "M5":  240 * 288 * 0.7,    # 288 bars/24h, 70% threshold for weekend gaps
    "M15": 720 * 96 * 0.7,
    "H1":  1095 * 24 * 0.7,
    "H4":  1095 * 6 * 0.7,
    "D1":  1095 * 0.7,
}

# Common broker suffixes to try if the bare symbol doesn't exist
SUFFIX_CANDIDATES = ["", ".s", ".m", ".raw", "#", "."]


# ============================================================
# Helpers
# ============================================================


def init_mt5():
    """Initialize connection to the specific lab MT5 instance."""
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
    print(f"  Balance: {account.balance} {account.currency}")
    print()
    return True


def resolve_symbol(symbol):
    for suffix in SUFFIX_CANDIDATES:
        candidate = symbol + suffix
        info = mt5.symbol_info(candidate)
        if info is not None:
            return candidate
    return None


def ensure_symbol_in_market_watch(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"  WARN: Could not add {symbol} to Market Watch")
            return False
    return True


def download_history(symbol, timeframe_const, days_back):
    end = datetime.now()
    start = end - timedelta(days=days_back)
    rates = mt5.copy_rates_range(symbol, timeframe_const, start, end)

    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        return 0, err
    return len(rates), None


def verify_history(symbol, timeframe_const, days_back):
    end = datetime.now()
    start = end - timedelta(days=days_back)
    rates = mt5.copy_rates_range(symbol, timeframe_const, start, end)
    if rates is None:
        return (False, 0)
    return (True, len(rates))


# ============================================================
# Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="Download MT5 historical data for the LWG lab")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbol list (default: all). Example: EURUSD,GBPUSD")
    parser.add_argument("--verify", action="store_true",
                        help="Verify existing data, do not re-download")
    args = parser.parse_args()

    if args.symbols:
        target_symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        target_symbols = SYMBOLS

    print("=" * 70)
    print("LWG Capital - MT5 Historical Data Download")
    print("=" * 70)
    print(f"  Mode:     {'VERIFY ONLY' if args.verify else 'DOWNLOAD'}")
    print(f"  Symbols:  {len(target_symbols)}")
    print(f"  Windows:  M5={TIMEFRAME_CONFIG['M5'][1]}d, "
          f"M15={TIMEFRAME_CONFIG['M15'][1]}d, "
          f"H1={TIMEFRAME_CONFIG['H1'][1]}d, "
          f"H4={TIMEFRAME_CONFIG['H4'][1]}d, "
          f"D1={TIMEFRAME_CONFIG['D1'][1]}d")
    print()

    if not init_mt5():
        sys.exit(1)

    print("Resolving symbol names on this broker...")
    resolved = {}
    for symbol in target_symbols:
        actual = resolve_symbol(symbol)
        if actual is None:
            print(f"  WARN  {symbol}: not found")
        else:
            resolved[symbol] = actual
            print(f"  OK    {symbol}{' -> ' + actual if actual != symbol else ''}")
    print()

    if not resolved:
        print("ERROR: No symbols resolved on this broker.")
        mt5.shutdown()
        sys.exit(1)

    print("Adding symbols to Market Watch...")
    for symbol, actual in resolved.items():
        if ensure_symbol_in_market_watch(actual):
            print(f"  OK    {actual}")
        else:
            print(f"  FAIL  {actual}")
    print()

    print(f"{'Verifying' if args.verify else 'Downloading'} history...")
    print(f"  {'Symbol':<15} {'TF':<5} {'Days':>5} {'Bars':>10} {'Status':<15}")
    print(f"  {'-'*15} {'-'*5} {'-'*5} {'-'*10} {'-'*15}")

    total_ops = 0
    successful = 0
    insufficient = []

    for symbol, actual in resolved.items():
        for tf_name, (tf_const, days_back) in TIMEFRAME_CONFIG.items():
            total_ops += 1
            if args.verify:
                is_ok, bar_count = verify_history(actual, tf_const, days_back)
                expected = EXPECTED_BARS[tf_name]
                sufficient = is_ok and bar_count >= expected
                status = "SUFFICIENT" if sufficient else "INSUFFICIENT"
                print(f"  {actual:<15} {tf_name:<5} {days_back:>5} {bar_count:>10} {status:<15}")
                if sufficient:
                    successful += 1
                else:
                    insufficient.append((actual, tf_name, bar_count))
            else:
                bars, err = download_history(actual, tf_const, days_back)
                status = "OK" if bars > 0 else f"FAIL: {err}"
                print(f"  {actual:<15} {tf_name:<5} {days_back:>5} {bars:>10} {status}")
                if bars > 0:
                    successful += 1
                time.sleep(0.2)

    print()
    print("=" * 70)
    print(f"Result: {successful}/{total_ops} successful")
    print("=" * 70)

    if args.verify and insufficient:
        print()
        print("The following need a fresh download:")
        for actual, tf_name, bar_count in insufficient:
            print(f"  - {actual} {tf_name} (only {bar_count} bars)")

    mt5.shutdown()

    if successful < total_ops:
        sys.exit(2)


if __name__ == "__main__":
    main()
