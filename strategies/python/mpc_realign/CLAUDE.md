# CLAUDE.md — strategies/python/mpc_realign/ (the MPC REALIGN bot)

**Purpose:** The internal-realignment setup as a standalone Python strategy. A bullish external
trend on the 15m (SOS → BOS → BOS) is broken by a **bearish shift of structure that is a FALSE
BREAK** — a structural liquidity grab. On the 5m the internal structure then turns bearish and back
bullish to **realign** with the original external direction, and the trade is taken on that
realignment, **before** the external bullish SOS that later confirms it. Shorts are the exact mirror.
**Scope:** This bot only — its 15m aggregator, tracker, order layer, config, tests. It does NOT own
the engines (`engines/`), the replay runner (`backtest/`), or the A+ machinery it reuses
(`strategies/python/mpc_sos_fade/`).
**Status:** Built + unit-tested (15 tests green) + **cross-checked against the TradingView Strategy
Tester**. 🔴 **NOT PARITY-VALIDATED — there is no export twin, no real CSV and no
`tools/compare_realign.py`, so stages 3, 4 and 6 of `docs/STRATEGY_WORKFLOW.md` are all outstanding.**
Every number below is a LAB finding. Read `docs/MPC_REALIGN_SPEC.md` for the setup and the full
measurement record.
**Last reviewed:** 2026-08-13 — first commit.

---

## What it trades

Five steps, and the false break is the whole idea:

1. **External trend** — a bullish external read on the 15m (a `bull_bos` or `bull_sos`).
2. **The false break** — a `bear_sos` against that trend. This is the deviation: price grabs the
   liquidity under the last confirmed low and the external structure flips bearish.
3. **The arm** — the pre-deviation external high (`broken_high_price`) is latched as the TARGET, and
   the setup stays armed for `realign_window_hrs` (24.0, chosen not measured).
4. **The realignment** — on the 5m, a counter-direction break followed by a with-trend SOS. That
   second break is the trigger.
5. **The entry** — MARKET, immediately, on the trigger bar's close. Stop behind the last counter
   internal shift plus `realign_sl_buf_tk`; target the latched external high.

Shorts mirror it exactly: bearish external trend, a `bull_sos` false break, a bearish realignment.

