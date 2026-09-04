# CLAUDE.md — strategies/python/b_leg/ (the B-LEG bot)

**Purpose:** The B-LEG setup as a standalone Python strategy — a port of
`strategies/tradingview/b_leg_strategy.pine` (Aaron's brother's B-LEG fork of MPC-JARVIS). The
B LEG is the SOS whose retrace arrived LATE: an SOS Fade reversal dies at 2/3 on a continuation
BOS before it retraces, the Sniper-Zone band (0.382–0.5) of that break is frozen, and a
resting limit at the 0.5 edge waits for the late return.
**Sweeps:** `b_leg_optimization.md`, next to this file — **empty on purpose**, because no
sweep has ever been run here. It carries the two named tuning candidates and the rule that must be
obeyed before the first grid: state the out-of-sample split BEFORE it runs, at n=50.
**Scope:** This bot only — its tracker, order layer, config, tests. It does NOT own the
engines (`engines/`), the replay runner (`backtest/`), or the SOS Fade machinery it reuses
(`strategies/python/sos_fade/`).
**Status:** Built + unit-tested (19 tests green) + **Pine-parity GREEN (exit 0), re-validated 2026-07-31**
on a fresh 6,329-bar `VANTAGE_XAUUSD, 15m` export off the session-window build — bar-for-bar
identical decision stream. The harness is `tools/compare_bleg.py` +
`strategies/tradingview/b_leg_strategy_export.pine`, registered in `verify_parity.py`.
⚠ **STILL NO ESTABLISHED EDGE, but the defaults MOVED THREE TIMES on 2026-08-06 and the old numbers
no longer describe this bot.** The shipped configuration is now **114 trades / +17.56R / PF 1.45 /
maxDD −5.15R over 7.9 years with spread and swap charged** (free book: +23.28R / PF 1.65 / maxDD
−4.19R), against the pre-change **59 / −1.73R / PF 0.94 / maxDD −16.00R** on the same bars and the
same charges. Both halves of the history are positive now (IS +3.14 / OOS +14.42) where the old
defaults lost 8R in the first. **The 95% CI on mean R is −0.068 → +0.376 and still contains zero**
— the 7.9-year total belongs anywhere in **−7.7R to +42.8R** — so read this as "the measurement
moved up and narrowed", never as "it works". Three defaults carry it and each was measured on its
own axis: `exec_trail_pct` 1.0 → 0.05, `bleg_max_days` 1.25 → 4.0, `exec_time_stop_hrs` 36 → 8.
See "The exit-ladder re-default".
`strategies/tradingview/b_leg_strategy.pine`.** All 11 params in `b_leg.meta.json` carry that input's
Pine title byte-for-byte and its tooltip verbatim as the `desc`; change one and change the Pine in
the same commit. 🔴 **13 descs were rewritten to plain English on 2026-08-16 when every Pine tooltip
was cut to one or two sentences, and `test_the_meta_descs_are_the_pine_tooltips_verbatim` WENT RED
first — which is that test earning its place.** It is the only automated guard on this pairing, so
treat a red there as the contract working rather than as a test to relax. Strings only: no name,
default, min, max or step moved. Two of them are deliberately the FORK's own wording, not the SOS Fade parent's —
`exec_aplus` is "SOS Fade has priority (stand the B-leg down)" because in this file SOS Fade never places an
order, and `exec_sl_buf_tk` says "beyond fib 1.0" because that is where this bot's stop always
sits. Nothing behavioural moved: the only Python edits were two comment strings in `config.py`.
✅ **`compare_bleg.py` re-run GREEN the same day** on a fresh 21,715-bar `VANTAGE_XAUUSD, 15m` export
(2025-08-31 → 2026-08-02, `cfg_bits` 61047 — `execBLeg` ON, `execAplus` priority ON, `execDeepFib`
ON, matching this fork's pins) — **exit 0 at warmups 100 / 500 / 1000 / 2000**. Earlier the same day: **the parent's new SOS Fade entry model is PINNED OFF here, and
unlike the minimum-stop guard it is NOT inert.** `sos_fade` gained rules 1-3 (`exec_fib_overlap` /
`exec_fib_deep_edge` / `exec_fib_nearest`), the pre-zone gate (`exec_fvg_pre_zone`) and the
deep-entry stop (`exec_sl_deep`), and flipped `exec_deep_fib` **True → False**.
`b_leg_strategy.pine` has none of those inputs and still ships `execDeepFib = true`, so
`BLegConfig` pins all six. **Why the pins are load-bearing rather than tidiness:** this fork
overrides `_place_entries` but **NOT `_entry_edges`**, and the SOS Fade edges it produces are passed to
`_armed()` — the "SOS Fade has priority, stand the B leg down" gate. A different SOS Fade entry edge therefore
changes which bars the B leg is allowed to trade on, so inheriting the parent's new defaults would
have moved B-LEG trades with no Pine change behind it. The pins keep this fork byte-identical to its
own Pine; nothing in this package's code changed and the parity run below still stands. Un-pin only
in the same commit that ports the model into `b_leg_strategy.pine`, then re-run `compare_bleg.py`.
⚠ One additive change did reach here: `Signals.fvgs` is now a 4-tuple carrying each gap's born bar,
and `Signals` gained `fibo_half_bar`. Both are read only by the pinned-off gate, so no B-LEG decision
moves. Earlier: 2026-08-01 — 🔴 **THIS BOT INHERITED THE PHANTOM-EXIT BUG AND IS FIXED WITH THE
SOS Fade — it reuses `sos_fade/execution.py`, so the fix arrived here without a line changing in this
folder.** `indicators/docs/BUG_exit_fill_price_mismatch.md`: the FILL BAR was allowed to stage the stop,
which put the stop through the market on a trade that had gone nowhere and market-closed every leg
at the next bar's open. Fixed on both sides, including `b_leg_strategy.pine` and its export.
✅ **`compare_bleg.py` exit 0** on a FULL-HISTORY post-fix export (`VANTAGE_XAUUSD, 15_1b2f3.csv`,
**21,691 bars**, 2025-08-31 → 2026-07-31) at warmups 100 / 200 / 500 / 1000 / 2000, no truncation
warning. Fingerprint scan: **0 of 5 entries** have a stop staged on the fill bar.
⚠ **The B-LEG fork has ZERO affected entries in any window measured, before OR after** — its TP1 is
the broken swing extreme, far further from the entry than the SOS Fade ladder's next fib, so its fill bar
rarely reaches it. **That is exposure, not proof:** the fix here is verified by construction (the
code is literally the SOS Fade's) and by parity, never by a caught case. If a B-LEG trade ever shows the
symptom, treat it as new. ⚠ **Every B-LEG number measured before today was measured through the
bug** — the trade counts are thin enough that one changed result moves the whole picture. ⚠ **NOT a
recurrence of this bug, and it will keep appearing:** a stop staged legitimately at TP1 on a later
bar can still be behind the market when it goes live next bar, and then fills at that bar's open.
That is a backtest limitation, identical in Pine and Python, parity-neutral, and erring in the safe
direction — see `strategies/python/sos_fade/CLAUDE.md` → `### Wrong-side stop fills`.
Earlier: 2026-07-31 — **the session-window fork is CLOSED and proven, and the harness had a
latent hole that a partial chart export walked straight into.** `b_leg_strategy.pine` had never
received the DST-aware session windows its SOS Fade parent has carried since 2026-07-12; both were synced
and `compare_bleg.py` re-run on a fresh export → **exit 0 at `--warmup 800`**, green at 1200 / 2000 /
3000. **What makes this run the right one for that fix:** the window is 2026-04-27 → 2026-07-31,
which sits ENTIRELY inside BST/EDT — the half of the year where the new city-clock windows and the
old fixed GMT-4 windows actually disagree (New York `0800-1700` America/New_York is 12:00–21:00 UTC
under EDT, an hour earlier than the old `0900-1800` GMT-4). A stale Python side would have disagreed
with Pine on every session boundary in this export, so green here is a real result rather than a
window where the two happen to coincide. **The harness hole:** `bl_l_bar`/`bl_s_bar` carry Pine's
`bar_index`, which counts from the first bar the CHART loaded, while the Python tracker counts from
the export's first ROW. Every previous export was the whole loaded history, so the two origins
coincided and nobody noticed the assumption. This one starts 15,362 bars in, and all 2,409 armed-bar
comparisons failed at exactly that constant — the logic was identical the whole time. `compare_bleg.py`
now MEASURES the origin (the modal `pine - python` difference) instead of assuming zero, and the
normalisation is deliberately majority-based so a genuine drift in WHICH bar armed is a minority
offset and still fails; `test_partial_chart_export_still_parity` and
`test_offset_normalisation_still_catches_a_real_armed_bar_drift` pin both halves. **Generalise it:
any parity column holding a Pine BAR INDEX is export-window-relative, and a harness that compares one
raw is only correct by the accident of a full-history export.** 19 tests green.
Earlier: 2026-07-30 — **the parent's new MINIMUM-STOP guard is PINNED OFF here, and is inert
on this path.** `sos_fade` gained `exec_min_stop_mode` / `exec_min_stop_val` (refuse a setup whose
stop lands too close to the entry — `qty = risk / stop_distance`, so a collapsing stop buys an enormous
position). It does not reach this fork: the floor is enforced in the parent's `_place_entries`, which
`BLegExecution` overrides, and `b_leg_strategy.pine` has no matching input to be parity-checked
against. `BLegConfig` pins the mode to `"Off"` so a future parent default change cannot silently claim a
guard this fork never runs. The hazard is also structurally absent here — a B leg's stop is the band
ORIGIN, always a full band away from the 0.5 entry edge, never a fib that can land on top of it. Porting
it = the Pine input + the floor check in this fork's `_place_entries` + a `cfg_min_stop` export column, in
one commit, then re-run `compare_bleg.py`. Nothing else changed and the parity run below still stands.
Earlier: 2026-07-29 — **the stale export is CLEARED: `compare_bleg.py` re-run GREEN on the
ratchet build.** `compare_bleg.py "VANTAGE_XAUUSD, 15_ab202.csv" --warmup 100` → exit 0, 21,493 bars,
2025-08-31 → 2026-07-29, still green at warmup 200/500/1000/2000. The export decoded
`cfg_exitmode = 20` (the new 3-way trail digit reading as "Structure + % ratchet"), `cfg_trail_pct = 1`
and `cfg_tp1_pct = cfg_tp2_pct = 0` — so the ladder changes below are proven through the export, not
merely present in it. `b_leg_strategy.pine` also compiles clean in TradingView. The ratchet's
43% → 53% run-capture caveat below still stands: parity proves the two sides AGREE, never that the
setting is right for B legs. Earlier: 2026-07-28 — **`b_leg_strategy.pine` caught up to the SOS Fade exit ladder**, so this
package's two divergence pins are gone: `exec_runner_trail` is INHERITED again ("Structure + % ratchet",
with `exec_trail_pct` alongside it) and the TP rungs sit at the inherited 0/0. The Pine also gained the
`qty_percent = 0` guard — without it a 0 rung closed the WHOLE position at TP1, which is why typing 0
"blew up" there. Nothing changed in this package's CODE (the ladder has always lived in the parent's
`Execution`); what changed is that the config no longer has to lie to stay parity-green. ⚠ **The export
is now STALE and every B-LEG number from this build is unvalidated until `compare_bleg.py` is re-run**
— `cfg_exitmode`'s trail digit went 2-way → 3-way and `cfg_trail_pct` is new, so an OLD export decodes
the ratchet as the plain structure trail. ⚠ The ratchet's 43% → 53% run-capture result was measured on
**SOS Fade trades only**; it is inherited for one-ladder consistency, not as a proven B-LEG result. Earlier:
2026-07-27 — the SOS Fade blocked-setup AND missed-setup markers stay non-ported here, both now pinned by a test (the miss watch needed an explicit opt-out). Earlier: 2026-07-26 — the exit levers landed, the Pine-parity harness was built, and it came back GREEN on the first real export (see "The parity gate").


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `strategies/python/b_leg/docs/BLEG_BUILD_NOTES.md`. **Nothing was deleted.** It was 30,800 bytes in 1 paragraph(s), the largest 30,800 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

