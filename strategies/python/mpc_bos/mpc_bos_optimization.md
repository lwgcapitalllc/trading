# MPC BOS — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

🔴 **NO SWEEP HAS EVER BEEN RUN ON THIS BOT. This file is empty on purpose and says so rather
than not existing**, because an absent log and an unswept bot look identical from outside.

⚠ **READ THE PARITY COVERAGE BEFORE TUNING ANYTHING HERE.** This bot's gate is **narrow** — the
gap ladder never ran — so a branch the gate has never entered is not proven on either side. See
`strategies/python/mpc_bos/CLAUDE.md`. **Tuning a parameter whose branch no gate reaches moves
the Python away from a Pine nobody has checked it against.**

Standing rules for anything recorded here:

- **Score in R, never dollars.** Sizing risks a fixed percentage of equity, so dollars compound
  and a dollar ranking measures recency rather than edge.
- 🔴 **A cut is applied to the SETUP POOL, before any position-slot rule** — refusing a setup
  buys whatever came next. Scoring a cut by deleting rows from a finished result measures a
  strategy that could see the future. Worked example:
  `strategies/python/mpc_extreme_leg/mpc_extreme_leg_optimization.md` → Run 11, where a cut that
  looked free on the finished book cost 10R when it was actually run.
- **Print the NEIGHBOURS of any winner**, and re-check it on both halves of the history.
- **Every run carries a CONTROL row that must reproduce the shipped baseline exactly.**
- ⚠ **Do not buy trade count by loosening a rule** — root `CLAUDE.md` → *Trading Philosophy*.
- **A result here is a measurement, not a default.** Adopting one means a commit across
  `config.py`, `strategies/tradingview/mpc_bos_strategy.pine` and its export, with the parity
  gate re-run green — and, for this bot, **widening that gate first if the parameter's branch is
  one the gate has never entered.**

## Runs

*(none)*

## Open candidates

*(none recorded — nothing has been named as a tuning candidate for this bot.)*
