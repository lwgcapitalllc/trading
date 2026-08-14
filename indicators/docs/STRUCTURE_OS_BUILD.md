# Structure OS / SMC Engine — Rebuild Snapshot

**Status:** 🔨 **IN PROGRESS — Stage 2b ~95% validated, Stages 3–4 NOT STARTED** (blocked on chart-by-chart validation, which only a human at TradingView can do). ⚠ **A separate track from the `mpc_assistant.pine` line the `engines/` Python engines were ported from** — nothing here feeds a live bot.

**Purpose.** Cross-session handoff for the from-scratch, pullback-only rewrite of the
"Structure OS" / "SMC Engine (OrthosLabs)" indicator. Read this first when resuming.
Keep it accurate — update status as each stage is validated on a real chart.

**Source of truth (in priority order):**
1. `docs/market_structure_engine_spec.md` — the rules, written from the TV overview. Verified accurate against the public page on 2026-06-20.
2. The public TradingView page: https://www.tradingview.com/script/SVUkldyr-Structure-OS/ (source code is private; description is public).
3. The settings-panel screenshots Aaron pasted (2026-06-20) — see Settings below.

**Files:**
- `indicators/engines/smc_engine_v2.pine` — the NEW pullback-only build (this rewrite).

---

## The one rule that defines everything

Swings are found **only** by the 3-candle pullback method. NO `ta.pivothigh` / `ta.pivotlow`,
NO lookback-window pivots, NO min/max range scan to place swings.

- Confirm a **swing HIGH**: 3 consecutive candles, each closing **below the previous candle's LOW**.
- Confirm a **swing LOW**: 3 consecutive candles, each closing **above the previous candle's HIGH**.
- **Reset on new extreme:** a new high (while seeking a high) / new low (while seeking a low) before
  the count hits 3 resets the count to zero at the new extreme.
- **Strictly consecutive:** any bar that fails the test resets the count to zero.

---

## Settings (VALIDATED from screenshots — all are bool toggles, no numeric inputs)

Group: **STRUCTURE**

| Input | Default | Tooltip |
|---|---|---|
| Show Swing Structure | ON | Main swing highs/lows using the 3-candle pullback rule. |
| Show BOS Labels | ON | Break of Structure — continuation in the current trend direction. |
| Show CHoCH Labels | ON | Change of Character — reversal against the current trend. |
| Show Swing Point Labels | ON | HH, HL, LH, LL labels at confirmed swing points. |
| Show Swing Level Lines | ON | Horizontal lines at active swing high/low levels. |
| Show Unconfirmed Levels | ON | Dotted line at candidate swing point before 3-candle confirmation. |
| Show Internal Structure | **OFF** | Structure within the current swing range. Same 3-candle rule. |
| Show Internal BOS | ON | Internal Break of Structure labels. |
| Show Internal CHoCH | ON | Internal Change of Character labels. |
| Show Internal Point Labels | ON | iHH, iHL, iLH, iLL labels at internal swing points. |
| Show Internal Level Lines | ON | Dashed lines at active internal high/low levels. |
| Show Historic Internal Structure | ON | Keep internal structure labels and lines from previous swing ranges. Off = only current swing range internals. |

There is also a **SESSIONS** group below STRUCTURE in the real indicator — out of scope (spec excludes sessions).
Colors live under the **Style** tab in the original; in v2 they are temporary `input.color`s in a "Colors" group.

---

## ⚠️ KEY FINDINGS (2026-06-20, daily gold, both indicators same chart) — READ FIRST

These reverse the original Stage-1-in-isolation plan. The swing map cannot be validated without breaks.

**Finding A — labeling is a BREAK event, not a detection event.**
Theirs labels the *currently active* swing high/low literally **"Swing High" / "Swing Low"** (drawn solid).
Only when that swing is **broken** does it get relabeled **HH / HL / LH / LL**. So HH/HL/LH/LL appear at
break time on the OLD (just-broken) swing. Our Stage 1 labelled every confirmed swing HH/HL immediately —
wrong. Must implement: active = "Swing High"/"Swing Low"; on break → reclassify to HH/HL/LH/LL + BOS/CHoCH.

