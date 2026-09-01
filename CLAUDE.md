## Communication Rules — Non-Negotiable

- Plain English only. Short sentences.
- **Never write a code name in a reply to ANYONE — no variable, parameter, config field, function or class names.** Say what the thing DOES: "the setting that decides what triggers the trade", not its name. If the reader needs to find it themselves, quote the label shown in the Command Center. File paths and file links are fine — those are places, not code. Write a real name only when they ask for it or ask to see the code. *(Aaron, 2026-08-20: "you keep using it as though I'm reading code." A sentence built round a raw name carries no information to the person reading it, so it hides the answer instead of supporting it. It applies to every person working this repo, not just the one who asked — nobody here reads as a compiler.)*
- **Answer in a short bulleted list, grouped by outcome.** Findings go under **Broken** and **Working**, worst first, and anything needing a decision goes last under its own heading. One line per bullet — a fact and its consequence, nothing else. No nested bullets, no closing summary repeating what the bullets said. *(Aaron, 2026-08-24: "this is the most efficient way to speak to me." He asked twice in one session after two prose answers, so a long-form reply is now the exception that has to earn itself. It applies to everyone working this repo.)*
- **Prose only when he asks for it, or when a bullet would hide the reasoning** — a design trade-off, a measurement that needs its caveat attached, why something broke. Then keep it to a paragraph and put it UNDER the bullets, never above them.
- Say the answer in the first bullet. Never build up to it.
- No preamble. No "Great question." No "Sure, I can help with that."
- Spawn subagents for routine tasks. Work sequentially unless the task explicitly requires parallel execution.


# CLAUDE.md — LWG Capital Monorepo

**Purpose:** Standing instructions for Claude Code across all subsystems.
**Scope:** This covers repo-wide rules, VPS workflow, and branch conventions. It does NOT cover subsystem internals — each subsystem has its own CLAUDE.md.
**Status:** Active — four apps, **13** canonical engines (count them with `ls engines`, never from memory — this line said "ten" for weeks), one LIVE bot, and tooling in various stages of production.
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
| `/run-audit` | after any lab run you are about to believe | 3, 6, 9, 11 |

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

**The overlap audit — the legs really do trade different parts of the move, RE-MEASURED 2026-09-01.** Over 157,004 M15 bars (2020-01-01 → 2026-08-23) A+ and B-LEG held a position at the same time on **45 bars** — 0.5% of A+'s hold time — of which **ZERO were same-side** (all 45 are opposite-direction, i.e. partly hedged). A+ 156 trades / +131.77R, B-LEG 101 / +20.20R; 4 trade pairs touch at all, and exactly ONE same-direction entry lands within 16 bars of the other's in 6.6 years. Monthly R correlation **+0.072** over 78 months, which is a FLOOR rather than a figure — a month only one bot traded contributes a zero for the other and pulls it toward 0. ⚠ **The 2026-08-09 reading (49 bars, ONE same-side) was measured before the dead-market entry filter landed on 2026-08-26 and no longer describes either bot.** ⚠ **Re-run `backtest/tools/overlap_audit.py` after any entry-logic change on either bot**: this is a fact about today's config, not about the setups, and the 2026-08-04 run was already measured on a B-LEG that no longer existed. ⚠ **A cross-cutting measurement is re-run by whoever MOVES the inputs, not by whoever wrote the conclusion** — that is why it was stale. ⚠ **Do not read a bigger overlap number as a regression without reading the direction split under it**: the absolute count went UP 27 → 49 while same-side went DOWN 18 → 1, from one change — and on the 2026-09-01 re-run both fell (49 → 45, 1 → 0). ⚠ **It does not make the two independent** (one structure stream, one instrument), and ⚠ **it does not retire the allocator** — the peak was still 2 concurrent positions, so one account would have carried 2× `exec_risk_pct` on those bars. Full numbers, the jitter audit that followed, and what it changed for bot #2: `HISTORY.md` → *The overlap audit, re-measured*.

**The BACKTEST side of the allocator exists; the LIVE side does not.** `backtest/portfolio/run_stack` replays both bots on ONE balance with ONE risk budget, and at a 10% cap over 155,807 M15 bars it **refused nothing** — risk is measured to each trade's CURRENT stop and A+ reaches breakeven in a median of one bar. ⚠ **The LIVE allocator is unbuilt and cannot reuse that object** (separate OS processes, every MT5 read magic-filtered), so "risk is budgeted per ACCOUNT" is still intent on the live side. See `docs/LIVE_TRADING_PIPELINE.md` → G10.

**A stack in `command-center/` is either a SCREEN or a SHARED ACCOUNT, and the page says which before any number below it.** A screen is N standalone runs added together — every leg on its own full account, so nothing can block anything and it is an UPPER BOUND. 🔴 **A shared run can close HIGHER than the screen with the cap working and nothing refused, and a doc here predicted the opposite.** A screen gives each leg a private balance; a shared account COMPOUNDS both onto one, so the second leg sizes off a balance the first has grown. Two effects in opposite directions, and the compounding one is unbounded while the refusal one is capped by how often the budget is genuinely full. ⚠ **So compare R, never net dollars** — the checks that say the gate is enforced are `peak_open_risk_pct <= risk_cap_pct` and every R difference tracing to a row in the contention log. **The standing lesson is about the CRITERION rather than the code: a verification test written before the thing exists is a prediction, and this one would have condemned a correct implementation.** Full run: `HISTORY.md` → *The lab stack, and the test that would have condemned it*.

---

## Repo Structure

See `README.md` for the full repo map and subsystem list.

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. Engines under `engines/` are canonical shared libraries, and their dependency map is: `market_structure/` is the base and `fibonacci/` is its one downstream consumer (public `StructureSnapshot` only, never its internals). **`order_blocks/` was downstream too until 2026-07-31 and is now STANDALONE** — the mpc rework stopped creating blocks on structure breaks, so it takes plain OHLC and consumes no engine at all; `sessions/` is standalone and time-driven; `liquidity/` and `session_volume_profile/` compose `sessions/`; `vwap/` and `news/` are standalone and time-driven; `vwap/` and `session_volume_profile/` are the two engines that need the bar's **volume**; `fair_value_gaps/` is standalone and OHLC-driven (no upstream engine, no volume, no timestamp — pure price-pattern detection); `rsi_divergence/` is likewise standalone (needs close for Wilder's RSI + the bar's high/low for the price anchor — no upstream engine, no volume, no timestamp); `equal_highs_lows/` is likewise standalone (needs high/low/close for ATR(50) + strict price pivots — no upstream engine, no volume, no timestamp); `candlesticks/` is likewise standalone (needs OHLC only — no upstream engine, no volume, no timestamp — and is the only engine here ported from a THIRD-PARTY indicator rather than from `mpc_assistant.pine`). `engines/regime/` and `engines/market_structure/` are imported by `algos/` via thin shims in `algos/shared/`. **`command-center/` imports six directly** (bare-name, public API only, never a second implementation): `regime/` and `news/` for tagging and the news filter, and `market_structure/` + `fair_value_gaps/` + `equal_highs_lows/` + `order_blocks/` for the backtest PRICE CHART's overlay layers (`backend/services/structure_overlays.py`, `fvg_overlays.py`, `ob_overlays.py`). Those four are **display** consumers — no strategy reads them, so a change there moves what a chart shows and never a trade — but they are consumers, and an engine's own CLAUDE.md must say so rather than claiming nothing imports it. Every other engine gets its `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS strategy folders. Per-engine detail lives in each engine's CLAUDE.md — do not restate it here.

