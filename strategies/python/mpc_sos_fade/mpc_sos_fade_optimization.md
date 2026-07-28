# MPC SOS Fade — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

Standing rules for anything recorded here:

- **Score in R, never dollars.** The bot risks a fixed % of equity per trade, so dollars
  compound and a dollar ranking measures recency, not edge.
- **Record per-year and per-half splits**, so a config that only worked in one regime is
  visible without re-running the grid.
- **A result here is a measurement, not a default.** Adopting one means a single commit
  across `config.py`, `indicators/mpc_strategy.pine`, `indicators/mpc_strategy_export.pine`
  and `compare_strategy.py`, with Pine↔Python parity re-run green.
- **Sweep in bar mode, validate the winner in tick mode.** A tick pass is ~100x slower, so
  the grid runs at zero costs and only the survivor gets real spread, slippage and swap.

## Runs

| # | Date | What was swept | Winner | Status |
|---|---|---|---|---|
| 1 | 2026-07-26 | TP1 % × TP2 % (runner = remainder), 21 combos | `tp1=0, tp2=0`, 100% runner — 70.7R | measured, not adopted |
| 2 | 2026-07-26 | The whole exit ladder — TP1 % × TP2 % × TP2 floor mode × trail mode/size, 525 combos | same TP split; **both dropdowns already at their best value** — 70.7R | measured, not adopted |
| 3 | 2026-07-26 | Stop TIMING — when breakeven fires × when the trail engages, 35 combos | **nothing beats the shipped timing** — the one row that scores higher fails the per-year check | nothing to adopt |
| 4 | 2026-07-26 | Stop PLACEMENT — `exec_sl_level` × `exec_sl_buf_tk` × TP split, 40 combos | **none — the sweep is INVALID.** Four of the five SL levels can place the stop on top of the entry; the account blows to −$63k. Found two real defects. | **discard the numbers, read the writeup** |
| 5 | 2026-07-26 | *"how do I cut the losers quicker?"* — diagnosis of the loss bucket, then `exec_sl_level` re-run on a clean window + `exec_close_opp_sos` + `exec_htf_exhaust_only` | **Diagnosis: every loss is a trade that never touched TP1.** `exec_sl_level=0.786` scores 59.3R vs 33.6R shipped at the SAME drawdown — but it reproduces Run 4's hazard on 8 trades, so **still not adoptable**. Both "cut quick" toggles measured **exactly zero effect**. | measured, **blocked on Run 4's guard** |
| 6 | 2026-07-27 | *"cut trades early / block the losing pattern"* — 8 years at the SHIPPED config, with every trade's per-bar R path captured. 3 cut families (~40 variants) + 10 entry blocks + `exec_close_opp_sos` | **The question is closed. Every cut rule loses money**, because no loser runs straight to its stop (min MFE **+0.09R**, median +0.51R) and winners are underwater just as deep (median MAE −0.36R) — the two are indistinguishable while live. The −54.9% DD is a **losing streak at 10% risk**, not give-back, so **risk % is the only lever**. Only positive filter: **stop < $2** (293x → 338x). | **do not build it** — read the verdict |

**Still open:** *"what R:R should I use as a dynamic stop loss?"* — no sweep of existing
parameters can answer it (the bot has no R:R dial). A three-stage plan is written up at the
**bottom of this file** under `# OPEN — "What R:R should I use?"`. Stage 1 is ~30 min and needs
no new strategy code. Start there.

**Run 5 sharpens why that plan is the right one.** The loss bucket has a single mechanical cause
(TP1 sits ~0.45R away while the stop sits 1R away, so a loser dies ~0.34R short of safety), and
the only lever that touches it is stop DISTANCE — which is exactly what Stage 2 builds and what
Run 4 proved is currently unguarded. Run 5's measured tighter-stop gain (+26R) is the size of the
prize sitting behind Stage 1's guard.

---

# Run 1 — TP Split Sweep (2026-07-26)

**Question:** how should the position be split between TP1, TP2 and the runner?
**Answer:** take nothing early. `exec_tp1_pct = 0`, `exec_tp2_pct = 0`, 100% on the runner.

## How it was measured

- All 185,530 M15 XAUUSD bars, 2018-09-14 → 2026-07-24 (the broker's measured intraday
  history floor; the 2015 range in the cache is the D1-substitution artifact and is excluded).
- **187 trades.** Same 187 in every row — TP sizes change only how much is banked, never
  which trades are taken. That is why win rate is flat across the whole grid.
- Scored in **R, not dollars.** The bot risks a fixed % of equity per trade, so dollars
  compound and a dollar ranking would measure recency instead of edge.
- 21 combos: TP1 % × TP2 % at 20-point steps, every pair summing ≤ 100. Runner = the
  remainder. Every other lever at its shipped default (structure trail, 20-tick buffer,
  TP2 stop floor at TP1 price).
- `fill_model="bar"` — zero costs, the same intrabar guess the Pine makes. A tick-mode
  re-run of the winner is still outstanding.

Half-split boundary: 2022-08-21.

## Result — the full grid, best first

| TP1% | TP2% | Runner% | Total R | PF | Win% | MaxDD R | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | **100** | **70.7** | 2.90 | 72.2 | −6.0 | 16.0 | 54.6 |
| 0 | 20 | 80 | 64.8 | 2.75 | 72.2 | −6.0 | 13.7 | 51.1 |
| 20 | 0 | 80 | 63.4 | 2.71 | 72.2 | −5.3 | 14.7 | 48.7 |
| 0 | 40 | 60 | 58.9 | 2.59 | 72.2 | −5.9 | 11.3 | 47.6 |
| 20 | 20 | 60 | 57.5 | 2.55 | 72.2 | −5.2 | 12.3 | 45.2 |
| 40 | 0 | 60 | 56.0 | 2.52 | 72.7 | −4.5 | 13.3 | 42.8 |
| 0 | 60 | 40 | 53.0 | 2.43 | 72.2 | −5.8 | 8.9 | 44.0 |
| 20 | 40 | 40 | 51.5 | 2.39 | 72.2 | −5.1 | 9.9 | 41.6 |
| 40 | 20 | 40 | 50.1 | 2.36 | 72.7 | −4.4 | 10.9 | 39.2 |
| 60 | 0 | 40 | 48.8 | 2.32 | 72.7 | −3.7 | 11.9 | 36.9 |
| 0 | 80 | 20 | 47.0 | 2.27 | 72.2 | −5.8 | 6.5 | 40.5 |
| 20 | 60 | 20 | 45.6 | 2.23 | 72.2 | −5.1 | 7.5 | 38.1 |
| 40 | 40 | 20 | 44.2 | 2.20 | 72.7 | −4.4 | 8.5 | 35.7 |
| 60 | 20 | 20 | 42.9 | 2.16 | 72.7 | −3.7 | 9.5 | 33.3 |
| 80 | 0 | 20 | 41.5 | 2.12 | 72.7 | −3.7 | 10.5 | 30.9 |
| 0 | 100 | 0 | 41.1 | 2.11 | 72.2 | −6.1 | 4.2 | 37.0 |
| 20 | 80 | 0 | 39.8 | 2.07 | 72.2 | −5.3 | 5.2 | 34.6 |
| 40 | 60 | 0 | 38.4 | 2.04 | 72.7 | −4.6 | 6.2 | 32.2 |
| 60 | 40 | 0 | 37.0 | 2.00 | 72.7 | −3.9 | 7.2 | 29.8 |
| 80 | 20 | 0 | 35.5 | 1.96 | 72.7 | −3.5 | 8.2 | 27.4 |
| 100 | 0 | 0 | 34.1 | 1.92 | 72.7 | −3.6 | 9.2 | 25.0 |

