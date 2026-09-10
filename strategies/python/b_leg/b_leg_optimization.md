# B-LEG — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

🔴 **THE FIRST SWEEP ON THIS BOT RAN 2026-09-07 AND IT IS RUN 1 BELOW.** Everything before that
date was a one-axis-at-a-time hand pass recorded in this package's own CLAUDE.md (2026-08-06,
two defaults moved) — real measurements, never a logged sweep, and made on a different broker.

⚠ **Read *The basis* before any row in this file.** Aaron's call, 2026-09-07: the sweep is
measured on **PU Prime demo ECN, account 700152905 — the terminal that is actually connected and
the account these bots trade.** Every earlier B-LEG figure in this repo was measured on **Vantage**
with a different symbol and a different history length, so **no number in this file may be compared
against one from before that date.**

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
- ⚠ **Do not buy trade count by loosening a rule.** `sos_fade_optimization.md` Run 12 and the
  root `CLAUDE.md` → *Trading Philosophy* both measured this: with one position slot an extra
  setup does not ADD to the book, it QUEUES in front of it, and the loosened runs displaced real
  trades worth more than they brought.
- **A result here is a measurement, not a default.** Adopting one means a commit across
  `config.py`, `strategies/tradingview/b_leg_strategy.pine` and its export, with the parity
  gate re-run green.

## The basis

Unless a run says otherwise:

| | |
|---|---|
| tooling | `backtest/tools/axis_sweep.py` |
| broker | **PU Prime demo ECN, account 700152905** — the attached terminal, and the account these bots trade |
| data | `XAUUSD.p`, **188,475 M15 bars**, first bar 2018-09-14 00:00, last 2026-09-04 20:45 |
| costs | **charged**: measured ECN spread 0.12, commission $1/side/lot, PU Prime swap |
| position slot | ONE |
| out-of-sample split | **IS before 2022-09-30, OOS from 2022-09-30** — declared before the first grid ran |

🔴 **THE SPLIT WAS STATED ON THE COMMAND LINE BEFORE ANY ROW RAN, AND THE TOOL REFUSES TO RUN
WITHOUT ONE.** It is the boundary the 2026-08-06 hand pass declared, reused deliberately so the
two passes describe the same halves — it is not a boundary chosen after looking at a grid.

⚠ **The swap is the lab's constant (−79.60 long / +30.25 short), not the 2026-09-02 live reading
(−80.54 / +32.67).** That gap was replayed both ways on the sibling bot and came to +0.09R against
a 15.06R run-to-run spread, and re-pricing it was deliberately refused — see
`backtest/CLAUDE.md` → `tools/swap_audit.py`. Named here so no row is quoted as though it used
today's rate.

## Runs

| # | Date | What was swept | Winner | Status |
|---|---|---|---|---|
| 1 | 2026-09-07 | 🔴 **THE FIRST SWEEP EVER RUN ON THIS BOT** — 8 settings moved ONE AT A TIME off the shipped defaults, 34 configurations, charged, on the account these bots trade | **NOT ONE VALUE BEAT THE SHIPPED SETTINGS.** Two settings turned out to be carrying the bot: the runner's trail method is worth **~24R** (the plain swing trail LOSES money, −3.09R at PF 0.92) and the time stop is worth **~6R** (off → +14.61R, always-on → +15.72R, shipped before-the-first-rung-only → +20.76R). The staleness window sits on top of its own plateau at the shipped 4 days. | ✅ **shipped CONFIRMED** |
| 2 | 2026-09-07 | **How much each exit rung BANKS** — 0/20/35/50% at each, the untested lever behind this package's own note that the runner banks exactly +1.00R and hands back everything above it | **BANKING AT THE FIRST RUNG LOSES, MONOTONICALLY: +20.76R → +18.86 → +17.43 → +16.00.** It buys win rate (30.2% → 42.2%) and pays in money, and the whole apparent benefit is in the FIRST half while the second collapses (+10.83R → +5.59R). The second rung moves **+0.44R across its entire range** with drawdown and win rate identical. | ✅ **shipped 0/0 CONFIRMED** |
| 3 | 2026-09-07 | **Is the second-rung stop floor a dead control?** All three of its values produced byte-identical books in Run 1 | **NO — IT IS REACHABLE AND MASKED.** Re-run with the trail pinned to "Fixed step" the three values separate hard: +16.78R / +15.36R / +12.35R. The shipped ratchet is already tighter than any of the three floors by the time that stage is reached. | **live, but inert under the shipped trail** |

