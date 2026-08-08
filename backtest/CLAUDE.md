# CLAUDE.md — backtest/ (the Python backtest runner)

**Purpose:** Standing instructions for `backtest/`, the LWG Python bar-replay backtest runner.
**Scope:** This package only — the data layer, replay loop, fill/cost model, output adapter, and
local optimizer. It does NOT cover the engines it replays (`engines/`), the strategies it runs
(`strategies/python/`), or the lab that consumes it (`command-center/`).
**Status:** **Deliverable A COMPLETE 2026-07-16.** A0 (data layer) + A1 (replay loop) landed
2026-07-15; A2 (fill & cost model), A3 (output adapter), the lab's `runner="python"` adapter, and A4
(local optimizer) all landed 2026-07-16. See `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
**Last reviewed:** 2026-08-08 (latest) — 🟢 **THE RAW PU PRIME TIERS CAN BE CHARGED A SWAP AGAIN, BECAUSE SOMEBODY FINALLY READ ONE.** `puprime_prime` and `puprime_ecn` have carried `UNMEASURED_SWAP` since 2026-08-06, when the assumption *"swap is a fact about the symbol, so it is shared across a broker's tiers"* was disproved on this broker's own products. **Aaron opened a demo of each tier and all three were read** (`broker_facts.py --path/--account/--symbol`, MT5_Lab logged into each in turn, read-only): **700119432 Standard `XAUUSD.s`, 700152904 Prime `XAUUSD.p`, 700152905 ECN `XAUUSD.p` — all three long −79.60 / short +30.25, 20-point stops level, contract 100, digits 2.** Identical to each other and to the live bot's account. ⚠ **Read the shared `_XAUUSD_SWAP` constant as "three reads that AGREED", never as "Standard's figure reused"** — that distinction is the whole point of the sentinel, and the 2026-08-06 refusal was correct on the evidence then available (`XAUUSD.s` vs `XAUUSD.crp` really do differ 8.5x on ONE account). **Three tiers agreeing is a RESULT and must not become the assumption**, which is why `puprime_cent` is still unread, still refuses, and is where the refusal tests were re-aimed rather than deleted. 🔴 **THE SPREAD IS STILL REFUSED AND THE SENTINEL STAYS.** The only readings available were the last quotes before a **Friday close** — Standard 37 points, both raw tiers 17 — and **a stale close-time quote is not a spread**; the tool reports nothing rather than letting a repeated tick pass for a rock-steady one. That 37-vs-17 gap points the right way for a marked-up tier against a raw one and is not evidence. 🔴 **PRIME AND ECN ARE INDISTINGUISHABLE FROM THE TERMINAL — same symbol, same swap, same stops level, and identical on every account-level field including leverage (500:1 on all three).** The only thing separating those two tiers is **COMMISSION, which MT5 does not publish on a symbol specification at all** — it lands on a filled deal. The tier labels come from PU Prime's back office, not from anything measured here, and **one 0.01-lot round turn on each demo would settle both which account is which AND the published $1.00-vs-$3.50 contradiction.** ⚠ **A correction to a conclusion recorded here on 2026-08-06: the suffix IS the tier.** *"The suffix scheme is product lines, not tiers"* was drawn from a **Standard** login — the one place that evidence is invisible. `.s` is Standard, `.p` is the raw tiers, and neither account can see the other's symbol; there is no `XAUUSD.p` on the Standard account. **A survey of what one account can see is not a survey of the broker.** ✅ 1 new test pinning the READ NUMBERS rather than `unmeasured is False` (a stand-in would pass the latter), watched RED against HEAD; 3 refusal tests re-aimed at `puprime_cent` with the reason in their docstring; 349 backtest tests green. Full record: `docs/BROKER_QUESTIONS.md`. Earlier: 2026-08-07 — ⚠ **`tools/bos_sweep.py` IS STILL FALSIFIED AND THE BOS PARITY GREEN DOES NOT RESCUE IT.** `strategies/python/mpc_bos/tools/compare_bos.py` exits 0 against a real export as of today — but it validates the PORT, and this file carries a separate, simplified model of the same setup. The Strategy Tester's refutation of it (20 trades / PF 2.97 here against 24 / PF 1.04 there, same config) stands unaddressed. **The docstring now says so rather than pointing at the gate as though it were pending on this file's behalf** — a green run somewhere else in the repo is not evidence about code that green run never executed. Use `strategies/python/mpc_bos/` for anything that has to be right. Earlier the same day: 🔴 **THE BAR CACHE CLAIMED 45 DAYS OF 1-MINUTE HISTORY IT DID NOT HAVE, AND BECAUSE A CLAIMED RANGE IS NEVER RE-FETCHED, THE LOSS WAS PERMANENT.** Aaron drilled the price chart to M1 and got ~100 bars behind a red *"No earlier M1 data — all the broker still has"*, on a symbol whose real M1 history runs to 2018-09-14. ✅ **MEASURED, not inferred: `XAUUSD__M1.ranges.json` claimed 2018-09-14 → 2026-08-06 while the CSV held NOTHING between 2026-06-22 and 2026-08-05 — 45 days, ~62,000 bars — and asking the broker directly for one day inside the hole returned 4,013 bars.** The file was otherwise perfect: 2.75M rows, sorted, no duplicates, spanning the full range. 🔴 **The mechanism is `_covered_end` answering with ONE END DATE, so it always claimed from `gap_start` whatever came back — a PARTIAL serve was recorded as a complete one.** Its single clamp is *never past the last bar returned*; there was no mirror for the first, so a 45-day request that came back with one day's bars was written down as 45 days fetched, and a fetch with a HOLE in it was claimed straight across. ⚠ **`Mt5Agent.bars` produces exactly those shapes on its own** — it CHUNKS a long window (M1 past ~60,000 bars needs several) and stitches them, and an empty chunk beside a served one is deliberately not an error, so a partial serve needs no bug anywhere else. ✅ **`covered_spans` replaces it: coverage now DESCRIBES the bars received** — the days that carry bars, joined across stretches no longer than `_MAX_CLOSURE_DAYS`, with the `gap_start` edge extended back only over that same tolerance. ⚠ **That tolerance is MEASURED, not chosen: the longest legitimate no-bar run in 7.9 years of cached XAUUSD is 2 days** (a weekend, or Good Friday plus its weekend — 2026-04-02 → 2026-04-05); 4 is that plus headroom, and it only has to tell 2 days from 45. Splitting on a weekend instead would refetch every weekend on every load, which is the 72x tax this package fixed a day earlier, returning in miniature. ⚠ **One diagnosis I wrote was WRONG and the test disproved it, so it is recorded as wrong**: I claimed an EMPTY fetch also claimed the whole gap — it cannot, because `BarCache.save` raises on a frame with no columns and the load fails loudly first. `covered_spans` still answers `[]` for it as defence in depth, and its test is LABELLED as not biting today, because coverage must not depend on another module crashing to stay honest. ✅ **`tools/repair_coverage.py` re-derives a sidecar from the bars on disk** — the fix stops the lie being WRITTEN and cannot un-write one already there. Run against the live cache it found **exactly one affected pair** (XAUUSD M1, 45 days) out of eleven, which is the reassuring half: this was one incident, not systemic rot. It only ever SHRINKS coverage, because growing it would be inventing a fetch. ✅ **Repaired and verified end to end: the sidecar was rewritten, the window re-fetched (67,039 bars in 53.8s), and the same drill-down request that returned 721 bars now returns 11,864.** ✅ 8 new tests in `test_source.py`, **4 watched RED** by restoring the old one-span logic; the other 4 are labelled as guards on the new code (over-splitting a weekend) rather than catches. **The standing lesson is this package's own rule finding one more branch to hide in: “never record what you requested as though it were what you received” was already written here, already enforced at the END of the window — and the START was still taking the request on trust. A clamp on one end of a range is not a clamp on the range.** Earlier: 🔴 **A SWEEP CANNOT REPLAY A STRATEGY THAT NEEDS TWO TIMEFRAMES, AND AS OF TODAY ONE DOES BY DEFAULT — SO IT REFUSES.** `mpc_sos_fade`'s `exec_secondary` (the 1-minute re-entry) defaulted **ON** on 2026-08-07, and it needs a second bar stream through `run_dual`. **`run_sweep` takes ONE frame**, so the optimizer, sweeps and the stress test's pooled sensitivity have nowhere to get one. ⚠ **The dangerous option is not refusing — it is replaying single-stream**, which returns every combo as a primary-only book and ranks it against a baseline that HAS re-entries, then hands the winner to a validation run that does too. **A comparison whose two sides were measured on different books is this repo's most-repeated defect** (the Run modal's costs, the Optimize modal's params, the tune page's `cost_layers`, the stress test's children). `_refuse_unreplayable` raises and NAMES the way out — the same call `reprice.py` makes about `bid_ask_fills`. ⚠ **It fires in TWO places on purpose**: in `run_sweep` before a pool is spawned (so a refusal reads as a refusal rather than as a crash sixty processes in) and in `_replay_one`, which is the seam every combo actually goes through, serial or pooled. ⚠ **Checking combo 0 is sound because a sweep varies PARAMS, never the strategy** — say it that way rather than implying every combo is inspected. ⚠ **A config without the field is untouched**, which is every other strategy here, and that half is pinned by a test that PASSES against the pre-guard code and is labelled as such: a guard reaching for a missing attribute would break every NT8/MT5 sweep at once. ✅ 4 new tests, 3 watched RED; 341 backtest tests green. **The standing lesson is about what a DEFAULT reaches: flipping one in a strategy package made a shared library in a different subsystem wrong, silently, because `run_sweep` had no way to know the strategy had grown a second input stream.** Before defaulting a capability on, ask which callers cannot provide what it needs. Earlier: 2026-08-06 — 🔴 **TWO PROCESSES WRITING THE BAR CACHE DESTROYED IT TWICE IN ONE DAY, AND BOTH TIMES IT LIED ABOUT BEING COMPLETE.** `BarCache.save` is a read-modify-write over the WHOLE file — load the CSV, merge, write it back — and nothing serialised it. Two of those interleaving is not a race that loses a few rows: the second writer lands its bytes on top of the first's at whatever offset it reached. **Measured on the live M1 file: 2,596,551 rows claiming to be one sorted history and holding two, spliced at line 618,164 where a timestamp reads `6-17 07:47:00`** — `2020-06-17` with its first six characters overwritten. 🔴 **The M15 incident earlier the same day is the more dangerous one because it produced no error at all**: the file simply lost ~31,000 rows out of its MIDDLE (9.6 MB → 8.0 MB, 186k → 155k rows) **while `ranges.json` went on claiming the whole span**, so nothing would ever have re-fetched them — a cache that reads clean and quietly holds less than it claims, which is the exact failure this package exists to prevent. ⚠ **Atomicity and locking are BOTH required and neither is sufficient**, which is the part worth carrying. `atomic_write_*` (temp file + `os.replace`) means a reader never sees a partial file — that kills the splice. It does **not** stop two writers each reading the same base file, merging their own bars, and replacing it in turn: the result parses perfectly and one writer's entire fetch is gone. That is the *quiet* version of the same lie, and it is what `cache_lock` closes. ⚠ **The lock covers the CSV and its `ranges.json` sidecar TOGETHER**, and `BarSource._load_base` holds it across the save/record pair: the invariant is not "each file is well-formed" but **coverage never claims more than the bars on disk**, and two individually-atomic writes still leave a window where exactly that lie is true. ⚠ **It is taken around save+record, NOT around the fetch** — the fetch is the slow part and holding a lock across it would serialise two backtests for minutes, whereas two processes fetching the same range is merely wasteful because `save` merges. ⚠ **Re-entrant by necessity, not convenience**: `flock` is per file DESCRIPTOR, so the nested acquire inside `save` would deadlock against the lock its own process already holds; the depth count makes the inner call free and a `threading.RLock` makes a second THREAD wait instead of walking straight through its own process's flock. ⚠ **`CROSS_PROCESS` is exported rather than swallowed** — with no `fcntl` this degrades to a thread lock, and a lock that silently protects less than it claims is the same class of defect it was built to fix. ✅ **7 new tests (`tests/test_cache_concurrency.py`), the two that matter WATCHED RED against HEAD for the RIGHT reasons** — `rows are out of order — two frames were spliced`, and `expected 1250000 bars, found 250000`. ⚠ **The first attempt at the splice test PASSED against the broken code and was vacuous**: 5 writers × 40k rows finish too fast to overlap, and only at 250k rows does the real interleave reproduce. **A concurrency test that does not lose the race proves nothing.** ⚠ **The writers are real SUBPROCESSES** — a threading-only reproduction would pass against a threading-only fix while the actual failure stayed open. 338 backtest tests green. **The standing lesson is about which failures a cache can even report: every other guard in this package protects against the BROKER answering a narrower question than the one asked, and this one came from inside — two of our own processes, no error, no warning, and a `ranges.json` still vouching for bars that were gone. Before trusting a shared file, ask what happens when two of you write it.** Earlier the same day: 🟢 **THE BAR PIPELINE CARRIES TICK VOLUME NOW, AND IT WAS DISCARDED AT THREE SEPARATE HOPS.** Aaron's brother asked for a VWAP on the command center's price chart. `engines/vwap/` has existed and been Pine-parity green since it was ported — **the missing piece was the DATA**: a VWAP is a volume-weighted mean, and **there was no volume anywhere in this package.** The VPS agent's `_rates_to_bars` built each bar as time/OHLC and never read MT5's `tick_volume`; `cache._normalize` sliced every frame to `OHLC_COLS`; `resample_up` aggregated four columns. Three independent discards, none of which errored, and the field was gone before any consumer could ask for it. **`volume` is now an OPTIONAL fifth column** carried by `_normalize` and summed by `resample_up`. ⚠ **Optional is the design, not a hedge: a frame from a feed with no volume must carry NO volume column, never a fabricated one** — a zero-volume bar is a real thing MT5 reports on a dead session, so filling the unknown with one puts a measurement where there is none and every consumer downstream reads it as fact. The chart layer's whole contract is that distinction (`command-center/backend/services/vwap_overlays.py`): all-or-nothing, refuse on a single unknown bar, draw on real zeros. ⚠ **Volume aggregates by SUM and by nothing else** — first/last/max keeps the number in the right order of magnitude and under-weights every resampled bar in a VWAP by roughly the resample ratio. ⚠ **`_volume_sum` uses `skipna=False`, which is the accuracy half**: pandas' default sum treats an unknown bar as a zero-volume one and yields a short total that looks perfectly ordinary, so one unknown base bar poisons its window and the window says so. ✅ **`FEED_VERSION` 2 → 3**, which is exactly the mechanism this module documents for a new column — a v2 file is not WRONG, it is INCOMPLETE, and the distinction cannot survive a merge: fold a v2 span and a v3 span into one file and the volume column is real for part of the history and NaN for the rest, which is the shape a VWAP averages straight through. **The measured cost of that bump is a one-time re-pull of 1.1 GB across 11 (symbol, tf) pairs**, the 144 MB XAUUSD M1 file included, paid per pair on next use. 🔴 **The bump created a DEPLOY-ORDERING TRAP and the sidecar now closes it.** `FEED_VERSION` lands in the repo; the VPS agent is deployed separately — so a fetch in that window writes a file stamped CURRENT while holding no volume, which then never re-pulls and leaves the chart layer permanently and silently absent for that symbol. `BarCache.has_volume()` records what CAME BACK rather than what the version implies (this package's own `_covered_end` rule, one file over), so `False` is a visible marker meaning *delete that pair's `.csv` and `.meta.json`*. ⚠ **It is deliberately NOT wired into `is_stale`** — that would re-pull the whole history on every run until the agent ships, which is loud but makes the lab unusable for anyone who pulls before deploying, and the honest fix is one deletion. ⚠ **Tick volume, never `real_volume`**: there is no exchange behind a CFD quote so `real_volume` is 0 on every broker here, and tick volume is also exactly what TradingView plots as `volume` on the same symbol — which is the series the engine was validated against, so the chart line and the TradingView line are computed from the same numbers. ✅ 11 new tests (`tests/test_volume_passthrough.py`), **8 of the first 10 watched RED against HEAD**; the two that passed there pin the half that was already right (an absent volume column stays absent) and are labelled as such. 331 backtest tests green. **The standing lesson is about where a field dies: three separate hops each had a defensible local reason to keep only OHLC, and none of them was wrong on its own — but a column discarded at the first hop cannot be missed at the third, so nothing downstream could even ask the question.** Before concluding a feed lacks a field, follow it from the source rather than from the first place you look.

**Earlier the same day:** 🔴 **THE CACHE WAS RE-DOWNLOADING SIX AND A HALF YEARS OF BARS TO OBTAIN ONE DAY, ON EVERY REQUEST THAT REACHED THE LIVE EDGE.** `BarSource._load_base` asked `RangeCoverage.covered()` — *is the WHOLE window fetched* — and on `False` re-pulled the entire window from the agent. **`_covered_end` deliberately never marks TODAY as covered** (the 2026-08-04 rule: a day still filling is indistinguishable from a complete one), so a window ending today can NEVER be fully covered, and every single call re-fetched the lot. ✅ **MEASURED on the live cache: 27.8s to load 155,776 XAUUSD M15 bars for 2020-01-01 → today, against 0.39s for the identical span ending yesterday — 72x, paid on every chart open, every backtest and every sweep whose window reaches the live edge.** `RangeCoverage.missing()` answers with the GAPS instead, so that run fetches one day and reads the other 155,000 bars off disk; a fully covered window returns `[]` and takes the old no-fetch path unchanged. ⚠ **The two rules are NOT alternatives and the fix keeps both**: the never-mark-today clamp is what keeps the recent edge HONEST, and this is what makes honouring it cheap — the defect was never the clamp, it was asking a yes/no question of something that is only ever partly true. ⚠ **A partial fetch is only safe because `BarCache.save` MERGES rather than overwrites** — an overwriting cache would let a one-day tail pull delete six years of history, which is the silent-data-loss version of this same change. ✅ 12 new tests (`test_coverage.py`, `test_source.py`), watched red against HEAD. **The standing lesson is about the SHAPE of the question: `covered()` is a boolean over a range, and a boolean cannot express "all but the last day" — so the one answer it could give forced the most expensive possible response.** When a cache reports its state as yes/no, ask what it does with *nearly*.

Earlier: 🔴 **EVERY PU PRIME PROFILE IN `PROFILES` SHARED A SPREAD MEASURED ON ONE ACCOUNT TIER, SO THE THREE THAT ARE NOT THAT TIER WERE FICTION — FIXED.** Aaron asked which PU Prime account type (Standard / Prime / ECN) suits the A+ bot. Measuring it exposed that `puprime_standard`, `puprime_prime`, `puprime_ecn` and `puprime_cent` all carried `_SPREAD_XAUUSD_PUPRIME = 0.32` — **measured on a STANDARD demo, which is the one tier priced by a marked-up spread.** So selecting `puprime_ecn` charged ECN's commission ON TOP OF Standard's spread: a combination no real account offers, which overstates every raw tier and makes Standard look better than it is. **Nothing errored.** ✅ **Fixed as a REFUSAL rather than a typed-in number** — the `SENTINEL` pattern `commission_per_side_per_lot` already uses ("passing 0.0 is fine IF you have checked it is zero; the point is that it must be a decision, not a default"). The three raw tiers carry **`SPREAD_UNMEASURED`**; `AccountProfile.spread_or_refuse()` raises and names `broker_facts.py`, `bid_ask_fills` on an unmeasured tier is refused at CONSTRUCTION (it decides which trades exist), and `mpc_sos_fade`'s `_spread()` routes through the refusal so it fires wherever the profile came from. **An unmeasured tier must refuse, never inherit a measured tier's spread**, which is this file's own "quoting one broker's figure for another is a 50% error" rule one level down — the same trap between two ACCOUNTS of one broker rather than between two brokers, and harder to see, because the broker name on the profile is right. ⚠ **The refusal is on the SPREAD, not on the tier** — a raw tier's commission and swap are known and still chargeable; refusing to build the profile at all would make the honest half unusable. ✅ **DRIVEN against real replays, not unit-tested alone: all six cases behave** — ecn+spread and cent+spread+swap refuse at the first charge, prime+bid_ask_fills refuses at construction, ecn+commission+swap still RUNS, and standard/vantage are untouched. ⚠ **One test asserts the MESSAGE and that is the whole test:** the sentinel is `-1.0`, so the pre-existing `spread <= 0` guard already raised — saying *"spread is 0 — the ask would equal the bid"*, a confident FALSE DIAGNOSIS, since the spread is not zero but unknown. **A nearby guard that happens to fire is not the right guard firing.** 🔴 **AND THE SWAP ASSUMPTION WAS CHECKED THE SAME DAY AND IS WRONG, SO SWAP REFUSES TOO.** The first pass left `_XAUUSD_SWAP` on every tier and NAMED the assumption — *swap is a fact about the SYMBOL, so it is the same across a broker's tiers* — as a ⚠ caveat rather than sentinelling it. Aaron asked for it settled properly. ✅ **MEASURED with `algos/tools/broker_facts.py --symbols` (added for this), one command against the live terminal: `XAUUSD.s` and `XAUUSD.crp` are the SAME market** — median M15 close difference **$0.08** over 200 shared bars — **on ONE account**, carrying **swaps 8.5x apart (long −79.60 vs −9.35) with the short CREDIT gone entirely (+30.25 vs +0.04)** and spreads of 0.320 (1,915,768 ticks) vs 0.130 (708,565). **This strategy trades both sides and its whole swap arithmetic rests on that credit nearly cancelling the long charge**, so borrowing another product's swap is not a small approximation. The three raw tiers now carry **`UNMEASURED_SWAP`** — a `SwapModel` whose point values stay at SENTINEL (honest: they are unset) and whose every read refuses. ⚠ **`swap=None` still means "charge no swap" and stays silent** — that distinction is the whole sentinel, and collapsing it would run a raw-tier backtest with the LARGEST cost on this strategy quietly zeroed. ⚠ **`XAUUSD.crp` is `trade_mode: DISABLED`** — evidence, not an opportunity, which is why the tool prints the trade mode beside the tempting numbers. ⚠ **The terminal cannot answer the tier question either way**: the suffix scheme across all 1,015 symbols is `.s` / `.24H` / `.crp` / no-suffix — product lines, not tiers — so **a second account is the only way to measure Prime or ECN.** ✅ **The refusal propagates without touching the lab**: `charge()` routes through `per_lot_per_night()`, and both real consumers (`execution.py`, `reprice.py`) go through `AccountProfile.swap_charge`, so one guard covers every path and `python_runner` inherits it by copying `base.swap`. ✅ **Driven end to end: ecn+swap refuses at the first charge, ecn+commission still RUNS, standard and vantage unchanged.** 500 backtest + strategy tests green; 3 new swap tests watched red by putting the borrowed swap back. **The standing lesson is about how an assumption survives: this one was testable in one command the whole time, and it lasted because no command existed. Naming an assumption is not testing it — when you write one down, ask what it would cost to check, because here it was ten minutes.** ✅ **The account question itself is ANSWERED and it overturns the intuitive reading: take a RAW tier, not Standard.** One real replay per row, 155,531 M15 bars, spread modelled with `bid_ask_fills` (the only cost model here that can move the trade list): **Standard ($0.32, $0 comm) +141.87R with 8 setups never filled · Prime (~$0.08, $3.50) +150.90R / 3 · ECN (~$0.08, $1.00) +152.07R / 3**, against +142.18R free. 🔴 **Spread costs ~20x what commission costs, and it costs by KILLING FILLS**: commission alone is 0.48R at $1.00/side and 1.67R at $3.50/side over 6.5 years, while the fill loss is monotonic in spread — 3 setups at $0.05-0.08, 6 at $0.15-0.22, 8 at $0.32, 12 at $0.50. ⚠ **Read the FILL column, not the R column** — a 10R gap sits under this strategy's sd of 15.06R, and what makes the conclusion safe is that every raw row beats every Standard row across the whole published range, not any single figure. ⚠ **The drawdown column was measured and DISCARDED**: Standard read 8.36R vs ~5.7R but it is not monotonic in spread ($0.50 → 6.77R), so it is one unlucky path and is not part of the case. ⚠ **Only the $0.32 is ours** (1,893,438 ticks); every Prime/ECN figure is off a marketing page and **the published sources contradict each other** on which tier carries $1.00 and which $3.50 — worth 1.2R, so it changes nothing. **The standing lesson is about which costs a fee table can express: a cost that acts by REMOVING opportunities cannot be compared against one that acts by SHAVING returns without replaying both** — the first shows up only in the trade COUNT, and a trade that never happened has no P&L to charge. The reasoning that fails is genuinely persuasive and was this assistant's first answer: *a resting limit fills at its own price or not at all, so it never pays the spread* — true, and wrong, because the limit avoids the spread BY NOT FILLING. Full record + the questions to put to the broker: `docs/BROKER_QUESTIONS.md` and `docs/LIVE_TRADING_PIPELINE.md` → G5a. Earlier the same day: ✅ **`PROFILES` NOW CARRIES PU PRIME'S OWN MEASURED NUMBERS, AND THE STRATEGY COSTS 23% MORE ON THE BROKER IT ACTUALLY TRADES.** Every layered-cost table in this repo was replayed on **Vantage**; the bot trades **PU Prime**. Measured off the live terminal with `algos/tools/broker_facts.py --history-days 3` (read-only, **1,893,438 ticks over 3 whole days**): **spread 0.33 → 0.32** (median; p99 0.37, max 0.39 — and flat at 0.32 in 22 of 23 traded hours, only the hour reopening after the 21:00–22:00 UTC break widening to 0.35), **swap long −78.29 → −79.60, short +29.49 → +30.25**. ✅ **What it costs, one real replay per row over 155,531 M15 bars at the shipped defaults:** free **+142.18R** (maxDD 5.61R) · Vantage **+130.59R** (6.23R) · **PU Prime +127.91R** (6.83R) — **2.68R more cost, 23% more, and a third more drawdown.** 🔴 **89% of that gap is the SPREAD, which is the opposite of what the swap's size suggests:** spread alone 7.67R vs Vantage's 5.28R, swap alone 6.60R vs 6.31R. Swap is the bigger cost on BOTH brokers and barely differs BETWEEN them, because PU Prime's worse long swap (−79.60 vs −74.84) is nearly cancelled by its better short credit (+30.25 vs +26.98) and this strategy trades both sides. ✅ **The layers are additive and the trade count is identical in every row (159)** — 5.28 + 6.31 = 11.59 exactly — which is the check that says the charge is real and correctly placed: **a cost changes what a trade MAKES, never whether it happens.** 🔴 **A SWAP IS NOT A CONSTANT.** The old values were read on 2026-07-16 and were 1.7% / 2.6% adrift three weeks later, with nothing to announce it — a swap gets read once, hardcoded, and then quietly describes a rate the broker has moved on from, and it is the LARGEST re-priceable cost on this strategy (6.41R of the reference run's 12.08R). **Re-measure before quoting a cost figure.** ⚠ **`test_each_brokers_spread_is_its_own_measurement` and `test_profile_swap_converts_units_to_lots` were updated, and that is the system working, not a test being loosened** — they exist to catch one broker's figure being copied onto the other, or a number moving with no measurement behind it. Their docstrings now name the tool and the sample, so the next edit has to bring evidence. ⚠ **Vantage is untouched and must stay so:** it is the BACKTEST broker, chosen to match the TradingView feed the Pine was written on, and every parity result depends on it. ⚠ **Commission is still ASSUMED $0.00** (demo) until a real fill confirms it. 295 backtest tests green. Earlier: 2026-08-06 — 🔴 **`EngineStack` BUILT NO EQ ENGINE, SO THE FVG CAP COULD NOT SEE LIQUIDITY EVEN IN PRINCIPLE — AND THAT PUT THE A+ PARITY GATE RED FOR THREE DAYS.** The FVG engine has accepted `eq_levels` / `eq_tol` since 2026-07-19 (the Pine `eqExemptFvg` coupling: a gap sitting on an active EQH/EQL survives the cap), and **nothing here ever passed them.** `mpc_strategy.pine` defaulted that input ON on 2026-08-03, so from that day the Pine and the Python bot evicted different gaps; at bar 11031 of a 21,999-bar export Pine rested a limit on a gap edge at 4965.73 that Python had FIFO-dropped, and Python snapped to fib 0.702 at 4990.02. **The gate reported it as an entry-RULE mismatch, and the entry rule is line-for-line identical on both sides.** `EngineConfig` now carries `eq_exempt_fvg` (+ the three locked detection constants), the stack builds an `EqualHighsLowsEngine` **only when the flag is on**, and it runs **EQ BEFORE FVG**, the Pine order — the exemption tests this bar's active levels against this bar's ATR(50) tolerance. ⚠ **The flag DEFAULTS OFF here and that is deliberate**: it is an input in every Pine that has it, turning it on changes which gaps exist hence which entries fire, and with it off the stack builds no EQ engine at all so every replay predating the coupling is byte-identical and free of the extra ATR + pivot scan. **`mpc_sos_fade` pins it True; `mpc_bleg` pins it False**, because their two Pines genuinely disagree. ⚠ **This is the unpinned-engine-input rule below reaching its worst case, and the new part is the second failure on top of it.** The four earlier instances were all *a consumer forgot to pin a value*; here the MECHANISM was absent, so no pin could have helped — and because no `cfg_` column carried the input, **the gate could not see the difference and blamed the wrong code.** A test now asserts the stack actually holds an EQ engine when the flag is on and none when it is off, because asserting the pin alone would have stayed green throughout the entire incident. ✅ `compare_strategy.py` exit 0 at warmups 100 / 500 / 1000 / 2000; `compare_bleg.py` exit 0 at 100 / 800 / 2000; 320 engine + backtest tests green. **Standing rule gained: when a consumer pins an engine input, check the STACK actually wires that input's mechanism — a config field with nothing reading it is a pin on a feature that does not exist.** Earlier: 2026-08-05 — 🟢 **THE JITTER AUDIT RAN, AND THE THING IT WAS BUILT TO MEASURE TURNED OUT TO BE THE SMALL ONE.** `tools/jitter_audit.py` closes G17: the shadow diff proved that four cents of broker quote difference can move a resting entry by $10.08 (a `exec_fib_nearest` rung flip), and one leg cannot say how OFTEN that happens. **MEASURED on 186,220 M15 bars (2018-09-13 → 2026-08-04), baseline 183 trades / +134.75R, 12 jittered replays at ±$0.05 per bar.** 🔴 **Rung flips are RARE — 1.4 per run, 0.8% of trades — and the real sensitivity is the FILL, an order of magnitude bigger: ~10.7 trades lost and ~10.4 gained per run, i.e. about 6% of the trade list changes.** Not because the strategy decided differently; because every entry here is a resting limit at an exact price, and five cents decides whether price reaches it. ✅ **The edge survives comfortably: every one of the 12 seeds finished POSITIVE (+92.24R to +148.13R), mean +131.74R, sd 15.06R.** ✅ **And the baseline is not optimistic — median jittered +134.52R against a +134.75R baseline**, i.e. the shipped number sits mid-distribution rather than at the top of it, which was not guaranteed and is the reassuring half. ⚠ **So "the strategy transfers" and "the trade list transfers" are different claims, and only the first is supported.** Expect the live trade list to be a cousin of the backtest's, not a twin. ⚠ **THE JITTER MODEL IS THE DESIGN, and the obvious version measures nothing**: a CONSTANT price offset cannot flip a rung — every fib level translates with it — so the offset is redrawn PER BAR, which is what moves a gap edge relative to a ladder anchored on different bars. One offset applied to all four of a bar's prices, so `high >= max(open, close)` still holds; jittering O/H/L/C independently would build candles no feed can produce and measure the engines on impossible data. ⚠ **The flip threshold is DERIVED, not chosen** — an offset drawn from [−amp, +amp] can move a price by at most `amp`, so two runs differ by at most `2*amp` from noise alone and anything beyond that is a different decision. ⚠ **A trade that merely fills a bar or two later is RETIMED, not lost-and-gained**, and that distinction moved the headline: the first pass counted them as one trade destroyed plus one invented and reported ~9% churn where the honest figure is ~6%. Retimed pairs are matched one-to-one nearest-first (52 across the 12 seeds) — without that, one jittered trade would be claimed as the twin of two baseline trades and BOTH counts would collapse toward zero, i.e. the tool would report perfect stability by double-counting. ⚠ **The flip count is a FLOOR**: a flip that also moves the entry bar lands in retimed or lost+gained, never in flipped. ⚠ **When a flip does fire it is violent — median 31% change in the 1R stop distance, max 84.5%** — and since the trade is sized to its stop, the nominal R is unchanged while the POSITION SIZE and the fill probability both move. **Read a flip as a size event, not a return event.** 28 tests (`tests/test_jitter_audit.py`), weighted toward the two silent errors: calling noise a flip, and calling a flip noise. Earlier: 2026-08-04 — 🔴 **THE BAR CACHE RECORDED WHAT IT WAS ASKED FOR, NOT WHAT CAME BACK, AND HAD BEEN SILENTLY TRUNCATING EVERY RUN THAT REACHED THE LIVE EDGE.** `_load_base` fetched, saved, and then called `coverage.record(start_date, end_date)` — **the REQUEST**. Ask for bars up to a date the broker does not have yet (every `--end today`, every `end = last_bar + 1 day`) and that date is marked fetched **forever**; the next request reads as a cache HIT and returns a frame that stops where the old fetch stopped. **No error, no warning, and nothing in the returned frame to tell you** — the caller gets a clean DataFrame that simply ends early. ✅ **MEASURED on the live cache, not reasoned about: the sidecar claimed history through 2026-08-06 while the CSV held nothing past 2026-08-03 03:45, and the agent was serving the missing 170 bars on request the whole time.** Found by the shadow diff, which could only compare 66 of 148 live bars and said so. **Fixed in `_covered_end`, two clamps:** never past the last bar actually returned, and **never into today** — because a day that is still filling is indistinguishable from a complete one by looking at the bars (a frame ending 00:15 on the last day is either *the broker stops here* or *it is 00:20 right now*), so the live edge is never marked covered and simply refetches until it is genuinely in the past. ⚠ **A window ending in the past is unaffected and does no extra work** — pinned by a test, because a fix that made every historical run pay an agent call would get reverted. ⚠ **The start side needs no clamp**: `assert_window` already refuses a window before the measured floor. This is that same defect arriving from the OTHER END of the window. 5 new tests in `tests/test_source.py`. **The standing lesson is this repo's own, and it is the third distinct route to it: the system quietly answered a NARROWER question than the one asked.** The hardcoded history floor did it at the start of the window, `run_report.py`'s default `--start` did it by defaulting, and this did it at the end — and all three shared the property that the RESULT looks perfect. **Never record what you requested as though it were what you received.** Same day: **`tools/overlap_audit.py`** landed (do two strategies trade different legs of the move — see the tools section). Earlier: **`reprice.py` AUDITED LAYER BY LAYER AGAINST REAL CHARGED REPLAYS, and the biggest layer turned out to be the untested one.** `test_repricing_reproduces_a_real_charged_replay` was parametrized over `spread` and `commission` only — the two EXACT layers — so the suite proved the cheap half and left **swap**, which is **6.41R of the reference run's 12.08R against the spread's 5.67R**, and the only layer whose docstring makes a numeric accuracy claim, resting on nothing. Now covered. ✅ **MEASURED over the full 2020→2026 window (155,453 M15 bars, 161 trades), re-price vs a real charged replay: spread `0.0000R`, commission `0.0000R`, swap `−0.0376R`** — and the swap error is **exactly one trade**, the long held **2022-12-28 → 2023-01-03**, where `rollovers_between` books a New Year night the replay never charged because no bar existed to charge it on. That is precisely the holiday supersede this module's docstring names, so the ~0.3% claim is now a verified number rather than an estimate: **0.03% of the R, 0.32% of the final balance.** ⚠ **The test's swap tolerance (0.05R) is a MEASURED bound, not a loosened one — if it starts failing, that is a real divergence in the swap model; do not widen it.** ⚠ **`equity_rel` is a SEPARATE parameter from the R tolerance**, because a tiny R error COMPOUNDS through the balance re-walk (0.0376R → 0.32% of final equity); one shared bound would either let a real R divergence through or fail the exact layers on dollars. ⚠ **`RepricedRun.total_cost_usd` had no docstring, and that is how it came to be rendered captioned "after compounding" in the lab** — it is the FEES, not how much smaller the run finished; those differ by **55x** on the reference run ($332,371 vs $18,200,741). It says so now. Earlier the same day: **`reprice.py` charges costs onto a run that ALREADY HAPPENED, from its stored trades, without replaying it.** The lab's run page needed to switch costs on and off after the fact, and the obvious objection is that it cannot be done: a charged run compounds differently, so every later trade is a different SIZE, and you cannot price a position the stored run never sized. **The way out is that each re-priceable cost is, in R, INDEPENDENT of size.** A trade risking `dist * qty` and charged `spread * qty` loses `spread / dist` of R whatever `qty` is; commission and swap cancel the same way. So the R is knowable and the dollars follow from re-walking the balance. ⚠ **Proven against real replays, not argued** — `tests/test_reprice.py` replays `mpc_sos_fade` free and charged, throws the charged replay away, rebuilds it from the free run's curve, and demands equality; on the live 161-trade lab run it lands **37¢ out on $16.3M**. ⚠ **`bid_ask_fills` and `slippage` are REFUSED, never approximated** — the first changes which setups fill (161 → 159, with four that never existed on the free path) and the second depends on which exits were market orders; no arithmetic over a trade list can produce either, and the caller is told to re-run. ⚠ **Swap is ACCURATE, NOT EXACT (~0.3%)**: the replay charges swap on the first BAR after a rollover and latches once, so any rollover in a stretch with no bars is superseded — Friday and Saturday always (gold shuts AT Friday's rollover; the weekend rides on the triple-swap Wednesday), and holidays unpredictably. **Mirroring the replay's source line-for-line would be the WRONG answer** — its `_last_rollover_before` skips Saturday only, and charging Friday books 8 nights a week instead of 7, measured at 0.74R too expensive. ⚠ **`build_equity_curve` now carries `r` and `risk_usd` per trade**, COPIED from the strategy: recovering them from a 2dp `profit` and a 5dp `stop_price` is correct but lossy and compounds to ~0.02% of final equity. A run predating them still re-prices, flagged `derived_basis`, and the caller must caption it. Earlier: 2026-08-02 — **`AccountProfile` learned the two costs BAR MODE could always have priced and never did: the SPREAD and the OVERNIGHT SWAP.** Two new fields, `spread` (price units) and `bid_ask_fills`, both bar-mode-only (tick mode has the real book) and both defaulting to the honest zero, so a profile built before they existed is byte-identical and no historical result moves. Swap needed **no new code at all** — `_charge_swap` has run on every bar since A2 and was dead only because callers passed `swap=None`. ⚠ **The two spread fields are ALTERNATIVES, not layers that stack**: a flat charge, or transacting on the real side of the book. Running both bills one spread twice, and the strategy's `_charge_spread` refuses the second. ⚠ **They do not agree, and the gap is the finding rather than a defect** — a flat charge is the MARKET-ORDER intuition, and a strategy whose entries and exits all name a PRICE feels the spread as fill TIMING instead; measured on `mpc_sos_fade` the flat charge costs 5.7R and the fill model costs none, because the whole burden lands on shorts (which buy the ask to exit). ⚠ **Spread is a fact about the SYMBOL as much as the account** — the `PROFILES` values are XAUUSD's, measured per broker off that broker's own cached ticks (**Vantage 0.22 over 1.49M ticks, PU Prime 0.33 over 688k**; quoting one for the other is a 50% error), exactly as `swap` already was. `bid_ask_fills` validates that `spread > 0`, because an ask equal to the bid would silently do nothing while claiming the fills are modelled. 386 tests green. Earlier: 2026-07-31 — `EngineConfig`'s FVG defaults reconciled to the ENGINE (`fvg_max_count` 6→8, `fvg_threshold_pct` 0.1→0.0), and doing it exposed that `mpc_sos_fade` had been reading the old `0.1` **unpinned** — a stale-looking default that was actually load-bearing. The unpinned-engine-input rule below gained that second example and its corollary: never tidy an `EngineConfig` default without checking which consumers read it unpinned. Both strategy parity gates re-verified green afterwards. Earlier: 2026-07-29 — `run_report.py --start` now defaults to the MEASURED broker floor instead of a hardcoded `2022-01-01`, and `backtest/archive/` was added for committed multi-year trade data. Earlier: 2026-07-27 — `build_results` gained `blocked_setups` and `missed_setups`; 2026-07-26 — `EngineConfig` gained `fvg_require_close` (see the unpinned-engine-input rule below); `verify_parity.py` gained a veto column and now runs the B-LEG parity check too

---

## What this is

Strategy- and instrument-agnostic backtest infrastructure — the same character as `engines/`: a
shared library, not owned by any one app. It pulls broker data, replays it bar-by-bar through the
canonical `engines/`, simulates fills against real ticks, and emits the
`{equity_curve, daily_pnl, kpis, engine_trades}` shape the command-center lab already consumes
(registered there as `runner="python"`, next to `"mt5"`/`"ninjatrader"`).

**Why top-level, not inside command-center:** it must be importable standalone — CLI backtests, the
`/audit-strategy` parity harness, CI — without dragging in the FastAPI app. The lab consumes it
through a thin `runner="python"` adapter in `runner_dispatch`, the same thin-shim pattern engines use.

## Build pieces (from the plan)

- **A0 — Data layer** *(done)*. `backtest/data/`. Pull broker bars directly at the base timeframe,
  cache to disk, resample UP to the target timeframe. Ticks (2yr deep) back the fill model.
- **A1 — Replay loop** *(done)*. `backtest/replay/`. `iter_bars(df)` turns the data-layer frame into
  `ReplayBar`s (0-based index + epoch-ms UTC time); `EngineStack.step(bar)` drives the canonical
  engines in Pine order (structure → fib{structure/sniper/macro/internal} → FVG → RSI-divergence →
  liquidity → sessions) and returns a `BarState`; `run(df, warmup=…)` is the convenience iterator.
  `EngineConfig` carries the engine-construction knobs; note `show_internal` (default True): the
  `market_structure` engine always computes internal structure, but a consumer whose Pine has
  "Show Internal Structure" OFF sets this False, which blanks the snapshot's internal-derived fields
  (`i_confirmed_*` / `ifib_seed_*`) so the Structure fib does not adopt an internal-swing anchor. The
  mpc_sos_fade bot pins it False; the engine parity harnesses keep it True (they validated internal ON).
- **A2 — Fill & cost model** *(done 2026-07-16; bar-mode costs added 2026-08-01)*.
  `backtest/fills.py` + the tick seam in `mpc_sos_fade/execution.py`. **Two fill models, and the
  distinction is load-bearing:** `fill_model="bar"` (default) is the strategy's own bar-level
  intrabar-path GUESS, and it matches what the Pine assumes, so it is the ONLY model
  `compare_strategy.py` may diff. **Bar mode charges zero costs BY DEFAULT — which is not the same
  as charging none by construction, and until 2026-08-01 the two were confused.** A caller may
  now hand `MpcSosFadeStrategy(..., cost_profile=<AccountProfile>)` and have commission and a
  per-fill slippage estimate charged into each trade's own P&L; omit it and the path is
  byte-identical to what it has always been, which is what keeps the parity gate valid. Build the
  strategy through `backtest.replay.build_strategy` rather than calling the class directly — it
  REFUSES to run a strategy that cannot accept a profile when the caller stated costs, instead of
  silently dropping them (that silent drop is exactly the lab bug this closed: the command center
  collected `commission_per_side` / `slippage_ticks` for months, stored them, displayed them, and
  charged neither). Two units to get right, both stated in `AccountProfile`: commission is per
  **LOT** per side (a lot is `contract_size` units — 100 oz for gold), and `slippage_ticks` is a
  **bar-mode-only** estimate charged on **market exits only**, because a resting limit fills at
  its price or better or not at all and tick mode measures the real thing off the tape.
  **Bar mode learned the SPREAD and the SWAP on 2026-08-02**, which were the two costs bar mode
  could have priced all along and did not: `AccountProfile` gained `spread` (price units, bar-mode
  only — tick mode has the real book) and `bid_ask_fills`. Both default to the honest zero, so a
  profile built before they existed is byte-identical. Swap needed no new code at all — the charge
  path has always run in bar mode and was dead only because callers passed `swap=None`.
  ⚠ **The two spread fields are ALTERNATIVES, not layers** — a flat charge, or transacting on the
  real side of the book; running both bills one spread twice, and `_charge_spread` refuses the
  second. ⚠ **They do not agree, and the gap is the finding, not a defect**: a flat charge assumes
  market orders, and a strategy whose entries and exits all name a PRICE feels the spread as fill
  TIMING instead — measured on `mpc_sos_fade`, the flat charge costs 5.7R and the fill model costs
  none, because the whole burden lands on shorts (which buy the ask to exit). ⚠ **Spread is a fact
  about the SYMBOL as much as the account** — the values in `PROFILES` are XAUUSD's, measured per
  broker off that broker's own cached ticks (**Vantage 0.22 over 1.49M ticks, PU Prime 0.33 over
  688k**; quoting one for the other is a 50% error), exactly as `swap` already was.
  `fill_model="tick"` resolves every level against real bid/ask ticks (long enters on the ask, exits
  on the bid), measures stop slippage off the actual next tick rather than assuming a constant, and
  charges commission + swap into the trade's own P&L. **Tick mode is expected to DISAGREE with the
  Pine on ambiguous bars — that is the improvement, not drift.** Bar mode must stay bit-identical
  forever; `test_execution_ticks.py::test_bar_mode_is_untouched_by_a2` is the guard.
  Measured on the 365d 15m XAUUSD run: real fills cost 1.3% of net, 0 bars fell back to the guess.
  ⚠ **Bar mode has one KNOWN LIMITATION that is not a defect and must not be "fixed" (recorded
  2026-08-01):** a stop staged mid-bar can be behind the market by the time it goes live next bar
  (price tags TP1, the stop stages to breakeven, price closes back through it in the SAME bar), so
  the exit fills at the next bar's OPEN rather than at the stop. Being out is CORRECT; only the
  exit PRICE is imprecise, and only because bar replay checks orders once per bar while a real
  broker watches every tick. **It errs in the safe direction (backtest looks slightly worse than
  reality), it is identical in Pine and Python so parity is unaffected, and tick mode legitimately
  disagrees with it** — that is the improvement, not drift. Canonical write-up:
  `strategies/python/mpc_sos_fade/CLAUDE.md` → `### Wrong-side stop fills`.
