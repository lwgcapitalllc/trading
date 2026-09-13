# Realign — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

🔴 **NO SWEEP HAS EVER BEEN RUN ON THE SHIPPED (external-frame) SETUP.** Run 1 below is research on
a separate chart-frame arm and tunes nothing the shipped setup reads. ⚠ **That arm and the study
tool are NOT on main** — they are parked on branch `research/realign-chart-frame`, and Run 1's
command only runs from a checkout of it.

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

### Run 1 — which 5-minute structure sequence is worth trading? (2026-09-11)

**Question (Aaron):** on the 5m the market trends (SOS, then BOS), prints ONE counter shift, then
shifts back to continue. Which version of that sequence is the most profitable to enter on?

**Why this ran before the parity gate the table below demands.** It is not a sweep of the SHIPPED
setup's parameters — that blocker stands untouched. It is research on a NEW arm
(`realign_arm_frame = "Chart frame"`) that has no Pine code at all, so no gate can exist for it
yet; it replays the canonical, gated structure engine and the shared, gated exit ladder; and it
moves no default. **Every number below is a LAB finding and must be quoted as one.**

**Basis.**

| | |
|---|---|
| bars | 467,352 5m bars **resampled from the Vantage M1 cache**, 2020-01-02 → 2026-08-06 |
| costs | `puprime_ecn` — the live account's tier (spread charged through the fill model, commission, swap) |
| risk | 1% per trade on every row, $10,000 start (R is scale-free; keeps the lot ceiling from binding) |
| split | IS < **2023-05-01** ≤ OOS, declared before the grid ran |
| exit | inherited ladder, TP2 at **2R**, TP1 at 1R, banking nothing at either rung — held fixed so the grid ranks ENTRIES |
| control | 3 replays per cell of random entries matched on direction, stop, target, month and hour, through the same ladder and slot |

**The grid, 36 cells, declared before it ran:** at least 0 / 1 / 2 with-trend BOS before the counter
shift × at most 0 / 1 / any further counter BOS × enter on the realigning shift or on the next
with-trend break × no trend filter or the 15m trend agreeing. **A cell qualifies only with ≥ 30
trades, positive in BOTH halves, and z ≥ 2 against its own control**; z ≥ 2.99 is the family-wise
bar for 36 cells.

**Command:**

```
command-center/backend/.venv/bin/python backtest/tools/realign_combo_study.py \
    --broker VantageMarkets-Demo --split 2023-05-01 --profile puprime_ecn --seeds 3 --out study.json
```

Pass 1 (37 books) 193s, pass 2 (111 control books) 476s, 18 workers. Output kept in the session
scratchpad as `study_ecn.json` / `study_ecn.log` — re-run the command to regenerate.

**Results: NO CELL QUALIFIED. All 36 lose money after costs, none is positive in both halves, and
the four that differ from random past the family-wise bar are all WORSE than random.**

