# Strategy Workflow — from an idea to "run a sweep and tell me the best combination"

**Status:** 📘 **STANDING PROCESS — the Pine→Python PORTING pipeline.** ⚠ **This repo has TWO process docs and until 2026-08-12 neither mentioned the other.** This one is the porting pipeline (spec → Pine → export twin → CSV → port → parity gate). **`docs/BOT_DEVELOPMENT_METHOD.md` is the LIFECYCLE** of a bot from idea to live (the six S.Y.S.T.E.M. steps). Complementary, not rivals — but both open by calling themselves *the* process, so whichever you landed on first looked like the whole answer.

**Who this is for:** either of us, and Claude. It is the checklist Claude should run through
before answering "optimize this strategy" — if a stage below is missing, say which one and
stop, rather than producing numbers that cannot be trusted.

**Why it exists:** the numbers you want (sweeps, optimizations, "what's the best combination")
come from the **Python** side. TradingView is where a strategy is designed and where the truth
lives. Those two are different programs, and a number from the Python side means nothing until
they have been proven to make the same decisions on the same candles. That proof is a file, it
is per strategy, and skipping it is how a whole day of measurements gets thrown away — it has
happened here twice.

---

## The six stages

Each stage produces one artefact. The stage is not done until the artefact exists.

| # | Stage | Artefact | Gate — how you know it is done |
|---|---|---|---|
| 1 | **Spec** | `docs/MPC_<NAME>_SPEC.md` | Rules written with no discretion left in them |
| 2 | **Pine strategy** | `indicators/strategies/mpc_<name>_strategy.pine` | Compiles in TradingView, runs in the Strategy Tester |
| 3 | **Pine export twin** | `indicators/strategies/mpc_<name>_strategy_export.pine` | Compiles; plots the per-bar decision stream (`px_*`) and every input (`cfg_*`) |
| 4 | **A real CSV export** | a `.csv` on disk from "Export chart data" | Has thousands of bars and the `px_*` / `cfg_*` columns |
| 5 | **Python port** | `strategies/python/mpc_<name>/` | Imports; declares `LAB_STRATEGY`; ships `mpc_<name>.meta.json` |
| 6 | **Parity harness** | `strategies/python/mpc_<name>/tools/compare_<name>.py` | **Exit 0** on the stage-4 CSV |

**Only after stage 6 is green can you trust a sweep, an optimization, or a backtest number.**

---

## What each stage actually involves

**1. Spec.** One markdown file. Entry, exit, stop, sizing, and every filter with its default.
Claude can write this with you.

**2. Pine strategy.** Must be `strategy()`, not `indicator()`. An `indicator()` has no
Properties tab and no Strategy Tester, so it cannot be scored — and the filename does not tell
you which one it is. This is the file you trade off and read on a chart.

**3. Pine export twin.** Same logic, plus a block at the bottom that plots what the strategy
*decided* on every bar — armed / blocked / stage / stop / fill / R — and every input setting as
a number. Claude writes this from the parent. It exists only so a machine can read the Pine's
mind. ⚠ Pine caps a script at **64 `plot()` calls**; the export block is already near it.

**4. A real CSV export.** **This is the only step a human must do.** In TradingView, open the
export twin on the chart and timeframe you care about, then *⋮ → Export chart data → Bar data
and indicator values*. Save the CSV. Claude cannot do this — it has no TradingView session.
Without this file, nothing downstream can be validated.

**5. Python port.** A package under `strategies/python/`. This is the thing the lab, the
optimizer, the sweeps and (eventually) the live bot all run. Claude writes it.

**6. Parity harness.** `compare_<name>.py` reads the CSV from stage 4, replays *those same
candles* through the Python port configured from the CSV's own `cfg_*` columns, and diffs the
two decision streams bar by bar. Exit 0 means the Python bot makes identical decisions to the
Pine. Claude writes it, but it can only be *run* once stage 4 exists.

---

## What you can ask for, and when

| You want | You need | If it is missing |
|---|---|---|
| "Backtest this on the chart" | stage 2 | TradingView Strategy Tester only |
| "Run a sweep on these parameters" | stages 5 **and** 6 green | The answer is unverified — direction only, never decimals |
| "What's the best combination?" | stages 5 and 6 green | Same |
| "Show it in the Command Center lab" | stage 5 + `meta.json`, then click **Scan Strategies** | It will not appear in the list |
| "Put it live" | all six, plus `docs/LIVE_TRADING_PIPELINE.md` | Do not |

**Claude: if someone asks for a sweep on a strategy whose stage 6 is not green, say so first.**
A table of numbers reads as a finding no matter what caveat sits under it — `bos_sweep.py` was
falsified by a single Strategy Tester run the day it was written, and its docstring had already
said it was only a model.

---

## Where things live — the naming is load-bearing

```
docs/MPC_<NAME>_SPEC.md                                  the rules
docs/MPC_<NAME>_OPTIMIZATION.md                          one entry per sweep, so nothing is re-measured
indicators/strategies/mpc_<name>_strategy.pine                      what you trade
indicators/strategies/mpc_<name>_strategy_export.pine               its instrumented twin
strategies/python/mpc_<name>/config.py                   every input, as a dataclass
strategies/python/mpc_<name>/strategy.py                 declares LAB_STRATEGY
strategies/python/mpc_<name>/mpc_<name>.meta.json        labels + tooltips for the lab UI
strategies/python/mpc_<name>/tools/compare_<name>.py     the parity gate
```

