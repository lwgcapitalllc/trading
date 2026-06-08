"""
Debug script: try every known method to switch NT8 SA BacktestType.
Run on VPS: python C:\trading\algos\nt8\test_bt_switch.py [Backtest|Optimize|WalkForward]
"""
import sys
import time

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("ERROR: pip install pywinauto comtypes")
    sys.exit(1)

BT_AID = "StrategyAnalyzerTabPropertiesPropertyGridEditorBacktestType"
BT_ORDER = ["Backtest", "Optimize", "WalkForward", "WalkForwardAnchored", "MultiObjective", "AiGenerate"]
TARGET = sys.argv[1] if len(sys.argv) > 1 else "Optimize"


def find_sa():
    sa = Desktop(backend="uia").window(title_re=".*Strategy Analyzer.*")
    sa.wait("visible", timeout=10)
    return sa


def report_current(ctrl):
    print(f"  window_text : {repr(ctrl.window_text())}")
    try:
        print(f"  get_value   : {repr(ctrl.get_value())}")
    except Exception as e:
        print(f"  get_value   : error — {e}")
    try:
        print(f"  selected_text: {repr(ctrl.selected_text())}")
    except Exception as e:
        print(f"  selected_text: error — {e}")


def attempt(label, fn):
    print(f"\n{'='*50}")
    print(f"ATTEMPT: {label}")
    try:
        result = fn()
        if result:
            print(f"  -> RESULT: SUCCESS")
        else:
            print(f"  -> RESULT: returned False")
        return result
    except Exception as e:
        print(f"  -> EXCEPTION: {type(e).__name__}: {e}")
        return False


def main():
    print(f"Target: {TARGET!r}")
    print(f"\nConnecting to SA...")
    sa = find_sa()
    print(f"SA: {repr(sa.window_text())}")

    ctrl = sa.child_window(auto_id=BT_AID, control_type="ComboBox")
    exists = ctrl.exists(timeout=2.0)
    print(f"\nBacktestType combo exists: {exists}")
    if not exists:
        print("FATAL: combo not found")
        sys.exit(1)

    print("Current state:")
    report_current(ctrl)

    # ── 1. select() — used by agent, no expand ──────────────────────────────
    def a1():
        ctrl.select(TARGET)
        return True
    if attempt("ctrl.select(TARGET)", a1):
        print("\nCurrent state after attempt:")
        report_current(ctrl)
        print("\nDONE — select() works.")
        return

    # ── 2. expand + ctrl.descendants ────────────────────────────────────────
    def a2():
        ctrl.expand()
        time.sleep(0.5)
        items = ctrl.descendants(control_type="ListItem")
        print(f"  ctrl.descendants found {len(items)} ListItems: {[i.window_text() for i in items]}")
        for item in items:
            if item.window_text() == TARGET:
                item.click_input()
                time.sleep(0.2)
                return True
        try:
            ctrl.collapse()
        except Exception:
            ctrl.type_keys('{ESC}')
        return False
    if attempt("expand + ctrl.descendants()", a2):
        print("DONE — expand+descendants works.")
        return

    # ── 3. expand + search all top-level windows ─────────────────────────────
    def a3():
        ctrl.expand()
        time.sleep(0.5)
        desk = Desktop(backend="uia")
        wins = desk.windows()
        print(f"  searching {len(wins)} top-level windows...")
        for win in wins:
            try:
                wt = win.window_text()
                items = win.descendants(control_type="ListItem")
                if items:
                    labels = [i.window_text() for i in items]
                    print(f"    win={repr(wt)!r:30s}  ListItems={labels}")
                    for item in items:
                        if item.window_text() == TARGET:
                            item.click_input()
                            time.sleep(0.2)
                            return True
            except Exception:
                pass
        try:
            ctrl.type_keys('{ESC}')
        except Exception:
            pass
        return False
    if attempt("expand + all-windows search", a3):
        print("DONE — all-windows search works.")
        return

    # ── 4. keyboard: F4 + HOME + DOWN×N + ENTER ──────────────────────────────
    def a4():
        idx = BT_ORDER.index(TARGET)
        ctrl.click_input()
        time.sleep(0.2)
        ctrl.type_keys('{F4}')
        time.sleep(0.5)
        items_after_f4 = ctrl.descendants(control_type="ListItem")
        print(f"  after F4: ctrl.descendants = {len(items_after_f4)} items")
        ctrl.type_keys('{HOME}')
        time.sleep(0.15)
        for i in range(idx):
            ctrl.type_keys('{DOWN}')
            time.sleep(0.1)
        ctrl.type_keys('{ENTER}')
        time.sleep(0.3)
        return True  # visual check needed
    if attempt(f"keyboard F4+HOME+{BT_ORDER.index(TARGET)}xDOWN+ENTER", a4):
        print("Keyboard attempt sent — CHECK SA visually to confirm value changed.")
        report_current(ctrl)
        return

    # ── 5. send_keys (system-wide, not to ctrl) ───────────────────────────────
    def a5():
        ctrl.set_focus()
        time.sleep(0.2)
        send_keys('{F4}')
        time.sleep(0.5)
        send_keys('{HOME}')
        time.sleep(0.1)
        idx = BT_ORDER.index(TARGET)
        for _ in range(idx):
            send_keys('{DOWN}')
            time.sleep(0.1)
        send_keys('{ENTER}')
        time.sleep(0.3)
        return True
    if attempt("send_keys F4+HOME+DOWN+ENTER (system-wide)", a5):
        print("send_keys attempt sent — CHECK SA visually.")
        report_current(ctrl)
        return

    print("\n\nALL ATTEMPTS FAILED.")
    print("Final state:")
    report_current(ctrl)


if __name__ == "__main__":
    main()
