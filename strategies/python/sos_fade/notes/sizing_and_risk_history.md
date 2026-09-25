# Notes — Sizing and risk — the venue ceiling and the 2026-09-06 default move

How the venue lot ceiling reaches this bot's default account, and the story behind the 2026-09-06 defaults move (scale-ins on, both re-entry triggers at once). Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The venue ceiling reaches THIS bot's default account too (2026-09-03)

`backtest/portfolio/account.py` gained a broker lot ceiling on 2026-09-02 — 100 lots of gold,
measured on the live account — and `SoloAccount` carries it. **This class builds a `SoloAccount`
whenever it is constructed without one, so the ceiling is on by default here**, and the comment
in `execution.py` saying otherwise was true until that day and is now corrected rather than left
to be believed. The rules for the ceiling itself live in `backtest/CLAUDE.md`; only what it means
for this bot is here.

- ⚠ **The default opening balance is $1,000,000 and the ceiling first bites above ~$927,000**, so
  anything constructing `Execution` with neither an account nor a capital figure is already sizing
  under the clamp. That is not hypothetical — it is what turned `test_sizing_matches_risk_over_stop_distance`
  red: the test asserted the sizing FORMULA through a clamp that has nothing to do with it.
- ✅ **Two tests now, because they measure two different things.** The formula test runs at
  $100,000, under any of these ceilings, so only its own subject is acting;
  `test_the_venue_ceiling_clamps_a_size_the_broker_would_REJECT` keeps the $1m case as COVERAGE of
  the clamp. **The failing case was kept rather than deleted** — a red test is the one moment the
  behaviour is easy to pin.
- ⚠ **The ceiling's measured numbers are written out in that test, not imported.** Importing them
  would make it agree with whatever the ceiling becomes, so a ceiling raised by accident would stay
  green. 100 lots is a measured fact about the venue, not a preference.

🔴 **THE PARITY GATE IS RED AND IT IS NOT THIS.** `compare_strategy.py` on the newest decision
export (`VANTAGE_XAUUSD, 15_2a817.csv`, 21,767 rows) exits 1 at **bar 16, `px_s_stage`: py=1
pine=0** — and the IDENTICAL red reproduces at `392dc89f`, i.e. before any of 2026-09-03's work.
**Proving the red at an older commit first is the rule here, because a stale export reds this gate
exactly like a bug does**, and that is what stopped the lot ceiling being blamed for it. ⚠ It is
not diagnosed: nobody has yet established whether the export or the code is the older side.

## 🔴 THREE DEFAULTS MOVED 2026-09-06 — SCALE-INS ON, AND BOTH RE-ENTRY TRIGGERS AT ONCE

Aaron's call, to measure the bot with everything on before deciding what reaches the demo account.

| field | was | now |
|---|---|---|
| `exec_scale_in` | `False` | **`True`** |
| `exec_sec_trigger` | `"Reclaim Entry"` | **`"FVG in zone + Reclaim Entry"`** |

⚠ **`exec_secondary` was ALREADY `True` and `exec_sl_deep` is still `False`** — neither moved. The
deeper-entry stop was measured on 2026-09-06 under these new defaults and left OFF; see below.

🔴 **EVERY FIGURE IN THIS FILE MEASURED BEFORE TODAY DESCRIBES A DIFFERENT BOT.** Pin
`exec_scale_in=False` and `exec_sec_trigger="Reclaim Entry"` to reproduce one. This is the same
cost the 2026-08-05 minimum-stop default change carried and it is stated the same way.

⚠ **The combined trigger REQUIRES `exec_sec_require="Breakeven"` and `exec_rec_require="Stopped
only"` and validation refuses any other pairing.** Both are already the defaults, so selecting it
changes nothing else — but a future edit to either makes the config raise at construction rather
than letting the two halves race for one latch.

⚠ **THE LIVE BOT DOES NOT PICK ANY OF THIS UP.** `sos_fade_demo` PINS all 116 of its settings in
its own instance config, so a default move cannot reach it — and it currently states
`exec_scale_in: false` and `exec_sec_trigger: "FVG in zone"`, i.e. the gap trigger alone. **A
default change is not a deploy**, and reaching that bot means changing its config and restarting.

