# CLAUDE.md — ChartPanel (backtest candlestick panel)

**Purpose:** A strategy-agnostic candlestick chart for the backtest page, built on klinecharts v9. It renders whatever a `ChartSpec` declares and contains **zero** strategy-specific logic.
**Scope:** This folder only. The host page is `pages/BacktestDetail.tsx`.
**Status:** Live — all build steps done. Renders real runs end-to-end: candles, sessions, trades, strategy-structure overlays, the ATR indicator, and the measurement tool.



🔴 **A drill-down's only sign of life was an 11px grey line in the header.** The fetch is a real round trip — **MEASURED at ~4.5s per 12,000-bar window on a warm cache, cold or warm** — and the panel deliberately keeps the previous timeframe's candles on screen throughout, so the loading state and the doing-nothing state were pixel-identical. There is a badge over the plot now, plus a spinner on the timeframe button, and **it names BOTH timeframes** (`loading M1 bars — showing M15 meanwhile`), because bars that do not match the button are a silent lie about what is on screen. The same badge carries the failure, in warn, for the same reason.


✅ **`tests/chart-drilldown.spec.ts` — 4 checks, and EVERY ONE PROVEN BY MUTATION** (a fail-watch against HEAD is impossible for the parts already fixed in the commit below): reverting the anchor, deleting the badge, restoring the hedged message and removing BOTH position fixes each turn exactly the naming check red. ⚠ Three of the four drive the REAL backend — what is under test is where the chart LANDS after a real fetch, so a mocked feed would be measuring the mock. The refusal is mocked, with the exact payload measured off the live backend, because the only way to produce it for real is to take the terminal down.

Earlier: 🔴 **PRESSING M5 WHILE READING 2020 THREW THE CHART SIX YEARS FORWARD, AND `Volume: n/a` WAS A NUMBER THE PIPELINE HAD IN HAND.** Two bugs Aaron reported off the screen, in the same header control and the same readout.



⚠ **THREE PATHS OF THIS FIX ARE NOT YET DRIVEN, AND THEY ARE NAMED HERE RATHER THAN LEFT TO LOOK COVERED.** (1) **`drillNewer`** — scrolling RIGHT in drill-down, back toward the present. It fired once incidentally before `drillTo` landed and no longer triggers on that path, so it is the mirror of code that WAS verified, which is an argument and not evidence. (2) **The hard-edge branch at a drill timeframe** — paging back was measured twice but never all the way to the broker's true M1 limit, so the red *no earlier data* line has not been seen to fire in drill-down. (3) **`goToDate`'s empty-fetch release** — jumping behind the broker's depth returns nothing, and if the guard is not released there the symptom is the chart refusing every later jump AND every page for the rest of the session. ⚠ **There is also no committed browser check for any of this**: it was driven with throwaway scripts. By this folder's own standard that makes it a well-driven fix, not a regression-proof one — `tests/chart-paging.spec.ts` is where the checks belong, and the defect is one revert away, so a fail-watch against HEAD is cheap here.

⚠ **One change was made, could not be demonstrated, and was REVERTED — recorded because the plausible story was the trap.** A Playwright click on M30 after a jump timed out past 90 seconds, which is what a frozen main thread looks like from outside, and there was a clean mechanism for it: a switch re-applies, `applyNewData` parks on the newest loaded bar, that bar is mid-history after a jump, so klinecharts could ask `loadNewer` for page after page from the edge it had just parked on. **It is not true.** An in-page 50 ms timer logged **2,407 samples over 120 s** — it never missed a tick — and the applied window moved only from `00:15` to `00:00`, which is the M30 resample and nothing else; it reproduces identically at HEAD. The blocked click is the harness. **A guard was written for that and taken back out, because shipping it would have meant writing a measurement nobody took into a comment** — the same rule this repo already has about plausible guesses in docs, met from the code side.

**(2) `Volume: n/a`.** klinecharts' candle tooltip carries a `volume` row and renders a missing value as `n/a`, and `chart_spec` was DELETING the column once its server-side layers had read it — so a number the pipeline held became a permanent *no data* on the readout. Volume ships now (**+16.0 bytes per candle: 23.32 MB → 25.77 MB on a 155,807-candle spec, ~+20 ms parse**, measured before the call), and the readout reads **`Volume: 5.221K`**. ⚠ **`resample()` no longer sums an unknown bar as zero.** `bucket.volume + (c.volume ?? 0)` was wrong in the direction that hides itself: a bar with no volume is not a bar that traded nothing, and summing it as zero reports a short total under a name claiming a measurement. A bucket is `undefined` the moment any base bar in it is — the same rule as `backtest/data/resample.py::_volume_sum`, which returns NaN for exactly this case. ⚠ **The line in this file saying "Volume does NOT travel to the browser" is now false and is why it is called out here**: `ChartCandle.volume` is optional in the STRONG sense — absent means we do not have it, never that the bar was flat.

**Earlier the same day:** 🔴 **A STRAY NUL BYTE MADE THIS APP'S LARGEST PAGE INVISIBLE TO `grep`, AND I DELETED A GOOD TEST ON THE STRENGTH OF IT.** `BacktestDetail.tsx` carried one NUL inside a string literal (`runId ?? '\0none'`, from `a314381`), and `grep` on this box is **ugrep**, which classifies a file containing a NUL as BINARY and skips it in **SILENCE — exit 1, no output, no warning**, exactly like a clean no-match. So a search for `useRefreshChartSpec` reported no callers when the file holds two, and on that basis the previous entry here recorded *"nothing in this app swaps the spec object during a session"* and deleted a browser check as unreachable. **The Rebuild chart button has existed the whole time** (Price tab, non-NT8 runs, `BacktestDetail.tsx:5050`). The NUL is removed and the sentinel is a plain `'__no_run__'`. ⚠ **A silent no-match is worse than an error, because it is the same shape as the answer you were hoping for** — a grep proving ABSENCE across this repo must be `grep -a`, or ripgrep, or it is not evidence. ✅ **The deleted check is restored and now BITES**, and getting there found the real mechanism: **TanStack applies structural sharing, so a rebuild returning identical content hands back the OLD object and the roster never recomputes.** The first restored version rebuilt an unchanged spec and *still* passed against the plain re-seed it was written to catch; the rebuilt spec has to genuinely DIFFER, so the check now intercepts the refresh and returns a spec carrying one extra layer — which is also the realistic case, since that is precisely what a spec cached before the VWAP existed does when rebuilt. Red under the mutation, green with `reconcileToggles`. **4 checks, every one proven by mutation.** ⚠ **`reconcileToggles` is therefore load-bearing after all, and its protection is narrower than it looks: structural sharing hides the defect for every rebuild that changes nothing, so the one rebuild that matters — the one that adds a layer — is the one that would have reset the reader's toggles.** **The standing lesson is about the evidence, not the bug: I stated a negative from a tool that cannot report its own blindness, and then wrote that negative into two CLAUDE.md files as a reason to remove a test. Before recording "there are no callers", make the tool prove it can see the file.** Earlier the same day: ✅ **THE VWAP IS DRAWING ON REAL BARS, AND PROVING ITS TESTS BITE DELETED ONE OF THEM.** The terminal was logged back in, so the layer was finally driven end to end rather than unit-tested: **186,274 XAUUSD M15 bars re-pulled with volume, the spec rebuilt with 155,805 VWAP points, and the value checked by hand against the raw cache on four sessions — identical to the 5dp it rounds to** (and the anchor moves with DST, 22:00 UTC in August against 23:00 in December). 3 browser checks in `tests/vwap.spec.ts`. ⚠ **A fail-watch against HEAD is VACUOUS for a layer HEAD already has**, so non-vacuity came from MUTATION: dropping `defaultOn` from the emitter turns all three red, and flipping `defaultOn !== false` to `=== true` turns exactly the one that names that rule red. 🔴 **A FOURTH CHECK WAS WRITTEN, PASSED, AND WAS DELETED FOR FAILING TO BITE — it claimed the reader's toggle survives a roster rebuild, and it PASSED with `reconcileToggles` replaced by the plain re-seed it was written to catch.** The condition cannot be produced from the UI: `indicatorRoster` is memoized on `spec.indicators`, a timeframe switch is a display-only resample that never touches the spec, and **`useRefreshChartSpec` — the one thing that would swap the object — has NO CALLERS.** So the reconcile is correct and defensive rather than exercised, and the spec file says so in place of the test. ⚠ **`data-indicators-on` on the panel root is a new declared TEST SEAM** beside `data-applied-lo/-hi`, for the same reason: an indicator draws into the candle pane's CANVAS, so a check that settled for *the menu row is ticked* would pass against a panel drawing nothing. **The standing lesson is the fail-watch rule taken one step further than usual: a green test is not evidence, and neither is a red SUITE — you have to watch THIS test go red, and when it will not, deleting it is the honest outcome.** Earlier the same day: 🟢 **A SESSION VWAP LINE, AND IT COST THE PANEL NOTHING NEW.** Aaron's brother asked for it. The canonical `engines/vwap/` engine is replayed server-side (`services/vwap_overlays.py`) into ONE `ChartSpec.indicators` entry — main pane, one value per bar — so it needed **no new overlay template, no new render effect and no new panel concept**: `ChartIndicator` is exactly what a value-per-bar series is, `mapSeriesToCandles` already re-times it when the reader zooms to a coarser display timeframe, and the Structure menu already gives every indicator its own toggle. Third entry in the run of layers that landed for one string and a colour (fair value gaps, order blocks, this). ⚠ **Emitting ~156k one-bar hlines would have been the same picture built from the wrong primitive** — the panel's overlay budget is superlinear and this is the one thing `indicators` exists for. ⚠ **`ChartIndicator` gained `defaultOn`, and absent means TRUE on purpose**: the ATR sub-pane has opened ON since it shipped and must keep doing so, while an analysis layer must not — the rule Fair Value Gaps, Order Blocks and Fibs all follow. ⚠ **`indicatorsOn` is now RECONCILED, not re-seeded.** It was rebuilt from `spec.indicators` on every change, which was safe only while nothing carried a non-default — the moment one does, a plain re-seed silently undoes the reader's toggle. That is the same defect `reconcileToggles` was written for on `groupsOn`, arriving in the one roster that had not adopted it. ⚠ **The layer is absent, not empty, when the run's bars carry no volume** — a VWAP is a volume-weighted mean and this chart's bars only started carrying volume today, so an older run shows no toggle at all until its bars are re-pulled. That absence IS the honest answer and is the same way Blocked and Missed vanish on a runner that cannot report them; the refusal rules live in `../../../backend/CLAUDE.md`. ⚠ **Volume does NOT travel to the browser.** `chart_spec` strips it once the server-side layers have read it, on the drill-down path too — nothing here plots it, and on a full-history run it is ~156k numbers of payload, parse and heap bought for nobody. `ChartCandle.volume` stays optional on the contract so a future volume pane re-adds it deliberately rather than finding it arriving by accident. **The standing lesson is the payoff note, restated because it keeps paying: the generic mechanisms here are worth reaching for BEFORE writing anything bespoke — but only once one has been exercised.** The `BOX` label path was the counter-example (a blue-chip default nobody had ever hit); `ChartIndicator` had a real user in the ATR pane, which is why this one carried no surprises.