The shipped default (30/40/30) sits mid-table at **47.9R**, measured separately.

## What it means

**The ranking is perfectly monotonic.** Every point of size moved off the runner and into an
early partial costs R, with no exception anywhere in the grid. This is the shape a real edge
makes. An overfit result looks like an isolated spike in the middle of a grid; this doesn't.
It is also consistent with the already-recorded finding that the runner produces more than
100% of net in every window ever measured on this bot.

**Nothing degenerates at 0%.** Verified in `execution.py`: `_remaining_brackets` skips a
zero-size bracket cleanly, and `_advance_stage` promotes on **price**, not on the partial
sizes. So at 0/0 the stop still moves to breakeven at TP1 price and to the floor at TP2 price
— the protection ladder is intact, only the cash-outs are gone. 0/0 is a legitimate
"let it all ride" config, not a broken one.

**The cost is smoothness, not money.** Worst drawdown goes from −3.6R (bank everything at
TP1) to −6.0R (full runner). You collect ~2x the R for ~1.7x the drawdown. Good trade
mathematically, worse to sit through.

**Both losing years survive every config.** 2018 and 2022 are negative in all 21 rows —
a useful honesty check that no row is quietly cherry-picked. Winner's per-year R:

```
2018 −1.8   2019 +4.0   2020 +14.8   2021 +3.6   2022 −2.3
2023 +10.0  2024 +14.3  2025 +14.6   2026 +13.5
```

## Before this becomes the default

1. Re-run 0/0/100 in **tick mode** (real bid/ask, measured slippage, commission, swap). A
   full-runner config holds positions longer, so it carries more swap than the partial-heavy
   configs it beat — bar mode cannot see that.
2. Any default change lands in **one commit** across `config.py`,
   `indicators/mpc_strategy.pine`, `indicators/mpc_strategy_export.pine` and
   `compare_strategy.py`, with Pine↔Python parity re-run and green.
3. 187 trades is the largest sample this bot has ever been tuned on (4x the 2-year window,
   8x the 365-day window) but it is still 187. Treat the size of the win as approximate and
   the direction as solid.

Harness: throwaway scratchpad sweep over `backtest/replay`'s `EngineStack`, one fresh
strategy and fresh stack per combo. Not committed — `backtest/optimizer.py` is the permanent
tool, but it scores in dollars with no time splits, so it was not used here.

---

# Run 2 — Full Exit-Ladder Sweep (2026-07-26)

**Question:** across the whole exit ladder at once, what is the best combination?
**Answer:** the two dropdowns are ALREADY at their best values — Aaron's brother's tested combo
(structure trail, 20-tick buffer, TP2 floor at TP1 price) wins. The only thing worth changing is
the TP split, which re-confirms Run 1 on a 25x bigger grid.

Best of 525: `exec_tp1_pct=0`, `exec_tp2_pct=0`, `exec_tp2_stop_mode="TP1 price"`,
`exec_runner_trail="Structure (swing)"`, `exec_struct_trail_buf_tk=10` — **70.7R**.
The shipped default (30/40, TP1 price, structure 20) scores **47.9R** in the same grid.

## How it was measured

- Same corpus as Run 1: all 185,530 M15 XAUUSD bars, 2018-09-14 -> 2026-07-24, half-split
  2022-08-21. **187 trades in every one of the 525 rows** — exit levers never change which
  trades are taken, so win rate is flat at 72.2% across the entire grid.
- 525 combos = `exec_tp1_pct` {0,10,20,30,40} x `exec_tp2_pct` {0,10,20,30,40} x
  `exec_tp2_stop_mode` {TP1 price, Breakeven, One trail step behind} x trail
  {Structure @ 10/20/40/80 ticks, Fixed step @ 3/5/10}.
- Scored in R. `fill_model="bar"` (zero costs). ~6 hours wall clock on 11 workers.

## Result 1 — the runner trail: structure beats fixed step, without exception

| Trail mode + size | mean R | best R | worst R |
|---|---|---|---|
| **Structure (swing) @ 10 ticks** | **51.3** | **70.7** | 38.4 |
| Structure (swing) @ 20 ticks | 51.3 | 70.7 | 38.4 |
| Structure (swing) @ 40 ticks | 51.2 | 70.6 | 38.4 |
| Structure (swing) @ 80 ticks | 51.0 | 70.3 | 38.4 |
| Fixed step @ 10 | 46.3 | 62.5 | 38.4 |
| Fixed step @ 5 | 41.1 | 47.6 | 38.2 |
| Fixed step @ 3 | 38.9 | 41.0 | 36.8 |

Every structure setting beats every fixed-step setting on both mean and best. The shipped
default is already the right family. **The best fixed-step config anywhere in the grid is
62.5R against structure's 70.7R** — an 8R penalty for using a price grid instead of the
structure engine's swings.

**The buffer distance is nearly irrelevant.** 10 -> 80 ticks is an 8x change in how far behind
the swing the stop sits, and it moves the result by 0.4R (70.7 -> 70.3). This directly answers
"do the runners need more room": no — not room measured in ticks behind the swing. The swing
anchor itself is what protects the runner; the buffer is noise on top of it. Keeping the shipped
20 is fine, and 10 is not a meaningful improvement (0.03R) — do not chase it.

## Result 2 — the TP2 stop floor: one mode is actively harmful

| Floor mode | mean R | best R | best config's MaxDD |
|---|---|---|---|
| Breakeven | **51.5** | 69.0 | **−5.1R** |
| **TP1 price** (shipped) | 50.5 | **70.7** | −6.0R |
| One trail step behind | 39.9 | **42.3** | −4.8R |

**"One trail step behind" caps the strategy.** Its best result anywhere in 175 combos is 42.3R —
worse than the shipped default's 47.9R and 28R behind the grid winner. It is defined never to sit
below breakeven, so on a runner it keeps ratcheting up under price and scratches the trade out
early. Do not use it.

"TP1 price" and "Breakeven" are effectively a tie: TP1 price takes the highest single result
(70.7R), Breakeven is 1R better on average and holds a smaller worst drawdown (−5.1R vs −6.0R).
The choice between them is a smoothness preference, not an edge. Shipped default stands.

