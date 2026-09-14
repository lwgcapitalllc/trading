# Notes — Secondary (1m sniper) re-entry — build story

The full build, measurement and defaults history of `exec_secondary`, the 1-minute sniper re-entry layer. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, committed `c962601`)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, committed `c962601`)*.

- **`run_dual(df15, df1m)`** merges the two streams on a close-time clock: the **primary** is stepped
  on 15m bars exactly as `run(df15)` (so parity is untouched); the **secondary** latches/arms/fills/
  manages on real **1m** bars — the sniper "in and out fast" a 15m bar can't express.
- **Execution** grows an `_entry_kind` tag + `step_secondary(bar1m, arm)`. A 15m bar only ever
  touches a `primary` position; a fill-clock bar only a `secondary`. They share the one position slot but
  never the same trade (the secondary arms only when flat), so the tag is all that separates them.
  With `exec_secondary` OFF, no secondary ever opens, so `step()` is byte-identical to before.
- **NO Pine parity gate** — the Pine is only the approximate version, so this is verified **visually**
  (the lab price chart + the 15m→1m drill-down). The offline guard is
  `test_run_dual_primary_is_identical_to_run_when_secondary_off` + the hand-traced arm/exec tests in
  `tests/test_secondary.py`, and OFF parity was re-confirmed on the real M15/M1 cache (`run` ==
  `run_dual`, 40 trades byte-identical). `compare_strategy.py` (which runs `run`, not `run_dual`)
  stays the primary's gate.
- ⚠ **UNMEASURED ON REAL DATA until 2026-08-06, and the reason it stayed that way was a WRONG NUMBER
  IN THIS FILE.** The note here used to read *"broker serves ~35d direct; older via ticks"*, so the
  only 1m window anyone thought was reachable was ~4 days of local cache, over which the secondary
  fired 0 times — correctly read as "expected, the setup is rare", and never re-examined. 🔴 **That
  35-day figure was a guess and it is false.** Probed against the live `MT5_Lab` terminal
  (VantageMarkets-Demo): **real 1-minute XAUUSD runs back to 2018-09-14, ~2.8M bars, 7.9 years.**
  Six windows sampled across the range (Sep 2018 / Jun 2020 / Jan 2023 / Mar 2025 / Jul 2026 / Aug
  2026) all return **1,341-1,392 bars per day at exactly 1.0-minute spacing**, and a request for
  Jun 2017 is REFUSED by the measured floor rather than silently served daily bars. ⚠ **Density is
  the check, never the earliest timestamp** — `backtest/data/history.py` exists because MT5 answers
  a too-deep intraday request with COARSER bars wearing the label you asked for. ⚠ **`backtest/cache/`
  held NO M1 at all** (M5/M15/H1/H4 only), which is a second reason the feature looked unrunnable —
  it is populated now, and on a machine where it is not, the first full-history run pays a one-off
  download of ~2.4M bars (measured: ~10 min, quarter by quarter, over the SSH tunnel). **The standing lesson is this repo's own from 2026-08-06,
  one layer earlier: a plausible guess written into a doc is not a cheap placeholder — it is a
  signpost, and a wrong one costs more than no sign.** This one pointed at "there is no data" for
  three weeks, and the real answer took one probe.
- 🔴 **MEASURED 2026-08-06, AND IT DOES NOT EARN ITS PLACE — THE WHOLE CASE IS ONE TRADE.** Three
  replays over 186,274 M15 + 2,744,333 M1 bars (2018-09-14 → 2026-08-05) at the shipped defaults:
  **A** `run(df15)` = the baseline, **B** `run_dual` with the secondary OFF = the control, **C**
  `run_dual` with it ON. **A 180 trades / +139.90R / maxDD 45.6% (5.61R) · C 190 / +165.46R / maxDD
  50.7% (6.53R).** ✅ **B reproduced A exactly (180 trades, identical entries), so the fill clock is
  inert on its own** and C's delta is the re-entries and nothing else — without that control a
  difference in C is a mix of *the re-entries made money* and *the fill-clock stream nudged the primary*,
  and no arithmetic afterwards separates them, because the two share one position slot. ✅ **Zero
  primaries displaced** (0 in A-not-C, 0 in C-not-A), so the one-slot queue effect did not fire.
  🔴 **Ten re-entries in 7.9 years and 2023-04-03 is +27.33R of the +25.56R total — DELETE THAT ONE
  TRADE AND THE OTHER NINE ARE −1.77R.** ⚠ **On the test that matters here it makes the book WORSE,
  which the total hides**: average R per trade 0.777 → 0.871 with the outlier and **0.731 without**,
  i.e. below baseline, and median R is unmoved (+0.030 → +0.031). **Nine trades that each earn less
  than the average dilute the thing they are added to, and a rising total is exactly what that looks
  like from outside.** ⚠ **It is bought with drawdown: 45.6% → 50.7%.** ⚠ **+25.56R is not evidence
  either way** — the jitter audit put this strategy's run-to-run spread at **sd 15.06R**, so the
  headline is under two standard deviations and rests on one fill. ⚠ **The fat-tail defence does not
  rescue it, and it is worth stating because this repo's own philosophy invites it**: SOS Fade is designed
  to be tail-heavy (5 of 165 trades once made 47% of everything won), so "one trade made it all" is
  not damning by itself — but the primary carries 180 trades and stays positive without any single
  one, while these ten go negative without theirs. **Ten trades cannot tell a small edge from a small
  negative one; that is the same verdict B-LEG got, for the same reason.**
