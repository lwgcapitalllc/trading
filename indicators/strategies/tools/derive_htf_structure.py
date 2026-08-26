#!/usr/bin/env python3
"""derive_htf_structure.py — build the HTF instance of the structure state machine MECHANICALLY.

`mpc_extreme_leg_strategy.pine` needs TWO instances of the external structure engine: one on the
chart's own bars (the 5-minute change of character that arms the trade) and one on 15-minute bars
aggregated in code (the trend and the swing that is the target).

🔴 THE SECOND INSTANCE IS DERIVED, NEVER RETYPED. The block is ~530 lines of state machine and a
hand-transcribed copy is a second implementation that drifts the first time somebody patches one
and not the other — which this repo has already had happen across eleven forked Pine files (see
`indicators/strategies/CLAUDE.md` -> the tied-extreme fix). Running this script regenerates the
derived half from the source half, so a divergence is a diff rather than a discovery.

WHAT IT CHANGES, and it is only this:
  * `type SMCStructure`        -> `type SMCStructure15`
  * `method process(...)`      -> `method process15(...)` taking the bar's O/H/L/C and pivot bar
  * BARE `high`/`low`/`close`/`open` -> the passed-in `_h`/`_l`/`_c`/`_o`
  * `bar_index[st.length]`     -> the passed-in `_pbi` (the pivot's own chart bar)

🔴 `bar_index` ITSELF IS DELIBERATELY NOT RENAMED, AND NEITHER ARE `low[i]` / `high[i]`. The first
build renamed all three and produced a state machine running on TWO CLOCKS at once: every swing
location was a chart bar index while every loop bound counted higher-timeframe bars, so the
post-break rescan searched a window three times too short and the seed loop could read past the
start of history. Both halves of that are silent — no error, no red test, just a swing anchored in
the wrong place.

The rule that resolves it: THE EXTREME OF A SPAN OF AGGREGATED BARS IS THE EXTREME OF THE CHART
BARS UNDER IT. A 15-minute bar's low IS the lowest of its three 5-minute lows, so a scan for the
lowest low between two points gives the same PRICE either way. So the scans, the loop bounds and
every stored location stay on the CHART's clock and stay consistent with each other; only the
per-bar decisions — is this bar inside the last one, did this close break the swing — need the
aggregated values, and those are exactly the bare reads.

⚠ One consequence to know rather than discover: the rescan's 1490-bar safety cap is now 1490 CHART
bars, about 496 higher-timeframe ones. It is a runaway guard, not a rule, and no swing here spans
that far — but it is a third of what the source intends.

⚠ The substitution is word-boundary anchored and refuses to touch an identifier that merely
CONTAINS one of those words (`pb_last_qualify_high`, `bull_bos_high`, `swing_low`). It asserts the
expected number of replacements and fails loudly on any other count, because a silent under-match
here is a state machine reading the wrong timeframe's bar with nothing to show for it.

⚠ Drawing calls are deliberately KEPT. The HTF instance runs on the main chart (not inside
`request.security`), so `label.new`/`line.new` are legal there, and stripping 61 drawing calls by
hand is exactly the unverifiable transcription this script exists to avoid.

Usage:  python3 indicators/strategies/tools/derive_htf_structure.py
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve()
STRAT = HERE.parents[1]
SOURCE = STRAT / "mpc_h4_sweep_strategy.pine"
OUT = HERE.parent / "_derived_structure_15.pine"

# The standardised block: the type declaration through the end of `method process`. Taken from the
# H4 file because that copy IS the standardised one (external half + the fib-free internal port) —
# see `indicators/strategies/CLAUDE.md` -> Section 2 is FIXED.
START = "type SMCStructure"
END = "// [doc 18] EXECUTION — EXTERNAL STRUCTURE"

# BARE reads only — an indexed read (`low[i]`) is history on the CHART's series and stays that way.
RENAMES = {"high": "_h", "low": "_l", "close": "_c", "open": "_o"}
EXPECTED = {"high": 12, "low": 15, "close": 9, "open": 2}
PIVOT_SRC = "bar_index[st.length]"
PIVOT_DST = "_pbi"
EXPECTED_PIVOT = 4


def derive(text: str) -> str:
    try:
        a = text.index(START)
        b = text.index(END)
    except ValueError:
        raise SystemExit(
            f"could not find the block markers in {SOURCE.name} — it has been restructured. "
            "Re-point START/END at the type declaration and the line after `method process`."
        )
    block = text[a:b].rstrip() + "\n"

    n_piv = block.count(PIVOT_SRC)
    if n_piv != EXPECTED_PIVOT:
        raise SystemExit(
            f"expected {EXPECTED_PIVOT} pivot-bar reads, found {n_piv}. The source block has "
            "changed; re-count and update EXPECTED_PIVOT in the same edit."
        )
    block = block.replace(PIVOT_SRC, PIVOT_DST)

    for word, repl in RENAMES.items():
        # `(?!\s*\[)` keeps an INDEXED read on the chart's own series — see the header.
        pattern = re.compile(r"(?<![\w.])" + word + r"(?![\w])(?!\s*\[)")
        block, n = pattern.subn(repl, block)
        if n != EXPECTED[word]:
            raise SystemExit(
                f"expected {EXPECTED[word]} substitutions of `{word}`, made {n}. The source block "
                "has changed. Re-count against the source and update EXPECTED in the same edit — "
                "do NOT relax the check, it is the only thing standing between a rename and a "
                "state machine quietly reading the wrong timeframe."
            )

    block = block.replace("type SMCStructure\n", "type SMCStructure15\n", 1)
    old_sig = "method process(SMCStructure st, float ph_val, float pl_val, string prefix, color bull_col, color bear_col) =>"
    new_sig = (
        "method process15(SMCStructure15 st, float ph_val, float pl_val, string prefix, "
        "color bull_col, color bear_col, float _o, float _h, float _l, float _c, int _pbi) =>"
    )
    if old_sig not in block:
        raise SystemExit("the `process` signature has changed — re-point old_sig at it.")
    block = block.replace(old_sig, new_sig, 1)
    # the two helper methods the type carries also draw, and they read the renamed globals
    block = block.replace(
        "method create_ash(SMCStructure st", "method create_ash15(SMCStructure15 st"
    )
    block = block.replace(
        "method create_asl(SMCStructure st", "method create_asl15(SMCStructure15 st"
    )
    block = block.replace("st.create_ash(", "st.create_ash15(")
    block = block.replace("st.create_asl(", "st.create_asl15(")

    header = (
        "// ─────────────────────────────────────────────────────────────────────────────\n"
        "// DERIVED FILE — DO NOT EDIT BY HAND.\n"
        "// Generated by indicators/strategies/tools/derive_htf_structure.py from\n"
        f"// {SOURCE.name}. Edit the SOURCE block and re-run the script; an edit made here is\n"
        "// lost on the next run and, worse, makes the two instances disagree in the meantime.\n"
        "// ─────────────────────────────────────────────────────────────────────────────\n"
    )
    return header + block


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing {SOURCE}")
    out = derive(SOURCE.read_text())
    OUT.write_text(out)
    print(f"wrote {OUT.relative_to(STRAT.parent.parent)} — {len(out.splitlines())} lines")


if __name__ == "__main__":
    main()
