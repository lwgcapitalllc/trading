# Engine Extraction Roadmap

**Purpose:** Track which parts of the TradingView SMC indicator still need to become their own Python engines.
**Source indicator:** `indicators/engines/mpc_assistant.pine` (full-featured SMC: structure, order blocks, sessions, kill zones, VWAP, liquidity, fibs, SVP).
**Status:** ✅ **COMPLETE — the extraction roadmap has nothing left on it.** Kept, and heavily referenced (9 files, including `.claude/commands/audit-engines.md` and 7 engine CLAUDE.md files), because it is the record of HOW each engine was extracted and what each parity gate was run on. Finished work, still load-bearing.

**Progress:** ALL 8 SMC-port engines done (regime, market_structure, fibonacci, order_blocks, sessions, liquidity, vwap, svp) · **5 off-roadmap engines done — news, fair_value_gaps, rsi_divergence, equal_highs_lows, candlesticks — for 13 in total** (⚠ corrected 2026-08-12: this line said "1 off-roadmap engine" and had not been updated as four more landed; count with `ls engines`, never from this sentence) — see "Off-roadmap engines" below. The 2026-07-09 re-sync (liquidity monthly-removal + fibonacci TP3-reset-drop/extend-guard/macro-seed) is now **committed** (`d367b6d`), every engine back at 100% Pine parity. A **fresh 2026-07-10 re-paste** of `mpc_assistant.pine` (524-line staged diff) was audited: **NO engine is stale.** Every engine-affecting change is either visual (swing-label hide toggle, VWAP polyline→plot, KZ/session display windows, session-H/L input consolidation, iBOS/iSOS label reposition) or already-aligned (macro fib run-guard opened to all-timeframes tracking, which the Python engine was already doing unconditionally). **TWO NEW blocks** appeared. One is engine work (now BUILT), one is strategy work (not built): (a) **FAIR VALUE GAPS (FVG)** — a 3-candle displacement gap detector (persists until tapped, FIFO cap); a genuine event detector → **✅ built + Pine-parity-validated 2026-07-10 as `engines/fair_value_gaps/`** (12 unit tests green; `compare_fvg.py --warmup 20` exit 0 on a real `VANTAGE_XAUUSD, 5m` export). The small **`fiboHalfReached`** fib add-on (inbound 0.5 touch) was **✅ built + parity-validated into `engines/fibonacci/`** the same day (2 new tests; `compare_fib.py --warmup 1002` exit 0). **Both ready to commit with the mpc re-paste.** (b) **A+ SETUP SEQUENCE** — a stateful sweep→SOS→fib-entry machine (continuation mode, Cycle-Fib POI, FVG confluence) that **REPLACES the old SETUP GRADING candidate**; it *decides trades*, so it is **strategy-tier, NOT an engine** — it belongs in `strategies/` (MT5/NT8) or a Python bot, and now has both its engine dependencies (FVG + `fiboHalfReached`) in place. **market_structure sync chain NOT triggered** (only label colour/position changed; no detection change). See "Audit findings — 2026-07-10" below.
**Last reviewed:** 2026-08-20 — audit of `700f7f6` + `2952fea` (the tied-extreme swing-label fix). 🔴 **The market_structure sync chain WAS triggered** (a real detection change: on a tied extreme the post-break rescan now keeps the ORIGINAL anchor instead of moving to the later bar, so `bull_bos_l_loc` / `bear_bos_h_loc` change on tie bars). ✅ **All five chain members are already in sync** — `mpc_assistant.pine`, `structure_engine.pine`, `structure_engine_export.pine` and `engines/market_structure/engine.py` all carry both guards, all 17 Pine copies carry them (verified by count, not by trusting the commit message), and the `algos/shared/` shim needs no edit because the fix adds no public field. ✅ **Only ONE Python file in the repo contains the scan** (`engines/market_structure/engine.py`) — the "strategies import the engine and embed no copy" claim is verified, not assumed. **No engine is stale and no new un-extracted block appeared.**

✅ **ONE HARNESS WAS DRIFTED — FIXED 2026-08-20, AWAITING A COMPILE. COUNTING THE GUARDS IS WHAT MISSED IT.** `indicators/engines/fib_export.pine` carries both tie guards — so a per-file guard COUNT says it is patched — but its embedded structure block **has never contained the fallback-promotion `else` branch** that landed in the 2026-07-08 structure re-sync (`f2a8411`) and that `mpc_assistant.pine`, `structure_engine.pine`, `structure_engine_export.pine` and `engines/market_structure/engine.py` all have (`git log -S'fallback_is_hh'` on that path returns nothing — it never had it, this is not a regression from today). ⚠ **The guard itself is NOT inert, and an earlier draft of this entry said it was — that was wrong.** The file DOES promote on the normal path (`st.last_conf_high := st.ash`, before the guard), so on every bar carrying an active swing high the guard reads a correctly-promoted value and behaves exactly as in the reference. `indicators/engines/CLAUDE.md` already recorded that the ordering was checked per file, and that check was right as far as it went. **The divergence is narrower and older than "the guard is inert": it is the `st.ash IS na` path only** — where the reference promotes `last_conf_high := highest_val` and prints an HH/LH label, and this harness promoted nothing and printed nothing, leaving a stale `last_conf_high` for the guard to compare against. ⚠ **`ob_export.pine` does NOT embed this scan at all** (zero `lowest_val`), so it is not affected — checked, not assumed. ⚠ **Consequence to weigh before the next `compare_fib.py` run: the fib gate grades Python fibonacci against a Pine whose STRUCTURE differs from canonical**, so a green there is a green against the wrong upstream on any bar the fallback branch would have fired. **The standing lesson: a guard COUNT proves presence, never placement — and placement was the whole difficulty of this fix.**

**The fix applied (2026-08-20):** the missing fallback branch was added AND the block was reordered to the reference's order — the extreme scan now runs BEFORE the promotion block rather than after it, because the fallback branch reads `highest_val`/`highest_loc` and could not otherwise see them. ⚠ **The reorder is behaviour-preserving and that was checked, not argued**: the scan reads only `high[i]` and `st.last_conf_low_loc`, and the promotion block writes neither. After the patch the two `process()` methods diff to **zero logic differences** — the only remaining lines are the `f_swingCol` colour helper and the `showExternal` display toggle, neither of which exists in the harness by design. Guard placement now verifies OK across **all 17** Pine files. ⚠ **UNCOMPILED — this file has not been through TradingView**, and it must be before `compare_fib.py` is trusted again; the fibonacci gate is stale until a fresh export off the patched harness exists.

✅ **RULE 22: BOTH GATES RE-RUN GREEN ON FRESH 2026-08-20 EXPORTS — AND NEITHER ONE PROVES THE TIE FIX.** Aaron exported both harnesses off TradingView (20,990 M15 bars each). `compare_tradingview.py --warmup 900` on the structure export exits **0**, all eight break-leg columns checked; `compare_fib.py --warmup 900` on the fib export exits **0** across Structure + Sniper + Internal. **That the fib export exists at all is the compile proof for the re-synced harness.**

🔴 **BUT THE TIE FIX IS STILL UNPROVEN, AND THIS WAS MEASURED RATHER THAN ASSUMED.** The same engine with **both guards stripped** was run against the same export and **also exits 0** — so a green here cannot tell the fixed engine from the broken one. Instrumenting the guard explains why: over 20,991 bars the tie CONDITION hit **46 times low / 38 high**, and the anchor **actually moved 0 times** — in every one of those 84 hits the rescan had already landed on the same bar the label was on. **The condition is common; the shape that stacks a label is not.** The fix's own replay found ~1 stacked pair per 26,000 M15 bars, so ~0.8 expected here and 0 observed is exactly on the nose. ⚠ **Same story for the fallback branch added to the fib harness: reached 0 times in 20,991 bars.** The **reorder** that came with it IS validated — it moves the normal path on every bar and the gate is green across all of them — but the added branch itself is untested by this export. **To exercise either, the export has to be far longer or on a much lower timeframe.** ✅ **MACRO FIB NOW CHECKED TOO** — a ≤5m export followed (`VANTAGE_XAUUSD, 5_84d6c.csv`, 20,376 M5 bars) and `compare_fib.py --warmup 900` exits **0** at scope **Structure + Sniper + Macro + Internal**. **All four fibs are green against the re-synced harness; the fibonacci gate is fully closed.** ⚠ **And it changes nothing about the tie fix — measured again on this export rather than assumed:** tie condition hit **47 low / 45 high**, anchor actually moved **0**, fallback branch reached **0**. Two independent exports, two timeframes, 41,368 bars between them, and the changed branch was never entered once.

🔴 **THE TRANSFERABLE PART: a parity gate that a MUTANT also passes is not evidence about the thing you changed.** Running the stripped-guard engine took one minute and turned "green, we are done" into "green, and blind to this fix". **Rule 14 says a green gate never proves either side RIGHT; this is the cheap way to find out whether it even LOOKED.** Do it whenever a fix touches a rare branch.

**Superseded — the reason the commit gave, which was wrong:** The commit records *"a sweep of the machine found no structure export at all"* — that is **wrong**: `engines/market_structure/exports/` holds three exports carrying `px_ash`/`px_asl`/`px_dir` AND all eight break-leg columns, and `compare_tradingview.py --warmup 1600` on the newest (`VANTAGE_XAUUSD, 5_9c376.csv`, 9,270 bars) exits **0, fully green**. ⚠ **That green does not validate the fix, and reading it as a pass would be the mistake.** Every export here is from **July**, generated by the PRE-fix harness, so a green means only that post-fix Python still matches pre-fix Pine — i.e. **the tie path was never exercised on those bars.** The fix's own measurement puts ties at roughly 1 per 25,000 bars; 9,270 bars is too small to expect even one. **The gate is green on the untouched 99.99% and silent on the branch that changed** — Rule 14 exactly. To actually close Rule 22: put the PATCHED `structure_engine_export.pine` on a chart, export a fresh CSV, re-run the tool.

⚠ **The LIVE bot does not have this fix.** `mpc_sos_fade_demo`'s frozen `deployed/` snapshot on the VPS carries the pre-fix engine (verified over SSH with a positive control, so the negative is real). A `git pull` cannot move it — only `promote.py` can. **Trades are NOT affected** (the fix's own replay found break-leg prices and break counts identical, 0 differences); what differs is duplicate swing LABELS. So this is a promote-when-convenient, not an incident.

**Previously reviewed:** 2026-08-12. ✅ **The "THREE ENGINES STALE" alarm below was RESOLVED the same day it was raised** — `a1b726d` (2026-07-31) re-synced `fair_value_gaps`, `fibonacci` and `liquidity` and validated them on two real exports. It is left in place because the write-up under it is the useful part, but **read it as history: there is no open staleness here.** ⚠ **A red banner that outlives its fix is worse than no banner** — the next reader either acts on a closed problem or learns to scroll past the red, and both cost more than the alarm ever saved. The original entry follows.

