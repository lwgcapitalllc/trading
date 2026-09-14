# CLAUDE.md — ChartPanel (backtest candlestick panel)

**Purpose:** A strategy-agnostic candlestick chart for the backtest page, built on klinecharts v9. It renders whatever a `ChartSpec` declares and contains **zero** strategy-specific logic.
**Scope:** This folder only. The host page is `pages/BacktestDetail.tsx`.
**Status:** Live — all build steps done. Renders real runs end-to-end: candles, sessions, trades, strategy-structure overlays, the ATR indicator, and the measurement tool.



🔴 **A drill-down's only sign of life was an 11px grey line in the header.** The fetch is a real round trip — **MEASURED at ~4.5s per 12,000-bar window on a warm cache, cold or warm** — and the panel deliberately keeps the previous timeframe's candles on screen throughout, so the loading state and the doing-nothing state were pixel-identical. There is a badge over the plot now, plus a spinner on the timeframe button, and **it names BOTH timeframes** (`loading M1 bars — showing M15 meanwhile`), because bars that do not match the button are a silent lie about what is on screen. The same badge carries the failure, in warn, for the same reason.


✅ **`tests/chart-drilldown.spec.ts` — 4 checks, and EVERY ONE PROVEN BY MUTATION** (a fail-watch against HEAD is impossible for the parts already fixed in the commit below): reverting the anchor, deleting the badge, restoring the hedged message and removing BOTH position fixes each turn exactly the naming check red. ⚠ Offline since 2026-09-11: the fetches are answered from RECORDED backend windows cut to each request, so what is under test is still where the chart LANDS after a real answer. The refusal is mocked, with the exact payload measured off the live backend.

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
`sos_fade_strategy.pine` prices its levels off the same convention (`fiboP7 = ash - range*0.0` is the
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
Analysis dropdown rather than Structure. ⚠ The gaps are the INDICATOR's (`mpc_jarvis.pine`), which
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
├── tradeGeometry.ts   the trade box's two PRICE rules (adverse floor, exit marker) — pure, tested
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

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 151 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/conventions.md` — How the panel is built — every convention and decision

**Read before touching:** any chart panel component, an overlay group, the klinecharts wiring, or the chart's data contract.

- Conventions

### `notes/trade-box-and-readout.md` — Trade box geometry and the pinned readout

**Read before touching:** the trade box, its adverse band, the exit marker, or the pinned readout.

- `Deepest` → `DD`, `Furthest` → `Best` (2026-08-21)
- 🔴 Nothing adverse is drawn past the stop on a trade the stop closed (2026-08-22)
- 🔴 The adverse band ends where price WENT, and every trade draws its exit (2026-08-25)
- The pinned readout follows the WINDOW, and carries no date (2026-08-23)

### `notes/status.md` — Status

**Read before touching:** checking the panel's state of play rather than a rule.

- Status
- Status @2
