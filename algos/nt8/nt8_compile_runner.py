"""
VPS Compile Runner — triggered by nt8_agent.py via subprocess.

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

import re
import sys
import time
from pathlib import Path

try:
    from pywinauto import Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("ERROR:pywinauto not installed — pip install pywinauto comtypes")
    sys.exit(2)

NT8_DOCS = Path.home() / "Documents" / "NinjaTrader 8"
NT8_CUSTOM_DLL = NT8_DOCS / "bin" / "Custom" / "NinjaTrader.Custom.dll"
TIMEOUT_SECS = 90

# NT8 keeps F5 compile errors ONLY in the editor's in-memory error grid — they are
# never written to any trace/log file. The status bar shows this exact string when a
# build is rejected, so it's our reliable, fast "the build failed" signal.
FAIL_MARKER = "must be resolved before compiling"
# Each grid row's Code column is a C# compiler code like CS1001 / CS0246.
CS_RE = re.compile(r"\bCS\d{3,4}\b")


def log(msg: str):
    print(f"LOG:{msg}", flush=True)


def _read_compile_errors(ed) -> tuple[list[str], bool]:
    """Best-effort scrape of the NinjaScript Editor.

    Returns (error_rows, marker_present). `marker_present` is True if NT8 is
    showing the "errors must be resolved" status marker. `error_rows` are
    reconstructed grid rows ("ORB.cs  Identifier expected  CS1001  1  16"),
    best-effort and possibly empty if the UIA layout differs. The caller compares
    the marker before vs after F5 so a stale marker from a previous failed build is
    never mistaken for a fresh one. All scraping is defensive: any failure yields
    ([], False) so the caller falls back to dll-mtime / timeout detection.
    """
    rows: list[str] = []
    marker = False
    try:
        for item in ed.descendants(control_type="DataItem"):
            cells = []
            for c in item.descendants():
                try:
                    txt = c.window_text()
                except Exception:
                    continue
                if txt and txt.strip():
                    cells.append(txt.strip())
            line = "  ".join(cells)
            if CS_RE.search(line):
                rows.append(line)
    except Exception:
        rows = []

    try:
        for d in ed.descendants():
            try:
                txt = d.window_text()
            except Exception:
                continue
            if txt and FAIL_MARKER in txt.lower():
                marker = True
                break
    except Exception:
        pass

    # Dedupe rows, preserve order, cap the volume we ship back.
    seen, deduped = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
        if len(deduped) >= 15:
            break
    return deduped, marker


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

    # "New" is a submenu — use expand() (IExpandCollapseProvider), not invoke().
    cc.child_window(title="New", control_type="MenuItem").expand()
    time.sleep(0.8)

    # After expand(), "NinjaScript Editor" becomes a child of the "New" menu item.
    new_item = cc.child_window(title="New", control_type="MenuItem")
    ns_item = new_item.child_window(title="NinjaScript Editor", control_type="MenuItem")
    if not ns_item.exists(timeout=2):
        raise RuntimeError("NinjaScript Editor menu item not found after expanding New")
    ns_item.invoke()  # leaf item — invoke() works
    time.sleep(3.0)

    ed = dt.window(title_re=".*NinjaScript Editor.*")
    ed.wait("visible", timeout=10)
    log("NinjaScript Editor opened")
    return ed


def main():
    pre_mtime = NT8_CUSTOM_DLL.stat().st_mtime if NT8_CUSTOM_DLL.exists() else 0
    log(f"Pre-compile dll mtime: {pre_mtime}")

    try:
        import ctypes

        dt = Desktop(backend="uia")
        ed = open_ns_editor(dt)
        # Snapshot any pre-existing "errors must be resolved" marker BEFORE we
        # compile, so a stale marker left by an earlier failed build isn't mistaken
        # for this compile's result.
        _, pre_marker = _read_compile_errors(ed)
        log(f"Pre-compile fail marker present: {pre_marker}")
        # SetForegroundWindow makes the editor receive keyboard input without
        # cursor movement (no mouse needed). send_keys uses SendInput (keyboard
        # only) which works in disconnected RDP sessions.
        hwnd = ed.element_info.handle
        log(f"NS Editor HWND: {hwnd}")
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        send_keys("{F5}")
        log("F5 sent to NinjaScript Editor — waiting for dll update...")
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        print("STATUS:error", flush=True)
        sys.exit(2)

    start = time.time()
    deadline = start + TIMEOUT_SECS
    # Give the build a moment to start before we trust the "no errors" state — the
    # error grid clears on F5 and repopulates, so an immediate read can be empty.
    grace = start + 6
    while time.time() < deadline:
        time.sleep(3)
        if NT8_CUSTOM_DLL.exists() and NT8_CUSTOM_DLL.stat().st_mtime > pre_mtime:
            log(f"dll updated — compile succeeded in ~{round(time.time() - start, 1)}s")
            print("STATUS:success", flush=True)
            sys.exit(0)

        if time.time() < grace:
            continue
        errors, marker = _read_compile_errors(ed)
        # Fail fast on real error rows, or on a FRESH fail marker (one that wasn't
        # already showing before this compile). dll-mtime is checked first above, so
        # a clean build exits as success before we ever look at the marker.
        if errors or (marker and not pre_marker):
            if errors:
                for e in errors:
                    print(f"ERROR:{e}", flush=True)
            else:
                print(
                    "ERROR:NinjaTrader reports build errors. Open the NinjaScript "
                    "Editor error panel on the VPS for the full list.",
                    flush=True,
                )
            log(
                f"compile failed in ~{round(time.time() - start, 1)}s "
                f"({len(errors)} error rows read)"
            )
            print("STATUS:failed", flush=True)
            sys.exit(1)

    # Neither the dll updated nor did the grid show errors — a genuine timeout.
    print(
        "ERROR:Compile did not complete within 90 s. "
        "Check the NinjaScript Editor output panel for errors.",
        flush=True,
    )
    print("STATUS:failed", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
