# CLAUDE.md — LWG Capital Algo Trading Suite

**Purpose:** Standing instructions for the XAUUSD/forex MT5 bot suite running on the Windows VPS.
**Scope:** This covers the bots, shared utilities, risk rules, scheduler, and deploy for `algos/`. It does NOT cover `command-center/`, `smart-money/`, or `engines/regime/` internals (regime is imported via the `shared_regime.py` shim).
**Status:** Active — **ONE BOT LIVE AND ARMED.** `mpc_sos_fade_demo` has run since 2026-07-31 and has placed real orders since 2026-08-05, on a PU Prime **ECN demo** account (700152905 / `XAUUSD.p` since 2026-08-12), under a 10% account-level risk cap. **`exec_sl_deep` was switched ON 2026-08-15 and takes effect on its next RESTART** — see below.

### `exec_sl_deep` ON (2026-08-15) — two rules, both live-path

🔴 **It COSTS 23R and is WORSE at matched drawdown — it is a deliberate trade of return for a
smaller ride, never an improvement.** +140.0R → **+117.0R**, max DD 5.61R → **4.73R** (45.6% →
41.1% at `exec_risk_pct` 10); re-levered to equal drawdown it returns 3,830x against 4,868x.
**Stated here because a reader meeting +117.0R against a +140.0R history otherwise reads a
regression.** Aaron's call, evidence and every warning in the `_exec_sl_deep` block of
`markets/fx/instances/mpc_sos_fade_demo/config.json`; the measurement is in
`docs/ALGOS_BUILD_NOTES.md` → *Which stop-outs a wider stop rescues*.

🔴 **A param change to a NON-reloadable field is REFUSED by the running bot, with a Telegram
message, and that refusal is the guard working.** `RUNTIME_RELOADABLE` is `{"exec_risk_pct"}`
alone, so the VPS `git pull` leaves this on disk and **the bot keeps trading the old rule until it
is RESTARTED.** ⚠ A param change needs **no `promote.py`** — the frozen snapshot covers code, and
the source-hash pin is re-checked on the restart regardless. `mpc_bleg_demo` is registered and **BENCHED** (`account: null`) pending a fresh `compare_bleg.py` parity run at its moved defaults. The four first-attempt bots were deleted 2026-06-22 to rebuild backtest-first; the pipeline that got the first Python strategy live is `docs/LIVE_TRADING_PIPELINE.md`.







This file is auto-loaded by Claude Code at the start of every session. Read it fully before touching any code.

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `algos/docs/ALGOS_BUILD_NOTES.md`. **Nothing was deleted.** It was 91,060 bytes in 7 paragraph(s), the largest 36,137 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

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

## 🔴 The bridge REFUSES `exec_scale_in` (2026-08-17)

`assert_supported()` gained a fourth refusal. **`OrderBridge` mirrors ONE entry limit and one
ratcheting stop — it has no path that places a second entry**, and `exec_scale_in` adds size to a
winning position. Left unrefused the bot would have traded the base position, placed no adds, and
reported nothing: the backtest would show a scaled book and the account an unscaled one, with
nothing explaining the gap. That is the exact divergence this function exists to prevent, and it is
why partial take-profits and the secondary are already refused.

✅ **Watched both ways rather than assumed** — scale-in ON is refused with a message naming the
cause, and the SHIPPED config still starts. A guard that refuses everything is not a guard.

⚠ **The refusal is not the whole fix and must not be read as one.** Making this live needs the add
path in the bridge AND the account-level allocator (`docs/LIVE_TRADING_PIPELINE.md` → G10): risk to
the shared stop is <= 0 by construction, but **margin sees the full stacked position**, and at the
shipped 4 adds x 2.0x cap that is several times the base size.



## ⚠ Before splitting the 10% cap between two strategies — three live-side facts the lab cannot show you (2026-08-20)

`backtest/tools/recovery_stack.py` now replays the loss-recovery rule as a LEG sharing this bot's
balance and its account budget. The measured sweep lives in
`strategies/python/loss_recovery/CLAUDE.md` and is not restated here. **What belongs here is that
adopting any such split is a LIVE change to an ARMED bot, and the live cap differs from the lab cap
in three ways that all push the same direction — live contention is MORE frequent and MORE
punishing than any stack backtest predicts.**

🔴 **1. The cap comparison here carries NO ROUNDING TOLERANCE.** `shared/account_risk.py`
(`check_account_cap`) tests the new order's risk against the remaining room on a bare `>`. **That is
the same defect shape found and fixed in `backtest/portfolio/account.py` on 2026-08-20**, where an
entry floor set equal to a leg's own risk rate refused **3,650 entries over 7.9 years** — because a
granted amount and a threshold were reached by different arithmetic (one side divides by the stop
distance to get a quantity, the other re-multiplies) and disagreed in the last bit. **A split
summing EXACTLY to the cap — 8% + 2% against a 10% cap — puts the second order on precisely that
edge.** ⚠ **Live it is strictly worse than the lab, and the lab CANNOT reproduce it**: the lab's
arithmetic is exact, while real open risk here is computed from the broker's ROUNDED lot size and
its actual stop, so an "8%" position is never 8.000%. Land the tolerance before adopting a split
that sums to the cap, or leave slack in the split.

⚠ **2. This side REFUSES; the lab side SHRINKS.** Refusing is correct (rule 17 — a resized order is
not the trade the strategy is holding) and it is not changing. But it means every lab cell reporting
*0 refused, 0 shrunk* is describing an allocator that WOULD have shrunk had it needed to. **The live
book of a split config is a SUBSET of the lab's book, never a rescaled copy of it**, so a lab result
does not transfer trade-for-trade.

⚠ **3. A RESTING order counts against this budget; the lab reserves at FILL.** A+ places a limit and
waits, sometimes for a long time. So live contention starts EARLIER and lasts LONGER than the
replay. **A stack backtest is a FLOOR on how often a split contends, never an estimate of it.**

⚠ **The starting point is also not what a split assumes.** `exec_risk_pct` is **10.0** in both
`config.json` and `deployed.json` today, so this bot's per-trade risk already equals the entire
account cap and there is no room to give a second strategy without lowering it first.
⚠ **`_account_risk_cap_pct` is NOT runtime-reloadable** — changing the cap needs a RESTART, so it
arrives through the promote / `stop.request` / `SYS_STARTUP` cycle rather than on its own.

## 🔴 The box backs up its OWN record now — the Mac no longer pushes (2026-08-24)

`SYS_LEDGERSYNC` runs `algos/tools/ledger_sync.py --local --alert-on-failure` **hourly at :20**.
The Mac's launchd agent still runs, with `--no-push`, as a second local copy.

**Why it changed.** The record left the box only when a Mac happened to be awake. Aaron, after a
weekend of records sitting on one disk: *"let the VPS go to work for me… so when I'm asleep,
things could run automated."*

**Why it could not before, and what actually fixed it.** The task runs as SYSTEM, whose credential
store has no cached token and no interactive session, so `git push` **BLOCKED** rather than failing.
Two changes, and the second is the one that matters:

  * a repo-scoped fine-grained token (`github_token`, git-ignored `algos/credentials.json`), spliced
    into the push URL **in memory** so it never reaches `.git/config`;
  * 🔴 **Git Credential Manager disabled outright** on every git call. **The token alone would NOT
    have fixed the hang.** MEASURED: with the helper live, even a SUCCESSFUL `ls-remote` printed
    *"Unable to persist credentials with the 'wincredman' credential store"* — it reaches for a
    store it cannot write, and under a session-less task that is what waits forever. Silent with it
    off.

⚠ **Exactly ONE machine may push.** Two timers on one branch rebase under each other. The box is
the one always on, so the box pushes and the Mac is `--no-push`. Do not "restore" the Mac's push.

🔴 **`_identity()` goes on the PUSH path as well as the commit — a rebase REPLAYS commits, so it
needs a committer too.** Missing there, the job committed hourly and pushed nothing for a night.
⚠ **It was invisible while the box was merely AHEAD of origin** (a fast-forward replays nothing)
and broke the instant the other machine pushed. **A branch only the rarer case reaches ships broken
and waits.**

⚠ **Reproduce a scheduled-task failure AS SYSTEM or you have not reproduced it.** The same call by
hand as Administrator succeeds — that account has a global git identity and SYSTEM has none. Every
failure this job has had was invisible to a hand-run.

⚠ **`git rev-list --count origin/main..HEAD` LIES ON THE BOX** — `_push` targets the authenticated
URL, not the remote NAME, and pushing to a URL never updates `refs/remotes/origin/main`. Compare
`rev-parse HEAD` against origin instead. The sync is unaffected; only the check is.

Story, measurements and the SYSTEM fixture: `HISTORY.md` → *The backup that committed all night*.

🔴 **It REFUSES to push when the working tree carries changes outside `algos/ledger_archive/`**
(`_foreign_changes`). `algos/tools/promote.py` freezes a live bot's snapshot out of that same
checkout, so a rebase underneath a half-finished deployment would change what is about to be
frozen. The commit stays local and the job says so. ⚠ **Untracked files do NOT count** — the box
permanently carries two, and counting them would mean the push never ran while looking installed.

⚠ **A failure sends a Telegram HEALTH message.** `--no-push` and `--dry-run` deliberately do NOT
alert: an alarm that fires when you asked for the thing is one people learn to ignore, and this
job's silence has already been mistaken for success twice.

⚠ **What it costs, and it was a deliberate trade:** that box already holds a live broker password,
and a repo write token beside it means a break-in costs the repository too. One repo, Contents
write, nothing else, is the whole of the limit.

⚠ **A rebuild does not restore the token** — it is git-ignored. The task then commits and never
pushes, with every green tick still green. Put it back as part of the rebuild.

