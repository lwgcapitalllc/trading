# Notes — The backtest price chart's data

ChartSpec candles and every overlay the backend builds: blocked and missed setups, gaps, order blocks, sessions, liquidity, candlesticks, adds, fibs, exit ladder, re-entries. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## ChartSpec candles — cap the WINDOW, never the timeframe

6.5 years of M15 is ~160k candles and a ~15 MB `chart_spec.json` on every chart open. Something has
to give. There were two axes to give on, and the first choice was wrong:

- **Coarsen the bars** (the old `_fit_timeframe`: that run shipped **H4**). Covers the whole span —
  and is useless, because H4 is a timeframe the run's trades and blocked setups line up with nowhere.
  It also forced a fetch-on-open to get back to M15, which meant a loading placeholder and a visible
  swap on every chart open.
- **Trim the window** (`_capped_start`, 2026-07-27, Aaron's call). Ship the run's OWN timeframe over
  the newest slice that fits `_CANDLE_CAP`. Measured on that same run: **33,041 candles / 3.1 MB /
  17 months**, painted on the first frame with no fetch at all.

Reach is restored by PAGING, not by coarsening: `historyStartMs` (the run's start) tells the panel how
far back it may go, and scroll-left pulls one page at a time through `GET /runs/{id}/candles`
(measured: 175d / 11,255 candles / ~1.0 MB / ~1.5s at M15). So trimming costs reach, not access.

**And a page carries the window's ANALYSIS, not just its bars (`analysis=true` → `_page_analysis`,
2026-08-02).** For a year that was only half true: the bars paged in and everything drawn ON them —
structure overlays, fair value gaps, blocked and missed setups — did not, because all of them are
built over `candles` and `candles` stops at `ship_from`. Scroll past that boundary and each layer
the reader had switched on drew nothing, with its toggle still on. Two rules hold it together, both
pinned by `tests/test_chart_page_analysis.py`:

- **Warm-up is context, not content.** The structure and FVG engines are streaming state machines,
  so a page is replayed over its window PLUS `_PAGE_WARMUP_BARS` (2,000 ≈ 30 trading days at M15)
  of older bars, and only overlays whose span reaches into `[from_ms, to_ms]` are returned. Without
  the prefix every page opens with no swings and no live gaps; without the filter the previous
  page's overlays are served twice.
- **A page's internal structure is HISTORIC** (`_demote_page_internal`). `build_market_structure_overlays`
  labels the newest leg in whatever it replayed "current", so each page would claim its own current
  leg — a group whose whole meaning is "the leg the run is in NOW", which exists only in the shipped
  window. The demotion carries the historic branch's own `requires` shape so the four toggles keep
  nesting.

It is best-effort and wrapped in its own `try`: the page is about its BARS, and a failed replay must
never cost the reader the history. Drill-down passes `analysis=False` — structure is computed on the
base timeframe, and a 1m view is a question about fills.

`baseTimeframe` and `runTimeframe` are now the SAME value. `runTimeframe` stays on the contract
because a `chart_spec.json` cached under the old scheme still carries a coarsened `baseTimeframe`,
and the panel opens on `runTimeframe` — which keeps those caches usable until they rebuild. Every
cached spec was cleared when this landed; they rebuild on next chart open (~5s for a 17-month M15).

## Blocked setups — the trades that never happened

A signal the strategy had READY and one of its OWN rules refused places no order, so it appears in
no trade list, no equity curve, no `engine_trades`, and no broker report. Nothing downstream can
infer it. That makes it impossible to judge whether a blocking rule protects the account or costs
it — which is the whole reason this channel exists.

The path is one straight line, and every hop is OPTIONAL so a runner that can't report them is
simply silent (never a lie, never an empty UI):

1. **The strategy records them.** `sos_fade/execution.py` — `BlockedSetup` + `_record_blocks`,
   a port of `sos_fade_strategy.pine`'s pink `TRADE BLOCKED` tag (4025-4086): the same six reason codes,
   the same PRECEDENCE, and the Pine's `sosBar*10 + code` dedupe generalised to the reason SET (one
   record per setup per distinct combination, not per bar). **One deliberate deviation:** the Pine
   reports the FIRST blocker only (a chart tag has room for one line); we record EVERY rule refusing
   the setup, because the lab filters by reason and "blocked by the veto" must stay true when the
   final hour was also blocking. Precedence survives as the ORDER, so `codes[0]` is exactly what
   `f_blkCode` would have returned — a per-reason count off the primary still reconciles with
   TradingView. **Reporting only** — nothing reads a record back, so it cannot move a decision and
   `compare_strategy.py`'s `px_*` stream is untouched. `b_leg` records none by construction (its
   `BLegExecution` overrides `_place_entries`, where the recording hangs) — deliberate: those codes
   describe why an **SOS Fade** setup was refused, and SOS Fade never trades in that fork.
2. **`backtest/output.py`** — `build_blocked_setups()` turns them into the lab's row shape;
   `build_results` returns them as `blocked_setups` (always present, `[]` when there are none).
   Strategy-agnostic duck-type: `dir`/`time_ms`/`edge` plus parallel `labels`/`reasons` sequences,
   emitted as a `reasons: [{label, reason}]` LIST (primary first).
3. **`backtest_runner._handle_complete`** writes `reports/lab/<run_id>/blocked_setups.json` when the
   runner reported any. Runner-agnostic — NT8/MT5 return no such key, so no file.
4. **`chart_spec._build_blocks`** reads that file into the spec's `blocks[]`, clipped to the candle
   window (same reason trades are). No file ⇒ `[]` ⇒ the chart's Blocked toggle never appears. The
   chart builds its per-reason filter roster straight off those label strings, so nothing between the
   strategy and the UI needs to know what any rule means.

**Only runs completed AFTER this landed have the file** — it is written at completion, and there is
no backfill (recomputing it would mean replaying the strategy). An older run's chart correctly shows
no Blocked layer. A run that HAS the file but a stale cached `chart_spec.json` needs **Reload charts**.

The `label`/`reason` strings are the STRATEGY's own words end to end; neither the lab nor the chart
interprets them, so a strategy with a different rule set needs no change anywhere in this path.

## Missed setups — how close the ones that died came

A **block** and a **miss** answer the same question one step apart in a setup's life. A block is a
trade the strategy had FULLY READY and one of its own rules refused. A miss never got that far: it
met some of the strategy's confluences and then DIED. Both place no order, so both are invisible
everywhere else; separately they answer "is this rule costing me?" and "what am I actually waiting
on that never arrives?".