## Why it exists (the split, 2026-07-24)

The B LEG lived inside `sos_fade_strategy.pine` as a second setup type (`execBLeg`, default OFF).
Turned ON alongside SOS Fade it made significantly more money, and Aaron wants to run it PARALLEL
to the SOS Fade bot on the shared account (the portfolio-stacking seam he built). Decision:
**abstract it into its own strategy that shares the READ layer** (the engine stack + the SOS Fade
sequence tracker) and owns its OWN entry/stop/TP — because he intends to tune those
independently, which is the textbook signal to split. The coupling is only on the SOS Fade
sequence STATE (a clean read dependency, like depending on an engine), never on the SOS Fade entry
logic. See the Pine file's header for the same reasoning.

## What it reuses vs what is new

It is deliberately ~90% the SOS Fade bot. The fill / TP-ladder / stop-staging / %-risk-sizing /
R-grading machinery is direction- and setup-agnostic, so it is REUSED wholesale:

- **Reused from `sos_fade`:** `SignalAdapter` → `Signals`, `SosFadeSequence` → `SeqState`
  (the whole SOS Fade engine + sequence), and `Execution` (the broker emulator + exit ladder).
- **New here:**
  - `bleg.py` `BLegTracker` → `BLegState` — the band-freeze / target-track / arm / tap /
    death state machine (Pine 3683-3758). Standalone; reads `Signals` + the `bleg_arm_*`
    flags off `SeqState`.
  - `execution.py` `BLegExecution(Execution)` — a thin subclass: `step(sig, seq, bleg)`
    stashes the `BLegState`; `_place_entries` is the ONLY override — SOS Fade entries disabled,
    B-LEG limit rested at the band's 0.5 edge (SL beyond the leg origin, TP1 = broken swing
    extreme `2·edge−inv`, TP2 = expansion extreme `tgt`, TP3 runner). Everything from
    `_open_position` onward is the parent's.
  - `config.py` `BLegConfig(SosFadeConfig)` — a strict superset, adds only `bleg_max_days`.
  - `strategy.py` `BLegStrategy(SosFadeStrategy)` — inherits `_fill_model` +
    `engine_config` (the SAME `fvg_max_count=7` + `show_internal=False` pins — the B-LEG reads
    the same structure/fib engines), overrides `__init__`/`run`/`step` to splice the tracker.
    `run_dual` is disabled (no secondary).

