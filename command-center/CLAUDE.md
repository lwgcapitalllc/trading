# CLAUDE.md — Command Center

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

```
command-center/
├── backend/          FastAPI + Pydantic v2, Python 3.9
│   ├── main.py
│   ├── config.py     loads config.json → typed constants
│   ├── config.json   absolute paths to smart-money and algos on this machine
│   ├── models.py     all Pydantic models (shared data contracts)
│   └── routers/
│       ├── smart_money.py
│       ├── bots.py
│       ├── backtests.py     stub
│       ├── stress_tests.py  stub
│       └── settings.py
├── frontend/         Vite + React 18 + TypeScript + Tailwind + TanStack Query
│   └── src/
│       ├── api/client.ts       all fetch goes through here (prefix /api → :8000)
│       ├── types/index.ts      mirrors all Pydantic models exactly
│       ├── hooks/              one file per backend module
│       ├── components/         Sidebar, TopBar, StatCard, ScaffoldBanner, EmptyState
│       └── pages/
│           ├── SmartMoney/     PoolOverview, Rankings, CandidateProfile, DisqualifiedLog, Config
│           ├── Bots/           monitoring table, scheduled jobs, log viewer
│           ├── Overview.tsx    scaffold
│           ├── Backtests.tsx   scaffold
│           ├── StressTests.tsx scaffold
│           └── Settings.tsx    scaffold
├── design/
│   ├── prototype.html          interactive visual spec — open in browser, no build step
│   ├── README.md               theme reference (Refined dark, teal accent, gold secondary)
│   └── LWG_Capital_Command_Center_Build_Spec.md   full architectural spec
└── start.sh          starts both processes; ./start.sh from this dir
```

---

## How to run

```bash
cd command-center
./start.sh
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000/docs
```

`start.sh` creates the Python venv and runs `npm install` on first launch.

---

## Key design decisions

**Config translation layer** — the Smart Money pipeline stores fractional values (`win_rate: 0.75`) but the UI shows percentages (`75.0`). `_pipeline_cfg_to_api()` and `_api_cfg_to_pipeline()` in `routers/smart_money.py` handle bidirectional conversion. The API contract (percentages, flat keys) is the stable interface; if the pipeline changes its format, only the translation functions change.