### The control, and what to assert against it

**116 trades / +21.18R / PF 1.55 / maxDD −6.42R / 30.2% win / IS +10.36R / OOS +10.81R** (2026-09-10).
Pass it as `--expect-trades 116 --expect-r 21.18` to every future sweep on this basis.

🔴 **RUNS 1–3 WERE MEASURED AT +20.76R, WITH ADDING TO WINNERS INHERITED ON** — a mode this fork's
Pine cannot express, pinned OFF on 2026-09-10. Re-measured on the same basis in one run: with it on,
the old control reproduces exactly (116 / +20.76R / IS +9.93R / OOS +10.83R); off, it is the line
above. ⚠ **The grid was NOT re-run.** The adds moved the control 0.42R over 116 trades, far inside
the ±0.113R-a-trade error every conclusion below already allows for, so no ranking rests on them —
but every row's absolute R is the old basis. Re-run a row before quoting its total.

⚠ **IT IS NOT AN EDGE AND THE SWEEP DOES NOT MAKE IT ONE.** Average **+0.179R a trade against a
standard error of ±0.113R** — the threshold this tool prints is twice the error, and it is not
met. What the sweep establishes is that the settings are not the thing holding it back.

🔴 **THIS IS THE FIRST B-LEG MEASUREMENT TAKEN AFTER THE 2026-08-22 STRUCTURE FIX, AND EVERY
FIGURE IN THIS PACKAGE PREDATING THAT DATE DESCRIBES A BOT WITH THE DEFECT STILL IN IT.**
`f4b0410b` stopped the structure engine anchoring backwards onto a candle a break had just
rejected. It re-measured the SIBLING bot in its own commit message (159 / +142.18R →
158 / +140.71R) and **nobody re-measured this one** — on Vantage bars it moves B-LEG
**+23.28R → +20.91R on an unchanged 114 trades**, found by bisecting 196 commits. ⚠ **The
2026-08-06 free-book figure recorded in this package's CLAUDE.md (112 / +17.64R) does not
reproduce at its own commit either** — replaying `37039547` on those exact bars gives
**114 / +23.28R** — so that number came from a run whose settings nobody wrote down, and it may
not be used as a control by anybody.

### Run 1 — the grid

`backtest/tools/axis_sweep.py --strategy b_leg --symbol XAUUSD.p --server PUPrime_Demo
--start 2018-09-14 --end 2026-09-05 --split 2022-09-30 --profile puprime_ecn`

| setting | values, shipped in bold | sum R |
|---|---|---|
| days the stale setup keeps watching | 2 / 3 / **4** / 5 / 6 | +5.64 / +13.95 / **+20.76** / +18.53 / +18.26 |
| time stop, hours | 4 / 6 / **8** / 12 / 18 / 36 | +15.38 / +17.28 / **+20.76** / +19.65 / +22.29 / +18.93 |
| time stop, when it applies | Off / **before the first rung** / always | +14.61 / **+20.76** / +15.72 |
| runner trail method | fixed step / plain swing / **swing + ratchet** | +16.78 / **−3.09** / **+20.76** |
| runner ratchet step | 0.03 / **0.05** / 0.08 / 0.10 / 0.15 / 0.25 | +21.39 / **+20.76** / +20.22 / +17.97 / +18.75 / +21.98 |
| breakeven cushion, ticks | 0 / 10 / **30** / 60 / 100 | +20.05 / +20.29 / **+20.76** / +21.20 / +19.87 |
| second-rung stop floor | **first-rung price** / breakeven / one step behind | **all three +20.76** — see Run 3 |
| stand down when the sibling is armed | **on** / off | **both +20.76** — see below |