The path is the block path, hop for hop, and every hop is equally optional:
`sos_fade/execution.py` (`MissedSetup` + `_record_misses`, a port of the Pine's orange 2-of-3
callout — see that package's CLAUDE.md → *The missed-setup watch*) → `backtest/output.py`
`build_missed_setups` → `missed_setups.json` in the run dir → `chart_spec._build_misses` →
`spec.misses[]` → the price chart's **Analysis → Missed** layer, default OFF.

**The one thing that is NOT a copy of the block path: `spec.missNoise`.** `_build_misses` returns a
second value — the reason labels the chart should start with UNTICKED — and it is **derived, never
named**. A label goes on the list when it never once appears on a miss the strategy flagged `near`.
Why this exists: the Pine's callout defaults to "Near misses only" because a chart showing every
setup that simply never retraced is unreadable, and on the measured window that is 50 of 93 markers.
Reproducing that default by teaching the chart what "No retrace" means would have put a strategy
concept inside a panel whose one rule is that it has none. Instead the strategy marks `near`, the
emitter turns it into a list of strings, and the panel hides those on first render. The panel still
lists them with their counts, so nothing is hidden silently, and one click brings any of them back —
which the Pine's radio buttons cannot do.

⚠ **A miss's `time` is the bar the setup DIED, and nothing may read it as "where the setup was".**
`zoneTime` / `zoneTurn` carry that instead — the retrace it was waiting on, recorded by the strategy
(2026-08-08). ✅ **Measured on the reference run: on 32 of the 35 three-of-three misses, price sits a
median $22 and up to $205 from the setup's own entry edge on the death bar, and the death bar is a
median 17 and up to 717 bars after the turn.** The Candlestick Reversals layer read `time` for one
day and painted marks in the wrong part of the chart because of it. Both are `None` when price never
reached the zone, and `None` must stay `None` — a fallback to `time` is the defect, a `0` is the
epoch.

Same on-disk-shape discipline as the blocks: a record missing `near` reads as `near: True`, so a
file written before the flag existed does not have every one of its reasons filed as noise and
hidden on open (which would make an old run look like it had no misses at all). Locked by
`backend/tests/test_chart_spec_misses.py`. **Python runner only, no backfill** — same as the blocks,
for the same reason.

## Fair value gaps — only where something happened

⚠ **The Pine sources these overlay services cite moved on 2026-08-13** — `.pine` files were split
into `indicators/strategies/` and `indicators/engines/` by their DECLARATION, so `structure_overlays.py`
now points at `indicators/engines/structure_engine.pine` and `fvg_overlays.py` at
`indicators/engines/mpc_jarvis.pine`. Comments only; no overlay geometry moved and no stored run
re-renders. A path here from before that date is stale.

🔴 **The equal-level constants here were 2 / 0.1 / 6 until 2026-09-09 and the indicator runs
2 / 0.25 / 14**, so this chart drew a different equality band and a different level cap from the
TradingView chart it mirrors — and those levels feed the gap cap exemption, so the GAPS drawn moved
too, not just the levels. Synced, with `tests/test_fvg_overlays.py` pinning them. ⚠ **This is a
DISPLAY consumer — no strategy reads it, so nothing traded differently** — but a chart that quietly
disagrees with the chart it is a copy of is how somebody concludes the engine is wrong. ⚠ **Six
files carried these three numbers; a default duplicated six ways is a default that drifts.** Full
record and the measurement: `engines/equal_highs_lows/CLAUDE.md`.

`services/fvg_overlays.py`. Replays the canonical `engines/fair_value_gaps/` engine over the candles
the chart is about to show and emits one `box` overlay per gap, in the group `Fair Value Gaps`, which
the panel lists in its **Analysis** dropdown (default OFF). Never a second FVG engine — bare-name
import, public events only, same shim as regime / news / structure.

**A gap is drawn only if it was in the engine's LIVE list on the bar of a trade ENTRY, a blocked
setup, or a missed setup.** That filter is the whole design: a 33k-bar run leaves thousands of gaps
and drawing them all is both unreadable and an answer to a question nobody asked. When several gaps
were open at one of those bars, ALL of them are drawn — a cluster is exactly the thing worth seeing.
The anchors arrive as bare timestamps (`trades[].entryTime` + `blocks[].time` + `misses[].time`), so
the module knows nothing about what a trade or a block IS; hand it different anchors and it draws
gaps at those. No anchors ⇒ `[]` ⇒ the toggle never appears, which is the honest answer for NT8/MT5.

**⚠ These are `mpc_jarvis.pine`'s gaps, and that is not always the set a bot traded on.** The
indicator runs a cap of 7, `eqExemptFvg` on, and two settings SPLIT by timeframe — below 15m a 0.0
floor and no middle-bar close test, from 15m up a 0.1% floor and the close test.
🔴 **They are READ from `engines/fair_value_gaps/` at draw time since 2026-09-10**, which carries both
rows once and is held to the Pine by `engines/tests/test_defaults_mirror_the_indicator.py`. This layer
typed its own `MPC_*` copy until then — cap 8, a 0.04 floor from 15m up, no close test on any frame —
which the indicator had left behind, **so on 15m and above it drew gaps TradingView does not.** A
display consumer, so nothing traded differently. ⚠ On 15m this is now the SOS Fade bot's own gap set
too (it pins 7 / 0.1 / close test / exemption on) — two Pines agreeing today, not a design. A
strategy's Pine can still differ (`bos` keeps a cap of 8 and the 0.04 floor), so do not resolve that
fork by repointing the emitter at a strategy's config, and do not read a drawn gap as one a "no FVG"
block ignored. Background: `engines/fair_value_gaps/CLAUDE.md`.

**Two details that would silently draw the wrong thing if they broke**, both pinned by tests:
- **The floor and the close test are timeframe-split**, so the same run charted at M5 and M15
  legitimately has different gaps. An unrecognised timeframe takes the STRICTER (15m+) row on purpose: over-filtering drops a
  marginal gap, under-filtering invents one the indicator never drew, and only the second puts
  something on the chart that is not there.
- **Box span mirrors the Pine box.** Pine creates it at `bar_index - 1`, pushes `box.set_right` every
  surviving bar, and DELETES it on the bar the gap is mitigated or evicted — so `t1` is the bar
  BEFORE its death, never the death bar. On the death bar mpc showed nothing there.

`build_stack_chart_spec` **strips this group**, for the same reason it strips blocks and misses: it
is anchored to the BASE leg's trades, so on a merged chart it would draw gaps at one strategy's
entries and nothing at the others' — which reads as "these setups had gaps and those didn't". A leg's
own page still carries it. Existing runs need **Reload charts** (`chart_spec.json` is cached).

**Tested two ways** (`tests/test_fvg_overlays.py`, 18 tests). Hand-built candles pin the layer's own
rules (which gaps, the cluster case, the box span, which timeframe row each frame gets, that a 15m gap
whose middle bar never cleared is NOT drawn, that the cap is read from the engine at draw time). Then a
real TradingView export is replayed and every box is diffed against **the Pine's own live gap arrays**
(`px_fvg_top_k` / `px_fvg_bot_k` / `px_fvg_count`): on each sampled anchor bar the boxes covering it
must be exactly the gaps mpc had open, price for price. The unit tests could all pass on an emitter
drawing the wrong gaps; that one could not. The export is git-ignored, so those two SKIP without it —
and it predates the 2026-07-18 mpc default drift, so it is replayed with the settings ITS build ran
(which is what the config keyword arguments on `build_fvg_overlays` exist for). That the ENGINE still
matches today's mpc build is proven separately by `engines/fair_value_gaps/tools/compare_fvg.py`.

## Order blocks — the same rule, a different box

`services/ob_overlays.py`. Aaron's brother asked to see order blocks on the backtest chart, so the
canonical `engines/order_blocks/` engine is replayed server-side and a block becomes one `box`
overlay in the group `Order Blocks`, listed in the panel's **Analysis** dropdown, default OFF.
Never a second OB engine — bare-name import, public events only, the same shim as the rest.

**It is deliberately the fair-value-gap layer with one engine swapped**, down to the anchor rule: a
block is drawn only if it was live on the bar of a trade ENTRY, a blocked setup or a missed setup.
MEASURED on run `432aff31f374` (32,978 M15 candles, 217 anchor bars): **2,567 blocks created,
579 live at an anchor** — the same ratio the gap layer sees (661 there), so the two together sit at
a readable ~1,240 boxes instead of ~3,200. Read `## Fair value gaps` above first; only the
differences below are worth carrying separately.

**THE BOX IS A STUB, NOT A LIVE-BAR TRACKER — this is the one thing that would silently look
plausible if it were wrong.** A gap box tracks the current bar. An order block box is created at
`[origin_index, created_index]` and then every surviving bar sets

    right = obNear ? max(bar_index + 1, origin + OB_STUB) : origin + OB_STUB      (OB_STUB = 30)

so it is a fixed 30-bar zone that stretches to the live bar only while price has come back within
one block-height of it, and it is DELETED the bar the block dies. That uniform width is the point
(`mpc_jarvis.pine:170-181`): it is what makes a set of zones scan as one family of levels rather
than a ragged row, and drawing them gap-style would put a rectangle spanning the whole session under
every old level. Two consequences that are correct and look like bugs:

- **A block's box can end long before the block does.** The zone stays live and keeps answering
  anchors for hundreds of bars after its 30-bar box stopped.
- **A block's box can end AFTER the bar it died on** — the stub runs past the live bar into empty
  space, so the last frame it was drawn on reached further right than its death bar. Emitting the
  death bar instead would trim every zone the reader actually saw.

**No settings fork to warn about, unlike the gaps.** The strategy files dropped order blocks entirely
on 2026-07-24/25, so `mpc_jarvis.pine` is the only source and the engine defaults ARE its
constants. The flip side is worth saying out loud: **`sos_fade` reads no block, so a drawn block
never explains an entry** — it is context the reader brings, not a rule the bot applied. The one Pine
input not modelled is `obDirOnly` ("Trend-Aligned Zones Only", default **off**), which HIDES blocks
opposing structure; it is a drawing filter and `engines/order_blocks/CLAUDE.md` names it as something
this layer must not bake in.

`build_stack_chart_spec` strips this group alongside the gaps, for the reason it strips both: the
anchors are the BASE leg's trades, so on a merged chart it would draw zones at one strategy's entries
and nothing at the others'.

⚠ **`tests/test_ob_overlays.py` (18 tests) has NO "and the boxes are the Pine's blocks" half, and
that is a stated gap.** The gap layer's tests cross-check every box against the Pine's own live
arrays in a real export; the three OB exports on disk (`engines/order_blocks/exports/`) all predate
the 2026-07-31 re-port — six slots, no `cfg_ob_*` columns, `compare_ob.py` refuses them outright —
and no post-re-port export is on this machine. So what is proven is that the EMITTER faithfully turns
the engine's events into mpc's boxes; that the ENGINE matches the Pine is proven separately, and was,
on a 21,691-bar 15m export and a 13,186-bar 5m one (`engines/order_blocks/CLAUDE.md` → Validation).
**Re-run `compare_ob.py` on the next real export**, and add the box-vs-array half here when one lands.

## The chart's session windows are the INDICATOR's, and two of the three were not

🔴 **Fixed 2026-08-08** (Aaron confirmed `mpc_jarvis.pine` is the correct source). `chart_spec`'s
`_FX_SESSIONS` shaded **Tokyo 09:00-15:00** and **London 08:00-16:30** against the indicator's
**09:00-18:00** and **08:00-17:00** — so two of the three session boxes on a backtest chart were
SHORTER than the boxes on the TradingView chart the run is read against, and nothing on either screen
said so. New York already matched, which is what made it look plausible.

⚠ **The engines already agreed with the indicator; this file was the only dissenter.**
`engines/sessions/engine.py`'s `SessionEngine.DEFAULT_SESSIONS` has carried
`Asia 0900-1800 / London 0800-1700 / NY 0800-1700` since the 2026-07-31 re-sync, and
`engines/liquidity/` composes it for the session H/L levels. So this was a **third statement of one
fact**, and the two that were right had been right for a week.

**The fix is pinned by COMPARING the two, never by restating the windows a third time**
(`tests/test_chart_spec_sessions.py`, 4 tests, **the one in this pass that could be WATCHED RED**).
A test hardcoding `09:00`/`18:00` would be a fourth copy, and the next re-sync would leave it stale
and green — which is the same disease one level down.

⚠ **The display names stay `Tokyo`/`New York` where the engine says `Asia`/`NY`, deliberately.** The
panel keys its per-session toggle state on `name`, so renaming would silently reset a reader's
switches; these are legend labels, not an identifier anything resolves through.

⚠ **A window is stated in its own city's clock, and that is what makes it DST-aware** — it does not
move when that city changes its clocks, while its UTC span does. Re-stating one as a fixed GMT offset
would be wrong for ~7 months a year and would look right for the other five.

## Liquidity levels — and WHICH POOLS PRICE HAD ALREADY TAKEN

`services/liquidity_overlays.py` (2026-08-08). Aaron asked to be able to read, off the backtest
chart, that liquidity had been swept for the daily, the New York session, the H4 and so on. The
canonical `engines/liquidity/` engine is replayed server-side and each level becomes an `hline` in
one of three groups. **It is that engine's FIRST consumer** — it was written, Pine-parity-validated
in July 2026 and then imported by nothing for a year, which is why nothing in this app could answer
the question until now.

**It is the anchor rule again — and here the rule is doing real work rather than being inherited.**
A liquidity level is not rare the way an order block is: every day mints a PDH and a PDL, every
session close a high and a low, and the H4 tier rolls SIX TIMES A DAY. ✅ **MEASURED over the full
history of run `1bbc8fa7773d` (155,891 M15 candles): 35,028 levels created, of which 20,376 — 58% —
are H4.** That is past `_MAX_PER_GROUP` (20,000), so drawing everything would have been a **silent
truncation of the oldest levels**, which is the half a reader scrolls back to and the exact defect
the structure layer's cap was raised to fix. Anchored to trade entries / blocked / missed bars it is
**8,174 levels, 4,608 of them swept** — the same order as the gap layer's 2,822 — and it answers the
question actually asked rather than papering the chart.

**THREE groups, not one**, and this is the one place it departs from the gap and block layers. The
tiers differ by an order of magnitude in volume and in meaning: H4 alone is 58% of the levels, so a
reader following daily and session sweeps wants it off and a reader timing an entry off the last H4
candle wants only it. The indicator gets away with one switch because it only ever draws the ~13
levels that are live RIGHT NOW.

⚠ **This is therefore NOT the same VIEW as the indicator's, and the difference is structural rather
than a fork to be closed.** `mpc_jarvis.pine` draws the live set and nothing else — it never shows
you a level from 2021, because there is no 2021 on a live chart. This layer draws the historical set
at the bars that matter. The two agree completely about what a level IS and disagree about which ones
are on screen.

🔴 **THE ENGINE MUST BE CONSTRUCTED WITH `hide_mitigated_on_new_day=False`, AND THE DEFAULT IS THE
TRAP.** Its default is `True` — the Pine's `i_currentDayOnly` tidy — and that tidy is GATED on
`not showMitLiq`, which went **TRUE** in `mpc_jarvis.pine` on 2026-08-07 (a swept level now freezes
dotted and grey instead of vanishing). So today's indicator never runs the tidy. Left at the default,
every swept level older than the current NY day is evicted before it can be drawn: the layer would
still render live levels, still look correct, and **be missing the one thing it exists to show.**
⚠ **Its test needed a SPARSE anchor set to catch that, and the first version was VACUOUS** — anchored
on every bar the two settings agree exactly (72 swept either way), because a level is marked seen on
the bar it is swept, before any later tidy can reach it. With one realistic anchor: **6 kept against
1 tidied.** Production is 944 anchors over 155,891 bars, i.e. the sparse case.

**BSL/SSL is DERIVED for every tier except h4, and the derivation is CHECKED rather than trusted.**
The Pine labels a swept high `BSL` and a swept low `SSL` on every tier (`liq_dh`, `liq_ash`, …), while
the engine models `sweep_label` on the **h4 kind alone** — the one tier whose Pine block prints the
tag on the chart. `sweep_label_for` therefore takes the engine's answer where it exists and derives
from the side otherwise. A derivation sitting beside a value something else computed is this repo's
most-repeated defect, so `test_the_derived_sweep_label_agrees_with_the_engines_own` runs the two
against each other on real h4 sweeps and asserts it checked at least one.

⚠ **`_origin_bar` scans back for the candle that MADE the level**, mirroring the Pine's
`f_originHigh`/`f_originLow`. A level is created on the first bar of the period AFTER the one that
produced it, so anchoring the line there starts every line a whole period right of the candle it
describes. It is geometry over candles the caller already holds — the engine still owns the PRICE —
and it scans from `created_index` BACKWARDS, never from the live bar, or it would find a bar that
re-touched the level later and draw the line from the sweep instead of from the origin.

⚠ **`label` is a TOP-LEVEL field on the overlay, not a `style` key.** The panel reads `ov.label` and
spreads `style` separately, so a label nested in `style` type-checks, survives the round trip and
simply never draws — leaving unlabelled lines on the layer whose entire job is naming which pool went.

⚠ **The tiers are dropped from a STACK spec** alongside the gaps and blocks. A level is a property of
the market rather than of a strategy, like the structure overlays that ARE kept — but what is
leg-specific is not the level, it is **which levels were selected for drawing**, and that selection is
the base leg's alone. A market fact filtered through one strategy's anchors is not a market fact.

✅ **Driven end to end through the running backend, not only unit-tested**: a real `?refresh=true`
rebuild of run `bc2143e547b8` (23,706 candles) in 2.3s returns 385 liquidity overlays across the three
groups, **208 of them swept**, carrying labels like `PWL swept · SSL`, with all 13 tier names present.

**Tests:** `tests/test_liquidity_overlays.py` (17). ⚠ **A fail-watch against HEAD is VACUOUS for all
of them** — the module did not exist — so non-vacuity came from **MUTATION**, and seven mutations are
recorded in the docstrings with the test each one turns red. 🔴 **Two of them did not bite on the
first attempt and the two causes are different, which is why both are written down:** the label-nesting
mutation never APPLIED (wrong indentation — a no-op edit proves nothing in either direction, so it was
re-run rather than recorded as a pass), while the origin-scan mutation applied cleanly and left its
test GREEN — that test was genuinely vacuous on a FLAT feed, where every bar spans the same high and
low so the creation bar satisfies the assertion exactly as the true origin does. It uses a trending
feed now.

🔴 **AND THE MUTATION HARNESS ITSELF WAS SILENTLY BROKEN FIRST, WHICH IS THE MOST TRANSFERABLE PART.**
A mutate-run-restore inside one second leaves the file's **mtime AND size unchanged**, so Python
reuses the cached bytecode and the "mutation" tests the unmutated module. It presented as a test that
stayed red after the source was restored byte-identically (`diff` clean, `grep` showing the right
values, `__file__` pointing at the right path) — because `__file__` names the SOURCE even when the
module was loaded from a `.pyc`. ⚠ **On macOS there is no local `__pycache__` to clear**:
`sys.pycache_prefix` is `~/Library/Caches/com.apple.python`, so `find . -name __pycache__` returns
nothing and the stale bytecode is somewhere else entirely. **Any mutation or fail-watch loop in this
repo must delete that prefix path (or sleep past the second) between steps, or it proves nothing and
looks like it proved something.**
## Candlestick reversals — which candle turned price, where a setup existed

`services/candle_overlays.py` + `chart_spec.reversal_anchors`. Aaron's ask (2026-08-08): *"I'm
trying to see if these candle patterns line up with my reversal where I took the trades, or the
ultimate reversal point before the trade went into my favour"* — so that he can later ask whether
candlestick patterns are worth adding as a confluence. The canonical `engines/candlesticks/` engine
is replayed over the run's own candles and every pattern candle in a setup's SPAN is repainted navy.
Never a second engine — bare-name import, public events only, the same shim as regime / news /
structure / fvg / ob.

**It is read at `CHART_PRESET`, NOT the engine's defaults** (trend 117 / doji 0.01 / eleven
patterns). Those are Aaron's brother's TradingView inputs, taken off a real export's own `cfg_*`
columns rather than transcribed; the engine mirrors its source Pine (5 / 0.05) and a CONSUMER pins
what it reads. Repointing this at the defaults would make the chart stop matching the indicator it
is read against — pinned by a test.