**Finding B — swing structure is RANGE/BREAK-GATED, which sets the scale.**
Counts on identical charts: daily low/high strict = 3, theirs = 9; 4H strict = 5, body = 22, theirs = 11.
No pullback threshold reproduces theirs — strict too sparse, body too noisy. The reason theirs is selective
is NOT strictness; it is that a **major (swing-level) point only forms when price exceeds the current trading
range (a break)**, then the 3-candle pullback confirms the new extreme. Break-gating is what separates
MAJOR (swing) from MINOR (internal) and produces the clean ~9/year majors. Our pure free-running alternating
pullback has no range concept, so after confirming a low it seeks ONE high and rides a 10-month rally to the
very top — missing every intermediate major swing. THIS is the bug, and it is architectural, not a threshold.

**Consequence — corrected architecture (close to the OLD smc_engine.pine skeleton):**
1. Maintain a trading RANGE = active swing high (ash, "Swing High") + active swing low (asl, "Swing Low").
2. On a body-close beyond a boundary → BREAK. Label BOS (with trend) or CHoCH (against, flips trend).
   The broken swing gets relabelled HH/HL/LH/LL and stored as last_conf_high/low.
3. After a break: find the protected opposing extreme (lowest-low / highest-high scan since the break) = new
   active swing on that side; then run the 3-candle pullback to confirm the NEW swing in the break direction
   → it becomes the new active "Swing High"/"Swing Low" (dotted candidate → solid on confirm).
4. The pullback detector (type PB) is REUSED as the confirm-the-new-swing step — not as a free-running
   alternator. The min/max scan for the protected extreme after a break is legitimate (it is NOT a pivot
   lookback for detection; it just locates the protected level — the new swing is still pullback-confirmed).
5. Internal engine (Stage 3) = the same 3-candle pullback scoped WITHIN the range = the minor swings our
   single engine currently over-plots (the 4H body 22 ≈ 11 swing + 11 internal). Hidden by default toggle.

**Confirmation rule:** body (close beyond prior open/close) is the working detector base; low/high strict is
too sparse (daily=3). Keep the temporary diagnostic input until break-gating is in and re-checked.

**DETECTOR VALIDATED (2026-06-20, daily gold, body mode):** ours 9 vs theirs 9, points overlap (3 regions
matched). Remaining diffs: (a) active labeling — ours shows HH on the latest swing, theirs shows
"Swing High"/"Swing Low"; (b) one consolidation swing each engine picks differently (ours Jul "LH", theirs
Apr) = swing/internal selectivity. Both are addressed by the break layer (Stage 2) and internal split (Stage 3).
KNOWN LIMITATION of the current free-running detector: on lower timeframes it over-plots (4H body 22 vs
theirs 11) because it does not yet separate swing from internal — that is Stage 3.

---

## Architecture — TWO engines, ONE shared confirmation type

The spec/docs require two independent engines on the same timeframe with **identical** confirmation
logic: **SWING (external)** and **INTERNAL (inside the swing range)**. v2 implements this as a single
reusable `type PB` (the 3-candle pullback tracker) instantiated **twice**:

- `var PB swing = PB.new()` — the EXTERNAL engine. Live now (Stage 1).
- `var PB internal = PB.new()` — the INTERNAL engine. Added in Stage 3. Same bars, same `step()`.

Why one type, two instances (not two code paths): it guarantees both engines use the exact same rule and
we can't drift into two different confirmations. If validation ever shows internal must differ, branch
inside `PB` with a flag — do NOT fork the type.

The internal instance adds only two WRAPPER concerns on top of the shared `step()` logic (no change to the
confirmation rule itself):
1. **Scope** — only confirms/plots between the current swing low and swing high.
2. **Reset on swing break** — when the external engine fires a BOS/CHoCH, wipe it: `internal := PB.new()`.

Caveat: the original's source is private, so we can't confirm it literally reuses one class twice. But
"same logic, two scopes" is what the docs describe, and one shared type is the correct way to enforce it.

---

## Design decisions (carry these forward)

1. **No numeric inputs.** Detection has zero tunable params. "3" is a fixed constant.
2. **Confirmation test = close vs previous bar's low/high** (not close-vs-close, not body). This is the
   verbatim wording from the TV page. We do NOT additionally require close<open ("bearish") — the page's
   mechanical test is purely "close beyond the previous candle's low/high." (OPEN Q1.)
3. **Alternating pivots.** After a swing high confirms we seek a swing low, and vice versa. One candidate
   tracked at a time, except at chart start (neutral bootstrap tracks both until the first confirmation).
