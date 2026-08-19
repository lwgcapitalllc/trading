# CLAUDE.md — strategies/python/mpc_sos_fade/ (the MPC SOS Fade bot)

**Purpose:** The MPC SOS Fade strategy in Python — a line-for-line port of the A+ block +
execution layer in `indicators/strategies/mpc_strategy.pine` (Aaron's brother's "MPC-JARVIS" script). It reads
the canonical engine stack's per-bar output and turns the A+ sequence into trades.
**Scope:** This strategy only — its state machine, order logic, config, and parity harness. It does
NOT own the engines (`engines/`), the replay runner (`backtest/`), or the lab (`command-center/`).
**Status:** Built + unit-tested + **logic-parity GREEN (exit 0) 2026-07-16** on a full-history
`VANTAGE_XAUUSD, 5m` export (20,076 bars, `compare_strategy.py` with no warmup — the export starts at
bar 0). Bar-for-bar identical decision stream vs `mpc_strategy.pine`. Runs real-tick fills + costs
(`fill_model="tick"`), and is registered in the command-center lab as `runner="python"` (see
`LAB_STRATEGY` in `__init__.py`) — risk % is editable in the Run modal. 51 offline tests green.
**RE-VALIDATED GREEN 2026-07-22** after the Pine changed (SOS-aware veto + `execConfSZ` + CONT
removal): the export was regenerated, the veto was ported, and `compare_strategy.py` matches Pine's
decision stream on a fresh 19,863-bar `VANTAGE_XAUUSD, 15m` grand export — every `px_dec_bits` /
`px_stages` / `px_edge` / `px_entry_price` bar-for-bar, one lone 25-cent `px_exit_run` difference on
a single Nov-2025 runner (an intrabar trail-fill guess, not a decision). See `## The 2026-07-22 re-sync`.
**RE-VALIDATED GREEN 2026-07-29** on a fresh 21,494-bar `VANTAGE_XAUUSD, 15m` export taken at the
shipped `exec_tp1_pct = exec_tp2_pct = 0` and carrying the swing ratchet through `cfg_exitmode`/
`cfg_trail_pct` — exit 0 at warmup 100 and at every warmup up to 2000. See
`### PARITY GREEN 2026-07-29`.
**RE-VALIDATED GREEN 2026-08-02** on a fresh 21,710-bar `VANTAGE_XAUUSD, 15m` export carrying the
new ENTRY MODEL through `cfg_bits` (decoded 544375, **bit 524288 set** = rule 3 live on both sides)
— exit 0 at warmups 100 / 500 / 1000 / 2000. That is the run that validates the port; an export
taken before 2026-08-02 has every new bit clear and proves nothing about it.
**RE-RUN GREEN 2026-08-02 after the label/tooltip sync**, on a FRESH 21,715-bar export taken off the
renamed file (2025-08-31 → 2026-08-02, `cfg_bits` 544375) — exit 0 at warmups 100 / 500 / 1000 /
2000. That change touched Pine input TITLES and tooltips, `config.py` comments and one display
string, so a green run on an export from the NEW file is the evidence it was cosmetic, rather than
an argument that it must have been. The same run is the compile proof: a title is a string literal,
so a mangled one fails to compile, it does not quietly change a trade.

### `mpc_sos_fade.meta.json` — labels and descs are SHARED WITH THE PINE (2026-08-02)

🔴 **39 `desc` fields were rewritten to plain English on 2026-08-16, and the trigger was the
PINE side.** Every input tooltip in all 29 Pine files was cut to one or two plain sentences
(rule: `indicators/strategies/CLAUDE.md` → *TOOLTIPS ARE PLAIN ENGLISH*), and because a `desc`
IS that tooltip verbatim, this file had to move with it or the lab panel would have gone on
teaching the old wording. ⚠ **Strings only — every param's `name`, `group`, `core`, `widget`
and `options` is unchanged, verified by diffing and counting the changed lines that do not
contain `"desc"`.** The measured detail those descs used to carry now lives in
`indicators/strategies/docs/mpc_strategy.md` and the specs.



Every `label` in the meta file is byte-identical to that input's title in
`indicators/strategies/mpc_strategy.pine`, minus Pine's leading `   ↳ ` indent marker. Every `desc` is that
input's tooltip **verbatim**. One parameter, one name, one explanation, two UIs.

**Change a label or a desc and change the Pine in the same commit.** Otherwise the lab and
TradingView start teaching different things about the same setting, which is exactly how the
old `exec_deep_fib` row came to be labelled "nearest fib ABOVE" — true for a long, wrong for a
short, and contradicting its own Pine tooltip four inches away.

The ONE allowed deviation is a suffix stating something true only of THIS runner: `exec_conf_sz`
reads "Allow Sniper Zone as entry confirmation **(not supported)**" in the lab, because the
Sniper-Zone entry is Pine-only and turning it on changes nothing on a lab run.

Verify with a diff, not by eye — the check is mechanical: pull every `input.*` title out of the
Pine, join on the field name, and compare. As of 2026-08-02 that is **42 of 43 shared params
identical** and **43 of 43 descs identical**.

⚠ **Rename titles, never reorder an `input.*` call.** TradingView keys a chart's saved input
values off declaration order, so a rename carries Aaron's settings forward and a reorder silently
resets them to defaults on every chart he has the script on.
**Open question — sample size, NOT correctness:** the validated 365d 15m run is only 22 trades (2yr:
40), and the runners alone make >100% of the net in both windows. Read `## The 2026-07-16 year run`
below before trusting any tuning done against it.
which are the two costs bar mode always knew and never billed, and it matters here more than on most
strategies because this runner is DESIGNED to hold overnight (deviation 1). Both come from a broker
profile rather than a typed number, behind layers that are **ALL OFF by default** — the baseline run
stays free so it stays comparable to the TradingView Strategy Tester. **MEASURED over 155,431 M15
bars (2020 → 2026-07-31) at the shipped defaults: free 161 trades / 135.94R / $28.26M · +spread
130.27R / $16.27M · +spread+swap 123.90R / $10.09M · bid/ask fills 159 trades / 141.93R / $29.48M.**
⚠ **A small charge is not a small effect — 12.04R of cost turns $28.3M into $10.1M, 64% of the
balance for 9% of the R**, because at fixed % risk a dollar not earned early never compounds; read a
cost against the R, never the net dollars. ⚠ **The bid/ask row is HIGHER than free, and that is what
a limit-entry strategy does with a spread** — every order here names a PRICE, so the spread moves
fill TIMING and lands almost entirely on SHORTS. Full table, the long-vs-short reasoning and the
"treat it as a lab finding" caveat: *Layered costs* below. ✅ The free path reproduces the documented
161 / +135.94R baseline to the cent and `compare_strategy.py` is exit 0. Earlier the same day:
**every trade now RECORDS the fib leg it was priced off, so the lab
chart can draw the exact ladder the entry, stop and targets came from.** Aaron's brother asked to
see, on each plotted trade, the fib run on the points that trade used — i.e. which retracement
levels it went into. `Trade.fib` (a `TradeFib`: the eight `(ratio, price)` pairs plus the bar the
LEG started on) is snapshotted in `_place_entries` onto `_Pending` and carried through
`_open_position` to the closed `Trade`. **REPORTING ONLY**, the same standing as `mfe_usd` / `tp1` /
`tp2` — nothing reads a ladder back, so no decision can move.
⚠ **It is taken at PLACEMENT and read from the ORDER at the fill, never from `sig` again.** A fib is
live and keeps extending while a limit rests, so re-reading it at the fill would report a leg the
order was never priced against — and the stop and targets on that same trade, which ARE frozen at
placement, would then belong to a different ladder from the one drawn beside them
(`test_the_recorded_fib_is_the_one_the_ORDER_rested_on_not_the_one_at_the_fill`).
⚠ **It is a COPY, not a derivation.** The prices are the `fiboP*` values the strategy had in hand;
nothing downstream recomputes them from anchors. A fib rebuilt in the backend or the browser is a
second claim about one leg, which is the failure this repo has now met four times.
⚠ **Recording is all-or-nothing** — a ladder missing a rung is dropped entirely, because seven
levels drawn where there are eight reads as "this trade had no 0.786" rather than "this record is
incomplete". The **1m secondary** records none by design (it rests at a retrace of its own tight 1m
leg, a different fib). ⚠ **`mpc_bleg` USED to get none for free by overriding `_place_entries`, and
since 2026-08-11 it records its OWN — do not read this section as covering it.** That fork prices
off the frozen SOS leg, not this ladder, so it builds a `TradeFib` from its own band anchors and
under the same all-or-nothing rule; inheriting `_freeze_fib` there would attach a real, fully
populated ladder describing a leg the trade was never priced against. See
`strategies/python/mpc_bleg/CLAUDE.md` → *The recorded fib*.
It needed two fields upstream: `Signals.fibo_ash_ms` / `.fibo_asl_ms`, converted from the fib
engine's new `ash_loc`/`asl_loc` through a bar-index→time table in `SignalAdapter`. ⚠ **Times,
deliberately not bar INDICES** — an index is relative to the window that produced it, and this repo
has already been bitten once by diffing a Pine `bar_index` across two windows (`strategies/CLAUDE.md`
→ the B-LEG harness bug); the chart trims its candles, so only a timestamp survives the trip.
✅ **Proven cosmetic by measurement, not argued:** `compare_strategy.py` **exit 0 at warmups 100 /
500 / 1000 / 2000** on the 21,715-bar `VANTAGE_XAUUSD, 15m` export, `compare_bleg.py` exit 0 at 100
and 800 on the B-LEG export, and the fibonacci engine A/B'd at HEAD vs the working tree over 47,263
real bars with 0 field differences (`engines/fibonacci/CLAUDE.md`). Also validated forward on 23,716
real M15 bars: all 17 trades in 2024 carry a ladder, and their entry ratios independently reproduce
the documented entry model — **0.618 ×5 / 0.702 / 0.786 ×3 exactly on a level (the `_fib_snap`
rules), the rest between levels (gap-edge entries)**, with deepest ratios 0.62–0.98, i.e. never past
the 0.886 stop. 79 tests green here. Earlier the same day: **the 2026-08-02 ENTRY MODEL is ported, and it changes the shipped
default.** Five new config fields, in lockstep with `mpc_strategy.pine`: `exec_fvg_pre_zone` (False),
`exec_fib_overlap` (False), `exec_fib_deep_edge` (False), **`exec_fib_nearest` (True)** and
`exec_sl_deep` (False) — and `exec_deep_fib` flipped **True → False**, because rule 3 replaces it.
⚠ **THAT LAST PAIR MOVES TRADES: the default entry PRICE changed.** Method 3 only ever looked at the
level ABOVE a floating gap, so a gap sitting a hair short of 0.702 was still entered way back at
0.618 (Aaron caught it on the 30 Jul 2026 trade); rule 3 measures BOTH sides and rests on whichever
is closer. Where the deeper level wins, the limit now sits PAST the gap, so it is a deeper entry and
a tighter stop **bought with fill rate** — a setup that only tags the gap and turns no longer fills
at all. **MEASURED on 155,431 cached M15 bars, 2020-01-01 → 2026-07-31: 165 trades / +126.68R
becomes 161 / +135.94R** — the fill-rate cost is real (4 trades gone) and the deeper entries more
than pay for it. That 126.68R baseline reproduces the Pine's own stated figure for the same window
**to the cent**, which is an independent cross-check that this port replays the build the Pine
measurement was taken against. ⚠ **Every other number in this file predates the change.** The rules
CASCADE (`_fib_snap`, Pine `f_fibEntry`):
rule 1 is independent and fires only on a gap whose BODY holds a level; rules 2 / 3 / Method 3 all
answer "where does a FLOATING gap rest?" so each overrides the next. **Every scan stops at 0.786 —
0.886 is the stop, so an entry resting there is a zero stop distance and a cancelled order**, which
is also why no rule here can ever REMOVE a trade. `exec_fvg_pre_zone` needed two new pieces of state
that had no Python home: `Signals.fvgs` is now a **4-tuple carrying each gap's born bar**, and
`Signals.fibo_half_bar` latches the bar price first tagged 0.5 (Pine `fiboHalfBar`, reset with the
leg). It gates **BOTH** gap consumers — the entry-edge loop AND `sequence.py`'s confluence flag —
because a gap the entry may not use must never be reported as the confluence that armed the setup;
add the call to any future reader of `sig.fvgs` or that path becomes a way around the gate.
`_sl_anchor` now takes `(edge, is_bull)` for `exec_sl_deep`, and `_record_blocks` computes it **per
side** rather than once, because the anchor is a function of that side's own entry edge.
⚠ **Two sibling forks had to PIN the old behaviour**, since neither of their Pines has this model:
`BLegConfig` pins all five plus `exec_deep_fib=True` (it does not override `_entry_edges`, and those
edges feed the "A+ has priority" gate, so this is NOT inert there), and `BosConfig` pins
`exec_deep_fib=True`. **Defaults verified mechanically against the Pine, not by eye** — all 23
execution inputs in the panel diffed programmatically, 0 mismatches. 140 tests green (11 new).
✅ **PARITY RE-VALIDATED GREEN THE SAME DAY, and the run is not vacuous.**
`compare_strategy.py "VANTAGE_XAUUSD, 15_cfa13.csv"` → **exit 0 at warmups 100 / 200 / 500 / 1000 /
2000**, 21,702 bars, 2025-08-31 → 2026-08-02. `cfg_bits` gained bits 131072 / 262144 / 524288 /
1048576 / 2097152 (65536 stays RETIRED, never reused) and the export **decoded 544375 — bit 524288
SET** — so the Pine really was running rule 3 and the Python was configured to it from the export,
rather than the two agreeing on a model neither had switched on. That is what makes this the run the
port needed: an export taken before today has all five bits clear, which decodes to Method 3 with
the gate off — exactly the build it came from, so archived exports still replay correctly, but a
green from one would have said nothing about this change. Also decoded: SL 0.886, TP rungs 0/0,
`cfg_exitmode = 20` (the ratchet), min-stop Off.
Earlier the same day: **the stop level is no longer limited to the five-value dropdown.**
`exec_sl_level = "Custom"` reads a new `exec_sl_custom` (any fib ratio in (0, 1.0], default 0.886),
priced off the leg anchors through the canonical `fib_level()` — so **Custom 0.886 is bit-identical
to picking "0.886"** and the mode switch alone moves nothing. It opens the half of the range the
ladder never had (0.886 → 1.0: deeper stop, smaller position) and, being a NUMBER, makes the level a
real optimizer axis instead of five strings. Out-of-range raises at construction rather than falling
back to fib 1.0, because a typed number silently becoming a different stop would replay a whole
backtest against a level nobody chose. ⚠ **No Pine counterpart** — `execSlLevel` is an `input.string`
with five options, so `compare_strategy.py` can never configure a Custom run (parity is therefore
structurally unaffected) and **a Custom result is a lab finding, not a validated one**. ⚠ Shallower
than 0.886 is Run 4's hazard at any ratio, not only at three — turn `exec_min_stop_mode` on first.
Detail: `### The Custom stop level`. 129 tests green (7 new).
Earlier: 2026-08-01 — 🔴 **THE FILL BAR WAS STAGING THE STOP — fixed, and it moved every
number in this file.** `indicators/docs/BUG_exit_fill_price_mismatch.md`, open since 2026-07-14, was not
a TradingView artifact: `_advance_stage` ran on the ENTRY bar and read that bar's whole high/low.
A resting limit is reached by price coming to it from the wrong side, so the entry bar's
*favourable* extreme is the approach to the order, never the trade's own move — the stop went to
breakeven on a trade that had gone nowhere, which puts it on the WRONG SIDE of the market, and
every leg market-closed at the next bar's open. Fixed here (`step` skips `_advance_stage` when
`opened`, `step_secondary` likewise, `_max_fav` seeds from the fill price) and in all five strategy
Pine files. **The excursion pair is now seeded ASYMMETRICALLY and that is deliberate** — a buy
limit fills on the way DOWN, so the entry bar's LOW is post-fill and a real adverse excursion while
its HIGH is only the approach; seeding both flat threw real information away and
`test_trade_records_favorable_and_adverse_excursion` caught it. **Measured on lab run
`d2ab68f9e884`** (XAUUSD 15m, 2020-01-01 → 2026-07-31): **all 165 entries identical**, 30 results
changed (18 better / 12 worse), **+101.68R → +112.43R**, win rate 63.6% → 67.3%. Four trades the
bug had killed at breakeven were really +3.90R / +2.98R / +2.86R / +1.87R. ⚠ **12 trades that used
to scratch now take a full −1R and max drawdown was NOT measured** — re-run in the lab before
quoting any risk number. ✅ **PARITY RE-VALIDATED the same day** on a FULL-HISTORY post-fix export
(`VANTAGE_XAUUSD, 15_fd236.csv`, **21,691 bars**, 2025-08-31 → 2026-07-31): `compare_strategy.py`
**exit 0** at warmups 100 / 200 / 500 / 1000 / 2000, no truncation warning. **The fingerprint is
gone from the bars:** on the entry bar, is `px_stop` already at breakeven instead of the real SL?
Before = **4 of 26** entries; after = **0 of 27**. All four affected candles are inside the window,
so each reads before/after on the same bar — 2025-10-02 died in 1 bar at −0.120R and now runs **47
bars to +0.008R**; 2025-12-02 −0.860R → **−1.000R**; 2026-05-11 +0.008R → **−1.000R**; 2026-07-20
**unchanged** at +0.859R (wrong stop, never hit). Three of four get worse or stay flat; the fix is
right anyway, because the exit price now corresponds to an order the strategy actually placed. An
earlier PARTIAL export the same day exposed a harness asymmetry, now fixed: `compare_strategy.py`
HARD REFUSED a truncated export where `compare_bleg.py` replays until the engine converges. It now
warns and requires `--warmup >= the missing bars` (`--debug-arm` still refuses — it diffs the
chart-relative `dbg_*` bar indices). ⚠ **Every measured number below this line — 110.65R, Run 8's 43% → 53%
run-capture, all twelve runs in `mpc_sos_fade_optimization.md` — was taken THROUGH this bug and
needs re-baselining**; the exit-ladder conclusions are the most exposed, because the bug killed
trades one bar after entry, before the ladder ever engaged. 3 regression tests, 534 green.
**The lesson: a green `compare_strategy.py` says Pine and Python AGREE, never that either is
right** — this bug was faithfully ported, so the gate was green for its whole life. **Recorded the
same day and NOT part of the bug: a wrong-side stop can still fill at the next bar's open
legitimately, and it is a backtest limitation rather than a defect** — see
`### Wrong-side stop fills` before anyone re-reports the symptom.
divergence on this pair.** `exec_min_stop_mode` / `exec_min_stop_val`, the floor applied at order
placement, block reason code 7, a REGENERATED `mpc_strategy_export.pine` (body byte-identical to the
parent again) carrying `cfg_min_stop` / `cfg_min_stop_val`, and the decode in `compare_strategy.py`.
Built as step 1 of the live-trading pipeline (`docs/LIVE_TRADING_PIPELINE.md`) because it is the
guard for the only hazard in this bot that can lose real money fast: a stop that collapses onto the
entry does not risk less, it balloons `qty = risk / dist`. **Default `"Off"`, byte-identical to the
previous build, so no historical result moves** — and equally, nothing here validates the filter ON
until a fresh export is diffed. Full record: `### The minimum-stop guard`. 111 tests green.
Earlier: 2026-07-29 — **Run 12: "can this bot trade more?" is answered NO, and one claim in
this file was measured wrong and is now corrected.** The `## The missed-setup watch` section used to
call the "No FVG in zone" bucket the layer's *actionable* output; replaying 6.5 years with
`exec_req_fvg` off shows those setups are a coin flip whose entire positive result is one 2020 trade
and whose sign flips with the counterfactual entry price — see the ⚠ block there. Three other routes
to more trades (smaller size on the extras, deeper entries, a looser gap rule) are negative too, and
the final-hour rule costs ~0.4R over 6.5 years so it stays on. **No strategy code changed**; the only
code change is a Pine UI cap (`aplusWindow` maxval 4320 → 20160, default still 4320, so no result
moves — `aplus_window` here never had a cap). Earlier the same day: **parity re-run GREEN on a fresh
export that finally carries the ratchet AND the shipped 0/0 rungs** (`### PARITY GREEN 2026-07-29`).
Every "the export is stale" warning in this file is cleared, with one exception that was NOT cleared
then and IS now: the export had no `execMinStopMode`/`execMinStopVal` column — see the 2026-07-30
entry above.
Earlier: 2026-07-27 — `exec_sl_level` defaulted **"1.0" → "0.886"** in lockstep with both
A+ Pine files (Aaron's call — it is what he trades, and Run 6 rode it over the full history). The
⚠ block below is AMENDED, not retracted: 0.886 is still inside the entry band and neither Run 4
defect is fixed; 0.618 / 0.702 / 0.786 stay unsupported. `mpc_bleg` PINS "1.0" rather than
inheriting, because its own Pine still ships 1.0. Earlier the same day: `Execution` now also
records MISSED SETUPS (the Pine's orange 2-of-3
callout, reporting-only) for the lab price chart's Missed layer; see `## The missed-setup watch`.
Earlier the same day: `exec_tp1_pct`/`exec_tp2_pct` defaulted 30/40 → **0/0** (Run 1
adopted; the whole position rides the runner), and **PARITY RE-VALIDATED GREEN (exit 0)** on a fresh
21,320-bar 15m export taken at the settings Aaron trades — SL fib 0.886, TP1 0%, TP2 0%, structure
trail. First run of the 0/0 exit path against the Pine. See `## The exit ladder`. Earlier the same
day: `Execution` now records BLOCKED SETUPS (the Pine's pink TRADE
BLOCKED tag, reporting-only) for the lab price chart's Blocked layer. Earlier: 2026-07-26 — the
exit levers (structure runner trail, TP2 stop floor, the three
setup toggles) ported from the Pine, the export's config columns completed, and **PARITY RE-VALIDATED
GREEN (exit 0)** on a fresh 21,230-bar `VANTAGE_XAUUSD, 15m` export — which caught a real unpinned-
engine-input bug (`fvg_require_close`). See `## The exit ladder` and `## The 2026-07-26 exit-lever sync`.

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `strategies/python/mpc_sos_fade/docs/SOS_FADE_BUILD_NOTES.md`. **Nothing was deleted.** It was 60,467 bytes in 2 paragraph(s), the largest 58,936 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

## The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)

`MPC` = Mental Peak Consulting (Aaron's brother's company) and prefixes every strategy in the
house. The suffix names the **narrative** the strategy trades off the shared `engines/` — here:
a **shift of structure (SOS)**, faded. The old name described the *grade filter* it happens to
use, not what it does, and "A+" would collide the moment a second MPC bot also traded A+ setups.

**"A+" is still correct vocabulary and is deliberately kept** wherever it names the brother's own
Pine concept — the A+/B/C/D grade dropdown, the "A+ SETUP SEQUENCE" block this ports, and the
`aplus_window` config field (which mirrors the Pine input "Max time: sweep → SOS (minutes)" and is
a lab param-grid key). Renaming those would break the line-for-line traceability to the Pine, and
`aplus_window` is also an optimizer grid key. The Pine files themselves are NEVER renamed: they are
the brother's source and the parity reference.

## Sizing — this bot sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True`, so the command-center lab does NOT run its dynamic
sizing engine over this bot's trades. `exec_risk_pct` (Pine default **10%** per trade) IS the risk
knob: it is a normal strategy param, so it is editable in the Run modal and sweepable in the
optimizer grid — that is the "manual %" for this strategy, and the SIZING MODE control is hidden
because there is nothing for it to decide. Pair a run with the **Unconstrained (No Limits)**
ruleset to see the raw behaviour with no halts and no drawdown floor cutting a day short.

**Input range (2026-07-27):** the Pine input's `maxval` was raised **10 → 100** across all four
strategy Pine files at Aaron's request — the old 10 was an arbitrary UI cap, not a safety rule, and
`exec_risk_pct` in `config.py` never had one. The DEFAULT is still 10 on both sides, so no run
changes. Two things the raised ceiling exposes and neither side checks: the `margin_long/short =
0.2` pin means TradingView rejects (or partially fills) an entry whose notional exceeds 5x equity —
silently, as a missing trade rather than an error — and the **no-minimum-stop-distance hazard**
below scales linearly with the risk %, so a degenerate stop that realised ~180% of equity at
`exec_risk_pct = 10` realises the same multiple of whatever is typed here.

## `live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)

The `backtest/setups.py` contract, implemented here. `Execution._setup_context` freezes each
side's live watch every bar; `live_setups()` assembles it with the CURRENT resting order;
`drain_setups()` is what the live runner calls. Messages and volume:
`docs/LIVE_SETUP_ALERTS.md`.

**Three confluences, reported with the strategy's own words**: Arm (`Sweep · Day High`), Shift of
structure, Retrace zone (`0.5-0.886 tagged, FVG live`). Plus the tradeable ZONE (`fibo_p2` →
`fibo_p6`) and the stop projected off the deep edge through `_sl_anchor`, so `exec_sl_level` /
`exec_sl_custom` / `exec_sl_deep` resolve exactly as they would for a real order.

⚠ **REPORTING ONLY, PROVEN BY REPLAY.** HEAD vs the working tree over 155,807 M15 bars →
byte-identical 159-trade list, SHA-256 `b52816e7…`, sum R **+142.177389**. **No figure in this
file moves.** 244 strategy tests green.

⚠ **The context is captured AFTER the accumulate block in `_record_misses`, not before.** Before
it, `m.zone` had not yet been set on the bar price first tags the band, so the alert reported a
setup as still waiting on a retrace on the very bar it got one. It also has to live there rather
than in `live_setups()` because that is the one place the per-side gates are already resolved
through the enable-toggles exactly as `_armed` reads them — so "armed" means the same thing in an
alert as it does in a decision.

⚠ **`live_setups()` must be called AFTER `step()` returns.** The resting order is rebuilt in
`_place_entries`, which runs after `_record_misses`, so reading `_pend_*` any earlier reports the
PREVIOUS bar's price beside this bar's confluences.

🔴 **A `Confluence.detail` has to stand ALONE, because the alert prints the detail and drops the
name.** `Confluence("Shift of structure", True, "confirmed")` rendered in Telegram as a bare
`confirmed` next to `Swept Day Low`; it says `SOS confirmed` now. **The strategy owns what its own
confluences are called** — `algos/live/alerts.py` must never learn what an SOS is, which is the
whole reason the contract carries text rather than codes.

⚠ **`_MISS_REASON` is read in TWO places** — the Telegram `NO TRADE` reply and the lab's miss
report — and both render it UNDER its `_MISS_LABEL`, so a sentence that restates the label says it
twice. Trimmed 2026-08-13 on Aaron's *"less verbose"*; the facts are unchanged and no code branches
on the text. ⚠ **Both of these are in the version-pinned tree, so a wording change here needs a
`promote.py`** where the same change in `algos/live/alerts.py` needs only a restart.
✅ **Reporting-only re-proven after both edits**: the same replay script over 155,807 M15 bars at
HEAD and on the working tree gives an identical 159-trade list, SHA-256
`30dc1c5b25f39ef795077ac990e9622e846a66e2a038c42ef816224082d31fe6`. ⚠ **That digest is NOT
comparable to the `b52816e7…` in `backtest/docs/BACKTEST_BUILD_NOTES.md`** — it is a different
serialisation of the same trades. The proof is the before/after pair, not the constant.

⚠ **`entry` is read from the ORDER, never recomputed from `sig`** — the identical trap already
recorded for `Trade.fib`: a fib keeps extending while a limit rests.

🔴 **`alert_resting_fib` (2026-08-14, default 0.236) decides WHEN a pending limit is announced, and
it changes no trade.** The order is still placed the instant the setup arms; only the Telegram
message waits. Aaron, on a live send: *"I only want to know a limit is pending when price gets back
to 23.6% of the retracement."* `_announce_ready` latches per leg on the SOS bar once the bar's
extreme tags `fib_level(0.236)` — priced through the canonical helper off the same anchors the fib
engine used, never interpolated from the zone edges.
⚠ **The ratio MUST stay under 0.5 and `__post_init__` refuses otherwise.** Every fill is at 0.5 or
deeper, so price cannot fill without crossing a shallower level first — **that is what makes a
suppressed message provably a setup that never traded**, a guarantee rather than a measurement. At
0.5 the guarantee is gone and a real trade could reach the trades room unannounced.
⚠ **The two event families mirror the trade DIFFERENTLY and one of them was measured wrong first**
— see `_announce_ready`'s docstring. It is deliberately outside the `exec_` namespace and has no
Pine counterpart, so `compare_strategy.py` is structurally unaffected.
✅ **REPORTING ONLY, proven by replay: 155,807 M15 bars at HEAD and on the working tree give an
identical 159-trade list, sum R +142.177389. No figure in this file moves.** Message volume
332 → 301 resting alerts over 6.5 years, and `alert_rate.py` still reports 159 trades / 158
announced — the one gap being the warm-up boundary it always was.

🔴 **Only a READY setup can be reported as BLOCKED, and getting this wrong made the message lie.**
A veto, the final hour or an HTF filter can be live while a setup is merely forming; reporting
that announced setups as blocked which then rested and filled, under a sentence reading "the setup
was ready and this rule stopped it". It now asks the same readiness question `BlockedSetup` does,
and of the CURRENT bar rather than of `m.blk_*`, which latch true for the setup's remaining life.
**Found by rendering the messages against real bars — no test saw it.**

⚠ **`strategy_name` is set by the STRATEGY, not by `Execution`.** `mpc_bleg` and `mpc_bos` share
this execution layer, so its own class name labelled all three "Execution" in Telegram.

🔴 **`mpc_bleg` and `mpc_bos` INHERIT `live_setups()` and would have claimed a channel they can
never fill.** Both set `_records_misses = False`, which gates the only method populating the setup
context — so they inherited a `live_setups()` returning `[]` on every bar forever, a
method-presence check called them supported, and the runner would have logged "Setup alerts: ON"
for a channel that can send nothing. **The empty-registry failure arriving through a base class
rather than a literal `{}`.** `reports_setups` is therefore DERIVED from `_records_misses`, so a
new fork cannot acquire a silent, empty channel by forgetting a line — and `True` is still not a
claim that a fork's confluences are right: turning the watch back on would report A+'s three
confluences for a setup it does not trade. Each fork needs its own `_setup_context` first.

✅ **The derivation was validated by an event rather than by an argument: `mpc_realign` landed on
main WHILE this was being built**, subclasses this layer, sets `_records_misses = False` like its
siblings, and declined the channel correctly with nobody editing anything and nobody aware of a
rule that did not exist when they started. **A per-fork flag would have needed its author to know
that rule.** The test ENUMERATES the forks rather than naming them, so the next one is covered
before it is written, and fails by NAME on whichever starts claiming a channel it cannot fill.

⚠ **`tradeable` is `arm_met` and NOTHING ELSE, deliberately.** The arm source is snapshotted at
the SOS, so a setup armed by a disabled source can never acquire a different one — that is a
decision the strategy has already made. A veto or the final hour can LIFT while a setup is alive,
so those stay reportable and travel as `blocked_by`. 🔴 **The estimate that justified this filter
was wrong by two orders of magnitude**: "220 of 609 are divergence-armed and cannot trade" read
`arm_src` (which source reached stage 1 FIRST), not `sos_l_swp` (was a sweep live at the SOS).
**It fires on ONE setup in 6.5 years, and `miss_audit.py` reports ZERO code-1 misses over the same
window** — the counter that settles it existed the whole time. **A count that is easy to obtain is
not the count you asked for.**

## The restart seam — `snapshot_position()` / `restore_position()` (2026-08-10)

`Execution` can write its whole open-trade state down and put it back. **It exists for
`algos/live/` and nothing in a backtest calls it** — the full design, and every refusal around
it, is in `algos/live/position_state.py`.

**Why it had to live here rather than in the live package.** A restart rebuilds this object EMPTY
from a warm-up replay, so the live bridge used to HALT on any position the broker already held and
the trade sat unmanaged until somebody looked — its broker stop stood, but nothing ratcheted it and
the time stop never fired. Putting the state back means writing ~30 private fields, and the live
package reaching across a subsystem boundary to set them would be a second, silent copy of what an
open trade IS. One method here is the honest seam, the same standing as the `account` / `leg` pair
above.

⚠ **`_POSITION_FIELDS` is the whole open-trade state and a missing entry is SILENT.** Leave one out
and the restored trade manages against a constructor default — a zero `_max_fav` un-ratchets the
trail, a zero `_stage` puts a breakeven stop back to the full stop, a missing `_entry_ms` resets the
time stop's clock. Nothing raises.
`test_the_snapshot_covers_every_field_open_position_assigns` therefore **DERIVES the required set by
reading `_open_position`'s own source**, because a hand-written list would re-freeze exactly the
assumption that fails — the same guard `run_dual`'s 1m signal needed after it shipped missing two
fields that three weeks of green tests never saw.

⚠ **`_traded_sos_l` / `_traded_sos_s` are carried even though `_open_position` does not assign
them there.** They are the one-trade-per-15m-leg latch, and without them a restored bot could
re-enter the very setup it is already holding, the moment that trade closes.

⚠ **`restore_position` REFUSES an incomplete record rather than filling defaults**, and that is the
safety property. A record missing `_stage` is not "a trade at stage 0", it is a record that cannot
be trusted; the caller halts, which is what the bot did in every case before this existed.

✅ **Parity is structurally unaffected and it is CHECKED rather than asserted**: a test reads the
source of `step`, `step_secondary` and `_manage_open` and fails if either method is ever called
from the bar path. A lab replay only ever holds a position it filled itself.

⚠ **`mpc_bleg` and `mpc_bos` inherit both methods**, which is correct — they share this exit ladder
and this emulator — but neither has been driven live, so treat the inheritance as untested there.

⚠ **It needs a PROMOTE to reach the live bot.** This package is version-pinned, so the running bot
keeps the old code until `algos/tools/promote.py` runs.

## The portfolio-account seam (2026-07-17)

`Execution.__init__` takes an injected `account` (default `SoloAccount`) and a `leg` name — the seam
for stacking this bot with others on ONE shared account (`backtest/portfolio/`). What changed:
`self.equity` now reads `account.balance` (the shared balance the bot sizes against); the leg-local
`_equity_realized` is kept for R. The fill gate in `_open_position` calls `account.request_fill`,
which **scales** the bot's own desired qty to the shared room (solo → full size); partial exits and
costs `book_pnl` onto the shared balance; the full close frees the reservation; each bar reports the
live stop via `update_stop`. **Parity is unchanged:** a `SoloAccount` grants full size always, so
`compare_strategy.py` stays exit 0 — re-verified on the 20,076-bar export after the seam landed. The
account scales the bot's qty rather than recomputing it precisely so parity holds (the bot sizes off
the limit price at placement, not the fill). Do not route qty computation through the account.

