#!/usr/bin/env python3
"""check_pine_blocks.py — prove every Pine COPY of a shared engine block still agrees with the
indicator it was copied from.

WHY THIS EXISTS
---------------
Pine has no import. So every engine block is physically copy-pasted into `mpc_jarvis.pine`, into
that engine's own parity harness, into any OTHER harness that embeds it for a coupling, and into
each strategy file plus that strategy's export twin. One rule change touches ~10 files and NOTHING
asserted they matched.

🔴 The parity gates cannot see this class of defect, and that is the whole point of this tool.
A `compare_*.py` answers "does the Python agree with ONE Pine file, on ONE export, on ONE machine".
It is structurally blind to two PINE files disagreeing with each other. On 2026-09-09 the equal-level
mitigation rule was moved close → wick in the indicator, the Python engine and two harnesses, while
SEVEN strategy Pine files stayed on `close` — and every gate that could run stayed green, because
none of them compares Pine against Pine.

⚠ The engine's own documentation said the rule lived in THREE places. It lived in eight. That is not
carelessness: the true count lived nowhere, so anybody checking was checking the files they happened
to know about. **A count that exists only in prose is a count that is wrong.** This file DISCOVERS
the copies instead of listing them, which is why it cannot go stale the way that sentence did.

THE DESIGN DECISION THAT MATTERS
--------------------------------
🔴 **Every check compares a copy against the INDICATOR, never against a value typed in here.**
Hardcoding `expect="high"` would make this tool a second place the rule is written down — and then
the next rule change has to update the checker too, which is precisely the disease. Read the truth
out of `mpc_jarvis.pine` and assert agreement, and a deliberate future rule change needs no edit
here at all: move the indicator, move the copies, this stays green.

⚠ It also means this tool CANNOT tell you the indicator is right. It tells you the copies match it.
That is rule 14 — a green parity check says two things agree, never that either is correct.

SELF-TEST
---------
⚠ "No findings" and "the scanner is broken" must never look the same. Every spec declares the
minimum number of files it expects to find; finding fewer is a FAILURE, not a pass. A regex that
stops matching after somebody reformats a file would otherwise report a clean repo.

Usage:
    python3 scripts/check_pine_blocks.py            # report; exit 1 on any drift
    python3 scripts/check_pine_blocks.py --verbose  # also list every file checked and its value

Standard library only. Step of `scripts/run_all_tests.sh`.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TRUTH = REPO / "indicators" / "engines" / "mpc_jarvis.pine"

# Directories that may hold a Pine copy of an engine block.
SEARCH_DIRS = ("indicators", "strategies")


# ─────────────────────────────────────────────────────────────────────────────
# Extractors — each returns a comparable value for one file, or None if the
# block is absent (absent is fine; DISAGREEING is not).
# ─────────────────────────────────────────────────────────────────────────────


def _eq_mitigation(text: str, side: str):
    """Which price field takes an equal-high/low level — the wick or the close?

    Two shapes exist in this repo and both must parse, because a checker that silently fails to
    match is a checker that reports everything as clean:

        if close > lvl                      (strategy files: level read into a local first)
        if high > array.get(eqhPx, i)       (the harnesses: read inline)

    Returns the LEFT operand of the comparison ("high" / "close" / "low"), which is the whole rule.
    """
    arr = "eqhPx" if side == "high" else "eqlPx"
    # Find the mitigation loop for this side. The loop may iterate the price array or the
    # parallel line array, so accept either as the header.
    loop = re.search(
        rf"for\s+i\s*=\s*array\.size\((?:{arr}|eq{side[0]}hLines|eq{'h' if side == 'high' else 'l'}Lines)\)\s*-\s*1\s+to\s+0",
        text,
    )
    if not loop:
        return None
    window = text[loop.end() : loop.end() + 600]
    m = re.search(rf"if\s+(\w+)\s*[<>]\s*(?:lvl|array\.get\({arr},\s*i\))", window)
    return m.group(1) if m else None


def _numeric_setting(text: str, name: str):
    """The value of a tuning constant, whether it is a bare constant or a panel input.

        float eqAtrMult   = 0.25
        float eqAtrMult   = input.float(0.25, "...")

    Returns a float, or None when the file does not carry the setting.
    """
    m = re.search(rf"\b{name}\s*=\s*input\.\w+\(\s*([0-9.]+)", text)
    if not m:
        m = re.search(rf"\b{name}\s*=\s*([0-9.]+)\s*$", text, re.MULTILINE)
    if not m:
        m = re.search(rf"\b{name}\s*=\s*([0-9.]+)", text)
    return float(m.group(1)) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# Specs
# ─────────────────────────────────────────────────────────────────────────────
# `min_files` is the self-test: fewer than this many copies found means the
# extractor stopped matching, not that the repo got tidier.

SPECS = [
    {
        "name": "equal-high mitigation (wick vs close)",
        "extract": lambda t: _eq_mitigation(t, "high"),
        "min_files": 8,
        "why": "an equal high is taken when price TRADES through it, not when it closes through",
    },
    {
        "name": "equal-low mitigation (wick vs close)",
        "extract": lambda t: _eq_mitigation(t, "low"),
        "min_files": 8,
        "why": "mirror of the above",
    },
    {
        "name": "equal-level tolerance (x ATR)",
        "extract": lambda t: _numeric_setting(t, "eqAtrMult"),
        "min_files": 8,
        "why": "decides which pivot pairs count as equal at all - it changes which levels FORM",
    },
    {
        "name": "equal-level cap per side",
        "extract": lambda t: _numeric_setting(t, "eqMax"),
        "min_files": 8,
        "why": "decides how many levels survive, which feeds the gap cap exemption",
    },
    {
        "name": "equal-level pivot width",
        "extract": lambda t: _numeric_setting(t, "eqPivotLen"),
        "min_files": 8,
        "why": "decides how sharp a turn counts as a pivot",
    },
]


def _pine_files():
    out = []
    for d in SEARCH_DIRS:
        out.extend(sorted((REPO / d).rglob("*.pine")))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--verbose", action="store_true", help="list every file checked and its value")
    args = ap.parse_args(argv)

    if not TRUTH.exists():
        print(f"ERROR: the source of truth is missing: {TRUTH.relative_to(REPO)}")
        return 1

    files = _pine_files()
    if not files:
        print("ERROR: no .pine files found - the search paths are wrong, not the repo clean.")
        return 1

    texts = {}
    for f in files:
        try:
            texts[f] = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"ERROR: cannot read {f}: {exc}")
            return 1

    truth_text = texts.get(TRUTH)
    if truth_text is None:
        print(f"ERROR: the source of truth was not picked up by the scan: {TRUTH}")
        return 1

    failures = 0
    scanner_broken = 0

    for spec in SPECS:
        expected = spec["extract"](truth_text)
        if expected is None:
            print(f"🔴 SCANNER BROKEN: '{spec['name']}' could not be read from the indicator.")
            print("   The rule did not vanish - the extractor stopped matching. Fix the extractor.")
            scanner_broken += 1
            continue

        found, drift = [], []
        for f, text in texts.items():
            if f == TRUTH:
                continue
            val = spec["extract"](text)
            if val is None:
                continue  # this file does not carry the block
            found.append((f, val))
            if val != expected:
                drift.append((f, val))

        # Self-test: too few copies means the extractor broke, not that drift is gone.
        if len(found) + 1 < spec["min_files"]:
            print(
                f"🔴 SCANNER BROKEN: '{spec['name']}' found only {len(found) + 1} "
                f"copies, expected at least {spec['min_files']}."
            )
            print("   A scan that matches nothing reports a clean repo. Fix the extractor, or")
            print("   lower min_files ONLY once you have confirmed a copy really was deleted.")
            scanner_broken += 1
            continue

        if drift:
            failures += len(drift)
            print(f"\n🔴 DRIFT: {spec['name']}")
            print(f"   the indicator says: {expected}   ({spec['why']})")
            for f, val in sorted(drift):
                print(f"     {val!r:>10}  {f.relative_to(REPO)}")
        elif args.verbose:
            print(f"\n✓ {spec['name']}: {len(found) + 1} copies agree on {expected!r}")
            for f, val in sorted(found):
                print(f"     {val!r:>10}  {f.relative_to(REPO)}")
        else:
            print(f"✓ {spec['name']}: {len(found) + 1} copies agree on {expected!r}")

    if scanner_broken:
        print(
            f"\n{scanner_broken} check(s) could not run. Treat that as a FAILURE: a check that "
            f"cannot run and a check that passes must never look the same."
        )
        return 1
    if failures:
        print(f"\n{failures} Pine cop(y/ies) disagree with indicators/engines/mpc_jarvis.pine.")
        print("The indicator is the source of truth. Move the copies to match it - and remember")
        print("each strategy's export twin must move WITH its strategy, or that gate goes red.")
        return 1

    print("\n✓ every Pine copy of every checked block agrees with the indicator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
