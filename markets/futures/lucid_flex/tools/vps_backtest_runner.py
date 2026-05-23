"""
Automates NinjaTrader 8 Strategy Analyzer to run all backtest combos.

Run this script ON THE VPS (via SSH or RDP terminal), not on Mac.

Prerequisites on VPS:
    pip install pywinauto comtypes

Usage:
    python vps_backtest_runner.py [--config path/to/backtest_config.json]

The script:
  1. Connects to the running NT8 instance
  2. For each combo in config: sets all fields, clicks Run, waits for completion
  3. Results are written to lucid_flex_results.csv by the strategy's Terminated handler

NOTE: NT8 must already be open with the Strategy Analyzer visible.
      Open it via: New -> Strategy Analyzer in NT8 Control Center.
"""

import sys
import os
import json
import time
import argparse

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("ERROR: pywinauto not installed.")
    print("  Run: pip install pywinauto comtypes")
    sys.exit(1)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(SCRIPT_DIR, "backtest_config.json")
RUN_TIMEOUT = 600


def load_config(path):
    with open(path) as f:
        return json.load(f)


def connect_nt8():
    """Connect to the running NT8 process."""
    print("Connecting to NinjaTrader 8...")
    attempts = [
        ("process name", {"path": "NinjaTrader.exe"}),
        ("title NT8",    {"title_re": ".*NinjaTrader.*"}),
        ("title SA",     {"title_re": ".*Strategy Analyzer.*"}),
    ]
    for label, kwargs in attempts:
        try:
            app = Application(backend="uia").connect(timeout=20, **kwargs)
            print(f"  Connected (via {label}).")
            return app
        except Exception:
            continue
    print("  ERROR: Could not connect to NT8.")
    print("  Make sure NinjaTrader 8 is running and Strategy Analyzer is open.")
    sys.exit(1)


def find_strategy_analyzer(app):
    """Locate the Strategy Analyzer window / panel."""
    try:
        sa = Desktop(backend="uia").window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        print("  Strategy Analyzer found.")
        return sa
    except Exception:
        pass
    try:
        sa = app.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        print("  Strategy Analyzer found (via app).")
        return sa
    except Exception as e:
        print(f"  ERROR: Strategy Analyzer not found: {e}")
        sys.exit(1)


def select_strategy(sa, strategy_name):
    """Select strategy from the NinjaScriptSelector dropdown."""
    try:
        selector = sa.child_window(auto_id="NinjaScriptSelector")
        selector.click_input()
        time.sleep(0.8)
        # found_index=0 picks the first match when the dropdown has multiple elements
        # sharing the same title (e.g., MenuItem + its Text child both show strategy name)
        item = sa.child_window(title=strategy_name, control_type="MenuItem", found_index=0)
        item.click_input()
        time.sleep(1.0)
        return True
    except Exception as e:
        print(f"  WARNING: could not select strategy '{strategy_name}': {e}")
        return False


def set_instrument(sa, instrument):
    """Set instrument in the InstrumentSelector control."""
    try:
        selector = sa.child_window(auto_id="InstrumentSelector")
        selector.click_input()
        time.sleep(0.3)
        send_keys("^a")
        send_keys(instrument, with_spaces=True)
        time.sleep(0.3)
        send_keys("{ENTER}")
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"  WARNING: could not set instrument '{instrument}': {e}")
        return False


def set_edit(sa, auto_id, value):
    """Set an Edit field by AutomationId."""
    try:
        ctrl = sa.child_window(auto_id=auto_id, control_type="Edit")
        ctrl.set_edit_text(str(value))
        return True
    except Exception as e:
        print(f"  WARNING: set_edit '{auto_id}' failed: {e}")
        return False


def set_combo(sa, auto_id, value):
    """Set a ComboBox field by AutomationId."""
    try:
        ctrl = sa.child_window(auto_id=auto_id, control_type="ComboBox")
        ctrl.select(str(value))
        return True
    except Exception:
        pass
    try:
        ctrl = sa.child_window(auto_id=auto_id, control_type="ComboBox")
        ctrl.expand()
        time.sleep(0.2)
        ctrl.child_window(title=str(value)).click_input()
        return True
    except Exception as e:
        print(f"  WARNING: set_combo '{auto_id}' failed: {e}")
        return False


def wait_for_run_complete(sa, timeout=RUN_TIMEOUT):
    """Poll until the Run button is re-enabled (backtest finished)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            run_btn = sa.child_window(auto_id="Run", control_type="Button")
            if run_btn.is_enabled():
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def configure_combo(sa, combo, global_params):
    """Push all settings for one combo into the Strategy Analyzer panel."""
    gp       = global_params
    strategy = combo["strategy"]
    pfx      = f"{strategy}PropertyGridEditorPDEX"

    # Select strategy first — this refreshes the strategy-specific params section
    select_strategy(sa, strategy)
    time.sleep(1.5)

    # Instrument
    set_instrument(sa, combo["instrument"])

    # Bar series
    set_combo(sa, "BarsPeriodPropertyGridEditorPDEX_PDEX_MarketDataType", gp["bar_type"])
    set_edit(sa, "BarsPeriodPropertyGridEditorPDEX_PDEX_Value", gp["bar_value"])

    # Date range
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_From", gp["start_date"])
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_To", gp["end_date"])

    # Slippage
    set_edit(sa, "StrategyBasePropertyGridEditorPDEX_Slippage", gp["slippage"])

    # Prop firm params — AutomationId prefix matches the strategy class name
    set_edit(sa, f"{pfx}_AccountSize",       gp["account_size"])
    set_edit(sa, f"{pfx}_RiskPct",           gp["risk_pct"])
    set_edit(sa, f"{pfx}_MaxDailyLoss",      gp["max_daily_loss"])
    set_edit(sa, f"{pfx}_DailyHaltFraction", gp["daily_halt_fraction"])
    set_edit(sa, f"{pfx}_CommissionPerSide", gp["commission_per_side"])

    # Strategy-specific params
    for key, value in combo.get("params", {}).items():
        set_edit(sa, f"{pfx}_{key}", value)


def run_combo(sa, combo, global_params, idx, total):
    print(f"\n[{idx}/{total}] {combo['id']}  ({combo['strategy']} on {combo['instrument']})")

    configure_combo(sa, combo, global_params)
    time.sleep(1)

    try:
        run_btn = sa.child_window(auto_id="Run", control_type="Button")
        run_btn.click_input()
        print("  Run clicked. Waiting for completion...")
    except Exception as e:
        print(f"  ERROR clicking Run: {e}")
        return False

    # SA takes a moment to disable the Run button after click
    time.sleep(2)
    finished = wait_for_run_complete(sa, RUN_TIMEOUT)
    if finished:
        print("  Backtest complete.")
    else:
        print(f"  WARNING: Timed out after {RUN_TIMEOUT}s.")

    time.sleep(2)
    return finished


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CFG)
    args = parser.parse_args()

    cfg    = load_config(args.config)
    combos = cfg["combos"]
    gp     = cfg["global_params"]

    app = connect_nt8()
    sa  = find_strategy_analyzer(app)

    total  = len(combos)
    passed = 0
    for i, combo in enumerate(combos, 1):
        ok = run_combo(sa, combo, gp, i, total)
        if ok:
            passed += 1

    print(f"\nFinished: {passed}/{total} combos ran successfully.")
    print("Results written to lucid_flex_results.csv in NT8 Documents folder.")


if __name__ == "__main__":
    main()
