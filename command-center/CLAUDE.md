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
| Smart Money — Config | ✅ Live | Reads/writes `smart-money/config/config.json` |
| Smart Money — Pool Overview | ✅ Live (UI) | Needs qualifying candidates to show real data |
| Smart Money — Rankings | ✅ Live (UI) | Needs qualifying candidates |
| Smart Money — Candidate Profile | ✅ Live (UI) | Needs qualifying candidates |
| Smart Money — Disqualified Log | ✅ Live | Category badges, readable reason formatting, filter tabs with counts, wallet hyperlinks |
| Smart Money — Run pipeline button | ✅ Live | `POST /smart-money/run` spawns `run_stage1.py`; 409 if already running; optimistic instant terminal |
| Smart Money — Scanner Terminal | ✅ Live | Matrix-style live address feed; hidden when viewing a historical run |
| Smart Money — Clear Cache button | ✅ Live | Two-step inline confirmation; shows live cached count; `DELETE /smart-money/cache` |
| Bots — monitoring table | ✅ Live (UI) | Needs VPS SSH verification |
| Bots — scheduled jobs | ✅ Live (UI) | Needs VPS SSH verification |
| Bots — log viewer | ✅ Live (UI) | Needs VPS SSH verification |

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

## What still needs to be done

### Step 4 — End-to-end test of Smart Money pipeline + dashboard ← **NEXT**
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

### Step 5 — Verify Bots monitoring against live VPS
`GET /bots/snapshot` makes two SSH calls to `forexvps`. Verify:
- The wmic + schtasks parsing matches what the VPS actually returns
- `bot_state.json` exists at `C:\trading\algos\markets\fx\instances\{bot_name}\bot_state.json`
- The `BotSnapshot` response populates correctly in the UI

### Step 6 — Overview page
Currently a scaffold. Should show a combined summary: bots running, SM pool size, recent pipeline run, last backtest. Pulls from existing endpoints — no new backend work needed.

### Step 7 — Enable bot control actions
Only after Step 5 is verified. Implement `POST /bots/start|stop|restart` in `routers/bots.py` using SSH calls mirroring CLAUDE.md's VPS deploy workflow. Keep Emergency Stop as last to implement. Remove `ScaffoldBanner` from Bots page and enable the control buttons when controls are live.

### Step 8 — Backtests module
Backend: `GET /backtests/runs` reads from `algos/` backtest output directory (TBD). Frontend `src/pages/Backtests.tsx` is scaffolded. See `design/LWG_Capital_Command_Center_Build_Spec.md` section 7 for the full spec.

### Step 9 — Stress Tests module
Backend: `GET /stress-tests/results` reads stress test output (TBD). Frontend `src/pages/StressTests.tsx` is scaffolded.

---

## Never do

- Touch `algos/` or `smart-money/` source code from within this subsystem — read their output files only
- Implement bot control actions before monitoring is verified (Steps 4–5 first)
- Commit secrets: `config.json` contains local paths only (no credentials), but `.env` or any credential files must never be committed
- Add frontend routes without adding the corresponding `ROUTE_LABELS` entry in `TopBar.tsx`
