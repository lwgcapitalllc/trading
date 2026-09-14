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