- **A3 — Output adapter** *(done 2026-07-16)*. `backtest/output.py`. `build_results(trades, …)` →
  the lab's `{equity_curve, daily_pnl, kpis, engine_trades, blocked_setups}`. Strategy-agnostic: it consumes any
  trade object carrying the reporting fields (`execution.Trade` satisfies it) and owns no strategy
  or fill logic — pure reporting arithmetic. It deliberately does NOT compute `sharpe`/`cagr`: the
  lab stamps canonical Sharpe from `daily_pnl` at completion (`metrics.apply_canonical_sharpe`) and
  a second definition here is exactly the duplicate-definition bug that doc warns about. The two lab
  contracts it mirrors by hand (the equity-curve point; `sizing_engine.RawTrade`) are locked by
  `tests/test_output.py` — including one that builds the REAL `RawTrade` from our rows, so the
  contract can't silently drift. Each equity-curve point also carries `favorable`/`adverse` (the
  trade's excursion, read from `Trade.mfe_usd`/`mae_usd` via `getattr` default 0.0, so a trade
  duck-type lacking them is fine) — the lab's TradingView-style equity chart reads them.
  ⚠ **`costs_usd` on a point is SIGNED, and a positive value is a real outcome, not an error.**
  The convention is the broker's (`execution.py::_charge`): **negative = charged, positive =
  CREDITED**, because a short's gold swap genuinely pays you (+26.98 points/night on Vantage) and
  can exceed the spread on the same trade — measured at **39 of 161 trades net-credit** on the
  reference run. `reprice.py`'s `cost_usd` is the OPPOSITE sign (positive = charge), so anything
  crossing between the two must negate, never take an absolute value. **Taking `Math.abs()` is the
  bug this warning exists for**: the lab's `Fees charged` row did exactly that until 2026-08-03 and
  read **$415,990 against a true $332,371 — and $514,315 against $252,998 on swap alone, 103%
  high**, while the pill beside it showed the correct figure. A cost model that can pay you is not
  an edge case here; it is the normal state of a short. Wired into
  the lab 2026-07-16 as `runner="python"`. **`blocked_setups`** (added 2026-07-27,
  `build_blocked_setups`) is the same idea for the trades that never happened: a setup one of the
  strategy's own rules refused places no order, so it is in no trade list and this is its ONLY
  channel to the lab. Same duck-type discipline (`dir`/`time_ms`/`code`/`edge`/`label`/`reason`),
  always present as a key, `[]` when a strategy records none. Full path:
  `command-center/backend/CLAUDE.md` → *Blocked setups*. **`missed_setups`** (added 2026-07-27,
  `build_missed_setups`) is its companion one step earlier in a setup's life: not "which ready trade
  did a rule refuse" but "how far did this setup get before it died". Same duck-type
  (`dir`/`time_ms`/`edge`/`met`/`near` + `labels`/`reasons`/`met_lines`), same always-present-and-
  empty rule. `met_lines` arrives pre-FORMATTED and `of` is a per-record number, so nothing here or
  downstream knows what a "confluence" is — a strategy scoring out of four just ships `of=4`. `near`
  is the strategy's own "worth looking at" flag and must pass through UNTOUCHED: the chart derives
  its opening view from it, so defaulting or dropping it silently changes what a reader sees first.
  Full path: `command-center/backend/CLAUDE.md` → *Missed setups*.
  **`fib`** (added 2026-08-02, `_trade_fib`) is the newest optional key on an equity-curve POINT:
  the fib LEG a trade was priced off, as `{start_ms, levels: [[ratio, price], …]}`, and absent
  entirely when a trade carries none. Same duck-type discipline as everything else here — any object
  exposing `levels` as (ratio, price) pairs satisfies it, so this file knows nothing about which
  ratios a fib "should" have and a strategy with its own ladder just ships different pairs.
  ⚠ **It COPIES, and must keep copying.** The prices are the ones the strategy had in hand when it
  placed the order; recomputing them here — or in the chart — from anchors and a direction would be
  a second implementation of one leg, and the two would eventually disagree about a trade neither
  can re-run. Pinned by `test_the_fib_ladder_is_COPIED_never_recomputed`, which feeds it a
  deliberately non-linear ladder and requires it back unchanged.
