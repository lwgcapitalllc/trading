Drive a strategy through the six stages in `docs/STRATEGY_WORKFLOW.md`, and refuse to skip the parity gate.

**Why this exists:** the numbers you want come from the Python side. TradingView is where the
truth lives. They are two different programs, and a Python number means nothing until they have
been proven to make the same decisions on the same candles.

That proof has been skipped twice and both times a full day of measurements was thrown away.
The previous BOS port was DELETED for producing an 82-configuration sweep nobody could check,
and `bos_sweep.py` was falsified by ONE Strategy Tester run the day it was written.

When the gate finally ran on the rebuilt BOS port, it went red on the first compared bar and
found **three real defects that 54 green unit tests could not see** — including one in the
comparison tool itself, which had been comparing a constant for its entire life.

---

## Do this

### 1. Report the stage table first

Read `docs/STRATEGY_WORKFLOW.md`. For the named strategy, check which artefacts exist on disk
and print the six-row table with a verdict per row. **Do this before any other work**, so we both
know what is real.

### 2. Name the blocker

If a stage is missing, say which one and what it blocks. In particular:

- **Stage 4 (a real CSV export) is the ONE stage only a human can do.** You have no TradingView
  session. If it is missing, say so plainly and stop — do not produce numbers instead.
- If stage 6 has never RUN, say "written, never run". That is a different thing from green, and
  the BOS port is the proof.

### 3. Build the missing stage — and check the config against the Pine field by field

When writing or reviewing a `config.py` that subclasses another strategy's config:

**Diff it against the Pine it claims to mirror, field by field. Never read the subclass.**
Every parent default you do not re-declare arrives uninvited, and the two that would have hurt
most on the BOS port were both added in the previous five days. `exec_fib_nearest` rests on a fib
the fork's Pine has no input for — so the export has no column and the gate would have blamed the
entry rule. `exec_secondary` needs a second bar stream the sweep cannot supply, so every sweep
would have refused outright.

**The reverse rule is as load-bearing: nothing may exist in the config without a Pine input
behind it.** A field the export cannot carry is a field the gate can never check. That is most of
why the old port died.

### 4. Run the gate, and run it at several warm-ups

```
python strategies/python/mpc_<name>/tools/compare_<name>.py --warmup 100
```

Then 500, 1000, 2000. A single warm-up can hide a cold-start divergence, and it can equally
report one that is genuine engine warm-up rather than a defect. Report the bar count compared.

### 5. Read the green before you trust it — this is the part that gets skipped

A green run says the two implementations AGREE. It does not say either is RIGHT, and it says
**nothing at all about a branch neither side entered.**

So report, every time:

- **How many bars were compared**, and over what window.
- **Which features were actually EXERCISED.** Print the block-code histogram. A guard that fired
  zero times in 21,897 bars was validated by nothing — one export ran a ten-cent stop floor on a
  $4,000 instrument and raised its block code zero times, green on a branch neither side entered.
- **How many trades closed** in the window. Arming evidence thousands of bars deep sits happily
  beside exit-ladder evidence six trades deep. Say which is which.
- **Which config bits were on.** Decode `cfg_bits` and state it. The Python must be configured
  FROM the export's own `cfg_*` columns, never from today's defaults — otherwise the two sides
  agree about a model neither had enabled.

### 6. Check the harness itself

The comparator is code, and it has been wrong:

- It read live state AFTER the replay, so every bar was diffed against the run's final value —
  a column that checked nothing while looking like it passed.
- It carried an accommodation written to match the PORT rather than the Pine. **A comparator that
  agrees with the thing it is checking is not a comparator.** Ask what each parity column is
  compared AGAINST.
- A column holding a Pine `bar_index` is export-window-relative. Diffing one raw is correct only
  by the accident of a full-history export.
- TradingView appends the still-forming live bar with its plotted series blank. Trim a trailing
  run; refuse a blank row in the middle.

### 7. Only then

Sweeps, optimizations and backtest numbers are trustworthy. Say so explicitly, with the caveat
from step 5 attached — *"green about the shipped defaults only"* is the honest headline when it
is true.