⚠ **A parameter's label in the lab must be the Pine input's title, and its description must be
the Pine tooltip, verbatim.** One parameter, one name, two UIs. They are changed in the same
commit. A lab row saying something different from the chart is how a rule gets read backwards.

---

## Current status — 2026-09-01

| Strategy | 1 Spec | 2 Pine | 3 Export twin | 4 CSV | 5 Python | 6 Parity | Can you sweep it? |
|---|---|---|---|---|---|---|---|
| **A+ SOS Fade** (`mpc_sos_fade`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ green | **Yes** |
| **B-LEG** (`mpc_bleg`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ green | **Yes** |
| **BOS** (`mpc_bos`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ green (narrow) | **Yes — at the shipped defaults** |
| **D** (`mpc_d`) | ❌ deleted | ❌ | ❌ | ❌ | ❌ | ❌ | **No, and it is GONE (2026-08-15).** Its one measurement was indistinguishable from zero and it was never going further. Both `.pine` files and `docs/MPC_D_STRATEGY_SPEC.md` removed; recover from git history. Its VOCABULARY was the second reason — "shakeout" now means one thing in this repo, and it belongs to RSO. |
| **OB Fade** (`mpc_ob_fade`) | ❌ withdrawn | ❌ | ❌ | ❌ | ❌ | ❌ | **No, and do not restart it.** Its spec was DELETED once the measurement closed the question — the record of what was tried is `strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md` |
| **Extreme Leg** (`mpc_extreme_leg`) | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | **Not yet — stage 4 is waiting on a human.** Stages 1/2/3/5 landed 2026-09-01: the Pine, a GENERATED export twin, and `strategies/python/mpc_extreme_leg/`. Take the export off `mpc_extreme_leg_strategy_export.pine` on a XAUUSD **5-minute** chart and run `compare_extreme_leg.py`. ⚠ Its numbers so far come from a STUDY (`backtest/tools/pre_sos_leg.py`) whose arming rule is measurably looser than the file being traded — see that package's CLAUDE.md. |
| **H4 sweep** | study only | ✅ | ❌ | ❌ | ❌ | ❌ | No |

### BOS — green as of 2026-08-07, and what that is worth

All six stages landed on 2026-08-07. Aaron took the CSV and
`compare_bos.py` exits 0: **6,300 bars compared, no divergence**, at warmups 900 / 1000 / 2000
/ 3000 over 7,200 closed M15 bars (2026-04-21 → 2026-08-07).

```bash
python strategies/python/mpc_bos/tools/compare_bos.py '<export>.csv' --warmup 900
```

🔴 **Stage 4 is worth the five minutes precisely because the run went RED first.** Three
defects came out of it that 54 green unit tests could not see — a dead leg that cleared its
own numbers where the Pine keeps them, a harness column that had been comparing a **constant**
for its whole life, and the still-forming last bar killing the run with an error that blamed
the bar feed. Full write-up: `strategies/python/mpc_bos/CLAUDE.md` → *The three defects the
first real gate run found*.

⚠ **THE GREEN IS NARROW, and the tool says so.** `bos_use_fvg` is OFF at the shipped defaults,
so the entire gap ladder — rules 1–5, Method 3, the Sniper Zone — **never ran on either side**.
Block codes 1/3/4/5/6 never fired, the minimum-stop floor refused nothing, and 6 trades closed
in the window. Take a second export with `bosUseFvg` ON before trusting a gap-priced result.

⚠ **Green does not backdate.** The port CHANGED to get green, so everything measured before
2026-08-07 describes different code — all of `docs/MPC_BOS_OPTIMIZATION.md`, and everything
`backtest/tools/bos_sweep.py` prints. That tool was *actively falsified* by one Strategy Tester
run (20 trades / PF 2.97 from the tool against 24 / PF 1.04 from TradingView, same config) and
nothing has re-checked it since.

⚠ **Read the tool's COVERAGE table before believing its exit code.** It prints which branches
the run actually reached and warns when one was never taken, because a green run is only green
about the branches both sides entered.

⚠ **Below warmup 900 this export is RED on the BOS ordinal alone** — genuine structure-engine
cold start, not a mask: an SOS at bar 856 resets both counters, which is exactly where the
disagreement ends.

⚠ There **was** a `strategies/python/mpc_bos/` — deleted 2026-08-04 as a half-built port with no
parity harness (commit `1946f8b`). The rebuild deliberately dropped its eight research dials
that had no Pine input, because a field the export cannot carry is a field the gate can never
check. Recover them from `1946f8b^` if the Pine ever grows the inputs.

---

## The two rules that keep being learned the hard way

**A green parity run says the two implementations AGREE. It never says either is RIGHT.** The
phantom-exit bug was faithfully ported into both sides and the gate was green for its whole
life; a human looking at a price chart found it.

**A gate proves nothing about a branch neither side entered.** Before trusting a green run on a
new feature, check the feature actually fired — the minimum-stop guard passed parity on an
export where its block code was raised zero times in 21,897 bars.
