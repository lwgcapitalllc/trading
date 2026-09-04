# CLAUDE.md — Market Structure Engine Subsystem

**Purpose:** Canonical market-structure (BOS/CHoCH/swing) detection engine shared by live algo
bots, for use in entries, take-profits, and stop losses.
**Scope:** Structure detection logic only. No trading decisions, no MT5 operations, no UI, no
chart rendering.
**Status:** Production — ported, unit-tested, and Pine-parity-validated (100% on the
`OANDA_XAUUSD, 15m` export, 21,729 bars); wired into `algos/` via
`algos/shared/structure_engine.py` (shim).
**Pine:** ported from `indicators/engines/structure_engine.pine`; parity harness is `indicators/engines/structure_engine_export.pine`, diffed against this Python by `tools/compare_tradingview.py`. Pine stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-08-08 (latest) — 🟢 **THE INTERNAL BREAKS CARRY THEIR OWN BAR NOW, AND THE CONSUMER THAT HAD TO GUESS ONE WAS WRONG AT EXACTLY ONE OF SIX SITES.** `InternalEvents` gained `bull_bos_loc` / `bear_bos_loc` / `bull_sos_loc` / `bear_sos_loc` — the BAR the broken level sits on, beside the four `*_price` fields that had been emitted bare since the port. 🔴 **The external engine has carried this since it was written (`bull_bos_h_loc` / `bear_bos_l_loc`); the internal engine never did, so a consumer that needed to DRAW a break had nothing to anchor it to and reached for `ifib_seed_*_loc` instead** — which is a fib LEG, a low and a high, not the level that broke. At five of the six internal-break sites the end of that leg *happens* to be the broken level. **At the first bear-iSOS branch it is not:** the break is `i_last_hl` while the seed's bottom is `i_tracked_ext`, a different price on a different bar, assigned two lines apart in `engine.py`. ✅ **MEASURED over 2.5 years of real cached M5 bars, 169 internal breaks: iBOS bull 65/65, iBOS bear 57/57, iSOS bull 22/22 — and iSOS bear 3/25**, wrong by up to $18.47. Found via the command-center chart, where the visible symptom was not the price at all: the wrong bar can land ON the break bar, so the line had zero length and did not render (12.4% of every internal break drew a line ≤1 bar). ⚠ **`int_break_origin_loc` is NOT this field and cannot substitute for it** — it is the order-block scan origin, and over the same 169 breaks it lands on the broken wick **zero** times in every category. That measurement is what said the engine had to grow the fields rather than the consumer picking a different existing one. ⚠ **Capture-only, the same additive pattern as `int_break_origin_loc`, `i_confirmed_*` and `ifib_seed_*`** — set at the six existing assignment sites, before the state reset, and nothing in the engine reads them back, so no structure decision can depend on them. ✅ **PROVEN COSMETIC BY A/B REPLAY rather than argued:** the engine was replayed at HEAD and at the working tree over **186,488 real cached M15 bars** and every pre-existing field diffed bar by bar — **12,308,208 field values, 0 differences**, with the four new fields carrying **1,993 real values** rather than a column of `None` (i.e. the check is not vacuous in either direction). ⚠ **THE PINE PARITY GATE IS OWED AND THE A/B REPLAY IS NOT A SUBSTITUTE FOR IT.** No `structure_engine_export.pine` CSV is on disk, so `compare_tradingview.py` could not be run — the same position the fib engine was in on 2026-08-02, where the A/B diff was accepted as *the same evidence by a different route* and the gate was still re-run on the next real export. **Re-run `compare_tradingview.py` on the next export.** ✅ 74 engine tests green (market_structure + fibonacci + order_blocks). **The standing lesson is about what an event is allowed to omit: the four prices were correct for their whole life, and the field the engine did NOT emit is what made a downstream consumer invent an answer — silently, and right often enough that only one branch in six ever showed it.** Earlier: 2026-07-12 — re-synced to the `choch_lock` removal in `mpc_jarvis.pine` and re-validated at 100% parity (`compare_tradingview.py --warmup 365`, exit 0, `VANTAGE_XAUUSD, 5m`, 9,270 bars). See "The 2026-07-12 CHoCH re-sync" below.

---

## Key paths

