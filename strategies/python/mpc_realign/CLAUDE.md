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

## The pattern rule — the loosest one wins

`realign_pattern` takes `any` | `opposing` | `strict`. **Default is `any`, the loosest.**

`strict` (with-trend iBOS → counter iSOS → with-trend iSOS) is the sequence Aaron drew, and it is
**the WORST of the three**: it cuts the book 183 → 121 and moves BOTH directions the wrong way
(long −2.3% → −5.7%, short +6.1% → +4.4%). The extra specificity carries no information.

⚠ Read that as a fact about the FILTER, not about the drawing. The sequence he identified is real;
requiring the first leg of it just removes setups without improving what is left.

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

Full-history replay, 5m XAUUSD, 2020-01-02 → 2026-08-06, shipped defaults, costs charged:

**162 trades · +37.67R · maxDD 14.60R · win 44%**

Cross-checked against the TradingView Strategy Tester on the same instrument and window:

**143 trades · +41.35% · PF 1.617 · maxDD 17.79% · win 30.77%**

✅ **Total R agrees within noise**, which is the check worth having at this stage — two
implementations, two fill models, one answer about whether the setup makes money.

🔴 **Two differences are DIAGNOSED AND NOT MEASURED, and neither should be quoted as understood:**

1. **Drawdown is worse in Pine (17.79% vs 14.60R)** — probably correct, and probably Pine's. The
   TradingView tester fills a gapped stop at the next bar's OPEN; the bar-replay model fills at the
   stop PRICE. That errs optimistic in Python, which is the direction that matters.
2. **The win rate gap (30.77% vs 44%)** — probably scratch classification. This repo counts a trade
   closing a cent up as a win and TradingView does the same, so the gap is more likely *where the
   breakeven stop lands* than a counting difference — see `32b633f`, which found the 30-tick
   breakeven buffer is smaller than the measured spread, so a "breakeven" exit is quietly a small
   loss.

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
