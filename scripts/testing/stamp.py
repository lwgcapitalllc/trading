"""The full run's side of the green records. Called by scripts/run_all_tests.sh.

    stamp.py snapshot PATH        record what the tree holds NOW, before any test runs
    stamp.py check                exit 0 (and say so) if the tree matches the last FULL green run
    stamp.py record PATH          the run went green: record the snapshot taken at its start
    stamp.py blindspots LOG PATH  the run went red: name every failure the fast tier would have
                                  skipped for the changes since the last green run

🔴 **The blind-spot report is how the fast tier's rules get corrected rather than trusted.** A
static selector is wrong in exactly one dangerous direction - a test it never picked goes red on
main - and nothing about a green fast run can reveal that. The full run is the only thing that
sees both answers, so it is the thing that says when they disagree.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import manifest, rules
from .fast import build_graph
from .selection import select

_STEP = re.compile(r"\[(\d+)/\d+\]")
_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+?\.py)")


def _snapshot(path: Path) -> int:
    tree = manifest.current()
    env = manifest.env_key(sys.executable)
    manifest.LOG_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps({"manifest": tree, "env": env}))
    return 0


def _check() -> int:
    rec = manifest.load_green("full")
    if not rec:
        return 1
    if rec.get("env") != manifest.env_key(sys.executable):
        return 1
    if manifest.diff(rec["manifest"], manifest.current()):
        return 1
    print(f"\n  Nothing changed since {manifest.describe(rec)}.")
    print("  Its output is in .test-logs/full.log - read that instead of running it again.")
    print("  To run anyway: scripts/run_all_tests.sh --force\n")
    return 0


def _record(path: Path) -> int:
    snap = json.loads(path.read_text())
    manifest.save_green("full", snap["manifest"], snap["env"])
    return 0


def _failures(log: Path):
    """{run_all_tests.sh step: set of failing test files, repo-relative} read off the full log."""
    step, out = 0, {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _STEP.search(line)
        if m and "..." in line:
            step = int(m.group(1))
            continue
        f = _FAILED.match(line.strip())
        if f and step in rules.PYTEST_STEPS:
            suite = next(s for s in rules.SUITES if s.name == rules.PYTEST_STEPS[step])
            rel = f.group(1)
            out.setdefault(step, set()).add(f"{suite.root}/{rel}" if suite.root else rel)
        elif line.lstrip().startswith("✗") and step not in rules.PYTEST_STEPS:
            out.setdefault(step, set())
    return out


def _blindspots(log: Path, snap_path: Path) -> int:
    rec = manifest.load_green("any")
    if not rec:
        print("  (no earlier green run recorded, so nothing to compare the fast tier against)")
        return 0
    snap = json.loads(snap_path.read_text())
    changed = manifest.diff(rec["manifest"], snap["manifest"])
    fails = _failures(log)
    if not changed or not fails:
        return 0
    sel = select(build_graph(snap["manifest"]), rules, changed)
    if sel.everything:
        return 0
    picked = {t for tests in sel.tests.values() for t in tests}
    missed = []
    for step, files in sorted(fails.items()):
        if step in rules.PYTEST_STEPS:
            missed += [f for f in sorted(files) if f not in picked]
        elif step == rules.GATE_STEP and not sel.gates:
            missed.append("step 15 (parity gates)")
        elif step not in rules.PYTEST_STEPS and step != rules.GATE_STEP and step not in sel.steps:
            missed.append(f"step {step}")
    if missed:
        print("\n  ⚠ BLIND SPOT: the fast command would NOT have run these for the changes since")
        print(f"    {manifest.describe(rec)}, and they failed:")
        for m in missed:
            print(f"      {m}")
        print(
            "    Add the missing rule to scripts/testing/rules.py - a selector that skipped a red"
        )
        print("    test once will skip it again.\n")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd, rest = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "snapshot" and len(rest) == 1:
        return _snapshot(Path(rest[0]))
    if cmd == "check" and not rest:
        return _check()
    if cmd == "record" and len(rest) == 1:
        return _record(Path(rest[0]))
    if cmd == "blindspots" and len(rest) == 2:
        return _blindspots(Path(rest[0]), Path(rest[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