## What it is (one paragraph)

A counter-trend reversal that fades exhaustion at HTF liquidity. Three-stage A+ sequence: **Arm**
(liquidity sweep by default, or an RSI divergence) → **SOS** (a same-side external structure break in
the trade direction, inside a staleness window) → **Zone+FVG** (price retraces into the 0.5–0.886 fib
band and a live FVG overlaps it; default requires the gap fully past 0.5). Entry is a resting limit — a
deep gap re-prices to the nearest shallower fib (Method 3), else the FVG's near edge, clamped into the
band; stop = fib 1.0 (leg origin) + buffer; exit = the fib TP ladder (30/40/runner) with stop→BE on
TP1, stop→TP1 on TP2, and a ratcheting trail on the runner. Full rules: `docs/MPC_SOS_FADE_SPEC.md`.

## The five modules (the data flow)

```
BarState  --SignalAdapter-->  Signals  --SosFadeSequence-->  SeqState  --Execution-->  Decision
(backtest.replay)             (Pine-named inputs)          (A+ stages)               (orders + fills + R)
```

- **`config.py`** — `SosFadeConfig`: every trade-affecting Pine input toggle, same name + default
  (**toggle parity is a hard requirement**). Instrument facts (mintick, point value, close time) are
  Layer-B injections, also here. Cosmetic Pine inputs (debug labels, boxes, table styling) are
  deliberately absent — they don't touch a trade decision.
- **`signals.py`** — `SignalAdapter`: turns a replay `BarState` into the exact Pine-named globals the
  A+ block reads. Two reconstructions are non-trivial and must stay faithful:
  1. `recentSSL` / `recentBSL` — the most-recent swept pool per side, from ten per-source slots
     (H4 / Day / Asia / London / NY high & low) resolved by latest sweep bar, sessions suppressed
     once Day is filled. Rebuilt from the liquidity engine's `mitigated` / `evicted` events.
  2. `bullDivActive` / `longVeto` — recomputed WITH the structure-break staleness (`lastExtBreakBar`)
     the standalone RSI engine can't see. **Do NOT use the RSI engine's convenience `bull_active`** —
     it omits the stale check and would diverge from the Pine.
- **`sequence.py`** — `SosFadeSequence`: the Stage 1→4 state machine, retro-link (a late-confirming
  divergence adopting an SOS that already fired), sequence death (opposite SOS / TP3 / invalidation /
  continuation BOS), and the arm-source snapshot (which Stage-1 source was live at the SOS).
- **`execution.py`** — `Execution`: entry edge → resting limit → TP1/TP2/runner ladder → staged stop
  + ratchet → %-risk sizing → graded R, on a small broker emulator (`_Broker`-style) that reproduces
  the two TradingView fill assumptions logic parity depends on:
  1. **calc-on-close, one-bar delay** — an order placed at a bar's close is active only next bar (a
     resting limit never fills the bar it was placed; an exit never fills the bar the entry filled).
     **This is also a KNOWN BACKTEST LIMITATION, not a defect — see `### Wrong-side stop fills`
     below before reporting it as one.**
  2. **intrabar path** — when a bar covers both a TP and the stop, the open's proximity to the
     extremes decides which fills first (open nearer high ⇒ price travels open→high→low→close ⇒
     targets first; nearer low ⇒ stop first). **This is the single most parity-sensitive assumption
     — it is a GUESS until `compare_strategy.py` is exit 0.**
  Each closed `Trade` also carries **reporting-only excursion** — `mfe_usd` (favorable: the most it
  ever showed in profit) and `mae_usd` (adverse: the deepest it sat against us), tracked across the
  whole hold on bar high/low (`_ext_high`/`_ext_low`) and converted to USD at close. NO decision
  reads them, so they are parity-safe (`compare_strategy.py` diffs the `px_*` decision stream, not
  `Trade`); they flow through `backtest/output.py` to the lab's equity-chart excursion overlay.
  `Execution` also records **blocked setups** (`BlockedSetup`, `execution.blocks`) — a port of the
  Pine's pink `TRADE BLOCKED` tag (`mpc_strategy.pine` 4025-4086): a setup price and the engine had
  READY (SOS in, fib agreeing, an entry edge to rest on, flat, this leg untraded) that one of the
  strategy's OWN toggles refused. Same six reason codes in the same PRECEDENCE (`f_blkCode`: 1
  direction off · 2 arm source off · 3 final hour · 4 divergence/extreme veto · 5 HTF breakout · 6
  HTF bias), the same hover text as `f_blkWhy`, and the Pine's `sosBar*10 + code` dedupe generalised
  to the reason SET — one record per setup per distinct COMBINATION, so a setup blocked for twenty
  bars is one record but a set that changes is a genuinely different refusal.
  **ONE DELIBERATE DEVIATION:** the Pine reports only the FIRST blocker (a chart tag has room for one
  line); we record EVERY rule refusing the setup, because the lab filters by reason and "blocked by
  the veto" has to stay true when the final hour was also blocking. Precedence survives as the ORDER,
  so `codes[0]` (exposed as `.code`) is exactly what `f_blkCode` would have returned alone — a
  per-reason count taken off the primary still reconciles with TradingView.
  **Reporting-only and parity-safe**, exactly like the excursion fields:
  nothing reads a record back, so no decision can move and `compare_strategy.py` diffs the same
  `px_*` stream as before. The recording hangs off `_place_entries` (reading gates `_armed`
  computed, never recomputing them), which is why `mpc_bleg` gets none — it overrides that method,
  and those codes describe why an *A+* setup was refused. Surfaced on the lab price chart's Blocked
  layer; the full path is in `command-center/backend/CLAUDE.md` → *Blocked setups*.
  `Execution` also records **missed setups** (`MissedSetup`, `execution.misses`) — the OTHER half of
  "why didn't this trade", and a port of the Pine's orange 2-of-3 callout (`f_w23Arm` / `f_w23`,
  `mpc_strategy.pine` 3064-3194 + 4022-4023). See *The missed-setup watch* below.
- **`strategy.py`** — `MpcSosFadeStrategy`: the driver. `run(df, warmup=…)` replays a canonical frame
  end-to-end; `step(bar_state)` does one bar. Collects `.decisions` (the per-bar stream) and
  `.execution.trades`.
- **`secondary.py`** — the 1m sniper re-entry (below). `Structure1m` (1m structure feed, port of Pine
  `f_struct1m`) + `SecondaryArm` (the latch/arm, port of Pine `f_secArm`). Consumed by `run_dual`.

## The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused

A **block** and a **miss** answer the same question one step apart in a setup's life, and mixing
them up makes both useless. A block is a trade the strategy had FULLY READY and one of its own
toggles refused. A miss never got that far: it reached 2 or 3 of the three confluences and then
DIED. Neither places an order, so neither is in any trade list, any equity curve, or any broker
report — the only place either is countable is here.

The three confluences, and what "met" means (Pine `f_w23`):

| # | Confluence | Met when |
|---|---|---|
| 1 | **ARM** | a liquidity sweep or an RSI divergence armed Stage 1 — and the source that fired is one you have ENABLED |
| 2 | **SOS** | always: it is why the watch is open at all |
| 3 | **ZONE** | price tagged the 0.5-0.886 band AND (with Require-FVG on) a gap was live in it while price was there |

**Exactly one thing is ever missing**, which is why `MissedSetup` carries a single `code` where
`BlockedSetup` carries a list. At 2 of 3 it is the arm or the zone (codes 1-3); at 3 of 3 every
confluence was there and the entry still never happened, so the record names the ENTRY-side reason
instead, in the Pine's precedence: veto → final hour → HTF → "the limit rested and price never
touched it" (codes 4-7). `reasons` is still exposed as a one-item LIST purely so a miss and a block
read identically all the way downstream.

### The RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08)

🔴 **`MissedSetup.time_ms` is the bar the setup DIED, and something downstream read it as "where
the setup was".** The lab's Candlestick Reversals layer anchored its marks there and painted them in
a part of the chart the setup had nothing to do with — Aaron, off the screen: *"the reversal candle
printed on the opposite side, which doesn't make sense … I'm expecting it to be that price got into
the zone for the trade and there was a reversal candle."*

