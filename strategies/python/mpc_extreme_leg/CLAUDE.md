# CLAUDE.md — MPC Extreme Leg (Python port)

**Purpose:** The Python side of `indicators/strategies/mpc_extreme_leg_strategy.pine` — the leg
that runs INTO the shift of structure, which is the move the A+ bot's setup begins after.
**Scope:** This package only. The strategy's design, its optimisation record and the evidence
behind each default live in `indicators/strategies/docs/mpc_extreme_leg_strategy.md`; the porting
process lives in `docs/STRATEGY_WORKFLOW.md`. Neither is restated here.
**Status:** 🔴 **STAGE 5 OF SIX. NO PARITY GATE HAS RUN.** Written 2026-09-01. It imports, it
replays, it registers in the lab — and until `tools/compare_extreme_leg.py` exits 0 on a real
export, every number it produces is a lab finding, not a measurement.
**Last reviewed:** 2026-09-01

---

## What is missing, and it is the only thing that matters

**Stage 4 — the CSV.** A human has to open `indicators/strategies/mpc_extreme_leg_strategy_export.pine`
on a XAUUSD **5-minute** chart and take *⋮ → Export chart data → Bar data and indicator values*.
Nothing here can do it. Then:

```bash
python3 strategies/python/mpc_extreme_leg/tools/compare_extreme_leg.py '<export>.csv' --warmup 1000
```

⚠ **A TRADE LIST IS NOT AN EXPORT and the tool refuses one** (exit 2). The first file handed to
this strategy was a trade list, which says two runs disagree and nothing about where. The twin
plots 62 per-bar columns so a disagreement lands on a named column at a named bar.

⚠ **The twin and the strategy are GENERATED FROM ONE BODY** by
`indicators/strategies/tools/build_extreme_leg.py`, so they cannot drift. Edit the generator, never
either `.pine`. The build asserts the bodies are identical apart from the title and the appended
export block.

---

## The one known disagreement left, and the two that were fixed

Found 2026-09-01 by diffing the Pine against the study that measured this strategy. Three root
causes; the port inherits only the first, and it was fixed on the Pine side.

| | What differed | Where it is now |
|---|---|---|
| **Session clocks** | The Pine read three fixed session strings with **no timezone**, so all three resolved in the symbol's EXCHANGE clock (New York). Two windows tracked no real session; the one labelled "London" was the New York session under a wrong name — its high and low equalled the house NY session's on **100.0%** of 38,747 M15 bars, while the other eight pairings agreed on 0.0–8.0%. | ✅ **FIXED IN THE PINE.** Each window now names its own city, matching `indicators/engines/mpc_assistant.pine` — which always passed the timezone — and `engines/sessions/`. |
| **When a sweep is stamped** | The study dates a sweep at the 15-minute bar's CLOSE; the strategy dates it on the 5-minute bar that crossed. The study's freshness window reaches 5–15 minutes further back. | ⚠ **STUDY ONLY.** This port runs the liquidity engine on the chart's own bars, so it stamps where the Pine does. Recorded in `backtest/tools/pre_sos_leg.py`. |
| **What freshness is counted in** | The study counts wall-clock MINUTES; the strategy counts BARS. They part company across a weekend. | ⚠ **STUDY ONLY.** This port counts bars. Same record. |

🔴 **THE CONSEQUENCE FOR EVERY NUMBER THIS STRATEGY HAS: the grid, the timeframe answer, the two
filters and the cost bill were all taken through the study, so they describe an arming rule
marginally LOOSER than the file being traded.** They are not wrong and they are not re-measured
here — the gate is what settles it.

⚠ **The session fix CHANGES WHAT THE STRATEGY TRADES.** It is a correction, not a tuning: the
direction was decided by the house standard and by the Pine's own parent, never by which clock made
more money. **Do not re-optimise around it** — picking a session clock for its P&L is picking a
result and calling it a rule.

---

## What this side does that the Pine does not, and why

🔴 **Pine's `na` is a float NaN here, not `None`.** Every refusal in the ladder is a comparison
against a value that may not exist — no swing, no average range for the first 49 bars. Pine reads
`na < 2.0` as false; Python's `None < 2.0` raises and `nan < 2.0` is **False**, the same answer for
the same reason with no guard anywhere. ⚠ **Adding an `isnan` check to any branch of
`_ladder` makes this side refuse where the chart does not** — there is a test that goes red on
exactly that. It is a parity device and nothing else; the repo's "no answer vs measured zero" rule
still uses `None`, which is why the sweep ages do.

🔴 **Refusal code 7 has no Pine counterpart, deliberately.** With no average range yet the stop is
`na`, every refusal above declines to fire, and the Pine reaches its entry call with an `na`
quantity. That is a warm-up bug, not a trade. This side refuses and records why, loudly, into the
blocked list — a divergence nobody can see is the worse half. It can only fire inside the ATR
warm-up, which every gate run excludes anyway.

