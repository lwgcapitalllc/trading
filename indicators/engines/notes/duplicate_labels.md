# Notes — The duplicate-label defects (tied-extreme and refused-wick swings)

The write-ups of two duplicate-label defects found in the tied-extreme swing detection and the refused-wick guard. Moved VERBATIM out of `indicators/engines/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 The refused-wick duplicate label (fixed 2026-08-21) — the sequel, and the tie guard could not see it

Three symptoms, one cause: a doubled `LL`, an `ASH` printed beside an `HH`, and a bogus `HH` after
it. **Structure breaks on a CLOSE; the post-break rescan reads the WICK** — over a window bounded by
the opposite side's last confirmed bar, which reaches back before the swing just confirmed. So it
resurrects a wick the break rule already refused and installs it as the new active swing: earlier
than, and more extreme than, the swing just labelled.

The 2026-08-20 tie guard fires only on an EXACT price match and so could never catch it. The fix
folds into that guard — *a rescan may only install a swing strictly NEWER than the one just
confirmed* — costing one line of code per site.

⚠ **`processMTF` in `mpc_jarvis.pine` needed it too**, unlike the tie guard: this snap moves the
VALUE, and `st.ash := highest_val` is what the next break is tested against. Its "deliberately NOT
repeated here" note was corrected in place.

⚠ **Not cosmetic** — `fibo_ash := st.ash`, so it moves the fib anchor, E1-E4 and the TP ladder. The
measurements, the traced bars and the outstanding parity-gate position are in
`engines/market_structure/CLAUDE.md` → *The 2026-08-21 refused-wick fix*, and are not repeated here.

## 🔴 The tied-extreme duplicate label (fixed 2026-08-20) — one swing, two labels that never go away

Aaron read an `LL` and an `HL` printed on the *same* 15m swing low and asked whether he had broken
something recently. He had not. The logic is as old as the port and was byte-identical here and in
`engines/market_structure/engine.py` — **rule 14 in the wild: the parity gate said the two agree,
and both were wrong the same way for the engine's whole life.**

**The mechanism, in one line:** when two bars print an identical extreme the post-break rescan (a
strict `<` running newest-to-oldest) anchors on the **later** bar, while the label for that swing is
already drawn on the **earlier** one — so `already_conf_low`, which compares bar index as well as
price, reads it as a new swing and draws a second label. **Pine cannot delete those labels, so they
stack forever.** The full trace, the before/after numbers and the reasoning live in
`engines/market_structure/CLAUDE.md` → *The 2026-08-20 tied-extreme fix*, and are not repeated here.

**What changed:** two guards, one per side, each keeping the original anchor when the rescan
ties the last confirmed extreme. Applied to **all five** engine files carrying this state
machine — `mpc_jarvis.pine`, `structure_engine.pine`, `structure_engine_export.pine`,
`fib_export.pine`, `mss_sweeps.pine` — plus the ten files in `strategies/tradingview/`.
**Sixteen Pine files hold copies of one engine, and a fix applied to one of them is a fix that
has diverged from fifteen.**

🔴 **`structure_engine_export.pine` HAD TO MOVE WITH THE PYTHON, AND IT IS THE ONE THAT WOULD
HAVE BITTEN SILENTLY.** It plots `px_bull_bos_l_ago` / `px_bear_bos_h_ago` — columns derived
from the very bar indices this guard changes — and those columns are what `compare_tradingview.py`
diffs. Fixing Python and leaving the export alone would make the next parity run go RED on tie
bars and read as *"the fix broke parity"*, when the truth is the two sides were being asked
different questions. ⚠ **When a fix touches a value the export EMITS, the export is part of the
fix, not a follow-up.**

✅ **`fib_export.pine` USED TO run its high-side steps in the OPPOSITE order to the other four**
— it promoted and *then* rescanned, where they rescan and then promote. **Re-synced 2026-08-20 to
the reference order (rescan, then promote); it is no longer the odd one out.** The note above was
correct and is kept because the check it describes is the right one: the guard did land in the
same place (immediately before `st.bear_bos_high`), the ordering WAS checked per file rather than
assumed, and one file differing out of sixteen is exactly why you check.

🔴 **But the per-file ordering check did not catch what was actually wrong with this file, and
that is the lesson worth keeping.** `fib_export.pine` has **never** carried the fallback-promotion
`else` branch that landed in the 2026-07-08 structure re-sync (`f2a8411`) and that
`mpc_jarvis.pine`, `structure_engine.pine`, `structure_engine_export.pine` and the canonical
Python engine all have — `git log -S'fallback_is_hh'` on that path returns nothing, so this is
drift from birth, not a regression from the tied-extreme fix. ⚠ **The guard was NOT inert** — the
normal path promotes before it, so on any bar with an active swing high it behaved correctly.
**The divergence was the `st.ash IS na` path alone**: the reference promotes `last_conf_high` to
the rescanned high and prints an HH/LH label there, and this file promoted nothing and printed
nothing, leaving a stale value behind. **A guard COUNT proves presence; an ORDERING check proves
placement; neither one can see a branch that was never there at all.** The only thing that found
it was diffing the whole method against the reference.

**The re-sync (2026-08-20):** fallback branch added, and the block reordered so the extreme scan
runs before the promotion — the fallback reads `highest_val`/`highest_loc` and cannot see them
otherwise. ⚠ **The reorder is behaviour-preserving, CHECKED not argued**: the scan reads only
`high[i]` and `st.last_conf_low_loc`, and the promotion block writes neither, so the normal path
is bit-identical. The two `process()` methods now diff to **zero logic differences** — all that
remains is the `f_swingCol` colour helper and the `showExternal` display toggle, neither of which
exists in this harness by design. ✅ **COMPILED AND GATED 2026-08-20** — Aaron pasted it into
TradingView and exported 20,990 M15 bars (`VANTAGE_XAUUSD, 15_b201e.csv`); `compare_fib.py
--warmup 900` exits **0** across Structure + Sniper + Internal. **The re-sync did not move a
single fib output on 20,991 bars, which is the evidence that the reorder is harmless** — it
changes the normal path on every bar, so a green across all of them is a real result.
⚠ **The ADDED fallback branch is a different matter: instrumented, it was reached 0 times in
those 20,991 bars.** It is present and correct-by-construction against the reference, and it is
UNTESTED by this export. ✅ **Macro fib closed the same night** — a 5m export
(`VANTAGE_XAUUSD, 5_84d6c.csv`, 20,376 bars) drove `compare_fib.py --warmup 900` to **0** at
scope Structure + Sniper + Macro + Internal. **All four fibs green against the re-synced
harness.** ⚠ **The added fallback branch was reached 0 times on that export too** — 41,368 bars
across two timeframes have now failed to enter it.

⚠ **The high-side guard is NOT placed symmetrically with the low-side one, and that is deliberate.**
The two sides run their steps in opposite order — the low side promotes then rescans, the high side
rescans then promotes — so the high-side guard sits immediately before `st.bear_bos_high`. Placed
beside its scan it reads a `last_conf_high` the promotion has not written yet and silently does
nothing, which is exactly what the first attempt did. **It looked right and changed nothing.**

⚠ **`processMTF` carries the same two guards and was left alone on purpose.** `f_mtfStruct` returns
`[dir, sEv]` only, `dir` is decided by close-vs-price breaks, and no `*_loc` in that method has any
consumer — checked, not assumed. **The 1m/15m/4H confirmation rows were never affected by this.** A
comment at each site records that, so the next reader does not "fix" a no-op into a token-ceiling
problem. See `mpc-assistant-token-ceiling`: this file has no room to spend on nothing.

🔴 **NOT PARITY-GATED — the gate cannot run on this machine.** `compare_tradingview.py` needs an
export carrying `px_ash`/`px_asl`/`px_dir`, and the only CSVs present are strategy exports. **Rule
22 blocks the commit until `structure_engine_export.pine` is put on a chart and exported.** The
Python half is covered by `engines/market_structure/tests/test_duplicate_swing_labels.py` (watched
RED), but **that proves the Python, not the Pine** — the Pine change is unverified until the gate
runs, and it has not been pasted into TradingView either, so it is not even known to compile.
