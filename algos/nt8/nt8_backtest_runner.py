"""
Automates NinjaTrader 8 Strategy Analyzer to run backtests.

Run this script ON THE VPS (via SSH or RDP terminal), not on Mac.

Prerequisites on VPS:
    pip install pywinauto comtypes

Two modes:

  Lab mode (job-keyed, called by nt8_agent.py):
    python nt8_backtest_runner.py --job-id <id> --job-spec <path/to/job_spec.json>
    Reads a single job spec, runs it, writes NT8_DOCS/lab_results/<job_id>/result.json.
    Emits PCT:N:message lines for agent progress tracking.

  Legacy mode (config-driven, all combos):
    python nt8_backtest_runner.py [--config path/to/backtest_config.json] [--combo ID]
    Writes lucid_flex_results.csv to the NT8 Documents folder.

NOTE: NT8 must already be open. The Strategy Analyzer is opened automatically if not visible.
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


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if (f != f) else f  # reject NaN
    except Exception:
        return None


def _safe_int(v) -> int | None:
    try:
        return int(float(v))
    except Exception:
        return None


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
    print("  Make sure NinjaTrader 8 is running.")
    sys.exit(1)


def _open_sa_via_new_menu(app):
    """Open a new Strategy Analyzer window via NT8 Control Center New menu.
    Called when SA is not already visible — happens after a hard NT8 crash/restart."""
    print("  SA not visible — opening via New menu...")
    try:
        dt = Desktop(backend="uia")
        cc = dt.window(title_re=".*NinjaTrader 8.*", control_type="Window")
        cc.set_focus()
        time.sleep(0.5)
        cc.child_window(title="New", control_type="MenuItem").click_input()
        time.sleep(0.8)
        # The popup menu item for Strategy Analyzer
        dt.window(title="Strategy Analyzer", control_type="MenuItem").click_input()
        time.sleep(4.0)  # SA takes a few seconds to open and load
        print("  SA opened via New menu.")
    except Exception as e:
        print(f"  ERROR: Could not open SA via New menu: {e}")
        sys.exit(1)


def find_strategy_analyzer(app):
    """Locate the Strategy Analyzer window / panel. Opens it if not already visible."""
    for attempt in range(2):
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
        except Exception:
            pass
        if attempt == 0:
            # SA not found — try opening it via New menu, then retry once
            _open_sa_via_new_menu(app)
    print("  ERROR: Strategy Analyzer not found after open attempt.")
    sys.exit(1)


def _find_strategy_item(sa, strategy_name, timeout=2.5):
    """Find a strategy MenuItem, polling until the WPF popup renders.

    WPF ComboBox popups render asynchronously and appear either as a child of
    the SA window (fresh SA) or as a top-level Desktop element (after the first
    run). Poll in 100ms increments so we return as soon as the item is present
    rather than burning a fixed sleep.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            item = sa.child_window(title=strategy_name, control_type="MenuItem", found_index=0)
            if item.exists(timeout=0):
                return item
        except Exception:
            pass
        try:
            item = Desktop(backend="uia").window(title=strategy_name, control_type="MenuItem", found_index=0)
            if item.exists(timeout=0):
                return item
        except Exception:
            pass
        time.sleep(0.1)
    return None


def select_strategy(sa, strategy_name):
    """Select strategy from the NinjaScriptSelector dropdown.

    Tries twice. On failure closes the dropdown by clicking the selector again
    (not ESC — ESC can dismiss unrelated dialogs per NT8 WPF behaviour).
    """
    selector = sa.child_window(auto_id="NinjaScriptSelector")
    for attempt in range(2):
        try:
            selector.click_input()
            item = _find_strategy_item(sa, strategy_name)
            if item is None:
                raise RuntimeError("not found in SA subtree or Desktop")
            item.click_input()
            time.sleep(1.0)
            return True
        except Exception as e:
            try:
                selector.click_input()  # toggle dropdown closed
            except Exception:
                pass
            time.sleep(0.5)
            if attempt == 1:
                print(f"  WARNING: could not select strategy '{strategy_name}': {e}")
    return False


_MONTH_ABR = {
    "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR",
    "05": "MAY", "06": "JUN", "07": "JUL", "08": "AUG",
    "09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC",
}


def _to_nt8_instrument(instrument: str) -> str:
    """Convert internal format 'MNQ 06-26' to NT8 format 'MNQ JUN26'.
    Passes through anything that doesn't match the MM-YY pattern.
    """
    parts = instrument.split()
    if len(parts) == 2 and "-" in parts[1]:
        root = parts[0]
        mm, yy = parts[1].split("-", 1)
        mon = _MONTH_ABR.get(mm, mm)
        return f"{root} {mon}{yy}"
    return instrument  # already in NT8 format or root-only


def set_instrument(sa, instrument):
    """Set instrument in the InstrumentSelector control.
    Converts internal format 'MNQ 06-26' to NT8 contract format 'MNQ JUN26'.
    """
    nt8_instr = _to_nt8_instrument(instrument)
    try:
        selector = sa.child_window(auto_id="InstrumentSelector")
        selector.click_input()
        time.sleep(0.3)
        send_keys("^a")
        send_keys(nt8_instr, with_spaces=True)
        time.sleep(0.2)
        send_keys("{ENTER}")
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"  WARNING: could not set instrument '{nt8_instr}': {e}")
        return False


def set_edit(sa, auto_id, value, warn=True):
    """Set an Edit field by AutomationId."""
    try:
        ctrl = sa.child_window(auto_id=auto_id, control_type="Edit")
        if not ctrl.exists(timeout=0.5):
            return False
        ctrl.set_edit_text(str(value))
        return True
    except Exception as e:
        if warn:
            print(f"  WARNING: set_edit '{auto_id}' failed: {e}")
        return False



def set_edit_typed(sa, auto_id, value, warn=True):
    """
    Set an Edit field using click_input+type_keys so NT8's WPF commit fires.
    set_edit_text alone does not trigger NT8's LostFocus/TextChanged handler.
    """
    try:
        ctrl = sa.child_window(auto_id=auto_id, control_type="Edit")
        if not ctrl.exists(timeout=1.0):
            return False
        ctrl.click_input()
        time.sleep(0.1)
        ctrl.type_keys(f"^a{str(value)}~", with_spaces=True)
        time.sleep(0.05)
        return True
    except Exception as e:
        if warn:
            print(f"  WARNING: set_edit_typed '{auto_id}' failed: {e}")
        return False


def set_checkbox(sa, auto_id, value):
    """Set a CheckBox field by AutomationId. value should be 'True' or 'False'."""
    try:
        ctrl = sa.child_window(auto_id=auto_id, control_type="CheckBox")
        if not ctrl.exists(timeout=0.5):
            return False
        target = 1 if str(value).lower() == "true" else 0
        if ctrl.get_toggle_state() != target:
            ctrl.click_input()
        return True
    except Exception as e:
        print(f"  WARNING: set_checkbox '{auto_id}' failed: {e}")
        return False


def set_combo(sa, auto_id, value):
    """Set a ComboBox field by AutomationId."""
    ctrl = sa.child_window(auto_id=auto_id, control_type="ComboBox")
    if not ctrl.exists(timeout=0.5):
        return False
    try:
        ctrl.select(str(value))
        return True
    except Exception:
        pass
    try:
        ctrl.expand()
        time.sleep(0.2)
        ctrl.child_window(title=str(value)).click_input()
        return True
    except Exception:
        pass
    try:
        # NT8 WPF ComboBoxes: dropdown popup is a child of the top-level NT8 window,
        # not of the SA panel — must search top_level_parent(), not sa.
        ctrl.click_input()
        time.sleep(0.3)
        item = sa.top_level_parent().child_window(title=str(value), control_type="ListItem")
        item.click_input()
        return True
    except Exception:
        pass
    try:
        ctrl.type_keys('{ESC}')  # close any open dropdown
    except Exception:
        pass
    print(f"  WARNING: set_combo '{auto_id}' = '{value}' failed all attempts")
    return False


