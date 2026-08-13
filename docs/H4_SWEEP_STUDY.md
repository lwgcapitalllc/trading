# H4 Sweep Study — is there a continuation edge after an H4 high/low is taken?

**Status:** ✅ **CLOSED 2026-07-31 — the question was ASKED and ANSWERED, and the answer was NO.** Do not build the H4 sweep continuation bot. Kept as the record of why, so the idea is not re-proposed and re-measured. **A closed study is not an open task.**

**Asked:** 2026-07-31, Aaron. Build an H4 strategy off a sweep of an H4 high or low plus
continuation, using the H4 liquidity tracking already in `mpc_assistant.pine`.

**Answered:** 2026-07-31. **No — do not build the continuation bot.** Part 1 below.

**Re-opened the same day**, Aaron: *"I don't want the 1:2 for the H4 strategy. Figure out how I
can use it or even run it standalone to give me some type of profits. Don't fight it, work with
whatever edge H4 gives."* He was right and Part 1's "too thin to pay costs" conclusion was wrong —
not about the signal, about the geometry I tested it with. **Part 2 has a standalone config that
makes money.** Jump to *Part 2 — making the fade pay*.

**Tool:** `backtest/tools/h4_sweep_profile.py`. Runs off `backtest/cache/` alone (no MT5, no
VPS). Imports no `engines/` — a pure price-and-level measurement, so nothing here can inherit a
bug from the structure stack.