⚠ **The entry is a MARKET order, which makes this fork structurally different from every other bot
here.** A+, B-LEG and BOS all rest a limit at a fib-priced edge; this one takes the close of the bar
that triggers it. So `_place_entries` is overridden wholesale, no fib ladder is frozen
(`TradeFib` is `None` on every trade, and the chart's Fibs row is correctly absent), and the
entry-side A+ config fields are inert rather than pinned.

---

## 🔴 "Internal" means the lower frame's OWN swing structure — and the other reading inverts the result

This is the single decision the whole strategy rests on, and both readings are defensible in English.

`engines/market_structure/` publishes two streams per frame: `ExternalEvents` (the swing structure a
chart draws) and `InternalEvents` (the sub-structure *within* it, one level further down).

**Aaron's "internal structure on the 5m" is the 5m's EXTERNAL stream** — the swing structure of the
5m chart, which is internal *relative to the 15m*. It is NOT the engine's `InternalEvents`, which is
one level below what he is pointing at.

That distinction is not cosmetic. **`InternalEvents` tracking RESETS on any external BOS/SOS of its
own frame**, and the false break is precisely such an event — so on **81% of candidates** the
internal stream was blank at the moment the setup armed. Reading it there does not measure a weaker
version of the setup; it measures a different, mostly-empty one.

`realign_long_source` / `realign_short_source` still expose both (`"swing"` / `"internal"`) because
the question was worth keeping open. **Both default to `"swing"`.**

---

## 🔴 The trigger scan got the SHORT side's SIGN wrong, and that is the transferable half

`backtest/tools/internal_realign_scan.py` counts setups and scores each one against a matched random
control. On shorts it reported **`"internal"` at +9.6% over control (+2.1σ)** — its single strongest
result, and the reason `realign_short_source` was originally defaulted there.

**A real replay through the exit ladder says the opposite, and not by a little:**

| shorts, 2020-01-02 → 2026-08-06 | trades | total R | avg R | maxDD |
|---|---|---|---|---|
| `realign_short_source = "swing"` | 87 | **+20.22R** | +0.232R | 6.39R |
| `realign_short_source = "internal"` | 60 | **−13.26R** | −0.221R | 14.61R |

The scan is not broken. It scores every setup **independently, at a FIXED target, with no exit
ladder, no staged stop and no position slot** — and that short edge lived entirely in the tail
(+0.1σ at 1R, +2.1σ at 4R). The real ladder banks at the structural target and stages the stop to
breakeven long before 4R, so **the edge the scan measured is one this strategy never collects.**

⚠ **Standing rule this leaves behind: take COUNTS from the scan, take the direction of anything
exit-sensitive from a REPLAY.** A trigger prior is not a strategy result, and here the two disagree
in sign, which is the one disagreement no amount of care about magnitude protects you from.

---

## The cascade — 5m carries it, 3m is flat, 1m is negative

The internal frame was swept rather than assumed:

- **5m** — the edge. 94 setups over 5.6 years on the single-engine count.
- **3m** — break-even. More setups, none of them better.
- **1m** — negative, **and its stops sit inside gold's spread floor**, so a positive result there
  would have been unbankable anyway.

⚠ A single-engine M15 run gives only **9 setups in 5.6 years** — the M15 engine emits 3 iSL and zero
iBOS/iSOS across Aaron's own window. The two-frame build is not a refinement; without it there is no
strategy to measure.

## 🔴 The pattern rule — the ranking INVERTS with costs, and this file had it wrong

`realign_pattern` takes `any` | `opposing` | `strict`. **Default is `any`, the loosest.**

**This section previously said `strict` — the sequence Aaron actually drew — was "the WORST of the
three" and that "the extra specificity carries no information". Both sentences were false, and they
came from the TRIGGER SCAN**, which the section two above says must never decide an exit-sensitive
question. The correction is the same lesson arriving inside the file that states it.

Measured by REPLAY, 467,352 M5 bars 2020-01-02 → 2026-08-06:

| FREE | trades | total R | avg R | win | PF | maxDD |
|---|---|---|---|---|---|---|
| `any` | 162 | +45.14R | +0.279 | 44.4% | 1.658 | 12.15R |
| `opposing` | 43 | +11.36R | +0.264 | 48.8% | 1.832 | 4.58R |
| `strict` | 42 | **+12.36R** | **+0.294** | **50.0%** | **1.977** | **4.15R** |

| CHARGED (`puprime_standard`) | trades | total R | avg R | win | PF | maxDD |
|---|---|---|---|---|---|---|
| `any` | 162 | **+35.81R** | **+0.221** | 33.3% | 1.496 | 15.52R |
| `opposing` | 43 | +6.22R | +0.145 | 30.2% | 1.425 | 5.51R |
| `strict` | 42 | +7.33R | +0.175 | 31.0% | **1.540** | **4.41R** |

**Free, `strict` is the BEST of the three on average R, profit factor and drawdown simultaneously.**
Charged, it is not — costs take **40% of its average R** (+0.294 → +0.175) against `any`'s **21%**
(+0.279 → +0.221), and the order flips. A conclusion drawn on a free book does not survive a charged
one here, which is the practical reason this repo charges costs before ranking anything.

⚠ **The mechanism is NOT measured.** The obvious candidate is that the strict sequence's stops are
tighter, so a fixed spread costs more R. It is plausible, it is one replay away (median stop distance
per pattern), and it is deliberately left as a hypothesis rather than written up as a finding.

**`any` still ships**, on the two figures that survive charging: 5x the total R and more R per unit
of drawdown (2.31 vs 1.66). But `strict` is a real rule with the best per-trade quality in the book,
and it is the one worth revisiting if the cost model or the entry ever gets cheaper — which is
exactly the conclusion the old wording would have prevented anyone from reaching.

---

## Single-frame by construction (`htf.py`)

The setup reads two frames and the strategy is **single-frame from the runner's point of view**: it
runs on the 5m stream and builds its own 15m bars in `HtfStructure`.

That is not a stylistic choice. **`backtest.optimizer.run_sweep` REFUSES dual-frame strategies** —
it replays one frame — so a `run_dual` build is locked out of the optimizer, every sweep and the
stress test's sensitivity pass. `run_dual` therefore raises here, by test.

Two correctness properties, both tested, both silent if broken:

- 🔴 **A 15m bar is published only once its last 5m bar has CLOSED.** Feeding a forming HTF bar to
  the engine is lookahead of the flattering kind — the external break would be known one or two 5m
  bars before it could have been, and every entry after it priced on information the trade did not
  have. The aggregator emits on the FIRST bar of the NEXT bucket.
- ⚠ **Buckets align to the wall clock** (:00/:15/:30/:45), never counted three-at-a-time. A counted
  aggregation drifts after any gap — a weekend, a holiday, one missing bar — and then silently
  builds 15m bars straddling two real ones.

---

## Inherited defaults — what had to be refused

`RealignConfig` is a `SosFadeConfig` superset for the same reason `BLegConfig` is: one exit ladder,
one sizing path, one cost model. **The inherited defaults are the risk, not the new fields** — the
`BosConfig` incident (2026-08-07), where two A+ defaults added in the preceding five days silently
broke a new fork.

- **`exec_secondary` PINNED False.** The parent defaults it **True** since 2026-08-07. The 1m
  re-entry needs a second bar stream through `run_dual`, which this fork raises on — so inherited,
  a replay would either refuse outright or, on the paths that do not check, return a primary-only
  book while reporting itself as having re-entries. Turning it on is REFUSED at construction rather
  than ignored.
- **`show_internal` switched back ON.** The parent pins it **False**. Inheriting that blanks the
  internal stream, and with `realign_*_source = "internal"` the bot would simply never trigger on
  that side — **a wrong RESULT with no error anywhere.** Tested.
- **The entry-side A+ fields are left alone deliberately** (`exec_fib_nearest`, `exec_deep_fib`,
  `exec_fvg_pre_zone`, `exec_fib_overlap`, `exec_fib_deep_edge`, `exec_sl_deep`). This fork places
  no fib-priced order, so nothing reads them. Pinning them would imply they mean something here.

## The exit ladder is the parent's, unchanged

Stop staging, the runner trail, TP rungs and the time stop all come from `mpc_sos_fade` and move
with it. That is the point of inheriting — but it also means **a change to the A+ ladder moves this
bot's numbers**, and the numbers below were taken before `32b633f` (the breakeven-buffer-vs-spread
finding). Re-measure before quoting them against a charged book.