🔴 **THE FIRST REAL RUN ON THE BOX COMMITTED NOTHING AND REPORTED "up to date".** `Path.relative_to`
returns the HOST's separator, so a path came out `algos\ledger_archive\...` while
`git status --porcelain` prints `algos/ledger_archive/...` — every membership test against git's
output missed, `pending()` returned empty, and the job printed *"up to date — all already
committed"*. Task result 0, exit 0, two modified record files still sitting in the working tree.
`_rel()` normalises to git's spelling everywhere. ⚠ **It could not happen on a Mac, and that is the
lesson: the code was correct for as long as it only ever ran on the machine that wrote it, and broke
the moment it moved to the box it was written to back up.** A path comparison is platform-specific
even when nothing about the logic is. ⚠ **This is the THIRD Windows-only defect to reach a scheduled
task through a green suite** — `%-I` in `strftime` and cp1252 console encoding were the other two —
so the standing rule above holds: **run it on the box.** ⚠ Its test asserts on a WINDOWS-SHAPED
string, because a real path on a Mac has no backslash and the assertion would pass without testing
anything.

🔴 **AND THE RUN AFTER THAT EXITED 1, FOR A SECOND REASON ONLY THE SYSTEM ACCOUNT HAS.** SYSTEM
does not share the interactive user's global git config, and this repo has no LOCAL identity — so
`git commit` refused with *"Please tell me who you are"*, **after** the files had been copied, which
leaves the working tree looking half-done. MEASURED with a throwaway SYSTEM task:
`git config --get user.email` returned nothing. **Running the identical command as Administrator
worked**, which is the shape that makes this hard to see — the hand-check passes and the unattended
run does not. `_identity()` supplies a fallback `LWG Trading Box <bot@lwgcapital.local>` per command.
⚠ **A machine, not a person**: these commits are made on a timer, and a history that says so beats
one borrowing somebody's name. ⚠ **Fallback ONLY** — a Mac keeps its own identity, or every manual
sync would be attributed to the box. ⚠ **Passed per-command, never written into `.git/config`**: that
checkout is what `promote.py` reads, and a write would silently re-attribute a human's commits made
from the same box.

**Tests:** `algos/tests/test_ledger_sync_local.py` (22), weighted toward what the job must REFUSE.
A fail-watch is vacuous (new functions), so non-vacuity is by MUTATION — dropping the archive
exemption and dropping the redaction each redden their own named test. 🔴 **One test caught a real
defect the live check had missed: the authenticated URL was missing its `@`, so it could never have
authenticated — and the check on the box only asserted the builder returned something.**

## 🔴 The status file is REPLACED, never emptied and refilled (2026-08-24)

`algos/shared/bot_state.py::_save_instance_state` writes a temp file and `os.replace`s it, the same
idiom `algos/live/position_state.py` uses. It was `open(path, "w")` until this date — which TRUNCATES
first — so any of the four readers landing in that window got an unparseable file.

**Measured cost.** 2026-08-22 03:50 UTC the dead-man's switch read it mid-write and sent `/fail`
saying *"bot_state.json cannot be read"*; it cleared on its next pass five minutes later. The bot
never missed a beat — `health-2026-08-22.jsonl` has pulses at 03:41 and 03:56, exactly on schedule.

⚠ **The false alarm was the SMALL half.** `_load_instance_state` swallows the parse error and returns
`{}`, so a `write_bot` landing there rebuilds the entry from defaults and saves — **wiping the other
bot's entry and this bot's own fields.** A reader that can only ever see a COMPLETE file cannot start
that chain, which is why the fix is at the writer rather than a retry in each reader.

⚠ **It does NOT make a read-modify-write atomic, and is not meant to.** Two writers can still lose a
field update; the loser is re-stamped within a poll. Benign. Reading a half-written file was not.

⚠ **The temp name carries the PID** — two processes sharing one scratch path is the same defect one
level down, where A's `os.replace` publishes B's half-written bytes.

⚠ **No trade was ever at risk and the watchdog was never fooled.** `monitor.py` reads the heartbeat
through the swallowing loader, gets `0`, and its own guard turns that into `stale_secs = 0` — so it
neither alarmed nor restarted. Nothing in the trading loop reads this file to decide anything.

**Tests:** `algos/tests/test_bot_state_atomic.py` (4). Three watched RED against HEAD (1,195
unreadable reads of 6,965; the good record overwritten; no scratch-path separation). The litter check
passed at HEAD by construction and is pinned by MUTATION — removing the temp cleanup reddens it.

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

**DELETED 2026-08-12 by `/dead-code-audit`: `bots/launcher.py`, and it is the empty-registry shape
one more time.** Its `BOT_SCRIPTS` had been `{}` since the four bots went on 2026-06-22, so it
could only ever have refused every `--bot` it was given — `argparse` validates against
`choices=BOT_SCRIPTS.keys()`. No scheduler XML named it, no `.ps1` named it, nothing imported it.
⚠ **The tests that mention "launcher" are about `startup_coordinator.py`** — `test_watchdog.py`
reads `STARTUP_SEQUENCE` out of that file by AST, and the word is prose. **`startup_coordinator.py`
is the only thing that launches a bot**, and it has been since `algos/live/runner.py` changed the
flag shape from `--config <file>` to `--bot <key>`; the roster in `## Registering a bot` names it.

Three unused functions went in the same pass, each with zero call sites repo-wide:
`notifications/telegram_bot.py::save_users` (the writer left behind when the user-management
commands were deleted on 2026-08-05 — the command center writes `users.json` over SSH itself),
`bots/startup_coordinator.py::get_log_size` (a wrapper over `log_baseline(...)[1]`, superseded when
the baseline had to start carrying its PATH), and in `algos/nt8/` the standalone CLI pipeline
`run_all.py` / `deploy.py` / `analyze.py` plus the pywinauto probe `debug_sa_display.py`. ⚠ **The nt8
trio predated the command center and did its job — deploy, wait for a manual Strategy Analyzer run,
fetch, analyse.** The Deploy button and the backtest lab own that path now. ⚠ **`backtest_config.json`
STAYS and is not orphaned with them**: `command-center/backend/services/strategy_scanner.py` reads
it. `nt8_agent.py`, `nt8_backtest_runner.py`, `nt8_compile_runner.py` and `setup_agent_task.py` are
all live. `test_bt_switch.py` stays too — it is the VPS debug script `conftest.py` deliberately
`collect_ignore`s.

| File | Location | Role |
|------|----------|------|
| `shared_regime.py` | `shared/` | Market regime classifier shim: 5 labels (TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY). Each bot owns its own REGIME_RISK_TABLE. |
| `mt5_ops.py` | `shared/` | All MT5 operations — symbol-parameterized, single shared instance per bot. `symbol_spec()` / `margin_for()` / `free_margin()` are what `order_sizing` reads; each returns `None` rather than a guess, and a `None` is a REFUSAL at the caller |
| `account_risk.py` | `shared/` | **The one place the WHOLE ACCOUNT's open risk is totalled.** `order_sizing` answers *how big is this order*; this answers *how much is already on*, across every bot and every hand trade. Pure — no MT5, no I/O. Reads the BROKER as truth (via `mt5_ops.account_exposure()`), because every alternative needs the bots to trust each other and a crashed bot leaves a stale reservation. Risk is measured to each position's **CURRENT** stop, so a stop at breakeven frees its room. **A position with no stop REFUSES rather than scoring zero** — its risk is unbounded, not absent. **It refuses; it never shrinks**, and the docstring records why that differs from `backtest/portfolio/`, which does |
| `order_sizing.py` | `shared/` | **The one place a broker lot count is produced.** Pure, no MT5, no I/O: takes the strategy's intent + a `SymbolSpec` and returns a `SizedOrder` or a `SizingRefusal`. Instrument-agnostic — lots come from `(stop_distance / tick_size) x tick_value`, so gold, a JPY pair and an index are one arithmetic. **It refuses rather than rounding up, clamping down, or shrinking to fit.** Built after the 2026-08-07 oversizing incident; read its module docstring before touching sizing anywhere |
| `bot_state.py` | `shared/` | Single source of truth read/write for each instance's `bot_state.json` |
| `credentials.py` | `shared/` | **The one place secrets are resolved.** Env var → git-ignored `algos/credentials.json` → empty. Never holds a literal. Copy `algos/credentials.template.json` to set a machine up. **Any key resolves, not just the canonical three** — a per-bot secret needs a new entry in that file and nothing else; the env name is always `LWG_<KEY IN CAPS>` (`env_name()`). |
| `notify.py` | `shared/` | Telegram sender. `send_telegram(text, kind, chat_id="", token_key="")` — **`kind` is `TRADE` or `HEALTH` and is REQUIRED**; it picks the room (see `### Two rooms` below). `chat_id`/`token_key` are optional and empty = the shared destination for that kind and the shared bot, so routing is PER BOT without a second sender. Reads `credentials.py`, never a hardcoded token, and NEVER raises — an unconfigured or unreachable notifier drops the message and prints once, because a notification channel must not be able to stop a trading loop. The four `notifications/` scripts now import their credentials from the same resolver instead of carrying inline copies (the 2026-07-06 refactor note, done 2026-07-30). |
| `structure_engine.py` | `shared/` | Market structure shim over `market_structure.StructureEngine` (canonical BOS/CHoCH/swing detection, ported from `indicators/engines/structure_engine.pine`) — bot-facing `update(candle: dict)` interface |
| `bot_utils.py` | `bots/` | Config loader, logging, path resolver |
| `startup_coordinator.py` | `bots/` | Orchestrates bot startup sequence — **the only launcher**, see below |

### `live/` — the live runtime (new 2026-07-30)

The seam between a validated backtest and real orders, for a `strategies/python/` bot. **It contains
no strategy logic:** the same strategy object the lab replays is stepped bar by bar, and this package
only supplies live bars and mirrors its intent onto the broker. That is what keeps a live result
comparable to a backtest result.

