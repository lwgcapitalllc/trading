## Communication Rules — Non-Negotiable

- Plain English only. Short sentences.
- Never use bullet points to explain a simple thing.
- No preamble. No "Great question." No "Sure, I can help with that."
- Spawn subagents for routine tasks. Work sequentially unless the task explicitly requires parallel execution.


# CLAUDE.md — LWG Capital Monorepo

**Purpose:** Standing instructions for Claude Code across all subsystems.
**Scope:** This covers repo-wide rules, VPS workflow, and branch conventions. It does NOT cover subsystem internals — each subsystem has its own CLAUDE.md.
**Status:** Active — four apps, ten canonical engines, and tooling in various stages of production.
**Last reviewed:** 2026-08-12 — see `HISTORY.md` for the working diary (what each pass found, measured and cost).

---

## The Rules

**Every one of these was learned by something breaking. The bracket is what it cost.**
They are short so they get read. The evidence behind each lives in `HISTORY.md`.

### Before you believe a number

1. **Never let "no" and "cannot ask" be the same value.** `None` means unasked, `0.0`/`False` means measured. Read `is False`, never falsy. *(A dead terminal read as a quiet market — bot blind 50 minutes, every dashboard green.)*
2. **Never trust a probe whose negative result a healthy system can also produce.** Ask what a healthy system returns before trusting the answer. *(Same incident. An empty bar frame is also a quiet Sunday.)*
3. **Never record what you REQUESTED as what you RECEIVED.** Clamp coverage to the data that came back. *(The bar cache claimed three days it did not hold, and served clean frames that stopped early.)*
4. **Never write a guessed number into a doc.** A plausible guess is a signpost, and a wrong one sends the next reader away from a one-command check. *(Cost three weeks — "the broker only has 35 days of 1m" was never measured and was false by eight years.)*
5. **Ask what a diagnostic is reporting ON** — the transport, the call, or the thing you did. *(`last_error()` printed "Success" on a rejected order.)*
6. **Compare R, never net dollars, across anything that shares a balance.** *(A shared stack read 2,266x the solo run on identical trades.)*

### Before you believe a feature works

7. **A label is a CLAIM about code somewhere else. Find the line that consumes it.** *(Six dead Telegram commands reported success. The Deploy button was dead eight days. The optimizer ranked on params the page never sent.)*
8. **Ask what a feature resolves THROUGH, and whether that registry is still populated.** An empty registry answers confidently and wrongly. *(Three separate jobs ran for weeks against `{}`.)*
9. **A feature nobody has RUN is not a feature.** Ask how many times it executed — and against which version of its engine. *(24 defects in one page that had never been driven end to end; a stress test graded A against an engine replaced three days later.)*
10. **A declared field is not an assigned one.** A model default is indistinguishable from a measurement. *(`running=False` told every python backtest its platform was free.)*
11. **Anything that recreates a run for COMPARISON must carry forward everything that decides what it is measured on** — window, costs, broker, sizing, per-leg params. *(Broken four times in this app. The difference column becomes the thing that lies.)*

### Before you believe a test

12. **A new test proves nothing until you have watched it go RED for the right reason.** If it cannot go red, prove it by mutation and say so in its docstring. *(At least eight vacuous tests have passed against their own bug here.)*
13. **A fixture more capable than production hides the defect.** If a test double answers something the real thing cannot, the test is describing a system you do not have. *(Four fixtures caught lying; one made a three-week-dead feature look tested.)*
14. **A green parity gate says the two implementations AGREE — never that either is RIGHT**, and says nothing at all about a branch neither one entered. *(The phantom-exit bug was faithfully ported and green for its whole life.)*

### Before you touch anything live

