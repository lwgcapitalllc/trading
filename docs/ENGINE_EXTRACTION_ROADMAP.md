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
- **`order_blocks/`** — bull/bear OB zones off external + internal breaks, with mitigation + FIFO eviction. Sibling of `fibonacci/` (consumes `market_structure/` directly). Ported line-by-line, 12 unit tests, 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (harness: `indicators/ob_export.pine` + `order_blocks/tools/compare_ob.py`).

---

## Still to build — in priority order

### 1. Liquidity levels
- **What:** the prices price runs toward and grabs — prev day/week/month highs and lows, previous-week-close, session highs and lows, H4 sweep (SSH/BSL), with mitigation tracking.
- **Depends on:** nothing (standalone), but the session H/L piece wants Sessions (#2) first.
- **Emits:** level-created, level-swept.
- **Note:** biggest block of code (~400+ lines).
- **Source block:** `LIQUIDITY LEVELS` (~line 123) plus `DAILY / WEEKLY / MONTHLY LEVELS`, `PWC`, `H4 LIQUIDITY SWEEP`, `SESSION H/L` (~lines 1335–1762).

### 2. Sessions + Kill Zones
- **What:** clock rules — Tokyo/London/New York session windows, kill zones, NY range box.
- **Depends on:** nothing. Small and simple.
- **Emits:** session-open/close, in-killzone flag, NY range high/low.
- **Note:** a prerequisite for the session-scoped parts of #1 (session H/L) and #3 (VWAP anchor). Worth doing before those.
- **Source block:** `TRADING SESSIONS` (~line 69), `KILL ZONES & NY RANGE` (~line 104), `SESSION H/L TRACKING` (~line 1594).

### 3. VWAP
- **What:** a session-anchored average line + cross events.
- **Depends on:** Sessions (#2) for the anchor; needs a **volume** column in the feed.
- **Emits:** VWAP value, VWAP cross.
- **Source block:** `VWAP` (~line 115).

### 4. Session Volume Profile (SVP)
- **What:** the Asia point-of-control / MV line.
- **Depends on:** Sessions (#2); volume-heavy.
- **Note:** niche — do last.
- **Source block:** `SESSION VOLUME PROFILE` (~line 220, 2554).

---

## Suggested batch order

`Sessions → Liquidity → VWAP → SVP`

Sessions is low down the value list but unlocks the session-scoped pieces of Liquidity and VWAP, so build it before them if batching.

If building just one: **Sessions** (it unblocks the most downstream).
