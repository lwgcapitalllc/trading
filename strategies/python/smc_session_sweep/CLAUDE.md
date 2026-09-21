# CLAUDE.md — the session-sweep Python port

**Purpose:** the Python half of `strategies/tradingview/smc_session_sweep_strategy.pine`, and its
parity gate.
**Scope:** this package only. The strategy's RULES live in `docs/SMC_SESSION_SWEEP_SPEC.md`; its
history and the six flat runs live in `strategies/tradingview/notes/session_sweep_strategy.md`.
Neither is restated here.
**Status:** 🟡 **Parity GREEN 2026-09-20, and REGISTERED in the lab the same day — on a frame
condition, not unconditionally.** Read the condition before quoting anything.

---

## What exists, and what does not

| Stage | Artefact | State |
|---|---|---|
| 1 Spec | `docs/SMC_SESSION_SWEEP_SPEC.md` | ✅ |
| 2 Pine | `strategies/tradingview/smc_session_sweep_strategy.pine` | ✅ |
| 3 Export twin | `..._export.pine` | ✅ |
| 4 Real CSV | `exports/golden/VANTAGE_XAUUSD_M5_20597bars.csv` | ✅ taken 2026-09-20 |
| 5 Python port | `config.py`, `core.py`, `structure.py`, `levels.py`, `strategy.py` | ✅ **runs in the lab** |
| 6 Parity gate | `tools/compare_smc_session_sweep.py` | ✅ **exit 0** |

## The three-stream blocker, and how it was actually closed

The old note here said this strategy needed three bar streams (1m confirmation, 5m zones, 15m
direction) while the lab replays two, and that the only ways out were to teach `backtest/` a third
frame or to move the confirmation. **Neither was needed, and the reason is worth keeping:**

🔴 **A higher timeframe is recoverable from a lower one; a lower one is not recoverable from a
higher one.** Fifteen-minute bars are exactly three five-minute bars, so the direction stream is
REBUILT from the replayed frame through the canonical `engines/market_structure/` — and MEASURED
against the Pine's own column on 20,096 bars, exact after warm-up. The previous day's and week's
levels went the same way. So the strategy now runs off **ONE** bar stream, not three, and the lab
needed no new capability at all.

⚠ **What is left is the one direction the trick does not go.** The confirmation timeframe is read
off the replayed bars themselves, so:

* the **confirmation timeframe must EQUAL the replayed frame**, and
* the **direction timeframe must be a whole multiple of it**.

`SessionSweepStrategy` REFUSES by name when either fails, rather than quietly confirming on the
wrong frame and reporting a different strategy from the one the chart trades.

🔴 **So the SHIPPED config — confirmation on 1 minute — needs a 1-minute replay.** Running it on
5-minute bars means moving the confirmation to 5, which is a real strategy change: it needs its
own TradingView export and its own green gate before any number off it is believed. ⚠ **A
5-minute-confirmation run has already been done locally and produced 10 trades at −4.97R over the
3.5-month window. That figure is UNGATED at that config and must not be quoted as a result** — it
is evidence the wiring works, nothing more.

---

## The parity gate — what it PROVES and what it is silent about

```bash
python3 strategies/python/smc_session_sweep/tools/compare_smc_session_sweep.py
```

**Green**, 20,597 bars read, 18,497 compared, 10 trades on both sides. ⚠ **The warm-up floor is
2,100 bars and it is a floor rather than a taste** — the previous-week level cannot exist before a
full week has closed (2,016 bars at 5m), and comparing it inside that week reports a warm-up as a
defect. Before that change the gate was green at 100, 500, 1,000 and 2,000 with the levels fed, so
no cold-start divergence exists to mask.

**Proven:** sessions and the DST-aware pool, the sweep, the gap scan and its mitigation, the
eleven-code block ladder, both sides' entry/stop/distance/targets — armed AND refused — the
minimum-stop floor, position sizing, the order lifecycle, the exit ladder, and the R of every
closed trade.

