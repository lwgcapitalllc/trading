# CLAUDE.md — indicators/

**Purpose:** From-scratch Pine Script rebuild of the "Structure OS / SMC Engine" market-structure indicator (swing highs/lows, HH/HL/LH/LL, BOS, CHoCH), replicating a private TradingView indicator's behavior using a pullback-only detection method.
**Scope:** This covers Pine Script indicator development and the market-structure detection engine only. It does NOT cover trading strategy logic, risk management, or any live/backtest execution — this is a charting indicator, not a bot.
**Status:** Under construction — Stage 2b (break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3 (internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-07-31 — **the harness pass: four export builds validated on two real grand exports, `mpc_jarvis_v2.pine` DELETED, and the session windows forked back together.** `ob_export.pine` was REBUILT (1148 → ~300 lines — it no longer embeds the structure engine, killing this folder's worst maintenance trap) and needed a real Pine fix to compile at all: **`CE10088 — a function may READ a global but never WRITE one`**, which the export-only counters were doing inside `extendOBs` and `f_obAdd`. `fvg_export.pine` had two holes that would each have produced a misleading GREEN (6 plotted slots against a cap of 8; a flat gap floor where mpc's is timeframe-split). `mpc_b_leg_strategy.pine` + its export had **never received the DST-aware session windows** the A+ parent has carried since 2026-07-12 — a real fork, and trade-affecting in principle because session H/L feed the sweep that arms A+; both bots re-verified GREEN after the sync, and then **on a FRESH B-LEG export off the synced Pine** (`--warmup 800`, exit 0, 6,329 bars over a window sitting entirely inside BST/EDT — the half of the year where the new windows and the old ones actually disagree, so this is the run that tests the fix rather than the Python side's self-consistency). `mpc_m15_playbook.pine` and `svp_export.pine` synced too, and `compare_svp.py` re-run green (12,117 bars). Of the four edited files, three were exported from, which proves them; `mpc_m15_playbook.pine` is uncompiled and **that is fine — Aaron's call, 2026-07-31: it is his brother's work in progress, not ready, and not a validation item for this repo.** Full record in the 2026-07-31 harness-pass section below, including the line-targeted-edit warning (the old Tokyo and New York values collide, so a global string replace corrupts them) and **the harness bug the first PARTIAL export exposed: `bl_*_bar` carries Pine's chart-relative `bar_index`, so `compare_bleg.py` was comparing two different coordinate systems and had only ever been right by the accident of full-history exports.** Earlier: 2026-07-30 — **`mpc_strategy_export.pine` REGENERATED off the parent, closing the last surviving drift.** It had no `execMinStopMode`/`execMinStopVal`, so the moment that filter was switched on the export stopped describing the strategy and `compare_strategy.py` would have reported GREEN while diffing a config it could not read. The regen followed the file's own documented procedure (`sed -n '1,4581p' mpc_strategy.pine` + the appended PARITY EXPORT block, then restore the line-29 title) and **`diff` over the shared range is now exactly one line — that title**. Two new columns carry the filter: `cfg_min_stop` (`Off?0 : % of price?1 : Fixed $?2 : x ATR(14)?3`) and `cfg_min_stop_val` (raw float, same reason the exit numerics are raw — a packed float that rounds mis-configures the bot silently). Deliberately NOT folded into `cfg_exitmode`: that column is the two EXIT dropdowns, and this is an ENTRY filter. The Python side was ported in the same pass (`strategies/python/mpc_sos_fade/CLAUDE.md` → `### The minimum-stop guard`), including block reason **code 7**, which the parent already emitted and nothing downstream could see. ⚠ **The filter is still unproven ON against a real export** — every green in this file was taken at the `"Off"` default, where the gate is inert and both sides are byte-identical to their previous build. Re-paste and re-export before trusting a run made with it on. ⚠ `mpc_b_leg_strategy.pine` still has no min-stop input at all (deliberate — a B leg's stop is its band ORIGIN, a full band from the entry, so the hazard is structurally absent); its Python fork pins the mode `"Off"` to keep that honest. Earlier: 2026-07-29 — **`aplusWindow`'s `maxval` raised 4320 → 20160 (14 days) in the A+ pair only** (`mpc_strategy.pine`, `mpc_strategy_export.pine`). The bug it fixes is worth knowing because the pattern can recur on any input: **the old ceiling EQUALLED the default**, so the field could only ever be lowered, and TradingView silently CLAMPS a typed value to `maxval` as you type — entering 4800 left the box showing a truncated number with no error, which reads as a broken input rather than a cap. Default is unchanged at 4320, so **no backtest and no parity run moves**, and the Python side (`aplus_window`) never had a cap so nothing there needed changing. **The export was raised in lockstep** — it must be able to carry any value the parent can produce, or a parity export taken at a longer window would silently be clamped to a different strategy. ⚠ `mpc_b_leg_strategy.pine` + its export and `mpc_bos_strategy.pine` / `mpc_m15_playbook.pine` still cap at 4320 (same default-equals-ceiling trap); raise them the same way if that window is ever swept there. Earlier the same day: **both strategy pairs re-validated GREEN, and both parents compile in TradingView.** `mpc_strategy.pine` and `mpc_b_leg_strategy.pine` were pasted in and compiled clean (the CE10117 token-cap worry did not materialise — no tooltip trimming needed). Fresh exports off `mpc_strategy_export.pine` (21,494 bars) and `mpc_b_leg_strategy_export.pine` (21,493 bars), both 2025-08-31 → 2026-07-29: `compare_strategy.py --warmup 100` → exit 0, `compare_bleg.py --warmup 100` → exit 0, and both hold at warmup 200/500/1000/2000. The A+ export carried `cfg_tp1_pct = cfg_tp2_pct = 0`, `cfg_exitmode = 20` (the 3-way trail digit decoding as the ratchet) and `cfg_trail_pct = 1` — i.e. the ratchet plumbing is proven through the export, not just present in it. **Every "STALE" warning below is CLEARED.** ⚠ **The one drift that survived that pass** — `mpc_strategy_export.pine` lacking `execMinStopMode`/`execMinStopVal` — **was closed 2026-07-30** (see the entry above). Those green runs were taken at the `"Off"` default where the gate is inert, so they still describe the current build exactly, and they still say nothing about the filter itself. Earlier: 2026-07-28 — **the swing ratchet landed in the A+ pair FIRST** (`mpc_strategy.pine` + `_export`), which is what the B-LEG entry below then caught up to: `execRunnerTrail` gained `"Structure + % ratchet"` and **now defaults to it**, with `f_swingRatchet()` and the `execTrailPct` child input (1.0%). It fixes the runner's give-back — the plain structure trail parks the stop at a LAGGING swing, so a strong leg hands back the gap between that swing and the high (measured 57% on the trades that ran ≥$10 of gold); the ratchet climbs one %-of-price step per step of favourable move and is never LOOSER than the plain trail, only equal or tighter. Export side: `cfg_exitmode`'s tens digit went 2-way → **3-way** and `cfg_trail_pct` was added — without both, the comparator would diff a ratcheted Pine against a non-ratcheted Python and report pure drift as a bug. ⚠ **The A+ export is now STALE: the 2026-07-27 GREEN parity run predates the ratchet, so it validates nothing about this build.** Re-run `compare_strategy.py` on a fresh export before trusting any A+ number from it — and run it at `execTp1Pct = execTp2Pct = 0` (the shipped rungs), because the 109.3R figure quoted for the ratchet was measured at 1%/1%; the true 0/0 baseline is **110.65R**. ⚠ **Pre-existing drift, NOT introduced by the ratchet:** `mpc_strategy_export.pine` lacks `execMinStopMode`/`execMinStopVal`, which the parent has. Inert at the `"Off"` default (the floor is 0.0, so the gate is always true) so parity holds today — but the moment minimum-stop-distance is switched on, the export stops describing the strategy and any parity result from it is meaningless. Close it before using that filter. Extension-fib take-profits on top of the ratchet were measured and REJECTED the same day; the full record is in `strategies/python/mpc_sos_fade/CLAUDE.md` → `### The swing ratchet`, and the short version is that 11 trades past the −0.618 extension carry 106R of the 109R, so any fixed ceiling caps exactly what pays. Earlier the same day — **the B-LEG pair now runs the SAME exit ladder as the A+ pair** (`mpc_b_leg_strategy.pine` + `_export`). Three changes, all ported line-for-line from `mpc_strategy.pine`: (1) `execTp1Pct`/`execTp2Pct` defaulted **30/40 → 0/0** — bank nothing, ride the whole position to the runner; (2) the **`qty_percent = 0` guard** — `strategy.exit()` reads 0 as "unspecified" and closes the WHOLE position at that limit, so a 0 rung is now SKIPPED rather than placed. That is why typing 0 previously blew the trade out at TP1 instead of banking nothing, and it is a real hazard, not a cosmetic default; (3) `execRunnerTrail` gained the third option **"Structure + % ratchet"** and now DEFAULTS to it, with `f_swingRatchet()` and the new `execTrailPct` child input (1.0%, greyed unless that method is selected). ⚠ **All three MOVE B-LEG results** — the rungs, the 0-guard and the trail default each change what a runner banks; nothing here is cosmetic. ⚠ **The 43% → 53% run-capture measurement behind the ratchet default was taken on the A+ file's own trades, NEVER on B legs** — it is inherited so the two forks share ONE ladder, not because it is a proven B-LEG result; sweep it before treating it as tuned. Export side: `cfg_exitmode`'s tens digit went from a 2-way to the A+'s **3-way** code (it used to collapse everything non-fixed to 1, which would have decoded the ratchet as the plain structure trail), and `cfg_trail_pct` was added. Python side, same commit: `mpc_bleg/config.py` DROPPED its `exec_runner_trail` pin (it existed only because this Pine lagged the parent), and `mpc_bleg.meta.json` gained the third choice + the `exec_trail_pct` row. The B-LEG exec-input gap vs A+ is now **three** levers, not four (`execSlLevel`, `execMinStopMode`, `execMinStopVal`). 98 Python tests green. **Not yet re-validated against a fresh export — `compare_bleg.py` must be re-run before any B-LEG number from this build is trusted.** Earlier the same day: **every Strategy Execution input in all FOUR strategy Pine files now lives in ONE consolidated block near the top of the file** (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export` — search `STRATEGY EXECUTION INPUTS`). All four carry the SAME eight sections in the SAME order; the B-LEG pair simply has fewer levers (no `execSlLevel`, no `execMinStopMode`/`execMinStopVal` — `execTrailPct` was in this list until the exit-ladder port later the same day), so its block is the A+ block minus those three. Ordered the way a trade happens (what trades → what arms it → where the limit rests → what can refuse it → size and stop → targets → runner → drawing), with each dependent input prefixed `↳` and carrying `active = <its parent>` so it greys out when irrelevant. **The block had to MOVE, not just be reordered:** panel order is declaration order, and two inputs (`execConfSZ`, `bLegMaxDays`) are read by engine code ~3,000 lines above the old block, so Pine forced them to be declared early — which stranded them at the TOP of the Execution panel, above "Trade Longs". **NO logic changed** — same inputs, same defaults, same reads; only declaration order, label text and `active =` gates. ⚠ **Reordering inputs resets saved TradingView settings** (TV maps them by position), so re-paste and click "Reset settings to defaults" once — cheap now that the defaults equal what Aaron trades. Three traps found while doing it, all now documented in the block's own header comment: (1) `execTrailStep` has TWO masters — `Fixed step` mode AND the `One trail step behind` TP2 floor — so it is deliberately NOT greyed by the trail method; (2) the three FVG entry rules still price an entry with `execReqFVG` OFF (that toggle only ADDS a 0.618 fib fallback), so they are siblings, not children; (3) `execMinStopMode` is an ENTRY filter and has nothing to do with the runner trail — the two never interact. **Standing rule: a new execution input goes in that block, in its section, with `active =` if anything can make it irrelevant.** `active` needs a pure INPUT bool, so never reassign one of these with `:=`. Earlier: 2026-07-27 — `execSlLevel` defaulted **"1.0" → "0.886"** in both A+ Pine files (`mpc_strategy`, `mpc_strategy_export`) to match `config.py` and what Aaron trades; the B-LEG pair deliberately keeps "1.0" (its Python fork pins the same). This MOVES the stop, so it changes every A+ trade's size and R — it is not cosmetic. Parity is unaffected: the export emits the level in `cfg_strcodes` and `compare_strategy.py` configures Python from that, so the harness never reads either side's default. Earlier the same day: `execRiskPct`'s `maxval` raised **10 → 100** in all four strategy Pine files (`mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`, `mpc_b_leg_strategy_export`); default stays 10, sizing math untouched, so no backtest moves. The old 10 was a UI cap only — the Python `exec_risk_pct` never had one. Note the `margin_long/short = 0.2` pin (500x) still bounds notional at 5x equity, so a high risk % on a tight stop can be rejected or partially filled by the tester with no error. Earlier the same day: `execTp1Pct`/`execTp2Pct` defaulted 30/40 → **0/0** in both A+ Pine files, with the `qty_percent = 0` guard that makes 0 mean "bank nothing" instead of "bank everything"; parity re-validated GREEN on a 21,320-bar export at SL 0.886 + 0/0 (see the 2026-07-27 entry). Earlier: 2026-07-26 — the new exit levers (structure runner trail, TP2 stop floor, SL fib dropdown, `execAplus`) ported into `mpc_b_leg_strategy.pine`, and `mpc_strategy_export.pine` given a column for every trade-affecting input (see the second 2026-07-26 entry). Earlier the same day: orphaned-SVP compile fix in `mpc_strategy.pine` + the export regenerated off it. Earlier: 2026-07-12 — the whole structure chain was re-synced to the `choch_lock` removal in `mpc_assistant.pine` and re-validated at 100% Pine parity (see the "2026-07-12 structure re-sync" note below), and the A+ divergence retro-link landed in both A+-carrying files (see the note after it).

---

## Key paths & entry points

- `indicators/smc_engine_v2.pine` — the current pullback-only rewrite (v6 Pine Script), overlay indicator named "SMC Engine"
- `indicators/STRUCTURE_OS_BUILD.md` — cross-session handoff doc: architecture, design decisions, validation findings, build-stage status. Read this first when resuming work.
- `docs/market_structure_engine_spec.md` — the source-of-truth rules spec, written from the TradingView overview page. `STRUCTURE_OS_BUILD.md` treats this as priority-1 source of truth.
- `indicators/mpc_assistant.pine` — a full-featured SMC indicator (structure + order blocks + sessions + kill zones + VWAP + liquidity levels + fibonacci + SVP) that Aaron sourced separately. Its market-structure logic is pivot-seeded (`ta.pivothigh`/`ta.pivotlow`) rather than pullback-only, which breaks the rule below — but it matches the original "Structure OS" indicator at ~99.99% parity. Treat it as read-only reference; don't merge its approach into `smc_engine_v2.pine`.
- `indicators/structure_engine.pine` — a straight extraction of *only* the market-structure logic (external ASH/ASL/BOS/CHoCH/HH/HL/LH/LL + internal iSH/iSL/iBOS/iSOS) from `mpc_assistant.pine`, with every other feature (OBs, sessions, kill zones, VWAP, liquidity, fibo, SVP) stripped out. Same pivot-seeded approach as `mpc_assistant.pine`, so same exception to the no-pivot rule below. Chart-validated by Aaron; now ported to Python as the canonical `engines/market_structure/` subsystem (imported by `algos/` bots). **Re-synced 2026-07-11 so its drawing/visibility layer is byte-for-byte identical to `mpc_assistant.pine`'s structure block** — same "Market Structure" input group (Structure Label Size, Show External / Internal / Historic-Internal Structure, Show Swing Point Labels), same `f_swingCol`/`f_structSize` gating, same historic-internal wiping, so every label and line overlaps the MPC assistant exactly. The re-sync touched only drawing/visibility — the state machine is unchanged, so `engines/market_structure/` and `structure_engine_export.pine`'s plot columns are unaffected and need no re-validation.
- `indicators/fib_export.pine` — instrumented build for the FIB parity check: the external **and internal** structure engine (copied from `structure_engine_export.pine`, plus the mpc capture lines the fibs need — `i_confirmed_*` and the `iFib_*` seed anchors) + the Structure, Sniper, Macro AND Internal fib blocks lifted from `mpc_assistant.pine` (compute + state machines; drawing removed) + `px_fib_*`, `px_sniper_*`, `px_macro_*` and `px_ifib_*` `plot()` columns. Used to export a CSV that `engines/fibonacci/tools/compare_fib.py` diffs Python-vs-real-Pine. **Re-synced 2026-07-09** (TP3 reset-latch dropped + extend-changed guard added on Structure+Internal, Macro first-bar seed) and re-validated at 100% on a fresh `VANTAGE_XAUUSD, 5m` export (13,759 bars, `--warmup 3154`, exit 0 — Structure+Sniper+Macro+Internal). Do not let any part drift from its source (`structure_engine.pine` / `mpc_assistant.pine`).
- `indicators/structure_engine_export.pine` — instrumented copy of `structure_engine.pine` (logic byte-for-byte identical; adds `plot()` output columns, including the eight break-leg columns `px_bull_bos_high/low` + `px_bull_bos_h_ago/l_ago` and bear mirror added 2026-07-02). Used only to export a CSV from TradingView for the Python↔Pine parity check in `engines/market_structure/tools/compare_tradingview.py`. That check passes at 100% on the `OANDA_XAUUSD, 15m` export (21,729 bars, exit 0) and was re-confirmed on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars, `--warmup 227`, exit 0) after the break-leg columns were added. Do not trade off it or let its logic drift from `structure_engine.pine`.
- `indicators/ob_export.pine` — instrumented build for the ORDER-BLOCK parity check. **REBUILT 2026-07-31 (1148 → ~300 lines): it no longer embeds the structure engine at all.** Every order block used to be born on a BOS/SOS/iBOS/iSOS, so this file had to carry a byte-for-byte copy of the structure engine and be re-synced whenever that changed — its single biggest maintenance trap (it silently went stale twice). The mpc rework commented out all four structure creation sites, so blocks now come from `ta.pivot(2,2)` TURNS alone and the structure engine is simply gone from here. Invisible boxes are KEPT (`color(na)`) because `extendOBs` reads `box.get_left` for its age check, which is what lets the port stay byte-identical instead of paraphrased. Carries nine `cfg_ob_*` columns so `compare_ob.py` configures the Python engine FROM the export, plus 10 array slots per side. **Pine-parity GREEN 2026-07-31** (21,691-bar 15m export, `--warmup 798`, exit 0; and 13,186-bar 5m, `--warmup 326`). ⚠ **It did not compile on the first paste** — `CE10088: cannot modify global variable in function`. Pine lets a function READ a global but never WRITE one, and the export-only counters were being incremented inside `extendOBs` AND `f_obAdd`. `extendOBs` now RETURNS its mitigation count and the creation counters are bumped at `f_obAdd`'s call sites. **Remember this shape for any future harness: per-bar instrumentation counters cannot live inside a Pine function.**
- `indicators/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). Its `process()` state machine is byte-identical to `mpc_assistant.pine`'s — verified by diff, keep it that way. **Sync direction reversed 2026-07-21: the REPO is now the source of truth** — Aaron pastes this file up to TradingView and his brother picks it up, so repo-side edits stick. (It used to flow the other way, which is why older notes warn about TradingView edits silently reverting fixes.) There is no local Pine compiler: validation is pasting into TradingView, checking it compiles, and confirming the Strategy Tester numbers are unchanged.
- `indicators/mpc_b_leg_strategy.pine` — a FORK of `mpc_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the A+ bot. The ONLY logic change vs the parent is the execution layer: the two A+ `strategy.entry` blocks are replaced with cancel-only stand-down (`longArmed`/`shortArmed` are still computed so the "A+ has priority" gate on the B leg is preserved), and the B LEG is the sole entry type. The whole engine + A+ sequence tracker above the execution block stays byte-identical to `mpc_strategy.pine` — do not let it drift. **Leaned out 2026-07-24** (4871 → 4573 lines): the code that went dead when A+ entries were disabled (`f_conf`, `f_slAnchor`, the `execSlLevel` input, `longDeep`/`shortDeep`, `longEdgeSz`/`shortEdgeSz`) plus three self-contained cosmetic subsystems the B leg never reads and that default OFF (VWAP, Session Volume Profile/MV, Order Blocks) were removed. Python port lives in `strategies/python/mpc_bleg/` (its own CLAUDE.md). Same no-local-compiler rule: validate by pasting into TradingView. **No Pine↔Python parity harness yet** — a `mpc_b_leg_strategy_export.pine` + `compare_bleg.py` are the follow-up.

---

## 2026-07-31 — the harness pass: four exports validated, one file deleted, session windows finally forked back together

**`indicators/mpc_jarvis_v2.pine` DELETED** (Aaron's call). It was a 2,084-line lean `indicator()`
build superseded by `mpc_strategy_export.pine`. Last committed at **`825592a`** — recover from there,
never from memory. All doc references removed in the same pass.

**The session windows were forked and nobody had noticed.** `mpc_strategy.pine` has carried the
DST-aware windows since **2026-07-12** (`317dbef`) — two weeks BEFORE `mpc_assistant.pine` got them
(`b25789d`, 07-26) — but `mpc_b_leg_strategy.pine` and `mpc_b_leg_strategy_export.pine` never did, so
the A+ and B-LEG forks disagreed about when a session opens. That breaks this file's own standing
rule: an engine-block change in the parent flows to the fork line-for-line.

| | old (fixed offset) | new (own city, DST-aware) |
|---|---|---|
| Tokyo  | `2000-0500` GMT-4 | `0900-1800` **Asia/Tokyo** |
| London | `0400-1300` GMT-4 | `0800-1700` **Europe/London** |
| New York | `0900-1800` GMT-4 | `0800-1700` **America/New_York** |

**It is trade-affecting in principle, not cosmetic** — session H/L feed `recentBSL`/`recentSSL`
(`mpc_strategy.pine:3121-3126`), which is what `execArmSweep` arms A+ on, and that toggle is ON in the
shipped prime combo. The path is narrow (`showSessH = liq_dh == ""` makes session levels a FALLBACK
used only when no day level exists) but narrow is not none. **Measured, not assumed: neither bot
moves** — `compare_strategy.py --warmup 100` and `compare_bleg.py --warmup 100` both still exit 0.

**Then proven on a FRESH export, which is the run that actually tests the fix.** The paragraph above
was measured against the 2026-07-29 B-LEG export, taken off the Pine *before* its windows changed — a
green there says the Python side is self-consistent, not that the sync is right.
`compare_bleg.py "VANTAGE_XAUUSD, 15_cabec.csv" --warmup 800` → **exit 0**, 6,329 bars,
2026-04-27 → 2026-07-31. **The window matters more than the bar count here:** it sits entirely inside
BST/EDT, which is the half of the year where the new city-clock windows and the old fixed GMT-4 ones
genuinely disagree (New York `0800-1700` America/New_York = 12:00–21:00 UTC under EDT, an hour earlier
than the old `0900-1800` GMT-4). A stale Python side would have disagreed with Pine on every session
boundary in this export. `svp_export.pine` was re-exported in the same pass and `compare_svp.py
--warmup 317` exits 0 on 12,117 bars, so the "re-expression, not a behaviour change" claim about Asia
is now measured too.

⚠ **Compile status after that pass, stated exactly.** `mpc_b_leg_strategy_export.pine` and
`svp_export.pine` both compiled — Aaron exported from them, which is stronger evidence than a paste.
`mpc_b_leg_strategy.pine` is body-identical to its export apart from the line-40 title, so it is
covered by construction. **`mpc_m15_playbook.pine` has never been pasted since its windows were
edited, and is deliberately left that way** — Aaron's call, 2026-07-31: it is his BROTHER's work in
progress, not ready and not part of this repo's validated set. Do not raise it as an open validation
item. The changes there were value-only, so if he does compile it and something breaks, it is one of
the six session strings.

Synced in `mpc_b_leg_strategy.pine`, `mpc_b_leg_strategy_export.pine` and `mpc_m15_playbook.pine`
(each file's own `display = display.none` preserved — only the six values changed).
⚠ **`mpc_m15_playbook.pine`'s NY window was `0900-1700`**, unlike every other file's `0900-1800` — a
pre-existing difference of unknown origin, now folded into the common `0800-1700`. Nothing replays
that file, but it is his BROTHER's in-progress file, so if that hour was deliberate it is his to
judge — mention it to him rather than assume the sync was right. `svp_export.pine` was re-stated too, purely for
consistency: `"2000-0500" GMT-4` and `"0900-1800" Asia/Tokyo` are the SAME 00:00-09:00 UTC window all
year, which is exactly why `engines/session_volume_profile/` needed no code change.

**Do this as a line-targeted edit, never a global string replace.** In these files the OLD Tokyo value
(`"2000-0500"`) and the OLD New York value (`"0900-1800"`) collide with the NEW Tokyo value, so a naive
substitution rewrites Tokyo and then immediately overwrites it again when the New York rule runs.
Anchor every edit on its `*_SESSION_GROUP`.

### `fvg_export.pine` — two holes that would each have produced a MISLEADING green

1. **It plotted 6 array slots against a cap of 8**, so gaps 7 and 8 were live in Pine and invisible to
   the diff — every earlier FVG "exit 0" covered the oldest six only. Now 10 slots, `fvgMaxCount`
   capped at 10 to match, and `compare_fvg.py` REFUSES an export whose `cfg_fvg_maxcount` exceeds the
   plotted slots rather than reporting partial coverage.
2. **Its minimum-gap floor was one flat number** while mpc's is timeframe-split
   (`mpc_assistant.pine:410-412`: `0.0` below 900s, `0.04` at 15m+). Exported on 15m the old build
   would still have gone GREEN — both sides read the setting from `cfg_fvg_thresh` — while running a
   DIFFERENT rule from the indicator it mirrors. It now carries `fvgThreshLTF`/`fvgThreshHTF` and the
   same `timeframe.in_seconds() < 900` ternary; `cfg_fvg_thresh` plots the EFFECTIVE value, so the
   comparator needed no change. Proven both ways: the 15m export read back **0.04**, the 5m **0.0**.

### The four harnesses, validated on two grand exports

`sessions_export.pine`, `liquidity_export.pine`, `ob_export.pine` and `fvg_export.pine` were put on
ONE chart and exported together — 146 columns, **no column-name collisions between the four**, so all
four comparators run off a single CSV. Both runs exit 0 on every check:

| export | bars | window | note |
|---|---|---|---|
| `VANTAGE_XAUUSD, 15m` | 21,691 | 2025-09-01 → 2026-07-31 | spans **four DST changeovers** — the real test of the window re-sync |
| `VANTAGE_XAUUSD, 5m` | 13,186 | 2026-05-27 → 2026-07-31 | covers the NY opening range, which is a ≤5m feature |

**Take the DST-spanning export on the COARSER timeframe.** TradingView caps an export near 20k bars,
so 15m spans a changeover and 5m may not — the opposite of the instinct to always export fine.
`sessions_export.pine` is the one harness that needs both: everything in it is timeframe-agnostic
except the NY opening range, which reads a 5-minute `request.security`. `compare_sessions.py` now
measures the export's bar interval, warns before running, and takes `--skip-nyr` (printing a **NOT
CHECKED** line on success as well as failure).

---

## 2026-07-31 — `mpc_bos_strategy.pine` defaults now ENCODE the spec, not the bare baseline

**Aaron's spec, stated 2026-07-31:** SOS opens the regime → a BOS with **clean displacement** → that
break **leaves an FVG** → price retraces into **0.5-0.886** and taps the gap. The **Sniper Zone is
optional** (it may price a leg that had no qualifying gap; it is never waited for). The **daily does
NOT have to agree** — no HTF bias gate.

**Four defaults flipped to carry it:** `bosUseFvg` OFF→**ON**, `execReqFVG` OFF→**ON**,
`bosMinDispAtr` 0.0→**0.5**, and `execConfSZ2` stays ON (that is what makes the zone an optional
stand-in rather than a requirement). `execHtfWeekly`/`execHtfDaily` stay **"Ignore"** by explicit
decision, now written on the daily tooltip so nobody "fixes" it later.

**Why the old defaults were not the target.** The file shipped with every filter and every entry
confirmation OFF so the run measured the raw BOS idea. That is a MEASUREMENT baseline. The standing
direction for this strategy is **quality over quantity — the confluences ARE the quality lever**, and
frequency comes from stacking A+, B-LEG and this one on one account, never from loosening this one.
Reading the old defaults as "keep it loose, it takes more trades" inverts the intent. The filters that
are still open questions (F1/F3/F4/F5/F6/F8) stay OFF, to be turned on one at a time and judged on
expectancy and drawdown — **not on how many trades survive.**

**⚠ 0.5 ATR is the spec expressed as a number, NOT a measured optimum.** No run has been taken at any
displacement value. Sweep 0.25 / 0.5 / 1.0 and set it from results. Same warning on its tooltip.

**⚠ EVERY NUMBER IN THIS FILE'S HEADER DESCRIBES THE OLD DEFAULTS.** The 365-day / 13-trade / −2.65%
figure and the F4 design-conflict finding were measured on the previous configuration and say nothing
about this one. The header keeps them, labelled as the previous baseline.

**No logic changed — inputs, defaults and comments only.** `bosEntryFib` is now INERT at the shipped
defaults (with a gap required, the plain-fib fallback at the bottom of the entry ladder is never
reached); its tooltip says so. The entry ZONE is not set by that dropdown — the gap edge is clamped to
0.5 at the shallow end and a gap outside 0.5-0.886 is refused, which is where the band comes from.
**Not compiled on TradingView yet** (no local Pine compiler), and there is still no export Pine, no
`compare_bos.py` and no Python port — so nothing here is parity-checked.

---

## 2026-07-29 — the FVG floor is now SPLIT BY TIMEFRAME (A+, its export, and BOS)

**The bug Aaron found.** `mpc_assistant.pine` draws fair value gaps on a 5m chart
that `mpc_strategy.pine` does not. Cause: the assistant's minimum-gap floor is
timeframe-aware and the strategy's was one flat number.

```pine
// mpc_assistant.pine:149-151
float fvgThreshLTF = 0.0
float fvgThreshHTF = 0.04
float fvgThreshPct = timeframe.in_seconds() < 900 ? fvgThreshLTF : fvgThreshHTF
```

The strategy had `input.float(0.1, "FVG Min Gap (% of price)")` — 0.1% at every
timeframe. **A %-of-price floor does not scale down.** 0.1% of gold at $3,300 is
$3.30 of gap, which is wider than most WHOLE 5m bars, so a single flat floor
silently erased nearly every low-timeframe gap. A second, smaller difference
stacked on it: the assistant has `fvgRequireClose = false` everywhere, while the
strategy HARDCODED the middle-bar close-cleared test on.

**What landed.** Both are now split at the same 900-second boundary, in
`mpc_strategy.pine`, `mpc_strategy_export.pine` and `mpc_bos_strategy.pine`:

| | below 15m | 15m and above |
|---|---|---|
| min gap | `fvgThreshLTF`, default **0.0** | `fvgThreshHTF`, default **0.1** |
| middle-bar close test | forced **off** | `fvgReqCloseHTF`, default **on** |

**15m and above is bit-identical to before, deliberately.** The HTF floor stays
0.1 and is NOT set to the assistant's 0.04, and the close test stays on. A+ is
traded on 15m, so its baseline, its 188-trade history and the `mpc_sos_fade`
parity pin (`EngineConfig.fvg_require_close = True`) must not move. Matching the
assistant at 15m too is a one-number change if it is ever wanted — but it is a
different decision, with a re-validation attached, and it was not made here.

**Consequence to carry.** These are new trade-affecting inputs and
`mpc_strategy_export.pine` has no `cfg_*` column for either. At their defaults on
15m that costs parity nothing (behaviour is unchanged), but **a parity run taken
on a sub-15m chart, or with either input tuned, is meaningless until the columns
land here and in `compare_strategy.py`.** Same trap as `execRunnerTrail` in the
2026-07-26 entry: a default that changes behaviour is as dangerous as a new
input, and it hides better.

**NOT applied to `mpc_b_leg_strategy.pine` / `mpc_b_leg_strategy_export.pine`.**
They carry the identical FVG block and are now the only strategy files without
the split. The standing "engine changes flow line-for-line to the fork" rule says
they should get it; it was left out only because the request scoped A+ and BOS.

**Pre-existing drift found while checking this, NOT caused by it.**
`mpc_strategy_export.pine` is missing `execMinStopMode` / `execMinStopVal`
entirely — the min-stop lever landed in the parent (`7603444`) and never reached
the export. That breaks the export's own "the title is the ONLY difference" rule.
A parity run replays the bot with a floor the export cannot describe; harmless
while the mode is "Off" (the default), wrong the moment it is not.

---

## 2026-07-29 — `mpc_bos_strategy.pine`, the third strategy off the shared engine

**New file `indicators/mpc_bos_strategy.pine`** (3875 lines), built to `docs/MPC_BOS_SPEC.md`. It
trades the CONTINUATION: an SOS sets a regime, and every BOS after it in that direction is a fresh
leg whose retrace is bought/sold. A+ fades the shift; this rides what the shift started.

**How it was assembled.** Engine block = **lines 1-3028 of `mpc_strategy.pine`, byte-identical**
(everything through the liquidity `recentSSL`/`recentBSL` block), then the watermark, then a new
execution layer. **Not copied:** the A+ SEQUENCE tracker, the B-LEG tracker, the missed-setup callout
and its `MissW` machinery — nothing here reads them, and the compile-token budget in this family has
already hit CE10117 and CE10295 twice. Net effect vs the parent: ~510 lines of tracker out, ~250 of
execution in. Regenerate with `head -3028 mpc_strategy.pine`, the parent's watermark block, then this
file's execution layer.

**Two default flips vs the A+, both named in the spec:** `execConfSZ` OFF→**ON** (the Sniper Zone is
entry method 3 here) and `execFvg50` OFF→**ON**. Note `execConfSZ` also gates `_snTrack`, and
`_snBullBOS`/`_snBearBOS` sit behind `showFibo` — so **"Show External Fib" is still trade-critical**
in this file even though the fib LEVELS are no longer read off it (see below).

**The levels are computed, not read.** The entry band, stop and targets come from `f_lvl(ext, org, v)`
over the anchor leg's own extreme/origin — identical arithmetic to the engine's `fiboP*`, just
anchored per-setup. `bosFibAnchor` picks the EXPANSION leg (default — `fibo_ash`/`fibo_asl`, the drawn
External fib's own anchors, so the band moves until the pullback confirms) or the frozen BREAK leg
(`bos_high`/`bos_low`). This is what makes the "Break leg" option possible at all; the A+ could only
ever price off the one drawn fib.

**Three deviations from the spec, all flagged in the file header and in the spec's new §10a.** The
important one: **`fibo7Touched` is re-implemented per-anchor.** The engine's latch is keyed to the fib
ORIGIN, which does not change across a run of breaks, so break #1's round trip would have killed
breaks #2 and #3 on their arm bar — every continuation after the first would be untradeable. The Pine
tracks the anchor's own 0.5 tap and its own return to 0.0 instead. The other two: the divergence
CLOSE fires on a confirmed divergence only (not extreme RSI — that is the normal state of a healthy
long, and closing on it flattens the runner on every winner), and `execMinStopMode`/`execMinStopVal`
are carried over from the A+ though §8 does not list them (default Off, so the baseline is unmoved).

**Not yet compiled on TradingView and not yet backtested.** There is no local Pine compiler; the file
is statically checked only (no identifier collisions with the engine block, every referenced engine
symbol present, no duplicate declarations or input titles). **No number in this repo describes this
strategy yet** — §10 steps 2-4 (baseline + the F1→F4→SL-model sweeps, the export Pine +
`compare_bos.py`, the Python port under `strategies/python/mpc_bos/`) are all open.

**Standing rule, same as the B-LEG fork:** any change to the engine block flows in line-for-line from
`mpc_strategy.pine`; any BOS execution change flows to the Python port once it exists.

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

## 2026-07-22 — `mpc_strategy.pine` readability pass + compile-budget cuts

The trade annotations were rebuilt so a chart can be read without decoding text, and two features were deleted to get back under Pine's compiled-token cap.

**Removed to buy tokens (CE10117: 100543 > 100256).**
- **Kill Zones & NY Range** — the whole input group, the `security` call, the boxes/plotshapes and the today-deletion logic. Both were cosmetic, default OFF, and read by nothing in the execution layer. They still live in `mpc_assistant.pine` if the drawing is ever wanted back. `nyHour` was KEPT — `lateDayBlock` reads it.
- **`debugMarkNoFvg`'s on-chart labels** — they duplicated the missed-setup callout, which already names FVG as the missing confluence. The COUNTERS (`missedNoFvgL/S`) stay; the diagnostic log still reports every one.

**Trade drawing, rebuilt.** A trade scales out in up to three pieces, so one box can never describe it. On close it now paints as stacked bands, each the slice of price one piece was actually paid for: entry→TP1 fill, TP1→TP2, TP2→runner, in three depths of the SAME green. A faded red band behind them shows how far price went against the trade first. A trade that banked nothing is one red band; one that came back to entry is a lone orange line. Every band comes from `strategy.closedtrades.exit_price()` — the real fill, never a fib level it merely aimed at. TP1/TP2/TP3 tags all anchor at the same x (the trade's right edge + 4) so they stack in one column instead of scattering across the candles.

**Result colours, not direction colours.** Aaron reversed an earlier call: the trade label is GREY while the trade is open (the result is not known yet), then green won / red lost / orange breakeven on close. Direction stays readable via the ▲/▼ arrow, the word LONG/SHORT, and the entry triangle. Breakeven is graded against `execBeBandR`, the same band the diagnostic log uses.

**Two new inputs.** `execLabelWhich` filters which results KEEP their label (All / Wins only / Losses only / Losses + breakevens / None) — the review view is losses + breakevens. `execLabelOff` sets the label's distance from price in ATRs. That second one exists because **Pine has no tooltip-positioning API**: TradingView anchors a tooltip to its label, so pushing the label further out is the only way to stop the tooltip covering the candles. Also note **tooltips exist only on `label`, never on `box`** — a result rectangle can never be hovered, which is why the annotation is a label with a leader line rather than text on the box.

**A regression worth remembering.** Trade labels were briefly gated behind `debugDays` (the missed-setup recency window), which silently deleted every trade label older than 3 days. `debugDays` now applies ONLY to the missed-setup callouts — every real trade always gets its label, however old.

### Pine gotchas this pass exposed

- **`to` cannot be a parameter name.** It is the `for i = 0 to n` keyword. Using it makes the parser reject the whole declaration and blame the FIRST parameter (`CE10156: Syntax error at input "x1"`), which points nowhere near the real cause. `from` is fine on its own but was renamed alongside it.
- **A function's last statement is its return value, and every branch of it must share a type.** `f_posBox`'s closing `if / else if / else` creates a box / a box / a line, which is `CE10235`. Fixed by putting a trailing `int _pbDone = 0` after the chain so the drawing is no longer the return expression — remove that line and the script stops compiling.
- Both of these are the same family as the existing `CE10295` workaround (wrap a big block in a function so the main body pays for one statement).

## 2026-07-23 — `mpc_strategy.pine` Method 3 (deep-fib entry) + prime-combo defaults

**New GRP_EXEC input `execDeepFib`** ("Entry: deep gap enters on nearest fib (not gap edge)"). It fixes a class of missed trades: when a qualifying FVG floats DEEP in the retrace, the limit used to rest at the gap's own edge, so price often stalled at a shallower fib and turned back before the edge was ever tapped. With it on, a gap whose NEAR edge (long = gap top `_gT`, short = gap bottom `_gB`) sits deeper than 0.618 re-prices to the nearest fib just SHALLOWER — 0.618/0.702/0.786 — the level price reaches first. A gap on a fib level, or shallower than 0.618, is unchanged. Logic: helper `f_deepFibEdge()` before the Entry EDGE block, called inside the FVG loop. **ONLY the near edge's position decides it** — an earlier "gap body contains a level" gate was WRONG (it dropped exactly the deep multi-level gaps this targets) and was removed.

**Defaults flipped to Aaron's "prime" combo** — the settings he hard-tests in TradingView, now the shipped defaults across the strategy Pine, the export Pine, and the Python bot: `execArmSweep` OFF→**ON**, `execArmDiv` ON→**OFF** (arm on liquidity sweeps, not divergence), `execFvgDeepOnly` OFF→**ON**, `execDeepFib` (new) → **ON**. `execReqFVG` stays ON. This combo measured ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2 years of gold at 84 trades (Aaron's TradingView Strategy Tester). NOTE: this changes the Strategy Tester baseline — the OLD divergence-armed numbers no longer reproduce without flipping the toggles back.

**Ported to the Python bot the same day** — `strategies/python/mpc_sos_fade/` (config `exec_deep_fib` + the four flipped defaults in `config.py`, `execution._deep_fib_edge()`, export `cfg_bits` bit 8192, `compare_strategy.py` reads it, meta.json panel entry + updated `edge`/`steps`, 4 unit tests). Parity re-run pending a fresh TradingView export.

**Slippage pinned to 0 in the `strategy()` call.** Both `mpc_strategy.pine` and `mpc_strategy_export.pine` now declare `slippage = 0` (the two `tradingview/` research strategies too), so the Strategy Tester Properties tab defaults to zero instead of Aaron's carried-over 25-tick setting. TV slippage is a broker-emulator COST, not signal logic — a flat per-fill charge that is neither honest (a resting limit never slips) nor comparable to the zero-cost Python `fill_model="bar"` run. Real costs go in the lab's tick fill model. The breakeven buffer (`execBeBufTk`, default 30) is a strategy INPUT and is unchanged. This does not touch the decision-stream (`px_*`/`cfg_*`) columns, so `compare_strategy.py` parity is unaffected.

---

## 2026-07-24 — the B-LEG fork + 500x leverage pin

**New file `indicators/mpc_b_leg_strategy.pine`** — the B LEG split out as its own strategy (see the Key-paths entry above for what it is, how it differs from the parent, and the lean-out). Standing rule for it: any change to the parent's engine or A+ block flows in line-for-line; any B-LEG change flows to the Python port in `strategies/python/mpc_bleg/`.

**500x leverage pinned in the `strategy()` call** to match Aaron's demo account. `mpc_strategy.pine`, `mpc_strategy_export.pine` and `mpc_b_leg_strategy.pine` now carry `margin_long = 0.2, margin_short = 0.2` (margin % = 100 / leverage → 500x = 0.2%), and the two `tradingview/` research strategies (`ny_orb.pine`, `london_breakout.pine`) got the same. Like `slippage = 0`, this only sets the Strategy Tester Properties defaults so a fresh paste reproduces Aaron's account — it is not signal logic and does not touch the `px_*`/`cfg_*` decision stream, so `compare_strategy.py` parity is unaffected.

---

## 2026-07-25 — blocked-trade marker (`mpc_strategy.pine` + `mpc_strategy_export.pine`)

A setup refused by one of the strategy's own toggles used to be **invisible everywhere**: no order is
placed, so nothing is drawn, no row reaches the trade list, and the Strategy Tester cannot know it
existed. That made it impossible to judge whether a blocking rule protects the account or costs it.

**New in both A+ files.** A pink `▲/▼ TRADE BLOCKED` label with the reason in its hover tooltip and a
dotted leader down to the price the limit would have rested at. Input `showBlockTag` ("Mark blocked
trades on chart (pink)", group `A+ Debug`, default ON). Cosmetic only — it reads state and places no
orders.

**Six reasons, reported by PRECEDENCE** (`f_blkCode` returns the first rule that would refuse the
order, so a tag never blames a downstream gate for an upstream refusal): 1 direction off · 2 arm
source off · 3 final hour · 4 divergence/extreme veto · 5 HTF breakout · 6 HTF bias.

**"Ready" deliberately omits every toggle gate** — those are the blockers being reported. It asserts
only what price and the engine decide: SOS in, `fibo_dir` agrees, an entry edge exists, flat, this leg
not already traded.

**Deduped on `sosBar * 10 + code`**, so a setup blocked for twenty bars is one tag — but a *changed*
reason (veto clears, final hour then blocks) is a genuinely different refusal and gets its own tag.

**The `[BLOCK]` log now reads the same `lBlkCode` / `sBlkCode`**, so the log and the tag can never
disagree about why a trade did not happen. This also *shrank* the diag block (the old `lReadyBase` /
`lBlkVeto` / `lBlkLate` trio is gone) and widened its coverage from two reasons to all six.

**Export gets `px_block`** = `longCode + shortCode·10`, non-zero on **every** bar the block holds
(not deduped like the tag), so an offline reader can measure how long each refusal lasted as well as
count them.

**It broke the token cap, and three subsystems paid for it (CE10117: 101484 > 100256).** Removed from
`mpc_strategy.pine` — **Order Blocks** (input group, `OrderBlock` type, `manageOBs`/`extendOBs`, and
all four creation blocks: external bull/bear + internal bull/bear), **VWAP** (input group,
`ta.vwap(hlc3)`, the `plot`), and the **Session Volume Profile / MV line** (input group + the whole
Asia-POC block). 4935 → 4700 lines.

All three were cosmetic, defaulted OFF, and read by **nothing** in the execution layer — verified by
grep before deleting (zero references to any of them after the `STRATEGY EXECUTION` header, and zero
orphaned identifiers after: `showOBs`, `obBodyOnly`, `maxActiveOB`, `colBull/BearOB`, `showBull/BearOB`,
`manageOBs`, `extendOBs`, `vwapValue`, `vwapColor`, `vwapWidth`, `showVwap`, `hlc3`, `SVP_SESSION`,
`SVP_TZ`, `inSVP`, `svpRows`, `svpHistory`, `svpPOCCol`, `svp_poc*`, `GRP_OB/VWAP/SVP`). The B-LEG
fork dropped the same three on 2026-07-24 for the same reason, so this is precedent, not a new call.
They live on in `mpc_assistant.pine` if the drawing is ever wanted back.

**`process()` is untouched**, so the byte-identical rule still holds and no parity harness is affected.

**`mpc_strategy_export.pine` got the identical cuts** (4778 → 4540 lines) — its pre-cut line numbers
matched the parent's exactly, so the same eight ranges applied verbatim. In the export the three were
doubly pointless: nobody reads its chart, it exists only to emit the columns, and none of the three fed
any of them. **All 25 `px_*` / `cfg_*` / `dbg_*` columns verified present afterward**, including the
new `px_block`, so `compare_strategy.py` is unaffected.

**If CE10117 returns anyway**, trim in this order: shorten the six `f_blkWhy` strings, then drop codes
1 and 2 (a disabled direction or arm source is a setting you already know about, unlike the four that
depend on price).

---

## 2026-07-26 — orphaned-SVP compile fix + `mpc_strategy_export.pine` regenerated

**The compile error.** Aaron's brother edited `mpc_strategy.pine` directly on TradingView and pushed
it. His copy deleted the Session Volume Profile **inputs** (`showSVP`, `svpRows`, `svpHistory`,
`svpPOCCol`, `GRP_SVP`) but left the entire 108-line SVP computation block behind, so the script failed
with `CE10272: Undeclared identifier "showSVP"` at the first line that read one. Removed the orphaned
block (the MV / Asia-POC line; cosmetic, read by nothing in the execution layer). 4668 → 4560 lines.
Order Blocks and VWAP were cut cleanly in his copy — verified by grep, no orphans left.

**Lesson for the next TradingView round-trip:** when a feature is cut on the TV side, grep for its
identifiers before trusting the paste. A deleted input group with its consumer still in place compiles
locally in nobody's head and fails on the first line that reads it. The 2026-07-25 entry above lists
the exact identifier set for all three cosmetic subsystems — use it as the checklist.

**`mpc_strategy_export.pine` regenerated** (4540 → 4610 lines) by its own documented procedure: the
parent's body up to the `DIAGNOSTIC LOG` header, plus the appended `PARITY EXPORT` block, then restore
`strategy("MPC A+ Strategy Export"` on line 29. That title is now the **ONLY** difference from the
parent — verified by `diff` over the shared range, zero other lines. The export had drifted five
trade-affecting changes behind (the whole **B LEG** setup + its three inputs and the `execAplus` term
in `longArmed`; **`execFvg50`**; **`execRunnerTrail` + `execStructTrailBufTk`**, the structure-swing
runner trail that is now the DEFAULT; **`execTp2StopMode`**; and the removed fixed-R:R lever) and still
carried the JARVIS confirmation table the parent dropped 2026-07-24. All 25 `px_*` / `cfg_*` / `dbg_*`
columns verified present afterward.

**Two things deliberately NOT done, both flagged in the export's own header:**
- **`cfg_bits` still packs 14 booleans.** `execAplus`, `execBLeg` and `execFvg50` have no bit, and
  `execRunnerTrail` / `execStructTrailBufTk` / `execTp2StopMode` have no column. At their **defaults**
  this costs parity nothing (`execBLeg` and `execFvg50` are OFF, and the `mpc_sos_fade` Python bot has
  no B leg — that lives in `mpc_bleg`). Tune any of them and the column must be added here AND in
  `compare_strategy.py` before a diff means anything.
- **`execFvgDeepest` (the deepest-gap-on-a-fib entry toggle) is GONE and has to be rebuilt from
  scratch if wanted.** Built repo-side 2026-07-25 across both Pine files, `mpc_sos_fade`
  (`config.py` / `execution._pick_edge` / 6 unit tests / meta.json panel / `cfg_bits` bit 16384) and
  never committed — then wiped: the brother's TradingView copy overwrote the Pine, and the working-tree
  revert that followed discarded the Python. Nothing of it survives. What it did: when TWO OR MORE
  FVGs qualify in the entry band, ignore the shallow ones and rest the limit at the DEEPEST gap whose
  body holds a fib entry level (0.618/0.702/0.786/0.886), at that gap's own near edge — instead of the
  historical rule of taking the gap price reaches FIRST. Method 3 was deliberately NOT applied on that
  path (re-pricing a gap that already holds a level drags the limit back to the shallow side and undoes
  the choice). Measured over 8 years of gold 15m: 188 trades / +39.0R → 180 / +44.5R, better in 6 of 9
  years — a real fix on the specific trade Aaron raised (a −1.00R stop-out became a +0.10R scratch) but
  only modestly above the ~3R noise floor in aggregate. **The lesson is the process, not the feature:
  commit repo-side Pine work before the next TradingView round-trip, or it dies.**

---

## 2026-07-26 — the exit levers ported to the B-leg fork + the export's config columns completed

Aaron's brother's 2026-07-25 paste added a new **exit** family to `mpc_strategy.pine`. This pass
brought `mpc_b_leg_strategy.pine` and both Python bots up to it, and closed the export hole it left.

**What was new in the parent** (all in `GRP_EXEC`):
- `execRunnerTrail` — "Fixed step" / **"Structure (swing)"**, the DEFAULT. Past TP2 the runner
  trails the structure engine's last confirmed swing (`st.last_conf_low` / `st.last_conf_high`)
  instead of the `execTrailStep` grid ratchet.
- `execStructTrailBufTk` — 20 ticks below/above that swing, so a wick doesn't clip the runner.
- `execTp2StopMode` — "TP1 price" (default) / "Breakeven" / "One trail step behind": the stop FLOOR
  the instant TP2 fills, before the trail engages. The trail may tighten past it, never loosen it.
- `execSlLevel` — the stop's fib, 0.618 … **1.0** (default = the leg origin, i.e. unchanged).
- `execAplus` — trade A+ setups at all, so the B leg can be read in isolation.

The brother's tooltip names the tested best combo: **Structure trail + buffer 20 + floor = TP1 price**.

**Ported into `mpc_b_leg_strategy.pine`:** `execRunnerTrail`, `execStructTrailBufTk`,
`execTp2StopMode` and the `lStage2Floor` / `sStage2Floor` + structure-trail exit block, line-for-line
off the parent. Plus `execAplus`, relabelled **"A+ has priority (stand the B-leg down)"** — in this
fork A+ never places an order, so the flag doesn't disable an entry path, it drops the priority gate.
That gate has been the file's own first-listed tuning candidate since 2026-07-24 and is now a toggle.

**Deliberately NOT ported to the B-leg fork**, with reasons, so nobody "fixes" it later:
- `execSlLevel` — the B leg's stop is its frozen band's origin, not a fib on the A+ leg. The dropdown
  has nothing to select there.
- The pink blocked-trade markers. Their codes answer "why was this **A+** setup refused". In a fork
  where A+ never trades, those tags read as the opposite of what they mean. A B-LEG block tag needs
  its own code set — new design work, not a port.

**The export hole this closed — the important part.** `execRunnerTrail` shipped defaulting to
Structure on 2026-07-25, but `mpc_strategy_export.pine` carried no column for it. So
`compare_strategy.py` configured the Python bot to the fixed-step fallback and diffed a
structure-trailed Pine against a grid-trailed Python: a mismatch that is pure drift, reported as if
it were a bug. **A default that changes behaviour is exactly as dangerous as a new input, and it
hides better.** The export now carries `cfg_bits` bits 16384 / 32768 / 65536 (`execAplus` /
`execBLeg` / `execFvg50`), `cfg_exitmode` (both exit dropdowns packed), and one RAW column each for
`execStructTrailBufTk` / `execTrailStep` / `execTp1Pct` / `execTp2Pct` / `execBeBufTk` /
`execSlBufTk` / `execBeBandR`. Those six are plotted raw rather than packed on purpose: any pack
that fits them in one float64 has to round, and a silently rounded buffer mis-configures the bot —
the exact failure the block exists to prevent. `compare_strategy.py` warns loudly on an export with
no `cfg_exitmode` (i.e. taken before this change) instead of guessing.

**VALIDATED the same day — and the new columns paid for themselves immediately.** A fresh 21,230-bar
`VANTAGE_XAUUSD, 15m` export off the updated export Pine ran `compare_strategy.py --warmup 100` to
**exit 0**. Two things only the new columns could have told us:
1. The Pine was running `execTp1Pct = 20` / `execTp2Pct = 20`, NOT the 30/40 shipped defaults. With no
   column for them the bot would have replayed 30/40 and the diff would have been blamed on logic.
2. The first run's single mismatch (`px_edge` on one bar) was a genuine bug — an unpinned FVG engine
   input. `mpc_strategy.pine` HARDCODES the middle-bar close-cleared check (lines 1686/1688) while the
   `fair_value_gaps` engine defaults `require_close` OFF, so Python created gaps the Pine never did.
   Fixed on the Python side (`EngineConfig.fvg_require_close`, pinned True by the bot). **Never fix
   this class of gap by editing the Pine** — it is the source of truth; the pin belongs in the port.

`mpc_b_leg_strategy.pine` compiles (confirmed on TradingView), and its parity harness was built the
same day: **`indicators/mpc_b_leg_strategy_export.pine`** = that file with the body byte-identical
(only the line-40 `strategy()` title differs) + an appended PARITY EXPORT block, diffed by
`strategies/python/mpc_bleg/tools/compare_bleg.py` and registered in `backtest/tools/verify_parity.py`.
It plots the B-LEG arm (NOT `longArmed` — A+ never places an order in this fork), the band's 0.5 edge,
the band-derived TP1/TP2, and the tracker's own `bl_*` state, which is the column set that matters:
every new B-LEG rule lives in the tracker, and a band-maths bug shows as a wrong price many bars before
it becomes a wrong trade. **Ran GREEN (exit 0) on its first real export the same day** — 21,231 bars, ~90 distinct frozen bands and 5 graded trades diffed. That run also found a bug in the HARNESS (entry direction read off `Fill.qty`'s sign instead of the signed `Fill.dir`), which the offline round-trip test could never catch because its encoder shared the same mistake — a round trip proves the two halves agree, never that either is right.
`cfg_strcodes`' SL slot is pinned to the "1.0" code because this fork has no `execSlLevel` (its stop is
the band ORIGIN), which keeps ONE `cfg_*` decoder serving both exports. Regeneration split point is in
the export's own header.

---

## 2026-07-27 — TP1/TP2 default 30/40 → 0/0, and the `qty_percent = 0` trap

`execTp1Pct` / `execTp2Pct` now default **0** in both `mpc_strategy.pine` and
`mpc_strategy_export.pine` (and `exec_tp1_pct`/`exec_tp2_pct` in `config.py`, in lockstep). 0 = bank
NOTHING at the targets; the whole position rides to the runner. This is what Aaron has actually been
trading — his saved chart carried 1% on both rungs, which is the closest the input would take — and it
is what `mpc_sos_fade_optimization.md` Run 1 measured as best (0/0 = 70.7R vs 47.9R at 30/40,
monotonic across all 21 combos).

**The trap, and why the code needed a guard, not just a new default.** `strategy.exit()` treats
`qty_percent = 0` as UNSPECIFIED and falls back to closing the **whole position** at that limit — so
setting the input to 0 would have banked everything at TP1, the exact opposite of what it reads as.
This is why 0 appeared not to work. Both files now SKIP the call entirely when the rung is 0:

```pine
if execTp1Pct > 0
    strategy.exit("L-TP1", from_entry = "Long", qty_percent = execTp1Pct, limit = lTP1, stop = lStop)
```

leaving the runner leg as the only exit, which is what 0% means. The TP **prices** still drive the
staged stop (`lStage`/`sStage`) whatever the rung sizes are — touching TP1 still lifts the stop to
breakeven, touching TP2 still hands the runner to the trail. The Python needs no guard:
`_remaining_brackets` computes p1 = p2 = 0 and emits neither bracket. `minval` on both inputs was
already 0; the failure was at runtime, not in the input.

**Parity RE-VALIDATED GREEN (exit 0) 2026-07-27** on a fresh 21,320-bar `VANTAGE_XAUUSD, 15m` export
taken at the settings Aaron trades — SL fib **0.886**, TP1 0%, TP2 0%, structure trail. First run of
the 0/0 exit path against the Pine, so the guard is verified by the decision stream, not just by the
script compiling.

**A note on reading TradingView's trade list, learned the same day.** The Strategy Tester counts each
exit RUNG as its own "trade": a 486-row list over 2020-2026 was 162 positions × 3 rungs. Group by entry
timestamp before comparing anything to a Python run's trade count. The rung SIZES in that export are
also how the 1%/1%/98% split was caught — the sizes are in the CSV and they are ground truth about what
the chart was configured to do, which the code's defaults are not.

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
