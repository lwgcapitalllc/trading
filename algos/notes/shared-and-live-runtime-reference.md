# Notes — Shared components and live runtime reference

The Shared Components file/role table and the full live/ live-runtime reference pulled out of the Fast Index. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

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
| `account_flows.py` | `shared/` | **What the account made NET OF DEPOSITS AND WITHDRAWALS**, off its whole deal history: money put in, what trading made, and the time-weighted return. Pure — no MT5, no I/O. **Refuses unless the deals rebuild the broker's balance to the cent.** See *A deposit is not a return* |
| `order_sizing.py` | `shared/` | **The one place a broker lot count is produced.** Pure, no MT5, no I/O: takes the strategy's intent + a `SymbolSpec` and returns a `SizedOrder` or a `SizingRefusal`. Instrument-agnostic — lots come from `(stop_distance / tick_size) x tick_value`, so gold, a JPY pair and an index are one arithmetic. **It refuses rather than rounding up, clamping down, or shrinking to fit.** Built after the 2026-08-07 oversizing incident; read its module docstring before touching sizing anywhere |
| `bot_state.py` | `shared/` | Single source of truth read/write for each instance's `bot_state.json` |
| `credentials.py` | `shared/` | **The one place secrets are resolved.** Env var → git-ignored `algos/credentials.json` → empty. Never holds a literal. Copy `algos/credentials.template.json` to set a machine up. **Any key resolves, not just the canonical three** — a per-bot secret needs a new entry in that file and nothing else; the env name is always `LWG_<KEY IN CAPS>` (`env_name()`). |
| `notify.py` | `shared/` | Telegram sender. `send_telegram(text, kind, chat_id="", token_key="")` — **`kind` is `TRADE` or `HEALTH` and is REQUIRED**; it picks the room (see `### Two rooms` below). `chat_id`/`token_key` are optional and empty = the shared destination for that kind and the shared bot, so routing is PER BOT without a second sender. `account_kind="live"` sends a trade or signal to the live rooms (`### The live rooms`). Reads `credentials.py`, never a hardcoded token, and NEVER raises — an unconfigured or unreachable notifier drops the message and prints once, because a notification channel must not be able to stop a trading loop. The four `notifications/` scripts now import their credentials from the same resolver instead of carrying inline copies (the 2026-07-06 refactor note, done 2026-07-30). |
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

1. **Only `live_config.RUNTIME_RELOADABLE` (a strategy param) and `RUNTIME_RELOADABLE_ACCOUNT` (the
   account cap, since 2026-09-11) are applied.** If anything else moved — a strategy param,
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

🔴 **THE CAP WAS COMPARED NOWHERE, SO A CAP-ONLY CHANGE WAS CONSUMED AS COSMETIC (fixed
2026-09-11).** `_config_delta` compared strategy params and nine identity fields; everything else fell
through `if not allowed:` and the mtime was consumed — the file said one cap, the bot ran another,
and nothing said so until a restart. Now `RUNTIME_RELOADABLE_ACCOUNT` is compared, handed to the
bridge (`set_account_risk_cap` — the room and the cap check read that field and nothing else) while
flat, and the new state is logged the way every start logs it (`_log_risk_cap`).
- ⚠ **No rebuild for a cap-only change** — nothing the strategy decides reads it.
- ⚠ **`None` is handed over as `None`** (uncapped), never 0, which would refuse every order.
- 🔴 **And every OTHER top-level field is BLOCKED now, never cosmetic** — the same defect one size
  wider: an edit to the margin safety, the sizing-basis adjustment or the alert routing read as saved
  while the bot ran the old value. A field `_config_delta` does not name is a restart the bot SAYS it
  needs (a catch-all over `dataclasses.fields`).
- ⚠ **The Command Center tells the reader a cap change needs no restart**, and a backend test reads
  this file to pin `RUNTIME_RELOADABLE_ACCOUNT` — change one, change both.
- ⚠ **A bot started on the older runner drops a cap-only change until it restarts once.** `algos/live/`
  reaches a bot on `git pull` + restart, no promote.

Tests: 8 more in `test_runtime_reload.py`, two watched RED against HEAD; 6 mutations, 6 killed.

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

**`tools/close_orphans.py` - close positions the bot did NOT choose, and record them as
MISTAKES rather than trades (2026-08-25).** Written the day five copies of one limit order
reached the broker. It keeps the ticket the bot wrote down for itself, closes every other
position under that bot's magic, and writes one `unmanaged_position_closed` record per ticket
into the decision ledger carrying `counts_as_strategy_performance: false`.