⚠ **THE 18-HOUR TIME STOP IS THE ONLY ROW THAT BEAT SHIPPED AND IT IS A COIN.** +22.29R against
+20.76R, with neighbours at 12h and 36h scoring +19.65R and +18.93R — a lone bump of 1.5R on a
116-trade book. **This is exactly the shape `extreme_leg_optimization.md` Run 3 refused**, and it
is refused here for the same reason: a hill and a spike look identical from the top.

⚠ **The ratchet step and the breakeven cushion move the whole book ~4R and ~1.3R with no shape.**
Neither axis is monotonic and neither peak has a slope leading to it. Nothing to adopt.

### 🔴 The "stand down when the sibling has a setup" gate changes NOTHING, and it is not broken

On/off produced identical books to the decimal — same 116 trades, same both halves. **It is
genuinely wired** (`Execution._armed`, via the sibling's arm flags) **and it can never bind**,
because the two bots have independently measured **ZERO same-side overlap in eight years**
(root `CLAUDE.md` → *Trading Philosophy*, re-measured 2026-09-02). The gate arbitrates a clash
that does not occur.

⚠ **This is the SECOND independent measurement agreeing.** The 2026-08-06 Vantage pass found
dropping it adds exactly one trade and that trade loses; here it adds none. **Two brokers, two
feeds, same answer.**

⚠ **Do not read "changes nothing" as "safe to delete."** It is faithful to this fork's Pine, so
removing it is a parity change for no measured gain — and the thing that makes it inert is a
property of the OTHER bot's entry rules, which are free to move.

### 🔴 A byte-identical row means "did not reach anything", and that is a QUESTION, not a result

Run 1 produced two settings whose every value gave an identical book. **They had opposite
explanations and nothing in the table distinguished them**: the sibling gate is unreachable in
practice, while the second-rung stop floor is reached and then overridden. Run 3 is what told
them apart — pin the thing suspected of masking, and see whether the setting wakes up.

**The standing rule: when an axis comes back flat to the decimal, find the line that consumes it
before writing down that it does not matter.** A setting that is masked TODAY starts deciding
trades the moment whatever masks it is changed, and a log saying "makes no difference" is what
the next person will read instead of measuring.

## Open candidates

These are recorded so a future sweep starts from what is already known rather than from scratch.

| | candidate | why it is a candidate | where it stands |
|---|---|---|---|
| 1 | **Dropping the "SOS Fade has priority" gate** | Aaron's own note in the Pine tooltip calls this the first thing to try when tuning. The bot stands down on a side where the SOS Fade setup is armed — faithful to the Pine fork — but the SOS Fade never PLACES an order there, it just holds the priority. **When the two bots are stacked on one account the account layer re-does this arbitration anyway**, so the gate may be doing the same job twice. | ✅ **CLOSED 2026-09-07 — it is worth nothing either way.** Run 1 gives a byte-identical book on and off; the 2026-08-06 Vantage pass gave one extra trade and it lost. **Two brokers, two feeds, same answer**, and the mechanism is known: zero same-side overlap between the two bots in eight years, so the gate arbitrates a clash that does not occur. ⚠ Inert is not deletable — it is faithful to this fork's Pine, and what makes it inert lives in the OTHER bot's entry rules. |
| 2 | **Behaviour by market regime** | The 2021–2023 losing stretch and the 2024–2026 recovery could be regime or could be noise. | **STILL OPEN, and no longer for the original reason.** The regime tag is reporting-only here and touches no trade, so there is nothing to sweep until a refusal is BUILT — the sibling bot shipped exactly that on 2026-09-02 and it is the one cut that has earned its place there. ⚠ The losing stretch this line was written about is not visible in the current book: both halves are now positive and nearly equal (+9.93R / +10.83R). **Re-derive the question before answering it.** |

⚠ **Before opening either of these, read `strategies/python/extreme_leg/extreme_leg_optimization.md`
→ Run 11.** It is the worked example of the mistake most likely to be made here: a cut scored by
deleting rows from a finished result measures a strategy that could see the future, and it will
endorse almost any cut you propose.