- **A4 — Local optimizer** *(done 2026-07-16)*. `backtest/optimizer.py`. `run_sweep(module_path, df,
  combos, …)` replays one strategy over N parameter sets with the bars loaded ONCE and combos fanned
  across cores — no VPS, no terminal lock, no deploy/compile (4 combos over 3 months = 9s).
  **It owns only "replay fast."** The LAB still expands the grid (min/max/step is the lab's contract,
  shared with NT8/MT5 — `optimization_runner.expand_grid`) and still scores/ranks/picks the winner
  (`objectives.py`, `_pick_best_run`), so nothing above the seam has a Python-specific branch.
  Configs arrive **fully built** (`Combo.config`), so exactly one place knows how a lab param dict
  becomes a strategy config. Each combo gets a fresh strategy + engine stack — sharing either would
  make results a function of grid order. **Sweep in bar mode, validate the winner in tick mode:** a
  tick pass is ~1,100s vs ~10s for the 365d 15m run, so a 100-combo grid is ~31h vs ~2min, and real
  fills only moved that run's net by 1.3%. Reached from the lab via `runner="python"` on the existing
  native-optimizer contract (`python_runner.start_native_optimization` / `native_opt_results`).
  **Callers must be import-safe** — the pool spawns workers, which re-import the calling module; a
  script needs an `if __name__ == "__main__"` guard (`python_runner` is a module, so it is safe).

