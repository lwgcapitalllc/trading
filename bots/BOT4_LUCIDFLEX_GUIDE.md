# BOT4_LUCIDFLEX_GUIDE.md
# Bot 4 — LucidFlex Prop Firm Bot (MNQ Futures)

**File:** `bots/bot4_lucidflex.py`
**Platform:** Tradovate (via `executors/tradovate.py`)
**Instrument:** MNQ (Micro E-mini Nasdaq-100) — configurable to any CME future
**Prop Firm:** LucidFlex by Lucid Trading — configurable to any firm

---

## What It Does

One bot, two modes. The same code passes the evaluation challenge and then
trades the funded account. You switch between modes by changing one line in
`config.json`. Everything else — position sizing, daily goals, drawdown limits,
profit targets — auto-calculates from the account size you set.

**Why MNQ:** Moves 200–400 points per day ($400–$800 per contract). Tight
spreads, huge liquidity, 1/10th the size of NQ so you can scale from 1 to 4
contracts without needing a large account. Perfect for $25K–$150K prop accounts.

---

## Two Modes

### Evaluation Mode (`"mode": "evaluation"`)

Goal: Pass the LucidFlex challenge in 3–5 days.

The bot is conservative and consistency-aware. It knows the 50% rule and
never lets any single day exceed 45% of the running total (5% safety buffer).
It targets a configurable daily profit and stops trading once that goal is hit.

**3-day pass plan on $50K (default config):**

| Day | Target | Running Total | Day % | Status |
|-----|--------|---------------|-------|--------|
| 1   | $600   | $600          | 100%  | Only day — fine |
| 2   | $600   | $1,200        | 50%   | Right at limit |
| 3   | $600   | $1,800        | 33%   | Comfortable |
| 4   | $600   | $2,400        | 25%   | Easy |
| 5   | $600+  | $3,000+       | <20%  | PASS |

If day 1 hits $800 the bot throttles back on day 2 to protect consistency.
If you have a $200 day the bot knows there's room to push harder next session.

### Funded Mode (`"mode": "funded"`)

Goal: Hit daily profit target, protect EOD drawdown, maximize payouts.

No consistency rule. No daily loss limit (LucidFlex funded). The bot runs a
dynamic profit engine: trades freely until daily goal is hit, then activates
peak protection, keeps trading until a 10% pullback from the peak triggers a
full stop. This locks in more than the minimum goal on good days.

**Funded daily engine example:**
- Daily goal: 2% of $53,000 = $1,060
- Bot hits $1,060 → peak protection ON → keeps trading
- Balance peaks at $55,200 → pulls back 10% from $2,200 peak
- Bot stops at $1,980 locked in → requests payout

---

## Fully Configurable

Everything in `config.json`. The bot reads it at startup and auto-calculates:

