# Instrument profiles — one SOS Fade, many markets

**Written 2026-09-17.** Aaron's ask: run SOS Fade on more instruments, starting with GBPJPY,
without carrying gold's tuning onto them and without a second copy of the strategy.

## The shape

`profiles.py` holds named parameter sets. A profile is instrument FACTS plus strategy
OVERRIDES on the shipped config. Nothing in `config.py` moved — the shipped defaults are the
gold configuration and every documented run, both live bots and the Pine parity gate reproduce
off them. `GOLD.build() == SosFadeConfig()` is checked, not assumed.

Four optimised versions of this strategy = four profiles over one engine. A logic fix lands
once. A failed instrument is a deleted profile, not a forked codebase.

## "Turn off the gold tuning" — what that could and could not honestly mean

39 fields were moved to their current values by measurements taken on XAUUSD. Git says only
**18** have a recoverable pre-tuning value. The other **21 were BORN TUNED** — introduced by an
optimisation commit, never having had an untuned state. There is no original to restore for
them and none is invented here.

The problem mostly dissolves rather than being solved: switching off the four features Aaron
asked for makes **20 of the 21** inert, because they are settings for machinery that is not
running. The one that would have stayed live is the time stop, switched off on the ground that
the feature did not exist at the original port, so absent IS its untuned state.

**`UNTUNED` has never been measured, on any instrument.** It is a defensible place to START a
walk-forward fit. It is not a configuration anyone should deploy, and its `status` field says so.

### Three things deliberately NOT reverted

- **Per-trade risk.** Original 10.0, current 5.0 — but that move was the account's risk-cap
  allocation, not a gold measurement. Reverting doubles risk on an unmeasured pair.
- **Stop level.** Original "1.0", current "0.886" — moved to match Aaron's own chart config, not
  by a sweep, so there is no fit to undo. ⚠ Still a choice made while looking at gold, and it
  sets the trade's R. Worth sweeping per instrument.
- **Minimum stop distance floor.** Its VALUE is a gold measurement, but the floor is a SAFETY
  guard: size is risk / stop distance, so a collapsing stop balloons the quantity. Turning it
  off in the name of being untuned removes the guard for that exact hazard. The value gets
  re-measured per instrument; the mode stays on meanwhile.

Two more were left alone because their "originals" were a shipped defect and a pre-bugfix
behaviour. Restoring a bug is not reverting a fit.

## GBPJPY — measured 2026-09-17, PU Prime demo 700152905

Tradeable, FULL mode, 0.01–100 lots, broker minimum stop 0. Spread median **0.015** over
956,001 stored ticks across 3 days, flat in every session except the 21:00 UTC rollover
(median 0.19, p99 0.31). Real M15 and M5 bars back to **at least** 2000-01-01.

⚠ "At least" is load-bearing. `backtest/data/history.py` returns its own `_SEARCH_FROM`
boundary when history reaches it, and then words the result as "no real bars before
2000-01-01" — asserting a measurement it did not make. **OPEN, small, and exactly rule 4.**

### Two things that do not behave like gold, and both change the strategy

1. **Swap is severely asymmetric: long +4.83, short -20.68 points per lot per night.** A long
   is PAID to hold; a short bleeds. Converted properly (see the currency bug below) that is
   **+$3.10 and -$13.25 per lot per night**, so at this strategy's ~4-day median hold a short
   pays about **$53/lot** against a long earning about **$12/lot**. Gold's short swap is a
   CREDIT — so a cost intuition carried over from gold is not merely wrong here, it is wrong
   with the sign flipped. Expect the fit to prefer longs. Aaron's call, 2026-09-17: run both
   directions and let it show, rather than constraining up front.
   ⚠ An earlier draft of this note read those points as DOLLARS and quoted $83 and $19. That
   was the very mistake the section below describes, made by hand.
2. **Point value is not constant.** Gold's 1.0 of price is always $1.00. Here it is
   yen-denominated and moves with USDJPY — `tick_value` read 0.6409188 per 0.001 tick on
   2026-09-17, about 640.92 per 1.0 of price per lot at that moment. **OPEN: a multi-year
   backtest cannot hold it fixed without mis-sizing every trade far from that rate.** Decide
   where the runner sources it before believing any result. Rule 15.

