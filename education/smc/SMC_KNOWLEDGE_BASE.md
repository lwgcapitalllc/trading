# SMC Knowledge Base — Master Snapshot

**What this is.** One self-contained reference for the entire SMC engine course *and* how it
maps onto the MPC JARVIS indicator and this repo's build/backtest stack. Built so future
SMC questions can be answered from this file alone — no need to re-read `education/smc/`
end to end. If a detail here needs the source, the pointer is in the [Source Map](#source-map).

**Provenance.** Distilled from `education/smc/` (modules 02 SMC Engine Training, 03 Risk
Management, 04 The Master Key, 05 My Full Trading Strategy) + the visual playbook PNGs in
`education/smc/playbooks/`. Numbers tagged "(data)" come from the course's own 2.5-year
backtest (module 05, video 25 "full data synopsis"). Where a rule exists only as a diagram
(premium/discount), that's flagged inline.

**Instrument/timeframes.** Taught on XAUUSD / EURUSD. **15m = primary direction (bias)
chart; 1m = execution/timing; 5m = cross-check.** All session times below are **US Eastern
(ET / UTC-4 on the course charts)** unless stated.

**Last built:** 2026-07-20.

---

## Table of contents

1. [The mental model (top-down bias)](#1--the-mental-model-top-down-bias)
2. [Market structure](#2--market-structure)
3. [Points of interest & entry objects](#3--points-of-interest--entry-objects)
4. [Liquidity & the session model](#4--liquidity--the-session-model)
5. [The session playbook — the 8 plays](#5--the-session-playbook--the-8-plays)
6. [The entry model (execution)](#6--the-entry-model-execution)
7. [Invalidation & overrides](#7--invalidation--overrides)
8. [Risk model](#8--risk-model)
9. [The backtested edge (the proof)](#9--the-backtested-edge-the-proof)
10. [Mapping to the MPC JARVIS indicator](#10--mapping-to-the-mpc-assistant-indicator)
11. [Build & backtest path](#11--build--backtest-path)
12. [Source map](#source-map)

---

## 1 — The mental model (top-down bias)

The whole method is one nested question chain, checked **in order**. Fail any step → do
nothing.

**Bias ≠ structure — and bias is the higher authority.** Two separate reads that can
disagree:
- **Directional bias** (weekly + daily) — from candle **closes**, data/probability-driven.
- **Market structure** (15m / 4H) — swing points, BOS/CHoCH.
When they conflict, **bias wins** (this is the invalidation hook — see [§7](#7--invalidation--overrides)).

**Hierarchy:** Weekly bias → Daily bias → **15m structure** (intraday direction) → **1m**
(execution timing). Daily+15m tell you **WHAT** and **WHERE**; the 1m tells you **WHEN**.

### Weekly bias (68% accuracy, ~15 yrs data)
- Prev week closes **below** the prior week's low → **bearish** week, expected to trade down
  into that low. Mirror above → bullish. Trader weights his own aligned read at 75–80%.
- Intra-week path follows **Power of Three**: open → push the wrong way (manipulation) →
  then the real move to target.

### Daily bias (67% accuracy, ~5,469 days)
- **Trigger 1:** today closes **below** the previous day's low → next day bearish. Mirror up.
- **Trigger 2:** price **wicks above** the prev day's high and **closes back inside** →
  67% next day trades **down**. Mirror: wick below prev-day low + close back inside → bullish.
- **Intraday path = Power of Three:** accumulation → **manipulation** (opposite first) →
  **distribution** (real move). Bearish day = Open-High-Low-Close; bullish = Open-Low-High-Close.
  You wait for the manipulation, then enter the continuation.
- **Trading-day open = 17:00 ET (5 PM).** *(Note: the indicator's liquidity/VWAP engines roll
  the trading day at 18:00 NY — a 1-hour offset from the course; reconcile when building — see
  [§10](#10--mapping-to-the-mpc-assistant-indicator).)*

### Step 2 of bias — the "draw on liquidity"
After candle direction, name **what price is being pulled toward**. Bias = direction + target.
Draws: FVGs, overlapping/inverted FVGs, equal highs/lows, order blocks, prev day/week high & low.

---

## 2 — Market structure

**Swing-point rules (the objective, rule-based core):**
- A swing point is **confirmed only when the opposite prior swing breaks** (until then it's an
  unconfirmed/dashed level). A high is real when the prior **low** breaks, not just on a pullback.
- The **new swing point after a break = the extreme reached before that break** (highest point
  before an up-break becomes the swing high).
- **Wicks do NOT count — a break needs a candle CLOSE through the level.** A wick below a low =
  failed acceptance, not a CHoCH/BOS.
- **Valid-pullback rule** gates every swing (a specific 3-candle wave, not any 3 candles). This
  repo's canonical rule: a swing high needs 3 consecutive candles each closing below the previous
  candle's low (mirror for lows). No pullback rule = random structure (the #1 mistake).

**BOS vs CHoCH:**
- **BOS (Break of Structure) = continuation** — breaks a structural high in an uptrend / low in a
  downtrend, same direction. Repeats freely.
- **CHoCH (Change of Character) = the FIRST break AGAINST trend = trend change.** Happens **once
  per direction** before the trend flips. First reversal sign.
- **This maps to the engine's SOS:** the market_structure engine calls the trend-flipping break an
  **SOS** (shift of structure) = the course's CHoCH. A plain **BOS** = continuation.

**Strong vs weak side:** in a bull trend the swing **low is strong/protected**, the **high is
weak** (expected to break) → trade toward the weak side. Reverse in a bear trend.

**Internal vs external (box method):** swing low → swing high defines the range; everything inside
= **internal structure** (labeled `I-` : I-CHoCH, I-BOS, iSH/iSL). Internal disappears when the
range breaks. An internal CHoCH realigning with the swing direction is a signal to target the swing
high/low (he prefers 1m confirmation over internal).

**Probabilities:** same rules on every timeframe. After a BOS, price continues **~60–66%** of the
time; failures usually run straight through with no LTF entry (un-tradable anyway). Textbook
reversal cycle = **expansion → contraction → reversal**.

---

## 3 — Points of interest & entry objects

**POI = an area price is expected to REACT from** — a supply/demand zone (order block), a liquidity
pool, or an FVG. It is **step 3** of the trade (after bias + structure). **Only valid INSIDE the
current price leg** (swing high → swing low); a POI outside the leg or against bias is irrelevant.

### POI strength (the biggest edge amplifier — playbook `02-points-of-interest/`)
| Grade | Rule | Behaviour on return |
|---|---|---|
| **Strong** | POI that **caused a structural break** / left displacement (an FVG behind it) | **Impact** — sharp reaction. Best. |
| **Weak** | POI from a weak/choppy origin move, no displacement | **No impact** — price cuts straight through. Avoid. |
| **Broad** | A **previous cluster/consolidation** range (wide zone) | Reaction from a wider area, less precise. |
| **None** | Nothing there | No trade. |
Filtering a setup by a **strong POI** is what promotes it to **A+** (e.g. London-sweep-Asia jumps
from ~30% to >50% win rate — see [§9](#9--the-backtested-edge-the-proof)).

### Order blocks (OB)
- **Definition:** the **last opposing candle/range at the swing extreme before an aggressive move**
  (fading selling before an up-move = bullish OB; fading buying before a down-move = bearish OB).
  This is the OrthosLabs / Kelly Lewis structure-tied definition — **not** a makuchaku engulfing OB.
- Use the **RANGE** the block creates, not just the line.
- Must have **displacement + a fair value gap (imbalance) left behind** to qualify (this is exactly
  what makes it a *strong* POI).
- **Bias-aligned only** (bull trend → show only bullish OBs).
- **Mitigation kills it:** once price trades/closes THROUGH the OB it's dead; a bullish OB traded
  through can re-qualify as a bearish OB.
- **Refined OB** narrows the zone to a single candle — HTF (daily) only.
- **Role = entry confirmation ONLY** (on 1m/5m after the LTF shift), NOT a direction tool. Thousands
  form per day; almost all are noise.

### Fair value gaps (FVG) & inverted FVG (iFVG)
- **FVG = a 3-candle imbalance/inefficiency** price tends to rebalance (return to). **Bias-aligned
  only.**
- **iFVG:** price trades *through* an FVG and it flips polarity, becoming an area of interest on the
  other side — **the trader's favorite entry.**
- Same role as OBs: **entry confirmation after the shift, not direction.** OBs and FVGs rank BELOW
  structure and sessions — cherry-pick the one at your setup.

### Premium / discount (fib) — *diagram-only, playbook `05-premium-discount/`*
Not spoken in modules 02/04 transcripts; the rule is read off the diagrams:
- Draw a fib on the swing leg: **equilibrium = 50%** of the range. **Discount = below the midpoint
  (buy zone); premium = above the midpoint (sell zone).**
- **Rule: buy only in discount, sell only in premium.** Valid long = entry taken *below* 0.5 (a deep
  retrace); invalid long = shallow entry *above* 0.5.
- Diagram entry levels: **0.618 / 0.705 / 0.786** (plus 0, 0.5, 1). **These match the indicator's fib
  entry tiers** E1 0.618 / E2 0.702 / E3 0.786 / E4 0.886 — see [§10](#10--mapping-to-the-mpc-assistant-indicator).

---

## 4 — Liquidity & the session model

**Liquidity = money; it concentrates at highs/lows and is absent inside imbalances.** Price
gravitates to it "like a magnet."

**The liquidity that matters (macro):** previous **day** high/low, previous **week** high/low,
**session** highs/lows (Asia/London/NY). Not every equal high/low.

**Sweep mechanic:** before a bearish move price first runs **up** to grab buy-side liquidity (bearish
candles wick the top), then expands down. Mirror for bullish. Four uses: (1) profit target/draw,
(2) a level that must be swept **before** your move, (3) narrative/context, (4) avoidance (don't
trade into a magnet against you). Liquidity is **not** a standalone context builder — pair it with
trend.

**Overextension logic:** sustained one-directional moves with no pullbacks put liquidity providers
in drawdown → expect mean-reversion at key prior highs/lows.

### The session model (all ET / UTC-4)
| Session | Window (ET) | Role |
|---|---|---|
| **Asia** | 20:00 – 00:00 | A **liquidity pool** (builds a high & low). *Don't trade Asia.* |
| **Frankfurt ("Frank")** | 00:00 – 02:00 | Pre-London German session; often **sweeps Asia** first. |
| **London (LDN)** | 02:00 – 05:00 | The session that **sweeps Asia** to fill orders; sub-windows 2–3 / 3–4 / 4–5. |
| **Lull** | 05:00 – 07:00 | Dead gap between London and NY; can **sweep the London high/low**. |
| **New York (NY)** | 07:00 – 10:00 | Either **continues** London (trending) or **sweeps London → reversal** (overextended); sub-windows 7–8 / 8–9 / 9–10. |

**How the sessions hand off:** each session's high/low becomes the **next** session's liquidity
target. If Asia's low is taken first, the remaining target is Asia's high (and vice-versa). Core
London play: London sweeps one side of Asia → continuation (paired with trend).

> ⚠️ **The indicator's `sessions` engine does NOT use these windows by default.** Its defaults are
> broader (Tokyo 20:00–05:00, London 04:00–13:00, NY 09:00–18:00 GMT-4) and it has **no Frankfurt or
> Lull**. Its `KZ1/2/3` "kill zones" (10:00–10:59, 11:45–12:14, 13:00–13:30 NY) are ICT kill zones,
> **not** the course's session windows. To build these plays, construct the engine with the course
> windows via `SessionEngine(sessions=[SessionSpec.from_pine("Asia","2000-0500","GMT-4"), ...])`
> and add Frank/Lull as extra `SessionSpec`s — see [§11](#11--build--backtest-path).

---

## 5 — The session playbook — the 8 plays

**The master engine behind every play:** M15 pro-trend bias → price reaches an **area of interest**
(a session-liquidity sweep OR a strong POI) → **M1 CHoCH/BOS aligned with the M15** → enter from an
**M1–M5 order block or FVG**. The plays differ only in *which session sweeps which session's
liquidity, and in which session the entry confirms*.

**The one rule that splits reversal from continuation:**
- **M1 CHoCH lands in the SAME session as the sweep → REVERSAL** → enter directly.
- **Sweep + CHoCH in one session, but you wait for the NEXT session to confirm with a further BOS →
  CONTINUATION** → you need that second break before entering.

| # | Play | Sweep (source→session) | Confirm | Type | Dir shown | POI needed? | Edge (data) |
|---|---|---|---|---|---|---|---|
| 1 | **NY continuation from LDN POI** | *no sweep* — retrace to a London-built OB | NY taps the LDN POI | Continuation | long (sym.) | **POI IS the trigger** | **63% win — best A+** |
| 2 | **LDN sweep Asia** | Asia H/L → London | M1 shift in London | Reversal | long (sym.) | strong POI → A+ | **>50% win w/ strong POI**; his most-traded |
| 3 | **Frank sweep Asia → LDN continuation** | Asia → Frankfurt | CHoCH in Frank, **wait LDN BOS** | Continuation | long (sym.) | optional | ~26% win but **~30–40% of all profit** (highest volume) |
| 4 | **Frank sweep Asia, CHoCH in LDN (variant)** | Asia → Frankfurt | CHoCH in **London** | Reversal→cont. | long (sym.) | optional | rare (~2 trades) — noise |
| 5 | **Lull sweep London → NY continuation** | London high → Lull | CHoCH in Lull, **wait NY BOS** | Continuation | short (sym.) | optional | part of NY-sweep-lull family (~55%) |
| 6 | **Lull sweep LDN → NY reversal** | London high → Lull | CHoCH **after NY open** | Reversal | short (sym.) | optional | mean-reversion ~55% |
| 7 | **NY sweep of LDN** | London low → NY | M1 confirm in NY | Reversal/cont. | long (sym.) | **not needed** | solid |
| 8 | **NY sweep of Asia** | Asia high → NY | M1 shift in NY | Reversal | short (sym.) | not needed | **DROP — 3 trades in 2.5 yr, no edge** |

All directions are "as drawn in the diagram" — **the model is symmetric** (long or short by
pro-trend). "Frank" = the Frankfurt session (00:00–02:00). "Lull" = the dead 05:00–07:00 window.

**Two more nuances the diagrams show:**
- The **Frank continuation** confirms with a **BOS** (trend already up); the **CHoCH variant**
  confirms with a **CHoCH** (fresh flip up). Same sweep, different confirmation break.
- The **Lull continuation** already has bearish structure (CHoCH *then* BOS before NY) so NY just
  continues down; the **Lull reversal** is still in an up-context and the CHoCH at NY is the turn.

---

## 6 — The entry model (execution)

The **"5-minute manipulation model"** — the single highest-probability entry.

**Preconditions:** must align with **M15 direction** AND **daily bias**.

**Steps:**
1. **Reach the POI** — price returns to the supply/demand zone / area of interest.
2. **Drop to M1 for confirmation.** As price pulls into the zone the 1m is usually *counter* to the
   15m → **sit on hands**. Enter only when the 1m **realigns**: an aggressive **BOS + CHoCH**
   flipping the 1m to the trade direction.
3. **M5 cross-check** — on the 5m this shows as **consolidation → sweep of the consolidation →
   close back inside → CHoCH** (the "5-minute manipulation & expansion").
4. **Entry trigger** — the **M1 inverted FVG** (favorite). Fallbacks: FVG, order block, breaker.
5. **Stop** — at the **M1 swing** (high for shorts / low for longs) — the logical invalidation point.
6. **Target** — at minimum the opposing liquidity (the draw). **1:5 R:R (5R) minimum** for this model.
7. **Scale-in** — add on an **M5 FVG / M5 iFVG** (or another M1 inversion) if it appears (opportunity,
   not a guaranteed fill).

**The 5-step trade construction (used across all trade examples):**
1. Directional bias (daily/weekly) → 2. M15 structure bias → 3. POI (supply zone / liquidity) →
4. Confirmation (1m shift into alignment) → 5. Risk (structure stop, liquidity target, ~5R).

**A+ grading:** picture scales — reasons up vs down. When your side is far heavier (bias + 15m
structure + LTF structure + Wyckoff schematic + order flow all stacked, nothing meaningful against),
it's A+ → **double down / scale in** rather than shrinking.

**Execution discipline:** if you don't get tagged, **do NOT chase** (never re-place the entry lower
with the stop just above — you get swept). **Skip any trade whose R:R < ~1:5.** Un-filled trades are
fine. Refinement from data: after the CHoCH, if the M1 makes a small pullback and continues, **keep
the original entry level** — don't wait for a second CHoCH (that old rule missed trades).

---

## 7 — Invalidation & overrides

Presented as the single most valuable concept: **when to override the structure/indicator.**

**Override 1 — internal Asia high/low used as a swing point.**
Do NOT treat the Asia high or low as a swing point when it sits in a **tight/compact range INSIDE a
price leg** (internal). Only trust it when it's **OUTSIDE the leg**. A CHoCH built on an internal
Asia extreme is a **"fake reversal"** — London routinely sweeps one side of Asia then the other,
trapping both retail longs and shorts. "It's always the change of character" that's the fake, because
it was measured off the wrong (internal) reference.

**Override 2 — daily AND weekly bias both against the structure idea.**
When 15m/4H structure says bullish but **both daily and weekly bias are bearish** (68% weekly + 67%
daily), do NOT take the counter-bias longs — trade with HTF flow. Worked example: weekly closed below
prior-week low + daily wicked above prior-day high and closed inside → both bearish → **short despite
bullish 15m structure**. **The 1H timeframe is a distraction** — invalidation is driven by daily+weekly.

**Trade-3 discretion:** when M1 external structure is too large to be actionable, **trade the internal
M1** instead (the 1m is about the "now," not the swing rule). Discretionary counter-structure trades
are only for high-probability reads; stop always at a logical structure swing; require ~1:5.

---

## 8 — Risk model

**Fixed risk per trade:**
- **≤1% per trade on a prop firm** (use 1% even in the evaluation/challenge phase).
- **Personal accounts: up to 2%.** Default sizing **0.5–1%**, scaled to **1.5–2% only on A+ setups
  when sitting on a buffer** (e.g. a 4% cushion) — "dynamic scaling of risk."
- Prop reality: with a **10% max drawdown**, "1% of a $200k account" is really **10% of true
  firepower** — 1% is genuinely aggressive on a prop account.

**Position-sizing formula:**
> **Lots = (Balance × Risk %) ÷ (Stop in pips × pip value per lot)**
> e.g. $200,000 × 1% ÷ (10-pip stop × …) = 20 lots. **The stop distance, not the lot count, sets the
> risk** — same lots with a 10× wider stop = 10× the risk.

**Capital preservation math:** risk 10%/trade → 5 losses = −50% (need to *double* to recover); risk
1%/trade → 5 losses = 95% intact (need only +5.26%). Fewer, more selective trades = less risk.

**Profitability formula (the 3 KPIs — optimize together):**
> **Profit factor = $ won ÷ $ lost** (>1 profitable). **Win rate = winners ÷ (trades − breakevens).**
> **Avg R:R = avg win ÷ avg loss.** Win rate and R:R *together* make PF — neither alone means anything
> (70% win at 0.2 R:R loses; 1:5 at 15% loses). Always subtract commissions/fees/swaps.

**Stops & targets:**
- **Stop = where the idea is invalidated** (structure), never an arbitrary point for a pretty R:R.
  Below the protected structural low (longs) / above the protected high (shorts).
- **Breakeven:** move to BE when the M1 breaks structure after entry and there's no M5 OB/FVG at your
  entry (no reason for price to return).
- **TP ladder:** **close 50% at 5R**, then **halve what's left at each structural level** on the way
  (old Asia/London/NY session highs & lows used as liquidity), **close the last piece in full at the
  final target.**

**Spread & slippage:** spread = bid/ask fee on every fill; slippage = fill gap from thin liquidity.
Both **blow out on high-impact news (NFP, CPI, FOMC) and bank holidays**. Quantified: an 8-pip stop
slipped 2 pips = **+25% risk** ($1,000 loss → $1,250). This is why the playbook **bans NY sessions
with CPI/NFP/FOMC** and blocks entries before 08:30 releases.

---

## 9 — The backtested edge (the proof)

Course's own **2.5-year** backtest (module 05, video 25), **1% fixed risk**, ~230 trades over 10
traded months:

| Metric | Value |
|---|---|
| Total return | **+216.86%** (~86%/yr, ~8.6%/month) |
| Profit factor | **3.07** |
| Win rate | **~33%** |
| Avg win:loss | **≈ 6.23R** |
| Max drawdown | **6%** |
| Hold time | winners ~12h, losers cut ~39min |

**The asymmetry comes entirely from management, not hit rate.** Per-setup:

| Setup | Win rate | Note |
|---|---|---|
| **NY continuation from LDN POI** | **63%** | best A+ |
| **London-sweep-Asia (strong POI)** | **>50%** | most-traded; strong-POI filter lifts it from ~30% |
| **NY sweep of the lull** | **~55%** | mean-reversion |
| **Frankfurt "London-sweep-Frank" family** | ~26% | **highest volume, ~30–40% of total profit** |
| **NY sweep of Asia** | ~breakeven | **only 3 in 2.5 yr — dropped** |

**Operating takeaways:** keep taking every valid setup; **scale risk to ~1.5–2% on A+ when you have a
buffer**; **drop NY-sweep-Asia**. Low win rate is fine — the 6R average win carries it.

---

## 10 — Mapping to the MPC JARVIS indicator

The indicator (`indicators/engines/mpc_jarvis.pine`) and its extracted `engines/` already detect **every
ingredient** these plays need. The course plays are essentially the indicator's existing **REV / A+ /
CONT** sequences **+ session-window gating + bias/premium-discount gating**.

### 10a — SMC concept → engine signal
| SMC concept | Engine (`engines/…`) | Signal / field |
|---|---|---|
| 15m CHoCH (trend flip) | `market_structure` | `bull_sos` / `bear_sos` (**SOS = CHoCH**) |
| 15m BOS (continuation) | `market_structure` | `bull_bos` / `bear_bos` |
| HH/HL/LH/LL, ASH/ASL | `market_structure` | `broken_high_label` / `broken_low_label` |
| Internal structure (I-BOS/I-CHoCH) | `market_structure` | internal `bull_bos`/`bear_bos`/`bull_sos`/`bear_sos`, iSH/iSL |
| 1m/4H structure shift (timing) | Pine `f_mtfStruct` (MTF) | per-TF **Shift** (SOS) / **Expansion** / **Continuation** — or run the structure engine on 1m/4H bars |
| Order block (POI) | `order_blocks` | `created` / `mitigated` / `active_bull` / `active_bear` (cap 2/dir) |
| **Strong** POI (displacement) | `order_blocks` **+** `fair_value_gaps` | OB **with** an FVG behind it = strong; OB without = weak *(derived, no single flag)* |
| **Broad** POI (cluster) | `equal_highs_lows` | `active_eqh` / `active_eql` (or a detected consolidation) |
| FVG / iFVG (entry) | `fair_value_gaps` | `formed` (+`is_bullish`) / `mitigated` / `active`; **iFVG = a `mitigated` FVG acting from the far side** *(derive)* |
| Premium / discount zone | `fibonacci` (Macro/Cycle) | discount = price < 0.5 (buy), premium = > 0.5 (sell); **Structure fib** `half_reached`=0.5, `E1 0.618 / E2 0.702 / E3 0.786 / E4 0.886` = the course's discount entries |
| Sniper zone (tight 0.382–0.5) | `fibonacci` (Sniper) | `created` per BOS, `confirmed`, `zone_active` |
| Liquidity pools (PDH/PDL/PWH/PWL/PWC/H4/session H-L) | `liquidity` | each level `created`→`mitigated`(=sweep)→`evicted`→`active` |
| **Liquidity SWEEP by source** | `liquidity` + Pine sweep read | `mitigated`; Pine `recentBSL`/`recentSSL` tagged **Asia/Ldn/NY High/Low**, Day/H4 — drives A+ Stage 1 |
| Session windows + session H/L | `sessions` | `in_asia`/`in_london`/`in_ny`, `closed` `SessionRange` (H/L) — **windows parameterizable** |
| NY opening range / kill zones | `sessions` | `ny_range_high/low`, `in_kz1/2/3` (ICT KZs, not course sessions) |
| VWAP context | `vwap` | line + `crossed_up`/`crossed_down` |
| Asia POC ("MV" line) | `session_volume_profile` | `poc`, `formed`, `confirmed` |
| RSI divergence confluence | `rsi_divergence` | `detected`, `bull_active`/`bear_active` |
| News blackout | `news` | `in_blackout`, `entered/exited_blackout`, `active_holiday` |
| Regime filter | `regime` | one of TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY |
| Weekly/Daily bias | *(no engine yet)* | Pine "Weekly/Daily established context"; buildable from daily bars + `liquidity` PDH/PDL/PWH/PWL |

### 10b — The existing indicator setups vs the plays
The indicator already computes three sequences (JARVIS table). **They are the plays without the
session gate:**

- **REV SETUP / A+ SETUP** (one 4-stage reversal machine, two code paths): **ARM** (RSI divergence,
  or a liquidity sweep at H4/PD/session pools) → **SOS** (same-side structure flip = CHoCH) →
  **0.5 early / 0.618+ deep fib entry** → **1m FVG confirm** → TP ladder 0.5/0.382/0.0. **This *is*
  the reversal family (plays 2, 6, 7, 8)** — but it arms on *any* sweep/div at *any* time, with no
  session or bias filter.
- **CONT** (continuation; currently dormant — compute removed to save Pine tokens): arms on a
  same-direction **15m BOS**, awaits a retrace into the BOS leg's E1–E4 fib where an FVG/Sniper zone
  sits, killed by any SOS. **This is the continuation family (plays 1, 3, 5).**

**So "recreate the plays" = wrap REV/A+/CONT with two gates the course adds and the indicator
doesn't:**
1. **Session gate** — the sweep must be of a *specific session's* liquidity (`recentBSL/SSL` source
   ∈ Asia/Ldn/NY) inside a *specific session window*, and the confirmation in the right window
   (same-session = reversal; next-session = continuation).
2. **Bias/premium-discount gate** — only trade with weekly+daily bias, and only enter in
   discount (long) / premium (short).

---

## 11 — Build & backtest path

**The scaffold already exists** — copy the `strategies/python/sos_fade/` pattern:
1. A setup **state machine** (`sequence.py` / `signals.py`) that reads per-bar engine output.
2. It consumes `backtest/replay/EngineStack.step(bar) → BarState` (structure, 4 fibs, FVG, RSI,
   liquidity, sessions).
3. `execution.py` runs fills + costs; `backtest/replay/` + `backtest/optimizer.py` backtest and sweep
   params; registered in the command-center lab as `runner="python"`.

**Gaps to close before these session plays can be built:**
- **`EngineStack` does not yet wire `order_blocks`, `vwap`, `session_volume_profile`, or
  `equal_highs_lows`.** Plays 1/3 use an **order block** as the POI → wire `order_blocks` into the
  stack first (small).
- **Session windows** — construct `SessionEngine` with the **course** windows (Asia 20:00–00:00,
  London 02:00–05:00, NY 07:00–10:00 ET) and **add Frankfurt (00:00–02:00) and Lull (05:00–07:00)**
  as extra `SessionSpec`s. The engine constructor already accepts a custom `sessions=[…]` list.
- **Weekly/Daily bias + premium/discount gates** have no engine — add a small bias module (daily-bar
  close vs prior day/week) and read the Macro fib's discount/premium zone.
- **Trading-day boundary** — course = 17:00 ET, indicator's liquidity/VWAP = 18:00 NY. Pick one
  consciously per strategy.

**Recommended build order (by proven edge, [§9](#9--the-backtested-edge-the-proof)):**
1. **NY continuation from LDN POI** (63% win) — CONT-style, needs `order_blocks` in the stack.
2. **London-sweep-Asia, strong-POI filtered** (>50%) — REV/A+-style + session gate + strong-POI grade.
3. **Frankfurt "London-sweep-Frank" family** (~26% but ~30–40% of profit) — CONT-style + Frank window.
4. **NY-sweep-of-lull mean-reversion** (~55%) — REV/A+-style + Lull window.
5. **Skip NY-sweep-Asia** (no edge).

Each becomes its own `strategies/python/mpc_*/` package, backtested on XAUUSD/EURUSD 15m (1m for the
entry feed), scored on the [§8](#8--risk-model) KPIs (PF, win rate, avg R:R) to see which prints the
most profit.

---

## Source map

| Topic | Where |
|---|---|
| Course library (transcripts + summaries) | `education/smc/` (modules 01–05) |
| Top-down bias, entry model, invalidation | `education/smc/04-the-master-key/transcripts/` |
| Core SMC vocab (structure/OB/FVG/liquidity/sessions) | `education/smc/02-smc-engine-training/transcripts/` |
| Session playbook rules | `education/smc/05-my-full-trading-strategy/transcripts/01-m15-intraday-bias-playbook.txt` |
| Backtest data synopsis | `education/smc/05-my-full-trading-strategy/transcripts/25-full-data-synopsis.txt` |
| Risk management | `education/smc/03-risk-management/` |
| Visual playbook (8 plays + 4 confluence categories) | `education/smc/playbooks/` (see its `README.md`) |
| The indicator | `indicators/engines/mpc_jarvis.pine`; strategy twin `strategies/tradingview/sos_fade_strategy.pine` |
| Canonical detectors | `engines/*/` (each has its own `CLAUDE.md`) |
| Per-bar strategy API | `backtest/replay/stack.py` (`EngineStack` / `BarState`) |
| Existing setup-as-strategy template | `strategies/python/sos_fade/` |
| Existing setups' Pine logic | `mpc_jarvis.pine` REV/A+ ~L4070–4666; MTF `f_mtfStruct` ~L1425; sweep tag ~L4045 |

*Rebuild this file if the course library, the playbook, or the indicator's setup logic changes
materially.*
