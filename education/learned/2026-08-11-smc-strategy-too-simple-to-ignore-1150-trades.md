---
source: https://youtu.be/lTrDQPVfJyI
title: This SMC Strategy Is Too Simple to Ignore (1,150+ Trades)
uploader: Lewis Kelly
duration: 21:12
watched: 2026-08-11
detail: balanced (89 frames, native captions)
focus: general
---

# This SMC Strategy Is Too Simple to Ignore (1,150+ Trades)

A five-step SMC trend-continuation model, walked through rule by rule and finished with one
live trade. The whole thing is a funnel for the presenter's paid indicator and playbook, but
the rules are stated plainly and he puts a real backtest dashboard on screen twice — which is
more than most videos of this kind do. Relevant to us because his **location** rule is a
session sweep rather than a fib retracement, and he says explicitly that he tested the fib
version and threw it out.

## The strategy — five steps

Stated as a sequence at [14:44]: direction → location → confirmation → point of interest →
targets. Shown as a London-session short; longs are the mirror.

**1. Direction — 15-minute swing structure only.** [00:29-02:07] Bearish = a series of lower
highs and lower lows; bullish = the inverse. A change of character flips the bias. He trades
in the direction of the M15 trend and nothing else. After a break of structure he wants to
sell the top of the pullback leg and target the lows.

**2. Location — sweep of the PREVIOUS session's high.** [11:55-12:22] This is the core claim.
In the **London** session he waits for the **Asian** session high to be taken, then looks for
shorts. In the **New York** session he waits for the **London** high to be taken, then looks
for shorts. He calls this session-dependency the single most useful thing he found for
answering "where in the range do I sell?"

**3. Confirmation — the 1-minute must flip to agree with the 15-minute.** [15:12-17:29] After
the sweep he drops to M1, which will be bullish (price is retracing up into his zone), and
waits for M1 structure to shift bearish — a change of character on the 1-minute. Only when
M15 and M1 are both bearish is the setup live. He names this discrepancy as the edge itself:
*"this is our edge right here, by finding this discrepancy."* Without it, he says, you sell
the moment Asia breaks and get run to the top of the move.

**4. Point of interest — 5-minute order block or fair value gap.** [18:11-19:52] He switches
to M5 and finds the nearest **untouched** OB or FVG above price. Already-tapped zones are
skipped ("they've been traded, they're no longer of interest"). Entry is a **sell limit** into
that zone. Stop goes **above the zone's high**. He is explicit that entering at the M1 change
of character instead would be a 1:2 trade, and the OB/FVG entry is what turns it into the
6R average.

**5. Targets — two liquidity levels.** [19:52-20:15] TP1 = **previous day's low**. TP2 =
**previous week's low**.

## The numbers, read off his dashboard

Two different dashboards are shown and **they are not the same book**. This matters, because
the title quotes one and the headline stats quote the other.

**This setup alone** — "London sweep Asia trend continuation", screen at [04:31]:

| | |
|---|---|
| Total trades | 230 |
| Win rate | 33.33% |
| Avg win/loss | **6.14** |
| Profit factor | 3.07 |
| Expectancy | $11,666 |
| Net P&L | $2,168,636 |
| Max drawdown | −$60,000 |
| Avg drawdown | −$18,987 |
| Window | ~03/2023 → 2025 |

**All his setups combined** — screen at [12:36], the source of the title's "1,150+":

| | |
|---|---|
| Total trades | 1,154 |
| Win rate | 32.84% |
| Avg win/loss | **3.93** |
| Profit factor | **1.92** |
| Expectancy | $5,883 |
| Net P&L | $5,941,897 |
| Max drawdown | **−$292,250** |
| Avg drawdown | −$45,792 |
| Window | ~01/2021 → 07/2025 |

So the "I lose 1, I win 6" line is the 230-trade subset. Across the full 1,154 trades the
figure is 3.93 and the profit factor nearly halves. He says there are "another five or six
variations" of the setup [12:47] — the aggregate is those variations diluting the one he
is teaching.

## He tested premium/discount and rejected it

[09:50-11:55], and it is the most useful ten minutes for us. His argument:

- A Fibonacci retracement is *"just a data collection that shows you the average pullback
  inside of a price range"* — plot 1,000 swing legs by how far they retraced and you get a
  bell curve centred somewhere around 50-60%.
- People see the fat middle of that curve and conclude 50-61.8% is where to trade. He says
  the distribution tells you what is *common*, not what is *tradeable*.
- When he ran his own tests using premium/discount as the location filter he was **still
  profitable, but took far fewer trades and skipped many good ones** purely for being below
  the 50% line.
- He replaced it with the session-sweep rule in step 2.

He does not publish the comparison, so this is his claim rather than a number we can check.

## Worth acting on

**His location rule is measurable here with engines we already have.** `engines/sessions/`
emits Asia/London/NY windows with running session high and low, and `engines/liquidity/`
already emits previous-day and previous-week highs and lows with sweep mitigation. So both
his step 2 (prior-session high swept) and his step 5 (PD low / PW low targets) are readable
today with no new engine. Testing "does an Asia-high-sweep gate change A+?" is a config and
a replay, not a build.

**It is a direct counter-claim to our entry model, from the opposite direction.** A+ enters at
a fib level of the frozen leg (0.5 for B-LEG, the four-rule model for A+). He is arguing the
fib level should not be the location filter at all — the session sweep should be, and the
zone (OB/FVG) picks the price. Note we have already measured this from our own side: Run 12
(2026-07-29) found deeper entries gave **fewer trades and less money**, and the 2026-08-02
rule-3 change measured a deeper entry costing fill rate. Neither of those tests the thing he
is actually proposing, which is replacing the retracement-depth filter with a session filter
and keeping the zone.

**The M15-direction + M1-confirmation shape is `exec_secondary` used differently.** We already
carry a 1-minute stream and a 1-minute structure flip — but we use it for a *re-entry after
the primary reached breakeven*. He uses the same flip as the *confirmation for the primary
entry itself*. Same data, different job. Our own measurement says the re-entry use dilutes
(eight trades in 7.9 years, average R/trade falling below baseline); it says nothing about
the confirmation use.

**The scratch-vs-win distinction he never makes.** He reports a 33% win rate against a 6.14
average win/loss. Our own 2026-08-01 finding was that a raw win rate hides scratches — 45 of
111 "winners" on one run made under a sixth of a typical loss. His 33% is probably clean given
the R multiple, but the dashboard cannot tell us.

## Not worth your time

**The one thing he insists is essential is the one thing he does not give you.** He spends
[02:07-07:12] arguing — correctly — that you cannot trade structure without mechanical rules
for what makes a swing high, a swing low, a break of structure and a change of character, and
that you must prove those rules with data. Then: *"I hired a team that built the algorithm"*,
and the rules themselves are behind the indicator. So the video tells you the five steps and
withholds the definitions that make step 1 reproducible. Ours are in
`engines/market_structure/`, Pine-parity validated, so this costs us nothing — but do not
expect to rebuild his model from this video.

**The sales pitch runs through the whole thing**, roughly seven mentions of the indicator and
playbook. Nothing after [20:43] is content.

**The b-roll.** Around two thirds of the video is a talking-head shot with the chart in a
small window or absent.

## Note on how this was watched

Scene-change frame selection landed almost entirely on the **talking-head cuts** and largely
missed the chart walkthrough, because a chart replay has few scene changes while a b-roll
edit has many. The two dashboard screens came through and carried the numbers, but the trade
mechanics in this note are from the transcript, not the frames. For a video that is mostly
one screen recording, `--start`/`--end` on the chart section is the better pass.