**Earlier the same day:** 🔴 **A DEEP "GO TO DATE" JUMP IS A REAL NINETY SECONDS, AND THE ONLY
SIGN OF LIFE WAS A LABEL THAT NEVER CHANGED.** Aaron: *"if I'm trying to load back to six years ago,
there's no intuitive indicator that something isn't broken."* **MEASURED end to end in a real
browser on run `211384ddbea4` at M15: 90.3s and 14 pages to reach 2020-02-03.** ⚠ **That run is no
longer in the lab (2026-08-16), and every `211384ddbea4` in this file is PROVENANCE rather than a
dependency — the numbers stand, they simply cannot be re-run against that row.** Naming the subject
of a measurement is correct; naming one in a TEST is not, and `chart-paging.spec.ts` had done the
second (see `../../CLAUDE.md` → *A FIXTURE PINNED TO A DATABASE ROW*). The pill said
`loading 2020-02-03…` for the whole of it — the DESTINATION, which does not move — and the on-chart
`Loading earlier bars…` edge is no help because the view is still parked at the right edge while the
jump runs. The jump now publishes `jumpAt` and the pill reports **the date already REACHED plus a
bar that fills**, verified stepping 11 times over 90s: `2025-03-09 → 2024-09-15 → … → 2020-05-24`.
⚠ **Progress is measured in TIME COVERED, never in pages done** — a page span is clamped at the run's
start so the last one is short, and the page count is not knowable in advance anyway. ⚠ **The reached
DATE is the load-bearing half, not the percentage**: a bar alone still reads as a guess. 🔴 **The
speed fix was BUILT, MEASURED AND REVERTED, and that is the part worth carrying.** Bulk-paging a jump
(50,000 bars instead of 12,000) is what the per-bar numbers demand — 175d/11,188 bars costs 6.63s
(0.59 ms/bar) against 875d/56,632 at 20.23s (0.36 ms/bar) — and driven end to end it bought **6%**
(89.4s → 83.9s), because the span is fixed and the analysis replay dominates either way. **It also
cost the very thing the change was for: the readout stepped 3 times instead of 14, i.e. 25 seconds of
stillness between updates instead of 6.** A minute-long wait that looks alive beats one that is 6%
shorter and looks hung. ✅ **The real lever is named and deliberately not pulled: `analysis=true` is
~60% of a page** (175d 2.61s bare vs 6.63s charged; 875d 8.24s vs 20.23s), so a bars-only jump would
be ~35s — but it trades away the guarantee the 2026-08-02 fix bought, that every layer reaches
exactly as far back as the bars do, and doing it safely means backfilling each skipped window after
the jump lands. ✅ **2 new browser checks (`tests/chart-paging.spec.ts`), BOTH watched red against
HEAD**, driving the real backend rather than a mocked feed — the thing under test is that the readout
tracks pages actually landing, so a mock would be testing the mock's cadence. ⚠ **One of them nearly
shipped VACUOUS**: the bar carries a 3% floor so it is visible at the start, so asserting `> 0%`
would pass against a completely dead progress value — it has to be watched GROW. Earlier:
2026-08-03 — **the panel is now WARM-MOUNTED by its host, hidden, before the
reader clicks the Price tab** — 2,453 ms → 167 ms from click to a painted chart, measured on run
`432aff31f374`. Nothing in this folder changed; what changed is that it can be alive inside a
`visibility: hidden` container, which is a real constraint on anything added here. See the first
bullet under **Conventions**. Earlier the same day: **Analysis → Order Blocks.** The canonical `engines/order_blocks/`
engine is replayed server-side and a block is drawn ONLY where it was live on a trade / blocked /
missed bar — the fair-value-gap layer's anchor rule, with one engine swapped (579 boxes on the
measured run, beside the gap layer's 661). **It needed no new template, no new effect and no new
concept**: it is a plain `box` group and a second string in `ANALYSIS_GROUPS`, which is precisely
what that list was added for. Default OFF, listed with its count, last in Analysis, and deliberately
**not** in Deep debug (Aaron's call). ⚠ **The box is a fixed 30-bar STUB from the anchor candle, not
a live-bar tracker** — the one place this differs from the gaps, and the reason a block's box can end
long before the block dies, or after the bar it died on. ⚠ **Exercising the generic `BOX` label path
for the first time found a bug sitting in it**: klinecharts' default overlay-text style is a solid
BLUE chip, so the first `OB` tag rendered as a blue pill — and the `HLINE` label path carried the
identical bug, still dormant. This file already recorded that trap for the `LABEL` template; it
applied to both and nobody had drawn one. All three now spread the shared `FLAT_TEXT` style.
**The lesson: a generic mechanism nobody has used is not a working mechanism.** Earlier:
2026-08-02 — **every trade can now draw the FIB LEG it was priced off** (Analysis
→ **Fibs**), so a plotted trade says which retracement levels it went into instead of
leaving you to redraw the fib by hand. Each level arrives as an explicit `(ratio, price)` pair the
STRATEGY recorded when it placed the order, so **there is no fib maths in the browser** and the
chart cannot land on a price the bot never used; two accent chips name the two readings a ladder
cannot state on its own — `entry 0.702` and `deepest 0.886`. **`TRADE_FIB` is a separate template
from `FIB` on purpose: this one is DATA, not a drawing** — locked, event-ignoring, undeletable, and
deliberately NOT following the fib editor's configurable ladder, because retuning your own tool must
not restyle what the bot measured (only the factory COLOURS are shared, so a 0.618 the bot used
looks like a 0.618 you drew). It is a SUB-toggle of Trades and reuses that effect's own predicates —
loaded-candle clip, layer isolation, Winners/Losers — so a fib can only ever be drawn under a trade
that is itself drawn, the same "no filters of its own" rule Step follows. Default OFF and listed
only when trades carry one, so NT8/MT5 and pre-today Python runs show no switch. Earlier the same
day: **Deep debug — one toggle at the top of the Analysis menu that
deepens whatever is on screen.** Reading a run one trade at a time meant setting the same three
context layers by hand across two dropdowns — the fib leg the entry was priced off, External
Structure, Fair Value Gaps — and unsetting them again constantly. **The design lesson is in how many
shapes it took before it was right, all in one day:** a segmented `Winners | Losers` pill beside the
menus, then a four-way `Winners / Losers / Both / Off` radio inside Analysis, and finally one
additive on/off row. The first two OWNED THE OUTCOME FILTER, and that is what made them wrong — it
asked "winners, losers or both" in a second place that could disagree with the rows below, and it
forced the unanswerable question "what does OFF restore?" (the first build shipped with no way out
at all, which Aaron caught). **Additive has neither problem: it never decides which trades are drawn,
so the filter has one home, off simply means off, and Step re-scopes off the same rows it always
did.** On/off is DERIVED from the layers, so unticking one by hand unticks the row. ⚠ **The write is
unconditional but the READ is not** — setting a layer the run never emitted is inert, while a read
over layers that cannot exist is vacuously TRUE and would pin the row permanently ON; `debugAvailable`
hides it instead. It reuses `ToggleMenu` rather than becoming a fourth hand-rolled dropdown, which
cost two new `MenuItem` fields (`section`, `action`) and keeps the header count describing layers
only — measured `Analysis 3/7` at rest, `5/7` on. Verified in-browser on run `211384ddbea4`: on →
Fibs + Fair Value Gaps + External Structure, with Winners/Losers untouched; untick Winners → Step
re-scopes 165 → 54 with the row still ticked; untick a debug layer by hand → the row unticks; off →
all three back off and the outcome filter still exactly as the reader left it. The fib clause was
exercised against an injected `ChartTradeFib`, since no run carries one until it is re-run.
Earlier the same day: 🔴 **every layer except the TRADES stopped at the shipped candles,
so scrolling back far enough emptied the chart while every toggle still read ON.** Structure, Fair
Value Gaps, Blocked and Missed are all emitted PER-WINDOW server-side (`chart_spec._capped_start`
ships ~17 months of a 6.5-year run), and the panel pages bars back to the run's start — so past that
boundary the layers you had switched on simply drew nothing, with no message and no change to their
switches. Aaron read it as the panel forgetting his settings, which is exactly what it looks like.
A page now asks for its own analysis (`GET /runs/{id}/candles?analysis=true` →
`chart_spec._page_analysis`) and the panel MERGES it — `allOverlays` / `blocks` / `misses`, deduped
by identity — so a layer reaches back exactly as far as the bars do. **The second half of the fix is
the one that generalises: rosters derived from the data must be RECONCILED, never re-seeded.**
`groupsOn` was rebuilt from `overlayGroups` on every change, which was harmless only while that list
never changed; the moment a page could rebuild it, `setGroupsOn(defaults)` would have switched the
reader's layers off mid-scroll — so `reconcileToggles` keeps an answer the reader has already given
and defaults only genuinely new keys (same rule for the miss-noise seed, which now seeds each label
once). Verified in-browser on run `211384ddbea4`: at 2024-05→06, nine months before the shipped
window, BOS/SOS lines, HH/HL/LH/LL tags, gap boxes and pink Blocked markers all draw, with Winners
still filtered off — that region was bare candles before. ⚠ **A page costs ~+2s and ~+230 KB** (a
structure + FVG replay over the window plus `_PAGE_WARMUP_BARS` of older bars), which a multi-page
`goToDate` jump pays per page. ⚠ **A page's internal structure is demoted to Historic** — the
engine calls the newest leg in whatever it replayed "current", and only the shipped window holds the
leg the run actually ended in. Earlier the same day: **the fib tool anchored its ladder the wrong way round, and had
since it shipped.** It put **0 on the first click and 1 on the second**, so dragging up from a swing
low placed 0 at the low and 1 at the high — the ladder mirrored, and every retracement level on the
wrong side of the move. It is now **1 on the first click (the leg's ORIGIN), 0 on the second (its
EXTREME)**: `p1 + (p0 - p1) * ratio`. That is how a retracement is read — price retraces from 0 back
toward 1 — and, more to the point, it is what every other fib in this repo means:
`mpc_strategy.pine` prices its levels off the same convention (`fiboP7 = ash - range*0.0` is the
extreme, `fiboP10 = ash - range*1.0` is the origin), so a hand-drawn fib and the bot's own levels
were reading opposite. One line of maths; extensions past 1 / below 0 still fall out of it for free,
now on the sides TradingView puts them on. Earlier: 2026-08-01 — **Step (`◀ Loss 12/60 ▶`), a header pill that walks the markers.**
Reading a run's losers back to back was a scroll hunt across years of bars. The arrows (and ← / →
while the pointer is over the panel) jump to the previous / next marker and centre it, paging older
history in on the way via the SAME `goToDate` the date pill drives. The design decision worth keeping:
**it has no set of its own — it walks whatever the Analysis dropdown is showing.** Untick Winners and
◀ walks the losers; turn Trades off with Blocked on and it walks the refusals; leave both on and it
interleaves them by time (measured on run `0e3983a0c3c7`: 164 trades → 104 / 60 / 138 with blocked
added, stepping Loss → Blocked → Loss). A second set of filters would just be a second place for the
navigator and the chart to disagree. One new overlay, `FOCUS` — an accent dashed vline on the parked
marker, because a step CENTRES its target rather than isolating it.
Earlier the same day: **Analysis → Fair Value Gaps.** The canonical FVG engine is replayed
server-side and a gap is drawn ONLY where it was live on a trade / blocked / missed bar (all of them
when several overlap), so the layer answers "where were the gaps when this fired" instead of papering
a 33k-bar chart with every gap the run ever saw — measured on the shipped 142-trade run: 215 anchor
bars → 655 boxes. It needed **no new overlay template and no new effect** — it is a plain `box` group,
and the only new panel concept is `ANALYSIS_GROUPS`, the list of overlay groups that belong in the
Analysis dropdown rather than Structure. ⚠ The gaps are the INDICATOR's (`mpc_assistant.pine`), which
is a stricter-vs-looser fork from what the bot's own entry rule counted — see the bullet below.
Earlier: 2026-07-30 (**scroll-left paging now SHOWS itself** — the blank strip you scroll
into is shaded and labelled `Loading earlier bars…` from the oldest loaded bar back, so a page in
flight no longer reads as the end of the data; earlier: **configurable fib levels** — the ladder is no longer a hardcoded
array: add / remove / retune / recolour / hide any level from a live editor, per drawing or as the
tool's persisted default; 2026-07-28: **Go to date** — a header pill that types you to a date instead of
dragging there, driving the existing scroll-left pager itself; earlier: the **Missed** layer — how
close the setups that died came — sharing one overlay template and one hover card with Blocked; the
spec now ships the run's OWN timeframe with the WINDOW capped, and older history pages in on
scroll-left — no fetch, no placeholder, no swap on open; plus the Analysis dropdown, Layers renamed
Structure, and day breaks moved into the Sessions legend)

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `command-center/docs/CHARTPANEL_BUILD_NOTES.md`. **Nothing was deleted.** It was 30,123 bytes in 7 paragraph(s), the largest 9,974 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

## Chart settings — the reader's own preferences, and the one place they live

