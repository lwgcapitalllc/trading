# CLAUDE.md — LWG Capital Algo Trading Suite

**Purpose:** Standing instructions for the XAUUSD/forex MT5 bot suite running on the Windows VPS.
**Scope:** This covers the bots, shared utilities, risk rules, scheduler, and deploy for `algos/`. It does NOT cover `command-center/`, `smart-money/`, or `engines/regime/` internals (regime is imported via the `shared_regime.py` shim).
**Status:** Active — no live bots yet; all four first-attempt bots were deleted 2026-06-22 to rebuild backtest-first. Deployment plumbing preserved, and the live-trading pipeline for the first Python strategy is now being built (`docs/LIVE_TRADING_PIPELINE.md`).
**Last reviewed:** 2026-08-12 (latest) — 🟢 **THE LIVE BOT MOVED OFF THE STANDARD DEMO ONTO THE ECN ONE, AND THE THING WORTH CARRYING IS WHY "NO COMMISSION" WAS THE EXPENSIVE ACCOUNT.** Aaron's call, after the 2026-08-10 tier measurements. `mpc_sos_fade_demo` traded account **700107749** (PU Prime MT5 Standard, `XAUUSD.s`) and now trades **700152905** (PU Prime MT5 **ECN**, `XAUUSD.p`) on the same `MT5_FFT` terminal. 🔴 **The question that had to be answered out loud is the one anybody asks: how is ECN cheaper when it charges commission and Standard charges none?** Put both costs in ONE unit and it collapses — gold is 100 oz per lot, so $1.00 per lot per side is **$0.01 per ounce per side**. **Round trip per ounce: Standard $0.31 spread + $0.00 = $0.31 · Prime $0.12 + $0.07 = $0.19 · ECN $0.12 + $0.02 = $0.14.** Standard charges **$0.19 more of hidden spread markup to save $0.02 of visible commission**. ⚠ **`SWAP IS IDENTICAL ON ALL THREE TIERS` (−79.60 / +30.25, measured on each), so swap cannot pick an account** — say so when it comes up, because "ECN has the lowest swap" is the natural guess and it is false. ⚠ **Prime and ECN are the SAME account with two commission rates** — same symbol, same spread, same swap, same 20-point stops level — so there is no trade-off to weigh and the cheaper toll wins outright. ⚠ **The 1.16R Prime↔ECN replay gap is far inside this strategy's run-to-run sd of 15.06R; the case is "strictly cheaper at identical everything else", never that number.** ✅ **Four fields moved together in the instance config and they have to move together**: `account`, `symbol` (`.s` → `.p`), `strategy_params.symbol` and `strategy_params.account_profile` (`puprime_standard` → `puprime_ecn`). ⚠ **Naming a profile whose spread is `SPREAD_UNMEASURED` cannot raise here and the reason is worth knowing before somebody "fixes" it**: bar mode returns before `PROFILES` is ever indexed, so the profile is INERT live — it is set correctly so the file never claims a tier this bot is not on. 🔴 **COMMISSION IS NOW A REAL COST THIS BOT PAYS ($1.00/side/lot) WHERE IT WAS $0.00, AND NOTHING NEEDED CHANGING TO RECORD IT** — `get_deal_breakdown()` has summed every deal of a position and reported gross / swap / commission separately since 2026-08-03, so `pnl_usd` stays NET and correct. **That is the 2026-08-03 decision paying off: a netted number cannot be taken apart later, and the day the account started charging commission the ledger already had a column for it.** ⚠ **`_measured` in the instance config is now flagged STALE rather than deleted** — most of it is a fact about the BROKER and carries, but digits, point, contract size, tick value, volume step, **filling mode** and the spread-by-hour are properties of the SYMBOL and the ACCOUNT and have NOT been re-read on `XAUUSD.p`. Filling mode is the one that bites (a wrong one is retcode 10030 and the order simply does not go on). ⚠ **The old account's $9,996.99 balance and its history do NOT come with it; 700107749 is left as it stands.** ⚠ **`magic` 770115 is unchanged and that is correct — a magic is only ever compared WITHIN one account.** ⚠ **Check the new account is CLEAN before the first start**: under `account_risk_cap_pct` a position with no stop refuses every order on the account, and a hand trade left running is exactly that. 🔴 **AND THE MOVE IMMEDIATELY BROKE THE ONE MEASUREMENT IT WAS MADE TO ENABLE, IN THE QUIETEST WAY AVAILABLE.** `broker_facts.py --sample 300` ran for five full minutes on the freshly-switched terminal, in the middle of the London/NY overlap, and reported **"no fresh ticks - market shut?"**. **MT5 streams ticks only for symbols in MARKET WATCH**, and the new account had never been asked to watch `XAUUSD.p` — `symbol_info` needs no such thing, so the whole specification block above it read correctly and currently, and only the measurement the tool exists for came back empty, wearing a sentence that points at the exchange. ✅ **Fixed: the sampler `symbol_select`s first (Market Watch only — no order state, nothing persisted), and a tick that never ARRIVED is now counted separately from a tick that never MOVED** — `none_reads` means the terminal would not answer, `stale_reads` means it answered with the same tick. **Two different failures with two different fixes had been sharing one message, which is this repo's own no-vs-cannot-ask rule inside the tool written to end guessing.** ✅ 4 new tests in `algos/tests/test_broker_facts_sampler.py`, **3 of them watched RED against HEAD** (the old code returns "market shut?", carries no `none_reads`, and never calls `symbol_select`), the fourth pinning the shut-market direction so the fix cannot simply rename one wrong answer into another. ⚠ **The fake terminal had to STOP QUOTING an unselected symbol** — a fake whose `symbol_info_tick` always answers cannot express this defect at all, which is the fixture-more-capable-than-production trap again. 🔴 **A SECOND DEFECT FELL OUT OF THE MOVE AND IT WOULD HAVE PUT A CONFIDENT WRONG NUMBER ON THE BOTS PAGE FOR EVER: `starting_balance` is an anchor for an ACCOUNT and was stored as though it were one for a BOT.** `ensure_starting_balance` wrote once and never again, so the $2,000 anchor taken on the Standard demo — which this bot grew to $9,996.99 — would have followed it onto an ECN account that OPENS at $10,000, reporting **+399% on the first poll and every poll after it** in the two places that read `total_pnl_pct` (the Bots page and Telegram's `/balance`). Nothing errors, and +399% is exactly what a bot that has been running well is expected to show. ✅ The anchor now records the account it was taken on and re-anchors when that CHANGES — never when the balance moves, which is the thing the percentage is for. ⚠ **An anchor written before the field existed is ADOPTED, not reset**: it carries no account, so *belongs to this one* and *belongs to one this bot has left* are indistinguishable, and discarding a real measurement is the worse of the two available mistakes. **So the guard could not have caught the move that motivated it** — the stale anchor was cleared by hand and this exists so the next move is automatic. ⚠ **`account=None` cannot reset anything**: *I don't know* is not *this is a different account*. ⚠ **Two test FAKES carried the old two-argument signature** and would have made the real call a `TypeError` on the live box only — the fixture-behind-production trap, twice in one commit. ✅ 5 new tests; 594 algos green. 🔴 **AND THE MOVE ITSELF EXPOSED THE SHARPEST DEFECT OF THE THREE, BY DOING IT UNDER A RUNNING BOT.** The terminal was logged from the Standard demo onto the ECN one while `mpc_sos_fade_demo` was live, and **the bot went on working**: it re-anchored its position sizing from **$1,992.21 to $9,996.99** — five times the money, off an account it had never been told about — and logged that re-anchor as the ordinary event it looks like. It placed no order in that window, so it cost nothing; the next setup would have been sized against a stranger's balance. ⚠ **The runtime-reload guard DID fire and was not enough**: it saw `account: 700107749 → 700152905` in the config and correctly refused to apply it live, saying *"restart the bot"* — but that check watches the **FILE**, and the thing that had actually moved was the **TERMINAL**. Two different questions; only one of them was being asked. 🔴 **`connect()` asserts the account, and asserting it ONCE is the whole defect.** The terminal is a shared resource for the life of the process and MT5 remembers every login it has seen, so every read afterwards is answered promptly and correctly about the wrong account — the balance it sizes from, the equity, the margin, and `positions_get()`, which returns the new account's book filtered by a magic that means nothing there. ✅ **`_check_account_identity` now runs every poll and HALTS**, with the account number captured off the SAME `account_info()` call the balance comes from (reading it separately is exactly what let two answers about one terminal disagree during the 50-minute blind outage of 2026-08-04). ⚠ **It is deliberately NOT reported as a lost link, and that is the design rather than a detail**: the link is healthy, it is the IDENTITY behind it that moved, and routing it through `_recover_link` would call `connect()` → `mt5.login()` and **drag the terminal back off whatever a human is doing on it** — a bot fighting its operator for a window neither owns exclusively. **Halting costs one human action.** ⚠ **It halts rather than closing or adopting anything**, for `adopt_broker_state`'s reason: a deliberate move and an accident are indistinguishable from here. ⚠ **An UNREADABLE login is not a match** — `None` returns early, and the absent case is already covered because an unreadable `account_info()` is a dead link and `probe_link` reports it as one. ⚠ **It LATCHES**, so a terminal flipping between logins cannot toggle a live book unattended. ✅ 9 new tests in `algos/tests/test_account_identity.py`, **all 9 watched RED against HEAD** (5 error — the method does not exist — and 4 fail because `probe_link` never captured the login). **The standing lesson is about how long an assertion stays true: `connect()`'s account check was correct, well-placed and passed every time it ran, and it ran once — after which the fact it established was free to change underneath every decision built on it. Before trusting a startup check, ask what could move afterwards and who would notice.** **The other standing lesson is about units rather than brokers: two costs quoted in different units are not comparable, and the one quoted in the unit you do not think in is the one that hides. Spread is quoted per ounce and commission per lot, they differ by 100x on this instrument, and the account that looked free was more than twice the price.** Earlier: 2026-08-10 — 🟢 **A RESTART WITH A TRADE OPEN PICKS THE TRADE BACK UP, AND THE RE-WARM PATH TURNED OUT TO BE THE BIGGER DOOR ONTO THE SAME FAILURE.** Aaron: *"if my bot goes offline and comes back online but there was a trade running, can it continue to manage the trade… this is crucial because this can happen when I go to bed."* 🔴 **It could not. `adopt_broker_state` HALTED on any position MT5 already held and `run()` returned exit 4**, so a bot that restarted overnight — box reboot, watchdog, crash, deploy — left the trade with whatever stop it had at the moment the process died. **The broker-side stop stood, so it was never naked; nothing ratcheted it again, the 36h time stop never fired, and no structure exit could close it.** `SYS_MONITOR` then restarted it up to three times, each halting the same way, and paged a CRITICAL. Median winner on this strategy holds **17.8 hours**, so it is not a corner case. ✅ **`algos/live/position_state.py` writes the open position to `<instance>/position.json`** (atomic, rewritten on the fill and on every stop move, DELETED on close) and `Execution.snapshot_position()` / `restore_position()` carry the emulator's whole open-trade state. 🔴 **THE RECORD IS DELIBERATELY NOT THE DECISION LEDGER, and the reason is this repo's own: the ledger is an append-only AUDIT log, and recovering live operational identity from a channel built to carry a status is exactly what made a Stop button cancel other platforms' jobs for months.** It also does not hold what a restore needs — the running favourable extreme the trail ratchets off, the equity baseline R is measured against, or the one-trade-per-15m-leg latch, without which a restored bot could re-enter the very setup it is already holding the moment the trade closes. ⚠ **THE RESTORE IS STRICTLY NARROWER THAN THE HALT IT REPLACES, and that is the safety property rather than the feature.** It needs exactly one position under this magic, a record written by THIS bot for THIS symbol, a ticket EQUAL to the broker's, and direction/size/entry/stop all agreeing. **Every other shape halts exactly as before** — no record, a torn record, an unknown version, a ticket that does not match, one field that disagrees — with five separate messages, because *"the two disagreed"* is true of every cause at once and sends the reader at the innocent half (the `order_vanished` lesson of 2026-08-07). ⚠ **A stop that differs is NEVER adopted, and this is the judgement call worth defending.** It means something moved it that this system does not know about — a hand edit, a broker action, or a bug on our side — and the bot cannot tell them apart. Adopting the broker's number would compute every later ratchet off a level the strategy never chose and record the wrong R with nothing to say so. **Halting costs one human action; adopting silently costs a trade managed off numbers nobody picked.** ⚠ **Compared against the symbol's POINT, never exactly** — MT5 rounds to the symbol's digits and a float round-trip through JSON is not bit-exact, so an equality test would halt on every ordinary restart and the feature would be switched off inside a week. 🔴 **THE ORDERING IS THE WHOLE REASON `apply_restore` IS A SECOND METHOD: `warm()` replays ~5,000 bars through the SAME emulator and opens imaginary trades of its own**, so a position applied before it is overwritten by a fiction. `adopt_broker_state` verifies and STAGES; `apply_restore` lands it after the warm-up, and a test asserts the emulator is untouched at the earlier point. 🔴 **AND THE RESTART WAS THE SMALLER HALF — `_recover_link` and the `gap > 4` branch both rebuild the strategy and re-warm, so a link outage MID-TRADE lost the position and halted the bot on the next bar.** That is the 50-minute MetaTrader auto-update of 2026-08-04 arriving through the recovery instead of the outage: **the bot survived the incident and was then stopped by its own repair.** `stage_rewarm()` hands the book from one emulator instance to the next; nothing is re-verified there and nothing needs to be, because it is the same process that has been holding the position all along. ⚠ **A re-warm restores SILENTLY (`announce=False`)** — `_recover_link` and the gap branch each already send a message for that event and two alerts for one event is how a channel gets muted — **but the ledger records it either way**, because *the position survived the re-warm* is invisible from outside and is exactly what a later audit needs. ⚠ **`stage_rewarm` failing does NOT halt**: the re-warm has not happened yet, so the bot is still coherent, and `_agrees` halts on the next bar if the position really is lost — the existing, tested path. ✅ **38 new tests (27 live + 11 strategy), 897 algos + strategy green, and non-vacuity proven by MUTATION on the four that carry the risk** — adopting a moved stop, skipping the ticket check, a restored bridge going WARMING, and a re-warm dropping the position each turned their own named test red. ⚠ **TWO EXISTING FIXTURES WERE STALE AND BOTH FAILED HONESTLY**: `_FakeExecution` had neither new method and `test_mt5_link`'s `_Bridge` had neither hook, which is the fixture-less-complete-than-production trap for the third time — and `test_startup_refuses_to_adopt_an_unknown_position` was passing on the WRONG refusal (it built a bridge with no instance directory, so it halted because it could not LOOK rather than because there was no record). It runs against a real, empty directory now. 🔴 **NOT YET DRIVEN ON THE DEMO, AND THAT IS THE OPEN ITEM.** This is offline-green and mutation-checked; the evidence that counts is opening a real position, killing the bot, restarting it, and watching the NEXT BAR MOVE THE STOP — because a restore that comes back and then never ratchets looks identical to a working one for hours. **This repo has a standing lesson about exactly that gap.** ⚠ **It also needs a PROMOTE**: `Execution` is in the version-pinned strategy tree, so the bot runs the old code until `promote.py` runs. The two new methods are decision-neutral (nothing in `step` / `step_secondary` / `_manage_open` calls either, asserted by test), so parity is structurally unaffected. **The standing lesson is about what "coming back online" has to mean: every recovery path in this suite rebuilds the strategy from scratch, and rebuilding state from real bars is right for the ENGINES and wrong for the BOOK — the engines can be re-derived from the market, and a position cannot be derived from anything except the record of having opened it.**

Earlier the same day: 🔴 **A REFUSED ORDER LOGGED THE WORD "SUCCESS", AND `get_deal_breakdown` HAD NEVER ONCE SEEN A DEAL.** Both found by MEASURING the PU Prime account tiers rather than reading code, and both sat in `shared/mt5_ops.py` behind a green suite. **(1) Every order-sending function logged `mt5.last_error()` on a refusal** — which reports the health of the API CALL, not of the ORDER. Reproduced on a demo with the terminal's AlgoTrading button off: the order was rejected with retcode **10027 / "AutoTrading disabled by client"** and the bot logged **`Order failed: (1, 'Success')`**. The retcode and the broker's own sentence were both on the result object and both thrown away. `refusal_detail()` renders all three now (retcode, the broker's `comment`, and `last_error` — kept because it is the only one that exists when `order_send` returns `None` outright, which is a transport failure rather than a rejection). ⚠ **`move_sl` and `close_position` logged NOTHING AT ALL**, and those are the worst two in the file: `move_sl` is how the stop stages to breakeven, which this strategy does on essentially every trade at a median of one bar, so a silent refusal leaves the STRATEGY believing it is protected while the broker still holds the original stop; a refused close leaves the bot's book and the broker's disagreeing, which is the one thing `bridge._agrees` halts on. **(2) `get_deal_result` and `get_deal_breakdown` bounded their history window with `datetime.utcnow()` while MT5 stamps a deal's `time` in the BROKER SERVER's clock.** PU Prime runs **+3h** ahead (measured), so a deal that had just happened was stamped **past the end of its own window** and both came back empty on every real fill. ✅ **Nothing would have recorded a false number — `algos/live/bridge.py` checks `deals: 0` and falls back rather than booking zero costs, so that guard did its job** — but the cost breakdown written on 2026-08-05 to answer G5 would have produced **nothing, for ever**, and the only symptom is a fallback that looks like normal operation. **A permanently absent measurement, not a wrong one.** ⚠ **The fix is a wider window and deliberately NOT a broker-clock conversion**: `markets/fx/tools/broker_clock.py` is correct for bar timestamps, but using it here would make deal history depend on the server obeying an offset rule its own docstring says only a live pull can prove — and if that rule is ever wrong for a new broker the deals go missing again, silently, which is the failure being fixed. **Correctness here never came from the window**: every caller re-filters on `position_id == ticket` and `position=` is passed to MT5 as well, so the bound is a query hint and making it generous cannot return a wrong deal. Two days covers any broker offset that exists, and a test pins that the position filter still holds. ✅ 11 new tests in `tests/test_mt5_ops_pending.py`, **9 watched RED against HEAD**; the two that pass there are kept and labelled — one pins that a server clock BEHIND UTC was always covered by the 7-day lookback (a window fixed only at the top would be the same bug mirrored), the other that `deals: 0` still means NOT FOUND rather than free. **558 algos tests green.** ⚠ **The fake terminal had to learn to REFUSE and to filter deal history by time** — a fake whose `order_send` always succeeds and whose `history_deals_get` ignores its own bounds would have let both defects pass, which is the fixture-more-capable-than-production trap this repo keeps meeting. **The standing lesson is about which half of a system a diagnostic describes: `last_error()` is a real, correct, well-named function that answers a question next to the one being asked, and its answer on a rejected order is "Success". Before trusting a diagnostic, ask what SUBJECT it is reporting on** — the transport, the call, or the thing you actually did.

Earlier the same day — 🟢 **A BOT CAN BE TAKEN OFF AN ACCOUNT NOW, AND THAT NEEDED A STATE THAT DID NOT EXIST: THE BENCH.** Aaron asked to add and remove bots from an account in the browser — *"if I wanna remove a bot from account, I can remove it, and the next one could just continue"* — and removing has to land SOMEWHERE. `LiveConfig.account` is `Optional[int]` and **`null` means registered, configured, and deliberately on no account**; the KEY stays required, so *deliberately unassigned* and *somebody forgot the account* stay different mistakes with different fixes. **`mpc_bleg_demo` is the first bot to ship on it** — a real instance, magic 770116, params DUMPED from `BLegConfig` rather than transcribed, trading nothing. ⚠ **THREE places enforce the bench and one would not have been enough**: `runner._run` refuses (exit 0, no alert — a benched bot is a choice, not a fault), and `startup_coordinator` SKIPS it in the boot sequence and REFUSES in single-bot mode. The runner alone is a guard that fires *after* the process is spawned, so the boot task and the watchdog would go on spawning one every 60 seconds for ever. ⚠ **Both per-account guards had to stand down for it, and `None == None` is why**: without an exemption `_assert_magic_is_unique` and `_assert_account_cap_agrees` fire BETWEEN TWO BENCHED BOTS — refusing to load a bot that is not trading because of another bot that is not trading either, and worse, blocking an assignment because of an unrelated benched sibling's leftover cap. Both re-arm the moment either bot is assigned. 🔴 **`BOT_ACCOUNTS` IS DELETED, AND IT WAS A SECOND COPY OF A FACT THAT CAN NOW MOVE.** It hardcoded a login per bot in `shared/bot_state.py` and was stamped into `bot_state.json`, which is what the Bots page renders in its Account column — so the moment that page could MOVE a bot, the row would have gone on showing the old number while the bot traded the new one. `read_account()` reads the bot's own config, the same file the bot reads. ⚠ **`is_assigned()` is the ONE definition of the bench**, shared by the coordinator, `monitor.py` and `deadman.py`; three copies is three chances for one of them to alarm about a bot somebody deliberately removed, which is how a channel gets muted. ⚠ **Both watchdogs REGISTER the benched bot and skip it per-pass, rather than registering it on assignment** — the static registry is complete, so the Bots page can never arm a bot nothing is watching. `monitor.py`'s skip is the load-bearing one: its response to an offline bot is to START it. ⚠ **Unreadable answers ASSIGNED everywhere** (`_instance_config` returns `None`, never `{}`) — "no account" and "cannot ask" must not be one value, and quietly not watching a live bot is the failure with no symptom. ✅ **DRIVEN through the running backend, not reasoned about: `PATCH /bots/mpc_bleg_demo/account` moved it onto 700107749 — cap 10% ADOPTED, `stacked: true`, `cap_takes_turns: true`, no magic clash — and BOTH configs still load under the startup guards**, which is the check that says the assignment left the account coherent rather than taking the live bot off the box at its next restart. Moved back to the bench and the config restored. ✅ 25 new tests (547 algos green), non-vacuity by MUTATION throughout — the two bench exemptions, the runner refusal, the coordinator's two defaults, the unreadable-config direction and the watchdog skips each turning their own named test red. 🔴 **Two EXISTING guards went red and both were RIGHT to**: `test_every_bot_the_vps_starts_is_watched` caught that registering B-LEG in `STARTUP_SEQUENCE` without registering it with the watchdog would let an assignment outrun the alarm — the reason both watchdogs now carry it — and a kill-scope test named `mpc_sos_fade_demo` as a literal, which is a roster stated twice; it READS `bots._BOTS` now. ⚠ **Benching writes ONLY `account: null`** and leaves the server, terminal and cap alone, so a bot that has been on an account carries that account's old cap while benched — inert (the guard exempts the bench) and deliberately cheap to re-assign. 🔴 **`mpc_bleg_demo` MUST NOT BE ASSIGNED YET and its config says so in `_NOT_VALIDATED`**: `compare_bleg.py` has not run since that fork's defaults moved on 2026-08-06, so every export on disk decodes the OLD values and the last green parity run describes a strategy that no longer exists. It is also UNPROMOTED. **The standing lesson is about what "remove" means: the feature was asked for as a button, and the thing it actually needed was a resting state for a bot to be in — and the moment that state existed, every registry holding its own copy of "which account" or "should this be running" became a place that could disagree with it.**

Earlier the same day: 🟢 **THE ACCOUNT CAP IS ON, AND A NUMBER THAT LIVES IN N FILES NOW HAS TO AGREE WITH ITSELF.** Aaron set the cap at **10%** ahead of a second bot, so `mpc_sos_fade_demo` carries `account_risk_cap_pct: 10.0` — the field shipped the same morning and was configured nowhere, which is the one state that reads as protected and is not. ⚠ **10% EQUALS this bot's own `exec_risk_pct`, so two bots will not SHARE the budget — they take turns**: one full-size position or resting limit fills the whole $200 on this $2,000 account and the other is REFUSED until the room returns. That is exactly the requested behaviour and it is written into the config's own note, because it is not obvious from the number — a cap that lets both hold at once has to exceed the sum. ⚠ **A RESTING order counts here and does NOT in `backtest/portfolio/`, which reserves at the FILL** — this strategy enters on a limit that can sit unfilled for hours, so **live contention will be MORE frequent than the shared-account backtest predicts and its empty contention log is not a forecast.** ✅ **The account was PROBED read-only before arming it — 0 positions, 0 resting orders, 0 stopless — because ONE hand trade with no stop refuses every order on the account**, and that failure reads exactly like a strategy that stopped finding setups. Re-probe after any manual trading. 🔴 **THE REAL WORK WAS THE GUARD UNDER IT: the cap is an ACCOUNT-level fact stored PER INSTANCE, so the same number lives in N files and can disagree in N ways** — and `bridge._account_cap_check` reads the CALLER's own setting, so **which number binds depends on which bot happens to ask, and the account's real ceiling becomes the LARGEST of them: the least protective, chosen by nothing.** `live_config._assert_account_cap_agrees` refuses to start a bot into that state, the same shape as the magic-uniqueness check beside it. ⚠ **A MISSING cap is a DISAGREEMENT, not a neutral value, and that is the case worth stating**: `null` means uncapped, so one capped bot beside one uncapped bot is the worst of the shapes — the uncapped bot fills the account freely while the capped one is refused, so the guard does nothing except handicap whichever bot was configured correctly. Reading `null` as *no opinion, inherit the sibling's* would be this repo's own *no* vs *cannot ask* defect with the absent value silently acquiring a meaning nobody wrote down. ⚠ **It REFUSES rather than warning, and the cost is deliberate**: an incoherent cap takes every bot on the account off the box at its next start, which is loud and recoverable, where a warning leaves an account trading under a ceiling that is not enforced and reads on screen as though it is. ⚠ **NOT runtime-reloadable — the config says 10% and the process is still UNCAPPED until it restarts.** ✅ 8 new tests (523 algos green), **3 watched RED** against the guard removed. **The standing lesson is about where a fact lives: an account-level number stored in a per-bot file is not one setting, it is N settings that happen to share a name — and nothing was checking that they agreed.** Earlier the same day: 🟢 **THERE IS A FLEET KILL SWITCH NOW, AND THE INTERESTING HALF IS WHAT IT DOES WHEN IT CANNOT READ ITSELF.** The bridge has always halted ONE bot on its own emulator/broker divergence, and `stop.request` has always stopped ONE process; neither is a fleet switch, so there was no way to say *"stop the whole account, now"* — which is the one thing you want at 3am before you know which bot is wrong. `algos/shared/fleet_halt.py` + `algos/tools/fleet_halt.py` + a check at the top of every runner poll. ⚠ **A FLAG FILE, because live bots are separate OS PROCESSES** — the same constraint that stops the live allocator reusing `backtest/portfolio/`'s in-memory account — **and the switch is deliberately pullable WITHOUT the tool**: `echo why > C:\trading\algos\FLEET_HALT` is the whole mechanism, because the day you need it is the day something is broken and a Python entry point that will not start is a switch that does not exist. ⚠ **IT STOPS ORDERS, NOT THE PROCESS AND NOT THE BOOK.** The loop keeps running, keeps heartbeating and keeps writing its ledger, and anything open keeps its BROKER-side stop. **Flattening a book is a trading decision and a safety device must not take one.** 🔴 **`Path.exists()` CANNOT BE USED HERE AND USING IT IS THE TRAP.** It answers `False` both when the flag is absent — the healthy state — and when the DIRECTORY is gone, which means this bot has no way to be told anything: **two opposite situations reported with one value**, the standing *no vs cannot-ask* rule arriving on the one path where the reassuring answer is also the dangerous one. `stat` does not rescue you either — a missing parent and a missing flag raise the SAME errno — so the module stats the **DIRECTORY first** and the file second, and only a clean directory stat lets `FileNotFoundError` on the flag mean *clear*. **Without that probe, `rm -rf` on the folder is a silent way to disable the switch and nothing reports it.** ⚠ **CANNOT-READ HALTS (Aaron's call), which is the OPPOSITE default from `runner._stop_file_present`, deliberately** — each default is safe against the failure ITS path causes, the same asymmetry as `startup_coordinator` vs `runner.already_running`: a false STOP ends a healthy process, a false HALT only refuses new orders while the bot stays alive with its positions protected. **A missed trade is recoverable; a kill switch that goes quiet on the day the disk is sick is a configuration, not a switch.** ⚠ **IT LATCHES — clearing the flag does NOT resume trading, and the tool says so on every `--off`.** A flapping or intermittently-unreadable filesystem would otherwise toggle a live book on and off unattended, and every other halt here is terminal-until-a-human-looks. Resume is: clear the flag, restart the bots. ⚠ **The flag SURVIVES a restart on purpose and must never be auto-cleared the way `stop.request` is** — `SYS_MONITOR` restarts a dead bot within ~60s, so an auto-cleared flag would be undone by the recovery system itself. ⚠ **It routes through `bridge.halt()` rather than adding a second gate**, so there is ONE answer to *may this bot place an order* — and the payoff is free: the pulse already carries `bridge_state`, so `log_review.py`'s existing halted rule raises the standing **Needs review** chip with no new rule and **no second alert for one event**. ✅ **It is `.gitignore`d, and that one matters**: a committed `FLEET_HALT` would halt every bot on the box at the next `git pull`. ✅ **DRIVEN END TO END, not just tested** — `--on` / `--status` / `--off` against the real path, with the reason, the user and a UTC stamp written into the flag and read back. ✅ 16 new tests, 516 algos green; **five mutations each caught by the right test** — the directory probe removed, the unreadable branch failing open, an empty flag ignored, the bridge never halted, and the latch deleted. 🔴 **A defect found by the suite rather than by reading: the loop test builds its runner with `LiveRunner.__new__`, so the new latch field did not exist and `_check_fleet_halt` raised `AttributeError` on its first line — which the loop's outer handler swallowed as a generic loop error, leaving a pass that silently read no bars and stamped no heartbeat.** ⚠ **That is the fixture-less-complete-than-production trap in its usual costume, and the giveaway was that the failure was SILENT**: a safety check that raises inside a `while True` whose handler counts toward a shutdown does not announce itself, it just stops the thing working. **When you add state a hot loop reads, grep for `__new__` before trusting the suite.** ⚠ **STILL NOT EXERCISED AGAINST A SECOND BOT**, for the same reason as the risk cap — there is no second instance. **The standing lesson is one this repo keeps meeting from new angles: the reassuring answer and the broken answer must not share a value, and here they shared a FUNCTION — `exists()` collapses "nothing to report" and "cannot be asked" into one `False`, and every caller of it in a safety path inherits that.** Earlier the same day: 🟢 **A SECOND BOT CAN NO LONGER OVERDRAW THIS ACCOUNT, AND THE ALLOCATOR READS THE BROKER RATHER THAN TRUSTING ANY BOT.** Aaron's requirement — *"if one bot wants to trade, but there's no risk available to trade on, it should be blocked by the system"* — is the live half of G10, and `exec_risk_pct` has been per-TRADE with nothing above it since the day it was written: two bots at 10% put 20% on from a state neither could see. Four pieces: `shared/account_risk.py` (the arithmetic and the refusals, pure and offline), `mt5_ops.account_exposure()` (the read), `bridge._account_cap_check` at the single sizing seam, and `account_risk_cap_pct` on the instance config. 🔴 **THE BROKER IS THE SOURCE OF TRUTH AND THAT IS THE DESIGN, NOT A COMPROMISE.** Every alternative — a shared state file, a lock, a message bus — needs the bots to trust each other, and a bot that crashed or was killed leaves a stale reservation, so the cap then bounds a fiction. The broker knows what is actually open **and knows the STOP on every one of them**, because this suite puts the stop at the broker by design (D4) — so risk-to-the-CURRENT-stop is READ rather than inferred, and a stop moved to breakeven frees its room exactly as it does in `backtest/portfolio/`. 🔴 **IT NEEDED THE ONE UNFILTERED READ IN THE LIVE PATH, AND THAT IS A DELIBERATE EXCEPTION TO A STANDING RULE.** Every other read in `mt5_ops.py` is MAGIC-filtered — correct for isolation, and **exactly what makes a bot blind to the account it shares**. `account_exposure()` reads everything on the symbol whoever placed it, and it never cancels, modifies or closes any of it: **the isolation rule is about WRITES**, and nothing here writes. ⚠ **A position with NO stop REFUSES the order rather than scoring zero risk** — its risk is unbounded, not absent, and the falsy value it arrives as has the same shape as *no risk*, so scoring it zero would let the one thing the cap exists to bound sit invisibly underneath it. A hand trade left running is exactly that. ⚠ **An unreadable account REFUSES**: a cap that opens itself when the terminal wobbles is absent exactly when the account is least healthy — *cannot ask* is never *affordable*, the `mt5_link` rule applied to money for the sixth time. ⚠ **It REFUSES, it never SHRINKS, and the backtest allocator SHRINKS — that difference is named rather than papered over.** Shrinking is coherent in the backtest because the account hands the granted size back and the same process's emulator opens at it; **nothing hands a size back across a process boundary**, so a shrunk live order would leave the emulator holding one trade and the broker a smaller one, they would grade different R, and `_agrees` would halt the bot on a divergence the safety feature created. **Anything that tunes the cap must be replayed under the REFUSE policy.** ⚠ **This bot's OWN exposure is excluded and that is not a shortcut**: one position slot, so anything of ours on the book is what this order REPLACES — counting it would make the bot refuse its own re-sizes near the cap, which reads exactly like a broken strategy. ⚠ **`null` = UNCAPPED, and the runner SAYS SO at every start** (a `risk_cap` health record plus a warning line), because a cap that is set and a cap that is absent behave identically on an empty account — the only moment the difference is legible is before anything has happened, and *"I thought the cap was on"* is precisely the belief that makes an uncapped second bot feel safe. Same call as `deadman_url`. ✅ **MAGIC NUMBERS ARE NOW ENFORCED UNIQUE PER ACCOUNT** (`live_config._assert_magic_is_unique`): two bots sharing one would each read the OTHER's position as their own — cancel its orders, ratchet its stop, book its fill — **the doubled-book failure the duplicate-process guards exist to prevent, arriving through CONFIGURATION instead of through a second process.** Per ACCOUNT, not global; the terminal scopes orders by login. 🔴 **A DEFECT IN MY OWN FIRST DRAFT, CAUGHT BY ITS TEST AND WORTH RECORDING: `measure_exposure` used `abs(entry - stop)` and carried no DIRECTION**, so a long whose stop had ratcheted ABOVE its entry scored its LOCKED-IN PROFIT as risk — and grew it as the runner ran. A winning trade would have held the budget shut against the other bot for as long as it kept winning, which is the exact opposite of what a reserve-to-the-current-stop model is for. It now uses `max(0, dir * (entry - stop))`, the identical expression `backtest/portfolio/account.py` uses — **two sides of one rule must not be two expressions of it.** 🔴 **SUPERSEDED THE SAME DAY — THE LIVE BOT NOW CARRIES THE CAP AT 10% (Aaron's call), so the "unchanged" claim below is history rather than the current state.** It read: *"it has no cap configured, `account_exposure` is never called, and its config loads with `account_risk_cap_pct = None`"* — true when the cap shipped, and false the moment it was configured. `mpc_sos_fade_demo/config.json` now sets `account_risk_cap_pct: 10.0`, verified through the real `live_config.load` rather than by reading the file. ⚠ **10% EQUALS this bot's own `exec_risk_pct`, so a second bot does not SHARE the budget with it — the two take turns**: one full-size position or resting limit fills the whole $200 on this $2,000 account and the other bot is REFUSED until that room returns. That is exactly the requested behaviour and it is worth stating out loud, because a cap that lets both trade at once would have to be 20%. ⚠ **A RESTING order counts, and this strategy enters on a limit that can sit unfilled for hours** — so live contention will be MORE frequent than any `backtest/portfolio/` run predicts, since that side reserves at the FILL. **Do not read the stack backtest's empty contention log as a forecast for this account.** ✅ **The account was PROBED read-only before the cap was armed — 0 positions, 0 resting orders, 0 stopless — because a single hand trade with no stop REFUSES every order on the account**, and that failure would look like a strategy that stopped finding setups. Re-probe before trusting the cap after any manual trading. ⚠ **It is not runtime-reloadable**: until the bot is restarted the config says 10% and the process is still running UNCAPPED, which is the one state that reads as protected and is not. ✅ 29 new tests, 500 algos green; **three bridge mutations each caught by the right test** (the cap neutered, the own-magic exclusion removed, a cap applied where none was configured) and two more on the magic guard. ⚠ **NOTHING HERE HAS BEEN DRIVEN AGAINST A REAL SECOND BOT**, because there is no second instance to drive it with — it is unit-tested and mutation-checked, not exercised, and this repo has a standing lesson about exactly that gap. ⚠ **Still open on the live side: no account-level HALT or fleet kill switch** — the bridge halts only its own bot. **The standing lesson is about a rule that was right and was still the problem: magic-filtering every read is correct isolation and it is precisely what made an account-level cap impossible, because a bot that can only see its own orders cannot know the account is full. Before adding a guard, ask what the existing correct rules make it unable to see.** Earlier: 2026-08-07 — 🟢 **STOPPING A BOT NOW ASKS IT TO STOP, AND A HALT THAT RECOVERED READS AS HISTORY.** Two cosmetic-but-corrosive defects, both found by Aaron reading a **NEEDS REVIEW (3)** chip on a bot that was perfectly healthy. 🔴 **Every deliberate stop in this system was a hard `wmic ... call terminate`, so the bot never reached the `finally` that writes its `shutdown` record — and the next startup dutifully reported *"the previous run ended WITHOUT a shutdown record: it was killed, it crashed, or the box went down."*** That sentence **IS** the silent-death detector (`### The daily record`), the only thing that can tell you a bot died without saying so, **and it was firing on every restart anybody performed on purpose.** ⚠ **An alarm that fires when you press the button is one you learn to scroll past**, so the noise was not the cost — the cost was the signal it was burying. ✅ **`_kill_bot` now writes `<instance>/stop.request`, waits up to 30s, and terminates only a bot that ignored it**; `runner._loop` checks for the file at the top of every pass and exits through the ordinary clean path, writing its own record. ⚠ **A FILE and not a signal, because Windows has no usable SIGTERM for a console process** — `taskkill` without `/f` posts WM_CLOSE, which a Python console app never receives — and a file fits what this loop already is: something that polls its own instance directory and re-reads its config from there. ⚠ **The escalation is not a fallback nobody exercises**, it is the honest answer for a wedged bot or one blocked in an MT5 call, and the return value says which path ran. ⚠ **THE ONE WAY THIS COULD BE WORSE THAN THE KILL IT REPLACES is a STALE request stopping a healthy bot seconds after boot** — from a crash, a failed shutdown, an aborted SSH call — so `run()` clears the file BEFORE the loop, both sides delete it after use, an unreadable directory is **never** read as a stop request, and a clear that fails **warns rather than refusing to start** (one clean shutdown after boot is visible and recoverable; a trading bot that will not start because a marker file would not delete is not). 🔴 **The second defect is the chip's TENSE, and it is a lesson about sticky findings rather than about wording.** `review.json` deliberately persists — a Telegram line you scrolled past at 3am is gone — but the halt finding kept saying *"the bot is placing nothing … Check the account"* in the present tense hours after the bridge came back, **so a recovered bot was indistinguishable from a broken one.** It now follows the CURRENT bridge state: ALERT and present-tense while halted, **WARN and past-tense once the heartbeat says live again**, still carrying the reason because *why did it halt* stays the open question. ⚠ **The KEY is unchanged either way and that is load-bearing** — re-rendering the same incident must update the chip WITHOUT re-announcing it, which is exactly what the `_ts`/`_at` split exists for. ⚠ **One EXISTING test had to be corrected rather than the behaviour**: it fed a `halted` event followed by *live* pulses and asserted ALERT, but a bridge never returns to live without a restart, so that fixture was always a RECOVERED halt — it had been passing on a scenario it misdescribed. ✅ **10 new tests watched RED against HEAD** (4 in `command-center/backend/tests/test_bot_kill_scope.py`, 6 across `test_graceful_stop.py` / `test_log_review.py`); **471 algos + 752 backend green.** ⚠ **The kill-scope suite needed a second fixture** — its whole subject is that the terminate command names `python.exe` AND `--bot <key>`, and after this change a healthy bot never reaches that command, so the scope tests now drive a bot that IGNORES its stop request. **A safety test whose scenario stops occurring passes for ever and protects nothing.** ⚠ **One pre-existing backend failure is untouched and is not mine**: `test_python_runner.py::test_the_broker_profile_changes_the_spread` still asserts 0.33 where `fills.py` has said 0.32 since it was re-measured.

Earlier the same day: 🔴 **THE LIVE BOT RESTED A 54.82-LOT ORDER ON A $2,000 ACCOUNT, IT SAT THERE FOR EIGHT HOURS LOOKING HEALTHY, AND THE BROKER DELETED IT AT THE FILL WITH `[no money]`.** Aaron asked why he kept getting notifications. The bot was HALTED. **The intended size was 0.25 lots — it sent 221x that** — and no artefact anywhere in the system, at any point before the fill, said anything was wrong. 🔴 **TWO FAULTS MULTIPLIED, AND NEITHER WAS VISIBLE.** **(1) UNITS.** `Execution` sizes in INSTRUMENT UNITS (`qty = equity·risk%/stop_distance`, i.e. OUNCES for gold) and `bridge._sync_side` handed that straight to MT5's `volume`, which is LOTS. Gold's contract is 100 oz, so **every order this bot has ever placed was 100x** — and the only place `trade_contract_size` appeared in the entire live path was reading a fill *back*. **(2) EQUITY.** The strategy is built with the real balance and then replays 5,000 warm-up bars **through the same emulator**, whose simulated trades book onto its own balance; after warming it was sizing against **~$4,423** of profit it had imagined. Its own orders prove it — three setups, three different stop distances, all three risking **$442.30**, which is 10% of a balance that did not exist. ✅ **MEASURED off the account, not inferred: MT5's order history says `order 320620565 ... state 5 ... comment 'deleted [no money]'`, and the −$7.50 on the balance is a HAND trade (magic 0, 0.05 lots, opened and closed 11 seconds apart) — not the bot.** ✅ **FIXED IN ONE SEAM: `algos/shared/order_sizing.py` is now the ONLY place in the live path a lot count is produced.** Lots come from the MONEY — `(stop_distance / tick_size) x tick_value` per lot, every number read off the broker — which is instrument-, broker- and account-currency-agnostic by construction, so a JPY pair, a gold CFD and an index are the same arithmetic. ⚠ **Be exact about which guard catches what, because a guard credited with more than it does is how the next one ships.** The units-route CROSS-CHECK (`qty / contract_size`) does **NOT** catch a caller passing an already-wrong quantity — both routes scale with `qty`. What it catches is the SPEC disagreeing with the STRATEGY: a `point_value` of 1.0 inherited from gold onto USDJPY is wrong by ~150x and is refused. **The MARGIN check is the backstop that has no opinion about causes**, and on 2026-08-07 it alone would have stopped the order eight hours before the broker did. The AUTHORISED-RISK check (`intended_risk == equity x risk% / 100`) is the one that sees fault 2. ⚠ **REFUSING IS THE ANSWER, AND IT IS NEVER A ROUNDING-DOWN — this is Aaron's question answered directly** (*"what if you want 0.18 of a lot and the account can't handle it?"*). Below the broker minimum → **no trade**, never round UP (the minimum would be a bigger bet than the strategy risk-checked, on an account already too small for the one it wanted). Above the maximum → **no trade**, never CLAMP. Unaffordable on margin → **no trade**, never shrink to fit — **a smaller position is not the trade the emulator is holding, and the two would drift apart silently, which is the same divergence that halts the bot arriving quietly instead of loudly.** ⚠ **"Cannot ask" is never "affordable"**: a margin figure the terminal declines to compute REFUSES, the `mt5_link` three-state rule applied to money. ✅ **The equity fix is a re-anchor at every FLAT moment** (the same seam `_maybe_reload_runtime` uses), not a one-off reset — a live balance moves, and one reset at startup drifts again. ⚠ **A balance that cannot be READ leaves the emulator alone**, because writing a stand-in is the failure being fixed arriving through the fix. 🔴 **A THIRD DEFECT, and it is the one nothing could see: a resting order the BROKER deletes left no trace at all.** The bridge went on believing the order was there; the emulator filled itself; six hours later a generic halt said the two disagreed. `_observe_vanished` now names it the moment it happens, and the halt message QUOTES the refusal that caused it instead of the sentence that is true of every cause at once. 🔴 **A FOURTH, which is why Aaron was being paged all night: `log_review.py`'s "Bridge is HALTED right now" keyed its dedup on the LATEST PULSE, written every 15 minutes** — so the hourly reviewer minted a new key every run and re-alerted for as long as the bot stayed halted. **That is the de-duplicating-alerter bug committed inside the module whose own docstring warns about it**, and the existing test could not catch it: it asserts the two runs SHARE a key (an intersection), and the stable `halted:` key is in both. **A finding that re-keys itself is invisible to a test that only asks whether *something* matched — assert on the key that is supposed to be stable, BY NAME.** ✅ **`order_too_small` is absorbed into `order_refused` carrying a `code`**: it was one of eight ways an order can fail to reach the broker, and naming one of them left the other seven — including the margin refusal — with nowhere to be recorded. ✅ **`order_placed` now records the MONEY** (`risk_ccy`, `intended_risk_ccy`, `margin_ccy`, `units`), because a 221x position previously left an artefact indistinguishable from a correct one. ✅ **46 new tests, 463 algos green. The eight bridge tests and the reviewer's dedup test were WATCHED RED against HEAD** — the units one failing with *"sent 24.79 lots"*, i.e. the incident reproduced in a test. ⚠ **`test_order_sizing.py` is deliberately mostly about instruments this repo has never traded** (EURUSD, USDJPY, a cash index), because that is where a gold-shaped assumption surfaces; and ⚠ **two test FAKES were found lying and were fixed**: `_FakeMt5Ops.place_pending_limit` recorded the call and left its own order book empty, so `get_pending_orders()` always said "nothing resting" — indistinguishable from the broker having deleted it, i.e. the exact condition the new check watches for — and the bridge fake now returns the SAME `SymbolSpec` dataclass production returns, so a fixture can never again be more complete than the code (the `test_secondary.py` trap of 2026-08-06). **The standing lesson is about where a unit lives: the strategy and the broker each had a coherent, documented, tested idea of what a quantity meant, and NOTHING owned the conversion between them — so there was no single place a reviewer could have looked to find it missing, and every artefact on both sides read as correct. Before trusting any number that crosses a system boundary, ask what its UNIT is on each side and which line converts it.**

Earlier: 2026-08-06 — 🟢 **THE MT5 AGENT SENDS TICK VOLUME NOW, AND IT HAD BEEN DROPPING IT SINCE THE DAY IT WAS WRITTEN.** Aaron's brother asked for a VWAP on the command center's backtest chart. `engines/vwap/` was already built and Pine-parity green; **what was missing was the data.** `_rates_to_bars` built every bar as `time`/`open`/`high`/`low`/`close` and never read `tick_volume` off the rates array — so no consumer downstream could ask for volume, because it was discarded at the source. One field added. ⚠ **`tick_volume`, NEVER `real_volume`:** there is no exchange behind a CFD quote, so `real_volume` is 0 on every broker here and reading it would hand every consumer a confident zero. Tick volume is also precisely what TradingView plots as `volume` on the same symbol, which is the series `engines/vwap/` was validated against — so the line the chart draws and the line on Aaron's chart are computed from the same numbers. ⚠ **The field access is direct (`r["tick_volume"]`), not a defensive `.get`**, deliberately: the dtype is stable and documented, and a silent fallback here is exactly the failure being fixed — if MT5 ever stopped supplying it, a loud break is the correct outcome. ⚠ **This is HALF of a two-part deploy and the order matters.** `backtest/data/cache.py::FEED_VERSION` went 2 → 3 in the same change so every cached file re-pulls itself; a fetch made AFTER that bump and BEFORE this agent is on the VPS writes a file stamped current while holding no volume, which then never re-pulls. `BarCache.has_volume()` makes that state visible (`False` ⇒ delete that pair's `.csv` and `.meta.json`). **Deploy the agent first.** ⚠ **Picking up this change needs `git pull` on the VPS AND a restart of the `MT5AgentRDP` task** — the agent is a long-running process, unlike the NT8 compile runner which is respawned per job — and the restart is a scoped kill of the `mt5_agent.py` PID, never a blanket `taskkill python.exe`, which would take the live trading bot with it. ✅ A source test in `backtest/tests/test_volume_passthrough.py` asserts the field is still sent, because this function cannot be imported off the VPS (it needs the real MetaTrader5 package) and dropping the field again is silent everywhere downstream — an absent volume simply removes the chart layer. **The standing lesson is small and specific: a data source's schema is decided by the function that transcribes it, and a field left out there is indistinguishable from a field the broker does not have.**

