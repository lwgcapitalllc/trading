# Notes — PDH/PDL vs session high/low — the tie-break and label bugs

The fix making PDH/PDL win a tie against a session high/low at the same price, the invisible-label reservation bug it exposed, and the mitigated-level redraw fix. Moved VERBATIM out of `indicators/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 2026-08-07 — PDH/PDL WIN A TIE AGAINST A SESSION HIGH/LOW AT THE SAME PRICE

Aaron: when the previous day's low IS the New York session low, the chart printed `PDL` and
`NY L` stacked on one line. **Drawing only — labels. No line, level, sweep, arm or trade moves.**

**The nudge was already working, which is why this reads as a different bug than it is.**
`f_liqLabels()` spaces colliding labels apart by `lblOff`, so two labels at one price were not
overlapping — they were being *separated*, into two names for a level only one of them needs to
name. The complaint is duplication, not collision.

**Fix:** a session H/L label whose price matches the active PDH/PDL is hidden (`textcolor` na, the
same mechanism a mitigated level already uses) **and left out of the nudge**, so the collision pass
does not space the survivors around an invisible label. Daily wins; the session label comes back the
moment the daily one does not exist — hence the test reads `d_hLbl`/`d_lLbl`, not just the prices
(a mitigated PDH is deleted on the next new day, and then there is nothing to defer to).

⚠ **The tolerance is ONE TICK and that is not a fudge factor.** Both numbers are maxima over the
same bar highs, so a real duplicate is EXACT; a level a few ticks away is a DIFFERENT level and the
existing nudge is the right answer for it. A visual-gap tolerance would start hiding real levels.

⚠ **Scope is deliberately PDH/PDL vs the three session levels only.** PWH/PWL and the H4 sweep can
also coincide with a session level and are untouched — a priority ORDER across all four tiers is a
bigger decision than the one asked for, and the JARVIS `recentBSL`/`recentSSL` block already has its
own (contradicted) ordering recorded above.

### 🔴 …and the same block was reserving space for labels nobody could see

Aaron, same day: "Ldn L" sat at a different distance from its line than its neighbours, and **H4 H
and H4 L were at different distances from their own two lines.** One cause explains both, and it is
not the creation offsets — every label is born at `price + lblOff` (highs) or `price - lblOff`
(lows), verified line by line across all eight files. It is the nudge.

**A MITIGATED daily/weekly/session level is hidden by blanking its textcolor, and the label OBJECT
survives.** The collision pass guarded only on `not na(<lbl>)`, so an invisible label was still
pushed into `liq_y`, still took a slot, and still shoved every visible label above it up by a full
`lblOff` — **with nothing on screen to explain the gap.** That is precisely "this tag's offset is
wrong": the label it was making room for cannot be seen.

⚠ **It explains the H4 pair too, and that is the tell.** H4 is the one tier that is never hidden —
a swept H4 stays on the chart in grey — so H4 H and H4 L both keep their space. What moved them
apart was a hidden Asia/Ldn level sitting under ONE of them and not the other.

**Fix:** the visibility term is added to each of the ten daily/weekly/session guards.
⚠ **The two families need DIFFERENT terms and this is not cosmetic.** `mpc_jarvis.pine` and
`m15_playbook.pine` hide a mitigated label only when `showMitLiq` is off, so their test is
`(not mit or showMitLiq)`; the strategy family's `f_liqMitigate` blanks the textcolor on `newMit`
**unconditionally**, so `i_showMitigated` does not resurrect the label there and the test is plain
`not mit`. Using the assistant's form in the strategies would keep reserving the slot the day
anyone flips that flag.
⚠ **H4 and PWC are deliberately NOT filtered** — both stay visible, so both genuinely need space.

⚠ **What is NOT changed, and is the remaining reason two visible tags can differ: the nudge is
one-directional.** It walks bottom-up and only ever pushes UP, so in a real cluster the lowest label
keeps its natural offset and everything above it drifts. That is the feature doing its job; it is
only misleading when it is spacing around a ghost, which is what this fixes.

**The standing lesson is small and general: hiding a drawing by making it transparent leaves an
object that every layout pass downstream still counts.** The chart said one thing and the geometry
was computed from another.

### 🟢 Mitigated levels are drawn again — and the dedupe was deferring to an invisible label

Aaron: "I also want the mitigated dotted lines for the sessions that break by a candle. I had it
before and it's gone." **`showMitLiq` false → TRUE in `mpc_jarvis.pine`.** It had been the
`Show Mitigated Liquidity Lines` input (default OFF) and the Chart Tools lock-down froze it at its
default as a constant — **which locked in the answer nobody had asked for.** A broken level now
freezes at the break bar, goes dotted and grey, and keeps a greyed label.

⚠ **ONE flag, THREE tiers.** PDH/PDL and PWH/PWL keep their broken levels too, not only the
sessions — which is exactly what the old input did (its tooltip named all three), so this restores
the behaviour rather than widening it. Split per tier if the daily and weekly read as clutter.
⚠ **Nothing accumulates** — each tier deletes and redraws its own line when its pool rolls, so
there is at most one broken level per tier. What changes is LIFETIME: the new-day wipe is skipped
while this is on, so a broken level survives to its own tier's next roll (a swept PWH most of a
week) instead of being cleared at NY midnight.

🔴 **Checking it exposed a hole in the PDH/PDL dedupe shipped hours earlier, and it is the SAME
defect as the reserved-slot one, from the other side.** `liqDupH` tested only `not na(d_hLbl)` — but
a mitigated PDH is INVISIBLE while its label object lives on until the next new-day wipe. So a
swept, invisible PDH went on suppressing a perfectly visible session tag at the same price, and the
level lost its name with nothing on screen holding the place. **Fixed in all eight files**: the
dedupe now defers only to a daily label that is actually drawn. ⚠ **The term differs by family for
the same reason the slot filter does** — `(not mit or showMitLiq)` in the indicator pair, plain
`not mit` in the strategies.

⚠ **The strategy family is deliberately NOT switched on.** Its `i_showMitigated` has always been a
hardcoded `false` — nothing was lost there, so nothing is being restored — and its
`f_liqMitigate` still blanks a mitigated label **unconditionally**, which is the pre-2026 version:
flipping the flag there would draw a faint unlabelled stub, the exact complaint the indicator's own
comment records fixing. Port that label branch first if it is ever wanted.
⚠ **`m15_playbook.pine` still has the real INPUT** (default off) and was left alone — it is a
control, not a lock, so it can just be ticked.

---

**All three changes applied to all eight files that carry the block** (the `showMitLiq` flip is the
indicator only), identical text:
`sos_fade_strategy.pine`,
`b_leg_strategy.pine`, `bos_strategy.pine`, their three exports, `mpc_jarvis.pine` and
`m15_playbook.pine`. ✅ **The three export mirrors were re-diffed after the edit and still
differ from their parents by exactly the `strategy()` title line plus their appended parity block.**
⚠ **NOT COMPILED** — no local Pine compiler, and these files have hit CE10117 twice; the change adds
three locals and six two-branch `if`s inside an existing function, so **zero new main-body
statements** (CE10295 unaffected) but not zero tokens. ⚠ **No input was added, renamed or reordered,
so no "Reset settings to defaults" is needed.**