**Built 2026-08-06 (Aaron's ask).** A cog at the **bottom** of the left tool strip, below the drawing
tools and separated from them by `mt-auto`, opens `ChartSettingsPanel`. It is not a tool: the ruler
and the fib button make a DRAWING, this configures the CHART, and the position says so.

**`chartSettings.ts` is a REGISTRY, not a settings object, and that is the whole design.** Adding a
setting is one field on `ChartSettings`, one default, and one row in `SECTIONS`; the panel renders
whatever the registry declares. It grows only when a new WIDGET KIND is needed — and then once, for
every setting of that kind that will ever exist.

- ⚠ **A setting is a PREFERENCE, never a measurement.** Nothing here may change what the chart
  computes, only how it is drawn — the panel says so in its own footer. The moment a control changes
  which trades exist, which gaps qualify, or what a number means, it belongs in the run's config
  where it is STORED WITH THE RUN. A display preference quietly reshaping a result would be
  undetectable, because this panel is per-browser.
- ⚠ **Stored settings are MERGED over the defaults, never swapped in**, and a value of the wrong
  TYPE is dropped rather than trusted (the blob is editable by hand and by any older build). Same
  rule `reconcileToggles` follows for overlay groups, and it fails the same silent way if broken:
  the reader's chart quietly loses a control they never turned off.
- 🔴 **`tradeLabels`** → `TradeExtend.showLabels` (2026-08-20, Aaron's ask). Off drops every
  ANNOTATION a trade draws — the `Entry` / `SL` / `TP1` / `Best` / `DD` / `Add` chips down
  the side, and the `Won` / `Lost` verdict over the end — and leaves the DRAWING: the bands, the
  level lines and their dots. His reason, and it is the design: *"I will just be able to eye it off
  of the colour of the drawdown filters and the TP zone."* On a chart with several trades in view
  the words are most of what is painted (MEASURED: **11,959 pixels**, ~4% of the panel's frame, on
  one parked trade) and the green/red already say which way it went.
  - 🔴 **WHATEVER NAMES THE TRADE SURVIVES, AND THAT IS THE WHOLE EXCEPTION** — a stack's strategy,
    the `SEC` / `REC` book tag, an add lot's `Add`. Aaron: *"leave the name of the trade in there if
    it has a name."* Which trade this IS cannot be read off the drawing at all: the colours grade
    the outcome and say nothing about whether this is the setup, its re-entry or the recovery
    that followed it. The verdict word goes with the side chips, because a win is already the green.
  - ⚠ **The chip is DROPPED ENTIRELY when nothing is left to say** — a single-run trade has no
    layer name and no kind tag, so it draws no chip at all. An empty one still paints its dark
    rounded box, which on a chart stripped of every other label is the only thing left to look at.
  - ⚠ **The pattern NAME goes too**, though it has its own setting one section down. It is an
    annotation about what happened at the turn, in the same family as `Best` and `DD` —
    keeping it while dropping `Won` would be arbitrary, and it is one toggle away.
  - ⚠ **The gate is ONE choke point (`addLabel`), never one per call site.** A trade grew its
    annotations one call at a time — `SL`, then the legs, then `Best`/`DD`, then the adds,
    then the TP ladder — and a flag wired at each would be a list the NEXT annotation is free to be
    left off, silently, because nothing fails when a label keeps drawing.
  - ⚠ **Undefined means ON**, same rule as `showPrices` below: a caller that has not been updated
    keeps the shipped reading.
- **`tradeLabelPrices`** → `TradeExtend.showPrices`. Off drops the number from every side label,
  leaving `Entry` / `SL` / `TP1`. **Undefined means ON**, so a caller that has not been updated keeps
  the shipped reading. It became a setting because a re-entry's box is short by construction and
  the price is most of each chip's width. **It now declares `dependsOn: 'tradeLabels'`** — see below.
- **`candleMarkLabels`** → the Candlestick Reversals tag. See the layer's own section below.
- **`dependsOn` — a row that is INERT is greyed, never hidden** (2026-08-20). A setting whose parent
  is off changes nothing on the chart, so the panel shows it at 40% and refuses the click. ⚠ **It is
  PRESENTATION ONLY, and the parent must still be honoured where the setting is READ** — greying a
  control the drawing code ignores would be a second claim about one behaviour, free to disagree
  with the first. ⚠ **Greyed rather than hidden**, the house rule `ParamEditor`'s `disable_if` and
  `AccountsTab`'s unassignable account both follow: a setting that vanishes reads as one that does
  not exist. ⚠ **The inert row KEEPS ITS VALUE** — the panel never writes on its behalf, so
  switching the parent back on restores the reader's own answer rather than a default.
- **`data-setting="<key>"` on every row is a declared TEST SEAM** (2026-08-20), beside
  `data-applied-lo/-hi` and `data-indicators-on` on the panel root. A row is a label, an ⓘ and a
  control in three SIBLING elements, so a locator built from the visible words lands on the label's
  own wrapper and never sees the switch beside it — and the check then fails as *element not found*,
  which reads as a missing setting rather than as a bad locator. It cost two suites a run each.
- **The `help` text renders behind an ⓘ, never under the label** (2026-08-08, Aaron's ask). A
  settings list is read by SCANNING NAMES, and a paragraph under every row triples the height of a
  panel that has to fit beside a chart — two settings already filled the box above the fib ladder.
  ⚠ **The explanation is moved, not dropped**, and the browser check asserts both halves for that
  reason: gone-from-the-row AND one hover away. Deleting the answer is the same tidy-up with the
  content thrown out, and it looks identical in a screenshot. It is `components/InfoTip` — the app's
  shared one, portalled to `<body>`, so this panel's `overflow-y-auto` scroll box cannot crop the
  tip. **Extend the existing control before inventing one**, the same rule the Toggle below records.

🔴 **The first Toggle was hand-rolled and rendered WRONG, which is the small lesson worth keeping.**
A `translate-x` knob inside a bordered track: under `border-box` the OFF state's 1px border shrinks
the content box, so the knob's fixed offsets stopped centring it and the control read as slightly
broken — in a panel where everything else looked native. It is now `ParamEditor`'s `switch` widget
verbatim (explicit `left`, no transform, no border on the track, the On/Off word beside it).
**Extend the existing control before inventing one.**

### The fib ladder lives in Chart settings now

**The fib tool's own gear is GONE from the tool strip** (2026-08-06, Aaron's ask). Its job — editing
the DEFAULT ladder that new and un-customised fibs follow — is a **Fib levels** section in the
settings panel, which is where a reader looks for how the chart is drawn.

⚠ **It was NOT left behind as a shortcut.** Two controls editing one ladder is two places for it to
be answered from, which is this repo's most-repeated defect in miniature. **One drawing's own levels
are still on that fib's right-click menu** — a different SCOPE, not a second route to the same one.

- **`FibLevelEditor` is the rows + footer with no frame, no header and no positioning**, extracted
  from `FibSettings` so the popover and the panel cannot become two editors that drift. `FibSettings`
  is now that component in a floating frame; both feed one ladder.
- **`SectionBody` is a union**: a section is EITHER registry-driven `items` OR one named `custom`
  block the host renders. ⚠ **Keep custom blocks RARE** — each one is a section the registry cannot
  describe, i.e. UI the next setting cannot reuse, which is the opposite of the point of the file.
  A control that fits a widget kind should be a widget kind; adding a kind is cheaper than adding a
  block. The fib ladder earns one because it is a scrolling list with its own add / remove /
  colour-pick behaviour, and flattening it into `SettingDef`s would be re-implementing it.
- **A custom section with no renderer is skipped WHOLE, title included** — an empty titled box reads
  as something that failed to load.
- The editor's shown/total count is reported UP (`onCountChange`) rather than drawn, because it
  belongs in whichever header hosts it and the component deliberately has none.

## `Deepest` → `DD`, `Furthest` → `Best` (2026-08-21)

Aaron's ask, and the second half was left to me. Both were the widest chips a trade draws, both
land in the cluster the de-collider is already pushing apart, and neither word carried more than
its short form. **`DD` is his; `Best` was chosen over `Reached` and `Peak`** — the favourable
extreme of a SHORT is the LOWEST price on the chart, so `Peak` points the reader at the wrong half
and `Reached` leaves *reached what?* unanswered, while `Best` reads the same on either side.

⚠ **They are DISPLAY strings and nothing keys off them** — the fields are still `mfePrice` /
`maePrice` end to end, and `services/candle_overlays.py` still calls the adverse extreme "deepest"
in its own reasoning, which is correct there and is not this chip.

## 🔴 Nothing adverse is drawn past the stop on a trade the stop closed (2026-08-22)

Aaron's call: *"if my stop loss stopped me out, no need to show the drawdown. I was stopped out.
There's no drawdown. I lost."* Three marks are suppressed together — the faint tail band beyond the
stop, the `DD` dot and label, and the **win/loss chip's parking height**, which was the loudest of
the three: on a 1.0R stopped-out short it sat a full 1.2R above that trade's own `SL` line, reading
as a trade that kept losing after it was closed.

⚠ **It is also not a preference — the number was wrong.** The bot widened the hold's worst price
with the whole closing bar before resolving that bar's exits, so a stop-out kept the bar's far end.
Fixed at source (`strategies/python/mpc_sos_fade/execution.py` → `_widen_hold`), where 77 of 77
stopped-out trades on run `976aff9ec279` were affected. **This guard is what makes every run STORED
BEFORE that fix read right too, because nothing backfills them.**

🔴 **Detected from the PRICES, never the exit reason.** An exit's reason string here is the
BRACKET that closed, not the trigger — a trade that lost exactly 1.0R at its stop is labelled
`S-TP1`, and on run `976aff9ec279` **not one of the 78 stop-outs carried a stop-shaped reason at
all**. Keying on the label would have silently missed every one of them.

⚠ **No automated test**, because Playwright is out of the suite by design. The arithmetic it
mirrors is tested on the python side (`tests/test_excursion_bounds.py`, 7 tests, 5 mutations).

## The one rule

No strategy or instrument names, and no strategy concepts (sessions, ranges, breakout levels), are hardcoded in this component. The panel draws **only** what the spec carries. Adding a new strategy later means the lab emits a different spec — the code in this folder does not change.

---

## Files

```
ChartPanel/
├── index.tsx          default export ChartPanel({ spec? }) — inits klinecharts, draws candles + overlays
├── types.ts           ChartSpec — the contract the lab emits per run (THE source of truth)
├── chartStyles.ts     klinecharts style object, derived from the app theme (no hardcoded hex)
├── overlays.ts        custom klinecharts overlay templates (registerChartOverlays, idempotent)
├── fibLevels.ts       the fib LADDER — factory set, localStorage persistence, add/sanitize helpers
├── FibSettings.tsx    the fib level editor panel (add / remove / retune / recolour / hide a level)
├── indicators.ts      shipped-series indicator: ensureSeriesIndicator + mapSeriesToCandles (pure)
├── sessions.ts        session placement math: tz + broker offset → broker-axis windows (DST-aware)
├── fixtures/audjpy.ts  AUDJPY_FIXTURE — hand-written stand-in spec until Step 7 wires real specs
└── CLAUDE.md          this file
```

---

## The contract (`types.ts`)

`ChartSpec` carries: `instrument`, `baseTimeframe` (the bars SHIPPED), `runTimeframe` (the bars the
run TRADED — what the chart opens on), `brokerGmtOffsetHours`, `candles`,
`sessions[]`, `trades[]`, `blocks[]` (OPTIONAL — refused setups), `misses[]` + `missNoise[]`
(OPTIONAL — setups that died partway, and the reason labels to start hidden), `overlays[]`
(`box`/`hline`/`vline`/`label`, each tagged with a `group`),
`indicators[]`. **All times are epoch milliseconds** (klinecharts' native unit) — convert at
the emitter, never in the browser. Indicator series are shipped from the run, **not recomputed
here**, so the chart shows exactly what the strategy saw.

---

## Conventions

- **Lazy-imported, and since 2026-08-03 WARM-MOUNTED.** `BacktestDetail.tsx` still imports the panel
  via `React.lazy` — klinecharts (~205 kB) and the fixture are never in the app's own bundle, and
  that must stay true: never import this folder eagerly from a page. What changed is *when* the
  lazy import is STARTED and when the panel is mounted. The page kicks the import off on arrival
  (`preloadChartPanel`) and, after an idle beat, mounts the panel HIDDEN behind the Equity tab
  (`ChartTabPanel`'s `keepMounted`), so the ~1.8 s klinecharts spends laying 33k candles out is paid
  in the background instead of under the reader — measured 2,453 ms → 167 ms from clicking Price to
  a painted chart. Two consequences for anything written in this folder:
  - **This component may be mounted in a container that is `visibility: hidden`.** That container
    has a REAL width (that is why it is not `display: none`), so `init()`, `getSize()` and
    `measureInset` all read correct numbers and the reveal needs no resize — verified, canvas width
    1033 px either side of it. But do not add mount-time work that assumes the panel is on screen:
    anything needing paint, an `IntersectionObserver`, or focus has to wait for a real interaction.
  - **It is mounted once and revealed, never remounted.** The `ResizeObserver` still carries every
    genuine size change (fullscreen measures 1033 → 1555 and back). Fullscreen, the tab cycle and
    the layer menus were all re-verified against a warm-mounted instance.
- **Theme.** Colors come from the app theme via `chartStyles.ts` (it reads `@/themes/electric-indigo`,
  the same source `@/themes/chart` uses for Recharts). No raw hex in components. Grid is off.
- **klinecharts data shape.** Spec candles use `time`; klinecharts wants `timestamp`. The
  `candlesToKLine` mapper in `index.tsx` is the single conversion point.
- **The spec ships the run's OWN timeframe and the WHOLE run, and the chart opens with NO fetch**
  (2026-07-27 for the timeframe, 2026-08-06 for the whole run). The bars are in the payload, so the
  chart paints on the first frame — no loading text, no placeholder, no swap under you. **The spec
  is no longer trimmed at all**: `_capped_start` / `_CANDLE_CAP` shipped the newest ~35k bars and
  everything older was fetched per window, which measured **7x more expensive than building the run
  once** (~7.2s a page against 17.8s for a full build that then serves in 0.004s).
  - **Why not coarsen.** An even earlier design stepped a long run's bars UP (that same run shipped
    H4). It could show the whole span and still be useless: H4 is a timeframe the run's trades and
    blocked setups line up with nowhere. Covering the span was the wrong thing to buy with the
    payload budget — and the payload turned out not to be the binding cost at all.
  - 🔴 **The whole run is HELD, never APPLIED.** `spec.candles` is the source; `baseCandles` is a
    window of it, `APPLIED_BARS` (12,000) wide. Handing klinecharts all 155,798 bars is a **MEASURED
    30,828 ms main-thread freeze** — `applyNewData` lays every candle out synchronously — against
    508 ms with the window. **This is the constraint to design against in this folder**, and it is
    not the network and not the payload.
  - **Older history is PAGED IN on scroll-left from MEMORY** — a binary search and an `Array.slice`,
    no fetch. `spec.historyStartMs` is the run's start; the panel extends from the oldest applied bar
    back toward it, one `PAGE_BARS` (12,000) chunk at a time. `loadNewer` is its mirror, and it has
    to exist: after a jump the window's right edge is in the past, so scrolling toward the present
    needs a real answer. See *Paging* below.
  - `runTimeframe` still exists on the contract and still drives `openMin`, because a CACHED spec from
    the coarsening era carries a stepped-up `baseTimeframe` with the run's real TF here. On a fresh
    spec the two are equal, so the auto-drill-down path is inert.
- **Timeframe — up = display, down = drill-down.** The segmented control offers two kinds of TF.
  **At or above the base** (`DISPLAY_TFS`, filtered to TFs ≥ and divisible by the spec's base TF):
  `resample` aggregates base bars up (epoch-aligned buckets) — display only, `spec.baseTimeframe`
  stays the source of truth. **Below the base** (`FETCH_TFS` = M1/M5/M15/M30/H1): these can't be
  resampled up,
  so they are **drill-down** — offered ONLY when the host passes an `onRequestCandles(tf, fromMs,
  toMs)` fetcher (BacktestDetail wires it to `GET /backtests/runs/{id}/candles`, gated to intraday
  runs — a D1/NT8 run has no sub-base bars). Selecting one enters `isFetchMode`: the panel pulls ONE
  window of `FETCH_CHUNK_BARS` (12,000) bars **anchored on the VIEWPORT**, weighted `FETCH_LEAD_FRAC`
  (25%) past it and the rest behind, and `displayCandles` becomes those `fetched` candles. Older bars
  arrive by PAGING (`drillOlder`), exactly as they do at the run's own timeframe.
  - 🔴 **It anchored on the RUN'S LAST BAR until 2026-08-06, and that is what made M1/M5 look broken.**
    A fixed lookback (45d M1 / 270d M5) back from `spec.candles[last].time` meant pressing M5 while
    reading 2020-08-05 applied `2025-11-09 .. 2026-08-06` — six years forward, with nothing on screen
    saying so — while M30 and H1 stayed put because they are resamples of loaded bars. **That is
    exactly the split it was reported as.** The lookback also rested on a stale belief about depth:
    the same endpoint returns **853 M5 bars** for 2020-08-02→06.
  - **The anchor is `viewCentreRef`, NOT `visibleCentreTs()`.** The latter reads klinecharts' visible
    INDEX range against `displayCandlesRef`, which is correct only while those two agree — and a
    timeframe switch is the one moment they do not, because the array has already been swapped while
    the index range still describes the old one. A timestamp recorded on every viewport change
    survives that.
  - **A drill-down LANDS on its anchor** (`drillTo`), borrowing `goToDate`'s `jumpingRef` +
    `pendingJumpRef`. Anchoring alone is not enough: `applyNewData` parks the view on the newest bar
    it was handed, which measured 2.5 months past the moment being read.
  - **The cache is keyed on the timeframe AND the range it covers** (`DrillWindow`). It used to be the
    timeframe alone, on the reasoning that a completed run's window is fixed — true then, false the
    moment the window follows the reader, since a drill at 2020 would be served the window pulled for
    2026. A hit requires the anchor to fall inside what was actually fetched.
  - **A drill-down shows the loaded bars until the finer ones land — never nothing.** A drill-down is
    a network pull, so `displayCandles` falls back to `baseCandles` while `fetched` is empty and the
    header names what is actually on screen (`showing M15 — loading these bars…`) — bars that don't
    match the TF button would otherwise be a silent lie. ⚠ **That placeholder is also a trap for a
    BROWSER CHECK**: the applied-window seam reads a perfectly stable M15 window while the fetch is in
    flight, so a poll that settles on "it stopped moving" reports the placeholder. Wait for the
    loading line to clear — a first pass here reported *M1 works* off an M15 readout.
  - **`FETCH_TFS` still runs M1→H1** even though a fresh spec now ships the run's own TF (so only
    M1/M5 sit below it). The extra rungs cost nothing and keep a CACHED coarsened spec — H4 base with
    an M15 run — usable at the timeframe it traded.

- **Paging older history (scroll left).** `chart.setLoadDataCallback` on `LoadDataType.Forward` →
  `loadOlder()` → one page from the run's own feed (`onRequestCandles`, i.e.
  `GET /runs/{id}/candles`), stopping at `spec.historyStartMs`. Four things hold it together:
  - **`baseCandles` state, not `spec.candles`,** is what the chart derives from — it starts as the
    shipped window and GROWS by prepending each page. Sessions and day breaks derive from it too, so
    paged-in history gets them; a `baseCandlesRef` feeds the callback, which is registered once on
    mount and would otherwise close over the first render's candles forever.
  - **`skipApplyRef`.** klinecharts has already merged a page AND kept the scroll position, so the
    `applyNewData` effect must NOT re-run for it — that would throw both away and snap the view back
    on every page. Set it before the state update; the effect clears it.
  - **A page goes to whichever list `displayCandles` is reading** — `fetched` in drill-down,
    `baseCandles` otherwise. ⚠ **`pagingOffRef` is DELETED (2026-08-06).** It disabled paging outright
    in drill-down, which was right while a drill-down held one fixed full-depth window and wrong the
    moment it held a window anchored on the reader: the wall would simply have moved, and at a
    historical boundary the backend reports no `hard_edge`, so the red *no earlier data* line
    correctly does not draw and the reader gets a blank strip with nothing saying why. The hazard it
    named — splicing base-TF bars into a 1m chart — is answered by routing the page instead of
    refusing it.
  - **Overlap guard.** A page is filtered to bars strictly older than the current oldest, so a feed
    that answers with an overlapping window can't duplicate bars.
  - **The ANALYSIS comes with the spec, and a page fetches nothing** (2026-08-06). Everything on
    this chart except the TRADES used to be emitted per-window server-side, so a page had to ask for
    its own overlays / blocks / misses / missNoise (`analysis=true` → `chart_spec._page_analysis`)
    or the Structure, Fair Value Gaps, Blocked and Missed layers went silently empty the moment you
    scrolled past the shipped candles, with their toggles still reading ON. **That whole path is
    deleted on both sides** — the spec carries every window's analysis, so `allOverlays` reads
    `spec.*` directly and the 2026-08-02 guarantee (a layer reaches exactly as far back as the bars
    do) is now structural rather than maintained by a merge. `pagedAnalysis`, `mergePageAnalysis`,
    `overlayKey`, `mergeById` and `seededNoiseRef` went with it.
    - ⚠ **`reconcileToggles` STAYS, and it is still load-bearing.** `groupsOn` was rebuilt from
      `overlayGroups` on every change — harmless only while that list never changed. The roster no
      longer changes as you page, but it must still survive a SPEC swap without re-seeding, and
      re-seeding with the defaults is what would switch the reader's layers off under them.
      `reconcileToggles(prev, roster)` keeps an answer already given, defaults only genuinely new
      keys, and returns `prev` unchanged when nothing moved so the effect cannot loop.
    - ⚠ **Do not reintroduce a per-window fetch to "save payload".** It was measured at ~7.2s a
      page against 17.8s to build the entire run once and 0.004s to serve it thereafter, and a deep
      `goToDate` paid it fourteen times over — 90.3s for one jump.
  - **A page in flight is drawn, not silent** (`LOADING_EDGE`, 2026-07-30). Scrolling past the loaded
    bars gave a blank strip with nothing on it — indistinguishable from the end of the run's data, so
    a ~1.5s page read as "there is nothing back here". While `pagingOlder` (or a jump's `jumping`) is
    set, the panel draws a dashed accent line at the OLDEST loaded bar and **shades the empty strip
    behind it** with a `Loading earlier bars…` chip in it. The shading is the point: a bare line
    leaves the reader guessing which SIDE of it is loading. The chip centres in the strip once it is
    ≥ `LOADING_LABEL_MIN_GAP` (190px) wide and otherwise parks just inside the data, so it is never
    half off the pane. Same template shape as `DATA_EDGE` and deliberately its opposite — that one
    marks a WALL (nothing older exists), this one marks a WAIT.
- **Go to date** (`GoToDate` in `index.tsx`, header pill next to the timeframe). Type a date, land on
  it — the answer to reach costing a long drag once history pages in. It sits by the timeframe because
  the two answer halves of one question: TF picks the bar SIZE, this picks WHERE.
  - ⚠ **Its `<input type="date">` carries `DATE_INDICATOR_CLS` from `@/lib/inputs` (2026-08-16), and
    that is the ONE thing this panel imports from outside its own tree.** Chrome draws the calendar
    button as a near-black SVG, invisible on this theme; the rule and its incident live in
    `../../CLAUDE.md` → *The period filter*. It is a class-name constant, not page furniture, which
    is why it does not breach the strategy-agnostic rule — and it lives in `lib/` precisely so this
    panel need not import it from `PeriodPicker`.
  - **It reuses the paging machinery above rather than adding a second one.** `goToDate` calls
    `loadOlder()` in a loop until the oldest loaded bar covers the target. klinecharts' own callback
    can't be asked to do this — it fires ONE page, and only when the viewport actually reaches the
    left edge — so the jump drives `loadOlder` directly. Two consequences worth keeping straight:
    it advances `baseCandlesRef` itself each round (that ref is where `loadOlder` reads its cursor,
    and state hasn't landed yet mid-loop), and it commits **one** `setBaseCandles` at the end — a set
    per page would re-apply and repaint the whole chart N times.
  - **A jump that paged does NOT set `skipApplyRef`** — the opposite of a scroll-left page. klinecharts
    has never seen these bars (this path bypasses its callback), so the chart MUST re-apply. That
    re-apply snaps the view to the right edge, which is why the scroll is deferred to `pendingJumpRef`
    and flushed by an effect declared AFTER the `applyNewData` effect. A jump inside the loaded window
    pages nothing and scrolls immediately.
  - **The two paths are mutually exclusive by `jumpingRef`**, which the load-data callback also checks:
    both splice onto the front of the same array, and two writers would duplicate or drop bars.
  - **Local midnight, not UTC.** klinecharts prints its time axis in the browser's timezone, so
    `dayStartMs` parses `YYYY-MM-DD` as LOCAL midnight — the instant sitting under that date on screen.
    `new Date("2026-03-05")` parses as UTC and lands on the wrong side of the day west of Greenwich;
    `toIsoDay` is its inverse for the same reason (never `toISOString().slice(0,10)`).
  - **The target is CENTRED, not parked on the right edge** where `scrollToDataIndex` leaves it — a
    date with nothing after it reads as the end of the run's data. It scrolls to `target + half a
    visible screen` (`getVisibleRange()`), so the lead-up stays on screen.
  - **A drill-down jump RE-ANCHORS its fetch** (`goToDate`'s `isFetchModeRef` branch → `drillTo`).
    Before 2026-08-06 there was no such branch and the jump degraded silently to a scroll inside
    whatever the one-shot fetch happened to hold. Step walks markers through the same call, so it
    reaches a marker outside the loaded window at M1/M5 too.
  - **Bounds are the span the chart can REACH** — everything loaded plus everything paging can still
    get to (`spec.historyStartMs`); **in drill-down that is now the run's own span too**, floored at
    the broker's edge for that timeframe once a request has MEASURED one, never at a guess about how
    much M1 history the feed keeps. Clamped in CODE as
    well as via the input's `min`/`max`, because a native bound stops the calendar widget and nothing
    else (the lesson `PeriodPicker` learned about the history floor). A weekend/holiday date has no bar
    of its own, so `indexAtOrAfter` lands on the NEXT trading bar — what "take me to the 5th" means
    when the 5th is a Sunday.
  - **A deep jump is a real wait** and says so: measured on the 2021→2026 M15 run, 2025-03-05 back to
    2022-09-15 is 6 pages / ~20s / ~101k bars, and reaching the run's start is 3 more / ~10s / 131k.
    So the pill reads `loading <date>…` in accent while it runs — naming the date, because "loading…"
    alone leaves the reader unsure the chart even took it.
  - **The red "no earlier data" edge.** The backend returns `data_start_ms` + `hard_edge`: `hard_edge`
    is True only when the oldest bar is the broker's TRUE limit (feed has nothing older, not our render
    cap — `_DRILL_CANDLE_CAP` 60k sits above M1/M5 depth so it never binds and can't fake a boundary).
    When set, the panel draws the `DATA_EDGE` overlay — a **red dashed full-height line** with a label
    ("No earlier 1-minute data" / "No earlier 5-minute data") at that bar. So a hard feed limit reads
    as a wall you scroll into, never a blank chart. `available: false` (empty candles) now means the
    feed is genuinely unreachable (agent offline) — shown as "no M1 available (data feed offline?)".
  - **Overlays are clipped to the loaded candles.** klinecharts clamps an overlay point whose
    timestamp is outside the data to the plot edge, so without this every trade/session/day-break
    older than a drill-down TF's data edge would pile its markers up in the empty no-data region. All
    auto-generated overlays (trades — by ENTRY time; sessions; day breaks; generic box/hline/vline
    structure) are filtered to `[loadedLoTs, loadedHiTs]` (the loaded candles' time bounds) before
    creation, so NOTHING draws left of the red edge line. User-drawn fibs are exempt (the user placed
    them). In display mode the candles cover the whole run, so the filter is a no-op there.
  - Switching TF re-applies data; it must NOT re-init the chart, so overlays (anchored by timestamp,
    incl. trade markers) survive the switch and land ON the 1m/5m candles — that's the sniper-entry
    view. The `DATA_EDGE` overlay is rebuilt after each data change like the other vline overlays.
- **Step** (`MarkerNav` in `index.tsx`, header pill next to Go to date, 2026-08-01) — `◀ Loss 12/60 ▶`.
  The other answer to "where": Go to date takes a calendar date, this walks the MARKERS. Reading a
  run's losers back to back was a scroll hunt across years of bars; it is now two keys.
  - **It has no set of its own and no filters of its own — the set is whatever the Analysis dropdown
    is SHOWING**, oldest to newest. Untick Winners and ◀ walks the losers; turn Trades off and leave
    Blocked on and it walks the refusals; leave both on and it interleaves them by time. This is the
    whole design. A second "winners only" control would be a second place for the chart and the
    navigator to disagree, and the navigator can never step to something that isn't drawn.
    `navMarkers` therefore reuses the drawing effects' own predicates (`winnersOn`/`losersOn`,
    `hiddenLayers`, `blockVisible`, `missVisible`) — change one of those and check both.
  - **The one place it deliberately parts company with the drawing effects is the loaded-candle
    clip.** They skip a marker outside `[loadedLoTs, loadedHiTs]` because klinecharts would clamp it
    onto the plot edge; the navigator must still LIST it, since reaching it is the entire point. It
    calls `goToDate`, so a step into unloaded history pages the bars in exactly like a typed date —
    one machinery, not two.
  - **It parks on `{ id, ts }`, not on an index.** The id is what finds the current position; the
    timestamp is what lets a marker leave the set under you (untick Losers while parked on a loss)
    and have the next press continue FROM THERE rather than teleport back to the viewport. The id is
    kind-prefixed AND layer-qualified — a stack merges several runs' trade lists, and two legs
    numbering their own trades from 1 would otherwise collide and walk in circles.
  - **The FIRST press anchors on the middle of the plot** (`visibleCentreTs`), so ◀ means "the last
    one before what I'm looking at", not "the last one in the run". Comparison is strict, so an
    anchor that IS a marker steps off it instead of onto itself.
  - **A step CENTRES its target, so `FOCUS` marks it** — an accent dashed vline under its own overlay
    name (registered from the same `vline` shape as `VLINE`/`DAY_BREAK`). Its own name is load-bearing:
    the generic structure effect calls `removeOverlay({ name: VLINE })`, which would wipe a shared one.
    Without the line, "which of the three trades on screen did it take me to" has no answer.
  - **← / → work only while the pointer is over the panel** (`hoveredRef`, set on the ROOT div so the
    keys keep working after clicking an arrow). The arrow keys belong to the page everywhere else, and
    a chart that swallowed them globally would be a bug on every host that embeds two of these.
  - ⚠ **A later overlay rebuild REPAINTS the focus line under the trade boxes it crosses**, because
    klinecharts draws overlays in creation order and the trade effects re-create theirs on any
    change (a Chart setting, a filter). MEASURED while proving the annotations toggle: 127 pixels of
    that one dashed column, and nothing else on the frame. Cosmetic, pre-existing, recorded here so
    the next reader does not chase it as a bug in whatever they just changed.
  - **Both arrows disable while `jumping`** and `stepMarker` bails on `jumpingRef` — `goToDate`
    refuses to start a second jump, so without the guard the readout would advance while the chart
    stood still.
- **Deep debug** — one row at the top of the **Analysis** menu, on or off (2026-08-02).
  It switches the CONTEXT you want behind any trade you are interrogating: **Fibs, External
  Structure and Fair Value Gaps.** Reading a run one trade at a time meant setting those three by
  hand across two dropdowns and unsetting them again constantly.
  - **It is purely ADDITIVE, and that is what makes it a toggle rather than a mode.** It does not
    touch WHICH trades are drawn — Winners / Losers / Blocked / Missed stay exactly where the reader
    set them, and Deep debug deepens whatever is on screen. Untick Winners and it deepens the losers;
    Step re-scopes with them and needs no help from here. **This was its third shape** (Aaron's call):
    it began as a segmented `Winners | Losers` pill beside the menus, then a four-way radio inside
    Analysis, and both owned the outcome filter — which meant asking "winners, losers or both" in two
    places that could disagree, and having to answer "what does OFF restore?". Additive has neither
    problem: off means off, and the filter has one home.
  - **It lives INSIDE Analysis, above the layers it switches**, because that is what it is — a
    shortcut through this menu, not a second place layer state lives. It reaches into the *Structure*
    menu for External Structure, which is the case for having it at all.
  - **On/off is DERIVED from those layers, never remembered** (`debugOn`). Switch the gaps off by
    hand and the row unticks itself, because deep debug is no longer what is on screen — the panel's
    standing lesson (a label is a claim about state somewhere else) in miniature. `toggleDebug` then
    sets all of them to `!debugOn`, so a half-set state resolves to fully on with one press.
  - ⚠ **The write is unconditional, the READ is not.** Setting a layer the run never emitted is inert
    (an absent group is dropped by the next `reconcileToggles`; `tradeFibsOn` with no recorded fib
    draws nothing), but a READ over layers that cannot exist is vacuously TRUE and would pin the row
    permanently ON. Hence `debugGroups` filters to groups the run carries, the fib clause is
    `!debugFibs || tradeFibsOn`, and `debugAvailable` hides the row outright when there is nothing to
    deepen — an NT8/MT5 run, or a Python run finished before the fib field existed.
  - **The groups are `DEBUG_ON_GROUPS`, read out of `STRUCTURE_GROUPS[0]` / `ANALYSIS_GROUPS[0]`**
    rather than retyped, so a rename in `overlays.ts` carries instead of silently switching nothing
    on. The fib is switched alongside them but is not IN the list — it is a trade sub-layer, not an
    overlay group.
  - **`MenuItem` grew two fields for this rather than a fourth hand-rolled menu** (see the
    `ToggleMenu` rule below): `section` draws a caption + rule above a row, and `action` marks a row
    as a shortcut so the header's `on/total` still counts only layers — a count that included
    shortcuts would stop describing how much is on the chart, which is its whole job. Measured:
    `Analysis 3/7` at rest, `5/7` with Deep debug on.
- **Overlays are registered once, created per-spec.** Custom templates live in `overlays.ts`
  (`registerChartOverlays()`, guarded so StrictMode/remounts don't double-register). The panel
  creates instances with `points` (anchored by `timestamp`) + `extendData` (colors/labels).
  `applyNewData` can clear overlays, so the overlay-build effect runs AFTER the data effect and
  re-creates everything on every TF switch / toggle. Geometry is derived from BASE candles so it
  is TF-invariant.
- **Sessions are data, placed DST-correctly.** `sessions.ts` converts a session's local time
  (its IANA `tz`) → true UTC (via `Intl`, reading the real offset per date) → broker axis
  (`+ brokerGmtOffsetHours`). Verified: London shifts BST↔GMT across the year; Tokyo is fixed.
  Boxes hug the high/low of the candles inside each window. **Managed from an on-chart "Sessions"
  legend** (TradingView indicator-legend style) pinned top-left over the plot — a pill showing the
  active count that opens a popover with a Show/Hide-all toggle, a per-session row each, and **Day
  breaks** below a rule. NOT in a header dropdown. **The legend owns everything CLOCK-driven**: day
  breaks ARE the daily session boundary, so having them in the header put the two halves of "when did
  the day/session start" in two different places. One roster (`clockLayerCount` / `anyClockLayerOn` /
  `setAllClockLayers`) drives the pill count, the dot and Show/Hide-all together — counting day breaks
  in the pill while leaving them out of "all" would be a quiet lie. To keep that top-left corner clear for the legend, klinecharts' own candle + indicator
  tooltips are set `showRule: 'follow_cross'` in `chartStyles.ts` (the OHLC/indicator legend appears on
  crosshair hover instead of being permanently pinned).
- **Trades** (`TRADE` overlay): a **profit-depth view**, not a plain box. From the entry it fills
  **both sides**. The FAVOURABLE run is two shades of a LIGHT mint (`favColor`, deliberately lighter
  than the candle up-colour so the band never blends into the green candles inside it) — SOLID
  entry→where profit was actually banked (`profitLegs`, else the exit on a win), FAINT on to the
  deepest point it ran (`mfePrice`) without banking. The ADVERSE run mirrors it in red (`advColor`):
  a **winner** shows one FAINT band entry→`maePrice` (the drawdown it sat through and recovered),
  a **loser** a DARKER band entry→**stop** (up to the stop line) plus a faint tail if price ran
  past the stop (gap/slippage) on to `maePrice`. Each level (stop,
  each profit-take, the entry) is a **thin dotted line** with a **small dot** at the left edge and a
  compact **rounded label** (`SL`/`TP1`/`TP2`/`TP3`/`Exit`/`Entry`/`DD`/`Best`; the TP/Exit
  label comes from the leg's exit id via `chart_spec._leg_label`, one style for every rung — no
  per-TP colours). 🔴 **Every one of these words can be switched
  off whole** — Chart settings → Trades → *Annotate trades* (2026-08-20): the lines, the dots and the
  bands stay, and only what NAMES the trade survives in the chip. See *Chart settings* above.
  **Every label states its own PRICE** (`SL 4031.84`, not `SL`) as of 2026-08-03,
  Aaron's call: these are the trade's record of what happened, so each carries the number it
  happened at instead of making you read it off the axis — `precision` rides in on `extendData`.
  **`DD` (`maePrice`) and `Best` (`mfePrice`) landed with it** — how far the trade ran each
  way, which the layer drew as band edges and never named. Each is drawn only where it says
  something its neighbours don't: `Best` needs a REAL `mfePrice` that ran PAST what was banked
  (it falls back to the banked/exit price, which the `Exit` chip already states), and `DD` needs
  to have gone adversely past the entry — otherwise a trade that never moved against itself prints
  `DD` on the entry's own pixel row. ⚠ On a stop-out `DD` sits within a hair of `SL`
  (measured: 0.05–0.62 on this instrument) so the two are always pushed apart by the de-collider;
  that is correct rather than noise — the gap between them is how far past the stop price ran. **The
  entry is the exception: no line across, just a short tick where the green begins** (the fill edge is
  the entry). Labels are collected, **de-collided top→down** (so a TP that sits right by the entry
  never stacks on it), then drawn just OUTSIDE the box to the left, flipping inside only if they would
  clip the pane edge. **Gotcha — a klinecharts `text` figure paints its OWN background:** `TextStyle`
  carries `backgroundColor`/`borderColor`/`borderRadius`/padding and the DEFAULT overlay text style is
  a solid BLUE chip, so a bare `text` figure renders as an ugly blue tag. The labels therefore style
  the text figure directly (subtle dark `backgroundColor`, rounded, thin border) — never a separate
  `rect` behind a bare `text`. The `mfePrice` line is a faint guide (the top of the faint band); it is
  labelled `Best` only when it outran what was banked, else it stays unlabelled as before. All prices arrive via `extendData`
  and are converted to pixels with the callback's **`yAxis.convertToPixel`** (the two overlay points
  give the entry/exit x-span) — so a variable number of legs needs no extra points. `overlays.ts`
  stays theme-free (fav/adv/entry/chip colours are passed in). **Degrades gracefully:** a trade
  lacking the rich fields (`mfePrice`/`profitLegs` — an NT8/MT5 run, or an old Python run whose stored
  `equity_curve.json` predates them) falls back to the original entry→exit outcome box (win green /
  loss red, dashed border + a direction triangle for a secondary). **A SECONDARY trade says so in
  words** (2026-08-06, Aaron's ask): the outcome chip reads **`SEC · Won`**, and on the degraded path a
  small `SEC` chip sits beyond the entry arrow. It had only the dashed box border before, which is
  invisible in practice — a dashed border reads as "different" only when a solid one is beside it, and a
  re-entry is rare enough that there usually is not one on screen. ⚠ **The first version pinned that
  chip under the ENTRY on both paths and it was UNREADABLE on real data, which is worth recording because
  the reasoning for it was sound**: the question a reader has is *why is there a SECOND trade on this leg*,
  which is a question about the entry — but directly under the entry point is exactly where the `Entry` /
  `SL` / `DD` price chips stack, and **a re-entry is TIGHT BY CONSTRUCTION, which is the whole
  idea**, so its box is short and those chips are already almost on top of each other. Screenshotted on
  2024-12-02, `DD 2634.29` and `SEC` were overlapping and `SL 2634.56` was touching it. The outcome
  chip is centred beyond the trade's resolved extreme and is the one label with clear air around it.
  ⚠ **It reads `SEC` FIRST (`SEC · Won`), so the fact that it is a re-entry survives being skimmed** —
  win or lose was explicitly not the point of the ask. ⚠ **The degraded path keeps the entry chip even
  though an NT8/MT5 trade cannot be a secondary today**: a marker that appeared only on the rich path
  would read as *not a re-entry* rather than as *this renderer had less to work with*, and an absence that
  looks like an answer is this repo's most-repeated defect. **The standing lesson is small and this folder
  has recorded it before: a placement can be right in principle and wrong on the data — render it.**
  🔴 **The tag GENERALISED on 2026-08-20, and the reason is the standing lesson rather than the
  feature.** A trade now states which BOOK it came from — the strategy's own setup, the re-entry,
  or a RECOVERY (the counter-trade the loss-recovery rule takes after a loss) — and any non-primary
  kind wears its own three-letter tag in the same slot (`REC · Won`).

  🔴 **SINCE 2026-08-21 A RE-ENTRY IS TAGGED BY WHAT THE TRADE IT FOLLOWED DID, NOT BY ITS BOOK** —
  `BE+` after a scratch, `SL+` after a stop-out, off the spec's optional `after`. Aaron, reading a
  run with both re-entry triggers on: *"fix the label line so I could tell the difference between a
  secondary that was re-entering from a breakeven versus one re-entering from the primary at a stop
  loss."* **One `SEC` on both is a tag that names the machinery instead of the situation**, and the
  situation is the whole reason the second trade exists — a scratch and a stop-out want different
  re-entries and the run may hold 107 of them. ⚠ **`after` ABSENT falls back to `SEC` rather than
  picking a side**: a re-entry can be armed through a precondition that asks nothing of the trade
  before it, and every run stored before that date carries no `after` at all — so the neutral tag
  is what "we cannot tell" looks like, and only a re-run turns it into `BE+` / `SL+`. ⚠ **A PRIMARY
  now wears `A+` where it wore nothing**, because "no tag" is only readable as "primary" once you
  already know that is the rule. 🔴 **`A+` is `mpc_sos_fade`'s own word and this panel draws every
  strategy's trades**, so on a `mpc_bleg` chart it is the wrong word for the right trade; it is
  hard-coded in `overlays.ts::PRIMARY_TAG` with that cost named, because the honest fix is a
  per-strategy tag on the spec and that needs a column on the strategies table for a LABEL. **The bug that prompted it was
  NOT a missing tag.** Recovery trades reached the chart with no `mfe_price`/`mae_price` on them, so
  every one took the DEGRADED path and drew as a bare rectangle with a direction triangle and nothing
  else — no `Entry`, no `SL`, no bands, no chip. Screenshotted beside a normal loser wearing its full
  profit-depth view, it read as *a different kind of thing on this chart*, which is the wrong
  conclusion twice over: same kind of thing, thinner record. **A fallback is not a style. Rendering an
  absence as a distinct SHAPE turns "we recorded less" into "this is different", and nothing on the
  chart lets a reader tell the two apart** — the same defect as the `SEC`-only-on-the-rich-path one
  just above, arriving from the DATA side instead of the drawing side. ⚠ **The fix was entirely on the
  data side and not one line of the drawing changed**: `mpc_sos_fade/recovery.py` now carries the
  excursion, and the identical figures render it. ⚠ **A recovery trade legitimately shows NO
  `TP1`/`TP2`** — that rule has no target ladder, it locks at +1R and trails — so that absence IS the
  picture rather than another thin record. ⚠ **A run STORED before this lands keeps the thin record**:
  `_build_trades` reads the run's saved `equity_curve`, nothing backfills it, so an old run still
  draws bare rectangles and only a re-run fixes it. The rich fields are emitted by
  `backtest/output.py` (`mfe_price`/`mae_price`/`stop_price`/`legs`, all reporting-only — parity-safe)
  → `chart_spec` (which filters `legs` to real profit-takes beyond a 0.1R scratch band, so a
  breakeven-stop fill is never drawn as profit, and attaches each surviving leg's label). One on/off
  toggle for all trades (`tradesOn`), driven from BOTH the **Analysis** dropdown AND the right-click
  chart menu — same state, either surface flips it. **Winners / Scratches / Losers outcome filters**
  (`winnersOn` / `scratchesOn` / `losersOn`, all default ON) sit under it as INDENTED sub-rows in
  Analysis, each with its count, so a run can be read as all-winners or all-losers without hunting
  trade by trade. They're listed only while `tradesOn` — with trades hidden they'd be inert switches
  — and **Scratches is listed only when the run HAS any**, since a permanently-0 chip is a control
  nobody can use. Every one of them, the box colour, the navigator pill and the chip read the SAME
  `tradeOutcome(tr)`, so a trade's colour and the filter that shows it can never disagree. A single
  **outcome chip** (`Won` green / `Scratch` grey / `Lost` red) sits
  horizontally **centred** over the trade, just BEYOND its **resolved extreme** — a win past the
  furthest favourable point (`mfePrice`), a loss past the furthest adverse point (`maePrice`, behind
  the stop) — so it always points the way the trade resolved (above a long win / below a long loss,
  mirrored for a short). Added because, once a winner also shows a red drawdown band, the result is no
  longer obvious from colour alone. It's a derived verdict, NOT the raw exit reason — no exit-reason
  text (`stop`/`S-RUN`/…) is ever drawn.

  🔴 **SCRATCH is a third state and it landed 2026-08-18, because `pnl > 0` had been drawing a
  trade that netted EXACTLY $0.00 as a loss.** On run `295a6ff29d21` the chart showed a SHORT
  entered at 4098.60, exited at 4085.07 — visibly in profit — with a red `Lost` chip. Nothing on
  screen could explain it and it read as a bug in the exit code. It was not: the base lot's profit
  had gone to a scale-in ADD the chart never drew (below). ⚠ **The verdict is the BACKEND's**
  (`trades[].outcome`, graded against the run's own median full loss — the same bar the run's
  `scratch_count` KPI uses), so the chart and the KPI row cannot tell two stories about one trade.
  ⚠ **The sign of the P&L is only the FALLBACK, for a run with no losing trade to scale against,
  and the fallback never returns `scratch`** — an ungraded trade is not a measured flat one. ⚠ **A
  run whose `chart_spec.json` was cached before this shipped keeps its old chips until that cache
  is deleted**; nothing versions the file. 🔴 **A scratch is ORANGE (`#ff5c00`) since 2026-08-20,
  and it was `theme.textSecondary` before that.** Grey is off the win/loss axis, which was the point
  — but it is also the chart's DEFAULT neutral, worn by body text, the entry marker and every chip
  with no layer colour, so the third verdict did not read as a verdict at all, it read as a chip
  nobody had coloured in. ⚠ **`TRADE_SCRATCH_COLOR` → `outcomeColor()` is the one place it is
  decided**, feeding the fallback box, the outcome chip (via the overlay's `scratchColor`), the Step
  navigator pill and the Show filters; a literal anywhere else lets two of them grade one trade in
  two colours. ⚠ **The overlay falls back to `entryColor` when `scratchColor` is absent** — an older
  cached spec keeps the grey rather than picking an orange the rest of the page did not agree to.
  ⚠ **It is NOT `theme.warn`, and that is the part worth keeping**: the obvious token (#ffb300) is
  **ΔE 15.8** in Lab from `MISS_COLOR` (#ff9800), i.e. the same colour on a 10px chip — a scratched
  trade and a setup that never finished would have been one signal. The shipped #ff5c00 measures
  **31.4** from the miss amber, **49.3** from the loss red, **80.9** from the blocked pink and
  **101.5** from the grey it replaces. **Re-measure before adding any warm colour to this chart** —
  a palette collision is invisible in the code and obvious on the screen.

  🔴 **A SCALE-IN ADD is drawn — one dotted `Add` line per lot (`trades[].adds`), in the entry's
  own colour, because that is what it is: a further entry at a later price.** Without them the box
  is unreadable in the literal sense — entry, exit and P&L describe arithmetic that does not close,
  and the missing lot was in no field the chart received. Several lots at one price collapse to
  `Add ×3` rather than stacking chips on one pixel row. 🔴 **AMBER since 2026-08-20** (`theme.warn`, via `addColor`), Aaron's call on seeing a real two-add trade: an add IS an entry, which is why it drew in the entry's own colour — and that made the one line on the box which is NOT the trade you opened indistinguishable from the line that is. ⚠ It shares a family with `TRADE_SCRATCH_COLOR` (#ffb300 amber vs #ff5c00 orange-red); they never share a pixel row, but move either AWAY from the other, never toward it. ⚠ **No toggle on the LINES**: they are not
  another view of the trade, they are part of what it held. ⚠ **A run finished before the strategy
  recorded them carries none and there is no backfill** — re-run the backtest.
- **Scale-in detail** (`TRADE_ADD` overlay, `trades[].adds[]` with per-lot exits) — **every add lot
  drawn as the trade it is** (Aaron's ask, 2026-08-20). The `Add` line above says a lot was BOUGHT
  and stops there; this answers the questions a reader actually has of it — how far it ran, what its
  drawdown was, where it came off — because a lot is a position and often carries most of the size.
  🔴 **It is the SAME overlay template, registered a second time under a second name**, so a lot gets
  the identical profit-depth view: two-tone green run, `Best`, `DD`, exit line, outcome
  chip. A bespoke renderer would have been a second implementation of the trade box, free to drift
  about what *how far it ran* means. The two names exist only so the layers clear independently.
  ⚠ **Extracting that template to a const cost it its typing** and the params silently became `any`
  — a template written inline is contextually typed by the `registerOverlay` call and one assigned
  to a bare const is not. `OverlayTemplateArg` is the annotation that keeps the extraction safe;
  `tsc` caught it, which is the only reason it is not still `any`.
  ⚠ **Default OFF, and it requires Trades ON** (unlike Fibs, which is a true peer): an add box with
  no parent trade under it reads as a trade the run never took. With it on, the parent's plain `Add`
  lines are SUPPRESSED via `addsDetailed` — each lot now draws its own `Entry` label on that exact
  pixel row, and two labels for one fill reads as two fills.
  ⚠ **No `stopPrice` and no `tpTargets` on a lot, deliberately.** A lot dies on the base's stop *as
  trailed*, which is neither the base's initial 1R nor anything recorded per lot; and the adds bank
  on their own `L-ATP` target, not the base's fib ladder. Either line would be drawn from a number
  the lot never had, and a wrong line does not announce itself. The overlay degrades without them.
  ⚠ **The chip reads `Add · Won` / `Add · Lost` and has only two states.** The backend grades whole
  trades against the run's median full loss; a lot has no such scale, so its verdict is the sign of
  its own P&L. There is no `scratch` here — a third state would claim a measurement never made.
  ⚠ **The row is counted on `exitPrice`, not on `adds.length`**, so it vanishes for a run stored
  before the strategy recorded per-lot detail rather than sitting there toggling nothing. The count
  is LOTS, since that is how many extra boxes the toggle puts on the chart.
- **Blocked setups** (`BLOCK` overlay, spec `blocks[]`) — **the trades that never happened.** A setup
  the strategy had READY and one of its OWN rules refused places no order, so it appears in no trade
  list, no equity curve and no broker report; without this layer there is no way to judge whether a
  blocking rule protects the account or costs it.
  - **The LINE is the marker.** The overlay's single anchor is the EXACT price the entry limit would
    have rested at. Three figures come off it: a **short horizontal dashed line AT that price**
    (`BLOCK_ENTRY_LINE_BACK` 8 / `_FWD` 46 px, weighted forward the way a resting order waits) — the
    working order, drawn the way a working order is drawn everywhere else, so the marker reads as
    "the limit sat HERE and price never gave it a chance" rather than "something happened on this
    bar"; a **dot** pinning the exact bar on that level (the line alone spans several); and a dashed
    **leader** tying the level to the tag. **The tag is
    parked at the PANE EDGE** — bottom for a refused long, top for a refused short (the way the trade
    would have moved) — never near the price, so it can never sit on the candles; that is also why the
    line has to be long. The tag is clamped so it can never cross the level it points at (possible
    when the price sits right at the pane edge), which would make the line double back. The two insets
    (`BLOCK_TAG_INSET_TOP` 56 / `_BOTTOM` 44) are ASYMMETRIC because the edges aren't equally busy:
    the top carries the pinned OHLC readout (a tag tight against it lands ON that text — the bug that
    set these), the bottom only has to clear the time axis. Raise them if either edge grows a row.
  - **The tag text is UNIFORM: `Blocked`, plus a count when several rules refused the same setup**
    (`Blocked 2`). Every tag looking identical is what makes the layer scannable at a glance, and the
    reasons are one hover away. Do not put reason text back on the chip.
  - **Hover** gives the side, EVERY rule that was refusing it (label + full sentence, primary first)
    and the would-be entry price. The card is a React node in the SAME `pointer-events:none` plane as
    the measurement layer (a card that ate its own hover would flicker), placed from the event's
    **`pageX`/`pageY`** and rendered viewport-`fixed` + clamped like the right-click menu — the overlay
    event's `x`/`y` are PANE-relative, so wrapper padding or a second pane would silently offset it.
    The `BLOCK` template is the ONE here that is deliberately not `ignoreEvent` (klinecharts only fires
    hover on figures that accept events), and its dot and line accept events too, so the LINE is
    hoverable, not just the chip.
  - **Both readers tolerate the pre-list record shape**, and must keep doing so. `blocked_setups.json`
    is written ONCE at run completion and then lives on disk forever, while the shape it is read with
    keeps moving — the backend reads a lone `label`/`reason` pair as a one-item list, and the panel
    normalises `spec.blocks` on read because `chart_spec.json` is CACHED per run. This already broke
    once (a run silently lost all 312 of its markers, with no error anywhere) and would have taken the
    whole panel down on the frontend side, since every read does `b.reasons.length`. Locked by
    `backend/tests/test_chart_spec_blocks.py`.
  - **`reasons` is a LIST** because several rules can refuse one setup. The panel derives its
    per-reason filter roster from those labels (first-seen order, with counts), exactly as it derives
    stack layers from trades — so it stays strategy-agnostic and a different rule set needs no chart
    change. A block draws while **ANY** of its reasons is still on: requiring ALL would make "show me
    the veto blocks" hide the ones the final hour was also refusing, and those are still veto blocks.
  - **Pink is off the win/loss axis on purpose:** a refused trade is not a loser, and red would read as
    one. Lives in the **Analysis** dropdown, **default OFF** — a diagnostic view, not part of reading
    the run, and a long run has more refusals than trades. Listed only when the run reports any, so an
    NT8/MT5 run (which cannot report them) shows no permanently-empty switch.
- **Missed setups** (`MISS` overlay, spec `misses[]`) — **how close the ones that DIED came.** The
  companion of Blocked, one step earlier in a setup's life: a block is a trade the strategy had
  fully ready and a rule refused; a miss met some of the strategy's confluences and then died. The
  tag is the SCORE (`2/3`, `3/3`), uniform within the layer for the same reason "Blocked" is; hover
  gives **Met** (what it had, as pre-formatted strings the panel prints verbatim) and **Missing**
  (the one thing it didn't), plus the price the entry would have rested at.
  - **One template, two layers.** `MISS` and `BLOCK` are the SAME registered template under two
    names (`const marker` in `overlays.ts`) — they draw the identical thing and forking it would
    guarantee the two drift in look and in bugs. The tag TEXT comes from the host via
    `extendData.text`, so the wording lives in `index.tsx` next to the data it describes; `row: 1`
    parks the Missed tags one step further from the pane edge so the two layers shown together
    don't stack. One `MarkerTipCard` serves both hovers, off one `markerTip` state, for the same
    reason.
  - **Amber, not a new colour.** Blocked pink = a rule said no; missed amber = the setup never
    finished. Siblings on the same "the trade that never happened" axis, both deliberately off the
    win/loss green/red, and matching the Pine's own orange 2-of-3 callout.
  - **`spec.missNoise` decides what the layer OPENS on, and the panel does not know why.** It is a
    list of reason labels to start UNTICKED, derived server-side from each miss's own `near` flag
    (see `backend/CLAUDE.md` → *Missed setups*). On the measured window 50 of 93 markers are "price
    never retraced" — the ordinary way a setup dies — so opening on all of them would bury the 35
    that are actually actionable. Hiding them by NAME here would have put a strategy concept inside
    a panel whose one rule is that it has none; hiding them by an emitter-supplied list of opaque
    strings does not. The hidden reasons are still listed with their counts, so nothing vanishes
    silently, and one click restores any of them.
  - **It filters by SCORE as well as by reason** (2026-08-08, Aaron: *"sometimes I just want to see
    2/3 vs 3/3 because they are legit different"*). A 3/3 had every confluence and still did not
    trade; a 2/3 never got there. **The reason list could already express that split — the seven
    labels map onto the two scores in this strategy — but only for a reader who already knew which
    was which**, which is the friction: a filter that requires you to hold the mapping in your head
    is not a filter, it is a lookup table you perform by hand.
    - **Derived and OPAQUE, exactly like the reason rows.** The panel does not know what a
      confluence is, only that a miss carries `met` / `of`; a strategy scoring out of four lists
      "3 of 4" here without this file changing, which is the contract `of` already had.
    - **Score AND reason — two independent axes.** Unticking "2 of 3" says nothing about the
      reasons, which is the point of splitting them. Score is listed FIRST because it is the
      coarser cut: reason answers *why*, score answers *how close*, and the reader picks the axis
      before the value.
    - ⚠ **Every score starts SHOWN, and that is load-bearing.** The layer's opening view is
      `missNoise`'s recommendation; a score defaulting to hidden would be a SECOND answer to "what
      do I see first" and a reader would have no way to tell which of the two had hidden a marker.
      The browser check asserts it — **without that assertion a mutation defaulting `2/3` hidden
      passed**, which is what the fail-watch was for.
  - Everything else — per-reason filters with ANY-of semantics, clipping to the loaded candles,
    default OFF, listed only when the run reports any — is the Blocked layer's, unchanged.
  - ⚠ **Every row in the Analysis menu now carries `aria-pressed`.** Its on-state used to live only
    in a colour dot and a tick glyph, so nothing outside the pixels could read it — and a test that
    infers a toggle's state from an icon is asserting the icon.
- **Fair value gaps** (`Fair Value Gaps` overlay group, backend `services/fvg_overlays.py`) — **the
  gaps that were LIVE when something happened.** The canonical `engines/fair_value_gaps/` engine is
  replayed server-side over the run's candles and a gap is emitted **only if it was in the engine's
  live list on the bar of a trade ENTRY, a blocked setup, or a missed setup**. Everything else is
  dropped, and when several gaps overlapped at one of those bars ALL of them are drawn.
  - **It is a plain `box` overlay group, so the panel needed no new template and no new effect** —
    the generic overlay pipeline already renders, clips and toggles it. The only new frontend
    concept is `ANALYSIS_GROUPS` in `overlays.ts`: the one list of overlay groups that belong in the
    **Analysis** dropdown rather than Structure, because they describe the strategy's SIGNALS rather
    than what the market drew. `overlayGroups` still backs `groupsOn` for every group; only the MENU
    each row appears in differs (`structureGroups` / `analysisGroups`). Default OFF, with its box
    count on the row, exactly like Blocked and Missed. Adding a second analysis layer is one string.
  - **It sits LAST in Analysis** because it is the context around the three rows above it, not a
    fourth kind of signal — "and show me what the gaps looked like there".
  - **The gaps are `mpc_assistant.pine`'s, not the strategy's**, and the fork is real: the indicator
    runs `fvgMaxCount 8 / fvgRequireClose false / 0.0 below 15m, 0.04 at and above`, while
    `mpc_sos_fade` pins `7 / True / 0.1`. A drawn gap is therefore one the INDICATOR shows, which is
    not always one the bot's entry rule counted (the bot sees strictly fewer). See
    `backend/CLAUDE.md` → *Fair value gaps* — do not "fix" it by repointing the emitter.
  - **Box geometry mirrors the Pine box**: created at `bar_index - 1`, extended every surviving bar,
    and gone on the bar the gap is mitigated or evicted — so `t1` is the bar BEFORE its death, never
    the death bar. mpc showed nothing there.
  - **No border, and bull and bear look identical** — mpc sets `border_color = color(na)` and paints
    both directions the same grey, so a tinted edge would be a shape the indicator doesn't have (its
    only direction cue is a green/red "FVG" caption, which klinecharts boxes have no room for). The
    generic `BOX` template reads **`lineWidth: 0` as "no border"** and switches the rect to `fill` —
    a 0 border SIZE alone still strokes a hairline. That rule is generic, not FVG-specific: some
    sources draw a bordered region, some a bare tint.
  - Dropped from a **stack** spec, for the same reason blocks and misses are: it is anchored to the
    BASE leg's trades, so on a merged chart it would draw gaps at one strategy's entries and nothing
    at the others'. A leg's own page still has it.
- **Order blocks** (`Order Blocks` overlay group, backend `services/ob_overlays.py`, 2026-08-03) —
  **the supply/demand zones that were LIVE when something happened.** Aaron's brother asked to see
  order blocks on the backtest chart; the canonical `engines/order_blocks/` engine is replayed
  server-side under the SAME anchor rule as the gaps (a block is drawn only if it was live on a trade
  ENTRY / blocked / missed bar), so this is the second entry in `ANALYSIS_GROUPS` and cost the panel
  **no new template, no new effect and no new concept** — it is a plain `box` group and the generic
  pipeline already draws, clips, counts and toggles it. Measured on run `432aff31f374`: 2,567 blocks
  created over the window, **579** drawn, beside the gap layer's 661. Default OFF, listed with its
  count, last in Analysis — it and the gaps are the CONTEXT a setup fired into, not a kind of signal.
  - **The BOX is a fixed STUB, and that is the only real difference from the gap layer.** mpc gives
    an order block `OB_STUB` (30) bars from its anchor candle and stretches it to the live bar only
    while price is back within one block-height; a gap box tracks the live bar. That uniform width is
    deliberate on the indicator — it makes a set of zones scan as one family of levels. Two things
    that follow and look wrong until you know: a block's box can end long BEFORE the block dies (the
    zone stays live and keeps answering anchors), and it can end AFTER the bar it died on (the stub
    runs past the live bar into empty space). Backend derivation: `backend/CLAUDE.md` → *Order blocks*.
  - **One deep orange for BOTH directions, drawn as an OUTLINE with a whisper of fill** (`#E65100`,
    mpc's `OB_ACCENT`), with the `OB` tag right-aligned in the box. The blue/red directional
    experiment was tried and REVERTED in the Pine, so bull and bear look identical here exactly as
    they do on the indicator — and the outline is what tells these apart from the borderless grey
    gap boxes they sit among.
  - **It is deliberately NOT in Deep debug** (Aaron's call — "don't add it to the deep debug yet").
    `DEBUG_ON_GROUPS` reads `ANALYSIS_GROUPS[0]`, so a new analysis layer goes on the END of that
    list and joins the preset only when someone decides it belongs in the every-trade reading.
  - **It found a live bug in the generic `BOX` label path**, which had never been used: klinecharts'
    default overlay-text style is a solid BLUE chip, so the first `OB` tag rendered as a blue pill.
    Both the BOX and HLINE label paths shipped carrying it, dormant, and both now spread the shared
    `FLAT_TEXT` style the `LABEL` template already used — see that constant in `overlays.ts`.
  - Dropped from a **stack** spec alongside the gaps, for the same anchored-to-the-base-leg reason.
- **Liquidity levels** (three `Liquidity — …` overlay groups, backend
  `services/liquidity_overlays.py`, 2026-08-08) — **the pools that were live when something fired,
  and WHICH OF THEM PRICE HAD ALREADY TAKEN.** Aaron asked to be able to read a sweep off the
  backtest chart — daily, New York, H4. The canonical `engines/liquidity/` engine is replayed
  server-side under the same anchor rule as the gaps and blocks, and each level is an `hline`.
  **A swept level is drawn DOTTED and GREY, ending at the bar it was taken on, labelled
  `PDH swept · BSL`; a live one is solid in its tier's colour with a bare name.** That styling IS the
  feature — it mirrors `mpc_assistant.pine`, where `showMitLiq` went TRUE on 2026-08-07 so a broken
  level freezes and greys rather than vanishing.
  - **Three rows in Analysis rather than one**, which is the first time a layer here has taken more
    than one. The tiers differ by an order of magnitude: **H4 is 58% of all levels** (measured —
    20,376 of 35,028 over a 6.5-year run), so a reader following daily and session sweeps needs it
    off, and a reader timing an entry needs only it. The indicator gets one switch because it only
    ever draws the ~13 levels live RIGHT NOW.
  - **It cost the panel no new template and no new effect** — three plain `hline` groups and three
    strings in `ANALYSIS_GROUPS`. Fourth entry in the run of layers that landed for a string and a
    colour (gaps, blocks, VWAP, this), and the reason to reach for the generic pipeline first.
  - **They go on the END of `ANALYSIS_GROUPS`**, so `DEBUG_ON_GROUPS` (which reads
    `ANALYSIS_GROUPS[0]`) is untouched and none of them joins Deep debug.
  - ⚠ **The dot colours describe the LIVE levels only**, because a swept level is grey whatever tier
    it came from. That is right: the dot says which rows a layer draws, and a spent pool has stopped
    being one of them. H4 is mpc's own `#FF6B35`, reproduced exactly; the daily/weekly and session
    hues are NOT the indicator's, which draws both in black — invisible on this chart — so each takes
    a hue picked away from structure teal, gap slate and block orange.
  - ⚠ **This is not the same VIEW as the indicator's, and it is not a fork to close.** mpc draws the
    live set and never a level from 2021, because a live chart has no 2021. This draws the historical
    set at the bars that matter. Same definition of a level, different question about which to show.
  - ⚠ **`label` is a TOP-LEVEL overlay field, not a `style` key** — the panel reads `ov.label` and
    spreads `style` separately, so a nested label round-trips fine and never draws. Pinned backend-side.
  - Dropped from a **stack** spec alongside the gaps and blocks: a level is a market fact, but WHICH
    levels were selected for drawing is the base leg's alone.
- **Candlestick reversals** (`CANDLE_MARK` overlay, `Candlestick Reversals` group, 2026-08-08) —
  **one candle repainted navy per setup: the pattern candle at the turn.** Aaron's ask, so he can
  read whether candlestick patterns line up with his reversals and later judge them as a confluence.
  Which candle, and which anchors qualify, are entirely the BACKEND's — see
  `../../../backend/CLAUDE.md` → *Candlestick reversals*. What lives here is the drawing.
  - **klinecharts has no per-bar candle styling, so the layer REPAINTS the bar from the overlay
    plane.** Four points at ONE timestamp carrying high / low / open / close, so the callback gets
    one x and four y's and can rebuild it: a 1px wick rect and a body rect `barSpace.gapBar` wide.
    ⚠ **`gapBar`, never `bar`** — the latter includes the gap between candles, so it would paint
    over the neighbours. ⚠ **The body must be OPAQUE**, because it paints OVER the real candle
    rather than replacing it, and a translucent one reads as a tint rather than a mark. ⚠ **A doji's
    body is zero-height and gets a 1px floor**, exactly as the candle layer gives it — it is the one
    pattern most worth seeing.
  - ⚠ **`setPoints` keeps every point regardless of `totalStep`** (verified in
    `dist/index.esm.js:1308`), which is what makes a 4-point overlay on a 2-step template legal.
  - **The navy is `#2f5fe0` with a `#7ea2ff` edge, and a TRUE navy was tried first and rejected** —
    `#1e3a8a` and darker are effectively invisible on this theme's near-black plot, checked against
    `bgBase` before picking. This is the most navy-reading blue that still stands out against the
    up/down candles it sits between, which is the whole job.
  - 🔴 **The pattern NAME is a Chart setting and defaults OFF** (`candleMarkLabels`, 2026-08-08,
    Aaron's ask). Every mark draws its own tag with **no cross-overlay de-collision** — unlike the
    batched `LABEL` template, which lays its chips out together in pixel space — so two marks a few
    bars apart write their names across the neighbouring candles. **The COLOUR is the marker; the
    name is what you switch on when you are asking which pattern it was.** ⚠ The tag is drawn in the
    EDGE colour, not the navy body, which is what lets a browser check tell *drawn* from *drawn and
    named* — a `navyPixels` check is satisfied by an untagged mark and proves nothing about it.
  - **The layer is WITHDRAWN off the base timeframe — the row AND the drawing.** A candlestick
    pattern is a property of ONE bar size (an M15 hammer is not an H1 hammer), so a resample has
    nothing honest to paint. ⚠ **Both halves are needed**: `groupsOn` keeps the reader's answer
    across a timeframe switch, so gating only the menu row would leave it painting M15 bars over H1
    candles — which is the more dangerous half, because it states something nobody measured.
  - ⚠ **The tag names EVERY pattern on the bar, joined.** It printed `Hammer +1` until 2026-08-08,
    which reads as a claim about the PATTERN — *"how could a pattern have more than one name?"* —
    when it is a fact about the BAR: one candle can satisfy several definitions at once, and every
    Hanging Man is also a Hammer by construction. Two names is a wider tag than one, and a tag
    nobody can interpret is worse than a wide one.
  - **A DIRECTION filter** (2026-08-08, Aaron: *"it's showing candle patterns that [point] nothing
    in the direction of the trade — if I take a long, it's showing my bearish engulfing"*). Three
    sub-toggles under the layer — With the setup / Neutral / Against it — the same shape as the
    Missed layer's score rows. ⚠ **All three start ON**: the opposing tier is half the point of the
    layer (*"if not, it will show me why I was wrong"*), so hiding it is something the reader asks
    for, never a default that quietly answers "there was nothing at the turn". ⚠ **It filters on the
    backend's `align`, never on `patternDir`** — see `backend/CLAUDE.md` for why the panel cannot
    work the setup-relative direction out for itself. Measured: 464 with / 409 neutral / 98 against.
  - **`candleMarkDeepestOnly`** (Chart settings, default OFF) — one candle per setup instead of
    every one in its span. Two readings of the same data: *which level offered the best entry* vs
    *which levels offered one at all*. The full reading is the default because it is what the layer
    was asked for.
  - 🔴 **The chip's candle is chosen by the OUTCOME's question, not by nearness (2026-08-08).**
    Ranking the span's marks on nearness alone put a `Bearish Engulfing` on a long that WON and a
    `Bullish Harami` on a short that won — reported off two screenshots: *"I should see BULLISH
    candle for long trades or BEARISH candle for short trades."* A winner and a 3/3 miss want the
    setup-ALIGNED candle; a **loser wants the OPPOSING one**, because *"if I lost it should default
    to the candle that signaled why I lost."* The rule and its measurements live in
    `../../../backend/CLAUDE.md` → *Which candle a setup is NAMED after*; what lives here is that
    the panel reads **`deepestNames[anchorIndex]` before `label`**. ⚠ **That per-anchor name is not
    a nicety**: one bar can be the deepest of a losing trade and a miss on the same leg, and the
    bar's single `label` is whichever anchor reached it first — nobody's answer in particular.
  - **The trade's outcome chip NAMES the reversal at its turn** — `Won · Bearish Engulfing`, or
    `Won · no candle`. 🔴 **The first attempt was `Won · ✓` / `Won · ✕` and it was unreadable**: a
    tick beside "Won" says *confirmed win*, which is a different claim — *"how would I know a tick
    means a candle was there and an x means none?"* **The name needs no legend, and it is free**,
    since the span's DEEPEST mark is the reversal at the turn and is the one worth naming when only
    one fits. ⚠ **The chip prints NOTHING when the layer is off**, because then the run has not been
    asked and `no candle` would state a measurement nobody took — the `mt5_link` rule again: never
    let "no" and "cannot ask" be the same value. ⚠ **It reads each mark's `spans` / `deepestOf`, not
    "is there a mark between entry and exit"** — spans overlap (a miss's retrace can sit inside a
    trade's hold), so a time-range test would credit a trade with somebody else's candle. ⚠ **It
    follows the direction filter**, so the chip agrees with the candles on screen; naming a bearish
    engulfing with the opposing tier hidden and no navy candle anywhere is the two-sources-one-answer
    trap this chart keeps meeting. ⚠ **It has NO automated check**: the chip is canvas-drawn with no
    DOM and its inputs live in `extendData`, so pinning it would mean contorting the product for the
    test. Verified by driving, both cases; named here rather than skipped.

  🔴 **Moving that computation exposed a TDZ crash worth recording.** `tradePattern` was declared
  above the `candleDirKey` it reads, so the whole panel threw *"Cannot access 'candleDirKey' before
  initialization"* on mount — **and `tsc` was clean**, because a `const` used before its declaration
  inside a closure is legal to the type checker and fails only at runtime. It was caught by DRIVING
  the page, not by the suite. **A green typecheck says nothing about declaration order.**
- **Fibs** (`TRADE_FIB` overlay, `trade.fib`, 2026-08-02) — **the leg each trade was actually
  priced off.** Aaron's brother asked to see the fib run on the points a trade used, so he can read
  which retracement levels it went into. Every level arrives as an explicit `(ratio, price)` pair
  recorded by the strategy when it PLACED the order, so there is **no fib maths in the browser at
  all** — the chart cannot arrive at a different price from the bot. The ladder spans the leg's
  start → the trade's exit, so it reaches back through the retracement rather than beginning at the
  fill. Each level is labelled at the RIGHT edge — the side a hand-drawn fib labels — and carries
  the **ratio only, never the price** (2026-08-03, Aaron's call). Full derivation of the two derived
  readings: `backend/CLAUDE.md` → *Trade fibs*.
  - **It draws the LADDER and nothing else.** It shipped with `entry <ratio>` / `deepest <ratio>`
    accent chips at the right edge; both are gone. The trade underneath already annotates its own
    entry, and how far it ran now belongs with the rest of its annotations (`DD` / `Best`
    in the TRADE template) — one price row labelled twice by two layers is what made the chart read
    as doubled up. `entryRatio` / `deepestRatio` are still computed and still ride on the spec;
    nothing draws them today.
  - **A separate TEMPLATE from `FIB`, deliberately — this one is DATA, not a drawing.** It is
    `lock: true`, every figure is `ignoreEvent`, and it is not draggable, selectable or deletable.
    Same call as `MISS`/`BLOCK` being two names, for the opposite reason: those share a template
    because they draw the same thing; these are split because one is the reader's work and one is
    the run's record.
  - 🟢 **It serves TWO bots since 2026-08-11, and the panel did not change to gain the second.**
    `mpc_bleg` recorded no ladder until then — `tradeFibCount` was 0, so the row correctly hid
    itself and a B-LEG run offered no Fibs at all while being the more fib-native of the two bots.
    Nothing here was edited: the template reads `(ratio, price)` pairs and knows nothing about which
    strategy produced them, which is the payoff on having built it strategy-agnostic.
  - ⚠ **BOTH bots' ladders are measured from the leg EXTREME, and that is a decision rather than an
    accident.** `mpc_bleg`'s own code calls its entry band *the 0.382-0.5 pocket*, measuring from the
    leg ORIGIN — the opposite end. Recording it that way would have shifted every rung onto a
    different retracement while still looking like an ordinary fib. **The visible consequence: on a
    B-LEG trade the band's far edge draws as 0.618, not 0.382.** Same line, named from the other end
    of the same leg. A strategy test pins it in both directions.
  - ⚠ **Every ratio a bot records is one of the eight in `DEFAULT_FIB_LEVELS`, so none falls through
    to `UNNAMED_LEVEL_COLOR`.** That is held by a test on the STRATEGY side, not here — if a future
    bot records a rung outside that set it draws grey, which is the honest fallback and also the tell.
  - ⚠ **No chart rebuild can add this layer to an existing run.** The ladder is written into the
    run's own equity curve at REPLAY time, so *Rebuild chart* cannot supply it and a run predating a
    bot's recording needs a RERUN. Same rule as the day the layer shipped; it now bites B-LEG runs.
  - **It does NOT read the user's configurable ladder** (`fibLevels.ts`) — Aaron's call. A trade's
    levels are a fact about that trade, so retuning the drawing tool must not change them. Only the
    COLOURS are shared, off the frozen `DEFAULT_FIB_LEVELS` constant, so a 0.618 the bot used looks
    like a 0.618 you drew. A ratio the factory set doesn't name renders grey, never invisible.
  - **It is a PEER row, and it reuses the trades effect's own predicates** — the loaded-candle
    clip, the layer isolation, Winners/Losers — so the two layers can never disagree about WHICH
    trades are of interest; its own filters would be a second place for them to differ, the same
    rule Step follows. **It does NOT require Trades to be on** (2026-08-03, Aaron's call: it is its
    own reading of the chart, not an annotation on another row). That is also why **Winners/Losers
    are listed whenever EITHER row is on** — they still filter the fibs, and a layer quietly
    filtered by a control that is off screen is the same failure the per-window paging bug produced.
    It sits directly before Fair value gaps: both are the CONTEXT a setup was priced in rather than
    a kind of signal. Default OFF (eight lines per trade is a lot of chart) and listed
    only when trades actually carry one, so NT8/MT5 and pre-2026-08-02 Python runs show no switch.
  - The leg's start is **clamped into the loaded bars**: a leg beginning before the oldest loaded
    candle would otherwise have klinecharts clamp its left edge onto the plot boundary, drawing the
    ladder across the no-data region as if the leg had started there.
- **Portfolio-stack layering** (`layer` / `layerName` / `layerColor` on a trade — all absent on a
  single-run spec, which is what makes every stack affordance vanish for a normal backtest). With
  several strategies' trades on ONE chart, the outcome alone doesn't say WHOSE trade it was, so the
  outcome chip becomes **`<strategy> · Won`** with a filled dot in the strategy's colour just left of
  it and its border in that colour — the same swatch the stack's equity lines and toggle chips use, so
  the eye matches trade → strategy without reading text. The entry marker takes the layer colour too.
  A **Strategies dropdown** sits beside Analysis (deliberately NOT folded into it — Aaron's call: a
  stack's legs are a different kind of thing from a run's own trades) and hides one strategy's trades
  (`hiddenLayers`), for when overlapping trades need isolating. **The roster is DERIVED from the
  trades themselves**, so the panel stays strategy-agnostic — it sees layers as data, exactly like
  overlay groups, and needs no new props and no knowledge of stacks. The **TP ladder**: every target the trade
  aimed at (`tpTargets` — emitted by `execution.py` → `output.py` `tp_targets` → `chart_spec`,
  reporting-only/parity-safe) is drawn as a FAINT line + dot + `TP1`/`TP2`/…, hit or not, **skipping
  any price a real profit LEG already draws** (that line is solid and says it BANKED there; two
  figures on one pixel row read as two fills). 🔴 **It was gated until 2026-08-20** — next-unhit only,
  and only when `mfePrice` had covered ≥ 33% of the gap to it — which put two shorts from ONE run side
  by side, both "hit TP1 → armed breakeven → scratched at BE", one showing `TP2` and one showing
  nothing. ⚠ **A layer that draws itself only sometimes cannot be read as absence-means-something**:
  a blank chart could not be told from a trade with no targets, so the reader had to go and check
  anyway — which is the cost the gate existed to save. Aaron's call.
  🔴 **EVERY RUNG IS NAMED `TP1`/`TP2`, AND THE REVERSE WAS TRIED AND WITHDRAWN THE SAME DAY
  (2026-08-21).** A rung whose size is 0 places no order and only steps the stop, so it was drawn
  as `Stop tightens` in a neutral colour. At mpc_sos_fade's shipped ladder **both** rungs of a
  primary bank 0%, so that chip became the only thing every A+ chart said. Aaron: *"Why is it that
  my A+ strategies now have annotation Stop Titans? I don't even know what it is. It should just
  show a faint dashed line where TP1 was and where TP2 was, so I could better understand why we
  exited at certain levels."* **The number IS the information.** Whether size comes off at a rung
  is a SETTINGS fact — true of every trade in the run at once — while where the rung SAT is a fact
  about this trade, and it is what a reader is reconstructing. The distinction is already drawn
  without words: a rung is a FAINT dotted line, a banked leg is SOLID. ⚠ **The lesson is about
  who the chip is for: a label that has to be looked up is worth less than one that is slightly
  incomplete.** The withdrawn version optimised against a claim nobody was making. ⚠ `banks` is
  still carried end to end and still never defaulted — this layer just does not spend a chip on it.
  🔴 **A price that is BOTH a rung and where the trade came off reads as ONE chip naming both —
  `TP2 / Exit`.** Aaron: *"If TP2 and exit is the same dash line, just update the label to say
  TP2 / Exit, so I could know."* Before this the rung was skipped whenever a drawn leg shared its
  price, so the reader could not tell *it exited AT its target* from *it exited somewhere the
  ladder never named* — the question the layer exists to answer. **It is not a rare case: 49 of
  206 trades on run `976aff9ec279`.** ⚠ Matched off `drawnLegs`, NOT `legs` — a plain win carries
  no rung detail and its only drawn price is the exit fallback, which is exactly the trade where
  this has to work. ⚠ No merge when the two names already agree, so nothing reads `TP1 / TP1`.
  ⚠ Numbering is by LADDER POSITION, which is the strategy's order and not nearest-first: a
  re-entry prices rung 1 off risk and rung 2 off a fib, so `TP2` can legitimately sit nearer the
  entry than `TP1` (23 of the 45 re-entries on run `687c8df2a523`; every main entry is correctly
  ordered). Sorting here would renumber the strategy's own rungs.
  Supported figure types are
  `circle/line/polygon/rect/text` (verified via `getSupportedFigures`). **Chart price marks:** the
  candle `priceMark.high`/`.low` (highest/lowest-visible-price tags) are turned OFF in `chartStyles.ts`
  — they render on the exact visual extreme, which is where the outcome chip sits, so they collided;
  the last-price line stays on.
- **Generic overlays** (`BOX` / `HLINE` / `VLINE`): render `spec.overlays`, grouped by `group`,
  each group independently toggleable. This is what carries strategy structure (range box,
  buy/sell levels, breakout marker in the fixture) — the chart never knows which strategy made
  them. Style (`color`/`fillColor`/`lineStyle`/`lineWidth`) + `label` come from the spec via
  `extendData`. `vline` spans the pane height (`bounding.height`); its point `value` is a dummy
  (only `x`/timestamp matters).
- **Point labels** (`LABEL`): flat coloured text tags for market structure (no box/border/background —
  Aaron's call, and it matches the Pine's `color(na)` label background). **All visible
  structure labels live in ONE `LABEL` overlay** — its `points` are the anchors and `extendData.items`
  the parallel `{text,color,placement}` array — because klinecharts maps every point to a coordinate,
  so the callback sees them together and **de-collides them in pixel space** (greedy left→right: a chip
  slides away from its anchor — up for a high tag, down for a low — until it clears every placed chip).
  A per-label overlay could never do this (it can't see its neighbours). Only on-screen chips are laid
  out, so it stays cheap. `placement` (`above`/`below`/`center`) sets the initial nudge + slide
  direction. The render effect collects the labels during the group loop and creates the single overlay
  after it.
- **Market-structure overlays (Step 7c).** The canonical `engines/market_structure/` engine is replayed
  over the run's candles **server-side** (`backend/services/structure_overlays.py`, imported by bare
  name — never a second engine) and emitted as generic `hline` + `label` overlays in **four groups that
  are the four TradingView toggles**, same names and order as `indicators/engines/structure_engine.pine`:
  `External Structure` (BOS/SOS break lines + tags, and the active unbroken swing rays),
  `Internal Structure` (iBOS/iSOS for the current external leg), `Historic Internal Structure` (the
  same for older legs), `Swing Point Labels` (HH/HL/LH/LL/ASH/ASL + internal iSH/iSL/…).
  The group names are pinned in `STRUCTURE_GROUPS` (`overlays.ts`) so the panel can (a) default them
  **OFF** — a chart with all structure drawn is unreadable — while every other group defaults ON, and
  (b) order the four together at the end of the Structure menu. **All four are listed whenever a run
  carries any structure at all, even when a group is EMPTY** — they're the Pine's four checkboxes, and
  one that vanishes reads as a missing feature. `Internal Structure` is the one this bites: it holds
  only the CURRENT external leg, so it's legitimately empty on most finished runs (everything older is
  Historic). Empty groups get their dot colour from `STRUCTURE_GROUP_COLOR`.
  **The four toggles NEST exactly like the Pine's**, via each overlay's optional `requires` list (a
  generic `ChartOverlay` field: every named group must ALSO be on for the overlay to draw). Pine hides
  ASH/ASL/HH/HL with `showExternal` regardless of the swing-label toggle, runs the whole internal
  engine only under `showInternal`, and treats internal history as a SUB-filter of it — so an external
  swing tag `requires` External, an internal swing tag `requires` Internal (+ Historic when it belongs
  to an older leg), and a historic internal break `requires` Internal. Switching a structure off can
  therefore never leave its swing tags floating, and Historic is not a peer layer. Computed on the **displayed/base TF** (v1):
  the lines align 1:1 with the bars on screen, and drill-down (M1/M5) shows price only — no per-window
  structure recompute yet. Colour convention follows the source Pine: a swing-HIGH label is bearish-red
  (resting sell-side liquidity), a swing-LOW label bullish-teal; a break takes its direction's colour.
  **Break lines run wick-to-wick** — anchored at the swing that broke so they start on that candle's
  actual wick. External lines use `bull_bos_h_loc`/`bear_bos_l_loc` (the origin candle's high/low equals
  the line price — verified). Internal lines use the engine's `ifib_seed_ash/asl` + `_loc` (the internal
  leg anchors, which land exactly on the wick), NOT `int_break_origin_loc` — that's the order-block scan
  origin and floats off the wick (the bug that made internal lines miss their candles).
  **Label coordinates mirror the Pine** so the chart reads like TradingView: a **break tag**
  (BOS/SOS/iBOS/iSOS) anchors at the **horizontal midpoint of its break line** (`_mid` =
  Pine's `mid_x`), which lands in the gap the impulse leg left — clear of the candle cluster at the
  break bar (the fix for tags sitting on top of the bars); a **swing tag** anchors AT its swing bar,
  above a high / below a low. The frontend's `LABEL` nudge (~13px, ≈ chip half-height) is the pixel
  echo of Pine's newline offset, then pixel de-collision keeps dense clusters legible.
  Current-vs-historic split boundaries on the **second-to-last external break** (a leg starts at a
  BOS/SOS) — robust to the pivot-confirmation cluster that piles swings at the data's end; an empty
  "current" is honest (no internal has printed since the last break). Per-group overlay count is capped
  (`_MAX_PER_GROUP` 1200, newest kept) so a very long run can't spawn tens of thousands of overlays.
  **Existing runs need a chart refresh** to pick up structure (the `chart_spec.json` is cached).
- **Indicators are shipped, not recomputed.** `indicators.ts` registers one klinecharts indicator
  template per indicator NAME (so multiple on a pane don't collide). Its `calc` doesn't compute
  anything — `mapSeriesToCandles` looks the shipped value up by timestamp (last shipped point in
  each displayed bar's window = value as of bar close), so higher-TF display is correct and
  klinecharts re-runs calc automatically on TF switch (the indicator effect does NOT depend on
  `displayCandles`). `pane:'main'` overlays the price (`IndicatorSeries.Price`, candle pane);
  `pane:'sub'` gets its own pane. Sub-pane ids are tracked in a ref for clean removal. Colors come
  from `INDICATOR_PALETTE` (theme).
- **Daily session breaks** (`DAY_BREAK`): vlines at each interior broker-day boundary (candle
  epochs are broker wall-clock, so boundaries fall on `DAY_MS` multiples; the left edge is
  skipped). Separate overlay name from `VLINE` so the two toggle independently. Toggled from the
  on-chart Sessions legend (see above), not the header — it is a clock layer, not market structure.
- **Two header dropdowns, split by QUESTION, not by mechanism** (Aaron's call, 2026-07-27).
  **Analysis** = what the strategy DID with its signals — Trades (+ the Winners / Losers sub-filters),
  Blocked and Missed (each + one sub-filter per reason). **Structure** = what the MARKET drew — the four
  market-structure groups + the shipped indicators. **Strategies** (stacks only) is a third, and
  everything CLOCK-driven (sessions, day breaks) is the on-chart legend, not a header menu. Trades and
  Blocked used to sit in the old catch-all "Layers"; they were moved because "which trades do I want to
  interrogate" and "which market structure do I want drawn" are different questions, and mixing them
  made a long menu where the two most-used rows were buried among structure groups. Renamed
  Layers → **Structure** once day breaks left it, so the title names what is actually in it.
- **A LAYER is a row; a FILTER'S VALUES are chips** (2026-08-08). `MenuItem` is a union — a
  `MenuToggle` (dot / label / count / tick) or a `MenuChips` (a caption over a wrapped set of
  `MenuChip`s). The split is not decoration:
  - **A row is a thing the chart DRAWS.** Everything else in the menu narrows a row that is already
    on, and giving the two one shape is what let nineteen entries read as nineteen layers. The
    header's `on/total` now counts rows only, so `Analysis 4/10` describes the chart — it read
    `18/25` before, which described nothing a reader could act on.
  - **The caption is the load-bearing part, and the Missed layer is why.** Its two filters —
    score and missing-confluence — are EACH a complete partition of the same setups (measured on the
    shipped run: 35 + 417 = 452, and 179 + 238 + 21 + 10 + 4 = 452). Listed as one indented column
    of seven they read as seven sub-filters of one thing, and the counts read as double-counting.
    Naming each set is what says they are different questions.
  - **Space was the smaller win**: 862px → 741px fully expanded, MEASURED. The chips claw back the
    dense parts and give some of it back to the captions.
- ⚠ **WHEN TWO FILTERS COMPOSE, EACH ONE'S COUNTS MUST BE CONDITIONED ON THE OTHER.** With `3 of 3`
  alone the Missed layer drew 35 markers while its reason chips read 179 / 238 / 21 / 10 / 4 — the
  whole 452 — which is how it was reported from the screen. **A chip's number is a claim about what
  ticking it would change**, so conditioned on nothing it counts markers that are not on the chart.
  `missReasons` therefore counts only score-visible misses and `missScores` only reason-visible
  ones. Two consequences worth keeping:
  - **The ROSTER is built from every record and only the COUNT is filtered.** Shrinking the roster
    to the values PRESENT in the subset would delete a chip the instant its count hit zero — and a
    control that vanishes at zero is one the reader cannot use to get back. A `0` is an answer (no
    3/3 miss can be missing its FVG, because a 3/3 met all three).
  - **Both `useState`s are declared ABOVE both memos**, because each memo reads the other filter's
    set. That is the TDZ trap this folder recorded a day earlier, and `tsc` catches it here only
    because the reference is direct — the same mistake inside a closure typechecks clean.
- **All three dropdowns are ONE `ToggleMenu` component** (button with an `on/total` count + a list of
  dot/label/count/tick rows, `sub: true` indenting a filter under its parent). It owns its own open
  state and click-outside close, so adding a fourth menu is one call. Never hand-roll a fourth — three
  hand-rolled copies is exactly what this replaced, and they had already drifted (the Strategies list
  had no counts and different padding). **The same rule applied to ROWS on 2026-08-02:** the deep-debug
  presets became two new `MenuItem` fields rather than a fourth menu with its own markup — `section`
  draws a caption + rule above a row (so one menu carries the presets AND the layers they set), and
  `action` marks a row as a preset so the header's `on/total` still counts only what is DRAWN.
- **All layer toggles** use one `ToggleChip` component (colored dot + label).
- **Header + tool-strip layout (TradingView).** The header row carries the **symbol/interval**
  controls top-**LEFT** — timeframe dropdown, then Go to date, then Step, then Analysis / Structure, then the drill-down fetch status — and
  the **snapshot (Copy)** button top-**RIGHT**. The header exposes three optional slot props so a
  host can fold ITS chrome onto this SAME single row rather than stacking a second bar above it:
  `headerLeading` (far left, before TF), `headerTrailing` (far right, after Copy), and
  `headerClassName` (appended to the row — e.g. a `border-b` when it doubles as a modal title bar).
  A fourth slot, **`toolActions`, is deliberately NOT a header slot** — it renders on the vertical
  TOOL STRIP, in the bottom cluster directly above the Chart settings cog, and it is where a host
  ACTION belongs. Two reasons, the second load-bearing: `headerTrailing` is absolutely positioned
  over the price-axis COLUMN (`axisW`, ~28-70px), so anything wider than one icon overflows it; and
  **this panel's fullscreen is `position: fixed` over the whole app, so any control the host renders
  OUTSIDE the panel (its tab strip, its toolbar) vanishes the moment the chart is expanded** — which
  is when it is most likely to be wanted. The strip is INSIDE the panel, so one button covers both
  views. ⚠ **Icon-sized: the strip is 40px**, and a labelled button there would widen it on every
  chart in the app. **Rebuild chart** is the first user (2026-08-08, Aaron's placement).
  `PriceChartPanel` uses them in fullscreen to put its **instrument title (`spec.instrument`) + a
  minimize button** (`Minimize2`, the two-arrows-inward icon) on the same row as TF/menus/Copy (it no
  longer renders a separate top bar) — so everything lives on one top row.
  Inline, the slots are unset and the header is just TF/menus/Copy. Chart **tools** do NOT live in the header — they
  sit on a vertical **tool strip** (40px, `border-r`, `bg-bg-sunken`) down the far-left edge of the
  chart body, like TV's drawing toolbar. Currently Measure + Fibonacci (**icon-only** ruler /
  align-lines buttons); it's built to hold more. It runs the **FULL chart height** (default flex
  stretch, no explicit height) — all the way down past the x-axis, in its own 40px column left of the
  plot (so it never covers the x-axis labels, which start inside the canvas). **The strip is a flex
  sibling OUTSIDE the measure-capturing wrapper on purpose** — a tool button's click must not bubble
  into `handleChartClick` (that would drop a measurement anchor on the button). The chart itself is
  the flex-1 wrapper; the measurement overlay is `inset-0` of it and shares the chart's origin, so
  `pixelToChart` (which measures off `containerRef`) stays coordinate-consistent.
  **Copy aligned to the plot (`chartInset.axisW`, MEASURED).** Copy is a **borderless** flat camera
  icon; its right edge lines up flush with the y-axis (price-scale) line, not over the price scale —
  inset via the header right cluster's `paddingRight = axisW`, where `axisW` comes from klinecharts
  `chart.getSize('candle_pane', DomPosition.YAxis).width`, re-measured on init, resize (via the
  `ResizeObserver`), and each data/TF change (a new price range can change the y-axis digit width).
  (`chartInset.xAxisH` is still measured but unused now the strip is full-height.) `headerTrailing`
  (the minimize button) is
  **centred over the price-axis COLUMN** — an `absolute right-0` box of `width: axisW` with
  `justify-center` — so it sits above the price scale, not jammed in the corner, BEYOND the
  axis-aligned Copy. In fullscreen the body padding is trimmed to `pl-2 pr-2 pt-2 pb-2` (from `px-5`)
  to maximise chart space; the instrument title keeps a small `ml-1` so it isn't jammed to the edge.
  Tool-strip + Copy icons are sized ~18–20px (a touch bigger than the default 16px).
- **Copy image** (`copyChartImage` in `index.tsx`): the TradingView-style snapshot button, top-right
  of the header (see layout above). `chart.getConvertPictureUrl(true, 'png', theme.bgBase)` renders the canvas — candles plus
  every klinecharts overlay (trades, sessions, indicators, day breaks) — to a PNG data URL, which is
  copied to the clipboard via `navigator.clipboard.write([new ClipboardItem(...)])` so it pastes
  straight into a chat. The blob is passed to `ClipboardItem` as a **Promise** (keeps the user gesture
  alive on Safari). If clipboard image-write is unavailable/blocked it falls back to downloading the
  PNG (`<instrument>-<tf>.png`). The React measurement layer is a separate DOM overlay and is NOT in
  the snapshot (it's an interactive helper, not chart content).
- **Measurement tool** (`measureMode` state in `index.tsx`): its toggle button lives on the left tool strip (see layout above). TradingView-style click-to-anchor → move-to-preview → click-to-lock interaction. One measurement at a time (`measurement: LockedMeasurement | null`). The overlay div uses `pointerEvents: none` so klinecharts canvas receives all mouse events (crosshair stays live); click/mousemove handlers attach to the outer wrapper div and fire via bubbling. Label shows 2 rows: price change in points + percent (direction-colored) and bar count + duration (muted). Clicking anywhere while a measurement is locked clears it. Escape exits measure mode and clears all state.
- **Fibonacci tool** (`FIB` overlay + tool-strip button): a real, draggable, klinecharts-**native**
  drawing (not a DOM overlay like Measure), so it re-anchors on pan/zoom. The button arms
  `chart.createOverlay({ name: FIB })` → the user click-drags two swing points; on `onDrawEnd` the two
  anchor points (timestamp/value) are lifted into React state (`fibs`), which is **the source of
  truth** so a fib survives TF switches / data reloads (a `[fibs, displayCandles, pricePrecision]`
  effect re-creates them from state, mirroring the trade/session effects — `applyNewData` clears
  overlays). Each configured **level** draws a thin (`size: 0.5` → 1 physical px on retina) horizontal
  line spanning **exactly the box the user dragged** (both anchor x's — so width AND height follow the
  drag, NOT projected to the pane edge) plus a right-aligned `<ratio> (<price>)` label — decimal ratio
  + parenthesised price (e.g. `0.886 (3987.45)`), styled as the **same dark rounded chip as the trade
  level labels** (`chipBg` via `extendData`, `withAlpha` border in the level colour) so it reads over
  candles. Prices come from `overlay.points[i].value` via `yAxis.convertToPixel`, so they track the
  axis. `precision` (label decimals) is inferred from instrument magnitude in `index.tsx`.
  **Direction (fixed 2026-08-02):** the ladder anchors **1 on the FIRST click and 0 on the second** —
  `p1 + (p0 - p1) * ratio`. Drag from a swing low up to a swing high and 1 is the low, 0 the high.
  It shipped the other way round (`p0 + (p1 - p0) * ratio`, 0 on the first click), which is the whole
  ladder backwards: a retracement is read from its EXTREME (0) back toward its ORIGIN (1), and it is
  what every fib in this repo means — `mpc_strategy.pine` prices the same way (`fiboP7 = ash -
  range*0.0` = the extreme, `fiboP10 = ash - range*1.0` = the origin), so a hand-drawn fib and the
  bot's own levels now line up instead of mirroring each other.
  **Delete (gotcha):**
  klinecharts REMOVES an overlay on right-click whenever its `onRightClick` returns falsy (source:
  `_figureMouseRightClickEvent`) — which silently deleted a fib on right-click. The fix: the fib's
  `onRightClick` returns **true** (keeps it) and stashes the fib id in `ctxFibRef` for the menu.
  klinecharts fires that right-click on `mousedown` (button 2) BEFORE the DOM `contextmenu`, so the
  React menu reads a fresh `ctxFibRef`. `onSelected` also marks a fib for the **Delete/Backspace** key
  (ignored while typing); `onPressedMoveEnd` writes an anchor-drag back to state.
- **Fib LEVELS are configurable** (`fibLevels.ts` + `FibSettings.tsx`, 2026-07-28) — add, remove,
  retune, recolour or hide any level, TradingView-style. `DEFAULT_FIB_LEVELS` in `overlays.ts` is now
  only the FACTORY set (Aaron's: 0/1 neutral grey, 0.382/0.5 green, 0.618/0.702/0.786 blue, 0.886 red)
  — the starting point and the "Reset" target, not the live ladder. Editing is **live**: every
  keystroke commits and the chart redraws, which is the point of doing it on the chart.
  - **Two scopes, one component.** The gear under the fib button on the tool strip edits the tool's
    **default** ladder; a fib's own right-click menu (**"Fib levels"**, above Delete) edits **that
    drawing**. Same panel either way, so the two can't drift.
  - **A drawing FOLLOWS the default until it is customised** (`fib.levels` is an override and is
    normally absent). Retuning the default therefore retunes every un-customised fib already on
    screen — snapshotting at draw time instead would make "change my levels" appear to do nothing.
    `Use default set` drops an override; `Save as default` promotes one AND drops it, so the fib you
    saved from keeps following rather than quietly freezing.
  - **The ladder persists** (`localStorage: chartpanel_fib_levels`) — it is a setting. A fib DRAWING
    is still session-only, which is unchanged and deliberate.
  - **Ratios past 1 or below 0 draw extensions** for free: the level price is
    `p1 + (p0 - p1) * ratio`, a straight-line map that never assumed a 0–1 range. On a low→high
    drag an extension past 1 sits BELOW the low (past the origin) and one below 0 sits above the
    high — the same sides TradingView puts them on.
  - **Gotchas, both measured.** (1) The overlay picks the ladder with `Array.isArray(d.levels)`, NOT
    `.length` — an EMPTY set means the user switched every level off and must draw nothing; the old
    `.length` test would answer "delete them all" with the factory set back. (2) `FibSettings`
    re-seeds its rows in an **effect** keyed on `resetKey`. The tempting render-phase version
    (mutate a "last seen key" ref, `setRows` during render) is silently broken under **StrictMode**,
    which double-invokes render: the first, discarded invocation moves the ref, the second skips the
    seed, and **Reset does nothing at all**. That was a real bug, caught in the browser, not in review.
  - The ratio is held as a **string** while editing — a number input cannot represent `0.` or `-`,
    the states a decimal passes through as it is typed. A row that isn't yet a number sits out that
    frame and returns the moment it parses.
- **Right-click menu** (`ctxMenu` state, incl. `fibId`): the chart body's `onContextMenu` opens a
  small viewport-`fixed` menu at the cursor (clamped), TradingView-style, and is **context-split** (per
  Aaron — fibs and the chart are separate concerns): right-click **on a fib** → a fib-only menu with
  just **"Delete this fib"** (deletes that one; no reset, no bulk-remove — clean up one at a time);
  right-click **on empty chart** → a chart-only menu with **"Reset chart view"** (restores the
  zoom/scroll — `setBarSpace` / `setOffsetRightDistance` / `scrollToRealTime` — captured into refs at
  init) and **Show/Hide trades**. The menu closes on Escape or any outside mousedown (it
  `stopPropagation`s its own mousedown so a click on an item isn't swallowed).
- **Decision (2026-06-14):** no per-trade trade table exists on the backtest page yet (trades
  are collapsed into `equity_curve` points — no per-trade entry/exit). Per Aaron, the clickable
  trade list + row→zoom is **deferred to Step 7**, when the real spec emitter provides per-trade
  data. Step 4 ships the chart overlay + toggle only.
- **Lifecycle.** Chart is `init()`-ed once on mount and `dispose()`-ed on unmount; a
  `ResizeObserver` calls `chart.resize()`. Data is (re)applied in a `spec`-keyed effect so the
  spec can change without re-initialising.

---

## Status

All build steps complete (1–6, 7a, 7b, 8). The panel renders real per-run specs end-to-end:
candles, timeframe switch, sessions, trades, generic structure overlays (box/hline/vline),
shipped indicators (EMA main-pane / ATR sub-pane), daily breaks, the TradingView-style measurement
tool, a draggable Fibonacci tool (Aaron's levels/colours, price labels), and a right-click menu
(Reset chart view / remove fibs). Backend emitter is `services/chart_spec.py`. Build history is in git.
ly menu with
  just **"Delete this fib"** (deletes that one; no reset, no bulk-remove — clean up one at a time);
  right-click **on empty chart** → a chart-only menu with **"Reset chart view"** (restores the
  zoom/scroll — `setBarSpace` / `setOffsetRightDistance` / `scrollToRealTime` — captured into refs at
  init) and **Show/Hide trades**. The menu closes on Escape or any outside mousedown (it
  `stopPropagation`s its own mousedown so a click on an item isn't swallowed).
- **Decision (2026-06-14):** no per-trade trade table exists on the backtest page yet (trades
  are collapsed into `equity_curve` points — no per-trade entry/exit). Per Aaron, the clickable
  trade list + row→zoom is **deferred to Step 7**, when the real spec emitter provides per-trade
  data. Step 4 ships the chart overlay + toggle only.
- **Lifecycle.** Chart is `init()`-ed once on mount and `dispose()`-ed on unmount; a
  `ResizeObserver` calls `chart.resize()`. Data is (re)applied in a `spec`-keyed effect so the
  spec can change without re-initialising.

---

## The pinned readout follows the WINDOW, and carries no date (2026-08-23)

🔴 **THE READOUT ACROSS THE TOP DESCRIBED A BAR THAT WAS NOT ON SCREEN, AND THE DATE IT PRINTED
WAS READ AS THE DATE OF THE TRADE BELOW IT.** With the readout pinned on and the pointer off the
chart, klinecharts falls back to `dataList[dataList.length - 1]` — the newest bar in the loaded
run, wherever you have scrolled to. On a chart parked on August 2025 around 3,330 it printed
`2026-08-21 15:45 … 4,603.31`, and the year on it was taken for the year of the trade on screen.
**Nothing was wrong with the data. The chart was showing two different moments at once with no
sign that it was doing it** — the same failure shape as a probe whose negative answer a healthy
system also produces. TradingView does not do this: its legend follows the visible window and
carries no timestamp at all.

Three rules, all TradingView's, and the third is the one nobody asks for until they hit it:

1. **The readout names the RIGHT-MOST VISIBLE bar** — never the end of the dataset. While the
   pointer is on a bar the crosshair's bar wins, because that is the bar being asked about.
2. **No date in it.** The date lives in exactly one place, the crosshair's own tag on the time
   axis, so a date you can see is always the bar you are pointing at.
3. **The current-price line goes quiet when its bar is off screen.** Left on, klinecharts clamps
   it to the top of the scale, where a bright line and a price tag read as a level in the market
   you are looking at. It is not one.

🔴 **THERE IS DELIBERATELY NO "IS THE POINTER ON THE CHART" FLAG, AND THE FIRST VERSION HAD ONE
AND WAS WRONG.** klinecharts clears its crosshair through more than one path and at least one of
them updates it without firing the change action, so a flag fed by that action sticks at
*hovering* — and the readout goes on naming the newest bar, i.e. **the defect surviving its own
fix**. MEASURED in a real browser: after the pointer left the chart the action never fired again.
**`resolveTipBar` needs no such flag**: the library hands us the crosshair's bar while the pointer
is on one and the LAST bar when it is not, so the only ambiguous case is the last bar itself — and
if that bar is on screen it IS the right-most visible bar, so both readings agree. Substitute only
when the last bar is off screen and it is the bar we were handed.

⚠ **Both readings format through ONE branch** (`makeCandleTooltip`, `chartStyles.ts`), so the
hovered and the pinned readout cannot drift into disagreeing about how a price is written — which
is why the `{open}`-style templates are not used for the hover path even though they work there.
⚠ **The price-line toggle is guarded on CHANGE**: `setStyles` redraws the whole chart and the
visible-range action runs on every frame of a drag.
⚠ **The edge bar is read off `chart.getDataList()`, not `displayCandles`** — the indices are
klinecharts' own, and the two lists differ for a frame during a page.
⚠ **`to` is EXCLUSIVE and already clamped**, so the right-most bar is `to - 1` and "the newest bar
is on screen" is `to >= length`.

⚠ **No automated check.** The readout is canvas-drawn with no DOM, so what was done instead was
driving the real page: hover a bar mid-chart, scroll back, take the pointer off, and read the
numbers off the screenshot against the candles under them. **Re-do that by hand after touching
either file** — a unit test here would be asserting on the resolver, which is not the half that
broke.

---

## Status

All build steps complete (1–6, 7a, 7b, 8). The panel renders real per-run specs end-to-end:
candles, timeframe switch, sessions, trades, generic structure overlays (box/hline/vline),
shipped indicators (EMA main-pane / ATR sub-pane), daily breaks, the TradingView-style measurement
tool, a draggable Fibonacci tool (Aaron's levels/colours, price labels), and a right-click menu
(Reset chart view / remove fibs). Backend emitter is `services/chart_spec.py`. Build history is in git.
