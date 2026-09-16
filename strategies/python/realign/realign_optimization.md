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

---

### Run 2 — the retest entry, and the frame pairing Aaron asked for (2026-09-15)

**What prompted it.** Aaron relayed his brother's actual trades: *"there's always a break of
structure followed by a shift of structure followed by another shift of structure ... and then
price retests that shift of structure area and then goes ... if we get it on the retest that's
even better"*. Two of those three things already existed here — the stop he described is the
shipped stop, and his three-break sequence is `realign_pattern="strict"`. **The retest was not
built on either side**, was listed under *Open* in `docs/REALIGN_SPEC.md`, and had never been
measured anywhere in this repo. He also asked which frame pairing makes more money, and proposed
a 5m-direction / 1m-entry build by analogy with the shipped 15m/5m.

**What was built.** `realign_entry_mode` ("market" | "retest"), `realign_retest_at`
("level" | "mid") and `realign_retest_bars`. The retest rests a limit at the structure level the
realignment broke and reuses the INHERITED `_try_entry_fill` — the placement differs and nothing
else does. Defaults are unchanged, and the shipped control reproduces exactly on both bases
(free 162 / +45.14R; charged 162 / +35.81R), so no figure published before today moves.

🔴 **THE ORDER OF THE CANCEL AND THE FILL IS THE CORRECTNESS ARGUMENT IN THIS RUN.** A resting
limit is cancelled when its expiry passes or when price reaches the stop without it having
filled. Doing that check BEFORE the bar is offered to the fill path deletes exactly the trades
that would have lost — price dipping to the limit and carrying on to the stop is a real losing
trade — and the row would be flattered in the one direction nobody audits. The cancel therefore
runs after the parent's fill phase, and a test pins it.

**Result 1 — the frame pairing. 5m/1m is dead, and it is not close.** Charged
`puprime_standard`, 1m bars, `realign_htf_minutes=5`, 2020-01-02 → 2026-08-06:

| pairing | entry | trades | sum R | avg R | PF | maxDD |
|---|---|---|---|---|---|---|
| 15m / 5m | market (shipped) | 162 | **+35.81** | +0.221 | 1.50 | 15.52 |
| 5m / 1m | market | 483 | **−67.28** | −0.139 | 0.74 | 89.77 |
| 5m / 1m | retest | 313 | **−87.97** | −0.281 | 0.54 | 88.25 |

⚠ **Both 1m rows destroyed the account, so their totals are floors rather than clean figures** —
an 88-90R drawdown at 10% risk per trade is ruin, and the retest row books its entire loss in the
first half with exactly +0.00R after it, which is what a dead account looks like, not a second
half that broke even. The SIGN is the finding; the magnitude is not quotable. This is the third
independent confirmation of the cascade in `docs/REALIGN_SPEC.md` (5m carries the edge, 3m
break-even, 1m negative) and it holds with the retest entry on, which was the one remaining
reason to think the 1m arm might be rescuable. **Aaron's 5m/1m idea is measured and refused.**

**Result 2 — the retest entry is worth real money on the shipped pairing, and it is a HILL.**
Charged, 15m/5m, retest at the broken level, sweeping only the expiry:

| expiry (5m bars) | 2 | 3 | **4** | **5** | **6** | 8 | 12 | 16 | 24 | 48 |
|---|---|---|---|---|---|---|---|---|---|---|
| trades | 99 | 105 | 111 | 114 | 121 | 127 | 134 | 135 | 136 | 142 |
| sum R | +31.25 | +38.15 | +44.98 | +45.34 | +45.42 | +40.26 | +36.09 | +35.66 | +37.75 | +40.18 |
| avg R | +0.316 | +0.363 | **+0.405** | +0.398 | +0.375 | +0.317 | +0.269 | +0.264 | +0.278 | +0.283 |
| PF | 1.64 | 1.77 | 1.88 | 1.87 | 1.85 | 1.69 | 1.57 | 1.56 | 1.59 | 1.60 |
| maxDD | 13.52 | 13.52 | 13.52 | 13.66 | 13.52 | 17.68 | 21.38 | 21.80 | 19.71 | 21.83 |

Against the shipped market entry (+35.81R, +0.221 avg, PF 1.50, 15.52R drawdown) the 4–6 bar
plateau is better on **every** axis at once — more total R from FEWER trades, ~1.8x the average R,
a better profit factor and a shallower drawdown — and it is a smooth rise and fall rather than a
spike, with the drawdown flat across the whole plateau. It also rebalances the calendar halves
(shipped: +8.35 / +27.46; retest at 4 bars: +18.36 / +26.62), which matters because the
half-split direction flip is this strategy's one known structural weakness.

