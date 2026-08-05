# CLAUDE.md — LWG Capital Algo Trading Suite

**Purpose:** Standing instructions for the XAUUSD/forex MT5 bot suite running on the Windows VPS.
**Scope:** This covers the bots, shared utilities, risk rules, scheduler, and deploy for `algos/`. It does NOT cover `command-center/`, `smart-money/`, or `engines/regime/` internals (regime is imported via the `shared_regime.py` shim).
**Status:** Active — no live bots yet; all four first-attempt bots were deleted 2026-06-22 to rebuild backtest-first. Deployment plumbing preserved, and the live-trading pipeline for the first Python strategy is now being built (`docs/LIVE_TRADING_PIPELINE.md`).
**Last reviewed:** 2026-08-05 — ✅ **THE LIVE BOT'S MINIMUM-STOP FLOOR IS 0.08, NOT 0.10 — CORRECTED THE SAME DAY, AND THE CORRECTION IS THE POINT.** It was shipped at `"% of price"` 0.10 hours earlier on the strength of a parity run and a doc note, and **Aaron asked what it actually cost.** Swept: 23 configs over 186,220 M15 bars (2018-09-13 → 2026-08-04), one real replay each. **0.10 costs 7 trades and 1.84R** (183 / +134.75R → 176 / +132.92R); **0.08 GAINS 2.00R** (181 / +136.75R). So the value that shipped was the wrong side of the optimum, and nothing in the parity gate could have said so — **a parity gate proves the two implementations agree about a setting, never that the setting is a good one.** Now `"% of price"` 0.08 in the instance config, the strategy default, both A+ Pine files and the instance template, promoted and restarted. ⚠ **A small floor GAINS R mechanically, not luckily: the three tightest stops in 7.9 years ($1.03 / $1.06 / $1.18) were all full −1.00R losers**, and `Fixed $` 1.25 refuses exactly those three for exactly +3.00R. Median stop distance is $8.88, so these are genuine outliers. ⚠ **Do NOT read +2R as an edge** — the jitter audit put this strategy's run-to-run spread at **sd 15.06R**, so 0.05 through 0.08 are indistinguishable; 0.08 is the HIGHEST value that does not start costing, i.e. the most protection for nothing. **A safety choice.** ⚠ **`x ATR(14)` was measured and REJECTED, against intuition** — it adapts to volatility and was cheapest on R, but at 0.35/0.40 it never refuses the $1.03 stop, because that bar was quiet and $1.03 was not tight *relative to ATR*. **The hazard is `qty = risk / stop_distance`: pure price units, volatility nowhere in it.** ⚠ **Also corrected here: `_exec_risk_pct` in the instance config still read "DECISION PENDING … harmless while the bot is in dry run".** Both halves went stale the moment the bot was armed the same day. **A comment claiming a live bot is not trading is worse than no comment**, and this file is the first thing anyone reads before touching the bot. Earlier the same day: ✅ **THE MINIMUM-STOP GUARD WAS SWITCHED ON IN THE LIVE BOT (`"% of price"` 0.10 at the time), AND IT TOOK TWO EXPORTS BECAUSE THE FIRST GATE WAS GREEN ON A BRANCH NEITHER SIDE ENTERED.** This is the last open item on the money hazard (G6/Step 1) and it is now closed. `compare_strategy.py` is **exit 0 at warmups 100 / 500 / 1000 / 2000** on a 21,899-bar `VANTAGE_XAUUSD, 15m` export taken with the guard enabled at `"% of price"` 0.30, and **block code 7 ("Stop too tight") fires 213 times in that window** — 49 long, 164 short. 🔴 **The first export was ALSO green at three warmups and proved nothing.** Its config columns read `cfg_min_stop = 2`, which is **`"Fixed $"`, not `"% of price"`** — a **ten-cent** floor on a $4,000 instrument — and **code 7 appeared ZERO times in 21,897 bars**, with the tightest filled stop at $6.76, 67× the floor in force. **The standing lesson is aimed at this repo's own gates: a green parity run says the two implementations AGREE, never that either is RIGHT — and it cannot say even that about a branch neither one entered. Before trusting a gate on a feature, check the feature was EXERCISED**, which here is a one-line block-code histogram over the export. ⚠ **Parity was proven at 0.30 and the live config ships 0.10** — same code path, same `px * val / 100` floor, same refusal, same block code, only the constant differs; say it that way rather than claiming 0.10 was itself diffed. ⚠ **It CHANGES which trades the bot takes** versus every result measured at `"Off"`, the 161-trade / +135.94R baseline included. ⚠ **It does not replace the two independent backstops** — the broker's own 20-point `SYMBOL_TRADE_STOPS_LEVEL` and `place_pending_limit`'s own refusal — but it is the only one acting on OUR side of the wire, which is where `qty = risk / stop_distance` is computed and therefore the only place a collapsed stop can be stopped from SIZING a position. Earlier the same day: 🟢 **THE BOT IS ARMED. `--live` IS IN `STARTUP_SEQUENCE`, AND THE FIRST TRADE WOULD HAVE RECORDED A P&L THAT DISAGREED WITH THE ACCOUNT BALANCE.** Aaron's call, on the $2,000 PU Prime **DEMO** account. The reason is the one dry run could not serve: **the bot ran three days and 274 bars and never armed a single setup** — every bar `long_armed`/`short_armed` false, stage never above 1, block code 7 never raised — which is not a fault, it is what **~2 trades a month** looks like over three days. Watching it decide nothing teaches nothing, and G5 (*PU Prime's spread, swap, commission and minimum stop distance are assumed, never measured*) cannot be answered by any amount of watching. ⚠ **The flag went in `STARTUP_SEQUENCE`'s argv because that tuple is the SINGLE SOURCE for all three start paths** — SYS_STARTUP at boot, the SYS_MONITOR watchdog restarting a dead bot, and the command center's Start/Restart buttons (via `--bot` single mode). Arming any one caller would mean **a watchdog restart silently returning a live bot to dry run**, which is worse than never arming it: the ledger keeps filling and nothing says the orders stopped. ⚠ **It follows that live is now this bot's DEFAULT on this box** — every automatic recovery brings it back armed, so disarming means deleting the flag and restarting, not stopping the process (the watchdog will simply undo that). 🔴 **The defect the arming exposed, found before the first order rather than after: `get_deal_result` returns MT5's `d.profit`, which is the PRICE MOVE ONLY, read off the CLOSING deal alone.** Swap was dropped entirely and commission — normally booked on the **ENTRY** deal, which that function never looks at — was never even fetched. So the very first live trade would have written a `pnl_usd` that quietly disagreed with the balance, under a field name giving no reader a reason to check. **This repo's signature defect once more: a number that is correct about a narrower question than the one being asked.** Fixed with a new `mt5_ops.get_deal_breakdown()` that sums **every deal of the position** and reports `gross_usd` / `swap_usd` / `commission_usd` / `net_usd` separately; the bridge writes all of them, and `pnl_usd` and the R are now NET, because a scratch that is +0.02R on price and negative after an overnight swap is a loss. ⚠ **The parts are kept rather than just the total, and that is the whole measurement** — a netted figure cannot be taken apart later, while gross + swap + commission can always be re-netted. ⚠ **Swap keeps MT5's OWN SIGN and is never `abs()`-ed**: gold's short swap is a real CREDIT (+26.98 points/night over the 6.5-year replay, where shorts were *paid* 2.14R while longs paid 8.55R), and the command center booked exactly that credit as a charge on 2026-08-03 with `-Math.abs(cost)` and overstated fees by 25%. **A cost field that cannot be positive cannot measure a broker that pays you.** ⚠ **`None` means the broker could not be ASKED; zero means it charged nothing** — `deals: 0` is what an unreachable terminal returns, and writing its zeros down would fabricate a measurement, which is worse than missing one because nothing downstream could tell. Same three-state rule as `mt5_link`. ⚠ **`get_deal_result` is deliberately UNCHANGED** (five callers unpack its 2-tuple) and its docstring now says the number is gross; the bridge calls the new method behind a `hasattr` so an older `mt5_ops`, or a test double, degrades to the old answer instead of raising out of an **exit** path — losing the cost breakdown is a bad day, losing the record that a trade closed is a much worse one. ⚠ **Entry fill vs intended price is repeated on the CLOSED row** even though it is already on the open one: joining the two by ticket works until a log rotation drops the open record, and a cost study that silently loses its oldest trades is worse than one that refuses to run. 16 new tests (`algos/tests/test_trade_costs.py`), weighted toward the ways a cost field is wrong while looking fine. Also fixed here: the 2026-08-05 `LOCAL_INSTANCES` → `LOCAL_ARCHIVE` rename had left `test_log_backup.py` erroring at setup on all 8 tests — **a rename that passes its own module and breaks its tests is invisible until somebody runs the suite.** 271 algos tests green. Earlier the same day: 🔴 **A BAR THAT RAISED WHILE BEING PROCESSED WAS SILENTLY DROPPED, AND EVERY MECHANISM THAT COULD HAVE CAUGHT IT WAS READING THE BOOKMARK THAT CAUSED IT.** Found by auditing the live ledger's three one-off `event` records — two turned out to be safety mechanisms working correctly (see below) and the third, a single `loop_error` on 2026-07-31, led here. `BarFeed.new_bars` advances `last_bar_time` when it HANDS THE ROWS OUT, not when the caller has finished with them, so an exception inside `_on_bar` left the bookmark past a bar the engines never saw. ✅ **Proven against the real `BarFeed`, not reasoned about: one fresh bar handed out, bookmark advanced, `gap_bars()` → 0, next `new_bars()` → empty.** 🔴 **Nothing could see it.** `gap_bars()` compares the newest broker bar against that same bookmark, so it read *up to date*; the next poll had nothing fresh to offer; and the outer handler only alerts after **TEN CONSECUTIVE** loop errors, while one lost bar is one error. **The engines are a streaming state machine, so a dropped bar is not a missing datapoint — every structure break, fib leg and gap after it is computed over a market history that never happened, for the rest of the session.** `new_bars`' own docstring says exactly that must not happen silently; the bookkeeping made it impossible to notice. ⚠ **RE-DELIVERING THE BAR IS DELIBERATELY NOT THE FIX, and this is the part to carry.** `_on_bar` steps the strategy and then mirrors its intent onto the broker, so a failure part-way through leaves the engines already advanced — replaying that bar would step them twice, which is the same desync from the other side. **Neither skipping nor retrying is safe, so the loop routes into the one recovery that is known-good and already built: the `gap > 4` branch's rebuild-and-re-warm.** ⚠ **It BREAKS out of the row loop rather than continuing** — the rows after the failure would otherwise be fed to engines already carrying the hole. ⚠ **A `bar_error` is its own ledger event, not another `loop_error`**: one is a poll that failed, the other is a data-integrity event, and an audit like this one cannot tell them apart if they share a name. The `rewarm` event now carries `after_bar_error` for the same reason — a re-warm after a 5-bar lag and one after a dropped bar look identical otherwise, and only one of them is a defect on our side. ⚠ **Alerts ONCE per outage** (the counter resets on the first clean bar) and **stops the bot after 10 unprocessable bars in a row** — a re-warm that is not fixing it will not start on the eleventh, and a bot silently processing nothing is worse than a stopped one, because the watchdog can see stopped. 14 tests (`algos/tests/test_bar_stream_holes.py`), most of them demonstrating the DROP against the real feed, because a fix for a bug nobody has reproduced is a fix for a guess. **The standing lesson is this repo's own arriving by a fourth route: the system recorded what it HANDED OUT as though it were what was PROCESSED** — the same shape as the bar cache recording the window it requested rather than the data it received, one layer up and inside the live loop. ✅ **The other two ledger events are CLOSED and were never defects.** The `config_change_refused` (2026-07-31 04:26) and `version_mismatch` (2026-08-04 01:10) are the version pin doing precisely its job — refusing to run code that was never promoted. **All three predate their own fixes, proven by commit ancestry rather than assumed**: the bot was launched from `1eaf5fd`, and the `Execution.cfg` property that would have prevented the `loop_error` landed in `5c53b0d` **13 minutes later**; the restart at 04:27 ran `7584380`, which contains it, and the identical operation then succeeded **twice** (`config_applied`, 04:30 and 04:31). The `version_mismatch` predates the frozen-`deployed/` snapshot by 38 minutes. Nothing outstanding from any of the three. **Same day, the ledger backup was fixed in a way that matters more than it reads: `ledger_sync.py` now commits to `algos/ledger_archive/`, NOT into the bot's own instance directory.** 🔴 **Committing a day into the live path BROKE `git pull` ON THE VPS** — the bot writes those files, so the box always holds its own untracked copy, and git correctly refuses to overwrite one (*"untracked working tree files would be overwritten by merge"*, pull aborted, measured). Every future pull would have needed a manual delete first, on the one machine that has to stay current for the watchdog, the dead-man's switch and the live loop. ⚠ **The rule, and `.gitignore` already stated it one paragraph up for `deployed/`: a file the VPS WRITES cannot also be a file git DELIVERS.** Two instances of one rule now; `algos/markets/fx/instances/*/ledger/` is ignored so a third cannot happen by hand. The archive MIRRORS the VPS layout (`<bot>/ledger/decisions-YYYY-MM-DD.jsonl`), so an archived file and its original differ only by the root — a hand `diff` stays trivial and the commit-msg hook's exemption pattern needed no change. ⚠ **Related and fixed the same day: the commit-msg hook had SILENTLY DISABLED this backup entirely** by classifying a `.jsonl` decision record as code and demanding a doc paragraph, so every unattended sync failed and a closed day sat on the VPS as the only copy — see the root `CLAUDE.md` → *Committing*. **A guardrail that fires on a robot's commit has no human to read its message: it does not nag, it stops the job.** Earlier: 2026-08-04 — 🟢 **THERE IS AN EXTERNAL DEAD-MAN'S SWITCH NOW (`SYS_DEADMAN`), AND IT IS THE ONLY ALERT IN THIS SUITE THAT SURVIVES THE BOX.** Every other one — the bot's own messages, `monitor.py`, the P&L tracker, the reporter — is sent BY the VPS, so the single failure nothing could report was the box or its network dying: that produces **silence**, and silence is what a healthy Sunday produces too. `notifications/deadman.py` inverts the direction. It checks each registered bot's **process, heartbeat freshness and `mt5_link`**, and pings an **off-box** service only when all of them are good; that service alerts when the pings stop. ⚠ **The ping is CONDITIONAL on health, and that is the whole design — it is the 2026-08-04 probe lesson stated from the other side.** An unconditional ping proves only that Task Scheduler is alive, so a healthy box and a bot that died an hour ago would send the identical green tick: **never trust a POSITIVE result a broken system can also produce**, exactly as you must not trust a negative one a healthy system can. ⚠ **TWO signals, because otherwise a dead bot and a dead box are the same silence**: a plain ping (missing ⇒ timeout alert, meaning *nothing on that box can talk to me*, and the far end genuinely does not know why) and **`<url>/fail` carrying the reasons** when the script runs and FINDS a fault — immediate, and named, instead of a silence you decode after the grace period. ⚠ **It restarts nothing.** `SYS_MONITOR` owns recovery; two independent things issuing starts for one bot is precisely how the duplicate below happened. ⚠ **It is a SEPARATE task from the watchdog on purpose** — the watchdog is the bigger program and the likelier to break, and a switch sharing its process shares its failure modes and stops being an independent check. ⚠ **Absence is never scored as health**: an unreadable `wmic`, an unreadable `bot_state.json` and a missing heartbeat field are each a FAILURE, not a quiet pass, and `mt5_link` is read `is False` and never falsy (`None` = UNASKED, the same three-state contract the Bots page follows). ⚠ **An UNCONFIGURED switch is a supported state** — no `deadman_url`, no send, exit 0 — because a task that fails every five minutes is one everybody learns to ignore, and then the real failure is ignored with it. ⚠ **The ping URL is a SECRET** (`deadman_url` in the git-ignored `credentials.json`; env `LWG_DEADMAN_URL`): whoever holds it can send your pings for you and hold the alert green forever, which is worse than having no switch because you would believe it. 21 tests (`algos/tests/test_deadman.py`), deliberately weighted toward the ways a check can wrongly say "fine" — **a bug in this module is silent by construction, so unlike every other watchdog here there is no user report coming.** Earlier the same day: 🔴 **`SYS_STARTUP` WAS NOT IDEMPOTENT: FIRING IT ON A HEALTHY BOX LEFT TWO COPIES OF THE TRADING BOT AND BOUNCED THE TELEGRAM BOT.** Found by RUNNING it to verify the Telegram fix below — which is the point: the Telegram half was proven and the worse half was sitting one level up, unmeasured. `startup_coordinator.py` launched every bot in `STARTUP_SEQUENCE` unconditionally, so **two `runner.py --bot mpc_sos_fade_demo` processes were left running four minutes apart with nothing anywhere reporting it.** ⚠ **Two copies of one bot is the worst duplicate in this system**: they share an account, a magic number and a strategy, so they see the same setup on the same bar and each sizes a FULL position off it — double the risk, from a state neither can see. `bridge` filters `get_open_positions()` by MAGIC, so each would find the other's position and read it as its own; `adopt_broker_state`'s HALT on an unknown position at startup is the only reason this is survivable. **Three guards, covering different paths:** the coordinator skips a bot already running on **BOTH** launch paths — full startup AND `--bot` single-bot mode, which was MISSED on the first pass and is the one the command center's Start button drives, i.e. the likeliest way anyone makes a duplicate (primary — and it avoids the false `offline` the alternative produces, since a second copy that exits immediately still starves `wait_for_connection` of its ready string), and **`runner.already_running()` refuses to be a second copy** (backstop for the command center, the watchdog, and a typed command). ⚠ **Both match on `--bot <key>`, never the script name** — every live bot IS `runner.py`, so the script identifies the FLEET and only the key identifies the bot; matching the script would stop a second, different bot from ever starting. The runner compares PIDs so it cannot mistake itself for a duplicate. ⚠ **The two guards default in OPPOSITE directions on an unreadable process list, deliberately.** The coordinator assumes RUNNING and leaves it alone (a duplicate bot is two positions); the runner assumes NOT running and starts ("cannot tell" must not become "refuse forever" for the process whose absence is silent). ✅ **Verified live: the task was fired again with both fixes in place and the box was unchanged — one bot (PID 8892), one Telegram (PID 12780), no new processes.** 208 algos tests green (6 new). **The standing lesson: a start command that is not idempotent is a duplicate generator, and every recovery path in this suite fires one.** Earlier the same day: 🔴 **THE TELEGRAM BOT WAS NEVER CRASHING. IT WAS BEING KILLED, AND ONE OF THE KILLERS WAS OUR OWN STARTUP SEQUENCE.** Aaron had watched it stop and come back for weeks and asked why. ✅ **Measured, not guessed: 4,764 Windows Application events over 14 days, none mentioning python, and no crash event (1000/1001/1026) since 26 July.** A `taskkill /f` leaves no event behind and a real fault does, so every "stop" was an external kill. Four kill paths, three fixed the day before without anyone realising they answered this question: the Telegram bot's own `/emergency` ran `taskkill /f /im python.exe` and **killed itself** (which is also why its confirmation reply never arrived), the command center's Stop button did the same, and three docs instructed the blanket kill by hand. **The fourth was the routine one and it was BY DESIGN:** `startup_coordinator.py` ended by launching `start_telegram.py` unconditionally, and that script's first act is `kill_existing()` — force-kill any running telegram_bot.py, sleep 2, start fresh. So **every Start/Restart from the Bots page, and every documented bot restart, killed the alert channel and rebuilt it**, after which SYS_MONITOR spotted the gap and sent 🟢 *Telegram Bot Restarted*. Fixed: `start_telegram_if_needed()` leaves a healthy Telegram alone. ⚠ **`SYS_TELEGRAM` deliberately KEEPS the force-restart** — that task exists to recover a bot that is alive but WEDGED, and it is what the watchdog fires (×3) when Telegram is genuinely down; the skip is about collateral damage from starting something else, and a test pins that `kill_existing` survives. ⚠ **An unreadable process list starts one rather than assuming it is up** — the safe direction is not symmetric: a second Telegram is refused by `telegram_bot.py`'s own singleton guard, a missing one is silence. ⚠ **The tests exec the launcher's real functions out of its AST** rather than importing it, because `startup_coordinator.py` hardcodes `C:/trading/algos` at module scope — the same trick `_coordinator_sequence` already used, so the check runs on the Mac where the mistake is actually made. 4 new tests, 202 algos tests green. **The standing lesson: an alert channel that cries wolf stops being read, so a routine event dressed as a failure costs exactly as much trust as a missed one — and "why does this keep restarting" deserves a measurement, not a shrug.** ⚠ **One blanket kill is still on disk on purpose**: `command-center/backend/tests/test_integration.py` runs `taskkill /f /im python.exe` on the VPS. It is excluded from every normal test run and documented in three places, but a bare `pytest tests/` still takes out the box. Earlier the same day: 🔴 **METATRADER RESTARTED ITSELF UNDER THE LIVE BOT AND THE BOT WENT BLIND FOR 50 MINUTES WITHOUT ONE INDICATOR CHANGING.** `C:\MT5_FFT\terminal64.exe` was rewritten at 02:57:53 UTC by an auto-update and the replacement process started two seconds later, taking the running bot's IPC handle with it. From the 02:30 bar onward it saw no market at all — across an open session, in which it would have taken no entry and managed no exit. ✅ **Proven rather than inferred: a separate read-only probe attached to the same terminal and got balance $2,000, live ticks at 4056.77 and fresh M15 bars, while the bot's own process was getting `None` from every call.** The terminal was healthy; only the bot's link was dead. 🔴 **The reason nothing caught it is the transferable part, and it is NOT this repo's usual label-vs-code refrain: every failure on the MT5 path returns an ABSENCE rather than raising.** `copy_rates_from_pos` → None → `get_candles` returns an empty frame (documented "never None", which is right for its callers and fatal here) → `BarFeed.new_bars` reads *no bar has closed* and `gap_bars` reads *no gap*; `account_info` → None → the heartbeat wrote a null balance. So the loop kept stamping, **SYS_MONITOR saw a healthy bot**, `wmic` still listed the process, the **Bots page said RUNNING**, and the log carried not one warning. **The only visible symptom in the entire system was a blank balance cell** — which is how it was found, by Aaron asking why. **Fixed:** `runner.probe_link()` asks `account_info()` FIRST, every poll; `_recover_link()` logs, alerts ONCE, retries on a 30s floor, and on reconnect **RE-WARMS** — an outage is a hole in the bar stream, i.e. the `gap_bars() > 4` condition arriving by another route, and resuming on the next bar would leave the engines carrying a market history that never happened. ⚠ **A bar-based probe cannot do this job and would have looked reasonable**: an empty frame is also what a QUIET MARKET produces, so such a check either cries wolf out of hours or treats a dead link as a quiet market forever — which is exactly how it shipped. `account_info()` answers whenever the link is alive, 3am Sunday or mid-session, so `None` means one thing. ⚠ **It deliberately does not reason about an open position** — if the broker holds one the rebuilt emulator does not, `OrderBridge._agrees` HALTS on the next bar, which is correct and already built; a second, less-tested answer to that question is how a restart doubles a book. ⚠ **`bot_state.json` gained `mt5_link` because a null balance is not a diagnosis**, and the Bots page renders it as a `No MT5 link` chip BESIDE the Running pill rather than replacing it: the process being ALIVE and being BLIND are both true and are different facts (alive ⇒ a restart is the fix and the watchdog was right not to fire). ⚠ **The heartbeat is still stamped while blind, on purpose** — dropping it would fire the stall alert, which means something else entirely. 12 new tests (`algos/tests/test_mt5_link.py`), 198 algos tests green; deployed and verified live (`mt5_link: true`, balance $2,000, bars current). **The standing lesson: before trusting a probe, ask whether a HEALTHY system can produce its negative result. If it can, it is not a probe.** Every layer here was individually defensible; the defect was that "no data" and "cannot ask" were the same value at every hop, so the distinction was destroyed at the bottom and unrecoverable above it. ✅ **CLOSED 2026-08-04 by `SYS_DEADMAN`** — see the header entry above. Earlier: 2026-08-02 — **no algos code changed; two cross-subsystem facts were recorded.** The MT5 agent's **`/status` is now a CONSUMED CONTRACT** — the command center reads `mt5_connected`/`account`/`server` from it to drive its MT5 health dot, because `/health` answers `ok` while the terminal is closed or logged out — and **both `MT5AgentRDP` and `NT8Agent` are now fired automatically** by a 60s supervisor loop on the Mac, which also re-probes after every `schtasks /run` (that command reports SUCCESS for a task Windows refuses to launch — the stored-password trap below). Both are written up under *Backtest data source*. Earlier: 2026-07-30 — **`algos/live/` landed: the live runtime for a `strategies/python/` bot on a named MT5 terminal** (see the section below and `docs/LIVE_TRADING_PIPELINE.md`), and `shared/mt5_ops.py` gained what it needs to drive one — pending/resting LIMIT orders (it could only send market orders, and the MPC strategies enter on a limit) plus the broker-clock fix on `get_candles`, which was labelling broker-server seconds as UTC and would have put every bar 2-3 hours out with a perfectly valid-looking timestamp. Also **credentials moved out of git.** The Telegram token was pasted into six files and committed; it has been revoked, and every copy is replaced by `shared/credentials.py`, which resolves env var → the git-ignored `algos/credentials.json` → empty. `credentials.template.json` (in git, values blank) is the setup path. Missing credentials are a no-op with one warning, never an exception. This is step 2 of `docs/LIVE_TRADING_PIPELINE.md`, the plan to take a validated `strategies/python/` bot to real orders on a named MT5 terminal — read it before touching anything under `bots/`, `shared/` or `notifications/`, because the pieces preserved from the deleted suite are about to get their first real consumer.

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
⚠ **A stale tick repeated for five minutes is NOT a rock-steady spread** — the sampler counts
repeats separately and reports no statistics at all when nothing fresh arrives, because a shut
market is otherwise the most confident-looking wrong answer it could give.
⚠ **It writes nothing.** `_measured` is a claim about when a reading was taken and by whom; a tool
silently rewriting it would make a fresh measurement indistinguishable from a stale one.

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

**`SYS_DEADMAN` is ON as of 2026-08-04** — every 5 minutes as SYSTEM, the external dead-man's
switch described in the header. It is the only alert here that does not originate on this box.
⚠ **It is INERT until `deadman_url` is set in `algos/credentials.json`** (deliberately: it reports
honestly and sends nothing rather than failing every five minutes). Check with
`deadman.py --status`, and treat an unset URL as an open gap rather than a configured switch.

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
