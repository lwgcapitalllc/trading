# Market Structure Rule Engine — Spec

**Status:** 🔨 **SPEC for work IN PROGRESS — and on the track people confuse.** It targets the from-scratch `indicators/engines/smc_engine_v2.pine` rebuild (progress in `indicators/docs/STRUCTURE_OS_BUILD.md`), **NOT** the shipped `engines/market_structure/` engine, which was ported from `mpc_assistant.pine` and is complete and parity-green. Two different structure efforts; do not read this spec as describing the live one.

Replication target: **Structure OS** (private TradingView indicator). This doc defines only the
structure-detection logic — swing highs/lows, HH/HL/LH/LL, BOS, CHoCH — using the indicator's own
confirmation method. Everything else (sessions, order blocks, FVG, liquidity, MTF dashboard) is out of scope.

---

## Core principle

Structure is mechanical, not subjective. Swing points are NOT found with a lookback window
(`ta.pivothigh` / `ta.pivotlow` over N bars). They are confirmed in real time by a **pullback of three
consecutive opposing candles**. No valid three-candle pullback = no confirmed swing point.

This is the one rule that defines the whole engine. A fixed-lookback pivot and a three-candle pullback
produce *different* swing maps on the same data → different BOS/CHoCH events → different signals. Get this
rule exact or nothing downstream matches.

---

## 1. Swing point detection (the three-candle pullback rule)

Two independent engines run on the **same timeframe** with the **same confirmation logic**: SWING (external)
and INTERNAL (inside the swing range). Swing vs internal is a scope distinction, not a timeframe distinction.

**Tracking.** As price moves, the engine tracks a candidate extreme:
- Candidate **swing high** = the highest high reached so far in the up-move.
- Candidate **swing low** = the lowest low reached so far in the down-move.

**Confirmation — three consecutive opposing candles:**
- To confirm a **swing high**: three consecutive **bearish** candles, each closing **below the previous
  candle's low**.
- To confirm a **swing low**: three consecutive **bullish** candles, each closing **above the previous
  candle's high**.

**Reset rule.** If price prints a **new extreme** (new high while confirming a high / new low while
confirming a low) before the three-candle count completes, the candidate resets and the count restarts from
zero at the new extreme.

**Result.** Once confirmed, the swing point is the extreme that was being tracked (the highest high before a
confirmed bearish pullback → swing high; the lowest low before a confirmed bullish pullback → swing low).

**Display.** A candidate level is drawn **dotted** while the three-candle count is in progress, and becomes
**solid** once confirmed.

> ⚠️ Discrepancy to resolve before coding. The indicator's overview says each candle must close "beyond the
> previous one's **body**," while its swing-engine section says "beyond the previous one's **low** (bearish)
> / **high** (bullish)." These give slightly different confirmations. The low/high wording is the more
> specific and is treated as primary here — but pin this down against live behaviour before backtesting,
> because it changes which swings confirm.

## 2. Swing labels: HH / HL / LH / LL

Each newly confirmed swing point is labelled by comparing it to the prior swing point of the same type:
- **HH** (Higher High) — confirmed swing high above the previous swing high.
- **LH** (Lower High) — confirmed swing high below the previous swing high.
- **HL** (Higher Low) — confirmed swing low above the previous swing low.
- **LL** (Lower Low) — confirmed swing low below the previous swing low.

Uptrend reads as a sequence of HH + HL. Downtrend reads as LH + LL. The transition between these sequences is
what BOS and CHoCH formalise.

## 3. The trading range, BOS and CHoCH

Once two swing points are confirmed (a swing high and a swing low), they define an active **trading range**.
A **candle body close beyond a range boundary** triggers a break event. A wick through the level does
**not** qualify — close only.

- **BOS (Break of Structure) = continuation.** Body close beyond the swing level **in the direction of the
  current trend** (close above swing high in an uptrend / below swing low in a downtrend).
- **CHoCH (Change of Character) = reversal.** Body close beyond the swing level **against** the prevailing
  trend (close below swing low in an uptrend / above swing high in a downtrend). Flips the trend state.

After a break, a new range is established from the new confirmed swing points and the cycle repeats.

## 4. Internal structure engine

Internal structure uses the **identical three-candle confirmation logic**, but scoped **only within the
current confirmed swing high and swing low**.

- Activates only **after** a new swing point is established.
- Cannot detect or plot structure **outside** the active swing boundaries.
- **Resets completely** when a swing-level BOS or CHoCH occurs (a new swing range begins).
- Tracks pullbacks *inside* the range independently of swing-level reversals.

Internal events are labelled **iBOS** and **iCHoCH** (and internal swing labels iHH / iHL / iLH / iLL), drawn
**dashed** to distinguish them from swing structure.

**Use.** A deep pullback into the range followed by an **internal CHoCH** in the swing's direction signals the
internal realigning with the swing — the trigger to target the swing extreme.

---

## Build checklist

1. Implement the three-candle pullback tracker with the reset-on-new-extreme rule. This is the core; verify
   it against the live indicator before anything else.
2. Resolve the body-vs-low/high close discrepancy (§1) against live behaviour.
3. Add HH/HL/LH/LL labelling off confirmed swings.
4. Add the range + body-close BOS/CHoCH logic.
5. Add the internal engine as the same tracker scoped to the live range, resetting on swing breaks.
6. Render candidates dotted, confirmed swings solid, internal structure dashed.
