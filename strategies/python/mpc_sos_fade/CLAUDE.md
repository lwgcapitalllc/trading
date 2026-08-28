# CLAUDE.md — strategies/python/mpc_sos_fade/ (the MPC SOS Fade bot)

> 🔴 **THIS FILE HOLDS THE RULES. THE EVIDENCE IS IN `docs/SOS_FADE_BUILD_NOTES.md` (2026-08-27).**
> Every section here keeps its ⚠ / 🔴 / ✅ rules and a pointer; the prose, the tables and the run
> numbers behind them moved there VERBATIM under the SAME heading. **Nothing was deleted** — a
> line that used to be here is in one of the two files, and that was checked rather than assumed
> (463 rule lines and 2,478 other lines, 0 lost).
>
> ⚠ **So a rule here may quote a figure whose table is now in the build notes.** Follow the
> pointer under the heading rather than assuming the number is unsupported.
> ⚠ **When you add to this file, add the RULE here and the working out there.** That is the repo
> rule — parents route, children explain — applied one level down, and it is the only thing that
> keeps this file from growing back.

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
**RE-VALIDATED GREEN 2026-08-23** on a fresh 21,060-bar `VANTAGE_XAUUSD, 15m` export
(2025-09-30 → 2026-08-23, shipped defaults, `exec_risk_pct` 10, stop fib 0.886, swing ratchet,
scale-in OFF) — exit 0 at warmups 100 / 500 / 1000 / 2000. **This is the run that clears the
2026-08-21 structure fix**, the refused-wick guard, whose only previous evidence was a red gate
against a twin that predated it. ⚠ **Non-vacuous, and it was checked rather than assumed:**
25 entries, 25 closes summing +29.05R, 2,470 armed bars and 267 blocked-setup tags, all
bar-for-bar. ⚠ **Rule 14 still stands** — green says the two AGREE, never that either is right,
and nothing about a branch neither entered; the harness itself reports that the no-gap fallback
was not exercised on this run.

### `mpc_sos_fade.meta.json` — labels and descs are SHARED WITH THE PINE (2026-08-02)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *`mpc_sos_fade.meta.json` — labels and descs are SHARED WITH THE PINE (2026-08-02)*.

🔴 **39 `desc` fields were rewritten to plain English on 2026-08-16, and the trigger was the
PINE side.** Every input tooltip in all 29 Pine files was cut to one or two plain sentences
(rule: `indicators/strategies/CLAUDE.md` → *TOOLTIPS ARE PLAIN ENGLISH*), and because a `desc`
IS that tooltip verbatim, this file had to move with it or the lab panel would have gone on
teaching the old wording. ⚠ **Strings only — every param's `name`, `group`, `core`, `widget`
and `options` is unchanged, verified by diffing and counting the changed lines that do not
contain `"desc"`.** The measured detail those descs used to carry now lives in
`indicators/strategies/docs/mpc_strategy.md` and the specs.

🔴 **`short` IS THE ONE KEY WITH NO PINE TWIN, AND IT IS EXEMPT FROM THE SYNC RULE BELOW
(2026-08-20).** All 83 params gained one. It is the same setting named in as few words as
possible — *Sweep → SOS window* against the label's *Max time: sweep → SOS (minutes)* — and it
exists because `label` is byte-identical to a Pine input TITLE, which is written to teach and
wraps to three lines in the command center's 248px run-report rail. ⚠ **Do NOT push a `short`
back into the Pine**: there is no input title for it, and adding one would break the byte-identity
that makes the sync checkable at all. ⚠ **It is a NAME, never an explanation** — the `desc` is
where an explanation goes (Aaron, 2026-08-20: *"they just have to be simple english names"*), and
⚠ **it carries no unit**, because the reader's value already renders `4320 minutes`. ⚠ **A param
added later without one is not an error** — the panel falls back to `label`; it just reads long.
⚠ **`strategy_scanner._PARAM_META_KEYS` is a whitelist and `short` is in it** — a key missing
there is dropped in silence and the UI behaves as though nobody wrote it.

⚠ **THE WHOLE SECONDARY GROUP IS PYTHON-ONLY AND IS EXEMPT FROM THIS RULE — CHECKED, NOT ASSUMED.**
`mpc_strategy.pine` declares 71 inputs and not one of them is a re-entry input (`grep -c "input\."`
then grep for the group); the Pine WIP that prototyped the feature was never merged. So a new
re-entry field — `exec_sec_risk_pct`, added 2026-08-20 — takes a label and a desc written for the
lab alone, and no Pine edit is owed in the same commit. ⚠ **Confirm with the grep before adding any
OTHER param**: the exemption is about which inputs the Pine happens to declare, not about the
prefix, and it flips the moment somebody ports the group across. ⚠ **Grep the GROUP, never
the word "sniper" — it means two different things across the two files.** The Pine's
"Allow Sniper Zone as entry confirmation" (G5) is a 15m confirmation zone on the PRIMARY
trade and has nothing to do with the re-entry this section calls the sniper. It has been
there all along and it is the one line a keyword search hits, so the search reports a
re-entry input that does not exist. The ten group labels are the reliable check: none of
them is a re-entry group.

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
incomplete". The **secondary** records none by design (it rests at a retrace of its own tight 1m
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

## 🔴 A BAR NUMBER IS LOCAL TO ONE RUN. THE ONE-TRADE-PER-LEG LATCH NOW KEYS ON TIME (2026-08-26)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 A BAR NUMBER IS LOCAL TO ONE RUN. THE ONE-TRADE-PER-LEG LATCH NOW KEYS ON TIME (2026-08-26)*.

🔴 **This repo had already written the lesson down, against a different consumer.** `shadow_diff`
joins on bar TIMESTAMP and its docstring says why in as many words: *"the live index counts on
from wherever warm-up stopped and survives restarts."* `strategies/CLAUDE.md` records the same
trap from the B-LEG harness, where 2,409 comparisons failed at one flat offset. **The live path
was still comparing numbers. A lesson recorded against one consumer is not a lesson applied to
the others — go and look at the others.**

✅ **`Execution._same_leg()` decides by TIME whenever both sides have one**, falling back to the
number only for a leg whose time was never seen. `_remember_bar()` keeps a bar-number → bar-time
map for the run, pruned to the recent 20,000 (a bot runs for weeks; an unbounded dict is a leak
with no upside). `_traded_sos_l_ms` / `_traded_sos_s_ms` are PERSISTED — without them a restart
restores a number from the previous numbering and the fix does nothing, which is the same bug one
layer down.

⚠ **The fallback is the OLD behaviour and is wrong across a restart.** It is kept because
refusing to answer would disable the latch outright, which is the same failure with fewer clues.

⚠ **It is a NO-OP in any single continuous run** — one backtest, one Pine chart, one uninterrupted
session — because within a run a number maps to exactly one time. The two answers can only differ
across a RESTART, which exists nowhere but live. **That is why parity is unaffected, and it was
RUN rather than reasoned**: `compare_strategy.py "VANTAGE_XAUUSD, 15_6fb2a.csv"` exit 0 at warmups
100 / 200 / 500 / 1000 / 2000 — the same five the pre-change code passes, and the known
pre-existing red below warmup 50 (bar 16, `px_s_stage`) is unchanged.

⚠ **Adding two fields to `_POSITION_FIELDS` means the next promote with a position OPEN will halt
on the restore** until the record is migrated. That is the designed refusal, and
`algos/tools/migrate_position_record.py` is the repair.

## The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)*.

## Sizing — this bot sizes ITSELF

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Sizing — this bot sizes ITSELF*.

## `live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *`live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)*.

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

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The restart seam — `snapshot_position()` / `restore_position()` (2026-08-10)*.

⚠ **`_POSITION_FIELDS` is the whole open-trade state and a missing entry is SILENT.** Leave one out
and the restored trade manages against a constructor default — a zero `_max_fav` un-ratchets the
trail, a zero `_stage` puts a breakeven stop back to the full stop, a missing `_entry_ms` resets the
time stop's clock. Nothing raises.
`test_the_snapshot_covers_every_field_open_position_assigns` therefore **DERIVES the required set by
reading `_open_position`'s own source**, because a hand-written list would re-freeze exactly the
assumption that fails — the same guard `run_dual`'s fill-clock signal needed after it shipped missing two
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

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The portfolio-account seam (2026-07-17)*.

## What it is (one paragraph)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *What it is (one paragraph)*.

## The five modules (the data flow)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The five modules (the data flow)*.

## The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused*.

### The RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08)*.

🔴 **`MissedSetup.time_ms` is the bar the setup DIED, and something downstream read it as "where
the setup was".** The lab's Candlestick Reversals layer anchored its marks there and painted them in
a part of the chart the setup had nothing to do with — Aaron, off the screen: *"the reversal candle
printed on the opposite side, which doesn't make sense … I'm expecting it to be that price got into
the zone for the trade and there was a reversal candle."*

✅ **MEASURED on the reference run (2020-01-01 → 2026-08-06, 155,807 M15 bars, 35 three-of-three
misses): on 32 of the 35, price sits a median $22 and up to $205 from the setup's own `edge` on the
death bar, which is a median 17 and up to 717 bars after the retrace.** That is correct for a marker
saying *this setup is now over* and useless for anything asking *where was price when it was live*.

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

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, committed `c962601`)*.

- **`run_dual(df15, df1m)`** merges the two streams on a close-time clock: the **primary** is stepped
  on 15m bars exactly as `run(df15)` (so parity is untouched); the **secondary** latches/arms/fills/
  manages on real **1m** bars — the sniper "in and out fast" a 15m bar can't express.
- **Execution** grows an `_entry_kind` tag + `step_secondary(bar1m, arm)`. A 15m bar only ever
  touches a `primary` position; a fill-clock bar only a `secondary`. They share the one position slot but
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
  50.7% (6.53R).** ✅ **B reproduced A exactly (180 trades, identical entries), so the fill clock is
  inert on its own** and C's delta is the re-entries and nothing else — without that control a
  difference in C is a mix of *the re-entries made money* and *the fill-clock stream nudged the primary*,
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
  re-entry 01:51 — same 15m SOS bar 7893, two different shift legs (120399 / 120499), the second
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
  fill-clock stream** — they would have replayed a primary-only book and ranked it against a baseline that
  has re-entries. They **REFUSE** now, naming the fix. ⚠ **`mpc_bleg` had to PIN it False and that
  one is not cosmetic**: A+ never places an order in that fork so there is no primary to follow,
  and `MpcBLegStrategy.run_dual` raises — an inherited `True` would have killed **every B-LEG lab
  run** on a `NotImplementedError`. ✅ The live bot is unaffected: its instance config states
  `exec_secondary: false` explicitly, and `algos/live/bridge.py` refuses the config outright.
- ⚠ **IT HAD NEVER OPENED A POSITION ON REAL DATA BEFORE THAT RUN, AND THREE WEEKS OF GREEN TESTS
  SAID OTHERWISE.** `run_dual` built its fill-clock signal as a namedtuple without `last_conf_high` /
  `last_conf_low` — the STRUCTURE runner trail's anchors, which the shared `_advance_stage` reads on
  **every** managed bar, primary or secondary — so the first fill-clock bar after any secondary fill raised
  `AttributeError`. Not a wrong number: the run died. 🔴 **The reason no test caught it is the
  transferable part: `tests/test_secondary.py` hand-builds its own fill-clock bar as a `SimpleNamespace`
  carrying both fields.** The fixture was more complete than production, so every test exercised a
  shape the code never produced. The regression test now DERIVES the required set by reading
  `_advance_stage`'s own source for `sig.<field>` and asserting the real `run_dual` supplies all of
  them — a hand-written list would have re-frozen exactly the assumption that failed. **Watched red
  against the bug, naming both missing fields.**
- ⚠ **WHERE THE LIMIT RESTS IS NOW A NUMBER (`exec_sec_retrace`, default 0.382), AND SWEEPING IT
  ANSWERS A QUESTION WORTH RECORDING FOR ITS SHAPE RATHER THAN ITS WINNER.** Aaron asked what
  happens if the 38.2% retrace comes out and the re-entry simply takes the fill-clock SOS. The 0.382 was a
  hardcoded constant; it is a config field now, byte-identical at the default (pinned by the suite)
  and refused outside `[0, 1.0)` at construction — 1.0 is the leg ORIGIN, where the stop is, so an
  entry there has a zero stop distance and the order is silently cancelled, which would report *the
  secondary took no trades* as though that were a finding. ✅ **Four full-history replays, run in
  parallel, with 0.382 as the CONTROL** (it reproduced 190 trades / +165.46R exactly, which is what
  says the refactor moved nothing):

  🔴 **Entering on the SOS is the WORST row and the result is monotonic — deeper is better** — which
  is mechanical rather than mysterious: **the stop is the shift leg origin whatever the entry**, so at
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
- 🔴 **THE GATES WERE LOOSENED FOUR WAYS ON 2026-08-19 AND EVERY DOOR IS WORSE. THE SWEPT-STOP
  RE-ENTRY LOSES MONEY.** Aaron's case: *in at 0.618, price takes the 0.886, swipes the stop, comes
  back, bounces off a higher fib and runs — the whole trade missed.* Three levers now exist to ask
  that question (`exec_sec_require` ∈ Breakeven / Any close / **Stopped only** / None,
  `exec_sec_zone_deep`, `exec_sec_zone_shallow`), all defaulting to the shipped rule. **9 real
  replays over 156,543 M15 + 2,343,987 M1 bars (2020-01-01 → 2026-08-18), control reproducing lab
  run `fbfc89d71fb4` exactly at 160 primaries + 7 secondaries.** The shipped rule wins on book R
  (374.17), on R-with-its-best-trade-removed (−0.81 against −1.49 … −5.70) and on drawdown
  (−15.01R against −18.08R), and the ordering is **monotonic in how much was loosened**. ⚠ **Asked
  in isolation the swept-stop door is 7 trades / −0.68R / 2 wins / 4 full −1R losses** — the pattern
  is real and taking it systematically loses. ⚠ **`exec_sec_zone_deep` is INERT on top of it** (1.0
  and 0.886 give the identical book): those legs were blocked by the breakeven gate alone, never by
  the zone, and only measuring the two separately showed it. ⚠ **Zero primaries displaced in any
  cell**, so none of it is the one-slot queue effect. ⚠ **The R differences sit inside the 15.06R
  jitter band — the DIRECTION (9 of 9) and the win/loss counts (1/1 → 3/9) are the signal.** 🔴 **The
  finding under the finding: the re-entries that DO fire mostly SCRATCH** — four of the control's
  seven land inside the ±0.15R band and eleven of "any close"'s fourteen are ≈0 or exactly −1R. A 1m
  entry gets a 1m-tight stop and is then handed to the 15m structure trail, which ratchets to
  breakeven long before a 15m target. **Entry confluence is answered; the EXIT ladder for a 1m entry
  has never been varied independently of the primary's.** Full grid: `mpc_sos_fade_optimization.md`
  → Run 23, part 1.
- **MEASURED 2026-08-19 (Run 23, parts 2–3) — THE EXIT LADDER IS WHERE THE RE-ENTRY WAS BROKEN, AND
  "HOW MANY RE-ENTRIES" IS ONE.** Four more levers, all defaulting to the shipped rule
  (`exec_sec_max_per_setup`, `exec_sec_req_m1_dir`, `exec_sec_be_at`, `exec_sec_tp1_pct`), 17 more
  replays on the same bars. 🔴 **Depth 2 / 3 / 5 / unlimited are BYTE-IDENTICAL** — in 6.6 years
  exactly one setup ever offered a second re-entry (2024-01-16 L, −1.00R) and a third never existed,
  so the cascade question has a sample of **n=1**. 🔴 **And the rule already ships**: a re-entry that
  closes at stage 0 sets `sec_stop_dir` → `mark_dead`, so a cascade can only continue through a
  SCRATCH, never through a loss — *"how many before settling into losses"* is answered in code as
  **the first real loss ends it**. 🔴 **`exec_sec_be_at="TP2"` (hold the initial stop through TP1) is
  WORSE and overturned the prediction that prompted it** — 1 win / 4 losses, and the three trades it
  rescued from a +0.05R scratch each became exactly −1.00R. **The breakeven ratchet was protecting
  them, not robbing them.** 🟢 **Banking part of the re-entry at TP1 (`exec_sec_tp1_pct`) is the
  first change in 26 replays that works** — win/loss goes **1/1 → 4/1** and ex-best turns positive
  for the first time. The diagnostic that found it: **three of the seven re-entries exited at exactly
  +$0.30 = `exec_be_buf_tk` (30 ticks)**, one of them $2.65 past TP1 with nothing banked. ⚠ **It
  costs the tail**: 50% banked cuts 2023-04-03 from +79.07R to +42.79R, and **that one trade IS the
  secondary book**. 🟢 **Best configuration measured: `exec_sec_req_m1_dir=True` +
  `exec_sec_tp1_pct=50`** — 5 trades, 4/1, **+3.19R ex-best**, best drawdown of all 26 replays
  (−14.92R), **and 32.28R BELOW control on total book R.** ⚠ **The two levers COMPOUND (+0.08 and
  +1.52 alone, +4.00 together) because the filter changes which 1m bar arms 2020-09-15 and banking
  then makes that trade a winner — a filter that looks inert on one exit ladder is not inert on
  another.** ⚠ **Zero primaries displaced in any of the 26 cells.** **Nothing shipped: this is a
  return-for-consistency trade Aaron makes, not one a table makes, and the shipped default is the
  choice consistent with this repo's stated philosophy.** Full grids:
  `mpc_sos_fade_optimization.md` → Run 23.
