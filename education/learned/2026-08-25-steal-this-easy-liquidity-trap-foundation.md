---
source: https://youtu.be/DAnXM7C16h0
title: STEAL This EASY Liquidity TRAP Trading Strategy - $500K+ (PERFECT Sniper Entries)
uploader: Chart Fanatics (guest: Marco Aset / @marcotrades, Inter Equity Trading)
duration: 1:49:37
watched: 2026-08-25
detail: transcript
focus: the foundation video the spec was written from — what it actually says, in full
---

# STEAL This EASY Liquidity TRAP Trading Strategy — the foundation, finally on disk

**This is "video 1" in `docs/DAVINCI_MODEL_SPEC.md` — the episode that spec was written from, and
the only source in this folder that had NO note.** The spec was typed out of a chat session and
whatever landed there was the only surviving record. This note closes that.

Structure: ~35 minutes of whiteboard theory, ~30 minutes of chart examples (YM, EURUSD, NQ), then a
**live trade taken on camera** — an NQ long held for an hour and fifty minutes, closed at target for
about $6,400 across four accounts.

⚠ Roughly 8 minutes of the runtime is sponsor reads: [06:17], [18:27], [38:46], [61:44]. Skip them.

## The theory — what the spec got right

**[02:52–04:16] The primitive.** High respected, move away → liquidity above that high. Liquidity is
defined with no mysticism: *"liquidity is just resting orders in the market… usually the best
example would be stop losses."*

**[08:59] Why retail concepts matter.** *"They temporarily work. They work for good reason —
purposely, to induce liquidity into the market. If these concepts never worked, why would people
trade them?"* You need to understand break-of-structure, order blocks and fair-value gaps precisely
because they tell you where the stops are.

**[10:16] The hard filter, verbatim.** *"I will never look to take longs above the lows, only below.
Buy below lows, sell above highs."*

**[12:55] The counterfactual.** *"High taken, low respected, move away. People can say channel,
people can say trend line liquidity. At the end of the day, keep it simple — it's literally just
liquidity."*

## 🔴 What the spec MISSED, and it is a lot

### 1. THE ONE STRICT RULE — an absolute entry gate [24:23–25:49]

The trailer teases *"one strict rule"* and this is it. It is stated twice, both directions:

> *"If we are moving to the downside and I'm looking for a whole buy scenario to play out, if we get
> a move to the upside and we take out highs, **I will not buy this asset pair until this low is
> taken out.** It doesn't matter what happens anywhere between. Sometimes the market will come down
> and then just go long. **It doesn't matter. This is not a move I was supposed to be in.**"*

And at [57:19] on EURUSD: *"even if we didn't take out this low, it's not a move my system would have
allowed me to be in."*

⚠ **This is stronger than "never buy above the lows."** It names a specific low and refuses
everything until *that* one goes — including trades that would have won. The spec has no equivalent
and no scanner here enforces it.

### 2. Entries come from INTERNAL, targets are EXTERNAL [27:41–28:20]

> *"Usually I'm taking entries off internal liquidity being taken… and I'm targeting external. **Once
> external is taken, there's reversals that occur.**"*

A clean architecture statement, and it also warns that hitting the far target is where the reversal
risk starts.

### 3. 🔴 THE TIME WINDOW, at maximum force [49:21–49:55]

> *"For myself, what's helped me a lot is I have a specific time window, a specific time of the day
> I like to trade. **This is very overlooked in my opinion.** What people need to understand is
> **what happens outside of the time window is completely irrelevant to me.** Sure, I can wake up
> and London had a nice move. It doesn't matter. That's not my time window. It's not in my plan.
> It's not in my rules."*

His window is New York: stock open 9:30 ET, *"typically I'm looking for entries after the open"*, and
he is trying to be flat before the lunch hour *"typically dead in volume"* [105:50]. He also names
the reason it works: *"a lot of the time those optimum times you won't see a lot of chop"* [71:38].

**Nothing in the spec, the scanner or the handout has a session rule.** He calls it the most
overlooked part of his own method.

### 4. 🔴 THE NEWS RULE [67:13]

> *"Just like stock open, **I'll never enter before news.** I want to wait for the news to get
> released and I'm entering after. Usually typically 2 minutes, 3 minutes, 4 minutes."*

A blackout *before* and a deliberate entry *after*. `engines/news/` currently models a blackout only.

### 5. 🔴 THE STOP BUFFER — resolved, and it is instrument-dependent [68:32–69:12]

This is the answer to spec open question 4, and it explains why the two data points in this repo are
30× apart:

> *"The thing about forex is you're going to have to keep it **well above or well below**, because
> of spread, because there's different feeds, there's a little bit of manipulation. However on these
> charts [futures] everyone's trading from **one feed**. So yes, **I do keep mine literally like a
> tick or two above the high.**"*
> *"Stop covers this high always. I don't want to get greedy and get too low. Always above the high."*