### 🔴 The rules match his indicator and the PRICES do not — 16% of marks disagree, and no rule change can close it

**MEASURED 2026-08-09, after Aaron reported eight candles that "are obviously engulfings" and were
not marked. Two of the eight are genuine misses and the cause is not in this file, in the engine, or
in the Pine — it is the BAR FEED.** This chart draws the run's own candles, which come from the MT5
cache (`backtest/cache/XAUUSD__M15.csv`). The indicator he is comparing against runs on
TradingView's feed. Same broker, same symbol, different tape.

✅ **20,053 shared bars, the export's own `px_*` flags as the reference, engine at `CHART_PRESET`:
the two feeds sit a systematic 6 cents apart (median close difference −0.060), and that alone
produces 600 marks his chart draws that this one misses plus 515 it draws that his does not —
15.9% of every mark he sees.** Bearish engulfing alone: **150 missed of 914.**

🔴 **A CONSTANT offset would flip nothing** — every clause here is a comparison between two prices,
so a whole-feed shift cancels — **so the damage is entirely the INTRA-BAR variation**, and it is
larger than the offset. On his 2025-12-09 16:45 case the two feeds disagree by 14 cents on the open
and 3 cents on the prior close, i.e. **17 cents on the one comparison that decides the rule**:
TradingView clears `open >= close[1]` by +0.09, the cache misses by −0.08. Every other clause passes
on both. That bar is the trade's adverse extreme, so the miss also changed the CHIP — the name fell
through to the `Inverted Hammer` on the next bar, which is how the reader noticed.