```
engines/market_structure/
├── engine.py                      ← StructureEngine (the state machine)
├── types.py                       ← Bar, SwingLevel, ExternalEvents, InternalEvents, StructureEvents
├── __init__.py                    ← re-exports the public API
├── CLAUDE.md                      ← this file
├── MARKET_STRUCTURE_ENGINE.md     ← plain-English algorithm doc
└── tests/
    └── test_engine.py             ← hand-traced synthetic-sequence tests
```

---

## Public API

```python
from market_structure import StructureEngine, Bar

eng = StructureEngine(major_length=15)  # 15 is the validated default; do not change casually

# Feed one closed candle at a time, in order:
events = eng.update(Bar(index=i, open=o, high=h, low=l, close=c))
# events.external -> ExternalEvents (bull_bos, bear_bos, bull_sos, bear_sos, new_swing_high/low,
#                    unconfirmed_high/low, broken_high/low_label,
#                    bull/bear_bos_high/low + _h_loc/_l_loc [break-leg endpoints, break bar only], ...)
# events.internal -> InternalEvents (bull_bos, bear_bos, bull_sos, bear_sos, new_swing_high/low,
#                    demoted_high/low_label,
#                    int_bull_break/int_bear_break + int_break_origin_loc [OB-creation gate, see below],
#                    i_confirmed_high/low_* + ifib_seed_* [fib-support captures, see below], ...)
# Every label the Pine source draws has a matching event field carrying its *_price and *_index.
# See the "Label -> event field" table in MARKET_STRUCTURE_ENGINE.md for the full mapping.

# Or replay a full history for backtesting (accepts Bar objects, dicts, or a pandas DataFrame):
all_events = eng.replay(bars)

# Current-state reads:
eng.dir  # 1 bullish, -1 bearish, 0 undetermined
eng.active_swing_high  # SwingLevel | None
eng.active_swing_low
eng.last_confirmed_high
eng.last_confirmed_low
eng.internal_mode  # 1 tracking up, -1 tracking down, 0 watching
eng.internal_swing
```

---

## Why this is a stateful class, not a stateless function (deviation from `engines/regime/`)

`engines/regime/` is the sibling shared-library pattern in this repo: stateless `df -> label` functions,
recomputed fresh on every call from a dataframe slice. This module intentionally does **not**
follow that pattern, and the reason is structural, not stylistic:

