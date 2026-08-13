# Copy Trading Roadmap

**Status:** ⏸️ **PARKED, and blocked on two separate things.** Stages 1–2 and 5 are live; **stages 3–4 need API keys that do not exist yet**, and the Smart Money UI has been flagged OFF in `command-center/frontend/src/lib/features.ts` since 2026-08-04 — nothing was deleted, one boolean restores it. Read this as a plan awaiting a decision, not as work in flight.

From a periodic batch scanner to a live, automated copy-trading system.

---

## Current State

The pipeline is a **batch research tool** — you trigger it manually, it scans
the Hyperliquid leaderboard, profiles every wallet, and ranks qualified
candidates. The output is a report; no trades are executed.

---

## Phase 1 — Find the Right Config (Now)

### What the simulation told us

`simulate_configs.py` ran 3,780 config combinations against 814 wallets
already in the DB. Key findings:

| Observation | Detail |
|---|---|
| Net losers | 51% of active, experienced wallets have negative total PnL |
| Hard ceiling | Maximum possible qualified traders under any config: **23** |
| Current config → qualifiers | **1** (too restrictive for this leaderboard) |
| Biggest blocker | Peak drawdown at 20% cuts 133/250 remaining wallets (53%) |
| Second blocker | Strike system (per-window win rate) cuts 69/270 (25%) |

### Recommended "balanced copy-trade" config

Apply this to `config/config.json` (or use `python simulate_configs.py --apply-best`
to patch the best grid result automatically):

| Setting | Current | Recommended | Reason |
|---|---|---|---|
| `min_win_rate` (per window) | 75% | **55%** | 75% leaves only 5 wallets; 55% gives 18–22 |
| `min_overall_win_rate` | 55% | **50%** | Meaningful floor; crypto traders win ~55% |
| `max_inactive_days` | 60 | **30** | Copy trading requires ACTIVE wallets |
| `max_drawdown` | 20% | **30%** | 20% is unusually tight for crypto vol |
| `min_trades` | 100 | 100 | Keep — sufficient track record |
| `min_span_days` | 90 | 90 | Keep — 3 months minimum history |

Expected result with recommended config: **~15–20 qualified traders**.

### Action

1. Update `config/config.json` with the values above
2. Clear the fills cache (24h TTL, or use the dashboard "Clear cache" button)
3. Run a fresh full scan: `python run_stage1.py`
4. Review the top 20 in the dashboard

---

## Phase 2 — Daily Automated Scanning (Near-term)

**Goal:** The system checks for new/disqualified traders every day without
manual intervention and sends an alert when the watchlist changes.

### Architecture

```
cron / launchd (daily 02:00)
        │
        ▼
  scheduler.py
        │
        ├─ run_stage1.py --dry-run   (re-profile from fills cache — fast, ~30s)
        │
        ├─ weekly: run_stage1.py     (fresh API fetch — clears cache, ~15 min)
        │
        └─ diff_watchlist.py
                │
                ├─ new qualifiers   →  Telegram alert: "🟢 New trader qualified: 0xABCD"
                ├─ disqualified     →  Telegram alert: "🔴 0xABCD disqualified: strike system"
                └─ reinstated       →  Telegram alert: "🟡 0xABCD reinstated after 2 clean months"
```

### Files to build

| File | Purpose |
|---|---|
| `scheduler.py` | Entrypoint for daily cron — decides dry-run vs full scan |
| `watchlist.py` | Reads current qualified candidates from DB; compares to previous day |
| `diff_watchlist.py` | Diffs current vs previous snapshot; emits change events |
| `notifier.py` | Sends Telegram messages (reuse algos/ Telegram infra or standalone) |
| `config/watchlist.json` | Persisted snapshot of last notified qualification state |

### Cron entry (macOS launchd or crontab)

```bash
# Daily at 02:00 — full scan on Sunday, dry-run Mon–Sat
0 2 * * 0 cd /Users/alwg/trading/smart-money && python scheduler.py --full
0 2 * * 1-6 cd /Users/alwg/trading/smart-money && python scheduler.py --dry-run
```

### Key design decisions

- **Dry-run Mon–Sat** re-profiles from the 24h fills cache. This takes ~30 seconds
  and keeps metrics current without hammering the API.
- **Full scan Sunday** clears the cache and re-fetches all fills. This captures any
  new wallets on the leaderboard and updates hold-time / win-rate for existing ones.
- **Snapshot diff** compares today's qualified list to yesterday's. A wallet that
  was qualified yesterday and is not today has been disqualified. Vice versa for
  new qualifiers.
- **Strike system state** is already tracked in `monthly_windows.strike_level` in
  the DB — the notifier can read it directly.

---

## Phase 3 — Live Trade Mirroring (Medium-term)

**Goal:** The moment a tracked trader opens or closes a position, replicate it
on your copy account automatically, scaled to your account size.

### How Hyperliquid enables this

Hyperliquid exposes a **WebSocket API** (`wss://api.hyperliquid.xyz/ws`) with
a `userFills` subscription. You can subscribe to any public wallet address and
receive real-time fill notifications.

