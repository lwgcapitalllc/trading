# Notes — Overview, sidebar and the Calendar page

What was audited and fixed on the Overview page, the sidebar's status dots, the Needs-review chip and the Calendar page. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain. [Detail](../docs/FRONTEND_BUILD_NOTES.md#overview) |
| Smart Money | 🟡 Built, flagged OFF | Scan, terminal, rankings, profiles, disqualified, config, cache — all still work. Hidden from the nav, the Overview and the router since 2026-08-04 (`FEATURES.smartMoney`); nothing was deleted |
| Bots | ✅ Live | One list (accounts as headings, bots as rows), an account panel and a bot panel — see *The Bots page* above. [Detail](../docs/FRONTEND_BUILD_NOTES.md#bots) |
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
| Stress Tests | ✅ Live | Grade card, source card, MC fan + drawdown + walk-forward + sensitivity charts. **Audited 2026-08-05 — the page had been driven end to end ONCE, three days before the engine underneath it was rewritten.** [Detail](../docs/FRONTEND_BUILD_NOTES.md#stress-tests) |
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
| News Calendar | ✅ Live | `pages/Calendar.tsx` (`/calendar`) — Forex-Factory-style economic calendar off the free TradingView feed. [Detail](../docs/FRONTEND_BUILD_NOTES.md#news-calendar) |
| History-limited periods | ✅ Live | `useHistoryLimit` + `PeriodPicker`'s `limit` prop. The date picker's minimum is the broker's MEASURED earliest backtestable date (probed server-side per broker, never hardcoded here), presets clamp to it, and a typed/pasted earlier date shows a one-click "Start at <date>" fix. [Detail](../docs/FRONTEND_BUILD_NOTES.md#history-limited-periods) |
| Overview calendar preview | ✅ Live | `pages/Overview.tsx` — full-width "Economic Calendar" card below the module grid: next high-impact callout (flag + countdown) + a 2-col list of the next upcoming events this week; whole card navigates to `/calendar`. Reuses `useCalendar` + `lib/calendar.ts` |
| Settings | ✅ Live | Config read/write; `nt8_agent_tunnel` + `mt5_agent_tunnel` |
| Sidebar health strip | ✅ Live | 4 dots: API, **SSH (3-state)**, NT8 (3-state), **MT5 Agent (3-state)**. Two of them were reporting something other than what they were named until 2026-08-02 — see *Two dots that were not measuring what they said* below |
| Price-chart panel | ✅ Live | Lazy klinecharts candlestick panel on BacktestDetail (`components/ChartPanel/`, own CLAUDE.md): TF switch (display resample up to **D1** + M1→H1 drill-down, the drill window ANCHORED ON THE VIEWPORT and paged like any other history + red "no earlier data" edge), sessions, generic overlays, … [Detail](../docs/FRONTEND_BUILD_NOTES.md#price-chart-panel) |
| News & Holiday filter | ✅ Live (NT8 + Python) | **A pill on the Performance header that reshapes the page's REAL numbers** — no duplicated tiles, no section of its own (both were removed 2026-07-30). [Detail](../docs/FRONTEND_BUILD_NOTES.md#news--holiday-filter) |
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail` page. Layer 2+ Python strategies over one shared instrument/costs/window — but **each leg runs on its OWN timeframe** since 2026-09-03. [Detail](../docs/FRONTEND_BUILD_NOTES.md#portfolio-stacks) |

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

### A slow agent draws YELLOW "slow", never the clickable red (2026-09-10)

🔴 **Red is the only clickable colour, and its click restarts the SSH tunnel.** An agent that
answered late used to draw red "click to start" — an invitation to cut every request in flight
over a busy-but-healthy agent. The dot now reads the server's `{nt8,mt5}_agent_state`: `down` is
red and clickable as before, `slow` is yellow with the word **slow** and a tooltip saying when it
last answered. ⚠ **The grace window is decided on the server and not restated here**, so there is
one answer to "how long before slow becomes down". ⚠ A backend without the field falls back to the
old boolean — `false` is down, exactly as before, never a guess either way.

**NinjaTrader switched off on purpose draws GREY "off" (2026-09-11)** — never red, never yellow,
never clickable, the server's `nt8_off_reason` on the tooltip; `=== true` only, so an unasked box
keeps the old colours. ⚠ **Only while NT8 is not working** — if somebody brings it back up the dot
goes green before the box's task state catches up. The Strategies page swaps its yellow "can't
reach the NT8 agent" banner for a quiet note (`AgentGapBanners`, `nt8-off-note`). Backend rules:
`../backend/CLAUDE.md` → *NinjaTrader switched off on purpose*.

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

🔴 **The mock's `server_now_ms` must be the PAGE's clock, never Node's — it silently defeated
`page.clock.install` for this entire file.** Fixed 2026-08-06. `mockCalendar` served
`server_now_ms: Date.now()`, and a route handler runs in the NODE process on the REAL clock, so
`useServerClock` — which holds the server/browser OFFSET and trusts the server, by design —
computed `offset = realNow − fakeNow` and rendered the real time however the test had set the
clock. ⚠ **The failure was invisible in ten of the eleven checks**, because they assert on
requested weeks and rendered rows rather than on a rendered time; only *"reads in days for an event
days away"* reads the countdown, so only it went red, and it went red on a SCHEDULE — the fixture's
event is four days past the requested Monday, so the assertion held until the real clock made that
event less than 24h away. **It reads exactly like a flaky clock-dependent fixture and it was not
one; the fixture was fine and the clock never arrived.** The mock now serves
`await page.evaluate(() => Date.now())`. ✅ Proven by mutation: moving the installed clock to 16h
before the event renders `Now 08:00 PM … in 15h 59m` — the INSTALLED time, which is the evidence
the fake clock now reaches the page, and a red assertion, which is the evidence the check still
bites.

⚠ **Two side effects of that fix, both worth carrying.** The `page.evaluate` adds a round trip to
every mocked response, and that latency exposed a second check asserting on a RACE: *"the
week-range pill follows it over midnight"* matched `getByText(/Aug 10 – Aug 16/)` page-wide, which
also matches the `Loading Aug 10 – Aug 16…` banner, so it had only ever passed because the mock was
fast enough for the banner to have gone. The pill now carries `data-testid="week-range"` and the
check is scoped to it — **which is what its own name always claimed it did.** **The general
rule: making a fixture slower is a legitimate way to find assertions that were passing on timing.**

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
one click away drew its `No MT5 link` chip. The chip is on both pages now. ⚠ **The *Bots
Running* stat card that also summarised it was removed 2026-09-11** as a copy of the bot list
under it, so the row's chip is the page's only statement — never add a fleet-health summary
back without testing its blind branch BEFORE every healthy one (a blind bot *is* running).

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

## The `Needs review` chip — a notification is a moment, a chip is a state

**Added 2026-08-05.** `ReviewChip` on the Bots page's Monitor row, fed by `BotStatus.review`, which
`algos/notifications/log_review.py` writes hourly after reading the bot's own health record. ⚠ **Since
2026-09-12 it is no chip: it is the row's one status, "Needs review"** — see *One status per row*.

**It answers the question no other signal on this page can.** Everything else here is about the
PROCESS — the Running pill, the uptime, the `No MT5 link` chip — and a bot can be alive, stamping its
heartbeat and showing RUNNING **while its order bridge is HALTED and it places nothing.** Same for a
bot that crash-looped overnight, or lost its terminal four times and recovered each time, or had a
settings change REFUSED so the page shows values it is not using.

⚠ **The chip and the Telegram alert are a PAIR, and neither replaces the other.** The ping gets your
attention when it happens; the chip is still on the row tomorrow if you scrolled past it at 3am. A
finding that only ever existed as a notification is a finding you can miss exactly once.

⚠ **It is deliberately NOT hidden on a stopped bot**, which is the opposite call from `No MT5 link`
one chip to the left. The findings worth most — it crashed, it was killed, it refused to start — are
precisely the ones you can only read once the bot has stopped, so hiding it there would suppress the
explanation at the moment somebody is hunting for it.

⚠ **Red vs amber is the WORST finding's level, not a count.** One halted bridge is red however many
warnings sit beside it; the count in the label says how many there are.

⚠ **The whole finding text goes on the `title`.** The point of the chip is that "why does this bot
need attention" is answerable without opening a JSONL file on a Windows box over SSH — a chip that
only says *something is wrong* has moved the question rather than answered it.

## The bots card is grouped BY ACCOUNT (2026-09-16)

Aaron: *"super ugly and confusing."* The flat list read "SOS Fade LIVE" twice with nothing to say
which account each was on, and printed one account's return on every bot of it. Now
`pages/overview/BotsCard.tsx`: total balance on top, then one block per account (live first, named
by its nickname and number, return and balance once on its header), bots on no account last, then
the VPS background jobs. A bot row is its name and its one-word state only. The best research
result now names its strategy. ⚠ Two tests had copied the box's FIRST bot, which is currently the
benched one with no account — they now set the account themselves.