✅ **MEASURED on the reference run (2020-01-01 → 2026-08-06, 155,807 M15 bars, 35 three-of-three
misses): on 32 of the 35, price sits a median $22 and up to $205 from the setup's own `edge` on the
death bar, which is a median 17 and up to 717 bars after the retrace.** That is correct for a marker
saying *this setup is now over* and useless for anything asking *where was price when it was live*.

`MissedSetup` therefore carries the retrace itself: `zone_time_ms` (the first bar of the visit) and
`zone_turn_ms` (its most adverse bar). Both `None` when price never reached the band.

🔴 **IT CANNOT BE DERIVED DOWNSTREAM, which is the reason this had to change here rather than in the
consumer.** The cheap fix — scan back from the death bar for a bar that traded through `edge` —
finds one for **all 35**, including the ten whose whole reason for existing is that price never
reached the limit, because price crosses that level at unrelated moments. It would have been
confidently wrong and silent.

🔴 **It must NOT be driven off the caller's `zone_hit`, and that is the subtle half.** `zone_hit` is
`l_half or l_618` — a **LATCH**: once price tags 0.5 it stays true until the leg resets, so every bar
to the death reads as "in the zone" and the visit measures 717 bars. `_MissWatch.visit()` asks the
BAR instead — does its range overlap `[fibo_p2, fibo_p6]` — which is the question the latch answered
once and then remembered. ✅ **That one change took the median span 17 bars → 3.**

⚠ **The DEEPEST visit is reported, not the first or the last.** A setup can tag the zone, leave, and
come back — those are different retraces, and the one worth reporting is the one that came closest to
filling.

⚠ **REPORTING ONLY, and proven so rather than argued**: the strategy replayed at HEAD and at the
working tree over the full **155,807 M15 bars** produces a byte-identical 159-trade list (same
SHA-256 over every entry time, direction, entry price, exit price, R and exit reason).

✅ **6 new tests in `tests/test_execution.py`, three MUTATION-proven** — dropping the band test (the
latch bug restored), reporting the first visit instead of the deepest, and flipping the direction
each turn a different one red. `_seq_short_ready` / `_seq_short_dead` were added for the last of
those: the adverse extreme is the highest high on a short, and a long-only fixture cannot see it
being backwards.

**Three deliberate deviations from the Pine, all reporting-side:**

1. **Every miss is recorded; nothing is filtered at write time.** The Pine has three view filters
   (`debugShow23`, `debug23Filter`, `debugShow23Disarmed`) plus a `debugDays` recency window because
   TradingView caps a chart at 500 labels. The lab has neither problem, and a miss filtered away at
   write time can never be counted later. The chart filters BY REASON instead, which is strictly
   more expressive than the Pine's three presets.
2. **`near` replaces those presets.** Each record carries the Pine's own near-miss test
   (`metN == 3 or (zone reached and zone not met)`). The chart derives its DEFAULT view from it —
   see `command-center/backend/CLAUDE.md` → *Missed setups* — so the layer opens on the Pine's
   default and one click widens it, which the Pine's radio buttons cannot do.
3. **A setup that filled this bar closes as TRADED immediately.** The Pine assigns `tradedSosL`
   further down its script than it reads it, so on the fill bar it still reads the previous value.
   Both end with no callout; ours gets there a bar sooner, and it is the correct answer on the one
   bar where they differ (a trade that opened and closed inside the same bar, which the Pine would
   have booked as a miss).

**Where it runs, and why not where the blocks run.** `_record_misses` is called from `step()`,
between the fills and the placement — the same slot the Pine calls `f_w23` from. It CANNOT hang off
`_place_entries` like the block recorder does: a setup keeps accumulating state while a position
from the other side is open, and that path never runs then. That is also why `_bar_gates` was
extracted from `_armed` (the final-hour / HTF / bias gates are needed on every bar, not only when
flat) and why `mpc_bleg` needs the explicit `_records_misses = False` opt-out rather than getting
the exclusion for free.

**Two additions this needed elsewhere, both parity-neutral.** `SeqState` gained `l_arm_src` /
`s_arm_src` (Pine `armHolderL`/`armHolderS`) — the source holding the Stage-1 slot, which is the one
thing the live `sos_*_swp`/`sos_*_div` flags cannot tell you once the execution layer has filtered
them through the toggles, and without it a "your arm source is off" reason could not say WHICH one.
`build_results` gained `missed_setups`.

**Measured on the shipped window** (XAUUSD M15, 2025-03-04 → 2026-07-27, 33,041 bars, defaults):
46 trades, 80 blocks, **93 misses** — 50 "No retrace" (none near), 35 "No FVG in zone" (all near),
4 "Never filled", 4 "Final hour". So the chart opens on 43 markers and the routine 50 are one click
away.

⚠ **"No FVG in zone" is a DIAGNOSTIC, not a to-do list — corrected 2026-07-29 (Run 12).** This
section used to call that bucket "the actionable number this whole layer exists to produce". It was
then measured over 6.5 years (2020-01-01 → 2026-07-29, 155,186 M15 bars) by replaying the same bars
with `exec_req_fvg` off, and **taking those setups is not worth it**: 180 no-FVG misses, 173 fill at
the 0.618 fallback, **50 win / 54 loss / 69 breakeven** (median +0.04R) for +34.0R gross — of which
**40% is one January-2020 trade**, and they crowd out 17 real trades worth +21.0R, so the net is
+13.0R on a 110.6R book while max drawdown goes **54.9% → 77.1%**. The sign also flips with the
counterfactual entry price (+13.0R at fib 0.618, **−6.7R at 0.5**), which is the signature of noise
rather than an edge. Deepening the entry and loosening which gaps qualify are both worse still.
**Read the layer as "why didn't this trade", never as "here is missed money"** — full record and the
three other routes in `mpc_sos_fade_optimization.md` → Run 12 / 12b.

## Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, committed `c962601`)

The 1-minute re-entry Aaron prototyped in Pine, built as the *exact* version here (Pine can only
sample the 1m engine once per 15m bar — its own tooltip says "the exact version is the Python port").
**Full rules + design: `docs/MPC_SOS_FADE_SECONDARY.md`.** One paragraph: after the **primary** 15m
A+ trade on a leg has traded and gone flat, while the 15m div + SOS are still live and price is back
in the 0.618-0.886 zone, a **1m shift of structure** in the trade direction rests a limit at a 38.2%
retrace of that tight 1m leg (stop = 1m leg origin; TP1/TP2 = 15m 0.5/0.382; runner = TP3). One
re-entry per 1m leg; a re-entry is never the first trade on a leg.

- **`run_dual(df15, df1m)`** merges the two streams on a close-time clock: the **primary** is stepped
  on 15m bars exactly as `run(df15)` (so parity is untouched); the **secondary** latches/arms/fills/
  manages on real **1m** bars — the sniper "in and out fast" a 15m bar can't express.
- **Execution** grows an `_entry_kind` tag + `step_secondary(bar1m, arm)`. A 15m bar only ever
  touches a `primary` position; a 1m bar only a `secondary`. They share the one position slot but
  never the same trade (the secondary arms only when flat), so the tag is all that separates them.
  With `exec_secondary` OFF, no secondary ever opens, so `step()` is byte-identical to before.
- **NO Pine parity gate** — the Pine is only the approximate version, so this is verified **visually**
  (the lab price chart + the 15m→1m drill-down). The offline guard is
  `test_run_dual_primary_is_identical_to_run_when_secondary_off` + the hand-traced arm/exec tests in
  `tests/test_secondary.py`, and OFF parity was re-confirmed on the real M15/M1 cache (`run` ==
  `run_dual`, 40 trades byte-identical). `compare_strategy.py` (which runs `run`, not `run_dual`)
  stays the primary's gate.
- ⚠ **UNMEASURED ON REAL DATA until 2026-08-06, and the reason it stayed that way was a WRONG NUMBER
  IN THIS FILE.** The note here used to read *"broker serves ~35d direct; older via ticks"*, so the
  only 1m window anyone thought was reachable was ~4 days of local cache, over which the secondary
  fired 0 times — correctly read as "expected, the setup is rare", and never re-examined. 🔴 **That
  35-day figure was a guess and it is false.** Probed against the live `MT5_Lab` terminal
  (VantageMarkets-Demo): **real 1-minute XAUUSD runs back to 2018-09-14, ~2.8M bars, 7.9 years.**
  Six windows sampled across the range (Sep 2018 / Jun 2020 / Jan 2023 / Mar 2025 / Jul 2026 / Aug
  2026) all return **1,341-1,392 bars per day at exactly 1.0-minute spacing**, and a request for
  Jun 2017 is REFUSED by the measured floor rather than silently served daily bars. ⚠ **Density is
  the check, never the earliest timestamp** — `backtest/data/history.py` exists because MT5 answers
  a too-deep intraday request with COARSER bars wearing the label you asked for. ⚠ **`backtest/cache/`
  held NO M1 at all** (M5/M15/H1/H4 only), which is a second reason the feature looked unrunnable —
  it is populated now, and on a machine where it is not, the first full-history run pays a one-off
  download of ~2.4M bars (measured: ~10 min, quarter by quarter, over the SSH tunnel). **The standing lesson is this repo's own from 2026-08-06,
  one layer earlier: a plausible guess written into a doc is not a cheap placeholder — it is a
  signpost, and a wrong one costs more than no sign.** This one pointed at "there is no data" for
  three weeks, and the real answer took one probe.
- 🔴 **MEASURED 2026-08-06, AND IT DOES NOT EARN ITS PLACE — THE WHOLE CASE IS ONE TRADE.** Three
  replays over 186,274 M15 + 2,744,333 M1 bars (2018-09-14 → 2026-08-05) at the shipped defaults:
  **A** `run(df15)` = the baseline, **B** `run_dual` with the secondary OFF = the control, **C**
  `run_dual` with it ON. **A 180 trades / +139.90R / maxDD 45.6% (5.61R) · C 190 / +165.46R / maxDD
  50.7% (6.53R).** ✅ **B reproduced A exactly (180 trades, identical entries), so the 1m clock is
  inert on its own** and C's delta is the re-entries and nothing else — without that control a
  difference in C is a mix of *the re-entries made money* and *the 1m stream nudged the primary*,
  and no arithmetic afterwards separates them, because the two share one position slot. ✅ **Zero
  primaries displaced** (0 in A-not-C, 0 in C-not-A), so the one-slot queue effect did not fire.
  🔴 **Ten re-entries in 7.9 years and 2023-04-03 is +27.33R of the +25.56R total — DELETE THAT ONE
  TRADE AND THE OTHER NINE ARE −1.77R.** ⚠ **On the test that matters here it makes the book WORSE,
  which the total hides**: average R per trade 0.777 → 0.871 with the outlier and **0.731 without**,
  i.e. below baseline, and median R is unmoved (+0.030 → +0.031). **Nine trades that each earn less
  than the average dilute the thing they are added to, and a rising total is exactly what that looks
  like from outside.** ⚠ **It is bought with drawdown: 45.6% → 50.7%.** ⚠ **+25.56R is not evidence
  either way** — the jitter audit put this strategy's run-to-run spread at **sd 15.06R**, so the
  headline is under two standard deviations and rests on one fill. ⚠ **The fat-tail defence does not
  rescue it, and it is worth stating because this repo's own philosophy invites it**: A+ is designed
  to be tail-heavy (5 of 165 trades once made 47% of everything won), so "one trade made it all" is
  not damning by itself — but the primary carries 180 trades and stays positive without any single
  one, while these ten go negative without theirs. **Ten trades cannot tell a small edge from a small
  negative one; that is the same verdict B-LEG got, for the same reason.**
- 🟢 **DEFAULTED **ON** 2026-08-07 AT AARON'S REQUEST, WITH A NEW ONE-PER-PRIMARY CAP — AND THE
  VERDICT ABOVE IS UNCHANGED AND IS RECORDED AS OVERRIDDEN RATHER THAN QUIETLY REVERSED.** Aaron
  read two `SEC` chips on one 2024-12 screen, asked whether one primary could really hand out
  several re-entries (it could), and asked for the cap measured and then shipped along with the
  feature. **The shipped book is now 188 trades / +165.46R / maxDD 5.53R over 7.9 years.** ⚠ **Pin
  `exec_secondary=False` to reproduce ANY figure in this file measured before that date** — every
  one of them is a primary-only book, including the 159 / +142.18R baseline the time stop and the
  EQ/FVG coupling were measured against.
- ⚠ **`exec_sec_once_per_setup` (default ON) — the latch retired the 1-MINUTE leg, so one 15m
  setup could keep handing out fresh legs.** On 2024-12-02 it did: primary 11:30, re-entry 20:08,
  re-entry 01:51 — same 15m SOS bar 7893, two different 1m legs (120399 / 120499), the second
  filling two minutes after the first closed. The cap also retires the 15m SOS BAR on a fill,
  which is one-to-one with the primary because the arm already requires `be_sos == *_sos_bar`.
  ⚠ **Per SETUP, not per lifetime** — a new break of structure re-opens it. ✅ **MEASURED, one real
  replay each over 186,366 M15 + 2,745,711 M1 bars: OFF 190 trades / +165.46R / maxDD 6.53R
  (50.7%) · ON 188 / +165.46R / maxDD 5.53R (45.3%), zero primaries moved.** It fires on exactly
  **two setups in 7.9 years**, removing 2024-01-16 18:44 (−1.000R) and 2024-12-03 01:51 (+1.000R).
  🔴 **The total R matching to fourteen decimal places is a COINCIDENCE — those two are exactly ∓1R
  and cancel — and must not be read as "capping is free by construction"**; on another history the
  second re-entry could be the +27R one. **What is not luck is the drawdown**: the −1R sat in the
  middle of the worst losing stretch, so the capped book is now marginally BETTER than the
  primary-only baseline (5.53R vs 5.61R) where the uncapped one was clearly worse. ⚠ **It does not
  rescue the feature** — eight re-entries instead of ten, April 2023 still carries all of it, and
  the book's average excluding that trade is 0.739R against the baseline's 0.777R.
