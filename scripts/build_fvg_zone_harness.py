#!/usr/bin/env python3
"""build_fvg_zone_harness.py — GENERATE indicators/engines/fvg_zone_export.pine, and prove it is
still what its two sources say it is.

WHY A GENERATOR AND NOT A HAND-WRITTEN PINE FILE
------------------------------------------------
The entry-band exemption needs four engine blocks in ONE script — market structure, the Structure
fib, EQ and FVG — because the band is the live fib's 0.382-0.886, recomputed every bar. That makes
this harness a TENTH Pine copy of the FVG block and a fresh copy of the structure engine, in a repo
whose most expensive class of defect is exactly that: Pine has no import, so every copy drifts and
no parity gate can see it (scripts/check_pine_blocks.py exists because seven strategy files sat on
a superseded rule while every gate stayed green).

🔴 So this file is not a convenience. It is the thing that stops the copy being a copy. The harness
is a BUILD ARTIFACT: every block is sliced verbatim out of fib_export.pine or fvg_export.pine, and
`--check` regenerates it and diffs. Edit either source without regenerating and the step goes RED,
which is the one outcome a hand-maintained tenth copy could never give you.

⚠ The only text authored HERE is the entry-band exemption, and that is because it exists in exactly
one place in the repo today (mpc_jarvis.pine) with no harness to lift it from. Every line of it
carries the mpc line numbers it was copied from, so the next reader can diff it by eye.

⚠ THIS DOES NOT PROVE THE HARNESS IS RIGHT, only that it matches its sources — rule 14 again. What
proves it right is engines/fair_value_gaps/tools/compare_fvg.py going green on a real export.

Usage:
    python3 scripts/build_fvg_zone_harness.py            # regenerate the harness
    python3 scripts/build_fvg_zone_harness.py --check    # exit 1 if it is out of date

Standard library only. Step of scripts/run_all_tests.sh.
"""

from pathlib import Path

REPO = Path("/Users/alwg/trading")
FIB = (REPO / "indicators/engines/fib_export.pine").read_text().splitlines()
FVG = (REPO / "indicators/engines/fvg_export.pine").read_text().splitlines()


# ⚠ SLICED ON TEXT ANCHORS, NEVER ON LINE NUMBERS. The first version of this file used line
# numbers and they were stale within the hour - widening the gap harness's plot block moved every
# boundary in it, and a numeric slice would have cut the new block in half while still producing a
# file. An anchor that stops matching raises here instead.
def _cut(lines, first, last=None):
    """The block from the line CONTAINING `first` up to (not including) the one containing `last`."""

    def find(needle, start=0):
        for i in range(start, len(lines)):
            if needle in lines[i]:
                return i
        raise SystemExit(
            f"anchor not found, so a source file has moved under this script: {needle!r}"
        )

    a = find(first)
    b = find(last, a + 1) if last is not None else len(lines)
    return "\n".join(lines[a:b])


# settings + external + internal structure, i.e. everything the fib anchors on
fib_structure = _cut(FIB, "//  SMC SETTINGS (hardcoded)", "//  STRUCTURE FIBONACCI")
# the Structure fib itself, up to (not including) the Sniper fib this harness does not need
fib_fib = _cut(FIB, "//  STRUCTURE FIBONACCI", "//  SNIPER FIB")
# inputs + EQ block + FVG detect/cap/mitigate
fvg_body = _cut(FVG, "// Defaults MIRROR mpc_jarvis.pine", "// ── Parity columns")
# the parity + cfg columns
fvg_plots = _cut(FVG, "// ── Parity columns")


def sub(text, old, new, count=1):
    if text.count(old) != count:
        raise SystemExit(f"anchor matched {text.count(old)} times, expected {count}:\n{old[:120]}")
    return text.replace(old, new)


# ── B1. The entry-band globals, declared beside the cap that reads them (mpc's own placement:
#        the fib is ~800 lines below and Pine needs a declaration before its use). ──
fvg_body = sub(
    fvg_body,
    "// State arrays (the Pine fvgBoxes drawing array is intentionally dropped).",
    """// ── Entry-band coupling (mpc fvgExemptZone): an FVG sitting in the live fib's 0.382-0.886 band,
//    ON THE TRADE'S OWN SIDE, is exempt from the cap. This is the reason this harness exists and
//    the reason it carries a whole structure + fib engine above: the band cannot be an input,
//    it is recomputed every bar from the live leg.
//    🔴 The band read here is LAST BAR'S, and that lag is mpc's, not an artefact of this file.
//    In mpc the FVG block runs ~800 lines ABOVE the fib block, so it can only ever see the
//    previous bar's publish. It is deliberate there ("this decides which gap to THROW AWAY,
//    never which one to trade"), so the harness reproduces the ordering rather than the result:
//    the FVG block below sits BEFORE the fib block, exactly as it does in the indicator. ──
bool  fvgExemptZone = input.bool(true, "Keep FVGs in the live fib entry band until mitigated")
var float fvgZoneLo  = na
var float fvgZoneHi  = na
var int   fvgZoneDir = 0

// State arrays (the Pine fvgBoxes drawing array is intentionally dropped).""",
)