🔴 **The RECORDING is the tool, and the closing is the easy half.** Those tickets are in the
broker's deal history for good, so any study built off the statement will find them and score
them - and on the day it was written the four extras were **+$2,770 in front**, which is the
shape that gets kept. A windfall from a defect that nobody labels becomes evidence for the
strategy the next time somebody totals the account. The flag sits next to the ticket so a
reader joining on the statement cannot miss it.

⚠ **It decides from the ACCOUNT, never from a return code, and that is the whole design.** The
incident it cleans up happened because a request that TIMED OUT was read as a request that
FAILED. So after every close it re-reads the open positions and concludes from what the broker
actually holds; a ticket still open is reported and **never automatically retried**. A recovery
tool that repeats the fault it is recovering from is worse than no tool.

⚠ **It asserts the account before it touches anything** (same `attach()` shape as
`broker_facts.py`), it never looks past its own magic, and it refuses outright if the
`--keep` ticket is not open - so it cannot be talked into closing everything.
⚠ **Read-only unless BOTH `--close` and the exact `--confirm` phrase are given**, and the
phrase names the bot and the count. A speed bump against a slip, not a wall against intent.
⚠ **It is NOT a kill switch** - `tools/fleet_halt.py` is that.

**`tools/shadow_diff.py` — did the LIVE bot decide what the LAB says it should have?** Step 9.2 of
`docs/LIVE_TRADING_PIPELINE.md`. It joins the bot's own `bar` ledger stream to a lab replay of the
same window and diffs them field by field. The claim it checks is narrow and therefore useful:
`algos/live/` holds no trading logic, so the two run the same strategy object and **any difference
is data — a feed, a clock, or a warm-up — never logic.**

⚠ **Joined on bar TIMESTAMP, never on index.** The live index counts on from wherever warm-up
stopped and survives restarts; the lab's counts from the first row of whatever frame it was handed.
Two unrelated integers that look comparable — the trap `strategies/python/b_leg/CLAUDE.md`
records from the B-LEG harness, where 2,409 comparisons failed at one flat offset while the logic
was identical.

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
layered-cost tables in `strategies/python/sos_fade/CLAUDE.md` were all run on Vantage's $0.22 —
so the charged rows there understate this account.
✅ **SUPERSEDED 2026-08-06: `PROFILES` now carries $0.32** (re-measured over 1,893,438 ticks / 3
whole days), and it is stored per ACCOUNT TIER — `_SPREAD_XAUUSD_PUPRIME_STANDARD`, because this
demo is a Standard account and an unread tier refuses rather than borrowing it. **Do not quote the
$0.33 above as current**; it is kept because the paragraph is a dated record of that day's reading.
🔴 **AND SUPERSEDED AGAIN FOR THE ACCOUNT THIS BOT ACTUALLY TRADES: NONE OF THE NUMBERS IN THIS
PARAGRAPH BELONG TO IT.** Every figure above was read off a **Standard** account (`XAUUSD.s`); the
bot moved to the **ECN** demo 700152905 / `XAUUSD.p` on 2026-08-12, and that tier measured
**$0.12** on 2026-08-14 — 3,033,270 ticks over 5 whole days, all 23 traded hours, `broker_facts.py
--bot sos_fade_demo --history-days 6`. **2.7x tighter than anything written above.** The tier
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

**Backtest data source — pinned to MT5_Lab only (2026-07-22).** All backtest price/tick data comes from the MT5 agent (`markets/fx/tools/mt5_agent.py`, VPS port 8766). Its `_ensure_mt5()` binds the Python API to the **MT5_Lab** terminal64.exe *only* (`TERMINAL_PATH` / `MT5_DATA_DIR`, else the baked-in `C:\MT5_Lab` default); if a live bot terminal (MT5_FFT, etc.) is already attached it drops and re-binds, and if MT5_Lab can't be reached it FAILS loudly rather than silently reading the wrong account. This closed a real leak — the old code called `mt5.initialize()` with no path and grabbed whichever terminal answered first. 🔴 **NEVER QUOTE THE LAB'S BROKER OR ACCOUNT FROM A DOC — ASK THE BOX.** `curl -s http://localhost:8766/status` returns account, server and terminal path together. This line named a Vantage demo (25893735) for months while MT5_Lab was on **PU Prime demo 700152905** (measured 2026-09-07), and it read as settled fact the whole time. The pin is what matters and it has not changed: the agent binds MT5_Lab only, so whatever account that terminal holds is what every backtest is measured on. ⚠ The symbol suffix follows the account — `.p` here — so a run returning no bars is usually a suffix mismatch, not missing history. To pick up an agent-code change: `git pull` on the VPS **and** restart the `MT5AgentRDP` scheduled task (kill only the specific `mt5_agent.py` PID) — never a blanket `taskkill python.exe`, which also kills the NT8 backtest agent (`NT8Agent` task).

