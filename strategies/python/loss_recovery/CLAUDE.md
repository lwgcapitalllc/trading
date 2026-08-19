# CLAUDE.md — Loss Recovery

**Purpose:** After a strategy takes a real stop-out, take one counter-trade on the opposing
external CHoCH, secure the loss back at +1R, and trail the rest.
**Scope:** Signal + trade management + R accounting. No sizing in lots, no broker calls, no UI,
no structure detection of its own.
**Status:** 🔴 **LAB ONLY.** `enabled` defaults False. No Pine twin exists, so there is no
`compare_*.py` parity gate and there never will be until one is written. Nothing imports this
package outside its own tests and `backtest/tools/recovery_report.py`. It has never been traded.
**Last reviewed:** 2026-08-18 — built this session from Aaron's question "when I lose, can I get
back in the other way and win the loss back?"

---

## The rule

1. A primary trade takes a real stop-out (`r < -scratch_r`; a scratch is not a loss).
2. Wait for an **external CHoCH** on the same timeframe in the **opposite** direction. Median
   wait ~13 hours. No CHoCH, no trade — and `pending()` reports the losses still waiting.
3. Either direction. See *Why both directions* below; this is not a preference.
4. Enter at the **next bar's open** after the CHoCH bar closes.
5. Stop at the **far end of the break leg** — `bull_bos_low` / `bear_bos_high`. That distance is
   this trade's 1R.
6. Size at **25%** of a normal trade's risk.
7. At **+1R**, move the stop **to +1R**. The loss is now paid back and cannot be given away.
8. Then trail the stop to each new confirmed swing level. **No target.**
9. Hard close at 30 days — a backstop against swap, not a working rule.

---

## MEASURED

`python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14 --sweep`

XAUUSD M15, 186,910 bars, `mpc_sos_fade` at shipped defaults with `exec_secondary=False`,
warmup 1000, bar fills. **Both sides costed at `puprime_ecn`** — the live account's tier.

| | |
|---|---|
| Primary alone | 181 trades, gross +138.9R → net **+129.0R**, **1,913x** @10%, maxDD **48.8%** |
| Recovery | 62 trades, **+16.2R** at full size, **58%** win, 35 of 62 locked, median hold ~4 days |
| At 25% size | **2,772x** at **48.3%** drawdown — **1.53x** what the same drawdown buys on the risk dial |

**25% is two answers at once**: the largest size that does not raise drawdown above what the bot
already runs, *and* the peak of the efficiency curve. The curve is flat from 20% to 55% (1.53 →
1.48), so it is not a knife edge.

⚠ **Charging costs to the recovery leg and not to the primary is rule 11 broken, and it flips the
verdict.** Uncosted-primary-vs-costed-recovery said the risk dial won; costing both says the
recovery wins by 1.3–1.7x. The primary holds a median **0.3 days** and 100 of its 181 trades are
SHORTS, which gold pays a swap *credit* to hold — so it loses only 7% of gross to costs while the
recovery loses far more. The tool charges both and must keep doing so.

---

## 🔴 It does NOT reduce max drawdown. It buys RETURN.

**MEASURED 2026-08-19, and it is the first thing to say to anyone who reaches for this to make a
losing streak hurt less.** Max drawdown at 25% size is **48.3%** against the primary's **48.8%** —
unchanged. At 100% size it goes **UP**, to 57.2%. **There is no size at which this protects the
account.** The gain is 1,913x → 2,772x at the same drawdown, and that is the whole trade.

The intuition it defeats is a good one, so record why it fails rather than just that it does.
The hope is that a recovery trade fires mid-streak and shortens the hole. It DOES fire mid-streak
and it is not too slow — over 13 losing streaks (longest 4), **76% of recoveries resolved before
the next primary loss landed**, and every streak got a signal. The arithmetic is what kills it:
inside those streaks the recoveries put back **+0.75R** against **−16.4R** of losses they sat
between. **5%.**

⚠ It cannot be fixed by sizing up. A recovery is a quarter-size trade winning 58% of the time; at
full size it wins more R but its 42% of losses arrive at the exact moment the curve is already at
a local low, which is why the drawdown rises faster than the return. `backtest/tools/recovery_report.py --sweep`
prints both columns — read them together, never the balance alone.

**If the goal is a smaller drawdown, the lever is `exec_risk_pct`, not this module.**

