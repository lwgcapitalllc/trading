# CLAUDE.md — LWG Capital Algo Trading Suite

**Purpose:** Standing instructions for the XAUUSD/forex MT5 bot suite running on the Windows VPS.
**Scope:** This covers the bots, shared utilities, risk rules, scheduler, and deploy for `algos/`. It does NOT cover `command-center/`, `smart-money/`, or `engines/regime/` internals (regime is imported via the `shared_regime.py` shim).
**Status:** Active — **ONE BOT LIVE AND ARMED.** `sos_fade_demo` has run since 2026-07-31 and has placed real orders since 2026-08-05, on a PU Prime **ECN demo** account (700152905 / `XAUUSD.p` since 2026-08-12), under a 10% account-level risk cap. **`exec_sl_deep` was switched ON 2026-08-15 and takes effect on its next RESTART** — see below.

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

## `markets/fx/accounts.json` — the broker accounts a bot can be put on

**Added 2026-08-12, GIT-TRACKED, HOLDS NO SECRET.** One entry per broker account: its server, the
terminal on the VPS logged into it, the suffix it puts on a symbol, which measured cost profile
prices it, and demo-or-live.

🔴 **It exists because until this date an account only existed once some bot already named it.**
The command centre DERIVES which bots share an account from the instance configs — which is right,
and which means the first bot onto a NEW account had nothing to be assigned to. That is precisely
what made moving the live bot from the Standard demo to the ECN one a hand-edited config on this
box: not a missing feature, a derivation being asked a question it had no input for.

⚠ **The RISK CAP is deliberately not here.** It is an account-level number stored per instance
because an instance config is the only file a bot reads, so the account's cap is whatever its bots
state — and `live_config._assert_account_cap_agrees` refuses to start every bot on an account whose
caps disagree. A copy in this file would be a second answer able to drift from the bots actually
running.

⚠ **THE PASSWORD IS NOT HERE EITHER AND MUST NEVER BE.** It lives in `algos/credentials.json` under
`mt5_accounts`, keyed by the same account number, which is git-ignored and per machine —
`live_config.account_credentials` already read it that way, so nothing on the bot side changed.

⚠ **`symbol_suffix` is THREE states.** A string is the suffix, `""` means this broker quotes bare
symbols, and **`null` means nobody recorded it** — a bot moved onto such an account keeps the symbol
it had and the move SAYS so rather than guessing. That distinction is the whole reason the field
exists: a bot pointed at a symbol its terminal does not quote connects, warms up and receives no
bars, which reads exactly like a quiet market.

⚠ **`mt5_path: ""` means no terminal serves the account, and a bot cannot be assigned to it.** Not a
placeholder — the two tier-probe accounts (700119432 Standard, 700152904 Prime) were logged into
**MT5_Lab** for minutes at a time to read spreads and commission, and MT5_Lab drives the backtest
agent. A live bot must never be pointed at it.

⚠ **Edit it from the command centre (Bots → Accounts), not by hand.** A write from there validates
the cost profile against `backtest.fills.PROFILES`, refuses an account with no server, and commits,
pushes and pulls it. A hand edit is still fine and its `_`-prefixed prose keys survive a write from
the page.

## Fast Index

### The Bots

🔴 **This line said "there are currently no live bots" until 2026-09-11 — while two were trading real money.** The roster is the bot folders (`### Registering a bot` below), and which bot trades which account lives in each bot's instance config and on Bots → Accounts. **Count them with `box_status`, never from this file.** The four first-attempt bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 to rebuild the suite backtest-first.

New bots follow the S.Y.S.T.E.M. process in `docs/BOT_DEVELOPMENT_METHOD.md` (specify → backtest → stress test → live demo). The reusable deployment plumbing left behind by the deleted suite — the MT5 connection layer, per-instance configs, Task Scheduler wiring, and the liveness/notification layer — is documented in `docs/BOT_DEPLOYMENT_INFRA.md` so a validated strategy can be wired to live demo without rebuilding the infrastructure.

### Risk Rules Summary

n/a — no live bots.

### AI Thresholds

n/a — no live bots.

### Registering a bot — a bot IS its folder (2026-09-13)

**A bot is `markets/fx/instances/<key>/config.json`, and the folder is the whole registration.**
`shared/bot_registry.discover()` lists them; the state map, the boot order, the watchdog, the
dead-man's switch and the chat bot read that one list, and the Command Center lists the same folders
by the same rule (`routers/bots.py::_discover_bots` — the subsystems may not import each other).
🔴 **It was five hand-kept lists until this date, and every omission was silent and failed
differently** — a startup `KeyError` after warming, a bot absent after a reboot, a bot nothing
watched — while two comments claimed the lists agreed. **A list stated twice is two lists.**