⚠ **The mechanism is consistent with what was already suspected and is still NOT measured.** The
retest does not pay the entry-side spread and enters nearer the stop, so the same structural
target is a larger multiple of a smaller R — which is the candidate `realign_pattern`'s docstring
names for why charging costs hurts the tighter patterns most. Consistent is not measured.

⚠ **avg R is +0.405 against a standard error of ±0.250 — 1.6 errors, still short of the bar of 2**,
same as everything else in this strategy. The table above was also run on the FULL window
including the year Aaron agreed to hold back, so **it is a fit, not a result.**

**Pre-declared before the refit was run, and recorded here before its output was read:** the hill
is re-fitted on 2020-01-02 → 2025-08-05 alone; the expiry is taken as the CENTRE of the
contiguous best-avg-R plateau on that window, never its argmax (a plateau centre is robust to the
noise that moves an argmax one cell); the pick is then run ONCE on 2025-08-06 → 2026-08-06
against the shipped market entry, and that single run is the verdict. **No second holdout run,
whatever the first one says.**

**Result 3 — the refit, 2020-01-02 → 2025-08-05 (the held-back year excluded).** The hill is the
same shape on the fitting window alone:

| expiry | 2 | 3 | **4** | **5** | **6** | 8 | 12 | 24 |
|---|---|---|---|---|---|---|---|---|
| trades | 86 | 91 | 95 | 97 | 102 | 108 | 115 | 117 |
| sum R | +21.21 | +29.16 | +37.02 | +35.85 | +35.79 | +30.63 | +26.46 | +28.12 |
| avg R | +0.247 | +0.320 | **+0.390** | +0.370 | +0.351 | +0.284 | +0.230 | +0.240 |
| maxDD | 13.52 | 13.52 | 13.52 | 13.66 | 13.52 | 17.68 | 21.38 | 19.71 |

Contiguous best-avg-R plateau is {4, 5, 6}; **its centre is 5, and 5 is the pick** — taken by the
rule declared above, not by the argmax, which was 4.

The market entry over the same fitting window, for the comparison the table above does not carry
(its control row is the pinned retest): **140 trades, +28.75R, +0.205 avg, PF 1.47, maxDD 15.52R.**
The retest at the pick is +35.85R from 97 trades at +0.370 avg, PF 1.83, maxDD 13.66R.

**Result 4 — the holdout, 2025-08-06 → 2026-08-06, run once.** Charged, 15m/5m, expiry 5:

| entry | trades | sum R | avg R | ±se | PF | maxDD |
|---|---|---|---|---|---|---|
| market (shipped) | 21 | +6.92 | +0.330 | 0.533 | 1.62 | 5.08 |
| **retest @ level, 5 bars** | 17 | **+9.49** | **+0.558** | 0.684 | **2.04** | **3.04** |

**The retest beat the shipped market entry on every axis in a year that had no say in choosing
it** — more total R from fewer trades, 1.7x the average, a better profit factor and a shallower
drawdown. That is the test the Loaded Level scalp pick FAILED (z +2.52 in-sample, −1.5R on its
holdout year), and it is the reason this one is worth continuing with.

🔴 **AND IT PROVES ALMOST NOTHING ON ITS OWN, FOR TWO SEPARATE REASONS — SAY BOTH WHENEVER THIS
TABLE IS QUOTED.** First, 17 trades: avg R +0.558 against a standard error of ±0.684 is under ONE
error, so this year cannot distinguish the retest from luck. Second and worse, **stripping each
row's single best trade turns BOTH rows negative** (−0.76R retest, −2.82R market): one trade
carries the entire holdout year in each configuration. A year like this can REFUTE a pick and
this one did not — that is the whole claim, and "did not refute" is not "confirmed". The evidence
for the retest is the 5.5-year fitting window and the hill's shape; the holdout's job was only to
try to kill it.

**What this run does NOT license.** Nothing here moves a default. `realign_entry_mode` ships
"market", because open question 1 below still blocks everything: **this bot has no parity gate**,
so the retest exists in Python and nowhere else, and adopting it means building the Pine side and
the export twin first. It has also never been scored against a matched random control the way the
5-minute-only arm was, and the half-split direction flip has not been re-checked with it on.