## Result 3 — the TP split is the only real lever, and it is monotonic in both directions

| TP1 % | mean R | | TP2 % | mean R |
|---|---|---|---|---|
| **0** | **51.2** | | **0** | **49.9** |
| 10 | 49.3 | | 10 | 48.6 |
| 20 | 47.3 | | 20 | 47.3 |
| 30 | 45.3 | | 30 | 46.0 |
| 40 | 43.4 | | 40 | 44.7 |

Roughly **−2R for every 10% moved off the runner**, on both rungs, with no exception anywhere.
This is Run 1's finding re-measured over 25x the combinations and with the dropdowns varying
underneath it — the monotonic shape survives, which is what a real edge looks like.

## What it means

The exit ladder is essentially **one-dimensional**. Of four levers swept, one carries almost all
the variance (the TP split), one is directionally settled but flat once you pick the right family
(trail: structure yes, buffer whatever), one has a single wrong answer to avoid ("One trail step
behind"), and one is a tie.

**This is a mostly negative result, and that is useful.** Three of the four levers do not need
tuning — they need leaving alone. The brother's TradingView-tested combo was already correct on
both dropdowns, which is independent corroboration that his manual tuning found the real settings.

Winner's per-year R (identical to Run 1's winner — the same config):

```
2018 −1.8   2019 +4.0   2020 +14.8   2021 +3.6   2022 −2.3
2023 +10.0  2024 +14.3  2025 +14.6   2026 +13.5
```

Shipped default's per-year R, for comparison — note it is worse in EVERY positive year, and the
gap is widest in the big years (2020: +5.7 vs +14.8; 2024: +6.2 vs +14.3):

```
2018 −1.4   2019 +3.4   2020 +5.7   2021 +4.9   2022 −2.1
2023 +9.1   2024 +6.2   2025 +11.4  2026 +10.7
```

The shipped default loses slightly less in the two down years (−1.4/−2.1 vs −1.8/−2.3). Banking
partials is genuinely buying a little downside protection — it just costs far more upside than it
saves.

## Before this becomes the default

Same three requirements as Run 1 (tick-mode re-run, one-commit-across-four-files, 187 trades is
still 187). Nothing here changes them, and Run 2 does not add a new requirement: the winning
config is the shipped config with two numbers changed, so there is no new code path to validate.

Harness: `scratchpad/sweep.py` + `run_stage1.py`, 11 workers, ~6h. Throwaway, not committed.

---

# Run 3 — Stop TIMING Sweep (2026-07-26)

**Question:** not how far the stop moves, but WHEN. At what point should the trade go to
breakeven, and at what point should the runner start trailing? Aaron's framing: "what makes it
best risk to reward."
**Answer:** the shipped timing is right. Waiting longer to protect DOES produce much bigger
average winners — up to 3.7x — but it loses money doing it, every single step of the way. Do not
change this.

This also settles a question that has been open in `CLAUDE.md` since 2026-07-16 — *"whether
stop→BE on TP1 caps runners."* **It does not.** It pays for itself. See below.

## How it was measured

**These two dials do not exist in the bot.** The shipped ladder hardcodes both moments
(breakeven the instant price touches TP1, floor + trail the instant it touches TP2), so they had
to be built to be measured. `scratchpad/timing.py` subclasses `Execution` and overrides
`_advance_stage` + `_stage2_floor` — research code only, nothing in the production package was
touched, and the baseline `be_at="TP1", trail_at="TP2"` was verified to reproduce the untouched
bot trade-for-trade before the grid ran.

- 35 combos: `be_at` {TP1, 0.5R, 1R, 1.5R, 2R, TP2, never} x `trail_at` {TP2, TP1, 1R, 2R, 3R}.
- Held at Run 1/2's winning TP split (nothing banked early, 100% on the runner) and the structure
  trail at 20 ticks — so the ONLY thing varying is timing.
- R multiples are measured off the trade's own entry-to-stop distance (`Execution._sl`, the frozen
  1R yardstick), so an R trigger already scales with the leg's size. **This is why ATR was not
  used** — ATR would re-derive volatility scaling that R already has. ATR's real place is trail
  DISTANCE, not trigger timing, and that is a separate unrun question.
- Same corpus: 185,530 M15 bars, 2018-09-14 -> 2026-07-24, half-split 2022-08-21.
- **Trade count is NOT constant here** (unlike Runs 1-2, which were all 187). It ranges 177-187,
  because when a position closes changes when the bot is next flat and able to take a setup. A
  row with fewer trades is not directly comparable per-trade; total R still is.

## Result — the full grid, best first