| cell (trend ≥ / counter ≤ / entry / filter) | n | sum R | avg R | PF | max DD | IS R | OOS R | control avg R | z |
|---|---|---|---|---|---|---|---|---|---|
| **SHIPPED** (15m false break) | 162 | **+38.97** | +0.241 | 1.55 | −13.90 | +10.28 | +28.69 | −0.089 | **1.85** |
| 0 / 0 / shift / – | 395 | −31.27 | −0.079 | 0.82 | −43.90 | −31.88 | +0.61 | +0.033 | −1.65 |
| 0 / 0 / shift / 15m | 218 | −10.73 | −0.049 | 0.89 | −29.13 | −12.74 | +2.01 | +0.084 | −1.40 |
| 0 / 0 / next / – | 225 | −40.73 | −0.181 | 0.58 | −44.93 | −22.79 | −17.94 | +0.023 | −2.87 |
| 0 / 0 / next / 15m | 184 | −34.36 | −0.187 | 0.57 | −38.61 | −18.73 | −15.63 | +0.067 | **−3.18** |
| 0 / 1 / shift / – | 598 | −30.31 | −0.051 | 0.89 | −51.81 | −31.04 | +0.73 | +0.051 | −1.62 |
| 0 / 1 / shift / 15m | 333 | −19.42 | −0.058 | 0.88 | −42.18 | −13.90 | −5.53 | +0.028 | −1.03 |
| 0 / 1 / next / – | 339 | −46.06 | −0.136 | 0.68 | −47.65 | −20.16 | −25.90 | +0.037 | −2.56 |
| 0 / 1 / next / 15m | 274 | −50.42 | −0.184 | 0.59 | −52.00 | −21.85 | −28.57 | +0.017 | −2.70 |
| 0 / any / shift / – | 742 | −52.75 | −0.071 | 0.85 | −69.14 | −46.38 | −6.37 | +0.081 | −2.64 |
| 0 / any / shift / 15m | 426 | −48.84 | −0.115 | 0.77 | −65.27 | −24.87 | −23.97 | +0.083 | −2.63 |
| 0 / any / next / – | 401 | −43.57 | −0.109 | 0.75 | −45.81 | −32.99 | −10.58 | +0.031 | −2.13 |
| 0 / any / next / 15m | 327 | −53.76 | −0.164 | 0.64 | −55.34 | −24.07 | −29.69 | +0.012 | −2.53 |
| 1 / 0 / shift / – | 323 | −21.86 | −0.068 | 0.86 | −39.00 | −25.69 | +3.83 | +0.039 | −1.37 |
| 1 / 0 / shift / 15m | 195 | −12.06 | −0.062 | 0.87 | −30.42 | −11.94 | −0.12 | +0.057 | −1.18 |
| 1 / 0 / next / – | 185 | −33.08 | −0.179 | 0.59 | −38.73 | −19.38 | −13.70 | +0.050 | −2.75 |
| 1 / 0 / next / 15m | 153 | −29.82 | −0.195 | 0.57 | −35.52 | −15.95 | −13.87 | +0.121 | **−3.46** |
| 1 / 1 / shift / – | 519 | −19.14 | −0.037 | 0.92 | −49.88 | −28.76 | +9.62 | +0.081 | −1.67 |
| 1 / 1 / shift / 15m | 291 | −12.48 | −0.043 | 0.91 | −36.75 | −9.43 | −3.05 | +0.079 | −1.29 |
| 1 / 1 / next / – | 293 | −42.92 | −0.146 | 0.65 | −45.53 | −24.84 | −18.08 | +0.056 | −2.85 |
| 1 / 1 / next / 15m | 230 | −43.07 | −0.187 | 0.58 | −46.71 | −21.86 | −21.21 | +0.058 | **−3.21** |
| 1 / any / shift / – | 643 | −40.30 | −0.063 | 0.87 | −63.94 | −39.63 | −0.67 | +0.033 | −1.55 |
| 1 / any / shift / 15m | 374 | −38.18 | −0.102 | 0.80 | −54.61 | −18.50 | −19.68 | +0.049 | −1.87 |
| 1 / any / next / – | 350 | −44.76 | −0.128 | 0.70 | −48.35 | −34.82 | −9.94 | +0.025 | −2.33 |
| 1 / any / next / 15m | 270 | −44.47 | −0.165 | 0.63 | −49.08 | −22.56 | −21.91 | +0.053 | −2.95 |
| 2 / 0 / shift / – | 205 | −2.79 | −0.014 | 0.97 | −22.25 | −13.72 | +10.92 | +0.107 | −1.20 |
| 2 / 0 / shift / 15m | 131 | −2.35 | −0.018 | 0.96 | −18.88 | −6.82 | +4.47 | +0.180 | −1.55 |
| 2 / 0 / next / – | 123 | −15.85 | −0.129 | 0.69 | −19.46 | −7.09 | −8.76 | +0.157 | −2.76 |
| 2 / 0 / next / 15m | 103 | −16.51 | −0.160 | 0.65 | −20.12 | −6.61 | −9.90 | +0.159 | −2.88 |
| 2 / 1 / shift / – | 368 | −7.39 | −0.020 | 0.96 | −36.60 | −15.26 | +7.87 | +0.114 | −1.63 |
| 2 / 1 / shift / 15m | 207 | −3.54 | −0.017 | 0.97 | −26.54 | −0.69 | −2.85 | +0.114 | −1.15 |
| 2 / 1 / next / – | 209 | −26.37 | −0.126 | 0.70 | −28.20 | −15.29 | −11.08 | +0.097 | −2.65 |
| 2 / 1 / next / 15m | 164 | −28.88 | −0.176 | 0.63 | −32.49 | −11.09 | −17.79 | +0.091 | −2.74 |
| 2 / any / shift / – | 458 | −23.77 | −0.052 | 0.89 | −49.94 | −36.26 | +12.49 | +0.040 | −1.33 |
| 2 / any / shift / 15m | 264 | −13.23 | −0.050 | 0.90 | −33.95 | −10.12 | −3.11 | −0.032 | −0.19 |
| 2 / any / next / – | 258 | −37.47 | −0.145 | 0.66 | −39.90 | −28.64 | −8.83 | +0.105 | **−3.24** |
| 2 / any / next / 15m | 197 | −35.32 | −0.179 | 0.62 | −38.92 | −11.75 | −23.57 | +0.021 | −2.31 |