| File | Role |
|------|------|
| `runner.py` | The loop — connect, verify the version pin, warm the engines, **probe the terminal link**, poll for a CLOSED bar, step, reconcile, heartbeat. `--dry-run` is the default; `--live` must be typed. The link probe is first on every pass and is `account_info()`, never a bar read — see the 2026-08-04 entry above. |
| `bridge.py` | Strategy intent ⇄ MT5 orders. Places/moves/cancels the resting limit, ratchets the stop, reports fills, notices an order the BROKER deleted, and **HALTS when the emulator and the broker disagree** rather than continuing on a fiction. **Every lot count it sends comes from `shared/order_sizing.plan_order` and from nowhere else** — see the 2026-08-07 entry. Since 2026-08-09 that same seam also runs the **account-level** cap (`_account_cap_check` → `shared/account_risk.py`), which is the only thing in the live path that reads past this bot's own magic number. |
| `feed.py` | MT5 rates → the canonical replay frame. Never hands over the forming bar; reports how far behind it is so a gap re-warms instead of resuming. |
| `ledger.py` | Append-only JSONL in **two streams that never overlap** — `decisions-*.jsonl` (bar, blocked, missed, trade, order events) answers *why did it trade or not*; `health-*.jsonl` (starts, stops, crashes, link outages, re-warms, config changes, `pulse`) answers *is the process alive*. See `## The daily record` below. |
| `position_state.py` | The OPEN POSITION, written down, so a restart can pick it up. `<instance>/position.json`, atomic, rewritten on the fill and on every stop move, deleted on close. **Nothing here is adopted on trust** — the bridge restores only when the record's ticket, direction, size, entry and stop all match what MT5 holds, and halts exactly as it always did otherwise. Deliberately NOT the decision ledger: that is an audit log, and recovering live state from a channel built to carry a status is a mistake this repo has already paid for. |
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

**`tools/shadow_diff.py` — did the LIVE bot decide what the LAB says it should have?** Step 9.2 of
`docs/LIVE_TRADING_PIPELINE.md`. It joins the bot's own `bar` ledger stream to a lab replay of the
same window and diffs them field by field. The claim it checks is narrow and therefore useful:
`algos/live/` holds no trading logic, so the two run the same strategy object and **any difference
is data — a feed, a clock, or a warm-up — never logic.**

⚠ **Joined on bar TIMESTAMP, never on index.** The live index counts on from wherever warm-up
stopped and survives restarts; the lab's counts from the first row of whatever frame it was handed.
Two unrelated integers that look comparable — the trap `strategies/CLAUDE.md` records from the
B-LEG harness, where 2,409 comparisons failed at one flat offset while the logic was identical.

⚠ **FEED drift and DECISION drift are reported SEPARATELY**, because the live bot trades PU Prime
`XAUUSD.s` and the lab replays Vantage `XAUUSD` — different brokers, so their bars genuinely differ.
Merging them would let a quote gap read as a strategy bug, or hide a real divergence inside an
expected one. ⚠ **It compares only what the ledger records**; the sequence fields are named as
uncompared rather than dropped, so a green run means "every field that CAN be compared matched".

**First run, 2026-08-04, 148 live bars:** clock perfect (148/148 timestamps align), 10 of 11
decision fields bar-for-bar identical, feeds differing by a systematic +4-5 cents. The eleventh
exposed a knife-edge in the entry model — see the header entry and `LIVE_TRADING_PIPELINE.md` G17.
Tests: `algos/tests/test_shadow_diff.py` (11), all on the join, because a join that matches too
little invents drift and one that matches too much invents parity.

**`tools/broker_facts.py` — MEASURE the live broker's costs instead of assuming them (2026-08-05).**
G5's measurable half. Every cost figure in this repo was taken on **VANTAGE** and the live bot
trades **PU PRIME**; this repo has already recorded a 50% error from quoting one broker's spread
for the other ($0.22 vs $0.33), and the shadow diff found the feeds differ by a systematic 4-5
cents on every bar. Read-only: it attaches to an already-running, already-logged-in terminal,
reads the symbol specification, then samples live ticks for a spread DISTRIBUTION.

⚠ **A single spread reading is not the spread**, and the instance config's `_measured` block
records exactly one — "spread 33 points", taken once on 2026-07-31. Gold widens at the 17:00 NY
rollover, around news and out of hours; the Vantage figure this repo trusts is a MEDIAN over 1.49M
ticks. The sampler is the point of the tool and the specification read is the cheap half.
⚠ **It asserts the ACCOUNT before printing anything.** This box runs two terminals — MT5_FFT (PU
Prime, the live bot) and MT5_Lab (Vantage, the backtest agent) — and `mt5.initialize()` with no
path grabs whichever answers first, which is the leak `_ensure_mt5()` below was written to close.
**Reporting Vantage's swap as PU Prime's is the exact error this tool exists to end, and it would
look completely normal.**
⚠ **`--path/--account/--symbol` measures an account that is NOT a bot (2026-08-08).** `--bot` reads
all three out of an instance config and stays the everyday path; the explicit form exists because
**a second ACCOUNT TIER is the only thing that can answer `docs/BROKER_QUESTIONS.md` question 3**,
and a Prime or ECN demo is not a registered bot. Both routes go through the same `attach()`, so the
account assertion is NOT relaxed — an explicit run still states the account it expects and still
refuses a terminal logged into a different one. ⚠ **`--symbol` is required with `--path` and is
worth passing even with `--bot`: PU Prime suffixes the TIER onto the symbol name** — the same market
is `XAUUSD.s` on Standard and `XAUUSD.p` on the raw tiers — so the instance config's symbol is
simply absent on another account. Run `--symbols` first and read what the account actually carries.
⚠ **A stale tick repeated for five minutes is NOT a rock-steady spread** — the sampler counts
repeats separately and reports no statistics at all when nothing fresh arrives, because a shut
market is otherwise the most confident-looking wrong answer it could give.
⚠ **It writes nothing.** `_measured` is a claim about when a reading was taken and by whom; a tool
silently rewriting it would make a fresh measurement indistinguishable from a stale one.
⚠ **Everything it PRINTS is ASCII, deliberately.** The VPS console is cp1252 and one non-ASCII
character raises `UnicodeEncodeError` mid-print — on the first run every number was measured and
printed and then a trailing warning line killed the process with a traceback and exit 1, so **a
successful measurement looked like a crash**. `sys.stdout.reconfigure(errors="replace")` is the
belt; degrading one character beats discarding the report it was decorating.

**FIRST MEASUREMENT — PU Prime demo `XAUUSD.s`, 2026-08-05 15:2x UTC (London/NY overlap, market
open), 120 fresh tick reads, 0 repeats.** Against the Vantage figures every backtest here uses:

| | PU Prime (live) | Vantage (all backtests) | gap |
|---|---|---|---|
| spread, median | **$0.32** (32 pts) | $0.22 | **+45%** |
| spread, p99 / max | $0.36 / $0.36 | 0.31 (p99) | — |
| swap LONG /lot/night | **−79.60** | −74.84 | 6% worse |
| swap SHORT /lot/night | **+30.25** | +26.98 | 12% better |
| contract / tick value | 100 oz / $1.00 | same | — |
| broker min stop | 20 pts = **$0.20** | — | — |

⚠ **The $0.33 in the instance config's `_measured` block was a single instant on 2026-07-31 and it
happens to be close — do not read that as confirmation.** A sample of one cannot be near or far
from a median; it just landed inside the band this time. The p99 already reaches $0.36 inside two
minutes of an open session.
⚠ **The spread is 45% wider than every cost figure in this repo assumes.** `backtest/fills.py`'s
`PROFILES` carried PU Prime at $0.33 from 688k ticks when this was written, which is closer, but the
layered-cost tables in `strategies/python/mpc_sos_fade/CLAUDE.md` were all run on Vantage's $0.22 —
so the charged rows there understate this account.
✅ **SUPERSEDED 2026-08-06: `PROFILES` now carries $0.32** (re-measured over 1,893,438 ticks / 3
whole days), and it is stored per ACCOUNT TIER — `_SPREAD_XAUUSD_PUPRIME_STANDARD`, because this
demo is a Standard account and an unread tier refuses rather than borrowing it. **Do not quote the
$0.33 above as current**; it is kept because the paragraph is a dated record of that day's reading.
🔴 **AND SUPERSEDED AGAIN FOR THE ACCOUNT THIS BOT ACTUALLY TRADES: NONE OF THE NUMBERS IN THIS
PARAGRAPH BELONG TO IT.** Every figure above was read off a **Standard** account (`XAUUSD.s`); the
bot moved to the **ECN** demo 700152905 / `XAUUSD.p` on 2026-08-12, and that tier measured
**$0.12** on 2026-08-14 — 3,033,270 ticks over 5 whole days, all 23 traded hours, `broker_facts.py
--bot mpc_sos_fade_demo --history-days 6`. **2.7x tighter than anything written above.** The tier
table and what still refuses: `backtest/CLAUDE.md`. ⚠ **This is the second time a dated reading
here has quietly become a statement about a different account** — a paragraph that names its
account survives the move; one that says "the live demo" does not.
⚠ **The short swap is a CREDIT and it is BIGGER here than on Vantage.** Gold's long swap costs and
its short swap pays; on the 6.5-year replay shorts were paid 2.14R while longs paid 8.55R, so this
broker is slightly better for the short side and slightly worse for the long one.
⚠ **STILL A SNAPSHOT.** 120 seconds of one session is not the spread — gold widens at the 17:00 NY
rollover, around news and out of hours, and the Vantage number it is being compared against is a
median over 1.49M ticks spanning a year. **Re-run in an Asian session and across a rollover before
this number goes into a cost model.** Commission is unmeasured here and remains so until a real
trade closes — `get_deal_breakdown` records it per trade now.

