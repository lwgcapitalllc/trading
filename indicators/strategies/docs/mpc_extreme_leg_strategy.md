# `mpc_extreme_leg_strategy.pine` — the run INTO the shift of structure

**Status: WRITTEN, NEVER COMPILED.** Nothing here has been pasted into TradingView. Every number
below comes from `backtest/tools/pre_sos_leg.py`, not from this file. Paste before trusting.

**Run it on a 5-minute chart.** The 15-minute half is aggregated in code, so the chart timeframe
is not a preference — it is the frame the trigger is measured on.

---

## What it trades, and how it differs from A+

The live A+ bot waits for the shift of structure and then fades the retracement into it. This
takes the move that CREATES the shift: from the extreme up to the swing whose break IS the shift.
Same structure stream, different part of the leg — the carve-up the root `CLAUDE.md` describes
under *Trading Philosophy*.

The rule, in full:

1. A liquidity level on the 15-minute chart gets swept — session, previous day, previous week, or
   the previous 4-hour candle.
2. Within 3 hours, the **5-minute** chart puts in its own change of character the other way.
3. The 15-minute trend still points against it, so the swing being aimed at is a change of
   character rather than a continuation.
4. That swing is at least 2 stops away, the stop sitting beyond the extreme of the last 2 hours.

Entry at the 5-minute close. Stop beyond the extreme. Target the swing. The stop does not move.

---

## 🔴 Why the file embeds the structure engine TWICE

The 15-minute half supplies the trend and the target; the 5-minute half supplies the trigger. Both
are the same external state machine on different bars.

**The second instance is DERIVED, never retyped** —
`indicators/strategies/tools/derive_htf_structure.py` regenerates it from the block in
`mpc_h4_sweep_strategy.pine`, renaming the type and method and swapping the four bar globals for
passed-in values. A hand-transcribed copy is a second implementation that drifts the first time
somebody patches one and not the other, which this repo has already had happen across eleven
forked Pine files. **A divergence is now a diff rather than a discovery.** The script asserts the
exact substitution counts and refuses to write on any other number.

⚠ **Regenerate after ANY change to the source block**, including a cross-cutting structure fix:

```
python3 indicators/strategies/tools/derive_htf_structure.py
python3 indicators/strategies/tools/build_extreme_leg.py
```

⚠ **`request.security` was considered and rejected for the 15-minute half.** A state machine has
to be FED; a security call returns a value. Aggregating three closed 5-minute bars is the only way
it sees the same bars a 15-minute chart would, in the same order, with no lookahead. The levels
still use `request.security`, where `[1]` paired with `lookahead_on` is the non-repainting idiom
for a previous completed period — either alone repaints.

⚠ **`ta.pivothigh` cannot see the aggregate**, because the aggregate is not a series. The 15-minute
pivots are the same rule applied by hand over a rolling window of completed 15-minute bars.

---

## ⚠ It breaks the fixed Section 2, and that is a decision for Aaron

The house contract says every strategy carries the same four market-structure toggles. This file
ships **two** — external structure and swing labels. There is no internal engine here, so the
other two would be controls that look like they do something, which is the exact hazard the
contract's own note names.

**Porting the internal engine would be a THIRD copy of a state machine in one file, ~450 lines,
purely to draw with** — in a file that already carries two and has never been compiled. The
compile-token ceiling is the live risk. Left as an open decision rather than done silently: if the
file compiles with room to spare, the internal engine should go in and the section becomes
standard.

---

## The numbers behind every default

All from `backtest/tools/pre_sos_leg.py`, Vantage XAUUSD, 2018-09-13 → 2026-08-23. Full study:
`docs/PRE_SOS_LEG_STUDY.md`.

| default | value | why |
|---|---|---|
| chart / confirmation frame | 5m | 15m confirms too late (target closer than the stop); 1m collapses to +0.002R once the round trip is charged |
| levels must be swept within | 180 min | the window the study measured |
| levels that must agree | 1 | two is better (+0.386R vs +0.296R) and halves the trade count — Aaron's call, not a measurement |
| only against the 15m trend | on | the with-trend half is where the edge is not |
| refuse a target nearer than | 2R | below it the setups have no room to pay |
| look back for the extreme | 120 min | the window the study measured |
| move the stop to breakeven | **off** | arming at 30% costs −0.217R; the best point (~70%) is worth +0.024R |

🔴 **The breakeven default is OFF and that is the measurement, not caution.** A breakeven stop on
this setup converts winners into scratches — the win rate falls 28.1% → 16.2% while losses only
fall 71.9% → 50.9%, because the retracements happen INSIDE the leg rather than before it. Leaving
the stop alone is within noise of the best possible setting and is one less thing to get wrong.

⚠ **Entering on the 15-minute close instead costs about a quarter of the edge** (+0.296R →
+0.223R) and was measured, because it decides whether the file needs two engines at all. It does.
The single-frame stand-in — a bar closing back beyond the sweep bar's extreme — scores +0.082R.
**The faster engine is not a convenience; it is what carries the result.**

---

## What this file does NOT have

No export twin, so **no parity gate can ever run on it** — the same hole
`mpc_realign_strategy.pine` has, and every number it produces will be a lab finding until a twin
exists. No Python port. No confirmation table. No fibs, sessions or internal structure drawing. No
news filter. No scale-in, no TP ladder, no time stop. One position at a time, which is not a
preference: every number behind this file was measured with one slot.

---

## Before this is believed

- It has never been compiled. The token ceiling is the first thing that could stop it.
- 228 trades in 9 years with three losing years inside them (2021, 2023, 2024).
- The rule set was found by testing ~20 combinations and reporting what scored. It survived a time
  split, a knob sweep and a change of broker feed; it is not out-of-sample.
- It reads the same structure stream as A+ on the same instrument, so the two are **not**
  independent. `backtest/tools/overlap_audit.py` has not been run against it.
