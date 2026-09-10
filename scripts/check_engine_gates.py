#!/usr/bin/env python3
"""check_engine_gates.py — run every engine's Pine↔Python parity gate against its COMMITTED
golden export, on every machine, every time.

WHY THIS EXISTS
---------------
🔴 Rule 22 says never commit an engine change until its `compare_*.py` has passed on a real
export. Until 2026-09-09 the exports were git-ignored scratch, so whether a gate could run at all
depended on which CSVs happened to be sitting on one laptop. Measured that day: NINE of the
fourteen gates could not answer, and the ones that did answer were red against exports taken two
months earlier — from a Pine that no longer existed. **A rule that cannot be satisfied stops being
a rule.** It became a blocker instead of a gate, and the honest options on any given day were to
stall or to route around it. Both happened.

The fix is to stop conflating two different jobs:

    golden export   REGRESSION.  Catches the PYTHON drifting away from a known-good answer.
                    Committed, small, runs on every clone in seconds, needs no human.

    fresh export    ACCEPTANCE.  Catches the PINE and the Python disagreeing after a Pine edit.
                    Needs a person with TradingView open. Unchanged by this tool.

⚠ **A green run here says the engine still does what it did when the golden file was taken. It
says NOTHING about a Pine edit made afterwards.** Do not let it stand in for a fresh export when
the indicator has moved — that is the same mistake as reading a green parity gate as proof the
implementation is RIGHT rather than merely in agreement (rule 14).

⚠ It is also blind to two PINE files disagreeing with each other. That is
`scripts/check_pine_blocks.py`, a separate step, for a separate reason.

HOW IT FINDS WORK
-----------------
Discovery, never a list: `engines/*/exports/golden/*.csv` paired with that engine's
`tools/compare_*.py`. Adding a golden export for another engine wires it in with no edit here.
⚠ That is deliberate — a hardcoded list is one more thing to forget, and this repo has already
paid for a count that lived only in prose.

SELF-TEST
---------
⚠ Finding NO golden exports is a FAILURE, not a pass. A runner that silently finds nothing and
prints success is worse than no runner, because the next reader takes the green for coverage.

Usage:
    python3 scripts/check_engine_gates.py

Standard library only. Step of `scripts/run_all_tests.sh`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENGINES = REPO / "engines"

# Raise this as golden exports are added, so losing one is a failure rather than a quieter run.
MIN_GOLDEN_EXPORTS = 12


def _gateable_engines():
    """Every engine that HAS a compare_*.py, i.e. every engine that COULD carry a golden export.

    Reported alongside the covered count so a green run can never be read as full coverage - see
    the coverage note in main().
    """
    return sorted({g.parent.parent for g in ENGINES.glob("*/tools/compare_*.py")})


def _discover():
    """(engine_dir, gate_script, golden_csv) for every engine carrying a golden export."""
    found = []
    for golden_dir in sorted(ENGINES.glob("*/exports/golden")):
        engine = golden_dir.parent.parent
        csvs = sorted(golden_dir.glob("*.csv"))
        if not csvs:
            continue
        gates = sorted(engine.glob("tools/compare_*.py"))
        if not gates:
            print(f"🔴 {engine.name}: has a golden export but NO compare_*.py to run on it.")
            found.append((engine, None, csvs[0], 0, []))
            continue
        # golden.json carries the MEASURED warm-up and the provenance. A missing manifest means
        # warm-up 0 rather than a skip: silently not running a gate is the failure this whole file
        # exists to stop.
        warmup, extra = 0, []
        manifest = golden_dir / "golden.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                warmup = int(data.get("warmup", 0))
                # ⚠ extra_args is a GENERIC seam, not a fib special case: any gate may need a
                # per-engine flag, and the alternative is this runner growing an if-statement per
                # engine. Whatever it carries MUST be justified in the manifest itself - the fib
                # entry explains why its macro half is excluded and when to revisit.
                extra = [str(a) for a in data.get("extra_args", [])]
            except (ValueError, OSError) as exc:
                print(f"🔴 {engine.name}: unreadable golden.json ({exc}) - running at warm-up 0.")
        for csv in csvs:
            found.append((engine, gates[0], csv, warmup, extra))
    return found


def main() -> int:
    if not ENGINES.is_dir():
        print(f"ERROR: no engines directory at {ENGINES} - the path is wrong, not the repo empty.")
        return 1

    work = _discover()

    if len(work) < MIN_GOLDEN_EXPORTS:
        print(
            f"🔴 SELF-TEST FAILED: found {len(work)} golden export(s), expected at least "
            f"{MIN_GOLDEN_EXPORTS}."
        )
        print("   A runner that finds nothing and prints success is worse than no runner - the")
        print("   next reader takes the green for coverage. Restore the export, or lower")
        print("   MIN_GOLDEN_EXPORTS only once you have confirmed one was deliberately removed.")
        return 1

    failures = 0
    for engine, gate, csv, warmup, extra in work:
        extra_note = f", {' '.join(extra)}" if extra else ""
        label = f"{engine.name} ({csv.name}, warm-up {warmup}{extra_note})"
        if gate is None:
            failures += 1
            continue
        cmd = [sys.executable, str(gate), str(csv)]
        if warmup:
            cmd += ["--warmup", str(warmup)]
        cmd += extra
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"  ✓ {label}")
            # 🔴 A GATE'S OWN WARNINGS MUST SURVIVE ITS GREEN, and this runner swallowed them.
            # compare_fvg.py prints how much of its export it could actually SEE - measured at 52%
            # of bars on the committed golden file, because the gap list outgrew the plotted slots.
            # That line went to a captured stdout that was discarded on success, so the step showed
            # a tick over a half-blind gate. **A tool that hides a caveat when things pass is the
            # misleading-green shape this whole file exists to stop**, one level up. Generic on
            # purpose: any gate can raise a caveat this way and none of them needs an if-statement
            # here.
            for line in (proc.stdout or "").splitlines():
                s = line.strip()
                if s.startswith("🔴") or s.startswith("⚠"):
                    print(f"      {s}")
        else:
            failures += 1
            print(f"  🔴 {label} - gate exit {proc.returncode}")
            tail = (proc.stdout or proc.stderr).strip().splitlines()
            for line in tail[:12]:
                print(f"      {line}")

    if failures:
        print(f"\n{failures} engine gate(s) RED against a committed golden export.")
        print("That means the PYTHON moved away from a known-good answer - this cannot be a stale")
        print("export, because the export is pinned in git next to the engine it validates.")
        return 1

    gateable = _gateable_engines()
    covered = {e for e, _g, _c, _w, _x in work}
    missing = [e.name for e in gateable if e not in covered]

    print(f"\n✓ {len(work)} engine gate(s) green against their golden exports.")
    # 🔴 STATE THE COVERAGE FRACTION OUT LOUD, ALWAYS.
    # A bare green tick on this step reads as "the engine gates pass" when it may mean "the ONE
    # engine with a committed export passes". That is the misleading-green shape this repo keeps
    # paying for, and it would be self-inflicted here: the step is new, so nobody yet has a prior
    # expectation of what it covers. Printing the fraction and NAMING the uncovered engines makes
    # the gap impossible to mistake for coverage.
    print(f"⚠ COVERAGE: {len(covered)} of {len(gateable)} gateable engines have a golden export.")
    if missing:
        print("⚠ NO golden export, so NOT regression-tested on any machine but the one holding a")
        print("  scratch CSV: " + ", ".join(missing))
        print("  Each needs one fresh TradingView export, once, to join this step permanently.")
    print("⚠ Regression only. A Pine change still needs a FRESH export before it may be trusted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
