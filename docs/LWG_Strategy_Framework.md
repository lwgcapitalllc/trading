# LWG Capital — Strategy Framework

**Purpose:** the standing reference for how strategies are designed, layered, built, and graded.
This is the "what and why" of strategy design. For the "how" at the code level —
file naming, the MQL5 `f_` prefix and NT8 `[Category("Foundational")]` conventions,
parameter schema, file placement — match the existing strategy files in `strategies/`
(the lab reads those conventions directly). This framework feeds into the
command-center lab (the grading engine).

---

## 0. The mission (read this first)

Prop firms are the **capital engine**, not the goal. The plan is to build a prop
farm purely to generate capital, then move that capital into **personal demo
forex/futures accounts** where the rules are looser and the real growth happens.

Two hard rules that shape everything below:
- **Intraday only. Never hold overnight.** Every strategy is flat by session end.
  No swing trading, ever. (This removes the carry bucket entirely and limits
  pairs to intraday-only.)
- **Every account has a ruleset — no exceptions.** Personal and demo accounts are
  not rule-free; they have *relaxed* rules and are graded to a real verdict, the
  same machinery as prop. There is no "no-verdict" account type.

This engine only ever holds **prop accounts** and **personal demo accounts**
(forex or futures). No personal *live* accounts. Personal demo balances default
to **$10,000**.

---

## 1. Core philosophy

A strategy is a **signal generator only**. It contains the edge and nothing else —
no account rules, no firm names, no instrument facts baked in. Everything that
isn't the edge is supplied at runtime by a layer below it.

This is what lets one strategy be tested against any account, on any instrument,
under any ruleset, without rewriting it. The same backtest grades against a
LucidFlex 50k, an Apex 100k, or a personal demo account — only the layers change.

**One idea per strategy. Generic logic. Injected config.**

---

## 2. The layer architecture

A strategy is a core plus three config layers. Each layer exists because it
changes for a *different reason* — that separation is what keeps it simple.

### Core — strategy logic (two halves)
The actual edge. Generic, instrument-agnostic, account-agnostic. It has two
equally important halves:

- **Entry logic** — when to get in (the signal).
- **Trade management** — how to get out (see Section 3, the part most people
  under-build and where most of the KPI quality actually comes from).

This is the only part rewritten when a winner ports from MT5 to NinjaScript.

### Layer A — Strategy parameters
The tunable knobs the optimizer sets: lookback, target R:R, RSI levels, range
window, trail distance, breakeven trigger. Same logic, different numbers per
instrument. Bound to the (strategy × instrument) pair.
- Convention: NT8 `[Category("Strategy Logic")]`; MQL5 no `f_` prefix.

### Layer B — Instrument profile  (plain English: "facts about the symbol")
Everything the code needs to know about *this specific symbol* that is neither
the strategy logic nor the account rules. Two kinds:

- **Broker-known facts** — the broker already knows these and tells the code
  automatically at runtime: how small one price tick is, what one tick is worth
  in money, the smallest allowed stop. **Never typed in, never stored** — the code
  asks the broker (`SymbolInfo`).
- **Things you set** — what the broker can't tell you: "don't trade when spread is
  wider than X," "only trade the London/NY session," "this symbol's volatility
  levels (regime thresholds)." A small per-symbol config.

The rule that keeps it simple: only *configure* what the broker can't *tell* you.

### Layer C — Account ruleset
Governance, split into the two axes that get graded:
- **Sizing (how big):** account size, contract-scaling table, max position. Risk
  per trade is **derived, not a free knob** — see below.
- **Guardrails (when to stop):** loss limits, profit target, drawdown, consistency,
  flatten time, etc. — the exact fields differ between prop and personal (Section 4).
- Convention: MQL5 `f_` prefix; NT8 `[Category("Foundational")]`; injected at
  runtime; hard-fail at init if a foundational param is still a placeholder.

