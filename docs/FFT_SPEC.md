# FFT (First Fib Touch) — spec

**Stage 1 of `docs/STRATEGY_WORKFLOW.md`.** Rules with no discretion left in them.

**The idea in one line:** with the 15m and the 5m trending one way and the 1m pulling back against
them, the first time price comes back to the 61.8 of the 5m's first leg, buy it (or sell it) and
hold to the 38.2.

**Status:** spec written and the Python bot built 2026-09-21 (`strategies/python/fft/`); matched to
the study trade for trade (below). **Not deployed** — no instance config, never near a broker.
**Author:** the user's hand-traded setup; version 1 frozen in `backtest/notes/fft_ledger.md`
(→ *The game plan as it stands*), measured by `backtest/tools/fft_first_touch_study.py --v1`.
**Instrument / frames:** XAUUSD only. **1-minute bars**; the 5m and 15m bars are built in code from
them. Silver is out: it did not confirm (ledger → *Version 1 through real costs and on silver*).

🔴 **THIS STRATEGY HAS NO PINE STAGE, AND THAT IS A DECISION.** The user cannot export 1-minute data
from TradingView (2026-09-21), so stages 2–4 and the usual stage-6 gate cannot exist. The
replacement proof is under *How it is proven* below. A MetaTrader tester port was rejected: it would
be a second copy of the structure and fib engines in another language, which rule 21 forbids.

---

## The rules — version 1

Written as a buy. **A sell is the exact mirror and is part of the strategy.**

Everything is decided at the **close of a 1m bar**, for the **next** minute. The 5m and 15m are read
as of their **last closed** bar — never the one still forming.

### The engines — canonical, default indicator settings

| Frame | What runs | Setting |
|---|---|---|
| 1m | external structure | pivot length 15 |
| 5m | external structure, internal structure, the Structure ("FFT") fib | pivot length 15; the fib **adopts a more-extreme internal swing**, as MPC Jarvis draws it by default |
| 15m | external structure | pivot length 15 |

⚠ The existing strategies switch internal structure OFF, which switches the adoption off. **FFT
keeps it ON**, because the study and the students' indicator both have it on.

### A limit order rests for the next minute only when ALL of these hold

1. **5m trend is up** and the 5m fib is drawn as a buy fib.
2. **5m first leg:** no continuation BOS up since the 5m shift (SOS) that started this trend. The
   shift itself counts as zero.