🔴 **A TOLERANCE WAS MEASURED AND IS STRICTLY WORSE — this is now a number, not only the standing
rule in `engines/candlesticks/CLAUDE.md`.** Relaxing the two `>=` boundaries by an epsilon, scored
against his own flags over the same 20,053 bars (engulfings, both directions):

| epsilon | we miss | we invent |
|---|---|---|
| **0 (shipped)** | **243** | **190** |
| $0.02 | 143 | 664 |
| $0.05 | 95 | 822 |
| $0.10 | 65 | 900 |

**Two cents recovers 100 marks and manufactures 474.** The mechanism is that on a gapless intraday
feed a bar's open sits within a cent or two of the prior close as the ORDINARY case, so any slack
floods the rule rather than nudging it. **Zero is the minimum-disagreement setting by a factor of
two**, which is the opposite of what "just a few cents of feed noise, allow a few cents" predicts.

⚠ **The remaining six of the eight are not this layer's doing and the clause breakdown is the only
answer that shows it** — four fail the full-body engulf by **$0.01 / $0.05 / $0.06 / $0.01 on HIS
OWN prices**, and one passes the engulf and fails the 117-bar uptrend gate with price $13 below
where it was 117 bars back. His indicator does not draw them either, read straight off `px_bear_eng`
in his export rather than argued. ⚠ **Do not answer a report like this with an assurance that the
engine is parity-green** — it is, and it is beside the point; print the failing CLAUSE with both
feeds' numbers beside it.

⚠ **The honest options are: accept it, or change the CANDLE SOURCE — and the second is not
available**, because the chart must draw the bars the strategy actually traded or the marks stop
lining up with the trades. **Accepted, no code change (Aaron's call, 2026-08-09.)**

**The standing lesson is about what a parity gate covers.** `compare_candles.py` feeds the engine
the EXPORT'S OWN prices, so it proves the rules agree and can never say anything about the data a
consumer feeds them. Every layer was green and the reader still saw the wrong candle. **Before
claiming one system matches another, ask whether they are reading the same INPUT — a validated rule
on a different tape is a different answer.** It is the shadow diff's finding (`algos/tools/shadow_diff.py`,
2026-08-04) arriving in a second subsystem: there four cents of broker difference moved a resting
entry $10.12; here six cents moves one mark in six.

### The anchor set is trades and 3/3 misses, and nothing else

**`reversal_anchors(trades, misses)` is public and named for one reason: it is the thing about this
layer that has already been got wrong once.** Five of the eleven patterns fire on **5-9% of every
bar** (both haramis, both engulfings, hammer, inverted hammer — measured, see
`engines/candlesticks/CLAUDE.md`), so an unanchored layer paints roughly one bar in twelve and says
nothing at all.

🔴 **BLOCKED setups were anchors until 2026-08-08 and it is what made the layer look random.** 324 of
them on the reference run against 159 trades and 35 three-of-three misses — **two thirds of every
mark** — and since the Blocked layer defaults OFF, they painted navy candles in places the reader
could see no setup at all. Reported from the screen as exactly that: *"we are plotting candles in
places that we didn't take trades or missed 3/3 trades."* ✅ **Measured: 518 anchors / 424 marks →
194 / 153.** A 2/3 miss is out for a different reason — it was never a setup, so there is no *which
candle turned it* to ask; `of > 0` guards a record that counted no confluences at all, because
`0 >= 0` would otherwise admit the least informative record there is.

🔴 **A 3/3 MISS ANCHORS ON ITS RETRACE, NOT ON ITS OWN `time` — the second thing this layer got
wrong, reported the same day.** A miss is booked on the bar the setup DIED, and that bar is nowhere
near the setup: ✅ **measured on the reference run, price sits a median $22 and up to $205 from the
setup's own entry edge by then, on 32 of the 35.** So the marks landed in a part of the chart the
setup had nothing to do with — read off the screen as *"the reversal candle printed on the opposite
side, which doesn't make sense … I'm expecting it to be that price got into the zone for the trade
and there was a reversal candle."* The strategy now records the retrace (`zoneTime` / `zoneTurn`, see
`strategies/python/sos_fade/CLAUDE.md`) and the span runs between them. ✅ **MEASURED, old vs
new: the nearest mark to the setup's own entry edge goes from a median $20.67 to $3.16, and 21 of 35
misses get a mark where 9 did.**

🔴 **It CANNOT be derived here, which is why the strategy had to change.** The obvious cheap fix —
scan back from the death bar for a bar that traded through `edge` — finds one for **all 35**,
including the ten where price provably never reached the limit, because price crosses that level at
unrelated moments. It would have been confidently wrong and silent. ⚠ **A run made before the
strategy recorded those fields yields NO miss anchors at all, deliberately: drawing nothing is
honest about a question the run cannot answer, and drawing it in the old place is not. Rerun to get
them.**

⚠ **The parameter list is the guard.** There is no value you can pass that produces a block-anchored
mark, so the only way blocks return is somebody adding the argument — and a signature test fails in
front of them with the reason.

### An anchor is a SPAN, and every pattern candle in it is drawn

`(start, direction, end, outcome, entry_price)` → every bar from `start` to the end of the setup's
DRAWDOWN. Inside it sits the turn — the bar price ran furthest against the setup — and everything
before that is the retracement the setup was entered into. **A trade spans entry → exit, win or
lose; a 3/3 miss spans its retrace.**

🔴 **It painted ONE candle per anchor until 2026-08-08 and that lost the whole question.** Aaron:
*"you don't only have to give me the deepest candle — you could give me all the candles that would
have shown a possible reversal all the way up to the deepest one … so let's say I entered at the
fifty, but there was no reversal candles until 0.702, and then maybe 0.786. I could see, wow, I
could have taken a trade at 0.702 or 0.786."* Read with the **Fibs** layer on, each mark sits on a
rung, so the layer answers *which entry level had a candle behind it* — which a single mark can
never say. ✅ **MEASURED: 194 anchors → 971 marks.** 464 point with the setup, 409 are neutral, 98 point
against; 167 are their span's deepest. **140 of 159 trades and 27 of 35 three-of-three misses carry
a reversal candle at all.**

🔴 **The span runs `_CONFIRM_BARS` (2) PAST the turn, and that is not a fudge factor.** It is the
longest pattern the engine reads minus the bar it starts on. **A pattern is reported on the bar it
COMPLETES**, so the bar that MADE the extreme is usually the pattern's first bar rather than its
last. ✅ **MEASURED on 194 anchors: 37.1% carry a pattern ON the turn bar and a further 40.2%
complete 1-2 bars after it** — so ending the span at the turn threw away the reversal candle on
**four setups in ten**, reported off the chart as *"it's not showing the deepest candle pattern that
would have been the most perfect entry."* ⚠ **Do not tune it.**