- 🟢 **DEFAULTED **ON** 2026-08-07 AT AARON'S REQUEST, WITH A NEW ONE-PER-PRIMARY CAP — AND THE
  VERDICT ABOVE IS UNCHANGED AND IS RECORDED AS OVERRIDDEN RATHER THAN QUIETLY REVERSED.** Aaron
  read two `SEC` chips on one 2024-12 screen, asked whether one primary could really hand out
  several re-entries (it could), and asked for the cap measured and then shipped along with the
  feature. **The shipped book is now 188 trades / +165.46R / maxDD 5.53R over 7.9 years.** ⚠ **Pin
  `exec_secondary=False` to reproduce ANY figure in this file measured before that date** — every
  one of them is a primary-only book, including the 159 / +142.18R baseline the time stop and the
  EQ/FVG coupling were measured against.
- ⚠ **`exec_sec_once_per_setup` (default ON) — the latch retired the 1-MINUTE leg, so one 15m
  setup could keep handing out fresh legs.** On 2024-12-02 it did: primary 11:30, re-entry 20:08,
  re-entry 01:51 — same 15m SOS bar 7893, two different shift legs (120399 / 120499), the second
  filling two minutes after the first closed. The cap also retires the 15m SOS BAR on a fill,
  which is one-to-one with the primary because the arm already requires `be_sos == *_sos_bar`.
  ⚠ **Per SETUP, not per lifetime** — a new break of structure re-opens it. ✅ **MEASURED, one real
  replay each over 186,366 M15 + 2,745,711 M1 bars: OFF 190 trades / +165.46R / maxDD 6.53R
  (50.7%) · ON 188 / +165.46R / maxDD 5.53R (45.3%), zero primaries moved.** It fires on exactly
  **two setups in 7.9 years**, removing 2024-01-16 18:44 (−1.000R) and 2024-12-03 01:51 (+1.000R).
  🔴 **The total R matching to fourteen decimal places is a COINCIDENCE — those two are exactly ∓1R
  and cancel — and must not be read as "capping is free by construction"**; on another history the
  second re-entry could be the +27R one. **What is not luck is the drawdown**: the −1R sat in the
  middle of the worst losing stretch, so the capped book is now marginally BETTER than the
  primary-only baseline (5.53R vs 5.61R) where the uncapped one was clearly worse. ⚠ **It does not
  rescue the feature** — eight re-entries instead of ten, April 2023 still carries all of it, and
  the book's average excluding that trade is 0.739R against the baseline's 0.777R.