---

## System Summaries

> **This section ROUTES — it does not explain.** Every subsystem below owns a `CLAUDE.md` next
> to its code, and that file is the one that gets updated and the one that is right. A summary
> here would be a SECOND COPY, and copies go stale: the 2026-08-12 doc audit found three files
> claiming there were no live bots, and the subsystem file was the one telling the truth. This
> section was 36 KB of exactly that — 53% of a file that loads on **every** session whether or
> not you go near the code it described. **A fact lives in exactly ONE CLAUDE.md, the one next
> to the code. Parents ROUTE, children EXPLAIN.** Enforced at the moment of the edit by
> `.claude/hooks/guard_sensitive_paths.py`.
>
> ⚠ **The last four entries are the exception and must NOT be collapsed** — `scripts/`,
> `tools/`, `education/learned/` and `.claude/` have no child CLAUDE.md, so root owns them
> outright and this is their only copy.

### The four apps

| Subsystem | What it is | What to know before you touch it |
|---|---|---|
| `algos/` | Live MT5 trading bots on a Windows VPS | **`mpc_sos_fade_demo` is LIVE and ARMED** — PU Prime **ECN 700152905**, `XAUUSD.p`, account risk cap 10%. `mpc_bleg_demo` is registered and BENCHED. A live bot imports from a frozen `deployed/` snapshot, so a `git pull` cannot move it — only `promote.py` can. A fleet kill switch and an account-mismatch halt both exist and both LATCH. |
| `command-center/` | React + FastAPI local ops platform — monitors bots over SSH, runs and grades backtests | A bot is registered ONCE (`routers/bots.py::BotReg`) and addressed by its KEY, never its display name. A broker ACCOUNT is a first-class row too. The Smart Money UI is flagged OFF behind one boolean. |
| `backtest/` | Strategy- and instrument-agnostic Python bar-replay runner — data, fills, costs, optimizer, portfolio stacks | An unmeasured cost REFUSES rather than borrowing a sibling tier's number. Swap, commission and — since 2026-08-14 — **ECN's spread** have been measured; **Prime and Cent still refuse, and ECN's figure may not be copied onto them.** History floors are measured per broker, never hardcoded. |
| `smart-money/` | Scans and profiles consistent crypto/forex traders for a copy-trade candidate pool | Runs locally on Mac. Stages 1–2 and 5 live; 3–4 blocked on API keys. |

### The engines — canonical, one implementation each

Ported from `indicators/engines/mpc_assistant.pine` and gated by a `compare_*.py` parity check on a real
TradingView export — except `regime/` and `news/`, which have no Pine source, and `candlesticks/`,
which is ported from a third-party indicator. **Never build a second implementation of any of
them** — see *Never Do*. The dependency map is in *Repo Structure* above. Per-engine detail is in
each engine's own CLAUDE.md and is not restated here.

| Engine | What it emits |
|---|---|
| `market_structure/` | BOS/CHoCH, swing highs/lows, HH/HL/LH/LL, internal structure — the base engine |
| `fibonacci/` | Fib level events (E1–E4, TP1–TP3) — the one downstream consumer of structure |
| `order_blocks/` | Order blocks off `ta.pivot(2,2)` turns — STANDALONE since the 2026-07-31 re-port; budget ~300 bars of warm-up |
| `sessions/` | Tokyo/London/NY windows, DST-aware kill zones, NY opening range — time-driven |
| `liquidity/` | Prev day/week levels, H4 sweeps, session highs/lows — never repaints, by decision |
| `vwap/` | Session VWAP re-anchored 18:00 NY — needs the bar's volume |
| `session_volume_profile/` | Asia point-of-control (the "MV" line) — needs the bar's volume |
| `fair_value_gaps/` | 3-candle imbalances and their mitigation |
| `rsi_divergence/` | Confirmed regular divergences at the RSI extremes |
| `equal_highs_lows/` | EQH/EQL liquidity levels within an ATR(50) band |
| `candlesticks/` | 15 classic patterns — a CONFLUENCE source to AND into a setup, never a filter on its own |
| `regime/` | 5 regime labels; each bot owns its own `REGIME_RISK_TABLE` |
| `news/` | Macro-release blackouts; inert before its cache's earliest date, by decision |

### The rest

| Subsystem | What it is |
|---|---|
| `strategies/` | Strategy source by runner platform. Python ports with a GREEN parity gate: `mpc_sos_fade`, `mpc_bleg`, and `mpc_bos` (**narrow** — the gap ladder never ran). **`mpc_realign` has NO gate at all** — no export twin, no CSV, no `compare_realign.py` — so every number it has produced is a lab finding. The end-to-end process, and which step only a human can do, is `docs/STRATEGY_WORKFLOW.md`. |
| `indicators/` | Pine source, split by DECLARATION since 2026-08-13: `strategies/` holds the 12 `strategy(` files, `engines/` the 17 `indicator()` files, and each owns its own CLAUDE.md. ⚠ **Count them with `ls`, never from this line** — it read 16 while there were 18, and one was then deleted. **The declaration decides it, never the filename** — `structure_engine.pine` reads like a strategy component and is an indicator. Includes the from-scratch `smc_engine_v2.pine` rebuild — mid-build, and a **separate track** from the `mpc_assistant.pine` the Python engines were ported from. Do not confuse the two. |
| `education/smc/` | The course material the engines were extracted FROM. Reference a human reads; no code reads any of it. |

### scripts/
Cross-subsystem VPS bootstrap and full-recovery scripts (`bootstrap_vps.ps1` for the MT5/algos side, `bootstrap_ninjatrader.ps1` for the NT8 side). Idempotent, run on a wiped or new VPS. Full run order in `scripts/README.md`. ⚠ **`bootstrap_vps.ps1`'s task list gained `SYS_LEDGERSYNC` on 2026-08-24** — the box commits and
pushes its own decision record hourly, so the backup no longer waits for a Mac to wake up. It is the
one task there that needs a SECRET a rebuild does not restore (`github_token` in the git-ignored
`algos/credentials.json`): without it the task runs, commits, and silently never pushes.
🔴 `install_ledger_sync.sh` **no longer installs anything and refuses if you ask** — its Mac agent
was a SECOND WRITER of an append-only file, and two appends to one file end cannot be merged at any
content (eight hours of hourly conflicts, 2026-08-28). **`--no-push` did not save it: on a shared
branch a local commit is a push with a delay.** The rule is enforced in `ledger_sync.py`, which
refuses to commit records the running machine did not write. Rules live in `algos/CLAUDE.md`; do
not restate them here.

