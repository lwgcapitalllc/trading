# Notes — Portfolio stacking and the venue ceiling

backtest/portfolio/ — the shared-account run, the loss-recovery leg, the entry-floor epsilon, the venue lot ceiling clamp, and the tools for judging whether a second leg is worth having. Moved VERBATIM out of `backtest/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Portfolio stacking (`backtest/portfolio/`)

Stack several strategies onto ONE shared account — one balance, one live risk budget the legs
compete for. Design + plan: `command-center/docs/PORTFOLIO_STACKING*.md`. Pure, offline, app-agnostic
(same discipline as `output.py`). Phase 0 + Phase 1 built 2026-07-17; lab wiring (Phase 2+) is future.

- **`combine.py`** — the cheap SCREEN. `combine_runs(legs)` adds up finished STANDALONE runs (their
  stored `daily_pnl`): combined curve, daily-return correlation, diversification drawdown, per-leg
  contribution. Idealized UPPER BOUND — it assumes every leg trades a full account and never gets
  blocked, so it OVERSTATES the stack. A candidate screen, not the demo result.
- **`account.py`** — `PortfolioAccount` (the broker): one balance; open trades RESERVE risk measured
  to their CURRENT stop (→ 0 at breakeven, freeing room); cap = % of live balance; `request_fill`
  **scales the leg's own desired qty** to the room (shrink-to-floor) — it never re-derives the qty,
  which is what preserves strategy parity (the bot sized off the limit price at placement).
  `request_fills` batch-splits same-bar ties by weight. `book_pnl`/`close_position` (or `on_close`),
  `update_stop`, a `contention` log stamped with `now`. **`SoloAccount`** = one leg, an infinite RISK
  budget (`room()` is `inf`), so contention never binds and the desired size is granted whole.
  ⚠ **It is NOT capless** — it still carries the VENUE ceiling (`max_lots`, default 100), which
  sits outside the budget and binds on a solo run, so it is not a pure passthrough and the
  parity anchor needs `max_lots=None` passed explicitly. See *the VENUE CEILING* below.
- **`clock.py`** — `merge_streams`: k-way merge of the legs' bar streams into time-ordered `Tick`s,
  co-timed bars grouped, stable leg order.
- **`simulator.py`** — `simulate(legs, account)`: steps the legs on the clock, orders
  **holders-before-flat legs** each tick so freed room is released before entries (release-before-entry
  without splitting the strategy's monolithic step), returns combined + per-leg trades + contention log.
  **v1 limit:** two flat legs filling on the EXACT same tick are first-come, not split-by-weight (the
  weighted split needs the strategy step split into decide/commit; `request_fills` is ready for it).
  **Optional `progress(tick_index)` / `should_cancel()` (2026-08-09)**, polled every `_CHECK_EVERY`
  (512) ticks, for a caller driving this from a UI — the lab does. ⚠ **A cancelled result is
  PARTIAL and says so (`cancelled=True`)**: it holds every trade closed up to the tick it stopped
  on, which reads exactly like a complete short backtest, so a caller must branch on the FLAG
  rather than on the trade list and must never persist a partial book as a finished one.

- **`legs.py`** — `StrategyLeg` / `build_leg`: one real `strategies/python/` bot wrapped as a leg
  the simulator can drive (an `EngineStack` plus the strategy, stepped exactly the way
  `optimizer._replay_one` steps it). **Each leg owns its own stack**, which is not an optimisation
  to remove: the two bots pin different engine inputs (`b_leg` forces `eq_exempt_fvg` off where
  SOS Fade forces it on), so one shared stack would replay at least one of them against a market it never
  saw. It uses `stack_config()`, never `engine_config()` — the second is the static Pine constants
  and a config whose POI source is order blocks needs the OB engine switched on. `exec_secondary`
  is **REFUSED when the leg was handed only ONE frame**, the same call `run_sweep` makes: replaying
  it single-stream returns a primary-only book that is then compared against controls that have the
  re-entries in them. ✅ **Since 2026-09-02 a leg may instead be GIVEN its second frame**
  (`LegSpec.df_fast`) and then it runs whole — `DualFeedLeg`, below. The refusal is now about a
  MISSING frame rather than about stacking, and it names the way out.

- 🔴 **`DualFeedLeg` — a leg on TWO bar frames (2026-09-02).** SOS Fade's re-entry fills on a faster clock
  than its primary, so pinning that switch off was pinning off a third of the bot's trades:
  MEASURED 2020-01-01 → 2026-08-23 on PU Prime `XAUUSD.p` with ECN costs charged, the SOS Fade leg goes
  158 → **235 trades, +183.04R** when it is given its fast frame. **A stack that cannot run the
  shipped config is not measuring the bot you own.**
  ⚠ **Defaults `None`, so NO documented baseline moves** — with no fast frame the build, the solo
  controls and the simulate call are unchanged, and every stored stack replays byte-identically.
  🔴 **The merge is NOT reimplemented — `DualClock` on the strategy owns it**, and it is the same
  object the live runner drives bar-at-a-time, so a stacked leg and the live bot order their two
  streams by ONE rule. A second copy of *which bar steps when* is exactly the duplication this repo
  keeps paying for.
  ⚠ **The bar carries WHICH FRAME it came from (`FeedBar.fast`) because the TIMESTAMP cannot answer
  it.** A 15m bar and a 5m bar share an open time four times an hour, and that is precisely the pair
  that has to be routed differently.
  ⚠ **PRIMARY FIRST at an equal timestamp, and the ordering is the contract.** A fast bar is stepped
  against the last CLOSED primary context, and the fast step flushes the primaries that closed by its
  open — so a primary must be queued before the fast bar sharing its open time, or the flush finds
  nothing.
  ⚠ **`bar_ms` is the PRIMARY's duration, never the merged stream's minimum gap.** The swap clock and
  the time stop are counted in primary bars; reading it off the merged stream puts both on the fast
  frame and silently shortens every hold.
  ⚠ **The TAIL has to be drained.** The last primary bars close after the final fast bar, so nothing
  flushes them; `simulate` calls `finish()` after the loop on any leg that has one, and **only when
  the run was not cancelled** — a partial book must not gain bars a complete one would have. Without
  it the leg drops its last bars, and a book that stops early looks exactly like a book that found no
  more setups.
  ⚠ **`df_fast` must cover the SAME window as the primary.** A fast frame that starts later produces
  no re-entries over the part it does not reach — a smaller book that reads exactly like a rule that
  found fewer setups.
  8 tests in `tests/test_dual_feed_leg.py`, each watched RED by its own mutation.
- **`runner.py`** — `run_stack(specs, balance=, risk_cap_pct=)`: build the account, build the legs,
  simulate, **and replay each leg SOLO on the same bars**. The solo control is not a convenience —
  without it a difference in the shared book is a mixture of *the cap bit* and *the shared balance
  re-sized everything*, and nothing afterwards separates them. Refuses two legs sharing a NAME:
  the account keys an open position by leg name, so a duplicate silently overwrites a live
  reservation and the cap under-counts the open risk while reporting itself enforced.
  ⚠ **A cancelled run SKIPS the solo controls** (2026-08-09), and that is the load-bearing half of
  the cancel path: a control's whole job is to be comparable to the shared book, and a control
  over the FULL history beside a book that stopped a year in is not a control — it is two
  different experiments in one table, and the screen-vs-shared delta would read the missing year
  as the cap's doing.
  ⚠ **`df_fast` reaches the SOLO CONTROL and the private source copy too, not only the shared
  build.** A control replayed without the fast frame holds a different set of trades from the leg it
  is the control for, and the screen-vs-shared delta would then report the missing re-entries as the
  cap's doing — the same failure the cancelled-run rule above exists to prevent.
- 🔴 **`LegSpec.source` — a leg may READ ANOTHER LEG'S CLOSED TRADES (2026-08-21).** The mechanism
  the loss-recovery rule needs: it has no setups of its own and arms off a primary's losses, so it
  cannot be an ordinary leg. `source` names another leg in the same stack; `run_stack` builds
  sources first, hands the dependent that leg's **live trade list object**, and gives it the
  frame's last bar and bars-per-day for its time stop. **Defaults `None`, so every stored stack is
  byte-identical** — with no sources the build order, the solo controls and the simulate call are
  all unchanged.
  🔴 **The list must be the OBJECT, not a copy, and that is the whole failure mode.** The dependent
  arms when a source trade CLOSES, so it reads a list that grows under it during the replay. A copy
  taken at build time is empty forever and the leg returns an empty book — **indistinguishable from
  a rule that genuinely found no setups.** Pinned by
  `test_the_dependent_is_handed_the_LIVE_trade_list_not_a_copy`, watched RED by `list(...)`.
  🔴 **A sourced leg's SOLO CONTROL gets a PRIVATE copy of its source**, on its own account, so only
  the measured leg books onto the control's balance. A sourced leg alone has nothing to recover, and
  an empty control makes the shared result look like the whole of the leg's worth rather than the
  part that survived the competition. ⚠ **The private source's trades are discarded on purpose** —
  it exists to lose, and reporting it would put a second copy of the source's book in the run.
  ⚠ **Three refusals, each with a silent failure behind it**: a source not in the stack (the
  dependent reads nothing), a leg sourcing itself, and a CHAIN — chains are refused rather than
  supported because the moment they are legal so are cycles, and a cycle here builds forever rather
  than raising. ⚠ **A leg handed a source that does not implement the contract is refused**, or the
  source is dropped in silence.
  ⚠ **`bars_per_day` is read off the leg's own `execution.bar_ms`**, which `StrategyLeg.__init__`
  has already measured — two readings of one fact are how they come to disagree.
  **Where this is going:** `docs/RECOVERY_LEG_IN_COMMAND_CENTER.md`. 10 tests in
  `tests/test_stack_runner.py`, 4 mutations each reddening exactly its own case.
- 🔴 **`legs.py` REFUSES a leg whose `exec_recovery` is on, and the reason is that it does NOTHING
  here (2026-08-21).** That switch runs from a `finalize(df)` hook the simulator never calls — it
  steps bars and never drives `run()` — so the leg came back with its recovery trades **silently
  missing**. No error, no empty list to notice, just a smaller book than the same settings produce
  anywhere else, reaching a comparison table looking ordinary. It joins `exec_secondary` at the same
  seam, for the same class of reason. ⚠ **No stored stack moves** — checked, not assumed: 0 of the
  6 stored stack leg runs had it on. ⚠ **The recovery belongs in a stack as its own LEG**, which is
  the version that competes for the budget; the switch cannot compete by construction, because it
  reads a book that has already finished.
- **`tools/stack_run.py`** — the CLI. Prints the shared book beside the solo controls, what the
  account CARRIED, and the contention log. ⚠ **It builds each leg from that strategy's CONFIG
  DEFAULTS**, so anything a leg does not declare it does not get: only fields a config actually
  has are passed (`LAB_STRATEGY` is an open contract — `extreme_leg` has no fill-model field
  at all), which is the same rule `overlap_audit.py` follows.

  🔴 **IT GAINED PER-LEG BAR FRAMES ON 2026-09-02, AND THE SIMULATOR HAD SUPPORTED THEM ALL ALONG.**
  `--legs sos_fade:15,extreme_leg:5` runs each leg on its own frame; bare `--legs` still
  uses `--tf` for all of them. The merged clock was built for this from the start — *"a 5m leg
  simply steps three times inside a 15m leg's bar"* — so the single-frame limit was **the CLI's
  alone**, and it made a mixed stack look impossible when it was one flag away.

  🔴 **THE DEFAULT START IS NOW THE LATEST FLOOR ACROSS THE FRAMES, NEVER EACH FRAME'S OWN.** The
  legs share one balance, so giving a 15m leg history the 5m leg does not have lets it compound
  ALONE before the other exists, and every later trade of BOTH is then sized off a balance one
  built unopposed. The run would not error — it would answer a different question, and nothing in
  the output would say which. The common window is printed when the floors differ.

  🔴 **PER-TRADE RISK IS A BASIS FIELD AND IT WAS PRINTED NOWHERE UNTIL 2026-09-02.** The first
  mixed stack ran `sos_fade` at 10% against `extreme_leg` at 1% — a 10:1 asymmetry that
  came from the two config defaults and that nobody chose. **The bigger leg fills the budget on
  its own and the smaller one reads as harmless, which is a fact about the SETTINGS rather than
  about the strategies.** It is a column in the leg table now, and `--risk-pct` forces every leg
  onto one basis. ⚠ **This is rule 11 in the place it is easiest to miss**: the two runs differ in
  what they are measured on, and both look like "the stack".

  ⚠ **`--server` was added for the same reason `overlap_audit.py` has one** — without it the bar
  source asks whichever terminal is attached, so a re-run with the app down fails at the fetch,
  and two brokers' gold histories differ in LENGTH, so a re-run on the wrong cache disagrees with
  every figure while looking perfectly healthy.

  ⚠ **A SHRUNK ENTRY IS INVISIBLE IN R.** R is measured against each trade's own risk, so a trade
  cut to half size reports the same R it would have at full size. On the 2026-09-02 mixed stack the
  SOS Fade leg's shared and solo R were identical despite one shrink. Rule 6 says compare R rather than
  dollars, and **this is the one place R cannot see what the cap did** — read the contention log.
- **The LAB drives the same object** (`command-center/backend/services/portfolio_runner.py`,
  2026-08-09) — it CALLS `run_stack` and owns no account model of its own. ⚠ **Anything tuned here
  is the rule the live allocator has to enforce**, or the stacked backtest stops predicting the
  stacked account.

### The shared-account run — MEASURED 2026-08-09

```
python backtest/tools/stack_run.py --start 2020-01-01 --end 2026-08-06 --balance 10000 --risk-cap 10
```

**155,807 M15 bars, SOS Fade and B-LEG on one $10,000 account, cap 10% of the live balance:**

| leg | shared trades | shared R | solo trades | solo R | solo closing |
|---|---|---|---|---|---|
| `sos_fade` | 159 | +142.18 | 159 | +142.18 | $54,683,172 |
| `b_leg` | 99 | +17.87 | 99 | +17.87 | $31,064 |
| **shared account** | **258** | **+160.04** | | | **$204,918,789** |

✅ **The seam is proven NEUTRAL, which is the whole point of the first run**: every leg posts the
SAME R shared as solo, because R is normalised to the trade's own risk and nothing was refused.
The shared account changed the DOLLARS — one balance compounding both legs — and moved no decision.
SOS Fade also reproduces its documented 159 / +142.18R baseline to the cent, which is the cross-check
that this drives the real strategies and not a third thing.

🔴 **AND NOTHING WAS EVER BLOCKED IN 6.5 YEARS, WHICH IS THE FINDING.** Peak open risk touched
**exactly 10.00%** — the cap — with **2 of 2 legs holding at once**, and the contention log is
EMPTY. The reason is the reservation model and it is the part worth carrying: **open risk is
measured to each trade's CURRENT stop, so a stop moved to breakeven releases its room**, and
`sos_fade` touches breakeven on 161 of 161 trades at a median of ONE BAR (measured 2026-08-06).
So by the time the second leg wants in, the first is reserving nothing. ⚠ **Read that as "the
allocator would rarely have had anything to arbitrate", never as "a cap is unnecessary"** — it is
the overlap audit's shared-bars result arriving through the budget (27 when this was written,
**45 with ZERO same-side at the 2026-09-01 re-run** — `docs/LIVE_TRADING_PIPELINE.md` → G14), and
the window where two bots really do carry 2× risk is the bar before the stop stages.

⚠ **A cap BELOW a leg's own risk % does not arbitrate, it re-sizes.** At `--risk-cap 5` against two
bots each risking 10%, all 258 entries are shrunk and NONE is blocked — every position is halved,
R is unchanged (it is normalised) and the closing balance falls $204.9M → $4.7M. That is the
shrink-to-fit design working, and it is a different lever from the one Aaron asked for; **blocking
only happens when a leg asks while the budget is genuinely full.**

🔴 **THE CONTENTION RULE IS NOW A CHOICE, AND IT IS STATED RATHER THAN IMPLIED.**
`PortfolioAccount(all_or_nothing=...)`. **False (default) = shrink-to-fit**, the behaviour every
stored run used. **True = *risk is never layered***: an entry that cannot be granted in FULL is
refused outright and the budget stays with whoever already holds it. ⚠ **Both obey the cap** — the
rule decides WHICH TRADE you end up in, never how much is at risk. ⚠ **It defaults OFF on purpose**;
a default that changed it would re-write every recorded run rather than add an option.

⚠ **It is deliberately NOT an entry floor, and the floor route was tried and abandoned.** A floor is
ONE number for the whole account while legs risk different amounts, so any floor high enough to make
a 10% leg all-or-nothing also bans a 2.5% leg outright whatever the room — MEASURED at **64 refusals
and 0 trades**, identical at a 10% and a 12.5% cap, which reads like an allocator verdict and is a
size ban. Asking the account *"was this granted in full?"* needs no per-leg number and holds for any
number of legs. ⚠ It rides on `_is_shrunk`, so it inherits that method's tolerance ON PURPOSE — a leg
whose own risk equals the cap misses by a float's last bit, and without it the rule would refuse
every uncontested entry.

🔴 **MEASURED, and the result is the argument for building PRIORITY next.** 186,910 M15 bars,
`puprime_ecn`, SOS Fade 10% under a 10% cap with the loss-recovery leg (`recovery_stack.py
--on-contention refuse`): **176 SOS Fade entries refused, 0 shrunk, SOS Fade 127.11R → 85.05R, and the account
ends $13.2M → $1.0M (−92%) with drawdown 50.2% → 55.2%.** The cause is structural rather than a
tuning miss: **SOS Fade risks the cap in full, so it needs the ENTIRE budget to trade at all, and the
moment the other leg holds anything SOS Fade is refused.** A leg worth **$14,025 standalone over eight
years** locks out the one carrying the return. ⚠ **The account has no notion of leg PRECEDENCE** —
whoever asks first takes the budget and the legs are treated as equals, which they are not. **Do not
enable this rule on a real comparison until precedence exists.**

🔴 **LEG PRECEDENCE, and it is what makes `all_or_nothing` usable at all.**
`PortfolioAccount(leg_priority=..., leg_risk_pct=...)` — lower rank number = higher precedence.
**It cannot be "the better leg wins the clash"**: by the time the priority leg asks, the other one
is already holding the budget, and the only way to take it back is closing a live trade. So
precedence acts BEFORE the clash — **a priority leg's declared risk stays RESERVED while it is
FLAT**, and lower legs get only what is genuinely spare (`room_for`, `_headroom_for`).
⚠ **A priority leg that is already HOLDING does not also get headroom** — its real reservation is
in `reserved()` and counting it twice would halve the room; that double count is pinned by test.
⚠ **A same-bar tie is settled BY RANK, not proportionally**, or a junior leg dilutes the one it
defers to on the one bar they arrive together. ⚠ **Both default empty**, so every stored run is
untouched.

🔴 **MEASURED, same window and tier, and it flips the verdict on the whole rule:**

| cap | precedence | SOS Fade | recovery | combined | maxDD |
|---|---|---|---|---|---|
| 10% | none | 85.05R, 176 refused | 60 trades | **$1,043,054** | 55.2% |
| 10% | SOS Fade first | **127.11R, 0 refused** | **0 trades, 65 refused** | $13,199,534 | 50.2% |
| 12.5% | SOS Fade first | 127.11R, 0 refused | 60 trades, 0 refused | **$17,074,731 (+29.4%)** | 50.4% |

**At a 10% cap with SOS Fade risking 10% there is NO spare room, so a deferring leg never trades — and
that is the honest answer to "is the recovery worth taking room off SOS Fade", not a bug to soften.**
The rule only earns its place given headroom of its OWN. ⚠ **And the gain is +14.77R against SOS Fade's
own ~15R jitter floor, so the COMBINED improvement is not distinguishable from noise on this
history** — the recovery leg's own 60-trade book having positive expectancy is a separate and
weaker claim. ⚠ Dollar columns rank runs against each other and are NOT a forecast: the largest
position in these runs is 1,821 lots and the lab models no broker maximum.

⚠ **Neither contention rule touches the peak open risk, and that was checked rather than assumed.**
The peak is set by the balance FALLING under a reservation already granted — overnight financing is
the big one — not by contention. MEASURED: **SOS Fade alone with no second leg in the run reproduces the
identical 2,984 over-cap ticks and the identical 10.9140% peak.** See
`docs/CARRY_COST_AND_THE_DAILY_RISK_RESET.md`.

⚠ **This is the BACKTEST side. The live side is unbuilt** (`docs/LIVE_TRADING_PIPELINE.md` → G10)
and cannot reuse this object — live bots are separate OS processes, so the live allocator has to
read the broker's real exposure across magic numbers. **Whatever rule is tuned here has to be the
rule it enforces, or the stacked backtest stops predicting the stacked account.**

🔴 **The run found a defect in the contention log on its first pass and it is the useful kind.**
Before `_GRANT_EPS`, that same 6.5-year run logged **11 contention events totalling $0.00 of
refused risk** — every one float noise. `granted = min(desired, cap − reserved)`, and a leg derives
its qty by DIVIDING by the stop distance while the account re-MULTIPLIES by it, so an entry that
exactly fills the cap disagrees in the last bit and reads as a shrink. **A log that reports
contention where none occurred is worse than a quiet one**: downstream it puts "this trade was
shrunk" markers on a chart for trades granted in full, and it hides the real events among the
noise. Fixed with a RELATIVE 1e-9 tolerance on the shrink TEST only — the granted qty is still
scaled exactly — and pinned by two tests at the seam (one ULP short is not contention; a
thousandth of a percent still is), each watched red against its own mutation. ⚠ **The first
attempt at that test was VACUOUS and passed against the bug**, because the numbers it chose
(10,000 × 0.10 = 1,000.0) are exact in binary — which is why it now tests the rule rather than
trying to synthesise a balance that happens to round.

`account.sample_exposure()` was added in the same pass and is sampled once per tick by the
simulator, because **the contention log answers "was anything refused" and cannot answer "what did
the account carry"** — a reservation is recomputed from live stops and leaves no trace once they
advance, so a book holding two full positions all day can log nothing at all.

The strategy seam lives in the strategy (`sos_fade/execution.py` takes an injected `account`,
default `SoloAccount`; both strategy constructors thread `account` / `leg` through as of
2026-08-09) — see that package's CLAUDE.md. `compare_strategy.py` staying exit 0 with the
SoloAccount is the gate that the seam didn't move standalone behaviour.

⚠ **`build_strategy` REFUSES a strategy that cannot accept the account**, and for a sharper reason
than the `cost_profile` refusal it sits beside: a dropped cost profile under-charges a run, while
a dropped ACCOUNT sends the leg back to its own `SoloAccount`, whose RISK budget is **infinite**,
so nothing about the shared cap binds it. (The venue ceiling is the one limit it still carries,
and that is not a risk gate — see *the VENUE CEILING* below.) The run would then report a capped, shared portfolio while that leg sized
off the whole balance and contended with nobody — a risk cap claimed on screen and enforced nowhere.

## `tools/recovery_stack.py` — the loss-recovery rule as a LEG of a shared account (2026-08-20)

Runs `sos_fade` and `strategies/python/loss_recovery/` through `backtest/portfolio/` — one
balance both size against, one budget they compete for, one merged clock, one refusal log. It
exists because the lab's own `exec_recovery` toggle is a POST-PASS: the recovery sizes off the
running balance and the primary never sizes off the recovery, so recovery profit sits BESIDE the
curve instead of lifting it. Identical trades, **+3.8% that way against +44.8% on one compounding
balance**. The toggle is not wrong to be built that way — it is what stops a lab switch moving a
parity-gated SOS Fade trade — but **it cannot answer "what would this have done on my account", and a
run made with it must not be read as if it did.**

🔴 **The answer is decided by HEADROOM, not by the rule.** SOS Fade risks 10% and the default cap is 10%,
so the two legs at full size want 12.5% of a 10% budget and every overlap shrinks SOS Fade by
construction. MEASURED over 186,910 M15 bars at `puprime_ecn`: **−29.9% at a 10% cap (25 SOS Fade entries
shrunk), +29.4% at 12.5%.** `--aplus-risk-pct` and `--risk-cap-pct` are the levers; the tool prints
a warning when the two legs cannot both fit.

⚠ **The sweep that actually answers the question holds TOTAL risk fixed and moves the SPLIT**, and
its table lives in `strategies/python/loss_recovery/CLAUDE.md` rather than here. One result from it
belongs with the tool though: **the per-cell "+X% against its own control" line this tool prints is
NOT comparable across cells** — it rose +11.5% → +50.5% across four splits purely because the solo
control it divides by was shrinking, so the best-looking uplift in the sweep sat on the worst plan
in it. Read the absolute balances, or read pairs where one plan beats another on BOTH axes.

⚠ **`--on-contention refuse` REFUSES TO RUN.** `entry_floor_pct` is ONE number for the whole
account and these legs risk different amounts, so any floor making SOS Fade all-or-nothing also bans
every 2.5% recovery entry — 64 refusals, 0 trades, the same output at two different caps. A real
refusal rule needs a PER-LEG floor. Never let *cannot express this* and *here are the numbers for
it* be the same output.

⚠ **It prints total R per leg, shared vs solo, and that check is the point.** R is normalised to
each trade's own risk, so a pure sizing change must leave it byte-identical — a difference is
either the cap biting (and then it is in the refusal log) or a decision moved. It has already
found one: SOS Fade shifts −0.10R on the shrink path, unexplained, 0.08% of the book and far under the
15.06R jitter floor. Written down rather than rounded away.

## `portfolio/account.py` — the entry floor carries `_GRANT_EPS` (2026-08-20)

🔴 **The floor test was a bare `<` while the shrink test beside it had a tolerance, and setting a
floor equal to a leg's own risk % is what exposed it.** That is the natural way to express *risk is
never layered* — refuse anything the budget would shrink — and it puts `granted` and `floor` on
exactly the same number, reached by different arithmetic (a leg DIVIDES by the stop distance to get
a qty, the account re-MULTIPLIES). They differ in the last bit, so an entry nothing was competing
for was refused. **MEASURED: SOS Fade at 10% under a 10% cap with a 10% floor was refused 3,650 times
over 7.9 years and took 31 trades instead of 181** — a book that reads like a savage allocator and
is a rounding error. ⚠ **No stored run moves**: `entry_floor_pct` defaults to 0.0 and both forms
answer identically at zero. Two tests at the boundary, both watched RED by their own mutation.

## `portfolio/account.py` — the VENUE CEILING, and why a clamp is allowed here (2026-09-02)

**`max_lots` is the largest position any leg may hold, in lots, defaulting to 100 for every
strategy.** An entry asking for more is RESIZED down to it rather than refused. Aaron's call:
a strategy asking for more lots than the venue takes should trade the maximum, not skip the setup.

🔴 **It is the one gate here that is NOT about risk, and reading it as one gets it backwards.**
Every other check in this file asks *can the account afford this*; this asks *will the broker
accept it at all* — a question no amount of equity changes.

🔴 **A CLAMP IS ONLY COHERENT BECAUSE IT HAPPENS AT THE SIZING DECISION.** Root rule 17 forbids
resizing an ORDER, and that reasoning is intact: a clamped order is not the position the emulator
holds, the two grade different R, and `algos/live/bridge.py::_agrees` halts the bot on a divergence
the safety feature created. **This seam is where the strategy decides its own size**, so the
emulator books the capped quantity as its own and neither side can disagree.
`algos/shared/order_sizing.py` keeps its order-level refusal as a backstop that should now never
fire; `bridge._reconcile_lot_ceiling` holds the ceiling at `min(configured, the broker's own
maximum)` so it cannot.

⚠ **The ceiling is applied BEFORE the risk arithmetic, and the order is load-bearing.** Cap
afterwards and the leg reserves budget against a position it was never going to hold, blocking the
other leg out of room nobody used. Pinned by a test that only sees the defect when the budget
BINDS — **the first version of that test had an unlimited budget, passed, and stayed green under
the very mutation it named.**

⚠ **A clamp is recorded in `lot_capped`, deliberately NOT in `contention`.** Contention means the
legs competed; a venue ceiling is not competition — a solo run with all the room in the world still
hits it. Each record carries the overage, because a COUNT of capped trades cannot say whether the
ceiling is a rare edge or the thing now driving the account.

⚠ **`None` switches it off, and the parity anchor should use it.** The Pine twin has no such rule,
so a capped Python run graded against an uncapped chart would report a policy difference as a
parity break. `compare_strategy.py` is exit 0 with the ceiling ON at warmup 1000 on the 2026-09-02
export.

🔴 **THAT GREEN PROVES LESS THAN IT LOOKS, AND THE REASON GENERALISES: `compare_strategy.py`
COMPARES R, AND R IS SIZE-INDEPENDENT.** R is profit over risk and both halves scale with the
quantity, so **capping the size cannot move any field the gate reads** — decisions, stages, vetoes,
stops and `px_closed_r` are all identical whether a trade is 100 lots or 742. So a green gate here
does NOT establish that the ceiling never bit; it establishes that the gate is blind to it. **This
is root rule 14 with a new edge: the gate says nothing about a dimension neither side measures.**
⚠ **Do not cite this gate as evidence the ceiling is inert on an export.** If that question
matters, read the account's `lot_capped` log, which is the only thing that records it.

⚠ **A missing or non-positive broker maximum is CANNOT ASK, never NO LIMIT and never ZERO** (rule
1). Zero would refuse every order; infinite would hand the broker a size it rejects. The configured
ceiling stands, and one bad read does not ratchet it down for the session.

### Stating one — `replay/build.py`, and why it is not a strategy parameter (2026-09-03)

**A caller states a ceiling with `build_strategy(..., max_lots=)`, which builds the run's account
itself and hands it in through the `account=` seam that already existed.** No strategy package was
touched, and that is the design rather than a shortcut: threading a parameter through five packages
gives five places to disagree about what it means, and `strategies/` is under rule 22 — most of its
gates cannot even run without an export sitting on the machine.

🔴 **THREE states, and `None` is a real answer.** Leaving the parameter out means *nobody stated
one* and the strategy builds its own account at the default 100; `None` means *do not clamp this
run at all*. Collapsing them would make a run that never mentioned a ceiling indistinguishable from
one that deliberately removed it — rule 1 — and it is the only way to reproduce a run made before
2026-09-02 or to measure what the ceiling costs. The sentinel is exported as `UNSTATED`.

⚠ **Stating a ceiling AND a shared account together is REFUSED.** A shared account carries one
ceiling for every leg on it, so a second one named per-leg would clamp that leg alone while the run
reported a ceiling it enforced unevenly.

🔴 **Passing an account used to rename the leg, and that would have been a silent side effect of a
SIZE setting.** `build_strategy` forced the leg key to the strategy CLASS NAME whenever an account
was supplied, so stating a ceiling would have re-filed every trade under `SosFadeStrategy`
instead of the strategy's own default — and the strategies do not agree on a default (`strat` for
most, `recovery` for the loss-recovery leg). The class-name fallback now applies only to a SHARED
account, where a missing key really is a caller bug. ⚠ **Nothing was relying on it** — every real
caller passes `leg=`, checked rather than assumed.

### `now` has an OWNER, and without one the clamp log was undateable (2026-09-03)

🔴 **Every venue-ceiling clamp on a standalone run carried a NULL time, for as long as the ceiling
had existed.** `account.now` was stamped only by `portfolio/simulator.py`, which drives a shared
stack — so every run the lab's own Run button makes recorded *which* entries were resized and
never *when*. **That log is the only trace a resized entry leaves anywhere**: the trade list and
the equity curve are identical either way, because R is profit over risk and both scale with
quantity. A record nobody can tie to a trade is most of the evidence gone.

✅ **The strategy now stamps its own bar time (`Execution._stamp_account_clock`), unless something
else owns the clock.** `PortfolioAccount.clock_external` is set by the simulator and by nothing
else, because a shared stack must log every leg against ONE clock — a 15m leg and a 5m leg each
reporting their own bar open would make the shared contention log disagree with itself about when
a clash happened. ⚠ **The re-entry stamps too**, from its own faster feed, or a clamp on a
re-entry would carry the 15m time of whenever the primary last stepped, which is worse than
carrying nothing. ⚠ **A bar time of ZERO is a time** — the guard tests for `None`, never for
truthiness. **MEASURED on a fresh replay of 23,714 M15 bars: 28 clamps, 28 of them dated**, the
first at 2025-09-04 13:15 inside the replayed window; before the fix that column was null on all
28. 🔴 **Found by RUNNING the feature end to end, not by reading it** — the code looked correct,
and the null only appears once something actually clamps.

⚠ **A change under `backtest/` needs the Command Center RESTARTED before it takes effect**, unlike
a change under `strategies/`: the lab's runner purges `strategies.python.*` from the module cache
before every run and nothing purges the shared library, so a long-running backend keeps whatever
it booted with. Checked rather than assumed.

### `SoloAccount.external_room` — one account, several PROCESSES (2026-09-03)

**Aaron's split: each bot gets a share of one account, and when one is occupying more than its
share the others SHRINK to what is left rather than being refused; with nothing left they refuse
and say why on Telegram.** Extreme leg 5%, SOS Fade 5%, account cap 10%.

**`PortfolioAccount` cannot cross an OS process boundary**, so the live side reads the BROKER and
pushes the dollars still free onto this field each bar. Nothing about a backtest changes — the field
is `None` everywhere in the lab, which means infinite, which is what this class has always done.

✅ **IT SHRINKS, AND THE SHRINK IS SIZED AT PLACEMENT — `PortfolioAccount.affordable_qty`, called
from `Execution._fit_to_budget` (2026-09-03).** The strategy asks the account what it can still
afford BEFORE it places the order, so the order that reaches the broker is already the size the
emulator believes it holds and both sides book the same quantity. A room too small to place
anything worth placing returns 0.0 and no order is placed at all.

🔴 **THE FIRST VERSION CLAMPED AT THE FILL AND WAS WRONG — same seam, same arithmetic, one step
too late.** A live bot's order is **already resting at the broker** by the time a fill happens, so
shrinking the emulator's copy there books a smaller position than the broker just filled — and
`bridge._agrees` compares direction and presence, **not size**, so nothing halts on it. MEASURED
before it was backed out: a $0.50 room granted 0.0005 lots, under the 0.01 broker minimum.
**A safety clamp is defined by its MOMENT as much as by its seam**, and the venue lot ceiling was
right next to it doing the same operator at the right moment the whole time.

⚠ **The placement answer and the fill answer come from ONE piece of arithmetic, on purpose.**
`affordable_qty` and `request_fill` share `_risk_of`, `room_for`, `_MIN_GRANT_USD` and
`_below_floor`; a placement sized by one rule and a fill judged by another is two answers to one
question, and this repo has already paid for the general form of that twice. There is a test whose
whole job is that a size the placement fitted is then granted **in full** at the fill.

⚠ **An unbudgeted account returns the desired size UNCHANGED, and that is the parity guarantee.**
Every solo run and every `compare_*.py` gate has no room stated, so the fit is the identity
function there and cannot move a stored result. **Proven rather than argued:**
`compare_strategy.py` on `VANTAGE_XAUUSD, 15_af500.csv` was run GREEN before the change and GREEN
after it, 21,302 bars both times.

⚠ **A green gate says nothing about the shrink itself** (rule 14) — the Pine has no account
budget, so no export can ever enter this branch. The unit tests and their mutations are the only
evidence this behaviour has, and they are the only evidence it will ever have.

⚠ **ONE residual case, named rather than papered over**: if the budget shrinks BETWEEN placement
and fill, `request_fill` still refuses the emulator's side while the broker's resting order may
fill. That is the pre-existing behaviour, it is now rare rather than routine, and the only real
fix is that the budget is decided once — at placement — which is what this now does.

⚠ **THREE states, and only two are a number** (rule 1). `None` is *nobody has said*, which is
every backtest; `0.0` is *somebody asked and there is none*, which blocks the fill. Collapsing
them either refuses every backtest or grants every live trade.

⚠ **This leg's OWN open risk is subtracted from the stated room**, because the room is what the
ACCOUNT has left after the OTHER bots and this bot's position spends the same budget. The live
read excludes this bot's known tickets for exactly that reason — they are counted here instead,
from the emulator that actually knows about them. Counting them in both places halves its share.

⚠ **A zero room BLOCKS rather than granting a dust position.** A leg holds one position at a time,
so a fill of essentially no size occupies its only slot — the defect that silently retired a leg
for five and a half years, and `_MIN_GRANT_USD` is what stops it here.

### The half-share minimum and the market-bot shrink (2026-09-15)

**`PortfolioAccount(min_grant_frac=...)`** — the smallest share of its OWN desired risk a leg may be
shrunk to; below it the entry is refused (Aaron: half). A fraction of the leg's own size, not of the
balance, so it holds for legs of any size — the thing `entry_floor_pct` could not do. One helper,
`_below_share`, checked in `affordable_qty`, `request_fill` and `request_fills`, carrying
`_GRANT_EPS`. ⚠ **Defaults 0.0, so no stored run moves.** `SoloAccount` derives it:
`SHARED_MIN_GRANT_FRAC` (0.5) once a room is stated, 0.0 otherwise — solo replays and parity gates
unchanged.

**`SoloAccount.fills_at_placement`** — set by the live bridge for a MARKET bot, whose fill IS its
placement. It switches off the stated-room refusal at the fill, which exists only because a resting
order is already at the broker by then. Before this a market bot sharing an account was only ever
refused. Nothing in the lab sets it.

⚠ Two cases in `tests/test_account.py` moved from a 250-of-1,000 room to 600: a quarter is now
refused, and at 250 the anti-drift test would have passed with nothing shrunk.
Live side, and the order-check defect found with it: `algos/notes/risk-sizing-and-halts.md`.

### `output.py` — the clamp's own record, and the state that must not vanish (2026-09-03)

**`build_results` carries `lot_capped` on every run.** `None` means nothing recorded it; `[]` means
the run was measured and the ceiling never bit; a list means it did, with the overage per entry.

🔴 **The three states matter more here than anywhere else in this file, because a clamp leaves NO
other trace.** A resized entry is still a trade, in the trade list, on the equity curve, with the
SAME R as an unclamped one — R is profit over risk and both scale with quantity. So a run whose
sizes were quietly halved looks completely healthy from every number a page shows, and this is the
only channel that can say otherwise. ⚠ **It is written to `lot_capped.json` WITHOUT the
write-or-delete helper the other optional artefacts use**: that helper deletes the file when there
is nothing to write, which is right for a chart layer and wrong here — it would turn the
measurement *"clamped nowhere"* into the absence *"nobody looked"*.

⚠ **ONE contract size for the whole account.** Every stack here is gold at 100 oz/lot; a stack
pairing gold with an index would silently measure one against the other's lot size. Refuse that
when it first appears rather than passing an average.

**Tests: 13 in `tests/test_account.py`, 6 in `algos/tests/test_live_bridge.py`. All 19 mutations
watched RED**, each reddening its own named test while a control stayed green — two mutations that
reddened everything were re-aimed rather than kept, because a mutation that breaks the module
proves nothing.

## Three tools for asking whether a SECOND leg is worth having (2026-08-24)

Built to answer one question — *can the setups the gap requirement refuses be traded for a small,
fixed R?* — and each is reusable for the next leg somebody proposes.

| tool | the question only it answers |
|---|---|
| `tools/nogap_scalp_audit.py` | what a whole grid of stop × target × breakeven × ladder rules would have made, without one replay per cell |
| `tools/nogap_ishift_audit.py` | whether a 1-minute INTERNAL change of character inside the band selects the no-gap setups that pay — against the 0.618 limit on the same tape and exit code (Run 27 in the SOS Fade record) |
| `tools/nogap_anyshift_audit.py` | the same setups entered on the FIRST 1m shift of either kind after the 0.5 tag, stop at the 1.0, across a target grid (Run 28) |
| `tools/ob_leg_replay.py` | what the ORDER LAYER makes of the winning cell, against the shipped bot on a basis identical by construction |
| `tools/drawdown_fill.py` | does a second leg put equity on the board while the FIRST one is bleeding — which total R cannot answer |

🔴 **THE FIRST TOOL IS A RECONSTRUCTION AND ITS BEST CELL WAS WRONG BY MORE THAN THE WHOLE
RESULT.** It prices entries off fib geometry instead of running the order layer, which is what
makes a grid affordable — and its +32.7R best cell replayed at **−6.6R**. Its bar-walk was
validated first, and thoroughly: the excursion it computes reproduces `Trade.mfe_price` on all 158
SOS Fade trades to 0.0000R, with two mutations watched red. **That validation was real and it did not
transfer.** The arithmetic was right; the conclusion was not, because the reconstruction's pool and
its entry price both differed from anything the engine could actually run. ⚠ **Validate the walk,
then still replay the answer** — a grid tool proposes, it never concludes.

⚠ **`drawdown_fill.py`'s compounded row is an approximation and `portfolio/run_stack` is not.** It
sequences trades by EXIT and compounds them consecutively, so two positions open at once are
billed as if they were consecutive, which understates concurrent exposure. It exists to say
whether the real stack run is worth starting. **Do not quote its row as the stack's result.**

⚠ **A leg can be UNCORRELATED and still not help, and this is the case that proves it.** Monthly
correlation −0.09 over 76 months, with essentially all of the second leg's profit landing in the
32 months the first was down — and adding it made the account spend MORE days under water at every
risk weight (1813 → ~1920), with the worst drawdown flat or deeper. **Uncorrelated is necessary and
nowhere near sufficient; an edge too small and too lumpy is leverage, not a hedge.** Read
days-under-water beside the drawdown depth: they are different halves of "help me through the flat
spells" and a leg can improve one while worsening the other.

⚠ **`nogap_scalp_audit.py` needs a SECOND replay purely to see order blocks**, and the reason is
rule 8. The block engine is only built into the stack when the strategy's point-of-interest setting
asks for something other than gaps, so at shipped settings the block list is empty on every one of
155,807 bars. The first version of that audit reported *"no order block in the zone on any of the
146 setups"* off exactly that, and it read as a finding. A registry nobody populated answers
confidently and wrongly.

## The contention log records the PLACEMENT gate too, and a row is an EPISODE (2026-09-16)

**Closed on Aaron's word, 2026-09-16** — it had been open since 2026-09-15 as a stated gap and is
kept here because the reasoning is what a reader of an older run needs.

**What was wrong.** `PortfolioAccount.contention` was documented as every shrink and refusal. It
was not: it held only what `request_fill` decided, at the FILL. The placement-time twin,
`affordable_qty`, had never logged one — so every entry a stack shrank or refused **before** the
order existed was missing from the run's evidence, which is where the live path and every stack
leg actually decide (`Execution._fit_to_budget` calls it on every armed bar).

**Why it waited.** `contention` is a finished run's evidence, quoted in the stack report and
compared between runs. Appending to it moves figures in runs already reasoned about, so it was
Aaron's call rather than a side effect of adding the Telegram alerts.

### `at` says which moment decided it

Every row now carries `at`: `"placement"` (no order was ever sent) or `"fill"` (an order was
resting and got cut when it filled). They are different events about different things and a
reader counting a mixed list cannot tell which happened. **It is also how anyone comparing
against a run recorded before 2026-09-16 gets the old figure back** — those are the `fill` rows.

⚠ `reason` (which of the three rules refused it) is on placement rows only. The fill gate tests
its rules together and does not know which bit, so the key is ABSENT rather than filled with a
guess — rule 1.

### 🔴 A row is one EPISODE, not one bar, and the difference was 20x

The placement gate is asked again on every bar a setup stays armed, so one setup answers hundreds
of times. **Measured: appending each one put 976 rows in a stack log holding 42 real occasions**,
and the summary's dollars summed one setup's refused risk once per bar — $18.5M of it. A reader of
"977 contention events" concludes 977 trades were cut. The arithmetic was right and every number
it produced was misleading, which is this repo's standing warning about a verified metric.

So a run of bars deciding the same thing about the same leg — same direction, same outcome, same
rule — extends the row already open (`bars`, `last_time`) instead of adding one. An episode ends
on:

- **a clean pass** — the leg asked and was not cut; and
- **a gap longer than the spacing that episode has already shown.** ⚠ The clean pass alone is not
  enough and taking it as the only ending HALVES the count: a leg that goes idle stops asking
  altogether, so two setups months apart are never separated by a pass that fits (measured: 21
  rows for 42 occasions). The boundary calibrates off the episode's own first gap — the account is
  handed no bar size and a guessed one would be a number nobody measured (rule 4).

⚠ **The live WATCHER is still told every time; only the log dedups.** The bridge keeps its own
episode state and needs each call to maintain it, and it is deployed — a change in what it hears
would be a live behaviour change smuggled in under a logging fix.

⚠ **`now` is None until a clock is pushed and a LIVE account may never get one.** An unmeasurable
gap is not a zero one (rule 1) and may not end an episode. Subtracting straight through raised
TypeError on the first repeat — **a crash in a live bot's sizing path**, caught by the bridge
suite before it landed.

### MEASURED before landing (2026-09-16)

`sos_fade` 15m + `extreme_leg` 5m on XAUUSD.p, PU Prime demo bars, 2018-09-14 → 2026-09-15,
$10,000 opening, 5% a side:

| cap | contention before | contention after | trades | R | closing |
|---|---|---|---|---|---|
| 10% (the live shape) | none | none | 318 | +263.53 | $25,147,617.03 |
| 7% (made to bind) | 1 | 39 (1 fill, 38 placement) | 318 | +263.53 | $25,292,292.21 |

**At the live cap nothing changes at all** — two 5% shares fit a 10% cap exactly, so it never
binds. At a binding cap the log gains 38 placement episodes covering 976 bar-evaluations, and
trades, R and the closing balance are identical. **Logging decides nothing**, which is the
property that had to be shown.

## The live tap — `on_contention`

The account carries an optional observer, `None` everywhere except a live bridge. It is handed the
same row the log holds, plus a `reason` naming which of the three rules refused the entry (that
extra key is added only on the tap, so the shape of a LOGGED row — which stored runs are compared
on — does not change). See `algos/notes/telegram-message-catalog.md` for what is sent.

⚠ An observer that throws is swallowed. It reports; it never decides. A Telegram outage that
refused entries would be the safety feature causing the incident.


---

## FFT + the extreme leg as ONE BOOK — the pair beats either bot (2026-09-23)

The user asked for a strategy that beats FFT and the extreme leg. The answer is that **the book
does, and both halves already exist.** Measured from the two solo lab runs' stored equity curves
(`046197075b55` FFT, `2c3698c96b26` extreme leg), simulated on one shared $10,000 balance with each
bot risking its own fraction of current equity at its own entry and booking at its own exit, events
in true time order so concurrent trades really overlap.

**They are not correlated — if anything the reverse.**

- monthly R correlation **−0.278** over 79 months. ⚠ With n=79 the standard error is ~0.115, so this
  is ~2.4 SE from zero: read it as **genuinely uncorrelated**, and do NOT bank on the negative sign.
- FFT lost 24 months of 79, the extreme leg 20, **both lost only 6** — independence predicts 6.1.
- Only **10 of 187** FFT trades have an extreme-leg trade open at the same time (5.3%), so the 10%
  cap almost never has to refuse one. At a 5/5 split both can hold a full trade at once anyway.

🔴 **What that is worth — the risk needed to reach the extreme leg's own $100,390, and its drawdown:**

| book | total risk | max drawdown |
|---|---|---|
| FFT only | 7.77% | **35.1%** |
| extreme leg only | 5.00% | **27.7%** |
| **50/50 split** | 5.60% | **15.5%** |
| 25/75 split | 5.21% | 21.5% |

**The pair reaches the same dollar target at 15.5% drawdown — 44% less than the extreme leg alone
and well under half of FFT alone.** Run at the full 10% cap (5/5) the book makes **$572,193 at 26.5%
drawdown**, against the extreme leg's $100,390 at 27.7% on its own.

**Why it is multiplicative rather than additive:** on a shared balance each bot compounds the other's
gains. The extreme leg alone is 11.0x and FFT alone 5.16x; 11.0 × 5.16 = 56.8x, and the measured book
is 57.2x. That is the entire effect, and it is why this was worth measuring rather than assumed.

**Best split measured** (net dollars per point of drawdown, shared balance): 5/5 at 21,586, then
3.3/6.7 at 19,215, then 2.5/7.5 at 17,922. **Even splits win** — tilting toward the better bot makes
the book worse, because the diversification is worth more than the edge difference.

⚠ **Read the dollar column only against other rows in this table.** These are shared-balance figures
and rule 6 forbids comparing them to a solo run's dollars; the solo numbers above are each bot's own
basis, printed for reference, never a term in a sum.
⚠ The two runs use different cost models (the extreme leg a modelled spread, FFT bid/ask fills) and
different bar sizes. That shifts each bot's LEVEL and not WHEN its trades happen, which is what the
correlation and the overlap read. Levels are taken as each run measured them.
⚠ The simulator does not enforce the cap's refusal when both want size at once. At 5/5 the shares sum
to exactly the cap and overlap is 5.3%, so the error is small — but a real lab stack run is what
would settle it.

**What this replaces:** the 2026-09-23 conclusion that $100k from FFT costs ~35% drawdown and the
whole account. It does — *alone*. Run as a book with the extreme leg it costs 15.5%, and neither bot
has to change by a line.

### The real stack run — mechanism CONFIRMED, and a defect in the stack path (2026-09-23)

`backtest/tools/stack_run.py --legs fft:1,extreme_leg:5 --symbol XAUUSD.p --server PUPrime-Demo
--start 2020-01-01 --end 2026-09-22 --balance 10000 --risk-cap 10 --risk-pct 5 --fill-profile puprime_ecn`

⚠ **`fft` was not in this tool's `_STRATEGIES` dict and neither are `realign` or
`smc_session_sweep`** — all three are lab-registered, and the tool answered "unknown strategy" as
though they did not exist (rule 8: a hand-maintained registry that went stale). `fft` was added;
the other two deliberately were NOT, because adding a leg nobody has run through this tool is a
registry that answers confidently about something untested. A `--fill-profile` flag was added with it.

| | shared trades | shared R | solo trades | solo R | solo close |
|---|---|---|---|---|---|
| fft (1m) | 187 | +27.71 | 187 | +27.71 | **$51,650.76** |
| extreme_leg (5m) | 116 | +58.26 | 116 | +58.26 | $127,171.16 |
| shared closing | | | | | **$668,616.03** |

**✅ The mechanism is confirmed.** FFT solo closes at **$51,650.76** — its lab run's net of
$41,650.76 on a $10,000 start, **to the cent**, so this path is faithful for that leg. Compounding is
multiplicative as predicted: 5.165x × 12.717x = 65.69x against 66.86x measured, inside 2%.

**✅ Contention is real but cheap.** Peak open risk hit the 10.00% cap exactly, peak legs holding at
once **2 of 2**, and 5 FFT entries were shrunk ($10,523.48 of risk refused) out of 303 trades. **R is
identical shared and solo on both legs** — a shrink scales risk and profit together, so contention
costs DOLLARS and no edge. It would also nudge drawdown slightly DOWN, never up.

🔴 **DO NOT QUOTE THE $668,616 — the extreme leg is UNDER-COSTED in every stack run.** Its
`LAB_STRATEGY` says `"supports_bid_ask_fills": False` and its costs are billed by the LAB's cost-layer
machinery, not by anything its config declares. `stack_run.py` builds a leg straight from
`LAB_STRATEGY["config"]`, so those layers never run: its solo close here is **$127,171.16 (net
$117,171) against its lab run's net $100,390.48** — the missing costs are worth ~$16.8k, about 14% of
its profit. FFT is unaffected because its fill model lives inside the strategy.

**This is a property of the stack PATH, not of this pair, so it affects every stack run in the lab** —
including the 5-bot `st_51adad44e2` whose legs summed to $36.8M. Reported, not fixed: it is the
platform's own seam.

**What still stands:** the 15.5% drawdown for the $100,390 target, because that figure comes from the
model built on BOTH legs' measured LAB runs, which are correctly costed — and contention, now
measured, moves it down rather than up.
