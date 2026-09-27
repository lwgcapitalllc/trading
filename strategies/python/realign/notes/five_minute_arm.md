# The 5-minute-only arm — moved verbatim from `CLAUDE.md` on 2026-09-27

Moved to keep the bot's CLAUDE.md under the 40 KB ceiling. Nothing reworded.

## The 5-minute-only arm — researched 2026-09-11, measured NEGATIVE, parked off main

Aaron's question: on the 5m ALONE — a trend (SOS, then BOS), one counter shift, the shift back —
which version is worth entering? An arm reading the whole sequence on one frame was built and a
36-combination study run, pre-declared, with costs, a split and matched random-entry controls.

- 🔴 **All 36 lose after ECN costs, none is positive in both halves, and the four that differ from
  random past the family-wise bar are all WORSE than random.** Entering on the next break after the
  realignment is worse per trade in all 18 pairs. Full table: `realign_optimization.md` → Run 1.
- ⚠ **This line said the shipped two-frame setup "does not clear the bar either: z 1.85" and that is
  SUPERSEDED as of 2026-09-16 — it clears it.** That 1.85 came from a TRIGGER SCAN on a different
  basis (ECN, 1% risk, full window), and this repo's own standing rule is that a trigger prior is
  not a strategy result. Replayed through the real strategy and the real exit ladder
  (`backtest/tools/realign_control.py`, 20 reps, `puprime_standard`, 2020-01-02 → 2025-08-05):
  **z +3.58 on the shipped setup with the 15m trail** (Run 10; +2.36 on the old 5m trail). The
  higher frame setting the trap is the version worth proving, and it is now the version that has
  been proven.
- **The code is on branch `research/realign-chart-frame`, not here** — five settings with no
  TradingView inputs, for an arm with no edge. Check it out to re-run the study; do not merge it.
- ⚠ **Two facts it measured about the engine stream hold on main too** (467,352 5m bars, 5,265
  breaks, at swing length 15 and 10): no bar ever breaks both ways, and once a run has printed its
  first break every counter break is flagged SOS. The first break itself can be a plain BOS.