## Tools

- **`tools/verify_parity.py`** — the one "is everything in sync?" command. Point it at the TradingView
  export CSV(s) you just pulled; it runs every parity check (all nine engine `compare_*.py` + the
  mpc_sos_fade `compare_strategy.py` + the mpc_bleg `compare_bleg.py`) whose MARKER column is present in the CSV, and prints one
  GREEN/RED/SKIP table. Cold-start warmup is auto-detected by walking a capped ladder (≤25% of the
  file), so a genuine LATE drift can never be skipped away as warmup. It reports drift; it does not fix
  it (a real logic change is still a hand port, per drift). Run it after any `mpc_assistant.pine` /
  `mpc_strategy.pine` / `mpc_b_leg_strategy.pine` re-paste + re-export. Stdlib only.
  `verify_parity.py <csv> [csv ...]`, or no args = newest CSV in `backtest/`.
  Each registry row carries a MARKER column and a **VETO** column (added 2026-07-26): a check runs
  when its marker is present and its veto is absent. The veto exists because the two STRATEGY exports
  overlap — `mpc_b_leg_strategy_export.pine` plots `px_stages` too (the B leg arms off the A+
  sequence), so marker-alone would run the A+ check against a B-LEG export and produce a red that
  means nothing. `bl_bits` exists only in the B-LEG export, so it is the A+ check's veto and the
  B-LEG check's marker. Deliberately NOT solved by re-marking A+ on an A+-only column like
  `px_block`: that column landed 2026-07-25, so every older A+ export would silently stop being
  checked.