Earlier the same day: 🔴 **"SWAP IS A FACT ABOUT THE SYMBOL, SO IT IS THE SAME ACROSS A BROKER'S ACCOUNT TIERS" WAS WRITTEN DOWN AS A NAMED ASSUMPTION IN THE MORNING AND DISPROVED THE SAME DAY BY THIS TOOL.** Aaron asked for it to be settled properly rather than left as a caveat. `broker_facts.py` gained **`--symbols`**, which lists every symbol on the terminal sharing the traded one's ROOT — the same market, quoted again — with each one's `trade_mode`, swap and live spread. ✅ **MEASURED on the live PU Prime demo, one command: `XAUUSD.s` and `XAUUSD.crp` are the SAME market** (median M15 close difference **$0.08** over 200 shared bars) **on ONE account**, and carry **swaps 8.5x apart — long −79.60 vs −9.35 — with the short CREDIT gone entirely, +30.25 vs +0.04**, and spreads of **0.320 (1,915,768 ticks) vs 0.130 (708,565 ticks)**. ⚠ **`XAUUSD.crp` is `trade_mode: DISABLED`, so it is EVIDENCE, not an opportunity** — and that is precisely why the tool prints the trade mode in the same row as the tempting numbers, because the first reading of this table was "there is a far cheaper gold on this account". 🔴 **The consequence is in `backtest/fills.py`: the raw PU Prime tiers now REFUSE their swap as well as their spread** (`UNMEASURED_SWAP`), because a strategy trading both sides has its entire swap arithmetic decided by that short credit — borrowing another product's swap is not a small approximation. ⚠ **The terminal cannot answer the ACCOUNT-TIER question either way**: the suffix scheme across all 1,015 symbols is `.s` / `.24H` / `.crp` / no-suffix, i.e. product lines, not tiers — **so a second account is the only way to measure Prime or ECN**, and the sentinel stays until one exists (`docs/BROKER_QUESTIONS.md`). **The standing lesson is about how an assumption survives: this one was checkable in one command the whole time, and it lasted because nothing existed to check it with.** Writing it down as ⚠ NAMED rather than measured felt like diligence and was still just a comment. **When you name an assumption, ask what it would cost to test it — here it was ten minutes and a read-only script.** Earlier the same day: ✅ **G5's MEASURABLE HALF IS CLOSED: PU PRIME'S COSTS ARE MEASURED, AND TRADING THIS STRATEGY ON THE REAL BROKER COSTS 23% MORE THAN EVERY TABLE IN THIS REPO SAYS.** `broker_facts.py` gained `--history-days N`, which reads the terminal's OWN TICK STORE instead of waiting for sessions to come round — **1,893,438 ticks over 3 whole days** against the 120-second London/NY snapshot the first attempt managed, and its own note had said to re-run in an Asian session and across a rollover before the number went into a cost model. **You cannot do that by waiting; you do it by reading the ticks that are already there.** Still read-only, still asserts the account first. ✅ **MEASURED: spread median $0.32** (p90 0.32, p99 0.37, max 0.39) against Vantage's $0.22; **swap long −79.60 / short +30.25** (a CREDIT), identical on 2026-08-05 and 2026-08-06; broker min stop 20 points = $0.20; commission $0.00. ⚠ **The spread is FLAT at $0.32 in 22 of the 23 traded hours.** The 21:00–22:00 UTC daily break holds no ticks at all and the hour that REOPENS after it is the only wide one (median $0.35, p99 $0.39) — **on this broker the reopen is where the spread lives, not the session.** A fixed marked-up spread also confirms this demo is the commission-free STANDARD tier, not a raw one. 🔴 **A SWAP IS NOT A CONSTANT, and that is the finding to carry.** `backtest/fills.py` carried −78.29 / +29.49, read off the Specification window on **2026-07-16**, and they were 1.7% / 2.6% adrift three weeks later. Nothing announced it and nothing could have caught it: a swap is read once, hardcoded, and then quietly describes a rate the broker has moved on from — and swap is the LARGEST re-priceable cost on this strategy. **Re-run this tool before quoting any cost figure.** 🔴 **A BUG I INTRODUCED AND CAUGHT, worth recording because it is this repo's own never-assume-the-clock trap reintroduced by the code written to avoid it:** the first version measured the server offset off whichever history chunk it processed first — the OLDEST — and reported **UTC−48**. The overall distribution was unharmed (it needs no clock), but every by-hour label was silently the BROKER's hour wearing a UTC heading, and **−48 ≡ 0 (mod 24)**, so the buckets looked plausible, self-consistent and wrong. It reads the LIVE tick now (measured **UTC+3**, the DST half of `broker_tz_offsets '2,3'` — the winter +2 is still unverified), and when the offset cannot be measured it **prints no by-hour table at all** rather than one under a heading it cannot justify. ⚠ **The instance `_measured` block is updated by HAND, not by the tool** — that block is a claim about when a reading was taken and by whom. ⚠ **Editing it does NOT disturb the running bot**: `live_config.load` strips every `_`-prefixed key, and `_maybe_reload_runtime` has an explicit *cosmetic edit (a comment, a note)* branch that consumes the mtime silently — checked before committing, because a false SETTINGS NOT APPLIED alert on a live bot is exactly the noise that gets a channel muted. **The cost, replayed rather than estimated** (155,531 M15 bars, one real replay per row): free +142.18R · Vantage costs +130.59R · **PU Prime costs +127.91R**, max drawdown 5.61 → 6.83R. 🔴 **89% of the gap is the SPREAD, not the swap** — spread alone costs 7.67R here against Vantage's 5.28R, while swap alone is 6.60R against 6.31R, because PU Prime's worse LONG swap is almost exactly cancelled by its better SHORT credit and this strategy trades both sides. **The bigger cost is not the one that differs.** ⚠ **Still assumed: commission** ($0.00 on the standing demo fact, unconfirmed until a real fill — `get_deal_breakdown` records it per trade). ⚠ **Three days covers every hour but no weekend and no major news cycle.** 420 algos + 295 backtest tests green. Earlier: 2026-08-05 — 🔴 **EVERY BLOCKED AND MISSED SETUP IN THE LIVE DECISION LEDGER WAS THE WARM-UP REPLAY, NOT A DECISION THE BOT MADE — 560 ROWS ACROSS THREE DAYS AND NOT ONE OF THEM FROM THE DAY IT WAS WRITTEN.** Aaron asked for the live bot's logs to be debugged for anything fishy; this is what came out. `LiveRunner.warm()` replays ~5,000 bars to build engine state, and `execution.step()` appends every blocked and missed setup to `execution.blocks`/`.misses` — it cannot tell a replay from a live bar, because it is the same object either way, **which is the property that earns Pine parity and must not change.** Nothing cleared those lists after the warm-up, so `_drain_records()` wrote the entire accumulation on the FIRST LIVE BAR, stamped with the live timestamp. ✅ **MEASURED on the real record rather than reasoned about, and it was not a corner case — it was all of it: 2026-07-31 122 rows / 0 from that day / 81 duplicates; 08-04 217 / 0 / 171; 08-05 221 / 0 / 178.** Ages ran **6 to 75 days**. The duplicates are there because every restart re-dumps the same warm-up — **5 starts on 08-05, so every historical setup was written 5 times.** ⚠ **The damage lands on the one record nothing else holds.** No broker statement contains a trade that was REFUSED, which is why `ledger_sync.py` commits this file at all — and *"what did the bot decline today"* was answerable only by comparing each row's own `bar_time` against its `ts`, which nothing did. ⚠ **It never affected trading**: `blocks`/`misses` are reporting-only, nothing reads a record back, and the bridge is driven by the decision object. **This is an audit-trail defect, and the audit trail is the product here.** ⚠ **Discarding beats tagging**: a warm-up setup is not a decision this bot made, it is history it replayed to build state, and a backtest already reports it properly — a flag would leave every future consumer needing to know about the flag. ⚠ **The count rides on the `warmed` event (`replayed_setups`) rather than vanishing**, because a silent drop is equally how a strategy that STOPPED recording refusals would go unnoticed. ✅ 4 tests (`algos/tests/test_ledger_warmup_records.py`), **all four watched to FAIL against the pre-fix runner and pass against the fix** — a suite written after a fix and never run against the defect is a description of the fix. 277 algos tests green. ⚠ **The three ledger days already on disk still contain the 560 rows**; they are identifiable by `bar_time` being older than `ts`, and they were left rather than rewritten — quietly editing an audit log is a worse habit than a polluted one. ⚠ **The live `bar` stream itself is CLEAN** — 66 rows on 08-05, no duplicates, one 15-minute hole caused by a deliberate restart. **The standing lesson is this repo's own by a fifth route: the system recorded what it REPLAYED as though it were what it DECIDED** — the same shape as the bar cache recording the window it requested rather than the data it received, and the feed advancing its bookmark on hand-out rather than on processing. Earlier the same day: ✅ **THE LIVE BOT'S MINIMUM-STOP FLOOR IS 0.08, NOT 0.10 — CORRECTED THE SAME DAY, AND THE CORRECTION IS THE POINT.** It was shipped at `"% of price"` 0.10 hours earlier on the strength of a parity run and a doc note, and **Aaron asked what it actually cost.** Swept: 23 configs over 186,220 M15 bars (2018-09-13 → 2026-08-04), one real replay each. **0.10 costs 7 trades and 1.84R** (183 / +134.75R → 176 / +132.92R); **0.08 GAINS 2.00R** (181 / +136.75R). So the value that shipped was the wrong side of the optimum, and nothing in the parity gate could have said so — **a parity gate proves the two implementations agree about a setting, never that the setting is a good one.** Now `"% of price"` 0.08 in the instance config, the strategy default, both A+ Pine files and the instance template, promoted and restarted. ⚠ **A small floor GAINS R mechanically, not luckily: the three tightest stops in 7.9 years ($1.03 / $1.06 / $1.18) were all full −1.00R losers**, and `Fixed $` 1.25 refuses exactly those three for exactly +3.00R. Median stop distance is $8.88, so these are genuine outliers. ⚠ **Do NOT read +2R as an edge** — the jitter audit put this strategy's run-to-run spread at **sd 15.06R**, so 0.05 through 0.08 are indistinguishable; 0.08 is the HIGHEST value that does not start costing, i.e. the most protection for nothing. **A safety choice.** ⚠ **`x ATR(14)` was measured and REJECTED, against intuition** — it adapts to volatility and was cheapest on R, but at 0.35/0.40 it never refuses the $1.03 stop, because that bar was quiet and $1.03 was not tight *relative to ATR*. **The hazard is `qty = risk / stop_distance`: pure price units, volatility nowhere in it.** ⚠ **Also corrected here: `_exec_risk_pct` in the instance config still read "DECISION PENDING … harmless while the bot is in dry run".** Both halves went stale the moment the bot was armed the same day. **A comment claiming a live bot is not trading is worse than no comment**, and this file is the first thing anyone reads before touching the bot. Earlier the same day: ✅ **THE MINIMUM-STOP GUARD WAS SWITCHED ON IN THE LIVE BOT (`"% of price"` 0.10 at the time), AND IT TOOK TWO EXPORTS BECAUSE THE FIRST GATE WAS GREEN ON A BRANCH NEITHER SIDE ENTERED.** This is the last open item on the money hazard (G6/Step 1) and it is now closed. `compare_strategy.py` is **exit 0 at warmups 100 / 500 / 1000 / 2000** on a 21,899-bar `VANTAGE_XAUUSD, 15m` export taken with the guard enabled at `"% of price"` 0.30, and **block code 7 ("Stop too tight") fires 213 times in that window** — 49 long, 164 short. 🔴 **The first export was ALSO green at three warmups and proved nothing.** Its config columns read `cfg_min_stop = 2`, which is **`"Fixed $"`, not `"% of price"`** — a **ten-cent** floor on a $4,000 instrument — and **code 7 appeared ZERO times in 21,897 bars**, with the tightest filled stop at $6.76, 67× the floor in force. **The standing lesson is aimed at this repo's own gates: a green parity run says the two implementations AGREE, never that either is RIGHT — and it cannot say even that about a branch neither one entered. Before trusting a gate on a feature, check the feature was EXERCISED**, which here is a one-line block-code histogram over the export. ⚠ **Parity was proven at 0.30 and the live config ships 0.10** — same code path, same `px * val / 100` floor, same refusal, same block code, only the constant differs; say it that way rather than claiming 0.10 was itself diffed. ⚠ **It CHANGES which trades the bot takes** versus every result measured at `"Off"`, the 161-trade / +135.94R baseline included. ⚠ **It does not replace the two independent backstops** — the broker's own 20-point `SYMBOL_TRADE_STOPS_LEVEL` and `place_pending_limit`'s own refusal — but it is the only one acting on OUR side of the wire, which is where `qty = risk / stop_distance` is computed and therefore the only place a collapsed stop can be stopped from SIZING a position. Earlier the same day: 🟢 **THE BOT IS ARMED. `--live` IS IN `STARTUP_SEQUENCE`, AND THE FIRST TRADE WOULD HAVE RECORDED A P&L THAT DISAGREED WITH THE ACCOUNT BALANCE.** Aaron's call, on the $2,000 PU Prime **DEMO** account. The reason is the one dry run could not serve: **the bot ran three days and 274 bars and never armed a single setup** — every bar `long_armed`/`short_armed` false, stage never above 1, block code 7 never raised — which is not a fault, it is what **~2 trades a month** looks like over three days. Watching it decide nothing teaches nothing, and G5 (*PU Prime's spread, swap, commission and minimum stop distance are assumed, never measured*) cannot be answered by any amount of watching. ⚠ **The flag went in `STARTUP_SEQUENCE`'s argv because that tuple is the SINGLE SOURCE for all three start paths** — SYS_STARTUP at boot, the SYS_MONITOR watchdog restarting a dead bot, and the command center's Start/Restart buttons (via `--bot` single mode). Arming any one caller would mean **a watchdog restart silently returning a live bot to dry run**, which is worse than never arming it: the ledger keeps filling and nothing says the orders stopped. ⚠ **It follows that live is now this bot's DEFAULT on this box** — every automatic recovery brings it back armed, so disarming means deleting the flag and restarting, not stopping the process (the watchdog will simply undo that). 🔴 **The defect the arming exposed, found before the first order rather than after: `get_deal_result` returns MT5's `d.profit`, which is the PRICE MOVE ONLY, read off the CLOSING deal alone.** Swap was dropped entirely and commission — normally booked on the **ENTRY** deal, which that function never looks at — was never even fetched. So the very first live trade would have written a `pnl_usd` that quietly disagreed with the balance, under a field name giving no reader a reason to check. **This repo's signature defect once more: a number that is correct about a narrower question than the one being asked.** Fixed with a new `mt5_ops.get_deal_breakdown()` that sums **every deal of the position** and reports `gross_usd` / `swap_usd` / `commission_usd` / `net_usd` separately; the bridge writes all of them, and `pnl_usd` and the R are now NET, because a scratch that is +0.02R on price and negative after an overnight swap is a loss. ⚠ **The parts are kept rather than just the total, and that is the whole measurement** — a netted figure cannot be taken apart later, while gross + swap + commission can always be re-netted. ⚠ **Swap keeps MT5's OWN SIGN and is never `abs()`-ed**: gold's short swap is a real CREDIT (+26.98 points/night over the 6.5-year replay, where shorts were *paid* 2.14R while longs paid 8.55R), and the command center booked exactly that credit as a charge on 2026-08-03 with `-Math.abs(cost)` and overstated fees by 25%. **A cost field that cannot be positive cannot measure a broker that pays you.** ⚠ **`None` means the broker could not be ASKED; zero means it charged nothing** — `deals: 0` is what an unreachable terminal returns, and writing its zeros down would fabricate a measurement, which is worse than missing one because nothing downstream could tell. Same three-state rule as `mt5_link`. ⚠ **`get_deal_result` is deliberately UNCHANGED** (five callers unpack its 2-tuple) and its docstring now says the number is gross; the bridge calls the new method behind a `hasattr` so an older `mt5_ops`, or a test double, degrades to the old answer instead of raising out of an **exit** path — losing the cost breakdown is a bad day, losing the record that a trade closed is a much worse one. ⚠ **Entry fill vs intended price is repeated on the CLOSED row** even though it is already on the open one: joining the two by ticket works until a log rotation drops the open record, and a cost study that silently loses its oldest trades is worse than one that refuses to run. 16 new tests (`algos/tests/test_trade_costs.py`), weighted toward the ways a cost field is wrong while looking fine. Also fixed here: the 2026-08-05 `LOCAL_INSTANCES` → `LOCAL_ARCHIVE` rename had left `test_log_backup.py` erroring at setup on all 8 tests — **a rename that passes its own module and breaks its tests is invisible until somebody runs the suite.** 271 algos tests green. Earlier the same day: 🔴 **A BAR THAT RAISED WHILE BEING PROCESSED WAS SILENTLY DROPPED, AND EVERY MECHANISM THAT COULD HAVE CAUGHT IT WAS READING THE BOOKMARK THAT CAUSED IT.** Found by auditing the live ledger's three one-off `event` records — two turned out to be safety mechanisms working correctly (see below) and the third, a single `loop_error` on 2026-07-31, led here. `BarFeed.new_bars` advances `last_bar_time` when it HANDS THE ROWS OUT, not when the caller has finished with them, so an exception inside `_on_bar` left the bookmark past a bar the engines never saw. ✅ **Proven against the real `BarFeed`, not reasoned about: one fresh bar handed out, bookmark advanced, `gap_bars()` → 0, next `new_bars()` → empty.** 🔴 **Nothing could see it.** `gap_bars()` compares the newest broker bar against that same bookmark, so it read *up to date*; the next poll had nothing fresh to offer; and the outer handler only alerts after **TEN CONSECUTIVE** loop errors, while one lost bar is one error. **The engines are a streaming state machine, so a dropped bar is not a missing datapoint — every structure break, fib leg and gap after it is computed over a market history that never happened, for the rest of the session.** `new_bars`' own docstring says exactly that must not happen silently; the bookkeeping made it impossible to notice. ⚠ **RE-DELIVERING THE BAR IS DELIBERATELY NOT THE FIX, and this is the part to carry.** `_on_bar` steps the strategy and then mirrors its intent onto the broker, so a failure part-way through leaves the engines already advanced — replaying that bar would step them twice, which is the same desync from the other side. **Neither skipping nor retrying is safe, so the loop routes into the one recovery that is known-good and already built: the `gap > 4` branch's rebuild-and-re-warm.** ⚠ **It BREAKS out of the row loop rather than continuing** — the rows after the failure would otherwise be fed to engines already carrying the hole. ⚠ **A `bar_error` is its own ledger event, not another `loop_error`**: one is a poll that failed, the other is a data-integrity event, and an audit like this one cannot tell them apart if they share a name. The `rewarm` event now carries `after_bar_error` for the same reason — a re-warm after a 5-bar lag and one after a dropped bar look identical otherwise, and only one of them is a defect on our side. ⚠ **Alerts ONCE per outage** (the counter resets on the first clean bar) and **stops the bot after 10 unprocessable bars in a row** — a re-warm that is not fixing it will not start on the eleventh, and a bot silently processing nothing is worse than a stopped one, because the watchdog can see stopped. 14 tests (`algos/tests/test_bar_stream_holes.py`), most of them demonstrating the DROP against the real feed, because a fix for a bug nobody has reproduced is a fix for a guess. **The standing lesson is this repo's own arriving by a fourth route: the system recorded what it HANDED OUT as though it were what was PROCESSED** — the same shape as the bar cache recording the window it requested rather than the data it received, one layer up and inside the live loop. ✅ **The other two ledger events are CLOSED and were never defects.** The `config_change_refused` (2026-07-31 04:26) and `version_mismatch` (2026-08-04 01:10) are the version pin doing precisely its job — refusing to run code that was never promoted. **All three predate their own fixes, proven by commit ancestry rather than assumed**: the bot was launched from `1eaf5fd`, and the `Execution.cfg` property that would have prevented the `loop_error` landed in `5c53b0d` **13 minutes later**; the restart at 04:27 ran `7584380`, which contains it, and the identical operation then succeeded **twice** (`config_applied`, 04:30 and 04:31). The `version_mismatch` predates the frozen-`deployed/` snapshot by 38 minutes. Nothing outstanding from any of the three. **Same day, the ledger backup was fixed in a way that matters more than it reads: `ledger_sync.py` now commits to `algos/ledger_archive/`, NOT into the bot's own instance directory.** 🔴 **Committing a day into the live path BROKE `git pull` ON THE VPS** — the bot writes those files, so the box always holds its own untracked copy, and git correctly refuses to overwrite one (*"untracked working tree files would be overwritten by merge"*, pull aborted, measured). Every future pull would have needed a manual delete first, on the one machine that has to stay current for the watchdog, the dead-man's switch and the live loop. ⚠ **The rule, and `.gitignore` already stated it one paragraph up for `deployed/`: a file the VPS WRITES cannot also be a file git DELIVERS.** Two instances of one rule now; `algos/markets/fx/instances/*/ledger/` is ignored so a third cannot happen by hand. The archive MIRRORS the VPS layout (`<bot>/ledger/decisions-YYYY-MM-DD.jsonl`), so an archived file and its original differ only by the root — a hand `diff` stays trivial and the commit-msg hook's exemption pattern needed no change. ⚠ **Related and fixed the same day: the commit-msg hook had SILENTLY DISABLED this backup entirely** by classifying a `.jsonl` decision record as code and demanding a doc paragraph, so every unattended sync failed and a closed day sat on the VPS as the only copy — see the root `CLAUDE.md` → *Committing*. **A guardrail that fires on a robot's commit has no human to read its message: it does not nag, it stops the job.** Earlier: 2026-08-04 — 🟢 **THERE IS AN EXTERNAL DEAD-MAN'S SWITCH NOW (`SYS_DEADMAN`), AND IT IS THE ONLY ALERT IN THIS SUITE THAT SURVIVES THE BOX.** Every other one — the bot's own messages, `monitor.py`, the P&L tracker, the reporter — is sent BY the VPS, so the single failure nothing could report was the box or its network dying: that produces **silence**, and silence is what a healthy Sunday produces too. `notifications/deadman.py` inverts the direction. It checks each registered bot's **process, heartbeat freshness and `mt5_link`**, and pings an **off-box** service only when all of them are good; that service alerts when the pings stop. ⚠ **The ping is CONDITIONAL on health, and that is the whole design — it is the 2026-08-04 probe lesson stated from the other side.** An unconditional ping proves only that Task Scheduler is alive, so a healthy box and a bot that died an hour ago would send the identical green tick: **never trust a POSITIVE result a broken system can also produce**, exactly as you must not trust a negative one a healthy system can. ⚠ **TWO signals, because otherwise a dead bot and a dead box are the same silence**: a plain ping (missing ⇒ timeout alert, meaning *nothing on that box can talk to me*, and the far end genuinely does not know why) and **`<url>/fail` carrying the reasons** when the script runs and FINDS a fault — immediate, and named, instead of a silence you decode after the grace period. ⚠ **It restarts nothing.** `SYS_MONITOR` owns recovery; two independent things issuing starts for one bot is precisely how the duplicate below happened. ⚠ **It is a SEPARATE task from the watchdog on purpose** — the watchdog is the bigger program and the likelier to break, and a switch sharing its process shares its failure modes and stops being an independent check. ⚠ **Absence is never scored as health**: an unreadable `wmic`, an unreadable `bot_state.json` and a missing heartbeat field are each a FAILURE, not a quiet pass, and `mt5_link` is read `is False` and never falsy (`None` = UNASKED, the same three-state contract the Bots page follows). ⚠ **An UNCONFIGURED switch is a supported state** — no `deadman_url`, no send, exit 0 — because a task that fails every five minutes is one everybody learns to ignore, and then the real failure is ignored with it. ⚠ **The ping URL is a SECRET** (`deadman_url` in the git-ignored `credentials.json`; env `LWG_DEADMAN_URL`): whoever holds it can send your pings for you and hold the alert green forever, which is worse than having no switch because you would believe it. 21 tests (`algos/tests/test_deadman.py`), deliberately weighted toward the ways a check can wrongly say "fine" — **a bug in this module is silent by construction, so unlike every other watchdog here there is no user report coming.** Earlier the same day: 🔴 **`SYS_STARTUP` WAS NOT IDEMPOTENT: FIRING IT ON A HEALTHY BOX LEFT TWO COPIES OF THE TRADING BOT AND BOUNCED THE TELEGRAM BOT.** Found by RUNNING it to verify the Telegram fix below — which is the point: the Telegram half was proven and the worse half was sitting one level up, unmeasured. `startup_coordinator.py` launched every bot in `STARTUP_SEQUENCE` unconditionally, so **two `runner.py --bot mpc_sos_fade_demo` processes were left running four minutes apart with nothing anywhere reporting it.** ⚠ **Two copies of one bot is the worst duplicate in this system**: they share an account, a magic number and a strategy, so they see the same setup on the same bar and each sizes a FULL position off it — double the risk, from a state neither can see. `bridge` filters `get_open_positions()` by MAGIC, so each would find the other's position and read it as its own; `adopt_broker_state`'s HALT on an unknown position at startup is the only reason this is survivable. **Three guards, covering different paths:** the coordinator skips a bot already running on **BOTH** launch paths — full startup AND `--bot` single-bot mode, which was MISSED on the first pass and is the one the command center's Start button drives, i.e. the likeliest way anyone makes a duplicate (primary — and it avoids the false `offline` the alternative produces, since a second copy that exits immediately still starves `wait_for_connection` of its ready string), and **`runner.already_running()` refuses to be a second copy** (backstop for the command center, the watchdog, and a typed command). ⚠ **Both match on `--bot <key>`, never the script name** — every live bot IS `runner.py`, so the script identifies the FLEET and only the key identifies the bot; matching the script would stop a second, different bot from ever starting. The runner compares PIDs so it cannot mistake itself for a duplicate. ⚠ **The two guards default in OPPOSITE directions on an unreadable process list, deliberately.** The coordinator assumes RUNNING and leaves it alone (a duplicate bot is two positions); the runner assumes NOT running and starts ("cannot tell" must not become "refuse forever" for the process whose absence is silent). ✅ **Verified live: the task was fired again with both fixes in place and the box was unchanged — one bot (PID 8892), one Telegram (PID 12780), no new processes.** 208 algos tests green (6 new). **The standing lesson: a start command that is not idempotent is a duplicate generator, and every recovery path in this suite fires one.** Earlier the same day: 🔴 **THE TELEGRAM BOT WAS NEVER CRASHING. IT WAS BEING KILLED, AND ONE OF THE KILLERS WAS OUR OWN STARTUP SEQUENCE.** Aaron had watched it stop and come back for weeks and asked why. ✅ **Measured, not guessed: 4,764 Windows Application events over 14 days, none mentioning python, and no crash event (1000/1001/1026) since 26 July.** A `taskkill /f` leaves no event behind and a real fault does, so every "stop" was an external kill. Four kill paths, three fixed the day before without anyone realising they answered this question: the Telegram bot's own `/emergency` ran `taskkill /f /im python.exe` and **killed itself** (which is also why its confirmation reply never arrived), the command center's Stop button did the same, and three docs instructed the blanket kill by hand. **The fourth was the routine one and it was BY DESIGN:** `startup_coordinator.py` ended by launching `start_telegram.py` unconditionally, and that script's first act is `kill_existing()` — force-kill any running telegram_bot.py, sleep 2, start fresh. So **every Start/Restart from the Bots page, and every documented bot restart, killed the alert channel and rebuilt it**, after which SYS_MONITOR spotted the gap and sent 🟢 *Telegram Bot Restarted*. Fixed: `start_telegram_if_needed()` leaves a healthy Telegram alone. ⚠ **`SYS_TELEGRAM` deliberately KEEPS the force-restart** — that task exists to recover a bot that is alive but WEDGED, and it is what the watchdog fires (×3) when Telegram is genuinely down; the skip is about collateral damage from starting something else, and a test pins that `kill_existing` survives. ⚠ **An unreadable process list starts one rather than assuming it is up** — the safe direction is not symmetric: a second Telegram is refused by `telegram_bot.py`'s own singleton guard, a missing one is silence. ⚠ **The tests exec the launcher's real functions out of its AST** rather than importing it, because `startup_coordinator.py` hardcodes `C:/trading/algos` at module scope — the same trick `_coordinator_sequence` already used, so the check runs on the Mac where the mistake is actually made. 4 new tests, 202 algos tests green. **The standing lesson: an alert channel that cries wolf stops being read, so a routine event dressed as a failure costs exactly as much trust as a missed one — and "why does this keep restarting" deserves a measurement, not a shrug.** ⚠ **One blanket kill is still on disk on purpose**: `command-center/backend/tests/test_integration.py` runs `taskkill /f /im python.exe` on the VPS. It is excluded from every normal test run and documented in three places, but a bare `pytest tests/` still takes out the box. Earlier the same day: 🔴 **METATRADER RESTARTED ITSELF UNDER THE LIVE BOT AND THE BOT WENT BLIND FOR 50 MINUTES WITHOUT ONE INDICATOR CHANGING.** `C:\MT5_FFT\terminal64.exe` was rewritten at 02:57:53 UTC by an auto-update and the replacement process started two seconds later, taking the running bot's IPC handle with it. From the 02:30 bar onward it saw no market at all — across an open session, in which it would have taken no entry and managed no exit. ✅ **Proven rather than inferred: a separate read-only probe attached to the same terminal and got balance $2,000, live ticks at 4056.77 and fresh M15 bars, while the bot's own process was getting `None` from every call.** The terminal was healthy; only the bot's link was dead. 🔴 **The reason nothing caught it is the transferable part, and it is NOT this repo's usual label-vs-code refrain: every failure on the MT5 path returns an ABSENCE rather than raising.** `copy_rates_from_pos` → None → `get_candles` returns an empty frame (documented "never None", which is right for its callers and fatal here) → `BarFeed.new_bars` reads *no bar has closed* and `gap_bars` reads *no gap*; `account_info` → None → the heartbeat wrote a null balance. So the loop kept stamping, **SYS_MONITOR saw a healthy bot**, `wmic` still listed the process, the **Bots page said RUNNING**, and the log carried not one warning. **The only visible symptom in the entire system was a blank balance cell** — which is how it was found, by Aaron asking why. **Fixed:** `runner.probe_link()` asks `account_info()` FIRST, every poll; `_recover_link()` logs, alerts ONCE, retries on a 30s floor, and on reconnect **RE-WARMS** — an outage is a hole in the bar stream, i.e. the `gap_bars() > 4` condition arriving by another route, and resuming on the next bar would leave the engines carrying a market history that never happened. ⚠ **A bar-based probe cannot do this job and would have looked reasonable**: an empty frame is also what a QUIET MARKET produces, so such a check either cries wolf out of hours or treats a dead link as a quiet market forever — which is exactly how it shipped. `account_info()` answers whenever the link is alive, 3am Sunday or mid-session, so `None` means one thing. ⚠ **It deliberately does not reason about an open position** — if the broker holds one the rebuilt emulator does not, `OrderBridge._agrees` HALTS on the next bar, which is correct and already built; a second, less-tested answer to that question is how a restart doubles a book. ⚠ **`bot_state.json` gained `mt5_link` because a null balance is not a diagnosis**, and the Bots page renders it as a `No MT5 link` chip BESIDE the Running pill rather than replacing it: the process being ALIVE and being BLIND are both true and are different facts (alive ⇒ a restart is the fix and the watchdog was right not to fire). ⚠ **The heartbeat is still stamped while blind, on purpose** — dropping it would fire the stall alert, which means something else entirely. 12 new tests (`algos/tests/test_mt5_link.py`), 198 algos tests green; deployed and verified live (`mt5_link: true`, balance $2,000, bars current). **The standing lesson: before trusting a probe, ask whether a HEALTHY system can produce its negative result. If it can, it is not a probe.** Every layer here was individually defensible; the defect was that "no data" and "cannot ask" were the same value at every hop, so the distinction was destroyed at the bottom and unrecoverable above it. ✅ **CLOSED 2026-08-04 by `SYS_DEADMAN`** — see the header entry above. Earlier: 2026-08-02 — **no algos code changed; two cross-subsystem facts were recorded.** The MT5 agent's **`/status` is now a CONSUMED CONTRACT** — the command center reads `mt5_connected`/`account`/`server` from it to drive its MT5 health dot, because `/health` answers `ok` while the terminal is closed or logged out — and **both `MT5AgentRDP` and `NT8Agent` are now fired automatically** by a 60s supervisor loop on the Mac, which also re-probes after every `schtasks /run` (that command reports SUCCESS for a task Windows refuses to launch — the stored-password trap below). Both are written up under *Backtest data source*. Earlier: 2026-07-30 — **`algos/live/` landed: the live runtime for a `strategies/python/` bot on a named MT5 terminal** (see the section below and `docs/LIVE_TRADING_PIPELINE.md`), and `shared/mt5_ops.py` gained what it needs to drive one — pending/resting LIMIT orders (it could only send market orders, and the MPC strategies enter on a limit) plus the broker-clock fix on `get_candles`, which was labelling broker-server seconds as UTC and would have put every bar 2-3 hours out with a perfectly valid-looking timestamp. Also **credentials moved out of git.** The Telegram token was pasted into six files and committed; it has been revoked, and every copy is replaced by `shared/credentials.py`, which resolves env var → the git-ignored `algos/credentials.json` → empty. `credentials.template.json` (in git, values blank) is the setup path. Missing credentials are a no-op with one warning, never an exception. This is step 2 of `docs/LIVE_TRADING_PIPELINE.md`, the plan to take a validated `strategies/python/` bot to real orders on a named MT5 terminal — read it before touching anything under `bots/`, `shared/` or `notifications/`, because the pieces preserved from the deleted suite are about to get their first real consumer.

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
| `mt5_ops.py` | `shared/` | All MT5 operations — symbol-parameterized, single shared instance per bot. `symbol_spec()` / `margin_for()` / `free_margin()` are what `order_sizing` reads; each returns `None` rather than a guess, and a `None` is a REFUSAL at the caller |
| `account_risk.py` | `shared/` | **The one place the WHOLE ACCOUNT's open risk is totalled.** `order_sizing` answers *how big is this order*; this answers *how much is already on*, across every bot and every hand trade. Pure — no MT5, no I/O. Reads the BROKER as truth (via `mt5_ops.account_exposure()`), because every alternative needs the bots to trust each other and a crashed bot leaves a stale reservation. Risk is measured to each position's **CURRENT** stop, so a stop at breakeven frees its room. **A position with no stop REFUSES rather than scoring zero** — its risk is unbounded, not absent. **It refuses; it never shrinks**, and the docstring records why that differs from `backtest/portfolio/`, which does |
| `order_sizing.py` | `shared/` | **The one place a broker lot count is produced.** Pure, no MT5, no I/O: takes the strategy's intent + a `SymbolSpec` and returns a `SizedOrder` or a `SizingRefusal`. Instrument-agnostic — lots come from `(stop_distance / tick_size) x tick_value`, so gold, a JPY pair and an index are one arithmetic. **It refuses rather than rounding up, clamping down, or shrinking to fit.** Built after the 2026-08-07 oversizing incident; read its module docstring before touching sizing anywhere |
| `bot_state.py` | `shared/` | Single source of truth read/write for each instance's `bot_state.json` |
| `credentials.py` | `shared/` | **The one place secrets are resolved.** Env var → git-ignored `algos/credentials.json` → empty. Never holds a literal. Copy `algos/credentials.template.json` to set a machine up. **Any key resolves, not just the canonical three** — a per-bot secret needs a new entry in that file and nothing else; the env name is always `LWG_<KEY IN CAPS>` (`env_name()`). |
| `notify.py` | `shared/` | Telegram sender. `send_telegram(text, kind, chat_id="", token_key="")` — **`kind` is `TRADE` or `HEALTH` and is REQUIRED**; it picks the room (see `### Two rooms` below). `chat_id`/`token_key` are optional and empty = the shared destination for that kind and the shared bot, so routing is PER BOT without a second sender. Reads `credentials.py`, never a hardcoded token, and NEVER raises — an unconfigured or unreachable notifier drops the message and prints once, because a notification channel must not be able to stop a trading loop. The four `notifications/` scripts now import their credentials from the same resolver instead of carrying inline copies (the 2026-07-06 refactor note, done 2026-07-30). |
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
demo is a Standard account and the raw tiers refuse rather than borrowing it. **Do not quote the
$0.33 above as current**; it is kept because the paragraph is a dated record of that day's reading.
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
unless the two are split.

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