| Breakeven at | Trail at | n | Total R | Avg win R | Avg loss R | Win% | MaxDD R | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|---|---|
| TP1 | 3R | 182 | **77.0** | 0.82 | −0.71 | 73.6 | −5.1 | 17.2 | 59.8 |
| **TP1** | **TP2** | 187 | **70.7** | 0.80 | −0.73 | 72.2 | −6.0 | 16.0 | 54.6 |
| TP1 | 2R | 185 | 69.2 | 0.77 | −0.72 | 73.0 | −5.1 | 15.7 | 53.5 |
| TP1 | TP1 | 187 | 69.2 | 0.79 | −0.73 | 72.2 | −5.1 | 16.4 | 52.8 |
| 1.5R | TP1 | 187 | 69.2 | 0.79 | −0.73 | 72.2 | −5.1 | 16.4 | 52.8 |
| 2R | TP1 | 187 | 69.2 | 0.79 | −0.73 | 72.2 | −5.1 | 16.4 | 52.8 |
| TP2 | TP1 | 187 | 69.2 | 0.79 | −0.73 | 72.2 | −5.1 | 16.4 | 52.8 |
| 0.5R | TP2 | 187 | 68.6 | 0.84 | −0.73 | 70.1 | −6.4 | 17.8 | 50.8 |
| 0.5R | 3R | 187 | 68.1 | 0.84 | −0.74 | 70.3 | −5.3 | 14.8 | 53.3 |
| 1R | TP2 | 187 | 68.0 | 1.13 | −0.91 | 62.6 | −7.5 | 18.4 | 49.6 |
| 2R | TP2 | 187 | 67.0 | 1.39 | −0.97 | 56.1 | −11.4 | 20.7 | 46.3 |
| TP2 | TP2 | 187 | 67.0 | 1.39 | −0.97 | 56.1 | −11.4 | 20.7 | 46.3 |
| TP2 | 3R | 187 | 64.8 | 1.35 | −0.97 | 57.1 | −12.2 | 18.2 | 46.5 |
| 0.5R | 1R | 187 | 64.6 | 0.81 | −0.73 | 70.1 | −6.8 | 16.9 | 47.7 |
| 1R | 3R | 187 | 64.5 | 1.16 | −0.94 | 61.5 | −10.1 | 14.4 | 50.0 |
| 1R | TP1 | 187 | 64.2 | 0.74 | −0.68 | 71.7 | −4.9 | 18.3 | 45.9 |
| TP1 | 1R | 187 | 64.0 | 0.74 | −0.68 | 71.7 | −4.9 | 18.3 | 45.7 |
| 2R | 3R | 180 | 63.9 | 2.24 | −0.99 | 41.7 | −24.1 | 12.4 | 51.4 |
| 0.5R | 2R | 187 | 62.9 | 0.78 | −0.74 | 70.8 | −6.8 | 15.3 | 47.7 |
| 0.5R | TP1 | 187 | 62.3 | 0.71 | −0.63 | 71.7 | −5.8 | 15.2 | 47.1 |
| 1R | 1R | 187 | 60.5 | 1.15 | −0.94 | 60.4 | −7.9 | 14.7 | 45.8 |
| 1.5R | 1R | 187 | 60.5 | 1.15 | −0.94 | 60.4 | −7.9 | 14.7 | 45.8 |
| 2R | 1R | 187 | 60.5 | 1.15 | −0.94 | 60.4 | −7.9 | 14.7 | 45.8 |
| TP2 | 2R | 187 | 60.0 | 1.31 | −0.97 | 56.8 | −10.9 | 16.8 | 43.2 |
| 1R | 2R | 187 | 59.7 | 1.13 | −0.94 | 61.1 | −7.9 | 13.0 | 46.7 |
| 1.5R | TP2 | 187 | 59.1 | 1.28 | −0.97 | 57.2 | −10.3 | 11.7 | 47.4 |
| 2R | 2R | 183 | 59.1 | 2.18 | −0.99 | 41.5 | −23.5 | 9.5 | 49.6 |
| TP2 | 1R | 187 | 59.1 | 1.05 | −0.91 | 62.6 | −8.8 | 17.4 | 41.6 |
| 1.5R | 3R | 185 | 55.2 | 1.57 | −0.99 | 50.5 | −16.1 | 6.4 | 48.8 |
| never | TP1 | 177 | 55.2 | 2.91 | −0.91 | 31.6 | −20.6 | 7.7 | 47.5 |
| never | 3R | 177 | 54.4 | **3.68** | −0.98 | 27.7 | −19.9 | 6.3 | 48.1 |
| never | 1R | 177 | 53.3 | 2.96 | −0.92 | 31.0 | −20.5 | 8.0 | 45.2 |
| never | 2R | 177 | 53.1 | 3.05 | −0.96 | 31.1 | −26.3 | 3.9 | 49.2 |
| never | TP2 | 177 | 53.0 | 2.96 | −0.92 | 31.0 | −21.0 | 7.5 | 45.5 |
| 1.5R | 2R | 185 | 50.5 | 1.52 | −0.99 | 50.3 | −15.5 | 4.9 | 45.5 |

Rows that tie exactly are not a bug — when `trail_at` fires at or before `be_at`, stage 2
supersedes stage 1 and the breakeven trigger is never reached, so several `be_at` values collapse
onto the same behaviour.

## The top row is NOT an improvement — read this before adopting it

`be=TP1 / trail=3R` scores 77.0R against the shipped 70.7R, and it holds a SMALLER drawdown
(−5.1R vs −6.0R). It looks free. The per-year split says otherwise:

| | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| shipped (TP1/TP2) | −1.8 | +4.0 | +14.8 | +3.6 | −2.3 | +10.0 | **+14.3** | **+14.6** | +13.5 |
| top row (TP1/3R) | −1.8 | +4.4 | +14.4 | +4.3 | −0.4 | +10.6 | **+22.6** | **+8.0** | +14.9 |

It gained **+8.3R in 2024** and lost **−6.7R in 2025**. The entire +6.3R headline is one good
year and one bad year nearly cancelling, on a config that is otherwise a coin-flip year to year.
That is noise redistribution, not an edge. **Recommendation: do not adopt.** Two extra columns
also warn against it — it takes 5 fewer trades (182 vs 187), so it is not even the same sample,
and its avg winner is 0.82R against the shipped 0.80R, i.e. it did not actually produce longer
runs.

## What it means — the real answer to "how do I get further runs?"

**You can absolutely get bigger runs. It costs more than it pays.** Ranked by how long you wait
before protecting the trade:

| Breakeven at | Avg winner | Win% | Total R | MaxDD R |
|---|---|---|---|---|
| **TP1 (shipped)** | **+0.80R** | **72%** | **70.7** | **−6.0** |
| 1R | +1.13R | 63% | 68.0 | −7.5 |
| 2R | +1.39R | 56% | 67.0 | −11.4 |
| never | +2.96R | 31% | 53.0 | −21.0 |

Average winner grows **3.7x**. Total R falls 25% and drawdown grows **3.5x**. The trade-off is
strictly bad at every step — there is no sweet spot in the middle where the bigger runs start
paying for themselves. Waiting is not rewarded here.

**The stop→BE rule pays for itself — the open question is settled.** Average LOSS is −0.73R with
breakeven at TP1 and −0.92R to −0.99R without it. That 0.2R per loser, over ~50 losers, is the
whole difference. The rule is not capping runners; it is converting would-be full losses into
scratches, exactly as `CLAUDE.md` describes, and the conversion is worth more than the upside it
gives up.

**The biggest single winner was +15.03R in ALL 35 combos.** Identical to the cent, in every row.
The best trade in nine years never traded against its stop, so no stop-timing rule could touch
it. Stop timing only reaches the MIDDLE of the distribution — and there, protecting early wins.
This is the strongest argument in the whole run: the trades that make the money are not the ones
this lever controls.

## What was NOT measured

**ATR-based trail DISTANCE.** R-based triggers answer the timing question (R already scales with
the leg), but nothing here tested sizing the trail's distance off volatility — e.g. half an ATR
behind the confirmed swing instead of a flat 20 ticks. Run 2 showed the fixed buffer is nearly
irrelevant (0.4R across an 8x range), which weakly suggests a volatility-scaled version would
also be flat, but it has not been run. Kept separate deliberately so its effect stays
distinguishable.

## Status

**Nothing to adopt.** Both dials are already at their best shipped values, and the one row that
beats them fails the per-year check. If a future run does want to change either moment, note that
**both are hardcoded in Python AND in `mpc_strategy.pine`** — this would be new inputs in both,
not a settings tweak.

Harness: `scratchpad/timing.py` (the two dials) + `sweep2.py` + `run_timing.py`, 2 workers, ~4h
wall clock under contention with Run 2. Throwaway, not committed. `sweep2.py` is a COPY of
`sweep.py` rather than an edit, because Run 2's job was importing `sweep.py` live at the time.

---

# Run 4 — Stop PLACEMENT Sweep (2026-07-26) — **INVALID, DO NOT USE THE NUMBERS**