**Data:** cached Vantage `XAUUSD`, **12,392 H4 bars, 2018-07-24 → 2026-07-31** (7.9 years, the
broker's measured intraday floor), with the 186,027 M15 bars used to resolve fills inside each H4
candle. Normalised by ADR20 throughout — gold ran $1,200 → $4,100 in this window and raw dollars
would make every recent year look like the edge grew.

Reproduce:

```bash
command-center/backend/.venv/bin/python backtest/tools/h4_sweep_profile.py \
    --out backtest/reports/h4_sweep
```

---

## What was measured

Two level definitions, side by side, because guessing one up front is how a study gets a fitted
answer:

- **prev** — the previous H4 candle's high/low. This is what the indicator draws and what
  `engines/liquidity/` emits as `h4_high` / `h4_low`. Sweep rule is a bare wick through it, matching
  `SWEEP_HIGH` in `engines/liquidity/types.py`.
- **pivot** — an H4 swing pivot high/low (`--pivot-len` bars either side, Pine's `ta.pivothigh`
  tie-left/strict-right convention). Rarer, older, the level real stops rest on.

Three things per definition: the forward outcome at +1/+2/+4/+8 H4 bars against a control of
non-sweep bars; a blind trade from the sweep bar's close; and — the one that matters, because it is
the design Aaron picked — a **confirmed** trade using H4 for context and 15m for entry (acceptance
beyond the swept extreme within 16 M15 bars, resting limit at 0.5 of the displacement leg, stop at
the leg origin, 0.1%-of-price min-stop floor).

---

## Finding 1 — the prev-H4 level is a base rate, not a signal

**82.1% of all H4 bars sweep the previous candle's high or low.** That is not a rare liquidity
grab; it is what an H4 candle does. Every number about it has to be read against the control, and
the tool prints one on every row.

At +4 H4 bars the sweep set continued 31.0% of the time and reverted 30.2%. The control continued
30.1% and reverted 30.5%. **One percentage point.** MFE and MAE both rise together on sweep bars
(0.484 / 0.457 ADR vs the control's 0.467 / 0.459) — that is a volatility effect, not a direction.

The pivot definition fires on 13.3% of bars and separates no better: 31.9% vs 30.9% continued.

## Finding 2 — continuation does not survive the out-of-sample split

The confirmed trade, 2R target, net of a $0.30 round-trip cost:

| definition | n | exp R gross | 1st half (≤2021) | 2nd half (≥2022) | exp R net |
|---|---|---|---|---|---|
| prev | 2,002 | −0.007 | **−0.085** | **+0.051** | −0.075 |
| pivot | 254 | −0.002 | **−0.226** | **+0.187** | −0.055 |

**The sign flips between the halves on both definitions**, which is the same failure `mpc_bos`
Run 3/4 recorded — regime, not edge. And it is negative net of costs everywhere regardless. The
blind-entry version is worse still: −411R over 9,969 trades at 1R, and the **control beats it**
(+40.8R), i.e. bars that swept nothing continued better than bars that swept.

**Continuation is closed. Do not build it.**

## Finding 3 — the reversal IS real, and it is consistently the fade

The mirror trade — acceptance back through the sweep bar's far extreme, then the same limit —
is positive gross on both definitions and in **both halves**:

| definition | n | exp R gross | 1st half | 2nd half | med stop $ | exp R net |
|---|---|---|---|---|---|---|
| prev | 1,464 | +0.073 | +0.049 | +0.092 | $4.61 | **+0.001** |
| pivot | 145 | +0.210 | +0.334 | +0.091 | $5.75 | **+0.151** |

On 1,464 trades with a stable sign across halves, **+0.073R gross is signal, not noise.** This is
the first positive directional result in the study and it points at the FADE — which is what
`mpc_sos_fade` already does, and consistent with everything else in this repo.

**But the gross edge is roughly the size of the transaction cost.** A $4.61 stop against a $0.30
round trip is 6.5% of 1R, and it eats +0.073 down to +0.001. On the large-sample definition the
reversal is exactly breakeven.

## Finding 4 — the one net-positive cell does not replicate

That leaves the pivot definition's +0.151R net. It does not survive inspection:

- **The entry price is the fragile axis.** At retrace 0.5 it is net-positive at every pivot length
  tested (2/3/4/5 → +0.151 / +0.153 / +0.172 / +0.184, both halves positive). At **retrace 0.618
  the second half goes negative at every one of them** (−0.227 / −0.318 / −0.524 / −0.760). This
  is exactly the A+ Run 12 pattern — a result whose sign flips with the entry price.
- **It is the long side, on a market that tripled.** Splitting it: reversal after a LOW sweep
  (= long) is +0.243R net with both halves positive; reversal after a HIGH sweep (= short) is
  +0.077R net with the **second half at −0.066**. `mpc_bos` Run 3 flagged this exact confound —
  "longs work on a 3x bull market" is the regime talking.
- **The long skew does not replicate on the 10× larger sample.** On the prev definition the two
  sides are symmetric (+0.071 long / +0.074 gross short) and both are ~0 net. So the pivot long-side
  result is 65 trades of noise, not a discovered side.

---

## Verdict — Part 1

**Do not build the H4 sweep continuation bot.** Continuation carries no edge on this instrument at
this timeframe, and what looks like one flips sign between the halves.

**The H4 sweep does carry directional information, and it is the fade.** That finding is solid
(1,464 trades, stable across halves and across both level definitions). It is simply too small to
monetise as its own bot at a $4-6 stop against gold's round-trip cost.

Nothing was committed as a strategy. `backtest/tools/h4_sweep_profile.py` is the reusable artefact
— point it at another symbol or window and it re-answers the whole question.

### What the result actually argues for

**Use the H4 sweep as a confluence INPUT to the A+ bot, not as a new strategy.** The measured edge
is a fade of an H4 level; `mpc_sos_fade` is a fade with a real exit ladder, a min-stop guard, and
Pine parity already earned. A thin standalone edge and a proven strategy in the same direction is
an argument for a filter, not a sibling. It is also the cheap test: one A/B on the existing bot.

Two other routes exist if a standalone H4 bot is still wanted, both aimed at the cost problem
rather than at the signal:

1. **Make 1R bigger relative to cost.** The whole gap is a $0.30 cost against a $4-6 stop. A wider
   stop with a proportionally smaller target moves the same gross edge above the cost line.
2. **Harvest the runners.** This study exits at a fixed R multiple. Run 8 on the A+ bot showed the
   `"Structure + % ratchet"` trail moved the banked share of each run from 43% to 53% at identical
   drawdown. A fixed 2R ceiling is exactly the thing Run 9 proved caps what pays.

### Open items this raises

- **The A+ overlap question, again.** Anything built from this finding is a fade of a swept level,
  which is what the A+ bot trades. The standing overlap audit in the root `CLAUDE.md` applies before
  any two of them run together.
- **Gold only.** Every number here is XAUUSD, because that is what the cache holds. The tool takes
  `--symbol`; the same question on a non-trending instrument would separate the fade result from the
  bull-market confound properly.

---

# Part 2 — making the fade pay

**Tool:** `backtest/tools/h4_sweep_optimize.py`. It imports the event builder and the trade
simulator from `h4_sweep_profile.py` — one simulator, so a sweep result and a published study
number cannot drift apart. The refactor that created that shared `run_trade` was verified
byte-identical against the Part 1 report before anything new was measured.

## Where Part 1 went wrong

Part 1 measured the fade at ONE geometry and concluded the edge did not clear costs. Two of its
choices were doing the damage, and both were mine, not the market's:

1. **Every entry retrace tested (0.5 / 0.618 / 0.786) makes the stop SMALLER.** Risk is
   `leg × (1 − retrace)`, so the whole axis I searched pushed cost drag the wrong way on an edge
   whose only problem was cost. **Retrace 0.236 doubles 1R** — median stop $5.75 → **$10.34**, and
   cost drag **6.5% of 1R → 2.9%**.
2. **Every exit was a fixed R ceiling.** A+ Run 9 already measured that a hard TP costs 20%+ of net
   because a handful of trades carry the book. It transfers: the same events at a fixed 2R make
   +0.117 exp R, and as a runner **+0.409**. The ceiling was throwing away two thirds of the edge.

## The config

**H4 swing-pivot sweep, faded, entered on 15m, held as a runner.**

| lever | value |
|---|---|
| level | H4 swing pivot, **3 bars either side**, most recent unswept per side |
| event | price wicks through the live pivot level |
| confirmation | an M15 bar CLOSES back through the sweep bar's far extreme, within 16 M15 bars |
| entry | resting limit at **0.236** of the displacement leg (shallow — this is the 1R lever) |
| stop | the leg origin, with the **0.1%-of-price min-stop guard ON** |
| target | **none** — runner |
| trail | **1% of price**, ratcheting off the running extreme |
| give up | 48 H4 bars (8 days) |

Results, net of a $0.30 round-trip cost, 2018-07 → 2026-07:

| book | n | /yr | win % | exp R net | sum R | 1st half | 2nd half | equity @2% risk | max DD |
|---|---|---|---|---|---|---|---|---|---|
| both sides | 202 | 25 | 37 | +0.409 | +82.6 | +0.368 | +0.442 | **3.80x** | **20%** |
| **low sweeps only (long)** | 104 | 13 | 41 | **+1.005** | +104.5 | +0.829 | +1.155 | **6.04x** | **13%** |
| high sweeps only (short) | 98 | 12 | 32 | −0.224 | −21.9 | −0.146 | −0.285 | 0.63x | 40% |

## Why this is not one lucky cell

- **It holds across all five level definitions.** At this geometry, `prev`, `pivot2`, `pivot3`,
  `pivot4` and `pivot5` are ALL net-positive in both halves. The `prev` definition — 2,536 trades —
  is +0.097 exp R net with halves +0.072 / +0.115. That is a very large independent sample agreeing.
- **It is a plateau, not a spike.** 75 of 98 exit configurations are positive in both halves. The
  neighbouring cells to the chosen one all work; the result does not sit on a knife edge.
- **The horizon ladder was searched until it turned over** (4 → 8 → 12 → 24 → 36 → 48 → 72). It
  peaks at 36-48 and thins at 72, so the winner is not on the grid's edge.
- **The min-stop guard is live and binding.** Worst trade **−1.1R**. Part 1's collapsing-stop
  hazard (A+ Run 4, BOS Run 1) cannot reappear here.

## The two caveats that matter

**1. The short side loses consistently, and the long side is where all the money is.** The
per-year breakdown is the real test, because BOTH halves of 2018-2026 are the same gold bull
market and the half-split cannot see through that:

| | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| low sweeps (long), sum R | −0.2 | +4.0 | **+28.7** | +7.3 | +23.8 | +6.0 | +22.7 | +11.2 | +1.0 |
| high sweeps (short), sum R | +0.3 | −5.8 | −3.7 | +2.9 | −6.7 | +1.2 | −6.2 | −2.5 | −1.5 |

The long book is positive in **8 of 9 years**, including 2021 and 2022 — gold's flat-to-down
stretch off the Aug-2020 high. That is better than a pure bull-market artefact would look, and it
is the strongest argument that this is a real asymmetry. But it is still 13 trades a year on one
instrument that trended up throughout, and the honest statement is that **this study cannot
separate "fading swept lows works" from "gold goes up"**. Only another instrument can.

**2. Five trades carry 71% of the profit.** Best +25.4R, and the top five sum to +73.9R of the
+104.5R total. Same shape as the A+ bot (Run 9: 11 of 164 trades carried 106R of 109R), so it is
this repo's normal profile for a runner rather than a defect — but it means the expectancy has wide
error bars and **every signal must be taken**. Skipping trades discretionarily breaks it. Excluding
2020 entirely still leaves +75.8R over 92 trades (+0.824 exp R), so it does not rest on one year.

## Recommendation

**Build it, long-only, as a standalone bot** — `pivot3 · low sweep · limit 0.236 · leg stop ·
runner · 1% trail · 48-bar cap`. 13 trades a year at 41% win with a 13% drawdown fits the
"few high-quality setups" philosophy better than anything else measured in this repo, and the
trade count is genuinely additive rather than a queue: at ~13/yr it will rarely contend with the
A+ bot for the single position slot.

Before it goes live, in this order:

1. **Re-run on a second instrument.** This is the one open question that changes the answer. If the
   long-only skew is gold's drift, a second symbol shows it immediately. Needs a cache pull.
2. **The A+ overlap audit.** This fades a swept level and so does the A+ bot. Count the bars where
   both hold a position before either goes near a shared account.
3. **Tick-mode validation.** Every number here is bar-mode at a flat $0.30. Confirm the winner
   against real spread and slippage, per the standing "sweep in bar mode, validate in tick mode" rule.
4. **Then** the strategy package, the Pine port and the parity gate.
