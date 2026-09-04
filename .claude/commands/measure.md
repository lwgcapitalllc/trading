Turn a claim into a measurement. No number gets written down without the command that produced it.

**Why this exists:** a plausible guess written into a doc is not a cheap placeholder. It is a
signpost, and a wrong one sends the next reader away from the thing they could have checked in
one command.

- *"The broker serves ~35 days of 1m data"* — never measured, false by eight years, written
  into three files as a fact. It made a feature look untestable when it was merely untested,
  and it cost three weeks.
- *"Swap is a fact about the symbol, so it is the same across a broker's tiers"* — written down
  as a named caveat in the morning, disproved the same day by one command. Two symbols on one
  account, same market to within 8 cents, swaps 8.5x apart.
- *"A shared run must close LOWER than the screen"* — a verification criterion written before
  the thing existed. The first real run closed HIGHER, with the cap working. That test would
  have condemned a correct implementation.

---

## The rule

**If you are about to write a number, a rate, a depth, a cost or a limit into code, a doc or a
message — either run the thing that produces it, or write "unmeasured" and name the command
that would settle it.** There is no third option, and "unmeasured" is an honest answer.

## Do this

### 1. State the claim as a question with a number for an answer

Not *"is the spread reasonable"* — *"what is the median XAUUSD spread on this account, over
what sample, in what unit"*.

### 2. Find or write the command

Prefer a tool that already exists. This repo has many:

- `algos/tools/broker_facts.py` — spread, swap, commission, stops level, symbol specs
- `backtest/tools/cost_tiers.py` — one real replay per cost tier
- `backtest/tools/jitter_audit.py` — run-to-run spread, so you know what is noise
- `backtest/tools/overlap_audit.py` — do two strategies hold at once
- `backtest/tools/run_report.py` — why a run made or lost money
- `strategies/python/*/tools/compare_*.py` — Pine↔Python parity
- `command-center/backend/scripts/` — backfills and re-derivations

If none fits, write one. A measurement you can re-run beats a number in a paragraph, because
the inputs move — the overlap audit's verdict went stale the day somebody changed three B-LEG
defaults, and nobody re-ran it for five days.

### 3. Run it and keep the raw output

Report: **the command, the sample size, the window, the unit, and the raw result.** A number
with no sample size is not a measurement.

### 4. Put both costs in ONE unit before comparing

Two costs quoted in different units are not comparable, and the one quoted in the unit you do
not think in is the one that hides. Gold spread is per OUNCE and commission is per LOT — they
differ by 100x, and the account that looked free was more than twice the price.

### 5. Ask whether the difference is bigger than the noise

Before calling a delta an edge, check it against this strategy's run-to-run spread — SOS Fade is
**sd 15.06R**, measured. A 1.16R gap is not an edge, and saying so is the finding. Say the
honest version: *"strictly cheaper at identical everything else"*, never *"worth 1.16R"*.

### 6. Cross-check that the tool drives the real thing

Reproduce a documented baseline with it. If `cost_tiers.py`'s free row reproduces the
documented +142.18R to the cent, the tool is driving the real strategy and not a third thing.
Without that, a clean-looking table is unfalsifiable.

⚠ **Size the probe so the answer clears the resolution of whatever reports it.** A commission
probe at 0.01 lots read "−$0.01 per side" — MT5's smallest non-zero cent, which is what every
rate from $0.50 to $1.49 prints. It looked like an answer and was a rounding floor.

⚠ **Refusing a trade is not subtraction.** With one position slot, a refused setup frees the
slot and the trade list reshuffles. Deleting rows from a finished list got the SIGN wrong
(+1.84R estimated, −1.84R replayed). Re-run the replay.

### 7. Write it down where it will be re-read

The number, its unit, its sample, its date, and the command. If it can go stale, say what
moves it and who has to re-run it — the re-run must be owned by whoever changes the INPUTS,
not by whoever wrote the conclusion.
