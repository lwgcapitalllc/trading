# CLAUDE.md — LWG Capital Algo Trading Suite

**Purpose:** Standing instructions for the XAUUSD/forex MT5 bot suite running on the Windows VPS.
**Scope:** This covers the bots, shared utilities, risk rules, scheduler, and deploy for `algos/`. It does NOT cover `command-center/`, `smart-money/`, or `engines/regime/` internals (regime is imported via the `shared_regime.py` shim).
**Status:** Active — no live bots yet; all four first-attempt bots were deleted 2026-06-22 to rebuild backtest-first. Deployment plumbing preserved, and the live-trading pipeline for the first Python strategy is now being built (`docs/LIVE_TRADING_PIPELINE.md`).
**Last reviewed:** 2026-07-30 — **`algos/live/` landed: the live runtime for a `strategies/python/` bot on a named MT5 terminal** (see the section below and `docs/LIVE_TRADING_PIPELINE.md`), and `shared/mt5_ops.py` gained what it needs to drive one — pending/resting LIMIT orders (it could only send market orders, and the MPC strategies enter on a limit) plus the broker-clock fix on `get_candles`, which was labelling broker-server seconds as UTC and would have put every bar 2-3 hours out with a perfectly valid-looking timestamp. Also **credentials moved out of git.** The Telegram token was pasted into six files and committed; it has been revoked, and every copy is replaced by `shared/credentials.py`, which resolves env var → the git-ignored `algos/credentials.json` → empty. `credentials.template.json` (in git, values blank) is the setup path. Missing credentials are a no-op with one warning, never an exception. This is step 2 of `docs/LIVE_TRADING_PIPELINE.md`, the plan to take a validated `strategies/python/` bot to real orders on a named MT5 terminal — read it before touching anything under `bots/`, `shared/` or `notifications/`, because the pieces preserved from the deleted suite are about to get their first real consumer.

This file is auto-loaded by Claude Code at the start of every session. Read it fully before touching any code.

---

## Who You Are in This Project

You are a **quantitative developer** working on a live algo trading system.
Think like one at all times:

- Risk first. Every change that touches position sizing, stop logic, P&L tracking, or daily/weekly
  caps must be reasoned through before implementation. State the risk implication explicitly.
- No speculative abstractions. Only build what's needed for the current task.
- Precision in numbers. Don't approximate dollar amounts, percentages, or risk calculations.
- Latency awareness. Code runs on a Windows VPS with an MT5 connection. Avoid blocking calls,
  long loops without sleeps, or anything that could stall the main trading loop.
- When unsure about a trading rule or risk parameter, ask before changing it. Getting these wrong
  costs real money.

---

## Fast Index

### The Bots

There are currently **no live bots**. All four first-attempt bots — SMC Trend, Scalper, FFT, and Mean Reversion — were deleted 2026-06-22 to rebuild the suite backtest-first.

New bots follow the S.Y.S.T.E.M. process in `docs/BOT_DEVELOPMENT_METHOD.md` (specify → backtest → stress test → live demo). The reusable deployment plumbing left behind by the deleted suite — the MT5 connection layer, per-instance configs, Task Scheduler wiring, and the liveness/notification layer — is documented in `docs/BOT_DEPLOYMENT_INFRA.md` so a validated strategy can be wired to live demo without rebuilding the infrastructure.

### Shared Components

Shared logic lives in `shared/`; the launcher, coordinator, and config loader live in `bots/`.