- ⚠ **The folder name IS the key** (`^[a-z][a-z0-9_]{1,63}$`), and `live_config.load` refuses a
  config whose `bot_key` names another folder: a copy with the key left unchanged would write into
  the other bot's state, ledger and position record.
- ⚠ **A folder that cannot be listed RAISES (`RegistryUnreadable`), never an empty list** — no bots
  reads as nothing to watch (rule 1). The watchdog alerts once, the dead-man's switch reports it as
  a problem, the coordinator refuses to run, the Command Center answers 503.
- ⚠ **The boot order is derived: live-account bots first.** Argv is `runner.py --bot <key>` with
  **no `--live`**, so a bot booting with the VPS never arms itself. No per-bot `BOT_*` task exists.
- 🔴 **Which process IS a bot is one rule, `bot_registry.is_runner_line`**: a line running
  `runner.py` whose `--bot` value is exactly the key, ending at a space, a quote or the line end. So
  `sos_fade_2` is never `sos_fade_20`, and a deploy, a re-entry check or the coordinator carrying the
  key is never the bot. Every check on the box uses it; `tests/fixtures/runner_lines.json` holds the
  cases, and the Command Center's own copy of the rule is tested against the same file.
- 🔴 **The MT5 connect lock is per TERMINAL** (`shared/mt5_lock.py`, `mt5_connect_<terminal>.lock`).
  It was one lock for the box, so one account's hung terminal held every other account's connects
  for up to 90s. Bots on one terminal still take turns. The coordinator clears only STALE locks
  (older than 45s); the fleet stop clears all of them.
- ⚠ **The watchdog and the coordinator read the process list ONCE per pass, and an unreadable list is
  *cannot tell*, never *not running*** — the coordinator then leaves the bot and its recorded status
  alone, where it used to mark every bot stopped.
- ⚠ `tests/test_bot_bench.py` asserts every roster IS the folders, and that the Command Center keeps
  no hand list and types no real key.
- ✅ **A new bot's Telegram messages are NOT something anyone has to ask for (2026-09-22).** The
  fill, the stop reaching breakeven, the stop trailing, size banked, size added and the outcome all
  come from `live/bridge.py` — the one layer every bot's runner builds — and are classified from
  prices rather than from any strategy's own stages, so a bot written next year inherits the whole
  set with no wiring and no config key. Aaron: *"if I create a bot, I shouldn't have to go say, hey,
  create telegram messages for it. It should be part of how we do work."* Detail and the throttle:
  `notes/telegram-and-notifications.md`.

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

## Live-path rules rescued from the moved narrative (2026-08-12)

**These were BURIED in the diary that now lives in `algos/docs/ALGOS_BUILD_NOTES.md` — 91,060 bytes across seven paragraphs, the largest 36,137 bytes on ONE line.** They are live-trading safety rules, and a safety rule nobody can find is not a safety rule. Each one's evidence is in the notes.

- **A safety device must never make a trading decision.** The fleet kill switch stops NEW ORDERS across the box; it does not flatten a book, because flattening is a trade. Same reasoning bounds every future guard.
- **Cannot-read HALTS** — deliberately the opposite default from `stop.request` — **and it LATCHES.** Clearing the flag does not resume trading; the bots must be restarted. A terminal flipping between logins therefore cannot toggle a live book unattended.
- **`Path.exists()` cannot be used to read the halt flag, and using it is the trap** — it answers `False` for *no flag* and for *cannot read the disk*, collapsing the very distinction the halt exists to protect. Read it in a way that can tell the two apart.
- **A magic number is only ever compared WITHIN one account.** An unchanged magic across an account move is correct, not a bug.
- **A restored stop that DIFFERS from the recorded one is never adopted.** Restore is deliberately strictly narrower than the halt it replaces — that narrowness is the safety property, not a limitation to widen later.
- **Stops are compared against the symbol's POINT, never for exact equality.**
- **Two failures must never share one message.** The tool written to end guesswork had itself merged *the tick never arrived* with *the sampler could not ask* — this repo's own no-vs-cannot-ask rule, broken inside its own diagnostic.
- **`b_leg_demo` MUST NOT be assigned to an account yet**, and its config says so in `_NOT_VALIDATED`. See `docs/LIVE_TRADING_PIPELINE.md` → G15.
- **An unmeasured spread cannot pick an account.** Swap is identical across all three PU Prime tiers (measured on each), and the Prime↔ECN replay gap of 1.16R sits far inside this strategy's run-to-run sd of 15.06R. The ECN case is "strictly cheaper at identical everything else" — never a claim that the number moved.