⚠ **`/symbols` (2026-09-07) is the only way to ASK what an account can actually trade.** Every other endpoint answers about a symbol name you already hold, so surveying the broker meant guessing names and probing them one at a time — and a name nobody thought of came back identical to an instrument the broker does not offer, which is *“no”* and *“cannot ask”* wearing the same face. It ENUMERATES instead: `curl "http://localhost:8766/symbols?tradable_only=1"`. It selects nothing into Market Watch, so it cannot change what the terminal is watching under a running backtest, and a terminal that cannot answer returns 502 rather than an empty list. ⚠ **Read `trade_mode` before putting anything in a portfolio** — a symbol can be quoted, charted and backtested while refusing a new position, and only one of those makes it a candidate.

⚠ **`/status` IS A CONSUMED CONTRACT AS OF 2026-08-02, not just a debug endpoint.** The command center's health strip reads `mt5_connected` / `account` / `server` from it to drive the MT5 dot's yellow state, because `/health` only proves Flask is alive — it answers `ok` while the terminal is closed or logged out, which showed a green dot over a disconnected MT5_Lab while every backtest needing uncached bars failed at fetch time. Renaming or dropping those three keys silently returns that dot to lying. Consumers: `command-center/backend/services/mt5_agent_client.status()` → `agent_supervisor.mt5_terminal_status()`.

⚠ **BOTH AGENT TASKS ARE NOW FIRED AUTOMATICALLY.** `command-center/backend/services/agent_supervisor.py` runs a 60s loop on Aaron's Mac that rebuilds the SSH tunnel and fires `MT5AgentRDP` / `NT8Agent` for whichever agent is not answering. Two consequences for VPS work: **(1)** killing an agent by hand to pick up a code change may see it restarted within a minute — stop the command-center backend first if you need it to stay down; **(2)** the loop **re-probes after every `schtasks /run`**, because that command reports SUCCESS for a task Windows refuses to launch (the stored-password trap below), so an agent that will not start is now reported rather than assumed healthy. It deliberately will **not** restart an agent whose lab job is still marked `running` — from the Mac, "dead" and "too loaded to answer `/health`" are indistinguishable, and the NT8 agent genuinely stops answering while driving a backtest under pywinauto.

Multi-instrument architecture (Phases 1–5) explained in `docs/ARCHITECTURE.md`.

## The stop-protection switch is runtime-reloadable, and that WIDENED the rule (2026-09-16)

`RUNTIME_RELOADABLE` held one name for its whole life — the risk share — on a stated principle:
only knobs that change HOW MUCH a bot risks may move under a running bot, never which trades it
takes, so the running bot stays comparable to the backtest that justified it. It now holds three.
The two new ones are the stop-protection switch (`exec_be_arm_r` on SOS Fade and B-Leg,
`use_breakeven` on the extreme-leg bot), and they change how a trade ENDS.

🔴 **THE EXCEPTION RESTS ON WHAT `_maybe_reload_runtime` ALREADY GUARANTEES, NOT ON THE CHANGE
BEING SMALL.** A reloadable change is applied ONLY while the bot is FLAT, by rebuilding the whole
strategy and replaying history into it, and it writes a ledger event. So no open position is ever
handed to rules that would not have opened it, and every trade still belongs to exactly one
configuration — which is the property the original sentence was protecting. A restart would add
only a re-check of `strategy_source_hash`, and that pins CODE; a value inside `strategy_params`
sits outside the pin whichever way it is written.

⚠ **They are two-state SWITCHES, not free numbers.** The Bots page offers off or on and nothing
else (`command-center/backend/services/bot_params.RUNTIME_SWITCHES` declares the exact pair). A
reader who wants some other arm multiple edits the instance config and restarts — the honest cost
of a value nothing has measured.

⚠ **THE TYPE IS LOAD-BEARING AND `True == 1` IS THE TRAP.** `runner._build_strategy` hands
`strategy_params` straight to the strategy's config class, so a bool written into the float arm —
or `1.0` written into the extreme-leg bot's boolean — is a bot that refuses to start, on a path
nobody exercises until the switch is flipped. The command center compares against the DECLARED
value's type, not a number cast out of it; `command-center/backend/tests/test_bot_switches.py`
pins it.

⚠ **A name a given bot's config does not carry is simply never seen for that bot.** This set is a
FILTER over what changed on disk, not a list of fields every bot must have.

⚠ **Both switches ship OFF and both are MEASURED LOSERS** — the numbers are in
`strategies/python/sos_fade/notes/reentry_ladder_mechanics.md` and
`strategies/python/extreme_leg/extreme_leg_optimization.md` (Run 2), and the page renders the
measurement beside the control. **Do not read this widening as the line moving.** A free-form
strategy number still goes lab → backtest → promote. What earned the exception is a two-state
switch whose both states are measured.
