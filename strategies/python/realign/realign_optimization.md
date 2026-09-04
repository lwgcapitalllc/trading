# Realign — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

🔴 **NO SWEEP HAS EVER BEEN RUN ON THIS BOT. This file is empty on purpose and says so rather
than not existing**, because an absent log and an unswept bot look identical from outside.

🔴 **AND THIS BOT HAS NO PARITY GATE AT ALL — no export twin, no CSV, no `compare_realign.py`.**
Every number it has produced is a lab finding, not a validated result. **Tuning an ungated
strategy optimises a Python program against itself.** Building the gate comes before the first
sweep, not after it. See the root `CLAUDE.md` → *Never Do*, rule 22.

Standing rules for anything recorded here:

- **Score in R, never dollars.**
- 🔴 **RECORD THE COMMAND THAT PRODUCED EVERY NUMBER.** This bot has already lost a measurement
  to this: an earlier revision of its CLAUDE.md claimed +37.67R / 14.60R max drawdown charged,
  **and it does not reproduce** — same window, same cost profile, today gives +35.81R / 15.52R.
  The free figure reproduces to the cent, so whatever differs is on the charged path alone, and
  **neither candidate can be tested because the original run's command was not recorded.**
- ⚠ **Read the R off the SAME BOOK as the win rate.** This bot's own history has the worked
  example: a Pine-vs-Python win-rate gap reported as "30.77% vs 44%" was the comparison reading
  its R off the charged book and its win rate off the free one. **Costs move this strategy's win
  rate by 11 points** (44.4% → 33.3%), because it enters at MARKET and pays the spread both ways
  rather than resting a limit like every other bot here.
- **Print the NEIGHBOURS of any winner**, and re-check it on both halves of the history.
- **Every run carries a CONTROL row that must reproduce the shipped baseline exactly.**
- **A result here is a measurement, not a default.**

## The basis

| | |
|---|---|
| data | 5m XAUUSD, 2020-01-02 → 2026-08-06, warmup 1000 |
| frame | 🔴 **the 5m frame RESAMPLED FROM M1** — reading the M5 cache is a trap, see the bot's CLAUDE.md |
| baseline, free | 162 trades (77L/85S), **+45.14R**, +0.279 avg, 44.4% win, PF 1.658, max drawdown 12.15R |
| baseline, charged (`puprime_standard`) | 162 trades, **+35.81R**, +0.221 avg, 33.3% win, PF 1.496, max drawdown 15.52R |

## Runs

*(none)*

## Open questions — blocking, and they are not tuning questions

| | question | status |
|---|---|---|
| 1 | **There is no parity gate.** | 🔴 **BLOCKS EVERYTHING BELOW.** Build the export twin and the comparison before any sweep. |
| 2 | **The drawdown disagrees with the chart and is undiagnosed by measurement** — 17.79% (≈19.5R) in the Strategy Tester against 15.52R here. | 🔴 **OPEN.** The candidate is that the chart fills a gapped stop at the next bar's open while the bar-replay model fills at the stop price, which would make the Python **optimistic** — the direction that matters. Same total R with a deeper drawdown is that signature, but a signature is not a measurement. |
| 3 | **~2.5 points of win-rate gap remain** after the costed/free mix-up was corrected. | ⚠ **OPEN and small.** Scratch classification is the candidate — 11 of 162 counted separately at \|r\| ≤ 0.02, against a tester that asks only whether P&L > 0. **Not measured.** |
