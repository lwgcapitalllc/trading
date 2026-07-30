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
| 7 | 2026-07-27 | **The minimum-stop guard, properly measured** — 17 real replays (not row-filtering), 8 years, three independent definitions of "too tight": fixed $, % of price, ×ATR(14) | **The guard PASSES, at a MILD threshold only.** All three definitions agree: light = **+0.7 to +2.7R**, medium/heavy = **−12 to −39R**. Best is **`pct 0.1`** (stop ≥ 0.1% of price): 182 trades, +2.5R, blocks the −1.98R trade, leaves 2021/2024/2025/2026 **untouched**. It is a **safety** rule — the R gain is noise-level, and it does **not** fix drawdown (−54.9% → −54.3%). | **measured, awaiting Aaron's go** |
| 8 | 2026-07-28 | *"the runner hands too much back"* — the whole runner-exit space at once: 4 trail families (fixed $, chandelier ATR, % trail, giveback cap), hard TP ceilings, "clamp once it's a monster", an RSI-divergence exit, and a NEW swing-ratchet trail | **ADOPTED: `"Structure + % ratchet"` at 1.0%.** Share of each run actually banked **43% → 53%**, same 164 trades, same entries, **identical % drawdown**. Everything else lost: every tightening family costs 60–90% of net, a hard TP costs 20%+ or never fires, the divergence exit costs 77%. | **SHIPPED** — default in 4 Pine files + both Python bots |
| 9 | 2026-07-28 | *"why not bank at the extension fibs?"* — Aaron's own hand rule (0.0 / −0.272 / −0.414 / −0.618) plus a stop-floor variant and a deep-rung variant (−1/−2/−3/−4/−6). 40 replays across 3 designs | **REJECTED in every form.** Shallow rungs **109.3R → 69.1R**; as a stop floor → **56.1R**; deep rungs → **106.3R**. Cause: only **29 of 164** trades ever reach 0.0 and the **11 past −0.618 carry 106R of the 109R**, so any fixed ceiling caps exactly what pays. | **do not build it** — read the verdict |
| 10 | 2026-07-29 | *"cut the trade by the SHAPE of its path"* — Aaron's in-and-out-of-profit idea, a stall variant, and his fib-level cut. 3 families, ~130 variants + 6 real replays, on captured per-bar R paths | **Two rejected, one mild keeper.** The in/out pattern is **not a loss signal** (trades showing it lose 18–30% of the time vs a **32% base rate**) — every cut loses, best is −70.5R. The fib cut at **0.886 fires 0 times** (it IS the stop) and at 0.786 costs **−27.0R** (35 losers saved +12.6R, 4 winners cost −33.6R). Only the **stall** cut works: no +0.15R by bar 3 → close = **+4.8R real-replayed**, and **drawdown does not move (54.9%)**. | measured, **not adopted** |
| 11 | 2026-07-29 | **Run 5's `exec_sl_level` sweep RE-RUN with Run 7's guard installed** — the file's stated highest-value open item. 5 SL levels × 4 guard strengths, 14 full-history replays | **ANSWERED, negatively. 0.886 is the right level.** 0.786 = **105.2R unguarded (below shipped) and 49.0R guarded**, and 72% of its unguarded total is 2024+2026 — the guard turns its 2024 from **+50.4R to −2.9R**, i.e. the tight-stop trades ARE the money. 0.702/0.618 reproduce Run 4's detonation on a third window. **The one improvement is `0.886 + pct 0.1`: 112.0R, maxDD 54.3%, worst trade −1.98R → −1.00R.** | **Run 7's guard CONFIRMED — awaiting Aaron's go** |
| 12 | 2026-07-29 | *"what if I took the MISSED setups?"* — Aaron's question about the 2-of-3 misses that had sweep + SOS + the retrace but **no FVG in the zone**. Measured as an A/B on one input (`exec_req_fvg`), 2020-01-01 → 2026-07-29, plus a 3-level robustness sweep on the counterfactual entry price | **KEEP REQUIRING THE FVG.** 180 no-FVG misses, 173 would have filled at the 0.618 fallback: **50 win / 54 loss / 69 breakeven, +34.0R gross** — but they crowd out 17 real trades worth **+21.0R**, so the net is **+13.0R on 110.6R** while **drawdown goes 54.9% → 77.1%**. And it is not an edge: **40% of the +34R is ONE trade** (2020-01-02) and the sign **flips with the entry price** (+13.0R at fib 0.618, **−6.7R at 0.5**, −58.5R at 0.786). | **do not build it** — read the verdict |

✅ **Both Pine↔Python parity gates were re-run GREEN on 2026-07-29** (`compare_strategy.py`, 21,494
bars, at the shipped `exec_tp1_pct = exec_tp2_pct = 0` and carrying the ratchet through
`cfg_exitmode`/`cfg_trail_pct`; `compare_bleg.py`, 21,493 bars). This CLEARS the Run 8 stale-parity
warning — Runs 8–9 now describe the Pine Aaron trades. ⚠ One gap remains and it is the one that
matters for Run 11's recommendation: `mpc_strategy_export.pine` still emits **no `cfg_min_stop*`
column**, so parity is proven only at the `execMinStopMode = "Off"` default. Shipping the guard
means closing that hole in the same commit.

**Still open:** *"what R:R should I use as a dynamic stop loss?"* — the plan at the bottom of this
file under `# OPEN — "What R:R should I use?"` still stands, but **Run 11 has closed one of its two
routes.** The cheap route (re-sweep the fib dropdown behind a minimum-stop guard) is DONE and the
answer is that no fib level beats 0.886. So the only remaining route is Stage 2's **ATR-based stop
distance** — new code in `config.py` AND the Pine. Stage 1 (measure MFE/MAE/ATR on the existing
trades) is still the right first step and is now partly done: Runs 6 and 10 captured the per-bar R
paths, and `backtest/archive/2026-07-29_xauusd_15m_full_history/` carries every trade's `mfe_r`/
`mae_r` on disk.

**What Runs 6, 10 and 11 jointly establish about DRAWDOWN — stop re-deriving this.** Four
independent attack surfaces have now been swept: exit timing (Runs 3, 6), exit tightening (Run 8),
path-shape cuts (Run 10) and stop placement (Runs 4, 5, 11). **None of them moves the drawdown.**
The best figure any of them produced is 54.3%, against a 54.9% baseline. The reason is Run 6's
Finding 5 and it has survived every re-test: the −54.9% is a **losing streak of clean −1R stops**
(2021-11-28 → 2022-11-14, nine full stops in 20 trades), and a trade that goes to the stop it was
given is not an exit-rule problem. **Drawdown is a position-size decision** (10% → 54.9%,
5% → 31.9%, 3% → 20.3%) or a **portfolio** decision — and the portfolio route is blocked on the
A+ vs B-LEG overlap audit, which is still UNRUN and is now the highest-value open item on this bot.

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

   **AMENDED 2026-07-27 — the default is now `"0.886"`, by Aaron's decision.** It is the setting he
   trades; the parity run went green at it and Run 6 rode it over the full history (188 trades,
   107.7R) without a degenerate stop. The finding above is NOT retracted: 0.886 is still inside the
   entry band and neither defect is fixed, it simply never collapsed at this level, because 0.886
   is the deepest price the entry limit itself can rest at. **0.618 / 0.702 / 0.786 remain
   unsupported.** A partial guard now exists on the Pine side only — `execMinStopMode` (default
   "Off") refuses a setup whose stop is inside a %-of-price / fixed-$ / ATR floor. It is NOT ported
   to `config.py`, so the Python bot still has no floor at all.
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

⚠ **SUPERSEDED 2026-07-29 by Run 11, which ran exactly that test. This dropdown is now RETIRED as a
tuning lever.** On the full 7.9-year history 0.786 scores **105.2R unguarded — below the shipped
0.886's 109.5R** — with a WORSE drawdown (60.2% vs 54.9%), and with `pct 0.1` installed it collapses
to **49.0R**. The +26R prize this section describes was a 4.5-year-window artifact. Read Run 11
before quoting anything in Run 5's `exec_sl_level` table.

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

---

# Run 7 — 2026-07-27 — the minimum-stop guard, measured properly. It passes, but only mildly.

Run 6 left one live recommendation: the minimum-stop-distance guard, on the strength of a single
number (`stop < $2` → 293x → 338x). That number came from **filtering rows out of a finished trade
list**, which is not a test of the rule. Skipping an entry frees the bot to take the NEXT setup it
would otherwise have been in a position for, so the guard changes *which trades exist*, not just
which ones are counted. This run does it honestly.

## How it was measured

17 full 8-year replays (185,668 M15 bars, 2018-09-13 → 2026-07-27, `exec_sl_level="0.886"`, the
shipped config). The guard is a subclass of the shipped `Execution` that lets the real
`_place_entries` build the order and then drops it if `abs(edge - sl)` is under the floor — so
every other rule (arming, vetoes, blocked/missed recording) behaves exactly as shipped and **only
the placement decision changes**. No repo file was modified.

The engines + signals + sequence stream is built ONCE and shared across all 17 variants. That is
safe because the pipeline is strictly one-way — nothing reads execution state back — and it turns
~75 minutes of replay into ~5.