- **`tools/run_report.py`** — the "WHY did it make/lose money" run. Replays a `strategies/python/`
  bot over YEARS of broker bars and writes `trades.csv` (one row per trade, tagged with the
  `engines/regime/` label at entry, NY session/hour, and excursion in R) plus `setups.csv` (one row
  per A+ leg that reached SOS, traded or not, with the FIRST thing that stopped it). The second file
  is the point: a blocked or skipped setup places no order, so it leaves NO trace in any broker trade
  list — this is the only place it is countable. Reports in **R, never dollars** (a fixed-%-risk
  strategy earns exponentially more dollars at the same edge, so a dollar curve makes a flat early
  year look like a broken edge). `--set FIELD=VALUE` overrides any config field for A/B tests
  (frozen dataclass, applied via `replace`); `--no-regime` skips the tagging. Everything it adds is
  reporting-only — no tag feeds back into the strategy, so results are identical with or without it.
  Carries the timeframe-substitution guard described under *history depth* below.
  **`--start` defaults to the MEASURED floor** (`_default_start` → `history.floor_for`), fixed
  2026-07-29. It had been hardcoded to `2022-01-01` while the help text claimed "broker's earliest",
  so every default run silently reported 4.6 of the available 7.9 years — the quiet direction of the
  substitution trap: nothing errors, the equity curve looks fine, and the run just answers a
  narrower question than the one asked. When the agent is down the broker cannot be identified, so
  it refuses and asks for an explicit `--start` rather than guess. **Same rule as everywhere else in
  this package: never type a history depth, measure it.**
