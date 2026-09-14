# CLAUDE.md — strategies/python/b_leg/ (the B-LEG bot)

**Purpose:** The B-LEG setup as a standalone Python strategy — a port of
`strategies/tradingview/b_leg_strategy.pine` (Aaron's brother's B-LEG fork of MPC-JARVIS). The
B LEG is the SOS whose retrace arrived LATE: an SOS Fade reversal dies at 2/3 on a continuation
BOS before it retraces, the Sniper-Zone band (0.382–0.5) of that break is frozen, and a
resting limit at the 0.5 edge waits for the late return.
**Sweeps:** `b_leg_optimization.md`, next to this file. 🔴 **THE FIRST SWEEP RAN 2026-09-07 AND
NOTHING BEAT THE SHIPPED SETTINGS** — 8 settings one at a time, charged, on **PU Prime demo ECN**
(Aaron's call: the attached terminal and the account these bots trade), so **no figure there may be
compared against the Vantage numbers below.** Read its *basis* and its CONTROL — **116 trades /
+21.18R / PF 1.55 / maxDD −6.42R** (+20.76R until adding to winners was pinned off, 2026-09-10), which
every later sweep asserts — before quoting any of it.
**Scope:** This bot only — its tracker, order layer, config, tests. It does NOT own the
engines (`engines/`), the replay runner (`backtest/`), or the SOS Fade machinery it reuses
(`strategies/python/sos_fade/`).
**Status:** Built + unit-tested + **Pine-parity GREEN on a COMMITTED golden (2026-09-10, `exports/golden/`, step 15)**; earlier re-validated 2026-07-31
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

## Sizing — sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True` (like the SOS Fade bot): `qty = equity·exec_risk_pct /
stop_distance`, so the lab's dynamic sizing engine leaves it alone and `exec_risk_pct` is the
risk knob. Registered as class `BLegStrategy` (distinct from `SosFadeStrategy`), so both
register and run side by side — the parallel-stack use case.

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/b_leg/tests/ -q
```
Offline. Hand-traced `BLegTracker` (band maths, arm, tap, staleness + invalidation death,
deepest-band migration, BLEG_MAX conversion) + end-to-end driver run + longs/shorts-off.

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

## Risk per trade is PINNED at 10 (2026-09-13)

`sos_fade`'s default moved 10 → 5 to match its live share, and `BLegConfig` inherits the field —
so it is pinned at 10.0 here, the value `b_leg_strategy.pine` ships and `b_leg_demo` states.
Nothing this bot trades moved, and its side of the overlap audit did not drift (step 17 flagged
only SOS Fade's). ⚠ **A fork inherits its parent's defaults as well as its code** — pin, never
follow, a parent's decision about a different bot.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 60 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/inherited_design.md` — The inherited exit ladder and the recorded-fib convention

**Read before touching:** the exit ladder, the TP1/TP2/SL overrides, the blocked/missed-setup markers, or the Fibs layer this bot draws on the price chart.
Most-cited code: `BLegConfig`, `BLegExecution`, `b_leg_strategy.pine`, `strategies/tradingview/b_leg_strategy.pine`, `compare_bleg.py`, `sos_fade_strategy.pine`.

- The exit ladder is inherited (2026-07-26)
- The recorded fib (2026-08-11) — this fork records its OWN, and the convention is the design

### `notes/parity_gate.md` — The parity gate — build history, refusals and gotchas

**Read before touching:** `tools/compare_bleg.py` or `b_leg_strategy_export.pine`, or before trusting any parity result this gate has produced.
Most-cited code: `tests/test_compare_bleg.py`, `b_leg_strategy.pine`, `BLegConfig`, `config.py`, `compare_bleg.py`, `tools/compare_bleg.py`.

- The parity gate — `tools/compare_bleg.py` + `b_leg_strategy_export.pine` (built 2026-07-26)
- 🔴 This gate refuses a sub-15m export too, and the green above was re-checked (2026-08-23)
- 🔴 The gate was RED for seventeen days and the CODE was innocent — the export was stale (2026-09-02)
- The gate does not compare the UNCONFIRMED TAIL (2026-09-02)
- ✅ This fork's shipped default is back inside its gate (2026-09-07 → 2026-09-10)
- 🔴 The gate REFUSES an export missing a column it compares (2026-09-10)
- Its gate tests replay once per distinct input (2026-09-10)

### `notes/measurements.md` — Superseded measurements and the exit-ladder re-default

**Read before touching:** quoting a historical B-LEG performance number, or re-opening the exit-ladder tuning question.
Most-cited code: `config.py`, `strategies/tradingview/b_leg_strategy.pine`, `b_leg_strategy.pine`.

- The 6.5-year measurement — 2026-08-04 — 🔴 **SUPERSEDED, AND KEPT AS THE RECORD OF WHY**
- The exit-ladder re-default — 2026-08-06
