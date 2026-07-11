# Engine Extraction Roadmap

**Purpose:** Track which parts of the TradingView SMC indicator still need to become their own Python engines.
**Source indicator:** `indicators/mpc_assistant.pine` (full-featured SMC: structure, order blocks, sessions, kill zones, VWAP, liquidity, fibs, SVP).
**Progress:** ALL 8 SMC-port engines done (regime, market_structure, fibonacci, order_blocks, sessions, liquidity, vwap, svp) · **1 off-roadmap engine done (news / economic-calendar)** — see "Off-roadmap engines" below. The 2026-07-09 re-sync (liquidity monthly-removal + fibonacci TP3-reset-drop/extend-guard/macro-seed) is now **committed** (`d367b6d`), every engine back at 100% Pine parity. A **fresh 2026-07-10 re-paste** of `mpc_assistant.pine` (524-line staged diff) was audited: **NO engine is stale.** Every engine-affecting change is either visual (swing-label hide toggle, VWAP polyline→plot, KZ/session display windows, session-H/L input consolidation, iBOS/iSOS label reposition) or already-aligned (macro fib run-guard opened to all-timeframes tracking, which the Python engine was already doing unconditionally). **TWO NEW blocks** appeared. One is engine work (now BUILT), one is strategy work (not built): (a) **FAIR VALUE GAPS (FVG)** — a 3-candle displacement gap detector (persists until tapped, FIFO cap); a genuine event detector → **✅ built + Pine-parity-validated 2026-07-10 as `engines/fair_value_gaps/`** (12 unit tests green; `compare_fvg.py --warmup 20` exit 0 on a real `VANTAGE_XAUUSD, 5m` export). The small **`fiboHalfReached`** fib add-on (inbound 0.5 touch) was **✅ built + parity-validated into `engines/fibonacci/`** the same day (2 new tests; `compare_fib.py --warmup 1002` exit 0). **Both ready to commit with the mpc re-paste.** (b) **A+ SETUP SEQUENCE** — a stateful sweep→SOS→fib-entry machine (continuation mode, Cycle-Fib POI, FVG confluence) that **REPLACES the old SETUP GRADING candidate**; it *decides trades*, so it is **strategy-tier, NOT an engine** — it belongs in `strategies/` (MT5/NT8) or a Python bot, and now has both its engine dependencies (FVG + `fiboHalfReached`) in place. **market_structure sync chain NOT triggered** (only label colour/position changed; no detection change). See "Audit findings — 2026-07-10" below.
**Last reviewed:** 2026-07-10 (fresh re-paste audit — no engine drift; FVG engine + `fiboHalfReached` built & Pine-parity-validated, ready to commit; A+ setup remains strategy-tier, not built)

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
- **`engines/order_blocks/`** — bull/bear OB zones off external + internal breaks, with mitigation + FIFO eviction. Sibling of `engines/fibonacci/` (consumes `engines/market_structure/` directly). Ported line-by-line, 12 unit tests, 100% Pine parity on two independent real exports — `VANTAGE_XAUUSD, 5m` (`--warmup 594`) and `VANTAGE_XAUUSD, 15m` (`--warmup 207`), confirming it's timeframe-agnostic (harness: `indicators/ob_export.pine` + `engines/order_blocks/tools/compare_ob.py`). Re-validated after the 2026-07-08 structure re-sync: engine untouched, but its harness `ob_export.pine` (which embeds the structure engine) was re-synced with the two f2a8411 changes, then re-validated 2026-07-09 on a fresh `VANTAGE_XAUUSD, 5m` export (12,618 bars; all OB fields match, `--warmup 1133`, exit 0).
- **`engines/sessions/`** — Tokyo/London/NY session windows + running session H/L, the three NY kill zones, and the NY opening range. The first **time-driven** engine (input = the bar's UTC timestamp + high/low, not just OHLC); standalone (depends on nothing). Ported line-by-line, 17 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (all 18 fields, `--warmup 263`), re-confirmed on a 15m export for the 16 timeframe-agnostic fields (harness: `indicators/sessions_export.pine` + `engines/sessions/tools/compare_sessions.py`). Unblocks the session-scoped parts of Liquidity (session H/L levels) and VWAP (session anchor).
- **`engines/liquidity/`** — the prices price runs toward and grabs: prev day/week/month H/L (PDH/PDL/PWH/PWL/PMH/PML), previous-week-close (PWC), the H4 sweep (SSH/BSL), and Asia/London/NY session H/L, with mitigation (sweep vs break) tracking. Consumes `engines/sessions/` for session H/L (composes it); reconstructs the day/week/month/H4 levels from the bar stream. **Non-repainting by Aaron's explicit decision (2026-07-05): every HTF level uses the PREVIOUS completed period only — the engine never forecasts the current period's high/low.** Ported, 15 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (11,457 bars; all 33 fields — 15 level prices, their mitigation flags, 4 boundary-roll pulses — match, `--htf-rollover 18 --warmup 4653`, exit 0; harness: `indicators/liquidity_export.pine` + `engines/liquidity/tools/compare_liquidity.py`). Calibrated boundary: XAUUSD session opens 18:00 NY (baked in as the default).
- **`engines/vwap/`** — the session VWAP: a volume-weighted running mean of `hlc3` (`ta.vwap(hlc3)`), re-anchored each trading day, plus a derived close-vs-line cross. First engine to need a **volume** column in the feed (XAUUSD tick volume — what the Pine `ta.vwap` already reads). Time-driven; reconstructs the trading-day anchor directly (the **same** 18:00-NY boundary the liquidity daily level uses), so it does not compose the sessions engine. Ported line-by-line from `mpc_assistant.pine` line 852, 13 unit tests, **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (6,973 bars; both fields — VWAP value + trading-day anchor pulse — match, `--htf-rollover 18 --warmup 90`, exit 0; harness: `indicators/vwap_export.pine` + `engines/vwap/tools/compare_vwap.py`). Uses a **relative** tolerance (1e-6) because the value is a cumulative sum that drifts at float-rounding level — unlike the copied-value level engines' exact match.
- **`engines/session_volume_profile/`** — the Session Volume Profile: on each **Asia** session close, a 50-row volume profile over the session range whose highest-volume row gives the **POC** (the "MV" line), plus the MV confirmation (price straddling the POC). Composes `engines/sessions/` for the Asia window/edges (like liquidity) and needs the **volume** feed (like VWAP). Two Pine quirks ported exactly: the session-close bar is folded into the profile, and the bull/bear two-array newest-first summation is kept (float addition is not associative — collapsing it could flip a near-tie POC row). Ported from `mpc_assistant.pine` (SVP block 2554, MV slot 2772), 12 unit tests, **100% Pine parity**. The row count was re-synced **100 → 50** on 2026-07-09 (mpc line 317) and re-validated on a fresh `VANTAGE_XAUUSD, 5m` export (13,147 bars; all 3 fields — POC price + form pulse + sweep state — match, `--warmup 251`, exit 0; harness: `indicators/svp_export.pine` + `engines/session_volume_profile/tools/compare_svp.py`). The POC uses an **exact** (1e-6) tolerance — it is a deterministic formula on the copied session H/L + integer volume, so it is bit-identical, unlike VWAP's cumulative value.

---

## Still to build

- **Internal Fib** (new; found 2026-07-06, now FULLY implemented in source as of the 2026-07-08 paste) —
  a **4th fib** for `engines/fibonacci/`, anchored to INTERNAL structure (iBOS/iSOS) instead of external
  swings, with a live-updating anchor (extends to the running low/high since the internal break), the
  same 0.618 gate as the Structure fib, and a TP3-hit reset (`iFibResetActive`), cleared on any external
  BOS/SOS. Pine block `GRP_IFIB` inputs + the `INTERNAL FIB` compute/touch/draw block + the
  internal-structure anchor captures. Not covered by any engine yet. Port as `InternalFib` alongside
  `StructureFib` and add `px_ifib_*` columns to `indicators/fib_export.pine`. See "Audit findings —
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
  SETUP" table row.

- **FAIR VALUE GAPS (FVG)** — ✅ **BUILT + PARITY-VALIDATED 2026-07-10** as `engines/fair_value_gaps/`
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

- **HTF Directional Bias helper** (candidate since 2026-07-08; simplified 2026-07-10) — `f_biasState` /
  `f_htfBias`: Daily+Weekly Established Context bias (Closed[1] vs Closed[2]) with sweep detection. The
  "Current Forming" half (Live[0] vs Closed[1]) was **removed from source 2026-07-10** ("never consumed"),
  so it now returns a 2-value shape. Still feeds only the JARVIS table; no engine yet. Port the simplified
  shape if extracted (the A+ sequence could consume it as a bias filter).

Everything else is ported. The other forward work is *consumption*, not extraction: give each engine
an `algos/shared/` shim when a bot first uses it, wire the news `coverage_start_ms` into the backtest
lab, and build the backtest-first bots per `docs/BOT_DEVELOPMENT_METHOD.md`.

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
MONTHLY block + `px_pmh/px_pml(_mit)` + `px_month_roll` from `indicators/liquidity_export.pine`; dropped
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
  `indicators/fib_export.pine` re-synced to match (both TP3 setters removed, `fiboPrevAsh/Asl` +
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

**Harnesses re-synced + validated (2026-07-09):** `indicators/liquidity_export.pine` (monthly block +
`MH`/`ML` + `px_month_roll` removed) and `indicators/fib_export.pine` (both TP3 setters dropped;
`fiboPrevAsh/Asl` + `iFibPrevAsh/Asl` vars + `*ExtChanged` guards + the Macro first-bar seed added). A
single fresh combined export — both indicators on one `VANTAGE_XAUUSD, 5m` chart (13,759 bars) — validated
both: `compare_liquidity.py --warmup 1742` and `compare_fib.py --warmup 3154`, both exit 0. Ready to commit.

Each engine fix must re-run its `compare_*.py` Pine-parity check on a fresh TradingView export (with the
matching `*_export.pine` harness updated first) before it is committed. **No engine code was changed in
this audit — report only.**

---

## Audit findings — 2026-07-08 (fresh, larger re-paste of `mpc_assistant.pine`)

Working-tree diff of `indicators/mpc_assistant.pine` vs commit `de54b6b` (HEAD; its mpc copy ==
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
- Per the MOST-CRUCIAL rule these make `indicators/structure_engine.pine`,
  `indicators/structure_engine_export.pine`, AND `engines/market_structure/engine.py` STALE as one
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
  tests/test_macro_fib.py}` + `indicators/fib_export.pine` full-reset edits are now WRONG — discard and
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
`_SVP_ROWS` 100 → 50 in `engine.py`, `svpRows` 100 → 50 in `indicators/svp_export.pine`, the 12 unit tests
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
internal-reset-on-BOS change. The catch was the **harness**: `indicators/ob_export.pine` still embedded
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

Working-tree diff of `indicators/mpc_assistant.pine` vs commit `6f76bed` (its last commit). Most of
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
- Harness `indicators/liquidity_export.pine` **FIXED** (lines 50/52, 89/91, 122/124 close-back guard
  dropped). Tests updated (`test_daily_high_swept_on_wick_through`; sweep-test comments corrected).

**HELD — NOT committed (2026-07-07) — `engines/fibonacci/` (Macro / "Cycle" fib)** (reset logic changed; suspected source bug — see RE-SYNC STATUS above):
- Price closing **above the locked top** used to only HIDE the cycle (stay locked); it now does a
  **full reset** — clears dir/origin/extreme, unlocks, clears touched flags, and **restarts
  bottom-tracking** from the current bar (`macro_last_bear_sos_bar := bar_index`, `macro_ll_since_bear_sos := low`).
  **FIXED:** `MacroFib` step 5 now does the full reset (mirrors the close-below-bottom reset + a
  touched-flag wipe). Note the reset now pre-empts a same-bar HH-extend (step 5 runs before step 6
  and unlocks the cycle) — matches Pine. (Structure + Sniper fibs unaffected — their changes are visual.)
- Harness `indicators/fib_export.pine` **FIXED** (full reset). Test updated
  (`test_close_above_top_resets_cycle`; the extend test now closes below the old top to isolate it).

**VALIDATED & COMMITTED (2026-07-07) — `engines/session_volume_profile/`** (MV confirm reset timing changed):
- `mv_swept` / MV confirmation now resets on **`svpNew`** (next Asia session open) instead of
  **`svpEnd`** (Asia session close) — so the confirmed/swept state now persists through the whole day
  until the next Asia session. **FIXED:** `SvpEngine` now resets on `svp_new` (`"Asia" in sess.opened`)
  instead of `svp_end`; ordering (tap check then reset) preserved (POC price + formed pulse unchanged).
- Harness `indicators/svp_export.pine` **FIXED** (line 121 `if svpEnd` → `if svpNew`). Tests updated
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