**Question:** Aaron's, and still the best one asked so far — *"what R:R ratio should I use as a
dynamic stop loss to maximize profits?"* Runs 1-3 all held `exec_sl_level="1.0"`, so 1R was the
same distance in all 581 combinations. Nothing had ever varied the DENOMINATOR.

**Result: the sweep is invalid and its numbers are discarded.** It did, however, expose two real
defects that matter more than the answer would have. Recorded so nobody re-runs it blind.

## What was run

40 combos: `exec_sl_level` {0.618, 0.702, 0.786, 0.886, 1.0} x `exec_sl_buf_tk` {0, 20, 50, 100}
x TP split {0/0, 30/40}, everything else at the Run-2 winner. Same 185,530-bar corpus.

## Why it is invalid

The top rows looked spectacular — 298.8R, 216.5R, 215.7R against the shipped 70.7R. All fake.
The tell was in the per-year columns:

```
0.702 / 50tk    2024 = +260.5R  of 298.8R total ... and NO 2026
0.786 / 20tk    2023 = +200.3R  of 216.5R total ... and NO 2024, 2025, 2026
0.618 / 20tk    2020 =  −42.3R                   ... and nothing after
```

Every high scorer stops trading partway through history with one absurd year just before it
stops. Direct replay of `0.786 / 20tk` (`scratchpad/diag.py`):

```
bars 185,530   trades 111   equity at end  −$63,726.25
biggest |R| trade:  r = +221.87   risk_usd $297.56   qty 1,487.8
final trade:        r =  −18.16   qty 39,033.1   pnl −$141,792   ... in ONE bar
```

**Root cause: the stop landed on top of the entry.** The entry is a resting limit inside the
**0.5-0.886 fib band**. Four of the five `exec_sl_level` choices (0.618 / 0.702 / 0.786 / 0.886)
sit INSIDE that same band, so the stop can be placed at, or past, the entry price. Divide
`risk_usd` by `qty` on the trades above and the stop distance is **$0.20** — twenty cents on 15m
gold, far inside one bar's normal range.

From there it is arithmetic. Position size is `risk / stop_distance`, so a 20-cent stop on a
$7,800 risk builds a **39,033 oz position (~$78M notional)**. The next bar moves $3.60 against it
and takes **18x the intended risk** in a single bar. Equity goes negative, `risk_usd` goes to
zero, no further trades fill — which is exactly the truncated year list. The big R numbers are
the same detonation caught mid-explosion, before the losing side arrived.

**R was NOT the flawed metric here.** `r = pnl / risk_usd` is correct, and because the bot risks a
fixed % of equity, 1R is the same money at any stop distance — that part of the design was sound.
What broke is that the *realised* loss stopped being 1R once the stop was tighter than one bar's
range.

## The two real defects this found

1. **`exec_sl_level` is not a safe dropdown.** Only `"1.0"` (the leg origin) is structurally
   guaranteed to sit outside the entry band. The other four are presented in `config.py` as equal
   choices, and nothing anywhere validates that the resulting stop is on the correct side of the
   entry, or a sane distance from it. **Treat `exec_sl_level="1.0"` as the only supported value
   until a guard exists.** (Unverified here: whether `mpc_strategy.pine` has the same exposure. It
   offers the same dropdown, so assume yes until checked.)
2. **There is no floor on stop distance.** Note carefully what is and is not broken here.
   `execution.py:329` sizes the position as `qty = (equity * exec_risk_pct / 100) / dist` — risk-
   based sizing, working exactly as designed. A wider stop gives a SMALLER lot, a tighter stop a
   bigger one, and the dollar risk stays at `exec_risk_pct` of equity. Both detonating trades above
   confirm it: `297.56 / 1487.78` and `7806.62 / 39033.12` both come to the same `$0.20` distance.
   **The sizing math is correct and is not the defect.**

   The defect is the assumption underneath it: `exec_risk_pct` is the true risk only **if the exit
   happens at the stop price**. That is safe when the stop is wider than a typical bar — which
   `"1.0"` (the leg origin) always is — and worthless when it is narrower. A $0.20 stop on 15m gold
   sits inside a single bar's ordinary range, so price does not stop you at your stop; it travels
   through and you exit wherever the bar ends. The nominal 10% risk was realised as **~180% on one
   trade**. The correct guard is therefore a **floor on `dist`** (reject the setup, or widen, when
   the stop is closer than some ATR multiple), NOT a change to the sizing formula. A position-size
   or margin cap is a reasonable second backstop but treats the symptom, not the cause.

## The question is still open, and the bot cannot currently answer it

**This bot has no R:R dial.** Targets are fibs and the stop is a fib, so the ratio is an OUTPUT of
the leg's geometry, never an input. There is no setting that expresses "risk 1 to make 3", which
is why no sweep of existing parameters can answer Aaron's question. Two routes:

- **Cheap:** re-run this grid with a minimum-stop-distance guard (e.g. reject the setup if the
  stop is closer than some multiple of ATR, and COUNT the rejections per level). That gives an
  honest read on whether tighter stops are viable at all, and the rejection count is itself the
  answer — if 0.618 discards most of its setups, it is not a real option.
- **Real:** give the bot a stop whose distance does not come from fib geometry — ATR-based — with
  targets at fixed R multiples on top. This is the "dynamic stop loss" actually described, and the
  only version where R:R becomes a choice. New code in Python, new tests, and eventually the same
  inputs in `mpc_strategy.pine`.

Do the cheap one first: if tighter stops fail even with a clean guard, the ATR build has less to
offer than it appears.

Harness: `scratchpad/run_sl.py` + `sweep.py`, 11 workers, ~20 min. Diagnosis: `scratchpad/diag.py`.
Results file `sl.json` retained for reference only — **its rankings are meaningless.**

---

# Run 5 — "How do I cut the losers quicker?" (2026-07-26)

**Question:** Aaron's — *"when they lose, they go straight to the fib 1.0. I should be able to cut
quick, but I don't know what to use to cut quick."*
**Answer:** there is nothing to cut quicker WITH. Every early-exit lever the bot already has was
measured at **exactly zero effect**. The loss bucket has one mechanical cause, and the only thing
that touches it is stop DISTANCE — the lever Run 4 proved is unguarded. **Nothing adopted.**

## The diagnosis — every loss is the same trade

**A loss is a trade that never touched TP1.** Not "a trade that went the wrong way" — the two are
the same set. Once TP1 fills the stop stages to breakeven + `exec_be_buf_tk`, so the worst
remaining outcome is a scratch of about +0.1R. There is no other failure mode in the data.

That reframes the whole question. "Cut the loser quicker" is really **"decide sooner that TP1 is
not coming"** — and the numbers say the losers are not obviously wrong trades that could be spotted
early. They are trades that nearly worked:

