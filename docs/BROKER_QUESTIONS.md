# Broker questions — PU Prime account type for the live A+ bot

**Purpose:** The questions to put to PU Prime before funding a live account, why each one is
being asked, and what to do with the answer.
**Scope:** PU Prime, XAUUSD, the `mpc_sos_fade` A+ bot. Not a general broker checklist.
**Status:** Open — sent nothing yet, and **questions 1-3 no longer need to be asked** (see below).
**Recommendation as it stands:** a **raw-spread tier (ECN, or Prime)** — **not Standard**.
**Evidence:** `docs/LIVE_TRADING_PIPELINE.md` → **G5a**, measured 2026-08-06.

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
| Q1 spread by tier | ⏳ needs an open market (Sunday 22:00 UTC onwards) |
| Q2 commission per lot per side | ⏳ two 0.01-lot round turns, or ask |
| Q4 swap-free / Islamic | ❓ still a human question |
| Q5 min stop | ✅ measured — 20 points ($0.20) on all three |
| Q6 limit-order handling by tier | ❓ still a human question |

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
2. ✅ **Replace the sentinel in `backtest/fills.py::PROFILES` with what you measured.** The three
   raw tiers now carry `SPREAD_UNMEASURED` and **refuse to be charged a spread** rather than
   borrowing Standard's 0.32 (which is what they all did until 2026-08-06 — see G5a). Once you
   have a real figure, set it on that tier and the refusal turns itself off. ⚠ **Do not paste in
   the number support gives you as though it were measured** — record it as broker-stated, and
   measure the tier properly once an account of that type exists.
3. **Once the live account is open, measure it — do not trust the reply.** Run
   `algos/tools/broker_facts.py --history-days 3` against the funded terminal. That is the same
   read-only tool that produced the $0.32, and it is the only figure on this page that came from
   the broker's own tick stream rather than from a page describing it.
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