✅ **The 15-minute direction stream and both previous-period levels are now DERIVED and compared,
not fed.** That is new on 2026-09-20 and it is most of the gate's new reach.

🔴 **Silent about ONE thing: the 1-minute confirmation stream.** `px_conf_*` is still fed, because
a 1-minute bar cannot be recovered from a 5-minute chart by any means. It comes from
`engines/market_structure/`, which carries its own gate; that file proves it and this one never
will. ⚠ **An export taken with the confirmation on 5 minutes would close this last hole**, and it
is the single most valuable thing a new export could do.

🔴 **FOUR features never ran in the window, so the gate says nothing about them**, and it prints
all four on every run: breakeven on an opposite shift, the time stop, the at-the-zone entry mode,
and the no-gap entry mode. Refusal codes 1, 5, 7 and 9 never fired either. ⚠ **Breakeven on an
opposite shift is one of the three rules added from the course in August to fix the missing
scratch exits** — it is the point of the August work and it is unverified.

**Proven red by mutation, 2026-09-20** (rule 12 — a test that has not gone red for the right
reason proves nothing): rounding the size instead of truncating it, resolving a same-bar
stop-and-target tie to the target, making a session window's end inclusive, and dropping the
untouched-gap filter each turned the gate red on the columns they should. ⚠ **Switching
breakeven-on-shift off left it GREEN** — which is how the coverage hole above was found rather
than assumed.

---

## The two defects the gate caught that nothing else would have

1. **The one-bar order delay was off by one.** The bar index advanced after the broker ran instead
   of before, so every order was live one bar late and the export's first fill never happened.
   Bar-for-bar green everywhere else; the only symptom was one missing trade.
2. **TradingView TRUNCATES position size to the venue's lot step; the port kept the full float.**
   82.4928 is sent as 82.4, never 82.5 — on every trade, in the direction of a larger position
   than the chart holds. ⚠ **A 0.1% relative tolerance in the comparator was hiding it**, which is
   an accommodation written to match the port rather than the Pine. Measured as a floor on all ten
   fills, and the column is now compared to a hundredth of a lot.

---

## Rules for anyone editing this package

- **Nothing goes in `config.py` without a Pine input behind it.** A field the export cannot carry
  is a field the gate can never check.
- **This config subclasses nothing.** Every parent default you do not re-declare arrives
  uninvited, and that is what killed the previous BOS port.
- **The two Pine files and this port move in the same commit**, or the gate is comparing two
  strategies.
- **`core.py` holds the Pine's OWN gap arithmetic, transcribed** — it is not a second engine, and
  `engines/fair_value_gaps/` stays canonical for anything that is not this gate.
- **Re-run the gate on the golden export before committing a change here**, and read the coverage
  table rather than the exit code.


## What was measured to make the streams derivable, so nobody re-guesses it

- **The higher-timeframe alignment.** A group's value becomes visible on the chart bar that CLOSES
  it; every earlier bar in the group carries the previous group's. Scored against the export:
  20,436 of 20,597 this way, 20,396 the other way — close enough to look right, and wrong on every
  group boundary, which is where the trades are.
- **The shift counter's ORIGIN differs and it is not a defect.** `request.security` runs over the
  symbol's FULL history, so the Pine's counter had already reached 3 at the export's first bar.
  Only the INCREMENT is ever read, so only the increment crosses the boundary or gets compared.
  Diffing the raw counter reports a constant offset of 3 as 20,096 failures.
- **The trading day rolls at 17:00 New York, not at midnight UTC.** Four boundaries were scored
  against the export's own previous-day columns: UTC day 8,531 of 20,597, New York calendar day
  2,136, **17:00 New York 20,321 — with every disagreement inside the first day.** The weekly
  boundary is the same clock and scores the same way, all disagreements inside the first week.
  ⚠ The UTC day is the obvious guess, looks identical on a chart, and is wrong on more than half
  the bars.
- **The streaming and batch derivations agree bar for bar** on all 20,597 bars, so the lab path
  and the gate path cannot drift apart. A test pins it.
