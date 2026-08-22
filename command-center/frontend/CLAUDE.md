# CLAUDE.md — Command Center Frontend

**Purpose:** React + Vite + TypeScript app (`:5173`) — the UI for the command center; all server state via TanStack Query against the FastAPI backend.
**Scope:** This covers frontend hook/component/page conventions, the theme system, and routing. It does NOT cover the backend (see `../backend/CLAUDE.md`) or `algos/`/`smart-money/`.
**Status:** Live — all pages shipped (Overview, Bots, Strategies, Rulesets, Backtests lab, Optimizations, Tuning workbench, Stress Tests, Settings). **Smart Money is built and flagged OFF** since 2026-08-04 — see *Feature flags*.



Auto-loaded by Claude Code when editing any file inside `frontend/`.

React + Vite + TypeScript app on `:5173`. All API calls go to the FastAPI backend on `:8000` via the Vite proxy at `/api`. Dark indigo-black UI, electric cyan accent, gold secondary.

**Lab design principle:** Run Backtest modal starts with no firms pre-selected. User must actively choose which firm challenges to evaluate against — never auto-select all.

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `command-center/docs/FRONTEND_DIARY_NOTES.md`. **Nothing was deleted.** It was 110,551 bytes in 3 paragraph(s), the largest 47,237 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

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
│   ├── RunBacktestModal.tsx  **The Costs section COLLAPSES, folded by default (2026-08-15, Aaron's ask — it sits between the params editor and Advanced and cost ~300px of scrolling on every run).** `SectionHead` takes `open`/`onToggle`/`summary` and becomes the collapse control. ⚠ **A collapsed section MUST pass `summary`** — the header is then the only thing standing for everything folded away, and a reader who cannot see what a hidden section is set to opens every one of them, which is worse than never having collapsed anything. It reads `frictionless` when nothing is ticked (the default, and every run until somebody decides otherwise) and otherwise names the ticked layers and the broker. ⚠ **The summary is derived from `costRows`, not from a second list**, so it names exactly what the rows below it offer, in their order, and cannot drift when a layer is added 🔴 **ONE VIEW: SCAN EVERY SETTING AND EDIT ANY OF THEM IN PLACE (2026-08-15).** It passes `layout="compact"` to `ParamEditor` — every setting, grouped, two to a row, ~30px a row against the stacked layout's ~60px, so `mpc_sos_fade`'s 30 settings read at a glance with no mode to be in. ⚠ **The first attempt was a READ-ONLY summary with an Edit button and it was rejected** (*"what's the point of essentials if I have a read only view and an edit view?"*). Two lessons, and the second is the general one: **a read-only view and an edit view of one thing is one view too many**, and **an Essentials card only earns its place when the rest are HIDDEN** — with everything on screen it is a duplicate, so the same param appeared twice. ⚠ **The compact grid is built from the exported `visibleParams`, the same function the modal counts changed settings with**, so the count can never name a row the grid does not render. **Same pass, the space complaint:** the read-only Strategy row moved into the TITLE (it restated the thing you clicked Run on), instrument + bar size + period share ONE row with three inline labels instead of four stacked uppercase sections, the instrument's ten preset chips became the input's own `<datalist>` (a select would have taken away typing a symbol they do not cover), the bar presets became a `<select>`, `PeriodPicker` gained `compact` (dates and quick ranges on one line, notes still below), and the shell went 900px → **1180px**. ⚠ **`compact` on the picker changes LAYOUT only** — same inputs, same presets, same clamping; a compact mode that also dropped a control would be a different picker wearing one name. ⚠ **`ParamEditor`'s opening explainer focus now requires `visible(p)`** — it picked the first `core` param off the raw list and opened on `exec_arm_div`, a SETTLED param with no row on screen.
│   ├── WorthinessBadge.tsx  Tier 1/2/3 pill badge (green/cyan/yellow)
│   ├── Tier3WarningModal.tsx    smart-routing modal for Tier 3 → sweep or optimize anyway. Bounded `flex flex-col max-h-[88vh]`: header + footer are `flex-shrink-0`, the intro/sub-header/sweep-CTA stay pinned, and ONLY the instrument rows scroll (their own `overflow-y-auto` with a `sticky` thead) — so a long instrument list never clips the header/footer. Tested results always show; the untested long tail is collapsed behind a "Show N untested instruments" toggle (`showUntested`) so the tested rows stay the focus
│   ├── OptimizeButton.tsx   tier-aware optimize trigger (Tier1 soft confirm, Tier2 direct, Tier3 warning)
│   ├── ParamEditor.tsx      SHARED strategy-param editor used by all three editing surfaces (Run / Tune / Optimize) so they never drift. **Rows are STACKED — param label (plus the tune `was X` tag) on one line, control on the next** — because side-by-side gave the label only the leftover width and every label in the narrow tune rail truncated to `Arm on di...`, with the `was on` tag cropping it further. **Every control then renders at one size (`CONTROL_W` = `w-full max-w-[420px]` x `CONTROL_H` 34px) — toggle, select, number and switch alike** — so the list has one straight edge, a row's height never depends on its label, and a wide Run/Optimize modal doesn't stretch a toggle across half the screen. In optimize mode the number box (`NumberBox fill`) and the sweep button share that one width. **A non-numeric param can be swept too, as a value LIST (2026-08-02)** — `AxisEdit` gained a `{mode:'list', values}` variant, and `sweepChoices(p)` is the single definition of what set a param has (a `choices` dropdown's options; a bool's two states, labelled from `p.options`). It is gated on `allowListSweep`, which `OptimizeButton` sets only for the **python** runner: NT8 and MT5 hand a Start/Step/End range to their own tester, so a list of strings has nowhere to go (the backend refuses one too — see `backend/CLAUDE.md`). Ticking the sweep button starts with EVERY option selected and the chips untick from there, and the last selected value cannot be unticked — a swept param with an empty set expands to zero combinations, which would run an optimization of nothing. Everything else (free text, a time) still renders read-only as `inherited · not swept`, which is now a true statement on the backend as well. Toggle state labels truncate (with a `title`) rather than wrap: a wrapping label used to grow its row and break the rhythm of the whole list. String params with a `choices` list render a **dropdown**, never free text — `choices` beats `widget`, because strategies match enum strings exactly and silently no-op on anything unrecognised, so a typo would disable a setting with no error. Essentials card (core knobs) + counted accordions, Simple/Expert switch, conditional `show_if` visibility, named toggle/switch/time widgets. **`show_if` takes a single value OR an array of values (2026-07-30)** — an array means "any of these", which every enum with one OFF state and several ON states needs (a minimum-stop mode of Off / % of price / Fixed $ / x ATR is the first). Before the array form the dependent row could only be tied to ONE of the ON values and stayed hidden for the rest, which reads as a missing setting rather than a conditional one; note the comparison is stringified, so `1` and `"1"` match. **`min`/`max` reach the number input as of 2026-08-02** — the scanner has passed them through from the meta since it was written and nothing read them, so a bounded param looked unbounded; the first real user is `mpc_sos_fade`'s Custom stop level, a fib ratio that must land in (0, 1.0]. Treat them as a CUE, never a gate: a native number input stops the spinner and marks the field `:invalid` (styled `invalid:text-neg`) but still accepts a typed or pasted value past the bound, so the STRATEGY's own check is what actually refuses one — `SosFadeConfig.__post_init__` raises and fails the run rather than silently substituting a different stop. **An option label can READ another param, and a toggle can be greyed rather than hidden (2026-08-15).** Three schema keys, all resolved through `condHolds` / `readerFor` / `isInert` at the top of the file so the comparison rule exists once. (1) **`{param_name}` in an option label** is substituted with that param's current value — `fillTokens` does it to the SCHEMA once in `ParamEditor`, not at each render site, because option labels are read in five places and a token surviving into any one of them shows a reader `{exec_sl_level}`; `OptimizeButton` calls it too, for the list-sweep chips. An unknown name is left on screen as `{typo}` rather than blanked. (2) **`disable_if` is `show_if` at the OPPOSITE POLARITY** — every condition holding GREYS the row and shows `disable_note`, for a setting whose two states cannot differ in the current configuration. ⚠ **Greyed, never hidden: a setting that vanishes reads as one that does not exist**, the same house rule `AccountsTab` follows for an unassignable account. The button carries `disabled`, so a click cannot write a value the strategy will not act on. (3) **`custom_from` names the sibling holding a dropdown's Custom value**, and the SIBLING'S OWN `show_if` decides when it applies — so there is no second copy of the trigger to drift. ⚠ **Everything that reads a value for display or gating resolves through it**, or `Custom = 1.0` and the dropdown's own `1.0` behave differently, which is exactly the case a value-blind gate gets wrong. ⚠ **`strategy_scanner._PARAM_META_KEYS` is a WHITELIST — a meta key missing from it is dropped in silence** and the editor behaves as though nobody wrote the rule; ⚠ **and `stress_tester.param_is_reachable` mirrors both gates**, because perturbing an inert param books a guaranteed 0% change that the stress page reports as "rock solid". First user: `mpc_sos_fade`'s `exec_sl_deep`, whose labels named a neighbouring widget (`Always the level above`) and which stayed live at a stop level of 1.0 where both its states place the same stop — the Pine had greyed it (`active = execSlLevel != "1.0"`) since it was written. 🔴 **A fourth key, `hidden`, RETIRES a settled param from the editor without removing the field (2026-08-15, Aaron: *"I don't want you to delete the configurations… you might be able to toggle it back on super easy"*).** The config field stays, its default is still sent, and only the ROW goes; `mpc_sos_fade` went 56 editable rows → 30, and two whole groups disappeared (`Higher-timeframe filter`, four params all at `Ignore`, and `Reporting`). 🔴 **THE BAR FOR HIDING IS A SWEEP, NOT AN UNTOUCHED VALUE (Aaron's correction, 2026-08-15).** The first pass proposed twenty more on the grounds that they took exactly one value across every stored run — and *never moved* is the ABSENCE of the experiment, not its result. Only the seven with a named sweep behind them went (`exec_close_opp_sos`, measured at exactly 0 effect TWICE; `exec_tp2_stop_mode` and `exec_struct_trail_buf_tk` and `exec_trail_step` off Run 2's 525-combo exit grid; `exec_be_buf_tk` off Run 17; `exec_fvg_deep_only` and `exec_no_late_day` off Run 12's relax routes). ⚠ **`exec_sl_buf_tk` is the sharp case and stays VISIBLE**: it WAS swept, in Run 4, and Run 4 is marked *INVALID, DO NOT USE THE NUMBERS* — which is worse than untested. ⚠ **`exec_risk_pct` is never hidden whatever the evidence says** — it decides position size on the LIVE bot's strategy, and a sizing input nobody can see is how a 54.82-lot order happens. 🔴 **The load-bearing half is the ESCAPE: a hidden param sitting AWAY from its default is shown anyway** (`settled()` in ParamEditor) — the value is still submitted, so hiding a MOVED one would put a setting on the run that no reader could see, which is a page unable to show what it is about to submit. ⚠ **The count is stated out loud** (`param-settled-count`), and `StrategyDetail` NAMES them in a `<details>` rather than counting: that page describes what the strategy IS, and a settled param is still a rule it applies — only the QUESTION is closed, never the behaviour. ⚠ **`StrategyDetail` drops them unconditionally where the editor does not**, because it has no per-run value that could be off-default. ⚠ **Hiding is decided per-param in the meta and is a PRODUCT call, not a cleanup** — the divergence VETO (`div_veto`, `exec_respect_veto`, `show_div`) stays visible while its ARM (`exec_arm_div`) is hidden, because the veto is still refusing setups; `backend/tests/test_param_gates.py` pins that split and pins that nothing already TUNED on a real run is hidden. ⚠ **`isSettled` is EXPORTED and every surface calls it** — the editor, the strategy page and the finished-run params panel — because a second copy of the `hidden && on-its-default` conjunction is how one of them starts hiding a MOVED param; `stress_tester._is_settled` is the fourth evaluator, on the python side, and mirrors it deliberately. 🔴 **`BacktestDetail`'s params panel FOLDS rather than filters** (`run-settled-params`, a `<details>` carrying its own count): that panel is the RECORD of what a run sent, and a run report that silently omits inputs is a worse defect than a long list. ⚠ **Since 2026-08-20 that fold is headed *Already decided*, its sibling *Instrument & broker*, and it holds TWO sets** — a settled param AND one a run could not act on (`isOutOfPlay`, a `show_if` that does not hold or a `disable_if` that does). Full rule: *The finished-run params panel* below. ⚠ **A settled key differing from the tune BASELINE stays in the main list too**, or the changed-vs-baseline count would name a row the reader cannot find. ⚠ **The Strategies list's `Params` column counts the TUNABLE ones** and puts the full breakdown on its tooltip — a shrinking number with no explanation reads as params having been deleted. ⚠ **`stress_tester.param_is_reachable` gained the settled gate too, and it is NOT the same shape as the other two**: shifting a settled param is not a no-op (the strategy really reads it), so the reason to exclude it is that sensitivity would rank a parameter no page renders — a ranking pointing at nothing. 🔴 **THE ESSENTIALS CARD AND THE SIMPLE/EXPERT SWITCH ARE GONE FROM BOTH LAYOUTS (2026-08-15, Aaron's call).** The card was built when the accordions were shut and it was the way in — but it **DUPLICATED** its params, so a `core` setting appeared both in the card and inside the group it belongs to, and changing one place left the other looking untouched. Simple mode went with it: its only job was hiding the non-core rows, which is a question about a card that no longer exists. ⚠ **Every param now appears EXACTLY ONCE, under its own group, on Run, Tune and Optimize alike.** ⚠ **`core` still means something and was NOT removed from the meta** — it now decides which accordion opens FIRST (`firstCoreGroup`), with `gi === 0` as the fallback for a strategy that flags none. The general lesson: **a curation of "the important ones" only earns its place when the rest are HIDDEN** — the moment they are all on screen it is a second copy, and this repo's most-repeated defect is a second copy. 🔴 **`layout="compact"` is a SECOND LAYOUT, not a variant of the first** — one dense editable grid (`CompactRow`), no Essentials card, no Simple/Expert switch, no explainer column, every group open on arrival. ⚠ **Its collapse state tracks what is COLLAPSED, not what is open**: a map of what is open defaults every group to shut on first render, which is the opposite of a layout whose whole point is reading all of it at once. ⚠ **A bool renders as a `<select>` here, not the segmented toggle** — at 190px a two-button toggle truncates a state label like `Structure + % ratchet`, and a truncated state label is the one thing this row cannot afford to get wrong. ⚠ **Every control is the same width**, so labels form one column and values another; that is what makes 30 settings scannable rather than a wall. ⚠ **Each group is its own bordered SECTION, not a heading over a continuous list** — read as one list the rows blur together and the group name stops doing any work (*"do something to make it visible that these are sections, segregate it from each other"*). The header is the collapse control, so a section can be shut to focus on another. ⚠ **`tests/tuning.spec.ts` RESOLVES its baseline from the lab rather than naming a run** (2026-08-15) — it was a literal id, and the day that run was deleted EIGHT tests failed on *"not in the lab any more"*, pointing at the leaderboard, which was fine. It now takes the newest completed STANDALONE run that carries a regime timeline **and has no children of its own** (real children would land in the leaderboard beside the five synthetic ones and move every count), and the drawdown assertion reads that run's OWN stored figures instead of typed literals — what it pins is the ORDER, percent before dollars. **A fixture pinned to one row is a fixture with an expiry date**, and this is the second one in two days (`backtests.spec.ts`'s millions check was the first). Tests: `tests/param-gates.spec.ts` (20) + `backend/tests/test_param_gates.py` (22), both non-vacuous by MUTATION. Friendly labels/groups/descs/units/`core`/`options`/`guide` come from the schema (overlaid from a strategy's companion `<Strategy>.meta.json` by the scanner). Theme tokens only; colour rule: blue=focus only, gold=section-title text. `mode`: `run`|`tune`|`optimize`. `explainer`: `panel` (fixed right column — wide Run/Optimize modals) · `inline` (drops under the focused row) · `coach` (no per-row explainer — parent renders the exported `<ParamCoach>` footer; `onFocusChange` surfaces the focused param). Degrades gracefully with no metadata (no core → no Essentials card, all groups as accordions)
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
    ├── StackDetail.tsx       portfolio stack (`/backtests/stacks/:stackId`). `composeCombined` unions the enabled legs' trades over one shared account (combined start = Σ each leg's opening balance) into a synthetic backtest-shaped `run` + portfolio equity, tagging each equity point with a `leg_<id>` running-balance field for the overlay lines. **Performance = a single backtest's own panel, all four cards of it (2026-08-10)**: BacktestDetail's exported `PerformancePanel` behind its exported `PerfCollapseToggle` and `usePerfCollapsed`, with `StackVerdictCard` in the **`verdict`** slot — so a stack is Verdict / Made / Risked / Trusted in one row, collapsing off the same stored preference. **The strategy legs are the Verdict card's ROWS, and each row is its own toggle.** Earlier builds put a `StackTradesRibbon` in the `ribbon` slot with the leg chips in a section of their own further down, which meant a stack and a run showing the same numbers looked like two different features, and the control deciding what every KPI counted sat nowhere near the KPIs. See *A stack renders a run's panel* below. Recomputes as strategies toggle. Charts are a `ChartTabPanel` (Equity / Price / Breakdown) with the SAME controls as a run: **Equity** is the real exported `EquityCurveChart` on the combined portfolio (so it inherits every toggle — Trade excursions, Run-ups & drawdowns, Date/Trade `XModeToggle`, Regimes `RegimeOverlayToggle`, expand) with a line per enabled strategy overlaid via the new `overlayLines` prop; Breakdown reuses exported `DrawdownChart`/`DailyPnlChart`/`DirectionBreakdown`; Price is exported `PriceChartView` fed the merged stack spec (structure layers/fib/measurement/expand/minimize, drill-down via `base_run_id`, trades layered + tinted per strategy). Regime bands come from `StackDetail.regime_timeline` (backend computes it on-demand for the shared window — sweep-child legs aren't tagged — and caches it). Everything recomputes on the Verdict card's leg rows (≥1 always on). **Rerun** opens the shared `StackConfigModal` prefilled with the stack's full config. Per-strategy row → that leg's BacktestDetail with `state:{fromStack}` so its Back returns here; reused legs are real standalone runs. Trades handed to the price chart carry `layerColor` + `layerName`, which is what makes the chart print `<strategy> · Won` in each outcome chip and build its own **Strategies** dropdown (see `ChartPanel/CLAUDE.md`). `avg_trade_duration_min` is the legs' own averages **trade-weighted** (you can't average durations flat), and profit factor reports `Infinity` when the enabled legs have no losing trade — the Made card prints ∞ rather than a dash that reads as missing data
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

