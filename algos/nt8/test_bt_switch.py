"""
Debug script: test switching NT8 SA BacktestType through all three scenarios.

NT8 display name    →  UIA internal name  (what pywinauto must use)
─────────────────────────────────────────────────────────────────────
Backtest            →  Backtest
Optimization        →  Optimize
Walk Forward Opt.   →  WalkForward

Run on VPS:
    python C:\trading\algos\nt8\test_bt_switch.py
Or via agent endpoint:
    curl "http://localhost:8765/test-bt-switch?value=Optimize"
"""
import sys
import time

try:
    from pywinauto import Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("ERROR: pip install pywinauto comtypes")
    sys.exit(1)

BT_AID   = "StrategyAnalyzerTabPropertiesPropertyGridEditorBacktestType"
BT_ORDER = ["Backtest", "Optimize", "WalkForward", "WalkForwardAnchored", "MultiObjective", "AiGenerate"]

# The three scenarios the runner needs to cover.
# UIA name  →  NT8 display name
SCENARIOS = [
    ("Backtest",     "Backtest"),
    ("Optimize",     "Optimization"),
    ("WalkForward",  "Walk Forward Optimization"),
]


def find_sa():
    sa = Desktop(backend="uia").window(title_re=".*Strategy Analyzer.*")
    sa.wait("visible", timeout=10)
    return sa


def discover_items(ctrl):
    """Expand and list all items via ctrl.descendants (works from agent context)."""
    try:
        ctrl.expand()
        time.sleep(0.4)
        items = [el.window_text() for el in ctrl.descendants(control_type="ListItem")]
        try:
            ctrl.collapse()
        except Exception:
            pass
        return items
    except Exception as e:
        return [f"(error: {e})"]


def switch_to(ctrl, uia_name):
    """
    Two-tier switch — mirrors runner's _set_backtest_type exactly.
    Returns (success: bool, method: str, error: str)
    """
    idx = BT_ORDER.index(uia_name)

    # Tier 1: select() — works from Backtest state
    try:
        ctrl.select(uia_name)
        return True, "select()", ""
    except Exception as e:
        tier1_err = str(e)

    # Tier 2: send_keys — works when ctrl.* fails (post-Optimize state)
    try:
        ctrl.set_focus()
        time.sleep(0.2)
        send_keys('{F4}')
        time.sleep(0.3)
        send_keys('{HOME}')
        time.sleep(0.1)
        for _ in range(idx):
            send_keys('{DOWN}')
            time.sleep(0.08)
        send_keys('{ENTER}')
        time.sleep(0.3)
        return True, "send_keys", ""
    except Exception as e:
        return False, "none", f"T1={tier1_err}  T2={e}"


def main():
    print("=" * 60)
    print("NT8 BacktestType switch test — 3 scenarios")
    print("=" * 60)

    sa   = find_sa()
    ctrl = sa.child_window(auto_id=BT_AID, control_type="ComboBox")

    if not ctrl.exists(timeout=2.0):
        print("FATAL: BacktestType combo not found")
        sys.exit(1)

    print(f"\nItem discovery (via ctrl.expand + descendants):")
    items = discover_items(ctrl)
    print(f"  {items}")
    print()

    results = []
    for uia_name, display_name in SCENARIOS:
        print(f"  Switching to '{display_name}' (UIA: '{uia_name}') ...", end=" ", flush=True)
        ok, method, err = switch_to(ctrl, uia_name)
        if ok:
            print(f"OK via {method}  — CHECK SA: should show '{display_name}'")
        else:
            print(f"FAILED  ({err})")
        results.append((display_name, uia_name, ok, method))
        time.sleep(1.0)  # pause between switches so each is visually observable

    print()
    print("Summary:")
    for display_name, uia_name, ok, method in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}]  {display_name!r:30s}  method={method}")


if __name__ == "__main__":
    main()
