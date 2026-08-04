# CLAUDE.md — LWG Capital Algo Trading Suite

**Purpose:** Standing instructions for the XAUUSD/forex MT5 bot suite running on the Windows VPS.
**Scope:** This covers the bots, shared utilities, risk rules, scheduler, and deploy for `algos/`. It does NOT cover `command-center/`, `smart-money/`, or `engines/regime/` internals (regime is imported via the `shared_regime.py` shim).
**Status:** Active — no live bots yet; all four first-attempt bots were deleted 2026-06-22 to rebuild backtest-first. Deployment plumbing preserved, and the live-trading pipeline for the first Python strategy is now being built (`docs/LIVE_TRADING_PIPELINE.md`).
**Last reviewed:** 2026-08-04 — 🔴 **THE TELEGRAM BOT WAS NEVER CRASHING. IT WAS BEING KILLED, AND ONE OF THE KILLERS WAS OUR OWN STARTUP SEQUENCE.** Aaron had watched it stop and come back for weeks and asked why. ✅ **Measured, not guessed: 4,764 Windows Application events over 14 days, none mentioning python, and no crash event (1000/1001/1026) since 26 July.** A `taskkill /f` leaves no event behind and a real fault does, so every "stop" was an external kill. Four kill paths, three fixed the day before without anyone realising they answered this question: the Telegram bot's own `/emergency` ran `taskkill /f /im python.exe` and **killed itself** (which is also why its confirmation reply never arrived), the command center's Stop button did the same, and three docs instructed the blanket kill by hand. **The fourth was the routine one and it was BY DESIGN:** `startup_coordinator.py` ended by launching `start_telegram.py` unconditionally, and that script's first act is `kill_existing()` — force-kill any running telegram_bot.py, sleep 2, start fresh. So **every Start/Restart from the Bots page, and every documented bot restart, killed the alert channel and rebuilt it**, after which SYS_MONITOR spotted the gap and sent 🟢 *Telegram Bot Restarted*. Fixed: `start_telegram_if_needed()` leaves a healthy Telegram alone. ⚠ **`SYS_TELEGRAM` deliberately KEEPS the force-restart** — that task exists to recover a bot that is alive but WEDGED, and it is what the watchdog fires (×3) when Telegram is genuinely down; the skip is about collateral damage from starting something else, and a test pins that `kill_existing` survives. ⚠ **An unreadable process list starts one rather than assuming it is up** — the safe direction is not symmetric: a second Telegram is refused by `telegram_bot.py`'s own singleton guard, a missing one is silence. ⚠ **The tests exec the launcher's real functions out of its AST** rather than importing it, because `startup_coordinator.py` hardcodes `C:/trading/algos` at module scope — the same trick `_coordinator_sequence` already used, so the check runs on the Mac where the mistake is actually made. 4 new tests, 202 algos tests green. **The standing lesson: an alert channel that cries wolf stops being read, so a routine event dressed as a failure costs exactly as much trust as a missed one — and "why does this keep restarting" deserves a measurement, not a shrug.** ⚠ **One blanket kill is still on disk on purpose**: `command-center/backend/tests/test_integration.py` runs `taskkill /f /im python.exe` on the VPS. It is excluded from every normal test run and documented in three places, but a bare `pytest tests/` still takes out the box. Earlier the same day: 🔴 **METATRADER RESTARTED ITSELF UNDER THE LIVE BOT AND THE BOT WENT BLIND FOR 50 MINUTES WITHOUT ONE INDICATOR CHANGING.** `C:\MT5_FFT\terminal64.exe` was rewritten at 02:57:53 UTC by an auto-update and the replacement process started two seconds later, taking the running bot's IPC handle with it. From the 02:30 bar onward it saw no market at all — across an open session, in which it would have taken no entry and managed no exit. ✅ **Proven rather than inferred: a separate read-only probe attached to the same terminal and got balance $2,000, live ticks at 4056.77 and fresh M15 bars, while the bot's own process was getting `None` from every call.** The terminal was healthy; only the bot's link was dead. 🔴 **The reason nothing caught it is the transferable part, and it is NOT this repo's usual label-vs-code refrain: every failure on the MT5 path returns an ABSENCE rather than raising.** `copy_rates_from_pos` → None → `get_candles` returns an empty frame (documented "never None", which is right for its callers and fatal here) → `BarFeed.new_bars` reads *no bar has closed* and `gap_bars` reads *no gap*; `account_info` → None → the heartbeat wrote a null balance. So the loop kept stamping, **SYS_MONITOR saw a healthy bot**, `wmic` still listed the process, the **Bots page said RUNNING**, and the log carried not one warning. **The only visible symptom in the entire system was a blank balance cell** — which is how it was found, by Aaron asking why. **Fixed:** `runner.probe_link()` asks `account_info()` FIRST, every poll; `_recover_link()` logs, alerts ONCE, retries on a 30s floor, and on reconnect **RE-WARMS** — an outage is a hole in the bar stream, i.e. the `gap_bars() > 4` condition arriving by another route, and resuming on the next bar would leave the engines carrying a market history that never happened. ⚠ **A bar-based probe cannot do this job and would have looked reasonable**: an empty frame is also what a QUIET MARKET produces, so such a check either cries wolf out of hours or treats a dead link as a quiet market forever — which is exactly how it shipped. `account_info()` answers whenever the link is alive, 3am Sunday or mid-session, so `None` means one thing. ⚠ **It deliberately does not reason about an open position** — if the broker holds one the rebuilt emulator does not, `OrderBridge._agrees` HALTS on the next bar, which is correct and already built; a second, less-tested answer to that question is how a restart doubles a book. ⚠ **`bot_state.json` gained `mt5_link` because a null balance is not a diagnosis**, and the Bots page renders it as a `No MT5 link` chip BESIDE the Running pill rather than replacing it: the process being ALIVE and being BLIND are both true and are different facts (alive ⇒ a restart is the fix and the watchdog was right not to fire). ⚠ **The heartbeat is still stamped while blind, on purpose** — dropping it would fire the stall alert, which means something else entirely. 12 new tests (`algos/tests/test_mt5_link.py`), 198 algos tests green; deployed and verified live (`mt5_link: true`, balance $2,000, bars current). **The standing lesson: before trusting a probe, ask whether a HEALTHY system can produce its negative result. If it can, it is not a probe.** Every layer here was individually defensible; the defect was that "no data" and "cannot ask" were the same value at every hop, so the distinction was destroyed at the bottom and unrecoverable above it. ⚠ **Still open and this incident is the argument for it: there is NO external dead-man's switch.** Every alert in the suite originates ON the VPS, so if the box or its network dies, silence is indistinguishable from health. Earlier: 2026-08-02 — **no algos code changed; two cross-subsystem facts were recorded.** The MT5 agent's **`/status` is now a CONSUMED CONTRACT** — the command center reads `mt5_connected`/`account`/`server` from it to drive its MT5 health dot, because `/health` answers `ok` while the terminal is closed or logged out — and **both `MT5AgentRDP` and `NT8Agent` are now fired automatically** by a 60s supervisor loop on the Mac, which also re-probes after every `schtasks /run` (that command reports SUCCESS for a task Windows refuses to launch — the stored-password trap below). Both are written up under *Backtest data source*. Earlier: 2026-07-30 — **`algos/live/` landed: the live runtime for a `strategies/python/` bot on a named MT5 terminal** (see the section below and `docs/LIVE_TRADING_PIPELINE.md`), and `shared/mt5_ops.py` gained what it needs to drive one — pending/resting LIMIT orders (it could only send market orders, and the MPC strategies enter on a limit) plus the broker-clock fix on `get_candles`, which was labelling broker-server seconds as UTC and would have put every bar 2-3 hours out with a perfectly valid-looking timestamp. Also **credentials moved out of git.** The Telegram token was pasted into six files and committed; it has been revoked, and every copy is replaced by `shared/credentials.py`, which resolves env var → the git-ignored `algos/credentials.json` → empty. `credentials.template.json` (in git, values blank) is the setup path. Missing credentials are a no-op with one warning, never an exception. This is step 2 of `docs/LIVE_TRADING_PIPELINE.md`, the plan to take a validated `strategies/python/` bot to real orders on a named MT5 terminal — read it before touching anything under `bots/`, `shared/` or `notifications/`, because the pieces preserved from the deleted suite are about to get their first real consumer.

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