**Batched VPS snapshot** — `GET /bots/snapshot` makes two SSH calls (replicating algo.py's `fetch_vps_snapshot()` exactly) and returns a single `BotSnapshot`. The frontend polls this at 60s. Never SSH per-bot.

**Bot control actions are 501 stubs** — `POST /bots/start|stop|restart|emergency` all return 501 with an explanatory message. This is deliberate: monitoring must be verified against the live VPS before controls are enabled. Do not implement these until `/bots/snapshot` has been validated in production.

**No auto-commit** — `PUT /smart-money/config` writes the file only. `GET /smart-money/config/git-status` shows dirty state. The user decides when to commit.

---

## What is built and live

| Module | Status | Notes |
|---|---|---|
| App shell (sidebar, topbar, routing) | ✅ Live | All 6 routes |
| Overview dashboard | ✅ Live | Stat row + Bots card + Smart Money card; navigates to sub-pages |
| Smart Money — Config | ✅ Live | Reads/writes `smart-money/config/config.json` |
| Smart Money — Pool Overview | ✅ Live (UI) | Needs qualifying candidates to show real data |
| Smart Money — Rankings | ✅ Live (UI) | Needs qualifying candidates |
| Smart Money — Candidate Profile | ✅ Live (UI) | Needs qualifying candidates |
| Smart Money — Disqualified Log | ✅ Live | Category badges, readable reason formatting, filter tabs with counts, wallet hyperlinks |
| Smart Money — Run pipeline button | ✅ Live | `POST /smart-money/run` spawns `run_stage1.py`; 409 if already running; optimistic instant terminal |
| Smart Money — Scanner Terminal | ✅ Live | Matrix-style live address feed; hidden when viewing a historical run |
| Smart Money — Clear Cache button | ✅ Live | Two-step inline confirmation; shows live cached count; `DELETE /smart-money/cache` |
| Bots — monitoring table | ✅ Live | VPS SSH implemented |
| Bots — scheduled jobs | ✅ Live | Gold glow = scheduled/waiting, green = running |
| Bots — log viewer | ✅ Live | SSH log fetch |
| Bots — control actions | ✅ Live | Start/Stop/Restart/Emergency (global + per-bot); all destructive actions require confirm |

---

## Recent session — bug fixes and enhancements (2026-05-26)

### Bugs fixed
- **`500 multiple values for 'run_id'`** — `StageReporter` writes `run_id` into `meta.json`. `get_run()` was then calling `SmartMoneyRun(run_id=run_id, **meta)` which duplicated it. Fix: `meta.pop("run_id", None)` before spreading into the constructor (`routers/smart_money.py`).
- **Error toasts black instead of red** — Sonner requires `richColors` prop on `<Toaster>` for semantic colouring in dark mode. Added to `App.tsx`.
- **Disqualified Log filter tabs "Drawdown" / "Win rate" showing 0** — old `matchesFilter()` looked for literal substrings. Actual reasons use phrasing like "Strike system: 2 yellow, 1 red flag" (win rate) or "Trading span 0 days < 90" (activity). Fixed with a `categorizeReason()` function mapping reason text → category via keyword checks.
- **API error entries styled as red disqualification reasons** — "API error: All 3 attempts failed…" now categorised as `api_error`, styled orange/warn, with its own filter tab.

### Features added
- **Matrix-style Scanner Terminal** (`ScannerTerminal` component in `SmartMoney/index.tsx`) replaces the old progress bar:
  - Wallet addresses stream in one-by-one via a client-side drain queue (90 ms stagger) bridging 1-second polls
  - `PASS ✓` entries glow green (`drop-shadow-glow-pos`), fails are dim
  - Scanline sweep animation, ping-ring running dot, opacity gradient on older entries
  - Stats bar: wallets/sec, scanned count, qualified count
  - Thin 3 px accent progress bar at bottom
  - Phase-sensitive: shows matrix feed during scan phase; status text + cursor blink otherwise
- **Instant terminal on "Run pipeline" click** — `handleRunPipeline` calls `setIsStarting(true)` synchronously before the mutation fires. The component immediately shows `STARTING_PROGRESS` (a constant `status: 'running'` placeholder). Once the backend confirms the run is live (`progress.status === 'running'`), `isStarting` is cleared and the real progress feed takes over. A module-level `_lastTriggerMs` timestamp keeps polling at 1.5 s for 60 s after the trigger (bridges the 10–15 s Python startup window where `progress.json` still shows the old completed state).
- **`recent_addresses` in progress feed** — `RunProgress` model (`models.py` / `types/index.ts`) gained `recent_addresses: list[dict]`; `run_stage1.py` maintains a rolling list of up to 25 entries (short keys `{a, s}`) and passes them on every `progress.update()` call; the scanner callback signature in `hyperliquid.py` was updated to emit `(address, result_type)`
- **Disqualified Log full rewrite** — category badges (Win Rate = red, Activity = teal, Drawdown = red, Concentration = gold, API errors = orange), readable reason formatting (Unix timestamps in window messages → human dates), filter tabs with live counts, wallet address hyperlinks to Hyperliquid explorer
- **Electric Cyan theme** — `tailwind.config.js` updated: `accent #00e5ff`, `pos #00ff7f`, `neg #ff3b5c`, `warn #ffb300`; cooler blue-black surface tones; `dropShadow` glow extensions (`glow-accent`, `glow-pos`, `glow-neg`, `glow-gold`) and `boxShadow` glow variants added globally

---

## Session bugs fixed (2026-05-27)

### Pipeline
- **`KeyError: rate_limit_delay_seconds`** — `run_stage1.py` hardcoded `hl_cfg["rate_limit_delay_seconds"]` but configs were updated to `requests_per_second`. Fixed with `.get()` fallback in `run_stage1.py:119`.

### Smart Money UI — run-in-progress lockdown
- **Stale data while running** — tabs still showed previous run. Fixed: all tabs (`pool overview`, `rankings`, `profile`, `disqualified`, `config`) replaced with `<RunPendingPlaceholder />` when `isLive`.
- **Tab bar clickable during run** — all tabs are now `pointer-events-none` + dimmed text when `isLive`.
- **Header during run** — dropdown, export button, profile toggle, and run date are all hidden. Only `● RUN IN PROGRESS` pill + `Stop pipeline` button show.

### Bots page
- **Bot log 500 error** — two bugs:
  1. `_ssh()` in `routers/bots.py` used `text=True` in `subprocess.run`, which raised `UnicodeDecodeError` on cp1252-encoded Windows log characters (arrow/dash symbols). Fixed: decode as `utf-8, errors="replace"`.
  2. `api.get<string>()` in frontend called `res.json()` on a `text/plain` response. Added `api.getText()` method to `client.ts`; `useBotLog` now uses it.
- **No loading state on Bots page** — replaced bare text with animated skeleton (stat card placeholders + table row stubs + spinner + "Connecting to VPS…" caption).

### Smart Money pipeline — fills cache
- Added `fills_cache` table to SQLite (`database.py`): stores raw fills JSON per wallet with `fetched_at` timestamp.
- `get_cached_fills(address, max_age_seconds)` and `cache_fills(address, fills)` functions added.
- `apply_initial_filters()` in `scanner/hyperliquid.py` now loads cached fills before the thread pool. Wallets with fresh cache skip the API call entirely; newly fetched fills are written to cache after the API call.
- Config: `hyperliquid.fills_cache_hours: 24` in all three configs. Set to 0 to disable.
- Effect: first run unchanged (~13–15 min); any re-run within 24h completes in ~30s.

---

## Session — pipeline data integrity + UI overhaul (2026-05-27)

### Pipeline fixes (`smart-money/`)

**`filters.py` — net-negative wallets bypassing drawdown check**
`check_drawdown` only fires when `peak_cum > 0`, so always-losing wallets pass it silently. Fixed by adding `check_overall_profitability` as the first check in `DisqualificationFilter.apply_all()` — disqualifies any wallet where `sum(pnl) <= 0`. Reason emitted: `"Net unprofitable: total PnL $-X"`.

**`run_stage1.py` — `min_trades` was enforced on raw fills, not matched trades**
Pre-filter counted closing fills before FIFO matching. Old accounts can have 100+ closing fills but collapse to a handful of matched pairs once opens predate the fetch window. Added an explicit check on `len(trades)` (matched count) immediately after `profiler.profile_wallet()`. Reason: `"Matched trades 7 < 100 (fill history likely truncated — X closing fills fetched)"`.

**`hyperliquid_profiler.py`** — `compute_balance_stats` now returns `cum_pnl_usd`.

**`reporter.py` — leaderboard fields silently dropped**
`build_wallet_profile` now captures a `leaderboard` block from the wallet dict: `account_value`, `all_time_pnl`, `all_time_roi` (fractional, e.g. 3.9 = 390%), `month_roi`, `week_roi`. `_profile_to_candidate` removes all synthetic $10k balance fields (`starting_balance`, `ending_balance`, `net_growth_pct`, `peak_balance`, `lowest_balance`) and emits real leaderboard fields + `cum_pnl_usd`.

### Data model (`models.py` + `types/index.ts`)
- **Removed:** `starting_balance`, `ending_balance`, `net_growth_pct`, `peak_balance`, `lowest_balance`
- **Added:** `account_value`, `all_time_pnl`, `all_time_roi`, `month_roi`, `week_roi` (all `Optional[float]`), `cum_pnl_usd: float = 0.0`

### UI (`frontend/`)

**`StatCard.tsx`** — added `onClick?: () => void` (renders as `<button>` with hover) and `disabled?: boolean` (35% opacity, `cursor-not-allowed`, no hover).

**`PoolOverview.tsx`** — accepts `onNavigate?: (tab: string, market?: string) => void`. Cards now navigate:
- Wallets Scanned → `disqualified` tab
- Qualified → `rankings`; disabled when `total_qualified === 0`
- Crypto → `rankings` with `market='crypto'`; disabled when count = 0
- Forex → `rankings` with `market='forex'`; disabled when count = 0

**`Rankings.tsx`** — accepts `initialMarket?: 'all' | 'crypto' | 'forex'` so the market filter tab is pre-selected when navigating from Overview. "Net growth %" column replaced with **Cum. PnL** (`cum_pnl_usd`), sign-colored.

**`CandidateProfile.tsx`** — stat card row replaced with real leaderboard data (Acct value, All-time PnL, All-time ROI, Peak DD, Trades). Responsive money formatting:
- Desktop (`sm+`): raw number with commas below 8 raw digits (< $10 M), then `m`/`b`
- Mobile: always abbreviated — `k` / `m` / `b`
- ROI uses `toLocaleString` for thousands separator, e.g. `+5,769%`

**`SmartMoney/index.tsx`** — `rankingsMarket` state wired through `onNavigate` → `Rankings.initialMarket` so market pre-selection works on tab switch.

### Pending verification
All pipeline fixes require a fresh run. Expected outcomes:
- Accounts with truncated fill history → disqualified (matched trades < min_trades)
- Net-negative wallets → disqualified (profitability check)
- `account_value`, `all_time_pnl`, `all_time_roi` populate in CandidateProfile from real leaderboard data

---

## Session — UI clarity audit (2026-05-27)

### `smart-money/run_progress.py`
- **`complete()` reset all counts to zero** — the final `progress.json` had `wallets_scanned: 0`, `wallets_total: 0`, etc., so the UI had no scan data on completion.
- Fix: `ProgressWriter` now tracks peak values during `update()` calls (`_last_wallets_scanned`, `_last_wallets_total`, `_last_qualified`, `_last_disqualified`) and passes them into `complete()`. The final `progress.json` now carries the real counts.

### Scanner Terminal — "Run complete" appeared 3×
Three independent places each rendered "Run complete" after a run:
1. **Header** `· run complete` — kept, this is the canonical status indicator.
2. **Body text** — was `progress.message || (isDone ? 'Run complete' : ...)`. Changed to show `"X wallets processed"` when done (using the now-preserved count), or `"Completed"` as a fallback. Errors show `progress.message` as before.
3. **Stats bar fallback** — removed `{isDone && counts===0 → "Run complete"}` entirely. Stats bar now only renders when there is real numeric content (`wallets_total > 0 || qualified > 0 || disqualified > 0 || scanRate >= 0.5`). The wallet count row is also hidden when done (body already shows it).

### `PoolOverview.tsx` — "API Scanned" card
- Label `"API Scanned"` → `"Wallets Scanned"` — unambiguous, no jargon.
- Sub `"top candidates, 1 sources"` → source name(s) directly, e.g. `"hyperliquid"` or `"3 sources"`. Immediately tells you where the data came from; grammar correct for any count.

### `StatCard.tsx` — clickable cards now signal navigation
- Added a subtle `›` at the right end of the label row when `onClick` is present.
- Makes it clear the card is a nav link without adding visual noise.

### `Rankings.tsx` — result count
- Added `"X of Y candidates"` at the right side of the filter bar.
- Instantly shows whether filters are active and how many are displayed.

### `DisqualifiedLog.tsx` — missing reason categories
- `"Matched trades N < 100 …"` now maps to `activity` (was falling through to `other`).
- `"Net unprofitable: total PnL $-X"` now maps to `drawdown`.

### `SmartMoney/index.tsx` — Export button
- Was a live-looking button with no `onClick`. Now `disabled` + `opacity-40` + tooltip `"Export coming soon"`.

---

## Session — cache management + terminal fix (2026-05-27)

### Clear Cache feature (on-demand fills cache wipe)

**Why:** The fills cache stores raw trade history per wallet for 24h to avoid re-fetching on same-day reruns. Users need a way to force a fresh fetch (e.g. to ensure data is current before a retest).

**`smart-money/database.py`**
- Added `clear_fills_cache() -> int` — `DELETE FROM fills_cache`, returns row count.

**`backend/routers/smart_money.py`**
- Added `_SM_DB_PATH = cfg.SMART_MONEY_ROOT / "data" / "smart_money.db"` module constant.
- Added `GET /smart-money/cache/stats` → `{ wallets_cached, oldest_fetched_at, newest_fetched_at }`. Uses `sqlite3` directly (no smart-money venv dependency). Polled every 60s by the UI.
- Added `DELETE /smart-money/cache` → `{ cleared: int }`. Wipes fills_cache table.

**`frontend/src/api/client.ts`**
- Added `delete: <T>(path) => request<T>(path, { method: 'DELETE' })` to the `api` object.

**`frontend/src/types/index.ts`**
- Added `CacheStats { wallets_cached, oldest_fetched_at, newest_fetched_at }`.
- Added `CacheClearResult { cleared }`.

**`frontend/src/hooks/useSmartMoney.ts`**
- Added `useCacheStats()` — polls `/smart-money/cache/stats` every 60s.
- Added `useClearCache()` — mutation for `DELETE /smart-money/cache`; success toast shows exact count removed.

**`frontend/src/pages/SmartMoney/index.tsx`**
- Added `confirmClear` state (boolean) for two-step confirmation guard.
- **Idle state only** (hidden during live runs): `Clear cache (N)` button shows live cached count.
  - Disabled + greyed out when cache is empty.
  - First click → swaps to inline confirmation bar: `⚠ Clear N cached wallets?  Cancel · Yes, clear`
  - Cancel → reverts to normal button.
  - "Yes, clear" → fires mutation, dismisses confirmation, shows toast.

### Scanner Terminal — hide on historical run

**Problem:** The terminal is driven by `progress.json` (always the latest run). When the user selects an older run from the dropdown, the terminal still displayed the latest run's "complete" state — confusing while browsing unrelated data.

**Fix (`SmartMoney/index.tsx`):**
- Added `isViewingHistoricalRun`: true when `selectedRunId` is explicitly set AND differs from `runs[0].run_id`.
- `showProgress` is now `effectiveProgress != null && !isViewingHistoricalRun`.
- Terminal hides entirely when browsing any run that is not the most recent one. Live runs always show the terminal regardless.

---

## Session — Bots page: uptime fix, per-row executing state, stop safety (2026-05-27)

### Uptime fix (`routers/bots.py`)
- `_uptime_seconds` now reads `state.get("started")` first — the actual Unix timestamp float that `shared/bot_state.py` writes via `time.time()`. Previous code only tried `started_at` / `start_time` (neither of which exist in the schema). Uptime now populates correctly for running bots.
- `import time as _time` moved to module level; inline `import time` stubs inside restart functions removed.

### Per-row executing state (`pages/Bots/index.tsx`)
- `pendingBotName` / `pendingBotAction` derived from mutation `.variables` (TanStack Query stores the last `mutate()` arg) to identify which specific bot is currently being acted on.
- When a row's bot is being acted on: buttons replaced by an inline spinner + label ("Restarting…", "Starting…", "Stopping…") — status shown on the exact row, not the global panel.
- **All rows' action buttons disabled while any action (global or per-bot) is in-flight** (`anyBusy = anyPending`). Prevents double-firing.
- Global "Executing…" label only shown for global control actions (start/stop/restart/emergency all), not per-bot actions.

### Note
- The "unexpectedly stopped" alert suppression and `[command center]` notifications were implemented in a later session — see below.

---

## Session — Bots page: controls, per-row actions, UX polish (2026-05-27)

### Backend (`routers/bots.py`)
- Control actions fully implemented (previously 501 stubs): `POST /bots/start|stop|restart|emergency`
- Per-bot endpoints added: `POST /bots/{bot_name}/start|stop|restart`
  - Start: `schtasks /run /tn {task_name}`
  - Stop: `wmic process where "commandline like '%{bot_key}%'" call terminate`
  - Restart: per-bot stop + 3s sleep + per-bot start

### Hooks (`hooks/useBots.ts`)
- Added `useBotStart`, `useBotStop`, `useBotRestart`, `useBotEmergency` (global)
- Added `useBotStartOne`, `useBotStopOne`, `useBotRestartOne` (per-bot, take `botName` as mutationFn arg)
- All control mutations invalidate `['bots', 'snapshot']` after 4s to allow VPS state to settle

### Bots page (`pages/Bots/index.tsx`)
- **Per-row action buttons**: Start (▷, green, disabled when RUNNING), Stop (■, red, disabled when not RUNNING), Restart (↺), Log (📄)
- **Stop buttons are red** (`neg` color) — both global "Stop all" and per-row Stop — and both require a confirmation modal before firing
- **Per-row Stop confirm**: dedicated modal naming the specific bot, `bg-neg-muted` confirm button
- **Start all disabled** when all bots are already running (`running === total`)
- **Emergency stop double-confirm**: custom `EmergencyModal` with red border, warning block about open positions, checkbox "I understand" must be ticked to unlock the Kill button
- **Scheduled job indicators**: `JobDot` shows gold glow (`shadow-[0_0_6px_#d9a441]`) for all non-running states (STOPPED + UNKNOWN both = "waiting for trigger"). Tooltip on hover: "Scheduled — waiting for next trigger". "Scheduled" text pill removed.
- **Manual refresh button** in header: calls `refetch()`, spins while `isFetching`, disabled during fetch
- `ScaffoldBanner` removed

### Overview (`pages/Overview.tsx`)
- `JobPill` updated to match: gold dot with glow for non-running, tooltip on hover

---

## Session — UI branding + Overview dashboard (2026-05-27)

### Branding overhaul
- **Indigo-black theme** — surface colors shifted to purple-tinted dark (`bg-base #080810`, `bg-sunken #0d0d1a`) so the electric cyan accent pops via complementary contrast. Glow shadow intensities bumped.
- **TopBar** simplified to brand wordmark only (`LWG` gradient cyan→gold + `Capital` white) + refresh button. No page name, no timestamp.
- **Sidebar** — logo image (`/logo.png`) in a centred zone at the top. "WORKSPACE" section label removed. Settings moved to footer after VPS/API status dots. `Radar` icon for Smart Money.
- **`/public/logo.png`** — processed from `IMG_1045.JPG`: flood-fill background removal from all 4 corners (removes white + circuit board pattern), navy letters → `#e9eaf0`, teal accents → `#00e5ff`. Full mark including "CAPITAL" text (533×466 px transparent PNG).

### Overview page — fully implemented
Replaces the scaffold with a real dashboard:
- **Stat row (4 cards, all clickable):** Bots Running (`X / 4`), Balance (exact `$7,432.50`), Last Scan (relative time), Candidates (count from latest run).
- **Bots card:** animated skeleton while VPS SSH loads; bot rows with status dot + name + daily PnL % + status badge; "locked" pill when `day_locked`; scheduled jobs + Telegram status footer.
- **Smart Money card:** pulsing cyan banner if pipeline is running (live % + stage name); last run stats (time, candidate count, run ID); historical run count footer.
- **Navigation:** every stat card and section card header navigates to the corresponding module page on click.

---

## Session — Bots page: status pills, System card, control gate (2026-05-27)

### Status indicators
- **`StatusPill` component** replaces the old dot+text approach everywhere — green `bg-pos-muted text-pos-text` for RUNNING, red `bg-neg-muted text-neg-text` for STOPPED/ERROR. Used on Bots page table, Overview `BotRow`, and the Telegram service row.
- **"Bots Running" stat card** — sub-text and `subVariant` now correctly reflect partial-stop state: `pos` when all running, `neg` when all stopped, `neutral` (not green) when some are stopped.

### Telegram card removed; System card reorganised
- The Telegram `StatCard` was removed from the 4-card stat row (grid shrunk to 3 columns) — it duplicated information already visible below.
- "Scheduled Jobs" card renamed to **System** with two sub-sections:
  - **Jobs** — Monitor, P&L Tracker, Reporter with gold-glow `JobDot` + schedule text (these are Task Scheduler tasks)
  - **Services** — Telegram with `StatusPill` (long-running daemon started by `startup_coordinator.py`, not a scheduled task)

### Start All gate
- Changed from "disabled when all running" (`allRunning`) → "disabled when **any** running" (`anyRunning = filteredRunning > 0`).
- Rationale: `SYS_STARTUP` starts everything from scratch — running it while any bot is up risks duplicate processes. Per-row ▷ handles the partial-start use case.
- Tooltip when disabled: `"Stop all bots first — use ▷ on a row to start an individual bot"`.

---

## Session — Critical bug fixes: Telegram notifications + spinner (2026-05-27)

### Bug 1 — Stop from command center gave wrong/no Telegram alert

**Root cause:** The crash monitor on the VPS reads `stop_suppress.json` before sending "unexpectedly stopped" alerts. `algo.py`'s control panel writes a suppress key AND sends its own `[control panel]` notification. The command center only wrote the suppress key — it never sent any notification.

**Fix (`routers/bots.py`):**
- Added `_notify_telegram()` using `urllib.request` (built-in, no new deps). Uses the same token/chat as `notify.py` and `algo.py`.
- Added `_KEY_DISPLAY` reverse map (`bot_key → display name`) for notification text.
- All 7 action endpoints now send a notification after the SSH action completes:

| Endpoint | Message |
|---|---|
| `POST /bots/{name}/stop` | `⏹ *SMC Trend* stopped [command center]` |
| `POST /bots/{name}/start` | `▶️ *Scalper* starting [command center]` |
| `POST /bots/{name}/restart` | `🔄 *FFT* restarting [command center]` |
| `POST /bots/stop` | `⏹ All bots stopped [command center]` |
| `POST /bots/start` | `▶️ All bots starting [command center]` |
| `POST /bots/restart` | `🔄 All bots restarting [command center]` |

### Bug 2 — Spinner ("Stopping…") never cleared after action

**Root cause:** The 45 s timeout lived inside `useEffect([snapshot])`. That effect only fires when `snapshot` updates. If the snapshot refetch is slow or fails after a stop action (SSH busy/timing out after VPS kill), `snapshot` never changes, the effect never fires, and the `timedOut` condition is never evaluated — spinner runs indefinitely.

**Fix (`pages/Bots/index.tsx`):**
- Added `transitionTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})`.
- `setPendingFor()` now also schedules a hard-clear `setTimeout` after **30 s** — fires regardless of snapshot state.
- `clearPendingFor()` cancels the timer when the snapshot confirms the expected state first (happy path). Both paths call the same function; cleanup `useEffect` cancels all timers on unmount.
- The `useEffect([snapshot])` snapshot-based clearing is kept as the primary/fast path; the `setTimeout` is the guaranteed fallback.

### Bug 3 — Status detection reading stale `bot_state.json`
(Fixed in the previous session, documented here for completeness.)
All `BOT_*` Task Scheduler tasks are **Disabled** on the VPS — `schtasks` reports `"Disabled"`, not `"Ready"`. The old `elif task_status in ("Ready", "")` branch never matched, causing fallthrough to `bot_state.json` which still says `"running"` after a hard kill. Fix: simplified to process-list-only: `running_in_procs → "RUNNING"`, otherwise `"STOPPED"`.

---

## Session — Bots table: alignment, layout, and column overhaul (2026-05-27)

### `pages/Bots/index.tsx`

**Vertical alignment** — added `align-middle` to all `<th>` and `<td>` elements. Inline-flex badges (StatusPill, account type pill) were causing rows to expand and content to drift to the text baseline; `align-middle` pins everything to the row's centre.

**Account type pill conditional** — the DEMO/LIVE pill next to the account number is only rendered when `filter === 'all'`. On the Demo or Live filter tab the type is already implied by the tab; showing the pill was redundant.

**Logs column** — the `FileText` log button was extracted from the Actions column flex group into its own `<td>` with a dedicated `"Logs"` header. `colSpan` on the empty-state row updated 7 → 8.

**Column reorder** — final order: `Bot | Status | Balance | Day P&L | Account | Uptime | Actions | Logs`. Groups the most critical operational info (Status) immediately after the identifier, keeps financial metrics together, and pushes reference info toward the middle.

**Universal left-align + spacing** — all `text-right` removed from both headers and cells; padding bumped from `px-[14px]` to `px-6` (24 px) on every header and cell. `justify-end` removed from the Actions flex container and the spinning transition state. Account cell badge alignment: wrapped account number + type pill in `<div className="flex items-center gap-[6px]">` to prevent baseline drift.

---

## Session — Bots header countdown + VPS status dot (2026-05-27)

### Bots header refresh button (`pages/Bots/index.tsx`)
Collapsed the separate `<span>` status text and `<button>` into a single combined button: `[↺] 45s · last 8:58:10 PM`. The countdown is derived live from `dataUpdatedAt` — a 1-second `setInterval` tick forces a re-render, then `Math.max(0, interval - elapsed)` is computed inline (no drift). Countdown resets automatically when TanStack Query marks a fresh fetch. When `hasPendingTransitions` is true the interval drops to 3 (matching the fast-poll cadence). While fetching, shows `[↺ spinning] Refreshing…`. Countdown number styled `text-accent font-mono tabular-nums` to signal it's live.

### VPS status dot (`components/Sidebar.tsx` + `routers/bots.py`)
- Added `GET /bots/ping` endpoint: runs `ssh forexvps "echo ok"` via `_ssh()`, returns `{"status": "ok"}` or `{"status": "error"}` (catches `TimeoutExpired` and any other exception — never raises HTTP error, returns graceful error instead).
- Sidebar now polls `/bots/ping` every 30s (same cadence as the API health check).
- `vpsOk` derived the same way as `apiOk`: `true` when status is `"ok"`, `false` on error, `null` while loading.
- `<StatusDot ok={vpsOk} />` replaces the hardcoded `ok={null}` grey dot.
- VPS label text is now dynamic: `forexvps` (green), `checking` (grey), `unreachable` (red) — mirrors the API row's pattern exactly.

---

## Session — Bots row buttons + spinner timing (2026-05-27)

### Context-sensitive row action buttons (`pages/Bots/index.tsx`)
**Rule:** hide when the action makes no sense; disable when it makes sense but isn't currently available.

- **Stopped bot** → Start only. Restart and Stop are hidden (not disabled) — both are semantically wrong on a stopped process.
- **Running bot** → Stop + Restart. Start is hidden — the bot is already running.

Previously all three buttons were always rendered, with Start disabled when running and Stop disabled when stopped. Restart had no status guard at all, so it appeared enabled even on stopped bots.

### Action-specific hard-clear timeouts
The hard-clear `setTimeout` in `setPendingFor` is now action-aware:
- **Start: 60 s** — scheduler task invocation + Python process boot takes time to show in `wmic` output
- **Stop / Restart: 20 s** — process kill is near-instant

Previously all actions shared a flat 30 s timeout, which was too short for start (spinner cleared before the bot appeared as RUNNING) and unnecessarily long for stop.

### Refetch on hard-clear
When the hard-clear fires, `await refetch()` runs before `clearPendingFor()`. Previously the timer fired, removed the transition, and the table showed whatever stale snapshot data was last cached — often still showing the old state (e.g. bot still STOPPED after starting). Now the spinner persists until fresh VPS data arrives, then clears with the correct state.

---

## Session — Bots page: simplified control flow + P&L column (2026-05-28)

### Bots page — control spinner simplified

**Previous design:** A `PendingTransition` state machine tracked per-bot expected status changes with fast-polling (3 s interval), effects keyed on `dataUpdatedAt`, `prevStatus` comparisons, and a 90 s timeout fallback. Multiple iterations failed because of stale closures, async interval edge cases, and `dataUpdatedAt` not updating as expected in TanStack Query v5.

**New design (current):** Removed entirely:
- `PendingTransition` type
- `pendingTransitions` state and `setPendingFor()` helper
- Both `useEffect` hooks (clearing effect + fast-poll interval)
- `hasPendingTransitions` derived value
- All inline `onSuccess` callbacks on `mutate()` calls

Spinner now shows only while the HTTP request is in-flight (`startOne.isPending` / `stopOne.isPending` / `restartOne.isPending`). Data update is handled by the existing `invalidateQueries(['bots', 'snapshot'])` in the mutation hook's `onSuccess` — one fresh fetch fires automatically after every action. No polling, no state tracking.

### Per-bot buttons — no longer disabled by other rows' actions

**Bug:** `disabled={anyBusy}` included `anyPerBotPending` — starting/stopping one bot disabled every other row's buttons.

**Fix:** Per-bot row buttons use `disabled={anyGlobalPending}` only. The active row already shows a spinner instead of buttons (so its actions can't be double-fired). Other rows stay enabled. Global control buttons (start all / stop all / restart all) still use `anyBusy` — you shouldn't fire a global action while a per-bot action is in-flight.

| Situation | Active row | All other rows | Global buttons |
|---|---|---|---|
| Per-bot action in-flight | Spinner (no buttons) | ✅ Enabled | Disabled |
| Global action in-flight | Disabled | Disabled | Disabled |
| Idle | Enabled | Enabled | Enabled |

### P&L column — Daily → Overall

**Changed:** The "Day P&L" column now shows **Overall P&L** (total growth since the $1,000 starting balance).

| File | Change |
|---|---|
| `backend/models.py` | `BotStatus.daily_pnl_pct` → `total_pnl_pct: Optional[float]` |
| `backend/routers/bots.py` | Reads `state.get("total_pnl_pct")` from `bot_state.json` (was `daily_pnl_pct`) |
| `frontend/src/types/index.ts` | `BotStatus.daily_pnl_pct` → `total_pnl_pct: number \| null` |
| `frontend/src/pages/Bots/index.tsx` | Column header `"Day P&L"` → `"Overall P&L"`, cell renders `bot.total_pnl_pct` |
| `frontend/src/pages/Overview.tsx` | `BotRow` reads `bot.total_pnl_pct` |

`bot_state.json` fields: `daily_pnl_pct` resets each day; `total_pnl_pct` is cumulative growth since the $1,000 demo start (written by `pnl_tracker` via `shared/bot_state.py`).

---

## Session — Bots page: detail panel + nav polish (2026-05-28)

### Sidebar — nav icon glow replaces "Live" pills (`components/Sidebar.tsx`)
- Removed the green `"Live"` pill from all built workspace nav items (Overview, Smart Money, Bots) — it was a static, hardcoded flag with no runtime meaning.
- `"Soon"` pill on unbuilt items (Backtests, Stress Tests) kept — still informative.
- Active nav item icon now gets `text-accent drop-shadow-[0_0_6px_#34d399]` with a 120 ms CSS transition. Replaces the pill as the "this is where you are" signal.

### Bot row expand — detail panel (`pages/Bots/index.tsx`)
Each bot row now has a `ChevronRight` icon in the name cell (rotates 90° when open). Clicking the name cell toggles an inline expanded `<tr>` below the row showing:

**4 stat tiles (flex row):** Daily P&L, Weekly P&L, Trades Today, Peak Balance — each in its own card with a 16px colored dollar amount and smaller pct annotation.

**Config strip (single compact line):** `Goal X% · Daily cap X% · Weekly cap X% · Updated Xm ago`

**Lock banner (conditional):** shown if `day_locked` is true, includes `lock_reason` if set.

### Backend — `BotStatus` detail fields (`models.py`, `routers/bots.py`)

New fields on `BotStatus`:

| Field | Source in `bot_state.json` |
|---|---|
| `daily_pnl` / `daily_pnl_pct` | `daily_pnl` / `daily_pnl_pct` |
| `weekly_pnl` / `weekly_pnl_pct` | `weekly_pnl` / `weekly_pnl_pct` |
| `peak_balance` | `peak_balance` (0 → `None`) |
| `trades_today` | `trades_today` |
| `lock_reason` | `lock_reason` (empty string → `None`) |
| `last_updated` | `last_updated` (empty string → `None`) |
| `daily_goal_pct` / `daily_cap_pct` / `weekly_cap_pct` | `_BOT_THRESHOLDS` dict in `bots.py` |

`_BOT_THRESHOLDS` added to `bots.py` (mirrors `bot_state.py`'s `BOT_THRESHOLDS`):
```python
_BOT_THRESHOLDS = {
    "smc_trend":      {"daily_goal": 2.0,  "daily_cap": 10.0, "weekly_cap": 20.0},
    "mean_reversion": {"daily_goal": 2.0,  "daily_cap": 10.0, "weekly_cap": 20.0},
    "scalper":        {"daily_goal": 10.0, "daily_cap": 8.0,  "weekly_cap": 20.0},
    "fft":            {"daily_goal": 2.0,  "daily_cap": 5.0,  "weekly_cap": 15.0},
}
```

`instrument` field was considered but removed — hardcoding `"XAUUSD"` was misleading since these accounts trade multiple pairs.

### `api/client.ts` — `patch` method added
Groundwork for the Configure tab. The `patch` method was added to the `api` object; it is not yet called by any hook or page.

---

## What still needs to be done

### Step 4 — Bots page: two-tab layout (Monitor + Configure) ← **NEXT**

User chose this design: keep the existing Monitor tab unchanged, add a Configure tab with 4 bot cards side by side for comparing performance and editing risk caps in one view.

#### What to build

**Tab structure** — add `tab: 'monitor' | 'configure'` state to the `Bots` component. Tab switcher in the header (same style as the Account filter tabs already on the page). Refresh button only shown on Monitor tab.

**Monitor tab** — zero changes. All existing table, stat cards, system panel, control actions stay exactly as-is.

**Configure tab** — replace the table area with a 4-column grid of bot config cards:

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ SMC Trend        │  │ Mean Reversion   │  │ Scalper          │  │ FFT              │
│ ● Running        │  │ ● Running        │  │ ● Stopped        │  │ ● Running        │
│──────────────────│  │──────────────────│  │──────────────────│  │──────────────────│
│ PERFORMANCE      │  │ PERFORMANCE      │  │ PERFORMANCE      │  │ PERFORMANCE      │
│ Daily  +$45 1.6% │  │ Daily  ...       │  │ Daily  —         │  │ Daily  ...       │
│ Weekly +$120 4%  │  │ Weekly ...       │  │ Weekly —         │  │ Weekly ...       │
│ Trades today  3  │  │ Trades ...       │  │ Trades —         │  │ Trades ...       │
│ Uptime   3h 22m  │  │ Uptime ...       │  │ Uptime —         │  │ Uptime ...       │
│──────────────────│  │──────────────────│  │──────────────────│  │──────────────────│
│ RISK CAPS        │  │ RISK CAPS        │  │ RISK CAPS        │  │ RISK CAPS        │
│ Daily goal  2.0% │  │ Daily goal  2.0% │  │ Daily goal 10.0% │  │ Daily goal  2.0% │
│ Daily cap  10.0% │  │ Daily cap  10.0% │  │ Daily cap   8.0% │  │ Daily cap   5.0% │
│ Weekly cap 20.0% │  │ Weekly cap 20.0% │  │ Weekly cap 20.0% │  │ Weekly cap 15.0% │
│──────────────────│  │──────────────────│  │──────────────────│  │──────────────────│
│ [Save config]    │  │ [Save config]    │  │ [Save config]    │  │ [Save config]    │
│ [Save & Restart] │  │ [Save & Restart] │  │ [Save & Restart] │  │ [Save & Restart] │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

Each card sections: header (name + StatusPill), Performance (read-only — Daily P&L, Weekly P&L, Trades Today, Uptime), Risk Caps (editable number inputs with % suffix), Action buttons.

#### Implementation details

**Form state** in `Bots` component:
```typescript
type BotForm = { daily_goal: string; daily_cap: string; weekly_cap: string }
const [configForms, setConfigForms] = useState<Record<string, BotForm>>({})
```
Initialize from `snapshot.bots` via `useEffect([snapshot])` — only init if `!prev[bot.name]` so user edits survive snapshot refreshes. On successful save, delete that bot's form entry so it re-initializes from the new snapshot values.

**Dirty detection** — compare form string values to `(bot.daily_goal_pct ?? '').toString()` etc. "Save config" button is accent-colored + enabled when dirty, grey + disabled when clean.

**New helper components** (add at top of file alongside existing helpers):
- `ConfigRow` — `label` (left) + `<input type="number">` + `%` (right). Input: `w-[64px] bg-bg-sunken border border-border-subtle rounded px-[7px] py-[4px] text-[12px] font-mono text-right focus:border-accent/50`.
- `PerfRow` — label (left) + `±$X.XX (±X.XX%)` (right), colored pos/neg/tertiary.

**Backend — `PATCH /bots/{bot_name}/config`** (add to `routers/bots.py`):
```python
from pathlib import Path as _Path

_CONFIG_OVERRIDES_PATH = _Path(__file__).parent.parent / "config_overrides.json"

def _load_config_overrides() -> dict[str, dict[str, float]]:
    if _CONFIG_OVERRIDES_PATH.exists():
        try: return json.loads(_CONFIG_OVERRIDES_PATH.read_text())
        except Exception: pass
    return {}

def _save_config_overrides(overrides: dict) -> None:
    _CONFIG_OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2))

def _get_thresholds(bot_key: str) -> dict[str, float]:
    overrides = _load_config_overrides()
    base = dict(_BOT_THRESHOLDS.get(bot_key, {}))
    base.update(overrides.get(bot_key, {}))
    return base
```
The snapshot builder already calls `thresholds = _BOT_THRESHOLDS.get(bot_key, {})` — change to `thresholds = _get_thresholds(bot_key)`.

Add `BotConfigUpdate(BaseModel)` to `models.py`:
```python
class BotConfigUpdate(BaseModel):
    daily_goal_pct: float
    daily_cap_pct: float
    weekly_cap_pct: float
```

Add the endpoint — note it must come BEFORE the `/{bot_name}/start|stop|restart` routes since FastAPI matches literally first:
```python
@router.patch("/{bot_name}/config")
def save_bot_config(bot_name: str, config: BotConfigUpdate):
    _, bot_key = _resolve_bot(bot_name)
    overrides = _load_config_overrides()
    overrides[bot_key] = {
        "daily_goal": config.daily_goal_pct,
        "daily_cap":  config.daily_cap_pct,
        "weekly_cap": config.weekly_cap_pct,
    }
    _save_config_overrides(overrides)
    return {"status": "ok"}
```

**Frontend hook** (`hooks/useBots.ts`) — `api.patch` was already added to `client.ts`:
```typescript
export function useSaveBotConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ botName, config }: { botName: string; config: { daily_goal_pct: number; daily_cap_pct: number; weekly_cap_pct: number } }) =>
      api.patch<{ status: string }>(`/bots/${encodeURIComponent(botName)}/config`, config),
    onSuccess: (_data, { botName }) => {
      toast.success(`${botName} config saved`)
      qc.invalidateQueries({ queryKey: ['bots', 'snapshot'] })
    },
    onError: (err, { botName }) => toast.error(`${botName} config save failed: ${err}`),
  })
}
```

**"Save & Restart"** — uses `mutateAsync` to await the save, then fires `restartOne.mutate(botName)`:
```typescript
const handleSaveAndRestart = async (botName: string, form: BotForm) => {
  try {
    await saveConfig.mutateAsync({ botName, config: { daily_goal_pct: +form.daily_goal, daily_cap_pct: +form.daily_cap, weekly_cap_pct: +form.weekly_cap } })
    setConfigForms(prev => { const n = {...prev}; delete n[botName]; return n })
    restartOne.mutate(botName)
  } catch { /* handled in hook */ }
}
```

#### Limitation to document in UI
Config overrides are persisted in `backend/config_overrides.json` and reflected in the dashboard immediately. The running bot process on VPS **does not yet read this file** — the actual day-lock behaviour still uses the hardcoded `BOT_THRESHOLDS` in `shared/bot_state.py`. To activate VPS-side cap changes, `pnl_tracker.py` needs to read from a shared config source. This is a separate VPS code change, not part of this frontend task.

---

### Step 5 — End-to-end test of Smart Money pipeline + dashboard
The pipeline trigger, terminal, lock-down UI, and file-reading are all implemented. Click "Run pipeline" in the UI and verify:
- Terminal appears instantly (< 200 ms) on click, tabs lock down
- Addresses stream in during scan phase with `PASS ✓` glow and dim fails
- Run completes → tabs unlock, new run appears in dropdown, Rankings/Pool Overview populate

**If 0 qualified candidates again**: check `disqualified.json` for dominant reason — bot profile at 70% win rate + 30% drawdown should be finding candidates now.

Expected directory shape (implemented in `StageReporter.export_run_dir()`):
```
smart-money/reports/
├── progress.json             → RunProgress model (overwritten each run)
└── {YYYYMMDD_HHMMSS}/
    ├── meta.json             → SmartMoneyRun model
    ├── candidates.json       → list of Candidate (flat, API shape)
    └── disqualified.json     → list of DisqualifiedCandidate
```

### Step 6 — Verify Bots monitoring against live VPS
`GET /bots/snapshot` makes two SSH calls to `forexvps`. Verify:
- The wmic + schtasks parsing matches what the VPS actually returns
- `bot_state.json` exists at `C:\trading\algos\markets\fx\instances\{bot_name}\bot_state.json`
- The `BotSnapshot` response populates correctly in the UI

### Step 7 — Backtests module
Backend: `GET /backtests/runs` reads from `algos/` backtest output directory (TBD). Frontend `src/pages/Backtests.tsx` is scaffolded. See `design/LWG_Capital_Command_Center_Build_Spec.md` section 7 for the full spec.

### Step 8 — Stress Tests module
Backend: `GET /stress-tests/results` reads stress test output (TBD). Frontend `src/pages/StressTests.tsx` is scaffolded.

---

## Never do

- Touch `algos/` or `smart-money/` source code from within this subsystem — read their output files only
- Commit secrets: `config.json` contains local paths only (no credentials), but `.env` or any credential files must never be committed
- Add frontend routes without adding a corresponding `NavItem` entry in `Sidebar.tsx`
- Change Telegram token/chat constants in `routers/bots.py` independently of `algos/shared/notify.py` — they must stay in sync
