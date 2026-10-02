# The REV setup's arm clock — how the JARVIS table and the SOS Fade bot came to disagree

**Read before touching:** the SOS Fade sequence inside `mpc_jarvis.pine`, its arm sources, or
anything that decides when the table's REV row stops tracking.

---

## 2026-09-27 — one clock, three days, and it is the bot's

Kelly asked why a REV setup was not tracking on his 15m gold chart although a 15m bearish SOS had
printed. The table read `Pass · No sequence`, which means only "nothing is tracking" — it is not a
verdict on the SOS and not an approval. Reading the sequence back answered it: **an SOS alone never
starts a REV.** A sweep or a divergence has to be armed FIRST, and an SOS that fires with nothing
armed is discarded rather than stored, so a sweep landing afterwards starts a fresh count and waits
for a new SOS.

That led to the real finding. **The indicator and the bot were enforcing different rules, and
nothing anywhere said so.**

### What was different

The bot (`strategies/python/sos_fade/sequence.py`, ported from
`strategies/tradingview/sos_fade_strategy.pine`, gated against THAT file and never against this
one) runs **one clock**: an arm dies 4320 minutes after it fires if no SOS follows.

This file ran **two**, and neither matched:

| | `mpc_jarvis.pine` before | The bot |
|---|---|---|
| Sweep arm shelf life | **1440 min** (24h), always enforced | 4320 min (72h) |
| Divergence arm shelf life | 4320 min, always enforced | 4320 min |
| Arm → SOS window | **switched off** | 4320 min, enforced |
| Arm survives while… | EITHER source clock is alive | the one clock is alive |
| A repeat sweep | restarted the 24h clock, so repeat sweeps could hold an arm open indefinitely | never extends the clock |
| A divergence arriving while a sweep holds Stage 1 | joined the LABEL only; arm and clock untouched | **takes the slot over and restarts the clock** |

Net effect: **the bot tracked and traded setups this table had already dropped** — any sweep between
24 and 72 hours old — and students reading the chart were shown a stricter setup than the bot takes.

### Measured before changing it

XAUUSD.p M15, 2020-01-01 → 2026-09-22, PU Prime ECN, bid/ask fills + commission + swap, consistent
sizing, one full replay per row with ONLY the window moved. Lab runs `c5bd33a16fe5` /
`8ae02c55429f` / `97a34e6e844e` / `57fa2c22d7ce`.

| Arm shelf life | Trades | Win | Profit factor | Max drawdown | Sharpe |
|---|---|---|---|---|---|
| 12h | 159 | 52.8% | 2.33 | 26.8% | 0.72 |
| **24h** — what this file had | 206 | 51.0% | 2.30 | 34.9% | 0.72 |
| **72h** — what it has now | 244 | 53.7% | **4.23** | 26.9% | **1.07** |
| 7d | 255 | 53.3% | 4.22 | 29.9% | 1.06 |

- **24h is DOMINATED, not a trade-off** — less return AND 8 points more drawdown. There was nothing
  to weigh, so this is not a preference.
- **72h sits on a plateau, not a peak.** 7 days lands within 0.003 profit factor and 0.002 Sharpe of
  it, which is what says the number is not fitted to one lucky cell. The two cells below it agree
  with each other too (12h and 24h both ≈2.3 and 0.72), so the step is a trend, not jitter on a
  strategy whose run-to-run spread is wide (sd 15.06R).
- **The 38 setups the 1-day cap refused are the ones that paid,** and profit is LESS concentrated at
  72h than at 12h — so it is not one outlier carrying the difference.
- ⚠ **This is the OPPOSITE of the usual result in this repo,** where loosening a filter costs money
  (root `CLAUDE.md` → Trading Philosophy, Run 12). Nothing was loosened: the setups are identical
  and only the fuel's AGE differs. **Sweep age is not a quality signal.**
- ⚠ The lab's one setting moves all four of the bot's uses of that clock at once (arm expiry, the
  arm → SOS limit, and the retro-link window). Divergence arming is OFF on the live bot
  (`exec_arm_div` false), so for TRADED setups this is a clean read on sweep age; a divergence arm
  can still occupy the Stage-1 slot, which the run does capture.
- ⚠ One instrument, one window. Gold M15, 2020 → 2026-09.

### Re-measured with its noise, 2026-10-01 — ADOPT 72h

