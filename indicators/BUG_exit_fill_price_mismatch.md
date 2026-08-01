# BUG: exit fills at a price matching no stop or target — ✅ CLOSED

**Status:** ✅ **FIXED AND VALIDATED 2026-08-01.** Root cause found, reproduced on real bars, fixed
in all five strategy Pine files and in `strategies/python/mpc_sos_fade/execution.py` (which
`mpc_bleg` reuses), **both parity gates exit 0 on full-history post-fix exports**, and the bug's
fingerprint is measurably gone from the bars (4 affected entries → 0). 534 tests green.
**Found:** 2026-07-14, on `VANTAGE_XAUUSD, 15m`, by eye off the price chart, by Aaron's brother.
**Severity:** Medium — see *Blast radius*. It cost almost nothing in realised P&L; what it cost
was 29 setups in 165 that were killed one bar after entry before they could do anything.
**Files:** all five strategy Pine files + `execution.py`. The ENGINE above the execution layer was
never involved.

> ### Why this file is kept after being closed
>
> Three reasons, and none of them are sentiment:
> 1. **Every number measured before 2026-08-01 was measured through it.** Until the re-baselining in
>    *What is still open* is done, this is the document that says which figures are stale and why.
> 2. **It is the worked example behind a standing repo lesson** — *a green parity run says the two
>    implementations AGREE, never that either is RIGHT*. That rule is quoted in four `CLAUDE.md`
>    files; this is the case it was learned from.
> 3. **The symptom recurs legitimately.** A wrong-side stop filling at the next bar's open is a
>    backtest limitation that will keep appearing on the chart (see *The residue* below). Without
>    this file, the next person who spots it re-opens a fixed bug.
>
> Delete it once the re-baselining is done AND the residue note has lived in
> `strategies/python/mpc_sos_fade/CLAUDE.md` long enough to stand alone.

---

## Symptom

Some trades close all partial legs (TP1 / TP2 / RUN) at the **same price on the same bar**, one
bar after entry, at a price that is **neither the stop nor any target** the code places.

Reference trade (CSV `MPC_A+_Strategy_FX_XAUUSD_2026-07-14.csv`, rows 1–3):

- SHORT, entry **3647.91** @ 2025-09-09 02:30
- All 3 legs (S-TP1 / S-TP2 / S-RUN) exit at **3649.89** @ 02:45 (next 15m bar)
- Result: **−0.17R**, −$173.45 total, 1-bar duration
- Label: Arm Div · SOS 0 bars ago · shallow (0.5) entry

---

## Root cause — the FILL BAR was allowed to stage the stop

**A resting limit is reached by price coming to it from the wrong side.** A buy limit is filled
on the way DOWN; a sell limit on the way UP. So the entry bar's *favourable* extreme is where the
market was **before the trade existed** — it is the approach to the order, not a move the trade
made.

The staging block read that extreme anyway:

```pine
if strategy.position_size < 0                       // ← ran on the FILL bar too
    if sStage < 1 and low <= sTP1                   // ← `low` = the WHOLE bar, incl. pre-fill
        sStage := 1
```

Stage 1 sets the stop to `sEntry - beBuf` — for a short that is **below** the entry. A buy-stop
below the market is already through it, so TradingView converts it to a market order and every
`strategy.exit` leg fills together at the **next bar's open**. That open is the "price matching no
stop and no target".

It is not a rare edge case. On a shallow (0.5) entry TP1 is the very next fib (0.382), a couple of
dollars away, and the bar that rises into the 0.5 limit came from below it — so it very often has
already printed past 0.382 before the fill.

