# Engine Extraction Roadmap

**Purpose:** Track which parts of the TradingView SMC indicator still need to become their own Python engines.
**Source indicator:** `indicators/mpc_assistant.pine` (full-featured SMC: structure, order blocks, sessions, kill zones, VWAP, liquidity, fibs, SVP).
**Last reviewed:** 2026-07-04

---

## The pattern

Every engine is built the same way:

1. Port the Pine block line-by-line into a stateful streaming state machine (one closed bar in at a time).
2. Emit **events**, never visuals (e.g. "level touched", "block mitigated").
3. Validate at 100% Pine parity — instrument the Pine with `px_*` plot columns, export a CSV, diff Python-vs-Pine bar-by-bar with a `compare` tool.
4. Ship it as the single canonical implementation. Bots consume it through a thin `algos/shared/` shim.

Downstream engines (like the fibs) read another engine's **public output** only — never its internals.

---

## Done

- **`regime/`** — market regime classifier (separate source, not the SMC indicator).
- **`market_structure/`** — external + internal structure (BOS/CHoCH, swings, HH/HL/LH/LL). 100% Pine parity.
- **`fibonacci/`** — Structure, Sniper, and Macro fibs. 100% Pine parity. Downstream of `market_structure/`.

---

## Still to build — in priority order

### 1. Order Blocks — do this next
- **What:** the zone where a bot enters after the trend breaks. Bull/bear OBs form off a structure break and die when tapped (mitigated).
- **Depends on:** `market_structure/` output — same setup as the fibs (same `StructureSnapshot` input, same shim, same parity workflow).
- **Emits:** OB-created, OB-mitigated (tapped).
- **Why first:** completes the SMC core a bot actually trades — structure says the trend broke, order blocks say *where* to enter, fibs give the levels. Lowest new-concept cost, highest value.
- **Source block:** `ORDER BLOCKS` (~line 27 in `mpc_assistant.pine`).

### 2. Liquidity levels
- **What:** the prices price runs toward and grabs — prev day/week/month highs and lows, previous-week-close, session highs and lows, H4 sweep (SSH/BSL), with mitigation tracking.
- **Depends on:** nothing (standalone), but the session H/L piece wants Sessions (#3) first.
- **Emits:** level-created, level-swept.
- **Note:** biggest block of code (~400+ lines).
- **Source block:** `LIQUIDITY LEVELS` (~line 123) plus `DAILY / WEEKLY / MONTHLY LEVELS`, `PWC`, `H4 LIQUIDITY SWEEP`, `SESSION H/L` (~lines 1335–1762).

### 3. Sessions + Kill Zones
- **What:** clock rules — Tokyo/London/New York session windows, kill zones, NY range box.
- **Depends on:** nothing. Small and simple.
- **Emits:** session-open/close, in-killzone flag, NY range high/low.
- **Note:** a prerequisite for the session-scoped parts of #2 (session H/L) and #4 (VWAP anchor). Worth doing before those.
- **Source block:** `TRADING SESSIONS` (~line 69), `KILL ZONES & NY RANGE` (~line 104), `SESSION H/L TRACKING` (~line 1594).

### 4. VWAP
- **What:** a session-anchored average line + cross events.
- **Depends on:** Sessions (#3) for the anchor; needs a **volume** column in the feed.
- **Emits:** VWAP value, VWAP cross.
- **Source block:** `VWAP` (~line 115).

### 5. Session Volume Profile (SVP)
- **What:** the Asia point-of-control / MV line.
- **Depends on:** Sessions (#3); volume-heavy.
- **Note:** niche — do last.
- **Source block:** `SESSION VOLUME PROFILE` (~line 220, 2554).

---

## Suggested batch order

`Order Blocks → Sessions → Liquidity → VWAP → SVP`

Sessions is low down the value list but unlocks the session-scoped pieces of Liquidity and VWAP, so build it before them if batching.

If building just one: **Order Blocks**.