- 🔴 **NOT EVERY PATH CAN RUN THE SECONDARY, AND THE DEFAULT MADE THAT LOAD-BEARING.** `run_dual`
  has exactly ONE caller (`python_runner`'s single-backtest path). `backtest/optimizer.run_sweep`
  replays one frame, so **the optimizer, sweeps and the stress test's pooled sensitivity have no
  1m stream** — they would have replayed a primary-only book and ranked it against a baseline that
  has re-entries. They **REFUSE** now, naming the fix. ⚠ **`mpc_bleg` had to PIN it False and that
  one is not cosmetic**: A+ never places an order in that fork so there is no primary to follow,
  and `MpcBLegStrategy.run_dual` raises — an inherited `True` would have killed **every B-LEG lab
  run** on a `NotImplementedError`. ✅ The live bot is unaffected: its instance config states
  `exec_secondary: false` explicitly, and `algos/live/bridge.py` refuses the config outright.
- ⚠ **IT HAD NEVER OPENED A POSITION ON REAL DATA BEFORE THAT RUN, AND THREE WEEKS OF GREEN TESTS
  SAID OTHERWISE.** `run_dual` built its 1m signal as a namedtuple without `last_conf_high` /
  `last_conf_low` — the STRUCTURE runner trail's anchors, which the shared `_advance_stage` reads on
  **every** managed bar, primary or secondary — so the first 1m bar after any secondary fill raised
  `AttributeError`. Not a wrong number: the run died. 🔴 **The reason no test caught it is the
  transferable part: `tests/test_secondary.py` hand-builds its own 1m bar as a `SimpleNamespace`
  carrying both fields.** The fixture was more complete than production, so every test exercised a
  shape the code never produced. The regression test now DERIVES the required set by reading
  `_advance_stage`'s own source for `sig.<field>` and asserting the real `run_dual` supplies all of
  them — a hand-written list would have re-frozen exactly the assumption that failed. **Watched red
  against the bug, naming both missing fields.**
- ⚠ **WHERE THE LIMIT RESTS IS NOW A NUMBER (`exec_sec_retrace`, default 0.382), AND SWEEPING IT
  ANSWERS A QUESTION WORTH RECORDING FOR ITS SHAPE RATHER THAN ITS WINNER.** Aaron asked what
  happens if the 38.2% retrace comes out and the re-entry simply takes the 1m SOS. The 0.382 was a
  hardcoded constant; it is a config field now, byte-identical at the default (pinned by the suite)
  and refused outside `[0, 1.0)` at construction — 1.0 is the leg ORIGIN, where the stop is, so an
  entry there has a zero stop distance and the order is silently cancelled, which would report *the
  secondary took no trades* as though that were a finding. ✅ **Four full-history replays, run in
  parallel, with 0.382 as the CONTROL** (it reproduced 190 trades / +165.46R exactly, which is what
  says the refactor moved nothing):

  | retrace | trades | total R | avg R/trade | sec | sec R | its best | other 9+ | W/L |
  |---|---|---|---|---|---|---|---|---|
  | **0.000** (on the SOS) | 192 | +154.38 | +0.804 | 12 | +14.48 | +16.51 | −2.03 | 3/3 |
  | 0.236 | 190 | +159.92 | +0.842 | 10 | +20.02 | +21.91 | −1.90 | 2/3 |
  | **0.382** (shipped) | 190 | +165.46 | +0.871 | 10 | +25.56 | +27.33 | −1.76 | 2/3 |
  | 0.500 | 189 | +170.07 | +0.900 | 9 | +30.17 | +34.01 | −3.84 | 1/4 |

  🔴 **Entering on the SOS is the WORST row and the result is monotonic — deeper is better** — which
  is mechanical rather than mysterious: **the stop is the 1m leg origin whatever the entry**, so at
  0.382 the stop distance is 0.618 of the leg and at 0.0 it is the whole leg. A shallower entry is a
  WIDER stop, hence a SMALLER position for the same risk, and less room between the fill and the 15m
  targets. **You fill more often and each fill is worth less** — +2 trades for −11R. ⚠ **But the
  ranking is one trade and the last two columns say so: strip each row's best and all four are
  NEGATIVE (−2.03 / −1.90 / −1.76 / −3.84).** The sweep is not measuring which entry is better, it
  is measuring how large that April 2023 winner grew as the stop tightened, which is arithmetic.
  **The clincher is the bottom row — 0.5 posts the worst hit rate in the table (1 win, 4 losses of 9)
  and the best total.** Drawdown is flat at 6.53R across all four, because it belongs to the primary
  book. ⚠ **So: do not enter on the SOS, and equally do not read this as a reason to move off
  0.382.** The lever does not change the verdict above; it changes the size of one fill.
- **NOT USABLE LIVE** — `algos/live/bridge.py` REFUSES `exec_secondary` outright
  (`UnsupportedStrategyConfig`), because the live runner drives ONE timeframe and this needs the 1m
  stream alongside the 15m (`run_dual`). The lab can run it; the bot cannot. Building the dual feed
  is a live-pipeline item, and it is correctly gated behind this being measured first.

## The exit ladder — every TP/SL lever, and which ones are switchable

The register of how this bot (and `mpc_bleg`, which reuses the whole ladder) decides where the
stop and the targets sit. Keep it current: a new exit lever in the Pine lands here, in `config.py`,
in `mpc_strategy_export.pine`, and in `compare_strategy.py` in ONE commit.

| Stage | What sets it | Switchable? |
|---|---|---|
| **Stop loss** | A fib on the deep side of 0.5, `exec_sl_level` ∈ {0.618, 0.702, 0.786, **0.886**, 1.0, **Custom**}, then `exec_sl_buf_tk` ticks beyond it. **Default 0.886 since 2026-07-27** (the deep edge of the entry band, and what Aaron trades); 1.0 = the leg origin. **"Custom" (2026-08-02) reads `exec_sl_custom` instead** — any ratio in (0, 1.0]. | **0.886 → 1.0 only** (the dropdown values or any Custom ratio between them) — anything shallower is unsupported, see the warning below |
| **TP1 / TP2** | Fibs, chosen AUTOMATICALLY by how deep the entry was. Deep entry → TP1 = 0.5, TP2 = 0.382. Shallow → TP1 = 0.382, TP2 = 0.0 (the swing extreme). | **No** — only the sizes (`exec_tp1_pct` / `exec_tp2_pct`, **both default 0** since 2026-07-27: bank nothing, ride the runner) |
| **TP3 (the runner)** | No target at all. It rides a trailing stop, and it is where the strategy's money is (>100% of net in every window measured). | **Yes** — see below |
| **Stop staging** | Three phases, always on: (0) the full stop → (1) after TP1, breakeven + `exec_be_buf_tk` → (2) after TP2, a floor, then the trail. | **No** |
| **The breakeven buffer** | `exec_be_buf_tk`, default **30 ticks = $0.30**. How far past the entry the stage-1 stop sits. **SWEPT 2026-08-11 and 30 is the optimum — every wider value is worse, monotonically** (60 → −6.17R, 400 → −35.90R). ⚠ **It does NOT cover the swap and cannot be made to**: one night of long swap is $0.796/oz, 2.7× the whole buffer, so ~29% of scratch exits are net losses on every real account — and widening it costs ~5R of total return per 1R of scratch rescued, because the same move that saves a returning trade cuts a running one. **Do not widen it, and do not make it swap-aware** — Run 17. | **Yes, and it is already at its best value** |
| **The TP2 floor** | `exec_tp2_stop_mode`: **"TP1 price"** (tight, can scratch the runner on the first pullback) / "Breakeven" (most room) / "One trail step behind" (never below breakeven). | **Yes** — dropdown |
| **The runner trail** | `exec_runner_trail`: "Fixed step" (a `exec_trail_step` grid ratchet anchored on TP2) / "Structure (swing)" (park the stop at the structure engine's last confirmed swing low/high, offset by `exec_struct_trail_buf_tk`) / **"Structure + % ratchet"** (same anchor, then climb one `exec_trail_pct`-of-price step per step of favourable move). | **Yes** — dropdown |
| **The ratchet step** | `exec_trail_pct`, default **1.0**. Only read in "Structure + % ratchet" mode. A PERCENT of price, never dollars — see below. | **Yes** |
| **Early bail-out** | `exec_close_opp_sos` (default OFF) force-closes on an opposite SOS instead of riding to the stop. **Measured INERT** (Run 5): turning it on produced a byte-identical trade list — an opposite SOS never fires before SL/TP has already resolved the position. There is nothing on the other end of this lever. | toggle exists, **does nothing** |
| **Deep-entry stop override** | `exec_sl_deep` (default **OFF**, Pine `execSlDeep`, 2026-08-02). An entry filling AT OR DEEPER THAN 0.786 puts its stop at the leg origin (1.0) instead of `exec_sl_level`; 0.702 and shallower keeps the chosen level. It exists because the entry band and the stop share the 0.886 line, so the band's deep end is priced against a stop it is nearly touching. 🔴 **MEASURED 2026-08-16 (Run 18) and it stays OFF: it costs 24.0R with the secondary live and 23.0R without**, on a full 2×2 over one window (2018-09-14 → 2026-08-14, bar fills) — the shipped cell is the best of the four at +164.4R / 189 trades. The mechanism is Run 11's from the other direction: the targets are fibs and do not move, so a wider stop makes every winner worth fewer R while every loss is still −1R (a 0.786 entry goes from a 0.100 stop to a 0.214 stop, the runner falls 7.86R → 3.67R and the position is less than half the size). ⚠ **It DOES hold a shallower drawdown** (−4.8R vs −5.5R) — expensive, not worthless, if drawdown ever becomes the objective. ⚠ **Its interaction with `exec_secondary` is 1.0R against sd 15.06R**, so the two are separable. This is the first direct measurement of the SHIPPED narrow version; the 2026-08-02 revert `mpc_strategy.pine` records was of a WIDER version that also caught 0.702, and the two agree. ⚠ **Its toggle is INERT when `exec_sl_level` is already 1.0** (or Custom = 1.0), because both states then place the same stop; the meta says so with `disable_if` + `disable_note` and the lab greys it, matching the Pine's `active = execSlLevel != "1.0"`. ⚠ **Its OFF label is `Stop {exec_sl_level}` — a TOKEN the editor substitutes, never a typed `0.886`**, which would be a second copy of a neighbouring param's value. | **Yes** — toggle |

🔴 **26 params are marked `hidden` in the meta (2026-08-15) — RETIRED FROM THE EDITOR, NOT REMOVED.** Every field is still in `SosFadeConfig`, still at its default, still sent on every run and still settable through the API; only the row is gone, so the editor is the levers still under test rather than every lever that exists. Aaron's call, and his framing is the rule: *"I don't want you to delete the configurations because I might talk to you, and you might be able to toggle it back on super easy."* **Ask and it comes back — one `hidden` flag.** The set: `exec_longs`/`exec_shorts`/`exec_bleg`/`exec_conf_sz`; `exec_arm_div` and the five RSI engine dials; `exec_poi_source`/`exec_ob_deepen`/`exec_fvg_pre_zone`/`exec_fib_overlap`/`exec_fib_deep_edge`; and the whole `Higher-timeframe filter` group. 🔴 **SEVEN MORE landed the same day under a STRICTER bar, and the bar is the part worth keeping.** The first batch above was chosen on "never moved across every stored run", and Aaron rejected that criterion outright: *"we did backtest with and we proved that they're not worthy or have another setting that beats it consistently. Keep that setting and hide the others."* **Never moved is the ABSENCE of the experiment, not its result.** So the seven each name a sweep in `mpc_sos_fade_optimization.md`: `exec_close_opp_sos` (Runs 5 AND 6 — *exactly 0 difference*, twice; an opposite SOS never fires before SL or TP has resolved), `exec_tp2_stop_mode` (Run 2's 525-combo grid — TP1 price wins at 70.7R, Breakeven is the harmful one), `exec_struct_trail_buf_tk` (Run 2 — 10→80 ticks moves it 0.4R, *"do not chase it"*), `exec_trail_step` (Run 2 — the fixed-step family loses by 8R with no exception, and its `show_if` means the row has never once rendered), `exec_be_buf_tk` (Run 17 — widening it costs 5R for every 1R it rescues on a charged book), and `exec_fvg_deep_only` + `exec_no_late_day` (Run 12 §3 and §4 — two of the four relax routes, all of which lost money or were noise). ⚠ **`exec_sl_buf_tk` is the case that shows the bar biting and it stays VISIBLE**: it WAS in a grid — Run 4 — and Run 4 is marked *INVALID, DO NOT USE THE NUMBERS*, which is worse than untested. ⚠ **The master switches (`exec_arm_sweep`, `exec_aplus`, `aplus_window`), the secondary mechanics and `flat_by_close` have ZERO mentions in the optimization log and therefore stay**, however long they have sat still. ⚠ **`exec_risk_pct` is never hidden on any criterion** — it decides position size on the strategy the LIVE bot runs. ⚠ **The divergence VETO is deliberately NOT in it** — `div_veto` and `exec_respect_veto` are ON and still refusing setups, so the ARM is settled and the behaviour is not; hiding those would take a live rule off the screen. ⚠ **`exec_conf_sz` is not a settled setting but a DEAD one** — declared in `config.py` and referenced only in a comment, so nothing reads it. ⚠ **`exec_req_fvg`, `exec_deep_fib`, `exec_sl_level` and `exec_secondary` stay visible because they have actually been moved on real runs**; a param somebody tunes is a live question whatever it defaults to. ⚠ **Only THREE of the first nineteen carry a sweep** (`exec_poi_source` and `exec_ob_deepen` off Run 15's order-block thread, `exec_htf_exhaust_only` off Run 5's zero-effect pair) — the rest are hidden on Aaron's direct instruction or because they are structural (longs/shorts), which is a legitimate reason and not a measured one. Say which is which rather than letting the next reader assume the whole set was proven. ⚠ **The "never moved" figures behind the first batch came from the 15 `mpc_sos_fade` runs then in the lab (19 now), and that is the whole sample** — older rows were deleted, so it means "nobody has touched these lately", never "never in this strategy's history". Mechanism, and the escape that shows a hidden param moved off its default: `command-center/frontend/CLAUDE.md` → `ParamEditor.tsx`.
| **Minimum stop distance** | `exec_min_stop_mode` ∈ {**"Off"**, "% of price", "Fixed $", "x ATR(14)"} + `exec_min_stop_val` (0.10). An ENTRY filter, not an exit lever — it lives in this table only because it is the guard for the `exec_sl_level` hazard two rows up. A setup whose stop lands closer to the entry than the floor places no order and records block code 7. | **Yes** — dropdown + floor; ported 2026-07-30 |
| **Time stop** | `exec_time_stop_mode` ∈ {**"Off"**, "Before TP1 only", "Always"} + `exec_time_stop_hrs` (36.0). Close a position open for that many CALENDAR hours. **"Before TP1 only" fires only at stage 0** — TP1 never touched, so the stop never staged to breakeven; touching TP1 makes a trade immune for the rest of its life. The exit leg books as `L-TIME` / `S-TIME`. Added 2026-08-05; **defaulted ON ("Before TP1 only", 36h) 2026-08-06 — the baseline moved.** | **Yes** — dropdown + hours; see `### The time stop` |
| **Scale-in (ADD size)** | `exec_scale_in` (default **OFF**) + `exec_scale_mode` (**"Trail"**) + `exec_scale_max_adds` (**3**) + `exec_scale_cap_x` (**0.5**). Past TP2, adds to a runner the trail is already protecting, sized so the add's worst case equals the profit the stop already guarantees. **The only ADDITIVE lever here; every other one is protective.** Added 2026-08-16; defaults re-measured 2026-08-18 after the fill model was corrected. ✅ Four `cfg_*` columns, **parity green**. | **Yes** — toggle + mode + two numbers; see `### Scale-in` |

The floor and the trail compose: past TP2 the stop is the floor, and the trail may only tighten
it further, never loosen it. With Structure selected and no confirmed swing yet, the trail is
absent and the floor alone holds the stop.

**The TP rungs default to 0/0 (2026-07-27) — and 0 does NOT disable the target.** The rung SIZE and
the target PRICE are separate things. At 0 no size leaves at TP1/TP2, but `_advance_stage` still
watches those prices, so touching TP1 still stages the stop to breakeven and touching TP2 still
installs the floor and hands the runner to the trail. The whole position then exits as one runner leg.
This is the shipped behaviour because it is what Run 1 measured as best AND what Aaron actually trades.
`test_zero_pct_rungs_bank_nothing_but_still_stage_the_stop` locks both halves of that.
Python needs no special case (`_remaining_brackets` computes p1 = p2 = 0 and emits neither bracket);
**the Pine does** — `strategy.exit(qty_percent = 0)` closes the WHOLE position, so both Pine files skip
the call when the rung is 0. If you ever port a new rung, port that guard with it.

**`mpc_bleg` overrides TP1, TP2 and the SL** with its own band prices (SL = band origin, TP1 =
the broken swing extreme, TP2 = the expansion extreme). Everything from the staging down —
floor, trail, both dropdowns — is this table, inherited unchanged.

**Aaron's brother's tested best combo (the shipped default 2026-07-26):** Structure trail +
buffer 20 ticks + TP2 floor = TP1 price.

### The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)

**The problem it fixes.** The plain structure trail PARKS the stop at the last confirmed swing.
That swing is a LAGGING anchor: in a strong leg it ends up a long way behind, and the gap between
it and the high IS the runner's give-back. Measured over 6.6y / 164 trades (XAUUSD 15m, SL 0.886):
the strategy banked **27.5% of the total profit it ever showed open**, and on the 78 trades that
ran ≥$10 of gold it captured $2,283 of the $5,300 they moved — **57% handed back**.

**What it does.** Same anchor (`last_conf_swing ± exec_struct_trail_buf_tk`), but from there the
stop climbs one `exec_trail_pct`-of-price step for every step of favourable move. It falls back to
the bare anchor until the move is one full step past it, so it is **never LOOSER than the plain
structure trail — only equal or tighter** (`test_swing_ratchet_is_never_looser_than_the_plain_structure_trail`).

**Measured, vs the plain structure trail** (same 6.6y window, same 164 trades, same entries):

| | order-free edge | net | run actually banked | max DD |
|---|---|---|---|---|
| Structure (swing) | 107.6R | $2.82M | **43%** | 54.7% |
| Structure + 1% ratchet | 109.3R | $3.81M | **53%** | 54.7% |

⚠ **Both rows were measured at `exec_tp1_pct = exec_tp2_pct = 1`, NOT at the shipped 0/0** (found
2026-07-28). The A/B is apples-to-apples so the comparison stands, but the absolute figures are not
the shipped configuration: at the true 0/0 default the same window gives **110.65R**, and the 1%+1%
rungs cost 1.4R. Quote 110.65R as "the current bot", not 109.3R — and run `compare_strategy.py` at
0/0 so the parity gate tests what the Pine actually ships.

**Read this honestly.** The EDGE is unchanged — +1.7R over 164 trades is noise, and 1.5% (106.3R)
/ 2.5% (110.4R) bounce either side of it, which is the signature of randomness rather than an
optimum. What is real is the 10-point jump in how much of each run survives to the close, and it
costs nothing: **percentage drawdown is IDENTICAL (54.7%, same day)** — the bigger DOLLAR drawdown
in an early write-up was a compounding-account artifact, not a risk increase. Only 11 exits change:
8 better (+13.2R), 3 worse (−11.5R), and ONE trade (2025-10-21, +25.23R → +16.27R) is nearly the
whole downside.

**Why PERCENT and not dollars.** Gold ran 1,500 → 3,400 across the test window, so no fixed $ step
is right at both ends ($20 is a 1.3% trail at 1,500 and 0.6% at 3,400). The dollar version tops out
at **100.4R vs the percent version's 109.3R** for exactly that reason, and it only ever climbs
toward the plain structure trail as the step widens — in dollars this dial cannot beat what it
replaced. Do not "simplify" it back to a $ step.

**Do NOT add a hard take-profit on top of it.** Tested (2026-07-28): a target is either too loose to
fire (40R was byte-identical to no target — no trade in 6.6y ever reached it) or tight enough to cut
the tail that IS the profit (15R → 86.4R, a fifth of the edge gone). The 25R row looks best on the
table and is three lucky trades — only 3 of 164 ever reached 25R peak. There is no useful middle.

**Extension fibs (NEGATIVE fibs past 0.0) — measured 2026-07-28, REJECTED in every form.** This is
the most natural-looking idea on the list and the one Aaron trades by hand, so it gets its own record
rather than a line in the list below. Past the 0.0 fib the runner has no target at all, so the
proposal was to bank at the standard extensions the way a discretionary trader would.

*As TAKE-PROFIT rungs, shallow* (0.0 / −0.272 / −0.414 / −0.618, all off at −0.618 — Aaron's hand
rule): **109.3R → 69.1R**, a third of the edge gone. Every one of 14 allocations lost, and the
ranking was perfectly monotonic in how much was banked — the limit of "bank less" is the shipped
runner. Best of them (50% at −0.618 only) still only reached 92.4R.

*As a STOP FLOOR* (bank nothing, but ratchet the stop up the extension ladder one rung behind price):
**worse than the targets — 109.3R → 56.1R at best**, roughly half the strategy. A fib level is a
FIXED price and does not breathe; the structure trail moves with the market and survives an ordinary
retrace, a horizontal line does not. The 23.5R trade became 10.5R, cut on a pullback six legs before
it actually finished. Same lesson as every other tightening experiment above.

*As DEEP rungs* (−1 / −2 / −3 / −4 / −6 — take nothing until the trade is already a monster, then
trim): far better than the shallow version and still not an improvement. Aaron's −1:10% / −4:50% /
−6:rest ladder = **106.3R**. The only rows that beat the baseline sit at −6, and **exactly ONE trade
in 6.6 years ever reached −6** (−6 take 100% = 112.2R, i.e. +1.55R over the true 110.65R baseline,
from a single 2020 trade). That is a description of July 2020, not a rule.

**The pattern, and why there is no ceiling to find.** Rule cost tracks how OFTEN the rule fires:
−1 touches 8 trades and costs 7–14R, −4 touches 2 and costs 1–3R, −6 touches 1 and costs nothing.
Every candidate converges on the baseline from below as it stops doing anything. There is no depth
at which banking becomes profitable — there is only a depth at which it becomes harmless.

**The shape of the book, which is the real reason.** Of 164 trades only **29 ever reach the 0.0 fib**,
11 reach −0.618, 8 reach −1, 2 reach −4, 1 reaches −6. Those **11 trades past −0.618 make 106R of the
109R total**. The two biggest ran to −4.77 and −6.74 and the trail paid −3.69 and −5.68. Any fixed
ceiling is applied to every trade, so it necessarily caps the handful that carry the strategy. Eight
trades DO run past 0.0 and hand the whole extension back (they exit at the 0.382 floor) — that leak
is real, but it is worth 5.7R and the cheapest rule that plugs it costs 17R.

**Four other exit ideas measured and REJECTED the same day, so they are not re-tried:** tightening
the trail in any form (fixed step $2–$40, chandelier 2–8×ATR, giveback caps 25–50%) costs 60–90% of
net; banking at the TP rungs (25/25, 33/33, 50/0) costs 60%; "stay loose then clamp once it is a
monster" (>3R/5R/8R/15R → a tight trail) costs 20–45%; and exiting on an opposing RSI divergence past
TP2 costs 77% — only 18 of 164 trades ever print one, the six biggest give-back trades print ZERO,
and where it does fire it fires 2–4 times so you can only ever act on the earliest and worst one.

**⚠ `exec_sl_level` — `"0.886"` (the default since 2026-07-27) and `"1.0"` only. Do NOT sweep or
ship 0.618 / 0.702 / 0.786** (Run 4, 2026-07-26). The entry is a resting limit inside the
**0.5–0.886 fib band**, and all four sub-1.0 levels sit inside that SAME band — so the stop can be
placed at, or past, the entry price. Nothing validates the result.

### Scale-in (`exec_scale_in`, 2026-08-16) — the first ADDITIVE lever this bot has ever had

**Every exit family swept here before this one was PROTECTIVE** (Run 8 alone killed ~50 tightening
variants, Run 9 rejected banking in every form). This one adds SIZE to a runner the trail is already
protecting, and a grep for pyramid/scale-in across the repo returned nothing before it.

**The rule, and it is a SIZING rule rather than a timing one:**

```
locked   = (stop - entry) * base_qty     profit the stop already guarantees
per_unit = (price - stop)                what one extra unit risks to that SAME stop
add_qty  = min(locked / per_unit, base_qty * exec_scale_cap_x)
```

Stop out right after adding and the two cancel — the base banks `locked`, the add gives back at most
`locked`. **An add can shrink a winner; it cannot manufacture a loser.** The guarantee is arranged in
advance by SIZE, never detected in real time.

🔴 **THE TRIGGER IS THE TRAIL (stage 2), NOT A TARGET, and that is what makes it self-regulating.**
At TP2 the stop is only at TP1, so `locked` is small while `price - stop` is large and the affordable
add is a rounding error. Once the trail ratchets up near price the same arithmetic permits a LARGE
add. A trending runner buys size; a stalling one buys nothing, with no extra "is this trade still
good" test.

**MEASURED 2026-08-16 (Run 19) — XAUUSD 15m, 2018-09-13 → 2026-08-14, PU Prime ECN costs charged:
off 182 trades / +128.26R / 6.03R maxDD / 65 losers, and 2 adds at cap 1.0x gives +211.59R (+65%) /
8.72R maxDD / 67 losers with the WORST TRADE UNCHANGED at −2.06R.** Return-per-drawdown 21.27 →
24.26. **Dropping the affordability test and adding a flat 1x instead costs 8–13 extra losing
trades — that difference is what the `locked / per_unit` line buys.** Full grid, the free-of-costs
pair whose losers are bit-identical, and the two families that closed NEGATIVE the same day (ATR
stop distance, regime filtering): `mpc_sos_fade_optimization.md` → Run 19.

⚠ **+83R is well outside this strategy's 15.06R run-to-run jitter, so the direction is real** — but
it is one window on one instrument, and the gain is concentrated in the runners that already carry
this book. **It does not widen the edge; it levers the tail that was already there.**

🔴 **THERE IS NO STRUCTURAL TRIGGER IN IT AT ALL, AND THAT IS AN OPEN DESIGN QUESTION rather than an
oversight** (Aaron, 2026-08-16: *"I don't know what market structures I'm looking at to add into"*).
The rule asks only *can I afford this*, never *is this a good place*. Structure enters INDIRECTLY —
the trail is parked on the last confirmed swing, so an add fires roughly when a new HL/LH confirms —
but that is a side effect of the trail's anchor, not a rule anyone chose, and it enters at MARKET on
the bar the trail moves, which is the worst price of the leg where the BASE entry rests a limit in a
discount zone and waits. Adding on a fresh BOS, on a retest of the broken level, or at a limit on
the new leg's retrace are all untested alternatives. **Location has never been varied.**

⚠ **Adds are separate LOTS, not extra `_qty`.** `_exit_portion` prices the whole position off ONE
`_entry`, so growing `_qty` would value added units as if bought at the original entry and invent
profit. Each lot closes pro-rata with the base and pays its own commission and spread.

⚠ **`_entry`, `_risk_usd` and `stop_distance` stay anchored to the BASE fill, so R is scale-free and
every row stays comparable to a run with this off.** A scaled trade's "3R" is NOT 3x the capital an
unscaled 3R had at work. It is also why the real implementation reproduced the shadow-ledger harness
to −0.00R, which was predicted to diverge and did not.

⚠ **THE GUARANTEE HOLDS TO THE STOP, NOT THROUGH A GAP.** Price jumping past the stop fills the whole
combined size at the open, and 3x the size loses 3x. Nothing here protects against that.

⚠ **NO ACCOUNT-LEVEL CAP EXISTS.** Net risk-to-stop is ≤ 0 by construction, but margin and
`run_stack`'s risk budget both see the FULL position. `docs/LIVE_TRADING_PIPELINE.md` → G10: the live
allocator is unbuilt, **so this must not go live before it is.**

✅ **VERIFIED TWO WAYS, and the first is the one that matters on a LIVE strategy.** The OFF path is
bit-identical to the costed control measured before the feature existed — 128.26R / 6.03 maxDD / 65
losers / −2.06R worst, all four — so a toggle whose OFF path moved the numbers would have failed.
ON at 2 adds reproduces the harness figure it was decided on (211.59R vs 211.59R, diff −0.00R).

🔴 **NO PARITY GATE HAS RUN.** The Pine side is built (`execScaleIn` / `execScaleAdds` /
`execScaleCapX`, and `pyramiding` raised 0 → 4, which is compile-time and cannot be an input), but
`compare_strategy.py` needs a fresh TradingView export only a human can take, and the export carries
no `cfg_*` column for these three yet. **Until both land, an ON result is a LAB finding** — and per
this file's own standing lesson, a trade-affecting input with no export column is invisible to the
gate BY CONSTRUCTION, so the gate would go green while comparing two different strategies.

### Scale-in gained a MODE — and the first answer was measured on a broken fill (2026-08-18)

`exec_scale_mode` ∈ {`"Trail"`, `"BOS retest"`}. **Trail** adds at MARKET on the bar the trail
ratchets. **BOS retest** waits for the next confirmed break of structure our way and RESTS A LIMIT
at the level that break cleared. The SIZE rule is untouched by either; only the moment and the
price move.

🔴 **THE 2026-08-17 DEFAULTS WERE WRONG AND ARE REVERSED. Every Run 20 figure is VOID.** That sweep
booked each add at the price its RULE TRIGGERED on, and Pine buys it somewhere else — a market
order fills at the NEXT bar's open, a resting limit fills when price comes back. So the harness
credited `BOS retest` with the retest level itself on every fill, which is exactly the price that
mode has to WAIT for and frequently never gets. **On the corrected fill the ranking INVERTS.**

**THE PARITY GATE IS WHAT CAUGHT IT** — `px_closed_r` at bar 1356, 2025-10-21: py **27.07R** vs
pine **22.03R**, one trade, on the largest runner in the book. Every decision field before it
agreed, and both books were internally consistent. ⚠ **A backtest that prices a fill at the moment
its rule FIRED is measuring a DECISION, not a TRADE, and nothing in the output can show you that.**

🔴 **THE BUG ALSO BROKE THE FEATURE'S ONE GUARANTEE, which is the more serious half.** The
affordability arithmetic is written against the price the add is BOUGHT at; a market order is sized
at one price and filled at another. **MEASURED over the same 182 trades: the market-order add
turned winners of +3.41R and +1.34R into losses of −2.50R and −2.15R, against an un-scaled worst of
−2.06R.** A resting limit closes it — the fill price is known before the order is sent, and price
that GAPS through a buy limit fills BETTER. ⚠ **`Trail` is a market rule by nature and keeps a
small version of the gap: zero breaches at 3 adds, −2.24R and −2.73R at 4.** That is why the add
count ships at 3, and zero observed is not zero possible.

🟢 **SHIPPED 2026-08-18 after a 32-cell re-run: `exec_scale_mode="Trail"`, `exec_scale_max_adds=3`,
`exec_scale_cap_x=0.5`.** Scored on the 2020-FREE book, because 2020 is ~1/3 of the all-period
figure and scaling roughly TRIPLES its contribution:

| | ALL R | dd | ret/DD | EX20 R | ret/DD |
|---|---|---|---|---|---|
| no scaling | 128.26 | 6.03 | 21.27 | 92.51 | 15.34 |
| **Trail 3 × 0.5x** | **194.15** | **7.24** | **26.81** | **124.05** | 11.99 |
| BOS retest 4 × 2.0x | 180.44 | 9.20 | 19.61 | 80.90 | 8.79 |

⚠ **`BOS retest` LOSES MONEY outside 2020 at every budget above one add** — down to −14.15R against
not scaling. It is kept as an option because it is implemented, gated and parity-green, **not
because any measurement supports it.**
⚠ **The CAP is the drawdown lever, not the add count.** Same 3 adds: ex-2020 drawdown 10.34 → 17.02
→ 22.99 → 24.56 across 0.5x / 1.0x / 2.0x / 3.0x. Adds are nearly free; SIZE is what hurts.
⚠ **NO CELL BEATS NOT-SCALING'S 2020-FREE ret/DD OF 15.34.** Scaling reliably buys return and
reliably pays in drawdown. This is the cell where that trade is closest to fair and the only one
better than baseline on BOTH axes over the full book. **Quote both halves.**
⚠ **LADDER SHAPE IS NOT MEASURABLE and the intuition behind it is wrong here.** At a fixed 1.5x
total, big-first 199.27R / flat 194.15R / small-first 183.96R — inside the 15.06R jitter. Risk on an
add is measured to the STOP, which trails up behind price, so the LAST add is the cheapest, not the
riskiest; small-first in fact had the lowest drawdown.

⚠ **`exec_scale_mode` REFUSES an unrecognised value** rather than falling back, same standing as
`exec_sl_custom`. ⚠ **`exec_scale_in` is still False, so the OFF path is byte-identical at 128.26R
and no other figure in this file moves** — what changed is what the toggle DOES. **Pin
`mode="Trail", adds=2, cap=1.0` to reproduce Run 19's 211.59R.**

✅ **PARITY GREEN 2026-08-18** — exit 0 on a fresh 20,799-bar export taken at `cfg_scale_in=1 /
cfg_scale_mode=1 / cfg_scale_adds=4 / cfg_scale_cap=2`, i.e. one that genuinely exercises the
feature rather than reading all zeros. **The same gate on the same schema was RED at bar 1356
before the fix**, which is what makes the green worth something.

⚠ **`algos/live/bridge.py` REFUSES `exec_scale_in` outright** — it mirrors one entry limit and one
ratcheting stop and has no path that places a second entry. **This cannot go live until the bridge
learns to place adds AND the account allocator exists** (margin sees the full stacked position even
though risk-to-stop does not).

🔴 **OPEN, and it is the next question worth money: an add has NO TARGET.** It rides the same
trailing stop as the base — but the base earned a runner by being a reversal bought at a discount
after a sweep and a structure shift, and an add has none of that behind it. Banking adds at a
target, structural or otherwise, has never been tested; the liquidity engine already emits previous
day/week levels and session highs and lows and the execution layer reads none of it.

Full grid, the ladder-shape test and the void banner: `mpc_sos_fade_optimization.md` → Run 21.

### The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`, 2026-08-05)

Aaron's ask, and it started from the right question rather than from a rule: *"what number could we
draw a line at and say if a trade is dancing around by this hour, cut it, to minimise our
drawdown."* The lever exists; **the evidence for the number does not yet, and that distinction is
the whole of this section.**

**What it does.** `exec_time_stop_mode = "Before TP1 only"` closes a position that has been open
`exec_time_stop_hrs` calendar hours **and is still at stage 0** — TP1 never touched. `"Always"`
drops the stage gate and closes on the clock alone. `"Off"` closes nothing. **"Before TP1 only" at 36h became the DEFAULT
on 2026-08-06 (Aaron's call), so the baseline moved — 159 trades / +137.94R / maxDD 7.99R →
159 / +142.17R / maxDD 5.62R. Pin `exec_time_stop_mode="Off"` when reproducing any run measured
before that date.** The exit leg books as `L-TIME` / `S-TIME` so it is countable in the lab
rather than hiding inside the ordinary force-close bucket.

**Why the milestone is TP1 and not something else.** Over the 161-trade window
(2020-01-01 → 2026-08-03, run `75ccc776d10c`) the TP1 line splits the book perfectly:
**105 trades reached TP1 and not one of them lost; all 56 that never reached it lost.** That is
structural, not a coincidence — touching TP1 stages the stop to breakeven, so a trade past that
line cannot take a full loss. The clock is therefore only ever asked about trades still at risk.

⚠ **Breakeven was the obvious alternative and it is INERT — measured, not assumed.** The entry is
a RESTING LIMIT, so price is sitting at the entry the moment it fills and the next bar's wick
crosses back over it: **161 of 161 trades touch breakeven, median 0.25h — one bar.** By hour 8 the
share of losers that have not returned to breakeven is **0%**. A breakeven-gated time stop fires on
nothing at any usable cutoff, and the sweep confirms it (0 trades cut at every H ≥ 8).

**MEASURED BY REAL REPLAY — 155,440 M15 bars (2020-01-01 → 2026-08-03), one full replay per row,
at today's shipped defaults** (which include `exec_min_stop_mode = "% of price"` 0.08, so the
baseline is **159 trades / +137.94R**, not the 161 / +135.94R of the pre-guard run `75ccc776d10c`):

| cut at | mode | trades | total R | max DD (R) | cut by the clock |
|---|---|---|---|---|---|
| — | **Off (shipped)** | 159 | **+137.94** | **7.99** | 0 |
| 24h | Before TP1 only | 159 | +140.22 | 5.54 | 10 |
| 30h | Before TP1 only | 159 | +142.05 | **5.37** | 7 |
| **36h** | **Before TP1 only** | 159 | **+142.18** | 5.61 | 6 |
| 40h | Before TP1 only | 159 | +142.59 | 5.60 | 6 |
| 48h | Before TP1 only | 159 | +140.10 | 7.34 | 4 |
| 36h | **Always** | 159 | **+97.27** | 5.91 | 26 |

✅ **RE-RUN 2026-08-06 and this table is the corrected one.** It was measured twice over: once
before the one-bar force-close fix, and once before `eq_exempt_fvg` reached the Python side. Both
were real reasons to distrust it and **neither moved it** — every row shifted by ≤0.05R and the
trade counts, the cut counts and the plateau are unchanged. Recorded because "we re-measured and
nothing moved" is a result; a table nobody re-ran after two known-relevant fixes is not.

**24h–40h is a PLATEAU, not a peak, and that is the only reason 36 is defensible.** Roughly the
same R and the same drawdown across a 16-hour band describes the trade population rather than
fitting it; 36 sits mid-plateau deliberately.

🔴 **"Always" is the row that justifies the stage gate, and it is not close: +137.94R → +97.32R,
a THIRD of the edge gone.** Same clock, same 36 hours — the only difference is that it also cuts
trades that had already reached TP1. It cuts 26 where the gated version cuts 6, and the 20 extra
are the winners. **The clock is not the lever; the stage gate is.** This is also why nothing below
~16h works: **losers here die FASTER than winners** (median hold — losers 2.0h, winners 17.8h), so
the stop is already the fast exit and the clock can only ever catch the tail that lingers.

✅ **The queue effect did NOT materialise, and that is a measured result rather than an
assumption: the trade count is 159 in EVERY row, including the "Always" run that cut 26 trades.**
This was the live risk on the whole exercise — with one position slot, a trade cut at 36h frees the
slot early and setups no arithmetic can see would have entered in its place, which is exactly how
the minimum-stop guard's cheap estimate got its SIGN wrong (+1.84R estimated, **−1.84R** replayed).
Here the naive re-pricing and the real replay agree on the delta to the cent (+4.23R at 36h),
because the trade list genuinely did not reshuffle. ⚠ **Read that as a fact about THIS window, not
as a general licence to re-price instead of replaying.** The reason it holds is mechanical and
narrow: A+ takes ~2 trades a month, so a slot freed 60 hours early usually contains no setup at
all — and an ENTRY-side change like the min-stop guard frees the slot at the exact moment a setup
exists, which is precisely when a competitor is nearby. **An exit-side lever and an entry-side
filter are not the same risk, and the next lever still gets replayed.**

⚠ **Do not read the +4.23R as edge.** `backtest/tools/jitter_audit.py` measured this strategy's
run-to-run spread at **sd 15.06R**, so +4.23R is a quarter of one standard deviation. **The case
for this lever is the DRAWDOWN — 7.99R → 5.62R at 36h, a 30% reduction, and 5.38R at 30h — and it
rests on 6 trades in 6.5 years.** That is a real improvement in the number a risk budget is set
against, bought for R that is indistinguishable from noise; it is not a profit lever and must not
be sold as one.

**Where it lives.** `_time_stop_due()` in `execution.py`, fired from the same Phase-B `elif` chain
as `exec_close_opp_sos` and `flat_by_close`, so the three force-close paths keep one precedence.
The clock is `sig.time_ms - self._entry_ms`, i.e. from the FILL — a limit can rest for days, and
charging that waiting time against the trade's life would close positions that had barely opened
(`test_the_clock_runs_from_the_FILL_not_from_the_bar_the_limit_was_PLACED`). `_stage == 0` is the
existing state rather than a new flag, because stage 1 IS "price touched TP1"; deriving it a second
way would be a second claim about one event.

⚠ **Calendar hours, weekends included** — the same basis the swap is charged on, and the one a
reader can check against a chart without knowing which hours the market was open. A Friday-to-Monday
hold advances the clock by the whole weekend on a handful of bars, which is deliberate and pinned.

⚠ **`mpc_bleg` INHERITS it, unlike the minimum-stop guard which that fork pins Off.** The lever
lives in the parent's `step()`, which `BLegExecution` delegates to, and both bots share ONE exit
ladder. `indicators/strategies/mpc_b_leg_strategy.pine` got the identical inputs in the same commit so the two
sides cannot drift. **But the 24h–40h plateau was measured on A+ trades only** — a B leg waits for a
LATE retrace by construction, so treat any value there as untested until it is replayed.

⚠ **The Pine inputs are declared next to the exit block, not up in the GRP_EXEC panel**, and that
must not be tidied up: TradingView keys saved input values off DECLARATION ORDER within each type,
and the last `input.float/string/int` in `mpc_strategy.pine` is `execBeBandR` (~4050), so declaring
the pair down at the exit block shifts **nothing**. Inserting them beside their siblings at ~483
would silently reset every later string and float input on every chart running the script.

✅ **PARITY VALIDATED 2026-08-06, AND GETTING THERE TOOK THREE EXPORTS AND FOUND A REAL BUG.**

- **Round 1, mode Off** — worthless by construction, exactly as this section had warned.
- **Round 2, mode ON at 36h** — `compare_bleg.py` exit 0, and it proved NOTHING: the clock fired
  **zero times**. At 36h the lever fires ~6 times in 6.5 years, so no export a human takes will
  reach it.
- **Round 3, mode ON at 4h** — the clock fires constantly, and the gate went **RED on its first
  exercised bar.**

🔴 **The bug it found is a one-bar fill error, and it was in the port from the first line.**
`_close_at(sig, sig.close, ...)` closed the position at the DECIDING bar's close. Pine's
`strategy.close()` is a MARKET order, so it cannot execute on a bar that has already closed — it
fills at the NEXT bar's open. Measured on real bars: Python booked bar 696's close **3651.28**,
Pine booked bar 697's open **3651.23**. The force-close is now held as `_pending_close` and filled
at the next bar's open, ahead of any stop or target, which is the order TradingView executes in.

⚠ **The same defect was already sitting in `exec_close_opp_sos`**, which is the other
`strategy.close()` in the Pine. It defaults OFF and has never appeared in a parity export, so it
was corrected by inference from the time stop's measured evidence rather than by its own. **The
one force-close that is NOT deferred is `flat_by_close`** — it has no `strategy.close()` behind it
(no Pine input exists) and its entire purpose is to be flat before the daily close, so deferring it
to the next open would carry the position overnight and charge the swap it exists to avoid.

🔴 **The second bug was in the HARNESS, and it is the more dangerous shape.** `_py_row` mapped a
force-close to `px_exit_run` by matching `endswith("CLOSE")`, so the new `L-TIME` / `S-TIME` leg
matched nothing and the tool reported `py=None pine=3855.13` — **a manufactured mismatch, in code
that was correct to the cent.** It now selects "any exit that is not a TP rung", so a future leg
name cannot reintroduce it. **A parity tool that must be taught every new leg name will fail this
way, and it fails by accusing the strategy.**

**After both fixes:**

| gate | result | clock exits in the window |
|---|---|---|
| `compare_bleg.py` | **exit 0** | 1 |
| `compare_strategy.py` | clean to bar 11031 | **6** (2 long, 4 short) |

Bar 11031 is the pre-existing minimum-stop divergence recorded above, unrelated to this lever and
red before it existed. Every clock exit before it matches Pine bar-for-bar and price-for-price.

⚠ **A THIRD probe bug is worth recording, because it is this section's own lesson eating itself.**
The script that counts clock exits read `getattr(t, "exit_name", "")` — a field `Trade` does not
have — so it returned `0 closed BY THE CLOCK` for **every** export, including the one where the
clock fired 12 times. The field is `exit_reason`. **The exercise check written to catch
"green on a branch neither side entered" was itself silently answering zero**, and a zero from a
broken counter is indistinguishable from a zero from an unexercised branch. Read the field
directly so a rename raises; never `getattr` with a default in a check whose whole job is to
notice absence.

✅ **THE SWEEP WAS RE-RUN 2026-08-06 AND THE TABLE ABOVE IS CORRECTED** — every row shifted by
≤0.05R, the trade counts and the plateau are unchanged. It had been stale twice over (the one-bar
force-close fix here, and `eq_exempt_fvg` reaching the Python side the same day) and neither moved
it. Quote the table freely now.

⚠ **Re-export at 4 hours after any change to this lever.** 36 is the shipped value and is
untestable on a normal chart; 4 is the same code path and exercises it dozens of times.

### ✅ CLOSED — the A+ parity failure was the EQ/FVG coupling, not the entry rule (2026-08-06)

**The symptom**, on a 21,999-bar `VANTAGE_XAUUSD, 15m` export, at every warmup 100 / 500 / 1000 /
2000:

```
bar 11031  2026-02-18 14:30  px_edge:  py=4990.02  pine=4965.73
```

Same fib leg on both sides (`dbg_fib_ash` 5052.77 / `dbg_fib_asl` 4842.20), same stage, same
`px_dec_bits`. Python rested at **fib 0.702 exactly**; Pine at **0.5866 of the leg**, which is not
a rung, so Pine was resting on a GAP EDGE. It reads exactly like the two sides taking different
branches of the entry model.

🔴 **They were not. `_fib_snap` is line-for-line identical on both sides, and the gap Pine rested
on did not exist in Python at all.** Dumping the live gap list at that bar found Python holding
five gaps and Pine holding a sixth — a bearish gap `[4965.73, 5060.25]` born 143 bars earlier,
which Python had FIFO-evicted and Pine had kept because it sits on an active EQH/EQL.

🔴 **The cause is `eqExemptFvg`, and the shape of it is the lesson.** That input exempts a gap
behind resting liquidity from the FVG cap. It **defaulted ON in `mpc_strategy.pine` on 2026-08-03**
(`b1b461b`), while on the Python side `backtest/replay/EngineStack` **built no EQ engine and passed
no levels to the FVG engine at all** — so the coupling could not fire even in principle. The two
implementations were evicting different gaps for three days.

🔴 **And no `cfg_` column carried the input, so the gate could not see it — it diffed two different
strategies and blamed the entry rule.** The Pine's own comment block, eight lines above the input,
still said *"THE EXEMPTION DEFAULTS OFF HERE"* and warned that neither the port nor the export
modelled it. The default was flipped and the warning was not.

**Fixed in four places, all in one commit:** `EngineStack` builds an `EqualHighsLowsEngine` and
feeds its levels to the FVG cap; the FVG engine's cap counts **ordinary gaps only** (it was still
on the self-cancelling SWAP rule the Pine fixed on 2026-08-03); `mpc_sos_fade` pins
`eq_exempt_fvg=True` and `mpc_bleg` pins it False (that fork's Pine keeps it off); and both export
Pines plot **`cfg_eq_exempt`**, which the harnesses now configure from.

✅ **GREEN at warmups 100 / 500 / 1000 / 2000**, and non-vacuously so — that export ran the live
`exec_min_stop_val = 0.08` and the time stop at **4 hours**, which closed **12 of its 26 trades**.
`--eq-exempt off` reproduces the original mismatch at bar 11031 exactly, so the fix is not masking
anything. `compare_bleg.py` exit 0 at 100 / 800 / 2000.

⚠ **The previous diagnosis in this file was WRONG and is recorded as wrong.** It read the failure
as `cfg_min_stop_val` going 0.30 → 0.08 "revealing" a pre-existing entry-rule disagreement. The
0.30 export really is green and every 0.08 export really is red, but that is export TIMING — the
0.30 export was taken before the Pine's default flipped. **Two changes landed within days of each
other and the visible one got the blame.** Forcing the Python floor across 0.0 / 0.05 / 0.08 / 0.10
never moved the diverging bar, which should have been read as *the floor is not involved* rather
than as *the floor is revealing something*.

✅ **MEASURED, and this is the counter-intuitive half: the coupling is heavily exercised and
changes no trade.** Over 155,531 M15 bars (2020-01-01 → 2026-08-03), **155,145 bars hold an active
EQ level, 92,984 hold at least one EXEMPT gap, and 20,546 hold MORE than the cap of 7** (max 12 at
once — the same maximum the Pine commit measured independently). Yet A/B over that window gives
**159 trades / +142.18R / maxDD 5.61R either way, with an identical entry set.** It moves the
RESTING LIMIT on **463 bars (0.30%)** — sometimes creating an edge where there was none — and not
one of those 463 ever became a different fill.

⚠ **So the honest summary is: the feature is real, it is exercised constantly, it changes where the
limit rests, and over 6.5 years it has never changed a trade.** Do not restate that as "it does
nothing" — the exercise counts are what make the second half a measurement rather than an
unentered branch, and this is one window on one instrument.

**The standing lesson is one this repo keeps meeting from new directions, and this is its sharpest
form: a trade-affecting input with no export column is invisible to the parity gate BY
CONSTRUCTION — and the gate does not go quiet, it goes WRONG, accusing whichever code the symptom
happens to land in.** `execRunnerTrail` (2026-07-26) and `cfg_min_stop` (2026-07-30) were the same
shape and were both caught before they cost anything. This one was caught after three days and a
misdiagnosis, because the missing column was for an input somebody else had already written a
warning about. **A comment saying "this defaults OFF" is not a guard; the column is the guard.**

### The Custom stop level (`exec_sl_custom`, 2026-08-02)

Aaron's ask: *"let me enter a fib level as a stop loss outside of the predefined ones, as long as it
falls between 0 and 1 — 0.90 instead of 0.886."* The five-value dropdown had no answer, and a stop
is a PRICE, not a member of a set. `exec_sl_level = "Custom"` reads `exec_sl_custom` (a ratio in
(0, 1.0], default **0.886**) instead of a fiboP*.

**Where the price comes from.** `Signals` has carried `fibo_ash` / `fibo_asl` — the leg anchors the
fiboP* were built from — since `e2140c3`, with a comment naming this feature as the one consumer.
`_sl_anchor` feeds them to the canonical `engines.fibonacci.geometry.fib_level()`, the same helper
and the same IEEE-754 path the fib engine used, so **Custom 0.886 is bit-identical to picking
"0.886"** and switching the mode alone moves nothing. That equality is a test
(`test_custom_at_a_dropdown_value_is_the_SAME_price_to_the_last_bit`), on a bear leg too.

**Which half of the range this opens, and which half it must not.** 0.886 → 1.0 is the safe half and
the reason it exists: deeper stop, smaller position, more room before the setup is wrong — and it is
exactly the gap the ladder never covered. **Shallower than 0.886 walks straight back into Run 4's
hazard**, now reachable at any ratio rather than only at three: a stop shallower than the fill either
fails `dist > 0` (the order is cancelled, no trade and no tag) or leaves a tiny `dist`, and
`qty = risk / dist` balloons the position. Turn `exec_min_stop_mode` on first.

**An out-of-range ratio raises at construction, it does not fall back.** `SosFadeConfig.__post_init__`
refuses anything outside (0, 1.0] when — and only when — the mode reads it. The tempting alternative
was `_sl_anchor`'s existing shape (an unrecognised level falls through to fib 1.0), and that is the
wrong answer for a number a human typed: it would replay a whole backtest against a stop nobody
chose and report it as theirs. Validating only under `"Custom"` is deliberate too — the optimizer may
sweep `exec_sl_custom` behind a fixed mode, which is a wasted grid but not an error.

⚠ **NO PINE COUNTERPART, so a Custom run is unvalidated.** `mpc_strategy.pine`'s `execSlLevel` is an
`input.string` with five options; `compare_strategy.py` decodes `cfg_strcodes` into those five and
can therefore never configure a Custom run, which is also why parity is structurally unaffected by
this change. **A Custom result is a LAB finding, not a validated one** — port the input to the Pine
(a new `input.float` + a `cfg_` column + a `_SL_LEVEL` branch) before trading one. Note this is the
first lever in the exit ladder to be Python-first; every other one landed in the Pine first.

**In the lab:** the Stop level dropdown gains a "Custom" option and a numeric field appears under it
(`show_if`), the same pattern `exec_min_stop_mode` → `exec_min_stop_val` already uses. Because it is
a numeric field it is also a real **numeric optimizer axis** — sweep 0.88 → 1.00 step 0.01 and the
grid walks it, which a list of five strings never could.

**Why 0.886 is nonetheless the shipped default.** It is what Aaron trades, the 2026-07-27 parity
run went GREEN at it, and Run 6 rode it over the broker's whole intraday history (188 trades,
107.7R, 293x, −54.9% maxDD) with no degenerate stop. That is 0.886 being the SHALLOWEST point the
entry limit can itself rest at — the stop is just past the deep edge of the band, so the collapse
mode needs the entry to fill at almost exactly 0.886. **It is evidence of absence, not a
guarantee:** both defects below are still OPEN at this level, so treat a sudden outsized loss as
this hazard until proven otherwise, and turn the Pine's "Minimum stop distance" on for live use.

