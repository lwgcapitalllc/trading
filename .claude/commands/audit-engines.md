---
description: Audit the latest mpc_assistant.pine against all extracted Python engines — detect logic drift and missing engines
---

Audit `indicators/engines/mpc_assistant.pine` against the extracted Python engines. This is a REPORT-ONLY audit — do not change any engine code.

Context: `indicators/engines/mpc_assistant.pine` is the source TradingView indicator. It gets edited on TradingView and re-pasted into this repo, so the working-tree copy may be newer than the last commit. Every functional block in it has been ported to a canonical Python engine under `engines/` — the mapping lives in `docs/ENGINE_EXTRACTION_ROADMAP.md`.

## MOST CRUCIAL — the market-structure sync chain (never let it drift)

The market-structure block is the one engine with a dedicated single-purpose Pine mirror that bots run on. Its detection logic must stay in lockstep across the whole chain, top to bottom:

1. `indicators/engines/mpc_assistant.pine` — the structure block (external `st.process` swing/BOS/CHoCH + the internal iSH/iSL/iBOS/iSOS block). **Source of truth.**
2. `indicators/engines/structure_engine.pine` — the structure-ONLY extraction. Its detection logic must stay **byte-for-byte identical** to mpc's structure block.
3. `indicators/engines/structure_engine_export.pine` — instrumented copy of `structure_engine.pine` (adds `px_*` plot columns only). Must mirror it byte-for-byte in logic.
4. `engines/market_structure/engine.py` — the canonical Python port, validated at 100% parity against `structure_engine_export.pine` by `engines/market_structure/tools/compare_tradingview.py`.
5. `algos/shared/structure_engine.py` — a **thin shim** over `engines/market_structure/` with NO detection logic of its own; it stays in sync automatically.

**The rule:** every time the audit's drift check finds a change to mpc's structure block, you MUST flag `indicators/engines/structure_engine.pine`, `indicators/engines/structure_engine_export.pine`, and `engines/market_structure/engine.py` as STALE together — they are one unit. A real fix re-syncs 2 → 3 → 4 in the same pass and re-runs `compare_tradingview.py` on a fresh TradingView export (exit 0) before committing; then check 5 only to expose any new public field a bot reads (the shim needs no logic edit).

**Distinguish carefully (this is the whole judgment call):** hiding structure behind a `showExternal` / `showInternal` toggle, a label size / vertical-offset / colour tweak, or a NEW output flag that only feeds a table (e.g. `int_bull_bos`/`int_bull_sos` alongside the already-existing `int_bull_break`) is **VISUAL** — it does NOT trigger the chain. Only a change to **WHEN a swing confirms or a break/CHoCH fires** — the 3-candle pullback count, the break condition, the seed / lookback scan, `choch_lock`, inside-bar handling — triggers it. When in doubt, treat it as logic and flag the chain.

Steps:

1. Run `git diff indicators/engines/mpc_assistant.pine` (and `git log -1` on the file) to see exactly what changed since the last audited version. If the working tree is clean, diff against the commit of the last audit instead.

2. Read `docs/ENGINE_EXTRACTION_ROADMAP.md` to load the block → engine mapping (structure, order blocks, sessions, kill zones, NY opening range, liquidity levels, VWAP, the three fibs, SVP/MV).

3. Coverage check: scan the FULL latest Pine and enumerate every functional block. For each, name the engine that covers it — or flag it as a NEW, un-extracted feature that belongs on the roadmap.

4. Drift check: for each block the diff touched, compare the changed Pine lines against the corresponding engine's Python. Classify every change as either:
   - **visual-only** — colors, labels, tables, boxes, plots, watermark, input renames. No engine impact; engines emit events, not visuals.
   - **logic** — conditions, thresholds, state machines, session times, array handling. The engine is now STALE.
   - For the **market-structure block specifically**, apply the "MOST CRUCIAL" sync-chain rule above: a logic change there makes `structure_engine.pine`, `structure_engine_export.pine`, AND `engines/market_structure/engine.py` stale as one unit (and check the `algos/shared/structure_engine.py` shim for a new field). A visual/toggle/table-flag change there does not.

5. Harness check: if a logic change touched a block, the matching export harness (`indicators/engines/*_export.pine`) is stale too — flag it. For a structure logic change, that harness is `indicators/engines/structure_engine_export.pine` (via `structure_engine.pine`).

6. Report a summary: one line per engine with status (IN PARITY / STALE / not affected), plus any new blocks needing extraction, plus stale harnesses. Plain English, concise.

7. If anything is stale or new, update `docs/ENGINE_EXTRACTION_ROADMAP.md` to reflect it, but do NOT fix engine code in this audit. Remind me that any engine fix must re-run its `compare_*.py` Pine-parity check on a fresh TradingView export before committing.