**`setup_learning_mode.sh` (2026-08-11) is the odd one out — it targets a DEV MACHINE, not the VPS**, and is the one-time install behind `/learn <video-url>`: it puts `ffmpeg`/`yt-dlp` on the PATH and clones the third-party `watch` skill (MIT, `bradautomates/claude-video`) to `~/.claude/vendor/`, symlinked into `~/.claude/skills/watch`. ⚠ **The watch skill is deliberately NOT vendored into this repo**, so a clone alone does not make `/learn` work — the skill checks for the install and names the script rather than shelling out to `yt-dlp` itself. **Re-running the script is also how it UPDATES**, which is the part that bites: `yt-dlp` breaks whenever a video site changes its markup, and a stale copy fails on real URLs while looking perfectly installed.

### tools/
Standalone utilities that belong to no subsystem and are run by hand. One today: `tools/skool-transcript/` — rips course video transcripts and indexes them into `education/`. It has its own CLAUDE.md. ⚠ **Nothing imports it and nothing schedules it**, which is the point — it is a dev-machine tool, not part of any deployable, so it is out of scope for the commit hook's money-path rule and for every parity gate.

### education/
The course material the engines were extracted FROM, plus notes. Two halves and they are different things. `education/smc/` is the source library — transcripts, summaries and visual playbooks for the SMC course, with its own CLAUDE.md; it is reference material a human reads, and no code reads any of it. `education/learned/` is where `/learn <video-url>` files a dated note per video (source link, what it covers with timestamps, what is worth acting on). ⚠ **The notes are COMMITTED and videos are never re-watched** — a note already on disk for a URL is read rather than regenerated, because the extracted frames are the whole token cost.

### .claude/
Repo-shipped Claude configuration — available to every clone, unlike `~/.claude/` which is per machine. Three folders.

**`commands/` — the slash commands.** Two kinds, and the split is the point. The **audit** commands look BACKWARDS at code already written: `/audit-engines`, `/audit-strategy`, `/doc-audit`, `/dead-code-audit`, `/prop-firm-rules-audit`, `/quant-review`, `/regenerate-snapshots`, `/session-start`. The **build-time** commands (added 2026-08-12) run BEFORE and DURING the work, and each one exists because a specific class of defect kept reaching the audits: `/spec` (write down what I think you asked for, before code — catches right-code-wrong-question), `/wire-check` (trace every label, config field and registry to the line that consumes it), `/prove` (watch every new test go red, or kill it by mutation), `/measure` (no number without the command that produced it), `/live-safety` (the 22-question checklist before anything touches the live path), `/port` (drive a strategy through `docs/STRATEGY_WORKFLOW.md` and refuse to skip the parity gate), `/run-audit` (take a run id and answer both halves — is this run TRUE, and was this configuration WORTH IT — recomputing every number from the trade list and measuring the feature against a matched control rather than against a run with a different basis). ⚠ **They are prompts, not enforcement** — nothing makes anyone type them. The two things that ARE enforced are the commit hook and the editor guard below, and the commands exist so that when the hook asks "what did you check", there is a repeatable answer.

**`hooks/guard_sensitive_paths.py` — the editor guard.** A `PreToolUse` hook on Edit/Write. A `deployed/` snapshot **asks first**, because a live bot imports from it and an edit there changes what a running bot trades immediately, with no promote and no restart. `engines/`, `strategies/`, `algos/live/`, `algos/shared/`, `backtest/` and `*.pine` attach a one-paragraph reminder of the rule that path keeps breaking, at the moment of the edit rather than 40,000 words away. **Since 2026-08-12 it also watches the CLAUDE.md files themselves** — a file over **40 KB** gets a reminder to move the story out and keep the rule. 🔴 **Since 2026-08-13 it fires on GROWTH, not on size, and that correction matters more than the feature did.** Warning on size alone meant **ten files tripped it on every single edit**, including the ones that are legitimately large — `ChartPanel/CLAUDE.md` is 122 KB and only ~3% of it is movable narrative; the rest is dense engineering reference with measured reasons attached. **A guard that fires on work it should not be criticising is a guard people learn to dismiss, and a dismissed guard is worth LESS than none, because the next reader takes silence for checked.** So a trim now passes in silence and only an edit that ADDS bytes to an already-oversized file has to justify itself. The delta is computed from the tool call itself (`content` for Write, `old_string`/`new_string` for Edit, multiplied out when `replace_all` is set). 🔴 **The reason it lives HERE and not in the commit hook is the whole point: a commit-time warning arrives when the work is already finished, and nobody stops to refactor a doc at that moment — you type the message and move on.** The edit is when the file is open and the context is loaded, so it is the only moment the reminder can change what happens. ⚠ **The 40 KB is MEASURED, not picked** — all 28 files fall into two clumps with an empty gap between them (everything sane lands at 27 KB or below; the next file up is 63 KB), so 40 KB is the middle of that gap and no file is close enough for a paragraph to flip it. At the ceiling's landing, **11 files tripped and 17 passed.** ⚠ **It FAILS OPEN by design** — any error allows the edit, because a broken guard must never stop the work. ⚠ **Which also means its silence proves nothing** — and now that a trim is DELIBERATELY silent, silence is its most common answer. Run **`python3 .claude/hooks/check_guard.py`** — **twenty-one** cases since 2026-08-21, and it is **step 6 of `scripts/run_all_tests.sh`**, because a check nobody runs is not a check. Each asserts a specific verdict, so a guard that always warned and a guard that never warned both fail it. Watched RED by mutation, and **the map in that file's docstring was RUN rather than reasoned** — three entries first written from inspection were wrong, each claiming a mutation was more surgical than it is.

🔴 **The guard had a HOLE for as long as it existed, and it was found by the guard firing on
NOTHING while two files grew (2026-08-21).** The check above reads its byte delta out of the
TOOL CALL, so it can only see an edit made through Edit or Write. An edit made through Bash is
invisible to it — a heredoc, an in-place rewrite, a three-line script. On 2026-08-21
`algos/CLAUDE.md` grew 103,804 → 106,667 bytes and `strategies/python/loss_recovery/CLAUDE.md`
grew to 41,391, both already over the ceiling, and the guard said nothing, because neither edit
went through a tool it watches. **This is the worst failure shape a guard has, and this file
already names it: a dismissed guard is worth LESS than none, because the next reader takes
silence for checked. Here the silence was not even a decision — the guard never ran.**