### Composition rule — most restrictive wins
At runtime the strategy *proposes* a trade. Layer B can shrink or block it
(min stop, spread guard). Layer C can shrink or block it (scaling table,
guardrails). **A layer can only shrink or veto, never expand.** A strategy can
never override an account limit. This is the silent-corruption guard expressed as
architecture.

### Risk per trade is derived, not chosen
Risk per trade is **not a free slider**. It's computed from the daily loss limit
and how many losing trades you'll tolerate in a day before that limit is hit:

```
max risk per trade  ≈  daily loss limit  ÷  max losing trades per day
```

On **prop** accounts this is locked — the firm's loss limit bounds it, and the
strategy's expected losers-per-day sets it. On **personal** accounts it's freer,
but still derived from the (relaxed) daily loss limit, not picked arbitrarily.

---

## 3. The full strategy anatomy (where the edge actually lives)

A static entry with a fixed stop and target is only the *skeleton* of a strategy —
it tests whether the entry has a pulse, nothing more. The real strategy is three
layers stacked on top of the instrument's physics (gold's spread/volatility):

```
            ┌─────────────────────────────────────────┐
            │  3. TRADE MANAGEMENT  (after you're in)   │  ← maximizes good trades
            ├─────────────────────────────────────────┤
            │  2. FILTERS  (whether to take the trade)  │  ← removes bad trades
            ├─────────────────────────────────────────┤
            │  1. ENTRY SIGNAL  (the raw setup)         │  ← finds candidate trades
            └─────────────────────────────────────────┘
                 on top of: instrument physics (Layer B)
```

The two upper layers improve KPIs through **different mechanisms**, so tune them
separately: filters raise win rate and dodge landmines (fewer bad trades taken);
trade management raises expectancy (better outcome per trade taken). Confusing
them muddies what's actually helping.

### Layer 1 — Entry signal
The raw setup (e.g. the ORB break). On its own, with a static stop/target, it is a
*diagnostic* — see Section 6: it answers "does this entry have any edge at all,"
and that's all a static test should be asked to do.

### Layer 2 — Filters (decide WHETHER to enter, before the trade)
Gates that say "don't take this one." They remove bad trades before they happen:
- **News filter** — block entries around high-impact events.
- **Regime filter** — only take trades in the regime the edge works in.
- **Session / time-of-day filter** — only trade the right hours (for gold, session
  matters enormously — London/NY behaves nothing like 3am). One of gold's
  highest-value filters; build it early.
- **Spread filter** — skip when spread is too wide to leave an edge (critical on
  gold).