⚠ **The 15-minute half instantiates the canonical structure engine a second time** rather than
copying it, and reads one private field (`_ext.ash` / `_ext.asl`) behind a guard, because the
public event stream fires on CHANGE and a target is a live STATE. Same call, same reason, as
`backtest/tools/pre_sos_leg.py`. A rename upstream fails on construction rather than scoring
nothing.

⚠ **A profile with `bid_ask_fills` on is REFUSED, not approximated.** That flag moves fills rather
than charging a cost, so honouring half of it would report a trade list neither model produces.

---

## Registering in the lab — and what running the scanner found

`LAB_STRATEGY` in `__init__.py` is the whole opt-in; the scanner imports the package and reads it.
MEASURED by actually calling `services.strategy_scanner._parse_python_package` on it rather than by
reading the dict and agreeing with it: **22 settings, 20 of them labelled from
`mpc_extreme_leg.meta.json`, 12 marked core, 4 steps, `display_under` honoured.**

🔴 **IT WAS 25 SETTINGS UNTIL THAT CALL, AND THREE OF THEM SHOULD NEVER HAVE BEEN THERE.** The
structure length, the 15-minute aggregation and the ATR length are HARDCODED in the Pine — no
input, therefore no `cfg_*` column, therefore nothing a parity gate could ever check. As config
fields each drew a row on the strategy page under its raw field name, and a run that moved one
would have diverged from the chart with nothing anywhere to say so. They are keyword arguments on
the strategy now: a test can pass one, the lab cannot see one. ⚠ **This is `config.py`'s own
opening rule catching `config.py`** — and the only reason it was caught is that the registration
was RUN. A dict that looks right is rule 7 exactly: a label is a claim about code somewhere else.

⚠ **The two remaining unlabelled settings are deliberate** — what a lot is worth and which
instrument. TradingView puts both on the Strategy Properties tab rather than in an input, so no
export column can carry them; the A+ bot exposes the same pair the same way.

## The tests, and what they are worth

```bash
python3 -m pytest strategies/python/mpc_extreme_leg/tests -q       # 42 tests
# ~2 min serial. Under the suite's own `-n auto --dist load` it MEASURED 24s on an idle machine and
# 52s on a busy one — quoted as a range because both readings are real and a single number here
# would be the tighter one, which is the reading nobody reproduces.
```

`tests/test_extreme_leg.py` — 30 hand-traced rules, ~2s. **Every one was watched RED, and each
docstring names the mutation that does it**, so the next reader can repeat it in ten seconds
instead of trusting a sentence.

`tests/test_compare_extreme_leg.py` — does the GATE work. 🔴 **It cannot prove Pine parity and must
never be read as if it did**: it builds a synthetic export from this side's own decisions and feeds
it back, so it only checks the gate's plumbing — column names, the two bit schemes, settings
decoding, row alignment — and that a disagreement is DETECTED AND NAMED. Each case moves one column
or flips one bit and asserts the gate fails and says which.

⚠ **The twenty column checks are ONE process, not twenty, and that is a stronger test rather than a
cheaper one.** Each case re-runs the strategy in a subprocess; twenty of those cost more wall clock
than everything else here put together, on a suite whose speed is a standing rule. Moving every
column at once also proves the gate's reporting is neither capped nor first-only, which a
per-column loop cannot show at all. Three columns keep an isolated case, one per KIND that fails
differently: a price carried through the whole ladder, a bit-packed column, and a refusal code.

🔴 **The fixture's WINDOW IS MEASURED, and the first version of it was wrong in the way this repo
keeps meeting.** Bars 0–6,000 of the cache contain armings and refusals but **not one accepted
setup**, so the test that raises the minimum-target setting passed against a gate that could not
have failed. Bars 12,000–20,000 carry 6 acceptances and refusal codes 0/1/3/6, and the fixture now
ASSERTS an acceptance, a refusal and an opened trade rather than hoping for them. Re-measure before
moving those numbers.

---

## What it does over the cached history — and what that is and is not

MEASURED 2026-09-01, 562,071 Vantage XAUUSD M5 bars (2018-09-14 → 2026-08-23), shipped defaults,
$10,000, 1% a trade:

```
178 trades   +97.4R   hit 50.6%   worst losing run 7.9R   every year positive
```

The study's tuned equivalent over the same window was **169 trades / +84.0R / worst run 7.9R**, so
the two land in the same place rather than in different places — which is the only claim this
comparison supports. ⚠ **It is NOT a validated result** (no gate), it predates the session fix
above, and it is not a reason to skip stage 4.

---

## Never do

- Quote a number from this package as a measurement before `compare_extreme_leg.py` exits 0.
- Allow a second concurrent position. Every result this strategy has was measured with one slot,
  and the reason a filter pays here is that refusing a setup genuinely buys the next one.
- Fork `engines/liquidity/` or `engines/sessions/` to make this side agree with a Pine. When they
  disagree, one of them is wrong and the gate says which — see the table above for how that went.
- Add a field to `ExtremeLegConfig` that has no Pine input behind it. No `cfg_*` column can carry
  it, so the gate would leave it at this side's default and never see a disagreement about it.