4. **Seeding the next leg.** When a high confirms, the new candidate low is seeded as the lowest low from
   the swing-high bar forward to now (bounded scan). Symmetric for lows. This places the opposing extreme
   correctly without a global lookback. (This scan is for SEEDING the live candidate only — it is NOT how
   swings get confirmed. Confirmation is still pullback-only.)
5. **BOS / CHoCH model (Stage 2).** Range = last confirmed swing high (top) + last confirmed swing low
   (bottom). A body **close** beyond a boundary (wick does not count) = break. BOS if in trend direction,
   CHoCH if against (flips trend). On break, that boundary is "consumed" (cleared) until the detector
   confirms a new swing on that side, so a break fires once, not every bar.
6. **HH/HL/LH/LL** are labelled on the detector's confirmed swings, by comparing to the previous swing of
   the same type. BOS/CHoCH are separate labels at the break point. (Panel has separate toggles for both.)
7. **Internal engine (Stage 3)** reuses the SAME pullback tracker type, scoped to the current
   [swing low, swing high] range, reset on every swing-level BOS/CHoCH. Output iHH/iHL/iLH/iLL + iBOS/iCHoCH,
   drawn dashed. Default OFF.
8. **Line styles:** candidate = dotted, confirmed swing = solid, internal = dashed.

---

## Open questions — must verify against the real chart

- **Q1. [RESOLVED — not a threshold problem]** Counts on identical 4H gold chart: low/high strict ≈ 5,
  body ≈ 22, close ≈ looser still; **theirs ≈ 11** — sits BETWEEN our strict and loose. No single pullback
  strictness reproduces 11. Conclusion: theirs' selectivity is STRUCTURAL, not a threshold. **Theirs shows
  only SWING-level (major) structure; the extra pullbacks our single Stage-1 engine plots are INTERNAL-level
  (toggled OFF in theirs).** body ≈ 2× theirs ≈ (their 11 swing) + (~11 internal) lumped together because
  Stage 1 doesn't yet separate swing vs internal. The separator is the range + BOS/CHoCH logic (Stage 2/3).
  Working detector base = **body** (catches the full candidate set to feed both layers). GATE before Stage 2:
  confirm theirs ⊆ ours (we have all their points + extras). If theirs has orphan points we miss → real
  detection bug, debug first.
- **Q1b.** Does confirmation require the candle to also be bearish/bullish (close<open / close>open), or is
  "close beyond the previous candle" the whole test? v2 currently uses close-beyond-only.
- **Q2.** First break when trend is still neutral (0) — label it BOS by convention? v2 plan: yes.
- **Q3.** Inside bars (high<=prevHigh and low>=prevLow) — do they count toward the pullback or are they
  skipped? v2 currently counts every bar. Old version skipped inside bars.
- **Q4.** Exact placement of the swing line/label x-coordinate vs the original (cosmetic).
- **Q5.** When does the candidate dotted line first appear relative to the original's behaviour.

---

## Build stages & status

- [x] **Stage 0** — Settings panel parity + design locked. (this doc)
- [~] **Stage 1** — Pullback detector exists and works as a candidate generator, BUT the pure free-running
      alternating model produces the WRONG SCALE and labels HH/HL too early. Superseded by the corrected
      architecture above (break-gated). The PB type is kept and reused; the execution/rendering section needs
      the range/break layer. Detector base = body.
- [x] **Stage 2 (free-running) — REJECTED.** Built it as a break-LABEL layer on top of the free-running
      detector. DISPROVEN on daily: theirs goes completely silent for the Mar–Jun 2026 decline because that
      stayed inside the range [4000, 5600] — **theirs only makes new swing structure on a range BREAK.** Ours
      kept plotting swings inside the range. Conclusion: swing confirmation MUST be break-gated, not free-running.
