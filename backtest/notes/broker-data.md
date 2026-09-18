# Notes — Broker identity, symbols and the bar cache

How a profile states its broker's symbol spelling and login, why the bar cache is partitioned by broker server, and the Vantage XAUUSD history-depth trap. Moved VERBATIM out of `backtest/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## A profile also states how its broker SPELLS a symbol (2026-08-26)

`AccountProfile.symbol_suffix` — `".p"`, `".s"`, or `""` for a broker quoting bare names. Identity,
never a cost. MEASURED 2026-08-08 across three PU Prime logins and re-confirmed on the ECN terminal
2026-08-26: **the suffix IS the tier, and neither account can see the other's symbol.**

- ⚠ **Three-state, and `None` means nobody recorded it** — not "bare". A caller must leave the
  symbol alone and say so. PU Prime Cent is `None`; nobody has logged into it, and `XAUUSD.crp` in
  another account's Market Watch is not evidence of what Cent quotes.
- ⚠ **Nothing in this package rebases anything.** The field is data; the lab resolves it at run
  creation (`command-center/backend` → *The BROKER spells the symbol*), reusing the live side's one
  rebase rather than adding a second.
- 🔴 This is the missing half of the partition below: the cache learned WHICH broker's bars it
  holds, and this is the broker saying what it calls them. A run that asks for a symbol the
  terminal does not quote gets the same empty frame a closed market returns — rule 2, one level
  down.

## Standard and Prime record their LOGINS (2026-08-26)

`account` was blank on both, so a lab pointed at either could not be confirmed as the attached
terminal and the page said *"cannot tell which terminal is connected"* about a terminal it could
name exactly. **They were never unknown** — MT5_Lab was signed into all three PU Prime demos in
turn on 2026-08-08 to measure their swaps and symbols, and that block names every login.

- 🔴 **The ACCOUNT is the only thing that separates these tiers** — all three live on
  `PUPrime-Demo`, and their spreads are 2.7x apart.
- ⚠ **Cent stays blank and that is the field WORKING.** Nobody has logged into it, so the lab will
  honestly say it cannot tell rather than blessing a tier.

## 🔴 The cache is partitioned by BROKER SERVER (2026-08-24)

**The filename was `(symbol, timeframe)` with no broker in it, for as long as the cache existed.**
That was survivable only because exactly one terminal ever filled it — every one of the 12 probed
history floors on this machine reads `VantageMarkets-Demo`, so nothing was ever mixed. It stopped
being survivable the moment the lab gained a reason to point at a second broker: **the second
broker would have read the first one's bars and been charged its own costs**, and there is nothing
in a trade list, an equity curve or a metrics panel that could show you that. The two feeds here
are MEASURED to differ by a systematic 4-5 cents on every bar (2026-08-04 shadow diff), so the
result would have been wrong by a real amount while looking completely normal.

Bars and ticks now live under `backtest/cache/<server>/`. ⚠ **Keyed on the SERVER, not the account
tier, and that is measured rather than tidy** — MT5 keys its own store by server, so PU Prime's
Prime and ECN logins (both `PUPrime-Demo`) genuinely share one history, and partitioning per tier
would triple a 1.28 GB download for byte-identical bars. **Costs are what differ per tier**, and
they are charged from `fills.PROFILES`, never from the cache.

⚠ **An unknown server REFUSES** (`UnknownBrokerError`) rather than falling back to a shared or
`default` folder. That is rule 1 applied to a filesystem path: "cannot ask" must never take the
same value as "the usual broker". An unreachable agent refuses for the same reason.

⚠ **An explicitly injected `BarCache`/`TickCache` is honoured and NOT partitioned.** That is what
every test in this package passes, and it is a deliberate statement about where those bars live.
⚠ **This file said "all 20 production call sites construct `BarSource()` bare, so production
always partitions — checked, not assumed" until 2026-08-25, and it was true when written and stale
within the day.** Seven of them pin a server now (the rerun, the price chart's feed and its
drill-down, the stack runner, the stack backfill); the hand-run tools under `tools/` stay bare on
purpose, because a person invoking one is pointing it at the terminal they have attached. **A count
of call sites is a fact with a shelf life — do not quote this line either, run the search.**

⚠ **Partitioning is LAZY, on the first `load()`.** Construction stays free of network calls, which
is the property `HistoryFloors` already had; a tool that dies while building an object reports the
failure in the wrong place.