**The guard is now PORTED (2026-07-30) — it was the one known Pine↔Python divergence on the A+
pair, and it is closed.** `exec_min_stop_mode` / `exec_min_stop_val` in `config.py` (defaults `"Off"`
/ 0.10, matching the Pine), the floor applied at order placement in `_place_entries`, block reason
**code 7** ("Stop too tight") so a setup refused on PRICE is countable in the lab's Blocked layer
like every toggle refusal, and `cfg_min_stop` / `cfg_min_stop_val` columns in a regenerated
`mpc_strategy_export.pine` that `compare_strategy.py` decodes. See `### The minimum-stop guard`.

The four modes match the Pine exactly: `"Off"` (floor 0.0 — inert, so every historical result is
unmoved), `"% of price"` (self-scaling, the one Run 7 recommends at 0.10), `"Fixed $"`, and
`"x ATR(14)"` — the ATR being Pine's `ta.rma(ta.tr(true), 14)`, updated on every bar at the top of
`step()` rather than inside the entry branch, because a `ta.*` call that skips bars returns a
different number. **Turn it on for live trading**; leave it Off to reproduce a past run.

Measured consequence at `0.786` + 20 ticks
over full history: stop distance collapses to **$0.20** on 15m gold, `qty = risk / stop_distance`
builds a **39,033 oz (~$78M notional)** position, one bar takes **18× the intended risk**, and
equity ends at **−$63,726** — after which the bot stops trading entirely. Two defects behind it,
both still OPEN and both live-trading hazards:
1. No validation that the chosen SL fib is on the correct side of the entry, or a sane distance
   from it. Assume `mpc_strategy.pine` has the same exposure (same dropdown) until checked.