Standalone MT5 lab tooling (not imported by any bot) lives in `tools/`: `download_mt5_history.py` (warm the lab MT5 history cache) and `audit_mt5_data_quality.py` (its read-only companion — probes what the broker actually serves). Both run on the VPS against `C:\MT5_Lab`.

**Backtest data source — pinned to MT5_Lab only (2026-07-22).** All backtest price/tick data comes from the MT5 agent (`markets/fx/tools/mt5_agent.py`, VPS port 8766). Its `_ensure_mt5()` binds the Python API to the **MT5_Lab** terminal64.exe *only* (`TERMINAL_PATH` / `MT5_DATA_DIR`, else the baked-in `C:\MT5_Lab` default); if a live bot terminal (MT5_FFT, etc.) is already attached it drops and re-binds, and if MT5_Lab can't be reached it FAILS loudly rather than silently reading the wrong account. This closed a real leak — the old code called `mt5.initialize()` with no path and grabbed whichever terminal answered first. **MT5_Lab is logged into a Vantage demo (account 25893735, `VantageMarkets-Demo`)** so backtest data matches TradingView's `VANTAGE_XAUUSD`; this replaced the earlier PU Prime `XAUUSD.s` feed. Vantage's gold symbol name/suffix may differ from `XAUUSD.s` — if a run returns no bars, check the symbol name first. To pick up an agent-code change: `git pull` on the VPS **and** restart the `MT5AgentRDP` scheduled task (kill only the specific `mt5_agent.py` PID) — never a blanket `taskkill python.exe`, which also kills the NT8 backtest agent (`NT8Agent` task).

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

🔴 **The stale-stamp fallback is `max(heartbeat, started)`, never `heartbeat or started`.**
`bot_state.json` outlives the process, so a restart refreshes `started` and leaves the DEAD run's
`heartbeat` in the file — a stale-but-truthy stamp wins an `or` outright and every restart drew a
false `STALLED`/`RECOVERED` pair quoting the previous run's clock (measured 2026-08-13). ⚠ **The
test that was supposed to cover this passes `started` with NO `heartbeat`** — a bot that has never
run, not one that restarted — so both fields present with one of them stale was the untested shape.
Story: `docs/ALGOS_BUILD_NOTES.md` → *The restart that reported itself stalled*.

**`SYS_DEADMAN` is ON as of 2026-08-04** — every 5 minutes as SYSTEM, the external dead-man's
switch described in the header. It is the only alert here that does not originate on this box.
⚠ **It is INERT until `deadman_url` is set in `algos/credentials.json`** (deliberately: it reports
honestly and sends nothing rather than failing every five minutes). Check with
`deadman.py --status`, and treat an unset URL as an open gap rather than a configured switch.

**`SYS_LOGBACKUP` is ON as of 2026-07-31.** Daily 00:30 UTC (the VPS clock is UTC), runs
`tools/log_backup.py`: zips the instance `.log` files into `algos/log_archive/`, prunes past 90
days, reports closed AND open record files. **It does no git** — see the SYSTEM-cannot-push note
above. The record reaches the repo via `algos/tools/ledger_sync.py` on the Mac, which since
2026-08-05 runs **itself, every 12 hours** under launchd — see `### The daily record` below. Logs
are COPIED, never rotated: the bot holds its log open and renaming an open file on Windows fails.

**`SYS_PNLTRACKER` and `SYS_REPORTER` no longer exist — deleted 2026-08-05, tasks and scripts
both.** They had sat here as "deliberately disabled, waiting for a bot registry", which is what
made them look like features. They were not: both carried an EMPTY registry (`BOT_TRADES = {}`,
`BOTS = {}`) inherited from the four bots deleted 2026-06-22, so enabling either would have run a
script that found no bots and exited. The tracker sent daily-goal / daily-cap / weekly-cap Telegram
alerts; the reporter sent a 4pm performance summary.

⚠ **The reason for deleting rather than fixing is worth keeping, because it decides what replaces
them.** A daily report on a strategy taking ~2 trades a month says "no trades today" almost every
day, and a channel that is noise 95% of the time is the one nobody reads on the day it matters —
the bot already pings on entry and exit. And the loss cap was **an alert, not a limit**: nothing in
it could refuse a trade, so it read on the Bots page as protection while the bot traded straight
through it. A real cap belongs in `algos/live/runner.py` where it can stop the loop.

⚠ **Deleting them took out more than two files, and the collateral is the interesting half.**
`shared/thresholds.json` and `BOT_THRESHOLDS` went (nothing else read them). The derived P&L fields
went out of `bot_state.py`'s defaults — `daily_pnl`, `weekly_pnl`, `total_pnl_pct`, `peak_balance`,
`trades_today` — rather than being left at `0.0`, because with no writer they would have rendered
"+0.00% today" under a field nothing measures: **this repo's own rule, that a fabricated zero and a
measured zero must never be the same value.** `balance` stays, written by `live/runner.py`. 🔴 **And auditing that claim found the defect this pass nearly shipped: `total_pnl_pct` had no writer either.** It was `set_pnl`'s too, and the Bots page's *Overall P&L* column and Telegram's `/balance` BOTH defaulted it to `0.0` — so a live account up 5% reported dead flat, in two places, with nothing on either screen able to say the number was never measured. **`live/runner.py` writes it now, because it is the only process that can**: it already reads the balance every poll, anchors `starting_balance` ONCE, and derives the percentage — `None` when the terminal is blind, never `0.0`. `/balance` reads both without a numeric default and prints `no MT5 link` or the bare balance instead of inventing a flat account. ⚠ **The lesson is about the DELETION, not the field: removing a writer leaves its readers behind, and a reader with a numeric default goes on answering confidently.** Grep for readers of anything a deleted job wrote — the seven fields that had no reader were the easy half. And
Telegram lost `/report`, `/demo`, `/live`, `/all` and **`/force`** — the last one mattering most,
because it fired *whatever* action was pending, so with reports gone it was an undocumented second
route to `/restart`, `/stop` and `/emergency`, and the `readonly` role held it.

⚠ **The same pass found `bootstrap_vps.ps1` registering neither `SYS_DEADMAN` nor `SYS_LOGBACKUP`**
despite both task XMLs sitting in `scheduler/`. A rebuilt box came back with **no dead-man's
switch** — the one alarm that fires when the box itself dies — and nothing anywhere would have said
so, because a missing alarm is silent by construction. Both are in the list now.

**The standing lesson: a job that is "disabled until later" and a job that does nothing are
indistinguishable from the outside, and the label protects the second one.** Before switching any
disabled task on, read what it would do with today's registries — not what its name says it does.

### The daily record — two streams, and what makes a silent death visible

**Built 2026-08-05 to Aaron's spec:** every day must carry (a) enough about the bot's *health* that
a bug or a silent death is readable from the logs, and (b) everything about *trades* — taken,
skipped, blocked, and why — with **nothing overlapping between the two**. Both go to GitHub twice
a day.

**Three files per bot per UTC day**, all rotating on the same boundary so they read side by side:

| file | question it answers | contents |
|---|---|---|
| `<inst>/ledger/decisions-YYYY-MM-DD.jsonl` | why did it trade, or not | `bar` (one per closed bar: stages, arms, edges, vetoes, stop, TP ladder), `blocked`, `missed`, `trade` open/close, and the broker-facing order events (`order_placed`, `order_refused`, `order_too_small`, `stop_moved`, `dry_run_action`, `warmup_position_skipped`) |
| `<inst>/ledger/health-YYYY-MM-DD.jsonl` | is the process alive and behaving | `startup` / `shutdown` / `startup_failed` / `version_mismatch`, `warmed`, `rewarm`, `mt5_link_lost` / `_restored`, `bar_error`, `loop_error`, `config_applied` / `_refused`, `halted`, `went_live`, and a `pulse` every 15 min |
| `<inst>/<bot>-YYYY-MM-DD.log` | the prose, with the tracebacks | the human log; per-day since this pass, via `runner.DailyFileHandler` |

**The dividing line is the SUBJECT, not the severity.** A record about a setup or an order is a
decision; a record about the process that runs them is health. That is why `order_refused` (the
broker declined a real order) is a decision and `halted` (the bridge stopped placing anything) is
health — one answers *why no trade on that setup*, the other *why no trading at all*.

⚠ **Routing is ONE dict (`ledger._DECISION_EVENTS`) and it is TEST-ENFORCED.**
`tests/test_ledger_streams.py` greps every `ledger.event("...")` call in `algos/live/` and fails if
the name is not classified, in **both** directions — an unrouted event would fall into health and
read as a process fault, and a rule for an event nobody writes any more is documentation of
behaviour that does not exist. Same shape as the news calendar's matches-nothing guard.

🔴 **The two mechanisms that make a silent death visible, because every failure worth catching here
produces NO OUTPUT.** A killed process writes nothing. A wedged loop writes nothing. A quiet Sunday
writes nothing too — which is why "the file is short today" was never a signal.

1. **Every exit the process CHOOSES writes a `shutdown` record**, with its reason and exit code,
   from `run()`'s `finally`. That is what makes the converse informative:
   **no `shutdown` record ⇒ it was killed or the box died.** ⚠ Until this pass only the clean
   Ctrl-C path wrote one — a failed connect (3), a halted bridge (4) and ten consecutive loop
   errors (6) all returned in silence, so the absence meant *killed, crashed, OR one of three
   ordinary refusals*, i.e. no signal at all. The startup of the NEXT run reads it back
   (`previous_run_clean`) and logs a warning, because **the trace of a hard kill has to be written
   by something still alive.** `None` there means UNKNOWN — a first-ever start or an unreadable
   file — and is deliberately not `True`, the same three-state rule as `mt5_link`.
