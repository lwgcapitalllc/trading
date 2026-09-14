# Notes — Cross-cutting Pine bugs — one fix, many copied files

Four dated incidents where the same rule was copy-pasted across every strategy file and drifted from the indicator or from each other: the gap-cap counting basis, the equal-level wick fix, the refused-wick structure fix, and the tied-extreme structure fix. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 Four files carried a superseded gap cap, dormant, for five weeks (2026-09-10)

`b_leg_strategy.pine`, `bos_strategy.pine` and both export twins counted EVERY gap against
`fvgMaxCount` while their drop scan skipped the ones an equal-level exemption protects. That makes
the exemption a **SWAP**: a protected gap holds a slot, so keeping it evicts an ordinary gap in its
place. `mpc_jarvis.pine` fixed the identical bug on 2026-08-03 and measured it over 40,000 M15 bars
as costing the SOS Fade bot 2 setups and gaining none.

⚠ **It was DORMANT, and that is why nobody found it.** Both files ship `eqExemptFvg` OFF, and with
the exemption off the two forms are identical by construction. The divergence appears only when
somebody ticks the box on a chart — at which point the Pine silently disagrees with the shared
Python engine, which has had the corrected form since 2026-08-06. **A bug held off by a default is
not fixed, it is armed**, and this file already records that lesson from the opposite direction (the
`qty_percent = 0` rung).

✅ **Fixed in all four, byte-identical to `sos_fade_strategy.pine`'s block**, and now checked on every
run: `scripts/check_pine_blocks.py` carries a *gap cap counting basis* spec across all ten Pine
copies, watched RED by reverting one file.

⚠ **NOT COMPILED and NOT GATED.** No strategy export exists on this machine, so no `compare_*.py`
could be run. The change is a no-op at the shipped default by construction — that is the argument,
and it is the whole argument. **Take a fresh export before turning `eqExemptFvg` on in either file.**

## The equal-level wick fix (2026-09-09) — all SEVEN files here, and nothing noticed for a month

`mpc_jarvis.pine` moved equal-high/low mitigation from a CLOSE through the level to a WICK through
it on **2026-08-04**. Every file in this folder stayed on `close` until 2026-09-09, along with the
tolerance (0.1 against the indicator's 0.25) and the level cap (6 against 14). All three are now
synced in `sos_fade_strategy.pine`, `b_leg_strategy.pine`, `bos_strategy.pine`,
`recovery_strategy.pine` and each of their export twins.

🔴 **THE GATES COULD NOT HAVE CAUGHT THIS AND IT IS WORTH UNDERSTANDING WHY.** A `compare_*.py`
asks whether the PYTHON agrees with ONE Pine file. Two Pine files disagreeing with each other is
outside the question it asks. So the indicator and these seven drifted for a month with every gate
that could run reporting green.

✅ **`scripts/check_pine_blocks.py` closes it** — step 14 of `scripts/run_all_tests.sh`. It went red
on 28 findings the moment it existed. ⚠ **It compares each copy against the INDICATOR rather than
against a value typed into the checker**, so a future rule change needs no edit there: move the
indicator, move the copies, it stays green.

⚠ **It matters here more than in a harness: these levels feed the gap-cap exemption, so they change
which GAPS survive, and the entry rule reads gaps.** The trade impact was measured as nil over 6.6
years (see `engines/equal_highs_lows/CLAUDE.md`), which is a fact about this window and this
configuration, not a reason the drift was harmless.

⚠ **An export twin moves WITH its strategy, always.** Twin and strategy are one unit; moving one
alone turns that strategy's gate red and sends the reader at the engine.

## The refused-wick structure fix (2026-08-21) — every strategy file and its export twin

The sequel to the tie fix below, and the tie guard could not see it: structure breaks on a CLOSE
while the post-break rescan reads the WICK, so it resurrects a wick the break rule already refused
and installs it as the new active swing — earlier than and more extreme than the swing just
confirmed. Folded INTO the existing guard, +1 line of code per site.

⚠ **It moves trades, it is not a redraw.** `sos_fade` over 2020-01-01 → 2026-08-06 goes
159 trades / +142.18R → **158 / +140.71R**, drawdown unchanged at 5.61R — inside the 15.06R
run-to-run sd, but real. Every strategy here was verified byte-identical to its export twin
afterwards, since a gate comparing a patched strategy to an unpatched twin compares two engines.

⚠ **No parity gate has run on it** — see the canonical write-up for why it cannot until a fresh
export exists. Mechanism, measurements and traced bars:
`engines/market_structure/CLAUDE.md` → *The 2026-08-21 refused-wick fix*.

## The tied-extreme structure fix (2026-08-20) — all ELEVEN strategy files

Every `strategy(` file here embeds its own copy of the market-structure state machine, and all
eleven carried the same defect: when two bars print an identical extreme, the post-break rescan
anchors on the LATER one while the label sits on the EARLIER one, so the swing gets a second
permanent label. **The mechanism, the measurements and the reasoning live in ONE place —
`engines/market_structure/CLAUDE.md` -> *The 2026-08-20 tied-extreme fix*. Do not restate them
here.**

What matters for THIS directory:

🔴 **`recovery_strategy.pine` DEMONSTRATED THE HAZARD WHILE THE FIX WAS BEING WRITTEN.** It
was forked from `sos_fade_strategy.pine` on 2026-08-19 — one day before the fix — on the other machine,
so it arrived carrying the defect and had to be patched on the way in. **A fork-per-strategy layout
means a bug fixed in sixteen files can walk back in through a seventeenth that was cut from the
pre-fix source, and nothing fails when it does.** ⚠ **Before calling a cross-cutting fix done,
re-run the sweep AFTER pulling** — `grep -rl 'lowest_val' --include='*.pine' .` and count guards.

⚠ **NO STRATEGY'S TRADE BEHAVIOUR CHANGES, and that was measured rather than argued.** The guard
moves bar INDICES, never prices. Every consumer of those indices in these ten files was traced:
label positions, `mid_x`, and `_snS` — the Sniper Zone box's left edge. All drawing. **And the
one path that COULD have moved a price was checked and did not**: the guard also shifts
`last_conf_*_loc`, which bounds the opposite side's rescan window, so a wider window could in
principle find a new extreme. Replayed over 186,759 M15 and 400,000 M1 bars: **identical break
counts and ZERO break-leg price differences.** The bars the window gains sit inside the swing
base, between the two tied extremes, so their highs cannot beat an extreme already scanned.

⚠ **The `_export` twins were changed in the same pass, deliberately.** A strategy and its export
must stay byte-identical in logic or the export stops describing the strategy — and here the
export is the only way the gate can ever see this code.

🔴 **NONE OF THE TEN IS COMPILE-VERIFIED OR PARITY-GATED FOR THIS CHANGE.** `mpc_jarvis.pine`
was pasted into TradingView and confirmed by Aaron; these ten were not, and no `compare_*.py`
has run on any of them. **Paste before trusting.**