## A settings GROUP must not hardcode a number one of its rows owns (2026-08-21)

The strategy editor renders its accordions from the `group` string in a strategy's meta file, so a
group name is a claim like any other label. The re-entry block read **`Secondary re-entries (1m)`**
until the re-entry's fill clock became a setting (5 minutes by default). Renaming it `(5m)` was the
obvious move and would have been the same defect one turn later — **the heading now names no
timeframe at all**, and the one row that owns the number is the only place it appears.

`tests/param-gates.spec.ts` pins the ABSENCE (`Secondary re-entries (\d+m)` must not render)
rather than the presence of a particular figure, so the test cannot go stale the next time the
default moves. ⚠ **Playwright is not in `scripts/run_all_tests.sh`** — it needs the app up — so
this one is only as good as somebody running it.

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
- **A mutation's failure toast comes from `api.*` already** — do NOT add an `onError: () => toast.error(...)` beside it. Seven hooks in `useLab.ts` carried one until 2026-08-06 and every failure they covered popped **twice**.
- **A POLLING query must not toast** — `request()` toasts on every non-ok response, so a query on a `refetchInterval` toasts on every tick, and one unreachable dependency becomes a permanent queue of popups (measured on the Strategies page: ~6/min with the NT8 agent down, plus a burst per window focus). Pass `api.get(path, { silent: true })` with `retry: false` **and render the failure in the layout**. ⚠ `silent` hides the toast, never the error — `isError` and the payload still reach the caller, so using it without rendering the failure turns a loud bug into a silent one.
- 🔴 **A PREFIX invalidation re-asks every DERIVED query, and after a destructive mutation the only answer left is a refusal (fixed 2026-08-10).** Aaron: *"whenever I run up a test I just get this red popup… and it has popped up twice always."* `useRetryBacktest` invalidated `['lab','run',<id>]` — which also matches that run's **re-price** and **news** queries — while a retry has just DELETED every artefact those read (`_clear_run_dir`), so the re-price fired against a run with no equity curve and got a `400`; the global `retry: 1` is why it popped **twice**. The retry now marks the derived queries stale with **`refetchType: 'none'`** and re-fetches the RUN alone (`exact: true`). Both derived queries are gated on the run having an equity curve, so they switch off when the run's own refetch lands and re-ask themselves once the new attempt finishes. ⚠ **Do not "simplify" that back to one call** — the prefix match is WANTED (a finished rerun must invalidate them); only the immediate re-ask is not. ⚠ **`useRunReprice` is `silent` for the reason one bullet up**: the refusal is RENDERED — the pill reads *Can't price this run* with the server's own sentence in its popover — so the toast was the same message twice over, and `reprice.py`'s refuse-don't-guess discipline was already reaching the reader without it. ✅ Proven in a real browser both ways: a rerun goes **3 re-price fetches → 1 with no toast**, and a forced `400` still renders the pill and the sentence with no toast.
- ⚠ **STANDING, UNFIXED: every failed request in this app toasts TWICE.** `main.tsx` sets a global `retry: 1` on all queries, and `api.request` toasts on every non-ok response — so one failure is two attempts and therefore two identical popups. It is **not** the duplicate-`onError` defect above (fixed 2026-08-06) and it is not the prefix-invalidation one (fixed 2026-08-10); those two each removed a *second cause* of doubling and left this one, which is why a report of "it pops up twice" keeps coming back after each fix. ⚠ **Do not read a doubled toast as a second bug** — count the requests first. The fix is one line (`retry: 0`, or `retry: (n, e) => !(e instanceof ApiError)` so only transport failures retry), and it was deliberately NOT made on 2026-08-10 because it changes the retry behaviour of **every query in the app** — including the polling ones that already pass `retry: false` for their own reasons — and that deserves its own measurement rather than riding along with a toast fix. ⚠ **A retry on a 4xx is also the wrong retry**: the server has refused, so the second attempt cannot succeed and buys nothing but the duplicate.

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

## The period filter — read a WINDOW of a finished run, with no rerun (2026-08-16)

**`useDateFilter` + `PeriodFilterChip` in `BacktestDetail.tsx`.** Aaron: *"Is there a way to not
rerun a specific period… just have a filter where I could look at trades within a specific period?
And once I select that period, everything on the page adjusts — the equity curve, all the KPIs, the
price chart, the breakdown, everything. Right now I'm just having to rerun different periods."*

The third control that reshapes this page's REAL numbers instead of shipping a second set beside
them, and it rebuilds through the same `buildFilteredRun` the other two do. **The period chip in
the page header IS the control** — it already stated the run's window, so making it clickable was
cheaper than a fourth pill, and there is deliberately no second copy on the Performance header.

🔴 **THE REBASE IS EXACT ARITHMETIC, NOT A MODEL, AND EVERYTHING RESTS ON IT BEING LINEAR.** He
asked for a window to read *"like I only traded from 10,000 from that specific point in time"*. The
tempting implementation replays each trade's R onto a fresh account and compounds it. That is
unnecessary: a trade's dollar result is a fixed fraction of the balance it was taken with, so
**scaling every profit in the window by ONE constant — the run's opening balance over the balance
entering the window — reproduces that replay to the cent.** ✅ MEASURED on run `831ec44195ce`,
2023-01-01 → end: the scale is ×0.074876 and lands at **$11,911,347.71 against the R-replay's
$11,911,354.78 — 0.000059% apart**, i.e. floating point.

⚠ **EVERY RATIO IS THEREFORE UNCHANGED BY THE REBASE** — profit factor, win rate, R, Sharpe,
peak-relative drawdown, concentration. ✅ Verified identical to 9 decimal places on that run
(PF 3.010326545, win rate 0.673267327, max DD 45.259156%). **If a ratio ever differs, the scale has
stopped being a single constant and the rebase is broken — do not "fix" it by special-casing the
ratio.**

⚠ **IT IS NOT A RERUN AND THE PICKER SAYS SO.** A rerun of 2023→2026 warms its engines from 2023
and sizes from $10,000 the whole way; the window carries the full warm-up from 2020 and each
trade's ACTUAL risk fraction, which drifted 5.9% → 66.4% on that run (risk is measured to the
trade's current stop). They agree on shape and on R and will not agree trade-for-trade.

⚠ **The picker states the rebase where the window is CHOSEN**, naming the balance it reads from,
the balance the account really held, the scale, and that ratios are untouched. A silent rebase
would put a balance nobody ever had under a headline that looks like the run's.

### Composition, and the one correct order

`costs → period → news`, in `BacktestDetail`. A **cost** is a property of a trade, so it is charged
before anything decides which trades count. The **period** then cuts and rebases, because the scale
is read off the balance entering the window and that balance moves once costs are charged. **News**
is last: it removes trades from whatever book the two above settled on, and its own rebuild anchors
on the first trade it is handed, which is already the rebased one. With nothing on, each `??` hands
the next filter the run's own object, reference-identical.

- ⚠ **The window lives in `?from=`/`?to=`** and both writes MERGE the existing params — house rule,
  and `setSearchParams({from})` alone drops `?tab=` (already recorded on the Bots page).
- ⚠ **`active` requires all three of** a window being set, it actually narrowing, and the rebase
  being possible. A window covering everything must leave the page reference-identical, and a
  window entering on a zero-or-negative balance is REFUSED rather than scaled by a made-up number.
- ⚠ **An empty window says the strategy stood still.** A real answer, and the one most easily
  mistaken for the filter being off.
- ⚠ **The compare baseline follows the period.** With a window set, the news and cost deltas ask
  what they did INSIDE it; comparing a windowed book against the whole run would put a delta on
  every row that is really the window wearing a checkbox's name. **The period itself shows NO
  delta** — it is a different span, not a what-if over the same trades.
- ⚠ **Refused under a firm's sizing, on the same guard as the other two, for a DIFFERENT reason.**
  Slicing a sized curve by date is honest arithmetic; the problem is that a firm's account opened
  at ITS `account_size`, so rebasing onto the run's deposit would state a prop account that never
  existed.
- ⚠ **The drawdown chart's firm LIMIT LINE is withdrawn while a window is rebased**, and only then.
  The limit is a dollar figure written against a real account; the windowed curve is scaled onto a
  different one. News and costs do not rebase, so they keep it.

### Two things it fixed that were NOT part of the ask

🔴 **The Breakdown tab read `effRun`, so it followed neither the news filter nor the costs pill** —
three charts under a header reading *"139 of 142 trades"* drawing all 142, since the day each pill
shipped. It reads `kpiRun` now, which IS `effRun` whenever no filter applies, so sizing is
unaffected.

🔴 **`Performance by Regime` rendered the run's server-computed rows under an already-filtered
panel.** `computeRegimeBreakdown` is a faithful port of `services/metrics.compute_regime_breakdown`
— the second frontend evaluator this repo has accepted, on `dailySharpe`'s argument. ⚠ **THE
EQUALITY IS THE REGRESSION TEST:** handed a run's own full trade list it must reproduce
`run.regime_breakdown` exactly (✅ byte-identical on `831ec44195ce`). Change one side and re-run it.
⚠ Keep the MT5 two-rows-per-trade rescale; dropping it makes the table disagree with the backend on
every MT5 run.

### The price chart follows by being handed LESS DATA

`clipSpec` filters the five timestamped arrays and raises `historyStartMs`. **ChartPanel is
untouched** — a `range` prop threaded through 4,300 lines would be a second place for "what is on
screen" to be decided, on the chart that already owns its viewport. ⚠ A SPAN overlay (box/hline) is
kept when it OVERLAPS the window: an order block opened earlier and still live is what the trades in
view are reacting to. ⚠ `missNoise` is NOT clipped — reason LABELS, not records. ⚠ Times parse as
UTC, matching the emitter, or the edge shifts by the reader's offset. ⚠ Memoised at the call site:
156k candles and 29k overlays on a 6-year M15 run.

### Proof

- **`scripts/check_period_rebase.mjs`** — the arithmetic, outside the browser, because these are
  numeric IDENTITIES and asserting them through `FitMoney`'s formatted text would be asserting on
  the formatter. 5 checks + a guard that the dollars really moved. ✅ Green, ✅ proven by mutation
  (`scale = 1` reddens the R identity, the drawdown invariance and the guard). ⚠ It reads the
  STORED `equity_curve.json` for the R identity — `risk_usd` is on disk and NOT declared on the
  backend's `EquityPoint`, so FastAPI drops it. This repo's "the model drops what it does not
  declare" trap, met as a limit on what can be PROVEN rather than as a rendering bug; nothing in
  the browser needs the field.
- **`tests/period-filter.spec.ts`** — 9 checks, 8 green, 1 skipped (needs an engine-sized run). ⚠
  **A fail-watch against HEAD is vacuous for most of it** (the control did not exist, so a red
  proves the locator and nothing else) — **non-vacuity is by MUTATION, named per check**. The
  Breakdown and regime checks are the two watched red against HEAD for the right reason.
- 🔴 **`lib/inputs.ts` → `DATE_INDICATOR_CLS`, and EVERY `<input type="date">` must carry it.**
  Chrome draws `::-webkit-calendar-picker-indicator` as a near-black SVG, so on this theme the
  calendar button is an invisible glyph on an invisible field — reported off the screen the day this
  shipped (*"can't see the calendar icon"*). ⚠ **The fix already existed and had not travelled:**
  `PeriodPicker` solved it privately when it was written, and the two date inputs added since
  (`ChartPanel`'s Go-to-date, this popover's two) never inherited it. It is a shared constant now,
  in `lib/` rather than in `PeriodPicker` — `ChartPanel` is strategy-agnostic and must not import
  page furniture. ⚠ `invert`, never a colour, so it survives a theme swap. ⚠ The browser check
  strips the class at runtime and requires the input to LOOK different; **it deliberately does not
  assert the class NAME**, which is a spelling rather than the property.
- 🔴 **TWO NEW SHAPES OF VACUOUS PASS, both found in one check** (full story:
  `../docs/FRONTEND_BUILD_NOTES.md` → *The period filter*). **Never assert a Recharts change by
  SCREENSHOT** — it animates on mount, so two loads differ by tween whatever the data is and
  `not.toBe(0)` passes on noise. **Never read SVG tick text with `allInnerTexts()`** — it returns a
  row of `null`, and nulls compare equal to nulls, so that passes too. Use `allTextContents()`
  scoped to `.xAxis`, and assert a VALUE (`Jul '20` → `Jan 3 '23`), not merely that two rows differ.

---

## What's built (status)