- 🟢 **SHIPPED 2026-08-20 — FIVE DEFAULTS MOVED TOGETHER, A SIXTH SETTING IS NEW, AND THE
  FEATURE IS A DIFFERENT ONE AFTER IT.**
  `exec_sec_req_div` OFF, `exec_sec_trigger` = `FVG in zone`, `exec_sec_stop` = `0.886`,
  `exec_sec_tp_r` = 1.25, `exec_sec_tp1_pct` = 50, and a new `exec_sec_risk_pct` = 50. Over the same
  7.9 years (2018-09-14 → 2026-08-18, 155,807 M15 + 2.74M M1) the leg goes from **10 re-entries to
  54**, and less its single best trade from **−1.77R to +7.16R**. ✅ **Primaries are +206.20R in
  every cell to the decimal and zero were displaced**, so all of it is the re-entries.
  🔴 **THE OLD DEFAULT COULD NOT FIRE ON THE BOOK IT SHIPPED WITH, WHICH IS WHY IT READ AS
  MARGINAL** — it demanded a live 15m divergence while the primary arms on a SWEEP (`exec_arm_div`
  OFF, shipped). Measured over the most recent year: **0 re-entries in 12 months.** The "ten trades
  cannot tell a small edge from a small negative one" verdict above was therefore measured on a
  gate, not on a setup, and it stands as a description of that fortnight rather than of this
  feature. ⚠ **Pin the old six to reproduce anything measured 2026-08-07 → 2026-08-20.**
- **THE EXIT LADDER WAS THE FIX, AND THE COLUMN THAT CHOSE IT WAS *LESS THE BEST TRADE*.** With the
  gap trigger on, **72% of re-entries reach +0.25R, 56% reach +0.5R, 37% reach +1R and 20% reach
  +2R; the median excursion is +0.56R** — so the scratches were never bad entries, they were a 1m
  entry handed a 15m target with a breakeven ratchet in front of it. Twelve replays of the rung and
  what banks there (re-entry R, then the same figure with its best trade removed): 0.5R/half
  **+0.14 / −5.35**, 0.75R/half **+22.03 / +4.83**, 1R/half **+24.43 / +5.63**, **1.25R/half +27.84
  / +7.16 ← ship**, 1.5R/half **+22.82 / +1.32**, 2R/half **+22.54 / +0.79**, and the old shape
  (no rung, nothing banked) **+29.50 / −0.36**. ⚠ **The headline column would have kept the old
  shape.** ⚠ **The rung also moves BREAKEVEN**, because the ratchet fires at stage 1 and stage 1 is
  this rung — the two are one decision, and 1.25R/half was the pair that won, not either alone.
- ⚠ **THE TRAIL AND THE SECOND RUNG WERE ASKED AND THE ANSWER WAS: CHANGE NOTHING.** Six more
  replays at 1.25R/half. The shipped 1% swing trail gives the best re-entry total (**+27.84R**) and
  by a distance the best PRIMARY book (**+206.20R** against +102.08R at 0.5% and +138.88R at 2%),
  because the trail is shared. Banking half at the SECOND rung as well collapses the leg to
  **+5.98R**. 🔴 **A re-entry-only trail at 0.5% has the best ex-best figure of anything measured
  (+10.12R) and is UNBUILT** — it is worth ~3R over eight years and would need its own lever, which
  is why it was left as a note rather than a build.
- 🔴 **THE RE-ENTRIES DEEPEN THE PRIMARY'S OWN DRAWDOWN RATHER THAN DIVERSIFYING IT — the first hard
  number this repo has on the correlation the root philosophy warns about in words.** Worst
  closed-trade drawdown on a $10k start: primaries alone **51.8%** (181 trades, +206.20R), with the
  re-entries at full weight **68.1%** (235 trades, +234.04R). **It is the SAME drawdown made
  deeper** — both trough in the same 2023-04-05 → 2024-10-29 stretch, inside which the primaries
  lose 6.34R and the re-entries lose a further 4.70R. They come off the setups the primaries just
  lost on, so they fail together. ⚠ Risk-adjusted it is WORSE, and that is the honest reading:
  4.0 R-per-drawdown-point becomes 3.4.
- **`exec_sec_risk_pct` (new 2026-08-20) IS THE ANSWER TO THAT, AND 50 WAS NOT CHOSEN OFF THE
  CURVE.** It scales the re-entry's LOT only — same bars, same entries, same exits — so **the R
  total is IDENTICAL at every size (27.84R)** and only the account-weighted contribution moves:
  ¼ **+6.96R / 56.2%**, ⅓ **+9.19R / 57.6%**, **half +13.92R / 60.4% ← ship**, ¾ **+20.88R / 64.4%**,
  full **+27.84R / 68.1%**, against **51.8%** with the feature off. Every step buys ~**1.6R per extra
  drawdown point** at a near-constant rate — a straight line with no knee, against ~**4.0R per
  point** for the primaries. **So the size was chosen on CONCENTRATION: one trade is +20.68R of the
  leg's +27.84R, the next is +6.06R, and the whole thing less its best is +7.16R over 54 trades.**
  ⚠ 🔴 **A BACKTEST SUMMARY WILL REPORT THE SAME R AT A QUARTER SIZE AS AT FULL** — halving the lot
  halves the win and the loss together. Multiply by this field before comparing a re-entry's R with
  a primary's, or the sizing decision is invisible in every table this repo prints.
  ⚠ It refuses 0 or a negative rather than clamping: a zero lot fills, closes and lands in the trade
  list at 0R — a trade that looks taken and moved nothing. The way to stop taking re-entries is the
  feature switch.
- ✅ **THE SUSPECTED CROSS-TALK BUG IS NOT REAL, CHECKED AND CLOSED 2026-08-20.** Aaron's report was
  that a stopped re-entry looked like it was retiring whichever setup was CURRENT rather than its
  own. Every setup-shutdown across seven full-history replays was traced to the trade that caused
  it: **zero mismatches, zero orphans.** ⚠ **What IS true and reads like it**: the shutdown fires
  whenever a re-entry closes before reaching its first rung, INCLUDING small winners — 31 shutdowns
  from 13 stop-outs in one run. That only changes a book if the one-per-setup cap is turned off, so
  it is a doc/code wording mismatch to tidy on the next pass, not a defect.
- ⚠ **THE PARITY GATE CANNOT SEE ANY OF THIS, AND AN EARLIER NOTE IN THIS SESSION SAID THE OPPOSITE.**
  `compare_strategy.py` replays 15-minute bars through `.run()`; every re-entry lever lives on the
  fill-clock path behind `run_dual`. **No `exec_sec_*` default can move the gate**, which is why six of
  them could change at once. It was still RUN rather than reasoned about, because that is what
  rule 22 asks for: GREEN (exit 0) on `engines/VANTAGE_XAUUSD, 15_4fef8.csv` and `…_49f80.csv` at
  `--warmup 1000`, both before the change and after it. ⚠ **Two other exports sitting on this
  machine (`a9c92` at bar 1356 on closed R, `a9caa` at bar 20608 on the short stage) are RED — and
  were RED in the identical place before this change**, so they are not it; their provenance is
  undocumented (neither is named anywhere in the repo) and a pre-existing red is still a red, so
  they are worth chasing on their own. ⚠ **Warm-up is not optional**: at the default warm-up all four report a
  mismatch on bar 16, which is the engines still filling.
- **NOT USABLE LIVE** — `algos/live/bridge.py` REFUSES `exec_secondary` outright
  (`UnsupportedStrategyConfig`), because the live runner drives ONE timeframe and this needs the 1m
  stream alongside the 15m (`run_dual`). The lab can run it; the bot cannot. Building the dual feed
  is a live-pipeline item, and it is correctly gated behind this being measured first.

### Reclaim Entry, and the combined value that runs it beside the gap

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Reclaim Entry, and the combined value that runs it beside the gap*.

🔴 **THE RECLAIM HALF READS ITS OWN SETTINGS — `exec_rec_require` / `exec_rec_stop` /
`exec_rec_tp_r` / `exec_rec_tp1_pct` — UNDER BOTH VALUES, AND THE SHARED `exec_sec_*` FIELDS ARE
DEAD TO IT.** That is what makes the combined value possible at all: the two halves want opposite
preconditions, different stops and different ladders, and one set of fields can only hold one of
each. Their defaults ARE the measured configuration, so selecting the trigger and touching nothing
else reproduces the book below.

**Why the two halves may share one position slot, one latch and one `_traded` stamp.** They fire on
DISJOINT setups structurally: a primary either reaches TP1 (stamping the breakeven latch, never the
loss latch) or closes at stage 0, which does the reverse. ⚠ **That is the whole safety case, so
validation REFUSES any pairing but `Breakeven`/`Stopped only`** rather than letting them race for
the latch. ✅ **MEASURED as 0, not "rare": of the 107 re-entries the two produce, ZERO share a
setup, ZERO overlap in time, and neither ever blocks a primary.**

#### The numbers — `run_dual` over 187,102 M15 / 2,801,964 M1 bars, 2018-09-14 → 2026-08-18

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The numbers — `run_dual` over 187,102 M15 / 2,801,964 M1 bars, 2018-09-14 → 2026-08-18*.

🔴 **ONE BALANCE, IN TIME ORDER — NOT A SECOND BOOK ADDED AFTERWARDS.** `run_dual` walks both feeds
on one clock through one `Execution`, and a re-entry sizes off `self.equity` at the moment its
order is PLACED, so the balance a primary sizes against already holds every re-entry that closed
before it. **MEASURED: 179 of the 181 primaries carry a DIFFERENT position size** in the reclaim
book than in the primary-only one (the first two predate the first re-entry) — the third is
$906 of risk against $1,042, and it compounds from there. This is the opposite of
`exec_recovery`, which is computed over a FINISHED book and can therefore neither compound into
the main curve nor be blocked by it; see `strategies/python/loss_recovery/CLAUDE.md`.

⚠ **"Identical" below means the 181 primaries take the same SETUPS at the same prices for the same
R** — no primary is displaced, delayed or blocked, which is what makes the R difference attributable
to the re-entries. **It does NOT mean their dollars are unchanged**, and an earlier draft of this
line said "byte-identical in every row", which reads as exactly the bolt-on defect this paragraph
exists to deny. **A sentence about a comparison has to name the BASIS it holds on.**

🔴 **THE COMBINED BOOK IS EXACTLY THE TWO HALVES — matched trade for trade on entry price, R summing
to the cent (13.09 + 19.00 = 32.09), 54 + 53 = 107, and 0 trades in one book and not the other.**
That is the claim the build had to earn, and it was earned on the third attempt; the two failures
are below because each is a rule.

⚠ **The last column is the one to read, not R** — a book that adds R and loses money is the normal
case here, because re-entries fire inside drawdowns and deepen the holes that set the risk ceiling.
The shipped gap trigger is the example: it adds 13.1R and finishes at **2,981** against
primary-only's **7,188**, because it can only carry 8.5% risk. The reclaim does not have that
problem (11.00%, the same as no re-entry at all).

✅ **It does the job it was built for, in both periods Aaron named.** Sep 2021 – Jan 2023:
+2.6R → **+9.8R** combined. Mar 2023 – Sep 2024: **−3.6R → +6.9R**, the re-entries adding +10.5R and
flipping a losing stretch. ⚠ **The gap trigger alone made that second window WORSE** (−4.1R), which
is the sharpest argument for the reclaim existing.

⚠ **The two halves are out-of-sample mirror images, and combining is what fixes that.** Split at
2022-09-01, re-entries only: the gap is **+11.0R then +2.1R**, the reclaim **+2.0R then +17.0R**,
and both together **+13.0R then +19.1R** — positive in both halves where each alone leans on one.
✅ Neither is carried by a single trade on the reclaim side (its best is +3.0R, the target caps it).

#### 🔴 Two control replays, two rules — the story is in the build notes, the rules are here

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 Two control replays, two rules — the story is in the build notes, the rules are here*.

**1. Which rule prices a side is the CONFIGURED TRIGGER's, never whichever block latched last.**
Section 3's fill-clock latch runs under EVERY trigger, including the two with no shift leg to price off,
because it moves `_l_leg`, which `_traded` / `_dead` / `_used` all read. Keying the entry price off
the latch let a fill-clock structure event price a GAP book at a 38.2% retrace of a fast-feed leg: **the
shipped book silently gained 4 re-entries and 4.9R.** Under the combined value ownership falls to
**which precondition is open**, which is well-defined precisely because the gates are disjoint.
⚠ **Do NOT gate section 3 behind a trigger test to "tidy" this** — tried twice, and both attempts
are the two rules on this list.

✅ **Rule 2 found a real defect rather than only restoring additivity.** It removed one reclaim
re-entry that had armed at the deep edge **without price ever reclaiming**, worth **+1.0R**.
⚠ **Every reclaim figure quoted before this is the pre-fix book — 156.9R over 54, not 157.9R over
53.**

#### The re-entry settings, split three ways in the editor (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The re-entry settings, split three ways in the editor (2026-08-21)*.

⚠ **No row count here, deliberately.** This section said "the 19 settings … the 8 both halves
read" and was stale within a day — the fill clock and the resting-order rule landed in the shared
group and made it 21 and 10. **A count in prose is a number with no test under it.** The exact
dead SET is pinned by `test_the_contract_kills_exactly_the_rows_the_tests_above_pin`; the group
sizes are whatever the contract says, and `python3 -c` over the meta file answers it in a second.
⚠ **A new row added to this block lands in the shared group by default and nothing asks whether it
is dead under a trigger** — that test only fails when a row IS killed without proof, never when one
that should be killed is not. Ask the question by hand when you add one.

⚠ **The retrace is the odd one — it is dead under the SHIPPED trigger too.** Only the `Structure shift`
retraces a leg; the gap rests at the primary's own price and the reclaim at the deep edge. It is
killed under all three of the other values.

🔴 **A DEAD ROW IS NOW HIDDEN, NOT GREYED (2026-08-27).** It was drawn greyed with its reason
beside it; on the shipped defaults that is SEVENTEEN dead controls the reader scans past to reach
the live ones, and Aaron reversed it: *"hide them, like everything else"*. The contract did not
change — the same key, the same conditions, the same reasons — only what the editor does with it.
⚠ **The reason is still REQUIRED on every one**: the finished-run params panel prints it, to say
why a setting did nothing on a run already taken.
⚠ **Not cosmetic either way — `stress_tester.param_is_reachable` stops perturbing a dead row**,
which is the point: shifting a setting the strategy never reads books a guaranteed 0% change and
reads back as *"tested, rock solid"*. That answer is unchanged by the hiding.

🔴 **THE SHALLOW ZONE EDGE LOOKS AS DEAD AS THE REST AND IS NOT, AND THAT IS THE TRANSFERABLE
FINDING.** The reclaim ignores the zone by design — this file says so and a test says so — so it
was on the dead list on the way in. It is live, because **section 3's fill-clock latch runs under
every trigger, its gate reads the zone, and it writes the same per-setup bookkeeping the reclaim's
own arm is measured against.** ⚠ **Reading the consuming line was not enough here**: the other nine
rows each have ONE reader inside an explicit source branch, and this one launders through shared
state with many. ⚠ **At the shipped cap of one re-entry per setup the cap refuses first and MASKS
the difference**, so the probe that settled it had to turn the cap off — a check that would have
agreed with the wrong answer at the default. Pinned by
`test_the_SHALLOW_zone_edge_is_NOT_dead_under_the_reclaim_so_it_is_never_hidden`, which is the only
thing standing between the next reader and a wrong answer on screen.

**TESTED:** 5 new tests in `tests/test_secondary.py` — 4 pinning the deadness claims at the arm and
the ladder, 1 the counter-case, 1 tying the contract's dead set to them. **9 mutations, 9 killed**
(357 strategy tests green, 49 backend param-gate/sensitivity tests green).
**PARITY:** `compare_strategy.py` green on the 2026-08-21 export at `--warmup 100`. ⚠ **The gate is
structurally blind to all of this** — it replays 15m bars through `.run()` and every re-entry lever
lives on the fill-clock path behind `run_dual`.