_BT_AID = "StrategyAnalyzerTabPropertiesPropertyGridEditorBacktestType"


def _find_bt_item(sa, value: str, timeout=2.0):
    """Poll for a BacktestType ListItem after the dropdown is expanded.

    WPF popup items appear under top_level_parent(), not under the ComboBox itself.
    Same pattern as _find_strategy_item.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            item = sa.top_level_parent().child_window(title=value, control_type="ListItem", found_index=0)
            if item.exists(timeout=0):
                return item
        except Exception:
            pass
        try:
            item = Desktop(backend="uia").window(title=value, control_type="ListItem", found_index=0)
            if item.exists(timeout=0):
                return item
        except Exception:
            pass
        time.sleep(0.1)
    return None


def _set_backtest_type(sa, value: str):
    """Set NT8 SA BacktestType dropdown. Hard-fails (RuntimeError) on failure.

    WPF popup items appear under top_level_parent(), not under the ComboBox subtree.
    expand() opens the popup, then _find_bt_item() locates the item.
    """
    ctrl = sa.child_window(auto_id=_BT_AID, control_type="ComboBox")
    if not ctrl.exists(timeout=2.0):
        raise RuntimeError("BacktestType combo not found — SA property grid not loaded")

    try:
        ctrl.expand()
    except Exception:
        ctrl.click_input()
    time.sleep(0.4)

    item = _find_bt_item(sa, value)
    if item is not None:
        item.click_input()
        time.sleep(0.2)
        return

    try:
        ctrl.type_keys('{ESC}')
    except Exception:
        pass
    raise RuntimeError(f"BacktestType item '{value}' not found — popup opened but item not in UIA tree")


def wait_for_run_complete(sa, timeout=RUN_TIMEOUT, use_abort_btn=False):
    """
    Wait for the SA run to finish.

    Backtest mode (use_abort_btn=False): watches Run button disabled -> enabled.
    Optimize mode (use_abort_btn=True): watches for Abort button to appear then disappear.
    NT8 replaces the Run button with Abort during optimization, so the Run-button
    heuristic does not work for that mode.

    Returns True on success, False on timeout.
    """
    deadline = time.time() + timeout

    if use_abort_btn:
        # Phase 1: wait up to 30s for the Abort button to appear (run started)
        phase1_deadline = time.time() + 30
        while time.time() < phase1_deadline:
            try:
                abort_btn = sa.child_window(title="Abort", control_type="Button")
                if abort_btn.exists() and abort_btn.is_visible():
                    break
            except Exception:
                pass
            time.sleep(0.5)
        # Phase 2: wait for Abort button to disappear (run complete)
        while time.time() < deadline:
            try:
                abort_btn = sa.child_window(title="Abort", control_type="Button")
                if not abort_btn.exists() or not abort_btn.is_visible():
                    return True
            except Exception:
                # element gone — run is done
                return True
            time.sleep(1)
        return False

    # Backtest mode: Run button disabled -> enabled
    phase1_deadline = time.time() + 15
    while time.time() < phase1_deadline:
        try:
            run_btn = sa.child_window(auto_id="Run", control_type="Button")
            if not run_btn.is_enabled():
                break
        except Exception:
            pass
        time.sleep(0.5)
    while time.time() < deadline:
        try:
            run_btn = sa.child_window(auto_id="Run", control_type="Button")
            if run_btn.is_enabled():
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def read_result_from_xml(combo_id, strategy, instrument, written_after: float = 0.0):
    """
    Find the most recently written SA XML log for this strategy and extract
    performance metrics from the Currency/UsDollar SummaryPerformancesSerialize.
    written_after: unix timestamp — ignore XML files older than this (avoids stale results).
    Returns a result dict or None on failure.
    """
    today   = datetime.now().strftime("%Y_%m_%d")
    pattern = str(SA_LOG_DIR / f"@@@{strategy}_{today}_*.xml")
    files   = [f for f in sorted(glob.glob(pattern))
               if os.path.getmtime(f) >= written_after]
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

        avg_win  = _safe_float(metrics.get("AverageWinningTrade"))
        avg_loss = _safe_float(metrics.get("AverageLosingTrade"))
        return {
            "id":                     combo_id,
            "strategy":               strategy,
            "instrument":             instrument,
            "net_pnl":                float(metrics.get("TotalNetProfit",   0)),
            "max_drawdown":           abs(float(metrics.get("MaxDrawdown",   0))),  # NT8 reports as negative
            "profit_factor":          float(metrics.get("ProfitFactor",      0)),
            "win_pct":                round(float(metrics.get("PercentProfitable", 0)) * 100, 2),
            "trades":                 int(float(metrics.get("TotalNumTrades", 0))),
            # Extended KPIs present in NT8's SummaryPerformancesSerialize
            "sharpe":                 _safe_float(metrics.get("SharpeRatio")),
            "sortino":                _safe_float(metrics.get("SortinoRatio")),
            "avg_win":                avg_win,
            "avg_loss":               avg_loss,
            "avg_trade_duration_min": _safe_float(metrics.get("AverageTimeInMarket")),
            "worst_losing_streak":    _safe_int(metrics.get("MaxConsecLosers")),
        }
    except Exception as e:
        print(f"  WARNING: Could not parse XML {xml_path}: {e}")
        return None


def configure_combo(sa, combo, global_params):
    """Push all settings for one combo into the Strategy Analyzer panel."""
    gp       = global_params
    strategy = combo["strategy"]
    pfx      = f"{strategy}PropertyGridEditorPDEX"

    # Select strategy first — this refreshes the strategy-specific params section.
    # Sleep 3s: switching strategy class causes NT8 to fully rebuild the property grid,
    # temporarily invalidating the UIA tree. 3s is enough for it to settle.
    select_strategy(sa, strategy)
    time.sleep(3.0)

    # Instrument
    set_instrument(sa, combo["instrument"])

    # Bar value — bar_type (Minute) is retained by NT8 between runs, no need to set it
    set_edit(sa, "BarsPeriodPropertyGridEditorPDEX_PDEX_Value", gp["bar_value"])

    # Date range
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_From", _nt8_date(gp["start_date"]))
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_To",   _nt8_date(gp["end_date"]))

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
        if not set_edit(sa, aid, value, warn=False):
            if not set_checkbox(sa, aid, value):
                set_combo(sa, aid, value)


def run_combo(app, combo, global_params, idx, total):
    print(f"\n[{idx}/{total}] {combo['id']}  ({combo['strategy']} on {combo['instrument']})")

    # Re-acquire SA handle each combo — stale handles crash after a strategy-class switch
    sa = find_strategy_analyzer(app)
    configure_combo(sa, combo, global_params)
    time.sleep(1)

    click_time = time.time()
    try:
        run_btn = sa.child_window(auto_id="Run", control_type="Button")
        run_btn.click_input()
        print("  Run clicked. Waiting for completion...")
    except Exception as e:
        print(f"  ERROR clicking Run: {e}")
        return None

    finished = wait_for_run_complete(sa, RUN_TIMEOUT)
    if not finished:
        print(f"  WARNING: Timed out after {RUN_TIMEOUT}s.")
        return None

    # Poll for the XML log to appear (NT8 writes it async after re-enabling Run)
    today   = datetime.now().strftime("%Y_%m_%d")
    pattern = str(SA_LOG_DIR / f"@@@{combo['strategy']}_{today}_*.xml")
    xml_deadline = time.time() + 60
    while time.time() < xml_deadline:
        if any(os.path.getmtime(f) >= click_time for f in glob.glob(pattern)):
            break
        time.sleep(1)
    print("  Backtest complete. Reading results from XML log...")
    result = read_result_from_xml(combo["id"], combo["strategy"], combo["instrument"],
                                  written_after=click_time)
    if result:
        print(f"  Trades={result['trades']}  NetPnL={result['net_pnl']:.2f}"
              f"  PF={result['profit_factor']:.4f}  MaxDD={result['max_drawdown']:.2f}")
    else:
        print("  WARNING: Could not read result from XML.")
    return result


def _pct(n: int, msg: str = ""):
    """Emit a progress line the agent parses: PCT:N:message."""
    print(f"PCT:{n}:{msg}", flush=True)


# ── Lab mode (job-keyed) ──────────────────────────────────────────────────────

def _nt8_date(iso: str) -> str:
    """Convert ISO YYYY-MM-DD to NT8 date format M/D/YYYY."""
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}/{y}"


# ── Native Optimizer Mode ─────────────────────────────────────────────────────

# Longer timeout for the optimizer — it runs all combos in one shot.
_OPT_TIMEOUT = 7200  # 2 hours max


def _build_opt_grid_map(sa) -> dict:
    """
    In NT8 Optimize mode, scan SA descendants in document order and build a
    mapping from each param's display label (lowercased) to its txtBox Edit element.

    Each optimizable param row consists of a Group (label) followed immediately
    by an Edit with auto_id='txtBox' (the Start;End;Step range field).  They are
    siblings in the UIA tree — not parent/child.
    """
    result          = {}
    last_group_text = None

    for el in sa.descendants():
        ct  = str(el.element_info.control_type)
        aid = el.element_info.automation_id or ""

        if ct == "Group":
            t = el.window_text()
            if t:
                last_group_text = t
        elif ct == "Edit" and aid == "txtBox":
            if last_group_text:
                result[last_group_text.lower()] = el
                last_group_text = None  # consumed — reset for the next pair

    return result


import re as _re

def _camel_words(name: str) -> list:
    """Split a camelCase/PascalCase identifier into lowercase words."""
    return [w.lower() for w in _re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+', name)]


def _match_display_name(code_name: str, grid_map: dict,
                         explicit: dict | None = None) -> str | None:
    """
    Find the grid_map key that best matches a NinjaScript property code name.

    explicit: optional {code_name: display_name} dict supplied in the spec.
              When present and the display_name exists in grid_map, use it directly.

    Fuzzy fallback: split both names into words, count substring overlaps, require
    >= 70 % of code words to match.  Short words (< 4 chars) are skipped to avoid
    common-word false positives (e.g. 'per', 'one').
    """
    if explicit and code_name in explicit:
        dn = explicit[code_name].lower()
        return dn if dn in grid_map else None

    code_words = [w for w in _camel_words(code_name) if len(w) >= 4]
    if not code_words:
        return None

    best_key   = None
    best_score = 0.0

    for key in grid_map:
        display_words = _re.sub(r'[^a-z0-9\s]', ' ', key).split()
        matches = sum(
            1 for cw in code_words
            if any(cw in dw or dw.startswith(cw) for dw in display_words)
        )
        score = matches / len(code_words)
        if score > best_score:
            best_score = score
            best_key   = key

    return best_key if best_score >= 0.70 else None


def _set_range_in_grid(grid_map: dict, code_name: str, lo, hi, step,
                       explicit: dict | None = None) -> bool:
    """
    Set a param's optimization range in NT8's Optimize-mode property grid.

    Finds the txtBox Edit element by matching code_name to a display label in
    grid_map (using explicit dict first, fuzzy fallback second), then writes
    'lo;hi;step'.

    Returns True on success, False if the param was not found.
    """
    display_key = _match_display_name(code_name, grid_map, explicit)
    if display_key is None:
        print(f"  WARNING: no Optimize-mode txtBox found for param '{code_name}'")
        return False
    el = grid_map[display_key]
    try:
        el.scroll_into_view()
        time.sleep(0.1)
    except Exception:
        pass
    val = f"{lo};{hi};{step}"
    # click_input focuses the field; type_keys with ~ (Enter) commits the value.
    # set_edit_text alone does not trigger NT8's LostFocus commit handler.
    el.click_input()
    time.sleep(0.05)
    el.type_keys(f"^a{val}~", with_spaces=True)
    print(f"  Param range '{code_name}' -> '{display_key}' = {val}")
    return True


def _set_plain_value_in_grid(grid_map: dict, code_name: str, value,
                              explicit: dict | None = None) -> bool:
    """
    Set a fixed (non-range) param value in NT8 Optimize-mode grid.
    Uses set_focus() instead of click_input() to avoid panel scroll.
    """
    display_key = _match_display_name(code_name, grid_map, explicit)
    if display_key is None:
        return False
    el = grid_map[display_key]
    try:
        el.scroll_into_view()
        time.sleep(0.05)
    except Exception:
        pass
    try:
        el.set_focus()
        time.sleep(0.05)
        el.type_keys(f"^a{value}~", with_spaces=True)
        print(f"  Fixed param '{code_name}' -> '{display_key}' = {value}")
        return True
    except Exception as e:
        print(f"  WARNING: _set_plain_value_in_grid '{code_name}' failed: {e}")
        return False


def _dismiss_dialog(dt) -> None:
    """Dismiss any lingering Export As or Confirm Save dialog."""
    for title in ["Export As", "Confirm Save As", "Confirm"]:
        try:
            w = dt.window(title=title)
            if w.exists(timeout=0.1):
                for btn in ["Cancel", "No", "OK"]:
                    try:
                        w.child_window(title=btn, control_type="Button").click_input()
                        return
                    except Exception:
                        pass
                w.close()
        except Exception:
            pass


def _nt8_split_param_names(names_concat: str) -> list:
    """
    Split NT8's concatenated parameter-name string into individual names.
    Returns the ordered list of display names (one per slash-separated value).
    """
    parts = _re.split(r'(?<=\))(?=[A-Z])', names_concat)
    result = []
    for part in parts:
        if '(' not in part:
            sub = _re.split(r'(?<=[a-z%])(?=[A-Z])', part)
            result.extend(s.strip() for s in sub if s.strip())
        else:
            paren_start = part.index('(')
            prefix = part[:paren_start]
            sub = _re.split(r'(?<=[a-z])(?=[A-Z])', prefix)
            if len(sub) > 1:
                result.extend(s.strip() for s in sub[:-1] if s.strip())
                result.append((sub[-1] + part[paren_start:]).strip())
            else:
                result.append(part.strip())
    return [t for t in result if t]

def _parse_optimization_csv(csv_path: str, param_names: set) -> list:
    """
    Parse NT8 optimization results grid CSV.

    NT8 grid format (exported via right-click on combo rows):
      Columns: Instrument, Performance, Parameters, Total net profit, ...
      'Parameters' cell: "v0/v1/.../vN (DisplayName0DisplayName1...DisplayNameN)"
      — one row per combo, param values embedded in the Parameters column.

    param_names: set of NinjaScript code names (e.g. {'ORMinutes', 'TpMultiple'}).
    Matching against display names is case-insensitive substring search.
    """
    import csv as csv_mod

    # NT8 grid column name → internal KPI name (case-insensitive lookup below)
    _KPI_MAP = {
        "total net profit":   "net_pnl",
        "net profit":         "net_pnl",
        "profit factor":      "profit_factor",
        "max. drawdown":      "max_drawdown",
        "max drawdown":       "max_drawdown",
        "total # of trades":  "trade_count",
        "# trades":           "trade_count",
        "num. trades":        "trade_count",
        "percent profitable": "win_rate",
        "% profitable":       "win_rate",
        "sharpe ratio":       "sharpe",
    }

    def _coerce(val_str: str):
        s = val_str.strip()
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        try:
            f = float(s.replace(",", "").replace("$", "").replace("%", ""))
            return int(f) if f == int(f) else f
        except (ValueError, OverflowError):
            return s

    combos = []
    param_pos: dict | None = None   # {code_name: position_in_slash_split}

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                params: dict = {}
                kpis:   dict = {}

                # --- Parse Parameters column to extract param values ---
                params_col = (row.get("Parameters") or "").strip()
                if params_col and "(" in params_col:
                    paren_idx   = params_col.index(" (")
                    values_str  = params_col[:paren_idx]
                    names_raw   = params_col[paren_idx + 2:].rstrip(")")
                    values_list = values_str.split("/")

                    # Build position mapping once from the first populated row
                    if param_pos is None:
                        display_names = _nt8_split_param_names(names_raw)
                        param_pos = {}
                        for code in param_names:
                            # Case-insensitive substring match against display names
                            code_lower = code.lower()
                            for i, dn in enumerate(display_names):
                                if code_lower in dn.lower() or dn.lower() in code_lower:
                                    param_pos[code] = i
                                    break
                            if code not in param_pos:
                                # Fallback: match by camelCase words
                                cw = [w.lower() for w in _re.findall(
                                    r'[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+',
                                    code) if len(w) >= 4]
                                best_i, best_s = None, 0.0
                                for i, dn in enumerate(display_names):
                                    dw = dn.lower().split()
                                    matches = sum(1 for c in cw
                                                  if any(c in d or d.startswith(c)
                                                         for d in dw))
                                    sc = matches / len(cw) if cw else 0
                                    if sc > best_s:
                                        best_s, best_i = sc, i
                                if best_s >= 0.60 and best_i is not None:
                                    param_pos[code] = best_i
                        print(f"  [opt-export] param_pos: {param_pos}")

                    # Extract each param's value by position
                    for code, pos in (param_pos or {}).items():
                        if pos < len(values_list):
                            params[code] = _coerce(values_list[pos])

                # --- Extract KPIs from standard columns ---
                for col, val in row.items():
                    col_key = (col or "").strip().lower()
                    kpi     = _KPI_MAP.get(col_key)
                    if kpi:
                        try:
                            v = float((val or "").strip()
                                      .replace("$", "").replace(",", "")
                                      .replace("%", ""))
                            if kpi == "win_rate":
                                # NT8 CSV may express as 32.7 (percentage) or 0.327 (fraction)
                                if v > 1.0:
                                    v = round(v / 100.0, 4)
                                else:
                                    v = round(v, 4)
                            if kpi == "max_drawdown":
                                v = abs(v)
                            kpis[kpi] = round(v, 4)
                        except (ValueError, OverflowError):
                            pass

                if params or kpis:
                    combos.append({"params": params, "kpis": kpis})

    except Exception as e:
        print(f"  [opt-export] CSV parse error: {e}")

    print(f"  [opt-export] Parsed {len(combos)} combos from optimization results")
    return combos


def _export_optimization_results(sa, job_id: str, param_names: set) -> list:
    """
    Export NT8 optimization results grid to CSV via the two-pass right-click method.

    After the optimizer completes NT8 shows the results grid in the SA main area.
    We right-click that area to find and click Export, then parse the resulting CSV.

    Returns list of {params: {...}, kpis: {...}} — empty on any failure.
    """
    from pywinauto import mouse as _mouse, Desktop
    import shutil

    out_dir = NT8_DOCS / "lab_results" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    dt = Desktop(backend="uia")
    _dismiss_dialog(dt)
    time.sleep(0.1)

    # Restore SA if minimized — minimized windows have invalid screen rect
    try:
        sa.restore()
        time.sleep(0.3)
    except Exception:
        pass

    # Right-click inside the optimization combo rows (top 5% of SA window).
    # y=5% lands in the first result rows; y=50%+ lands in the performance
    # summary tab which exports the wrong format.
    sa_rect = sa.rectangle()
    sa_w    = sa_rect.right  - sa_rect.left
    sa_h    = sa_rect.bottom - sa_rect.top
    rc_x    = sa_rect.left + int(sa_w * 0.25)
    rc_y    = sa_rect.top  + int(sa_h * 0.05)

    nt8           = sa.top_level_parent()
    export_coords = None

    # Pass 1: open context menu, scan NT8 UIA tree for Export item screen coordinates.
    # UIA scan closes the WPF popup — capture coords before menu closes.
    _mouse.right_click(coords=(rc_x, rc_y))
    time.sleep(0.5)
    menu_items_found = []
    for el in nt8.descendants():
        txt = (el.window_text() or "").strip()
        ct  = str(getattr(el.element_info, "control_type", ""))
        if ct == "MenuItem" and txt:
            r = el.rectangle()
            menu_items_found.append(f"{txt}@{r.width()}x{r.height()}")
            if txt.startswith("Export") and r.width() > 5 and export_coords is None:
                export_coords = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)

    print(f"  [opt-export] Menu items found: {menu_items_found}")
    if export_coords is None:
        print("  [opt-export] Export menu item not found — no export")
        send_keys("{ESC}")
        return []

    # Pass 2: right-click again, immediately click Export at the cached coordinates.
    _mouse.right_click(coords=(rc_x, rc_y))
    time.sleep(0.4)
    _mouse.click(coords=export_coords)
    print(f"  [opt-export] Clicked Export at {export_coords}")
    time.sleep(0.8)

    # Enter twice: accept default filename, confirm overwrite
    send_keys("{ENTER}")
    time.sleep(0.3)
    send_keys("{ENTER}")
    time.sleep(1.0)

    _dismiss_dialog(dt)

    # Find the CSV NT8 just wrote (default name: "NinjaTrader Grid *.csv" in Documents)
    docs   = Path.home() / "Documents"
    cutoff = time.time() - 30
    csvs   = [p for p in docs.glob("NinjaTrader Grid*.csv") if p.stat().st_mtime >= cutoff]
    if not csvs:
        csvs = sorted(docs.glob("NinjaTrader Grid*.csv"),
                      key=lambda p: p.stat().st_mtime, reverse=True)[:1]

    if not csvs:
        print("  [opt-export] No CSV found after optimization export")
        return []

    csv_path = max(csvs, key=lambda p: p.stat().st_mtime)
    dest     = out_dir / "opt_results.csv"
    shutil.copy(str(csv_path), str(dest))
    print(f"  [opt-export] CSV saved to {dest.name}")

    return _parse_optimization_csv(str(csv_path), param_names)


def run_native_optimize_mode(job_id: str, spec: dict):
    """
    Native optimizer mode: run NT8's Strategy Analyzer in Optimize mode.

    Switches the SA BacktestType to "Optimize", sets per-param Start;End;Step
    ranges for Strategy Logic params, keeps Foundational params as fixed values,
    fires Run, waits for all combos to complete, then exports the results grid to CSV.

    Writes native_opt_result.json to lab_results/<job_id>/ on success.
    Exits non-zero on failure so nt8_agent.py classifies the run correctly.

    spec fields:
        strategy_class   str
        instrument       str   (internal format, e.g. "MNQ 06-26")
        bar_type         str   "Minute" / "Day"
        bar_value        int
        start_date       str   YYYY-MM-DD
        end_date         str   YYYY-MM-DD
        commission_per_side  float
        slippage_ticks   int
        param_ranges     dict  {name: {min, max, step} | [val, ...] | scalar}
        fixed_params     dict  {name: value}  (Foundational + non-optimized defaults)
    """
    strategy           = spec["strategy_class"]
    instr              = spec["instrument"]
    param_ranges       = spec.get("param_ranges", {})
    fixed_params       = spec.get("fixed_params", {})
    param_display_names = spec.get("param_display_names", {})

    print(f"JOB {job_id}: native optimize {strategy} on {instr}")
    print(f"  Ranges: { {k: (v if isinstance(v, list) else v) for k, v in param_ranges.items()} }")
    _pct(10, "Connecting to NT8")

    app = connect_nt8()
    sa  = find_strategy_analyzer(app)
    _pct(20, "Selecting strategy")

    pfx = f"{strategy}PropertyGridEditorPDEX"

    # Select strategy first — property grid is not live until a strategy is loaded.
    if not select_strategy(sa, strategy):
        print(f"  ERROR: Strategy '{strategy}' not found in NT8 — is it compiled?")
        sys.exit(1)
    time.sleep(3.0)

    # Must set Optimize mode after strategy load; hard-fails if it can't be set.
    try:
        _set_backtest_type(sa, "Optimize")
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    _pct(25, "Configuring parameters")

    # Instrument, date range, bar value, slippage — same fields as single-run mode.
    # These must be set explicitly; Optimize mode does not inherit them from the last run.
    set_instrument(sa, instr)
    set_edit(sa, "BarsPeriodPropertyGridEditorPDEX_PDEX_Value", spec.get("bar_value", 5))
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_From",  _nt8_date(spec["start_date"]))
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_To",    _nt8_date(spec["end_date"]))
    set_edit(sa, "StrategyBasePropertyGridEditorPDEX_Slippage", spec.get("slippage_ticks", 1))

    # Separate fixed_params by type.
    # Numeric params use SRWD Custom controls in the Optimize grid (txtBox auto_id).
    # String params use PDEX Edit controls that exist in both modes.
    bool_params = {k: v for k, v in fixed_params.items() if isinstance(v, bool)}
    str_params  = {k: v for k, v in fixed_params.items() if isinstance(v, str)}
    num_params  = {k: v for k, v in fixed_params.items()
                   if not isinstance(v, (bool, str))}

    # Set each numeric fixed param via Optimize grid using lo;hi;step format.
    # NT8 requires min;max;increment even for fixed values (e.g. "2;2;1" not "2").
    # Rebuild grid_map before each to get fresh element refs after WPF refresh.
    for name, value in num_params.items():
        grid_map = _build_opt_grid_map(sa)
        _set_range_in_grid(grid_map, name, value, value, 1, param_display_names)

    # String params via PDEX Edit controls (always present, IValueProvider works).
    for name, value in str_params.items():
        set_edit(sa, f"{pfx}_{name}", value, warn=False)
        print(f"  Fixed str param '{name}' = {value}")
    for name, value in bool_params.items():
        set_checkbox(sa, f"{pfx}_{name}", value)

    # Set Range params (ORMinutes, TpMultiple) — final grid_map build.
    grid_map = _build_opt_grid_map(sa)
    print(f"  Optimize grid map: {list(grid_map.keys())}")
    for name, range_spec in param_ranges.items():
        if isinstance(range_spec, dict):
            lo   = range_spec["min"]
            hi   = range_spec["max"]
            step = range_spec["step"]
        elif isinstance(range_spec, list):
            if not range_spec:
                continue
            lo   = range_spec[0]
            hi   = range_spec[-1]
            step = round(range_spec[1] - range_spec[0], 8) if len(range_spec) > 1 else 1
        else:
            lo = hi = range_spec
            step = 1
        _set_range_in_grid(grid_map, name, lo, hi, step, param_display_names)

    _pct(30, "Starting native optimization")

    click_time = time.time()
    try:
        run_btn = sa.child_window(auto_id="Run", control_type="Button")
        run_btn.click_input()
        print("  Optimization Run clicked. Waiting for all combos...")
    except Exception as e:
        print(f"  ERROR clicking Run: {e}")
        sys.exit(1)

    _pct(35, "Optimization running")

    # Optimize mode: NT8 shows Abort button during run (Run button disappears)
    finished = wait_for_run_complete(sa, timeout=_OPT_TIMEOUT, use_abort_btn=True)
    if not finished:
        print(f"  ERROR: Optimization timed out after {_OPT_TIMEOUT}s")
        sys.exit(1)

    elapsed = round(time.time() - click_time, 1)
    print(f"  Optimization finished in {elapsed}s")
    _pct(80, "Exporting optimization results")

    param_names = set(param_ranges.keys())
    combos = _export_optimization_results(sa, job_id, param_names)

    if not combos:
        print("  ERROR: Could not parse optimization results from NT8 CSV export")
        sys.exit(1)

    out_dir = NT8_DOCS / "lab_results" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "job_id":         job_id,
        "strategy_class": strategy,
        "instrument":     instr,
        "combos":         combos,
        "combo_count":    len(combos),
        "elapsed_sec":    elapsed,
        "completed_at":   datetime.now().isoformat(),
    }
    (out_dir / "native_opt_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"  Native opt result written: {len(combos)} combos in {elapsed}s")
    _pct(100, f"Complete — {len(combos)} combos")


def _parse_walkforward_csv(csv_path: str) -> list[dict]:
    """
    Parse NT8 Walk Forward results CSV.

    NT8 WF export format (right-click → Export on the Walk-Forward Analyzer tab):
      Columns typically include: Period type, Net profit, Profit factor,
                                 Max. drawdown, Total # of trades, Percent profitable
      Row values: "In-Sample 1", "Out-Of-Sample 1", "In-Sample 2", etc.

    Returns list of {"type": "is"|"oos", "window": int, "net_pnl": ..., ...}.
    """
    import csv as csv_mod
    import re

    _KPI_MAP = {
        "total net profit": "net_pnl",
        "net profit":       "net_pnl",
        "profit factor":    "profit_factor",
        "max. drawdown":    "max_drawdown",
        "max drawdown":     "max_drawdown",
        "total # of trades": "trade_count",
        "# trades":          "trade_count",
        "percent profitable": "win_rate",
        "% profitable":       "win_rate",
    }

    def _coerce(s: str):
        s = s.strip()
        try:
            return float(s.replace(",", "").replace("$", "").replace("%", ""))
        except ValueError:
            return s

    windows = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            headers_lower = {k.strip().lower(): k for k in (reader.fieldnames or [])}
            for row in reader:
                # Identify period column — usually first column
                period_val = ""
                for col in (reader.fieldnames or []):
                    v = row.get(col, "").strip()
                    if re.search(r"(in.?sample|out.?of.?sample|in-sample|out-sample)", v, re.I):
                        period_val = v
                        break
                if not period_val:
                    continue

                period_lower = period_val.lower()
                is_in_sample = "in" in period_lower and "out" not in period_lower
                m = re.search(r"\d+", period_val)
                window_num = int(m.group()) if m else 0

                entry: dict = {
                    "type":   "is" if is_in_sample else "oos",
                    "window": window_num,
                }
                for col_lower, col_orig in headers_lower.items():
                    kpi = _KPI_MAP.get(col_lower)
                    if kpi:
                        v = _coerce(row.get(col_orig, ""))
                        if isinstance(v, float):
                            if kpi == "win_rate" and v > 1.0:
                                v = round(v / 100.0, 4)
                            if kpi == "max_drawdown":
                                v = abs(v)
                            entry[kpi] = round(v, 4)
                windows.append(entry)
    except Exception as e:
        print(f"  [wf-export] CSV parse error: {e}")

    return windows


def run_native_walkforward_mode(job_id: str, spec: dict):
    """
    Walk Forward mode: run NT8's Strategy Analyzer in Walk Forward mode with fixed params.

    Sets all strategy params as single-value ranges (value;value;1) so NT8 performs
    no re-optimization — the fixed winner params are tested across each IS/OOS window.
    One data load, all windows processed natively.

    NOTE: WF-specific auto_ids (OutOfSampleIterations, OutOfSamplePercentage) were derived
    from NT8 SA naming conventions and MUST be validated on VPS before relying on them.
    If set_edit returns False for these, NT8 uses its defaults (5 periods, 30% OOS).

    Writes native_wf_result.json to lab_results/<job_id>/ on success.
    Exits non-zero on failure so nt8_agent.py classifies the run correctly.

    spec fields:
        strategy_class   str
        instrument       str
        bar_type         str
        bar_value        int
        start_date       str   YYYY-MM-DD
        end_date         str   YYYY-MM-DD
        commission_per_side  float
        slippage_ticks   int
        params           dict  {name: value}  — ALL strategy params, fixed
        wf_windows       int   (default 5)
        oos_pct          int   (default 30)
        param_display_names  dict (optional)
    """
    strategy           = spec["strategy_class"]
    instr              = spec["instrument"]
    all_params         = spec.get("params", {})
    wf_windows         = int(spec.get("wf_windows", 5))
    oos_pct            = int(spec.get("oos_pct", 30))
    param_display_names = spec.get("param_display_names", {})

    print(f"JOB {job_id}: native walk-forward {strategy} on {instr}  windows={wf_windows}  oos={oos_pct}%")
    _pct(10, "Connecting to NT8")

    app = connect_nt8()
    sa  = find_strategy_analyzer(app)
    _pct(20, "Selecting strategy")

    # Select strategy first — property grid is not live until a strategy is loaded.
    if not select_strategy(sa, strategy):
        print(f"  ERROR: Strategy '{strategy}' not found in NT8 — is it compiled?")
        sys.exit(1)
    time.sleep(3.0)

    # Must set WalkForward mode after strategy load; hard-fails if it can't be set.
    try:
        _set_backtest_type(sa, "WalkForward")
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    _pct(25, "Configuring walk-forward parameters")

    pfx = f"{strategy}PropertyGridEditorPDEX"

    # Set WF window count and OOS %. These auto_ids follow the SA naming convention but
    # must be verified on VPS — if they don't resolve, NT8 uses its defaults.
    _WF_ITERATIONS_AID  = "StrategyAnalyzerTabPropertiesPropertyGridEditorOutOfSampleIterations"
    _WF_OOS_PCT_AID     = "StrategyAnalyzerTabPropertiesPropertyGridEditorOutOfSamplePercentage"
    if not set_edit(sa, _WF_ITERATIONS_AID, wf_windows, warn=False):
        print(f"  WARNING: WF iterations auto_id not found — using NT8 default")
    if not set_edit(sa, _WF_OOS_PCT_AID, oos_pct, warn=False):
        print(f"  WARNING: WF OOS % auto_id not found — using NT8 default")

    # Separate params by type (same as optimize mode)
    bool_params = {k: v for k, v in all_params.items() if isinstance(v, bool)}
    str_params  = {k: v for k, v in all_params.items() if isinstance(v, str)}
    num_params  = {k: v for k, v in all_params.items() if not isinstance(v, (bool, str))}

    # All numeric params as single-value ranges (value;value;1) — no re-optimization in IS.
    for name, value in num_params.items():
        grid_map = _build_opt_grid_map(sa)
        _set_range_in_grid(grid_map, name, value, value, 1, param_display_names)

    for name, value in str_params.items():
        set_edit(sa, f"{pfx}_{name}", value, warn=False)
    for name, value in bool_params.items():
        set_checkbox(sa, f"{pfx}_{name}", value)

    _pct(30, "Starting walk-forward run")

    click_time = time.time()
    try:
        run_btn = sa.child_window(auto_id="Run", control_type="Button")
        run_btn.click_input()
        print(f"  Walk Forward Run clicked. windows={wf_windows}  oos={oos_pct}%")
    except Exception as e:
        print(f"  ERROR clicking Run: {e}")
        sys.exit(1)

    _pct(35, "Walk forward running")

    finished = wait_for_run_complete(sa, timeout=_OPT_TIMEOUT, use_abort_btn=True)
    if not finished:
        print(f"  ERROR: Walk Forward timed out after {_OPT_TIMEOUT}s")
        sys.exit(1)

    elapsed = round(time.time() - click_time, 1)
    print(f"  Walk Forward finished in {elapsed}s")
    _pct(80, "Exporting walk-forward results")

    # Export using the same right-click mechanism as optimize mode.
    # Exports from the Walk-Forward Analyzer results grid.
    from pywinauto import mouse as _mouse, Desktop
    import shutil

    out_dir = NT8_DOCS / "lab_results" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    dt = Desktop(backend="uia")
    _dismiss_dialog(dt)
    time.sleep(0.1)

    try:
        sa.restore()
        time.sleep(0.3)
    except Exception:
        pass

    sa_rect = sa.rectangle()
    sa_w    = sa_rect.right  - sa_rect.left
    sa_h    = sa_rect.bottom - sa_rect.top
    rc_x    = sa_rect.left + int(sa_w * 0.25)
    rc_y    = sa_rect.top  + int(sa_h * 0.05)

    nt8           = sa.top_level_parent()
    export_coords = None

    _mouse.right_click(coords=(rc_x, rc_y))
    time.sleep(0.5)
    menu_items_found = []
    for el in nt8.descendants():
        txt = (el.window_text() or "").strip()
        ct  = str(getattr(el.element_info, "control_type", ""))
        if ct == "MenuItem" and txt:
            r = el.rectangle()
            menu_items_found.append(f"{txt}@{r.width()}x{r.height()}")
            if txt.startswith("Export") and r.width() > 5 and export_coords is None:
                export_coords = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)

    print(f"  [wf-export] Menu items found: {menu_items_found}")
    if export_coords is None:
        print("  [wf-export] Export menu item not found")
        send_keys("{ESC}")
        sys.exit(1)

    _mouse.right_click(coords=(rc_x, rc_y))
    time.sleep(0.4)
    _mouse.click(coords=export_coords)
    time.sleep(0.8)
    send_keys("{ENTER}")
    time.sleep(0.3)
    send_keys("{ENTER}")
    time.sleep(1.0)
    _dismiss_dialog(dt)

    docs   = Path.home() / "Documents"
    cutoff = time.time() - 30
    csvs   = [p for p in docs.glob("NinjaTrader Grid*.csv") if p.stat().st_mtime >= cutoff]
    if not csvs:
        csvs = sorted(docs.glob("NinjaTrader Grid*.csv"),
                      key=lambda p: p.stat().st_mtime, reverse=True)[:1]

    if not csvs:
        print("  [wf-export] No CSV found after walk-forward export")
        sys.exit(1)

    csv_path = max(csvs, key=lambda p: p.stat().st_mtime)
    dest     = out_dir / "wf_results.csv"
    shutil.copy(str(csv_path), str(dest))
    print(f"  [wf-export] CSV saved to {dest.name}")

    windows = _parse_walkforward_csv(str(csv_path))
    if not windows:
        print("  ERROR: Could not parse walk-forward results from NT8 CSV")
        sys.exit(1)

    result = {
        "job_id":         job_id,
        "strategy_class": strategy,
        "instrument":     instr,
        "wf_windows":     wf_windows,
        "oos_pct":        oos_pct,
        "windows":        windows,
        "elapsed_sec":    elapsed,
        "completed_at":   datetime.now().isoformat(),
    }
    (out_dir / "native_wf_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"  Native WF result written: {len(windows)} period rows in {elapsed}s")
    _pct(100, f"Complete — {len(windows)} periods")


def configure_from_spec(sa, spec: dict):
    """Configure Strategy Analyzer from a lab job spec (firm-agnostic)."""
    strategy = spec["strategy_class"]
    pfx      = f"{strategy}PropertyGridEditorPDEX"

    # Strategy switch first — property grid is not live until a strategy is loaded.
    if not select_strategy(sa, strategy):
        raise RuntimeError(f"Strategy '{strategy}' not found in NT8 — is it compiled?")
    time.sleep(2.0)

    # Must set Backtest mode after strategy load; hard-fails if it can't be set.
    _set_backtest_type(sa, "Backtest")

    set_instrument(sa, spec["instrument"])
    set_edit(sa, "BarsPeriodPropertyGridEditorPDEX_PDEX_Value", spec.get("bar_value", 5))
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_From",  _nt8_date(spec["start_date"]))
    set_edit(sa, "NinjaScriptBasePropertyGridEditorPDEX_To",    _nt8_date(spec["end_date"]))
    set_edit(sa, "StrategyBasePropertyGridEditorPDEX_Slippage", spec.get("slippage_ticks", 1))

    # Prop-firm SA params: set permissive so strategy trades freely;
    # actual pass/fail is evaluated post-run against firm rules by the backend.
    set_edit(sa, f"{pfx}_AccountSize",       100000,                              warn=False)
    set_edit(sa, f"{pfx}_CommissionPerSide", spec.get("commission_per_side", 2.25), warn=False)
    set_edit(sa, f"{pfx}_MaxDailyLoss",      99999,                               warn=False)
    set_edit(sa, f"{pfx}_DailyHaltFraction", 1.0,                                 warn=False)
    set_edit(sa, f"{pfx}_RiskPct",           2.0,                                 warn=False)

    # Strategy-specific params
    for key, value in spec.get("params", {}).items():
        aid = f"{pfx}_{key}"
        if not set_edit(sa, aid, value, warn=False):
            if not set_checkbox(sa, aid, value):
                set_combo(sa, aid, value)


# ── Trade export (pywinauto) ──────────────────────────────────────────────────

def _dump_controls(win, depth: int = 5) -> None:
    """Print control identifiers for a window — used for debugging NT8 UI structure."""
    try:
        print(f"  [debug] Controls (depth={depth}):")
        win.print_control_identifiers(depth=depth)
    except Exception as e:
        print(f"  [debug] Could not print controls: {e}")


def _parse_nt8_date(raw: str):
    """Parse NT8 date strings ('M/D/YYYY H:MM:SS', etc.) → 'YYYY-MM-DD' or None."""
    if not raw:
        return None
    for fmt in [
        "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",       "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",    "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try stripping trailing AM/PM from the date part only
    parts = raw.strip().split()
    if parts:
        for fmt in ["%m/%d/%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(parts[0], fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _parse_dollar(s: str) -> float:
    """Parse NT8 dollar strings: '$594.00' → 594.0, '($2448.00)' → -2448.0."""
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        try:
            return -float(s[1:-1])
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_trades_csv(csv_path: str) -> tuple:
    """
    Parse NT8-exported trades CSV → (equity_curve, daily_pnl).
    Uses 'Cum. net profit' for equity (authoritative cumulative) with
    per-trade fields (direction, profit, exit_name) for frontend charts.
    Returns ([], []) on failure.
    """
    import csv as csv_mod

    CUM_COLS  = ["Cum. net profit", "Cumulative Net Profit"]
    PNL_COLS  = ["Profit", "Net Profit", "P&L", "Net P&L"]
    DATE_COLS = ["Exit time", "Exit Time", "ExitTime", "Close Time", "Exit Date"]
    DIR_COLS  = ["Market pos.", "Market Pos", "Direction", "Side"]
    NAME_COLS = ["Exit name", "Exit Name", "ExitName"]

    equity_curve: list = []
    daily_map: dict    = {}

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader   = csv_mod.DictReader(f)
            fields   = reader.fieldnames or []
            cum_col  = next((c for c in CUM_COLS  if c in fields), None)
            pnl_col  = next((c for c in PNL_COLS  if c in fields), None)
            date_col = next((c for c in DATE_COLS if c in fields), None)
            dir_col  = next((c for c in DIR_COLS  if c in fields), None)
            name_col = next((c for c in NAME_COLS if c in fields), None)

            if cum_col is None and pnl_col is None:
                print(f"  [trades] No P&L column found. Available: {fields}")
                return [], []

            running = 0.0
            for i, row in enumerate(reader):
                trade_num = i + 1
                pnl   = _parse_dollar(row.get(pnl_col,  "0")) if pnl_col  else 0.0
                cum   = _parse_dollar(row.get(cum_col,  "0")) if cum_col  else None
                equity = round(cum, 2) if cum is not None else round(running + pnl, 2)
                if cum is None:
                    running += pnl

                direction = (row.get(dir_col,  "") or "").strip() if dir_col  else None
                exit_name = (row.get(name_col, "") or "").strip() if name_col else None
                date_str  = _parse_nt8_date(row.get(date_col, "") if date_col else "")

                equity_curve.append({
                    "index":     trade_num,
                    "equity":    equity,
                    "date":      date_str,
                    "direction": direction or None,
                    "profit":    round(pnl, 2),
                    "exit_name": exit_name or None,
                })

                if date_str:
                    daily_map[date_str] = round(daily_map.get(date_str, 0.0) + pnl, 2)

    except Exception as e:
        print(f"  [trades] CSV parse error: {e}")
        return [], []

    daily_pnl = [{"date": d, "pnl": v} for d, v in sorted(daily_map.items())]
    print(f"  [trades] Parsed {len(equity_curve)} trades, {len(daily_pnl)} trading days")
    return equity_curve, daily_pnl


def _try_export_trades(sa, job_id: str) -> tuple:
    """
    Export trades from NT8 Strategy Analyzer using two-pass right-click.

    NT8 uses WPF — context menus are not Win32 #32768 and UIA scanning of
    nt8.descendants() dismisses open WPF popups before click_input() can fire.
    Two-pass approach: pass 1 opens the menu and scans for Export's screen
    coordinates (menu closes during scan — that's fine); pass 2 right-clicks
    again and immediately clicks the cached position.

    Returns (equity_curve, daily_pnl) — both [] on any failure.
    """
    from pywinauto import mouse as _mouse, Desktop
    import shutil

    out_dir = NT8_DOCS / "lab_results" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    dt = Desktop(backend="uia")

    def _dismiss(desktop):
        for title in ["Export As", "Confirm Save As", "Confirm"]:
            try:
                w = desktop.window(title=title)
                if w.exists(timeout=0.1):
                    for btn in ["Cancel", "No", "OK"]:
                        try:
                            w.child_window(title=btn, control_type="Button").click_input()
                            return
                        except Exception:
                            pass
                    w.close()
            except Exception:
                pass

    # Dismiss any leftover Export As dialog from a previous run
    _dismiss(dt)
    time.sleep(0.1)

    # Switch Display to Trades
    try:
        sa.child_window(auto_id="dmsDisplay").click_input()
        time.sleep(0.5)
        sa.child_window(title="Trades", control_type="MenuItem", found_index=0).click_input()
        time.sleep(0.3)
        print("  [trades] Switched Display to 'Trades'")
    except Exception as e:
        print(f"  [trades] Display switch failed: {e}")
        return [], []

    # Restore if minimized — minimized windows have invalid screen rect
    try:
        sa.restore()
        time.sleep(0.3)
    except Exception:
        pass

    # Right-click target: center-left of SA window, lower half (data area)
    sa_rect = sa.rectangle()
    rc_x = sa_rect.left + (sa_rect.right - sa_rect.left) // 4
    rc_y = sa_rect.top + int((sa_rect.bottom - sa_rect.top) * 0.55)

    # Pass 1: open context menu, scan NT8 tree for Export menu item coordinates
    nt8 = sa.top_level_parent()
    export_coords = None
    _mouse.right_click(coords=(rc_x, rc_y))
    time.sleep(0.3)
    for el in nt8.descendants():
        txt = (el.window_text() or "").strip()
        ct  = str(getattr(el.element_info, "control_type", ""))
        if ct == "MenuItem" and txt.startswith("Export"):
            r = el.rectangle()
            if r.width() > 5:
                export_coords = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                break

    if export_coords is None:
        print("  [trades] Export menu item not found in NT8 UIA tree")
        send_keys("{ESC}")
        return [], []

    # Pass 2: right-click again, immediately click Export at cached coords
    _mouse.right_click(coords=(rc_x, rc_y))
    time.sleep(0.4)
    _mouse.click(coords=export_coords)
    time.sleep(0.8)

    # Enter twice: accept default filename, confirm overwrite
    send_keys("{ENTER}")
    time.sleep(0.3)
    send_keys("{ENTER}")
    time.sleep(1.0)

    _dismiss(dt)

    # Find the CSV NT8 just wrote (default name: "NinjaTrader Grid *.csv" in Documents)
    docs = Path.home() / "Documents"
    cutoff = time.time() - 30
    csvs = [p for p in docs.glob("NinjaTrader Grid*.csv") if p.stat().st_mtime >= cutoff]
    if not csvs:
        # Fallback: newest regardless of age
        csvs = sorted(docs.glob("NinjaTrader Grid*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:1]

    if not csvs:
        print("  [trades] No CSV found after export")
        return [], []

    csv_path = max(csvs, key=lambda p: p.stat().st_mtime)
    shutil.copy(str(csv_path), str(out_dir / "trades.csv"))
    return _parse_trades_csv(str(csv_path))


def write_job_result(job_id: str, spec: dict, kpis: dict,
                     equity_curve: list | None = None,
                     daily_pnl: list | None = None):
    out_dir = NT8_DOCS / "lab_results" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "job_id":         job_id,
        "strategy_class": spec["strategy_class"],
        "instrument":     spec["instrument"],
        "kpis": {
            "net_pnl":                kpis.get("net_pnl"),
            "max_drawdown":           kpis.get("max_drawdown"),
            "profit_factor":          kpis.get("profit_factor"),
            "win_rate":               kpis.get("win_rate"),
            "win_count":              kpis.get("win_count"),
            "trade_count":            kpis.get("trade_count"),
            "sharpe":                 kpis.get("sharpe"),
            "sortino":                kpis.get("sortino"),
            "cagr":                   None,
            "avg_win":                kpis.get("avg_win"),
            "avg_loss":               kpis.get("avg_loss"),
            "avg_trade_duration_min": kpis.get("avg_trade_duration_min"),
            "worst_day_pnl":          None,
            "worst_losing_streak":    kpis.get("worst_losing_streak"),
        },
        "equity_curve": equity_curve or [],
        "daily_pnl":    daily_pnl    or [],
        "completed_at": datetime.now().isoformat(),
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"  Result written to {out_dir / 'result.json'}")


def run_job_mode(job_id: str, spec_path: str):
    """Lab mode: run a single job spec, write result.json, exit 0 on success."""
    with open(spec_path) as f:
        spec = json.load(f)

    strategy = spec["strategy_class"]
    instr    = spec["instrument"]
    print(f"JOB {job_id}: {strategy} on {instr}")
    _pct(10, "Connecting to NT8")

    app = connect_nt8()
    sa  = find_strategy_analyzer(app)
    _pct(20, "Configuring Strategy Analyzer")

    try:
        configure_from_spec(sa, spec)
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)
    time.sleep(1)

    click_time = time.time()
    try:
        run_btn = sa.child_window(auto_id="Run", control_type="Button")
        run_btn.click_input()
        print("  Run clicked.")
    except Exception as e:
        print(f"  ERROR clicking Run: {e}")
        sys.exit(1)

    _pct(30, "Executing Backtest")
    finished = wait_for_run_complete(sa, RUN_TIMEOUT)
    if not finished:
        print(f"  WARNING: Timed out after {RUN_TIMEOUT}s.")
        sys.exit(1)

    _pct(70, "Exporting Trade Data")
    equity_curve, daily_pnl = _try_export_trades(sa, job_id)
    if equity_curve:
        print(f"  Trade export OK: {len(equity_curve)-1} trades, {len(daily_pnl)} days")
    else:
        print("  Trade export unavailable — equity curve will be empty")

    _pct(80, "Reading results")
    # Poll for XML written after this run's click (avoid stale files from earlier today)
    today   = datetime.now().strftime("%Y_%m_%d")
    pattern = str(SA_LOG_DIR / f"@@@{strategy}_{today}_*.xml")
    xml_deadline = time.time() + 60
    while time.time() < xml_deadline:
        if any(os.path.getmtime(f) >= click_time for f in glob.glob(pattern)):
            break
        time.sleep(1)

    result = read_result_from_xml(job_id, strategy, instr, written_after=click_time)
    if result is None:
        print("  ERROR: Could not read result from XML.")
        sys.exit(1)

    kpis = {
        "net_pnl":                result["net_pnl"],
        "max_drawdown":           abs(result["max_drawdown"]),  # ensure positive
        "profit_factor":          result["profit_factor"],
        "win_rate":               result["win_pct"] / 100.0,
        "trade_count":            result["trades"],
        "win_count":              round(result["win_pct"] / 100.0 * result["trades"]),
        "sharpe":                 result.get("sharpe"),
        "sortino":                result.get("sortino"),
        "avg_win":                result.get("avg_win"),
        "avg_loss":               result.get("avg_loss"),
        "avg_trade_duration_min": result.get("avg_trade_duration_min"),
        "worst_losing_streak":    result.get("worst_losing_streak"),
    }
    print(f"  Trades={kpis['trade_count']}  NetPnL={kpis['net_pnl']:.2f}"
          f"  PF={kpis['profit_factor']:.4f}  MaxDD={kpis['max_drawdown']:.2f}")

    write_job_result(job_id, spec, kpis, equity_curve, daily_pnl)
    _pct(100, "Complete")


# ── Legacy mode ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config",   default=DEFAULT_CFG)
    parser.add_argument("--combo",    default=None,
                        help="Run only this combo ID (e.g. ORB_MNQ). Omit to run all.")
    parser.add_argument("--job-id",   default=None, help="Lab mode: job ID")
    parser.add_argument("--job-spec", default=None, help="Lab mode: path to job_spec.json")
    parser.add_argument("--mode",     default=None,
                        help="Runner mode: omit for single-run, 'native-optimize', 'native-walkforward'")
    args = parser.parse_args()

    if args.job_id and args.job_spec:
        with open(args.job_spec) as f:
            spec = json.load(f)
        if args.mode == "native-optimize":
            run_native_optimize_mode(args.job_id, spec)
        elif args.mode == "native-walkforward":
            run_native_walkforward_mode(args.job_id, spec)
        else:
            run_job_mode(args.job_id, args.job_spec)
        return

    # Legacy config-driven mode
    cfg    = load_config(args.config)
    combos = cfg["combos"]
    gp     = cfg["global_params"]

    if args.combo:
        combos = [c for c in combos if c["id"] == args.combo]
        if not combos:
            valid = ", ".join(c["id"] for c in cfg["combos"])
            print(f"ERROR: combo '{args.combo}' not found. Valid IDs: {valid}")
            sys.exit(1)
        print(f"Running single combo: {args.combo}")

    app = connect_nt8()

    total   = len(combos)
    results = []
    for i, combo in enumerate(combos, 1):
        try:
            result = run_combo(app, combo, gp, i, total)
        except BaseException as e:
            print(f"  ERROR on combo {combo['id']}: {e} — skipping")
            result = None
        if result:
            results.append(result)

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