**Three independent definitions of "too tight", deliberately**, because the answer must not depend
on which one was picked:

| definition | what it is | why it is in the sweep |
|---|---|---|
| `fixed` | a flat dollar floor | simplest, but gold ran 1200 → 3300 over this window, so one number cannot mean the same thing at both ends |
| `pct` | floor as a % of price | self-scales with the price level, needs no new state, ports to Pine in one line |
| `atr` | floor as a fraction of ATR(14) | the honest volatility measure — the only one that reacts to a quiet vs violent market at the SAME price |

**The pass mark was set before the results arrived:** positive across a RANGE of thresholds and
degrading smoothly = a real rule. Positive at exactly one value and negative either side = a curve
fit, and a fail.

## The result

| guard | trades | sumR | final $ | x | maxDD | worst yr |
|---|---|---|---|---|---|---|
| **none (shipped)** | 188 | 107.7 | 2,931,537 | 293.2x | −54.9% | −4.0R |
| fixed 1 | 188 | 107.7 | 2,931,537 | 293.2x | −54.9% | −4.0R |
| **fixed 1.5** | 183 | **110.4** | 3,868,664 | 386.9x | −54.9% | −3.0R |
| fixed 2 | 180 | 108.4 | 3,380,685 | 338.1x | −54.3% | −3.0R |
| fixed 2.5 | 174 | 95.3 | 1,948,835 | 194.9x | −54.3% | −1.2R |
| fixed 3 | 169 | 89.5 | 1,140,728 | 114.1x | −54.3% | −2.1R |
| fixed 4 | 160 | 95.3 | 2,120,192 | 212.0x | −54.3% | −2.1R |
| pct 0.05 | 188 | 107.7 | 2,931,537 | 293.2x | −54.9% | −4.0R |
| **pct 0.1** | 182 | **110.2** | 3,912,804 | 391.3x | −54.3% | −3.0R |
| pct 0.15 | 172 | 89.3 | 1,147,596 | 114.8x | −54.3% | −1.2R |
| pct 0.2 | 166 | 94.3 | 2,047,887 | 204.8x | −45.7% | −2.1R |
| pct 0.3 | 137 | 68.4 | 608,340 | 60.8x | −40.3% | −3.1R |
| atr 0.25 | 188 | 107.7 | 2,931,537 | 293.2x | −54.9% | −4.0R |
| **atr 0.5** | 185 | **108.4** | 3,133,618 | 313.4x | −54.9% | −3.0R |
| atr 0.75 | 184 | 106.2 | 2,585,781 | 258.6x | −57.0% | −3.5R |
| atr 1 | 179 | 109.2 | 3,672,402 | 367.2x | −57.5% | −3.5R |
| atr 1.5 | 168 | 71.9 | 674,094 | 67.4x | −49.3% | −3.1R |

**The harness is validated:** the `none (shipped)` row reproduces Run 6's baseline exactly —
188 trades / 107.7R / $2,931,537 / 293.2x / −54.9%.

## Read sumR, NOT the x-multiple

The `x` column is ragged and non-monotonic (fixed: 387 → 338 → 195 → 114 → **212**; pct: 391 → 115
→ **205** → 61; atr: 313 → 259 → **367** → 67). That bouncing is **compounding amplifying which
individual trades land either side of the line** — a +2.5R difference in the raw edge becomes a
+100x difference in the final balance because an early trade's outcome multiplies everything after
it. **The 391x must never be quoted as the expected gain.** sumR is the honest column.

In sumR the picture is clean and, critically, the **same in all three definitions**:

| tightness | fixed $ | % of price | ×ATR |
|---|---|---|---|
| **light** (blocks 3–6 trades) | **+2.7R** | **+2.5R** | **+0.7R** |
| medium | −12.4R | −18.4R | −1.5R |
| heavy | −18.2R | −39.3R | −35.8R |

Three unrelated ways of measuring "too tight" agreeing on both the sign and the shape is what makes
this a finding rather than a fluke. It passes the curve-fit test.

## The per-year table is the proof

```
         guard    2018    2019    2020    2021    2022    2023    2024    2025    2026
none (shipped)    -1.8     0.7    22.2     4.6    -4.0    20.5    19.1    31.5    15.1
     fixed 1.5    -0.8     1.7    21.8     4.6    -3.0    20.5    19.1    31.5    15.1
       pct 0.1    -0.8     0.7    21.8     4.6    -3.0    21.4    19.1    31.5    15.1
       atr 0.5    -1.8     0.7    21.8     4.6    -3.0    20.5    19.1    31.5    15.1
--- everything below here eats winners ---
     fixed 2.5    -0.8    -1.2    21.7     4.6    -1.2     6.6    19.1    31.5    15.1
       fixed 3    -1.9    -1.4    21.7     4.6    -2.1     3.1    19.1    31.5    15.1
      pct 0.15    -0.8    -1.2    21.7     4.6    -1.2     5.3    19.1    26.8    15.1
       pct 0.3    -0.9    -1.1    19.3     4.1    -3.1     6.6    -1.2    28.6    16.1
       atr 1.5    -1.8    -2.2    22.7     3.6    -3.1     6.1    -3.0    33.5    16.1
```

At the mild settings **four of the nine years are byte-identical** to the shipped bot. The rule
costs 0.4R in 2020 and everything it gains comes out of **2018 and 2022 — the two losing years**.
That is exactly the shape a safety rule should have: it removes damage, it does not manufacture
profit.

**The tell for "too tight" is the 2023 column.** It collapses 20.5R → 3.1–6.6R at `fixed 2.5/3/4`,
`pct 0.15/0.2/0.3` and `atr 1.5`. `pct 0.3` and `atr 1.5` also destroy 2024 (19.1 → −1.2 / −3.0).
Past the mild band the guard stops refusing degenerate stops and starts refusing real trades.

## Winner: `pct 0.1` — the stop must be at least 0.1% of price

$1.20 when gold is at 1,200; $3.30 when it is at 3,300. It scales itself, needs no new state, and
is one line in Pine. It blocks 6 of 188 trades, scores **+2.5R**, and **it does block the
2023-07-27 trade** — the single trade in eight years that realised 1.98R against a 1R risk (a $1.83
stop against a bar that travelled $11; 0.1% of 1967 = $1.97, so it is refused). `fixed 1.5` scores
marginally higher (+2.7R) but does NOT block that trade ($1.83 > $1.50), and a flat dollar floor is
the wrong shape for an instrument that tripled.

`atr 0.5` is the most theoretically correct definition and is also positive (+0.7R), but it too
misses 2023-07-27 and it needs ATR state on both sides of the parity boundary. Keep it as the
fallback if `pct` ever misbehaves at a different price regime.

## Verdict

1. **Adopt the guard at `pct 0.1`** — but adopt it as a **SAFETY rule, not a profit rule.** +2.5R
   out of 107.7R over eight years is inside the noise. The reason to ship it is that it closes the
   `## The exit ladder` ⚠ hazard: a stop narrower than a typical bar means `exec_risk_pct` is no
   longer the real risk, and the realised loss is unbounded. The measured edge being mildly
   positive means the protection is **free**, which is the whole argument.
2. **Do NOT optimise the threshold upward.** The mild band is the finding; the higher numbers are
   the rule breaking. Anything above ~0.1% / $1.50 / 0.5×ATR is refusing real trades.
3. **This does not fix drawdown.** −54.9% → −54.3%. Run 6's verdict stands unchanged: drawdown is a
   position-size decision. This guard removes a tail hazard, not the losing streak.
4. **Run 6's verdict item 3 is SUPERSEDED by this run.** Its "293x → 338x" was row-filtering, not a
   replay, and it overstated the gain by an order of magnitude. The direction was right; the size
   was not.

## What adoption requires (the standing rule)

`exec_min_stop_pct` (default 0.1) in `config.py` **and** in `indicators/mpc_strategy.pine` **and**
`indicators/mpc_strategy_export.pine` (new `cfg_*` column) **and** `compare_strategy.py`
(`_TOGGLE_COLS`), in ONE commit, with `compare_strategy.py` re-run green on a fresh export. Note
`mpc_bleg` inherits `_place_entries` — decide explicitly whether the B-LEG's band-origin stop wants
the same floor before shipping.

## What was NOT measured

- ~~The guard interacting with a different `exec_sl_level`. All 17 runs are at 0.886. Run 5's
  finding that 0.786 scores 59.3R vs 33.6R *if the hazard were fixed* is the obvious follow-up —
  **re-run Run 5's `exec_sl_level` sweep with `pct 0.1` installed** and see whether the shallower
  stops become adoptable. That is now the highest-value open item on this bot.~~
  **DONE — see Run 11 (2026-07-29). The answer is no: 0.786 scores 105.2R unguarded (BELOW the
  shipped 0.886) and 49.0R with the guard on.** Run 5's 59.3R did not survive the full history.
  Run 11 also found the guard is **not** a universal safety floor — at 0.702 a −2.74R trade
  survives both `pct 0.10` and `pct 0.15`, and at 0.618 a −4.53R trade survives. It closes 0.886's
  one hazard trade; it does not license a tighter level.