**What the grid says.**

- 🔴 **The pattern loses on its own terms, not just against costs.** Random entries with the SAME
  direction, stop, target, month and hour, through the same ladder, average +0.01 to +0.18R per
  trade in 35 of 36 cells. The pattern's own entries average −0.01 to −0.20R. **The entry is
  worse than a coin toss at the same moment.**
- **Entering on the next with-trend break is worse per trade than entering on the realigning
  shift in all 18 pairs**, and every one of the four cells past the family-wise bar is a next-break
  entry. Waiting for the extra break buys in late.
- **More trend before the counter shift helps, monotonically, and still never turns positive** —
  counter ≤ 0, shift entry: −0.079 → −0.068 → −0.014 avg R at 0 / 1 / 2 trend breaks.
- **The 15m trend filter rescues nothing.** It halves the trade count and moves avg R by a few
  hundredths either way.
- **Nearest to breakeven: 2 / 0 / shift**, −2.79R over 205 trades (−2.35R / 131 with the 15m
  filter), first half negative and second positive — the shape of noise around zero, at z −1.20
  against a control that made +0.107R per trade.
- ⚠ **THE SHIPPED SETUP WAS MEASURED AGAINST A MATCHED RANDOM CONTROL FOR THE FIRST TIME HERE, AND
  IT DOES NOT CLEAR THE BAR EITHER: z 1.85.** +38.97R over 162 trades, positive in both halves,
  against a control averaging −0.089R — so it beats random by ~0.33R a trade, and that is
  suggestive rather than proven. **This is a charged ECN figure at 1% risk and is not comparable to
  the `puprime_standard` basis row above.**
- ⚠ **Lead, NOT a finding: the next-break entries are reliably worse than random**, which says 5m
  breaks straight after a realignment tend to fail. Fading them is a NEW hypothesis — inverting a
  loser picked from this grid is exactly the post-hoc selection the pre-declared grid exists to
  prevent, and the fade pays the same costs, so the losing side's R does not transfer. It needs
  its own pre-declared study on its own control.

**Why the result is believed rather than suspected.** The first smoke run's all-negative grid WAS a
bug (a structural target behind the entry), so this one was checked for the same shape: the R
distribution is that of a working ladder with a losing entry — over all 36 cells' trade lists
(10,975 rows, a trade counted once per cell it appears in) 39.5% full stops, 9.6% past 1.5R, a best
trade of +8.44R; per cell, full stops run 31.6%–45.4% — not the no-winners signature of the bug.
The geometry was then checked trade by trade on one full-history cell (at least 0 / any / shift /
no filter, free book): **all 742 trades carry TP2 at exactly entry + 2 × their own risk, and none has a
stop on the wrong side** — the bug's exact shape, measured absent. The harness
reproduces the published free baseline exactly (162 trades, +45.136R), and the controls, which
share every exit and cost with the cells, make money.

**Verdict: the 5-minute realignment, on its own, is not an entry. Nothing here moves a default.**

## Open questions — blocking, and they are not tuning questions

| | question | status |
|---|---|---|
| 1 | **There is no parity gate.** | 🔴 **BLOCKS EVERYTHING BELOW.** Build the export twin and the comparison before any sweep. |
| 2 | **The drawdown disagrees with the chart and is undiagnosed by measurement** — 17.79% (≈19.5R) in the Strategy Tester against 15.52R here. | 🔴 **OPEN.** The candidate is that the chart fills a gapped stop at the next bar's open while the bar-replay model fills at the stop price, which would make the Python **optimistic** — the direction that matters. Same total R with a deeper drawdown is that signature, but a signature is not a measurement. |
| 3 | **~2.5 points of win-rate gap remain** after the costed/free mix-up was corrected. | ⚠ **OPEN and small.** Scratch classification is the candidate — 11 of 162 counted separately at \|r\| ≤ 0.02, against a tester that asks only whether P&L > 0. **Not measured.** |
