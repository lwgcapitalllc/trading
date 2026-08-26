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
  across `config.py`, `indicators/strategies/mpc_strategy.pine`, `indicators/strategies/mpc_strategy_export.pine`
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
| 13 | 2026-07-31 | **NOT a sweep — a DEFECT, found from one chart.** Stop staging reads the ENTRY BAR's own high/low, so a limit that fills on the way down is credited with the move that happened *before* it filled — promoted to breakeven having never been in profit | **44 of 164 trades (27%) are staged by their own entry bar** — 34 to breakeven, 10 straight to the TP2 floor; 35 die within 3 bars. Staging only from the bar AFTER the fill: **110.65R → 125.56R (+14.91R)**, same 164 entries, 30 outcomes changed. **81% of the gain is 3 trades and drawdown is UNMEASURED**, so the case is correctness, not profit. Present in `mpc_strategy.pine` identically. | ✅ **FIXED & SHIPPED 2026-08-01** (commit `8143c05`) — see the banner below |

| 18 | 2026-08-16 | **`exec_sl_deep` × `exec_secondary`, the full 2×2** — 4 full `run_dual` replays on ONE window (2018-09-14 → 2026-08-14, 186,910 M15 + 2,799,088 M1 bars, bar fills) | **`exec_sl_deep` stays OFF — it costs 24.0R with the secondary live and 23.0R without.** The shipped cell is the best of the four at **+164.4R / 189 trades**. The interaction is **1.0R against sd 15.06R**, i.e. the two levers are separable. Deep-ON does hold a shallower drawdown (−4.8 vs −5.5) and pays ~24R for it. | **measured — shipped default CONFIRMED** |
| 19 | 2026-08-16 | 🟢 **SCALE-IN** — add size to a runner the trail already protects, sized so an add's worst case equals the profit the stop guarantees. 2 stages (shadow ledger to search, real implementation to verify), XAUUSD 15m 2018-09-13 → 2026-08-14, **PU Prime ECN costs charged** | **+128.26R → +211.59R (+65%) at 2 adds / cap 1.0x**, ret/DD 21.27 → 24.26, **worst trade unchanged at −2.06R** and losers 65 → 67. Dropping the affordability test costs 8–13 extra losers, which is what the rule buys. **The trigger is arithmetic only — no structure, no retest; location has never been varied.** | **BUILT, toggle ships OFF — no parity gate has run** |
| 20 | 2026-08-17 | 🟢 **WHERE a scale-in adds** — 15 locations (retest, fib 23.6/38.2/50/61.8/78.6%, FVG, order block, fib∩gap, fib∪gap, ATR pullbacks, momentum, market), then per-year, per-half and a budget grid on the finalists | **`BOS retest` at 4 adds / cap 2.0x SHIPPED as the mode default** (toggle still OFF, so no figure here moves). The sweep's own winner (fib 23.6%, 302R) was **80% one year** — 2020-free it falls BELOW the shipped market rule. **Deeper is worse, monotonically**, and 61.8%/78.6% lose money outright. Two harness bugs caught. | 🔴 **VOID — broken fill model, superseded by Run 21** |
| 21 | 2026-08-18 | 🔴 **The scale-in grid RE-RUN on a corrected fill** — Run 20 priced every add at its TRIGGER, not where Pine buys it. 32 cells (2 modes × 1-4 adds × 4 caps) + a ladder-shape test, XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN costs | **`Trail` 3 adds × 0.5x cap SHIPPED** — 194.15R vs 128.26R not scaling, drawdown 6.03 → 7.24, and the only cell better than baseline on **both** axes over the full book. **`BOS retest` LOSES money outside 2020 at every budget above one add.** The CAP is the drawdown lever, not the add count. Ladder shape (big-first vs flat vs small-first) is inside the 15.06R jitter. ⚠ No cell beats baseline ret/DD ex-2020. | **SHIPPED (mode + adds + cap) — PARITY GREEN** |
| 22 | 2026-08-19 | 🔴 **WHERE THE SCALE-IN ADDS TAKE PROFIT** — the adds had no exit of their own, so this asked whether banking them beats riding. Two independent target families: a flat multiple of base risk (1R…8R, the control) and real structure (prev day/week H/L, H4, session H/L, and combinations). 16 configurations, XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN costs, on `Trail` 3 × 0.5x | **EVERY TARGET LOSES TO RIDING**, and they lose in order of how OFTEN the target fires — Ride 194.15R (0 banks), prev week 168.51R (16), prev day 157.57R (25), H4 146.09R (47). The flat-risk control produced the same monotonic curve independently, and banking at 1R (126.76R) came out **below never scaling at all**. 🔴 **The first structural table was VOID and these are RE-MEASURED** — the harness resolved its target from the LIVE bar, so `Prev day`/`H4` banked ZERO times in 8 years while resolving 1,804 and 2,438 valid targets; day/H4 levels die on a WICK and the engine steps first, so the level was gone on the exact bar it would have filled. **Weekly dies on a CLOSE through and was immune, hiding it on the only mode being watched.** ⚠ Worst trade is −2.06R in every configuration — the affordability rule already prevents the giveback a target was asked for. ⚠ **Strip the top 20 trades and banking WINS on risk-adjusted return** (prev day 14.49, H4 14.60 vs Ride 11.99): it smooths the ordinary book and pays for it out of the tail. | **`exec_scale_tp_mode` SHIPPED defaulting to `"Prev week H/L"` — Aaron's call, AGAINST the measurement.** 🔴 **DEFAULT UNDER REVIEW** — he chose it on a 4.38R gap said to be inside the 15.06R jitter; the true gap is **25.64R, outside it**. 🔴 **NOT PARITY-GATED YET** |
| 23 | 2026-08-19 | **THE SECONDARY (1m re-entry), END TO END** — 7 levers, 26 replays: the entry gates (swept-stop re-entry, zone depth) and then the exit ladder (depth cap, 1m direction filter, where breakeven fires, banking at TP1). | **The entry gates are already right and the exit ladder was not.** Every loosened door is worse, monotonically. Depth 2/3/5/unlimited are byte-identical (n=1 in 6.6 years). Banking part of a re-entry at TP1 is the first change in 26 replays that works — win/loss 1/1 → 4/1 — and it costs the tail. | measured, **nothing adopted** |
| 24 | 2026-08-19 | 🔴 **THE LOSS-RECOVERY LEG** — nine stop placements and six exit ladders on the 25%-size counter-trade taken after every A+ loss (`strategies/python/loss_recovery/`). Not a sweep of this bot's params; its population is A+'s 62 real stop-outs. | **Nothing beat the shipped rule, and its best-looking challenger was five trades.** A stop on the CHoCH bar's own extreme scores +24.4R against +16.2R on a 7x tighter stop with lower drawdown — and **−7.4R once its best five are deleted**, where the shipped stop survives at +2.3R. `soft_stop_r=-0.3` is the one free change: same net R, avg loss −1.01R → −0.30R, win 58% → 37%. Everything else lost. | measured, **nothing adopted; `loss_recovery` still ships `enabled=False`** |

⚠ **Rows 14–17 were never added to this index; their `# Run N` sections below are the authority.**
Count the runs with `grep -c '^# Run ' `, never off this table.

🔴 **READ THIS BEFORE QUOTING ANY NUMBER ABOVE. Run 13's defect SHIPPED on 2026-08-01, so every
figure in Runs 1–12 was measured through a bug that no longer exists.** The fix (commit `8143c05`)
changed 30 of 164 outcomes without touching a single entry, so a config's *ranking* is probably
intact but its *score* is not. **No run in this file has been re-measured against the fixed build.**
Treat every R figure above as a pre-fix number until it is.

⚠ **The two post-fix measurements taken so far DISAGREE on the baseline, and reconciling them is an
open item.** Run 13's counterfactual (below) measured 110.65R → 125.56R over 164 trades,
2020-01-01 → 2026-07-29. The shipped fix measured **101.68R → 112.43R over 165 trades** on lab run
`d2ab68f9e884`. Same change, same direction, ~+11R either way — but the *baselines* differ by 9R,
which is a window/config difference nobody has chased down yet. Do not average them and do not quote
one as if it settles the other.

➡ The defect itself — mechanism, why it is wrong, why no parity gate could see it, and what is still
open — is in **`indicators/docs/BUG_exit_fill_price_mismatch.md`** (status: ✅ CLOSED). It was found by
eye off a price chart by Aaron's brother on 2026-07-14.

✅ **Both Pine↔Python parity gates were re-run GREEN on 2026-08-01, post-fix** (`compare_strategy.py`
and `compare_bleg.py`, both 21,691 bars, 2025-08-31 → 2026-07-31, **exit 0 at warmups
100/200/500/1000/2000**). That is the run that matters: it says the Run 13 fix landed identically on
both sides. The earlier 2026-07-29 pass (21,494 / 21,493 bars, at the shipped
`exec_tp1_pct = exec_tp2_pct = 0` and carrying the ratchet through `cfg_exitmode`/`cfg_trail_pct`)
CLEARED the Run 8 stale-parity warning — Runs 8–9 describe the Pine Aaron trades.

⚠ **A green parity run says the two implementations AGREE, never that either is RIGHT.** Run 13's
defect was faithfully ported, so this gate was green for its entire life and never saw it. It took a
human reading a price chart to find it.

⚠ One parity gap remains and it is the one that matters for Run 11's recommendation:
`mpc_strategy_export.pine` still emits **no `cfg_min_stop*` column**, so parity is proven only at the
`execMinStopMode = "Off"` default. Shipping the guard means closing that hole in the same commit.

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
   `indicators/strategies/mpc_strategy.pine`, `indicators/strategies/mpc_strategy_export.pine` and
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

`exec_min_stop_pct` (default 0.1) in `config.py` **and** in `indicators/strategies/mpc_strategy.pine` **and**
`indicators/strategies/mpc_strategy_export.pine` (new `cfg_*` column) **and** `compare_strategy.py`
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

🔴 **CORRECTED BY RUN 25 (2026-08-24) — DO NOT QUOTE THE "FREE INSURANCE" LINE ABOVE.** It was
asserted, never measured, and it is wrong: **44% of this book already sits through a session break
and 9% through a WEEKEND**, so the rule closes a two-hour window while the exposure runs the other
twenty-two. ⚠ **The VERDICT survives — keep the rule** — but on the trades, not on the insurance:
re-measured on today's config only **two** of the added trades are genuinely final-hour entries and
they are worth **−1.56R** together, while the headline +0.4R is one unrelated setup filling fifteen
minutes earlier. ⚠ **The +0.4R here and in Run 25 agree across two different baselines**, so the
arithmetic was never the problem — the interpretation was. See Run 25.

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

---

# Run 13 — The entry bar stages its own stop (2026-07-31) — ✅ **FIXED 2026-08-01, not a sweep**

**This is the only entry in this file that is not a parameter sweep.** It is a logic defect found
by reading one chart, then measured. **It was fixed and shipped the next day in commit `8143c05`** —
in all five strategy Pine files and in `strategies/python/mpc_sos_fade/execution.py` (which
`mpc_bleg` reuses), with both parity gates re-run green on full-history post-fix exports.

⚠ **The numbers below are the pre-fix COUNTERFACTUAL, not the shipped result.** They come from a
patched replay in the scratchpad that monkey-patched the staging call; nothing in the repo was
modified when they were taken. The shipped fix measured **101.68R → 112.43R over 165 trades** on lab
run `d2ab68f9e884` — same direction, ~+11R either way, but off a different baseline. See the
reconciliation warning at the top of this file before quoting either.

➡ **The defect itself — mechanism, why it is wrong, why no parity gate could see it, and what is
still open — lives in `indicators/docs/BUG_exit_fill_price_mismatch.md`** (status: ✅ CLOSED). This entry
is the MEASUREMENT only. Do not duplicate the analysis here; update the bug file.

## How it was found

Aaron asked why the 2025-10-02 A+ long lost when price never reached the 0.886 stop. It didn't
need to — the stop had already moved to breakeven, on the entry bar, before price came back.

```
bar 12057   2025-10-02 10:30 NY   O 3864.01  H 3866.09  L 3836.38  C 3837.94
  10:30:00   3864.01   FLAT — a limit rests at 3842.60
     ...     3866.09   FLAT — the bar's high
     ...     3856.29   FLAT — this is TP1 (fib 0.5). Nobody is in a trade.
     ...     3842.60   LIMIT FILLS — now long
     ...     3836.38   underwater
  10:44:59   3837.94   close.  staging asks "high >= TP1?"  3866.09 >= 3856.29 -> stage 1
                       stop 3804.82 -> breakeven + 30tk = 3842.90

bar 12058   O 3838.07  -> already through 3842.90, fills at the open.  -0.12R
```

The position's best price while open was its own fill. It was never one cent in profit. Why that is
a defect rather than a tuning choice, and why no parity gate could see it:
`indicators/docs/BUG_exit_fill_price_mismatch.md`.

## Measured — 2020-01-01 → 2026-07-29, 155,255 M15 bars, shipped config

| | trades | sumR |
|---|---|---|
| baseline (shipped) | 164 | **110.65** |
| staging starts the bar AFTER the fill | 164 | **125.56** |

Entries are byte-identical in both runs — the entry rule is untouched, only the stop moves.

```
trades staged by their OWN entry bar     44 / 164   (27%)
  -> stage 1 (breakeven)                 34
  -> stage 2 (TP2 floor)                 10    stop jumps PAST breakeven on the entry bar
  died within 3 bars                     35
  their combined result                  +20.5R
outcomes changed by the counterfactual   30
```

Biggest movers (baseline R → counterfactual R):

```
2025-06-12   +0.02 ->  +4.50      2020-09-29   +0.18 ->  -1.00
2025-05-30   -0.07 ->  +3.90      2023-02-16   +0.07 ->  -1.00
2025-04-23   -0.23 ->  +3.37      2026-05-11   +0.01 ->  -1.00
2020-05-08   +0.21 ->  +2.86      2021-06-18   -0.00 ->  -1.00
2020-08-27   -0.37 ->  +1.58
```

## Read the +14.91R honestly — it is NOT the reason to fix this