---

### Run 3 — a fixed take-profit, and the hold-time question underneath it (2026-09-15)

**What prompted it.** Aaron: *"I like to have an average take profit that I could just close the
trades off of and bank the money. That way I'm not holding over days or sessions."* Two separate
asks — bank at a fixed multiple, and stop holding so long — and they turn out to have opposite
answers.

**The complaint is factually correct.** At the Run 2 pick (retest, 5-bar expiry), over
2020-01 → 2025-08: **every one of the 97 trades exits on a trailing stop or the time stop. Nothing
ever banks at a target** — `exec_tp1_pct` and `exec_tp2_pct` are both 0.0, so the two rungs only
stage the stop. Median hold 11.2h, **28 of 97 run past 24 hours, longest 209 hours (8.7 days)**.

**Built:** `realign_tp_r` — close the whole position at N x its own risk. It re-prices the FIRST
rung and the config refuses unless `exec_tp1_pct = 100`, so it reuses the existing ladder rather
than adding a second exit path. Default `None`; no shipped figure moves.

⚠ **Measured by REPLAY, not by recomputing R off the trade list's excursions.** With one position
slot, closing earlier frees the slot and a different later set of trades gets taken — the effect
that got the minimum-stop guard's sign wrong (+1.84R estimated, −1.84R replayed).

**Result 1 — a fixed take-profit loses, at every level tested.** Charged, retest @ 5:

| exit rule | trades | sum R | avg R | PF | maxDD | win% |
|---|---|---|---|---|---|---|
| **trail (shipped ladder)** | 97 | **+35.85** | **+0.370** | 1.83 | 13.66 | 28.9% |
| bank all at structural TP1 | 99 | +11.73 | +0.118 | 1.27 | 8.54 | 50.5% |
| bank all at 1.0R | 100 | **−3.93** | −0.039 | 0.92 | 13.15 | 50.0% |
| bank all at 1.5R | 98 | +4.39 | +0.045 | 1.08 | 10.93 | 43.9% |
| bank all at 2.0R | 98 | +8.86 | +0.090 | 1.16 | 13.53 | 38.8% |
| bank all at 2.5R | 98 | +10.88 | +0.111 | 1.19 | 16.25 | 35.7% |
| bank all at 3.0R | 96 | +7.59 | +0.079 | 1.13 | 16.94 | 33.3% |
| bank all at 4.0R | 96 | +15.31 | +0.159 | 1.25 | 18.09 | 32.3% |
| bank all at 5.0R | 95 | +16.26 | +0.171 | 1.27 | 18.09 | 32.6% |

**The best fixed target is worth less than half the trail, and the trend is monotone outward** —
the further the cap, the better it does, which is the table saying *do not cap at all*. The reason
is in Run 2's own excursion profile: only 43% / 27% / 18% of trades ever reach 1R / 2R / 3R, against
a best of 24.6R. **The tail pays for the strategy, and a fixed target sells the tail while keeping
every loser whole.** 🔴 **The 1R row is the one to remember: 50% win rate and it LOSES MONEY.** A
rule can feel good on every individual trade and still be the worst row in the table.

**Result 2 — the hold-time complaint has a real fix, and it is the CLOCK, not the target.** The
existing time stop is 36h and applies *before the first rung only*, so a trade that has moved is
never timed out. Switching it to apply ALWAYS and sweeping the limit, same basis:

| limit (h) | 6 | 8 | **12** | 18 | 24 | 36 | 48 |
|---|---|---|---|---|---|---|---|
| sum R | +27.26 | +34.52 | **+37.76** | +32.02 | +32.43 | +31.33 | +31.20 |
| avg R | +0.275 | +0.349 | **+0.389** | +0.330 | +0.334 | +0.323 | +0.322 |
| PF | 1.90 | **2.04** | 2.01 | 1.80 | 1.79 | 1.73 | 1.71 |
| maxDD | **7.78** | 10.64 | 12.12 | 14.93 | 15.98 | 14.26 | 14.85 |
| win% | 38.4% | 38.4% | 36.1% | 32.0% | 28.9% | 29.9% | 28.9% |