---

## Measured — and what is still open

Full-history replay, 5m XAUUSD, 2020-01-02 → 2026-08-06, shipped defaults, warmup 1000, **the 5m
frame resampled from M1** (see *How to re-run this* below — reading the M5 cache is a trap):

| | trades | total R | avg R | win | PF | maxDD |
|---|---|---|---|---|---|---|
| free | 162 (77L/85S) | +45.14R | +0.279 | 44.4% | 1.658 | 12.15R |
| charged (`puprime_standard`) | 162 | +35.81R | +0.221 | 33.3% | 1.496 | 15.52R |

Cross-checked against the TradingView Strategy Tester on the same instrument and window:

**143 trades · +41.35% (≈35R) · PF 1.617 · maxDD 17.79% (≈19.5R) · win 30.77%**

✅ **Total R agrees within noise** — two implementations, two fill models, one answer about whether
the setup makes money.

⚠ **AN EARLIER REVISION OF THIS SECTION CLAIMED +37.67R / maxDD 14.60R CHARGED AND IT DOES NOT
REPRODUCE.** Same window, same profile, today: +35.81R / 15.52R. **The FREE figure reproduces to the
cent**, so whatever differs is on the charged path alone. `32b633f` was checked and is not the cause
— it touched only tools and docs, no execution code. The candidates are a different warmup or a
different bar set in the original run, and **neither is measured, because the original run's command
was not recorded.** That is the whole argument for the *How to re-run this* section below.

