## Communication Rules — Non-Negotiable

- Plain English only. Short sentences.
- **Never write a code name in a reply to ANYONE — no variable, parameter, config field, function or class names.** Say what the thing DOES: "the setting that decides what triggers the trade", not its name. If the reader needs to find it themselves, quote the label shown in the Command Center. File paths and file links are fine — those are places, not code. Write a real name only when they ask for it or ask to see the code. *(Aaron, 2026-08-20: "you keep using it as though I'm reading code." A sentence built round a raw name carries no information to the person reading it, so it hides the answer instead of supporting it. It applies to every person working this repo, not just the one who asked — nobody here reads as a compiler.)*
- **Answer in a short bulleted list, grouped by outcome.** Findings go under **Broken** and **Working**, worst first, and anything needing a decision goes last under its own heading. One line per bullet — a fact and its consequence, nothing else. No nested bullets, no closing summary repeating what the bullets said. *(Aaron, 2026-08-24: "this is the most efficient way to speak to me." He asked twice in one session after two prose answers, so a long-form reply is now the exception that has to earn itself. It applies to everyone working this repo.)*
- **Prose only when he asks for it, or when a bullet would hide the reasoning** — a design trade-off, a measurement that needs its caveat attached, why something broke. Then keep it to a paragraph and put it UNDER the bullets, never above them.
- Say the answer in the first bullet. Never build up to it.
- **Keep the headings; cut the CONTENT to the bone.** The section structure above stays, "needs a decision" included — what gets shortened is each bullet: state the fact, drop the explanation, and let him ask you to expand on the one he cares about. *(Aaron, 2026-09-09. Applies to everyone working this repo.)*
- No preamble. No "Great question." No "Sure, I can help with that."
- Spawn subagents for routine tasks. Work sequentially unless the task explicitly requires parallel execution.

## The Mandate — who decides what

**Aaron's standing instruction, 2026-09-09, and it governs every session in this repo.** *"You know
better than me when it comes to these things... I expect that you will not cut corners on anything
to satisfy my desires... You will push back on me when what I want is just wrong and suggest what is
statistically and architecturally right... Still let me be the imaginary and the requirement setter,
but you are the one who is my personal expert quant partner. All recommendations are always
welcomed."*

- **He sets the vision and the requirements. The agent owns statistical and architectural
  correctness** — a judgement call on strategy design, statistics, risk or platform structure gets
  MADE and stated, never handed back as a menu of equal options. The goal is the most money he can
  make **sustainably**, which is a durable edge rather than a flattering number.
- **A corner cut to satisfy the ask is a defect, not a favour.** If the fast route costs coverage,
  correctness or sound structure it is off the table — say what the honest route costs instead.
- **Push back OUT LOUD when the ask is wrong**, then name what is right. He asked for this
  explicitly, so silence is a failure rather than politeness. If he reaffirms after hearing the
  objection that is his call, and the full thing gets built under stated assumptions.
- **Everything from here is built reusable and modular** — designed so a later feature can reuse it,
  no one-off wiring.
- ⚠ **This does NOT license speculative abstraction, and over-engineering is also a corner cut.**
  The standing resolution is the one already in `algos/CLAUDE.md`: generic at the SEAM, concrete in
  the IMPLEMENTATION. Never stub a bot you cannot test — a stub is an empty registry that answers
  confidently, which is rule 8.
- ⚠ **The reason this is written down rather than remembered: a yes-man here costs money.** Every
  expensive failure in `HISTORY.md` shipped looking fine, with docs written and a green suite.


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
17. **Refusing is the answer — except at the venue lot ceiling, where it is RESIZE, and the difference is WHICH LAYER acts.** Never shrink an ORDER to fit: it is not the trade the emulator holds, the two grade different R, and the bridge halts. *(Below broker minimum and unaffordable still mean NO TRADE.)* 🔴 **Above the venue maximum the position is resized in the STRATEGY's own sizing** (`backtest/portfolio/account.py`, one seam every bot reaches), so both sides book the same quantity. **Clamping at the DECISION is coherent; clamping at the ORDER is the bug this rule was written about.** Default 100 lots, every strategy. *(Aaron's call, 2026-09-02 — refusing skipped setups worth having. Numbers and the backstop: `backtest/CLAUDE.md`, `algos/shared/order_sizing.py`.)* ⚠ **Past the ceiling risk-per-trade falls and compounding turns linear** — safe in the direction that matters, and why a long run stops describing a tradeable account.
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

**MEASURED 2026-07-29 (Run 12), and it cuts both ways: you may not buy trade count by loosening a strategy either.** Four ways of relaxing the SOS Fade entry rule to add trades were replayed over 6.5 years and every one lost money or was noise. The reason is structural, not specific to SOS Fade: **with one position slot, an extra setup does not ADD to the book, it QUEUES in front of it** — the loosened runs displaced 17, 36 and 2 real trades respectively, and one displaced winner was worth +16.5R on its own. Corollary worth remembering before any future "let's take more setups" idea: **spending drawdown on SIZE beat spending it on FREQUENCY** — the shipped 164 trades at `exec_risk_pct = 12.5` made 832x at 64.2% max drawdown, while 337 loosened trades at half risk made 426x at 64.9%. So the honest routes to frequency stay the ones this section already names (another LEG, another instrument, another timeframe), not a looser filter.

Two things this does NOT excuse, and which must still be said plainly when they're true:

1. **A small sample still means wide error bars on that strategy's own edge.** Stacking five strategies does not make strategy A's edge more certain; it just spreads A's outcomes over more calendar time. Confidence in each edge is still earned per strategy. Say so when it matters — as a caveat on a number, never as a reason to refuse the work.
2. **Stacking only reduces drawdown if the strategies are actually independent.** Everything here reads the same `engines/market_structure/` on the same instrument. Two "different" strategies off one structure stream can fire together, lose together, and behave as one position at 2x the size. Correlation between strategies is a real open question in this repo, not a solved one.

**The suite is carved up by LEG, not by signal.** Aaron's answer to the correlation problem (2026-07-27): the strategies share a confluence source on purpose, but each takes a different part of the move — think Elliott waves. SOS Fade SOS Fade catches the REVERSAL. The breakout-structure bot (not built yet) catches the LEGS IN BETWEEN. B-LEG catches SOS setups that take a long time to play out. By construction they should not be in the market on the same swing at the same time.

**Risk is budgeted per ACCOUNT, and never layered.** The intended rule: there is one risk pool (call it 10%, whatever the number lands on) available at any moment. Concurrent setups either SHARE that pool or the later one is BLOCKED outright. Risk is never stacked on top of risk. `exec_risk_pct = 10` is a per-trade figure and the account-level cap above it **exists on both sides** (built 2026-08-09; this line said UNBUILT until 2026-09-03). 🔴 **THE POOL IS SPLIT AS OF 2026-09-04 AND THIS LINE CALLED IT THE OPEN DECISION FOR THREE DAYS AFTER IT WAS TAKEN.** Aaron's call: **SOS Fade 5% and the extreme leg 5%**, two shares summing to the 10% cap exactly, so each bot can hold one full-size trade at once and the budget is fully allocated with nothing refused. Both bots were RUNNING on PU Prime demo 700152905 when this was checked on the box, 2026-09-07. ⚠ **A THIRD bot is a CHOICE, not a blocker, and do not write it up as one** (Aaron, 2026-09-07: *"I can lower individual bots risk or just up the cap so no issue there"*). Two routes, both his, both one write: shrink the per-trade shares so three fit under 10, or raise the cap. The only thing the doc owes a reader is the MECHANIC — shares that sum past the cap mean the bots take turns instead of sharing, and the Command Center refuses the assignment at the moment it is made — never a recommendation to stop and decide. The Pine input's own ceiling was raised 10 → **100** on 2026-07-27 at Aaron's request (defaults unchanged at 10, and the Python side never had a cap), so nothing in the code now refuses a per-trade risk the account rule would.