A hill peaking at 12h. **A hard 12-hour limit beats the 36-hour before-first-rung rule on every
axis at once** — +37.76R vs +35.85R, avg +0.389 vs +0.370, PF 2.01 vs 1.83, drawdown 12.12R vs
13.66R — *and* it caps the hold at half a day, which is what was asked for. Both calendar halves
positive (+21.69 / +16.07). 8h gives up 3R for the best profit factor in the table and a 10.64R
drawdown, and is the choice if shallower drawdown is worth more than total R.

🔴 **THIS PICK HAS NO HOLDOUT AND MUST NOT BORROW RUN 2's.** Run 2 pre-declared *"no second holdout
run, whatever the first one says"*, and that year has been spent. Testing this pick on it now is a
second draw on the same data — the mechanism by which a holdout stops meaning anything. The
evidence for 12h is the fitting window and the hill's shape only. **The clean validation is data
that does not exist yet: forward, or a broker cache with history this one lacks.**

⚠ Nothing here moves a default. `realign_tp_r` ships `None` and the time stop stays as inherited.

**Result 3 — not holding over the weekend is free, and not holding OVERNIGHT is better than
free.** Aaron: *"what if we don't hold to weekends? ... fifteen minutes before the market close we
close the trade."* The parent already had the DAILY version (`flat_by_close`, off by default) and
the DST-aware New-York-hour plumbing behind it; only the Friday-only variant was missing, and it
is added as `realign_flat_before_weekend` reusing the parent's `_in_flat_window` rather than
re-deriving when the close is. Charged, on retest @ 5 + the 12h clock:

| | trades | sum R | avg R | PF | maxDD | win% |
|---|---|---|---|---|---|---|
| no flat rule | 97 | +37.76 | +0.389 | 2.01 | 12.12 | 36.1% |
| flat before the WEEKEND (Fri only) | 97 | +37.66 | +0.388 | 2.01 | **11.06** | 36.1% |
| flat before EVERY daily close | 99 | **+38.03** | +0.384 | **2.11** | **9.38** | **39.4%** |

**Flattening on Friday costs 0.1R and takes a full R off the drawdown — it is free.** Flattening
every day is better still: slightly more total R, the best profit factor and **a 23% shallower
drawdown (9.38R vs 12.12R)**, and it removes overnight gap risk entirely, which is exposure this
backtest models only as a bar gap and a live account feels as slippage. ⚠ Its calendar halves are
more lopsided than the baseline's (+26.61 / +11.42 against +21.69 / +16.07) — worth re-checking
before it is ever adopted, and NOT a reason to prefer the weaker rule.

🔴 **Same holdout status as Run 3's clock: none, and it may not borrow Run 2's.** These are the
third and fourth picks made on the same fitting window.

⚠ **The weekday is read off the UTC timestamp and the epoch began on a THURSDAY.** The obvious
`+4` shift flattens on Thursday — a rule that still closes trades and still looks like it works.
Caught before it ran, and pinned by a test.

**Tooling fixed on the way (`backtest/tools/axis_sweep.py`).** `--axis` on any field whose current
value is `None` passed the RAW STRING through — every `Optional` lever in the repo was unsweepable,
and a config without a validator would have replayed `"2"` as a string while the table labelled the
row `2`. It now reads the declared annotation and REFUSES a field it cannot type. ⚠ **No stored
result moves:** the old path could only produce a crash or a string-valued config, so no published
figure was ever produced through it.

---

### Run 4 — "don't take the SOS Fade trail blindly" (2026-09-15)

**What prompted it.** Aaron: *"I know if we're doing a trailing stop we're going to be giving back
returns ... maybe we take off the majority of the position and leave a runner, or trail tighter
after a certain amount of equity is built. I just don't want to take the SOS Fade trailing stop
blindly."* Correct instinct, and the answer is that the inherited trail is already the best thing
tested — but only because of WHERE it leaks, which is not where it looks like it leaks.

**How much it actually hands back.** At the Run 3 stack (retest @ 5 + 12h clock + nightly flat),
banked +38.03R against +121.75R of summed peak excursion — "69% given back" as a headline, **and
that headline is misleading and must not be quoted alone.** Bucketed by how far each trade ever ran:

| peak reached | trades | sum of peaks | banked | kept |
|---|---|---|---|---|
| 0–1R | 63 | +21.26 | **−30.40** | — |
| 1–2R | 19 | +26.00 | +10.17 | 39% |
| 2–3R | 11 | +25.74 | +16.47 | 64% |
| 3–5R | 3 | +11.58 | +8.16 | 70% |
| 5R+ | 3 | +37.16 | +33.63 | **91%** |

