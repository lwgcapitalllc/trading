# CLAUDE.md — Command Center Frontend

**Purpose:** React + Vite + TypeScript app (`:5173`) — the UI for the command center; all server state via TanStack Query against the FastAPI backend.
**Scope:** This covers frontend hook/component/page conventions, the theme system, and routing. It does NOT cover the backend (see `../backend/CLAUDE.md`) or `algos/`/`smart-money/`.
**Status:** Live — all pages shipped (Overview, Bots, Strategies, Rulesets, Backtests lab, Optimizations, Tuning workbench, Stress Tests, Settings). **Smart Money is built and flagged OFF** since 2026-08-04 — see *Feature flags*.
**Last reviewed:** 2026-08-05 — 🔴 **THE TUNING WORKBENCH WAS RUNNING EVERY ITERATION ON A FREE BOOK AND PUTTING THE RESULT IN A TABLE BESIDE A CHARGED BASELINE.** Aaron asked for an audit of the page, then for the fixes. **`runIteration` sent `commission_per_side` and `slippage_ticks` and nothing else** — no `cost_layers`, no `broker_profile`, no `sizing_mode` — so tuning a run that charged spread and swap produced a child measured under different physics from its own parent, and the Δ column attributed the whole gap to the param you moved. Retry has carried those fields deliberately since the day they existed; this was the one run-launching path in the app that did not. ✅ **PROVEN BY RUNNING IT, not by reading the diff — three real python backtests against the live backend on cached XAUUSD M15 (2024).** A charged baseline (spread + swap, `vantage_demo`) was built, then the SAME iteration (`exec_tp1_pct` 0→40) was fired twice: once with the body this page now sends and once with the body it used to. **PF 1.499 vs 1.581, P&L $3,157.33 vs $3,646.75 — and trade counts IDENTICAL at 17**, which is the check that says the charge is real and correctly placed, since spread and swap change what a trade MAKES and never whether it happens. The old page would have shown that $489 as the param's doing. All three probe runs deleted afterwards; the lab is back at the 10 rows it started with. 🔴 **"Ranked by profit factor" was a caption over a table sorted newest-first** — a label claiming something no code did, this repo's most-repeated defect, sitting on the one page whose entire job is ranking. It ranks now. 🔴 **The ★ could be won on any trade count at all**, so a fluke with three trades outranked the real winner; it needs 10 trades and the caption SAYS so, because a threshold nobody can see is indistinguishable from a bug when the obvious winner has no star. 🔴 **Max DD was listed in dollars only** — the exact defect the Runs list had fixed on 2026-08-01, in a second table, where $1.7M beside $14M of profit reads as ~12% against a true 55.9%. Percent leads now, dollars beneath. 🔴 **Tuning an iteration hid it**: the page listed DIRECT children only, so a grandchild vanished from the only page that compares it — and the same filter was letting SWEEP and OPTIMIZER children in as "tweaks", since `source_run_id` is stamped by all three. Descendants are walked transitively, sweeps and optimizations excluded by their own ids. ⚠ **Two fixes are about a page that changes under the reader rather than about a wrong number.** The palette was handed out in TABLE order, so every line on the chart swapped colour whenever a run finished and re-sorted the leaderboard — it is CREATION order now, and a colour once given is that run's for good. And edits are held in `sessionStorage` per baseline, so clicking a row to inspect it no longer throws away what you typed: **persistence rather than a navigation-guard dialog, because nothing is lost means there is nothing to warn about.** ⚠ **The changed-count on the Run button and the params in the request are filtered through ONE set of known keys**, so the button can never promise a change the request then drops. ⚠ **`cost_layers: null` on a baseline is NOT forwarded as `null`** — it means "made before layered costs existed", which is not a contract a NEW run can be created under; `[]` is its honest equivalent and charges the same nothing. **Payload: 137 KB → 49 KB per iteration** (`?timeline=false`, measured), because `regime_timeline` is 96 KB of that and is the same calendar for every run in the window — the chart bands off exactly one copy. ⚠ **It is only slimmed when the BASELINE actually carries a timeline, and it is cached under its own key**, never `['lab','run',id]`, which belongs to the run page. ⚠ **One audit finding was WRONG and is recorded as wrong: `copyChartAsPng` already toasts on every failure path**, so there was nothing to add — the call site ignoring its boolean is not a silent failure. Also: a loading chart no longer says "no completed runs", the fullscreen chart's height is measured with a `ResizeObserver` instead of a one-shot `window.innerHeight` read, the inline chart unmounts while fullscreen is open, the baseline's dot renderers are memoised (a keystroke in the param editor was repainting 165 markers), Reset is enabled whenever an edit is HELD rather than only when one differs, a Stop button sits on the running banner, iterations are named by what they CHANGED instead of `Tweak 15f0122a`, Sharpe / worthiness / Win% and Trades deltas are shown, and the regime bands finally have a key. ✅ **8 new browser checks (`tests/tuning.spec.ts`), and they were WATCHED TO FAIL first — all 8 red against the page at `HEAD`, all 8 green against the fix.** A suite written after a fix and never run against the defect is a description of the fix, not a test of it. 4 new backend tests, 506 backend green, frontend typechecks and builds. **The standing lesson is the Optimizations one arriving from one page over: this feature had been BUILT and never DRIVEN END TO END — and the giveaway is that the two worst defects were both invisible unless you compared a child to its own parent, which is the only thing this page is for.** Earlier the same day: 🔴 **THE OVERVIEW — THE PAGE YOU OPEN TO ASK "IS ANYTHING WRONG" — HAD ELEVEN DEFECTS AND NOT ONE OF THEM SHOWED AN ERROR.** Every single one rendered a confident, healthy-looking answer, which on this page is the whole failure. **Two of the three scheduled jobs on the live box are DISABLED and all three wore the gold "waiting for next trigger" pill** — the Bots page had handled that for months, with a comment saying a gold dot on a dead task is worse than no dot, and this page did exactly what that comment forbids. **A bot RUNNING with a dead terminal link read `1 / 1 · all bots live` in green** (the 2026-08-04 blind-bot incident, on the page a reader checks first). **`balance ?? 0` counted "could not tell me" as a real zero** in the fleet total. **A failed refetch drew the error banner over the last good rows, undated.** **The calendar window was `useMemo(…, [])`, so a dashboard left open past Sunday midnight asked for LAST week for ever** — proved with a faked clock, and the same test against the old code stays pinned, which is what makes it a test. **`server_now_ms` was read straight from the response, so "now" froze between polls.** Plus: a calendar error rendering as "Loading…" for ever, `0 / 0` bots reading "all bots live", a best-PF ranking with no sample floor, a running backtest announcing itself nowhere, an empty event grid, a DST-wrong week end, and rows keyed by name instead of key. ⚠ **The correction worth keeping is one I had to make to my own audit: the Overview does NOT pay for the runs/optimizations/stress-test polling — `Sidebar.tsx` is always mounted and already holds those cache entries.** Guessing at a cost is the same error as guessing at a number. **25 browser checks green** against mocked blind/empty/dead-VPS/dead-feed fleets. Full detail in *The Overview was audited 2026-08-05*. Earlier the same day: 🔴 **THREE HOOKS NOBODY RENDERED, AND TWO OF THEM RESTARTED A LIVE TRADING BOT.** The Bots audit found `useBotConfig` / `useSaveBotConfig` / `useSaveBotCaps` with **zero consumers** — and the endpoints behind them were not inert: `PATCH /{bot}/config` wrote arbitrary config sections including strategy params, going around the backend's runtime-editable allowlist, then committed, pushed, pulled and **restarted the bot**; `PATCH /{bot}/caps` did the same restart to write a threshold file for a disabled job. All three are deleted here and in the backend (`git show 407d716^`), along with the `BotConfigSections` / `BotConfigUpdate` types. `useBotParams` reads and `useSaveBotRuntime` writes the one lever that may move — **and that one does not restart the bot.** ⚠ **The lesson is about where dead frontend code is dangerous: a hook with no consumer is normally just clutter, but a hook is a claim that an endpoint is a supported thing to call, and here the endpoint's blast radius was a live position.** Deleting the hook without deleting the endpoint would have left the hazard and removed the only trace of it. Same pass, the **Users tab** now says WHICH row is saving. ⚠ **The global disable stays, and that was the finding** — it looked like an ergonomics bug (removing one user greys out every role select) and it is actually load-bearing: every one of those endpoints rewrites the WHOLE `users.json`, so two in flight means the second one's read can predate the first one's write and silently undo it. The backend now holds a lock across its own read-modify-write; the fix HERE is legibility, not concurrency — the acting row tints and says `Saving…`, so a table of greyed-out controls reads as *waiting for that one* instead of *everything broke*. **Do not "fix" the remaining rows to stay enabled.** ✅ **Third change, and it is the one that matters for bot #2: nothing on this page addresses a bot by its DISPLAY NAME any more.** `BotStatus.key` is the stable identifier — the same string on the VPS process commandline — and the `?bot=` URL param, the rail selection, `expandedBot`, `logBot`, `confirmStopBot`, the pending-row marker and every API path now key off it. ⚠ **A name is a label chosen for a human, so it is the field that eventually changes, and `?bot=MPC%20SOS%20Fade` is a bookmark that dies the day somebody renames the bot — silently, because the fallback is `bots[0]`, i.e. a DIFFERENT bot's promote button with the URL still naming the one you wanted.** ⚠ **Key and label are separate PROPS wherever both are needed** (`DeployCard`, `RuntimeEditor`, `LogModal`), and user-facing copy goes through a `labelOf(key)` lookup — a control that ACTS on a name acts on nothing the day it changes, and a dialog that shows a key is unreadable. ✅ **Verified in a real browser on a mocked 4-bot fleet including a LIVE one**: `?bot=orb_live` in the URL, **1 promote button with 4 bots registered**, the panel reads *ORB* and never leaks `orb_live`, a key deep-link survives a reload and a Monitor round trip, and stopping the live row shows **"Stop ORB?"** while calling **`orb_live/stop`**. No console errors. Frontend typechecks and builds. Earlier the same day: **SMART MONEY IS BEHIND A FEATURE FLAG AND OFF.** Aaron is auditing the command center down to what he uses, and this is not on the list for a while. `src/lib/features.ts` is the switch; **the rule is that a flag hides an AREA, not a component** — its nav row, its route and every card that summarises it move together, because hiding only the nav leaves a page reachable by URL (which is not "removed") and hiding only the route leaves a row that goes nowhere. ⚠ **Hidden means NOT FETCHED**: `useRunProgress` polls every 30s forever, so a card that is merely unrendered goes on costing a request twice a minute for something nobody can see — both hooks took an `enabled` param and the Overview now issues **0** `/smart-money` requests, measured in a real browser. ⚠ **A grid's column count has to follow what is actually rendered** — two cards left in a `grid-cols-4` row is half a row of blank space, which reads as data that failed to load, so both Overview grids pick their columns off the flag. ⚠ **`FEATURES` is typed `Record<…, boolean>` and deliberately not `as const`** — literal types narrow every `FEATURES.x && <Card/>` to `false` and TypeScript then reports the switched-off branch as dead code to delete, which is precisely what a flag exists to prevent. Nothing is deleted: pages, hooks, types, the backend router and the `smart-money/` pipeline are untouched, so one boolean restores it. **Rendering it found the one real defect: an unmatched route drew NOTHING** — a blank main area beside a working sidebar — so a stale `/smart-money` bookmark looked like the app breaking; `App.tsx` gained a `path="*"` redirect to Overview. Verified at 1670×940. Full rules in *Feature flags*. Earlier the same day: **THE BOTS PAGE'S CONFIGURE TAB IS A BOT SELECTOR NOW, AND THE POINT IS NOT THAT IT LOOKS TIDIER.** Aaron's ask: it was a flat vertical stack — a full screen per bot, risk editor + Account + Deployed version + a 53-row parameter accordion, with no selector — which is correct for one bot and does not scale to configuring and promoting several. It is a **left rail + detail panel** with a **fleet version strip** above it (closes 2 of G11's 3 bullets; Monitor's global-vs-per-bot controls are the third and are still open). ✅ **The property that earns it is measured, not argued: only the SELECTED bot's controls exist in the DOM.** Driven in a real browser against a mocked 4-bot fleet, `getByRole('button', {name: /promote/i})` counts **1** where the flat stack would render 4 — a Promote button for a bot you did not pick is not there to be hit, which no amount of spacing, ordering or confirmation copy can buy. ⚠ **The fleet strip and the per-bot card must never be two readings of one fact** — they share ONE derivation (`versionFlags`) and ONE TanStack cache entry per bot (`useBotVersions` reuses `useBotVersion`'s key), because a strip saying *all deployments clean* over a card warning *restart pending* is worse than no strip; it also therefore costs no extra fetch, since the flat stack was already reading every bot's version to render every card. ⚠ **An unreadable deployment record counts as `unreadable`, never as clean** — the same *no data ≠ cannot ask* rule the `No MT5 link` chip below exists for, and the strip has to state it or absence reads as health. ⚠ **The detail header is deliberately NOT sticky and the RAIL is:** "which bot am I editing" has to survive scrolling past 53 params, and the rail IS the selector, so its highlighted row cannot disagree with itself — a second sticky header is a second answer to one question. It also landed straight in **the 22px trap this file already records**: `<main>` is a padded scroller, so `top-0` pins 22px LOW and the params card header scrolled up through the transparent strip it left. **That is the standing lesson and it is a small one: this file had the trap written down, the code still hit it, and a screenshot found it in one look where reading the diff had not.** Render the thing. Selection lives in `?bot=` (so a refresh cannot move you to another bot's promote button) and the page's `setTab` MERGES the query string instead of rebuilding it, or leaving the tab would drop the selection. Both confirm dialogs now NAME the bot — with a selector above them the bot is a choice made a scroll ago and no longer on screen. Frontend typechecks and builds. Earlier the same day: 🔴 **AN EM-DASH IN THE BOTS PAGE'S BALANCE COLUMN WAS THE ONLY THING IN THE WHOLE SYSTEM REPORTING A BOT THAT HAD BEEN BLIND FOR 50 MINUTES.** MetaTrader auto-updated itself on the VPS and restarted, taking the running bot's terminal connection with it. The bot stayed alive and kept stamping its heartbeat, so the watchdog saw a healthy bot, the process list still had it, and this row said **RUNNING** — while it received no bars at all across an open session. `BotStatus.mt5_link` now carries the answer and Monitor renders a **`No MT5 link`** chip. ⚠ **The chip sits BESIDE the Running pill rather than replacing it**, because both are true simultaneously and they are different questions: the process is ALIVE (so a restart is the fix, and the watchdog was right not to fire) and it is BLIND (so it is trading nothing) — collapsing them into one word loses whichever half the reader came for. ⚠ **`=== false`, never falsy** — the same rule the sidebar's `mt5_connected` follows, in this same file: `null` means the bot has not stamped a link state, and painting a healthy bot as disconnected is the identical mistake in reverse. ⚠ **The balance cell says `no link` in `warn` rather than an em-dash**, so the two causes of a missing number cannot look the same again, and the tooltip names the next action because the runner self-heals. Full detail in *A blank cell is not a diagnosis*. Same pass, this file's Bots row was corrected — it claimed "no bots registered yet" while one had been live since 2026-07-31 — and now names `DeployCard` (deployed hash / commit / params, with a previewing Promote button) and the G11 caveat that Configure is a flat per-bot stack with no selector. **The standing lesson is NOT this folder's usual label-vs-code refrain: every layer beneath that cell behaved defensibly on its own** — an empty bar frame is a fine thing for a data call to return, a null balance a fine thing to write when you have none — **and the defect was that "no data" and "cannot ask" were the SAME VALUE at every hop**, so by the time it reached the browser the distinction did not exist to render. When a cell can be empty for two reasons, the API has to say which. Earlier: 2026-08-03 — 🔴 **the Costs pill and the Net hero were reporting different quantities under names that let a reader treat them as one.** Turning spread + swap on for run `75ccc776d10c` drops Net by **$18,200,741** while the pill read `Charging $332,371`; both are correct — the first is the balance impact, the second the fees actually paid — and the page showed neither the relationship nor the reason (**98.2% of that gap is lost compounding**, demonstrated by re-walking the same trades and fees at 1% risk instead of 10%, where the gap falls from 64.5% to 11.0%). Worse, the footer captioned the fees `after compounding`, the one description that does not fit them. **The headline is now R** (`Charging 12.08R`): a pill holds one number, and R is the only one that cannot contradict the page, is what the `CostRule` rows above sum to, and is comparable between runs. The popover names all three through a new `Figure` row — **Charged / Fees charged / Net before → after** — plus the ratio in words. `useCostFilter` returns `netBefore`/`netAfter`/`balanceImpact` **summed off the same rows `buildFilteredRun` sums**, so the pill and the card cannot drift, and the `Costs charged` KPI row became **`Fees charged`** because the old name invited exactly the subtraction that makes the two look contradictory. Full detail in *Costs are switchable in TWO places*. **The standing lesson is a new one and it is not this folder's usual label-vs-code refrain: every number here was correct and every label defensible on its own, and the page still misled — because two true figures of different KINDS shared a footer and the reader was left to subtract. A control that changes a headline has to state what it CHARGED and what it MOVED, under names that cannot be swapped.** Earlier the same day: **the Price tab opens instantly, because the run page now builds it in the background on arrival.** Aaron's ask: land on a backtest, and by the time you click Price it should already be there. **MEASURED on run `432aff31f374` (32,978 M15 candles): 2,453 ms from click to a painted chart → 167 ms.** ✅ **The finding worth carrying is that the wait was THREE costs, and the obvious two were the small ones.** A ~3.5 MB `ChartSpec` fetch (0.39 s served from the run dir's cache, **7.6 s on a cold build**, plus the browser's parse), the lazy klinecharts chunk, and — the bulk of it — **klinecharts laying 33k candles and their overlays out on MOUNT**. Prefetching the spec and preloading the chunk together bought only 2,453 → 1,964 ms; the remaining ~1.8 s could not be prefetched at all, because **a build cost is only payable by mounting the thing.** So `ChartTabPanel` gained `keepMounted`, and the Price tab now stays mounted while another tab shows. ⚠ **The hidden tab is `visibility: hidden` + `position: absolute`, deliberately NOT `display: none`** — a display-none container measures 0 wide, so klinecharts would size its canvas to nothing and need a resize on reveal, which is the swap this change exists to remove. `visibility` keeps the real WIDTH (verified: canvas 1033 px before and after the reveal, one instance throughout — 2 canvases, never 4) while contributing no height, and it also takes the panel out of the tab order and the accessibility tree. ⚠ **The warm mount is DEFERRED to an idle beat (floor 1.2 s), not done on mount** — klinecharts blocks the main thread while it lays out, and the equity curve is what the reader is actually waiting for on arrival. ⚠ **The prefetch is `prefetchQuery`, never a page-level `useChartSpec`** — same cache entry, but without subscribing the whole page to a multi-megabyte object it never renders; it also swallows its own errors, so a failed prefetch stays invisible and the panel reports the real error on mount. ⚠ **The cost is real and is the trade Aaron asked for: a run page now always fetches the spec and builds the chart, even if the reader never opens the Price tab.** `StackDetail` and `StressTestDetail` pass no `keepMounted` and are untouched. Verified in a real browser: hide → reveal cycle 76 ms, fullscreen resizes 1033 → 1555 and back, no console errors, and the equity tab's layout is byte-for-byte what it was. Earlier the same day: **the price chart draws ORDER BLOCKS** (Analysis → Order Blocks, default OFF), the supply/demand zones that were live when a trade fired, refused or died. **The frontend interest is entirely in what it did NOT need:** no new overlay template, no new render effect, no new concept — one string appended to `ANALYSIS_GROUPS` in `overlays.ts`, a colour beside it, and the generic `box` pipeline drew, clipped, counted and toggled the layer. That is the second entry in a list built for exactly this when the gap layer landed, and it is the shape to reach for before writing a template. ⚠ **It is deliberately NOT in Deep debug** (Aaron's call) — `DEBUG_ON_GROUPS` reads `ANALYSIS_GROUPS[0]`, so a new analysis layer goes on the END of that list and joins the preset only when someone decides it belongs in the every-trade reading. ⚠ **The one change to shared code is `BoxOverlay.label` / `labelAlign`**: an order block carries mpc's `OB` tag right-aligned, because a zone's LEFT edge is its anchor candle and a tag there sits on price. **And exercising that path for the first time found a live bug in it.** The generic `BOX` label figure had never been used by any emitter and shipped carrying klinecharts' default overlay-text style — a solid BLUE chip — so the first `OB` tag rendered as a blue pill; the `HLINE` label path carried the identical bug, still dormant. This folder's own CLAUDE.md had recorded the trap for the `LABEL` template and it applied to both, unnoticed, for months. All three now spread one `FLAT_TEXT` constant. **The standing lesson: a generic mechanism nobody has exercised is not a working mechanism — it is untested code wearing a general-purpose name, and the first real user is its first test.** Verified in a real browser on run `432aff31f374`, Order Blocks and Fair Value Gaps drawn together. Earlier: 2026-08-02 — **the price chart's Analysis menu grew a Deep debug toggle** — one row that switches the context you want behind any trade you are interrogating (Fibs, External Structure, Fair Value Gaps), so reading a run one trade at a time stops being three switches across two dropdowns set and unset constantly. **The transferable part is how many shapes it took in one day before it was right:** a segmented `Winners | Losers` pill beside the menus, then a four-way `Winners / Losers / Both / Off` radio inside Analysis, then one additive on/off row. Both earlier shapes OWNED THE OUTCOME FILTER, and that is exactly what was wrong with them — they asked "winners, losers or both" in a second place that could disagree with the rows below, and they forced the unanswerable "what does OFF restore?" (the first build shipped with no way out at all). **Additive has neither problem: it never decides which trades are drawn, so the filter keeps one home, off means off, and Step re-scopes off the same rows it always did.** On/off is DERIVED from the layers themselves, so unticking one by hand unticks the row — a remembered flag is how a label starts claiming something the chart is not doing. ⚠ **The write is unconditional but the READ is not:** setting a layer the run never emitted is inert, while a read over layers that cannot exist is vacuously TRUE and would pin the row ON for ever, so `debugAvailable` hides it on a run with nothing to deepen. It reuses the shared `ToggleMenu` rather than becoming a fourth hand-rolled dropdown, which cost two new `MenuItem` fields — `section` (caption + rule) and `action` (a shortcut row, kept OUT of the header's `on/total`, which must go on describing what is drawn). Verified in-browser on run `211384ddbea4`, including that Winners/Losers and Step are untouched by it. Detail in `ChartPanel/CLAUDE.md` → *Debug*. Earlier: 🔴 **the price chart emptied itself when you scrolled back past the shipped candles, and every toggle went on claiming otherwise.** Structure, Fair Value Gaps, Blocked and Missed are all emitted PER-WINDOW by the backend, while the panel pages bars back to the run's start — so past that boundary the layers drew nothing with their switches still ON, which reads as the panel forgetting the settings. A page now fetches its own analysis and the panel merges it (`ChartPanel/CLAUDE.md` → *Paging older history*). **The frontend half generalises past this chart: a roster DERIVED from data must be RECONCILED, never re-seeded.** `groupsOn` was rebuilt from `overlayGroups` on every change, which was safe only because that list never changed; the moment a page could rebuild it, `setGroupsOn(defaults)` would have switched the reader's layers off mid-scroll — the same bug from the other side. `reconcileToggles` keeps an answer already given and defaults only genuinely new keys; the miss-noise seed follows the same rule, seeding each label once so a reason ticked back on is never re-hidden. Verified in-browser on run `211384ddbea4` at 2024-05→06, nine months before the shipped window: BOS/SOS lines, HH/HL/LH/LL tags, gap boxes and pink Blocked markers all draw with Winners still filtered off — bare candles before. Earlier: 🔴 **two sidebar dots were rendering their field faithfully and the field was measuring the wrong thing.** The **SSH** dot's `ssh_tunnel` came from a fresh `ssh forexvps "echo ok"`, which has nothing to do with the port forwards, so after a laptop sleep it sat green beside two red agent dots and pointed at the VPS instead of at the dead tunnel on this laptop; the **MT5 Agent** dot read the Flask agent's `/health`, which answers `ok` whether or not the terminal is logged in, so a disconnected MT5_Lab showed green while every python run needing uncached bars failed at fetch time. Both are three-state now — SSH: green forwards up / **yellow tunnel down but VPS reachable** (the backend supervisor rebuilds it, so yellow means *wait*) / red VPS unreachable; MT5: green agent+terminal / **yellow agent up, terminal not connected** (needs RDP) / red agent down. ⚠ **`mt5_connected` is `boolean | null` and every check is `=== false`, never falsy** — `null` means the agent could not be asked, and rendering an unanswered question as a failure invents a measurement (the same rule `DrawdownMeter` follows for an unmeasured tail). Detail in *Two dots that were not measuring what they said*. Earlier: 2026-08-01 — **the News & Holiday filter now defaults to OFF on both rules, so a run page opens on the run exactly as traded.** Holidays had defaulted ON and news followed the strategy's `avoid_news`, which meant the headline figure on screen was not the backtest's own result — and, worse, the default DIFFERED BETWEEN STRATEGIES, so two runs over the same window could open on different trade counts with nothing on screen explaining why. Turning a rule on is a deliberate what-if now. `useNewsFilter` no longer takes `avoidNews`. Same day: **`FitMoney` never abbreviates again** — the *Made* hero shows `+$14,387,475`, not `$14.4M`. That was not a style choice but a measurement bug with a plausible-looking output: it compared the text against ITS OWN span, which is a content-sized flex item whose width IS the text's width, so "does it fit" was true by exactly `FIT_SLACK` on every value forever. It measures the hero ROW now (`data-fit-box`) and shrinks the TYPE rather than abbreviating; `dollarShort` is deleted. **The repo had already recorded this trap for `PanelRow` values and it applied to the hero too** — reason enough to check every remaining content-sized measurement. Same day: **the *Made* hero is the DOLLARS, with `from $10,000` under it** — the multiple (`1439.7x`) was the hero and the starting balance appeared NOWHERE on the page, so it was a multiple of a number the reader could not see; it is the first row now. A **`Costs charged`** row landed with it (shown only on a priced run — `$0` everywhere would read as "trading is free"), plus a **`Won / scratched / lost`** row beside the win rate and a **`Top 5 trades`** row beside profit concentration, both because the numbers above them were TRUE and were being misread. Detail in `## Backtest detail — chart and KPI conventions`. Earlier: **the price chart got a Step navigator: `◀ Loss 12/60 ▶` walks the markers, previous / next, centred.** Reading a run's losers back to back was a scroll hunt across years of bars; it is now two clicks or ← / → with the pointer over the panel, and a step into unloaded history pages the bars in through the SAME `goToDate` the date pill drives. **The design decision to keep: it has no set of its own — it walks whatever the Analysis dropdown is SHOWING.** Untick Winners and ◀ walks the losers; turn Trades off with Blocked on and it walks the refusals; leave both on and it interleaves them by time. Giving it its own filters would give the navigator and the chart a way to disagree, and would let it step to something that isn't drawn. Verified on run `0e3983a0c3c7`: 164 markers → 104 / 60, then 138 with Blocked added, stepping Loss → Blocked → Loss with the park surviving the filter change. Detail in `ChartPanel/CLAUDE.md` → *Step*. Earlier the same day: **the price chart draws fair value gaps, and the panel grew one new concept to hold them: `ANALYSIS_GROUPS`.** The backend emits a gap only where it was live at a trade / blocked / missed setup, tagged into a `Fair Value Gaps` overlay group. The panel needed **no new overlay template and no new render effect** — it is a plain `box` group, so the generic pipeline already draws, clips and toggles it. The only addition is the list in `overlays.ts` naming which overlay groups belong in the **Analysis** dropdown rather than Structure: one roster still backs `groupsOn`, only the MENU each row appears in differs (`structureGroups` / `analysisGroups`). Default OFF with its box count, like Blocked and Missed, and last in the menu because it is the CONTEXT around those three rows, not a fourth kind of signal. Adding a second analysis layer is one string. Detail — including why the drawn gaps are the INDICATOR's and not the bot's — in `ChartPanel/CLAUDE.md`. Earlier: 2026-07-31 — **the frontend had two private copies of Sharpe and neither zero-filled flat days, so every number they produced was inflated ~3x.** The backend has always zero-filled every weekday in the span (`metrics.zero_filled_daily_values`); `computeFallbacks` and `StackDetail.composeCombined` each scored only the days that CLOSED a trade, then annualized by √252 — 142 active days in a 1,447-weekday span read **2.96 against a true 0.91**, and a stack read **13.06**. It surfaced as a news-filter delta of +2.07 from removing 3 of 142 trades, which is the tell: the filtered side fell back to the frontend formula while the unfiltered side used the stored backend one, so the "delta" was two formulas, not a change. `dailySharpe()` is now the single frontend definition and reproduces the stored value to 15 significant figures. `FallbackMetrics` also lost `worstStreak` — a trades-labelled row has no honest answer from a day list, and `worstLosingStreakOf(pnls)` off trades replaces it in both synthesizers. See `## Backtest detail — chart and KPI conventions` → *Metrics that were saying the wrong thing*. Same day: **the verdict left its full-width bar and became the FIRST card**, leftmost, which takes the section to **180px collapsed / 305px expanded** at 1670 (from 234 / 345, and 318 / 496 on this panel's first build). The bar was charging a whole row — 44px plus its gap, in both states — on a panel whose point is fitting on one screen with the equity curve. **The move was only safe because the content changed shape with it, and that is the transferable lesson:** the rules were inline pills laid out by wrap, fine at full width and five lines at a quarter of it, and since the grid is `items-stretch` a tall fourth card drags the other three with it — as rows each rule is 24px whatever it says. The card anatomy (`panelCardCls` / `CardHead` / `CardHero` / `PanelRows`) moved to module scope so the fourth card cannot drift from the three beside it; `verdict` and `ribbon` are separate props because two callers still want a bar (a stack's strategy legend is genuinely horizontal, an optimizer combo has no verdict at all); and breakpoints are set by the longest real rule label, measured at 118px. See `## Backtest detail — chart and KPI conventions` → *The verdict is a card, not a bar*. Earlier the same day: **the Performance panel's rows became label + ⓘ + number, and validating its numbers turned up three that were saying the wrong thing.** Every explanation moved onto the label's tooltip, which deleted the ragged right column and the re-explaining suffixes in one move (`4 days · consecutive losing`); the panel now collapses to its three heroes + the drawdown meter, default ON, so the equity curve shares the fold. The three metric bugs: `worst_losing_streak` counts **trades**, not days (the real worst run of losing calendar days was 2, not 4); time underwater is weighted by the **calendar**, not by row count (`daily_pnl` omits flat days, so 67% "of days" was 67% of ACTIVE days — 71% by the clock); and profit concentration was measured in **dollars**, which on a compounding account reports the compounding — 89% ("edge clustered — overfit risk", the page's only warning colour) against an honest 40%. Plus `fmtDate` parsed dates as UTC midnight and printed a day early in five separate copies. See `## Backtest detail — chart and KPI conventions`. Earlier the same day: **the Evaluation + Performance panel was rebuilt as `PerformancePanel`: a verdict ribbon over three question cards** (Made / Risked / Trusted), replacing the 6+6 `KpiGrid` and its evaluation card. That layout caused all three standing complaints at once — cropped values (a fixed `KPI_ROW_H` on variable content), visibly uneven cards (`KPI_COLS` widened for one long money value), and an empty evaluation box on `unconstrained` — and none was fixable by resizing. Metrics group by the question they answer, so every one fits at once: **the expand toggle and both fixed heights are deleted**, `StackDetail` included. Two rules landed with it: **colour marks the exception, not the sign** (a wall of green ranks nothing, Worst Day can only be negative, and Sharpe 0.91 is positive AND weak — soft numbers say so in words), and the new **`DrawdownMeter` may never invent its references** — the gold limit tick only when the ruleset states a peak-% limit, the hatched tail only from a `dd_basis === 'percent'` stress test, otherwise it says the tail is *unknown, not zero*. The trade count became the ribbon's anchor with its `≈2/month` cadence. See `## Backtest detail — chart and KPI conventions`. Earlier: 2026-07-30 — **Max Drawdown and Calmar were measuring against a static account balance and both were wrong on any compounding run** (1096.7% and a red 0.11 on a run whose true figures are 54.9% and 2.25). Both now divide by the running PEAK — see `## Backtest detail — chart and KPI conventions` → *Drawdown is peak-relative*. Same day: the price chart's **scroll-left paging shows itself** (the blank strip you scroll into is shaded from the oldest loaded bar back, with a `Loading earlier bars…` chip — see `ChartPanel/CLAUDE.md` → *Paging older history*), and the News & Holiday filter **stopped duplicating the KPIs and now reshapes the real ones**. It has no section of its own: it is a pill on the empty half of the **Performance** header, driving the actual `PerformancePanel` (via a synthesized filtered `Run`) plus the Equity chart, with each card's caption swapped for its delta vs unfiltered. Bank holidays became a real checkbox instead of a hidden always-on rule (and both rules default OFF as of 2026-08-01), every label became a COUNT rather than a state word, and `exit_ms` on `EquityPoint` made **Avg Trade** computable over a subset. See `## The News & Holiday filter` below — especially the four things that deliberately do NOT follow the filter. Earlier: 2026-07-29 — the price chart's **fib levels are configurable** (add / remove / retune / recolour / hide, per drawing or as the tool's persisted default), and the News & Holiday filter became a collapsed-by-default accordion whose state lives in a page-level `useNewsFilter` hook, so the MAIN Equity chart redraws on the kept trades (its own duplicate mini-curve is gone); 2026-07-28 — price chart: a **Go to date** pill that jumps the view to a typed date (paging history in on the way); earlier, the Analysis dropdown (Trades + Winners/Losers, Blocked and **Missed** + per-reason filters), and it now ships/opens on the run's own timeframe with older history paged in on scroll-left

Auto-loaded by Claude Code when editing any file inside `frontend/`.

React + Vite + TypeScript app on `:5173`. All API calls go to the FastAPI backend on `:8000` via the Vite proxy at `/api`. Dark indigo-black UI, electric cyan accent, gold secondary.

**Lab design principle:** Run Backtest modal starts with no firms pre-selected. User must actively choose which firm challenges to evaluate against — never auto-select all.

---

## Stack

- React 18 + TypeScript + Vite
- React Router v6 — client-side routing
- TanStack Query — all server state
- sonner — toasts
- TailwindCSS — custom theme in `tailwind.config.js`
- Lucide React — icons (no other icon libraries)
- Recharts — analytics charts (equity, drawdown, P&L, etc.) — no D3, no other charting libs here
- klinecharts (v9) — the candlestick **price-chart panel only** (`src/components/ChartPanel/`). Lazy-loaded; do not import it elsewhere. All other charts stay on Recharts.

Do not add UI libraries (MUI, Radix, Headless UI, etc.) without raising it first.

---

## Directory layout

```
frontend/src/
├── App.tsx                  router + layout shell
├── main.tsx                 entry point
├── api/client.ts            ONLY place fetch() lives
├── types/index.ts           mirrors all backend Pydantic models exactly
├── hooks/                   one file per backend domain
│   ├── useLab.ts            strategies, rulesets (useRulesets + useFirms alias), runs, evals, sweeps, optimizations, useChartSpec (price-chart panel), useRunNews (post-run news/holiday tags), useHistoryLimit (broker history floor → the date picker's min)
│   ├── useBots.ts
│   ├── useSmartMoney.ts
│   ├── useStressTests.ts    stress tests — useStressTests, useStressTest, useRunStressTest, useDeleteStressTest, useRunningStressLock, useStrategyBestGrades
│   └── useCalendar.ts       live News Calendar — useCalendar(fromMs, toMs) → GET /calendar?from&to, 45s poll, placeholderData keeps the prev week while paging
├── components/              reusable, dumb components
│   ├── Sidebar.tsx
│   ├── TopBar.tsx
│   ├── StatCard.tsx
│   ├── EmptyState.tsx
│   ├── SystemHealthStrip.tsx
│   ├── RunBacktestModal.tsx
│   ├── WorthinessBadge.tsx  Tier 1/2/3 pill badge (green/cyan/yellow)
│   ├── Tier3WarningModal.tsx    smart-routing modal for Tier 3 → sweep or optimize anyway. Bounded `flex flex-col max-h-[88vh]`: header + footer are `flex-shrink-0`, the intro/sub-header/sweep-CTA stay pinned, and ONLY the instrument rows scroll (their own `overflow-y-auto` with a `sticky` thead) — so a long instrument list never clips the header/footer. Tested results always show; the untested long tail is collapsed behind a "Show N untested instruments" toggle (`showUntested`) so the tested rows stay the focus
│   ├── OptimizeButton.tsx   tier-aware optimize trigger (Tier1 soft confirm, Tier2 direct, Tier3 warning)
│   ├── ParamEditor.tsx      SHARED strategy-param editor used by all three editing surfaces (Run / Tune / Optimize) so they never drift. **Rows are STACKED — param label (plus the tune `was X` tag) on one line, control on the next** — because side-by-side gave the label only the leftover width and every label in the narrow tune rail truncated to `Arm on di...`, with the `was on` tag cropping it further. **Every control then renders at one size (`CONTROL_W` = `w-full max-w-[420px]` x `CONTROL_H` 34px) — toggle, select, number and switch alike** — so the list has one straight edge, a row's height never depends on its label, and a wide Run/Optimize modal doesn't stretch a toggle across half the screen. In optimize mode the number box (`NumberBox fill`) and the sweep button share that one width. **A non-numeric param can be swept too, as a value LIST (2026-08-02)** — `AxisEdit` gained a `{mode:'list', values}` variant, and `sweepChoices(p)` is the single definition of what set a param has (a `choices` dropdown's options; a bool's two states, labelled from `p.options`). It is gated on `allowListSweep`, which `OptimizeButton` sets only for the **python** runner: NT8 and MT5 hand a Start/Step/End range to their own tester, so a list of strings has nowhere to go (the backend refuses one too — see `backend/CLAUDE.md`). Ticking the sweep button starts with EVERY option selected and the chips untick from there, and the last selected value cannot be unticked — a swept param with an empty set expands to zero combinations, which would run an optimization of nothing. Everything else (free text, a time) still renders read-only as `inherited · not swept`, which is now a true statement on the backend as well. Toggle state labels truncate (with a `title`) rather than wrap: a wrapping label used to grow its row and break the rhythm of the whole list. String params with a `choices` list render a **dropdown**, never free text — `choices` beats `widget`, because strategies match enum strings exactly and silently no-op on anything unrecognised, so a typo would disable a setting with no error. Essentials card (core knobs) + counted accordions, Simple/Expert switch, conditional `show_if` visibility, named toggle/switch/time widgets. **`show_if` takes a single value OR an array of values (2026-07-30)** — an array means "any of these", which every enum with one OFF state and several ON states needs (a minimum-stop mode of Off / % of price / Fixed $ / x ATR is the first). Before the array form the dependent row could only be tied to ONE of the ON values and stayed hidden for the rest, which reads as a missing setting rather than a conditional one; note the comparison is stringified, so `1` and `"1"` match. **`min`/`max` reach the number input as of 2026-08-02** — the scanner has passed them through from the meta since it was written and nothing read them, so a bounded param looked unbounded; the first real user is `mpc_sos_fade`'s Custom stop level, a fib ratio that must land in (0, 1.0]. Treat them as a CUE, never a gate: a native number input stops the spinner and marks the field `:invalid` (styled `invalid:text-neg`) but still accepts a typed or pasted value past the bound, so the STRATEGY's own check is what actually refuses one — `SosFadeConfig.__post_init__` raises and fails the run rather than silently substituting a different stop. Friendly labels/groups/descs/units/`core`/`options`/`guide` come from the schema (overlaid from a strategy's companion `<Strategy>.meta.json` by the scanner). Theme tokens only; colour rule: blue=focus only, gold=section-title text. `mode`: `run`|`tune`|`optimize`. `explainer`: `panel` (fixed right column — wide Run/Optimize modals) · `inline` (drops under the focused row) · `coach` (no per-row explainer — parent renders the exported `<ParamCoach>` footer; `onFocusChange` surfaces the focused param). Degrades gracefully with no metadata (no core → no Essentials card, all groups as accordions)
│   ├── PeriodPicker.tsx     shared backtest-period control (two ISO date inputs + 1Y/3Y/5Y/All presets + the start<end message) plus the `today`/`yearsAgo` helpers and the `PresetBtn` pill. Used by `RunBacktestModal` (new run), `BacktestDetail`'s `RerunModal`, and `StackConfigModal` so a period is picked identically everywhere. Takes an optional `limit?: HistoryLimit | null` (from `useHistoryLimit`) = the broker's MEASURED earliest backtestable date: it sets `min` on both inputs, **clamps the 1Y/3Y/5Y presets** to the floor (so "5Y" on a 4-year broker asks for what exists) and makes "All" mean all there IS, and renders a one-click **"Start at <date>"** fix — a native `min` stops the calendar widget but NOT a typed or pasted date. `limit == null` (non-python runner, agent down, unidentified broker) leaves the range fully open: the backend and data layer still refuse a bad window, so guessing a limit here could only be wrong. `source: 'seed'` renders as "last known — terminal unreachable" so a fallback is never mistaken for a measurement
│   ├── InfoTip.tsx          shared "ⓘ" hover tooltip for KPI/metric labels (BacktestDetail + StressTestDetail). Portalled to `<body>` with fixed positioning so a card's `overflow-hidden` can't crop it, AND clamped to the viewport on both axes — anchoring straight to the icon's rect pushed a right-edge card's tooltip (Calmar, last column) off-screen. Height is measured in a `useLayoutEffect` before paint, so it can flip below the icon when it won't fit above. `TIP_W` must stay in sync with the `w-[208px]` class — the clamp math reads it
│   ├── RulesetTypeBadge.tsx PROP EVAL / PROP FUNDED / PERSONAL / DEMO type badge for ruleset rows
│   ├── RobustnessGradeBadge.tsx  A/B/C/D/F letter grade pill
│   ├── GradeLegend.tsx      collapsible "Grade key" explaining A–F (mirrors backend services/grading.py) + the "target A or B before a bot" guidance; reused on the StressTests list. Uses RobustnessGradeBadge
│   ├── WorthinessLegend.tsx collapsible "Score key" explaining the worthiness tiers (STRESS TEST / OPTIMIZE / DISCARD; mirrors backend services/worthiness.py); shown above the Backtests Runs table. The Score-column companion to GradeLegend. Uses WorthinessBadge
│   ├── RegimeOverlayToggle.tsx  regime-band on/off pill (Layers icon + "Regimes"). SHARED by BacktestDetail's equity chart and TuningWorkbench's overlay — the tune page carried a plain checkbox, so one control looked like two different things on two charts meant to read as one system
│   ├── XModeToggle.tsx      Date / Trade # segmented switch for the equity x-axis. SHARED by BacktestDetail's equity chart and TuningWorkbench's overlay, and both read one stored preference (`lib/chartAxis.ts`), so the two pages can never disagree about the axis
│   ├── ChartTabPanel.tsx    shared tabbed chart chrome (tab strip + right-side slot + Expand button) and the portalled fullscreen `ChartModal`. **Fullscreen convention, app-wide:** the expanded view carries a **camera** (copy-as-image) button and closes with a **`Minimize2`** icon — never an X, and the inline chart never gets a copy button (expanding is what you do before sending someone the chart). `ChartModal` gives every Recharts chart both for free via `lib/chartImage.ts` (`copyChartAsPng`: clone the SVG → paint the page background in → 2× canvas → `ClipboardItem`, falling back to a download when clipboard image writes are blocked). The klinecharts price panel has its own canvas snapshot path and takes `showCopy` (host passes `isFullscreen`); the tuning workbench's own fullscreen wires the same two buttons. Extracted from BacktestDetail so StressTestDetail reuses it. Optional `aboveChart` slot renders KPI cards between the description and the chart. **Optional `keepMounted` (2026-08-03)** = tab keys that stay MOUNTED while another tab shows, so clicking them costs nothing — only worth it for a tab whose BUILD is slow and whose data is already loaded, which today means exactly one caller (`BacktestDetail`'s Price tab, where klinecharts spends ~1.8s laying 33k candles out). An inactive one is `visibility: hidden` + `position: absolute`: **`display: none` is the wrong tool and will look like it works** — a display-none container measures 0 wide, so klinecharts sizes its canvas to nothing and has to resize on reveal, which is the visible swap the whole thing exists to remove. Unset = every tab renders only while active, as before
│   ├── MonteCarloFan.tsx    equity path fan (100 paths, p10–p90) — shared `BANDS` array drives the lines, the percentile-named tooltip, AND the Luckier→Unluckier key below the chart; axes labelled (Cumulative P&L / Trade #). Optional `height` prop
│   ├── DrawdownDistribution.tsx  drawdown histogram with limit line; axes labelled (# simulations / max drawdown reached). Optional `height` prop
│   ├── WalkForwardChart.tsx IS vs OOS Sharpe grouped bar chart with zero baseline + "Sharpe" axis label; series named In-Sample (tuned on) / Out-of-Sample (unseen). Optional `height` prop
│   ├── SensitivityRadar.tsx param sensitivity horizontal bar chart — reads BOTH shapes: perturbation (signed `pnl_delta_pct`) and grid-injected (`degradation` → negative magnitude). X-axis domain is data-driven (`[lo-pad, hi+pad]`, always includes 0) so the worst-case bar never clips. Optional `height` prop
│   └── ChartPanel/         strategy-agnostic klinecharts price-chart panel — HAS ITS OWN CLAUDE.md.
│                            Lazy-mounted on BacktestDetail; reads a ChartSpec (candles, sessions,
│                            trades, generic overlays, indicators). Zero strategy-specific logic.
│                            NOTE: EvaluationCard, EquityCurveChart, DrawdownChart,
│                            DailyPnlChart, DirectionBreakdown are all inline
│                            components inside BacktestDetail.tsx — not separate files.
└── pages/
    ├── Overview.tsx
    ├── SmartMoney/
    │   ├── index.tsx         tab shell + scan control
    │   ├── Rankings.tsx
    │   ├── CandidateProfile.tsx
    │   ├── PoolOverview.tsx
    │   ├── DisqualifiedLog.tsx
    │   └── Config.tsx
    ├── Bots/
    │   ├── index.tsx         monitor tab + live snapshot
    │   ├── ConfigureTab.tsx  risk caps + deploy
    │   └── UsersTab.tsx      Telegram users
    ├── Rulesets.tsx          own top-level page (/rulesets) — firm-grouped prop tables + personal group
    ├── Backtests.tsx         lab landing — Runs / Sweeps / Stacks tabs. `CreateStackModal` (Stacks tab) picks 2+ Python strategies + one shared instrument/timeframe/costs/window; a live `useStackPreview` shows a green **Reuse** or amber **Run** chip per leg (reuse = a completed standalone run already matches these exact settings) + a summary; when every leg reuses, no backtest fires and the button reads **Create stack**
    ├── BacktestDetail.tsx    **Tune button carries a COUNT badge** of the iterations already run from this run (`source_run_id === runId`, off the unfiltered `useBacktestRuns()` so it shares the Runs list's cache entry) — clicking it opens the workbench where they all live. Without the badge the only way to discover a run had ever been tuned was to go back to the Runs list and spot the nested Tune rows. Full run detail — params side panel, per-firm evaluation + KPIs, tabbed charts, logs, News & Holiday filter (inline `NewsFilterPill`/`ExcludeRule`/`PerformanceHeader`, driven by the page's `useNewsFilter` hook — which feeds the KPI grid AND the Equity chart)
    ├── StrategyDetail.tsx    strategy "spec sheet" — overview + grouped param reference tables
    ├── SweepDetail.tsx       sweep results — live-updating table sorted by worthiness tier
    ├── StackDetail.tsx       portfolio stack (`/backtests/stacks/:stackId`). `composeCombined` unions the enabled legs' trades over one shared account (combined start = Σ each leg's opening balance) into a synthetic backtest-shaped `run` + portfolio equity, tagging each equity point with a `leg_<id>` running-balance field for the overlay lines. **Trades + Performance = a single backtest's own panel**: BacktestDetail's exported `PerformancePanel` (Made/Risked/Trusted), with `StackTradesRibbon` passed into the `ribbon` slot — the per-strategy trade breakdown inline and the combined total anchored right. A stack keeps the BAR while a backtest moved its verdict into a fourth card, and that is deliberate: a legend is one entry per leg with its colour, so it is genuinely horizontal and would wrap badly in a quarter-width column. Recomputes as strategies toggle. (Was a fixed-height `StackTradesCard` beside the 6+6 grid; both that grid and its pinned height are gone.) Charts are a `ChartTabPanel` (Equity / Price / Breakdown) with the SAME controls as a run: **Equity** is the real exported `EquityCurveChart` on the combined portfolio (so it inherits every toggle — Trade excursions, Run-ups & drawdowns, Date/Trade `XModeToggle`, Regimes `RegimeOverlayToggle`, expand) with a line per enabled strategy overlaid via the new `overlayLines` prop; Breakdown reuses exported `DrawdownChart`/`DailyPnlChart`/`DirectionBreakdown`; Price is exported `PriceChartView` fed the merged stack spec (structure layers/fib/measurement/expand/minimize, drill-down via `base_run_id`, trades layered + tinted per strategy). Regime bands come from `StackDetail.regime_timeline` (backend computes it on-demand for the shared window — sweep-child legs aren't tagged — and caches it). Everything recomputes on the per-strategy chips (≥1 always on). **Rerun** opens the shared `StackConfigModal` prefilled with the stack's full config. Per-strategy row → that leg's BacktestDetail with `state:{fromStack}` so its Back returns here; reused legs are real standalone runs. Trades handed to the price chart carry `layerColor` + `layerName`, which is what makes the chart print `<strategy> · Won` in each outcome chip and build its own **Strategies** dropdown (see `ChartPanel/CLAUDE.md`). `avg_trade_duration_min` is the legs' own averages **trade-weighted** (you can't average durations flat), and profit factor reports `Infinity` when the enabled legs have no losing trade — the Made card prints ∞ rather than a dash that reads as missing data
    ├── Optimizations.tsx     own top-level page (/optimizations) — optimization list table
    ├── OptimizationDetail.tsx  optimizer results (/optimizations/:id) — table/bar-chart toggle, "Tune winner"
    ├── TuningWorkbench.tsx   /backtests/runs/:runId/tune — param editor + iteration leaderboard + regime overlay. The **Equity overlay** plots ACCOUNT BALANCE (not cumulative P&L from $0) off each run's own `equity_curve` — the same points BacktestDetail's equity chart draws — so the baseline traces an identical path there and here. It reuses that chart's conventions wholesale: starting balance derived as `equity[0] - profit[0]`, y-ticks anchored ON it, dashed break-even ReferenceLine, and the baseline as a monotone `Area` with `baseValue={startBal}` + the split green/red stroke and fill (split offset mapped to the filled shape's bbox, same math). Iterations ride on top as dashed palette Lines. Every run is anchored at the window's start date so the lines share a left edge, and balances FORWARD-FILL on days a run didn't trade (nulls + `connectNulls` drew a fake diagonal across flat stretches); `<runId>__pt` marks the real trade rows so only those get a dot. Regime bands come from ONE `date → regime` map, built TIMELINE-FIRST: the baseline's full-calendar `regime_timeline` if it has one, else any iteration's, else (pre-timeline runs) every run's tagged `daily_pnl` days merged — a run only reports days it traded, so any single run's tags leave the calendar full of holes. Fullscreen has the camera + minimize buttons. Its header controls are the run page's, in the run page's order and spacing — `XModeToggle` then `RegimeOverlayToggle`, `gap-2`. It carries the SAME `XModeToggle` as the run page and reads the SAME stored preference (`lib/chartAxis.ts` `getXMode`/`setXModePref`), so the two pages can never disagree about the axis: Date plots the calendar, Trade # keys each run's curve by trade ordinal (`balByIndex`) and a shorter run simply holds its final balance once it's out of trades. Regime bands project onto whichever axis is active — `regimeBandsFromTimeline` (date) or `regimeBandsByIndex` over the BASELINE's trades (trade #), both fed from one `date → regime` map, timeline-first
    ├── StressTests.tsx       stress test list — grade badge, prob breach/pass
    ├── StressTestDetail.tsx  stress test detail — grade card + tabbed Monte Carlo / Walk-Forward / Sensitivity workspace
    ├── Calendar.tsx          live News Calendar — Forex-Factory-style economic calendar. **Opens on today** (first mount selects today's day when on the current week with no explicit day; deselecting → whole week sticks). Day-summary strip (Mon–Sun counts, click-to-filter, Today button), "now" line + live countdown off the server clock, actual/forecast/previous with beat/miss colour. Filters (currency chips w/ country flags, independent High/Medium/Low impact toggles, category dropdown) + week offset + selected day all live in the URL. Fetches the whole week; filters CLIENT-SIDE so changes are instant and the strip counts stay in sync. Shared display helpers (flag map, impact colours, time/countdown formatters) live in `lib/calendar.ts` — reused by the Overview preview
    └── Settings.tsx
```

Path alias: `@/` → `src/`. Always use it — never `../../../`.

Implementation-level detail for the denser pages (BacktestDetail, TuningWorkbench, StressTestDetail, and the rest of the pages above) — exact layout structure, chart/KPI conventions, sizing-UI wiring, cross-linking rules: `command-center/docs/FRONTEND_BUILD_NOTES.md`.

---

## Feature flags — `src/lib/features.ts`

**Added 2026-08-04. Smart Money is OFF.** Aaron is leaning the command center down to
what he actually uses and Smart Money is not on the list for a while, so it is hidden
rather than deleted: the pages, hooks, types, backend router and the `smart-money/`
pipeline itself are all untouched, and flipping `FEATURES.smartMoney` back to `true`
restores the area whole.

**A flag hides an AREA, not a component — its nav row, its route and every card that
summarises it move together.** Hiding only the nav leaves a page reachable by URL,
which is not "removed"; hiding only the route leaves a nav row that goes nowhere. So
one flag is read in three places:

| Place | What it does |
|---|---|
| `Sidebar.tsx` | `NavEntry.feature` ties a row to a flag; `VISIBLE_SECTIONS` drops it, **and drops a section left with no rows** — a header over nothing |
| `App.tsx` | the routes are inside `{FEATURES.x && <>…</>}` |
| `Overview.tsx` | the stat cards and the module card, **and the hooks that feed them** |

- **Hidden means NOT FETCHED.** `useRunProgress` polls every 30s forever, so a card
  that is merely not rendered goes on costing a request twice a minute for a feature
  nobody can see. Both smart-money hooks took an `enabled` param for this; measured in
  a real browser, the Overview now issues **0** `/smart-money` requests.
- **A grid's column count must follow what is actually rendered.** Two cards left in a
  `grid-cols-4` row is half a row of blank space, which reads as data that failed to
  load — so both Overview grids pick their columns off the flag (4→2 stats, 3→2 module
  cards).
- **`FEATURES` is typed `Record<…, boolean>`, deliberately NOT `as const`.** With
  literal types every `FEATURES.x && <Card/>` narrows to `false` and TypeScript starts
  reporting the switched-off branch as dead code to delete, which is the one thing a
  flag exists to prevent.
- **`App.tsx` gained a `path="*"` redirect to Overview** in the same pass. An unmatched
  path rendered *nothing* — a blank main area beside a working sidebar — so a stale
  `/smart-money` bookmark looked like the app breaking. Verified: it lands on Overview.
- ⚠ **This does not retire the *add a route → add a NavItem* rule below** — it is that
  rule with a switch on it. Both still change in one commit.

Verified in a real browser at 1670×940: nav reads Overview / Strategies / Backtests /
Optimizations / Stress Tests / Bots / Rulesets / Calendar / Settings, the string
"Smart Money" appears nowhere on the Overview, and `/smart-money` redirects.

---

## Tab state — always use URL

All page-level tab state lives in the URL via `useSearchParams`, never `useState`. This preserves the active tab across refresh, back/forward, and deep links.

```typescript
// Pattern used in Backtests, Bots, SmartMoney
const [searchParams, setSearchParams] = useSearchParams()
const tab = (searchParams.get('tab') ?? 'default') as TabType
const setTab = (t: TabType) => setSearchParams({ tab: t }, { replace: true })
```

Special case — SmartMoney's `profile` tab requires `selectedCandidate` in session state. If arriving cold on `?tab=profile` with no candidate, fall back to `rankings`.

---

## Live log streaming during active runs

`useRunLog` accepts a third `live` boolean parameter. Pass `live={isRunning}` from the parent page so logs poll at 2 s during an active run and stop polling when the run completes:

```tsx
// In LogsSection or equivalent:
const { data: log } = useRunLog(open ? runId : null, 200, isRunning)
```

Also auto-expand the log panel when `isRunning` is true (`autoExpand={isFailed || isRunning}`) so the user sees live output without clicking.

---

## Hook conventions

One hooks file per backend domain. Every hook wraps a single endpoint.

```typescript
// Read
export function useThings() {
  return useQuery({
    queryKey: ['things'],
    queryFn: () => api.get<Thing[]>('/things'),
    refetchInterval: 30_000,
  })
}

// Write
export function useCreateThing() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ThingCreate) => api.post<Thing>('/things', body),
    onSuccess: () => {
      toast.success('Thing created')
      qc.invalidateQueries({ queryKey: ['things'] })
    },
    onError: () => toast.error('Create failed'),
  })
}
```

- Never call `fetch()` directly — always `api.get/post/put/patch/delete`
- Every mutation needs `onSuccess` toast + `invalidateQueries`, and `onError` toast
- Query keys: `[domain, resource]` or `[domain, resource, id]`

---

## Component conventions

Pages own data fetching. Components own rendering. No business logic in components.

- Numbers → `font-mono tabular-nums`
- Loading → skeleton for tables/cards; `value="—"` for `StatCard`
- Status indicators → use existing `StatusPill` / `StatusDot` patterns, don't invent new shapes
- All tab state → `useSearchParams` (see above)

---

## Standard components — use before building new

| Component | Use for |
|---|---|
| `StatCard` | All stat tiles. Supports `value="—"` loading, `onClick`, `disabled` |
| `EmptyState` | Empty data screens — icon + title + description |

Extend an existing component with a new prop before forking a near-duplicate.

---

## Sticky page banners (`StickyHeader` + condense-on-scroll)

Top page banners are always sticky. Only the two full-bleed detail pages (BacktestDetail, TuningWorkbench) **condense** as you scroll — the minimize earned its keep there (it reclaims vertical space for the chart while a full-height side panel stays pinned). The list/index pages (Rulesets, Backtests, Optimizations, Stress Tests, Strategies) deliberately do NOT condense: their banner stays full and just drops a scroll shadow. Content scrolls behind the banner; tabs, filters, action buttons, and any collapsed score/grade legend stay pinned.

**The 22px gotcha — read before touching any sticky banner.** The app shell's `<main>` is the scroll container and has `p-[22px]`. A `position: sticky; top: 0` child of a *padded* scroller pins **22px below** the visible top, not flush against it. That single transparent strip is what caused the earlier round of bugs: a horizontal gap content scrolled through, "cropped" table headers (rows peeking through the strip), and a 22px jump the instant scroll crossed the threshold.

Fix, baked into the shared `components/StickyHeader.tsx`: pin at **`-top-[22px]`** (not `top-0`), full-bleed back across the padding with `-mx-[22px] -mt-[22px] px-[22px] pt-[22px]`, and `flow-root` so child margins are contained and the painted `bg-bg-base` reaches the content boundary (no gap). At rest the banner already sits at its pinned spot, so there's no jump.

Use the shared `StickyHeader` for list pages — it's a render-prop: `children: (scrolled) => ReactNode`, but it now always passes `scrolled = false` so the header never condenses (it stays sticky + drops the scroll shadow). The per-page `scrolled ? …` branches are kept intact (harmless dead branches) so condensing any list page is a one-line revert in the component. Earlier condense styling for reference: shrink the title (`text-h1` 20px → `text-[16px]`), force any legend collapsed (`<GradeLegend forceCollapsed={scrolled} />`), keep the painted bottom spacing INSIDE the banner (`${scrolled ? 'mb-2.5' : 'mb-[18px]'}` — never a parent `space-y-*` gap, which is transparent and lets condensed content scroll up to the title), and never inline the title into a tab row (reads as a tab item).

Full-bleed detail pages hand-roll their banner (it coexists with a full-height sticky side panel) via the `useStickyBanner` hook. Same `-top-[22px]` correction applies, and the side panel offsets its own sticky `top` by `Math.max(headerH - 22, 0)` to pin directly below the banner (not behind it). Condensed detail banners keep the period + ruleset chips (drop them only at narrow widths via `max-[1100px]:hidden` / `max-[900px]:hidden`).

**Two glitch fixes baked into `useStickyBanner` (don't regress these).** (1) **Hysteresis** — it condenses only after scrolling past `condenseAt` (72px) and re-expands only below `expandAt` (8px). A single flip point sits right where condensing shrinks the banner, so the scroll position lands on the boundary and the banner oscillates full↔condensed. (2) **Constant scroll height** — condensing shaves ~85px off the banner, which shrinks the scrollable area; on a short page the browser then **clamps `scrollTop`**, dropping it below `expandAt` and re-expanding — a feedback loop hysteresis alone can't stop (the clamp moves the scroll position itself). So the hook returns `collapse` (px the banner gave up vs its expanded height) and each page renders an invisible `flex-shrink-0` bottom spacer of that height, holding total scroll height constant. Both BacktestDetail and TuningWorkbench wire `collapse` this way.

---

## Theme system — how it works and how to swap

All color values live in **`src/themes/electric-indigo.js`** — the single source of truth.

| File | What it feeds |
|---|---|
| `src/themes/electric-indigo.js` | Master color values |
| `tailwind.config.js` | Imports the theme → builds all Tailwind tokens |
| `src/themes/chart.ts` | Imports the theme → exports constants for Recharts (SVG can't use Tailwind classes) |
| `src/index.css` | Body bg + scrollbar are hardcoded here to `bgBase` / `bgSurface2` — update manually when swapping |

**To swap themes:**
1. Create `src/themes/<new-theme>.js` with the same shape as `electric-indigo.js`
2. Update the import in `tailwind.config.js` → `from './src/themes/<new-theme>.js'`
3. Update the import in `src/themes/chart.ts` → `from './<new-theme>.js'`
4. Update 3 values in `src/index.css` (body bg, scrollbar thumb, scrollbar border — comments label which theme key each maps to)
5. Rebuild

**Theme token classes — never hardcode colors in components:**

| Use | Class |
|---|---|
| Primary text | `text-text-primary` |
| Secondary text | `text-text-secondary` |
| Tertiary / dim | `text-text-tertiary` |
| Surfaces | `bg-bg-base`, `bg-bg-sunken`, `bg-bg-surface` |
| Borders | `border-border-subtle`, `border-border-default` |
| Accent (cyan) | `text-accent`, `bg-accent`, `border-accent` |
| Profit / pass | `text-pos-text`, `bg-pos-muted` |
| Loss / fail | `text-neg-text`, `bg-neg-muted` |
| Warning | `text-warn-text`, `bg-warn-muted` |
| Gold / highlight | `text-gold-text`, `bg-gold-muted` |

**Chart components** — import from `@/themes/chart` and use `C.pos`, `C.neg`, `C.accent`, `C.tooltipBg`, `C.axisTick`, etc. Never paste raw hex in chart props.

No raw hex anywhere else. Exception: brand gradient in `TopBar.tsx` (intentional — it defines the wordmark style).

---

## Toasts

```typescript
import { toast } from 'sonner'
toast.success('Saved')
toast.error('Failed: ...')
```

- Every user-initiated state change → success + failure toast
- Reads don't toast
- Don't toast on navigation, hover, or query refetches

---

## Routing

- Routes defined in `App.tsx`
- Sidebar nav items in `Sidebar.tsx` — one `SECTIONS` array grouped by what each item IS: an ungrouped **Overview** at the top, then **Lab** (Strategies → Backtests → Optimizations → Stress Tests, in lifecycle order), **Live** (Bots; Smart Money sits here too and is flagged OFF), **Reference** (Rulesets, Calendar). Add a new item to the section it belongs to. A row carrying a `feature` key is dropped when its flag is off — see *Feature flags*
- `live: false` shows a "Soon" badge; set to `true` when the page is real
- Navigation: `useNavigate()` — never `<a href>` for in-app links
- **Activity indicator:** `Sidebar.tsx` shows a pulsing accent `ActivityDot` on Backtests / Optimizations / Stress Tests when a job is running under each (`activeByRoute`, mirroring each page's "active" logic — backtest/sweep run excluding optimization combos, optimization grid, any stress phase). The dot is anchored to the **icon's top-right corner** so it's identical expanded or collapsed; expanded also adds a "Running" pill. Polling comes from the list hooks (`useBacktestRuns` now adaptive 3s/15s like `useOptimizations`; `useStressTests` 10s)

---

## Regime color constants

Regime visualization uses `REGIME_COLORS` / `REGIME_LABEL` / `REGIME_ORDER` from `src/lib/regime.ts` (single source of truth — imported by `BacktestDetail.tsx` and `TuningWorkbench.tsx`). Applied via inline style since these data-driven colors aren't in the Tailwind theme.

| Regime | Hex | Notes |
|---|---|---|
| TRENDING | `#06b6d4` | cyan — app accent |
| TRANSITIONING | `#8b5cf6` | violet |
| RANGING | `#f59e0b` | amber |
| HIGH_VOLATILITY | `#ef4444` | red |
| LOW_VOLATILITY | `#64748b` | slate |
| UNKNOWN | `#6b7280` | produces no colored segment in the overlay |

Companion constants in `BacktestDetail.tsx`: `REGIME_LABEL` (full display strings), `REGIME_LABEL_SHORT` (abbreviated for narrow zones, e.g. `Trans.`, `Hi Vol.`).

## Foundational config

`ParamSchemaEntry` carries `category?: 'strategy_logic' | 'foundational'`. Foundational params are never shown as editable inputs in `RunBacktestModal` or the optimizer grid — both filter them out; `RunBacktestModal` shows them read-only instead, pulled from the selected ruleset. `RunBacktestModal` also carries a **Sizing Mode** toggle (Consistent | Bullet) that picks how the dynamic sizing engine turns a strategy's unit-size signals into real contracts — it only affects strategies reshaped for the engine and is inert for the rest. `BacktestDetail` renders the resulting sized account as its own chart tab, timeline table, and per-firm KPI switching (a strategy makes the same trades for every firm, but each firm's ladder/floor sizes and halts them differently).

Implementation detail (exact param-type render rules, the sized-chart/timeline/breach-cutoff mechanics, per-firm `effRun` switching): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

## Rulesets page (own top-level nav item)

`pages/Rulesets.tsx`, route `/rulesets` (Reference group, with Calendar). Prop rows grouped by firm, personal/demo rows in their own group; page-level firm/Personal filter. Prop rows are read-only in the UI (server-side locked); personal/demo rows have an edit modal for the 5 personal rule fields.

Implementation detail (exact columns, contract-cap pill rendering, canonical display names): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

---

## What NOT to do

- Call `fetch()` directly
- Hardcode colors — tokens only
- Put business logic in components
- Forget `invalidateQueries` after a mutation
- Create new spinner or empty-state components — use existing ones
- Add a UI/animation/chart library without raising it first
- Use `any` in TypeScript — use `unknown` + narrow instead
- Store server state in `useState` or React context
- Use relative imports that escape the current folder — always `@/...`
- Use `useState` for page-level tab state — use `useSearchParams`

---

## When you add a new page

1. Create `src/pages/PageName.tsx`
2. Add the route in `App.tsx`
3. Add an entry to the right group in `SECTIONS` in `Sidebar.tsx` (Lab / Live / Reference)
4. If it needs data, create `src/hooks/useThing.ts`
5. Add types to `src/types/index.ts`
6. If it's a stub, use `EmptyState` for the placeholder — replace when it goes live

---

## Lab UX principle

The lab is a platform for designing and stress-testing trading strategies, not a dashboard. Every page should help the user make a decision: is this strategy viable, which parameter set is most robust, does it survive Monte Carlo? Design for decisions, not metrics.

---

## Backtest detail — chart and KPI conventions

BacktestDetail's charts live in one tabbed panel (Equity / Price / Breakdown), each fullscreen-expandable, with a permanent Performance-by-Regime table below. The numbers above them render as **`PerformancePanel` — one row of four question cards** (see the section below). **`FitMoney` never abbreviates (2026-08-01).** It renders the full thousand-separated figure and, when one genuinely cannot fit, shrinks the TYPE — `$14.4M` and `$846.3k` are harder to read than the number they replace, and reading it is the entire job of a headline. `dollarShort` is deleted; do not reintroduce a `k`/`M` form here. **The measurement is the part that breaks silently:** it must measure against the hero ROW (`data-fit-box` on `CardHero`), never against its own span, which is a content-sized flex item whose width IS the text's width — so `need > avail` was true by exactly the slack, on every value, forever. That is why `+$14,387,475` rendered as `$14.4M` in a card with room for it twice over. The same trap is already recorded below for `PanelRow` values ("do not use `FitMoney` here"); it applied to the hero too and was missed. Because a CSS transform leaves the layout box at natural size, the wrapper pins its own width to the scaled width — otherwise the unit label beside it sits where the unscaled text ended. Verdict colours, chips, and tooltip styling all follow the shared theme tokens (see Theme system above) — nothing here is bespoke to this page.

### The Performance panel is four questions, not twelve peers

**Rebuilt 2026-07-31, replacing the 6+6 `KpiGrid`. Read this before adding a metric.**

Twelve equal cards with a fixed pixel height was the wrong shape three ways at once, and every
complaint about the old panel traces to one of them: **cropping** (`KPI_ROW_H` 196/228 — a constant
height on variable content, so the taller cards clipped), **lopsided cards** (`KPI_COLS` =
`1.4fr repeat(5,1fr)`, widened to fit one long money value and visibly uneven ever after), and an
**empty evaluation box** (`unconstrained` states no rules by design, so `EvalCard` rendered 300×196px
of nothing). None of the three is fixable by resizing; they are all consequences of the layout.

The metrics answer four questions — what did it **Make**, what did it **Risk**, can I **Trust** it,
and what is the **Verdict** — so there is one card per question, each with one hero number and its
supporting rows. Consequences worth knowing before you change it:

- **The 6+6 expand toggle is gone**, and with it both fixed heights. Three wide cards hold every
  metric at once, so nothing hides behind a chevron and rows flow instead of clipping. `KPI_ROW_H`,
  `KPI_ROW_H_EXPANDED`, `KPI_COLS`, `MoreMetricsToggle` and `TradeCountStandout` no longer exist —
  in `StackDetail.tsx` either.
- **The evaluation card became `VerdictCard`** — a fourth card, rendered FIRST (2026-07-31, second pass — it was a
  full-width ribbon in between). The empty box cannot recur because a ruleset with nothing to say
  simply has no rows. See *The verdict is a card, not a bar* below for why the content had to change
  shape to move, and what still uses the `ribbon` slot.
- **The trade count is `VerdictCard`'s hero**, at the same 34px as the other three, with its cadence
  beneath it (`≈2/month`) — it is the sample size every other number rests on, and cadence is the
  unit the root `CLAUDE.md` Trading Philosophy states the design target in. It appears exactly once
  on the panel; printing it in *Trusted* as well made the second copy read as a different number.
- **`deriveKpis` is unchanged and still the single derivation**, so the news filter's `compare`
  mechanism works exactly as before. Add a metric there first, then to a card's row list.
- **The whole panel collapses to its heroes** (`collapsed`, persisted under
  `performance_panel_collapsed`, **default ON** — hence `getPerfCollapsed`, since `getBoolPref`
  defaults off). Expanded, the panel plus its header fills the fold on a laptop and pushes the
  equity curve entirely off screen, and the headline and the curve are read together. The three
  heroes and the drawdown meter survive the collapse, so the default still answers "how did this
  run do" without a click. `StackDetail` passes nothing and stays expanded.
- **Height is measured, not eyeballed.** At 1670×940 with the params panel collapsed the section
  (header + cards) is **180px collapsed / 305px expanded**, from 234 / 345 with the ribbon and
  318 / 496 on the first build of this panel. Things that carried it, each worth knowing before you
  add height back: the card's **question shares the title's line** (its own row charged ~16px per
  card, forever, for a sentence nobody re-reads); the meter's **limit-label padding is charged only
  when a limit exists** (15px of blank card on every ruleset stating none); the **verdict left its
  own row** (44px + a 10px gap, in both states); and rows are `py-[4px] leading-[1.3]` at 24px each.
  Re-measure rather than estimate — the biggest single saving on the ribbon build was a sentence
  that wrapped, which was invisible in the source and only showed up on a real render.
- **Measuring gotcha, cost an afternoon:** Playwright's option is `newContext({ viewport })`.
  `viewportSize` is Puppeteer's name, is silently ignored, and every reading lands at the default
  1280×720 while the script claims 1670. Card *widths* are the tell — if the four sum to ~990 on a
  1670 run, the viewport never applied. `page.setViewportSize()` IS correct on the page object.

#### The verdict is a card, not a bar

**2026-07-31, second pass.** The verdict went evaluation-box → full-width ribbon → a card in the row. The
bar bought a row it did not need: 44px plus its gap, charged in both states, on a panel whose whole
point was fitting on one screen with the equity curve.

**Moving it was only safe because the CONTENT changed shape with it, and that is the transferable
part.** As a bar the rules were inline pills laid out by wrap — fine at 1330px, five or six lines at
a quarter of that. The grid is `items-stretch`, so a tall fourth card drags the other three up with
it, and you would trade one 54px row for something worse. As **rows** each rule is 24px whatever it
says, and each rule's explanation moved from a `title` attribute nobody discovers to the same ⓘ every
other row uses. Before moving anything else into that grid, ask whether it lays out by wrap.

Rules that hold it together:

- **The card anatomy lives at module scope** — `panelCardCls`, `CardHead`, `CardHero`, `PanelRows`.
  They were closures inside `PerformancePanel`; a second private copy in `VerdictCard` is exactly
  how the fourth card would drift out of line with the three beside it. Change the anatomy in one
  place and all four move.
- **`VerdictCard` is FIRST**, leftmost (`0.8fr 1fr 1fr 1fr`). The grade and the sample size are what
  you check before reading the three numbers to their right, and it inherits the position the
  ribbon's own verdict chip held at the panel's top-left.
- **`VerdictCard` has no question line.** At ~285px there is no room for a title, a question and a
  verdict chip, so the chip takes the aside slot the other cards use for `no limit set`.
- **The ruleset name is a caption under the hero, not a row.** It is identity, not measurement, and
  the row's value column is `whitespace-nowrap` — `Unconstrained (No Limits)` there would push the
  card wide. As a caption it truncates with the full name on `title`.
- **`verdict` and `ribbon` are separate props.** Two callers still want a bar and neither is a
  regression: `StackDetail`'s strategy legend is genuinely horizontal (one entry per leg, with its
  colour), and an optimizer combo (`isOptCombo`) has no verdict at all — just a prompt to run a real
  backtest, which earns the width. Passing `verdict` is what switches the grid to four columns.
- **Breakpoints are set by the longest rule label, measured.** `Daily DD ≤ $5,000` renders 118px at
  12px, plus its ⓘ and tick. So: weighted `1fr 1fr 1fr 0.8fr` from **xl** (verdict card ~285px at
  1670, ~202px at 1280 — fits), four EQUAL columns at **lg** (weighted there lands near 148px and
  would truncate the label to nothing useful), two columns below that. Measured across widths:
  180/305 at 1670, 1440 and 1280; 207/362 at 1200; 223/378 at 1024.
- **The `verdict unfiltered` badge became a `Graded on → all 142` row.** Same fact — firm rules are
  evaluated server-side on every trade, so the grade never follows the news pill — stated as a
  number instead of a label to decode.

#### A row is a label, a ⓘ and a number — nothing else

**2026-07-31.** Every row's explanation lives on the label's `InfoTip`, never beside the value.
Suffixes carried both a definition and a judgement (`4 days · consecutive losing`,
`3.63 · strong — wins 2× losses`) and cost twice for it: they re-explain a term the reader learned
on first read, and they make the value column ragged, because a column of numbers is only as tidy as
its longest sentence. Rules if you add a row:

- `PanelRow.tip` is **required**. Write what the metric IS, then what THIS value means — the
  `*Label` helpers (`sharpeLabel`, `pfLabel`, `concentrationLabel`, `zScoreLabel`, `winRateLabel`)
  are still the single definition of the words and now end their tip rather than the row.
- `PanelRow.value` is a **`ReactNode`, but keep it short** — usually a formatted number, or a tick
  or cross on a pass/fail rule row. The column is `whitespace-nowrap`, so a long value pushes the
  card wide rather than wrapping. Do not use `FitMoney` here — it measures a flex cell that shrinks
  to its content, decides the number doesn't fit and abbreviates a value with room to spare (that is
  why Net read `+$846.3k` in a card wide enough for `+$846,257` twice over). `FitMoney` is for the
  fixed-width hero only.
- The **delta** is the one thing allowed beside a value, because it is what the news filter was
  opened to ask. Unmoved rows print nothing.
- **Units get converted, not printed raw.** `1365 min` is a number the reader has to divide before
  it means anything; `fmtHold` gives `22.8 h`.

#### Colour marks the exception, not the sign

The obvious rule — green for positive, red for negative — fails three ways, so the panel does not use
it. On a strategy that works nearly every row is positive, so a wall of green ranks nothing. **Worst
Day** and **Deepest in $** can only ever be negative, so red on them is decoration on a definition.
And **Sharpe 0.91 is positive AND weak** — green would call it good, and on this very run the news
filter moves it 0.91 → 2.98 by removing 3 of 142 trades. The rule instead:

- the three **hero numbers** carry colour (each is its card's verdict)
- every **delta** is coloured in both directions — a change is the signal the filter was opened to
  find, and its direction is the point
- a **row** stays neutral unless it is an exception: an unexpected sign (a negative Net inside
  *Made*), or a value past a threshold (concentration ≥60%, PF <1, a ≥6-day losing streak)

Where a number is soft its **tooltip** says so in words rather than the value lying with a colour.
`exceptionCls(cls)` maps a value-colour helper to "no colour" for ordinary values, so the `*Cls`
helpers stay the single definition of what counts as bad while only the crossings get painted.
Sharpe is the one that moved (2026-07-31): it now goes **amber below 1.0**, which is not a sign
colour but the same exception rule as every other row — green-for-positive would have called 0.91
good, amber-for-weak is the threshold that should stop you.

#### Metrics that were saying the wrong thing — fixed 2026-07-31

All of these were unit or basis errors, not display bugs, and each looked plausible enough to
survive a redesign. **Every one of them is the same mistake: `daily_pnl` holds only days that
CLOSED a trade, and three separate metrics treated that sparse series as if it were the calendar.**
Check for it before trusting the next one.

- **`worst_losing_streak` is counted in TRADES.** `backtest/output.py:_worst_losing_streak` walks
  the trade list, not the day list; the row said "4 days". On a strategy that trades twice a month
  that reads as a far worse run of luck than it was — the real worst run of consecutive losing
  *calendar* days on that run is 2.
- **Time underwater is weighted by the CALENDAR, not by row count.** Counting rows answered "what
  share of ACTIVE days" while the label said "of days". 67% by rows, 71% by the clock.
- **Profit concentration is measured in RETURNS.** See below — this one was printing a false amber.
- **Sharpe zero-fills flat weekdays, and there is now ONE frontend definition of it.** The backend
  has always zero-filled (`metrics.zero_filled_daily_values`, and its docstring warns about exactly
  this); the frontend had two private copies that did not, in `computeFallbacks` and in
  `StackDetail.composeCombined`. Scoring only the days that traded asks "how good were the 142 days
  it traded" and then annualizes by √252 as if it had traded 252 of them — on the shipped run
  that is **2.96 against a true 0.91**, over 142 active days in a 1,447-weekday span. It surfaced
  as a news-filter delta of **+2.07 from removing 3 of 142 trades**, which is the tell: the filtered
  side fell back to the frontend formula while the unfiltered side used the stored backend one, so
  the "delta" was two different formulas, not a change. `dailySharpe()` in `BacktestDetail.tsx` is
  now the single frontend definition and reproduces the stored value to 15 significant figures —
  that equality is the regression test; run it before touching either side. A stack read 13.06.
- **A streak has no daily fallback any more.** `FallbackMetrics` no longer carries `worstStreak`,
  because there is no honest way to answer a trades-labelled row from a day list — `deriveKpis`
  reads `run.worst_losing_streak` and nothing else. Both synthesizers (`buildFilteredRun`,
  `StackDetail.composeCombined`) set it with the exported `worstLosingStreakOf(pnls)`, off trades in
  entry order. Until this was fixed, the filtered panel printed consecutive losing DAYS in a row
  that said "N trades".

#### The *Made* hero is DOLLARS, and the starting balance is on screen (2026-08-01)

The hero was the MULTIPLE (`1439.7x on capital`) with the dollars demoted to a row. Aaron's call to
swap them, and the reason is the second half of his complaint rather than the first: **the starting
balance appeared nowhere on this page**, so the multiple was a number with no referent — 1439.7x of
*what*. Now:

- hero = **Net dollars**; caption directly beneath = **`from $10,000`**, taken off the equity curve
  itself (`equity[0].equity - equity[0].profit`) rather than the ruleset, because a python run
  opens on its own deposit and that is what the multiple actually divides by;
- first row = **`Return on capital 1439.7x`**, the old hero;
- the caption survives the collapse, because the multiple in the rows below is meaningless without
  it.

**Keep the compounding caveat on both tooltips.** At a fixed % risk per trade the dollar figure is
exponential in the edge, so it is the number LEAST comparable between runs — which is exactly why
it had been demoted in the first place, and the trade-off is deliberate: the dollars answer "what
was this worth" directly, and the tooltip says to rank on R or profit factor instead.

A **`Costs charged`** row landed with it, and it appears ONLY on a priced run. Charged costs were
invisible until this date — the run row carried the settings and nothing reported the resulting
figure — and `costs_usd` now rides on each equity point (`EquityPoint`, backend AND frontend: the
model drops any field it does not declare, the third time that trap has been hit here). Printing
`$0` on an unpriced run would read as "trading was free" rather than "nothing was priced", hence
the row is hidden rather than zeroed. Its tooltip carries the compounding warning because the raw
charge and its effect are wildly different sizes: on the shipped run **$50,582 of charged slippage
moves the final balance by $1,630,361** — 32x — purely because a dollar not earned early never
compounds.

#### Two rows the Performance panel needed, and one column on the Runs list (2026-08-01)

An audit of run `f866873aa862` found **no arithmetic wrong on this page**. What was wrong was what
three true numbers let a reader conclude. Same class as *Metrics that were saying the wrong thing*
above, except nothing here was miscomputed — each number simply needed a companion beside it, and
a label change could not have supplied one.

- **Win rate 67.3% → a `Won / scratched / lost` row.** A trade that closed a cent up counts as a
  full win. On that run 45 of the 111 "winners" made under a sixth of a typical loss, every one
  exiting at exactly the breakeven-stop buffer — the stop doing its job, which is real risk
  control and is not an edge. The honest split is **40% won / 27% scratched / 33% lost**.
  `computeScratchCount` measures a scratch against **the run's own median full loss**, so the bar
  self-scales across strategies and account sizes with nothing to tune (for a fixed-risk strategy
  that median IS 1R); median rather than mean so one outsized loss cannot move it. It returns
  `null` — never 0 — with no losing trade, because 0 would read as "no scratches" rather than
  "no scale to measure against". Amber past a quarter of the book: at that point the headline win
  rate is describing something other than winning.
- **Profit concentration → a `Top 5 trades` row beside it.** The existing row splits the span into
  QUARTERS, so it answers *did the edge show up in one period*. The reader hears *did it come from
  a handful of trades*, and the two can disagree completely — that run reads 34% by quarter
  (spread evenly across 6.6 years) while 5 of its 165 trades made **47%** of everything won.
  High is not automatically bad, and the tooltip says so: a runner-based strategy is meant to be
  fat-tailed, so it means the edge lives in the tail, not that the run is overfit.
- **Max DD on the Runs LIST was dollars only.** `BacktestDetail` has had the peak-relative
  percentage since 2026-07-30 (*Drawdown is peak-relative* above); the list did not, and the list
  is where runs get compared. $1.7M of drawdown listed beside $14M of profit reads as ~12% where
  the honest figure is **56%**. The percent now leads with the dollars beneath it — the percent is
  what is comparable across runs of different sizes, the dollars are what a prop-firm limit is
  written in. `BacktestSummary.max_drawdown_pct` is backend-stored (the list ships no equity
  curves); a negative value is the backfill's "measured, no answer" sentinel.

Both trade-shape metrics are computed **client-side and returned from `deriveKpis`**, exactly like
profit concentration and for the same two reasons: the stored column is whatever basis was current
when a run finished, and the news filter needs every number recomputed over a subset.
`services/metrics.py` applies identical rules, so a stored row agrees without the page depending
on it.

#### Profit concentration measures the edge, not the account

**`computeProfitConcentration` weights each trade by its RETURN on the equity it was taken with,
not by its dollars, whenever the run compounded.** In dollars the metric reports the compounding
rather than the clustering it exists to detect: on an account that grows 85x the final quarter must
hold nearly all the dollars however evenly the edge is spread. Measured on run `d2ab68f9e884` —
dollar quarters of $9k / $49k / $71k / $1,039k read **89%** and printed the panel's only warning
colour ("edge clustered — overfit risk"); the same trades as returns read **40%** ("spread across
the test"). The amber was describing the account.

The switch is `equityBase(equity) > 0` — whether the curve carries a real account balance. A
%-of-equity strategy compounds and must be normalized; an NT8-shaped cum-P&L-from-zero curve is a
unit-size run whose dollars already ARE comparable across periods, and dividing those by a
fictitious balance would introduce the opposite bias. `StackDetail` already used the same
`equity[0].equity - equity[0].profit` idiom to find a stack's opening balance.

The panel **computes this client-side instead of reading `run.profit_concentration_pct`**. The
stored column is whatever basis was current when a run FINISHED, so preferring it would show a mix
of old and new figures depending on a run's age. `services/metrics.profit_concentration_pct` applies
the identical rule and `init_db` re-stamps history, so a stored row agrees — but the page does not
depend on that having happened.

#### The drawdown meter, and the two things it may never invent

`DrawdownMeter` gives the *Risked* hero the reference it needs — 54.9% is neither good nor bad until
you say what you would accept. Both references are drawn **only when real**:

- the **gold limit tick** is the ruleset's own `personal_max_drawdown_from_peak_pct`. Prop rulesets
  cap a *trailing dollar floor*, which is a different rule from a peak-relative percentage — those
  get no tick, and their rules show as `VerdictCard` rows instead. Do not convert one into the other.
- the **hatched extension** is the stress test's worst-1% simulated drawdown, gated on
  `dd_basis === 'percent'` (the dollar basis isn't comparable on a compounding run, and tests before
  2026-07-30 have no percent columns). With no stress test the caption says *"the simulated tail is
  unknown, not zero"* — an unmeasured tail must never be drawn as an absent one.

The track snaps to one of `METER_CEILINGS` (25/50/75/100) rather than scaling to the run, so two runs
of the same strategy stay visually comparable.

The Equity chart is a TradingView-style panel. **Its x-axis is the CALENDAR by default** (`xMode`, persisted; a Date / Trade # switch sits with the series toggles). Calendar is canonical: regime bands only have a true width on it, drawdown DURATION is a time metric, and it's the axis the tuning workbench overlays runs on — so the same run traces the same path on both pages. Trade # spaces every trade evenly and exists for per-trade forensics (streaks, excursions). `x` is the plotted position in whichever unit, and the regime bands, the run-up/drawdown ribbon and the starting-balance anchor (`windowStart` = the run's start_date in date mode) are all expressed in that same unit, so switching moves the chart together. Regime bands are built from ONE `date → regime` map (the run's full-calendar `regime_timeline` — see backend — falling back to `daily_pnl` tags on pre-timeline runs) and then PROJECTED onto whichever axis is live: `regimeBandsFromTimeline` (date) or `regimeBandsByIndex` (trade #, each trade taking its date's regime). The first band stretches back to the anchor and the last forward to the final point, and they render with `ifOverflow="visible"` — Recharts DISCARDS an out-of-domain `ReferenceArea` by default, which is why an earlier stretch silently did nothing. **Stretch AFTER filtering out UNKNOWN**, or the stretch lands on a band that never renders and the chart opens with a bare gap. Shared axis maths (`getXMode`/`setXModePref`/`dateMs`/`niceStep`/`monthTicks`/`monthLabel`/`tradeTicks`/`balTick`/`balanceTicks`/`regimeBandsFromTimeline`/`regimeBandsByIndex`) lives in `lib/chartAxis.ts` — used by BOTH equity charts so they can't drift. The cumulative-PnL line is **colour-split at the starting balance** (green above, red below — `startEq = data[0].equity - data[0].profit`, offset mapped to the fill bbox so the flip lands on the break-even line), the curve is **anchored** by a synthetic starting-balance point so it leaves the `startEq` line, the Y axis is tick-anchored on `startEq` (starting balance always labelled), and a dot on every trade point (hover → Balance + Favorable/Adverse excursion). Two opt-in `SeriesToggle`s: **one bottom-bar toggle** — on runs that carry excursion it draws the combined **Trade excursions** bar (solid net-result core + translucent favorable/adverse halo, in true dollars anchored on `startEq`), otherwise a plain profit **Histogram** — and **Run-ups & drawdowns** (green/red ribbon along the bottom, green while equity makes new highs). Regime bands skip UNKNOWN (chart matches the legend). The XAxis is `scale="point"` so the bars never shift the line. Excursion needs `favorable`/`adverse` on `models.EquityPoint` (else FastAPI drops them) — and so does `entry_ms`, which the News filter tags on; that one was missing until 2026-07-28, so read this as a rule, not a one-off.

**The Equity chart's DATA can be filtered — `equityCurve = news.filteredCurve ?? run.equity_curve`.** When the News & Holiday accordion is removing trades, this is the only chart on the page that follows it; the KPI grid beside it follows the same switch (`newsOnKpis`), and every OTHER number and chart on the page still reports the raw backtest. Two rules if you touch it. (1) A filtered curve MUST be rebuilt on the run's real starting balance (`equity = startBal + running profit`), never restarted from 0 — the chart derives `startEq` from its first point and anchors the axis, the break-even line and the green/red split there, so a zero-based curve silently rebases the whole panel. (2) Anything indexed off the curve must read the SAME curve — `regimeBandsByIndex` does, or in Trade # mode every band after the first removed trade sits one trade to the right of what it describes. Details in `FRONTEND_BUILD_NOTES.md`.

### Drawdown is peak-relative — never over a static balance

**Fixed 2026-07-30. Read this before touching `deriveKpis`, `computeCalmar` or anything that divides by `balance`.**

A percentage of capital only means something if the denominator is the capital the account actually
had *at that moment*. Both drawdown-derived cards divided by the ruleset's `account_size`, frozen at
the opening balance, and on a compounding run that is not the account — it is the account 5 years
ago. The shipped `mpc_sos_fade` run (142 trades, $10k → $856k) printed **Max DD 1096.7%** and a
**red Calmar 0.11**. The honest figures are **54.9%** and **2.25**. Two of the six core cards were
arguing the strategy was bad.

- **`maxDrawdownPctOf(series)`** is the fix: worst drop as a fraction of the running peak. It also
  returns that episode's dollars and peak, because **the deepest DOLLAR drawdown and the worst
  PERCENTAGE drawdown are different events on a compounding run** — here $109,665 off a $330,303
  peak (33.2%) versus 54.9% off $16,748 (only $9,198). The card's sub-line must describe the episode
  its own value names; the deepest dollar figure moved to the tooltip, labelled as the prop-firm
  view. Putting them side by side is how the next wrong number gets written.
- **Calmar divides by that same fraction.** CAGR compounds, so the drawdown must too, or the ratio is
  measuring two different accounts. Follow-on: Calmar now **does** move with the Account balance
  slider — the old "capital-independent by design, the balance cancels" claim was never true and is
  gone from the tooltip.
- **This is the same defect the stress-test engine fixed the same day**, in a second file — see
  `backend/CLAUDE.md` → *Drawdown basis*, where Monte Carlo switched to a percent basis for exactly
  this reason. When a number is a percentage of a growing account, check the denominator grows too.
- 54.9% is also the figure the repo already recorded for this strategy (root `CLAUDE.md`, Run 12).
  The panel was the only place disagreeing with it — worth remembering as the tell.

Full implementation detail (exact card set, fixed-height math, per-metric fallback rules, chart-specific quirks like the equity tooltip's segment-key filtering and the MT5 duration gap): `command-center/docs/FRONTEND_BUILD_NOTES.md`.

---

## The News & Holiday filter — it reshapes the REAL KPIs

**Reworked 2026-07-30. Read this before touching `useNewsFilter`, `NewsFilterPill` or `PerformancePanel`'s `compare` prop.**

The filter has now shed a duplicate copy of the run's numbers **twice** — first its own 200px equity
curve, then its own five KPI tiles — and both times the answer was the same: **reshape the page's
real readout, never ship a smaller second one beside it.** It has no section of its own. It is a pill
on the **Performance** header (a row that was otherwise empty, so the control costs zero vertical
space) and it drives the actual `PerformancePanel` plus the main Equity chart.

**1. A filtered run is a synthesized `Run`.** `buildFilteredRun` clones the run, overrides what the
trades determine (net P&L, win rate, PF, avg win/loss, drawdown, equity curve, daily P&L regrouped
with regime tags carried over by date) and then **NULLS every field derived from `daily_pnl`** so the
existing recompute path (`computeFallbacks`, `computeProfitConcentration`) redoes it off the filtered
series. The nulling is load-bearing — a left-behind `sharpe` is the raw run's, sitting in a grid
labelled filtered. This is the same transform `effRun` does for per-firm switching and
`StackDetail.composeCombined` does for a portfolio; three callers now want "synthesize a Run from a
trade list", so the next one should extract it rather than write a fourth.

**2. Four things cannot follow the filter, and none of them is faked.**
- **Per-firm SIZED runs block it outright** (`newsBlocked`). Sizing is path dependent — remove trade
  #7 and #8's position size changes, and every trade after it. That is a re-run, not arithmetic. The
  sized curve is also re-indexed 1..N over only that firm's taken trades, so the news tags (keyed on
  raw indices) would not even line up. The pill disables with that reason.
- **The firm Evaluation card** is computed server-side over every trade; it carries an `unfiltered`
  chip while Performance beside it is filtered.
- **`platform_sharpe`** is NT8/MT5's own whole-run number — no filtered version exists.
- **`sharpe_low_sample` is RECOMPUTED, not inherited.** Removing trades can only push a run *toward*
  too-few-days, so carrying `false` over would silence the warning exactly where it starts to matter.

**3. The Equity chart is gated on the SAME switch as the grid** (`newsOnKpis`). Holidays are excluded
without anyone touching a control, so on a blocked run the chart would otherwise quietly draw a
filtered curve under unfiltered numbers.

**4. Both exclusion rules are on screen, and both are switchable.** Bank holidays used to be
hardcoded always-on with no control and no row. That is what made the panel unreadable: the pill
counted trades being removed while the only visible switch said the news ones were *kept*, and
nothing accounted for the difference. Now each rule is an `ExcludeRule` row — tick, name, and **the
trades it matches whether or not it is ticked**, so the row doubles as the price tag on turning it
on. **BOTH rules default OFF (2026-08-01, Aaron's call)** — the page opens on the run exactly as
traded, so every figure on it is the backtest's own result and ticking a rule is a deliberate
what-if. This replaced two different defaults for one reason: a filtered default means the headline
number on screen is not the run's, and nothing about a checkbox further down the page makes that
obvious. Holidays had defaulted ON, and news followed the strategy's `avoid_news`, so the default
silently DIFFERED BETWEEN STRATEGIES — two runs over the same window could open on different trade
counts with no indication why. `strategy.avoid_news` is still real metadata; it just no longer
decides what you see first, and `useNewsFilter` no longer takes it. Because a trade can match BOTH rules, `excluded` is measured off the kept list, never summed
from the two counts.

**5. Every label is a COUNT, never a state word.** "News kept" / "news filtered" read as "nothing
removed" while holidays were going out regardless. The pill says `Excluding N trades`, the header
says `Performance · 139 of 142 trades`, the popover footer says `139 of 142 trades counted`. A label
that is a number cannot say one thing while the grid says another.

**6. Deltas replace each row's note, they don't crowd in beside it.** `PerformancePanel`'s `compare`
prop runs the extracted `deriveKpis` a second time against the unfiltered run; `rowSuffix` then swaps
the standing note (`· 3.63:1 R:R`) for the delta, and `heroDelta` does the same beside the big number.
The note is read once; the delta is the answer to the question the filter was opened to ask. Zero
extra height. **A row that did not move says nothing at all** (2026-07-31) — the old grid printed
"unchanged vs unfiltered" on every card, which was eight lines of text to communicate that nothing
happened. Deltas are the one place colour still tracks direction rather than exception, because a
change IS the signal here.

---

## Costs are switchable in TWO places, and the split is about arithmetic, not about UI

**Built 2026-08-02, extended to the run page 2026-08-03 at Aaron's request.**

The **Run backtest modal** (from `Strategies` or `StrategyDetail`) chooses the costs a run is
MEASURED at — one row per layer in `python_runner.COST_LAYERS`, every one **OFF by default**, gated
on `strategy.runner === 'python'`. **`BacktestDetail`'s Performance header now also carries a Costs
pill** (`CostFilterPill`, beside the News & Holiday one) that charges costs onto a run that already
happened, reshaping the real KPIs and the Equity chart without re-running anything.

⚠ **The first version of this section claimed a run-page toggle was impossible, and it was wrong.**
The argument was that a cost changes what the trades would have been, so a page-level control would
flip a number while the trade list under it stayed put. The premise is right and the conclusion does
not follow. **Every cost that CAN be re-priced costs a fixed amount of R regardless of position
size** — a spread over a stop distance, a commission over a stop distance — so the R is knowable
even though a charged run compounds into different position sizes, and the dollars follow from
re-walking the balance. Proven against real replays in `backtest/tests/test_reprice.py`; on the live
161-trade run `75ccc776d10c` the pill reproduces a real charged replay to **37¢ on $16.3M**. Left as
a standing reminder that "this cannot be derived" deserves the same evidence as any other claim.

**Where the split really falls** is on whether a cost changes WHICH trades exist:

| | re-priceable on the page | needs a re-run |
|---|---|---|
| | spread, commission, swap | `bid_ask_fills`, `slippage` |
| why | a fixed R per trade, size-independent | changes which setups fill / which exits were market orders |

`bid_ask_fills` moved the reference run 161 → 159 trades with four setups that never existed on the
free path — no arithmetic over a stored trade list can invent those. The server names such layers in
`needs_rerun` and the pill SAYS so; it never silently drops one and shows the rest under the same
label.

Rules the pill has to keep:

- **Costs compose BEFORE the news filter, never after** — `useCostFilter(run)` then
  `useNewsFilter(costs.repricedRun ?? run)`. A cost is a property of a trade, so it has to be
  charged before anything decides which trades count. With nothing charged the news filter gets the
  run's own object, reference-identical.
- **It rebuilds through `buildFilteredRun`, the same function the news filter uses.** One definition
  of "a Run derived from a trade list" is what stops the two controls drifting into different
  answers for the same KPI.
- **Refused under a firm's sizing, on the same guard as the news filter** (`newsBlocked`). A sized
  curve is PATH DEPENDENT — charging trade #7 changes the balance going into #8 and therefore its
  size — so there the cost is not size-independent and the whole justification evaporates.
- **`is_exact` false must reach the reader.** Two different causes, both captioned: a `swap` layer
  (accurate to ~0.3%, because its real charge depends on which bars existed and holiday closures
  are not in the stored trades) and `derived_basis` (a run predating the stored per-trade `r` /
  `risk_usd`, accurate to ~0.02%). Neither is "indicative" — but rendering either identically to an
  exact figure is how a number nobody measured comes to be trusted.
- **A trade the server did not price back voids the whole view** rather than passing through at its
  old value, which would show a partly-charged book as a fully-charged one.
- **Each row states its own price, and in R.** `CostRule` exists because the first build reused
  `ExcludeRule` — right for an exclusion rule, which counts the trades a release landed on, and
  meaningless for a cost, which touches every trade — so every row rendered a hardcoded
  `0 trades` that looked exactly like real data. **The unit is load-bearing:** a layer's DOLLAR
  cost depends on which others are on (charging one changes the balance, so every later position
  is a different size), so three dollar figures would not sum to the total beneath them and the
  panel would read as broken while every number in it was right. In R the size cancels and the
  rows add up exactly — pinned in `test_reprice.py` and `test_run_repricing.py`.
- 🔴 **THE PILL AND THE FOOTER CARRY THREE NUMBERS, AND NAMING ONLY TWO OF THEM READ AS A LYING
  PAGE (fixed 2026-08-03, reported by Aaron from the screen).** The footer said
  `−12.08R charged · $332,371 after compounding` and the pill headline said
  `Charging $332,371` — while the Net hero six inches away fell by **$18,200,741**. Both figures
  were correct and they are not the same quantity, so the only way to reconcile them was a
  subtraction the page never showed, and the honest conclusion from the screen was that the
  costs feature was broken. Worse, `total_cost_usd` is the FEES and "after compounding" is the one
  caption that does not describe them. The three, on run `75ccc776d10c`:

  | | | |
  |---|---|---|
  | **Charged** | `total_cost_r` | −12.08R — the size of it, and the only additive unit |
  | **Fees charged** | `total_cost_usd` | $332,371 — what actually left the account |
  | **balance impact** | `netBefore − netAfter` | $18,200,741 — 55x the fees |

  The gap is compounding and nothing else: at ~10% risk over 161 trades a fee paid early also
  costs everything it would have grown into. **The pill headline is now R** (`Charging 12.08R`) —
  a pill has room for one number and R is the one that cannot contradict the page, is what the
  rows above it sum to, and is comparable between runs. Both dollar figures live in the popover
  under their own names via the `Figure` row, with the ratio spelled out. **`useCostFilter` returns
  `netBefore` / `netAfter` / `balanceImpact`, summed off the SAME rows the Net hero sums**, so the
  pill and the card cannot disagree about what moved. The `Costs charged` KPI row was renamed
  **`Fees charged`** for the same reason — the old name invited exactly the subtraction that makes
  the two look like a contradiction.
- 🔴 **`cost_usd` IS SIGNED, and `-Math.abs()` on it was a live 25% overstatement (fixed
  2026-08-03).** A short's gold swap is a real CREDIT (+26.98 points/night on Vantage) and can
  exceed the spread on the same trade, so `cost_usd` goes negative — on the reference run **39 of
  161 trades are a net credit**. Forcing the sign booked every one of them as a charge, so the
  `Fees charged` row read **$415,990 against the pill's true $332,371**, and **$514,315 against
  $252,998 on swap alone — 103% high**. Two numbers, one label, six inches apart. The stored
  convention is negative = charge and `cost_usd` is the other way round, so the view SUBTRACTS it;
  it also adds to the point's own `costs_usd` rather than replacing it, so a run priced at replay
  time keeps its own charges in the row that names them.
- 🔴 **The pill was live under a firm's SIZED numbers while the page ignored it (fixed
  2026-08-03).** `costOnKpis` has always required `!newsBlocked`, so the charge correctly never
  reached a sized curve — but `CostFilterPill` took no `blocked` prop, so it stayed interactive,
  fetched, and read `Charging 12.08R` over numbers that had not moved. It takes the same
  `blocked` the news pill does now (`Charging n/a`, disabled, reason on the title). A sized curve
  is PATH DEPENDENT — charging trade #7 changes #8's position size — so the size-independence the
  whole control rests on is genuinely absent there.
- 🔴 **A server REFUSAL rendered as "Charging nothing" (fixed 2026-08-03).** `useRunReprice`'s
  `isError` was never destructured, so a 400 left `report` undefined → `view` null → `active`
  false → the label read *Charging nothing* with the reader's boxes still ticked. `reprice.py`
  refuses rather than guesses on purpose (a curve missing an entry price, a stop or a size is a
  re-run, not arithmetic) and that discipline is worth nothing if the UI shows the refusal as
  "no costs apply". The pill now says **Can't price this run** and prints the server's own
  message, which always names the missing thing.
- **The BROKER is named in the popover header** (`· vantage demo`). The two profiles differ by 50%
  on the gold spread ($0.22 vs $0.33), so a charge with no broker beside it is a figure whose
  provenance the reader cannot check.
- **A layer this broker does not charge says so in words** — `none on this account` rather than
  `0.00R`, which reads as a failure to compute. A demo pays no commission and that is a finding.
- **A layer the RUN charged renders ticked and LOCKED** (`charged in the run`, readout `in the
  run`). It is already in every number on the page; the server refuses to charge it again (see
  `backend/CLAUDE.md` → *already_charged*), and it cannot be charged OFF from here either, because
  the stored trades were measured with it. The row states no R on purpose — what that charge came
  to is baked into the trades and never reported separately, so any figure there would be invented.
- **The report is fetched with NOTHING ticked too**, because that is when the per-layer prices are
  most useful: you see what a layer would cost before turning it on, exactly as the news filter
  shows each rule's trade count whether or not it is applied.

**⚠ The trade count does NOT move, and that is correct — expect it to be reported as a bug.** It
already has been, from the screen. Spread, commission and swap change what each trade was WORTH;
only `bid_ask_fills` changes which trades exist, and that one is refused here. Verified end to end
on run `432aff31f374` (73 trades, Aug 2023 → Aug 2026), where everything else moves:

| | as traded | costs on |
|---|---|---|
| trades | 73 | **73 — unchanged, by construction** |
| net | $573,812 | $485,984 |
| win rate | 65.8% | 60.3% |
| profit factor | 4.04 | 3.83 |
| avg win / avg loss | $15,881 / −$7,539 | $14,945 / −$5,918 |
| worst drawdown | 57.2% | 60.1% |

Two things in that table are worth keeping. **The win rate falls 5.5 points because four trades
flip from winner to loser** — +$12, +$68, +$207 and +$376 becoming −$26, −$133, −$1,315 and
−$2,331 — i.e. scratches that only looked like wins because the run was frictionless. And
**drawdown gets WORSE while profit falls**: a cost does not merely shave the top off, it deepens
every losing stretch, so the two headline cards move in opposite directions and neither is wrong.

⚠ The RISKED card's percentage will not match a hand-calculation from the starting balance —
`ddWorst` rebases the curve onto the account-balance slider (`rebaseEquity(equity, balance)`), so
its denominator differs by design. It is still derived from the RE-PRICED curve, which is what
makes it move at all.

Four things about the Run modal that would each silently mislead if changed:

- **The spread is never typed.** `useBrokerProfiles` (`staleTime: Infinity`) fetches
  `GET /backtests/broker-profiles` and every detail string on those rows — the `$0.22` spread, the
  swap per night — is rendered FROM that response. A number hardcoded into a form is a second claim
  about what the backend charges, and that exact defect (the Run modal's old futures 2.25/1 reaching
  a forex run) is why this whole area was rebuilt.
- **Spread and "model bid/ask fills" are mutually exclusive**, enforced in `toggleLayer` by unticking
  the other. They are two ways of pricing one spread; both on bills it twice.
- **`cost_layers: []` and `cost_layers: null` must render DIFFERENTLY.** The detail row is gated on
  `run.cost_layers != null`: `[]` means the run was asked to charge nothing, `null` means the run
  predates the switches. Showing "no costs" for both would claim a deliberate free run where there
  was only an older contract.
- **Two rows are tagged, and the tags are the point.** Slippage says it is a guess (it is the one
  cost history cannot measure), and bid/ask fills says it moves trades (it is the only layer that
  changes which setups fill). A reader ticking either should know that before the run, not after.

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain. **Audited 2026-08-05, 11 defects, every one of them rendering a healthy-looking answer** — a `No MT5 link` chip and a blind-bot stat branch, disabled jobs no longer wearing the "scheduled" pill, a fleet balance that names the bots that did not report, dated stale rows behind a dead VPS, a calendar window that survives midnight, a ticking server clock shared with the Calendar page, a sample floor under "best PF", and a running-backtest banner. See *The Overview was audited 2026-08-05* |
| Smart Money | 🟡 Built, flagged OFF | Scan, terminal, rankings, profiles, disqualified, config, cache — all still work. Hidden from the nav, the Overview and the router since 2026-08-04 (`FEATURES.smartMoney`); nothing was deleted |
| Bots | ✅ Live | Monitor, control, configure, users. **Configure carries `DeployCard`** — the deployed version read off the VPS (hash / commit / date / params as deployed) plus the **Promote** button, which previews before it deploys and warns on the four states that make a version claim false. **Monitor's row shows a `No MT5 link` chip (2026-08-04)** beside the Running pill when the bot's process has lost its terminal — see *A blank cell is not a diagnosis* below. **Configure is a rail + detail panel (2026-08-04)** — a bot selector down the left, one bot's config on the right, a fleet version strip on top. It was one full section PER BOT with no selector. ⚠ **Only the selected bot's controls exist in the DOM** (1 promote button with 4 bots registered, measured), which is the misclick guard; the layout is downstream of that. **Monitor's `Fleet controls` card is danger-bordered, chipped `ALL N BOTS`, and every button carries its count** (`Stop all 4`) with the affected bots listed by name in the dialog; the row column header is `This bot`. 🔴 Its guards were computed off the demo/live-FILTERED list while the endpoints act on everything — fixed, and the card now says when the filter is hiding a bot. G11 closed |
| Backtests lab | ✅ Live | Runs / Sweeps tabs; run modal; BacktestDetail |
| Optimizations | ✅ Live | Own top-level page (`/optimizations`); detail at `/optimizations/:id`; "Tune winner" → workbench |
| Tuning workbench | ✅ Live | `/backtests/runs/:runId/tune` — edit params, run iterations, leaderboard + regime-aware equity overlay + net-P&L-by-regime |
| Worthiness Badges | ✅ Live | Tier 1/2/3 pill on every completed run |
| Sweep Detail | ✅ Live | ProgressCard, ResultsTable, FailedRunsTable, cancel + retry |
| Optimization Detail | ✅ Live | Table / Bar Chart toggle; best param callout; CSV export |
| Optimize Button | ✅ Live | Tier-aware modals; int-param range validation blocks decimals |
| Tier 3 Warning Modal | ✅ Live | Per-instrument past results; sweep untested; stamps contract month |
| Runner Badge | ✅ Live | NT8 (cyan) / MT5 (purple) icons; Python renders a gold "PY" text mark (it's local, not a vendor platform, so it has no product icon). Always use `RunnerBadge` — never a hand-rolled `<img src={isMt5 ? … : …}>`. On Strategies, StrategyDetail, Runs |
| Market Filter | ✅ Live | All / Futures / Forex on Strategies and Runs tabs |
| Stress Tests | ✅ Live | Grade card, source card, MC fan + drawdown + walk-forward + sensitivity charts |
| Regime tagging (M4) | ✅ Live | RegimeBadge + Performance by Regime table on BacktestDetail |
| Regime equity overlay (M4) | ✅ Live | RegimeOverlayToggle; faint background bands (`ReferenceArea`) on equity — consistent with the tune page; persists to localStorage |
| Optimizer regime filter (M4) | ✅ Live | Regime Filter select in OptimizerModal; chip in OptimizationDetail |
| Strategy deployment (Pass 2) | ✅ Live | Deployed sub-tab: drag/drop `.cs`/`.mq5`, delete, NT8 + MT5 compile |
| Deploy button (Pass 2.5) | ✅ Live | Per-strategy Deploy/Redeploy; filled accent when out of sync |
| MT5 backtest modal | ✅ Live | Free-text symbol, bar presets; Evaluate Against lists forex rulesets (personal forex demo) and is required like futures; Foundational hidden (NinjaScript-only) |
| MT5 backtest detail | ✅ Live | MT5_RUN_STEPS; NT8-only buttons hidden; Stress Test button shown |
| Run Stress Test modal | ✅ Live | WF + sensitivity run together; ruleset locked to first eval. Sample-size gate (mirror backend `MIN_TRADES_FOR_STRESS = 100`): Stress Test button disabled below 100 trades with an explicit tooltip — the whole test is blocked, not just a phase |
| Stress test market lock | ✅ Live | One futures + one forex test at a time; button disabled when blocked |
| Running stress indicators | ✅ Live | Pulsing chips/banners on Runs, BacktestDetail, OptimizationDetail |
| Strategy best grades | ✅ Live | Best Grade column on Strategies tab; links to the grading test |
| News Calendar | ✅ Live | `pages/Calendar.tsx` (`/calendar`) — Forex-Factory-style economic calendar off the free TradingView feed. Opens on today; day-summary strip, server-clock "now" line + countdown, actual/forecast/previous w/ beat-miss colour, currency chips (country flags), independent High/Medium/Low toggles, category dropdown. Whole week fetched, filtered client-side; all filter/week/day state in the URL. Shared helpers in `lib/calendar.ts` |
| History-limited periods | ✅ Live | `useHistoryLimit` + `PeriodPicker`'s `limit` prop. The date picker's minimum is the broker's MEASURED earliest backtestable date (probed server-side per broker, never hardcoded here), presets clamp to it, and a typed/pasted earlier date shows a one-click "Start at <date>" fix. Wired in `RunBacktestModal`, `BacktestDetail`'s `RerunModal` (which also disables Confirm below the floor) and `StackConfigModal`. Prevents submitting a window MT5 would answer with coarser bars mislabelled as the requested timeframe. |
| Overview calendar preview | ✅ Live | `pages/Overview.tsx` — full-width "Economic Calendar" card below the module grid: next high-impact callout (flag + countdown) + a 2-col list of the next upcoming events this week; whole card navigates to `/calendar`. Reuses `useCalendar` + `lib/calendar.ts` |
| Settings | ✅ Live | Config read/write; `nt8_agent_tunnel` + `mt5_agent_tunnel` |
| Sidebar health strip | ✅ Live | 4 dots: API, **SSH (3-state)**, NT8 (3-state), **MT5 Agent (3-state)**. Two of them were reporting something other than what they were named until 2026-08-02 — see *Two dots that were not measuring what they said* below |
| Price-chart panel | ✅ Live | Lazy klinecharts candlestick panel on BacktestDetail (`components/ChartPanel/`, own CLAUDE.md): TF switch (display resample up + M1→H1 drill-down w/ full-depth fetch + red "no earlier data" edge), sessions, generic overlays, indicators, day breaks, measurement + fib tools. The **fib LEVELS are configurable** TradingView-style — add, remove, retune, recolour or hide any level (extensions past 1.0 included) from a live editor, either as the tool's default ladder (gear on the tool strip, persisted) or for one drawing (its right-click menu); an un-customised fib follows the default live. **It SHIPS and opens on the timeframe the run TRADED, with no fetch** — the payload is capped by trimming the WINDOW (newest slice under `_CANDLE_CAP`; measured 33k candles / 3.1 MB / 17 months on a 2020→2026 15m run), never by coarsening the bars, so the chart paints on the first frame with no loading text and no swap. Older history **pages in as you scroll left** (one ~12k-bar chunk, ~1 MB, back to `spec.historyStartMs`) — and **says so while it does**: the blank strip you scroll into is shaded from the oldest loaded bar back with a `Loading earlier bars…` chip, so a page in flight no longer reads as the end of the data — so trimming costs reach, not access. **A page brings its own ANALYSIS with it (2026-08-02)** — structure overlays, fair value gaps, blocked and missed setups for that window (`?analysis=true`), merged into the panel's own — because all of those are emitted per-window and, until this landed, every layer you had switched on drew nothing past the shipped candles while its toggle still read ON. And and a **Go to date** pill beside the timeframe types you straight there instead, driving that same pager itself until the date is loaded (klinecharts only ever pages one chunk, and only on reaching the left edge), then centring the target bar. The Analysis menu opens with a **Deep debug** section — `Winners` / `Losers` / `Both` / `Off`, a radio sitting above the very rows it sets: one press gives Trades on with that outcome, **Fibs on**, External Structure + Fair Value Gaps on, Blocked and Missed off. That is the seven switches reading a run one trade at a time otherwise takes across two dropdowns, and it pairs with Step (press Winners, then ← / → walks only the winners, each arriving with the fib leg its entry was priced off already drawn). It presses the SAME switches the rows below it do — no second copy of layer state — and which preset is ticked is DERIVED from those rows, so changing anything by hand ticks `Off` instead; everything a preset does not name is left exactly as you had it. Beside it, **Step** (`◀ Loss 12/60 ▶`, or ← / → while the pointer is over the panel) walks the MARKERS instead of the calendar — previous / next, centred, with an accent dashed line on the one you landed on, paging history in through that same jump. **Its set is whatever the Analysis dropdown is showing**, oldest to newest: untick Winners and ◀ walks the losers, turn Trades off with Blocked on and it walks the refusals, leave both on and it interleaves them by time. It has no filters of its own on purpose — a second set would be a second place for the navigator and the chart to disagree. **Two header dropdowns split by question:** *Analysis* = what the strategy did with its signals — **Trades** (+ Winners / Losers filters, so a run reads as all-winners or all-losers), **blocked setups**, the trades that never happened (a setup the strategy had ready and its own rules refused: a dashed line pointing at the exact would-be entry price with a uniform `Blocked` tag parked clear of the candles, every refusing rule on hover, and one filter per reason), and **missed setups**, the ones that DIED partway (the same marker with the score on the tag — `2/3` / `3/3` — and hover showing what it had vs the one thing it didn't; the routine reasons start unticked, driven by `spec.missNoise`, so the layer opens on the misses worth studying). Both default OFF and are listed only when the run reports any. Directly before Fair value gaps sits **Fibs** — the fib LEG each trade was actually priced off, so a plotted trade says which retracement levels it went into instead of leaving you to redraw the fib by hand. Every level arrives as an explicit `(ratio, price)` pair the STRATEGY recorded when it PLACED the order, so **the browser does no fib maths at all** and the chart cannot land on a price the bot never used; the ladder spans the leg's start → the trade's exit, reaching back through the retracement rather than beginning at the fill, and each level is labelled on the RIGHT the way a hand-drawn fib is — **ratio only, no price** (2026-08-03, Aaron's call: the price is already on the axis and on the trade's own annotations). It draws the LADDER and nothing else; the `entry <ratio>` / `deepest <ratio>` accent chips it shipped with are gone, because the trade underneath was annotating the same two price rows and one number told twice by two layers is what made the chart read as doubled up. `entryRatio` / `deepestRatio` are still computed and still ride on the spec — they are the two readings a ladder cannot state — but nothing draws them today. `TRADE_FIB` is a SEPARATE overlay template from the fib TOOL on purpose — this one is data, not a drawing: locked, event-ignoring, and deliberately NOT following the fib editor's configurable ladder, because retuning your own tool must not restyle what the bot measured (only the factory COLOURS are shared). It reuses the trades effect's own predicates (loaded-candle clip, layer isolation, Winners/Losers), so the two layers can never disagree about WHICH trades are of interest — but it does NOT require Trades to be on, because a peer row whose layer draws nothing while its switch reads ON is the exact failure the per-window paging bug produced. Winners/Losers are therefore listed whenever EITHER row is on, so the fibs are never filtered by a control that is off screen. Default OFF and listed only when trades carry one — NT8/MT5 and pre-2026-08-02 Python runs show no switch, and there is no backfill because it would mean replaying the strategy, so an existing run needs a RERUN (Reload charts cannot supply it). Last in Analysis sits **Fair value gaps** — the gaps that were LIVE when something happened. The canonical `engines/fair_value_gaps/` engine is replayed server-side and a gap is drawn ONLY if it was open on the bar of a trade entry, a blocked setup or a missed setup (all of them when several overlap), so the layer answers "where were the gaps when this fired" instead of papering a 33k-bar chart with every gap the run ever saw. Default OFF with its box count. ⚠ The gaps are `mpc_assistant.pine`'s, deliberately NOT the stricter set the bot pins — a drawn gap is one the INDICATOR shows and not always one the entry rule counted. Below it, **Order blocks** (2026-08-03) — the supply/demand zones that were live on those same bars, off the canonical `engines/order_blocks/` engine, under the identical anchor rule (579 boxes on the measured run beside the gap layer's 661). Default OFF, and **not** in Deep debug. It needed no new template and no new effect — a plain `box` group and a second string in `ANALYSIS_GROUPS`. ⚠ **Its box is a fixed 30-bar STUB from the anchor candle, not a live-bar tracker** — so a block's box can end long before the block dies, or after the bar it died on; both are mpc's own drawing rule. ⚠ **No settings fork to warn about here** (the strategy files dropped order blocks entirely), which also means **a drawn block never explains an entry — the bot reads none.** *Structure* = what the market drew (structure groups + shipped indicators). Everything clock-driven — the session windows AND **Day breaks** — lives in the on-chart Sessions legend instead, so the two halves of "when did the day/session start" are in one place. Real spec via `useChartSpec`. **Market-structure overlays live** — the canonical `engines/market_structure/` engine replayed server-side (`chart_spec` → `structure_overlays.py`) into the 4 Structure toggles that mirror `structure_engine.pine` (External / Internal / Historic Internal Structure / Swing Point Labels — nesting like the Pine's via each overlay's `requires` list), default OFF, flat text tags anchored at each break line's midpoint (BOS/SOS/iBOS/iSOS), de-collided, on wick-anchored break lines |
| News & Holiday filter | ✅ Live (NT8 + Python) | **A pill on the Performance header that reshapes the page's REAL numbers** — no duplicated tiles, no section of its own (both were removed 2026-07-30). State lives in the page-level **`useNewsFilter`** hook because three things read it: the pill, the `PerformancePanel` (fed `news.filteredRun`, a synthesized `Run` built by `buildFilteredRun`) and the main Equity chart (`news.filteredCurve`). Popover lists BOTH exclusion rules as `ExcludeRule` checkboxes — bank holidays and high-impact news (with its before/after window sliders nested under it, default 15/30) — **both unticked by default (2026-08-01)**, so the page opens on the run exactly as traded; each row shows the trades it matches whether ticked or not. Every card's caption becomes its delta vs unfiltered (`KpiGrid`'s `compare` prop). **Refused rather than faked:** per-firm SIZED runs block the filter (sizing is path-dependent), the firm Evaluation card carries an `unfiltered` chip, `platform_sharpe` goes null, `sharpe_low_sample` is recomputed. Coverage-honest (untagged where no calendar data; the pre-`entry_ms` note offers "Reload charts" on NT8 only). **Forex/MT5 not wired — TODO #3** (needs MT5 `entry_ms`/`exit_ms` + non-UTC broker timezone handling) |
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail` page. Layer 2+ Python strategies over one shared instrument/timeframe/costs/window. **StackDetail renders like a single backtest on the combined portfolio** — reuses BacktestDetail's exported `PerformancePanel` + chart components + `PriceChartView` against a client-side `composeCombined` payload (identical three-question panel, Equity/Price/Breakdown tabs, full price chart with structure/fib/measurement). New + Rerun share `components/StackConfigModal.tsx` (prefilled for rerun) — and so does the **Strategies page**: ticking 2+ python rows there reveals a gold **Stack N strategies** button that opens the SAME modal prefilled with them, so a stack is configured identically wherever you start it (the checkbox column only appears when 2+ python strategies are listed, and a non-python row has no checkbox because stacking replays python only). Per-strategy toggles drive everything (same `enabled` set, ≥1 always on); a leg's Back returns to the stack. **Smart reuse** — `CreateStackModal` calls `useStackPreview` (POST `/backtests/stacks/preview`) to show per-leg Reuse/Run chips; a leg whose exact settings already have a completed standalone run is reused (opens the real run on View), the rest re-run fresh. Costs default 0/0 (comm 0 / slip 0 / 15m) to match the Pine strategies (all pinned commission=0, slippage=0); these fields are cosmetic for Python runs (real cost comes from the account profile), so 0/0 keeps the display honest. Match is STRICT (any settings difference re-runs) |

---

## Two dots that were not measuring what they said

**Fixed 2026-08-02, `components/SystemHealthStrip.tsx`.** Both were frontend-correct — they rendered
their field faithfully. The field was the problem, which is why neither could be spotted from this
side, and it is the third instance of the repo's standing lesson: **a label on a screen is a CLAIM
about code somewhere else.**

- **SSH** rendered `ssh_tunnel`, which the backend filled from `ssh forexvps "echo ok"` — a brand-new
  connection with nothing to do with the port forwards. After a laptop sleep the dot sat **green**
  beside two red agent dots, which sends you to the VPS when the problem is the dead tunnel on this
  laptop. It is now three-state, off two separate backend fields: green = the forwards are bound,
  **yellow = tunnel down but the VPS is reachable** (the backend's supervisor rebuilds it within a
  minute, so yellow means *wait*, not *go and do something*), red = the VPS is unreachable.
- **MT5 Agent** rendered `mt5_agent`, the Flask agent's `/health` — which answers `ok` whether or not
  the terminal is running or logged in. Every python backtest that needs uncached bars goes through
  MT5_Lab, so a terminal that had dropped its broker connection showed green and the run failed at
  fetch time. Now three-state on `mt5_connected`, mirroring what NT8's dot has always done: red =
  agent down (clickable), **yellow = agent up, terminal not connected** (needs RDP), green = both,
  with the server and account on the tooltip.

⚠ **`mt5_connected` is `boolean | null` and the null branch is load-bearing.** `null` means the agent
could not be asked — not that the terminal is disconnected. The checks are written `=== false`, never
falsy, so an unanswered question renders as *"terminal state unknown"* rather than as a failure the
UI invented. Same rule as `DrawdownMeter`'s refusal to draw an unmeasured tail as an absent one.

## The Calendar page was audited 2026-08-05

**Read before touching `pages/Calendar.tsx`, `lib/calendar.ts` or the Overview's preview.** Nine
defects, and the frame is the Overview's own from one page over: **not one of them rendered an
error.** A calendar that is confidently wrong about which week it is showing is worse than one that
says it does not know — and four of these made it wrong about exactly that.

🔴 **The week was frozen at mount.** `useMemo(() => localWeekStart(weekOffset), [weekOffset])` —
and `weekOffset` does not change at midnight, so a tab left open across Sunday→Monday went on asking
for LAST week for ever, with the day-strip dates and the Today highlight stale to match. ⚠ **This is
the identical defect the Overview fixed on 2026-08-05, and the Overview's own comment asserted that
THIS page recomputed and was right.** It did not. **A value derived from the CLOCK cannot be
memoized on a key that does not contain the clock** — the rule was written down here and the second
instance of it was sitting two files away the whole time. The 1s `useServerClock` tick is what
carries the recomputed value over the boundary with no reload.

🔴 **Paging a week rendered the PREVIOUS week under the new week's header.** `placeholderData: prev`
holds the old payload, and the page only checked `isLoading` — which is false, because placeholder
data exists. So for the length of the fetch the pill read `Aug 10 – 16` over a day strip reading
**0 0 0 0 0 0 0** (counts are computed against the NEW `fromMs`, so the old events all fall outside
0…6) and a list of the week before. ⚠ **Held data is only honest while the KEY is unchanged.** When
the key changes the held payload is not stale, it is the answer to a different question — so
`isPlaceholderData` now renders the loading state and the strip prints `—`, never `0`.

🔴 **A failed background poll deleted a good week.** `isError && <EmptyState/>` sat before the list,
so one 502 on a 45s poll replaced a fully-loaded calendar with "Couldn't load the calendar" while
TanStack still held the data. Now: a failure **with data on hand** is a dated banner above the
retained rows (`showing the calendar as of 14:32`), and only a failure with **nothing** to show
takes the page. Same rule, same wording, as the bot snapshot on the Overview — and the Overview's
own calendar card had the same bug and got the same fix.

🔴 **`?day=abc` rendered as an empty week.** `parseInt` gave NaN, which matches no event, so the
page said "No events" with every filter looking untouched. Range-checked to 0…6 now; anything else
reads as "no day selected", which is the honest interpretation of a URL nobody can satisfy.

🔴 **A category the loaded week has none of rendered as a BROKEN page.** The options come from the
loaded week and the selection lives in the URL, so paging to a week with no `Labor` rows left the
`<select>` matching no option — blank, over an empty list, with nothing saying a filter was still
applied. The selection is KEPT (paging back must restore it), the held value is offered as an
option, and the empty state names it.

⚠ **Duplicate React keys, and they are real rather than theoretical.** `timestamp_ms + currency +
title` is NOT unique in live feed data — the calendar carries two `CAD Budget Balance` rows at one
timestamp. The position is part of the key now, **on both surfaces**.

⚠ **The "now" line belongs to the week that CONTAINS now.** It used to draw on every week, so
paging forward put `Now 14:32` above next week's first event. Derived from the clock
(`nowMs >= fromMs && nowMs < toMs`), never from `weekOffset`, so it survives the rollover with
everything else.

**Efficiency, and the cost was the clock rather than the data.** `useServerClock` re-renders this
page every second and a week is ~200 events, so every row was rebuilt once a second — each one
calling `toLocaleTimeString`, which CONSTRUCTS a formatter per call. `EventRow` is `memo`'d (both
props are primitives, so only the row crossing `now` re-renders) and `lib/calendar.ts` holds three
module-level `Intl.DateTimeFormat` instances. ⚠ Do not inline a `toLocale*` call into a row again.

**Shared, not copied:** `fmtDay`, `fmtWeekRange` and `dayIndexOf` moved into `lib/calendar.ts`
beside `localWeekStart`. `dayIndexOf` matters most — **the Overview WRITES the index this page
READS** (`/calendar?day=N`), so two private copies were two ways to answer one question. And
`fmtCountdown` grew a day unit: the week view legitimately counts down to something six days out,
and `152h 12m` is a number the reader has to divide.

✅ **`tests/calendar.spec.ts` — 11 checks, and 10 of them were WATCHED TO FAIL against the page at
`HEAD`.** The 11th passed there and was kept deliberately: it pins the half of the error rule that
was always right (an error with no data may take the page), and a rule stated in one direction only
is the one that gets "simplified" back. ⚠ **This suite needs NO BACKEND** — only the dev server —
because the calendar reads one endpoint, so intercepting it whole makes the suite runnable without
the SSH tunnel or the live MT5 box. **Prefer that shape for a new suite whenever the page allows
it**; `overview.spec.ts` needs the live snapshot and is the exception, not the model. ⚠ Two traps
the spec had to learn: **the page OPENS ON TODAY**, so a fixture built on a fixed weekday renders
empty on every other day of the real week (pass `?day=` explicitly), and a **`focus` event does not
force a refetch** — the app's global `staleTime: 30_000` skips it, so a poll failure has to be
driven by fast-forwarding the clock past the 45s interval.

### The two filters that were applied without being visible

**Closed the same day, after the nine above.** Both were measured and recorded as *not worth
changing* first, then done properly rather than left as a note — a known gap in a filter row is a
thing somebody comes back to, and neither cost much.

🔴 **A `NONE`-impact row was governed by a rule with no control.** `IMPACTS` held the three visible
levels and `passFilters` read `impactAll || enabledImpacts.has(...)`, where `impactAll` meant *all
three ticked* — so unticking **Low**, a different level entirely, silently took every unrated row
with it. `NONE` is a level like the others now, and its chip renders **only when the loaded week
contains one**: a control for a state that cannot occur is UI nobody can read, and one that appears
the moment the state does is the honest version of both. ⚠ **The level stays in `enabledImpacts`
whether or not its chip is drawn**, so an unrenderable row is never hidden by its own absence.
(MEASURED: zero NONE-impact events in 2,000 real ones — TradingView's `importance` is always
1/0/−1. That is why this was latent, and exactly why it was worth closing rather than noting.)

🔴 **The currency chips were a hardcoded nine beside a comment saying they mirrored the backend.**
Two statements of one claim, and **not even in the same namespace**: the feed is QUERIED by bloc
code (`US`/`EU`/`GB`) and ANSWERS with an ISO currency (`USD`/`EUR`/`GBP`), so the frontend could
never have derived it and a tenth bloc would simply never have got a chip — a currency present in
the rows and absent from the filter, which reads as a quiet week. `useCalendarCurrencies()` →
`GET /calendar/currencies` now serves it, mapped backend-side. ⚠ **A SEPARATE query from the week,
deliberately** — the roster is a property of the backend's configuration, not of any week, so
folding it into the calendar payload would make the chip row vanish whenever a week was loading or
had failed, and **a filter you cannot see is still a filter that is applied**. ⚠ **A currency held
in the URL but missing from the roster is still offered**, or a stale bookmark filters with no way
to clear it — the same rule `categoryMissing` follows one control over.

**4 new browser checks (15 total), all 4 red against the page at `HEAD`** — though be precise about
the last one: it asserts the three-chip default, which was already correct, and failed there only
because its `data-testid` did not exist. It is kept to pin that half, not claimed as a catch.

The backend half — the beat/miss polarity list that had been written for the wrong provider, the
HIGH-impact inflation print it coloured backwards, and the currency-roster mapping — is in
`../backend/CLAUDE.md` → *The calendar's polarity list was written for the wrong provider*.

## The Overview was audited 2026-08-05, and its job was to be WRONG quietly

**Read this before adding anything to `pages/Overview.tsx`.** It is the first page anybody opens
and the only one whose entire purpose is *is anything wrong*. Eleven defects came out of one
pass, and the shape they share is the point: **not one of them showed an error. Every single one
rendered a confident, healthy-looking answer** — which is the worst possible failure mode for the
page a reader checks precisely so they don't have to check the others.

🔴 **A DISABLED scheduled job wore the gold "Scheduled — waiting for next trigger" pill.** `JobPill`
branched on `RUNNING` vs everything-else, so a task that will never fire read as covered. **Two of
the three jobs on the live box are disabled right now** (P&L Tracker, Reporter). The Bots page's
`JobDot` had handled this for months, *with a comment saying a gold dot on a dead task is worse
than no dot at all* — and this page did the exact thing that comment forbids. Both now carry the
same three branches and the same tooltip wording. ⚠ **`STOPPED` correctly KEEPS the gold pill** —
a scheduled task not executing at this instant is healthy; only `DISABLED` is the lie.

🔴 **A bot that was RUNNING and BLIND read as a healthy fleet.** The page never looked at
`mt5_link`, so the 2026-08-04 incident (MetaTrader auto-updated under the live bot and it sat
blind for 50 minutes) would have shown `1 / 1 · all bots live` in green here, while the Bots page
one click away drew its `No MT5 link` chip. The chip is on both pages now. ⚠ **The stat card's
blind branch is tested BEFORE every healthy branch**, because a blind bot *is* running and any
other ordering lets the cheerful string win the tie.

🔴 **`balance ?? 0` folded "this bot could not tell me" into the fleet total as a real zero.** Same
*no data ≠ cannot ask* rule as the chip above, one card to the right. It sums only what was
reported and says `1 of 2 not reporting` in `warn` for the rest.

🔴 **A failed refetch rendered the error banner AND the last good rows, undated.** TanStack keeps
`data` through a failed background refetch, so "VPS connection failed" sat above bot rows still
saying RUNNING, with `snapshot.fetched_at` never drawn anywhere. Stale rows are now dated
(`showing the snapshot from 22:49`) — verified by waiting out the real 60s poll with the endpoint
failing.

🔴 **The calendar window was `useMemo(…, [])`, so a dashboard left open past Sunday midnight asked
for LAST week for ever** and read *"No more events this week"* while the Calendar page, which
recomputes per render, was right. ⚠ **This is the standing lesson and it is not this folder's
label-vs-code refrain: a value derived from the CLOCK cannot be memoized on mount.** The window is
recomputed every render now (it is two `Date` calls) and the second tick from `useServerClock`
is what carries it over the boundary. **Proved with a faked clock rather than argued** — parked at
23:59:50 Sunday, fast-forwarded 30s, and the page asks for the new week with no reload; the same
test run against the old code stays pinned to the old week, which is what makes it a test.

🔴 **`server_now_ms` was read straight from the response, so "now" froze between polls** — the
countdown sat still and a fired event stayed listed as upcoming for up to 45s. `useServerClock`
(in `hooks/useCalendar.ts`) holds the server/browser OFFSET and ticks every second. **It is shared
with the Calendar page, which had its own copy** — two surfaces disagreeing about the present is
how one says "in 2m" while the other has already dropped the event.

Also fixed, each a smaller instance of the same thing: a **calendar fetch error rendered as
"Loading…" for ever** (`isError` was never read); **`0 / 0` bots read "all bots live"** because
`runningBots === totalBots` is true at zero; **"best PF" ranked runs with no sample floor**, so two
trades at PF 8.0 outrank two hundred at PF 2.0 (`MIN_TRADES_FOR_BEST = 30`, the optimizer modal's
own default and its own reasoning, with the trade count now printed beside the ratio); **a running
BACKTEST announced itself nowhere** while optimizations and stress tests each had a banner; **the
event grid rendered empty** when the only upcoming event had been promoted into the callout; the
week end was `from + 7 × 86_400_000`, which is an hour wrong across a **DST** changeover; and rows
were keyed by `bot.name` instead of `bot.key`.

**Two things this audit did NOT do, and both were nearly done wrongly:**

- ⚠ **The Overview does not add polling for runs / optimizations / stress tests.** The first draft
  of this audit called that out as the page's own cost. It is not: **`Sidebar.tsx` is always
  mounted and already holds those three cache entries**, so the Overview's hooks are free. The
  calendar poll IS the page's own, and it dropped to 5 min via `useCalendar`'s `refetchMs` — the
  preview shows a title, a time and an impact dot, none of which change once an event is published.
- ⚠ **The `/backtests/runs` list ships every run's full `params` dict and `verdicts`** (~1.7 KB per
  run, measured). That is real, and it is the **Sidebar's** cost on every page, not this one's — so
  it needs its own measurement and its own change, not a drive-by here.

**Verified in a real browser at 1670×940 — 25 checks, all passing**, most of them against mocked
snapshots for the states the live box cannot produce today: a blind bot, a bot with no balance, a
two-bot fleet reporting partially, an empty fleet, a VPS that dies after a good snapshot, a dead
calendar feed, and a week with exactly one event left. Frontend typechecks and builds.

**A second pass covered what the first one had not, and it found a 12th defect at every width
including the one already "verified".** Worth reading as a lesson about what a browser check
actually covers: the first pass drove the things it had CHANGED, so it never asked the page a
question it had not already thought of.

- 🔴 **The calendar event grid overflowed its own container by exactly 6px at 1670, 1280 and
  1024.** The rows carried `-mx-[6px]` for their hover fill, and **a grid ITEM cannot take a
  negative margin without escaping its track** — a track is sized before the margin applies. The
  bleed moved to the container and the rows took `min-w-0`. Pre-existing (`a10598e`), not a
  regression, and invisible at a glance because 6px of bleed hides inside the card's 15px padding.
  ⚠ **`NavStatRow` and the other rows use the same `px-[8px] -mx-[8px]` idiom safely** — they are
  block children, not grid items. The idiom is only wrong inside a grid.
- **The Smart Money branch was rendered with the flag flipped ON**, because `relativeTime` gained
  an argument that ONLY that branch calls and **a typecheck is not a render**. Both grids take
  their 4 / 3 columns, the age reads `65d ago`, no console errors. ⚠ A flagged-off branch is
  exactly the code a compiler will bless and nobody will run.
- **The 1s clock ticker was MEASURED, not assumed** — it is a cost this change introduced, so it
  does not get to be free by assertion. **44ms of scripting per 10s wall clock (0.44%)** against a
  1ms baseline on `/rulesets`, layout and style both 0ms. The heavy per-run derivations are behind
  `useMemo` on `[backtestRuns]` / `[stressTests]`; keep any new one there or the ticker starts
  paying for it every second.
- **The DST week was paged to** (`?week=12`, US fall-back on 2026-11-01): the window spans a real
  **169h**, where the old `from + 7 × 86_400_000` gave 168h and quietly dropped the last hour of
  that Sunday.

## Browser tests — `npm test`, and what deliberately is NOT in them

**Added 2026-08-05.** This folder had no test runner at all: the convention was "verify it in a
real browser", done by hand, which is why the Overview's twelve defects each survived until
somebody looked. `@playwright/test` + `tests/*.spec.ts` keeps those checks runnable —
**25 tests, ~3.5 min**, run with `npm test` from `frontend/`.

**`tests/tuning.spec.ts` (8, ~19s) — added 2026-08-05 with the Tuning workbench audit, and it was
WATCHED TO FAIL before it was kept.** Every one of the 8 fails against the page as it was at
`HEAD` and passes against the fix; a suite written after a fix and never run against the defect is
a description of the fix, not a test of it. Same mock discipline as the Overview's: the leaderboard
states that cannot be produced on demand — a grandchild, a sweep child wearing a tweak's
`source_run_id`, a 3-trade fluke at PF 99 — are built by MUTATING the real runs list and the real
run detail. ⚠ **Scope table locators to `.first()`**: the per-regime table further down that page is
also a `tbody` of rows whose second cell is a number, and an unscoped `td:nth-child(2)` silently
picks up three extra rows.

⚠ **It runs against the RUNNING app** (`./start.sh` first — backend on `:8000`, dev server on
`:5173`), and `playwright.config.ts` deliberately has **no `webServer` block**. The backend here
talks to a live VPS and a live MT5 terminal, so a runner that boots it on demand is a runner that
can start things on the trading box. Starting it stays a person's decision — the same reasoning
`test_integration.py` is deselected under.

⚠ **`workers: 1`, `retries: 0`.** The tests intercept API routes and one installs a **fake clock**;
parallel workers would be several browsers disagreeing about what time it is. And a retry that
turns a real flake green is how a broken page ships.

⚠ **Mocks MUTATE THE REAL SNAPSHOT rather than hand-writing a fixture** (`mockSnapshot`). A
hand-written fixture drifts from the backend's model and then pins a shape the server never sends
— which is a test that passes while the page is broken.

**Two things were verified by hand and are deliberately NOT committed as tests:**

- 🔴 **The Smart Money render, which needs `FEATURES.smartMoney` flipped ON.** The one-off check
  did that by REWRITING `lib/features.ts`, and **a committed test that edits a source file is a
  hazard, not a test** — a crash mid-run leaves the flag on and Smart Money silently returns to
  the nav. It was run manually (both grids take their 4 / 3 columns, `relativeTime` reads
  `65d ago`, no console errors); re-run it by hand after touching anything that branch calls.
  ⚠ **The general point: a flagged-off branch is exactly the code a compiler blesses and nobody
  renders** — `relativeTime` gained an argument that only that branch passes, and a typecheck is
  not a render.
- **The 1s ticker's cost**, measured through CDP `Performance.getMetrics`: **44ms of scripting per
  10s wall clock (0.44%)** against a 1ms baseline on `/rulesets`, layout and style both 0ms.
  A one-off measurement, not a threshold worth asserting on every run.

⚠ **Two API facts the suite had to learn the hard way, and both will mislead the next test:**
`main.tsx` sets a global **`staleTime: 30_000`**, so navigating away and back does NOT re-fetch
inside 30s (measured: the mocked route was hit exactly once), and **`page.goto` is a full page
load** that destroys the query cache entirely. Any test about *stale data still on screen* must
therefore wait out the real poll — which is why one test is 65s and says so.

## Decided 2026-08-05: the Overview does NOT get its own health strip

Asked for and declined, and the reasoning is the reusable part. `SystemHealthStrip` already
renders API / SSH / NT8 / MT5 in the **sidebar**, which is on screen on the Overview and every
other page. A second rendering of those four dots would be **two readings of one claim** — this
repo's most-repeated failure, and the exact argument that made the Bots page's fleet strip share
one `versionFlags` derivation. A health strip that disagreed with the sidebar six inches away
would be worse than no strip.

⚠ **`GET /system/readiness` is a different question, and THAT one the Overview does answer**
(built the same day, `useReadiness` → the warning block above the stat row). It reports the
dependencies whose failure mode is SILENCE — an un-backfilled news calendar makes the News &
Holiday filter tag zero trades, missing credentials make every Telegram send a no-op — and
neither raises, neither turns a dot red, and neither was visible anywhere in the app. That is
the opposite case from the health dots: not a second copy of something already on screen, but
the only copy of something that was on none.

- ⚠ **It renders ONLY when `warnings` is non-empty.** A card reading "all dependencies OK" is a
  permanent green tick, and a permanent green tick teaches the reader to stop looking at that
  spot — which is fatal for the one row that must be read on the day it finally speaks.
- ⚠ **Polled at 5 min with a 2 min `staleTime`**, not the usual 30s: it reads the whole news
  event store (~0.3s measured server-side) and its answer changes when somebody runs a backfill,
  not minute to minute.
- Rows are keyed on the message, because the backend returns bare sentences with no ids and the
  sentence IS the finding.

## The sidebar stopped pulling three lists to draw three dots

**2026-08-05.** `Sidebar.tsx` is mounted on every page, and `activeByRoute` derived its three
running-dots client-side from `useBacktestRuns()` / `useOptimizations()` / `useStressTests()`. So
merely having the app open polled the full runs list — **measured 1.69 KB per run, two thirds of
it the 54-key `params` dict**, ~137 KB at 81 runs — to answer three yes/no questions. It reads
`useNavActivity()` (`GET /system/activity`, 62 bytes) now.

⚠ **The predicates moved to the server and are no longer visible beside the dot they draw.**
`lab_db.get_nav_activity` is the only statement of them and `backend/tests/test_nav_activity.py`
pins each one — an optimization COMBO must not light the Backtests dot, sweep and stack children
must, and a stress test is `running_wf` / `running_sens` for most of its life. **Change one side
and change the other in the same commit.**

⚠ **This is NOT the same question as `useRunningVpsJob()`** — that partitions by PLATFORM (is NT8
/ MT5 / python free to take work) and this partitions by NAV SECTION (is this part of the app
busy). Do not merge them: an MT5 optimization belongs to `mt5` there and `optimizations` here.

⚠ **The runs list itself was NOT trimmed, deliberately.** Dropping `params` from it was measured
and rejected — `TuningWorkbench` genuinely reads it off the list for per-iteration deltas, so a
conditional field would make `params: {}` mean both "not requested" and "none exist", landing in
the tune page as a confident "no parameters changed". Same *no data vs cannot ask* rule as
`mt5_link`. The pages that render those lists still fetch them; only the sidebar stopped.

Also decided, and recorded so nobody "fixes" it: **"best grade" and "N robust" span ALL stress
tests ever, on purpose** (Aaron's call). They are a *has this lab ever produced something solid*
reading, not a recent-form one. **`MIN_TRADES_FOR_BEST` is a different thing and stays** — a
sample floor is about whether a number means anything, not about how far back it looks.

## A blank cell is not a diagnosis — the Bots page's `No MT5 link` chip

**Added 2026-08-04, and this page was the ONLY place the incident was visible.** MetaTrader
auto-updated itself on the VPS and restarted, taking the running bot's connection with it. The bot
stayed alive and kept stamping its heartbeat — so the watchdog saw a healthy bot, the process list
still had it, and this row said **RUNNING** — while it received no bars for 50 minutes across an
open session. The one thing on screen that reflected any of it was **an em-dash in the Balance
column**, which is also what a bot that has simply not reported yet looks like.

`BotStatus.mt5_link` is the fix, and the rendering rules are the interesting part:

- **The chip sits BESIDE the Running pill, it does not replace it.** Both facts are true at the same
  time and they are different questions: the process is ALIVE (so restarting it is the fix, and the
  watchdog was right not to fire) and it is BLIND (so it is taking no trades and managing none).
  Collapsing them into one word loses whichever half the reader came for.
- **`=== false`, never falsy** — same rule as `mt5_connected` above, in the same file. `null` means
  the bot has not stamped a link state (stopped, or predating the field), which is not the claim
  "disconnected", and painting a healthy bot as disconnected is the identical mistake in reverse.
- **The balance cell says `no link` in `warn` rather than the em-dash**, so the two causes of a
  missing number can never look the same again. The em-dash survives for the genuinely-unknown case.
- **The tooltip states what happens next** ("retries every 30s; if this persists, restart the bot"),
  because the runner self-heals and a warning with no action reads as something the reader must fix.

**The transferable rule, and it is not this folder's usual label-vs-code one:** every layer under
this cell behaved defensibly on its own — an empty bar frame is a fine thing for a data call to
return, and a null balance is a fine thing to write when you have no balance. The defect was that
*"no data"* and *"cannot ask"* were the SAME VALUE at every hop, so by the time it reached the
browser the distinction did not exist to render. When a cell can be empty for two reasons, the API
has to say which.

## The affirmation ribbon, and why it holds still

**Built 2026-08-03, Aaron's request.** Six affirmations rotate in the top bar, one every 20 seconds.
The list is the `AFFIRMATIONS` array in `components/TopBar.tsx` — edit that and nothing else, since
the rotation reads its own length. They render uppercase on one line that never wraps, so roughly 40
characters is the ceiling before a narrow window clips one.

**The Refresh button moved to the sidebar footer to make room** (`Sidebar.tsx` → `RefreshAll`, styled
as a peer of Settings and collapsing to an icon like every other row). Refresh-everything is a global
action, so the global nav is an honest home for it, and the top bar's width was the only space in the
shell wide enough to hold a sentence.

**The animation is deliberately front-loaded, and the brief is the reason.** These are meant to
register subconsciously, which rules out the obvious treatment: a looping shimmer or a pulsing glow
stops being SEEN within minutes — the eye adapts to steady motion and files it as background — and
until it does, it competes with the numbers the page is actually for. Looping motion reads as
decoration; motion that finishes reads as intent. So the whole budget goes on the ARRIVAL — words
fade up 75ms apart, so the line assembles at the pace of a voice saying it and the eye travels along
and READS it rather than glancing at a block that appeared — and then it holds perfectly still for
its full turn. Still, bright and identical every time round is what repetition needs in order to
encode. The exit is a plain fade, duller than the entrance on purpose: two ends competing for
attention would make the change feel like an effect.

Four things that will break it if they are changed back:

- **`-webkit-background-clip: text` is not usable here, although the wordmark beside it uses exactly
  that.** The clip silently stops working when the same element also carries a `transform` — and this
  line moves on every change — at which point the gradient floods the whole box and the transparent
  letters vanish inside it. What you see is a solid gradient BAR where the text should be, which is
  how it shipped twice during the build. The ribbon paints a flat colour instead, and the word-by-word
  entrance would have forced that anyway: a gradient can span the whole line or restart per word, and
  neither survives animating each word on its own.
- **The rAF that starts the entrance needs the timer beside it.** `requestAnimationFrame` does not
  fire in a BACKGROUND tab while the timers driving the rest of the cycle keep running, so on rAF
  alone the ribbon parks in `enter` — fully transparent — until the tab is looked at again. The 80ms
  fallback is the fix for a real stall, not belt-and-braces.
- **It is `absolute inset-0` across the whole bar, not a flex child.** Laid out in the row it centres
  in the space LEFT OVER beside the wordmark, which is visibly right of centre. The two therefore
  overlap at narrow widths: the wordmark carries `z-10`, and the type steps down from 22px to 17px
  below 1280px so the longest line still clears it.
- **One node shows one affirmation.** The three phases (`enter` → `in` → `out`) reuse a single
  element rather than crossfading two copies, so a stalled timer can never leave the bar reading two
  things at once.

Verified in headless Chrome at 2.5s and at 25s — message 1 then message 2, which is what proves the
rotation advances rather than the first line simply sitting there. That check is also what caught the
background-tab stall.

## Key UI decisions

**Platform-based job lock** — `GET /backtests/running-job` returns `{ nt8, mt5, python }: RunningJobInfo` (polled at 5s via `useRunningVpsJob()`). All three lock independently. **Never branch on `runner === 'mt5'`** — that conflated two different questions (which lock scope? is this NT8-only UI?) and silently gave Python jobs the NT8 badge and the NT8 lock. Resolve both through `lib/runner.ts`: `runningJobFor(runningJob, runner)` for the lock (`jobBlocked = !!runningJobFor(runningJob, run.runner)?.running`), `isNt8Runner(runner)` for NT8-only UI (futures contract months, prop-challenge rulesets, injected foundational params, the NT8 chart export), `runnerMarket(runner)` for forex-vs-futures ruleset filtering (MT5 and Python are both forex), and `runnerScope`/`RUNNER_LABEL`/`RUNNER_FULL_LABEL` for display. It mirrors the backend's `_SCOPE_RUNNER_SQL`, including NT8 as the fallback for unknown runners. Lock surfaces: `RunBacktestModal`, `OptimizeButton`, `Tier3WarningModal`, `RunRow` retry, `BacktestDetail` retry/rerun. `Strategies.tsx` calls `useRunningVpsJob()` at page level (result unused) to keep the cache warm — without this, the first modal render sees `runningJob = undefined` and treats the lock as clear. All six job-lifecycle mutations invalidate `['lab', 'running-job']` on success. `BacktestSummary.runner` must be mapped in `_row_to_summary` or `run.runner` is undefined on the frontend. The backend `get_running_job()` correctly routes MT5 optimizations to the `mt5` bucket (joins `strategies` on runner) — a running MT5 optimization does NOT set `nt8.running`.

**Optimization running indicator** — `OptimizationNestRow` shows a pulsing gold dot (`w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse`) when `opt.status === 'running'`. The parent `RunRow` does NOT show an "OPTIMIZING" badge — the dot on the sub-row is the only running indicator. MT5 optimizations emit live `completed_count`/`total_count` per combo; the sub-row counter (e.g. "35/36 runs") reads these from the optimization record's `completed_runs`/`estimated_runs`.

**Tab-specific active dots** — each Backtests tab has its own pulsing dot logic (not "any job running"): `runsActive = allRuns?.some(r => !r.sweep_id && r.status === 'running')` (includes opt-combo full backtests while running). `sweepsActive = allSweeps?.some(s => s.status === 'running')`. `optsActive = allOpts?.some(o => o.status === 'running')` — only fires when an actual optimization grid is running, NOT during a single-combo full backtest (`retry_single_optimization_run` uses `set_running=False` so the optimization stays `complete`). Running opt-combo full backtests appear in the Runs tab filter (`!r.optimization_id || r.status === 'running'`) with their OPT chip visible, then disappear once complete.

**Runs table columns** — "Score" = WorthinessBadge (Tier 1/2/3, the quality verdict; the `WorthinessLegend` "Score key" above the table explains the tiers). "Trades" = `run.trade_count` for at-a-glance volume. "Challenge" = firm name chip(s) showing which challenges the run was evaluated against. Score and Challenge are intentionally separated: score = how good, challenge = under what rules. Per-firm PASS/WARN/DISCARD detail lives only on BacktestDetail. There is **no Status column** — run status is a small `RunStatusIcon` glyph after the strategy name (running = pulsing accent dot, failed = red ✕, complete = green dot); a finished run is otherwise self-evident from its populated metrics. Nested rows (optimization/sweep/tune) keep their own status pill and still span `colSpan={12}` (column count is unchanged: Status removed, Trades added).

---

## The Tuning workbench — audited 2026-08-05

`pages/TuningWorkbench.tsx`. Edit a completed run's params, fire an iteration, compare the children
against the baseline in a leaderboard + equity overlay + per-regime table. Route:
`/backtests/runs/:runId/tune`.

**Everything on this page is a COMPARISON, and that is the frame for every rule below.** A number
here is never read on its own — it is read as a difference from the baseline — so anything that
makes the child and the parent incomparable is a defect even when both numbers are individually
correct. Both of the audit's worst findings were of exactly that shape, and both were invisible
unless you checked a child against its own parent.

### The iteration is measured on the baseline's physics

`runIteration` carries `cost_layers`, `broker_profile`, `sizing_mode` and `manual_risk_pct` off the
baseline's detail, alongside the window and the legacy `commission_per_side`/`slippage_ticks`. It
sent only the last two until 2026-08-05, so an iteration off a charged run ran **free** and the Δ
column blamed the param for the difference.

MEASURED against the live backend, same params, same window, same strategy — one iteration fired
with the new body and one with the old:

| body | layers stored | PF | net P&L | trades |
|---|---|---|---|---|
| new (costs carried) | `['spread','swap']` | 1.499 | $3,157.33 | 17 |
| old (no cost fields) | `[]` | 1.581 | $3,646.75 | 17 |

**Trade counts identical at 17** is the check that the charge is real and correctly placed: spread
and swap change what a trade MAKES, never whether it happens. A row where the count moved would
mean something else had changed.

⚠ **`cost_layers: null` on the baseline is sent as `[]`, never as `null`.** `null` means "a run
written before layered costs existed" — a contract a NEW run cannot be created under — and `[]` is
its honest equivalent, charging exactly the same nothing. The distinction still matters everywhere
it is READ; it just has no meaning on the way in.

⚠ **The panel STATES what it is carrying**, above the Run button (`no costs charged` / the layer
names + broker, and the sizing mode). The fix and the caption landed together on purpose: a page
that silently inherits is one refactor away from silently not inheriting.

### Everything the request sends and the button promises comes from ONE key set

`knownParams` = the baseline's own params ∪ the current schema. The changed-count on the button, the
dot on the collapsed panel and the params in the request are all filtered through it, so the button
can never promise a change the request then drops. It only ever bites on a `sessionStorage` edit for
a param that has since disappeared — and a request carrying an input the runner does not declare is
worse than a dropped edit, because MT5 treats a set file with an unknown input as mismatched and
silently runs a single backtest instead.

### Edits are persisted, not guarded

`sessionStorage`, keyed per baseline run, cleared when the edits are spent. Clicking a leaderboard
row to inspect it is the common way to leave this page, and losing the form was the complaint —
**persistence rather than a navigation-guard dialog, because nothing lost means nothing to warn
about.** Reset is enabled whenever an edit is HELD, not only when one differs from the baseline: a
value typed and typed back is still an edit sitting there, and greying out the only way to clear it
made the button look broken.

### The leaderboard ranks, the ★ has a floor, and Max DD is a percent

- **Sorted by profit factor**, because that is what the caption says. Rows with no PF (running,
  failed) sink to the bottom, newest first.
- **`MIN_STAR_TRADES = 10`**, and the caption names it. A PF off a handful of trades is not a
  measurement, and a threshold nobody can see is indistinguishable from a bug when the obvious
  winner has no star. The **Trades delta is uncoloured on purpose** — fewer trades is not worse, it
  is a different sample, and it is the number to read before trusting a ★.
- **`max_drawdown_pct` leads, dollars beneath.** Same rule as the Runs list (2026-08-01): a dollar
  drawdown beside a compounded profit reads an order of magnitude too small. A **negative value is
  the backfill's "measured, no answer" sentinel** and is never rendered — the cell falls back to
  dollars. Deltas are in percentage points when both sides have a percent, dollars otherwise, and
  the two are never mixed.

### Iterations are DESCENDANTS, and `source_run_id` is not exclusive to tuning

The tree is walked breadth-first with a seen-set (a cycle cannot hang the page), so tuning an
iteration keeps the grandchild on the page that compares it. ⚠ **A sweep or an optimization launched
from a run stamps `source_run_id` too**, so both are excluded by their own ids — before this they
would have shown up here as tweaks. Stress-test children never reach the client (`list_runs` filters
them server-side).

### Colours come from creation order

The palette is assigned by `created_at` among the iterations, not by table order. Table order moves
— a finishing iteration re-sorts the leaderboard — and colouring off it meant **every line on the
chart swapped colour underneath the reader** whenever a run completed. Creation order never changes
for a run that already exists.

### The payload: fetch the timeline once

Each run's detail is 137 KB and `regime_timeline` is 96 KB of it (measured, 165-trade run) — the
same full calendar for every run in the window, and the chart bands off exactly one copy. The
baseline is fetched whole; the iterations go through **`GET /backtests/runs/{id}?timeline=false`**
(49 KB). Two guards, both load-bearing:

- **Only slimmed when the BASELINE actually carries a timeline.** A run completed before the backend
  emitted one falls back to the iterations' own sparse tags, and slimming would leave the chart with
  no bands at all.
- **Cached under `['lab','run',id,'slim']`, never `['lab','run',id]`.** That key belongs to the run
  page, which renders the timeline; handing it a stripped copy would blank the bands over there
  instead. Prefix invalidation still reaches both.

### Smaller things worth not undoing

- The fullscreen chart's height is **measured with a `ResizeObserver`**, not read once from
  `window.innerHeight` — same pattern as BacktestDetail's fullscreen panel. The inline chart
  unmounts while fullscreen is open, so there is only ever one live chart.
- The baseline's `dot`/`activeDot` renderers are **memoised**. Recharts repaints every dot when the
  prop is a new function, so a keystroke in the param editor was redrawing 165 markers.
- Runs are named by **what they changed** (`exec_tp1_pct=40 · exec_tp2_pct=30 +2`) in the chart
  legend, tooltip and regime headers — a `Tweak 15f0122a` in a legend tells the reader nothing. The
  table's Run cell keeps the short form, because the Changes column beside it already spells out
  old→new.
- **A loading chart says so.** "No completed runs to chart yet" was rendered during the fetch, which
  is the state that arrives on every single visit.
- ⚠ **One audit finding was wrong and is recorded as wrong: `copyChartAsPng` already toasts on every
  failure path.** The call site ignoring its boolean is not a silent failure, and a second toast
  would have double-reported it.

---

## The Optimizations page — audited 2026-08-04, and it had never been run

The `optimizations` table was **EMPTY** when this audit ran. That is the frame for everything
below: the page had never been driven end to end, so every defect was latent rather than
corrupting data, and none of them had been caught by use. The backend half is in
`../backend/CLAUDE.md`; this section is the UI half.

**What a reader could not see, and now can.**

- **Winner robustness** (`RobustnessCard`). The backend has computed `grid_sensitivity_score`
  on every native optimization since that pass landed, and stored it, and **nothing rendered
  it** — the one number a parameter sweep exists to produce was the one number the page did not
  show. 0 = the settings either side score the same (a plateau you can trade); 1 = they
  collapse (a lone spike, i.e. a number fitted to this history). The per-param breakdown prints
  each neighbour's PF and its % drop.
- **`BaselineRow`** — the run the optimization was launched FROM, beside the winner. Without it
  the grid is a ranking with no reference point: you can see which combination won and not
  whether it beat the settings you already had, which is the only question that decides whether
  to adopt it. It reads `opt.source_run_id` through `useBacktestRun`.
- **`winner_note`** — an amber banner when the ★ was picked by a FALLBACK rather than by the
  rule the chips above it name (an empty regime-filtered population, a trade floor that
  excluded everything). Falling back is right, because an optimization with no winner is
  useless. Falling back *silently* is this repo's signature defect.
- **A costs chip.** A grid ranked on a free book is not comparable to a priced run, and nothing
  said which one you were looking at. ⚠ `cost_layers === null` ("not recorded", a row predating
  layers) and `[]` ("none charged") are worded **differently** on purpose.

**Things that were true on screen and wrong.**

- `useElapsed` returned a number for a finished run with no `completed_at`, counting up from
  `Date.now()` — so a failed optimization read `Ran for 74h` and kept climbing. It returns
  `null` now and the page draws `—`. The backend stamps `completed_at` on failure too.
- `fmtOptStatus` labelled `failed_cancelled` as **Failed** on the list page while the detail
  page said **Cancelled** for the same row. One row, two words. `fmtOptStatus` gained the case.
- ★ fell back to `i === 0` when `bestRunId` was absent, so with the table sortable the star
  followed the sort and appeared to crown a different combination. **★ is the winner the
  BACKEND chose, or nothing.**
- The Retry-N-failed button rendered *while running* too. `retry-failed` calls
  `ensure_platform_idle`, and the running optimization IS the job holding that platform, so the
  request could only ever 409 — a button whose single outcome was an error toast. Removed;
  cancel first, then retry.

**Two toasts, and the useful one was the one thrown away.** Every optimization mutation's
`onError` read `(e as {detail?: string}).detail` off an error that never carried it, so the
branch could not fire and a generic message toasted **on top of** the one `api.request` had
already shown. `api/client.ts` now throws **`ApiError`** (carrying `status` + `detail`) and the
optimization hooks have **no `onError` toast at all**. ⚠ The rule: `request` owns the message;
a hook's `onError` is for BRANCHING on a reason, not for restating it.

**Modal (`OptimizeButton.tsx`).**
- Go is blocked on `comboIncomplete` and on `rangeErrors` (step ≤ 0, max below min). Both used
  to render as `— combos` with Go still enabled, so the run started and died minutes later.
  `rangeProblem()` distinguishes *still typing* from *finished and wrong* and names the param.
- **Cost layers are inherited from the source run** and stated in the modal. Without this the
  whole grid was ranked on a free book and its winner compared against a priced run — two
  numbers produced under different physics, presented as a comparison.
- **`min_trades` (Minimum trades to win)**, defaulted to **30 in the modal** and **0 in the
  API**. Profit factor has no opinion about sample size, so two lucky trades at PF 8.0 outrank
  two hundred at PF 2.0. ⚠ The split of defaults is deliberate: nothing is assumed of a caller
  that states nothing (the 0/0 commission rule), and the modal's 30 is *visible and editable*,
  which is what keeps it from being a silent narrowing. A combo under the floor still runs and
  still shows — dimmed — it just cannot be ★.
- A **runtime estimate**, from the source run's own measured duration × combos ÷ cores. ⚠
  **Python only.** A python sweep replays the same bars this run replayed on this box; NT8 and
  MT5 load data once and parallelise inside their own tester, so per-combo cost there is not
  this run's cost and no estimate is offered rather than a wrong one.

**Payload and render.** The detail endpoint now ships only the **grid's own** param keys per
combo (a combo's stored params are fixed+swept, 50+ keys on a Python strategy), the table and
bar chart sorts are `useMemo`'d, and both pages stopped pulling the **entire** lab run list —
`OptimizationDetail` scopes it to `{ strategy_id }`, and `Optimizations` dropped it outright
(it fetched every run to choose between two empty-state sentences that said the same thing).

**List page.** Runner, winner (with a ⚠ when a `winner_note` exists), and start time are
columns now; Firm prints a short name instead of the raw `lucidflex_50k_eval` slug; the Method
column went (every new optimization is `native`).

---

## ProgressCard pattern (SweepDetail / OptimizationDetail)

Both detail pages use an identical `ProgressCard` sub-component with:
- Left: status icon + label + segmented progress bar + counts
- Right: elapsed/duration timer (`useElapsed` hook) + Cancel button (while running) + Retry-N-failed button (when not running)
- Inline warning when failures accumulate during a run

**Terminal color scheme** (matches Smart Money terminal aesthetic):
- Complete (no failures): `border-accent/20 bg-accent/5` background, `text-accent` status label + icon, `bg-accent` progress bar, `text-accent` count
- Instrument/combo done pills: `border-accent/25 bg-accent/10 text-accent`
- Failed/partial: unchanged (red/amber)
- Running: unchanged (cyan spinner, already matched)

`useElapsed(startIso, endIso, running)` — counts up live when `running`, freezes at final duration when done, and returns **`null`** when a finished job has no `completed_at` (the caller draws `—`). ⚠ It must never fall back to `Date.now()` for a finished job: a failed optimization then reads `Ran for 74h` and keeps climbing, which is how a job that died on Tuesday looked like a job still running.

Per-row retry in `FailedRunsTable`: a `RotateCcw` icon button calls `useRetryBacktest().mutate(run.run_id)`. Spinner activates on the specific row via `retryRun.variables === run.run_id`. `e.stopPropagation()` prevents the row-click navigation from firing.

---

## Strategy deployment manager

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). The modal has a status-icon header (`StatusIcon`: spinner / green check / red X) + one-line summary, a body capped at `max-h-[85vh]` that scrolls, and a pinned footer. While running it shows staggered pulse **skeleton rows** (no second spinner) shaped like the result rows that replace them. On completion it renders the real `job.errors` / `job.warnings` **text** — not just counts — via `CompileSection` (color-coded, numbered, monospace lines: red `neg` for errors, amber `warn` for warnings); warnings show even on a successful compile. The elapsed counter ticks every second from a **local `setInterval`** (anchored to `started_at`, freezing at `completed_at` when done) — without it the count only advanced on each poll and visibly jumped. Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `orphans: string[]` (DB strategies whose source file is gone) + `warnings: string[]`; `ReconcileResult` carries `removed: string[]` + `warnings: string[]`.

**Scan vs Reconcile (bidirectional delete).** Scan is read-only: `useScanStrategies` (`POST /strategies/scan`) adds/updates and its success toast flags the orphan count (`N orphaned (source deleted — use Reconcile)`). Deleting a source file from the repo propagates to the DB row + the deployed VPS file ONLY through an explicit action: `useReconcileStrategies` (`POST /strategies/reconcile`). On the `Strategies.tsx` header, a red **Reconcile (N)** button appears next to Scan **only when the last scan found orphans** (`scan.data?.orphans`), fronted by the shared `ConfirmDeleteModal` (imported from `pages/Backtests`) listing exactly which strategies will be removed. On success it invalidates `['lab','strategies']` + the strategy-files / sync-status keys, and surfaces any per-strategy VPS-delete warnings as error toasts. The per-strategy Delete button uses the same backend `remove_strategy` path. See backend CLAUDE.md "Bidirectional delete (reconcile)".

Each row in `StrategiesTab` has a Deploy/Compile/Run action driven by the **content-aware** `StrategyFileSyncStatus` (`needs_deploy` / `needs_compile`, not the old presence-only `in_sync`). `StrategyRow` takes the full `sync` object (via `syncByStrategy[s.id]`), and the Status cell shows a version chip `v{current_version}` (title tooltip: "Local vN · running vM") next to the state pill: amber **Needs deploy** (local source differs from what's deployed) → amber **Needs compile** (deployed but not compiled from that content) → green **In sync**. The action button mirrors the pill: `needs_deploy` → Deploy, else `needs_compile` → Compile, else Run. `handleDeploy` tracks `deployingId` and on success invalidates `sync-status`. **First-run:** every strategy shows Needs deploy until deployed once through the tracked path (no deploy-hash recorded yet — see backend CLAUDE.md). `StrategyVersion` type + `GET /strategies/{id}/versions` expose the full version history if a per-strategy view wants it.

**"Needs scan" pill (2026-07-23).** Separate from the deploy/compile sync above — it reads `Strategy.needs_scan` (on the strategy row itself, not `StrategyFileSyncStatus`), which the backend computes live (source hash / meta mtime vs last scan). When true, `StrategyRow`'s Status cell shows a clickable amber **● Needs scan** pill (calls `onScan` → `useScanStrategies().mutate()`, spins while pending) ABOVE the deploy/compile pills. It renders for ALL runners, and for a Python strategy — which has no deploy/compile step, so its Status cell was otherwise empty — it's the only status pill. `RunBacktestModal` shows a matching amber banner when `strategy.needs_scan` ("Parameters may be out of date … click Scan Strategies, then reopen"): the panel form is built from the last-scanned schema, so editing a Python `config.py`/meta without re-scanning silently runs on the OLD params (the bug that ran mpc_sos_fade on stale divergence-armed defaults). This is the Python analog of the MT5/NT8 deploy/compile badges.