#### A re-entry records WHAT THE TRADE BEFORE IT DID, and that is a second question (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *A re-entry records WHAT THE TRADE BEFORE IT DID, and that is a second question (2026-08-21)*.

🔴 **It is NOT a rename of `*_src`, and collapsing the two is the mistake to avoid.** `src` is the
trigger that was CONFIGURED; this is the outcome that was OBSERVED. They agree under every shipped
configuration, which is exactly why they must stay two fields — point the gap half at
`Stopped only` and a gap-triggered re-entry is a re-entry after a LOSS, and the chart has to say so.

⚠ **`None` means the run could not tell, and must never become a word downstream.** A re-entry
armed through the `None` precondition follows a primary that may not have traded at all.
⚠ **Stopped is tested before closed.** `_prim_closed_sos_*` is stamped on every close whatever the
outcome, so a stopped primary sets both latches; asking "closed?" first calls every stop-out a
plain close.

🔴 **`SecondaryArm.update` has TWO `SecArm` returns and a test can leave through only one.** The
first version of these tests passed while the mutation that stripped the field off the plain return
reddened NOTHING — the resting-order rule had been defaulted ON in the same tree, so every test in
the file was exiting through the other branch and the untested return was free to be wrong. **A
duplicated construction is only as covered as its least-visited branch**, and the fix was to
parametrise the tests over the rule rather than to trust the default.

#### Nothing in the re-entry layer says "1 minute" any more (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Nothing in the re-entry layer says "1 minute" any more (2026-08-21)*.

⚠ **A saved run or bot config carrying the old string is REFUSED**, not silently reinterpreted —
the same behaviour as the `Deep-edge reclaim` → `Reclaim Entry` rename the day before, and for the
same reason: quietly falling back to a default would replay a different strategy under the old
name.

🔴 **THE PANEL GROUP NOW NAMES NO TIMEFRAME AT ALL, AND THAT IS THE RULE, NOT THE FIX.** It read
`Secondary re-entries (1m)`; the obvious change was `(5m)` and it would have been the same defect
one turn later. **A heading must not hardcode a number the row beneath it owns** — the fill clock
is one setting, in one place, and every other surface points at it. `param-gates.spec.ts` pins the
ABSENCE of a timeframe in the group name rather than the presence of a particular one.

⚠ **A MEASUREMENT TAKEN ON 1m DATA STILL SAYS 1m, EVERYWHERE, AND WAS DELIBERATELY LEFT ALONE.**
Rule 4 cuts both ways: you may not edit a recorded figure to match today's default any more than
you may invent one. The sweep skipped every line carrying an R figure, a bar count or a date — so
`1m 2,804,720 bars / +147.56R` reads exactly as it was run, and the prose around it no longer
claims that is what the strategy does now.

⚠ **The IDENTIFIERS were left alone and that is a debt, not something to be proud of** — `df1m`,
`sig1m`, `M1State`, `Structure1m`, `_Bar1mSig`. Renaming a public parameter moves every caller
(`python_runner`, `run_report`, the portfolio stack, the tests) for a cosmetic gain, and this layer
is one promote away from money. `run_dual`'s docstring now says in as many words that the second
frame's timeframe is the caller's choice and that the parameter name is the one thing in there
which cannot be trusted.

⚠ **A DUPLICATE OF THE SECTION ABOVE SHIPPED IN `e107345` AND WAS DELETED HERE.** Two identical
copies, ~1,950 bytes, from an insert script run twice against an anchor that was unique the first
time. It was caught by the NEXT insert refusing — `assert s.count(anchor) == 1` — rather than by
anybody reading the file. **The assertion that stops a script writing twice is the same one that
tells you it already did; a script that inserts without counting its anchor has no way to notice.**

⚠ **`exec_rec_stop` of `Shift leg` or `swing low` is REFUSED**, stricter than the gap trigger's rule,
because the entry is a FIXED price and a fill-clock swing can land either side of it. That refusal is
also what lets section 2c read the stop anchor BEFORE the shift leg latch — both legal anchors are pure
reads of the 15m fib. ⚠ **Do not hoist that lookup for the other triggers**: under `Shift leg` the
anchor IS the leg assigned by that latch.

⚠ **The exit ladder is not a detail on this half.** All-out at 3x its own risk is the default and is
why the numbers hold; the shipped bank-half-at-1.25x ladder gives **3,111x, worse than taking no
re-entry at all** (3,582x). A re-entry priced this tight has to be allowed to pay for the ones that
fail.

**TESTED:** 350 strategy tests green (24 new), 11 rules each watched RED by a named mutation —
detail in the build notes. **PARITY:** `compare_strategy.py` exit 0 on `4fef8` and `49f80` at
`--warmup 1000`, before and after. ⚠ **The gate is structurally blind to all of this** — it replays
15-minute bars through `.run()` and every re-entry lever lives on the fill-clock path behind
`run_dual`, so a green run means the primary is untouched and nothing more.

⚠ **NOT USABLE LIVE, and no new refusal was needed** — `algos/live/bridge.py` already refuses
`exec_secondary` outright, so the whole re-entry layer including both new values is covered.

## The exit ladder — every TP/SL lever, and which ones are switchable

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The exit ladder — every TP/SL lever, and which ones are switchable*.

| Stage | What sets it | Switchable? |
|---|---|---|
| **Stop loss** | A fib on the deep side of 0.5, `exec_sl_level` ∈ {0.618, 0.702, 0.786, **0.886**, 1.0, **Custom**}, then `exec_sl_buf_tk` ticks beyond it. **Default 0.886 since 2026-07-27** (the deep edge of the entry band, and what Aaron trades); 1.0 = the leg origin. **"Custom" (2026-08-02) reads `exec_sl_custom` instead** — any ratio in (0, 1.0]. | **0.886 → 1.0 only** (the dropdown values or any Custom ratio between them) — anything shallower is unsupported, see the warning below |
| **TP1 / TP2** | Fibs, chosen AUTOMATICALLY by how deep the entry was. Deep entry → TP1 = 0.5, TP2 = 0.382. Shallow → TP1 = 0.382, TP2 = 0.0 (the swing extreme). | **No** — only the sizes (`exec_tp1_pct` / `exec_tp2_pct`, **both default 0** since 2026-07-27: bank nothing, ride the runner) |
| **TP3 (the runner)** | No target at all. It rides a trailing stop, and it is where the strategy's money is (>100% of net in every window measured). | **Yes** — see below |
| **Stop staging** | Three phases, always on: (0) the full stop → (1) after TP1, breakeven + `exec_be_buf_tk` → (2) after TP2, a floor, then the trail. | **No** |
| **The breakeven buffer** | `exec_be_buf_tk`, default **30 ticks = $0.30**. How far past the entry the stage-1 stop sits. **SWEPT 2026-08-11 and 30 is the optimum — every wider value is worse, monotonically** (60 → −6.17R, 400 → −35.90R). ⚠ **It does NOT cover the swap and cannot be made to**: one night of long swap is $0.796/oz, 2.7× the whole buffer, so ~29% of scratch exits are net losses on every real account — and widening it costs ~5R of total return per 1R of scratch rescued, because the same move that saves a returning trade cuts a running one. **Do not widen it** — Run 17. ⚠ **"Do not make it swap-aware" is AMENDED, not retracted, as of 2026-08-24** — `exec_be_buf_mode` can now express the buffer as a fraction of the trade's own stop, optionally floored at what the trade has cost; it ships `"Ticks"`, so this row still describes the shipped bot. Run 17's ceiling on what a cost-covering stop can recover (+2.11R against 15.06R jitter) is unchanged and still binds. | **Yes, and the FIXED buffer is already at its best value** |

🔴 **THE FORM NOW CASCADES: THE MODE PICKS WHICH CUSHION IS ON SCREEN (2026-08-27).** The tick figure
shows under `Ticks` and the fraction, the cap, the cost margin and the conflict rule show only under
the modes that read them — `_be_buffer` returns on the tick branch before any of the other four is
touched, so under the shipped default they were four settings that could not do anything. ⚠ **This
was not cosmetic. A run launched on the fraction mode at 0.35 put the stage-1 stop $12.92 into
profit instead of $0.30 and closed the 2026-06-04 short at +0.35R where the shipped mode held it to
+4.51R — and nothing on the form said which cushion was in play.** ⚠ **The same rule was applied to
the short-hold variant's five rows and the floating-gap anchor's precedence chain**, both read
straight off the returning branch in `execution.py`.
| **The TP2 floor** | `exec_tp2_stop_mode`: **"TP1 price"** (tight, can scratch the runner on the first pullback) / "Breakeven" (most room) / "One trail step behind" (never below breakeven). | **Yes** — dropdown |
| **The runner trail** | `exec_runner_trail`: "Fixed step" (a `exec_trail_step` grid ratchet anchored on TP2) / "Structure (swing)" (park the stop at the structure engine's last confirmed swing low/high, offset by `exec_struct_trail_buf_tk`) / **"Structure + % ratchet"** (same anchor, then climb one `exec_trail_pct`-of-price step per step of favourable move). | **Yes** — dropdown |
| **The ratchet step** | `exec_trail_pct`, default **1.0**. Only read in "Structure + % ratchet" mode. A PERCENT of price, never dollars — see below. | **Yes** |
| **Early bail-out** | `exec_close_opp_sos` (default OFF) force-closes on an opposite SOS instead of riding to the stop. **Measured INERT** (Run 5): turning it on produced a byte-identical trade list — an opposite SOS never fires before SL/TP has already resolved the position. There is nothing on the other end of this lever. | toggle exists, **does nothing** |
| **Deep-entry stop override** | `exec_sl_deep` (default **OFF**, Pine `execSlDeep`, 2026-08-02). An entry filling AT OR DEEPER THAN 0.786 puts its stop at the leg origin (1.0) instead of `exec_sl_level`; 0.702 and shallower keeps the chosen level. It exists because the entry band and the stop share the 0.886 line, so the band's deep end is priced against a stop it is nearly touching. 🔴 **MEASURED 2026-08-16 (Run 18) and it stays OFF: it costs 24.0R with the secondary live and 23.0R without**, on a full 2×2 over one window (2018-09-14 → 2026-08-14, bar fills) — the shipped cell is the best of the four at +164.4R / 189 trades. The mechanism is Run 11's from the other direction: the targets are fibs and do not move, so a wider stop makes every winner worth fewer R while every loss is still −1R (a 0.786 entry goes from a 0.100 stop to a 0.214 stop, the runner falls 7.86R → 3.67R and the position is less than half the size). ⚠ **It DOES hold a shallower drawdown** (−4.8R vs −5.5R) — expensive, not worthless, if drawdown ever becomes the objective. ⚠ **Its interaction with `exec_secondary` is 1.0R against sd 15.06R**, so the two are separable. This is the first direct measurement of the SHIPPED narrow version; the 2026-08-02 revert `mpc_strategy.pine` records was of a WIDER version that also caught 0.702, and the two agree. ⚠ **Its toggle is INERT when `exec_sl_level` is already 1.0** (or Custom = 1.0), because both states then place the same stop; the meta says so with `disable_if` + `disable_note` and the lab takes the row off the screen, matching the Pine's `active = execSlLevel != "1.0"`. ⚠ **Its OFF label is `Stop {exec_sl_level}` — a TOKEN the editor substitutes, never a typed `0.886`**, which would be a second copy of a neighbouring param's value. | **Yes** — toggle |

🔴 **26 params are marked `hidden` in the meta (2026-08-15) — RETIRED FROM THE EDITOR, NOT REMOVED.** Every field is still in `SosFadeConfig`, still at its default, still sent on every run and still settable through the API; only the row is gone, so the editor is the levers still under test rather than every lever that exists. Aaron's call, and his framing is the rule: *"I don't want you to delete the configurations because I might talk to you, and you might be able to toggle it back on super easy."* **Ask and it comes back — one `hidden` flag.** The set: `exec_longs`/`exec_shorts`/`exec_bleg`/`exec_conf_sz`; `exec_arm_div` and the five RSI engine dials; `exec_poi_source`/`exec_ob_deepen`/`exec_fvg_pre_zone`/`exec_fib_overlap`/`exec_fib_deep_edge`; and the whole `Higher-timeframe filter` group. 🔴 **SEVEN MORE landed the same day under a STRICTER bar, and the bar is the part worth keeping.** The first batch above was chosen on "never moved across every stored run", and Aaron rejected that criterion outright: *"we did backtest with and we proved that they're not worthy or have another setting that beats it consistently. Keep that setting and hide the others."* **Never moved is the ABSENCE of the experiment, not its result.** So the seven each name a sweep in `mpc_sos_fade_optimization.md`: `exec_close_opp_sos` (Runs 5 AND 6 — *exactly 0 difference*, twice; an opposite SOS never fires before SL or TP has resolved), `exec_tp2_stop_mode` (Run 2's 525-combo grid — TP1 price wins at 70.7R, Breakeven is the harmful one), `exec_struct_trail_buf_tk` (Run 2 — 10→80 ticks moves it 0.4R, *"do not chase it"*), `exec_trail_step` (Run 2 — the fixed-step family loses by 8R with no exception, and its `show_if` means the row has never once rendered), and `exec_fvg_deep_only` + `exec_no_late_day` (Run 12 §3 and §4 — two of the four relax routes, all of which lost money or were noise). 🔴 **`exec_be_buf_tk` WAS in that list on Run 17's evidence and came OUT on 2026-08-27, and the
rule behind that is general: A ROW A `show_if` MAKES CONDITIONAL MUST NOT ALSO BE SETTLED.** Run 17
swept the tick buffer and nothing beat 30, which is the bar for settling — but the buffer MODE has
three values and the shipped one is Ticks, so this figure is what the ladder reads on every live
trade while the two fraction fields it competes with were on screen. **The form was showing the
cushions that were not in force and hiding the one that was.** Between them the two mechanisms hide
a row everywhere: the gate takes it off wherever it cannot matter, `hidden` takes it off wherever it
can. Pinned by `test_no_NEW_param_is_both_settled_and_conditional`, which also freezes the five
older rows that still carry both and names them as an open question rather than asserting them
away. ⚠ **`exec_sl_buf_tk` is the case that shows the bar biting and it stays VISIBLE**: it WAS in a grid — Run 4 — and Run 4 is marked *INVALID, DO NOT USE THE NUMBERS*, which is worse than untested. ⚠ **The master switches (`exec_arm_sweep`, `exec_aplus`, `aplus_window`), the secondary mechanics and `flat_by_close` have ZERO mentions in the optimization log and therefore stay**, however long they have sat still. ⚠ **`exec_risk_pct` is never hidden on any criterion** — it decides position size on the strategy the LIVE bot runs. ⚠ **The divergence VETO is deliberately NOT in it** — `div_veto` and `exec_respect_veto` are ON and still refusing setups, so the ARM is settled and the behaviour is not; hiding those would take a live rule off the screen. ⚠ **`exec_conf_sz` is not a settled setting but a DEAD one** — declared in `config.py` and referenced only in a comment, so nothing reads it. ⚠ **`exec_req_fvg`, `exec_deep_fib`, `exec_sl_level` and `exec_secondary` stay visible because they have actually been moved on real runs**; a param somebody tunes is a live question whatever it defaults to. ⚠ **Only THREE of the first nineteen carry a sweep** (`exec_poi_source` and `exec_ob_deepen` off Run 15's order-block thread, `exec_htf_exhaust_only` off Run 5's zero-effect pair) — the rest are hidden on Aaron's direct instruction or because they are structural (longs/shorts), which is a legitimate reason and not a measured one. Say which is which rather than letting the next reader assume the whole set was proven. ⚠ **The "never moved" figures behind the first batch came from the 15 `mpc_sos_fade` runs then in the lab (19 now), and that is the whole sample** — older rows were deleted, so it means "nobody has touched these lately", never "never in this strategy's history". Mechanism, and the escape that shows a hidden param moved off its default: `command-center/frontend/CLAUDE.md` → `ParamEditor.tsx`.
| **Minimum stop distance** | `exec_min_stop_mode` ∈ {**"Off"**, "% of price", "Fixed $", "x ATR(14)"} + `exec_min_stop_val` (0.10). An ENTRY filter, not an exit lever — it lives in this table only because it is the guard for the `exec_sl_level` hazard two rows up. A setup whose stop lands closer to the entry than the floor places no order and records block code 7. | **Yes** — dropdown + floor; ported 2026-07-30 |
| **Time stop** | `exec_time_stop_mode` ∈ {**"Off"**, "Before TP1 only", "Always"} + `exec_time_stop_hrs` (36.0). Close a position open for that many CALENDAR hours. **"Before TP1 only" fires only at stage 0** — TP1 never touched, so the stop never staged to breakeven; touching TP1 makes a trade immune for the rest of its life. The exit leg books as `L-TIME` / `S-TIME`. Added 2026-08-05; **defaulted ON ("Before TP1 only", 36h) 2026-08-06 — the baseline moved.** | **Yes** — dropdown + hours; see `### The time stop` |
| **Scale-in (ADD size)** | `exec_scale_in` (default **OFF**) + `exec_scale_mode` (**"Trail"**) + `exec_scale_max_adds` (**3**) + `exec_scale_cap_x` (**0.5**). Past TP2, adds to a runner the trail is already protecting, sized so the add's worst case equals the profit the stop already guarantees. **The only ADDITIVE lever here; every other one is protective.** Added 2026-08-16; defaults re-measured 2026-08-18 after the fill model was corrected. **Since 2026-08-19 the adds also carry their own TAKE PROFIT** — `exec_scale_tp_mode` (**"Ride"**, i.e. no target, which is what the measurement says; it shipped for one day on `"Prev week H/L"` and was reversed once the 4.38R gap behind that choice turned out to be 25.64R). ✅ **Five** `cfg_*` columns. ⚠ **The fifth is UNGATED until a fresh export carries `cfg_scale_tp`.** | **Yes** — toggle + mode + two numbers + where the adds bank; see `### Scale-in` |