- **`archive/`** — committed, frozen `run_report.py` output. `backtest/reports/` is git-ignored
  per-run scratch, which meant multi-year trade data existed only on the machine with a warm cache
  and a live agent; `archive/<date>_<symbol>_<tf>_<scope>/` is the copy that travels with a clone, so
  someone with no VPS and no MT5 can still analyse real trades. It is a SNAPSHOT, not a build
  artefact — nothing regenerates it, so any config change makes it stale. Each folder carries a
  README stating the window, fill model, config levers at run time, and open caveats; keep that
  honest or the numbers get quoted without them. Current: `2026-07-29_xauusd_15m_full_history/`
  (A+ and B-LEG, 2018-09-13 → 2026-07-29, bar fills).
- **`tools/overlap_audit.py`** — do two strategies actually trade DIFFERENT legs of the move? Replays
  two `strategies/python/` bots over ONE bar frame and reports the bars both held a position (split
  same-side vs opposite), which trades pair up, how far apart same-direction ENTRIES land (the direct
  test of "both fired on one structure break"), what a single account would have carried, and the
  monthly R correlation. **Built 2026-08-04 to close the standing A+/B-LEG overlap question**, which
  had been design intent in three CLAUDE.md files for a year and never measured; it passed —
  27 shared bars in 155,453, one same-direction cluster in 6.5 years. ⚠ **It deliberately does NOT
  net the two into a combined equity curve**: both bots are `self_sizing`, so running them on one
  account changes both bots' sizes from the first shared trade and the result is a third thing
  neither bot is. That question belongs to the unbuilt allocator (G10); this tool measures how often
  the allocator would have had anything to arbitrate. ⚠ **Re-run it after any entry-logic change on
  either bot** — the output is a fact about today's config. The bar arithmetic is unit-tested
  (`tests/test_overlap_audit.py`), because a slip in it would report "the legs never overlap" exactly
  as cleanly as the truth does.
- **`tools/jitter_audit.py`** — how much of a backtest survives a few cents of feed difference?
  Replays a `strategies/python/` bot over the same bars N times with a small random offset added to
  each BAR's four prices, and classifies every jittered trade against the baseline: **flipped** (the
  entry moved further than the noise can account for — a `exec_fib_nearest` rung change),
  **retimed** (same setup, filled within 16 bars), **lost** / **gained** (no twin at all), and
  **shifted** (moved by about the noise, which is expected). **Built 2026-08-05 to close G17**, the
  half of the shadow-diff finding that one live window could not answer. ⚠ **The offset varies per
  BAR and is applied to all four prices at once** — a constant offset translates the whole fib ladder
  and flips nothing, and independent per-price noise builds candles no feed can produce. ⚠ **The flip
  threshold is `2 * amp`, derived from the noise rather than picked.** ⚠ **`--amp` defaults to the
  MEASURED broker gap** (0.05; the shadow diff found Vantage above PU Prime by 0.04–0.05 on every one
  of 148 live bars), not a round number — raising it measures a broker nobody trades. ⚠ **Read the
  spread across seeds, never one seed**: the answer is a distribution, and a single jittered run is
  one draw from it. The classification is unit-tested (`tests/test_jitter_audit.py`) because a slip
  in it would report "the trade list is perfectly stable" exactly as cleanly as the truth would.
- **`tools/compare_feeds.py`** — feed-parity check: MT5 pull vs a TradingView export of the same
  symbol/TF/window. Reports **clock offset** (0 = aligned; non-zero = the broker-server-time bug
  that shifts every session — fix before demo), coverage, and OHLC drift. This is *data* parity, not
  *logic* parity (that's the strategy's `compare_strategy.py`) — MT5 and TradingView are different
  feeds and never match exactly; the tool measures the gap. **Not a per-backtest check.** Run it:
  once as a baseline, whenever the agent's time handling or the broker/terminal changes, at the start
  of each demo campaign then ~monthly, and any time trades look off vs the chart. Needs the MT5 agent
  + tunnel; the alignment math is unit-tested offline. Full rationale + cadence: `docs/MPC_SOS_FADE_BUILD_PLAN.md`.

- **`tools/trigger_edge.py`** — **does a TRIGGER carry edge, before any strategy is built?** Added
  2026-08-06 to answer "which of the two continuation setups is worth pursuing" when NEITHER has a
  Python port, so neither could reach `optimizer.py`. It replays the canonical `market_structure` +
  `vwap` engines, finds the bar a trigger would actually be IN on, and asks only whether price reaches
  `+NR` before `-1R`. No sizing, no ladder, no costs; R is each trigger's own structural stop.
  🔴 **THE CONTROL IS THE TOOL.** Gold went 1,200 → 4,300 across the cached window, so a long-side
  "edge" is free and any harness without a control will find one. Every set is scored against random
  entries **matched on direction AND stop distance**, and the control landing on the theoretical
  breakeven with expectancy ~0.000 is what certifies the harness before any result is read off it.
  **If you add a trigger here, add its control in the same commit.**
  ✅ **Findings 2026-08-06** (186,384 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-07): the with-trend
  BOS → 0.5 retrace trigger is **+4.4% over control (+2.5σ, n=778)**; adding the **pro-trend session
  VWAP side** takes it to **+6.8% (+2.8σ, n=404)** with the median stop **38% tighter** (1.80 → 1.11
  ATR); the D strategy's counter-SOS → VWAP-reclaim trigger is **−0.4% (−0.3σ, n=833)**, i.e.
  indistinguishable from random, and goes significantly negative at long targets (−2.8%, −2.1σ at 4R).
  That is what put VWAP into `mpc_bos_strategy.pine` (F10) rather than leaving it in the D file.
  ⚠ **It measures SKELETONS, not the shipped strategies** — no FVG requirement, no Sniper Zone, no
  session filter, no min-stop guard, no real exit ladder. A result here is a prior for a TRIGGER,
  never a strategy's own number.
  🔴 **The look-ahead trap it already fell into, recorded because the symptom was being TOO GOOD
  rather than erroring:** reading the VWAP side off the close of the bar its limit FILLS on selects
  bars that recovered by their close, and reported the filter at **+15.9% / +5.0σ**; reading the
  PREVIOUS closed bar gives +6.8%. **Anything evaluated on the bar it acts on is look-ahead until
  proven otherwise** — see `prev_side`.
  ⚠ **It drops the coarse head of the cache before measuring.** `XAUUSD__M15.csv` opens with
  HOURLY bars — MT5 serving coarser data where it has no M15 history, exactly the silent-substitution
  trap this file documents below — so `drop_coarse()` keeps only the contiguous tail whose median
  spacing really is 15 minutes. Measuring the raw file would score eight years of one trigger against
  a different bar size.
  ⚠ **Stdlib only, on purpose** — it drives the engines directly and needs no pandas, so it runs on a
  bare interpreter. Run it: `python3 backtest/tools/trigger_edge.py` (~5s).

