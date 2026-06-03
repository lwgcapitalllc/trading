"""
VPS Compile Runner — triggered by vps_agent.py via subprocess.

Opens the NT8 NinjaScript Editor (or reuses an existing one), presses F5
to compile all strategies, and detects success by watching
NinjaTrader.Custom.dll modification time.

Exit codes:
    0 — compile succeeded (dll updated within timeout)
    1 — compile failed (dll not updated, likely build errors)
    2 — setup error (couldn't reach NT8 window)

Output lines:
    STATUS:success
    STATUS:failed
    STATUS:error
    ERROR:<message>
    LOG:<message>
"""

import sys
import time
from pathlib import Path

try:
    from pywinauto import Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("ERROR:pywinauto not installed — pip install pywinauto comtypes")
    sys.exit(2)

NT8_DOCS       = Path.home() / "Documents" / "NinjaTrader 8"
NT8_CUSTOM_DLL = NT8_DOCS / "bin" / "Custom" / "NinjaTrader.Custom.dll"
TIMEOUT_SECS   = 90


def log(msg: str):
    print(f"LOG:{msg}", flush=True)


def _find_cc_hwnd() -> int | None:
    """Find the NT8 Control Center HWND via Win32 EnumWindows.

    The Control Center is a WPF docked panel that appears in Win32's window
    list but NOT as a top-level UIA window. We locate it by HWND, then wrap
    it in pywinauto for child interaction.
    """
    import ctypes
    found: list[int] = []
    buf = ctypes.create_unicode_buffer(512)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _):
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        if "Control Center" in buf.value:
            found.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(_cb, None)
    return found[0] if found else None


def open_ns_editor(dt) -> object:
    """Return the NinjaScript Editor window, opening it if necessary."""
    # Already open?
    try:
        ed = dt.window(title_re=".*NinjaScript Editor.*")
        ed.wait("visible", timeout=2)
        log("NinjaScript Editor already open")
        return ed
    except Exception:
        pass

    log("Opening NinjaScript Editor via NT8 Control Center New menu...")
    cc_hwnd = _find_cc_hwnd()
    if cc_hwnd is None:
        raise RuntimeError("NT8 Control Center window not found via Win32 — is NT8 running?")

    log(f"Control Center HWND: {cc_hwnd}")
    cc = dt.window(handle=cc_hwnd)
    cc.set_focus()
    time.sleep(0.5)
    cc.child_window(title="New", control_type="MenuItem").click_input()
    time.sleep(0.8)
    dt.window(title="NinjaScript Editor", control_type="MenuItem").click_input()
    time.sleep(3.0)

    ed = dt.window(title_re=".*NinjaScript Editor.*")
    ed.wait("visible", timeout=10)
    log("NinjaScript Editor opened")
    return ed


def main():
    pre_mtime = NT8_CUSTOM_DLL.stat().st_mtime if NT8_CUSTOM_DLL.exists() else 0
    log(f"Pre-compile dll mtime: {pre_mtime}")

    try:
        dt = Desktop(backend="uia")
        ed = open_ns_editor(dt)
        ed.set_focus()
        time.sleep(0.5)
        send_keys("{F5}")
        log("F5 sent to NinjaScript Editor — waiting for dll update...")
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        print("STATUS:error", flush=True)
        sys.exit(2)

    deadline = time.time() + TIMEOUT_SECS
    while time.time() < deadline:
        time.sleep(3)
        if NT8_CUSTOM_DLL.exists() and NT8_CUSTOM_DLL.stat().st_mtime > pre_mtime:
            elapsed = round(time.time() - (deadline - TIMEOUT_SECS), 1)
            log(f"dll updated — compile succeeded in ~{elapsed}s")
            print("STATUS:success", flush=True)
            sys.exit(0)

    print(
        "ERROR:Compile did not complete within 90 s. "
        "Check the NinjaScript Editor output panel for errors.",
        flush=True,
    )
    print("STATUS:failed", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