| Config field | What it controls |
|---|---|
| `account_size` | Position sizing, daily goal calculation |
| `profit_target` | When evaluation is complete |
| `max_loss_limit` | EOD drawdown floor calculation |
| `daily_profit_goal_pct` | % of balance to target per day |
| `daily_profit_goal_floor` | Minimum daily target in $ |
| `daily_profit_goal_ceil` | Maximum daily target in $ |
| `max_contracts` | Hard cap on position size |
| `mode` | `"evaluation"` or `"funded"` |
| `close_time_et` | Force-close time (default 16:30 — 15min before Lucid's 16:45) |
| `symbol` | MNQ, MES, NQ, ES, or any CME future |
| `point_value` | Dollar per point (MNQ=$2, MES=$5, NQ=$20, ES=$50) |
| `risk_pct_per_trade` | % of balance risked per trade |

**Works on any account size:**
- $25K → bot auto-caps at 2 contracts, targets $250–500/day
- $50K → up to 4 contracts, targets $500–1000/day
- $100K → up to 8 contracts, targets $1000–2000/day
- $150K → up to 10 contracts, targets $1500–3000/day

---

## Architecture — Multi-Account Scaling

```
bot4_lucidflex.py --config lucid_account1/config.json  ← Account 1
bot4_lucidflex.py --config lucid_account2/config.json  ← Account 2
bot4_lucidflex.py --config lucid_account3/config.json  ← Account 3
bot4_lucidflex.py --config lucid_account4/config.json  ← Account 4
bot4_lucidflex.py --config lucid_account5/config.json  ← Account 5
```

Each instance is a separate process with its own credentials, its own P&L
tracking, its own compliance engine. All 5 run the same strategy independently.

When the trade copier (copier.py — to be built) is enabled, one account becomes
master and the others just mirror its trades. This is more efficient — analysis
runs once, all 5 accounts execute simultaneously.

---

## Entry Logic

Same SMC framework as Bot 1, adapted for futures:

1. **Asian session range** (midnight–9:30am ET on Nasdaq)
2. **Judas Swing** — sweep of Asian range then reversal
3. **Hard H4 filter** — sweep direction must match H4 EMA 200 trend
4. **FVG** on M5 confirms displacement
5. **Confluence score ≥ 5**
6. **AI approves** ≥ 55% probability

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +1R profit | Stop to entry |
| Trailing | After BE | 1× ATR trail following peak |
| Force close | 16:30 ET | All positions closed (15min before Lucid's 16:45) |
| Compliance stop | Daily goal hit | Closes all, waits for next day |
| Drawdown stop | Balance near MLL | Closes all, logs warning |

---

## EOD Drawdown Protection

LucidFlex uses End-of-Day trailing drawdown. The bot monitors this constantly:

```
Max Loss Limit (MLL) = starting balance - max_loss_limit
Safety floor = MLL + drawdown_buffer (default $500)

If balance <= safety floor → close all, stop trading
```

On a $50K account: MLL = $47,500. Safety floor = $48,000.
The bot stops trading before you even get close to the actual limit.

**Why this matters:** If you blow the evaluation you pay another $130 to restart.
The safety buffer prevents that.

---

## Prop Firm Compliance Engine

The `PropFirmCompliance` class tracks every rule automatically:

**Evaluation mode:**
- Running profit total vs today's profit — enforces 45% daily cap (safe under 50%)
- Stops trading when daily goal hit
- Detects when profit target is reached
- Logs end-of-day summary with progress toward target

**Funded mode:**
- Dynamic profit engine — runs until peak protection triggers
- EOD drawdown buffer always active
- Payout eligibility tracking (5 profitable days for LucidFlex)

---

## File Structure

```
bots/
└── bot4_lucidflex.py

executors/
└── tradovate.py              ← Tradovate API connection layer

markets/futures/instances/
├── lucid_account1/
│   ├── config.json           ← All settings (committed to GitHub)
│   ├── credentials.json      ← NEVER committed — create manually on VPS
│   ├── credentials.template.json
│   ├── bot4.log
│   ├── bot4_trades.json
│   ├── bot4_daily.json
│   ├── bot4_equity.json
│   └── bot4_model.pkl
├── lucid_account2/           ← Identical structure
├── lucid_account3/
├── lucid_account4/
└── lucid_account5/
```

---

## Setup — Step by Step

**1. Buy a LucidFlex $50K evaluation at lucidtrading.com**

Use discount codes — Lucid regularly runs 30–50% off. Check their Discord or
affiliate links for current codes. At $130 one-time fee (or less with discount)
this is the cheapest entry point in prop trading.

**2. Connect Tradovate**

Lucid uses Tradovate as its execution platform. After purchasing:
- Log into your Lucid dashboard
- Connect your Tradovate account
- Note your Tradovate username, password, and account ID

**3. Create credentials.json on VPS**

```bash
ssh forexvps
```
Then on VPS:
```
C:\algos\markets\futures\instances\lucid_account1\credentials.json
```
```json
{
    "username":    "your_tradovate_username",
    "password":    "your_tradovate_password",
    "account_id":  12345678,
    "environment": "demo"
}
```
Set `"environment": "live"` when ready to trade the funded account.

**4. Install dependencies**

```bash
ssh forexvps "pip install aiohttp websockets pandas numpy"
```

**5. Add Task Scheduler task**

Name: `FUTURES_MNQ_Bot4_Account1`
Command:
```
python C:\algos\bots\launcher.py --bot bot4 --config C:\algos\markets\futures\instances\lucid_account1\config.json
```

**6. Add to algo.py LOG_MAP and TASK_BOT_MAP**

```python
LOG_MAP = {
    ...
    "FUTURES_MNQ_Bot4_Account1": ("futures", "lucid_account1", "bot4.log"),
    "FUTURES_MNQ_Bot4_Account2": ("futures", "lucid_account2", "bot4.log"),
}
TASK_BOT_MAP = {
    ...
    "FUTURES_MNQ_Bot4_Account1": "bot4",
    "FUTURES_MNQ_Bot4_Account2": "bot4",
}
```

**7. Start**

```bash
algo start
```

Or for a single account:
```bash
algo
# Select [4] Manage individual bot → FUTURES_MNQ_Bot4_Account1 → Start
```

---

## Switching from Evaluation to Funded

Once Lucid upgrades your account to funded (usually 5–10 minutes after passing):

1. Open `config.json` on VPS
2. Change `"mode": "evaluation"` to `"mode": "funded"`
3. Change `"environment": "demo"` to `"environment": "live"` in credentials.json
4. Restart bot: `algo restart`

That's it. The same bot, the same strategy, just with the funded ruleset now active.

---

## Scaling to 5 Accounts

```
lucid_account1/config.json  ← Account 1 (first eval)
lucid_account2/config.json  ← Account 2 (start after Account 1 passes)
lucid_account3/config.json  ← Account 3
lucid_account4/config.json  ← Account 4
lucid_account5/config.json  ← Account 5 (max Lucid allows)
```

Each config is identical except `account_id` in credentials.json.
All 5 Task Scheduler tasks point to the same `bot4_lucidflex.py`.
All 5 show up in `algo` control panel under FUTURES.

**Revenue at 5 funded accounts:**
- $2,000 per payout cycle per account (LucidFlex $50K cap)
- 5 accounts × $2,000 = $10,000 per cycle
- Cycles every ~5 profitable trading days
- Roughly $40,000/month at max capacity

After 6 payouts per account → LucidLive (real capital, $2,000 cash bonus at $50K)

---

## Lucid vs Tradeify — Strategy

**Phase 1 (now): Lucid only**
- 5 × LucidFlex $50K
- One-time fees (~$130 each)
- No bot verification required
- Same bot across all accounts freely
- Target: $10,000/payout cycle

**Phase 2 (after Lucid is running): Add Tradeify**
- Tradeify requires: bot exclusively theirs, video verification of you enabling it
- Build a SEPARATE dedicated bot for Tradeify (do NOT share bot4)
- 5 × Tradeify Select $50K
- 100% of first $15,000 in profits (better split than Lucid)
- Additional $10,000+/cycle

**Why Lucid first:**
- One-time fee vs Tradeify's monthly subscription (~$111/mo)
- No video verification requirement
- No cross-firm bot restriction
- Faster to get started

**Why add Tradeify later:**
- 100% profit split on first $15K is exceptional
- Max 5 funded accounts same as Lucid
- Combined: 10 accounts × $2,000+ = $20,000+ per cycle

---

## Log Messages to Watch

```
BOT 4 -- LucidFlex | MNQ | EVALUATION                        ← startup
Account: $50,000 | Target: $3,000 | Daily goal: 2.0%         ← config loaded
Connected | Balance: $50,000.00                               ← tradovate connected
Scanning | MNQ=18542.50 | H4=bullish | ATR=45.20             ← active scan
Asian range: H=18610.00 L=18490.00                           ← range detected
H4 FILTER: sweep=bearish but H4=bullish. Counter-trend blocked. ← filter working
SIGNAL | BULLISH | score=6 | AI=62% | R:R=2.1               ← trade signal
ORDER PLACED | Buy 2x MNQ | SL=18495.00 TP=18640.00         ← order placed
T12345 -> BREAKEVEN @ 18542.50 (1.0R)                       ← BE hit
DAILY GOAL HIT: +$620 (target $600). Stopping for today.    ← eval mode stop
EVAL | day=3 | total=$1,820 (61% of target) | today=+$620   ← progress
EVALUATION COMPLETE! Profit target hit: $3,040 / $3,000     ← PASSED!
FUNDED | today=+$1,240 | peak_protection=ON                 ← funded mode
PEAK PROTECTION: pulled back $180 from peak +$1,800.        ← day locked
FORCE CLOSE: 16:30 ET reached. Closing 2 position(s).      ← eod close
New day | $51,840.00 | FUNDED | today=+$0                   ← next day reset
```

---

## Tuning Guide

| Problem | Config field | Adjustment |
|---|---|---|
| Passing too slow | `daily_profit_goal_pct` | Raise 2.0 → 2.5 |
| Consistency violations | `daily_profit_goal_ceil` | Lower 600 → 400 |
| Too few signals | `min_confluence_score` | Lower 5 → 4 |
| Stops hit too quickly | `atr_sl_multiplier` | Raise 1.2 → 1.5 |
| AI too slow to train | edit `shared_ai_brain.py` MIN_TRADES_TRAIN | Lower to 10 |
| Funded: giving back gains | `trail_atr_mult` | Lower 1.0 → 0.8 |
EOF
echo "Guide created"