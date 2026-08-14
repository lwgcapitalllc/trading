# Broker questions — PU Prime account type for the live A+ bot

**Purpose:** The questions to put to PU Prime before funding a live account, why each one is
being asked, and what to do with the answer.
**Scope:** PU Prime, XAUUSD, the `mpc_sos_fade` A+ bot. Not a general broker checklist.
**Status:** Largely closed by measurement — **Q1, Q2, Q3 and Q5 are answered from our own terminals**
and nothing was ever sent to support. Q4 (swap-free) and Q6 (limit handling by tier) are still human
questions and are the only reason to send the message below.
**Recommendation, now MEASURED rather than quoted: the ECN account.** Same spread as Prime, same
swap, same minimum stop, and 3.5x cheaper commission — strictly better, with no trade-off to weigh.
**Evidence:** the 2026-08-10 section below; `docs/LIVE_TRADING_PIPELINE.md` → **G5a**.

---

## 🟢 2026-08-08 — QUESTION 3 IS ANSWERED BY MEASUREMENT: SWAP DOES NOT DIFFER BY TIER

This page was written on the premise that *"only a second account can measure Prime or ECN"*. Aaron
opened a demo of each tier, `MT5_Lab` was logged into all three in turn, and
`broker_facts.py --path/--account/--symbol` read each one (read-only, market shut).