### The breakeven buffer can be a FRACTION of the stop (`exec_be_buf_mode`, 2026-08-24, ships OFF)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The breakeven buffer can be a FRACTION of the stop (`exec_be_buf_mode`, 2026-08-24, ships OFF)*.

🔴 **The cap is the point, not a safety belt, and it is why the fixed buffer sweep read the way it
did.** A buffer that reaches the rung which staged it closes the trade at the target instead of
protecting a runner. MEASURED on run `5a5e2174d095` (243 trades, ECN costs charged): that happens on
**0 trades at 30 ticks, 24 at 300, 70 at 600** — so a wide fixed buffer stops being a breakeven stop
and becomes an exit, and the widest rungs were losing R for that reason rather than by cutting
winners early. As a fraction: **0.20R never reached the rung on any of the 243; 0.35R did on 5%;
0.50R on 24%.**

⚠ **Aaron's premise was right about his trades and wrong about the typical one.** The median round
trip costs **$0.020/oz** — 6% of the $0.30 buffer — but **66 of 243 trades (27%) cost more than it**,
and **10 of the 46 scratches are genuine losses.** The driver is overnight financing (correlation
**0.727** with hold time), which swings the per-trade cost roughly **250-fold**. That range is the
argument against any fixed distance, and it is the whole argument.

🔴 **THE COST FLOOR IS THE THING RUN 17 SAID NOT TO BUILD, AND ITS CEILING STILL BINDS.** Run 17
rejected a swap-aware stop and asked to be re-read first; it has been. Its mechanism objection
survives — only overnight trades pay financing and those are the runners — and **the cap bounds that
without reversing it.** Its ceiling on what a stage-1 ratchet can recover, **+2.11R over 6.5 years
against 15.06R of run-to-run jitter**, is unchanged. **So the cost half cannot be argued on return;
argue it, if at all, on the 10 losses currently reported as breakevens.** The FRACTION half is a
separate question Run 17 never asked — it swept the buffer's SIZE and never its SHAPE.

⚠ **The conflict case REFUSES to stage.** When accrued cost alone sits past the cap, no price both
covers cost and stays under the rung, so the frozen entry stop is held. Staging anyway is a stop
labelled breakeven that guarantees a loss. A conflicted LONG stays conflicted (the cap is fixed,
cost only grows); a SHORT can recover on the swap credit. Stage 2 is untouched, so the second rung
still lifts the stop and hands it to the trail. `exec_be_cost_conflict = "Clamp to cap"` is the
measurable alternative and is not the recommendation.

🔴 **AND THE CONFLICT NEVER HAPPENS — MEASURED 2026-08-24, THE SETTING IS DEAD CODE.** The two runs
that differ only in `exec_be_cost_conflict` came back **trade for trade identical** (fingerprint
`8088d3411b5e4449`, 246 trades each, matched on entry time, direction, entry, exit and R). Accrued
cost never once grew past 75% of the entry → nearer-rung distance, because on gold at this sizing
costs are small next to that distance. **The branch above has unit tests and has never made a
decision on real bars** — repo rule 9 landing inside a feature, and the tests that cover it
construct the conflict artificially, which is the *fixture more capable than production* shape.
⚠ **Before this build is ever switched on, either prove the branch reachable at a width somebody
would actually use, or delete the setting and hardcode the clamp.** Run 26.