✅ **Closed by a second hook on `PostToolUse` (matcher `*`, same script) that measures the FILE,
not the tool call**: current bytes on disk against `git cat-file -s HEAD:<path>`, for every
CLAUDE.md git knows about. ⚠ **It was deliberately NOT fixed by pattern-matching Bash for
redirections, in-place edits or python one-liners.** That is a deny-list against an infinite
space of ways to write a file: it is wrong quietly, and it goes stale the first time somebody
reaches for a tool it has not heard of — which is exactly how the browser guard's deny-list is
already known to be its weak half. **A measurement of the file cannot be fooled by HOW the edit
was made, and that is the entire point.** First live confirmation: it fired on this very
paragraph, which grew an already-oversized file.

⚠ **It is a BACKSTOP, never a replacement, and the older half stays exactly as it was.** That
one fires BEFORE the edit, while the file is open and the context is loaded, and the paragraph
above says plainly that the timing is the only reason it changes what happens. This one arrives
after the fact, which is worth less — but it is the only thing that can see what the other is
blind to.

⚠ **It says each file ONCE per session** (a marker under the temp dir, keyed on the session).
It runs after *every* tool call, so the naive version repeats itself forty times before the file
is committed, which is nagging with extra steps — the same mistake the growth rule fixed in
2026-08-13. The first time is the one that can change anything. ⚠ **A trim still passes in
silence**: growth against HEAD, never size alone. ⚠ **It FAILS OPEN in every direction** — not
a git repo, git missing, no HEAD, a timeout, an unwritable marker: all of them allow the action
with nothing printed.

⚠ **A CLAUDE.md with no HEAD version counts as 0 bytes, so a brand-new one born over the ceiling
WARNS — that is a decision, not a fallthrough.** A doc costs the next reader the same context
whether it has been bloated for months or arrived that way this morning, and "it is new" is not
a reason for it to land at 50 KB unremarked. The alternative — stay quiet until its first commit
— puts the warning at the one moment this repo has already measured to be useless, when the work
is finished and nobody stops to refactor a doc.

⚠ **It costs ~0.16s per tool call** — MEASURED on an idle machine, three passes of 20 runs over 33 CLAUDE.md files, of which ~0.06s is python interpreter startup that any hook here pays —
one `rev-parse`, one `ls-files`, and ONE batched `cat-file --batch-check` for the whole set
rather than one call per file. The per-file fan-out is the shape that made a version endpoint
slower every time either of us pushed, and it was avoided here on purpose.

