# RUN ANALYST — AI analysis of a backtest run

**Purpose:** Build plan for the "analyse this run" feature in the command-center lab.
**Scope:** The analysis layer only. It never changes a strategy, an engine, or a fill.
**Status:** PLAN — nothing built yet.
**Last reviewed:** 2026-07-26

---

## What you asked for

After a backtest finishes, you click an icon. You get a plain-English report that tells you:

- Which days, hours and sessions make money. Which lose money.
- Where the biggest winners come from. Where the biggest losers come from.
- Why it is happening.
- What to change: stop trading before the close, only trade one session, wait 45 minutes
  after the open, drop a filter, add a filter.
- What to stop doing.

---

## The one rule that makes this useful instead of dangerous

Slicing a backtest until a nice number appears is curve-fitting. It is the single most
common way traders destroy an edge. If we let an AI hunt for patterns in 300 trades it
will find twenty, and eighteen will be noise.

So the feature is built in three stages, and the third one is what makes it honest:

1. **FACTS** — Python computes the cuts. No AI. Same numbers every time.
2. **READ** — the AI reads only those numbers and writes the verdict in English.
3. **PROVE** — every suggestion is re-run as a real backtest and reported with its
   honest before/after. A suggestion that is not testable is not shown.

Stage 3 is the difference between a tool that helps and a tool that flatters you.

---

## Stage 1 — the fact pack (Python, deterministic)

New file: `backtest/analysis/factpack.py`.

It takes the run's trades plus the market context at each entry, and returns one small
JSON object. That object is the ONLY thing the AI ever sees.

### Cuts it computes

Every cut reports the same six numbers: trade count, net R, win rate, average win R,
average loss R, profit factor.

| Cut | Slices |
|---|---|
| Day of week | Mon–Fri |
| Hour of day | NY hour, 0–23 |
| Session | Asia / London / NY / off-session |
| Minutes since session open | 0–15, 15–45, 45–120, 120+ |
| Minutes to daily close | last 30 / last 60 / rest of day |
| Direction | long / short |
| Regime at entry | the five `engines/regime/` labels |
| HTF bias at entry | weekly and daily state |
| Cycle-fib zone at entry | discount / mid / premium |
| Arm source | sweep / divergence / both |
| Entry depth | which fib the limit rested at |
| Exit reason | TP1 / TP2 / runner / stop / breakeven / opposite-SOS |
| Trade duration | quartiles |
| Month and year | drift over time |

### Three extra blocks

- **Concentration** — how much of net profit comes from the top 5 trades, and what the
  curve looks like without them. An edge carried by three trades is not an edge.
- **The tail** — the 10 biggest winners and 10 biggest losers, each with its full context
  row. This is what answers "why is it happening".
- **Missed setups** — the legs that armed and never traded, and what blocked them.
  `backtest/tools/run_report.py` already produces this (`setups.csv`). It is the only
  place a blocked trade is countable, and it is where "add a filter" ideas come from.

### Sample-size guard

Every slice carries an `n` and a `reliable` flag. Below 30 trades a slice is marked
unreliable and the AI is instructed to say "not enough data" rather than draw a rule from
it. This is not optional — it is the guard against the AI inventing an hour-of-day rule
from four trades.

### What has to be built first

The lab's trade rows (`backtest/output.py`) carry price, P&L and exit reason, but no
market context. `run_report.py` already computes regime, session, NY hour and excursion
for the CLI report. Move that tagging into a shared module so both the CLI and the lab
path get it. Reporting-only — it can never move a trade.

---

## Stage 2 — the AI report

New file: `command-center/backend/services/run_analyst.py`.

It sends the fact pack to Claude with a fixed system prompt and gets back a structured
report. Nothing else is sent. The AI never sees raw trades, never sees code, never
guesses a number.

### Report shape

```
verdict          one paragraph: is this edge real, fragile, or noise
strengths        3-5 findings, each with the numbers behind it
weaknesses       3-5 findings, each with the numbers behind it
proposals[]      each: what to change, why, expected effect, the exact config change
watch_outs       what looks good but is probably noise, and why
```