| account | tier (per PU Prime's back office) | symbol | swap long | swap short | min stop |
|---|---|---|---|---|---|
| **700119432** | MT5 Standard | `XAUUSD.s` | **−79.60** | **+30.25** | 20 pts |
| **700152904** | MT5 Prime | `XAUUSD.p` | **−79.60** | **+30.25** | 20 pts |
| **700152905** | MT5 ECN | `XAUUSD.p` | **−79.60** | **+30.25** | 20 pts |

**Identical on all three, and identical to the live bot's account (700107749).** Contract 100 oz,
digits 2, rollover3days 3 everywhere. ✅ **`backtest/fills.py` now carries the measured swap on
`puprime_prime` and `puprime_ecn`** — they had been refusing (`UNMEASURED_SWAP`) since 2026-08-06.

⚠ **Read the shared constant in `fills.py` as "three reads that agreed", never as "Standard's
figure reused".** That distinction is the entire point of the sentinel, and the earlier refusal was
correct on the evidence available then — `XAUUSD.s` vs `XAUUSD.crp` really do differ 8.5x on ONE
account. Three tiers agreeing is a RESULT; it must not become the assumption. **`puprime_cent` is
still unread and still refuses**, which is what keeps the guard alive.

🔴 **THE SUFFIX IS THE TIER, AND THE 2026-08-06 CONCLUSION THAT IT WAS NOT IS NOW KNOWN WRONG.**
That reading — *"the suffix scheme across all 1,015 symbols is `.s` / `.24H` / `.crp` / no-suffix,
i.e. product lines rather than tiers"* — was taken from a **Standard** login, which is the one place
the evidence is invisible. `.s` is Standard and `.p` is the raw tiers, and **neither account can see
the other's symbol**: there is no `XAUUSD.p` on the Standard account at all. **A survey of what one
account can see is not a survey of the broker.**

🔴 **PRIME AND ECN ARE INDISTINGUISHABLE FROM THE TERMINAL — same symbol, same swap, same stops
level, same contract, byte for byte.** Nothing MT5 publishes separates them, including the
account-level fields (`company`, `leverage` — 500:1 on all three — `margin_mode`, both stop-out
levels). **The only difference is COMMISSION, and commission is not a symbol property**; it lands on
a filled deal and nowhere else. The tiers in the table above are read off **PU Prime's back office**,
which names them outright, not inferred from anything measured here.

⚠ **So question 2 is NOT retired and is now the one that decides the account.** If Prime and ECN
quote the same spread as well (Sunday will say), then commission is the only thing between them and
the cheaper one simply wins — which makes the published $1.00-vs-$3.50 contradiction, previously
worth ~1.2R and ignorable, the whole decision. ✅ **It is settleable without asking anyone: one
0.01-lot round turn on each demo, read back through `mt5_ops.get_deal_breakdown()`.**

⚠ **Spread is still UNMEASURED on every raw tier and the sentinel stays.** The only readings taken
were the last quotes before a Friday close — Standard 37 points, both raw tiers 17 — and **a stale
close-time quote is not a spread.** `broker_facts.py` deliberately reports nothing rather than
letting a repeated tick pass for a rock-steady spread, and a freshly-logged-in account has no local
tick store for `--history-days` either. **The spread half needs an open market** and wants each
terminal left logged in long enough to build a tick store. That 37-vs-17 gap points the right way
for a marked-up tier against a raw one, and it is not evidence.

### What is left

| | status |
|---|---|
| Q3 swap by tier | ✅ **measured — identical**, in `fills.py` |
| Q1 spread by tier | 🟡 **measured on an open market 2026-08-10 — Standard $0.31, Prime $0.12, ECN $0.12.** Five minutes each, so NOT yet in `fills.py` — see below |
| Q2 commission per lot per side | ✅ **measured — Prime $3.50, ECN $1.00** per side per standard lot |
| Q4 swap-free / Islamic | ❓ still a human question |
| Q5 min stop | ✅ measured — 20 points ($0.20) on all three |
| Q6 limit-order handling by tier | ❓ still a human question |

---

## 🟢 2026-08-10 — THE ANSWER IS **ECN**, AND IT IS NOW MEASURED RATHER THAN QUOTED

The market reopened, `MT5_Lab` was logged into each demo in turn, and every raw-tier reading was
**paired with a simultaneous Standard control** off the live `MT5_FFT` terminal. One terminal means
the three logins are sequential and gold's spread moves through a session, so without the control a
tier-to-tier gap could just as well have been a moment-to-moment one.

| tier | account | symbol | spread (median) | commission /side /lot | swap long / short | min stop |
|---|---|---|---|---|---|---|
| Standard | 700119432 | `XAUUSD.s` | **$0.31** | $0.00 | −79.60 / +30.25 | 20 pts |
| Prime | 700152904 | `XAUUSD.p` | **$0.12** | **$3.50** | −79.60 / +30.25 | 20 pts |
| **ECN** | 700152905 | `XAUUSD.p` | **$0.12** | **$1.00** | −79.60 / +30.25 | 20 pts |

The Standard control read $0.31–$0.32 through all three windows, ~280 fresh ticks per five-minute
sample, so the market held still while the tiers were compared.

**Prime and ECN are the same account with two commission rates.** Same symbol, same spread, same
swap, same stops level — so there is no trade-off to weigh and the cheaper toll simply wins. This is
the branch the 2026-08-08 entry predicted: *"if they quote the same spread, commission is the only
thing between them."*

✅ **Q2 was settled by FILLING something, because commission is not a symbol property.** One
0.10-lot round turn on each demo, read through `mt5_ops.get_deal_breakdown()`: booked on the entry
deal and the exit deal, identical long and short. **PU Prime's own account-types page was right and
the third-party breakdown that reversed the tiers was wrong.**

⚠ **The first probe used 0.01 lots and produced a number that was not a measurement.** It read
−$0.01 per side, which is MT5's smallest non-zero cent — every commission from $0.50 to $1.49 per
lot prints exactly that. **Size a cost probe so the charge clears the rounding floor**, or it
returns the confident-looking wrong answer rather than no answer.

**Replayed at the measured figures** — `backtest/tools/cost_tiers.py`, 155,531 M15 bars,
2020-01-01 → 2026-08-03, one real replay per row, `bid_ask_fills` for the spread:

| tier | trades | total R | vs free |
|---|---|---|---|
| free (no costs) | 159 | +142.18 | — |
| Standard ($0.32 measured, $0.00) | 156 | +141.87 | −0.31 |
| Prime ($0.12 stated, $3.50) | 157 | +150.23 | +8.05 |
| **ECN ($0.12 stated, $1.00)** | 157 | **+151.39** | +9.22 |

**ECN beats Standard by 9.5R and Prime by 1.16R over 6.5 years**, which is the same shape the
published-figure table produced and lands within 0.7R of it — so getting the real numbers moved the
magnitude and not the decision. ⚠ **The Prime↔ECN gap of 1.16R is far inside this strategy's
run-to-run spread of sd 15.06R**, so read it as *commission is nearly irrelevant and ECN is not
worse*, never as a measured 1.16R edge. The case for ECN rests on it being strictly cheaper at
identical everything else, not on that number.

⚠ **The spread is NOT in `backtest/fills.py` and the `SPREAD_UNMEASURED` sentinel stays.** Five
minutes of one quiet Asian session is not a spread — the $0.32 it is being compared against is a
median over 1,893,438 ticks across all 23 traded hours, and the only wide hour on this broker is the
22:00 UTC reopen, which these samples did not cover. Both raw tiers sat pinned at 11–12 points
throughout, flat enough to want that hour before trusting it. **Model it with
`cost_tiers.py --spread puprime_ecn=0.12`, which labels the row `stated` and touches nothing.**

**To close it:** log the idle `C:\MT5_Scalper` terminal into the ECN demo and leave it running — it
builds its own tick store without borrowing `MT5_Lab` back from the Vantage backtest feed — then
`broker_facts.py --path C:\MT5_Scalper\terminal64.exe --account 700152905 --symbol XAUUSD.p
--history-days 1` for the by-hour distribution.

### 2026-08-12 — the bot moved onto ECN, and the sentinel STAYS

Aaron put `MT5_FFT` itself on the ECN demo, so `MT5_Scalper` is no longer needed for this and the
tick store builds under the terminal the bot trades on. Read off it the same day:

| | 2026-08-10 (MT5_Lab, Asian session) | 2026-08-12 (MT5_FFT, London/NY overlap) |
|---|---|---|
| spread median | $0.12 | **$0.12** (239 fresh reads over 240s, p90 $0.12, p99 $0.12, max $0.15) |
| swap long / short | −79.60 / +30.25 | **−81.18 / +31.29** |
| stops level | 20 pts | 20 pts |
| digits / point / contract / tick value | — | 2 / 0.01 / 100 / $1.00 — identical to `XAUUSD.s` |

✅ **Two independent sessions on two terminals now agree on $0.12**, which is worth more than either
reading alone. ⚠ **It is still not a measurement and the sentinel stays**, for the reason above and
unchanged by the second sample: both are minutes of ONE session and neither covers the 22:00 UTC
reopen, the only wide hour this broker has. Close it with `--history-days 1` once a full day of
ticks has accumulated on this terminal.

🔴 **The swap MOVED 2% in two days** (−79.60 → −81.18, +30.25 → +31.29), in the same direction on
both sides. `backtest/fills.py` already carried the standing warning that swap is a rate rather than
a constant — it was 1.7%/2.6% adrift after three weeks in July — and this is the third reading to
confirm it. **Do not re-hardcode a swap without a date beside it.**

🔴 **Taking this reading found a defect in the tool.** The first run reported *"no fresh ticks -
market shut?"* after five minutes in the middle of the London/NY overlap: MT5 streams ticks only for
symbols in **Market Watch**, and the newly-switched account had never been asked to watch
`XAUUSD.p`. `symbol_info` needs no such thing, so the whole specification block above it read
correctly and only the measurement the tool exists for came back empty — wearing a sentence that
points at the exchange. Fixed in `algos/tools/broker_facts.py`: the sampler selects the symbol
first, and a tick that never ARRIVED is counted apart from a tick that never MOVED.

🔴 **Two live-path defects were found by taking these measurements, both now fixed** — see
`algos/CLAUDE.md`. A refused order logged `(1, 'Success')` because it reported the API call's health
instead of the order's, and `get_deal_breakdown` / `get_deal_result` bounded their history window
with `datetime.utcnow()` while MT5 stamps deals in SERVER time (+3h here), so **they returned empty
on every real fill and the cost measurement they were written for had never produced a reading.**
⚠ **That is the argument for probes like this one being run rather than reasoned about: both bugs
sat in code with green tests, and only placing an order surfaced them.**

---

## Why this is being asked at all

The choice was measured rather than reasoned, over 155,531 M15 bars (2020-01-01 → 2026-08-03),
one real replay per row. The short version:

- **Standard costs ~10R over 6.5 years** against either raw tier, because its **$0.32** spread
  stops **8 setups in 159** from ever filling. Every entry in this strategy is a resting limit, so
  a wider quote does not shave a few cents off a trade — it deletes the trade.
- **Commission is nearly irrelevant.** $1.00/side = 0.48R; $3.50/side = 1.67R, over the whole
  6.5 years. The entire commission question is worth about a fifth of the spread question.
- **Swap costs 6.60R — bigger than the gap between account types.** Nobody publishes whether it
  varies by tier. That is why question 3 matters more than questions 1 and 2.

🔴 **AND "SWAP IS THE SAME ACROSS A BROKER'S TIERS" WAS TESTED AND FAILS ON THIS BROKER'S OWN
PRODUCTS.** It was written here as a named assumption and disproved the same day with
`algos/tools/broker_facts.py --symbols`:

| on ONE account | swap long | swap short | spread | trade mode |
|---|---|---|---|---|
| `XAUUSD.s` | **−79.60** | **+30.25** | 0.320 (1,915,768 ticks) | FULL |
| `XAUUSD.crp` | **−9.35** | **+0.04** | 0.130 (708,565 ticks) | **DISABLED** |

Same market — median M15 close difference **$0.08** over 200 shared bars — quoted twice, **8.5x
apart on the long swap, with the short CREDIT gone entirely.** So swap is emphatically not safe to
assume shared, and the raw tiers now REFUSE it as well as the spread.

⚠ **`XAUUSD.crp` is DISABLED and is therefore not a cheaper way to trade** — it is the evidence,
not an opportunity. ⚠ **The terminal cannot answer the tier question either way**: the suffix
scheme across all 1,015 symbols is `.s` / `.24H` / `.crp` / no-suffix, i.e. product lines rather
than tiers. **Only a second account can measure Prime or ECN** — which is what makes question 3 the
one to press.

⚠ **Only the $0.32 is ours.** It is measured off the live terminal (1,893,438 ticks,
`algos/tools/broker_facts.py`) on a **Standard** demo. Every Prime and ECN figure below came off a
marketing page, and **the published sources contradict each other** — PU Prime's own account-types
page puts ECN at $1.00/side and Prime at $3.50/side, while a third-party breakdown reverses it. The
replay deliberately spans that whole range, so the conflict does not change the recommendation. It
does mean **the numbers in the questions below are the ones to get confirmed, not quoted back.**

---

## The message to send

> **Subject: XAUUSD trading costs — Standard vs Prime vs ECN**
>
> Hi,
>
> I run an automated strategy on XAUUSD through MT5 and I'm choosing between the Standard, Prime
> and ECN accounts. Minimum deposit is not a constraint for me. Could you give me exact figures
> for the following?
>
> **1.** Typical average spread on **XAUUSD**, quoted in US dollars or in points, for each of
> Standard, Prime and ECN. I've measured about **$0.32** on my Standard demo, so what I'm after is
> the comparable figure for the other two — a "from 0.0 pips" headline doesn't tell me what gold
> actually trades at.
>
> **2.** Commission **per side, per standard lot, on XAUUSD specifically**, for Prime and for ECN.
> I've seen both $1.00 and $3.50 quoted for both tiers on different pages, so I'd like it confirmed
> for gold rather than for FX majors.
>
> **3.** Do **XAUUSD swap rates differ between account types?** My demo currently shows −79.60
> long and +30.25 short, per lot per night. If those change by tier, please give the figures for
> each one.
>
> **4.** For the **swap-free (Islamic) option**: what is the administration fee on XAUUSD per lot
> per night, and does it also remove the **positive short-side swap**?
>
> **5.** **Minimum stop distance and freeze level** on XAUUSD, for each tier.
>
> **6.** My strategy enters **exclusively with resting limit orders**. Does the handling of pending
> limit orders differ between the tiers in any way — execution model, partial fills, or requotes?
>
> Thanks.

---

## What each answer changes

| # | If the answer is… | Then |
|---|---|---|
| **1** | Prime and ECN quote the same gold spread | Take **ECN** and pay the lower commission — same spread, cheaper toll, strictly better. |
| **1** | One tier is genuinely tighter on gold | Take that one and **ignore the commission difference entirely**. It is worth ~1R over 6.5 years. |
| **1** | A raw tier is quoted **wider than ~$0.22** on gold | Re-run the replay before deciding — past $0.22 the fill loss starts to bite (6 setups at $0.22, 8 at $0.32). |
| **2** | Either $1.00 or $3.50 | **Does not change the recommendation.** Measured at 0.48R vs 1.67R over 6.5 years. |
| **3** | Swap is identical across tiers | Put the confirmation in `fills.py` and replace `UNMEASURED_SWAP` on those tiers. Until then they REFUSE — see below. |
| **3** | **Swap differs by tier** | 🔴 **This outranks everything else on the page.** Swap is 6.60R against a ~10R total gap between tiers. Re-run the replay with the per-tier rates before choosing. |
| **4** | Admin fee is below ~$50/lot/night equivalent | Worth pricing properly — but ⚠ **gold's short swap is a CREDIT we currently collect**, so swap-free removes income as well as cost. The 6.60R figure is already net of that credit. Do not treat swap-free as a free 6.60R. |
| **5** | Min stop is wider than **$3.20** on gold | Matters. Our own `exec_min_stop_mode` floor of 0.08% binds at ~$3.20 on $4,000 gold, so the broker's 20-point ($0.20) limit currently never bites. A tier with a much wider limit would start refusing our orders instead. |
| **6** | Limit handling differs by tier | 🔴 Follow it up hard. **Fill behaviour on resting limits is this strategy's single largest sensitivity** — the jitter audit put ~6% of the trade list on five cents of quote difference (`backtest/tools/jitter_audit.py`). |

---

## After the answers land

1. Put the confirmed figures into **`docs/LIVE_TRADING_PIPELINE.md` → G5a**, replacing the
   published ones and **labelling them as broker-stated, not measured**. A support reply is a
   better source than a marketing page and is still not a measurement.
2. ✅ **Replace the sentinel in `backtest/fills.py::PROFILES` with what you measured.** The raw
   tiers carried `SPREAD_UNMEASURED` and **refused to be charged a spread** rather than borrowing
   Standard's 0.32 (which is what they all did until 2026-08-06 — see G5a). Set a measured figure
   on the tier and the refusal turns itself off. ⚠ **Do not paste in the number support gives you
   as though it were measured** — record it as broker-stated, and measure the tier properly once
   an account of that type exists.
   ✅ **DONE FOR ECN, 2026-08-14** — `_SPREAD_XAUUSD_PUPRIME_ECN = 0.12`, off 3,033,270 ticks over
   5 whole days on 700152905, all 23 traded hours including the 22:00 UTC reopen.
   🔴 **Prime and Cent still refuse, and ECN's figure may not be copied onto Prime.** The two are
   identical on every field the terminal publishes, which is the same "they look the same, so they
   are" reasoning that produced the 2026-08-06 defect and was wrong by 2.7x. A terminal only holds
   the ticks of the account it is logged into: sit `MT5_FFT` on 700152904 for a day and re-run.
3. **Once the live account is open, measure it — do not trust the reply.** Run
   `algos/tools/broker_facts.py --bot <bot> --history-days 3` against the funded terminal. That is
   the same read-only tool that produced the $0.32 and the ECN $0.12, and those are the only
   figures on this page that came from the broker's own tick stream rather than from a page
   describing it. ⚠ **`--history-days N` reads STORED ticks, so it can only see as far back as the
   terminal has been sitting on that account** — it is the measurement `--sample` cannot make (a
   live sample only ever sees the session you are sitting in), and it is why the ECN answer had to
   wait for the terminal rather than for anyone's attention.
4. ⚠ **Re-measure swap periodically regardless.** The values in `fills.py` were read on 2026-07-16
   and were 1.7% / 2.6% adrift three weeks later, with nothing to announce it. Swap is the largest
   re-priceable cost on this strategy.

---

## The reasoning trap this closed, recorded because it is easy to fall into again

The intuitive argument for Standard is genuinely persuasive, and it was the first answer given
before anything was replayed:

> Every entry is a resting limit. A limit fills at its own price or not at all, so it never pays
> the spread. Commission is charged on every fill regardless. Therefore pay the spread, not the
> commission — the raw tier is the worse deal.

**Every sentence is true and the conclusion is wrong.** The limit does avoid paying the spread —
by *not filling*. That is not a saving, it is the entire trade lost, and it is invisible in any
cost column because a trade that never happened has no P&L to charge. It shows up only as a
smaller trade count, which is why this needed `bid_ask_fills` (the one model here that can move the
trade list) and not an arithmetic charge.

**The general form: a cost that acts by REMOVING opportunities cannot be compared against a cost
that acts by SHAVING returns, unless you replay both.** One appears in the P&L and one appears in
the trade count, and only the first is visible in a fee table.
