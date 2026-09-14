# Notes — Costs, brokers, symbols and the news filter

Cost layers and the spread models, which broker account prices a run, symbol resolution, the broker instrument list, regime caching, the post-run news filter. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## News filter (post-run)

The economic-calendar (news) filter is a **post-run view layer**, NOT a run-time gate: the lab runs every backtest RAW (news is never wired into the C#/MQL5 strategy), so removing news-window trades is pure arithmetic on the finished trade list — instant, no VPS re-run. Design decision (Aaron 2026-07-05): **run raw + toggle after.** Window default **15 min before / 30 min after** a high-impact USD release (asymmetric — liquidity dies only in the last minutes before; the spike/reversal/move run 15–30 min after). **Two rules, both switchable, and BOTH DEFAULT OFF** (2026-08-01, Aaron's call): the page opens on the run exactly as traded, so every number on it is the backtest's own and turning a rule on is a deliberate what-if. That replaced two different defaults for one reason — a filtered default means the headline figure on screen is not the run's result, and no checkbox further down the page makes that obvious. Holidays had defaulted ON (hardcoded always-excluded with no control at all until 2026-07-30, when they became a visible checkbox but stayed ticked), and news followed the strategy's own `avoid_news`, so the default silently DIFFERED BETWEEN STRATEGIES — two runs over the same window could open on different trade counts with nothing on screen explaining why. The backend reports `in_news` and `in_holiday` separately and always has; every default here has been a frontend-only decision.

- **`services/news_filter.py`** — composes the canonical `engines/news/` engine (imported by bare name after adding `engines/` to `sys.path`, same pattern as regime; **never a second calendar impl**). `build_report(trades, pre, post, ...)` loads the `EventStore` cache, builds a lab `NewsPolicy` (high-impact USD, holidays always), and walks each trade's `entry_ms` through the engine → per-trade `{in_coverage, in_news, in_holiday, title}` + coverage boundary + counts. Reads `in_news` (a high-impact window) and `in_holiday` **separately** so the UI keeps them separable. 9 unit tests (synthetic events, no network). Coverage honesty: outside the fetched calendar range trades come back untagged (never guess) — backfill months via `engines/news/tools/backfill.py`.
- **`GET /backtests/runs/{id}/news?pre=&post=`** → `RunNewsReport` (models.py `RunNewsReport`/`NewsTradeTag`). Pure off the stored `equity_curve` — no VPS. `pre`/`post` are the window minutes (sliders re-call to re-tag). Old runs with no `entry_ms` come back untagged.
- **Trade entry time capture:** `parse_trades_csv` now stores each trade's `entry_ms` (UTC epoch ms) on its equity-curve point, from the NT8 "Entry time" column via `_parse_nt8_dt`. The VPS **NinjaTrader Time zone is UTC** (confirmed) → naive value treated as UTC, no offset. Old NT8 runs predate this → re-pull with **Reload charts** (or rerun). Python runs carry it from `backtest/output.py` and never needed either.
- **`entry_ms` AND `exit_ms` MUST be declared on `models.EquityPoint`** (entry fixed 2026-07-28, exit 2026-07-30 — the SAME omission, caught twice, which is why this is written as a rule and not an anecdote). `exit_ms` had likewise always been in `equity_curve.json` and was likewise stripped on the way out; with both present a consumer can compute trade duration over any SUBSET of trades, which is what lets the News filter report **Avg Trade** instead of a dash once it removes something. Pydantic drops any field a model doesn't declare — so the value reached disk and the `/news` endpoint (which reads `equity_curve.json` directly, and therefore tagged correctly all along) but was stripped on the way to the browser. The card's `hasEntryTimes` check then failed for EVERY run and it showed "made before trade times were recorded" universally, which reads as an old-run problem and is not one. Same trap the `favorable`/`adverse` comment two lines below it warns about. **Nothing that reaches the frontend can rely on a field being in the JSON on disk — only on it being in the model.**
- **`avoid_news` is metadata, not a default:** `strategies.avoid_news` (INTEGER col, migration; default 0) overlaid from `<Strategy>.meta.json` top-level `"avoid_news"` by `strategy_scanner._read_strategy_overview`, exposed on `Strategy.avoid_news`. ⚠ **It no longer sets the News toggle's default** (2026-08-01 — both rules default OFF; see above). It remains real strategy metadata read off meta.json and is still exposed on the API; nothing in the UI consumes it today. Re-wiring it to a default would restore the per-strategy divergence that change removed — raise it before doing so. `ORB.meta.json` ships `avoid_news:true` (gold avoids news). **Scanner fix:** the `.cs` skip now also re-scans on meta.json **mtime** (mirrors the `.mq5` path) — before this, a meta-only edit on an unchanged `.cs` source (avoid_news, edge/steps, param labels) never took effect. A **Scan** picks up the new value.
- **Runner support:** NT8 and **PYTHON** both work (python verified end-to-end 2026-07-28 on a 142-trade XAUUSD run — 142/142 in coverage, 11 news-window trades at a 15-min pre-window). **TODO (#3, still not built): the MT5/forex path** — `runner_dispatch._normalize_mt5_results` needs its own `entry_ms`, and the **MT5 broker server clock is NOT UTC** (offset + DST), so it needs its own timezone handling (a confirming step like the NT8 one).
- **Calendar coverage is the real gate, not the code.** The engine reports `has_coverage=False` outside the fetched range and the filter goes inert there — so a correctly-wired filter over an unbackfilled period looks identical to a broken one. Backfill first (`engines/news/tools/backfill.py --from YYYY-MM`), then judge. The cache is git-ignored, so it is per-machine and a fresh clone starts empty. ⚠ **Keeping it current is `./go`'s job since 2026-09-01** (step 6, `--top-up --if-stale`) — before that nothing did it at all and the cache silently fell a month behind, with `readiness.py`'s banner the only thing that noticed. Rules: `engines/news/CLAUDE.md` → *Keeping the cache current*.

## Costs are ONE SWITCH, and it defaults to ON (2026-08-24)

**Aaron's call, reversing the 2026-08-02 default.** A run nobody configured used to charge nothing,
so the first number the lab produced was always the frictionless one — a figure you cannot trade,
sitting where the answer goes. It also asked the operator to reassemble a cost policy out of five
tickboxes on every run, and a rule that lives in somebody's memory is a rule that gets broken on a
Friday.

`BacktestRunRequest.charge_costs` is a nullable bool defaulting **True**, and `routers/backtests.py`
RESOLVES it into `cost_layers` at run creation. Rules:

- ⚠ **Resolved at CREATION, never inside the runner** — rule 3: the stored row must record what was
  CHARGED, not what was asked for. The detail page, the re-price endpoint, the stress tester and
  every retry read that column back.
- ⚠ **`None` means "this caller has no opinion"** and leaves `cost_layers` exactly as sent. That is
  what a retry of a pre-2026-08-24 row does — **a retry must reproduce the run it is retrying, not
  today's default.** It is why the field is nullable rather than a plain bool.
- ⚠ **PYTHON-ONLY.** NT8 and MT5 have no layer contract; their runs keep `cost_layers = None`, and
  `charge_costs` must never manufacture one for them.
- 🔴 **`python_runner.CHARGED_LAYERS` is `(bid_ask_fills, commission, swap)` and `slippage` is
  DELIBERATELY ABSENT.** It is a typed-in guess — the modal has labelled it "a guess" since it
  shipped — and this repo's standing rule is that an unmeasured cost REFUSES rather than borrowing a
  plausible number. Folding it in would put one invented figure beside three measured ones with
  nothing downstream able to tell them apart. It is added only when a caller states a tick count > 0,
  which is somebody saying the guess out loud.
- 🔴 **`bid_ask_fills` rather than the flat `spread` charge, and they are ALTERNATIVES** — running
  both bills one spread twice. The fill model is the one that also changes WHICH setups fill
  (measured 161 trades → 159, four setups that never existed on the free path), which is the half a
  page-level toggle can never reproduce.
- 🔴 **`charged_layers(broker)` REFUSES a tier whose spread or swap has never been measured**
  (`UnpricedBrokerError` → 400). PU Prime's Prime and Cent tiers refuse today. Copying ECN's figure
  onto them is the exact mistake the sentinel exists to prevent — those tiers measured **2.7x**
  apart.
- 🔴 **Commission comes off the ACCOUNT, not off the form.** `measured_commission(broker)` writes the
  measured figure onto the row, so it is the one number the run was billed rather than a number
  somebody typed beside three measurements. Settled 2026-08-10 by filling one 0.10-lot round turn on
  each demo: Prime $3.50/side/lot, ECN $1.00, demos $0.00.

🔴 **`bid_ask_fills` IMPLIES `spread` on the RE-PRICE side too, and forgetting it double-bills.**
A run that transacted at the ask has paid the spread in the fills, so `spread` never appears in its
stored layer list — read literally it looks available, and ticking it adds a second flat charge to a
book that already carries one. Nothing downstream can tell: the result is a plausible number.
`get_run_repriced` adds `spread` to `already` whenever `bid_ask_fills` is there. ⚠ **It became
reachable on the day the charged default made `bid_ask_fills` the ordinary case** rather than a
layer nobody ticked — the implication had been stated in `_cost_profile` since 2026-08-02 and only
the WRITING side honoured it. Pinned by `test_bid_ask_fills_counts_as_the_spread_already_charged`
and `test_a_fully_charged_run_has_nothing_left_to_reprice`, both watched RED by mutation.

## The SPREAD has two models, and a strategy says which one it can be charged under (2026-09-02)

`strategies.supports_bid_ask_fills` (INTEGER NOT NULL DEFAULT 1), declared by the package as
`LAB_STRATEGY["supports_bid_ask_fills"]`, carried by the scanner, read by
`_costs._spread_model_for`.

🔴 **"Costs ON" ALWAYS resolved to the moved-fill model, so a strategy that prices the spread FLAT
could not be run charged AT ALL.** `CHARGED_LAYERS` leads with `bid_ask_fills`; `extreme_leg`
refuses a moved-fill profile at construction; so the job died three seconds in with a stack trace
**while the run form's switch said costs were being charged.** That is rule 1 in a new place —
*cannot be run* and *ran with costs* must never be reachable from the same switch, and here the
second was simply unavailable. There is no per-layer control on the form, so the operator had no
way out except running gross.

**When any strategy in the run declares it cannot move fills, the spread is charged FLAT instead.**

- ⚠ **The same three costs are still billed.** The switch means what it says; only the spread's
  MODEL bends. A fallback that quietly made a charged run cheaper would be worse than the crash.
- ⚠ **SWAPPED in the layer list, never appended.** The two models are alternatives — appending
  bills one spread twice, and the result is a plausible number nothing downstream can question.
- ⚠ **A whole STACK falls back together if ONE leg cannot**, so every call site passes EVERY leg.
  Legs on one account measured under two fill models is not a portfolio, it is two experiments
  added up.
- ⚠ **The stored layers record which model was used**, so `run_diff.py` and the lab MCP refuse a
  comparison across the two on BASIS rather than reading the gap as the strategy's doing. That
  property is why the fallback swaps the layer instead of leaving `bid_ask_fills` on the row.
- ⚠ **It is NOT a free pass.** The flat model cannot change which setups fill, so such a strategy's
  charged trade LIST is its gross trade list. Say that out loud when comparing it to one that moves
  fills.
- ⚠ **The default is TRUE and an absent key means TRUE.** Every package but one models moved fills;
  defaulting the other way would silently downgrade every charged run in the lab.
- ⚠ **A caller passing NO strategies keeps the moved-fill model** — stating nothing is not stating
  the weaker answer.
- 🔴 **It is a SECOND copy of a fact the strategy's own constructor already enforces**, so the
  declaring package PINS the two together by test
  (`test_the_declaration_matches_what_the_constructor_actually_does`). A declaration that drifts
  from its refusal gets a run charged a model the code then rejects — the dead job this whole
  mechanism removes, restored in silence.

⚠ **The strategy's own refusal is the backstop and its wording is a rule of its own** — it must
name the run's cost options rather than the broker account, which cannot clear it. Lives with the
code that raises it: `strategies/python/extreme_leg/CLAUDE.md`.

**Tests:** `tests/test_cost_spread_model.py` (9), watched RED by four mutations — the fallback
dropped, the absent-key default flipped, only the first leg asked, and the layer appended rather
than swapped.

## The regime map is CACHED on its inputs, not recomputed per run (2026-08-26)

A regime is a property of the MARKET on a date, not of a run — `build_date_regime_map`'s own
docstring said so while recomputing the whole calendar on every single run. **MEASURED: 98.5s to
turn 50,548 H1+H4 rows into 2,066 date→label strings, and a second identical call cost the same
again.** On a 3.5-minute backtest that was half the wall clock, and the tuning loop re-runs one
window over and over. **After: 2.27s, output byte-identical — 0 of 2,066 days disagree against a
baseline captured before the change.**

- 🔴 **Keyed on the DATA, never on the dates alone.** A window ending today is still filling and
  the broker back-fills history, so a date-keyed cache would serve yesterday's answer for bars
  that have since moved. The fingerprint is the index and OHLC of both frames, so a hit is only
  possible when the inputs are byte-identical and there is no staleness to reason about.
- 🔴 **The classifier's own SOURCE is in the key.** Edit `engines/regime/classifier.py` and every
  stored map stops matching — a cached label from a superseded rule is the silent wrongness this
  repo keeps paying for. `_REGIME_CACHE_LOGIC_VERSION` covers the surrounding logic (warmup,
  window size, which frames feed it); bump it by hand when any of those move.
- ⚠ **The key is taken AFTER the fetch**, which costs 2.3s every call. That is what buys the
  guarantee, and it is the right trade against a wrong regime label nothing downstream can spot.
- ⚠ **A key that cannot be taken is `None`, and `None` neither reads nor writes.** A key that
  quietly drops an input still looks like a key and would serve stale labels for ever.
- ⚠ **Fails OPEN in every direction** — corrupt file, wrong shape, unwritable dir: all cost the
  98 seconds and none stop the run. **An empty map is never stored**: `{}` means the fetch failed,
  not that the window has no regimes, and storing it would make one bad fetch permanent.
- ⚠ **This did NOT make the cold path faster** and was not meant to. The 96s is pandas overhead
  inside the classifier — ~20 operations on a 34-row window, 2,066 times. Making THAT faster means
  changing arithmetic, which is a separate decision.

⚠ **A first attempt replaced the per-day window scan with a binary search — provably identical
output, and MEASURED at no gain (105.9s against 100.8s), so it was reverted.** The quadratic is
real (2,066 days × 50,548 rows masked and copied) and it is not the cost; the cost is pandas.
Recorded so nobody spends the afternoon again.

## The cost account FOLLOWS the attached terminal (2026-08-24)

🔴 **The bar cache is partitioned by broker, so one broker's BARS can no longer reach another
broker's replay — but the cost profile was a hardcoded `vantage_demo` string.** Point the lab at PU
Prime and you got PU Prime's bars charged at Vantage's spread: the same mixed basis one level up,
silent in the same way, and the two gold spreads are $0.12 and $0.22 an ounce.

`GET /backtests/broker-profiles` now reports each profile's `server`, `account` and whether it is
`attached` — the terminal the lab is pointed at right now. The Run modal defaults to it.

- 🔴 **The ACCOUNT resolves it, never the server.** PU Prime's Prime and ECN logins both live on
  `PUPrime-Demo`, so blessing a tier on the server alone hands a run ECN's $0.12 spread while it
  sits on Prime — the 2.7x error the unmeasured-spread sentinel exists to prevent, arriving through
  the front door. A profile with no recorded account can only ever match a terminal with no
  recorded account.
- ✅ **Standard and Prime gained their logins 2026-08-26, so all three tiers can now be NAMED.**
  Until then the sentence above bit the profiles it was written to protect: blank on both meant a
  lab attached to either got the "cannot tell" notice about a terminal it could identify exactly.
  ⚠ Cent stays blank deliberately — nobody has logged into it, and the honest answer there is
  still "cannot tell".
- ⚠ **An unreachable agent attaches NOTHING** rather than falling back to a default (rule 1), and a
  terminal that answers while DISCONNECTED attaches nothing either — the agent replies `ok` with
  its broker link down, which is this repo's own 2026-08-04 incident.
- ⚠ **It WARNS, never blocks.** Measuring a strategy against a broker you are not pointed at is a
  legitimate deliberate act; the page says the run would charge one broker's costs over another's
  bars and leaves the decision alone.
- ⚠ **`server`/`account` live on `AccountProfile` in `backtest/fills.py`** — identity beside the
  costs they identify, so they cannot drift from the numbers they describe.

Three checks in `tests/test_run_list_queries.py`, each watched RED by its own mutation (server-only
matching; a default on an unreachable agent; the connected check dropped).

🔴 **THE CHART FEED WAS THE HALF LEFT BEHIND, AND IT DREW AN EMPTY CHART BESIDE 247 TRADES
(2026-08-25).** The replay was pinned to the run's own broker when the cache was partitioned; the
price chart's bar fetch was not, so it resolved whatever terminal is attached TODAY. A charged
re-run of a Vantage run completed normally and its Price tab came back blank, because the attached
terminal was PU Prime — which does not quote that run's symbol at all. ⚠ **Every other number on
the page was right**, which is what made it hard to read: the trades, the equity curve and every
KPI rendered, so the only symptom was a blank chart with no reason attached. ✅ **Fixed by resolving
the run's own profile (`chart_spec._bar_server`, which calls `python_runner.bar_server` rather than
repeating the lookup — two copies is how the chart and the replay would drift back into disagreeing
about which broker a run belongs to) and threading it to `ohlc_fetcher.get_ohlc`.** The STACK
runner and its backfill script carried the same bare call and were pinned in the same change.
⚠ **The tests pin the ARGUMENT, not the bars** (`tests/test_chart_spec_broker_pin.py`, 5 checks,
watched RED by mutation): the defect was never in the fetch, it was in what the fetch was asked
for, so a test asserting "some candles came back" would pass against the bug on any machine whose
attached terminal happened to be the right one.

⚠ **The standing lesson is about the SWEEP, not this call site.** Pinning three call sites in the
runner and stopping there left four more — the chart feed, its drill-down, the stack runner and the
stack backfill — each of which reads the same partitioned cache and each of which was silently
wrong. **When a shared resource gains a partition, the audit is every construction of the thing
that reads it, not the ones the reported bug happened to touch.**

Proof: `tests/test_run_list_queries.py`, four checks, each watched RED by its own mutation (default
flipped to None; commission override deleted; refusal removed). The fourth — costs-off still
reachable — passes throughout on purpose, so a later "simplification" that hard-wires charging
cannot land quietly.


## The broker's own instrument universe — `GET /backtests/broker-symbols` (2026-09-07)

🔴 **THE RUN FORM'S INSTRUMENT SUGGESTIONS WERE TEN NAMES TYPED INTO THE SOURCE, AND THEY WERE THE
WRONG BROKER'S.** They were Vantage's spellings, confirmed against a terminal in July 2026, while
the lab has since been attached to PU Prime — which quotes gold with a suffix and has its bare forex
group DISABLED outright. MEASURED on the attached terminal: **1,085 instruments, 0.34s**, of which
1,075 could not be reached from the form at all. `services/broker_symbols.py` serves them, grouped.

⚠ **The agent endpoint it reads had existed since 2026-08-16 with NO consumer** — rule 9, a feature
nobody has run. It was correct; nothing had ever asked it.

🔴 **`symbols` is `None` when `available` is false, NEVER `[]`.** An unreachable agent, a
disconnected terminal and a terminal answering with an error all come back as a reason, and a caller
rendering an empty list would be describing an outage as a product decision. ✅ **Confirmed against
a REAL outage the same day** — the agent went down mid-session and the endpoint answered
`available: false · "MT5 agent /status: timed out"` with `symbols: null`.

⚠ **It is a 200 carrying that refusal, not a 503.** The page has a legitimate question and an
unreachable agent is a real answer to it; an error status makes a working page look broken and puts
the reason where nothing renders it.

🔴 **THE LIST BELONGS TO THE ATTACHED TERMINAL, NEVER TO THE BROKER PICKED IN THE FORM**, so every
response names the server and account it was read from. One terminal is attached at a time; showing
its 1,085 names under a different broker's selection is the mixed-basis defect one field over.

🔴 **The cache is keyed on the terminal's IDENTITY and that identity is re-checked on every call**
(rule 16 — the terminal has already switched accounts under a running bot once). A universe cached
against a constant key keeps serving the previous broker's instruments under the new account's name.
⚠ **An unreachable agent RAISES rather than keying the cache on a blank server**, or the second
caller is served the previous broker's list under a terminal nobody can reach.

⚠ **The asset classes are derived from KEYWORDS in the broker's own grouping, never from a table of
one broker's folder names** — a table is right on one broker and silently wrong on the next.
⚠ **The ORDER of the rules carries meaning** (metals before commodities, indices before shares) and
must not be sorted. ⚠ **Anything the keywords do not recognise KEEPS THE BROKER'S OWN LABEL rather
than being swept into "Other"** — an "Other" bucket would tell a reader that two unrelated groups
are the same kind of thing.

🔴 **THE WHOLE PATH IS READ, AND JUDGING ONLY THE OUTERMOST FOLDER HID 93 INSTRUMENTS (fixed
2026-09-07).** MT5 nests — `247 Product\Stocks\US\AAPLUSD` — and `classify` judged
`_clean_group(path)`, the first segment alone. `247 Product` names no asset class, so **Apple,
Tesla, Amazon and 78 more were filed under a chip called *247 Product* while a reader hunting them
checked *Shares***. The word that answers it, `Stocks`, was fetched on every call and thrown away
one line before the rules ran. ✅ MEASURED on the live terminal: **81 symbols move to Shares, 12 to
ETFs, and nothing else in the 1,085 changes**; the picker's chip row went 12 categories to 10.

⚠ **Segments are tried DEEPEST FIRST** — the innermost folder is the most specific, so
`247 Product\ETFs` must answer ETFs rather than falling through to the outer folder. Rule ORDER
still decides within one segment. ⚠ **The last segment is the SYMBOL and is dropped**: reading it
would classify `Forex\XAUUSD` as Metals off the symbol's own spelling rather than off anything the
broker said. ⚠ **A path with no separator is one FOLDER, not a leaf**, or every flat group on the
terminal has nothing left to classify.

⚠ **`US.24H` still falls through and that is NOT a failure to patch by hand.** Its 62 symbols sit
flat under one folder with no sub-folder and no type word anywhere in the path, so the broker
genuinely states nothing, and its own label at least tells the reader it is a round-the-clock book.
**Inventing a class for it would be a guess wearing a measurement's clothes.**

🔴 **ALL 36 TESTS PASSED THROUGHOUT, BECAUSE THE FIXTURE WAS FLATTER THAN THE TERMINAL.**
`LIVE_GROUPS` wrote every group as one folder plus a symbol (`247 Product\SPCXUSD`) where the real
path is three folders deep — **and a two-segment fixture cannot exercise a bug that needs three.**
⚠ **Rule 13 says a fixture MORE capable than production hides the defect. This is the same rule from
the other end: a fixture SIMPLER than production hides it just as well, and is harder to notice,
because nothing about a tidy path looks like a claim.** The fixture now carries the terminal's real
nesting, and four mutations were RUN — the shipped behaviour, an unconditional leaf drop, keeping
the leaf, and outermost-first — each red on its own named test.

🔴 **Only a one- or two-letter LOWERCASE tail is trimmed from a group name, and that narrowness was
MEASURED.** The first version stripped any trailing dotted word, which turned the `US.24H` group —
62 round-the-clock share CFDs — into a category called `US`. It did not fail; it produced a
plausible label carrying no information, which is the worse half of getting it wrong.

⚠ **A restricted symbol is LISTED and MARKED, never dropped.** 59 of the 1,085 are disabled,
close-only or long-only, including the entire bare forex group — a restriction on the ACCOUNT says
nothing about whether the instrument's history is replayable.

⚠ **The venue lot ceiling travels with each symbol** (rule 17): it is part of what a run is measured
on, so it is served rather than looked up again elsewhere.

🔴 **ONE DROPPED REQUEST USED TO BLANK THE WHOLE PICKER, AND IT WAS REPORTED OVER A TERMINAL THAT
WAS CONNECTED THE ENTIRE TIME (2026-09-07).** Two faults, both here. The identity probe got **no
retry**, and the observed failure is an immediate *"Remote end closed connection without response"*
rather than a timeout — so a sub-second tunnel blip was indistinguishable from a dead terminal. And
because the identity check runs BEFORE the cache is consulted, that blip **threw away 1,085
instruments read seconds earlier** and told the reader the broker could not be reached. MEASURED
minutes later: 30 probes out of 30 clean, 0.45s each; the symbol pull finishes in 0.8s and does not
block the health probe, so the agent was never the problem.

✅ **The probe is asked twice** (`_PROBE_ATTEMPTS`), and ⚠ **only a TRANSPORT failure is retried** —
a terminal that answers and says it is not connected has given a real answer, and asking again is
just being slower about believing it.

✅ **A failed probe now serves the LAST GOOD read rather than a blank panel**, flagged `stale: true`
with its `reason` and the time it was read. ⚠ **`available` still means "there is a list to show"**,
so the picker keeps working. ⚠ **The payload keeps the server and account it was ACTUALLY read
from** — the one real hazard is that the terminal moved during the gap, and an account number in
front of the reader is what lets them notice. ⚠ **No TTL is applied on that path on purpose**: it is
only reached when the terminal cannot be asked at all, and a list from an hour ago beats nothing —
a broker's instruments change over months. The staleness is REPORTED, never enforced. ⚠ **With
nothing ever read, it is still a refusal** — the fallback must not invent a list.

⚠ **The generalisation is worth more than the fix: the rest of this app already tolerates a blip**
(the health dot caches 30s, the bot snapshot and the calendar keep their last good rows and date
them). This endpoint was the only thing on the page that panicked, so it was the only thing that
looked broken — and it blamed the broker for its own brittleness.

✅ **36 tests, 12 mutations RUN and 12 killed.** 🔴 **One SURVIVED and found a real gap: the
disconnected-terminal test passed an explicit `False`, which `is False` and `is not True` both
catch — so the two readings were indistinguishable and the suite was green either way. The case that
separates them is a status dict with the key MISSING (the agent answered and did not say), which is
"cannot tell".** Story and the measured counts: `../docs/BACKEND_BUILD_NOTES.md`.

### 🔴 A stack's cost layers were WRITTEN as a list and READ BACK as text (2026-09-07)

`insert_stack` JSON-encodes `cost_layers` with a careful three-state comment. `get_stack_settings`
was a bare `SELECT *` that decoded nothing, so what went in as `["spread", "commission", "swap"]`
came back as those 31 CHARACTERS. Handed to `python_runner._cost_profile`, **a string iterates** —
every real layer name fails to match and the validator refuses, naming `' '`, `'"'`, `','`, `'['`,
`']'`, `'a'`, `'c'`, `'d'`… which are exactly the distinct characters of that JSON.

🔴 **It killed two of the three stack stress-test phases and had done since the column existed.**
Walk-forward lost all 8 periods; sensitivity died on the stack's own baseline replay. The grade
came back a **D** off Monte Carlo alone, with the tool honestly reporting that the other two "are
not evidence either way" — which is the right behaviour and is also why nobody chased it.

🔴 **THE REASON IT HID IS THE PART TO KEEP: the round trip was only ever HALF MADE.** CREATING a
stack takes its settings from the REQUEST, where they are a real list, so stacks built, replayed
and reported correct books for months. Only the phases that RE-READ the row later ever saw the
text. **A round trip that is never completed looks exactly like one that works.**

✅ Fixed at the READ, with the helper this module already has (`_parse_json_fields`), so every
consumer gets what was written and nobody has to remember. ⚠ **NULL stays None and must** — it
means *this row predates layers*, against `[]` meaning *charge nothing*, and collapsing them
silently re-prices every stored stack the moment one is rerun.

⚠ **One TEST was pinned to the broken contract** and went red: it did
`json.loads(stored["cost_layers"])` to work around the text, which was never part of what it
asserted. It compares directly now, so a regression to text fails there rather than three phases
later. **A workaround inside a test is a record of a defect nobody named.**

⚠ **Every model in this app declares `cost_layers` as `Optional[list[str]]`**, so the text form
was out of contract with the whole codebase — checked, not assumed. Both new tests watched RED by
their own mutation (drop the decode; collapse NULL to `[]`).

### `GET /stress-tests/gradable` — the refusal moved to BEFORE the click (2026-09-07)

Promoting a stack to a stress test was offered on stacks that cannot be graded, and **nothing on
the page could tell**: the stack reported 272 combined trades and its contention data as
`available: true`, so every check the screen could make PASSED. The missing piece was a file only
this process can see. The reader clicked, waited, and got a 400.

✅ It calls `gradable.resolve` and returns its reason — **never re-asking its questions.** A second
copy of *"is this gradable"* is two answers about a stack somebody is about to spend an hour on,
and the copy that goes stale is the one the button reads (rule 7).

⚠ **`gradable: false` is a 200, not an error.** A page asking a legitimate question must not look
broken in the console. ⚠ It takes a run OR a stack because the resolver does — the single-run flow
has the same class of precondition and would otherwise grow its own private copy later.

⚠ **The gate discriminates BOTH WAYS and that was checked**: disabled with the server's exact
reason on a stack with no combined book, enabled with no reason on one that has it. An
always-disabled button passes the first test alone.

### 🔴 `_SHARED_TREES` gained `execution` — and it is HAND-MIRRORED, not derived (2026-09-07)

`bot_versions.trees_for` answers *which trees ARE this bot's version*. Its strategy half shares a
resolver with the promote tool; **its shared half is a tuple typed out here**, and that half is
free to drift.

🔴 **IT NEARLY DID, THE SAME DAY.** A new top-level `execution/` package was added to what a
promote COPIES, because the strategy imports it at module scope and a snapshot without it cannot
import. Had this tuple not moved with it, the tree would deploy while the Configure tab reported
the bot up to date — **the promoted-but-not-counted failure this module's own docstring names.**

⚠ **The docstring says both sides "call the SAME resolver". That is true of the STRATEGY half
only**, and it was read as true of both. The shared trees have always been mirrored.

✅ **The mirror is now enforced from the `algos/` side** —
`algos/tests/test_promote_version.py::test_the_counted_trees_ARE_the_trees_promote_copies`
PARSES this tuple and compares it against what `promote.repo_trees` actually returns. ⚠ **Parsed,
not imported**: this package has its own venv and pulls in FastAPI, and wiring two trees together
to read a tuple of strings is worse than reading the text — the same call `test_bot_bench.py`
makes about the bot registry. ⚠ **It refuses on an empty parse**, or renaming the tuple would
compare equal to nothing and pass. Three mutations run, all red.

⚠ **The test that carried that name before could not have caught this** — it pinned the copier's
list against a literal and never read this file at all. **A guard named for a comparison it does
not make is worth less than none.**

**Add a shared tree to BOTH lists or to neither.**

---

## 🔴 A stored symbol beat the instrument the run LOADS (2026-09-09)

`_build_config` filled the symbol in only when the params carried nothing
(`not kwargs.get("symbol")`), so a SCANNED DEFAULT won over the resolved instrument. PU Prime
quotes gold suffixed and Vantage bare — the lab has resolved the instrument against the broker
since 2026-08-26 — and `extreme_leg`'s package declares the bare name. **So that stack leg
replayed `XAUUSD.p` BARS with a config that said `XAUUSD`, and its stored row said the bare name
too.**

⚠ **Found by diffing a stack leg against the bot it mirrors, not by a test.** The one field that
reads it is the news filter's instrument, that filter is OFF on the bot, so nothing errored and
nothing could have. **A wrong instrument name in a config is not an error, it is a question asked
about a different market.**

🔴 **THE TEST THAT WAS SUPPOSED TO COVER THIS ASKED ONLY THE EASY HALF.**
`test_the_symbol_comes_from_the_run_not_the_param_form` passes an EMPTY param dict, which the
broken code handles correctly — so it was green against the bug for as long as both existed.
**A test named for a rule must exercise the case where the rule can be broken**, and here that is
a params dict that already carries a symbol.

✅ **Two halves, and neither is sufficient alone:**

- **`_build_config` — the RUN'S INSTRUMENT ALWAYS WINS.** There is no case where a param should
  override it: a run measured on one instrument while telling the strategy it is on another is
  not a configuration, it is two runs. ⚠ An UNRESOLVED instrument (a broker whose naming was
  never recorded resolves to the name as typed) leaves a stated symbol alone rather than blanking
  it.
- **`with_run_symbol` — the RECORD.** The stored row must SAY the instrument the run loads, or a
  reader, a rerun, a settings copy and a comparison are all looking at a name the run never used
  (rule 3). Called by the single-run path and by BOTH stack paths.

⚠ **It only rewrites a key that is ALREADY there.** A strategy declaring no symbol must not grow
one: the bot settings import diffs a run's params against a bot's declared fields, and an invented
key would show up there as a setting somebody chose.

⚠ **It copies rather than mutating.** A leg's params come straight off the scanned strategy row,
which the caller may hand to another leg.

**Tests:** 7 new (43 in `test_python_runner.py`, 59 in `test_shared_stack.py`). ⚠ **Non-vacuity by
MUTATION: 6 written, 6 RUN, 6 killed** — the old guard restored, the unresolved case blanking a
stated symbol, the rebase inventing a key, writing an unresolved name as a claim, mutating in
place, and the shared launch no longer rebasing.

🔴 **ONE SURVIVED FIRST AND IT WAS THE HARNESS AGAIN — third time in this file.** The anchor
carried a blank line, which matched the SCREEN path while the test drives a SHARED stack, so the
mutation landed on a path the case never enters. **A mutation that lands somewhere else is not a
surviving mutation, and it reads exactly like one.** Anchor on something unique to the branch you
mean.

⚠ **The end-to-end case must run against a broker whose suffix is RECORDED.** On `vantage_demo`
the resolved name and the typed name are the same string, so the fixed and the broken code produce
identical output and the case proves nothing — the same shape as a scaling test written against a
scale of exactly 1.
