---
description: Audit the latest mpc_assistant.pine against all extracted Python engines — detect logic drift and missing engines
---

Audit `indicators/mpc_assistant.pine` against the extracted Python engines. This is a REPORT-ONLY audit — do not change any engine code.

Context: `indicators/mpc_assistant.pine` is the source TradingView indicator. It gets edited on TradingView and re-pasted into this repo, so the working-tree copy may be newer than the last commit. Every functional block in it has been ported to a canonical Python engine under `engines/` — the mapping lives in `docs/ENGINE_EXTRACTION_ROADMAP.md`.

Steps:

1. Run `git diff indicators/mpc_assistant.pine` (and `git log -1` on the file) to see exactly what changed since the last audited version. If the working tree is clean, diff against the commit of the last audit instead.

2. Read `docs/ENGINE_EXTRACTION_ROADMAP.md` to load the block → engine mapping (structure, order blocks, sessions, kill zones, NY opening range, liquidity levels, VWAP, the three fibs, SVP/MV).

3. Coverage check: scan the FULL latest Pine and enumerate every functional block. For each, name the engine that covers it — or flag it as a NEW, un-extracted feature that belongs on the roadmap.

4. Drift check: for each block the diff touched, compare the changed Pine lines against the corresponding engine's Python. Classify every change as either:
   - **visual-only** — colors, labels, tables, boxes, plots, watermark, input renames. No engine impact; engines emit events, not visuals.
   - **logic** — conditions, thresholds, state machines, session times, array handling. The engine is now STALE.

5. Harness check: if a logic change touched a block, the matching export harness (`indicators/*_export.pine`) is stale too — flag it.

6. Report a summary: one line per engine with status (IN PARITY / STALE / not affected), plus any new blocks needing extraction, plus stale harnesses. Plain English, concise.

7. If anything is stale or new, update `docs/ENGINE_EXTRACTION_ROADMAP.md` to reflect it, but do NOT fix engine code in this audit. Remind me that any engine fix must re-run its `compare_*.py` Pine-parity check on a fresh TradingView export before committing.
