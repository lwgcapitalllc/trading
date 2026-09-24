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
- **Advise first, don't just carry out the ask** *(Aaron, 2026-09-17)*. On everything he asks for
  or points to, think as a professional quant, algo developer and trader first. Suggest techniques
  and strategies he may not know about, without being asked, whenever they help with higher
  return, lower drawdown, a smoother equity curve, more trades (through another leg, instrument or
  timeframe, never a looser filter) or a better Sharpe. Say so when an idea fails statistically.
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

19. **The owning CLAUDE.md — or a file in its `notes/` folder — lands in the same commit as the code.** Enforced by hook. Never `--no-verify` — the honest skip is `DOCS: none - <reason>`.
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

⚠ **A Pine `strategy()` file is not finished until `scripts/check_pine_conventions.py` passes on it** — the numbered input panel, the six trade annotations and the standard result colours. Added 2026-09-16 after the convention was written down, audited once, and drifted anyway. ⚠ **It is NOT yet in `scripts/run_all_tests.sh`, and this line claimed it was for a day** — two files still fail it (the extreme leg and the session sweep), so wiring it would land a red build on everyone; run it by hand until they are fixed. What IS wired, inside step 14, is `indicators/tools/check_continuation.py`. Detail: `strategies/tradingview/CLAUDE.md`.
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