| | n | median MFE | p25 | p75 |
|---|---|---|---|---|
| losses | 29 | **0.34R** | 0.20R | 0.45R |
| scratches | 28 | 0.49R | 0.37R | 0.70R |
| wins | 61 | 1.47R | 0.87R | 1.90R |

**The stop is at fib 1.0, so 1R is a median $15.43 of gold.** TP1 — a fib on the same leg — lands
roughly **0.45R** from entry. A losing trade therefore gets about three quarters of the way to the
level that would have saved it, turns, and travels the full $15 back to the stop. The margin
between "safe" and "full loss" is a third of the risk being taken.

**This is a stop-DISTANCE problem wearing a stop-TIMING costume.** Run 3 already proved the timing
is optimal and cannot be improved. What has never been varied safely is the denominator.

## The two "cut quick" toggles: measured at exactly zero

Both were run on the full corpus with `--set`, both produced **byte-identical trade lists** to the
baseline — same 118 trades, same 33.6R, same drawdown.

| Toggle | Result | Why |
|---|---|---|
| `exec_close_opp_sos=True` | **0 difference** | An opposite SOS never fires before SL or TP has already resolved the position. The lever is inert on this strategy, not merely unhelpful. |
| `exec_htf_exhaust_only=True` | **0 difference** | No trade in the window was ever taken into a fresh weekly breakout closure. The setup fades a sweep, and a sweep is never a `Close >` / `Close <` state. |

`exec_close_opp_sos` is listed in `CLAUDE.md`'s exit-ladder register as the "early bail-out" lever.
**It is not one.** Nothing is on the other end of it.

## A time stop is the wrong instinct — it would cut the winners

The obvious "cut quick" idea is a bar cap. Measured, it inverts:

| trades held longer than | n | sumR |
|---|---|---|
| 20 bars | 65 | **+36.6** |
| 40 bars | 49 | +36.2 |
| 60 bars | 41 | +32.7 |
| 100 bars | 23 | +27.0 |

All 33.6R of net comes from trades held past 20 bars; the sub-20-bar population is net negative.
Losers are bimodal — a quarter die inside 4 bars (nothing to cut, they were stopped immediately)
and the rest bleed for 80–350 bars. A time cap cannot separate the second group from the winners,
which live in the same range. **Do not build one.**

## The `exec_sl_level` re-run — and how it relates to Run 4

Run 4 swept this dropdown and detonated. This run swept it again deliberately, on a **different
window and a different buffer**, to see whether anything survives once the blow-ups are excluded.
**It does not overturn Run 4.** Read both together.

Differences from Run 4: window 2022-01 → 2026-07 (the M15 cache, 118 trades) instead of 2018+;
`exec_sl_buf_tk=0` instead of the {0,20,50,100} grid; shipped 30/40 TP split instead of Run 2's
0/0 winner. Scored in R, `fill_model="bar"`.

| SL level | median stop | trades | sumR | MaxDD | max loss streak | worst year |
|---|---|---|---|---|---|---|
| **1.0** (shipped) | $15.43 | 118 | 33.6 | −5.7R | 3 | 2022: −3.7 |
| 0.886 | $11.50 | 118 | 47.5 | −6.2R | 4 | 2022: −4.4 |
| **0.786** | **$8.17** | 108 | **59.3** | **−6.1R** | 3 | **2022: +0.7** |
| 0.702 | $5.40 | 94 | 21.6 | — | — | degenerate |
| 0.618 | $2.53 | 69 | 205.4 | — | — | **garbage** |

**0.618 and 0.702 are Run 4's failure reproducing exactly.** 0.618 puts 15 of its 69 trades on a
sub-$1 stop — inside the spread on 15m gold — and its 205.4R with a 17.42R average winner is the
same division-by-a-tiny-denominator artifact Run 4 diagnosed. Run 4's root cause is confirmed
independently on a second window.

**0.786 survives two stress tests, 0.886 fails one.** Stripping the top 3 trades from each:
0.786 still leads **32.9R vs 18.8R** shipped, while 0.886 collapses to **16.2R — below baseline**,
so 0.886's headline is outliers. Dropping every trade whose stop was under \$2 (unrealistically
tight): 0.786 = **50.2R** on 100 trades, shipped = 33.6R on 118. 0.786 is also the only setting
positive in all five years, and it turns the shipped default's losing 2022 (−3.7R) into +0.7R.

**Drawdown does not move.** −6.1R at 0.786 against −5.7R shipped, with the same 3-trade maximum
losing streak. The tighter stop takes more losses (37 vs 29) but each is still −1R while every win
is worth more R, because the targets did not move and the denominator shrank. That is the entire
mechanism, and it is why the return roughly doubles for no extra pain.

## Why 0.786 is still NOT adoptable

**8 of its 108 trades had a stop under \$2, and one was \$0.81.** That is Run 4's defect, live, on
this window — the entry is a resting limit inside the 0.5–0.886 band and 0.786 sits inside that
same band, so the stop can land on top of the entry. It did not detonate here only because
`exec_sl_buf_tk=0` and the 2022+ window happened not to contain the pathological case that took
Run 4's account to −\$63k. **That is luck, not safety.** `exec_sl_level="1.0"` remains the only
supported value.

What this run adds to Run 4 is the *size of the prize*: the minimum-stop-distance guard is not
merely a safety fix, it is the thing standing between the bot and a measured **+26R** over 4.5
years. That reprioritises Run 4's defect 2 from "hygiene" to "the highest-value open item on this
bot."

## What to do next — Stage 1 of the OPEN plan, unchanged but now sharper

The plan below is correct and Run 5 does not modify it. It does sharpen two of its three questions
with real numbers to check against:

- **"How tight can a stop safely be?"** — 0.786 gives a median \$8.17 stop and 100 of 108 trades
  were fine at it. Stage 1's winners' MAE distribution should show whether that generalises or
  whether the 8 casualties are the leading edge of a cliff.
- **"Is the current stop too wide?"** — provisionally **yes**. Run 5 is the first measurement
  pointing that way, but it is not proof until the guard exists and the sweep is re-run clean.
- **"What R:R is even available?"** — unchanged; Stage 1's MFE distribution still owns it.

Concretely: build the `dist` floor (reject the setup when the stop is closer than some ATR
multiple), re-run this exact grid with it in place, and **count the rejections per level**. If
0.786 keeps most of its setups under the guard, it becomes a real candidate. If the guard discards
most of them, the ATR-stop build in Stage 2 is the only route and this dropdown should be retired.

## How it was measured

`backtest/tools/run_report.py --no-regime` off the M15 cache, 2022-01-02 → 2026-07-24, 118 trades
at the shipped config, `fill_model="bar"` (zero costs), `--set` for each variant. Per-trade
`mfe_r` / `mae_r` / `bars_held` / `exit_reason` read straight from the emitted `trades.csv`.