Swing/BOS/CHoCH structure is inherently a streaming state machine. The active swing, the pullback
qualifying-candle counters, the trend direction, the CHoCH lock — all of it carries forward
bar-to-bar and cannot be correctly recomputed from a single bar or a short window in isolation.
Recomputing it from scratch on every call would mean replaying up to ~2000 bars of Python-level
branching per call (the Pine indicator's own `max_bars_back`), which fights directly against the
"near real-time, speed is part of the trading edge" requirement this engine exists to serve —
see `algos/CLAUDE.md`'s latency-awareness rule. A `StructureEngine` instance is built once per
symbol/timeframe, fed one bar per `update()` call as candles close, and carries its state forward
indefinitely at O(1) amortized cost per bar (aside from the bounded backward scans described in
`MARKET_STRUCTURE_ENGINE.md`, which are capped, not unbounded rescans of full history).

Do not "fix" this into a stateless function to match `engines/regime/`'s shape. The two subsystems solve
different problems: regime classification is a snapshot judgment over a rolling window; structure
tracking is inherently sequential.

---

## Pivot lag caveat (brief — full explanation in MARKET_STRUCTURE_ENGINE.md)

New external swing *candidates* are only confirmed `major_length` (15, by default) bars after the
fact — this mirrors Pine's `ta.pivothigh`/`ta.pivotlow` window and is preserved deliberately, not
a bug. **BOS/CHoCH break events themselves are same-bar/real-time** — the lag only affects how
quickly a brand-new swing candidate gets identified, not how fast a break against an
already-known level fires. Internal structure has no pivot lag at all. See
`MARKET_STRUCTURE_ENGINE.md` for the full explanation.

---

## Consumers

| Consumer | Path | Status |
|---|---|---|
| Live/algos bots | `algos/shared/structure_engine.py` (thin shim over `market_structure.StructureEngine`) | Wired |
| `engines/fibonacci/` | reads the public `ExternalEvents` + `InternalEvents` (i_confirmed / ifib_seed) via its own `StructureSnapshot` | Wired |
| `engines/order_blocks/` | reads the public `ExternalEvents` + `InternalEvents` via its own `StructureSnapshot` | Wired |
| Command-center backtest lab | `command-center/backend/services/` | Not yet wired — future consumer, not touched by this port |

**`InternalEvents` OB-creation gate (`int_bull_break` / `int_bear_break` / `int_break_origin_loc`).**
These three fields were added for `engines/order_blocks/`. They are a purely additive, capture-only exposure
of state the engine already computes — they mirror Pine's `int_bull_break` / `int_bear_break` /
`int_break_origin_loc` and are set at the six internal-break sites (iBOS bull/bear use
`tracked_ext_loc` as the origin; the four iSOS branches use `sw_loc`), right where the existing
`bull_bos` / `bear_sos` / `*_price` fields are set, before the state reset. No structure logic
changed and structure parity was re-confirmed unbroken. `engines/order_blocks/` scans back from
`int_break_origin_loc` to drop an OB on the internal break; the external OB path reads the existing
`bull_bos_l_loc` / `bear_bos_h_loc`.

**`InternalEvents` fib-support captures (`i_confirmed_high/low_*` + `ifib_seed_*`).**
Added for `engines/fibonacci/` in the 2026-07-08 fib re-sync, and the same additive, capture-only
pattern as the OB gate above — no structure logic changed and structure parity was re-confirmed
unbroken (`compare_tradingview.py` exit 0). Two groups: (1) `i_confirmed_high/low_price` + `_loc`
are set on the bar an internal swing confirms (Pine's iSH/iSL confirm sites), and the Structure fib
adopts the more-extreme confirmed internal swing as its pull anchor. (2) `ifib_seed_dir/asl/asl_loc/
ash/ash_loc` are set at the six internal-break sites (iBOS bull/bear + the four iSOS branches), the
same sites as the OB gate, and seed the new Internal fib (`InternalFib`) with the leg it anchors on.
Both are `None` off their firing bar.

---

## Do

- Port changes to `indicators/engines/structure_engine.pine` back into `engine.py` line-by-line if that
  Pine source is ever updated post-validation. Do not let the two drift.
- Keep `update()`'s hot path free of pandas/numpy — see "Never do" below.
- When adding a new event or read property, update `MARKET_STRUCTURE_ENGINE.md` and this file's
  Public API section in the same commit.
- If you find what looks like a bug or inconsistency in the ported Pine logic, leave a `# NOTE:`
  comment in `engine.py` flagging it rather than silently correcting it. Several already exist —
  see the internal iHH/iLH labeling note and the CHoCH-branch asymmetry note in `engine.py`.

## Never do

- Do not add a pandas/numpy hard dependency to `engine.py`'s `update()` hot path. `replay()` may
  import pandas lazily (optional, DataFrame convenience only) — mirror the try/except pattern
  already used there.
- Do not simplify, "clean up", or optimize away any branch of the ported state machine (pullback
  qualifying-candle logic, bounded rescans, etc.) without Aaron's explicit sign-off — this is
  validated against a real chart at ~99.99% parity and any behavioral change breaks that.
- Do not "tidy up" the now-unread `choch_lock` field. As of 2026-07-12 it is still declared, set and
  released but nothing reads it — that dead state exists in `mpc_jarvis.pine` too, and these
  files are kept byte-identical to it. Deleting it here would make the next Pine diff lie.
- Do not build a second structure engine anywhere else in the repo. This is the canonical
  implementation; all consumers import from here.
- Do not change `major_length` from 15 in production consumers without discussing — it is the
  validated constant from the source Pine indicator.

---

## Validation (Pine ↔ Python parity)

Before trusting the engine on live money, confirm it matches the Pine source on real candles:

1. `indicators/engines/structure_engine_export.pine` — an instrumented copy of `structure_engine.pine`
   (logic byte-identical; adds `plot()` columns for every engine output). Put it on a chart in
   TradingView and export the chart data to CSV.
2. `engines/market_structure/tools/compare_tradingview.py <that.csv>` — feeds the CSV's candles through
   `StructureEngine` and diffs its output against the Pine columns in the same file, bar by bar.
   Exit 0 = full parity; exit 1 = prints every mismatch. Pass `--major-length` to match the Pine
   build. Uses only the standard library.

The CSV carries both the candles (fed to Python) and the Pine outputs (compared against), so
there is no data-source mismatch to muddy the result.

**Result (2026-07-02):** full parity — every field matched on all 21,729 bars of the
`OANDA_XAUUSD, 15m` export (exit 0). The run closed one porting gap: the port had raised external
`new_swing_high`/`new_swing_low` on the mid-pullback break-promotion path, which the Pine source
never does (Pine sets those flags only in the 3-candle pullback-confirm block). That false signal
seeded the internal engine early and drifted `internal_mode` for ~22 bars. Fixed in
`_on_ash_broken`/`_on_asl_broken`. Re-run this tool after any `engine.py` change to keep it at 100%.

**Second gap (2026-07-02, post-validation):** the eight break-leg fields (`bull_bos_high`,
`bull_bos_h_loc`, `bull_bos_low`, `bull_bos_l_loc` + bear mirror) existed in
`structure_engine.pine` but were never ported — they carry the full impulse leg of a BOS (both
endpoints), which the Sniper-fib anchor needs. Added to `engine.py`/`types.py` and to the export +
compare tool (`px_bull_bos_high` / `px_bull_bos_h_ago` columns; `_loc` exported as "bars ago" to
survive the Pine absolute-index vs Python 0-based-index offset). The new columns are **optional** in
`compare_tradingview.py`, so old CSVs still validate every other field. **Parity confirmed
2026-07-02** on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars): every field — the eight new
break-leg fields included — matches on all 9,494 warm bars (`--warmup 227`, exit 0). The first 227
bars mismatch only because the Pine export begins at a non-zero `bar_index` (TradingView had chart
history before the export window, so its engine was already warm while the Python engine starts
cold); both converge once the structure re-establishes inside the window. This is a second,
independent dataset from the original OANDA validation, so it re-confirms the whole engine too.

## The 2026-07-12 CHoCH re-sync (`choch_lock` removed from the break decision)

Aaron's brother reported a missing higher high on XAUUSD 15m (17 Jun 2026, the ~4382 spike) and had
it fixed on the TradingView side. That fix landed in `mpc_jarvis.pine` and was ported down the
whole chain. **Both symptoms he saw were one bug.** A bullish SOS set `choch_lock`; the next bearish
break was therefore not treated as a CHoCH, so it rendered as a **BOS instead of an SOS**. And
because the bear-break fallback classifies the old high with `old_is_hh = is_choch ? true : (…)`,
losing the CHoCH also lost the forced `true` — so the **HH never printed**.

Four changes, applied byte-identically to all six Pine copies of the engine and ported here:

1. `is_choch = st.dir == -1` (was `… and not st.choch_lock`) — bull break.
2. `is_choch = st.dir == 1` (was `… and not st.choch_lock`) — bear break.
3. On a bull-break SOS, the promoted pullback low is labelled **ASL**, not HL/LL.
4. On a bear-break SOS, the promoted pullback high is labelled **ASH**, not HH/LH.

…plus, in both, the confirmed-swing map (`last_conf_high` / `last_conf_low`) is now written only
`if not is_choch`. On a fast reversal the promoted extreme is merely the new ACTIVE swing — the NEXT
break in that direction classifies it. That guard is what stops a lower high from overwriting a
genuine higher high, which is what suppressed the HH.

**Public-API consequence:** `broken_high_label` / `broken_low_label` widened from `"HH"|"LH"` /
`"HL"|"LL"` to include `"ASH"` / `"ASL"`. Consumers keying off the confirmed labels must read ASH/ASL
as *"not yet classified"*, not as an unknown value. No production consumer reads those fields today.

`choch_lock` itself is now inert — still declared, set and released, never read. It is kept
deliberately (see "Never do") so these files stay byte-identical to `mpc_jarvis.pine`.

**Parity re-confirmed 2026-07-12** on a single fresh `VANTAGE_XAUUSD, 5m` export (9,270 bars) that
carried the OB + fib harnesses at once: `compare_tradingview.py --warmup 365` exit 0, and the two
downstream engines (STALE-BY-INPUT, since the structure stream now fires more SOS and confirms fewer
swings) re-validated off the same CSV — `compare_ob.py --warmup 548` and `compare_fib.py --warmup 368`,
both exit 0.

## The 2026-08-21 refused-wick fix — the same swing, labelled twice, for a different reason

The day after the tie guard shipped Aaron sent three charts: a doubled `LL`, an `ASH` printed beside
an `HH`, and a bogus `HH` that appeared later. **One root cause behind all three, and the tie guard
could not see it** — the two bars are NOT at the same price, so an exact-equality test never fires.

🔴 **STRUCTURE BREAKS ON A CLOSE. THE RESCAN READS THE WICK.** That is the whole defect. A wick
through the level is deliberately refused (`ash_broken = close > st.ash`), but the post-break rescan
reads the raw `high[i]` / `low[i]` over a window bounded by the OPPOSITE side's last confirmed bar.
That window reaches back BEFORE the swing the break just confirmed — so it can find a bar that
pierced the level, closed back inside, was correctly refused, and install THAT as the new active
swing. The result is an active swing EARLIER than and MORE EXTREME than the swing just labelled: a
second label crowding the first. When it is later broken it is promoted to its own permanent
`HH`/`LL`, which is the "wrong new HH" that follows.

**Traced end to end on real bars** (`XAUUSD__M15`, rows 5307-5319):

```
bar 5307   high 1241.90  close 1241.05    active swing high 1241.12
           → high pierced it, close did NOT. Correctly no break, no label.
bar 5308   closes above  → confirmed HH @ 1241.51
bar 5319   bear break    → promotes HH @bar5308, then rescans and finds
                           bar 5307's refused wick → installs it as the new ASH
```

**MEASURED, before → after:**

| | before | after |
|---|---|---|
| bear breaks anchoring the new ASH EARLIER than the HH, 400,000 M1 bars | 15 / 1,380 | **0** |
| bull breaks, mirror, M1 | 16 / 1,662 | **0** |
| bear breaks, 186,759 M15 bars | 8 / 768 | **0** |
| bull breaks, M15 | 7 / 934 | **0** |
| `sos_fade` book, 2020-01-01 → 2026-08-06 | 159 trades / +142.18R / maxDD 5.61R | 158 / **+140.71R** / 5.61R |

🔴 **NOT COSMETIC.** `fibo_ash := st.ash`, so a bogus active swing moves the External Fib's anchor
and with it E1-E4, the TP ladder, the Sniper Zone and the B-LEG band. One measured case was **$8.10**
out. The SOS Fade cost is −1 trade and −1.47R over 6.5 years, well inside this strategy's own run-to-run
sd of 15.06R (the jitter audit) — but it is a real trade-list change, not a redraw.

**The fix folds INTO the tie guard rather than sitting beside it**, because a tie is just the
equality case of the same question: *a rescan may only install a swing strictly NEWER than the one
just confirmed.* At-or-before it, a tie or a deeper extreme is either the same swing or a refused
wick, and snapping the value on a tie is a no-op. One test, both cases, +1 line of code per site.

⚠ **`processMTF` in `mpc_jarvis.pine` DID need it, and the note saying otherwise was corrected.**
That note was right about the 2026-08-20 guard — it only moved a `*_loc`, and no `*_loc` in that
method has a consumer, so omitting it really was a no-op. **This snap moves the VALUE**, and
`st.asl := lowest_val` is the level the next break is tested against. Omitted there, the MTF rows,
`f_rev15`'s leg and the chart engine would answer differently about the same bar. **A guard that was
correctly skipped once is not a guard that can be skipped again — check what the new one writes.**

⚠ **Applied to all 17 Pine files (36 sites) and the Python port**, each strategy verified
byte-identical to its export twin, or a parity gate would be comparing two different engines.

⚠ **The parity gate has NOT run and cannot yet.** `engines/market_structure/exports/` is empty, and
an export taken before this change encodes the OLD behaviour — so the gate can only be satisfied by
a fresh export from the FIXED `structure_engine_export.pine`. Rule 22 is outstanding on this change;
`tests/test_rescan_wick.py` (100 real bars, watched RED) is the evidence that exists today.

✅ **CLOSED 2026-08-27 — RULE 22 IS SATISFIED FOR THIS FIX.** A post-fix export exists after all,
in `engines/` rather than in `exports/`: `VANTAGE_XAUUSD, 5_0bcd2.csv`, taken **2026-08-23**, and
`compare_tradingview.py` is **GREEN from bar 0 on all 20,574 bars**. The paragraph above stands as
the record of what was true when it was written; the gate has now run.

🔴 **AND THE THREE RED GATES ON THIS MACHINE ARE THIS FIX WORKING, NOT A DEFECT — CHECKED, NOT
INFERRED FROM DATES.** Every red export was taken **2026-08-20 23:08–23:31**, the day BEFORE the
fix, so its Pine columns encode the OLD behaviour. What settles it is the OHLC underneath the
disagreement, read straight out of the export:

| export | bar | Pine anchored | Python kept |
|---|---|---|---|
| `15_b201e.csv` | 14123 | bar **14108**, low 4677.34, close 4691.34 | bar **14111**, low 4681.90 |
| `5_84d6c.csv` | 7322 | bar **7309**, low 4335.14, close 4338.83 | bar **7312**, low 4336.87 |

**In both, Pine installed the EARLIER and MORE EXTREME bar — a low the close never broke — which is
precisely the refused wick this fix stopped installing.** `15_9d44d.csv` fails at the same bar
14123 and the same timestamp, one engine upstream. The fibonacci reds are inherited: `fibo_asl` IS
the structure anchor, so a wrong active swing moves E1-E4, the TP ladder and the Sniper Zone with
it.

⚠ **The 5m fibonacci export ALSO has a genuine cold start at bars 49-58** (touch latches and
`px_fib_origin`), which is the ordinary "TradingView's engine was warm before the export window"
effect and is unrelated. It is called out separately so a future reader does not fold it into the
anchor story.

⚠ **A pre-existing red is still a red, and this note did NOT retire these three.** What it retired
was the need to re-investigate them: **the fix is right, the exports are stale, and the only thing
that can turn them green is re-exporting from today's Pine.**

✅ **RE-EXPORTED AND ALL THREE ARE GREEN (2026-08-27, same day).** Aaron re-took all three from
today's Pine and every gate passes:

| new export | replaces | bars | verdict |
|---|---|---|---|
| `VANTAGE_XAUUSD, 15_cafd7.csv` | `15_9d44d` (structure) | 21,403 | **GREEN from bar 0, every field** |
| `VANTAGE_XAUUSD, 15_dfe47.csv` | `15_b201e` (fibonacci) | 21,403 | **GREEN from bar 32** |
| `VANTAGE_XAUUSD, 5_02c0a.csv` | `5_84d6c` (fibonacci) | 20,229 | **GREEN from bar 49** |

⚠ **The three superseded files were DELETED the same day** (Aaron's call). They are named here
only as history — do not go looking for them, and do not re-derive a red from one if a copy turns
up. **A stale export left beside a fresh one is a trap that costs an afternoon**, because a gate
run against it is red for a reason that has nothing to do with the code under test.

🔴 **THE PREDICTION HELD EXACTLY, AND THAT IS THE POINT WORTH KEEPING.** The paragraph above
was written from the exports' own OHLC — Pine anchoring an earlier, more extreme bar the close never
broke — and it said the fix was right and the files were stale. **A fresh export was the experiment
that could have falsified it and did not.** Had the reds been drift, re-exporting would have changed
nothing.

⚠ **The two fibonacci gates each still disagree on exactly ONE bar, and it is not warm-up in the
usual sense — CHECKED, not assumed.** In both files the single mismatching bar IS the very first bar
the fib becomes active (bar 31 on the 15m, bar 48 on the 5m), and the one field is the leg's
origin-changed pulse. **Pine compares the new origin against an unset previous value, and an unset
value makes that comparison neither true nor false — so Pine reports no change on its own first
activation, while the Python reports one.** It can only ever happen once per run, because after the
first activation there is a previous value to compare against; the gate proves it, running clean
across the remaining 21,371 and 20,180 bars. On that bar the pulse resets latches that are already
clear, so nothing downstream moves.

⚠ **The structure gate needs no warm-up allowance at all and the fib gates do** — that asymmetry is
inherent, not a defect: the fibs cannot exist until structure has produced an anchor, so their first
bar is always a first activation and structure's never is.

## The 2026-08-20 tied-extreme fix — one swing, two permanent labels

Aaron spotted an `LL` and an `HL` printed side by side on the same 15m swing low and asked whether
he had broken something recently. He had not: the defect is as old as the port (`3dfdfd9`) and was
byte-identical in `mpc_jarvis.pine` and here. **It is rule 14 in the wild — the parity gate said
the two implementations AGREE, and both were wrong the same way for the engine's whole life.**

**What happens.** When two bars print an *identical* extreme, the post-break rescan runs
newest-to-oldest with a strict `<` (or `>`), so it lands on the **later** of the tied bars — while
the label for that swing is already anchored on the **earlier** one. `already_conf_low` /
`already_conf_high` then compare bar index *as well as* price, read the moved anchor as a brand new
swing, and emit a second label at the same price. Pine never deletes those labels, so they stack.

🔴 **The block already contained the answer and disagreed with itself.** Three lines below the
guard, the ASL/ASH label is suppressed on `lowest_val != st.last_conf_low` — **price alone**. So one
test in that block treats an equal price as the same swing and the other demands a matching bar
index too. **The bug was not a missing rule, it was two rules for the same question.** The fix makes
them agree: on a tie, keep the original anchor.

⚠ **The two sides run their steps in OPPOSITE ORDER, and the first attempt at this fix was placed
symmetrically and silently did nothing.** The low side promotes the old swing and *then* rescans;
the high side rescans and *then* promotes. Put next to the scan, the high-side guard reads a
`last_conf_high` the promotion has not written yet, compares against the wrong swing, and no test
notices because the code is *there* and looks right. It sits immediately before `st.bear_bos_high`
for that reason. **A guard that reads a value written later is indistinguishable from a guard that
works, and only a red test told the two apart.**

**MEASURED, replaying the real cache** (`backtest/cache/XAUUSD__M15.csv`, `__M1.csv`):

| | before | after |
|---|---|---|
| stacked pairs, 186,759 M15 bars | 7 | **0** |
| stacked pairs, 400,000 M1 bars | 28 | **0** |
| labels emitted, M15 | 3,776 | 3,769 (−7) |
| labels emitted, M1 | 8,392 | 8,362 (−30) |
| labels that vanished leaving NO label at that price | — | **0** |
| labels the fix ADDED | — | **0** |

Every removal was a duplicate on a price that still carries a label; nothing new is invented. On M1
two of the thirty removals were 32–57 bars from their twin rather than adjacent — same price, label
retained, and stated here rather than rounded to "only duplicates".

⚠ **The high side is the MORE common of the two (17 vs 11 on M1) and nobody had ever noticed it**,
because a tie there prints `HH` beside `HH` — it just looks like a slightly bold label. The low side
prints `LL` beside `HL`, a visible contradiction, which is the only reason this was ever reported.
**Look for the silent twin of any defect whose sides are labelled by different rules.**

⚠ **`>=` was left alone, deliberately.** `brk_is_hl = st.asl >= st.last_conf_low` calls an exactly
equal low a *higher* low, which is what makes the second label read `HL`. With the anchor fixed the
equal-price case never reaches it, so changing it would relabel swings nobody has complained about.
It is a separate judgement, not part of this fix.

⚠ **`processMTF` in `mpc_jarvis.pine` carries the same two guards and was NOT changed.**
`f_mtfStruct` returns `[dir, sEv]` only, direction is decided by close-vs-price breaks, and no
`*_loc` in that method has a consumer — so the tie cannot change what it reports. That was checked,
not assumed; the 1m/15m/4H confirmation rows were never affected. A comment at each site says so.

🔴 **NOT PARITY-GATED, AND IT CANNOT BE ON THIS MACHINE.** `compare_tradingview.py` needs an export
carrying `px_ash`/`px_asl`/`px_dir`; the only CSVs present are *strategy* exports, and a sweep of
the machine found no structure export at all. **Rule 22 therefore blocks the commit** — this is the
same "which gate you can run depends on what is sitting on that machine" problem the root CLAUDE.md
records. To unblock: put `indicators/engines/structure_engine_export.pine` on a TradingView chart,
export the CSV, run the tool, and only then commit.

**The test is `tests/test_duplicate_swing_labels.py`.** Watched RED against the pre-fix engine — the
three regression tests fail with the exact stacked pairs, on real inlined bars (the shortest
cold-start replays that still reproduce: 130 bars and 200 bars; 120 and 180 do not). A fourth test
asserts the tied bars are still present in the fixtures, so a fixture that silently loses its tie
goes red instead of letting the other three pass for the wrong reason.

## References

- Algorithm explained in plain English: `MARKET_STRUCTURE_ENGINE.md`
- Pine source of truth: `indicators/engines/structure_engine.pine` (validated ~99.99% parity against the
  original "Structure OS" TradingView indicator via `indicators/engines/mpc_jarvis.pine`)
- Shim and bot integration: `algos/shared/structure_engine.py`
- Sibling shared-library pattern (stateless, for contrast): `engines/regime/CLAUDE.md`
- Monorepo context: `../CLAUDE.md`

## 🔴 The pivot detector copied the WHOLE 2000-bar buffer to read 31 of them (2026-08-27)

`_pivot_at_current_bar` did `list(self._bars)[n - (2*L+1) : n]`. `self._bars` is a deque bounded at
`max_bars_back` (2000), so **every bar allocated a 2000-element list, copied 2000 references into
it, and threw all but 31 away** — on every replay in this repo, for the life of the port.

**MEASURED under cProfile on a 23,539-bar replay: it was the single hottest function in the whole
profile, 3.26s of 34.1s.** Removing the copy took the profile to **8.3s**, which is far more than
the function's own share — the allocation and its 2,000 reference-count operations per bar were
driving garbage collection that cProfile charges to whoever is running. **Unprofiled, end to end on
62,468 real bars, the replay went 81.25s → 22.16s.**

✅ **Indexing near a deque's right-hand end walks from that end**, so the window costs O(L²) pointer
steps rather than an O(max_bars_back) copy plus a list allocation.

⚠ **The COMPARISONS are untouched and that is deliberate** — the same `>` and `<` against the same
bars, candidate excluded, and the early exit cannot alter a result because both tests are pure
conjunctions. It only stops asking once both answers are settled. **This is a memory-traffic fix,
not a logic change**, which is the only kind of change this file's *Never do* list allows here
without sign-off.

✅ **RULE 22 SATISFIED — the gate RAN, on two real exports, before and after:**

| export | before | after |
|---|---|---|
| `VANTAGE_XAUUSD, 5_0bcd2.csv` (20,574 bars) | GREEN from bar 0 | **GREEN from bar 0** |
| `VANTAGE_XAUUSD, 15_9d44d.csv` (20,991 bars) | RED at bar 14123 | **RED at bar 14123, same timestamp** |

✅ **THE 15m RED WAS A STALE EXPORT AND IS NOW CLOSED (2026-08-27)** — its replacement
`VANTAGE_XAUUSD, 15_cafd7.csv` (21,403 bars) is **GREEN from bar 0 on every field**, so this engine
now has a green gate on both timeframes. The paragraph below stands as the record of what was true
when it was written, and its discipline is the reason the red was recorded rather than explained away.

⚠ **THE 15m EXPORT IS RED AND WAS RED BEFORE THIS CHANGE — a pre-existing red is still a red.** It
is recorded here so the next reader does not spend an afternoon blaming the pivot detector for it,
and it is NOT retired by this note. The same discipline was applied downstream: the SOS Fade strategy gate
is GREEN on `15_3ce38.csv`, and the fibonacci gate is RED at bar 31 / bar 49 on its two exports
**identically before and after**.

✅ **Also proven at the CONSUMER, which is the check a green engine gate cannot make**: the
`sos_fade` book over 62,468 real M15 bars is byte-identical before and after — same bar-stream
digest, all 66 trades identical on every field (`backtest/tools/replay_fingerprint.py`, with the
engine reverted via `git stash` to take the baseline in the same working tree).

**Tests:** 251 engine tests green, 1,201 strategy + backtest tests green.