🔴 **THE TRAIL IS NOT LEAKING ON THE RUNNERS — IT KEEPS 91% OF THEM** (the 24.60R peak banked
+22.56R). The 0–1R row is not giveback at all: those are losers that ticked green before stopping
out, and no exit rule recovers them. The only real bleed is the 1–2R band at 39% kept.

**Result — all three proposed fixes lose, and two of them lose badly.** Same basis:

| | trades | sum R | avg R | PF | maxDD | win% |
|---|---|---|---|---|---|---|
| **shipped trail** | 99 | **+38.03** | **+0.384** | **2.11** | 9.38 | 39.4% |
| bank 25% at the first rung | 99 | +30.12 | +0.304 | 1.88 | 8.49 | 42.4% |
| bank 50% | 99 | +22.20 | +0.224 | 1.65 | 7.60 | 45.5% |
| bank 75% | 99 | +14.29 | +0.144 | 1.42 | **7.27** | **48.5%** |
| ratchet 0.25% | 99 | +20.87 | +0.211 | 1.61 | 9.38 | 39.4% |
| ratchet 0.5% | 99 | +24.95 | +0.252 | 1.73 | 9.38 | 39.4% |
| ratchet 2.0% / 3.0% | 99 | +38.03 | +0.384 | 2.11 | 9.38 | 39.4% |
| trail buffer 5 / 10 / 40 / 80 ticks | 99 | +38.05 … +37.94 | +0.384 | 2.11 | 9.38 | 39.4% |

**Partial banking is the fixed-target result again in another costume** — monotone: the more you
bank early, the higher the win rate (39.4% → 48.5%), the shallower the drawdown (9.38 → 7.27R) and
the less money you make (+38.03R → +14.29R). **You buy 2.1R of drawdown for 23.7R of return.**
A real risk/return trade is available here and it is a bad one.

🔴 **AND THE SECOND HALF OF THE INHERITED TRAIL IS INERT AT ITS SHIPPED SETTING.** `exec_trail_pct`
at 1.0, 2.0 and 3.0 return **byte-identical books** — same total, same halves, same drawdown —
while 0.5 and 0.25 differ. The ratchet only ever TIGHTENS past the structure anchor, so at ≥1.0 the
anchor is always the binding constraint and the ratchet never fires. **`"Structure + % ratchet"` is
running as a plain structure trail**, and tightening it until it does fire costs 13–17R. The buffer
width is likewise flat across a 16x range (5 → 80 ticks moves the total by 0.11R): **not a lever.**

**Verdict: the inherited trail stays, now for a measured reason rather than by inheritance.** The
one place worth another idea is the 1–2R band, and nothing tested here addresses it — partial
banking hits every band at once, which is why it pays for the 1–2R improvement with the 5R+ tail.
⚠ A band-specific rule would be a NEW hypothesis chosen by looking at this table, on a fitting
window already used for three picks. It needs its own pre-declared study, not a fifth draw here.

---

### Run 5 — is the SETUP better than a random moment? (2026-09-16)

**The question everything else rested on and nobody had asked of the real strategy.** Every figure
in Runs 1-4 says what the strategy made; none says whether the PATTERN made it. An exit ladder, a
stop geometry and a hard-drifting instrument can make money from almost any entry — and Run 1 found
exactly that on the 5-minute-only arm, where **random entries beat the pattern's own**. The shipped
setup's only prior score, z 1.85, came from a TRIGGER SCAN on a different basis (ECN, 1% risk, full
window) and never cleared the bar.

**Method.** `backtest/tools/realign_control.py`. The control replays the REAL strategy through the
REAL execution and swaps only the TRIGGER, via a scripted tracker injected at `strategy.tracker`.
Sizing, the three-stage stop, the trail, the time stop, flat-by-close, the cost profile and the
single position slot are all shipped code, so the two arms differ in exactly one thing. Each
control trigger keeps the real one's side, calendar month, New York hour, stop distance, target
distance and retest offset — **only the moment is random.** 20 reps, charged
`puprime_standard`, 2020-01-02 → 2025-08-05.

| arm | trades | avg R | control avg R | beats random by | **z** |
|---|---|---|---|---|---|
| shipped (market entry, 36h before-TP1) | 140 | +0.205 | −0.053 | +0.258R | **+2.36** |
| stacked (retest @ 5 + 12h clock + nightly flat) | 99 | +0.384 | −0.057 | +0.441R | **+4.21** |