---

## 🔴 It does not smooth the equity curve either — and this qualifies the 1.53x headline

**MEASURED 2026-08-19.** Max drawdown is one worst moment. Everything describing the REST of the
curve is flat or marginally worse:

| | primary alone | + recovery @25% |
|---|---|---|
| Max drawdown | 48.8% | **48.3%** |
| **Average** drawdown | 16.6% | **17.2%** |
| **Median** drawdown | 11.4% | **12.2%** |
| % of trades under water | 75% | **79%** |
| Longest time under water | 612d | **612d** |
| Losing months | 37 / 86 | 40 / 88 |
| Std dev of monthly R | 4.78R | 4.76R |
| **Monthly mean / std** | **0.314** | **0.318** |

Same cause as the drawdown answer: 62 extra trades losing 42% of the time, opening immediately
after a primary loss — i.e. while the curve is already below its high. More small dips, not fewer.

⚠ **One figure looks like smoothing and is not.** Per-trade R volatility falls 3.32R → 2.88R, but
that is DILUTION from adding quarter-size trades, not a steadier curve. Return per unit of that
volatility goes the other way: **0.215 → 0.190**. Never read a volatility drop without the return
that came with it.

🔴 **What this does to the 1.53x claim, stated plainly rather than left for the next reader to
find.** In R the module adds **+4.1R on top of +129.0R — about 3%.** That compounds to 45% more
money (1,913x → 2,772x) because the extra R lands early enough to lift everything after it. But
**monthly risk-adjusted return is unchanged (0.314 → 0.318).** So "1.53x better than the risk
dial" is true *at matched MAX drawdown*, and max drawdown is a single point on the curve. On every
broader measure it is a wash.

**The honest summary: this buys a small amount of extra R that happens to compound well. It is not
a better-behaved strategy, it does not protect the account, and it does not smooth the ride.** Say
that before quoting the balance.

⚠ **If a smoother curve is the goal, this is the wrong lever** — the ones that would move it are
fewer correlated positions or a second strategy on a different structure stream. See root
CLAUDE.md → *The overlap audit*.

---

## Why this is a package and not a flag on `mpc_sos_fade`

The trigger is "a primary trade lost", which every strategy in this repo can state. Wiring it to
one strategy's concrete `Trade` class would make the second consumer a rewrite, so the engine is
defined against the `LossEvent` **Protocol** (`dir`, `exit_index`, `r`).
`mpc_sos_fade.execution.Trade` satisfies it unchanged.

⚠ **`scaled_r`, never `r`.** A recovery trade is taken at a FRACTION of normal size, so `r` (its
outcome in its own risk units) and `scaled_r` (`r * risk_fraction`, what the account sees) are
different units. A journal adds up `scaled_r`. Booking `r` overstates the contribution 4x at the
default size — the same class of error as handing MT5 ounces where it wanted lots.

---

## Why both directions

**`both_directions=False` is the one FITTED choice available here, and it is off by default.**
"Longs only" was picked after seeing that longs beat shorts on this exact record.

The earlier finding that counter-shorts lose −11.8R was measured with a **10R target**, and that
was the wrong test: gold drifts up over this record, so a counter-short almost never travels ten
times its risk. Re-run with the lock-and-trail exit, counter-shorts are **−2.9R over 25 trades**
with no era pattern (−2.6R first half, −0.4R second) — noise around zero, not a losing edge. And
both directions together score **1.49x** against the risk dial where longs alone score **1.48x**.

The shorts are free, they lower the drawdown slightly (the two directions do not lose at the same
moments), and taking them removes the only fitted element in the rule. Take both.

---

## Why the exit is the whole thing

Four exits were measured on the same 62 trades, net of costs:

| Exit | Net | Win | Median hold | Swap |
|---|---|---|---|---|
| 10R target, unmanaged | +13.3R | 35% | 17d | −19.7R |
| Breakeven at +1R, then trail | +9.5R | 54% | 7d | −6.1R |
| **Lock +1R at +1R, then trail** | **+18.9R** | **70%** | **4d** | **−4.7R** |
| Trail from the start | +2.4R | 49% | 5d | −5.6R |