**The overlap audit — the legs really do trade different parts of the move. RE-MEASURED 2026-09-10 ON TODAY'S SOS Fade.** Over 157,004 M15 bars of **PU Prime `XAUUSD.p`** (2020-01-01 → 2026-08-23, `--server PUPrime-Demo`) SOS Fade and B-LEG held a position at the same time on **46 bars** — 0.3% of SOS Fade's hold time, 1.9% of B-LEG's — and **ZERO were same-side** (all 46 opposite, i.e. partly hedged). SOS Fade **244 trades / +248.59R** (156 primary + **88 re-entries**), B-LEG 101 / +20.20R; 5 trade pairs touch at all and **none is same-direction**, and exactly ONE same-direction entry lands within four hours of the other's in 6.6 years. Monthly R correlation **+0.059** over 78 months — a FLOOR rather than a figure, because a month only one bot traded contributes a zero for the other and pulls it toward 0.
🔴 **THIS SAID 200 TRADES / +164.27R FOR A WEEK AFTER THAT STOPPED BEING THE BOT.** Two SOS Fade defaults moved on 2026-09-06 (Aaron's call: adding to a winning trade switched on, and both re-entry triggers together), the live bot followed on 2026-09-07/08, and nobody re-ran this. **PROVEN, not inferred:** today's code with only those two put back replays exactly 200 / +164.27R, so nothing else moved the bot. ✅ **Every clash figure HELD** — 46 bars, zero same-side, 5 pairs, one cluster; only the percentages (SOS Fade's own hold time grew) and the correlation moved. ⚠ **B-LEG read +20.07R for a day**: its settings extend SOS Fade's, so its default had picked up adding-to-winners, which its own Pine cannot do. Pinned OFF 2026-09-10 and re-measured — same 101 trades at the same times, +20.20R, correlation +0.063 → +0.059, every clash figure held (`strategies/python/b_leg/CLAUDE.md`).
✅ **ENFORCED FOR SETTINGS SINCE 2026-09-10: step 17 of `scripts/run_all_tests.sh` goes red when any audited bot's strategy or engine settings differ from the ones these figures were measured on**, and prints the re-measure command — all three stale readings were a moved default. ⚠ **A rule changed in CODE is still on you**: re-run `backtest/tools/overlap_audit.py ... --record` after any entry-logic change on either bot. How it works: `backtest/CLAUDE.md` → `tools/overlap_audit.py`. ⚠ **Name the broker and pass `--server`**: 157,004 is PU Prime's bar count for this window and 156,819 is Vantage's, and a re-run on the wrong cache disagrees with every figure here while looking healthy. ⚠ **Read the direction split before reading a bigger overlap as a regression** — shared bars once went 27 → 49 while same-side went 18 → 1, from one change. ⚠ **It does not make the two independent** (one structure stream, one instrument), and ⚠ **it does not retire the allocator** — peak concurrent positions is still 2, so one account carries both legs' risk on those bars. The tool's own history — a one-frame replay that dropped a third of SOS Fade's trades, and a *two positions at once* finding that was its own placement bug, retracted 2026-09-03 (**a guard firing is a question, not an answer**) — is in `backtest/CLAUDE.md` → `tools/overlap_audit.py`; every earlier reading is in `HISTORY.md` → *The overlap audit, re-measured*, and the paragraphs this one replaced are under *The overlap audit outlived its inputs a third time*.

**The extreme-leg bot does not clash with SOS Fade either — RE-MEASURED 2026-09-10, across two bar frames.** Over 470,995 M5 bars of PU Prime `XAUUSD.p` (same window) SOS Fade (15m) and the extreme leg (5m) held a position at the same time on **1,049 bars** — 2.6% of SOS Fade's hold time, 6.0% of the extreme leg's — and **ZERO were same-side**. SOS Fade 244 / +248.59R, extreme leg 113 / +58.53R; 6 trade pairs touch at all, **none** same-direction. Monthly R correlation **−0.038** over 79 months, same floor caveat.
⚠ **ONE same-direction entry now lands within four hours, where the 200-trade bot had none**: on 2025-04-07 an SOS Fade re-entry went long and was stopped out (−1.00R) before the extreme leg went long three hours later (+2.49R). No shared bar, so no doubled risk — but it is the first time these two read the same move inside the window, and it arrived with the 2026-09-06 defaults. ⚠ **At the live shares (5% + 5%) those 1,049 bars carry 10% of the account, the cap exactly**; on the strategy defaults the tool replays it is 10% + 5% = 15%. **The tool printed a typed "10% → 20%" on every run until 2026-09-10** and now reads each config's own risk — a doubling shorthand is only right while two legs are matched. Risk moves no trade here: each bot replays off its own equity. ⚠ **This bot puts SOS Fade at raised risk 7.6× longer than B-LEG does** — 2.62% of SOS Fade's hold time against 0.345%. 🔴 **That ratio divides the PERCENTAGES, never the bar counts** — a 5-minute bar is a third of a 15-minute one, and an earlier revision divided the counts and printed "24×". ⚠ **Do not read one audit's survival as evidence for the other's**: on the 5-minute grid a re-entry's timestamp is a bar open and on the 15-minute grid it is not, which is why the 2026-09-02/03 tool bugs moved one audit and not the other. ⚠ **This is a WEAKER claim than the SOS Fade/B-LEG one**: the extreme leg's parity gate covers 3.5 months and 7 entries and cannot cover the market-condition refusal behind these numbers — the chart has no such engine — so they describe the Python port. Why the shared time axis is the finer frame's own index rather than a clock: `backtest/CLAUDE.md` → `tools/overlap_audit.py`.

**BOTH SIDES OF THE ALLOCATOR EXIST.** `backtest/portfolio/run_stack` replays both bots on ONE balance with ONE risk budget, and at a 10% cap over 155,807 M15 bars it **refused nothing** — risk is measured to each trade's CURRENT stop and SOS Fade reaches breakeven in a median of one bar.

🔴 **THIS PARAGRAPH SAID THE LIVE SIDE WAS UNBUILT UNTIL 2026-09-03, AND IT HAD BEEN BUILT SINCE 2026-08-09.** It is wired at the single sizing seam (`bridge._account_cap_check`, called from `_plan`), it reads the BROKER rather than any shared object — separate OS processes, so `PortfolioAccount` genuinely could not be reused — and it carries 21 tests. ⚠ **The correct claim was in `docs/LIVE_TRADING_PIPELINE.md` → G10's own BODY the whole time, while that section's HEADING said "LIVE HALF STILL OPEN" and this file agreed with the heading.** A stale summary two files from the truth is this repo's parents-route-children-explain rule arriving as a bill, and it read as a blocker on a second bot for three and a half weeks.

⚠ **The two sides resolve a shortfall differently and that is deliberate: the backtest SHRINKS, live REFUSES.** Nothing hands a size back across a process boundary, so a shrunk live order would leave the emulator holding a different trade. **Anything that tunes the cap must be replayed under the REFUSE policy.**

🔴 **THIS SAID A SECOND BOT WAS BLOCKED BY A NUMBER, AND IT WAS — THE NUMBER MOVED ON 2026-09-04.** SOS Fade went 10.0 → 5.0 and the extreme leg was assigned at 5.0, so the second bot has been running beside the first ever since. ⚠ **The ordering trap that paragraph implied is real and is worth keeping: the sibling must come DOWN before the new bot is assigned**, because the Command Center refuses any write where an account's shares sum past its cap, and 10 + 5 > 10 is refused at the moment of assignment rather than discovered later. ⚠ **The third share is the part still open** — see the split above.

**A stack in `command-center/` is either a SCREEN or a SHARED ACCOUNT, and the page says which before any number below it.** A screen is N standalone runs added together — every leg on its own full account, so nothing can block anything and it is an UPPER BOUND. 🔴 **A shared run can close HIGHER than the screen with the cap working and nothing refused, and a doc here predicted the opposite.** A screen gives each leg a private balance; a shared account COMPOUNDS both onto one, so the second leg sizes off a balance the first has grown. Two effects in opposite directions, and the compounding one is unbounded while the refusal one is capped by how often the budget is genuinely full. ⚠ **So compare R, never net dollars** — the checks that say the gate is enforced are `peak_open_risk_pct <= risk_cap_pct` and every R difference tracing to a row in the contention log. **The standing lesson is about the CRITERION rather than the code: a verification test written before the thing exists is a prediction, and this one would have condemned a correct implementation.** Full run: `HISTORY.md` → *The lab stack, and the test that would have condemned it*.

---

## Repo Structure

See `README.md` for the full repo map and subsystem list.

`algos/`, `smart-money/`, and `command-center/` are fully independent from each other. Engines under `engines/` are canonical shared libraries, and their dependency map is: `market_structure/` is the base and `fibonacci/` is its one downstream consumer (public `StructureSnapshot` only, never its internals). **`order_blocks/` was downstream too until 2026-07-31 and is now STANDALONE** — the mpc rework stopped creating blocks on structure breaks, so it takes plain OHLC and consumes no engine at all; `sessions/` is standalone and time-driven; `liquidity/` and `session_volume_profile/` compose `sessions/`; `vwap/` and `news/` are standalone and time-driven; `vwap/` and `session_volume_profile/` are the two engines that need the bar's **volume**; `fair_value_gaps/` is standalone and OHLC-driven (no upstream engine, no volume, no timestamp — pure price-pattern detection); `rsi_divergence/` is likewise standalone (needs close for Wilder's RSI + the bar's high/low for the price anchor — no upstream engine, no volume, no timestamp); `equal_highs_lows/` is likewise standalone (needs high/low/close for ATR(50) + strict price pivots — no upstream engine, no volume, no timestamp); `candlesticks/` is likewise standalone (needs OHLC only — no upstream engine, no volume, no timestamp — and is the only engine here ported from a THIRD-PARTY indicator rather than from `mpc_jarvis.pine`). `engines/regime/` and `engines/market_structure/` are imported by `algos/` via thin shims in `algos/shared/`. **`command-center/` imports six directly** (bare-name, public API only, never a second implementation): `regime/` and `news/` for tagging and the news filter, and `market_structure/` + `fair_value_gaps/` + `equal_highs_lows/` + `order_blocks/` for the backtest PRICE CHART's overlay layers (`backend/services/structure_overlays.py`, `fvg_overlays.py`, `ob_overlays.py`). Those four are **display** consumers — no strategy reads them, so a change there moves what a chart shows and never a trade — but they are consumers, and an engine's own CLAUDE.md must say so rather than claiming nothing imports it. Every other engine gets its `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS strategy folders — ⚠ **but only its `.cs`, `.mq5` and `python/` halves.** Since 2026-09-02 it also holds `tradingview/`, the Pine `strategy()` source, and **nothing there is scanned, registered or deployed by anything**: the scanner globs `.cs` and `.mq5` only and has never globbed `.pine`. Those files reach the lab by being PORTED to `python/`, gate and all. 🔴 **A Pine strategy INLINES its engine rather than importing one, so it is not a consumer of `engines/` and nothing under `indicators/` is a consumer of it either** — that is why the move cost nothing, and it is also why an inlined copy and its canonical source are now two trees apart with nothing enforcing that they agree. Per-engine detail lives in each engine's CLAUDE.md — do not restate it here.

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
| `algos/` | Live MT5 trading bots on a Windows VPS | **TWO bots are LIVE and ARMED on ONE account** — `sos_fade_demo` (M15) and `extreme_leg_demo` (M5), both PU Prime **700152905**, both `XAUUSD.p`, **5% each under a 10% account risk cap**. `b_leg_demo` is registered and BENCHED. ⚠ **Count them with `box_status`, never from this line** — it named one bot for three days after the second was assigned and running. A live bot imports from a frozen `deployed/` snapshot, so a `git pull` cannot move it — only `promote.py` can. A fleet kill switch and an account-mismatch halt both exist and both LATCH. |
| `command-center/` | React + FastAPI local ops platform — monitors bots over SSH, runs and grades backtests | A bot is registered ONCE (`routers/bots.py::BotReg`) and addressed by its KEY, never its display name. A broker ACCOUNT is a first-class row too. The Smart Money UI is flagged OFF behind one boolean. |
| `backtest/` | Strategy- and instrument-agnostic Python bar-replay runner — data, fills, costs, optimizer, portfolio stacks | An unmeasured cost REFUSES rather than borrowing a sibling tier's number. Swap, commission and — since 2026-08-14 — **ECN's spread** have been measured; **Prime and Cent still refuse, and ECN's figure may not be copied onto them.** History floors are measured per broker, never hardcoded. |
| `smart-money/` | Scans and profiles consistent crypto/forex traders for a copy-trade candidate pool | Runs locally on Mac. Stages 1–2 and 5 live; 3–4 blocked on API keys. |

### The engines — canonical, one implementation each

Ported from `indicators/engines/mpc_jarvis.pine` and gated by a `compare_*.py` parity check on a real
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
| `strategies/` | Strategy source by runner platform — NT8 `.cs`, MT5 `.mq5`, Python packages, and since **2026-09-02** the Pine `strategy()` files in `tradingview/` (moved in from `indicators/strategies/`; the two scratch ideas dropped to `tradingview/research/`). ⚠ **Nothing under `tradingview/` is scanned or deployed** — the lab's scanner globs `.cs` and `.mq5` only. Python ports with a GREEN parity gate: `sos_fade`, `b_leg`, and `bos` (**narrow** — the gap ladder never ran). **`realign` has NO gate at all** — no export twin, no CSV, no `compare_realign.py` — so every number it has produced is a lab finding. The end-to-end process, and which step only a human can do, is `docs/STRATEGY_WORKFLOW.md`. |
| `indicators/` | Pine INDICATOR source. Split by DECLARATION since 2026-08-13, and since **2026-09-02 the two halves are in two different trees**: `indicators/engines/` holds the 17 `indicator()` files, and the 16 `strategy(` files moved out to `strategies/tradingview/` — Pine runs only on TradingView, so a `strategy()` file is strategy source and belongs beside the MT5, NinjaTrader and Python strategies. Nothing in any `.pine` changed in that move. ⚠ **Count them with `ls`, never from this line** — it read 16 while there were 18, and one was then deleted. **The declaration decides it, never the filename** — `structure_engine.pine` reads like a strategy component and is an indicator. Includes the from-scratch `smc_engine_v2.pine` rebuild — mid-build, and a **separate track** from the `mpc_jarvis.pine` the Python engines were ported from. Do not confuse the two. |
| `education/smc/` | The course material the engines were extracted FROM. Reference a human reads; no code reads any of it. |

### scripts/
Cross-subsystem VPS bootstrap and full-recovery scripts (`bootstrap_vps.ps1` for the MT5/algos side, `bootstrap_ninjatrader.ps1` for the NT8 side). Idempotent, run on a wiped or new VPS. Full run order in `scripts/README.md`. ⚠ **`bootstrap_vps.ps1`'s task list gained `SYS_LEDGERSYNC` on 2026-08-24** — the box commits and
pushes its own decision record hourly, so the backup no longer waits for a Mac to wake up. It is the
one task there that needs a SECRET a rebuild does not restore (`github_token` in the git-ignored
`algos/credentials.json`): without it the task runs, commits, and silently never pushes.

⚠ **And `SYS_REENTRYWATCH` on 2026-09-03** — hourly, grades each live re-entry against the strategy
and reports on Telegram. It needs no secret. 🔴 **It is the SECOND task here whose normal state is
silence**, alongside the dead-man's switch, so it carries the same hazard: a missing watcher and a
quiet month look identical. That is why it announces its own failure and writes a health record on
every run — **a task list that registers an alarm nobody can tell is dead is the 2026-08-05 failure
with a different name.** Rules: `algos/CLAUDE.md` → *The re-entry can be switched on*.

⚠ **And `SYS_BROKERCOSTS` on 2026-09-03** — daily at 06:40 UTC, it reads the broker's overnight
financing off the live terminal and reports when the broker MOVES it. That rate was caught drifting
four times in seven weeks and every one was found by a person who happened to look. It needs no
secret and it CHANGES nothing — re-pricing the lab's constant re-bases every charged figure in the
repo and stays a deliberate job. 🔴 **THIRD task here whose normal state is silence**, so same
hazard and same answer: it announces its own failure and writes a health record carrying the
reading on every run. Rules: `algos/CLAUDE.md` → *`SYS_BROKERCOSTS`*.
🔴 `install_ledger_sync.sh` **no longer installs anything and refuses if you ask** — its Mac agent
was a SECOND WRITER of an append-only file, and two appends to one file end cannot be merged at any
content (eight hours of hourly conflicts, 2026-08-28). **`--no-push` did not save it: on a shared
branch a local commit is a push with a delay.** The rule is enforced in `ledger_sync.py`, which
refuses to commit records the running machine did not write. Rules live in `algos/CLAUDE.md`; do
not restate them here.

**`setup_learning_mode.sh` (2026-08-11) is the odd one out — it targets a DEV MACHINE, not the VPS**, and is the one-time install behind `/learn <video-url>`: it puts `ffmpeg`/`yt-dlp` on the PATH and clones the third-party `watch` skill (MIT, `bradautomates/claude-video`) to `~/.claude/vendor/`, symlinked into `~/.claude/skills/watch`. ⚠ **The watch skill is deliberately NOT vendored into this repo**, so a clone alone does not make `/learn` work — the skill checks for the install and names the script rather than shelling out to `yt-dlp` itself. **Re-running the script is also how it UPDATES**, which is the part that bites: `yt-dlp` breaks whenever a video site changes its markup, and a stale copy fails on real URLs while looking perfectly installed.

### `scripts/check_pine_blocks.py` — the drift check the parity gates cannot do

**Step 14 of `scripts/run_all_tests.sh`.** Pine has no import, so every engine block is copy-pasted
into the indicator, into that engine's own parity harness, into any OTHER harness embedding it for a
coupling, and into each strategy plus that strategy's export twin — **~10 files per rule, with
nothing asserting they matched.**

🔴 **A `compare_*.py` is structurally blind to this.** It asks whether the PYTHON agrees with ONE
Pine file, on ONE export, on ONE machine. Two PINE files disagreeing with each other is outside the
question. On 2026-09-09 the equal-level mitigation rule moved close → wick in the indicator, the
Python engine and two harnesses while SEVEN strategy files stayed on close — and every gate that
could run stayed green. This step went red on 28 findings the moment it existed.

⚠ **It compares each copy against the INDICATOR, never against a value typed into the checker.**
Hardcoding the answer would make the checker one more place the rule is written down, and then a
rule change has to edit it too — which is the disease, not the cure. Move the indicator, move the
copies, and this stays green with no edit.

⚠ **It DISCOVERS copies rather than listing them.** The engine's own doc said the rule lived in
three files; it lived in eight. That was not carelessness — the true count lived nowhere, so anyone
checking checked the files they knew about. **A count that exists only in prose is a count that is
wrong.**

⚠ **Every spec declares a minimum number of copies and finding fewer is a FAILURE**, because a
regex that stops matching after somebody reformats a file would otherwise report a clean repo.
Watched RED by mutation, and the mutant exits 1 rather than passing quietly.

⚠ **It cannot tell you the INDICATOR is right** — only that the copies match it. That is rule 14
arriving in a new place.

⚠ **Seven rules as of 2026-09-10** — the five equal-level ones plus the gap cap's counting basis and
the gap mitigation rule. The cap spec went red the moment it existed: four strategy files were
counting EVERY gap against the cap while their drop scan skipped the protected ones, which makes the
exemption a swap rather than an addition. **It was DORMANT — those files ship the exemption off, and
the two forms are then identical by construction — so it could only ever have been found by a tool
that compares Pine against Pine.** Story: `strategies/tradingview/CLAUDE.md`.

### `scripts/check_engine_gates.py` — golden exports, so a gate can always run

**Step 15 of `scripts/run_all_tests.sh`.** Runs each engine's `compare_*.py` against a COMMITTED
export under `engines/<name>/exports/golden/`.

🔴 **Rule 22 was unsatisfiable for most of this repo, and that is what this fixes.** *"No engine
change without a green gate"* is right, but exports were git-ignored scratch — so whether a gate
could run depended on which CSVs sat on one laptop. Measured 2026-09-09: **nine of fourteen gates
could not answer**, and those that could were red against two-month-old exports from a Pine that no
longer existed. **A rule that cannot be satisfied stops being a rule** — it blocked work instead of
gating it, and both stalling and routing around it happened that day.

⚠ **Two different jobs, and you need both.** A golden export is REGRESSION — it catches the PYTHON
drifting from a known-good answer, on every clone, in seconds, with no human. A fresh export is
ACCEPTANCE — it catches the Pine and the Python disagreeing after a Pine edit, and still needs a
person with TradingView open. **A green golden run says nothing about a Pine change made after the
file was taken.**

⚠ **It prints its COVERAGE FRACTION and names the engines that lack an export**, because a bare
green tick on this step would read as *the engine gates pass* when it means *the one engine with a
committed export passes*. Coverage: **11 of 11** gateable engines, from **thirteen** committed exports — the gap engine carries two (2026-09-10) because the fib entry-band exemption is a separate branch with its own harness, and the fib engine two frames (5m and 15m), each at its own measured warm-up: `golden.json` may key the warm-up per file.

🔴 **A GATE'S OWN WARNINGS NOW SURVIVE ITS GREEN, and they did not until 2026-09-10.** Each gate's
stdout was captured and DISCARDED on success, so a caveat the gate printed on every run reached
nobody. Two were hiding behind ticks: `compare_fvg.py` reporting that it could only see **48%** of
its export's bars, and `compare_candles.py` naming a pattern that **never fired on either side** —
i.e. rule 14's *says nothing about a branch neither one entered*, printed and swallowed. Any 🔴/⚠
line a gate prints is now echoed under its tick. ⚠ **Generic on purpose** — any gate can raise a
caveat this way and none of them needs an if-statement in the runner.

🔴 **The fibonacci gate excludes its MACRO half deliberately, and that is a decision rather than
a gap.** The macro fib diverges on 11,356 of 13,304 bars because the engine matches the STRATEGY
file the bot replays, not the assistant's 2026-07-31 rework — porting that would manufacture drift
in the bot. Nothing trades on it: the strategy computes the zone and reports it, execution never
reads it. **A gate that can never pass is worse than none**, so the other three fibs are gated for
real and the exclusion prints in the tool's scope line on every run.

⚠ **`golden.json` carries an `extra_args` list** — a generic seam so any gate can take a per-engine
flag without this runner growing an if-statement per engine. Anything it carries must justify itself
in the manifest, as fib's does.

⚠ **Each golden folder carries a `golden.json`** holding the MEASURED warm-up and the provenance
(broker, symbol, timeframe, bar count, harness). Provenance is recorded because a cross-cutting run
on 2026-09-01 recorded NEITHER broker nor symbol and cost three replays — two brokers disagree on
the bar count for the same window while both look perfectly healthy.

🔴 **A warm-up is MEASURED, never guessed, and never raised to bury a LATE mismatch.** The export
starts warm and the Python starts cold, so an opening prefix of mismatches is expected; the number
is set past the last mismatching bar with the whole remaining tail confirmed clean. Mismatches that
RECUR after a clean stretch are real divergence — raising the warm-up to swallow them turns the gate
into decoration. Two of the ten were diagnosed that way on landing: the gaps engine looked 100%
divergent and was a window too short (seven gaps born before the export began, and a gap only dies
when price closes past it), while fibonacci's macro half is genuine.

⚠ **Cost: ~25 MB raw, ~4 MB compressed in git, once.** That is the price of every gate being
runnable on every machine forever, and it is worth stating so nobody re-litigates it later.

⚠ **Engines are DISCOVERED, never listed** — drop a CSV in the golden folder and it is wired in
with no edit. ⚠ **Finding zero golden exports is a FAILURE**, not a quiet pass.

✅ **STRATEGIES JOINED ON 2026-09-10 — all four**, from `strategies/python/*/exports/golden/`, so
every strategy's parity gate, both LIVE bots' included, runs on every clone. 🔴 **BOS's was RED on
arrival**: every fork had inherited SOS Fade's 2026-09-06 adding-to-winners default, which no
fork's Pine can do, and nothing had run BOS's gate since. **A fork inherits its parent's DEFAULTS as
well as its code** — pinned off in all three (`strategies/python/bos/CLAUDE.md`). ⚠ **A folder with two
compare scripts must NAME its gate in `golden.json`** — SOS Fade has two, and the runner took the
first alphabetically, right by luck; unnamed ambiguity is now refused. ⚠ **A Pine twin that gains
a compared column makes its golden REFUSED rather than stale** — the step goes red and the answer
is a re-export. ⚠ Each manifest says what the chart's settings did NOT exercise, and a passing
gate's ⚠ lines print under its tick, so read them before quoting a green. Both paths watched
RED by mutation: reverting the engine's rule turns the gate red through this runner, and raising the
minimum makes the self-test fire and exit 1.

### `engines/gate_common.py` — the export-format rules every parity gate needs

🔴 **It exists because the live-bar rule was written three times before it was written once.**
`compare_bos.py` had it, `compare_candles.py` copied it with a comment saying so, and a third copy
was about to land in `compare_fvg.py`. Eleven copies of a three-line rule is the disease this repo
pays for in Pine *because Pine has no import* — Python has one, so not using it is a choice.

🔴 **The rule: the final row of a TradingView export is the LIVE bar, and every gate was feeding it
as a closed one.** Most Pine blocks gate detection on `barstate.isconfirmed`, so they do not run on
that bar, while the CSV carries its current OHLC. It fired on the gap gate on 2026-09-10 — one bar
in 20,188 — and **all twelve golden exports end on a row carrying values, so every gate carried the
exposure** and was green only because its last bar happened not to matter.

⚠ **NOT decided from the clock.** *Is this bar still open?* is a question about when the export was
TAKEN, not when the gate is RUN, so a committed golden file would answer it wrong for ever. The
final row is treated as suspect unconditionally: one bar in twenty thousand, and it cannot rot.

⚠ **Deliberately NARROW and it must not grow into a parity-gate framework.** Each engine's
comparison is genuinely its own; a shared base class would be the over-engineering this repo counts
as a corner cut in its own right. What lives here is a fact about the EXPORT FORMAT — the one thing
all eleven demonstrably share.

⚠ **Its message says `note:`, not `⚠`, on purpose.** `check_engine_gates.py` echoes 🔴/⚠ lines under
a passing tick because those are caveats about that RUN; this one is a constant of the format and
would print identically twelve times, which is how a reader learns to skip the marker that matters.

### `engines/pine_constants.py` + `engines/tests/` — every engine default is held to the Pine (2026-09-10)

🔴 **On 2026-09-09 three equal-level numbers moved in the indicator and had to move in SEVEN Python
places; an eighth copy turned up a day later.** Now each engine declares its defaults ONCE
(`DEFAULT_*` in its `engine.py`), every Python consumer imports them — the gates, the lab's
`backtest/replay/stack.py` — and `engines/tests/test_defaults_mirror_the_indicator.py` READS each
paired value out of the Pine and goes red when the engine disagrees. 28 pairs across seven engines,
plus the profile's row count and the gap engine's 15m row — the one the Command Center's gap layer
draws with; watched RED from both sides and on the reader's three shapes.

⚠ **The table in that test is the one place the PAIRING is written** — which Python default mirrors
which Pine name. A default with no Pine counterpart (the trading-day rollover, regime, news) is not in
it, and a Pine value split by timeframe is held to its below-15m branch, because an engine takes one
value per run. ⚠ **A strategy's own pin is deliberately NOT routed through these** — it mirrors its
own Pine file. ⚠ `pine_constants.py` refuses unless exactly ONE declaration matches, and it is
tests-only: nothing deployed imports it.

### `scripts/build_fvg_zone_harness.py` — a Pine harness that is a BUILD ARTIFACT

**Step 16 of `scripts/run_all_tests.sh`.** Generates `indicators/engines/fvg_zone_export.pine` by
slicing blocks verbatim out of `fib_export.pine` and `fvg_export.pine`; `--check` regenerates and
diffs.

🔴 **It exists because that harness has to be a TENTH copy of the gap block.** The cap's entry-band
exemption needs four engine blocks in one script — the band is the live fib recomputed every bar, so
it cannot be an input — and step 14 exists precisely because copies drift with nothing asserting they
match. **A generated harness cannot drift from its sources without this step going red**, which is
the one thing a hand-maintained copy could never offer.

⚠ **It slices on TEXT ANCHORS, never line numbers** — the first version used line numbers and they
were stale within the hour; a numeric slice would have cut a block in half while still producing a
file that looks fine.

⚠ **A red here means the harness is validating Python against a Pine block the repo no longer has.**
Regenerate, then RE-EXPORT before trusting its gate: a regenerated harness is a changed harness, and
the committed CSV was taken from the old one.

⚠ **It does not prove the harness is RIGHT**, only that it matches its sources — rule 14 again. What
proves it right is `compare_fvg.py` going green on a real export.

🔴 **It — and steps 6 and 13 — read `/Users/alwg/trading` from ANY clone until 2026-09-10.** A
typed repo path: on another machine all three fail to start, and in a second clone on this one
they certify the WRONG checkout. **Proven in a worktree elsewhere — each passed with its own subject
broken**, and goes red once it reads its own clone. All three derive the repo from their own file
now. ⚠ **Never type a repo path into a check.** ⚠ The guard itself still finds its place in the
repo by the `/trading/` in a path, so a clone must keep that folder name — a default clone does.

### Step 18 — the Pine export twins are build artifacts too (2026-09-10)

`strategies/tradingview/tools/build_export_twins.py --check`: each `_export.pine` twin must be its
parent with " Export" on the title plus its block from `strategies/tradingview/export_blocks/`. 🔴
**Five of the six twins were kept by hand until this step existed.** Rules:
`strategies/tradingview/CLAUDE.md`.

### tools/
Standalone utilities that belong to no subsystem and are run by hand. One today: `tools/skool-transcript/` — rips course video transcripts and indexes them into `education/`. It has its own CLAUDE.md. ⚠ **Nothing imports it and nothing schedules it**, which is the point — it is a dev-machine tool, not part of any deployable, so it is out of scope for the commit hook's money-path rule and for every parity gate.

### education/
The course material the engines were extracted FROM, plus notes. Two halves and they are different things. `education/smc/` is the source library — transcripts, summaries and visual playbooks for the SMC course, with its own CLAUDE.md; it is reference material a human reads, and no code reads any of it. `education/learned/` is where `/learn <video-url>` files a dated note per video (source link, what it covers with timestamps, what is worth acting on). ⚠ **The notes are COMMITTED and videos are never re-watched** — a note already on disk for a URL is read rather than regenerated, because the extracted frames are the whole token cost.

### .claude/
Repo-shipped Claude configuration — available to every clone, unlike `~/.claude/` which is per machine. Three folders.

**`commands/` — the slash commands.** Two kinds, and the split is the point. The **audit** commands look BACKWARDS at code already written: `/audit-engines`, `/audit-strategy`, `/doc-audit`, `/dead-code-audit`, `/prop-firm-rules-audit`, `/quant-review`, `/regenerate-snapshots`, `/session-start`. The **build-time** commands (added 2026-08-12) run BEFORE and DURING the work, and each one exists because a specific class of defect kept reaching the audits: `/spec` (write down what I think you asked for, before code — catches right-code-wrong-question), `/wire-check` (trace every label, config field and registry to the line that consumes it), `/prove` (watch every new test go red, or kill it by mutation), `/measure` (no number without the command that produced it), `/live-safety` (the 22-question checklist before anything touches the live path), `/port` (drive a strategy through `docs/STRATEGY_WORKFLOW.md` and refuse to skip the parity gate), `/run-audit` (take a run id and answer both halves — is this run TRUE, and was this configuration WORTH IT — recomputing every number from the trade list and measuring the feature against a matched control rather than against a run with a different basis). ⚠ **They are prompts, not enforcement** — nothing makes anyone type them. The two things that ARE enforced are the commit hook and the editor guard below, and the commands exist so that when the hook asks "what did you check", there is a repeatable answer.

**`hooks/guard_sensitive_paths.py` — the editor guard.** A `PreToolUse` hook on Edit/Write. A `deployed/` snapshot **asks first**, because a live bot imports from it and an edit there changes what a running bot trades immediately, with no promote and no restart. `engines/`, `strategies/`, `algos/live/`, `algos/shared/`, `backtest/` and `*.pine` attach a one-paragraph reminder of the rule that path keeps breaking, at the moment of the edit rather than 40,000 words away. **Since 2026-08-12 it also watches the CLAUDE.md files themselves** — a file over **40 KB** gets a reminder to move the story out and keep the rule. 🔴 **Since 2026-08-13 it fires on GROWTH, not on size, and that correction matters more than the feature did.** Warning on size alone meant **ten files tripped it on every single edit**, including the ones that are legitimately large — `ChartPanel/CLAUDE.md` is 122 KB and only ~3% of it is movable narrative; the rest is dense engineering reference with measured reasons attached. **A guard that fires on work it should not be criticising is a guard people learn to dismiss, and a dismissed guard is worth LESS than none, because the next reader takes silence for checked.** So a trim now passes in silence and only an edit that ADDS bytes to an already-oversized file has to justify itself. The delta is computed from the tool call itself (`content` for Write, `old_string`/`new_string` for Edit, multiplied out when `replace_all` is set). 🔴 **The reason it lives HERE and not in the commit hook is the whole point: a commit-time warning arrives when the work is already finished, and nobody stops to refactor a doc at that moment — you type the message and move on.** The edit is when the file is open and the context is loaded, so it is the only moment the reminder can change what happens. ⚠ **The 40 KB is MEASURED, not picked** — all 28 files fall into two clumps with an empty gap between them (everything sane lands at 27 KB or below; the next file up is 63 KB), so 40 KB is the middle of that gap and no file is close enough for a paragraph to flip it. At the ceiling's landing, **11 files tripped and 17 passed.** ⚠ **It FAILS OPEN by design** — any error allows the edit, because a broken guard must never stop the work. ⚠ **Which also means its silence proves nothing** — and now that a trim is DELIBERATELY silent, silence is its most common answer. Run **`python3 .claude/hooks/check_guard.py`** — **twenty-one** cases since 2026-08-21, and it is **step 6 of `scripts/run_all_tests.sh`**, because a check nobody runs is not a check. Each asserts a specific verdict, so a guard that always warned and a guard that never warned both fail it. Watched RED by mutation, and **the map in that file's docstring was RUN rather than reasoned** — three entries first written from inspection were wrong, each claiming a mutation was more surgical than it is.

🔴 **STEP 6 WENT RED ON `main` ON 2026-09-04 AND THE GUARD WAS WORKING PERFECTLY — THE CASE HAD
AN EXPIRY DATE NOBODY WROTE DOWN.** One case wrote a hardcoded **400,000 bytes** over
`command-center/backend/CLAUDE.md` to prove the guard warns on growth. That doc reached **400,570
bytes**, so the "grow" quietly became a SHRINK, the guard correctly said nothing, and the failure
pointed at the guard. The comment naming the fixture still said *282 KB*. **A case whose premise is
a typed number about a file that GROWS is a case that rots on a schedule**, and it is the same
shape as the case pinned to a path that moved on 2026-09-02 — a fixture describing a repo you no
longer have. ✅ Every size there is now DERIVED from the file (`_size(BIG) + 50_000`), and two
PREMISE assertions refuse to run the file at all if the big fixture stops being oversized or the
small one stops being under — because trimming that doc would otherwise leave the oversized cases
passing while testing the quiet path. Both watched red.

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
with the guard live and silent — `strategies/tradingview/CLAUDE.md` (then
`indicators/strategies/CLAUDE.md`) went 38,766 → 69,605 bytes in
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
`strategies/python/sos_fade` −102 KB (307 → 205 KB, 2026-08-27). The reminder is working on
the files it can reach.


⚠ **MEASURED there, and it bounds what a doc migration can ever achieve: moving EVERY explanation
out — prose, tables and run numbers — still left 205 KB, because ~70% of that file is rules WITH
their justification, which must stay next to the code. Past that point, reaching the ceiling is a
decision to compress or DROP rules, not a migration. Say which is being asked for.**

🔴 **A subsystem fragment is ANCHORED at the repo root (2026-08-13, `subsystem_matches`)** — a fragment starting with `/` matches only paths actually under that top-level dir, while `.pine` is about what the file IS and still matches anywhere. It was a plain substring test until `indicators/engines/` was created and a Pine file was about to be told it is a canonical Python engine. **The standing lesson: a directory RENAME can silently re-aim a guard** — nothing fails and no test goes red; the only symptom is correct-looking advice about the wrong file. Story: `HISTORY.md`.

🔴 **IT HAPPENED AGAIN ON 2026-09-02, IN THE OPPOSITE DIRECTION, AND THE CHECK THAT WAS SUPPOSED TO CATCH IT STAYED GREEN.** The Pine `strategy()` files moved to `strategies/tradingview/`, so for the first time they sit under the top-level `strategies/` and collect its reminder as well as the Pine one. `check_guard.py` had a case asserting they do NOT — and it passed anyway, because the case names a path as a STRING and nothing asks whether that path still exists. **A case pinned to a path that has been moved out from under it is not testing anything; it is describing a repo you no longer have, in green.** It went red the moment it was pointed at the real path.

✅ **The second reminder was KEPT rather than special-cased away** — a Pine strategy is half of a parity gate, so *"if a default moves, every documented baseline needs pinning or re-measuring"* is true of it. Excluding the new folder from the fragment would have preserved 2026-08-13's behaviour exactly and left a special case behind, and a special case is the half that goes stale. ⚠ **The generalisation is worth more than either decision: a guard case that hardcodes a path needs re-aiming by hand whenever that path moves, and nothing will tell you.**

⚠ **The bloat it is guarding against was measured the same day and the root file was the worst case: 36 KB of its 69 KB — 53% — was `## System Summaries`, a paragraph per subsystem restating what that subsystem's own CLAUDE.md already said.** That section loads on EVERY session whether or not you go near the code it describes. **The duplication is also what makes the drift**: the 2026-08-12 doc audit found three files claiming there were no live bots, and the subsystem file was the one that was right. Hence the standing rule the guard's message repeats — **a fact lives in exactly ONE CLAUDE.md, the one next to the code. Parents ROUTE, children EXPLAIN.**

🔴 **`hooks/block_hook_bypass.py` — the bypass refusal (2026-09-07), and it exists because a git hook CANNOT enforce this one.** *Never bypass the commit hook* has been a rule here since 2026-08-04 and nothing enforced it: the flag tells git to skip its hooks, so the refusal that would object never runs — unreachable by construction. This one is a `PreToolUse` hook on Bash and refuses BEFORE git is invoked at all. It catches the long flag on commit, push, merge, cherry-pick, rebase and am; the short form, which need not lead its cluster (`-an` is that flag plus another, and reads as a typo rather than a decision); and pointing git at a different hooks folder for one command, which runs nothing while looking innocent in the shell history. ⚠ **The repo's own documented pre-push skip is deliberately ALLOWED** — it prints a loud line and has no silent form, and the objection is to skipping WITHOUT A TRACE, never to skipping. ⚠ **It FAILS OPEN and says so out loud when it does**: this one BLOCKS rather than advises, so a silent failure would make *checked* and *never ran* look identical, which is the mistake already paid for twice here. ⚠ **The wrapper in `settings.json` must NOT end `|| true`** like the two advisory hooks do — that swallows the refusal and leaves a hook that reads as protection while providing none. 🔴 **Its mutation map carries the sharpest lesson in this section, and it is one past step 11's: SIX of eleven entries written from inspection were wrong, and one mutation survived the entire file in GREEN.** Two defences sat over the same rule — the shell tokenizer makes a quoted commit message one word, so the case meant to cover the value-swallowing branch passed with that branch deleted. **Two defences over one rule can leave one of them uncovered while everything stays green, and only running the mutation shows which.** Ported from `block-no-verify.js` in `github.com/affaan-m/ecc` (MIT), rewritten on the standard library's shell tokenizer — Python because the other hooks here are, and a hook is a bad place to acquire a second runtime. Proof: **`python3 .claude/hooks/check_no_verify.py`**, 29 cases, **step 13 of `scripts/run_all_tests.sh`**.

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
the app's own scripts and rejects bot start/stop/restart, promote (and, since 2026-09-10, the
same deploy started as a background job — `POST …/promote/job`), strategy deploy and delete,
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
the win rate. ✅ **The VENUE LOT CEILING joined the basis on 2026-09-03, and it is the case that
shows why the check is read off the contract rather than curated by hand: R is IDENTICAL either
side of a ceiling** — profit and risk both scale with the quantity — **so every instinct says it
cannot matter, while balance, drawdown and CAGR all move.** MEASURED on the live SOS Fade bot over 6.6
years: same 205 trades, same +107.36R, closing balance $11,528,822 uncapped against $10,752,175 at
100 lots. Nobody would have added it from memory.

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
ssh forexvps "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe C:\trading\algos\tools\promote.py --bot sos_fade_demo"

# Stop the running bot by ASKING, never by killing. It polls its instance dir every 10s,
# writes a shutdown record, and clears the file. Give it ~30s, then confirm it is gone.
ssh forexvps "echo stop > C:\trading\algos\markets\fx\instances\sos_fade_demo\stop.request"
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
ssh forexvps "wmic process where \"name='python.exe' and commandline like '%--bot sos_fade_demo%'\" call terminate"
ssh forexvps "del C:\trading\algos\markets\fx\instances\sos_fade_demo\stop.request"
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

### `./go` is also the only thing that maintains the news calendar cache (2026-09-01)

🔴 **Its step 6 asked whether the cache FILE EXISTS, which is not a question about the dates inside
it.** The file had been there since July while its coverage stopped four weeks back, so every launch
said fine and the backend's own startup banner was the only thing that ever noticed. **Presence is
not freshness.** Step 6 now tops the cache up, costs nothing on the days there is nothing to fetch,
and never kills the launcher when it cannot. The cache is git-ignored, so this is per-machine by
design and there is no second writer. Rules, the tool, and the wiring bug that made a refusal read
as an all-clear: `engines/news/CLAUDE.md` → *Keeping the cache current*; story in `HISTORY.md`.

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

🔴 **Step 10 (2026-09-03) gates the one number two different pages multiply every dollar by.**
`check_period_window.mjs` drives the period window's rebase — the constant that reads a slice of a
finished book as though it were the whole book — for the single-backtest page and the stack page
at once. It lived inside a React hook until that day, reachable only from a browser, which is the
same shape rule that put steps 8 and 9 here. ⚠ **A wrong scale here is not a broken chart; it is a
plausible dollar figure with nothing on screen to say it is wrong.** 🔴 **Its mutation map caught
the sharper lesson: four scaling cases were written against a window whose scale happened to be
exactly 1, where *"this field is scaled"* and *"this field is left alone"* are the same assertion.
They were green and two mutations survived them.** A scale of 1 is the arithmetic version of a
fixture more capable than production — the test describes a system where the thing under test does
nothing. **Check that a test's inputs can distinguish the behaviours it names.**

🔴 **Step 11 (2026-09-07) gates the list a reader picks the INSTRUMENT off.** `check_instrument_search.mjs`
drives the picker's ranking and its per-broker recents — both decide from data, neither has any
pixels in it, and the form they belong to offered ten symbol names typed into the source until that
day, which were the WRONG BROKER'S: Vantage's spellings while the lab sat attached to PU Prime and
its 1,085 instruments. ⚠ **A wrong rank does not look broken. It looks like a list with the
instrument you wanted three pages down, which a reader takes for "the broker does not offer it".**
🔴 **Its map carries the sharpest lesson yet, and it is one step past step 10's: SIX mutations
survived across two passes, and the last three survived because a LATER FIX REROUTED their cases
onto a code path the mutation could no longer reach.** Nothing went red and no case was edited — the
map simply stopped being true, and re-running it end to end is the only thing that showed it. **A
fix that reroutes a case can silently un-cover the branch that case used to exercise.** ⚠ **One
ranking tier was DELETED rather than covered** — unreachable by construction, killable by no
mutation, and reading to the next person as a covered branch.

🔴 **Step 12 (2026-09-07) gates something no test in this repo could previously see: a COLOUR that
does not exist.** `check_theme_tokens.mjs` checks every `bg-`/`text-`/`border-` class in the
frontend against the palette in `tailwind.config.js`. **Tailwind DROPS a class it cannot resolve
and says nothing** — no build error, no console warning — so the instrument dropdown shipped with
`bg-bg-raised` as its background (the palette is base / sunken / surface / surface-2) and rendered
with NO BACKGROUND at all: sixty rows drawn straight over the form underneath. ⚠ **A colour that
does not exist and a colour deliberately set to transparent are THE SAME THING on screen**, so
nothing in the running app can tell you which one you wrote — this is rule 7 arriving in CSS, a
class name being a CLAIM about a definition somewhere else with nothing checking it. 🔴 **It found
three more the same minute, live, in pages nobody suspected** (`bg-bg-elevated` on the run detail
page, `text-gold-bright`, and a missing hyphen in `bg-bg-surface2`), each invisible for as long as
it had existed. ⚠ **It reads the palette OUT of the config rather than from a list typed into the
check**, so a colour added to the theme cannot start failing it. ⚠ **It carries a SELF-TEST,
because otherwise "no findings" means *the app is clean* and *the scanner is broken* at the same
time** — the exact defect it exists to stop. ⚠ **Nine mutations killed and one DELETED**: a guard
rejecting arbitrary values (`text-[11px]`) that no mutation could kill, because the rule beside it
already rejected every one of them — **a branch nothing can kill reads as a covered branch**, the
same call step 11 made about its unreachable ranking tier.

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
the LIVE `sos_fade`** were reverted to HEAD and are still unformatted.

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
it, and the LIVE `sos_fade` shipped in a commit whose message said it was excluded. **Nothing
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
- `wip/secondary-pine` — **parked TradingView work, rescued from a stash 2026-09-01.** The
  1m-engine / drift / secondary rewrite of the SOS Fade Pine strategy, one file, 276 insertions.
  ⚠ **It does NOT apply to `main` and is not meant to** — it was taken on **f70053e9
  (2026-07-19)** against `indicators/sos_fade_strategy.pine`, a path that stopped existing at the
  2026-08-13 split into `indicators/strategies/` and `indicators/engines/`. Reviving it means
  re-applying the ideas onto the current file, not merging the branch.
  🔴 **The reason it is a branch is that a stash is the most losable place git has**: it is
  addressed by an INDEX, so every new stash renumbers it, nothing pushes it, and a clone does
  not carry it. This one had already shifted from `stash@{2}` to `stash@{3}` and back inside a
  single session. ⚠ **The stash was deliberately NOT dropped** — two copies until somebody who
  knows the work confirms the branch is the one they want.
  ⚠ **Made with `git branch <name> stash@{N}`, which needs no checkout.** Two sessions share
  this clone, so switching branches to rescue a stash would yank the working tree out from
  under whoever else is in it.

---

## Never Do

- Commit `credentials.json`, `users.json`, `.env`, any `.pkl` model files, or API tokens/keys
- Commit with `--no-verify` to get past the CLAUDE.md hook. It leaves NO trace, so the next person cannot tell a deliberate skip from a forgotten one — which is the whole problem the hook exists to fix. The honest skip is a `DOCS: none - <reason>` line in the message, and it costs one sentence. **Refused at the moment you type it since 2026-09-07** — see `.claude/hooks/block_hook_bypass.py` in the `.claude/` section, and `## Committing`
- Touch `algos/` when working on `smart-money/` or `command-center/` and vice versa
- Build a second regime classifier in `command-center/` or anywhere else — `engines/regime/classifier.py` is the canonical implementation; all consumers import from there
- Build a second structure engine, fib engine, order-block engine, sessions engine, liquidity engine, VWAP engine, SVP engine, fair-value-gap engine, RSI-divergence engine, equal-highs-lows engine, candlestick-pattern engine, or news/economic-calendar engine anywhere — `engines/market_structure/engine.py`, `engines/fibonacci/`, `engines/order_blocks/`, `engines/sessions/`, `engines/liquidity/`, `engines/vwap/`, `engines/session_volume_profile/`, `engines/fair_value_gaps/`, `engines/rsi_divergence/`, `engines/equal_highs_lows/`, `engines/candlesticks/` and `engines/news/` are the canonical implementations; all consumers import from them
- Commit `engines/news/data/events.json` (or anything under `engines/news/data/`) — it is fetched calendar data, git-ignored, not source
- Commit a new or changed engine before its Pine↔Python parity check has actually run and passed (exit 0) on a real TradingView CSV export — unit tests pin the logic but do not prove parity. Build engine + tests + harness, then wait for the real export and the `compare_*.py` pass; only then commit (Aaron's standing rule, 2026-07-05)
- Hardcode a broker's history depth — including as a "sensible" DEFAULT start date on a tool. A default is a hardcode with better manners: it fails quietly in the direction nobody checks, silently narrowing every run that didn't pass the flag (`run_report.py` did exactly this until 2026-07-29). Measure the floor, or refuse to run and ask.
- Construct a `LAB_STRATEGY` class directly when a run may carry costs — go through `backtest.replay.build_strategy`. `LAB_STRATEGY` is an open contract, so a strategy may predate the `cost_profile` kwarg; passing it unconditionally crashes, and passing it conditionally reintroduces the exact bug that let the lab collect commission and slippage for months and charge neither. The helper refuses to run instead
- Report a metric as verified because its arithmetic reproduces. Every stored KPI on run `f866873aa862` recomputed to the cent and the page still misled three ways — a drawdown in dollars only, a win rate counting breakeven scratches, a concentration measured over quarters answering a different question from the one its name asks. **Ask what a reader will CONCLUDE from a number, not just whether it is correct**
- "Fix" a wrong-side stop filling at the next bar's open. It is the one-bar order delay every fill model here is built on, it is identical in Pine and Python (so parity is unaffected), and it makes the backtest look slightly WORSE than reality — the safe direction. Removing it is a real behaviour change across all five Pine files and needs its own measurement, not a tidy-up. See `strategies/python/sos_fade/CLAUDE.md` → `### Wrong-side stop fills`
- Read a `/health` response as a statement about the thing BEHIND the agent, or a `schtasks /run` exit code as evidence the task started. The MT5 agent answers `ok` while its terminal is disconnected; `schtasks` answers SUCCESS for a task Windows refuses to launch. Probe the thing you are actually claiming, and re-probe after any action you take
- Trust a probe whose NEGATIVE result a healthy system can also produce — that is not a probe, it is a coin flip you have decided to believe. The live bot asked its bars whether the terminal was alive, and an empty bar frame is equally what a quiet market returns: when MetaTrader auto-updated and restarted itself on 2026-08-04 the bot read the dead link as a quiet market and sat blind for 50 minutes with its heartbeat ticking, the watchdog green and the Bots page saying RUNNING. `account_info()` is the probe now, because it answers whenever the link is alive whatever the market is doing. **The generalisation is about VALUES, not labels: never let "no data" and "cannot ask" be the same value.** Every layer in that path was individually defensible — an empty DataFrame is a reasonable return for a bar fetcher, a null balance a reasonable write when you have no balance — and the distinction was destroyed at the bottom and unrecoverable at every level above it, leaving a blank cell as the only symptom in the entire system
- Record what you REQUESTED as though it were what you RECEIVED. The bar cache did exactly that until 2026-08-04: it fetched a window, saved whatever came back, and then marked the whole **requested** range as covered — so asking for bars through a date the broker did not have yet (every `--end today`) marked that date fetched forever, and every later run read a cache HIT and got a frame that silently stopped early. Measured: the sidecar claimed history through 2026-08-06 while the file held nothing past 2026-08-03 03:45, with the agent serving the missing bars on request the whole time. **The returned frame is clean and gives you no way to notice.** This is the same defect as the hardcoded history floor arriving from the other end of the window — the system answering a narrower question than the one asked. Clamp coverage to the data, and never into today, because a day still filling looks exactly like a complete one
- Hardcode a broker's history depth, or trust MT5's `/data_availability` for it. MT5 answers a request for a timeframe it has no history at with the nearest COARSER bars, still labelled as what you asked for — a backtest fed those runs clean and lies. Depth is MEASURED by bar density (`backtest/data/history.py`, probed per broker and cached); `/data_availability` samples one bar per end and is fooled the same way (it reported M1 back to 2007, false by ~11 years). Verify by bars-per-day, never by the earliest timestamp
- Put a non-ASCII character straight after an unbraced `$VAR` in a shell script — write `"${VAR}…"`. macOS's `/bin/bash` is 3.2.57 and folds the character's leading byte into the name, so `set -u` kills the script as *unbound variable*. Bash 5 parses it fine, so **it only ever breaks on the machine that did not write it**. *(`setup_learning_mode.sh` shipped broken — one line, the only one where an ellipsis touched a variable. Detail in `HISTORY.md`.)*
