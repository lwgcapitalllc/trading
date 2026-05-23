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
    from pywinauto.timings import wait_until_passes
except ImportError:
    print("ERROR: pywinauto not installed.")
    print("  Run: pip install pywinauto comtypes")
    sys.exit(1)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(SCRIPT_DIR, "backtest_config.json")

# How long (seconds) to wait for a backtest run to finish before timing out
RUN_TIMEOUT = 600


def load_config(path):
    with open(path) as f:
        return json.load(f)


def connect_nt8():
    """Connect to the running NT8 process."""
    print("Connecting to NinjaTrader 8...")
    # NT8 window titles vary — try process name first, then title patterns
    attempts = [
        ("process name",  {"path": "NinjaTrader.exe"}),
        ("title NT8",     {"title_re": ".*NinjaTrader.*"}),
        ("title SA",      {"title_re": ".*Strategy Analyzer.*"}),
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
    from pywinauto import Desktop

    # Desktop enumeration is the most reliable — works regardless of how SA is docked
    try:
        sa = Desktop(backend="uia").window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        print("  Strategy Analyzer found.")
        return sa
    except Exception:
        pass

    # Fallback: search within the connected app
    try:
        sa = app.window(title_re=".*Strategy Analyzer.*")
        sa.wait("visible", timeout=10)
        print("  Strategy Analyzer found (via app).")
        return sa
    except Exception as e:
        print(f"  ERROR: Strategy Analyzer not found: {e}")
        print("  Open it via New -> Strategy Analyzer in NT8 Control Center.")
        sys.exit(1)


def set_field(sa, label_text, value):
    """
    Set a field in the Settings panel by its label.
    NT8 uses WPF so we find the element by AutomationId or Name.
    """
    try:
        ctrl = sa.child_window(title=label_text, control_type="Edit")
        ctrl.set_edit_text(str(value))
        return True
    except Exception:
        pass

    # Fallback: try finding by partial title
    try:
        ctrl = sa.child_window(title_re=f".*{label_text}.*", control_type="Edit")
        ctrl.set_edit_text(str(value))
        return True
    except Exception:
        return False


def set_combo(sa, label_text, value):
    """Set a combo-box / dropdown field."""
    try:
        ctrl = sa.child_window(title=label_text, control_type="ComboBox")
        ctrl.select(str(value))
        return True
    except Exception:
        return False


def wait_for_run_complete(sa, timeout=RUN_TIMEOUT):
    """Poll until the Run button is re-enabled (backtest finished)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            run_btn = sa.child_window(title="Run", control_type="Button")
            if run_btn.is_enabled():
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def configure_combo(sa, combo, global_params):
    """Push all settings for one combo into the Strategy Analyzer panel."""
    gp = global_params

    fields = {
        # Data Series
        "Instrument":       combo["instrument"],
        "Type":             gp["bar_type"],
        "Value":            gp["bar_value"],
        # Time Frame
        "Start date":       gp["start_date"],
        "End date":         gp["end_date"],
        # Historical fill processing
        "Slippage":         gp["slippage"],
        # Prop firm params
        "Account Size ($)": gp["account_size"],
        "Risk % per Trade": gp["risk_pct"],
        "Max Daily Loss ($)": gp["max_daily_loss"],
        "Daily Halt Fraction": gp["daily_halt_fraction"],
        "Commission/Side ($)": gp["commission_per_side"],
    }

    # Merge strategy-specific params
    fields.update(combo["params"])

    for label, value in fields.items():
        ok = set_field(sa, label, value) or set_combo(sa, label, value)
        if not ok:
            print(f"    WARNING: could not set field '{label}' — may need manual tuning")

    # Set strategy dropdown
    set_combo(sa, "Strategy", combo["strategy"])

    # Trading hours — set to RTH template if available
    # NT8 uses "Trading hours" dropdown; RTH template name varies by instrument
    # Leave as "Use instrument settings" unless a specific override is needed


def run_combo(sa, combo, global_params, idx, total):
    print(f"\n[{idx}/{total}] {combo['id']}  ({combo['strategy']} on {combo['instrument']})")

    configure_combo(sa, combo, global_params)
    time.sleep(1)

    try:
        run_btn = sa.child_window(title="Run", control_type="Button")
        run_btn.click()
        print("  Run clicked. Waiting for completion...")
    except Exception as e:
        print(f"  ERROR clicking Run: {e}")
        return False

    finished = wait_for_run_complete(sa, RUN_TIMEOUT)
    if finished:
        print("  Backtest complete.")
    else:
        print(f"  WARNING: Timed out after {RUN_TIMEOUT}s — backtest may still be running.")

    # Small pause between runs
    time.sleep(2)
    return finished


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CFG)
    args = parser.parse_args()

    cfg     = load_config(args.config)
    combos  = cfg["combos"]
    gp      = cfg["global_params"]

    app = connect_nt8()
    sa  = find_strategy_analyzer(app)

    total = len(combos)
    passed = 0
    for i, combo in enumerate(combos, 1):
        ok = run_combo(sa, combo, gp, i, total)
        if ok:
            passed += 1

    print(f"\nFinished: {passed}/{total} combos ran successfully.")
    print("Results written to lucid_flex_results.csv in NT8 Documents folder.")
    print("Next: scp the results file to your Mac and run analyze.py")


if __name__ == "__main__":
    main()