**The same contamination hit two more things**, both fixed in the same pass:
- `lMaxFav`/`sMaxFav` (the runner trail's high-water mark) was seeded from the entry bar's extreme.
- `_ext_high`/`_ext_low` (the MFE/MAE reporting pair) took the whole entry bar both ways.

### Confirmed on real bars

`VANTAGE_XAUUSD` 15m, 2025-09-09, chart time UTC-4:

| bar | open | high | low | close |
|---|---|---|---|---|
| 02:30 (entry) | 3638.66 | 3649.93 | **3637.80** | 3649.76 |
| 02:45 (exit)  | **3649.71** | 3649.99 | 3644.23 | 3647.57 |

The entry bar's low is 3637.80 — **ten dollars below the 3647.91 fill, all of it before the sell
limit was touched.** `sTP1` was 3645.21, so stage 1 fired on the entry bar. Stop → 3647.91 − 0.30
= 3647.61. The next bar opens above it and fills at the open. (The report's 3649.89 is the FX feed's
version of that 3649.71 — the original CSV is `FX_XAUUSD`, a different provider.)

Three independent checks agree: 1.98 pts ÷ 11.4 pts risk = **−0.174R** vs the reported −0.17R, and
87.5 × 1.98 = **$173** vs the reported $173.45.

It also nearly went one worse: `sTP2` was 3636.50 and the bar's low was 3637.80. Another $1.25 and
stage 2 would have installed the TP1-price floor — same instant exit, bigger gap.

### ⚠ The original report's item 4 was the thing that hid this

> *"Stop never staged. …favorable excursion = 0 means price never went below entry, so `sStage`
> stayed 0"*

Invalid inference. Excursion is measured from the entry **price**; `sStage` is advanced from the
**bar's** low. They are not the same number, and on a limit entry they are systematically
different. That deduction is what sent the investigation toward a TradingView emulator artifact
instead of the code.

---

## The fix

**The fill bar can no longer stage the stop.** Its exit orders are not live on it either (the
one-bar delay the whole emulator is built on), so nothing could have banked there — skipping it
makes staging consistent with that rule instead of contradicting it.

| where | change |
|---|---|
| all 5 strategy Pine files | the staging block is gated `and strategy.position_size[1] > 0` (mirror `< 0` for shorts) — "we were ALREADY in the position last bar", so this is not the fill bar |
| same | `lMaxFav := lEntry` / `sMaxFav := sEntry` (was `high` / `low`) |
| `execution.py` `step` | `_advance_stage` skipped when `opened` — the rest of Phase B still runs, so `px_stop` is still emitted on the entry bar and parity is unaffected |
| `execution.py` `step_secondary` | same rule on the 1m sniper (`filled_dir is None`) |
| `execution.py` `_open_position` | `_max_fav = fill_price`; excursion seeded **asymmetrically** |

Pine files touched: `mpc_strategy`, `mpc_strategy_export`, `mpc_b_leg_strategy`,
`mpc_b_leg_strategy_export`, `mpc_bos_strategy` — **four changed lines each, and ZERO new main-body
statements.** That last part is deliberate: this family already sits near Pine's statement cap
(CE10295), which is why the gate is written as a bare `position_size[1]` condition rather than the
helper bool it started as. Both export pairs re-diffed against their parents — identical up to the
split point, line-29/40 title only.

**The excursion asymmetry is deliberate and is the subtle half.** A buy limit fills on the way
down, so the entry bar's LOW is reached AFTER the fill and *is* a real adverse excursion; only its
HIGH is the approach. Seeding both flat threw away real information — caught by
`test_trade_records_favorable_and_adverse_excursion`, which is why that test exists.

**Deliberately NOT done: a "stop may never be placed through the market" clamp.** It would have
caught this on day one, but with the staging fixed the remaining wrong-side cases are legitimate
(price tags TP1 then closes back through breakeven in the same bar — you *should* be out). Adding
it would change real behaviour and would have to land in Pine too. Worth doing as its own change,
with its own measurement.

### Regression tests (`tests/test_execution.py`)

- `test_the_entry_bar_cannot_stage_the_stop` — the reference trade's shape; also asserts the bar
  *after* the fill still stages normally, so the rule is "not on the fill bar", not "never".
- `test_max_fav_starts_at_the_entry_price_not_the_entry_bars_extreme`
- `test_entry_bar_excursion_keeps_the_adverse_side_and_drops_the_favourable_one`

---

## Blast radius

Two real TradingView trade lists, grouped into positions (TV counts each exit rung as its own
"trade", so the raw row count is ~3× the position count):

| export | positions | 1-bar, all legs one price | exit within 2× the BE buffer of entry |
|---|---|---|---|
| 2026-07-25 | 125 | 24 (19%) | **11 (9%)** |
| 2026-07-27 | 162 | 37 (23%) | **20 (12%)** |

The right-hand column is unambiguous: the exit sits exactly $0.30 from the entry, which is
`execBeBufTk` × mintick. A genuine stop is a fib leg away, never 30 ticks.

**Measured exactly on lab run `d2ab68f9e884`** (XAUUSD 15m, 2020-01-01 → 2026-07-31, 165 trades,
`exec_risk_pct` 10, `exec_sl_level` 0.886, rungs 0/0):

| | trades |
|---|---|
| stop staged on the entry bar (wrong) | 44 |
| ...died on the very next bar | 33 |
| ...**killed at the breakeven stop — the bug** | **29** (15 "winners", 13 losers, 1 flat) |
| ...the other 4 hit their real stop — genuine losses | 4 |
| staged wrong but survived past bar 2 | 11 (all winners, +25.34R) |

**Those 29 trades are worth −0.57R out of the run's +101.68R.** The direct P&L cost is
approximately nothing, because they die within pennies of the entry. The damage is elsewhere:

1. **The stats are wrong.** 15 of the run's 105 "winners" made a few cents. True win rate is
   nearer 60% than 64%; average win and profit factor are both flattered.
2. **29 correct setups were shot before they could do anything.** That cost is real and was
   unmeasured until the re-run below.

⚠ **Removing the accidental breakeven stop is NOT free.** The bug was *protecting* some trades by
accident: without the premature breakeven they take their real 1R loss instead of a scratch. Judge
the fix on being correct, not on the P&L delta.

### The re-run — run `d2ab68f9e884`'s exact config, before vs after

|  | trades | W | L | flat | win% | sum R | net (compounded) |
|---|---|---|---|---|---|---|---|
| **before** | 165 | 105 | 59 | 1 | 63.6% | **+101.68R** | $3,031,404 |
| **after**  | 165 | 111 | 54 | 0 | 67.3% | **+112.43R** | $7,133,405 |

**All 165 entries are identical** — same setups, same bars, same fills. Not one trade was added or
removed, which is the strongest available evidence that the fix is confined to the stop.

**30 trades changed result: 18 better, 12 worse, net +10.75R.** The four biggest are trades the bug
had killed at breakeven that turn out to be real winners — 2025-05-30 (−0.07R → **+3.90R**),
2025-06-12 (+0.02R → **+2.98R**), 2020-05-08 (+0.21R → **+2.86R**), 2025-04-23 (−0.23R →
**+1.87R**). The 12 that got worse are mostly scratches becoming full −1.00R losses, exactly as
predicted.

⚠ **Read the R column, not the dollars.** $3.0M → $7.1M is compounding at 10% risk over 6.5 years
amplifying +10.75R; it is not a 2.4× better strategy. ⚠ **Max drawdown was NOT measured here** —
more trades now run to a full −1R, so it may well be worse. Re-run this in the lab properly before
quoting any risk number.

---

## Why the parity harness never caught it

`compare_strategy.py` was **green throughout**, because both sides had the bug, faithfully ported.
The harness compares Pine to Python; it cannot see a defect they share. Same standing lesson as the
unpinned-engine-input traps: **a green parity run says the two implementations agree, never that
either is right.**

---

## ✅ PARITY RE-VALIDATED 2026-08-01 on fresh post-fix exports

Both Pine parents pasted into TradingView, compiled, and exported over the **FULL history**. Both
gates green at every warmup from 100 up:

| gate | export | warmups | result |
|---|---|---|---|
| `compare_strategy.py` (A+) | `VANTAGE_XAUUSD, 15_fd236.csv`, **21,691 bars**, 2025-08-31 → 2026-07-31 | 100 / 200 / 500 / 1000 / 2000 | **exit 0** |
| `compare_bleg.py` (B-LEG) | `VANTAGE_XAUUSD, 15_1b2f3.csv`, **21,691 bars**, same window | 100 / 200 / 500 / 1000 / 2000 | **exit 0** |

No truncation warning on either, so the ~100-bar skip is genuine engine cold start rather than a
mask — the same standard every other green run in this repo is held to.

*(An earlier pair of PARTIAL exports the same day — `15_88f5a` / `15_21332`, ~6,340 warmup bars
missing each — were also green, at warmups 6337+ and 2000+ respectively. Superseded by the full
run above; kept here only because the partial run is what exposed the harness asymmetry below.)*

**`compare_strategy.py` had to be changed to run on a partial export at all, and the change is a
real fix worth keeping.** It *hard
refused* any truncated export (`return 2`) on the reasoning that Pine warmed on history the file
lacks. That is true for row 0 and false in general — `compare_bleg.py` has always handled the same
situation by replaying until the engine converges, and the two harnesses disagreeing about it was
itself a defect. It now WARNS and requires `--warmup >= the missing bars` instead of refusing.
`--debug-arm` still refuses: it diffs the `dbg_*` **bar indices**, which are chart-relative and
cannot be corrected for (the standing rule from the B-LEG harness bug).

### The bug's fingerprint is gone from the bars

Read straight off the decision stream, no inference needed: on the ENTRY BAR, is `px_stop` already
at breakeven (entry ± `execBeBufTk`) instead of the real SL?

| export | entries | stop at the real SL | **staged on the fill bar (bug)** |
|---|---|---|---|
| A+ **before** (2026-07-29, 21,494 bars) | 26 | 22 | **4** |
| A+ **after** (full history, 21,691 bars) | 27 | 27 | **0** |
| B-LEG **after** (full history) | 5 | 5 | **0** |

**All four affected candles are inside the new window**, so every one can be read before and after
on the same bar — this is the check the earlier partial export could not finish:

| candle | before | after |
|---|---|---|
| 2025-10-02 14:30 long @ 3842.65 | stop **$0.30** → died **1 bar** later, **−0.120R** | stop **$37.78** → ran **47 bars**, **+0.008R** |
| 2025-12-02 15:15 long @ 4195.95 | stop **$0.30** → 1 bar, −0.860R | stop **$9.09** → 1 bar, **−1.000R** |
| 2026-05-11 12:45 short @ 4700.45 | stop **$0.30** → 1 bar, +0.008R | stop **$37.42** → 3 bars, **−1.000R** |
| 2026-07-20 00:00 long @ 3984.17 | stop **$0.30** | stop **$17.17** — result **unchanged**, +0.859R |

Read that table honestly — it is the fix in miniature. One trade was killed for nothing and now
survives 47 bars. Two now take the real 1R loss the bug was hiding (2025-12-02 was already losing;
the old exit gapped past the breakeven stop rather than reaching the true SL, which is why −0.860R
was never the honest number). The fourth had the wrong stop, never went near it, and is identical.
**Three of the four get WORSE or stay flat. The fix is right anyway** — the point is that the exit
price now corresponds to an order the strategy actually placed.

⚠ **The B-LEG fork has zero affected entries in any window** — before OR after. Its TP1 is the
broken swing extreme, far further from the entry than the A+ ladder's next fib, so its fill bar
rarely reaches it. That is exposure, not proof: the fix there is verified by construction (the code
is identical to the A+) and by parity, not by a caught case.

---

## The residue — what still looks like this bug and is NOT

⚠ **This bug is fixed, but a similar-looking exit will keep appearing on the chart forever. It is a
BACKTEST LIMITATION, not a defect. Do not re-open this file for it.**

**The shape.** Price runs up, tags TP1, the ladder stages the stop to breakeven — and then price
closes back through breakeven **inside the same bar**. The stop only becomes live on the NEXT bar
(`calc_on_every_tick = false`, the one-bar delay the whole emulator is built on). By then it is
already behind the market, so it converts to a market order and fills at that bar's **open**, not
at the stop price.

**Why that is correct.** Being OUT is right — price genuinely traded through the stop. Only the exit
PRICE is imprecise, and only because a bar-replay tester checks orders once per bar while a real
broker watches every tick and would have filled at or near the stop.

Three things follow, and they are the reason it is left alone:

- It makes the backtest look **slightly worse than reality** — the safe direction to be wrong. Never
  "fix" it to improve a number.
- **Pine and Python behave identically**, so **parity is unaffected**. No `compare_*.py` will ever
  flag it, and that is not the harness failing.
- It is a **bar-mode** property. `fill_model="tick"` resolves the stop against real ticks and will
  legitimately disagree; that is the improvement, not drift.

**How to tell the two apart in one glance.** THIS bug put the stop at breakeven on the **entry bar**,
before the trade had gone anywhere — `px_stop` sits exactly `execBeBufTk` × mintick from the entry on
the fill bar itself. The residue only ever stages the stop **after** the trade has genuinely reached
TP1 on a later bar. Same exit shape, completely different cause.

Also see *Deliberately NOT done* above: the "a stop may never be placed through the market" clamp
would remove the residue, changes real behaviour, has to land in all five Pine files, and therefore
needs its own change and its own measurement.

The durable copy of this note lives in `strategies/python/mpc_sos_fade/CLAUDE.md` →
`### Wrong-side stop fills`, and it is summarised in the root `CLAUDE.md` "Never Do" list.

---

## What is still open

1. ~~Re-export and re-run both parity gates.~~ **DONE 2026-08-01 — see above.** For the record,
   against the *pre-fix* export `compare_strategy.py` diverged exactly as intended: 52 `px_stop`
   lines plus the 5 exits that follow, across 3 trades, and **zero** divergence in `px_dec_bits` /
   `px_edge` / `px_entry_price` / `px_stages` — the fix never touched entry logic.
2. **Re-baseline every published number.** 110.65R, Run 8's 43% → 53% run-capture, the whole
   `mpc_sos_fade_optimization.md` log and both `backtest/archive/` snapshots were all measured
   through this bug. The exit-ladder conclusions are the most exposed: the bug kills trades one bar
   after entry, before the ladder ever engages.
3. **`mpc_bos_strategy.pine`** got the same fix but has never been compiled or backtested, so
   nothing there is validated either way.
