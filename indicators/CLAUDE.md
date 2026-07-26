# CLAUDE.md — indicators/

**Purpose:** From-scratch Pine Script rebuild of the "Structure OS / SMC Engine" market-structure indicator (swing highs/lows, HH/HL/LH/LL, BOS, CHoCH), replicating a private TradingView indicator's behavior using a pullback-only detection method.
**Scope:** This covers Pine Script indicator development and the market-structure detection engine only. It does NOT cover trading strategy logic, risk management, or any live/backtest execution — this is a charting indicator, not a bot.
**Status:** Under construction — Stage 2b (break-gated swing structure + BOS/CHoCH) is ~95% validated against the original; Stage 3 (internal structure) and Stage 4 (multi-symbol/timeframe comparison) not started. Blocked on chart validation by Aaron before Stage 3 begins.
**Last reviewed:** 2026-07-26 — the new exit levers (structure runner trail, TP2 stop floor, SL fib dropdown, `execAplus`) ported into `mpc_b_leg_strategy.pine`, and `mpc_strategy_export.pine` given a column for every trade-affecting input (see the second 2026-07-26 entry). Earlier the same day: orphaned-SVP compile fix in `mpc_strategy.pine` + the export regenerated off it. Earlier: 2026-07-12 — the whole structure chain was re-synced to the `choch_lock` removal in `mpc_assistant.pine` and re-validated at 100% Pine parity (see the "2026-07-12 structure re-sync" note below), and the A+ divergence retro-link landed in both A+-carrying files (see the note after it).

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
- `indicators/mpc_strategy.pine` — Aaron's brother's "MPC-JARVIS" backtest script: the same engine as `mpc_assistant.pine`, converted from `indicator()` to `strategy()` and given an execution layer at the end (A+ sequence entries, fib TP ladder, %-risk sizing). Its `process()` state machine is byte-identical to `mpc_assistant.pine`'s — verified by diff, keep it that way. **Sync direction reversed 2026-07-21: the REPO is now the source of truth** — Aaron pastes this file up to TradingView and his brother picks it up, so repo-side edits stick. (It used to flow the other way, which is why older notes warn about TradingView edits silently reverting fixes.) There is no local Pine compiler: validation is pasting into TradingView, checking it compiles, and confirming the Strategy Tester numbers are unchanged.
- `indicators/mpc_b_leg_strategy.pine` — a FORK of `mpc_strategy.pine` that trades ONLY the B LEG (the SOS whose retrace arrived late), split out 2026-07-24 to run PARALLEL to the A+ bot. The ONLY logic change vs the parent is the execution layer: the two A+ `strategy.entry` blocks are replaced with cancel-only stand-down (`longArmed`/`shortArmed` are still computed so the "A+ has priority" gate on the B leg is preserved), and the B LEG is the sole entry type. The whole engine + A+ sequence tracker above the execution block stays byte-identical to `mpc_strategy.pine` — do not let it drift. **Leaned out 2026-07-24** (4871 → 4573 lines): the code that went dead when A+ entries were disabled (`f_conf`, `f_slAnchor`, the `execSlLevel` input, `longDeep`/`shortDeep`, `longEdgeSz`/`shortEdgeSz`) plus three self-contained cosmetic subsystems the B leg never reads and that default OFF (VWAP, Session Volume Profile/MV, Order Blocks) were removed. Python port lives in `strategies/python/mpc_bleg/` (its own CLAUDE.md). Same no-local-compiler rule: validate by pasting into TradingView. **No Pine↔Python parity harness yet** — a `mpc_b_leg_strategy_export.pine` + `compare_bleg.py` are the follow-up.

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

`mpc_b_leg_strategy.pine` compiles (confirmed on TradingView) but has **no parity harness yet** — the
`compare_bleg.py` + export Pine remain the follow-up, so its numbers are still directional only.

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