**Caveat on the tighter-stop numbers:** bar mode charges nothing. An \$8 stop is roughly twice as
cost-sensitive as a \$15 one, so spread + commission eat a materially larger share of it. Any
tick-mode re-run will come in below 59.3R — the direction is solid, the magnitude is optimistic.
Also note the corpus is the 2022+ cache (118 trades), NOT the 187-trade 2018+ corpus Runs 1–4
used, so Run 5's R totals are not directly comparable to theirs.

Harness: scratchpad only, nothing committed.

---

# OPEN — "What R:R should I use?" and the plan to answer it

**Status: not started. Aaron's question, still unanswered as of 2026-07-26.** Runs 1-4 could not
answer it and no further sweep of existing parameters can. Read Run 4 first — it is why.

## Why no existing sweep can answer this

**The bot has no R:R dial.** The stop is a fib, the targets are fibs, so the ratio is an OUTPUT of
the leg's geometry, never an input. No combination of shipped parameters expresses "risk 1 to make
3." Run 4 tried to get at it by moving the stop and detonated (four of the five `exec_sl_level`
values can land on top of the entry).

**Sizing is NOT the obstacle and does NOT need changing.** `execution.py:329` already does
`qty = (equity * exec_risk_pct / 100) / dist` — risk-based, dynamic, correct. A wider stop gives a
smaller lot; the dollar risk stays at 10% of equity. The real constraint Run 4 exposed is that
`exec_risk_pct` is the true risk *only if the exit happens at the stop price*, which fails once the
stop is tighter than a typical bar. So the live question is not "what ratio" but **"how close can
the stop get before a single bar can jump it"** — an ATR question, and answerable.

## Stage 1 — measure what the bot already does (NO new strategy code, ~30 min)

Almost everything needed already exists. Every `Trade` already carries **`mfe_usd`** (the most it
ever showed in profit) and **`mae_usd`** (the deepest it sat against us) — divide by `risk_usd` for
R. ATR is NOT in the replay `BarState`, but it is ~10 lines off the OHLC frame in a research
script; **do not build an ATR engine for this** (`engines/equal_highs_lows/` already computes its
own ATR(50) internally — that is precedent for a local calc, not for a new shared engine).

Replay the existing 187 trades at the shipped config and record per trade: **ATR at entry**, the
**current fib stop distance in ATR units**, **MFE in R**, **MAE in R**. Three answers fall out:

1. **How tight can a stop safely be?** = the MAE distribution of the WINNERS. If winners routinely
   dip 0.6R before running, any stop tighter than that kills the trades that pay. That is the
   floor, measured instead of guessed — and it is the guard Run 4 proved is missing.
2. **What R:R is even available?** = the MFE distribution. If the typical trade never shows more
   than 2R, a 3:1 target is fantasy regardless of stop placement.
3. **Is the current stop too wide?** = stop distance in ATR. If it sits at 4 ATR while winners only
   ever dip 1 ATR, there is genuine room to tighten — and tightening means a bigger position for
   the same 10%, which is the whole prize.

Stage 1 may well show Stages 2-3 are not worth doing. Run it first.

## Stage 2 — build the ATR stop (ONLY if Stage 1 shows room; ~2h build + 30 min run)

New config: `exec_sl_mode` ∈ {Fib, ATR} and `exec_sl_atr_mult`, plus the **minimum-stop-distance
guard applied in BOTH modes** so the existing fib path gets protected too (that guard is worth
landing on its own merits — see Run 4 defect 2). Then sweep the multiplier.

## Stage 3 — fixed-R targets (expected to FAIL; do not start before Stage 1)

Replace the fib TP ladder with targets at fixed R multiples. **Prediction on the record: this
loses.** The biggest winner was 15.03R against a 0.8R average — a hugely dispersed distribution,
and fixed targets only beat an open-ended runner when outcomes cluster. Runs 1-3 already showed
every point of size taken off the runner costs R. Stage 1's MFE spread will confirm or kill it
properly, which is the honest way to retire the idea.

## Constraint on all of it

Stage 1 changes nothing and is safe. **Anything ADOPTED from Stage 2 or 3 is new inputs in
`config.py` AND in `mpc_strategy.pine` / `mpc_strategy_export.pine` / `compare_strategy.py`, in one
commit, with Pine↔Python parity re-run green** — the brother's Pine is the source of truth and
must gain the same levers or parity breaks.

---

# Run 6 — 2026-07-27 — "cut the losers early" is dead. The answer is position size.

**The question, Aaron's words:** *"when I lose a trade it runs straight to stop loss. I need
something, some confluence that could help me know when to cut trades early. Look at the trades
I'm losing — is there a pattern I could block? And what can I use to dynamically assess whether
to cut a trade early?"*

**The answer: no, and the reason is not a missing indicator.** Three independent families of
early-exit rule were tested and **every single variant lost money.** The premise itself does not
survive contact with the data — no trade in eight years ran straight to its stop.

This supersedes Run 5's version of the same question. Run 5 tested two toggles on a partial
window; Run 6 tests the full history at the SHIPPED config (SL 0.886 + TP 0/0), with the
**per-bar R path of every trade captured**, so a cut rule can be scored against the actual ride
instead of guessed at from the extremes.

## How it was measured