2. **A `pulse` every 15 minutes** carrying link, balance, bridge state, position, last bar, bars
   seen, gap and uptime. ⚠ **The cadence IS the feature**: it is the one record whose *absence* is
   the signal, so a stall becomes a gap of known size instead of an absence somebody has to
   interpret. It is not the same thing as `bot_state.json`'s heartbeat — that file is overwritten
   in place, so it can say the bot is blind NOW and can never say for how long, or that it happened
   at all once it recovers. That is exactly what the 50-minute outage on 2026-08-04 left behind.

**Backup runs every 12 hours, on the Mac.** `scripts/install_ledger_sync.sh` installs a launchd
agent (`com.lwg.ledger-sync`) at **00:05 and 12:05 local**, running `tools/ledger_sync.py`: it asks
the VPS for its closed and open files (`log_backup.py --list-closed` / `--list-open`), scp's them
into `algos/ledger_archive/`, and commits. ⚠ **Today's files are fetched too and are still being
written**, so `_whole_lines` drops a trailing partial JSON line before committing — the check is
*does the last line parse*, never *does it end in a newline*, because a record can be flushed
complete a moment before its newline lands and truncating on the newline would silently discard the
newest record on every sync. Text logs are never truncated: prose is not records.

⚠ **`closed` and `open` stay separate concepts even though both are now committed.** A closed day
is final; an open one is the best copy so far and will be fetched again. Merging them is what lets
a torn half-day later read exactly like a whole one.

⚠ **The VPS still does not push, and must not be made to.** Its tasks run as SYSTEM, whose Git
Credential Manager has no token and no interactive session, so `git push` BLOCKS rather than
failing (measured 2026-07-31). Fixing that means a GitHub write token on a box already holding a
live MT5 password. **The honest cost of the Mac-side design: the backup runs only when this Mac is
on.** launchd fires a missed calendar job on the next wake, so a closed laptop delays rather than
skips — but a Mac off for three days is three days of record on one disk.

⚠ **The text log rolls by choosing a NAME, never by renaming** (`runner.DailyFileHandler`).
`TimedRotatingFileHandler` renames the live file, and renaming a file Windows holds open fails with
a sharing violation — the same trap `log_backup.py` records as *"logs are COPIED, never rotated"*.

⚠ **`log_backup.py` imports `STREAM_RE` from `live/ledger.py` rather than restating it.** Two copies
of the filename pattern drift, and the drift's symptom is a whole stream that is silently never
committed — which looks exactly like a stream that was never written.

Tests: `tests/test_ledger_streams.py` (12), `tests/test_live_health_stream.py` (13, **12 watched
red against HEAD** before the fix), `tests/test_log_backup.py` (26).

🔴 **DEPLOYING THAT SPLIT BROKE STARTING THE BOT, TWICE OVER, AND BOTH FAILURES REPORTED SUCCESS.**
Found by stopping the live bot to deploy and being unable to bring it back — not by the suite.

1. **`startup_coordinator.bot_is_running` matched the coordinator ITSELF.** In single-bot mode
   this process is `startup_coordinator.py --bot <key>`, and the check was a substring search for
   `--bot <key>` over the whole `wmic` dump, so it found its own commandline. **That is the path
   the command center's Start button drives** — the button could never start a bot, and it said
   the reassuring thing while failing: *"already running — left alone"*. ⚠ The anti-duplicate
   guard it belongs to was one day old and right in intent. **`runner.already_running()` got the
   same check right by excluding its own PID** — two implementations of one rule, one wrong, the
   shape this repo keeps meeting. The match now requires the RUNNER SCRIPT *and* the key, per
   line: the key alone says which bot, the script alone says which fleet, **only the pair says a
   running bot**, and a coordinator holding the same key is not one. ⚠ **`runner.already_running()`
   had the SAME latent race and it was found by reading, not by it biting**: it excluded its own
   PID but matched `--bot <key>` alone, and the coordinator that Popens it is still alive while it
   boots — so the runner could refuse to start the very bot it was asked for, log an error and
   return 0. Fixed the same way. **The PID rule and the script+key pair cover different impostors
   — itself, and its launcher — so both stay.**
2. **`wait_for_connection` watched `<bot>.log`, which the dated handler had stopped writing.** A
   perfectly healthy start would have timed out after 180s and been marked `offline`. ⚠ **A
   healthy start reported as a failure is worse than a silent one — it sends you to fix a bot
   that is fine.** `live_log()` resolves the newest `<bot>-YYYY-MM-DD.log` each poll, falling back
   to the plain path. ⚠ **The baseline PATH now travels with the baseline SIZE** (`log_baseline`):
   on the first start of a UTC day the bot writes a *different* file from the one measured a
   moment earlier, and applying yesterday's size as an offset into today's file slices off its
   front and hides the very line being waited for.

⚠ **`schtasks /run` reported SUCCESS for the run that started nothing**, exactly as this file
already warns. The check that caught it was `wmic` — probe the thing you are claiming, every time.

🔴 **And the commit-msg hook silently broke the unattended backup for the SECOND time in one day.**
Its exemption had been widened that morning to `*/ledger/decisions-*.jsonl` after the sync was
found refusing with a day outstanding. The split added two new shapes — `health-*.jsonl` and the
dated `.log` — and **the sync broke again on its first run**, because an exemption enumerates the
shapes that existed when somebody wrote it. ⚠ **A rule that fires on a robot's commit has no human
to read its message: it does not nag, it silently stops the job**, and a backup that quietly stops
happening looks exactly like a backup with nothing to do. Both shapes are exempt now, and the real
fix is that **the hook is driven FOR REAL against the exact paths `ledger_sync.py` writes**
(`tests/test_commit_hook_ledger_exemption.py`, 6 tests, 3 watched red) — a fourth artefact added to
the sync fails in the suite instead of at midnight. ⚠ **The exemptions stay narrow PATHS, never
`*.jsonl` / `*.log`**, and a test pins that: a future file holding a contract under either
extension must still demand its doc, the way `*.meta.json` explicitly does.

🔴 **Then `.gitignore`'s blanket `*.log` swallowed the text log — the THIRD silent break of one
backup in one day, and the quietest.** The sync fetched the file, `git status` did not list it (an
ignored file is not a changed one), `pending()` dropped it without a word, and the run printed
**"2 file(s) pushed"** having committed two of the three streams it had just downloaded. ⚠ **From
the commit side an ignored file and a file that was never written are identical** — this repo's
own two-things-one-value rule, arriving through git's config where nothing was looking. Fixed
twice over, because either alone leaves the hole open: a `!algos/ledger_archive/**/*.log`
negation, and `ledger_sync.ignored()`, which NAMES an unbackupable fetch and **returns non-zero**
rather than reporting success. ⚠ **`git check-ignore` must be read WITHOUT `-v`**: with it, git
reports the last matching pattern *including negations* and exits 0 for a path a `!` rule has
re-included — the first version of the test failed on a correctly-committable file for exactly
that reason. Tests: `tests/test_ledger_archive_is_committable.py` (5), one of them run against
**this repo's real `.gitignore`** rather than a fixture, because the rule that broke the backup
was a real line in a real file and a fixture would have been written to pass.

**The standing lesson: a rename is a contract change, and the readers of a filename are invisible
from the file that writes it.** Nothing imports `<bot>.log`; two separate pieces of the launcher
simply knew the name, the commit hook knew a third, and `.gitignore` knew a fourth. **Every one of
the four failed silently and three of them reported success.** Tests:
`tests/test_startup_coordinator.py` (10, **7 watched red**).

### `SYS_LOGREVIEW` — reading the record, because nothing did

**Built 2026-08-05, hourly, `notifications/log_review.py`.** The health stream above is only worth
writing if something reads it. Nothing did: `monitor.py` asks whether the PROCESS is there and
stamping, `deadman.py` asks whether the BOX can still talk, and neither opens a line the bot wrote.

🔴 **So the bridge could be HALTED and no alert in this system could see it** — the loop runs, the
heartbeat ticks, `wmic` lists the process, the Bots page says RUNNING, and the bot places nothing.
Same for a crash loop overnight, a terminal link lost and regained four times, a re-warm storm, or a
runtime config change the bot REFUSED (so the command center shows settings it is not using).

**The charter, stated so this does not grow into a second watchdog: `monitor.py` owns NOW, this owns
THE RECORD.** The watchdog answers *is it alive this minute* and restarts it; this answers *what does
today's record say happened*, including things that recovered before anyone looked. That split is why
this deliberately does NOT alert on "process gone" or "heartbeat stale" — those are the watchdog's,
and two alerts for one event is how a channel gets muted.

⚠ **It restarts nothing and starts nothing.** The watchdog owns recovery; two things issuing starts
for one bot is how a book gets doubled (measured 2026-08-04).

⚠ **Silent when clean — no "nothing to report" message, ever.** The reason `reporter.py` was deleted
rather than fixed applies here in full: a channel that is noise 95% of the time is the one nobody
reads on the day it matters.

⚠ **One alert per OCCURRENCE, not per run.** Findings carry a key containing the timestamp of the
thing that happened, so the same halt does not ping 24 times a day **and a NEW halt still does**.
Keying on the KIND of thing would alert once and then stay silent through every future incident —
the classic de-duplicating-alerter bug, and it is silent by construction. State lives in
`algos/log_review_state.json`; an unreadable state file RE-ANNOUNCES rather than suppressing, because
noisy once beats silent forever.

⚠ **Being unable to read is a FINDING, never silence** — but only for a bot whose state says it
should be running. The rule this repo has now met five times, and here the reassuring answer is the
dangerous one: a checker with nothing to say is indistinguishable from a system with nothing wrong.
The other half matters just as much: **a bot you stopped on purpose has no record to write**, and an
alarm that fires every time you stop one is an alarm you learn to ignore.