### Hard rules in the prompt

- Every claim must quote a number from the fact pack. No number, no claim.
- Never use a slice flagged unreliable except to say the sample is too small.
- Every proposal must map to a config field the strategy ALREADY has. The strategy has
  many switchable levers (`execNoLateDay`, session gates, HTF bias requirements, arm
  sources, exit ladder). A proposal that needs new code is written as a note, not a
  proposal — it cannot be auto-tested.
- Rank proposals by how much of the loss they remove, not by how clever they are.

### Cost and caching

One report is a few thousand tokens. Cache it against the run id and hash of the fact
pack, so clicking the icon twice costs nothing and always says the same thing.

---

## Stage 3 — prove it (the part that matters)

New file: `command-center/backend/services/run_analyst_verify.py`.

Each proposal is a config diff. For each one:

1. Re-run the backtest with only that change, on the SAME window.
2. Re-run it again on data the original run never saw — earlier history, or a held-out
   slice. `backtest/data/history.py` measures the broker's real history floor, so we know
   how far back we can honestly go.
3. Report three numbers side by side: original, changed in-sample, changed out-of-sample.

A proposal that improves in-sample and dies out-of-sample is shown as **REJECTED — curve
fit**, in red, with its numbers. That row is worth more than any suggestion, because it
teaches the difference every time you use the feature.

The optimizer already replays fast (`backtest/optimizer.py` — 4 combos over 3 months in
9s), so testing 5 proposals is seconds, not hours. Run it in bar mode, then re-check the
survivors in tick mode with real costs.

---

## Stage 4 — the UI

- An icon on the run detail page. One click.
- A panel with four sections: Verdict, What works, What is broken, Proposals.
- Each proposal is a card: the change, the reason, the three-number proof, and an
  **Apply as a new run** button that clones the run with that config.
- Rejected proposals stay visible, collapsed, marked as curve fits.
- Heatmap for the day/hour grid — green and red, one glance.

---

## Build order

| Step | Work | Depends on |
|---|---|---|
| 1 | Shared context tagging (`regime`, session, NY hour, cycle zone) on every trade row | — |
| 2 | `factpack.py` + tests. Deterministic, no AI. | 1 |
| 3 | API endpoint returning the raw fact pack as JSON | 2 |
| 4 | UI: heatmap + tables off the fact pack, no AI yet | 3 |
| 5 | `run_analyst.py` — the AI report | 2 |
| 6 | `run_analyst_verify.py` — auto re-run each proposal | 5 |
| 7 | UI: proposal cards with the three-number proof | 6 |

Steps 1–4 are already useful on their own. If the AI layer is ever wrong or annoying, you
turn it off and still have the analysis. Build them in this order for that reason.

---

## My honest opinion, as the trading side of this

Four things I would tell you before you build it.

**One: the fact pack is worth more than the AI.** The numbers are what change your
decisions. The AI is a translator. Build the numbers first and you already have most of
the value.

**Two: expect the answer to be "trade less".** Almost every strategy analysis on a real
edge comes back with the same shape — a few hours and one or two conditions carry the
whole thing, and the rest is noise that costs commission. That answer is usually correct
and usually ignored, because cutting trades feels like cutting income. It is not.

**Three: the biggest single lever is not a time filter, it is the exit.** Your concentration
and excursion numbers will tell you whether you are leaving money on the table at the
runner or giving it back. That is one config change and it moves everything. Time filters
move less than people expect.

**Four: the "stop trading before the close" style of rule is the most over-fitted thing in
retail algo trading.** The daily-close block you already have (`execNoLateDay`) has a real
reason behind it — gap risk over the session break. Rules like "no trades after 14:00"
usually do not. Demand a mechanical reason for every time filter, not just a number. If
you cannot say WHY that hour is different, it is noise.

---

## What this is NOT

- Not a live trading advisor. It only reads finished backtests.
- Not an optimizer. The optimizer searches a grid; this explains one run.
- Not allowed to edit a strategy file. It proposes config diffs and re-runs them, nothing
  more.