Execution uses the **Hyperliquid REST API** with your own API key (generated
from the app). Alternatively, Hyperliquid supports "agent wallets" — a
sub-wallet that can trade on behalf of your main wallet without holding funds.

### Architecture

```
WebSocket subscriber
  └─ subscribes to fills for each address in watchlist
        │
        ▼
  trade_mirror.py
        │
        ├─ parse fill: coin, side, size, price
        ├─ scale size: your_allocation / trader_account_value
        ├─ risk check: daily_loss_limit, max_open_positions, max_size_usd
        └─ execute: POST https://api.hyperliquid.xyz/exchange
```

### Position sizing

```
your_trade_size = (your_allocation_usd / trader_account_value_usd) × trader_trade_size
```

Example: trader has $50,000 account, opens 1 BTC long. You allocate $5,000 → copy 0.1 BTC.

### Key files to build

| File | Purpose |
|---|---|
| `live/ws_subscriber.py` | WebSocket client; subscribes to `userFills` for watchlist |
| `live/trade_mirror.py` | Fill parser + scaling logic + execution |
| `live/risk_manager.py` | Daily loss limit, max position size, max open positions |
| `live/copy_account.py` | Hyperliquid API wrapper for your copy account |
| `config/copy_config.json` | Per-trader allocation %, daily loss limit, max position |

### Watchlist gating

Only wallets that have **passed the qualification pipeline** AND have been on
the watchlist for a minimum number of days (e.g. 14 days observation) are
eligible for live mirroring. This prevents copying a wallet that qualified
but immediately disqualifies next month.

---

## Phase 4 — Vault Copy Trading (Longer-term)

**Goal:** Simplest possible copy execution — deposit funds into the trader's
own Hyperliquid vault.

### How it works

Some qualified traders run **Hyperliquid vaults** — shared pools that execute
the manager's trades proportionally for all depositors. When you deposit, your
funds move in lockstep with the manager's strategy automatically.

### Identifying vault managers

During wallet profiling, check if the wallet address is also a vault contract:
```
GET https://api.hyperliquid.xyz/info
body: {"type": "vaultDetails", "vaultAddress": "<address>"}
```

If the wallet has an active vault with open deposits, it's a Vault Manager.
Depositing into their vault replaces the need for live mirroring entirely.

### Trade-offs vs live mirroring

| | Vault Copy | Live Mirror |
|---|---|---|
| Execution complexity | None — Hyperliquid handles it | High — you build the infra |
| Latency | Zero — happens natively | 100–500ms depending on feed |
| Slippage | Shared with vault | Your own execution |
| Control | None — can only deposit/withdraw | Full control over sizing |
| Risk | Vault manager takes % fee | No fee, but your infra failure |

Use vault copy where available; live mirroring as fallback for non-vault managers.

---

## Phase 5 — Risk Framework (All Phases)

Before copying any real money, these limits must be enforced:

| Limit | Suggested Value | Rationale |
|---|---|---|
| Max allocation per trader | $5,000 or 10% of copy capital | Concentration risk |
| Max total copy capital | 20% of total trading capital | Drawdown containment |
| Daily loss limit per trader | 3% of allocation | Stop copying if DD spikes |
| Max open positions | 3 simultaneously | Liquidity & risk management |
| Min observation days | 14 | Stability check before live copy |
| Stop copying if disqualified | Immediate | Trust the pipeline |

---

## Implementation Sequence

| Phase | Status | Estimated effort |
|---|---|---|
| 1 — Config tuning + fresh scan | **Ready now** | 10 min |
| 2 — Daily automated scanning + alerts | Not started | 1–2 days |
| 3 — Live WebSocket mirroring | Not started | 3–5 days |
| 4 — Vault copy integration | Not started | 1 day (once Phase 3 done) |
| 5 — Risk framework | Partially designed | 1 day (integrated with Phase 3) |

---

## Data Source Expansion (Parallel to Phases 1–3)

The simulation ceiling of 23 traders is entirely a **leaderboard coverage problem**,
not a code problem. The Hyperliquid leaderboard shows the top ~3,000 wallets by
all-time PnL — most are not consistently profitable; they hit big once and then lose.

To find more qualified traders:

1. **Expand Hyperliquid leaderboard depth** — currently capped at top 3,000. Try
   scanning the next 3,000–10,000 (mid-tier traders often have more consistent
   performance than the PnL-maximizers at the top).

2. **Hyperliquid vaults leaderboard** — separate endpoint lists all active vaults
   ranked by return. Vault managers are directly copyable and pre-selected for
   having external depositors (social proof).

3. **Myfxbook / FX Blue** (Stage 4) — adds verified FX traders who use MT4/MT5.
   These are an entirely separate pool with different characteristics.

4. **Drift Protocol (Solana)** — Drift has a similar perpetuals leaderboard (Stage 3).
   Different market, potentially less survivorship bias than Hyperliquid.
