# CLAUDE.md — indicators/

**Purpose:** From-scratch Pine Script rebuild of the "Structure OS / SMC Engine" market-structure indicator (swing highs/lows, HH/HL/LH/LL, BOS, CHoCH), replicating a private TradingView indicator's behavior using a pullback-only detection method.
**Scope:** This covers Pine Script indicator development and the market-structure detection engine only. It does NOT cover trading strategy logic, risk management, or any live/backtest execution — this is a charting indicator, not a bot.
**Status:** Under construction — Stage 2b (break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3 (internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-07-12 — the whole structure chain was re-synced to the `choch_lock` removal in `mpc_assistant.pine` and re-validated at 100% Pine parity (see the "2026-07-12 structure re-sync" note below), and the A+ divergence retro-link landed in both A+-carrying files (see the note after it).

---

## Key paths & entry points

- `indicators/smc_engine_v2.pine` — the current pullback-only rewrite (v6 Pine Script), overlay indicator named "SMC Engine"
- `indicators/STRUCTURE_OS_BUILD.md` — cross-session handoff doc: architecture, design decisions, validation findings, build-stage status. Read this first when resuming work.
- `docs/market_structure_engine_spec.md` — the source-of-truth rules spec, written from the TradingView overview page. `STRUCTURE_OS_BUILD.md` treats this as priority-1 source of truth.
- `indicators/mpc_assistant.pine` — a full-featured SMC indicator (structure + order blocks + sessions + kill zones + VWAP + liquidity levels + fibonacci + SVP) that Aaron sourced separately. Its market-structure logic is pivot-seeded (`ta.pivothigh`/`ta.pivotlow`) rather than pullback-only, which breaks the rule below — but it matches the original "Structure OS" indicator at ~99.99% parity. Treat it as read-only reference; don't merge its approach into `smc_engine_v2.pine`.
- `indicators/structure_engine.pine` — a straight extraction of *only* the market-structure logic (external ASH/ASL/BOS/CHoCH/HH/HL/LH/LL + internal iSH/iSL/iBOS/iSOS) from `mpc_assistant.pine`, with every other feature (OBs, sessions, kill zones, VWAP, liquidity, fibo, SVP) stripped out. Same pivot-seeded approach as `mpc_assistant.pine`, so same exception to the no-pivot rule below. Chart-validated by Aaron; now ported to Python as the canonical `engines/market_structure/` subsystem (imported by `algos/` bots). **Re-synced 2026-07-11 so its drawing/visibility layer is byte-for-byte identical to `mpc_assistant.pine`'s structure block** — same "Market Structure" input group (Structure Label Size, Show External / Internal / Historic-Internal Structure, Show Swing Point Labels), same `f_swingCol`/`f_structSize` gating, same historic-internal wiping, so every label and line overlaps the MPC assistant exactly. The re-sync touched only drawing/visibility — the state machine is unchanged, so `engines/market_structure/` and `structure_engine_export.pine`'s plot columns are unaffected and need no re-validation.
- `indicators/fib_export.pine` — instrumented build for the FIB parity check: the external **and internal** structure engine (copied from `structure_engine_export.pine`, plus the mpc capture lines the fibs need — `i_confirmed_*` and the `iFib_*` seed anchors) + the Structure, Sniper, Macro AND Internal fib blocks lifted from `mpc_assistant.pine` (compute + state machines; drawing removed) + `px_fib_*`, `px_sniper_*`, `px_macro_*` and `px_ifib_*` `plot()` columns. Used to export a CSV that `engines/fibonacci/tools/compare_fib.py` diffs Python-vs-real-Pine. **Re-synced 2026-07-09** (TP3 reset-latch dropped + extend-changed guard added on Structure+Internal, Macro first-bar seed) and re-validated at 100% on a fresh `VANTAGE_XAUUSD, 5m` export (13,759 bars, `--warmup 3154`, exit 0 — Structure+Sniper+Macro+Internal). Do not let any part drift from its source (`structure_engine.pine` / `mpc_assistant.pine`).
- `indicators/structure_engine_export.pine` — instrumented copy of `structure_engine.pine` (logic byte-for-byte identical; adds `plot()` output columns, including the eight break-leg columns `px_bull_bos_high/low` + `px_bull_bos_h_ago/l_ago` and bear mirror added 2026-07-02). Used only to export a CSV from TradingView for the Python↔Pine parity check in `engines/market_structure/tools/compare_tradingview.py`. That check passes at 100% on the `OANDA_XAUUSD, 15m` export (21,729 bars, exit 0) and was re-confirmed on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars, `--warmup 227`, exit 0) after the break-leg columns were added. Do not trade off it or let its logic drift from `structure_engine.pine`.
- `indicators/ob_export.pine` — instrumented build for the ORDER-BLOCK parity check: `structure_engine_export.pine` (the byte-for-byte structure engine, external + internal) with the Order-Block blocks from `mpc_assistant.pine` bolted on (drawing removed) + `px_ob_*` `plot()` columns for the active OB arrays (6 slots × top/bottom per direction), counts, created/mitigated pulses and the internal-break origin. Used to export a CSV that `engines/order_blocks/tools/compare_ob.py` diffs Python-vs-real-Pine. **Because it embeds the structure engine, it must be re-synced whenever the structure block changes** — it was re-synced 2026-07-09 with the two 2026-07-08 detection changes (bear-BOS fallback scan + internal-reset firing on external BOS too), then passed at 100% on a `VANTAGE_XAUUSD, 5m` export (12,618 bars, `--warmup 1133`, exit 0). Do not let its structure logic drift from `structure_engine.pine` or its OB logic from `mpc_assistant.pine`.
- `indicators/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). Its `process()` state machine is byte-identical to `mpc_assistant.pine`'s — verified by diff, keep it that way. It is edited on TradingView and re-pasted, so **whenever the structure block changes here, tell Aaron's brother to re-paste this file from the repo**, or his next TradingView edit silently reverts the fix on his side.

---

## The 2026-07-12 structure re-sync (`choch_lock` removed from the break decision)

Aaron's brother found a missing higher high on XAUUSD 15m (17 Jun 2026, the ~4382 spike) and had it fixed on TradingView. The fix landed in `mpc_assistant.pine` and was propagated through the entire chain. **Both symptoms were one bug:** a bullish SOS set `choch_lock`, so the next bearish break was not treated as a CHoCH — it printed as a **BOS instead of an SOS**, and since the bear-break fallback classifies the old high with `old_is_hh = is_choch ? true : (…)`, losing the CHoCH also lost the forced `true`, so the **HH never printed**.

Four changes, now byte-identical across all six Pine copies of the engine (`mpc_assistant.pine`, `structure_engine.pine`, `structure_engine_export.pine`, `ob_export.pine`, `fib_export.pine`, `mpc_strategy.pine`):

1. bull break — `is_choch = st.dir == -1` (the `and not st.choch_lock` gate is gone)
2. bear break — `is_choch = st.dir == 1` (same)
3. bull-break SOS — the promoted pullback low prints **ASL**, not HL/LL
4. bear-break SOS — the promoted pullback high prints **ASH**, not HH/LH

…and in both break paths the confirmed-swing map (`last_conf_high` / `last_conf_low`) is now written only `if not is_choch`. On a fast reversal the promoted extreme is only the new ACTIVE swing; the NEXT break in that direction classifies it. That guard is what stops a lower high overwriting a genuine higher high.

`choch_lock` is now **inert** — still declared, set and released, but never read. Leave it alone. It is dead in `mpc_assistant.pine` too, and these files are kept byte-identical to it; deleting it would make the next Pine diff lie.

**Parity re-confirmed 2026-07-12 on ONE combined export.** `ob_export.pine` + `fib_export.pine` were put on a single `VANTAGE_XAUUSD, 5m` chart and exported as one CSV (9,270 bars). `structure_engine_export.pine` was **not needed on the chart** — `ob_export.pine` already carries all 23 of its `px_*` columns (strict superset), and `fib_export.pine` collides with neither, so all three compare tools (which resolve columns by name and ignore extras) ran off that single file: `compare_tradingview.py --warmup 365`, `compare_ob.py --warmup 548`, `compare_fib.py --warmup 368` — all exit 0. Warm-up differs per engine because each needs a different depth of history before it catches up with the state Pine already had at row 0.

---

## The 2026-07-12 A+ divergence retro-link

An RSI divergence pivot only confirms `divPivotLen` (5) bars **after** the extreme it marks. On a fast V-reversal the SOS fires inside that lag, so by the time the divergence arms Stage 1 the SOS is already in the past — and Stage 2 only looks forward. The setup stuck at 1/3 forever, and in `mpc_strategy.pine` that meant a divergence-armed setup could never place a trade.

Fix: remember the last bull/bear SOS bar, and when a divergence arms, adopt an SOS that already fired **at or after** the divergence's pivot bar, provided it is still inside the staleness window. The sequence really did run div → SOS; we just learned about the div late.

This lives ONLY in the two files that carry the A+ sequence — `mpc_assistant.pine` and `mpc_strategy.pine`. The structure engine, the three export builds and every Python engine have no A+ block, so nothing else needed it and no parity harness was affected (no re-run required).

**The two A+ blocks are NOT byte-identical, and that is expected.** Only `process()` is held byte-identical between the two files. `mpc_assistant.pine`'s A+ block has since moved on: its staleness window is measured in **minutes** (`aplusWindow * 60000`), arming is gated behind `aplusL_canArm`, and it has a session-gap detector. `mpc_strategy.pine` is an earlier generation — the window is in **bars** — so the retro-link there compares bar numbers, not timestamps. The strategy also needed a second change: its execution layer snapshots the arm source (`sosL_swp` / `sosL_div`) *on the SOS bar*, which never runs for a retro-linked SOS, so that snapshot is taken at retro-link time instead, measured against the SOS bar. Without it the table would show 2/3 but no trade would fire.

---

## Standing instructions

**Do**
- Confirm swings only by the 3-candle pullback method: a swing high needs 3 consecutive candles each closing below the previous candle's low; a swing low needs 3 consecutive candles each closing above the previous candle's high.
- Reset the pullback count to zero at a new extreme if price prints a new high (while seeking a high) or new low (while seeking a low) before the count reaches 3.
- Keep detection to a single fixed constant (3). No numeric tuning inputs for detection.
- Reuse the same shared pullback-tracker type (`type PB`) for both the swing (external) engine and the internal engine — instantiate it twice, don't fork the logic.
- Gate new swing structure on a body-close break of the current trading range (BOS/CHoCH), per the corrected Stage 2b architecture — do not let swings form freely inside the range.
- Update `STRUCTURE_OS_BUILD.md` status/changelog as each stage is validated on a real chart.

**Never do**
- Do not use `ta.pivothigh` / `ta.pivotlow` or any fixed-lookback-window pivot method to detect swings in `smc_engine_v2.pine` (the from-scratch rebuild). This does not apply to `mpc_assistant.pine` / `structure_engine.pine`, which are a separate, intentionally pivot-seeded track — see Key paths above.
- Do not add numeric/tunable inputs for the detection logic itself — it must stay a zero-parameter mechanical rule.
- Do not fork the shared `PB` pullback-tracker type into two separate code paths for swing vs. internal — if the two ever need to diverge, branch inside `PB` with a flag instead.
- Do not build or validate Stage 2/3 logic on top of an unvalidated swing map — the swing detector is the foundation; get it confirmed against the real chart first.
- Do not treat a wick-only touch of a range boundary as a break — only a candle body close beyond the boundary counts (BOS/CHoCH).

---

## Guides & references

- `indicators/STRUCTURE_OS_BUILD.md` — full build log: settings-panel parity, architecture (two engines/one shared type), design decisions, open questions, and per-stage validation status against the original TradingView indicator.
- `docs/market_structure_engine_spec.md` — plain-language spec of the detection rules (swing points, HH/HL/LH/LL, BOS/CHoCH, internal engine) derived from the TradingView indicator's public description.
