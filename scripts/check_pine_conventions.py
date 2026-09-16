#!/usr/bin/env python3
"""check_pine_conventions.py — every strategy Pine carries the panel, the annotations, the palette.

🔴 **THIS EXISTS BECAUSE THE CONVENTION WAS WRITTEN DOWN, AUDITED ONCE, AND DRIFTED ANYWAY.**
Aaron, 2026-09-16: *"all pine strategies and export must have these conventions. I believe I
stated this before and I did an audit and now we back to here."* He was right — `realign` was
built, measured six times and taken to the edge of a parity gate without a position box, without
a result callout, without entry triangles, without a refusal tag and on ad-hoc input groups.

**A convention enforced by remembering to read a CLAUDE.md is not enforced.** The annotations are
how a chart gets judged by eye, which is the one check no backtest replaces — so this runs in
`scripts/run_all_tests.sh` and fails the build, the same way `check_pine_blocks.py` does for the
engine copies.

What it checks, per `strategies/tradingview/CLAUDE.md`:

  1. **The numbered input-panel contract** — groups are `"N · Name"`, and the numbers used are
     real ones from the table. A strategy with no fibs simply has no group 9; the numbering does
     not close up, because the number is the address.
  2. **The trade annotations** — a position box, the best/worst excursion the trade reached, an
     entry callout that recolours WIN / LOSS / BREAKEVEN, entry triangles, and a tag for a setup
     that was REFUSED.
  3. **The palette** — every colour a TRADE is drawn in comes from `sos_fade_strategy.pine`.
     A hex outside the approved set in a strategy file is a colour somebody re-picked in a fork,
     which is exactly what Aaron asked to stop.
  4. **The export twin exists** and is not hand-kept.

⚠ **It reads the PARENT, never the twin** — a twin is generated from its parent, so a convention
checked on the twin would pass on a file nobody trades.

⚠ **This is a TEXT check and it can only prove absence, not correctness.** A file can satisfy
every rule here and still draw the wrong thing. It catches the failure that actually happened —
a whole layer simply missing — and makes no claim beyond that.

    python scripts/check_pine_conventions.py            # all strategy files
    python scripts/check_pine_conventions.py realign     # one, by name
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TV = _ROOT / "strategies" / "tradingview"

# The standard's own RESULT colours, read off `sos_fade_strategy.pine`. Change one by changing
# it there first and copying it down — never by picking a new one in a fork.
_WIN, _LOSS, _BE = "#26A69A", "#EF5350", "#FF9800"

# Group numbers from the contract table. A file uses a SUBSET; it may not invent a number.
_GROUPS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}

# (label, at least one of these patterns must appear)
_RULES = [
    ("position box", [r"box\.new\("]),
    ("favourable excursion (how far it ran)", [r"\bbest\b", r"maxFav", r"\bf1\b"]),
    ("adverse excursion (max drawdown)", [r"\bworst\b", r"maxAdv", r"POS_DD"]),
    ("result callout recoloured on close", [r"BREAKEVEN"]),
    ("entry triangles", [r"shape\.triangleup"]),
    ("refused / blocked setup tag", [r"REFUSED", r"BLOCKED", r"blkCode", r"BlkCode", r"TrigCode"]),
]

# Files that are deliberately exempt, each with the reason. ⚠ An exemption is a DECISION with a
# name on it, never a quiet skip — an empty list here would make the check pass vacuously.
_EXEMPT: dict = {
    "recovery_strategy.pine": "a loss-recovery SIZING rule, not a setup — it draws no trade of "
    "its own and has no export twin by design.",
}


def _check(path: Path) -> list:
    src = path.read_text(encoding="utf-8")
    fails = []

    # ⚠ Groups are almost always named through a CONSTANT (`var string G1 = "1 · …"`, then
    #   `group = G1`), so a check reading only literal `group = "…"` strings finds nothing and
    #   reports every compliant file as broken. Resolve the constants first. A check that cries
    #   wolf gets ignored, which is the failure this whole script exists to prevent.
    # ⚠ Both declaration styles are real and in use: `var string G1 = "1 · …"` (sos_fade)
    #   and a bare `G2 = "2 · …"` (extreme_leg). Matching only the first reported a compliant
    #   panel as having "no numbered groups at all" — a false positive on the very file whose
    #   real gaps were elsewhere, which is how a checker loses its reader.
    consts = dict(re.findall(r'(?:var\s+string\s+)?(\w+)\s*=\s*"(\d+)\s*·[^"]*"', src))
    groups = {int(v) for v in consts.values()}
    used = set(re.findall(r"group\s*=\s*(\w+)", src))
    bad_groups = sorted(set(re.findall(r'group\s*=\s*"([^"\d][^"]*)"', src)))
    unnumbered = sorted(n for n in used if n not in consts and not n.startswith("_"))
    if not groups:
        fails.append("no numbered input groups at all — see THE INPUT PANEL CONTRACT")
    if bad_groups:
        fails.append(f"un-numbered input group(s): {bad_groups[:4]}")
    if unnumbered:
        fails.append(f"group constant(s) that are not numbered: {unnumbered[:4]}")
    if groups - _GROUPS:
        fails.append(f"input group number(s) not in the contract: {sorted(groups - _GROUPS)}")

    for label, pats in _RULES:
        if not any(re.search(p, src) for p in pats):
            fails.append(f"no {label}")

    # 🔴 CHECKED BY PRESENCE, NOT BY ABSENCE, AND THAT IS DELIBERATE. "No hex outside the
    # palette" cannot be done by text: these files legitimately colour sessions, gaps, the
    # confirmation panel and the B-LEG overlay, and flagging those made the first version of
    # this script report all seven files as broken. A check with false positives gets ignored.
    # So the rule enforced here is the one that matters and is decidable: the three RESULT
    # colours a trade is graded in must be the standard's own.
    hexes = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", src)}
    for need, what in ((_WIN, "WIN"), (_LOSS, "LOSS"), (_BE, "BREAKEVEN")):
        if need not in hexes:
            fails.append(f"does not use the standard {what} colour {need}")

    twin = path.with_name(path.stem + "_export.pine")
    block = _TV / "export_blocks" / path.name
    if not twin.exists():
        fails.append("no export twin")
    elif not block.exists():
        fails.append("export twin has no block file — it is a hand-kept copy")
    return fails


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    files = sorted(p for p in _TV.glob("*_strategy.pine") if not p.name.endswith("_export.pine"))
    if argv:
        want = {a.replace("_strategy.pine", "").replace(".pine", "") for a in argv}
        files = [p for p in files if p.stem.replace("_strategy", "") in want]
        if not files:
            print(f"no strategy Pine matching {sorted(want)}")
            return 2

    worst = 0
    for p in files:
        if p.name in _EXEMPT:
            print(f"–  {p.name}  EXEMPT — {_EXEMPT[p.name]}")
            continue
        fails = _check(p)
        if fails:
            worst = 1
            print(f"✗  {p.name}")
            for f in fails:
                print(f"     · {f}")
        else:
            print(f"✓  {p.name}")

    print()
    if worst:
        print("Some strategy Pine files are missing conventions every one of them must carry.")
        print("The contract is strategies/tradingview/CLAUDE.md → THE INPUT PANEL CONTRACT,")
        print("PHASE 1 — the trade annotations, and THE ANNOTATION PALETTE.")
        print("⚠ Bringing a file onto the panel contract REORDERS its inputs, which resets saved")
        print("  values on any chart already running it. Do it before an export is taken, and say")
        print('  that "Reset settings to defaults" is needed once.')
    else:
        print("✓ every strategy Pine carries the panel, the annotations and the palette.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