🔴 **A RERUN READS THE BROKER THE RUN WAS MADE ON — `BarSource(server=...)`, added 2026-08-24 the
same day and reported from the screen.** Aaron: *"when we click rerun charged it should still rerun
against the broker that the data originated from — otherwise all of my backtests will be broken."*
Exactly right, and the partition is what made it urgent rather than what caused it: **before, the
flat cache served the old broker's bars whatever was attached — wrong, but in the silent
direction; after, an unpinned rerun looks in the ATTACHED broker's folder, misses, and tries to pull
the run's window from a terminal that may not even quote its symbol.** The lab pins it from the
run's own `broker_profile` (`python_runner.bar_server`), so a stored run replays its own history and
only a NEW run follows the attached terminal.

⚠ **The pin is checked at FETCH time, never at partition time**, so a fully cached window still
replays with the terminal unreachable — a property this package already had and the pin must not
cost. ⚠ **A fetch on a mismatched pin REFUSES and names both brokers.** Merging is the failure that
cannot be undone: the file is one CSV per (symbol, timeframe) and **nothing in a bar records which
broker served it**, so a single wrong fetch is permanent and invisible. ⚠ **Serving the short cached
span instead would be worse than the error** — a narrower window than the caller asked for, silently.
⚠ **A profile with no recorded server pins NOTHING rather than guessing one**, which is what every
pre-2026-08-02 row is.

🔴 **THE PIN WAS THREE CALL SITES SHORT FOR A DAY, AND THE PRICE CHART WAS ONE OF THEM (2026-08-25).**
A charged re-run of a Vantage run completed with 247 trades and drew an EMPTY chart, because the
chart's own bar fetch was still bare and resolved the attached terminal. Fixed in
`command-center/backend` (its CLAUDE.md owns the detail); recorded here because the lesson belongs
to the PARTITION rather than to the chart. ⚠ **When a shared store gains a partition, the audit is
every construction of the thing that reads it — not the ones the reported bug happened to touch.**

🔴 **A WRONG-PARTITION READ HAS TWO OUTCOMES AND ONLY ONE OF THEM IS LOUD.** Aaron asked the right
question about that empty chart: *was it drawing PU Prime's prices under my Vantage trades?* It was
not — but the reason is worth writing down, because it is **not** a safeguard. A partition holds one
file per EXACT symbol name, and PU Prime's gold carries a suffix Vantage's does not, so the lookup
found no file, the fetch was refused, and the chart came back blank. **Had both brokers used the
same symbol name and the wrong partition happened to cover the window, it would have served the
other broker's prices with nothing anywhere to flag it** — no error, no empty result, just a chart
and a replay quietly measured on a different market. ⚠ **So the loud failure everybody saw was luck
(a symbol suffix), not design.** The design answer is the pin, and it is why the pin belongs on
every reader rather than on the ones that have been seen to fail.

⚠ **A flat cache from before this change is INVISIBLE, not wrong** — every read is a miss and the
bars come down again from whatever broker is attached. That is the safe direction to fail in, and
it is why there is no automatic migration. To keep the existing 1.28 GB, a human asserts which
broker filled it:

```bash
python backtest/tools/file_cache_by_broker.py --server VantageMarkets-Demo --dry-run
python backtest/tools/file_cache_by_broker.py --server VantageMarkets-Demo
```

**Guessing the server would have written the exact claim the partition exists to prevent** — a
folder labelled with a broker whose prices may never have been in it — so the name is a required
argument. The tool refuses to merge into an existing partition, moves rather than copies (a flat
shadow of a 1 GB tick store is a trap), and COPIES `history_floors.json` because that file is
keyed by server inside and stays valid in both places.

⚠ **PU Prime's recorded M15 floor is WRONG — see the two defects below before trusting it.**

⚠ **PU Prime's history depth is its own fact. It is now partly known and is still NOT a measured
floor** — say the difference out loud rather than letting the next reader read a bound as a bottom.
`XAUUSD.p` M15 is cached from **2019-01-01 23:00 to 2026-08-23 23:45, 180,619 bars with volume**
(pulled 2026-08-24 in ~28s, verified off disk here rather than taken on report). ⚠ **2019-01-01 is
the earliest date anybody ASKED for, so the real floor is at or before it and nobody has looked** —
recording it as the floor would be rule 3 exactly: what you requested written down as what you
received. Vantage gold bottoms out at 2018-09-13 on M15; do not carry that number across either.
The floor probe re-runs per server on its own — that part was already right.