**It reports in two places because they fail differently.** Telegram gets one message per new
finding — an alert you scrolled past is gone. `<instance>/review.json` is a standing flag the command
center renders as a **Needs review** chip on the Bots page, and it is still there tomorrow. ⚠ **Its
own file, NOT `bot_state.json`**: the runner rewrites that every poll through a read-modify-write, so
a review written into it would race the heartbeat and could be lost, or clobber a balance.

⚠ **`telegram_health_chat` in `credentials.json` sends findings to a SEPARATE chat from the one
carrying fills.** These messages are routine chatter ("reconnected twice, re-warmed"), and the day you
mute them you must not also mute your trades — the same reasoning behind the dead-man's switch using
EMAIL. Unset falls back to the main group and says which it used on stdout: an alert in the wrong
room beats no alert, which is the OPPOSITE call from `deadman_url`, where unset means the check
cannot work at all.

### Two rooms — every message declares its KIND

🔴 **Splitting the reviewer's findings out was the small half of this, and shipping it that way would
have missed the point.** Aaron's rule is that the chat he reads for entries and exits carries nothing
else. A sweep of every Telegram sender in the repo found **32 messages going to that chat and only 2
of them were trades**: the live runner's twelve lifecycle messages (link lost, link restored,
re-warming, startup banner, clean stop, config refused, and the bridge's **HALTED**), the watchdog's
nine (offline, restarted, stalled, recovered, two CRITICALs), the command center's nine buttons
(start/stop/restart/promote/runtime params), the Telegram bot's own startup ping, and every finished
stress test. **The reviewer had a routing config; nothing else did** — which is the shape of fix that
looks complete and leaves the problem where it was.

So a message now states what it IS and the kind picks the room:

| kind | goes to | who sends it |
|---|---|---|
| `TRADE` | `telegram_chat_id` | `live/bridge.py` only — the entry alert and the exit that replies to it |
| `HEALTH` | `telegram_health_chat` → falls back to `telegram_chat_id` | everything else in the repo |
| `SIGNAL` | `telegram_signal_chat` → falls back to `telegram_chat_id` | `live/setup_alerts.py` only — a setup forming, its entry zone going live, a rule blocking it, and what became of it. See *A THIRD room* below |

⚠ **`kind` is a REQUIRED argument, not a defaulted one.** A default routes silently, and "the wrong
room, quietly" is the exact failure this ends — the same reasoning behind the ledger's stream routing
being a table rather than a guess. ⚠ **And a required argument alone is not the guard**: a forgotten
one is a `TypeError` raised at 3am inside the very alert that was trying to tell you something, so
`tests/test_notification_routing.py` **greps every call site in `algos/` and `command-center/`** and
fails in the suite instead. Same shape as `test_ledger_streams.py`, for the same reason. Both grep
tests also assert they MATCHED something — a sweep that finds nothing passes for ever.

⚠ **The fallback is deliberately asymmetric.** HEALTH with no room of its own borrows the trades chat
and warns once; TRADE never borrows the health chat. Health in the wrong room is a nuisance you can
see, a fill buried in re-warm chatter is the thing being prevented.

⚠ **The HALT is HEALTH, and it is the call worth defending** — it is the most consequential message
here, which is precisely why it must not sit in a room only checked when a fill arrives. It is also
why `log_review.py` raises it AGAIN as a standing chip on the Bots page: one Telegram line, in any
room, was never enough for that one.

⚠ **Telegram command REPLIES are not routed at all** (`telegram_bot.send_to`) — an answer belongs
where the question was asked. A `/balance` typed in the trades group replying somewhere else would be
baffling, and it is not an unsolicited message competing for attention.

⚠ **`command-center/backend/services/notify.py` carries a SECOND copy of this table**, because the two
subsystems may read each other's files and never import each other's code. What holds them together is
that both route on the same credential KEYS, pinned by a backend test that READS `shared/notify.py`.
That app also refuses to use `TRADE` at all, by test: it has no way to know a trade happened.

⚠ **`log_review.py` read `credentials.json` directly until this pass**, which silently ignored
`LWG_TELEGRAM_HEALTH_CHAT` — an env override this repo's own template documented and nothing honoured.
It goes through `notify.chat_for` now. **A second reader of one credential is a second answer.**

### A THIRD room — `SIGNAL`, the pre-trade setup channel (2026-08-13)

Aaron's ask: know a setup is coming *before* it trades — the confluences so far, the entry ZONE
(shallow to deep), the projected stop — then have the outcome reply to that same message, whether
it filled, was blocked by one of his own rules, or died. New Telegram group, **LWG Capital
Signals**.

`SIGNAL` → `telegram_signal_chat`, per-bot overridable exactly like the other two. **A third room
because it is a third reflex** — read when you have time, not the moment it arrives — and because
it is MEASURED at ~10x the volume of fills (**20.2 messages/month against 2 fills**, one every 1.5
days, on `mpc_sos_fade` over 6.5 years). Putting that in the trades chat would bury the fills under
setups that mostly do not become trades, which is the failure the split already exists to prevent,
arriving from a new direction. Fallback stays asymmetric: SIGNAL borrows the trades chat and warns
once; **TRADE never borrows another kind's room.**

**`live/setup_alerts.py`** is the transition layer and knows NOTHING about any strategy — it reads
`backtest.setups.SetupSnapshot`, so a new bot gets alerts by implementing `live_setups()` and
nothing here changes. Formatting is in `live/alerts.py` (pure, no network, so wording is
unit-testable and can never move a trade). Sending goes through `runner._notify`, so per-bot chat
and token routing come free.

⚠ **Per SETUP, not per transition, and that is a MEASURED failure rather than a preference.** A
resting limit is rebuilt every bar and cleared when not armed — 665 raw transitions across 332
setups over 6.5 years. Edge-triggering alone still announces one setup two or three times.

**The messages are FOUR lines, and they were eight** (Aaron, 2026-08-13, on the first real renders:
*"can you make them less verbose?"*). Confluences collapsed onto one line as the strategy's own
`detail`; `Waiting on a retrace into that zone` went because it sat directly under
`Retrace zone — not tagged yet`; `(the zone's deep edge)` went because it explained a number rather
than giving one. 🔴 **The resting message names only what is OUTSTANDING, and that one line is a
safety property, not a nicety** — an order can rest at 2 of 3 (the gap can exist before price gets
there), so a message carrying a price must not read as *everything is met*. ⚠ **The `display` name
comes from the RUNNER**, because a strategy only knows its class name and `MpcSosFadeStrategy` is
not what the same bot is called in every other message.

🔴 **AND THE SAME TRIM CAUSED THE NEXT DAY'S DEFECT, so the rule it produced is the one to keep:
when trimming a message, a word that explains a NUMBER is decoration and a word that names the
STATE of something is not.** `(the zone's deep edge)` tells you how a price was derived and a
reader can live without it; `(limit resting)` — deleted in the same pass, as the same kind of
parenthetical — was the only word saying no position existed, and the message was read as a fill
the next day. The header is the MT5 order type now (`BUY LIMIT RESTING` / `SELL LIMIT RESTING`) so
the message and the terminal call one thing by one name, and the price line says `Limit`, never
`Entry`. Four tests pin it, all watched RED. Story: `docs/ALGOS_BUILD_NOTES.md` → *The limit that
read as a fill*.

🔴 **`algos/tests/test_setup_alert_wording.py` exists because there was NOTHING there — every one
of these four formatters was rewritten and 643 tests stayed green.** `test_setup_alerts.py` covers
which message fires and in which thread, and asserted not one word of what any of them SAY.
**A message is not a side effect of this system, it is the product**: nobody sees a `SetupSnapshot`.
12 tests, all 7 mutations reddening their own named test. It pins the CLAIMS a message makes that
could be false, never the wording — renaming a label must not redden it.

⚠ **A wording change needs a RESTART but NOT a promote**: `algos/live/` is not in the frozen tree.
A change to a strategy's confluence `detail` or death sentence is the other way round — that is
`strategies/python/`, so it needs `promote.py`, and the death sentences are shared with the lab's
miss report.

**`tools/signal_samples.py` sends one example of every thread shape** — eight of them, covering
both directions, all three retrace wordings, an order resting at 2 of 3, one blocking rule and
three, a block that LIFTS, and every death the strategy has a sentence for. `--dry-run` prints and
sends nothing. ⚠ **It builds real `SetupSnapshot`s and calls the real `alerts.format_*`**, so a
sample cannot drift from what the bot sends; hand-typed samples would review wording that does not
exist. ⚠ **Its `render()` duplicates `SetupAlerts._handle`'s routing** and is the one thing here
that CAN drift — if the order of the checks in `_handle` changes, change it here too.
🔴 **Telegram's group ceiling is ~20 messages a minute and a burst tool is the only thing here that
can reach it** — the first run sent at 1.2s and lost four of twenty-four to `429`, orphaning the
replies under them. 3.5s now, with one retry after a 30s pause. ⚠ **It reports what LANDED and
exits non-zero on any failure**: it printed `sent: 24` while four had been refused, which is the
requested-vs-received rule inside the tool written to check the messages. **The pacing belongs to
the tool, not to `notify.py`** — a bot sending a handful an hour must not pay for a burst sender.

⚠ **NEVER RAISES, and it binds harder here than anywhere else in the package**: `on_bar` runs
inside `_on_bar`, between the strategy stepping and the broker being reconciled.

🔴 **A strategy without the contract gets no alerts and the runner SAYS SO by name at startup** —
never a silent skip. Same rule as `_log_risk_cap` beside it: an absent reporter and a quiet market
look identical from outside. The `setup_alerts` ledger event records ON or OFF, and OFF carries
why.

🔴 **Warm-up snapshots are DISCARDED in `warm()`, and this is louder than the stale-record rule it
sits beside.** `drain_setups()` returns everything resolved since the last drain, so without the
discard the FIRST live bar would post years of history into Telegram in one burst — and again on
every restart.