---

## Shared MT5 Architecture — Non-Negotiable

All MT5 operations live in `shared/mt5_ops.py`. Bots never implement MT5 logic directly.

Full `BotMT5` method list, the thin-delegate pattern, and what stays bot-specific are documented in `docs/ARCHITECTURE.md`.

### When to update `shared/mt5_ops.py`

Any time you add or fix behaviour that applies to ALL bots. Do not add it to one bot and
leave the others with stale code. Fix the shared implementation, update the thin delegates
in every bot that uses it.

**`tools/mark_trade.py` — a trade that is STAYING but must not be counted (2026-08-26).**
Companion to `close_orphans.py`, which closes and marks; this one marks and leaves the trade
alone. ⚠ **It changes nothing about how the bot treats the trade** — the bot goes on managing it
normally, which is usually right: a trade that should not exist should still be exited properly.
It marks by TICKET, the one thing the ledger and the broker statement share.

## Commit Discipline

- Docs update in the same commit as the code change that required them.
- Commit message: describe the *why*, not just the what.
- Never commit credentials, `.env` files, or `users.json`.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 342 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### Deploying — the story lives in the ROOT `notes/deploying.md`

**Read before touching:** `tools/promote.py`, the snapshot pin, or anything that restarts a bot.
🔴 **Deliberately a POINTER, not a copy** — the deploy workflow is shared with the Command Center,
which drives the same tool, so its one account lives at the repo root. A second copy here is the
drift this repo has already paid for three times.

- 🔴 A deploy that would ship NOTHING now refuses and leaves the running bot alone (2026-09-23). It used to restart it anyway: `fft_1` was deployed twice in three minutes, the second run staged byte-identical code, and the restart cancelled the limit order the bot had placed ninety seconds earlier. Three things must agree before it refuses — the code against the RECORD, the code against WHAT IS ON DISK, and the PARAMETERS — and the commit is deliberately not one of them while the pin is still written. `--redeploy` forces it.

### `notes/order-execution.md` — Order execution — the bridge's entries, exits, banking and market orders

**Read before touching:** order placement, closing, banking or the bridge's MT5 call handling.

- 🔴 The bridge REFUSES `exec_scale_in` (2026-08-17)
- ✅ A trade can be CLOSED ON DEMAND (2026-09-02) — and the instruction goes to the STRATEGY
- 🔴 The bridge could not bank at a price, and only two of the six rungs were refused (2026-09-01)
- ✅ The bridge can BANK part of a position (2026-09-01) — and still cannot close the last of it
- 🔴 `partial_close` had never run once, and it CLAMPED UP to the broker minimum (2026-09-01)
- The live runner's SECOND bar feed — G18 stage 1 (2026-09-01). Stages 2-4 still open
- 🔴 The fill clock halted both SOS Fade bots on their OWN limit; the fix, re-adopt by replay, and the daily-break alert (2026-09-17)
- ✋ A hand close of the bot's own trade is booked as yours and the bot keeps trading; what a hand-moved stop does (2026-09-17)
- ✋ A stop you tighten at the broker is kept, a looser one halts; a trade vanishing beside another halts (2026-09-17)
- 🔴 A broker rejection is alerted once, and a temporary one (no connection, requote …) is re-sent within seconds rather than a bar later (2026-09-16)

### `notes/risk-sizing-and-halts.md` — Risk sizing, account budget and halts

**Read before touching:** risk sizing, the account risk cap, or the halt/promote safety guards.
Most-cited code: `tools/recovery_stack.py`, `shared/account_risk.py`, `shared/sizing_basis.py`, `tools/migrate_position_record.py`.

- 🔴 THE HALT DID NOT HOLD — a reconnect, a bar gap or a settings edit put a halted bot back to trading (2026-09-02)
- ⚠ Before splitting the 10% cap between two strategies — three live-side facts the lab cannot show you (2026-08-20)
- 🔴 A shrunk entry could never reach a broker; the pooled cap, the half-share minimum and the priority order — promote BEFORE pull (2026-09-15)

### `notes/account-anchor-scale-in-and-targets.md` — Account anchor, scale-in add path and the travelling target