✅ **ONE OF THE TWO PINE/PYTHON DIFFERENCES IS NOW LARGELY CLOSED, AND THE CAUSE WAS THE COMPARISON
RATHER THAN EITHER IMPLEMENTATION.** This section used to report the win-rate gap as "30.77% vs 44%"
and blame scratch classification. **44% is the FREE book.** The charged book — the one the R figure
is quoted from — wins **33.3%**, against the tester's 30.77%. The comparison was reading its R off
one book and its win rate off the other. **Costs move this strategy's win rate 11 points** (44.4% →
33.3%), because it enters at MARKET and pays the spread both ways rather than resting a limit like
every other bot here. ⚠ ~2.5 points remain, scratch classification is still the candidate (11 of 162
counted separately at |r| ≤ 0.02 against a tester that asks only whether P&L > 0), and it is small
and NOT measured.

🔴 **The drawdown difference is still open and undiagnosed by measurement: 17.79% (≈19.5R) in Pine
against 15.52R here.** The candidate is that TradingView fills a gapped stop at the next bar's OPEN
while the bar-replay model fills at the stop PRICE, which would make Python optimistic — the
direction that matters. Same total R with a deeper drawdown is that signature, but a signature is
not a measurement, and **the parity gate is what settles it.**

## How to re-run this

```
.venv/bin/python -m pytest strategies/python/mpc_realign/tests/ -q     # 15 tests
```

For the replay: build the 5m frame by resampling `backtest/cache/XAUUSD__M1.csv`, never by loading
the M5 cache. 🔴 **`backtest/cache/XAUUSD__M5.csv` holds 26,887 bars where a complete 2020→2026
history is ~467,000.** A streaming structure engine fed across holes that size builds structure over
candles that never traded, and returns a frame and a number that look perfectly clean. Every figure
in this file is from the M1 resample; a run off the cache is not comparable to any of them.

**Neither is a reason to trust one side over the other yet. They are the two things the parity gate
exists to settle, and the parity gate does not exist.**

---

## Rules

- **Do not quote a number from this bot without saying it is unvalidated.** No export twin, no real
  CSV, no `compare_realign.py` — the Pine and the Python have never been diffed bar for bar, only
  compared on totals. `docs/STRATEGY_WORKFLOW.md` stages 3, 4 and 6 are the outstanding work, and
  stage 4 is the one only a human can do.
- **Take counts from `internal_realign_scan.py`; take the direction of anything exit-sensitive from
  a replay.** The scan had the short side's sign wrong. See above.
- **Never publish a forming HTF bar** from `htf.py`. It is lookahead, it improves every result, and
  nothing errors.
- **Diff this config against `SosFadeConfig` field by field before touching either.** Inherited
  defaults arrive uninvited and this fork has already had to refuse two of them.
- **A change to the A+ exit ladder changes this bot.** The ladder is shared, not copied.

## Key paths

| Path | What |
|---|---|
| `config.py` | `RealignConfig` — the levers, and every pin with its reason |
| `htf.py` | `HtfStructure` — the 15m aggregator, and the no-lookahead argument |
| `tracker.py` | `RealignTracker` — arming on the false break, walking the realignment |
| `execution.py` | `RealignExecution` — the market entry, sizing, the stop |
| `strategy.py` | `MpcRealignStrategy` — wiring, `engine_config()`, `run_dual` refusal |
| `tests/test_realign.py` | 15 tests, weighted toward the silent failures |
| `indicators/mpc_realign_strategy.pine` | the TradingView side |
| `docs/MPC_REALIGN_SPEC.md` | the stage-1 spec and the full measurement record |
| `backtest/tools/internal_realign_scan.py` | the counting/geometry scan |