| Module | Status | Notes |
|---|---|---|
| Overview | ✅ Live | Stat row + cards for each domain. [Detail](../docs/FRONTEND_BUILD_NOTES.md#overview) |
| Smart Money | 🟡 Built, flagged OFF | Scan, terminal, rankings, profiles, disqualified, config, cache — all still work. Hidden from the nav, the Overview and the router since 2026-08-04 (`FEATURES.smartMoney`); nothing was deleted |
| Bots | ✅ Live | Monitor, control, configure, users. **Configure carries `DeployCard`** — the deployed version read off the VPS (hash / commit / date / params as deployed) plus the **Promote** button, which previews before it deploys and warns on the four states that make a version claim false. [Detail](../docs/FRONTEND_BUILD_NOTES.md#bots) |
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
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail` page. Layer 2+ Python strategies over one shared instrument/timeframe/costs/window. [Detail](../docs/FRONTEND_BUILD_NOTES.md#portfolio-stacks) |

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

## ESLint runs on this folder, from a config at the REPO ROOT (2026-08-14)

`eslint.config.mjs`, `.prettierrc.json` and `node_modules/` are at the monorepo root, not here.
That is not an accident of layout: `lint-staged` has to see every staged path — python included —
and a tool rooted inside one subsystem cannot. This folder keeps its own `package.json` for the
React build; the root one is dev tooling only. Full rules and why each is set: root `CLAUDE.md` →
*Formatting, linting and the test gate*.

Two things that decide what you see here:

- **The React Compiler rules are at WARN, not error.** `eslint-plugin-react-hooks` v7 promoted them
  into its recommended set and they are **51 of the 65 errors** this frontend produced, every one on
  code that ships and works (28 are `set-state-in-effect` alone). Read them — several point at real
  re-render bugs — but an error would mean editing one line of `BacktestDetail.tsx` blocks the commit
  on 28 findings nobody in that commit created. ⚠ **`rules-of-hooks` stays an ERROR** and must: a
  conditional hook call is a crash, not advice.
- **`@typescript-eslint/no-unused-expressions` allows ternaries**, because
  `set.has(x) ? set.delete(x) : set.add(x)` is a deliberate toggle idiom used in 11 places here.

**Current state: 0 errors, 78 warnings.** Getting to zero errors deleted three genuinely dead
symbols the linter found in the Playwright specs — an unused `type Page` import, an uncalled
`weekStart` helper, and an unreferenced `API` constant. ⚠ **`prettier` is configured `semi: false`
/ `singleQuote: true` because that is what these 108 files already do** (377 single-quoted imports
against 4 double, 30 semicolon-terminated lines out of 40,677) — it codifies the house style rather
than imposing one. Markdown is deliberately excluded; the measurement is in `.prettierignore`.

## Browser tests — `npm test`, and what deliberately is NOT in them

**Added 2026-08-05.** This folder had no test runner at all: the convention was "verify it in a
real browser", done by hand, which is why the Overview's twelve defects each survived until
somebody looked. `@playwright/test` + `tests/*.spec.ts` keeps those checks runnable —
**229 tests in 21 files** (counted 2026-08-20 with `npx playwright test --list`; the figure here had
been left at a stale "66 in 5" through several passes — re-count it rather than incrementing it),
run with `npm test` from `frontend/`.

### 🔴 A FIXTURE PINNED TO A DATABASE ROW — bitten three times now

**A spec that asserts on which rows happen to be in the lab will fail on a day nothing is wrong, and
that failure is indistinguishable from a regression until somebody reads it.** Third instance
2026-08-16 (`chart-paging.spec.ts`, both checks, a 120s timeout pointing at paging code that was
fine); the incidents are in `../docs/FRONTEND_BUILD_NOTES.md` → *Fixtures pinned to a row*. Two
answers, chosen by what the check needs:

- **RESOLVE when the check needs a SHAPE.** `chart-paging` wants "the longest intraday python run
  with trades and a built spec", `period-filter` wants "any run with ≥20 dated trades". ⚠ **Derive
  the DATE constants from the resolved run too** — a literal `TARGET` beside a resolved run moves
  the expiry from the run id to the calendar instead of removing it. ⚠ **Keep the vacuity guard**
  (here: the target really is outside the applied window); with the fixture no longer fixed, that
  stops being self-evident.
- **PIN, and make the pin ANNOUNCE ITSELF, when the check needs particular LAYERS.** Seven specs
  legitimately name a run — they need a VWAP series, a recorded fib leg, candle-reversal marks, an
  all-defaults param set. Each calls **`requireRun(RUN, '<what a replacement must carry>')`**
  (`tests/fixtures.ts`) in a `beforeAll`. ⚠ **A DIAGNOSIS, not a repair**: the suite is still red
  and still needs re-pointing by hand; what changes is that the failure lands in a second and names
  the run. ⚠ **The `needs` sentence is the load-bearing half** — a bare "not found" moves the
  question rather than answering it, and the next reader has to know it was the VOLUME on those bars
  that mattered. ✅ Proven against a dead id.

### 🔴 …and a row is only ONE of the five things a spec drifts against (2026-08-16)

**Sixteen checks were red across three specs nobody had touched, and every one was the page being
RIGHT.** A database row is the version of this everybody sees; the other four are the same defect
wearing different clothes, and each has its own fix. Full record: `../docs/FRONTEND_BUILD_NOTES.md`
→ *The five things a browser spec drifts against*.

| Pinned to | How it bit | The fix |
|---|---|---|
| a **row** | `chart-paging` (2), 7 specs at risk | resolve, or `requireRun` — above |
| the **weekday** | `calendar.spec.ts` (2) — the fixture built Mon–Fri and **the page opens on TODAY**, so both checks were green five days in seven and failed on a Sunday | **the FIXTURE covers all seven days.** The file had already met this trap and written it down beside one `?day=1`; the next two tests walked straight in. **A trap named in a comment is one the next test still hits — fix it where it is GENERATED** |
| the **calendar** | `overview.spec.ts` (1) — `?week=12 // US fall-back, 2026-11-01`, a fixed date written in an offset from today, so it named a different week every Monday and asserted 169h against a correct 168h | **derive the offset.** `nextDstWeek()` scans `getTimezoneOffset()` forward for the real changeover and expects 169h on a fall-back, 167h on a spring-forward. ⚠ It THROWS on a no-DST timezone — a silent skip and a pass are the same outcome |
| the **registry's SIZE** | `overview.spec.ts` (2) — `1 of 1` / `1 of 2` not reporting, against a fleet that grew to 3 | **SET the fleet, don't add to it.** Trim the real snapshot to the bots the rule needs. ⚠ And STATE the reporting bot's balance rather than inheriting it — the live one is `null` whenever the terminal is quiet, which would make the check pass for the wrong reason on exactly the days it matters |
| an **empty table** | `stress.spec.ts` (11) — the lab held ZERO stress tests, so a whole feature's suite had switched itself off | **make the fixture one command.** `backend/scripts/seed_stress_fixture.py` seeds a Monte-Carlo-only test (seconds, no VPS, no child backtests, Telegram stubbed), and the suite's own failure prints that command |

⚠ **The generalisation is the repo's own rule one level out: a test may depend on the world, but it
must not be able to fail SILENTLY-WRONGLY when the world moves.** Every one of these five failed
loudly enough to be seen and quietly enough to be read as a regression, which is the expensive half.

⚠ **`tsc --noEmit` DOES NOT COVER `tests/`.** A spec's syntax error typechecks clean and surfaces
only when Playwright loads the file. **`npx playwright test --list` is the parse check** — seconds,
every file, and where the count above comes from.

⚠ **The trade outcome chip's NAME still has no automated check, and that gap widened on 2026-08-08
when the naming rule gained an outcome dimension.** The chip is canvas-drawn with no DOM and its
inputs live inside `extendData`, so pinning it would mean contorting the product for the test. The
RULE is pinned backend-side (`test_candle_overlays.py`, mutation-proven); what is verified by hand
is that the browser renders it. Named here rather than skipped.

**`tests/chart-rebuild-fullscreen.spec.ts` (1, ~7s) — added 2026-08-08, WATCHED RED against HEAD.**
It asserts **Rebuild chart** is on the chart panel itself, in both the inline and the expanded view,
and that clicking it reaches the endpoint. ⚠ **Every locator is scoped to the panel's own root
(`[data-applied-lo]`) and has to be**: anything the HOST renders is outside that root, and in
fullscreen the host's chrome is still in the DOM behind the `position: fixed` overlay — covered, not
hidden — so a page-wide `getByRole` matches it and passes against the broken page. **Fourth instance
of that trap in this folder.** ⚠ **It also asserts a page-wide count of exactly ONE**, which is the
only assertion that says the button was MOVED rather than duplicated; without it, the tab strip's
copy could come back and the check would stay green. ⚠ **The refresh call is intercepted and
rewritten to the CACHED spec URL** — a genuine rebuild is a 7.6s engine replay, and the click only
has to prove it reaches the endpoint; the panel still gets a real payload, so nothing downstream is
mocked into a shape the server never sends.

**`tests/candle-reversals.spec.ts` (9, ~57s) — added 2026-08-08 with the Candlestick Reversals
layer, and it also carries the Missed layer's two filters.** ⚠ **The 9th check is the only one here
with a clean fail-watch and it is the most valuable for that reason** — the cross-filter defect
existed at HEAD, so the check goes RED there naming the count that does not move (a reason chip
stuck at 179 while the layer draws 35). Every other check in the file pins a layer HEAD did not
have, where a red is just the element being absent. ⚠ **It asserts a chip's count falls to exactly
`0` rather than merely decreasing**, because 0 is the finding: no 3/3 miss can be missing its FVG,
since a 3/3 met all three confluences. ⚠ **And it asserts the chip is STILL VISIBLE at 0** — the
roster is deliberately built from every record while only the count is filtered, so a control never
disappears at the moment it reads zero. ⚠ **Its `RUN` and `DATE_WITH_A_MARK` constants are tied to real data and drift**: the layer
went 424 marks → 153 → **820** in one day as its anchor rule was corrected twice, and a date that had
a mark under one rule need not under the next. When a check here goes red, ask what the run actually
draws now before touching the assertion. It drives the REAL backend, because the marks come from a server-side engine replay over
the run's own candles and a mocked spec would be testing the mock. ⚠ **A fail-watch against HEAD is
vacuous for a layer that did not exist** — every check would go red on the element being absent,
which proves the locator and nothing else — so four are proven by MUTATION and the other is
non-vacuous by construction (it measures the same pixels off and on). **The fifth check pins that a
setting EXPLAINS ITSELF FROM THE ⓘ**, and it asserts both halves — the paragraph is gone from the row
AND the text is one hover away — because *checking only that the paragraph is gone would pass against
a panel that simply deleted the answer*, which is the same tidy-up with the content thrown out. 🔴 **Two of the four broke when
blocked setups stopped being anchors, and they broke CORRECTLY: they read the opening viewport, which
held a mark only while the run carried 424 of them.** At 153 the newest bars have none, and **an
empty viewport is pixel-identical to a layer that never draws** — so both now jump to a date that has
one. **A pixel check has to be pointed at something before it means anything.** ⚠ The label check
counts the mark's lighter EDGE colour, not the navy body: the body is drawn either way, so a
`navyPixels` assertion would pass against a mark with no tag. ⚠ **Check 6 (the Missed layer's SCORE
filter) lives here rather than in a Missed-layer spec because this is the only suite that drives that
dropdown, and it reads the layer's COUNT rather than pixels — a pixel check cannot tell 35 markers
from 179.** ⚠ **Its "every score starts shown" assertion is what makes it non-vacuous: without it a
mutation defaulting `2/3` hidden PASSED.** ⚠ The Chart settings gear is a TOGGLE —
a second click closes the panel — and closing it via `.getByRole('button').last()` inside the panel
picks up the fib editor's own delete buttons instead.

**`tests/chart-trade-labels.spec.ts` (3, ~17s) — added 2026-08-20 with the *Annotate trades*
setting.** ⚠ **A fail-watch against HEAD is VACUOUS for all three** — the setting did not exist, so a
red only proves the row is absent. **Every one is watched red by MUTATION, named in its own comment**;
the middle one is also non-vacuous BY CONSTRUCTION, measuring the same pixels three times (on → off →
on). ⚠ **The drawing is measured in PIXELS and the diff is computed IN THE PAGE**: a trade annotation
is painted into klinecharts' canvas with no element of its own, so a check reading the toggle would
be asserting the toggle — and a full frame is millions of bytes, so a copy is parked on `window` and
only the count of differing pixels crosses into Node. 🔴 **Its first version PASSED VACUOUSLY at a
diff of 0**: the chart opens at the right edge, so every marker is BEHIND the viewport centre and
`Next marker` is enabled with nothing to step to — **an empty viewport is pixel-identical to a
setting that removed everything.** It steps `Previous marker` and asserts the Step pill is PARKED
before it measures anything. ⚠ **The restore is asserted as ~1% of the change, not as byte
equality**, and the residue was MEASURED rather than tolerated — 127 pixels in one dashed column,
the Step focus line repainted under a rebuilt trade box.

**`tests/chart-paging.spec.ts` (2, ~45s) — added 2026-08-06 with the go-to-date progress readout,
both watched RED against `HEAD`.** ⚠ **It drives the REAL backend rather than intercepting the
candles route, which is the opposite call from `calendar.spec.ts` and is deliberate**: the thing
under test is that the readout tracks pages ACTUALLY LANDING, so a mocked feed would be measuring
the mock's cadence. It keeps the jump short (~1 year, 2 pages) so it costs ~45s instead of the 90s a
full-history jump takes. ⚠ **The second check nearly shipped vacuous** — the progress bar carries a
3% floor so it is visible from the first frame, and `> 0%` would therefore pass against a completely
dead progress value; it asserts the width GROWS. Full detail: `ChartPanel/CLAUDE.md`.

**`tests/strategies.spec.ts` (11, ~38s) — added 2026-08-06 with the Strategies audit.** ⚠ **This is
the one suite in this folder with NO clean fail-watch, and the reason is recorded rather than
glossed**: the endpoints it covers changed shape (bare list → envelope) in the same pass, so the
page at `HEAD` fails against the new backend for reasons unrelated to any defect. Non-vacuity came
from **mutation** — remove a fix, confirm the test goes red — and that is what exposed a test of
mine that passed with the guard it named deleted. Full detail: *The Strategies page* above.

**`tests/stress.spec.ts` (11, ~44s) — added 2026-08-05 with the Stress Tests audit, and every one
of the 11 was watched to fail against the page at `HEAD`.** ⚠ **Two locator traps live here, and
both fail by PASSING**, which is the only kind worth writing down: `page.locator('svg').first()`
resolves to the **sidebar logo**, so a page-wide assertion that some element is absent passes on
the broken page too (the fan's no-limit-line check proved nothing until it was scoped to the fan's
own container); and a chart label exists three times over — the KPI card, the chart `<tspan>`, and
Recharts' hidden `#recharts_measurement_span` — so a bare `getByText` is a strict-mode violation
rather than a miss. Scope to `locator('tspan', { hasText })`. ⚠ Like the calendar's, this suite
intercepts one endpoint whole, so **it needs no live VPS** — only the backend and the dev server.

**`tests/tuning.spec.ts` (8, ~19s) — added 2026-08-05 with the Tuning workbench audit, and it was
WATCHED TO FAIL before it was kept.** Every one of the 8 fails against the page as it was at
`HEAD` and passes against the fix; a suite written after a fix and never run against the defect is
a description of the fix, not a test of it. Same mock discipline as the Overview's: the leaderboard
states that cannot be produced on demand — a grandchild, a sweep child wearing a tweak's
`source_run_id`, a 3-trade fluke at PF 99 — are built by MUTATING the real runs list and the real
run detail. ⚠ **Scope table locators to `.first()`**: the per-regime table further down that page is
also a `tbody` of rows whose second cell is a number, and an unscoped `td:nth-child(2)` silently
picks up three extra rows.

🔴 **Two of these tests broke on the DATA rather than on the code, and both were coupled to the lab
in a way a rendering test must not be (repaired 2026-08-06).** The Overview's disabled-job check
named `P&L Tracker` and `Reporter` — **the two scheduled jobs deleted on 2026-08-05** — so it was
asserting on a subject that no longer exists and failed for that reason rather than for the defect;
it now MUTATES the snapshot to force one job `DISABLED` and one `STOPPED`, so the rule survives the
fleet changing shape. The Stress Tests `not graded` check was a bare substring match that also
caught the reasons panel's heading and the reason line; it passed only while the lab held one row
whose reasons were empty, and became a strict-mode violation the moment a real ungraded row carried
them — `{ exact: true }` now scopes it to the badge. **A test that asserts on which rows happen to
be in the database is a test that will fail on a day nothing is wrong**, and the failure is
indistinguishable from a regression until somebody reads it. Mock the state; never name the data.

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

## `useHistoryLimit` takes the run's PARAMS, and omitting them is the defect (2026-08-15)

**A run can load more than its chart timeframe** — `exec_secondary` adds a 1m feed — and each
feed has its own broker floor, so the earliest legal date depends on the PARAMS, not just the
instrument and bar size. The hook takes them and sends the names of every truthy one as repeated
`&flags=`; the backend keeps the ones that mean a feed. Backend rules and the incident:
`../backend/CLAUDE.md` → *THE FLOOR IS PER-RUN*.

- ⚠ **Omitting `params` asks the chart-only question and gets a floor that is too EARLY**, which
  renders as a perfectly ordinary date picker offering a date the run will die on. Measured: run
  `50331c7cbe96` was offered 2018-09-13, accepted, and failed at 8% on a 1m feed whose history
  starts 2018-09-14.
- ⚠ **The frontend deliberately carries NO copy of which flags mean a feed.** It sends every
  truthy param name and lets the backend intersect. A copy here is the second claim about one
  rule that this app keeps being bitten by, and a feed added tomorrow would simply never reach
  the picker.
- ⚠ **`flags` is part of the QUERY KEY.** Two runs of one strategy differing only by
  `exec_secondary` have different floors and must not share a cache entry.
- ⚠ **In `RunBacktestModal` the hook sits BELOW the params state**, not beside the other window
  controls, because it depends on them — ticking the secondary moves the earliest date the
  picker accepts.
- ⚠ **`StackConfigModal` passes the UNION of the selected legs' truthy flags.** The legs share
  one window, so it is legal only if EVERY leg can be served. It drops `exec_secondary` in
  shared mode, because that path pins it off before running.

🔴 **`RerunModal` MOVES an illegal start to the floor and SAYS SO** (`rerun-moved-to-floor`).
This is the Retry path for a failed run, so the run in front of the reader may have failed ON
the floor — and before this the modal re-offered the same illegal date, so Retry could only fail
identically and the only way out was deleting the run. ⚠ **The move is announced, never silent**:
a silent clamp runs a window the reader did not ask for, which is the narrowing this repo refuses
everywhere else. They can type it back; the Rerun button stays disabled until the date is legal,
so nothing is decided for them.

## The Backtests list and the Backtest detail page — audited 2026-08-06

Aaron asked for an in-depth audit of both pages and then for the fixes. **27 findings; nine real
defects, three of them destructive.** The backend half is in `../backend/CLAUDE.md`; this is the UI
half, and every item shares the shape this folder keeps recording: **not one of them rendered an
error.** A rerun reported success. A caption contradicted the checkbox beside it. A rule silently
skipped the trades that matched two rules.

### The two destructive controls on the list, and the one that did not exist

🔴 **The row Rerun was ONE unconfirmed click, and a rerun replaces the run.** `retry.mutate(...)`
fired on the click, at 13px, inside a row whose own click navigates away, beside the chevron — and
it resets the row in place and discards its result, its charts and its evaluations. The detail page
has opened a modal for the same action since the day it existed. It raises to the page now, which
owns `ConfirmRerunModal`.

🔴 **There was no per-row DELETE at all, and the only reachable delete had no cascade warning.**
`deleteRunId` was never set, so `handleSingleDelete` and `cascadeMessage` were unreachable — and
`cascadeMessage` is the **only** place that says a delete takes attached optimizations, sweeps and
tuning iterations with it. So the one warning that names the blast radius was on the one path
nobody could reach, while the bulk checkbox path — which deletes the most — showed the generic
message. There is a row Delete now, and `bulkCascadeMessage` gives the bulk path the same warning
across the selection.

⚠ **Both raise to the PAGE rather than firing in the row.** The cascade sentence can only be
computed where the optimizations and sweeps lists live, and a row that can start a destructive
mutation on its own is a row one stray click from discarding a result.

**`fmtMoney` gained an `M` step.** `+$14387.5k` — five digits before a thousands suffix, harder to
read than the number it abbreviates, in the column whose whole job is comparing runs at a glance.
The same class as the `FitMoney` fix one page over.

**The bulk-delete failure toast stopped naming a cause it could not know.** It said "not found" for
every failure; a delete can also fail on a foreign key, a 409 or a dead backend, and `api.delete`
has already toasted each real reason. This line is a count, not a diagnosis.

### A caption that contradicted its own checkbox

🔴 **"Bank holidays · on by default"** — left over from when that rule really was hardcoded on, and
still on screen five days after **both** rules were defaulted OFF on 2026-08-01. This repo's
signature defect, sitting on the exact control that was rebuilt to stop it. **If a default changes,
the caption changes in the same commit.**

**`removeNewsChoice` went from `boolean | null` to a plain boolean.** The third state existed to
mean "the reader has not chosen, so fall back to the strategy's `avoid_news`", and that fallback
was removed with the same change. A three-state that only ever resolves one way is a state nobody
can reach, and it reads as though something still depends on it.

### The news filter's two rules did not compose

🔴 `if (in_holiday) {…} else if (in_news) {…}` — one chain doing both the COUNTING and the REMOVING.
A trade that was both took the holiday branch, so **ticking High-impact news with Holidays off left
that trade in the result, silently exempt from the rule you had just switched on.** The `else if`
was written for the counting rule (don't double-count against the total) and leaked into the
removal.

They are separate decisions now: the counts keep holiday-wins precedence, the removal is a plain
OR. Pinned by a browser check that tags exactly one trade as both, so the delta it asserts on can
only come from that trade.

### A drawdown percentage withheld with instructions the page gave no way to follow

🔴 Max DD% needs `balance`, which came from the primary evaluated ruleset's `account_size`. With no
evaluation the hero read `—` and the card said **"Set an account balance to measure drawdown as a
percentage"** — while the balance slider renders only when a ruleset default already exists. It
asked for something the page could not accept, and the backend had `max_drawdown_pct` stored on
that row the whole time (the Runs list shows it).

`defaultBalance` falls back to the run's OWN opening balance, recovered from the curve's first
point (`equity - profit`, exact arithmetic — `equity` is cumulative and anchored on it). ⚠ **That
is also the more correct denominator for a self-sizing run**, which compounds off its own deposit
and knows nothing about the account size of a ruleset it was merely graded against; the ruleset
still wins when present, because a prop limit is written against that account. The remaining
fallback message now says a run stored no equity curve, which is the only case left.

🔴 **`rebaseEquity` did not anchor on the opening balance, so it disagreed with the backend.**
`services/metrics.max_drawdown_pct` — what the Runs list renders — PREPENDS the opening balance;
the page started at `balance + profit[0]`. A drawdown is measured from a peak and the account's
first peak is the money it started with, so without the anchor a run that opens with a loss is
measured from a peak already below its own start. ✅ **MEASURED on the shape that decides it — a
run down 40% from $10k that never regains the start reads 25% without the anchor and 40% with it.**
One number, two definitions, two places.

### Three things the cost pill and the failure banner were not saying

🔴 **A partly-priced re-price rendered as "Charging nothing".** If the server returned fewer priced
trades than the curve holds, `view` was null → `active` false → the pill read *Charging nothing*
with the reader's boxes still ticked. The view is right to refuse the short answer — a partly
charged book shown as a charged one is worse than no charge — but the refusal has to reach the
reader. It is a third state now (`partial` / `partialOf`), distinct from `failed` (the server
refused and said why) and from inactive (nothing ticked).

🔴 **The excursion bars were not re-priced**, so the solid net-result core could stick out past its
own translucent favourable halo — which reads as a broken chart. `favorable`/`adverse` shift by the
charge and are then CLAMPED around the new profit, because a halo the result escapes is the one
shape that bar can never draw.

🔴 **`FailureBanner` declared `onRetry` and the page never passed one**, so the banner's Retry
button did not exist — on the one banner a reader is looking at because something failed. It was
wired to `RerunModal` for a standalone run and to the direct re-fire for a sweep child or optimizer
combo, and disabled while that platform held a job (the backend 409s, and a button whose only
outcome is an error toast is not a button).

⚠ **SUPERSEDED 2026-08-15 — THE BANNER HAS NO BUTTON AGAIN, AND THAT IS NOT THE OLD BUG.** The
fix above was right that the control was missing and wrong about where it belonged: the page
HEADER already carries a Retry firing the identical action a few inches up, so the page ended up
with two controls for one destructive action — two places for the disabled state and the period
gate to drift apart. Aaron, from the screen: *"I don't need the double retry buttons, keep the one
outside."* **The banner's job is to say what FAILED.** ⚠ **The props were REMOVED, not left
unused** — a declared-and-never-passed `onRetry` is precisely what made the component look like it
had a button when it did not, so leaving it behind re-arms the original defect. ⚠ **The browser
check was FLIPPED rather than deleted**, and now pins the COUNT (`exactly one Retry, and not on
the banner`) asserting BOTH halves: deleting it would leave nothing stopping the next reader
re-adding the banner button as a fix for the original defect, whose reasoning still reads as sound.

**Worst streak was blank on every per-firm sized view.** `effRun` NULLED `worst_losing_streak` so
it would recompute from the sized daily P&L — but a streak is counted in TRADES and
`FallbackMetrics` deliberately carries no daily answer for it, so it recomputed to nothing. It is
computed from that firm's own equity curve with the exported `worstLosingStreakOf`.

### The running banner — one bar, and its width IS the progress (2026-08-20)

🔴 **A progress bar whose speed is unrelated to the progress is worse than no bar** — it teaches
the reader that the number on it means nothing. `RunningBanner` drew a row of NAMED STAGES as
evenly-spaced dots (`Load bars` / `Replay` / `Results` for a python run, five more for NT8) with
the fill drawn in the connectors between them, and **equal widths carried wildly unequal work**:
loading bars was 0–15% of the run and got half the bar, stepping 156,721 bars was 15–94% and got
the other half. The fill sprinted to mid-screen in seconds and then crawled for minutes, and each
stage change snapped one connector full while the next started at zero — which reads as the bar
falling back. Aaron, 2026-08-20: *"sometimes it shoots up and it shoots back down… very
inconsistent."* It is now ONE bar filled to `pct`, and the stage names are gone — *replay* was
internal vocabulary for stepping the strategy over the bars and said nothing to the person
watching. The words moved to the message line underneath, where a sentence has room to be one.

🔴 **`/lab/progress` IS ONE FILE FOR THE WHOLE APP, and that is the other half of "shoots back
down".** It describes whatever job wrote it last, so a second backtest, an optimization or a sweep
starting anywhere overwrites it — this page stops recognising the job id and used to substitute
zeros: the bar emptied, the message fell back to *Starting…* and the elapsed clock restarted, on a
run that had not slowed down. It now keeps the last report that BELONGED to this run
(`ownProgressRef`), which is the honest answer — a zero there is a statement about somebody
else's job wearing this run's banner. ⚠ **It holds the last real report; it never invents one.**
⚠ **Cleared when a rerun gives the same id a new start time.**

⚠ **The pct itself had to move too, and that is in `backend/CLAUDE.md`** — a bar can only be
proportional if the number behind it is. ⚠ **ONE hold, not two.** The first attempt also held a
running maximum inside the banner, and with both in place **reverting the real fix left every
assertion green** — either mechanism alone kept the bar full. Watched RED by mutation:
`tests/backtests.spec.ts` → *another job stealing the shared progress file cannot empty this bar*
reports `0%` against the old ternary. The bar and its percentage carry `run-progress-fill` /
`run-progress-pct` so the check reads the element it means.

### The finished-run params panel — plain names, three tiers, collapsible (2026-08-20)

🔴 **It printed FIELD NAMES** — `exec_nogap_arm`, `exec_sl_buf_tk`, `aplus_window` — so the one
surface that records what a finished run actually charged was unreadable without the source open.
Aaron: *"the parameters is the names of the variables in the code… this makes no sense for me when
I look at it."* Every row now shows the words from the strategy's own metadata, and the values with
it: a bool reads as its two option labels (`Arms setups` / `Ignore`) rather than `true`/`false`, and
a number carries its unit (`4320 minutes`, `0 ticks`).

🔴 **A SECOND NAME, `short`, EXISTS BECAUSE THE EDITOR'S LABEL IS WRITTEN TO TEACH.** *Max time:
sweep → SOS (minutes)* is right on the run form and wraps to three lines in a 248px rail, burying
the value under the explanation. Aaron: *"don't be too verbose and try to explain params in the
side bar… they just have to be simple english names."* So `short` is the same setting named in as
few words as possible (*Sweep → SOS window*), read through the exported `shortLabelOf`, and `label`
stays what the editor shows. ⚠ **Authored in the meta, never DERIVED** — stripping parentheses and
units mechanically produces a name nobody chose. ⚠ **Optional everywhere**: no `short` falls back
to `label`, which is what `mpc_bleg` and `mpc_bos` do today; `mpc_sos_fade` carries one for all 83.
⚠ **Units belong to the VALUE** — the row already renders `4320 minutes`, so a `(minutes)` in the
name says it twice. ⚠ **`strategy_scanner._PARAM_META_KEYS` is a WHITELIST and `short` had to be
added to it** in the same commit, or the key is dropped in silence and the panel looks unchanged.

🔴 **THREE TIERS, EACH DIFFERING IN MORE THAN ONE WAY.** The first pass got the words right and
left them all at one weight and one colour: *"I need the parameter categories and keys to stand out
from the values… right now everything is very flat."* Category = gold, bold, uppercase, tracked,
rule above (the same treatment `ParamEditor`'s compact group headers carry — one shape learned
twice); setting = 10.5px tertiary regular, the question, which should recede; value = 12.5px
semibold primary `tabular-nums`, the answer, and the only thing on the row that differs run to run.
⚠ **Size alone will not carry it at these sizes** — 10px against 12px is nearly invisible in a
248px rail, so every tier moves colour AND weight AND size. The three are constants
(`TIER_CATEGORY` / `TIER_SETTING` / `TIER_VALUE`) so the folds cannot drift from the main list.

🔴 **SECTIONS COLLAPSE, AND THE STATE TRACKS WHAT IS SHUT — NEVER WHAT IS OPEN.** A set of OPEN
groups starts empty, which renders every section collapsed on first paint, and this panel exists to
show at a glance what ran. ⚠ **A shut section still states its COUNT**: a collapsed group with no
number reads as a group with nothing in it, the one thing a record of a run's inputs may never
imply. ⚠ **ONE expand/collapse-all icon in the header, and it offers the action the panel is not
already in** — two buttons leave a dead one on screen at each extreme, and a control that does
nothing when clicked reads as broken rather than as already-done. ⚠ **`allShut` is derived from the
groups that EXIST**, never from a count held beside the set.

🔴 **The `useState` went in BELOW this component's `if (!entries.length) return null` and that is a
crash, not a lint opinion** — *Cannot access 'shutGroups' before initialization*, on the first
click. Caught by driving the real page, not by the typechecker, which was green throughout. Hooks
go above every early return.

⚠ **The two folds were renamed because their headings were internal vocabulary.** *"What does the
settled section even mean?"* — `Settled` is now **Already decided** (*tested, answered, and taken
off the run form; still sent — this run used these*) and `Foundational` is **Instrument & broker**
(*what was traded and how it filled, not how it decided*). Same sets, same rules, said in words.
⚠ **The editor still says "settled" on its own count** — that one can follow if it reads badly
there too, but it is a different surface with a different reader.

🔴 **A SETTING WHOSE PARENT IS OFF DID NOTHING ON THIS RUN, SO IT IS FOLDED AWAY TOO.** Fourteen
secondary re-entry rows sat in the main list on every run with the secondary switched off, and the
same shape repeats through every cascade in the schema (*"if secondary trades is off in the
strategy you DON'T need to show all the params related to it… same goes for anything cascading"*).
Asked of `isOutOfPlay`, exported from `ParamEditor` — a `show_if` that does not hold, or a
`disable_if` that does. ⚠ **The EDITOR must not use it**: there, `show_if` hides and `disable_if`
GREYS, and that difference is deliberate; here there is one question — did this setting do anything
— and both answers are no. ⚠ **The PARENT toggle stays in the main list.** A section that empties
completely reads as one that does not apply to this strategy; leaving the switch visible says WHY
the rest is gone. ⚠ **FOLDED, never dropped** — same rule as a settled param. ⚠ **It shares the
"Already decided" fold, so that caption names BOTH reasons a row lands there**, or half its
contents look mis-filed. Measured on the pinned run: the secondary section went 3 rows → 1, entry
zone 4 → 3, sessions 2 → 1, and the fold 26 → 31.

⚠ **Rows are STACKED and grouped**, for the same reason `ParamEditor`'s are: a sentence has no
chance in the ~120px a right-aligned value leaves in a 248px rail, and a truncated label is the
same defect as a field name. Group headings and their ORDER come from the metadata, which is the
order the strategy decides things in. ⚠ **A param with no metadata entry falls back to a prettified
field name rather than vanishing** — this panel is the RECORD of what the run sent, so nothing may
be dropped; `fill_model`, `symbol`, `mintick`, `point_value` and `daily_close_hour_ny` are the live
cases. ⚠ **`fillTokens` runs here too**, against this run's own values, or a toggle reads
`{exec_sl_level}` on the page two clicks from the editor showing `0.886`.

⚠ **`tests/param-gates.spec.ts` asserts on the WORDS** (`RSI length`, not `div_rsi_len`) — every
param in `mpc_sos_fade`'s metadata carries a unique short name, so a name still identifies a row
exactly. Three checks, all watched RED by mutation: the fold, sections-start-open (flip the set to
track what is open), and the all-in-one icon.

### Efficiency, measured

- **Two `/log` polls during a run, not one.** `RunningBanner` asked for 500 lines and
  `LogsSection` for 200 — `lines` is part of the query key, so that is two cache entries and two
  requests every 2 seconds for the whole run. Both ask for 200. ⚠ If that ever needs to change,
  change both call sites together or the duplicate comes straight back.
- **The run page pulled the whole lab to draw one badge.** `useBacktestRuns()` unfiltered, on the
  argument that it shared the Runs list's cache entry — true while the sidebar held that entry on
  every page, and no longer true since the sidebar moved to `useNavActivity`. It is scoped to
  `source_run_id` now. ✅ **MEASURED: 20.6 KB → 0.002 KB, 10.5 ms → 5.3 ms.** ⚠ Always pass the
  filter — `useBacktestRuns(undefined)` fetches everything.
- **Five backtest hooks toasted their errors twice.** `api.request` already toasts the server's
  `detail`, and `ApiError`'s own docstring forbids toasting on top; the generic message landed
  SECOND and buried the real reason — the history floor's 400 names the earliest date the broker
  has, which is the sentence worth reading. ⚠ The branch in `useTriggerBacktest` could not fire
  anyway: it read `.detail` off an `unknown` that only carries it on an `ApiError`.

### The `python` lock scope never reached the browser

🔴 **`GET /backtests/running-job` named `nt8` and `mt5` and never passed `python`**, and
`RunningJobStatus` declares that field with a `running=False` default — so the omission was silent
and **a python backtest reported its own platform free for its entire run.** Found by DRIVING the
Stop fix against a real backtest, not by reading anything.

Nothing on this side was wrong: `lib/runner.ts` resolves the scope correctly and `runningJobFor`
reads it. But every control gated on it — **the Runs list's Rerun, this page's Retry and Rerun, the
Run modal, the Optimize button** — stayed enabled through a python run, and the backend's gate
(which was never broken) then answered `409`. **A button whose single outcome is an error toast.**
Fixed in the router by DERIVING the response from the scope map; see `../backend/CLAUDE.md`.

⚠ **The lesson for anything reading this shape: a `running: false` from that endpoint was
indistinguishable from a scope nobody had answered for.** The frontend cannot detect the
difference and should not try — but when a gate and its button disagree, suspect the payload before
the predicate.

### `tests/backtests.spec.ts` — 11 checks

**10 of the 11 were WATCHED TO FAIL against the page at HEAD.** The 11th could not be: it needs a
`data-testid` that is part of the fix, so its non-vacuity was established by **MUTATION** — remove
just the `onRetry` prop, confirm red, restore, confirm green.

🔴 **And that test was VACUOUS on its first attempt, which is why the mutation step exists.** It
asserted a page-wide `Retry` button and PASSED against the broken page, because **the page HEADER
carries its own Retry** — the locator was matching a control that was never in question. Same trap
as `page.locator('svg').first()` being the sidebar logo. **A green new test proves nothing until
you have seen it red for the RIGHT REASON.**

⚠ **It asserts on MUTATED state, never on which rows are in the lab today.** The Overview and
Stress Tests suites both broke on the data rather than on the code, and a test that fails on a day
nothing is wrong is indistinguishable from a regression until somebody reads it. ⚠ A cost rule is a
`<button>`, not a `<label>` — `CostRule` renders its own checkbox glyph so a locked row can be
disabled.

## The Strategies page — audited 2026-08-06

Aaron asked for a full audit of the page (Strategies tab, Deployed tab, Scan) with one reported
symptom: **"if the NT8 agent is down I get this annoying error about remote end closed connection
without response, every couple of seconds."** He was describing a toast storm, and the storm turned
out to be the visible edge of a page that could not distinguish *the VPS says no* from *nobody
asked the VPS*. The backend half is in `backend/CLAUDE.md` → *The Strategies page — the 2026-08-06
audit*.

🔴 **A toast is an EVENT; a dependency being down is a STATE.** `api.get` toasts on every non-ok
response, and both strategy-file queries are on a `refetchInterval` — so one unreachable agent
produced roughly **six error toasts a minute for as long as the page was open**, plus a burst on
every window focus, each one duplicated by an `onError` handler that toasted the same failure a
second time. `request()` now takes `RequestOpts { silent }`, both polling hooks pass
`{ silent: true }` with `retry: false`, seven duplicate `onError` toasts are gone, and the failure
is **rendered** — `AgentDownBanner` on both tabs, driven by the `nt8_error` / `mt5_error` fields on
the new envelopes. ⚠ **`silent` suppresses the TOAST, never the error** — `isError` and the payload
both still reach the caller, and using it anywhere the caller does not render the failure would be
converting a loud bug into a quiet one.

🔴 **With sync-status down, a strategy that needed deploying offered a Run button.** The endpoint
502'd, every row lost its `sync` object, and `sync === undefined` fell through every pill and every
guard to the default action. **An absent answer took the shape of a healthy one.** The action cell
is now gated — `isPython || sync !== undefined` — and renders a plain `unknown` otherwise.

🔴 **The version chip named the wrong version.** `liveVer` read `needs_compile ? deployed_version :
(compiled_version ?? deployed_version)`, so on a strategy deployed but not yet compiled it reported
the DEPLOYED version as what was running — while NT8 and MT5 both execute the **compiled**
artefact. It is `sync.compiled_version` full stop now, and the tooltip says *compiled vN is what
runs*.

⚠ **`file_exists_on_vps` was returned by the backend and rendered by nothing**, so a deployment
whose file had been deleted off the box read green **In sync**. It draws **Missing on VPS** now,
with the action reading **Redeploy** — and 🔴 **my first fix reintroduced the exact contradiction
it existed to remove**, adding the red chip BESIDE the hash-derived pill so the row showed green
*In sync* next to red *Missing on VPS*. **The browser check caught it; reading the diff had not.**
The status is one ordered-exclusive chain: `Needs deploy → Missing on VPS → Needs compile → VPS
unknown → In sync`.

**Also:** the compile modal had **no way out while a job ran** (footer Close renders only on
completion, and a hung poll never completes) — it now has a header X, an Escape handler, and reads
`isError` so a failed status poll ends the spinner instead of spinning for ever. The Reconcile
button reads `strategy.is_orphan` off the row rather than `scan.data?.orphans`, so a deleted source
file is visible on load instead of only after somebody presses Scan. The market filter moved into
`?market=`, and both `setSearchParams` calls **merge** rather than replace — `setSearchParams({tab})`
drops every other param, which is how the tab switch would have silently cleared the filter.

**`tests/strategies.spec.ts` — 11 new checks.** ⚠ **A clean fail-watch against `HEAD` was
impossible and was NOT done**: the two endpoints changed shape from a bare list to an envelope, so
the old page fails against the new backend for unrelated reasons. Non-vacuity was established by
**mutation** — each fix removed in turn, the naming test confirmed red. 🔴 **That found a test of
mine that could not fail on the defect it named**: deleting the Run-button guard left *"a strategy
that needs deploying still says so with the agent down"* green, because that mock sets
`needs_deploy: true` and Deploy renders either way. A separate test (*"a whole sync failure never
leaves a deploying strategy offering Run"*) fails the entire sync request and **does** go red
without the guard. **A green new test proves nothing until you have seen it red — and "I watched
the suite go red" is not the same claim as "I watched THIS test go red for THIS reason."**
⚠ **Locators here key off the platform badge `img`, not the name** — the Name column renders the
display name (*Opening Range Breakout*), not the class name (*ORB*).

## A stack renders a RUN's panel — same four cards, and the legs are the Verdict card's rows

**Rebuilt 2026-08-10, Aaron's call, in his words: *"it should look exactly like a single run
backtest page… I don't want stack stuff here and a regular backtest details page to look two
different. Unless there's some cumulative thing that I need to watch."*** Plus: *"the strategies on
your stack could be toggled from within the verdict section, and the KPIs and everything should
change as you toggle them."*

`StackDetail` already reused `PerformancePanel`, so the numbers were computed identically — and the
page still read as a different feature, because everything AROUND the numbers differed. It had a
full-width strategy ribbon where a run has a Verdict card, three cards where a run has four, a
plain `<h2>Performance</h2>` where a run has a collapse control, and the leg toggles in a section of
their own two scrolls down. Now:

- **Four cards, Verdict first**, via the panel's `verdict` slot. A stack has no ruleset to grade
  against, so that card answers the question that IS a stack's own — what is this made of — with
  the same hero a run puts there (the trade count) and the same cadence line under it.
- **The legs are `PanelRow`s inside it, and each row is the toggle.** That is the point of moving
  them: the control that decides what Made / Risked / Trusted count now sits in the same row as the
  numbers it recomputes. A leg that cannot be toggled — still replaying, failed, or the last one
  left on — is still LISTED, dimmed, with the reason on its ⓘ: *not finished* and *not in this
  stack* are different answers, and hiding the first makes a stack look smaller than it is.
- ⚠ **`PanelRow` gained `onClick` / `lead` / `muted` rather than the card forking its own row
  markup.** A second private copy of that anatomy is exactly how the fourth card drifts out of line
  with the three beside it — the same argument that moved `panelCardCls` / `CardHead` / `CardHero`
  to module scope when the verdict became a card.
- ⚠ **The Verdict card passes `collapsed: false` ALWAYS.** The panel's collapse means *hero numbers
  only*; the leg rows are a CONTROL, not a supporting metric, and hiding them would put the toggles
  behind a preference the reader last set on a different page.
- ⚠ **`usePerfCollapsed` is ONE hook behind ONE key, exported and shared.** A second copy of that
  state would mean the same control on the same panel remembering two answers depending on which
  page you pressed it on last.

## A leg toggle swaps in the SOLO CONTROL — it does not slice the shared book

**2026-08-10, and this is the rule that makes the toggles trustworthy.** `composeCombined` takes
the stack's `mode` and returns a `basis` naming which book produced the numbers:

| basis | when | what it shows |
|---|---|---|
| `screen` | the stack is a screen | every leg had its own full account, so any subset is honestly additive |
| `shared` | every leg on | the shared replay, exactly as it ran |
| `solo` | one leg on, and it has a stored control | that leg's SOLO replay — genuinely *if the others never existed* |
| `unmeasured` | anything else | nobody replayed it, so there is nothing to show |

🔴 **Before this, a subset was composed from the SHARED trades**, which answers *what did this leg
contribute to an account the others built* and reads as *what this leg made*. Measured on
`st_94aeb25f0c`: MPC B-LEG posts **99 trades and +17.8674R either way, at identical entry and stop
prices**, and reads **$47,758,999 shared against $21,064 alone**, because inside the stack its last
trade risks $16,925,791 of a balance A+ grew rather than $3,102 of its own.

- ⚠ **`unmeasured` still renders the Verdict card.** The leg toggles live inside it, so hiding the
  Performance panel would leave the reader in a state they cannot click their way out of. The three
  KPI cards are replaced by `UnmeasuredCard`, which states what DOES exist and offers the way back.
- ⚠ **A subset of a SCREEN is never refused.** There nothing could block anything, so removing a leg
  removes only its own trades; a screen needs no control book and must not ask for one.
- ⚠ **The per-leg row value is R.** It is the only per-trade figure a change of position size cannot
  touch, so it is identical shared or solo — which is exactly why the row leads with it. The row used
  to print a trade count with *"It made `<net_pnl>` on its own account"* on its tooltip, and on a
  shared stack `net_pnl` is the leg's dollars INSIDE the portfolio, so that sentence was false by
  2,266x on the measured stack. The tooltip now names BOTH figures and says which is which.
- ⚠ **`legTrades` and `legR` cover every COMPLETE leg, not only the enabled ones.** They are facts
  about a leg, and falling back to a different unit when the reader switches it off made one row read
  `+17.87R` and the other `160` on the same card. The duration weighting reads the book directly for
  the opposite reason — averaging in legs that are switched off describes a portfolio nobody is
  looking at.
- ⚠ **`BasisChip` is beside the Performance heading, not in a tooltip.** It changes what every number
  under it MEANS, and the figures jump by orders of magnitude between bases, so a silent swap is its
  own defect even when each number is right.
- ⚠ **`EquityPoint.r` had to be declared on the BACKEND model to reach here** — the fifth field that
  model has dropped while it sat on disk. See `../backend/CLAUDE.md`.
- ⚠ **A shared stack replayed before 2026-08-10 has no control book**, so it lands on `unmeasured`
  rather than inventing one. `backend/scripts/backfill_stack_solo.py` re-derives it.

## A loss-recovery leg is a TICK BOX ON ITS PARENT, never a row in the picker (2026-08-21)

`StackConfigModal` nests one checkbox under the selected strategies: *Also run loss recovery on
&lt;leg&gt;'s losses*. It sends `recovery_parent`. Backend rules: `../backend/CLAUDE.md` →
*A stack leg may READ ANOTHER LEG'S LOSSES*.

🔴 **The rule is FILTERED OUT of every picker on `Strategy.requires_source`** — the stack builder's
list and the Strategies page's stackable set. It has no setups of its own, so picking it as an
ordinary leg builds a stack with nothing to read, and **an empty book is indistinguishable from a
rule that found no setups**. The alternative shape — listing it beside the real strategies with a
"recovers:" dropdown — was rejected: it lets you build a stack with no parent, or the wrong one,
and the run then refuses AFTER the reader has filled in the form. **A dependency the UI cannot
express becomes a runtime refusal, which is a worse version of the same rule.**

🔴 **THE STRATEGIES LIST IS A TREE (2026-08-21).** `ordered` groups each row under the strategy
its own package declares (`Strategy.display_under`), so the loss-recovery rule sits directly beneath
the bot it recovers instead of wherever the alphabet put it. ⚠ **The indent lives INSIDE the name
cell**, never on the `td` and never as a spacer column — padding the cell shifts every column to
its right out of line with the header, and the table's own column widths are what keep
Platform/Params/Runs/Status aligned. ⚠ **A child whose parent is not in the visible list renders at
the TOP level rather than disappearing** — the market filter hides rows, and a strategy vanishing
from this page is how somebody concludes it was deleted. ⚠ **A cycle appends the unemitted rows
instead of dropping them**, same reason. ⚠ **Display only** — nesting changes nothing about how a
strategy runs, stacks or deploys.

🔴 **THE STACK BUILDER COUNTS LEGS, NOT TICKED STRATEGIES (2026-08-21).** `settingsReady` required
two ticked strategies and the Strategies page's Stack button required two before it would even
open — so **A+ with a recovery on A+, the stack this whole leg exists to make possible, was greyed
out at both doors and refused by the backend behind them.** The count is now
`selected.size + (shared && recoveryFor ? 1 : 0)`, matching `_validate_stack_strategies`, and the
list-page button opens at ONE ticked strategy because the recovery is ticked inside the builder,
where that button cannot see it. ⚠ **Opening is not running** — the builder still refuses to submit
under two legs. **Nothing here was broken; the path just could not be walked, and every piece of it
had been tested on its own.**

⚠ **`recoveryFor` holds the PARENT's id, not a boolean and not a set** — at most one recovery leg
per stack, because two would share a name on the shared account. Unticking a parent clears it, or
the request names a leg that is not in the stack.

⚠ **Never sent on a SCREEN.** There every leg trades its own full account, so the recovery could
never take room off its parent — the only question it exists to answer. The backend refuses it;
this never sends it.

⚠ **The Strategies page GREYS its Run button (*Needs a parent*) rather than hiding it**, with the
reason on the title. Same rule as an unassignable account on the Accounts tab: a control that
vanishes reads as a feature that does not exist, and a reader who came looking for the rule needs
to be told where it went.

🔴 **AND SO DOES `StrategyDetail.tsx`, WHICH WAS MISSED AND IS THE WHOLE LESSON HERE (2026-08-21).**
Filtering the pickers and greying the LIST page's Run left the rule's own detail page with an
unconditional Run Backtest button and a full Run modal — so it could still be run alone, from the
UI, in two clicks. **A strategy is reachable from more than one place, and guarding the list is not
guarding the strategy.** Both pages now read the same flag and render the same disabled button with
the same title. ⚠ **The button is a LABEL either way** — the gate is `routers/_source_guard.py`,
which refuses every endpoint that starts a job from a strategy id; see `backend/CLAUDE.md`. There
is no automated test on either button, because Playwright is out of the suite by design.

## A NEW stack is always a SHARED ACCOUNT — the mode picker is gone

**2026-08-10, Aaron's call:** *"I would never ever ever wanna do a screen. I would always wanna do
a shared account, because that's what a stack IS — we're sharing the same resource. I wanna know
how two strategies affect each other and where some trades are dropped because others have taken up
all the capacity."*

A `screen` runs each leg on its own full account and adds the results up, so nothing can ever block
anything. Offering it beside `shared` as an equal choice in `StackConfigModal` made the one mode he
wants a coin flip — **and it was the mode a `?? 'screen'` default silently picked.**

- ⚠ **This is NOT a removal of screen support, deliberately.** Three stacks in the lab are screens,
  `StackDetail` still renders them with their `Screen · upper bound` chip, and a RERUN carries its
  own mode forward through `initial.mode` — so rerunning a stored screen does not silently turn it
  into a different experiment. What is gone is the way to make a NEW one. Deleting the mode
  outright would rewrite what those stored rows mean.
- The mode paragraph is derived from `shared` rather than removed, so a screen's own rerun modal
  explains what it is and says new stacks are shared accounts.

## The shared-account panel — every fact kept, the prose moved to its ⓘ

**Condensed 2026-08-10.** Aaron: *"does this section need to be so verbose? Like I'm reading a
storybook."* It was three big figures with nothing saying what any of them was FOR (*"one account,
the screen promised, peak open risk — I don't know the significance of these things"*), then a
rewrite that kept every explanation as body text, which was four paragraphs nobody re-reads.

It is now three lines: the peak risk with its meter, a refused/not-refused chip, the cap and
concurrency caption, and a `together $X · apart $Y · +$Z` row sharing a line with the disclosure.

⚠ **The rules those paragraphs stated are load-bearing and are NOT deleted — they are one hover
away.** Two in particular, and both have a browser check that HOVERS rather than reading the chip:

- **An empty contention log still has to read as a measurement.** *"Nothing was ever refused… open
  risk is measured to each trade's CURRENT stop… read it as 'the budget would rarely have had
  anything to arbitrate', never as 'a cap is unnecessary'"* lives on the chip's ⓘ. Asserting only
  the chip would pass against a build that dropped the explanation entirely, which turns a measured
  result back into a number nobody can interpret.
- **The together-vs-apart gap still has to name COMPOUNDING.** Read as risk it is alarming; it is
  one balance both strategies grow, and `docs/SHARED_RISK_STACK.md` predicted the opposite SIGN
  from exactly that misreading before the first real run disproved it.

⚠ **The per-strategy table stays behind a disclosure that OPENS ITSELF when there is contention** —
on every run measured so far its Shrunk / Blocked / Risk-refused columns are entirely em-dashes.

## The regime overlay is OFF by default, from ONE hook

**2026-08-10.** Aaron: *"Regimes, take it off by default. I don't wanna see the regimes on the
equity curve — that's the same thing whether I'm on a backtest, a stack, an optimization, a tune,
all those pages that have equity curves."*

🔴 **There were THREE definitions of this preference and only one of them persisted anything.**
`BacktestDetail` had `getOverlayPref`/`setOverlayPref` (stored, defaulting ON); `StackDetail` and
`TuningWorkbench` each had a bare `useState(true)`. So switching it off on two of the three
surfaces did not survive a navigation, let alone a reload — the same shape as the Sharpe formula
this folder already records three private copies of.

`useRegimeOverlay()` in `components/RegimeOverlayToggle.tsx` is the single one, and it lives with
its CONTROL rather than in whichever page wanted it first.

⚠ **The default is expressed as the polarity of the stored check** — `localStorage.getItem(_KEY)
=== 'true'`, so an unset key reads OFF. The old `!== 'false'` spelling is what made it default ON;
flipping the default means flipping that comparison, **never adding a second key**, or a reader
who already answered gets asked again under a different name.

## The portfolio line is green and no leg may be confusable with it

🔴 **`LEG_COLORS` was `C.series.filter(c => c !== C.pos && c !== C.neg)`, and exact string
inequality cannot express "not confusable with".** The palette holds near-misses: `series[1]` is
`#00ff7f` against `C.pos`'s `#00ff82` — three units apart in one channel, the same green to any eye
— and `series[5]` is `#ff3b5c` against `C.neg`'s `#ff496b`. Both passed the filter, so the second
leg of every two-strategy stack drew in the PORTFOLIO's own colour and the legend showed two green
swatches. Reported off the screen (2026-08-10).

It is an explicit list now — cyan / amber / violet / blue. ⚠ **Keep it explicit rather than a
filter over `C.series`:** a filter is a rule that silently re-breaks the day somebody adds a colour
to the shared palette.

🔴 **One of the three new browser checks was VACUOUS on its first run and passed against its own
mutation.** `panel.locator('table')).toHaveCount(0)` asserted straight after `goto` is satisfied
while the PANEL is absent too, so it was green against a build that renders the table
unconditionally. It waits on the panel's own disclosure button first now. **Fourth instance of this
trap recorded in this folder** (`svg.first()` being the sidebar logo; a page-wide Retry matching the
page header's; a page-wide Rebuild matching the host's chrome behind a fullscreen overlay) — and the
only reason it was caught is that the mutation was actually run rather than reasoned about.

## Shared-account stacks — the mode has to be on screen before any number is

**Landed 2026-08-09.** `StackConfigModal` (mode toggle + account fields), `StackDetail`
(`SharedAccountPanel` + the header chip), the Stacks list's **Mode** column, `useStackContention`.
Backend and the measured first run: `../backend/CLAUDE.md` → *Shared-account stacks*.

**A stack is one of two DIFFERENT experiments over the same legs**, and everything here follows
from that. A `screen` adds up N standalone runs — every leg sized as if it owned the account and
nothing could block anything, so it is an UPPER BOUND. A `shared` stack replays them together on
one balance with one risk budget. Two rows in the list, over the same legs and window, reporting
different numbers, with nothing to tell them apart, is a comparison the reader cannot make.

- **The mode chip is in the HEADER, beside the window** — before the performance panel, because it
  changes what every number below it means.
- **A screen's chip says `upper bound`**, which is the entire reason it carries a chip at all
  rather than the shared one carrying the only badge. *This is a screen* is not the useful half;
  *nothing here could ever block anything* is.
- **The Rerun modal carries the mode and its knobs forward.** A rerun that silently reverted to a
  screen would be a different experiment under the word "rerun", reporting different numbers with
  nothing on screen accounting for it.

### The panel, and the three things it must not render as blanks

- **The headline delta is computed off the SOLO CONTROLS** (`solo_closing_balance` per leg, minus
  the shared opening balance once). Those controls ARE the screen — each leg on its own full
  account — so it is a like-for-like comparison against a replay that really happened rather than
  an estimate of one.
- ⚠ **An empty contention log is rendered as a MEASUREMENT, in words.** It is the EXPECTED state,
  not a missing one: open risk is measured to each trade's CURRENT stop, so a stop moved to
  breakeven releases its room before the other strategy asks, and the measured 6.5-year two-bot run
  refuses nothing at all. A panel that goes blank there is pixel-identical to one that failed to
  load.
- ⚠ **`available: false` is THREE answers** — this is a screen, it is still replaying, or it
  failed — and the panel renders a different thing for each. `progress` separates the second;
  `stack.mode` separates the first. The **test seam is on all three branches**, not only the
  finished one, or a check for "it says what it is doing while running" can never find it.
- **The seam check is rendered.** With a full budget a leg must post the same R shared as solo (R
  is normalised to the trade's own risk), so a difference is the shared account moving a decision
  it must not touch. That is invisible in a table of numbers unless something says it.

⚠ **The panel sits ABOVE the strategy chips**, which toggle legs in and out of the combined view.
The budget is a property of the run as it happened, not of whichever legs are currently ticked.

⚠ **Contention MARKERS on the price chart are deferred and named** (`docs/SHARED_RISK_STACK.md`).
Every measured run so far refuses nothing, so a marker layer would be a generic mechanism nobody
has ever exercised — the trap this folder already records for the `BOX` template's label path,
whose first real user was its first test. The events are served and rendered as a table instead.

### `tests/stacks.spec.ts` — 10 checks, and three of them were vacuous first

Non-vacuity here is by **MUTATION** and could not be anything else: none of this existed at HEAD,
so every check would go red on an element being absent, which proves the locator and nothing more.
Each check names its mutation in a comment. The three that passed when they should not have are
worth more than the seven that worked:

- 🔴 **Every route mock keyed on `http://localhost:8000` and matched NOTHING.** The app fetches
  through the Vite proxy — `api/client.ts` is `const BASE = '/api'` — so three checks silently read
  the LIVE lab and asserted on whichever stacks happened to be in the database that day. **Route on
  `u.pathname` against the `/api` prefix**, the idiom `tuning.spec.ts` already uses.
- 🔴 **"A screen renders no shared panel" passed against its own mutation.** The hook is disabled
  on a screen, so the report is `undefined` and the panel cannot render whichever way the render
  guard is written — **the render guard and the fetch guard are not separable from the DOM.** It
  counts the FETCH now, which is the real guard: a poll enabled on a screen gets `available: false`
  back and leaves a finished screen showing a permanent "replaying the strategies…" spinner.
- 🔴 **The counter that fixed it was registered BEFORE the mock, and was shadowed.** Playwright
  matches the most recently registered route first, so the counter never incremented and the
  assertion was trivially true a third time.

**The standing lesson is this folder's fail-watch rule one notch further.** It already says it is
not enough to watch the SUITE go red — you have to watch THIS test go red for THIS reason. These
three add: you also have to know the OBSERVATION the test makes is one the mutation can change. All
three were green, well-named, and asserting on something the defect could not move.

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
`algos/notifications/log_review.py` writes hourly after reading the bot's own health record.

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

## The version banner — "am I behind, and by how much" (2026-08-07)

`VersionBanner` in `pages/Bots/ConfigureTab.tsx`, first and full width on the detail panel.

🔴 **The version row on `DeployCard` read `v0`, and it always would have** —
`strategy_version` defaulted to 0 in `algos/live/live_config.py` and nothing wrote it. (Fixed at
the source 2026-08-14: `promote.py` stamps a real count, and the field is `number | null` here
with `null` meaning a deployment made before the stamp. **The banner still renders `compare`**,
which can answer for such a deployment and is the only side that knows what the BACKTESTER is on.) So the one
question the Configure tab exists to answer had no answer on it. Aaron said so directly: *"If you
make me look at commit IDs or parameters from code from a configuration, like exec_time_stop_mode,
I don't know what any of that means. I just wanna know what is the version that I have compiled in
my backtester versus the version that is deployed... and if I'm behind, there should be a big nice
button."*

The banner reads `compare` off the version endpoint (derivation and why not the lab's own registry:
`../backend/CLAUDE.md` → *A bot's VERSION*). Live it renders **"MPC SOS Fade is 21 versions behind
· Deployed v100 · 2026-08-05 · Backtester v121"** over the settings that would move, with
`Deploy v100 → v121`.

⚠ **It is the ONLY promote entry point on the page.** `DeployCard` carried its own until this
landed, and two controls firing one destructive action is two places for the confirmation copy, the
disabled state and the preview gate to drift apart — on the single control that changes what a live
account trades. `DeployCard` is now purely the detail (hash, commit, files) and says where the
button went.

⚠ **`comparable` false renders the `reason` and NO BUTTON.** Never promoted, commit not fetched, no
git — each is an ordinary state with its own fix and none of them is "press deploy". Rendering `0`
there would say *up to date*, which is the most reassuring answer available and the one most likely
to be wrong. Same rule as `mt5_link` and `DrawdownMeter`'s unmeasured tail.

⚠ **A PINNED setting is listed separately, not filtered out.** *This changed in the repo and your
bot is holding it still* is the reassuring half of the same question, and dropping it leaves the
reader unable to tell "not affected" from "not checked". It is also the one the promote preview
does not report.

⚠ **A new setting reads `not in v100`, never `Off → On`.** The deployed version had no such lever
at all, and "Off" is the lie in the safe-looking direction. `is_new` carries it; the backend sends
`was: ""` rather than wording it.

⚠ **The wording of every setting row is the STRATEGY's own**, from its meta file, with the full
`desc` on the row's `title`. A name→sentence map written here would be a second claim about what a
setting does.

⚠ **Uncommitted edits in the bot's trees are called out**, because the backtester runs the WORKING
TREE while a version describes a commit — and `promote.py` refuses a dirty tree, so this is also
the explanation for that refusal before you hit it. It caught a real one on the first render.

⚠ **The 21 code changes are behind a disclosure, and the settings are not.** The settings are what
CHANGES ON THIS BOT; the commit list is context. Putting them at the same level is what made the
old card read like a git log.

🔴 **A FINISHED DEPLOY RENDERED AS A PENDING ONE, and Aaron hit it the first time he used this.**
The output panel held a bare `output: string`, so a completed promote printed under the PREVIEW's
own caption — *"Checked the code on the VPS — nothing deployed yet"* — with **Deploy & restart**
still sitting beneath it. He pressed it, it worked, and the page gave him no way to tell:
*"confused what to do I click deploy and restart."* ✅ The deploy really had landed — the ledger
shows `shutdown exit_code 0 · reason "stop requested"` at 18:36:12 and `startup hash 556bf70c18b7 ·
previous_run_clean: true` eleven seconds later.

**`result` now carries `kind: 'preview' | 'deploy'` plus `ok` and `restarted`**, and the panel
branches on it: a deploy gets a green *"Deployed — MPC SOS Fade restarted and is running v121"*,
the button is **withdrawn**, and Cancel becomes Close. ⚠ **The text alone cannot carry this** —
`promote.py`'s own output reads much the same either way, and the one line that distinguishes them
(`dry run — nothing was deployed`) is at the bottom of a scrolling `<pre>`. **A panel that shows a
result has to say which ACTION produced it.**

⚠ **`restarted` is rendered, not assumed.** `ok && !restarted` means the snapshot is on disk and
the OLD code is still trading — the most misleading state this page can be in — so it says *restart
it to pick this up* rather than claiming the new version is live. And a FAILED deploy says the bot
is **untouched and still on v100**, because a promote that fails leaves the running bot exactly as
it was; claiming otherwise sends somebody to debug a bot that is fine.

### The accordion that would not close, and the deploy that landed short (2026-08-14)

🔴 **A SUCCESSFUL deploy left the panel in its PRE-DEPLOY shape under a green success line** — the
promote's `<pre>` held the block open at full height and the "N settings would change" section still
described the state before the deploy. A success now collapses to the green line with the output
behind a **Show output** toggle; a **preview** and a **FAILED** deploy keep theirs open unasked,
because that text is what you read before deciding and the only place a failure's reason lives.

🔴 **And the Deploy button stayed live across the refetch.** `usePromoteBot` invalidates the version
on success, so for the length of that request every number on the banner — including the button's own
`v163 → v165` label — still describes the state before the deploy. It reads `isFetching` now
(`checking…`, disabled) and the changes block is withheld over that window. ⚠ **That last guard has
NO browser check and its mutation was RUN and stayed green**: it governs only a transient, and a
Playwright assertion retries until the state settles. Named rather than glossed.

🔴 **THE SAME BUTTON WAS ALSO LIVE OVER ITS OWN PREVIEW, and that half was reported separately the
same day:** *"I click deploy and then it expanded to show me all the things that it will commit. But
the deploy button is still there. I click it. It just keeps repeating the process over and over."*
Pressing it re-ran the dry run and re-rendered an identical panel, which is **pixel-identical to a
dead button** — so the reader's reasonable next move is to press it again. It is disabled while a
preview is on screen (`awaitingConfirm`), leaving **exactly one live control**: `Deploy & restart`
below. ⚠ **Disabling was not enough on its own** — a greyed button still labelled `Deploy v164 →
v167` reads as BROKEN rather than as done-its-part, so the label becomes `checked — confirm below`
and names where the action went. ⚠ **`Cancel` hands it back** rather than the gate being one-shot:
the repo can move while you are reading the preview. ⚠ **It is a separate flag from `busy`, not an
addition to it** — `busy` also disables the confirm button, so folding it in would disable BOTH and
leave no way to deploy at all.

🔴 **The success line named `local_version` — what the reader ASKED for, not what landed.** MEASURED:
it read *"running v165"* over a bot running **v164**. It is `deployed_version` now, and is withheld
until the refetch answers — **a version quoted from the pre-deploy payload is a claim about the thing
that just changed.**

🔴 **`unpushed_commits` is why that deploy landed short, and the page could not say it. A promote
PULLS on the VPS, so the ceiling is the REMOTE, never this laptop's HEAD** — an unpushed commit is
unreachable however many times Deploy is pressed, and every number on the banner stays correct while
the button looks broken. It names the count and the version a promote can actually reach, beside the
uncommitted-files line it is the outward twin of. ⚠ **`null` = no upstream to ask, `[]` = measured
and all pushed** — both silent here, and collapsing them upstream is what makes the answer wrong.

⚠ **The `/version` mock must ANSWER DIFFERENTLY AFTER A PROMOTE or three checks are vacuous** — a
route frozen at `deployed_version: 100` leaves the page reading "21 versions behind" after a deploy,
indistinguishable from the defect. `landsAt` is what pins a deploy that deliberately falls short.

🔴 **And the mutation harness silently no-opped TWICE: restoring the file and applying the next
mutation IN THE SAME SHELL CALL left Vite serving the previous module**, so two mutations read as
*did not bite* against plainly mutated source. **The `__pycache__` trap from `backend/CLAUDE.md`,
arriving in the dev server.** Every step asserts the replacement APPLIED and runs in its own call —
**a mutation that silently no-ops looks exactly like a test doing its job.**

✅ **`tests/bots-version.spec.ts` — 17 checks, and they need NO BACKEND and no VPS** (the real
`/version` route SSHes to the live trading box and `/promote` deploys onto it, so both are
intercepted whole — the `calendar.spec.ts` shape, and it matters more here than anywhere).
⚠ **A fail-watch against HEAD is VACUOUS** — the banner did not exist, so every check would go red
because the element is absent, proving the locator and nothing else. **Non-vacuity is by MUTATION,
named in a comment on each check**; collapsing `result.kind` back to a string turns the three
deploy-state checks red together.

🔴 **Two of the ten were VACUOUS on the first run and this file's own trap caught them: the
Risk-per-trade card carries its OWN `Deploy` button**, so a page-wide *"no deploy button"*
assertion passes against a broken banner. That is the third instance recorded here
(`svg.first()` was the sidebar logo; a page-wide Retry matched the page header's own).
`data-testid="version-banner"` is a declared test seam and **every assertion is scoped to it**.

#### The confirmation says one thing, and the dirty-file line said a FALSE one (2026-08-14)

Aaron, on the v168 promote: *"this confirmation looks complicated."* Two separate faults stacked
under one green tick.

🔴 **The dirty-file warning claimed a refusal that cannot happen, and a promote had just
disproved it six inches above.** It read *"a promote refuses a dirty tree — commit or revert
first"* over a deploy of v168 that succeeded with **54 files edited here**. The two dirty checks
run on DIFFERENT MACHINES: `promote.py::dirty_paths` runs on the VPS and measures the VPS's own
checkout, while `compare().uncommitted_files` measures THIS laptop. A local edit cannot block a
promote and never could. It now says what is true — those files are not in v168, so a lab run
here is not testing what the bot has, and committing and pushing is how they reach it.
⚠ **This is `unpushed_commits` from the other end**: there the page understated what a promote
could reach, here it invented a reason one would be refused. **Both come from reading a fact
measured on one machine as though it described the other.** ⚠ **The VPS-side dirty state — the
one that really does refuse — is still not measured anywhere on this page.**

🔴 **And the success line restated the header.** *"Deployed — MPC SOS Fade restarted and is
running v168"* sat directly under *"MPC SOS Fade is up to date · Deployed v168 · Backtester
v168"*, with the bot's name in the page title above both: the version three times, the name
three times, under two green ticks. It is **`Deployed and restarted`** now. ⚠ **A FAILURE stays
explicit** (`Deploy failed — <bot> is untouched and still on v164`) and the asymmetry is the
point: after a success the header has re-read the version and agrees, while after a failure the
banner still describes the state BEFORE the attempt, so the line must carry the version itself.
⚠ **The *restart it to pick it up* branch also stays explicit** — nothing in the header says the
running process is older than the snapshot on disk.

⚠ **`the success line names the version that LANDED` MOVED rather than went.** Its subject was a
string that no longer exists, and the rule it guards is live — a deploy that could not reach HEAD
must never be described as having landed there — so it asserts the HEADER now, where that fact
went. **Re-mutated to confirm it still bites**: rendering `local_version` as the deployed version
turns it red.

## The Accounts tab is a RAIL + DETAIL, not a stack of cards (2026-08-12)

`AccountsTab` was a card per account, stacked down the page. Aaron's report is the spec for what
replaced it: *"the more accounts I add, it's just gonna keep scrolling up and down… the first thing
that I'm looking at is what is the broker? Then what's the account number? And then the account
type? Those things don't stand out to me at all… I can't tell easily what bot is trading on what
account… I don't see an easy way to add bots or remove bots from accounts."*

Three separate faults, and only the first is about layout:

- **It grew downward for ever.** With five accounts the page was a scroll and a memory test, and
  the answer to *what is trading where* was never on one screen.
- **Identity did not stand out from description.** Broker, number and tier were three
  interchangeable pieces of grey `text-micro`, sitting beside the server, the suffix and the cap in
  the same treatment — so nothing on a card told you WHICH account you were looking at faster than
  anything else did.
- **Moving a bot was drag-only**, which nothing on screen advertised.

⚠ **The rail is the selector and the ONLY thing that grows; the detail pane is fixed.** Same shape
as `ConfigureTab`, deliberately — two tabs that both pick one thing out of a list and configure it
should not be two different interactions, and that tab's own note already argues the case (only the
selected subject's controls exist in the DOM, so a control for something you did not pick is not
there to be hit).

⚠ **Selection lives in `?account=` and MERGES the existing params.** `setSearchParams({account})`
would drop `?tab=accounts` and throw the reader back to Monitor. It is also why a reload keeps the
account you were reading — a selection that dies on refresh is one you re-make every visit.

⚠ **The default lands on an account that is TRADING.** The registry is ordered by account number,
so the first row is whichever login is numerically lowest — on this box a retired Standard demo —
and opening on it made the page's first answer to *what is running* an account with nothing on it.

⚠ **`data-kind` is on BOTH the rail row and the detail pane**, so a bare `[data-kind="bench"]`
matches two elements; every check scopes to `account-rail-item` or `account-card` first. The
strict-mode violation that follows reads as a MISSING card rather than a duplicated one, which is
the wrong direction to be sent in.

### Both panes are the height of the PAGE, and the height is measured

⚠ **`usePaneHeight` measures, and a `calc()` here is the trap.** `100vh - 148px` is right for the
top bar, the page padding and the tab row — and wrong the moment anything else is above the pane,
which really happens: the VPS-failure banner appears on a poll and a hardcoded height then runs the
pane's bottom edge off the screen. One `getBoundingClientRect` per render, guarded so it converges
in a pass, cannot be wrong about what is actually above it.

⚠ **The effect has NO dependency array on purpose.** A banner appearing above this pane moves its
top without any state in here changing, so the measurement has to run on every render.

⚠ **The detail pane is header / scrolling body / pinned footer**, and each part is where it is for a
reason: the identity stays put while the bot list scrolls (you are never reading a table whose
subject has scrolled away), and the risk cap is a footer rather than something you scroll to find.
`AccountForm` takes the same shape, so switching between reading an account and editing one does
not resize the page under the reader — and its Save is pinned for the same reason Add account is.

🔴 **The Monitor tab's loading skeleton rendered over every tab** until 2026-08-12, so opening
Accounts drew ~400px of fake Monitor cards above it for the four seconds the VPS snapshot takes and
then snapped away. **Neither Accounts nor Users reads that snapshot to render** — Accounts joins it
only for the State column, which honestly says `—` — so both were blocked by a fetch neither needs.
⚠ **The error banner is deliberately still ungated**: a dead VPS is why the State column cannot
answer, and that is worth saying on this tab. The measured height is what absorbs it.

### Whether anything is TRADING an account — three states, one definition

**Added 2026-08-12.** Aaron: *"make more obvious that the account has a bot running against it or
not."*

🔴 **The rail's last line read `2 bots`, which is a fact about the CONFIG and reads as a fact about
the account being live.** Two bots assigned and stopped rendered identically to two bots trading,
so the rail — the one place every account is on screen together — could not answer *which of these
is running right now*, and getting the answer meant selecting each account in turn and reading the
State column. The rail row now carries a green dot + `1 of 2 trading`, and the detail pane a
`running-chip` reading `Trading · 1 of 2`.

⚠ **`liveOf` is ONE derivation, read by the rail row and by the chip.** Two hand-written readings
is how a green dot in the list ends up beside *nothing running* on the pane it opens — the same
argument that made `useAccountCount` exported and `BotStatusPill` a shared file.

⚠ **THREE answers, and the third is the whole reason it is a function.** `known` counts the bots
the VPS snapshot actually came back for, so `running: 0` with `known: 0` means **nobody asked**,
not *nothing is trading*. `/bots/accounts` deliberately never touches the VPS, so this tab renders
in full while the box is unreachable — and reading that silence as `idle` would report the fleet as
stopped at exactly the moment nothing can be checked. It says `Running state unknown` / `unknown`
instead. Same rule as `has_password`'s `null`, and as `mt5_link` before it.

⚠ **`running > 0` wins even when some bots are unanswered.** A bot SEEN running is a measurement;
the unknowns can only add to it.

⚠ **An idle account says `Nothing running` rather than drawing no marker.** An absent green dot is
indistinguishable from an account nobody could ask about — which is the same collapse the plain
count was guilty of.

⚠ **The dot is STEADY, never `animate-pulse`.** A bot runs for weeks, and permanent motion in a
list is read as an alert on day one and as background by day two; the row already has a warning
triangle that genuinely wants the eye.

⚠ **The chip is FIRST in the readiness row.** Everything else there — password, terminal, cap — is
about whether the account COULD trade. This one says whether anything IS, which is the question the
page is opened with.

⚠ **The default SELECTION was deliberately not changed to prefer a trading account.** It is
`busiest` by bot count, which is answerable from the accounts payload alone; keying it on the
snapshot would move the reader's selection ~4s after load, when the VPS answers.

3 new browser checks (41 in the file), **each proven by MUTATION** — the rail falling back to the
plain count, the chip rendering only when something runs, and `state` collapsed to `running > 0`
each turn their own named check red and leave the others green.

### The counts are on the TAB CHIPS, from one definition each

Aaron: *"accounts on the left navigation as account four — just put that count inside the accounts
tab where I could see it. Users should have a count for how many users we have."*

⚠ **A count on the chip is readable from a tab you have not opened**, which is the whole point; the
same number inside the panel only answers the question once you are already there. So the rail's
own header carries no number — two places is two claims about one set.

⚠ **`useAccountCount` is exported and is the ONE definition**, and it counts registered accounts
plus any account a bot names that nobody registered — exactly the set the rail draws as accounts.
The bench and the unreadable-configs rows are states, not accounts.

⚠ **An unanswered query renders NO chip, never `0`.** *No accounts registered* is a claim, and it is
never the true one here. ⚠ **Monitor and Configure carry no count on purpose** — the fleet size is a
stat card on Monitor, and Configure lists the same bots.

### Accounts vs Configure — and the row that says so

The question came up as a question (*"what's the difference between accounts and configure?"*),
which is the tell that nothing on the page answered it. **This tab decides WHICH account a bot
trades; Configure decides HOW it trades there.** They are two different writes — one rewrites the
login, server, terminal, symbol and cap together, the other edits a runtime parameter — so they stay
two tabs, and every bot row now carries a **Configure** link that jumps straight to that bot on the
other tab. ⚠ It MERGES the query string (`tab` + `bot`), like every other navigation on this page.

### Two defects that only a real render could show

Both were invisible in the diff, and this folder has recorded that lesson twice before (the 22px
sticky trap; the 6px grid bleed).

🔴 **Add account sat below the fold.** It was under the list, which put it 10px off the bottom of a
940px viewport with five accounts registered — so the one control that makes this tab work would
have been the first thing to disappear as the fleet grew, which is precisely the failure the
rebuild was for. It is above the list now, and the LIST scrolls (`max-h-[calc(100vh-150px)]` with
its own `overflow-y-auto`) rather than the page.

🔴 **The Move `<select>` rendered ~320px wide.** A native select sizes itself to its WIDEST OPTION,
and an option here is a whole account identity (`PU Prime #700152905 · ECN · demo`) — a string only
ever shown in the open popup. It takes an explicit `w-[104px]`.

### The Move menu — drag is the fast path, not the only one

⚠ **It fires the SAME mutation the drop and the Add bot list fire.** Three gestures, one write; a
private write on any of them would be a second place for the six-field move to drift out of step
with `assign_plan`.

⚠ **An unassignable account is LISTED and DISABLED with the reason in the option itself.** Hiding it
makes an account that exists look like one that does not — the same rule the Add bot list follows
for a running bot, and the same rule the `no-terminal` chip states one panel up.

⚠ **A RUNNING bot is refused on all three controls in the same words.** It read its config at
startup, so a write cannot reach the live process and the page would show it under one account
while it traded another. A second control that is not guarded is a way round the guard rather than
a convenience — which is also the answer to *"do I have to stop it first? I don't know"*: the reason
is on the disabled control's own title, not somewhere else on the page.

## Adding a broker account — the control that did not exist (2026-08-12)

`AccountsTab` renders a card per REGISTERED account now, whether or not a bot is on it yet, plus an
**Add account** form. Backend and the reasoning: `../backend/CLAUDE.md` → *The account REGISTRY*.

🔴 **The tab could only ever show accounts a bot was ALREADY on**, because the grouping is derived
from the instance configs — which is right, and which meant the first bot onto a new account had
nothing on this page to be moved to. That is why the live bot's move to the PU Prime ECN demo was a
hand-edited config on the VPS.

- **`emptyGroup(reg)` synthesizes the card for an account with no bots.** ⚠ It sets
  `cap_agrees: true` with `risk_cap_pct: null` — the honest reading of an empty account, since no
  bot states a cap so there is nothing to disagree about. `cap_agrees: false` would draw the
  disagreement banner over an account nobody is trading.
- **An account a bot names but nobody registered still renders**, with a `Not registered` chip
  saying what this page cannot do with it. Hiding it would be the defect the registry exists to
  end, in reverse.
- **`targets` excludes an unassignable account**, so the Add-bot list on every card can only offer
  a move the backend will accept.

### Three chips, and the middle one is the three-state rule again

- **`password-chip`** — `Password set` / `No password` / **`Password unknown`**. ⚠ `has_password`
  is `boolean | null` and `null` means the VPS could not be asked. Rendering it as *No password*
  sends the reader to re-enter a credential that is already there and refuses a move that would
  have worked. Same rule as `mt5_link` and `mt5_connected`.
- **`no-terminal`** — the account has no terminal on the box, so **Add bot is DISABLED with the
  reason on its title.** The refusal exists server-side; this is it stated before the click rather
  than as a 409 after the reader has committed to the move.
- **`live-chip`** — a live account is tinted, the same treatment the Configure tab gives one.

### The form, and the field it puts front and centre

⚠ **The symbol suffix has its own block, its own sentence and a live example** (`XAUUSD.s` becomes
`XAUUSD.p`), rather than sitting in the grid with the display fields. It is the field the 2026-08-12
move forgot, and forgetting it produces a bot that connects, warms up and receives no bars — which
looks exactly like a quiet market rather than like a misconfiguration.

⚠ **It is a CHECKBOX plus a text field, because `null` is a real value.** Unticked sends `null`
("nobody recorded it" — the move leaves the symbol alone and says so); ticked-and-empty sends `""`
("this broker quotes bare symbols" — the move really does strip the suffix). A single text input
would collapse them, and the empty string is the one that silently rewrites a live instrument.

⚠ **There is NO risk cap field on this form and there must not be one.** The cap is set on the card
above — one write, N instance configs — and reported from what the bots actually state.

⚠ **The password field is WRITE-ONLY and blank on an edit.** Nothing returns it, so the form shows
whether one is stored and never what it is; leaving it blank changes nothing. It is sent on the
same request as the registry row, so the credential lands BEFORE the row is committed and pushed —
a registered account with no password is a visible, fixable state the list reports, while a pushed
row whose password write failed afterwards reads as complete.

### The move's `notes` are raised as WARNINGS, not folded into the success line

`useAssignBotAccount` toasts each entry of `BotAccountAssignResult.notes` separately.
**They describe a failure that is silent on the box** — an unregistered account whose symbol and
cost profile could not be carried, or one with no recorded suffix — so burying them in the success
sentence would put the one thing worth acting on inside the message that says it worked.

**`tests/bots-accounts.spec.ts` — 8 new checks (27 in the file).** ⚠ **`mock()` now routes
`/api/bots/accounts/registry` and it MUST**: that endpoint asks the VPS whether a password is
stored, so an unmocked one reaches the live box from a unit check. It defaults to an EMPTY
registry, which is what leaves every pre-registry check unchanged. Non-vacuity is by MUTATION —
five run here, each turning its named check red (registry cards dropped, `assignable` ignored, the
suffix dropped from the submit body, the suffix sent unconditionally instead of `null`, and the
in-use guard dropped from Remove).

## Dragging a bot onto an account in the RAIL — a second GESTURE, never a second path (2026-08-12)

A bot's row in the detail pane is draggable and every row in the ACCOUNT RAIL is a drop target.
Aaron's words: *"if I wanna switch a bot between accounts, I could, like, drag and drop bot from one
account to the next and hit, like, a deploy button."*

⚠ **The rail is the target since the tab became master–detail, and it had to be** — only one
account's card is on screen at a time, so a card-to-card drag can no longer reach a destination.
The rail is the one surface that always shows every account.

🔴 **A drop fires the SAME `useAssignBotAccount` mutation the Add bot list fires.** The move writes
four config fields plus two inside `strategy_params`, and a private write here would be a second
place for that to drift out of step with `assign_plan`. What is new is the gesture; nothing about
what a move DOES is duplicated.

⚠ **THERE IS NO STAGED "pending moves, then hit Deploy" STEP, and adding one would be the defect.**
It would be a stored intention able to disagree with what the bots are actually configured to do —
the exact shape this tab exists to avoid, and the reason the grouping is DERIVED rather than
stored. A drop writes, commits, pushes and pulls in one action, which is already *click, click,
done*; the toast still says a restart is needed, because neither `account` nor the cap is
runtime-reloadable.

⚠ **The GRIP is the only thing on screen that says a row can be dragged.** A `draggable`
attribute is invisible, and the gesture shipped with nothing advertising it but a sentence under the
rail — which reads as an instruction for a feature nobody can find, and was reported in exactly
those words (*"that drag feature doesn't even work. I don't even know what that does"*). Every
movable row carries one, with the destination in its hover text; the sentence is gone. ⚠ **It is a
MARKER, not a handle** — the whole row is still the drag source, so grabbing anywhere works, and a
grip that only worked when grabbed by its 13 pixels would be worse than none.

⚠ **Refusing a drop is `preventDefault` NOT being called on `dragover`.** That is what makes an
element a valid drop target, so declining it is how an account with no terminal says no **while the
reader is still holding the row** — a cursor rather than a toast after they have let go. It is also
why the check for it asserts on `data-dropping`: the refusal has no other observable.

⚠ **A RUNNING bot carries `draggable={false}`**, matching the Remove button beside it. It read its
config at startup, so a write cannot reach the live process and the page would show it under one
account while it traded another. The backend refuses it with a 409 regardless; this is the same
fact stated before the gesture rather than after it.

⚠ **`text/bot-key` is a custom MIME type on purpose.** `onDragOver` checks
`dataTransfer.types.includes(...)`, so dragging text, a file or a link over a card does nothing —
a card that highlights for anything is a card that will eventually accept something it should not.

3 browser checks (30 in the file), **each proven by MUTATION**: removing `onDrop`, making
`draggable` unconditional, and dropping the `assignable` early return from `onDragOver` each turn
their own named check red. ⚠ **The drag events are dispatched by hand rather than with
`dragTo`** — Playwright's helper is unreliable across the mouse-move heuristics, and what these
check is the DATA the drop carries, which the manual events model exactly.

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

## The Stress Tests page — audited 2026-08-05

`pages/StressTestDetail.tsx` + `StressTests.tsx` + the four charts. **The frame is one query: the
`stress_tests` table held ONE row, written 2026-07-27 — three days BEFORE the accuracy pass that
rewrote this engine.** So the page had been driven end to end exactly once, against code that no
longer existed, and nothing had re-scored the stored row since. Every defect below is what that
looks like from the browser.

**And the shape they share is the Overview's: not one of them rendered an error.** A magnitude drawn
as a loss, a null drawn as 0%, a dollar figure drawn under a grade decided in percent — each renders
a confident number.

### The drawdown was shown in a unit the grade did not read

🔴 **The engine picks its basis per run** — `dd_basis` is `percent` on a compounding run (the
2026-07-30 fix: shuffling dollar P&L on a run whose trade size drifts 17.7x simulates a strategy
that never existed) and `dollars` otherwise. The page read **neither `dd_basis` nor the percent
columns**. It printed dollars against a dollar limit and coloured them over/under, while the letter
beside them had been decided on percentages — **so a red "over limit" could sit next to an A**.

`dd(dollars, pct)` is the one derivation: on the percent basis it renders the percent and compares
it to `ddLimitPct`, on the dollar basis it renders dollars against `ddLimit`. ⚠ **It shows ONE of
them, never both** — showing a percent drawdown beside a dollar limit is what invited the
comparison in the first place — and a `basisNote` says which unit is in force and why.

⚠ **A prop ruleset's percent limit is DERIVED** (`ddLimit / account_size`), a personal one's is
stated (`max_drawdown_from_peak_pct`). Do not swap them: a trailing dollar floor and a
peak-relative percentage are different rules, and this is the same distinction `DrawdownMeter`
already refuses to blur.

### Null was rendered as zero, in two places, both reassuring

🔴 **`st.prob_pass_eval ?? 0` printed "0%"** — *this strategy never passes the eval* — for a
measurement that was never taken. The backend made both probability fields `Optional[float]`
specifically so a ruleset with no limit could say **nothing to breach**; the page collapsed that
third answer into the worst of the two real ones. It says `no limit to breach` now and renders no
probability card at all.

🔴 **A sensitivity shift whose backtest FAILED was drawn as a flat zero bar** — "tested, no effect",
the most reassuring answer available. Rows with no measurement are DROPPED from the radar
(`if (magnitude == null) continue`), and the coverage line says how many.

🔴 **A completed test with no letter rendered a card with no letter and no explanation**, which
reads as a broken page. `grade_reasons` had been computed and stored since the accuracy pass and
**nothing displayed it** — the one thing that says *why* there is no grade. It renders now, beside
`phase_failures` and `results_error`.

### A magnitude drawn as a direction

🔴 **`degradation` is `|Δ| / baseline` — a MAGNITUDE — and the page drew `-degradation * 100`**, so
every shift rendered as a loss and "Median Change" was negative by construction. **A parameter shift
that IMPROVED the result was drawn as a long red bar.** The engine now records `pf_delta_pct`
(signed) alongside it; the radar reads `pf_delta_pct ?? pnl_delta_pct ?? null`, ranks on
`magnitude`, and paints neutral when the direction is genuinely unknown rather than inventing one.

⚠ **Ranked by magnitude, capped at `TOP_N = 24` with a show-all toggle.** A 60-shift run rendered 60
rows at 11px; the worst shifts are the point and the tail is scroll.

### Walk-forward: the numbers the verdict turns on were dropped by the model

🔴 **`is_trades` / `oos_trades` were written by the engine and undeclared on `WalkForwardWindow`**,
so Pydantic stripped them and the page could never show that **every window on the stored test
closed 6 out-of-sample trades** — under the engine's own 20-trade floor, i.e. a degradation figure
with nothing behind it. **This is the `entry_ms` / `exit_ms` / `favorable` trap for the fourth
time**; the rule in `backend/CLAUDE.md` is not an anecdote. Thin windows now fade to 0.22 opacity
and a caption reads `5 of 5 windows too thin`.

🔴 **The native path writes `is_sharpe: null` deliberately** (it has no trade-level data and degrades
on profit factor), and the chart did `is_sharpe ?? 0` — **five pairs of zero bars asserting "Sharpe
0.00 in and out"**. It detects the PF shape and reports profit factor, with `not measured` in the
tooltip for a genuine null.

### The fan drew a reference it cannot support

🔴 **`MonteCarloFan` drew a `ReferenceLine` at `y = -max_loss_eod` on a CUMULATIVE-P&L axis.** A
drawdown is peak-to-trough, so a path can breach many times over without ever crossing a line below
zero — **a fan sitting entirely above it read "no simulation breaches" while Prob. Breach said
otherwise.** Removed. The histogram, which actually measures drawdown, keeps its limit line and
takes a `unit` prop so it is labelled in the basis it was measured on.

### The rest

`WF_MIN_TRADES_PER_WINDOW = 20` mirrors the backend and drives a **live feasibility warning in the
Run modal** — the windows slider says `~10 OOS trades per window` before you spend an hour finding
out. A **Stop** button (`useCancelStressTest`, distinguishing `job_stopped` the way the optimizer's
cancel does). `phases_requested` drives the pipeline stepper, so a walk-forward-only test no longer
draws a Sensitivity step that can never complete. The list page gained a basis-correct **Worst 1%
DD** column, `n/a` instead of blank for null probabilities, and a `not graded` chip. And a
`Fragment key={step.key}` — the stepper was building a keyless array.

### `tests/stress.spec.ts` — 11 checks, all 11 watched to fail

Every one is red against the page at `HEAD` and green against the fix. Same mock discipline as the
Overview's and the Tuning workbench's: the states cannot be produced on demand — a compounding run
graded on percent, a crashed walk-forward, a native path with no Sharpes, a shift whose child failed
— so they are built by **MUTATING the real detail response**, never hand-written.

⚠ **Two locator traps this suite had to learn, and both produce a VACUOUS PASS rather than a
failure.** `page.locator('svg').first()` is the **sidebar logo** — a page-wide search for an absent
element passes on any page, including the broken one, so the fan's no-limit-line check proved
nothing until it was scoped to the fan's own container. And a chart label appears three times (the
KPI card, the chart `<tspan>`, and Recharts' hidden `#recharts_measurement_span`), so a bare
`getByText` is a strict-mode violation rather than a miss — scope to `locator('tspan', {hasText})`.

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

The "Deployed" sub-tab (`FilesTab`) has a drag/drop zone (`.cs`/`.mq5`), a file list sorted by platform then filename, trash-can delete, and overwrite/delete confirm modals. "Compile NT8" (`useTriggerCompile`) and "Compile MT5" (purple, only when MT5 files present; `useTriggerCompileMt5`) both open the generic `CompileModal` (props: `title` + `usePollHook`). The modal has a status-icon header (`StatusIcon`: spinner / green check / red X) + one-line summary, a body capped at `max-h-[85vh]` that scrolls, and a pinned footer. While running it shows staggered pulse **skeleton rows** (no second spinner) shaped like the result rows that replace them. On completion it renders the real `job.errors` / `job.warnings` **text** — not just counts — via `CompileSection` (color-coded, numbered, monospace lines: red `neg` for errors, amber `warn` for warnings); warnings show even on a successful compile. The elapsed counter ticks every second from a **local `setInterval`** (anchored to `started_at`, freezing at `completed_at` when done) — without it the count only advanced on each poll and visibly jumped. Strategy-file hooks live in `useLab.ts`: `useStrategyFiles`, `useStrategyFileSyncStatus`, `useUploadStrategyFile` (native `fetch()` + `FormData`, not `api.post`), `useDeleteStrategyFile`, `useTriggerCompile`, `useCompileStatus`, `useTriggerCompileMt5`, `useCompileStatusMt5`, `useDeployStrategy`. `useParamTypes(strategyId)` calls `GET /strategies/{id}/param-types` → `Record<string, 'int' | 'double'>` with `staleTime: Infinity`; used by `OptimizerModal` to validate int-param ranges; disabled when `strategyId` is null. Types: `StrategyFile` (+ `platform`), `StrategyFileSyncStatus`, `CompileJobStatus`, `DeployJobStatus`; `ScanResult` carries `orphans: string[]` (DB strategies whose source file is gone) + `warnings: string[]`; `ReconcileResult` carries `removed: string[]` + `warnings: string[]`. **Since 2026-08-06 both file endpoints return an ENVELOPE, not a bare list** — `StrategyFilesResponse { files, nt8_error, mt5_error }` and `StrategyFileSyncResponse { statuses, nt8_error, mt5_error }` — so one unreachable agent degrades the other platform's rows instead of 502-ing the whole call, and the page can say WHICH agent is down. The modal now has a header X and an Escape handler (the footer Close renders only on completion, so a hung poll had no way out) and reads `isError`, so a failed status poll ends the spinner.

**Scan vs Reconcile (bidirectional delete).** Scan is read-only: `useScanStrategies` (`POST /strategies/scan`) adds/updates and its success toast flags the orphan count (`N orphaned (source deleted — use Reconcile)`). Deleting a source file from the repo propagates to the DB row + the deployed VPS file ONLY through an explicit action: `useReconcileStrategies` (`POST /strategies/reconcile`). On the `Strategies.tsx` header, a red **Reconcile (N)** button appears next to Scan whenever any strategy row carries **`is_orphan`** — ⚠ **not `scan.data?.orphans`, which is MUTATION state**: gated on that, an orphan was invisible on a fresh page load and stayed invisible until somebody happened to press Scan (fixed 2026-08-06). It is fronted by the shared `ConfirmDeleteModal` (imported from `pages/Backtests`) listing exactly which strategies will be removed. On success it invalidates `['lab','strategies']` + the strategy-files / sync-status keys, and surfaces any per-strategy VPS-delete warnings as error toasts. The per-strategy Delete button uses the same backend `remove_strategy` path. See backend CLAUDE.md "Bidirectional delete (reconcile)".

Each row in `StrategiesTab` has a Deploy/Compile/Run action driven by the **content-aware** `StrategyFileSyncStatus` (`needs_deploy` / `needs_compile`, not the old presence-only `in_sync`). `StrategyRow` takes the full `sync` object (via `syncByStrategy[s.id]`), and the Status cell shows a version chip `v{current_version}` next to the state pill. **The pill is ONE ordered-exclusive chain and must stay one** (2026-08-06): amber **Needs deploy** → red **Missing on VPS** (`file_exists_on_vps === false`, previously returned by the backend and rendered by nothing, so a file deleted off the box read green) → amber **Needs compile** → grey **VPS unknown** (`file_exists_on_vps == null`, i.e. the agent could not be asked) → green **In sync**. ⚠ **The first attempt at this added *Missing on VPS* as a chip BESIDE the hash-derived pill, so a row rendered green *In sync* next to red *Missing on VPS*** — the exact contradiction the fix existed to remove, one line lower, caught by a browser check and not by reading the diff. The action mirrors the pill (`Deploy` / `Redeploy` / `Compile` / `Run`), and **the whole action cell is gated on `isPython || sync !== undefined`** — with sync-status down every row lost its `sync` object and fell through to Run, so a strategy that needed deploying offered to run. ⚠ **`liveVer` is `sync.compiled_version`, full stop** — it used to fall back to `deployed_version` when `needs_compile`, which named the deployed source as what was running while NT8 and MT5 both execute the COMPILED artefact. `handleDeploy` tracks `deployingId` and on success invalidates `sync-status`. **First-run:** every strategy shows Needs deploy until deployed once through the tracked path (no deploy-hash recorded yet — see backend CLAUDE.md). `StrategyVersion` type + `GET /strategies/{id}/versions` expose the full version history if a per-strategy view wants it.

**"Needs scan" pill (2026-07-23).** Separate from the deploy/compile sync above — it reads `Strategy.needs_scan` (on the strategy row itself, not `StrategyFileSyncStatus`), which the backend computes live (source hash / meta mtime vs last scan). When true, `StrategyRow`'s Status cell shows a clickable amber **● Needs scan** pill (calls `onScan` → `useScanStrategies().mutate()`, spins while pending) ABOVE the deploy/compile pills. It renders for ALL runners, and for a Python strategy — which has no deploy/compile step, so its Status cell was otherwise empty — it's the only status pill. `RunBacktestModal` shows a matching amber banner when `strategy.needs_scan` ("Parameters may be out of date … click Scan Strategies, then reopen"): the panel form is built from the last-scanned schema, so editing a Python `config.py`/meta without re-scanning silently runs on the OLD params (the bug that ran mpc_sos_fade on stale divergence-armed defaults). This is the Python analog of the MT5/NT8 deploy/compile badges.

---

## The scheduled-job status gained an ARMED value (2026-08-21)

`JobStatus.status` now carries `ARMED` alongside `RUNNING` / `STOPPED` / `DISABLED` / `UNKNOWN`.
It is what the backend returns for a scheduled task that is enabled and waiting for its next
trigger — the normal state of a once-a-minute watchdog. Full story, and why the payload was wrong
while the page was right, in `command-center/backend/CLAUDE.md`.

⚠ **No component changed, and that is deliberate.** `ARMED` falls through the same else-branch
`STOPPED` did in both `JobDot` (Bots) and `JobPill` (Overview), onto the same gold *"waiting for
next trigger"* dot with the same tooltip — which was already the correct thing to show. `allJobsOk`
still counts only `RUNNING`, so the summary tile is unchanged too. **The type learned a value the
UI already handled correctly**; rendering armed differently from unrecognised is a separate decision
nobody has made.