- Tick-mode fills. Every number here is bar mode (zero costs), like every other run in this file.
- Whether the six blocked setups would have been better taken at a WIDER stop rather than skipped
  entirely. Refusing the trade is the conservative choice; re-anchoring the stop is a different
  rule and was not tested.

---

# Run 8 — 2026-07-28 — the runner's give-back. One winner out of ~50 candidates.

**The question, Aaron's words:** *"the runner hands too much back at the turn."*
**The answer: he was right, and there is exactly one fix that works.** The plain structure trail
PARKS the stop at the last confirmed swing and leaves it there. That swing is a **lagging** anchor,
so in a strong leg the gap between it and the high IS the give-back. Measured over 164 trades: the
bot banked **27.5% of the total profit it ever showed open**, and on the 78 trades that ran ≥$10 of
gold it captured $2,283 of the $5,300 they moved — **57% handed back**.

**ADOPTED: `exec_runner_trail = "Structure + % ratchet"`, `exec_trail_pct = 1.0`.** Same swing
anchor, but the stop then climbs one %-of-price step per step of favourable move instead of sitting
still while price runs away. Shipped as the default in all four strategy Pine files and both Python
bots on 2026-07-28.

## How it was measured

Window **2020-01-01 → 2026-07-27** (155,071 M15 XAUUSD bars), `exec_sl_level="0.886"`, structure
trail, `fill_model="bar"`. **164 trades in every row** — these are exit levers, so entries never
move.

⚠ **The sweep ran at `exec_tp1_pct = exec_tp2_pct = 1`, not the shipped 0/0** (caught 2026-07-28,
after the fact). Every A/B below is apples-to-apples so **no ranking changes**, but the absolute
figures are one config off the shipped bot. **The true 0/0 baseline on this window is 110.65R**; the
1%+1% rungs cost 1.4R. Quote 110.65R as "the current bot", never 109.3R.

Note this is a SHORTER window than Runs 1–7 (2020+, 164 trades — not the 2018+ 187/188-trade
corpus), so R totals here are not directly comparable to theirs. Within this file, compare Run 8 and
Run 9 to each other and to 109.3R/110.65R only.

## Result 1 — the winner

| | order-free edge | net | run actually banked | max DD |
|---|---|---|---|---|
| Structure (swing) — the old default | 107.6R | $2.82M | **43%** | 54.7% |
| **Structure + 1% ratchet** — shipped | **109.3R** | $3.81M | **53%** | **54.7%** |

**Read this honestly: the EDGE is unchanged.** +1.7R over 164 trades is noise, and the neighbouring
steps bounce either side of it (1.5% → 106.3R, 2.5% → 110.4R) — the signature of randomness, not an
optimum. **Do not treat 1.0 as a tuned value; treat it as the middle of a flat region.**

What IS real is the 10-point jump in how much of each run survives to the close, and it costs
nothing: **percentage drawdown is identical — 54.7%, on the same day.** The bigger DOLLAR drawdown
in an early write-up was a compounding artifact of a larger account, not a risk increase. This is
the same trap Run 7 flagged in its `x`-multiple column; the same discipline applies.

**Only 11 exits change at all.** 8 better (+13.2R), 3 worse (−11.5R), and ONE trade (2025-10-21,
+25.23R → +16.27R) is almost the entire downside. A change this narrow is not a new strategy — it is
a targeted repair to the trades that were leaking.

**Never looser than what it replaced.** The ratchet falls back to the bare swing anchor until the
move is one full step past it, so it is only ever equal or tighter than the plain structure trail.
That is pinned by a unit test (`test_swing_ratchet_is_never_looser_than_the_plain_structure_trail`)
and is why adopting it cannot re-open Run 3's stop-timing conclusions.

## Result 2 — why PERCENT and not dollars

Gold ran **1,500 → 3,400** across the window, so no fixed $ step means the same thing at both ends:
$20 is a 1.3% trail at 1,500 and a 0.6% trail at 3,400. The dollar version of the identical
mechanism tops out at **100.4R against the percent version's 109.3R**, and as the step widens it
only ever climbs back toward the plain structure trail it was meant to beat. **Do not "simplify" it
back to a $ step** — that is the same reasoning Run 7 used to pick `pct 0.1` over `fixed 1.5`.

## Result 3 — everything else lost. ~50 variants, four families, all negative.

| family | variants tested | best result | cost vs baseline |
|---|---|---|---|
| tighten the trail — fixed step $2–$40 | 7 | — | **60–90% of net** |
| tighten the trail — chandelier 2–8×ATR(14) | 4 | — | 60–90% of net |
| tighten the trail — % trail 0.5–2.5% | 4 | — | 60–90% of net |
| tighten the trail — giveback cap 25–50% | 6 | — | 60–90% of net |
| bank at the TP rungs (25/25, 33/33, 50/0) | 3 | — | ~60% of net |
| "stay loose, then clamp once it's a monster" (>3R/5R/8R/15R → tight trail) | 8 | — | 20–45% of net |
| hard take-profit ceiling | 3 | 40R = **byte-identical** to no target | 15R → 86.4R |
| exit on an opposing RSI divergence past TP2 | 4 | — | **77% of net** |

Three of these deserve their own note, because each fails for a *different* reason and each looks
reasonable before it is run:

- **The hard TP ceiling has no useful middle.** 40R never fires — no trade in 6.6 years reached it,
  so the row is byte-identical to no target at all. 15R fires and costs a fifth of the edge. The 25R
  row looks best on the table and is **three lucky trades** — only 3 of 164 ever reached a 25R peak.
  This is the same shape Run 9 finds in the extension fibs, arrived at independently.
- **The RSI-divergence exit is starved of signal.** Only 18 of 164 trades ever print an opposing
  divergence past TP2, **the six biggest give-back trades print ZERO**, and where it does fire it
  fires 2–4 times — so a live bot can only ever act on the earliest one, which is the worst one.
  This is the "use an indicator the bot doesn't currently read" idea Run 6 left open. It is now
  closed for RSI divergence specifically.
- **Every tightening family reproduces Run 6's Finding 2 in a new costume.** Winners and losers are
  indistinguishable while live, so a rule that protects the average trade taxes the tail — and the
  tail is the strategy. The ratchet wins precisely because it never tightens *relative to the
  structure trail*; it only stops the stop from falling behind.

## Verdict

1. **Adopted, as a give-back repair — not as an edge improvement.** The honest claim is "53% of each
   run banked instead of 43%, at identical percentage drawdown." The claim "+1.7R" is noise and must
   not be quoted as the reason.
2. **Do not tune `exec_trail_pct`.** The region is flat and the neighbours straddle the winner.
3. **The runner-tightening question is now closed** the same way Run 6 closed early cuts. Four
   families, ~30 variants, every one negative. Reopen only with a mechanism that does not tighten
   against the structure trail.

## What adoption cost, and the standing rule it triggered

One commit across `config.py`, all four Pine files, and `compare_strategy.py` — plus the export
plumbing, which is the part that is easy to forget: **`cfg_exitmode`'s trail digit went 2-way →
3-way and `cfg_trail_pct` was added.** Without both, the comparator silently decodes a ratcheted
Pine as "Structure (swing)" and reports pure drift as a parity bug.

⚠ **The A+ parity gate is STALE as of this run.** The last green `compare_strategy.py` was
2026-07-27, which predates the ratchet. **Re-run it on a fresh export at the shipped
`exec_tp1_pct = exec_tp2_pct = 0`** before any number from this build is trusted. `compare_bleg.py`
is stale for the same reason.

Harness: `scratchpad/trail_sweep.py` + `ext_*.py`, subclassing `Execution` so no repo file was
modified. Throwaway, not committed.

---

# Run 9 — 2026-07-28 — extension fibs. Aaron's own hand rule, and it loses in all three forms.

**The question, Aaron's words:** *"I don't ever have a TP3 on my runners... after structure is
broken it's kinda like a no man's land. What about using extension fibs? If I was manually trading
I'd bank some at the 0.0, some at the −0.272, some at −0.414, and if it gets all the way to −0.618
I take everything off the table. Can you run a test and see if that would extend some of my
winners?"*

**The answer: no, in every form tested — and the reason is the shape of the trade book, not the
choice of levels.** This is the most natural-looking idea in the file and the one Aaron actually
trades by hand, so it gets a full run rather than a footnote.

**Nothing adopted. Nothing to build.**

## How it was measured

Same corpus and caveats as Run 8: 155,071 M15 bars, 2020-01-01 → 2026-07-27, `exec_sl_level=0.886`,
164 trades in every row, `fill_model="bar"`, baseline 109.3R at 1%/1% rungs (**110.65R at the
shipped 0/0**).

Extension prices are direction-agnostic: `ext(x) = p7 + (p7 − p10) * x`, where `p7` is the leg's 0.0
fib and `p10` its 1.0. **The leg anchors are frozen at ORDER PLACEMENT**, not at fill — matching how
TP1/TP2 are already frozen, so a rung cannot drift with a later structure update.

Three independent designs, deliberately, so the answer does not depend on one framing:

## Design 1 — as TAKE-PROFIT rungs, at Aaron's levels

