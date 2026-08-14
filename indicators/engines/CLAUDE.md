# CLAUDE.md — indicators/engines/

**Purpose:** The Pine `indicator()` sources — the charting engines every Python engine under
`engines/` was ported FROM, plus the instrumented `_export` twins their parity gates diff
against, plus the from-scratch `smc_engine_v2.pine` rebuild, plus a small number of THIRD-PARTY
indicators kept here for reference under their own licences.
**Scope:** This file owns everything true of an INDICATOR Pine file here. It does NOT cover the
`strategy()` sources (`indicators/strategies/CLAUDE.md`) and it does NOT restate what any Python
engine does — each `engines/<name>/CLAUDE.md` owns that, and duplicating it here is how three
files came to disagree about whether a bot was live.
**Status of the from-scratch rebuild (`smc_engine_v2.pine`):** Under construction — Stage 2b
(break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3
(internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on
chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-08-13 — split out of `indicators/CLAUDE.md` when the Pine sources were
divided into `strategies/` and `engines/`. The rules below moved verbatim; nothing was rewritten.

## What lives here, and the one thing that decides it

A file is in this folder if its declaration is `indicator()`, and in `../strategies/` if it is
`strategy(`. Mechanical on purpose — **check the declaration, never the filename**:
`mpc_m15_playbook.pine` is an `indicator()` and lives here while `mpc_m15_playbook_strategy.pine`
is a `strategy()` and lives next door, and `structure_engine.pine` reads like a strategy
component but is an indicator.

🔴 **The stale-armed-level defect, found 2026-08-13 by reading `mss_sweeps_luxalgo.pine`, and the reason `mss_sweeps_mpc.pine` disarms on the CHARACTER change rather than only on the opposite break.** In their file the armed direction is cleared by a sweep, a failed sweep, or the OPPOSITE BOS — and an opposite BOS needs a character change plus a second break. So: bull BOS freezes the protected low at 100, price makes a new internal low at 110, price closes under 110 (a confirmed bearish character change), and **nothing touches the armed state**. Price then wicks to 98, closes 102 green, and a *bullish* signal prints into a confirmed bearish leg. It self-heals only in the one case where the protected level and the current internal low are still the same price, which any pullback after the break destroys. **Our fork disarms on any shift against the armed direction at EITHER degree**, plus a bar-count expiry and an ATR depth cap. ⚠ **The same bug has a second entrance and it is guarded separately**: the engine writes `i_last_hl` only when it has a tracked pullback extreme, and otherwise KEEPS THE PREVIOUS VALUE rather than going `na` — so `not na(i_last_hl)` alone would arm on an iHL from an earlier cycle. The arm test requires the LOCATION to have moved on this bar. **The standing lesson is about what clears state, not about their file: a state machine is only as good as its exits, and "the opposite event will overwrite it" is not an exit when the opposite event needs two steps to arrive.**

⚠ **A `_luxalgo` or otherwise vendor-suffixed file is THIRD-PARTY reference, not our source.** It
was not ported from `mpc_assistant.pine`, no `compare_*.py` gate measures it, and it carries its
own licence header at line 1 — leave that line alone. It is here to be read, not to be edited: an
edit makes it a fork nobody can re-download, so change the CLAUDE.md and take a new copy instead.

🔴 **Two separate tracks live in this one folder and confusing them wastes a session.**
`mpc_assistant.pine` and everything extracted from it (`structure_engine.pine`, every
`*_export.pine`) is the track the 13 canonical Python engines were ported from and the track
every `compare_*.py` gate measures. `smc_engine_v2.pine` is an independent from-scratch rebuild
of the same idea, with its own detection rule and its own standing instructions below. A finding
about one says nothing about the other.

⚠ **An `*_export.pine` is half of a parity gate and has to move with its parent.** Changing
`structure_engine.pine` without landing the same change in `structure_engine_export.pine` leaves
the gate green about a file nobody uses. Rule 22: an engine change is not committed until its
`compare_*.py` has actually RUN and passed on a real TradingView export.

---

## 🔴 The one real defect: `f_rev15` had three ways to die and the chart-side A+ engine has four

The missing one is the one that fires on a WIN — `fibo7Touched`, price back at the leg origin. So on the 15m chart the REV row read `Pass` the moment TP3 printed, while the **1m chart kept the same leg alive at stage 4 saying TAKE PROFIT** until an opposite SOS or a continuation BOS happened along, which can be hours. Two charts, two answers, one setup. Worse than a stale row: the RE-ENTRY round trip clears the TP latches when price returns to 0.618, so a finished trade could hand the 1m a fresh AWAIT and ask for a 1m SOS on a leg the 15m had closed the book on. Fixed with `or L_tp0` / `or S_tp0` on the two death conditions — `L_tp0` **is** TP3, since `p0` is `L_high`, the leg origin, the same 0.0 the drawn fib labels TP3. ⚠ **It kills one bar LATE**: the death block runs before the fib block that sets the latch, where the 15m side kills on the bar itself. Left as is — every other value this engine ships crosses the security boundary a bar late in the same way. ⚠ **It retires the whole 1m stack together, not just the row** — `rStage` falling below 3 drops `_m15Retraced`, which is what `fiboShowAligned`, the 1m External Fib, the 1m Sniper Zone and the 1m ENTRY row all hang off. ⚠ **Nothing on the 15m moves**: every consumer of `rStage`/`rTp50`/`rDeepCode`/`rZoneLo` sits behind `_fibOneMin`, `_sn1m`, `revOn1m` or the non-15m branch of the table, checked one by one; `f_rev15` exists only in `mpc_assistant.pine` and `mpc_m15_playbook.pine`, so **no bot and no parity gate can see this.**

---

## Key paths & entry points

- `indicators/engines/smc_engine_v2.pine` — the current pullback-only rewrite (v6 Pine Script), overlay indicator named "SMC Engine"
- `indicators/engines/mpc_assistant.pine` — a full-featured SMC indicator (structure + order blocks + sessions + kill zones + VWAP + liquidity levels + fibonacci + SVP) that Aaron sourced separately. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsmpcassistantpine)
- `indicators/engines/structure_engine.pine` — a straight extraction of *only* the market-structure logic (external ASH/ASL/BOS/CHoCH/HH/HL/LH/LL + internal iSH/iSL/iBOS/iSOS) from `mpc_assistant.pine`, with every other feature (OBs, sessions, kill zones, VWAP, liquidity, fibo, SVP) stripped out. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsstructureenginepine)
- `indicators/engines/fib_export.pine` — instrumented build for the FIB parity check: the external **and internal** structure engine (copied from `structure_engine_export.pine`, plus the mpc capture lines the fibs need — `i_confirmed_*` and the `iFib_*` seed anchors) + the Structure, Sniper, Macro AND Internal fib blocks lifted from … [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsfibexportpine)
- `indicators/engines/structure_engine_export.pine` — instrumented copy of `structure_engine.pine` (logic byte-for-byte identical; adds `plot()` output columns, including the eight break-leg columns `px_bull_bos_high/low` + `px_bull_bos_h_ago/l_ago` and bear mirror added 2026-07-02). [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsstructureengineexportpine)
- `indicators/engines/ob_export.pine` — instrumented build for the ORDER-BLOCK parity check. **REBUILT 2026-07-31 (1148 → ~300 lines): it no longer embeds the structure engine at all.** [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorsobexportpine)
- `indicators/engines/candle_sticks.pine` — **a THIRD-PARTY indicator, added 2026-08-08** ("Candlestick Patterns Identified, update 1-17-26", © repo32, MPL-2.0, v6). [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorscandlestickspine)
- `indicators/engines/candle_sticks_export.pine` — the parity harness for `engines/candlesticks/`. [Detail](../docs/INDICATORS_BUILD_NOTES.md#indicatorscandlesticksexportpine)
- `indicators/engines/mss_sweeps_luxalgo.pine` — **a THIRD-PARTY indicator, added 2026-08-13.** "MSS Sweeps [LuxAlgo]", published open-source on TradingView (`tradingview.com/script/gRo6KnE6`, author `MrQuant_Jacob`), MPL-2.0, v6, 193 lines. Fetched VERBATIM — the pine-facade API reports `scriptAccess: open_no_auth`, and the licence header is line 1. **Reference only: nothing imports it, no Python port exists, no `compare_*.py` measures it.** What it does: tracks internal SMC legs, waits for a hidden CHoCH followed by an internal BOS, remembers the protected swing that break left behind, and fires when price sweeps that level and reclaims it. Four `alertcondition`s — bullish BOS, bearish BOS, higher-low sweep, lower-high sweep. ⚠ **It is a SECOND structure implementation and must never become an import path** — `engines/market_structure/` is canonical, and this file's leg detection is its own rule, not ours. Read it for the sweep-and-reclaim idea; do not wire it to anything.
- `indicators/engines/mss_sweeps_mpc.pine` — **our fork of the MSS Sweeps trigger, added 2026-08-13, 1321 lines.** Keeps the IDEA from `mss_sweeps_luxalgo.pine` (after a continuation break, remember the protected swing behind it; signal when price wicks through and closes back) and replaces their structure entirely with ours. **The engine block is `structure_engine.pine` lines 27-1044 byte-identical** — regenerate with `sed -n '27,1044p' structure_engine.pine`, and land any structure change THERE first. What our engine buys, and it is the reason the fork exists: (1) **a second degree of structure.** Theirs has only internal-at-length-5, so it cannot ask whether a sweep points with the trend; ours has `st.dir`, and the trend filter is built on it. (2) **no repaint** — every `int_bull_bos`/`int_bear_sos` fires under `barstate.isconfirmed`, where their BOS reads the live close and can vanish intrabar. (3) **the stale-level defect is fixed** — see the entry below. ⚠ **`showInternal` is TRADE-CRITICAL in this file, not cosmetic**: the engine gates its whole internal state machine on that display toggle (`internalActive = showInternal`), so turning it off stops every signal. Left byte-identical rather than patched; the MSS layer draws an orange on-chart warning instead of failing silently. ⚠ **NOTHING IS MEASURED** — not compiled, no Strategy Tester run, no export twin, no `compare_*.py`, no Python port. Every default is legible rather than optimal, and the stats table exists so the trend filter can be judged from a chart instead of argued about.
- `indicators/docs/STRUCTURE_OS_BUILD.md` — cross-session handoff doc for the from-scratch rebuild: architecture, design decisions, validation findings, build-stage status. Read this first when resuming that track.
- `docs/market_structure_engine_spec.md` — the source-of-truth rules spec, written from the TradingView overview page. `STRUCTURE_OS_BUILD.md` treats this as priority-1 source of truth.

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