**Read before touching:** the account anchor, scale-in / add-to-winner behaviour, or the live target/stop-travels-with-order path.
Most-cited code: `tools/audit_reentry.py`, `tools/watch_reentry.py`.

- 🔴 A RENAME orphans the account anchor, and the symptom is a confident 0.0% (2026-09-05)
- The target now travels WITH the order, the way the stop always has (2026-09-09)

### `notes/account-accounting-and-status.md` — Account accounting and status reporting

**Read before touching:** return/PnL accounting, the trade-permission check, or the heartbeat/status file.
Most-cited code: `shared/bot_state.py`, `live/position_state.py`, `shared/account_flows.py`.

- 🔴 A deposit is not a return — the return comes off the broker's deal history (2026-09-12)
- 🔴 Whether the account may TRADE is read every poll, and said once (2026-09-12)
- The heartbeat says what the bot holds at the broker, and why it halted (2026-09-12)
- 🔴 The status file is REPLACED, never emptied and refilled (2026-08-24)
- 🔴 What MT5 says at connect reaches the record before anything can refuse (2026-09-14)

### `notes/vps-tasks-and-ledger.md` — VPS scheduled tasks, ledger backup and the dead-man's switch

**Read before touching:** a scheduled task, the ledger sync, the watchdog, or the daily health record.
Most-cited code: `tools/ledger_sync.py`, `live/runner.py`, `tools/promote.py`, `tools/scan_terminals.py`, `tools/log_backup.py`, `live/ledger.py`.

- 🔴 The box backs up its OWN record — and it is the ONLY machine that may (2026-08-24/28)

### `notes/telegram-and-notifications.md` — Telegram rooms and notification format

**Read before touching:** Telegram notifications, alert formatting, or bot naming for messages.
Most-cited code: `live/setup_alerts.py`, `live/alerts.py`, `live/bridge.py`, `shared/notify.py`, `tools/signal_samples.py`, `tools/alert_rate.py`.

- 🔴 The live rooms — each ACCOUNT names its own channels; a live bot with none refuses to start (2026-09-13)
- ✅ The health room's icons collapsed from 14 ad hoc glyphs to 4 named severity levels; every example is in `notes/telegram-message-catalog.md` (2026-09-14)
- 🔴 A setup's Telegram thread did NOT survive a restart — four identical alerts for one setup in 24 hours, none of the first three closable. The thread bookkeeping now lives on disk and is reconciled at the end of every warm-up (2026-09-16)
- ✅ Setup messages are ON for every bot; the extreme-leg bot now sends them, and a bot whose strategy cannot says so in the health room (2026-09-16)
- ✅ A trade's thread now says how it is being MANAGED — breakeven, trail, tighten, size banked, size added — and EVERY bot gets it because the bridge sends it from prices, not from a strategy's stages. The trail is throttled to 0.5R of fresh profit per message; the breakeven crossing always sends. A restart keeps the thread and the 1R yardstick (2026-09-22)

### `notes/telegram-message-catalog.md` — Every Telegram message this suite can send, by room

**Read before touching:** wording or icons on any Telegram message, or before adding a new one.
Most-cited code: `shared/alert_format.py`, `live/alerts.py`, `live/runner.py`, `live/bridge.py`.

- Real, rendered examples of every message in the trades, signals and health rooms, grouped by
  the health room's four severity levels. Not executable — re-write an example by hand whenever
  its wording changes, or the catalog goes stale while looking current.

### `notes/bot-registries-and-lifecycle.md` — Bot registries and lifecycle

**Read before touching:** Adding, renaming, cloning or registering a bot.
Most-cited code: `tools/promote.py`.

- 🔴 The startup line names the commit the snapshot was PROMOTED from, or "unknown" — it printed the box repo's HEAD (2026-09-16)
- 🔴 The order-sending code (`live/`, `shared/`) is frozen into the snapshot and pinned; a restart cancels a resting order, so restart a live bot only when flat (2026-09-17)


### `notes/shared-and-live-runtime-reference.md` — Shared components and live runtime reference

**Read before touching:** Looking up what a shared module does or how the live runtime is put together.
Most-cited code: `bots/launcher.py`, `live/runner.py`, `notifications/telegram_bot.py`, `bots/startup_coordinator.py`, `shared/account_risk.py`, `shared/mt5_ops.py`.


### `notes/working-notes.md` — Working notes

**Read before touching:** Checking what was in progress at the time this was last touched.