| ladder | sumR | vs base |
|---|---|---|
| **BASE — runner only (shipped)** | **109.3** | — |
| 50% at −0.618 only | 92.4 | −16.9 |
| 10/10/10/10, 60% runs on | 92.3 | −17.0 |
| 50% at −0.414 only | 91.1 | −18.2 |
| 50% at −0.272 only | 89.5 | −19.8 |
| 15/15/15/15, 40% runs on | 83.9 | −25.4 |
| 20/20/20/0, 40% runs on | 82.1 | −27.2 |
| 50% at 0.0 only | 79.3 | −30.0 |
| 0/0/0/100 — all off at −0.618 (**Aaron's stated rule**) | 77.7 | −31.6 |
| 0/25/25/50 — skip the 0.0 | 75.7 | −33.6 |
| 25/25/25/0 | 75.4 | −33.9 |
| 10/20/30/40 | 73.2 | −36.1 |
| 20/20/20/40 | 70.9 | −38.4 |
| **even 25/25/25/25** | **69.1** | **−40.2** |

**All 14 allocations lose, and the ranking is perfectly monotonic in how much is banked.** That is
the same shape as Run 1's TP-split grid, re-measured on a different rung set: the limit of "bank
less" is the shipped runner, and there is no interior optimum. Aaron's exact hand rule scores 77.7R
against 109.3R.

## Design 2 — as a STOP FLOOR (bank nothing, just ratchet the stop up the extension ladder)

This is the steelman: keep 100% of the position, but once price trades through a rung, refuse to
give that rung back.

| variant | sumR | vs base |
|---|---|---|
| **BASE (no extension floor)** | **109.3** | — |
| floor one rung behind | 56.1 | −53.2 |
| floor two rungs behind | 51.9 | −57.4 |
| floor at the tagged rung | 49.3 | −60.0 |

**Worse than the take-profit version — roughly half the strategy.** The cause is specific and worth
recording: **a fib level is a FIXED price and does not breathe.** The structure trail moves with the
market and survives an ordinary retrace; a horizontal line does not. The 23.5R trade became 10.5R,
cut on a pullback **six legs before it actually finished.** Adding lag does not help — it makes it
worse, because a floor two rungs behind is simply a looser version of the same rigid line.

## Design 3 — as DEEP rungs (Aaron's follow-up: −1 / −2 / −3 / −4 / −6)

Aaron's own correction after seeing Design 1: *"if we ever get to −6, take all the money off the
table. If we ever get to −4, take at least 50% off. If we get to −1, take like 10%."* Design 1 only
tested shallow rungs, so this was a genuine gap in the test, not a re-run.

| variant | sumR | vs base |
|---|---|---|
| −6 take 100% | **112.2** | +2.9 |
| −6 take 50% | 109.6 | +0.3 |
| −6 take 25% | 109.4 | +0.1 |
| **BASE runner only** | **109.3** | — |
| −4 take 25% | 107.9 | −1.4 |
| −4 take 50% | 106.5 | −2.8 |
| **AARON −1:10% / −4:50% / −6:rest** | **106.3** | **−3.0** |
| −4 take 100% | 106.0 | −3.3 |
| −3 take 25% | 105.6 | −3.7 |
| −2:25 / −4:25 / −6:50 | 104.5 | −4.8 |
| −1:10 / −2:20 / −4:30 / −6:40 | 102.6 | −6.7 |
| −1 take 25% | 102.4 | −6.9 |
| −1 take 50% | 95.5 | −13.8 |
| *(22 variants total; the rest fall between)* | | |

**Far better than shallow, and still not an improvement.** The three rows that beat the baseline all
sit at **−6, and exactly ONE trade in 6.6 years ever reached −6.** `−6 take 100%` scores 112.2R,
which is **+1.55R over the true 110.65R baseline, from a single 2020 trade.** That is a description
of July 2020, not a rule. Aaron's ladder scores 106.3R.

## The pattern — why there is no ceiling to find, at any depth

**Rule cost tracks how OFTEN the rule fires.** Nothing else.

| depth | trades that ever reach it | what a rule there costs |
|---|---|---|
| −1 | 8 | 7–14R |
| −4 | 2 | 1–3R |
| −6 | 1 | ~0 |

Every candidate converges on the baseline **from below** as it stops doing anything. **There is no
depth at which banking becomes profitable — there is only a depth at which it becomes harmless.**
This is the general answer to "surely some ceiling works", and it applies to hard R targets (Run 8)
exactly as it applies to fib extensions.

## The shape of the book — the real reason, in one table

Of 164 trades:

| reached | trades | % |
|---|---|---|
| the 0.0 fib | **29** | 18% |
| −0.272 | 23 | 14% |
| −0.414 | 18 | 11% |
| **−0.618** | **11** | **7%** |
| −1 | 8 | 5% |
| −2 | 2 | 1% |
| −4 | 2 | 1% |
| −6 | **1** | 0.6% |

**Those 11 trades past −0.618 make 106R of the 109R total.** The two biggest ran to **−6.738** and
**−4.770**, and the swing ratchet paid them out at −5.679 and −3.692. A fixed ceiling is applied to
every trade, so it necessarily caps exactly the handful that carry the strategy.

Aaron's own reference trade (2026-06-17) is not in this list — it did not clear 0.0. The trade he
was looking at that turned "right before the −0.618" is the 2025-10-21 trade, which ran to −0.630
and exited at −0.302. His read of the chart was correct; it just does not generalise, because the
book contains two trades that ran 7–10x further and they are where the money is.

## The one real leak, and why it is still not worth plugging

**8 trades run past 0.0 and hand the ENTIRE extension back**, exiting at the 0.382 floor. That leak
is real and Aaron's instinct was aimed at it. It is worth **5.7R**. The cheapest rule found that
plugs it costs **17R**, because the same rule necessarily touches the trades that keep going. This
is the honest version of "why not just protect the ones that round-trip": you can, and it costs 3x
what it saves.

## Verdict

1. **Do not build extension-fib exits, in any of the three forms.** 40 replays, three independent
   designs, every one negative against the shipped runner.
2. **The manual method is not wrong — it is a different instrument.** Trading by hand, Aaron sees
   the leg and can judge which run is a monster. A fixed rule cannot, so it charges every trade for
   the protection and only 11 of 164 can pay.
3. **This closes the "no man's land past 0.0" question.** The runner already has the right answer
   there: a trail that moves with structure, which is the only mechanism tested that does not cap
   the tail.

## What was NOT measured

- **Conditional rungs** — e.g. bank at −0.618 only when the trade took longer than N bars, or only
  in a RANGING regime. Run 6 swept ten single-bucket entry filters and found nothing, and at n=164 a
  two-way conditional sweep will find something that looks good and is noise. Deliberately skipped.
- **Tick-mode fills.** Bar mode, zero costs, like every run in this file. Extension rungs are limit
  orders at fixed prices, so tick mode would if anything treat them slightly WORSE than the market
  exits they replace.

Harness: `scratchpad/ext_fibs.py` (rungs), `ext_floor.py` (stop floor), `ext_deep.py` (deep rungs),
`ext_where.py` (per-trade depth diagnostic) — all subclassing `Execution`, no repo file modified.
Throwaway, not committed.

---

# Run 10 — 2026-07-29 — cut the trade by the SHAPE of its path. Two of three ideas die.

**The question, Aaron's words:** *"how many losers went never into profit and just trickled towards
the stop loss? How many went into profit at least two times before they hit stop? … find a number,
doesn't have to be two — the most amount of losers whose price went into profit, then back into
loss, and back into profit, up to n times. Use that as a baseline to say, when price is acting like
this it typically leads to a loss, so cut those trades at hopefully breakeven."*

**The answer: the pattern is not a loss signal — it is a mild WIN signal.** Trades that chop in and
out of profit lose **18–30%** of the time against a **32% base rate**, and that number is flat at
every threshold and every repeat count. Every cut rule built on it loses money.

A second idea derived from the same data DOES work, mildly: cutting a trade that **stalls** (never
clears +0.15R). And Aaron's own follow-up — cut when price retraces to a deep fib — **fails, with
0.886 mathematically unable to fire at all.**

**Nothing adopted.**

## How it was measured

Window **2018-09-13 → 2026-07-29** (185,783 M15 XAUUSD bars — the broker's whole measured intraday
history), the shipped config: `exec_sl_level="0.886"`, TP rungs 0/0, `"Structure + % ratchet"` at
1.0%, risk 10%, `fill_model="bar"`. **Baseline 188 trades, 109.5R, maxDD 54.9%, 384x, 59W/61L/68S**
(breakeven band ±0.15R). This is the same corpus as
`backtest/archive/2026-07-29_xauusd_15m_full_history/`.

Two artefacts, both from monkey-patching the shipped `Execution` on the INSTANCE — no repo file was
modified:

- **A per-bar R path** per trade: the bar's favourable extreme, adverse extreme, CLOSE (the price a
  market exit would actually get) and the exit-ladder STAGE. 10,767 rows over 188 trades.
- **A per-bar OHLC path + the frozen fib ladder** (0.618/0.702/0.786/0.886) snapshotted where the
  order is PLACED, which is where `pend.sl` is frozen.