- 🔴 **NOT EVERY PATH CAN RUN THE SECONDARY, AND THE DEFAULT MADE THAT LOAD-BEARING.** `run_dual`
  has exactly ONE caller (`python_runner`'s single-backtest path). `backtest/optimizer.run_sweep`
  replays one frame, so **the optimizer, sweeps and the stress test's pooled sensitivity have no
  fill-clock stream** — they would have replayed a primary-only book and ranked it against a baseline that
  has re-entries. They **REFUSE** now, naming the fix. ⚠ **`b_leg` had to PIN it False and that
  one is not cosmetic**: SOS Fade never places an order in that fork so there is no primary to follow,
  and `BLegStrategy.run_dual` raises — an inherited `True` would have killed **every B-LEG lab
  run** on a `NotImplementedError`. ✅ The live bot is unaffected: its instance config states
  `exec_secondary: false` explicitly, and `algos/live/bridge.py` refuses the config outright.
- ⚠ **IT HAD NEVER OPENED A POSITION ON REAL DATA BEFORE THAT RUN, AND THREE WEEKS OF GREEN TESTS
  SAID OTHERWISE.** `run_dual` built its fill-clock signal as a namedtuple without `last_conf_high` /
  `last_conf_low` — the STRUCTURE runner trail's anchors, which the shared `_advance_stage` reads on
  **every** managed bar, primary or secondary — so the first fill-clock bar after any secondary fill raised
  `AttributeError`. Not a wrong number: the run died. 🔴 **The reason no test caught it is the
  transferable part: `tests/test_secondary.py` hand-builds its own fill-clock bar as a `SimpleNamespace`
  carrying both fields.** The fixture was more complete than production, so every test exercised a
  shape the code never produced. The regression test now DERIVES the required set by reading
  `_advance_stage`'s own source for `sig.<field>` and asserting the real `run_dual` supplies all of
  them — a hand-written list would have re-frozen exactly the assumption that failed. **Watched red
  against the bug, naming both missing fields.**
- ⚠ **WHERE THE LIMIT RESTS IS NOW A NUMBER (`exec_sec_retrace`, default 0.382), AND SWEEPING IT
  ANSWERS A QUESTION WORTH RECORDING FOR ITS SHAPE RATHER THAN ITS WINNER.** Aaron asked what
  happens if the 38.2% retrace comes out and the re-entry simply takes the fill-clock SOS. The 0.382 was a
  hardcoded constant; it is a config field now, byte-identical at the default (pinned by the suite)
  and refused outside `[0, 1.0)` at construction — 1.0 is the leg ORIGIN, where the stop is, so an
  entry there has a zero stop distance and the order is silently cancelled, which would report *the
  secondary took no trades* as though that were a finding. ✅ **Four full-history replays, run in
  parallel, with 0.382 as the CONTROL** (it reproduced 190 trades / +165.46R exactly, which is what
  says the refactor moved nothing):

  🔴 **Entering on the SOS is the WORST row and the result is monotonic — deeper is better** — which
  is mechanical rather than mysterious: **the stop is the shift leg origin whatever the entry**, so at
  0.382 the stop distance is 0.618 of the leg and at 0.0 it is the whole leg. A shallower entry is a
  WIDER stop, hence a SMALLER position for the same risk, and less room between the fill and the 15m
  targets. **You fill more often and each fill is worth less** — +2 trades for −11R. ⚠ **But the
  ranking is one trade and the last two columns say so: strip each row's best and all four are
  NEGATIVE (−2.03 / −1.90 / −1.76 / −3.84).** The sweep is not measuring which entry is better, it
  is measuring how large that April 2023 winner grew as the stop tightened, which is arithmetic.
  **The clincher is the bottom row — 0.5 posts the worst hit rate in the table (1 win, 4 losses of 9)
  and the best total.** Drawdown is flat at 6.53R across all four, because it belongs to the primary
  book. ⚠ **So: do not enter on the SOS, and equally do not read this as a reason to move off
  0.382.** The lever does not change the verdict above; it changes the size of one fill.
- 🔴 **THE GATES WERE LOOSENED FOUR WAYS ON 2026-08-19 AND EVERY DOOR IS WORSE. THE SWEPT-STOP
  RE-ENTRY LOSES MONEY.** Aaron's case: *in at 0.618, price takes the 0.886, swipes the stop, comes
  back, bounces off a higher fib and runs — the whole trade missed.* Three levers now exist to ask
  that question (`exec_sec_require` ∈ Breakeven / Any close / **Stopped only** / None,
  `exec_sec_zone_deep`, `exec_sec_zone_shallow`), all defaulting to the shipped rule. **9 real
  replays over 156,543 M15 + 2,343,987 M1 bars (2020-01-01 → 2026-08-18), control reproducing lab
  run `fbfc89d71fb4` exactly at 160 primaries + 7 secondaries.** The shipped rule wins on book R
  (374.17), on R-with-its-best-trade-removed (−0.81 against −1.49 … −5.70) and on drawdown
  (−15.01R against −18.08R), and the ordering is **monotonic in how much was loosened**. ⚠ **Asked
  in isolation the swept-stop door is 7 trades / −0.68R / 2 wins / 4 full −1R losses** — the pattern
  is real and taking it systematically loses. ⚠ **`exec_sec_zone_deep` is INERT on top of it** (1.0
  and 0.886 give the identical book): those legs were blocked by the breakeven gate alone, never by
  the zone, and only measuring the two separately showed it. ⚠ **Zero primaries displaced in any
  cell**, so none of it is the one-slot queue effect. ⚠ **The R differences sit inside the 15.06R
  jitter band — the DIRECTION (9 of 9) and the win/loss counts (1/1 → 3/9) are the signal.** 🔴 **The
  finding under the finding: the re-entries that DO fire mostly SCRATCH** — four of the control's
  seven land inside the ±0.15R band and eleven of "any close"'s fourteen are ≈0 or exactly −1R. A 1m
  entry gets a 1m-tight stop and is then handed to the 15m structure trail, which ratchets to
  breakeven long before a 15m target. **Entry confluence is answered; the EXIT ladder for a 1m entry
  has never been varied independently of the primary's.** Full grid: `sos_fade_optimization.md`
  → Run 23, part 1.
- **MEASURED 2026-08-19 (Run 23, parts 2–3) — THE EXIT LADDER IS WHERE THE RE-ENTRY WAS BROKEN, AND
  "HOW MANY RE-ENTRIES" IS ONE.** Four more levers, all defaulting to the shipped rule
  (`exec_sec_max_per_setup`, `exec_sec_req_m1_dir`, `exec_sec_be_at`, `exec_sec_tp1_pct`), 17 more
  replays on the same bars. 🔴 **Depth 2 / 3 / 5 / unlimited are BYTE-IDENTICAL** — in 6.6 years
  exactly one setup ever offered a second re-entry (2024-01-16 L, −1.00R) and a third never existed,
  so the cascade question has a sample of **n=1**. 🔴 **And the rule already ships**: a re-entry that
  closes at stage 0 sets `sec_stop_dir` → `mark_dead`, so a cascade can only continue through a
  SCRATCH, never through a loss — *"how many before settling into losses"* is answered in code as
  **the first real loss ends it**. 🔴 **`exec_sec_be_at="TP2"` (hold the initial stop through TP1) is
  WORSE and overturned the prediction that prompted it** — 1 win / 4 losses, and the three trades it
  rescued from a +0.05R scratch each became exactly −1.00R. **The breakeven ratchet was protecting
  them, not robbing them.** 🟢 **Banking part of the re-entry at TP1 (`exec_sec_tp1_pct`) is the
  first change in 26 replays that works** — win/loss goes **1/1 → 4/1** and ex-best turns positive
  for the first time. The diagnostic that found it: **three of the seven re-entries exited at exactly
  +$0.30 = `exec_be_buf_tk` (30 ticks)**, one of them $2.65 past TP1 with nothing banked. ⚠ **It
  costs the tail**: 50% banked cuts 2023-04-03 from +79.07R to +42.79R, and **that one trade IS the
  secondary book**. 🟢 **Best configuration measured: `exec_sec_req_m1_dir=True` +
  `exec_sec_tp1_pct=50`** — 5 trades, 4/1, **+3.19R ex-best**, best drawdown of all 26 replays
  (−14.92R), **and 32.28R BELOW control on total book R.** ⚠ **The two levers COMPOUND (+0.08 and
  +1.52 alone, +4.00 together) because the filter changes which 1m bar arms 2020-09-15 and banking
  then makes that trade a winner — a filter that looks inert on one exit ladder is not inert on
  another.** ⚠ **Zero primaries displaced in any of the 26 cells.** **Nothing shipped: this is a
  return-for-consistency trade Aaron makes, not one a table makes, and the shipped default is the
  choice consistent with this repo's stated philosophy.** Full grids:
  `sos_fade_optimization.md` → Run 23.
- 🟢 **SHIPPED 2026-08-20 — FIVE DEFAULTS MOVED TOGETHER, A SIXTH SETTING IS NEW, AND THE
  FEATURE IS A DIFFERENT ONE AFTER IT.**
  `exec_sec_req_div` OFF, `exec_sec_trigger` = `FVG in zone`, `exec_sec_stop` = `0.886`,
  `exec_sec_tp_r` = 1.25, `exec_sec_tp1_pct` = 50, and a new `exec_sec_risk_pct` = 50. Over the same
  7.9 years (2018-09-14 → 2026-08-18, 155,807 M15 + 2.74M M1) the leg goes from **10 re-entries to
  54**, and less its single best trade from **−1.77R to +7.16R**. ✅ **Primaries are +206.20R in
  every cell to the decimal and zero were displaced**, so all of it is the re-entries.
  🔴 **THE OLD DEFAULT COULD NOT FIRE ON THE BOOK IT SHIPPED WITH, WHICH IS WHY IT READ AS
  MARGINAL** — it demanded a live 15m divergence while the primary arms on a SWEEP (`exec_arm_div`
  OFF, shipped). Measured over the most recent year: **0 re-entries in 12 months.** The "ten trades
  cannot tell a small edge from a small negative one" verdict above was therefore measured on a
  gate, not on a setup, and it stands as a description of that fortnight rather than of this
  feature. ⚠ **Pin the old six to reproduce anything measured 2026-08-07 → 2026-08-20.**
- **THE EXIT LADDER WAS THE FIX, AND THE COLUMN THAT CHOSE IT WAS *LESS THE BEST TRADE*.** With the
  gap trigger on, **72% of re-entries reach +0.25R, 56% reach +0.5R, 37% reach +1R and 20% reach
  +2R; the median excursion is +0.56R** — so the scratches were never bad entries, they were a 1m
  entry handed a 15m target with a breakeven ratchet in front of it. Twelve replays of the rung and
  what banks there (re-entry R, then the same figure with its best trade removed): 0.5R/half
  **+0.14 / −5.35**, 0.75R/half **+22.03 / +4.83**, 1R/half **+24.43 / +5.63**, **1.25R/half +27.84
  / +7.16 ← ship**, 1.5R/half **+22.82 / +1.32**, 2R/half **+22.54 / +0.79**, and the old shape
  (no rung, nothing banked) **+29.50 / −0.36**. ⚠ **The headline column would have kept the old
  shape.** ⚠ **The rung also moves BREAKEVEN**, because the ratchet fires at stage 1 and stage 1 is
  this rung — the two are one decision, and 1.25R/half was the pair that won, not either alone.
- ⚠ **THE TRAIL AND THE SECOND RUNG WERE ASKED AND THE ANSWER WAS: CHANGE NOTHING.** Six more
  replays at 1.25R/half. The shipped 1% swing trail gives the best re-entry total (**+27.84R**) and
  by a distance the best PRIMARY book (**+206.20R** against +102.08R at 0.5% and +138.88R at 2%),
  because the trail is shared. Banking half at the SECOND rung as well collapses the leg to
  **+5.98R**. 🔴 **A re-entry-only trail at 0.5% has the best ex-best figure of anything measured
  (+10.12R) and is UNBUILT** — it is worth ~3R over eight years and would need its own lever, which
  is why it was left as a note rather than a build.
- 🔴 **THE RE-ENTRIES DEEPEN THE PRIMARY'S OWN DRAWDOWN RATHER THAN DIVERSIFYING IT — the first hard
  number this repo has on the correlation the root philosophy warns about in words.** Worst
  closed-trade drawdown on a $10k start: primaries alone **51.8%** (181 trades, +206.20R), with the
  re-entries at full weight **68.1%** (235 trades, +234.04R). **It is the SAME drawdown made
  deeper** — both trough in the same 2023-04-05 → 2024-10-29 stretch, inside which the primaries
  lose 6.34R and the re-entries lose a further 4.70R. They come off the setups the primaries just
  lost on, so they fail together. ⚠ Risk-adjusted it is WORSE, and that is the honest reading:
  4.0 R-per-drawdown-point becomes 3.4.
- **`exec_sec_risk_pct` (new 2026-08-20) IS THE ANSWER TO THAT, AND 50 WAS NOT CHOSEN OFF THE
  CURVE.** It scales the re-entry's LOT only — same bars, same entries, same exits — so **the R
  total is IDENTICAL at every size (27.84R)** and only the account-weighted contribution moves:
  ¼ **+6.96R / 56.2%**, ⅓ **+9.19R / 57.6%**, **half +13.92R / 60.4% ← ship**, ¾ **+20.88R / 64.4%**,
  full **+27.84R / 68.1%**, against **51.8%** with the feature off. Every step buys ~**1.6R per extra
  drawdown point** at a near-constant rate — a straight line with no knee, against ~**4.0R per
  point** for the primaries. **So the size was chosen on CONCENTRATION: one trade is +20.68R of the
  leg's +27.84R, the next is +6.06R, and the whole thing less its best is +7.16R over 54 trades.**
  ⚠ 🔴 **A BACKTEST SUMMARY WILL REPORT THE SAME R AT A QUARTER SIZE AS AT FULL** — halving the lot
  halves the win and the loss together. Multiply by this field before comparing a re-entry's R with
  a primary's, or the sizing decision is invisible in every table this repo prints.
  ⚠ It refuses 0 or a negative rather than clamping: a zero lot fills, closes and lands in the trade
  list at 0R — a trade that looks taken and moved nothing. The way to stop taking re-entries is the
  feature switch.
- ✅ **THE SUSPECTED CROSS-TALK BUG IS NOT REAL, CHECKED AND CLOSED 2026-08-20.** Aaron's report was
  that a stopped re-entry looked like it was retiring whichever setup was CURRENT rather than its
  own. Every setup-shutdown across seven full-history replays was traced to the trade that caused
  it: **zero mismatches, zero orphans.** ⚠ **What IS true and reads like it**: the shutdown fires
  whenever a re-entry closes before reaching its first rung, INCLUDING small winners — 31 shutdowns
  from 13 stop-outs in one run. That only changes a book if the one-per-setup cap is turned off, so
  it is a doc/code wording mismatch to tidy on the next pass, not a defect.
- ⚠ **THE PARITY GATE CANNOT SEE ANY OF THIS, AND AN EARLIER NOTE IN THIS SESSION SAID THE OPPOSITE.**
  `compare_strategy.py` replays 15-minute bars through `.run()`; every re-entry lever lives on the
  fill-clock path behind `run_dual`. **No `exec_sec_*` default can move the gate**, which is why six of
  them could change at once. It was still RUN rather than reasoned about, because that is what
  rule 22 asks for: GREEN (exit 0) on `engines/VANTAGE_XAUUSD, 15_4fef8.csv` and `…_49f80.csv` at
  `--warmup 1000`, both before the change and after it. ⚠ **Two other exports sitting on this
  machine (`a9c92` at bar 1356 on closed R, `a9caa` at bar 20608 on the short stage) are RED — and
  were RED in the identical place before this change**, so they are not it; their provenance is
  undocumented (neither is named anywhere in the repo) and a pre-existing red is still a red, so
  they are worth chasing on their own. ⚠ **Warm-up is not optional**: at the default warm-up all four report a
  mismatch on bar 16, which is the engines still filling.
- **NOT USABLE LIVE** — `algos/live/bridge.py` REFUSES `exec_secondary` outright
  (`UnsupportedStrategyConfig`). The lab can run it; the bot cannot. ⚠ **CORRECTED 2026-09-01 —
  the refusal is unchanged and still right, but the three reasons this bullet used to give are all
  now false.** The live runner is NO LONGER single-timeframe (it opens a second `BarFeed` and
  merges it through this package's own `dual_clock.DualClock`, the same object `run_dual` drives);
  the second stream is NOT a 1m one (it is `exec_sec_fill_tf_min`, **5 minutes by default since
  2026-08-21** and the caller's choice — the parameter still named `df1m` is a name its own
  docstring says not to trust); and building that feed is no longer an open item. **The reason it
  refuses TODAY is the order path**: the bridge mirrors ONE entry limit and one ratcheting stop, so
  it has no path that places the re-entry's own order at its own price. That is G18 stage 2, and
  the same sentence is why partial take-profits and scale-in are refused — read the three refusals
  together. ⚠ The refusal fires at strategy construction, BEFORE the second feed is built, so no
  bot drives two frames today. See `docs/LIVE_TRADING_PIPELINE.md` → G18.
- 🔴 **AND THIS LADDER IS THE SECOND BLOCKER, NOT JUST THE FEED (2026-09-01).** The bridge has NO
  exit path at all — every exit reaches the broker as a stop move — while the re-entry banks
  **100%** at its target under the reclaim trigger (`exec_rec_tp1_pct`) and **50%** under the gap
  trigger (`exec_sec_tp1_pct`). So placing the re-entry's ENTRY is not enough: the scale-out would
  have nowhere to go and the bot would RIDE where this file's numbers BANKED. ⚠ **Either the bridge
  learns to bank, or `exec_sec_tp1_pct` / `exec_rec_tp1_pct` go to 0 and every re-entry figure here
  is re-measured** — `+32.50R over 44 trades` was measured WITH the bank and does not survive
  turning it off. ✅ **HALF-RESOLVED 2026-09-01: the bridge can now bank PART of a position**
  (`_sync_partials`), so the GAP trigger's 50% is no longer a live blocker — its remaining blocker
  is the missing second ENTRY. ⚠ **The RECLAIM's 100% still is one**: taking the WHOLE position off
  at a price needs a full-exit path that does not exist, and 100 is the value that measured best
  for that trigger. **So on today's build the gap trigger can reach live and the reclaim cannot**,
  which is the opposite way round from where every published figure came from. ⚠ **`exec_short_hold` had the same shape and was reachable TODAY** (its
  `exec_sh_tp1_pct` defaults to 100 and nothing refused it); `bridge.price_triggered_banks` now
  mirrors `Execution._tp1_pct` branch for branch, so **re-read it against this ladder whenever a
  rung changes.**

#### 🔴 THE TWO TRIGGERS WANT OPPOSITE EXITS — MEASURED 2026-09-01, AND IT DECIDES THE LIVE ROUTE

**157,004 M15 + 470,995 M5 bars, 2020-01-01 → 2026-08-23, PU Prime demo bars, one `run_dual`
replay per row.** Base params are the LIVE BOT'S OWN `config.json` with only the named field
moved — ⚠ **not** the stage-1 proof file, which sets `exec_sec_trigger` to the reclaim while the
bot states the gap, and that field decides which banking percentage is even READ.

| configuration | trades | total R | primaries | re-entries | re-entry R | maxDD R |
|---|---|---|---|---|---|---|
| re-entry OFF (control) | 158 | +104.09 | 158 / +104.09 | 0 | +0.00 | −4.22 |
| **reclaim** · `exec_rec_tp1_pct` **100** | 188 | +125.09 | 158 / +104.09 | 30 | **+21.00** | −6.66 |
| **reclaim** · `exec_rec_tp1_pct` **0** | 188 | +111.26 | 158 / +104.09 | 30 | +7.16 | −6.66 |
| **gap** · `exec_sec_tp1_pct` **50** | 205 | +116.72 | 158 / +104.09 | 47 | +12.62 | −4.65 |
| **gap** · `exec_sec_tp1_pct` **0** | 205 | +124.21 | 158 / +104.09 | 47 | **+20.11** | −5.16 |

🟢 **BEST SETTING, AND IT IS DIFFERENT FOR EACH TRIGGER — DO NOT CARRY ONE ACROSS TO THE OTHER.**

- **Reclaim Entry → BANK IT ALL: `exec_rec_tp1_pct` = 100.** Turning the bank off costs
  **−13.84R of a +21.00R contribution — two thirds of the edge.** Its target is far out
  (`exec_rec_tp_r` = 3.25) and the trade does not survive the retrace back from it.
- **FVG in zone (the gap) → BANK NOTHING: `exec_sec_tp1_pct` = 0.** Banking half COSTS
  **−7.49R** against letting it run (+12.62R vs +20.11R). Its target is near
  (`exec_sec_tp_r` = 1.25), so taking half off there caps the trades that were going much
  further while doing nothing for the ones that fail.
- ✅ **FIXED 2026-09-07: the default moved 50 → 0** (Aaron's call, on this table). The pin in
  `tests/test_secondary.py` moved with it and now also pins `exec_rec_tp1_pct` at 100, so a future
  "make these two agree" edit goes red instead of quietly costing the reclaim two thirds of its
  edge. ⚠ **The live bot was ALREADY at 0 and it was the DEFAULT that was wrong** — the drift ran
  the other way from every other setting on that bot.
- **The shipped 50 was therefore the WRONG value for the trigger the bot is actually set to**, and
  the two facts were never read against each other because every published re-entry figure came
  from the reclaim while `config.json` states the gap.

🟢 **AND IT IS THE ROUTE TO LIVE.** The bridge could not bank at a price at all, so a re-entry
that banks cannot go live as measured. The gap trigger does not need to bank — **at 0 it is both
better AND live-compatible with no new order path**. The reclaim needs the bank, so it waits on
the partial-exit path.

⚠ **The primaries are IDENTICAL in all five rows — 158 trades, +104.09R every time.** The
re-entry never displaces a primary here, because it only arms after the primary on that leg has
CLOSED. So its contribution reads directly off the difference, which is unusually clean for this
repo and worth not squandering: **do not re-derive it from a run with a different basis.**

⚠ **LAB FINDINGS, and there will never be anything else.** No parity gate covers a re-entry —
the Pine has none — so `compare_strategy.py` has exercised exactly ZERO of these trades.
⚠ **30 and 47 trades over 6.6 years.** Enough to act on, not enough to be precise about; the
error bars on a per-trigger figure are wide and stacking does not narrow them.
⚠ **Re-run before trusting it after any entry-logic change**, and re-run
`backtest/tools/overlap_audit.py` with it — both were stale for three weeks the last time.

Reproduce: `command-center/backend/.venv/bin/python` on a script that loads the live
`config.json`, flips `exec_secondary` on, and varies only the named field — the five rows differ
in nothing else.

### Reclaim Entry, and the combined value that runs it beside the gap

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Reclaim Entry, and the combined value that runs it beside the gap*.

🔴 **THE RECLAIM HALF READS ITS OWN SETTINGS — `exec_rec_require` / `exec_rec_stop` /
`exec_rec_tp_r` / `exec_rec_tp1_pct` — UNDER BOTH VALUES, AND THE SHARED `exec_sec_*` FIELDS ARE
DEAD TO IT.** That is what makes the combined value possible at all: the two halves want opposite
preconditions, different stops and different ladders, and one set of fields can only hold one of
each. Their defaults ARE the measured configuration, so selecting the trigger and touching nothing
else reproduces the book below.

**Why the two halves may share one position slot, one latch and one `_traded` stamp.** They fire on
DISJOINT setups structurally: a primary either reaches TP1 (stamping the breakeven latch, never the
loss latch) or closes at stage 0, which does the reverse. ⚠ **That is the whole safety case, so
validation REFUSES any pairing but `Breakeven`/`Stopped only`** rather than letting them race for
the latch. ✅ **MEASURED as 0, not "rare": of the 107 re-entries the two produce, ZERO share a
setup, ZERO overlap in time, and neither ever blocks a primary.**

#### The numbers — `run_dual` over 187,102 M15 / 2,801,964 M1 bars, 2018-09-14 → 2026-08-18

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The numbers — `run_dual` over 187,102 M15 / 2,801,964 M1 bars, 2018-09-14 → 2026-08-18*.

🔴 **ONE BALANCE, IN TIME ORDER — NOT A SECOND BOOK ADDED AFTERWARDS.** `run_dual` walks both feeds
on one clock through one `Execution`, and a re-entry sizes off `self.equity` at the moment its
order is PLACED, so the balance a primary sizes against already holds every re-entry that closed
before it. **MEASURED: 179 of the 181 primaries carry a DIFFERENT position size** in the reclaim
book than in the primary-only one (the first two predate the first re-entry) — the third is
$906 of risk against $1,042, and it compounds from there. This is the opposite of
`exec_recovery`, which is computed over a FINISHED book and can therefore neither compound into
the main curve nor be blocked by it; see `strategies/python/loss_recovery/CLAUDE.md`.

⚠ **"Identical" below means the 181 primaries take the same SETUPS at the same prices for the same
R** — no primary is displaced, delayed or blocked, which is what makes the R difference attributable
to the re-entries. **It does NOT mean their dollars are unchanged**, and an earlier draft of this
line said "byte-identical in every row", which reads as exactly the bolt-on defect this paragraph
exists to deny. **A sentence about a comparison has to name the BASIS it holds on.**

🔴 **THE COMBINED BOOK IS EXACTLY THE TWO HALVES — matched trade for trade on entry price, R summing
to the cent (13.09 + 19.00 = 32.09), 54 + 53 = 107, and 0 trades in one book and not the other.**
That is the claim the build had to earn, and it was earned on the third attempt; the two failures
are below because each is a rule.

⚠ **The last column is the one to read, not R** — a book that adds R and loses money is the normal
case here, because re-entries fire inside drawdowns and deepen the holes that set the risk ceiling.
The shipped gap trigger is the example: it adds 13.1R and finishes at **2,981** against
primary-only's **7,188**, because it can only carry 8.5% risk. The reclaim does not have that
problem (11.00%, the same as no re-entry at all).

✅ **It does the job it was built for, in both periods Aaron named.** Sep 2021 – Jan 2023:
+2.6R → **+9.8R** combined. Mar 2023 – Sep 2024: **−3.6R → +6.9R**, the re-entries adding +10.5R and
flipping a losing stretch. ⚠ **The gap trigger alone made that second window WORSE** (−4.1R), which
is the sharpest argument for the reclaim existing.

⚠ **The two halves are out-of-sample mirror images, and combining is what fixes that.** Split at
2022-09-01, re-entries only: the gap is **+11.0R then +2.1R**, the reclaim **+2.0R then +17.0R**,
and both together **+13.0R then +19.1R** — positive in both halves where each alone leans on one.
✅ Neither is carried by a single trade on the reclaim side (its best is +3.0R, the target caps it).

#### 🔴 Two control replays, two rules — the story is in the build notes, the rules are here

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 Two control replays, two rules — the story is in the build notes, the rules are here*.

**1. Which rule prices a side is the CONFIGURED TRIGGER's, never whichever block latched last.**
Section 3's fill-clock latch runs under EVERY trigger, including the two with no shift leg to price off,
because it moves `_l_leg`, which `_traded` / `_dead` / `_used` all read. Keying the entry price off
the latch let a fill-clock structure event price a GAP book at a 38.2% retrace of a fast-feed leg: **the
shipped book silently gained 4 re-entries and 4.9R.** Under the combined value ownership falls to
**which precondition is open**, which is well-defined precisely because the gates are disjoint.
⚠ **Do NOT gate section 3 behind a trigger test to "tidy" this** — tried twice, and both attempts
are the two rules on this list.

✅ **Rule 2 found a real defect rather than only restoring additivity.** It removed one reclaim
re-entry that had armed at the deep edge **without price ever reclaiming**, worth **+1.0R**.
⚠ **Every reclaim figure quoted before this is the pre-fix book — 156.9R over 54, not 157.9R over
53.**

#### The re-entry settings, split three ways in the editor (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The re-entry settings, split three ways in the editor (2026-08-21)*.

⚠ **No row count here, deliberately.** This section said "the 19 settings … the 8 both halves
read" and was stale within a day — the fill clock and the resting-order rule landed in the shared
group and made it 21 and 10. **A count in prose is a number with no test under it.** The exact
dead SET is pinned by `test_the_contract_kills_exactly_the_rows_the_tests_above_pin`; the group
sizes are whatever the contract says, and `python3 -c` over the meta file answers it in a second.
⚠ **A new row added to this block lands in the shared group by default and nothing asks whether it
is dead under a trigger** — that test only fails when a row IS killed without proof, never when one
that should be killed is not. Ask the question by hand when you add one.

⚠ **The retrace is the odd one — it is dead under the SHIPPED trigger too.** Only the `Structure shift`
retraces a leg; the gap rests at the primary's own price and the reclaim at the deep edge. It is
killed under all three of the other values.

🔴 **A DEAD ROW IS NOW HIDDEN, NOT GREYED (2026-08-27).** It was drawn greyed with its reason
beside it; on the shipped defaults that is SEVENTEEN dead controls the reader scans past to reach
the live ones, and Aaron reversed it: *"hide them, like everything else"*. The contract did not
change — the same key, the same conditions, the same reasons — only what the editor does with it.
⚠ **The reason is still REQUIRED on every one**: the finished-run params panel prints it, to say
why a setting did nothing on a run already taken.
⚠ **Not cosmetic either way — `stress_tester.param_is_reachable` stops perturbing a dead row**,
which is the point: shifting a setting the strategy never reads books a guaranteed 0% change and
reads back as *"tested, rock solid"*. That answer is unchanged by the hiding.

🔴 **THE SHALLOW ZONE EDGE LOOKS AS DEAD AS THE REST AND IS NOT, AND THAT IS THE TRANSFERABLE
FINDING.** The reclaim ignores the zone by design — this file says so and a test says so — so it
was on the dead list on the way in. It is live, because **section 3's fill-clock latch runs under
every trigger, its gate reads the zone, and it writes the same per-setup bookkeeping the reclaim's
own arm is measured against.** ⚠ **Reading the consuming line was not enough here**: the other nine
rows each have ONE reader inside an explicit source branch, and this one launders through shared
state with many. ⚠ **At the shipped cap of one re-entry per setup the cap refuses first and MASKS
the difference**, so the probe that settled it had to turn the cap off — a check that would have
agreed with the wrong answer at the default. Pinned by
`test_the_SHALLOW_zone_edge_is_NOT_dead_under_the_reclaim_so_it_is_never_hidden`, which is the only
thing standing between the next reader and a wrong answer on screen.

**TESTED:** 5 new tests in `tests/test_secondary.py` — 4 pinning the deadness claims at the arm and
the ladder, 1 the counter-case, 1 tying the contract's dead set to them. **9 mutations, 9 killed**
(357 strategy tests green, 49 backend param-gate/sensitivity tests green).
**PARITY:** `compare_strategy.py` green on the 2026-08-21 export at `--warmup 100`. ⚠ **The gate is
structurally blind to all of this** — it replays 15m bars through `.run()` and every re-entry lever
lives on the fill-clock path behind `run_dual`.

#### A re-entry records WHAT THE TRADE BEFORE IT DID, and that is a second question (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *A re-entry records WHAT THE TRADE BEFORE IT DID, and that is a second question (2026-08-21)*.

🔴 **It is NOT a rename of `*_src`, and collapsing the two is the mistake to avoid.** `src` is the
trigger that was CONFIGURED; this is the outcome that was OBSERVED. They agree under every shipped
configuration, which is exactly why they must stay two fields — point the gap half at
`Stopped only` and a gap-triggered re-entry is a re-entry after a LOSS, and the chart has to say so.

⚠ **`None` means the run could not tell, and must never become a word downstream.** A re-entry
armed through the `None` precondition follows a primary that may not have traded at all.
⚠ **Stopped is tested before closed.** `_prim_closed_sos_*` is stamped on every close whatever the
outcome, so a stopped primary sets both latches; asking "closed?" first calls every stop-out a
plain close.

🔴 **`SecondaryArm.update` has TWO `SecArm` returns and a test can leave through only one.** The
first version of these tests passed while the mutation that stripped the field off the plain return
reddened NOTHING — the resting-order rule had been defaulted ON in the same tree, so every test in
the file was exiting through the other branch and the untested return was free to be wrong. **A
duplicated construction is only as covered as its least-visited branch**, and the fix was to
parametrise the tests over the rule rather than to trust the default.

#### Nothing in the re-entry layer says "1 minute" any more (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Nothing in the re-entry layer says "1 minute" any more (2026-08-21)*.

⚠ **A saved run or bot config carrying the old string is REFUSED**, not silently reinterpreted —
the same behaviour as the `Deep-edge reclaim` → `Reclaim Entry` rename the day before, and for the
same reason: quietly falling back to a default would replay a different strategy under the old
name.

🔴 **THE PANEL GROUP NOW NAMES NO TIMEFRAME AT ALL, AND THAT IS THE RULE, NOT THE FIX.** It read
`Secondary re-entries (1m)`; the obvious change was `(5m)` and it would have been the same defect
one turn later. **A heading must not hardcode a number the row beneath it owns** — the fill clock
is one setting, in one place, and every other surface points at it. `param-gates.spec.ts` pins the
ABSENCE of a timeframe in the group name rather than the presence of a particular one.

⚠ **A MEASUREMENT TAKEN ON 1m DATA STILL SAYS 1m, EVERYWHERE, AND WAS DELIBERATELY LEFT ALONE.**
Rule 4 cuts both ways: you may not edit a recorded figure to match today's default any more than
you may invent one. The sweep skipped every line carrying an R figure, a bar count or a date — so
`1m 2,804,720 bars / +147.56R` reads exactly as it was run, and the prose around it no longer
claims that is what the strategy does now.

⚠ **The IDENTIFIERS were left alone and that is a debt, not something to be proud of** — `df1m`,
`sig1m`, `M1State`, `Structure1m`, `_Bar1mSig`. Renaming a public parameter moves every caller
(`python_runner`, `run_report`, the portfolio stack, the tests) for a cosmetic gain, and this layer
is one promote away from money. `run_dual`'s docstring now says in as many words that the second
frame's timeframe is the caller's choice and that the parameter name is the one thing in there
which cannot be trusted.

⚠ **A DUPLICATE OF THE SECTION ABOVE SHIPPED IN `e107345` AND WAS DELETED HERE.** Two identical
copies, ~1,950 bytes, from an insert script run twice against an anchor that was unique the first
time. It was caught by the NEXT insert refusing — `assert s.count(anchor) == 1` — rather than by
anybody reading the file. **The assertion that stops a script writing twice is the same one that
tells you it already did; a script that inserts without counting its anchor has no way to notice.**

⚠ **`exec_rec_stop` of `Shift leg` or `swing low` is REFUSED**, stricter than the gap trigger's rule,
because the entry is a FIXED price and a fill-clock swing can land either side of it. That refusal is
also what lets section 2c read the stop anchor BEFORE the shift leg latch — both legal anchors are pure
reads of the 15m fib. ⚠ **Do not hoist that lookup for the other triggers**: under `Shift leg` the
anchor IS the leg assigned by that latch.

⚠ **The exit ladder is not a detail on this half.** All-out at 3x its own risk is the default and is
why the numbers hold; the shipped bank-half-at-1.25x ladder gives **3,111x, worse than taking no
re-entry at all** (3,582x). A re-entry priced this tight has to be allowed to pay for the ones that
fail.

**TESTED:** 350 strategy tests green (24 new), 11 rules each watched RED by a named mutation —
detail in the build notes. **PARITY:** `compare_strategy.py` exit 0 on `4fef8` and `49f80` at
`--warmup 1000`, before and after. ⚠ **The gate is structurally blind to all of this** — it replays
15-minute bars through `.run()` and every re-entry lever lives on the fill-clock path behind
`run_dual`, so a green run means the primary is untouched and nothing more.

⚠ **NOT USABLE LIVE, and no new refusal was needed** — `algos/live/bridge.py` already refuses
`exec_secondary` outright, so the whole re-entry layer including both new values is covered.