**Three trades carry 81% of the gain** (+12.05R of +14.91R); past the top seven movers the
remaining 18 changed trades net to roughly zero. That is the same concentration signature this file
has already called noise twice (Run 12's "40% of the gross is one 2020 trade", Run 9's "11 trades
carry 106R of 109R"). A result resting on three trades in 6.6 years is not a measured edge.

Four scratches also become full −1.00R stops. Run 3 measured that delaying breakeven grows drawdown
3.5x, and this is a milder version of the same lever, so **drawdown is expected to move the wrong
way and it was NOT measured.**

**Fix it because the rule fires on the wrong event. If it had measured at −5R the answer would be
the same.**

🔴 **IT SHIPPED, so every historical figure in THIS FILE has moved** — all 12 prior runs are measured
against a 110.65R baseline that the fix invalidated, and **none of them has been re-measured.** The
re-baselining is tracked in `indicators/docs/BUG_exit_fill_price_mismatch.md` → *What is still open*.

Harness: `scratchpad/why_trade.py`, `why_trade2.py`, `why_exit.py`, `stage_audit.py` — the audit
monkey-patches `Execution._advance_stage` to skip the entry bar; **no repo file modified.**
Throwaway, not committed.

---

# Run 14 — 2026-08-01 — **OPEN HYPOTHESIS, NOT MEASURED.** The SOS with no follow-through is a sweep

**Aaron's observation, his words:** *"If there's a shift of structure and it barely closes above,
meaning it does not even have one candle or two … two candles going in, and they occur third chain.
Then that can probably be a sweep, and that [trade] can most likely lose."*

**The claim.** An SOS that closes only marginally through the broken level, and is NOT followed by
a couple of candles continuing in the break direction, is not a real shift — it is a liquidity
sweep wearing an SOS label. A+ arms Stage 2 on that SOS, so the "retrace into 0.5-0.886" it then
waits for is not a retrace at all: it is the reversal continuing, and the limit fills into it.

**Nothing like this exists in A+ today.** Grepped `mpc_strategy.pine` for displacement /
follow-through / consecutive-close gates: there are none. The SOS arms Stage 2 the moment
`close > ash` (or `< asl`), with no test of how far past, and no test of what the next bars did.

**Two DIFFERENT filters live inside that one sentence, and they must not be conflated:**

| | what it measures | already exists anywhere? |
|---|---|---|
| **MAGNITUDE** | how far past the broken level the breaking candle CLOSED | Yes — `bosMinDispAtr` in `mpc_bos_strategy.pine` ("Break must clear the swing by x ATR", default 0.5). **Never measured** — the BOS file's own tooltip says so. |
| **PERSISTENCE** | how many candles CLOSED in the break direction before price turned | **No. Nowhere.** This is the new idea. |

Aaron described the second one. A one-candle poke that closes a long way past the level would PASS
a magnitude filter and FAIL a persistence filter, and a slow grind two candles deep would do the
reverse. They are independent, and the sweep signature is arguably the second.

## What this is NOT, so it does not get answered with the wrong data

**Run 10 does not cover this.** Run 10 cut by the shape of the path AFTER the trade was already
open (pokes in and out of profit, stalls). This is a gate BEFORE the setup ever arms — a different
population and a different question. Nothing in Runs 1-13 tests the SOS bar itself.

**Run 6 does not cover it either.** Run 6 established that a live losing trade is indistinguishable
from a live winner. That is about trades that already exist. This proposes to stop some from
existing.

## The honest prior, stated before measuring so it cannot be fitted afterwards

Every "cut the losers" family measured in this file has lost money — Run 5 (nothing to cut
quicker with), Run 6 (~40 cut variants, all negative), Run 10 (70 poke combos, all negative). That
is a poor base rate for this class of idea in this strategy, and it is a reason to score it
honestly, not a reason to skip it: those three all cut trades that were ALREADY OPEN. This one
refuses the setup, which is the one shape not yet tried.

Run 12 also removed the usual objection: with one position slot, fewer trades is not automatically
worse, because a marginal setup DISPLACES a real one rather than adding to it. So a filter that
cuts trade count can win on both R and drawdown — that is exactly what has to be measured.

## What a measurement has to report, or it does not count

- **R, not dollars**, and per-half + per-year (this file's standing convention).
- **Both sides of the ledger**, the way Run 10's separation table did: of every SOS that FAILS the
  filter, what did those setups turn out to be? If the loss rate among them is not clearly above
  the 32% base rate, there is nothing here and no threshold will find it.
- **Winners killed**, in R, against losers avoided. Run 10 died on this column.
- **Drawdown**, which Run 6 identified as a losing-streak property that only risk % moves. A filter
  that improves R but not drawdown is a smaller book, not a safer one.
- **The grid**: persistence N ∈ {1, 2, 3} closes; magnitude ∈ {0, 0.25, 0.5, 1.0} × ATR; and the
  two crossed, because they may only work together.

**One design question to settle first, and it changes what is even measurable.** Requiring N
candles of follow-through DELAYS the arm by N bars. On a fast reversal the retrace into 0.5-0.886
can begin inside those N bars, so the filter would not merely refuse bad setups — it would arrive
too late for some good ones and never place their order at all. That cost is invisible unless the
harness counts the setups lost to LATENESS separately from the setups lost to the FILTER. Design
the capture for that before running anything.

## Status

**Not built, not measured, nothing adopted.** No code changed. Recorded so the idea is not lost and
so the next person does not answer it with Run 10's data.

---

# FVG DETECTION — 2026-08-01 — **OPEN DEFECT.** A+ does not see gaps that are on the chart

**Found by Aaron on a live chart** (XAUUSD, ~$4,170, Nov 27-28 2025): two fair value gaps he drew
by hand were not drawn or held by the strategy. This is the SAME class of discrepancy already fixed
in `mpc_bos_strategy.pine` on 2026-07-31 — and A+ was deliberately left alone at the time, so the
gap is still open here.

**Three filters, all still at the A+ values, any of which alone explains a missing gap:**

| input | A+ (`mpc_strategy.pine`) | what the chart draws (`mpc_assistant.pine`) | effect at gold $4,170 |
|---|---|---|---|
| `fvgThreshHTF` (15m+ min gap) | **0.1 %** | 0.04 % | A+ needs **$4.17**; the chart draws from **$1.67**. Every gap between those two is VISIBLE and INVISIBLE to the strategy at the same time. |
| `fvgReqCloseHTF` (middle bar must close past the gap) | **ON** | OFF | A+ refuses a gap the chart shows whenever bar B closed inside the void. |
| `fvgMaxCount` | **7** | 8 | The 8th-oldest gap is evicted here and kept there. |

A fourth, smaller one now exists too: the EQ engine was ported into all three strategy files on
2026-08-01, but `eqExemptFvg` defaults **OFF** there and is hardcoded **ON** in the assistant — so a
gap sitting on an EQH/EQL survives the cap on the chart and is evicted in A+.

**The 0.1 % floor is the prime suspect** because it is the only one that scales with price: gold has
run to $4,170, so the floor is now $4.17 and rising, while the gaps a 15m bar leaves have not grown
with it. This filter gets stricter every year with no one deciding that it should.

**Why A+ was NOT changed when the BOS file was.** Both values are load-bearing here and only here:

1. The **110.65R baseline** and every one of Runs 1-13 were measured at 0.1 / close-test-ON.
   Changing either moves which gaps exist, so it moves which entries fire, so **every number in
   this file becomes invalid.**
2. `MpcSosFadeStrategy.engine_config()` PINS `fvg_require_close = True` specifically to match this
   Pine. Turning the Pine's test off without re-pinning the Python breaks `compare_strategy.py`
   silently — and the export carries no `cfg_` column for either input, so the harness would go
   GREEN while comparing two different gap populations.

**So this is a DECISION, not a bug fix.** Matching the chart is one line per input. The work is
everything attached to it:

- flip `fvgThreshHTF` 0.1 → 0.04 and `fvgReqCloseHTF` ON → OFF in `mpc_strategy.pine` **and**
  `mpc_strategy_export.pine` in the same commit (the export must never drift from the parent),
- add `cfg_fvg_thresh` / `cfg_fvg_req_close` columns and decode them in `compare_strategy.py`,
  so the harness can never again go green across a floor change,
- re-pin `EngineConfig.fvg_require_close` from the export rather than hardcoding True,
- re-export off a fresh paste and re-run `compare_strategy.py` to exit 0,
- **then** re-measure the baseline, and treat every prior run in this file as superseded.

Same prerequisite chain as `indicators/docs/BUG_exit_fill_price_mismatch.md` (the Run 13 defect). Do not
do the one-line half of it alone.

⚠ **Unverified from the screenshot: WHICH filter refused those two specific gaps.** Three candidates
fit. Confirming it costs one chart: put `mpc_assistant.pine` and `mpc_strategy.pine` on the same
chart, set the assistant's FVG drawing on, and read off which gaps differ — then check each
candidate gap's height in dollars against $1.67 and $4.17. Do that before changing anything, or the
fix is a guess.

💡 **This got cheaper on 2026-08-01 and the note above predates it.** The command center's price
chart now draws fair value gaps server-side (`command-center/backend/services/fvg_overlays.py`,
Analysis dropdown, default OFF) — and it deliberately draws **`mpc_assistant.pine`'s** gaps at cap 8
/ no close-check / the 0.0–0.04 split floor, i.e. exactly the set A+ does NOT trade. So a run page
already shows both populations at once: a visible gap beside a "no FVG" block IS the discrepancy
this section is about. Read it there against a real run before touching TradingView.

**Unrelated cosmetic bug found while checking, in BOTH A+ and BOS:** `fvgKeepUntilBroken` is
declared `input.bool(true, …)` but its tooltip opens *"OFF (default) = a gap is removed the moment
price taps its near edge."* The default is ON. The tooltip is wrong, not the code — the behaviour is
keep-until-broken. Fix the text, not the default.

---

# ENTRY PRICE — 2026-08-01 — **OPEN CHANGE REQUEST.** Snap every gap entry to a fib, not the gap edge

**Aaron, 2026-08-01:** *"The entry should be on the nearest fib, not the edge of the fair value gap."*

**Half of this already exists and the other half is the hole.** `execDeepFib` (Method 3, added
2026-07-23, default ON) does exactly this — but ONLY for a gap whose near edge sits DEEPER than
0.618. Everything shallower still rests at the raw gap edge.

```pine
f_deepFibEdge(_gB, _gT, _bull, p3, p4, p5) =>
    if _bull and _gT < p3            // ONLY fires past 0.618
        _out := _gT >= p4 ? p3 : _gT >= p5 ? p4 : p5
...
float _e = na(_df) ? math.min(_gT, lTop) : _df      // else: the gap's own edge
```

With `exec_fvg_deep_only` ON (the shipped default) a qualifying gap's near edge sits between 0.5 and
0.886. So the untouched population is precisely **gaps whose near edge lands between 0.5 and
0.618** — those rest at an arbitrary price like 0.57 that is not a fib at all, is not a level anyone
drew, and is not a level price has any reason to respect.

**The fix is to extend the same function down one rung**, so 0.5 becomes a snap target alongside
0.618 / 0.702 / 0.786. One branch, both directions, in `mpc_strategy.pine`, `mpc_strategy_export.pine`,
`mpc_bos_strategy.pine` (same helper, same hole) and `execution._deep_fib_edge()`.

## The one design question that has to be answered first

**"Nearest" is ambiguous, and the two readings are different strategies.** Method 3 today does NOT
snap to the nearest fib — it snaps to the nearest fib **SHALLOWER** than the gap, deliberately. Its
own tooltip gives the reason: *"the price you reach first — instead of chasing the gap's own edge,
which price may never tap."*

| reading | a long whose gap top is 0.57 rests at | consequence |
|---|---|---|
| **nearest SHALLOWER** (what Method 3 does today) | 0.5 | fills MORE often, at a WORSE price, and fills **before price ever enters the gap** |
| **nearest by distance** | 0.618 (0.57 is closer to 0.618 than to 0.5) | better price, but the fill now requires a deeper retrace than the gap itself demanded — some never come |

Extending the current behaviour means the second option is never chosen. That is defensible and
consistent, but it makes something explicit that is currently half-hidden: **once every entry snaps
shallower, the FVG stops being the entry price and becomes only a QUALIFIER** — it says "a gap
exists in this band", and a fib decides where the order rests. The trade may then fill without price
ever touching the gap it was justified by.

That may be exactly what is wanted. It is not what the spec says today, so it needs to be a stated
decision rather than a side effect of a one-line edit.

## Second-order effects to check, not guess

- **0.886 is never a snap target and must stay that way.** The helper's shallowest output is 0.786.
  In A+ the default stop IS 0.886 (`exec_sl_level`), so snapping an entry there would put the stop
  on top of the entry — the Run 4 hazard. Do not add it as a rung.
- **`mpc_bos_strategy.pine` derives its TP ladder from where the entry landed** (`longTier` /
  `shortTier`, added 2026-08-01). Snapping every entry to a fib makes those tiers cleaner, not
  messier — but the tier boundaries are `<= 0.618` and `> 0.5`, so an entry snapped exactly TO 0.5
  lands in the STANDARD tier, not SHALLOW. Verify that is still the intent after the change.
- **The BOS file's new `bosEntryTop = "0.382"` option** (also 2026-08-01) adds 0.382 as a band
  ceiling. If that is on, 0.382 becomes a legitimate snap target too and the helper needs it.
- **This moves every A+ number in this file.** It changes entry PRICES, so it changes fills, R and
  drawdown on trades that already exist — a bigger blast radius than the FVG-floor item above, which
  only changes WHICH gaps qualify.

## What a measurement has to report

Same bar as every other run here: R per half and per year, drawdown, and **the trades whose entry
price actually moved** counted separately from the trades that changed outcome. Most entries will be
unaffected (the deep population already snaps); the honest question is what happens to the 0.5-0.618
band alone, so report that slice on its own rather than only the aggregate.

## Status

**Not built, not measured, nothing adopted.** Recorded with the ambiguity unresolved on purpose —
answer "nearest shallower or nearest by distance" before writing the branch.

---

# FVG TIMING — 2026-08-02 — **MEASURED. A gap born INSIDE the zone confirms its own entry.**

**Aaron found it on the chart, from one trade: 30 Sep 2025.** Price traded into the 0.5-0.886 band,
flipped violently while it was in there, and that flip printed a fair value gap. The strategy then
used that gap as the entry confirmation — the retrace manufacturing the confluence it is judged on.
His rule: **a gap must already exist when price arrives at the zone.**

## The defect

Neither the Pine nor the Python asks WHEN a gap was born. The entry-edge loop only asks whether a
live gap OVERLAPS the band on the current bar:

| where | what |
|---|---|
| `mpc_strategy.pine` | the entry-edge loop (`longEdge`/`shortEdge`) + the `aplus*_fvg` confluence flag |
| `execution.py` | `_entry_edges()` |
| `sequence.py` | the `l_fvg`/`s_fvg` confluence flag |

Both sides already STORE the birth bar (`fvgBorn`, `FvgGap.born_index`). Nothing reads it. What was
missing is a "bar price entered the zone" marker — the Pine's own `fiboHalfReached` latch is exactly
that event, it just never recorded the bar.

## How it was measured

Full replay, `backtest/cache/XAUUSD__M15.csv`, **2020-01-01 → 2026-07-31, 155,431 M15 bars**, shipped
defaults, post-Run-13 build. Two passes over the same bars: shipped, then with every gap whose
`born_index` is not STRICTLY earlier than the leg's 0.5-tag bar removed from `sig.fvgs`. Trades
paired on `(dir, sos_bar, day)` so a trade can be classified rather than just counted.

**Zone entry is the Pine's OWN `fiboHalfReached` latch, not a raw price test.** That matters: a first
pass using `low <= fiboP2` directly gave 149 trades / +104.22R. The faithful definition gives
148 / +105.22R. Use the latch — it is what the A+ stage machine already calls "in the zone", and it
resets with the fib leg, which is the leg the gap is being judged against.

## The result

| | trades | R | W / scratch / L |
|---|---|---|---|
| shipped | 165 | **+126.68** | 66 / 45 / 54 |
| rule enforced | 148 | **+105.22** | 60 / 38 / 51 |

The baseline reconciles with Run 13's post-fix figure (125.56R / 164 trades to 2026-07-29) — this run
just carries two more days. **Read the DELTA, not the totals.**

**20 baseline trades are touched:** 18 vanish, 2 survive on an older gap at a different limit (both
lost either way), and **1 NEW trade appears** — the one position slot, freed by a removed trade.

| year | shipped R | rule R | delta |
|---|---|---|---|
| 2020 | 32.56 | 27.03 | −5.53 |
| 2021 | 7.46 | 7.97 | **+0.51** |
| 2022 | −3.03 | −4.88 | −1.85 |
| 2023 | 20.63 | 20.57 | −0.06 |
| 2024 | 17.95 | 19.94 | **+1.99** |
| 2025 | 34.79 | 18.75 | −16.04 |
| 2026 | 16.31 | 15.84 | −0.47 |

## The whole cost is ONE trade

The 18 removed trades are +20.47R at 6 wins / 7 scratches / 5 losses. **2025-10-21 alone is +16.49R.**
Strip it and the other 17 are **+3.98R over six and a half years** — noise, on a 126R book.

So this is a rule to decide on the LOGIC. The R says almost nothing either way, and the one trade it
does say something about is the one examined below.

## ⚠ The cross-analysis, and a claim that was WRONG on the first pass

The first read of the counterfactual was reported as *"18 vanish because no other gap was in the
zone"*. **That was the replay's conclusion restated, not an inspection, and it is false.** Every zone
was then enumerated gap by gap:

| why no pre-zone gap qualified | trades (they overlap) |
|---|---|
| **nothing alive at all** | **0** |
| some pre-zone gap was the **wrong direction** | 14 |
| pre-zone gap **outside the 0.5-0.886 band** | 9 |
| right direction, in band, rejected only by **`exec_fvg_deep_only`** | 4 |
| a gap **fully qualified** and still no trade followed | 3 |

**There is never an empty zone** — every one of the 18 had 3-6 gaps alive. The dominant disqualifier
is DIRECTION, and that is structural rather than incidental: price ran one way into the zone, so the
gaps it left behind point away from the fade being taken.

**The 4 in the deep-only row are the actionable finding.** Those setups had a legitimate
right-direction gap sitting in the band, and `exec_fvg_deep_only` rejected it for straddling 0.5 —
not this rule. **The two toggles compound**, and that interaction has never been swept.

## The +16.49R trade, in full — it is not what it looked like

2025-10-21 short. **Two bearish gaps DID pre-date the zone** (born bars 136913 / 136921), and they
rested a short limit at **4293.55** from well before price arrived. Price then traded up through it.

It never filled because the **divergence / extreme-RSI veto was blocking the short** — armed on **0 of
51 bars** while those gaps were alive. Bar 137008 then ripped 4292 → 4323.67 and mitigated both. From
there NO bearish gap existed until the reversal candle at 137056 printed the one that took the trade.

So the honest reading: this rule does not reject a setup that had no confirmation. It rejects one
whose confirmation the veto stopped it taking, and which the market then destroyed. The other two
qualified-gap cases are simpler — the limit rested at a different price and price never returned
(2024-01-29 at 2044.19, armed all 13 bars; 2026-02-15 at 5067.65, armed 32 of 36).

## Status — ⚠ BUILT, THEN LOST IN A TRADINGVIEW ROUND-TRIP

The toggle was written into `mpc_strategy.pine` on 2026-08-02: `execFvgPreZone` (default OFF), a
`fiboHalfBar` latch set beside `fiboHalfReached` and reset with the leg, and one helper
(`f_gapPreZone`) ANDed onto every consumer of the gap arrays. **A paste from the TradingView side
overwrote the file the same day and none of it survives** — same failure as `execFvgDeepest` in the
2026-07-26 entry of `indicators/CLAUDE.md`. Rebuild from this record, and **commit repo-side Pine work
before the next round-trip**.

Nothing was ported to Python, so `mpc_sos_fade` still takes all 18 trades. Parity is unaffected —
the toggle defaults OFF and byte-identical, and the export carries no `cfg_` column for it, so a run
with it ON would be a TradingView finding, not a validated one.

## What was NOT measured

- **Drawdown.** Only trade count, R, and the per-year split. The removed trades include four −1R
  losers, so DD could move either way and this run cannot say.
- **The interaction with `exec_fvg_deep_only`**, which the category table shows is doing part of the
  same job on 4 setups. Sweep the two together before adopting either.
- **The inclusive variant** (`born <= zone entry`) is identical to the strict one under the Pine
  latch — 148 trades both ways — so the boundary is not a live question here. It was NOT identical
  under the raw-price definition (145 vs 149), which is one more reason to keep the latch.
- **`mpc_bleg`** is structurally unaffected — its trigger is the band tap and it never reads an FVG.

---

# Run 15 — 2026-08-09 — **ORDER BLOCKS. Seven angles, two timeframes, all null. THREAD CLOSED.**

Aaron: *"I'm so convinced that there's something there with order blocks, and I can't figure out
what it is."*

This is the whole record of what was tried, so nobody re-runs it. `docs/MPC_OB_FADE_SPEC.md` —
which described a separate `mpc_ob_fade` fork — was **DELETED** in the same commit, because the
measurement below says that bot should not be built and a spec left lying around is a signpost
pointing the next reader at work the data already closed.

## The seven angles

All measured over 155,531 M15 bars (2020-01-01 → 2026-08-03), against the shipped FVG rule's
**159 trades / +142.18R**.

| # | Angle | Result |
|---|---|---|
| 1 | `exec_poi_source = "Order block"` — blocks INSTEAD of gaps | 267 trades / +75.93R |
| 2 | `"Either"` — blocks OR gaps, pooled | 292 / +85.77R (worst) |
| 3 | `"FVG first"` — gaps ranked first, blocks as fallback | 276 / +102.90R |
| 4 | `"Order block (no FVG)"` — a block leg with its OWN slot, stacked | leg solo 133 / **+0.02R** / maxDD 21.81R; the pair posts +142.19R against the FVG leg's own +142.18R |
| 5 | Block PRESENCE as a filter on the existing book | mildly ANTI-predictive (no-block +1.847R/trade vs +0.595R with) |
| 6 | `exec_ob_deepen` — re-price an entry onto a deeper block | 102 / +73.41R / maxDD 15.20R |
| 7 | **Gap-on-block as a QUALITY split of the existing book** | no separation — see below |

## Why angles 1-6 could never have worked, and it is not about order blocks

Every one of them asks *where do I put my limit order*, so every one lets a block ARM a setup the
gap rule never armed. With ONE position slot that is not an addition, it is a **queue** — the Run
12 lesson arriving through a different door.

**`"Either"`'s 178 ADDED trades were +33.08R POSITIVE and the book still came out worst**, because
it displaced 45 real ones. The `"FVG first"` decomposition is the same story in more detail:
UNTOUCHED 130 (+110.07R) · REPRICED 0 · **DISPLACED 29 (+32.11R gone)** · NEW 146 (−7.16R, i.e.
−0.049R each) = **−39.27R**, and ONE displaced trade (2025-10-21, +16.49R) is 42% of the damage.

⚠ So **"the added block trades lose money" is the WRONG summary and must not be recorded as the
finding.** They roughly break even. What loses is what they push out of the way.

⚠ Angle 6 failed for a separate, geometric reason worth keeping: **TP1 is a fib ABOVE a long, so a
deeper entry is FURTHER from it** — TP1 hit rate 65.4% → 47.1%, scratches 44 → 15, and a median
79% tighter stop sits inside ordinary bar noise so the average loss went **−0.98R → −1.37R**. 57
trades never filled at all, giving up +44.61R, and the freed slot produced **ZERO** replacements.

## Angle 7 — the only order-block question the position slot cannot punish

`backtest/tools/ob_confluence.py`. It splits the **already-taken** book by whether the gap each
limit actually rested on had a same-direction order block under it. It adds no trade, removes
none and moves no entry price, so displacement is structurally impossible. It is also the shape
Aaron's standing requirement asks for — *"I wanna be able to tune how much risk they can take
because some trades are just way higher quality"* — because a quality split is a SIZING lever.

Control reproduced to the cent (159 trades / +142.18R) with the block engine forced on.

| blocks read from | on-block | avg R | plain gap | avg R | difference |
|---|---|---|---|---|---|
| **15m** | 81 | +0.763R | 78 | +1.031R | −0.268R = **0.47x** its own standard error |
| **4H** | 16 | +0.980R | 143 | +0.885R | +0.095R = **0.08x** the noise |

**Neither separates anything.** The undirected reading at 15m is *byte-identical* (same 81/78
split, same R), so whether the block points the same way as the gap decides nothing either. And
the 4H on-block total is **one trade**: strip its best (+16.49R) and the other 15 make **−0.81R**.

## 🔴 The tidy explanation for angles 1-6 was WRONG, and angle 7 at 4H is what refuted it

The story offered after the first six was: an order block is **wallpaper** — a live one exists on
**99.9% of all bars** — so it cannot separate anything because it is present on nearly everything.

That story predicts a **rarer** block separates better. It does not. **4H blocks tag 16 of the 159
trades where 15m blocks tag 81 — five times rarer at the entry — and the separation gets WORSE.**

**Scarcity was never the problem.** The statement the data supports is duller and narrower:
**an order block carries no information about how these trades turn out.**

⚠ **Standing lesson, and it is about explanations rather than order blocks: six null results were
given one story that fitted every number, and the seventh test refuted the story while agreeing
with all of them. A story that fits the evidence is not evidence — run the test that could break
it.** Here that test was one flag.

## How the tag is kept honest

- **Pinned to `Execution._entry_edges`.** Naming the winning gap means re-running the selection,
  and a second implementation of a rule is this repo's signature defect — so the replica must
  reproduce the real edge **to the float on every bar** and REFUSES the run otherwise. Zero
  mismatches over 155,531 bars.
- **The tag is taken at PLACEMENT, from the winning gap, AFTER the gates.** Not "was a block
  nearby". A gap only becomes the entry if it cleared the band, the deep-only gate and the
  pre-zone gate.
- **Higher-timeframe blocks obey a hard no-lookahead rule** — a snapshot is admitted only once its
  own coarse bar has CLOSED. Get that wrong and the tool manufactures an edge out of nothing.
- **Non-vacuity probes refuse rather than print a confident 0%** — no bar carrying a block, or no
  candidate ever overlapping one, is an error, not a result.

---

# Run 16 — 2026-08-09 — **THE TIMEFRAME SWEEP. 30m looked like the one win for an hour.**

Asked in the same session: *"does this mean you gonna run the strategy... on, like, thirty
minutes, one hour, four hour time frames?"* `backtest/tools/tf_sweep.py`, same 6.5 years,
shipped defaults, costs off (matching every baseline figure here).

| tf | bars | trades | total R | avg R | ± se | maxDD R | win% |
|---|---|---|---|---|---|---|---|
| **15m** | 155,531 | 159 | +142.18R | +0.894 | 0.284 | 5.61 | 39.6% |
| **30m** | 77,784 | 106 | +94.70R | +0.893 | 0.405 | 10.07 | 34.0% |
| 1H | 38,914 | 37 | −6.61R | −0.179 | 0.137 | 8.43 | 24.3% |
| 4H | 10,180 | 9 | −3.99R | −0.443 | 0.163 | 3.99 | 0.0% |

The 15m row is the control and reproduces the documented baseline to the cent. **Above 30m the
edge does not weaken, it INVERTS.** The 30m row posts the same average per trade as the shipped
bot to three decimals, which is why it needed refuting rather than celebrating.

## 🔴 The 30m is NOT a second strategy — it is this bot through a coarser lens

`backtest/tools/tf_overlap.py`, with the A+/B-LEG pair as the yardstick:

| | 15m vs 30m | A+ vs B-LEG |
|---|---|---|
| shared in-market time | **37.0%** of A's | 0.5% |
| of that, SAME direction | **95%** (1,242 of 1,305 hrs) | 1 bar of 49 |
| same-direction entries within 4 hrs | **39** | 0 |
| closest pair | **0 minutes apart** | — |
| monthly R correlation | **+0.613** | +0.172 |

Stacking it concentrates risk on the same swings instead of spreading it, and it would sit on the
account risk cap constantly rather than rarely. ⚠ **It is no good as a REPLACEMENT either**: same
average R, fewer trades, drawdown **5.61R → 10.07R**.

⚠ **`overlap_audit.py` structurally could not have answered this and would have looked like it
could** — it works in bar INDICES over ONE frame, and an index is a different amount of time on
each side of a timeframe pair. `tf_overlap.py` measures on the trades' own `entry_ms`/`exit_ms`
clock instead. **Before comparing two runs, check they share an axis; a bar index is not one
whenever the bar size can differ.**

## What was NOT measured

- **Daily order blocks.** `--block-tf 1440` failed — D1 is not cached and the MT5 terminal was not
  answering. Resampling M15 locally would need the 18:00-NY trading-day boundary, not UTC
  midnight, or it is a different daily bar from the broker's.
- **Blocks as a TARGET or an exit**, rather than an entry. Every angle above asks where to get in.
- **Block QUALITY gates** (displacement size, ATR height, unmitigated, age). All seven angles treat
  every block as equal. ⚠ Given angle 7's result at two timeframes, the prior on this is poor.
- **The 30m variant with its own tuning.** It was run at the 15m bot's shipped defaults. The
  overlap result makes this moot for stacking, so it is recorded rather than recommended.
- **Costs.** Both runs are free-book, matching every baseline here. A higher timeframe holds longer
  and pays more swap, so charge before quoting a 30m figure anywhere else.

---

# Run 17 — 2026-08-11 — **THE BREAKEVEN EXIT IS NOT BREAKEVEN. Widening it costs 5R for every 1R it rescues.**

Aaron's theory, from memory of an earlier session and worth quoting because both halves turned out
to be half right: *"my drawdown is as big as it is because I'm compounding losses more than ten
percent, and I attribute that to swaps I'm paying on long-hanging losing trades. Also a thirty gap
is not enough to break even on trades for a standard account… make sure we are truly breaking even
and not just running negative thinking we're breaking even."*

`exec_be_buf_tk` is **30 ticks = $0.30**. The measured PU Prime Standard spread is **$0.32**. So the
buffer the strategy calls breakeven is smaller than the spread on the account the live bot is
currently on, and **~26% of all trades exit on exactly that stop.** The question is a good one.

Tools: `backtest/tools/scratch_audit.py` and `backtest/tools/swap_audit.py`, both new.

## The scratch cohort really does go negative

155,531 M15 bars (2020-01-01 → 2026-08-03), one real replay per row, `bid_ask_fills` + swap +
commission. A **scratch** is classified on the PRICE MOVE — an exit between 0 and 1.5× the buffer in
the favourable direction — never on the money, because sorting by profit would put the negative ones
in the loss bucket and return "all scratches are positive" by construction.

| account | scratches | mean R | total R | net negative |
|---|---|---|---|---|
| free (no costs) | 42 | **+0.034** | +1.44 | 0 of 42 |
| Standard | 41 | **−0.014** | −0.56 | **12 of 41 (29%)** |
| Prime | 41 | −0.023 | −0.94 | 12 of 41 |
| ECN | 41 | −0.017 | −0.71 | 12 of 41 |

**Confirmed: on every account that can actually be opened, this cohort is a net loss.** Free-book
runs report it as a small gain, which is where the false sense of "flat" came from.

## 🔴 But it is the SWAP, and it is the LONGS — the spread never touches these trades

The gross move per unit on a scratch is **+$0.298 to +$0.300 on every tier including the free
control** — identical. The spread does not appear at all, and the reason is the same limit-order
asymmetry recorded in `CLAUDE.md` → *Layered costs*: **the entry limit fills at the price it names
and the stop fills at the price it names.** A spread changes WHICH trades happen, not what a scratch
nets. The premise ("a 30-tick gap can't cover a 32-cent spread") is arithmetically true and
describes a cost this strategy does not pay.

What it does pay is swap, and the direction split is the finding. On Standard, where commission is
$0.00 and bar-mode slippage is 0, `Trade.costs_usd` is **pure swap** with nothing to disentangle:

| Standard scratches | n | mean R | net negative |
|---|---|---|---|
| **long** | 23 | **−0.052** | **12 of 23** |
| **short** | 18 | **+0.036** | 0 of 18 |

Gold charges longs (−79.60/lot/night) and PAYS shorts (+30.25). A scratch by definition **hung
around** — it ran to TP1 and came back — so longs pay for that time and shorts are paid for it.
**Aaron had the cause right and the cost wrong.**

Scale, which is what kills the fixed-buffer idea: **one night of long swap is $0.796 per ounce,
2.7× the entire $0.30 buffer**; a Wednesday rollover books three nights, $2.39, **eight times** the
buffer. Across the 35 longs that paid any swap the stop would have had to move a median **$1.59** —
**5.3× the buffer** — with a p90 of $3.98 and a worst case of $7.96.

## 🔴 Widening the buffer fixes the cohort and costs five times what it rescues

`exec_be_buf_tk` swept on a charged Standard book, one full replay per row:

| buffer | trades | total R | scratch n | scratch R | maxDD R |
|---|---|---|---|---|---|
| **30 ($0.30, shipped)** | 156 | **+141.87** | 41 | −0.56 | 8.36 |
| 60 ($0.60) | 156 | +135.70 | 44 | +0.58 | 8.29 |
| 100 ($1.00) | 156 | +134.44 | 46 | +3.29 | 8.54 |
| 160 ($1.60) | 156 | +114.81 | 52 | +8.56 | 7.80 |
| 240 ($2.40) | 156 | +117.00 | 58 | +15.27 | 8.61 |
| 400 ($4.00) | 156 | +105.97 | 67 | +30.80 | 8.48 |

**The scratch problem is completely solvable — −0.56R → +30.80R — and total R falls 141.87 → 105.97
doing it.** The exchange rate is roughly **5R lost per 1R of scratch rescued**, and it is monotonic.
A stop further into profit protects the trades that were coming back AND stops out the trades that
were running, and the runner is where this strategy's money is (Run 8: >100% of net in every window).
**30 ticks is already the best value in the table.**

## Why the DYNAMIC version is worse than the fixed one, not better

Aaron's actual proposal was smarter than a fixed widening: move the stop at each rollover by the
swap just charged, so a breakeven exit is truly zero. **It aims at exactly the wrong trades.** Only
positions held OVERNIGHT pay swap, and the positions held overnight are the runners — so a
swap-driven ratchet tightens the stop precisely on the trades the sweep above says to leave alone,
while doing nothing at all to the half of the book that closes same-day (median nights held: **0**,
p90 3, max 11).

**Ceiling on what it could recover: +2.11R** over 6.5 years (the swap paid by the scratch cohort —
the only trades a stage-1 ratchet can move without touching something still at risk). Against a
run-to-run spread of **sd 15.06R**, and against an exchange rate that has cost 5R per 1R everywhere
it has been measured. ⚠ **That +2.11R is an UPPER BOUND, not a forecast** — the same shape of cheap
estimate got its SIGN wrong on the minimum-stop guard (+1.84R estimated, −1.84R replayed).
**NOT BUILT. Do not build it without re-reading this row.**

## The other half — "losses compounding more than 10%" is real and tiny

At `exec_risk_pct = 10` a full loss should be exactly −1.000R.

| account | full losses worse than −1.000R | worst | total excess |
|---|---|---|---|
| free | **1 of 49** | −1.98R | +0.98R |
| Standard | 4 of 48 | −1.98R | +1.13R |
| Prime | **44 of 44** | −2.02R | +1.71R |
| ECN | **44 of 44** | −1.99R | +1.30R |

**The −1.98R trade is a GAP through the stop** — it costs $0.00 in fees and is present on the free
book too, so no cost model and no stop rule can recover it. That single trade is a ~20% equity hit
and is almost certainly what Aaron noticed.

🔴 **Standard's losers carry a swap CREDIT (+$71.92 mean), not a charge** — losers here die fast
(median 2.0h, Run/time-stop section) and are short-heavy, so they never accrue swap. **The
swap-on-losers half of the theory does not hold.** Prime and ECN put every loser past −1R purely on
COMMISSION, which is charged whatever the stop is and which no stop move can recover.

**Total excess across the whole history is 1.0–1.7R.** That is not what builds a −54.9% drawdown.
Run 6's verdict stands: the drawdown is a losing STREAK at 10% risk, and risk % is the only lever
that moves it.

## 🔴 And the longs EARN their swap, so do not cut them

The obvious reading of an 8.93R long swap bill is that longs are the problem:

| side | n | gross R | swap R | net R | net R/trade |
|---|---|---|---|---|---|
| **long** | 70 | +73.11 | **−8.93** | +64.18 | **+0.917** |
| **short** | 89 | +69.07 | **+2.33** | +71.40 | +0.802 |

**Longs out-earn shorts per trade after paying all of it.** Any rule that shortens long holds — a
direction-split time stop, a flat-by-close on longs only — is cutting the better side. This is the
same result `## Deliberate deviations` records for `flat_by_close`, which inverts the long side
entirely (+70.96R → −12.10R) to save 6.4R of swap.

## Verdict

**No change to the strategy.** The bleed is real, it is ~1R over 6.5 years, and every fix measured
costs more than the bleed.

✅ **The thing that actually helps is the ACCOUNT, and it needs no strategy change: switch to PU
Prime ECN.** Worth **+9.5R** against Standard over the same window (Run: `cost_tiers.py`;
`docs/BROKER_QUESTIONS.md`), which is five times the entire scratch problem.

## What was NOT measured

- **A stage-1-only swap ratchet, replayed.** Only its ceiling was computed. If it is ever built, it
  must be a replay — the ceiling is arithmetic over a finished trade list and this file records two
  occasions where that got the sign wrong.
- **A direction-split buffer** (wider on longs, unchanged on shorts). The sweep moved both sides
  together. ⚠ The prior is poor: the long scratches are the ones being rescued and the long runners
  are the ones being cut, so both effects land on the same side.
- **The buffer on an ECN book.** Swept on Standard, which is what the live bot trades today.
- **Buffer values between 30 and 60.** The sweep starts at the shipped value and the first step
  already costs 6.17R, so a finer grid would only locate a peak that is already known to be at 30.
- **Anything below 30 ticks.** A narrower buffer moves the stop toward the entry, which is the
  direction the wrong-side-stop-fill limitation lives in.

---

# Run 18 — 2026-08-16 — **`exec_sl_deep` costs 24R and does not interact with the secondary. Leave it OFF.**

**The question.** `exec_sl_deep` (an entry filling at or deeper than 0.786 puts its stop at the leg
origin instead of `exec_sl_level`) shipped OFF on 2026-08-02 and had **never been swept**. The exit
ladder register said *"Measure it."* Aaron asked for it measured together with `exec_secondary`,
because the 1m re-entry changes which entries fill deep.

## How it was measured

Four full replays, one per cell of the 2×2, **all on ONE window: 2018-09-14 → 2026-08-14**
(186,910 M15 bars + 2,799,088 M1 bars), `fill_model="bar"` (zero costs), shipped defaults otherwise,
`run_dual` so the 1m secondary is genuinely live. Script: `dual_2x2.py` pattern —
`StrategyCls(config=replace(cfg, exec_sl_deep=…, exec_secondary=…)).run_dual(df15, df1m, warmup=1000)`.

⚠ **The window is 2018-09-**14**, not the M15 floor of 2018-09-13**, because the M1 cache starts a day
later and every cell must see the same bars. That one day is worth **1 trade and 1.1R** — see the
rule-11 note below before comparing anything here to a figure elsewhere in this file.

## Result — the full 2×2

| `exec_sl_deep` | `exec_secondary` | trades | **sum R** | maxDD (R) | secondary trades | secondary R |
|---|---|---|---|---|---|---|
| **OFF** | **ON** *(shipped)* | 189 | **+164.4** | −5.5 | 8 | +25.5 |
| ON | ON | 192 | +140.4 | −4.8 | 9 | +24.5 |
| OFF | OFF | 181 | +138.9 | −5.6 | 0 | — |
| ON | OFF | 183 | +115.9 | −4.7 | 0 | — |

**The effects are additive and the interaction is noise.**

| effect | measured at | delta |
|---|---|---|
| `exec_sl_deep` ON | secondary ON | **−24.0R** |
| `exec_sl_deep` ON | secondary OFF | **−23.0R** |
| `exec_secondary` ON | sl_deep OFF | **+25.5R** |
| `exec_secondary` ON | sl_deep ON | **+24.5R** |

1.0R of interaction against this strategy's measured run-to-run spread of **sd 15.06R**
(`jitter_audit.py`) is nothing. **The two levers can be reasoned about separately.**

## What it means

🔴 **`exec_sl_deep` stays OFF.** It buys 2–3 extra trades and ~0.8R of drawdown and pays ~24R for
them. The mechanism is the one Run 11 already named from the other direction — **the targets are
fibs and do not move, so a wider stop makes every winner worth fewer R while every loss is still
−1R.** This is the first direct measurement of the SHIPPED narrow version (0.786-and-deeper only);
the 2026-08-02 revert that `mpc_strategy.pine` records was of a WIDER version that also caught 0.702.
Two independent measurements, same answer.

✅ **The shipped configuration is the best of the four**, which was not guaranteed going in.

⚠ **Deep-ON genuinely does hold a shallower drawdown in both rows** (−4.8 vs −5.5, −4.7 vs −5.6). If
drawdown per R ever becomes the objective this is not worthless — it is simply very expensive.

⚠ **The secondary's +25.5R rests on 8 trades**, and Run 12-era analysis of that feature already found
its value concentrated in one 2023 fill. Nothing here re-opens that; the secondary was held at its
shipped default and measured as a factor, not re-litigated.

⚠ **Zero costs.** The MT5 agent was unreachable, so tick fills were unavailable. Same fill model as
every other run in this file, so these numbers are comparable to the rest of it — but the costed
confirmation was NOT run.

## 🔴 The methodology finding, which outlived the result

**`backtest/tools/run_report.py` could not replay `exec_secondary` at all, and said nothing.** It
calls `strategy.run(df15)`; the secondary fills on 1m bars via `run_dual`. The first pass of this
2×2 was run through that tool and returned **byte-identical trade lists for secondary ON and OFF** —
which reads as a clean finding (*the 1m re-entry never fires here*) and was not one.

**Byte-identical is what "no secondary signals fired" looks like AND what "the 1m feed was never
wired" looks like.** Root rule 1, arriving through a replay path instead of through a null.

⚠ **Therefore: every figure in this file produced by `run_report.py` at the default config is a
PRIMARY-ONLY book**, because `exec_secondary` defaults **True**. They remain valid as MATCHED SETS —
each combo in a sweep was missing the secondary equally, so rankings hold — and they understate
absolute totals. Fixed the same day (the tool now loads the 1m frame, refuses what it cannot replay,
and prints the secondary count); full record in `backtest/docs/BACKTEST_BUILD_NOTES.md` →
*The secondary that never ran*.

🔴 **And the verification pass caught a rule-11 slip in this run's own write-up.** The first draft
quoted the secondary's value by pairing a dual run (from 09-14) against a 15m-only run (from 09-13)
— two different windows. Confirmed by re-running the 15m-only path pinned to 09-14: **181 trades /
+138.9R, matching the dual `secondary=False` cell exactly.** That single check verified both the
window explanation AND that `run_dual` with the secondary off is equivalent to `run()`.
**The M15 and M1 cache floors differ by one day, so any 15m-vs-dual comparison on this symbol
crosses windows unless both are pinned to the later date.** Nothing warns.

## What was NOT measured

- **Costs.** No tick fills; the agent was down.
- **`exec_sl_deep` at any other boundary.** 0.786 is the shipped threshold and it has already been
  wrong twice in the other direction (see `mpc_strategy.pine` ~line 509). This run holds it fixed.
- **`exec_sl_deep` combined with `exec_sl_level` other than 0.886.** The toggle is inert at 1.0 by
  construction; the shallower levels are unsupported (Run 4 / Run 11).
- **Whether 0.886 should become a snap target.** Related and separate — `_fib_snap` excludes it
  unconditionally, and `exec_sl_deep` would make it geometrically legal. A scan over the same
  history found **132 of 386 setups (34.2%) saw a gap wholly inside 0.786–0.886**, so the
  opportunity is not negligible. It is a CODE change on both sides plus a re-parity, not a sweep.

---

# Run 19 — 2026-08-16 — 🟢 **SCALE-IN. +65% on a costed book, and the losing column barely moves.**

**The question.** Aaron asked what exit families exist beyond the fixed TP1/TP2 + % runner trail.
Three were proposed; two closed NEGATIVE the same day and are recorded below so they are not
re-tried. The third — **adding SIZE to a runner the trail is already protecting** — is the first
ADDITIVE lever ever measured on this bot. Every family swept before it was protective (Run 8 killed
~50 tightening variants, Run 9 rejected banking in every form), and a grep for pyramid/scale-in
across the repo returned nothing.

## The rule

```
locked   = (stop - entry) * base_qty     profit the stop already guarantees
per_unit = (price - stop)                what one extra unit risks to that SAME stop
add_qty  = min(locked / per_unit, base_qty * exec_scale_cap_x)
```

Stop out right after adding and the two cancel — the base banks `locked`, the add gives back at most
`locked`. **An add can shrink a winner; it cannot manufacture a loser.** The guarantee is arranged in
advance by SIZE, never detected in real time, which is why no "get out of the late entry" rule is
needed.

🔴 **The trigger is the TRAIL (stage 2), not a target, and that is what makes it self-regulating.**
At TP2 the stop is only at TP1, so `locked` is small while `price - stop` is large and the affordable
add is a rounding error — the idea looks worthless if you test it there. Once the trail ratchets up
near price the same arithmetic permits a LARGE add. A trending runner buys size; a stalling one buys
nothing. **A ratchet check refuses the next add until the trail moves past the stop the last one was
sized against** — without it a stalling runner re-adds every bar against the same locked profit and
spends the guarantee several times over.

## How it was measured

Two stages. **Stage 1** a shadow ledger layered on an untouched replay (fast, used to search the
2×2 of adds × cap). **Stage 2** the real implementation, replayed end to end. Both on **XAUUSD 15m,
2018-09-13 → 2026-08-14**, `warmup=1000`, `exec_secondary=False`, and stage 2 with **PU Prime ECN
costs charged** (`PROFILES["puprime_ecn"]`, commission $1.00/side/lot, measured spread $0.12,
`bid_ask_fills=False`). Scripts: `scale_in.py`, `scale_in_costed.py`, `verify_scale_in.py`.

## Result — costed, PU Prime ECN

| | trades | **total R** | maxDD (R) | won | scratch | **losers** | worst | best | ret/DD |
|---|---|---|---|---|---|---|---|---|---|
| **off (shipped)** | 182 | **+128.26** | 6.03 | 70 | 47 | **65** | −2.06 | 24.64 | 21.27 |
| 2 adds, cap 1.0x | 182 | **+211.59** | 8.72 | 50 | 65 | **67** | −2.06 | 57.75 | **24.26** |
| 3 adds, cap 1.0x | 182 | +233.04 | 12.45 | 48 | 66 | 68 | −2.06 | 69.63 | 22.99 |

**Free of costs the same pair is 140.00R → 224.84R with the losers BIT-IDENTICAL** (62, −60.19R,
worst −1.98R), ret/DD 24.94 → 31.70. With costs "exactly zero" becomes slightly negative, which is
the 65 → 67.

🔴 **The affordability test is the whole feature, and dropping it is what proves it.** A naive
variant that ignores `locked / per_unit` and adds a flat 1x cost **8–13 extra losing trades**
depending on the cap. **The worst trade is unchanged at −2.06R in every safe row** — the rule does
what it claims.

⚠ **Trade count is identical at 182 in every row**, so the one-position-slot queue effect did not
fire. An add does not consume the slot; it enlarges a position already in it.

⚠ **2 adds is the pick on return-per-drawdown, not on total R.** 3 adds makes 21R more and gives
back 3.7R more drawdown.

## Verified two ways

✅ **The OFF path is BIT-IDENTICAL to the costed control measured before the feature existed** —
128.26R / 6.03 maxDD / 65 losers / −2.06R worst, all four. On a LIVE strategy this is the check that
matters: a toggle whose OFF path moves the numbers has changed the shipped bot whatever its default
says.

✅ **ON at 2 adds reproduces the harness figure the decision was taken on: 211.59R vs 211.59R,
diff −0.00R.** ⚠ **This was PREDICTED TO DIVERGE and did not, and the reason is worth keeping: R is
scale-free.** Per-trade R is `pnl / risk_usd` with `risk_usd` frozen at entry, so scaling the
position leaves R unchanged — the equity-path compounding that was expected to separate the two
cannot show up in the R column. **The R numbers are trustworthy; dollar totals cannot be read off
them.**

## What is NOT settled

🔴 **THERE IS NO STRUCTURAL TRIGGER IN IT AT ALL** (Aaron, same day: *"I don't know what market
structures I'm looking at to add into"*). The rule asks only *can I afford this*, never *is this a
good place*. Structure enters INDIRECTLY — the trail is parked on the last confirmed swing, so an add
fires roughly when a new HL/LH confirms — but that is a side effect of the trail's anchor rather than
a rule anyone chose, and **it enters at MARKET on the bar the trail moves, which is the worst price
of the leg**, where the base entry rests a limit in a discount zone and waits. Three untested
alternatives: add on a fresh BOS, add on a retest of the broken level, or rest a limit at the new
leg's retrace. **Location has never been varied — this is the next thing to measure.**

🔴 **NO PARITY GATE HAS RUN.** The Pine is built (`execScaleIn` / `execScaleAdds` / `execScaleCapX`;
`pyramiding` raised 0 → 4, which is compile-time and cannot be an input), but there is **no `cfg_*`
column for any of the three**, so `compare_strategy.py` cannot configure a scale-in run and would go
green while comparing two different strategies — the exact shape this file records from
`execRunnerTrail` (2026-07-26), `cfg_min_stop` (2026-07-30) and `eqExemptFvg` (2026-08-06). **An ON
result is a LAB finding until the columns land and a fresh export is diffed.**

⚠ **No account-level cap exists.** Net risk-to-stop is ≤ 0 by construction, but margin and
`run_stack`'s risk budget both see the FULL position. **Must not go live before the allocator**
(`docs/LIVE_TRADING_PIPELINE.md` → G10).

⚠ **The guarantee holds to the STOP, not through a GAP.** Price jumping past the stop fills the whole
combined size at the open, and 3x the size loses 3x.

## The two families that closed NEGATIVE the same day

**ATR-based stop DISTANCE — REJECTED.** Aaron's own idea, and he asked for it on the stop from the
beginning rather than only on the runner. Control **140.00R / 5.61 maxDD / ret-DD 24.94**; the best
pure ATR variant (2.5×) is **105.08R / 8.59 / 12.23**. 🔴 **The decisive row is `atr 3.0×`: median
stop $9.27 against the control's $8.92 — essentially the same DISTANCE — yet 86.27R against 140.00R,
with a near-identical outcome mix (69 winners both) and median winner 0.89R against 1.26R.** So it is
not the width of the stop that pays. **The fib LEVEL is doing work as a LOCATION, not as a distance**
— which contradicts what this log twice named as the only remaining route on stop placement. Floor
variants (−2R to −10R) are all inside the 15.06R jitter. ✅ The minimum-stop guard worked as designed
throughout (113 trades refused at k=0.5), so Run 4 did not repeat.

**REGIME filtering — CLOSED, and it needed no new code.** `run_report.py` already tags every trade
with the canonical `engines/regime` classifier at entry. **163 of 182 trades are TRENDING**, 18
TRANSITIONING, 1 UNKNOWN — so the accuracy question Aaron raised is moot at this split: 90% of the
book is one bucket. The differing bucket is **profitable** (+0.32 avgR, +5.7R), so filtering it costs
money, and 5.7R is inside the jitter anyway. **Read it as: the A+ setup already selects for
trending.** Session splits harder (London 51% / 1.00 avgR on n=43 against Asia 33% / 0.48 on n=45),
but Asia is still +21.6R, so there is nothing to cut there either.

**The pattern across all three families, and it is the same one Runs 6 and 12 found: every subgroup
of this book is profitable and every exit variation left the LOSING column untouched. There is
nothing here to filter — the only lever that moved anything was the one that added size to what
already works.**

---

# Run 20 — 2026-08-17 — 🔴 **VOID. Every number below was measured on a broken fill model. See Run 21.**

> 🔴 **DO NOT QUOTE ANY FIGURE IN THIS ENTRY.** The harness booked each add at the price its RULE
> TRIGGERED on, and Pine buys it somewhere else — a market order fills at the NEXT bar's open, a
> resting limit fills when price comes back. That handed `BOS retest` the retest level itself on
> every fill, which is exactly the price that mode has to WAIT for and frequently never gets. It
> ranked first here on that. **On the corrected fill the ranking INVERTS and `BOS retest` loses
> money outside 2020 at every budget above one add** (Run 21).
>
> ⚠ **The entry is kept rather than deleted, because the failure is the useful part.** The parity
> gate caught it on 2025-10-21 (py 27.07R vs pine 22.03R) — nothing in this write-up looked
> wrong, the grid was internally consistent, and the depth gradient it reports is still real.
> **A backtest that prices a fill at the moment its rule fired is measuring a DECISION, not a
> TRADE**, and no amount of reading the output can show you that.

**Original heading:** *WHERE a scale-in adds. "BOS retest" ships; the sweep's own winner was 80% one year.*

**The question.** Run 19 shipped the SIZE rule and left the LOCATION unexamined — the add fires at
MARKET on the bar the trail happens to move, which is the worst price of the leg. Aaron: *"I don't
know what market structures I'm looking at to add into."* Fifteen locations were tested, his and
mine.

## How it was measured

One replay per variant, **XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN costs**, `warmup=1000`,
`exec_secondary=False`. Two controls on every table: `off` must print 128.26R and the shipped market
rule must print 211.59R. Both reproduced to the cent in every run below, which is what says the
harness never moved the base strategy. Scripts: `scale_where.py`, `scale_sweep.py`,
`scale_validate.py`, `scale_ceiling.py`.

🔴 **THE FIRST TABLE WAS PINNED AT 2 ADDS / CAP 1.0x AND THAT MADE IT THE WRONG EXPERIMENT.** A cap
that does not bind a rule firing 91 times strangles one firing 8 times, so it measured FREQUENCY and
read as quality. Re-run at 4 adds / cap 3.0x, which no rule here can exhaust.

## Result — the fair fight

| variant | total R | maxDD | ret/DD | fills |
|---|---|---|---|---|
| **fib 23.6%** | **302.39** | 9.50 | **31.83** | 51 |
| FVG | 191.23 | 6.37 | 30.02 | 26 |
| BOS retest | 273.02 | 9.10 | 29.99 | 65 |
| fib 38.2% | 261.19 | 9.25 | 28.23 | 37 |
| fib 50% | 184.24 | 8.75 | 21.05 | 30 |
| fib 61.8% | 113.88 | 7.78 | 14.63 | 20 |
| fib 78.6% | 119.76 | 7.06 | 16.97 | 18 |
| market (shipped) | 280.62 | 20.97 | 13.38 | 126 |
| pullback 1.0 ATR | 399.60 | 20.80 | 19.21 | 128 |
| off | 128.26 | 6.03 | 21.27 | — |

🔴 **DEEPER IS WORSE, MONOTONICALLY, AND THIS IS THE FINDING WITH A MECHANISM.** 23.6% → 38.2% →
50% → 61.8% → 78.6% falls 302 → 261 → 184 → 114 → 120, and the last two are **below not scaling at
all** (R/add −0.72 and −0.47). A deep pullback means the runner has already handed the move back —
the add lands on a dying trade just before the trail stops it out. ⚠ This reverses the prediction
written down before the run: `add_qty = locked / (price − stop)` means a deeper fill permits a
BIGGER add, so deep was expected to win. It does buy more size; it buys it into failure.

## 🔴 The winner was an artefact, and only the PER-YEAR test caught it

**2020 is 175R of fib 23.6%'s 302R.** Excluding 2020 and scoring each against no scaling:

| | gain, 2020 removed | years beating `off` |
|---|---|---|
| **BOS retest** | **+56.5R** | 5/9 |
| market (shipped) | +41.7R | 5/9 |
| fib 23.6% | +35.0R | 4/9 |
| FVG | +24.4R | 3/9 |
| fib 38.2% | +7.2R | 2/9 |

The ranking inverts and **fib 23.6% falls below the rule already shipped**. fib 38.2% is 95% one
year. ⚠ **THE HALF-SPLIT PASSED EVERYTHING AND WAS USELESS HERE** — 2020 sits inside the first half,
so the coarser robustness check this log has relied on twice could not see it. **Run the per-YEAR
split before believing a sweep's top row; the halves are not enough.**

## Where it tops out

Adds saturate: 4 → 65 fills, 6 → 69, 8 → 71, and 12 and 20 are identical to 8. ⚠ **But 2020-free R
PEAKS AT 4 AND FALLS**: 4 adds 185.06R, 6 and 8 both 175.16R. **Adds 5-8 pay only in 2020 and cost
~10R everywhere else.** The cap never stops helping in-sample (1x → 8x keeps climbing, drawdown flat
at 9.10 above cap 3.0) — **which is exactly where the backtest is blind, so it is NOT shipped at the
cap it likes**: the affordability rule guarantees only down to the STOP, and a gap straight through
it loses on the whole stacked position, ~33x base size at 4 adds × 8x.

## 🔴 The bug that made two modes inert, and why the numbers above had to be taken twice

The first build resolved the adds' target from the **live** bar. Verified against it, `"Prev day
H/L"` and `"H4 H/L"` returned **194.15R — byte-identical to `Ride`**, meaning they banked **zero
times in eight years**.

The obvious theory (the levels are never there) was wrong, and counting said so: daily **resolved
1,804** valid targets and banked 0; H4 **resolved 2,438** and banked 0; weekly resolved 2,390 and
banked 11. The targets existed, stood unmitigated, and sat beyond the newest add. They just never
filled.

**The cause is an interaction between two correct components.** A daily or H4 level is mitigated by
a **WICK** (`SWEEP_HIGH` / `SWEEP_LOW`), and `stack.step(bar)` runs **before** the strategy sees the
bar. So on the exact bar price reached the level, the engine had already flagged it mitigated and
the target evaluated to `None`. **The order disappeared precisely on the bar that would have filled
it** — every time, for eight years.

🔴 **WEEKLY WAS IMMUNE, AND THAT IS THE PART WORTH KEEPING.** A week level is mitigated by a
**CLOSE** through (`BREAK_HIGH` / `BREAK_LOW`), so it survives the spike that fills it and banked
normally. The default mode — the only one anybody was looking at — was the one mode the defect could
not touch. **A feature verified on the option you are watching says nothing about the options you
are not**, and here it produced two shipped-looking modes that did nothing at all.

**The fix is not new machinery.** The target is now latched at the bar's close (`_add_tp_level`) and
filled against on the next bar — the same one-bar order delay the base ladder already honoured, and
what Pine does for free with `strategy.exit(..., limit=)`. The adds were the single path that
skipped it. `test_a_target_swept_by_the_filling_bar_still_fills` pins it, and reverting the fix
reddens that test and nothing else.

⚠ **Every structural figure in the first table was taken through a throwaway harness carrying the
same flaw**, so all of them were void — including the weekly row that agreed with the fixed code by
coincidence. ⚠ **The flat-risk control was NOT affected**: its target is a fixed price off the base
entry, with no level and nothing to mitigate.

## Shipped

`exec_scale_mode = "BOS retest"`, `exec_scale_max_adds = 4`, `exec_scale_cap_x = 2.0`.
**`exec_scale_in` is still False, so no documented figure in this package moves** — what changed is
what the toggle DOES. Pin `mode="Trail", adds=2, cap=1.0` to reproduce Run 19's 211.59R.

⚠ **THE CASE IS CONSISTENCY, NOT RETURN-PER-DRAWDOWN, and saying otherwise repeats the mistake this
run exists to record.** On the full book BOS retest is THIRD on ret/DD (29.99, behind fib 23.6% at
31.83 and FVG at 30.02) — and fib 23.6% is the row that was 80% one year. The 2020-free ret/DD was
never computed for the alternatives, so no claim that this wins it is supported. What it does win:
the 2020-free gain, the most years, losses under 3.3R in every year it loses, positive in all four
of the most recent years (fib 23.6% LOST money in 2025), and 9.10R drawdown against the market
rule's 20.97R.

⚠ **AND THE RISK-ADJUSTED GAIN AT THE SHIPPED CAP IS THIN**: 2020-free ret/DD 15.51 against 15.34
for not scaling. This buys more money for proportionally more drawdown. It is not a free lunch, and
the clear ratio win only appears at the caps that carry unpriceable gap risk.

## Two harness bugs, both caught before they became conclusions

🔴 **A DEAD FIELD READ THROUGH `getattr(..., False)`.** The internal-shift confirmation read
`snapshot.int_bull_break`, which lives on `InternalEvents` and not on the snapshot — so it answered
False on all 186,948 bars and Aaron's own design booked ZERO adds while reading as a strict rule
that had been tested and lost. Probed: the snapshot pair is 0/0 and the real fields fire 765/657
times. **Never `getattr` with a default in a check whose whole job is to notice absence** — the same
rule this file already records from the `exit_name` probe.

🔴 **AND THE ZERO THAT SURVIVED THE FIX IS STILL NOT A VERDICT.** After the field was corrected the
rule confirmed 0 times on 375 waiting bars. At the internal break's own base rate (0.380%/bar, one
direction) the EXPECTED count is **1.43**, and P(0) under Poisson is 24%. **Zero rejects nothing.**
The binding gate is not the confirmation anyway — the funnel is 79 BOS → 40 with a valid zone → **8
touched** → 0 confirmed, so the fib∩gap ZONE is what starves it. ⚠ **`fib AND gap` remains
UNMEASURABLE at 13 fills even on a generous budget, and `order block` at 7. Neither lost; neither
was tested.**

## Mine, tested alongside his, and reported the same way

**ATR pullback made the MOST money and is rejected** — 1.0 ATR is 399.60R, top of the table, at
20.80R drawdown against 6.03R for doing nothing. Per unit of drawdown that is 19.21, **worse than
not scaling at all** (21.27). It also adds 11 losing trades and pushes the worst trade to −2.98R.
**New-high momentum is not a distinct idea**: 279.76R on 126 fills against the market rule's 280.62R
on 126 — when the trail ratchets, price is usually making new highs, so it is the same rule renamed.

**The standing lesson is the one the per-year table taught: a sweep hands you the row that scored
best under the metric you wrote down, on the window you happened to have. The depth gradient
survived every cut because it is five rows moving one way with a mechanism under it. The single
best row did not survive one extra question.**

---

# Run 21 — 2026-08-18 — 🔴 **The fill model was wrong, every Run 20 number is void, and the ranking inverts.**

**The question was not a new one.** Run 20 had already answered *where should a scale-in add?* and
its answer — `BOS retest`, shipped as the mode default the same day — was produced by a harness
that priced each add at the moment its RULE FIRED. That is not where Pine buys it. This run asks
the same question of code that matches the Pine bar-for-bar.

## What was wrong, and why nothing in the output showed it

The Pine issues an add as `strategy.entry(qty = ...)`. With no `limit`, that is a **market order**,
and TradingView fills a market order at the **next bar's open**. Run 20's harness — and the first
Python implementation — booked it at the trigger price on the trigger bar.

For `Trail` that gap is small: the trigger is `close`, and the next open is usually right beside it.
For `BOS retest` it is enormous. That mode's whole premise is *wait for price to come back to the
level the break cleared* — so crediting it with the level itself, on every fill, credits it with
precisely the price it must wait for and frequently never gets.

🔴 **THE PARITY GATE CAUGHT IT, AND NOTHING ELSE COULD HAVE.**

```
bar 1356  2025-10-21 15:00  px_closed_r:  py=27.068367  pine=22.032799
```

One trade, 5R apart, on the largest runner in the book. Every decision field before it agreed. The
equity curve, the trade list and every R figure were internally consistent on both sides of the
bug — **a backtest that prices a fill at the moment its rule fired is measuring a DECISION, not a
TRADE, and no amount of reading the output can show you that.**

## What was fixed

| | before | after |
|---|---|---|
| `Trail` | sized at `close`, booked at `close` | sized at `close`, **filled at the next bar's open** (it is a market order) |
| `BOS retest` | sized at the level, booked at the level | **rests a real limit** at the level; fills when price returns, or better on a gap through |
| `lAddN` / add count | incremented at PLACEMENT | incremented at the **FILL** — a resting order can sit unfilled for many bars |
| add exits | placed once `lAddN >= n` | placed unconditionally, so a limit that fills mid-bar is never unprotected |
| stale orders | none | **cancelled when the trade ends** — a limit outlives the position that placed it |

## The guarantee broke, and that is the finding under the finding

The affordability rule promises an add can shrink a winner but never create a loser. That
arithmetic is written against the price the add is BOUGHT at. A market order is sized at one price
and filled at another, so whatever moves against you in between is size the guarantee never covered.

**MEASURED, over the same 182 trades, un-scaled worst −2.06R:**

```
market-order add (sized at trigger, filled next open)   worst −2.50R   2 trades breached
  +3.41R  →  −2.50R
  +1.34R  →  −2.15R
resting limit                                           worst −2.06R   0 breached
```

Two winners turned into losers — the one thing the rule says cannot happen. The resting limit
closes it: the fill price is known before the order is sent, and price that GAPS through a buy
limit fills at the open, i.e. BETTER. Every error term now points the safe way.

⚠ **`Trail` is a market rule by nature and still carries a small version of the gap.** It measures
ZERO breaches at 3 adds and below, and **−2.24R / −2.73R at 4 adds** — which is why the shipped add
count is 3 and not 4. Zero observed is not zero possible.

## The grid, re-run

32 cells. Scored on the **2020-free** book, because 2020 is ~1/3 of the all-period figure and
scaling roughly TRIPLES its contribution — a grid ranked on the ALL column is ranking one year.
XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN costs, `exec_secondary=False`, `warmup=1000`.

```
                    ALL R    dd  r/dd    EX20 R    dd  r/dd    gain  worst
no scaling         128.26  6.03 21.27     92.51  6.03 15.34       -  -2.06
Trail  1 x 0.5x    155.90  7.15 21.81    104.63  7.15 14.64  +12.12  -2.06
Trail  2 x 0.5x    178.90  7.15 25.03    117.79  8.11 14.52  +25.28  -2.06
Trail  3 x 0.5x    194.15  7.24 26.81    124.05 10.34 11.99  +31.54  -2.06   <- SHIPPED
Trail  3 x 1.0x    233.01 12.46 18.71    145.48 17.02  8.55  +52.96  -2.06
Trail  3 x 2.0x    260.09 17.60 14.78    165.73 22.99  7.21  +73.21  -2.06
Trail  3 x 3.0x    266.57 18.53 14.39    166.40 24.56  6.78  +73.89  -2.06
Trail  4 x 2.0x    275.02 20.07 13.70    174.94 25.46  6.87  +82.43  -2.73
BOS retest 1 x 2.0x 137.01  6.58 20.83   101.36  6.58 15.41   +8.85  -2.06
BOS retest 2 x 1.0x 140.34  7.78 18.04    93.15  7.78 11.97   +0.64  -2.06
BOS retest 3 x 2.0x 161.90  9.20 17.60    82.50  9.20  8.97  -10.02  -2.06
BOS retest 4 x 2.0x 180.44  9.20 19.61    80.90  9.20  8.79  -11.62  -2.06
BOS retest 4 x 3.0x 193.38  9.27 20.85    78.36  9.27  8.45  -14.15  -2.06
```

### 1. `BOS retest` does not work

Every cell above one add is flat or **negative** outside 2020, down to **−14.15R against not
scaling at all**. Only 1 add scrapes positive and by less than the 15.06R jitter. It is kept as an
option because it is implemented, gated and parity-green — **not because anything supports it.**

The mechanism is the same one the bug was hiding: a limit only fills if price comes back. Structure
breaks and runs away often enough that most of these orders never fill, and the ALL column climbs
with add count purely because the few that do fill are 2020's.

### 2. The CAP is the drawdown lever, not the add count

Same 3 adds, cap alone: ex-2020 drawdown **10.34 → 17.02 → 22.99 → 24.56** across 0.5x / 1.0x /
2.0x / 3.0x. Adds are nearly free; SIZE is what hurts. The previous default of 2.0x sat on the wrong
side of that.

### 3. Ladder SHAPE does not matter — and the intuition behind it is wrong here

Aaron's proposal: each add smaller than the last (0.75x / 0.5x / 0.25x), because an add further from
the original entry is bought at a worse price and is therefore riskier. Tested at a FIXED 1.5x total
so only the distribution varies:

```
big first   0.75/0.5/0.25   ALL 199.27  dd 7.42   EX20 126.67  dd 11.04  r/dd 11.47
flat        0.5/0.5/0.5     ALL 194.15  dd 7.24   EX20 124.05  dd 10.34  r/dd 11.99
small first 0.25/0.5/0.75   ALL 183.96  dd 7.18   EX20 120.86  dd  9.05  r/dd 13.36
```

Big-first makes the most money and the spread is **inside the 15.06R jitter**, so the shape is not
measurable. Repeated at a 2.25x total (225.21 vs 218.22) with the same verdict.

🔴 **The premise is wrong, and the correction is worth more than the test.** Risk on an add is not
measured from the ENTRY — it is measured to the STOP, and the stop trails up behind price. By the
third add the stop is right underneath, so that add is the **cheapest** one, not the riskiest. The
data agrees: small-first had the LOWEST drawdown and the best ratio. Flat ships because it is
simpler and nothing measured argues against it.

### 4. The honest caveat

**No cell in the grid beats not-scaling's 2020-free return-per-drawdown of 15.34.** Scaling reliably
buys raw return and reliably pays for it in drawdown. `Trail 3 × 0.5x` is the cell where that trade
is closest to fair, and the only one better than baseline on **both** axes over the full book
(194.15R vs 128.26R at 26.81 vs 21.27 ret/DD). Quote both halves.

## What shipped

`exec_scale_mode` `"BOS retest"` → **`"Trail"`**, `exec_scale_max_adds` 4 → **3**, `exec_scale_cap_x`
2.0 → **0.5**, in lockstep across `config.py`, `mpc_strategy.pine` and `mpc_strategy_export.pine`.

⚠ **`exec_scale_in` is still `False`.** The OFF path is byte-identical at 128.26R / 6.03 maxDD /
worst −2.06R, so no other figure in this log moves. What changed is what the toggle DOES.

✅ **PARITY GREEN** — `compare_strategy.py` exit 0 on a fresh 20,799-bar export taken at
`cfg_scale_in=1 / cfg_scale_mode=1 / cfg_scale_adds=4 / cfg_scale_cap=2`, i.e. an export that
genuinely exercises the feature rather than reading all zeros. **The same gate on the same schema
was RED at bar 1356 before the fix**, which is what makes this green worth something.

⚠ **Still not live-capable.** `algos/live/bridge.py` refuses `exec_scale_in` outright — it mirrors
one entry limit and one ratcheting stop and has no path that places a second entry — and the
account-level allocator remains unbuilt (`docs/LIVE_TRADING_PIPELINE.md` → G10). Margin sees the
full stacked position even though risk-to-stop does not.

## The open question this did not answer

An add has no target. It rides the same trailing stop as the base, and the base earned that by
being a reversal bought at a discount after a sweep and a structure shift — an add has none of that
behind it. **Banking adds at a target, structural or otherwise, has never been tested.** The
liquidity engine already emits previous day/week levels and session highs and lows; the strategy's
execution layer reads none of it.

---

# Run 22 — 2026-08-19 — **THE ADDS HAD NO TAKE PROFIT. EVERY TARGET THAT GIVES THEM ONE LOSES TO RIDING.**

## The question, and why it was a fair one to ask

Scale-in lots had **no exit of their own**. They closed pro-rata whenever the base ladder banked a
rung, and otherwise rode the base trade's trailing stop. Aaron's objection: an add is bought late
and high, with almost none of the base entry's cushion, so a pullback should hand back what it just
made — and the natural fix is to bank it at a level that means something (previous day/week high or
low, H4, session extremes).

## Two independent target families, because one would not have settled it

**The control — bank at a flat multiple of the base 1R distance.** Deliberately not structural. If
riding beats a plain target at every distance, structure is unlikely to rescue it.

| bank the adds at | total | maxDD | ret/DD |
|---|---|---|---|
| no scaling at all | 128.26R | 6.03 | 21.27 |
| **ride — no target (shipped before today)** | **194.15R** | 7.24 | **26.81** |
| 1.0R | 126.76R | 6.00 | 21.14 |
| 2.0R | 130.84R | 6.48 | 20.19 |
| 3.0R | 134.19R | 7.15 | 18.77 |
| 4.0R | 136.00R | 7.15 | 19.03 |
| 6.0R | 141.24R | 7.24 | 19.50 |
| 8.0R | 135.82R | 7.24 | 18.75 |

🔴 **Banking at 1R is WORSE THAN NEVER SCALING AT ALL** — all the machinery, and it finishes behind
where it started. And the curve climbs monotonically toward the ride as the target moves further
away, which is the shape you get when the right answer is "no target".

**The structural test — the levels Aaron actually named.** Every level comes from
`engines/liquidity`, which builds each from a PREVIOUS completed period and never forecasts the
current day's or week's extreme. That is what makes any of this tradeable live.

🔴 **THE FIRST STRUCTURAL TABLE WAS WRONG AND IS VOID. These are the RE-MEASURED numbers**, taken
on the shipped code after the resting-order fix (see *The bug that made two modes inert*, below).
The harness that produced the first set resolved its target from the LIVE bar, so it described a
rule neither implementation uses — including the weekly row that happened to look right.

| bank the adds at | total | maxDD | ret/DD | banks | worst | excl. top 20 | its dd | ret/dd |
|---|---|---|---|---|---|---|---|---|
| scale-in OFF | 128.26R | 6.03 | 21.27 | — | −2.06 | 92.51R | 6.03 | 15.34 |
| **ride — no target** | **194.15R** | 7.24 | **26.81** | 0 | −2.06 | 124.05R | 10.34 | 11.99 |
| prev week H/L | 168.51R | 7.24 | 23.27 | 16 | −2.06 | 114.12R | 9.73 | 11.73 |
| prev day H/L | 157.57R | 7.51 | 20.97 | 25 | −2.06 | 111.91R | 7.72 | **14.49** |
| H4 H/L | 146.09R | 7.15 | 20.44 | 47 | −2.06 | 104.38R | 7.15 | **14.60** |

⚠ **VOID, never re-measured on the fixed code:** `daily + weekly` 174.35R, `daily + weekly + H4`
161.00R, `session H/L` 159.39R. None is a shipped option. Do not quote them.

## 🔴 The ORDERING is the finding, not any single row

Both tables sort by **how often the target fires**. Weekly levels sit far away and rarely bind, so
that row is nearly the ride. Session highs and lows are close and get hit constantly, so that row is
worst. Two unrelated target families, measured separately, produce the same monotonic curve. **The
adds earn on the handful of trades that run a long way, and every target truncates exactly those.**

⚠ **It rests on few events — 16 to 47 bank fills across the full eight years.** What carries the
conclusion is that **every configuration agrees and orders itself by the same mechanism**, not the
size of any one gap. ⚠ The flat-risk control is **unaffected by the bug** and still stands on its
own: its target is a fixed price off the base entry, so there is no level and nothing to mitigate.

🔴 **BANKING BUYS A SMOOTHER RIDE AND PAYS FOR IT OUT OF THE TAIL — the last three columns are the
honest case FOR a target, and they were not visible in the first table.** Strip the top 20 trades
and the ranking inverts on risk-adjusted return: prev day **14.49** and H4 **14.60** against Ride's
11.99, with drawdown falling 10.34 → 7.15. **On the ordinary book a target is genuinely better.** It
loses overall only because the extraordinary book is where this strategy earns.

⚠ **Drawdown on the FULL book barely moves** (7.15–7.51 against the ride's 7.24). Measured across
the whole sample, a target is not buying safety.

⚠ **The worst trade is −2.06R in all 16 configurations — identical.** That is the direct answer to
the concern that prompted the work. The affordability rule already sizes each add against its own
distance to the trailing stop, so an add can shrink a winner but cannot create a loser. There was no
giveback left for a target to prevent.

## A verification worth recording, because the null looked like a bug

`ALL structure` and `daily + weekly + H4` returned **byte-identical** numbers, which is what a scope
that never binds also looks like. Counting the events directly: session levels **do** bind — they
win the target pick 534 times — but they keep landing on the **same price** as a daily or H4 level,
because the previous day's high WAS set during some session. Adding them shuffles which family gets
credited (daily 346 → 56) without moving a single price. Real dominance, not a dead scope. ⚠ The
general point: **a scope that silently matches nothing reports as "no effect" and reads exactly like
"this does not help".**

## Shipped

**`exec_scale_tp_mode`, defaulting to `"Prev week H/L"` — Aaron's explicit call, AGAINST the
measurement.** He chose it wanting certain money on the runners rather than the best expectancy,
which is a legitimate preference. 🔴 **But the DEFAULT IS UNDER REVIEW, because he chose it on a
number the live-bar bug had made wrong: he was quoted a 4.38R gap said to sit inside this
strategy's 15.06R jitter, and the true gap is 25.64R — OUTSIDE it, and about 13% of total return.**
"Certainty for no measurable cost" is not the trade-off on offer. He has been told and has not yet
answered. ⚠ **Confirm before treating this default as settled.** Session H/L is not offered — worst
measured, and six more mirrored Pine variables to add.

⚠ **`"Ride"` reproduces 194.15R and scale-in OFF reproduces 128.26R exactly**, so nothing already
stored moves.

🔴 **NOT PARITY-GATED.** `cfg_scale_tp` is a new export column and no export carries it yet, so
`compare_strategy.py` has never checked this path. Rule 22 is unsatisfied until a fresh export lands
with the column present and the gate passes on it.


# Run 23 — 2026-08-19 — **THE SECONDARY, END TO END. THE ENTRY GATES ARE ALREADY RIGHT; THE EXIT LADDER IS NOT.**

**Three grids, 26 real replays, one question.** Part 1 loosens the ENTRY gates four ways and every
one is worse. Part 2 asks how many times a setup may be re-entered and what the re-entry's own exit
ladder should be — and finds the first change in this whole exercise that makes the small re-entries
profitable. Part 3 combines the two survivors. ⚠ **Read all three: part 1's conclusion ("nothing
helps") is true of the doors and false of the ladder, and stopping at part 1 was the wrong place to
stop.**

---

## Part 1 — the entry gates, loosened four ways. Every one is worse.

**The question, in Aaron's words:** *"I'm at a crossroad where I don't know if a secondary trade is
still valid sometimes when price hits my stop loss also. Let's say I got in at 0.618, price went
down, hit my 0.886, I literally swiped it, then came back, bounced on one of my higher fib levels
and then went. Now I just missed the whole trade."* So: **find the best confluence for a re-entry,
by running the loosened models.**

## What was loosened, and what it cost to ask

Three new config levers, all defaulting to the shipped rule so nothing historical moves:

| lever | default | what the looser values do |
|---|---|---|
| `exec_sec_require` | `"Breakeven"` | `"Any close"` (the primary traded, any outcome) · `"Stopped only"` (**the swept-stop case** — it closed without reaching TP1) · `"None"` (no primary needed) |
| `exec_sec_zone_deep` | `0.886` | `1.0` = arm while the 15m bar has closed BEYOND the entry band, which is the state a swept stop leaves behind |
| `exec_sec_zone_shallow` | `0.618` | `0.5` = arm after price has already reclaimed part of the move |

`Execution` grew the two latches the looser gates read (`prim_closed_sos_*`, `prim_lost_sos_*`),
latched at finalise off the trade's final `_stage`. Nothing else reads them, so parity is untouched.

## The grid — 9 real replays, 2020-01-01 → 2026-08-18, 156,543 M15 + 2,343,987 M1 bars each

Forked off one bar load, no costs (matching lab run `fbfc89d71fb4`). **The CONTROL reproduced that
stored run exactly — 160 primaries + 7 secondaries — which is what makes every delta attributable.**

| variant | trades | sec | book R | sec R | its best | **ex-best** | W/L | ddR |
|---|---|---|---|---|---|---|---|---|
| **control** (breakeven, .618–.886) | 167 | 7 | **374.17** | +78.26 | +79.07 | **−0.81** | 1/1 | −15.01 |
| any close | 174 | 14 | 373.49 | +77.58 | +79.07 | −1.49 | 3/5 | −16.09 |
| breakeven + deep zone 1.0 | 169 | 9 | 372.17 | +76.26 | +79.07 | −2.81 | 1/3 | −17.00 |
| no primary required | 176 | 16 | 371.66 | +75.75 | +79.07 | −3.32 | 3/7 | −18.01 |
| any close + deep zone 1.0 | 176 | 16 | 371.49 | +75.58 | +79.07 | −3.49 | 3/7 | −18.08 |
| any close + zone .5–1.0 | 177 | 17 | 369.28 | +73.37 | +79.07 | −5.70 | 3/9 | −18.07 |
| **stopped only** | 167 | 7 | 295.23 | **−0.68** | +2.07 | −2.75 | 2/4 | −16.00 |
| stopped only + deep zone 1.0 | 167 | 7 | 295.23 | −0.68 | +2.07 | −2.75 | 2/4 | −16.00 |
| stopped only + zone .5–1.0 | 168 | 8 | 295.20 | −0.72 | +2.79 | −2.79 | 2/4 | −16.00 |

🔴 **THE SHIPPED RULE WINS ON ALL THREE COLUMNS THAT MATTER — book R, ex-best R, and drawdown — and
the ordering is MONOTONIC in how much was loosened.** Every door that was opened let in trades that
lost. There is no cell where a looser gate paid for itself.

🔴 **The swept-stop re-entry, asked in isolation, is a LOSER: 7 trades, −0.68R, 2 wins / 4 full
−1.00R losses** (2021-03-15, 2024-08-26, 2025-02-19, 2025-12-15 all −1.000R). The two winners are
+1.32R and +2.07R. **So the pattern Aaron described is real — it happens seven times in 6.6 years —
and taking it systematically loses money.** The stop got swept because the setup was failing, and
re-entering is buying the same idea a second time at a worse place in its life.

⚠ **The zone-deep lever does NOTHING on top of "Stopped only" — 1.0 and 0.886 give the identical
book to the cent.** The swept-stop legs were never blocked by the zone; they were blocked by the
breakeven gate alone. **Two levers that sound like the same story are not the same lever, and
measuring them separately is what showed that one of them was inert here.**

⚠ **ZERO primaries displaced in any of the nine cells** (0 lost / 0 gained against control), so
none of this is the one-slot queue effect. The deltas are the re-entries themselves.

⚠ **The differences are inside this strategy's own run-to-run jitter (sd 15.06R), so no single
row's R is evidence.** What is not noise is the **direction** — nine of nine loosenings move the
same way — and the **win/loss counts**, which go 1/1 at the control to 3/9 at the loosest.

## The finding under the finding — the re-entries that DO fire mostly scratch

Read the control's own seven: **+0.05, −0.09, +79.07, +0.08, +0.10, +0.05, −1.00.** Four of the
seven land inside the ±0.15R scratch band, one is a full loss, one is a rounding error, and the
whole case is 2023-04-03. The looser cells inherit the shape: of "any close"'s 14, **eleven are
either ≈0 or exactly −1.00R.**

**So the secondary's problem is not only how OFTEN it fires — it is what happens after it fills.**
A 1-minute entry gets a 1-minute-tight stop and then hands the trade to the 15m structure trail,
which ratchets to breakeven long before a 15m target is reached. The re-entry is being ticked out
of its own scratch. **Entry confluence was the question asked and the answer is "none of the four
doors"; the untested question is the EXIT ladder for a 1m entry**, which no run in this log has
ever varied independently of the primary's.

### Part 1 shipped

**Nothing.** All three levers stay at their defaults, which reproduce the shipped book byte-for-byte.
They stay in the code because the question will be asked again and the answer should cost one run.

✅ 8 new tests in `tests/test_secondary.py`, **every one watched RED under 7 mutations** (the
breakeven branch forced true; an unknown mode falling through to true; the zone edges recomputed
instead of read; "Stopped only" and "Any close" reading the wrong latch; the deep edge pinned;
"None" refusing). 262 strategy + 27 backend runner tests green.


---

---

## Part 2 — how many re-entries, and what exit ladder. 10 replays, same bars, same control.

**The question, in Aaron's words:** *"What if this secondary re-entry also gets scratched? Up to what
number should we allow before settling into losses? Because at one point, if it keeps coming back,
that means it's probably a shift of structure that happened, and we should not take the re-entry."*

Four more levers, again all defaulting to the shipped rule:

| lever | default | what it does |
|---|---|---|
| `exec_sec_max_per_setup` | `1` | how many re-entries one setup may spend, read only while `exec_sec_once_per_setup` is on |
| `exec_sec_req_m1_dir` | `False` | on = only arm while the 1m structure already points the trade's way — the *"has structure shifted against me"* test, on the lower timeframe |
| `exec_sec_be_at` | `"TP1"` | `"TP2"` holds the re-entry's ORIGINAL stop through TP1 instead of ratcheting to breakeven |
| `exec_sec_tp1_pct` | `-1.0` (inherit) | the re-entry banks its own percentage at TP1, separately from the primary |

| variant | trades | sec | book R | sec R | its best | **ex-best** | W/L | ddR |
|---|---|---|---|---|---|---|---|---|
| 1m trend must agree | 165 | 5 | **374.25** | +78.34 | +79.07 | −0.73 | 1/1 | **−14.92** |
| **control** (1 re-entry, BE at TP1) | 167 | 7 | 374.17 | +78.26 | +79.07 | −0.81 | 1/1 | −15.01 |
| depth 2 | 168 | 8 | 373.17 | +77.26 | +79.07 | −1.81 | 1/2 | −15.01 |
| depth 3 | 168 | 8 | 373.17 | +77.26 | +79.07 | −1.81 | 1/2 | −15.01 |
| depth 5 | 168 | 8 | 373.17 | +77.26 | +79.07 | −1.81 | 1/2 | −15.01 |
| depth unlimited | 168 | 8 | 373.17 | +77.26 | +79.07 | −1.81 | 1/2 | −15.01 |
| BE at TP2 (hold initial SL) | 167 | 7 | 370.93 | +75.02 | +79.07 | −4.04 | 1/4 | −15.01 |
| depth 3 + BE at TP2 | 168 | 8 | 369.93 | +74.02 | +79.07 | −5.04 | 1/5 | −15.01 |
| **bank 50% at TP1** | 167 | 7 | 339.41 | +43.50 | +42.79 | **+0.71** | **4/1** | −15.01 |
| bank 100% at TP1 | 167 | 7 | 304.65 | +8.74 | +6.51 | **+2.23** | **4/1** | −15.01 |

🔴 **DEPTH 2, 3, 5 AND UNLIMITED ARE BYTE-IDENTICAL, AND THE ANSWER TO "HOW MANY" IS ONE.** In 6.6
years exactly **one** setup ever offered a second re-entry — 2024-01-16 L, and it was a full −1.00R.
A third never existed at any depth. ⚠ **So the cascade question has a sample of n=1** and the table
cannot rank 2 against 3 against 5; it can only say the second one that occurred lost.

🔴 **AND THE RULE THAT ANSWERS IT ALREADY SHIPS.** A re-entry that closes at stage 0 (stopped
without reaching TP1) sets `sec_stop_dir`, the driver calls `mark_dead`, and **that 15m leg is
finished** — no depth setting overrides it. So a cascade can only ever continue through a SCRATCH,
never through a loss. *"Up to what number before settling into losses"* is already answered in code
as **the first real loss ends it**, and raising the depth only buys extra tries after a scratch.

🔴 **BE-AT-TP2 IS WORSE, AND IT OVERTURNED THE PREDICTION THAT PROMPTED IT.** Part 1 ended by
blaming the breakeven ratchet for ticking re-entries out of their own trades, so this cell holds the
original stop through TP1. Result: **1 win / 4 losses, ex-best −4.04.** The three trades it rescued
from a +0.05R scratch each became **exactly −1.00R** (2024-01-16, 2024-12-02, 2025-01-29). **The
ratchet was protecting them, not robbing them** — the trade genuinely came back and the scratch was
the good outcome. ⚠ **The plausible mechanism was the wrong one, and only the run said so.**

🟢 **BANKING PART OF THE RE-ENTRY AT TP1 IS THE FIRST CHANGE IN THIS WHOLE EXERCISE THAT WORKS.**
It converts the four scratches into small wins and flips the win/loss count **1/1 → 4/1**, and it
is the first positive ex-best number anywhere in 26 replays. The diagnostic that led here: **three
of the seven control re-entries exited at exactly +$0.30, which is `exec_be_buf_tk` (30 ticks) to
the cent** — one of them $2.65 past TP1 with nothing banked.

⚠ **AND IT COSTS THE TAIL, WHICH IS BIGGER THAN EVERYTHING ELSE COMBINED.** Banking 50% cuts
2023-04-03 from **+79.07R to +42.79R**; banking 100% cuts it to **+6.51R**. The whole secondary book
over 6.6 years is that one trade. **So this is not an optimisation, it is a bet about which kind of
re-entry the next 6.6 years holds more of** — the four small ones, or the one that runs.

⚠ **The 1m trend filter beats control on book R AND drawdown — by 0.08R and 0.09R.** That is
nothing next to the 15.06R jitter band. What it actually does is drop **2 of 7** re-entries (both
scratches: 2022-03-06, 2025-01-29) and **it does not filter the one full loss** (2025-08-21 survives
every variant). It also nudges 2020-09-15 from +0.05R to +0.09R by arming on a later 1m bar.

---

## Part 3 — the two survivors together. 7 replays.

| variant | trades | sec | book R | sec R | its best | **ex-best** | W/L | ddR |
|---|---|---|---|---|---|---|---|---|
| **control (shipped)** | 167 | 7 | **374.17** | +78.26 | +79.07 | −0.81 | 1/1 | −15.01 |
| 1m dir + bank 25% | 165 | 5 | 358.07 | +62.16 | +60.93 | +1.23 | 4/1 | −14.92 |
| bank 25% at TP1 | 167 | 7 | 356.79 | +60.88 | +60.93 | −0.05 | 4/1 | −15.01 |
| **1m dir + bank 50%** | 165 | 5 | 341.89 | +45.98 | +42.79 | **+3.19** | **4/1** | **−14.92** |
| 1m dir + bank 50% + depth 2 | 167 | 7 | 339.89 | +43.98 | +42.79 | +1.19 | 4/3 | −14.92 |
| bank 50% at TP1 | 167 | 7 | 339.41 | +43.50 | +42.79 | +0.71 | 4/1 | −15.01 |
| bank 75% at TP1 | 167 | 7 | 322.03 | +26.12 | +24.65 | +1.47 | 4/1 | −15.01 |

🟢 **`exec_sec_req_m1_dir=True` + `exec_sec_tp1_pct=50` is the best re-entry configuration measured
— on every column except the one that matters most.** 5 trades, **4 wins / 1 loss**, **+3.19R
excluding the outlier** (the only cell above +2.23), best drawdown in all 26 replays (−14.92R).
**Its total book R is 32.28R BELOW control**, because it halves the 2023-04-03 tail.

🔴 **THE TWO FILTERS COMPOUND, WHICH NEITHER DID ALONE.** The 1m filter on its own moved ex-best by
+0.08R; banking 50% on its own moved it by +1.52R; together they move it by **+4.00R**. The reason
is visible in the per-trade list: **the filter changes WHICH 1m bar arms 2020-09-15, and with 50%
banked that trade goes +0.05R → +2.86R instead of +0.09R.** ⚠ **A filter that looks inert on the
shipped exit ladder is not inert on a different one — measure a combination as a combination.**

⚠ **Depth 2 on top of the best cell is strictly worse: it adds 2020-09-16 −1.00R and 2024-01-16
−1.00R and takes the record to 4 wins / 3 losses.** Third independent confirmation that the answer
to *"how many re-entries"* is **one**.

⚠ **Zero primaries displaced in all 26 replays** (0 lost / 0 gained against control everywhere). The
one-slot queue effect that killed the Run 12 loosenings is not in play here — a re-entry only ever
fires on a leg whose primary is already closed.

## Shipped

**Nothing. Every one of the seven levers stays at its default, and the defaults reproduce the
shipped book byte-for-byte.** The measured recommendation, if the re-entry is ever wanted live, is
`exec_sec_req_m1_dir=True` + `exec_sec_tp1_pct=50` — **and it is a return-for-consistency trade
Aaron has to make, not one a table can make.** It converts a book of scratches plus one 79R trade
into a book of small wins plus one 43R trade. Against this repo's stated philosophy — *few
high-quality setups, size over frequency, the tail is the point* — **the shipped default is the
consistent choice, and that is why nothing changed.**

⚠ **n=7 secondaries in 6.6 years.** Every conclusion here about the small trades rests on four of
them, and every conclusion about return rests on one. **What the 26 replays DO establish, and what
does not depend on the sample: which levers are inert (`exec_sec_zone_deep` on a swept stop),
which are byte-identical (depth ≥ 2), and which direction each door moves the win/loss count.**

🔴 **NOT PARITY-GATED, and it cannot be.** All seven levers are Python-only — there is no
`exec_sec_*` twin in `mpc_strategy.pine` beyond the shipped ones, and `algos/live/bridge.py` refuses
`exec_secondary` outright. **Every number in Run 23 is a lab finding about a path no chart and no
bot has ever run.**

✅ **20 new tests in `tests/test_secondary.py`** (8 for the gates, 12 for depth + exit ladder),
**every one watched RED by mutation.** 🔴 **One mutation SURVIVED the first pass and the test was
rewritten:** *"the depth counter never resets on a new setup"* reddened nothing, because the test
only checked that the FIRST re-entry on a new setup armed — which the SOS-bar comparison already
guarantees on its own. It now makes the new setup spend its **full** allowance of two, and the trap
is written into its docstring. 285 strategy + 27 backend runner tests green.


---

# Run 24 — 2026-08-19 — **THE LOSS-RECOVERY LEG. NINE STOPS, SIX EXIT LADDERS, AND THE DEFAULT WON.**

⚠ **This is not a sweep of `SosFadeConfig`. No parameter of this bot moves, and no figure
elsewhere in this log or in its CLAUDE.md changes.** The subject is
`strategies/python/loss_recovery/` — a separate lab package that replays a **25%-size
counter-trade after every A+ loss**, and is what Aaron's *"can I win the loss back the other way"*
question turned into. It is filed here because its entire population is **this bot's 62 real
stop-outs**, so a change to A+'s entry rule re-populates it and this run goes stale.

**Setup for every row below:** `python backtest/tools/recovery_report.py --start 2018-09-14
--end 2026-08-14 [--exits | --soft-curve | --stops | --search]`, XAUUSD M15, **186,910 bars**,
`mpc_sos_fade` at shipped defaults with `exec_secondary=False`, warmup 1000, bar fills, **both
legs costed at `puprime_ecn`**. The shipped recovery rule is: stop at the far end of the CHoCH
break leg, lock +1R at +1R, then trail confirmed swings.

## The question

Aaron, off the 2026-05-11 chart: *"the stop loss is the previous shift of structure — that's
almost the same distance from where it entered … if we're only trading 25%, we need some kind of
tight stop-loss strategy so that if we're wrong we just get out of the trade."* And separately,
off 2026-03-15: the trade closed at exactly +1R and price then ran another 2.9R.

🔴 **The first pass tested only the four ideas already named in conversation and reported that as
a search. Aaron rejected that, correctly** — *"I told you to go find strategies … but you never
went and did that, you only listened to what I told you."* Part 2 is the actual search, and the
rejection is recorded because the first pass looked complete: five variants, a plateau check, a
commit. **A search bounded by the conversation is not a search, and nothing in its output says so.**

## Part 1 — the four named ideas (one lever at a time, everything else shipped)

| lever | net R | win | avg loss | vs the risk dial |
|---|---|---|---|---|
| **shipped** — structural stop, lock +1R→+1R | +16.2R | 58% | −1.01R | 1.53x |
| **soft cut at −0.3R** (stop unchanged, exit early) | **+18.5R** | 37% | **−0.30R** | **1.90x** |
| exit on the opposing CHoCH | +9.7R | 52% | −0.61R | 1.23x |
| early breakeven step at +0.5R | +4.2R | 47% | −0.68R | 0.90x |
| lock later — arm +2R, stop to +1R | −2.3R | 37% | −1.04R | 0.53x |

🔴 **Three of the four lose, and two of them were the assistant's own suggestions, made before
anything was measured.** Recorded rather than dropped:

- **Structural invalidation costs 6.5R.** An external CHoCH against a trade that is WORKING is a
  normal pullback, so the rule cuts winners to save losers the lock had already capped.
- **An early breakeven step is the worst lever on the board.** The structural stop is ~4x a normal
  one, so +0.5R is inside the noise of the leg and the step gets tagged on the retrace that
  precedes the run.
- **Splitting the lock's trigger from its destination loses monotonically.** The shipped 1→1 is
  not a placeholder somebody forgot to separate.

### The soft cut is a PLATEAU, and it buys nothing

`--soft-curve`, 0.05 steps, with both halves and the five best trades deleted:

| cut at | net R | 1st half | 2nd half | less top 5 | win | maxDD |
|---|---|---|---|---|---|---|
| −0.15R | +8.5R | +4.1R | +4.4R | **−4.7R** | 15% | 49.6% |
| −0.2R | +11.8R | +6.4R | +5.3R | **−1.4R** | 23% | 48.7% |
| −0.25R | +17.1R | +9.5R | +7.7R | +3.3R | 32% | 46.5% |
| **−0.3R** | **+18.5R** | +12.1R | +6.5R | +4.7R | 37% | 47.0% |
| −0.5R | +13.8R | +9.2R | +4.6R | +0.0R | 40% | 49.1% |
| −0.75R | +18.0R | +10.6R | +7.4R | +4.1R | 53% | 47.4% |
| structural | +16.2R | +7.5R | +8.6R | +2.3R | 58% | 48.3% |

🔴 **Every value from −0.25R to structural lands between +12.9R and +18.5R, against this
strategy's measured run-to-run spread of 15.06R** (`jitter_audit.py`). **That is one flat region,
so the honest claim is that cutting early is FREE — never that it earns more.** What moves
monotonically is the SIZE of a loss (avg −1.01R → −0.30R, worst −1.27R → −0.44R), bought with win
rate (58% → 37%). A preference about how a wrong trade feels, not a return decision.

⚠ **It collapses below −0.25R** — at −0.2R and −0.15R the rule goes negative once its five best
trades are removed, i.e. the stop is now inside the noise of the entry bar and the winners are the
only thing holding it up.

🔴 **The mechanism matters, and the intuitive version is wrong.** `soft_stop_r` works ONLY because
it leaves `risk` at the STRUCTURAL distance. A position is sized off its stop, so moving the stop
nearer buys a bigger position and the loss in money is unchanged; this does not move the stop that
SIZED the trade, it refuses to sit through more than a fraction of it. **"Tighter stop" and
"smaller loss" are different things and only one of them is available.**

## Part 2 — the actual search: nine stop placements, scored against an ATR control

`--stops` and `--search`.

| stop | took | refused | median stop | cost/R | net R | maxDD | net less its best 5 |
|---|---|---|---|---|---|---|---|
| **break leg (shipped)** | 62 | 0 | $37.91 | 0.4% | **+16.2R** | 48.3% | **+2.3R** |
| the CHoCH bar's extreme + 0.1 ATR | 62 | 0 | $5.18 | 2.6% | **+24.4R** | 46.3% | 🔴 **−7.4R** |
| break leg × 0.25 | 62 | 0 | $9.55 | 1.5% | +2.7R | 48.8% | |
| break leg × 0.5 | 62 | 0 | $19.09 | 0.7% | −3.1R | 51.2% | |
| the last confirmed swing | 62 | 0 | $5.16 | 2.7% | −12.3R | 58.6% | |
| the losing trade's own entry | 57 | **5** | $16.05 | 0.9% | +1.8R | 51.3% | |
| 1.5 × ATR(14) — **CONTROL** | 62 | 0 | $4.71 | 3.0% | +3.3R | 52.6% | |
| 2 × ATR(14) — **CONTROL** | 62 | 0 | $6.29 | 2.2% | +2.3R | 47.8% | |
| 3 × ATR(14) — **CONTROL** | 62 | 0 | $9.43 | 1.5% | −2.9R | 55.8% | |

🔴 **The signal-bar stop looked like the answer and is not.** +24.4R with a LOWER drawdown on a
stop 7x tighter — and **−7.4R once its five best trades are deleted**, where the shipped stop
survives the same deletion at +2.3R. Its median hold is **4 bars**: it is not a better version of
this rule, it is a different hour-long rule that caught five big moves in a record where gold ran.
⚠ **Its pad is a cliff too** — 0 ATR gives −2.2R and 1.0 ATR gives −5.4R, either side of a wide
flat middle. **Two independent robustness checks failing on the row with the best headline is the
whole reason to run them before reporting the headline.**

✅ **The ATR control earned its place.** At a matched $5–6 stop it scores +3.3R against the signal
bar's +24.4R, which is what says the STRUCTURE is doing the work rather than the tightness. It
also says nothing else here is: every other structural placement loses to it or ties.

⚠ **`swing` is the worst row on the board (−12.3R at a 58.6% drawdown) at almost exactly the same
stop SIZE as `signal_bar`. Size is not the variable — where the level came from is.**

### Aaron's own idea: the stop on the LOSING TRADE'S ENTRY

*"the stop loss is the entry of the original trade that lost … otherwise gonna increase the lot
size because the stop loss is shorter. However, we will hit 1R quicker, and then we can move to
breakeven faster."* **Every step of that mechanism is correct and it still loses 14R.**

The stop is **2.4x tighter** ($37.91 → $16.05), so the same risk buys 2.4x the position, and the
median trade resolves in **43 bars against 294** — eleven hours instead of three days. Cost is not
the objection either (0.9% of R at $16).

🔴 **What breaks it is WHERE that stop sits.** The primary's entry is a price the market has just
been trading around — it went there, filled an order, and reversed through it — so it is the most
likely level in the area to be revisited. The tell is the EXCURSION, not the P&L: **median MFE
falls 1.01R → 0.89R.** Shrinking the stop 2.4x should have made every dollar of travel worth 2.4x
more R; it made it worth LESS, which can only mean the trades are dying before the move they were
entered for. `locked` falls 56% → 49% for the same reason.

⚠ **5 of 62 are REFUSED outright** — by the time the CHoCH prints, price is back on the wrong side
of the primary's entry and a stop there would sit above a long's fill. Refusing is correct (rule
17), and `refused()` counts them separately from `pending()`, because *the signal never came* and
*the stop was unusable* say opposite things about a rule.

⚠ **It does not combine with the soft cut either** — `loss_entry` + a −0.3R cut is **−1.7R**, the
only negative variant measured on this rule.

## Part 3 — "the +1R lock gives up the continuation"

Answered with the EXCURSION rather than with more variants. Of the **35 recoveries that reach
+1R**:

| | |
|---|---|
| median booked | **+1.00R** |
| median MFE **while the trade was open** | **+1.06R** |
| ever saw +2R while open | **3 of 35** |
| ever saw +3R while open | 2 of 35 |
| median extra R offered **after the exit** (30d window) | **+2.33R** |
| offered more than 1R after the exit | **22 of 35** |
| offered more than 3R after the exit | 15 of 35 |

🔴 **Price tags +1R, takes the stop, and THEN runs — so no trail can reach it.** Only 3 of 35
trades were ever above +2R while still open, and every attempt to hold for them pays 32 trades of
given-back R to catch 3. Which is exactly what the alternatives measure:

| exit | net R |
|---|---|
| **lock +1R→+1R + confirmed swings (shipped)** | **+16.2R** |
| bank 25 / 50 / 75% at +1R, rest to breakeven | +6.4 / +6.0 / +5.6R |
| bank 50% at +1R, rest keeps the +1R stop | +11.3R |
| bank 50% at +0.75 / +1.5 / +2R, rest to breakeven | +2.5 / +8.1 / +7.0R |
| lock +1R→+1R + 1 / 2 / 3 / 4 ATR chandelier | +9.0 / +8.3 / +8.4 / +10.4R |
| lock to +0.5R instead of +1R | +7.9R |
| lock to breakeven instead of +1R | +9.5R |

⚠ **A percent-of-price ratchet loses to the swing trail on BOTH stops, and flatly across a 20x
range of steps** (0.05% +8.5R … 1% +9.2R on the break-leg stop). At 1% one step is **$40 against a
$38 median stop** — inert, the `mpc_bleg` trap — and at 0.05% it binds constantly and hands back
the runners. **A swing level is the market saying the move is still intact; a percentage is
arithmetic saying so.**

🔴 **THE ONE UNEXPLORED LEAD, and it is the biggest number here: +2.33R median on 22 of 35 trades,
arriving AFTER the position closed, is a RE-ENTRY signal rather than a trailing-stop problem.**
Nothing in this rule takes a second trade on the same premise. It is a new rule with its own spec
and its own arming condition, and it is the only direction these numbers actually point at.

## Status

**Nothing adopted. `loss_recovery` still ships `enabled=False`, `stop_mode="structural"`,
`soft_stop_r=None`, `trail_pct=0`, `partial_at_r=0`, `trail_atr_mult=0`** — so every number
elsewhere in this log stands unchanged, and `soft_stop_r=-0.3` is available as a one-line change
if the smaller losses are wanted.

⚠ **No parity gate exists and none can yet** — there is no Pine twin of `loss_recovery`, so every
figure above is a LAB finding. `indicators/strategies/mpc_recovery_strategy.pine` is a FORK for
eyeballing entries on a chart and **its P&L is not this rule's P&L**: TradingView holds ONE net
position, so it closes the recovery when the primary enters the other way.

⚠ **This run's whole population is A+'s 62 stop-outs at the shipped defaults with
`exec_secondary=False`. Any change to A+'s entry rule re-populates it and this run goes stale** —
same standing as `overlap_audit.py`.

✅ **31 tests in `strategies/python/loss_recovery/tests/`, every one watched RED by a named
mutation.** 🔴 **Two were caught VACUOUS by that pass, and both failure modes are general.** One
refusal branch was tested by running the mode over the real fixture — where every signal HAS a
usable swing, so the branch was never reached and a mutation making it borrow the structural stop
passed; a refusal is only testable by CONSTRUCTING the state that triggers it. And one mutation
string failed to match after `ruff format` had collapsed the block it targeted, leaving a green
run that proved nothing: **a mutation that does not apply is indistinguishable from a test that
survived it — assert the replacement landed before believing the red.**

---

## Run — five ways to stop the RECLAIM re-entry giving its money back (2026-08-24)

**The question.** Aaron's 2025-08-19 reclaim ran **+2.98R**, missed its target by **7.5 cents** on
gold, and finished **−1R**. The reclaim half banks 100% at its target and its stop does not move
until that target is touched, so there is no middle outcome: a trade either pays 3R or pays −1R.
Five ideas were replayed against that.

**Basis, identical for every row.** XAUUSD M15, 2020-01-01 → 2026-08-23, no cost layers, 10% per
trade compounding, 5-minute fill clock, seeded from control run `71d8aa048999` with only the named
fields changed. Control reproduces Aaron's run `6e029942cb29` on every stored KPI: 249 trades,
0.5863 win rate, 44 scratches, 43.34% drawdown. **The A+ leg is +139.71R (159 trades) and the gap
leg +8.19R (44 trades) in EVERY row below**, which is the check that each change touched only the
reclaim.

⚠ **R is recomputed per trade from the stored equity curve**, not read off a KPI. The gap and
reclaim halves are told apart by their first target's distance in R (reclaim 3.0, gap 1.25) —
`kind` alone cannot separate them.

### The verdict, all five

| idea | setting | reclaim book | vs control |
|---|---|---|---|
| — | control (shipped) | **+30.00R** | — |
| bank the reclaim earlier | target 1.25R | +10.25R | **−19.75R** |
| move the stop to breakeven | arm 1.5R, keep 0 | +23.77R | **−6.23R** |
| enter at market, not on the retest | market, target 3R | +23.11R | **−6.89R** |
| halve the stop zone at halfway | arm 1.5R, keep 0.5R | +29.00R | **−1.00R** |
| **expire the resting order** | **cancel after 12h** | **+38.00R** | **+8.00R** |

🔴 **FOUR OF THE FIVE LOSE, AND THEY LOSE FOR ONE REASON.** A reclaim winner pays **3R** and a
reclaim loser pays **1R**. Any rule that protects a loser saves at most 1R; any rule that knocks
out a winner costs 3R plus whatever it then loses. **The break-even exchange rate is one winner
per three-to-four saves, and none of the four clears it.** Every losing idea either widens the
entry-to-stop distance or tightens the stop into the noise the trade has to survive to reach 3R.

### 1. Expire the resting order — the only one that pays

Cancel a reclaim's resting limit after it has waited N fill-clock bars without filling, and forbid
the same setup re-placing it (a new break of structure arms a fresh one).

| order waited | orders | W/L | worth |
|---|---|---|---|
| under 30 min | 61 | — | +25.84R |
| 30 min – 1 h | 6 | 2W/4L | −1.87R |
| 1 – 3 h | 8 | 5W/3L | +2.52R |
| 3 – 6 h | 2 | 1W/1L | +0.25R |
| **6 – 12 h** | **5** | **4W/1L** | **+11.25R** |
| 12 – 24 h | 4 | 0W/4L | −4.00R |
| over 24 h | 4 | 0W/4L | −4.00R |

Whole-book totals by cutoff: 0.5h +173.73R, 1h +171.87R, 3h +174.39R, 6h +174.64R,
**12h +185.89R**, 24h +181.89R, control +177.89R. Drawdown 43.34% at 12h, unchanged.

✅ **The 8.00R is EXACT ARITHMETIC, not a difference between two noisy runs.** Matching trades by
entry time across the runs: at every cutoff the cancelled orders are **pure subtraction — zero new
trades appear in any run.** The freed position slot never let another trade in, so there is no
displacement term. The 8 orders cancelled at 12h are named, spread over 2020, 2021 ×2, 2023,
2024 ×2, 2025 ×2, and every one lost exactly −1R. Aaron's 2025-08-19 reclaim is one of them.

⚠ **Every cutoff of 6 hours or less LOSES**, because the 6–12h band is the best in the whole
re-entry book. Cutting early is not a milder version of cutting late — it is the opposite trade.

⚠ **THE RULE RESTS ON 8 TRADES.** Eight straight losses at roughly even odds is about a 1-in-250
fluke, so it is suggestive rather than established. It is worth **~1.5R a year**. ⚠ **This is the
one idea here that could NOT be answered from stored data**: runs record when an order FILLED and
never when it was PLACED. An earlier attempt to reconstruct the wait by pairing each secondary
with the preceding primary matched on only 32 of 90 exit prices and was discarded unpublished.

### 2. Halve the stop zone at halfway — the near miss

Arm on the trade's own favourable excursion, then move the stop PART of the way back rather than
to breakeven.

| arm at | stop keeps | reclaim | vs control | winners lost |
|---|---|---|---|---|
| 1.0R | 0.50R | +28.00R | −2.00R | 2 |
| 1.5R | 0.75R | +31.25R | +1.25R | 0 |
| **1.5R** | **0.50R** (as asked) | **+29.00R** | **−1.00R** | **1** |
| 1.5R | 0.25R | +24.00R | −6.00R | 3 |
| 1.5R | 0 (breakeven) | +23.77R | −6.23R | — |
| 2.0R | 0.50R | +31.00R | +1.00R | 0 |
| **2.0R** | **0.25R** | **+31.50R** | **+1.50R** | **0** |

✅ **The arithmetic closes to the cent and that is what makes it trustworthy.** Each armed loser
saves `(1 − keep)` R; each winner knocked out costs `3 + keep` R. At arm 1.5R five losers arm, so
keep 0.75 gives 5 × 0.25 = +1.25R with no winner lost; keep 0.50 gives 2.50 − 3.50 = −1.00R with
one lost; keep 0.25 gives 3.75 − 9.75 = −6.00R with three lost. Every row reproduces.

⚠ **The best row is +1.50R off TWO trades** — only 2 of the 27 losing reclaims ever reach 2R in
front before failing. ⚠ **Account drawdown is 43.34% in six of the seven runs**, i.e. unchanged:
the drawdown is driven by the A+ book, so shrinking individual re-entry losses does not move it.
**Making a losing ticket smaller is not the same as making the account safer, and this row is the
proof.**

### 3. Enter at market instead of waiting for the retest

| | trades | reclaim | vs control | drawdown |
|---|---|---|---|---|
| control (retest, 3R) | 46 | +30.00R | — | 43.34% |
| market, target 3R | 49 | +23.11R | −6.89R | 53.53% |
| market, target 4R | 49 | +21.12R | −8.88R | 51.20% |
| market, target 2R | 49 | +15.11R | −14.89R | 51.01% |

🔴 **THE STOP DOES NOT MOVE, SO A WORSE ENTRY IS A WIDER RISK AND A TARGET FURTHER AWAY IN PRICE.**
On 2025-08-19 the retest entered at 3327.49 with the stop at 3323.51 — risk **$3.98**, target
$11.93 up at 3339.42, and price reached 3339.34. Market entry got in **12h45m earlier** at
00:25 and paid **3336.02**: risk **$12.51**, target **3373.55**, price topped at 3345.25. It
reached **0.74R** and scratched. **In the move ten hours before the high, and still nowhere near
the target.**

⚠ **The upside it was built for is three trades.** Reclaims that arm and then run away without
ever offering a retest never fill today; over 6.6 years there are **3** of them (46 → 49). Three
extra trades do not pay for tripling the risk on the other 46.

⚠ **Re-cutting the target does not rescue it** — 4R is worse, 2R is much worse. The reclaim's edge
IS the tight geometry, so paying up for the entry removes the thing being traded.

### 4/5. Bank earlier, and the near-miss tolerance

Pulling the target to 1.25R takes the reclaim book **30.00R → 10.25R** and worsens drawdown.
A "bank if price gets within $7.50 of the target" rule was not replayed: on this book $7.50 is
arithmetically a **1.3R** target, which is the row above under another name, and only **one trade
in 46** ever came within $0.25 of its target.

### What shipped

**Nothing is on.** Three settings were added, all defaulting to the shipped behaviour: the
protected-stop trigger, how far that stop moves, and the resting-order cancel. The cancel is the
only one recommended, at **144 fill-clock bars = 12 hours**.

⚠ **Risk percent is a SIZE dial and was ruled out early** — it changes dollars and account
drawdown, never R and never which trades happen.

✅ **409 tests, 8 mutations written and all 8 killed.** 🔴 **Two mutations survived the first pass
and both were test defects worth naming.** One test passed the setting in by hand, so it never
read the default it claimed to pin — a default test that names the default in its own fixture is
vacuous. The other built the order record itself, so it never reached the pricing rule at all —
the fixture-more-capable-than-production trap, caught only by running the mutation. A third guard
was written with a test that was green either way: the branch is unreachable, because the arm
needs the same bar the guard checks for.

---

# Run 25 — 2026-08-24 — **THE FINAL-HOUR RULE IS WORTH KEEPING, AND RUN 12 §4 KEPT IT FOR THE WRONG REASON.**

Aaron asked what taking the refused end-of-day setups would do to the KPIs, whether those entry
levels ever come back, and whether an overnight gap could cost him more than 1R. Run 12 §4 answered
the first (*"neutral, keep the rule"*) and asserted the third without measuring it: *"buys real
session-gap protection — that is free insurance."* **That sentence is wrong, and the verdict it
supported is still right. Both halves matter.**

## The A/B, re-run on today's config

`backtest/tools/run_report.py`, 2018-09-14 → 2026-08-20, M15, primary entries only, `--no-regime`,
identical on both sides with only the final-hour setting changed.

| | trades | sumR | maxDD | win | loss | be | win rate |
|---|---|---|---|---|---|---|---|
| rule ON (shipped) | 180 | **+137.43** | 5.61R | 80 | 63 | 37 | 56% |
| rule OFF | 181 | **+137.83** | 5.61R | 80 | 64 | 37 | 56% |

**+0.41R on +1 trade**, drawdown identical, win rate identical. Run 12 measured +0.4R on +1 trade
off a different baseline (164 trades). **Independently reproduced on a moved basis** — that is the
strongest thing this entry contains.

## 🔴 The headline number is an ARTIFACT, and the dissection reverses its sign

Three trades are added and two displaced. Only **two of the three are actually final-hour entries**:

| entry (NY) | dir | R | what it is |
|---|---|---|---|
| 2020-03-06 16:30 | short | **−1.61** | a genuine final-hour entry |
| 2020-12-04 16:30 | short | +0.05 | a genuine final-hour entry |
| 2026-04-12 18:00 | long | +3.40 | **NOT a final-hour entry** — it displaced the 18:15 fill of the same setup |

**The two trades the rule is actually about are worth −1.56R combined.** The +3.40R is one setup
filling fifteen minutes earlier because the slot was free, and it displaced a +1.38R trade, so it
contributed roughly +2.0R of pure reshuffle. **Strip the artifact and turning the rule off is
NEGATIVE.** ⚠ Zero shared trades were re-priced, so there is no third term hiding here.

## The gap risk is real, it is the WEEKEND, and it hit exactly this trade

Measured on 2,805,977 M1 bars (2018-09-14 → 2026-08-21), 1,989 session breaks. Gold's break is
17:00–18:00 NY, confirmed off the tape rather than assumed.

| break | median | p90 | p99 | worst |
|---|---|---|---|---|
| nightly (n=1,575) | $0.35 | $1.73 | $8.31 | $29.89 |
| weekend (n=414) | $1.27 | $11.46 | $39.92 | **$113.23** (2026-04-12) |

Scaled by the stop distance actually used (median 0.402% of price, from the 180-trade ledger), a
**weekend** jump exceeds the whole stop **11.1%** of the time; a **nightly** one, **0.3%**.

**The 2020-03-06 loser is the mechanism, not a hypothetical.** Friday 16:30 NY short at 1674.47,
stop $10.83 away at 1685.30. Gold closed Friday at 1674.34 and reopened Sunday at 1691.93 — a
**$17.59 jump straight through the stop**, filled at 1691.93, **$6.63 past it = 1.61R on 1R of
risk.** One of the two trades the rule refuses is the exact failure Aaron described.

## 🔴 But the rule is NOT the protection — the book already carries the exposure

Measured on `backtest/reports/trade_ledger_20260806/trades.csv` (180 trades):

- **80 of 180 (44%) already sit through at least one session break**; 109 nightly breaks crossed.
- **17 of 180 (9%) already sit through a WEEKEND**; 18 weekend breaks crossed.
- Median hold is 7.2h, p90 **64.1h**. Positions are not flattened at the daily close and the time
  stop is 36 calendar hours, so holding overnight is the norm.

**So the rule closes a two-hour window while the book stays exposed the other twenty-two.** Calling
it session-gap insurance overstates it by an order of magnitude. Keep the rule for what it actually
buys — **the −1.56R those two trades cost** — and treat the overnight exposure as a separate,
unanswered question.

## ⚠ What was NOT measured, and one probe that cannot answer

- **Costs and tick fills.** Both A/B sides used the bar-path guess with zero costs. Matched, so the
  comparison is fair; the absolute R is optimistic. Every variant here ADDS a trade, so real costs
  penalise the OFF side harder — it can only strengthen the verdict.
- 🔴 **The August ledger records `c_slippage = 0.00 on all 180 trades`, so it never modelled a gap
  through a stop at all.** Reading its clean record as *"no gap has ever hurt this book"* would have
  been exactly the trap this repo names — a negative result a broken probe also produces. The gap
  numbers above come from raw M1 price, which no fill model can launder.
- **Closing before the Friday close.** The obvious follow-up and untested. 17 weekend holds is a
  small sample, and the tail is the whole point, so a naive average will mislead.
- **A concurrency change.** As in Run 12, every number assumes one position slot; the displacement
  term only exists because of it.

## Verdict

**KEEP the rule** — unchanged from Run 12, on better evidence and for a different reason. It costs
nothing measurable, refuses two trades worth −1.56R over eight years, and one of those is a weekend
gap that blew 61% past its stop. ⚠ **Correct the "free session-gap protection" line in §4 of Run 12
rather than quoting it.**

Harness: `run_report.py` twice with `--set`, plus three throwaway scripts in the session scratchpad
(session-break detection, gap sizing in R, hold/exposure counts). **No repo file modified to take
these numbers.**

---

# Run 26 — 2026-08-24 — **THE BREAKEVEN BUFFER AS A FRACTION OF THE STOP. Built, swept ten ways, every one loses. Run 17's verdict survives its third test.**

Run 17 measured a FIXED widening of `exec_be_buf_tk` and found 5R lost per 1R of scratch rescued.
It closed with *"NOT BUILT. Do not build it without re-reading this row."* This run builds the
smarter version the row did not cover — a buffer that scales with the trade's own stop distance,
with an optional floor at what the trade has already SPENT — and sweeps it. **It loses too.**

## What was built (ships OFF, tick mode is the default and is byte-identical to before)

Five new settings on `mpc_sos_fade`, all inert unless `exec_be_buf_mode` is moved off `"Ticks"`:

| setting | what it does |
|---|---|
| `exec_be_buf_mode` | `"Ticks"` (shipped) / `"Fraction of stop"` / `"Fraction of stop + cost"` |
| `exec_be_buf_r` | the fraction of FROZEN entry risk (`abs(entry - sl)`, never the live stop) |
| `exec_be_cost_margin_r` | extra margin above accrued cost, in R, for the cost-floor mode |
| `exec_be_cap_pct` | ceiling as a % of the distance to the rung price action just touched |
| `exec_be_cost_conflict` | `"Hold stop"` / `"Clamp to cap"` when the cost floor exceeds the cap |

The cap is measured off `_stage_rungs()[0]` — the NEARER rung by distance — because a secondary can
carry a flipped ladder and capping off `_tp1` directly would be wrong on those trades.

Accrued cost counts the UNPAID exit side too (exit commission, plus half-spread when the profile is
not in `bid_ask_fills` mode — under bid/ask the cost already lives in the fill prices, so adding it
would double-charge).

## Basis — one replay per row, everything else pinned

`XAUUSD.p`, Minute/15, **2020-01-01 → 2026-08-23**, `puprime_ecn`, cost layers
`["bid_ask_fills", "commission", "swap"]`, commission $1.00/side, slippage 0 ticks, `consistent`
sizing, `exec_risk_pct = 10`, `exec_scratch_r = 0.15`, `exec_tp2_stop_mode = "TP1 price"`.
Python runner. Every number below is **recomputed from each run's own trade list**, not read off
the stored KPIs.

**Integrity, checked before reading anything:**

- ✅ The control reproduces the pre-change baseline `5a5e2174d095` **trade for trade** — fingerprint
  `13fc4e5f9c7a95fb`, 243 vs 243 trades, matched on entry time, direction, entry, exit and R.
  **The shipped path is untouched by this build.**
- ✅ **9 of 9** variants differ from the control, so the settings are genuinely reaching the engine
  and none of this is a stale backend silently dropping unknown keys.

🔴 **THE FIRST VERSION OF THAT FINGERPRINT WAS PARTLY VACUOUS, AND IT IS THE SAME DEFECT THIS BUILD
ALREADY RECORDS ONE LEVEL UP.** It keyed on `entry_time`, which **is not a field in these trade
records** — the key is `entry_ms`. `dict.get()` returned `None` for every trade in both runs, so
that component of the comparison matched nothing against nothing and contributed no evidence. The
check was still doing real work on direction, entry price, exit price and R, which is why it did not
read as broken — **a partly-dead comparison looks exactly like a live one, because the half that
still works produces a plausible answer.**

✅ **Re-run 2026-08-25 on the real field plus `exit_name`, and BOTH claims survive** — control vs
baseline `13fc4e5f9c7a95fb` on both sides (243 trades), and the two conflict variants
`8088d3411b5e4449` on both sides (246 trades). The fingerprints quoted throughout this run are the
corrected ones; the earlier values `7d622ec152d11e3a` / `a386e83230115f1c` were computed with the
dud key and appear nowhere any more.

⚠ **The transferable rule is the one this file already states about tests, applied to a
MEASUREMENT**: `.get()` on a misspelled key is silent, and a comparison built out of several fields
degrades quietly rather than failing. **Assert the key exists before you fingerprint on it** — a
comparison that cannot distinguish two runs will happily report them identical.

## The sweep — every rung loses, none improves drawdown

| rung | trades | total R | scratches | still LOSSES | loss R | R handed back | win % | max DD % | best R | top5 R | run id |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **CONTROL 30 ticks** | 243 | **+159.1** | 46 | 10 | −0.52 | 38.9 | 53.1 | **46.79** | 24.6 | 86.0 | `6b18811e25d5` |
| frac 0.10 | 245 | +150.7 | **51** | 3 | −0.09 | **39.9** | 55.5 | 48.35 | 24.6 | 86.0 | `a623fdb70e47` |
| frac 0.20 | 246 | +149.4 | 15 | 1 | −0.15 | 12.7 | 56.9 | 49.00 | 24.6 | 86.0 | `3fe90b8b4d4e` |
| frac 0.20, cap 50% | 246 | +149.3 | 16 | 1 | −0.15 | 13.3 | 56.9 | 49.41 | 24.6 | 86.0 | `5ce548bf9e69` |
| frac 0.35 | 246 | +138.2 | 9 | 1 | −0.01 | 8.0 | 57.3 | **53.96** | 24.6 | 82.1 | `f04cd22560b7` |
| frac 0.50 | 246 | +135.0 | 8 | 0 | 0.00 | 6.7 | 57.7 | 49.74 | 24.6 | 82.1 | `cf8ab94197dc` |
| cost 0.20, margin 0.00 | 246 | +150.6 | 17 | **0** | 0.00 | 20.4 | 56.9 | 48.17 | 24.6 | 86.0 | `9392c1e6736e` |
| **cost 0.20, margin 0.05** | 246 | **+150.8** | 17 | **0** | 0.00 | 20.3 | **58.1** | **47.91** | 24.6 | 86.0 | `19580097656b` |
| cost 0.20, clamp | 246 | +150.8 | 17 | **0** | 0.00 | 20.3 | 58.1 | 47.91 | 24.6 | 86.0 | `ce302a5f909f` |
| cost 0.35, margin 0.05 | 246 | +139.1 | 10 | **0** | 0.00 | 11.8 | 58.1 | 53.68 | 24.6 | 82.1 | `9406a9ecf48f` |

All ten completed on the first attempt.

**The exchange rate is WORSE than Run 17's, not better.** The problem being solved is 10 losing
scratches worth **−0.52R in total over 6.5 years**. The cheapest complete fix costs **8.3R**. That
is ~**16R lost per 1R rescued**, against Run 17's 5:1 on a Standard book. Building the smarter
version made the ratio worse because the cohort on ECN is smaller than it was on Standard, while
the runners it cuts are the same runners.

## 🟢 The cost floor genuinely beats the plain fraction, and the reason is the interesting part

`cost 0.20 m.05` is the best variant in the table on every column at once: **+150.8R**, the
smallest loss; **47.91%** drawdown, the closest any variant gets to leaving it alone; **zero**
remaining losing scratches, where every plain-fraction rung except 0.50 left one; 58.1% win rate,
the highest; and **top-five 86.0R, identical to control**.

**Why**: the plain fraction widens the stop on EVERY trade that reaches stage 1. The cost floor only
widens it on trades that have actually SPENT money — commission, spread, swap — and a trade that
runs to target and beyond in the same session has spent almost nothing. So it leaves the runners
alone. The evidence is in the top-five column: the wide plain-fraction rungs (0.35, 0.50) clip it
**86.0R → 82.1R**, and every cost-floor rung at 0.20 keeps all of it.

⚠ **That is still not a reason to switch it on.** 8.3R sits inside the strategy's own run-to-run
spread of **sd 15.06R**. The honest reading of the best variant is *"not measurably worse"*, never
*"better"* — and *"not measurably worse than doing nothing"* is not an argument for adding five
settings to a live strategy.

## 🔴 `exec_be_cost_conflict` is DEAD CODE at every width tested — the branch never executed

`cost 0.20 m.05` (`"Hold stop"`) and `cost 0.20 clamp` (`"Clamp to cap"`) came back **trade for
trade identical** — fingerprint `8088d3411b5e4449` on both, 246 trades each, same entries, exits
and R.

The accrued cost never once grew past 75% of the distance to the rung price action had just touched.
On gold at this sizing, costs are small next to that distance, so **the conflict the setting exists
to resolve does not arise.** The setting has unit tests and has never made a decision on real bars.

⚠ This is repo rule 9 — *a feature nobody has RUN is not a feature* — landing on a branch inside a
feature. It is covered by tests that construct the conflict artificially, which is exactly the shape
`CLAUDE.md` warns about under *a fixture more capable than production*. **If this build is ever
switched on, either prove the branch reachable at a width someone would actually use, or delete the
setting and hardcode the clamp.** ⚠ The `cap 50%` rung does NOT test this — it is a plain-fraction
run, and the conflict only exists in cost mode.

## 🔴 The narrowest rung is worse than useless, and it is the one that looks safest

`frac 0.10` produces **MORE** scratches than the control (51 vs 46), hands back **MORE** R
(39.9 vs 38.9), and still costs 8.4R. It is a buffer large enough to move the stop into the path of
trades that were coming back to run, and too small to clear the costs that make a scratch negative
in the first place — it converts full winners into scratches without fixing any scratch. **The
intuition that a small setting is a small risk is wrong here; the small setting is the worst
value in the table.**

## ⚠ Correction — R is the monotonic column, drawdown is not

Mid-sweep, on four data points, this session asserted to Aaron that drawdown climbed monotonically
(46.79 → 48.35 → 49.00 → 49.74) and used that as the load-bearing evidence that the effect was not
noise. **The fifth rung falsified it**: `frac 0.35` lands at **53.96%**, worse than the wider
`frac 0.50` at 49.74%.

The correct reading, recorded so the next reader does not repeat it:

- **Total R across the plain-fraction ladder IS strictly monotonic** — 159.1 → 150.7 → 149.4 →
  138.2 → 135.0, five points, never once going the wrong way. **That** is the signal.
- **Drawdown is uniformly worse than control but noisily ordered.** Every rung is above 46.79%; the
  sequence between them is not readable.
- The transferable point: **a direction that holds across many settings is evidence even when each
  individual gap sits inside the noise band — but declaring monotonicity on four points, mid-sweep,
  before the ladder was full, was the error.** Wait for the sweep.

## 🟢 The cap does its job

**Best single trade stays 24.6R at all ten settings.** Run 17's fixed widening had no ceiling, which
is the mechanism by which a wider buffer eats the runner. Capping the buffer at a fraction of the
distance to the rung just touched removes that failure mode completely — the remaining loss is the
extra stop-outs, not a clipped runner. **The cap is the part of this build worth keeping if any of
it is ever revived.**

## Verdict

**No change to the strategy. `exec_be_buf_mode` ships as `"Ticks"` and `exec_be_buf_tk` stays at 30.**

**Third measurement, third loss.** Run 17 measured the fixed widening (5R per 1R). Run 17 computed a
ceiling of **+2.11R** for the dynamic swap-aware version and refused to build it. This run built the
fraction-of-stop version end to end and swept it ten ways: the best case is **−8.3R**, inside the
noise band, with a worse drawdown.

⚠ **The problem is real and it is not worth fixing.** Ten breakeven exits over 6.5 years are
genuinely small losses rather than genuinely flat, totalling −0.52R. Every mechanism that removes
them removes more than they cost, because the stop that saves a trade coming back is the same stop
that ends a trade still running, and this strategy's money is in the runners (Run 8: >100% of net).

## What was NOT measured

- **The conflict branch on real bars.** See above — it never executed. Its reachability at any
  practical setting is unknown, not proven absent.
- **Anything on a Standard or Prime book.** This is ECN only. Run 17 was Standard only. The two
  are consistent in direction; neither is evidence for the other's tier.
- **A direction-split buffer.** Still open, still with the poor prior Run 17 recorded: the long
  scratches are the ones being rescued and the long runners are the ones being cut.
- **Fractions between 0.20 and 0.35.** The ladder loses at both ends and the R column is monotonic
  through the gap, so a finer grid would locate a peak already known to be outside the range.
- **The parity gate.** `compare_sos_fade.py` has NOT run against this change — no decision-stream
  export exists on this machine. Repo rule 22 applies: this code must not be treated as parity-clean
  until an export arrives and the gate passes.

Harness: `backtest/tools/` untouched. Ten runs driven through the lab's own HTTP API by throwaway
scripts in the session scratchpad (`queue3b.py` with bounded retry on `failed_crashed` only,
`analyse3.py` recomputing every column from the trade lists plus two integrity checks). **No repo
file was modified to take these numbers.**