The table above has no error bar, so the 24h vs 72h pair was re-run on the current bot. Basis
copied from lab run `978a5f9fafa1` (72h, the shipped setting): XAUUSD.p M15, 2020-01-01 →
2026-09-30, PU Prime ECN, bid/ask fills + commission + swap, consistent sizing, 100-lot ceiling.
`7a216af8c1ac` is the same run with only the arm clock at 1440. `compare_runs` confirmed that
setting is the only difference.

| Arm shelf life | Trades | Total R | Max DD R | Without best | Profit factor | Max DD % | Sharpe |
|---|---|---|---|---|---|---|---|
| 24h `7a216af8c1ac` | 207 | +129.4 | 9.4 | +102.7 | 2.36 | 33.5% | 0.97 |
| **72h** `978a5f9fafa1` | 246 | **+175.1** | **6.8** | **+148.5** | **3.33** | **24.7%** | **1.21** |

- **72h minus 24h: +45.8R ± 21.9R (1 se), 95% range +9.8R to +94.7R, P(72h better) 0.997.** Paired
  by entry day (a day only one arm traded counts 0 for the other), resampled in whole ISO weeks so
  clustered trades stay together, 149 weeks with a trade, 20,000 draws.
- Agrees with the 2026-09-27 table in direction and size. The verdict is now statistical, not just
  dominance on point estimates.
- ⚠ The 24h arm is the BOT with one clock shortened, not a replay of this file's old rules (which
  also let a repeat sweep restart the clock). It answers "which shelf life is right", not "what did
  the old table show".

### What changed in the file

Three settings are gone: the sweeps-can-arm toggle (always on), the ignore-the-window toggle (always
on, which is what made the arm → SOS limit dead code), and the separate sweep window. One constant
remains. The two per-source expiry blocks are deleted; the stale-arm clear that was dead code is now
the only thing that ages an arm out. A divergence now takes over a sweep's Stage-1 slot and restarts
the clock, matching the bot.

**The per-source timestamps are KEPT but are label state only** — they still drive the Stage-1 row's
`Sweep / Div / Sweep+Div` text, they are set whenever that source fires at Stage 1, and they are
cleared everywhere the arm is cleared. Nothing reads them for expiry any more. Do not put a clock
back there without moving the bot too.

The same clock was added to the **1-minute path**, `f_rev15()`, which had **no clock at all** — a
divergence arm sat there until a death came along, which can be weeks. It also gained a per-side SOS
timestamp, because its retro-link had no window and the one timestamp it did keep is shared by both
directions, so a bear SOS would have dated a bull link.

### What still does NOT match, and why

- 🔴 **The 1-minute path arms on a DIVERGENCE ONLY — it has no sweep arming whatsoever.** The live
  bot is the mirror image: sweeps on, divergence off. So on a 1m chart the REV row can arm from a
  source the bot ignores and cannot arm from the source the bot uses. **This is pre-existing and was
  not introduced here.** It is not a tweak to fix: `f_rev15()` is itself called through
  `request.security`, the sweep pools are built from `request.security(..., "D", ...)` daily levels
  (`mpc_jarvis.pine` ~1484), and Pine does not allow one lookup inside another. Closing it means
  restructuring how the 1m chart gets its 15m state, not adding a condition.
- The 1m path evaluates its deaths BEFORE the arm; the 15m path and the bot both do it after.
  Pre-existing, same-bar effects only, left alone.
- The 1m path has no "day-level sweep older than a day" rule. Moot while it has no sweeps.

### Two display findings raised at the same time, not yet acted on

- **`Pass` is the wrong word on a student table.** It reads as "passed", i.e. approved, when it means
  "standing aside". `No setup` was recommended.
- **A sweep gets no backwards adoption of an SOS that already fired; a divergence does.** The
  divergence retro-link exists precisely because a late-confirming pivot misses a fast reversal —
  the same lag can hit a sweep, and there the setup is lost outright. Applies to the bot as much as
  to this file.

### ⚠ Unproven until it compiles

Pine only runs on TradingView, so **nothing in this repo has executed this change.** There is no
harness, no parity gate on this file's sequence (the gate covers the STRATEGY Pine, which was
already correct), and no test that can go red. The numbers above were measured on the bot, which is
the thing the change makes this file agree WITH — they are not evidence that this file now does.
**Load it on a 15m and a 1m gold chart and check the REV row before trusting it.** Rule 9.