⚠ **The parity gate is structurally blind to the trigger change** — every re-entry lever lives on
the fill-clock path behind `run_dual` and the gate replays 15m bars through `.run()`. **Scale-in is
NOT blind**: it has Pine inputs and `cfg_scale_*` columns, so rule 22 applies to it and a fresh
export is owed before the ON path is called validated here.

### The deeper-entry stop was re-measured under these defaults and stays OFF

Aaron asked whether to keep it, so it was replayed both ways rather than answered from the 2026-08-16
table (which was measured with the re-entry off and scale-ins off — a different bot).

**PU Prime `XAUUSD.p` M15, 157,004 bars + the M5 feed, 2020-01-01 → 2026-08-23, $10,000, bar fills,
new defaults on both sides, only `exec_sl_deep` moving:**

| | trades | total R | worst run of losses | max account drawdown |
|---|---|---|---|---|
| **OFF (shipped)** | 244 | **+240.60R** | 6.69R | **54.9%** |
| ON | 235 | +193.75R | 7.24R | 55.8% |

🔴 **UNDER THESE DEFAULTS IT NO LONGER BUYS DRAWDOWN AT ALL, WHICH WAS ITS ONLY ARGUMENT.** The
2026-08-16 measurement had it trading 23R of return for 4.5 points of drawdown — expensive but a
real trade. Here it costs 47R **and** the drawdown is marginally worse. At matched drawdown it is
not close: re-levered to the same 54.9%, ON returns roughly a tenth of OFF.

⚠ **The compounded multiples behind that matched-drawdown line ignore the venue lot ceiling**, so
they are a levelling device for comparing the two runs and NOT a tradeable account. Quote the R and
the drawdown; the multiples only order the two.

⚠ **The live bot has it **ON**** (`exec_sl_deep: true`, Aaron's call 2026-08-15 on the old
measurement). **This default and that bot now disagree, deliberately and knowingly** — changing the
bot is a separate decision.

⚠ **2026 shows 81 trades against 20–36 in every earlier year in both runs.** It is shared by both
sides so it cannot have moved this verdict, and it is UNEXPLAINED. Do not quote a per-year figure
from these runs until somebody has looked at it.

### 🔴 The replay tool defaults to a symbol PU Prime does not quote

`backtest/tools/run_report.py --symbol` defaults to a bare `XAUUSD`. The lab terminal is PU Prime,
which quotes gold as `XAUUSD.p`, so both runs above failed on the first attempt with *no bars
returned*. ⚠ **The agent's `/health` says `ok` regardless** — it was probed for actual BARS, on both
names, before the symbol was blamed. **Pass `--symbol XAUUSD.p` on this box.**

---

## 🔴 THE SCALE-IN GUARANTEE WAS EXACT AT ONE ADD AND DOUBLE-SPENT AT TWO (fixed 2026-09-23)

**Found by a real trade, not by reading.** `sos_fade_1` (PU Prime demo 700152905), 2026-09-22.

The rule on the tin: an add is sized so that being stopped out costs at most the profit the stop
has already locked, so *an add can shrink a winner but it cannot manufacture a loser*. That is
exact arithmetic — **for one add**. `locked` was read off the BASE lot alone, so the second add
pledged the same locked profit a second time, and the lots already bought were invisible to the
calculation meant to be protecting them. They are the ones that matter, because a scale-in only
fills as price runs, so **an earlier add is always the lot furthest from the shared stop.**

### The trade

Short 0.37 lots @ 4369.93, stop 4391.88, all three lots closed at 4356.86.

| lot | filled | price | P&L |
|---|---|---|---|
| base | 21:45 UTC 09-21 | 4369.93 | **+$483** |
| add 1 | 05:45 | 4320.58 | **−$617** |
| add 2 | 08:00 | 4300.90 | **−$560** |

