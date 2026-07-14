# BUG: exit fills at a price matching no stop or target

**File:** `indicators/mpc_strategy.pine` (STRATEGY EXECUTION block only — engine above is fine)
**Status:** Open — deferred, lower priority
**Found:** 2026-07-14, on `VANTAGE_XAUUSD, 15m`
**Severity:** Medium — produces losses (and possibly wins) at prices the exit logic never set. Corrupts backtest P&L / R stats.

---

## Symptom

Some trades close all partial legs (TP1 / TP2 / RUN) at the **same price on the same bar**, one bar after entry, at a price that is **neither the stop nor any target** the code places.

Reference trade (CSV `MPC_A+_Strategy_FX_XAUUSD_2026-07-14.csv`, rows 1–3):

- SHORT, entry **3647.91** @ 2025-09-09 02:30
- All 3 legs (S-TP1 / S-TP2 / S-RUN) exit at **3649.89** @ 02:45 (next 15m bar)
- Result: **−0.17R**, −$173.45 total, 1-bar duration
- Label: Arm Div · SOS 0 bars ago · shallow (0.5) entry

Second instance of the same pattern in the same CSV: rows 4–6 (2025-09-30, entry 3838.36, all exit 3843.96).

## What was verified (all check out)

1. **Intended stop = 3659.31** (fib 1.0, `sSL = fiboP10 + execSlBuf`, buffer 0).
   Confirmed by money math, independent of the chart:
   - 3 legs = 30/30/40% → total qty ≈ 87.5
   - Risk 10% of $10k equity (first trade) → 1R = $1000
   - `slDist = 1000 / 87.5 = 11.4 pts` → `3647.91 + 11.4 = 3659.3` ≈ 3659.31 ✓
2. **Stop never reached.** Adverse excursion = 2.0 pts (max price ~3649.9), ~9.4 pts short of 3659.31.
3. **Targets below entry, never filled.** Shallow short → TP1 0.382 = 3645.21, TP2 0.0 = 3636.50. Favorable excursion = 0 on all legs (price never went in favor).
4. **Stop never staged.** Stage advances only on `low <= sTP1` (3645.21); favorable excursion = 0 means price never went below entry, so `sStage` stayed 0 and `sStop` stayed = `sSL` = 3659.31. Not breakeven, not trail.

So the only live orders were: stop 3659.31 (unhit) + limits 3645.21 / 3636.50 (unhit). Yet the position closed at 3649.89 (above entry, below SL, ≈ the trade's worst point).

## Hypotheses to test

- TradingView intrabar fill artifact from multiple `strategy.exit` calls (S-TP1/S-TP2/S-RUN) sharing one `stop = sStop` on the same `from_entry`, with `process_orders_on_close = false` / `calc_on_every_tick = false`.
- Order-of-operations on the entry/fill bar: `sEntry` / `sStage` set in the position-flip block vs. the exit block placing orders the same bar.
- `sSL` / `sTP*` frozen from a different leg than assumed (ruled out by the R-math above for `sSL`, but re-confirm `sTP1`/`sTP2`).

## Next step (repro)

Add a one-line debug label on the exit bar printing `sStage / sSL / sStop / sTP1 / sTP2` at the fill moment, then bar-replay to 2025-09-09 02:45 and read exactly which order fired at 3649.89. Fix once the firing order is identified.

## Impact

- W/L/Scratch and Total R / PF stats include these phantom exits.
- Every "all three legs same price, same bar, 1-bar duration" row in the trade log is suspect — grep the CSV for that shape to size the blast radius before trusting any backtest.