⚠ **Bare `XAUUSD` does not exist on this broker.** PU Prime quotes `XAUUSD.p`, and a request for the
bare symbol returns nothing at any date (checked 2019 and 2024). Eight runs died on it in one
evening before anybody noticed, which is the loud failure working as intended — but every stored run
made against Vantage carries `instrument: XAUUSD`, so a rerun of one on this terminal cannot fetch.

✅ **The migration has RUN on this machine (2026-08-24): 42 entries, 1.28 GB, now under
`cache/VantageMarkets_Demo/`.** That the server name was `VantageMarkets-Demo` is not an assumption —
all 12 probed history floors in `history_floors.json` carry it, so exactly one terminal has ever
filled this cache.

🔴 **The partition SILENTLY SKIPPED four tests and the suite still printed green**, which is the
lesson worth more than the feature. `tests/test_reprice.py` looks for the reference bars at a fixed
path and skips when they are absent — so the moment the files moved, the four slowest and most
load-bearing tests in the package (the real two-year replays that prove re-pricing reproduces a
charged run to the cent) went from passing to SKIPPED with nothing to notice. **A missing file is
indistinguishable from a git-ignored one.** It searches the partitions now.

⚠ **A profile now records the SERVER and ACCOUNT it was measured on** (`fills.py` →
`AccountProfile.server` / `.account`). Identity, never a cost — nothing charges either. They exist
because the partition fixes the BARS and leaves the COSTS free to mismatch: a run can legitimately
replay PU Prime's bars and charge Vantage's spread, which is the same defect one level up. The
Command Center reads them to default its cost account to the attached terminal; rules there.
⚠ **The account is what separates PU Prime's tiers** — Prime and ECN share `PUPrime-Demo`, so a
server-only match would hand a run ECN's $0.12 spread while it sat on Prime.
⚠ **Blank/None means UNRECORDED, never "matches anything".**

⚠ **A floors entry is keyed on the SUFFIX-STRIPPED symbol, by design** (`_key` → `_norm`, which
splits on the dot, because `.s`/`.p`/`.a` are the same underlying instrument's history). So
`PUPrime-Demo|XAUUSD|15` is the record FOR `XAUUSD.p`, not for a bare symbol nobody can fetch.
**An earlier version of this paragraph read it the other way round and reported a phantom defect** —
corrected 2026-08-24 after a peer session checked the code rather than the filename. A probe that
fails writes nothing at all, so an entry can never exist for a symbol returning no data.

🔴 **STILL OPEN, and it is worse than the phantom was: `PUPrime-Demo|XAUUSD|15 → 2018-09-13` is a
GENUINELY BAD FLOOR, and both checks that exist to catch it pass.** That day is HALF SUBSTITUTED —
MEASURED against the live terminal: **2018-09-13 returns 38 bars for an M15 request, with 18 gaps of
60 minutes, one 75-minute seam, then 18 gaps of 15 minutes.** PU Prime's real M15 history starts
partway through that day and everything before the seam is H1 wearing an M15 label. A clean day is
92–96 (2018-10-15 measures 92, with 90 gaps of 15).

Two defects, both reproduced here rather than reasoned about:

1. **`_day_is_real` counts BARS and never looks at their SPACING.** The threshold is
   `_DENSITY_MIN 0.35 × 96 = 33.6`, and 38 clears it. Its docstring's reasoning — *"a coarser
   substitution fails by a factor"* — is sound for a CLEAN substitution (H1-as-M15 is 24/96 = 25%
   and fails) and does not hold for a day that is **half** real.
2. **`assert_bar_spacing` cannot catch it either, which is the surprising half.** Run on that exact
   frame: the gaps tie 18–18, `gaps.mode()` returns `[15, 60]`, `.iloc[0]` takes **15**, modal
   equals requested, and it PASSES. Its `closer` test only hunts gaps SMALLER than the interval —
   there is deliberately no check for a sustained run of LARGER ones, because weekends produce
   those legitimately. ⚠ **Over a LONG window it gets worse, not better**: the modal is dominated
   by the real days and the substituted region never moves it.

