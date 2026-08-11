# CLAUDE.md — Command Center Backend

**Purpose:** FastAPI backend (`:8000`) — owns all SQLite state, talks to the VPS via SSH + HTTP agents, runs the smart-money pipeline via subprocess, and drives NT8/MT5 backtests.
**Scope:** This covers backend conventions, routers, services, DB, and VPS interaction. It does NOT cover the frontend (see `../frontend/CLAUDE.md`) or `algos/`/`smart-money/` source.
**Status:** Live — lab (strategies, rulesets, backtests, sweeps, optimizations, stress tests, MT5 runner, Python runner) all shipped.
**Last reviewed:** 2026-08-10 (latest) — 🔴 **THE SOLO CONTROL WAS COMPUTED ON EVERY SHARED STACK AND THROWN AWAY, SO THE ONE BOOK THAT ANSWERS "WHAT WOULD THIS HAVE MADE ALONE" DID NOT EXIST ON DISK.** Aaron switched MPC SOS Fade off on stack `st_94aeb25f0c`, read that MPC B-LEG had made **$47,758,999**, ran the same strategy standalone over the same window and got **$21,064** — *"how is it when I combine them the b leg make forty seven million on the stack, but only twenty one thousand by itself?"* ✅ **MEASURED, and both numbers are right: 99 trades either way, 99/99 identical entry timestamps, 99/99 identical entry AND stop prices, and +17.8674R either way to four decimals.** The only thing that differs is `risk_usd` — the last trade risks **$16,925,791** of the shared balance against **$3,102** of its own, **5,456x**, for the identical +0.014R — because in a shared account the B-LEG sizes off a balance A+ grew to ~$169M. ⚠ **Profit factor is distorted too and that one is quieter: same trades, same R, same 51.5% win rate, PF 1.505 solo → 3.111 shared**, because dollar PF weights each trade by how big the balance was when it happened. 🔴 **`_persist` kept `solo_r` and `solo_closing_balance` and DISCARDED the control's trades**, so a subset of a shared stack could only be composed from the SHARED book — which answers *what did this leg contribute to an account the others built* and reads as *what this leg made*. `_write_solo` / `solo_book` keep the full book now, `GET /stacks/{id}` serves it as the leg's `solo_equity_curve` / `solo_daily_pnl`, and **a SCREEN gets nothing** (there every leg already traded its own full account, so a second copy would be two fields holding one fact). 🔴 **`EquityPoint` did not declare `r` — the FIFTH field this model has dropped that was already on disk** (`entry_ms`, `exit_ms`, `favorable`, `adverse`, now `r`); it is the one per-trade figure a change of position SIZE cannot move, which is exactly what a portfolio page needs. ✅ **`scripts/backfill_stack_solo.py` re-derives the missing books for stacks replayed before today, and it REPRODUCED the stored scalars exactly** (17.8674R / 141.1774R, $31,063.99 / $49,214,855.53) — the cross-check that it replayed the same thing — leaving every stored row, KPI and leg curve untouched. It refuses to overwrite an existing book without `--force`. ✅ **DRIVEN through the running backend and a real browser, not reasoned about: both legs on reads +$184,416,910, B-LEG alone reads +$21,064** (his standalone figure to the dollar) **and A+ alone reads +$49,204,855**, with no console errors. ✅ 4 new backend tests (920 green, 1 pre-existing failure) + 4 browser checks; **non-vacuity by MUTATION on all of them**, seven mutations each turning its own named check red. **The standing lesson is about a control that is computed and not kept: the shared runner has always known the honest answer — it replays every leg alone precisely so a difference is attributable — and it reduced that replay to two scalars, which is enough to CHECK the seam and not enough to SHOW anyone. A measurement you summarise to a number you can compare is a measurement you can no longer display.** Earlier: 2026-08-09 — 🟢 **ADD AND REMOVE, AND THE THING REMOVAL NEEDED WAS A STATE RATHER THAN A BUTTON.** Aaron: *"I don't see no ability to say, like, add bot… Same thing if I wanna remove a bot from account, I can remove it."* `PATCH /bots/{key}/account` is the whole API, and it writes the bot's OWN config — there is no membership record, because two bots naming one account ARE sharing a balance and a stored grouping would be a second answer that can disagree with them. **`account: null` is the BENCH**: registered, configured, trading nothing, which is where a removed bot lands. 🔴 **A MOVE WRITES FOUR FIELDS, NOT ONE, AND THE CAP IS THE ONE THAT BITES.** `bot_accounts.assign_plan` adopts the target's account, server, terminal path and **risk cap** — because `live_config._assert_account_cap_agrees` refuses to start EVERY bot on an account whose caps disagree, so a bot arriving with its own cap would not merely misconfigure itself, it would take the bots already there off the box at their next restart. It REFUSES outright when the target's bots disagree or one is unreadable, rather than adopting the reported `None`. ⚠ **A RUNNING bot is refused (409)**: it read its config at startup, so the write cannot reach the process, and the page would show it under one account while it traded another — a screen lying about a live position rather than a stale setting. 🔴 **`bench` and `unknown` ARE DIFFERENT GROUPS and merging them is the defect.** Both lack an account NUMBER, so keying `group_by_account` on `account` alone files a bot somebody deliberately removed beside a bot whose config is broken, under one heading, with the same controls. `AccountGroup.kind` separates them, and `stacked` is now guarded on it — two benched bots share no balance, and a **Stacked** chip on a bot that is not trading is a false alarm about doubled risk, the one direction that chip must never fail in. ✅ **`magic_clash` replaces the raw Magic column** (*"I don't know what the column magic even means"*): the number told the reader nothing while the fact it encodes — two bots on one account each reading the OTHER's orders as their own — matters enormously here, so it is REPORTED when true and absent otherwise. 🔴 **THREE COLOUR CLASSES ON THE ACCOUNTS TAB WERE NOT TOKENS AT ALL** (`bg-negative-muted`, `text-negative`, `bg-positive-muted`), so Tailwind emitted nothing and the cap chip and the disagreement banner had been rendering with NO COLOUR since they shipped. **A misspelled token does not fail a build; it silently draws nothing.** ✅ **DRIVEN through the running backend rather than reasoned about: the endpoint moved `mpc_bleg_demo` onto account 700107749 — cap 10% adopted, `stacked: true`, `cap_takes_turns: true`, no clash — and BOTH instance configs still load under the startup guards**, which is the check that says the assignment left the account coherent; then moved back to the bench, with the config diffed byte-for-byte against its original. ✅ 21 new backend tests (916 green, 1 pre-existing failure) + 11 browser checks, **non-vacuity by MUTATION** since the module is new. 🔴 **ONE OF THOSE TESTS WAS VACUOUS AND PASSED AGAINST ITS OWN MUTATION**, which is the sharpest thing in this pass: it asserted that two UNREADABLE configs do not manufacture a magic clash — and an unreadable bot is grouped under `unknown`, where `magic_clash` returns early on `kind`, so the guard it named was never reached. The reachable half is a READABLE config with no `magic` key, which is what it drives now; the `unreadable` clause beside it is defensive and is deliberately NOT claimed as covered. **The standing lesson is that "remove" was never a button: it needed a resting state for a bot to be in, and the moment that state existed, every place holding its own copy of "which account" became a place that could disagree with it — `algos/shared/bot_state.py`'s hardcoded `BOT_ACCOUNTS` was exactly that, and it fed the Account column on this very page.** Earlier the same day: 🟢 **A LIVE STACK IS SOMETHING YOU READ, NOT SOMETHING YOU CONFIGURE.** Aaron asked to manage stacking from the command center rather than from a chat: group the bots on an account, set one shared risk cap, see a **Stacked** indicator on the page that shows what is running. `services/bot_accounts.py` + `GET /bots/accounts` + `PATCH /bots/accounts/{account}/risk-cap`. 🔴 **THE GROUPING IS DERIVED AND THAT IS THE WHOLE DESIGN: two bots naming the same `account` in their instance configs are trading one balance whether or not anybody grouped them**, so there is no stored membership and no drag-and-drop — a stored grouping is a second answer that can disagree with what the bots actually do, which is this app's most-repeated defect. The broker is the source of truth about exposure; the instance config is the source of truth about which account a bot points at. ⚠ **THREE STATES FOR THE CAP AND THEY MUST NOT COLLAPSE INTO TWO** — a number (capped), `None` (UNCAPPED, deliberately, and what every measured result in this repo was taken on) and **unreadable** (the config could not be parsed, so the cap is UNKNOWN). `unreadable` is its own field rather than a bot that quietly vanishes from its account, because **a bot missing from a group reads as an account with fewer bots on it — the most reassuring wrong answer available on a page about how much risk is on.** 🔴 **When the bots DISAGREE the endpoint reports NO cap — deliberately not the max and not the min**, because picking one would invent a ceiling nobody configured and hide the fault behind a number that looks exactly like a configured one. ⚠ **`cap_change_plan` REFUSES the whole write when any config is unreadable rather than skipping it**: writing the cap to three of four leaves exactly the disagreement the mechanism exists to prevent, and it would report success. ⚠ **`cap_takes_turns` is a FACT the two numbers imply and neither states** — at a 10% cap against two bots each risking 10% the account never holds both at once — reported so the page can show it instead of leaving it to be discovered by a bot that mysteriously never trades. ⚠ **The PATCH never reports the cap as APPLIED**: it is not in `live_config.RUNTIME_RELOADABLE`, so it is picked up at a bot's startup and nowhere else, and the response says `restart_required` and names the bots. ⚠ **`risk_cap_pct: 0` is REFUSED (422)** — it blocks every order on the account, and if that is the intent it is the FLEET HALT, which stops orders without making every bot log a risk refusal. ⚠ **The endpoint does NOT touch the VPS** — it reads the same instance configs the bots read, so it is pollable and still answers while the box is unreachable; whether a bot is RUNNING is a different question with a different source and the page joins the two on `key`. ✅ 20 new tests (900 backend green, 1 pre-existing failure), **non-vacuity by MUTATION** since a fail-watch is vacuous for a new module — four mutations, four distinct tests red (a missing cap made inheritable, the max picked on a disagreement, an unreadable bot skipped, a single bot claiming turn-taking). **The standing lesson is about where a fact lives: an account-level number stored in a per-bot file is not one setting, it is N settings sharing a name — so the API's job is not only to write it but to say when they have stopped agreeing.** Earlier the same day: 🟢 **A STACK IS TWO DIFFERENT EXPERIMENTS NOW, AND THE PLAN'S OWN VERIFICATION CRITERION WAS WRONG.** The lab side of shared-risk stacking landed (`docs/SHARED_RISK_STACK.md` items 3-5): `stacks` gained `mode` + `account_size` / `risk_cap_pct` / `entry_floor_pct`, `POST /stack` branches on the mode into `services/portfolio_runner.py`, and `GET /stacks/{id}/contention` serves what the budget did. **The runner CALLS `backtest/portfolio/run_stack` and owns no account model of its own** — a second one would be a second answer about what a shared budget does, and the live allocator already has to be a third. ✅ **DRIVEN END TO END through the running backend, not reasoned about: XAUUSD M15 2024, two legs, $10,000, cap 10% — 33 trades, +26.35R, $36,805.85 closing, and every leg posts the SAME R shared as solo**, which is the control that says the seam moved no decision. 🔴 **THE DOC SAID A SHARED RUN MUST CLOSE LOWER THAN THE SCREEN AND SAID A HIGHER ONE MEANS THE GATE IS NOT ENFORCED. The measured run closes $36,806 against the screen's $26,870 — HIGHER — with the cap working and nothing refused.** The prediction assumed refusals are the only difference; they are not. **A screen gives each leg a private balance and a shared account COMPOUNDS both onto one**, so the second leg sizes off a balance the first has grown. Two effects in opposite directions, and the compounding one is unbounded while the refusal one is capped by how often the budget is genuinely full. **Compare R, never net dollars** — that check would have failed on a correct implementation. 🔴 **The first real launch DIED IN A BACKGROUND TASK**, because `exec_secondary` has defaulted ON since 2026-08-07 and a leg on a merged clock is one bar frame, so `legs._refuse_unreplayable` raised. The router PINS it now and **writes the pinned value onto the child run**, so the row and the replay cannot disagree — and `test_shared_stack.py` READS `legs.py` and fails if it grows a refusal the router misses, rather than restating the list. ⚠ **The schema change needed the column declared in BOTH the migration list and the CREATE TABLE, and only one of those is obvious**: migrations run FIRST, so on a fresh database `ALTER TABLE stacks` fails and is swallowed — leaving a brand-new clone without the columns while every existing database has them. **Proven both ways by test.** ⚠ **`mode` defaults to `'screen'` and every account knob is NULL there** — a screen has no account, and a stored `0` would render as an account with no money while making "no cap" indistinguishable from a cap that refuses everything. ⚠ **A shared stack REUSES NOTHING**, deliberately: a finished standalone run was measured on its own full account with nothing able to block it, so dropping one in would put an un-contended leg beside contended ones. ✅ **Cancel reaches the replay** — `simulate` gained `progress` / `should_cancel`, and a cancelled run RETURNS a partial book flagged `cancelled` which the runner refuses to persist. 10 new backend tests (880 green, 1 pre-existing failure), 5 new `backtest/` tests (377 green), 10 browser checks. 🔴 **THREE of those browser checks were VACUOUS on their first run and each failed differently — the file records all three, because every one looked like a green test.** The route mocks keyed on `http://localhost:8000` while the app fetches through the Vite proxy at `/api`, so three checks silently read the LIVE lab; the "a screen renders no panel" check passed against its own mutation, because the hook is disabled there so the panel cannot render either way (it counts the FETCH now); and the counter that fixed it was registered BEFORE the mock, which shadows it — Playwright matches the most recent route first. **The standing lesson is the doc's, not the code's: a verification criterion written before the thing exists is a prediction, and this one would have condemned a working risk gate.** Full detail: *Shared-account stacks* below. Earlier: 🔴 **THE CANDLE LAYER'S "DRAWDOWN ZONE" WAS A REGION IN TIME, AND THE ZONE IS A REGION IN PRICE — THAT ONE MISTAKE PRODUCED FOUR SEPARATE COMPLAINTS ACROSS TWO ROUNDS.** Aaron reported six trades off the chart. ✅ **MEASURED on run `e51d95f212e3`, 166 anchors, and the defects point in OPPOSITE directions, which is why no single bound could have fixed it:** (1) **255 of 1084 marks — 23% — sat entirely on the FAVOURABLE side of the entry**, 35 from a confirm tail measured off the end of the drawdown instead of off the turn (his 2026-07-15 long's only mark sat **$25 above the entry, two bars into a rally**, and named the chip) and 196 from the span opening at the ENTRY BAR, so a trade that ran into profit before coming back painted the whole excursion between — **one turn is 112 bars after entry**. (2) 🔴 **A LOSER WAS MARKED AFTER IT WAS CLOSED**: a stopped-out trade's adverse extreme IS its final bar, so `turn + _CONFIRM_BARS` reached past the exit — *"Trade already lost. You already hit stop loss… I don't care what the candles after the trade. It has to be within the trade."* (3) 🔴 **AND THE FIRST FIX WENT TOO FAR THE OTHER WAY.** Walking one contiguous excursion and stopping at the first favourable bar meant that when price came BACK to the entry an hour later, the re-test was outside the zone — while the chart's own red box plainly covered it. *"we came back up to entry. And there was at least three different candles you coulda highlighted there, and you didn't highlight any of them."* ✅ **The rule is now one price test and one clamp: a bar is drawn while ANY part of it trades on the adverse side of the entry, anywhere between the entry bar and the EXIT bar.** `_drawdown_end` is DELETED — no walk can express "come back later" without also swallowing the profit in between. ✅ **Driven through the live backend: 1090 → 853 marks, ZERO past any exit, 31 outside the band and every one within `_CONFIRM_BARS` of the extreme; his 2026-02-15 short gains the two re-test `Hammer`s, his 2026-05-11 loser loses the `Hammer` printed 30 minutes after the stop.** 🔴 **A FOURTH defect fell out of the audit and nothing had ever reported it: `_anchor_bars` required `j > i`, so a trade that OPENS AND CLOSES INSIDE ONE BAR read as having no end at all** and fell through to the 3-bar fallback — **4 marks on 3 trades, one a `Bearish Engulfing` drawn after a trade that lasted 4 minutes.** `>=` now; only an end BEFORE the start is unusable. ⚠ **FOUR of the six candles Aaron named are NOT this layer's doing and were MEASURED clause by clause against `candle_sticks.pine:32`** — three fail `open >= close[1]` by **$0.05 / $0.06 / $0.01** (a body that misses a full engulf by a cent) and one passes the engulf but fails the **117-bar uptrend gate** (price $13 LOWER than 117 bars back, so the indicator will not call it a bearish reversal). **All four are in the zone and would be painted the instant the engine detected them; his own TradingView chart does not draw them either.** Do NOT add a tolerance — a 0/1 flag has no "close enough", and the engine's parity with the indicator his brother reads is the whole point. ✅ **6 new tests, 4 WATCHED RED against HEAD**, the rest by MUTATION; 870 backend tests pass, 1 pre-existing failure. ⚠ **Existing runs need Rebuild chart.** **The standing lesson is about restating a reader's words as a rule: he kept saying "in the drawdown", which is the red box on his screen — a region in PRICE — and every version of this that reasoned in BARS was self-consistent, easy to test, and answering a question nobody asked.** Earlier the same day: ⚠ **THE MT5_LAB DEMO ACCOUNT NUMBER CHANGED AND THE OLD ONE WAS WRITTEN INTO SIX PLACES, TWO OF THEM HERE.** Vantage demo **25815745 → 25893735** (same broker, same `VantageMarkets-Demo` server, same `XAUUSD` symbol), confirmed off the running agent's own `/status`. The two test fixtures in `test_agent_supervisor.py` and `test_system_health.py` carried the dead number as their stand-in account. ⚠ **A fixture value is not a claim about the live system, which is exactly why this is worth a line: it is the kind of stale number a reader copies out believing it, and nothing fails when it rots.** Both updated; 36 backend tests green. ⚠ **The account number is the only thing that moved on this side** — `mt5_agent_client.status()` reads it off the terminal, so no code was ever keyed to the literal. The finding with teeth is in `backtest/fills.py`: the stored Vantage SWAP was measured on the retired account and no longer matches what the terminal quotes. Earlier: 2026-08-08 — 🔴 **THE CANDLE LAYER STOPPED PAINTING TWO BARS PAST THE ADVERSE EXTREME, SO IT COVERED LESS THAN HALF OF SOME DRAWDOWNS.** Aaron, off the chart: *"In drawdown, you're supposed to map all the applicable candles in line with the order we trade. I've hovered over the candles which I think you've missed."* The span ended at `turn + _CONFIRM_BARS`, and **the bar that makes the adverse extreme is nowhere near the end of the zone**: on his 2026-06-18 short the turn is 02:00 while the trade stays above its entry until 05:30 — **21 bars of drawdown against a 9-bar span**. ✅ **MEASURED on that trade: the zone holds THREE pattern candles and the layer drew ONE** — the opposing `Bullish Harami` at 01:30 — so the `Inverted Hammer` at 03:00 and the `Hammer` at 05:45 were never painted and the chip read **`no matching candle`** for a trade that plainly had one. `_drawdown_end` walks forward from the turn while the bar still trades on the adverse side of the ENTRY and stops at the first bar lying entirely on the favourable side, so the span is exactly the bars touching the red band the reader is pointing at. ✅ **MEASURED over 166 anchors: 846 → 1090 marks (with 364→480 / neutral 398→511 / against 84→99), 149 of 166 anchors now carry one**, and that trade's chip reads `Won · Inverted Hammer` — **driven through the live backend, not the probe.** ⚠ **It walks from the TURN and BREAKS on the first favourable bar**, so it is one contiguous excursion; scanning the whole hold for any bar back near the entry would re-open the zone every time a winner retraced months later. ⚠ **A bar counts while ANY of it is adverse** — the same test as *does this candle sit in the red band* — rather than only while it is entirely adverse, which would drop the candle whose wick made the very high the zone is measured to. ⚠ **A 3/3 MISS passes NO entry price and keeps the turn-relative window, deliberately: no position was opened, so it has no drawdown.** ⚠ **`reversal_anchors` is a 5-tuple now** (`…, entry_price`). ✅ **3 new tests; the one that matters WATCHED RED against HEAD** naming the unmarked candle, and the two pins proven by MUTATION (deleting the walk's `break`; defaulting a missing entry to the start bar's close). 🔴 **The second pin was VACUOUS on its first attempt and PASSED under its own mutation** — it asserted on the MARKS, and the substituted price happened to fall the wrong side of one wick and cut the walk short anyway; it drives `_reversal_span` directly now, because the rule under test is the span. 864 backend tests pass, 1 pre-existing failure. ⚠ **Existing runs need Rebuild chart.** Earlier: 🔴 **A DRILL-DOWN PAINTED THE RUN'S OWN TIMEFRAME'S STRUCTURE ON SOMEBODY ELSE'S CANDLES, AND AN INTERNAL BREAK LINE NAMED A LEVEL THAT NEVER BROKE.** Two defects on the chart's structure layer, reported by Aaron against his TradingView `mpc_assistant.pine` — *"if its a UI bug and not plotting the structure engine 100% exactly figure it out and fix it"*, then *"the Command center internal SOS is not showing the horizontal lines like the mpc_assistant"*. 🔴 **(1) STRUCTURE WAS COMPUTED ONCE, ON THE RUN'S TIMEFRAME, AND DRAWN OVER WHATEVER CANDLES WERE ON SCREEN.** A drill-down replaces the bars and nothing replaced the overlays, so an M5 drill of a 15m run drew the M15 replay's swings on M5 candles: the chart's own OHLC readout was the M5 bar while every label on it read `SOS @4242.99` / `iSL @4247.23` — **prices that are not swings on anything underneath them. The M5 answer, and TradingView's, is `SOS @4224.73`.** `_drill_structure()` replays the engine over the drill window's OWN bars and the endpoint ships `overlays`. ⚠ **`_DRILL_WARMUP_BARS = 2_000` of context is replayed IN FRONT of the window** — the engine is a streaming state machine, so a cold replay opens with no swings and then "catches up", which reads as a broken layer rather than a warming one; only overlays reaching into the window are returned. ⚠ **Nothing errored and both halves were internally correct** — the M15 overlays were right about M15 — which is why it read as an engine disagreeing with the indicator it was ported from. 🔴 **(2) THE INTERNAL BREAK LINES WERE ANCHORED ON THE FIB SEED, WHICH IS A LEG AND NOT A LEVEL.** `structure_overlays.py` took both the price and the bar from `ifib_seed_ash`/`_asl`, and at five of the engine's six internal-break sites the end of that leg *happens* to be the level that broke. At the first bear-iSOS branch it is not: the break is `i_last_hl` while the seed's bottom is `i_tracked_ext` — a different price on a different bar. ✅ **MEASURED over 2.5 years of real cached M5 bars, 169 internal breaks: iBOS bull 65/65, iBOS bear 57/57 and iSOS bull 22/22 land on the broken wick — iSOS bear was 3/25**, drawn wrong by up to $18.47. ⚠ **The reported symptom was the LINE, not the price, and that is the transferable half: a wrong anchor bar can land ON the break bar, and a zero-width `hline` renders as NOTHING** — so the `iSOS` tag appeared with no line beneath it. **21 of 169 lines were ≤1 bar long; now 0, and 169/169 anchor on the broken wick.** On Aaron's own window the 13:05 iSOS went from 4230.86 over **0 bars** to 4249.33 over **77**. ⚠ **`int_break_origin_loc` is NOT a substitute and the existing comment warning against it was right** — it is the order-block scan origin and over the same 169 breaks it lands on the broken wick **zero** times in every category, so the engine had to grow four capture-only `*_bos_loc` / `*_sos_loc` fields (see `engines/market_structure/CLAUDE.md`; proven cosmetic by A/B replay, 12,308,208 field values over 186,488 bars, **0 differences**). ✅ **14 new tests across `test_chart_drill_structure.py` and `test_structure_internal_breaks.py`, 5 of the 7 internal-break ones WATCHED RED against HEAD.** 🔴 **One was VACUOUS on the first attempt and PASSED against the defect, and it is the sharpest lesson here.** It asserted only that a line starts on a bar whose wick carries the line's own price — but under the bug the price and the bar are a **matched pair** taken from the fib seed, so the line sits perfectly on a wick while describing a level that never broke. **The test was comparing the anchor against itself.** It now replays the engine independently and diffs the drawing against the engine's own break price; the old assertion is kept beside it, labelled as pinning the pair rather than the price. ⚠ **A LATENT bug was found and fixed in the same file and is recorded as latent, not as live:** `_fetch_candles` read `astype("int64") // 1_000_000` off a DatetimeIndex whose unit **pandas chooses**. Nanoseconds is the pandas 2 default, so the divide is correct on this venv (2.3.3) and nothing served from it was ever wrong — but **pandas 3 makes MICROseconds the default and the same divide then yields epoch SECONDS wearing the name `_ms`**, every candle 1000x too small, silently (measured on pandas 3.0.5: `1785888000` instead of `1785888000000`). `as_unit("ms")` states the unit instead of assuming it and is byte-identical under pandas 2. **A pin is what makes a bug latent, and a pin is not a fix.** ✅ 859 backend tests green; the one failure is the documented stale `0.33`-vs-`0.32` spread assertion in `test_python_runner.py` and is not mine. ⚠ **The Pine parity gate is OWED and the A/B replay is not a substitute for it** — no `structure_engine_export.pine` CSV is on disk, so `compare_tradingview.py` could not run; same position the fib engine was in on 2026-08-02. ⚠ **Recorded and NOT fixed: a COARSER display resample (M30/H1/H4/D1) still draws the run's base-timeframe structure**, because the swap is gated on `isFetchMode = selectedMin < baseMin` — the same class of defect as this one, arriving from the opposite direction. **The standing lesson is about what a drawing is checked AGAINST: both defects put a correct number on the wrong bars, nothing raised, and every layer was self-consistent — the chart had no independent source of truth for what it was drawing, and neither did the first test I wrote for it.**

**Earlier the same day:** 🔴 **"DEEPEST" WAS BEING MEASURED IN TIME, NOT IN PRICE — AND A WINNING SHORT WAS STILL NAMED AFTER A BULLISH CANDLE.** Aaron, off two more trades. **(1)** When no pattern bar reaches the turn the span still has a deepest one, and it was `pool[-1]` — the LAST bar, i.e. most RECENT rather than deepest. ✅ **MEASURED on his 2026-06-16 short: the named candle was a Bearish Harami at high 4345.02 while the deepest aligned one is a Bearish Engulfing at 4349.27, $4.25 further into the retracement** — *"the deepest best entry was on a bearish engulfing yet you did not highlight it."* `_deepest_bar` reads the adverse extreme now; **the deepest bar moves on 13 of 166 anchors and the NAME changes on 8.** **(2)** The name fell through to an OPPOSING candle when the span held nothing else — *"Shouldn't it be a neutral candle, no candle or best yet a bearish candle?"* — so the preference ends at NEUTRAL and below it the chip says **`no matching candle`**, which is a different fact from `no candle`. ✅ **82 named as asked / 56 neutral / 19 no candle / 9 drawn-but-unnamed, and ZERO named against.** ⚠ **The bar stays PAINTED and stays `deepestOf` — 846 marks either way** — because showing the opposing candle is half the layer. ⚠ **A red candle is not a pattern**: his second trade's retrace zone is 9 bars and ONE carries a pattern, against the first's 21 bars carrying 8. ✅ 5 tests, **fail-watch VACUOUS (the module gained a symbol, so the file fails to import at HEAD) — non-vacuity by 5 MUTATIONS**, one of which was itself vacuous twice before the fixture put one bar INSIDE the other. 847 backend tests pass, 1 pre-existing failure. ⚠ **Existing runs need Reload charts.** Earlier: 🔴 **THE CANDLE A TRADE WAS NAMED AFTER WAS CHOSEN BY NEARNESS, SO A WINNING LONG READ `Won · Bearish Engulfing`.** Aaron, off two screenshots — a long that won named with a bearish candle and a short that won named with a bullish one: *"I should see BULLISH candle for long trades or BEARISH candle for short trades."* The three-tier direction PREFERENCE existed and was only ever applied to the patterns ON one bar; **which BAR became the span's `deepestOf` was still whichever pattern candle sat closest to the turn, whichever way it pointed.** ✅ **The rule is now the outcome's question, and it is Aaron's**: *"if I won it should default to the BEST candle that helped or COULD HAVE HELPED signal the reversal… If I lost it should default to the candle that signaled why I lost. If I missed the trade it should default to the DEEPEST CORRECT candle that I could have used to enter."* So a WINNER and a MISS want the setup-aligned candle and a **LOSER wants the OPPOSING one** — `_wanted_direction(direction, outcome)`, and `reversal_anchors` carries a fourth element to feed it. ✅ **MEASURED over 194 anchors, old vs new: 69 → 98 named with the candle the reader asked for, and 44 → 10 named against it** — losers moved most (33 named with an aligned candle → 4), and every one of the surviving 10 is a span that contains ONLY opposing candles, which is the deliberate fallback. ⚠ **The NEUTRAL tier had to be a real tier and two tiers was not enough**: 59 of 194 spans hold no directional candle at all, so `preferred or anything` picks an opposing bar whenever it sits nearer the turn. ⚠ **This orders the NAME and paints nothing differently** — pinned by a test that asserts both readings of one span draw identical candles, because the opposing tier is half the layer (*"it will show me why I was wrong"*). ⚠ **`deepestNames` is keyed PER ANCHOR**, because one bar can be the deepest of a losing trade and a 3/3 miss on the same leg and those two want opposite directions — a single `label` is whichever anchor reached the bar first and is nobody's answer. ⚠ **A miss is `"miss"`, never `"loss"`** — no trade was taken, so the question is which candle it could have been entered on. ✅ **8 new tests. The fail-watch against HEAD was VACUOUS and is recorded as such** — five of the eight died on the tuple unpack, i.e. on the signature change rather than the rule — so non-vacuity is by **MUTATION**: five mutations (loser rule removed, neutral tier removed, fallback removed, `deepestNames` dropped, missing outcome defaulting to loss), each turning its own named test red. 842 backend tests pass, 1 pre-existing failure. ⚠ **A cached `chart_spec.json` keeps the old naming — existing runs need Reload charts.** **The standing lesson is that a preference applied at one level is not a preference: the direction rule was correct, tested and doing nothing about the choice that actually reached the reader.** Earlier: 🟢 **THE PRICE CHART PAINTS THE CANDLE THAT TURNED PRICE, AND THE FIRST VERSION LOOKED RANDOM BECAUSE OF WHERE IT WAS ALLOWED TO PAINT.** Aaron's ask: highlight the reversal candle at his trades and at the setups he missed, *"so I could do analysis and say, can I add candle patterns as an additional confluence to get better entries or avoid bad trades"*. The canonical `engines/candlesticks/` engine is replayed server-side into one navy candle per setup. 🔴 **The anchor set is the whole feature, and it was wrong: BLOCKED setups were anchors, 324 of them against 159 trades and 35 three-of-three misses — two thirds of every mark — and since the Blocked layer defaults OFF they painted navy candles where the reader could see no setup at all.** Reported off the screen in exactly those words. ✅ **518 anchors / 424 marks → 194 / 153, measured.** 🔴 **The second defect was a `Bearish Engulfing` marking a LONG that WON**: ranking started at nearest-the-extreme, so whichever pattern sat closest won regardless of which way it pointed. Direction is now a three-tier PREFERENCE — aligned, neutral, opposing — with nearness the tie-break WITHIN a tier. ⚠ **The opposing tier is KEPT and is half the point** (*"if not, it will show me why I was wrong"*), so this is a preference and never a filter: **89 aligned / 49 neutral / 15 against / 41 with no pattern at the turn**, measured over the 194 anchors. ⚠ **The NEUTRAL tier does most of the work, and the reason is in the source Pine** — ten of its fifteen rules gate on a trend lookback, so in an uptrend the bullish rules cannot fire at all, which is exactly why the reference mark was bearish. ⚠ **A WINNER is searched over its whole HOLD**, because *"the ultimate reversal point before the trade went into my favour"* is the deepest adverse price of the hold — MEASURED at a median 2 bars past entry but **p90 27 and worst 112**, so the obvious fixed window finds the real turn on barely half of them; a ±2-bar tolerance stops a long hold reporting a distant pattern as its turn. ✅ **Aaron's third question — a 3/3 miss with no mark — was MEASURED rather than reasoned about: all nine unmarked 3/3 misses have ZERO patterns anywhere in their window.** No pattern at the turn is a real answer. ✅ **The pattern NAME is a Chart setting now, default OFF** — the tags carry no cross-overlay de-collision, unlike the batched `LABEL` template, so they write across neighbouring candles; the colour is the marker. 30 backend tests + 4 browser checks, **all proven by MUTATION** (a fail-watch is vacuous for a new module). 🔴 **Two existing browser checks broke and broke CORRECTLY — they read the opening viewport, which held a mark only while the run carried 424 of them, and an empty viewport is pixel-identical to a layer that never draws.** 810 backend tests green, 1 pre-existing failure. **The standing lesson is about scope rather than correctness: every individual mark this layer drew was the right candle by its own rule, and the feature still read as broken, because the rule was allowed to answer a question in places the reader could not see one being asked.** Before trusting a layer that annotates, check that everything it annotates is VISIBLE on the same screen. Earlier: 2026-08-07 — 🔴 **THE BOTS PAGE'S VERSION NUMBER WAS `v0` AND NOTHING HAD EVER WRITTEN IT.** Aaron asked the one question that tab exists for — *"what version do I have compiled in my backtester versus the version that is deployed"* — and the page could not answer it: `strategy_version` defaults to 0 in `live_config.py` and no code path assigns it, so the card read `v0` before a promote and `v0` after. `services/bot_versions.py` builds a real one — **the number of commits that have touched the bot's trees**, so it moves only when the bot's code moves, both machines compute the same number from the git history with no registry to sync, and subtracting two of them IS the work waiting to go out. Live: **v100 deployed → v121 in the backtester, 21 behind.** ⚠ **Deliberately NOT the lab's own `strategy_versions` registry** — that hashes the strategy PACKAGE while a bot runs the package plus `engines/` and `backtest/`, so it would sit unchanged while the engines beneath it moved: the exact failure `deployment_hash` exists to prevent, re-introduced as a label. ⚠ **`trees_for` mirrors `promote.py::repo_trees` and a test READS that file to pin it** — a tree promoted but not counted deploys while the page says up to date. ⚠ **It also names the settings that would change WITHOUT being asked** (a repo default moving under a config that does not pin it — the 36-hour time stop, today), reproducing `promote.py --dry-run`'s four independently, **plus one it does not report: `exec_secondary` went Off → On in the repo and this bot PINS it Off.** ⚠ **`ast`, never `exec`** — it parses config source out of an arbitrary historical commit. ✅ 28 tests, **non-vacuity by MUTATION** (a fail-watch is vacuous for a new module): four mutations, four distinct tests red. Full detail: *A bot's VERSION* below. Earlier: 🔴 **THE PRICE CHART TOLD AARON THE BROKER HAD NO MORE 1-MINUTE HISTORY, AND IT WAS READING THAT OFF OUR OWN CACHE.** He drilled to M1 and got ~100 bars behind a red *"No earlier M1 data — all the broker still has"*, on a symbol whose real M1 history runs back to 2018-09-14 (~2.8M bars). ✅ **The chart was faithfully reporting a lie told one layer down** — the bar cache claimed 45 days it did not hold (full record in `backtest/CLAUDE.md`) — but `hard_edge` is what turned *we have no more* into *there IS no more*: it was `oldest bar is well past what we asked for`, which is a fact about OUR data being used to assert a fact about THE BROKER. It now also requires that oldest bar to sit on the broker's **MEASURED** history floor (`history_limits.limits_for`), and **an unknown floor answers False — no measurement, no claim.** ⚠ **The label was the smaller half: the frontend STOPS PAGING on a hard edge**, so the claim was self-sealing — nothing would ever ask for the missing bars again. That asymmetry is the whole design of the fix: a wrong True is unrecoverable for the session, a wrong False costs one request that comes back empty. ⚠ **NT8/MT5 therefore never report a hard edge here**, because `limits_for` is python-only by design and a confident red line off no measurement would be pure invention. ⚠ **The flag is now RARELY true in practice and must not be deleted for it** — MEASURED against the live backend after the repair, a python drill-down reaching the real floor is refused by `BarSource.load`'s own floor guard BEFORE any fetch, so it returns `available: false` carrying the measured sentence, which the chart prints; the pager stops either way, since a page with no bars answers `more: false`. ✅ **Proven on the live backend: the same request that returned 721 bars with `hard_edge: true` now returns 11,864 with `hard_edge: false`.** ✅ 4 new tests (`tests/test_chart_drill_edge.py`), **2 watched RED** by removing the floor clause; the other 2 are labelled as pins on the new risk (an exact-equality floor comparison would refuse to call the true edge the edge, since history opens mid-session). **The standing lesson is one this app keeps meeting from new angles: a boundary you OBSERVE and a boundary that EXISTS are different claims, and code that infers the second from the first will report every gap in its own data as a fact about the world.** Earlier: 🔴 **`available` ON THE DRILL-DOWN CANDLES ENDPOINT WAS `bool(candles)` — THE SAME FACT AS "THE LIST IS EMPTY" — WHILE ITS OWN DOCSTRING CLAIMED IT MEANT THE FEED COULD NOT SERVE THE WINDOW.** Aaron reported the symptom from the price chart: a drill-down that *"says it is loading then stops and says 'no data here (feed offline, or none this far back?)'"* — a message that hedges because the payload genuinely could not tell the two apart. 🔴 **The distinction was destroyed one layer lower, in `_build_candles`, which caught every exception and returned `[]`** — so a dead MT5 agent, a refused window and a broker with no history that far back were one value by the time the router saw them. `_fetch_candles(...) -> (rows, error)` now carries the reason; `available` means **the feed could be ASKED**, and a new `feed_error` names the failure. ✅ **PROVEN against the live backend, not argued: asking for M1 in 2010 returns `available: false` with `HistoryFloorError: XAUUSD has no real 1-minute history before 2018-09-14 on VantageMarkets-Demo (measured, not assumed)`** — the whole answer, including the date, which is why the chart now prints the server's own sentence instead of mapping it to a phrase of its own. ⚠ **`_build_candles` survives as a thin wrapper** because the spec build genuinely does not need the reason — it degrades to an empty chart either way — and giving it one would be a second thing to keep in sync. **The standing lesson is the repo's own rule caught mid-flight: "never let no and cannot-ask be the same value" is not a property of one field, it is a property of every HOP — this one was destroyed in a `try/except` and then re-asserted, falsely, in a docstring two functions up, where it read like a contract.** 744 backend tests pass (one pre-existing failure). Earlier:  🟢 **THE PRICE CHART DRAWS A SESSION VWAP, AND THE ENGINE FOR IT HAD BEEN SITTING FINISHED THE WHOLE TIME — WHAT WAS MISSING WAS VOLUME.** Aaron's brother asked for it. `engines/vwap/` is Pine-parity green and was never consumed here, and the reason is that **a VWAP is the one layer on this chart that needs the bar's VOLUME, and nothing in the bar pipeline carried any**: the VPS agent dropped MT5's `tick_volume`, `cache._normalize` sliced to OHLC, `resample_up` aggregated four columns, and `ohlc_fetcher` sliced again. Volume now rides through all four (see `backtest/CLAUDE.md`), and `services/vwap_overlays.py` replays the canonical engine into ONE `ChartSpec.indicators` entry. ✅ **It cost no new panel concept** — a VWAP is a value per bar, which is what `ChartIndicator` already is, so it needed no template, no render effect and no menu row of its own; the same payoff `ob_overlays.py` recorded when it reused the generic `box`. ⚠ **`ChartIndicator` gained `defaultOn`, absent ⇒ true** — the ATR sub-pane has always opened ON and must keep doing so, while an analysis layer must not; and `indicatorsOn` is now RECONCILED rather than re-seeded, the rule `groupsOn` already followed. 🔴 **THE CONTRACT IS THE REFUSAL, AND IT IS WHY THIS IS NOT A THIN WRAPPER.** Given bars with no volume the arithmetic still runs — it degenerates into a plain running mean of hlc3 — and it draws a smooth, plausible, completely different line under the name VWAP that would disagree with the one on the TradingView chart it exists to reproduce. So: no `volume` key ⇒ no layer; `None`/NaN on **ANY** bar ⇒ no layer; every bar real with **some of them zero** ⇒ DRAW. **That last line is the whole distinction** — a dead session genuinely trades no ticks, so treating zero as unknown would drop the layer on any run containing a quiet hour, which reads as the feature not existing. ⚠ **All-or-nothing is not defensiveness**: a half-refetched cache would otherwise yield a line that is a true VWAP over part of the history and an hlc3 mean over the rest, with the seam invisible — worse than no line, because the wrong half is unmarked. 🔴 **VOLUME IS NO LONGER STRIPPED, AND THE STRIP IS WHY THE CHART SAID `Volume: n/a` (fixed 2026-08-06, Aaron reported it off the screen).** `chart_spec._strip_volume` dropped the column once the server-side layers had read it, on the drill-down path too, reasoning that the browser plots none. **klinecharts' candle tooltip has a `volume` row by default and renders a missing value as `n/a`** — so the saving was paid for with a permanent *no data* on the OHLC readout, for a number the pipeline had in hand. The function is deleted; `_build_candles` attaches whatever the feed gave it. ⚠ **ABSENT rather than zero when the feed supplied none** (a bar cache written before the pipeline carried volume, or a runner whose feed has none): `n/a` is the honest answer and a fabricated `0` reads as a dead session — the *no data ≠ cannot ask* rule reaching the one place that was solving it by deleting the data. ✅ **The cost was MEASURED before the call, not waved through: +16.0 bytes per candle, so the 155,807-candle spec goes 23.32 MB → 25.77 MB (~10.7%) and ~+20 ms of parse** — and the underlying cache is complete (186,366 rows, 2018-09-14 → 2026-08-06, **zero null volume**), so this is a real reading on every bar rather than a column of holes. ✅ Proven by rebuilding the spec through the live backend (200, 25.77 MB, 19.2 s, all 155,807 candles carrying volume, drill-down too) and then by the symptom itself in a real browser: the readout reads **`Volume: 5.221K`** where it read `n/a`. ⚠ **The two tests replacing the strip test were proven by MUTATION** — an unconditional `row["volume"] = 0.0` turns both red — because a fail-watch against HEAD would only have shown the deleted behaviour. ⚠ **The anchor is the trading day at 18:00 New York, DST-aware**, carried from the engine rather than re-stated; a different instrument would need its own. ✅ **13 new tests (`tests/test_vwap_overlays.py`), and because the module is new a fail-watch against HEAD would be vacuous — non-vacuity was established by MUTATION instead: neutering the refusal turns two red, and passing a constant volume turns three red, including the bar-for-bar check against the canonical engine.** 743 backend tests pass. ⚠ **One PRE-EXISTING failure is untouched and is not mine**: `test_python_runner.py::test_the_broker_profile_changes_the_spread` asserts PU Prime's spread is 0.33 while `fills.py` has said 0.32 since it was re-measured over 1,893,438 ticks earlier today — the test is the stale half. **The standing lesson is the Optimizations one inverted: this was not an unexercised feature, it was a FINISHED one with no consumer, and the thing blocking it was three layers away in a package nobody would think to check.** When a component is built, tested and unused, ask what it needs that it is not being given.

**Earlier the same day:** 🟢 **THE CHART SPEC CARRIES THE WHOLE RUN NOW, AND THE PER-WINDOW PAGER IT REPLACES IS DELETED.** Aaron asked for the price chart to load everything it can in the background so jumping to a date is seamless. **MEASURED end to end on run `997c14cc53bc` (XAUUSD M15, 2020-01-01 → 2026-08-06, 155,798 candles, 19,538 overlays): a six-year date jump went 90.3s → 2.0s.** The old design shipped the newest ~35k bars (`_capped_start` / `_CANDLE_CAP`) and the panel fetched every older window, each one replaying the structure and FVG engines server-side over a 2,000-bar warm-up (`_page_analysis`) — **~7.2s a page, and a deep jump took 14 of them.** ✅ **Building the entire run ONCE costs 17.8s and then serves in 0.004s for ever, so paging was 7x more expensive than not paging.** `_capped_start`, `_CANDLE_CAP`, `_PAGE_WARMUP_BARS`, `_page_analysis`, `_demote_page_internal`, `_overlay_anchor` and the `analysis=true` branch of `GET /runs/{id}/candles` are all gone; that endpoint is now the M1/M5 DRILL-DOWN only. 🔴 **The endpoint was ALSO parsing its own cache to re-serialise it, and that was the bigger multiple: `json.loads` → dict → FastAPI's `json.dumps` cost 0.26s of a 0.40s response.** `cached_chart_spec_bytes` serves the file's bytes — **0.40s → 0.004s, ~100x** — and the cache is written atomically (tmp + `os.replace`) with compact separators, because a spec that is now served AS BYTES makes a torn write a 200 carrying broken JSON rather than a rebuild. ⚠ **The 404 must still be decided by the DB, never by the cache being absent.** 🔴 **GZip was added, MEASURED and REMOVED rather than left in: on the 4 MB spec, identity 0.004s vs level-1 0.037s vs level-9 1.05s — a 9x LOSS at its cheapest setting**, because this app is one machine talking to itself over loopback at ~1 GB/s. `main.py` carries the measurement as a comment so it is not re-added by reasoning. ⚠ **My own first claim — "one line of gzip erases the payload problem" — was wrong, and the saving it appeared to buy was really the double-serialisation above.** 🔴 **`_build_candles` was calling `df.iterrows()`: 12.63s against 0.15s column-at-a-time on 155,776 bars, byte-identical output, 85x, paid on every cold chart build.** ✅ **The overlay caps were raised 1,200/1,500 → 20,000 and that fixed a silent data loss** — `_MAX_PER_GROUP` was dropping ~83% of a full-history run's 7,056 Swing Point Labels, OLDEST FIRST, so scrolling back far enough showed "no structure back there" with the toggle on. It is affordable now only because the PANEL creates overlays for the viewport rather than for the loaded history; an overlay in the spec is data, not a live klinecharts object. ⚠ **Compact `[t,o,h,l,c]` candles were measured and SKIPPED**: 14.43 MB → 8.97 MB but only 151ms → 95ms of browser parse, which is not worth a contract change across six readers. ✅ 8 new tests in `test_chart_spec_cache.py`; 🔴 **one of them was VACUOUS and passed against a plain `write_text`** — a non-atomic write leaves identical content and no `.tmp`, so an output-only assertion proves nothing; it spies on `os.replace` now, confirmed by mutation. **The standing lesson is that the expensive thing was not the one that looked expensive: the payload was 16.8 MB and the payload was never the problem — the costs were a cache re-serialising itself, a DataFrame walked row by row, and a design that paid a 7-second engine replay every time the reader scrolled somewhere it had already been told about.** Measure the seam before optimising the number you can see.

**Earlier the same day:** 🔴 **STOP CANCELLED WHATEVER JOB THE SHARED PROGRESS FILE NAMED, AND A RERUN SERVED THE PREVIOUS ATTEMPT'S CHART.** Aaron asked for an in-depth audit of the Backtests list and the Backtest detail page, then for the fixes — 27 findings, nine real defects, three destructive, and **not one of them produced an error.** 🔴 `stop_backtest_run` read its job id from `lab_progress.json`, ONE file shared by every runner, while `job_id == run_id` for every backtest this app starts — **measured on the live file, it held a stale `"j2"`** — so a Stop cancelled another platform's job (or nothing), swallowed the failure, marked THIS run cancelled, released its lock and left the real job running. 🔴 **Cancelling did not stop the poller either, so `_handle_complete` wrote `complete` back over `failed_cancelled`** — the Optimizations audit's own defect, still live here; the DB row is the single lock source and is now the single place a cancellation is read, marked BEFORE the runner is told and re-checked AFTER the results fetch, which is where a Stop actually lands. 🔴 **A rerun deleted two artefacts of six**: `chart_spec.json` is CACHED, so the Price tab drew the OLD run's candles and trades; `blocked_setups.json` / `missed_setups.json` are written only when non-empty, so the old refusals stayed on the chart; a rerun over a new window kept the old regime calendar; and a stale `engine_timeline.json` kept `sized` true on a run that no longer was. ⚠ **The converse is the rule worth carrying: an optional artefact's ABSENCE is what removes its chart layer, so `if blocked:` is not a write guard, it is a way of publishing last time's data.** 🔴 **A ten-minute WALL CLOCK killed healthy heartbeating jobs and wrote "No heartbeat for 0s"** — a false diagnosis pointing at the agent; latent only because the longest run in this lab is 275s. A stall and an overrun are different diagnoses and now have different constants and different messages. ✅ **Efficiency, MEASURED rather than asserted: the runs list was N+1 (one sqlite connection per row) — 12 connections / 23.72 ms → 1 / 2.28 ms with byte-identical output**, and `GET /backtests/runs?source_run_id=` lets the run page count its own iterations in **0.002 KB instead of 20.6 KB**. `_JOBS` in the python runner was never evicted (**a 115-trade run's payload is 4.14 MB, retained for the life of the process**); it now sheds the payload and KEEPS the status, because deleting the entry turns *finished an hour ago* into *failed* for a late poller. 🔴 **`cost_layers` could not be sent as `null`**, so NT8/MT5 runs stored `[]` — *deliberately charged nothing* — and the page called a tester that charged commission and slippage frictionless; ⚠ an ABSENT key still means `[]` so a python run cannot fall into the legacy branch by omission, and only an EXPLICIT null writes NULL. ⚠ **Two audit findings were WRONG and are recorded as wrong**: `compute_regime_breakdown` per GET and `/repriced`'s four curve walks were flagged as costs and measure **20.1 ms and 19.3 ms for the whole endpoint** — *a cost guessed at is the same error as a number guessed at.* ✅ **21 new tests (719 green), 17 of them WATCHED RED against HEAD**; the four that passed there are kept and labelled in their own docstrings as pinning the half of a rule that was already right. 🔴 **DRIVING the fixes against a real running backtest — rather than reading them — found a further defect: `GET /backtests/running-job` named `nt8` and `mt5` and never passed `python`, so a python run reported its own platform FREE for its entire life.** The gate was never affected (a second run really was refused `409`, proven live), but every control the UI gates on that response stayed enabled and could only produce an error toast. The response is DERIVED from the scope map now. ⚠ **It is the `entry_ms` / `favorable` trap from the OPPOSITE direction — not a field the model failed to DECLARE, but a declared field the constructor failed to ASSIGN, whose default is the most reassuring answer available.** ✅ **Stop was then pressed against a real full-history replay: `job_stopped: true`, cancelled in 287 ms, lock released, and still `failed_cancelled` 120 s later; and a rerun took a run dir from 6 artefacts to 0 and rebuilt 5.** Full detail: *The Backtests list and the Backtest detail page — the 2026-08-06 audit*. **The standing lesson is about a shared mutable file used as an identifier: `lab_progress.json` exists to drive one progress bar, and the moment something READ an id back out of it, an unrelated platform's job became the target of this run's Stop. The run id was in hand the whole time.** Earlier: 2026-08-05 — 🔴 **A STRESS TEST'S CHILD RUNS WERE MEASURED ON A FREE BOOK WHILE THEIR PARENT CHARGED SPREAD AND SWAP, AND SENSITIVITY REPORTED THE COST GAP AS THE PARAMETER'S FRAGILITY.** Aaron asked for a full audit of the stress test feature. **The frame is one query: `SELECT count(*) FROM stress_tests` returned 1, and that row was written 2026-07-27 — three days BEFORE the accuracy pass that replaced the shuffle series, the drawdown basis, the sensitivity metric and the walk-forward floor.** Nothing had re-scored it, so a confident **D** sat on the list for a week; re-scored through the live backend it is **ungraded**, both probabilities NULL, sensitivity 0.858 → 0.205. 🔴 **The load-bearing defect: `run_walk_forward_task` and `run_sensitivity_task` built a spec with the window, the params and the two legacy cost fields — and no `cost_layers`, no `broker_profile`, no `sizing_mode`.** `python_runner._cost_profile` reads exactly those, so every child ran frictionless, and since the sensitivity score is `|child_pf − baseline_pf| / baseline_pf` against a CHARGED baseline, **the charge showed up as the parameter's doing on every shift.** ✅ **Proven on real data, not by reading the diff: every child of a charged 161-trade baseline now carries `["spread","swap"] / vantage_demo / consistent`.** `child_measurement_fields()` is the one seam. **This is the third launcher in this app carrying the window but not the physics** — the Run modal's costs, the Optimize modal's params, the tune page's `cost_layers` — so the rule is now general: **anything creating a child run for COMPARISON must carry everything that decides what a run is measured on.** 🔴 **"Never ran" and "ran and crashed" were the SAME VALUE.** A crashed phase left its summary NULL and grading reads NULL as not-run — explicitly unpenalised, with a caveat saying so — **so a walk-forward whose every backtest failed cost the test nothing and could be handed an A carrying the words "walk-forward not run".** Both tasks return `(ok, err)`, `phase_failures` names the death, and `compute_grade` takes `wf_failed=`/`sens_failed=`. ⚠ **`phases_requested` is written when the ROW IS INSERTED, and that is not a detail: written at the end it is absent for the test's whole life, and a task killed mid-flight leaves no record of what was ASKED for.** Demonstrated during this audit — the backend reloaded under a live test and left exactly that hole. 🔴 **`prob_pass_eval` was computed against the DOLLAR limit while `prob_breach` had moved to percent**, so on a compounding run the two contradicted each other; measured on a compounding fixture at a 60% limit, old = 0.0% breach / **31.2%** pass, new = 0.0% / **100%**. 🔴 **Cancel did not cancel** (it marked the row and left the children running) and 🔴 **delete left every file behind** — which is how `reports/lab` reached **191 directories against 84 live runs**; a real delete now takes 216 → 192, measured. 🔴 **`asyncio.create_task` had no strong reference**, so a long-awaiting stress test was collectable mid-flight and would leave its row `running` for ever. 🔴 **`update_stress_test_mc` hardcoded `complete`** even with phases to come, releasing the market lock in the gap and leaving a crash there permanently invisible to `reset_stale_stress_tests`. ⚠ **Sensitivity no longer perturbs a param that is UNREACHABLE in this run** (behind a `show_if` switch it has off — 3 of 17 on the measured baseline, 12 wasted backtests) and it STORES its coverage, because a silent skip reads as coverage that never happened. ⚠ **`shifted_value` REFUSES a shift past a param's own bound rather than clamping** — a clamped shift is a duplicate of the bound scored as though it were the ±25% case. ✅ **27 new tests, 650 green**, and an idempotent `GRADE_ENGINE = 3` migration that re-derives every stored test under today's rules — **re-deriving from stored inputs only, never re-running a backtest**, so a row whose children are gone is left alone rather than handed a number nothing measured. Full detail: *Stress tests — the 2026-08-05 audit*. **The standing lesson is the Optimizations one at one remove: that page had never been run, which is at least legible. This one had been run ONCE and then its engine was replaced — so it carried the evidence of a completed end-to-end drive, and every bit of that evidence described code that no longer existed. Ask not only how many times a subsystem has executed, but when, and against what.** Earlier the same day: 🟢 **TWO SCHEDULED JOBS LEFT THE BOTS PAGE BECAUSE THEY NEVER DID ANYTHING, AND TWO THAT DO WERE NEVER LISTED.** Aaron asked what `SYS_PNLTRACKER` and `SYS_REPORTER` were for and whether he still needed them; the answer was that **neither could have done anything if switched on** — both carried an empty bot registry inherited from the four bots deleted 2026-06-22 (`algos/CLAUDE.md`). This page had been rendering them as **DISABLED** with a deliberate comment saying a disabled task is not a failed one, which was true and beside the point: **a job that is switched off and a job that does nothing look identical from here, and only one of them is a feature.** Both deleted, and `SYS_DEADMAN` + `SYS_LOGBACKUP` — real, enabled, and never in `_SCHEDULED_JOBS` — take their place, so the three jobs listed are now the three that run. ⚠ **`_SYS_TASK_BY_JOB` is DERIVED from `_SYS_DISPLAY_NAMES`**, because the loop restated the name→task map and a job listed under a name that map missed resolved to a permanent `UNKNOWN` — a job the page cannot see, rendered as one it never asked about. 🔴 **Seven fields came off `BotStatus` with them, and leaving them would have been the real defect**: `daily_pnl`, `daily_pnl_pct`, `weekly_pnl`, `weekly_pnl_pct`, `peak_balance`, `trades_today` and the three cap fields (`daily_goal_pct` / `daily_cap_pct` / `weekly_cap_pct`) had **no writer left**, so the Monitor tab's four stat tiles and three cap chips were drawing an em-dash or nothing — which reads as *quiet*, not as *nothing measures this*. **This repo's own rule, and the third time it has been applied on this page: a fabricated value and a measured one must never look alike** (`mt5_link`, `grid_sensitivity_score`, now this). `balance`, `total_pnl_pct` and `uptime` survive because `algos/live/runner.py` writes them, and they are in the row above. ⚠ **The caps were the dangerous half: they rendered as PROTECTION.** They were the P&L tracker's Telegram ALERT levels — nothing in them could refuse a trade — so the page showed a daily cap the bot would have traded straight through. `_BOT_THRESHOLDS`, `_load_thresholds_json` and `_get_thresholds` are gone, along with `algos/shared/thresholds.json`. **A real cap belongs in the bot's own loop.** ✅ 650 backend tests green, frontend typechecks and builds. **The standing lesson is the Optimizations one from a different direction: there, a feature nobody had RUN was 24 defects waiting; here, a feature nobody had run was wearing the word DISABLED, which is what kept anyone from checking.** Before switching a dormant job on, read what it would do against today's registries — not what its name says it does. Earlier the same day: 🟢 **THE TEST SUITE'S VPS INTERLOCK NOW COVERS SSH, AND CLOSING THAT GAP FOUND THE GUARD ITSELF WAS SWALLOWABLE.** The HTTP half landed yesterday with its own limitation written down — *"a green suite here is not proof that nothing shells out to the box"* — and this closes it. **There is no funnel to patch on the SSH side**: `routers/bots.py::_ssh` is one, `services/agent_supervisor.py` shells out three more times on its own, and the next module to need the VPS will shell out again — so the guard sits on **`subprocess.run`/`Popen` themselves and decides per-argv**, which is the only placement a NEW call site cannot walk around. ⚠ **It classifies rather than banning**: refuse an `ssh`/`scp`/`sftp` program, or any argv containing `cfg.SSH_ALIAS` — the second clause catching `restart_tunnel`'s opening `pkill -f "ssh -N.*forexvps"`, whose program is not ssh and **which would kill the developer's own tunnel from inside a unit test**. `git` and the smart-money stage scripts still run for real; a blanket ban on `subprocess` would be easier to write and would test nothing about the VPS. 🔴 **The finding is that an `AssertionError` guard is INERT on this path, and it was inert on the HTTP side too.** Every probe here catches `Exception` and reads the failure as *the box is down* — `vps_reachable`, `_agent_ok`, `schtasks_run`, six bare `except Exception: pass` blocks in `_build_health` — so the guard would be swallowed by precisely the code it polices: call still made, caller reports "unreachable", suite green. ✅ **Measured rather than argued — with one stub removed from `test_system_health.py`, an `Exception`-based guard left 11 of 12 tests PASSING while every one of them opened a real ssh connection; the `BaseException` version fails 6 by name and prints the argv.** So `LiveVpsCall` derives from `BaseException`, and a test pins that it is not an `Exception` so a future tidy-up fails there instead of quietly disarming the suite. ⚠ **An autouse interlock's failure mode is SILENCE — never firing and never being installed look identical from a green run** — so `tests/test_vps_interlock.py` (13) drives it directly at the four real call sites rather than trusting the fixture list. 530 backend tests green. **The standing lesson is this repo's own probe rule arriving in the test harness: a check that cannot fail where the failure happens is not a check.** Earlier the same day: **`GET /backtests/runs/{id}` TAKES `?timeline=false`, AND THE ONE RULE IS THAT ITS DEFAULT MUST STAY `true`.** `regime_timeline` is the single biggest slice of a run detail — **measured: 96 KB of 137 KB on a 165-trade run, and the whole response drops to 49 KB without it** — and it is the SAME full calendar for every run over one window. The tuning workbench overlays N runs and bands off exactly one copy, so it fetches the baseline whole and the iterations slim. ⚠ **`[]` is what the flag returns, which is INDISTINGUISHABLE from a run that genuinely has no timeline** — so it is only ever safe for a caller that already holds the calendar it needs and is asking for the run's other fields. Do not default it to False, and do not let a slimmed response share a cache key with a full one; both traps are named at the call site and in `frontend/CLAUDE.md` → *The Tuning workbench*. 4 new tests in `tests/test_backtests.py`, one of which asserts that slimming changes **nothing but that field** — the point of the flag is a smaller payload, not a different run, and a caller reading a slimmed response must never get a different answer from one reading the full one. **The finding this served is on the frontend and is the interesting half: the tune page was launching every iteration WITHOUT the baseline's `cost_layers`/`broker_profile`/`sizing_mode`, so a child of a charged run was measured on a free book and put in a table beside its own parent** — proven with three real python runs against this backend (PF 1.499 charged vs 1.581 free on identical params and an identical 17 trades). The retry path has carried those fields off the row deliberately since they existed; the tune path was the one run-launching caller that did not. 500 tests green. Earlier the same day: 🟢 **THE REST OF THE BOTS AUDIT LANDED, AND THE BIGGEST FIX IS THAT THERE IS NOW ONE BOT REGISTRY INSTEAD OF NINE.** `routers/bots.py` held nine parallel dicts keyed three different ways — task name, bot key, state-file section — so registering a bot meant editing all nine, and **missing one produced a confident wrong answer rather than an error**: no `_TASK_ACCT_TYPE` entry rendered a **LIVE bot as demo** (losing the amber tinting, the "N of these are LIVE accounts" warning on every fleet dialog, and its place in the demo/live filter, all silently), and no `_SUPPRESS_KEYS` entry made **"Stop all N bots" skip that bot and report success**, because `_stop_procs` iterated the crash-alert map while the count on the button came from the registry the loop was not using. It is one `BotReg` dataclass per bot now, and every map is DERIVED. ⚠ **`account_type` deliberately has NO DEFAULT** — forgetting it is a TypeError at import, which is loud and free, where `.get(task, "demo")` defaulted in the dangerous direction. The rest default off the bot key (that is genuinely how `algos/live/` names things) and each can be overridden. ⚠ **Add a `BotReg`; never edit a derived map.** Eight more fixes in the same pass. 🔴 **`GET /{bot}/version` took 8.5 seconds and ~5s of it was waste** — it called the full two-command fleet snapshot (every python process, every scheduled task, every bot's state file) to read ONE `source_hash` string, and the Configure tab's fleet strip fires one per bot, so the cost multiplied by the fleet. The bot's own `bot_state.json` now rides the SAME round trip as the git facts: **measured 8.5s → ~3.7s against the live VPS, with `running_hash` still correct.** 🔴 **That same block named `state_mpc_sos_fade` outright**, so any second bot got a blank `running_hash` — which reads as "the live process agrees with the deployment record" and makes the *restart pending* warning permanently impossible to fire, i.e. the fleet strip would report a confident **0 restart pending** across a fleet it cannot see. 🔴 **`params_drift` was blind in both directions**: `deployed.get(k, current) != current` over the CURRENT keys only, so a setting **added** to config.json since the promote defaulted to its own value and compared equal, and a setting **removed** was never looked at. Now a union diff through a sentinel — because a param whose value is legitimately `None` must not read as absent. 🔴 **Whether a promote worked was read off its PROSE** (`"pinned" in out`, `"dry run" in out`) while `promote.py` has always returned a real exit code. Two silent failures: reword one `print` and the verdict flips, and a FAILURE whose message happens to contain the word reads as a success — **and a success also restarts the bot.** It reads `if errorlevel 1` now, never `echo %errorlevel%`, which cmd expands at PARSE time and would always answer 0 — a trap that looks like a working exit-code check. ⚠ **An unreported result is a THIRD answer**: false, no restart, no alert, with the doubt spelled out in the output rather than resolved in silence. 🔴 **`get_snapshot` read `task_status == "Running" or running_in_procs` — the exact opposite of the comment directly above it** saying the process list is authoritative. The scheduled task answers a different question entirely: a bot boots through `startup_coordinator.py`, which EXITS once it has spawned the bot, so the task is "Running" only while the launcher runs and "Ready" for the bot's whole life. Process list only now. 🔴 **`PATCH /{bot}/config`, `PATCH /{bot}/caps` and `GET /{bot}/config` are DELETED** (`git show 407d716^`). All three had NO consumer — their frontend hooks existed and nothing rendered them — and two restarted a **live trading bot** to do it: `/config` wrote ARBITRARY sections including `strategy` and went straight around `bot_params.RUNTIME_EDITABLE`, **the allowlist whose entire job is to say which lever may move under a running bot** (a backdoor around a safety rule is worse than no rule, because the rule is what everybody reads), and `/caps` did the same restart to write `thresholds.json` for `SYS_PNLTRACKER`, **a task that is disabled**, plus a loop over `_CAP_CONFIG_FIELDS`, which is empty by design. `/params` (read) and `/runtime` (write the reloadable set, **no restart**) are the maintained pair; editing thresholds by hand is the honest cost of a job nobody has switched on. 🔴 **Removing or demoting the LAST admin is refused (409)**, and `role` is validated against `("admin","readonly")` — a typo like `"Admin"` is not a new role, it is a user with NO permissions, because `ROLE_COMMANDS` misses. ⚠ **The Telegram bot's `ADMIN_CHAT` fallback does NOT cover this** — checked rather than assumed: it fires only when users.json is MISSING or unparseable, so a file listing everyone as `readonly` is read as written and the primary admin loses `/stop` too. ✅ **The users read-modify-write now holds a lock across the read AND the write** (`_USERS_LOCK`), closing the gap the 2026-08-04 entry below named as deliberately unfixed. ⚠ **Its test had to be fixed before it proved anything** — the fake read snapshotted the file AFTER its delay, so every thread got the latest state and **the test passed with the lock removed**; snapshotting at read time makes it fail without the lock, which is the only version worth keeping. **A concurrency test that has not been watched to fail is a comment.** 462 backend tests green (49 new across `test_bot_registry.py`, `test_bot_promote.py` and the three files below). ✅ **And the last one closes the loop on all of it: every route was keyed on the DISPLAY NAME.** `_resolve_bot` now takes a **bot key or** a display name, key first, and `BotStatus` carries `key`. A name is a label chosen for a human and is therefore the one field somebody eventually changes — renaming "MPC SOS Fade" would have broken every bookmark, the Configure tab's `?bot=` selection and any script anyone had written, **while the bot itself was untouched**. The key already identifies the process on the VPS (`runner.py --bot <key>`); it simply was not reachable from the API. ⚠ **Key BEFORE name, never the reverse** — if a future bot's display name equalled another bot's key, name-first would silently route one bot's Stop to the other, and no test can rule that out because the two namespaces are free; the ORDER is the guarantee. ⚠ **Display names keep working deliberately** (the frontend renders off `BotStatus.name` and this is not worth a flag day); the rule for new code is "pass the key". ✅ **Verified in a real browser against a mocked 4-bot fleet including a LIVE one**: the URL carries `?bot=orb_live`, **1 promote button with 4 bots registered**, the panel names *ORB* and never leaks `orb_live`, a key deep-link survives a reload and a Monitor round trip, and stopping the live row shows **"Stop ORB?"** while calling **`orb_live/stop`**. **The standing lesson from this half is about registries rather than labels: N parallel maps keyed on N different things is not duplication, it is N chances to answer confidently and wrongly — and every wrong answer here pointed the safe-looking way (demo not live, success not skipped, agrees not pending). The name-keyed routes are the same disease in its mildest form: an identifier that is also a label is a rename away from addressing nothing.** Earlier the same day: 🔴 **THE TEST SUITE COULD KILL THE LIVE TRADING BOT, AND THE ONLY THING STOPPING IT WAS A FLAG SOMEBODY HAD TO REMEMBER.** `tests/test_integration.py` Case 6 kills the NT8 agent on purpose to prove a run times out, and it did it with **`taskkill /f /im python.exe`** — every python process on the VPS: both backtest agents, the Telegram bot, and **the live trading bot**. That was harmless when it was written (no live bot existed) and stopped being harmless on 2026-07-31; the identical blanket kill is what left the bot dead for three days in July. ⚠ **Nothing enforced the guard.** The module's docstring said to select it explicitly from the day it was written, `pytestmark = pytest.mark.integration` was registered but never deselected, and `command-center/CLAUDE.md`'s standing advice was to type `--ignore=tests/test_integration.py` **every single time** — so the safety of a live trading account rested on a person's memory, forever, with no failure signal until it cost a position. **An interlock you have to remember is not an interlock.** ✅ **Fixed at both levels, and verified in both directions rather than assumed:** `pytest.ini` gained `-m "not integration"` (**measured: 432 collected, 5 deselected on a bare `pytest tests/`; `pytest tests/test_integration.py -m integration` still collects all 5**, because a command-line `-m` replaces the default), and the kill itself is now a `wmic` match scoped on **both** `name='python.exe'` and `nt8_agent.py`. ⚠ **Both halves of that match are load-bearing and neither is obvious** — without the process-name clause it matches the `cmd.exe`/`wmic.exe` running the command, whose own commandline contains the pattern; without the script name it is the blanket kill again. Same two-clause rule as `routers/bots.py::_kill_bot`, which the 2026-08-04 audit found four routes had each reinvented wrongly. **The standing lesson is not about this test: a dangerous default guarded by documentation is an unguarded dangerous default.** The docs were correct, complete, and prominently placed the whole time — and the interlock was one line of config nobody had written. **When the cost of forgetting is a live position, make the machine refuse rather than the file explain.** Earlier: 2026-08-04 — 🔴 **AN AUDIT OF THE WHOLE BOTS PAGE FOUND THREE WAYS IT WAS CONFIDENTLY WRONG, AND THE FIRST ONE HAD BEEN DECLARED FIXED THE DAY BEFORE.** (1) 🔴 **The per-bot Stop and Restart buttons used an UNSCOPED kill.** `_kill_bot` matches `name='python.exe' AND commandline like '%--bot <key>%'`, and both halves are the safety property — but four call sites (per-bot stop, per-bot restart, the config-deploy restart and the caps restart) built their own `wmic process where "commandline like '%<key>%'" call terminate` with NEITHER. Without the process-name clause it matches the `cmd.exe` and `wmic.exe` hosting the very command being run — **the key is in the query, so the query is in their commandline** — i.e. the kill can terminate itself; without the `--bot ` prefix it matches `promote.py --bot <key>` and `startup_coordinator.py --bot <key>`, the deploy and the launcher. The fleet Stop was fixed on 2026-08-03 and **that commit's own message asserts "the per-bot routes already did this correctly"** — they did not, and the routes it skipped are the ones on the row a human actually clicks. All four now call `_kill_bot`. ⚠ **The guard against a fifth is a SOURCE test, not a behavioural one** (`tests/test_bot_kill_scope.py` walks the AST and asserts only `_kill_bot` builds a `call terminate` string): a behavioural test only covers routes somebody remembered to write one for, and the defect lived in the routes nobody thought to check. Same class as `taskkill /f /im python.exe`, which killed the live bot for three days in July. (2) 🔴 **A DEAD SSH RENDERED AS "EVERY BOT IS STOPPED".** `_ssh` discarded the return code and stderr and handed back stdout — and **measured: a broken ssh exits 255 with empty stdout and raises nothing**, so `get_snapshot` got empty sections and reported every bot STOPPED with a null balance, no error, no banner, nothing on the page able to say the question was never answered. `wmic … get commandline` prints nothing when no bot is running, so *"nothing is running"* and *"nobody answered"* arrived as the SAME VALUE. `_ssh` now raises **`VpsUnreachable`** and the endpoint returns a named 502. ⚠ **Only exit 255 with EMPTY stdout is read as a connection failure** — OpenSSH reserves 255 for its own errors, while a remote command that merely fails reports its own code (`type` on a missing file exits 1, a `call terminate` matching nothing likewise), and those are ORDINARY here: half the commands in this module end in `2>nul` precisely because failing is the normal case. Raising on any non-zero would break every one of them. **This is the repo's own rule arriving in the backend for the first time** — the live bot read a dead MT5 link as a quiet market for the same reason, one layer down and pointed the other way. (3) 🔴 **ADDING ONE TELEGRAM USER COULD DELETE EVERY OTHER ONE.** Every write to `users.json` is a read-modify-write of the WHOLE file, so a failed read is not an inconvenience, it is a delete — and `_read_users_vps` answered `{}` for a missing file, an unreadable one, a locked one, a corrupt one and a dead SSH alike. `add_user` then wrote `{"users": {the one new user}}`. Remove and role-change survived by accident (an empty dict 404s before it can write); **add is the destructive one, and it is what somebody runs while onboarding a person — the moment nobody is looking at the existing list.** The read now asks Python on the far end (`type x 2>nul` cannot express *missing* vs *unreadable*, which is the only distinction that matters), the ABSENT case is the sole one that answers `{}`, everything else raises `UsersFileUnreadable` → 502, the write takes a **`users.json.bak`** first, and the write CONFIRMS itself with a marker — a remote Python traceback exits non-zero with empty stdout, which `_ssh` correctly does not read as a connection failure, so without a marker a failed write reports success. ⚠ **`list_users` now 502s rather than returning `[]`**: an empty list reads as *nobody has access*, which is a different fact and would send somebody to re-add users that are already there. ⚠ **Still not fixed and deliberately not attempted: there is no LOCK on the read-modify-write**, so two concurrent edits can still lose one. That is a real gap and a much smaller one than the destructive case — say so rather than implying the file is now safe under concurrency. 462 backend tests green (31 new across `test_bot_kill_scope.py` / `test_bot_ssh_failure.py` / `test_bot_users.py`). **The standing lesson is where these three were found: all of them sat behind a control that LOOKED fine and had no test at all — the audit was prompted by a UI scalability question, and every finding was in the layer underneath it.** Earlier the same day: **`BotStatus.mt5_link` — because `balance: None` is not a diagnosis.** A live bot lost its MT5 terminal (MetaTrader auto-updated and restarted itself under it) and went 50 minutes without a bar, and the ONLY thing that changed anywhere in this backend's output was the balance going null — which is also what a bot that has not reported yet looks like. `routers/bots.get_snapshot` now passes the bot's own `mt5_link` stamp through. ⚠ **It is `Optional[bool]` and `None` means UNASKED** (a stopped bot, or one predating the field), so the frontend checks `=== false`, never falsy — the same contract `mt5_connected` has carried since 2026-08-02, and for the same reason: rendering an unanswered question as a failure invents a measurement. ⚠ **It is forced to `None` when the bot is not RUNNING**, since a stopped bot's last stamp describes a process that no longer exists. The detection itself lives in `algos/live/runner.py` (`probe_link` / `_recover_link`) and is written up in `algos/CLAUDE.md`; nothing in this backend can diagnose it, which is the point — only the bot's own process can ask its terminal a question. Same pass: the Bots row in the table below claimed **no bots were registered** while `mpc_sos_fade_demo` had been live since 2026-07-31, and now names `GET /{bot}/version` (VPS deployment record + git HEAD + the LIVE process's `source_hash`, so the page reports what is RUNNING rather than what `config.json` intends) and `POST /{bot}/promote[/preview]`. ⚠ **Per-bot stop is a TARGETED `wmic … call terminate` matched on the bot key**, never `taskkill /f /im python.exe` — the blanket kill takes out both backtest agents and the Telegram bot with it, and it is what killed the live bot for three days in July. Earlier: **Last reviewed:** 2026-08-03 — 🔴 **`GET /runs/{id}/repriced` NEVER READ THE RUN'S OWN `cost_layers`, so a layer the run already charged could be charged a SECOND time.** The stored trades were measured with that cost baked in, and re-pricing it on top bills it twice — producing a plausible number rather than an error, which is the worst shape a defect can take here. Latent rather than live (all 81 stored runs are `cost_layers` NULL or `[]`, so nothing has ever double-charged), and live the moment anyone launches a priced run. Fixed at the seam: `already` is read off the run, an already-charged layer is dropped from `layers`, reported in the new **`already_charged`**, and priced at **0.0** in `layer_cost_r` — because the honest answer to "what does turning this on cost from here" is nothing, and quoting its standalone price is what invites the double charge. ⚠ **`already_charged` is computed off the RUN, not off what the caller ticked**, so the UI can render those rows as already-on rather than offering a checkbox that silently does nothing. ⚠ **It must go through `_json_list`** — `cost_layers` is stored as raw JSON TEXT, so `set(row["cost_layers"])` iterates its CHARACTERS and every real layer name fails to match while `'s'`, `'p'`, `'r'`… all appear charged; pinned by its own test. ⚠ **There is no way to charge a layer OFF from here** and there should not be: the stored trades were measured with it, so removing it is a re-run. ✅ **Audited end to end rather than reasoned about: all 81 python runs re-price through the live endpoint without error, and the arithmetic was checked layer-by-layer against real charged replays over the full 155,453-bar window — spread 0.0000R, commission 0.0000R, swap −0.0376R**, the last isolated to a SINGLE trade held 2022-12-28 → 2023-01-03 where the re-price books a New Year night no bar existed to charge. That is the documented holiday supersede, not a new defect. 6 new tests in `tests/test_run_repricing.py` (19 total). Earlier the same day: **`services/ob_overlays.py` puts ORDER BLOCKS on the price chart** (Aaron's brother's ask). The canonical `engines/order_blocks/` engine replayed server-side, one `box` overlay per block that was LIVE on a trade-entry / blocked / missed bar — the fair-value-gap layer with one engine swapped, down to the anchor rule. MEASURED on run `432aff31f374`: **2,567 blocks created over the window, 579 drawn**, beside the gap layer's 661, so the two together sit at a readable ~1,240 boxes instead of ~3,200. ⚠ **The BOX GEOMETRY is the one real difference, and it is the thing that would look plausible if it were wrong**: an order block is a fixed **30-bar stub** from its anchor candle, stretched to the live bar only while price is back within one block-height, where a gap box tracks the live bar — so a block's box legitimately ends long BEFORE the block dies, and can end AFTER the bar it died on. ⚠ **No settings fork to warn about, unlike the gaps** — the strategy files dropped order blocks in 2026-07, so `mpc_assistant.pine` is the only source; the flip side is worth saying out loud, that **a drawn block never explains an entry, because `mpc_sos_fade` reads none**. ⚠ **`tests/test_ob_overlays.py` (18) proves the EMITTER and deliberately claims no more** — the gap layer's box-vs-Pine-array cross-check could not be run here, because all three OB exports on disk predate the 2026-07-31 re-port (six slots, no `cfg_ob_*`) and `compare_ob.py` refuses them outright; the ENGINE's parity is proven separately on real 15m/5m exports, and the missing half is named rather than quietly skipped. Same pass: **`_page_analysis` now builds its ANCHORS over the warm-up as well as the page** and slices for content — a zone can outlive the bars its box covers, so anchoring off the page alone would drop one that a trade just off the left edge is the whole reason for (a real page's block/miss counts are unchanged at 21 / 45). 388 tests green (18 new). Earlier: ⚠ **`layer_cost_r` carries EVERY re-priceable layer's own price, ticked or not, and it is in R rather than dollars for a reason that would look like a bug if it were ignored:** charging a layer changes the balance and therefore every later position's SIZE, so a layer's DOLLAR cost depends on which other layers are on. Three per-layer dollar figures would not sum to the dollar total shown beneath them, and the panel would read as broken while every number in it was correct. In R the size cancels and they add up exactly (pinned in `tests/test_run_repricing.py`). Same day: **`GET /runs/{id}/repriced` charges costs onto a completed run without replaying it**, so the detail page can switch them on and off (Aaron's ask, the day after the Run modal got them). Post-processing off the stored equity curve, the same shape as `/runs/{id}/news` — and the difference between the two is the interesting part: the news filter REMOVES trades the run already made, while this changes what each trade was worth. That is only possible because each re-priceable cost is, in R, independent of position size (`backtest/reprice.py`, proven against real replays; on the live 161-trade run `75ccc776d10c` it reproduces a real charged replay to **37¢ on $16.3M**). ⚠ **A layer that cannot be re-priced is REPORTED in `needs_rerun`, never dropped and never a 400** — `bid_ask_fills` changes which setups fill and `slippage` depends on which exits were market orders; the caller asked a reasonable question and the honest answer is "that one needs a re-run", while silently ignoring it would show a spread-only number under a bid/ask label. ⚠ **`is_exact` false is captioned, not hidden**, for two distinct causes: a `swap` layer (~0.3%, its real charge depends on which bars existed) and `derived_basis` (~0.02%, a run predating the stored per-trade `r`/`risk_usd`). ⚠ **The starting balance is RECOVERED from the curve's first point** (`equity - profit`), because there is no deposit column and defaulting to $10k would rescale every dollar on the page while leaving R correct — the hardest kind of wrong to notice. ⚠ **The broker defaults to the one the RUN was made against**, since the two profiles differ by 50%. 367 tests green (11 new in `tests/test_run_repricing.py`). Earlier: 2026-08-02 — 🔴 **`python_runner` was charging neither the SPREAD nor the OVERNIGHT SWAP, the two costs the lab already knew.** The 2026-08-01 fix wired commission and slippage through; these two were never collected at all, so bar mode stayed frictionless in a way that fix did not reach. A request now carries **`cost_layers`** (which costs to charge) + **`broker_profile`** (whose measured facts to charge them from) — `COST_LAYERS` is the roster, `backtest.fills.PROFILES` the source — and **every layer is OFF by default**, Aaron's explicit call, so a bare run stays comparable to the TradingView Strategy Tester. Swap needed no new code: the charge path has always run in bar mode and was dead only because `_cost_profile` passed `swap=None`. ⚠ **`cost_layers` absent (`None`) is NOT `[]`** — `None` = a row predating the layers, which must keep the OLD contract; `[]` = charge nothing. Collapsing them would re-price all 80 stored runs the first time one was retried, so `routers/backtests._json_list` preserves the distinction and the API models it as `Optional[list[str]]`. ⚠ **`spread` and `swap` are never accepted from the request** — they are MEASUREMENTS, and a field the operator can type is a field that can disagree with the broker; `GET /backtests/broker-profiles` exists so the Run modal never retypes one. The `$0.33` this repo had recorded is **PU Prime's**, and using it for a Vantage backtest overstated the cost by 50% (Vantage measures **$0.22** over 1,494,459 cached ticks). ⚠ **`bid_ask_fills` REPLACES the spread cost rather than adding to it**, and it is the only layer that can change which trades exist. ⚠ **Sweeps and stacks do not write the columns yet**, so they land in the legacy branch and stay frictionless — correct today, wire them before anyone expects a priced stack. Both `_cost_profile` call sites inherit it, so the optimizer cannot rank combos on one cost model and hand the winner to a run on another. 356 tests green (7 new in `tests/test_python_runner.py`). Full rules: *Layered costs* below. Earlier the same day: 🔴 **everything the price chart draws except the TRADES was clipped to the SHIPPED candle window, so scrolling back far enough emptied the chart.** `chart_spec._capped_start` ships the newest ~17 months of a 6.5-year run and the panel pages the rest in on scroll-left — but `overlays` (structure + FVG), `blocks` and `misses` were only ever built over those shipped candles, so past that boundary every layer the reader had switched on drew nothing while its toggle still read ON. Indistinguishable from the panel forgetting the setting, and reported as exactly that. `GET /runs/{id}/candles?analysis=true` → **`chart_spec._page_analysis`** now serves each paged window's own analysis, built with the SAME functions `build_chart_spec` uses. ⚠ **The engines are streaming state machines, so a page is replayed with `_PAGE_WARMUP_BARS` (2,000) of older bars in front of it** and only overlays reaching into the window are returned — a cold replay would open every page with no swings and no live gaps, i.e. a seam that reads as "the layer stopped working" one page further back. ⚠ **A page's internal structure is demoted to Historic** (`_demote_page_internal`): `build_market_structure_overlays` calls the newest leg in whatever it replayed "current", and only the shipped window holds the leg the run actually ended in — several pages each claiming a current leg would make that toggle describe something that does not exist. Analysis is best-effort and wrapped: a failure still delivers the page's bars. Measured on run `211384ddbea4`: one page = 11,259 candles + 1,309 overlays + 21 blocks + 45 misses, ~+2s and ~+230 KB over the bare page. 337 tests green (7 new in `tests/test_chart_page_analysis.py`). **The standing lesson, and it is not the label-on-a-screen one: a per-window computation behind a view the reader can EXTEND is a silent hole. Whatever the view can reach, the data has to reach too.** Earlier: 🔴 **the "SSH" health check never touched the tunnel, and `/health` on the MT5 agent never touched MT5.** `_check_ssh` ran `ssh forexvps "echo ok"` — a brand-new connection unrelated to the port forwards — so the dot went green over a dead tunnel; and the MT5 agent answers `ok` whether or not its terminal is running or logged in, so a disconnected MT5_Lab showed green while every python run needing uncached bars failed at fetch time. Both are measured properly now (`ssh_tunnel` = the forwards are bound, `vps_reachable` = the old question, `mt5_connected`/`mt5_server`/`mt5_account` off the agent's `/status`), and `mt5_connected` is `Optional[bool]` because **`None` = could not ask, which is not the same as disconnected**. With them, `main._auto_start_agents` — a one-shot thread 8s after boot — became **`services/agent_supervisor.py`**, a 60s loop whose first pass is identical to every later one; see *The agent supervisor* below for the two-probe table, the job-lock guard, and the deliberate unbound-vs-stale asymmetry. `restart_tunnel`/`schtasks_run` moved out of `routers/system.py` into that service (subprocess calls belong in `services/`, and `main.py` had been reaching across into the router to call one). Also new: `services/readiness.py`, the boot report for dependencies that fail silently. 330 tests green (31 new). Earlier: 2026-07-31 — **profit concentration had been measuring the account, not the edge.** The largest-quarter share was weighted in DOLLARS, which on a compounding run reports the compounding: the last quarter of an 85x account holds nearly all the dollars however evenly the edge is spread. Run `d2ab68f9e884` read **88.94%** — past the 60% "overfit risk" threshold — where the same trades weighted by RETURN read **39.97%**. `profit_concentration_pct` now takes the equity curve (that is what says whether a run compounded), stores a `profit_concentration_basis` beside the number, and `init_db` re-stamps history; all 78 completed runs were converted. See `## Metrics` → *Profit concentration*. Same day: **`unconstrained` had been returning PASS on every run, including one that lost 95% of the account.** `_evaluate_personal` ended `DISCARD if failures else PASS`, and both its checks are guarded on limits that row deliberately does not set, so `failures` was empty by construction — a vacuous pass, and the exact opposite of what `lab_db.py`'s seed note on that row says ("a run against it cannot be graded"). It now returns `INFO` ("Not graded" in the UI). Verdicts are **stored**, so `init_db` also carries an idempotent migration rewriting the affected `PASS` rows — every evaluation row in the live DB was this case. See `## Ruleset types` → *Nothing checked is not a pass*. Earlier: 2026-07-30 — **the stress-test engine was measuring the wrong things, and the D grade on `630cefbebd8347db` was the engine's fault, not the strategy's.** Four defects fixed, all generic (Aaron's scoping rule: fix what is inaccurate for ANY strategy, never tune the engine to this one). (1) Monte Carlo shuffled a DOLLAR P&L series on a compounding run — trade size drifts 17.7x across that run, so the shuffle simulated a strategy that never existed; it now switches to the per-trade RETURN series and compounds when the dollars actually drift, and the worst-1% drawdown went $41,970 → $359,886. (2) Drawdown is now compared PERCENT-to-percent on such runs — the dollar view had reported a 100% breach of total ruin across 20,000 simulations that never once wiped out the account. (3) Sensitivity scores on PROFIT FACTOR, not net P&L, so a sizing knob is no longer graded as fragility (`exec_risk_pct`: 85.8% on profit vs 11.8% on PF, and it alone set the run's score); no-op shifts are skipped, which is where ~50 of the run's 80 minutes went (43 of 60 backtests reproduced the baseline exactly). (4) Walk-forward now drops windows under 20 trades, and an unassessable WF caps the grade at B instead of being silently free. Also: a `None` grade is now a first-class outcome — **D used to be the CEILING for a ruleset stating no drawdown limit** — and `personal_forex_risk` (55%) was seeded so forex runs have a bar to be graded against. ⚠ Grading no-limit rulesets against total RUIN was built, measured, and removed — see the walk-back in `## Robustness grading`. Earlier: 2026-07-29 — `entry_ms` added to `models.EquityPoint`, which is what had the News filter reporting every run as "made before trade times were recorded"; the filter now works on Python runs too. 2026-07-27 — missed setups (how close the ones that died came) plumbed alongside blocked setups, strategy → output → run dir → chart spec; `chart_spec` now ships the run's own timeframe and caps the WINDOW instead of coarsening the bars

Auto-loaded by Claude Code when editing any file inside `backend/`.

FastAPI backend served on `:8000`. Talks to the VPS via SSH and HTTP, runs smart-money pipeline via subprocess, and owns all SQLite state. The frontend never touches the filesystem or the VPS directly.

The lab module (strategies, firms, backtests, evaluations) is live as of M1.

**Lab design principle:** The user always picks which firm challenges to evaluate against. Never default `evaluate_firms` to all firms.

---

## Guides & references

- `command-center/docs/PROP_RULESET_KPIS.md` — per-firm prop ruleset KPIs, doc links, and the DB sync-check query.
- `command-center/docs/BACKEND_BUILD_NOTES.md` — NT8 Strategy Analyzer pywinauto automation implementation notes, and the dynamic sizing/risk engine build history.

---

## Directory layout

```
backend/
├── main.py                app entry; registers all routers
├── config.py              loads config.json → typed module constants
├── config.json            machine-specific paths only — no business logic here
├── models.py              ALL Pydantic models — one file, never split
├── routers/               thin — validation + status codes only, no business logic
│   ├── smart_money.py
│   ├── bots.py
│   ├── backtests.py       lab — backtest runs; GET /history-limit serves the measured broker history floor (drives the UI date picker); GET /runs/{id}/chart-spec serves the price-chart ChartSpec (chart_spec.py); GET /runs/{id}/news serves the post-run news/holiday trade tags (news_filter.py); GET /runs/{id} takes `?timeline=false` to drop `regime_timeline` (96 KB of a 137 KB detail) for a caller that already has that calendar — default stays `true`, and `[]` is indistinguishable from a run that never had one
│   ├── strategies.py      lab — strategy registry + deploy endpoint + POST /scan (read-only) + POST /reconcile (destructive orphan cleanup) + GET /:id/instrument_summary + GET /:id/param-types
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets); PATCH = guarded personal-rules edit (prop rows locked 403; PUT also 403 on prop)
│   ├── system.py          lab — health + log proxies
│   ├── strategy_files.py  lab — strategy file deployment (list, upload, delete, compile, sync-status)
│   ├── stress_tests.py    lab — stress test CRUD + trigger (GET /stress-tests, GET /running-lock, GET /strategy-grades, GET /:id, POST /run, **POST /:id/cancel**, DELETE /:id). The trigger returns `warnings` (a walk-forward whose windows cannot each hold 20 trades is arithmetic, knowable before ten backtests run); DELETE rmtrees the test's dir AND every child's
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps, GET/DELETE /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*, DELETE /optimizations/:id)
│   ├── calendar.py        live News Calendar tab — thin GET /calendar?from&to (ISO); returns the whole week unfiltered, 400 on bad ISO/window, 502 on feed error. GET /calendar/currencies serves the filter roster (static, no upstream call) so the page's chips cannot drift from the query
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_import.py   the ONE way a Python strategy package is imported — purge the cached
│   │                      `strategies.python.*` modules, then import. This backend is long-running,
│   │                      so `import_module` otherwise pins whatever was on disk at boot; the
│   │                      scanner then writes a fresh source hash beside stale defaults and the row
│   │                      becomes UNCORRECTABLE by scanning. See *The scanner read the module and
│   │                      hashed the files* below
│   ├── strategy_scanner.py  reads from strategies/ (not algos/); scan is READ-ONLY (add/update + report orphans, never deletes). reconcile_strategies() is the explicit destructive counterpart (DB row + VPS file); remove_strategy() is the shared one-strategy delete.
│   │                      ⚠ Its tests state the expected roster ONCE, as `EXPECTED_CLASS_NAMES` in
│   │                      tests/test_strategies.py — added/skipped counts are `len()` of it, never a
│   │                      repeated literal. Adding a strategy used to fail three tests that each had
│   │                      to be traced back to the same cause; now it is a one-line edit
│   ├── evaluator.py       per-ruleset verdict; also exports compute_contract_cap_status()
│   ├── trailing_drawdown.py  compute_trailing_mll() — EOD trailing max-loss engine (the drawdown check)
│   ├── sizing_engine.py     dynamic sizing & risk engine — PURE (no DB/network). run_engine(mode="bullet"|"consistent") sizes each trade off the room left (bullet=max the rules allow; consistent=room÷7), reserves open-trade risk, applies halts, rounds-up-to-min-or-skip, detects breaches; emits size-correct daily_pnl (feeds evaluator) + the decision log. CORE BUILT, not yet wired to a runner — see "Dynamic sizing & risk engine" below
│   ├── decision_log.py      the ONE reusable audit log — TradeDecision/DecisionLog. One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order, the sizing decision, and the full life of a taken trade. Extensible (new gate = decision.gate(...)); identical in backtest and live
│   ├── metrics.py         shared metric helpers: daily_sharpe / apply_canonical_sharpe / profit_concentration_pct / compute_regime_breakdown (per-regime P&L table → BacktestDetail.regime_breakdown; rescales direction-point counts to trade_count — after the _normalize_mt5_results fix, MT5 equity curves have one point per trade so scale=1.0, but the rescale is kept for safety)
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    runs N backtests sequentially (semaphore = 1) for a sweep
│   ├── optimization_runner.py  native NT8/MT5 optimizer (one VPS job, all CPU cores)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   ├── stress_tester.py   Monte Carlo + walk-forward + sensitivity + auto-trigger
│   ├── grading.py         compute_grade() → A/B/C/D/F with plain-English reasons
│   ├── scripts/backfill_metrics.py  one-time, idempotent backfill of file-derivable metrics on old runs
│   ├── scripts/backfill_regime_timeline.py  opt-in backfill of `regime_timeline.json` on old runs (`--force`, `--run-id`); kept OUT of backfill_metrics.py because it fetches OHLC
│   ├── scripts/prop_kpi_audit.py    read-only dump of every prop ruleset's core KPIs from lab.db (the saved "is our engine in sync" query); feeds docs/PROP_RULESET_KPIS.md
│   ├── ohlc_fetcher.py    fetch and cache daily OHLC per (instrument, date); NT8 first, yfinance fallback
│   ├── chart_spec.py      build the ChartSpec for the price-chart panel (candles + sessions + trades + blocked setups + recomputed strategy structure/ATR + market-structure overlays). Always ships the timeframe the run TRADED and caps the WINDOW instead (`_capped_start` → the newest slice under `_CANDLE_CAP`), with `historyStartMs` telling the panel how far back it may page; see "ChartSpec candles" below. `_build_blocks` reads the run dir's `blocked_setups.json` — see "Blocked setups" below; `_build_misses` reads `missed_setups.json` and ALSO returns the derived `missNoise` list — see "Missed setups" below
│   ├── fvg_overlays.py    replay the CANONICAL engines/fair_value_gaps/ engine (+ engines/equal_highs_lows/
│   │                      for mpc's eqExemptFvg cap coupling) over a run's candles → the "Fair Value Gaps"
│   │                      overlay group. Emits a box ONLY for a gap that was LIVE on a trade-entry / blocked /
│   │                      missed bar (all of them when several overlap); everything else is dropped. Settings
│   │                      are mpc_assistant.pine's LOCKED constants incl. the timeframe-SPLIT gap floor —
│   │                      NOT the strategy's, which differ. See "Fair value gaps" below
│   ├── ob_overlays.py     the same shape for ORDER BLOCKS — replay the CANONICAL engines/order_blocks/
│   │                      engine over a run's candles → the "Order Blocks" overlay group, one box per
│   │                      block that was LIVE at a trade-entry / blocked / missed bar. Read
│   │                      fvg_overlays.py first; the differences are the BOX GEOMETRY (a fixed 30-bar
│   │                      stub from the anchor candle, not a box tracking the live bar) and that here
│   │                      there is NO settings fork to warn about. See "Order blocks" below
│   ├── structure_overlays.py  replay the CANONICAL engines/market_structure/ engine over a run's candles → BOS/SOS/swing overlays for the chart, in the 4 groups that ARE structure_engine.pine's 4 toggles (External / Internal / Historic Internal Structure / Swing Point Labels), nesting like the Pine's via each overlay's `requires` list (swing tags need their owning structure; historic internal needs Internal). Never a 2nd engine (bare-name import like regime/news); called by chart_spec on the displayed TF. Break tags anchor at the line MIDPOINT (`_mid`, = Pine's `mid_x`) so they clear the break-bar candles; reversal breaks are labelled SOS/iSOS (not "CHoCH")
│   ├── news_filter.py     post-run news/holiday tagging — composes the canonical engines/news/ engine (never a 2nd impl) to mark which of a run's trades opened in a high-impact news window / on a bank holiday, for the BacktestDetail News filter card. Pure over a trade list; loads the EventStore cache (see "News filter (post-run)")
│   ├── history_limits.py  broker history floors — thin shim over the canonical `backtest/data/history.py`
│   │                      (declares NO dates itself). `limits_for()` → the MEASURED earliest backtestable
│   │                      date for an (instrument, timeframe, runner); `validate_window()` raises ValueError
│   │                      which routers turn into a 400. PYTHON RUNNER ONLY — NT8/MT5 read history from their
│   │                      own terminals, so a Vantage floor must never be imposed on them (see "History floors")
│   ├── calendar_service.py  live News Calendar tab — calls engines/news/ TradingViewSource.fetch_window() (never a 2nd impl), 60s in-memory cache keyed on (from,to,countries) and BOUNDED at 64 entries under one lock, computes beat/miss "surprise" server-side via _LOWER_IS_BETTER. Read-only: does NOT touch the shared EventStore cache. Returns the whole week; the frontend filters client-side. ⚠ Every upstream failure is normalised to RuntimeError in `_fetch` — a JSONDecodeError IS a ValueError and used to surface as a 400. See "The calendar's polarity list" below. Also owns `currencies_for()` — the chip roster the page draws, DERIVED from the queried country list via `_COUNTRY_CURRENCY` (bloc codes and ISO currencies are different namespaces, so only this side can map them)
│   ├── agent_supervisor.py  keeps the SSH tunnel + both VPS agents up — one 60s loop, identical on
│   │                      every pass, so a cold start and a wake-from-sleep are the same code path.
│   │                      Owns `restart_tunnel()` / `schtasks_run()` (moved out of routers/system.py,
│   │                      where main.py was reaching across to call one). Probes the TUNNEL by port
│   │                      binding and the AGENTS by HTTP, because `ssh -L` binds the local port
│   │                      itself — see "The agent supervisor" below
│   ├── readiness.py       boot-time report of the dependencies that fail SILENTLY (news calendar
│   │                      cache, Telegram credentials). Reports, never acts; `GET /system/readiness`
│   ├── runner_dispatch.py      typed HTTP wrapper over NT8 nt8_agent; runner dispatcher (routes mt5 → mt5_agent_client)
│   ├── mt5_agent_client.py  typed HTTP wrapper over MT5 agent (port 8766 via SSH tunnel). `health()`
│   │                      is the AGENT; `status()` is the TERMINAL (mt5_connected/account/server) —
│   │                      two different questions, and only the second says a run can fetch bars
│   ├── python_runner.py     local Python runner — runs strategies/python/ packages in-process via the top-level backtest/ package (backtests + A4 optimizer sweep). No VPS, no agent. Resolves strategies by `strategy_class` (the class `__name__` the scanner stored) — NEVER by package id
│   └── notify.py            Telegram notifier (urllib, no extra deps). Holds NO token: it reads env vars, else the git-ignored `algos/credentials.json`, by PATH (`cfg.MONOREPO_ROOT / "algos" / "credentials.json"`) — the same file `algos/shared/credentials.py` reads, without importing across the app boundary, which the subsystem-independence rule forbids. `routers/bots.py` delegates here; it must never grow its own sender again. `telegram_configured()` answers whether a send would go anywhere. **Every send states a `kind`** (`HEALTH` for everything this app produces) and the kind picks the chat — see the Telegram row in the feature table
├── data/lab.db            strategies, rulesets, runs, evaluations, optimizations, stress_tests
└── reports/lab/           run output files — equity curves, logs, progress.json
```

---

## Router conventions

```python
from fastapi import APIRouter, HTTPException
import config as cfg
from models import ThingA, ThingCreate
from services import some_service

router = APIRouter(prefix="/things", tags=["things"])

@router.get("", response_model=list[ThingA])
def list_things(): ...

@router.post("", response_model=ThingA, status_code=201)
def create_thing(body: ThingCreate): ...
```

- Prefix = single noun, plural (`/strategies`, `/bots`, `/firms`)
- Routers validate input and set status codes — nothing else
- Business logic, DB queries, subprocess calls → `services/`
- Trigger endpoints → 202 with `{run_id, status: "started"}`
- Errors → `HTTPException(status_code=..., detail=...)`, never bare `raise`
- Always set `response_model` on read endpoints

---

## Pydantic models

All in `models.py`. One file. Never split it.

- `snake_case` fields
- `Optional[X] = None` for nullable fields
- `field_validator` for constraints
- New models go at the bottom of their section

---

## SQLite conventions

- Raw `sqlite3` only — no SQLAlchemy, no ORM
- Each domain owns one DB file. Lab cannot read smart-money tables — expose cross-domain data through the other domain's API
- Schemas in `init_db()` — run on startup, idempotent (`CREATE TABLE IF NOT EXISTS`)
- All queries parameterized — never `f"WHERE id = '{id}'"`
- `conn.row_factory = sqlite3.Row` for dict-like access

**Heavy data goes on disk, not in SQLite.** Equity curves, trade lists, daily P&L arrays → JSON files under `reports/lab/<run_id>/`. DB row stores the path.

---

## VPS interaction

| Channel | Use for | How |
|---|---|---|
| SSH (subprocess) | File transfer, Task Scheduler, taskkill | `subprocess.run(["ssh", cfg.SSH_ALIAS, ...])` |
| HTTP (nt8_agent) | NT8 control, pywinauto, live job control | `services/runner_dispatch.py` — always use the typed wrapper |

Never make a synchronous SSH call from a request handler that could take > 2s. Background it.

---

## NT8 Strategy Analyzer UI automation (nt8_backtest_runner.py)

Backtest and optimization runs drive NT8's Strategy Analyzer window via pywinauto (WPF UI automation over SSH), not an API — there's no native NT8 automation interface. This is inherently fragile: WPF control identification, popup timing, and mode-switch state all have non-obvious failure modes.

Full implementation notes (exact sleep durations, coordinate math, ComboBox identification quirks, optimization export mechanics, param-setting order): `command-center/docs/BACKEND_BUILD_NOTES.md`.

---

## Background job pattern

Smart-money `/run` is the canonical pattern:

1. Check progress file — return 409 if already running
2. `subprocess.Popen` the worker, redirect stdout/stderr to log file
3. Write PID to `reports/<domain>/.pid`
4. Return 202 immediately
5. Worker writes `progress.json` atomically (write `.tmp` → `os.replace`)
6. `/progress` endpoint reads the file; frontend polls
7. `/stop` reads PID, sends SIGTERM, resets progress

Lab backtests use the same pattern but the "worker" is the NT8 agent over HTTP.

---

## Config

`config.json` holds machine-specific paths and the SSH alias. Nothing else. No thresholds, no business rules, no feature flags. If you're adding a non-path field to `config.json`, it belongs somewhere else.

---

## What NOT to do

- Hardcode paths — everything machine-specific comes from `config.json`
- Cross-domain DB access — lab cannot SELECT from smart-money tables
- Business logic in routers — validate and delegate only
- Synchronous SSH in request handlers — background it
- Introduce an ORM or new framework without raising it first
- Write `progress.json` non-atomically — always write `.tmp` then `os.replace`
- Treat a `/health` response as a statement about the thing BEHIND the agent. The MT5 agent answers
  `ok` while its terminal is disconnected, and `schtasks /run` answers SUCCESS for a task Windows
  refuses to launch. Probe the thing you are actually claiming, and re-probe after any action
- Write a destructive test and rely on a person remembering a flag to keep it out of the way.
  `tests/test_integration.py` drives the live VPS and its Case 6 kills a running agent on purpose;
  its docstring said "select it explicitly" from day one and nothing enforced it, so a bare
  `pytest tests/` ran the lot. `pytest.ini` now carries `-m "not integration"` — the suite is
  DESELECTED by default and runs only on `pytest tests/test_integration.py -m integration`. If you
  add another test that touches the live box, mark it `integration` so the same interlock covers it
- Kill by image name anywhere — in source, in a test, or in a one-off command. `taskkill /f /im
  python.exe` takes out both backtest agents, the Telegram bot and the LIVE TRADING BOT, and it is
  what left the bot dead for three days in July. `test_integration.py` carried one until 2026-08-05.
  Every kill matches on BOTH `name='python.exe'` and something identifying the ONE process — see
  `routers/bots.py::_kill_bot` for why each half is load-bearing
- Let the agent supervisor run in a test process. `CC_DISABLE_SUPERVISOR=1` is set at module scope
  in `tests/conftest.py`; a fixture is too late, because `main` is imported at collection. Without it
  a plain `pytest tests/` restarts the SSH tunnel and fires two scheduled tasks on the live VPS
- Commit credentials (Telegram tokens, API keys, `.env`)
- Add a prop firm without filling in `docs_url` — rules drift, the link is how you verify

---

## When you add a new module

1. Create `routers/<thing>.py`
2. Create `services/<thing>.py` (or `<thing>_db.py` for DB-heavy modules)
3. Add Pydantic models to `models.py`
4. Register the router in `main.py`
5. If it has its own DB, create it under `data/` and call `init_db()` on startup
6. Update directory layout above

---

## Ruleset abstraction (M3)

The `firms` table is now `rulesets`; `firm_id` is `ruleset_id` everywhere (evaluations, optimizations). The `/firms/*` backward-compat redirect shim (`routers/firms.py`) was removed 2026-07-01 — no callers were found (frontend's `useFirms` is an alias to `useRulesets`, never hit `/firms` directly). `BacktestRunRequest.evaluate_rulesets` replaces `evaluate_firms` (backward-compat alias still accepted). Full migration story is in git history (M3).

**`ruleset_type` values and evaluation logic:**

| ruleset_type | Who uses it | Evaluator behavior |
|---|---|---|
| `prop_eval` | Prop firm eval challenges | EOD trailing max-loss (DISCARD on breach) → profit target (WARN if missed; target is raised when a `raise_target` firm's consistency is breached) → consistency (WARN). PASS if all clear. |
| `prop_funded` | Prop firm funded accounts | EOD trailing max-loss only — PASS if not breached, else DISCARD. No WARN. |
| `personal` | Personal trading accounts | Real PASS/DISCARD verdict against the relaxed personal rules (`_evaluate_personal`): DISCARD on `max_consecutive_loss_days` consecutive days whose loss hit `daily_loss_cap`, or on EOD equity dropping `max_drawdown_from_peak_pct` from its running peak; otherwise PASS. **`INFO` when the ruleset configures NEITHER condition** — see *Nothing checked is not a pass* below. `daily_profit_target` is an informational halt note, never a fail. No trailing MLL (max_loss_eod = 0 sentinel), no profit-target requirement, no consistency rule, no reference line. |
| `demo` | Paper/demo accounts | Same as `personal`. |

**Nothing checked is not a pass (fixed 2026-07-31).** `_evaluate_personal` ended
`verdict = "DISCARD" if failures else "PASS"`, and both of its checks are guarded — check 1 needs
`daily_loss_cap` AND `max_consecutive_loss_days`, check 2 needs `account_size` AND
`max_drawdown_from_peak_pct`. On `unconstrained`, which states neither by design, both were skipped
and `failures` was empty *by construction*: **a run that lost 95% of the account returned PASS.**
Zero failures out of zero checks is the absence of a verdict, not a passing one, and it contradicted
the rule `lab_db.py`'s own seed note states on that row ("a run against it cannot be graded… there is
no honest default to substitute"). It now returns `INFO`, which the frontend already renders
neutrally as **Not graded** with no rule chips. Two things to keep in mind if you touch it: the
"was anything checked" test must **mirror the two guards exactly** (testing the caps alone called a
run graded when a missing `streak_limit` had silently skipped check 1), and because verdicts are
**stored**, the source fix alone leaves history wrong — `init_db` carries an idempotent migration
rewriting stored `PASS` rows on limit-less personal/demo rulesets to `INFO` (every evaluation row in
the live DB was exactly this case). Guard on `!= 0` as well as `IS NOT NULL`: `daily_loss_cap` is
`0`, not null, on both no-limit rows.

For prop types the verdict reads `max_loss_eod` (the trailing-MLL amount) and `mll_lock_balance` for drawdown; it never reads `daily_loss_cap` (a soft/informational field for firms like Apex). For personal/demo types `daily_loss_cap` IS a rule input (the capped-day trigger) and `max_loss_eod` is never read (0 sentinel = no trailing EOD rule). `metrics.effective_dd_limit_usd()` is the one place that turns a ruleset into a dollar MC/objective drawdown limit — personal/demo rows translate to `account_size × max_drawdown_from_peak_pct`. The stress-test primary pick excludes personal/demo rows from its strictest-ruleset comparison; worthiness prefers prop rows but falls back to the strictest personal/demo limit when a run was evaluated against personal/demo only (forex).

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

Columns on `rulesets`: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (18 rows): 4 prop firms = 14 prop rows — LucidFlex, FundedNext, Tradeify each at 50k/100k × eval/funded (12 rows), plus Apex EOD eval-only at 50k/100k (2 rows; funded/PA not yet seeded) — plus 2 personal demo rows (`personal_forex_demo`, `personal_futures_demo`; ruleset_type `personal`, account_tier `demo`), `unconstrained`, and `personal_forex_risk`. Personal demo rules on a $10k balance: $500 daily loss cap, $1,000 daily profit target, fail at 15% drawdown from peak (`max_drawdown_from_peak_pct`) or 3 consecutive capped-loss days (`max_consecutive_loss_days`) — stored now, enforced in a later evaluator pass. `max_loss_eod = 0` is the sentinel for "no trailing EOD rule" on personal rows (the column is NOT NULL); the evaluator must treat it as rule-absent. All seeded via the per-id idempotent pattern (`_PROP_SEED_ROWS` + `_seed_apex_eod_eval`). The core KPIs of all 14 prop rows (account size, target, drawdown type/amount/lock, consistency, min trading days, contract scaling, funded split, doc links) are documented for hand-off in `command-center/docs/PROP_RULESET_KPIS.md`, which also carries the firm doc links, the saved sync query (`scripts/prop_kpi_audit.py`), and a verification prompt; re-run that prompt to re-check the firms and keep the doc in sync with the DB. Display names: the firm name lives in the UI group header only; `name` carries the program/challenge ("LucidFlex $50k Evaluation", "Select $50k Evaluation", "Futures Flex $50k Challenge", "EOD $50k Evaluation") — canonical map in `_RULESET_DISPLAY_NAMES`, re-applied on every `init_db`. The firm behind the `lucidflex_*` ids is Lucid (Lucid Trading); LucidFlex is its program name.

**The two forex rows are a PAIR, and the difference is the whole point (2026-07-30).** `unconstrained` states no limit, which makes it the honest raw-behaviour view AND ungradeable — every grade in `services/grading.py` is a statement about drawdown vs a limit, and there is no defensible default to substitute (see the ruin walk-back in `grading.compute_grade`). `personal_forex_risk` ("Personal Forex — 55% Drawdown") is the same row with the one bar stated, so the same run returns a letter. 55% is **Aaron's stated tolerance**, picked against his own measured numbers on the A+ SOS Fade run: worst-5% of simulations draws down 53.2%, worst-1% draws down 62.1% — so 55% accepts the 5% tail and explicitly does not accept the 1% tail. Every other limit on it is deliberately absent (no daily cap, no loss-streak rule, no profit target), because at 10–12.5% risk per trade a daily cap fires constantly and the verdict stops being about drawdown.

⚠ **The 15% on `personal_forex_demo` is a PROP-FIRM figure and must never be applied to forex** (Aaron, 2026-07-29). Grading a forex run against it produces a D that says nothing about the strategy. Pinned by `tests/test_rulesets.py::test_the_forex_risk_row_does_not_inherit_the_prop_15_percent`.

---

## Dynamic sizing & risk engine + decision log

The mechanism behind the LWG gated-layer model (`docs/LWG_Strategy_Framework.md`,
`docs/dynamic_sizing_engine.md`): the strategy proposes setups at unit size; gates decide
*whether* a trade is allowed; the engine decides *how big* from the room left now. No strategy
manages risk.

- **`services/sizing_engine.py`** — PURE (no DB/network/clock). `run_engine(trades, ruleset,
  *, is_micro, mode)` where mode is the per-run **bullet/consistent** switch: bullet = the most
  the rules allow (with a one-loss-can't-breach guard); consistent = **room ÷ 7** per trade.
  Room is measured to the **trailing floor** (highest-EOD-based, capped at the firm lock — NOT
  balance−start, so growth doesn't fake a buffer). It reserves **open-trade risk** (a running
  trade holds its risk; the next signal shrinks or is blocked), rounds a sub-minimum size **up
  to 1 only if 1 still fits the room** else skips, applies the daily-loss / profit-target halts,
  and detects breaches. Output: `daily_pnl` (size-correct — feeds `evaluator.evaluate_run`
  unchanged, so no second grader), a day-by-day `timeline`, `sized_trades`, and `decisions`.
  Sizing is goal-driven, NOT % of balance and NOT `daily-loss ÷ trade-count` (both dead).
- **`services/decision_log.py`** — `TradeDecision` / `DecisionLog`, the one reusable audit log.
  One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order
  (which one shut it down, or that all passed), the sizing decision (size + what bound it, or why
  skipped), and the full life of a taken trade (entry, exit, exit reason, P&L). Gates are an
  ordered list — a new gate just calls `decision.gate(name, passed, reason)`, no schema change.
  Pure stdlib, identical in backtest and live.
- **`services/sizing_pipeline.py`** — the FS/IO wiring: `run_sizing_engine(run_id, trade_records,
  ruleset, *, mode, instrument, strategy, results_dir)` builds `RawTrade`s from a runner's export,
  runs the engine, and persists `decisions.jsonl` + `engine_timeline.json` + `engine_daily_pnl.json`
  to the run dir. `size_run_for_rulesets(...)` sizes once per ruleset and additionally writes every
  firm's `{kpis, daily_pnl, timeline}` to `ruleset_sizing.json`, keyed by ruleset id, so every
  evaluation carries its own P&L, timeline, and equity curve (not just the primary/headline
  ruleset) — this is what lets BacktestDetail switch all ruleset-dependent charts/KPIs per firm.
  Locks the runner→engine column contract.
- **Tests:** `tests/test_sizing_engine.py` (20), `tests/test_decision_log.py` (7),
  `tests/test_sizing_pipeline.py` (7) — all green.

**Current state:** ORB.cs (NT8) and LondonBreakout.mq5 (MT5) are both reshaped to trade unit
size and emit `engine_trades.csv` (the runner→engine contract). `nt8_backtest_runner` and the
MT5 agent both read that file back after a run and attach it as `result["engine_trades"]`;
`backtest_runner._handle_complete` sizes any run that carries `engine_trades` per ruleset,
runner-agnostically (same gate for NT8 and MT5). The per-run **bullet/consistent** sizing mode
is plumbed end-to-end: `BacktestRunRequest.sizing_mode` → `backtest_runs.sizing_mode` column →
`BacktestDetail.sizing_mode`/`sized`/`sized_timeline`. Native (unit-size, non-reshaped) runs
carry no `engine_trades` and are unaffected. The whole sized path only activates once a reshaped
strategy actually emits `engine_trades.csv` from a VPS run.

Build history (the ORB/LondonBreakout reshape, the NT8/MT5 wiring order, the per-firm
`ruleset_sizing.json` rollout, and the MT5 tester-agent sandbox file-path gotcha) is in
`command-center/docs/BACKEND_BUILD_NOTES.md`.

## Lens metrics (the per-run scoring layer)

**Drawdown = EOD trailing max-loss** (`services/trailing_drawdown.compute_trailing_mll`), not whole-test max DD. Floor trails the highest EOD balance, capped at `mll_lock_balance` when set; a breach (balance falls through the floor) is the only thing that fails `drawdown_pass`. Detail columns on `evaluations`: `mll_final_floor`, `mll_highest_eod_balance`, `mll_breach_day`, `mll_min_floor_distance`.

**Canonical Sharpe — one definition everywhere.** `metrics.apply_canonical_sharpe(kpis, daily_pnl)` writes the daily-√252 Sharpe into `sharpe`, moves the platform's value to `platform_sharpe`, and sets `sharpe_low_sample`. It's called at every run-completion path that has `daily_pnl` — single run, sweep child, stress child, optimizer winner — but NOT the native-combo path (no daily_pnl). **Idempotency guard:** only runs when `platform_sharpe` is null, so a second pass can't overwrite the platform value. Walk-forward window Sharpe (`stress_tester._compute_sharpe`) goes through the dated `daily_sharpe`.

**Flat days are zero-filled before the Sharpe (2026-07-16).** `daily_pnl` carries only days that closed a trade (the trailing-drawdown engine walks the days that exist), so Sharpe used to average the ACTIVE days and annualize by √252 — scoring a strategy that's flat 90% of the time as if every day earned the active-day mean. A real 22-trade/225-day run read **7.80 against a true ~2.2**; TradingView's own Sharpe on the same trades, annualized, independently agreed at ~2.0 (see `metrics.zero_filled_daily_values`). `daily_sharpe(daily_pnl)` now zero-fills every weekday in the span first — dates PRESENT are always kept, even on a weekend, so a Sunday-open forex fill isn't dropped. **Do NOT change `daily_pnl` itself** — the trailing-drawdown engine depends on flat days being absent; the zero-filled series exists only for Sharpe.

Two traps this creates, both guarded:
- **`sharpe_low_sample` must count ACTIVE days** (`metrics.active_day_count`), never `len()` of the zero-filled series — otherwise a 3-trade year reads as ~250 well-sampled days and the flag never fires, exactly where it's needed most.
- **`daily_sharpe_from_values` (undated) does NOT zero-fill and must stay that way** for callers whose day population is sparse *by definition* — the optimizer's regime-filtered scoring, where the days in between are other regimes, not flat days of this one.

**Backfill (`scripts/backfill_metrics.py`) recomputes `sharpe`/`sharpe_low_sample` on EVERY pass** (pure functions of the stored `daily_pnl` → idempotent), which is how a change to the canonical definition reaches history; only the one-way `sharpe`→`platform_sharpe` move stays null-guarded. **The move skips `runner = 'python'`**: `backtest/output.py` deliberately computes no Sharpe, so a python run's `sharpe` is already ours, and moving it would stamp our own value as "the platform's" and invent a reference that never existed — NULL is the honest answer.

**Contract cap** (`evaluator.compute_contract_cap_status`, informational — never moves the verdict): scaling ladder → `not_applicable`; MT5 (lots) → `not_applicable`; NT8 without per-trade size → `not_evaluable`; NT8 fixed cap + size → real largest-single-trade vs cap. Per-trade `size` is captured from NT8's Quantity column / MT5 volume.

**Profit concentration** persisted as `profit_concentration_pct` (largest quarter's share of gross profit) for later grading use, alongside `profit_concentration_basis` — `'return'` or `'dollars'` — which says how it was weighted, so a row is self-describing.

**It is weighted in RETURNS whenever the run COMPOUNDED (fixed 2026-07-31), and this was a real false alarm, not a refinement.** In dollars the metric reports the compounding rather than the clustering it exists to detect: on an account that grows 85x, the final quarter must hold nearly all the dollars however evenly the edge is spread. Measured on run `d2ab68f9e884` — dollar quarters of $9k / $49k / $71k / $1,039k read **88.94%**, which is past the 60% "edge clustered — overfit risk" threshold and was the only warning colour on that page; the same trades weighted by each one's return on the equity it was taken with read **39.97%** ("spread across the test"). The switch is whether the equity curve carries a real account base (`_equity_base > 0`): a %-of-equity strategy compounds and must be normalized, while an NT8-shaped cum-P&L-from-zero curve is a unit-size run whose dollars ARE already comparable across periods — dividing those by a fictitious balance would introduce the opposite bias. **`profit_concentration_pct` therefore needs the EQUITY CURVE, not just `daily_pnl`**; every caller passes it (`backtest_runner._handle_complete`, `scripts/backfill_metrics.py`).

Because the figure is stored, `init_db` carries a one-time `_restamp_profit_concentration` that re-reads each completed run's `equity_curve.json` and rewrites it; `profit_concentration_basis IS NULL` is the marker that makes it run exactly once. A run whose file is missing is stamped `'dollars'` — that IS what its stored number is, and leaving it NULL would re-read a missing file on every startup forever. It restamped all 78 completed runs in the live DB. The frontend recomputes client-side rather than reading the column (`frontend/CLAUDE.md` → *Profit concentration measures the edge*), so a page never depends on this migration having run.

### The Python runner's costs were collected and never charged (fixed 2026-08-01)

`commission_per_side` and `slippage_ticks` are collected in the Run modal, stored on
`backtest_runs`, shown on the run page — and `services/python_runner.py` read neither. Every
Python run was **frictionless** while reporting a cost profile it had not applied. The tell in the
data was 52 of one run's 54 losing trades each losing **exactly 10.00%** of prior equity, which no
cost model can produce; the values themselves (2.25/1) came from a FUTURES prop-firm ruleset and
were never meaningful for spot gold.

`python_runner._cost_profile(spec)` is the seam: it turns the run's stated costs into a
`backtest.fills.AccountProfile`, passed to both the single-run path and `run_sweep` (so the
optimizer cannot rank combos on a frictionless book and then hand the winner to a run that is
not). Four rules, each of which fails silently if broken:

- **0/0 returns `None`, not a zero-valued profile.** No profile means no charge path is entered at
  all, which is what keeps every result measured before this date reproducible.
- **Either number alone builds one.** An `and` there would drop slippage-only runs back to
  frictionless — the same bug, one level down.
- **Commission is per LOT per side** (a lot = `contract_size` units, 100 oz for gold). Reading the
  field as per-unit overcharges gold 100x and nothing downstream looks wrong.
- ~~**`swap=None` deliberately.**~~ **Superseded 2026-08-02 — see below.**

#### Layered costs — and the two numbers that were never typed in (2026-08-02)

Aaron's framing, and it is the right one: the spread and the swap are things we KNOW, so leaving
them unpriced is a choice nobody made. Both are now chargeable in bar mode, and the request carries
**`cost_layers`** (which costs to charge) + **`broker_profile`** (whose measured facts to charge
them from) — `python_runner.COST_LAYERS` is the roster, `backtest.fills.PROFILES` the source.

**Every layer is OFF by default, and that is Aaron's explicit call.** A bare run charges nothing,
so it stays directly comparable to the TradingView Strategy Tester, and each cost is switched on
deliberately. **Slippage keeps its own switch and its own typed number** for the opposite reason
to the rest: it is the one cost no amount of history can measure, so it must never ride along with
the measured ones.

Four rules, each of which fails silently if broken:

- **`cost_layers` absent (`None`) is NOT `[]`.** `None` = a row written before layers existed and
  must keep the old contract (charge whatever commission/slippage it stated); `[]` = charge
  nothing. Collapsing them would re-price all 80 stored runs the first time one was retried.
  `routers/backtests._json_list` preserves the distinction on the way out, and the API models it
  as `Optional[list[str]]` so the page can caption which it is.
- **`spread` and `swap` are never accepted from the request.** They are measurements, and a field
  the operator can type is a field that can disagree with the broker. Picking `puprime_standard`
  over the default `vantage_demo` moves the spread 0.22 → **0.32** because those are two different
  measurements — **using one broker's figure for the other overstates the cost by 45%.** (This
  paragraph said 0.33 until 2026-08-06; the figure was re-measured over 1,893,438 ticks and the
  code has been 0.32 since. The prose was the stale half.)
- 🔴 **A BROKER PROFILE CAN NOW REFUSE, AND A 500 HERE IS THE FEATURE WORKING (2026-08-06).**
  `backtest/fills.py` used to give all four PU Prime tiers the SAME spread and swap — both measured
  on a **Standard** demo, which is the one tier priced by a marked-up spread. So `puprime_ecn`
  charged ECN's commission on top of Standard's spread and swap: a cost model no real account
  offers, and **nothing errored**. The three unmeasured tiers now carry `SPREAD_UNMEASURED` /
  `UNMEASURED_SWAP` and raise `CostsNotConfigured` naming `algos/tools/broker_facts.py`. **So a run
  requesting `spread`, `bid_ask_fills` or `swap` on `puprime_prime` / `puprime_ecn` / `puprime_cent`
  now FAILS instead of returning a plausible wrong number.** ⚠ **`commission` on those tiers still
  works** — it is the one of the three a broker states unambiguously per lot, so the refusal is on
  the unmeasured COST, not on the tier. ⚠ **The swap half was measured, not assumed:** on ONE PU
  Prime account `XAUUSD.s` and `XAUUSD.crp` are the same market (median M15 close difference $0.08
  over 200 shared bars) with swaps **8.5x apart** and the short CREDIT gone entirely. Full record:
  `backtest/CLAUDE.md` and `docs/BROKER_QUESTIONS.md`. **If a lab run starts 500-ing on a raw tier,
  do not "fix" it by defaulting the spread — measure that account, or run without the layer.**
- **`bid_ask_fills` REPLACES the spread cost, never adds to it** (see the strategy's
  `_charge_spread`), and it is the only layer that can change which trades exist.
- **`GET /backtests/broker-profiles` exists so the Run modal never retypes a spread.** It serves
  `PROFILES` itself — the object the runner bills from. A number copied into a form is a second
  claim about what is charged, which is this lab's most-repeated defect.

Both `_cost_profile` call sites (single run and the optimizer sweep) inherit it, so the optimizer
cannot rank combos on one cost model and hand the winner to a run on another. ⚠ **Sweeps and stacks
do NOT write the columns yet**, so they land in the legacy branch and stay frictionless — correct
today (that is also the default), but wire them before anyone expects a priced stack.

Strategies are constructed through **`backtest.replay.build_strategy`**, never by calling the
class: `LAB_STRATEGY` is an open contract, so a strategy may predate the `cost_profile` kwarg, and
that helper **raises** rather than dropping a stated cost on the floor. Defaults on every request
model are now **0/0** (`models.py`), and `RunBacktestModal` resolves its primary ruleset across
BOTH the futures and forex lists — searching futures only is why a forex run's 0/0 ruleset default
never reached the form.

### Three numbers that were true and got misread

Auditing run `f866873aa862` found **no arithmetic wrong anywhere** — every stored KPI reproduced
from the raw trades, Sharpe included. What was wrong was what three headline numbers let a reader
conclude, and none was fixable by relabelling; each needed a companion that had never been
computed. All three live in `services/metrics.py`, are stored on `backtest_runs`, and are
backfilled onto history by `lab_db._backfill_run_shape_metrics`.

| stored | what it fixes |
|---|---|
| `max_drawdown_pct` | the drawdown was stored and LISTED in dollars only. $1.73M beside $14.4M of profit reads as ~12%; against the running peak it is **55.9%**. `BacktestDetail` always computed the percentage client-side — the RUNS LIST, which is where runs get compared, did not, and a list is exactly where a wrong order of magnitude does its damage. |
| `scratch_count` | the win rate counts a trade that made a cent as a win. 45 of that run's 111 "winners" made under a sixth of a typical loss, every one exiting at the breakeven-stop buffer — the stop doing its job, which is risk control and not an edge. Honest split: 40% won / 27% scratched / 33% lost. |
| `trade_concentration_pct` | `profit_concentration_pct` is the largest QUARTER's share — a question about time. Readers hear the question about TRADES, and the two can disagree completely: that run is 34.5% by quarter (spread evenly over 6.6 years) while **5 of 165 trades made 47%** of everything won. |

Three rules they share, and each is load-bearing:

- **All three weight by RETURN when the run compounded** (`_trade_weights`, the same
  `_equity_base` switch `profit_concentration_pct` uses). Dollars on a compounding account measure
  the compounding.
- **The scratch yardstick is the run's own MEDIAN full loss**, not a typed-in figure. For a
  fixed-risk strategy that median IS 1R, so the bar self-scales across strategies, instruments and
  account sizes with nothing to tune; the median rather than the mean so one outsized loss cannot
  move it. (It landed on the same 0.15 that `mpc_strategy.pine`'s own `exec_scratch_r` uses — not
  a coincidence, since 0.15 of the median loss and 0.15R are the same bar at fixed risk.)
- **`None` is never rounded to 0.** No losing trade means no scale to measure a scratch against,
  and `0` would read as "no scratches" — the opposite of "cannot tell". The backfill stamps
  `max_drawdown_pct = -1.0` for a run whose curve is missing, for the same reason
  `_restamp_profit_concentration` stamps `'dollars'`: a row left NULL is re-read on every startup
  forever.

**A high `trade_concentration_pct` is not a verdict.** A runner-based strategy is supposed to be
fat-tailed and this repo's stated design intent is few high-quality setups, so read it as "the
edge lives in the tail, size the risk for that" rather than as a defect. The frontend recomputes
both trade-shape metrics client-side (same rule as profit concentration — the stored value is
whatever basis was current when a run finished, and the news filter needs them over a subset).

**Backfill:** `scripts/backfill_metrics.py` recomputes the file-derivable columns (Sharpe trio, profit concentration + basis, contract status) on old runs — idempotent, only touches what's derivable from stored result files.

**Capital-based scores stay client-side** (BacktestDetail). Calmar / Max-DD-% need an account balance (the ruleset's `account_size` or the what-if slider); they're computed in the browser by rebasing the equity, never persisted, and never feed the verdict. **Both are measured against the RUNNING PEAK, not the starting balance (2026-07-30)** — the same defect `dd_basis` fixed for Monte Carlo, found in a second file: dividing a late dollar drawdown by a static `account_size` reported **1096.7%** and a red **Calmar 0.11** on a run whose honest figures are 54.9% and 2.25. If you add another percent-of-capital metric anywhere, the denominator has to grow with the account. Detail: `frontend/CLAUDE.md` → *Drawdown is peak-relative*.

---

## Foundational config (Pass 1)

Rulesets carry 10 foundational fields (risk %, halt fraction, consecutive loss limit, entry hours ET, days allowed, daily profit target, profit lock-in %, commission/side, slippage ticks), injected into strategy params at run creation by `runner_dispatch.inject_foundational()`. Detail is in git history (Pass 1).

**Standing rules:**
- **Category tagging:** every `[NinjaScriptProperty]` carries `[Category("Strategy Logic")]` (tunable, optimizer-visible) or `[Category("Foundational")]` (injected, hidden in UI). Legacy `[Display(GroupName = "Prop Firm")]` falls back to `"foundational"` via GroupName heuristic.
- **Dispatcher injection** happens at three creation points — `trigger_backtest()`, `trigger_sweep()`, `run_optimization()` — using the primary ruleset (first in `evaluate_rulesets`). Merged params stored in DB at creation so all retry paths pick them up without re-injection. **NinjaScript-only:** never inject for the `mt5` runner — foundational params map to `[Category("Foundational")]` properties MQL5 strategies don't have. Forex runs now carry a (personal) ruleset for *evaluation*, but `trigger_backtest()` forces `primary_ruleset=None` when `runner == "mt5"`, so no config is injected. **`run_native_optimization()` enforces the same gate** (`if firm and runner_str != "mt5"`): it previously injected NT8 foundational params (`AccountSize`, `EarliestEntryTimeET`, `DaysOfWeekAllowed`, …) into the MT5 optimizer's `.set` file regardless of runner, and MT5 treats a set file carrying inputs the EA doesn't declare as mismatched — silently running a single backtest instead of the optimization, so `opt_results.csv` is never written. See the set-file purity rule under "Runner dispatcher" below.
- **Primary ruleset rule:** only the first ruleset injects foundational config; others evaluate only. To test two rulesets' configs, run two separate backtests.
- **Sentinel guard:** strategies refuse to trade (warn + return) if foundational params are still at placeholders (-1 or empty string), catching dispatcher failures early.

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | SSH monitor + control. **One bot registered — `mpc_sos_fade_demo`** (this row said "none currently registered" until 2026-08-04; it has run since 2026-07-31). Global + per-bot controls, cap deploy, Telegram users. `GET /{bot}/version` reads the VPS deployment record (`deployed.json`) + git HEAD + the LIVE process's own `source_hash`, so the page reports what is RUNNING rather than what `config.json` intends; `POST /{bot}/promote[/preview]` stages, verifies and deploys. ⚠ **`BotStatus.mt5_link` is `Optional[bool]` and `None` means UNASKED** — a stopped bot, or one predating the field — so it is read `=== false` on the frontend, never falsy. Same rule as `mt5_connected` on the health strip, and for the same reason: rendering an unanswered question as a failure invents a measurement. It exists because `balance: None` is not a diagnosis — see the 2026-08-04 entry in `algos/CLAUDE.md`. ⚠ **Every kill goes through `_kill_bot`, which matches on BOTH `name='python.exe'` and `--bot <key>`** — never `taskkill /f /im python.exe` (that blanket kill takes out both backtest agents and the Telegram bot with it, and is what killed the live bot for three days in July), and never a bare commandline match either: without the process-name clause it matches the `cmd.exe`/`wmic.exe` running the command itself, and without the `--bot ` prefix it matches `promote.py` and `startup_coordinator.py`. Four per-bot routes built their own unscoped version until 2026-08-04; `tests/test_bot_kill_scope.py` now fails the build if a fifth appears. |
| Strategies | ✅ Live | Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. `run_count` (shown in the Strategies-tab Runs column) joins `backtest_runs` with `r.stress_test_id IS NULL` — same "real run" filter as `list_runs`, so hidden stress-test child runs don't inflate the count. **Strategy-level narrative** (`edge` TEXT, `steps` JSON) is overlaid from the companion `<Strategy>.meta.json` **top-level** `edge`/`steps` keys by `strategy_scanner._read_strategy_overview` and stored on `strategies`; drives the StrategyDetail Overview. UI-only (no source-hash impact). NULL-safe: a backfill migration sets `steps='[]'` and `Strategy.steps` has a `mode="before"` validator coercing `None→[]` (a NULL would otherwise fail the `list[dict]` response validation on `GET /strategies`). `.mq5` re-scans on meta mtime change; `.cs` only on source change. **`needs_scan`** (2026-07-23) — the scan-time twin of `needs_deploy`/`needs_compile`: `strategy_scanner.needs_rescan(row)` recomputes the on-disk source hash (Python = whole-package `_python_source_hash`; `.cs`/`.mq5` = file md5) + meta mtime and returns True when either diverged from what the DB last scanned, i.e. the param schema the Run modal shows is stale. Computed LIVE and enriched onto every row in `routers/strategies.list_strategies`/`get_strategy` (NOT stored — a circular import if `lab_db` computed it, and it must reflect disk right now). This is what surfaces the "Needs scan" pill so a Python strategy (which has no deploy/compile step) still tells the user to re-scan after a `config.py`/meta edit — the gap that let a run fire on the old divergence-armed defaults. |
| Rulesets | ✅ Live | CRUD at `/rulesets`. 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. 18 seeded rows (14 prop + 2 personal demo + `unconstrained` + `personal_forex_risk`). Prop rows locked server-side (PATCH/PUT 403); `PATCH` edits the 5 personal rule fields only (`PersonalRulesetPatch` extra=forbid + SQL allowlist). |
| Backtests | ✅ Live | NT8/MT5 runs via agent. Equity curve, daily P&L, per-ruleset verdicts, Worthiness tier (1/2/3). |
| Sweeps | ✅ Live | N sequential backtests across instruments (`_MAX_CONCURRENT = 1`). Cancel, retry-all, per-run retry. |
| Optimizations | ✅ Live | Native NT8/MT5 optimizer (one VPS job, full grid, all CPU cores). Scores by objective. `best_run_id` tracked. Source run nesting. Per-run retry. |
| System | ✅ Live | Health (SSH, NT8, MT5 agents). Log proxies. `POST /system/{nt8,mt5}-agent/start` fires schtasks. |
| Stress Tests | ✅ Live | MC (10k reshuffles + 1k bootstrap), walk-forward (IS/OOS windows), sensitivity (±10%/±25%). A–F grade. **Audited 2026-08-05** — child runs now carry the baseline's `cost_layers`/`broker_profile`/`sizing_mode`, a phase that ran and CRASHED is distinguishable from one never requested, `prob_pass_eval` is measured on the basis the grade reads, cancel actually cancels, delete removes the files, and unreachable params are not perturbed. See *Stress tests — the 2026-08-05 audit* |
| Regime Tags | ✅ Live | `backtest_runner.build_regime_timeline_and_tag()` classifies **every trading day in the run's window** once (via the existing `build_date_regime_map`), writes it to `reports/lab/<run_id>/regime_timeline.json` → `BacktestDetail.regime_timeline` `[{date, regime}]`, and tags `daily_pnl` from that same map (a P&L day with no bar carries the last classified day). Regime is a property of the MARKET on a date, not of a run — tagging only traded days left the equity charts banding off a sparse calendar, so two runs over the same window disagreed about the regime. Cheaper too: one classification per day, reused. Old runs: `scripts/backfill_regime_timeline.py` (opt-in — it fetches OHLC, so it's not in `backfill_metrics.py`). Optimizer `regime_filter` unchanged. |
| Strategy Files | ✅ Live | Upload/delete/compile `.cs` (NT8 F5) and `.mq5` (MetaEditor) files. Sync-status badges. |
| Strategy Deploy | ✅ Live | `POST /strategies/{id}/deploy` reads `source_path`, uploads to VPS. `.mq5` → MT5 agent, `.cs` → NT8 agent. |
| Param types | ✅ Live | `GET /strategies/{id}/param-types` parses `.cs`/`.mq5` source → `{paramName: "int"\|"double"}`. Used by optimizer modal to block decimal steps on integer params. |
| MT5 runner | ✅ Live | `mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. Runner dispatch via `runner_dispatch`. `/historical_data` maps M5/M15/M30 (was M1/H1/H4/D1 only), `symbol_select()`s before reading bars, **preserves symbol case** and tries the symbol **as given then its root** (terminals vary — GBPJPY is only `GBPJPY.s`, USDJPY both ways). `ohlc_fetcher._resolve_mt5_symbol` passes the run's broker symbol through; `chart_spec._capped_start` caps candle volume by trimming the WINDOW, never the timeframe. |
| MT5 deployment | ✅ Live | MT5 agent upload/delete `.mq5`. `POST /compile` → MetaEditor. Backend: `POST/GET /strategy-files/compile-mt5`. |
| MT5 native optimizer | ✅ Live | `mt5_agent.py` `POST /native-optimize` + `POST /native-walkforward`; `mt5_agent_client.py` typed wrappers. `runner_dispatch` dispatcher + `optimization_runner.run_native_optimization` route by `runner`. Native single-job `Optimization=1` run — MQL5 frame callbacks (`OnTesterInit/OnTester/OnTesterPass/OnTesterDeinit`) collect per-combo KPIs into `opt_results.csv`; the tester distributes combos across its local agents. **The EA MUST implement those callbacks** — without them the optimizer runs every pass but harvests nothing (single backtests work, optimization yields an empty CSV → "OnTesterPass may not have fired"). CSV columns must match `_parse_opt_csv` / `_OPT_KPI_COLS` (net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe[/gross_profit/gross_loss]) and the param column names must equal the grid keys. Combos rank on MT5's platform Sharpe (the native path has no `daily_pnl`, so canonical Sharpe isn't computed) — re-validate a winner with a single full backtest. |
| Python runner + optimizer | ✅ Live | `services/python_runner.py` — runs `strategies/python/` packages LOCALLY, in-process, via the top-level `backtest/` package (data cache → engine replay → `output.build_results`). No VPS, no agent, no compile. Scanner registers packages declaring `LAB_STRATEGY` (`strategy_scanner._parse_python_package`); the runner resolves by `strategy_class` = the strategy class's `__name__` — the same job-spec key NT8/MT5 use, locked by `test_python_runner.py`'s scanner↔runner agreement test. Optimizer: `runner_dispatch.start_native_optimization(spec, "python")` → `backtest/optimizer.run_sweep` fans combos across cores (lab still owns grid expansion + ranking — `expand_grid`, `objectives.py`). Sweeps run in bar mode; validate the winner in tick mode. Third lock scope: `has_running_python_job()`, surfaced through `get_running_job()`'s `python` bucket and consumed by the frontend's `lib/runner.ts` (wired 2026-07-16). Price charts AND regime tagging both read `ohlc_fetcher.get_ohlc(runner="python")` → `backtest.data.BarSource`, the SAME disk cache the run replayed, and deliberately never fall back to another feed: yfinance maps XAUUSD.s → GC=F, so a fallback would chart/label a spot-gold run off Yahoo's gold FUTURES daily bars. **Feature parity with the native runners is otherwise inherited, not re-implemented** — `run_backtest_job`/`_handle_complete` are runner-agnostic, so sizing (via `engine_trades`, which `backtest/output.py` emits), evaluations, worthiness, canonical Sharpe, regime tagging, the news/holiday filter (needs `entry_ms`, which the Python output carries) and stress tests all work unchanged. |
| Portfolio stacks | ✅ Live | `routers/stacks.py` + `services/lab_db.py` — layer 2+ **Python** strategies over ONE shared instrument/timeframe/window/cost profile to see combined P&L (summed client-side from each leg's `daily_pnl`; toggling a leg off never re-runs). **Smart reuse** (2026-07-25): on create, each leg that already has a COMPLETED standalone run at the EXACT same settings is reused as-is; only legs with no match are backtested fresh. `POST /backtests/stacks/preview` reports reuse-vs-run per leg without running anything (drives the modal's badges). See "Portfolio stacks (smart reuse)" below. |
| Telegram notifications | ✅ Live | `services/notify.py` — urllib Telegram sender, no extra deps. **No token in the source (2026-07-30):** env var, else the git-ignored `algos/credentials.json` read by path. `stress_tester` fires after grade is written. **`send_telegram(text, kind)` — the `kind` is REQUIRED and picks the chat (2026-08-05).** Every message this app sends is `HEALTH` (bot started/stopped/restarted/promoted, runtime params applied, stress test finished); none is a fill, because only the bot on the VPS can know a trade happened — and `tests/test_notification_routing.py` **refuses a `TRADE` here by test**, as well as greping every sender for a stated kind. ⚠ **This is a SECOND implementation of `algos/shared/notify.py`'s routing table**, which the subsystem boundary requires (shared FILE, never a shared import); the two are pinned together by routing on the same credential keys, checked by a test that reads that file. **`services/alert_format.py` (2026-08-05) is the same arrangement for the message SHAPE** — `<icon> <LABEL> · <subject>` then grouped facts then what to act on, plain text, and **no timestamp** because Telegram already prints the send time in each reader's own local clock. `algos/tests/test_alert_format.py` loads this app's copy BY PATH and asserts both files render byte-identical output, including the cases where two hand-written copies diverge first (an absent fact, a whitespace-only one). |
| Live calendar tab | ✅ Live | `routers/calendar.py` (`GET /calendar?from&to`) → `services/calendar_service.py` → `engines/news/` `TradingViewSource.fetch_window()` (never a 2nd impl). Returns the whole week's events unfiltered + `server_now_ms` (drives the frontend "now" line off the server clock); 60s in-memory cache; beat/miss `surprise` computed server-side (`_LOWER_IS_BETTER`). Read-only — does NOT write the shared EventStore cache (separate path from the post-run news filter). Feed only, no DB. |
| History floors | ✅ Live | `services/history_limits.py` + `GET /backtests/history-limit`. Refuses (400) any backtest window starting before the broker's REAL history for that timeframe — MT5 silently substitutes coarser bars, which would produce a plausible but fictional run. Floor is MEASURED off the live terminal (probed by bar density, cached per broker) via the canonical `backtest/data/history.py`, so a broker swap re-measures instead of inheriting. Enforced at run / retry / sweep / optimization / stack, and again in `BarSource.load`. Python runner only. |
| Settings | ✅ Live | Config read/write. `nt8_agent_tunnel` and `mt5_agent_tunnel` both present. |
| Startup — agent supervisor | ✅ Live | `services/agent_supervisor.py` — 60s loop, guarded on the per-platform job lock. Replaces the one-shot startup thread. See *The agent supervisor* below. |
| Startup — readiness report | ✅ Live | `services/readiness.py` — one boot-time line per silently-degrading dependency; `GET /system/readiness`. |

---

## The agent supervisor — and the two indicators that were lying

**Added 2026-08-02. `services/agent_supervisor.py`.** Replaces `main._auto_start_agents`, a one-shot
thread that ran 8 seconds after boot and never again: it worked on a cold start and did nothing for
every case after it, which is why the MT5 agent had to be started by hand after every laptop sleep.
There is no separate startup path now — the first pass is the same pass as every later one, so
"it works on launch" and "it recovers from sleep" cannot diverge.

**Two probes, because `ssh -L` binds the local port ITSELF.** A TCP connect to 127.0.0.1:8766
succeeds for as long as the ssh process holds the forward, whether or not anything is alive at the
far end. That gives two independent signals, and the pair is what tells the failures apart:

| ports bound | agents answering | diagnosis | action |
|---|---|---|---|
| neither | — | the tunnel is dead (laptop slept) | rebuild it |
| both | **neither** | stale tunnel forwarding into nothing, **or** both agents really down | rebuild, then fire both tasks |
| both | one | the tunnel is fine | fire that agent's task only |

🔴 **The old health check answered neither question.** `_check_ssh` ran `ssh forexvps "echo ok"` — a
BRAND NEW connection that has nothing to do with the forwards — and that is what the sidebar's "SSH"
dot reported. So after a sleep the dot sat green beside two red agent dots, which sends you to the
VPS when the problem is on the laptop. `SystemHealth.ssh_tunnel` now measures the forwards;
`vps_reachable` is a new field carrying the old question, and it is what separates a dead tunnel
from a dead network. (The agent-start endpoints already rebuilt the tunnel before firing a schtask —
the workaround was in the code, the indicator just could not say so.)

🔴 **`/health` on the MT5 agent is not a statement about MT5.** It returns `ok` if Flask is alive,
which it is whether or not the terminal is running or logged in — so an MT5_Lab that had dropped its
broker connection showed a green dot and every python run needing uncached bars failed at fetch time
instead. `mt5_agent_client.status()` wraps the agent's `/status` and health now carries
`mt5_connected` / `mt5_server` / `mt5_account`. **`mt5_connected` is `Optional[bool]` and `None`
means the agent could not be asked** — an unanswered question is not a disconnected terminal, and
rendering it as one invents a measurement. The terminal is not probed at all when the agent is down.

**The guard is the point, not the loop.** Every action is skipped when the scope it would disturb
has a job running (`lab_db.get_running_job`), and a **python run counts as MT5 traffic** — the local
runner pulls its bars through port 8766 (`backtest/data/mt5_agent.py`), so restarting the tunnel
mid-fetch kills a run that never touched the VPS directly. `busy_scopes()` returns **all three
scopes** when the DB cannot be read: doing nothing is always safe, and the wrong guess in the other
direction kills a live run.

**One deliberate asymmetry, and it is not an oversight.** An **unbound** port is rebuilt even under a
running job — nothing can connect, so every call that job makes is already failing and rebuilding is
its only route back. A merely **stale** tunnel (ports bound, agents silent) is not, because that
reading has a real false positive: an agent driving a heavy backtest stops answering `/health` while
working perfectly. The NT8 agent does exactly this under pywinauto.

**`schtasks /run` is not evidence.** It reports SUCCESS for a task Windows refuses to launch (see
`algos/CLAUDE.md` → the stored-password trap), so every fire is followed by a re-probe and the
outcome is logged either way — `nt8-started` or `nt8-fired-but-still-down`. Silence after a fire
used to read as success.

⚠ **It will not rescue an agent whose death left a job marked `running`.** "Dead" and "busy driving
my job and too loaded to answer" are indistinguishable from here, and the wrong guess kills a live
run — so the skip NAMES the deadlock (`nt8-DOWN-with-a-job-running (lock held by nt8 — Stop it or
restart the backend)`) rather than retrying silently forever. Observed live on 2026-08-02: the NT8
agent died on a backtest submission, the run row stayed `running`, and the loop correctly refused to
touch it. Clear the lock and the next pass restarts the agent by itself.

⚠ **The supervisor is DISABLED under pytest** — `CC_DISABLE_SUPERVISOR=1`, set at module scope in
`tests/conftest.py` (a fixture runs too late; `main` is imported at collection). Every endpoint test
builds a `TestClient`, which fires the startup hook, so without the guard a plain `pytest tests/` on
a laptop whose tunnel happened to be down would rebuild the tunnel and fire two scheduled tasks on
the live VPS. Same class of hazard as `tests/test_integration.py`, and refused by default for the
same reason.

🔴 **And a task that CANNOT start is not the same as a task that failed — that gap left the NT8
agent dead for two days (fixed 2026-08-06).** An agent process can be **alive with its socket
dead**: the PID is in the list, nothing is listening on its port. Windows then refuses to launch a
second instance of a task whose first one is still running (`0x800710E0`, *the operator or
administrator has refused the request*), so **every fire is a guaranteed no-op** and the loop
logged `nt8-fired-but-still-down` once a minute, indefinitely, while reporting a real action each
time. **Measured on the live box: PID 13396 alive since 2026-08-04 02:59 UTC with nothing bound to
8765.** The sidebar's Start button fires the same task and was equally unable to recover it — so
this was not a supervisor gap, it was the *only* recovery path in the app being a no-op against
this failure mode. The loop now kills the corpse and re-fires once: `nt8-wedged-process-killed` →
`nt8-restarted-after-kill`, or `nt8-still-down-after-kill` when the second fire is honest about
failing too.

⚠ **`kill_agent_process` is the two-clause `wmic` match and both clauses are load-bearing** — the
same rule `routers/bots.py::_kill_bot` documents, and the reason `taskkill /f /im python.exe` is
banned repo-wide. `name='python.exe'` alone would kill every python process on the box **including
the live trading bot**; the `commandline like '%nt8_agent.py%'` clause alone matches the `cmd.exe`
/ `wmic.exe` hosting the very command being issued, whose own commandline contains the script name
— i.e. the kill terminates the process running it. Verified against the live box on 2026-08-06:
the match resolved to one PID while the trading bot (9620), the MT5 agent (5392) and both Telegram
processes were untouched.

⚠ **wmic's exit code is not evidence, the OUTPUT is.** It prints `Method execution successful` per
matched process and `No Instance(s) Available.` when nothing matched, and neither reaches the exit
code — so `kill_agent_process` returns True only on the success string. **Nothing to kill is a
DIFFERENT diagnosis and is logged as one** (`fired-but-still-down (no process to clear)`): it means
the task genuinely never started, which is the stored-password trap or a missing interactive
session, and a second fire would not fix that either.

⚠ **The kill is safe here and would not be one branch earlier.** It sits after the busy-scope guard
has already returned, so no job is running in that agent's scope. Killing an agent that is merely
*too loaded to answer* is precisely the repair-at-the-wrong-moment this module exists to refuse.

**Tests:** `tests/test_agent_supervisor.py` (25) + `tests/test_system_health.py` (12). Most of them
are about what the supervisor REFUSES to do — the dangerous failure of a supervisor is not a missed
repair, it is a repair at the wrong moment. The six added with the wedged-agent path are that shape
too: three are about what the kill must NOT reach.

## The calendar's polarity list was written for the wrong provider

🔴 **Fixed 2026-08-05.** `calendar_service._LOWER_IS_BETTER` decides which way a released `actual`
is coloured — green when a LOWER print is the good one (inflation, unemployment), red otherwise. It
was a flat lowercase-substring list, and **it had been written against Forex Factory's naming while
this tab reads TradingView.**

**MEASURED against the live feed, 811 distinct real titles over ~275 days: six of its eleven keys
matched ZERO of them** — `initial claims`, `continuing claims`, `crude oil inventories`,
`gasoline inventories`, `natural gas storage`, `producer prices`. TradingView calls those
*Initial Jobless Claims*, *EIA Crude Oil Stocks Change*, *EIA Natural Gas Stocks Change* and *PPI*.

⚠ **A dead key costs nothing visible, and that is what makes it dangerous — the damage is what it
leaves UNCOVERED.** The worst case was **`Core PCE Price Index MoM` — HIGH impact, USD, the Fed's
own preferred gauge** — which matched nothing and fell through to the default higher-is-better. So
a 0.4% actual against a 0.3% forecast printed **green "beat" on PCE and red "miss" on CPI**, rows
apart in one table, answering one question. Pinned now by
`test_the_two_inflation_prints_agree_with_each_other`.

**The fix that matters is not the added keys, it is the guard.** `tests/test_calendar.py`
parametrises over `_LOWER_IS_BETTER` and **fails the build on any key that matches nothing** in
`tests/fixtures/tradingview_titles.txt` (the harvested corpus). The list is a CLAIM about one
provider's vocabulary, and a claim nothing checks is this repo's most-repeated defect — here in its
quietest form, because a wrong polarity renders a confident colour rather than an error. ⚠ **If
that test fails, the feed renamed an event: find what it calls it now, do not delete the key.**

⚠ **Keys are matched at a word boundary on the LEFT and openly on the RIGHT.** The left boundary
stops `ppi` matching *Shipping* / *Shopping* (theory rather than a live bug — zero real titles hit
it — but the next key added may not be so lucky). The open right end is what lets one key cover a
family: `inflation` alone covers *Inflation Rate*, *Core Inflation Rate*, *Michigan Inflation
Expectations*, *Food Inflation* and *TD-MI Inflation Gauge*.

⚠ **Every key in the shipped list matches real titles today** — candidates that read well but match
nothing (`unemployment change`, `bankruptcies`, `foreclosure`) were written, measured, and removed
rather than left in as aspiration. That is what keeps the dead-key test meaningful.

Two smaller fixes in the same pass:

- **Upstream failures are classified at one seam** (`_fetch`, blanket `except Exception` →
  `RuntimeError` → the router's 502). The source only converts `HTTPError`/`URLError`, so a non-JSON
  body raised **`json.JSONDecodeError` — a subclass of ValueError — which the router maps to 400**,
  reporting somebody else's outage as a malformed request; and a read timeout raised `TimeoutError`
  (an OSError, not a URLError), which escaped both handlers and became a bare 500. Neither is
  visible to the reader, which is why both survived. **`ValueError` out of this module must mean
  "the caller asked for something impossible", and nothing upstream can be that.**
- **The cache is bounded (64) and locked.** The key is the exact `(from, to, countries)` triple, so
  every week a reader pages to minted an entry nothing ever removed; and two readers landing on one
  uncached week each hit TradingView, since the endpoint runs in FastAPI's threadpool.

✅ `_MAX_SPAN_MS` (60 days) was checked rather than assumed: a 60-day window returns ~1,495 events,
inside the provider's ~2,000 cap, so no window the router accepts can be silently truncated. (105
days returns exactly 2,000 — truncated — which is what the guard is for.)

**And the chip roster is served rather than restated (`GET /calendar/currencies`, same day).** The
page's currency chips were a hardcoded nine sitting beside a comment saying they mirrored the
backend — a second statement of the same claim, which is the disease this whole audit is about, in
its mildest form: **the two are not even the same namespace.** TradingView is QUERIED by bloc code
(`US`, `EU`, `GB`) and ANSWERS with an ISO currency (`USD`, `EUR`, `GBP`), so the frontend could
never have derived it, and a tenth bloc added to `DEFAULT_COUNTRIES` would simply never have got a
chip — a currency present in the data and absent from the filter, which reads as a quiet week.
`calendar_service._COUNTRY_CURRENCY` is the one place the two namespaces meet. ⚠ **An unmapped code
falls back to itself** (a chip matching no event — visibly odd rather than silently absent), and the
build fails first: `test_every_queried_country_maps_to_a_currency` plus
`test_the_roster_is_the_currencies_the_feed_actually_returns`, which checks the roster **against the
811-title corpus in both directions** — no currency in the corpus without a chip, no chip for a
currency the feed never returns. Same guard shape as the dead polarity key, for the same reason.

## Readiness — the checks whose failure mode is silence

`services/readiness.py`, reported once at boot and served at `GET /system/readiness`. The supervisor
above watches things that announce themselves; this covers the opposite class — dependencies whose
absence produces no error anywhere, just a feature that quietly does nothing:

- **An un-backfilled news calendar makes the News & Holiday filter INERT.** The engine reports
  `has_coverage=False` outside the fetched range and tags nothing, so a correctly-wired filter over
  an unbackfilled period is indistinguishable from a broken one. The cache is git-ignored, so a
  fresh clone starts empty and every machine backfills its own. A cache that STOPS partway is the
  nastier case and is reported with the date it ends — recent trades come back *untagged, not
  unaffected*.
- **Missing `algos/credentials.json` makes every Telegram send a no-op.** Deliberate (a notifier
  must never be able to stop a trading loop) and it means a stress-test grade can finish with
  nobody told.

It **reports and does not act** — neither is repairable from here, and neither is worth refusing to
boot over. `_news_calendar()` catches everything: it runs inside the startup hook, and an exception
there would stop the backend booting over a git-ignored cache file.

## A unit test may not reach the VPS, and now it cannot

**2026-08-05.** `tests/conftest.py`'s `client` fixture has said *"all outbound VPS calls
stubbed"* since it was written, and it was not true: `list_strategy_files` was unstubbed on
both agents, so `GET /strategy-files/sync-status` really did call the NT8 agent over the live
SSH tunnel. **The test around it passed whenever the box happened to be up** and 502'd
otherwise — green on the machine with the tunnel open, red on a fresh clone or after a laptop
sleep, and pointing at the wrong thing either way.

`_no_live_vps` (autouse) covers **both channels the backend can reach the box on**, and a
test that legitimately needs one stubs the specific function above it, whose patch wins.

**HTTP** — `_get`/`_post` on both agent clients raise a message naming the fix. Those four
are the whole surface; every agent call funnels through them.

**SSH** — there is no funnel. `routers/bots.py::_ssh` is one, `services/agent_supervisor.py`
shells out three more times on its own (`restart_tunnel`, `schtasks_run`, `vps_reachable`),
and the next module to need the box will shell out again. So the guard sits on
`subprocess.run`/`Popen` themselves and decides **per-argv** — refuse when the program is
`ssh`/`scp`/`sftp`, or when `cfg.SSH_ALIAS` appears anywhere in it. That second clause is not
redundant: `restart_tunnel` opens with `pkill -f "ssh -N.*forexvps"`, whose program is not
ssh, and which would **kill the developer's own tunnel from inside a unit test**. ⚠ Everything
else runs for real — `_git_commit_push` really does shell out to git, and a blanket ban on
`subprocess` would be easier to write and would test nothing about the VPS. ⚠ Tests marked
`integration` are exempt; driving the live box is their whole job.

🔴 **The guard raises `LiveVpsCall(BaseException)`, and that is the load-bearing detail.**
Every probe on this path catches `Exception` and reads the failure as *the box is down* —
`vps_reachable`, `_agent_ok`, `schtasks_run`, and six bare `except Exception: pass` blocks in
`routers/system.py::_build_health`. **An `AssertionError` guard is swallowed by exactly the
code it is meant to police**: the call is still made, the caller reports "unreachable", the
suite stays green. ✅ **Measured rather than argued** — with the vps_reachable stub removed
from `test_system_health.py`, an `Exception`-based guard left **11 of 12 tests passing while
every one of them opened a real ssh connection**; the `BaseException` version fails 6 of them
by name, printing the exact argv. **This is the repo's own probe rule arriving in the test
harness: a check that cannot fail where the failure happens is not a check.**

⚠ **The interlock is autouse, so its failure mode is silence — a guard that never fires and a
guard that was never installed look identical from a green suite.** `tests/test_vps_interlock.py`
(13 tests) drives it directly: the classifier both ways, the four real call sites, that a stub
still wins, and that `LiveVpsCall` is **not** an `Exception` — pinned on its own so a future
tidy-up fails there instead of quietly disarming the whole suite.

**Same pass, the stale roster:** `EXPECTED_CLASS_NAMES` in `tests/test_strategies.py` still
listed `MpcBosStrategy`, three tests deep, after `1946f8b` deleted the unfinished port. That
commit's message says "and its roster line with it" and means `backtest/tools/run_report.py`,
which it correctly called "the ONLY live reference" — this is a SECOND roster, in another
subsystem, and it went unnoticed for a day. ⚠ **A roster stated once per file is still stated
N times across the repo: when you delete a strategy, grep the CLASS NAME, not the package
path.**

## Stress tests — the 2026-08-05 audit

**Read this before touching `services/stress_tester.py`, `services/grading.py` or the stress-test
half of `lab_db.py`.** The frame is one query: `SELECT count(*) FROM stress_tests` returned **1**,
and that row was written **2026-07-27 — three days before the accuracy pass** that replaced the
shuffle series, the drawdown basis, the sensitivity metric and the walk-forward floor. So the
feature had been driven end to end exactly once, against an engine that no longer exists, and
nothing had re-scored the row since. It carried a confident **D** for over a week; re-scored
through the live backend it is **ungraded**, with both probabilities NULL and sensitivity
0.858 → 0.205.

### Driven against the live backend, because a page nobody has run is not a page anybody has tested

That is the whole reason this list exists, so the fixes were driven rather than reasoned about — a
real stress test on a real **charged** 161-trade XAUUSD M15 baseline (`spread`+`swap`,
`vantage_demo`), walk-forward and sensitivity both on.

- **Every child carries the baseline's physics.** All of them, walk-forward and sensitivity alike,
  in ONE group: `["spread","swap"] / vantage_demo / consistent`. Under the old code that group
  would have been `NULL / NULL / consistent`.
- 🔴 **And the charge is REAL, which is a separate claim and needed its own measurement.** Carrying
  a field proves nothing about whether anything downstream reads it, so a walk-forward child of a
  charged baseline was re-run FREE over its own window and params — the body the stress tester used
  to send:

  | `wf_1_is`, 2020-01-01 → 2022-04-22 | charged | free |
  |---|---|---|
  | trades | 51 | **51 — identical** |
  | profit factor | 1.463 | 1.612 |
  | net P&L | $69,838.19 | $108,443.55 |

  **The identical trade count is the check that says the charge is correctly placed** — spread and
  swap change what a trade MAKES, never whether it happens, so a moved count would mean something
  else had changed. That $38,605 is what the old code reported as the strategy's out-of-sample
  behaviour while its parent was measured charged. The same pair on the full-history baseline
  itself: **159 trades either way, PF 3.942 → 3.668, $34,877,368 → $13,012,425.**
- **`phases_requested` is readable while the test is still running** — `["monte_carlo",
  "walk_forward", "sensitivity"]` at `running_sens`, so the page's pipeline stepper draws all three
  with per-phase elapsed (MC 1s, WF 1m 31s, sensitivity in flight). It was NULL until the very end.
- **The walk-forward numbers are the counterpart of the stored row, which is what makes them
  useful.** That row ran 5 windows and closed **6** out-of-sample trades in every one — under the
  20 floor, i.e. a degradation figure with nothing behind it, and the page could not say so because
  the field was stripped by the model. This run at 2 windows closes **30**, and the page reads
  `all windows have enough` beside IS 0.90 → OOS 1.70. `walk_forward_feasibility(161, w)` predicted
  it: OK at 2, infeasible at 3 (16 OOS), 5 (10) and 8 (6).
- **Cancel stops the work, and it was pressed against a real running test rather than a fixture.**
  A sensitivity phase 16 children deep returned `job_stopped: true` with 1 in-flight child cancelled,
  then sat at **16 children for 120 seconds** with the status holding at `failed_cancelled` — never
  overwritten by `complete`, which is what the old code did on the way out. **Both locks released
  immediately**: `running-lock` `{futures: false, forex: false}` and the python bucket of
  `running-job` free. Before this, the row said cancelled while the sweep kept every core and the
  per-platform lock reported the platform idle, so a second job could start on top of it.
- **Delete removes the files**: `reports/lab` 216 → 192 directories on a real delete, rows gone, and
  a dirs-vs-runs diff afterwards shows **no orphan dated today**.
- ✅ **The pre-existing backlog was cleared too, at Aaron's request: 109 orphaned directories,
  7.9 MB** — 92 stress-test children whose parent was deleted before this fix, 13 `opt_*` combos,
  and 3 sizing-pipeline test fixtures (`t_consistent`, `t_bullet`, `r2`). They are the
  "191 directories against 84 live runs" the audit opened with. **`reports/lab` is now 82
  directories and a dirs-vs-rows diff is CLEAN in the orphan direction (0).** ⚠ **The orphan set is
  computed against `backtest_runs` UNION `stress_tests`** — a test's own directory holds its
  `equity_paths.json` and is referenced by no run row, so diffing against runs alone would delete
  live data. ⚠ **Three ROWS legitimately have no directory** (`equity_curve_path` empty, never
  written); that is the opposite condition and is left alone.
- **Sensitivity skips what it cannot reach**: 3 of 17 numeric non-foundational params on this run
  are behind a switch it has off, so 12 backtests that could only reproduce the baseline are not
  run, and the coverage says so.
- ✅ **A full sensitivity phase finished, which is what "driven end to end" finally means here.**
  `status: complete`, grade **D** with real reasons ("Median simulation is profitable but median
  drawdown breaches the limit" / "55% probability of breaching ruleset limit at some point"), and
  `sensitivity_coverage` populated on real charged data: **12 params perturbed, 46 shifts run, 0
  failed, 14 skipped and NAMED** (`exec_tp1_pct`/`exec_tp2_pct` sit at 0.0 so every shift lands
  back on 0; `div_pivot_len ±25%` rounds onto values already run) **and 3 params unreachable and
  named**. `phase_failures` is `{}` — empty, and distinguishable from null.

⚠ **The drive killed its own test TWICE, and the pair is the cleanest proof the
`phases_requested` fix was needed.** The backend is served with `--reload`; a `.py` edit landed
while a test was in flight and `reset_stale_stress_tests` correctly marked it `failed_crashed`.
**The first time — before the fix — the row recorded `phases_requested: NULL`, so nothing anywhere
said what that test had been asked to do.** The second time, after the fix, the same crash left
`["monte_carlo", "walk_forward", "sensitivity"]` on the row. Same failure, same recovery path, and
the difference is the whole point: a record written at the END does not survive the failures it
exists to describe. ⚠ **Do not edit backend source while a stress test is running** — a `.md` edit
is safe (uvicorn's reloader watches `*.py` only), a docstring is not.

⚠ **What this audit did NOT verify live, stated so it is not mistaken for measured: the NATIVE
walk-forward path (optimizer-derived, profit-factor based), the MT5 and NT8 runners, and the worker
pool's peak memory.** Everything driven here was the **python** runner, which is Aaron's stated
focus for this feature (2026-08-05) — so the native paths keep their unit tests and are deliberately
not on the critical path. The memory figure is simply missing: the sample was taken after the pool
had already torn down, which measures nothing. **Do not read any of the four as checked.**

### A child run must be measured on the BASELINE's physics

🔴 **`run_walk_forward_task` and `run_sensitivity_task` built a job spec carrying the window, the
params and the legacy `commission_per_side`/`slippage_ticks` — and no `cost_layers`, no
`broker_profile`, no `sizing_mode`.** `python_runner._cost_profile` reads those off the spec, so
stress-testing a run that charged spread and swap measured **every child on a free book**. On
walk-forward that makes the IS→OOS comparison a comparison against a run neither half resembles;
on sensitivity it is worse, because the score is `|child_pf − baseline_pf| / baseline_pf` and the
baseline PF came from the CHARGED parent — **so the cost gap was reported as the parameter's
fragility, on every single shift.**

`child_measurement_fields(source_run)` is the one seam, spread into both specs and into the child
row. ⚠ **`cost_layers` goes through `_json_list`** — it is stored as raw JSON TEXT, so handing the
string on iterates its CHARACTERS; the same trap `/runs/{id}/repriced` hit on 2026-08-03. ⚠
**`null` is forwarded as `[]`**, for the reason the tune page states: `null` means "written before
layered costs existed", which is not a contract a NEW run can be created under.

**This is the third launcher in this app found carrying the window but not the physics** (the Run
modal's costs, the Optimize modal's params, the tune page's `cost_layers`). The rule is now
general: **anything that creates a child run for COMPARISON must carry everything that decides
what a run is measured on.**

### "It never ran" and "it ran and crashed" were the same value

🔴 **A phase that crashed left its summary NULL, and grading reads a NULL summary as NOT RUN** —
explicitly unpenalised, with a caveat printed saying so. **So a walk-forward whose every backtest
failed cost the test nothing and could be handed an A carrying the words "walk-forward not run".**

Both phase tasks return `(ok, err)` now, and `phases_requested` / `phase_failures` are stored.
`compute_grade` takes `wf_failed=` / `sens_failed=`: a failed phase is neither credited nor
described as absent, and `genuinely_not_run` replaces the old `walk_forward is None` at both
caveat sites.

⚠ **`phases_requested` is written when the ROW IS INSERTED, not when the task finishes** — the only
point that cannot be missed. Written at the end it is absent for a test's entire life, so the page
has to infer which phases are coming, and **a task killed mid-flight leaves no record of what was
asked for at all.** That is not hypothetical: the backend reloaded under a live test during this
audit and left exactly that hole. `phases_requested(include_wf, include_sens)` in `stress_tester`
is the single definition, used at creation and again at the end. ⚠ **NULL still means "written
before this was recorded"** and the page falls back to inferring — `["monte_carlo"]` would be a
positive claim that nothing else was requested.

🔴 **The native walk-forward path failing left the test with no walk-forward at all.** It now falls
through to the serial path rather than reporting nothing; `failed_periods` is tracked, and a
missing curve gives `sharpe = None`, never `0.0` (which reads as a measured flat window).

### Sensitivity runs its shifts in PARALLEL

🔴 **The phase replayed 60 full-history backtests ONE AT A TIME on a 12-core box, while
`backtest/optimizer.run_sweep` had been fanning optimizer grids across every core the whole time.**
Aaron asked why it was slow when the bars are cached — and the cache was never the bottleneck.
MEASURED: **69s per child, 65–71s across children.** That tightness is the tell — it is compute
(an engine replay stepping ~165k bars in Python), not I/O.

⚠ **The obvious fix does not work, and it would have looked like it did.** Wrapping the loop in
`asyncio.gather` with a semaphore is the natural move, but `python_runner.start_backtest` runs each
backtest on a THREAD and the replay is pure-Python bar-by-bar, i.e. **GIL-bound** — N threads buy
almost nothing while appearing to be a fix. It needs PROCESSES.

`_run_shifts_pooled` submits the whole shift set as ONE sweep job. Rules that hold it together:

- **It goes through `runner_dispatch` → `python_runner`, never `run_sweep` directly**, because
  `_cost_profile` lives there. A second caller building its own cost profile is precisely how the
  children came to be measured on a free book in the first place. `python_runner` gained a
  `param_sets` passthrough for it — sensitivity is ONE-PARAM-AT-A-TIME, and `expand_grid` would
  return the CARTESIAN PRODUCT of the same shifts, a different and far larger experiment.
- **Python only, and that is not a limitation to lift.** NT8 and MT5 each drive one physical
  terminal; there is nothing to parallelise on, and firing concurrent jobs at a single Strategy
  Tester would be actively harmful. They keep `_run_shifts_serial`.
- ⚠ **Rows are matched back by `(param, value)`, NEVER by index.** `run_sweep` ends with
  `[r for r in results if r is not None]` — it COMPACTS on cancellation — so a cancelled sweep
  returns fewer rows than combos and index-matching would hand one shift's profit factor to a
  different parameter, silently. `sensitivity_plan` dedupes values per param, so the pair is unique.
- ⚠ **A shift the sweep did not return is FAILED, never a complete row with zero KPIs** — a zero
  scores as "this parameter does nothing", the most reassuring answer available for a measurement
  that never happened.
- ⚠ **Pooled children carry KPIs but no equity curve or daily P&L**, because a sweep worker returns
  KPIs only. Nothing reads a sensitivity child's curve (scoring uses profit factor and net P&L, and
  the UI never navigates to one), so the paths are NULL rather than pointing at files that do not
  exist, and no canonical Sharpe is computed — there is no daily series to compute one from.

✅ **PROVEN, and the correctness check mattered more than the speed one.** The same shift
(`sens_aplus_window_+25%`) was run through the pool and then re-run down the single-run path:
**161 trades, PF 3.268, $12,184,685.53 — identical to the cent both ways.** A 4x speedup that
quietly moves a number is worse than the slow version.

**MEASURED end to end: 46 shifts in 841s (14 min) against ~3,174s (53 min) serial — 3.8x.** ⚠ **Not
the ~10x the core count suggests, and the gap is worth knowing**: `default_workers` deliberately
leaves a core free (this runs inside the backend serving the UI that reports its progress), and the
~165k-row frame is pickled to each worker at pool start.

**`_estimate_sens_duration_min` was recalibrated in the same pass and was wrong twice over.** It
used a flat `_mins_per_job` of 0.2 min for python — true for a short backtest, 6x optimistic for a
6.6-year replay — and it summed serially. It now takes the SOURCE RUN's own measured duration (the
same reasoning the optimizer modal's estimate uses; a per-job constant is wrong by construction
because the cost scales with the window) and divides by the worker count. Quoted 13 min for the run
that took 14, against the old code's 12 for a 53-minute job. ⚠ **`started_at`/`completed_at` are
read `is not None`, never truthily** — a timestamp of 0 is a value, and `if started` silently
dropped it back to the constant. A test caught that, not review.

### Sensitivity: what was NOT tested is part of the answer

🔴 **A param behind a `show_if` switch this run has OFF was perturbed anyway**, and every shift
reproduced the baseline exactly — 3 of 17 numeric non-foundational params on the measured run, i.e.
**12 backtests that could not tell you anything.** `param_is_reachable` mirrors `ParamEditor`'s own
`show_if` rules (single value or array, stringified comparison) and `perturbable_params` is the one
roster, shared with the router's estimate so the two cannot drift.

🔴 **`shifted_value` REFUSES a shift past the param's own `min`/`max` rather than clamping it.** A
clamped shift is a duplicate of the bound, scored as though it were the ±25% case — a measurement
of a different question wearing the right label.

⚠ **`coverage` is stored and rendered.** A silent skip reads as coverage that never happened, which
is the same defect as the zero bar for a failed shift, one level up.

### Monte Carlo, cancel, delete

- **`prob_pass_eval` is measured on the basis the grade will read.** It was computed against the
  dollar limit while `prob_breach` had switched to percent, so on a compounding run the two
  contradicted each other. Measured on a synthetic compounding fixture with a 60%-of-account limit:
  old = 0.0% breach / **31.2%** pass, new = 0.0% / **100%**.
- **`distribution["max_dd_pct"]` exists exactly when the percent basis does**, so the histogram is
  labelled in the unit it was measured in and never invents one.
- **`_split_windows` starts out-of-sample the day AFTER in-sample ends.** The two halves shared a
  boundary day, so one day's trades were in both.
- 🔴 **Cancel now cancels** — `POST /{id}/cancel` marks the row, returns its running children, and
  cancels each through `runner_dispatch`, reporting `job_stopped` separately (the row is cancelled
  either way; "we told the runner" and "we could not reach it" are different facts). Every phase
  checks `is_cancelled` between children, and a cancelled test is not graded.
- 🔴 **Delete removes the files.** It returned a bare bool and the router did nothing else, so every
  child left its `reports/lab/<run_id>/` behind — which is how that directory reached **191 entries
  against 84 live runs**. It returns the child ids now and the router rmtrees the test's own dir and
  each child's. Measured live: 216 → 192.
- 🔴 **`asyncio.create_task` was called with no strong reference.** The loop only holds a task while
  one of its callbacks is scheduled, so a long-awaiting background task is collectable and can
  vanish mid-flight, leaving the row `running` for ever. `_BACKGROUND_TASKS` holds one.
- **`update_stress_test_mc` takes `next_status`.** It hardcoded `complete` even with phases still to
  come, so the market lock (`status LIKE 'running%'`) RELEASED in that gap and a crash inside it left
  a permanently `complete` test `reset_stale_stress_tests` cannot see.
- **A results file that is present-and-unreadable is a different fact from one never written**, and
  both arrived as `None`. `results_error` names it.

### The migration

`GRADE_ENGINE = 3` + `_restamp_stress_tests()` in `init_db`, idempotent and stamped so it runs once.
It rebuilds each stored test's walk-forward and sensitivity summaries under today's rules and
re-grades. ⚠ **It may only RE-DERIVE from stored inputs — it never re-runs a backtest** — so a row
whose child data is gone is left alone rather than being given a number nothing measured.

---

## A bot's VERSION — the number the page showed was never written (2026-08-07)

🔴 **The Configure tab's version row read `v0`, and it always would have.**
`BotDeployedVersion.strategy_version` comes from `deployed.json`, which `promote.py` copies from
`live_config.LiveConfig.strategy_version` — an int that defaults to **0** and that **no code path
in this repo assigns**. So the card read `v0` before a promote and `v0` after one. Aaron asked the
question the tab exists for and found it unanswerable: *"I just wanna know what is the version that
I have compiled in my backtester versus the version that is deployed... and if I'm behind, there
should be a big nice button."*

`services/bot_versions.py` builds the real one, served as `BotDeployedVersion.compare`.

**A version is the number of commits that have touched the bot's trees, counted at a commit.**
Three properties fall out of that and the page needs all three: it moves when — and only when —
the code this bot runs moves; it is derived from the git history, so this machine and Aaron's
brother's compute the SAME number with no registry to sync; and subtracting two of them is not an
estimate of the work waiting to go out, it IS it. Measured on the live deployment: **v100 → v121,
21 behind**, which is exactly the 21 commits `git log 4e97565..HEAD -- <trees>` returns.

⚠ **Not the lab's own `strategy_versions` registry, and the reason is the whole design.** That
table is content-addressed and monotonic and it hashes the **strategy package**, while a bot runs
that package plus `engines/` and `backtest/` — which is where most of the logic lives, and is
precisely why `algos/live/version.py::deployment_hash` spans all three. A number off the lab
registry would sit unchanged while the engines beneath it moved: the bot would report the version
it was promoted at and trade different rules. **That is the exact failure the deployment pin exists
to prevent, re-introduced one layer up as a label.**

⚠ **`trees_for` mirrors `algos/tools/promote.py::repo_trees` and the two must not drift.** That
function decides what is COPIED into a snapshot; this one decides what is COUNTED. A tree promoted
but not counted is a change that deploys while the page says you are up to date — silent, and wrong
in the reassuring direction. The subsystem rule forbids importing into `algos/`, so the agreement
is pinned by a test that READS that file, the same arrangement `test_notification_routing.py` uses.

⚠ **Every function answers `None` rather than a number it cannot stand behind**, and `compare`
carries a plain-English `reason` instead. A missing commit (never fetched), an unreadable git, a
bot with no package: `0` would mean *up to date*, the most reassuring answer available and the one
most likely to be wrong. Same rule as `mt5_link` and `grid_sensitivity_score`.

### The settings that change without anyone asking

`setting_changes` diffs the strategy's dataclass DEFAULTS between the two commits and marks which
ones the bot's config PINS. This is the half of a promote nobody requests and everybody gets:
`live_config.py` states that *"a value that is not in the file is a value this bot does not have an
opinion about"*, so a default that moves in the repo moves the live bot on its next promote with
nothing in the request saying so. On the promote in front of Aaron that is the **36-hour time
stop** — and the service reproduces `promote.py --dry-run`'s four settings independently, which is
the cross-check that says the derivation is right.

⚠ **A `stated` row is RETURNED, not filtered out.** *This changed in the repo and your bot is
holding it still* is the reassuring half of the same question, and dropping it leaves the reader
unable to tell "not affected" from "not checked". It caught a real one: `exec_secondary` went
Off → On in the repo and this bot pins it Off — which `promote.py --dry-run` does not report.

⚠ **`ast`, never `import` or `exec`.** This parses source read out of an arbitrary historical
commit; running it would execute that commit's code inside the backend. Two refusals rather than
two guesses: a non-literal default is `_UNPARSED` (reported as *changed, cannot say to what*), and
a field declared in two classes with different defaults is also `_UNPARSED`, because `mpc_bleg`
subclasses `mpc_sos_fade`'s config and picking one silently would describe the wrong bot.

⚠ **`was` is `""` exactly when `is_new`, never `"Off"`.** The deployed version had no such lever at
all, which is not the same as having it switched off — and "Off" is the lie in the safe-looking
direction.

⚠ **Labels come from the strategy's own `*.meta.json`**, copied. A name→sentence mapping written in
this app would be a second claim about what a setting does, which is this repo's most-repeated
defect; the same discipline the trade-fib layer follows.

⚠ **`areas` on a change names which TREE a commit touched and is not a claim about trades.**
`backtest/` holds both the fill model the bot runs on and the lab's own cache, and no path can tell
those apart. Naming the area is derived; naming the effect would be a guess wearing a label.

✅ **28 tests (`tests/test_bot_versions.py`), non-vacuity proven by MUTATION** — a fail-watch
against HEAD is vacuous for a new module. Four mutations, four distinct tests red: dropping the
shared trees from `trees_for`, returning `0` instead of `None` for an unfetched commit, letting a
subclass override win silently, and claiming a new setting `was: "Off"`.

## Stopping a bot ASKS it to stop (2026-08-07)

🔴 **Every deliberate stop this app issued was a hard `wmic ... call terminate`, so the bot never
reached the `finally` that writes its `shutdown` record — and the NEXT startup reported *"the
previous run ended WITHOUT a shutdown record: it was killed, it crashed, or the box went down."***

That sentence is the **silent-death detector** (`algos/CLAUDE.md` → *The daily record*): no shutdown
record ⇒ the process was killed or the box died. **It only carries information if a DELIBERATE stop
leaves one.** It did not, so it fired on every restart anybody performed on purpose, and the Bots
page carried a permanent `NEEDS REVIEW` chip saying a healthy bot had crashed. Aaron read exactly
that on 2026-08-07 and asked why. ⚠ **An alarm that fires when you press the button is one you learn
to scroll past — the noise was not the cost, the signal it was burying was.**

`_kill_bot` now writes `<instance>/stop.request`, polls for the process to go for
`_GRACEFUL_STOP_SECONDS` (30, at `_STOP_POLL_SECONDS` 3), and terminates only a bot that ignored it.
`runner._loop` checks for the file at the top of every pass and exits through the ordinary clean
path. The return value names which path ran.

⚠ **A FILE, not a signal.** Windows has no usable SIGTERM for a console process — `taskkill` without
`/f` posts WM_CLOSE, which a Python console app never receives — and a file fits what that loop
already is: something that polls its own instance directory every `poll_seconds` and already
re-reads its config from there.

⚠ **The escalation is not a fallback nobody exercises.** A wedged bot, one blocked in an MT5 call, or
one running code that predates the file will never see it, and terminating those is the honest
answer. It keeps the two-clause `wmic` match — see `tests/test_bot_kill_scope.py` for why each half
is load-bearing.

⚠ **THE ONE WAY THIS COULD BE WORSE THAN THE KILL IT REPLACES is a STALE request stopping a healthy
bot seconds after boot** (left by a crash, a failed shutdown, an aborted SSH call). Four guards:
`run()` clears the file BEFORE the loop, both sides delete it after use, an unreadable instance
directory is never read as a stop request, and a clear that FAILS warns rather than refusing to
start. **A trading bot that will not stay up is a far worse failure than a noisy chip.**

⚠ **`_bot_is_running` answers True when the process list cannot be read**, so the caller escalates to
a kill rather than reporting a stop that may not have happened. Of the two wrong answers, "kill a
process that was already gone" is harmless and "report a live trading bot as stopped" is not.

⚠ **The kill-scope suite needed a SECOND fixture for this.** Its whole subject is that the terminate
command names both `python.exe` and `--bot <key>` — and after this change a healthy bot never
reaches that command, so those tests would have passed against a `_kill_bot` that issued no kill at
all. `stubborn_ssh` drives a bot that ignores its stop request. **A safety test whose scenario stops
occurring passes for ever and protects nothing.**

## The "needs review" flag — the one thing this page could not see

`BotStatus.review`, served from `<instance>/review.json` on the VPS, written hourly by
`algos/notifications/log_review.py` (`SYS_LOGREVIEW`), which reads each bot's own health record.

**Why it exists.** Every other signal on the Bots page is about the PROCESS — is it in the process
list, is it stamping a heartbeat, does it still hold its MT5 link. **None of them can see a HALTED
order bridge**: the loop runs, the heartbeat ticks, `wmic` lists the process, the page says RUNNING,
and the bot places nothing. Nor a bot that crash-looped overnight, nor a link outage that recovered
before anyone looked, nor a runtime config change the bot REFUSED (so the page shows settings it is
not using). All of those are in the bot's health stream and nothing here read a line of it.

⚠ **It is fetched on the SAME batched snapshot connection as `bot_state.json`.** A second ssh round
trip per bot is precisely the cost `_fetch_vps_snapshot` exists to avoid — the same reasoning that
moved `GET /{bot}/version`'s state read onto its git round trip (8.5s → 3.7s).

⚠ **The section name is DERIVED, `_review_section(key)`, used by the fetch and the parse both.** A
marker written under one spelling and read under another produces a flag that is always absent —
which renders exactly like a healthy bot, i.e. it fails in the reassuring direction and nothing
anywhere raises. `tests/test_bot_review_flag.py` pins that the two agree.

⚠ **`review_file` is PER BOT even when two bots share a `bot_state.json`.** A review is about one
bot's own record, and merging two into one file makes *which bot needs attention* unanswerable from
the file whose entire job is answering it.

⚠ **A missing file means NOTHING TO REVIEW, and that is the normal state** — `log_review.py` deletes
it when a bot comes back clean, so absence must stay quiet. A malformed one is dropped rather than
raised: this page must not invent an alarm out of its own plumbing failing, and the review job's own
absence is visible where it belongs, as a DISABLED `SYS_LOGREVIEW` in the scheduled-jobs list.

⚠ **It is NOT gated on `status == "RUNNING"`, unlike `mt5_link` directly above it.** The findings
that matter most — it crashed, it was killed, it refused to start — are exactly the ones you can only
read once the bot is no longer running, so hiding the flag on a stopped bot would suppress the
explanation at the moment somebody is looking for it. `mt5_link` is gated because a stopped bot's
last link stamp describes a process that no longer exists; a review describes the record, which does.

## Nav activity — three booleans so the sidebar stops pulling three lists

`GET /system/activity` → `lab_db.get_nav_activity()` → `{backtests, optimizations, stress_tests}`.

**Added 2026-08-05 because `Sidebar.tsx` is mounted on EVERY page** and derived those three
booleans client-side from the full runs / optimizations / stress-test lists. So having the app
open at all cost a `GET /backtests/runs` on a poll — **measured 1.69 KB per run, 66% of it the
54-key `params` dict** (~137 KB at 81 runs), plus the other two lists — to decide whether to draw
three pulsing dots. The endpoint is 62 bytes.

⚠ **The predicates must mirror `Sidebar.tsx`'s `activeByRoute` exactly, and they are now the ONLY
statement of them** — the dot used to be derived next to the thing it drew, and nothing in the
browser can contradict this any more. That is the saving and equally the risk, so every one is
pinned in `tests/test_nav_activity.py`, including the ones that must NOT match:

- a run carrying `optimization_id` is **not** a Backtests-section job (it belongs to the
  Optimizations section, whose own grid reports it) — one job must not light two dots;
- sweep and stack children **are**, because they surface in the Runs tab;
- stress tests match **`LIKE 'running%'`**, never `= 'running'` — a test spends most of its life
  in `running_wf` / `running_sens`, and an equality check leaves the dot off for the bulk of the
  run, which looks exactly like a test that already finished.

⚠ **It is deliberately NOT `has_running_job()`.** That answers *may I start work on this PLATFORM*
and partitions by runner; this answers *is this NAV SECTION busy* and partitions by job kind.
Collapsing them makes an MT5 optimization light the Backtests dot, or a python backtest fail to.

⚠ **The trimming stops here.** Dropping `params` from the runs LIST was considered and rejected:
`TuningWorkbench` genuinely reads it off that list to compute per-iteration deltas, so making it
conditional would produce a response where `params: {}` means both *"I did not ask for it"* and
*"there are none"* — the same **no data vs cannot ask** defect as `mt5_link` and
`grid_sensitivity_score`, landing in the tune page as "no parameters changed".

## Worthiness scoring

`services/worthiness.py`. Scored against the strictest evaluated prop firm (smallest `max_loss_eod`). When a run is evaluated against personal/demo rulesets only (e.g. a forex run — no prop firm covers forex), it falls back to the strictest personal drawdown limit (`account_size × max_drawdown_from_peak_pct`, via `metrics.effective_dd_limit_usd`) so forex runs still get a tier. Prop rows always win the pick when present.

| Tier | Criteria |
|---|---|
| **Tier 1 — STRESS_TEST** | PF > 1.3 AND DD ≤ firm limit AND DD not in danger zone AND trade_count ≥ 50 |
| **Tier 2 — OPTIMIZE** | PF in [0.8, 1.3] OR DD in danger zone (0.7×–1.0× of limit), trade_count ≥ 30 |
| **Tier 3 — DISCARD** | PF < 0.8 OR DD > firm limit OR trade_count < 30 |

Columns on `backtest_runs`: `worthiness_tier`, `worthiness_reason`, `worthiness_computed_against_firm` (firm_id of the strictest firm used). Added via migration — not in the original CREATE TABLE.

---

## Objective functions

`services/objectives.py`. Two registered objectives; chosen by `mode`:

- **`eval_pass_probability`** (default) — score 0.0–1.5. 1.0 = DD ok + target hit; speed bonus up to +0.5 for hitting target in fewer than 30 simulated days. Partial credit (0–0.5) if DD passes but target not reached. 0.0 if DD breached.
- **`funded_sharpe_under_drawdown`** — Sharpe ratio if DD within limit, −∞ if breached. Used when `mode = "funded"`.
- **`raw_profit_factor`** — profit factor, straight. Used when `mode = "raw"`, which is **every MT5 and every Python optimization**. ⚠ It has no opinion about sample size: two lucky trades at PF 8.0 outrank two hundred at PF 2.0. The floor that stops that is `optimizations.min_trades`, applied in `_pick_best_run` and **not** inside the objective — a combo below the floor is still run, still scored and still listed, it just cannot WIN.

⚠ **−∞ is how every objective here says INELIGIBLE**, and `_pick_best_run` starts at −∞ with a strict `>`, so a field where *every* combo is ineligible used to leave `best_run_id` NULL — a finished optimization with no ★ and nothing on the page explaining it. See the fallback ladder below.

---

## The optimizer's winner — three fallbacks, each of which must SAY SO

`_pick_best_run` returns `(best_run_id, winner_note)`. An optimization that names no winner is
useless, so falling back is right; a **silent** fallback is this repo's signature defect — a
page claiming something the code did not do. `winner_note` is stored on the row and rendered as
an amber banner above the results.

1. The stated scoring (objective + regime filter + trade floor).
2. Trade floor excluded everything → drop the floor, keep the scoring. *"No combination reached
   the N-trade minimum… treat it as a small sample."*
3. Regime filter matched no trades in any combo → re-score on ALL trades. *"…the regime filter
   did not apply."* ⚠ This one was a hard NULL before: `_regime_filtered_score` returns −∞ when
   a run has no trades in the target regime, and on a filter that matches nothing that is every
   run.
4. Everything still ineligible → highest profit factor, flatly. *"Read it as a ranking, not a
   pass."*

---

## Optimizations — the 2026-08-04 audit

The `optimizations` table was **EMPTY** when this ran, which is the frame: the page had never
been driven end to end, so every defect was latent and none had been caught by use. UI half in
`../frontend/CLAUDE.md`.

✅ **DRIVEN AGAINST THE LIVE BACKEND AFTERWARDS, not only unit-tested** — four real python
optimizations on cached XAUUSD M15, because a page nobody has run is not a page anybody has
tested, and that is the whole reason this list existed.
- **The hang is gone at the seam that matters**: `step: 0` posted to the live server returned
  `400 exec_risk_pct: step must be greater than 0` in milliseconds and the backend kept
  answering. Before, that request never returned and took every other endpoint with it.
- **Costs are CHARGED, not just carried.** The same 4-combo grid (`exec_tp1_pct` 0→45, Jan 2024
  → Jun 2025) run free and then with `spread`+`swap` on `vantage_demo`: PF 2.631/2.478/2.308/
  2.119 → 2.551/2.400/2.230/2.041, P&L $33,228/$28,323/$23,443/$18,624 → $31,149/$26,408/
  $21,703/$17,069. ⚠ **Trade counts identical at 33 across all eight runs** — which is the
  check that says the charge is real and correctly placed: spread and swap change what a trade
  MAKES, never whether it happens. A grid where the trade count moved would mean something else
  had changed.
- **Cancel stops the work.** A 6-combo full-history sweep cancelled mid-flight returned
  `job_stopped: true`, then sat at `failed_cancelled` with **0 runs written for 100+ seconds**
  and never flipped to `complete`; the platform lock released immediately (a new optimization
  was accepted straight after). Before, that sweep would have run to the end and overwritten
  its own cancelled status.
- **The fallback ladder fires and speaks.** `min_trades: 500` on a window that produces 4
  trades completed with a winner and the note *"No combination reached the 500-trade minimum,
  so the winner is the best of the whole grid. Treat it as a small sample."*
- **Robustness anchors on the ★** and the payload trim holds: a combo row came back with
  `params` = `{"exec_tp1_pct": 0.0}` alone, out of the strategy's full config.
- **Delete cleans up**: all four removed 204, leaving zero orphaned `backtest_runs` and zero
  orphaned `evaluations`.

🔴 **A `0` typed into a step box hung the WHOLE BACKEND.** `_expand_axis` expanded a range with
`while v <= hi: v += step` and never checked `step`, so zero (or a negative step, or a max below
the min with one) appended forever — and it ran **on the event loop inside the request
handler**, so it took every endpoint with it, not just this optimization. The range is counted
arithmetically now (`n = floor((hi-lo)/step) + 1`, which also stops the old loop's float drift),
and `_expand_axis` **raises** on step ≤ 0, max < min, non-finite values, an empty value list, or
an axis over `_MAX_AXIS_VALUES`. `validate_param_grid()` runs at REQUEST time → 400, and
`expand_grid` moved off the event loop. ⚠ **The ceiling is checked from the COUNT, before the
list is built** — a guard that materialises the thing it is guarding against is the event.

🔴 **Cancel did not cancel.** `POST /cancel` wrote `failed_cancelled` to the row and nothing
else: the sweep kept every core busy, the per-platform job lock (which reads that status) said
the platform was free so a second job could start on top of it, and the finished job overwrote
its own cancelled status with `complete`. Cancel now calls `runner_dispatch.cancel_job` —
runner-agnostic, three implementations behind one call — and the native poller checks the row's
status each tick and abandons the job. ⚠ It reports **`job_stopped`**: the row is cancelled
either way, but "stopped" and "could not tell it to stop" are different facts and only one of
them means the machine is free.

🔴 **Every grid was ranked on a FREE BOOK** while the run it was launched from had spread and
swap charged — two numbers produced under different physics, presented as a comparison.
`optimizations` gained `cost_layers` + `broker_profile`, the modal inherits them from the source
run, and they ride the spec into `python_runner._cost_profile`. ⚠ **NULL is not `[]`** here
either: NULL = a row predating the column, which keeps the old behaviour rather than being
silently re-priced on its next re-run.

🔴 **Delete and re-run both 500'd on a foreign key.** `stress_tests.run_id` and
`evaluations.run_id` are FKs into `backtest_runs` under `PRAGMA foreign_keys=ON`.
`delete_optimization` purged evaluations but not stress tests; `reset_optimization_for_rerun`
purged neither — so **re-run crashed on every optimization that had a ruleset** (NT8 writes an
evaluation row per combo). Both go through `_purge_stress_tests_for_runs` now. Re-run also
clears `best_run_id`, `winner_note` and the grid-sensitivity columns: a re-run re-measures, and
carrying them forward describes a grid that no longer exists.

🔴 **"Winner robustness" was measured on a combination that is not the winner.**
`_compute_grid_sensitivity` ran BEFORE the winner existed and anchored itself on the highest
profit factor. That is the same row only under `raw` mode with no trade floor — under `eval` or
`funded` the objective is not profit factor at all, and with `min_trades` set the top row may be
the very fluke the floor exists to exclude. It runs LAST now and takes the ★'s own params. ⚠ **It returns
`None` — never 0.0 — when the question cannot be answered** (winner absent from the grid after a
retry, winner PF ≤ 0, one value per axis, empty grid), and the caller then writes nothing so the
column stays NULL and the card does not render. **0.0 is the PERFECT-PLATEAU score**, the
strongest "trust this winner" the metric can say, so using it for "not measured" prints the most
reassuring number on screen exactly when nothing was checked. Same rule as `mt5_link` and
`mt5_connected`: never let "no" and "cannot ask" be the same value.

**`fail_optimization` stamps `completed_at`.** Without it the page had no end to measure against
and fell back to now(), so a job that died on Tuesday read `Ran for 74h` and kept climbing. **A
failure is a finish.**

**Write batching.** A native combo arrives already finished, so the whole grid is one
`insert_complete_optimization_runs` executemany instead of insert + update per combo (~2 sqlite
connections each — 2,000 on a 1,000-combo grid), evaluations come back through
`get_evaluations_for_runs` in one chunked query instead of one per combo, and worthiness writes
through `update_run_worthiness_bulk`. The evaluator loop is skipped wholesale when there is no
ruleset, which is every Python optimization. ⚠ `get_evaluations_for_runs` **chunks at 500** —
SQLite's default host-parameter ceiling is 999 and the thousand-combo case is the entire point
of the function — and it keys **every** requested id, because a missing key and an empty list
are different answers.

**`GET /{id}` trims the payload** to the grid's own param keys per combo (a combo's stored
params are fixed+swept, 50+ keys on a Python strategy) and moved its `job_status` call off the
event loop — for NT8/MT5 that is an HTTP round trip over the SSH tunnel, polled every 3 seconds.
⚠ It is a **projection**, not a deletion: the full params stay on the row.

---

## DB schema — notable columns

`backtest_runs`:
- `started_at` — actual start of the LATEST attempt. Set = `created_at` at insert; `reset_run_for_retry` moves it to `now` (while `created_at` stays put to anchor list order). Duration on the Runs page is `completed_at − started_at`, so a retried run measures only the attempt that produced the result, not back to the first kickoff. The live progress-bar timer already reads `progress.json`'s per-attempt `started_at`, so it was never affected.
- `worthiness_tier`, `worthiness_reason`, `worthiness_computed_against_firm` — see Worthiness scoring above
- `sweep_id` — child runs of an instrument sweep
- `optimization_id` — child runs of an optimizer job
- `source_run_id` — set when a sweep/optimization is triggered from a BacktestDetail page, OR when a tuning-workbench iteration is run from a baseline run; links derived runs back to the originating run. `BacktestRunRequest` and `BacktestSummary` both carry `source_run_id`; the tuning workbench filters runs by it to group iterations.
- `stress_test_id` — walk-forward and sensitivity child runs; links them back to the parent stress test
- `walk_forward_window_id` — identifies the window and period (e.g. `wf_2_oos`, `sens_EntryOffset_+10%`)

`optimizations` key fields: `optimization_id`, `strategy_id`, `instrument`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `ruleset_id`, `mode`, `search_method`, `param_grid` (JSON), `status`, `estimated_runs`, `completed_runs`, `best_run_id`, `source_run_id`, `regime_filter` (one of the 5 regime labels or NULL), `created_at`, `completed_at`, `grid_sensitivity_score` + `grid_sensitivity_summary` (JSON), and since 2026-08-04:
- `cost_layers` (JSON) + `broker_profile` — what the grid was CHARGED, so its winner is comparable to the run it came from. ⚠ NULL ≠ `[]`: NULL is a row predating the column and keeps the old free-book behaviour; `[]` is an explicit "charge nothing".
- `min_trades` — the trade floor a combo must clear to be eligible to WIN. 0 = no floor, and 0 is the API default; the optimize modal states 30 explicitly.
- `winner_note` — set when the ★ came from a fallback rather than the stated rule. Rendered on the page; see the fallback ladder above.

`instrument_daily_ohlc`: caches OHLC by (instrument, date). Source `"yfinance"` or `"nt8"`. Cache freshness: dates > 5 days old fetched once and never refetched; recent dates always refetched.

`stress_tests`:
- `mc_completed_at` — unix timestamp when Monte Carlo phase finished; frontend pipeline stepper shows per-phase elapsed time
- `wf_completed_at` — unix timestamp when walk-forward phase finished; same purpose

---

## How stress tests work

**Monte Carlo** — pure Python (numpy), no NT8 involved. Takes the trade P&L list from a completed backtest and runs two simulations:
- 10,000 reshuffles: same trades, random order. Probes whether the sequence of wins/losses was lucky. Sum is invariant, so final PnL doesn't vary across reshuffles — only drawdown does.
- 1,000 bootstrap resamples: samples trades with replacement. Both total PnL and drawdown vary.
- **Drawdown** stats (median/P95/P99, prob-breach) use BOTH pools (order genuinely varies drawdown). **Final-PnL** stats — the median/p5/p1 percentiles, the PnL histogram, AND the "probability of passing the eval" — use the **BOOTSTRAP pool only**: reshuffle final PnLs are all the net total (order-invariant), so including them collapses those onto one degenerate value. Don't reintroduce `all_pnls` into a final-PnL stat.
- **Pass-probability by ruleset_type** (`run_monte_carlo`): `prop_eval` with a profit target = `mean(final_pnl ≥ target AND max_dd ≤ limit)` (hit target AND never breach). `prop_funded`, `demo`, **and `personal`** = `1 − prob_breach` ("pass" = never breached the drawdown rule — none of them has a profit-target requirement). `personal` MUST stay in the `1 − prob_breach` branch with `demo`: it was previously only in the target branch, so with `profit_target = 0` it fell through both and defaulted to `0.0`, silently reporting 0% pass for any good personal strategy.
- **`prob_breach`/`prob_pass_eval` are `Optional[float]`, and `None` when the ruleset states no limit.** Not `0.0` (never breaches) and not `1.0` (always does) — there is nothing to breach, which is a third answer. Grading reads them through `_num()`, which falls back ONLY on `None`; the old `value or fallback` was a live bug in both directions, since every metric here can legitimately be `0.0` (a stored `prob_breach = 0.0` was reported to the user as "100% probability of breaching ruleset limit", and a `0.0` drawdown became `inf` and failed every limit check).

**Which SERIES gets shuffled — dollars or returns (2026-07-30).** Reshuffling a dollar P&L list assumes the trades are exchangeable, which is only true at constant position size. A %-risk compounding strategy violates it outright: on run `06f7eece0db1` the median |P&L| per trade drifts **$222 → $3,913 across the run (17.7x)**, so a shuffle was moving late $4k trades to the front of a $10k account and back-loading the small ones — measuring a strategy that never existed. `choose_shuffle_series(trade_pnls, balances)` picks per run: it measures the drift of both the dollar series and the per-trade RETURN series (`pnl / balance_before`, median |value| of the last third over the first third) and switches to returns only when the dollars actually drift (≥ `_DRIFT_TRIGGER` 2.0, ≥ `_DRIFT_MIN_TRADES` 30 trades) AND returns are the more stationary of the two. Same run: dollar drift 17.66x vs return drift 1.42x → returns. Paths then COMPOUND (`start_bal × cumprod(1+r) − start_bal`) instead of `cumsum`. **Fixed-size runs are untouched** — no balance series, or no drift, means dollars exactly as before. This is not a cosmetic change: the same run's worst-1% drawdown went **$41,970 → $359,886**, i.e. the old number understated the tail ~8x.

**Drawdown basis — `dd_basis` (`"percent"` | `"dollars"`).** A compounded run reports drawdown as a percent of the running peak (`median_max_dd_pct` / `pct5_max_dd_pct` / `pct1_max_dd_pct`, alongside the dollar columns, both persisted), because a fixed dollar limit stops being comparable to an account that has grown away from the size the limit was written for. The dollar view of that same run reported a **100% breach of TOTAL RUIN across 20,000 simulations in which the account was never once wiped out** — real ruin 0.00%, real worst-1% drawdown 61%. `prob_breach` is measured on whichever basis the grade will read, so the headline number and the letter can never come off different bases and contradict. Rows written before 2026-07-30 carry no `dd_basis` and keep the dollar path, so their stored grades stay reproducible.

**Walk-forward** — sends real backtests to NT8. Splits the original date range into N equal windows. Each window is split 70% in-sample / 30% out-of-sample — two separate NT8 backtests per window. Measures how much Sharpe drops from in-sample to out-of-sample. Large drop = strategy may be overfit to the training period. **Degradation is only computed over windows with a MEANINGFUL positive IS Sharpe** (the serial/MT5 path) — `1 − OOS/IS` is a meaningless signed ratio when IS Sharpe ≤ 0, and *explodes* when IS Sharpe is a tiny positive (a flat in-sample window with Sharpe ~0.002 once produced a 539,229% per-window value → 134,540% average). So windows below `_WF_IS_SHARPE_FLOOR` (0.1) are excluded as not-assessable, and each surviving window is clamped to `_WF_DEG_CLAMP` (`[-100%, +200%]`) before averaging. If no window qualifies, degradation is stored as `None` → UI shows "n/a (IS Sharpe ≤ 0)" and grading treats it as not-run (neither credit nor penalty). The native NT8 WF path (optimization-derived runs) degrades on **profit factor**, not Sharpe (no per-trade data), so the signed-ratio sign-flip can't occur — but it applies the **same honesty rule**: when no window has IS PF > 0, degradation is stored as `None` (not `0.0` — `0.0` would read as "0% = solid robustness" for a strategy unprofitable in every in-sample window), and grading's not-assessable reason is PF-worded ("IS profit factor ≤ 0"). Both WF paths now treat unassessable degradation identically (`None`); `0.0`-as-solid is gone from both. **Thin windows are excluded too (`_WF_MIN_TRADES_PER_WINDOW = 20`, 2026-07-30):** a Sharpe off 6 out-of-sample trades is noise wearing a decimal point, and averaging it in produced a confident-looking degradation figure with nothing behind it (measured windows on run `06f7eece0db1`: IS/OOS = 15/6, 24/6, 10/6, 16/12, 22/8 — every one thin). `window_data` now carries `is_trades`/`oos_trades` so the filter can see them, and when every window is thin the degradation is `None` with a reason that names the fix ("the windows closed too few trades each to support a Sharpe. Re-run with fewer walk-forward windows") rather than the generic IS-Sharpe wording, which would be a false diagnosis.

**Sensitivity** — re-runs the strategy with each numeric parameter shifted, one VPS backtest per shift. **Only STRATEGY-LOGIC params are perturbed** — foundational params (`category == "foundational"` or the MQL5 `f_` prefix) are excluded via `_is_foundational`, the same split the optimizer tunes; perturbing injected config (often at the `-1` sentinel) is wasteful and meaningless. Booleans are skipped. **Scored on PROFIT FACTOR, not net P&L (2026-07-30, Aaron's call):** `degradation = |child_pf − baseline_pf| / baseline_pf`. Net P&L is not scale-free, so any parameter that moves position SIZE dominates the score by construction — on run `06f7eece0db1` `exec_risk_pct` read **85.8% on profit and 11.8% on profit factor**, and since the field is a max across params it single-handedly set the run's score to 85.8% (true worst on PF: `aplus_window` at 12.6%). That is a sizing knob doing exactly what it is supposed to do, graded as fragility. Excluding the param instead would have been overfitting the engine to one strategy; changing the metric is generic. `pnl_delta` is still recorded per shift (the frontend keeps it as a legacy field), and `degradation` is `None` — never `0.0` — when the baseline PF is missing or non-finite. **A shift that changes nothing is skipped, not run:** integer rounding made 43 of this run's 60 sensitivity backtests reproduce the baseline exactly (a ±10% shift on a param whose value is 1 rounds back to 1), which is ~50 minutes of VPS time measuring the same number. `seen_vals` also dedupes shifts that collide with each other. Both are reported in `skipped` — a silent skip would read as coverage that never happened. Large swings = strategy is fragile to exact parameter values. **MT5 uses 2 shifts (±10%)** to limit queue depth; NT8 uses 4 shifts (±10% and ±25%). `SHIFTS` in `stress_tester.run_sensitivity_task()` is runner-aware. The UI time estimate, the note's backtest count, and the run loop all read from shared helpers (`sensitivity_param_count` = perturbed (non-foundational) count, `sensitivity_shift_count` = 2/4 by runner) so they can't drift — `_estimate_sens_duration_min(n_params, runner)`.

**Auto-trigger** — fires MC only (no NT8) automatically when a Tier 1 backtest completes or an optimizer picks a winner. Manual trigger always runs all three phases (MC + walk-forward + sensitivity); no user checkbox.

**Sample-size gate** (`stress_tester.MIN_TRADES_FOR_STRESS = 100`) — one flat floor: below 100 trades the WHOLE stress test is blocked, not just walk-forward. Rationale: the page's output is the A–F grade, and the grade leans on Monte Carlo TAIL percentiles (A = worst-1% drawdown, B = worst-5%) that small samples can't estimate — so a sub-100 grade is false confidence, the same disease as the 134,540% walk-forward number. `POST /stress-tests/run` returns **422** below 100 and `trigger_auto_stress_test` skips (so Tier 1 runs with 50–99 trades get no auto Monte Carlo either). `BacktestDetail.tsx` mirrors the constant and disables the Stress Test button below 100 with an explicit tooltip — backend is authoritative. Clear the bar with more DATA (longer period, more instruments, smaller timeframe), never by loosening params to inflate the trade count (that just curve-fits).

**Child run isolation** — walk-forward and sensitivity runs are inserted into `backtest_runs` with `stress_test_id` set. `lab_db.list_runs()` always adds `r.stress_test_id IS NULL` to its WHERE clause so they never appear in the Runs tab. They're accessible only from `StressTestDetail`.

**Market lock** — `lab_db.running_stress_test_markets()` queries `stress_tests WHERE status LIKE 'running%'` (covers `running`, `running_wf`, `running_sens`), joins to derive `runner`, returns `{futures, forex, run_ids}`. `POST /stress-tests/run` checks this before inserting; 409 if same market is already running. `GET /stress-tests/running-lock` exposes it for the frontend poll.

**Crash recovery** — `lab_db.reset_stale_stress_tests()` marks any `running%` stress tests as `failed_crashed` and their child runs as `failed_timeout`. Called in `main.py` `startup()` — backend restarts automatically clear stuck tests and release the market lock.

---

## Key architectural decisions

**Optimizer implementation:** All optimizations use `search_method = "native"`. The brute-force batch path still exists in `optimization_runner.py` for retrying the two legacy runs in the DB but is not reachable from the UI for new jobs.

- **`"native"`** — sends ONE `POST /native-optimize` to the VPS agent. `nt8_backtest_runner.run_native_optimize_mode` switches the SA to Optimization mode, sets Start/End/Increment ranges for each Strategy Logic param, fires a single Run that uses all CPU cores, then exports the results grid to CSV. MT5 path uses `mt5_agent.py` with `Optimization=1` ini + set-file ranges + HTML combo parser. The backend creates run rows for every combo after the grid is returned. No per-combo equity curve — auto-trigger stress test is skipped; winner must be stress-tested via a manual single rerun. `estimated_runs` is always the full grid size.

**What the non-swept params are held at — "inherited" has to mean inherited (fixed 2026-08-02).** The optimize modal shows each unswept param at the SOURCE RUN's value and labels it `inherited · not swept`. The grid was built from `strategy.default_params` and never read the run at all, so optimizing from a TUNED run quietly tested a different configuration from the one on screen, with nothing on the page able to say so. Live example: run `096432c2ad20` (MPC B-LEG) carries `exec_tp1_pct = 30` / `exec_tp2_pct = 40` against `config.py` defaults of 0/0 — every combo in a grid launched from it ran 0/0. `optimization_runner.base_params_for(opt, strategy)` is the one seam, used by BOTH the native and brute paths. **It may change a VALUE and never introduce a KEY:** a run can carry leftovers from an older schema, and for MT5 a `fixed_params` dict holding an input the EA does not declare makes the tester treat the set file as mismatched and silently run a single backtest (the set-file purity rule below). Foundational injection still lands last, so ruleset values keep overriding.

**Only the Python runner may be sent a LIST axis (2026-08-02).** `_expand_axis` has always accepted `[val, ...]` beside `{min, max, step}`, which is what lets a dropdown or an on/off be swept across its own closed set — but only `python_runner` expands the grid locally. NT8 and MT5 hand a Start/Step/Increment RANGE to their own tester, so a list of strings has nowhere to land there and the job would optimize nothing while reporting success. `POST /optimizations/run` refuses it with a 400 naming the params (`routers/optimizations.py`); the frontend mirrors the rule by only offering the sweep button on python runs. Both sides are pinned by `tests/test_optimizer_grid.py`.

**Per-platform job lock — the single source of truth:** There is one physical terminal per platform — one NT8 Strategy Analyzer, one MT5 Strategy Tester — so each platform runs at most ONE job at a time (single backtest, sweep, or optimization), but **the platforms are fully independent: an MT5 job never blocks an NT8 job and vice versa.** `python` is a THIRD independent scope — no terminal at all (runs in the backend process), serialized anyway to protect the local CPU/data cache; its rows are excluded from the NT8 count so the scopes partition. The lock is the DB, scoped by runner. `lab_db.has_running_job(runner)` is the canonical check — it dispatches to `has_running_nt8_job()` / `has_running_mt5_job()` / `has_running_python_job()`, which each count `status='running'` rows in `backtest_runs` (covers single runs, sweep child runs, and stress-test child runs — all carry `runner`) plus `optimizations`. Every trigger/retry/rerun endpoint across backtests, sweeps, optimizations, and stress tests calls `routers._locks.ensure_platform_idle(runner)` before creating a job; it raises 409 if that platform is busy. **Gates must never read `lab_progress.json`** — that file is for the single-run progress bar only and is shared across both platforms, so using it to gate would cross-block (an MT5 run blocking NT8) and could deadlock on a stale value. There is no cross-platform "any VPS job" lock.

**Must join strategies for optimizations:** `optimizations` has no `runner` column — `has_running_nt8_job()`, `has_running_mt5_job()`, and `get_running_job()` all `LEFT JOIN strategies s ON s.id = o.strategy_id` and filter on `COALESCE(s.runner, 'ninjatrader')`. Without the join a running MT5 optimization would appear as an NT8 job and block NT8. `get_running_job()` returns `{nt8, mt5, python}` — one bucket per lock scope, each resolved by the SAME `_SCOPE_RUNNER_SQL` predicate table the `has_running_*_job()` checks use, over the three job types (backtest → sweep → optimization, first hit wins). **The predicates must PARTITION:** a row matching two scopes makes one job block a platform it never touches; a row matching none runs unreported and a second job starts on top of it. NULL/unknown runners fall to NT8. `tests/test_job_locks.py` pins the partition from both sides — the owning scope sees each job type, the other two do not. Sweep child runs persist `runner` (set in `insert_run_sweep`), so MT5 sweeps lock MT5 and NT8 sweeps lock NT8.

**Sizing: who decides the size (2026-07-16).** Two questions, kept separate. (1) **Does the lab size this strategy at all?** `strategies.self_sizing` — 0 (default) = it proposes unit-size trades and `sizing_engine` sizes them per ruleset (ORB, LondonBreakout: the gated layer, which forbids a strategy from baking risk management in — so there is deliberately no meta.json escape hatch, only a python package's `LAB_STRATEGY` may declare it). 1 = the strategy already applied its own risk % (`mpc_sos_fade`'s `exec_risk_pct`), so `_handle_complete` SKIPS the engine entirely. It must: re-sizing discards the strategy's real size, and since `equity_curve` deliberately stays the runner's own curve while `kpis`/`daily_pnl` get replaced, the page would show two different P&Ls for one run. (2) **If the lab sizes it, on whose terms?** `backtest_runs.sizing_mode` ∈ `sizing_engine.MODES` — `consistent` (room÷7) and `bullet` (max the ladder allows) are AUTOMATIC (the ruleset decides); `manual` takes `backtest_runs.manual_risk_pct` and risks exactly that % of the CURRENT balance every trade (so it compounds). Manual sets only the waterfall's BASE — the hard clamps (drawdown room, contract ladder) still apply, so on a ruleset with limits manual is a request, not a guarantee. The **`unconstrained` ruleset** ("Unconstrained (No Limits)") is the pairing that makes X% mean exactly X%: `max_loss_eod=0` + `max_drawdown_from_peak_pct=NULL` ⇒ `current_floor()` is None ⇒ room is None ⇒ no clamp; no daily cap/target ⇒ no halts; no ladder/consistency. **Never add a limit to that row** — its whole purpose is having none.

**Crash recovery — DB is authoritative, so it must be cleaned on boot:** A backend restart kills the asyncio task polling a VPS job, leaving the row `status='running'` forever — and since the lock now reads these rows, a stale row would deadlock the platform. `main.py` startup calls `reset_stale_stress_tests()` (stress tests + their child runs) then `reset_stale_runs()` (all remaining `running` `backtest_runs` + `optimizations` → `failed_crashed`). `lab_progress.json` is also reset on startup but only drives the progress bar, not the lock.

**Stress test architecture:** `services/stress_tester.py` runs three phases: (1) Monte Carlo — pure numpy, vectorised, ~5s even for 700+ trades. (2) Walk-forward — N windows × 2 VPS backtests (IS + OOS), sequential. (3) Sensitivity — N params × SHIFTS VPS backtests, sequential; SHIFTS = 2 for MT5, 4 for NT8. Auto-trigger runs MC only — no VPS needed. Manual trigger always runs all three phases.

**Auto-trigger gate — Tier 1 only:** Both paths that auto-trigger MC must check `worthiness_tier == "TIER_1_STRESS_TEST"` before firing. Single-run path (`backtest_runner.py`) already does this. Optimization winner path (`optimization_runner.py`, `_run_winner_backtest`) must also check — without the gate it fires on every winner regardless of how bad the result is, producing unexpected F grades the user never asked for.

**Strategy best grades:** `lab_db.best_grades_by_strategy()` queries all graded stress tests, returns `{strategy_id: {grade, stress_test_id}}` keeping the best grade per strategy (A–F ordered). `GET /stress-tests/strategy-grades` exposes this. Route must be defined before `GET /{stress_test_id}` to avoid FastAPI matching "strategy-grades" as a stress test ID.

**Robustness grading:** `services/grading.py`. Grade A-F based on Monte Carlo tail risk + optional walk-forward IS→OOS degradation + parameter sensitivity.

| Grade | MC condition | Walk-forward (if run) | Sensitivity (if run) |
|---|---|---|---|
| A | worst-1% DD ≤ limit | degradation < 20% | max drop < 25% |
| B | worst-5% DD ≤ limit | degradation < 30% | max drop < 40% |
| C | median DD ≤ limit | — | — |
| D | median profitable but DD fails | — | — |
| F | median loses money | — | — |
| **`None`** | **ruleset states NO drawdown limit** | — | — |

**"DD ≤ limit" is compared in the unit `dd_basis` names** — percent-vs-percent on a compounded run, dollars-vs-dollars otherwise — and the grade_reasons are written in that same unit (`_fmt`), so a reason never quotes a dollar figure the letter didn't read. `metrics.effective_dd_limit_pct()` is the one place a ruleset becomes a percent limit: personal/demo rows state it outright, prop rows derive it (a $5,000 trailing max loss on a $50,000 account is 10% — nothing new had to be defined).

**A `None` grade is a first-class outcome, not an error** (2026-07-30). The test still completes and the Monte Carlo numbers are still reported; there is simply no letter, because every row of that table is a statement about drawdown vs a limit and `unconstrained` states none. Before this, all three `limit > 0` guards evaluated False and the run fell through to **D — so D was the CEILING for any no-limit ruleset**, which reads as a verdict on the strategy and is not one. The reasons carry the fix ("Set the drawdown percent you are willing to accept on a ruleset and re-run"), and `personal_forex_risk` exists to be that ruleset for forex.

⚠ **Total ruin (100%) was implemented as the default limit for no-limit rulesets, measured, and REMOVED.** It is the one bar needing no opinion, so it looks like the obvious answer. It does not discriminate: a compounding simulation cannot reach a zero balance (every `1+r` is guarded > 0), so the bar is only brushed by a strategy already in total collapse — a 10%-risk run with a **70.4% worst-1% drawdown clears it and would have been graded A**. A threshold almost nothing can fail is not a grade. Do not re-add it; the walk-back is recorded in `grading.compute_grade` and pinned by `tests/test_drawdown_basis.py::test_no_stated_limit_stays_ungraded_even_on_the_percent_basis`.

**An unassessable walk-forward CAPS the grade at B** (Aaron's call, 2026-07-30). An A is the only grade that claims out-of-sample evidence, so awarding one off Monte Carlo alone overstates what was measured. The cap is a CEILING, not a deduction — a run that would have graded C stays C — and it applies only when WF *ran and could not be assessed*, never when it was genuinely not run (an MC-only auto-trigger is not evidence of overfitting). When the cap binds and the worst-1% would otherwise have passed, a reason says so explicitly rather than leaving the user to infer why an A became a B.

When walk-forward/sensitivity weren't run, those conditions are skipped (grade is based on MC alone — still valid but grade_reasons notes the gap). A WF that ran but couldn't be assessed (degradation `None` — all IS Sharpe ≤ 0 on the serial path, or all IS profit factor ≤ 0 on the native path) is treated the same as not-run — neither credit nor penalty — with a distinct grade_reason that names the path's metric ("Walk-forward ran but IS→OOS degradation is not assessable (IS Sharpe ≤ 0)" serial / "(IS profit factor ≤ 0)" native; chosen by summary shape — native rows carry `is_pf`); the "not run" caveat is scoped to genuinely-not-run so the two messages don't contradict.

**Deployment gates (UI only, soft):** A = funded; B = eval purchase; C = demo. Shown as warnings, never blocking.

**Regime classifier (M4):** Import from `trading/engines/regime/` — the canonical implementation lives there, never duplicate it here. The canonical algorithm doc is at `trading/engines/regime/REGIME_CLASSIFIER.md`. Import pattern:
```python
import sys
from pathlib import Path
# engines/ on sys.path so the canonical engines import by bare name
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))
from regime import classify_regime  # returns one of 5 labels + UNKNOWN
```
Lab uses daily OHLC, so pass the same DataFrame for both `df_short` and `df_long` (`classify_regime(df_daily, df_daily)`). Warmup: fetch 50 extra days before `start_date` so day 1 gets a real label. Window: 34 bars. The OHLC cache is in `instrument_daily_ohlc` — use `services/ohlc_fetcher.get_ohlc()`, never fetch directly in service code.

**Regime filter in optimizer (M4):** When `regime_filter` is set on an optimization, `_pick_best_run` builds a `date → regime` map once from OHLC, then scores each child run using only trades from matching-regime days. NT8 still runs the full backtest period — filtering happens at scoring time only. All three scoring paths (initial run, retry-one, retry-all) go through `_pick_best_run`.

**Sweep serialisation:** `sweep_runner.py` uses `asyncio.Semaphore(1)` — same constraint as the optimizer. Instruments run one at a time through the SA window.

**Runner dispatcher:** `runner_dispatch.start_backtest(job_spec, runner)` routes to the appropriate backend. `"ninjatrader"` (NT8 Strategy Analyzer), `"mt5"` (MT5 Strategy Tester via `mt5_agent_client`), and `"python"` (local in-process via `python_runner` — backtests AND `start_native_optimization`/`native_opt_results`) are wired. `runner_dispatch._nt8_to_mt5_spec()` translates the NT8-style job_spec to the MT5 agent's format — critically, it passes `job_id` through so the MT5 agent stores the job under our `run_id`; without this every status poll returns 404 and the run times out. Timeframe mapping in `_nt8_to_mt5_spec`: M1/M5/M15/M30/H1/H4/D1 (Minute bar_value thresholds: ≥240→H4, ≥60→H1, ≥30→M30, ≥15→M15, ≥5→M5, else M1). `_normalize_mt5_status/results()` translates the MT5 agent's response shape back to the NT8 shape so all callers remain runner-agnostic. `_normalize_mt5_status` passes through actual `pct`, `completed_count`, and `total_count` from the MT5 agent job dict (single backtests have no granular progress so they stay at a low floor; optimizations emit per-combo updates). `runner` field added to `BacktestDetail` model and `_row_to_detail`. File upload/delete also dispatch by extension: `.mq5` files go to `mt5_agent_client`, `.cs` files go to the NT8 nt8_agent.

**Set-file purity (MT5) — the `.set` file must contain ONLY inputs the target EA declares.** `_nt8_to_mt5_spec` provides standalone foundational (`f_*`) defaults for raw MT5 runs (no ruleset → `inject_foundational` never fires), but that default set is a *union* across MT5 EAs (e.g. it carries MeanReversion's `f_BrokerToEtOffsetHours`). It now **filters those defaults to keys present in the strategy's scanned `params`** (`{k: v for k, v in foundational_defaults.items() if k in params}`) so an EA never receives an `f_` input it doesn't declare. Strategies always pass their declared `f_` params (at the `-1` sentinel pre-injection), so a missing key genuinely means "not an EA input". MT5 tolerates a *lone* unknown input, but a set file polluted with several is treated as mismatched and the optimizer silently degrades to a single backtest (no `opt_results.csv`). This is the runtime twin of the `run_native_optimization` gate above — both exist to keep the MT5 set file clean.

**MT5 deal direction vs position direction:** MT5 Strategy Tester emits 2 deal-rows per trade — an entry deal (profit=0, deal direction = position direction: "buy" for Long, "sell" for Short) and an exit deal (profit=realized P&L, deal direction = opposite of position direction: "buy" to close a Short, "sell" to close a Long). `_normalize_mt5_results` **builds the equity curve directly from the paired trades** — it walks deals in time order (entry = profit==0.0, exit = profit≠0), pairs them via a **FIFO queue** of pending entries (so two positions open at once close first-opened-first-closed instead of the later entry clobbering the earlier), and emits **one directional point per closed trade**, accumulating realized P&L onto an opening-balance anchor. This guarantees `long + short == trade_count` for every consumer (Long-vs-Short breakdown, regime breakdown, stress-test trade-P&L list, price-chart markers). **Do NOT** revert to overlaying direction onto the agent's raw balance curve keyed by exit timestamp: MT5 timestamps are minute-resolution, so two trades closing in the same minute collapsed onto one point and the breakdown silently undercounted (long+short < trade_count). And do NOT map all deals naively — that doubles the trade count and inverts the labels on exit deals. The entry/exit split is heuristic (profit==0.0 = entry), so a genuine $0.00 breakeven exit would be misread as an entry — acceptably rare with commissions, but the real fix would need the report's Direction (in/out) column, which `mt5_agent.py` drops before the backend sees it.

**`delete_run` cascade — stress tests included:** `stress_tests.run_id` is a FOREIGN KEY into `backtest_runs`, so a run that has a stress test cannot be deleted until that test (and its walk-forward/sensitivity child runs) is gone — otherwise SQLite raises `IntegrityError` and the DELETE endpoint 500s. `delete_run` calls `_purge_stress_tests_for_runs()` for the target run AND for the optimization/sweep child runs it cascades (a winner or sweep child can also carry a stress test). A stress test's own child runs never carry a nested stress test (auto-trigger is parent-only), so one level of cascade suffices. `delete_run` **returns the run_ids of every backtest_run it deleted** (target + all cascaded children; empty list = run not found), and the DELETE router `shutil.rmtree`s each one's `reports/lab/<run_id>` dir so no orphan report folders are left behind.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

**source_run_id:** `optimizations` stores the `run_id` of the backtest that spawned it. Sweep child runs store the `run_id` of the run that triggered the sweep. The Runs tab uses this to nest linked jobs under their source run. Rows without `source_run_id` (created before this was added) appear only in their own tab — no backfill is possible.

**Rerun over a new period:** `RetryRunRequest` optionally carries `start_date`/`end_date` (ISO days). Both or neither — a half-set, a malformed date, or `start >= end` is a 400. The dates are written onto the run row (`lab_db.update_run_period`) BEFORE the job fires, because the retry re-fills the SAME row: a run that kept its old window in the DB while being re-run over a new one would label the new result with the wrong period. **Standalone runs only** — a sweep child or optimizer combo shares one period with every sibling in its set, so an override there is rejected (400) rather than silently desyncing the comparison. The frontend mirrors the split: `BacktestDetail`'s Rerun button opens `RerunModal` (period pre-filled from the run) only when `!sweep_id && !optimization_id`, and re-fires directly otherwise.

**Rerun clears its own stale progress entry:** a retry reuses the `run_id`, so the FAILED attempt's entry in `lab_progress.json` — error text and all — is still filed under that same id, and the live banner rendered the old error while the rerun was already running. `retry_backtest_run` clears it up front, but only when `read_progress()["job_id"]` is this run: the progress file is shared across runners, and blanking it for a live job on another platform would be a worse bug. The frontend half is `useRetryBacktest` marking a trigger + invalidating `['lab','progress']` — without it the progress query sits on its idle 30s cadence (the last payload was a failure, so it isn't `running`) and the stale text survives the backend fix.

**Optimizer-combo full backtest scoring (inherit, else prompt):** combo runs (`insert_run_optimization`) don't store an eval selection, so `POST /runs/{id}/retry` resolves one before re-firing: explicit `RetryRunRequest.evaluate_rulesets` (the UI's choice) > the optimization's own `ruleset_id` > the spawning run's `evaluate_firms` (forex/`raw` optimizations have no `ruleset_id` but are usually launched from an evaluated parent) — see `optimization_runner.resolve_opt_eval_rulesets`. When nothing is inheritable and no explicit choice was sent, the endpoint returns `{status: "needs_ruleset"}` WITHOUT starting a run; the frontend prompts (`FullBacktestEvalModal`) and re-fires with the choice. `retry_single_optimization_run(run_id, evaluate_rulesets=...)` then scores via `_handle_opt_complete` → `evaluator.evaluate_run`. Without this a combo full backtest completed unscored (empty `ruleset_ids` → zero evaluation rows → no PASS/DISCARD).

---

## Strategy file deployment (Pass 2)

Live behavior. NT8 agent endpoints: `GET/POST/DELETE /files/strategies/<filename>`, `POST/GET /compile`. NT8 strategy folder: `C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`. Detail is in git history (Pass 2).

**Gotchas:**
- **Compile (NT8):** `nt8_compile_runner.py` uses pywinauto F5 via NinjaScript Editor (`NCompile.exe` does not exist on this install). **Success** = `NinjaTrader.Custom.dll` mtime advances (NT8 rewrites it on every successful compile). **Failure** is read straight from the editor's UIA error grid — NT8 keeps F5 compile errors ONLY in that in-memory grid, never in any trace/log file (verified: the trace/log dirs carry zero compile output), so polling logs can't surface them. The runner scrapes the grid rows (`ORB.cs  Identifier expected  CS1001  1  16`) and emits each as an `ERROR:` line, which the `CompileModal` renders one per line. It fails **fast** (~6–10s, after a 6s grace for the grid to repopulate) instead of always waiting the full 90s. Guardrails: real error rows are trusted unconditionally; the "errors must be resolved" status marker only counts if it's *fresh* (captured before vs after F5, so a stale marker from a prior failed build can't false-trip); if the grid read finds nothing it still fails fast with an honest "open the editor" message; a true hang falls back to the 90s timeout. The NT8 agent spawns the runner as a fresh subprocess per compile, so a runner change is live on `git pull` alone — no agent restart. **Note:** sync-status compares only the hashes command-center itself deployed/compiled — it never re-hashes the live VPS file, so a file hand-edited directly on the VPS (bypassing deploy) still shows green "In sync"; a failed compile never advances `compiled_source_hash` (`mark_runner_compiled` runs only on `status == "success"`), so the badge is honest for the normal deploy→compile flow.
- **Compile (MT5):** `mt5_agent._run_compile` compiles each `.mq5` explicitly (`metaeditor64.exe /compile:<file> /log`) and confirms success the same way NT8 does — by mtime. It records each `.ex5` mtime before compiling and requires it to advance afterward; MetaEditor's exit code is unreliable and the directory form (`/compile:<dir>`) could silently no-op, reporting a stale `.ex5` as success. A file whose `.ex5` mtime does not move is a hard failure (`status: failed`) with the compiler `.log` lines surfaced in `errors` — never reported as success. **Warnings** are scraped from the same `.log` and returned in `warnings`, but the match requires the `": warning"` token (MQL5 format `file(line,col) : warning 123: msg`), NOT a bare `"warning"` substring — MetaEditor's trailing summary line `Result: 0 errors, 0 warnings, …` contains the word "warning" and a loose check false-positived a clean build as "1 warning". **The MT5 agent is a long-running process** (not respawned per compile like the NT8 runner), so an agent-side change like this is live only after `git pull` on the VPS **and** restarting the `MT5AgentRDP` schtask — never a blanket `taskkill python.exe` (that also kills the NT8 backtest agent).
- **Upload limit:** 256 KB, enforced on both agent and backend router.
- **Lock detection:** agent tries `r+b` open before upload/delete; `IOError` → HTTP 423.
- **Sync-status:** `GET /strategy-files/sync-status` — **content-aware** (no longer presence-only). It reads the local source **live from disk**, hashes it (md5, same as the scanner via `strategy_scanner.source_hash`), and compares to the recorded deployed/compiled hashes: `needs_deploy = local_hash != deployed_source_hash`, `needs_compile = deployed_source_hash != compiled_source_hash`. `in_sync = file_exists_on_vps AND not needs_deploy`. Also returns `current_version` / `deployed_version` / `compiled_version`. It lazily registers the live hash (`ensure_strategy_version`) so the current version always resolves even before a re-scan. **Since 2026-08-06 an unreachable agent degrades instead of 502-ing** — see *The Strategies page — the 2026-08-06 audit* below.

## The scanner read the MODULE and hashed the FILES — so a stale row could not be fixed by scanning

🔴 **Fixed 2026-08-06.** `exec_time_stop_mode` was flipped `"Off"` → `"Before TP1 only"` in
`strategies/python/mpc_sos_fade/config.py`, the scan reported success, and the Run modal went on
offering **Off**. Clearing `source_hash` by hand in sqlite was the only way out.

`_parse_python_package` called `importlib.import_module`, which returns whatever is already in
`sys.modules`. **The backend is a long-running process, so the FIRST import of a strategy pins its
config dataclass for the life of that process** — and uvicorn's `--reload` watches `backend/`, not
`strategies/`, so editing a strategy never restarts it.

⚠ **On its own that is an ordinary staleness bug. What made it dangerous is that it SEALS ITSELF.**
`_python_source_hash` reads the FILES while `_py_param_schema` reads the cached MODULE, so a scan
after an edit writes the **new hash beside the old defaults** — and `needs_rescan` compares only the
hash. The row is satisfied for ever; every later scan skips it. **Nothing reports anything**: the
"Needs scan" pill clears, the scan says `updated`, and the lab keeps serving a default the strategy
no longer has. This repo's *no data vs cannot ask* rule, arriving as *this is current vs I last
looked before you changed it*.

`services/strategy_import.py` is the one seam: `purge_strategy_modules()` then
`import_strategy_package()`. Both `strategy_scanner.scan_strategies` and `python_runner._resolve`
go through it.

⚠ **`python_runner._resolve` had the identical bug and it is the worse half** — a backtest replaying
a strategy the repo no longer contains produces an entirely normal-looking result describing code
nobody can read. It purges too, once per job.

⚠ **Purge the whole `strategies.python` namespace, never one package.** `mpc_bleg` imports
`mpc_sos_fade`'s execution module and sorts BEFORE it, so a per-package purge would re-import the
dependent against a still-cached dependency — the same mixed reading, one level down.

⚠ **The `strategies` ROOT is deliberately left cached** (it is an empty namespace package carrying
no strategy source). In a test that matters and is called out in the fixture: another test imports
the real `strategies` first, which pins `__path__` to the monorepo, and a `tmp_path` probe package
is then never found.

⚠ **Dropping a module from `sys.modules` does not invalidate references anything already holds** —
an in-flight backtest keeps the classes it was built with and finishes on them. That is what makes
this safe to call from a request handler.

✅ **Proven against the LIVE backend, not only by test.** With the strategy already cached in the
running process, `config.py` was edited to `"Always"`, one scan reported `updated: 1`, and
`GET /strategies` returned `Always`; reverting and re-scanning returned `Before TP1 only`. 5 new
tests (698 green), **4 of them watched RED with `purge_strategy_modules` neutered** — the fifth is
kept and LABELLED vacuous, since it pins idempotency and passes either way.

**The standing lesson is narrower than the label-vs-code refrain and worth keeping separate: when
one fact is derived from two reads, they must be reads of the same thing.** A freshness check whose
marker is read from disk and whose payload is read from memory does not merely go stale — it
records that it is up to date, and that record is what stops anyone ever finding out.

## The Backtests list and the Backtest detail page — the 2026-08-06 audit

Aaron asked for an in-depth audit of both pages and then for the fixes. **27 findings; nine were
real defects and three of those were destructive.** The shape they share is the one this repo keeps
meeting from new directions: **not one of them produced an error.** Each reported success while
doing something other than what it said. The UI half is in `../frontend/CLAUDE.md`.

### Stop cancelled whatever job the shared progress file named

🔴 **`stop_backtest_run` read the job id out of `lab_progress.json`** — ONE file shared by every
runner — and `job_id == run_id` for every backtest this app starts, so the lookup could only ever
be wrong. **Measured on the live file when this was found: it held `"j2"`,** a stale entry, so a
Stop would have sent `cancel_job("j2")`, had the failure swallowed by `except Exception: pass`,
marked THIS run `failed_cancelled`, released its platform lock — **and left the real job running.**
With two platforms busy it cancels the *other* platform's job. `clear_progress()` on the next line
blanked another platform's live progress the same way; it is now conditional on the entry being
ours.

⚠ **`job_stopped` is reported separately**, exactly as the optimizer's cancel does: the row is
cancelled either way, but *the runner acknowledged* and *we could not reach it* are different
facts and only the first means the machine is free.

### Cancelling did not stop the poller, so a cancelled run came back as `complete`

🔴 `run_backtest_job` never re-read the row, so when the agent eventually finished,
`_handle_complete` wrote KPIs and `complete` straight over `failed_cancelled`. The same "cancel did
not cancel" defect the Optimizations audit fixed on 2026-08-04, still live here.

`run_was_cancelled(run_id)` reads the DB — **the single lock source, therefore the single place a
cancellation is recorded** — and the poller stands down. Three rules hold it:

- **The router marks the row BEFORE it reaches for the runner.** The other order leaves a window in
  which the job finishes and overwrites the cancellation.
- **`_handle_complete` re-checks AFTER fetching results**, not only before. That await is where a
  Stop lands most often, and everything below it writes.
- ⚠ **An unreadable row answers False.** The poller carrying on is recoverable; abandoning a live
  run because sqlite was momentarily busy is not.

### A rerun left every artefact except two, so the page showed the PREVIOUS attempt

🔴 `retry_backtest_run` deleted `equity_curve.json` and `daily_pnl.json`. A run directory also holds
`chart_spec.json`, `blocked_setups.json`, `missed_setups.json`, `regime_timeline.json`,
`engine_timeline.json` and `ruleset_sizing.json` — **all of it derived, none of it cleared.** The
consequences are not stale numbers, they are the old run's data rendered as this one's: the spec is
CACHED, so the Price tab drew the previous candles and trades until somebody clicked Reload charts;
the blocked/missed files are written only when non-empty, so the old refusals stayed on the chart;
a rerun over a NEW window kept the old regime calendar; and a stale `engine_timeline.json` kept
`sized` true on a run that no longer was.

`_clear_run_dir` rmtrees it, on the standalone **and** the sweep and optimization retry paths —
neither of which cleared anything at all. `_handle_complete` also writes-or-UNLINKS the optional
artefacts, because an optional file's ABSENCE is what removes its chart layer, so `if blocked:`
alone left the previous attempt's refusals on disk.

### A ten-minute wall clock killed healthy jobs and blamed the agent

🔴 `heartbeat_age > _STALL_KILL_SEC or (now - started_at) > _STALL_KILL_SEC`. The second clause
cancels a perfectly healthy, heartbeating job and writes **"No heartbeat for 0s — job cancelled"**,
which points at the agent for something the lab did. Latent rather than live — the longest
completed run in this lab is 275s — but a tick-mode run, a wider window or a slower box crosses it.

`_MAX_RUNTIME_SEC` (6h) is now separate from `_STALL_KILL_SEC` (10 min of NO heartbeat), and the two
write different messages, because **a stall and an overrun are different diagnoses.**

### The runs list was N+1, and the run page pulled the whole lab for a badge

`_row_to_summary` called `get_run_verdict_summary` per row, and every call opens a fresh sqlite
connection with two PRAGMAs — on a list polled every 3s while anything runs, and read by the Runs
tab, the sweep detail and the optimization detail. ✅ **MEASURED against the live lab:
12 connections / 23.72 ms → 1 connection / 2.28 ms, with byte-identical output** (12x fewer
connections, 10.4x faster; it would be 81x on the lab as it stood a week ago).
`get_run_verdict_summaries` is the bulk form and all three list callers use it.

`GET /backtests/runs` also takes **`source_run_id`** now, so the run page can count its own tuning
iterations without fetching every run. ✅ **MEASURED: 20.6 KB → 0.002 KB and 10.5 ms → 5.3 ms.**
⚠ **It does NOT narrow to tuning iterations** — a sweep and an optimization stamp `source_run_id`
too, and telling them apart is the caller's job (they carry `sweep_id` / `optimization_id`).
Narrowing it here would make one field mean two different things depending on which query you asked.

### `_JOBS` in the python runner was never evicted

Every python backtest and every optimizer grid held its whole `results` / `combos` structure in the
backend process until somebody restarted it, for data no caller can still ask for
(`_handle_complete` fetches results exactly once). ✅ **MEASURED: a 115-trade run's output is
4.14 MB, so the 12 payloads now retained are ~50 MB — and the old code retained every job for the
life of the process.**

⚠ **The eviction drops the PAYLOAD and keeps the status metadata**, rather than deleting the entry:
`job_status` answers `failed_error` for an unknown id, so a straight delete would turn *this
finished an hour ago* into *this failed* for any late poller. A shed job's `job_results` raises and
says so, which is correct — the data is genuinely gone.

### `cost_layers` could not be sent as `null`

`BacktestRunRequest.cost_layers` was `list[str] = []`, so the Run modal sent `[]` for NT8 and MT5 —
and `[]` means *deliberately charged nothing*, which the detail page renders as **"This run was
deliberately frictionless"** over a tester that really did charge the commission and slippage on the
same row. It is `Optional[list[str]] = []` now.

⚠ **The KEY BEING ABSENT and the key being explicitly `None` are different requests**, and
`insert_run` keeps them apart: absent (sweeps, stacks, every caller with no opinion) → `[]`, so a
new python run can never fall into the legacy commission/slippage branch by omission; explicitly
`None` → NULL, which is the honest description of a runner that has no layer switches at all.

### `_DEFAULT_CAPITAL`

`python_runner` read `spec.get("deposit") or 10_000` and **nothing in this app has ever set
`deposit`** — a constant wearing the shape of a setting. It is named now, because the run page has
to agree with it: a self-sizing strategy compounds off this balance, so it is the only honest
denominator for a percentage drawdown, and the page reads it back off the run's own equity curve
rather than off an evaluated ruleset's `account_size` (a different account entirely).

### Two audit findings were WRONG, and are recorded as wrong

Both were flagged as efficiency problems and both were over-flagged; measuring is what settled it.
**`compute_regime_breakdown` on every detail GET** is a linear pass over ~1,500 daily rows and ~165
trades, and **`/repriced` walking the curve four times** is 4 × 165 iterations — the WHOLE endpoints
measure **20.1 ms and 19.3 ms** end to end. Neither is worth a cache, and adding one would be
complexity bought with nothing. *A cost guessed at is the same error as a number guessed at.*

### The `python` lock scope was computed, declared, read — and never served

🔴 **Found by DRIVING the fixes rather than by reading them (2026-08-06).** A real python backtest
was started to press Stop against, and `GET /backtests/running-job` reported
`python.running = false` **while the run's own row said `running`.**

`get_running_job` in the ROUTER built its response by naming fields — `nt8=…, mt5=…` — and never
passed `python`. Every other layer of that scope was built and correct: `lab_db.get_running_job`
computes it, `RunningJobStatus` **declares** it, `lib/runner.ts` resolves it and `runningJobFor`
reads it. Because the model declares a default of `running=False`, **the omission was silent and
the answer was the most reassuring one available.**

⚠ **The GATE was never affected, and that distinction is the whole severity assessment.**
`ensure_platform_idle` reads `has_running_job`, which was right — ✅ **proven live: a second python
run submitted during the first was refused `409 An Python job is already running`.** So nothing
could ever double-run. What broke is every control the UI gates on this response — the Runs list's
Rerun, the detail page's Retry and Rerun, the Run modal, the Optimize button — all of which stayed
enabled through a python run and could only ever produce a 409 toast. **A button whose single
outcome is an error is the same defect this audit fixed twice elsewhere.**

⚠ **The response is DERIVED from `_SCOPE_RUNNER_SQL` now, never restated field by field.** Naming
the keys is what let one go missing. This is the `entry_ms` / `exit_ms` / `favorable` / `is_trades`
trap arriving from the OPPOSITE direction, and it is worth separating: those were fields the MODEL
failed to declare, so the value never left the backend. Here the model declared it and the
CONSTRUCTOR failed to fill it — and a declared field with a default cannot be caught by the same
reasoning, because nothing is missing from the response. **Ask not only whether the model declares
a field, but whether anything actually assigns it.**

✅ **Verified live after the fix**: `python.running=true`, `job_id` matching the run, description
`MPC SOS Fade on XAUUSD`, and `false` again the moment it finished.

### Driven against a real running job, not only against mocks

The Stop path is the largest fix here and every test of it drove the router and the poller with the
runner MOCKED, so it was driven for real before being believed:

- **A full-history python backtest was started and stopped mid-replay.** `job_stopped: true`, the
  row `failed_cancelled` in **287 ms**, the platform lock released immediately, and the row still
  `failed_cancelled` **120 seconds later** — well past the point the old code wrote `complete` over
  it. The python job's own log reads `[failed_cancelled] cancelled`, i.e. it reached a terminal
  state, so the wait was not vacuous.
  ⚠ **What that drive does NOT prove is the resurrection guard itself**: the cooperative cancel
  makes the python job report `failed_cancelled`, so the poller takes the failure branch rather
  than the completion one. The `complete`-over-`cancelled` case is covered by
  `test_a_cancelled_run_does_not_come_back_as_complete`, which calls `_handle_complete` with real
  results on a cancelled row. Say which half is measured and which is unit-tested.
- **A rerun was fired at a run whose `chart_spec.json` had been built.** Six artefacts before
  (including the cached spec), **zero immediately after the retry**, five rebuilt on completion.
  That is the defect's visible consequence — the Price tab can no longer serve the previous
  attempt's candles — rather than just the directory call.

🔴 **The dev server wedged once during this drive, was recorded as UNEXPLAINED, and is now
DIAGNOSED AND FIXED (2026-08-06) — and the hypothesis that stood in for it was wrong.** The
uvicorn worker went unresponsive at 0% CPU with the reloader still holding port 8000. The stated
guess was a reload killing a replay thread mid-flight. **It is not that, and it has nothing to do
with backtests: `touch main.py` on an idle server reproduces it exactly**, /health going from
`200` in 19 ms to a hard timeout, the same worker PID alive at 0% CPU twenty seconds later.

**The mechanism, measured end to end.** On a reload the reloader asks the worker to stop and then
JOINS it; the worker's own shutdown waits for open connections to close. **The Vite dev server
holds a keep-alive POOL to port 8000 — `lsof` counted 19 established sockets from one `node` PID —
and an idle keep-alive socket is never going to close on its own.** So the worker waits for ever,
the reloader waits for the worker, and the listening socket stays bound with nobody accepting on
it, which is why every request HANGS rather than being refused. `/usr/bin/sample` (no root needed,
unlike py-spy) put the main thread in `uv__io_poll` inside `run_until_complete` — a live event loop
awaiting a shutdown that cannot finish. Confirmed from the other end too: `kill` on the reloader
did nothing until the worker was `kill -9`'d, at which point the reloader immediately spawned a
replacement.

**The fix is one flag in `start.sh`: `--timeout-graceful-shutdown 10`.** ✅ Proven by reproducing
the same sequence with the pool rebuilt to 14 sockets — `200` in 1.9 ms after the reload, and again
on a second file — with `Application shutdown complete` / `Started server process` in the log both
times. 10s is deliberate: it clears the slowest measured request on this app (a cold ChartSpec
build, 7.6s) so an in-flight request still finishes, and only ever bounds the wait on sockets doing
nothing. `tests/test_dev_server_flags.py` guards it, **2 of its 4 checks watched RED against the
old `start.sh`**, and every grep in it asserts it matched something first.

⚠ **The standing lesson is about what an undiagnosed failure costs, and it is uncomfortable: the
hypothesis was plausible, related, written in the right file — and it sent the next reader at
`--reload` and replay threads, which is the half of the system that was innocent.** The thing that
actually cracked it was refusing to reason and running `touch main.py` on an idle box. **A recorded
guess is not a cheap placeholder for a diagnosis; it is a signpost, and a wrong one costs more than
no sign at all.** ⚠ **And the failure itself is this repo's silent-failure shape in a new place:
nothing logged, nothing crashed, the port still answered `LISTEN`, and every symptom pointed at the
app rather than at its supervisor.**

### Tests

**25 new (723 green), in `tests/test_backtest_lifecycle.py`, `tests/test_run_list_queries.py` and
`tests/test_dev_server_flags.py` (the last 4 added with the reload-wedge fix above, 2 of them
watched red against the old `start.sh`).**
**17 of the 21 were WATCHED RED against the code at HEAD.** The four that passed there are kept
and **labelled as such in their own docstrings**: one pins that our own stale progress entry is
still cleared (the old code did it unconditionally, satisfying this by accident while failing the
test beside it), one pins that adding the `source_run_id` filter did not narrow the UNfiltered list,
one pins that an omitted `cost_layers` still means `[]`, and one is a FORWARD guard that every
scope in `_SCOPE_RUNNER_SQL` reaches the API (it could not be red, because the model declares all
three keys — which is precisely what made the `python` omission silent). Each is the half of a rule
that was already right, and a rule stated in one direction is the one that gets "simplified" back.

## The Strategies page — the 2026-08-06 audit

Aaron asked for a full audit of the page — Strategies tab, Deployed tab, Scan — with one reported
symptom: *"if the NT8 agent is down I get this annoying error about remote end closed connection
without response, every couple of seconds."* The toast storm is the shallow half. **The reason it
was a storm and not a banner is that every one of these endpoints treated an unreachable agent as
a fatal error rather than as an unanswered question**, and the page polls.

🔴 **A dead NT8 agent blanked the status of every strategy, including MT5 and Python ones.** Both
`GET /strategy-files` and `GET /strategy-files/sync-status` raised a 502 on any NT8 exception while
swallowing an MT5 one with a bare `pass`. **The consequence on the page is worse than a missing
badge: a row with no sync object rendered no status pill and a Run button — so a strategy that
needed deploying looked ready to run.** Both endpoints now return an envelope
(`StrategyFilesResponse` / `StrategyFileSyncResponse`) carrying `files`/`statuses` plus `nt8_error`
and `mt5_error`, and both platforms are caught symmetrically.

⚠ **The split that makes the degraded response worth serving: `needs_deploy` and `needs_compile`
survive an unreachable agent, and `file_exists_on_vps` / `in_sync` / `is_compiled` go `None`.**
`needs_deploy` is the LOCAL source hash against this app's own deploy record — it is answerable
with the VPS switched off — while the other three are claims about the box. Nulling everything
would have been safe and useless; nulling nothing is the defect above. **Ask of each field whether
the thing that answers it was reachable, not whether the request succeeded.**

⚠ **`is_compiled` defaulted a missing column to `1`** (`s.get("is_compiled", 1)`) — a fabricated
COMPILED, this repo's own rule broken in its usual direction. `None` now, and the page renders no
claim rather than a green one.

🔴 **`nt8_running` and `nt8_sa_visible` initialised to `False` in `_build_health`**, so with the
agent down the sidebar reported *NinjaTrader is not running* — a measurement nothing took, and it
was exactly wrong on 2026-08-06: NinjaTrader was open on the VPS the whole time the agent was
wedged. Both are `Optional[bool] = None` now, the same three-state contract as `mt5_connected`.

**MT5 `needs_compile` was hash-only, so deleting the `.ex5` off the box left the row reading "In
sync".** MT5 loads the compiled artefact, so its absence is the question — `needs_compile` is now
also true when the source matches its deploy record and `is_compiled` is `False`.

**`POST /strategies/{id}/deploy` 500'd on a python strategy** — a python strategy is a package
DIRECTORY, so `read_bytes()` raised `IsADirectoryError`. It is a 400 that says why. Latent (the UI
never offers the button), which is precisely the kind of endpoint something else calls later; the
existence check also became `is_file()`. **`GET /strategies/{id}/deploy-status/{job}` served any
job from any strategy's URL** — it 404s on a mismatch, so the path segment means something.
`_deploy_jobs` is an `OrderedDict` capped at 50; nothing had ever removed an entry.

**A python package whose import failed was indistinguishable from one that is not a lab strategy** —
`_parse_python_package` returned a bare `None` for both. The row kept its STALE param schema,
`needs_scan` stayed true for ever, and the scan reported success with *0 updated*: a silent failure
whose only symptom was a pill that would not clear. It returns `(row, error)` now and the error
lands in `ScanResult.warnings`, which the frontend toasts. **A package that simply does not declare
`LAB_STRATEGY` stays silent — that is the normal state for a helper package, not a fault.**

**`is_orphan` is on the strategy row, not only in a scan result.** The Reconcile button was gated on
`scan.data?.orphans` — mutation state — so a strategy whose source file had been deleted was
invisible on a fresh page load until somebody happened to press Scan. `strategy_scanner.is_orphan`
is the read-only per-row twin of `_detect_orphans`. **A standing fact belongs on the row that states
it, not in the result of the action that last noticed it.**

**Tests:** 16 new (693 green). ⚠ **A clean fail-watch against `HEAD` was IMPOSSIBLE here and the
honest note is that it was not done** — the two endpoints changed shape from a bare list to an
envelope, so the old frontend fails against the new backend for reasons unrelated to any defect.
Non-vacuity was established by **mutation instead**: each fix was removed in turn and the naming
test confirmed red. That found a real hole — see `frontend/CLAUDE.md` → *The Strategies page*.

## Portfolio stacks (smart reuse)

A **stack** layers 2+ Python strategies over ONE shared instrument + timeframe + window + cost profile. The combined portfolio line and per-strategy toggles are composed CLIENT-SIDE from each leg's `daily_pnl`, so there is no stack-level result row and toggling a leg off never re-runs anything.

**Ownership ≠ membership (the reuse enabler, 2026-07-25).** Two tables:
- **`stacks`** — the stack's own settings (`instrument`, `bar_type`, `bar_value`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `created_at`). Persisted so a stack whose legs are ALL reused (zero owned child runs) still knows what it is — `list_stacks`/`get_stack` read settings from here, not from a child row.
- **`stack_members(stack_id, run_id, owned, position)`** — membership. `owned=1` = a fresh run the stack created (carries `backtest_runs.stack_id`, hidden from the Runs tab, **deleted with the stack**). `owned=0` = a pre-existing standalone run REUSED as-is (`stack_id` stays NULL, **stays in the Runs tab, survives stack deletion**). `list_stack_runs` INNER JOINs members→runs so a reused run the user later deletes simply drops from the stack instead of 500-ing.

**Smart reuse on create (`trigger_stack`).** For each leg, `find_matching_stack_run()` looks for the most-recent COMPLETED **standalone** Python run (`stack_id IS NULL AND stress_test_id IS NULL AND sweep_id IS NULL AND optimization_id IS NULL`) matching the leg's EXACT identity — strategy + instrument + `bar_type` + `bar_value` + window + `commission_per_side` + `slippage_ticks`. Match → add an `owned=0` member, no re-run. No match → create an `owned=1` child and queue it through `run_sweep` (unchanged). The python job lock is only taken when ≥1 leg needs a fresh run; an all-reused stack is assembled instantly and returns `status="complete"`. A per-strategy `params_by_strategy` override **disables reuse for that leg** ("run it my way", not "reuse whatever exists").

**Matching is STRICT by Aaron's call (2026-07-25)** — any difference (even a one-day window shift or a different cost field) misses and the leg re-runs. Do NOT loosen it without asking. **Cost defaults are 0/0** (`commission_per_side=0`, `slippage_ticks=0`, `bar_value=15`) — matching the Pine strategies, which are all pinned `commission=0, slippage=0` for TV↔Python parity (costs are modeled inside the strategy via the 30-tick breakeven buffer). **These fields are cosmetic for Python runs** — `python_runner` never reads them; the real cost comes from the strategy's account profile (`backtest/fills.py` `PROFILES["vantage_demo"]` = commission 0.00) + measured (tick) / 0 (bar) slippage. So they're the displayed + leg-matching values, not the applied ones. The stack's original bug was the **5m timeframe** (vs the designed 15m), not costs — a stacked leg read ~⅓ of the same strategy's standalone run because it ran on entirely different signals. The forex rulesets (`personal_forex_demo`, `unconstrained`) also seed `default_slippage_ticks=0` (converged on existing DBs in `init_db`) so the Run modal shows 0/0 too; futures rulesets keep `2.25/1` (NT8/MT5 platforms genuinely apply them).

**`POST /backtests/stacks/preview`** (`StackPreviewRequest` → `StackPreviewResponse`) reports per-leg `action` (`reuse`|`run`) + the matched run's `net_pnl`/`trade_count`/`profit_factor`, running nothing — it drives the modal's live Reuse/Run badges. **`GET /stacks/{id}`** (`StackDetail`, async) now also carries `commission_per_side`/`slippage_ticks` (from the settings row, for the Rerun modal) and a full-calendar `regime_timeline` for the shared window (drives the equity chart's regime overlay). Regime source: read from a leg's `regime_timeline.json` if present; sweep-child legs aren't regime-tagged, so when none exists it computes the timeline once via `build_regime_timeline_and_tag(..., runner="python")` (off-thread) and caches it to the base leg's dir so later polls read the file. **`build_stack_chart_spec`** carries the base leg's structure `overlays`/`indicators` (a property of the market on the shared candles, identical for every leg) and a `base_run_id` — so the stack's price chart has full BacktestDetail parity (structure layers, ATR pane, fib/measurement, and M1/M5 drill-down routed through the base leg's `/candles`). **`delete_stack`** removes only `owned=1` legs from `backtest_runs` (+ their report dirs, via the router) and clears the `stacks`/`stack_members` rows; reused legs are untouched. `_backfill_stack_membership` (in `init_db`, idempotent) materialises `stacks` + owned `stack_members` for any legacy pre-membership stack so old stacks survive. Python-only: summing daily P&L models independent sleeves, and NT8/MT5 have their own single-window terminals a lab stack has no reason to touch.

## Shared-account stacks — one balance, one budget, N bots competing for it

**Landed 2026-08-09.** `services/portfolio_runner.py` + the `mode` branch in `routers/stacks.py`.
Plan and the measured first run: `command-center/docs/SHARED_RISK_STACK.md`.

**A stack is now one of two DIFFERENT experiments over the same legs, and almost every rule here
is about keeping them apart.** A `screen` runs each leg as its own standalone backtest and adds
the results together — every leg sized as if it owned the account, nothing could block anything,
so it is an UPPER BOUND. A `shared` stack replays them together on one balance with one risk
budget they compete for. Confusing the two produces numbers that look perfectly ordinary and
answer a question nobody asked.

### It CALLS the simulation and owns no copy of it

`backtest/portfolio/run_stack` is the account model. This module builds legs from lab rows, runs
it on a thread and persists what comes back. **A second account model here would be a second
answer about what a shared budget does** — and the live allocator (`docs/LIVE_TRADING_PIPELINE.md`
→ G10) already has to be a third implementation, because live bots are separate OS processes that
cannot share an in-process object. Two is the most this rule can afford.

### What the first real launch found, before it found anything about portfolios

🔴 **It died in a background task on the first attempt.** `mpc_sos_fade`'s `exec_secondary` (the
1-minute re-entry) has defaulted **ON** since 2026-08-07, it needs a second bar stream through
`run_dual`, and a leg on a merged clock is one frame — so `legs._refuse_unreplayable` raised and
the only trace was a string in a progress field.

`_SHARED_LEG_PINS` in the router pins it ahead of that refusal, and two things about the fix
matter more than the pin:

- ⚠ **The pinned value is written onto the CHILD RUN**, not applied at replay time. Overriding
  during the replay while the stored row said `exec_secondary: true` is this app's most-repeated
  defect — a page stating a value no code read. Here the row and the replay agree, so that leg's
  own detail page is telling the truth about what ran.
- ⚠ **`tests/test_shared_stack.py` READS `backtest/portfolio/legs.py`** and fails if
  `_refuse_unreplayable` grows a refusal the router does not pin. A hand-written copy of that list
  here would be a second claim about one rule and would go stale in silence — the same arrangement
  `test_notification_routing.py` and `test_bot_versions.py` use.

### The schema change needed BOTH declarations, and only one of them is obvious

⚠ **`mode` / `account_size` / `risk_cap_pct` / `entry_floor_pct` are declared in the idempotent
migration list AND in the `stacks` CREATE TABLE.** The migrations run FIRST, so on a fresh
database the `ALTER TABLE stacks` lines fail (no table yet) and are swallowed by the
try/except — leaving a brand-new clone **without** the columns while every existing database has
them. That is the worst shape a schema change can take: it works on the machine that ran the
migration and breaks everywhere else. Both directions are proven by test.

⚠ **`mode` defaults to `'screen'`.** Every stack written before the column existed WAS a screen,
and defaulting to `'shared'` would relabel finished results as a simulation nobody ran.

⚠ **The account knobs are NULL on a screen, never 0** — `insert_stack` drops them rather than
storing what the request happened to carry. A screen has no account (each leg traded its own full
one), a stored `0` renders as an account with no money, and `risk_cap_pct = 0` — which refuses
every entry — would be indistinguishable from "this stack never had a cap".

### A shared stack reuses nothing, and always takes the lock

Both are departures from the screen path and both would be defects if copied across:

- **No reuse, ever.** A finished standalone run was measured on its own full account with nothing
  able to block it. Dropping one into a shared stack puts an un-contended leg beside contended
  ones and calls the pair a portfolio. The screen's reuse optimisation is only sound *because* a
  screen never claims the legs interacted. `POST /stacks/preview` takes the mode for this reason —
  otherwise the modal offers a reuse count for a run that will replay everything regardless.
- **It always takes the python lock**, because there is always work: `run_stack` is
  `1 + len(legs)` full replays (the shared book plus one solo CONTROL per leg).

### Cancel reaches the replay, and a cancelled book is not persisted

`simulate` gained `progress` / `should_cancel` (polled every 512 ticks — the check is cheap and
the loop body is cheaper). A full-history two-leg stack is four replays over ~150,000 bars, so a
Stop button that cannot reach that loop is a Stop button that does nothing.

⚠ **A cancelled `StackRun` RETURNS with `cancelled=True` and a PARTIAL book**, and the runner
refuses to persist it. That book holds every trade closed up to the tick it stopped on, which is
indistinguishable from a complete short backtest once written to disk — persisting it is the
"cancel did not cancel" defect from the other side: not a run that carried on, but a stopped run
recorded as a finished one.

⚠ **A cancelled shared run also skips the SOLO CONTROLS.** A control's whole job is to be
comparable to the shared book, and a control over the full history beside a book that stopped a
year in is two different experiments in one table — the screen-vs-shared delta would report the
missing year as the cap's doing.

⚠ **`_is_cancelled` reads the DB rows** (the single lock source) and answers **False** on an
unreadable row. Carrying on is recoverable; abandoning a multi-minute replay because sqlite was
momentarily busy is not.

### What is persisted, and the check it stores

`reports/lab/<stack_id>/` holds `contention.json` and `shared_summary.json`; each leg is written
through the same shape `sweep_runner._handle_complete` uses, so the existing drill-in detail page
works on a shared leg with no branch of its own. **The stack's own directory is deleted with the
stack** — no child run references it, so deleting only the children leaves it behind, which is
how `reports/lab` reached 191 directories against 84 runs before the stress-test audit.

⚠ **A leg's equity curve here is its CONTRIBUTION, not its balance.** It is walked from the
account's opening balance over that leg's own trades, because the real balance path belongs to the
shared account and there is no such thing as "this leg's balance" once the two compound together.
The legs' daily P&L still SUMS to the shared account's, which is what the page composes the
combined line from.

`shared_summary.json` carries a `neutral` verdict, and it is the one thing this artefact can
CHECK rather than report: **R is normalised to the trade's own risk, so with nothing refused a leg
must post the SAME R shared as solo.** A difference there is the shared account moving a decision
it must not touch — a defect in the seam, not a portfolio effect — and it is invisible in a table
of numbers unless something says so out loud.

### The SOLO CONTROL is a BOOK, not two scalars

**2026-08-10.** `run_stack` has always replayed each leg alone as a control, and `_persist` kept
only `solo_r` and `solo_closing_balance` from it. That is enough to CHECK the seam — with a full
budget a leg must post the same R shared as solo — and not enough to SHOW anyone, so the page
composed "what would the rest of this have made without that strategy" out of the SHARED trades.

🔴 **Those trades are sized off a balance every leg compounded onto, so that composition answers a
different question and reads as the right one.** Measured on `st_94aeb25f0c`, MPC B-LEG:

| | solo | in the shared stack |
|---|---|---|
| trades | 99 | **99 — same entry timestamps, same entry and stop prices** |
| total R | **+17.8674** | **+17.8674** |
| win rate | 51.5% | 51.5% |
| risk on the last trade | $3,102 | **$16,925,791** |
| net | **$21,064** | **$47,758,999** |
| profit factor | 1.505 | **3.111** |

`_write_solo` persists the control to `<stack_dir>/solo/<strategy_id>/`, `solo_book` reads it, and
the leg serves it as `solo_equity_curve` / `solo_daily_pnl`.

- ⚠ **The control gets NO run row and NO evaluation.** It is not a lab run — nobody requested it,
  it has no id to navigate to, and putting it in `backtest_runs` would list a backtest nobody
  launched.
- ⚠ **A SCREEN is served nothing, and that is not a gap.** There every leg already traded its own
  full account, so the leg's own curve IS the solo answer; a second field would be two copies of
  one fact that can disagree. `_solo_fields` reads the mode off the SETTINGS row — a leg row
  carries no mode, so reading it from `first` would answer `None` on a legacy stack and silently
  withhold the book from a shared one.
- ⚠ **Absent is `None`, never `[]`.** A stack replayed before this landed has the scalars and no
  book, and the page renders a refusal there rather than an empty curve — the *no data is not the
  same as cannot ask* rule, on the page that met it.
- **`scripts/backfill_stack_solo.py`** re-derives the book for older stacks. ⚠ It **re-runs** the
  replay (nothing was written to recover), which is `1 + legs` full replays — the same work a
  Rerun does, except it touches no stored row, KPI or leg curve. It reproduced the stored scalars
  exactly on the live stack, which is the check that says it replayed the same thing, and it
  refuses to overwrite an existing book without `--force`.

🔴 **`models.EquityPoint` did not declare `r`, and this is the FIFTH time that model has dropped a
field already on disk** (`entry_ms`, `exit_ms`, `favorable`, `adverse`, now `r`). `backtest/output.py`
has written it since 2026-08-03 and `reprice.py` reads it straight off the file, so the value was
there the whole time and never reached the browser. **It is the one per-trade figure a change of
position SIZE cannot move**, which is precisely what a portfolio page needs: a leg's R is the same
shared or solo while its dollars differ by orders of magnitude.

### The report distinguishes its three "no answer" cases

⚠ **`available: false` is THREE answers and a caller must not collapse them**: this stack is a
SCREEN (no account exists to contend over), it is still RUNNING, or it failed. `progress`
separates the second; `StackDetail.mode` separates the first.

⚠ **`events: []` under `available: true` is the OPPOSITE of all three — a real measurement that
nothing was refused, and it is the EXPECTED result.** Open risk is measured to each trade's
current stop, so a stop moved to breakeven releases its room before the other leg asks. Read it as
*the budget would rarely have had anything to arbitrate*, never as *the cap is not working*.

⚠ **`_PROGRESS` is in-process and nothing may ever recover an IDENTITY from it.** It drives one
progress line. `lab_progress.json` was read for a job id on 2026-08-06 and a Stop cancelled an
unrelated platform's job; the rule that came out of it is that a channel built to carry a STATUS
must never be asked who something is.

⚠ **No `cost_layers` / `broker_profile` yet**, which is the current state of stacks generally
rather than a decision — the `stacks` table does not carry those columns, so a shared stack takes
the legacy commission/slippage branch like every other stack. **Wire them for BOTH modes at
once**, or a screen and a shared run over the same legs would be measured on different physics and
the delta column would report the cost gap as the cap's doing.

## History floors — blocking a window the broker has no bars for

**MT5 does not error when a symbol lacks history at the requested timeframe — it returns the nearest
COARSER bars, still labelled as what you asked for.** A backtest fed daily bars as 15m does not crash:
it produces a full trade list, a clean equity curve, and a completely fictional answer. So the lab
refuses the window instead of running it.

The floor is **measured, never hardcoded**: `backtest/data/history.py` binary-searches the live
terminal by bar density and caches per `(server, symbol, timeframe)` — swap MT5_Lab to a broker with
deeper history and the limit widens by itself. `services/history_limits.py` is a thin shim over it and
declares no dates of its own; duplicating them here would guarantee the UI and the data layer
eventually disagree, and the disagreement would surface as a run that passes validation then dies
mid-flight.

- **`GET /backtests/history-limit?instrument=&bar_type=&bar_value=&runner=[&refresh=]`** → `HistoryLimit`
  (`earliest_date`, `broker`, `verified`, `source: probed|seed`, `note`) or **`null`** when unbounded.
  The frontend date picker reads this instead of hardcoding a date. `refresh=true` re-probes (~15s).
- **400 at every trigger that accepts dates**, checked BEFORE the platform lock is taken or a run row
  is inserted: `POST /backtests/run`, `POST /runs/{id}/retry` (period override), `POST /backtests/sweep`
  (per instrument), `POST /optimizations/run`, `POST /backtests/stacks`. `BarSource.load` raises too, so
  a path that forgets the check still cannot replay substituted bars — but it raises at FETCH time, by
  which point a row exists, a lock is held, and the user is watching a progress bar. That is the whole
  reason the router-level check exists as well.
- **Python runner ONLY.** NT8 (NinjaTrader) and MT5 pull history from their own terminals, so their
  depth is a different question with a different answer. `limits_for()`/`validate_window()` return
  None / no-op for them. Claiming a Vantage gold floor on an NT8 futures run would be a lie in the
  more dangerous direction.
- **`null` means UNKNOWN, never "unlimited"** — agent down, or a broker we cannot identify. Nothing is
  refused on a guess; the data layer's bar-spacing backstop still catches substituted bars.

Full mechanism, the evidence table, and the probe's two-phase design: `backtest/CLAUDE.md` →
*History floors*.

## ChartSpec candles — cap the WINDOW, never the timeframe

6.5 years of M15 is ~160k candles and a ~15 MB `chart_spec.json` on every chart open. Something has
to give. There were two axes to give on, and the first choice was wrong:

- **Coarsen the bars** (the old `_fit_timeframe`: that run shipped **H4**). Covers the whole span —
  and is useless, because H4 is a timeframe the run's trades and blocked setups line up with nowhere.
  It also forced a fetch-on-open to get back to M15, which meant a loading placeholder and a visible
  swap on every chart open.
- **Trim the window** (`_capped_start`, 2026-07-27, Aaron's call). Ship the run's OWN timeframe over
  the newest slice that fits `_CANDLE_CAP`. Measured on that same run: **33,041 candles / 3.1 MB /
  17 months**, painted on the first frame with no fetch at all.

Reach is restored by PAGING, not by coarsening: `historyStartMs` (the run's start) tells the panel how
far back it may go, and scroll-left pulls one page at a time through `GET /runs/{id}/candles`
(measured: 175d / 11,255 candles / ~1.0 MB / ~1.5s at M15). So trimming costs reach, not access.

**And a page carries the window's ANALYSIS, not just its bars (`analysis=true` → `_page_analysis`,
2026-08-02).** For a year that was only half true: the bars paged in and everything drawn ON them —
structure overlays, fair value gaps, blocked and missed setups — did not, because all of them are
built over `candles` and `candles` stops at `ship_from`. Scroll past that boundary and each layer
the reader had switched on drew nothing, with its toggle still on. Two rules hold it together, both
pinned by `tests/test_chart_page_analysis.py`:

- **Warm-up is context, not content.** The structure and FVG engines are streaming state machines,
  so a page is replayed over its window PLUS `_PAGE_WARMUP_BARS` (2,000 ≈ 30 trading days at M15)
  of older bars, and only overlays whose span reaches into `[from_ms, to_ms]` are returned. Without
  the prefix every page opens with no swings and no live gaps; without the filter the previous
  page's overlays are served twice.
- **A page's internal structure is HISTORIC** (`_demote_page_internal`). `build_market_structure_overlays`
  labels the newest leg in whatever it replayed "current", so each page would claim its own current
  leg — a group whose whole meaning is "the leg the run is in NOW", which exists only in the shipped
  window. The demotion carries the historic branch's own `requires` shape so the four toggles keep
  nesting.

It is best-effort and wrapped in its own `try`: the page is about its BARS, and a failed replay must
never cost the reader the history. Drill-down passes `analysis=False` — structure is computed on the
base timeframe, and a 1m view is a question about fills.

`baseTimeframe` and `runTimeframe` are now the SAME value. `runTimeframe` stays on the contract
because a `chart_spec.json` cached under the old scheme still carries a coarsened `baseTimeframe`,
and the panel opens on `runTimeframe` — which keeps those caches usable until they rebuild. Every
cached spec was cleared when this landed; they rebuild on next chart open (~5s for a 17-month M15).

## Blocked setups — the trades that never happened

A signal the strategy had READY and one of its OWN rules refused places no order, so it appears in
no trade list, no equity curve, no `engine_trades`, and no broker report. Nothing downstream can
infer it. That makes it impossible to judge whether a blocking rule protects the account or costs
it — which is the whole reason this channel exists.

The path is one straight line, and every hop is OPTIONAL so a runner that can't report them is
simply silent (never a lie, never an empty UI):

1. **The strategy records them.** `mpc_sos_fade/execution.py` — `BlockedSetup` + `_record_blocks`,
   a port of `mpc_strategy.pine`'s pink `TRADE BLOCKED` tag (4025-4086): the same six reason codes,
   the same PRECEDENCE, and the Pine's `sosBar*10 + code` dedupe generalised to the reason SET (one
   record per setup per distinct combination, not per bar). **One deliberate deviation:** the Pine
   reports the FIRST blocker only (a chart tag has room for one line); we record EVERY rule refusing
   the setup, because the lab filters by reason and "blocked by the veto" must stay true when the
   final hour was also blocking. Precedence survives as the ORDER, so `codes[0]` is exactly what
   `f_blkCode` would have returned — a per-reason count off the primary still reconciles with
   TradingView. **Reporting only** — nothing reads a record back, so it cannot move a decision and
   `compare_strategy.py`'s `px_*` stream is untouched. `mpc_bleg` records none by construction (its
   `BLegExecution` overrides `_place_entries`, where the recording hangs) — deliberate: those codes
   describe why an **A+** setup was refused, and A+ never trades in that fork.
2. **`backtest/output.py`** — `build_blocked_setups()` turns them into the lab's row shape;
   `build_results` returns them as `blocked_setups` (always present, `[]` when there are none).
   Strategy-agnostic duck-type: `dir`/`time_ms`/`edge` plus parallel `labels`/`reasons` sequences,
   emitted as a `reasons: [{label, reason}]` LIST (primary first).
3. **`backtest_runner._handle_complete`** writes `reports/lab/<run_id>/blocked_setups.json` when the
   runner reported any. Runner-agnostic — NT8/MT5 return no such key, so no file.
4. **`chart_spec._build_blocks`** reads that file into the spec's `blocks[]`, clipped to the candle
   window (same reason trades are). No file ⇒ `[]` ⇒ the chart's Blocked toggle never appears. The
   chart builds its per-reason filter roster straight off those label strings, so nothing between the
   strategy and the UI needs to know what any rule means.

**Only runs completed AFTER this landed have the file** — it is written at completion, and there is
no backfill (recomputing it would mean replaying the strategy). An older run's chart correctly shows
no Blocked layer. A run that HAS the file but a stale cached `chart_spec.json` needs **Reload charts**.

The `label`/`reason` strings are the STRATEGY's own words end to end; neither the lab nor the chart
interprets them, so a strategy with a different rule set needs no change anywhere in this path.

## Missed setups — how close the ones that died came

A **block** and a **miss** answer the same question one step apart in a setup's life. A block is a
trade the strategy had FULLY READY and one of its own rules refused. A miss never got that far: it
met some of the strategy's confluences and then DIED. Both place no order, so both are invisible
everywhere else; separately they answer "is this rule costing me?" and "what am I actually waiting
on that never arrives?".

The path is the block path, hop for hop, and every hop is equally optional:
`mpc_sos_fade/execution.py` (`MissedSetup` + `_record_misses`, a port of the Pine's orange 2-of-3
callout — see that package's CLAUDE.md → *The missed-setup watch*) → `backtest/output.py`
`build_missed_setups` → `missed_setups.json` in the run dir → `chart_spec._build_misses` →
`spec.misses[]` → the price chart's **Analysis → Missed** layer, default OFF.

**The one thing that is NOT a copy of the block path: `spec.missNoise`.** `_build_misses` returns a
second value — the reason labels the chart should start with UNTICKED — and it is **derived, never
named**. A label goes on the list when it never once appears on a miss the strategy flagged `near`.
Why this exists: the Pine's callout defaults to "Near misses only" because a chart showing every
setup that simply never retraced is unreadable, and on the measured window that is 50 of 93 markers.
Reproducing that default by teaching the chart what "No retrace" means would have put a strategy
concept inside a panel whose one rule is that it has none. Instead the strategy marks `near`, the
emitter turns it into a list of strings, and the panel hides those on first render. The panel still
lists them with their counts, so nothing is hidden silently, and one click brings any of them back —
which the Pine's radio buttons cannot do.

⚠ **A miss's `time` is the bar the setup DIED, and nothing may read it as "where the setup was".**
`zoneTime` / `zoneTurn` carry that instead — the retrace it was waiting on, recorded by the strategy
(2026-08-08). ✅ **Measured on the reference run: on 32 of the 35 three-of-three misses, price sits a
median $22 and up to $205 from the setup's own entry edge on the death bar, and the death bar is a
median 17 and up to 717 bars after the turn.** The Candlestick Reversals layer read `time` for one
day and painted marks in the wrong part of the chart because of it. Both are `None` when price never
reached the zone, and `None` must stay `None` — a fallback to `time` is the defect, a `0` is the
epoch.

Same on-disk-shape discipline as the blocks: a record missing `near` reads as `near: True`, so a
file written before the flag existed does not have every one of its reasons filed as noise and
hidden on open (which would make an old run look like it had no misses at all). Locked by
`backend/tests/test_chart_spec_misses.py`. **Python runner only, no backfill** — same as the blocks,
for the same reason.

## Fair value gaps — only where something happened

`services/fvg_overlays.py`. Replays the canonical `engines/fair_value_gaps/` engine over the candles
the chart is about to show and emits one `box` overlay per gap, in the group `Fair Value Gaps`, which
the panel lists in its **Analysis** dropdown (default OFF). Never a second FVG engine — bare-name
import, public events only, same shim as regime / news / structure.

**A gap is drawn only if it was in the engine's LIVE list on the bar of a trade ENTRY, a blocked
setup, or a missed setup.** That filter is the whole design: a 33k-bar run leaves thousands of gaps
and drawing them all is both unreadable and an answer to a question nobody asked. When several gaps
were open at one of those bars, ALL of them are drawn — a cluster is exactly the thing worth seeing.
The anchors arrive as bare timestamps (`trades[].entryTime` + `blocks[].time` + `misses[].time`), so
the module knows nothing about what a trade or a block IS; hand it different anchors and it draws
gaps at those. No anchors ⇒ `[]` ⇒ the toggle never appears, which is the honest answer for NT8/MT5.

**⚠ These are `mpc_assistant.pine`'s gaps, and that is NOT the set the bot traded on.** The indicator
runs `fvgMaxCount 8`, `fvgRequireClose false`, and the timeframe-**split** floor
(`timeframe.in_seconds() < 900 ? 0.0 : 0.04`), with `eqExemptFvg` on — all locked constants, mirrored
here as named `MPC_*` values. `strategies/python/mpc_sos_fade` pins `fvg_max_count=7`,
`fvg_require_close=True`, `fvg_threshold_pct=0.1`, because `mpc_strategy.pine` hardcodes the
middle-bar close check and carries its own count. So the bot's entry rule counted strictly FEWER gaps
than this layer draws (`require_close` only ever removes gaps, and its floor is higher). The chart was
asked to match what TradingView draws, so it does — do not resolve the fork by repointing the emitter
at the strategy's config, and do not read a drawn gap as one a "no FVG" block ignored. Background:
`engines/fair_value_gaps/CLAUDE.md` → the `require_close` callout.

**Two details that would silently draw the wrong thing if they broke**, both pinned by tests:
- **The floor is timeframe-split**, so the same run charted at M5 and M15 legitimately has different
  gaps. An unrecognised timeframe takes the STRICTER (15m+) branch on purpose: over-filtering drops a
  marginal gap, under-filtering invents one the indicator never drew, and only the second puts
  something on the chart that is not there.
- **Box span mirrors the Pine box.** Pine creates it at `bar_index - 1`, pushes `box.set_right` every
  surviving bar, and DELETES it on the bar the gap is mitigated or evicted — so `t1` is the bar
  BEFORE its death, never the death bar. On the death bar mpc showed nothing there.

`build_stack_chart_spec` **strips this group**, for the same reason it strips blocks and misses: it
is anchored to the BASE leg's trades, so on a merged chart it would draw gaps at one strategy's
entries and nothing at the others' — which reads as "these setups had gaps and those didn't". A leg's
own page still carries it. Existing runs need **Reload charts** (`chart_spec.json` is cached).

**Tested two ways** (`tests/test_fvg_overlays.py`, 16 tests). Hand-built candles pin the layer's own
rules (which gaps, the cluster case, the box span, the timeframe split, the mpc constants). Then a
real TradingView export is replayed and every box is diffed against **the Pine's own live gap arrays**
(`px_fvg_top_k` / `px_fvg_bot_k` / `px_fvg_count`): on each sampled anchor bar the boxes covering it
must be exactly the gaps mpc had open, price for price. The unit tests could all pass on an emitter
drawing the wrong gaps; that one could not. The export is git-ignored, so those two SKIP without it —
and it predates the 2026-07-18 mpc default drift, so it is replayed with the settings ITS build ran
(which is what the config keyword arguments on `build_fvg_overlays` exist for). That the ENGINE still
matches today's mpc build is proven separately by `engines/fair_value_gaps/tools/compare_fvg.py`.

## Order blocks — the same rule, a different box

`services/ob_overlays.py`. Aaron's brother asked to see order blocks on the backtest chart, so the
canonical `engines/order_blocks/` engine is replayed server-side and a block becomes one `box`
overlay in the group `Order Blocks`, listed in the panel's **Analysis** dropdown, default OFF.
Never a second OB engine — bare-name import, public events only, the same shim as the rest.

**It is deliberately the fair-value-gap layer with one engine swapped**, down to the anchor rule: a
block is drawn only if it was live on the bar of a trade ENTRY, a blocked setup or a missed setup.
MEASURED on run `432aff31f374` (32,978 M15 candles, 217 anchor bars): **2,567 blocks created,
579 live at an anchor** — the same ratio the gap layer sees (661 there), so the two together sit at
a readable ~1,240 boxes instead of ~3,200. Read `## Fair value gaps` above first; only the
differences below are worth carrying separately.

**THE BOX IS A STUB, NOT A LIVE-BAR TRACKER — this is the one thing that would silently look
plausible if it were wrong.** A gap box tracks the current bar. An order block box is created at
`[origin_index, created_index]` and then every surviving bar sets

    right = obNear ? max(bar_index + 1, origin + OB_STUB) : origin + OB_STUB      (OB_STUB = 30)

so it is a fixed 30-bar zone that stretches to the live bar only while price has come back within
one block-height of it, and it is DELETED the bar the block dies. That uniform width is the point
(`mpc_assistant.pine:170-181`): it is what makes a set of zones scan as one family of levels rather
than a ragged row, and drawing them gap-style would put a rectangle spanning the whole session under
every old level. Two consequences that are correct and look like bugs:

- **A block's box can end long before the block does.** The zone stays live and keeps answering
  anchors for hundreds of bars after its 30-bar box stopped.
- **A block's box can end AFTER the bar it died on** — the stub runs past the live bar into empty
  space, so the last frame it was drawn on reached further right than its death bar. Emitting the
  death bar instead would trim every zone the reader actually saw.

**No settings fork to warn about, unlike the gaps.** The strategy files dropped order blocks entirely
on 2026-07-24/25, so `mpc_assistant.pine` is the only source and the engine defaults ARE its
constants. The flip side is worth saying out loud: **`mpc_sos_fade` reads no block, so a drawn block
never explains an entry** — it is context the reader brings, not a rule the bot applied. The one Pine
input not modelled is `obDirOnly` ("Trend-Aligned Zones Only", default **off**), which HIDES blocks
opposing structure; it is a drawing filter and `engines/order_blocks/CLAUDE.md` names it as something
this layer must not bake in.

`build_stack_chart_spec` strips this group alongside the gaps, for the reason it strips both: the
anchors are the BASE leg's trades, so on a merged chart it would draw zones at one strategy's entries
and nothing at the others'.

⚠ **`tests/test_ob_overlays.py` (18 tests) has NO "and the boxes are the Pine's blocks" half, and
that is a stated gap.** The gap layer's tests cross-check every box against the Pine's own live
arrays in a real export; the three OB exports on disk (`engines/order_blocks/exports/`) all predate
the 2026-07-31 re-port — six slots, no `cfg_ob_*` columns, `compare_ob.py` refuses them outright —
and no post-re-port export is on this machine. So what is proven is that the EMITTER faithfully turns
the engine's events into mpc's boxes; that the ENGINE matches the Pine is proven separately, and was,
on a 21,691-bar 15m export and a 13,186-bar 5m one (`engines/order_blocks/CLAUDE.md` → Validation).
**Re-run `compare_ob.py` on the next real export**, and add the box-vs-array half here when one lands.

## The chart's session windows are the INDICATOR's, and two of the three were not

🔴 **Fixed 2026-08-08** (Aaron confirmed `mpc_assistant.pine` is the correct source). `chart_spec`'s
`_FX_SESSIONS` shaded **Tokyo 09:00-15:00** and **London 08:00-16:30** against the indicator's
**09:00-18:00** and **08:00-17:00** — so two of the three session boxes on a backtest chart were
SHORTER than the boxes on the TradingView chart the run is read against, and nothing on either screen
said so. New York already matched, which is what made it look plausible.

⚠ **The engines already agreed with the indicator; this file was the only dissenter.**
`engines/sessions/engine.py`'s `SessionEngine.DEFAULT_SESSIONS` has carried
`Asia 0900-1800 / London 0800-1700 / NY 0800-1700` since the 2026-07-31 re-sync, and
`engines/liquidity/` composes it for the session H/L levels. So this was a **third statement of one
fact**, and the two that were right had been right for a week.

**The fix is pinned by COMPARING the two, never by restating the windows a third time**
(`tests/test_chart_spec_sessions.py`, 4 tests, **the one in this pass that could be WATCHED RED**).
A test hardcoding `09:00`/`18:00` would be a fourth copy, and the next re-sync would leave it stale
and green — which is the same disease one level down.

⚠ **The display names stay `Tokyo`/`New York` where the engine says `Asia`/`NY`, deliberately.** The
panel keys its per-session toggle state on `name`, so renaming would silently reset a reader's
switches; these are legend labels, not an identifier anything resolves through.

⚠ **A window is stated in its own city's clock, and that is what makes it DST-aware** — it does not
move when that city changes its clocks, while its UTC span does. Re-stating one as a fixed GMT offset
would be wrong for ~7 months a year and would look right for the other five.

## Liquidity levels — and WHICH POOLS PRICE HAD ALREADY TAKEN

`services/liquidity_overlays.py` (2026-08-08). Aaron asked to be able to read, off the backtest
chart, that liquidity had been swept for the daily, the New York session, the H4 and so on. The
canonical `engines/liquidity/` engine is replayed server-side and each level becomes an `hline` in
one of three groups. **It is that engine's FIRST consumer** — it was written, Pine-parity-validated
in July 2026 and then imported by nothing for a year, which is why nothing in this app could answer
the question until now.

**It is the anchor rule again — and here the rule is doing real work rather than being inherited.**
A liquidity level is not rare the way an order block is: every day mints a PDH and a PDL, every
session close a high and a low, and the H4 tier rolls SIX TIMES A DAY. ✅ **MEASURED over the full
history of run `1bbc8fa7773d` (155,891 M15 candles): 35,028 levels created, of which 20,376 — 58% —
are H4.** That is past `_MAX_PER_GROUP` (20,000), so drawing everything would have been a **silent
truncation of the oldest levels**, which is the half a reader scrolls back to and the exact defect
the structure layer's cap was raised to fix. Anchored to trade entries / blocked / missed bars it is
**8,174 levels, 4,608 of them swept** — the same order as the gap layer's 2,822 — and it answers the
question actually asked rather than papering the chart.

**THREE groups, not one**, and this is the one place it departs from the gap and block layers. The
tiers differ by an order of magnitude in volume and in meaning: H4 alone is 58% of the levels, so a
reader following daily and session sweeps wants it off and a reader timing an entry off the last H4
candle wants only it. The indicator gets away with one switch because it only ever draws the ~13
levels that are live RIGHT NOW.

⚠ **This is therefore NOT the same VIEW as the indicator's, and the difference is structural rather
than a fork to be closed.** `mpc_assistant.pine` draws the live set and nothing else — it never shows
you a level from 2021, because there is no 2021 on a live chart. This layer draws the historical set
at the bars that matter. The two agree completely about what a level IS and disagree about which ones
are on screen.

🔴 **THE ENGINE MUST BE CONSTRUCTED WITH `hide_mitigated_on_new_day=False`, AND THE DEFAULT IS THE
TRAP.** Its default is `True` — the Pine's `i_currentDayOnly` tidy — and that tidy is GATED on
`not showMitLiq`, which went **TRUE** in `mpc_assistant.pine` on 2026-08-07 (a swept level now freezes
dotted and grey instead of vanishing). So today's indicator never runs the tidy. Left at the default,
every swept level older than the current NY day is evicted before it can be drawn: the layer would
still render live levels, still look correct, and **be missing the one thing it exists to show.**
⚠ **Its test needed a SPARSE anchor set to catch that, and the first version was VACUOUS** — anchored
on every bar the two settings agree exactly (72 swept either way), because a level is marked seen on
the bar it is swept, before any later tidy can reach it. With one realistic anchor: **6 kept against
1 tidied.** Production is 944 anchors over 155,891 bars, i.e. the sparse case.

**BSL/SSL is DERIVED for every tier except h4, and the derivation is CHECKED rather than trusted.**
The Pine labels a swept high `BSL` and a swept low `SSL` on every tier (`liq_dh`, `liq_ash`, …), while
the engine models `sweep_label` on the **h4 kind alone** — the one tier whose Pine block prints the
tag on the chart. `sweep_label_for` therefore takes the engine's answer where it exists and derives
from the side otherwise. A derivation sitting beside a value something else computed is this repo's
most-repeated defect, so `test_the_derived_sweep_label_agrees_with_the_engines_own` runs the two
against each other on real h4 sweeps and asserts it checked at least one.

⚠ **`_origin_bar` scans back for the candle that MADE the level**, mirroring the Pine's
`f_originHigh`/`f_originLow`. A level is created on the first bar of the period AFTER the one that
produced it, so anchoring the line there starts every line a whole period right of the candle it
describes. It is geometry over candles the caller already holds — the engine still owns the PRICE —
and it scans from `created_index` BACKWARDS, never from the live bar, or it would find a bar that
re-touched the level later and draw the line from the sweep instead of from the origin.

⚠ **`label` is a TOP-LEVEL field on the overlay, not a `style` key.** The panel reads `ov.label` and
spreads `style` separately, so a label nested in `style` type-checks, survives the round trip and
simply never draws — leaving unlabelled lines on the layer whose entire job is naming which pool went.

⚠ **The tiers are dropped from a STACK spec** alongside the gaps and blocks. A level is a property of
the market rather than of a strategy, like the structure overlays that ARE kept — but what is
leg-specific is not the level, it is **which levels were selected for drawing**, and that selection is
the base leg's alone. A market fact filtered through one strategy's anchors is not a market fact.

✅ **Driven end to end through the running backend, not only unit-tested**: a real `?refresh=true`
rebuild of run `bc2143e547b8` (23,706 candles) in 2.3s returns 385 liquidity overlays across the three
groups, **208 of them swept**, carrying labels like `PWL swept · SSL`, with all 13 tier names present.

**Tests:** `tests/test_liquidity_overlays.py` (17). ⚠ **A fail-watch against HEAD is VACUOUS for all
of them** — the module did not exist — so non-vacuity came from **MUTATION**, and seven mutations are
recorded in the docstrings with the test each one turns red. 🔴 **Two of them did not bite on the
first attempt and the two causes are different, which is why both are written down:** the label-nesting
mutation never APPLIED (wrong indentation — a no-op edit proves nothing in either direction, so it was
re-run rather than recorded as a pass), while the origin-scan mutation applied cleanly and left its
test GREEN — that test was genuinely vacuous on a FLAT feed, where every bar spans the same high and
low so the creation bar satisfies the assertion exactly as the true origin does. It uses a trending
feed now.

🔴 **AND THE MUTATION HARNESS ITSELF WAS SILENTLY BROKEN FIRST, WHICH IS THE MOST TRANSFERABLE PART.**
A mutate-run-restore inside one second leaves the file's **mtime AND size unchanged**, so Python
reuses the cached bytecode and the "mutation" tests the unmutated module. It presented as a test that
stayed red after the source was restored byte-identically (`diff` clean, `grep` showing the right
values, `__file__` pointing at the right path) — because `__file__` names the SOURCE even when the
module was loaded from a `.pyc`. ⚠ **On macOS there is no local `__pycache__` to clear**:
`sys.pycache_prefix` is `~/Library/Caches/com.apple.python`, so `find . -name __pycache__` returns
nothing and the stale bytecode is somewhere else entirely. **Any mutation or fail-watch loop in this
repo must delete that prefix path (or sleep past the second) between steps, or it proves nothing and
looks like it proved something.**
## Candlestick reversals — which candle turned price, where a setup existed

`services/candle_overlays.py` + `chart_spec.reversal_anchors`. Aaron's ask (2026-08-08): *"I'm
trying to see if these candle patterns line up with my reversal where I took the trades, or the
ultimate reversal point before the trade went into my favour"* — so that he can later ask whether
candlestick patterns are worth adding as a confluence. The canonical `engines/candlesticks/` engine
is replayed over the run's own candles and every pattern candle in a setup's SPAN is repainted navy.
Never a second engine — bare-name import, public events only, the same shim as regime / news /
structure / fvg / ob.

**It is read at `CHART_PRESET`, NOT the engine's defaults** (trend 117 / doji 0.01 / eleven
patterns). Those are Aaron's brother's TradingView inputs, taken off a real export's own `cfg_*`
columns rather than transcribed; the engine mirrors its source Pine (5 / 0.05) and a CONSUMER pins
what it reads. Repointing this at the defaults would make the chart stop matching the indicator it
is read against — pinned by a test.

### 🔴 The rules match his indicator and the PRICES do not — 16% of marks disagree, and no rule change can close it

**MEASURED 2026-08-09, after Aaron reported eight candles that "are obviously engulfings" and were
not marked. Two of the eight are genuine misses and the cause is not in this file, in the engine, or
in the Pine — it is the BAR FEED.** This chart draws the run's own candles, which come from the MT5
cache (`backtest/cache/XAUUSD__M15.csv`). The indicator he is comparing against runs on
TradingView's feed. Same broker, same symbol, different tape.

✅ **20,053 shared bars, the export's own `px_*` flags as the reference, engine at `CHART_PRESET`:
the two feeds sit a systematic 6 cents apart (median close difference −0.060), and that alone
produces 600 marks his chart draws that this one misses plus 515 it draws that his does not —
15.9% of every mark he sees.** Bearish engulfing alone: **150 missed of 914.**

🔴 **A CONSTANT offset would flip nothing** — every clause here is a comparison between two prices,
so a whole-feed shift cancels — **so the damage is entirely the INTRA-BAR variation**, and it is
larger than the offset. On his 2025-12-09 16:45 case the two feeds disagree by 14 cents on the open
and 3 cents on the prior close, i.e. **17 cents on the one comparison that decides the rule**:
TradingView clears `open >= close[1]` by +0.09, the cache misses by −0.08. Every other clause passes
on both. That bar is the trade's adverse extreme, so the miss also changed the CHIP — the name fell
through to the `Inverted Hammer` on the next bar, which is how the reader noticed.

🔴 **A TOLERANCE WAS MEASURED AND IS STRICTLY WORSE — this is now a number, not only the standing
rule in `engines/candlesticks/CLAUDE.md`.** Relaxing the two `>=` boundaries by an epsilon, scored
against his own flags over the same 20,053 bars (engulfings, both directions):

| epsilon | we miss | we invent |
|---|---|---|
| **0 (shipped)** | **243** | **190** |
| $0.02 | 143 | 664 |
| $0.05 | 95 | 822 |
| $0.10 | 65 | 900 |

**Two cents recovers 100 marks and manufactures 474.** The mechanism is that on a gapless intraday
feed a bar's open sits within a cent or two of the prior close as the ORDINARY case, so any slack
floods the rule rather than nudging it. **Zero is the minimum-disagreement setting by a factor of
two**, which is the opposite of what "just a few cents of feed noise, allow a few cents" predicts.

⚠ **The remaining six of the eight are not this layer's doing and the clause breakdown is the only
answer that shows it** — four fail the full-body engulf by **$0.01 / $0.05 / $0.06 / $0.01 on HIS
OWN prices**, and one passes the engulf and fails the 117-bar uptrend gate with price $13 below
where it was 117 bars back. His indicator does not draw them either, read straight off `px_bear_eng`
in his export rather than argued. ⚠ **Do not answer a report like this with an assurance that the
engine is parity-green** — it is, and it is beside the point; print the failing CLAUSE with both
feeds' numbers beside it.

⚠ **The honest options are: accept it, or change the CANDLE SOURCE — and the second is not
available**, because the chart must draw the bars the strategy actually traded or the marks stop
lining up with the trades. **Accepted, no code change (Aaron's call, 2026-08-09.)**

**The standing lesson is about what a parity gate covers.** `compare_candles.py` feeds the engine
the EXPORT'S OWN prices, so it proves the rules agree and can never say anything about the data a
consumer feeds them. Every layer was green and the reader still saw the wrong candle. **Before
claiming one system matches another, ask whether they are reading the same INPUT — a validated rule
on a different tape is a different answer.** It is the shadow diff's finding (`algos/tools/shadow_diff.py`,
2026-08-04) arriving in a second subsystem: there four cents of broker difference moved a resting
entry $10.12; here six cents moves one mark in six.

### The anchor set is trades and 3/3 misses, and nothing else

**`reversal_anchors(trades, misses)` is public and named for one reason: it is the thing about this
layer that has already been got wrong once.** Five of the eleven patterns fire on **5-9% of every
bar** (both haramis, both engulfings, hammer, inverted hammer — measured, see
`engines/candlesticks/CLAUDE.md`), so an unanchored layer paints roughly one bar in twelve and says
nothing at all.

🔴 **BLOCKED setups were anchors until 2026-08-08 and it is what made the layer look random.** 324 of
them on the reference run against 159 trades and 35 three-of-three misses — **two thirds of every
mark** — and since the Blocked layer defaults OFF, they painted navy candles in places the reader
could see no setup at all. Reported from the screen as exactly that: *"we are plotting candles in
places that we didn't take trades or missed 3/3 trades."* ✅ **Measured: 518 anchors / 424 marks →
194 / 153.** A 2/3 miss is out for a different reason — it was never a setup, so there is no *which
candle turned it* to ask; `of > 0` guards a record that counted no confluences at all, because
`0 >= 0` would otherwise admit the least informative record there is.

🔴 **A 3/3 MISS ANCHORS ON ITS RETRACE, NOT ON ITS OWN `time` — the second thing this layer got
wrong, reported the same day.** A miss is booked on the bar the setup DIED, and that bar is nowhere
near the setup: ✅ **measured on the reference run, price sits a median $22 and up to $205 from the
setup's own entry edge by then, on 32 of the 35.** So the marks landed in a part of the chart the
setup had nothing to do with — read off the screen as *"the reversal candle printed on the opposite
side, which doesn't make sense … I'm expecting it to be that price got into the zone for the trade
and there was a reversal candle."* The strategy now records the retrace (`zoneTime` / `zoneTurn`, see
`strategies/python/mpc_sos_fade/CLAUDE.md`) and the span runs between them. ✅ **MEASURED, old vs
new: the nearest mark to the setup's own entry edge goes from a median $20.67 to $3.16, and 21 of 35
misses get a mark where 9 did.**

🔴 **It CANNOT be derived here, which is why the strategy had to change.** The obvious cheap fix —
scan back from the death bar for a bar that traded through `edge` — finds one for **all 35**,
including the ten where price provably never reached the limit, because price crosses that level at
unrelated moments. It would have been confidently wrong and silent. ⚠ **A run made before the
strategy recorded those fields yields NO miss anchors at all, deliberately: drawing nothing is
honest about a question the run cannot answer, and drawing it in the old place is not. Rerun to get
them.**

⚠ **The parameter list is the guard.** There is no value you can pass that produces a block-anchored
mark, so the only way blocks return is somebody adding the argument — and a signature test fails in
front of them with the reason.

### An anchor is a SPAN, and every pattern candle in it is drawn

`(start, direction, end, outcome, entry_price)` → every bar from `start` to the end of the setup's
DRAWDOWN. Inside it sits the turn — the bar price ran furthest against the setup — and everything
before that is the retracement the setup was entered into. **A trade spans entry → exit, win or
lose; a 3/3 miss spans its retrace.**

🔴 **It painted ONE candle per anchor until 2026-08-08 and that lost the whole question.** Aaron:
*"you don't only have to give me the deepest candle — you could give me all the candles that would
have shown a possible reversal all the way up to the deepest one … so let's say I entered at the
fifty, but there was no reversal candles until 0.702, and then maybe 0.786. I could see, wow, I
could have taken a trade at 0.702 or 0.786."* Read with the **Fibs** layer on, each mark sits on a
rung, so the layer answers *which entry level had a candle behind it* — which a single mark can
never say. ✅ **MEASURED: 194 anchors → 971 marks.** 464 point with the setup, 409 are neutral, 98 point
against; 167 are their span's deepest. **140 of 159 trades and 27 of 35 three-of-three misses carry
a reversal candle at all.**

🔴 **The span runs `_CONFIRM_BARS` (2) PAST the turn, and that is not a fudge factor.** It is the
longest pattern the engine reads minus the bar it starts on. **A pattern is reported on the bar it
COMPLETES**, so the bar that MADE the extreme is usually the pattern's first bar rather than its
last. ✅ **MEASURED on 194 anchors: 37.1% carry a pattern ON the turn bar and a further 40.2%
complete 1-2 bars after it** — so ending the span at the turn threw away the reversal candle on
**four setups in ten**, reported off the chart as *"it's not showing the deepest candle pattern that
would have been the most perfect entry."* ⚠ **Do not tune it.**

🔴 **AND THE ZONE IS A REGION IN PRICE, NOT A STRETCH OF TIME — that one mistake produced FOUR
separate complaints across two rounds (2026-08-08 → 2026-08-09).** Every version that reasoned in
BARS was self-consistent and easy to test, and each one was wrong in a different direction. ✅ **All
MEASURED on run `e51d95f212e3`, 166 anchors:**

  - 🔴 **`turn + _CONFIRM_BARS` covered a fraction of the zone.** The bar that makes the adverse
    extreme can sit anywhere in the drawdown, so on a trade that tops out early and grinds sideways
    the span missed most of the red box. **On the 2026-06-18 short the turn is 02:00 and the trade
    stays above its entry until 05:30 — 21 bars of drawdown against a 9-bar span, holding THREE
    patterns of which ONE was drawn**, and that one was the opposing candle, so the chip read
    `no matching candle`.
  - 🔴 **Then the confirm tail leaked into the takeoff.** Adding `_CONFIRM_BARS` to the END of the
    drawdown rather than to the TURN is two free bars after price has already left the band — and on
    a trade that leaves the band into a rally, those two bars ARE the rally. **On the 2026-07-15 long
    the drawdown ends 17:15, the next bar rallies $16 clear, and the `Inverted Hammer` two bars later
    at 4060-4066 — $25 above the entry — was the trade's ONLY mark, so it named the chip.**
  - 🔴 **And the span opened at the ENTRY BAR**, so a trade that ran into profit first and only later
    came back to make its adverse extreme painted the whole excursion in between — **one turn is 112
    bars after entry.** Together those two put **255 of 1084 marks entirely on the favourable side.**
  - 🔴 **A LOSER WAS MARKED AFTER IT WAS CLOSED.** A stopped-out trade's adverse extreme IS its final
    bar, so `turn + _CONFIRM_BARS` reached past the exit into the next setup. Aaron, off the
    2026-05-11 short (stopped 13:30, a `Hammer` painted 14:00): *"Trade already lost. You already hit
    stop loss… I don't care what the candles after the trade. It has to be within the trade."*
  - 🔴 **And the contiguous-excursion fix went too far the other way.** Walking from the turn and
    stopping at the first favourable bar meant that when price came BACK to the entry later in the
    hold, the re-test fell outside the zone — while the chart's own red box plainly covered it. On
    the 2026-02-15 short that is two unmarked `Hammer`s: *"we came back up to entry. And there was at
    least three different candles you coulda highlighted there, and you didn't highlight any of
    them."*

✅ **The rule is now one price test and one clamp.** `_reversal_span` returns the whole hold — entry
bar → EXIT bar — and `_in_zone` draws a bar while ANY part of it trades on the adverse side of the
entry. That is the same test as *does this candle touch the red box*, which is what the reader is
pointing at. ⚠ **`_drawdown_end` is DELETED, and it could not be salvaged: no walk can express "and
again when price comes back" without also swallowing the profitable stretch in between.** ✅
**Driven through the live backend: 1090 → 853 marks, ZERO past any exit, 31 outside the band and
every one within `_CONFIRM_BARS` of the extreme.**

🔴 **A FOURTH defect fell out of the same audit and nothing had ever reported it.** `_anchor_bars`
took an end only `if j > i`, so **a trade that OPENS AND CLOSES INSIDE ONE BAR read as having no end
at all** and fell through to the `window` fallback — a 60-second trade with a THREE-BAR span reaching
43 minutes past its own exit. **MEASURED: 4 marks on 3 trades, one a `Bearish Engulfing` drawn after
a trade that lasted 4 minutes.** It is `j >= i` now; only an end BEFORE the start is genuinely
unusable.

⚠ **FOUR of the six candles Aaron named are NOT this layer's doing, and saying so needed the clause
breakdown rather than an assurance.** All four are IN the zone and would be painted the instant the
engine detected them — the engine does not, because `candle_sticks.pine:32` says
`bearEng = close[1] > open[1] and open > close and open >= close[1] and open[1] >= close and
open - close > close[1] - open[1] and open[trend] < open`:

  | candle | the clause that fails | by |
  |---|---|---|
  | 2026-06-16 13:00 | `open >= close[1]` — 4354.59 vs 4354.64 | **$0.05** |
  | 2026-04-06 09:45 | `open >= close[1]` — 4703.35 vs 4703.41 | **$0.06** |
  | 2026-01-30 00:15 | `open >= close[1]` — 5445.02 vs 5445.03 | **$0.01** |
  | 2026-06-18 05:30 | `open[trend] < open` — 4336.58 vs 4323.15 | the **117-bar uptrend gate** |

**On a gapless intraday feed a red bar opens within pennies of the prior close, so a full-body
engulf is decided at the cent** — and the trend gate refuses to call anything a bearish reversal
while price sits BELOW where it was 117 bars ago. ⚠ **Do NOT add a tolerance to close those gaps.**
A 0/1 flag has no "close enough", the same argument `engines/candlesticks/CLAUDE.md` makes for its
three boundary ties — and the engine matching the indicator Aaron's brother actually reads is the
entire reason this layer is trustworthy. His TradingView chart does not draw these four either.

⚠ **The confirm bars stay exempt from the band test, and that is why this is not JUST a price
filter.** A pattern is reported on the bar it COMPLETES, so on a sharp V the third bar of a Morning
Star is already back above the entry — and that bar IS the reversal candle. ✅ **MEASURED: dropping
the exemption leaves 40 trades with no mark against 21.**
⚠ **A 3/3 MISS passes NO entry price, so every bar of its span qualifies**: no position was opened,
so there is no entry to measure a band from, and its span is already the visit into the zone. It is
clamped to its death bar for the same reason a trade is clamped to its exit.

**Each mark also carries `spans`, `deepest` and `align`, and none of the three is derivable
downstream.** `spans` are the anchor indices whose span covers the bar (so the chart can badge a
trade), `deepestOf` are the ones it is the REVERSAL of — a LIST, not a flag, because one bar can be
the turn of one setup and an ordinary mark inside another's span — and `align` is its direction
**relative to the setup**. ⚠ **`align` is NOT `patternDir`** — that is the pattern's own direction,
and whether a bullish candle points the setup's way depends on the setup's SIDE, which a mark does
not carry and cannot: one bar can sit inside a long's span and a short's at once. ⚠ **`spans` is
collected for EVERY anchor covering a bar, not just the one that names it** — the dedupe decides the
name, and reusing it here would make a trade whose only pattern bar was already claimed report as
having none, which is the one thing the trade badge exists to say. ⚠ **`_anchor_bars` carries the
anchor's ORIGINAL index**, because it drops anchors off the loaded candles and renumbering would
mislabel every trade after the first drop, silently and plausibly.

⚠ **A LOSER carries its exit too, and it used to carry `None`** and get a 3-bar window. Its span is
the retracement it was entered into on the way to the stop, which is the same question. ✅ **MEASURED
on 106 winners: the adverse extreme sits a median of 2 bars past entry, p90 27, worst 112** — so a
fixed short window truncates the retracement on half of them.

⚠ **`_TURN_TOLERANCE_BARS` is GONE, and it was doing real damage.** It kept only patterns within 2
bars of the extreme, so on a long retracement it deleted every earlier entry level — exactly the
ones the request is about.

### Which candle a setup is NAMED after — and why the outcome flips it

🔴 **Fixed 2026-08-08, reported off two screenshots of WINNERS named with the opposing candle** (a
long reading `Won · Bearish Engulfing`, a short reading `Won · Bullish Harami`). The three-tier
direction preference below was real and was only ever applied to the patterns ON one bar; **which
BAR became the span's `deepestOf` was still nearest-the-turn, whichever way it pointed** — and that
is the one the trade's chip names and the one *"Only the deepest"* leaves on screen.

**`_wanted_direction(direction, outcome)` is the rule, and it is Aaron's:**

| anchor | wants | because |
|---|---|---|
| a WINNER | the setup-aligned candle | *"the BEST candle that helped or COULD HAVE HELPED signal the reversal"* |
| a 3/3 MISS | the setup-aligned candle | *"the DEEPEST CORRECT candle that I could have used to enter"* |
| a **LOSER** | the **OPPOSING** candle | *"the candle that signaled why I lost"* |

So the question is always *which candle explains what happened to this setup*, and it flips on the
OUTCOME rather than on the side. `reversal_anchors` carries a fourth element to say which.

✅ **MEASURED over the reference run's 194 anchors, old rule vs new:**

| | named as asked | neutral | named against | no candle |
|---|---|---|---|---|
| old | 69 | 54 | **44** | 27 |
| new | **98** | 59 | **10** | 27 |

Losers moved most — 33 named with an aligned candle → 4 — which is expected, since the aligned one
was the OLD ordering's first choice and is now the last.

⚠ **THREE tiers, and two was measurably not enough.** 59 of 194 spans contain no directional candle
at all (ten of the source Pine's fifteen rules gate on a trend lookback), so a `preferred or
anything` pool picks an OPPOSING bar whenever it happens to sit nearer the turn. Preferred → neutral
→ whatever is left, the same preference the within-bar ordering uses one level down.

⚠ **It orders the NAME and paints nothing differently.** Every pattern candle in the span is still
drawn in every direction — `test_the_outcome_changes_the_NAME_and_never_what_is_PAINTED` asserts
both readings of one span produce identical marks — because the opposing tier is half the point of
the layer. The chart's direction filter remains the only thing that hides anything.

⚠ **`deepestNames` is keyed PER ANCHOR (`{"0": "Hammer", "1": "Bearish Engulfing"}`).** One bar can
be the deepest of a losing trade AND a 3/3 miss on the same leg, and those two want opposite
directions; the bar's single `label` is whichever anchor reached it first, which is nobody's answer
in particular. The chart reads this for a trade's chip and falls back to `label`.

⚠ **A miss is `"miss"`, never `"loss"`,** even though no trade was taken — it is a setup that was
never entered, so it asks the winner's question. Filing it as a loss would name it after the candle
that beat a trade nobody had.

⚠ **An anchor with no outcome reads as a WIN.** Aligned is the answer for two of the three cases;
defaulting to the loser rule would name a healthy trade after the candle that beat it.

⚠ **The fallback to the whole span is deliberate and must not be tightened to nothing.** A setup
whose only candles point the other way still has a deepest one, and reporting *no reversal candle*
for a setup that plainly had one is the failure the opposing tier exists to prevent.

### "Deepest" is a PRICE, and an OPPOSING candle is never the NAME

🔴 **Two more defects, both reported off the chart on 2026-08-08, both in the same three lines.**

**(1) The fallback ranked by TIME.** When no pattern bar in the preferred tier reaches the turn, the
span still has a deepest one — and it was `pool[-1]`, the LAST bar in the span, which is *most
recent*, not *deepest*. ✅ **MEASURED on the reference run's 2026-06-16 short: the span holds eight
pattern bars including three Bearish Engulfings, and the last one is a Bearish Harami at high
4345.02, while the genuinely deepest aligned candle is the 11:00 Bearish Engulfing at 4349.27 —
$4.25 further into the retracement, i.e. the better short entry.** Aaron named it exactly:
*"the deepest best entry was on a bearish engulfing yet you did not highlight it."* `_deepest_bar`
reads the adverse extreme — highest high on a short, lowest low on a long. ✅ **Over 166 anchors the
deepest bar moves on 13 and the NAME changes on 8.** ⚠ **A pattern COMPLETING at or after the turn
still wins outright** (that IS the turn candle — see `_CONFIRM_BARS`); "deepest" only becomes a
question when nothing in the pool reaches it. ⚠ **Ties keep the EARLIER bar**, because the earlier
one is the entry you could actually have taken.

**(2) The name fell through to an OPPOSING candle.** Aaron, on a winning short reading
`Won · Bullish Harami`: *"Shouldn't it be a neutral candle, no candle or best yet a bearish
candle?"* — so the preference order ends at NEUTRAL and the honest answer below it is silence.
✅ **MEASURED: 9 of the reference run's 166 anchors hold nothing but opposing candles, and every one
was named after the candle arguing AGAINST the setup. After: 82 named as asked, 56 neutral, 19 with
no candle at all, 9 drawn-but-unnamed, and ZERO named against.**

⚠ **The bar stays in `deepestOf` and stays PAINTED — only the NAME is withheld.** Dropping it would
hide the opposing candle behind the panel's *"Only the deepest"* setting, and showing it is half the
point of the layer (*"it will show me why I was wrong"*). ✅ **846 marks either way, measured.**

⚠ **The chart says `no matching candle`, NOT `no candle`.** Three states, not two: `no candle` = the
span held no pattern at all; `no matching candle` = it held some and none pointed the way this
outcome asks about, so the marks ARE on screen and none of them earns the chip. Collapsing them
would report a setup that plainly had candles in it as having had none.

⚠ **The panel reads `deepestNames[anchor]` with NO fallback to `label` when the field is present.**
An object lacking this anchor's key is an ANSWER — the backend withheld the name — while the field
being ABSENT means a spec cached before per-anchor naming existed. `label` is the fallback only for
the second. The repo's own rule: never let "no" and "cannot ask" be the same value.

⚠ **A red candle is not a pattern, and this was asked directly** (*"why did you not highlight all the
bearish candles in the drawdown zone"*). The layer draws the engine's fifteen named RULES; a bar
being the right colour is not one of them.

🔴 **BUT THE MEASUREMENT ORIGINALLY WRITTEN HERE ANSWERED THE WRONG QUESTION, AND IT IS THE MOST
UNCOMFORTABLE ENTRY IN THIS SECTION.** It read *"its retrace zone is 9 bars and exactly ONE carries a
pattern"* — and **9 bars is the SPAN THE CODE WAS USING, not the zone the reader was pointing at.**
The trade's real drawdown is **21 bars and holds THREE patterns**. So a true number, measured
honestly, was quoted as evidence that nothing was missing — while it was in fact a restatement of
the very bug being reported, and it stood for a day until Aaron asked again. **When a reader says a
region is bigger than what you drew, measure the REGION THEY NAMED, never the one the code
computed** — the second can only ever agree with itself. The zone is the red box now (`_in_zone`),
and on that trade the layer draws all three. ⚠ **The same mistake was nearly made a second time the
next day**: four of the six candles reported on 2026-08-09 really were outside this layer's control,
and the only honest way to say so was to print each failing CLAUSE with its numbers — not to assert
that the engine had been checked.

✅ **5 new tests. The fail-watch against HEAD is VACUOUS and is recorded as such** — the module gained
`_deepest_bar`, so the whole test file fails to IMPORT at HEAD, which proves the import and nothing
else. Non-vacuity is by **MUTATION**: five mutations (the recency fallback restored, the opposing
name restored, unnamed bars dropped from `deepestOf`, the neutral tier dropped from the name, and
the deepest key hardcoded each way), each turning its own named test red. 🔴 **One of the five was
VACUOUS on its first TWO attempts and is commented as such** — with the high and the low on
different bars, a rule reading the wrong PRICE still returns the right index, because only the key
was mutated and the comparator is still chosen by direction. It needs one bar sitting INSIDE the
other.

### Direction orders the NAME on a bar, and never whether it is painted

🔴 **Selecting one candle per anchor is what put a `Bearish Engulfing` on a LONG that won** —
reported from the screen: *"we should have plotted a bullish candle if one was present."* That class
of error is gone by construction: nothing is selected, so nothing is suppressed. What direction still
decides is the NAME, in three tiers — **aligned → neutral → opposing**.

⚠ **An opposing candle is drawn like any other, and that is half the point of the layer**: *"if I'm
trying to take a short with a bullish candle printed, and that's why price reversed, yeah, highlight
that … if it lines up with my trades, then great. If not, it will show me why I was wrong."* ✅
**MEASURED across the 820 marks: 346 neutral, 259 bearish, 215 bullish.**

⚠ **The NEUTRAL tier is what does most of the work, and the reason is in the source Pine.** Ten of
its fifteen rules gate on a `trend`-bar lookback, so in an uptrend the bullish rules cannot fire at
all — which is precisely why the reference trade's mark was bearish. Hammer, Inverted Hammer and
Doji carry no trend filter and no direction, so they are the tier that rescues it.

⚠ **`label` is a CHOICE, not the first element.** 7.4% of bars carry more than one pattern (every
Hanging Man is also a Hammer by construction), so the chosen bar's list is reordered by the same
tiers — otherwise a bar printing both a Bearish Engulfing and a Hammer is named after the wrong one
on a long.

### Tests

`tests/test_candle_overlays.py` (46) + `tests/test_chart_spec_reversal_anchors.py` (9). ⚠ **A
fail-watch against HEAD is vacuous for a new module**, so non-vacuity is by MUTATION — each turning
a distinct test red: marking only the turn, running the span past the turn, anchoring a miss on its
death bar again, giving losers back their `None`, ignoring `hold_end`, dropping the dedupe, and
dropping the label reorder. Making direction a FILTER rather than an ordering turns
`test_with_NOTHING_but_an_opposing_candle_it_is_still_marked` red, which is the half worth guarding.

⚠ **Every fixture builds bars that make a REAL pattern fire and asserts that it did.** A test that
placed a mark by mocking the engine would pass against a layer reading the wrong bar, which is the
one thing worth checking here. ⚠ **Two fixtures were caught being wrong BY THE CODE**: a "no
pattern" bar was itself a Hammer, and replacing it with a long bearish body made its neighbours an
Evening Star — **a three-bar pattern is a property of the bars AROUND the one you are placing**, so
the fixtures now assert their own quiet bars are quiet.

## Trade fibs — the leg each trade was actually priced off

`chart_spec._trade_fib`. Aaron's brother asked to see, on every trade the chart plots, the fib run
on the points that trade used — which retracement levels it went into. The strategy records that
ladder when it places the order (`mpc_sos_fade/execution.py` → `TradeFib`), `backtest/output.py`
puts it on the equity-curve point, and this turns it into the chart's `trades[].fib`.

**The levels are PASSED THROUGH; only the two RATIOS are computed here.** That split is the whole
design. The prices are the ones the strategy had in hand at placement, so a chart and a bot can
never disagree about where a level sat — a fib rebuilt downstream from anchors and a direction is
a second claim about one leg, which is the failure this repo has now met four times (Run modal
costs, Optimize modal params, the SSH dot, the lab-vs-Pine parameter names). What a price ladder
CANNOT state is where the fill landed on it, and that is the question:

- **`entryRatio`** — the fill as a ratio (0.702 = it entered at the 70.2% retrace). On the A+ bot
  this reproduces the entry model without being told about it: an entry snapped to a fib by
  `_fib_snap` reads exactly 0.618 / 0.702 / 0.786, and a gap-edge entry reads between two rungs.
- **`deepestRatio`** — the same for the deepest ADVERSE price of the hold, i.e. how far the
  retracement really ran after entry. **Not clamped at 1.0**: a trade that traded through the leg
  origin genuinely retraced past it, and clamping would report every stop-out as having stopped
  exactly at the origin.

⚠ **Both are computed and served, and since 2026-08-03 the chart draws NEITHER** — the panel's Fibs
layer prints the ladder only, and the trade's own `Entry` / `Deepest` annotations carry those two
price rows (with prices). They stay here because they are the two readings the ladder cannot state
and the derivation is pinned by tests; if nothing consumes them by the next chart pass, delete them
rather than leaving a field the UI implies it is showing.

Both are pure geometry off two levels the ladder already carries — a fib price is linear in its
ratio, so any two `(ratio, price)` pairs define the line and inverting it maps a price back. **No
anchor, no direction, no range**, hence no branch for a bear leg and nothing here that can drift
from the strategy. A degenerate (zero-height) leg returns `None` rather than dividing by zero.

`startTime` is the bar the LEG began on, not the entry — a ladder starting at the fill would hide
the retracement that produced it, which is the thing the layer exists to show.

**Optional end to end**, like blocks and misses: NT8/MT5 record none, a Python run finished before
this landed has none (**no backfill — it would mean replaying the strategy**), and `mpc_bleg` has
none by construction. The chart's Trade fibs toggle is listed off whether any trade carries one, so
absence removes the switch instead of offering an empty layer. Existing runs need **Reload charts**
(`chart_spec.json` is cached). Tests: `tests/test_chart_spec_trade_fib.py` (12).

## News filter (post-run)

The economic-calendar (news) filter is a **post-run view layer**, NOT a run-time gate: the lab runs every backtest RAW (news is never wired into the C#/MQL5 strategy), so removing news-window trades is pure arithmetic on the finished trade list — instant, no VPS re-run. Design decision (Aaron 2026-07-05): **run raw + toggle after.** Window default **15 min before / 30 min after** a high-impact USD release (asymmetric — liquidity dies only in the last minutes before; the spike/reversal/move run 15–30 min after). **Two rules, both switchable, and BOTH DEFAULT OFF** (2026-08-01, Aaron's call): the page opens on the run exactly as traded, so every number on it is the backtest's own and turning a rule on is a deliberate what-if. That replaced two different defaults for one reason — a filtered default means the headline figure on screen is not the run's result, and no checkbox further down the page makes that obvious. Holidays had defaulted ON (hardcoded always-excluded with no control at all until 2026-07-30, when they became a visible checkbox but stayed ticked), and news followed the strategy's own `avoid_news`, so the default silently DIFFERED BETWEEN STRATEGIES — two runs over the same window could open on different trade counts with nothing on screen explaining why. The backend reports `in_news` and `in_holiday` separately and always has; every default here has been a frontend-only decision.

- **`services/news_filter.py`** — composes the canonical `engines/news/` engine (imported by bare name after adding `engines/` to `sys.path`, same pattern as regime; **never a second calendar impl**). `build_report(trades, pre, post, ...)` loads the `EventStore` cache, builds a lab `NewsPolicy` (high-impact USD, holidays always), and walks each trade's `entry_ms` through the engine → per-trade `{in_coverage, in_news, in_holiday, title}` + coverage boundary + counts. Reads `in_news` (a high-impact window) and `in_holiday` **separately** so the UI keeps them separable. 9 unit tests (synthetic events, no network). Coverage honesty: outside the fetched calendar range trades come back untagged (never guess) — backfill months via `engines/news/tools/backfill.py`.
- **`GET /backtests/runs/{id}/news?pre=&post=`** → `RunNewsReport` (models.py `RunNewsReport`/`NewsTradeTag`). Pure off the stored `equity_curve` — no VPS. `pre`/`post` are the window minutes (sliders re-call to re-tag). Old runs with no `entry_ms` come back untagged.
- **Trade entry time capture:** `parse_trades_csv` now stores each trade's `entry_ms` (UTC epoch ms) on its equity-curve point, from the NT8 "Entry time" column via `_parse_nt8_dt`. The VPS **NinjaTrader Time zone is UTC** (confirmed) → naive value treated as UTC, no offset. Old NT8 runs predate this → re-pull with **Reload charts** (or rerun). Python runs carry it from `backtest/output.py` and never needed either.
- **`entry_ms` AND `exit_ms` MUST be declared on `models.EquityPoint`** (entry fixed 2026-07-28, exit 2026-07-30 — the SAME omission, caught twice, which is why this is written as a rule and not an anecdote). `exit_ms` had likewise always been in `equity_curve.json` and was likewise stripped on the way out; with both present a consumer can compute trade duration over any SUBSET of trades, which is what lets the News filter report **Avg Trade** instead of a dash once it removes something. Pydantic drops any field a model doesn't declare — so the value reached disk and the `/news` endpoint (which reads `equity_curve.json` directly, and therefore tagged correctly all along) but was stripped on the way to the browser. The card's `hasEntryTimes` check then failed for EVERY run and it showed "made before trade times were recorded" universally, which reads as an old-run problem and is not one. Same trap the `favorable`/`adverse` comment two lines below it warns about. **Nothing that reaches the frontend can rely on a field being in the JSON on disk — only on it being in the model.**
- **`avoid_news` is metadata, not a default:** `strategies.avoid_news` (INTEGER col, migration; default 0) overlaid from `<Strategy>.meta.json` top-level `"avoid_news"` by `strategy_scanner._read_strategy_overview`, exposed on `Strategy.avoid_news`. ⚠ **It no longer sets the News toggle's default** (2026-08-01 — both rules default OFF; see above). It remains real strategy metadata read off meta.json and is still exposed on the API; nothing in the UI consumes it today. Re-wiring it to a default would restore the per-strategy divergence that change removed — raise it before doing so. `ORB.meta.json` ships `avoid_news:true` (gold avoids news). **Scanner fix:** the `.cs` skip now also re-scans on meta.json **mtime** (mirrors the `.mq5` path) — before this, a meta-only edit on an unchanged `.cs` source (avoid_news, edge/steps, param labels) never took effect. A **Scan** picks up the new value.
- **Runner support:** NT8 and **PYTHON** both work (python verified end-to-end 2026-07-28 on a 142-trade XAUUSD run — 142/142 in coverage, 11 news-window trades at a 15-min pre-window). **TODO (#3, still not built): the MT5/forex path** — `runner_dispatch._normalize_mt5_results` needs its own `entry_ms`, and the **MT5 broker server clock is NOT UTC** (offset + DST), so it needs its own timezone handling (a confirming step like the NT8 one).
- **Calendar coverage is the real gate, not the code.** The engine reports `has_coverage=False` outside the fetched range and the filter goes inert there — so a correctly-wired filter over an unbackfilled period looks identical to a broken one. Backfill first (`engines/news/tools/backfill.py --from YYYY-MM`), then judge. The cache is git-ignored, so it is per-machine and a fresh clone starts empty.

## Strategy versioning (content-addressed)

`strategy_versions` table — the single source of truth for "what version of strategy X exists / is running." Each distinct source content hash maps to a monotonic `version` per strategy (PK `(strategy_id, version)`, UNIQUE `(strategy_id, source_hash)`); reverting to earlier content **reuses** its original version. `lab_db.ensure_strategy_version()` assigns/returns it (content-addressed, idempotent, retries on the rare concurrent-PK race); `version_for_hash()` resolves a stored hash; `list_strategy_versions()` is the history (newest-first), exposed at `GET /strategies/{id}/versions`.

Versions are registered in three places: the **scanner** (every scan, both `.cs`/`.mq5`, before the skip check so unchanged strategies still register), the **deploy** endpoint, and the **upload** endpoint. Lab-VPS deploy/compile state lives as columns on `strategies` (`deployed_source_hash`/`deployed_at`, `compiled_source_hash`/`compiled_at`): `set_strategy_deployed()` stamps the deployed hash + flags needs-compile (`is_compiled=0`); `mark_runner_compiled()` stamps `compiled_source_hash = deployed_source_hash` on compile success (content-accurate, not just the coarse `is_compiled` boolean). **Hash parity is essential** — anything that records a deployed hash must hash the same way the scanner does (decode bytes utf-8 errors=replace → md5), or `deployed_version` won't resolve.

**First-run note:** strategies deployed before this feature have `deployed_source_hash = NULL`, so they correctly show `needs_deploy` until deployed once through the tracked path (we never fake a hash we can't verify — the VPS agent's file listing exposes size/mtime, not content). **Scalability:** the version registry is target-agnostic — a future "deploy version N to bot X" records `(strategy_id, target, version)` in its own table without touching the registry; the lab VPS is just today's only target.

---

## Strategy location + deploy (Pass 2.5)

Live behavior. Scanner reads from `strategies/` via `rglob("*.cs")`/`rglob("*.mq5")`; `source_path` stored relative to monorepo root (e.g. `strategies/ninjatrader/ORB.cs`); missing `source_path` warns, never auto-deletes. `POST /strategies/{id}/deploy` reads `source_path` and uploads via `runner_dispatch` (`.mq5` → MT5 agent, `.cs` → NT8 agent), returns 202 + `deploy_job_id`. Edge cases: `source_path` null → 400, file missing → 404, VPS locked → 423. Detail is in git history (Pass 2.5).

**Bidirectional delete (reconcile) — deletion propagates only on an explicit action.** Deleting a source file from the repo should mean "remove everywhere" (DB row + the deployed `.cs`/`.mq5` on the VPS NT8/MT5 folder), but that destructive step is **never** wired into a scan. `scan_strategies()` is READ-ONLY: it adds/updates from disk and calls `_detect_orphans()` (DB strategies whose recorded `source_path` no longer exists on disk) to REPORT them in `ScanResult.orphans` — it deletes nothing. A scan is a frequent read; a mis-synced disk (wrong `MONOREPO_ROOT`, repo not checked out) would otherwise silently wipe every deployed file. The destructive cleanup is a separate endpoint, `POST /strategies/reconcile` → `reconcile_strategies()`, which calls `remove_strategy(sid)` for each orphan (best-effort VPS delete — 404/"not found" counts as success; a real failure is surfaced as a warning but never blocks the DB removal) and returns `ReconcileResult{removed, warnings}`. The per-strategy `DELETE /strategies/{id}` uses the same `remove_strategy` helper. Frontend (`Strategies.tsx`): Scan toast flags orphan count; a red **Reconcile (N)** button appears only when the last scan found orphans, fronted by a `ConfirmDeleteModal` listing exactly which strategies go.

**`delete_strategy` cascades the FK chain.** Foreign keys are ON, and `backtest_runs`/`optimizations` reference `strategies` (and `evaluations`/`stress_tests` reference those runs), all `NO ACTION`. So `lab_db.delete_strategy()` purges the whole chain children-first in one transaction — evaluations + stress_tests (via the strategy's run_ids) → backtest_runs + optimizations → strategy_versions → the strategy — or deleting any strategy that has runs raises `FOREIGN KEY constraint failed` (this was an unhandled 500 on reconcile of a strategy with runs).

**MT5 delete removes BOTH the `.mq5` and the `.ex5`.** MT5 loads the compiled `.ex5`, which outlives its source — deleting only the `.mq5` leaves the strategy in the Navigator and Strategy Tester. `mt5_agent_client.delete_strategy_file()` deletes both siblings (`_delete_one` per file; an already-absent sibling 404 is fine; fails only on a real error or if neither existed). NT8 has no analog — it compiles all `.cs` into one `NinjaTrader.Custom.dll`, so deleting the `.cs` + recompiling clears it.