**Both captures are self-validating, and that matters more than usual here.** The R path's
`max(fav_r)` reproduces every trade's independently-computed `mfe_r` to **7.4e-6**. The fib
capture's 0.886 level equals the trade's actual stop to **$0.000000** — which it must, because
`exec_sl_level="0.886"` with `exec_sl_buf_tk=0`. A capture that did not reconcile would have made
every number below meaningless.

**Convention, matching `_advance_stage` and Run 6:** a counter read at bar N's close is acted on at
that close (a market exit) or is live from bar N+1 (a stop). Checking the trigger bar's own
extremes for a stop would let a rule act on a move it only learned about at the close.

## Part A — the bucket counts Aaron asked for

How many of the **61 losers** went into profit 0 / 1 / 2+ times before dying? A "poke" is counted
once and only re-counted after price returns to the entry price or worse (hysteresis — without it a
wobble around the line reads as ten separate excursions).

| "in profit" = the bar's favourable extreme reached | never | once | 2+ times |
|---|---|---|---|
| **+0.10R** (barely above entry) | **1** | 13 | **47** |
| **+0.25R** (the repo's scratch band) | 13 | 21 | 27 |
| **+0.50R** | 29 | 20 | 12 |

**The "never in profit, just trickled to the stop" trade is ONE trade in 61** — 2025-12-15, which
showed +0.09R. That reconciles exactly with the archive's never-worked column (2025 = 1, every other
year 0) and with Run 6's min-MFE of +0.09R, from a third independent direction.

The 13 "never" trades at +0.25R are the real trickle group: they topped out at 0.09–0.24R and **all
13 died at exactly −1.00R**, worth **−13.0R** together. Distribution of the multi-pokers is long-
tailed — one trade poked 20 times, one 15, one 14.

## Part B — the poke cut. 70 combos, every one negative.

7 thresholds × 5 poke counts × {cut at any stage, cut only while at full risk}. Fire at the close of
the bar the counter reaches N.

| T | N | fires on | losers caught | winners killed | R saved on losers | R lost on winners | net |
|---|---|---|---|---|---|---|---|
| 0.10 | 2 | 165 | 47 | 57 | **+47.7** | **−127.7** | **−70.5R** |
| 0.25 | 2 | 126 | 27 | 51 | +29.7 | −89.9 | −46.2R |
| 0.25 | 3 | 48 | 11 | 19 | +15.3 | −47.4 | −28.2R |
| 0.30 | 5 | 17 | 5 | 7 | +5.5 | −25.6 | −18.6R |
| 0.50 | 3 | 17 | 4 | 7 | +6.8 | −27.7 | −18.4R |

**The separation table is what kills it, and it is the finding worth keeping.** Of every trade that
ever reaches N pokes, what did it turn out to be?

| poke threshold | N | reached it | loss | scratch | win | **% loss** | their R if left alone |
|---|---|---|---|---|---|---|---|
| +0.10R | 2 | 165 | 47 | 61 | 57 | **28%** | +119.9 |
| +0.10R | 4 | 69 | 16 | 24 | 29 | **23%** | +75.7 |
| +0.20R | 3 | 68 | 14 | 24 | 30 | **21%** | +82.7 |
| +0.25R | 2 | 126 | 27 | 48 | 51 | **21%** | +106.5 |
| +0.25R | 5 | 22 | 5 | 6 | 11 | **23%** | +29.9 |
| +0.50R | 2 | 65 | 12 | 22 | 31 | **18%** | +90.5 |

**Base rate is 32%** (61/188). Every row is BELOW it, and the column does not rise as N rises — if
the pattern were a loss signal it would. Every one of these populations is net PROFITABLE if left
alone. **There is no number to find. The requested rule does not exist in this data.**

**Why an earlier read of this looked worse than it is.** A first pass compared raw poke counts
between winners and losers (86% of winners poke 2+ times vs 44% of losers) and called that the
refutation. That comparison is UNFAIR — winners are held a median 75 bars against a loser's 10, so
they have seven times as many bars in which to poke. The separation table above is the honest form
of the test, and it happens to reach the same conclusion by a valid route.

**Matched against the alternative.** The aggressive settings DO cut drawdown, but only by amputating
the book, and turning the risk dial down buys the same drawdown while keeping all 109.5R:

| poke rule | sumR | maxDD | final | plain risk % at the SAME drawdown | sumR | final |
|---|---|---|---|---|---|---|
| T=0.10 N=2 | 39.0 | 27.4% | 24x | 4.2% | **109.5** | 29x |
| T=0.25 N=2 | 63.3 | 29.5% | 69x | 4.6% | **109.5** | 37x |
| T=0.25 N=3 | 81.3 | 41.6% | 72x | 6.9% | **109.5** | 120x |
| T=0.30 N=3 | 83.0 | 45.9% | 82x | 7.8% | **109.5** | 178x |

The `final` column bounces both ways — Run 7's ragged-multiple warning applies exactly. Read sumR.

## Part C — the STALL cut. The one thing that works, and it does not touch drawdown.

Different from Run 6's time stops, which keyed on the trade being BELOW 0R at bar N. This keys on
failure to make PROGRESS: a trade can be fractionally green and still be going nowhere.

**The diagnostic that picks the threshold** — how many bars until the trade first shows +T R:

| | n | never | median | p90 | max |
|---|---|---|---|---|---|
| **+0.15R** wins | 59 | 0 | 0 | 0 | **18** |
| **+0.15R** losses | 61 | 5 | 0 | 1 | 41 |
| **+0.25R** wins | 59 | 0 | 0 | 10 | **56** |
| **+0.25R** losses | 61 | 13 | 0 | 7 | 42 |

**+0.15R is the only level where the two populations separate.** No winner ever takes more than 18
bars to clear it; losers stretch to 41. At +0.25R a winner can take 56 bars, so any finite cut-off
catches winners — and the grid confirms it (T=0.25 loses 20–28R at every N).

**REAL-REPLAYED, not screened** (6 variants, the rule inside the strategy so entries may move). The
control reproduced the baseline exactly — 188 trades / 109.5R / 54.9% / 384x:

| variant | trades | sumR | ΔR | maxDD | final | cut |
|---|---|---|---|---|---|---|
| **CONTROL** | 188 | **109.5** | — | **54.9%** | 384x | 0 |
| **T=0.15 N=3** | 188 | **114.3** | **+4.8** | **54.9%** | 662x | 15 |
| T=0.15 N=5 | 188 | 113.0 | +3.6 | 54.9% | 578x | 11 |
| T=0.15 N=10 | 188 | 111.8 | +2.4 | 54.9% | 501x | 7 |
| T=0.15 N=20 | 188 | 111.0 | +1.5 | 54.9% | 451x | 2 |
| T=0.20 N=10 | 188 | 112.6 | +3.2 | **56.6%** | 572x | 15 |

The T=0.15 family is **positive at every N and decays smoothly toward zero** as the rule stops
firing — the shape Run 7 set as the pass mark for a real rule rather than a curve fit. The screen
predicted +5.0R and the real replay delivered +4.8R, so the offline approximation held.

**But maxDD is 54.9% in every T=0.15 row — identical to baseline, to one decimal.** And +4.8R out of
109.5R is noise-level, the same standing as Run 7's +2.5R. T=0.20 makes drawdown WORSE. So this is a
small free improvement that does **not** answer the question it was built to answer.

## Part D — Aaron's fib-level cut. 0.886 cannot fire; 0.786 loses 27R.

*"Trades that went in and out of entry level more than N times and then retraced back to at least
0.786 — or 0.886 — go ahead and cut."*

**0.886 fires on 0 of 188 trades, by construction.** `exec_sl_level="0.886"` with
`exec_sl_buf_tk=0` means the 0.886 fib **IS** the stop, to the cent. There is no room between the
entry and it for a cut to live in. Verified rather than argued: the captured level equals the actual
stop on every trade, worst gap $0.000000.

**0.786** sits strictly between entry and stop on 161/188 trades. Cut fires as a stop at the level
(or the open, if the bar gapped past), only while the trade is still at full risk:

| cut level | poke T | N | fires | losers caught | winners killed | R saved | R lost | net | maxDD |
|---|---|---|---|---|---|---|---|---|---|
| **0.786** | any | 0 | 48 | 35 | 4 | **+12.6** | **−33.6** | **−27.0R** | 52.3% |
| 0.786 | 0.10 | 2 | 37 | 26 | 4 | +8.7 | −33.6 | −29.5R | 55.0% |
| 0.786 | 0.10 | 4 | 15 | 12 | 1 | +4.2 | −1.6 | +1.4R | 56.6% |
| **0.702** | any | 0 | 58 | 29 | 17 | +17.2 | −59.3 | **−47.3R** | **62.4%** |
| 0.702 | 0.02 | 3 | 36 | 19 | 11 | +11.0 | −49.5 | −41.2R | 60.7% |

**Four winners.** The rule rescues 35 losers for +12.6R and kills four trades worth −33.6R — nearly
three times as much. 0.702 is worse and makes drawdown worse (62.4%). The poke filter does not
rescue either: as N rises the rule fires less and creeps back to baseline (+1.4R at N=4 is noise).

**This is Run 9's pattern again, arrived at from the opposite side.** Run 9: *"there is no depth at
which banking becomes profitable — only a depth at which it becomes harmless."* Here: there is no
depth at which cutting becomes profitable, only a depth at which it stops firing.