**DELETED 2026-07-31 (Aaron's call), superseding the 2026-07-06 "deliberately parked" note:**
`shared_ai_brain.py`, `shared_calmar.py`, `shared_risk.py` and `shared_scanner.py` are gone. They
had no importers for five weeks and were keeping a design alive that no longer exists. **What each
one did, and the one command to restore it, is in [`docs/DELETED_CODE.md`](docs/DELETED_CODE.md) —
commit `e92304a`.** Read that before rebuilding any of it from scratch; `shared_risk.py` in
particular is the closest thing in this repo to the account-level allocator that is still unbuilt.

`shared_regime.py` and `structure_engine.py` survive: they are shims over the canonical `engines/`,
unused today only because `algos/live/` reaches the engines through `backtest/replay`. Deleting
them is an architecture decision, not a cleanup.

| File | Location | Role |
|------|----------|------|
| `shared_regime.py` | `shared/` | Market regime classifier shim: 5 labels (TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY). Each bot owns its own REGIME_RISK_TABLE. |
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
| `runner.py` | The loop — connect, verify the version pin, warm the engines, **probe the terminal link**, poll for a CLOSED bar, step, reconcile, heartbeat. `--dry-run` is the default; `--live` must be typed. The link probe is first on every pass and is `account_info()`, never a bar read — see the 2026-08-04 entry above. |
| `bridge.py` | Strategy intent ⇄ MT5 orders. Places/moves/cancels the resting limit, ratchets the stop, reports fills, and **HALTS when the emulator and the broker disagree** rather than continuing on a fiction. |
| `feed.py` | MT5 rates → the canonical replay frame. Never hands over the forming bar; reports how far behind it is so a gap re-warms instead of resuming. |
| `ledger.py` | Append-only JSONL: one record per bar, per blocked/missed setup, per trade open/close. This is what makes "why did this not work" answerable later. |
| `live_config.py` | One bot's instance config — which terminal, which account, which symbol, which version. Named `live_config` because bare `config` shadows the backend's. |
| `version.py` | The content pin. Re-hashes the strategy package at startup and refuses to run code that was never promoted. |

Two rules this package is built around, both in `docs/LIVE_TRADING_PIPELINE.md`:
**the strategy is authoritative and the bridge only mirrors** (that is what preserves Pine parity),
and **version isolation is two mechanisms** — params frozen in the instance config so lab edits
cannot reach a live bot, plus a source-hash pin the bot refuses to start against on mismatch.

🔴 **THE TERMINAL CAN RESTART UNDERNEATH A RUNNING BOT, AND UNTIL 2026-08-04 NOTHING NOTICED.**
MetaTrader auto-updates itself: on that date `C:\MT5_FFT\terminal64.exe` was rewritten at 02:57:53
and the replacement process started two seconds later, taking the running bot's IPC handle with it.
The bot then sat **50 minutes across an open session having seen no bars**, and every indicator in
the suite said it was fine — because **each failure on the MT5 path returns an ABSENCE, not an
error**. `copy_rates_from_pos` → None → `get_candles` returns an empty frame (documented "never
None", correct for its callers and fatal here) → `BarFeed.new_bars` reads *no bar has closed* and
`gap_bars` reads *no gap*; `account_info` → None → a null balance. The loop kept stamping its
heartbeat, so **SYS_MONITOR saw a healthy bot**, `wmic` still listed the process, so the **Bots page
said RUNNING**, and the log carried no warning. The only visible symptom in the entire system was a
**blank balance cell** on a page nobody had reason to distrust.

`runner.probe_link()` now asks `account_info()` FIRST, every poll, and `_recover_link()` reconnects
and **re-warms** (an outage is a hole in the bar stream — the `gap_bars() > 4` condition arriving by
another route). ⚠ **A bar-based probe cannot do this job**: an empty frame is also what a quiet
market produces, so such a check either cries wolf out of hours or treats a dead link as a quiet
market forever, which is exactly how it shipped. ⚠ **`bot_state.json` carries `mt5_link`** because a
null balance is not a diagnosis; the Bots page renders it beside the Running pill, since the process
being ALIVE and being BLIND are both true and are different facts. ⚠ **The heartbeat is still
stamped while blind, on purpose** — the bot IS alive, and dropping the stamp would fire the watchdog's
stall alert, which means something else and would restart a process whose problem is not the process.
Tests: `algos/tests/test_mt5_link.py` (12). **The transferable rule: before trusting a probe, ask
whether a healthy system can produce its negative result — if it can, it is not a probe.**

**Everything account-, machine- and version-specific is in the instance config, never in code
and never global.** Which terminal, which account, which server, which symbol, which magic
number, which strategy version, which broker clock — and **where this bot reports**. Two bots on
two accounts are two different conversations, so `telegram_chat_id` routes a bot's messages to
its own group and `telegram_token_key` lets it send as its own Telegram bot. The key NAMES an
entry in `algos/credentials.json`; the token itself never enters an instance config. Both empty
= the shared default, so a one-bot setup needs neither.

**Runtime config reload (added 2026-07-31).** `exec_risk_pct` can be changed under a RUNNING bot
from the command center: it rewrites the instance config, pushes, the VPS pulls, and the bot
notices its own file changed (`runner._maybe_reload_runtime`). Three rules, each guarding a
specific failure:

1. **Only `live_config.RUNTIME_RELOADABLE` is applied.** If anything else moved — a strategy param,
   the account, the symbol, the version pin — the change is REFUSED, left on disk, logged and
   Telegrammed. That is the case where a `git pull` carrying unrelated strategy edits reaches a
   running bot, and absorbing it silently is exactly what the source-hash pin exists to prevent.
   A restart is required, so the pin is re-checked and the engines re-warm on the code that is
   actually there. A refused change is reported ONCE, not every poll.
2. **Applied only while FLAT** — no position AND nothing resting (`bridge.is_flat`) — by
   **REBUILDING the strategy and re-warming** (~3s for 5,000 bars, measured), the same path a bar
   gap already takes. It rebuilds rather than assigns because `SosFadeConfig` is a **frozen**
   dataclass and ONE instance is shared by signals, sequence, execution and the secondary arm: there
   is no attribute to set, and reaching past `frozen` would let four components disagree about their
   own settings. That is what makes flat load-bearing rather than tidy — a rebuild discards the
   emulator's position state. A pending change is NOT consumed: it waits, and lands the moment the
   bot goes flat.
3. **The ledger records `risk_pct` per trade**, read off the strategy live rather than cached, so
   "why was trade 14 at 0.05 lots and trade 15 at 0.02" stays answerable.

`RUNTIME_RELOADABLE` is **mirrored** in `command-center/backend/services/bot_params.py`
(`RUNTIME_EDITABLE`) — the subsystems may not import each other, so the command center pins the two
sets equal with a test that reads `live_config.py` as text. Drift is silent and one-directional-bad:
the UI offers an edit, the push and pull both succeed, and the bot ignores the value forever.
**Change one, change both.**

Tests: `algos/tests/` — **104, all offline against a faked terminal**, so `pytest algos/` runs on
the Mac with no MT5 and no VPS. 60 cover this package, 16 cover the pending-order layer in
`shared/mt5_ops.py`, 13 cover credential resolution and Telegram routing, 15 cover the reload above.

**Offline green is not the same as "it runs".** The first real startup on the VPS
(2026-07-31, dry run, full connect → pin → warm → bridge) found three things a fully green suite
had not, and all three would have stopped the bot dead:

1. **The version pin could never match.** The hash was over raw bytes, and the VPS has
   `core.autocrlf = true` — git rewrites every newline on checkout, so one commit hashed
   differently on the two machines. The bot would have refused to start every time, on correct
   code. Newlines are now normalised in `live/version.py` **and** in the lab's scanner; they must
   stay in step. A guard that always fires is a guard that gets switched off.
2. **`LiveRunner` could not be constructed at all** — `_make_logger` imported `bot_utils`, which
   was not on the path it built. Every test covered a PIECE (bridge, feed, ledger, pin); nothing
   built the object that wires them together. `test_live_runner_startup.py` now does.
3. **The log silently dropped lines.** A Windows console is cp1252 and cannot encode the arrows
   and em-dashes these messages use; `logging` discards the record and prints a
   UnicodeEncodeError in its place. Both streams are forced to UTF-8 now — the log is the audit
   trail, so an unencodable character costs a glyph, never the line.

The standing lesson: **run it on the VPS before believing it works.** These were found in one
five-minute dry run.

**2026-07-31, second dry run — the lesson repeated, and this time the tests were the problem.**
Registering the bot and adding the runtime reload found three more, all invisible to a green suite:

4. **`bot_state.set_started()` would have killed the bot on startup.** Its registries were empty and
   the lookup is unguarded, so the bot connected, warmed 5,000 bars and died on a bare `KeyError`.
5. **`Execution` had no public `cfg`.** `algos/live/` reached for `.cfg` in two places: the reload
   crashed the loop, and the ledger's per-trade `risk_pct` silently recorded `None` through a
   defensive `getattr`. **Every reload test passed because every one used a stand-in that HAD a
   `.cfg`.** A test double that is more capable than the real object tests nothing. There is now one
   test that builds the REAL strategy.
6. **The config is frozen**, so the reload could not have assigned to it even with the accessor —
   which is how the rebuild-instead-of-mutate design was found.

A fourth, in the command center rather than here: the batched snapshot's section markers merged
whenever a state file had CONTENT (`type` emits no trailing newline), so a running bot reported
nothing about itself with no error anywhere. That one could not appear until a bot had run once.

**And the diagnosis gap that made all of this slower than it needed to be:** the coordinator's
single-bot launch sent stdout/stderr to `DEVNULL`. A failure before the bot's own logger exists had
nowhere to go — "launched", no log, no process. It now writes `<bot_key>_boot.log` beside the config.

One test hashes a strategy package with both `version.py` and the lab's scanner and requires the
same answer — a pin that disagrees with the lab is worse than no pin.

The root `conftest.py` has to `collect_ignore` `algos/nt8/test_bt_switch.py`: it is a VPS debug
script, not a test, and it calls `sys.exit(1)` at IMPORT when pywinauto is missing, which crashes
collection for the whole repo rather than failing one file.

Standalone MT5 lab tooling (not imported by any bot) lives in `tools/`: `download_mt5_history.py` (warm the lab MT5 history cache) and `audit_mt5_data_quality.py` (its read-only companion — probes what the broker actually serves). Both run on the VPS against `C:\MT5_Lab`.

**Backtest data source — pinned to MT5_Lab only (2026-07-22).** All backtest price/tick data comes from the MT5 agent (`markets/fx/tools/mt5_agent.py`, VPS port 8766). Its `_ensure_mt5()` binds the Python API to the **MT5_Lab** terminal64.exe *only* (`TERMINAL_PATH` / `MT5_DATA_DIR`, else the baked-in `C:\MT5_Lab` default); if a live bot terminal (MT5_FFT, etc.) is already attached it drops and re-binds, and if MT5_Lab can't be reached it FAILS loudly rather than silently reading the wrong account. This closed a real leak — the old code called `mt5.initialize()` with no path and grabbed whichever terminal answered first. **MT5_Lab is logged into a Vantage demo (account 25815745, `VantageMarkets-Demo`)** so backtest data matches TradingView's `VANTAGE_XAUUSD`; this replaced the earlier PU Prime `XAUUSD.s` feed. Vantage's gold symbol name/suffix may differ from `XAUUSD.s` — if a run returns no bars, check the symbol name first. To pick up an agent-code change: `git pull` on the VPS **and** restart the `MT5AgentRDP` scheduled task (kill only the specific `mt5_agent.py` PID) — never a blanket `taskkill python.exe`, which also kills the NT8 backtest agent (`NT8Agent` task).

⚠ **`/status` IS A CONSUMED CONTRACT AS OF 2026-08-02, not just a debug endpoint.** The command center's health strip reads `mt5_connected` / `account` / `server` from it to drive the MT5 dot's yellow state, because `/health` only proves Flask is alive — it answers `ok` while the terminal is closed or logged out, which showed a green dot over a disconnected MT5_Lab while every backtest needing uncached bars failed at fetch time. Renaming or dropping those three keys silently returns that dot to lying. Consumers: `command-center/backend/services/mt5_agent_client.status()` → `agent_supervisor.mt5_terminal_status()`.

⚠ **BOTH AGENT TASKS ARE NOW FIRED AUTOMATICALLY.** `command-center/backend/services/agent_supervisor.py` runs a 60s loop on Aaron's Mac that rebuilds the SSH tunnel and fires `MT5AgentRDP` / `NT8Agent` for whichever agent is not answering. Two consequences for VPS work: **(1)** killing an agent by hand to pick up a code change may see it restarted within a minute — stop the command-center backend first if you need it to stay down; **(2)** the loop **re-probes after every `schtasks /run`**, because that command reports SUCCESS for a task Windows refuses to launch (the stored-password trap below), so an agent that will not start is now reported rather than assumed healthy. It deliberately will **not** restart an agent whose lab job is still marked `running` — from the Mac, "dead" and "too loaded to answer `/health`" are indistinguishable, and the NT8 agent genuinely stops answering while driving a backtest under pywinauto.

Multi-instrument architecture (Phases 1–5) explained in `docs/ARCHITECTURE.md`.

### Risk Rules Summary

n/a — no live bots.

### AI Thresholds

n/a — no live bots.

### What I Am Working On

✅ **THE DEPLOYED CODE SNAPSHOT LANDED 2026-08-04** (`88305b8`). This section described it as in
flight with three red tests; both are now history, and the tests were fixed to the new contract
rather than the contract reverted.

**What it does:** a promoted bot imports from `instances/<bot>/deployed/`, never the repo working
tree, so a `git pull` or a lab edit cannot reach it. **Proven live: three commits were pulled onto
the VPS under a running bot and it kept its version, its PID and its hash.** Before this, `git pull`
rewrote the code under a live bot and the version pin then refused to restart it — backtesting a new
version could brick the deployed one. Aaron's rule, now enforced: a bot runs what you last DEPLOYED
until you deploy something else.

⚠ **The pin covers THREE trees, not one** — `strategies/python/<pkg>`, `engines/` and `backtest/`.
Hashing only the strategy package left the other two free to move under a GREEN pin, so the bot
would start, report the version it was promoted at, and trade different logic. Same shape as the
phantom-exit bug: a guard that looks fine while the thing beneath it moved. `verify_pin` therefore
takes a LIST of roots — do not "fix" it back to one.

**Promoting is `algos/tools/promote.py`** (stage → verify in a clean subprocess → activate, so a
failed promote leaves the running bot untouched) or the **Promote button on the Bots page →
Configure**, which previews before it deploys. `instances/*/deployed/` and `deployed.json` are
git-ignored: they are a per-machine build artefact, reproducible from `promoted_commit`, and
promoting happens ON the VPS, so committing them would collide with the next pull.

⚠ **The freeze covers the STRATEGY, not `algos/live/`.** The runner itself is repo code loaded at
process start, so a runner fix reaches a bot on `git pull` + restart with no promote — which is
correct (it is plumbing, not trading logic) and worth knowing when you change one.

**Phase:** No live bots. All four first-attempt bots were deleted 2026-06-22. The suite is being rebuilt backtest-first per the S.Y.S.T.E.M. method (`docs/BOT_DEVELOPMENT_METHOD.md`) — strategies are validated through the command-center backtest lab before any return to live demo trading. The reusable deployment infrastructure is preserved in `docs/BOT_DEPLOYMENT_INFRA.md`.

### CLEAN SLATE — 2026-07-31. Read this before trusting anything older.

**Aaron's decision: the suite starts from scratch today. Nothing from before this date carries
forward, and nothing is expected to still be on disk.** Both the VPS and the repo were leaned out:

- **Deleted from the repo:** the four dead `shared_*` modules — commit **`e92304a`**, documented in
  [`docs/DELETED_CODE.md`](docs/DELETED_CODE.md).
- **Deleted from the VPS:** `C:\algos` (a 36 MB pre-migration copy of the whole old suite, including
  the dead bots' instance state), `C:\algos-backup`, every stale task XML and log in `C:\temp`,
  `C:\tmp`, the root probe scripts, the orphaned `C:\trading\regime`, scratch files
  (`dump_opt.json`, `filetest`, `smoke_out.txt`, dead zero-byte agent logs, a `.vpslocal.bak`), old
  bot state (`monitor_state.json`, `stop_suppress.json`), stale Telegram runtime state, and every
  `__pycache__`. `git status` on the VPS is clean.

**The consequences, stated plainly so nobody re-derives them:**

1. **There is no historical trade data on the VPS.** No old ledgers, no `bot_state.json` from a
   previous bot, no equity logs. The first live ledger entry will be the first real one.
2. **A file's absence is not a bug.** If something references a path that is not there, the answer is
   that it was deleted on purpose — check git history and `DELETED_CODE.md` before recreating it.
3. **To recover anything, use the commit hash.** Do not rewrite deleted code from memory or from a
   docstring; `git show <commit>^:<path>` gives you the real thing.
4. **What was deliberately KEPT:** all four MT5 terminal installs (`MT5_FFT`, `MT5_Lab`,
   `MT5_Scalper`, and the Program Files instances) — Aaron may attach new bots to them;
   `start_mt5_agent.bat` (`MT5AgentRDP` runs it); `credentials.json` and `users.json`; and the
   `C:\temp` directory itself, which `bootstrap_vps.ps1` uses as its staging dir.
5. **Only the Telegram bot is maintained from the original suite**, and only for trade ENTRY and
   EXIT alerts. Crash alerts, P&L tracking and the daily reporter are fixed but disabled — see
   *On hold* below.

### Scheduled tasks — the stored-password trap (found 2026-07-31)

**Every `SYS_*` task on the VPS had been silently dead since 30 May.** They were registered with
`LogonType: Password` against the machine's Administrator SID, the provider rotates that password
(there is a `CheckAndPromptPasswordChange` task on the box), and once it changed Windows refused to
launch them. The symptom is the nasty part: **`schtasks /run` still reports SUCCESS** and the task
still shows `Ready` — only `Last Run Time` gives it away by never advancing.

`MT5AgentRDP` and `NT8Agent` kept working because they use `InteractiveToken` (the logged-in desktop
session), which is why the platform looked healthy while its whole scheduled layer was off.

What that cost: crash alerts were off for two months, and **`SYS_STARTUP` would not have restarted
anything after a reboot.**

All are now running as **SYSTEM** — no password to go stale, and it survives the next rotation.
`algos/scheduler/*.xml` were rewritten to match, because they also hardcoded this machine's SID and
would have re-created dead tasks on any rebuild or new VPS.

**Standing rule: a scheduled task that must run unattended runs as SYSTEM.** Never register one with
a stored password, and never trust `schtasks /run`'s exit code — verify `Last Run Time` moved.

**Follow-on, same day: the XMLs could not be registered at all.** Every file in
`algos/scheduler/` carried `<LogonType>ServiceAccount</LogonType>`, which this Windows build
rejects for `S-1-5-18` — `schtasks /create /xml` fails with *"incorrectly formatted or out of
range"* naming LogonType. A working SYSTEM principal on this box is `UserId` + `RunLevel` and **no
`LogonType` element**; `schtasks /query /tn <name> /xml` on a live task is the way to see the shape
Windows actually accepted. `bootstrap_vps.ps1` installs every task through that same call and only
`Write-Warn2`s per failure, so **a rebuild would have created no tasks and still reported success.**
All six XMLs are fixed and each was test-imported under a throwaway name. If you add a task, import
it before you trust it — and delete the throwaway immediately, because a stray copy of
`telegram_task.xml` or `startup_coordinator_task.xml` starts a SECOND bot.

**Two things a task cannot do, both found by running it as SYSTEM:**

- **It cannot `git push`.** SYSTEM has its own credential store, Git Credential Manager has no token
  there and no session to prompt in, so the push **blocks** rather than failing — the task sits in
  `Running` with no output until its execution limit kills it. This is why the ledger is pulled by
  the Mac (`algos/tools/ledger_sync.py`) instead of pushed by the VPS. Do not "fix" it by putting a
  GitHub token on this box: it already holds a live MT5 password and a Telegram token.
- **It has no console.** `timeout /t` and anything else wanting a console fails under a task and
  over SSH alike.

### Live tasks, and the two still on hold

**`SYS_MONITOR` is ON as of 2026-07-31** (Aaron's call — a dry-run bot nobody is watching is the
thing this layer exists to prevent). It runs every minute as SYSTEM and alerts on: bot gone, bot
back, **loop stalled**, Telegram bot down (auto-restart ×3, then a critical alert).

⚠ **The stalled-loop half had never been able to fire, and that is worth knowing before trusting
any watchdog here.** `monitor.py` reads a `heartbeat` timestamp from `bot_state.json`; nothing
wrote one, and the check read the missing key as `0` and then asked `0 > 300`. So it was
permanently false rather than obviously broken — and a frozen bot still answers `wmic`, so it
reads RUNNING on the Bots page, in Telegram and in the task list. `runner._heartbeat()` now stamps
it every loop (with the balance read moved OUT of that try block, so a broker hiccup cannot swallow
the stamp), and the monitor falls back to `started` when no stamp exists. `algos/tests/test_watchdog.py`
pins both halves plus three launcher↔watchdog agreement tests. **A watchdog whose failure mode is
silence is worse than none — the empty alert channel reads as good news.**

**`SYS_LOGBACKUP` is ON as of 2026-07-31.** Daily 00:30 UTC (the VPS clock is UTC), runs
`tools/log_backup.py`: zips the instance `.log` files into `algos/log_archive/`, prunes past 90
days, reports closed ledger days. **It does no git** — see the SYSTEM-cannot-push note above. The
ledger reaches the repo when `algos/tools/ledger_sync.py` is run **on the Mac**, which means the
decision record is on one disk until someone runs it. Logs are COPIED, never rotated: the bot holds
its log open and renaming an open file on Windows fails.

Still deliberately **disabled**:

| Task | Script | Why it waits |
|---|---|---|
| `SYS_PNLTRACKER` | `notifications/pnl_tracker.py` | Its bot registry is still empty |
| `SYS_REPORTER` | `notifications/reporter.py` | Daily report at 21:00 — would send an empty one |

Re-enable with `schtasks /change /tn <NAME> /enable`. The Bots page renders a disabled task as
**DISABLED**, not "scheduled — waiting for next trigger", so an off watchdog stops reading as a
covered one.

### Registering a bot — the four registries, and the crash if you miss one

**2026-07-31: `mpc_sos_fade_demo` is registered.** It is the first bot in the rebuilt suite. Four
registries had to be filled and they are not optional — `bot_state.set_started()` does
`BOT_ACCOUNTS[key]` unguarded and `algos/live/runner.py` calls it at the top of its loop, so a bot
missing from ONE of them connects to MT5, warms 5,000 bars, and then dies on a bare `KeyError`:

| File | What it registers |
|---|---|
| `shared/bot_state.py` | `BOT_INSTANCES` / `BOT_ACCOUNTS` / `BOT_NAMES` — the state file, account, display name |
| `bots/startup_coordinator.py` | `STARTUP_SEQUENCE` — how it boots, and the log line that means "connected" |
| `notifications/monitor.py` | `BOTS` — liveness watch (inert while SYS_MONITOR is disabled) |
| `command-center/backend/routers/bots.py` | Six task/bot maps — how it appears on the Bots page |

Two things about that list. `STARTUP_SEQUENCE` entries carry a **full argv**, not a config path
(the deleted bots took `--config`, `algos/live/runner.py` takes `--bot`) and deliberately do **not**
pass `--live`, so a bot that boots with the VPS can never arm itself. And there is **no per-bot
`BOT_*` scheduled task** — boot goes SYS_STARTUP → coordinator, and the command center starts a bot
through that same coordinator over WMI. The command center's maps are keyed by a task name that
does not exist as a real task, which is harmless: the PROCESS LIST is authoritative there.

`bot_state.ALGOS_ROOT` is **derived from `__file__`**, not the literal `C:/trading/algos` it used to
be. The runner is dry-run-capable off the VPS, and a hardcoded Windows path made every state write
fail on a Mac while looking perfectly correct in the source.

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
