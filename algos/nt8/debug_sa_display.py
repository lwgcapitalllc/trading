"""
Standalone SA diagnostic.
Run on VPS while NT8 is open with the Strategy Analyzer visible.
Usage: python debug_sa_display.py
Dumps the full SA UIA tree, then probes every unnamed ComboBox.
"""
import time
import sys

try:
    from pywinauto import Desktop
except ImportError:
    print("ERROR: pywinauto not installed")
    sys.exit(1)


def find_nt8_and_sa():
    dt = Desktop(backend="uia")
    nt8_wins = [w for w in dt.windows() if "NinjaTrader" in (w.window_text() or "")]
    if not nt8_wins:
        print("ERROR: No NinjaTrader window found — is NT8 running?")
        sys.exit(1)
    nt8_win = nt8_wins[0]
    print(f"NT8 window : '{nt8_win.window_text()}'")

    sa = None
    for desc in nt8_win.descendants(control_type="Pane"):
        try:
            nm = getattr(desc.element_info, "name", "") or ""
            if "Strategy Analyzer" in nm or "Strategy Analyzer" in (desc.window_text() or ""):
                sa = desc
                break
        except Exception:
            pass

    if sa is None:
        # Fallback: look for it by window text in all descendants
        for desc in nt8_win.descendants():
            try:
                if "Strategy Analyzer" in (desc.window_text() or ""):
                    sa = desc
                    break
            except Exception:
                pass

    if sa is None:
        print("ERROR: Strategy Analyzer pane not found — is SA open?")
        sys.exit(1)

    print(f"SA found   : ctrl_type={getattr(sa.element_info, 'control_type', '?')}  text='{sa.window_text()}'")
    return dt, nt8_win, sa


def dump_tree(label, root, max_depth=None):
    print(f"\n{'='*60}")
    print(f"  TREE: {label}")
    print(f"{'='*60}")
    try:
        for desc in root.descendants():
            try:
                txt = (desc.window_text() or "").strip()
                aid = (desc.automation_id() or "").strip()
                ct  = str(getattr(desc.element_info, "control_type", "?"))
                nm  = (getattr(desc.element_info, "name", "") or "").strip()
                if txt or aid or nm:
                    print(f"  {ct:<28} aid={aid!r:<52} text={txt!r}  name={nm!r}")
            except Exception:
                pass
    except Exception as e:
        print(f"  dump failed: {e}")


def probe_combos(dt, nt8_win, sa):
    print(f"\n{'='*60}")
    print("  UNNAMED COMBOBOX PROBE")
    print(f"{'='*60}")

    unnamed = [
        c for c in sa.descendants(control_type="ComboBox")
        if not (c.automation_id() or "").strip()
    ]
    print(f"Found {len(unnamed)} unnamed ComboBox(es) in SA subtree\n")

    for i, combo in enumerate(unnamed):
        print(f"--- Combo #{i} ---")
        try:
            rect = combo.rectangle()
            print(f"  rect : {rect}")
        except Exception:
            pass

        wins_before = {w.handle for w in dt.windows()}

        try:
            combo.click_input()
        except Exception as e:
            print(f"  click_input failed: {e}")
            continue

        time.sleep(1.5)

        # --- Search SA subtree ---
        print("  Searching SA + NT8 subtree for any new text items:")
        for root_label, root in [("sa", sa), ("nt8", nt8_win)]:
            try:
                for desc in root.descendants():
                    try:
                        txt = (desc.window_text() or "").strip()
                        if txt:
                            ct  = str(getattr(desc.element_info, "control_type", "?"))
                            aid = (desc.automation_id() or "").strip()
                            nm  = (getattr(desc.element_info, "name", "") or "").strip()
                            print(f"    [{root_label}] {ct:<25} aid={aid!r:<40} text={txt!r}  name={nm!r}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  scan {root_label} error: {e}")

        # --- New top-level windows ---
        wins_after  = {w.handle for w in dt.windows()}
        new_handles = wins_after - wins_before
        print(f"  New top-level windows: {len(new_handles)}")
        for hwnd in new_handles:
            try:
                popup = dt.window(handle=hwnd)
                ptxt  = popup.window_text() or ""
                ptype = str(getattr(popup.element_info, "control_type", "?"))
                print(f"  POPUP title={ptxt!r} type={ptype}")
                for desc in popup.descendants():
                    try:
                        txt = (desc.window_text() or "").strip()
                        ct  = str(getattr(desc.element_info, "control_type", "?"))
                        aid = (desc.automation_id() or "").strip()
                        nm  = (getattr(desc.element_info, "name", "") or "").strip()
                        if txt:
                            print(f"    {ct:<25} aid={aid!r:<40} text={txt!r}  name={nm!r}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  popup read error: {e}")

        # Close without selecting — click again to toggle
        try:
            combo.click_input()
        except Exception:
            pass
        time.sleep(0.5)
        print()


def main():
    print("=== SA Display Diagnostic ===")
    dt, nt8_win, sa = find_nt8_and_sa()

    dump_tree("SA subtree", sa)
    probe_combos(dt, nt8_win, sa)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