2. **No minimum stop distance.** `execution.py:329` sizes correctly —
   `qty = (equity * exec_risk_pct / 100) / dist` — so risk IS dynamic and a wider stop DOES give a
   smaller lot. The formula is not the bug. What it assumes is: `exec_risk_pct` is only the real
   risk **if the exit actually happens at the stop price**. That holds when the stop is wider than
   a typical bar (which `"1.0"` = leg origin always is) and fails completely when it is narrower —
   price gaps straight through and the realised loss is unbounded. At a $0.20 stop on 15m gold the
   nominal 10% risk was realised as **~180% in one bar**. So the guard needed is a floor on
   `dist` (e.g. ≥ some ATR multiple), NOT a change to the sizing math. A position/margin cap is
   worth adding as a second backstop, but it treats the symptom.

**This bot has no R:R dial.** Targets are fibs and the stop is a fib, so the risk-reward ratio is
an OUTPUT of leg geometry, never an input — no combination of existing parameters can express
"risk 1 to make 3". Answering that question needs an ATR-based stop distance + fixed-R targets,
which is new code here AND in the Pine. See Run 4's writeup for the two proposed routes.

**Every sweep of these levers is logged in `mpc_sos_fade_optimization.md`** — one entry per run,
with the full grid, per-year and per-half R, and whether it was adopted. Read it before tuning
anything here so a question already answered is not re-measured. ⚠ **Count them with
`grep -c '^# Run ' mpc_sos_fade_optimization.md`, never off this line** — it read "twelve" while
eighteen were filed. Only
1–7 are enumerated below (they are the exit-ladder work this section owns); 8–12 live in the log and
are summarised in the paragraph after the list. **Run 1 is ADOPTED (2026-07-27)** and **Run 8 is
SHIPPED (2026-07-28)**; every other run is measured and unadopted — Runs 1–3 on the same
185,530 M15 bars / 187 trades, Runs 6–7 on the full 185,668-bar history at 188 trades:

1. **TP split** (21 combos) — monotonic; best is `exec_tp1_pct=0, exec_tp2_pct=0` (100% on the
   runner) at 70.7R vs 47.9R for the shipped 30/40 split. **ADOPTED 2026-07-27 as the default**, in
   lockstep across `config.py` and both A+ Pine files. The tick-mode re-run this entry originally
   asked for was overtaken by better evidence: Aaron's own TradingView chart had been running the
   rungs at 1% each (the closest the input would take to 0) for the whole 2020-2026 Deep Backtest,
   so the setting has a real 162-trade out-of-sample record, not just a bar-mode sweep. Adopting it
   also FIXED a live hazard — see the `qty_percent = 0` guard note in `## The exit ladder`.
2. **The whole ladder** (525 combos) — re-confirms (1), and finds **both dropdowns are already at
   their best value**: structure trail beats every fixed step (best fixed = 62.5R), the trail
   buffer is nearly irrelevant (0.4R across 10→80 ticks), and `exec_tp2_stop_mode="One trail step
   behind"` is actively harmful (caps out at 42.3R). The TP split is the only lever with real
   variance: ~−2R per 10% moved off the runner.
3. **Stop TIMING** (35 combos, research-only dials — both moments are hardcoded in Python AND
   Pine) — **the shipped timing wins; nothing to adopt.** Delaying breakeven grows the average
   winner 3.7x (0.80R → 2.96R) but total R falls 25% and drawdown grows 3.5x, monotonically bad.
   **This settles the open question below about whether stop→BE on TP1 caps runners: it does not.**
   It converts full losses to scratches (avg loss −0.73R with it, −0.99R without) and that is worth
   more than the upside it forgoes. The biggest winner was +15.03R in all 35 combos — the trade
   that makes the money never traded against its stop, so this lever cannot reach it.
4. **Stop PLACEMENT** (40 combos) — **INVALID, discard the numbers.** Four of the five
   `exec_sl_level` values put the stop on top of the entry; equity ended at −$63,726. See the ⚠
   warning above — it is this run's writeup.
5. **"How do I cut the losers quicker?"** (2022+ cache, 118 trades) — **there is nothing to cut
   quicker with.** Both early-exit toggles measured at exactly zero effect (`exec_close_opp_sos`
   and `exec_htf_exhaust_only` each produced byte-identical trade lists), and a time stop would
   cut the WINNERS (all net comes from trades held past 20 bars). The diagnosis is the value:
   **every loss is a trade that never touched TP1**, and TP1 sits ~0.45R away while the stop sits
   1R away, so a losing trade dies a median 0.34R short of the level that would have staged it to
   breakeven. That makes this a stop-DISTANCE problem, not a stop-timing one. Re-running
   `exec_sl_level` on a clean window scored **59.3R at 0.786 vs 33.6R shipped at the same
   drawdown** — but 8 of its 108 trades reproduced Run 4's sub-$2-stop hazard, so it stays
   unadoptable. ~~The minimum-stop-distance guard is worth a measured ~+26R.~~ **That ~+26R figure
   is WRONG — superseded by Run 7**, which replayed the guard properly instead of filtering rows out
   of a finished trade list.
6. **"Cut trades early / block the losing pattern"** (2026-07-27; 8 years, per-bar R paths, ~40 cut
   variants + 10 entry blocks) — **the question is CLOSED, do not build it.** No loser runs straight
   to its stop (min MFE **+0.09R**, median +0.51R) and winners sit underwater just as deep (median
   MAE −0.36R), so the two populations are indistinguishable while the trade is live. Every cut
   family loses money. The −54.9% drawdown is a **losing streak at 10% risk**, not give-back —
   **risk % is the only lever that moves it.**
7. **The minimum-stop guard, measured properly** (2026-07-27; 17 real replays, three independent
   definitions: fixed $, % of price, ×ATR) — **it PASSES, at a MILD threshold only, as a SAFETY
   rule.** All three definitions agree: light (blocks 3–6 of 188 trades) = **+0.7 to +2.7R**;
   medium/heavy = **−12 to −39R**. Best is **`pct 0.1`** — the stop must be ≥ 0.1% of price
   (self-scaling, one line in Pine): 182 trades, **+2.5R**, blocks the −1.98R trade, and leaves
   2021/2024/2025/2026 **byte-identical**. Two cautions: the +2.5R is **noise-level** (ship it to
   close the hazard, not for the money — read sumR, never the ragged x-multiple), and it does
   **NOT** fix drawdown (−54.9% → −54.3%). **Not adopted — awaiting Aaron's go.** The follow-up it
   unblocks: re-run Run 5's `exec_sl_level` sweep with the guard installed, to see whether 0.786
   becomes adoptable.

**Runs 8–12, in one line each** (full write-ups in the log; do not re-measure any of them):
**8** the runner-exit space — **SHIPPED**, `"Structure + % ratchet"` at 1.0%, run-capture 43% → 53%
on the same 164 trades at identical % drawdown; every tightening family lost 60–90%. · **9** banking
at the extension fibs — **REJECTED in every form** (109.3R → 69.1R as rungs, 56.1R as a stop floor,
106.3R as deep rungs); 11 trades past −0.618 carry 106R of the 109R, so any fixed ceiling caps
exactly what pays. · **10** cutting by the SHAPE of the path — in/out-of-profit is **not** a loss
signal (32% base rate), the 0.886 fib cut fires zero times and 0.786 costs −27.0R; only a "no +0.15R
by bar 3 → close" stall cut is mildly positive (+4.8R) and it does not move drawdown. · **11** the
`exec_sl_level` sweep re-run WITH Run 7's guard — **`exec_sl_level` is settled at "0.886"**; 0.786 is
105.2R unguarded / 49.0R guarded, and 0.702/0.618 detonate. The one improvement is `0.886 + pct 0.1`
(112.0R, maxDD 54.3%, worst trade −1.98R → −1.00R), which independently confirms Run 7. · **12** *can
this strategy trade MORE?* — **no, not from inside the entry rule.** Dropping the FVG requirement,
sizing those extras smaller, deepening the entry and loosening which gaps qualify are all negative
or noise (see the ⚠ block in `## The missed-setup watch`), and the final-hour rule costs ~0.4R over
6.5 years so it stays on. **Trade count is a PORTFOLIO property here** — with one position slot every
marginal setup displaces a real one, and sizing UP trades already trusted beats adding new ones
(shipped book at `exec_risk_pct=12.5` = 832x @ 64.2% DD vs 426x @ 64.9% for the loosened book).

### The deeper-entry test (`exec_ob_deepen`, 2026-08-09) — REFUTED, and the mechanism is geometry

Aaron's theory, and it is a good one: **31% of the scratches and almost all of the losers could have
filled at an order block DEEPER than where they actually entered** (measured first — a deeper
same-direction block existed on 113 of 159 trades, and price reached it on 4 of 40 winners, 11 of 36
scratches and **35 of 37 losers**). A deeper fill has a TIGHTER stop, so the same price path is worth
more R — *"would I have less losers? and potentially slightly more return on the scratches."*

**Filling almost only on losers is bad only if the loser stays a loser**, which is why this needed a
REPLAY and not arithmetic over the finished list.

**MEASURED, two full replays, 155,807 M15 bars (2020-01-01 → 2026-08-06):**

| | trades | won | scratch | **lost** | hit TP1 | total R | maxDD |
|---|---|---|---|---|---|---|---|
| baseline | 159 | 63 | 44 | **52** | 104 (65.4%) | **+142.18R** | 5.61R |
| deepened | 102 | 35 | 15 | **52** | 48 (47.1%) | +73.41R | 15.20R |

**Both of his questions come back NO**: losers stay at exactly **52** and their R goes **−50.86 →
−71.30**; scratches **44 → 15**, their R +1.54 → +0.72.

🔴 **The mechanism he named runs BACKWARDS, and it is geometry rather than luck.** TP1 is a FIB, and
on a long it sits ABOVE the entry — so entering deeper puts it FURTHER away, not nearer. **TP1 hit
rate 65.4% → 47.1%.** TP1 is what stages the stop to breakeven, so fewer trades get that protection,
which is the opposite of the theory. The same inversion applies to the deep-entry TP table (a deep
entry takes TP1 = 0.5 where a shallow one takes 0.382), so it compounds.

🔴 **The average LOSS exceeds 1R — −0.98R → −1.37R — which is the minimum-stop hazard arriving by a
new route.** The stop is a median **79% tighter**, which puts it inside ordinary bar noise, so price
runs straight through and the exit stops happening at the stop price. **A risk % is only the real
risk if the exit actually happens at the stop** (`### The minimum-stop guard`); this is that rule
being violated by an ENTRY change rather than by a stop-level change.

Per-trade accounting, matched on the setup `(side, SOS bar)`:

```
never filled at the deeper price    57   (+44.61R given up)   ← the adverse selection, priced
entry unchanged (no deeper block)   47
re-priced and BETTER                16   (+25.70R)
re-priced and WORSE                 39   (−49.85R)
setups the baseline never traded     0   (+0.00R)             ← the freed slot bought nothing
```

⚠ **The freed slot produced ZERO replacement trades, and that is worth recording because this repo
expects the opposite.** The queue effect is real for an ENTRY-side filter (the min-stop guard's cheap
estimate got its SIGN wrong that way), and here it did not fire — this bot takes ~2 trades a month,
so a skipped setup usually has nothing waiting behind it. **A fact about this window, not a licence to
stop replaying.**

⚠ **The strongest form was tested deliberately** — `_deepen` rests on the DEEPEST qualifying block,
not the nearest. A milder version would move less and lose less, i.e. a diluted dose of the same three
mechanisms; the direction is structural.

⚠ **NO PINE COUNTERPART**, so `compare_strategy.py` can never configure it and parity is structurally
unaffected. Ships **OFF**, byte-identical to before, so nothing historical moves. Kept rather than
deleted because it is the instrument this measurement was taken with.

### Bar-mode costs — commission and slippage, charged at last (2026-08-01)

Bar mode charging ZERO costs is the parity requirement (deviation 3 above). Bar mode being
*incapable* of charging any is not, and the two were confused: the command-center lab collected
`commission_per_side` and `slippage_ticks` on every run, stored them, displayed them, and
`python_runner` read neither — so every lab run of this bot was frictionless while reporting a
cost profile it had not applied. The tell was 52 of one run's 54 losers each losing **exactly
10.00%** of prior equity.

`MpcSosFadeStrategy(..., cost_profile=<AccountProfile>)` now passes a profile straight through to
`Execution` in bar mode. **Omit it and every path is byte-identical to what it was**, which is
what keeps `compare_strategy.py` a valid gate — and the harness never passes one, so parity is
untouched by construction. `mpc_bleg` inherits the kwarg.

Two units, both deliberate, and both would look plausible if wrong:

- **Commission is per LOT per side** — a lot being 100 oz. Charged on the entry and on every
  ladder rung, through the existing `_charge_commission`, which means it lands inside the trade's
  own P&L and R rather than beside them.
- **Slippage is charged on MARKET exits only** (`_charge_slippage`, `_exit_portion(market=...)`).
  A stop is a market order and pays; the entry limit and the TP rungs are RESTING LIMITS, which
  fill at their price or better or not at all, so charging them would price a cost that does not
  exist. It is also skipped entirely in **tick mode**, where the fill price already contains the
  real slippage off the tape — charging an estimate on top would book it twice.

⚠ ~~**Swap is NOT charged from the lab's fields.**~~ **Closed 2026-08-02 — see below.**

### Layered costs — spread and swap, and the one that moves trades (2026-08-02)

Aaron's ask: *"you know the spread… the only thing we don't know is slippage."* Correct, and bar
mode was pricing neither the spread nor the swap. Both are now chargeable, from a broker profile
rather than a typed number, behind independent switches that are **all OFF by default** — the
baseline run stays frictionless so it stays comparable to the TradingView Strategy Tester, and
every cost is something you deliberately turned on. Lab contract: `python_runner.COST_LAYERS`.

**Swap needed almost nothing** — `_charge_swap` has run on every bar in bar mode since A2 and was
dead only because the lab passed `swap=None`. It matters here more than on most strategies: this
runner is designed to hold overnight (deviation 1) and gold swap is **−74.84 points/lot/night**
long on the Vantage demo.

**The spread is measured, and the number this repo had was the wrong broker's.** `$0.33` is PU
Prime's (688k ticks). Vantage — the broker every backtest here replays — measures **$0.22**
(median, over 1,494,459 cached ticks spanning 2025-08 → 2026-07; p90 0.27, p99 0.31). Using 0.33
would have overstated every backtest cost by 50%.

**MEASURED over 155,431 M15 bars, 2020-01-01 → 2026-07-31, at the shipped defaults:**

| run | trades | sum R | final equity | charged |
|---|---|---|---|---|
| free (the shipped baseline) | 161 | 135.94R | $28.26M | $0 |
| + spread as a cost | 161 | 130.27R | $16.27M | −$266,948 |
| + spread + swap | 161 | 123.90R | $10.09M | −$333,110 |
| **bid/ask fills + swap** | **159** | **141.93R** | **$29.48M** | −$361,835 |

🔴 **EVERY ROW ABOVE IS PRICED ON VANTAGE, AND THE BOT TRADES PU PRIME — which costs 23% more.**
Measured 2026-08-06 (`docs/LIVE_TRADING_PIPELINE.md` → G5) off the live terminal's own tick store,
1,893,438 ticks over 3 whole days. On the CURRENT shipped defaults over 155,531 bars, one real
replay per row: free **+142.18R** · Vantage costs **+130.59R** · **PU Prime costs +127.91R**, with
max drawdown 5.61R → 6.83R. **89% of that 2.68R gap is the SPREAD** ($0.32 vs $0.22 — 7.67R vs
5.28R), not the swap, whose worse long leg (−79.60 vs −74.84) is almost exactly cancelled by its
better short credit (+30.25 vs +26.98) on a strategy that trades both sides. **So read this table
as the BACKTEST broker's cost and add ~23% for the live one** — Vantage is pinned here because it
matches the TradingView feed the Pine was written on, which is a parity decision, not a cost one.