🔴 **THE LOAD-BEARING RESULT IS THE CONTROL COLUMN, NOT THE z.** Random timing through this exact
machinery **LOSES money** — −0.053R and −0.057R a trade, and the shipped arm's controls averaged
−7.19R over 136 trades. So the exit ladder, the stop geometry and gold's 2020-2025 drift are NOT
what pays: handed a random moment they hand money back. **That was the single most likely
explanation for this strategy's results and it is now measured and rejected.** It is also the exact
failure the 5-minute-only arm died of, so the test has demonstrated it can return the other answer.

⚠ **READ THE TWO ROWS DIFFERENTLY — THEIR EVIDENCE IS NOT THE SAME KIND.** The shipped row's
configuration predates today and was in no way chosen against this control, so **+2.36 is the clean
number**; it clears the plain bar of 2.0 and NOT the family-wise 2.99 this repo uses when several
things are tested at once. The stacked row's +4.21 is inflated by selection: three of its four
settings were picked on this very window in Runs 2-4, and only the retest has ever faced a holdout.
**The honest reading is that the pattern is real, and that the stacked improvements are part real
and part fitted in an unknown proportion.**

⚠ Control trade counts differ from the real arm's (135.8 and 93.9 against 140 and 99) and that is
correct rather than a flaw: with one position slot a randomly-timed setup displaces whatever real
setup came next. The counts are reported, never assumed equal.

**Verdict: the 15m/5m Realign pattern carries a real edge over random entry, and the retest entry
roughly doubles the distance from random.** This is the first result in the strategy's history that
clears its own bar on a clean basis. It does NOT make any of Run 3's or Run 4's picks validated,
and it does not touch open question 1 below.

---

### Run 6 — how concentrated is the profit? (2026-09-16)

Aaron: *"take out the biggest winning trade, do we still make money?"* Yes, and barely. Charged
`puprime_standard`, 2020-01-02 → 2025-08-05, dropping the largest trades in order:

| dropped | 0 | 1 | 2 | 3 | 5 | 10 |
|---|---|---|---|---|---|---|
| shipped (140 tr) | +28.75 | +10.21 | +3.72 | **−1.67** | −10.24 | −25.75 |
| stacked (99 tr) | +38.03 | +15.46 | +9.82 | +4.40 | **−2.48** | −13.09 |

Five biggest, shipped: +18.54, +6.49, +5.39, +4.55, +4.03 — **136% of the total.**
Five biggest, stacked: +22.56, +5.64, +5.43, +3.92, +2.96 — **107% of the total.**

🔴 **THE SINGLE BEST TRADE IS ~60% OF THE RESULT IN BOTH BOOKS, AND EVERYTHING OUTSIDE THE TOP FIVE
NETS TO ROUGHLY ZERO.** This is the most important caveat attached to every figure in Runs 2-5 and
belongs beside any of them that get quoted. Practically it is a larger risk than the missing
holdouts: a year without those trades is flat-to-losing and has to be sat through.

⚠ **It is not evidence the edge is fake.** Run 5's control does not depend on the big winners —
random timing through the same exits loses money across all 20 reps. Fat tails are also the stated
design intent (root `CLAUDE.md` → *Trading Philosophy*).

**The stacked configuration is measurably LESS concentrated**: 5 removals to break rather than 3,
and its drawdown holds flat at 9.38R through the first three removals while the shipped book's
stays at 15.52R throughout. That is a point in favour of Run 2-3's changes that no other table
here shows.

## Open questions — blocking, and they are not tuning questions

| | question | status |
|---|---|---|
| 1 | **There is no parity gate.** | 🔴 **BLOCKS EVERYTHING BELOW.** Build the export twin and the comparison before any sweep. |
| 2 | **The drawdown disagrees with the chart and is undiagnosed by measurement** — 17.79% (≈19.5R) in the Strategy Tester against 15.52R here. | 🔴 **OPEN.** The candidate is that the chart fills a gapped stop at the next bar's open while the bar-replay model fills at the stop price, which would make the Python **optimistic** — the direction that matters. Same total R with a deeper drawdown is that signature, but a signature is not a measurement. |
| 3 | **~2.5 points of win-rate gap remain** after the costed/free mix-up was corrected. | ⚠ **OPEN and small.** Scratch classification is the candidate — 11 of 162 counted separately at \|r\| ≤ 0.02, against a tester that asks only whether P&L > 0. **Not measured.** |