- [~] **Stage 2b (break-gated) — PARTIALLY VALIDATED (~95%), NOT DONE.** As of 2026-06-20:
      • Swing points (Swing High/Low + HH/HL/LH/LL): validated on daily gold at ~95% vs theirs. Remaining
        diffs are sporadic, bidirectional edge cases (see FINAL DIAGNOSIS below) — needs future refinement.
      • BOS / CHoCH labels: BUILT but NOT YET TESTED against theirs (those toggles were off during all swing
        comparisons). Must validate before calling Stage 2 complete.
      • Still pending: choch_lock, exact protected-extreme tie-breaks, hardcode body / remove diagnostic input.
      Engine rebuilt as a range/break state machine (the original
      smc_engine.pine skeleton, pivot-free):
        • Bootstrap: free-running PB seeds the first range (ash="Swing High", asl="Swing Low"), then it is
          retired.
        • Waiting state: a body close beyond ash/asl = BREAK. BOS (with dir) / CHoCH (against → flip dir).
        • On break: broken swing → HH/HL/LH/LL (last_conf_*); protected opposing extreme (lowest-low /
          highest-high scan since the broken swing) becomes the new active swing; then pullback-confirm the
          NEW swing in the break direction (dotted candidate → solid "Swing High"/"Swing Low").
        • No new swing structure forms inside the range → matches theirs' silence. Internal swings = Stage 3.
      Validate on DAILY first. KNOWN simplifications vs old code: no choch_lock yet; dup-protected-extreme
      handled by a simple loc check; protected scan capped at 500 bars.
      BUGFIX (2026-06-20): first cut showed all highs but NO lows. Cause: an early dip nulled asl mid-low-
      confirmation, then a bullish break fired while asl==na; low-creation was wrongly guarded by `not na(asl)`,
      so asl stayed na forever and every later break skipped lows. Fix: a break now ALWAYS sets the protected
      opposing swing (from the scan) and only conditionally demotes the previous one. Symmetric for highs.
      STATUS after bugfix (daily gold, body): ALMOST PERFECT. ours is now a clean SUBSET of theirs — every
      ours plot overlaps theirs; theirs has sporadic EXTRA swings ours misses (sharp pop-and-pullback moves).
      So we slightly UNDER-detect. NEXT PROBE: test confMode="Previous candle close" (loosest) on daily — does
      it fill the missing extras without over-plotting? If yes → hardcode close, drop the diagnostic input. If
      it over-plots → it's a swing-LOCKING nuance (where the post-break swing high/low is pinned), not a
      threshold; investigate that.
      PROBE RESULT (2026-06-20): confMode is NOT the lever — "close" (loosest) did NOT add the missing extras;
      "low/high" removed good ones. So BODY stays.
      FINAL DIAGNOSIS (2026-06-20): the remaining diffs are BIDIRECTIONAL and sporadic. In some choppy spots
      OURS splits a move into an extra HH/HL that theirs merges; in others THEIRS splits one that ours merges.
      Neither is a subset of the other. This is a sub-swing LOCKING-timing nuance (when a swing locks relative
      to a new extreme printing), not a threshold — no single rule closes both directions (tightening fixes one
      circle, worsens the other). Match is ~95%+: all major swings, BOS/CHoCH, quiet-in-range, and active
      labels line up. Exact parity on the edge cases is not achievable without the original's source. DECISION
      POINT: accept + lock body + move to Stage 3 (internal), vs. keep chasing edge cases (low ROI).
      Scope: 3-candle tracker, dotted candidate, solid confirmed swing lines, HH/HL/LH/LL labels.
      Inputs wired: Show Swing Structure, Show Swing Point Labels, Show Swing Level Lines, Show Unconfirmed Levels.
      Confirmed swing lines currently extend forever (no break logic yet — that's Stage 2).
- [ ] **Stage 2** — Trading range + BOS/CHoCH (close-only breaks, trend flip, consume-on-break, line stops at break).
      Wires: Show BOS Labels, Show CHoCH Labels.
- [ ] **Stage 3** — Internal engine (reuse tracker, scoped to range, reset on swing break, dashed, iBOS/iCHoCH/iHH...).
      Wires: Show Internal Structure, Show Internal BOS/CHoCH, Show Internal Point Labels, Show Internal Level Lines, Show Historic Internal Structure.
- [ ] **Stage 4** — Side-by-side compare vs the real indicator on multiple symbols/timeframes; resolve Q1–Q5; replace old file.

**Currently blocked on:** chart validation of Stage 1 by Aaron (compare v2 swing points to the real
indicator on the same chart). Until that's confirmed, do not build Stage 2 — a wrong swing map breaks everything downstream.

---

## Changelog
- 2026-06-20 — Created. Spec verified vs TV page. Settings captured. Design locked. Stage 1 built (unvalidated).