**Deliberately parked (Aaron's call, 2026-07-06):** with no live bots, `shared_ai_brain.py`, `shared_calmar.py`, `shared_risk.py`, `shared_scanner.py`, and `mt5_ops.py` currently have no consumers. They are kept on purpose for the backtest-first rebuild — do not flag them as dead code or delete them. Note `shared_risk.py` may be superseded by the command-center sizing engine; decide its fate when the first new bot is wired.

| File | Location | Role |
|------|----------|------|
| `shared_ai_brain.py` | `shared/` | AI engine (Claude API), trade logger, daily performance logger |
| `shared_calmar.py` | `shared/` | Calmar ratio tracker, morning report |
| `shared_regime.py` | `shared/` | Market regime classifier shim: 5 labels (TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY). Each bot owns its own REGIME_RISK_TABLE. |
| `shared_scanner.py` | `shared/` | Multi-instrument watchlist scanner — `InstrumentScanner`, `SetupCandidate`, `LearningPhaseGate` |
| `shared_risk.py` | `shared/` | Dynamic risk / capacity engine — `RiskEngine` tracks portfolio-level risk budget per bot |
| `mt5_ops.py` | `shared/` | All MT5 operations — symbol-parameterized, single shared instance per bot |
| `bot_state.py` | `shared/` | Single source of truth read/write for each instance's `bot_state.json` |
| `credentials.py` | `shared/` | **The one place secrets are resolved.** Env var → git-ignored `algos/credentials.json` → empty. Never holds a literal. Copy `algos/credentials.template.json` to set a machine up. **Any key resolves, not just the canonical three** — a per-bot secret needs a new entry in that file and nothing else; the env name is always `LWG_<KEY IN CAPS>` (`env_name()`). |
| `notify.py` | `shared/` | Telegram sender. `send_telegram(text, chat_id="", token_key="")` — both optional, both empty = the shared group and the shared bot, so routing is PER BOT without a second sender. Reads `credentials.py`, never a hardcoded token, and NEVER raises — an unconfigured or unreachable notifier drops the message and prints once, because a notification channel must not be able to stop a trading loop. The four `notifications/` scripts now import their credentials from the same resolver instead of carrying inline copies (the 2026-07-06 refactor note, done 2026-07-30). |
| `structure_engine.py` | `shared/` | Market structure shim over `market_structure.StructureEngine` (canonical BOS/CHoCH/swing detection, ported from `indicators/structure_engine.pine`) — bot-facing `update(candle: dict)` interface |
| `bot_utils.py` | `bots/` | Config loader, logging, path resolver |
| `launcher.py` | `bots/` | Universal Task Scheduler launcher |
| `startup_coordinator.py` | `bots/` | Orchestrates bot startup sequence |

### `live/` — the live runtime (new 2026-07-30)

The seam between a validated backtest and real orders, for a `strategies/python/` bot. **It contains
no strategy logic:** the same strategy object the lab replays is stepped bar by bar, and this package
only supplies live bars and mirrors its intent onto the broker. That is what keeps a live result
comparable to a backtest result.

| File | Role |
|------|------|
| `runner.py` | The loop — connect, verify the version pin, warm the engines, poll for a CLOSED bar, step, reconcile, heartbeat. `--dry-run` is the default; `--live` must be typed. |
| `bridge.py` | Strategy intent ⇄ MT5 orders. Places/moves/cancels the resting limit, ratchets the stop, reports fills, and **HALTS when the emulator and the broker disagree** rather than continuing on a fiction. |
| `feed.py` | MT5 rates → the canonical replay frame. Never hands over the forming bar; reports how far behind it is so a gap re-warms instead of resuming. |
| `ledger.py` | Append-only JSONL: one record per bar, per blocked/missed setup, per trade open/close. This is what makes "why did this not work" answerable later. |
| `live_config.py` | One bot's instance config — which terminal, which account, which symbol, which version. Named `live_config` because bare `config` shadows the backend's. |
| `version.py` | The content pin. Re-hashes the strategy package at startup and refuses to run code that was never promoted. |

Two rules this package is built around, both in `docs/LIVE_TRADING_PIPELINE.md`:
**the strategy is authoritative and the bridge only mirrors** (that is what preserves Pine parity),
and **version isolation is two mechanisms** — params frozen in the instance config so lab edits
cannot reach a live bot, plus a source-hash pin the bot refuses to start against on mismatch.

**Everything account-, machine- and version-specific is in the instance config, never in code
and never global.** Which terminal, which account, which server, which symbol, which magic
number, which strategy version, which broker clock — and **where this bot reports**. Two bots on
two accounts are two different conversations, so `telegram_chat_id` routes a bot's messages to
its own group and `telegram_token_key` lets it send as its own Telegram bot. The key NAMES an
entry in `algos/credentials.json`; the token itself never enters an instance config. Both empty
= the shared default, so a one-bot setup needs neither.

Tests: `algos/tests/` — **83, all offline against a faked terminal**, so `pytest algos/` runs on the
Mac with no MT5 and no VPS. 54 cover this package, 16 cover the new pending-order layer in
`shared/mt5_ops.py`, 13 cover credential resolution and Telegram routing. One of them hashes a strategy package with both `version.py` and the lab's
scanner and requires the same answer — a pin that disagrees with the lab is worse than no pin.
The root `conftest.py` has to `collect_ignore` `algos/nt8/test_bt_switch.py`: it is a VPS debug
script, not a test, and it calls `sys.exit(1)` at IMPORT when pywinauto is missing, which crashes
collection for the whole repo rather than failing one file.

Standalone MT5 lab tooling (not imported by any bot) lives in `tools/`: `download_mt5_history.py` (warm the lab MT5 history cache) and `audit_mt5_data_quality.py` (its read-only companion — probes what the broker actually serves). Both run on the VPS against `C:\MT5_Lab`.

**Backtest data source — pinned to MT5_Lab only (2026-07-22).** All backtest price/tick data comes from the MT5 agent (`markets/fx/tools/mt5_agent.py`, VPS port 8766). Its `_ensure_mt5()` binds the Python API to the **MT5_Lab** terminal64.exe *only* (`TERMINAL_PATH` / `MT5_DATA_DIR`, else the baked-in `C:\MT5_Lab` default); if a live bot terminal (MT5_FFT, etc.) is already attached it drops and re-binds, and if MT5_Lab can't be reached it FAILS loudly rather than silently reading the wrong account. This closed a real leak — the old code called `mt5.initialize()` with no path and grabbed whichever terminal answered first. **MT5_Lab is logged into a Vantage demo (account 25815745, `VantageMarkets-Demo`)** so backtest data matches TradingView's `VANTAGE_XAUUSD`; this replaced the earlier PU Prime `XAUUSD.s` feed. Vantage's gold symbol name/suffix may differ from `XAUUSD.s` — if a run returns no bars, check the symbol name first. To pick up an agent-code change: `git pull` on the VPS **and** restart the `MT5AgentRDP` scheduled task (kill only the specific `mt5_agent.py` PID) — never a blanket `taskkill python.exe`, which also kills the NT8 backtest agent (`NT8Agent` task).

Multi-instrument architecture (Phases 1–5) explained in `docs/ARCHITECTURE.md`.

### Risk Rules Summary

n/a — no live bots.

### AI Thresholds

n/a — no live bots.

### What I Am Working On

**Phase:** No live bots. All four first-attempt bots were deleted 2026-06-22. The suite is being rebuilt backtest-first per the S.Y.S.T.E.M. method (`docs/BOT_DEVELOPMENT_METHOD.md`) — strategies are validated through the command-center backtest lab before any return to live demo trading. The reusable deployment infrastructure is preserved in `docs/BOT_DEPLOYMENT_INFRA.md`.

Update this section when the phase changes or a new open question arises.

---

## Documentation Rules — Non-Negotiable

**After every code change, update all affected docs in the same session.**
Not as a follow-up. Right now, before moving on.

### What to update and when

| Doc | Update when |
|-----|-------------|
| `CLAUDE.md § Fast Index` | Bots table, shared components, phase, or "What I Am Working On" change |
| `docs/ARCHITECTURE.md` | Multi-instrument system design changes (scanner, risk engine, correlation, learning gate) |

| `README.md` | Repo structure changes, new top-level files/dirs, workflow changes |
| `notifications/NOTIFICATIONS_GUIDE.md` | Any change to alerts, Telegram commands, monitor behavior |
| `scheduler/SCHEDULER_GUIDE.md` | Task Scheduler changes |

### Rules

1. If a doc describes behavior that no longer exists — correct or delete it. Stale docs are
   worse than no docs.
2. Keep the repo structure tree in `README.md` in sync with actual layout.
3. `scripts/README.md` bootstrap procedure must always produce a working VPS from scratch — verify mentally
   after any change that affects deploy or VPS setup.
4. `CLAUDE.md § What I Am Working On` — update this section to reflect current state.
   Never log session history here. Git commits are the changelog.

---

## Project Reference

Architecture deep-dive: `docs/ARCHITECTURE.md`
VPS recovery: `scripts/README.md` + `scripts/bootstrap_vps.ps1`
Notification system: `notifications/NOTIFICATIONS_GUIDE.md`

---

## Coding Conventions

- Python throughout. Self-contained bot files. Shared logic in `shared/` only.
- Config-driven via `config.json` per instance. Never hardcode paths or account numbers.
- All logging via `bot_utils.py` logger. No bare `print()` in bot code.
- Never duplicate logic between bots — if two bots need it, it goes in `shared/`.
- Never optimize to past data. Overfitting is the primary enemy.
- MT5 operations: always check return values. Log failures. Don't silently swallow errors.
- No unused imports. Every imported symbol must appear in the file body.

---

## Shared MT5 Architecture — Non-Negotiable

All MT5 operations live in `shared/mt5_ops.py`. Bots never implement MT5 logic directly.

Full `BotMT5` method list, the thin-delegate pattern, and what stays bot-specific are documented in `docs/ARCHITECTURE.md`.

### When to update `shared/mt5_ops.py`

Any time you add or fix behaviour that applies to ALL bots. Do not add it to one bot and
leave the others with stale code. Fix the shared implementation, update the thin delegates
in every bot that uses it.

### The pending-order layer (added 2026-07-30) — four MT5 behaviours to know

`place_pending_limit` / `modify_pending` / `cancel_pending` / `cancel_all_pending` /
`get_pending_orders` / `get_open_positions` / `normalize_volume` / `min_stop_distance`.
Added because the file could only send MARKET orders and the MPC strategies enter on a resting
limit. Each is a broker quirk that fails silently rather than loudly:

- **`MODIFY` silently ignores `volume`.** MT5 accepts the request, reports success, and leaves the
  size unchanged. A size change — which happens on almost every bar, because size is a % of moving
  equity — must be CANCEL + re-place, never a modify.
- **`SYMBOL_TRADE_STOPS_LEVEL` is checked twice**, market→limit *and* limit→stop. A limit that is
  legal against the market but whose stop sits inside the band is rejected at fill time, not at
  placement, which looks like a random missing trade hours later.
- **`normalize_volume` rounds DOWN and returns 0.0 below `volume_min`.** Rounding a sub-minimum size
  UP to the broker minimum would silently trade more risk than the strategy asked for; refusing is
  the honest answer.
- **Every read is MAGIC-filtered.** `get_pending_orders`/`get_open_positions` see only this bot's
  orders, so two bots on one account cannot cancel each other and a hand-placed trade is invisible
  to the reconciler.

**Never treat MT5's `time` field as UTC.** It is the BROKER SERVER's local time, and it arrives as a
plain epoch int with nothing to mark it. `get_candles` converts through `broker_clock.py`
(measured offsets, not assumed). Before the fix on 2026-07-30 every bar was 2–3 hours out behind a
perfectly valid-looking timestamp — which moves every session boundary a strategy trades off, with
no error anywhere. Verify a new broker with `compare_feeds.py`; do not assume the offset.

---

## Commit Discipline

- Docs update in the same commit as the code change that required them.
- Commit message: describe the *why*, not just the what.
- Never commit credentials, `.env` files, or `users.json`.