3. **15m trend is up.**
4. **1m trend is down** as of the minute just closed.
5. **No 1m break up** (BOS or SOS) in any minute after the one that made the fib's 0.0 high.
6. **First touch:** the fib's 61.8 has not been touched on this leg. A touch **spends the leg even
   when a gate above was failing at the time**, exactly as the study counted it. One entry per leg
   (leg = fib direction + the fib's 1.0 anchor).
7. **The last closed 5m bar closed above the 61.8.**
8. **No new 0.0 high since that 5m close.** A 1m bar that makes one cancels the order until the next
   5m close redraws the fib.
9. **No market closure inside the leg:** no gap over 12 hours between two 1m bars, from the 0.0-high
   minute to now — and no order left resting into a weekend, or into an early-close holiday break.
   ⚠ A plain "tomorrow is a holiday" is NOT refused: the shared calendar marks Thanksgiving Day
   closed, but PU Prime trades it until ~13:00 New York (measured 2020-11-26).
10. **Flat:** no FFT position open. *(New versus the study. Measured 2026-09-21: it removes 0 of 157
    trades 2020–25 and 0 of 34 in the last year, because the median trade lasts about an hour.)*

### Entry, stop, target

- **Entry:** buy limit at the fib's 61.8. A minute that opens below it fills at the open.
- **A buy limit the bid touched and the ask did not keeps resting** until it fills or TP1 prints
  (only when fills are modelled on the bid and ask). The first touch still spends the leg.
- **Stop:** the fib's 1.0, fixed at the fill.
- **Target:** TP2, the fib's 38.2, fixed at the fill.
- **No management:** no break-even, no partials, no time stop. Both TP1 break-even and TP3 were
  measured worse (ledger → *Refinements*).
- **Weekends:** no forced exit. The study held 8 of 157 trades over a closure, and that is in its
  result. Rule 9 stops a new entry across one.
- **When one minute reaches both the stop and the target, it is a loss**, as the study counted it.

### Risk — the account's pool, first come first served (the user, 2026-09-21)

- **5% of balance per trade, the same as every other bot** (the user, 2026-09-21), risked from the
  61.8 to the 1.0. ⚠ What that means, stated once: the worst backtest drawdown was about 4R (~19% of
  the account at 5%), and planning for twice that is ~34%, against about +4R (~+20%) a year after
  costs. On the point estimates 5% is about a fifth of Kelly; at the low end of the win-rate
  estimate (two standard errors down) it is about full Kelly.
- **The account's 10% cap is not raised.** FFT joins the other bots under the same cap. Whichever bot
  fills first takes its share; an FFT order that would push open risk past 10% is refused outright,
  never shrunk. **Checked: this is already how the live order code and the Command Center work.**
  Shares that add up past the cap are allowed at assignment and settled trade by trade.

### Labelled, not a separate trade

- **A+ grade — these trades ARE taken**; they are already inside the checklist. The bot only tags
  whether a previous-day, session or 4-hour low was swept between the 0.0 high and the fill. The tag
  exists for one future decision: whether A+ deserves more size. Not yet: the sweep lifted the TP1
  hit rate, but to TP2 it was no better on 2020–25 (+0.16R vs +0.15R).
- **Second touch — a setting, default OFF, logged as "would have entered".** It was positive when
  flat (+0.21R), but it adds drawdown as fast as profit: 2020–25 return per drawdown 6.1 with it vs
  6.4 without. And it rests on 28 trades, 4 of them in the last year.

### Settings — every rule is one, so a change is a setting, not a rebuild

| Label | Default | Measured alternatives |
|---|---|---|
| Trade longs / Trade shorts | on / on | — |
| Structure pivot length | 15 | — |
| Fib adopts internal swings | on | — |
| Max 5m continuation BOS | 0 | 1, any |
| 15m trend must agree | on | off |
| 1m against, no 1m break | on | off |
| Skip a leg across a market closure | on | off |
| Stop level | 1.0 | 88.6 |
| Target | TP2 | TP1 |
| Trade the second touch when flat | off | on |
| Risk per trade % | 5.0 | — |

Sniper-zone entries, FVGs, sessions, kill zones, news and scale-in are **not** settings. They were
measured and did not help, or they need the forward log first.

---

## How it is proven — replacing the Pine gate

1. **The engines are already proven against the indicator.** The structure engine and the Structure
   fib pass their parity gates on Vantage XAUUSD 5m and 15m TradingView exports of MPC Jarvis. The
   bot imports them; it copies nothing.
2. **The bot against the study, trade by trade.** Two independent implementations of the same rule
   — the study's offline scan and the bot's minute-by-minute replay — run over PU Prime 1m,
   2020-01 → 2026-09. **Exit 0** when every study setup is matched at the same minute with the same
   levels and outcome, and every unmatched one has a named cause. This covers ~190 trades and
   ~3,000 first touches, far more than any TradingView export would have.
   **MEASURED 2026-09-21 — EXIT 0 on both windows:** 2020-01 → 2025-09 matched 157/157 trades,
   157/157 outcomes and 2,644/2,644 first touches; 2025-08 → 2026-09 matched 34/34, 34/34 and
   494/494. Through PU Prime ECN with bid/ask fills: **+0.149R a trade over 152 (2020-25)** against
   the ledger's +0.140R, and +0.136R over 34 in the last year. Getting there found three bot-side
   defects, all fixed: the extra-trade half of the gate (a mutation passed it), Sunday evenings
   refused as "closed", and an unfilled buy limit dropped instead of left resting.
3. **The user's chart check.** The 20 most recent bot trades are listed with time, side and levels,
   and the user confirms each on TradingView with MPC Jarvis. **Pass: all 20 read as FFT**, and any
   that don't get diagnosed before demo. This is the only step that checks the rule is *right*,
   rather than that two copies agree.
4. **On demo, live against replay.** Every decision the demo bot logs must match the lab replaying
   the same PU Prime bars. This catches feed and timing differences that no backtest can.

⚠ Steps 1 and 2 share the engines, so an engine defect would pass both. Step 3 is the check on that.

---

## The seven questions

**1. What I think was asked for.** A bot that trades exactly the version 1 checklist the students
get, on gold, and runs on demo. "First leg" means **zero 5m continuation BOS since the shift**. "1m
opposite" means **the 1m trend is against the trade and has not broken in the trade's direction
since the leg's extreme**.

**2. What it changes.** New files only:
- `strategies/python/fft/` (config, strategy, meta.json, tests, and the study-matching tool)
- an FFT row in the status table of `docs/STRATEGY_WORKFLOW.md`, recording the replaced gate

No stored number moves.

**3. What decides whether it worked.**
- **Step 2 above exits 0.**
- **Step 3 passes 20 of 20.**
- **After PU Prime ECN costs, the lab lands within noise of the ledger:** +0.140R a trade 2020–25
  and +0.165R over the last year.

**4. What would prove it wrong.**
- The lab, on the frozen rule after costs, averages **≤ 0R a trade on 2020–25** → the study measured
  something a bot cannot trade; stop.
- Or **more than 5% of the study's setups cannot be matched** for a named reason → the bot is not the
  setup; fix it before any demo.
- Or **the user rejects any of the 20 chart-checked trades** and it traces to the rule rather than a
  data difference → the rule is wrong in both copies; fix it before any demo.
- On demo: **fills that differ from the model** (buy limits missing by the spread more than the lab
  predicts). Demo checks the plumbing, not the edge. At ~2.3 trades a month only the forward log can
  test the edge.

**5. The alternative I am NOT doing.** A MetaTrader Strategy Tester port as the second
implementation. It would test on the broker's own ticks, but it means rewriting the structure and fib
engines in another language — a second implementation that drifts.

**6. What I am assuming.**
- **The live feed serves 1m bars.** Checked: it does.
- **Resting limit orders are supported live.** Checked: the order code has pending-order support
  and tests.
- **The account cap behaves as described under Risk.** Checked: the live order code refuses an order
  that does not fit, and the Command Center allows shares that add up past the cap.
- **The lab will not clip reopen spikes.** The study did (97 in 5.7 years). This is one source of
  named differences in step 2.

**7. Scope I am NOT touching.**
- Nothing under `algos/live/`, `engines/`, or any existing strategy or stored baseline.
- No Pine file.
- The deploy step comes last and is a separate yes.