🔴 **AND THE ZONE IS A REGION IN PRICE, NOT A STRETCH OF TIME — that one mistake produced FOUR
separate complaints across two rounds (2026-08-08 → 2026-08-09).** Every version that reasoned in
BARS was self-consistent and easy to test, and each one was wrong in a different direction. ✅ **All
MEASURED on run `e51d95f212e3`, 166 anchors:**

  - 🔴 **`turn + _CONFIRM_BARS` covered a fraction of the zone.** The bar that makes the adverse
    extreme can sit anywhere in the drawdown, so on a trade that tops out early and grinds sideways
    the span missed most of the red box. **On the 2026-06-18 short the turn is 02:00 and the trade
    stays above its entry until 05:30 — 21 bars of drawdown against a 9-bar span, holding THREE
    patterns of which ONE was drawn**, and that one was the opposing candle, so the chip read
    `no matching candle`.
  - 🔴 **Then the confirm tail leaked into the takeoff.** Adding `_CONFIRM_BARS` to the END of the
    drawdown rather than to the TURN is two free bars after price has already left the band — and on
    a trade that leaves the band into a rally, those two bars ARE the rally. **On the 2026-07-15 long
    the drawdown ends 17:15, the next bar rallies $16 clear, and the `Inverted Hammer` two bars later
    at 4060-4066 — $25 above the entry — was the trade's ONLY mark, so it named the chip.**
  - 🔴 **And the span opened at the ENTRY BAR**, so a trade that ran into profit first and only later
    came back to make its adverse extreme painted the whole excursion in between — **one turn is 112
    bars after entry.** Together those two put **255 of 1084 marks entirely on the favourable side.**
  - 🔴 **A LOSER WAS MARKED AFTER IT WAS CLOSED.** A stopped-out trade's adverse extreme IS its final
    bar, so `turn + _CONFIRM_BARS` reached past the exit into the next setup. Aaron, off the
    2026-05-11 short (stopped 13:30, a `Hammer` painted 14:00): *"Trade already lost. You already hit
    stop loss… I don't care what the candles after the trade. It has to be within the trade."*
  - 🔴 **And the contiguous-excursion fix went too far the other way.** Walking from the turn and
    stopping at the first favourable bar meant that when price came BACK to the entry later in the
    hold, the re-test fell outside the zone — while the chart's own red box plainly covered it. On
    the 2026-02-15 short that is two unmarked `Hammer`s: *"we came back up to entry. And there was at
    least three different candles you coulda highlighted there, and you didn't highlight any of
    them."*

✅ **The rule is now one price test and one clamp.** `_reversal_span` returns the whole hold — entry
bar → EXIT bar — and `_in_zone` draws a bar while ANY part of it trades on the adverse side of the
entry. That is the same test as *does this candle touch the red box*, which is what the reader is
pointing at. ⚠ **`_drawdown_end` is DELETED, and it could not be salvaged: no walk can express "and
again when price comes back" without also swallowing the profitable stretch in between.** ✅
**Driven through the live backend: 1090 → 853 marks, ZERO past any exit, 31 outside the band and
every one within `_CONFIRM_BARS` of the extreme.**

🔴 **A FOURTH defect fell out of the same audit and nothing had ever reported it.** `_anchor_bars`
took an end only `if j > i`, so **a trade that OPENS AND CLOSES INSIDE ONE BAR read as having no end
at all** and fell through to the `window` fallback — a 60-second trade with a THREE-BAR span reaching
43 minutes past its own exit. **MEASURED: 4 marks on 3 trades, one a `Bearish Engulfing` drawn after
a trade that lasted 4 minutes.** It is `j >= i` now; only an end BEFORE the start is genuinely
unusable.

⚠ **FOUR of the six candles Aaron named are NOT this layer's doing, and saying so needed the clause
breakdown rather than an assurance.** All four are IN the zone and would be painted the instant the
engine detected them — the engine does not, because `candle_sticks.pine:32` says
`bearEng = close[1] > open[1] and open > close and open >= close[1] and open[1] >= close and
open - close > close[1] - open[1] and open[trend] < open`:

  | candle | the clause that fails | by |
  |---|---|---|
  | 2026-06-16 13:00 | `open >= close[1]` — 4354.59 vs 4354.64 | **$0.05** |
  | 2026-04-06 09:45 | `open >= close[1]` — 4703.35 vs 4703.41 | **$0.06** |
  | 2026-01-30 00:15 | `open >= close[1]` — 5445.02 vs 5445.03 | **$0.01** |
  | 2026-06-18 05:30 | `open[trend] < open` — 4336.58 vs 4323.15 | the **117-bar uptrend gate** |

**On a gapless intraday feed a red bar opens within pennies of the prior close, so a full-body
engulf is decided at the cent** — and the trend gate refuses to call anything a bearish reversal
while price sits BELOW where it was 117 bars ago. ⚠ **Do NOT add a tolerance to close those gaps.**
A 0/1 flag has no "close enough", the same argument `engines/candlesticks/CLAUDE.md` makes for its
three boundary ties — and the engine matching the indicator Aaron's brother actually reads is the
entire reason this layer is trustworthy. His TradingView chart does not draw these four either.

⚠ **The confirm bars stay exempt from the band test, and that is why this is not JUST a price
filter.** A pattern is reported on the bar it COMPLETES, so on a sharp V the third bar of a Morning
Star is already back above the entry — and that bar IS the reversal candle. ✅ **MEASURED: dropping
the exemption leaves 40 trades with no mark against 21.**
⚠ **A 3/3 MISS passes NO entry price, so every bar of its span qualifies**: no position was opened,
so there is no entry to measure a band from, and its span is already the visit into the zone. It is
clamped to its death bar for the same reason a trade is clamped to its exit.

**Each mark also carries `spans`, `deepest` and `align`, and none of the three is derivable
downstream.** `spans` are the anchor indices whose span covers the bar (so the chart can badge a
trade), `deepestOf` are the ones it is the REVERSAL of — a LIST, not a flag, because one bar can be
the turn of one setup and an ordinary mark inside another's span — and `align` is its direction
**relative to the setup**. ⚠ **`align` is NOT `patternDir`** — that is the pattern's own direction,
and whether a bullish candle points the setup's way depends on the setup's SIDE, which a mark does
not carry and cannot: one bar can sit inside a long's span and a short's at once. ⚠ **`spans` is
collected for EVERY anchor covering a bar, not just the one that names it** — the dedupe decides the
name, and reusing it here would make a trade whose only pattern bar was already claimed report as
having none, which is the one thing the trade badge exists to say. ⚠ **`_anchor_bars` carries the
anchor's ORIGINAL index**, because it drops anchors off the loaded candles and renumbering would
mislabel every trade after the first drop, silently and plausibly.

⚠ **A LOSER carries its exit too, and it used to carry `None`** and get a 3-bar window. Its span is
the retracement it was entered into on the way to the stop, which is the same question. ✅ **MEASURED
on 106 winners: the adverse extreme sits a median of 2 bars past entry, p90 27, worst 112** — so a
fixed short window truncates the retracement on half of them.

⚠ **`_TURN_TOLERANCE_BARS` is GONE, and it was doing real damage.** It kept only patterns within 2
bars of the extreme, so on a long retracement it deleted every earlier entry level — exactly the
ones the request is about.

### Which candle a setup is NAMED after — and why the outcome flips it

🔴 **Fixed 2026-08-08, reported off two screenshots of WINNERS named with the opposing candle** (a
long reading `Won · Bearish Engulfing`, a short reading `Won · Bullish Harami`). The three-tier
direction preference below was real and was only ever applied to the patterns ON one bar; **which
BAR became the span's `deepestOf` was still nearest-the-turn, whichever way it pointed** — and that
is the one the trade's chip names and the one *"Only the deepest"* leaves on screen.

**`_wanted_direction(direction, outcome)` is the rule, and it is Aaron's:**

| anchor | wants | because |
|---|---|---|
| a WINNER | the setup-aligned candle | *"the BEST candle that helped or COULD HAVE HELPED signal the reversal"* |
| a 3/3 MISS | the setup-aligned candle | *"the DEEPEST CORRECT candle that I could have used to enter"* |
| a **LOSER** | the **OPPOSING** candle | *"the candle that signaled why I lost"* |

So the question is always *which candle explains what happened to this setup*, and it flips on the
OUTCOME rather than on the side. `reversal_anchors` carries a fourth element to say which.

✅ **MEASURED over the reference run's 194 anchors, old rule vs new:**

| | named as asked | neutral | named against | no candle |
|---|---|---|---|---|
| old | 69 | 54 | **44** | 27 |
| new | **98** | 59 | **10** | 27 |

Losers moved most — 33 named with an aligned candle → 4 — which is expected, since the aligned one
was the OLD ordering's first choice and is now the last.