✅ **THE DEFECT IS NARROWER THAN "the density check is broken", and this is the part that makes a
future fix SCOPED rather than a risky tightening.** All three cases, arithmetic checked:

| the day | bars of 96 | verdict | right? |
|---|---|---|---|
| entirely H1 substituted | 24 (25%) | fails the 0.35 threshold | ✅ correct, and by a wide margin |
| a short holiday session in clean history | fewer, but correctly SPACED | fails → floor lands LATE | ✅ safe direction |
| **history starts MID-DAY** | **38 (40%)** | **passes** | 🔴 **the only broken case** |

**So the rule is: the check is wrong exactly where a broker's history STARTS PART-WAY THROUGH A
DAY**, and nowhere else. A fix therefore has to catch a frame that is half correctly-spaced without
refusing a genuinely short session — which is why "tighten `_DENSITY_MIN`" is the wrong instinct: it
would push every holiday-adjacent floor later while still passing 38.

⚠ **Impact today is nil and that is not a reason to leave it** — nobody is starting a run there. The
risk is that the recorded floor INVITES someone to start on 2018-09-13 and receive ~18 hourly bars
inside an otherwise clean frame **with no error raised**, which is precisely the fictional-backtest
failure this module's own docstring says it exists to prevent.

⚠ **NOT FIXED HERE, deliberately.** `history.py` is money-path code and a stricter density or
spacing rule can refuse legitimate short sessions and holidays, so it needs its own measurement
across brokers rather than a tightening bolted onto a cache change. ⚠ **Do not paper over it by
deleting the entry** — it re-appears on the next load, and the floor would still be wrong.

Proof: `tests/test_cache_broker_partition.py`, watched RED **by mutation** rather than by revert.
Reverting only produced an ImportError, which proves a symbol is new and nothing about whether the
assertions catch anything. Flattening `broker_cache_dir` in place fails the two data tests on
*"broker B served broker A's cached ticks"*; replacing the refusal with a `default` folder fails
the two refusal tests on DID NOT RAISE.

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

## ⏳ OPEN TASK — adding one day rewrites the whole cache file (2026-09-17)

`BarCache.save` is a read-modify-write of the entire symbol/timeframe CSV, and a window ending today
always has one gap (today is never marked covered, on purpose). **Measured: 26.0s of writing per
page open, 19.2s of it `to_csv`, on one account's two bar loads** — and every backtest, sweep or
chart reaching today pays the same. Not fixed: the honest fix changes how lab prices are stored,
which every backtest depends on. The brief, the measurements, the constraints that may not be traded
away and how to prove a fix: `docs/BAR_CACHE_REWRITE_TASK.md`.

## A history floor at the search bound is a BOUND, not an edge (2026-09-17)

`probe()` starts its binary search at `_SEARCH_FROM` (2000-01-01) and returns that date
immediately when real bars already exist there — the correct answer to "how far back can I go",
but it means *the probe stopped looking*, not *history ends here*.

`describe()` worded both outcomes identically, so it asserted an edge it had never found.
Observed on GBPJPY on 2026-09-17: **"GBPJPY has no real 15-minute bars before 2000-01-01"**,
when the truth is that the probe never reached the earliest bar at all.

That is rule 4 — never write a guessed number into a doc — arriving through a TOOL rather than a
person, which is the harder direction to catch, because the reader has every reason to trust a
measurement and no way to see that this one hit a wall instead.

`describe()` now returns `bounded_by_search`, and the two cases read differently:

- bounded — *"…has real 15-minute bars at least as far back as 2000-01-01 … which is where the
  probe STOPS LOOKING, so the true earliest bar may be earlier. This is a bound, not a measured
  edge."*
- measured — the original wording, unchanged. XAUUSD still reads "no real 15-minute bars before
  2018-09-13", which IS an edge the probe found.

⚠ Two tests, and both were watched RED before the fix went in: the bounded case died on
`KeyError: 'bounded_by_search'`, and the second test exists so the fix cannot pass by wording
EVERY floor as a bound.

⚠ **Anything that raises `_SEARCH_FROM` changes what this flag means.** A probe that started in
1990 would report a real edge for the pairs that currently hit the bound.

## Swap is charged in the SYMBOL'S currency, not the account's (2026-09-17)

