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
  3. Reads results from NT8's strategy analyzer XML logs (written automatically)
  4. Writes lucid_flex_results.csv to the NT8 Documents folder

NOTE: NT8 must already be open with the Strategy Analyzer visible.
      Open it via: New -> Strategy Analyzer in NT8 Control Center.
"""

import sys
import os
import csv
import glob
import json
import time
import argparse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("ERROR: pywinauto not installed.")
    print("  Run: pip install pywinauto comtypes")
    sys.exit(1)


SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(SCRIPT_DIR, "backtest_config.json")
RUN_TIMEOUT = 600

NT8_DOCS    = Path.home() / "Documents" / "NinjaTrader 8"
SA_LOG_DIR  = NT8_DOCS / "strategyanalyzerlogs"
RESULTS_CSV = NT8_DOCS / "lucid_flex_results.csv"

CSV_FIELDS  = ["id", "strategy", "instrument",
               "net_pnl", "max_drawdown", "profit_factor", "win_pct", "trades"]


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
    selector = sa.child_window(auto_id="NinjaScriptSelector")
    for attempt in range(3):
        try:
            selector.click_input()
            time.sleep(1.5)  # dropdown needs time to populate on first open
            # found_index=0 picks first match — the MenuItem and its Text child
            # both share the same title, so pywinauto finds 2; we want index 0.
            item = sa.child_window(title=strategy_name, control_type="MenuItem", found_index=0)
            item.click_input()
            time.sleep(1.0)
            return True
        except Exception as e:
            if attempt < 2:
                send_keys("{ESCAPE}")
                time.sleep(1.0)
            else:
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


def set_checkbox(sa, auto_id, value):
    """Set a CheckBox field by AutomationId. value should be 'True' or 'False'."""
    try:
        ctrl   = sa.child_window(auto_id=auto_id, control_type="CheckBox")
        target = 1 if str(value).lower() == "true" else 0
        if ctrl.get_toggle_state() != target:
            ctrl.click_input()
        return True
    except Exception as e:
        print(f"  WARNING: set_checkbox '{auto_id}' failed: {e}")
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
    except Exception:
        pass
    try:
        # NT8 WPF ComboBoxes: click to open, find ListItem in the whole tree
        ctrl = sa.child_window(auto_id=auto_id, control_type="ComboBox")
        ctrl.click_input()
        time.sleep(0.3)
        item = sa.child_window(title=str(value), control_type="ListItem")
        item.click_input()
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


def read_result_from_xml(combo_id, strategy, instrument):
    """
    Find the most recently written SA XML log for this strategy and extract
    performance metrics from the Currency/UsDollar SummaryPerformancesSerialize.
    Returns a result dict or None on failure.
    """
    today   = datetime.now().strftime("%Y_%m_%d")
    pattern = str(SA_LOG_DIR / f"@@@{strategy}_{today}_*.xml")
    files   = sorted(glob.glob(pattern))
    if not files:
        print(f"  WARNING: No XML log found matching {pattern}")
        return None

    xml_path = files[-1]
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        # Sanity-check that the XML matches the expected instrument
        xml_instrument = root.findtext(".//Instrument") or ""
        if instrument.split()[0].upper() not in xml_instrument.upper():
            print(f"  WARNING: XML instrument '{xml_instrument}' doesn't match expected '{instrument}'")
        perf_nodes = root.findall(".//SummaryPerformancesSerialize")
        if not perf_nodes:
            print(f"  WARNING: No SummaryPerformancesSerialize in {xml_path}")
            return None
        # First node is Currency/UsDollar — the dollar P&L values we want
        raw     = perf_nodes[0].text or ""
        metrics = {}
        for part in raw.split("|"):
            bits = part.split(";")
            if len(bits) >= 2:
                metrics[bits[0]] = bits[1]  # "All" column (index 1)

        return {
            "id":            combo_id,
            "strategy":      strategy,
            "instrument":    instrument,
            "net_pnl":       float(metrics.get("TotalNetProfit",   0)),
            "max_drawdown":  float(metrics.get("MaxDrawdown",       0)),
            "profit_factor": float(metrics.get("ProfitFactor",      0)),
            "win_pct":       round(float(metrics.get("PercentProfitable", 0)) * 100, 2),
            "trades":        int(float(metrics.get("TotalNumTrades", 0))),
        }
    except Exception as e:
        print(f"  WARNING: Could not parse XML {xml_path}: {e}")
        return None


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

    # Bar value — bar_type (Minute) is retained by NT8 between runs, no need to set it
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

    # Strategy-specific params — Edit for numerics, CheckBox for bools, ComboBox for enums
    for key, value in combo.get("params", {}).items():
        aid = f"{pfx}_{key}"
        if not set_edit(sa, aid, value):
            if not set_checkbox(sa, aid, value):
                set_combo(sa, aid, value)


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
        return None

    # SA takes a moment to disable the Run button after click
    time.sleep(2)
    finished = wait_for_run_complete(sa, RUN_TIMEOUT)
    if not finished:
        print(f"  WARNING: Timed out after {RUN_TIMEOUT}s.")
        return None

    # Give NT8 a moment to finish writing the XML log
    time.sleep(2)
    print("  Backtest complete. Reading results from XML log...")
    result = read_result_from_xml(combo["id"], combo["strategy"], combo["instrument"])
    if result:
        print(f"  Trades={result['trades']}  NetPnL={result['net_pnl']:.2f}"
              f"  PF={result['profit_factor']:.4f}  MaxDD={result['max_drawdown']:.2f}")
    else:
        print("  WARNING: Could not read result from XML.")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CFG)
    args = parser.parse_args()

    cfg    = load_config(args.config)
    combos = cfg["combos"]
    gp     = cfg["global_params"]

    app = connect_nt8()
    sa  = find_strategy_analyzer(app)

    total   = len(combos)
    results = []
    for i, combo in enumerate(combos, 1):
        result = run_combo(sa, combo, gp, i, total)
        if result:
            results.append(result)

    # Write CSV — Python-side, bypassing the C# Terminated handler
    try:
        with open(RESULTS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults written to {RESULTS_CSV}  ({len(results)}/{total} combos)")
    except Exception as e:
        print(f"\nERROR writing CSV: {e}")

    print(f"Finished: {len(results)}/{total} combos produced results.")


if __name__ == "__main__":
    main()
