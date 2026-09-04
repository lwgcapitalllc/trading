---
title: The M15 Intraday Bias Playbook
video: 01-m15-intraday-bias-playbook
status: done
---

# The M15 Intraday Bias Playbook

**Transcript:** [../transcripts/01-m15-intraday-bias-playbook.txt](../transcripts/01-m15-intraday-bias-playbook.txt)

## In one line
How to turn the M15 Intraday Bias model into a written playbook plus a tagging
system, so a year of backtesting produces data you can filter to find your best
setups and cut the ones that lose.

## Key pointers
- The real lesson isn't the setup — it's the **operating method**: write the
  rules, tag every variable, backtest, then let the data tell you what works.
- A **playbook** is a short list of principles you follow every time. The depth
  comes from **tags**, which let you slice the same trades many ways after.
- "**Let the data decide.**" Don't add or drop rules on a hunch — tag the
  variable, collect enough samples, then look. Removing what loses is the
  fastest way to more profit, faster than adding anything.
- Fewer, higher-quality trades beat more trades — more trades = more chances to
  make mistakes.

## Rules / mechanics
**The model:** pro-trend on M15 (external swing structure via the 3-candle
pullback), entered on a lower-timeframe confirmation.

Playbook checklist, in order:
1. **Bias (always):** must be pro-trend on M15. If not pro-trend, do nothing.
2. **Area of interest (required):** a strong point of interest **or** a session
   liquidity sweep (Asia/London). No AOI, no trade.
3. **Entry trigger:** an **M1 change of character or break of structure** aligned
   with the M15 bias.
4. **Entry object:** enter from an **M1–M5 order block or fair value gap** in
   that area (which one is contextual to the price action).

Management:
- **Breakeven:** if M1 breaks structure after entry **and** there's no reason for
  price to return (no M5 order block / FVG at your entry level), move stop to BE.
- **Stop loss:** below the protected structural low (longs) / above the protected
  high (shorts).
- **Take profit:** close half at **5R**, then scale out half of what's left at
  each structural level on the way (old Asia/London/NY highs as liquidity);
  close the final piece in full at the last target.

News:
- **Never trade** a session with **CPI, NFP, or FOMC** (the NY session).
- **Don't enter before** 8:30am **retail sales** or **core PCE**.

Refinement he added from data: after the CHoCH at your AOI and a displacement
that leaves an M5 FVG/OB, if the M1 makes a small pullback and continues, **keep
the entry at that level** — don't force yourself to wait for another CHoCH (that
rule used to make him miss the trade).

## The tagging system (the variables to test)
- **Setups — New York (5):** NY continuation from London POI · NY sweep of London
  · NY sweep of Asia · lull-sweep-London → NY continuation · lull-sweep-London →
  NY reversal. (The "lull" is the quiet 5–7am ET window.)
- **Setups — London (3):** London sweeps Asia · Frankfurt sweeps Asia → London
  continuation (with M1 CHoCH in Frankfurt) · Frankfurt sweeps Asia with the
  CHoCH occurring in London. (Frankfurt = midnight–2am ET, between Asia and
  London.)
- **Execution window:** London 2–3 / 3–4 / 4–5am · New York 7–8 / 8–9 / 9–10am.
- **Point of interest:** weak (failed to break a level) · strong (caused a break)
  · broad (large HTF cluster; trade after a sweep) · none (no-man's-land).
- **Trend phase:** change of character · trend confirmation (CHoCH + 1 BOS) ·
  trending (2+ BOS).
- **Structural flow:** pro-trend only (no internal) · counter-internal ·
  pro-internal.
- **Premium/discount:** yes/no — extra confluence, to be tested not assumed.
- **News tag:** closed for high-impact news · entered after news · held through
  moderate news · no news.
- **Session:** London / New York.

The payoff: your playbook might show a 40% win rate overall, but filtering by
these tags reveals one setup at 70% and another at 20% — that's how you find your
A+ setups and drop the dead weight.

## How it ties into the SMC engine
This is the human playbook our code implements. Direct mappings:
- **Bias / CHoCH / BOS / trend phase** → `engines/market_structure/` (the break
  events and swing structure the whole system reads).
- **Points of interest (order block / FVG)** → `engines/order_blocks/` and
  `engines/fair_value_gaps/`.
- **Session sweeps, kill zones, Asia/London/NY highs & lows** →
  `engines/sessions/` and `engines/liquidity/`.
- **News blackout rules (CPI/NFP/FOMC, retail sales, core PCE)** →
  `engines/news/`.
- The **setups and tags** are exactly the configs and grade inputs a strategy
  like `strategies/python/sos_fade/` would parameterize and split-test —
  same "let the data decide / find the A+ setup" logic as our grading work.

## Questions / follow-ups
- Which of the 8 setups do we already cover end-to-end in the engines, and which
  need work (e.g. Frankfurt/lull window detection in `sessions/`)?
- Can we reproduce his tag-and-filter backtest in our `backtest/` runner —
  tagging each simulated trade with these same variables for the same slice-and-
  filter analysis?