## The "SOS Fade has priority" gate (kept for baseline; first tuning candidate)

`BLegExecution._place_entries` still computes the SOS Fade `longArmed`/`shortArmed` via the parent's
`_armed()` and stands the B-LEG down on a side where SOS Fade is armed — faithful to the Pine fork.
SOS Fade never PLACES an order (the fork's whole point), it just holds the priority. When stacked
with the real SOS Fade bot on one account the account layer re-does this arbitration, so **dropping
this gate is the first thing to try when tuning** (Aaron's own note in the Pine tooltip). Run
SOLO, the bot fires MORE B-legs than the parent did with `execBLeg` on, because no SOS Fade position
occupies the account — that is correct and expected, not drift.

## Three parity-safe additions to `sos_fade` (do not revert)

The reuse needed three ADDITIVE, decision-neutral changes there (all re-verified: the SOS Fade's
55 offline tests stay green):

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-
   leg endpoints the band-freeze reads). Nothing in the SOS Fade path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine
   point (Pine 3661): after the opposite-SOS death, BEFORE the continuation-BOS death clears
   `l_sos_bar` and BEFORE the half/618 latch update. This is the whole reason the sequence had
   to expose them — by the time `update()` returns, the state the B-LEG arms off is gone.
3. **`execution.py`** — the SOS Fade arm decision was extracted from `_place_entries` into `_armed()`
   (a pure refactor) so the B-LEG subclass can reuse the priority gate. No behaviour change.

## The exit ladder is inherited (2026-07-26)

The structure runner trail, the TP2 stop-floor dropdown and the two setup toggles were ported into
`sos_fade`, and this bot picks up ALL of them for free — `BLegConfig` subclasses `SosFadeConfig`
and `BLegExecution` subclasses `Execution`, and the exit ladder lives entirely in the parent. The
full register is `sos_fade/CLAUDE.md` → `## The exit ladder`. What is specific here:

- **`exec_bleg` is re-defaulted to True.** `b_leg_strategy.pine` ships `execBLeg = true` (the
  SOS Fade file ships it false), so `BLegConfig` overrides the inherited default to match. It gates the
  B-LEG arm in `_place_entries`; OFF the bot trades nothing, which is its only real use.
- **`exec_aplus` controls the PRIORITY GATE here, not entries.** SOS Fade never places an order in this
  fork, so `exec_aplus=False` doesn't disable an entry path — it drops the "SOS Fade stands the B leg
  down" gate entirely. That is the tuning experiment this file's own notes have called for since
  2026-07-24, now a one-flag run instead of a code edit. The same input was added to
  `strategies/tradingview/b_leg_strategy.pine` under the label "SOS Fade has priority (stand the B-leg down)".
- **This bot OVERRIDES TP1 / TP2 / SL** with its band prices (SL = band origin, TP1 = the broken
  swing extreme, TP2 = the expansion extreme). Everything from the stop staging down — the floor,
  the trail, both dropdowns — is the parent's, unchanged.
- **`exec_min_stop_mode` is PINNED `"Off"` (2026-07-30) and is INERT here.** The parent's
  minimum-stop guard runs inside `_place_entries`, which this fork overrides, so the floor is never
  applied on this path — and there is no `execMinStopMode` in `b_leg_strategy.pine` to be
  parity-checked against. The pin exists so a future parent default change cannot make this config
  claim a guard the code does not run. Structurally the hazard is absent too: a B leg's stop is the
  band ORIGIN, a full band away from the 0.5 entry edge, so it cannot collapse onto the entry the
  way a fib stop can. Porting it is three edits in one commit (Pine input, floor check in this
  fork's `_place_entries`, `cfg_min_stop` export column) followed by `compare_bleg.py`.

`strategies/tradingview/b_leg_strategy.pine` was ported in the same pass and now matches: `execRunnerTrail`,
`execStructTrailBufTk`, `execTp2StopMode`, `execAplus`, and the `lStage2Floor` / structure-trail
exit block copied line-for-line from `sos_fade_strategy.pine`. **Completed 2026-07-28** — that Pine had
fallen a lever behind: it lacked the `"Structure + % ratchet"` trail method (+ `f_swingRatchet` and
`execTrailPct`), still defaulted the TP rungs 30/40, and still called `strategy.exit()` on a 0% rung.
All three were ported, so the two forks are back on ONE ladder with nothing pinned around a gap. **Not ported, deliberately:** `execSlLevel`
(the SL fib dropdown) is meaningless here because the B leg's stop is its band origin, not a fib; and
the pink blocked-trade markers, whose codes describe why an **SOS Fade** setup was refused — in this fork
SOS Fade never trades, so those tags would report the opposite of what a reader would assume. A B-LEG
block tag would need its own code set, which is new design work, not a port.

**That non-port now also holds on the PYTHON side (2026-07-27).** `sos_fade`'s `Execution` gained
`blocks` (the same six codes, feeding the lab price chart's Blocked layer). This fork records none by
CONSTRUCTION: the recording hangs off the parent's `_place_entries`, which `BLegExecution` overrides.
`test_this_fork_records_no_blocked_setups` pins it, so restoring the parent's entry path here can't
quietly switch on tags that would mean the opposite of what they say.

**Same call for the MISSED-setup markers (2026-07-27), but this one is NOT free.** The parent's miss
watch scores how far an **SOS Fade** setup got before it died (2 of 3 / 3 of 3) — meaningless in a fork
where SOS Fade never places an order. Unlike the blocks it runs from `step()`, which this fork delegates
straight to the parent, so it takes an explicit class-level opt-out: `BLegExecution._records_misses
= False`. `test_this_fork_records_no_missed_setups` pins it — a flag is far easier to flip by
accident than an overridden method. A B-LEG version of either marker needs its own code set (what
would "2 of 3" even mean for a frozen band?), which is new design work, not a port.

## The recorded fib (2026-08-11) — this fork records its OWN, and the convention is the design

**Unlike the blocked and missed markers above, this one IS ported — and it had to be built rather
than inherited.** The lab's price chart draws a `Fibs` layer from `Trade.fib`, a ladder the strategy
snapshots when it places the order. That snapshot lives in the parent's `_place_entries`, which this
fork overrides, so **every B-LEG trade carried `fib=None` and the chart offered no Fibs row at all**
— on the bot whose entry, stop and first target are all fib levels of one leg.

**`execution._band_fib(ext, inv, direction, leg_ms)` builds it from the frozen band's own anchors.**
Not from `sig` — the parent's `_freeze_fib` reads the live **Structure** fib, which is a different
leg on a different bar, so inheriting it would have attached a real, fully populated, entirely
plausible ladder describing something the trade was never priced against.

🔴 **THE CONVENTION IS THE WHOLE OF IT, BECAUSE THIS FORK SPEAKS THE OTHER ONE.**

| | measured from | entry | band far edge | stop | TP1 |
|---|---|---|---|---|---|
| this fork's own vocabulary (`bleg.py`, the Pine) | leg ORIGIN | 0.5 | **0.382** | — | — |
| what is RECORDED (`fib_level`, the SOS Fade bot's) | leg EXTREME | 0.5 | **0.618** | 1.0 | 0.0 |

Same two prices, two namings — and `BLegState`'s own docstring already assumed the second one when
it called `*_inv` *the leg origin (fib 1.0)*. The record uses the DRAWING convention so a ratio
means one thing on a chart showing both bots' fibs. **The one visible consequence is that the band's
far edge draws as 0.618**, which reads as wrong until you know it is the same line named from the
other end. `tests/test_bleg_fib.py::test_the_band_far_edge_is_recorded_as_0_618_not_0_382` pins it
in both directions.

Rules that hold it together:

- **All eight rungs, and four are COMPUTED** — through the canonical
  `engines.fibonacci.geometry.fib_level()`, never inline arithmetic. A four-rung ladder reads as
  *this trade had no 0.786* when the level exists on that leg and the bot merely did not act on it;
  the SOS Fade ladder has the identical all-or-nothing rule.
- **The ratios are byte-identical to the SOS Fade bot's, asserted by test.** That also keeps every rung on
  a named factory colour in the browser rather than falling through to grey.
- **`*_ext` / `*_leg_ms` are frozen WITH the band and re-frozen on a migration.** The deepest-band
  rule can replace a band mid-watch, and a kept leg beside a moved band would draw one leg's fib
  around another leg's entry.
- ⚠ **`*_ext` is NOT `*_tgt`.** The target keeps tracking the expansion extreme after the freeze and
  runs past the leg, so reusing it would stretch the ladder to wherever price went.
- **An undatable leg records NOTHING.** A swing predating the replay window has no honest x-anchor,
  and drawing from the entry bar would hide the retracement the fib exists to show.
- **Reporting only** — no rule reads `*_ext`, `*_leg_ms` or `Trade.fib`, so `compare_bleg.py` is
  structurally unaffected (exit 0 at warmup 800, and the baseline reproduces at 99 / +17.8674R).

⚠ **It needed four reporting-only fields on `Signals`** (`bull_bos_high_ms` and its three siblings),
read straight off the structure engine's long-published `bull_bos_h_loc` etc. **Nothing in the
engine changed** — the leg's bar positions were there the whole time and nobody had threaded them
through.

⚠ **EXISTING B-LEG RUNS NEED A RERUN.** The ladder is written into the run's own equity curve at
replay time, so *Rebuild chart* cannot supply it.

## Sizing — sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True` (like the SOS Fade bot): `qty = equity·exec_risk_pct /
stop_distance`, so the lab's dynamic sizing engine leaves it alone and `exec_risk_pct` is the
risk knob. Registered as class `BLegStrategy` (distinct from `SosFadeStrategy`), so both
register and run side by side — the parallel-stack use case.

## The parity gate — `tools/compare_bleg.py` + `b_leg_strategy_export.pine` (built 2026-07-26)

### The unsettled tail is a DAY, and the pivot lookahead was too small (2026-09-03)

🟢 **GREEN on a fresh 15m export — `engines/VANTAGE_XAUUSD, 15_b480e.csv`, 21,702 bars compared,
exit 0 at warmups 100 / 500 / 1000.**

🔴 **THE TRIM ADDED ON 2026-09-02 WAS SIZED TO THE SWING LOOKAHEAD AND DID NOT COVER THIS FORK'S
OTHER UNSETTLED DEPENDENCY.** It inherits SOS Fade's DAY-HIGH liquidity line, which is time-based: on
the fresh export Python placed a new Day High at 2026-09-03 00:45 and swept it while Pine still
pointed at the previous one, **65 bars from the end — four times outside a 15-bar trim.** ~230
COMPLETED day boundaries in the same file agree exactly, which is what says settling rather than a
bug. The trim is now the export's final calendar day, **floored by `major_length`** so a file
ending minutes into a new day still covers unconfirmed pivots.

⚠ **`unsettled_tail` is IMPORTED from `sos_fade/tools/compare_strategy.py`, not copied** — this
gate already imports that module's decoders, and two copies of a trim rule is how the two drift.
SOS Fade hit the identical defect the same day; the transferable half is that **a sibling gate's tail
constant is sized to ITS unsettled dependency and does not transfer**, and neither does a bar count
fitted to one export.

🔴 **`test_the_tail_is_the_pivot_lookahead_and_nothing_wider` IS RETRACTED AND RENAMED.** Its claim
— one bar wider and the gate skips settled bars — was right about padding and wrong about the set
of things that do not settle. **It stayed green through the whole period the gate was red.** The
constant is now a FLOOR, and the widening is measured rather than "to be safe".

⚠ **Three mutations SURVIVED the entire suite when this landed** — reverting the trim to the bare
constant, dropping the lookahead floor, and disabling the empty-window refusal. The first was
caught only by one real export on one machine, which is exactly the fragility rule 22 warns about.
Three tests now cover them; all three were watched RED.


🟢 **GREEN, re-run 2026-08-23 on `engines/VANTAGE_XAUUSD, 5_f8228.csv` — 20,573 M5 bars, identical
from bar 0, no warmup needed.** ⚠ Rule 14 still applies: it says the two AGREE, never that either is
RIGHT, and nothing about a branch neither entered. 🔴 **The export before it was RED, and the code was
innocent — a stale twin reds this gate exactly like a bug does.** Before hunting a defect, check which
side is older: prove the red at HEAD first (it was), then look at the export's date.

`strategies/tradingview/b_leg_strategy_export.pine`
= `b_leg_strategy.pine` (body byte-identical, only the line-40 `strategy()` title differs) + an
appended PARITY EXPORT block. Export it from a 15m XAUUSD chart, then:

```
command-center/backend/.venv/bin/python strategies/python/b_leg/tools/compare_bleg.py <export.csv> --warmup N
```

Exit 0 = bar-for-bar identical. It is also registered in `backtest/tools/verify_parity.py`, so the
one-shot "is everything in sync?" run covers the B leg now.

**What it diffs, and why it is NOT a flag on `compare_strategy.py`.** The two bots diff DIFFERENT
fields. In this fork SOS Fade never places an order, so:
- `px_dec_bits`' arm bits are the **B-LEG** arm (`bLegLongArm`/`bLegShortArm`), not `longArmed`.
  Diffing `longArmed` here would test a decision that never happens.
- `px_edge` is the frozen band's 0.5 edge, not an FVG edge.
- `px_tp1`/`px_tp2` are their own columns because the B leg derives its ladder from the band
  (TP1 = 2·edge − origin, TP2 = the expansion extreme) instead of reading fib levels.
- `px_stages` IS still diffed: the B leg arms off the SOS Fade sequence's death, so an SOS Fade stage drift is
  where a B-LEG mismatch usually ORIGINATES. It turns "a trade differs" into "the upstream moved".

What IS shared — the packed `cfg_*` decoding — is imported, not duplicated: both export Pines plot
`cfg_*` with one identical scheme on purpose, and `compare_strategy.config_from_export` now returns
the caller's config CLASS, so passing a `BLegConfig` gets one back with `bleg_max_days` intact.
`allow_bleg=True` is needed because the SOS Fade decoder (correctly) REFUSES an export with `execBLeg` on,
and this fork's export always ships it on.

**The `bl_*` columns are the point.** They carry the TRACKER's own state — `bl_bits` (on/tap per
side), `bl_bars` (the armed bar per side, packed as bar+1 so 0 = none), and the four band prices per
side (top / bot / inv / tgt). Every new B-LEG rule lives in the tracker (band freeze, deepest-band
migration, target track, tap, staleness death), and a bug there shows as a wrong band price MANY bars
before it becomes a wrong trade. Without them a mismatch says "a trade differs" and nothing about why.

**Two things that are NOT in the export, deliberately:**
- `execSlLevel` — the fork has no such input (the B-LEG stop is its band ORIGIN, not a fib on the SOS Fade
  leg). `cfg_strcodes`' SL slot is pinned to the "1.0" code so the shared decoder reads
  `exec_sl_level = "1.0"` — correct-and-unused here, and one decoder keeps serving both exports.
- The Diagnostic Log block, dropped in the export copy to stay under Pine's token cap (CE10117),
  exactly as the SOS Fade export does.

**Regenerate it whenever `b_leg_strategy.pine` changes** — the split point is exact and is
recorded in the export's own header (`sed -n '1,4486p'`, then re-append the block and restore the
line-40 title). A new trade-affecting input = a new `config.py` field + a new `cfg_*` plot + a new
read in `compare_bleg.config_from_export`, in the SAME commit as the Pine change.

Offline guard: `tests/test_compare_bleg.py` (8 tests) round-trips the tool — run the bot, serialise
its own decisions + tracker state into an export-shaped CSV using the Pine's packing, feed it back,
require exit 0 — then plants a `bl_l_top` mismatch and a `px_dec_bits` mismatch and requires the tool
to catch each at the right bar. The encoder there is written from the Pine's plot expressions rather
than from the tool's decoder, so it also catches the two drifting apart. It uses 30 synthetic days,
not 10: on 10 no leg ever ARMS, so the `bl_*` diff would prove nothing.

Two of those eight cover the **partial-export** case added 2026-07-31 — one re-packs `bl_bars` as
if the chart held 15,362 bars before the export's first row and requires exit 0, the other shifts
all but ONE armed bar and requires that odd one to still be caught. They are a pair on purpose:
the first alone would pass just as happily if the tool had stopped diffing the bar index at all.

### PARITY GREEN 2026-07-31 (exit 0) — the session-window build

`compare_bleg.py "VANTAGE_XAUUSD, 15_cabec.csv" --warmup 800` → **exit 0**. 6,329 bars,
2026-04-27 → 2026-07-31. Green at warmup 1200, 2000 and 3000 too, so nothing late is hiding
behind the skip.

**Why the warm-up is 800 and not 100.** This export is a partial chart — it starts 15,362 bars
into the loaded history, so Pine walks in already holding a frozen band that the Python side has
never seen. It has to wait for a whole fresh band to form. That is cold start in the ordinary
sense, just a longer one than a from-bar-zero export needs; the same run at `--warmup 400` fails
only on `bl_s_top`-style band prices Pine carried in, never on a decision.

**What it proves that the 21k-bar 2026-07-29 run could not.** The window is entirely inside
BST/EDT, which is exactly where the new city-clock session windows differ from the old fixed
GMT-4 ones. `b_leg_strategy.pine` had been a genuine fork on those windows; a Python side
still on the old offsets would have disagreed with Pine on every session boundary here. Config
decoded off the export: `cfg_exitmode = 20` (the ratchet trail), `cfg_trail_pct = 1`,
`cfg_tp1_pct = cfg_tp2_pct = 0`, `cfg_bleg_days = 1.25`, risk 10%, `aplus_window = 4320`.

Exercised: 605 / 695 bars with a live long / short leg, 2,063 bars armed, **2 entries, 2 trades
graded, sum 5.73R**. The usual caveat applies harder than ever on a 3-month window — that trade
count proves the two implementations agree and says nothing about the edge.

**It also found the harness bug described in "Last reviewed"** — the raw `bar_index` comparison.
Worth restating as a rule: a round trip proves the two halves agree, and a full-history export
hides an origin assumption, so **the first PARTIAL export is its own kind of gate.**

### PARITY GREEN 2026-07-29 (exit 0) — the ratchet build

`compare_bleg.py "VANTAGE_XAUUSD, 15_ab202.csv" --warmup 100` → **exit 0**. 21,493 bars,
2025-08-31 → 2026-07-29. Green at warmup 200, 500, 1000 and 2000 as well, same cold-start
picture as the first run.

This is the run that clears the 2026-07-28 stale-export warning. What makes it non-vacuous is
what the export DECODED, not just the bar count: `cfg_exitmode = 20`, `cfg_trail_pct = 1`,
`cfg_tp1_pct = cfg_tp2_pct = 0`. The tens digit of `cfg_exitmode` is the trail method, and it
went 2-way → 3-way when the ratchet landed. An OLD export would have decoded the ratchet as
the plain structure trail and gone green while comparing two different exit ladders — this one
carries the third code, so the Python side really was configured to the ratchet.

5 trades graded, **sum 10.91R** over the window. That trade count is the same warning as ever:
enough to prove the two implementations agree, nowhere near enough to tune against.

### PARITY GREEN 2026-07-26 (exit 0) — first real export

`compare_bleg.py "VANTAGE_XAUUSD, 15_9b74a.csv" --warmup 100` → **exit 0**. 21,231 bars,
2025-08-31 → 2026-07-24. Green at every warmup from 100 to 2000, so the ~100-bar skip is genuine
engine cold start, not a mask.

**The run was not vacuous** — it exercised the machinery this harness exists to check:

| what | count |
|---|---|
| bars with a live long / short leg | 2,195 / 1,010 |
| bars tapped (long / short) | 568 / 141 |
| bars ARMED (long / short) | 2,024 / 862 |
| entries taken (long / short) | 2 / 3 |
| trades closed and graded in R | 5 |
| distinct frozen band prices diffed | 48 long / 45 short |

So the band freeze, the deepest-band migration, the target track, the tap and the staleness death
were all diffed against Pine across ~90 distinct bands — not just the 5 bars that became trades.
That breadth is the whole reason the `bl_*` columns exist.

**The first run found a bug — in the HARNESS, not the port.** `bar 680 px_entry_dir: py=1 pine=-1`.
`_py_row` derived the trade direction from `Fill.qty`'s sign, but `qty` is NOT signed in this
codebase — `Fill.dir` is. Every short read as a long. Fixed to read `Fill.dir`.

**Why the round-trip test could never have caught it:** the test's encoder had the identical wrong
derivation, so encoder and decoder agreed and the round trip passed. A round trip only proves the
two halves are consistent with each other, never that either is right. That is the structural limit
of the technique, and it is why a real export is the gate.
`test_entry_direction_comes_from_fill_dir_not_qty_sign` now asserts against the FIELD rather than
against a round trip — the only way a shared-mistake bug like that gets caught offline. Apply the
same shape to any future packed column whose value is DERIVED rather than copied.

**Config decoded off the export** (all of it correct): `bleg_max_days` 1.25, SOS Fade-priority ON,
`execBLeg` ON, Structure trail, TP2 floor = TP1 price, TP1/TP2 30/40%, risk 10%.

Backtest numbers are now validated logic, not directional guesses — with the standing caveat that
**5 trades is far too thin a sample to tune against.** Parity says the code is right; it says nothing
about whether the edge is real.

## The 6.5-year measurement — 2026-08-04 — 🔴 **SUPERSEDED, AND KEPT AS THE RECORD OF WHY**

⚠ **EVERY NUMBER IN THIS SECTION IS DEAD. Do not quote it.** It measures the configuration that
existed on 2026-08-04, and **three defaults moved on 2026-08-06** — `bleg_max_days` 1.25 → 4.0,
`exec_trail_pct` 1.0 → 0.05, `exec_time_stop_hrs` 36 → 8 (see the two 2026-08-06 header entries).
Re-measured on 2026-08-09 over the same 155,531 bars, by two independent drivers that agree to the
cent: **99 trades, +17.87R**, free. Charged over the full history: 114 / +17.56R / PF 1.45 /
maxDD **−5.15R**. The drawdown is the real change — it used to be nearly double SOS Fade's and is now
slightly under it.

⚠ **The section stays because the STATISTICAL argument in it is still the right argument**, and it
now points the other way: 99 trades is still not many, and **no jitter audit has ever been run on this
bot**, so +17.87R has no error bar. SOS Fade's equivalent measured a run-to-run spread of sd 15.06R —
larger than B-LEG's entire total. Read the CI reasoning below, substitute today's numbers, and the
honest verdict is *"positive and not yet distinguishable from noise"* rather than *"no edge"*.

🔴 **The lesson is about the DOCS, not the bot.** This file's header recorded the new numbers on
2026-08-06 the same day they were measured. `docs/LIVE_TRADING_PIPELINE.md` → G15 and the root
`CLAUDE.md` went on quoting −0.94R for three days, and those are the two files a decision is read
out of. **The number was corrected where it was produced and not where it was consumed.**

---

That last sentence was finally acted on. **Nothing above this line changes** — parity is still green
and the code is still right. What is new is that the bot has been *replayed*, rather than validated,
over a real window.

```
python backtest/tools/run_report.py --strategy b_leg --start 2020-01-01 --end 2026-08-03
```

**155,453 M15 bars, 50 trades, −0.94R.** No cost layers (the free baseline, comparable to the
Strategy Tester). Win rate 34%, average win +1.65R, average loss −1.01R, expectancy −0.02R/trade,
peak-to-trough **−15.62R**.

| | trades | sum R | mean R | 95% CI on mean R | max DD (R) |
|---|---|---|---|---|---|
| `sos_fade` | 161 | **+135.94** | +0.84 | **+0.29 → +1.40** | −7.99 |
| `b_leg` | 50 | **−0.94** | −0.02 | **−0.40 → +0.37** | −15.62 |

**Read the CI column, not the sum R column.** SOS Fade's interval is entirely positive — 6.5 years of gold
is enough to say its edge is real. B-LEG's straddles zero and is centred on it: its true 6.5-year
total belongs anywhere between −20R and +18R, and no amount of staring at the −0.94 will narrow that.
This is the one place where `CLAUDE.md`'s "sample size arrives at the portfolio level" argument does
**not** apply: that rule says do not reject a strategy for trading rarely, and this is not a rejection
— it is the statement that the measurement cannot yet distinguish this bot from a coin.

⚠ **Everything here is about the SHIPPED DEFAULTS.** `exec_tp1_pct`/`exec_tp2_pct` = 0/0 and
`exec_sl_level` = "1.0" are **pinned to this fork's Pine for parity**, which is a correctness
decision, never a performance one. Lab run `096432c2ad20` ran 30/40. Read the table as "the
parity-pinned configuration has no measured edge", never as "the B-LEG setup does not work".

⚠ **The obvious next move is also the dangerous one.** Optimizing over 50 trades will find a winning
combination whether or not one exists. If it is done: state the out-of-sample split **before** the
grid runs, and expect the honest answer to be "not enough data", because `sos_fade_optimization.md`
Run 12 already showed on the SOS Fade bot that buying trade count by loosening a rule loses money.

⚠ **`--no-regime` was passed** on this run (the regime tag is reporting-only and does not touch a
trade). The "by regime" answer for B-LEG has not been measured and is a genuinely open question — the
2021–2023 losing stretch and the 2024–2026 recovery could be regime or could be noise at n=50.

## The exit-ladder re-default — 2026-08-06

Two defaults moved. Both are FORK PINS in `config.py` and matched defaults in
`strategies/tradingview/b_leg_strategy.pine` + its export; neither is inherited, and neither should be
"reconciled" with the SOS Fade parent, whose own measurements say the opposite in both cases.

| | `exec_trail_pct` | `bleg_max_days` |
|---|---|---|
| was | 1.0 (inherited) | 1.25 (`maxval` 3) |
| now | **0.05** | **4.0** (`maxval` 6) |
| SOS Fade parent | keeps 1.0 — its sweep gives 0.25% → 43.6R vs 109.3R at 1.0 | n/a, B-LEG-only input |

**Charged (spread + swap, `vantage_demo`), 186,312 M15 bars, 2018-09-13 → 2026-08-05:**

| | trades | sum R | PF | wins | max DD | IS | OOS |
|---|---|---|---|---|---|---|---|
| old defaults | 59 | −1.73 | 0.94 | 21 | −16.00R | −8.15 | +6.42 |
| **shipped now** | **112** | **+12.02** | **1.23** | 37 | **−8.89R** | **+0.78** | **+11.24** |

Free book at the new defaults: 112 / +17.64R / PF 1.36 / maxDD −6.21R.

**The protocol, because at n≈60 the protocol is most of the evidence.** The split was declared
before any row ran (IS 2018-09-13 → 2022-09-30, OOS after). Every row is a REAL REPLAY of the full
window; IS/OOS are computed by splitting the resulting trade list on entry time, which is safe here
only because it splits the OUTPUT of one identical run and therefore cannot change which trades
exist. Levers were measured ONE AXIS AT A TIME off the shipped baseline, never as a grid — a grid
over 60 trades finds a winner whether or not one exists, and this file said so before the work
started. The two that survived their own axis were then combined and re-checked in both halves.

⚠ **The reason to trust the combination is the FLATNESS, not the peak.** PF is 1.18–1.25 across the
whole 4×3 grid of trail step {0.05, 0.08, 0.10, 0.15} × staleness {3, 4, 5}. Every cell beats the
old PF of 0.94. There is no sharp optimum to have fitted to.

⚠ **It is still not an edge.** 95% CI on mean R = **−0.140 → +0.355**, i.e. the 7.9-year total
belongs anywhere in −16R to +40R. The top 3 trades are 100% of the total and the single best is
+5.07R of it. What genuinely improved is the drawdown, the sample size and the sign of the first
half — all three of which are what a live decision is actually made on, and none of which is proof.

### Rejected, with the reason each was worth trying

- **The minimum-stop guard** (floors 0.10%–0.40% of price, prototyped as a `_place_entries`
  subclass): no effect that survives both halves. The hypothesis was reasonable — this fork's stop
  distances span $2.51 to $49.02 and `qty = risk / dist`, so the tight end buys a position a single
  15m gold bar can traverse whole — and it is simply not where the money goes. ⚠ **The cheap
  estimate disagreed and was wrong in the usual direction**: deleting the refused rows from the
  finished 50-trade list scores a 0.25% floor at **+6R**, the real replay scores **zero**. This
  file's warning about entry-side filters and the one position slot, reproduced on demand.
- **The deeper band edge** (rest at `l_bot`, the 0.618 retrace, instead of `l_top`): PF 2.43,
  maxDD −4.58R, and **28 trades with +15.81 of its +17.25R in the first half**. Fill rate collapses
  112 → 28, which is the real cost and the reason the headline PF is meaningless.
- **Shorts only**: PF 1.58, IS −1.15 / OOS +14.82. A bet on gold's 2023-2026 run wearing a filter.
- **Dropping the SOS Fade priority gate** (`exec_aplus = False`): this file has called it the first tuning
  candidate since 2026-07-24. It adds exactly one trade over 7.9 years and that trade loses.

### Open lead — the Asia-session filter (NOT shipped)

Refusing entries in the Asia session and the late-day window gives **79 trades / +12.32R / PF 1.37
/ maxDD −4.98R**, positive in both halves (IS +2.89 / OOS +9.42) — the best drawdown of anything
measured, on Aaron's stated objective. Two independent samples agree: the original 50-trade baseline
had Asia at −5.0R on 13 trades. The mechanism is plausible (Asia is the thinnest book for gold, and
this fork's tightest stops are the ones a thin-book wick reaches).

**It is not shipped because it is new code, not a default.** Neither `b_leg_strategy.pine` nor
this package has a session filter for the B-LEG arm; adding one is a Pine input + a `cfg_` column +
the Python gate + a parity re-run, in one commit. It is also the most curve-fit-prone thing measured
here — slicing 112 trades by session is exactly the shape that finds a pattern in noise — so it
needs its own out-of-sample statement before it ships, not this one reused.

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/b_leg/tests/ -q
```
Offline. Hand-traced `BLegTracker` (band maths, arm, tap, staleness + invalidation death,
deepest-band migration, BLEG_MAX conversion) + end-to-end driver run + longs/shorts-off.

## 🔴 This gate refuses a sub-15m export too, and the green above was re-checked (2026-08-23)

This fork's engine config is the parent's with one field replaced, so it inherits the
parent's **15-minute gap pins** while its Pine reads those two values off the CHART. Below
15m the two sides are configured differently before a bar is replayed, so `compare_bleg.py`
REFUSES rather than reporting a mismatch. Full reasoning and the measurement that forced it:
`strategies/python/sos_fade/CLAUDE.md` → *The gate REFUSES an export from a chart faster
than 15m*.

✅ **The M5 green recorded above STANDS, and it was re-measured rather than defended.** That
export was replayed a second time with the sub-15m pair the Pine actually used and came back
green on every bar as well — so the difference provably decided nothing there. It could not:
a B-LEG entry rests on the frozen band, never on a gap.

🔴 **That is exactly why the check was still added.** *"It did not bite this time"* is a fact
about one export and one entry rule, and the next run gets no such promise. A green obtained
under a configuration mismatch is right by luck, and luck is not a gate.

**Tests:** 2 in `tests/test_compare_bleg.py` — the refusal and its deliberate override —
both watched RED by mutation.

## It is LISTED under the SOS Fade bot (2026-08-23)

The package names the SOS Fade bot as the row it is drawn beneath, so the strategies list shows the suite
the way it is actually carved up — one structure stream, each leg taking a different part of the
move — instead of an alphabetical list that hid the relationship entirely.

⚠ **DISPLAY ONLY.** It changes nothing about what this bot may be run with: standalone, in any stack,
on any instrument, exactly as before. Nothing but the list reads it. Full contract:
`command-center/backend/CLAUDE.md` → *A strategy may declare which row it is LISTED UNDER*.

## Do / Never

- **Do** port any change to `b_leg_strategy.pine`'s B-LEG block or execution here
  line-for-line, and any change to its SOS Fade engine into `sos_fade` first.
- **Do** keep `BLegConfig` a superset of `SosFadeConfig` — a new SOS Fade toggle should flow in for free.
- **Never** build a second copy of any engine or of the SOS Fade sequence here — reuse `sos_fade`.
- **Never** trust a backtest number until a `compare_bleg.py` is green on a fresh export.

## References

- Pine source of truth: `strategies/tradingview/b_leg_strategy.pine` (B-LEG block ~3683-3758,
  execution ~4429-4506).
- The SOS Fade bot it reuses: `strategies/python/sos_fade/CLAUDE.md`.
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.

## 🔴 The parent's re-entry ships ON again — this fork's pin is LOAD-BEARING (2026-08-27)

`sos_fade` has now flipped `exec_secondary` THREE times: ON 2026-08-07, OFF 2026-08-21, and ON
again 2026-08-27, this time as the **reclaim** re-entry banking all-out at 3.25x (Aaron's call).
**This fork's own pin is unchanged and still False**, so nothing this bot trades has moved.

🔴 **The pin is LOAD-BEARING again, not redundant — that is the change.** A fork that leans on its
parent's default is one flip away from breaking, and this field has now flipped three times.
The fork's own value is asserted first because that is what protects this bot; the parent's value is
pinned after it so a flip back to True surfaces in B-LEG's own test rather than as a
crash on a NotImplementedError.


## `exec_min_atr_pct` is PINNED off (2026-08-26)

The parent gained a dead-market entry floor
(`strategies/python/sos_fade/CLAUDE.md` → *The DEAD-MARKET floor*). This fork pins it to 0.0
rather than inheriting, for the same reason it pins the minimum-stop guard: `b_leg_strategy.pine`
has no such input, so an inherited value would put this bot's Python and Pine on different entry
rules with no gate able to see it.

⚠ **The pin is INERT TODAY and is kept anyway.** This fork overrides `_place_entries`, so it does
not currently reach the shared floor check the gate hangs off — but *"it overrides the method"* is a
claim about one call site and the sibling `bos` disproved it the same day. **A pin costs one
line; discovering an inherited entry filter costs a run nobody can explain.**

---

## Its chips say `B-LEG` on the price chart (2026-09-02)

`LAB_STRATEGY["chart_tag"] = "B-LEG"` — the late-retrace leg the package is named for. ⚠ **A LABEL: no run, no cost and no decision reads
it**, so changing it repaints chips and moves no trade. ⚠ **Keep it SHORT** — it is drawn beside the
entry price. Why it exists, what it does on a STACK, and why rule 22 is silent for it:
`command-center/backend/CLAUDE.md` → *A strategy names its own setup on the chart*.

## The frame it is measured on is DECLARED (2026-09-03)

`LAB_STRATEGY["suggested_bar_value"] = 15` — its measured book is 186,312 M15 bars, 2018-09-13 → 2026-08-05. The lab reads it and every form fills a leg's
timeframe box from it, so nobody has to remember which bot runs on which frame.

⚠ **It is a DEFAULT, never a refusal.** Nothing rejects a run on another frame — sweeping a bot
across frames is a real question — so a figure quoted off a different frame is a DIFFERENT
EXPERIMENT from every number in this file, and has to say so.

🔴 **Why it had to be declared: the stack page had ONE timeframe for the whole stack**, so a 5m
bot and a 15m bot on one account meant one of the two was replayed on a frame nobody has ever
measured it on — and the combined table said *portfolio*. Rules for the lab side:
`command-center/backend/CLAUDE.md` → *A stack leg runs on its own frame*.

## 🔴 The gate was RED for seventeen days and the CODE was innocent — the export was stale (2026-09-02)

`compare_bleg.py` failed at `px_l_stage: py=3 pine=2` on 2026-05-08 02:30. Nothing was wrong with
this bot. **The export was taken on 2026-08-16 and two STRUCTURE fixes landed after it** —
`700f7f65` (the tied-extreme duplicate swing) and `f4b0410b` (a break may not install a swing the
break itself refused). Both change the swing anchor the fib is measured from, so Python extended
its anchor where the older chart did not, which moved the 0.5 level below the bar's low and latched
the half-retrace the Pine never saw. A fresh export cleared it.

🔴 **THE PROOF THAT IT WAS THE EXPORT, NOT THE CODE, IS THAT THE TWO PINE EXPORTS DISAGREED WITH
EACH OTHER.** The SOS Fade export (2026-09-02) and the B-LEG export (2026-08-16) start on the same bar of
the same Vantage 15m chart, and at that timestamp one says stage 3 and the other says 2. **Python
matched the newer one.** Two exports of one chart disagreeing is a statement about WHEN they were
taken; nothing in either Python package can produce it.

⚠ **The diagnosis cost four wrong hypotheses, and every one was ruled out by MEASUREMENT rather
than by reading**: a re-armed SOS carrying its predecessor's latch (zero re-arms in the whole run),
the EQ/FVG coupling (flipping it moves no stage), the packed structure codes (they carry only the
stop level and the HTF flags), and the two fib toggles (Python already matched the export).
**A source comparison cannot settle this class of question** — the fib logic, the anchor
assignment and the inlined structure engine are all byte-identical between the two Pine files.

⚠ **This is the SECOND time a stale twin has reddened this gate** (the first is recorded under
*The parity gate*). **Check the export's DATE against the Pine's git log before hunting a defect**,
and prove the red at HEAD first — it was, in a throwaway worktree, byte-identical failure.

## The gate does not compare the UNCONFIRMED TAIL (2026-09-02)

The last `UNCONFIRMED_TAIL` bars of an export are skipped, and the number is **DERIVED from
`major_length`, never typed**. Swings come from `ta.pivothigh(high, majorLength, majorLength)`,
which cannot confirm a pivot until `majorLength` further bars exist — so an export pulled from a
LIVE chart ends with bars whose structure has not settled on the Pine side, and Python is entitled
to a different answer there. MEASURED on the fresh export: green on every bar except the last 10,
and trimming turned the whole run green.

⚠ **It is a REPORTING window, never a shortened replay.** Every bar is still stepped, so the state
carried into the compared bars is the state the whole export produced, and a real drift starting in
the tail still shows on the next export.

⚠ **It ANNOUNCES itself on every run, and the SUCCESS line carries it too** — *"every bar from N to
the last 15 (unconfirmed swings, not compared)"*. A silently-trimmed comparison printing PARITY OK
is a gate claiming ground nobody covered, which is the over-claiming green this repo keeps
recording. `--tail 0` diffs them anyway.

🔴 **A TEST DEFINED RELATIVE TO THE NUMBER IT POLICES CANNOT POLICE IT, and that was MEASURED here
rather than reasoned.** `test_a_mismatch_OUTSIDE_the_tail_is_still_reported` plants at
`len - UNCONFIRMED_TAIL - 1`, so widening the constant moves its own plant with it — a 10x widening
reddened nothing. The value is pinned separately by
`test_the_tail_is_the_pivot_lookahead_and_nothing_wider`, which asserts the DERIVATION rather than
the number 15. **Its docstring says what it cannot catch**, because a test naming the wrong
mutation reports coverage that is not there.

**Tests: 4 in `tests/test_compare_bleg.py`, 5 mutations each watched RED against its own named
test** with an unrelated control staying green. The first two are a PAIR — *it is ignored* alone
would pass just as happily if the diff had stopped reading that column.