15. **Ask what a value's UNIT is on each side of a boundary, and which line converts it.** *(A 54.82-lot order on a $2,000 account. Ounces handed to MT5 as lots.)*
16. **A startup check establishes a fact that is then free to change.** Ask what could move afterwards and who would notice. *(The terminal switched accounts under a running bot; it re-anchored sizing to a stranger's balance for two hours.)*
17. **Refusing is the answer.** Never round up, clamp, or shrink to fit — a resized order is not the trade the strategy is holding. *(Below broker minimum, above maximum, and unaffordable all mean NO TRADE.)*
18. **Never `taskkill /f /im python.exe`** — it kills the bot, the Telegram bot and both agents. Kill one bot by its commandline. *(Killed the live bot for three days.)*

### Process

19. **The owning CLAUDE.md lands in the same commit as the code.** Enforced by hook. Never `--no-verify` — the honest skip is `DOCS: none - <reason>`.
20. **A strategy, engine or live change names its proof in the commit** (`MEASURED:` or `TESTED:`). Enforced by hook.
21. **Never build a second implementation of a canonical engine.** See *Never Do*.
22. **Never commit a new or changed engine before its `compare_*.py` gate has actually run and passed on a real export.**

### The skills that enforce these

Type these rather than trying to remember the list. They are in `.claude/commands/`.

| Command | Use it when | Rules it covers |
|---|---|---|
| `/spec` | before building anything non-trivial | catches "right code, wrong question" |
| `/wire-check` | before calling a feature done | 7, 8, 9, 10, 11 |
| `/prove` | after writing tests | 12, 13, 14 |
| `/measure` | before quoting any number | 3, 4, 6 |
| `/live-safety` | before anything under `algos/live/` | 1, 15, 16, 17, 18 |
| `/port` | new strategy from Pine to Python | 14, 22 |

---

## Trading Philosophy — read this before judging any strategy

**Recorded 2026-07-27, Aaron's standing design intent. This governs how every strategy in this repo is evaluated.**

**Few high-quality setups, not many mediocre ones.** A low trade count is the design target, not a defect. The whole point of a selective entry is that when it fires you can put real risk behind it. Chasing quantity means loosening the filter, and a loose filter is what blows an account in bad conditions or a black swan. A strategy that trades a couple of times a month and is right is worth more than one that trades weekly and is marginal.

**Sample size arrives at the PORTFOLIO level, not the strategy level.** Multiple strategies stack on one account. Each may trade 2–4 times a month; together they produce the trade frequency a single strategy is never asked to produce alone. So do NOT reject a strategy, or hedge every conclusion about it, on the grounds that "164 trades is a small sample." That objection has been raised and answered — stop re-raising it as a blocker.

**MEASURED 2026-07-29 (Run 12), and it cuts both ways: you may not buy trade count by loosening a strategy either.** Four ways of relaxing the A+ entry rule to add trades were replayed over 6.5 years and every one lost money or was noise. The reason is structural, not specific to A+: **with one position slot, an extra setup does not ADD to the book, it QUEUES in front of it** — the loosened runs displaced 17, 36 and 2 real trades respectively, and one displaced winner was worth +16.5R on its own. Corollary worth remembering before any future "let's take more setups" idea: **spending drawdown on SIZE beat spending it on FREQUENCY** — the shipped 164 trades at `exec_risk_pct = 12.5` made 832x at 64.2% max drawdown, while 337 loosened trades at half risk made 426x at 64.9%. So the honest routes to frequency stay the ones this section already names (another LEG, another instrument, another timeframe), not a looser filter.

Two things this does NOT excuse, and which must still be said plainly when they're true:

1. **A small sample still means wide error bars on that strategy's own edge.** Stacking five strategies does not make strategy A's edge more certain; it just spreads A's outcomes over more calendar time. Confidence in each edge is still earned per strategy. Say so when it matters — as a caveat on a number, never as a reason to refuse the work.
2. **Stacking only reduces drawdown if the strategies are actually independent.** Everything here reads the same `engines/market_structure/` on the same instrument. Two "different" strategies off one structure stream can fire together, lose together, and behave as one position at 2x the size. Correlation between strategies is a real open question in this repo, not a solved one.

**The suite is carved up by LEG, not by signal.** Aaron's answer to the correlation problem (2026-07-27): the strategies share a confluence source on purpose, but each takes a different part of the move — think Elliott waves. A+ SOS Fade catches the REVERSAL. The breakout-structure bot (not built yet) catches the LEGS IN BETWEEN. B-LEG catches SOS setups that take a long time to play out. By construction they should not be in the market on the same swing at the same time.

**Risk is budgeted per ACCOUNT, and never layered.** The intended rule: there is one risk pool (call it 10%, whatever the number lands on) available at any moment. Concurrent setups either SHARE that pool or the later one is BLOCKED outright. Risk is never stacked on top of risk. `exec_risk_pct = 10` is today a per-trade figure with no allocator above it — the account-level cap is UNBUILT and is a prerequisite for running more than one bot live. The Pine input's own ceiling was raised 10 → **100** on 2026-07-27 at Aaron's request (defaults unchanged at 10, and the Python side never had a cap), so nothing in the code now refuses a per-trade risk the account rule would.

**The overlap audit — RE-MEASURED 2026-08-09, and the design intent HELD MORE CLEANLY than at the first run.** "The legs don't overlap" was intent rather than fact for a year; `backtest/tools/overlap_audit.py` measures it, and on 155,531 M15 bars (2020 → 2026-08-03) **A+ and B-LEG held a position at the same time on 49 bars** — 0.5% of A+'s hold time — of which **exactly ONE was same-side** and 48 were opposite, i.e. partially hedged. The specific worry was the two firing on ONE structure break, and across 6.5 years there is now **NO** A+ trade with a same-direction B-LEG entry within 16 bars. Monthly R correlation +0.172 over 78 traded months. 🔴 **THE RE-RUN IS THE FINDING, NOT THE NUMBERS.** The 2026-08-04 audit was measured on a B-LEG that no longer exists: three of its defaults moved on 2026-08-06 (`bleg_max_days` 1.25 → 4.0, `exec_trail_pct` 1.0 → 0.05, `exec_time_stop_hrs` 36 → 8), which **doubled its trade count and tripled how long a frozen band lives**. The instruction to re-run was written down and nobody ran it, because the change landed in the B-LEG package and the verdict lived in `docs/LIVE_TRADING_PIPELINE.md`. **A cross-cutting measurement has to be re-run by whoever moves the inputs, not by whoever wrote the conclusion.** ⚠ **The absolute overlap went UP (27 → 49 bars) and the same-side overlap went DOWN (18 → 1), from the one change** — B-LEG holds longer so it shares more bars, and the bars it gained are opposite-side. Do not read the bigger number as a regression without reading the direction split under it. ⚠ **Re-run it after any entry-logic change on either bot** — this is a fact about today's config, not about the setups, which is why it is a tool and not a paragraph. ⚠ **It does not make the two independent**: both read one structure stream on one instrument, and being flat at different moments is not losing for different reasons. ⚠ **It does not retire the allocator** — the peak was still 2 concurrent positions, each sized off its own equity, so one account would have carried 2× `exec_risk_pct` on those bars. It says the allocator would rarely have had anything to arbitrate. 🟢 **And the thing that was recorded as blocking bot #2 is no longer true**: B-LEG at today's defaults is **99 trades / +17.87R** over the same 6.5 years, not the 50 / −0.94R the old entry quoted, with the drawdown down from −15.62R to −5.15R (charged, over the full history). It is a candidate again — see `docs/LIVE_TRADING_PIPELINE.md` → G15. ✅ **And the error bar it was missing now exists: `jitter_audit.py` ran on B-LEG for the first time (186,128 bars, ±$0.05 per bar, 12 seeds) and ALL TWELVE SEEDS FINISHED POSITIVE — min +21.63R, mean +26.33R, sd 2.61R, with the baseline sitting BELOW the jittered median.** In proportion that is the same feed sensitivity as A+ (11.2% of total against 10.6%), so the sign of this edge is not a feed artefact. ⚠ **A jitter audit is not an out-of-sample test** — it says the edge survives another broker's quotes, not that one tuning pass generalises. Still open: re-export and re-run `compare_bleg.py` at the new defaults, since every export on disk decodes the old ones.

**The BACKTEST side of the allocator was built 2026-08-09 and it re-states the same result through a second mechanism.** `backtest/portfolio/run_stack` replays both bots on ONE balance with ONE risk budget, and over 155,807 M15 bars at a 10% cap **it refused nothing** — peak open risk touched exactly 10.00% with both legs holding, and the contention log is empty, because risk is measured to each trade's CURRENT stop and A+ reaches breakeven in a median of one bar. ⚠ **The LIVE allocator is still unbuilt and cannot reuse that object** (separate OS processes; every MT5 read is magic-filtered), so "risk is budgeted per ACCOUNT" remains intent on the live side. See `docs/LIVE_TRADING_PIPELINE.md` → G10.

**It is drivable from the LAB as of the same day, and doing so refuted the plan's own success test.** A stack in `command-center/` is now either a **screen** (N standalone runs added together — every leg on its own full account, so nothing can block anything and it is an UPPER BOUND) or a **shared account**, and the page says which in the header before any number below it. 🔴 **`command-center/docs/SHARED_RISK_STACK.md` had stated that a shared run must close LOWER than the screen and that a higher one means the risk gate is not being enforced. The first real run closes $36,806 against the screen's $26,870 — HIGHER — with the cap working and nothing refused.** The prediction assumed refusals are the only difference between the two views; they are not. **A screen gives each leg a private balance and a shared account COMPOUNDS both onto one**, so the second leg sizes off a balance the first has grown — more money on the same trades, rather than less risk. Two effects in opposite directions, and the compounding one is unbounded while the refusal one is capped by how often the budget is genuinely full. ⚠ **So compare R, never net dollars**: the checks that say the gate is enforced are `peak_open_risk_pct <= risk_cap_pct` and every R difference tracing to a row in the contention log. **The standing lesson is about the criterion rather than the code: a verification test written before the thing exists is a prediction, and this one would have condemned a correct implementation.**

---

## Repo Structure

See `README.md` for the full repo map and subsystem list.

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. Engines under `engines/` are canonical shared libraries, and their dependency map is: `market_structure/` is the base and `fibonacci/` is its one downstream consumer (public `StructureSnapshot` only, never its internals). **`order_blocks/` was downstream too until 2026-07-31 and is now STANDALONE** — the mpc rework stopped creating blocks on structure breaks, so it takes plain OHLC and consumes no engine at all; `sessions/` is standalone and time-driven; `liquidity/` and `session_volume_profile/` compose `sessions/`; `vwap/` and `news/` are standalone and time-driven; `vwap/` and `session_volume_profile/` are the two engines that need the bar's **volume**; `fair_value_gaps/` is standalone and OHLC-driven (no upstream engine, no volume, no timestamp — pure price-pattern detection); `rsi_divergence/` is likewise standalone (needs close for Wilder's RSI + the bar's high/low for the price anchor — no upstream engine, no volume, no timestamp); `equal_highs_lows/` is likewise standalone (needs high/low/close for ATR(50) + strict price pivots — no upstream engine, no volume, no timestamp); `candlesticks/` is likewise standalone (needs OHLC only — no upstream engine, no volume, no timestamp — and is the only engine here ported from a THIRD-PARTY indicator rather than from `mpc_assistant.pine`). `engines/regime/` and `engines/market_structure/` are imported by `algos/` via thin shims in `algos/shared/`. **`command-center/` imports six directly** (bare-name, public API only, never a second implementation): `regime/` and `news/` for tagging and the news filter, and `market_structure/` + `fair_value_gaps/` + `equal_highs_lows/` + `order_blocks/` for the backtest PRICE CHART's overlay layers (`backend/services/structure_overlays.py`, `fvg_overlays.py`, `ob_overlays.py`). Those four are **display** consumers — no strategy reads them, so a change there moves what a chart shows and never a trade — but they are consumers, and an engine's own CLAUDE.md must say so rather than claiming nothing imports it. Every other engine gets its `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS strategy folders. Per-engine detail lives in each engine's CLAUDE.md — do not restate it here.

---

## System Summaries

### algos/
Automated trading on PU Prime demo accounts (Windows VPS via Task Scheduler). No live bots currently — the four first-attempt bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 to rebuild the suite backtest-first per `docs/BOT_DEVELOPMENT_METHOD.md`. Deployment learnings (MT5 connection, configs, scheduler, liveness layer) are preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md`. **CLEAN SLATE 2026-07-31 (Aaron's call): the suite starts from scratch — nothing before that date carries forward.** The VPS and the repo were leaned out: the four dead `shared_*` modules deleted (commit `e92304a`), and on the VPS a 36 MB pre-migration copy of the whole old suite, its backup, every stale task XML/log, the old bots' state files and all scratch. **There is no historical trade data anywhere.** A missing file is deliberate, not a bug — to recover anything use the commit hash via `algos/docs/DELETED_CODE.md`, never a rewrite from memory. Only the Telegram bot survives from the original suite. **The last two relics went 2026-08-05: `pnl_tracker.py` and `reporter.py` are DELETED** — they had been listed here as "disabled until a live bot is registered", but both carried an empty bot registry from the June deletion, so switching either on would have run a script that found no bots and exited. **Telegram is TWO rooms since 2026-08-05**: `telegram_chat_id` carries TRADES and nothing else, `telegram_health_chat` carries every message about the machinery — every sender in the repo states a `TRADE`/`HEALTH` kind and a test greps them all. Full rules in `algos/CLAUDE.md` → *Two rooms — every message declares its KIND* **Every message is also rendered by ONE formatter** (`shared/alert_format.py`) — icon, LABEL, subject, grouped facts, then what to act on, and no timestamp, because Telegram already prints the send time in the reader's own clock. **The Telegram bot answers four commands** (`/status`, `/balance`, `/help`, `/users`); the six control commands were deleted 2026-08-05 because their bot registry had been empty since June and two of them reported success on an empty list. **There is an ACCOUNT-level risk cap since 2026-08-09** — `shared/account_risk.py` + `mt5_ops.account_exposure()` + `bridge._account_cap_check`, the layer above `exec_risk_pct` that had never existed, reading the BROKER's real exposure across every magic rather than trusting any bot's own record. **Off by default (`account_risk_cap_pct: null`) and the runner says so at every start — but the LIVE BOT IS NO LONGER ON THAT DEFAULT: `mpc_sos_fade_demo` carries `10.0` since 2026-08-09 (Aaron's call), ahead of a second bot on the account.** ⚠ **That bot moved accounts on 2026-08-12** — it trades PU Prime **ECN 700152905 / `XAUUSD.p`**, not the Standard 700107749 / `XAUUSD.s` that most of this file's older entries name. The cap is a percentage so it travelled unchanged; the opening balance did not (the old account's growth stays on the old account). **Since the same day, a terminal logged into any other account HALTS the bot rather than being read as its own** — see `algos/CLAUDE.md` → *ACCOUNT MISMATCH*. ⚠ **10% equals that bot's own `exec_risk_pct`, so two bots do not share the budget — they take turns**, and a RESTING limit holds the whole budget while it waits, which `backtest/portfolio/` does not model (it reserves at the FILL). Expect more live contention than any stack backtest shows. Magic numbers are enforced unique per account in the same pass. **There is also a FLEET KILL SWITCH since 2026-08-09** — `shared/fleet_halt.py` + `tools/fleet_halt.py`, a flag file every bot re-reads each poll that stops NEW ORDERS across the whole box without closing anything or killing a process. **Cannot-read HALTS**, deliberately the opposite default from `stop.request`, and it LATCHES: clearing the flag does not resume trading, the bots must be restarted.

### smart-money/
Scans and profiles consistent crypto/forex traders for copy trading candidate pool construction. Runs locally on Mac. Stages 1–2 and 5 live; Stages 3–4 need API keys. Full rules in `smart-money/CLAUDE.md`.

### command-center/
React + FastAPI local operations platform. Monitors bots via SSH, runs and evaluates NinjaTrader, MT5, and local Python backtests. **The Smart Money UI is built and FLAGGED OFF since 2026-08-04** (`command-center/frontend/src/lib/features.ts`) — Aaron is auditing the app down to what he uses; nothing was deleted, the backend endpoints are still served, and one boolean restores the nav row, the routes and the Overview cards together. **Self-healing since 2026-08-02** — `backend/services/agent_supervisor.py` keeps the SSH tunnel and both VPS agents up on a 60s loop, guarded on the per-platform job lock, so starting it fresh and reopening a slept laptop are the same code path. **The Bots page was audited end to end 2026-08-05 and 14 defects fixed** — three of them destructive (a per-bot Stop that could kill the wrong process, a dead SSH rendering as "all bots stopped", an add-user that could delete every other user), plus two unused endpoints that **restarted a live trading bot**, now deleted. Two facts from it bind anything that touches this subsystem: **a bot is registered ONCE** (`routers/bots.py::BotReg` — there were nine parallel maps, and a missing entry answered confidently and wrongly, always in the safe-looking direction), and **a bot is addressed by its KEY, never its display name** (`BotStatus.key`; a name is a label and a rename would have broken every URL). **Since 2026-08-12 a broker ACCOUNT is a first-class row too** — `backend/services/bot_account_registry.py` over `algos/markets/fx/accounts.json` — so the Bots page has an **Accounts** tab that adds, edits and removes accounts and assigns bots to them. **That tab decides WHICH account a bot trades and Configure decides HOW it trades there**: one write moves the login, server, terminal, symbol suffix and risk cap together, and a RUNNING bot is refused. ⚠ **A stored MT5 password is write-only** — it goes to the VPS-only, git-ignored `algos/credentials.json` and no endpoint returns it. **The Tuning workbench was audited 2026-08-05 and 17 items fixed**, the load-bearing one being that it launched every iteration WITHOUT the baseline's `cost_layers`/`broker_profile`/`sizing_mode` — so tuning a charged run produced a child measured on a free book and put it in a table beside its own parent (proven with three real python runs: PF 1.499 charged vs 1.581 free on identical params and an identical 17 trades). **The rule it leaves behind binds every page in this app: a page whose whole job is COMPARING two runs must carry forward everything that decides what a run is measured on — the window, the costs, the broker, the sizing — or its own difference column becomes the thing that lies.** **The News Calendar was audited 2026-08-05 and 10 defects fixed**, the load-bearing one being that the beat/miss polarity list had been written against **Forex Factory's** naming while the tab reads **TradingView** — six of eleven keys matched none of 811 real titles, and `Core PCE Price Index MoM` (HIGH, USD) was therefore coloured the opposite way to CPI on the same screen. **The guard it leaves behind is the transferable part: a key that matches nothing now fails the build**, because a list of magic strings matched against another system's vocabulary fails silently by matching nothing at all. **The Stress Test feature was audited 2026-08-05 and the frame was one query: the `stress_tests` table held ONE row, written three days BEFORE the accuracy pass that rewrote the engine** — so nothing had been exercised against the code it runs on, and re-grading that row live moved it from a confident **D** to **ungraded**. Its load-bearing defect is the Tuning workbench's, in a second page on the same day: **a walk-forward or sensitivity child was launched without the baseline's `cost_layers` / `broker_profile` / `sizing_mode`, so stress-testing a charged run measured every child on a free book** and sensitivity blamed the cost gap on the parameter. **The rule this app now states three times over: any page that COMPARES two runs must carry forward everything that decides what a run is measured on — window, costs, broker, sizing — and a page that has been run once, before its own engine was replaced, has not been run.** The same pass made sensitivity run its shifts **across the cores** — it replayed 60 full-history backtests one at a time on a 12-core box (69s each, measured) while `backtest/optimizer.run_sweep` had been fanning optimizer grids across every core the whole time; **46 shifts went 53 min → 14 min (3.8x), proven identical to the cent against the single-run path.** ⚠ **The obvious fix would have looked like it worked and bought almost nothing** — those backtests run on threads and an engine replay is pure-Python bar-by-bar, so it is GIL-bound and needs PROCESSES; the cache was never the bottleneck. Full rules in `command-center/CLAUDE.md`.

### backtest/
Top-level Python backtest runner — strategy- and instrument-agnostic shared infrastructure (same character as `engines/`): broker-data layer with disk cache, bar-replay loop over the canonical engines, tick-level fill & cost model, lab output adapter, a local multi-core optimizer, and **`reprice.py`** (2026-08-03) — charging costs onto a COMPLETED run from its stored trades, which works because each re-priceable cost is size-independent in R; it refuses `bid_ask_fills`/`slippage` outright rather than approximating them. **`portfolio/` gained its runner 2026-08-09** — `run_stack` replays several `strategies/python/` bots on ONE shared balance and ONE risk budget they compete for, plus a SOLO control replay per leg (without which a difference is a mixture of *the cap bit* and *the shared balance re-sized everything*); driven by `tools/stack_run.py`. Consumed by `strategies/python/` bots and by the command-center lab as `runner="python"`. **Deliverable A complete 2026-07-16.** 🔴 **A COST NOBODY MEASURED ON THAT ACCOUNT NOW REFUSES RATHER THAN BORROWING A SIBLING'S (2026-08-06).** All four PU Prime tiers in `fills.py::PROFILES` carried ONE spread and ONE swap, both measured on a **Standard** demo — the single tier priced by a marked-up spread — so `puprime_ecn` charged ECN's commission on top of Standard's costs, a model no real account offers, and **nothing errored**. The raw tiers now carry `SPREAD_UNMEASURED` / `UNMEASURED_SWAP` and raise, naming `algos/tools/broker_facts.py`; **commission still charges, because it is the one of the three a broker states unambiguously per lot.** ✅ **Both refusals have since been retired one at a time, by measurement, on a demo of each tier — and the ORDER they fell is the point.** Swap came back 2026-08-08 (identical on Standard, Prime and ECN, so `puprime_prime` / `puprime_ecn` carry it again — read that as *three reads that agreed*, never as *Standard's figure reused*; `puprime_cent` is still unread and still refuses, which is what keeps the guard alive). **Commission was CONFIRMED 2026-08-10 by two real 0.10-lot round turns — $3.50 and $1.00 per side per standard lot — so the two numbers already in `PROFILES` were right and are now ours rather than a marketing page's.** ⚠ **The SPREAD still refuses on every raw tier even though it has now been read**, because $0.12 came from five minutes of one quiet session and the sentinel's whole purpose is that a tier is measured or it refuses, with no third state for *nearly*. Use `backtest/tools/cost_tiers.py --spread <tier>=<value>` to model an unmeasured tier; it labels the row `stated` and writes nothing back. ⚠ **The swap half was MEASURED, not reasoned:** the assumption *"swap is a fact about the symbol, so it is the same across a broker's tiers"* was written down as a named caveat in the morning and disproved the same day by `broker_facts.py --symbols` — on ONE PU Prime account `XAUUSD.s` and `XAUUSD.crp` are the SAME market (median M15 close difference **$0.08** over 200 shared bars) carrying **swaps 8.5x apart (−79.60 vs −9.35) with the short CREDIT gone entirely (+30.25 vs +0.04)**. This strategy trades both sides and its swap arithmetic rests on that credit. ⚠ **`XAUUSD.crp` is `trade_mode: DISABLED`, so it is EVIDENCE and not a cheaper way to trade** — the tool prints the trade mode beside the tempting numbers for exactly that reason. **The standing lesson is about how an assumption survives: it was checkable in one command the whole time, and it lasted because no command existed. Naming an assumption is not testing it — when you write one down, ask what it would cost to check.** **Broker history floors enforced 2026-07-26** (`data/history.py`): MT5 silently returns COARSER bars when a symbol lacks history at the requested timeframe, so `BarSource.load` refuses a window before the broker's real start — the floor is MEASURED by probing the live terminal (bar density, binary search) and cached per broker, never hardcoded, so swapping brokers re-measures. `tools/run_report.py` is the "why did it make/lose money" multi-year run (per-trade regime/session/excursion + a row per A+ leg that never traded); its `--start` defaults to that measured floor as of 2026-07-29 (it was hardcoded to 2022-01-01, silently reporting 4.6 of 7.9 available years). `backtest/archive/` holds committed, frozen snapshots of that output — `backtest/reports/` is git-ignored scratch, so the archive is how real multi-year trade data reaches a machine with no VPS, no MT5 and no cache. Full rules in `backtest/CLAUDE.md`.

### engines/regime/
Shared market regime classifier. Imported by the live bots (via `algos/shared/shared_regime.py` thin shim) and by the command-center backtest lab. Single output set: 5 labels (TRENDING, TRANSITIONING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY). Each bot owns its own `REGIME_RISK_TABLE` mapping labels to trade decisions. Full rules in `engines/regime/CLAUDE.md`. Algorithm documented in `engines/regime/REGIME_CLASSIFIER.md`.

### engines/market_structure/
Canonical market-structure detection engine (BOS/CHoCH, swing highs/lows, HH/HL/LH/LL, internal structure). A stateful streaming state machine ported line-by-line from `indicators/structure_engine.pine`. **Re-synced 2026-07-12 to the `choch_lock` removal in `mpc_assistant.pine`** (a CHoCH no longer needs the anti-whipsaw latch; on an SOS the promoted extreme prints ASH/ASL and is NOT written to the confirmed-swing map — this is the fix for the missing higher high) and re-validated at 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export. Note the public label domain widened: `broken_high_label`/`broken_low_label` now also carry `"ASH"`/`"ASL"` = *not yet classified*. Imported by the live bots via `algos/shared/structure_engine.py` (thin shim); the command-center backtest lab is a future consumer. This is the single implementation — do not build another anywhere. Full rules in `engines/market_structure/CLAUDE.md`; algorithm in `engines/market_structure/MARKET_STRUCTURE_ENGINE.md`.

### engines/fibonacci/
Canonical fib engine. Turns `engines/market_structure/` output (public `StructureSnapshot` only) into fib LEVEL EVENTS — the first-touch of each level (E1–E4 entries, TP1–TP3 targets, 1.0) — via four fib state machines (Structure "FFT", Sniper, Macro, Internal) ported from `indicators/mpc_assistant.pine`. Unit-tested (40 tests), 100% Pine parity re-confirmed after the 2026-07-12 structure re-sync (the fibs were STALE-BY-INPUT — own code untouched, but the structure stream feeding them changed; fresh 5m export, exit 0). Full rules in `engines/fibonacci/CLAUDE.md`.

### engines/order_blocks/
Canonical order-block engine — **RE-PORTED 2026-07-31 and it is a DIFFERENT OBJECT now**. Structure breaks no longer create blocks at all, so this engine is **STANDALONE**: it consumes no other engine and `update()` takes plain OHLC (it used to take a `StructureSnapshot`). Every block now belongs to a `ta.pivot(2,2)` **TURN**, read two ways at most once each — a PUSH (the engulf reading) and the TURN itself — behind six creation gates (min-back, dead, 1.0x ATR displacement, tap-after-departure, 0.5 overlap dedupe, 2.0x ATR height ceiling). Mitigation is three rules (wick-tap / close-inside-then-out / close clean through) plus a 500-bar age cap reported SEPARATELY as `expired`, because a block price never returned to was not consumed. `max_active` 2 → **10**. In shape it is now a sibling of `fair_value_gaps/` and `equal_highs_lows/`, not of `fibonacci/`. Ported from `mpc_assistant.pine`, 19 hand-traced unit tests, **100% Pine parity 2026-07-31** on two real exports (21,691-bar 15m at `--warmup 798`; 13,186-bar 5m at `--warmup 326`). ⚠ **Budget ~300 bars of warm-up**, and expect a cold engine to be MISSING a block rather than inventing one. **First consumer landed 2026-08-03: `command-center`'s backtest price chart** (`backend/services/ob_overlays.py` → Analysis → Order Blocks), which reads the public events only and is a DISPLAY consumer — no strategy reads a block, so a change here moves what a chart shows and never a trade. Full rules in `engines/order_blocks/CLAUDE.md`.

### engines/sessions/
Canonical sessions engine — the first **time-driven** engine (input = the bar's UTC timestamp + high/low). Emits session EVENTS — Tokyo/London/NY windows + running session high/low, the three DST-aware NY kill zones, the NY opening range, new-day/weekday flags — **each window now stated in its own city's clock and DST-aware** (re-synced 2026-07-31 from a fixed GMT-4: Tokyo `0900-1800` Asia/Tokyo, London `0800-1700` Europe/London, New York `0800-1700` America/New_York — Tokyo is UTC-identical year-round, London and NY shift an hour earlier under BST/EDT). **Validated on two timeframes 2026-07-31** — a 15m export spanning four DST changeovers, and a 5m export for the NY opening range (a ≤5m feature the coarser export cannot test). Standalone, and the base the liquidity and SVP engines compose. Ported from `mpc_assistant.pine`, unit-tested (17 hand-traced tests), 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export. Full rules in `engines/sessions/CLAUDE.md`.

### engines/liquidity/
Canonical liquidity-levels engine. Turns the bar stream into liquidity LEVEL EVENTS — prev day/week high & low, prev week close, the H4 sweep high/low, and Asia/London/NY session high & low, each with sweep/break mitigation; composes `engines/sessions/` for the session levels. **Non-repainting by Aaron's explicit decision (2026-07-05): every HTF level uses the PREVIOUS completed period only — never the current period's forecast.** Unit-tested (14 hand-traced tests), 100% Pine parity re-confirmed after the 2026-07-09 monthly-level (PMH/PML) removal (fresh 5m export, exit 0). XAUUSD trading day opens 18:00 NY (baked-in default). Full rules in `engines/liquidity/CLAUDE.md`.

### engines/vwap/
Canonical session-VWAP engine — a volume-weighted running mean of `hlc3` re-anchored each trading day (the same 18:00-NY boundary as the liquidity daily level), plus a derived close-vs-line cross. The first engine to need a **volume** column in the feed. Unit-tested (13 hand-traced tests), 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export (relative 1e-6 tolerance — the cumulative sum drifts at float-rounding level). Full rules in `engines/vwap/CLAUDE.md`.

### engines/session_volume_profile/
Canonical Session Volume Profile engine — the Asia point-of-control ("MV" line): on each Asia session close it builds a **50**-row volume profile over the session range (`svpRows`, cut 100 → 50 on 2026-07-08; this line said 100 until 2026-07-31 — the code and `svp_export.pine` were always right), reports the highest-volume row's mid-price as the POC, and marks it confirmed when price first straddles it. Composes `engines/sessions/`; needs the **volume** feed. Unit-tested (12 hand-traced tests), 100% Pine parity on a real `VANTAGE_XAUUSD, 5m` export. The **last of the roadmap's eight planned SMC-port engines — the core extraction roadmap is complete** (the fair-value-gap engine below was pulled later, for the A+ setup). Full rules in `engines/session_volume_profile/CLAUDE.md`.

### engines/fair_value_gaps/
Canonical fair-value-gap engine — turns the bar stream into FVG EVENTS: a price void left by a 3-candle imbalance (the LuxAlgo definition — the two outer candles don't overlap, the middle bar's close cleared the gap, and the gap clears a **timeframe-split** size floor — 0.0% below 15m, 0.04% at 15m and above), plus its later mitigation (a candle CLOSING fully past the far edge — a wick no longer counts) and FIFO eviction past `fvgMaxCount` (default 6). Standalone and OHLC-driven — no upstream engine, no volume (the Pine's directional-visibility filter is drawing-only and is deliberately not reproduced; every gap is emitted with its `is_bullish` flag and a consumer decides alignment). Ported line-by-line from `mpc_assistant.pine`'s FVG block, unit-tested (15 hand-traced tests). **Re-synced 2026-07-18** to the mpc default drift: the middle-bar close-cleared check is now the OPTIONAL `require_close` flag (Pine `fvgRequireClose`, default False — the classic FVG that the mpc default produces; the engine had silently required it since the gate landed in mpc on 2026-07-17), and the defaults were reconciled to the Pine (`max_count` 6→10, `threshold_pct` 0.1→0.0). `fvg_export.pine` now carries `cfg_fvg_*` columns and `compare_fvg.py` configures the engine from them, so parity survives any input tweak. **Pine-parity RE-VALIDATED 2026-07-19 (exit 0)** on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export at the reconciled defaults. Pulled off the indicator later than the eight planned engines, to feed the A+ setup. Full rules in `engines/fair_value_gaps/CLAUDE.md`.

### engines/rsi_divergence/
Canonical RSI-divergence engine — turns the bar stream into RSI-DIVERGENCE EVENTS: a confirmed regular divergence at the extremes (price lower-low while Wilder's RSI higher-low from oversold = bullish; the overbought mirror = bearish), plus the live confluence flags (`bull_active`/`bear_active`) a consumer reads. Standalone and price-driven (close for RSI + the bar's high/low for the anchor — no upstream engine, no volume, no timestamp); a sibling of `fair_value_gaps/` in shape. Pivots confirm `pivot_len` bars late (non-repainting by design). Pulled off the indicator later than the eight planned engines (like FVG), to feed the A+ setup. Ported line-by-line from `mpc_assistant.pine`'s RSI DIVERGENCE block, unit-tested (9 hand-traced + reference-cross-check tests), **100% Pine parity** on a real `VANTAGE_XAUUSD, 5m` export (`compare_rsi_div.py --warmup 1630`, exit 0). Full rules in `engines/rsi_divergence/CLAUDE.md`.

### engines/equal_highs_lows/
Canonical Equal Highs/Lows (EQH/EQL) engine — turns the bar stream into EQH/EQL LEVEL EVENTS: when two consecutive same-side strict price pivots land within an ATR(50)×mult band of each other, a horizontal liquidity level prints (EQH = buy-side resting above, EQL = sell-side below) and lives until a candle CLOSES through it; FIFO cap per side (default 6). Standalone and price-driven (high/low/close — no upstream engine, no volume, no timestamp); a sibling of `fair_value_gaps/` and `rsi_divergence/` in shape. Ported line-by-line from `mpc_assistant.pine`'s EQ block, unit-tested (7 tests). **Pine-parity VALIDATED 2026-07-19 (exit 0)** on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export. The real-export run exposed and FIXED a genuine pivot bug: Pine's `ta.pivothigh`/`pivotlow` allow a tie on the LEFT of the centre but require a STRICT extreme on the RIGHT (the last bar of an equal run is the pivot); the engine had used strict-both-sides, which silently dropped the frequent raw-price ties on gold. The identical latent bug was fixed in `rsi_divergence/` too (there ties on RSI values are rare, so it only surfaced as a couple of diagnostic-column misses). The Pine's `eqExemptFvg` coupling (a gap behind an EQ level survives the FVG cap) is now MODELLED (2026-07-18, Aaron's exact-match call): the FVG engine's `update()` takes `eq_levels`/`eq_tol` and the consumer runs EQ→FVG (`backtest/replay/EngineStack` wiring is a follow-up). Full rules in `engines/equal_highs_lows/CLAUDE.md`.

### engines/candlesticks/
Canonical candlestick-pattern engine — **built 2026-08-08 and the first engine here ported from a THIRD-PARTY indicator** (`indicators/candle_sticks.pine`, © repo32, v6) rather than from `mpc_assistant.pine`. Turns the bar stream into CANDLESTICK PATTERN EVENTS: fifteen classic single-, two- and three-bar patterns, each carrying the direction its source Pine draws it in. Standalone and OHLC-driven (no upstream engine, no volume, no timestamp) — a sibling of `fair_value_gaps/`, `rsi_divergence/` and `equal_highs_lows/` in shape. It exists to be a CONFLUENCE source: something a strategy ANDs into a setup it already has. A pattern is a property of ONE bar, so there is no live list, nothing is mitigated and nothing expires; a window ("within the last 3 bars") is asked of the engine (`bars_since`), never of a bar's events. 42 hand-traced tests green; replayed clean over 186,366 real XAUUSD M15 bars with all fifteen patterns firing at least once. ✅ **PINE-PARITY VALIDATED 2026-08-08 (exit 0)** on a real 20,138-bar `VANTAGE_XAUUSD, 15m` export, green at warmups 0 / 100 / 500 / 2000, configured from the export's own `cfg_*` columns — and **NOT VACUOUS: 14 of the 15 patterns fired**, 302,070 flag comparisons, **zero rule differences**. ⚠ **Three BOUNDARY TIES, and how they are handled is the transferable part**: `doji`, `invHammer` and `shootingStar` each compare two quantities that come out **exactly equal in decimal** on real prices (0.26 vs 0.26 · 3.96 vs 3.96 · 5.43 vs 5.43, confirmed with `Decimal`), neither side is representable in binary float, so the two implementations land on opposite sides of a rule they both compute correctly. **A tolerance was deliberately NOT used** — a 0/1 flag has no "close enough" and a tolerance would swallow real bugs with the ties — so the harness CLASSIFIES instead: it re-runs each mismatch with every price in the bar's window nudged ±1e-6 and asks whether the answer flips. Proven non-vacuous by injecting two fabricated flips, which came back REAL with exit 1. ⚠ **An unclassifiable mismatch counts as REAL, never as a tie.** ⚠ **The measured frequencies split the set in two and that decides how it can be used:** five patterns fire on **5–9% of every bar** (both haramis, both engulfings, hammer 8.9%, inverted hammer 8.3%) — arriving every ~12 to 20 candles, so on their own they are not filters — while ten fire between **19 and 661 times in eight years**, with `bullish_belt` at 19 and `hanging_man` at 25 too rare to measure at all, which is the B-LEG sample-size problem in miniature. ⚠ **Hammer, Inverted Hammer and Doji are emitted direction-NEUTRAL, deliberately: the source draws them as a neutral diamond and gives them NO trend filter**, where ten of the fifteen rules gate on `open[trend]`. A hammer with no trend context is a candle shape, not a reversal — a consumer that wants it bullish states so in its own config, because the moment the engine decided it, the engine and the chart would disagree about the same candle. ⚠ **7.4% of bars carry more than one pattern and that is correct** — every Hanging Man is also a Hammer by construction and the Pine plots both. Full rules in `engines/candlesticks/CLAUDE.md`.

### engines/news/
Canonical economic-calendar (news) engine — **off the extraction roadmap and NOT a Pine port**. Standalone and time-driven: turns each bar's UTC timestamp into trade-BLACKOUT events around scheduled macro releases plus bank-holiday reporting; the engine reports, the bot decides via its own `NewsPolicy`. **Honest-coverage by Aaron's decision (2026-07-05): the filter is inert before the cache's earliest fetched date; `coverage_start_ms` marks the boundary.** Validated by 29 unit tests + live checks (no Pine source to diff). Full rules in `engines/news/CLAUDE.md`.

### strategies/
Generic trading strategy source files, organized by runner platform. `strategies/ninjatrader/` holds the only live NinjaScript strategy, `ORB.cs` (VWAP_MR and Momentum were deleted 2026-06-21 — they baked risk management into the strategy, against the gated-layer rules). The command center scanner reads from here to register strategies in the database; the Deploy button uploads files to the VPS (NT8 or MT5 folder by extension). `strategies/mt5/` holds one MQL5 strategy: `LondonBreakout.mq5` (instrument-agnostic Asian-range → London breakout). `strategies/python/` holds Python strategy packages run locally by the lab's python runner (no deploy) — currently `mpc_sos_fade/` (MPC SOS Fade, **Pine-logic-parity green, re-validated 2026-07-27** on 21,320 bars at the settings Aaron trades — SL fib 0.886, TP rungs 0/0), `mpc_bleg/` (MPC B-LEG, the late-retrace setup split out of `mpc_strategy.pine` to run parallel to A+ — unit-tested, **Pine-parity GREEN 2026-07-26** on a real 21,231-bar export) and `mpc_bos/` (MPC BOS, the break-of-structure continuation setup, built 2026-08-07 — **Pine-parity GREEN 2026-08-07**, `compare_bos.py` exit 0 on 6,300 of a 7,200-bar M15 export at warmups 900 / 1000 / 2000 / 3000; ⚠ **green about the SHIPPED defaults only** — the gap entry is OFF there, so the whole FVG ladder, the Sniper Zone and block codes 1/3/4/5/6 were never exercised, and 6 trades closed in the window). **The end-to-end process — spec → Pine → export twin → a real CSV → the Python port → the parity gate, and which of those only a human can do — is `docs/STRATEGY_WORKFLOW.md`.** Both share ONE exit ladder, and its switchable TP/SL levers are registered in `strategies/python/mpc_sos_fade/CLAUDE.md` → `## The exit ladder` — add a new one there, in `config.py`, in `mpc_strategy_export.pine` and in `compare_strategy.py` in the same commit. Full rules in `strategies/CLAUDE.md`.

### scripts/
Cross-subsystem VPS bootstrap and full-recovery scripts (`bootstrap_vps.ps1` for the MT5/algos side, `bootstrap_ninjatrader.ps1` for the NT8 side). Idempotent, run on a wiped or new VPS. Full run order in `scripts/README.md`. **`setup_learning_mode.sh` (2026-08-11) is the odd one out — it targets a DEV MACHINE, not the VPS**, and is the one-time install behind `/learn <video-url>`: it puts `ffmpeg`/`yt-dlp` on the PATH and clones the third-party `watch` skill (MIT, `bradautomates/claude-video`) to `~/.claude/vendor/`, symlinked into `~/.claude/skills/watch`. ⚠ **The watch skill is deliberately NOT vendored into this repo**, so a clone alone does not make `/learn` work — the skill checks for the install and names the script rather than shelling out to `yt-dlp` itself. **Re-running the script is also how it UPDATES**, which is the part that bites: `yt-dlp` breaks whenever a video site changes its markup, and a stale copy fails on real URLs while looking perfectly installed.

### .claude/
Repo-shipped Claude configuration — available to every clone, unlike `~/.claude/` which is per machine. Three folders.

**`commands/` — the slash commands.** Two kinds, and the split is the point. The **audit** commands look BACKWARDS at code already written: `/audit-engines`, `/audit-strategy`, `/doc-audit`, `/dead-code-audit`, `/prop-firm-rules-audit`, `/quant-review`, `/regenerate-snapshots`, `/session-start`. The **build-time** commands (added 2026-08-12) run BEFORE and DURING the work, and each one exists because a specific class of defect kept reaching the audits: `/spec` (write down what I think you asked for, before code — catches right-code-wrong-question), `/wire-check` (trace every label, config field and registry to the line that consumes it), `/prove` (watch every new test go red, or kill it by mutation), `/measure` (no number without the command that produced it), `/live-safety` (the 22-question checklist before anything touches the live path), `/port` (drive a strategy through `docs/STRATEGY_WORKFLOW.md` and refuse to skip the parity gate). ⚠ **They are prompts, not enforcement** — nothing makes anyone type them. The two things that ARE enforced are the commit hook and the editor guard below, and the commands exist so that when the hook asks "what did you check", there is a repeatable answer.

**`hooks/guard_sensitive_paths.py` — the editor guard.** A `PreToolUse` hook on Edit/Write. A `deployed/` snapshot **asks first**, because a live bot imports from it and an edit there changes what a running bot trades immediately, with no promote and no restart. `engines/`, `strategies/`, `algos/live/`, `algos/shared/`, `backtest/` and `*.pine` attach a one-paragraph reminder of the rule that path keeps breaking, at the moment of the edit rather than 40,000 words away. ⚠ **It FAILS OPEN by design** — any error allows the edit, because a broken guard must never stop the work. ⚠ **Which also means its silence proves nothing**; verify it by piping a fake event through it, the way it was verified when it landed.

**`skills/` — `learn/` (2026-08-11)**: `/learn <video-url> [focus]` watches a video and files a durable note to **`education/learned/`** (dated markdown, source link, what it covers with timestamps, what is worth acting on). It drives the third-party `watch` skill for the watching — captions first, `ffmpeg` frames second, Whisper API only when a video has no captions — and adds the note. ⚠ **The note is the deliverable and the chat reply is deliberately short**: a note that lists the TOPICS a video mentioned is worthless, so it records what the thing actually IS. ⚠ **The notes are COMMITTED and the videos are not re-watched** — a note already on disk for a URL is read rather than regenerated, because the frames are the whole token cost. ⚠ **No speech-to-text key is configured** (`~/.config/watch/.env`, per machine, git-ignored by living outside the repo): captions cover most of YouTube, and a caption-less source — a Loom, a TikTok, your own screen recording — comes back frames-only and says so. A free Groq key retires that.

### indicators/
From-scratch Pine Script rewrite of the "Structure OS / SMC Engine" market-structure indicator (`indicators/smc_engine_v2.pine`), replicating a private TradingView indicator using a pullback-only (no pivot lookback) swing detection method. Mid-rebuild: swing detection and break-gated BOS/CHoCH (Stage 2b) are ~95% validated against the original; internal structure (Stage 3) and full multi-symbol comparison (Stage 4) are not started. Full rules in `indicators/CLAUDE.md`.

---

## VPS Deploy Workflow

**Pulling does NOT change what a bot trades — promoting does.** Since 2026-08-03 a live bot
imports from a frozen snapshot in `algos/markets/fx/instances/<bot>/deployed/`, not from the
repo, so a pull is safe at any time and a restart still comes back on the SAME version. See
`algos/live/version.py`.

```bash
# Push changes
git add . && git commit -m "..." && git push

# Pull on the VPS — safe while a bot is running; it will not move the deployment
ssh forexvps "cd C:\trading && git pull origin main"

# Deploy the code to a bot (the ONLY thing that changes what it trades).
# Stages, verifies it imports, then swaps; a failure leaves the running bot untouched.
ssh forexvps "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe C:\trading\algos\tools\promote.py --bot mpc_sos_fade_demo"

# Restart onto the new version. SYS_MONITOR also restarts a dead bot on its own within
# ~60s, so killing it is enough — but this is the deliberate path.
ssh forexvps "schtasks /run /tn SYS_STARTUP"
ssh forexvps "wmic process where \"name='python.exe'\" get commandline"
```

⚠ **NEVER `taskkill /f /im python.exe`.** It kills every Python process on the box — the
trading bot, the Telegram bot, the MT5 backtest agent and the NT8 agent — and it is what
killed the live bot on 2026-07-31 (dead for three days; nothing restarted it then). This
workflow told you to run it, which is how it kept happening. Kill ONE bot by its commandline:

```bash
ssh forexvps "wmic process where \"name='python.exe' and commandline like '%--bot mpc_sos_fade_demo%'\" call terminate"
```

VPS path: `C:\trading\algos\` (main)

---

## Committing — the docs land in the same commit as the code

**Enforced since 2026-08-04 by a git hook, not by memory.** Two people work this repo from
two machines, and these CLAUDE.md files are the only way each learns what the other did. A
code change whose doc never landed is invisible on the other machine until it bites.

`.githooks/commit-msg` refuses any commit where a changed file's **owning CLAUDE.md** is not
in the same commit. The owner is the nearest CLAUDE.md walking UP from the file's folder —
so `engines/vwap/engine.py` needs `engines/vwap/CLAUDE.md`, a ChartPanel component needs
`ChartPanel/CLAUDE.md`, and a root-level file needs this file. Updating a PARENT does not
satisfy a child: the nearest one is the one somebody reads next.

Exempt: markdown, lock files, images, data (`.csv`, `.db`, `.pkl`), `.gitignore`,
`.claude/settings.local.json`, and **`*/ledger/decisions-*.jsonl`**. Merges, rebases, reverts and
`fixup!` commits pass through — they carry somebody else's change and would ask for the same
paragraph twice. ⚠ `*.meta.json` is deliberately NOT exempt: it is a contract the Pine and the lab
both read, not data.

🔴 **The ledger exemption was added 2026-08-05 because the hook had QUIETLY DISABLED THE ONE BACKUP
THAT MATTERS.** `algos/tools/ledger_sync.py` commits the live bot's decision record unattended —
that record is the only copy of what the bot decided, including every setup it refused, and no
broker statement contains it. The hook classified the `.jsonl` as code and demanded a paragraph in
`algos/CLAUDE.md` for a data file, so **every automated sync failed and a closed day sat on the VPS
alone.** Measured: the sync refused with 2026-08-04 outstanding, and it went through the moment the
exemption landed. ⚠ **It is a PATH, not `*.jsonl`** — the extension is generic, and a future
`.jsonl` carrying a contract would be waved through the way `*.meta.json` explicitly is not, while
`*/ledger/decisions-*.jsonl` can only ever be this. **The standing lesson is about guardrails, not
about this file: a rule that fires on a robot's commit has no human to read its message, so it does
not nag — it silently stops the job.** When you add a check, ask what it does to the things that
commit without a person watching.

When a change genuinely needs no doc update, say so **in the message** — the reason is
required and is recorded where the other person can read it:

```
fix(chart): correct a comment typo

DOCS: none - comment only, no behaviour change
```

### The second half — a change to the money paths names its evidence

**Added 2026-08-12.** The docs check proves somebody WROTE something down. It does not prove
anybody CHECKED anything, and this repo's expensive mistakes all shipped with docs AND a green
suite: a 54.82-lot order on a $2,000 account, a bot re-anchoring its sizing to a stranger's
balance for two hours, an 82-combination sweep from a port whose parity gate had never once run.

So for the paths where a wrong number costs money rather than time — `engines/`, `strategies/`,
`algos/live/`, `algos/shared/`, `backtest/`, `indicators/*.pine` — the message has to carry one
line naming the evidence:

```
fix(live): halt when the terminal is on another account

TESTED: 18 new tests, 13 watched RED against HEAD; 603 algos green
MEASURED: cost_tiers.py, 155,531 M15 bars - ECN 157 trades / +151.39R
PROOF: none - renamed a local variable, no behaviour change
```

The line is **not graded**. The point is that you had to type what you actually ran, which is
the moment you notice you ran nothing. `/prove` and `/measure` exist to make that line true
rather than plausible.

⚠ **It is deliberately NARROW, and widening it has a cost.** A hook that nags on every UI tweak
is a hook people learn to bypass, and `--no-verify` leaves no trace at all — which is strictly
worse than no hook, because the history then reads as checked. `command-center/` is excluded on
purpose. If you widen it, name the reason.

⚠ **The exemptions are shared with the docs check, so the unattended ledger sync still passes** —
that was verified rather than assumed, because a rule firing on a robot's commit has no human to
read its message and silently stops the job. That has already happened twice on the docs half.

⚠ **Merges, rebases, reverts and `fixup!` pass straight through**, same as the docs check.

### Getting it switched on — four tripwires, because nothing runs on clone

⚠ **The hook lives in `.githooks/` and is switched on by `core.hooksPath`, which is per-clone
LOCAL config that `git clone` does not carry.** A fresh clone is unprotected and looks
IDENTICAL to a protected one — measured, not assumed: a clone of this repo committed a code
change with no doc and no complaint.

**Git will not execute repo code on clone or fetch**, and that is a security property, not an
oversight — so no hook of ours can fire first. The answer is to check at every entry point
somebody plausibly uses first. All four call the one installer, `scripts/install_hooks.sh`,
which is **silent when nothing needs doing** and speaks up only when it just installed:

| Tripwire | Fires when | Catches |
|---|---|---|
| `.githooks/post-merge` | every `git pull` / merge | drift, an unset config, a hook arriving without its executable bit |
| `.claude/settings.json` → `SessionStart` | every Claude Code session in this repo | **a fresh clone** — neither of us works here without Claude |
| `conftest.py` | any `pytest` run | a fresh clone, before the suite runs |
| `./go` | every launch of the command center | a fresh clone |

`post-merge` also **says so when the pull changed the rules themselves** (`.githooks/` or the
installer), because a rule that changes under you without a word makes the next refusal read
as a bug.

⚠ **`post-merge` cannot cover the clone case and must not be read as if it does** — it is the
one tripwire that requires the hooks to already be installed. The clone is covered by the
other three, and they are three rather than one because each only fires if you happen to do
that thing first.

⚠ **The pytest notice is suppressed by `pytest -q`** (which hides the header). The install
still happens; only the message is hidden. Run plain `pytest` to see it.

⚠ **A hook that is not executable is skipped by git in silence** — same "looks installed, does
nothing" shape one level down. The installer chmods every hook every run.

## Branches

- `main` — active development, all code changes go here

---

## Never Do

- Commit `credentials.json`, `users.json`, `.env`, any `.pkl` model files, or API tokens/keys
- Commit with `--no-verify` to get past the CLAUDE.md hook. It leaves NO trace, so the next person cannot tell a deliberate skip from a forgotten one — which is the whole problem the hook exists to fix. The honest skip is a `DOCS: none - <reason>` line in the message, and it costs one sentence. See `## Committing`
- Touch `algos/` when working on `smart-money/` or `command-center/` and vice versa
- Build a second regime classifier in `command-center/` or anywhere else — `engines/regime/classifier.py` is the canonical implementation; all consumers import from there
- Build a second structure engine, fib engine, order-block engine, sessions engine, liquidity engine, VWAP engine, SVP engine, fair-value-gap engine, RSI-divergence engine, equal-highs-lows engine, candlestick-pattern engine, or news/economic-calendar engine anywhere — `engines/market_structure/engine.py`, `engines/fibonacci/`, `engines/order_blocks/`, `engines/sessions/`, `engines/liquidity/`, `engines/vwap/`, `engines/session_volume_profile/`, `engines/fair_value_gaps/`, `engines/rsi_divergence/`, `engines/equal_highs_lows/`, `engines/candlesticks/` and `engines/news/` are the canonical implementations; all consumers import from them
- Commit `engines/news/data/events.json` (or anything under `engines/news/data/`) — it is fetched calendar data, git-ignored, not source
- Commit a new or changed engine before its Pine↔Python parity check has actually run and passed (exit 0) on a real TradingView CSV export — unit tests pin the logic but do not prove parity. Build engine + tests + harness, then wait for the real export and the `compare_*.py` pass; only then commit (Aaron's standing rule, 2026-07-05)
- Hardcode a broker's history depth — including as a "sensible" DEFAULT start date on a tool. A default is a hardcode with better manners: it fails quietly in the direction nobody checks, silently narrowing every run that didn't pass the flag (`run_report.py` did exactly this until 2026-07-29). Measure the floor, or refuse to run and ask.
- Construct a `LAB_STRATEGY` class directly when a run may carry costs — go through `backtest.replay.build_strategy`. `LAB_STRATEGY` is an open contract, so a strategy may predate the `cost_profile` kwarg; passing it unconditionally crashes, and passing it conditionally reintroduces the exact bug that let the lab collect commission and slippage for months and charge neither. The helper refuses to run instead
- Report a metric as verified because its arithmetic reproduces. Every stored KPI on run `f866873aa862` recomputed to the cent and the page still misled three ways — a drawdown in dollars only, a win rate counting breakeven scratches, a concentration measured over quarters answering a different question from the one its name asks. **Ask what a reader will CONCLUDE from a number, not just whether it is correct**
- "Fix" a wrong-side stop filling at the next bar's open. It is the one-bar order delay every fill model here is built on, it is identical in Pine and Python (so parity is unaffected), and it makes the backtest look slightly WORSE than reality — the safe direction. Removing it is a real behaviour change across all five Pine files and needs its own measurement, not a tidy-up. See `strategies/python/mpc_sos_fade/CLAUDE.md` → `### Wrong-side stop fills`
- Read a `/health` response as a statement about the thing BEHIND the agent, or a `schtasks /run` exit code as evidence the task started. The MT5 agent answers `ok` while its terminal is disconnected; `schtasks` answers SUCCESS for a task Windows refuses to launch. Probe the thing you are actually claiming, and re-probe after any action you take
- Trust a probe whose NEGATIVE result a healthy system can also produce — that is not a probe, it is a coin flip you have decided to believe. The live bot asked its bars whether the terminal was alive, and an empty bar frame is equally what a quiet market returns: when MetaTrader auto-updated and restarted itself on 2026-08-04 the bot read the dead link as a quiet market and sat blind for 50 minutes with its heartbeat ticking, the watchdog green and the Bots page saying RUNNING. `account_info()` is the probe now, because it answers whenever the link is alive whatever the market is doing. **The generalisation is about VALUES, not labels: never let "no data" and "cannot ask" be the same value.** Every layer in that path was individually defensible — an empty DataFrame is a reasonable return for a bar fetcher, a null balance a reasonable write when you have no balance — and the distinction was destroyed at the bottom and unrecoverable at every level above it, leaving a blank cell as the only symptom in the entire system
- Record what you REQUESTED as though it were what you RECEIVED. The bar cache did exactly that until 2026-08-04: it fetched a window, saved whatever came back, and then marked the whole **requested** range as covered — so asking for bars through a date the broker did not have yet (every `--end today`) marked that date fetched forever, and every later run read a cache HIT and got a frame that silently stopped early. Measured: the sidecar claimed history through 2026-08-06 while the file held nothing past 2026-08-03 03:45, with the agent serving the missing bars on request the whole time. **The returned frame is clean and gives you no way to notice.** This is the same defect as the hardcoded history floor arriving from the other end of the window — the system answering a narrower question than the one asked. Clamp coverage to the data, and never into today, because a day still filling looks exactly like a complete one
- Hardcode a broker's history depth, or trust MT5's `/data_availability` for it. MT5 answers a request for a timeframe it has no history at with the nearest COARSER bars, still labelled as what you asked for — a backtest fed those runs clean and lies. Depth is MEASURED by bar density (`backtest/data/history.py`, probed per broker and cached); `/data_availability` samples one bar per end and is fooled the same way (it reported M1 back to 2007, false by ~11 years). Verify by bars-per-day, never by the earliest timestamp