🔴 **AND THAT $0.32 IS A FACT ABOUT AN ACCOUNT TIER, NOT ABOUT A BROKER (2026-08-06).** It was
measured on PU Prime's **Standard** account — the one tier priced by a MARKED-UP spread — and
`backtest/fills.py::PROFILES` gave all four PU Prime tiers the same number, so a `puprime_ecn` run
charged ECN's commission ON TOP OF Standard's spread, a combination no real account offers.
✅ The unmeasured tiers carry `SPREAD_UNMEASURED` and **REFUSE**: `_spread()` routes
through `AccountProfile.spread_or_refuse()`, so the refusal fires wherever the profile came from
rather than only on the lab's path. ⚠ **It refuses the SPREAD, not the tier** — a raw tier's
commission and swap are known and still chargeable.
✅ **ECN — the tier this bot actually trades — left that list on 2026-08-14 at `$0.12`** (5 days of
its own ticks; provenance and which tiers still refuse: `backtest/CLAUDE.md`). ⚠ **NO documented
baseline here moves.** The tier RAISED before, so no table below ever charged an ECN spread, and
the `cost_tiers.py` row that quoted $0.12 as `stated` returns an identical 157 trades / +151.39R
now that it is `measured`. ⚠ **`0.0` and "unmeasured" must never
collapse**: 0.0 charges nothing on purpose, and the sentinel is NEGATIVE, so passing it through
would PAY the trader half a spread on every fill. 🔴 **The SWAP on those tiers refuses too, and that
assumption was checked rather than argued**: `XAUUSD.s` and `XAUUSD.crp` are the SAME market on ONE
PU Prime account (median M15 close difference $0.08 over 200 shared bars) carrying **swaps 8.5x
apart — long −79.60 vs −9.35 — with the short CREDIT gone entirely (+30.25 vs +0.04)**. This bot
trades both sides and its whole swap arithmetic rests on that credit nearly cancelling the long
charge, so borrowing another product's swap is not a small approximation. ⚠ **`swap=None` still
means "charge no swap" and stays silent** — only an UNREAD swap refuses. **Which tier to actually
trade is measured and
answered in `docs/BROKER_QUESTIONS.md` — a RAW tier, not Standard, because on this strategy the
spread costs ~20x what the commission does and it costs by killing FILLS** (8 setups of 159 never
fill at $0.32, 3 at $0.08; commission is 0.48R at $1.00/side and 1.67R at $3.50/side over 6.5
years). That is the same limit-order asymmetry the `bid_ask_fills` row above describes, read as a
decision rather than as a lab curiosity.

Two things to take from that table, and the second is the one worth remembering.

⚠ **A small charge is not a small effect.** 12.04R of cost turns $28.3M into $10.1M — **64% of the
final balance for 9% of the R** — because at a fixed % risk a dollar not earned early never
compounds. Always read a cost against the R, never against the net dollars.

⚠ **The last row is HIGHER than the free baseline, and that is not a bug — it is what a
limit-entry strategy does with a spread.** A flat spread charge is the market-order intuition (buy
the ask, sell the bid, lose the spread), and nothing here is a market order: every entry and exit
names a PRICE, so the spread changes WHEN an order fills rather than what it fills at. On a long
the buy limit fills at its own price and the stop sells at its own price — identical cash result,
the limit is simply harder to reach. The cost lands almost entirely on SHORTS, which sell the bid
to get in and buy the ask to get out, so their stops arrive a spread early and their targets a
spread late. On this book that traded 6 marginal entries away and, because there is one position
slot, let 4 different setups through in their place — the queue effect Run 12 already measured.
**So read the flat charge as a conservative UPPER BOUND and `bid_ask_fills` as the real question.**
⚠ It is also the newest and least-validated path here: it is unit-tested per order side and
measured once. Treat a `bid_ask_fills` result as a lab finding until it has been read on a chart.

Everything else is unchanged and deliberately so: **omit the profile and every path is
byte-identical** (the free row above reproduces the documented 161 / +135.94R exactly), the
harness never passes one, and `compare_strategy.py` is still **exit 0**.

**A cost turns marginal winners into real losers, and the win rate is where it shows up
(measured 2026-08-03).** On the 3-year run `432aff31f374` (73 trades, Aug 2023 → Aug 2026),
charging spread + swap took the win rate from **65.8% to 60.3%** — because **four trades flipped
side**: +$12 → −$26, +$68 → −$133, +$207 → −$1,315 and +$376 → −$2,331. All four were scratches
that only looked like wins because the run was frictionless, and the last two are not small.

⚠ **Drawdown got WORSE while profit fell — 57.2% → 60.1%.** A cost does not merely shave the top
off the equity curve, it deepens every losing stretch, so profit and risk move in opposite
directions and both readings are correct. This is the companion to the compounding warning above:
that one says a small charge costs a large fraction of the FINAL BALANCE; this one says it also
costs you drawdown, which is the number a risk budget is actually set against.

⚠ **Trade count cannot move** under spread / commission / swap — they change what a trade was
worth, never whether it happened. Only `bid_ask_fills` moves the trade list. A re-priced run
showing the same trade count as its source is working correctly.

### Wrong-side stop fills — a KNOWN BACKTEST LIMITATION, not a bug (recorded 2026-08-01)

**Read this before reporting "the exit price matches no stop and no target" again.** That symptom
was the phantom-exit bug (`indicators/docs/BUG_exit_fill_price_mismatch.md`, fixed 2026-08-01), but with
that fixed there is a *legitimate* residue that produces a similar-looking exit, and it will keep
appearing on the chart forever.

**The shape.** Price runs up, tags TP1, the ladder stages the stop to breakeven — and then price
closes back through breakeven **inside the same bar**. The stop only becomes live on the NEXT bar
(assumption 1 above, `calc_on_every_tick = false` / `process_orders_on_close = false`). By then it
is already behind the market, so the emulator converts it to a market order and fills at that bar's
**open**, not at the stop price.

**Why it is not a defect.** Being OUT is correct — price genuinely went through the stop. What is
imprecise is the exit PRICE, and only because a bar-replay backtest looks at orders once per bar
while a real broker watches every tick and would have filled at or near the stop. Three consequences
worth holding onto:

- It makes the backtest look **slightly worse than reality**, which is the safe direction to be
  wrong. Do not "fix" it to make numbers look better.
- **Pine and Python behave identically**, so **parity is unaffected** — `compare_strategy.py` and
  `compare_bleg.py` stay valid, and neither will ever flag it.
- It is a **bar-mode** property. `fill_model="tick"` resolves the stop against real ticks and will
  legitimately disagree here; that is the improvement, not drift (see `backtest/CLAUDE.md` → A2).

**Deliberately NOT fixed: a "a stop may never be placed through the market" clamp.** It would have
caught the phantom-exit bug on day one, but applied now it would change real trade behaviour and
would have to land in all five Pine files too. That makes it its own change with its own
measurement, not a tidy-up. ⚠ It also matters for **live**: the bridge places the stop with the
broker, so a live fill will land nearer the stop than the backtest's. Expect live to beat the
backtest marginally on exactly these trades — and treat any BIGGER live/backtest gap as a real
problem, not as this.

## The 2026-07-26 exit-lever sync

`mpc_strategy.pine` gained a structure-based runner trail, a TP2 stop-floor dropdown, an SL fib
dropdown and three setup toggles. Ported here, with the Pine's defaults adopted verbatim:

- **New config fields** — `exec_runner_trail` (**"Structure (swing)"**), `exec_struct_trail_buf_tk`
  (20), `exec_tp2_stop_mode` ("TP1 price"), `exec_aplus` (True), `exec_bleg` (False here, True in
  `BLegConfig`), `exec_fvg_50` (False). `exec_sl_level` already existed.
- **`signals.py`** — `Signals` gained `last_conf_high` / `last_conf_low`, passed straight through
  from the structure snapshot. Only `_advance_stage` reads them, and only past TP2.
- **`execution.py`** — `_trail()` gained the structure branch; the stage-2 floor moved out of
  `_current_stop()` into `_stage2_floor()`. Both anchors are snapshotted at the bar's CLOSE, the
  same one-bar delay `_max_fav` already had, because the stop placed at bar N's close is what bar
  N+1 trades against. Reading the live swing instead would silently make the trail clairvoyant.
- **`exec_fvg_50` is NOT ported** (same standing as `exec_conf_sz`) — `compare_strategy.py` refuses
  an export taken with it on. `exec_bleg` on is refused too: those trades belong to `mpc_bleg`.

### PARITY GREEN 2026-07-29 (exit 0) — the ratchet build, at the shipped rungs

`compare_strategy.py "VANTAGE_XAUUSD, 15_7b2f3.csv" --warmup 100` → **exit 0**. 21,494 bars,
2025-08-31 → 2026-07-29. Green at warmup 200, 500, 1000 and 2000 too.

This clears the 2026-07-28 stale warning. Two things make it the run that was actually needed:

1. **It carries the ratchet through the export.** `cfg_exitmode = 20` — the tens digit is the trail
   method, and it went 2-way → 3-way when `"Structure + % ratchet"` landed. Plus `cfg_trail_pct = 1`.
   An export taken before that change would decode the ratchet as the plain structure trail and go
   green while silently comparing two different exit ladders.
2. **It was taken at `cfg_tp1_pct = cfg_tp2_pct = 0`** — what the bot actually ships. The previous
   green run and the 109.3R ratchet headline were both at 1%/1%, which is not the shipped config.

26 trades graded, **sum 30.29R** over the ~11 months. Note this is the TradingView window, not the
6.6-year MT5 window the 110.65R baseline and the extension-fib work were measured on — the two
numbers are not comparable and neither supersedes the other.

⚠ **Not covered by this run:** it was taken before the minimum-stop guard was ported, at the `"Off"`
default where the gate is inert. It therefore still describes the CURRENT build exactly (see below —
Off is byte-identical on both sides), but it says nothing about the filter itself.

### The minimum-stop guard (ported 2026-07-30) — and what is NOT yet proven

The parent Pine had `execMinStopMode` / `execMinStopVal` and the Python did not. That was the one
known Pine↔Python divergence on this pair, and it was the dangerous kind: the export carried no
column for it, so `compare_strategy.py` would have gone GREEN while the Pine refused setups the
Python took. Closed in one pass:

| where | what changed |
|---|---|
| `config.py` | `exec_min_stop_mode` (default `"Off"`) + `exec_min_stop_val` (0.10) |
| `execution.py` | `_update_atr` (Pine `ta.atr(14)`), `_min_stop_floor`, `_stop_clears_floor` / `_stop_is_tight`; the floor gates both `_pend_long` and `_pend_short`; block reason **code 7** |
| `mpc_strategy_export.pine` | REGENERATED off the parent (body now byte-identical again apart from line 29's title) + `cfg_min_stop` / `cfg_min_stop_val` plots |
| `compare_strategy.py` | `_MIN_STOP` decode; **absent column ⇒ `"Off"`**, never the Python default |
| `mpc_sos_fade.meta.json` | both fields, with `show_if` on the mode (which needed `show_if` to accept a LIST of values — one enum, three ON states) |
| `mpc_bleg/config.py` | `exec_min_stop_mode` PINNED `"Off"` — that fork overrides `_place_entries`, so the floor never runs there and its Pine has no such input |

**At `"Off"` the two sides are byte-identical to what they were**, which is why the 2026-07-29 green
above still describes this build: the floor is 0.0, so `dist > 0 and dist >= 0.0` is the old
`dist > 0`, and code 7 cannot fire. 11 new tests pin that, both floor definitions, the ATR against
Wilder by hand, the precedence of code 7 behind a toggle refusal, and the decode.

⚠ **NOT yet proven: the filter ON, against a real export.** Everything above is unit-tested and
round-tripped through a synthetic export, which proves the two halves of OUR code agree — never that
they agree with TradingView (that is exactly the limit the B-LEG harness bug demonstrated). Before
trusting a run made with the guard on: re-paste `mpc_strategy_export.pine`, export at the mode you
intend to use, and re-run `compare_strategy.py` to exit 0.

#### The guard reaches the 1-MINUTE path too (2026-08-07)

The table above says the floor gates `_pend_long` and `_pend_short`. Those are the **15m** orders.
`_secondary_pending` — the 1m sniper's resting limit — asked only `dist > 0`, so from the day the
re-entry was built the shipped floor did not reach it. `exec_min_stop_mode` has been
`"% of price"` **0.08 since 2026-08-04**, not `"Off"`, so this was a live gap in a default run
rather than one waiting to be switched on.

It matters more on this path than on the 15m one, not less: `qty = risk / dist`, and a 1-minute
leg is a **shorter leg**, so its stop distance is smaller by construction.

✅ **MEASURED before it was written — two full replays, 186,366 M15 + 2,790,942 M1 bars, at the
shipped defaults.** The instrumented control reproduced the shipped book exactly (188 trades /
+165.46R / ddR 5.53 / 8 secondaries), which is what makes the delta attributable:

| | trades | R | ddR | maxDD | secondaries |
|---|---|---|---|---|---|
| control | 188 | +165.46R | 5.53 | 45.26% | 8 |
| floor on the 1m path | 188 | +165.42R | 5.53 | 45.26% | 8 |

**−0.04R over 7.9 years. All 180 primaries identical.** The refused trade did not vanish — a later
re-entry on the same setup took the freed slot 47 minutes on (+0.099R where the refused one made
+0.144R). That is the queue effect again, and it is why this was replayed rather than subtracted:
the same guard's cheap estimate on the 15m path got its **sign** wrong (+1.84R estimated, −1.84R
replayed).

🔴 **The honest size of the problem is ONE setup, and the first count of it was misread.** Over the
whole history **1,956 secondary limits were placed and 90 rested under the floor** — but a resting
limit is re-placed on every 1m bar, and all 90 are the **same limit at the same ratio (0.9848 of
the floor), one setup resting for 90 minutes.** Reading them as 90 near-misses would have been a
count of bars dressed up as a count of risk. Exactly one under-floor secondary has ever FILLED
(2024-12-02 20:08, a $2.08 stop against a $2.11 floor — 1.5% short).

⚠ **So the case for this is CONSISTENCY, not the measurement.** The history contains no instance of
the hazard the floor exists for; what it contains is one rule enforced in one of the two places it
applies. The sizing hazard on a 1m leg is structural and unpriced either way — an absence over 8
years is not evidence it cannot happen, and the $0.36-stop re-entry that motivated the question
existed until `exec_sec_once_per_setup` removed it the day before.

⚠ **The floor reads `self._atr`, which is the FIFTEEN-minute ATR(14)** — `_update_atr` runs in
`step`, never in `step_secondary`. That is the right reading (the setup is a 15m setup and the risk
is budgeted against it) and it only matters under `"x ATR(14)"`; the shipped `"% of price"` mode is
a pure function of the entry price.

✅ 5 new tests in `tests/test_secondary.py`, **3 watched RED** against the restored `dist > 0`. The
2 that pass at HEAD are kept and LABELLED — they pin the direction the old rule already got right,
which is the direction a later "simplification" would restore. 196 strategy + 348 backtest green.

⚠ **The same pass found a test my own default flip had made vacuous the day before.**
`test_run_dual_primary_is_identical_to_run_when_secondary_off` built its config with
`SosFadeConfig()` and a comment reading *"exec_secondary defaults False"*. It ships **True** since
2026-08-07, so the test had quietly become a run of the secondary path — and it still PASSED,
because the synthetic 1m stream it feeds never arms one. It pins `exec_secondary=False` explicitly
now. **The lesson generalises past this file: flipping a default silently re-points every test that
relied on it, and the ones that keep passing are the ones you will not find.** When you change a
default, grep the suite for bare constructions of that config.

### PARITY GREEN 2026-07-26 (exit 0) — and the bug the run caught

`compare_strategy.py "VANTAGE_XAUUSD, 15_e8beb.csv" --warmup 100` → **exit 0**, bar-for-bar identical
on 21,130 of 21,230 bars (20,730 15m bars, 2025-09-01 → 2026-07-25). The export starts mid-history, so
the ~100-bar warmup is genuine engine cold start, not a mask: every warmup from 100 up is green and the
first mismatch at warmup 0 is bar 16.

The first run came back with ONE mismatch, and it was a real bug, not noise:

> `bar 20315 2026-07-12 23:00:00 px_edge: py=4100.94376 pine=None`

Python computed a short entry edge on a bar where the Pine had none. The fib matched to the decimal
(`dbg_fib_p2`/`p6`/`ash`/`asl` all identical), so it was an **FVG lifetime** difference: Python held a
bearish gap created on the first bar after the weekend gap that the Pine never created at all.

**Root cause — an unpinned engine input.** `mpc_strategy.pine` HARDCODES the middle-bar close-cleared
check in its FVG detection (`close[1] > high[2]` / `close[1] < low[2]`, lines 1686/1688). The
`fair_value_gaps` engine has that as the OPTIONAL `require_close` flag, defaulting **False** (it mirrors
`mpc_assistant.pine`, where it IS an input and IS off). Nothing exported it, so nothing caught it — the
engine happily created gaps whose middle candle never cleared the void.

Fixed by making it explicit rather than implicit: `EngineConfig` gained `fvg_require_close` (default
False, so no other consumer moves) and `MpcSosFadeStrategy.engine_config()` pins it **True**, alongside
the `fvg_max_count=7` and `show_internal=False` pins that were already there for exactly this reason.
`test_engine_config_pins_every_input_the_pine_moved_off_its_default` locks all three.

**The lesson is the class of bug, not the flag.** An engine input the decision stream does not export
is invisible to the parity check until a fresh export happens to disagree — and this one had been wrong
since the FVG engine made the gate optional on 2026-07-18. Any time an engine's default changes, check
every `engine_config()` that replays a Pine which does NOT share that default.

**What the new export columns immediately paid for:** they revealed the Pine was running
`execTp1Pct = 20` / `execTp2Pct = 20`, not the 30/40 defaults. Before this change no column carried
them, so the bot would have silently replayed 30/40 against a 20/20 Pine and the diff would have been
blamed on logic.

**The export had a real hole while this was in flight.** `execRunnerTrail` defaulted to Structure in
the Pine on 2026-07-25, but no `cfg_*` column carried it, so `compare_strategy.py` configured the
bot to the fixed-step fallback and diffed two different strategies. Any parity result from that
window is drift, not a bug. `mpc_strategy_export.pine` now carries `cfg_bits` bits 16384 /
32768 / 65536 (`execAplus` / `execBLeg` / `execFvg50`), `cfg_exitmode` (both exit dropdowns), and
one raw column each for the six exit numerics + the scratch band. An export WITHOUT `cfg_exitmode`
is pre-2026-07-26 and `compare_strategy.py` prints a loud warning rather than guessing.

## Deliberate deviations from the Pine (per the framework)

🔴 **PYTHON-ONLY FIELDS — THE GATE IS BLIND TO THESE, AND THERE ARE NOW TWO (audited 2026-08-12).** A field with no Pine input has no `cfg_*` column, so `compare_strategy.py` **can never configure a non-default run of it** — the green gate says nothing whatever about these branches. This is rule 14 with a specific shape: *a gate proves nothing about a branch neither side entered*, and here one side cannot enter it at all.
- **`exec_no_gap_arm`** — no `execNoGapArm` input exists in either A+ Pine. Any result measured with it moved was taken with one implementation only.
- **`exec_poi_source`** — `execPoiSource` appears in **zero** `.pine` files. The Pine POI seam was reverted (`indicators/CLAUDE.md` records it); the Python side was not reverted with it, so this field outlived its counterpart.

⚠ **Before trusting any A+ measurement, check whether it moved one of these two.** ⚠ **The fix is a decision, not a tidy-up:** either add the Pine inputs and re-export so the gate can see them, or drop the fields. Leaving them is the one option that keeps a live strategy carrying dials nothing verifies. Detail: `strategies/python/mpc_sos_fade/docs/SOS_FADE_BUILD_NOTES.md`.

**Other rules rescued from that same moved narrative (60,467 bytes, largest paragraph 58,936 bytes on ONE line):**
- **Block codes are a WIRE FORMAT — never renumbered.** `leg` must stay distinct per leg.
- **An absent column means "Any"** — read it as a fact about what the Pine did *before the gate existed*, never as the Python default.
- **Read a within-noise R as "not worse", never as the gain.** This strategy's run-to-run spread is 15.06R, so anything under that is a consistency check on a rule, not a second measurement of the edge. Where a pass genuinely gained, it gained FREQUENCY — a count, which noise cannot manufacture — and it was bought with drawdown that must be restated every time the gain is quoted.

