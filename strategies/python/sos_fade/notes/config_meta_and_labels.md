# Notes — The meta file — labels shared with the Pine

How this strategy's settings are labelled and described for the lab pages, and why those labels are shared with the Pine. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### `sos_fade.meta.json` — labels and descs are SHARED WITH THE PINE (2026-08-02)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *`sos_fade.meta.json` — labels and descs are SHARED WITH THE PINE (2026-08-02)*.

🔴 **39 `desc` fields were rewritten to plain English on 2026-08-16, and the trigger was the
PINE side.** Every input tooltip in all 29 Pine files was cut to one or two plain sentences
(rule: `strategies/tradingview/CLAUDE.md` → *TOOLTIPS ARE PLAIN ENGLISH*), and because a `desc`
IS that tooltip verbatim, this file had to move with it or the lab panel would have gone on
teaching the old wording. ⚠ **Strings only — every param's `name`, `group`, `core`, `widget`
and `options` is unchanged, verified by diffing and counting the changed lines that do not
contain `"desc"`.** The measured detail those descs used to carry now lives in
`strategies/tradingview/docs/sos_fade_strategy.md` and the specs.

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
⚠ **A value carries a unit only if its param STATES one.** `exec_sec_fill_tf_min` did not, so
the run rail read *Fill clock · 5*; it states `minutes` since 2026-09-13. Its `label` keeps
*(minutes)* — `config.py` and three backend comments quote it word for word.

⚠ **THE WHOLE SECONDARY GROUP IS PYTHON-ONLY AND IS EXEMPT FROM THIS RULE — CHECKED, NOT ASSUMED.**
`sos_fade_strategy.pine` declares 71 inputs and not one of them is a re-entry input (`grep -c "input\."`
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
leg, a different fib). ⚠ **`b_leg` USED to get none for free by overriding `_place_entries`, and
since 2026-08-11 it records its OWN — do not read this section as covering it.** That fork prices
off the frozen SOS leg, not this ladder, so it builds a `TradeFib` from its own band anchors and
under the same all-or-nothing rule; inheriting `_freeze_fib` there would attach a real, fully
populated ladder describing a leg the trade was never priced against. See
`strategies/python/b_leg/CLAUDE.md` → *The recorded fib*.
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
default.** Five new config fields, in lockstep with `sos_fade_strategy.pine`: `exec_fvg_pre_zone` (False),
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
edges feed the "SOS Fade has priority" gate, so this is NOT inert there), and `BosConfig` pins
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
run-capture, all twelve runs in `sos_fade_optimization.md` — was taken THROUGH this bug and
needs re-baselining**; the exit-ladder conclusions are the most exposed, because the bug killed
trades one bar after entry, before the ladder ever engaged. 3 regression tests, 534 green.
**The lesson: a green `compare_strategy.py` says Pine and Python AGREE, never that either is
right** — this bug was faithfully ported, so the gate was green for its whole life. **Recorded the
same day and NOT part of the bug: a wrong-side stop can still fill at the next bar's open
legitimately, and it is a backtest limitation rather than a defect** — see
`### Wrong-side stop fills` before anyone re-reports the symptom.
divergence on this pair.** `exec_min_stop_mode` / `exec_min_stop_val`, the floor applied at order
placement, block reason code 7, a REGENERATED `sos_fade_strategy_export.pine` (body byte-identical to the
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
SOS Fade Pine files (Aaron's call — it is what he trades, and Run 6 rode it over the full history). The
⚠ block below is AMENDED, not retracted: 0.886 is still inside the entry band and neither Run 4
defect is fixed; 0.618 / 0.702 / 0.786 stay unsupported. `b_leg` PINS "1.0" rather than
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