# ── B2. f_fvgZoneKeep, copied from mpc_jarvis.pine:3833-3835. ──
fvg_body = sub(
    fvg_body,
    "// ── Detection (confirmed bars only; needs the two-bars-back candle) ──",
    """// True when a gap sits in the live fib ENTRY BAND on the trade's own side (mpc f_fvgZoneKeep,
// copied from mpc_jarvis.pine:3833-3835). Read by the cap below both to COUNT and to CHOOSE what
// to drop, so a protected gap never holds a slot and is never the one evicted.
f_fvgZoneKeep(float gTop, float gBot, bool isBull) =>
    fvgExemptZone and fvgZoneDir != 0 and isBull == (fvgZoneDir == 1) and not na(fvgZoneLo)
      and gTop >= fvgZoneLo and gBot <= fvgZoneHi

// ── The band as the cap ACTUALLY SAW IT this bar, captured before the fib block below can move
//    it. Exported as px_fvgzone_*, so compare_fvg.py feeds Python the same numbers the Pine used
//    and no off-by-one can hide inside the comparison tool. The band the fib PUBLISHES this bar is
//    exported separately (px_fibband_*), and the tool asserts consumed[i] == published[i-1] — that
//    turns the one-bar lag from a sentence in a comment into a checked fact. ──
float fvgZoneLoUsed  = fvgZoneLo
float fvgZoneHiUsed  = fvgZoneHi
int   fvgZoneDirUsed = fvgZoneDir

// ── Detection (confirmed bars only; needs the two-bars-back candle) ──""",
)

# ── B3. Compose the two exemptions in BOTH cap loops — the count and the drop scan. Applying one
#        to only the count is the self-cancelling swap this repo already paid for once. ──
old_test = (
    "if not (eqExemptFvg and f_fvgNearEq(array.get(fvgTops, _di), array.get(fvgBots, _di), eqTol))"
)
new_test = (
    "if not ((eqExemptFvg and f_fvgNearEq(array.get(fvgTops, _di), array.get(fvgBots, _di), eqTol))"
    " or f_fvgZoneKeep(array.get(fvgTops, _di), array.get(fvgBots, _di), array.get(fvgIsBull, _di)))"
)
fvg_body = sub(fvg_body, old_test, new_test, count=2)

# ── C. The band publish, copied from mpc_jarvis.pine:4896-4907, appended INSIDE `if fibActive`
#       exactly where mpc puts it (last statement of the fib's active branch). ──
fib_fib = (
    fib_fib.rstrip("\n")
    + """

    // ── PUBLISH THE ENTRY BAND FOR THE FVG CAP — copied from mpc_jarvis.pine:4896-4907 ──
    // Read on the NEXT bar by the FVG cap above, which is why this is the last thing the fib
    // block does. 0.382 → 0.886, ordered with min/max so a short's band (which runs the other
    // way) still compares correctly.
    // ⚠ fvgZoneDir is `fiboResetActive ? 0 : fibo_dir` in mpc. `fiboResetActive` is only ever set
    //   true on a 1-MINUTE chart there (mpc:4893 `if _fibOneMin and (fibo7Touched or rTp50)`), and
    //   reaching that needs the whole MTF-alignment block. So on any timeframe above 1m this term
    //   is `fibo_dir` in mpc too, and this harness reproduces mpc-above-1m faithfully rather than
    //   pretending to cover a branch it cannot reach. Export above 1m. The Python engine's
    //   dir == 0 branch IS exercised — it is every bar before the first leg confirms.
    fvgZoneLo  := math.min(fiboP1, fiboP6)
    fvgZoneHi  := math.max(fiboP1, fiboP6)
    fvgZoneDir := fiboResetActive ? 0 : fibo_dir"""
)

# ── D. The extra columns. ──
fvg_plots = (
    fvg_plots.rstrip("\n")
    + """
// ── Entry-band columns ──
// px_fvgzone_* is the band the cap CONSUMED on this bar; px_fibband_* is what the fib PUBLISHED
// on it. compare_fvg.py drives Python off the consumed set and self-tests the one-bar lag against
// the published set.
plot(fvgZoneLoUsed,  "px_fvgzone_lo",  color = color.new(color.gray, 100))
plot(fvgZoneHiUsed,  "px_fvgzone_hi",  color = color.new(color.gray, 100))
plot(fvgZoneDirUsed, "px_fvgzone_dir", color = color.new(color.gray, 100))
plot(fvgZoneLo,      "px_fibband_lo",  color = color.new(color.gray, 100))
plot(fvgZoneHi,      "px_fibband_hi",  color = color.new(color.gray, 100))
plot(fvgZoneDir,     "px_fibband_dir", color = color.new(color.gray, 100))
plot(fvgExemptZone ? 1.0 : 0.0, "cfg_fvg_exemptzone", color = color.new(color.gray, 100))"""
)