🔴 **NOTHING IN `algos/live/` MAY IMPORT `backtest`, `engines` OR THE STRATEGY PACKAGE AT MODULE
SCOPE, AND THIS TOOK THE LIVE BOT DOWN ON 2026-08-13.** `alerts.py` grew a module-level
`from backtest.setups import FILLED`; `bridge.py` imports `alerts` and `runner.py` imports
`bridge`, all before `_bind_code()` binds the frozen snapshot. Every start died with
`Cannot freeze this deployment: … was already imported from the repo before the snapshot was
bound`, exit 2, uptime 1 second, on a ~60s watchdog loop until the import moved into its function.

✅ **The guard worked exactly as designed** — it named the module, named the cause and said what
to do, and it refused to run rather than silently half-applying the freeze. ⚠ **What it could not
do is fire before the code reached a live bot**: `is_frozen` is false in every test and every dry
run, so the ONLY configuration that trips it is the one with real money behind it.
`_bind_code`'s docstring said *"Nothing in `algos/live/` imports these at module scope
(checked)"* — checked by a human, once, and no longer true by the time it mattered.
**`tests/test_no_frozen_imports_at_module_scope.py` now imports each entry module in a SUBPROCESS
and fails by name**, so this fails in the suite instead of on the box. **The fix is always to move
the import inside the function, never to add an allow-list.**

⚠ **`setup_alert_categories` distinguishes ABSENT from EMPTY.** Absent = all four; `[]` = the
reader switched them all off. Collapsing them would make a config typo look deliberate.

🔴 **The resting-limit message waits for `snap.announce_resting`, and the CHECK ORDER is the whole
point.** It is tested BEFORE `_sent` is marked — marking first would burn the setup's one
resting-message slot on a bar the message was suppressed, so the announcement would never arrive.
Same bookkeeping-before-the-guard trap the `tradeable` check beside it is written to avoid, and
silent in the same way. ⚠ **The STRATEGY owns when a resting order is worth announcing**
(`backtest/setups.py`); this layer has no price and must never learn what a fib is. Aaron, on a live
message: *"I only want to know a limit is pending when price gets back to 23.6% of the
retracement."*

⚠ **A setup the strategy has already refused is never announced** (`SetupSnapshot.tradeable`) —
Aaron's rule: *"I should only be getting signals for the trades originating from my default
settings."* The guard is checked BEFORE any bookkeeping, so a suppressed setup leaves no thread
entry behind and can still be announced later if it becomes tradeable.

✅ **The paired invariant — every trade in the TRADES room originated from a thread in the SIGNALS
room — is CHECKED, by `backtest/tools/alert_rate.py`, not asserted.** 159 trades closed, 158
announced as ENTERED over 6.5 years; the one gap is the warm-up boundary. **Re-run it after any
entry-logic change**, because that check is how the `tradeable` filter fails: suppress one setup
too many and a real trade arrives in the trades group having never been signalled, with nothing
anywhere reporting a skipped message.

**The credential is `telegram_signal_chat`** (`algos/credentials.json`, git-ignored, per machine;
env `LWG_TELEGRAM_SIGNAL_CHAT`). ⚠ **Aaron's group is a BASIC group, not a supergroup** — id
`-5572666026`, no `-100` prefix. **Telegram silently CHANGES that id if the group is ever upgraded
to a supergroup** (which happens on its own when enough members join, or it is made public), and
the sends then fail into the log rather than erroring anywhere visible. A signals channel that has
gone quiet for days is that, until proven otherwise.

### A deploy is ONE event — its three messages are now a THREAD (2026-08-14)

Aaron: *"Look at the messages every time I promote also; can this be a thread instead of
individual messages?"* A promote produces **STOPPED, PROMOTED and ONLINE** — and the middle one
comes from the command center on a laptop while the other two come from this bot on the VPS, so
they arrived as three unrelated bubbles with nothing saying they were one action.

The command center sends the PROMOTED **root**, then writes its Telegram message id into
`<instance>/alert_thread.json`. `runner.py` reads it and REPLIES with STOPPED and ONLINE. The
instance directory is the channel those two processes already share (`stop.request`,
`bot_state.json`, `review.json`), so nothing new had to exist to carry it.

🔴 **The one way this could be WORSE than not threading is a STALE id**, and it is the
`stop.request` hazard exactly: a file in an instance directory that outlives what it describes.
There a leftover request stopped a healthy bot; here a leftover id quietly parents every future
lifecycle message under an ancient deploy — in the channel whose whole job is saying what is
happening NOW. **Two guards and neither alone is enough:**

* an **EXPIRY** (15 min, written by the sender) covers a restart that never completed, where
  nobody is left to delete the file. A record with no expiry at all is ignored — defaulting that
  field to *forever* would make the missing value the most dangerous one in the file;
* the **ONLINE alert CONSUMES it**, covering a bot that restarts twice inside the window.

⚠ **STOPPED must NOT consume it** — the ONLINE that follows a promote is sent by a DIFFERENT
PROCESS, so deleting the file there orphans the message the reader is actually waiting for.
Pinned by a test that READS `runner.py` and counts call sites, because the behavioural version
of that check was **measured vacuous**: adding `clear_alert_thread()` beside the STOPPED alert
left every test green.

⚠ **Only the two lifecycle messages a promote causes are threaded** (`_notify_health(...,
thread=True)`). Threading everything would file an unrelated 3am reconnect under that morning's
deploy.

⚠ **Every failure answers "no thread"**, which is the behaviour every bot had before this
existed — a missing file, an unreadable one, an expired one, a message id of 0. A notifier
convenience must never be able to cost a lifecycle message.

⚠ **The ROOT is sent BEFORE the bot is stopped**, and the ordering is the feature: this bot
writes STOPPED the moment it notices its stop file, seconds later, and a root sent afterwards is
not the root of anything. So the root states the INTENT (*"Restarting it now"*) and the two
replies report what happened.

### The version a bot reports — it was `v0` for the life of the field (2026-08-14)

🔴 **`LiveConfig.strategy_version` was declared `int = 0` and NOTHING assigned it**, so every
bot's ONLINE banner read `v0 (e4137dbb)` on every start, and so did the log banner, the ledger's
startup record and `bot_state.json`. Aaron, off the health channel: *"the last message say V0? Is
it missing the version deployed."* **A declared field with a default is indistinguishable from a
measurement** — the same defect as `running=False` in the lab and `is_compiled` defaulting to 1.

**`algos/tools/promote.py::version_at` measures it and stamps it into `deployed.json`** (which
overrides `config.json` for the version fields, as `promoted_commit` already did). A version is
the **count of commits touching this bot's PROMOTED trees**, derived from `repo_trees` — the same
function that decides what is COPIED, so a tree that deploys is a tree that counts. It moves when
and only when the code this bot runs moves, and subtracting two of them is the work between two
deployments.

⚠ **`None`, never 0, and it renders `v?` through the single `LiveConfig.version_label`.** 0 is a
version somebody could genuinely be on, and it is precisely the value that was lying. Four
readers share that one rendering because `f"v{None}"` prints `vNone` in every one of them.

⚠ **The count is stamped at PROMOTE time and that is the whole point.** `command-center`'s
`bot_versions.version_at` runs the same command over the same trees, so the two agree by
construction rather than by being kept in step — the difference is WHEN. The bot has no git and
no backend; the stamp is what lets it state its own version.

⚠ **A bot promoted before this has no stamp and reads `v?`** until its next promote. That is the
honest answer, and it is why nothing back-fills a number onto a deployment nobody measured.

⚠ **`promote.py` also prints `##VERSIONS <from> <to>`** — a machine-readable line for the caller
that has to put those in a message, parsed and stripped by the command center's promote route.
The prose line beside it is for a human; **scraping the prose is what the OK/FAIL markers already
exist to avoid**, and a reworded `print` must not change what anything reads.

### One shape for every message — `shared/alert_format.py`

**Aaron's brief, 2026-08-05, after picking from rendered samples in the health chat:** concise, but
never so concise you cannot diagnose it; facts that belong together on one line, facts that do not
on the next; and it must be obvious what to act on.

    <icon> <LABEL> · <subject>
    <the facts, grouped>
    <what to do about it>

Every sender in the repo renders through `alert()` — the runner's twelve, the bridge's three, the
watchdog's nine, the reviewer's findings, the Telegram bot's ping, and the command center's ten
through its own mirror. Before this they were five different voices, and each buried the actionable
part somewhere different.

⚠ **The LABEL is the whole message in two words**, because that is what a lock screen shows. It names
the STATE, not the event: `WILL NOT START` rather than `CRITICAL`, because the first says what is
true now. A test caps the header at 45 characters.

⚠ **A health message ends with the consequence, and "Nothing to do" counts as one.** `RECONNECTED …
Nothing to do` is the difference between a glance and an investigation at 3am. The old messages
stated a fact and left the reader to work out whether it mattered.

⚠ **NO TIMESTAMP on a message about now.** Telegram already prints the send time in each reader's own
local clock, directly above the message, and a bot cannot do better — it sends one string to a group
and cannot know where anyone is reading it. A second clock in UTC beside Telegram's local one invites
the reader to reconcile two times for one event. **The one exception is a message about the PAST** —
the hourly reviewer at 21:20 reporting a restart at 18:06 — and `alert_format.when()` renders that in
the box's clock *with the zone named*, because the ledger and the logs are UTC and a bare "6:06" is an
hour of arithmetic away from the record it points at.

⚠ **`log_review._ts` and `_at` are deliberately separate.** `_ts` builds the dedup KEY and `_at`
renders for a human. They were one function, and changing its output would have re-announced every
outstanding finding exactly once — so the wording can never be improved without waking the channel up
unless the two are split. **Cashed in on 2026-08-13**: `when()` gained a date and not one outstanding
finding re-announced.

