"""
test_opt_pass.py — One-shot test for OnTesterDeinit() CSV output.

Runs a 9-combo (3×3) native MT5 optimization on TestOptPass.mq5 and checks
whether opt_test_results.csv appears in MQL5/Files. If it does, OnTesterDeinit
works and we can drop the sequential single-backtest approach.

Prerequisites:
  1. TestOptPass.mq5 compiled to TestOptPass.ex5 in the Experts directory.
  2. MT5_DATA_DIR env var set (or TERMINAL_PATH) — same as for the mt5_agent.

Run directly on the VPS:
  python C:\\trading\\algos\\markets\\fx\\tools\\test_opt_pass.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def _find_data_dir() -> Path | None:
    explicit = os.environ.get("MT5_DATA_DIR", "")
    if explicit:
        p = Path(explicit)
        if p.is_dir():
            return p

    terminal_path = os.environ.get("TERMINAL_PATH", "")
    if not terminal_path:
        return None
    target = str(Path(terminal_path)).lower()
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    base = Path(appdata) / "MetaQuotes" / "Terminal"
    if not base.is_dir():
        return None
    for folder in base.iterdir():
        origin = folder / "origin.txt"
        if origin.is_file():
            try:
                if origin.read_text(encoding="utf-8", errors="replace").strip().lower() == target:
                    return folder
            except Exception:
                pass
    return None


def _find_tester_exe(data_dir: Path) -> Path | None:
    origin = data_dir / "origin.txt"
    if origin.is_file():
        try:
            terminal_dir = Path(origin.read_text(encoding="utf-8", errors="replace").strip())
            for name in ("terminal64.exe", "metatester64.exe"):
                p = terminal_dir / name
                if p.is_file():
                    return p
        except Exception:
            pass
    env = os.environ.get("TERMINAL_PATH", "")
    if env:
        d = Path(env)
        if not d.is_dir():
            d = d.parent
        for name in ("terminal64.exe", "metatester64.exe"):
            p = d / name
            if p.is_file():
                return p
    return None


def main() -> None:
    data_dir = _find_data_dir()
    if not data_dir:
        print("ERROR: cannot locate MT5 data dir — set MT5_DATA_DIR or TERMINAL_PATH")
        sys.exit(1)
    print(f"Data dir: {data_dir}")

    tester_exe = _find_tester_exe(data_dir)
    if not tester_exe:
        print("ERROR: cannot locate terminal64.exe / metatester64.exe")
        sys.exit(1)
    print(f"Tester exe: {tester_exe}")

    ex5 = data_dir / "MQL5" / "Experts" / "TestOptPass.ex5"
    if not ex5.is_file():
        print(f"ERROR: {ex5} not found — compile TestOptPass.mq5 first")
        sys.exit(1)
    print(f"EA: {ex5}  OK")

    # Set file: FastPeriod 5→15 step 5, SlowPeriod 20→30 step 5 → 3×3 = 9 combos
    tester_dir = data_dir / "MQL5" / "Profiles" / "Tester"
    tester_dir.mkdir(parents=True, exist_ok=True)
    set_path = tester_dir / "testoptpass.set"
    set_path.write_text(
        "FastPeriod=5||5||5||15||Y\n"
        "SlowPeriod=20||20||5||30||Y\n",
        encoding="utf-8",
    )
    print(f"Set file: {set_path}")

    reports_dir = data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ini_path = data_dir / "testoptpass.ini"
    ini_path.write_text(
        "[Tester]\n"
        "Expert=TestOptPass\n"
        "ExpertParameters=testoptpass.set\n"
        "Symbol=EURUSD\n"
        "Period=H1\n"
        "Model=0\n"
        "FromDate=2025.01.01\n"
        "ToDate=2025.03.01\n"
        "ForwardMode=0\n"
        "Report=reports\\testoptpass\n"
        "ReplaceReport=1\n"
        "ShutdownTerminal=1\n"
        "Deposit=100000\n"
        "Currency=USD\n"
        "Leverage=1:100\n"
        "Visual=0\n"
        "Optimization=1\n",
        encoding="utf-8",
    )
    print(f"INI: {ini_path}")

    output_csv = data_dir / "MQL5" / "Files" / "opt_test_results.csv"
    if output_csv.exists():
        output_csv.unlink()
        print("Removed stale opt_test_results.csv")

    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 6  # SW_MINIMIZE
    proc = subprocess.Popen(
        [str(tester_exe), f"/config:{ini_path}"],
        startupinfo=startupinfo,
    )
    print(f"Launched PID {proc.pid}. Waiting up to 180s …")

    deadline = time.time() + 180
    while time.time() < deadline:
        rc = proc.poll()
        if rc is not None:
            print(f"Process exited (rc={rc})")
            break
        time.sleep(3)
    else:
        proc.terminate()
        print("TIMEOUT — process killed")

    time.sleep(2)

    if output_csv.exists():
        content = output_csv.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in content.splitlines() if l.strip()]
        print(f"\nSUCCESS — {output_csv}")
        print(f"{len(lines)-1} data rows (expected 9):")
        print(content)
    else:
        print(f"\nFAIL — {output_csv} was not created")
        print("OnTesterDeinit() did not fire or FileOpen failed.")

    set_path.unlink(missing_ok=True)
    ini_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
