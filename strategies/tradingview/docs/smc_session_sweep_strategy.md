# smc_session_sweep_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `smc_session_sweep_strategy.pine`

---

## [1] SMC SESSION SWEEP STRATEGY — five-step session-sweep continuation model,

```
// SMC SESSION SWEEP STRATEGY — five-step session-sweep continuation model,
// ported from Lewis Kelly's "This SMC Strategy Is Too Simple to Ignore".
//
// 🔴 THE REASONING LIVES IN `strategies/tradingview/CLAUDE.md`, NOT HERE.
// This file carried ~670 lines of explanation until 2026-08-16 — 45% of it, and
// every byte loaded on every read. Aaron: "realistically I will never read these
// comments." Read the doc before changing anything: what each rule is FOR, which
// numbers were measured against what, and the defects each guard exists to stop
// are all there, and several of them are not recoverable from the code.
//
// Before any edit: `python3 indicators/tools/check_active_order.py <this file>`.
// Before trusting a number: this file has NO parity gate and NO Python twin.
// After adding an input: TradingView keys saved values off declaration order per
// type, so inserting one resets every later input of that type on a live chart.
```


## [2] The panel follows the house contract numbers; provenance lives in the group names

Since 2026-09-30 (Aaron's call) the group NUMBERS are the house contract's — 2 Market structure,
3 What trades, 4 What arms it, 5 Entry, 6 Stop & targets, 7 Filters, 8 Chart annotations,
10 Drawing: sessions. Unused numbers (1, 9, 11, 12) stay unused; the numbering does not close up.
Where each setting came from is kept in the group NAME: "— his model" is the course's rule,
"— ours" is our own, and a group holding both says "his model + ours" (5, 6 and 7). Groups 6 and 7
were briefly split into a "his model" and an "ours" group under the SAME number; they were merged
the same day, because a panel with two 6s and two 7s is not the one every other strategy shows.

⚠ TradingView places a group where its FIRST input is declared, so seven declarations had to move, in three places,
to keep the on-screen order ascending: the structure pivot length went to the top (group 2), the
five "What trades" inputs followed it (group 3), and the stop anchor ("Stop sits behind…") moved
up beside the other group-6 inputs. Everything else was regrouped by changing its group string.

⚠ **Press "Reset settings to defaults" once** on any chart already running this file — moving and
adding inputs shifts TradingView's saved values onto the wrong settings.

## [3] The entry confluence label — SOS Fade's pattern: grey while open, graded on close

One label per trade, placed at the entry bar the moment it fills, grey while the trade is open.
On the bar it closes it recolours WIN / LOSS / BREAKEVEN and appends the R; hovering shows the
full breakdown. The breakdown is written when the order ARMS, from the live flags (direction,
sweep, confirmation, gap), so a condition that did not hold prints ✗ instead of being assumed.
The plan (entry, stop, targets in R) is the armed plan; the filled price is appended at the fill.
This replaced the result label that used to appear only at close. Copied from
`sos_fade_strategy.pine` (`f_confOpen` / `f_confClose`).
