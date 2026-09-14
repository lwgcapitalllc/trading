# Notes — Parity gate — dated fixes

The gate skipping the export's final calendar day, and the 2026-07-22 re-sync. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Deliberate deviations from the Pine (per the framework)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Deliberate deviations from the Pine (per the framework)*.

🔴 **PYTHON-ONLY FIELDS — THE GATE IS BLIND TO THESE, AND THERE ARE NOW TWO (audited 2026-08-12).** A field with no Pine input has no `cfg_*` column, so `compare_strategy.py` **can never configure a non-default run of it** — the green gate says nothing whatever about these branches. This is rule 14 with a specific shape: *a gate proves nothing about a branch neither side entered*, and here one side cannot enter it at all.
- **`exec_no_gap_arm`** — no `execNoGapArm` input exists in either SOS Fade Pine. Any result measured with it moved was taken with one implementation only.
- **`exec_poi_source`** — `execPoiSource` appears in **zero** `.pine` files. The Pine POI seam was reverted (`indicators/CLAUDE.md` records it); the Python side was not reverted with it, so this field outlived its counterpart.

⚠ **Before trusting any SOS Fade measurement, check whether it moved one of these two.** ⚠ **The fix is a decision, not a tidy-up:** either add the Pine inputs and re-export so the gate can see them, or drop the fields. Leaving them is the one option that keeps a live strategy carrying dials nothing verifies. Detail: `strategies/python/sos_fade/docs/SOS_FADE_BUILD_NOTES.md`.

   **It does exactly what it promises and the swap goes to zero** — the charge falls 12.04R → 5.64R
   and what remains is pure spread. **You save 6.4R of swap and give up 76.1R of edge to do it, a
   12:1 bad trade.** The entries are IDENTICAL (161 either way, all matched on entry bar); **73 of
   them are cut short**, and held to the end those 73 made 140.39R against 64.28R cut at the close.
   The worst single one ran 274 hours for **+23.96R** and becomes a **−0.46R** scratch after 3.8h.
   ⚠ **It does not merely shave the runner, it INVERTS the long side: longs go +70.96R → −12.10R.**
   Shorts survive (+64.98R → +31.38R) because gold's short swap is a CREDIT (+26.98 points/night on
   Vantage) — over the run shorts were paid 2.14R of swap while longs paid 8.55R. So "the swap is
   expensive" is a statement about LONGS only, and the fix for it cannot be a rule that hits both.
   **The mechanism is structural, not a tuning artefact:** the runner trails on confirmed structure
   (`Structure + % ratchet`), and structure takes days to build — a hard 17:00 NY exit caps every
   runner at one session. This is the same finding as Run 12 from a new direction: the edge is in
   the tail, and anything that truncates the tail costs more than the friction it removes.
   ⚠ **Do not read the earlier figure recorded here** (6.5 months / 32 trades / OFF $39,454 vs ON
   $19,813, measured 2026-07-16). Same direction, but 4 overnight trades is not a sample and the
   dollars predate the phantom-exit fix and the layered costs. The cost table in the build notes supersedes it.
   (This param was DEAD CODE until 2026-07-16 — `_in_flat_window` read only `sig.ny_hour`, so
   "minutes left" was always a multiple of 60 and never hit the ≤15 window. Any A/B run before that
   date compared a flag against itself.)
2. ~~**Sizing** — real runs swap in the dynamic sizing engine under a ruleset.~~ **No longer true
   as of 2026-07-16:** the bot declares `self_sizing: True`, so real runs keep the Pine's own fixed-%
   sizing (`exec_risk_pct`) and the engine never re-sizes them — this is NOT a deviation any more,
   parity and real runs size identically. See `## Sizing — this bot sizes ITSELF` above.
3. **Fill model** — parity REQUIRES `fill_model="bar"` (the Pine's own intrabar guess, zero costs).
   Real runs set `fill_model="tick"` + `account_profile` + `symbol` for real bid/ask fills and costs.
   See `backtest/CLAUDE.md` A2 — tick mode disagreeing with the Pine is correct, not drift.

### The gate skips the export's final calendar day, and the CODE WAS INNOCENT (2026-09-03)

🔴 **RED FROM 2026-09-02 TO 2026-09-03 ON A DEFECT THAT WAS NOT IN THE BOT.** On a fresh full
export the two sides are identical for **21,702 bars**; the only disagreement was the short side's
stage on the still-forming final day — Python placed a new Day-High liquidity level at
2026-09-03 00:45 and swept it, Pine still pointed at the previous one. **~230 COMPLETED day
boundaries in the same export agree exactly**, which is what makes this settling rather than a
day-roll bug: only the day that has not finished disagrees.

🔴 **THE CUT-OFF IS A DAY, NOT A BAR COUNT, AND COPYING THE SIBLING GATE'S NUMBER WOULD HAVE LEFT
THIS RED WHILE LOOKING FIXED.** `compare_bleg.py` gained the same guard a day earlier sized to its
STRUCTURE lookahead (15 bars) because its unsettled dependency is a swing. This bot's is a DAILY
liquidity line, which is time-based — the divergence sat **65 bars** from the end, four times
outside a 15-bar tail. ⚠ **Nor is 65 the answer**: a number fitted to one export hides the next
real drift that starts inside the tail. `unsettled_tail()` computes the final calendar day from
the export itself, floored by the structure lookahead so a file ending minutes into a new day
still covers unconfirmed swings.

⚠ **The final day is dropped whether or not it happens to be complete** — an export from a live
chart ends mid-day by construction and nothing distinguishes a day that closed from one that
merely stopped. A settled day costs one day of coverage the next export gets back; an unsettled
one costs a red gate nobody can act on. ⚠ **The replay is always the FULL export**; the tail
narrows only what is COMPARED, so the engines stay warm and a drift beginning in the tail shows up
next time.

🔴 **THE FIRST VERSION OF THE GUARD COULD REPORT PARITY IT NEVER CHECKED.** `--tail 99999` compared
ZERO bars and printed `PARITY OK`. It now **refuses** (exit 2), and every `PARITY OK` states how
many bars the verdict rests on — *"could not run"* and *"ran and passed"* must never be the same
outcome, and a narrowed window is invisible without the count. ⚠ **Three distinct exits: 0 agreed,
1 real mismatch, 2 cannot run.**

⚠ **One mutation SURVIVES BY CONSTRUCTION and is named rather than left looking covered**:
truncating the REPLAY instead of the comparison changes nothing observable in a single run, because
the tail sits at the end and no diffed decision depends on it. That invariant only shows on the
NEXT export, so it is enforced by reading the code, not by a test.

### The 2026-07-22 re-sync (the export was 7 days stale)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-22 re-sync (the export was 7 days stale)*.
