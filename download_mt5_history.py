"""
download_mt5_history.py

Downloads historical OHLC data for the LWG Capital lab into a specific MT5 instance.

Run this ON THE VPS, against the dedicated lab MT5 install at C:\\MT5_Lab.

Usage:
    python download_mt5_history.py
    python download_mt5_history.py --years 5         # change history depth
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
from pathlib import Path

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

# Symbols to download. Broker suffixes (e.g. ".s") may be applied automatically
# at runtime — see resolve_symbol() below.
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

# Timeframes needed by the lab:
# - H1 + H4 for forex regime classification (matches the bots)
# - D1 for daily-bar metrics if ever needed
TIMEFRAMES = {
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

# Default years of history to fetch
DEFAULT_YEARS_BACK = 3

# How many bars to expect per timeframe per year (rough estimates for verification)
EXPECTED_BARS_PER_YEAR = {
    "H1": 6000,    # ~24h * 252 trading days, less weekend gaps
    "H4": 1500,    # ~6 bars/day * 252 days
    "D1": 252,     # trading days per year
}

# Common broker suffixes to try if the bare symbol doesn't exist
SUFFIX_CANDIDATES = ["", ".s", ".m", ".raw", "#", "."]


# ============================================================
# Helpers
# ============================================================


def init_mt5() -> bool:
    """Initialize connection to the specific lab MT5 instance."""
    print(f"Connecting to MT5 at {MT5_PATH}...")
    if not mt5.initialize(path=MT5_PATH):
        print(f"ERROR: Failed to initialize MT5: {mt5.last_error()}")
        return False

    info = mt5.terminal_info()
    if info is None:
        print("ERROR: terminal_info() returned None — MT5 not properly connected")
        return False

    account = mt5.account_info()
    if account is None:
        print("ERROR: account_info() returned None — not logged into an account")
        print("Log into a demo account in MT5 first, then re-run.")
        return False

    print(f"  Connected. Terminal data path: {info.data_path}")
    print(f"  Account: #{account.login} ({account.server}) — {account.name}")
    print(f"  Balance: {account.balance} {account.currency}")
    print()
    return True


def resolve_symbol(symbol: str) -> str | None:
    """
    Try to find the actual symbol name on this broker.
    Returns the resolved name or None if not found.

    PU Prime uses .s suffix on most symbols (e.g. EURUSD.s).
    Other brokers use different conventions.
    """
    for suffix in SUFFIX_CANDIDATES:
        candidate = symbol + suffix
        info = mt5.symbol_info(candidate)
        if info is not None:
            return candidate
    return None


def ensure_symbol_in_market_watch(symbol: str) -> bool:
    """
    Make sure the symbol is visible in Market Watch.
    Required before MT5 will fetch history for it.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"  WARN: Could not add {symbol} to Market Watch")
            return False
    return True


def download_history(symbol: str, timeframe_name: str, timeframe_const: int, years_back: int) -> int:
    """
    Download history for one symbol/timeframe combination.
    Returns the number of bars actually fetched.
    """
    end = datetime.now()
    start = end - timedelta(days=years_back * 365)

    # copy_rates_range pulls the history into MT5's internal cache.
    # This is what Strategy Tester reads from later.
    rates = mt5.copy_rates_range(symbol, timeframe_const, start, end)

    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        print(f"  FAIL  {symbol} {timeframe_name}: no data returned. Error: {err}")
        return 0

    return len(rates)


def verify_history(symbol: str, timeframe_name: str, timeframe_const: int, years_back: int) -> tuple[bool, int]:
    """
    Check whether enough history exists for this symbol/timeframe.
    Returns (is_sufficient, bar_count).
    """
    end = datetime.now()
    start = end - timedelta(days=years_back * 365)

    rates = mt5.copy_rates_range(symbol, timeframe_const, start, end)
    if rates is None:
        return (False, 0)

    bar_count = len(rates)
    expected_minimum = EXPECTED_BARS_PER_YEAR[timeframe_name] * years_back * 0.7  # 70% threshold
    return (bar_count >= expected_minimum, bar_count)


# ============================================================
# Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="Download MT5 historical data for the LWG lab")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS_BACK,
                        help=f"Years of history to download (default: {DEFAULT_YEARS_BACK})")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbol list (default: all). Example: EURUSD,GBPUSD")
    parser.add_argument("--verify", action="store_true",
                        help="Verify existing data, do not re-download")
    args = parser.parse_args()

    # Filter symbol list
    if args.symbols:
        target_symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        target_symbols = SYMBOLS

    print("=" * 70)
    print("LWG Capital — MT5 Historical Data Download")
    print("=" * 70)
    print(f"  Mode:       {'VERIFY ONLY' if args.verify else 'DOWNLOAD'}")
    print(f"  Years back: {args.years}")
    print(f"  Symbols:    {len(target_symbols)}")
    print(f"  Timeframes: {', '.join(TIMEFRAMES.keys())}")
    print()

    if not init_mt5():
        sys.exit(1)

    # Step 1: resolve symbol names (handle broker suffixes)
    print("Resolving symbol names on this broker...")
    resolved = {}
    for symbol in target_symbols:
        actual = resolve_symbol(symbol)
        if actual is None:
            print(f"  WARN  {symbol}: not found on this broker (tried all suffix candidates)")
        else:
            resolved[symbol] = actual
            if actual != symbol:
                print(f"  OK    {symbol} → {actual}")
            else:
                print(f"  OK    {symbol}")
    print()

    if not resolved:
        print("ERROR: No symbols could be resolved on this broker. Check broker settings.")
        mt5.shutdown()
        sys.exit(1)

    # Step 2: ensure each symbol is in Market Watch
    print("Adding symbols to Market Watch...")
    for symbol, actual in resolved.items():
        if ensure_symbol_in_market_watch(actual):
            print(f"  OK    {actual}")
        else:
            print(f"  FAIL  {actual}")
    print()

    # Step 3: download (or verify) each symbol × timeframe
    print(f"{'Verifying' if args.verify else 'Downloading'} history...")
    print(f"  {'Symbol':<15} {'TF':<5} {'Bars':>10} {'Status':<15}")
    print(f"  {'-'*15} {'-'*5} {'-'*10} {'-'*15}")

    total_ops = 0
    successful = 0
    insufficient = []

    for symbol, actual in resolved.items():
        for tf_name, tf_const in TIMEFRAMES.items():
            total_ops += 1
            if args.verify:
                is_ok, bar_count = verify_history(actual, tf_name, tf_const, args.years)
                status = "SUFFICIENT" if is_ok else "INSUFFICIENT"
                print(f"  {actual:<15} {tf_name:<5} {bar_count:>10} {status:<15}")
                if is_ok:
                    successful += 1
                else:
                    insufficient.append((actual, tf_name, bar_count))
            else:
                bars = download_history(actual, tf_name, tf_const, args.years)
                status = "OK" if bars > 0 else "FAILED"
                print(f"  {actual:<15} {tf_name:<5} {bars:>10} {status:<15}")
                if bars > 0:
                    successful += 1
                # Small pause to be nice to the broker's data server
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
        print()
        print("Run without --verify to download them.")

    mt5.shutdown()

    if successful < total_ops:
        sys.exit(2)


if __name__ == "__main__":
    main()
