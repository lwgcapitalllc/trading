# CLAUDE.md — the session-sweep Python port

**Purpose:** the Python half of `strategies/tradingview/smc_session_sweep_strategy.pine`, and its
parity gate.
**Scope:** this package only. The strategy's RULES live in `docs/SMC_SESSION_SWEEP_SPEC.md`; its
history and the six flat runs live in `strategies/tradingview/notes/session_sweep_strategy.md`.
Neither is restated here.
**Status:** 🟡 **Parity GREEN 2026-09-20 — and NOT runnable in the lab.** Read both halves of that
sentence before quoting anything.

---

## What exists, and what does not

| Stage | Artefact | State |
|---|---|---|
| 1 Spec | `docs/SMC_SESSION_SWEEP_SPEC.md` | ✅ |
| 2 Pine | `strategies/tradingview/smc_session_sweep_strategy.pine` | ✅ |
| 3 Export twin | `..._export.pine` | ✅ |
| 4 Real CSV | `exports/golden/VANTAGE_XAUUSD_M5_20597bars.csv` | ✅ taken 2026-09-20 |
| 5 Python port | `config.py`, `core.py` | 🟡 **the DECISION CORE only** |
| 6 Parity gate | `tools/compare_smc_session_sweep.py` | ✅ **exit 0** |

🔴 **There is no `LAB_STRATEGY` and that is deliberate, not an oversight.** Declaring one would
register a strategy in the lab that cannot replay, and an empty registry answering confidently is
rule 8. The blocker is real and is named below.

---

## The blocker: this strategy reads THREE bar streams and the lab replays two

The direction is a 15-minute structure read, the confirmation is a 1-minute structure read, and
the zone scan and the chart are 5-minute. `backtest/optimizer.run_sweep` replays ONE frame and
`run_dual` replays two. **So the lab cannot run this strategy as built**, and no sweep,
optimization or backtest number can come out of it yet.

⚠ **Switching the confirmation off does NOT drop the 1-minute stream.** Three other rules read it
with the confirmation off — cancel-on-an-opposite-shift, breakeven-on-an-opposite-shift, and the
chart marker. Dropping to two frames means moving the confirmation to 5-minute, which is a
STRATEGY change and needs its own export and its own gate.

**Two honest routes, and they are Aaron's call, not the agent's:**

1. Teach `backtest/` a third frame. Correct, reusable by any later three-stream strategy, larger.
2. Move the confirmation to the 5-minute. One input, measurable tomorrow, and it makes the bot a
   slightly different bot than the chart currently trades.

---

## The parity gate — what it PROVES and what it is silent about

```bash
python3 strategies/python/smc_session_sweep/tools/compare_smc_session_sweep.py --warmup 500
```

**Green at warm-ups 100, 500, 1000 and 2000**, 20,597 bars read, 10 trades on both sides at every
one. No cold-start divergence exists to mask.

**Proven:** sessions and the DST-aware pool, the sweep, the gap scan and its mitigation, the
eleven-code block ladder, both sides' entry/stop/distance/targets — armed AND refused — the
minimum-stop floor, position sizing, the order lifecycle, the exit ladder, and the R of every
closed trade.

🔴 **Silent about the two structure streams.** `px_dir` and `px_conf_*` are FED to the port from
the export's own columns, because a 1-minute bar cannot be recovered from a 5-minute chart. They
come from `engines/market_structure/`, which carries its own gate; that file proves them and this
one never will. The previous-day and previous-week levels are fed for the same reason.

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