⚠ **THREE tiers, and two was measurably not enough.** 59 of 194 spans contain no directional candle
at all (ten of the source Pine's fifteen rules gate on a trend lookback), so a `preferred or
anything` pool picks an OPPOSING bar whenever it happens to sit nearer the turn. Preferred → neutral
→ whatever is left, the same preference the within-bar ordering uses one level down.

⚠ **It orders the NAME and paints nothing differently.** Every pattern candle in the span is still
drawn in every direction — `test_the_outcome_changes_the_NAME_and_never_what_is_PAINTED` asserts
both readings of one span produce identical marks — because the opposing tier is half the point of
the layer. The chart's direction filter remains the only thing that hides anything.

⚠ **`deepestNames` is keyed PER ANCHOR (`{"0": "Hammer", "1": "Bearish Engulfing"}`).** One bar can
be the deepest of a losing trade AND a 3/3 miss on the same leg, and those two want opposite
directions; the bar's single `label` is whichever anchor reached it first, which is nobody's answer
in particular. The chart reads this for a trade's chip and falls back to `label`.

⚠ **A miss is `"miss"`, never `"loss"`,** even though no trade was taken — it is a setup that was
never entered, so it asks the winner's question. Filing it as a loss would name it after the candle
that beat a trade nobody had.

⚠ **An anchor with no outcome reads as a WIN.** Aligned is the answer for two of the three cases;
defaulting to the loser rule would name a healthy trade after the candle that beat it.

⚠ **The fallback to the whole span is deliberate and must not be tightened to nothing.** A setup
whose only candles point the other way still has a deepest one, and reporting *no reversal candle*
for a setup that plainly had one is the failure the opposing tier exists to prevent.

### "Deepest" is a PRICE, and an OPPOSING candle is never the NAME

🔴 **Two more defects, both reported off the chart on 2026-08-08, both in the same three lines.**

**(1) The fallback ranked by TIME.** When no pattern bar in the preferred tier reaches the turn, the
span still has a deepest one — and it was `pool[-1]`, the LAST bar in the span, which is *most
recent*, not *deepest*. ✅ **MEASURED on the reference run's 2026-06-16 short: the span holds eight
pattern bars including three Bearish Engulfings, and the last one is a Bearish Harami at high
4345.02, while the genuinely deepest aligned candle is the 11:00 Bearish Engulfing at 4349.27 —
$4.25 further into the retracement, i.e. the better short entry.** Aaron named it exactly:
*"the deepest best entry was on a bearish engulfing yet you did not highlight it."* `_deepest_bar`
reads the adverse extreme — highest high on a short, lowest low on a long. ✅ **Over 166 anchors the
deepest bar moves on 13 and the NAME changes on 8.** ⚠ **A pattern COMPLETING at or after the turn
still wins outright** (that IS the turn candle — see `_CONFIRM_BARS`); "deepest" only becomes a
question when nothing in the pool reaches it. ⚠ **Ties keep the EARLIER bar**, because the earlier
one is the entry you could actually have taken.

**(2) The name fell through to an OPPOSING candle.** Aaron, on a winning short reading
`Won · Bullish Harami`: *"Shouldn't it be a neutral candle, no candle or best yet a bearish
candle?"* — so the preference order ends at NEUTRAL and the honest answer below it is silence.
✅ **MEASURED: 9 of the reference run's 166 anchors hold nothing but opposing candles, and every one
was named after the candle arguing AGAINST the setup. After: 82 named as asked, 56 neutral, 19 with
no candle at all, 9 drawn-but-unnamed, and ZERO named against.**

⚠ **The bar stays in `deepestOf` and stays PAINTED — only the NAME is withheld.** Dropping it would
hide the opposing candle behind the panel's *"Only the deepest"* setting, and showing it is half the
point of the layer (*"it will show me why I was wrong"*). ✅ **846 marks either way, measured.**

⚠ **The chart says `no matching candle`, NOT `no candle`.** Three states, not two: `no candle` = the
span held no pattern at all; `no matching candle` = it held some and none pointed the way this
outcome asks about, so the marks ARE on screen and none of them earns the chip. Collapsing them
would report a setup that plainly had candles in it as having had none.

⚠ **The panel reads `deepestNames[anchor]` with NO fallback to `label` when the field is present.**
An object lacking this anchor's key is an ANSWER — the backend withheld the name — while the field
being ABSENT means a spec cached before per-anchor naming existed. `label` is the fallback only for
the second. The repo's own rule: never let "no" and "cannot ask" be the same value.

⚠ **A red candle is not a pattern, and this was asked directly** (*"why did you not highlight all the
bearish candles in the drawdown zone"*). The layer draws the engine's fifteen named RULES; a bar
being the right colour is not one of them.

🔴 **BUT THE MEASUREMENT ORIGINALLY WRITTEN HERE ANSWERED THE WRONG QUESTION, AND IT IS THE MOST
UNCOMFORTABLE ENTRY IN THIS SECTION.** It read *"its retrace zone is 9 bars and exactly ONE carries a
pattern"* — and **9 bars is the SPAN THE CODE WAS USING, not the zone the reader was pointing at.**
The trade's real drawdown is **21 bars and holds THREE patterns**. So a true number, measured
honestly, was quoted as evidence that nothing was missing — while it was in fact a restatement of
the very bug being reported, and it stood for a day until Aaron asked again. **When a reader says a
region is bigger than what you drew, measure the REGION THEY NAMED, never the one the code
computed** — the second can only ever agree with itself. The zone is the red box now (`_in_zone`),
and on that trade the layer draws all three. ⚠ **The same mistake was nearly made a second time the
next day**: four of the six candles reported on 2026-08-09 really were outside this layer's control,
and the only honest way to say so was to print each failing CLAUSE with its numbers — not to assert
that the engine had been checked.

✅ **5 new tests. The fail-watch against HEAD is VACUOUS and is recorded as such** — the module gained
`_deepest_bar`, so the whole test file fails to IMPORT at HEAD, which proves the import and nothing
else. Non-vacuity is by **MUTATION**: five mutations (the recency fallback restored, the opposing
name restored, unnamed bars dropped from `deepestOf`, the neutral tier dropped from the name, and
the deepest key hardcoded each way), each turning its own named test red. 🔴 **One of the five was
VACUOUS on its first TWO attempts and is commented as such** — with the high and the low on
different bars, a rule reading the wrong PRICE still returns the right index, because only the key
was mutated and the comparator is still chosen by direction. It needs one bar sitting INSIDE the
other.

### Direction orders the NAME on a bar, and never whether it is painted

🔴 **Selecting one candle per anchor is what put a `Bearish Engulfing` on a LONG that won** —
reported from the screen: *"we should have plotted a bullish candle if one was present."* That class
of error is gone by construction: nothing is selected, so nothing is suppressed. What direction still
decides is the NAME, in three tiers — **aligned → neutral → opposing**.

⚠ **An opposing candle is drawn like any other, and that is half the point of the layer**: *"if I'm
trying to take a short with a bullish candle printed, and that's why price reversed, yeah, highlight
that … if it lines up with my trades, then great. If not, it will show me why I was wrong."* ✅
**MEASURED across the 820 marks: 346 neutral, 259 bearish, 215 bullish.**

⚠ **The NEUTRAL tier is what does most of the work, and the reason is in the source Pine.** Ten of
its fifteen rules gate on a `trend`-bar lookback, so in an uptrend the bullish rules cannot fire at
all — which is precisely why the reference trade's mark was bearish. Hammer, Inverted Hammer and
Doji carry no trend filter and no direction, so they are the tier that rescues it.

⚠ **`label` is a CHOICE, not the first element.** 7.4% of bars carry more than one pattern (every
Hanging Man is also a Hammer by construction), so the chosen bar's list is reordered by the same
tiers — otherwise a bar printing both a Bearish Engulfing and a Hammer is named after the wrong one
on a long.

### Tests

`tests/test_candle_overlays.py` (46) + `tests/test_chart_spec_reversal_anchors.py` (9). ⚠ **A
fail-watch against HEAD is vacuous for a new module**, so non-vacuity is by MUTATION — each turning
a distinct test red: marking only the turn, running the span past the turn, anchoring a miss on its
death bar again, giving losers back their `None`, ignoring `hold_end`, dropping the dedupe, and
dropping the label reorder. Making direction a FILTER rather than an ordering turns
`test_with_NOTHING_but_an_opposing_candle_it_is_still_marked` red, which is the half worth guarding.

⚠ **Every fixture builds bars that make a REAL pattern fire and asserts that it did.** A test that
placed a mark by mocking the engine would pass against a layer reading the wrong bar, which is the
one thing worth checking here. ⚠ **Two fixtures were caught being wrong BY THE CODE**: a "no
pattern" bar was itself a Hammer, and replacing it with a long bearish body made its neighbours an
Evening Star — **a three-bar pattern is a property of the bars AROUND the one you are placing**, so
the fixtures now assert their own quiet bars are quiet.

## A trade that added — `trades[].adds`, and why a box could not account for its own P&L

**2026-08-18.** The chart drew run `295a6ff29d21` trade T137 as a SHORT entered at 4098.60 and
exited at 4085.07 — plainly in profit — with a "Lost" chip and a P&L of $0.00. Nothing about that
box was reconcilable, and nothing in the record explained it.

**Both halves were missing, and each is a different lesson.** The verdict was the sign test (see
`metrics.trade_outcomes` above): $0.00 is not a loss. And the P&L was right all along — the base
lot's profit had gone to a SCALE-IN ADD, a second lot bought later at a better price and closed at
the same exit. 🔴 **Every field the chart had described the BASE lot only** — `size` is the base
quantity, `legs` is the exit ladder, `favorable`/`adverse` are excursions on the base — so the one
fact that closes the arithmetic appeared in no field of the equity curve, the KPI row or the spec.

So `backtest/output.py` now carries the filled lots onto the curve point (`adds`) and this file
passes them through to `trades[].adds`, one record per lot. The panel draws a dotted `Add` line per
lot.

**Since 2026-08-20 a lot is TRADE-SHAPED** — `mfePrice`, `maePrice`, `exitPrice`, `exitTime`,
`exitReason`, `pnl` alongside the original three — so the panel's `Scale-in detail` layer can draw a
lot the way it draws a trade. Renamed to camelCase here because the chart defines that shape.
⚠ **Every field past `qty` is OPTIONAL PER LOT and is copied only when the strategy recorded it.**
🔴 **An absent field is never defaulted to `0.0`**, and this is the rule that matters: a lot reported
as exiting at price zero is a *measurement*, stated with the same confidence as a real one, and the
panel would draw a box from the fill price down to 0.00. Absent means nothing closed it. Same shape
as the bar cache recording a REQUESTED range as received, and as the live bot reading an empty bar
frame as a quiet market. Three tests in `tests/test_chart_spec_trade_outcome.py` pin it, including
the two independent halves (a lot measured but never closed keeps its excursion and omits the exit). ⚠ **The key is ABSENT on a trade that never added**, not `[]` — every trade of
every strategy without scale-in is that trade, and an empty list on all of them reads as a feature
that ran and bought nothing.

⚠ **A run finished before this shipped carries none, and there is no backfill** — the lots were
never recorded, so recovering them means replaying the strategy. Re-run the backtest. The
`outcome` verdict needs no re-run (it is derived from the stored curve), but a run's
`chart_spec.json` is CACHED and holds neither field until that file is deleted and rebuilt.

Tests: `tests/test_chart_spec_trade_outcome.py` (6) — the $0.00 trade, the band's two edges
($149 of a $1,000 median loss is a scratch, $151 is a loser), the ungraded run, and both halves of
the `adds` passthrough. **Each was watched RED by mutation**: grading on the sign alone reddens the
scratch cases and nothing else, and deleting the passthrough reddens only the lots test.

⚠ **`build_engine_trades` deliberately does NOT carry them.** That is the unit-size contract the
sizing engine re-sizes from, and it has no concept of a position that grew mid-trade — feeding it
adds would not make it model them, it would make it double-count the base. A scaled run is
therefore not something the sizing engine can currently re-size, and that is a known gap rather
than a solved problem.

## Trade fibs — the leg each trade was actually priced off

`chart_spec._trade_fib`. Aaron's brother asked to see, on every trade the chart plots, the fib run
on the points that trade used — which retracement levels it went into. The strategy records that
ladder when it places the order (`sos_fade/execution.py` → `TradeFib`), `backtest/output.py`
puts it on the equity-curve point, and this turns it into the chart's `trades[].fib`.

**The levels are PASSED THROUGH; only the two RATIOS are computed here.** That split is the whole
design. The prices are the ones the strategy had in hand at placement, so a chart and a bot can
never disagree about where a level sat — a fib rebuilt downstream from anchors and a direction is
a second claim about one leg, which is the failure this repo has now met four times (Run modal
costs, Optimize modal params, the SSH dot, the lab-vs-Pine parameter names). What a price ladder
CANNOT state is where the fill landed on it, and that is the question:

- **`entryRatio`** — the fill as a ratio (0.702 = it entered at the 70.2% retrace). On the SOS Fade bot
  this reproduces the entry model without being told about it: an entry snapped to a fib by
  `_fib_snap` reads exactly 0.618 / 0.702 / 0.786, and a gap-edge entry reads between two rungs.
- **`deepestRatio`** — the same for the deepest ADVERSE price of the hold, i.e. how far the
  retracement really ran after entry. **Not clamped at 1.0**: a trade that traded through the leg
  origin genuinely retraced past it, and clamping would report every stop-out as having stopped
  exactly at the origin.

⚠ **Both are computed and served, and since 2026-08-03 the chart draws NEITHER** — the panel's Fibs
layer prints the ladder only, and the trade's own `Entry` / `DD` annotations carry those two
price rows (with prices). They stay here because they are the two readings the ladder cannot state
and the derivation is pinned by tests; if nothing consumes them by the next chart pass, delete them
rather than leaving a field the UI implies it is showing.

Both are pure geometry off two levels the ladder already carries — a fib price is linear in its
ratio, so any two `(ratio, price)` pairs define the line and inverting it maps a price back. **No
anchor, no direction, no range**, hence no branch for a bear leg and nothing here that can drift
from the strategy. A degenerate (zero-height) leg returns `None` rather than dividing by zero.

`startTime` is the bar the LEG began on, not the entry — a ladder starting at the fill would hide
the retracement that produced it, which is the thing the layer exists to show.

**Optional end to end**, like blocks and misses: NT8/MT5 record none, and a Python run finished
before this landed has none (**no backfill — it would mean replaying the strategy**). ⚠ **`b_leg`
recorded none by construction until 2026-08-11 and now records its own**, off the frozen SOS leg
rather than this ladder — so a B-LEG run made before that date shows no switch and needs a RERUN,
not *Reload charts*. Nothing here changed to support it: this function is strategy-agnostic, reads
only `levels` and `start_ms`, and its two derived ratios are pure geometry — which is why a second
bot's ladder arrived with no backend edit at all. ⚠ **`entryRatio` reads exactly `0.5` on every
B-LEG trade** (its entry IS that rung, by construction), where on the SOS Fade bot the same field varies
and reproduces the entry model; do not read a constant there as a stuck value. The chart's Trade
fibs toggle is listed off whether any trade carries one, so
absence removes the switch instead of offering an empty layer. Existing runs need **Reload charts**
(`chart_spec.json` is cached). Tests: `tests/test_chart_spec_trade_fib.py` (12).

## The exit ladder — a rung is only a TARGET if the trade places an order at it (2026-08-21)

`chart_spec._tp_targets` + `_leg_label`, feeding `trades[].tpTargets` and `trades[].profitLegs`.

**The picture that found it.** Run `687c8df2a523`, the re-entry short of 2026-05-21 (T198): the
price chart drew **two chips reading `TP1`**, at 4,507.04 and at 4,491.99, on one trade. Neither
was a drawing glitch — they came from two independent naming schemes over the same record, and
nothing reconciled them.

**Defect 1 — a leg was named after the ORDER that carried it, not the price it closed at.** The
upper chip came from a leg whose exit-order id was `S-TP1`. The trade's TRAIL closed that rung at
4,507.04 while its first target sat 15 points further away at 4,491.99, and price never reached it
(deepest favourable of the whole hold: 4,504.09). A rung keeps its order id when something else
closes it — a trail, a time stop, a flip — so an order named for the first target routinely comes
off nowhere near that target. **13 of 205 trades on that run carried a green target chip sitting
short of the target it was named after.** `_leg_label` now treats the id as a CLAIM and checks it
against the rung it names: a leg that did not reach its own target price is `Exit`, whatever the
order was called. ⚠ **Reached is at-or-BEYOND, never equality** — a limit the bar opens past fills
at the open, i.e. better than its own price, and that is still the target filling. ⚠ **A rung the
trade reports no target for keeps its id**: absent evidence is not evidence against, and inventing
an `Exit` there would relabel every run stored before rungs existed.

**Defect 2 — a price with no order behind it was drawn as a target.** The same picture carried a
`TP2` chip at 4,505.43 for a rung that places no order at all. At sos_fade's shipped settings
`exec_tp2_pct` is 0 — nothing is ever sold there and a touch only steps the stop. Across all 205
trades of that run there is **not one second-rung fill**; every trade closed on the runner, the
first rung, or time. So `tpTargets` is no longer a bare price list: each rung is `{price, banks?}`,
and the chart draws a non-banking rung under its own name rather than a target's.

🔴 **`banks` ABSENT is not `banks: false`.** Every run stored before 2026-08-21 carries bare
prices, and defaulting those to "banks nothing" would redraw every historical chart's targets as
stop steps off a measurement nobody made. `_tp_targets` emits the key only when the strategy
reported it. This is the same rule as the dead terminal reading as a quiet market.

⚠ **Ladder order is the STRATEGY's, and is NOT nearest-first** — the old comment here claimed it
was. A re-entry prices its first rung off risk (`exec_sec_tp_r`) and its second off a fib, so the
second can be the NEARER of the two: **23 of the 45 RE-ENTRIES on that run; all 160 main
entries are correctly ordered.** ⚠ **The first count published here said 182 of 205 and was
WRONG** — the check had the direction of *nearer* inverted, so it counted every correct trade
as broken and read as a repo-wide defect instead of a re-entry one (corrected 2026-08-21).
A distance is measured FROM the entry in the favourable direction, and on a short that means
the nearer target is the HIGHER price; a bare price comparison gets it backwards on one side
and looks fine on the other. Numbering is by
ladder position, so `TP2` legitimately sits closer to the entry than `TP1`; sorting here would
renumber the strategy's own rungs.

⚠ **Two rungs closed by ONE event at ONE price are ONE chip.** A trail takes every still-open
bracket at the same price on the same bar, so the record holds one leg per bracket — drawing both
de-collides the second 15px below the first and reads as two separate fills.

⚠ **Existing runs need a RERUN, not *Reload charts*** — `banks` comes from the strategy's own
record, so a run replayed before this landed has bare prices and keeps the old (unknown) rendering.

Tests: `tests/test_chart_spec_tp_rungs.py` (8, all watched RED — 5 against HEAD, 3 by mutating the
target check to always relabel).

## `chart_spec` carries what the trade BEFORE a re-entry did (2026-08-21)

`_build_trades` passes an optional `after` — `"breakeven"` | `"stopped"` | `"closed"` — straight
off the stored equity-curve point. The panel tags a re-entry `BE+` or `SL+` with it instead of one
`SEC` for both, which was Aaron's ask on a chart holding 107 re-entries from two different triggers.

⚠ **Emitted ONLY for a real non-empty string.** Absent means the run could not tell — a re-entry
can be armed through a precondition that asks nothing of the trade before it, and every run stored
before this date has no `after` at all. The panel falls back to the neutral tag on a missing one,
so `"after": ""` or `"after": null` shipped as a value would make it read a fact nobody measured.
An equity curve is JSON somebody else wrote, so the type is checked rather than assumed.

⚠ **Still generic — no strategy or runner names here.** This function draws every runner's trades
and the docstring says so; `after` is a fact about a BOOK, the same shape as `kind` beside it.

Tests: `tests/test_chart_spec_trade_book.py` (4, all watched RED by mutation — dropping the emit,
making it unconditional, and dropping the type check).

## The commit-gate probe writes PER-WORKER files (2026-08-21)

`tests/test_deploy_commit_gate.py` drives the real `commit-msg` hook against a scratch message and
a scratch index under `.git`. Both were FIXED names, and both suites run `-n auto` — so three tests
in this one file wrote and then `unlink`ed the same two paths, and under xdist one worker deleted
the file another was still using. The hook then exited non-zero with
`grep: .git/COMMIT_EDITMSG_probe: No such file or directory`, which reads as *"the deploy gate is
broken"* rather than *"the test tripped over itself"*.

MEASURED 2026-08-21: green 3/3 serially, red 3/3 under `-n auto`, and it is step 2 of
`scripts/run_all_tests.sh` — **so the gate has been intermittently red for everyone, on a file
nobody had touched.** Now `_probe_paths()` keys both names on the PID: 4/4 green in parallel.

⚠ **This is the exact failure the root CLAUDE.md warns about** — *"a new test that writes a fixed
path breaks other tests non-deterministically, which is the worst failure shape a suite has"* —
and it was already in the suite when that line was written. **The rule is not "don't add one", it
is "go and look for the ones already there" the first time a suite goes parallel.**

⚠ **Keyed on the PID, not `PYTEST_XDIST_WORKER`**, so it is still correct when the file is run
outside xdist, where that variable does not exist and a `.get()` default would put every serial
run back on one shared name.

## The re-entry's fill feed is 5m, and `EXTRA_FEEDS` holds a COPY on purpose (2026-08-21)

`run_feeds.EXTRA_FEEDS["exec_secondary"]` moved `1` → `5`, and `python_runner` now loads whatever
that registry says instead of a hardcoded 1. MEASURED over 7.9 years: 5m loads a fifth of the bars
(561,795 vs 2,804,720) and lands within 1.3% of the 1m result; 15m is 7.6% off. The table and the
reasoning live with the strategy that owns the number
(`strategies/python/sos_fade/CLAUDE.md` → *The re-entry's FILL CLOCK*), not here.

🔴 **The runner must load the SAME feed the registry BOUNDED the window with.** `EXTRA_FEEDS` is
what `history_limits` uses to refuse a window the extra feed cannot serve; loading a different one
in the runner replays a feed the window was never checked against — the pre-flight and the run
disagreeing, which is the exact defect this module was created to end.

⚠ **It is a COPY of the strategy's `exec_sec_fill_tf_min`, deliberately.** This module bounds the
window *before* any strategy is constructed, so it cannot import the value it needs, and a value it
cannot read is a value it would have to guess. `tests/test_run_feeds.py` asserts the two agree and
was watched RED by setting the registry back to 1.

🔴 **AND THE COPY HAD A CONSEQUENCE NOBODY WROTE DOWN: THE RUN FORM'S "Re-entry fill clock
(minutes)" CONTROL WAS DEAD ON THIS PATH — RAISED AND ✅ FIXED 2026-09-01.** The strategy
declares it as a live number widget (`sos_fade.meta.json`, range 1–15, shown whenever the
re-entry is on) whose own description tells the reader it changes how accurate the test is. This
module ignores it. `required_timeframes` only ever adds the registry's constant, and
`python_runner.py:431` FETCHES at `EXTRA_FEEDS[SECONDARY_FLAG]` rather than at the config — so a
run that sets the clock to 1 or to 15 still bounds and still replays **5m bars**, and the result
carries the value the user chose while having been measured at another. **MEASURED, not reasoned:**

```
cd command-center/backend && .venv/bin/python -c "from services import run_feeds; \
print(run_feeds.required_timeframes('Minute', 15, {'exec_secondary': True, 'exec_sec_fill_tf_min': 1}))"
# -> [5, 15]     ... and [5, 15] again at 15. The control moves nothing.
```

⚠ **The CLI tool disagrees with the app**, which is the part that will bite: `backtest/tools/
run_report.py:448` reads `getattr(cfg, "exec_sec_fill_tf_min", 1)` off the built config and DOES
honour it. So the same params produce a different fill clock depending on which side ran them, and
nothing says so. ⚠ **This is rule 7 arriving through the pre-flight** — the label is a claim about
code somewhere else, and here that code read a constant.

✅ **HOW IT WAS FIXED, and the shape is the point.** `EXTRA_FEEDS` now holds a `FeedSpec(param,
default)` rather than an int: `param` is the run setting that OVERRIDES the feed's timeframe,
`default` is what a run that never states it loads. **One resolver — `extra_feed_minutes(flag,
params)` — and BOTH the fetch and the floor ask it**, where they previously read the table
separately. ⚠ **The default is still load-bearing and is NOT the strategy's field read at
import**: this module bounds the window before any strategy is constructed, so it cannot import
the value, and `tests/test_run_feeds.py` pins both the default AND the override's NAME — a typo
in the name would fail nothing on its own, it would just never find the param and silently
restore the dead control.

⚠ **The PICKER needed a second half, and without it the fix would have been the 2026-08-15 defect
one level down.** The UI sent flag NAMES only, so it would have bounded every run at the default
while the run loaded something else. It now sends its numeric params as `name:value` pairs
(`&pv=`) exactly the way it sends its flags — **everything it holds, with this module keeping only
what a feed reads** — so the frontend still carries no copy of the feed list. MEASURED before
choosing that shape: 60 numeric params, ~1.4 KB of query string.

⚠ **A stated value that is not a positive whole number falls back to the default rather than
raising.** This resolver runs inside a date-picker request, and a picker that 500s because
somebody is mid-typing in a number box is worse than one bounded at the default — the RUN still
refuses properly, because the strategy's own config validates the value.

⚠ **It changes what a run MEASURES.** A stored run whose params state a clock other than 5 was
measured at 5; re-running it now will not reproduce it. That is the correction landing, not a
regression, but it is the kind of thing that reads as a lab bug six months from now.

🔴 **FOUR FLOOR TESTS WENT RED ON THIS CHANGE AND NONE OF THEM WAS ABOUT IT.** They prove a
mechanism — the window is bounded by the shallowest feed a run loads — and they had used the
re-entry as their vehicle, so `== [1, 15]` and `earliest_date == "2018-09-14"` had quietly become
assertions about a number that lives in another subsystem. They now pin the extra feed to 1m
themselves (`SHALLOW_FEED`) and the real value is asserted once, against its owner. **A test that
fails on an unrelated config change is a test nobody trusts the next time it speaks** — and the
tempting repair, editing 1 to 5 in each, would have left four copies of the number where there had
been one.