**Original entry, 2026-07-31:** 🔴 **THREE ENGINES STALE after 10 uncaught commits** (diff `48c183f..HEAD`, 2,468+/738- on `mpc_assistant.pine`; `48c183f` is the 2026-07-17 paste the 2026-07-19 grand export validated). ✅ **The market-structure sync chain was NOT triggered** — `process()` and `processMTF()` are byte-identical apart from five appended label-hiding lines, internal structure changed only its break-line COLOURS, and `structure_engine.pine` still diffs clean against mpc. 🔴 **`engines/order_blocks/` needs a RE-PORT, not a re-sync** — structure breaks no longer create blocks at all (`f_obMake` + all four creation sites commented out); blocks are now born at `ta.pivot(2,2)` TURNS from two sources (an impulsive engulfing PUSH read 10 bars late, and the turn itself), gated by a 1.0×ATR departure test, a 0.5 overlap dedupe and a 2.0×ATR height ceiling, with mitigation redefined to wick-tap / close-inside-then-out / close-through, an `OB_MAX_AGE = 500` cap and `maxActiveOB` 2 → 10. 🔴 **`engines/sessions/` STALE — the three session windows moved** (Tokyo `2000-0500` GMT-4 → `0900-1800` Asia/Tokyo; London `0400-1300` GMT-4 → `0800-1700` Europe/London; NY `0900-1800` GMT-4 → `0800-1700` America/New_York). Tokyo is UTC-identical year-round, but London and NY were pinned to a FIXED GMT-4 and now follow real DST, so under BST/EDT both shift **one hour earlier** — roughly seven months a year. Kill zones and the NY opening range are unchanged. Cascade: **`engines/liquidity/` STALE-BY-INPUT** (session H/L), **`engines/session_volume_profile/` UNAFFECTED** (Asia only, and Asia is value-identical). 🔴 **`engines/fibonacci/` MacroFib STALE** — the cycle origin moved from `macro_ll_since_bear_sos` to the break leg's own `bull_bos_low`, and a new `macroCycleTf = 1` + `f_cycleState()` sources the whole cycle from a **1-minute `request.security`** on every higher chart, which the single-stream Python engine cannot reproduce without a design decision. Structure/Sniper/Internal fibs unaffected. **Default drift:** `fvgMaxCount` 10 → 8 (FVG detection itself is byte-identical, so parity holds — sync the Python default). Every other engine input was frozen into a constant **at its existing value** (the 121→24 student-panel lockdown), and detection is now always-on with new `draw*` flags gating drawing only. **STALE HARNESSES:** `ob_export.pine`, `sessions_export.pine`, `liquidity_export.pine`, `fib_export.pine`. **IN PARITY:** market_structure, equal_highs_lows, rsi_divergence, vwap, session_volume_profile, fair_value_gaps (detection), fibonacci Structure/Sniper/Internal, regime, news. Two new blocks appeared and **both are strategy-tier** — a B-LEG tracker + BLEG SZ box (already built as `mpc_b_leg_strategy.pine` / `strategies/python/mpc_bleg/`; worth a drift check against this copy) and an A+ REV SETUP rework (split sweep/divergence expiry windows, `aplusDivOnly` true→false, a deep-level re-entry ladder, a LEVELS row, five-tier alerts). No new un-extracted engine-tier block. See "Audit findings — 2026-07-31" below. Previously 2026-07-14 — ✅ **ALL ENGINES RE-VALIDATED ON ONE FRESH COMBINED EXPORT.** After the FVG re-sync + order_blocks 6→2 default sync below, a single fresh `VANTAGE_XAUUSD, 5m` export (`…5ead0.csv`, 10,364 bars) carrying the fvg/ob/structure/fib/liquidity harness columns drove all five compare tools to exit 0: `compare_fvg.py --max-count 6 --threshold-pct 0.1 --warmup 886`, `compare_ob.py --warmup 353` (cap 2 default — confirms the new default on fresh data), `compare_tradingview.py --warmup 887`, `compare_fib.py --warmup 887`, `compare_liquidity.py --htf-rollover 18 --warmup 1562` (fresh post-change confirmation). `rsi_divergence` was already green on `…b07c0.csv` (unchanged Pine). **Every engine is in 100% Pine parity; FVG + order_blocks are committable.** The audit that preceded this: clean working tree across 8 commits since the `choch_lock` re-sync (`8f6b5ca`), diff `8f6b5ca..HEAD` on `mpc_assistant.pine` = 477 lines (330+/147-). 🔴 **`engines/fair_value_gaps/` is STALE — the FVG detection AND lifecycle were redefined.** Detection dropped the "clean 3-candle impulse" rule (three same-direction, progressively-closing candles) for the **LuxAlgo imbalance** definition — bar A / bar C don't overlap, the middle bar's close cleared the gap — and the size floor moved from a `fvgMinTicks` (default 0) tick filter to a **hardcoded 0.1%-of-price** threshold (`fvgThreshPct = 0.1`). Mitigation flipped from "delete on a **tap of the near edge**" to "delete only when a candle **CLOSES fully past the far edge**" (a wick in no longer kills the gap). `fvgMaxCount` default also 3→6. Engine STALE, harness `indicators/engines/fvg_export.pine` STALE, re-run `compare_fvg.py`. **market_structure sync chain NOT triggered** (zero hunks in `process`/detection; only `showSwingLabels` default true→false, visual). **`engines/liquidity/` heavily restructured but appears value-identical on intraday** — needs a confirmatory `compare_liquidity.py` re-run, not a code change: PDH/PDL & PWH/PWL security fetches refactored (branch on chart TF, but intraday value = previous completed period, unchanged), `f_originHigh/Low` now start each line at the candle that formed the level (visual line-origin only), a `showMitLiq` toggle + `f_liqMitigate` gained a `showMit` param (mitigation DETECTION untouched — only whether broken lines stay drawn). **`engines/order_blocks/` — `maxActiveOB` default 6→2** (parameterized FIFO cap, still user-tunable; sync the Python default when convenient, not a parity break). Everything else IN PARITY: sessions/vwap/fibonacci/svp/rsi_divergence/regime/news saw only input-default or display-scope flips (`showVwap` true→false, `showHistoricSessions` false→true, `hideFibsSub5m` false→true, `showMacroFib`/`showIFib`/`showDiv`/`showDivHistory` defaults, master `showTradeTools`/`showFibTool` true). The large A+ SETUP block rework (renamed **REV SETUP** in the table, divergence-late **retro-link** to a prior SOS, Div-Only arming, ignore-time-window option, E2/E3/E4 0.702/0.786/0.886 latches, precise FVG/SZ "tapped-into" tests, an EARLY-tier `alert()`, CONT rows commented out) is all **strategy-tier — not an engine**. No new un-extracted block. See "Audit findings — 2026-07-14" below. Previously 2026-07-12 — ✅ **RE-SYNC APPLIED AND PINE-PARITY CONFIRMED.** The `choch_lock` chain break found by the second audit of the day has been fixed end-to-end per Aaron's "accept mpc as source of truth, accept the risk" call: all four detection changes are now byte-identical across `mpc_assistant.pine`, `structure_engine.pine`, `structure_engine_export.pine`, `ob_export.pine`, `fib_export.pine` and `mpc_strategy.pine`, and ported into `engines/market_structure/engine.py` (+ `types.py` label-domain widening to ASH/ASL). 64/64 tests green. **Root cause confirmed on Aaron's 17-Jun-2026 XAUUSD 15m chart: `choch_lock` suppressed the CHoCH, which both mislabelled the break as a BOS AND — via `old_is_hh = is_choch ? true : …` — suppressed the higher high. One bug, two symptoms; the removal was the fix, not a side effect.** ✅ **All three parity checks re-run on one fresh combined `VANTAGE_XAUUSD, 5m` export (9270 bars) and green:** `compare_tradingview.py --warmup 365`, `compare_ob.py --warmup 548`, `compare_fib.py --warmup 368` — all exit 0. `engines/fibonacci/` and `engines/order_blocks/` were STALE-BY-INPUT and are re-validated. **Safe to commit.** See "Re-sync applied — 2026-07-12" below. The audit that found it: (a fresh working-tree re-paste vs commit `7e0b30e`, 66-line diff — 24+/42-. 🔴 **THE MARKET_STRUCTURE SYNC CHAIN WAS TRIGGERED — first time since 2026-07-08.** Two real detection changes in mpc's `process`: (1) **`choch_lock` no longer gates CHoCH** (`is_choch = st.dir == -1 and not st.choch_lock` → `is_choch = st.dir == -1`, bull 648 / bear 772) — the flag is still declared/set/released but nothing reads it, so it is now inert in mpc while `structure_engine.pine`, `structure_engine_export.pine` and `engine.py` all still gate on it; (2) **`last_conf_high`/`last_conf_low` no longer update on a CHoCH** (now wrapped in `if not is_choch`, bull 697 / bear 820) — on an SOS the pullback extreme prints as an ACTIVE swing (ASH/ASL) and is confirmed only by the NEXT opposite break. **STALE as one unit: `indicators/engines/structure_engine.pine`, `indicators/engines/structure_engine_export.pine`, `engines/market_structure/engine.py`.** Cascade: **`engines/fibonacci/` (MacroFib reads `bull_sos` + `last_conf_high`) and `engines/order_blocks/` (creates OBs on `bull_sos`/`bear_sos`) are STALE-BY-INPUT** — their own code is fine, but their inputs and their structure-embedding harnesses (`fib_export.pine`, `ob_export.pine`) are not. **Public-API note:** `broken_high_label`/`broken_low_label` are typed `"HH"|"LH"` / `"HL"|"LL"`; mpc now prints ASH/ASL on a CHoCH, widening that domain. `indicators/strategies/mpc_strategy.pine` (the brother's backtest) also still carries the OLD `choch_lock` logic. The RSI-divergence 3-day-history source bug flagged in the audit below got **worse** (moved from the drawing layer into the detection `if`) but stays inert on intraday → `engines/rsi_divergence/` is still 100% parity. See "Audit findings — 2026-07-12 (SECOND — choch_lock removal)" below. Previously today: fresh working-tree re-paste vs commit `5c477ac`, 308-line diff — 202+/106-. **NO engine was stale; market_structure sync chain NOT triggered.** The paste was (a) the `marketStructureOnly` master toggle REPLACED by two positive master switches — `showTradeTools` (FVG/OBs/sessions/KZ/liquidity/VWAP/MV) and `showFibTool` (external/internal/cycle fib) — with `marketStructureOnly` now *derived* (`not showTradeTools and not showFibTool`); plus a `hideFibsSub5m` timeframe gate on the fib drawing/compute. Same effective defaults as before (everything non-structure off) — purely visual; (b) RSI-divergence inputs **frozen into hardcoded constants** (`divRsiLen` 14, `divPivotLen` 5, `divOS` 25, `divOB` 75, `divValidBars` 100, `divVeto` true, extremes 80/20) — these match `engines/rsi_divergence/` defaults EXACTLY, so the 5c477ac sync is confirmed correct and nothing further is needed; the div drawings became a FIFO-capped array (`divMaxCount` 10) instead of a single deleted-on-stale line — visual; (c) a heavy A+ SETUP SEQUENCE rework (staleness window bars→MINUTES, a session-gap guard, daily-sweep age cap, arm-only-when-idle, A+-owned 0.5/0.618 latches, HTF-bias warn/block, Sniper Zone accepted as location confirmation alongside FVG, optional INT trigger, divergence veto REMOVED from A+) — all **strategy-tier**, the A+ machine is not an engine. **ONE SOURCE BUG flagged (not an engine issue):** the new "Show Divergence History" 3-day filter tests `time[divPivotLen] >= time - 259200000`, which measures the pivot's age as `divPivotLen` bars — always ~25 minutes on a 5m chart — so the toggle is inert on every intraday timeframe. See "Audit findings — 2026-07-12" below. Previously: 2026-07-11 (SECOND audit of the day — a fresh working-tree re-paste vs commit `21cbe43`, 484-line diff. **NO engine is stale; market_structure sync chain NOT triggered; no `*_export.pine` harness or `compare_*.py` needs re-running.** The paste is (a) a new `marketStructureOnly` master DISPLAY toggle that force-hides every non-structure feature — each `show*` flag renamed `<flag>Input` and gated `marketStructureOnly ? false : …Input` — purely visual; (b) a heavy rework of the A+ SETUP SEQUENCE (edge-triggered arming on new sweep OR new divergence, stale-arm clearing, a separate CONT continuation trade type with its own row + chart labels, a divergence/extreme-RSI VETO, FVG now REQUIRED for READY) — all **strategy-tier**, the A+ machine is not an engine; (c) a divergence-staleness rule (`bullDivStale`/`bearDivStale`: a div goes stale on the next external break) + drawing-deletion — **strategy-tier composition** of RSI+structure, not the standalone RSI engine's job. **ONE engine-relevant nit:** the RSI-divergence input DEFAULTS drifted `divOS` 30→25 and `divOB` 70→75 — detection formula unchanged (still `<= divOS` / `>= divOB`), so the engine is parity-valid, but its default params should be synced 30→25 / 70→75 (and `compare_rsi_div.py` re-run at the new defaults) when convenient. See "Audit findings — 2026-07-11 (marketStructureOnly + A+/CONT rework)" below. Earlier today: RSI Divergence detector BUILT + PARITY-VALIDATED as `engines/rsi_divergence/` — engine + harness + compare tool + 9 tests green; `compare_rsi_div.py --warmup 1630` exit 0 on a real `VANTAGE_XAUUSD, 5m` export.)

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

- **`engines/regime/`** — market regime classifier (separate source, not the SMC indicator).
- **`engines/market_structure/`** — external + internal structure (BOS/CHoCH, swings, HH/HL/LH/LL). 100% Pine parity.
- **`engines/fibonacci/`** — Structure, Sniper, and Macro fibs. 100% Pine parity. Downstream of `engines/market_structure/`.
- **`engines/order_blocks/`** — bull/bear OB zones off external + internal breaks, with mitigation + FIFO eviction. Sibling of `engines/fibonacci/` (consumes `engines/market_structure/` directly). Ported line-by-line, 12 unit tests, 100% Pine parity on two independent real exports — `VANTAGE_XAUUSD, 5m` (`--warmup 594`) and `VANTAGE_XAUUSD, 15m` (`--warmup 207`), confirming it's timeframe-agnostic (harness: `indicators/engines/ob_export.pine` + `engines/order_blocks/tools/compare_ob.py`). Re-validated after the 2026-07-08 structure re-sync: engine untouched, but its harness `ob_export.pine` (which embeds the structure engine) was re-synced with the two f2a8411 changes, then re-validated 2026-07-09 on a fresh `VANTAGE_XAUUSD, 5m` export (12,618 bars; all OB fields match, `--warmup 1133`, exit 0).
- **`engines/sessions/`** — Tokyo/London/NY session windows + running session H/L, the three NY kill zones, and the NY opening range. The first **time-driven** engine (input = the bar's UTC timestamp + high/low, not just OHLC); standalone (depends on nothing). Ported line-by-line, 17 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (all 18 fields, `--warmup 263`), re-confirmed on a 15m export for the 16 timeframe-agnostic fields (harness: `indicators/engines/sessions_export.pine` + `engines/sessions/tools/compare_sessions.py`). Unblocks the session-scoped parts of Liquidity (session H/L levels) and VWAP (session anchor).
- **`engines/liquidity/`** — the prices price runs toward and grabs: prev day/week/month H/L (PDH/PDL/PWH/PWL/PMH/PML), previous-week-close (PWC), the H4 sweep (SSH/BSL), and Asia/London/NY session H/L, with mitigation (sweep vs break) tracking. Consumes `engines/sessions/` for session H/L (composes it); reconstructs the day/week/month/H4 levels from the bar stream. **Non-repainting by Aaron's explicit decision (2026-07-05): every HTF level uses the PREVIOUS completed period only — the engine never forecasts the current period's high/low.** Ported, 15 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (11,457 bars; all 33 fields — 15 level prices, their mitigation flags, 4 boundary-roll pulses — match, `--htf-rollover 18 --warmup 4653`, exit 0; harness: `indicators/engines/liquidity_export.pine` + `engines/liquidity/tools/compare_liquidity.py`). Calibrated boundary: XAUUSD session opens 18:00 NY (baked in as the default).
- **`engines/vwap/`** — the session VWAP: a volume-weighted running mean of `hlc3` (`ta.vwap(hlc3)`), re-anchored each trading day, plus a derived close-vs-line cross. First engine to need a **volume** column in the feed (XAUUSD tick volume — what the Pine `ta.vwap` already reads). Time-driven; reconstructs the trading-day anchor directly (the **same** 18:00-NY boundary the liquidity daily level uses), so it does not compose the sessions engine. Ported line-by-line from `mpc_assistant.pine` line 852, 13 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (6,973 bars; both fields — VWAP value + trading-day anchor pulse — match, `--htf-rollover 18 --warmup 90`, exit 0; harness: `indicators/engines/vwap_export.pine` + `engines/vwap/tools/compare_vwap.py`). Uses a **relative** tolerance (1e-6) because the value is a cumulative sum that drifts at float-rounding level — unlike the copied-value level engines' exact match.
- **`engines/session_volume_profile/`** — the Session Volume Profile: on each **Asia** session close, a 50-row volume profile over the session range whose highest-volume row gives the **POC** (the "MV" line), plus the MV confirmation (price straddling the POC). Composes `engines/sessions/` for the Asia window/edges (like liquidity) and needs the **volume** feed (like VWAP). Two Pine quirks ported exactly: the session-close bar is folded into the profile, and the bull/bear two-array newest-first summation is kept (float addition is not associative — collapsing it could flip a near-tie POC row). Ported from `mpc_assistant.pine` (SVP block 2554, MV slot 2772), 12 unit tests, **100% Pine parity**. The row count was re-synced **100 → 50** on 2026-07-09 (mpc line 317) and re-validated on a fresh `VANTAGE_XAUUSD, 5m` export (13,147 bars; all 3 fields — POC price + form pulse + sweep state — match, `--warmup 251`, exit 0; harness: `indicators/engines/svp_export.pine` + `engines/session_volume_profile/tools/compare_svp.py`). The POC uses an **exact** (1e-6) tolerance — it is a deterministic formula on the copied session H/L + integer volume, so it is bit-identical, unlike VWAP's cumulative value.
- **`engines/rsi_divergence/`** — Wilder-RSI regular-divergence detector (standalone; sibling of FVG). Ported line-by-line, 9 tests, **100% Pine parity** (`compare_rsi_div.py --warmup 1630`, exit 0). Feeds the A+ setup "+ DIV" tag.
- **`engines/equal_highs_lows/`** — EQH/EQL liquidity-level detector (standalone; sibling of FVG + RSI-divergence). Two consecutive same-side strict price pivots within an ATR(50)×mult band → a level (EQH `max` / EQL `min`), FIFO cap per side, close-through mitigation. Ported line-by-line from the mpc EQ block, **7 unit tests green (built 2026-07-18)**. **Pine-parity VALIDATED 2026-07-19 (exit 0)** on a 16,639-bar `VANTAGE_XAUUSD, 5m` grand export — the run caught + fixed a real pivot-tie bug (Pine allows a LEFT tie / strict RIGHT; the last bar of an equal run is the pivot). The Pine's `eqExemptFvg` FVG↔EQ coupling is MODELLED (FVG `update()` takes `eq_levels`/`eq_tol`; consumer runs EQ→FVG) — see the 2026-07-18/07-19 notes.

---

## Still to build

- **Internal Fib** (new; found 2026-07-06, now FULLY implemented in source as of the 2026-07-08 paste) —
  a **4th fib** for `engines/fibonacci/`, anchored to INTERNAL structure (iBOS/iSOS) instead of external
  swings, with a live-updating anchor (extends to the running low/high since the internal break), the
  same 0.618 gate as the Structure fib, and a TP3-hit reset (`iFibResetActive`), cleared on any external
  BOS/SOS. Pine block `GRP_IFIB` inputs + the `INTERNAL FIB` compute/touch/draw block + the
  internal-structure anchor captures. Not covered by any engine yet. Port as `InternalFib` alongside
  `StructureFib` and add `px_ifib_*` columns to `indicators/engines/fib_export.pine`. See "Audit findings —
  2026-07-08". **Do this as part of the fibonacci re-sync (the engine is STALE anyway).**

- **A+ SETUP SEQUENCE — STRATEGY, not an engine** (new; found 2026-07-10 paste — **REPLACES the
  2026-07-09 SETUP GRADING checklist**, deleted from source). This is **trade-decision logic**, so it is
  strategy-tier, not an engine: engines report facts, strategies decide trades, and this decides trades.
  It sequences engine events into an entry, per side: (1) SWEEP — a tracked HTF liquidity grab
  (`recentSSL`/`recentBSL`); (2) MSS — an external SOS after the sweep within `aplusWindow` bars;
  (3) ENTRY — the SOS leg's fib retrace (0.5 tap → EARLY, 0.618 → READY). Plus a **Cycle-Fib POI** latch
  (discount 0.618–0.886 long / premium ≥0.382 short), **FVG confluence** (a live gap in the 0.5–0.886
  zone), a **continuation mode** (next same-side BOS after a completed A+ re-arms the tiers), and death
  rules (opposite SOS, close past fib 1.0, TP3 hit). It composes existing engine outputs + the new FVG
  engine + the `fiboHalfReached` fib flag. It does **not** go on the engine roadmap — it belongs in the
  strategy layer (`strategies/` for the MT5/NT8 build, or a Python bot per `docs/BOT_DEVELOPMENT_METHOD.md`),
  and it depends on the two engine items below being built first. Currently drives only the JARVIS "A+
  SETUP" table row. **Reworked twice since (2026-07-11, 2026-07-12) — port the CURRENT shape, not this
  paragraph:** edge-triggered arming on a new sweep OR a new divergence, arm-only-when-idle, a
  TIME-based staleness window (`aplusWindow` in minutes, against an `armTime` stamp — a bar count is
  fragile across timeframes), a session-gap guard that suppresses arming/death on the daily-close bar,
  a 24h age cap on daily sweeps, A+-owned 0.5/0.618 latches that survive a fib redraw, FVG **or** Sniper
  Zone as the location confirmation for READY, an optional INT (iSOS/iBOS) trigger, HTF-bias warn/block
  off `wEstState`/`dEstState`, and a separate CONT (continuation) trade type with its own row. The
  divergence veto now applies to CONT only, not A+.

- **FAIR VALUE GAPS (FVG)** — ✅ **RE-SYNCED + PINE-PARITY RE-VALIDATED 2026-07-14** to the mpc FVG
  rewrite (LuxAlgo imbalance + 0.1%-of-price floor + close-past-far-edge mitigation + max_count 6);
  14 unit tests green; `compare_fvg.py --max-count 6 --threshold-pct 0.1 --warmup 886` exit 0 on a
  fresh `VANTAGE_XAUUSD, 5m` export (10,364 bars). Detail below is the ORIGINAL 2026-07-10 build note
  (old clean-impulse detection) — kept for the port history; the current detection/mitigation rules
  are in `engines/fair_value_gaps/CLAUDE.md`. Original note:
  ✅ **BUILT + PARITY-VALIDATED 2026-07-10** as `engines/fair_value_gaps/`
  (engine + types + `__init__` + CLAUDE.md + 12 hand-traced unit tests, green). A clean-displacement gap
  detector: bullish gap = void between candle A's high and candle C's low when three same-direction candles
  close progressively higher (bearish mirrors); confirmed bars only; **persists until price taps its near
  edge** (deleted on tap, NOT on BOS/SOS); FIFO cap (`fvgMaxCount`). Standalone (OHLC-only — the Pine's
  directional-visibility filter is drawing, not reproduced). **`compare_fvg.py --warmup 20` → exit 0** on a
  real `VANTAGE_XAUUSD, 5m` export (8,578 bars): all 3 gap slots × top/bottom/is-bull + count + formed/mit
  pulses matched Pine on every warm bar. The 20-bar warm-up is a lingering pre-window bear gap in the Pine
  export whose near edge price never revisited (never tapped) — the cold-started Python engine can't know an
  off-screen gap; it flushes by bar 20. **Harness gotcha (fixed):** the first export carried NO FVG columns
  because the plots used `display = display.none`, which TradingView excludes from "Export chart data"; the
  plots now use transparent colours (same as `fib_export.pine`). Ready to commit with the mpc re-paste.

- **`fiboHalfReached` fib add-on** — ✅ **BUILT + PARITY-VALIDATED 2026-07-10** in `engines/fibonacci/`
  (StructureFib now emits `half_reached`: the **inbound 0.5 touch** during the retrace, ungated, distinct
  from the outbound TP1; a first-touch latch reset each leg). Additive — no existing fib level changed; 2
  new unit tests green (42 total). `fib_export.pine` gained a `px_fibo_half_reached` column and
  `compare_fib.py` compares it. **`compare_fib.py --warmup 1002` exit 0** on a fresh combined
  `VANTAGE_XAUUSD, 5m` export (7,891 bars) — `px_fibo_half_reached` matched Pine on every warm bar
  alongside all existing fib fields. Ready to commit (with the mpc re-paste).

- **RSI Divergence detector** — ✅ **BUILT + PARITY-VALIDATED 2026-07-11** as `engines/rsi_divergence/`
  (engine + types + `__init__` + CLAUDE.md + 9 tests, green). A standalone regular-divergence detector
  at the extremes: bullish = price lower-low while Wilder's RSI (`ta.rsi`, len 14) prints a higher-low
  from oversold (≤`divOS`); bearish = the overbought mirror. Pivots via `ta.pivotlow`/`ta.pivothigh` on
  RSI (`divPivotLen`), so it confirms `divPivotLen` bars after the extreme (non-repainting). Emits a
  divergence event per side + the live-confluence flags (`bull_active`/`bear_active`, valid
  `divValidBars` bars). Standalone (no upstream engine, no volume, no timestamp — close for RSI + the
  bar's high/low for the anchor) — same shape as the FVG engine. Feeds **only** the JARVIS "A+ SETUP"
  table row as a "+ DIV" confluence tag (does not alter the A+ sequence's staging). Three Pine details
  ported exactly: Wilder RSI (SMA-seeded RMA, not a gain average), strict `(2·L+1)`-window pivots (the
  same semantics `market_structure` ports), and the `low[divPivotLen]`/`high[divPivotLen]` price anchor.
  **`compare_rsi_div.py --warmup 1630` → exit 0** on a real `VANTAGE_XAUUSD, 5m` export (9,830 bars):
  RSI value + both RSI pivots + both divergence pulses + both live flags + both ages matched Pine on all
  8,200 warm bars (harness `indicators/engines/rsi_div_export.pine`). The 1,630-bar warm-up is the cold-start
  (Pine opens with off-window RSI + divergences; its first-bar ages are 471 / 1902). **2026-07-12: the
  Pine froze all of these into hardcoded constants (14 / 5 / 25 / 75 / 100), which match the engine's
  defaults exactly — the params are now settled, not user-tunable.**

- **HTF Directional Bias helper** (candidate since 2026-07-08; simplified 2026-07-10) — `f_biasState` /
  `f_htfBias`: Daily+Weekly Established Context bias (Closed[1] vs Closed[2]) with sweep detection. The
  "Current Forming" half (Live[0] vs Closed[1]) was **removed from source 2026-07-10** ("never consumed"),
  so it now returns a 2-value shape. Still feeds only the JARVIS table; no engine yet. Port the simplified
  shape if extracted (the A+ sequence could consume it as a bias filter).

Everything else is ported. The other forward work is *consumption*, not extraction: give each engine
an `algos/shared/` shim when a bot first uses it, wire the news `coverage_start_ms` into the backtest
lab, and build the backtest-first bots per `docs/BOT_DEVELOPMENT_METHOD.md`.

---

## Audit findings — 2026-08-23 (`/audit-engines`, clean tree, one commit since: `f4b0410`) 🟢 STRUCTURE CHAIN SYNCED, GATE GREEN

**One commit touched an engine block: `f4b0410` — "a break may not install a swing the break itself
refused".** A structure break is decided on a CLOSE; the rescan that follows read the WICK, so a bar
that pierced the level, closed back inside and was correctly REFUSED could then be installed as the
swing behind that same break — the engine anchoring backwards onto a candle it had just rejected.

### The sync chain — all four links carry ONE condition ✅

Checked by diffing the code, not by reading the commit message:

| Link | Verdict |
|---|---|
| 1. `mpc_assistant.pine` structure block | patched, 4 sites (2 in `process`, 2 in `processMTF`) |
| 2. `structure_engine.pine` | **byte-identical to link 1** — 395 code lines each, zero differences in `process` |
| 3. `structure_engine_export.pine` | identical logic; the only 15 differences are `f_swingCol()` label colour (13) and two `showExternal` visibility blocks — **visual, per this command's own rule** |
| 4. `engines/market_structure/engine.py` | both sites present, same condition and same placement (AFTER the promotion, which is where the previous attempt at this fix got it wrong) |
| 5. `algos/shared/structure_engine.py` | pass-through shim, no detection logic, no new public field to expose |

⚠ **`processMTF` is NOT ported and does not need to be** — link 2 has no MTF method, so the Python's
two sites are the two in `process`, which is called once for external structure. Correct as-is.

### 🔴 The gate — RED, and the commit's own account of why is WRONG

The commit says *"engines/market_structure/exports/ is empty"*. **It is not** — it holds six CSVs,
four of them carrying `px_ash`. Left standing, that sentence tells the next reader there is nothing
to run, when in fact the gate runs and answers.

**MEASURED 2026-08-23 on `engines/VANTAGE_XAUUSD, 15_9d44d.csv` — taken 2026-08-20 23:08, i.e.
AFTER the tie guard and BEFORE this fix, so it isolates exactly this change:**

```
20,990 bars compared     77 mismatching bars (0.37%), bars 14123 → 14199, then RESYNCS
fields: px_asl 48 · px_lcl 31 · the four *_bos level/ago fields 6
```

**Every diverging field is a swing ANCHOR or a level derived from one. `px_dir`, `px_new_sh`,
`px_new_sl` and the break/CHoCH event flags do not diverge at all** — so the fix moves where a swing
sits and does not move whether a break fires, which is what it claims to do. A bounded episode that
resyncs is this harness's own signature for a tie-break edge case rather than a logic gap.

⚠ **This is NOT a green gate and must not be read as one.** It is the fix's footprint measured
against a pre-fix twin. Rule 22 is unsatisfied until `structure_engine_export.pine` is re-exported
from TradingView and `compare_tradingview.py` exits 0 — **and only a human can take that export.**

### ✅ GATE GREEN — the fresh export arrived the same day

Aaron re-exported `structure_engine_export.pine` on 2026-08-23:

```
compare_tradingview.py "engines/VANTAGE_XAUUSD, 5_0bcd2.csv"
20,574 M5 bars · major_length=15 · tol=1e-06 · break-leg columns present and checked
✓ PARITY: every field matched on every bar.
```

**Rule 22 satisfied for `engines/market_structure/`.** ⚠ Rule 14 is not repealed by it: green says the
Pine and the Python AGREE, never that either is right, and nothing at all about a branch neither one
entered. ⚠ **It is an M5 export where every previous structure gate ran on M15** — the engine is
timeframe-agnostic so this is a legitimate pass, but it is a DIFFERENT window, not a re-run of the
old one, and it does not re-validate anything the M15 exports covered.

🔴 **The transferable finding is how cheap the answer was once the right file existed.** The red above
had a full mechanical account attached — 77 bars, named fields, a bounded episode that resyncs — and
every word of it was about a stale twin. **A parity red is a claim about a PAIR. Establish which half
is older before you spend a day inside the newer one.**

⚠ **The three July exports are useless for this** — they diverge in the hundreds across `px_dir`,
`px_i_mode` and `px_i_sw`, because two further fixes have landed since. Do not gate on them.

### The knock-on: B-LEG is green too, A+ is still waiting on its export

`compare_strategy.py` was exit 0 at `af62847` and diverges at bar 14126 (`px_l_stage py=3 pine=2`)
at `f4b0410`, on all three A+ exports — the same bar the structure episode opens on. **Same cause,
one layer up: new Python against an old Pine twin.** `compare_bleg.py` was red on its only export for
the same reason.

✅ **B-LEG re-ran GREEN on a fresh export the same day** — `engines/VANTAGE_XAUUSD, 5_f8228.csv`,
20,573 M5 bars, identical from bar 0. That confirms the knock-on diagnosis rather than merely being
consistent with it: the code never moved, only the twin did.

🔴 **A+ IS STILL RED AND IS THE ONE THING OUTSTANDING.** Its export twin was not on the chart when
these two were taken. ⚠ **Do not read B-LEG's green as covering it** — they are separate strategies
with separate harnesses, and B-LEG's pass says nothing about A+'s stage ladder. `mpc_strategy_export.pine`
has to go on a chart and be exported before rule 22 is satisfied for `strategies/python/mpc_sos_fade/`.

⚠ **A+ and B-LEG cannot share one export file**: their instrumentation blocks emit column names that
collide almost completely, so one CSV could not tell whose numbers are whose. The structure engine's
columns do NOT collide with either, so it can ride along on the same chart as one strategy — which is
how these two files were taken.

### ✅ The LIVE bot is unaffected, and it was checked rather than assumed

`algos/markets/fx/instances/mpc_sos_fade_demo/deployed/` carries its own frozen `engines/`, and that
copy does **not** contain the guard. A `git pull` on the VPS cannot move it; only `promote.py` can.
**The engine gate is now green, and that is still not clearance to promote — the LIVE bot is A+, and
the A+ gate is the one still red.**

### Everything else — IN PARITY, nothing new to extract

Coverage scan of all 7,152 lines of `mpc_assistant.pine`: every functional block still maps to a
canonical engine (structure, order blocks, FVG, EQH/EQL, RSI divergence, sessions/kill zones/NY
range, VWAP, liquidity, fibs, SVP). The A+ and B-LEG sequences are strategy-tier as before;
Continuation is still disabled; Internal Fib is still deleted from the Pine. **No new un-extracted
block.** `engines/market_structure/tests` 17 green.

---

## Audit findings — 2026-07-31 (10 commits since the last validated paste; clean tree, diff `48c183f..HEAD`) 🔴 3 ENGINES STALE

Working tree clean. Audited the cumulative diff of `indicators/engines/mpc_assistant.pine` from `48c183f`
(2026-07-17 — the paste every engine was last validated against, on the 2026-07-19 grand export) to
`HEAD` (`9c34f04`): **3,206 lines, 2,468+/738-** across 10 commits. Report only; no engine code changed.

**✅ MARKET-STRUCTURE SYNC CHAIN NOT TRIGGERED.** `process()` is byte-identical over its whole 432
lines except **five appended lines** that set the ASH/ASL label `textcolor` to `color(na)` when
`showExternal` is off — visual. The swing feed is unchanged (`majorLength = 15`,
`ta.pivothigh/pivotlow(high/low, majorLength, majorLength)`). Internal structure detection is
unchanged: every hunk in that block is break-line **RECOLOURING** (new `f_iBrkCol()` + four `line`
handles `i_last_hl_line` / `i_last_lh_line` / `i_sos_hh_line` / `i_sos_ll_line`, so an iBOS/iSOS label
no longer sits on a line drawn in the opposite colour). `processMTF()` is byte-identical too.
**Verified directly:** `diff` of `structure_engine.pine`'s `process` against mpc's is empty, so
`structure_engine.pine`, `structure_engine_export.pine` and `engines/market_structure/engine.py` are
all still in lockstep and need nothing.

### 🔴 `engines/order_blocks/` — STALE. An order block is a DIFFERENT OBJECT now, not a tweaked one.

This is a re-port, not a re-sync. Nothing about the old definition survives:

- **Structure breaks no longer create blocks at all.** `f_obMake` and `f_obCandle` are gone
  (commented out), and so are all four creation sites — external bull/bear AND internal bull/bear.
  The old rule (on a BOS/SOS, scan the break leg for the last opposing *engulfing* candle) is dead.
  The `mergeOBs` overlap-absorb and the SOS wipe went with them.
- **Two new sources, both anchored on a `ta.pivotlow/pivothigh(2, 2)` TURN.** (a) **PUSH** — an
  impulsive engulfing candle read `OB_PUSH_WAIT = 10` bars late: its body must beat the body it
  consumed *and* clear an `ATR(14) × 0.3` noise floor, the consumed candle must clear that floor too
  (a doji cannot be a level), it is found by scanning back up to `OB_PUSH_LOOK = 5` bars, and the
  anchor must sit at or within `OB_TURN_SCAN = 8` bars *after* a matching-direction pivot.
  (b) **TURN** — every such pivot, anchored on the last opposing candle located by a running-body
  scan. One block per turn: the push reading claims it via the `obTurnUsedL/S` latch.
- **New `f_obAdd` gates:** a departure test (price must have closed `OB_DISP_MULT = 1.0 × ATR(14)`
  away — "a block is made AFTER price has gone"), a dead test, a tapped test, a `OB_DUPE_OVERLAP = 0.5`
  overlap dedupe against live blocks, a height ceiling `OB_MAX_ATR = 2.0 × ATR(14)`, and a birth-time
  catch-up replay that carries the `entered` flag forward.
- **Mitigation redefined end to end.** A wick that reaches in and closes back OUT now kills the block
  (the tap rule); a close INSIDE keeps it alive until a later close outside *either* side; a close
  clean past the far edge kills it outright. Plus `OB_MAX_AGE = 500` bars.
- **`maxActiveOB` 2 → 10**, and eviction is now plain oldest-out — it no longer protects
  structure-born blocks. New `OrderBlock` fields `fromBreak` and `entered`.
- Box geometry: `OB_STUB = 30` bars as a FLOOR, growing only when price returns within one
  block-height. Appearance (one orange outline, `OB_SCAN_MAX = 40`) is visual.

**Engine STALE, harness `indicators/engines/ob_export.pine` STALE (last touched 2026-07-14). Re-run
`compare_ob.py`.** Note the old engine's `maxActiveOB` sync-to-2 note from 2026-07-14 is now moot.

**RE-PORTED 2026-07-31 — engine, types, `__init__`, 19 unit tests, harness and compare tool all
rewritten.** `engines/order_blocks/` now implements the turn-anchored definition end to end. Three
things made this the safest of the stale items to do immediately: **nothing consumes it** (not
`EngineStack`, not either bot), **there is no two-Pine fork** (the strategy files dropped order
blocks entirely on 2026-07-24/25, so `mpc_assistant.pine` is the only source), and the engine
**became STANDALONE** — `StructureSnapshot` is deleted and `update()` takes plain OHLC, so it no
longer depends on `engines/market_structure/` at all. `indicators/engines/ob_export.pine` shrank 1148 → ~300
lines because it no longer has to EMBED the structure engine, which removes its single biggest
maintenance trap (it silently went stale twice), and it now carries `cfg_ob_*` columns that
`compare_ob.py` configures the Python engine from. ⚠ **NOT Pine-parity-validated yet** — the compare
tool round-trips clean on a synthetic export and correctly localises a planted mismatch, which
proves the harness plumbing and nothing about parity (a round trip shows the two halves agree, never
that either is right — the 2026-07-26 B-LEG harness bug is the precedent). Full detail and the exact
gate: `engines/order_blocks/CLAUDE.md`.

### 🔴 `engines/sessions/` — STALE. All three session windows changed.

| | old (48c183f) | new (HEAD) |
|---|---|---|
| Tokyo  | `2000-0500` **GMT-4** | `0900-1800` **Asia/Tokyo** |
| London | `0400-1300` **GMT-4** | `0800-1700` **Europe/London** |
| New York | `0900-1800` **GMT-4** | `0800-1700` **America/New_York** |

Same change in `SVP_SESSION`/`SVP_TZ` (`2000-0500`/`GMT-4` → `0900-1800`/`Asia/Tokyo`).

**Worked through in UTC, because two of the three are NOT equivalent:**
- **Tokyo is identical year-round** — both forms are 00:00–09:00 UTC (GMT-4 is a fixed offset and
  Asia/Tokyo has no DST). This is a pure re-expression.
- **London and New York are identical only in northern-hemisphere WINTER.** The old windows were
  pinned to a *fixed* GMT-4, the new ones follow real DST. Under BST/EDT both shift **one hour
  earlier**: London 08:00–17:00 → 07:00–16:00 UTC, New York 13:00–22:00 → 12:00–21:00 UTC. That is
  roughly seven months of every year, so this moves real session boundaries.

**Kill zones and the NY opening range are UNCHANGED** — still `America/New_York`, `inKZ1 = nyHour == 10`,
`inKZ2` 11:45–12:14, `inKZ3` 13:00–13:30, `inSession5 = time("5","0930-0935")`, `inExtend5 0935-1600`.
So only the three session windows moved.

**Cascade:**
- 🔴 **`engines/liquidity/` is STALE-BY-INPUT** — its own code is fine, but it composes the session
  windows for the Asia/London/NY session high/low levels, and two of those windows moved. Harness
  `indicators/engines/liquidity_export.pine` (2026-07-09) stale.
- ✅ **`engines/session_volume_profile/` is UNAFFECTED** — it composes the **Asia** window only, and
  Asia is value-identical. Re-confirm on the next export rather than changing code.
- Harness `indicators/engines/sessions_export.pine` (2026-07-04) stale.

### 🔴 `engines/fibonacci/` MacroFib (Cycle Fib) — STALE. The anchor moved and it now reads a second timeframe.

- **The origin changed.** It was `macro_ll_since_bear_sos` — the lowest low tracked since the last
  bearish SOS. It is now **`st.bull_bos_low` / `mtf.bull_bos_low`**, the break leg's own low. A
  different bottom anchor means *every* Cycle fib level prices differently. The Python `MacroFib`
  still implements the old bottom-tracking (`engines/fibonacci/engine.py`, `_last_bear_sos_bar` /
  `bottom_anchor`).
- **New `macroCycleTf = 1` + `f_cycleState()`.** On any chart ABOVE 1m the entire cycle state
  (`cyc_origin` / `cyc_extreme` / `cyc_visible`) now comes from a `request.security` at **1 minute**;
  at or below 1m it runs natively (`ncyc_*`). ⚠ **This is not a one-line sync** — the Python engine
  consumes one bar stream and has no lower-timeframe feed, so reproducing it needs a design decision
  first (feed the engine a 1m stream, or pin `macroCycleTf` to the chart timeframe for parity runs).
- **Touch-latch reset moved** from `macroNewHH` (a rising `last_conf_high`) to `macroRangeChanged`
  (`macro_extreme != macro_prev_extreme`), and the old `macroExtChanged` suppression guard is gone.

**StructureFib, SniperFib and InternalFib are unaffected** — no change to their compute or touch
machines. Harness `indicators/engines/fib_export.pine` (2026-07-12) is stale for the macro columns.

**RESOLVED 2026-07-31 — Aaron's call: LEAVE the engine as it is, and document the fork.** The
decisive fact, found while scoping the port: **`indicators/strategies/mpc_strategy.pine` still carries the OLD
anchor** (`macro_ll_since_bear_sos`, lines 2614-2672). That is the file
`strategies/python/mpc_sos_fade/` replays, so `MacroFib` is stale against the *assistant* but
**correct against the strategy** — porting the rework would have manufactured drift in the bot
instead of removing it. Same shape as the `fvg_require_close` trap: the two mpc Pine files disagree,
so no single behaviour is right for both. Low stakes today either way — `mpc_sos_fade` computes the
macro POI and reports it through the sequence state, but **execution never reads it**, so no trade
depends on it. **Port it when the rework reaches `mpc_strategy.pine`, not before** — and note the
1-minute `request.security` is the real work at that point, not the anchor line.

### Default drift — not parity breaks, but sync them

- **`fvgMaxCount` 10 → 8.** FVG *detection* is byte-identical (formula, both thresholds `0.0`/`0.04`,
  `fvgRequireClose = false`), so `engines/fair_value_gaps/` is in parity — but its Python default is
  10. `compare_fvg.py` configures the engine from the export's `cfg_fvg_*` columns, so a parity run
  still passes; sync the default anyway.
- **Every remaining engine input was FROZEN into a constant at its existing value** — `eqPivotLen` 2,
  `eqAtrMult` 0.1, `eqMax` 6, `eqExemptFvg` true, `divRsiLen` 14, `divPivotLen` 5, `divOS` 25,
  `divOB` 75, `divMaxCount` 10, `svpHistory` 2, `i_lineExtend` 50, `i_lblOffset` 300,
  `macroMaxTfMin` 30, `vwapWidth` 1. **No value changed** — this is the student-panel lockdown
  (121 inputs → 24), panel-only.

### Detection is now ALWAYS-ON — worth knowing before the next export

`showFVG`, `showDiv`, `showFibo` and `i_showLiquidity` are hardcoded `true`, with new `drawFVG` /
`drawDiv` / `drawFibo` / `drawSniper` / `drawLiq` flags gating **drawing only**. `showSniperFib` was
dropped from `_snBullBOS`/`_snBearBOS` entirely, so the Sniper Zone always tracks. This moves the Pine
*toward* the engines (which always compute and never draw), so it is not staleness — but the
`*_export.pine` harnesses still gate their compute off the OLD flags, which is one more reason they
need re-syncing alongside the engines above.

### IN PARITY (detection unchanged this window)

`engines/market_structure/` ✅ · `engines/equal_highs_lows/` ✅ (label size → `f_liqSize()` and an
`x1` clamp to `LIQ_ORIGIN_CAP` — both drawing) · `engines/rsi_divergence/` ✅ (colours moved into
`DIV_BULL_COL`/`DIV_BEAR_COL` constants; the intraday-inert 3-day-history bug is untouched) ·
`engines/vwap/` ✅ (`ta.vwap(hlc3)` untouched) · `engines/session_volume_profile/` ✅ ·
`engines/fair_value_gaps/` ✅ detection · `engines/fibonacci/` Structure/Sniper/Internal ✅ ·
`engines/regime/` and `engines/news/` — not sourced from this Pine, unaffected.

**Liquidity, beyond the session cascade: all DRAWING.** The `LIQ_ORIGIN_CAP = 1500` x1 clamp, hiding a
mitigated line once its break bar ages past that buffer, the dimmed (rather than hidden) mitigated
label, and `drawLiq` colour gating all sit inside `f_liqMitigate`'s draw branch — the `breachCond →
newMit` mitigation test itself is untouched. The new `liq_dh_t`/`liq_dl_t` timestamps exist only for
the A+ daily-sweep age check (strategy-tier), replacing a `time[bar_index - bar]` read that could
reach past the historical buffer.

### Two new blocks — both STRATEGY-tier, neither needs an engine

1. **B-LEG tracker + "BLEG SZ" box** (`bLegL_*`/`bLegS_*`, `bLegArmL/S`, band = 0.382–0.5 of the SOS
   leg, invalidation at the leg origin, `BLEG_MAX = 120` bars, drawn on 15m only, plus a B LEG row in
   the JARVIS table). New to `mpc_assistant.pine`, but this setup is **already built** as
   `indicators/strategies/mpc_b_leg_strategy.pine` and `strategies/python/mpc_bleg/`. ⚠ **Worth a drift check:**
   the assistant's copy was written independently of the fork, so the two may not agree on band edges
   or invalidation.
2. **A+ REV SETUP rework** — per-source arm timestamps with SEPARATE expiry windows
   (`aplusSweepWindow = 1440` for sweeps vs `aplusWindow = 4320` for divergences), `aplusDivOnly`
   default **true → false**, the `aplusL_scaled` latch replaced by a deep-level re-entry ladder
   (`aplusL_deepSeen` / `aplusL_reentry`), a new `inTrade` latch, `aplusL_fvgZone`/`aplusL_szTap`
   confluence flags, a LEVELS table row with entry/SL/TP prices, and a five-tier `alert()` set. The
   15m `f_rev15` sequence got the same deep ladder plus a BOS-after-SOS kill.

**No new un-extracted ENGINE-tier block appeared.**

---

### What was FIXED on 2026-07-31 (the audit above was report-only; these landed after it)

| item | action | state |
|---|---|---|
| `engines/fair_value_gaps/` | `max_count` default 10 → 8 (detection untouched) | ✅ done, 17 tests green |
| `engines/sessions/` | three windows re-synced to their own cities' DST-aware clocks | ✅ done, 18 tests green |
| `indicators/engines/sessions_export.pine`, `indicators/engines/liquidity_export.pine` | old hardcoded windows re-synced | ✅ done |
| `engines/liquidity/` | no code change needed — it inherits `SessionEngine()`'s defaults | ✅ done |
| `engines/session_volume_profile/` | confirmed UNAFFECTED; Asia equivalence now pinned by a test | ✅ done |
| `engines/fibonacci/` MacroFib | **deliberately NOT changed** — see the RESOLVED note above | ✅ decided |
| `engines/order_blocks/` | full re-port + rebuilt harness + rebuilt compare tool | ✅ code done |

529 tests green across `engines/`, `backtest/tests/` and both bots.

✅ **ALL FOUR PINE-PARITY-VALIDATED 2026-07-31** on ONE grand `VANTAGE_XAUUSD, 15m` export carrying all
four harnesses at once — **21,691 bars, 2025-09-01 → 2026-07-31, 146 columns, no column-name
collisions between the four files.** The window spans **four DST changeovers** (UK Oct-2025 /
Mar-2026, US Nov-2025 / Mar-2026), which is what makes it a real test of the session re-sync rather
than a re-run of the same offset.

| check | result | warm-up | note |
|---|---|---|---|
| `compare_fvg.py` | **exit 0** | **0** | all 10 slots; `cfg_fvg_thresh` read back as **0.04**, i.e. the new timeframe split fired correctly on 15m |
| `compare_sessions.py --skip-nyr` | **exit 0** | **1** | 14 fields. The single bar-0 miss was `px_new_day`, which is undefined on the first bar for both sides (`time[1]` does not exist) |
| `compare_liquidity.py --htf-rollover 18` | **exit 0** | **449** | 28 fields. Warm-up is all `None` vs `0.0` on the `_mit` flags — Python has no level yet where Pine's `var bool` initialised false |
| `compare_ob.py` | **exit 0** | **798** | 55 columns, config read from `cfg_ob_*`. See the warm-up finding below |

All four hold at every higher warm-up tested (sessions 500–5000, liquidity 1000–5000, OB 1000–10000),
so none of them is a threshold that happens to land just past a real mismatch.

**A Pine bug was found and fixed getting here.** `ob_export.pine` would not compile: `CE10088 — cannot
modify global variable in function`. Pine lets a function READ a global but never WRITE one, and the
export-only counters were being incremented inside `extendOBs` AND inside `f_obAdd`. `extendOBs` now
RETURNS its mitigation count and the creation counters are bumped at `f_obAdd`'s call sites off its
existing bool return. The counters do not exist in mpc at all, so no ported logic moved. The other
three harnesses were checked for the same class of error and are clean.

**Two holes in `fvg_export.pine` closed in the same pass, both of which would have produced a
misleading green.** (1) It plotted **6 slots against a cap of 8**, so the two newest gaps were live in
Pine and invisible to the diff — every earlier FVG "exit 0" covered the oldest six only. Now 10 slots,
and `compare_fvg.py` REFUSES an export whose `cfg_fvg_maxcount` exceeds the plotted slots. (2) Its
minimum-gap floor was one flat number, but mpc's is timeframe-split (`0.0` below 900s, `0.04` at 15m+,
`mpc_assistant.pine:410-412`). On this 15m export the old build would still have gone green — both
sides read the setting from `cfg_fvg_thresh` — while running a DIFFERENT rule from the indicator it
mirrors, and proving nothing about the 15m gap set `mpc_strategy.pine` actually trades.

### Second export — 5m, and the NY opening range is now covered too

A **second grand export** (same four harnesses, `VANTAGE_XAUUSD, 5m`, **13,186 bars,
2026-05-27 → 2026-07-31**) closed the one gap the 15m run could not reach, and re-ran the other three
on a different timeframe and different data as a bonus. **All four exit 0 again**, each stable at
every higher warm-up tested:

| check | result | warm-up | note |
|---|---|---|---|
| `compare_sessions.py` (**no `--skip-nyr`**) | **exit 0** | 220 | **all 18 fields**, NY opening range included — the last uncovered piece of the engine |
| `compare_fvg.py` | **exit 0** | 4990 | `cfg_fvg_thresh` read back as **0.0**, i.e. the timeframe split fired the OTHER way on 5m |
| `compare_liquidity.py --htf-rollover 18` | **exit 0** | 862 | prev-week levels are the long pole |
| `compare_ob.py` | **exit 0** | 326 | see below — this number is the interesting one |

**Every warm-up here is pre-window carry-in, and this export makes that unambiguous:** unlike the 15m
file, it is a mid-history SLICE, so Pine opens already holding state Python cannot know. The clearest
case is FVG — **`px_fvg_formed` never mismatches on a single bar**, so both sides agree on every gap
FORMATION from bar 0; the slot columns differ only because Pine carries in gaps like one at 4733.88
while price is trading ~4520, which can never close past its far edge and so sits in Pine's array for
ever. That is precisely the 2026-07-19 EQ/FVG ghost trap, observed rather than theorised.

**The 5m order-block run independently confirms the ~300-bar warm-up finding.** Pine is WARM here and
Python is the cold one, which is the same configuration as the cold-start-at-2000/6000/12000 test —
and it needed only **326** bars, versus 798 on the 15m file where Pine was cold too. Same number, same
direction, arrived at from different data. The "budget ~300 bars, and expect a cold engine to MISS a
block rather than invent one" guidance stands.

**Coverage is now two timeframes for all four engines:** 15m proves the DST window behaviour across
four changeovers; 5m proves the ≤5m NY opening range and re-proves the rest on independent data.

### 🔴 Found while confirming sync: the B-LEG Pine fork never got the session windows

`mpc_strategy.pine` has carried the NEW windows since **2026-07-12** (`317dbef`) — two weeks BEFORE
`mpc_assistant.pine` got them (`b25789d`, 07-26). But **`mpc_b_leg_strategy.pine` and
`mpc_b_leg_strategy_export.pine` are still on the old fixed `GMT-4` strings**, so the A+ and B-LEG
forks now disagree about when a session opens. That breaks the standing rule in
`indicators/CLAUDE.md`: any engine-block change in the parent flows to the fork line-for-line.

**It is trade-affecting in principle, not cosmetic.** Session H/L feed `recentBSL`/`recentSSL`
(`mpc_strategy.pine:3121-3126`), which is what `execArmSweep` arms A+ on — and `execArmSweep` is ON
by default in the shipped "prime" combo. The path is narrow because `showSessH = liq_dh == ""` makes
session levels a FALLBACK used only when no day level exists, but narrow is not none.

**Measured, not assumed: neither bot moves.** After `SessionEngine`'s defaults changed,
`compare_strategy.py --warmup 100` and `compare_bleg.py --warmup 100` both still exit 0 on their
existing 2026-07-29 exports. So the window change does not alter either decision stream over those
windows, and no backtest number is invalidated. Worth knowing WHY that is reassuring rather than
conclusive: the A+ Python bot consumes these windows for real (`EngineStack` builds `SessionEngine()`
with no args, and `mpc_sos_fade/sequence.py` reads `recent_ssl`/`recent_bsl`), so it was silently
running OLD windows against a Pine on NEW ones from 07-12 until this pass. The green says the
fallback path did not fire differently on that data — not that it never can.

**✅ FIXED the same day — all five files synced.** `mpc_b_leg_strategy.pine`,
`mpc_b_leg_strategy_export.pine` and `mpc_m15_playbook.pine` now carry
Tokyo `0900-1800` Asia/Tokyo · London `0800-1700` Europe/London · New York `0800-1700`
America/New_York, matching `mpc_assistant.pine:464-478` and `mpc_strategy.pine:185-200`. Each file's
own `display = display.none` was preserved — only the six values changed per file. `svp_export.pine`
was re-stated too, purely for consistency: `"2000-0500" GMT-4` and `"0900-1800" Asia/Tokyo` are the
same 00:00-09:00 UTC window year-round, which is the same equivalence that left
`engines/session_volume_profile/` unaffected.

⚠ **`mpc_m15_playbook.pine`'s NY window was `0900-1700`, not the `0900-1800` every other file had** —
a pre-existing difference of unknown origin, now folded into the common `0800-1700` America/New_York.
It is not a bot and nothing replays it, but if that shorter window was deliberate, this changed it.
⚠ **That file was DELETED on 2026-08-15** (Aaron's call), so this open question closes unanswered
rather than resolved. Its `strategy()` half survives as
`indicators/strategies/smc_session_sweep_strategy.pine` and carries its own session block.

**Done as a line-targeted edit, not a string replace, on purpose:** in these files the OLD Tokyo
value (`"2000-0500"`) and the OLD New York value (`"0900-1800"`) collide with the NEW Tokyo value, so
a naive global substitution would have rewritten Tokyo and then immediately overwritten it again when
the New York rule ran. Anchoring each edit on its `*_SESSION_GROUP` is what makes it safe.

**Both bots re-verified after the change:** `compare_strategy.py --warmup 100` and
`compare_bleg.py --warmup 100` still exit 0, and 529 tests stay green.

### 🔴 Also found and fixed: `mpc_sos_fade` was relying on an unpinned engine default

The roadmap previously called `backtest/replay/stack.py`'s `EngineConfig` FVG values "two generations
stale, harmless because every real consumer pins". **Half of that was wrong.** `mpc_sos_fade` pins
`fvg_max_count` and `fvg_require_close` — and **not** `fvg_threshold_pct`. It was silently inheriting
`stack.py`'s `0.1`, which happens to be `mpc_strategy.pine`'s 15m floor, so the bot worked by
coincidence rather than by decision. Proven by removing it: `compare_strategy.py` failed on the very
first compared bar (`px_edge` py=3478.99 vs pine=3475.43). Anyone "tidying" that default to match the
engine would have moved the A+ bot's trades with no test failing.

Fixed the right way round — shared infra carries ENGINE defaults, each bot pins what it trades:

| | was | now |
|---|---|---|
| `stack.py` `fvg_max_count` | 6 | **8** (engine / `mpc_assistant.pine`) |
| `stack.py` `fvg_threshold_pct` | 0.1 | **0.0** (engine, the sub-15m floor) |
| `mpc_sos_fade.engine_config()` | 3 pins | **4 pins** — `fvg_threshold_pct=0.1` added explicitly |

`test_engine_config_pins_every_input_the_pine_moved_off_its_default` now asserts all four, so the
shared default is free to move again without silently dragging the bot with it. This is the same
class of bug as the 2026-07-26 `fvg_require_close` miss, and the rule in `backtest/CLAUDE.md` →
*Rules* already names it: **an engine input the decision stream does not export is a silent parity
trap.** The lesson to add is that it applies to an input a bot forgot to pin, not only to one whose
default changed.

### The order-block warm-up — investigated, not assumed

798 bars is long, so it was chased rather than accepted. Findings:

- The export starts at Pine's **bar_index 0** (zero blocks held at row 0), so the warm-up is NOT
  ghost blocks carried in from before the window — the usual explanation does not apply here.
- Over bars 0–324 Python creates a strict **superset**: 20 blocks Pine never made, and **zero** that
  Pine made and Python missed. Pine creates nothing at all until bar 122.
- It is not the displacement gate going marginal: those 20 clear it at **travel/ATR of 1.06–6.71**,
  and none is near the ×1.0 threshold. It is not the ATR seed, and not `obHuge`.
- **The decisive test — cold-start the Python engine at bars 2000 / 6000 / 12000 instead.** Every one
  gives the OPPOSITE signature: Python *misses* 1–3 blocks inside its first 300 bars (Pine is warm
  there and Python is not), then matches exactly. The over-firing appears ONLY at bar 0, i.e. only
  where **Pine itself is also cold**.

So Pine suppresses creation during the oldest bars of a chart in a way this port does not. The exact
mechanism could not be pinned down from this export because it plots no intermediate values
(`obTurnHi`, `obTravel`, the pivot series), and it never recurs in the following 20,893 bars.
**Practical consequence: budget ~300 bars of warm-up before trusting order-block output, and expect a
cold consumer to be missing a block or two inside that window rather than inventing one.** Adding
`px_ob_pv_hi` / `px_ob_pv_lo` / `px_ob_travel` diagnostic columns to the harness would settle it and
is the cheap follow-up if it ever matters.

**Both follow-ups flagged here were CLOSED the same day** — see the two sections above.
`backtest/replay/stack.py`'s `EngineConfig` was reconciled (and the "harmless, every real consumer
pins its own" claim turned out to be half wrong — `mpc_sos_fade` never pinned `fvg_threshold_pct`).
The stale session windows were synced in every remaining file, and `mpc_jarvis_v2.pine`
was DELETED rather than synced (2026-07-31, Aaron's call — superseded by
`indicators/strategies/mpc_strategy_export.pine`; last committed at `825592a`).

---

## 2026-07-19 — grand-export parity GREEN; real EQ/RSI pivot-tie bug found + fixed ✅

Aaron exported ONE grand CSV with all 10 engine export indicators + the strategy on a single 5m
XAUUSD chart, to prove every engine matches mpc exactly in one shot (`verify_parity.py` runs all 11
checks off the one file). Two rounds:

1. **First export (9,469 bars) — surfaced the "pre-window ghost" limit.** structure/OB/fib/liquidity/
   sessions/vwap/svp green; FVG/EQ red. Root cause was NOT a bug: the window's highest bar was 4541 but
   Pine held EQH levels + an FVG up at 4733 — created by a spike BEFORE bar 0 that never mitigates
   (price never returns), so the cold-started Python engine can't reproduce or shed them. Every
   in-window level matched. Fix = a wider re-export.

2. **Wider export (16,639 bars, high 4773) — cleared the ghosts AND exposed a REAL bug.** FVG went
   green. EQ stayed red with in-window pivot misses: **Pine's `ta.pivothigh`/`pivotlow` are NOT
   symmetric-strict** — the centre may EQUAL a bar to its LEFT but must be STRICTLY beyond every bar to
   its RIGHT (the last bar of an equal-price run is the pivot). The EQ engine used strict-both-sides and
   dropped the frequent raw-price ties on gold. Fixed (`_pivot_high`/`_pivot_low`). **The `rsi_divergence`
   engine had the identical latent bug** (same pivot code; ties on RSI values are just rare, so it only
   ever showed as a couple of diagnostic-column misses the notes had written off as "float-ties"). Same
   fix applied there.

**Result — ALL 10 ENGINES GREEN (exit 0)** on the grand export: EQ `--warmup 3500`, RSI `--warmup 2000`,
FVG `--warmup 250`, plus structure/OB/fib/liquidity/sessions/vwap/svp. 7 EQ + 9 RSI + 17 FVG unit tests
green. EQ / FVG / RSI are now the canonical validated implementations (committed 2026-07-19). The
**strategy (bot)** check is still red — not a mismatch: the tool detected the export omitted ~3,863 of
the chart's oldest bars (TradingView wasn't scrolled fully left), and the strategy needs the true first
bar (engines tolerate the cold-start, the A+ sequence state does not). A full-left re-export closes it.

**Lesson:** a persistent-level engine (EQ/FVG) can't be parity-checked on a window whose price never
revisits the pre-window extreme — the ghost levels never mitigate. And a narrow window can HIDE a real
pivot bug; the wider export is what made the tie failures visible.

---

## 2026-07-18 — EQ engine built + FVG `requireClose` drift fixed + defaults reconciled

Triggered by Aaron: "make every mpc input an engine, and bring the Python defaults in line with the
Pine." Two things landed (NOT yet committed; EQ + FVG Pine-parity re-runs PENDING a fresh export):

1. **`engines/equal_highs_lows/` BUILT** — the last mpc feature block with no engine. Standalone
   EQH/EQL detector (ATR(50) tolerance + strict len-2 price pivots + `max`/`min` level + FIFO cap +
   close-through mitigation), ported line-by-line from the mpc EQ block. 7 unit tests green. Harness
   `indicators/engines/eq_export.pine` + `engines/equal_highs_lows/tools/compare_eq.py` built and
   self-consistency-checked; wired into `verify_parity.py` (marker `px_eq_tol`). Full detail in
   `engines/equal_highs_lows/CLAUDE.md`.

2. **`engines/fair_value_gaps/` REAL DRIFT FIXED.** The `fvgRequireClose` gate
   `(not fvgRequireClose or close[1] > high[2])` landed in `mpc_assistant.pine` on **2026-07-17**
   (commit `a0b8e1d`, "Implement feature X…"), AFTER the last FVG validation (07-14). So the Python
   engine AND `fvg_export.pine` had silently gone stale: both HARDCODED the middle-bar close check,
   while the mpc DEFAULT (`fvgRequireClose = false`) SKIPS it — i.e. on a default mpc chart the engine
   was rejecting gaps mpc keeps. This is why a single-commit `/audit-engines` (which diffs only the
   latest commit) missed it. **Fix:** the close check is now the OPTIONAL `require_close` engine flag
   (default False = mpc default); defaults reconciled `max_count` 6→10 and `threshold_pct` 0.1→0.0
   (the sub-15m value; 15m+ passes 0.04). `fvg_export.pine` now carries `cfg_fvg_*` columns and
   `compare_fvg.py` configures the engine FROM the export (Aaron's "let the file carry the settings"
   call) — parity now survives any Pine input tweak. 15 unit tests green.

**RESOLVED — the FVG↔EQ coupling (`eqExemptFvg`, default ON) is now WIRED (Aaron's exact-match call):**
mpc's FVG cap eviction skips a gap sitting behind an active EQ level (it persists until mitigated).
Modelled via the public-output pattern (NOT by FVG reaching into EQ): `FairValueGapEngine.update()`
takes `eq_levels` + `eq_tol`, and the CONSUMER runs EQ→FVG (the Pine order) and passes EQ's active
levels + tolerance. `fvg_export.pine` now EMBEDS the EQ compute + `f_fvgNearEq` + the exempt-eviction
(byte-for-byte mpc) and carries `cfg_eq_*` columns; `compare_fvg.py` runs the Python EQ engine from
those cfg columns and feeds the FVG cap — so the coupling is validated against mpc, not just asserted.
2 new FVG unit tests pin the exemption (and that no-EQ stays plain FIFO). **Follow-up:**
`backtest/replay/EngineStack` does not yet wire EQ→FVG (exemption off there); the mpc_sos_fade strategy
parity is unaffected while it stays off.

**Lesson:** a single-commit audit can miss a drift that entered in an earlier, vaguely-messaged commit.
When proving parity, run `verify_parity.py` on a fresh export — the machine catches what the eyeball
diff of one commit does not.

---

## Re-sync applied — 2026-07-12 (chain 2→3→4 brought back in line) ✅ PARITY CONFIRMED

Aaron's call: **accept `mpc_assistant.pine` as source of truth and port it as written**, `choch_lock`
removal included, risk accepted. The audit below stands as the record of *what* changed; this section
records *what was done about it*.

**Root cause, confirmed against Aaron's chart (XAUUSD 15m, 17 Jun 2026, the ~4382 spike).** Both of the
symptoms his brother reported are ONE bug, not two. A bullish SOS set `choch_lock`. The very next
bearish break — the reversal off that spike — was therefore *not* treated as a CHoCH and rendered as a
**BOS instead of an SOS**. And because the bear-break fallback classifies the old high with
`old_is_hh = is_choch ? true : (st.ash >= st.last_conf_high)`, losing the CHoCH also lost the forced
`true` — so the **HH never printed**. Removing `choch_lock` fixes the break label and the missing HH in
one move. It was the fix, not a side effect. The `if not is_choch` gating of the confirmed-swing map is
the matching half: on a fast reversal the promoted extreme is only ACTIVE (ASH/ASL), and a later,
lower high can no longer overwrite a genuine higher high.

**Applied — the same four changes, byte-identical, in every Pine copy of the structure engine:**
`mpc_assistant.pine` (source), `structure_engine.pine`, `structure_engine_export.pine`,
`ob_export.pine`, `fib_export.pine`, `mpc_strategy.pine`. Verified: `diff` of mpc's structure block
(402–909) against `structure_engine.pine` (57–564) is now **empty — byte-for-byte identical**.
`choch_lock` remains declared/set/released but unread in all six, exactly as mpc leaves it; the dead
code is kept deliberately so the files stay identical to source.

**Ported to Python:** `engines/market_structure/engine.py` (`_on_ash_broken` / `_on_asl_broken` — both
`is_choch` lines, both label ternaries, both confirmed-map guards). `types.py`: the
`broken_high_label` / `broken_low_label` domain is widened to `"HH"|"LH"|"ASH"` and `"HL"|"LL"|"ASL"` —
consumers keying off the confirmed labels must read ASH/ASL as *"not yet classified"*. No production
consumer reads those fields today (grep-verified: tests only). `algos/shared/structure_engine.py` is a
pure pass-through and needed no edit.

**Tests:** 64/64 green (market_structure 10, fibonacci 40, order_blocks 12+). One structure test
(`test_bear_sos_choch_fires_on_bar_8`) legitimately hand-encoded the OLD behaviour and was updated: the
break-promoted high now asserts `broken_high_label == "ASH"`, plus a new regression assertion that
`last_confirmed_high` stays at the genuine 10.3@4 rather than being overwritten by the 10.6@7 promotion —
that overwrite is precisely the bug that suppressed the HH.

**✅ PINE PARITY RE-CONFIRMED — all three green, one export.** `ob_export.pine` + `fib_export.pine`
were put on a single `VANTAGE_XAUUSD, 5m` chart and exported as ONE CSV
(`engines/market_structure/exports/VANTAGE_XAUUSD, 5_9c376.csv`, 9270 bars). `structure_engine_export.pine`
was **not needed on the chart**: `ob_export.pine` already carries all 23 of its `px_*` columns
(strict superset), and `fib_export.pine` collides with neither. All three compare tools resolve columns
by NAME (`csv.DictReader` + `_resolve_columns`) and ignore extras, so one file drives all three.
`engines/fibonacci/` and `engines/order_blocks/` were **STALE-BY-INPUT** (own code correct, structure
stream changed) — both re-validated unchanged.

| Compare tool | Warm-up | Result |
|---|---|---|
| `engines/market_structure/tools/compare_tradingview.py` | `--warmup 365` | ✅ exit 0 |
| `engines/order_blocks/tools/compare_ob.py` | `--warmup 548` | ✅ exit 0 |
| `engines/fibonacci/tools/compare_fib.py` | `--warmup 368` | ✅ exit 0 |

Every mismatch was a **contiguous block at bar 0** — the export starts mid-stream, so Pine holds swing
state at row 0 that Python must rebuild; each engine re-synced at its warm-up bar and never drifted
again across the remaining ~8.7–8.9k bars. (Warm-up differs per engine because each needs a different
depth of history: OBs need enough breaks to fill the 6-deep FIFO, the fibs need one full cycle.)
The single-CSV multi-indicator trick is the same one used for the 2026-07-09 liquidity+fib run.

---

## Audit findings — 2026-07-14 (8 commits since the `choch_lock` re-sync; clean tree, diff `8f6b5ca..HEAD`) 🔴 FVG STALE

Working tree clean. Audited the cumulative diff of `indicators/engines/mpc_assistant.pine` from `8f6b5ca` (the
last full engine audit + re-sync) to `HEAD` (`f9c947c`): **477 lines, 330+/147-** across 8 commits
(`2cc1ac7` retro-link, `62fc274` div-only/ignore-window, `35437f0`+`2a172c2`+`ceff9ff` FVG, `bc6014e`
liquidity pool-refresh, `f139cc6` input defaults, `f9c947c` REV SETUP alert). **One engine is STALE
(FVG), one needs a confirmatory re-run (liquidity), one has a benign default drift (order_blocks); the
market_structure sync chain is NOT triggered.**

### fair_value_gaps — 🔴 STALE (detection + lifecycle both redefined)

Three real logic changes, all mirrored bull/bear:

1. **Detection rule replaced.** Old: a "clean impulse" — `close>open and close[1]>open[1] and
   close[2]>open[2] and close>close[1] and close[1]>close[2]` gating `low > high[2]`. New: the **LuxAlgo
   imbalance** — `bullFvg = low > high[2] and close[1] > high[2] and (low - high[2]) / high[2] * 100 >
   fvgThreshold` (bear mirror). The three-bar body/colour/progressive-close rule is **gone**; any 3 bars
   that leave a big-enough non-overlapping gap with the middle bar closing past it now qualify.
2. **Size floor changed.** Old: `fvgMinTicks` input (default 0) → `fvgMinSize = fvgMinTicks *
   syminfo.mintick`, an absolute tick filter. New: a **hardcoded 0.1%-of-price** floor (`fvgThreshPct =
   0.1`, compared as `(gap / price) * 100 > 0.1`). Not user-tunable any more, and percentage- not
   tick-based. `fvgMaxCount` default also **3 → 6**.
3. **Mitigation/lifecycle flipped.** Old: `tapped = bar_index > born and (isBull ? low <= gTop : high >=
   gBot)` — a gap died the moment price **tapped its near edge**. New: `closedPast = barstate.isconfirmed
   and bar_index > born and (isBull ? close <= gBot : close >= gTop)` — a gap dies only when a candle
   **CLOSES fully past its far edge**; a wick into the gap now leaves it alive.

`engines/fair_value_gaps/engine.py` still implements the OLD clean-impulse detection (`bull_impulse`/
`bear_impulse`, `>= min_size` tick floor) and OLD tap-near-edge mitigation (grep-confirmed). **STALE:**
`engines/fair_value_gaps/engine.py` + its harness `indicators/engines/fvg_export.pine` — re-sync both, then re-run
`engines/fair_value_gaps/tools/compare_fvg.py` to exit 0 on a fresh export before committing. (Note the
`__init__` defaults `max_count=3, min_ticks=0` and the CLAUDE.md/docstring text will need updating too.)

### liquidity — ⚠️ RESTRUCTURED, but value-identical on intraday → confirmatory re-run only

The daily/weekly/session liquidity block was reworked (`bc6014e` + `f139cc6`), but on the timeframes the
engine runs and is validated at (5m/15m) the emitted facts look unchanged:

- **HTF fetch refactor.** `pdh/pdl` and `pwh/pwl` now branch on chart type (`_pdDayChart`/`_pwWkChart`).
  On intraday both resolve to the `lookahead_on` `high[1]/low[1]` security = the **previous completed
  period** — the same value the old `dailyHigh[1]`/`weeklyHigh[1]` gave. Value-identical intraday; the new
  branch only bites on Daily+/Weekly+ charts.
- **`f_originHigh`/`f_originLow`.** New back-scan that starts each drawn line at the candle that first
  reached the level, instead of the detection bar. Pure **line-origin (x1) visual** — the engine emits
  level price + mitigation, not the drawing's start bar.
- **`showMitLiq` + `f_liqMitigate(..., showMit)`.** New toggle (default false) to keep broken levels on
  the chart as dotted lines. The mitigation **DETECTION** (`if not newMit and breachCond: newMit := true;
  newMitBar := bar_index`) is byte-unchanged — only whether/how a broken line is drawn changed. Visual.
- The weekly redraw trigger moved from `hasWeeklyTimeChanged and not isLastWeekly and barstate.isconfirmed`
  to a value-changed guard (`pwh != w_hPrice`); on intraday `pwh` changes exactly at the week roll, so the
  establishment timing is equivalent.

**Resolved 2026-07-14 — liquidity is IN PARITY, no code change.** `indicators/engines/liquidity_export.pine`
is a **value-based clean-room harness**, not a copy of mpc's drawing block: it derives each level from
`request.security("D"/"W"/"240", high[1]/low[1]/close[1], lookahead_on)` and publishes price +
mitigation + roll pulses only. The new mpc `pdh`/`pwh` resolve to that **same** previous-completed-period
value on intraday, and every changed line (origin-candle `x1`, `showMitLiq` display, chart-type display
scope) is drawing-layer — none touches a level value, a mitigation flag, or a roll pulse. Confirmed
empirically: `compare_liquidity.py "…44e3d.csv" --htf-rollover 18 --warmup 4653` → **PARITY OK, every
one of 28 fields matches on every warm bar.** Neither the engine nor the harness needs an edit.

### order_blocks — IN PARITY (benign default drift)

`maxActiveOB` input default **6 → 2** (`f139cc6`). Still an `input.int` (user-tunable), and the engine
parameterizes the FIFO cap, so the algorithm is unchanged — same class as the earlier RSI divOS/divOB
default drift. Sync `engines/order_blocks/` default 6→2 when convenient; not a parity break. Structure
detection is untouched, so OB creation timing is unchanged and `ob_export.pine` stays valid.

### market_structure — IN PARITY (sync chain NOT triggered)

Zero diff hunks touch `method process`, the 3-candle pullback, the break/CHoCH conditions, `choch_lock`,
the seed/lookback scan, the bear-BOS fallback, or the internal iSH/iSL/iBOS/iSOS detection. The only
structure-adjacent edit is `showSwingLabels` default **true → false** (a label-visibility default — the
tooltip states the engine keeps running unchanged). Per the MOST-CRUCIAL rule this is VISUAL. All six Pine
copies + `engines/market_structure/engine.py` + the shim stay current.

### Everything else — IN PARITY (input-default / display-scope only)

- **sessions** — `showHistoricSessions` false→true (display window). Not affected.
- **vwap** — `showVwapInput` true→false (default off). Not affected.
- **fibonacci** — `hideFibsSub5m` false→true, `showMacroFib`/`showIFib` defaults true; compute blocks
  byte-untouched. The A+ block newly reads `fibo4/5/6Touched` (0.702/0.786/0.886) but those are
  pre-existing StructureFib outputs, only newly *consumed*. Not affected.
- **rsi_divergence** — `showDivInput` false→true, `showDivHistory` false→true; detection byte-unchanged;
  the intraday-inert 3-day-history bug from prior audits is untouched. 100% parity holds.
- **svp / regime / news** — zero hunks. Not affected.
- **Master toggles** — `showTradeTools`/`showFibTool` default false→true; live in `mpc_assistant.pine`
  only (the `*_export.pine` harnesses have their own toggles), so parity exports are unaffected.

### A+ SETUP SEQUENCE — STRATEGY-tier rework, NOT an engine (renamed "REV SETUP" in the table)

All in the decision/display layer: (1) a divergence **retro-link** — remembers the last bull/bear SOS bar
and adopts an SOS that already fired at/after a late-confirming divergence's pivot (fixes the setup stuck
at 1/3 on fast V-reversals); (2) `aplusDivOnly` (arm Stage 1 on divergence only, ignore sweeps) and
`aplusIgnoreWindow` (order-only, no time backstop); (3) A+-owned E2/E3/E4 latches (`_702`/`_786`/`_886`)
plus precise per-bar "tapped INTO" tests for FVG (`aplusL_fvgInNow`) and Sniper Zone (`_szTapNow`), so
READY now requires an actual tap, not mere presence; (4) an `alert()` on the EARLY tier ("REV SETUP EARLY
LONG/SHORT (0.5 tap)"); (5) the table rows renamed A+ SETUP → **REV SETUP** and the CONT rows **commented
out** (tracking still runs; display suppressed). It composes existing engine outputs + FVG + fibs + the
divergence flags and decides trades → strategy-tier (`strategies/` or a Python bot). No engine dependency's
detection changed here (though its FVG confluence will shift once the FVG engine is re-synced).

### Coverage sweep — no new blocks

Every functional block still maps to an existing engine or the known strategy-tier candidates (A+/REV
SETUP sequence, HTF Directional Bias helper). **No new un-extracted feature appeared.**

### Reminder

**No engine code was changed in this audit — report only.** The FVG re-sync must re-run `compare_fvg.py`
(with `fvg_export.pine` re-synced first) to exit 0 on a fresh TradingView export before commit; the
liquidity confirmatory `compare_liquidity.py` run should be done on a fresh export too.

---

## Audit findings — 2026-07-12 (SECOND — `choch_lock` removal, working tree vs committed `7e0b30e`) 🔴 CHAIN TRIGGERED

Staged working-tree diff vs commit `7e0b30e`. Small diff — **66 lines (24+/42-)** — but it lands in the
one place that costs the most. 🔴 **The market_structure sync chain IS triggered.** This is the first
structure detection change since 2026-07-08.

### market_structure — 🔴 STALE (whole sync chain)

Two real detection changes in `method process`, each mirrored on the bull and bear side:

1. **`choch_lock` no longer gates the CHoCH decision.**
   `bool is_choch = st.dir == -1 and not st.choch_lock` → `bool is_choch = st.dir == -1`
   (mpc 648 bull / 772 bear). The flag is still *declared* (421), still *set* on a CHoCH (656, 780) and
   still *released* (492–496, 538, 580) — but **nothing reads it any more**, so `choch_lock` is now inert
   in mpc. Meanwhile `structure_engine.pine:303/424`, `structure_engine_export.pine:295/416` and
   `engines/market_structure/engine.py:614/714` **all still gate on it**. Effect: every counter-trend break
   now fires as an SOS/CHoCH, where the lock previously suppressed the SOS on the break immediately after
   a CHoCH. **More SOS events, fewer BOS.** This is squarely "WHEN a break/CHoCH fires" → logic.

2. **`last_conf_high` / `last_conf_low` no longer update on a CHoCH.**
   Both assignments are now wrapped in `if not is_choch` (mpc 697–699 bull / 820–822 bear). Python sets
   them **unconditionally** (`engine.py:651–652` / `751–752`). Source comment states the intent: *"On an
   SOS (fast reversal) the extreme is only the ACTIVE swing low — it prints as ASL and is confirmed to
   HL/LL by the NEXT bullish break."* This changes the **confirmed-swing map**, and `last_conf_*` is
   load-bearing — it feeds the HH/HL/LH/LL classification, the fallback scans
   (`if lowest_val != st.last_conf_low`, mpc 748 / 882), the public `last_confirmed_high()` /
   `last_confirmed_low()` API (`engine.py:261–270`), and the Macro fib's origin lock + new-HH extend.

**Public-API consequence (check the shim + consumers).** `broken_high_label` / `broken_low_label` are
typed `"HH" | "LH"` and `"HL" | "LL"` (`types.py:100/103`). On a CHoCH mpc now prints **ASH / ASL**
instead, so the field's domain widens (or should go `None` on a CHoCH). `algos/shared/structure_engine.py`
needs no *logic* edit (it is a thin shim) but this is exactly the "new public field a bot reads" check the
sync rule calls for.

**STALE as one unit — re-sync 2 → 3 → 4 in a single pass, then re-run
`engines/market_structure/tools/compare_tradingview.py` to exit 0 on a fresh export before committing:**
- `indicators/engines/structure_engine.pine`
- `indicators/engines/structure_engine_export.pine`
- `engines/market_structure/engine.py`

### Cascade — STALE-BY-INPUT (engine code is fine; its INPUT changed)

- **`engines/fibonacci/` — STALE-BY-INPUT.** `MacroFib` reads `snap.bull_sos` / `snap.bear_sos`
  (`engine.py:387, 419`) to lock its origin, and `snap.last_conf_high` / `snap.last_conf_high_loc`
  (`engine.py:419–425, 435–441`) as its extreme + new-HH extend. **Both of those inputs now change.** The
  fib engine's own port is still a faithful copy of mpc's fib blocks (untouched by this diff) — but its
  macro output will differ until structure is re-synced. `indicators/engines/fib_export.pine` **embeds the
  structure engine**, so it must be re-synced too, then `compare_fib.py` re-run.
- **`engines/order_blocks/` — STALE-BY-INPUT.** Creates OBs on `(snap.bull_bos or snap.bull_sos)` /
  `(snap.bear_bos or snap.bear_sos)` (`engine.py:78–81`). More SOS events → more order blocks.
  `indicators/engines/ob_export.pine` **embeds the structure engine** → re-sync, then re-run `compare_ob.py`.

### Stale harnesses

`structure_engine.pine`, `structure_engine_export.pine`, `ob_export.pine`, `fib_export.pine` — all four
carry the old `choch_lock`-gated `is_choch` and the unconditional `last_conf_*` update.

⚠️ **Also carrying the OLD logic: `indicators/strategies/mpc_strategy.pine`** (the brother's MPC-JARVIS backtest
script). It embeds the same structure engine and its trades read **only** the BOS/SOS/iBOS/iSOS breaks —
so its backtest results no longer match what the chart now prints. Not an engine, but flagging it: it is
a real consumer of the changed logic.

### rsi_divergence — IN PARITY (but the source bug got worse)

The divergence-history bug flagged in the audit below **was "fixed" in the wrong direction.** The display
layer (the `bullDivBars` / `bearDivBars` index arrays + the relevance-recolour loop, ~20 lines) was
**deleted outright**, and the same broken 3-day test was moved **into the detection `if`**:

```
bool _divRecent = showDivHistory or time[divPivotLen] >= time - 259200000
if not na(divPrevRsiLow) and _divRecent          // ← now gates DETECTION, not drawing
```

`time[divPivotLen]` is still the pivot bar — always exactly `divPivotLen` bars back, i.e. **~25 minutes on
a 5m chart** — so `25 min >= now − 3 days` remains unconditionally true and the toggle is still inert on
every intraday timeframe. **Engine impact: still none** — on 5m/15m the gate is a no-op, so
`engines/rsi_divergence/` stays at 100% parity and needs no port of it. But the placement is now *worse*:
on a Daily+ chart it silently disables divergence **detection** entirely (it used to only hide the
drawing), and it now gates `lastBullDivBar`/`lastBearDivBar` — the state the A+ row reads. The correct fix
is to age the divergence at *display* time against `lastBullDivBar`, not to gate detection. Still a Pine
source bug for Aaron/his brother, not an engine issue.

### Not affected

`sessions`, `liquidity`, `vwap`, `session_volume_profile`, `fair_value_gaps`, `regime`, `news` — zero diff
hunks in their compute blocks.

### Coverage sweep — no new blocks

Every functional block in the 3,980-line source still maps to an existing engine or to the known
strategy-tier candidates (A+ SETUP SEQUENCE, HTF Directional Bias helper). **No new un-extracted feature
appeared.**

### Cosmetic / noise (no impact)

- The `//===== INTERNAL FIB =====` header comment got indented **into** the macro-fib `if` block (mpc 2940).
  Pine ignores comments, so it is harmless — but it is a paste accident worth cleaning.
- Trailing newline removed at EOF; one blank line dropped before the JARVIS table; `showDivHistory` tooltip
  text rewritten.

### Reminder

**No engine code was changed in this audit — report only.** The market_structure re-sync must re-run
`compare_tradingview.py` on a fresh TradingView export (exit 0) before commit, and because the structure
change cascades, `compare_ob.py` and `compare_fib.py` must be re-run too — each with its structure-embedding
harness (`ob_export.pine`, `fib_export.pine`) re-synced FIRST.

---

## Audit findings — 2026-07-12 (master display switches + A+ session-gap/HTF rework, working tree vs committed `5c477ac`)

Working-tree diff vs commit `5c477ac` (the RSI-divergence default sync). 308-line diff (202+/106-).
**No engine is stale. The market_structure sync chain is NOT triggered. No `*_export.pine` harness is
stale and no `compare_*.py` needs re-running.** The structure region (mpc lines ~402–1743) has **zero
diff hunks** — every hunk is in the input block (lines 1–399), the divergence block (1846–1906), the A+
sequence (3602–3860), or the JARVIS table (3950+). Coverage swept: every functional block still maps to
an existing engine; **no new un-extracted block appeared.**

**VISUAL — the display master switch was inverted.** The single negative `marketStructureOnly` toggle
("Hide Everything Except Market Structure") is replaced by two POSITIVE master switches in a new
`Display` group: `showTradeTools` (FVG, Order Blocks, Sessions, Kill Zones, Liquidity, VWAP, MV) and
`showFibTool` (External/Internal/Cycle fib). Both default **false**, and `marketStructureOnly` is now
*derived* (`not showTradeTools and not showFibTool`) purely to gate the table's EXT/INT rows. Every
`show*` flag was re-derived from a `marketStructureOnly ? false : <flag>Input` ternary to a plain
`showTradeTools and <flag>Input` / `showFibTool and <flag>Input` conjunction. **Same effective defaults
as before** (everything non-structure already defaulted off), and these flags live only in
`mpc_assistant.pine` — the standalone `*_export.pine` harnesses have their own toggles, so parity exports
are untouched. Every gated engine — order_blocks, fair_value_gaps, sessions/kill-zones/NY-range, vwap,
liquidity, svp, fibonacci (external/internal/macro/sniper) — is **not affected**.

**VISUAL (noted) — `hideFibsSub5m`.** A new input adds `not (hideFibsSub5m and timeframe.in_seconds() <
300)` to `showFibo` and `showIFib`, which gate the fib compute blocks (mpc 2528 / 3014). Default **off**,
so nothing changes today. Even when on, it is a per-chart *scope* decision — it stops the fib machine from
running on sub-5m charts; it does not change what a fib level is or when it is touched. The Python fib
engine runs on whatever feed a bot gives it, so nothing to port. IN PARITY.

**market_structure — IN PARITY (sync chain NOT triggered).** Zero hunks touch `process`, the 3-candle
pullback, the break/CHoCH conditions, `choch_lock`, the seed/lookback scan, the bear-BOS fallback, or the
internal iSH/iSL/iBOS/iSOS detection. The only structure-adjacent edit is the `marketStructureOnly`
derivation on line 50 (an input expression). `structure_engine.pine`, `structure_engine_export.pine`,
`engines/market_structure/engine.py` and the `algos/shared/` shim all stay current.

**rsi_divergence — IN PARITY; the 5c477ac default sync is now CONFIRMED CORRECT by source.**
- *Inputs frozen into constants.* The whole `GRP_DIV` numeric input set became hardcoded literals
  (`divRsiLen = 14`, `divPivotLen = 5`, `divOS = 25`, `divOB = 75`, `divValidBars = 100`, `divVeto =
  true`, `divExtremeOB = 80`, `divExtremeOS = 20`), with only `showDivInput` (default flipped **true →
  false**) and a new `showDivHistory` toggle left as inputs. **These are exactly the engine's defaults**
  (`engine.py:127` — `rsi_len=14, pivot_len=5, oversold=25.0, overbought=75.0, valid_bars=100`), so the
  2026-07-11 sync landed on the values the source has now locked in. Nothing to do.
- *Detection unchanged.* The bull/bear divergence conditions and the RSI-pivot logic are byte-identical.
- *FIFO drawing cap = VISUAL.* `lastBullDivLine`/`lastBullDivLabel` (single, deleted-on-stale) became
  `array<line>`/`array<label>` with a `divMaxCount = 10` FIFO evict. Only `line.delete`/`label.delete`
  are involved; `lastBullDivBar`/`lastBearDivBar` — the engine-relevant state — are never cleared. The
  old delete-the-drawing-on-stale block is gone entirely.
- ⚠️ **SOURCE BUG (report only, no engine impact) — the "Show Divergence History" filter does nothing on
  intraday.** The new gate is `_divRecent = showDivHistory or time[divPivotLen] >= time - 259200000`
  (mpc 1857 / 1876), wrapping the divergence *detection* condition. Its tooltip says "Off = only show
  divergences from the last 3 days", but `time[divPivotLen]` is the pivot bar — always exactly
  `divPivotLen` bars back from the current bar, i.e. **25 minutes on a 5m chart**. `25 min >= now − 3
  days` is unconditionally true, so `_divRecent` is always true on every timeframe below ~14.4h/bar and
  the toggle is inert. It only bites on Daily+ charts, where it silently suppresses ALL divergences.
  Presumably the intent was to age out the divergence when it *fires* (against `lastBullDivBar`), or to
  filter the drawing rather than the detection. **Consequence for the engine: none** — on 5m/15m (every
  timeframe the engine is validated and run at) the gate is a no-op, so `engines/rsi_divergence/` remains
  at 100% parity and needs no port of it. Flagging for Aaron/his brother to fix in Pine.
- *Staleness rule widened — still STRATEGY-tier.* `bullDivStale` now also fires when a NEWER opposite-side
  divergence exists (`lastBearDivBar > lastBullDivBar`), on top of the existing "next external break"
  rule. This composes RSI + market_structure + the opposite side, which the standalone RSI engine has no
  inputs for by design. Its primitives (`bull_active`/`bear_active`) are unchanged and remain the right
  building block; the staleness AND belongs in the A+ strategy consumer.

**A+ SETUP SEQUENCE — STRATEGY-tier rework, NOT an engine (unchanged classification).** Substantial, all
in the decision layer: (1) the staleness window `aplusWindow` moved from **bars (300) to MINUTES (1440)**
and is compared against a new `aplusL/S_armTime` timestamp — explicitly because a bar count is fragile
across timeframes; (2) a **session-gap guard** (`sessionGapBar` = a bar whose time jump exceeds 2× the
normal spacing, i.e. the 17:00–18:00 daily close) now suppresses arming, stale-clearing and death rules on
that bar, because the daily-security roll was falsely killing live setups; (3) **daily sweeps age out**
after 24h (`dailySweepTooOldL/S`); (4) **arm-only-when-idle** (`aplusL_canArm`) so a rotating liquidity
source can't overwrite a live arm; (5) **A+-owned 0.5/0.618 latches** (`aplusL_half`/`aplusL_618`) that
survive a fib-origin redraw at the session gap, and Stage 2+ no longer requires a `fibo_dir` match (it
flickers at the rollover); (6) **HTF bias grading** — `htfDisagreeL/S` (both Weekly AND Daily oppose) warns
or optionally blocks (`aplusHtfWarn` / `aplusHtfBlock`, block only at stage ≤1), `htfTurnL/S` flags a
forming turn; (7) the **Sniper Zone is now accepted as location confirmation alongside FVG** (`seqSz`;
READY needs `seqFvg or seqSz`, not FVG alone); (8) an optional **INT trigger** (`aplusReqInt` — hold at
AWAIT ENTRY until an iSOS/iBOS confirms in the trade direction); (9) the **divergence veto is REMOVED from
A+** (a div at the sweep is part of a reversal's confirmation, not a reason to distrust it — the veto now
belongs to CONT only); (10) the on-chart CONT labels were dropped (visual). It composes existing engine
outputs only — no engine dependency changed, and it still decides trades, so it stays strategy-tier
(`strategies/` or a Python bot per `docs/BOT_DEVELOPMENT_METHOD.md`).

**fibonacci / order_blocks / sessions / liquidity / vwap / svp / fair_value_gaps / regime / news — not
affected.** Their compute blocks are byte-untouched; the only edits near them are the master-toggle
rewiring (visual) and `hideFibsSub5m` (visual, default off).

**JARVIS table — VISUAL.** The EXT and INT rows are now printed only in `marketStructureOnly` mode; the
A+ row gained the location/HTF/INT tags described above. No compute touched.

**HTF Directional Bias helper (candidate, still not extracted).** `wEstState`/`dEstState` are now consumed
by the A+ HTF-bias gate as well as the table — a second consumer, but still no engine. Unchanged status.

**Harnesses — none stale.** No ported engine's detection changed, so no `*_export.pine` needs re-syncing
and no `compare_*.py` needs re-running.

**No engine code was changed in this audit — report only.** If the A+ sequence, the divergence-staleness
rule, or the HTF bias helper are ever extracted, each engine fix must re-run its `compare_*.py` Pine-parity
check on a fresh TradingView export (matching `*_export.pine` updated first) before commit.

---

## Audit findings — 2026-07-11 (marketStructureOnly + A+/CONT rework, working tree vs committed `21cbe43`)

Working-tree diff vs commit `21cbe43` (the RSI-divergence-engine commit). 484-line diff (305+/179-).
**No engine is stale. The market_structure sync chain is NOT triggered. No `*_export.pine` harness is
stale and no `compare_*.py` needs re-running.** The diff is three things: a display master-toggle, a
strategy-tier rework of the A+ setup machine, and a divergence liveness/veto rule. The structure `process`
+ internal detection region (mpc lines ~390–1800) has ZERO diff hunks — the hunks are all in the input
block (lines 42–356), the divergence vars/logic (1835–1908), and the A+ sequence + JARVIS table (3596–3874).

**NEW — `marketStructureOnly` master DISPLAY toggle (VISUAL).** A new `input.bool(true, "Hide Everything
Except Market Structure")` at the top of the Market Structure group. Every non-structure feature toggle was
renamed `<flag>Input` (e.g. `showOBs`→`showOBsInput`, `showFVG`→`showFVGInput`, `showDiv`→`showDivInput`,
`showSessions`, `showKZandNYR`, `showVwap`, `i_showLiquidity`, `showIFib`, `showFibo`, `showMacroFib`,
`showSVP`) and the live flag re-derived inline as `marketStructureOnly ? false : <flag>Input`; three
downstream flags with no `active=` dependents (`showSniperFib`, `showKillZones`, `showNYRange`) get a plain
`:=` override in a dedicated block. This force-hides every non-structure drawing when on (the default). It
gates DISPLAY only — no detection, no event stream, and it lives only in `mpc_assistant.pine` (the
standalone `*_export.pine` harnesses don't have it, so parity exports are unaffected). Every engine that
these flags gate — order_blocks, fair_value_gaps, rsi_divergence, sessions/kill-zones/NY-range, vwap,
liquidity, fibonacci (external/internal/macro/sniper), svp — is **not affected**.

**market_structure — IN PARITY (sync chain NOT triggered).** No hunk touches `process`, the 3-candle
pullback, the break/CHoCH conditions, `choch_lock`, the seed/lookback scan, the bear-BOS fallback, or the
internal iSH/iSL/iBOS/iSOS detection. `extBreakThisBar` (mpc line 1255 = `bull_bos or bear_bos or bull_sos
or bear_sos`) is the pre-existing structure-break alias, only newly *consumed* by the divergence-staleness
and A+ blocks. `structure_engine.pine`, `structure_engine_export.pine`, `engines/market_structure/engine.py`
and the shim all stay current.

**rsi_divergence — DETECTION IN PARITY; ONE default drift + new staleness/veto is strategy-tier.**
- *Detection unchanged.* The bull/bear divergence conditions (`_pLow < divPrevPriceLow and divPlRsi >
  divPrevRsiLow and math.min(...) <= divOS`, and the bear mirror) and the pivot logic are byte-identical.
  The only edit at the detection site is capturing the drawn line/label into `var line/label` vars so they
  can later be deleted — visual.
- *Config-default drift — SYNCED IN CODE + PARITY RE-CONFIRMED at 25/75 (2026-07-11).* Input defaults
  `divOS` 30→25 and `divOB` 70→75 changed. The formula is unchanged (parameterized threshold), so the
  algorithm is not broken. Synced `oversold` 30.0→25.0 / `overbought` 70.0→75.0 across
  `engines/rsi_divergence/engine.py` (defaults + comments + docstring), `indicators/engines/rsi_div_export.pine`
  (input defaults), `engines/rsi_divergence/tools/compare_rsi_div.py` (argparse defaults + help + docstring),
  `engines/rsi_divergence/tests/test_engine.py` (`ref_run` defaults + the two anchor assertions 30/70→25/75
  + the defaults comment), `__init__.py` + `CLAUDE.md` doc refs. **9 unit tests green** at 25/75 (the swing
  series still fires both divergences under the stricter gate). **PARITY: `compare_rsi_div.py --warmup 8762`
  exit 0** on a fresh 25/75 `VANTAGE_XAUUSD, 5m` export (16,887 bars) — every field matches on all warm bars,
  and the divergence **pulses** (`px_div_bull`/`px_div_bear`, the real output) match from bar 16 onward. The
  warm-up is larger than the earlier 1,630 (30/70) run for two benign reasons, both verified: (1) the age
  columns cold-start — Pine's export opens carrying an OFF-window divergence in `bull/bear_age`, which only
  reconciles once the first mutually-agreed IN-window divergence resets both counters; at the stricter 25/75
  gate qualifying divergences are rarer, so the bear-side reconciliation lands near bar 8761. (2) Four
  isolated RSI-pivot float-ties (bars 1639/2179/3561/8761) where the CSV-rounded RSI equals a neighbour to
  ~1e-14 (e.g. bar 1634 = 51.75679981943045 vs bar 1635 = …44) — Pine's full-precision strict `ta.pivothigh`
  confirms the pivot, Python's RSI-from-rounded-closes sees a tie and skips it. This is the documented
  Wilder-RMA float-tie, independent of the divOS/divOB change (pivots don't read those thresholds), and it
  causes ZERO divergence-pulse mismatch on this export. **Validated — ready to commit.**
- *New staleness rule = STRATEGY-tier, not the engine.* `bullDivStale`/`bearDivStale` mark a divergence
  stale once the next external break fires after it (`lastExtBreakBar > lastBullDivBar`), and
  `bullDivActive`/`bearDivActive` now AND in `not …Stale` (plus the drawing is deleted). This ties
  divergence liveness to external structure — a composition of RSI + market_structure. The standalone RSI
  engine has no structure input by design; its primitive (`bull_active`/`bear_active` = divergence within
  `divValidBars` bars) is the right building block, and the A+ consumer ANDs it with "no external break
  since." So this belongs in the A+ SEQUENCE strategy build, NOT in `engines/rsi_divergence/`.
- *New veto = STRATEGY-tier.* `divVeto`/`divExtremeOB`(80)/`divExtremeOS`(20) inputs + `longVeto`/`shortVeto`
  flags suppress a setup on opposing live divergence or extreme RSI. Pure trade-decision logic → A+ strategy.

**A+ SETUP SEQUENCE — STRATEGY-tier rework, NOT an engine (unchanged classification).** Big rework, all in
the decision layer: Stage-1 arming is now EDGE-triggered on a NEW sweep OR a NEW divergence (`newSweepL`/
`newDivL` via `!= [1]`), the `aplusL_consumed`/`aplusL_done` bookkeeping is gone, a stale-arm is cleared
when no SOS follows within `aplusWindow`, death rules are reworked (any SOS clears CONT on both sides), and
**CONT (continuation) is split out into its own trade type** with its own JARVIS row + on-chart "CONT"
labels (BOS with no A+ tracked on that side, entry at E1–E4). READY now REQUIRES a live FVG (else "AWAIT
FVG"); the veto shows "EXTREME" instead of a tradeable row. It composes existing engine outputs + FVG +
`fiboHalfReached` + the divergence flags; it decides trades, so it stays strategy-tier (belongs in
`strategies/` or a Python bot per `docs/BOT_DEVELOPMENT_METHOD.md`). No engine dependency changed.

**fibonacci / order_blocks / sessions / liquidity / vwap / svp / fair_value_gaps / regime / news — not
affected.** Their compute blocks are untouched; the only edits near them are the `marketStructureOnly`
display gate (visual), the FVG bull/bear colours flipped to grey (visual), and the removal of the FIB
INTERNAL/EXTERNAL/CYCLE rows from the JARVIS table (visual — the fib engines still emit everything; the
table just stopped printing those rows, replaced by a `table.clear` cleanup).

**Harnesses — none stale.** No ported engine's detection changed, so no `*_export.pine` needs re-syncing.
(The optional RSI default sync above would touch `rsi_div_export.pine` + a fresh export at that time.)

**No engine code was changed in this audit — report only.** If the RSI defaults are synced, or the A+
sequence / divergence-staleness / veto are ever extracted, each engine fix must re-run its `compare_*.py`
Pine-parity check on a fresh TradingView export (matching `*_export.pine` updated first) before commit.

---

## Audit findings — 2026-07-10 (RSI-divergence re-paste, working tree vs committed `29d55f2`)

Working-tree diff vs commit `29d55f2` (the FVG + `fiboHalfReached` + A+ setup commit — the section below
this one is that audit). Tiny diff: **66 lines, 64+/2-**, one self-contained new feature. **No engine is
stale. The market_structure sync chain is NOT triggered.** No `*_export.pine` harness is stale and no
`compare_*.py` needs re-running.

**NEW BLOCK — RSI Divergence** (un-extracted). A `GRP_DIV` input group (`showDiv`, `divRsiLen` 14,
`divPivotLen` 5, `divOS` 30, `divOB` 70, `divValidBars` 100) + a compute block: `ta.rsi(close, divRsiLen)`
with `ta.pivotlow`/`ta.pivothigh` on the RSI, detecting regular divergence at the extremes — price
lower-low while RSI higher-low from oversold (bullish), price higher-high while RSI lower-high from
overbought (bearish). Pivots confirm `divPivotLen` bars after the extreme (non-repainting). Draws a dotted
line + label and sets `bullDivActive`/`bearDivActive` (live for `divValidBars` bars). Genuine new event
logic; standalone (RSI + price/RSI pivots — no upstream engine, no volume, no timestamp), same shape as
the FVG engine. Added to "Still to build" as a candidate.

**Only consumer = the JARVIS "A+ SETUP" table row.** The flags flow to `seqDiv` (line 3685) → a `" + DIV"`
tag appended to the READY/EARLY A+ row text (lines 3688–3693). They do NOT alter any engine's detection,
and they do NOT alter the A+ setup sequence's staging (`seqStage`) — purely a display confluence tag. So
this is an A+-support add-on in the strategy/display tier, not an engine change.

**Every engine — not affected.** Nothing in the diff touches structure, fibonacci, order_blocks,
sessions/kill zones/NY range, liquidity, vwap, svp, fair_value_gaps, regime, or news. All IN PARITY.

**Housekeeping:** the FVG engine + `fiboHalfReached` that the audit below listed as "ready to commit" are
now COMMITTED (`29d55f2`, 2026-07-10) — still listed under "Still to build" with their ✅ built markers
for the port detail, but they are shipped and Pine-parity-validated.

**No engine code was changed in this audit — report only.** If the RSI divergence detector is later
extracted, it gets its own `rsi_divergence` engine + a parity harness (`rsi_div_export.pine`) +
`compare_rsi_div.py`, run to exit 0 on a fresh TradingView export before commit.

---

## Audit findings — 2026-07-10 (fresh re-paste of `mpc_assistant.pine`, staged, uncommitted)

Staged diff vs commit `d367b6d` (the last audit's commit). 524-line diff (381+/143-). **No engine is
stale.** This paste is mostly visual polish plus two genuinely new computed features (FVG + the A+ setup
sequence machine). Block by block:

**market_structure — IN PARITY (sync chain NOT triggered).** Only cosmetic changes touch the structure
block: a new `showSwingLabels` input + `f_swingCol()` helper that hides swing-point labels by making
their text transparent (the comment in source is explicit — "The label objects still exist and the
engine's state is untouched"), every `textcolor=…` wrapped in `f_swingCol(…)`, and the iBOS/iSOS labels
repositioned (dropped the `- i_lbl_y_offset`, style `label.style_none → label.style_label_up`). The
3-candle pullback, break/CHoCH conditions, `choch_lock`, the seed/lookback scan, the bear-BOS fallback,
and the internal iSH/iSL/iBOS/iSOS *detection* are all byte-unchanged. Per the MOST-CRUCIAL rule these
are label colour/position tweaks → **VISUAL, chain not triggered.** `structure_engine.pine`,
`structure_engine_export.pine`, `engines/market_structure/engine.py` and the shim all stay current. (The
new `extBreakThisBar` bool just names the already-existing `bull_bos or bear_bos or bull_sos or bear_sos`
condition to clear the *table's* INT row — not a detection change.)

**fibonacci — IN PARITY (existing outputs unchanged) + one new A+-support flag noted.**
- *Structure fib*: NEW `fiboHalfReached` var — the **inbound 0.5 touch** during the retracement toward
  the entry zone (ungated; distinct from `fibo2Touched`, which tests the same price on the way *out* as
  TP1, gated behind 0.618). It is reset in the new-leg block and computed via the existing `f_checkTouch`.
  It changes NO existing level's detection (fibo1–fibo10 touch logic is byte-unchanged); it is a purely
  additive flag that feeds ONLY the new A+ sequence. So the fib engine is correct on everything it emits
  today; `fiboHalfReached` is a **new output it does not yet emit**. Add it (as a StructureFib event +
  `px_fibo_half_reached` column) only when the A+ sequence is extracted or a bot needs the 0.5 early-entry
  tier.
- *Macro / Cycle fib*: the run-guard opened from `if showMacroFib and macroFibAllowed` to `if bar_index
  >= 0` — the **tracking state machine now runs on every bar/timeframe** (drawing stays gated, now via the
  new `macroMaxTfMin` input, and the `showMacroFib and macroFibAllowed` guard survives at the DRAW site,
  mpc line 2740). The macro compute BODY is unchanged (bear-SOS first-bar seed, origin lock, bottom anchor
  all identical). The Python `MacroFib` already runs unconditionally from bar 0, so this brings source
  *toward* the engine, not away — and on the validated 5m export the old guard was already true, so the
  harness output is bit-identical. **No re-validation needed; IN PARITY.**

**order_blocks — not affected.** Structure detection unchanged → internal-break timing unchanged →
`ob_export.pine` (embeds the structure engine) stays valid. No OB code touched.

**sessions / kill zones / NY range — not affected (VISUAL).** Display-window reworks only: sessions
switched from a rolling 7-day cutoff to a calendar-week anchor (Sunday 00:00 NY); kill zones / NY range
switched from `kzDaysBack`/`nyrDaysBack` int inputs to a `showKZHistoric` toggle (current NY day only by
default); the redundant `tzHighD/tzLowD` daily-security was removed and the KZ boxes now reuse
`dailyHigh/dailyLow` (same values). All gate only drawn boxes/`sessionInfos`, never the event stream. No
engine impact (SVP, which composes the sessions stream, is likewise unaffected).

**liquidity — not affected (VISUAL).** The three `i_showAsiaHL/LondonHL/NYHL` inputs were collapsed into
one `i_showSessionHL` toggle, kept as three internal flags "so the drawing/mitigation logic below stays
unchanged" (source comment). No level or mitigation compute changed.

**vwap — not affected (VISUAL).** `vwapValue = ta.vwap(hlc3)` is byte-unchanged; only the DRAWING switched
from a per-bar-rebuilt polyline to a single `plot()` (O(1) vs O(n²)). Default toggle flipped on. Engine
IN PARITY.

**svp / regime / news — not affected.** SVP/MV and Sniper compute blocks are fully intact — only their
JARVIS *table rows* were removed (visual). No compute touched.

**HTF Directional Bias helper (candidate, still not extracted) — simplified.** `f_htfBias` dropped the
"Current Forming" bias (Live[0] vs Closed[1]) that "was never consumed" and now returns only the
Established Context (Closed[1] vs Closed[2]) from one security call. Still feeds only the JARVIS table;
still a candidate, no engine. Noted so a future extraction ports the simplified 2-value shape.

**NEW FEATURE #1 — FAIR VALUE GAPS (FVG)** (un-extracted). A clean-displacement gap detector: a bullish
FVG is the void between candle A's high and candle C's low when three same-direction candles close
progressively higher (bearish mirrors); confirmed bars only; persists until price taps its near edge
(deleted on tap, NOT on BOS/SOS); optional directional filter (hide gaps opposing `st.dir`); FIFO cap
(`fvgMaxCount`, oldest dropped). Genuine new event logic (gap formed / gap mitigated). Candidate for a
small `fair_value_gaps` engine (or an A+ sub-component). Added to "Still to build".

**NEW FEATURE #2 — A+ SETUP SEQUENCE** (un-extracted; REPLACES the old SETUP GRADING candidate). A
stateful, ordered setup machine, per side: (1) SWEEP — a tracked HTF liquidity grab (recentSSL/recentBSL);
(2) MSS — an external SOS firing after the sweep within `aplusWindow` bars; (3) ENTRY — the SOS leg's fib
retrace (0.5 tapped → EARLY, 0.618 reached → READY/E1). Plus: a **Cycle-Fib POI** latch (discount 0.618–
0.886 for longs / premium ≥0.382 for shorts, tracked on all timeframes), **FVG confluence** (a live gap
overlapping the 0.5–0.886 entry zone), a **continuation mode** armed after a completed A+ (next same-side
BOS re-arms the same entry tiers), and death rules (opposite SOS, close past fib 1.0, or TP3 hit). This is
real bot-relevant decision logic built entirely on existing engine outputs + FVG + `fiboHalfReached`.
Strong candidate for a `setup_sequence` engine. Added to "Still to build" (supersedes SETUP GRADING).

**Harnesses — none stale.** No ported engine's detection changed, so no `*_export.pine` needs re-syncing
and no `compare_*.py` needs re-running. (If/when FVG, the A+ sequence, or `fiboHalfReached` are extracted,
each gets its own parity harness + check at that time.)

**No engine code was changed in this audit — report only.** Any future engine change (e.g. adding
`fiboHalfReached`, or building the FVG / A+ / bias engines) must re-run its `compare_*.py` Pine-parity
check on a fresh TradingView export, with the matching `*_export.pine` harness updated first, before it is
committed.

---

## Audit findings — 2026-07-09 (fresh re-paste of `mpc_assistant.pine`, uncommitted)

Working-tree diff vs commit `f2a8411` (its last commit; HEAD is `eecd3f7`). 184-line diff. This paste
came AFTER the 2026-07-08 re-sync was completed & committed, so it re-opens drift. Most of it is one
feature removal (Monthly liquidity), one fib touch-detection refinement (repeated across Structure +
Internal), and one new table block. The engine-affecting changes:

**liquidity — STALE (feature removed from source).** The entire **MONTHLY level (PMH/PML) is deleted**:
the `request.security(..., "M", ...)` fetch, `hasMonthlyTimeChanged`, `canShowMonthly`, the whole
`MONTHLY LEVELS` compute/mitigate block, the `i_isMonthlyEnabled` / `i_monthlyColor` inputs, the
`a_lastHighs`/`a_lastLows` arrays shrunk **3 → 2** (monthly slot 2 gone), the monthly label pushes, and
the `"MH"`/`"ML"` plot columns. The engine emitted PMH/PML, so its event set diverged from source.
**RE-SYNC STATUS (2026-07-09): DONE + parity CONFIRMED (exit 0).** Aaron's call: **remove monthly entirely**
(not keep behind a flag). Removed `_key_month`, `_monthly` tracker, the `enable_monthly` arg, the
`"monthly"` enable/hide entries, and the PMH/PML emission from `engines/liquidity/engine.py`; dropped the
MONTHLY block + `px_pmh/px_pml(_mit)` + `px_month_roll` from `indicators/engines/liquidity_export.pine`; dropped
the monthly columns + `_key_month` import + month roll-watcher from `tools/compare_liquidity.py`; removed
the monthly unit test and `enable_monthly` from the test helper (14 tests green); scrubbed monthly from
the engine/types/`__init__`/CLAUDE docstrings. The check now covers **28 fields** (13 prices + 12 mit +
3 rolls). **RE-VALIDATED: `compare_liquidity.py --warmup 1742` exit 0** on a fresh combined
`VANTAGE_XAUUSD, 5m` export (13,759 bars) — every retained field matches on every warm bar; the 1,742-bar
warm-up is now just the weekly cold-start (monthly no longer dominates it). Everything else in liquidity is
unchanged — daily/weekly/PWC/H4/session and their mitigation are untouched.

**fibonacci — STALE (logic changed across Structure + Internal + Macro).**
- *Structure fib*: (a) NEW **extend-changed guard** — touched-checks now also skip on the bar the
  extending anchor itself moved (`fiboExtChanged` via new `fiboPrevAsh`/`fiboPrevAsl`), so a fresh live
  wick-high can't retroactively satisfy the TP3 level it just created. (b) The **TP3-hit reset is
  REMOVED** — `if fibo7Touched: fiboResetActive := true` is gone; the leg is no longer hidden/spent on a
  TP3 tap (it now only clears on a real BOS/SOS / close past 1.0). The engine currently latches
  `self._reset_active = True` on the TP3 hit (`engine.py:192`) — now WRONG.
- *Internal fib*: same two changes — NEW `iFibExtChanged` guard (`iFibPrevAsh`/`iFibPrevAsl`, also
  cleared in the external-BOS/SOS reset block), and the **TP3-hit reset REMOVED** (`iFibResetActive`
  latch gone; engine still sets `self._reset_active = True` at `engine.py:626` — now WRONG).
- *Macro / Cycle fib*: the bear-SOS tracker now **seeds on the first bar too**
  (`if st.bear_sos or na(macro_last_bear_sos_bar)`) so the first bullish SOS can lock immediately
  instead of waiting for a prior bearish SOS.
- **RE-SYNC STATUS (2026-07-09): DONE + parity CONFIRMED (exit 0).** Ported into `engines/fibonacci/engine.py`:
  removed both `reset_active`-on-TP3 latches (Structure + Internal; `_reset_active` kept as an
  always-False mirror since the Pine var still exists), added the extend-changed guard + `_prev_ash/_prev_asl`
  tracking to StructureFib and InternalFib (InternalFib resets them on the external-break clear only, not on
  a seed — matching Pine), and gave MacroFib the first-bar seed. Dropped the now-unused `_TP3` constant.
  `indicators/engines/fib_export.pine` re-synced to match (both TP3 setters removed, `fiboPrevAsh/Asl` +
  `iFibPrevAsh/Asl` vars + `*ExtChanged` guards + the macro seed fallback added). Fib tests re-traced (40
  green: the two TP3-latch tests rewritten to assert reset_active stays False, + a new extend-changed-skip
  test for both fibs). `compare_fib.py` needs NO change — the column set is unchanged
  (`px_fib_reset_active` / `px_ifib_reset_active` are now always 0 on both sides). **RE-VALIDATED:
  `compare_fib.py --warmup 3154` exit 0** on a fresh combined `VANTAGE_XAUUSD, 5m` export (13,759 bars) —
  Structure + Sniper + Macro + Internal all match on every warm bar (the warm-up is the Macro cycle
  cold-start). Downstream of market_structure (unchanged here), so no ordering constraint.
- *Table-only consequence (VISUAL, no engine impact):* the JARVIS `fib_stage`/`int_fib_stage` rows no
  longer clear on a TP3 tap (they mirror the removed reset) — that lives in the confirmation-table block,
  not the fib engine.

**market_structure — IN PARITY (sync chain NOT triggered).** Nothing in `process`, the 3-candle
pullback, the break/CHoCH conditions, `choch_lock`, the seed/lookback scan, or the internal
iSH/iSL/iBOS/iSOS detection changed. The `st.bear_sos` / `st.bull_bos` reads in the fib & macro blocks
*consume* structure output; they don't alter detection. `structure_engine.pine`,
`structure_engine_export.pine`, `engines/market_structure/engine.py` and the shim all stay current.

**order_blocks — not affected.** Consumes internal structure breaks; structure is unchanged, so OB
timing is unchanged and `ob_export.pine` (which embeds the structure engine) stays valid.

**sessions — not affected (VISUAL).** `showHistoricSessions` renamed "Show All History",
`sessionsDaysBack` input removed, and `sessionsCutoff`/`withinSessionDays` simplified to a fixed 7-day
display window (or unlimited when the toggle is on). This gates only the drawn `sessionInfos`, not the
event stream the engine emits. No engine impact (SVP, which composes the sessions event stream, is also
unaffected).

**vwap / svp / regime / news — not affected.** Untouched by this paste.

**NEW block — SETUP GRADING (candidate, not extracted).** A setup classifier (A+/B/C/Pass) synthesizing
bias + sweep + external structure + fib/sniper location + internal timing into one grade + side; feeds
only the new JARVIS "SETUP" table row for now. Added to "Still to build" as a candidate (alongside the
HTF Directional Bias helper). No engine yet.

**Harnesses re-synced + validated (2026-07-09):** `indicators/engines/liquidity_export.pine` (monthly block +
`MH`/`ML` + `px_month_roll` removed) and `indicators/engines/fib_export.pine` (both TP3 setters dropped;
`fiboPrevAsh/Asl` + `iFibPrevAsh/Asl` vars + `*ExtChanged` guards + the Macro first-bar seed added). A
single fresh combined export — both indicators on one `VANTAGE_XAUUSD, 5m` chart (13,759 bars) — validated
both: `compare_liquidity.py --warmup 1742` and `compare_fib.py --warmup 3154`, both exit 0. Ready to commit.

Each engine fix must re-run its `compare_*.py` Pine-parity check on a fresh TradingView export (with the
matching `*_export.pine` harness updated first) before it is committed. **No engine code was changed in
this audit — report only.**

---

## Audit findings — 2026-07-08 (fresh, larger re-paste of `mpc_assistant.pine`)

Working-tree diff of `indicators/engines/mpc_assistant.pine` vs commit `de54b6b` (HEAD; its mpc copy ==
`6f76bed`). This is a big re-paste (1721 lines). Most of it is still visual — the JARVIS table rebuilt
to a 3-col Weekly/Daily HTF-bias layout, a new watermark, table position/size inputs, `showExternal` /
`showHistoricalInternal` / `showHistoricSessions` / `showIFib` toggles, `showOBs`/`showKZ`/`showVwap`
default-off, mitigated-levels hardcoded off, line-length inputs, sniper bull/bear colouring, and the
new HTF-bias table block. The engine-affecting changes:

**market_structure — STALE (logic changed; whole sync chain).** Two real detection changes in mpc's
structure block that are NOT in `structure_engine.pine` (which only got the visual table flags), so the
mirror has drifted:
- *External* (`process`): a new `else` fallback that, when no ASH pullback high exists at a bearish
  confirmation, scans back for the highest high since the last confirmed low and promotes it to
  `st.last_conf_high` / `st.last_conf_high_loc` (with an HH/LH label). Changes when/what a swing high
  confirms — a public output the fib + macro anchor on.
- *Internal*: the "stop internal tracking" reset now fires on external **BOS too**
  (`st.bull_bos or st.bear_bos or st.bull_sos or st.bear_sos`), not just SOS — changes iBOS/iSOS timing.
- Per the MOST-CRUCIAL rule these make `indicators/engines/structure_engine.pine`,
  `indicators/engines/structure_engine_export.pine`, AND `engines/market_structure/engine.py` STALE as one
  unit. Re-sync 2→3→4 and re-run `compare_tradingview.py` (exit 0) on a fresh export before committing;
  then check the `algos/shared/structure_engine.py` shim only for any new public field.
- Note: the new `int_bull/bear_bos/sos` flags + `i_lbl_y_offset` `*100→*20` in `structure_engine.pine`
  are VISUAL (table flags / label offset) — they are fine, they are not the drift.
- **RE-SYNC STATUS (2026-07-08): DONE — parity CONFIRMED (exit 0).** Both detection changes ported into
  `structure_engine.pine`, `structure_engine_export.pine`, and `engines/market_structure/engine.py` (the
  external fallback mirrors the `label.new` via `broken_high_*` and updates `st.last_conf_high`; the
  internal reset now fires on `bull_bos/bear_bos` too). The `algos/shared/structure_engine.py` shim reads
  only `last_confirmed_high/low` — no new field, no shim edit. Unit tests 10/10 pass.
  `compare_tradingview.py` on a FRESH `VANTAGE_XAUUSD, 5m` export from the updated harness
  (`exports/VANTAGE_XAUUSD, 5_ce976.csv`, 7,369 bars, `--warmup 161`) → **✓ PARITY: every field matched
  on every bar** (bars 0-160 are the usual cold-start warmup — Pine's export began mid-history; they
  converge cleanly and stay matched). (The `i_confirmed_low/high` internal-swing capture is fib-support —
  "used only for the fib pull" — and is deferred to the fibonacci re-sync as a StructureSnapshot addition,
  not part of this detection re-sync.)

**fibonacci — STALE (logic changed, heavily).** The held Macro question is resolved and the whole fib
block needs re-syncing:
- *Structure fib*: **dropped TP4 (`fibo8`, -0.270) and TP5 (`fibo9`, -0.618)** — the emitted level set
  shrank. Also added: adopt a more-extreme **internal** swing (`i_confirmed_low/high`) as the fib
  anchor, and a **`fiboResetActive`** reset that hides all levels once TP3 (`fibo7`/0.0) is touched,
  until a new leg. Touch checks refactored to `f_checkTouch` (same semantics).
- *Macro / Cycle fib*: the held **full-reset is REVERTED to HIDE-only** (`macro_visible := false`, no
  state wipe) and moved to run AFTER the HH-extend + touch checks; the bottom anchor is now **always**
  `macro_ll_since_bear_sos` (the `macroLLafterSOS` conditional that could pick `st.last_conf_low` is
  gone); dead `_time` vars removed. So the currently-HELD `engines/fibonacci/{engine.py,
  tests/test_macro_fib.py}` + `indicators/engines/fib_export.pine` full-reset edits are now WRONG — discard and
  redo as hide-only + the new bottom anchor.
- *Internal Fib (NEW, 4th fib)*: now FULLY implemented in source (`GRP_IFIB` inputs + the INTERNAL FIB
  compute/touch/draw block + the internal-structure anchor captures) — anchored to iBOS/iSOS, live
  anchor extending to the running low/high, 0.618 gate, TP3-hit reset, cleared on any external
  BOS/SOS. Port as `InternalFib` alongside `StructureFib`; add `px_ifib_*` columns to `fib_export.pine`.
- Downstream of market_structure — re-sync fibonacci only AFTER the structure engine is re-synced (the
  new external fallback changes `last_conf_high`, which the macro reads).
- **RE-SYNC STATUS (2026-07-08): DONE — parity CONFIRMED (exit 0).** All four
  changes ported: (1) `market_structure` now captures `i_confirmed_high/low_*` (at each iSH/iSL confirm)
  and the `ifib_seed_*` anchors (at each of the six iBOS/iSOS sites) on `InternalEvents` — capture-only,
  structure parity re-confirmed exit 0. (2) Structure fib drops TP4/TP5, adopts the confirmed internal
  swing as its pull anchor (latched + reset on origin change), and latches `reset_active` on the TP3 hit.
  (3) Macro bottom anchor is always `ll_since`, and HIDE now runs after extend+touch (hide-only). (4) New
  `InternalFib` class + `InternalFibEvents` ported (seed → live-extend → 0.618-gated touch machine → TP3
  reset → external-break clear). Harness `fib_export.pine` rebuilt: full internal-structure block + the
  four fib blocks + 62 `plot()` columns (Internal fib emits touch pulses + state only — no per-level
  price columns — to stay under TradingView's 64-plot cap; touches validate geometry indirectly).
  `compare_fib.py` updated (drops tp4/tp5, adds `px_ifib_*` + `px_fib_reset_active`). Fib tests: 47 pass
  (8 new: i_confirmed adoption, TP3 reset, macro bottom anchor, + a new `test_internal_fib.py`).
  **Parity confirmed 2026-07-09** on a fresh `VANTAGE_XAUUSD, 5m` export (7,562 bars): every compared
  field — Structure + Sniper + Macro + Internal — matches on all 5,646 warm bars (`--warmup 1916`, exit 0).
  The warmup is the Macro cycle's cold-start: Pine's macro is active from bar 0 (a cycle that began before
  the export window) and, being long-lived, only reconciles with the cold-started Python engine once that
  pre-window cycle ends and both lock the same in-window cycle at bar 1916 (Structure/Sniper converge by
  ~bar 108). One InternalFib 0.5-touch fired a single bar late from CSV 2-dp rounding at a float-tie
  boundary; absorbed by a `_TOUCH_EPS = 1e-6` inclusive margin on the InternalFib touch comparisons
  (« 0.01 tick — cannot register a real un-reached level early). Re-synced and committed.

**session_volume_profile — DONE, parity CONFIRMED (2026-07-09).** `svpRows` **100 → 50** (mpc line 317,
now a hardcoded literal, was an input at 225). Halving the profile granularity moves the POC price. Done:
`_SVP_ROWS` 100 → 50 in `engine.py`, `svpRows` 100 → 50 in `indicators/engines/svp_export.pine`, the 12 unit tests
re-traced to the 50-row grid (3 POC asserts shifted — 99.05→99.1, 99.1→99.0, 99.1→99.0 — all green), and
every 100-row reference in the engine/docstrings/CLAUDE.md updated to 50. Re-validated on a **fresh 5m
export from the updated 50-row `svp_export.pine`** (13,147 bars): `compare_svp.py --warmup 251` exit 0,
all three fields (POC price + form pulse + sweep state) match on every warm bar. The 251-bar warmup is the
cold-start (Pine carries a pre-window POC of 4538.06 from bar 0; Python forms its first in-window POC at
bar 251). (The `svpNew` MV-reset change already matched the committed engine — only the row count was
newly stale.)

**liquidity — IN PARITY (no new drift).** The mitigation was refactored into a shared `f_liqMitigate`
helper but the conditions are unchanged from what's committed — wick-only sweep (`high>lvl`/`low<lvl`)
for daily/session/H4, close-break for weekly/monthly. The PDH/PDL/PWH/PWL `[1]` offset + weekly
`lookahead_off` bring mpc's DISPLAY in line with the already-non-repainting engine (prev completed
period), so no event change. No action.

**order_blocks — DONE, parity CONFIRMED (2026-07-09).** `extendOBs` and OB detection are untouched;
only the default toggle flipped. But OB consumes internal breaks, whose timing shifts with the
internal-reset-on-BOS change. The catch was the **harness**: `indicators/engines/ob_export.pine` still embedded
the pre-2026-07-08 structure block (built 2026-07-04), so it had to be re-synced first — the same two
f2a8411 changes (bear-BOS fallback swing-high scan + internal-reset firing on external BOS too) ported
in, leaving its `process` method byte-identical to the current `structure_engine_export.pine` and its
internal state machine differing only by the OB creation blocks. With the harness current, `compare_ob.py`
passed on a fresh `VANTAGE_XAUUSD, 5m` export (12,618 bars): every OB field — active bull/bear arrays
slot-by-slot, counts, created/mitigated pulses, and `px_i_break_origin_ago` — matched on every warm bar
(`--warmup 1133`, exit 0). The 1133-bar warm-up is the cold-start (Pine opened holding 6 pre-window bull
OBs; the bull side flushed them by bar 1132, bear by bar 29). The OB **engine code needed no change** —
this was a re-validation; only the harness was re-synced.

**sessions / vwap / regime / news — not affected.** Sessions gained a `withinSessionDays` display-window
gate (current-week-only unless `showHistoricSessions`); it gates only the drawn `sessionInfos`, not the
event stream the engine emits — visual, noted for reconciliation. VWAP/regime/news untouched.

**Stale harnesses to update before re-validation:** `structure_engine.pine` (+ its export),
`fib_export.pine` (Structure fib level drop + internal anchor + `fiboResetActive` + macro hide-only/
bottom-anchor + new `px_ifib_*`), `svp_export.pine` (50 rows), `ob_export.pine` (embedded structure
block — re-synced 2026-07-09 with the two f2a8411 changes; ALL now DONE).

**New block noted (not yet on the extract list):** the **HTF Directional Bias** helper
(`f_biasState`/`f_htfBias`, Daily/Weekly established+current bias with sweep detection) — currently
feeds only the JARVIS table, but it is genuinely new computed logic a bot might want. Flagging as a
candidate; no engine yet.

Each engine fix must re-run its `compare_*.py` Pine-parity check on a fresh TradingView export (with the
matching `*_export.pine` harness updated first) before it is committed.

---

## Audit findings — 2026-07-06 (re-pasted `mpc_assistant.pine`) — SUPERSEDED by 2026-07-08 above

Working-tree diff of `indicators/engines/mpc_assistant.pine` vs commit `6f76bed` (its last commit). Most of
the diff is visual — a reworked JARVIS confirmation table (3-col, most-recent BSL/SSL + per-fib
one-way stage tracking), a bottom watermark, new show/hide toggles (`showExternal`, `showConfTable`,
`showIFib`), `showOBs`/`showKZandNYR`/`showVwap` flipped to default-off, `fiboLineExtend`/`iFibExtend`
line-length inputs, sniper bull/bear colouring, and macro fib label renames (HH/LL → TP3/1.0). Those
touch no engine. The engine-affecting changes:

**RE-SYNC STATUS (2026-07-07):** all three engines were re-synced (engine code + `*_export.pine`
harness + unit tests, all green: liquidity 15, fibonacci 25, svp 12) and the fresh-export parity
re-run has now RUN:
- **liquidity — VALIDATED & COMMITTED (2026-07-07):** `compare_liquidity.py` exit 0 on a real
  month-spanning `VANTAGE_XAUUSD, 5m` export (10,543 bars, `--warmup 9137` past the June→July month
  roll so the previous-month level warms; all 33 fields match).
- **svp — VALIDATED & COMMITTED (2026-07-07):** `compare_svp.py` exit 0 on the same export
  (`--warmup 304`; all 3 fields match).
- **fibonacci Macro — RE-SYNCED but HELD (NOT committed):** the port is a faithful mirror (Python ==
  Pine exactly: 45 lock attempts, 0 held, 0 mismatches over a 20,928-bar / ~4-month export), but the
  re-pasted source change appears to **disable the macro cycle entirely** — the full-reset fires on
  the same bar the cycle locks (the top is set to the swing high price just broke, so `close>top` is
  already true on the birth bar), so the cycle never survives to a second bar and never displays. On
  ~4 months of data it never once held (pre-re-paste it held 2,502 bars). Suspected bug in
  `mpc_assistant.pine`, not the port. Awaiting Aaron + brother review before the Python change,
  `fib_export.pine`, its tests and the re-pasted `mpc_assistant.pine`/`structure_engine.pine` are
  committed.

**NEW — Internal Fib** → not extracted (see "Still to build" above).

**VALIDATED & COMMITTED (2026-07-07) — `engines/liquidity/`** (mitigation logic changed):
- Daily, Asia, London, NY and H4 mitigation **dropped the close-back guard**: was the sweep rule
  `high>lvl and close<lvl` (H) / `low<lvl and close>lvl` (L), now fires on the wick alone
  (`high>lvl` / `low<lvl`). **FIXED:** `types.py` `is_taken_by` now defines `SWEEP_HIGH/LOW` as the
  wick-only test (name kept — these are still "sweeps" in Aaron's vocabulary, just without the
  close-back filter); daily/session/H4 creation sites unchanged (they already used `SWEEP_*`).
  Weekly/monthly keep the `close`-only break rule — unchanged.
- Weekly H/L and PWC `request.security` flipped `lookahead_on → lookahead_off` — a repaint fix in the
  main indicator's display path; the engine is already non-repainting (prev-completed-period), so no
  event change. No action needed; noted for reconciliation.
- Harness `indicators/engines/liquidity_export.pine` **FIXED** (lines 50/52, 89/91, 122/124 close-back guard
  dropped). Tests updated (`test_daily_high_swept_on_wick_through`; sweep-test comments corrected).

**HELD — NOT committed (2026-07-07) — `engines/fibonacci/` (Macro / "Cycle" fib)** (reset logic changed; suspected source bug — see RE-SYNC STATUS above):
- Price closing **above the locked top** used to only HIDE the cycle (stay locked); it now does a
  **full reset** — clears dir/origin/extreme, unlocks, clears touched flags, and **restarts
  bottom-tracking** from the current bar (`macro_last_bear_sos_bar := bar_index`, `macro_ll_since_bear_sos := low`).
  **FIXED:** `MacroFib` step 5 now does the full reset (mirrors the close-below-bottom reset + a
  touched-flag wipe). Note the reset now pre-empts a same-bar HH-extend (step 5 runs before step 6
  and unlocks the cycle) — matches Pine. (Structure + Sniper fibs unaffected — their changes are visual.)
- Harness `indicators/engines/fib_export.pine` **FIXED** (full reset). Test updated
  (`test_close_above_top_resets_cycle`; the extend test now closes below the old top to isolate it).

**VALIDATED & COMMITTED (2026-07-07) — `engines/session_volume_profile/`** (MV confirm reset timing changed):
- `mv_swept` / MV confirmation now resets on **`svpNew`** (next Asia session open) instead of
  **`svpEnd`** (Asia session close) — so the confirmed/swept state now persists through the whole day
  until the next Asia session. **FIXED:** `SvpEngine` now resets on `svp_new` (`"Asia" in sess.opened`)
  instead of `svp_end`; ordering (tap check then reset) preserved (POC price + formed pulse unchanged).
- Harness `indicators/engines/svp_export.pine` **FIXED** (line 121 `if svpEnd` → `if svpNew`). Tests updated
  (`test_form_bar_confirms_when_it_straddles`, `test_swept_resets_on_next_session_open`).

**Unaffected:** `engines/market_structure/` (new `int_bull/bear_bos/sos` flags just re-expose
already-detected internal breaks for the table; detection unchanged), `engines/order_blocks/`,
`engines/sessions/`, `engines/vwap/` — only default toggles / labels changed.

Each engine fix must re-run its `compare_*.py` Pine-parity check on a fresh TradingView export
(with the matching `*_export.pine` harness updated first) before it is committed.

---

## Off-roadmap engines (not from the SMC indicator)

These do not come from `mpc_assistant.pine`, so they follow the engine *shape* (time-driven,
streaming, events-not-visuals, `algos/shared/` shim) but **not** step 3 (Pine parity) — there is no
Pine source to diff against. Validated by unit tests + a live check instead.

- **`engines/news/`** — economic-calendar (news) engine. Built 2026-07-05. Turns each bar's UTC
  timestamp into a trade **blackout** around scheduled macro releases (NFP/CPI/FOMC/PCE/ISM/EIA…),
  plus **whole-day bank-holiday** blackouts (gold can't trade holidays; futures liquidity is thin),
  plus coming-up / happening-now / just-finished phases — so a bot can veto trading during news.
  Macro calendar keyed by currency → serves FX, gold and index/rates futures (not single-stock
  earnings). Two data paths, both into one local `EventStore` cache, behind a swappable
  `CalendarSource`: **live** = the free Forex Factory / faireconomy JSON feed (current week, no deps,
  `tools/refresh.py`); **history** = scrape the FF website month-by-month past Cloudflare via
  `curl_cffi` (`tools/backfill.py`) — cached, so static months are fetched once. Honest-coverage by
  Aaron's call (2026-07-05): before the cache's earliest fetched date the filter is inert (backtest
  trades normally) and the engine exposes `coverage_start_ms` for a UI "news starts here" line.
  29 unit tests + a live feed smoke + a real Feb-2025 backfill (blacked out ISM PMI + USD Presidents
  Day), green. Full rules in `engines/news/CLAUDE.md`.
  **Follow-up (not built):** wire `coverage_start_ms` into the command-center backtest lab as a
  vertical line; add the `algos/shared/` shim when a bot first consumes it.

## Extraction complete

Every SMC block that was on this roadmap is now its own Pine-parity-validated Python engine —
Sessions, Liquidity, VWAP and SVP were the final four, all done. **There is no next engine to
extract.** Forward work is consumption (per-engine `algos/shared/` shims as bots adopt them, the news
`coverage_start_ms` backtest-lab line) and the backtest-first bot rebuild in
`docs/BOT_DEVELOPMENT_METHOD.md`.