🔴 **`when()` prints the DATE once the moment is not today, and today still renders bare.** The
reviewer looks back TWO days and fires its findings in one hourly burst, so a bare "11:12 AM CDT" put
yesterday's events and this afternoon's in the same block with nothing to tell them apart — nine
messages at once, five of them from the day before, all correct and all misread. ⚠ **"Another day" is
decided in the READING zone, never in UTC**: they disagree for five hours out of twenty-four, and
stamping an 8pm Chicago event with tomorrow's date is worse than the bare time it replaced.
Story: `docs/ALGOS_BUILD_NOTES.md` → *The burst of nine*.

⚠ **The entry states the risk; the exit does not restate it.** The exit posts as a Telegram reply to
the entry, so "on $200.00 risked" there repeats what is one tap above (Aaron's call). That makes the
ENTRY the only place it is said, which is what `test_the_entry_states_the_risk_because_the_exit_will_not`
exists to protect. **"Risking", never "losing if stopped"** — a gap can fill worse than the stop.

⚠ **The stop distance in pips is gone, and `pip_size` with it.** 1,725 pips on gold answered a
question nobody asks; `Entry 3,290.00 · Stop 3,280.00` says the same thing in the reader's units.

⚠ **`_VERDICT_LABEL` renders `LOSS` while `verdict()` still returns `LOSE`.** The bridge, the ledger
and the tests compare against the value; the label is what a human reads. Merging them would make a
wording change a behaviour change.

🔴 **`when()` shipped with `%-I` and crashed `log_review.py` on its first run on the VPS**, against a
fully green suite on the Mac. `%-I` strips the leading zero on glibc and macOS; on Windows it raises
`ValueError: Invalid format string` (the equivalent there is `%#I`). It formats with the portable
`%I` and strips the zero in Python now. ⚠ **This is the SECOND Windows-only crash in two days to
reach a scheduled task through a passing test run**, the first being cp1252 in this same module — so
the rule is now general: **anything that runs on the VPS is running on a platform the tests are not,
and `strftime`, console encoding and path separators are where that shows up.** Run it on the box.

⚠ **`command-center/backend/services/alert_format.py` is a MIRROR**, for the same boundary reason as
the routing table. `algos/tests/test_alert_format.py` loads it BY PATH and asserts both that the
contract strings match and that the two render byte-identical output on the cases where hand-written
copies diverge first — an absent fact and a whitespace-only one.

### The Telegram bot lost six commands, because none of them could do anything

🔴 **`/restart` and `/stop` asked you to confirm, acted on an EMPTY LIST, and reported success.**
`BOTS` and `TASK_NAMES` had been `{}` since the four first-attempt bots were deleted on 2026-06-22 —
the same empty-registry rot that made `pnl_tracker.py` and `reporter.py` deletable. Aaron asked which
commands were still in use; the answer was that six of them could not have worked.

| gone | why it could not work |
|---|---|
| `/restart`, `/stop` | iterated `BOTS` / `TASK_NAMES`, both empty — **and reported success** |
| `/emergency` | same empty registry |
| `/trades` | read a per-bot trades file `live/runner.py` has never written; always answered 0 |
| `/resume`, `/resetweek` | drove `day_locked` and the weekly counters, written by the deleted `pnl_tracker.py` |
| `/confirm` | nothing can create a pending action once the control commands are gone |

⚠ **`/confirm` is the subtle one.** It works perfectly and can only ever reply "No pending action" —
which is the same defect as the others, one level quieter. A command that cannot do its job is not
harmless just because it fails honestly.

⚠ **Control lives in the command center, and that is not an admission of laziness.** The Bots page can
see how many copies of a bot are running; a phone command cannot. The guard against creating a
duplicate bot had to live with the PROCESS (`startup_coordinator.py`, 2026-08-04) precisely because a
confirmation step cannot make an uncounted start safe.

🔴 **`/status` was itself broken and is now wired to something that cannot go stale.** It looped over a
`BOT_SCRIPTS = {}` literal declared two lines above the loop, so it printed a "Trading Bots" heading
with nothing under it. It reads `bot_state.read_all()` now — written by the runner every poll — so a
bot appears by RUNNING. It reports the process, the heartbeat and the MT5 link as THREE facts, because
a bot can be alive and blind.

🔴 **`telegram_bot.py` was not importable on a Mac at all** (`str | None`, which needs 3.10; the VPS
runs 3.11). It had no tests, and that is why: **a module nothing imports cannot be tested, and nothing
says so.** 30 tests now, 27 of them watched RED against HEAD.

**ARMED 2026-08-05** — `telegram_health_chat` is set on the VPS to the "LWG Captial Bot Health"
group, proven by a `--all` run reporting 2 findings into it. ⚠ **Getting a group's chat id took four
failed attempts and both causes are worth writing down, because the symptom of each is an EMPTY
`getUpdates` and they are indistinguishable from outside.** (1) **BotFather privacy mode is ON**
(`getMe` → `can_read_all_group_messages: false`), so the bot never receives a plain group message —
only a SLASH COMMAND or an @mention — and the update you are waiting for was never delivered rather
than lost. (2) **The running Telegram bot long-polls with an offset, which DELETES each update as it
confirms it**, so a message sent while it is alive is gone before you can read it; killing it is not
enough either, because `SYS_MONITOR` restarts it inside ~60s and eats the next one too. The sequence
that works: `schtasks /change /tn SYS_TELEGRAM /disable`, terminate the process by scoped commandline,
send `/status` in the group, read `chat.id`, then re-enable and `schtasks /run`. ⚠ **Re-enable it** —
disabling that task silences every fill alert on the box, and nothing else reports that it is off.
⚠ **Read `getUpdates` WITHOUT an `offset` parameter while diagnosing**: passing one confirms the
updates and destroys the evidence you are hunting for.

🔴 **Its first real run on the VPS crashed while PRINTING a finding.** A Windows console is cp1252
and cannot encode the arrows, dashes and icons a finding is written with, and Python does not
degrade — it raises `UnicodeEncodeError`. So a scheduled task that detects a halted bridge dies on
its way to telling you. `live/runner._make_logger` carries the identical fix for the identical
reason, so this is now a rule for **anything that prints on that box**: reconfigure stdout/stderr to
UTF-8 with `errors="replace"`, because an unencodable character must cost a glyph, never the message.
⚠ **It was found by RUNNING it, not by reading it** — the module's own tests all passed on the Mac.

Tests: `tests/test_log_review.py` (23), weighted toward the ways a checker wrongly says "fine" — the
same reason `test_deadman.py` is. **A bug in this module is silent by construction: every other alarm
here fails loudly and gets reported, this one fails by having nothing to say, and having nothing to
say is also what a healthy day looks like.**

### Registering a bot — the five registries, and the crash if you miss one

**2026-07-31: `mpc_sos_fade_demo` is registered.** It is the first bot in the rebuilt suite. Five
registries had to be filled and they are not optional — `bot_state.set_started()` does
`BOT_ACCOUNTS[key]` unguarded and `algos/live/runner.py` calls it at the top of its loop, so a bot
missing from ONE of them connects to MT5, warms 5,000 bars, and then dies on a bare `KeyError`:

| File | What it registers |
|---|---|
| `shared/bot_state.py` | `BOT_INSTANCES` / `BOT_ACCOUNTS` / `BOT_NAMES` — the state file, account, display name |
| `bots/startup_coordinator.py` | `STARTUP_SEQUENCE` — how it boots, and the log line that means "connected" |
| `notifications/monitor.py` | `BOTS` — liveness watch (inert while SYS_MONITOR is disabled) |
| `notifications/deadman.py` | `BOTS` — what the external dead-man's switch requires to be healthy. A bot missed here is never watched by the one alert that survives the box, and nothing errors — a test cross-checks it against the coordinator and the monitor |
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

## Live-path rules rescued from the moved narrative (2026-08-12)

**These were BURIED in the diary that now lives in `algos/docs/ALGOS_BUILD_NOTES.md` — 91,060 bytes across seven paragraphs, the largest 36,137 bytes on ONE line.** They are live-trading safety rules, and a safety rule nobody can find is not a safety rule. Each one's evidence is in the notes.

- **A safety device must never make a trading decision.** The fleet kill switch stops NEW ORDERS across the box; it does not flatten a book, because flattening is a trade. Same reasoning bounds every future guard.
- **Cannot-read HALTS** — deliberately the opposite default from `stop.request` — **and it LATCHES.** Clearing the flag does not resume trading; the bots must be restarted. A terminal flipping between logins therefore cannot toggle a live book unattended.
- **`Path.exists()` cannot be used to read the halt flag, and using it is the trap** — it answers `False` for *no flag* and for *cannot read the disk*, collapsing the very distinction the halt exists to protect. Read it in a way that can tell the two apart.
- **A magic number is only ever compared WITHIN one account.** An unchanged magic across an account move is correct, not a bug.
- **A restored stop that DIFFERS from the recorded one is never adopted.** Restore is deliberately strictly narrower than the halt it replaces — that narrowness is the safety property, not a limitation to widen later.
- **Stops are compared against the symbol's POINT, never for exact equality.**
- **Two failures must never share one message.** The tool written to end guesswork had itself merged *the tick never arrived* with *the sampler could not ask* — this repo's own no-vs-cannot-ask rule, broken inside its own diagnostic.
- **`mpc_bleg_demo` MUST NOT be assigned to an account yet**, and its config says so in `_NOT_VALIDATED`. See `docs/LIVE_TRADING_PIPELINE.md` → G15.
- **An unmeasured spread cannot pick an account.** Swap is identical across all three PU Prime tiers (measured on each), and the Prime↔ECN replay gap of 1.16R sits far inside this strategy's run-to-run sd of 15.06R. The ECN case is "strictly cheaper at identical everything else" — never a claim that the number moved.

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