All OFF for the parity check (to match the Pine); each is a real-run choice:
1. **Flat-by-close** — force-flat + no new entries N minutes before the daily close (`flat_by_close`).
   **Default False, and RE-MEASURED 2026-08-03 over the full 6.5 years: leave it that way, and the
   margin is not close.** Aaron asked the natural question — *"I don't like swaps, what if we just
   close before the market closes?"* — so it was replayed four ways over the same 155,453 M15 bars
   at run `75ccc776d10c`'s params:

   | | trades | R | final balance |
   |---|---|---|---|
   | hold overnight, free | 161 | **135.94** | $28,258,768 |
   | hold overnight, spread+swap | 161 | 123.90 | $10,090,716 |
   | flat before close, free | 161 | **59.82** | $411,314 |
   | flat before close, spread+swap | 161 | 54.18 | $236,057 |

   **It does exactly what it promises and the swap goes to zero** — the charge falls 12.04R → 5.64R
   and what remains is pure spread. **You save 6.4R of swap and give up 76.1R of edge to do it, a
   12:1 bad trade.** The entries are IDENTICAL (161 either way, all matched on entry bar); **73 of
   them are cut short**, and held to the end those 73 made 140.39R against 64.28R cut at the close.
   The worst single one ran 274 hours for **+23.96R** and becomes a **−0.46R** scratch after 3.8h.
   ⚠ **It does not merely shave the runner, it INVERTS the long side: longs go +70.96R → −12.10R.**
   Shorts survive (+64.98R → +31.38R) because gold's short swap is a CREDIT (+26.98 points/night on
   Vantage) — over the run shorts were paid 2.14R of swap while longs paid 8.55R. So "the swap is
   expensive" is a statement about LONGS only, and the fix for it cannot be a rule that hits both.
   **The mechanism is structural, not a tuning artefact:** the runner trails on confirmed structure
   (`Structure + % ratchet`), and structure takes days to build — a hard 17:00 NY exit caps every
   runner at one session. This is the same finding as Run 12 from a new direction: the edge is in
   the tail, and anything that truncates the tail costs more than the friction it removes.
   ⚠ **Do not read the earlier figure recorded here** (6.5 months / 32 trades / OFF $39,454 vs ON
   $19,813, measured 2026-07-16). Same direction, but 4 overnight trades is not a sample and the
   dollars predate the phantom-exit fix and the layered costs. The table above supersedes it.
   (This param was DEAD CODE until 2026-07-16 — `_in_flat_window` read only `sig.ny_hour`, so
   "minutes left" was always a multiple of 60 and never hit the ≤15 window. Any A/B run before that
   date compared a flag against itself.)
2. ~~**Sizing** — real runs swap in the dynamic sizing engine under a ruleset.~~ **No longer true
   as of 2026-07-16:** the bot declares `self_sizing: True`, so real runs keep the Pine's own fixed-%
   sizing (`exec_risk_pct`) and the engine never re-sizes them — this is NOT a deviation any more,
   parity and real runs size identically. See `## Sizing — this bot sizes ITSELF` above.
3. **Fill model** — parity REQUIRES `fill_model="bar"` (the Pine's own intrabar guess, zero costs).
   Real runs set `fill_model="tick"` + `account_profile` + `symbol` for real bid/ask fills and costs.
   See `backtest/CLAUDE.md` A2 — tick mode disagreeing with the Pine is correct, not drift.

## Engine-construction pins (`MpcSosFadeStrategy.engine_config`)

**FOUR** engine inputs are NOT in the decision stream, so the bot pins them to the Pine STRATEGY's own
input defaults rather than the shared engine defaults — miss any one and the fib the bot reads drifts.
`test_engine_config_pins_every_input_the_pine_moved_off_its_default` asserts all four.
1. **`fvg_max_count=7`** — `mpc_strategy.pine` sets Max Active FVGs to 7 (the FVG engine default is 8);
   a smaller cap evicts the oldest gap one bar sooner and drops an entry edge Pine still holds.
2. **`fvg_threshold_pct=0.1`** *(added 2026-07-31 — it had NEVER been pinned)*. The minimum-gap floor.
   `mpc_strategy.pine` splits it by timeframe (`fvgThreshLTF` 0.0 below 15m / `fvgThreshHTF` **0.1** at
   15m and up, lines 116-118) and this bot trades 15m. `mpc_assistant.pine` uses **0.04** at 15m and
   the ENGINE default mirrors the indicator, so the two Pines genuinely disagree and no shared default
   can be right for both. **The bot worked for months by coincidence**: `backtest/replay/stack.py`
   happened to carry 0.1 as its own default. That default was itself stale relative to the engine, so
   anyone reconciling it would have silently moved this bot's trades with no test failing. Proven
   load-bearing by removing it — `compare_strategy.py` failed on the first compared bar
   (`px_edge` py=3478.99 vs pine=3475.43). `stack.py` now carries the engine default (0.0) and this
   pin carries the strategy's, which is the right way round.
3. **`fvg_require_close=True`** — `mpc_strategy.pine` HARDCODES the middle-bar close-cleared check
   while the engine defaults it OFF (mirroring the indicator). Caught 2026-07-26 as the single
   mismatch on a fresh export; full story in `### PARITY GREEN 2026-07-26`.
4. **`show_internal=False`** — the Pine's "Show Internal Structure" input defaults OFF, and Pine gates
   the ENTIRE internal block behind it (`internalActive = showInternal`), so `i_confirmed_*` is never
   set and the **Structure fib never adopts a more-extreme internal swing** as its anchor. The
   `market_structure` engine ALWAYS computes internal structure, so the `EngineStack` must be told to
   suppress the internal-derived snapshot fields (it blanks `i_confirmed_*` + `ifib_seed_*` when this
   is off). This is a real "a drawing toggle changes trade logic" coupling in the Pine — do not drop it.

## The three parity fixes (2026-07-16) — read before touching signals/fib

The port went green after fixing three faithful-translation gaps; each is a class of bug to watch for:
1. **Internal-swing adoption** (the `show_internal` pin above) — the engine's always-on internal
   structure fed the fib an anchor the Pine strategy never had (internal display off).
2. **Sweep double-count at the daily/session rollover** — Pine records a sweep on `d_lMit and not
   d_lMit[1]` (a bar-to-bar edge of a persistent VARIABLE). When a daily/session/H4 level rolls at
   18:00 and is re-taken on its own creation bar, `d_lMit[1]` (the old level, already swept) is still
   true, so no edge fires. The engine models levels (create / mitigate / EVICT) and the naive
   reconstruction latched on every `mitigated` event, re-recording the rollover sweep — which made a
   stale sweep look fresh and armed a trade Pine didn't. `signals.py` now reconstructs the Pine
   variable: reset on `created`, set on `mitigated`, **left alone on `evicted`**, edge vs the prior bar.
3. **The forming last bar** — TradingView exports the final (still-forming) bar's plotted series as
   NaN. `compare_strategy.py` now marks that bar `_px_present=False` and skips it, instead of reading
   `fillna(0)` as a real "stage 0" and flagging a phantom mismatch.

## The parity gate — `tools/compare_strategy.py` + `/audit-strategy`

The standing regression harness (same pattern as the engines' `compare_*.py`). `mpc_strategy_export.pine`
(in `indicators/`) = `mpc_strategy.pine` + an appended block that plots the per-bar decision stream
(`px_*`) and every toggle (`cfg_*`). Export it to CSV on a 5m XAUUSD chart; `compare_strategy.py` reads
the toggles, configures the bot identically, replays the same bars, and diffs the decision stream. Exit
0 = bar-for-bar identical. On a mismatch it names the first diverging bar + field. Run it via
`/audit-strategy`, or:
```
command-center/backend/.venv/bin/python strategies/python/mpc_sos_fade/tools/compare_strategy.py <export.csv> --warmup N
```

### The 2026-07-22 re-sync (the export was 7 days stale)

`mpc_strategy_export.pine` was last regenerated 2026-07-15 and had drifted on three trade-affecting
Pine changes, so any diff it produced was July-15 drift, not a bug. Regenerated from
`mpc_strategy.pine` @ `361f007`:

1. **The veto is now SOS-aware** (Pine `longVetoA`/`shortVetoA`, ~3701). A divergence printing AFTER
   the SOS no longer vetoes its own setup — once stage 2 is live the setup is waiting on a retrace,
   and an opposing divergence formed during that retrace IS the pullback. Only one already live at
   or before the SOS bar still blocks. Extreme RSI keeps blocking LIVE. **Ported here**: the veto
   moved out of `SignalAdapter.update()` (which has no sequence state) into `signals.sos_aware_veto()`,
   which `execution.py` and `secondary.py` both call. `Signals` now carries the veto PARTS
   (`veto_on`, `veto_rsi_ob`, `veto_rsi_os`) instead of the finished `long_veto`/`short_veto`.
   The old, stricter rule is why a lab run can miss a long TradingView took.
2. **`execConfSZ`** — "Allow Sniper Zone as entry confirmation", a second accepted entry
   confirmation alongside the FVG. **NOT ported.** `config.exec_conf_sz` exists (default False) and
   the export packs it as `cfg_bits` bit 4096, so `compare_strategy.py` REFUSES an export taken with
   it on rather than diffing against logic this bot lacks. Port = read `BarState.sniper`'s
   0.5-0.618 pocket as an entry edge on any leg with no qualifying FVG.
3. **CONT trades removed** from the Pine — the export used to carry `contL_ok`/`contS_ok`.
4. **`execDeepFib`** (Method 3, added 2026-07-23) — "Floating gap → nearest fib shallower" (titled
   "Entry: deep gap enters on nearest fib (not gap edge)" until the 2026-08-02 label sync).
   A qualifying FVG whose NEAR edge (long = gap top, short = gap bottom) sits deeper than
   0.618 rests its limit at the nearest fib just SHALLOWER (0.618/0.702/0.786) — the level price
   reaches first — instead of chasing a gap edge price may never tap. **PORTED here**: `config.exec_deep_fib`
   (default **True** as of 2026-07-23 — see the prime-combo defaults note below), `execution._deep_fib_edge()`
   + the override in `_entry_edges()`, the export packs it as `cfg_bits` bit 8192, and `compare_strategy.py`
   reads it (no refusal — it is fully ported). ONLY the near edge's position decides it; what the gap body
   crosses is irrelevant (an earlier "body contains a level" gate was WRONG and dropped exactly the deep
   multi-level gaps this targets).

**Prime-combo defaults (2026-07-23).** Aaron's TradingView-tested "prime" settings are now the shipped
defaults in BOTH Pine files and `config.py`, in lockstep so `compare_strategy.py` parity holds:
`exec_arm_sweep` False→**True**, `exec_arm_div` True→**False** (arm on liquidity sweeps, not divergence),
`exec_fvg_deep_only` False→**True**, `exec_deep_fib` (new) → **True**. `exec_req_fvg` stays True. Combo
result on Aaron's Strategy Tester: ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2yr gold at 84 trades.
This SUPERSEDES the old divergence-armed default — the "2-year run" analysis further down was measured
under that old default and predates Method 3 + deep-only; keep it as the historical baseline only.

**Slippage pinned to 0 in the Pine (2026-07-23).** Both `mpc_strategy.pine` and `mpc_strategy_export.pine`
now declare `slippage = 0` in the `strategy()` call, so the TradingView Properties tab defaults to zero
instead of Aaron's old 25-tick setting. Reason: for HONEST parity the Pine's `fill_model="bar"` (zero
costs) must line up with a TV run that also charges nothing, so `compare_strategy.py` and a hand
trade-diff compare like-for-like. Real costs belong in the LAB's `fill_model="tick"` run (real bid/ask +
spread + slippage + commission + swap), not smeared as a flat 25-tick charge on every TV fill. The
breakeven buffer (`execBeBufTk`, default 30) is a STRATEGY input and is unchanged — it is signal logic,
not a cost. So the old note that TV's number is "slightly PESSIMISTIC because TV charges 25 ticks" no
longer applies to a fresh export: at slippage 0 the TV bar-mode number and our bar-mode number are the
honest apples-to-apples pair; the tick-mode lab run is the real tradeable number.

**When the Pine changes:** brother re-pastes `mpc_strategy.pine` → regenerate `mpc_strategy_export.pine`
(re-copy + re-append the parity block) → re-export → re-run until exit 0. A new trade-affecting input =
a new `config.py` field + a new `cfg_*` plot + a new `compare_strategy._TOGGLE_COLS` entry.

**One-shot sync check:** `backtest/tools/verify_parity.py <export.csv> [more.csv ...]` runs EVERY parity
check (all nine engines + this strategy) whose columns are present in the CSV(s) and prints one
GREEN/RED/SKIP table with auto-detected cold-start warmup. It is the "is everything in sync?" command
to run after any re-paste; it reports drift, it does not fix it (a real logic change is still a hand
port). Engines are the foundation — sync them first (`/audit-engines`), then this strategy.

## LOGIC parity vs RESULT parity — two different tools, two different questions

`compare_strategy.py` answers "is our CODE the Pine's code?" — it replays TradingView's OWN bars and
diffs the per-bar `px_*` decision stream, so the data feed is out of the equation. That is the gate.

`tools/compare_trades.py` answers a different question: "why does a LAB RUN's finished trade list
differ from what I got in the TradingView Strategy Tester?" It pairs the two trade lists by entry TIME
(not price — different brokers legitimately differ by cents on the same bar) and reports matched /
TV-only / ours-only. **It is a diagnosis tool, not a parity gate** — a diff here is usually the DATA
FEED, not the code (proven 2026-07-22: run `f455b21faabe` came in ~110% vs TradingView's 142%; the whole
gap was two longs Vantage's wick swept a level our PU-Prime feed's wick fell ~10 cents short of, so the
sweep never armed. `compare_strategy.py` was green on TradingView's bars, i.e. our code took both those
longs on Vantage data — the lab missed them purely on the feed). Two counting conventions also confuse
the comparison and are NOT bugs: TradingView counts each TP rung as its own "trade" (41 positions × 3
rungs = 123) and its max-DD % is vs peak equity where ours is vs starting capital. Usage:
`compare_trades.py <tv_trades.csv> <run_id>` — `--tz` defaults to `Etc/GMT+4` (the Vantage XAUUSD chart
is a FIXED UTC-4, no US DST); it prints a hint if the median pairing offset says otherwise.

## The 2026-07-16 year run — what the numbers actually say

365d, 15m, XAUUSD.s, `exec_risk_pct=10`, $10k start. Both fill models, same 22 trades:

| | bar (Pine guess, no costs) | tick (real bid/ask + costs) |
|---|---|---|
| net | $11,525.41 (115.25%) | **$11,374.78 (113.75%)** |
| PF | 4.426 | 4.228 |
| win% | 72.73% | 72.73% |

Real fills cost 1.3%; **0 bars fell back to the guess**, so every fill is a real tick. TradingView's
110.19% on the same setup is slightly PESSIMISTIC, not optimistic — TV charges a flat 25 ticks of
slippage on every fill, and the real broker is better than that (the entry is a resting limit, which
never slips; only stops pay).

**TradingView's 66 trades = our 22.** Each `strategy.exit` leg (TP1/TP2/runner) is a separate closed
trade in TV's stats: 22 × 3 = 66 exactly, and the filtered 16 winners × 3 = 48 exactly. Net / return /
drawdown mean the same thing in both; **profit factor and average-trade do NOT** — splitting one
winner into three legs changes the ratio (TV 4.155 vs the real 4.426). Don't compare those two.

**The distribution is the real story** (`|R| < 0.25` = scratch):

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner (TP1+TP2 banked) | 8 | +12,510 | **110%** | 1.19 |
| TP1 only, rest stopped at BE | 8 | +2,389 | 21% | 0.19 |
| never reached TP1 | 6 | −3,524 | −31% | −0.42 |

The 72.73% win rate is arithmetically right and analytically misleading: **10 of the 22 trades are
near-scratch** (together +$749), six of the eight "TP1 only" winners made under $300, only 2 trades
lost a full R (the stop→BE rule converts most losses to scratches), and the **top 3 trades are 57% of
net**. The edge is the runner. Treat the win rate as a byproduct of the BE stop, not as the edge.

### The 2-year run (2024-07-16 → 2026-07-16, tick mode) — the shape HOLDS

> **⚠️ Pre-combo baseline (superseded 2026-07-23).** Everything in this subsection was measured under
> the OLD default (divergence-armed, gap-edge entry, no deep-only). The shipped default is now the
> deep-entry combo (sweep-arm + deep-only + deep-fib → ≈+237%/PF6.2/85%/13%DD at 84 trades). The
> numbers below still stand as the divergence-only baseline, but they are no longer the default's
> results. Read them as history, not as what the bot does out of the box today.

40 trades, net **$21,536.60** on $10k. The distribution is the same story with a bigger sample:

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner | 15 | +26,565 | **123%** | 1.13 |
| TP1 only | 12 | +4,032 | 19% | 0.16 |
| never reached TP1 | 13 | −9,060 | −42% | −0.45 |

What the second year of data changed, and what it didn't:
- **Win rate fell 72.73% → 67.5%** (27/40) and losers went 6→13 — the 1-year window was the kinder half.
- **Concentration improved**: top 3 = 45% of net (was 57%) — still above the framework's <60% floor
  but no longer resting on three trades.
- **Still 17 of 40 near-scratch**, and still exactly the runner carrying everything (123% of net).
- **Full-R losses scale with the sample** (2 → 5), i.e. the stop→BE rule keeps converting most losses
  to scratches; that behaviour is stable, not a one-year artifact.
- **The ~83% short skew (33 shorts / 7 longs) is EXPLAINED as of 2026-07-16 — it is not a bug.**
  The port is parity-green, so the Pine skews identically. Measured per-side over the same 2yr
  window (48,246 bars, gold +75%):
  - **Root cause — the arm-source filter.** The sequence arms on a sweep OR a divergence, but
    `exec_arm_sweep` defaults **False**: only DIVERGENCE-armed setups may enter. Bearish
    divergences outnumber bullish **142:73 (66%)** in an uptrend — price keeps making higher
    highs on weakening RSI, while bullish divergences need lower lows a bull market rarely gives.
    The skew is inherited almost entirely from that 2:1. Sweeps, by contrast, are near-symmetric
    (1,505 S / 1,308 L), and the raw structure is *dead even* — external SOS is **125/125**. So
    nothing upstream of the arm filter is asymmetric.
  - **Amplified by fib geometry.** Episodes reaching Stage 4 READY: **37 L vs 67 S**. After a bull
    SOS a long waits for a retrace to 0.5/0.618 — in a strong uptrend the pullback is too shallow
    to reach it (51 long episodes die at peak stage 2, vs 25 short), while the deep counter-trend
    rallies a short setup needs arrive reliably.
  - **The default filter is the profitable subset, and it is a strict SUBSET.** Every
    divergence-armed trade is also sweep-armed, so `both` is bit-identical to `sweep only`.
    Arm source → trades / short% / net / PF (bar mode, 2yr, no costs):
    divergence-only (OLD default) 40 / 82.5% / +190% / **3.27** · sweep-only (= both) 79 / 69.6% /
    +144% / **1.87**. Enabling sweeps adds 39 trades that lose money net and drags PF down ~43%.
  - **Longs are not broken, just rare** — 7 trades, **86% win**, profitable (+21% of capital).
    Nothing is blocking longs incorrectly; there simply are few bullish divergences up here.
  - **What to actually worry about is concentration, not the count.** Shorts carry **89% of net**.
    Every HTF bias filter is `Ignore` (`exec_htf_weekly`/`exec_htf_daily`), so this is an
    unfiltered counter-trend fade that shorted a +75% bull market and won at 70%. That is the
    claim needing a second regime to confirm — the direction split itself is now accounted for.

Open threads (Aaron is on the edge work as of 2026-07-16): ~~whether stop→BE on TP1 caps runners~~
(**ANSWERED 2026-07-26, Run 3 in `mpc_sos_fade_optimization.md`: it does not — it pays for itself**); and
why 15m is reportedly the only winning timeframe (a real edge usually survives on neighbouring
timeframes — if 5m and 30m lose, suspect luck). 40 trades is still a thin sample; treat the KPIs as
directional, not settled. (Superseded note: an earlier version warned "do not flip `exec_arm_sweep` — it
breaks parity". That was wrong on the mechanism — parity is driven by the export's `cfg_bits`, not the
default — and moot now: the default flipped to sweep-arm on 2026-07-23, in lockstep across both Pine
files and `config.py`, so parity holds. Flip toggles freely per run; just keep the two Pine files and
`config.py` defaults identical when you change a DEFAULT.)

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_sos_fade/tests/ -q
```
Offline, no network, no TradingView. `test_sequence.py` (state machine on the real engine stack +
hand-checked Pine rules), `test_execution.py` (fills / ladder / stop-out / sizing, hand-checked),
`test_strategy_driver.py` (end-to-end), `test_compare_strategy.py` (the parity tool round-trips its
own output). These prove the plumbing; the Pine diff is the live gate.

## The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)

`strategies/python/mpc_bleg/` (the standalone B-LEG bot) reuses this package's engine + A+ sequence +
fill machinery, so it needed three ADDITIVE, decision-neutral changes here. All three are safe (this
bot's offline tests stay green) and must not be reverted:

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-leg
   endpoints the B-LEG band-freeze reads). Nothing in the A+ path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine point:
   after the opposite-SOS death, BEFORE the continuation-BOS death clears `l_sos_bar` and before the
   half/618 latch update. The B leg arms off state that `update()` has already cleared by the time it
   returns, so the sequence has to expose it here.
3. **`execution.py`** — the A+ arm decision was extracted from `_place_entries` into `_armed()` (a pure
   refactor) so the B-LEG subclass can reuse the "A+ has priority" gate. No behaviour change.

Full context in `strategies/python/mpc_bleg/CLAUDE.md`.

## Do / Never

- **Do** port any change to `mpc_strategy.pine`'s A+ block or execution layer here line-for-line, then
  re-run `compare_strategy.py`. Keep the Pine the source of truth — never edit it to match the Python.
- **Do** read engine OUTPUT only (`backtest.replay` `BarState`) — never reach into an engine's internals.
- **Never** build a second copy of any engine here — this consumes the canonical `engines/`.
- **Never** trust a backtest number until `compare_strategy.py` is exit 0 on a fresh export.
- **Never** commit a real TradingView export or backtest cache into git.
- **Never** revert the three B-LEG parity-safe additions above without also updating `mpc_bleg/`.

## References

- Spec: `docs/MPC_SOS_FADE_SPEC.md`; build plan + order: `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
- Pine source of truth: `indicators/strategies/mpc_strategy.pine` (A+ block ~3708-3972, execution ~4112-4735).
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