### Layer 3 — Trade management (decide what to do AFTER you're in)
Where good Sharpe, low drawdown, and survivability come from — intraday-critical,
because "flat by session end" + "get to breakeven fast" is how a prop drawdown is
protected.
- **Stop management** — initial stop; fast **breakeven move** (pull stop to entry
  after +X so a winner can't become a loser); **trailing stop** to lock open profit.
- **Profit taking** — full target, or **scale-out** (bank partial, run the rest),
  or trail a runner for a larger move.
- **Regime-exit** — bail when the regime flips against an *open* trade (note: this
  is management; "don't enter in a bad regime" is a *filter* — same concept, two
  jobs).
- **Time-based adjustment** — tighten stop / take profit faster during specific
  volatile windows (e.g. the open).
- **Capped re-entry** — re-enter if stopped at breakeven and the setup is still
  valid. See the overfit warning below — this is powerful but dangerous.

### Two overfitting landmines — prove these, never assume them
Two trade-layer features are the easiest ways to fool yourself in backtest. Both
are legitimate, both must be proven with the stress test / walk-forward on data
they were never tuned on, never just switched on because they raise the backtest.

- **Re-entry.** "Re-enter while the signal is valid" quietly becomes "keep
  re-entering until variance hands me a winner" — manufacturing fake profit by
  repeating the same move until one works. Defense: hard-cap re-entries (1–2 per
  setup), and test re-entry as its own toggle — does it actually raise expectancy,
  or just inflate the curve?
- **Time rules.** With enough data, *some* random hour always looks profitable by
  chance. A time rule is an edge only if it has a *reason* (the London open is
  volatile because liquidity shifts — not because the backtest liked that hour)
  and survives walk-forward. A time filter found by searching is noise.

The common thread: both can make a backtest look great by accident. The defense is
the same for both — the rule must make sense *before* you add it, and survive data
it wasn't tuned on. The stress gate exists to catch exactly these.

---

## 4. Rulesets — prop vs personal

Every account is graded against a ruleset. The difference is the *numbers and
field types*, not whether rules exist.

### Prop rulesets (concrete — not editable)
Locked. Core rules cannot be changed (they're the firm's rules, verified from
their docs). The four that matter, all enforced:
- **Trailing EOD max-loss** — trails the end-of-day high; one breach = instant
  DISCARD. Locks at a fixed balance for most firms (start + $100), or start +
  target (Apex/Rithmic), or never (Tradovate/Tradeify eval).
- **Profit target** — the number to clear to pass.
- **Consistency** — best day ≤ X% of total (varies by firm; FundedNext *raises
  the target* on breach instead of failing).
- **Contract scaling** — balance → max contracts (funded phase; eval is fixed cap).

Risk per trade and core rules are **locked** on prop.

### Personal demo ruleset (relaxed — editable)
The goal is **grow consistently, never get close to blowing it.** Fails fire
*early and cheaply*, long before real damage. Default balance $10,000.

| Rule | Value | Effect |
|---|---|---|
| Daily loss cap | **5%** | stops trading for the day (a halt, not a fail) |
| Daily profit target | **10%** | stops trading for the day when hit |
| Consecutive bad days | **3 days in a row hitting the 5% cap** | **DISCARD** |
| Drawdown from peak | **15% from equity peak (within the run)** | **DISCARD** |
| Consistency | NULL | not applied |
| Scaling | none | not applied |

The two DISCARD conditions guard *different* failure modes and are both kept:
- **Consecutive-bad-days** catches broken discipline (three capped days in a row).
- **15%-from-peak** catches total damage however it accumulates — including slow
  bleed that never hits the daily cap.

A strategy fails the personal ruleset if *either* fires.

**Key contrast with prop:** on personal you can lose 5% three days and survive
(only the streak or the 15% drawdown ends it). On prop, the trailing max-loss
means one breach is instant violation. Same architecture, opposite tolerance.

### Editability rule
- **Personal/demo rulesets:** editable from the Rulesets page.
- **Prop rulesets:** locked — core rules and risk-per-trade cannot be edited.

---

## 5. The edge buckets

Strategies are collected as **uncorrelated return sources**, so that when stacked,
something is working in every regime and the combined equity curve is smooth
enough to pass an eval. Two strategies from the same bucket don't diversify a
stack; they double the same bet.

All buckets are built **intraday only.**

### Core three (build these first, in this order)
1. **Mean reversion** — fade price when it stretches from a mean. The backbone;
   trades most, smoothest curve. On in RANGING / LOW_VOLATILITY.
2. **Trend / momentum** — buy strength, sell weakness, ride the move. The hedge
   for #1: mean reversion's worst days are strong-trend days, which is when trend
   pays. On in TRENDING.
3. **Volatility breakout** — catch the move when a quiet market expands. Fills the
   in-between regime the first two don't handle. On in TRANSITIONING.

The first three together are already a self-covering intraday stack.

### Depth (build after the core works)
4. **Seasonality / time-of-day** — session opens, weekday/turn-of-day effects.
   Mostly an overlay on the core three; orthogonal, stacks cleanly. Intraday by
   nature.
5. **Pairs / relative value (intraday only)** — long one instrument, short a
   correlated one, closed before session end. Market-neutral. Only viable if it
   fits the intraday rule.

**Carry is out.** It requires holding overnight for the swap — incompatible with
the intraday-only rule. Not part of this framework.

### Patterns are triggers, not buckets
Candlestick / price patterns (gap, smash day, hook, engulfing, ORB) are **entry
triggers** bolted onto bucket 1 or 2 — never standalone edges. ORB read as a
breakout feeds bucket 2; read as a failed-break fade it feeds bucket 1.

### Speed is a dial, not a bucket
Every bucket can be built at different intraday holding times. The fast end is
**scalping** (minutes, many trades). True HFT (sub-second, co-located) is out of
scope — wrong hardware, wrong costs, prop rules ban it.

### Regime coverage (the spine of the stack)

| Regime | Bucket that's "on" |
|---|---|
| TRENDING | Trend/momentum, volatility breakout |
| TRANSITIONING | Volatility breakout/expansion |
| RANGING | Mean reversion |
| LOW_VOLATILITY | Mean reversion, pre-expansion squeeze setups |
| HIGH_VOLATILITY | Trend/breakout with vol-scaled sizing; mean reversion breaks here |

Trend and mean reversion fail in *opposite* ways — trend with low win rate and
lumpy drawdowns, mean reversion with a smooth curve and a fat left tail. Stacked,
they cover each other. That mutual cover is the reason to build buckets rather
than hunt for one perfect strategy.

---

## 6. How to build one (without fooling yourself)

The goal is never "find the magic parameters." It is "does this idea have an edge
at all," then tune gently. Optimization tunes a real edge; it cannot manufacture
one. A weak strategy is just weak.

1. **Idea first, not parameters.** One clear hypothesis, one instrument, intraday,
   bar-close logic. (e.g. "the first 30-min range break after the gold session open
   continues in the break direction, target sized to beat spread, flat by session
   end.")
2. **Static smoke test — entry + fixed stop/target, run ONCE. This is a diagnostic,
   not the strategy.** A static version exists to answer one question: does the
   entry have *any* pulse? It is *supposed* to look unimpressive — a fixed stop and
   target throw away most of the edge. If a setup can't show even a weak positive
   signal after spread with a basic stop/target, no amount of trade management will
   save it (management *amplifies* an edge, it can't *create* one) — move on, don't
   tune to rescue a coin flip. If it shows a pulse, proceed. Keep this step to a
   quick checkpoint; it is the smoke test, never the destination.
3. **Build the real strategy: add filters, then trade management.** This is where
   the strategy actually gets made and where the KPIs go from mid to good — Section
   3's three layers. Add filters (regime, session, spread, news) to remove bad
   trades; add trade management (fast breakeven, trailing, scale-out, regime-exit)
   to maximize the good ones. Test each addition as its own toggle so you know what
   helped. Treat re-entry and time rules with extra suspicion (Section 3's two
   landmines).
4. **Coarse sweep to see the shape, not pick a winner.** Wide steps. You're
   looking for a broad *region* of decent parameters. A real edge is a plateau;
   noise is a single spike.
5. **Pick from the middle of the good region, not the peak.** The single best
   combo is overfit. A parameter that works across a *range* survives live.
6. **Stress-test the survivor** (Monte Carlo, walk-forward, sensitivity), then
   **forward-test on demo**, then it earns a prop eval.

### The brute-force trap
Testing every combination and picking the best is the most common way to fool
yourself. In 10,000 combos, hundreds look brilliant by luck. Pick the peak and you
pick noise — it backtests beautifully and dies live. Brute force is for *exploring
the shape*, never for *picking*.

### "It trades every day" is not an edge
A break every day, or a trade every day, means nothing unless those trades win
more than they lose **after spread**. Judge an idea on whether the trades pay, not
on how often it fires.

---

## 7. The grading pipeline (the lens)

Every strategy is judged by the command-center lab against the account's ruleset.
The lens is correct, ruleset-driven, and honestly measured — its job is to stop a
weak or overfit strategy from reaching real capital.

### The path forward (what "it works" leads to)
```
Build in lab → grade against KPI floor → stress-test → forward-test on demo
→ prove against a ruleset → buy eval (prop) / fund (personal) → grow
```
A strategy that passes has somewhere to go. That path is the answer to "what if it
works."

### KPI floor (general strategy quality — separate from the ruleset verdict)
| Metric | Floor | Notes |
|---|---|---|
| Sharpe (daily, √252) | ≥ 1.0 | 1.5+ preferred; >3 on small sample is suspect |
| Calmar | ≥ 1.0 | 2.0+ good; capital-independent. Carries the recovery-factor signal (return ÷ drawdown) — shown on the dashboard with recovery factor in its tooltip |
| Max drawdown % of capital | judged vs the account it runs on | — |
| Profit concentration | < ~60% in one quarter | the overfit detector |
| Z-score (runs test) | within ±2 | beyond = non-random streaking |
| Expectancy ($) | > 0 after costs | the edge per trade |

Run the KPI floor and the ruleset verdict as **two separate scores** — they answer
different questions.

### Anti-overfit discipline
- Grade under conservative (risk-adjusted) parameters, not the optimizer's peak.
- Profit concentration over time is the first thing to check on any winner.
- Backtest is necessary, never sufficient — forward time is the real validator.

---

## 8. Data fidelity (what you can trust today)

- Real bid/ask ticks available on the broker ≥ 2 years deep — **not used by
  either tester today.**
- **MT5** runs `Model=1` (1-min OHLC, invents the intrabar path); **NT8** runs
  minute bars with standard fill assumptions.
- **Trustworthy for bar-close logic at M5 and above** on both platforms.
- **Not trustworthy for sub-minute / intrabar-precise scalping** — needs real
  ticks (MT5 `Model=4`, NT8 Tick Replay), a known one-line lever, not yet enabled.
- **Spread decides the instrument** (PU Prime demo): EURUSD/GBPUSD ~0–1% of a
  typical scalp target (cleanest), gold ~18% (workable), GBPJPY ~38% / NAS100 ~27%
  (heavy). Build first on a tight-spread major.
- Always hold a strategy to a **pessimistic slippage buffer on top of real
  spread** before trusting a result.

---

## 9. Build order (current)

1. **MT5 first** for every strategy (faster optimization), port winners to
   NinjaScript afterward.
2. **Mean reversion → trend → volatility breakout** (the core three).
3. Intraday, bar-close logic at **M5 / M15** on a tight-spread major
   (EURUSD/GBPUSD) first.
4. Build **2–3 candidates per bucket** at different intraday holding times, so the
   future stacking layer has real choices.
5. Depth buckets (seasonality, intraday pairs) only after the core stack works.

---

## Principles, in one place
- Prop is the capital engine; personal demo is the destination.
- Intraday only — flat by session end, always.
- Every account has a ruleset; personal is relaxed, not rule-free.
- Strategies are signal generators; config is layered and injected.
- A strategy is three layers: entry signal, filters (whether to enter), trade
  management (what to do once in). Filters raise win rate; management raises
  expectancy. Tune them separately.
- A static stop/target run is a diagnostic — it only tells you if the entry has a
  pulse. The real strategy is built in the filter and management layers.
- Trade management amplifies a real edge; it cannot create one. Confirm the pulse
  before building on top.
- Re-entry and time-of-day rules are the two easiest ways to fool yourself — cap
  re-entries, require a real reason for time rules, prove both on untuned data.
- Risk per trade is derived from the daily loss limit, not chosen freely.
- A layer can only shrink or veto a trade, never expand it.
- Collect uncorrelated edges, not more of the same edge.
- Optimization tunes a real edge; it cannot create one.
- A real edge is a plateau of working parameters, not a single spike.
- Frequency is not an edge; trades must pay after spread.
- Grade general quality (KPIs) and ruleset rules (verdict) separately.
- Backtest is necessary, never sufficient — forward-test before real capital.
- Accuracy over speed; flag conflicts rather than guess.