🔴 **The 10R version only worked in the 2022–26 gold run and its whole result was five trades** —
removing its best five sent it to −0.7R, and its first half lost 7.8R. Locking at +1R made
**+9.2R in the first half and +9.6R in the second**, and still nets +6.6R with its best five
deleted. The difference is what the trade has to ASK of the market: 10R needs a 10–24% gold move,
+1R needs price to travel one R — and 97% of losses do that within a month.

🔴 **Swap is why the time stop exists.** Gold costs **$79.60 per lot per night** to hold long on
`puprime_ecn` (triple on Wednesday) and pays **+$30.25** to hold short. The 10R version left
trades open for 130+ days and paid **−8.66R** of swap on one that made +1.25R — 77% of its gross
went to costs. With the lock-and-trail exit nothing reaches the cap, and 30 / 60 / 90 days all
return the identical number.

⚠ **Liquidity levels were tested as targets and they lose.** Because the structural stop is ~4x a
normal stop, the nearest PDH/PDL/session/swing level sits a median **0.13R** from entry and 91%
are inside a single R — banking there risks a full R to make a fraction of one. Best level-based
version made +6.4R against +49.3R for letting it run.

---

## Tests

`command-center/backend/.venv/bin/python -m pytest strategies/python/loss_recovery/tests/ -q`
→ **16 passed.**

🔴 **Every one was watched RED by a named mutation, and the harness earned its keep: 5 of the
first 15 were VACUOUS.** They passed against their own bugs. What the mutation pass found, kept
here because each is a general trap:

| Vacuous because | Fix |
|---|---|
| `if t.locked:` never entered — the counter-LONG fixture has no trade that reaches +1R | run the counter-SHORT set, and `assert locked` first |
| deleting the lock made the trade book MORE (+1.457 vs +1.000) — the swing trail rescued it | switch trailing OFF so the assertion is about the lock |
| `r >= -1` still holds when a mutation books +3R | assert the exit reason is in the closed set, and `r <= mfe` |
| `mfe >= r` is trivially true when every trade books exactly −1R | assert `mfe > 0` — the mutation leaves unarmed trades at 0.0 |
| re-running the SAME frame cannot fail (StructureEngine tolerates a re-feed), and real-then-FLAT cannot either (a second guard refuses it) | two DIFFERENT real slices |

⚠ **One assertion could not be made red at all and was replaced rather than kept.** Reordering
the stop check against the arm block returns **byte-identical** results over 2,400 real bars,
because no bar there both arms and stops. It is now a direct two-bar test of `_manage` where the
ordering is observable. **A test that cannot go red is decoration, and the honest move is to say
so in the docstring or delete it.**

⚠ **The price fixture is 2,400 REAL XAUUSD M15 bars** (`tests/fixture_xauusd_m15.csv`, committed
so the tests need no bar cache). Hand-built ramps and sawtooths were tried first and the canonical
structure engine emitted **zero** events on every one — pivot seeding plus 3-candle pullback
confirmation needs price action a straight line does not contain, and a fixture the engine cannot
read would have let every assertion pass on an empty list.

---

## What would have to happen before this trades

1. A Pine implementation and a green parity gate. **It cannot be bolted onto
   `mpc_strategy.pine`** — that file assumes one position at a time (`closedR` at line 3869,
   `openRiskUsd`, `netAtEntry` and 13 separate `strategy.position_size == 0` arming gates), so a
   concurrent recovery position makes the primary mis-grade its own trades. It needs a fork, the
   same shape as `mpc_b_leg_strategy.pine`.
2. `/live-safety`, in full.
3. **The account-level risk cap.** A recovery trade can open while a primary is still on — that
   is the point of it — and the live allocator that would refuse the second one does not exist
   (root CLAUDE.md → *Risk is budgeted per ACCOUNT*; `docs/LIVE_TRADING_PIPELINE.md` → G10).
4. Re-run `backtest/tools/overlap_audit.py`. This adds a third source of concurrent positions on
   one instrument off one structure stream, and that audit's conclusion is about today's config.

## Key paths

| | |
|---|---|
| `config.py` | every knob, with the measured default and why |
| `types.py` | `LossEvent` protocol, `RecoveryTrade`, `ArmedSignal` |
| `engine.py` | the state machine; consumes `engines/market_structure` public events only |
| `tests/` | 16 tests + the real-bar fixture |
| `backtest/tools/recovery_report.py` | the runner that produced every number above |