**The distinction that makes this different from Run 5, and worth writing down.** Cutting at 0.786
MID-TRADE takes a smaller loss on a position already sized off the 0.886 stop. Setting the stop to
0.786 AT ENTRY is a different thing entirely — `qty = risk / dist`, so a tighter stop buys a BIGGER
position, the loss stays exactly 1R, and the winners are worth more R. That is the mechanism behind
Run 5's +26R claim, and Run 11 tests it properly.

## Verdict

1. **The in-and-out-of-profit rule does not exist.** The pattern is a mild WIN signal (18–30% loss
   rate vs a 32% base rate, flat across every parameter). Do not re-open without a signal that is
   not derived from the trade's own price path — Run 6's Finding 2 and this run now agree from two
   independent measurements.
2. **The fib-level cut is dead.** 0.886 is arithmetically incapable of firing; 0.786 costs 27R.
3. **The stall cut (no +0.15R by bar 3) is real, small, and free** — +4.8R real-replayed, same
   drawdown, positive at every N. It is a candidate on the same footing as Run 7's guard: ship it
   for tidiness, never for the money. **Not adopted** — it would be new inputs in `config.py` AND
   both Pine files, and +4.8R does not justify that on its own. Bundle it with the Run 11 guard
   commit or leave it.
4. **None of this touches drawdown.** Best figure in the whole run is 54.9% — unchanged.

## What was NOT measured

- **Tick-mode fills.** Bar mode, zero costs, like every run in this file. Parts B and D exit at
  market or at a stop, so tick mode would treat them slightly WORSE than the baseline's trailed
  exits.
- **The stall cut combined with the Run 7 guard.** Both are mild positives that fire on different
  trades; whether they compose or overlap is unrun.
- **Combinations of poke count with anything else** (regime, session, stop size). Deliberately
  skipped for Run 6's stated reason: at n=188 a two-way sweep will find something that looks good
  and is noise. The separation table makes a conditional version unpromising anyway — there is no
  base-rate lift to condition ON.

Harness: `scratchpad/poke_capture.py` + `poke_grid.py` (Parts A/B), `stall_grid.py` +
`stall_replay.py` (Part C), `fib_cut_capture.py` + `fib_cut_grid.py` (Part D). All patch or subclass
`Execution`; no repo file modified. Throwaway, not committed.

---

# Run 11 — 2026-07-29 — the stop-level sweep, guarded. 0.886 is the right level.

**The question:** the one this file has called its highest-value open item since Run 7 (2026-07-27).
Run 5 measured `exec_sl_level="0.786"` at **59.3R vs 33.6R** shipped, but 8 of its 108 trades rested
a stop under \$2 — Run 4's account-detonating hazard, live. Run 7 then measured a guard that closes
it (`pct 0.1`: the stop must be ≥ 0.1% of the entry price) and found it essentially free. Nobody had
put the two together. Run 7's closing line: *"re-run Run 5's `exec_sl_level` sweep with `pct 0.1`
installed. That is now the highest-value open item on this bot."*

**The answer: no shallower stop is adoptable. 0.886 — what Aaron already trades — is correct.**
Run 5's +26R prize was a short-window artifact and does not survive the full history.

**The one thing this run DOES confirm for adoption: `0.886 + pct 0.1`.** It reproduces Run 7's
result independently on a fresh full-history replay that includes the swing ratchet Run 7 predated.

## How it was measured

14 full replays, **2018-09-13 → 2026-07-29** (185,783 M15 bars), shipped config apart from the two
dials. The guard is a subclass that lets the REAL `_place_entries` build the order and then DROPS it
if `abs(edge - sl)` is inside the floor — so arming, vetoes and every other rule behave exactly as
shipped and **only the placement decision changes.** No repo file was modified.

**Harness validated two ways.** `0.886 / no guard` reproduces the shipped run to the decimal (188
trades, 109.5R, 54.9%, 384x, worst trade −1.98R, tightest stop \$1.03). `0.886 / pct 0.10`
reproduces Run 7's `pct 0.1` row (182 trades, +2.5R, 54.9% → 54.3%, and it blocks the −1.98R trade)
— Run 7 measured that on a pre-ratchet bot, so agreeing here is a genuine independent confirmation.

## The result

| SL fib | guard | trades | sumR | maxDD | final | W/L/S | worst trade | tightest stop |
|---|---|---|---|---|---|---|---|---|
| 1.0 | — | 188 | 75.7 | 47.4% | 181x | 64/42/82 | −1.00 | \$2.21 |
| 1.0 | 0.10% | 188 | 75.7 | 47.4% | 181x | 64/42/82 | −1.00 | \$2.21 |
| **0.886 (shipped)** | — | 188 | **109.5** | 54.9% | 384x | 59/61/68 | **−1.98** | \$1.03 |
| **0.886** | **0.10%** | 182 | **112.0** | **54.3%** | **512x** | 56/58/68 | **−1.00** | \$1.43 |
| 0.786 | — | 170 | 105.2 | 60.2% | 171x | 51/61/58 | −1.88 | \$0.65 |
| 0.786 | 0.05% | 169 | 102.8 | 60.2% | 138x | 50/61/58 | −1.88 | \$0.65 |
| 0.786 | 0.10% | 160 | 49.0 | 55.8% | 23x | 45/56/59 | −1.37 | \$1.32 |
| 0.786 | 0.15% | 152 | 36.8 | 70.3% | 10x | 42/52/58 | −1.37 | \$2.06 |
| 0.702 | — | 150 | 18.1 | 82.8% | 1x | 36/73/41 | −2.74 | \$0.87 |
| 0.702 | 0.10% | 138 | 9.7 | 83.9% | 0x | 28/68/42 | −2.74 | \$1.12 |
| 0.702 | 0.15% | 106 | 10.4 | 75.3% | 1x | 18/52/36 | −2.74 | \$2.11 |
| 0.618 | — | 118 | **223.8** | **97.6%** | 3x | 23/81/14 | **−5.02** | **\$0.08** |
| 0.618 | 0.10% | 62 | 6.5 | 87.8% | 0x | 10/38/14 | −4.53 | \$1.35 |
| 0.618 | 0.15% | 42 | 15.2 | 67.5% | 1x | 7/25/10 | −4.53 | \$2.88 |

## Why 0.786 fails, and why its unguarded number is a trap too

**Unguarded it is already worse than shipped** — 105.2R vs 109.5R, with a WORSE drawdown (60.2% vs
54.9%) and the hazard fully live (tightest stop \$0.65, worst trade −1.88R). Run 5's 59.3R-vs-33.6R
was measured on the 2022+ cache (118 trades) under the old exit ladder. It does not generalise.

**And that 105.2R is concentrated in two years.** Per-year R: `+0.5 −4.6 +4.5 +8.2 +2.8 +12.3
+50.4 +5.6 +25.4` — **2024 alone is +50.4R and 2026 is +25.4R, i.e. 72% of the total.**

**The guard then turns 2024 from +50.4R into −2.9R.** That is the decisive fact in the whole run:
the trades carrying 0.786's result are precisely the ones with stops tight enough for the guard to
refuse. **You cannot separate 0.786's return from its hazard, because they are the same trades.**
Guarded it scores 49.0R; tightening the guard to 0.15% makes it 36.8R. There is no setting where
0.786 is both safe and better than 0.886.

## The guard is a hazard reducer, NOT a licence to tighten

Worth recording separately, because it is easy to assume otherwise: `pct 0.1` removes 0.886's single
worst trade (−1.98R → −1.00R), but at **0.702 a −2.74R trade survives both 0.10% and 0.15%**, and at
**0.618 a −4.53R trade survives both.** A 0.1%-of-price floor is enough to catch the tail of a
sane level; it does not make an unsafe level safe.

**0.618 is Run 4's detonation reproducing on a third independent window.** 223.8R — the highest
number anywhere in this file — at a **97.6% drawdown** for a 3x account, on an \$0.08 tightest stop.
It is the same divide-by-a-tiny-denominator artifact Runs 4 and 5 diagnosed, and it is the cleanest
available demonstration of why sumR must never be read without the drawdown beside it. Guarded, it
discards **56 of 118 setups** (118 → 62) and still holds a −4.53R trade at 87.8% — which is Run 4's
own stated test (*"if 0.618 discards most of its setups, it is not a real option"*) applied and
failed.

## Matched drawdown — the question that actually decides it

Every config dialled to the shipped bot's 54.9% drawdown, so return is compared at equal pain:

| SL fib | guard | sumR | risk % for the same 54.9% DD | final at that risk |
|---|---|---|---|---|
| **0.886** | **0.10%** | **112.0** | 10.2% | **540x** |
| 0.886 | — | 109.5 | 10.0% | 384x |
| 1.0 | — | 75.7 | 12.2% | 382x |
| 0.786 | — | 105.2 | 8.8% | 122x |
| 0.786 | 0.10% | 49.0 | 9.8% | 22x |
| 0.702 | — | 18.1 | 4.7% | 1x |
| 0.618 | — | 223.8 | 2.7% | 11x |