- **`tools/bos_sweep.py`** — 🔴 **DO NOT QUOTE ITS NUMBERS. FALSIFIED 2026-08-07, the day it was
  written.** On the same symbol, timeframe and window, with the config confirmed identical by the
  Pine's own `[CFG]` echo, this tool reports **20 trades / 80% win / PF 2.97 / +102.5%** where the
  TradingView Strategy Tester reports **24 trades / 66.67% win / PF 1.043 / +5.01%**. The Tester is
  the ground truth. **Entries roughly agree; the EXIT LADDER does not** — this model extracts far
  more from its winners than the Pine does. It is kept because its METHOD is sound and reusable
  (matched drawdown budgets, paired jitter, resolvable-stop screening, matched random controls) and
  because fixing it is cheaper than rewriting it. **Every result must be treated as unverified
  until `compare_bos.py` is green.** See `docs/MPC_BOS_OPTIMIZATION.md` → Run 8.
  ⚠ **Its own docstring warned it was a model rather than the strategy, and that was not enough** —
  a table of numbers reads as a finding whatever caveat sits under it. The check that falsified it
  was ONE Strategy Tester run, available the entire day it went unrun.
  Added 2026-08-07; it chose that file's current defaults (Run 7 in `docs/MPC_BOS_OPTIMIZATION.md`), and it
  exists so that answer is reproducible rather than asserted. Stdlib only, same as `trigger_edge.py`,
  and it reuses that tool's `drop_coarse()` reasoning. Modes: `sensitivity` (one lever at a time),
  `frontier` (the cartesian, ranked at a matched drawdown budget), `settle` (paired jitter
  head-to-head). ~35,000 configurations over 186,384 M15 bars; `frontier` takes ~40s on 12 cores.
  ⚠ **It models ONE POSITION SLOT, because the Pine is a `strategy()`.** Scoring setups
  independently counts trades the strategy could never have taken and lets a winner and the trade it
  would have blocked BOTH score — the queue effect this repo has now measured three times, and twice
  the cheap estimate had the SIGN wrong.
  ⚠ **It charges spread AND swap per night held**, and swap keeps MT5's sign, so gold's short-side
  CREDIT stays a credit. A strategy that holds overnight cannot be ranked without it.
  🔴 **Its load-bearing output is not the R column — it is the TIGHTEST-TENTH STOP printed beside
  every row.** R = profit / stop, so a stop model that produces small stops inflates every R in the
  book without one extra dollar being made. The first leaderboard this tool ever produced was
  entirely configurations with a **median 74-cent stop** reading +250R to +450R, on an instrument
  whose spread is $0.22 — numbers a 15-minute bar cannot even resolve, since inside one bar price
  crosses that spread constantly. **Ranking on R alone cannot see this. Never rank a stop model on R.**
  ⚠ **Configurations are compared at a MATCHED DRAWDOWN BUDGET** (`risk_for_dd`), not at equal risk:
  summing R treats a 25R drawdown as three times worse than an 8R one, when at 10% risk it is the
  difference between giving back 30% and giving back 93%. It is the only way a 55-trade book and a
  600-trade one can be ranked together.
  ⚠ **That budget metric is NOISY — a factor of two across jitter seeds on one configuration** — so
  `settle` scores every finalist on the SAME jittered series and compares pairwise. Unpaired medians
  had the old and new defaults tied (42.8x vs 42.3x) purely because the real price series is unlucky
  for one and lucky for the other; pairing separated them 32-8.
  ⚠ **Two look-ahead traps are deliberately avoided and both were made and caught here**: the VWAP
  side is read off the PREVIOUS closed bar (reading it off the fill bar's own close selects bars that
  recovered — worth a fake +9%), and the FILL BAR MAY NOT STAGE THE STOP, which is
  `BUG_exit_fill_price_mismatch`.
  ⚠ **It is a MODEL of the Pine, not the Pine.** No `compare_bos.py` exists yet, so nothing here has
  been diffed against the strategy's own decision stream. Read its results as a strong prior.

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
  `update_stop`, a `contention` log stamped with `now`. **`SoloAccount`** = one leg, no cap, always
  full size = standalone behaviour, and the parity anchor.
- **`clock.py`** — `merge_streams`: k-way merge of the legs' bar streams into time-ordered `Tick`s,
  co-timed bars grouped, stable leg order.
- **`simulator.py`** — `simulate(legs, account)`: steps the legs on the clock, orders
  **holders-before-flat legs** each tick so freed room is released before entries (release-before-entry
  without splitting the strategy's monolithic step), returns combined + per-leg trades + contention log.
  **v1 limit:** two flat legs filling on the EXACT same tick are first-come, not split-by-weight (the
  weighted split needs the strategy step split into decide/commit; `request_fills` is ready for it).

The strategy seam lives in the strategy (`mpc_sos_fade/execution.py` takes an injected `account`,
default `SoloAccount`) — see that package's CLAUDE.md. `compare_strategy.py` staying exit 0 with the
SoloAccount is the gate that the seam didn't move standalone behaviour.

## Data layer (A0) — how it works

`backtest.data.BarSource.load(symbol, timeframe, start_date, end_date)` is the one entry point:
1. `resolve_base_tf` picks the base timeframe to pull — the target itself if the broker serves it
   (M1/M5/M15/M30/H1/H4/D1), else the largest served timeframe that divides it.
2. Base bars are served cache-first (`BarCache`, one CSV per symbol+tf under `backtest/cache/`,
   git-ignored). A miss fetches the whole window from the MT5 agent (`Mt5Agent`, HTTP on
   localhost:8766 via the SSH tunnel) and records the fetched date range (`RangeCoverage`).
   ⚠ **This hop is why a running PYTHON job counts as MT5 traffic to the command center's agent
   supervisor** (`command-center/backend/services/agent_supervisor.py`, 2026-08-02): a python
   backtest runs locally and touches no VPS terminal, but a cache MISS pulls its bars through this
   tunnel, so restarting the tunnel or the MT5 agent mid-fetch kills the run. If the data layer ever
   stops going through the agent, that coupling in the supervisor goes stale — change both.
   The corollary is the good news: a fully CACHED window needs neither the tunnel nor the agent, so
   a replay over bars already on disk is unaffected by anything on the VPS.
3. `resample_up` aggregates to the target timeframe if base ≠ target — **never down**.
4. The result is sliced to `[start_date, end_date]` inclusive.

**One request can't exceed the terminal's bar cap — `Mt5Agent.bars()` chunks.** Past
"Max bars in chart" (the classic 65,000) MT5 does not clamp or answer partially: it fails the whole
call with `(-2, 'Terminal: Invalid params')`, which reaches the client as a bare 404 "no data" —
indistinguishable from a symbol with no history. Measured 2026-07-21 on XAUUSD.s M15: 64,837 bars
fine, ~70,000 (3 years) dead, so a 3-year backtest could not load bars at all. `bars()` now splits
any long window into chunks sized from the timeframe against a 24h day (`_MAX_BARS_PER_REQUEST`
60,000), fetches each, and stitches them (dropping the shared boundary bar). A window already small
enough still makes exactly one call. (The terminal's own "Max bars in chart" was later set to
unlimited — see *history depth* below — but the per-request chunking stays: it is what makes a
multi-year window loadable at all, and it must not depend on a terminal setting nobody can see from
here.) **An empty chunk is not an error when others returned data** —
broker history starts somewhere, so a 3-year request against a shallower symbol now returns the
history that exists instead of failing; only "no chunk served anything" raises. `_read_error` also
surfaces the agent's `mt5_error`, which is what distinguishes the two cases.

**Backtest broker = Vantage demo (backtest-ONLY; live trading is always PU Prime).** Chosen so bar +
tick data match the `VANTAGE_XAUUSD` TradingView feed the strategies are designed against. MT5_Lab is
logged into the Vantage demo (account 25815745, `VantageMarkets-Demo`); **gold symbol is `XAUUSD`, no
`.s` suffix** (that was PU Prime). See `algos/CLAUDE.md` for the MT5_Lab pin.

**Don't hand-feed broker facts — pull them.** The agent has two read-only endpoints that read the live
terminal so spread/commission/swap/symbol and history depth never have to be typed in:
- `GET /symbol_info?symbol=XAUUSD` → digits, point, contract size, volume steps, live spread, and
  swap long/short straight off the symbol Specification. This is how `backtest/fills.py`'s
  `vantage_demo` profile was built (2026-07-22): **commission 0.00** (it is a demo — demos never
  charge), swap **−74.84 long / +26.98 short**, triple-swap Wednesday. Spread is NOT stored — it is
  measured live from the Vantage bid/ask tick stream.
- `GET /data_availability?symbol=XAUUSD&timeframes=M1,M5,M15,M30,H1,H4` → earliest→latest served bar
  per timeframe (cheap: one bar from each end).

## History floors — MEASURED per broker, and ENFORCED (`data/history.py`)

**The floor is discovered, never hardcoded.** `HistoryFloors.floor(symbol, tf)` binary-searches the
live terminal for the earliest date with real bars and caches it keyed on
`(server, symbol, timeframe)`, where `server` is the agent's `/status` server name
(`VantageMarkets-Demo`). Point MT5_Lab at a broker with deeper history and the floor widens on its
own; point it at a shallower one and it tightens. A hardcoded date would fail in both directions —
needlessly truncating the deep broker, and fictionalising the shallow one.

Probing asks one question per candidate day — *"does this day return a plausible number of bars for
this timeframe?"* — because **bar density is the one thing that cannot lie** (see the substitution
table below). Two phases, deliberately with opposite error tolerances: a holiday-tolerant cluster
test for the binary search (a false "no data" on a single holiday would push the floor years late),
then a strict single-day forward scan to remove the early bias that tolerance creates. ~25 HTTP calls,
once per (broker, symbol, timeframe), then cached to `backtest/cache/history_floors.json`.
`refresh=True` re-probes (use after a broker back-fills).

**Two independent defences, both required:**
1. `HistoryFloors.assert_window()` — the measured floor, checked in `BarSource.load` **before any
   fetch**. Also read by the lab API so a user is stopped at the date picker, not 40 minutes into a run.
2. `assert_bar_spacing()` — pure, empirical, on what actually came back: the frame's MODAL gap must
   equal the requested timeframe. Backstop for an unprobed symbol, an unreachable agent, and the day a
   broker's depth shifts. Checked at the BASE timeframe, because resampling up would smooth a
   substitution into a plausible-looking frame.

**`floor()` returning `None` means UNKNOWN, never "unlimited"** — an unreachable agent, or a broker we
cannot identify. Nothing is refused on a guess; the spacing backstop still applies. The `_SEED`
fallback is tagged with the server it was measured on and is applied **only** to that broker.

**Enforcement points.** `BarSource.load` (every consumer — lab, optimizer, CLI) plus a 400 at each lab
trigger: `POST /backtests/run`, `POST /runs/{id}/retry` (period override), `POST /backtests/sweep`,
`POST /optimizations/run`, `POST /backtests/stacks`. Only the **python** runner is bounded —
NT8 and MT5 pull history from their own terminals, so their depth is a different question and claiming
a Vantage gold floor there would be a lie in the more dangerous direction.

**UI.** `GET /backtests/history-limit?instrument=&bar_type=&bar_value=&runner=` → `HistoryLimit`
(`earliest_date`, `broker`, `verified`, `source: probed|seed`, `note`) or `null` when unbounded.
`useHistoryLimit` feeds `PeriodPicker`, which sets `min` on both date inputs, **clamps the 1Y/3Y/5Y
presets** to the floor (so "5Y" on a 4-year broker asks for what exists), makes "All" mean *all there
is*, and shows a one-click "Start at <date>" fix — a native `min` stops the calendar but not a typed
or pasted date. `source: "seed"` renders as "last known — terminal unreachable" so a fallback is never
mistaken for a measurement. Tests: `backtest/tests/test_history.py` (20) — a fake agent with a settable
history start exercises the real probe, including deeper-broker, shallower-broker, and
broker-swap-does-not-inherit.