**So: the stop sits immediately past the level, and the buffer is set by the instrument's spread and
feed quality — a tick or two on futures, materially wider on a forex or CFD product.** That
reconciles ~0.2 on 1-minute gold against the ~$6.5 ("50 pips") allowance in
[[2026-08-25-simple-liquidity-hack-you-need-to-learn]]. Combined with Ep. 2's *"the market dictates
how big my stop is"*, the whole stop question is now closed.

### 6. Execution is MARKET, not limit — and that contradicts the later video [46:16–46:48]

> *"I personally don't use limits too much. I just like to market execute… I came from a forex
> background, transitioned into futures. So forex, you have spread, **limits don't get tagged
> sometimes.** So I always wanted to avoid that."*

⚠ **In [[2026-08-25-simple-liquidity-hack-you-need-to-learn]] he sets a resting limit and goes to
bed.** Both are his. The difference is being awake, and the instrument. Do not code one as the rule.

### 7. Partials — he does take them, at levels, in size [47:27, 69:12, 105:50]

> *"I would partial here. Usually **50%, maybe 70% if I'm very confident in the higher time frame**,
> and then I'd hold the rest to the further target."*

But never at a number: *"I'm not looking to close at a specific R. A lot of people say I'll take a
partial at 1:3 or 1:5. **I always ask myself, why are you analyzing the chart at all?** If you're
partialling at a random RR point… it's completely random."* [33:25]

There is still a size floor — at [95:02] he refuses to pay himself on *"only a 140 tick move"*.
Consistent with the 1:1.6 refusal in Ep. 9.

### 8. Trade management, live and narrated [94:04–107:59]

- *"Stop is going to stay where it is. **I'm not going to roll it out of fear.** When the chart tells
  me to, I will."* [94:04]
- Then he does roll it, in stages, as each structural high is taken. [96:04], [97:44]
- Breakeven only once meaningfully in profit: *"there is no reason why I would want to see price back
  down to my entry. That'd be foolish to be this much in profit."* [98:40]
- **He manages on the clock**: *"timing is getting tough now, it's 11:15"*, *"I do want to be out of
  this before this lunch hour"*. [101:38], [105:50]
- *"Sometimes all it takes is taking the entry, setting your stop and a target. What happens in
  between is irrelevant. Don't let these candle closures make you get emotional."* [104:12]
- *"There's no ifs, ands, buts. I had targets in mind. If it doesn't reach it, then there's no
  profits and it is what it is."* [99:28]

### 9. 🔴 HE EXPLICITLY WARNS AGAINST TREATING HIS DIAGRAMS AS PATTERNS [12:16]

> *"I don't want it for people to view it as a pattern. This is just strictly for understanding,
> because **I don't want you guys to print out this diagram, go to your chart and just try to find
> this exact scenario, cuz it won't work like that.**"*

And again at [31:34]: *"I'm not a pattern trader. So I need to make sure there's logic."*

⚠ **`docs/teaching/MPC_Loaded_Level_Strategy.pdf` is a printable document built on four schematic
diagrams.** That is precisely the artefact he is warning about. It is not a reason to delete it —
but the warning belongs on the page, in his terms, and it is currently nowhere in the handout.

### 10. Other rules with no home yet

- **Liquidity voids: do not trade for days.** *"This big move has just occurred… all I can mark on is
  we've taken out this high, period. I don't see any other liquidity. So why would I be trading?"*
  [14:51]
- **Ranges: stay out.** *"We ranged quite heavily. This is where people screw up. If you learn how to
  stay out of price action like this, it'll avoid you a lot of losses."* [56:41]
- **Watchlist: two or three pairs while learning.** [35:50]
- **No correlation tools, no SMT, one chart.** *"Whatever chart is in front of me is the chart I'm
  trading."* [63:42]
- **The 5-minute is home.** *"This is usually the timeframe I'm hanging out on. Kind of a do-it-all
  timeframe."* [42:02]
- **Missed setups become future targets** — liquidity left behind gets run later, sometimes the next
  day, and often builds ahead of a scheduled release. [26:28]

## Worth acting on

1. **Rewrite the spec's source block and open questions.** Questions 4 and 9 are answered outright
   here; 2, 6 and 7 are answered across this and the four other unabsorbed videos.
2. **Add the strict rule as a hard gate.** It is the single most refusable rule in the model and
   nothing in this repo implements it.
3. **Add a session window and a news rule to the spec**, flagged as unmeasured. He names both as
   central; the scanner has neither, so every number it has produced is from a model missing them.
4. **Put the pattern warning in the handout**, in his words, on the diagram pages.
5. **Do not code entry as either market or limit** until the instrument split is settled.

## Not worth your time

The four sponsor reads at [06:17], [18:27], [38:46] and [61:44] — about 8 minutes total. The live
trade from [72:00] onward is long and slow, but the management commentary in the last 15 minutes is
the densest trade-management material in this folder; do not skip that part.