**`0.886 + pct 0.1` is the best config in the sweep on every honest measure** — highest sumR, lowest
drawdown of the viable rows, best matched-drawdown outcome.

**A side finding worth keeping: the stop level is nearly risk-equivalent.** `1.0` needs 12.2% risk
to reach the same 54.9% drawdown and lands at 382x, statistically the same as 0.886 at 10% (384x).
So 1.0 vs 0.886 is a smoothness preference, not an edge — which is a cleaner statement of the same
thing Run 5 was reaching for, and it means Run 4's "1.0 is the only supported value" advice cost
nothing while it stood.

## Verdict

1. **`exec_sl_level` is settled. Keep "0.886". The dropdown is retired as a tuning lever.** 0.618 /
   0.702 / 0.786 are now measured-bad on the full history, not merely unsupported-pending-a-guard.
2. **Adopt `pct 0.1` on 0.886** — as a SAFETY rule, exactly as Run 7 argued. +2.5R out of 109.5R is
   noise; the reason to ship is that it deletes the only trade in 7.9 years that lost more than the
   1R it risked, and it closes the `## The exit ladder` ⚠ hazard.
3. **This does not fix drawdown** (54.9% → 54.3%), and neither does any other row. Run 6's Finding 5
   stands after a fourth independent attempt.
4. **Run 5's `exec_sl_level` table and its +26R follow-up are SUPERSEDED.** Both are annotated in
   place.

## What adoption requires (unchanged from Run 7, plus one item)

`exec_min_stop_mode` / `exec_min_stop_val` (or a single `exec_min_stop_pct`, default 0.1) in
`config.py` **and** `mpc_strategy.pine` (which already has `execMinStopMode`/`execMinStopVal`)
**and** a new `cfg_min_stop*` column in `mpc_strategy_export.pine` **and** a `_TOGGLE_COLS` entry in
`compare_strategy.py` — ONE commit, then re-run parity. **The export column is the load-bearing
part:** today the Pine has the filter and the export cannot see it, so the moment it is switched on
in TradingView the Pine refuses setups the Python still takes and `compare_strategy.py` reports
GREEN anyway. That is the one known Pine↔Python divergence on the A+ pair and shipping the guard is
what closes it. Also decide explicitly whether `mpc_bleg` (which inherits `_place_entries`) wants
the same floor on its band-origin stop.

## What was NOT measured

- **Tick-mode fills.** Bar mode, zero costs, like every run in this file. Note a tighter stop is
  proportionally more cost-sensitive, so any tick re-run would penalise the shallow levels FURTHER —
  it can only strengthen this verdict, not weaken it.
- **`atr 0.5`, Run 7's theoretically-cleaner guard definition, at levels other than 0.886.** `pct`
  was carried forward because Run 7 picked it and it needs no new state on either side of the parity
  boundary. Given 0.786 fails at every `pct` strength, an `atr` variant is unlikely to rescue it.
- **The guard combined with Run 10's stall cut.** Both are mild positives on different trades.

Harness: `scratchpad/sl_guarded.py` — a `GuardedExecution` subclass, no repo file modified.
Throwaway, not committed.

---

# Run 12 — 2026-07-29 — the MISSED setups. "No FVG in the zone" is not lost money.

**The question (Aaron's, verbatim in intent):** the strategy logs a pile of 2-of-3 misses where the
sweep armed it, the SOS fired, price *did* retrace into the entry band — and no fair-value gap
overlapped the band, so no limit ever rested. **If I had taken those trades, how many would have won,
how many would have lost, and what would it have done to my P&L?** Window: 2020-01-01 → now.

**The answer: they are a coin flip that costs more than it pays.** Taken at the strategy's own no-gap
fallback they add **+34.0R gross**, but they displace **+21.0R** of real trades and push max drawdown
from **54.9% to 77.1%**. 40% of the gross is one January-2020 trade, and the whole verdict **flips
sign** if the counterfactual entry moves half a fib step. **Keep `exec_req_fvg = True`.**

## How it was measured

**One input changed, nothing else.** `exec_req_fvg` False is the Pine's OWN answer to "take it
without the gap" (`if not execReqFVG ... longEdge := fiboP3` — rest the limit at the 0.618 / E1 fib),
so the counterfactual is existing, parity-tested logic rather than a rule invented for the test.

Two full replays over the **same 155,186 M15 bars** (2020-01-01 → 2026-07-29), shipped config
otherwise, bar fills, warmup 1000. Trades are then paired **by entry bar**, which splits them three
ways: MATCHED (in both), NEW (only the counterfactual — the no-FVG entries), DISPLACED (a baseline
trade that no longer happens, because a new trade was holding the one position slot).

**Harness validated two ways.** The baseline reproduces the shipped figure exactly — **164 trades,
110.6R** vs the file's 110.65R — and all **147 matched trades are identical to the decimal** in both
entry price and R (drift count: 0). So every difference below is genuinely the added setups, not a
side effect.

## The baseline's own miss ledger (what the chart's orange callouts count)

| miss reason | n |
|---|---|
| No retrace (price never reached the band — the ordinary death) | 238 |
| **No FVG in zone ← this run** | **180** |
| Final hour (3-of-3, refused by the 16:00-18:00 rule) | 18 |
| Never filled (3-of-3, limit rested, price never came back) | 7 |
| Divergence / RSI veto (3-of-3) | 3 |

180 no-FVG misses over 6.6 years, and **173 of them would actually have filled** at the 0.618 — the
other 7 never traded that deep.

## The result

| | trades | sumR | win | loss | breakeven | avgWin | avgLoss | maxDD | final equity |
|---|---|---|---|---|---|---|---|---|---|
| **A — baseline (FVG required)** | 164 | **110.6** | 54 | 52 | 58 | 2.91 | −0.92 | **54.9%** | \$3.95M |
| **B — no-FVG allowed** | 320 | **123.6** | 99 | 102 | 119 | 2.11 | −0.87 | **77.1%** | \$6.52M |
| *the NEW no-FVG entries, in isolation* | 173 | **+34.0** | **50** | **54** | **69** | 1.52 | −0.82 | — | — |
| *the baseline trades they DISPLACED* | 17 | **+21.0** | 5 | 4 | 8 | 4.97 | −1.00 | — | — |

**The R arithmetic, which is the honest number** (order-free, unlike dollars):
`110.6 + 34.0 − 21.0 = 123.6R`, i.e. **+13.0R, +11.7% of the edge, for +22 points of drawdown.**

Aaron's question answered literally: of the 173, **50 won, 54 lost, 69 scratched at breakeven** —
so roughly a third each way, and the median trade is **+0.04R**. That is a coin flip, and the
breakeven third is only breakeven because the stop→BE staging rescued it.

## Why the +34R is not an edge — two independent reasons

**1. Concentration.** One trade (2020-01-02, +13.56R) is **40% of the total**, and the top 3 are
**106%** of it — without the single best trade the remaining 172 make **+20.4R**, about **0.12R
each**. Compare the shipped book's own avgR of 0.67.

**2. It is a bet on the entry PRICE, not on the setups.** The whole test rests on where a limit with
no gap to anchor it should sit. Move it and the verdict inverts:

| fallback entry level | cf trades | cf sumR | delta vs baseline | new n | new R | maxDD |
|---|---|---|---|---|---|---|
| **0.618 (E1) — the Pine's own fallback** | 320 | 123.6 | **+13.0** | 173 | +34.0 | 77.1% |
| 0.500 — shallowest legal entry | 352 | 103.9 | **−6.7** | 205 | +14.3 | 64.2% |
| 0.786 — deep entry | 290 | 52.2 | −58.5 | 138 | −35.5 | 94.3% |

Half a fib step shallower and the idea **loses** money. A result that changes sign under a
cosmetic change to an arbitrary parameter is not a finding. (**The 0.786 row is contaminated** —
with the stop at 0.886 the stop distance collapses and Run 4's degenerate-sizing hazard fires, which
is why equity ends at \$3,355. Read it as "the hazard is still live at shallow entries", not as a
−58.5R measurement.)

## The displacement, which nobody would see on a chart

17 real trades vanish because a no-FVG trade was already holding the position — including
**2025-10-20 short, +16.49R**, which is single-handedly why 2025 goes **+22.4R → +1.6R**. This is the
account-level allocator gap in `CLAUDE.md` showing up as a measured cost: with one position slot,
adding marginal setups is not free, it is a **queue**, and the marginal setup can be standing in
front of the trade that pays for the year.

## Per year — it helped the first four years and hurt the last three

| year | base n | base R | new n | new R | displaced R | cf R | delta |
|---|---|---|---|---|---|---|---|
| 2020 | 23 | 31.1 | 20 | +15.6 | 4.5 | 42.2 | **+11.1** |
| 2021 | 23 | 5.4 | 21 | +6.3 | −0.5 | 12.2 | +6.8 |
| 2022 | 22 | −4.0 | 35 | +15.4 | 1.8 | 9.6 | **+13.6** |
| 2023 | 28 | 20.5 | 25 | +7.2 | 0.1 | 27.6 | +7.1 |
| 2024 | 18 | 19.1 | 33 | −2.7 | −1.0 | 17.4 | −1.7 |
| 2025 | 33 | 22.4 | 27 | −4.7 | 16.1 | 1.6 | **−20.8** |
| 2026 | 17 | 16.2 | 12 | −3.1 | 0.0 | 13.1 | −3.1 |

The gain is 2020-2023 and the damage is 2024-2026. Per this file's standing per-year rule, that is a
config that worked in one regime, not an improvement.

## Verdict

1. **Keep `exec_req_fvg = True`. The FVG requirement is doing real work** — it is what makes the
   book 164 trades at 0.67R instead of 320 at 0.39R.
2. **The 180 "No FVG in zone" callouts are not lost money.** They are the filter working. The layer
   is still worth having as a diagnostic; it is not a to-do list.
3. **Drawdown is the disqualifier even on the best row.** 77.1% at 10% risk is not survivable, and
   Run 6's Finding 5 stands again: nothing but risk % moves drawdown on this bot.
4. **The 3-of-3 misses are a different and better question, and they are still open** — 18 final-hour
   + 7 never-filled + 3 veto = 28 setups that had every confluence. That is where to look next, and
   the final-hour bucket is the biggest single addressable one.

## What was NOT measured

- **Tick fills.** Bar mode, zero costs, like every run here. Note the counterfactual **doubles the
  trade count**, so real spread/commission/swap would penalise it roughly twice as hard — it can only
  weaken this row, not rescue it.
- **A gap-quality relaxation instead of a removal.** `exec_fvg_deep_only=False` and `exec_fvg_50`
  (which is unported here) both loosen *which* gaps qualify rather than dropping the requirement.
  Those are the honest follow-ups if the question is revisited — not this one.
- **The 3-of-3 buckets** (verdict item 4), the biggest of which is the final-hour rule.

Harness: `scratchpad/nofvg_ab.py` (the A/B + pairing) and `scratchpad/nofvg_extra.py` (the entry-level
robustness sweep + concentration). Both monkeypatch or re-configure `Execution`; **no repo file was
modified.** Throwaway, not committed.

## Run 12b — the four follow-ups Aaron asked for. All negative or neutral.

Same window, same method (one input changed, trades paired by entry bar). Recorded here rather
than as separate runs because they are one question: **can this strategy be made to trade more?**

### 1. Size the extras smaller (Aaron: "I'd take those at 5%, not 10%")

**Worse, and the direction of the error is instructive.** Risk % scales SIZE, not which trades
fire — so it scales the extras' contribution but NOT the cost of them displacing a real trade.
A 1%-risk no-FVG trade holds the one position slot exactly as long as a 10% one.

| extras at | trades | sumR (10%-risk units) | equity | maxDD |
|---|---|---|---|---|
| 0.5% | 320 | 91.3 | 153x | 55.8% |
| 1% | 320 | 93.0 | 179x | 53.1% |
| 2% | 320 | 96.4 | 235x | 55.6% |
| 5% | 320 | 106.6 | 426x | 64.9% |
| 7.5% | 320 | 115.1 | 568x | 71.5% |
| 10% | 320 | 123.6 | 652x | 77.1% |
| *shipped* | *164* | *110.6* | *395x* | *54.9%* |

Break-even is **X ≈ 6.2%** (`34.0R × X/10 = 21.0R`), so **5% is NEGATIVE (−4.0R)** and the
trade-off gets monotonically worse as X falls. At X→0 you have blocked 17 real trades for nothing.
**No X clears both bars** (beat baseline AND not raise drawdown).

**The matched-drawdown control kills it outright on Aaron's own terms** (he was explicit that the
goal is more money, not less drawdown): no-FVG at 5% = **426x at 64.9% DD**; the SHIPPED 164 trades
at `exec_risk_pct=12.5` = **832x at 64.2% DD**. Same ruin risk, nearly double the money, zero new
trades. Baseline gradient for reference: 5% → 44x/31.9%, 7.5% → 151x/44.4%, 10% → 395x/54.9%,
11% → 545x/58.8%, 12% → 728x/62.5%. **Adding marginal setups is a strictly worse use of a risk
budget than sizing up trades you already trust.**