`SwapModel.per_lot_per_night` computes `points * contract_size * 10**-digits` and the result lands
in the **quote currency**, not the account's. Every instrument this repo had priced was USD-quoted
against a USD account, so the two were the same thing and nothing here converted — the gap has been
invisible for the life of the project because it has never had a chance to show.

GBPJPY is quoted in yen. MEASURED off PU Prime demo 700152905 on 2026-09-17: swap long **+4.83**,
short **-20.68** points, contract 100,000, digits 3 — so **+483.00 / -2,068.00 JPY** per lot per
night unconverted, against a real **+$3.10 / -$13.25**. **156x, and nothing refuses it**: the
number is the right shape and plainly wrong, which is the dangerous kind.

`AccountProfile.swap_charge` now takes `quote_to_account`, **defaulting to 1.0** so every existing
call site is byte-identical and no stored result moves. The factor to pass is the strategy's
`point_value`: for a pair whose contract is denominated in the BASE currency, one unit through 1.0
of price is exactly one unit of the quote currency, so `point_value` already IS "account currency
per unit of quote currency". Gold's 1.0 says the two currencies are the same; GBPJPY's 0.006409188
is 1/USDJPY.

⚠ **Two tests, the yen one watched RED (483.0 against 3.0956) and the gold one green on both
sides** — the pair exists so a change that fixed the pair while moving gold cannot pass.

⚠ **STILL OPEN: it does not vary with TIME.** `point_value` is a config constant read once, so a
multi-year replay prices every night at one rate. USDJPY ran roughly 100 to 160 across a replayable
window, so a fixed rate is wrong by up to 60% at the ends of it, in a cost that compounds every
night a position is held. The same constant is what sizing divides by, so **it is one fix, not
two**. Deep history exists for the conversion: USDJPY.p serves M15 and D1 back to at least 2000 on
PUPrime-Demo, probed 2026-09-17.

## The conversion is a SERIES, not a number — `data/fx.py` (2026-09-17)

Closes the "does not vary with time" item above.

**Why a series.** A rate is not a constant. MEASURED off `USDJPY.p` daily bars on PUPrime-Demo,
2026-09-17: **108.56** (2020-01-02) → **130.16** (2022-06-01) → **142.00** (2024-01-02) →
**155.10** (2026-09-15). Pricing a six-year replay at one reading is wrong by ~30% at the far
end — in sizing, which divides by the rate, and in every cost, which multiplies by it. The error
is largest exactly where the window is longest, which is where a backtest is most believed.

**Cross-check, two independent sources agreeing.** The broker's own tick value for `GBPJPY.p`
implies USDJPY **156.026** (0.6409188 USD per 0.001 yen on 100,000 units, read 2026-09-17), and
the `USDJPY.p` daily bar for 2026-09-15 reads **155.10**. Different endpoints, different
mechanisms, same answer.

`RateSeries` wraps the conversion pair's bars and hands out a `time_ms -> rate` callable — the
shape `Execution.set_rate_provider` takes. `invert=True` turns a quoted pair into the direction
the account needs (a USD account pricing a yen-quoted symbol holds USDJPY and needs USD-per-JPY).

### The two directions are NOT symmetric, and that is the design

- **Forward across a gap: CARRY.** A weekend has no bars and the rate genuinely did not move for
  anyone holding through it, so the last close is the right answer.
- **Backward before the first bar: REFUSE.** That is extrapolation. A flat rate reached backwards
  is a plausible number, raises no error, and is wrong — which is worse than a stopped run.

⚠ **No bars REFUSES rather than defaulting to 1.0.** A 1.0 fallback would price a yen-quoted
instrument as though it were dollars: the exact bug this module exists to end, reintroduced as a
convenience.

⚠ **A non-positive close is refused at CONSTRUCTION.** Sizing divides by the rate, so a zero is
an infinite position; it dies where the message can name the cause rather than downstream as an
order nobody can explain.

⚠ `constant_rate(1.0)` exists so *"this instrument needs no conversion"* is a thing a caller SAYS
rather than a thing it omits — same reasoning as the cost sentinels in `fills.py`. A silent
absence and a deliberate 1.0 read identically at the call site and mean very different things.

⚠ 13 tests, offline (the source is injected). Three mutations run, each killing exactly one test:
allowing backwards extrapolation, accepting a non-positive close, and accepting an empty series.