🔴 **SWEPT TEN WAYS 2026-08-24, AND EVERY ONE LOSES — Run 26.** Best variant (cost floor at 0.20R,
margin 0.05R) is **+150.8R against the control's +159.1R**, with a **worse** drawdown (47.91% vs
46.79%). Every rung in the table is below the control on return and above it on drawdown. The
problem being fixed — 10 breakeven exits that are really small losses — is worth **−0.52R over 6.5
years**, so the cheapest complete fix costs ~**16R per 1R rescued**, against Run 17's 5:1 on a
Standard book. ⚠ The 8.3R gap sits inside the strategy's **sd 15.06R** run-to-run spread, so the
best variant is *"not measurably worse"* and never *"better"* — which is not an argument for adding
five settings to a live strategy. ✅ **Two things the sweep vindicated**: the cap works (best single
trade stays **24.6R at all ten settings**, where Run 17's uncapped widening ate the runner), and the
cost floor genuinely beats the plain fraction because it only widens on trades that have SPENT
money, leaving the same-session runners alone (top-five **86.0R, identical to control**, where the
wide plain-fraction rungs clip it to 82.1R). 🔴 **The narrowest rung is the worst value in the
table** — `frac 0.10` produces MORE scratches than the control (51 vs 46) and hands back MORE R,
converting winners into scratches without fixing any scratch. Full tables, run ids and basis:
`mpc_sos_fade_optimization.md` → Run 26.

✅ **PARITY GATE GREEN, 2026-08-26 — rule 22 is now SATISFIED for this change.**
`compare_strategy.py "VANTAGE_XAUUSD, 15_6fb2a.csv"` → **exit 0 at warmups 100 / 200 / 500 / 1000 /
2000**, 21,259 bars from 2025-10-01. ⚠ **It proves the SHIPPED path only.** The five new fields have
no Pine counterpart, so the export configures them at their off position and a green says **nothing**
about the fraction or cost modes — the same structural blindness this file already records for the
Custom stop level. ⚠ **And the harness itself warned that the no-gap arm was not exercised**: this
export ran with Require-FVG ON, so neither side entered that fallback branch. A green covers the
bars it walked, never the branch nobody entered.

⚠ **At warmup 0 the gate is RED at bar 16 (`px_s_stage` py=1 pine=0), and that is PRE-EXISTING.**
Confirmed rather than assumed: the identical failure, same bar, same field, same values, reproduces
on the code from BEFORE this change in a throwaway worktree at `1ff36e4^`. Green from **warmup 50**
onward on both. **A pre-existing red is still a red and is not retired by this note** — it is
recorded here so the next reader does not spend the afternoon blaming the breakeven buffer for it.

⚠ **THE SHIPPED PATH IS UNCHANGED.** The control run reproduces the pre-change
baseline `5a5e2174d095` **trade for trade** (fingerprint `13fc4e5f9c7a95fb`, 243 vs 243 — ⚠ the
FIRST version of this fingerprint keyed on `entry_time`, which is not a field in these trade records,
so `.get()` returned `None` for every trade and that component compared nothing to nothing; corrected
to `entry_ms` + `exit_name` on 2026-08-25 and both claims survived. **A comparison built from several
fields degrades SILENTLY — assert the key exists before you fingerprint on it.** Run 26), so tick
mode is byte-identical to before this build. `compare_strategy.py` has NOT run — no decision-stream
export exists on this machine (the CSVs here are trade lists and engine chart data), which is the
"9 of 14 gates could not run" condition the root CLAUDE.md records. ⚠ **Rule 22 is NOT satisfied.**
⚠ **No Pine counterpart either**, so even with an export the gate could never configure a non-default
run of these five fields — the same blindness this file already records for the no-gap arm gate and
the POI source.

**TESTED:** 21 tests in `tests/test_be_buffer.py`, 21 of 21 watched RED by 18 mutations. ⚠ **One was
VACUOUS on its first pass and is recorded rather than quietly replaced** — it asserted the buffer
reads `_sl` rather than "the live stop", and `Execution` has no live-stop attribute, so no mutation
could redden it. **A test that cannot go red is a claim with nothing behind it**, and that one would
have read forever as proof the hazard was considered. Story:
`docs/SOS_FADE_BUILD_NOTES.md` → *The breakeven buffer becomes a FRACTION of the stop*.

### The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)*.

⚠ **Both rows were measured at `exec_tp1_pct = exec_tp2_pct = 1`, NOT at the shipped 0/0** (found
2026-07-28). The A/B is apples-to-apples so the comparison stands, but the absolute figures are not
the shipped configuration: at the true 0/0 default the same window gives **110.65R**, and the 1%+1%
rungs cost 1.4R. Quote 110.65R as "the current bot", not 109.3R — and run `compare_strategy.py` at
0/0 so the parity gate tests what the Pine actually ships.

**⚠ `exec_sl_level` — `"0.886"` (the default since 2026-07-27) and `"1.0"` only. Do NOT sweep or
ship 0.618 / 0.702 / 0.786** (Run 4, 2026-07-26). The entry is a resting limit inside the
**0.5–0.886 fib band**, and all four sub-1.0 levels sit inside that SAME band — so the stop can be
placed at, or past, the entry price. Nothing validates the result.

### Scale-in (`exec_scale_in`, 2026-08-16) — the first ADDITIVE lever this bot has ever had

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Scale-in (`exec_scale_in`, 2026-08-16) — the first ADDITIVE lever this bot has ever had*.

🔴 **THE TRIGGER IS THE TRAIL (stage 2), NOT A TARGET, and that is what makes it self-regulating.**
At TP2 the stop is only at TP1, so `locked` is small while `price - stop` is large and the affordable
add is a rounding error. Once the trail ratchets up near price the same arithmetic permits a LARGE
add. A trending runner buys size; a stalling one buys nothing, with no extra "is this trade still
good" test.

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

🔴 **AN ADD THAT HANDS THE WHOLE GUARANTEE BACK CLOSES THE TRADE AT EXACTLY $0.00 — and until
2026-08-18 nothing in the run said an add had ever existed.** That is the affordability rule
landing on its own worst case: `add_qty = locked / per_unit`, so a stop-out at the SAME stop the
lot was sized against cancels to the cent. Run `295a6ff29d21` did it 8 times in 160 trades, and
the reader saw a SHORT entered at 4098.60, exited at 4085.07 — visibly in profit — labelled `Lost`
with a P&L of zero. **Every field that could have explained it describes the BASE lot only**:
`qty`/`size` is the base size, `legs` is the exit ladder, `mfe_usd`/`mae_usd` are excursions on the
base. So `Trade.adds` now records each FILLED lot (`{price, ms, qty}` — `_add_lots`, a report-only
twin of `_adds`, which `_exit_portion` spends on the way out), `backtest/output.py` puts it on the
equity-curve point, and the chart draws an `Add` line per lot. **The P&L identity in `Trade`'s
docstring is now stated in full and it needs every lot** — base leg + each add + costs.

**3 tests in `tests/test_execution.py`, all MUTATION-proven** — the lot is recorded, the P&L
identity closes only when every lot is read, and a trade that never added carries an empty ledger.
Deleting the one `_add_lots.append` line reddens exactly the first two. ⚠ **The exact-flat fixture
needs `exec_scale_cap_x = 2.0`**: at the shipped 0.5 the CAP binds first, the add is smaller than
the offsetting size, and the trade still books a profit — so the $0 outcome belongs to the
UNCAPPED affordability rule, not to scale-in in general.

⚠ **`_add_lots` is in `_POSITION_FIELDS`**, so a restarted live bot restores its own record of what
it bought. ⚠ **The cost of that outcome is real and small: those 8 trades were worth +6.27R
un-scaled, against +154.73R that the same toggle ADDED over the run** (`295a6ff29d21` 295.91R with
scale-in on vs `1f98a36d063c` 141.18R with only that toggle flipped, same window, same params).
**Do not read the $0 trades as an argument against the feature; read them as the guarantee being
paid for.** ⚠ **They are also invisible to a win rate** — a scratch is neither, which is what
`scratch_count` has always been for.

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

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Scale-in gained a MODE — and the first answer was measured on a broken fill (2026-08-18)*.

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

### The adds got a TAKE PROFIT, and the measurement said not to (2026-08-19)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The adds got a TAKE PROFIT, and the measurement said not to (2026-08-19)*.

**It was measured before it was built, and every target lost to riding.** XAUUSD 15m 2018-09-13 →
2026-08-14, PU Prime ECN costs, on `Trail` 3 × 0.5×, 182 trades. 🔴 **These are the RE-MEASURED
numbers, taken after the resting-order fix below — the first set was wrong and is void.**

🔴 **THE ORDERING IS THE FINDING, NOT ANY SINGLE ROW.** That column sorts by how OFTEN the target
fires: weekly levels are far away and rarely bind, H4 levels are near and bind constantly. A
separate control run — banking at a flat multiple of base risk rather than at structure — produced
the same monotonic curve independently (1R **126.76R**, 3R 134.19R, 6R 141.24R), and banking at 1R
came out **below never scaling at all**. Two unrelated target families, one shape: the adds earn on
the few trades that run a long way, and every target truncates exactly those. ⚠ **The control is
untouched by the bug below and still stands** — its target is a fixed price off the base entry, so
there is no level and nothing to mitigate.

🔴 **BANKING BUYS A SMOOTHER RIDE AND PAYS FOR IT OUT OF THE TAIL — the last three columns are the
honest case FOR a target.** Strip the top 20 trades and the ranking inverts on risk-adjusted return:
prev day 14.49 and H4 14.60 against Ride's 11.99, with drawdown falling 10.34 → 7.15. On the
ordinary book a target is genuinely better. It only loses because the extraordinary book is where
this strategy earns, and truncating it costs more than the smoothing is worth.

⚠ **Drawdown on the FULL book barely moves** (7.15–7.51 against Ride's 7.24). Read against the
whole sample, a target is not buying safety.

⚠ **VOID, NEVER RE-MEASURED:** `daily + weekly` 174.35R, `daily + weekly + H4` 161.00R and
`session H/L` 159.39R. All three came off the throwaway harness that carried the live-bar flaw, and
none is a shipped option. Do not quote them; re-measure if they are ever wanted.

⚠ **The worst trade is −2.06R in all 16 configurations, identical.** That is the answer to the
question that prompted the work: the affordability rule already stops an add turning a winner into
a loser, so there is no giveback left for a target to prevent.

✅ **IT SHIPS ON `"Ride"` — settled 2026-08-19 (Aaron), after one day on `"Prev week H/L"`.**
He picked the target deliberately, wanting certain money off the runners rather than the best
expectancy, and **on the number he was given that was a sound trade: a 4.38R gap to `Ride`, INSIDE
this strategy's 15.06R jitter.** "Certainty for no measurable cost" is a reasonable thing to buy.
The 4.38R came from the run with the live-bar bug in it. **The true gap is 25.64R — OUTSIDE the
jitter, and about 13% of total return.** Re-asked on the real number, he reversed within a minute.

🔴 **THE LESSON IS ABOUT THE DECISION, NOT THE DIAL, and it generalises past this input.** A wrong
measurement does not arrive looking wrong. It arrives as a **reasonable-looking number** and quietly
buys a judgement call: nothing about "4.38R" was suspicious — it was small, plausible, and it made a
preference cheap. The defect was two layers away in a mitigation flag, and the ONLY symptom it ever
produced at this level was a default nobody would otherwise have picked. ⚠ **So a judgement call is
only as settled as the measurement under it. When the number moves, go back and re-ask the
question** — do not carry the earlier answer forward as a decision already made. Rule 4 says never
write a guessed number into a doc; this is its neighbour, and it costs more: **a wrong number that
has already been ACTED on leaves a defensible-looking decision behind, and the decision outlives the
correction unless somebody deliberately goes back for it.** ⚠ Session H/L is deliberately not an option:
worst measured, and it would need six more mirrored Pine variables.

🔴 **THE TARGET IS RESTED AT THE BAR'S CLOSE AND FILLS ON THE NEXT BAR (`_add_tp_level`), AND THAT
IS THE WHOLE REASON TWO OF THE FOUR MODES WORK AT ALL.** Resolved from the LIVE bar instead —
which is how this was first built — `"Prev day H/L"` and `"H4 H/L"` banked **ZERO times in eight
years**, returning a figure byte-identical to `Ride`. They were not short of levels: daily resolved
**1,804** valid targets and H4 **2,438**, every one of them standing and beyond the newest add.

⚠ **WEEKLY HID IT COMPLETELY, AND THAT IS THE TRANSFERABLE PART.** A week level dies on a **CLOSE**
through (`BREAK_HIGH` / `BREAK_LOW`), so it survives the spike that fills it and banked normally
throughout. The one family anybody was looking at was the one family immune to the defect — the
default looked healthy while two of its three alternatives were inert. **A feature that works on the
option you are watching tells you nothing about the options you are not.**

⚠ **The fix is not new machinery — it is the one-bar order delay the rest of this file already
honoured.** TradingView places `strategy.exit(..., limit=)` at a bar's close and it is live on the
NEXT bar; the base ladder stages `dec.stop = self._current_stop()` in Phase B for exactly this
reason. The adds were the single path that skipped it. `test_a_target_swept_by_the_filling_bar_still_fills`
pins it, and reverting the fix reddens that test and only that test.

🔴 **BANKING DOES NOT HAND THE ADD SLOT BACK.** Pine's `lAddN` only counts up, and the Python side
zeroes each lot **in place** rather than emptying `_adds`, because the ladder is capped on adds
BOUGHT. Freeing the slot would let a trade add again after banking — "scale in and out repeatedly",
which is a **different strategy** that nothing here has measured. There is a test pinning it.

⚠ **The comparator decodes an absent `cfg_scale_tp` as `"Ride"`, and that is the opposite of how the
four columns beside it are read.** "Absent ⇒ off" is safe for `cfg_scale_in` because that feature
shipped OFF. This one ships **active**, so falling back on the config default would replay every
pre-2026-08-19 export with its adds banking at a weekly level the exported Pine had no code to look
at — and the diff would blame the strategy for the harness's own configuration.

⚠ **UNGATED SO FAR.** `cfg_scale_tp` is new, so no export carries it yet and
`compare_strategy.py` has never checked this path. Rule 22 is not satisfied until a fresh export
lands with the column present and the gate passes on it.

### An add lot is now a TRADE-SHAPED record (2026-08-20)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *An add lot is now a TRADE-SHAPED record (2026-08-20)*.

🔴 **The lot's excursion is measured FROM THE LOT and is not the trade's.** An add is bought later
and further into the move, so it sits through a different part of it — on the fixture the base's
drawdown reaches 103.5 on its entry bar, which happened *before the lot existed*. Copying the
parent's numbers down would report the base's worst price as the add's, and the chart would draw a
`DD` line (the chart's adverse-extreme chip) at a price that lot never saw. MEASURED over 2018-09→2026-08: **110 of 112 lots have
an excursion that differs from their parent's.** The two that match are lots that happened to ride
the same extremes, not evidence of inheritance.

⚠ **Seeded ASYMMETRICALLY on the fill bar, the same rule `_try_entry_fill` follows.** A `Trail` add
is a market order at the bar's open, so the whole bar is genuinely the lot's. A `Limit` add is
reached by price coming to it from the wrong side, so that bar's *favourable* extreme is the
approach into the order — `_widen_add_excursions` skips the fill bar entirely for a limit lot, and
would otherwise hand every one of them a run it never made.

⚠ **`_adds` and `_add_lots` are INDEX-ALIGNED and that is now load-bearing.** The spent list says
which lots are live; the record list says what each did. `_bank_adds` zeroes in place rather than
popping, which is what keeps them aligned — a future edit that pops from either breaks the pairing
**silently and in reporting only**, which is the shape of defect nothing here fails on.

⚠ **`exit_price` is ABSENT, never `0.0`, on a lot nothing closed** — through `backtest/output.py`
and `chart_spec.py` alike. A defaulted zero reports a lot as having exited at price zero, with the
same confidence as a real measurement. Same rule as the bar cache's coverage and the terminal
probe: *never let "not measured" and "measured zero" be the same value.*

⚠ **There is no backfill and there cannot be one** — it would mean replaying the strategy. A run
stored before this carries the three original keys, and the chart's `Scale-in detail` row simply
does not appear for it.

🔴 **The parity gate is GREEN and CANNOT COVER THIS, and saying so is the point.**
`compare_strategy.py` diffs the **decision** stream; every field added here is reporting-only, so a
green run means *my edits to `_exit_portion` and `_bank_adds` did not disturb the decisions* — which
is worth having and is not the same claim. The claim that needed proving was proved directly
instead: full-history replays across four configs, fingerprinted on entry/exit/qty/price/R/costs,
**byte-identical to HEAD**. ⚠ Note the gate's own invocation is `--warmup 1000`; run without it and
it reports a mismatch at bar 16 that is engine cold-start and nothing else.

### 🔴 A TP RUNG WAS SLICING THE ADDS, AND `_finalise_trade` BINNED THE REST (fixed 2026-08-19)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 A TP RUNG WAS SLICING THE ADDS, AND `_finalise_trade` BINNED THE REST (fixed 2026-08-19)*.

✅ **Exactly two rows came back UNCHANGED, and they are the two that should have.** `0/0` never
slices (the runner closes 100% of the base, so the fraction was always 1.0) and `50/50` never
creates an add at all — the ladder fully closes the position before `_stage` reaches 2, which is
the gate `_maybe_scale_in` requires. Every row that could be wrong was, and no row that could not
be moved. That is the regression check on the fix, not just on the shipped default.

⚠ **`discarded` and `re-run` are two different measurements and only the second one counts.** The
discarded column valued each orphaned lot at the exit bar's CLOSE, while a trade ending on a stop
or a limit would have filled it at that price instead — so it SIZES the defect and does not
reconstruct the run. It is kept because the gap between the two columns is the point: adding it
back to `booked` predicted 172.17R at 25/0 where the re-run measures 174.62R. **A defect this
shape is re-measured, never corrected by arithmetic** — the missing P&L compounds, so it moves
every later trade's size, and win%, sd and drawdown cannot be reconstructed from an aggregate at
all.

⚠ **DIRECTION IS NOT FIXED, and the aggregate hides it.** Only **49 of the 112** dropped lots were
in profit — by COUNT most were underwater. The net came out positive because the winners are far
bigger, which is what lots added into a trend look like. On a single trade the bug can flatter just
as easily: the unit test's fixture drops a LOSING lot, so there the old code read 21,073 against a
true 11,257. **"It understates" was true of the eight-year total and of nothing smaller.**

🔴 **IT COULD NOT FIRE AT THE SHIPPED `0/0`, WHICH IS THE WHOLE REASON IT SURVIVED.** With both
rungs at zero the runner closes 100% of the base, so the pro-rata fraction was always 1.0 and the
two implementations agreed exactly. **The divergence existed only on settings nobody had ever
run** — rule 14, stated as plainly as this repo can state it: a green parity gate says the two
sides AGREE, never that either is RIGHT, and says nothing at all about a branch neither one
entered. ⚠ **The live bot was never exposed** (`exec_tp1_pct = exec_tp2_pct = 0`), and the fix is
byte-identical there: the `(0,0)` row reproduced at **194.15R / 7.24 R-dd / 3,510.4x** after it.

✅ **GATED 2026-08-19 on a purpose-made export, and the COVERAGE is the point rather than the
verdict.** `compare_strategy.py` GREEN on `engines/VANTAGE_XAUUSD, 15_4fef8.csv` (20,899 bars,
2025-10 → 2026-08, `--warmup 1000`) at **`cfg_tp1_pct=50, cfg_scale_in=1, cfg_scale_tp=0`** — Aaron
exported it specifically to reach this path.

🔴 **A GREEN GATE IS WORTH WHAT ITS COVERAGE IS WORTH, AND THAT WAS MEASURED HERE RATHER THAN
ASSUMED.** The run produced **25 trades, 24 add lots, and 11 exits that fired while an add was
live — all 11 closing exactly HALF the base (`frac = 0.5`)**, which is the pro-rata path itself.
Under the old code each of those 11 would have halved its add lots and binned the remainder. So
this run had **11 genuine chances to disagree** and took none.

⚠ **Contrast it with the run the day before**, which was equally GREEN on `49f80` and proved
nothing: that export carried `cfg_tp1_pct=0`, so the runner closed 100% of the base, the fraction
was always 1.0 and neither side ever entered the branch. **Same message, no information.** ⚠ **Do
not read "PARITY OK" as coverage — count the entries into the path you changed.** The probe is four
lines (wrap `_exit_portion`, count exits where `any(lot[1] > 0)` and `qty < _qty`); run it whenever
a gate is asked to vouch for a specific branch.

⚠ **The test is `test_a_tp_rung_does_not_slice_the_adds`, WATCHED RED by mutation** (restore the
pro-rata block → 121.4 vs 100.4 on P&L and on R). It carries no hand-computed constant: it runs the
same price path at `exec_tp1_pct` 0 and 50 where the rung banks at 105 and the stop sits at 105, so
the two runs ARE each other's expected value and only a sliced base can separate them.

### The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`, 2026-08-05)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`, 2026-08-05)*.

⚠ **Breakeven was the obvious alternative and it is INERT — measured, not assumed.** The entry is
a RESTING LIMIT, so price is sitting at the entry the moment it fills and the next bar's wick
crosses back over it: **161 of 161 trades touch breakeven, median 0.25h — one bar.** By hour 8 the
share of losers that have not returned to breakeven is **0%**. A breakeven-gated time stop fires on
nothing at any usable cutoff, and the sweep confirms it (0 trades cut at every H ≥ 8).

✅ **RE-RUN 2026-08-06 and this table is the corrected one.** It was measured twice over: once
before the one-bar force-close fix, and once before `eq_exempt_fvg` reached the Python side. Both
were real reasons to distrust it and **neither moved it** — every row shifted by ≤0.05R and the
trade counts, the cut counts and the plateau are unchanged. Recorded because "we re-measured and
nothing moved" is a result; a table nobody re-ran after two known-relevant fixes is not.

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

⚠ **A THIRD probe bug is worth recording, because it is this section's own lesson eating itself.**
The script that counts clock exits read `getattr(t, "exit_name", "")` — a field `Trade` does not
have — so it returned `0 closed BY THE CLOCK` for **every** export, including the one where the
clock fired 12 times. The field is `exit_reason`. **The exercise check written to catch
"green on a branch neither side entered" was itself silently answering zero**, and a zero from a
broken counter is indistinguishable from a zero from an unexercised branch. Read the field
directly so a rename raises; never `getattr` with a default in a check whose whole job is to
notice absence.

✅ **THE SWEEP WAS RE-RUN 2026-08-06 AND THE TIME-STOP TABLE IN THE BUILD NOTES IS THE CORRECTED ONE** — every row shifted by
≤0.05R, the trade counts and the plateau are unchanged. It had been stale twice over (the one-bar
force-close fix here, and `eq_exempt_fvg` reaching the Python side the same day) and neither moved
it. Quote the table freely now.

⚠ **Re-export at 4 hours after any change to this lever.** 36 is the shipped value and is
untestable on a normal chart; 4 is the same code path and exercises it dozens of times.

### ✅ CLOSED — the A+ parity failure was the EQ/FVG coupling, not the entry rule (2026-08-06)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *✅ CLOSED — the A+ parity failure was the EQ/FVG coupling, not the entry rule (2026-08-06)*.

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

### The Custom stop level (`exec_sl_custom`, 2026-08-02)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The Custom stop level (`exec_sl_custom`, 2026-08-02)*.

🔴 **Do not go SHALLOWER than 0.886.** A stop shallower than the fill either fails the
positive-distance test (order cancelled, no trade and no tag) or leaves a tiny distance, and the
position size balloons off it. Turn the minimum-stop guard on first.

⚠ **An out-of-range ratio RAISES at construction rather than falling back.** Falling through
would replay a whole backtest against a stop nobody chose and report it as theirs.

⚠ **NO PINE COUNTERPART, so a Custom run is unvalidated.** `mpc_strategy.pine`'s `execSlLevel` is an

### The deeper-entry test (`exec_ob_deepen`, 2026-08-09) — REFUTED, and the mechanism is geometry

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The deeper-entry test (`exec_ob_deepen`, 2026-08-09) — REFUTED, and the mechanism is geometry*.

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

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Bar-mode costs — commission and slippage, charged at last (2026-08-01)*.

⚠ ~~**Swap is NOT charged from the lab's fields.**~~ **Closed 2026-08-02 — see below.**

### Layered costs — spread and swap, and the one that moves trades (2026-08-02)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Layered costs — spread and swap, and the one that moves trades (2026-08-02)*.

🔴 **EVERY ROW OF THE COST TABLE IN THE BUILD NOTES IS PRICED ON VANTAGE, AND THE BOT TRADES PU PRIME — which costs 23% more.**
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
baseline here moves.** The tier RAISED before, so no cost table in the build notes ever charged an ECN spread, and
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
years). That is the same limit-order asymmetry the `bid_ask_fills` row in the build notes describes, read as a
decision rather than as a lab curiosity.

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

⚠ **Drawdown got WORSE while profit fell — 57.2% → 60.1%.** A cost does not merely shave the top
off the equity curve, it deepens every losing stretch, so profit and risk move in opposite
directions and both readings are correct. This is the companion to the compounding warning above:
that one says a small charge costs a large fraction of the FINAL BALANCE; this one says it also
costs you drawdown, which is the number a risk budget is actually set against.

⚠ **Trade count cannot move** under spread / commission / swap — they change what a trade was
worth, never whether it happened. Only `bid_ask_fills` moves the trade list. A re-priced run
showing the same trade count as its source is working correctly.

### 🔴 THE RE-ENTRY NOW SHIPS **OFF** (Aaron's call, 2026-08-21 — reverses 2026-08-07)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE RE-ENTRY NOW SHIPS **OFF** (Aaron's call, 2026-08-21 — reverses 2026-08-07)*.

⚠ **This MOVES every historical figure in this repo that was produced on the defaults**, exactly as
turning it on did in August. A number quoted from before this date may be a 235-trade book. Check
which before comparing anything to it.

⚠ **The once-per-setup CAP stays ON, deliberately.** It only means anything while the re-entry is
enabled, and anyone who switches the re-entry on should get the capped rule with it rather than the
uncapped book by accident. Turning a feature off is not a reason to unpin the rule that governs it.

⚠ **It cannot move `compare_strategy.py`, and that was VERIFIED rather than argued.** The re-entry
needs a fill-clock stream through `run_dual` while the gate replays the export's own single frame, so no
re-entry has ever fired inside it — exit 0 at warmups 100 / 500 / 1000 on
`VANTAGE_XAUUSD, 15_bfe65.csv`, before and after the flip.

⚠ **A pull does NOT move the live bot.** It imports from its frozen `deployed/` snapshot, so this
default reaches an armed bot only through `promote.py`. Until then the live bot keeps whatever it
was promoted with.

### A SHRUNK entry paid its costs on the size it ASKED for (fixed 2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *A SHRUNK entry paid its costs on the size it ASKED for (fixed 2026-08-21)*.

🔴 **The symptom was not a wrong dollar figure — it was the R INVARIANT disagreeing.** R's
denominator followed the shrink and one piece of its numerator did not, so a shrunk trade's R came
back BELOW the same trade run solo. That invariant is the shared account's own test for *"a sizing
change stayed a sizing change"*, and leaving this in place made it cry wolf on every shared run.
⚠ **The tool offers two explanations for a moved R — the cap bit, or a decision changed — and this
was a THIRD it had no name for.** The refusal log showed ZERO refusals, which is what pointed at it.

⚠ **Nothing already recorded moves**, and that was checked rather than assumed: `compare_strategy.py`
is **exit 0 at warmups 100 / 200 / 500 / 1000** on `VANTAGE_XAUUSD, 15_bfe65.csv` (21,052 bars,
2025-10-01 →). ⚠ **That export ran Require-FVG ON, so the no-gap fallback branch was never entered
and the green says nothing about it** — the standing rule that a gate speaks only about code both
sides executed.

⚠ **It is the ONLY charge site that used the requested size.** The TP rungs, the exits and the
scale-in adds all bill against the real position; checked, not assumed.

### Wrong-side stop fills — a KNOWN BACKTEST LIMITATION, not a bug (recorded 2026-08-01)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Wrong-side stop fills — a KNOWN BACKTEST LIMITATION, not a bug (recorded 2026-08-01)*.

**Deliberately NOT fixed: a "a stop may never be placed through the market" clamp.** It would have
caught the phantom-exit bug on day one, but applied now it would change real trade behaviour and
would have to land in all five Pine files too. That makes it its own change with its own
measurement, not a tidy-up. ⚠ It also matters for **live**: the bridge places the stop with the
broker, so a live fill will land nearer the stop than the backtest's. Expect live to beat the
backtest marginally on exactly these trades — and treat any BIGGER live/backtest gap as a real
problem, not as this.

## The 2026-07-26 exit-lever sync

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-26 exit-lever sync*.

⚠ **Not covered by this run:** it was taken before the minimum-stop guard was ported, at the `"Off"`

⚠ **NOT yet proven: the filter ON, against a real export.** Everything above is unit-tested and

✅ **MEASURED before it was written — two full replays, 186,366 M15 + 2,790,942 M1 bars, at the

🔴 **The honest size of the problem is ONE setup, and the first count of it was misread.** Over the

⚠ **So the case for this is CONSISTENCY, not the measurement.** The history contains no instance of

⚠ **The floor reads `self._atr`, which is the FIFTEEN-minute ATR(14)** — `_update_atr` runs in

✅ 5 new tests in `tests/test_secondary.py`, **3 watched RED** against the restored `dist > 0`. The

⚠ **The same pass found a test my own default flip had made vacuous the day before.**

## Deliberate deviations from the Pine (per the framework)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Deliberate deviations from the Pine (per the framework)*.

🔴 **PYTHON-ONLY FIELDS — THE GATE IS BLIND TO THESE, AND THERE ARE NOW TWO (audited 2026-08-12).** A field with no Pine input has no `cfg_*` column, so `compare_strategy.py` **can never configure a non-default run of it** — the green gate says nothing whatever about these branches. This is rule 14 with a specific shape: *a gate proves nothing about a branch neither side entered*, and here one side cannot enter it at all.
- **`exec_no_gap_arm`** — no `execNoGapArm` input exists in either A+ Pine. Any result measured with it moved was taken with one implementation only.
- **`exec_poi_source`** — `execPoiSource` appears in **zero** `.pine` files. The Pine POI seam was reverted (`indicators/CLAUDE.md` records it); the Python side was not reverted with it, so this field outlived its counterpart.

⚠ **Before trusting any A+ measurement, check whether it moved one of these two.** ⚠ **The fix is a decision, not a tidy-up:** either add the Pine inputs and re-export so the gate can see them, or drop the fields. Leaving them is the one option that keeps a live strategy carrying dials nothing verifies. Detail: `strategies/python/mpc_sos_fade/docs/SOS_FADE_BUILD_NOTES.md`.

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
   dollars predate the phantom-exit fix and the layered costs. The cost table in the build notes supersedes it.
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

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Engine-construction pins (`MpcSosFadeStrategy.engine_config`)*.

## The three parity fixes (2026-07-16) — read before touching signals/fib

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The three parity fixes (2026-07-16) — read before touching signals/fib*.

## The parity gate — `tools/compare_strategy.py` + `/audit-strategy`

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The parity gate — `tools/compare_strategy.py` + `/audit-strategy`*.

### The 2026-07-22 re-sync (the export was 7 days stale)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-22 re-sync (the export was 7 days stale)*.

## LOGIC parity vs RESULT parity — two different tools, two different questions

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *LOGIC parity vs RESULT parity — two different tools, two different questions*.

## The 2026-07-16 year run

⚠ **SUPERSEDED 2026-07-23.** Every figure in it was measured on the pre-combo baseline, so it
describes a bot that no longer exists — read it as history, never as a current number.
See `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-16 year run*.

## This bot's LOSSES are another package's population — `strategies/python/loss_recovery/`

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *This bot's LOSSES are another package's population — `strategies/python/loss_recovery/`*.

`loss_recovery` replays a **25%-size counter-trade after every A+ stop-out**. It is not a config
of this bot and changes nothing here — but its entire trade population is **this bot's 62 real
losses**, so it is coupled in one direction: ⚠ **any change to A+'s entry rule re-populates it and
every figure it has produced goes stale**, the same standing `overlap_audit.py` has. Re-run
`backtest/tools/recovery_report.py` after one.

## 🔴 The gate REFUSES an export from a chart faster than 15m (2026-08-23)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The gate REFUSES an export from a chart faster than 15m (2026-08-23)*.

⚠ **MEASURED, because "it would differ a bit" was not good enough:** on a 20,574-bar M5
export, **13,759 of 20,477 compared bars diverge as shipped and 0 diverge with the sub-15m
pair.** `px_edge` on 13,401 of them. The whole file was noise about the chart's timeframe.

🔴 **It REFUSES rather than warning, and that is the point.** The run above did not look
like a configuration problem — it looked like a broken entry rule, at a named bar, with a
price on each side. That is the shape of a real defect, and it sends the next reader into
the strategy. **Never let *cannot compare* and *compared and disagreed* be the same
outcome** — the same rule as the terminal that answered "quiet market" when it was dead.

⚠ **The spacing is read as the SMALLEST gap between rows**, matching how the bot infers its
own bar duration. A real export has weekends in it, and a reading that lets a session break
raise the apparent timeframe would walk a fast chart straight past this check.

⚠ **`--allow-fast-timeframe` exists on purpose.** The pins CAN be changed; a wall with no
door gets routed around in ways that leave no trace, which is strictly worse.

⚠ **It is a floor, not an equality** — H1 and H4 exports are legitimate, because the Pine
runs the same two values everywhere at or above 15m.

**Tests:** 5 in `tests/test_compare_strategy.py`, each watched RED by mutation. 🔴 **One of
them was WRONG on its first pass and is kept as the record**: it claimed a median reading
would break on a weekend gap, and it passed against that mutation, because weekends are a
minority of the gaps. **A test whose mutation passes is not evidence — it is a second
opinion from the same mistake.** It is written against the reading that genuinely fails.

## Tests

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Tests*.

## The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)*.

## `Trade.tp_rungs` — the closed record says how much each rung TAKES OFF (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *`Trade.tp_rungs` — the closed record says how much each rung TAKES OFF (2026-08-21)*.

⚠ **The percentage is resolved for the trade that was actually OPEN, not read off the config.**
A re-entry may bank its own (`exec_sec_tp1_pct`, 50 by default) and the reclaim half a different
one again (`exec_rec_tp1_pct`, 100), so it goes through `_tp1_pct()` exactly as the live ladder
does. Reading `cfg.exec_tp1_pct` here would report a primary's percentage for every re-entry.

⚠ **REPORTING ONLY**, the same standing as `mfe_usd` / `tp1` / `tp2` / `fib` — nothing reads it
back, so no decision can move and `compare_strategy.py` diffs the same `px_*` stream.

🔴 **A re-entry's rungs are NOT in distance order, and that is worth knowing beyond the chart.**
Rung 1 is priced off risk (`exec_sec_tp_r`, 1.25R below a short's entry) while rung 2 stays the 15m
fib it was armed on, so **rung 2 can be the NEARER of the two — 23 of the 45 re-entries on run
`687c8df2a523`. The 160 main entries are all correctly ordered, and the Pine's own ladder
(0.5 then 0.382) is too — the flip is created by this Python-only risk-multiple override and
exists nowhere in `mpc_strategy.pine`.** ⚠ **A first count published as 182 of 205 was WRONG**
and made this look repo-wide; it measured *nearer* with the sign inverted (corrected
2026-08-21). Distance is measured FROM the entry in the FAVOURABLE direction — on a short the
nearer target is the HIGHER price — and a bare price comparison is backwards on one side.

🔴 **IT WAS FLIPPED, MEASURED, AND REVERTED. DO NOT FLIP IT — IT COSTS MONEY, AND THE READING THAT
SAYS OTHERWISE IS THE INTUITIVE ONE.** MEASURED 2026-08-21 via `run_report`, XAUUSD M15
2018-09-14 → 2026-08-20, matched basis, only the stage ordering differing:

**−4.43R over 7.9 years, and nine winners became scratches.** ⚠ **The reason is that a TRAIL is
STRONGER protection than breakeven, not weaker.** On a flipped trade the first rung price reaches
already arms the trail, which is better than arming plain breakeven — so the "fix" REPLACES the
trail with breakeven at the near price and DELAYS the trail to the far one. Trades that were
banking 0.8–1.2R came off at 0.02–0.06R instead.

⚠ **"It skips the breakeven step" therefore describes something GOOD, and reading it as a defect
is what motivated the flip.** The naming is what is backwards, not the behaviour: the step called
"1" waits on the far price and the step called "2" on the near one, so the bot reaches the better
one first. Aaron's call, 2026-08-21: leave it.

✅ **The question the reordering was mistaken for — arming breakeven EARLIER THAN EITHER RUNG —
has now been MEASURED, and the answer is DON'T (2026-08-25).** `exec_be_arm_r` /
`exec_be_keep_r` generalise the reclaim's arm to every trade: the stop moves once price has gone a
multiple of the trade's own entry risk its way, with no rung touched. Both ship **OFF** and the
`warn` on each says why.

🔴 **Every setting tested LOST money, and the decomposition is the rule, not the totals.** Over
6.6 years on 246 trades (control `32f82feae4ee`, 139.09R): **99.92R** at 1.00R→breakeven,
**71.20R** at 0.75R, **51.55R** at 0.50R; keeping half the risk instead is the least bad and still
loses — **118.99R** at 1.00R, **108.12R** at 0.75R. At 1.00R→breakeven it rescued 17 trades worth
**+17.07R** and destroyed 15 worth **−54.49R**, one of them a **+16.48R** winner cut to +0.35R.

🔴 **The give-back and the outsized winners are the SAME EVENT** — this book is carried by trades
that run, pull back hard THROUGH the entry, and only then go, so any rule that refuses to sit
through the pullback kills those trades first, at about three R destroyed per R rescued.

⚠ **A rising win rate is NOT evidence here**: it went 58.1% → 68.7% at the earliest arm while the
money fell by two thirds. ⚠ **Protection did not reliably buy drawdown either** — keeping half the
risk at 0.75R made the worst drawdown WORSE (60.21% against 53.68%).

⚠ **The defect it was built for is real and is still open**: the stop's ONLY trigger is a rung
TOUCH, so a trade can run a full R in profit and have nothing happen. The 2020-11-04 re-entry did
exactly that (best price 1.016R, nearest rung 1.25R, full loss) and survived in the shipped
configuration only because the flipped ladder put a rung at 0.757R. **A ladder defect was
load-bearing for a stop with no other trigger.**

## Every entry method OWNS its stop rule — the precedence list is gone (2026-08-27)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Every entry method OWNS its stop rule — the precedence list is gone (2026-08-27)*.

🔴 **MEASURED with `stopwalk.py` on 2026-08-26.** Entry 100.00, stop 98.00, general rule arming at
1R and keeping half. At 2.25R in front the stop was 99.00; at 2.50R it went back out to 98.50.
**A protective stop that RETREATS on a winning trade** — the trade got better and its stop got
worse, putting 0.50 back at risk on a position that had already been made safe. It retreated at
every arm later than 1R (0.10 / 0.50 / 0.90 at keeps of 0.55 / 0.75 / 0.95).

⚠ **A second retreat existed one branch up and is closed in the same change**: a re-entry set to
hold its initial stop until the second target returned the FROZEN entry stop the moment the first
rung was touched — wider than whatever its own protection rule had already set.

⚠ **The rule is not switchable — its VALUE is.** `-1` does not mean "this method has no rule"; it
means "this method's rule is *never move the stop*". Switching an entry method on brings its exit
rules with it and they cannot be detached. That is the model, and it is why there is no "inherit
the shared one" value on any of the four.

✅ **PROVEN A NO-OP AT SHIPPED SETTINGS, trade by trade.** All four pairs ship at `-1` / `0.0`, so
nothing can arm. HEAD (`ecdbd9b1`) and this change were replayed on identical bars, window and
params (XAUUSD.p, 2020-01-01 → 2026-08-23, reclaim trigger, 3.25R target): **200 trades and
141.6497R on both, and zero trades differ.** Same 44 re-entries at 32.50R.

✅ **And proven to CHANGE the thing it was meant to change.** With the old collision switched on
(general 1.0R/keep 0.5, reclaim 2.5R/keep 0.75) the same replay differs on **12 trades**: eleven
reclaims that the primary's rule used to reach now take their own method's rule instead, and one
of them goes −0.5R → **+3.25R** because the borrowed stop had been knocking it out.

⚠ **`_rec_be_armed` is now written but never READ.** It is kept only so a live bot rolled BACK onto
the previous deployment can still restore this version's position record — `restore_position()`
refuses a record with a missing field, and `promote.py` refuses a version that cannot restore the
open position. It is set only on a reclaim, so the older code computes the same stop from it.

⚠ **An UNNAMED re-entry gets no stop movement, and that is a decision rather than a fallthrough.**
Reinstating the primary's pair for the one case the map does not cover would put the precedence
question straight back. It can only ever leave the frozen entry stop in place, never widen one that
has already moved. In production every armed re-entry carries a source (`secondary.py::_src_for`);
the unnamed case is duck-typed test stand-ins.

⚠ **The two new pairs have NEVER been MEASURED ON.** No replay has been run with either positive,
and this file's own numbers above are the reason to distrust the intuition: every protective
setting tested on the primary LOST money, at about three R destroyed per R rescued.

⚠ **Parity is unaffected while they ship off** — nothing can arm, so `compare_strategy.py` sees the
decisions it always did. The moment any of the four goes positive, Python and Pine are trading
different ladders: there is no TradingView side for any of them.

## The re-entry rests its order and LEAVES it — and what the 1m feed is actually for (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The re-entry rests its order and LEAVES it — and what the 1m feed is actually for (2026-08-21)*.

🔴 **THE RE-DECIDING WAS WORTH 0.02R OVER 7.9 YEARS, AND IT WAS THE ONLY REASON THE ORDER HAD TO BE
RE-ASKED EVERY MINUTE.** MEASURED, matched basis, the only difference in each pair being the switch:

⚠ **The ~11R between the two ROWS is a DIFFERENT thing and is not this switch.** It is fill
PRECISION — a 15m bar fills a resting limit at a worse price than the minute price actually traded
at. **That is a measurement-accuracy question, not a strategy one: live, the broker fills the order
at the price that trades and there is no 15-minute anything.** Read the 15m row as a pessimistic
simulation of the same live behaviour, never as a different rule.

✅ **5 MINUTES IS THE PLACE TO BACKTEST.** Same window, same config, only the fill clock:

⚠ **It freezes the PRICES, not just the armed flag.** The fibs keep extending, so a re-read edge
would slide a still-resting order to a level it was never placed at and the trade's record would
name a price that was never live.

🔴 **THE SNAPSHOT IS CLEARED WHERE A LEG RETIRES (`mark_traded` / `mark_dead`), NOT BY THE READER.**
The first version tried to infer both inside `_rested` by comparing the 15m SOS bar against
`_l_traded` — and those are different keys, because `_traded` holds the LEG id, which under the 1m
trigger is a 1-minute SOS bar and never equals the 15m one. It left a filled order resting and let
a second re-entry straight through the one-per-setup cap. **Three existing tests caught it, which
is the whole argument for a cap having its own tests rather than being 'obviously' enforced.**

⚠ **NOT byte-identical to the old path** — 2 re-entries move and 1 is lost over 7.9 years, so a
stored figure from before this date reproduces only with the switch set False.

## The re-entry's FILL CLOCK is 5 minutes, and it is an accuracy knob (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The re-entry's FILL CLOCK is 5 minutes, and it is an accuracy knob (2026-08-21)*.

🔴 **IT IS A MEASUREMENT-ACCURACY KNOB, NOT A STRATEGY ONE.** Live, the broker fills a resting
limit at the price that trades — there is no 15-minute anything. A coarser feed fills the order at
a worse price than really traded, so it UNDERSTATES, which is the safe direction. **Never read the
5m default as "the strategy trades on 5m"**: the setup, the entry price and the stop are all 15m.

⚠ **A finer feed also bounds the WINDOW by its own measured history floor**, so 1m is not free
even on a machine that can afford the bars — it costs a day here, and more on a symbol whose 1m
history is shallower.

⚠ **A strategy that does not declare one keeps the old 1m behaviour.** `run_report` reads
`getattr(cfg, "exec_sec_fill_tf_min", 1)` — absent means "this fork has not been measured", not
"coarsen it".

## What the 1-minute STRUCTURE engine contributes at the shipped trigger (2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *What the 1-minute STRUCTURE engine contributes at the shipped trigger (2026-08-21)*.

⚠ **It is NOT inert, and the difference matters.** Its SOS latch still writes `_l_leg` / `_s_leg`,
which is the key `_traded` / `_dead` / `_used` read — so it can still move which setup counts as
already-used. `secondary.py` records a control replay where keying the price rule off the latch
instead of the trigger priced a gap book at a 1-minute retrace, +4 re-entries and +4.9R.

⚠ **Read from the CODE, not from a replay.** Nobody has run the book with the 1m structure engine
suppressed, so "it contributes nothing but bookkeeping" is a reading of the source and not a
measurement. Say which it is before quoting it.

⚠ **Aaron's description of the shipped rule is the right one and the module's own docstring is
stale**: it opens *"1m sniper re-entry … a 1m shift of structure rests a tight limit at a 38.2%
retrace of that 1m leg"*, which describes `"1m shift"` — a trigger that is no longer the default.
The shipped rule is: the first trade reaches breakeven, price comes back into the zone, a fair
value gap is there, and the entry follows the PRIMARY's model around that gap.

## 🔴 The worst price a trade reports is bounded by its STOP — `_widen_hold` (2026-08-22)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The worst price a trade reports is bounded by its STOP — `_widen_hold` (2026-08-22)*.

⚠ **It is not an intrabar-ordering guess.** The stop is triggered BY the adverse move, so any
price past the stop necessarily came at or after the fill. Determinate, which is what makes this
fixable at all.

⚠ **The remaining 4 are the ENTRY BAR and are correct.** The stop is not managed until the next
bar — the one-bar order delay every fill model here is built on — so a first-bar excursion past the
stop is real exposure the trade genuinely sat through. Bounding it would report a better worst
price than the trade actually had, which is a lie in the flattering direction.

⚠ **A bar that OPENS past the stop is bounded by the OPEN, not the stop**, because that is where
the stop fills (`_fill_price`) and that fill is real.

⚠ **The FAVOURABLE side is deliberately untouched.** A target is partial — TP1 banks a portion and
the runner stays open — so price past a target is still the trade's move. Only the stop closes
everything.

⚠ **Reporting only, and proven rather than argued.** No decision reads the excursion, so parity
could not move; the gate was run anyway, on three exports, because that is the rule.

## The SHORT-HOLD variant — `exec_short_hold` (2026-08-24, ships OFF)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The SHORT-HOLD variant — `exec_short_hold` (2026-08-24, ships OFF)*.

🔴 **IT IS A SWITCH TO EXPERIMENT WITH, NOT A LEG TO DEPLOY, and the numbers are why.** On the
pool it was built for (order blocks where no gap qualified), matched basis, ECN costs:

**It does exactly what it was designed to do and still earns less.** The scratch problem it was
built to fix is fixed — 33 → 1 — and the drawdown improves; the total halves, because capping a
trade at 2R throws away the tail that was carrying the pool. ⚠ It is also still negative in 2020,
2024 and 2026, the same decay the pool has without it.

🔴 **THE DEPTH CAP SHIPS INERT BECAUSE IT MEASURED NEGATIVE, AND THAT REVERSED THE
RECOMMENDATION THE FIELD WAS BUILT ON.** Entry depth was the strongest split found anywhere in
this work and it replicated three independent ways, including in this bot's own shipped book. Then
it was applied: capping at 0.702 removed 5 trades, 2.1R and made the drawdown slightly worse.
**The split was measured under the fib ladder and the cap was applied under a fixed R target** —
a deep entry has a short stop and the breakeven ratchet takes it out, which stops mattering once
the trade closes at 2R. ⚠ **A finding is scoped to the exit regime it was measured in; carrying
it across an exit change is a new claim and needs its own run.** Nothing was wrong when it was
measured, it was generalised one step too far.

⚠ **Two new BLOCK codes (8, 9) have no Pine counterpart.** `f_blkCode` stops at 7. They are
appended so every existing code keeps its number, they can only fire with the toggle on, and
`BlockedSetup` is reporting-only — which is what makes a new code parity-safe rather than merely
convenient.

⚠ **The variant's hour window is its OWN gate, deliberately not more hours folded into the
final-hour rule.** That rule's label is rendered by the block marker and the Telegram callout as
*"no new entries 16:00-18:00 New York"*, and widening it would leave both of them saying 16:00
about a setup refused at 10:00.

✅ **THE PINE PARITY GATE HAS RUN AND IS GREEN (2026-08-24).** `compare_strategy.py` on
`VANTAGE_XAUUSD, 15_80a5f.csv` — 21,162 bars, 2025-10-01 → 2026-08-24, shipped config
(`cfg_bits` 544375) — **exit 0 at warmups 100 / 500 / 1000 / 2000.** Rule 22 is satisfied for
this change: the Python makes the identical decision to the Pine on every bar.

⚠ **Read what that green run covers, and what it cannot.** It proves parity of the SHIPPED path,
which is the claim that matters here — the variant is off, so the Pine and the Python are running
the same strategy and agree bar for bar. It says nothing about the variant itself, and **no export
ever can**: the Pine has no counterpart to these three rules, so there is nothing on the other side
to diff against. That is a stronger version of the gate's own standing warning about the no-gap
arm gate, which this run also reported as un-exercised. **A green gate is evidence about the
branch it entered and about no other.**

⚠ **Without `--warmup` the gate reports a mismatch at bar 16** (`px_s_stage` py=1 pine=0). That is
engine cold-start and is already recorded further down this file — it is not this change, and it
reproduces on HEAD.

⚠ **All six settings carry a label and a description in `mpc_sos_fade.meta.json`**, which is what
puts them on the Command Center's parameter form — a toggle nobody can find is not a toggle. That
file is a CONTRACT the lab reads, not data, and a backend test refuses any tunable parameter with
no description, which is what caught them missing. ⚠ **Position in its `params` array is the order
the form renders in, so APPEND — never re-sort.** Sorting it once here silently reordered all 93
existing settings, and the diff was 1,671 lines that should have been 73.

## Do / Never

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Do / Never*.

## References

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *References*.

## 🔴 THE RE-ENTRY LADDER COMES OUT BACKWARDS ON ONE HALF, AND THE FLIP IS PROTECTIVE (2026-08-25)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE RE-ENTRY LADDER COMES OUT BACKWARDS ON ONE HALF, AND THE FLIP IS PROTECTIVE (2026-08-25)*.

🔴 **THE FLIP IS NOT A BEHAVIOUR BUG. IT IS A LABELLING ONE, AND "FIXING" IT COSTS REAL MONEY.**
`_stage_rungs()` already sorts the stop ladder by DISTANCE, so on a flipped trade the nearer rung —
the fib, labelled `TP2` — is what arms BREAKEVEN, and the further one still banks
`exec_sec_tp1_pct`. That is a good ladder: protect early, bank later. Push the second rung away and
you delete the early breakeven trigger. **MEASURED on the re-entry short of 2020-11-04** (entry
1902.97, stop 1912.55354, TP1 1890.99058, TP2 1895.72498, best price 1893.23): price cleared TP2 and
never reached TP1, the stop staged to 1899.61576 and took it for **+0.348R**. With the second rung
floored at 1.5× it moved to 1885.00086, nothing was touched, the stop never staged, and the same
trade ran back to 1912.55354 for **−0.907R**.

⚠ **So `exec_sec_tp2_min_x` exists, is MEASURED, and ships OFF.** Four floors were swept against a
matched control on the basis above. Total R 139.09 (off) / 140.64 / 140.29 / 139.79 / 137.10 at
1.5× / 2× / 2.5× / 3×; the re-entry leg alone improves at every floor and the improvement survives
removing its single best trade. ⚠ **Read none of that as an edge: only 13 of 246 trades changed and
they swung about ±1R each** — the +1.55R is thirteen coin flips. The one durable read is drawdown,
53.68% → 49.02% at 1.5×. ⚠ **3× is not a clean comparison at all** — it drops the book to 237
trades, so it changed which setups were TAKEN.

⚠ **If the naming is to be fixed, sort the LABELS and leave both prices alone.** Everything the
stop ladder does is already distance-ordered; only the chip is out of order.

### The second rung as a CHOSEN distance, not leftover geometry (2026-08-25)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The second rung as a CHOSEN distance, not leftover geometry (2026-08-25)*.

✅ **`exec_sec_tp2_x` REPLACES it with a chosen multiple of the first rung, so the two are ordered
by construction.** ⚠ **It is not the floor above renamed — the difference is DIRECTION.** A floor
lets a distant fib stand and can only push a rung away; this overrides both ways, so it also pulls
IN the rung that ran to 3.66×. Applied BEFORE the floor, so with both on they compose.

⚠ **SHIPS OFF, and the standing rules from its sweep are these three.** ① **The money is noise and
the drawdown is not** — best arm (1.25×) is 142.87R against 139.09R, which is 15 trades swinging ±1R
each, while max drawdown fell at EVERY arm monotonically as the multiple tightened, 53.68% → 47.95%.
Treat it as a drawdown lever, never as a way to make more money. ② **Any arm at 3× or beyond is a
DIFFERENT BOOK, not a comparison** — a re-entry then holds long enough to block the setups behind it
and the trade count drops to 237 and 235; with one position slot an extra hold does not add to the
book, it queues in front of it. ③ 🔴 **Ordering the ladder DELETES the only breakeven trigger some
re-entries have.** 2020-11-04 goes +0.348R → −0.907R at every setting tested, with 2021-02-11 and
2020-12-28 doing the same. **Ordering the targets and protecting those trades are opposing goals**,
and the cheap way to have both is still the one named above: sort the chart LABELS, leave the prices
alone.

🔴 **ONE SWEEP ARM SILENTLY REPLAYED STALE CODE.** The 2.5× arm ran 170s, stored its parameter, and
produced a ladder byte-identical to the control; an identical re-request came out correct. The lab
purges cached strategy modules under one namespace only, and `mpc_bleg` imports this package's
files under their BARE names, which are never purged. **Verify a swept parameter by reading the
stored TRADES, never the KPI row** — the KPI row of a stale replay looks entirely normal.

## 🔴 THE TWO RE-ENTRY HALVES ARE TWO FEATURES, AND ONLY ONE OF THEM EARNS (2026-08-23)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE TWO RE-ENTRY HALVES ARE TWO FEATURES, AND ONLY ONE OF THEM EARNS (2026-08-23)*.

✅ **THE THREE ARE EXACTLY ADDITIVE, AND THAT IS THE STRUCTURAL FINDING.** 139.71 + 30.00 =
169.71; + 8.19 = 177.89. The 159 A+ trades are **identical in all three** — same entry times,
same fills, same R, checked trade by trade. **Neither half displaces an A+ setup or interferes
with the other**, so each is a genuinely independent switch. ⚠ That is a fact about THIS config,
not a property of the design — one position slot means displacement is always possible. **Re-run
the three-way before trusting it after any entry-logic change.**

🔴 **The gap half is one trade away from losing money over six and a half years.** 44 trades,
+8.19R, average +0.186R — and **dropping its single best result leaves −1.92R over 43 trades.**
Its own worst run of losses is **−7.75R, deeper than the whole strategy's −6.41R.** The reclaim
half is the opposite shape: 46 trades, +30.00R, a clean binary of −1R or +3R (19 wins, 27
losses), carried by no single trade.

⚠ **"Adds R" was never the question.** Both halves add R. The gap half adds 8.19R of which none
is repeatable, for 44 extra trades and 0.28R of extra drawdown. **Split a multi-trigger feature
into its triggers and drop the best trade from each — a leg carried by one outlier is a finding,
not a strategy.**

⚠ **It did NOT smooth the drawdown, and the account-drop column is why that reads backwards.**
The worst stretch (2022-01-26 → 2022-11-14) has A+ down 4.13R and the re-entries down another
1.68R on top, with **five occasions where the re-entry lost immediately after the A+ it followed
lost.** In bad conditions the two are ONE position at 1.5× the size — 10% plus 5% on the same
failing setup. The account drop improves 45.6% → 43.3% only because the extra profit compounds
the balance; that is sequencing, never safety. **Read the R drawdown, which got 0.8R worse.**

⚠ **Sample-size caveat, and it cuts against over-reading this too:** 44 trades is thin. The
honest verdict on the gap half is *"it has not shown an edge over this window"*, never *"it does
not work"*.

## Where the reclaim banks: 3.0R → 3.25R, and the 0.25R that costs nothing (2026-08-27)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Where the reclaim banks: 3.0R → 3.25R, and the 0.25R that costs nothing (2026-08-27)*.

✅ **The move from 3.00R to 3.25R changed NO trade's outcome.** Same 18 winners, same 29 losers —
every winner that reached 3.00R also reached 3.25R and simply carried 0.25R further. **The +4.50R
is not bought from anywhere**, which is what separates this from a tuning nudge that traded one
population of trades for another.

⚠ **THE TARGET TABLE (NOW IN THE BUILD NOTES) WAS MEASURED ON A FROZEN CHECKOUT AND TODAY'S TREE GIVES A DIFFERENT BOOK.**
Work landed on this strategy between the sweep and the default change, and on current code the
same window gives **44 reclaims, not 47**. Do not expect to reproduce 29.50R by replaying today —
quote the table as what it is, a ranking measured on one pinned checkout.

✅ **RE-CONFIRMED ON CURRENT CODE (2026-08-27), with the target resolved from the SETTING rather
than pinned in the run's params:** 3.00R gives 44 reclaims / **28.00R** / 18 winners, and 3.25R
gives 44 reclaims / **32.50R** / 18 winners. **The same 44 trades, the same 18 winners, and zero
outcomes flipped** — 18 × 0.25R = exactly the +4.50R observed. Different absolute numbers, same
structure, same conclusion.

🔴 **THE FIRST ATTEMPT AT THAT CHECK WAS VACUOUS AND PASSED ANYWAY, WHICH IS THE LESSON WORTH
KEEPING.** It replayed a params file that PINNED the target, so both sides read the pinned value
and the default under test was never consulted. Both runs came back byte-identical, and identical
is exactly what a working no-op looks like — **the check could not tell "took effect" from "was
overridden".** To test a DEFAULT, the key has to be ABSENT from the params, not set to the value
you are hoping for. This is the same shape as the lab's basis trap: a request-time value that
overwrites the thing you meant to measure.

🔴 **3.50R ties it at 29.50R and was NOT chosen.** It has one fewer winner, and it sits one 0.25R
step from a cliff where four winners vanish and the leg halves. 3.25R keeps twice that margin for
identical money. ⚠ **The cliff rests on four trades, so its exact position is soft — that it
exists is not**: 3.75R and 4.00R are both down there.

⚠ **This is the OTHER half of the same question the de-risking grid answered**, and the two
answers point the same way: this leg is carried by trades that run, so anything that shortens
them — a nearer target, a tightened stop — costs more than it saves. See *Every entry method owns
its stop rule* above for the stop half.

⚠ **The default is all that moved. The re-entry itself still ships OFF** (Aaron's call,
2026-08-27) and the shipped trigger is still the gap, so no shipped run changes.
🔴 **The live bot PINS the old 3.0 in its own instance config** — `algos/markets/fx/instances/
mpc_sos_fade_demo/config.json` — so it will NOT pick this up. It is inert there today because
that bot's re-entry fires off the gap, but the moment anyone switches the reclaim on live, the
pinned 3.0 silently wins over this default. **Change it there too, or the measurement never
reaches the bot.**

⚠ **Every losing reclaim in all nine runs came back at exactly −1.0R** (one exception at 4.00R).
The leg is binary, which is what lets each row's total be reconciled from its win count alone —
all nine do, to the cent. That is an independent check on the table rather than a restatement of
it.

## 🔴 THE RECLAIM'S GIVE-BACK — FIVE FIXES REPLAYED, FOUR LOSE, AND THE EXCHANGE RATE SAYS WHY (2026-08-24)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 THE RECLAIM'S GIVE-BACK — FIVE FIXES REPLAYED, FOUR LOSE, AND THE EXCHANGE RATE SAYS WHY (2026-08-24)*.

🔴 **THE RULE, AND IT GENERALISES TO ANY ALL-OR-NOTHING LEG: WORK OUT THE EXCHANGE RATE BEFORE
BUILDING THE FIX.** A winner here pays 3R and a loser pays 1R, so protecting a loser saves at most
1R while knocking out one winner costs 3R plus what it then loses. **Nothing that touches the stop
or the entry clears one winner per three-to-four saves.** Four separate ideas were built, tested
and replayed before that arithmetic was written down; it would have predicted all four.

⚠ **A WORSE ENTRY IS A WIDER STOP AND A TARGET FURTHER AWAY IN PRICE, because the stop does not
move with it.** Market entry got 2025-08-19 in **12h45m earlier** — exactly what was asked for —
and the risk went **$3.98 → $12.51** with the target moving **3339.42 → 3373.55**. Price topped at
3345.25: **in the move ten hours before the high, and further from the target than before.** The
reclaim's edge IS its tight geometry, so paying up for the entry removes the thing being traded.

⚠ **The one that pays does so by REMOVING trades, not by trading them better.** 8 orders in 6.6
years waited over 12 hours to fill and every one lost; cancelling them is **pure subtraction, with
ZERO new trades appearing in any run** — the freed position slot never let anything in, so there
is no displacement term and the 8.00R is exact. ⚠ **Every cutoff of 6 hours or less LOSES**: the
6–12h band is the best in the whole re-entry book (4 wins from 5). Cutting early is the opposite
trade, not a milder one. ⚠ **It rests on 8 trades** — roughly a 1-in-250 fluke if the pattern is
not real — and is worth ~1.5R a year.

⚠ **A SMALLER LOSING TICKET IS NOT A SAFER ACCOUNT, and this run is the proof.** Account drawdown
is **43.34% in six of the seven** stop-protection runs, i.e. unchanged, because the drawdown is
driven by the A+ book. Halving the re-entry loss moves the number on the ticket and nothing else.

**Three settings landed, all defaulting to the shipped behaviour and all OFF:** the protected-stop
trigger, how far that stop moves, and the resting-order cancel. **Only the cancel is recommended,
at 144 fill-clock bars = 12 hours.** ⚠ **Risk percent was ruled out early — it is a SIZE dial**, so
it changes dollars and account drawdown, never R and never which trades happen.

⚠ **This is the one question that could NOT be answered from stored runs**: a run records when an
order FILLED and never when it was PLACED. Reconstructing the wait by pairing each secondary with
the preceding primary matched on only 32 of 90 exit prices and was discarded before it was quoted.
**Re-run the sweep rather than mining a stored run for it.**

## 🔴 The minimum stop distance permits a stop a normal gap can double (2026-08-23)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The minimum stop distance permits a stop a normal gap can double (2026-08-23)*.

⚠ **That is the documented one-bar order delay doing exactly what it is supposed to do** — see
*Wrong-side stop fills* — and it is the SAFE direction for a backtest. **The finding is not the
fill, it is the floor that let the stop be that tight.** The run's minimum stop distance was
0.08% of price; the stop cleared it by six thousandths of a percent, and one ordinary gold gap
then cost twice the risk the position was sized for.

⚠ **Sizing is computed off the stop distance, so a tighter stop buys a BIGGER position.** The
floor is the only thing standing between a near-zero stop distance and an enormous one, and a
floor set just under what the market gaps in a bar is a floor that is not doing its job. ⚠ **One
trade in 249 is not a reason to move it** — it is a reason to measure the floor against the
instrument's typical bar gap rather than picking a round number.

## Loss recovery — the toggle, and the one property it must never break

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Loss recovery — the toggle, and the one property it must never break*.

🔴 **Turning it on cannot move one A+ trade, and a test pins that.** The recovery reads A+'s
finished losses and appends rows tagged `kind="recovery"`; it never gates, delays or re-sizes an
A+ entry. That is what makes it safe to ship a lab-only toggle on the LIVE bot's config class — a
feature that could rewrite the shipped book would put every parity number and every figure in
`mpc_sos_fade_optimization.md` at the mercy of a switch. `test_turning_it_on_cannot_move_one_aplus_trade`
is the one to keep green; it was watched red by having `apply` re-size a source trade.

🔴 **The cost of that choice was called "slight" here until it was measured, and it is most of
the result (2026-08-20, run `236e206d0142`).** The recovery sizes off the RUNNING balance (every
A+ and earlier recovery trade already closed is in it); A+ does not size off the recovery. **They
share a balance in ONE direction only**, so recovery profit sits BESIDE the curve instead of
lifting it and never compounds. Identical trades, added up two ways: **+3.8% as the lab runs it
against +59.9% on one shared compounding balance.** ⚠ **Neither is this rule's worth.** The
larger figure also assumes one balance with NO risk budget on it; at the 10% account cap this bot
already runs, 23 of that run's 160 A+ entries opened while a recovery was still holding risk and
the leg turns NEGATIVE. **The honest range is +45% to −15%, decided by an allocator that does not
exist on the live side.** Full bracket: `strategies/python/loss_recovery/CLAUDE.md` → *Put ONE RISK
BUDGET on that balance*. It is NOT a shared-account run — `backtest/portfolio/`
is what one of those looks like.

🔴 **`finalize(df)` is a hook three separate drivers have to call, and a missed one is silent.**
`run()` and `run_dual()` call it. Anything that steps bars itself must too: the lab's
`python_runner._replay` and `backtest/optimizer.py::_replay_one` both reproduce the bar loop rather
than calling `run()`, so neither inherits it. A driver that forgets does not error — it reports a
book with the recovery trades missing, which is rule 7 exactly (the toggle is a CLAIM about code
somewhere else). Idempotent via a `_recovery_applied` flag on the strategy.

⚠ **Idempotence is a FLAG, not "are there recovery rows in the book".** Inferring it from the rows
made the `kind != "recovery"` source filter unreachable — a book carrying one returned before that
line, so no test could redden it. Dead code that reads as load-bearing is worse than none.

⚠ **`r` on a recovery Trade is that trade's own R**, so `pnl_usd / risk_usd` reproduces it exactly
as on every other row. The quarter-sizing is carried in the DOLLARS (`risk_usd` is a quarter of a
normal trade's), which is what makes the equity curve right without giving one row's R a different
meaning from its neighbour's. Do not "fix" this to `scaled_r`.

🔴 **A recovery row carries its EXCURSION, and it had to be added — the chart was drawing these
as bare rectangles (2026-08-20).** Every reporting field a chart reads is optional by design, so a
trade that carries none degrades to a plain entry→exit box; that fallback exists for an NT8/MT5
trade with no fill prices in it at all. The first version of this adapter left `mfe_price` and
`mae_price` at their `0.0` defaults, so **every recovery trade took that path** and appeared beside
a normal loser — which was wearing entry, stop, both excursion bands and its outcome chip — as a
featureless green block. **It read as a different KIND of trade and it was the same kind of trade
with a thinner record.** The general rule, and it is the one this repo keeps relearning from the
other direction: **an absence rendered as a distinct shape becomes a claim.** A missing measurement
must degrade into something that reads as *less information*, never as *a different answer*.

✅ **The outcome CHIP grades a recovery correctly, checked rather than assumed.** The verdict comes
from the run's scratch band, which is scaled to a full-size loss — so a quarter-size trade could
plausibly have been painted orange all the way down. It is not: over the **62 recoveries of the
UNCOSTED run** on the window below — see the cost-tier note under it before comparing that count
with the 65 — **26 of 26 losers grade `Lost` and none grades `Scratch`**, because the band is a
fraction of the run's median loss rather than a fixed dollar figure. ⚠ Worth re-checking if the size
knob is ever taken far below a quarter.

⚠ **Both excursion prices are stepped off the recovery engine's OWN R figures, never re-read from
the bars.** The engine already measured them, on the same bars, with the exit-bar cap that keeps
them inside what the trade lived through — a second reading here would be a second answer free to
disagree with the first. `max_adverse_r` was added to that engine for this; `max_favourable_r` was
already there. **A recovery row carries no target ladder and no fib leg, and both absences are
real** — the rule has no targets and prices nothing off a fib — so the chart correctly draws no
`TP1`/`TP2` on one.

⚠ **No Pine twin exists**, so `compare_strategy.py` can never gate this. With the toggle OFF the
bot is byte-identical to the gated one — which is why it defaults OFF, and why an export made with
it ON is not a parity input.

### 🔴 The toggle's warning text was WRONG in the direction that flatters the rule (rewritten 2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The toggle's warning text was WRONG in the direction that flatters the rule (rewritten 2026-08-21)*.

1. **"Does not model one account" overstates the defect.** Half the sharing is real — a recovery
   trade IS sized off a balance carrying every A+ trade that had closed by then (`recovery.py`'s
   heap walk). What is missing is the way BACK: A+ never sizes off the recovery. Saying neither
   direction works sends the reader looking for a bug that is not there.
2. **"Added AFTER the main book is finished"** describes the PASS correctly and reads as though the
   rows are appended at the end of the timeline. They are interleaved by entry bar.
3. 🔴 **+44.8% was the most optimistic row of a bracket the same measurement calls a BRACKET, and
   it is a RE-PRICE rather than a replay.** The real leg replayed on one balance under one 10%
   budget — the cap this bot already runs — measures **−29.9%** ($13,199,534 → $9,251,114 over
   186,910 M15 bars). **So the warning pointed the reader at "the real answer is much better" when
   the measured answer at the shipped cap is negative.** Both numbers are in
   `strategies/python/loss_recovery/CLAUDE.md`; the desc quoted the wrong one.

✅ **Rewritten to describe the MECHANISM and carry no figures at all**, which is also this file's own
house rule (`_comment` → COPY STYLE: no measurement dumps, no counts, no dates). It now says the
printed result is wrong in BOTH directions, names which half understates (profit that never
compounds) and which half flatters (nothing competes for one risk budget), states that the rule
loses money at the cap this bot runs and only pays on risk the main bot is not using, and points at
`backtest/tools/recovery_stack.py` and the package CLAUDE.md for the numbers.

🔴 **The standing lesson is about WHERE a number lives, not about this switch.** The stale figure
was in a UI string nobody re-measures, four files away from the table that would have corrected it.
**A warning that carries its own numbers goes stale silently and keeps being read as current** —
put the direction in the warning and leave the arithmetic in the doc that owns the measurement.

**13 tests in `tests/test_recovery.py`, all watched RED by a named mutation** (the mutation is in
each docstring). ⚠ **A fourteenth was written for the excursion cap, watched STILL-GREEN, and
deleted** — every recovery in the synthetic fixture exits LOCKED and in profit, so the mutation it
named changed nothing. The assertion now lives in `loss_recovery/tests/test_engine.py` as a direct
two-bar `_manage` call, which is the only shape where the ordering is observable.

⚠ **Quote the COST TIER with the recovery count or the number looks like a regression.** The rule
arms on a real loss, and a cost tier moves a borderline scratch across that line — same bars, same
window, same settings: **uncosted gives 62 recovery trades and `puprime_ecn` gives 65**, because
the primary's real-loss population goes 62 → 65 with the friction charged. Nothing changed in the
rule between those two runs.

## The DEAD-MARKET floor — `exec_min_atr_pct` (2026-08-26, ON at 0.08)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The DEAD-MARKET floor — `exec_min_atr_pct` (2026-08-26, ON at 0.08)*.

🔴 **READ ITS DRAWDOWN, NEVER ITS R, AND THE REASON GENERALISES TO EVERY ENTRY FILTER HERE.** Across
off / 0.08 / 0.10 the drawdown falls in order (55.5% → 47.9% → 41.5%) and the R does not (119.0 →
127.9 → 114.4), swinging ±8R on a 0.01 nudge. With one position slot, refusing a setup changes
which LATER trade gets the slot, so total R and the ending balance are a reshuffle; **removing
losing stretches is what survives the reshuffle.** The smoothness measure bottoms at 0.08.

🔴 **ORDER AN EQUITY PATH BY EXIT TIMESTAMP, NEVER BY BAR INDEX — this trade list mixes two
clocks.** A 15m setup carries a 15m index and a re-entry a fill-clock one, so an index sort puts a
2026 setup before a 2021 re-entry. **A SUM is order-independent, so the ending balance and the R
total come out byte-identical either way and give no signal at all**; only the path-dependent
numbers are wrong, and they are the only ones anybody reads. Refuse when the timestamp was never
populated rather than falling back to the index.

🔴 **"IT OVERRIDES THE METHOD" IS A CLAIM ABOUT ONE CALL SITE — FIND THE LINE THAT CONSUMES THE
VALUE.** The gate rides inside `_stop_clears_floor` because TWO entry paths call it (the 15m setup
and the re-entry's own fill clock), and a filter guarding one path is how a refused setup gets in
through the other door. `mpc_bos` defines its own `_place_entries` and still calls that shared
check from inside it (`mpc_bos/execution.py:401`), so it would have acquired a volatility filter
with **no error, no failing test and no Pine input to catch it**. All three forks now PIN it off
with the reason attached.

⚠ **An unseeded ATR REFUSES rather than passes** — the first 14 bars cannot answer *is the market
quiet*, and a gate whose silence reads as approval on the bars it knows least about is rule 1.

✅ **PORTED TO THE PINE THE SAME DAY** (`execMinAtrPct` + `f_marketHasRange`), with a `cfg_min_atr`
column in the export twin and the decode in `compare_strategy.py` — so this is **not** another
Python-only field the gate is structurally blind to. ⚠ **The Pine gates the 15m setup path only,
because that is the only entry path Pine has**; the re-entry is Python-only and has nothing to be
compared against. ⚠ **The Pine input is APPENDED after the last `input.float`** rather than sitting
beside the stop floor it belongs with, because declaration order is what TradingView keys a saved
chart's values off.

🔴 **ON AT 0.08 ON BOTH SIDES (Aaron's call, 2026-08-26), SO THE SHIPPED BOOK IS 240 TRADES AND
NOT 245.** It landed OFF earlier the same day and was switched on once the run was read — the
switch and the value were two separate decisions and the history is kept that way on purpose.
⚠ **PIN IT TO 0.0 TO REPRODUCE ANY BASELINE IN THIS FILE MEASURED BEFORE TODAY.** Not a formality:
the floor removes 5 entries, and with one position slot a removed entry changes which LATER setup
gets the slot, so a stored figure does not merely shift by the refused trades' R.
⚠ **The live bot does not have it until somebody PROMOTES**, and **the A+/B-LEG overlap audit is
stale until `backtest/tools/overlap_audit.py` is re-run** — it was measured on the logic that took
245.

✅ **RULE 22 IS SATISFIED (2026-08-26), AND IT TOOK TWO EXPORTS — THE SECOND ONE IS THE PROOF.**

🔴 **THE FIRST RUN WAS GREEN AND PROVED NOTHING ABOUT THIS FEATURE, AND ONLY A COVERAGE CHECK
COULD HAVE TOLD YOU.** At the shipped 0.08 the floor refused **nothing** on that window: replaying
its own bars with the floor OFF gave the same 26 trades and the same +29.06R. **That is not bad
luck, it is arithmetic** — the floor refuses 5 setups in 6.6 years, so an 11-month export expects
about 0.2 of one. A shipped-value export can never gate this.

⚠ **So export at a value that FIRES, then put the chart back.** It is the identical code path, and
it is the move the time stop already documents (shipped at 36 hours, exported at 4). Measured on
these bars: 0.08 and 0.10 refuse nothing, 0.20 refuses 6, **0.30 refuses 17–21** — the spread is
because the two exports are not the same bar set. **Re-export at 0.30 after any change here.**

🔴 **AND THE REASON A REFUSAL IS INVISIBLE IS WORTH KNOWING BEFORE SOMEBODY LOOKS FOR IT IN THE
DECISION STREAM: this gate emits NO block code on either side, deliberately** — `_stop_is_tight`
excludes it, matching Pine's `lBlkTight`, so a refused setup is untagged and shows up only as an
entry that is not there. **A coverage check here therefore cannot read a counter; it has to replay
the same bars with the floor off and diff the entries.** Four lines, and it is the only thing
standing between a green run and a false claim.

⚠ **What stands in meanwhile is deliberately weak and its own docstring says so**:
`test_the_PINE_side_ships_the_SAME_value_and_still_gates_both_entries` reads the Pine source and
pins that the two defaults are the same number and that both entry placements carry the gate. **It
would pass against a Pine whose comparison ran the wrong way round.**

**TESTED:** 10 in `tests/test_dead_market.py`, watched RED against HEAD and re-proved BY MUTATION,
because "the field is new" cannot tell a working gate from a present one. ⚠ **Turning it on broke
71 pre-existing tests and not one was a defect** — those fixtures feed two to four bars, so the ATR
never seeds and the gate refuses by design. **They were fixed by having each DECLARE its basis, not
by teaching a fixture to fake an ATR** — a fixture more capable than production describes a system
you do not have.

## 🔴 The leg latch's bar-time map was re-sorting 20,000 keys EVERY BAR (fixed 2026-08-26)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The leg latch's bar-time map was re-sorting 20,000 keys EVERY BAR (fixed 2026-08-26)*.

✅ **A dict preserves INSERTION order, `step` inserts one strictly increasing index per bar, and
the map is rebuilt empty on every restart (it is deliberately NOT in `_POSITION_FIELDS`) — so the
earliest-inserted key IS the smallest key** and `next(iter(...))` is the same answer the sort was
recomputing from scratch. O(n log n) per bar became O(1).

⚠ **The equivalence is a fact about the ORDER keys arrive in, so `_bar_ms_ordered` CHECKS it
rather than trusting it.** Any out-of-order or repeated index latches the flag False and the
original sort takes over, which is correct at any order. The latch is deliberately one-way:
re-arming it would be a second claim about the same thing.

✅ **Same keys survive, so no decision can move — PROVEN ON REAL BARS**, 62,468 of them, both
algorithms giving a byte-identical 66-trade book (`0c4250ab`).

🔴 **THE FIRST VERSION OF THAT PROOF WAS VACUOUS AND THE TIMING IS WHAT CAUGHT IT.** The script
patched `Execution` imported by package path; **the lab instantiates a DIFFERENT class object
loaded from the same file**, so the patch hit nothing, both runs took the new path, and
`TRADES IDENTICAL` was a run compared against itself. Nothing in the verdict looked wrong — the
tell was that the supposedly-slower run came out FASTER, which no amount of machine noise
explains. ⚠ **Patch `type(strategy.execution)`, never the imported name**, and this is the same
double-load this file already records under the 2.5× sweep arm that silently replayed stale code.
⚠ **A performance number is a CHECK on a correctness claim here, not just a headline** — the
identity result alone could not tell the two apart.