### 2. Deep-fib entries (Aaron's cut: "only the ones with deep fib entries")

Wrong on BOTH axes he cares about — deeper means **fewer** trades *and* less money. The stop dial
is included because it is a CONFOUND: at stop 0.886 an entry at 0.786 leaves ~0.1 of the leg as
stop distance, which is Run 4's degenerate-sizing hazard, live.

| entry | stop | added | addedR | win/loss/be | median |
|---|---|---|---|---|---|
| **0.618** | 0.886 (shipped) | **173** | **+34.0** | 50/54/69 | +0.04 |
| 0.618 | 1.0 | 173 | +23.6 | 52/45/76 | +0.03 |
| 0.702 | 0.886 | 153 | −12.8 | 43/82/28 | −0.32 |
| 0.702 | 1.0 | 153 | −7.9 | 50/65/38 | +0.03 |
| 0.786 | 0.886 | 138 | −35.5 | 31/92/15 | **−1.00** |
| 0.786 | 1.0 | 138 | −8.8 | 42/72/24 | −0.27 |

**The confound was real and is now separated:** 0.786 goes −35.5R → −8.8R once the stop moves to
1.0, so most of the earlier catastrophe (equity → \$3,355) was the tight stop, NOT the entry.
**Hazard-free, deep entries are still negative.** The tell is the 0.786/0.886 row's median of
**exactly −1.00R** — the median added trade is a full stop-out, 92 of 138 lost.

**Mechanism:** filling deeper requires a deeper retrace, and a retrace that deep is the reversal
FAILING, not a better price. Shallower is no better (0.5 = −6.7R), so **0.618 is an interior
optimum — the level the Pine already picks.**

### 3. Loosen WHICH gaps qualify (`exec_fvg_deep_only=False`) — the one route that keeps the rule

**The worst of the three: 229 trades (+65), 78.2R vs 110.6R, 395x → 37x, maxDD 62.6%.**
The 101 added trades are worth **+3.4R total** (11 win / 20 loss / **70 breakeven** — median
+0.01R, pure noise), 36 real trades are displaced (+16.7R), and uniquely **it damages trades you
already take**: 7 shared trades were RE-PRICED for **−19.1R**, because a shallower qualifying gap
wins the "first price reaches" contest and drags the entry to a worse price. 2023 alone goes
+20.5R → −2.8R. **A looser gap rule is not additive — it is corrosive.**

### 4. The final-hour rule (`exec_no_late_day=False`) — the last 3-of-3 bucket

**Neutral. Keep the rule.** 18 setups are recorded as final-hour misses, but only **3 ever fill**
once the clock stops refusing them — the rest still need price to come back to the limit.

| | trades | sumR | equity | maxDD |
|---|---|---|---|---|
| rule ON (shipped) | 164 | 110.6 | 395x | **54.9%** |
| rule OFF | 165 | 111.1 | 337x | **54.9%** |

Added 3 (1 win / 1 loss / 1 breakeven, +1.8R), displaced 2 (+1.4R) → **net +0.4R on +1 trade**, and
the biggest added trade is **186% of the added total** (without it: −1.6R). Drawdown is identical
to the decimal. **The rule costs ~0.4R over 6.5 years and buys real session-gap protection — that
is free insurance, not a constraint.** (Note the equity multiple FALLS, 395x → 337x, purely from
compounding order — read sumR, not the multiple.)

## Verdict on the whole thread — the trade count is not inside this strategy

Four routes to more A+ trades, measured on 6.5 years: drop the gap (+173 trades, +13.0R net, 40%
one trade, negative 2024-2026), size the extras down (negative below 6.2%), deepen the entry (fewer
trades AND negative), loosen the gap rule (+65 trades, −32.4R). **The entry rule is not gatekeeping
trade count out of fussiness — it IS the edge**, and with ONE position slot every marginal trade is
a queue, not an addition.

**This is the same conclusion the account-level allocator gap in the root `CLAUDE.md` predicts, now
measured:** trade frequency is a PORTFOLIO property. The routes that remain are more SETUPS
(`mpc_bleg` is built and parity-green), more instruments, or more timeframes — not a looser A+.

## What was NOT measured (all four)

- **Tick fills**, as everywhere in this file. Every variant here ADDS trades, so real costs
  penalise them harder than the baseline — it can only strengthen these verdicts.
- **`exec_fvg_50` / `exec_conf_sz`** — the two Pine entry fallbacks not yet ported to Python. Both
  are "qualify a shallower entry", which is the family §3 just measured at −32R, so neither is
  promising. Porting them for parity is still worth doing; sweeping them is not.
- **A concurrency change.** Every number here assumes one position at a time. The displacement cost
  (17 / 36 / 2 trades) only exists because of that, and it is the single biggest term in §1 and §3.
  Whether the A+ book improves with two concurrent slots is a REAL open question — and it needs the
  account-level risk allocator that `CLAUDE.md` lists as unbuilt and as a prerequisite for running
  more than one bot live.

Harness: `scratchpad/nofvg_ab.py`, `nofvg_extra.py`, `nofvg_tiered.py`, `nofvg_deep.py`,
`loosen_gap.py`, `matched_dd.py`, `latehour.py` — all subclass or re-configure `Execution`; **no
repo file modified.** Throwaway, not committed.