## Vantage XAUUSD history depth — and the silent-substitution trap

**MT5 does NOT error when a symbol has no history at the requested timeframe. It returns the nearest
COARSER timeframe's bars, still labelled as what you asked for.** This is the single most dangerous
behaviour in the data layer: a backtest fed daily bars as 15m does not crash — it produces a full
trade list, a clean equity curve, and a completely fictional answer. Verified 2026-07-26 on Vantage
XAUUSD by asking for one month (January 2010) at four timeframes:

| asked | bars returned | real count would be |
|---|---|---|
| M1  | 21 | ~29,000 |
| M15 | 21 | ~1,900 |
| H1  | 21 | ~480 |
| D1  | 21 | 21 ← the bars all four actually served |

21 = the trading days in that month. Every intraday request was handed D1. Single-day probes show the
same thing one level up: on 2018-09-11, M1/M5/M15/M30 each return an identical 23 bars of $1.88 median
range — H1 data, served four ways.

**Real depth (density-verified 2026-07-26, AFTER "Max bars in chart" was set to unlimited).** These
are a SNAPSHOT for orientation — the code probes rather than reading them, so do not treat them as the
contract:

| timeframe | real history starts | bars available |
|---|---|---|
| M1 · M5 · M30 · H1 · H4 | **2018-09-14** | ~2.8M / 570k / 95k / 47k / 12k |
| M15 | **2018-09-13** (probe; a partial 38-bar first day) | ~190k |
| D1 | 2007-06-21 | ~4,700 |

Every INTRADAY timeframe shares one floor — Vantage's gold intraday start. That common date is itself
the proof no bar cap is in play: a cap would exhaust M1 ~15× sooner than M15, and it does not.
**~7.9 years is the hard ceiling for any intraday backtest on this broker**; no MT5 setting moves it
(only a different broker or a paid feed would).

Note M15 starts one day earlier than hand-sampling found: the automated probe caught 2018-09-13 (38
real bars, $1.24 median range — history begins mid-day) where manual day-picking had tested 09-12 and
09-14 and missed the Thursday between. The `_SEED` fallback deliberately carries the LATER 2018-09-14
for all intraday: refusing one extra day costs nothing, allowing one day too early is the failure this
whole section exists to prevent.

**`GET /data_availability` CANNOT be trusted for depth.** It samples one bar from each end, so the
substitution above fools it completely — on 2026-07-26 it reported `earliest 2007-06-22` for **every**
timeframe including M1, which is false by ~11 years. The two previous depth figures in this file
(2026-07-21, 2026-07-22: "M1 from 2026-04-13", "M30/H1/H4 from 2007") came from that endpoint and were
wrong for the same reason. **Verify depth by BAR DENSITY — count bars per day and compare against the
timeframe's expected count — never by the earliest timestamp.**

**"Max bars in chart" must be unlimited in the MT5_Lab terminal.** Before it was raised (2026-07-25)
every timeframe capped at ~100,000 bars, which is 4.2 years on M15 but only ~3.5 months on M1 — the
old "M1 from 2026-04-13" reading was that cap, not the broker's history. Tools → Options → Charts.

**The guard now lives in the DATA LAYER, so every consumer inherits it** — `BarSource.load` calls both
`assert_window` and `assert_bar_spacing` (see *History floors* above), which closes the earlier gap
where only `run_report.py` was protected and the lab/optimizer were exposed. Verified firing: asking
for 15m over 2015 raises `HistoryFloorError: … most common spacing in the returned data is 1440m`.
`run_report.py` keeps its own copy of the spacing check so it fails with a CLI-shaped message before
loading, which is redundant by design — a duplicated refusal is cheap, a missed one is not.

**Cache isolation is by SYMBOL name, not broker** — files are keyed `(symbol, tf)` with no broker tag,
so Vantage `XAUUSD__*.csv` and any PU Prime `XAUUSD_s__*.csv` are naturally separate. The trap: if a
config still asked for `XAUUSD.s` the agent's suffix-strip fallback would pull Vantage bars and cache
them under the `.s` key — mixing brokers. The stale PU Prime cache was cleared 2026-07-22 and the
strategy default symbol is now `XAUUSD`, closing that path.

The agent's `/ticks` endpoint landed with A2; `Mt5Agent.ticks()` reads it, and `backtest/data/ticks.py`
caches by hour. Pull the SMALLEST window that answers the question — gold is ~690k ticks/day (~43MB,
~90s), while one 5m bar is ~260KB and under a second.

## Rules

- **An engine input the decision stream does not export is a silent parity trap.** `EngineConfig`
  carries the engine-construction knobs, and a consumer replaying a specific Pine must pin every one
  that Pine does not leave at the engine's default — `EngineConfig`'s own defaults cannot be right for
  everyone, because the Pine files disagree with each other. Live example (caught 2026-07-26):
  `fvg_require_close` defaults **False** here, mirroring `mpc_assistant.pine` where it is an input and
  is off; but `mpc_strategy.pine` HARDCODES the check, so `mpc_sos_fade` pins it True. Unpinned, the
  engine created gaps that Pine never did and produced a phantom entry edge — invisible to
  `compare_strategy.py` until a fresh export happened to disagree, ~8 days after the engine made the
  gate optional. **When an engine default changes, audit every `engine_config()` that replays a Pine
  which does not share the new default.**
  **Second live example, and the nastier direction (caught 2026-07-31): the trap also fires on an input
  a consumer FORGOT to pin.** `EngineConfig` carried `fvg_max_count = 6` / `fvg_threshold_pct = 0.1`,
  two generations stale, and this file said so — flagged as harmless because "every real consumer pins
  its own". **That was half wrong.** `mpc_sos_fade` pinned `fvg_max_count` and `fvg_require_close` and
  never pinned `fvg_threshold_pct`, so it was silently inheriting the 0.1 — which happens to equal
  `mpc_strategy.pine`'s 15m floor, so the bot worked by coincidence rather than by decision. Anyone
  reconciling that "stale" default to the engine's would have moved the A+ bot's trades with **no test
  failing**. Verified by doing exactly that: `compare_strategy.py` failed on the first compared bar
  (`px_edge` py=3478.99 vs pine=3475.43). Fixed the right way round — **`EngineConfig` carries ENGINE
  defaults (8 / 0.0), each strategy pins what its own Pine uses**, and
  `test_engine_config_pins_every_input_the_pine_moved_off_its_default` now asserts all four pins so the
  shared default is free to move again. **Corollary: never "tidy" an `EngineConfig` default without
  first checking which consumers read it unpinned — a stale-looking default may be load-bearing.**
- **Never build a second copy of a canonical engine here.** This package *replays* `engines/`; it
  imports them, it does not reimplement structure/fib/fvg/rsi/liquidity/sessions detection.
- **Every write to `backtest/cache/` goes through `data/atomic.py`** — `atomic_write_*` for the
  bytes, `cache_lock(dir, symbol, tf)` around any read-modify-write. Both, never one: atomicity
  stops a torn file, the lock stops a lost update, and the lost update is the silent one. A new
  sidecar written with a plain `write_text` is a new hole of exactly the shape that destroyed the
  M1 and M15 caches on 2026-08-06. ⚠ **If a write and the record that DESCRIBES it are separate
  calls, hold one lock across both** — the invariant is that coverage never claims more than the
  bars on disk, and two individually-atomic writes leave a window where it does.
- **Resample only ever UP.** Building a lower timeframe from a higher one invents intrabar path —
  forbidden. Pull a smaller base instead, or use ticks.
- **Stdlib + pandas only** in the data layer (no parquet/pyarrow — the environment lacks it; CSV is
  the cache format). Keep the package dependency-light so it imports anywhere.
- **The cache is git-ignored broker data** — never commit anything under `backtest/cache/`.
- **Tests run offline.** Network (the MT5 agent) is injected, so tests use a fake. Run:
  `command-center/backend/.venv/bin/python -m pytest backtest/tests/ -q`.
- **Bars are UTC**, timestamped at the bar OPEN (matching MT5), columns open/high/low/close plus
  an OPTIONAL `volume`. This line said "no volume (the A+ engines don't need it)" until
  2026-08-07 and was two generations stale: the data layer has carried volume since the
  2026-08-06 `FEED_VERSION` 3 pass, and `ReplayBar` carries it from 2026-08-07 for
  `strategies/python/mpc_bos/`, the first strategy that needs it (its session-VWAP filter).
  ⚠ **`ReplayBar.volume` is `Optional[float]` and `None` means THE FEED CARRIED NONE — never
  0.0.** A zero-volume bar is a real thing MT5 reports on a dead session, so filling the unknown
  with one puts a measurement where there is none, and a volume-weighted consumer averages
  straight through it without complaining. A NaN cell (one unknown bar inside an otherwise
  populated column) is `None` for the same reason. The A+ and B-LEG paths never read it, so
  their replays are byte-identical.

## Reading the numbers — two standing caveats

- **Annualized Sharpe is inflated across ALL runners (NT8/MT5/Python).** `output.py:build_daily_pnl`
  records only days that had a closed trade; flat days are deliberately absent (the trailing-drawdown
  engine walks the days that exist). `metrics.daily_sharpe` then annualizes those active days ×√252,
  as if every day looked like an active one. On a 22-trade / ~225-day run the shipped figure was
  **7.80** vs a true **~2.2** when every weekday is zero-filled (monthly-%, daily-%, and dollar
  variants all cluster ~2.0–2.6 — that cluster is the tell). KNOWN + MEASURED, deliberately NOT fixed
  (fixing it re-scores every historical run — Aaron's call). Treat Sharpe as a *relative* ranking
  between our own runs only; never quote it as an absolute, and never compare it raw to TradingView's.
  If ever fixed, build a separate zero-filled series for the Sharpe calc — do NOT change `daily_pnl`
  itself (the trailing-drawdown engine depends on the absent flat days).
- **Reconciling with TradingView's Strategy Tester — two conventions differ, both expected.**
  (1) TV counts each TP-ladder exit as its own closed trade, so it reports ~3× our position count
  (66 TV "trades" = our 22 positions; win RATE matches to 4 s.f. — compare the rate, never raw counts).
  (2) TV's Sharpe is a RAW MONTHLY figure — multiply by √12 (≈3.464) before comparing to our
  annualized daily one. Normalize for both before calling any TV-vs-lab gap a bug; `verify_parity.py`
  proves the SIGNALS match bar-for-bar, it does not make the two summary reports directly comparable.
- **If a real backtest must be run, the MT5 runner is much faster than NT8** (NT8's Strategy Analyzer
  is driven by slow pywinauto UI automation). Prefer an MT5-runner strategy/symbol when the goal allows.