## 🔴 THE BLOCKER: the cost model has no currency conversion

**Commission IS measured now — $1.00 per lot per side, read off a real round trip on demo
700152905 on 2026-09-17 (2 deals, 0.02 lots, -$0.02), the same rate gold pays on this tier.**
That is not what stops the pair running.

`SwapModel.per_lot_per_night` computes `points * contract_size * 10**-digits` and its docstring
calls the result "account-currency". **It is not. It is the SYMBOL'S QUOTE CURRENCY.** Every
instrument this repo has ever priced is USD-quoted, so quote and account currency have always
been the same thing and the gap has never shown.

GBPJPY is quoted in yen. The model would return **483 and -2068** and the caller would spend
them as dollars — **overstating swap by 156x**, the USDJPY rate. Nothing in the path converts,
and nothing refuses either: the numbers are the right shape and plainly wrong.

⚠ **This is rule 15 exactly** — *ask what a value's UNIT is on each side of a boundary, and
which line converts it*. There is no such line. It is not GBPJPY-specific: any non-USD-quoted
instrument hits it, so it has to be fixed once, at the seam, before ANY of them can be priced.

⚠ **And the conversion is not a constant.** USDJPY moved from roughly 100 to 160 over the
window a backtest would replay. A fixed rate is wrong by up to 60% at the ends, in a cost that
compounds every night a position is held. The honest fix sources the rate per bar, the same way
`point_value` has to (the other open item above — they are the same problem, and fixing one
should fix both).

**Until that exists, a GBPJPY run must refuse.** It does.

## 🔴 THE SECOND BLOCKER: position sizing drops the point value entirely

Traced 2026-09-17 through the whole money path, and this one is worse than the swap bug.

Size is computed as `qty = equity * risk_pct / 100 / dist`, where `dist` is a price distance.
**The point value is not in that formula.** Risk is then booked as
`qty * dist * point_value` — so the dollars actually put at risk are
**the intended risk multiplied by the point value**.

Gold's point value is 1.0, so the two have always agreed and the omission has never once shown.
Any instrument whose point value is not 1.0 mis-sizes every trade by exactly that factor.

⚠ **R SURVIVES IT, WHICH IS WHY IT COULD SIT HERE UNSEEN.** P&L is
`(exit-entry) * dir * qty * point_value` and risk is `qty * dist * point_value`; the point value
and the quantity cancel in the ratio, so **R is algebraically immune to this bug** — proved by
substitution, not assumed. Every R figure this repo has ever quoted stays good. Dollars, lots,
dollar drawdown, the account risk cap and every per-lot cost do not.

⚠ **THE LIVE SIDE ALREADY GETS THIS RIGHT AND THE TWO WOULD DISAGREE.**
`algos/shared/order_sizing.py` sizes off the broker's own tick value, which is already in the
account's currency, and its module docstring was written anticipating exactly this pair: *"a
`point_value = 1.0` inherited from gold is wrong by a factor of ~150 (see the USDJPY test)."* So
live sizing is currency-correct and the backtest's is not — on GBPJPY the two would size the
same setup completely differently. That is a lab-vs-live divergence in the one number that
decides how much money is at stake.

**The fix is to fold the point value into the sizing formula**, mirroring what the live side
already does. At gold's 1.0 it is provably a no-op, so no existing result moves — but it is a
change to a LIVE strategy's sizing line and must be treated as one.

### A worked example of how easy this is to get wrong

The first draft of this file recorded GBPJPY's point value as **640.92** — the per-LOT figure.
`config.py` defines it **per UNIT**: gold's 1.0 is per ounce, not per 100-ounce lot. The right
value is `tick_value / (tick_size * contract_size)` = **0.006409188**, and the draft was
**100,000x** too large, in a field that multiplies straight into risk. Written into the very
file that was warning about rule 15.

## Why GBPJPY still refuses to run

Its `account_profile` names a key that does not exist in `backtest/fills.py`, on purpose, so a
run REFUSES rather than borrowing gold's costs. Commission for this pair is unmeasured: it
lands on a filled deal and this account has never traded it. See
`algos/notes/broker-cost-measurement.md`.

GBPUSD has no facts here at all yet — nobody has read its symbol info.