HEADER = """// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/ MPL-2.0
//@version=6
// ============================================================================
//  FVG ZONE EXPORT — parity harness for the FVG cap's ENTRY-BAND exemption
// ============================================================================
// 🔴 WHY THIS FILE IS SEPARATE FROM fvg_export.pine, AND WHY IT IS SO LARGE.
// The entry-band exemption cannot be tested by fvg_export.pine, and not for want of trying: the
// band is not an input, it is the live fib's 0.382-0.886 recomputed every bar from the current
// leg. Reproducing it needs the market-structure engine AND the Structure fib in the same script.
// So this harness carries all four blocks — structure, fib, EQ, FVG — because that is what the
// coupling is.
//
// It is a SECOND file rather than an extension of fvg_export.pine for two reasons, both measured:
//   1. fib_export.pine already uses 63 of TradingView's 64 plot slots, so the FVG columns cannot
//      go there. That direction is closed, not merely unattractive.
//   2. fvg_export.pine gates what every CONSUMER of the engine actually runs today — a plain FVG
//      engine with no band — and its golden export regression-tests exactly that. Folding 1,100
//      lines of structure into it would make the cheap, universal gate depend on the fib. The
//      pattern here is the one eq_export.pine/fvg_export.pine already set: one harness for the
//      engine alone, a second for the coupling.
//
// ⚠ THE COST IS A TENTH PINE COPY OF THE FVG BLOCK, and it is stated rather than hidden.
//    scripts/check_pine_blocks.py is what stops it drifting; if you change an FVG rule anywhere,
//    that step is the thing that tells you which of the ten files you missed.
//
// COMPOSITION — every block is byte-lifted, never retyped:
//   1. Market structure, external + internal .... from fib_export.pine (which took it from
//      structure_engine_export.pine). Validated at 100% Python parity in its own gate.
//   2. EQ + FVG detection / cap / mitigate ...... from fvg_export.pine, unchanged apart from the
//      band exemption composed into the two cap loops.
//   3. The Structure fib ........................ from fib_export.pine, plus the band publish
//      copied from mpc_jarvis.pine:4896-4907.
//
// 🔴 BLOCK ORDER IS THE POINT AND MUST NOT BE "TIDIED". The FVG block sits BEFORE the fib block,
//    exactly as it does in mpc_jarvis.pine (~3830 vs ~4810). That is what gives the cap last bar's
//    band, which is mpc's deliberate behaviour. Moving the fib above the FVG would produce a
//    harness that is self-consistent, green, and describing an indicator nobody runs.
//
// Diffed by engines/fair_value_gaps/tools/compare_fvg.py. Export above the 1-minute timeframe
// (see the publish site for why). Do NOT trade off this file.
// ============================================================================
indicator("FVG Zone Export", overlay = false, max_bars_back = 2000, max_labels_count = 500, max_lines_count = 500)
"""

out = "\n".join([HEADER, fib_structure, "", fvg_body, "", fib_fib, "", fvg_plots, ""])
DEST = REPO / "indicators/engines/fvg_zone_export.pine"


def main(argv):
    check = "--check" in argv
    current = DEST.read_text() if DEST.exists() else None
    if check:
        if current == out:
            print(f"✓ {DEST.relative_to(REPO)} is in sync with fib_export.pine + fvg_export.pine")
            return 0
        print(f"🔴 {DEST.relative_to(REPO)} is STALE.")
        print("   It is generated by slicing fib_export.pine and fvg_export.pine, and one of those")
        print("   has moved since it was last built - so this harness is now validating Python")
        print("   against a Pine block the repo no longer has. Regenerate it:")
        print("       python3 scripts/build_fvg_zone_harness.py")
        print("   Then RE-EXPORT from TradingView before trusting its gate: a regenerated harness")
        print("   is a changed harness, and the committed CSV was taken from the old one.")
        if current is not None:
            import difflib

            diff = list(
                difflib.unified_diff(
                    current.splitlines(),
                    out.splitlines(),
                    fromfile="on disk",
                    tofile="regenerated",
                    lineterm="",
                    n=1,
                )
            )
            for line in diff[:40]:
                print(f"      {line}")
            if len(diff) > 40:
                print(f"      ... {len(diff) - 40} more diff lines")
        return 1
    DEST.write_text(out)
    print(
        f"wrote {DEST.relative_to(REPO)} - {len(out.splitlines())} lines, "
        f"{out.count(chr(10) + 'plot(')} plot columns"
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