🔴 **THE AUDIT THAT FOLLOWED FOUND A SECOND HOLE, BIGGER THAN THE FIRST (2026-08-21).** Nothing
ever "got around" this check — it has never blocked anything, it only prints. The real finding
is when it speaks. **It reads the file's size BEFORE the edit, so on the edit that takes a doc
OVER the ceiling the doc is still under it, and the check says nothing. It only ever starts
complaining about files that are already a problem — the moment it can do least good.** MEASURED
over the full history of all 33 docs: **every one of the 11 currently oversized files crossed
from below, and not one of them was warned at the crossing.** Two of those crossings happened
with the guard live and silent — `indicators/strategies/CLAUDE.md` went 38,766 → 69,605 bytes in
one commit on 2026-08-16, and `strategies/python/loss_recovery/CLAUDE.md` went 26,745 → 41,391
on 2026-08-21. ✅ **The after-the-fact check closes this too, because it measures the file once
the edit has landed** — proven on a fixture that crosses in one go, and it is a case in
`check_guard.py`. ✅ **And the before-the-edit half now judges the size the file is ABOUT TO BE rather than the
size it is** (Aaron's call, 2026-08-21), so the crossing is caught at the one moment it can
still be prevented. It costs no extra nagging — a doc well under the ceiling has to be handed
an edit big enough to cross before it hears anything. ⚠ **A file that does not exist yet counts
as 0 bytes rather than being skipped**, so creating an oversized CLAUDE.md warns too; that
deliberately matches what the after-the-fact half does with a doc that has no committed
version, because the two halves disagreeing about what a new file means is how somebody ends
up trusting the quieter one.

⚠ **THE 40 KB'S ORIGINAL JUSTIFICATION HAS ERODED, and that is worth saying rather than leaving
the paragraph above to read as still-true.** The number was picked as the middle of an empty gap
**36,050 bytes wide** (largest sane file 27,116; next one up 63,166). Re-measured 2026-08-21:
that gap is now **7,823 bytes** — `indicators/engines/CLAUDE.md` sits at 33,568 just under, and
`strategies/python/loss_recovery/CLAUDE.md` at 41,391 just over. **So "no file is close enough
for a paragraph to flip it either way" is no longer true**, and 40 KB is now a judgement rather
than a measurement. ✅ **KEPT at 40 KB anyway (Aaron's call, 2026-08-21).** ⚠ **Chasing the
distribution upward is how a limit stops meaning anything** — the honest reading is that the
repo grew into the number, not that the number is wrong. **Re-measure this gap before ever
moving it, and record the new width here; do not move it because a file is sitting near it.**

⚠ **The direction of travel is good and the audit should say so.** Since the ceiling landed,
seven of the eleven oversized docs have SHRUNK, several by a lot — `command-center/backend`
−83 KB, `command-center/frontend` −75 KB, `indicators` −166 KB, `command-center` −117 KB, and
`strategies/python/mpc_sos_fade` −102 KB (307 → 205 KB, 2026-08-27). The reminder is working on
the files it can reach.


⚠ **MEASURED there, and it bounds what a doc migration can ever achieve: moving EVERY explanation
out — prose, tables and run numbers — still left 205 KB, because ~70% of that file is rules WITH
their justification, which must stay next to the code. Past that point, reaching the ceiling is a
decision to compress or DROP rules, not a migration. Say which is being asked for.**

🔴 **A subsystem fragment is ANCHORED at the repo root (2026-08-13, `subsystem_matches`)** — a fragment starting with `/` matches only paths actually under that top-level dir, while `.pine` is about what the file IS and still matches anywhere. It was a plain substring test until `indicators/engines/` was created and a Pine file was about to be told it is a canonical Python engine. **The standing lesson: a directory RENAME can silently re-aim a guard** — nothing fails and no test goes red; the only symptom is correct-looking advice about the wrong file. Story: `HISTORY.md`.

⚠ **The bloat it is guarding against was measured the same day and the root file was the worst case: 36 KB of its 69 KB — 53% — was `## System Summaries`, a paragraph per subsystem restating what that subsystem's own CLAUDE.md already said.** That section loads on EVERY session whether or not you go near the code it describes. **The duplication is also what makes the drift**: the 2026-08-12 doc audit found three files claiming there were no live bots, and the subsystem file was the one that was right. Hence the standing rule the guard's message repeats — **a fact lives in exactly ONE CLAUDE.md, the one next to the code. Parents ROUTE, children EXPLAIN.**

**`skills/` — `learn/` (2026-08-11)**: `/learn <video-url> [focus]` watches a video and files a durable note to **`education/learned/`** (dated markdown, source link, what it covers with timestamps, what is worth acting on). It drives the third-party `watch` skill for the watching — captions first, `ffmpeg` frames second, Whisper API only when a video has no captions — and adds the note. ⚠ **The note is the deliverable and the chat reply is deliberately short**: a note that lists the TOPICS a video mentioned is worthless, so it records what the thing actually IS. ⚠ **The notes are COMMITTED and the videos are not re-watched** — a note already on disk for a URL is read rather than regenerated, because the frames are the whole token cost. ⚠ **No speech-to-text key is configured** (`~/.config/watch/.env`, per machine, git-ignored by living outside the repo): captions cover most of YouTube, and a caption-less source — a Loom, a TikTok, your own screen recording — comes back frames-only and says so. A free Groq key retires that.

## The MCP servers — what Claude is handed instead of a shell

**Added 2026-08-20/21.** `.mcp.json` at the repo root wires up three servers, so they arrive
with a clone and behave the same on both machines. Each of us approves them once, on the first
session after pulling. Full build story, measurements and one fix that was backed out:
`HISTORY.md` → *The MCP servers arrive*.

| Server | What it is for |
|---|---|
| **browser** | Opens the Command Center in a real browser — the answer to rules 7 and 9, which are about features nobody ever RAN |
| **tradingbox** | Seven named trading-box operations instead of an open SSH prompt |
| **lab** | Backtests, and a comparison that refuses when the two runs were not measured the same way |

**The one idea behind all three: a rule that lives in somebody's memory is a rule that gets
broken on a Friday.** Each server moves a rule this repo keeps re-learning into something that
cannot be talked out of it.

🔴 **browser — the page can be clicked, and the live buttons cannot.** The backend talks to the
trading box, so a click is a real action. `.claude/mcp/browser_guard.js` is injected ahead of
the app's own scripts and rejects bot start/stop/restart, promote, strategy deploy and delete,
account writes and agent starts INSIDE the browser; they never reach the backend. Promote
PREVIEW and every lab write stay allowed — those cost compute, never money, and a guard that
blocks the useful half gets switched off. ✅ **A missing guard file makes the server refuse to
start**, so there is no unguarded state. ⚠ **Not a security boundary** — it makes an accident
impossible, not an attack. ⚠ **It runs headless, which MEASURED costs nothing** except being
able to watch. ⚠ **Google's font hosts are allowed deliberately**: blocked, the page still
rendered and screenshotted happily in the wrong typeface with one console error as the only
sign, and a screenshot that looks plausible and is subtly wrong is worse than one that fails.

🔴 **tradingbox — the point is what is ABSENT.** No hard kill, no fleet kill, no lock deletion,
no account edit, no password change, no user management, no agent start, no restart.
`taskkill /f /im python.exe` killed the live bot for three days; it is not on the menu, so a
typo or a bad quote cannot reach it. ⚠ **The two writes take a phrase naming the bot and the
action** — a speed bump against a slip, not a wall against intent, and it refuses *before* the
network. ⚠ **Every reply says whether the question was ASKED**: unreachable returns no payload,
never a `running: false`. That is rule 1.

🔴 **lab — the comparison refuses when the basis differs.** Rule 11 has been broken four times
in this app, always the same way: the difference column becomes the thing that lies. Window,
timeframe, instrument, costs, broker, sizing — if any of them moved, the tool refuses and names
the field. ⚠ **The basis is READ OFF the request contract, not chosen** — `check_lab.py` parses
`BacktestRunRequest` out of this repo, so adding an input to a run turns red until somebody
decides whether it changes what the run is measured on. ✅ **It caught a real one on
2026-08-25**: a run input that OVERWRITES a basis field is request-time, not basis, and a tool
handing over the resolved field must PIN it or the lab re-resolves it and a copied basis is
silently measured differently. Story: `HISTORY.md` → *The switch that overwrote the basis*. ⚠ **Net dollars are reported under the
unit-free numbers, never above** (rule 6), and the breakeven-scratch count always travels with
the win rate.

⚠ **All three are FRONT DOORS onto the Command Center backend, never second implementations** —
so the app must be running, and each says so plainly when it is not. The one exception is the
trading box's ledger tool, which reads committed files and keeps working regardless.

⚠ **The MCP wire is hand-rolled on the standard library**, because the official SDK needs Python
3.10 and every interpreter here is 3.9.6. Adding a tool must not mean adding a runtime.

**Prove them rather than trusting them** — they are steps 4, 5 and 7 of `scripts/run_all_tests.sh`,
and every one was watched RED by mutation:

```
node   .claude/mcp/check_browser_guard.js
python3 .claude/mcp/check_tradingbox.py
python3 .claude/mcp/check_lab.py
```

🔴 **BOTH PROMOTE TOOLS ON THE TRADING BOX HAD NEVER WORKED, and the check passed the whole
time (2026-08-26).** They POSTed with no body to an endpoint whose body is required, so the
Command Center answered HTTP 422 every single call. `check_tradingbox.py` was green because
every case it had asserted what a tool REFUSES, or how it reports a dead backend — **and a tool
that always fails passes both of those beautifully. A check that only tests the sad paths
certifies a tool with no working happy path.** It now records the request and asserts the body,
field by field. ⚠ **The Command Center's own button was never affected** — it sends
`{pull, restart}` and was verified end to end the same day. ⚠ **The MCP sends `restart: false`
on purpose**: this server's whole design is what it does NOT offer, so a promote from here moves
the code and stops, and a human restarts the bot.

⚠ **When a new route touches money or the live box, it goes in the browser guard and the trading
box in the SAME change.** Both are deny-lists by design — a route they have never heard of is
allowed. That is the honest trade for not blocking the lab, and it is the part that goes stale.

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

# Stop the running bot by ASKING, never by killing. It polls its instance dir every 10s,
# writes a shutdown record, and clears the file. Give it ~30s, then confirm it is gone.
ssh forexvps "echo stop > C:\trading\algos\markets\fx\instances\mpc_sos_fade_demo\stop.request"
ssh forexvps "wmic process where \"name='python.exe'\" get commandline"

# Restart onto the new version. SYS_MONITOR also brings a dead bot back on its own within
# ~60s — but this is the deliberate path.
ssh forexvps "schtasks /run /tn SYS_STARTUP"
```

🔴 **Ask, do not kill — and it is not politeness.** A hard kill gives the bot no chance to
write its `shutdown` record, so the next startup reports *"the previous run ended without
shutting down."* That sentence is the **silent-death detector**, and while this workflow said
to kill, it fired on every restart anybody performed on purpose. **An alarm that fires when
you press the button is one you learn to scroll past**, and the thing it catches is the one
failure here that leaves no other trace. `stop.request` is the graceful path (`runner.py` →
`STOP_FILE`); the Command Center's Stop button has used it since 2026-08-07 and the CLI was
the half left behind. Story: `HISTORY.md`, the 2026-08-13 deploy that alarmed on itself.

⚠ **Escalate only for a bot that ignored the request** — wedged, blocked in an MT5 call, or
running code that predates the file. Delete the request afterwards, since nothing consumed it:

```bash
ssh forexvps "wmic process where \"name='python.exe' and commandline like '%--bot mpc_sos_fade_demo%'\" call terminate"
ssh forexvps "del C:\trading\algos\markets\fx\instances\mpc_sos_fade_demo\stop.request"
```

⚠ **NEVER `taskkill /f /im python.exe`.** It kills every Python process on the box — the
trading bot, the Telegram bot, the MT5 backtest agent and the NT8 agent — and it is what
killed the live bot on 2026-07-31 (dead for three days; nothing restarted it then). This
workflow told you to run it, which is how it kept happening. Kill ONE bot by its commandline,
as above.

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

🔴 **THE SAME RECORD BROKE THE SAME WAY AGAIN ON 2026-08-27, AND THE CAUSE WAS LINE ENDINGS.**
The trading box writes the decision record with a carriage return; the Mac does not. Both machines
commit it, git stores whatever bytes it is handed, and two copies that disagree on EVERY line
conflict on every line — **even though both sides had only ever APPENDED.** Hit twice inside ten
minutes while pushing a doc change, and it was harmless only because a person was standing in front
of it. Unattended, it is the 2026-08-05 failure exactly: the sync does not nag, it stops, and the
day sits on one machine alone.

✅ **FIXED AT THE STORAGE LAYER by `.gitattributes` at the repo root** — `*.jsonl` and `*.log` are
declared text, so git normalises them however they arrive and the two machines store identical
bytes. ⚠ **Deliberately NOT fixed by making an agent write the other ending.** That is a rule living
in one script's memory, and this repo already knows what happens to those: the next tool that
touches the file has never heard of it. **Nothing has to remember anything for this fix to hold.**
⚠ **The broad glob was CHECKED, not assumed** — all 64 tracked files of those two types are these
bot records, so nothing else is touched. ⚠ **62 existing files were renormalised in the same
commit**, and each was verified byte-identical to its old version once carriage returns are ignored:
a record of what the bot decided may not be edited to fix a merge problem. ⚠ **Proven rather than
reasoned** — a carriage-return file was written, staged, and the stored blob confirmed to hold none.

⚠ **The deeper hazard is unchanged and this does not retire it: TWO machines still commit this file,
and exactly one may push.** The rule stops them conflicting on formatting. It does not stop them
diverging, and a same-day divergence still needs a human to merge — check that the fuller side is a
strict superset before taking it, because on 2026-08-27 it was, and that is the only reason nothing
was lost.

When a change genuinely needs no doc update, say so **in the message** — the reason is
required and is recorded where the other person can read it:

```
fix(chart): correct a comment typo

DOCS: none - comment only, no behaviour change
```

🔴 **`git add -A` FROM A SECOND SESSION BREAKS THE PAIRING THE HOOK EXISTS TO ENFORCE, and it
happened on 2026-08-25.** The docs check asks that a changed file's owning CLAUDE.md be in the SAME
commit. It cannot ask the reverse — that a CLAUDE.md paragraph ships with the code it describes —
so a blanket stage from a session working on something else sweeps up another session's in-progress
doc edits and lands them alone. Commit `89a6324` (an MCP fix) carried 19 lines of this file
describing a test step that lived only in an uncommitted working file, so **`main` documented step
8 of `scripts/run_all_tests.sh` while `main`'s own copy of that script still said seven steps.**

⚠ **Nothing failed and no check went red** — the same shape as the ruff carve-out that `git add -A`
undid, and this file already names that one. **Stage by PATH when two sessions share a clone**, and
before committing, read `git status` for files you did not touch.

⚠ **The direction of the damage is the part to remember: a doc that arrives EARLY reads exactly
like a doc that is right.** The next person greps for the step, finds the paragraph, runs the
script, and sees seven — and the honest conclusion available to them is that the script is broken.

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

---

## Formatting, linting and the test gate

**Added 2026-08-14.** Until this date the repo had no formatter, no linter and no automated test
run — the standing practice was to run the suites by hand before committing, which is a practice
rather than a mechanism.

**One command installs everything:** `./scripts/install_dev_tools.sh` (run by `./go`, named by the
pre-commit hook when a clone lacks it).

| | tool | where |
|---|---|---|
| Python — format + lint | **ruff** 0.16.3, pinned | `.venv-lint/` (git-ignored), `requirements-lint.txt`, config in `ruff.toml` |
| TS/TSX/JSON/CSS — format | **prettier** | `node_modules/`, config in `.prettierrc.json` |
| TS/TSX — lint | **eslint** | `eslint.config.mjs` |
| Which tool sees which file | **lint-staged** | `lint-staged.config.mjs` |
| pre-commit | format + lint the STAGED files | `.githooks/pre-commit` |
| pre-push | repo-wide lint + format sweep (**NOT the tests**) | `.githooks/pre-push` |

**Prettier cannot format Python** — no official support, the community plugin is abandoned — so
ruff owns `.py` and prettier owns the frontend. **`lint-staged` is the common ground**: it is a node
package, but it runs whatever command you point at a glob, so one config drives both languages from
one hook.

🔴 **NO HOOK RUNS THE TESTS. `pre-push` ran the full suite for one day and it was removed on
2026-08-14 (Aaron's call).** MEASURED: 4:21 for the root suite (1,725 tests) + 2:17 for the backend
(1,014) = **~7 minutes on every push**. That is the same argument that kept the suite off
`pre-commit`, one step later: a seven-minute guard is one people route around, and
`LWG_SKIP_TESTS=1` on every push is indistinguishable from no gate while reading like one.

⚠ **State the loss plainly rather than letting the next reader find it: a broken suite can now
reach `main`, and the first to know is whoever pulls it.** `scripts/run_all_tests.sh` is still the
one command — it is now a thing a PERSON runs, and both the hook's output and its header say so. If
that bites twice, the answer is a FASTER suite rather than a slower hook.

✅ **That answer was taken on 2026-08-15 and the suite is ~2x faster: ~7 minutes → 3:16 end to end
through `scripts/run_all_tests.sh` (frontend typecheck included), and 2,811 tests still run.** Nothing was deleted or excluded — an audit for dead, vacuous and duplicated
tests found **none** (7 assertion-free tests, all deliberate "must never raise"; 0 tests for
deleted code; 0 real duplicates). **The count was never the problem: 67 tests out of 2,811 were
the entire runtime, and 2,744 of them finished in ~130s all along.** Full record and the
per-file numbers: `docs/TEST_SUITE_PERFORMANCE.md`.

The four things that made it fast, in the order they were worth doing:

| | fix | measured |
|---|---|---|
| an N+1 **in production code** (`services/bot_versions.py` ran one `git show` per commit) | one `git log --name-only` | 1,080 subprocesses → 14; that file 53.7s → 8.7s |
| the same 31 MB bar cache re-read and the same engine replayed once per TEST | `lru_cache` on the read, the slice and the replay | 62s → 21s |
| eight strategy replays where four are needed; one cache collision fired per test | share them | 182s → 80s; 86s → 25s |
| both suites single-core on a 12-core box | `pytest-xdist`, `-n auto --dist load` | root 202s → 119s, backend 150s → 45s |

🔴 **The first row is the transferable one: a slow TEST is sometimes a defect in the code under
it.** That git fan-out scaled with repo history, so it made the `/version` endpoint slower every
time either of us pushed — and it had been invisible for as long as it existed, because its output
was byte-identical either way. **Nothing in a result can show you a cost.**

⚠ **`backtest/tests/test_reprice.py` is ~68s of the root suite's 119s, alone**, and it is four
genuine two-year replays. Everything else runs in ~44s. **Any further speed is a COVERAGE decision,
not a scheduling one** — say so out loud rather than quietly narrowing a window.

✅ **RE-MEASURED 2026-08-27: `scripts/run_all_tests.sh` is 3:16 → 2:00 end to end, all green, and
NOT ONE TEST WAS TOUCHED TO GET THERE.** The whole gain came from making the REPLAY faster — the
regime map, the bar loop, a leg-latch prune that re-sorted 20,000 keys per bar and a pivot detector
that copied 2,000 to read 31 (`HISTORY.md` → *A full-history backtest went from ten minutes to a
minute*). ⚠ **The per-file split above is from 2026-08-15 and predates that work, so the 68/119
figures no longer describe this suite** — the total is measured, the split is not. Re-measure before
quoting either half. 🔴 **This is the 2026-08-15 lesson arriving from the other end and it is worth
saying plainly: a slow TEST is sometimes a defect in the code under it, and the reverse also holds —
fixing production code is how a suite gets faster without a single scheduling decision.**

⚠ **The suites are only parallel-safe because the shared state is per-test** (`tmp_path` DBs, the
`_no_live_vps` interlock, scratch git indexes). A new test that writes a fixed path breaks other
tests non-deterministically, which is the worst failure shape a suite has. ⚠ **`--dist load`, not
`loadfile`** — see the reasoning in `scripts/run_all_tests.sh`, and note that the intuitive choice
measured slower.

### 🔴 If the tests will not START on this machine, it is the xdist dependency — fix it, do not work around it

**The first pull after 2026-08-15 needs one install, and a fresh clone needs it too.**
`scripts/run_all_tests.sh` passes `-n auto` to both python suites, and `pytest-xdist` was added to
`command-center/backend/requirements.txt` in the same commit — but **nothing re-installs
requirements on a `git pull`**, so a machine that had a working venv yesterday will not have the
package today.

**Symptom:** the script prints `pytest-xdist is not installed in …` and exits 1 before running a
single test. **Fix, and it is the whole fix:**

```bash
command-center/backend/.venv/bin/python -m pip install -r command-center/backend/requirements.txt
```

⚠ **Do NOT "fix" it by dropping `-n auto`, by running bare `pytest`, or by exporting
`PYTEST_PARALLEL=` permanently.** Those all work and they all hide the missing package while
putting the suite back to one core on a twelve-core box — the exact state this change existed to
leave. `PYTEST_PARALLEL=` is for a deliberate one-off serial run when you are debugging a suspected
parallelism problem, and nothing else.

⚠ **`./go` and `command-center/start.sh` DO install it** (they run `pip install -r
requirements.txt`), so launching the app once is the other way out. **Nothing else does** — not
`post-merge`, not `conftest.py`, not `install_dev_tools.sh`, which owns `.venv-lint/` and has no
opinion about the backend venv.

⚠ **The refusal is deliberate and must stay a refusal.** pytest exits **4** on an unrecognised
`-n`, which reads as a suite failure and sends the reader at the tests rather than at the venv; and
a silent fall-back to serial would turn a missing package into *"the tests are slow today"*, which
nobody investigates. **This is the same rule as everywhere else here: never let *cannot run* and
*ran and passed slowly* be the same outcome.**

**What `pre-push` does now costs ~3s and is still worth having**: `pre-commit` only ever sees
STAGED files, so a `--no-verify` commit, a rebase that resurrected an old file, or an edit from
another tool reaches a branch unformatted. This is the repo-wide sweep that catches them.
⚠ **The 3s is entirely down to CACHING, and it is all eslint** — MEASURED: ruff clears 628 python
files in **0.2s**, prettier takes **6.4s**, eslint takes **28s** (70% of the hook) because
`typescript-eslint` is type-aware and rebuilds the TS program. `--cache` on both makes it **1.9s**
warm. A first run after a frontend pull pays the full ~35s again — that is the cache working.
⚠ **The cache files are git-ignored**: they key on local file mtimes, so a checked-in cache is a
linter skipping files it has never read on this machine.

⚠ **"Run all tests" is NOT a bare `pytest`** — the root collects 2,670 tests and dies on a
collection error, because the backend has its own `pytest.ini`, its own venv, and imports
`services`/`routers` by bare name. Use `scripts/run_all_tests.sh`. It runs all three suites even
when one fails: stopping early reports the others as unknown, and unknown reads as fine.

✅ **Frontend logic CAN be gated when it is pulled out of the canvas.** Step 8 runs
`command-center/frontend/scripts/check_trade_geometry.mjs` with nothing running — the backtest
chart's trade box decides from PRICES how far its adverse band reaches and whether the exit is
drawn at all, and both were wrong on real trades for as long as they lived inside a klinecharts
callback that only a browser could reach. ⚠ **The lesson is about REACHABILITY, not about charts:
logic with no seam a test can grab is logic nobody checks.** The rules are in
`command-center/frontend/src/components/ChartPanel/CLAUDE.md`.

🔴 **Step 9 (2026-08-27) is the same move for a harder case: a rule written TWICE, in two
languages.** `check_param_conditions.mjs` drives the run form's visibility evaluator, whose twin is
the lab's own `stress_tester.param_is_reachable` — and the two have already disagreed in silence, a
number that compared equal in Python and unequal in JavaScript leaving a dead control live on
screen. ⚠ **The CASES are the shared artifact, not the code**: one fixture file, read by the node
check here and by the python test in step 2, so a shape one side learns and the other does not
fails on the side that did not learn it. ✅ It found a real disagreement on its first run. **When
you write the same rule on both sides of a boundary, make the two answer ONE list of cases** —
mirroring them by hand is how they drift, and neither side looks wrong alone.

⚠ **Playwright is deliberately NOT in the gate.** Its config has no `webServer` block on purpose —
this backend talks to a live VPS and a live MT5 terminal, so a runner that boots it on demand can
start things on the trading box. `./start.sh` then `npm test` stays a person's decision; `tsc
--noEmit` is the half that needs nothing running.

### 🔴 Both hooks are built around the UNATTENDED committer

`algos/tools/ledger_sync.py` commits AND pushes the live bot's decision record twice a day from the
Mac with nobody watching, staging only `.jsonl` and `.log`. **A rule that fires on a robot's commit
has no human to read its message: it does not nag, it silently stops the job** — which has already
happened twice on the docs half of `commit-msg` (2026-08-05).

- **`pre-commit` checks SCOPE BEFORE TOOLS** — nothing lintable staged ⇒ exit 0 without ever asking
  whether node is installed.
- **`pre-push` skips a push carrying no code**, on a POSITIVE trigger rather than an ignore-list, so
  a new data format added tomorrow is skipped by default — the safe direction.
- Deliberate skip: `LWG_SKIP_PREPUSH=1 git push` (`LWG_SKIP_TESTS=1` still works — it is what is in
  everyone's muscle memory). It prints a loud line and has no silent form.

### The rules were MEASURED, not picked

Every number behind them is in `HISTORY.md` → *Formatting and linting arrive*. The rules themselves:

- **`line-length = 100`**, because that is how this code is already written (p90 94). Ruff's default
  88 would rewrap 21,040 lines against 2,647.
- **`target-version = "py39"`** — the lowest runtime here. It is why `UP` is not selected: those
  rules propose 3.10+ syntax the backend venv cannot run.
- 🔴 **`E402` is OFF because the engine imports DEPEND on breaking it** — 193 files do
  `sys.path.insert` then `from market_structure import ...`. ⚠ **That makes the import SORTER the
  thing to watch, and it was checked rather than assumed: 0 hoisted across all 193.** Re-run that
  check if `I` is ever swapped for a different sorter.
- 🔴 **`F401`'s "unused" is per-MODULE, so `--fix` DELETES a RE-EXPORT and nothing fails until
  run time.** It cannot see `other_module.NAME` read in a different file. It did exactly that on
  2026-08-14 to `sizing_pipeline.MODES`, and one test caught it — an `AttributeError` inside a
  sizing branch, i.e. a crash on a real backtest rather than on import. ⚠ **Checking `__init__.py`
  files is NOT enough** — that reasoning covers a package's public API and a plain module launders
  a re-export straight past it. **A deliberate re-export needs `# noqa: F401` and a comment naming
  its consumer**, or the next `--fix` removes it again.
- **`E741`, `B904`, and eslint's React Compiler rules are off or at warn** — each fires dozens of
  times on code that ships and works. `rules-of-hooks` stays an error: a conditional hook call is a
  crash, not advice.
- 🔴 **A rule nothing can AUTO-FIX blocks the ratchet, and that is worse than it sounds.**
  `pre-commit` runs `ruff check --fix`, which exits non-zero while any finding remains — so a
  legacy file carrying one un-fixable finding is a file you cannot commit a one-line change to.
  Six such rules (`B023`, `F841`, `B007`, `B008`, `B017`, `E731`) were selected wholesale, never
  measured, and turned 46 shipping-and-working sites into a wall; each is now off with its count
  and the reason it was READ rather than waved through, in `ruff.toml`. ⚠ **Before selecting a
  rule, ask what it does to the files you are NOT going to fix** — a wall gets `--no-verify`d, and
  that leaves no trace.
- **Markdown is NOT formatted.** Prettier pads table columns, which grows a CLAUDE.md ~35% in pure
  whitespace and would trip this repo's own doc-growth guard on every commit.

### The ratchet, and the one bulk pass that was allowed through it

413 of 627 python files predated any formatter. A bulk pass ran on **2026-08-14** and covers 424 of
them — but **`engines/` and `strategies/` were carved OUT of it by rule 22**, and how that was
decided is the part worth keeping.

**Rule 22 was applied by RUNNING all 14 gates, not by reasoning that layout cannot change
behaviour.** It cannot — and that is exactly the confident argument a gate exists so you do not
have to trust. **Only the 5 engines whose gate ran GREEN were reformatted** (`market_structure`,
`rsi_divergence`, `session_volume_profile`, `candlesticks`, `vwap`). `fibonacci`, `order_blocks`,
`sessions`, `liquidity`, `fair_value_gaps`, `equal_highs_lows` and **all four strategies including
the LIVE `mpc_sos_fade`** were reverted to HEAD and are still unformatted.

🔴 **9 of the 14 gates COULD NOT RUN, and that is the finding.** Exports are git-ignored scratch
(`.gitignore` → `*VANTAGE_*.csv`), so **which engine you can gate depends on what is sitting on
that machine**, and a fresh clone can gate almost nothing. ⚠ **Rule 22 is therefore unsatisfiable
on demand for most of this repo — it blocks work rather than gating it.** Fixing that is a decision
about where exports live, not a formatting job.

⚠ **A "pre-existing" red is still a red.** `fibonacci`, `sessions` and `liquidity` were re-run
against HEAD in a throwaway worktree and gave byte-identical output. That exonerates the formatter
and changes nothing about whether they may be committed. They may not.

⚠ **`regime/` and `news/` were reformatted and have NO parity gate by construction** — no Pine
source, so no `compare_*.py` can exist. Unit tests are the only gate they will ever have. Do not
read this as rule 22 having a general exception.

🔴 **THE CARVE-OUT IS ENFORCED IN `ruff.toml`, NOT BY REMEMBERING WHAT YOU REVERTED.** It was
first done with `git checkout --` on those paths, which holds exactly until the next
`ruff format .` over the whole repo — which re-formatted every one of them, `git add -A` staged
it, and the LIVE `mpc_sos_fade` shipped in a commit whose message said it was excluded. **Nothing
failed and no test went red; the commit message was the only thing that disagreed with the tree.**
⚠ **A decision that lives in your memory of what you reverted is not one the next command
respects.** ⚠ **The exclusion only binds an explicitly-named path when `--force-exclude` is
passed** — `lint-staged.config.mjs` passes it on both ruff commands, the same flag that protects
`deployed/`.

Per-gate bar counts and the full verdict table: `HISTORY.md` → *The bulk reformat, and the nine
gates that could not answer*. Outside those two trees the repo still converges as it is worked on.

🔴 **`deployed/` is excluded in `ruff.toml` AND the hook passes `--force-exclude`** — that flag is
what makes an explicitly-named path still honour the exclusion. An edit there changes what a running
bot executes, with no promote and no restart.

⚠ **Ruff's version is PINNED**, or two machines reformat the same file differently and each undoes
the other on every commit.

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
- Put a non-ASCII character straight after an unbraced `$VAR` in a shell script — write `"${VAR}…"`. macOS's `/bin/bash` is 3.2.57 and folds the character's leading byte into the name, so `set -u` kills the script as *unbound variable*. Bash 5 parses it fine, so **it only ever breaks on the machine that did not write it**. *(`setup_learning_mode.sh` shipped broken — one line, the only one where an ellipsis touched a variable. Detail in `HISTORY.md`.)*