Account 16,455.47 → 15,765.48, **−$690 on a trade that was ~+$2,890 open** at the 4300 low.
Risk was 5% ≈ $823, so a **+0.59R winner closed −0.84R**.

- **Add 1** sized against locked = (4369.93 − 4357.859) × 37 = **$446**. Correct: at that stop the
  base's +$446 and the add's −$446 cancel.
- **Add 2** sized against locked = (4369.93 − 4356.783) × 37 = **$486**. At that same moment
  **add 1 was already $634 under that stop** and nothing looked at it. Worst case was therefore
  −$634, not flat, and that is what the trade booked.

⚠ **The fill was a full M15 bar late on both adds**, which made it worse but did not cause it.
The strategy sized add 1 at 4332.00 (the 05:30 bar's close) and the broker filled 4320.58 (the
05:45 bar's close); add 2 sized 4310.83, filled 4300.90. Each add's real risk-to-stop was
therefore **44% and 22% larger** than the arithmetic allowed. With lab-accurate fills the same
trade still books **≈ −$449** — the double-spend is the cause, the late fill is a multiplier.

🔴 **AND THE LEDGER RECORDED THE INTENDED RISK, NOT THE TAKEN RISK** — `risk_ccy 439.60` against
$633.70 actually at stake, because it is computed at the price the add was SIZED at. Rule 3,
in the one record that would have shown this on the day.

### The fix — two halves, and neither replaces the other

1. **`_locked_at_stop()`** sums the base off its entry **plus every open add lot marked to the
   same stop, signed**. A lot underwater subtracts and shrinks or refuses the next add; a lot in
   profit adds and may fund a larger one. Worst case at the stop is flat at ANY number of adds.
2. **`exec_scale_gate`** ("↳ When it may add again"), default **"Past the last add"**: the stop
   must have ratcheted past the PRICE the last add was bought at, not merely past the stop it was
   sized against. The old reading is kept as "Stop improved" so the two can be swept. On
   2026-09-22 the stop improved **1.17 points** and that was enough to authorise add 2.

⚠ **The base term is still `_base_qty` off the entry and that was deliberate.** Reading the
REMAINING base instead was tried and reverted within the hour: it makes a trade that banks half at
the first target buy a smaller add than an identical trade that banks nothing, which breaks the
invariant `test_a_tp_rung_does_not_slice_the_adds` holds — banking at a price and stopping at that
same price are the same thing. Only the adds were ever unaccounted for.

### Evidence

- 3 tests in `tests/test_execution.py`, **both mutations watched RED**: reverting `_locked_at_stop`
  to the base-only reading makes the two-add fixture book **−$8,197.89** where the fix books
  **exactly $0.00**; disabling the gate check kills the contrast test. 715 tests green.
- Pine mirrored in `strategies/tradingview/sos_fade_strategy.pine` — `_locked` now adds a loop over
  `strategy.opentrades` for every id containing `ADD`, and the new input carries the gate. Twin
  rebuilt; all four panel checks pass on both halves.
- 🔴 **THE PARITY GATE IS RED AND MUST STAY RED UNTIL AARON RE-EXPORTS.** Checked both ways on the
  committed golden (20,220 bars, warm-up 468): **PARITY OK before the change, and after it the
  first divergence is bar 5698, 2026-01-30 10:00, `px_closed_r` py 2.546 vs pine 2.593** — a
  scale-in trade whose add is now correctly smaller. The CSV was exported from the OLD Pine, so it
  encodes the old rule and cannot clear the new one. **Rule 22: this does not get committed until a
  fresh TradingView export off the updated Pine passes.** Only a human can produce it.

### MEASURED 2026-09-23 — the grid was owed and has been run (Run 43)

`exec_scale_mode` / `exec_scale_max_adds` / `exec_scale_cap_x` were all chosen by sweeps run
against the **broken** sizing (Run 22 and the 2026-08-18 32-cell grid), so every one of those
defaults was a number picked under a rule that no longer exists. ⚠ **The "4 adds turns winners into
losers, so ship 3" finding is this defect** — worst trade −2.24R and −2.73R against an unscaled
−2.06R is precisely an add manufacturing a loser, and it was capped rather than diagnosed.

**Re-run 2026-09-23** — `backtest/tools/scale_in_grid.py`, 37 cells, three arms over identical
bars and config, XAUUSD.p 15m 2018-09-14 → 2026-08-14, PU Prime ECN costs. Full table and the
reasoning: `sos_fade_optimization.md` → Run 43. What it settled:

- **The diagnosis above is confirmed by the grid.** Under the old rule the worst trade degrades
  with the budget — −2.37R at 4 × 1.0x and **−2.86R at 4 × 2.0x**. **Under the fixed rule it is
  −2.07R in every one of the 24 scaled cells**, at every add count and every cap. The add count was
  never the lever; the sizing was.
- **The fix is not a safety tax.** It raises return and lowers drawdown together at nearly every
  cell above one add — `4 × 2.0x` goes 230.54R at 19.04 drawdown → **236.74R at 15.51**. The
  double-spend was buying size the trade could not afford, on the lots furthest from the stop.
- **The budget does not move.** `Trail`, 3 adds, 0.5x cap still ships, and now on a measurement of
  the rule the bot runs. It beats not-scaling on return-per-drawdown on **both** books
  (22.51 vs 19.98; ex-2020 **18.08 vs 16.71**), which Run 21 could not say of any cell.
- **The stricter re-arm gate ships OFF.** 12.79R of return for 0.11R of drawdown at the shipped
  budget, and no change to the worst trade, because the sizing fix had already taken the tail.
  ⚠ It WINS at 4 adds × 0.5x — re-measure before raising the add count.

⚠ **Still owed: nothing in Runs 19–22 has been re-measured against the fixed rule.** Run 43
measured the BUDGET, not those runs' own questions (where an add happens, where its lots bank).
Treat every scale-in figure in Runs 19–22 as a pre-fix number.

### The detail drained out of `CLAUDE.md` on 2026-09-23, kept here

- **The live trade that found it**, `sos_fade_1` 2026-09-22: short 0.37 lots at 4369.93, two adds
  at 4320.58 and 4300.90, all three stopped at 4356.86. A **+0.59R winner booked at −0.84R**.
- **The re-arm gate's own numbers**, at the shipped 3 adds × 0.5x: it costs **12.79R** of return
  and buys **0.11R** of drawdown, and the worst trade is −2.07R either way. It WINS at 4 adds
  × 0.5x (ret/DD **21.21 vs 19.95**). On the live trade a **1.17-point** stop move authorised a
  second add over a first sitting **36 points** underwater.
- **The parity red was the DEFAULT, not the fix, and it is now green.** With the new re-arm
  setting defaulted ON the gate failed at **bar 5698** (closed-R 2.546 in Python against 2.593 in
  Pine) — the committed export came off a Pine with no such input, so the harness configured the
  Python stricter than the chart had run. Reverting the default to the old reading turns it green
  on all 19,668 compared bars. **A new input whose default differs from what every stored export
  ran is a parity break with no code defect behind it.**
- ✅ **PROVEN 2026-09-24 on a second golden.** The first golden's green was empty — the pre-fix
  sizing passed it too. The stress export (4 adds, 2.0x cap, "Stop improved") is green on the fix and
  RED on the pre-fix sizing at bar 6,120. Detail: `sos_fade_optimization.md` → Run 43.
- ⚠ **Run the gate at the warm-up `exports/golden/golden.json` records.** Without it, it reports
  a mismatch at bar 16 that is chart state a cold replay cannot have — not a defect, and it cost
  an hour here.
- **The two live-side defects, with their numbers**: the bot buys each add a full M15 bar after
  the lab does — sized at 4332.00 and filled at 4320.58, sized at 4310.83 and filled at 4300.90,
  inflating each add's true risk-to-stop by **44% and 22%** — and the ledger recorded
  **$439.60** of risk where the add actually took **$633.70** (rule 3). Neither is fixed.
