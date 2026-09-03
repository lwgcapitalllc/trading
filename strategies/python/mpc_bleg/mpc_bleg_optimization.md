# MPC B-LEG — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

🔴 **NO SWEEP HAS EVER BEEN RUN ON THIS BOT. This file is empty on purpose and says so rather
than not existing**, because an absent log and an unswept bot look identical from outside, and
the next person to ask *"has anyone tuned this?"* deserves an answer instead of a silence.

Standing rules for anything recorded here:

- **Score in R, never dollars.** Sizing risks a fixed percentage of equity, so dollars compound
  and a dollar ranking measures recency rather than edge.
- 🔴 **STATE THE OUT-OF-SAMPLE SPLIT BEFORE THE GRID RUNS.** This bot has ~50 trades. **A grid
  over 50 trades will find a winning combination whether or not one exists**, and the honest
  answer is likely to be *"not enough data"*. Deciding the split afterwards is how a sweep
  launders noise into a default.
- **Print the NEIGHBOURS of any winner**, and re-check it on both halves of the history. A
  setting that only works in one half is not a setting.
- **Every run carries a CONTROL row that must reproduce the shipped baseline exactly.** If the
  control has moved, the harness moved and no row in that run is readable.
- ⚠ **Do not buy trade count by loosening a rule.** `mpc_sos_fade_optimization.md` Run 12 and the
  root `CLAUDE.md` → *Trading Philosophy* both measured this: with one position slot an extra
  setup does not ADD to the book, it QUEUES in front of it, and the loosened runs displaced real
  trades worth more than they brought.
- **A result here is a measurement, not a default.** Adopting one means a commit across
  `config.py`, `strategies/tradingview/mpc_b_leg_strategy.pine` and its export, with the parity
  gate re-run green.

## Runs

*(none)*

## Open candidates — named, never measured

These are recorded so a future sweep starts from what is already known rather than from scratch.
**None of them has a number attached, and none may be quoted as though it did.**

| | candidate | why it is a candidate | why it is still open |
|---|---|---|---|
| 1 | **Dropping the "A+ has priority" gate** | Aaron's own note in the Pine tooltip calls this the first thing to try when tuning. The bot stands down on a side where the A+ setup is armed — faithful to the Pine fork — but the A+ never PLACES an order there, it just holds the priority. **When the two bots are stacked on one account the account layer re-does this arbitration anyway**, so the gate may be doing the same job twice. | Never measured. ⚠ Run SOLO the bot fires MORE legs without it, because no A+ position occupies the account — **that is correct and expected, not drift**, and a sweep must not read it as an improvement. |
| 2 | **Behaviour by market regime** | The 2021–2023 losing stretch and the 2024–2026 recovery could be regime or could be noise at n=50. | Never measured — the regime tag is reporting-only on this bot and touches no trade. **Genuinely open**, and the sample is too small for it to be settled by a grid. |

⚠ **Before opening either of these, read `strategies/python/mpc_extreme_leg/mpc_extreme_leg_optimization.md`
→ Run 11.** It is the worked example of the mistake most likely to be made here: a cut scored by
deleting rows from a finished result measures a strategy that could see the future, and it will
endorse almost any cut you propose.