**Risk is budgeted per ACCOUNT, and never layered.** The intended rule: there is one risk pool (call it 10%, whatever the number lands on) available at any moment. Concurrent setups either SHARE that pool or the later one is BLOCKED outright. Risk is never stacked on top of risk. `exec_risk_pct` is a per-trade figure (SOS Fade's default is 5 since 2026-09-13 — its live share) and the account-level cap above it **exists on both sides** (built 2026-08-09; this line said UNBUILT until 2026-09-03). 🔴 **THE POOL IS SPLIT AS OF 2026-09-04 AND THIS LINE CALLED IT THE OPEN DECISION FOR THREE DAYS AFTER IT WAS TAKEN.** Aaron's call: **SOS Fade 5% and the extreme leg 5%**, two shares summing to the 10% cap exactly, so each bot can hold one full-size trade at once and the budget is fully allocated with nothing refused. Both bots were RUNNING on PU Prime demo 700152905 when this was checked on the box, 2026-09-07. ⚠ **A THIRD bot is a CHOICE, not a blocker, and do not write it up as one** (Aaron, 2026-09-07: *"I can lower individual bots risk or just up the cap so no issue there"*). Two routes, both his, both one write: shrink the per-trade shares so three fit under 10, or raise the cap. The only thing the doc owes a reader is the MECHANIC, and this line stated it WRONG until 2026-09-23: shares that sum past the cap are **accepted** and the bots then **share the room** by PRIORITY. 🔴 **The old text ("the bots take turns" and "the Command Center refuses the assignment at the moment it is made") has been false since 2026-09-15** — `command-center/backend/services/bot_accounts.py` → `share_overflow_reason` refuses only an UNREADABLE share or ONE bot risking more than the whole cap, and `share_note` says summing past the cap is "informational, never a refusal". At runtime `algos/shared/account_priority.py` orders the bots by `account_priority`: the higher one sizes first and the lower one sizes into what is left, refused only below HALF its share. MEASURED 2026-09-23 on three bots at 5% each against a 10% cap over 2020-2026: 5 shrinks and 4 refusals in 547 trades, and none at all at the risk levels a $100k target needs. ⚠ **The stale half of this line cost real advice** — a session read it, wrote the third bot up as a blocker and recommended shrinking all three shares, which is precisely what the sentence above forbids. The Pine input's own ceiling was raised 10 → **100** on 2026-07-27 at Aaron's request (SOS Fade's default moved 10 → 5 in both files on 2026-09-13; the Python side never had a cap), so nothing in the code now refuses a per-trade risk the account rule would.

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
| `algos/` | Live MT5 trading bots on a Windows VPS | **TWO bots trade the LIVE account 34957946 since 2026-09-11** — `sos_fade_demo` (M15) and `extreme_leg_demo` (M5), both `XAUUSD.p`, **5% each under a 10% account risk cap** (the keys say demo; they are not). Their DEMO copies `sos_fade_2` / `extreme_leg_2` are registered to run on demo **700152905**; `b_leg_demo` is BENCHED. ⚠ **Count them with `box_status`, never from this line** — it named one bot for three days after the second was assigned, and the demo account after both moved to live. A live bot imports from a frozen `deployed/` snapshot, so a `git pull` cannot move it — only `promote.py` can. ⚠ **Its order-sending code joined the snapshot 2026-09-17**; a bot promoted before then still runs that half from the repo until its next promote. A fleet kill switch and an account-mismatch halt both exist and both LATCH. |
| `command-center/` | React + FastAPI local ops platform — monitors bots over SSH, runs and grades backtests | A bot IS its folder (`algos/markets/fx/instances/<key>/`), listed by both apps from disk, and addressed by its KEY, never its display name. A broker ACCOUNT is a first-class row too. The Smart Money UI is flagged OFF behind one boolean. |
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
| `strategies/` | Strategy source by runner platform — NT8 `.cs`, MT5 `.mq5`, Python packages, and since **2026-09-02** the Pine `strategy()` files in `tradingview/` (moved in from `indicators/strategies/`; the two scratch ideas dropped to `tradingview/research/`). ⚠ **Nothing under `tradingview/` is scanned or deployed** — the lab's scanner globs `.cs` and `.mq5` only. Python ports with a GREEN parity gate: `sos_fade`, `b_leg`, `bos` (**narrow** — the gap ladder never ran), and `realign` (**narrow** — 3.5 months, market and retest entries; green 2026-09-16). The end-to-end process, and which step only a human can do, is `docs/STRATEGY_WORKFLOW.md`. |
| `indicators/` | Pine INDICATOR source. Split by DECLARATION since 2026-08-13, and since **2026-09-02 the two halves are in two different trees**: `indicators/engines/` holds the 17 `indicator()` files, and the 16 `strategy(` files moved out to `strategies/tradingview/` — Pine runs only on TradingView, so a `strategy()` file is strategy source and belongs beside the MT5, NinjaTrader and Python strategies. Nothing in any `.pine` changed in that move. ⚠ **Count them with `ls`, never from this line** — it read 16 while there were 18, and one was then deleted. **The declaration decides it, never the filename** — `structure_engine.pine` reads like a strategy component and is an indicator. Includes the from-scratch `smc_engine_v2.pine` rebuild — mid-build, and a **separate track** from the `mpc_jarvis.pine` the Python engines were ported from. Do not confuse the two. |
| `education/smc/` | The course material the engines were extracted FROM. Reference a human reads; no code reads any of it. |

## Token use — two people share one subscription

**MEASURED 2026-09-13** (`tools/token-usage/usage_report.py`, run it on each machine): one week on
one laptop was 5.6 billion input tokens, 58% of it in three sessions left open for days. **Every
turn re-reads the whole conversation**, so cost is roughly conversation size x turns.

- **One task per session.** `/clear` or a new session when the task changes; never leave one open overnight.
- **Search with a subagent on Sonnet**, not in the main conversation — each search there re-reads everything above it.
- **Tell a routine subagent not to spawn its own agents.** A general-purpose one can fan out — asked to work one doc at a time on 2026-09-13, it launched eleven.
- **Grep before you Read.** Reading any file pulls its folder's CLAUDE.md into context; a shell search does not.
- **A CLAUDE.md holds rules and an index only.** Detail goes in its `notes/` folder, and the commit hook accepts a notes file as the doc update.
- **`/context` shows what fills a session**; the usage report shows the week.

---

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
- `research/realign-chart-frame` — **a measured negative, parked 2026-09-11, never to be
  merged**; kept so the result can be re-run. Record: `strategies/python/realign/realign_optimization.md` → Run 1.
- `research/nogap-shift-entry` — **the SOS Fade no-gap shift entry, parked 2026-09-16; Aaron
  intends to return to it.** Measured no edge (Runs 27–30 in
  `strategies/python/sos_fade/sos_fade_optimization.md`). ⚠ It adds three settings the live
  bots' frozen code refuses, so none may reach a live bot's config before a promote ships them.

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

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 123 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/strategy-overlap.md` — Do the bots trade the same move? — the overlap audits

**Read before touching:** changing either bot's entry logic, adding a bot to an account, or quoting an overlap or correlation figure.


### `notes/checks-and-gates.md` — The repo-wide checks — parity gates, golden exports and Pine drift

**Read before touching:** an engine, a parity gate, a golden export, a Pine block, or a step of the full test run.


### `notes/repo-tooling.md` — Standalone scripts, tools and the course material

**Read before touching:** a bootstrap script, a scheduled task on the box, a standalone tool, or the learning notes.


### `notes/claude-config.md` — Claude's own configuration — commands, hooks and guards

**Read before touching:** a slash command, a hook under `.claude/`, or the doc-size guard.


### `notes/mcp-servers.md` — The three servers Claude drives instead of a shell

**Read before touching:** adding a route that touches money or the live box, or changing what Claude is allowed to drive.

- The MCP servers — what Claude is handed instead of a shell

### `notes/deploying.md` — Deploying to the trading box

**Read before touching:** deploying to the box, stopping a bot, or restarting one.

- VPS Deploy Workflow
- 🔴 A deploy that would ship nothing now REFUSES and leaves the running bot alone — it used to restart it anyway, which cancelled a resting order for nothing (2026-09-23)

### `notes/committing.md` — Committing — the doc rule, the evidence rule and the tripwires

**Read before touching:** changing a git hook, the commit rules, or the shared-clone workflow.

- Committing — the docs land in the same commit as the code

### `notes/testing-and-linting.md` — Tests, formatting and linting

**Read before touching:** test plumbing, the selector rules, the linter config, or a suite that will not start.

- Formatting, linting and the test gate