Window **2018-09-13 → 2026-07-27** (185,649 15m bars — the broker's whole intraday history),
`exec_sl_level=0.886`, TP rungs 0/0, structure trail. **188 trades, 107.7R, 293x, −54.9% maxDD.**

Two artefacts, and the second is the new one:

- `run_report.py --set exec_sl_level=0.886` → `trades.csv` (per-trade tags + excursion extremes).
- A **path capture**: the same replay, snapshotting each open trade's R at every bar's close plus
  that bar's own high/low in R. 12,838 path rows over 188 trades. A stop cannot move price, so the
  path is invariant to the stop — which is what makes replaying it against a different stop an
  honest counterfactual. Exit-only rules can therefore be scored offline in a second each, instead
  of a 10-minute replay per variant. **Rules that change ENTRY cannot be scored this way** (fewer
  trades = different equity = different sizing) and were run properly instead.

Convention, matching `_advance_stage`: a stop moved on bar N's close is live from bar N+1. Checking
the trigger bar's own low would let a rule exit on a move it only learned about at that bar's close.

## Finding 1 — there is no trade to cut. Every loser goes into profit first.

`run_report.py`'s never-worked column reads **0 in every one of the eight years.** Not one losing
trade failed to reach +0.1R before it died.

| losers' MFE (how far in profit before they lost) | R |
|---|---|
| minimum, all 61 losses | **+0.09** |
| 25th pct | +0.27 |
| **median** | **+0.51** |
| 75th pct | +1.00 |
| max | +4.03 |

32 of 61 losers showed **+0.5R or better** and gave it all back plus the full stop. 16 showed
+1.0R. 3 showed +2.0R. The loss bucket is not bad entries — it is good entries that reversed.

**Why they get no protection:** the stop only lifts to breakeven when the TP1 PRICE is touched, and
TP1 is a fib, not a risk level. Measured across the 138 trades that reached stage 1, that trigger
fires at a **median +0.76R and a 90th-percentile +2.69R.** So a trade can run +1.5R and round-trip
to a full stop with the stop never having moved. **50 of the 61 losers never reached stage 1 at all.**

That is a real mechanical gap, and it is the obvious thing to fix. Finding 2 is why fixing it loses money.

## Finding 2 — winners and losers are indistinguishable while the trade is live

The eventual winners are underwater too. Their MAE: **median −0.36R, 25th pct −0.57R, 10th pct
−0.74R.** A winner routinely sits three-quarters of the way to the stop before it pays.

So the two populations overlap almost completely. Share of losers whose R sits inside the winners'
10–90 band at bar N — i.e. the share a rule at that bar cannot tell apart:

| bar since entry | winners' median R | losers' median R | losers indistinguishable |
|---|---|---|---|
| 1 | +0.13 | −0.04 | **55%** |
| 3 | +0.19 | −0.02 | **70%** |
| 8 | +0.37 | −0.22 | **62%** |
| 20 | +0.77 | −0.28 | **39%** |

There is no early tell. Not at bar 3, not at bar 20. **Any rule that cuts a loser early cuts a
winner early**, and the winners are where the entire edge is (avgWin 2.75R, max 23.9R, avgLoss −0.92R).

## Finding 3 — all three cut families lose money. Best variant of each:

| rule | sumR | vs base | helped | hurt | final | maxDD |
|---|---|---|---|---|---|---|
| **baseline (shipped)** | **107.7** | — | — | — | **293x** | **−54.9%** |
| breakeven at +0.5R | 76.0 | −31.8 | 17 | 19 | 64x | −43.0% |
| breakeven at +1.0R | 104.9 | −2.8 | 7 | 5 | 256x | −50.6% |
| stop to +0.25R at +1.5R | 80.8 | −26.9 | 8 | 4 | — | — |
| give-back cap (past 2R keep 25%) | 79.2 | −28.6 | 6 | 4 | — | — |
| time stop: below 0R at bar 48 → close | 95.5 | −12.2 | — | 14 | 186x | −56.1% |
| time stop: below 0R at bar 10 → close | 77.1 | −30.6 | — | 47 | 43x | −56.9% |

Every row is negative. Note the two traps:

- **The rule that saves the most trades loses the most money.** BE at +0.5R rescues 17 losers and
  destroys 19 winners — and it costs 78% of the account (293x → 64x) to shave 12 points off the
  drawdown. The rescued trades are worth ~1R each; the killed ones are worth many.
- **Time stops make the drawdown WORSE, not better** (−54.9% → −56.9%). Losers already die fast:
  median hold **10 bars** for a loser vs **75 bars** for a winner. There is nothing to cut short —
  a time stop only reaches the slow trades, and the slow trades are the winners.

## Finding 4 — no entry filter either. Ten candidates, all fail.

| block | trades cut | their R | new final | new maxDD |
|---|---|---|---|---|
| *(keep everything)* | — | — | **293x** | **−54.9%** |
| stop < $2 | 8 | −0.6 | **338x** | −54.3% |
| stop < $5 | 51 | +21.3 | 107x | −46.2% |
| stop > $25 | 21 | +17.9 | 66x | −55.0% |
| Asia session | 45 | +20.9 | 165x | −50.2% |
| Late session | 13 | +2.6 | 236x | −55.0% |
| TRANSITIONING regime | 20 | +4.3 | 223x | −59.9% |
| longs | 85 | +42.5 | 29x | −56.8% |
| Friday | 23 | +21.7 | 122x | −55.1% |
| Monday | 26 | +29.1 | 70x | −56.0% |

Only **stop < $2** is positive, and it is positive because those 8 trades are collectively worth
−0.6R — it is the degenerate-stop hazard from Run 4, not a market pattern. Everything else that
looks like a "losing bucket" is carrying winners that pay for it.

`exec_close_opp_sos` was re-run ON over the full window as a real structure-based cut signal:
**188 trades either way, 107.7R either way.** An opposite SOS essentially never prints while a
position is open. Confirms Run 5's zero-effect result on a longer window.

## Finding 5 — the drawdown is a LOSING STREAK, not give-back. So risk % is the lever.

The −54.9% drawdown is one stretch, **2021-11-28 → 2022-11-14, 20 trades**:

```
+0.0 +0.0 -1.0 +0.1 -1.0 -1.0 +0.0 -1.0 -1.0 +0.1 +1.1 +0.1 -1.0 -1.0 -1.0 +0.1 +0.0 +0.0 +0.0 -1.0
```

Nine clean −1.0R full stops and no give-back at all. **No exit rule can touch this** — these trades
went to the stop they were given, which is the stop doing its job. What made it −54.9% is that each
of those nine was 10% of the account.

Longest consecutive full-loss run in eight years: **4** (0.9⁴ = −34% at 10% risk; −19% at 5%).

| risk % | final | maxDD |
|---|---|---|
| 2% | 6x | −14.0% |
| 3% | 13x | −20.3% |
| 5% | **41x** | **−31.9%** |
| 7% | 104x | −42.1% |
| **10% (shipped)** | **293x** | **−54.9%** |

This is the whole answer to *"save me some max drawdown."* It is the one dial that moves drawdown
without touching the edge, because it does not interact with the trade logic at all.

## Verdict

1. **Do not build an early-cut rule.** Three families, ~40 variants, every one negative. The
   strategy's edge is a fat right tail and every protective rule taxes the tail to rescue trades
   worth 1R. This question is now closed — reopen it only with a signal that separates winners from
   losers *while the trade is live*, which Finding 2 says does not exist in anything tested.
2. **Do not raise the TP1-touch breakeven trigger into an R trigger**, despite Finding 1 making it
   look like an obvious gap. It is the BE-at-+X row of Finding 3 and it loses money at every X.
3. **The minimum-stop-distance guard is still worth doing** — the only positive filter found
   (293x → 338x, and it removes the single −1.98R trade, the one trade in eight years that lost
   more than the 1R it risked). Small, but free, and it closes a real hazard rather than curve-fitting.
4. **Drawdown is a sizing decision, not a logic decision.** 10% risk earns 293x and costs 55%.
   5% earns 41x and costs 32%. Nothing in the strategy changes either number — pick the ride.

## What was NOT measured

- Rules using an indicator the bot does not currently read (a live RSI-divergence flip against the
  position, an opposing FVG forming, price closing back inside the entry zone). Finding 2 makes
  these unpromising — the populations overlap on PRICE, and these all derive from price — but they
  are not disproven.
- Anything that changes ENTRY count, beyond the ten single-bucket blocks above. Combinations were
  not swept, deliberately: at n=188 a two-way block sweep will find something that looks good and
  is noise.
