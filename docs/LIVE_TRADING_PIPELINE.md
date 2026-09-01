# Live Trading Pipeline — Python strategy → MT5 demo account

**Purpose:** The build plan that takes a validated `strategies/python/` bot from the backtest lab to
placing real orders on a chosen MT5 terminal, controlled from the command center Bots page.
**Scope:** The live runtime, the order bridge, per-bot control, Telegram alerts, trade logging,
log backup, and version pinning. It does NOT change strategy logic, engines, or the backtest lab.
**Status:** IN BUILD — steps 1-4 done (the minimum-stop guard, secrets out of git, pending orders +
the broker-clock fix, and the `algos/live/` runtime), and **the first bot is configured, deployed and
proven to start on the VPS** (see *First VPS startup* below). Steps 5-9 open; 7 and 9 still need the
Telegram token and a deliberate `exec_risk_pct`.
**Created:** 2026-07-30. **Last updated:** 2026-07-31.
**Owner requirements this satisfies (Aaron, 2026-07-30):** start/stop/restart individual bots from
the Bots page without touching the others · Telegram on trade entry and trade exit only (exit
carries P&L) · Aaron names which MT5 instance each bot trades · lab work on a strategy must never
change what the live bot is running · always know exactly which version is trading · every trade and
its confluences logged and answerable later · logs backed up daily.

---

## 1. The one-paragraph answer

Roughly 70% of this already exists and 30% does not. The strategy is done and Pine-parity green. The
engines are done. The bar-by-bar driver (`EngineStack.step` → `strategy.step`) is the *same object*
live and in backtest, so there is no strategy rewrite. The MT5 connection layer, the Task Scheduler
boot chain, the per-bot state file, the crash monitor and the entire command-center Bots page
(including per-bot start/stop/restart over SSH) were all built for the deleted 2026-06 bot suite and
were deliberately kept. **What is missing is the middle: a live runner that turns closed bars into
strategy steps, and an order bridge that turns the strategy's intent into MT5 orders.** Plus four
smaller things — pending-limit support in `mt5_ops.py`, the broker-clock fix on the live bar feed, a
new Telegram token, and version pinning so the lab and the live bot cannot collide.

---

## 2. What we have

### 2.1 Strategy layer — DONE, no changes needed

| Piece | Where | State |
|---|---|---|
| MPC SOS Fade (A+) | `strategies/python/mpc_sos_fade/` | Pine-parity GREEN 2026-07-29, 21,494 bars |
| MPC B-LEG | `strategies/python/mpc_bleg/` | Pine-parity GREEN 2026-07-29 |
| Per-bar driver | `MpcSosFadeStrategy.step(bar_state)` | Already the live seam — one closed bar in, one `Decision` out |
| Self-sizing | `exec_risk_pct` (default 10) | The strategy computes its own lot size; the lab's sizing engine is bypassed (`self_sizing: True`) |
| Confluence records | `execution.blocks` / `execution.misses` | Every refused and every died setup, with reasons — already structured for logging |

The strategy is a **pure function of the bar stream**. It has no I/O, no clock, no broker. That is
what makes the live wiring a thin layer rather than a port.

### 2.2 Engine layer — DONE

Eleven canonical engines under `engines/`, all Pine-parity validated. They are **stateful streaming**
engines: feed them bars in order and they build their own state. Live, this means the bot must replay
N historical bars at startup to warm them before the first real decision. That is a loop, not a
feature build.

### 2.3 Replay infrastructure — DONE, reusable live

- `backtest/replay/EngineStack.step(bar)` — drives all engines in Pine order, returns a `BarState`.
  Identical live.
- `backtest/replay/iter_bars(df)` — turns a canonical frame into `ReplayBar`s.
- `backtest/data/` — MT5 bar pull, disk cache, measured history floors. Useful for the **warmup
  fetch**, though live warmup can come straight off the trading terminal instead.

### 2.4 Live MT5 plumbing — BUILT, currently unused

Everything here was kept when the first bot suite was deleted (`algos/docs/BOT_DEPLOYMENT_INFRA.md`).

| Piece | Where | What it gives us |
|---|---|---|
| `BotMT5` | `algos/shared/mt5_ops.py` | Terminal binding by explicit `mt5_path` (this is how "which MT5 instance" is answered), login, **account-number guard that refuses to trade the wrong account**, connection lock, market orders, `move_sl`, `partial_close`, `close_position`, `lot_size`, `recover_open_positions` |
| Instance configs | `algos/markets/fx/instances/<name>/config.json` + `bots/bot_utils.py` | Account, symbol, risk, params — never hardcoded. Loader + logger + path resolver |
| Boot chain | `algos/scheduler/*.xml`, `bots/launcher.py`, `bots/startup_coordinator.py` | Auto-start on VPS boot, bots started one at a time so they don't race the MT5 connection |
| Connection lock | `algos/mt5_connect.lock` | Stops two bots initializing the same terminal at once |
| Liveness | `algos/shared/bot_state.py` | `bot_state.json` per instance — heartbeat, status, balance, daily/weekly P&L |
| Crash alerts | `algos/notifications/monitor.py` | Watches for stale logs / dead processes, alerts Telegram |
| Broker clock | `algos/markets/fx/tools/broker_clock.py` | MT5 server time → true UTC, DST-aware, **measured not assumed**. Critical and already solved |

### 2.5 Command center Bots page — BUILT AND WIRED, registry empty

`command-center/backend/routers/bots.py` already implements, over SSH:

- `GET /bots/snapshot` — one batched SSH call, returns every bot's status, balance, P&L, uptime
- `POST /bots/{name}/start | stop | restart` — **per-bot, does not touch other bots.** Start launches
  `startup_coordinator.py --bot <key>` through WMI so the child survives the SSH session closing;
  stop kills only the `python.exe` whose commandline carries that bot's key
- `POST /bots/start | stop | restart | emergency` — the global versions
- `GET /bots/{name}/log` — tail a bot's stdout log
- `PATCH /bots/{name}/config` and `/caps` — edit params, commit, push, VPS pull, restart that bot
- Telegram user management

The frontend (`frontend/src/pages/Bots/`) already renders the per-bot table with those buttons.

**The only reason the page shows nothing is that six module-level dicts are empty** —
`_BOT_DISPLAY_ORDER`, `_DISPLAY_NAMES`, `_TASK_BOT_KEYS`, `_LOG_MAP`, `_BOT_INSTANCE_MAP`,
`_SUPPRESS_KEYS`. Registering a bot is filling those in. **This is the cheapest item in the whole
plan and it delivers Aaron's headline requirement.**

### 2.6 Audit log — BUILT, unwired

`command-center/backend/services/decision_log.py` — `TradeDecision` / `DecisionLog`. One JSONL record
per signal (taken or not): the idea, every gate's verdict in order, the sizing decision, and the full
life of a taken trade. Its docstring already says it is meant to be *identical in backtest and live*.
It has never been called from anywhere live.

---

## 3. The gaps

Ordered by how much they block. Every one of these is real work, not a config change.

### G1 — There is no live runner (the biggest gap) — **BUILT 2026-07-30, see step 4**

Nothing turns "a 15m bar just closed on the broker" into `strategy.step(bar_state)`. Needed:

1. Connect to the named terminal, guard the account number.
2. Pull N historical bars, convert to canonical UTC frame, replay them through a fresh `EngineStack`
   + strategy **without acting on any decision** — this is engine warmup.
3. Poll for a newly *closed* bar, step it, act on the decision, sleep, repeat.
4. Heartbeat to `bot_state.json` every cycle so the monitor and the Bots page see it alive.
5. Handle weekend/market close, terminal disconnect, and reconnect.

Warmup depth matters: the liquidity engine needs previous-week levels and the RSI engine needs
`rsi_valid_bars=100`. Budget ~2,000 15m bars (~3 weeks of trading) minimum; 5,000 is safer and costs
nothing but startup seconds.

### G2 — There is no order bridge — **BUILT 2026-07-30, see step 4**

The strategy's `Execution` is a **broker emulator**. It holds its own resting limits
(`_pend_long`/`_pend_short`), its own position (`_pos_dir`, `_qty`, `_entry`, `_sl`, `_stage`), and it
fills them itself against bar OHLC. Live, MT5 is the broker. Something has to reconcile the two.

**Recommended design — mirror mode.** The strategy stays authoritative for *levels and intent*; the
bridge makes MT5 match, then feeds reality back:

```
bar closes → strategy.step() → read strategy's DESIRED state
                                 ├── wants a resting long limit @ P, stop S, qty Q  →  ensure that
                                 │    pending order exists on MT5 at that price/qty/SL
                                 ├── wants no order that side                        →  cancel it
                                 └── holds a position with stop S'                   →  move_sl to S'
MT5 fills/stops out → read the REAL fill → feed it back into the strategy's state → log it
```

Why mirror and not a rewrite: it preserves the parity that was expensive to earn. The decision stream
that `compare_strategy.py` proves bar-for-bar is the exact same stream driving live orders.

**The one honest caveat:** the strategy's emulator and MT5 will not agree perfectly. A real limit can
fill at a marginally different price, and a real stop fills intrabar in continuous time while the
emulator resolves it at bar granularity. That is the same class of difference as tick-mode vs
bar-mode in the lab — an improvement in realism, not drift. The bridge must **overwrite the
emulator's fill price with the broker's actual fill** so the two do not diverge cumulatively, and log
every correction.

**Simplification worth knowing:** at the shipped `exec_tp1_pct = exec_tp2_pct = 0` there are **no
scale-outs**. Live, each trade is one entry limit + one stop that ratchets each bar close. No partial
closes, no TP orders. The bridge is much smaller than the exit-ladder table suggests.

### G3 — `mt5_ops.py` cannot place a pending limit order — **CLOSED 2026-07-30**

`place_order()` sends `TRADE_ACTION_DEAL` — a market order only. The A+ entry is a **resting limit**.
Missing methods: `place_pending_limit()`, `modify_pending()`, `cancel_pending()`,
`get_pending_orders()`. Roughly 120 lines against `TRADE_ACTION_PENDING` /
`TRADE_ACTION_MODIFY` / `TRADE_ACTION_REMOVE`, following the existing `place_order` shape.

### G4 — The live bar feed labels broker time as UTC — **CLOSED 2026-07-30**

`BotMT5.get_candles()` does `pd.to_datetime(df["time"], unit="s", utc=True)`. MT5 returns **broker
server time**, not UTC. This is the exact bug `broker_clock.py` was written to fix on the lab agent —
it was 2–3 hours off, and it silently moves every session boundary the sessions, liquidity and VWAP
engines depend on. Those are precisely the engines A+ trades off.

`broker_clock.to_utc()` exists and is measured, but `mt5_ops.py` does not use it. Must be wired, and
**the offset must be re-measured on the live terminal** — `broker_clock.py`'s own docstring warns
that an earlier version passed its unit tests and was still wrong. `backtest/tools/compare_feeds.py`
is the tool; it must read a flat 0h across a window spanning a DST transition.

### G5 — Broker and symbol are not the backtest broker

The strategy was validated against **Vantage demo XAUUSD** (chosen so it matches the
`VANTAGE_XAUUSD` TradingView feed the Pine was written on). `backtest/CLAUDE.md` states live trading
has historically been PU Prime, where the gold symbol is `XAUUSD.s`. Whichever terminal Aaron names
brings its own symbol name, spread, swap, tick size, minimum stop distance and **server clock
offset**. None of that is fatal; all of it must be declared per instance and measured once, not
assumed.

**2026-08-05 — the MEASUREMENT is now instrumented, and arming the bot is what it was for.** The
2026-08-04 shadow diff already showed the two feeds differ by a systematic 4-5 cents (Vantage above
PU Prime on every one of 148 bars), and the jitter audit showed that ±$0.05 per bar churns ~6% of
the trade list. So the gap is real and the only thing that can close it is PU Prime's own fills.

🔴 **It could not have been closed as the code stood.** `mt5_ops.get_deal_result` returns MT5's
`d.profit` — the **price move only** — read off the **closing deal alone**. Swap was dropped and
commission, which brokers normally book on the **entry** deal, was never fetched. The first live
trade would have written a `pnl_usd` that disagreed with the account balance under a name that
gives a reader no reason to check it. Fixed with `mt5_ops.get_deal_breakdown()`, which sums every
deal of the position and reports `gross_usd` / `swap_usd` / `commission_usd` / `net_usd`
**separately**; `live/ledger.py::trade_closed` writes all of them plus the fill-vs-intended entry
price. `pnl_usd` and the R are now NET.

⚠ **The parts are kept rather than only the total, and that IS the measurement** — a netted number
cannot be taken apart afterwards; gross + swap + commission can always be re-netted.
⚠ **Swap keeps MT5's own sign.** Gold's short swap is a CREDIT; a field that cannot be positive
cannot measure a broker that pays you (the command center made exactly this mistake on 2026-08-03
and overstated fees by 25%).
⚠ **`None` = could not ask, `0.0` = charged nothing.** `deals: 0` is what an unreachable terminal
returns, and writing its zeros down would fabricate a measurement.

**2026-08-06 — MEASURED, and the cost model now carries PU Prime's own numbers.**
`algos/tools/broker_facts.py --history-days 3` reads the live MT5_FFT terminal's own tick store
instead of waiting for sessions to come round, which is what made this answerable in one run:
**1,893,438 ticks over 3 whole days**, against the 120-second London/NY snapshot the first attempt
managed. Read-only; it attaches to the running terminal and asserts the account before printing.

| | PU Prime (live) | Vantage (every backtest) | was in `fills.py` |
|---|---|---|---|
| spread, median | **$0.32** | $0.22 | 0.33 (688k ticks, 2026-07-14) |
| spread, p99 / max | $0.37 / $0.39 | 0.31 (p99) | — |
| swap LONG /lot/night | **−79.60** | −74.84 | −78.29 (2026-07-16) |
| swap SHORT /lot/night | **+30.25** (a credit) | +26.98 | +29.49 |
| broker min stop | 20 pts = **$0.20** | — | not modelled |
| commission | **$0.00** (demo) | $0.00 | 0.00 |

✅ **WHAT IT COSTS, replayed rather than estimated — 155,531 M15 bars, 2020-01-01 → 2026-08-03, one
real replay per row at the shipped defaults:**

| | trades | total R | max DD | cost vs free |
|---|---|---|---|---|
| free (no costs) | 159 | +142.18R | 5.61R | — |
| Vantage costs | 159 | +130.59R | 6.23R | 11.59R |
| **PU Prime costs** | 159 | **+127.91R** | 6.83R | **14.27R** |

**So trading this on the real broker costs 2.68R more than every cost table in this repo says —
23% more cost, and max drawdown 5.61R → 6.83R.**

🔴 **And 89% of that gap is the SPREAD, not the swap, which is the opposite of what the swap's size
suggests.** Isolated by replaying each layer alone:

| | spread alone | swap alone | together |
|---|---|---|---|
| Vantage | 5.28R | 6.31R | 11.59R |
| PU Prime | **7.67R** | 6.60R | 14.27R |
| gap | **+2.39R** | +0.29R | +2.68R |

Swap is the bigger cost on both brokers, but it barely differs BETWEEN them — PU Prime's worse long
swap (−79.60 vs −74.84) is almost exactly cancelled by its better short credit (+30.25 vs +26.98),
and this strategy trades both sides. The spread is 45% wider and nothing offsets it.
⚠ The layers are additive here (5.28 + 6.31 = 11.59 exactly, and 159 trades in every row), which
says no trade was added or removed — a cost changes what a trade MAKES, never whether it happens.

⚠ **The spread is FLAT at $0.32 in 22 of the 23 traded hours.** The 21:00–22:00 UTC daily break has
no ticks at all, and the hour that REOPENS after it is the only wide one (median $0.35, p99 $0.39).
So on this broker the reopen is where the spread lives, not the session — and a fixed marked-up
spread is confirmation this demo is the commission-free STANDARD tier rather than a raw one.

🔴 **A SWAP IS NOT A CONSTANT, and that is the transferable half.** The values in `fills.py` were
read on 2026-07-16 and were 1.7% / 2.6% adrift three weeks later. Nothing announced it and nothing
could have caught it: a swap is read once, hardcoded, and then quietly describes a rate the broker
has moved on from. Swap is also the LARGEST re-priceable cost on this strategy. **Re-run
`broker_facts.py` before quoting any cost figure.**

**Still open, and narrower than it was:** **commission** is `$0.00` on the standing fact that demos
do not charge, and no live fill has confirmed it — `get_deal_breakdown` records it per trade and
will. The **minimum stop distance** is measured at 20 points ($0.20) but has still never been
recorded against a real refusal; note our own `exec_min_stop_mode` floor of 0.08% (~$3.20 on
$4,000 gold) binds ~16x earlier, so the broker's limit should never be the one that bites.
**Three days is three days** — it covers every hour but no weekend and no major news cycle.

#### G5a — WHICH PU PRIME ACCOUNT TYPE — ✅ **ANSWERED 2026-08-10: ECN · DEPLOYED 2026-08-12**

🟢 **The tiers were MEASURED on an open market, and the answer is ECN.** Everything below this
box was decided on figures off a marketing page; the table that decides it now is ours.

🟢 **AND IT IS NOW WHAT THE BOT ACTUALLY TRADES.** On 2026-08-12 Aaron logged `MT5_FFT` into the
ECN demo and `mpc_sos_fade_demo` moved with it: **700107749 / `XAUUSD.s` → 700152905 /
`XAUUSD.p`**, `account_profile` `puprime_standard` → `puprime_ecn`. Verified live — connected
`#700152905 / $9,996.99`, warmed 5,000 bars, 0 errors, 0 halts. The old account's $9,996.99 (grown
from $2,000) does not travel; 700152905 opens at $10,000.

⚠ **The question everybody asks, answered once here so it is not re-derived: how is ECN cheaper
when it charges commission and Standard charges none?** Put both costs in ONE unit — gold is 100 oz
per lot, so $1.00/lot/side is **$0.01 per ounce per side**. Round trip per ounce: **Standard $0.31 +
$0.00 = $0.31 · Prime $0.12 + $0.07 = $0.19 · ECN $0.12 + $0.02 = $0.14.** Standard charges $0.19 of
hidden spread markup to save $0.02 of visible commission. ⚠ **Swap is IDENTICAL on all three tiers,
so swap cannot pick an account** — that is the natural guess and it is false.

✅ **`SPREAD_UNMEASURED` IS RETIRED FOR ECN AS OF 2026-08-14 — AND FOR ECN ONLY.** Aaron left
`MT5_FFT` logged into 700152905 for several days, so the terminal finally held the tick history the
refusal was waiting on: `broker_facts.py --bot mpc_sos_fade_demo --history-days 6` read
**3,033,270 ticks over 5 whole days**, median **$0.12**, p99 $0.18, max $0.19, across **all 23
traded hours** — including the 22:00 UTC reopen that was the named blocker (median $0.16, p99
$0.19, i.e. the one wide hour, exactly as on Standard). `backtest/fills.py` now carries
`_SPREAD_XAUUSD_PUPRIME_ECN = 0.12` and `cost_tiers.py` needs no `--spread` flag for that row.

⚠ **No stored run re-prices.** `spread_or_refuse()` RAISED for this tier, so nothing that ever
completed charged an ECN spread, and every figure in the table below was produced with
`--spread puprime_ecn=0.12` — the same number, labelled `stated`. Re-run 2026-08-14 with it
measured: **ECN 157 trades / +151.39R**, identical to the cent.

🔴 **PRIME KEEPS THE SENTINEL AND THAT IS DELIBERATE, NOT AN OVERSIGHT.** Prime and ECN are
indistinguishable on every field this terminal publishes, so "they're obviously the same, copy it
across" is available as an argument again — and it is precisely the argument that put Standard's
$0.32 on all four tiers and was wrong by 2.7x. A terminal can only hold the ticks of the account it
is logged into. Close Prime the same way: sit `MT5_FFT` on 700152904 for a day and re-run.

⚠ **The tool also read the SWAP at −81.18 / +31.29**, against the −79.60 / +30.25 that
`fills.py::_XAUUSD_SWAP` still carries (2.0% / 3.4% adrift in six days). **Deliberately NOT changed
in this pass** — swap is the largest re-priceable cost on this strategy, so moving it re-prices
every charged figure in the repo and belongs in its own commit with the affected numbers restated.
It is recorded here so the drift is not discovered again from scratch.

🔴 **THE MOVE FOUND THREE DEFECTS AND NONE OF THEM RAISED ANYTHING** — full write-ups in
`algos/CLAUDE.md`, named here because each is a hazard of *moving a live bot between accounts*
rather than of this account:

1. **The spread sampler called an unwatched symbol a shut market.** MT5 streams ticks only for
   symbols in Market Watch, and the new account had never been asked to watch `XAUUSD.p`.
2. **`starting_balance` followed the bot instead of staying with the account.** The $2,000 anchor
   from the Standard demo would have reported **+399%** on a fresh $10,000 account, for ever.
3. **Nothing re-checked WHICH account the terminal was on.** `connect()` asserts it once; for two
   hours afterwards the bot read the new account's balance believing it was on the old one, and
   **re-anchored its sizing from $1,992.21 to $9,996.99**. The runtime-reload guard fired and was
   not enough — it watches the config FILE, and what moved was the TERMINAL.

**Before moving any bot to a different account, read those three.** The sequence that works:
stop the bot → edit the four fields together (`account`, `symbol`, `strategy_params.symbol`,
`strategy_params.account_profile`) → add the login to `credentials.json` on the VPS → clear
`starting_balance` → check the new account is clean → start.

| tier | account | spread (median) | commission /side /lot | swap long / short | min stop |
|---|---|---|---|---|---|
| Standard | 700119432 | **$0.31** | $0.00 | −79.60 / +30.25 | 20 pts |
| Prime | 700152904 | **$0.12** | **$3.50** | −79.60 / +30.25 | 20 pts |
| **ECN** | 700152905 | **$0.12** | **$1.00** | −79.60 / +30.25 | 20 pts |

**Prime and ECN are the same account with two commission rates** — same `XAUUSD.p`, same spread,
same swap, same stops level — so the cheaper toll wins outright and there is no trade-off to weigh.
Replayed at those figures (`backtest/tools/cost_tiers.py`, 155,531 M15 bars, one real replay per
row): free 159 / +142.18R · Standard 156 / **+141.87R** · Prime 157 / **+150.23R** · **ECN 157 /
+151.39R**. ⚠ The Prime↔ECN gap is **1.16R**, far inside this strategy's sd of **15.06R** — the case
for ECN is *strictly cheaper at identical everything else*, not that number.

⚠ **Each raw-tier reading was PAIRED with a simultaneous Standard control** off the live MT5_FFT
terminal ($0.31–$0.32 through all three windows), because one terminal means three sequential
logins and gold's spread moves through a session — without the control, a tier gap and a moment gap
are the same measurement.

✅ **ECN's $0.12 is MEASURED in `backtest/fills.py` since 2026-08-14** (5 days, 3.03M ticks, all 23
traded hours) — see the box at the top of this section. **Prime's $0.12 in the table above is still
a five-minute reading and is NOT in `fills.py`**; model it with
`cost_tiers.py --spread puprime_prime=0.12`, which labels the row `stated`. Full detail:
`docs/BROKER_QUESTIONS.md`.

⚠ **Read the row above with that split in mind.** The Standard and ECN spreads are now measurements
and the Prime one is not, so the "Prime and ECN are the same account with two commission rates"
conclusion rests on a measured ECN beside an unmeasured Prime. It does not change the DECISION —
ECN is cheaper on commission at a spread that cannot be worse than equal — but it is not three
measurements, and it should not be quoted as if it were.

⚠ **Commission was settled by FILLING something**, since it is not a symbol property — 0.10-lot
round turns on each demo through `get_deal_breakdown()`. A first attempt at 0.01 lots read "$0.01
per side", which is MT5's smallest non-zero cent and matches every rate from $0.50 to $1.49 per lot:
**size a cost probe so the charge clears the rounding floor.**

**Everything below is the 2026-08-06 analysis on published figures. Its reasoning still holds and
its numbers are superseded.**

#### G5a (original) — WHICH PU PRIME ACCOUNT TYPE (measured 2026-08-06)

Aaron's question, ahead of funding a live account: PU Prime sell **Standard** (no commission, wide
spread), **Prime** and **ECN** (both raw-ish spread + a per-lot commission). Minimum deposits are
not a constraint — he can meet all three. His own framing was the right one and is why this needed
a replay rather than a fee table: *"I'm more concerned about filling at the right price. The spread
makes me not get into certain trades."*

🔴 **THE ANSWER IS A RAW TIER, AND THE FIRST INTUITION — INCLUDING THIS ASSISTANT'S — WAS BACKWARDS.**
The reasoning that fails is seductive: every entry here is a resting LIMIT, a limit fills at its own
price or not at all, so the spread is dodged and only the commission is unavoidable — therefore pay
spread, not commission. **The flaw is that dodging is not free.** A limit dodges the spread by NOT
FILLING, and a setup that never fills is the whole trade lost, not a few cents of it.

**MEASURED — one real replay per row, 155,531 M15 bars, 2020-01-01 → 2026-08-03, shipped defaults.**
Spread is modelled with `bid_ask_fills` (broker bars are the BID, so a long's entry limit and a
short's exits sit one spread further away), which is the ONLY cost model here that can move the
trade list. Swap is PU Prime's own measured rate on every row.

| tier | gold spread | comm/side/lot | trades | total R | setups never filled |
|---|---|---|---|---|---|
| free (no costs) | — | — | 159 | +142.18 | — |
| **Standard** | **$0.32** (MEASURED) | $0.00 | 156 | **+141.87** | **8** |
| **Prime** | ~$0.08 (published) | $3.50 | 158 | **+150.90** | 3 |
| **ECN** | ~$0.08 (published) | $1.00 | 158 | **+152.07** | 3 |
| ECN, if comm is really $3.50 | ~$0.08 | $3.50 | 158 | +150.90 | 3 |

**Standard costs ~10R over 6.5 years against either raw tier.** Which raw tier is close to
irrelevant — the entire $1.00-vs-$3.50 commission question is worth **1.2R**.

✅ **The two costs were isolated, and they differ by a factor of twenty.**

*Commission alone* (a flat toll, cannot move the trade list): $1.00/side = **0.48R**,
$3.50/side = **1.67R**, over the whole 6.5 years. This strategy takes ~2 trades a month, so a
per-lot toll barely registers. ⚠ Commission in R is **size-independent** (`reprice.py`'s own
reasoning), which is why R is the only honest unit here — the dollar figure is meaningless on a
compounding account.

*Spread alone* (moves the trade list), and this is the monotonic, mechanical relationship that
answers the question actually asked:

| spread | setups never filled | total R |
|---|---|---|
| $0.05 | 3 | +151.96 |
| $0.08 | 3 | +152.54 |
| $0.15 | 6 | +151.82 |
| $0.22 | 6 | +147.88 |
| **$0.32 (Standard, measured)** | **8** | +141.87 |
| $0.50 | 12 | +119.15 |

⚠ **Read the FILL COLUMN as the finding, not the R column.** It is monotonic across every value and
is a mechanical consequence of a resting limit meeting a wider quote. The R column is directionally
consistent but a 10R gap sits under this strategy's measured run-to-run spread of **sd 15.06R**
(`backtest/tools/jitter_audit.py`), so no single R figure here is significant on its own. **What
makes the conclusion safe is that it does not rest on one figure**: every raw-tier row beats every
Standard row, and it holds whether ECN's real gold spread is 5c or 15c and whether its commission is
$1.00 or $3.50.

⚠ **The drawdown column was DISCARDED and that is recorded rather than hidden.** Standard read
8.36R against ~5.7R for the raw tiers, which looks like a strong second argument — but it is **not
monotonic in spread** ($0.50 reads 6.77R), so it is one unlucky path rather than a systematic
effect. It is not part of the case.

⚠ **MEASURED vs PUBLISHED, and only one row is ours.** The $0.32 is a real measurement
(1,893,438 ticks, `broker_facts.py`); the demo is a Standard account and $0.32 agrees with their
published "3.0 pips" at the $0.10/pip gold convention, which is what pins the convention. **Every
Prime and ECN figure is off a marketing page, and the sources contradict each other** — their own
account-types page (read 2026-07-16) puts ECN at $1.00/side and Prime at $3.50/side; a third-party
breakdown reverses it and quotes ECN gold at 5-15 cents. The replay covers that whole range on
purpose, so the conflict changes nothing. **Do not promote any of it to a measurement.**

🔴 **A LATENT DEFECT THIS FOUND, AND IT IS THE SILENT KIND — now FIXED.** `backtest/fills.py::PROFILES`
gave **all four** PU Prime tiers `_SPREAD_XAUUSD_PUPRIME = 0.32` — a figure measured on the
STANDARD account, which is the one tier priced by a MARKED-UP spread. So selecting `puprime_ecn`
charged ECN's commission on top of Standard's spread: a combination no real account offers, which
overstates the raw tiers' cost and made Standard look better than it is. **Nothing errored.**

✅ **Fixed as a REFUSAL rather than a published number typed into code** — the `SENTINEL` pattern
`commission_per_side_per_lot` already uses. The three raw tiers carry `SPREAD_UNMEASURED`;
`AccountProfile.spread_or_refuse()` raises and names `broker_facts.py`, and `bid_ask_fills` on an
unmeasured tier is refused at CONSTRUCTION, because it decides which trades exist.

⚠ **The refusal is on the SPREAD, not on the tier.** A raw tier's commission and swap are known
and still chargeable — refusing to build the profile at all would make the honest half unusable.

✅ **DRIVEN against real replays rather than unit-tested alone**, all six cases: `puprime_ecn`
+spread and `puprime_cent` +spread+swap refuse at the first charge, `puprime_prime` +bid_ask_fills
refuses at construction, `puprime_ecn` +commission+swap still RUNS, and `puprime_standard` /
`vantage_demo` are untouched (3 trades each, identical to before).

⚠ **One test asserts the MESSAGE and that is the whole test.** The sentinel is `-1.0`, so the
pre-existing `spread <= 0` guard already raised — saying *"spread is 0 — the ask would equal the
bid"*, a confident FALSE DIAGNOSIS, since the spread is not zero but unknown. **A nearby guard
that happens to fire is not the same as the right guard firing.**

🔴 **THE SWAP ASSUMPTION WAS CHECKED THE SAME DAY AND IT IS WRONG — SWAP REFUSES TOO.** The first
pass left `_XAUUSD_SWAP` on every tier and NAMED the assumption (*swap is a fact about the SYMBOL,
so it is the same across a broker's tiers*) as a ⚠ caveat. ✅ **MEASURED with the new
`algos/tools/broker_facts.py --symbols`, one command against the live terminal:**

| on ONE account | swap long | swap short | spread | trade mode |
|---|---|---|---|---|
| `XAUUSD.s` | **−79.60** | **+30.25** | 0.320 (1,915,768 ticks) | FULL |
| `XAUUSD.crp` | **−9.35** | **+0.04** | 0.130 (708,565 ticks) | **DISABLED** |

They are the **same market** — median M15 close difference **$0.08** over 200 shared bars — quoted
twice, **8.5x apart on the long swap with the short CREDIT gone entirely.** This strategy trades
both sides and its whole swap arithmetic rests on that credit nearly cancelling the long charge, so
borrowing another product's swap is not a small approximation. The raw tiers now carry
`UNMEASURED_SWAP` and refuse.

⚠ **`XAUUSD.crp` is DISABLED, so it is EVIDENCE, not an opportunity** — the first reading of that
table was *"there is a far cheaper gold sitting on this account"*, which is why the tool now prints
`trade_mode` in the same row as the tempting numbers.

⚠ **The terminal cannot answer the ACCOUNT-TIER question in either direction.** The suffix scheme
across all 1,015 symbols is `.s` / `.24H` / `.crp` / no-suffix — **product lines, not tiers** — so
this account sees only its own products. **A second account is the only way to measure Prime or
ECN**, and question 3 in `docs/BROKER_QUESTIONS.md` is what turns the sentinel off.

**The standing lesson is about how an assumption survives.** This one was testable in one command
the whole time, and it lasted because no command existed. Writing it down as ⚠ NAMED rather than
measured felt like diligence and was still just a comment. **When you name an assumption, ask what
it would cost to test — here it was ten minutes and a read-only script.**

**Still open — see the broker questions in `docs/BROKER_QUESTIONS.md`.** The one number that would
change this answer is not in any table above: **swap costs 6.60R, larger than the entire gap between
account types.** If swap differs by tier, it outweighs everything here.

### G6 — The minimum-stop-distance guard is a live hazard and does not exist in Python — **CLOSED 2026-07-30**

This is the only item on this list that can lose real money quickly.

`exec_sl_level = "0.886"` places the stop just past the deep edge of the entry band. The entry is a
limit *inside* that band. When they land close together, stop distance collapses, and
`qty = risk / stop_distance` builds an enormous position. Measured at `0.786`: a $0.20 stop, a
39,033 oz position, ~180% of equity lost in one bar. At 0.886 it has never fired across 6.5 years,
but that is **evidence of absence, not a guarantee** (`mpc_sos_fade/CLAUDE.md` says so explicitly).

`mpc_strategy.pine` has the guard (`execMinStopMode` / `execMinStopVal`). **`config.py` has no
equivalent**, the export carries no column for it, and `compare_strategy.py` therefore reports GREEN
regardless. Run 7 already measured the fix: `pct 0.1` (stop must be ≥ 0.1% of price) blocks 6 of 188
trades, is +2.5R, and leaves four whole years byte-identical.

**Build it before live. Not optional.** Separately, MT5 rejects orders whose SL is inside
`SYMBOL_TRADE_STOPS_LEVEL`, so the bridge needs broker-side handling too — but a broker rejection is
a missing trade, whereas the strategy-side hazard is an oversized one.

### G7 — Telegram token revoked, and the old one was committed — **CLOSED 2026-07-30**

The token appeared in plaintext in **six** files: `algos/shared/notify.py`, the three notification
scripts, `algos/notifications/telegram_bot.py`, `command-center/backend/routers/bots.py` and
`command-center/backend/services/notify.py`. It is revoked, so this was the moment to move it out of
git for good rather than paste a new one into the same six places.

Done: `algos/shared/credentials.py` resolves env → git-ignored `algos/credentials.json`, with
`algos/credentials.template.json` in git carrying the shape and no values. Every VPS-side file now
calls the resolver; `routers/bots.py` lost its private copy of the token, chat id and urllib call and
delegates to `services/notify.py`, which reads the same file from the command-center side (a shared
FILE is the allowed seam between the two apps; a shared import is not). Missing credentials are a
no-op with one printed warning, never an exception — a notification channel must not be able to stop
a trading loop. The standing "keep the two token constants in sync" rule is gone: there is nothing
left to keep in sync.

Still to do: Aaron creates the new bot and group, then fills in `algos/credentials.json` on the Mac
and on the VPS.

**No trade-level notifications exist yet** — the current alerts are crash and daily-report alerts.
Entry/exit alerts are new code in the live runner (step 7).

### G8 — Nothing keeps the lab and the live bot apart — **MECHANISM BUILT 2026-07-30** (`algos/live/version.py` + the instance config); the lab-side Promote button is step 6

The VPS runs `git pull origin main`. Edit `config.py` locally to test a new idea, push, and the next
VPS pull + restart silently changes what is trading. There is also no record of which version any bot
is running. `lab.db` has content-addressed `strategy_versions` (per strategy source hash → monotonic
version), but that tracks lab deploys of `.cs`/`.mq5` files, not running processes.
`docs/LWG_Roadmap_And_Open_Questions.md` already specs a bot version ledger; it was never built.

### G9 — No trade log and no log backup

No live trade log exists (there are no live trades). `decision_log.py` is the right tool and is
unwired. Nothing backs up any VPS log anywhere — `algos/` logs live only on the VPS disk.

### G10 — No account-level risk allocator — **BACKTEST HALF BUILT 2026-08-09, LIVE HALF STILL OPEN**

`exec_risk_pct` is per-trade with nothing above it, and the account-level cap is a prerequisite for
running more than one bot live.

**Consequence for this plan is unchanged: start with ONE bot.** A+ alone needs no allocator.

**Split the gap in two, because only one half moved.**

✅ **The BACKTEST can now run a shared account.** `backtest/portfolio/run_stack` replays several
`strategies/python/` bots on ONE balance and ONE risk budget: every leg sizes off the shared balance,
every leg's P&L books onto it, an open trade reserves risk to its CURRENT stop, and an entry with no
room is shrunk to fit or refused. Every shrink and refusal lands in a contention log. Driven by
`backtest/tools/stack_run.py`. Both strategy constructors thread `account` / `leg` through to
`Execution`, where the seam had existed since 2026-07-17 with nothing able to pass it one.

✅ **MEASURED on the first real run — 155,807 M15 bars, A+ and B-LEG, $10,000, cap 10% of the live
balance: A+ 159 trades / +142.18R · B-LEG 99 / +17.87R · account $10,000 → $204,918,789**, with
every leg posting the SAME R shared as solo. That equality is the control, not the headline: R is
normalised to the trade's own risk, so with nothing refused the shared account changed the DOLLARS
and moved no decision — which is what makes any later difference attributable to the cap.

🔴 **AND NOTHING WAS EVER BLOCKED IN 6.5 YEARS.** Peak open risk touched **exactly 10.00%** with
**2 of 2 legs holding at once**, and the contention log is empty — because risk is measured to each
trade's CURRENT stop and A+ touches breakeven on 161 of 161 trades at a median of ONE BAR, so its
room is released before the other leg can ever be refused. **Read that as "the allocator would
rarely have had anything to arbitrate", never as "a cap is unnecessary"**: it is G14's shared
bars (27 when this was written, **45** at the 2026-09-01 re-run) arriving through the budget, and the window where two bots genuinely carry 2× risk is the bar
before the stop stages.

✅ **THE LIVE HALF IS BUILT TOO, LATER THE SAME DAY, AND IT COULD NOT REUSE THAT OBJECT.**
`PortfolioAccount` is an in-process Python object; live bots are separate OS processes. So the live
allocator reads **the BROKER**, which is the design rather than a compromise: every alternative —
a shared state file, a lock, a message bus — needs the bots to trust each other, and a bot that
crashed or was killed leaves a stale reservation, so the cap then bounds a fiction. The broker
knows what is actually open, **and it knows the STOP on every one of them**, because this suite
puts the stop at the broker by design (bridge → D4). Risk-to-the-current-stop is therefore READ,
not inferred — the same basis the backtest reserves on.

| piece | where |
|---|---|
| the arithmetic and the refusals, pure and offline | `algos/shared/account_risk.py` |
| the ONE unfiltered broker read | `mt5_ops.account_exposure()` |
| the check, at the single sizing seam | `bridge._account_cap_check`, called from `_plan` |
| the setting | `account_risk_cap_pct` on the instance config — `null` = uncapped |

🔴 **The unfiltered read is the whole foundation and it is a deliberate exception to a standing
rule.** Every other read in `mt5_ops.py` is MAGIC-filtered — right, and exactly what makes a bot
blind to the account it shares. `account_exposure()` reads everything on the symbol whoever placed
it. It never cancels, modifies or closes any of it: **the isolation rule is about WRITES**, and
nothing here writes.

⚠ **A position with NO stop REFUSES the order rather than scoring as zero risk.** Its risk is not
small, it is unbounded — a hand trade left running is exactly that — and the falsy value it arrives
as has the same shape as "no risk". Scoring it zero would let the one thing the cap exists to bound
sit invisibly underneath it.

⚠ **An unreadable account REFUSES.** A cap that opens itself when the terminal wobbles is a cap
that is absent exactly when the account is least healthy. "Cannot ask" is never "affordable".

🔴 **THE TWO SIDES RESOLVE A SHORTFALL DIFFERENTLY, AND IT IS NAMED RATHER THAN PAPERED OVER.** The
backtest SHRINKS the leg's size to the room; live REFUSES. Shrinking is coherent in the backtest
because the account hands the granted size back and the same process's emulator opens at it —
**nothing hands a size back across a process boundary**, so a shrunk live order would leave the
emulator holding one trade and the broker a smaller one, they would grade different R, and
`_agrees` would eventually halt the bot on a divergence the safety feature created. On the measured
history it changes nothing, because the cap never bound at all — but that is a fact about one
history. **Anything that tunes the cap has to be replayed under the REFUSE policy**, or the
backtest stops predicting the account.

⚠ **A cap BELOW a leg's own risk % does not arbitrate, it RE-SIZES** (in the backtest) or refuses
everything (live). At a 5% cap against two bots each risking 10%, all 258 backtest entries are
shrunk and none is blocked; R is unchanged and the closing balance falls $204.9M → $4.7M.

⚠ **This bot's OWN exposure is excluded from the total, and that is not a shortcut**: the strategy
has ONE position slot, so anything of ours already on the book is what this order REPLACES.
Counting it would make the bot refuse its own re-sizes near the cap, which reads exactly like a
broken strategy.

⚠ **`null` = UNCAPPED and the runner SAYS SO at every start** (a `risk_cap` health record and a
warning line). A cap that is set and a cap that is absent behave identically on an empty account,
so the only moment the difference is legible is before anything has happened — and *"I thought the
cap was on"* is precisely the belief that makes an uncapped second bot feel safe. Same call as
`deadman_url`. 🔴 **SUPERSEDED SAME DAY — the live bot is CAPPED AT 10% now** (Aaron's call, ahead of
bot #2). It read *"the live bot is unchanged: it has no cap configured, so nothing about it moves"*,
which was true for a few hours. ⚠ **10% equals A+'s own `exec_risk_pct`, so the two bots will not
share the budget — they take turns**: one full-size position or resting limit fills it and the other
is refused until the room returns. A cap that lets both hold at once has to be 20%. ⚠ **A RESTING
order counts here and does NOT in `backtest/portfolio/`, which reserves at the fill** — A+ enters on
a limit that can sit for hours, so **live contention will be more frequent than the shared-account
backtest predicts, and its empty contention log is not a forecast for this account.** ✅ The account
was probed read-only first (0 positions, 0 orders, 0 stopless), because one stopless hand trade
refuses every order and would read as a strategy that went quiet.

✅ **Magic numbers are now enforced UNIQUE per account** (`live_config._assert_magic_is_unique`).
Two bots sharing one would each read the OTHER's position as their own — cancel its orders, ratchet
its stop, book its fill — which is the doubled-book failure the duplicate-process guards exist to
prevent, arriving through configuration instead of through a second process. Per ACCOUNT, not
global: the terminal scopes orders by login.

✅ **THE FLEET HALT LANDED 2026-08-09** — `algos/shared/fleet_halt.py`, a flag file every bot re-reads
each poll, plus `algos/tools/fleet_halt.py` to pull and release it. It stops NEW ORDERS across every
bot on the box; it does not close a position, cancel a broker stop or kill a process. **Cannot-read
HALTS** (the opposite default from `stop.request`, because a false halt only costs a missed trade
while a false stop takes a healthy bot off the box), and it **LATCHES** — clearing the flag does not
resume trading, the bots have to be restarted. Full rules in `algos/CLAUDE.md`.

⚠ **STILL OPEN: nothing here has been exercised against a real second bot**, because there is no
second instance to exercise it with; the cap and the halt are unit-tested and mutation-checked, not
driven.

The overlap half of this gap is **CLOSED** — see G14. What stands between here and a second bot is
the live allocator above and the caveats on B-LEG in G15.

### G14 — The overlap audit — **RE-MEASURED 2026-09-01, and it still passes**

`backtest/tools/overlap_audit.py`, replayed over **157,004 M15 bars (2020-01-01 → 2026-08-23)**.
A+ reproduces **156 trades / +131.77R** and B-LEG **101 / +20.20R**, which is the cross-check that
the tool drives the two strategies correctly rather than a third thing.

🔴 **THE RE-RUN IS THE POINT, AND IT HAS NOW BEEN NEEDED TWICE FOR THE SAME REASON.** The first
audit ran 2026-08-04. On **2026-08-06** B-LEG was re-defaulted on three axes at once —
`bleg_max_days` 1.25 → 4.0, `exec_trail_pct` 1.0 → 0.05, `exec_time_stop_hrs` 36 → 8 — which **more
than doubled its trade count and tripled how long a frozen band stays alive**. It happened AGAIN on
**2026-08-26**, when the dead-market entry filter (`exec_min_atr_pct` = 0.08) landed on A+ and took
its shipped book from 245 trades to 240 — and the 2026-08-09 reading below then described neither
bot and stood unchallenged in three files for three weeks. **A cross-cutting measurement has to be
re-run by whoever MOVES the inputs, not by whoever wrote the conclusion.** ⚠ The second time, that
instruction was already written at the bottom of this very section and it still did not happen —
so treat it as a step in the change, not as a reminder.

**The legs still do not overlap, and on direction they now overlap not at all.** Both bots held a
position on **45 bars out of 157,004** — 0.5% of A+'s own hold time, 1.9% of B-LEG's. **ZERO of
those bars were same-side**; all 45 were opposite, i.e. partially hedged. Four A+ trades out of 156
(2.6%) shared a bar with a B-LEG trade, and **none of those four pairs was same-direction**.

**They barely fire on the same structure break either**, which was the specific worry: across 6.6
years **exactly ONE** A+ trade has a same-direction B-LEG entry within 16 bars (2023-07-27, one bar
apart; A+ −1.99R, B-LEG −1.00R). Monthly R correlation is **+0.072** across all 78 traded months
(both traded in 52). ⚠ **Read that as a FLOOR on how together they move rather than as a figure** —
a month only one bot traded contributes a zero for the other and pulls it toward 0.

⚠ **Both halves improved this time, and neither direction is a trend.** 2026-08-09 → 2026-09-01:
49 → 45 shared bars, 1 → 0 same-side. Before that the absolute count went UP 27 → 49 while same-side
went DOWN 18 → 1, from one change. **Do not read a bigger overlap number as a regression without
reading the direction split under it** — and do not read a smaller one as progress on its own.

⚠ **This does NOT clear the allocator (G10).** The peak was still 2 concurrent positions, and each
bot sizes off its OWN equity, so on those 45 bars one account would have carried 2 ×
`exec_risk_pct`. The audit says the allocator would rarely have had anything to arbitrate — not
that risk stacking is safe. The backtest allocator measured the same thing from the other side on
2026-08-09 and refused nothing.

⚠ **And it does NOT mean the two are independent.** Both read one structure stream on one
instrument, and being flat at different moments is not the same as losing for different reasons. A
near-zero monthly correlation is the better evidence, and it is still only 6.6 years of one symbol.

⚠ **Re-run it after any entry-logic change on either bot** — that is what the tool is for, and the
result above is a fact about today's config, not about the setups.

### G15 — B-LEG: the "no edge" verdict was OVERTURNED — re-measured 2026-08-09

**Raised 2026-08-04 as 50 trades / −0.94R and that number is DEAD.** At today's defaults, over the
same 155,531 bars and driven by two independent paths that agree to the cent (`overlap_audit.py` and
the shared-account stack's solo control): **99 trades, +17.87R**, free of cost layers.

What moved it was the 2026-08-06 tuning pass in `strategies/python/mpc_bleg/`, measured over 186,312
M15 bars with spread and swap charged, IS/OOS split declared before any row ran:

| axis | old | new | why |
|---|---|---|---|
| `bleg_max_days` | 1.25 | **4.0** | the old value was never tuned — it was the Pine `maxval = 3`, and the best region sits outside it. 1.25 → 59 trades, 4.0 → 112, 5.0 → 118, 7.0 → 121 and falling |
| `exec_trail_pct` | 1.0 | **0.05** | a UNIT bug, not tuning: the step is a % of PRICE and a B leg's whole 1R is 0.13–1.25% of price, so one inherited step was larger than the entire risk and the ratchet was **inert for this fork's whole life** |
| `exec_time_stop_hrs` | 36 | **8** | fires only at stage 0, so it cuts no winner; 4–12h is a drawdown plateau |

**Charged, the shipped config is 114 trades / +17.56R / PF 1.45 / maxDD −5.15R**, against the old
59 / −1.73R / PF 0.94 / maxDD −16.00R. The drawdown is the headline, not the total: B-LEG used to
carry nearly **double** A+'s peak-to-trough for none of the return, and now carries slightly less
(−5.15R against A+'s −5.62R).

✅ **THE ERROR BAR EXISTS NOW, AND THE EDGE CLEARS IT.** `jitter_audit.py` had never been run on this
bot; it was run 2026-08-09 over **186,128 M15 bars, ±$0.05 redrawn per bar, 12 seeds**. Baseline
114 trades / +23.28R free, and **every one of the 12 seeds finished positive — min +21.63R, max
+30.36R, mean +26.33R, sd 2.61R.** The baseline sits *below* the jittered median, so it is not an
optimistic seed. In proportion the noise matches A+ almost exactly (**11.2% of total here, 10.6%
there**), and the worst seed still clears zero by a wide margin. **The sign of this edge is not a
feed artefact.**

⚠ **B-LEG is structurally far less flip-prone than A+, and that is a difference in kind.** A+ snaps
its limit to a fib rung off a gap — discontinuous, which is why four cents moved its entry $10.08 in
the shadow diff. B-LEG rests at its frozen band's own 0.5 edge with all four fib-entry rules pinned
off, so its entry *moves* with the feed rather than *jumping*: **0.6 rung flips per run against A+'s
1.4**. The trade-list churn is the same though — ~5.8 lost and ~7.9 gained per run — so expect a
cousin of this backtest on another broker, never a twin.

⚠ **This is still not "B-LEG is ready", and the difference matters.** Two things are open.
(1) **It has been tuned exactly once and never re-validated since** — the pass declared its own IS/OOS
split, which is the right discipline, but one honest split is not out-of-sample evidence, and a jitter
audit is **not** an out-of-sample test. It answers "does this survive another broker's quotes", not
"does this generalise".
(2) **Not parity-re-validated at the new defaults** — `compare_bleg.py` configures Python from the
export's own `cfg_*` columns, so parity is structurally unaffected, but every export on disk decodes
the OLD values and proves nothing about these. Re-export before trusting it.

**Consequence: B-LEG is no longer the thing blocking bot #2.** What blocks it now is the live
allocator (G10), the fleet halt, and the multi-bot Bots page (G11).

### G16 — No external dead-man's switch — **CLOSED 2026-08-04**

Every alert this suite has ever sent originates ON the VPS: the bot's own Telegram messages,
`monitor.py`, the bot's own entry/exit pings. So the box has to be alive and networked to tell you
it is in trouble, and if it is neither you get **silence** — which is exactly what a healthy Sunday
produces. The 50-minute blind-bot incident (G12) was survivable only because the box was up.

`algos/notifications/deadman.py` + `SYS_DEADMAN` (every 5 minutes, SYSTEM). It checks each
registered bot's process, heartbeat freshness and `mt5_link`, and pings an **external** service only
when all three are good. That service alerts when the pings stop, so the alerting lives off the box
and survives it.

⚠ **The ping is CONDITIONAL on health, and that is the design rather than an implementation detail.**
An unconditional ping proves only that Task Scheduler is alive — a healthy system and a bot that died
an hour ago send the identical green tick. **This is G12's probe rule from the other side: never
trust a POSITIVE result a broken system can also produce.**

⚠ **Two signals, because otherwise a dead bot and a dead box are the same silence.** A plain ping
(missing ⇒ timeout alert, meaning *nothing on that box can talk to me* — the far end genuinely does
not know why, and inventing a reason would be a made-up diagnosis), and `<url>/fail` carrying the
reasons when the script runs and finds a fault, which alerts immediately and by name.

⚠ **It restarts nothing.** `SYS_MONITOR` owns recovery. Two independent things issuing starts for one
bot is exactly G13.

✅ **ARMED 2026-08-05 and PROVEN, not assumed.** `deadman_url` is set on the VPS (a healthchecks.io
check, period 5 min / grace 15, notifying by **email** — which is a different inbox from every other
alert in this suite, and worth knowing on the night it fires). Verified in four steps rather than one:
`--status` reads the URL back, a real healthy run reported `sent`, **a deliberate `/fail` ping was
sent and the alert arrived**, and a healthy ping cleared it. `SYS_DEADMAN` is Enabled, last result 0,
repeating every 5 minutes.

⚠ **Sending the test failure was the point.** Everything up to it proves the box can talk to the
service; only the fail ping proves the service talks to a human. An alarm nobody has heard ring is a
configuration, not an alarm — and this one's whole value is that it fires when no other part of the
system can tell you anything.

⚠ **Unset remains a supported, honest state** (`--status` reports it and the task exits 0), because a
task that fails every five minutes is one everyone learns to ignore. **A rotated or cleared URL puts
this gap back to closed-in-CODE and open-in-FACT** — do not read the task existing as the switch
existing.

⚠ **The URL is a SECRET.** Whoever holds it can send your pings for you and hold the alert green
forever, which is strictly worse than no switch, because you would believe in it.

### G17 — The shadow diff RAN, and it found a knife-edge in the entry model — 2026-08-04

Step 9.2, executed. `algos/tools/shadow_diff.py` joins the live bot's own `bar` ledger stream to
a lab replay of the same window **on bar TIMESTAMP** (never on index — the two count from
different places) and diffs them field by field. **148 live bars, 2026-07-31 → 2026-08-05.**

**The clock is right.** 148 of 148 live bars have a lab bar at the same timestamp; zero missing.
That is the check this step exists for, and it passes outright.

**The feeds differ by a systematic 4–5 cents.** Vantage (the lab) quotes gold consistently ABOVE
PU Prime (the live account) — `lab − live` is +$0.04 to +$0.05 on every one of the 148 bars, never
once the other way. That is a quote-level difference between two brokers, not drift, and it is
expected: every backtest in this repo was measured on Vantage and the bot trades PU Prime.

**Ten of the eleven compared decision fields are bar-for-bar identical.** Stages, arms, vetoes,
stops, TP ladder — no divergence anywhere.

🔴 **The eleventh is the finding.** `long_edge` differs on all 148 bars: on 123 of them by exactly
the feed offset (+$0.04, i.e. the same level priced off a 4-cent-higher feed), and on **25
consecutive bars — 2026-07-31 14:30 to 20:30, one leg — by $10.08.**

**The cause was isolated, not guessed: both prices are rungs on the SAME fib ladder.** At
2026-07-31 14:30 the lab's own ladder reads 0.618 = 4041.958 and 0.702 = 4031.841. The live bot
rested at **0.618**; the lab rested at **0.702**. Same leg, same anchors (ash 4116.39 / asl
3995.95), same stage on both sides — **the entry RULE picked a different rung.**

That is `exec_fib_nearest` (rule 3, ON by default since 2026-08-02), which rests on whichever of
the two bracketing levels is nearer the gap edge. **It is a discontinuous choice, and nothing had
measured how sharp the discontinuity is: four cents of feed difference moved the resting entry by
$10.12.**

⚠ **It is not just a different price, it is a different TRADE.** With the stop at 0.886 (4009.68),
entry 4041.96 is a $32.28 stop and entry 4031.84 is a $22.16 stop — **46% apart**. Same nominal 1R,
so the R-based backtest is unaffected, but the position SIZE, the fill probability and the distance
price must travel are all materially different. A backtest's fill rate is therefore **not
transferable across brokers at the margin**, and this is the mechanism.

✅ **Nothing was affected in this window.** No trade was taken, `l_stage` never exceeded 1 on either
side, and no stop was ever set — the edge was being computed but never rested. So this is a measured
sensitivity, not an incident.

✅ **THE FOLLOW-UP RAN 2026-08-05, AND THE RUNG FLIP IS THE SMALL HALF OF THE ANSWER.**
`backtest/tools/jitter_audit.py` replays the strategy with a per-bar ±$0.05 offset and counts what
changes. **MEASURED over 186,220 M15 bars (2018-09-13 → 2026-08-04), baseline 183 trades /
+134.75R, 12 seeds:**

| what changed | per run | share of the trade list |
|---|---|---|
| **rung flips** (this section's finding) | 1.4 | 0.8% |
| trades RETIMED (same setup, filled ≤16 bars away) | 4.3 | 2.4% |
| trades LOST outright | 10.7 | 5.8% |
| trades GAINED | 10.4 | — |

🔴 **The fill is the sensitivity, not the entry rule — an order of magnitude bigger.** Every entry
here is a resting limit at an exact price, so five cents decides whether price reaches it at all.
About **6% of the trade list changes** on a few cents of quote difference, and almost none of that
is the strategy deciding differently.

✅ **The edge survives comfortably: all 12 seeds finished POSITIVE**, +92.24R to +148.13R, mean
+131.74R, sd 15.06R. ✅ **And the baseline is not optimistic** — median jittered **+134.52R** against
a **+134.75R** baseline, i.e. the shipped figure sits mid-distribution rather than at the top of it.

**So the conclusion splits in two, and only the first half is supported: the STRATEGY transfers, the
TRADE LIST does not.** Expect the live trade list to be a cousin of the backtest's, not a twin, and
do not treat a divergence in which specific setups filled as evidence that something is wrong.

⚠ **When a flip does fire it is violent — median 31% change in the 1R stop distance, max 84.5%.**
The trade is sized to its stop, so the nominal R never moves; the POSITION SIZE and the fill
probability do. Read a flip as a size event, not a return event.

⚠ **The flip figure is a FLOOR.** A flip that also moves the entry BAR is counted as retimed or as
lost+gained, never as a flip.

⚠ **Retiming is why the number is 6% and not 9%.** The first pass scored a limit that filled one bar
later as one trade destroyed plus one invented, which overstates the churn — it is the same setup.
Pairs are matched one-to-one, nearest first; without that constraint one jittered trade would be
claimed as the twin of two baseline trades and both counts would collapse toward zero, reporting
perfect stability by double-counting.

⚠ **The diff compares only what the ledger records.** `l_sos_bar` / `s_sos_bar` / `l_arm_src` /
`s_arm_src` come off the SEQUENCE object, which a replay does not retain per bar; the tool names
them as uncompared rather than dropping them quietly. Read a green run as "every field that CAN be
compared matched", never as "everything matched".

⚠ **Running it found a defect one layer down** — the bar cache was recording the window it
REQUESTED rather than the data it RECEIVED, so the first run could only compare 66 of 148 bars.
Fixed in `backtest/data/source.py::_covered_end`; see `backtest/CLAUDE.md`.

### G11 — The Bots page is CORRECT for many bots and unreadable with them — **CLOSED 2026-08-04**

**All three bullets below are closed.** Configure is a bot SELECTOR (a left rail) plus a detail panel
for the one selected bot; a fleet-wide version strip sits above it; and Monitor's global Start / Stop
/ Restart have left the visual language of the per-row buttons.

**Monitor's half, and why it needed more than spacing.** The three fleet buttons and the ▷ ■ ↻ in
every table row were rendered as peers, and they are not the same kind of thing — one restarts a bot,
the other kills every python process on the VPS. The card is now danger-bordered, titled **Fleet
controls** with an `ALL N BOTS` chip, and **every button carries the count it will hit** (`Stop all 4`),
because a label that is a number cannot say one thing while the table says another. The row column
header became **This bot** — the one place a row's scope can be stated once. Each fleet dialog now
LISTS the bots by name with live accounts flagged (`AffectedBots`): the old copy described the
mechanism ("kills all python.exe processes") and never the subjects, so the single fact that catches a
misclick — *which accounts* — was the one thing not on screen.

🔴 **A real defect fell out of that pass: the fleet buttons were GATED on the filtered list.**
`anyRunning` and the empty check were computed over the demo/live-filtered bots, while
`POST /bots/{start,stop,restart}` fires SYS_STARTUP / kills python on the VPS and has never heard of
a filter. So the "Stop all bots first" guard on Start could be defeated by choosing a tab — with the
**live** filter on and no live bot running, `anyRunning` read false while the demo bots were up — and
"No bots in this filter" disabled controls that would have worked fine. Both now count over ALL bots,
and when the filter is hiding a bot the card says so in words: *the demo filter is hiding 1 bot; these
buttons still act on all 4.* ⚠ **The general shape is this repo's own: a control's GUARD must be
derived from the same set the control acts on.** A view filter that reaches the guard but not the
endpoint is two different populations wearing one number.

**What the Configure fix actually buys, and it is a property rather than a layout preference: only the
SELECTED bot's controls exist in the DOM.** Verified in a real browser against a mocked 4-bot fleet —
`getByRole('button', {name: /promote/i})` counts **1** with four bots registered, where the flat stack
would have rendered four. A Promote button for a bot you did not pick is not there to be hit, which is
something no amount of spacing, ordering or confirmation copy can buy. Beside it: selection lives in
`?bot=` so a refresh cannot silently move you to a different bot's promote button, the promote confirm
and the risk-change dialog both NAME the bot (with a selector above them, the bot is a choice made a
scroll ago and no longer on screen), and a `live` account is tinted amber in the rail and the header.

⚠ **The fleet strip and the per-bot card derive from ONE function** (`versionFlags`), and share one
TanStack cache entry per bot (`useBotVersions` reuses `useBotVersion`'s key). Two readings of "is this
deployment claim false" is two answers that can disagree, and a strip saying *all clean* over a card
warning *restart pending* would be worse than no strip. It costs no extra fetch — the flat stack was
already reading every bot's version to render every card.

⚠ **A version that could not be READ is counted as `unreadable`, never as clean.** Same rule as the
`No MT5 link` chip: *no data* and *cannot ask* must not be the same value.

⚠ **The detail header is deliberately NOT sticky and the RAIL is.** "Which bot am I editing" has to
survive scrolling past a 53-row parameter accordion, and the rail is the selector, so its highlighted
row cannot disagree with itself. A second sticky header was a second answer to one question — and it
landed straight in the 22px trap `command-center/frontend/CLAUDE.md` records (`<main>` is a padded
scroller, so `top-0` pins 22px LOW and the card headers below scroll up through the strip it leaves).
It was visible in a screenshot before it was reasoned about.

Original write-up follows.

Aaron's question, and the answer is yes on the part that matters: `ConfigureTab` maps over
`snapshot.bots` and renders a full section per bot — its own Deployed version card, its own promote
button, its own risk editor — and every endpoint is keyed by bot name, so promoting or restarting one
cannot reach another. Nothing here is single-bot by construction.

**What does not scale is the READING of it, and it gets worse exactly when it matters most.** Both
tabs are flat vertical stacks with no bot selector, no filter and no collapse:

- ✅ **Configure** is roughly a full screen per bot (risk editor + Account + Deployed version + a 47-row
  parameter accordion). Three bots is a scroll hunt; the promote button you want is somewhere in the
  middle of it, and the promote controls of the two bots you do NOT want to touch are identical and
  adjacent. That is a misclick surface, not just a layout complaint. — **FIXED: rail + detail panel.**
- ✅ **Monitor** already has a table, so it scales further, but the per-bot start/stop/restart buttons
  sit in rows that look alike, and the page-level Start / Stop / Restart act on ALL bots — a
  distinction that is easy to miss with one bot registered and expensive to miss with four.
  — **FIXED: a danger-bordered `Fleet controls` card, counts on every button, `This bot` on the row
  column, and the affected bots listed by name in the dialog.**
- ✅ **The version card is per bot with nothing comparing them.** The question that will actually be
  asked once there are several — *which bots are behind the repo, which have a restart pending* — has
  no single place that answers it, even though `GET /bots/{name}/version` already returns everything
  needed. — **FIXED: the fleet strip at the top of Configure.**

**Fix before the second bot goes live, not after.** Sketch: a bot selector (or per-bot collapse,
defaulting to collapsed past one) on Configure; a fleet-level version summary row; and the global
Start/Stop/Restart visually separated from the per-bot ones. None of it is hard — it is layout over
endpoints that already exist per bot — which is precisely why it should not be left until the day
there is a live position on the line. **All three landed 2026-08-04.**

⚠ **This pairs with G10 and neither is sufficient alone.** G10 stops two bots overdrawing one
account; G11 stops a human doing the same thing by clicking the wrong row. Both are prerequisites for
running more than one bot live.

### G12 — The terminal can restart underneath a running bot — **CLOSED 2026-08-04**

**MetaTrader updates itself, and it does not ask.** At 02:57:53 UTC `C:\MT5_FFT\terminal64.exe` was
rewritten and the replacement process started at 02:57:55. The bot (started 02:24) held an IPC handle
to the process that had just been replaced, so from the 02:30 bar onward it saw nothing at all —
50 minutes across an open session, in which it would have taken no entry and managed no exit.

**Nothing in the system reported it, and that is the part worth keeping.** Every failure on the MT5
path returns an ABSENCE rather than raising: `copy_rates_from_pos` → None → `get_candles` returns an
empty frame (documented as *"never None"*, which is right for its callers and fatal here) →
`new_bars` reads *no bar has closed* and `gap_bars` reads *no gap*. `account_info` → None → the
heartbeat wrote a null balance. The loop therefore kept stamping its heartbeat, so **SYS_MONITOR saw
a healthy bot**, `wmic` still listed the process, so **the Bots page said RUNNING**, and the log
carried not one warning. The single visible symptom anywhere was a **blank balance cell**, which is
what Aaron noticed.

**The fix, and why it is `account_info()` rather than a bar check.** The loop probes the link first,
every poll. A bar-based probe cannot work: an empty frame is what a QUIET MARKET produces too, so
such a check either cries wolf out of hours or — the way it actually shipped — treats a dead link as
a quiet market indefinitely. `account_info()` answers whenever the link is alive, at 3am on a Sunday
as readily as mid-session, so `None` means exactly one thing. A lost link is logged, alerted once
(not every 10s), and reconnected on a 30s floor; **recovery RE-WARMS**, because an outage is a hole
in the bar stream and that is the condition `gap_bars() > 4` already exists for. It deliberately does
not reason about an open position — if the broker holds one the rebuilt emulator does not know
about, `OrderBridge._agrees` halts on the next bar, which is correct and already built.

`bot_state.json` gains **`mt5_link`**, surfaced on the Bots page as a **No MT5 link** chip beside the
Running pill, because *a blank balance is not a diagnosis*. Both facts are true simultaneously and
they are different: the process is alive (so a restart is the fix and the watchdog was right not to
fire) and it is blind (so it is trading nothing). 12 tests in `algos/tests/test_mt5_link.py`.

⚠ **The general lesson, and it is not this repo's usual label-vs-code one.** Every layer here behaved
correctly and defensibly on its own — an empty DataFrame is a reasonable thing for a bar fetcher to
return, and a null balance is a reasonable thing to write when you have no balance. **The defect was
that "no data" and "cannot ask" were represented by the same value at every hop**, so the distinction
was destroyed at the bottom and could not be recovered anywhere above it. Before adding a probe
anywhere in this system, ask whether its negative result can be produced by a healthy system too — if
it can, it is not a probe.

✅ **CLOSED 2026-08-04 by `SYS_DEADMAN`** — see G16. This incident was the argument for it: every
alert in the suite originated ON the VPS, so a dead box or a dead network produced silence, and
silence is what a healthy Sunday produces too.

### G13 — Every recovery path could produce a duplicate — **CLOSED 2026-08-04**

**`SYS_STARTUP` was not idempotent, and every recovery path in this suite fires it.** The boot
task, the Bots page Start/Restart buttons, and the documented restart command all run
`startup_coordinator.py`, which launched each bot in `STARTUP_SEQUENCE` unconditionally and then
launched `start_telegram.py`, whose first act is to force-kill any running Telegram bot.

**Measured on the live box**, by firing the task to verify an unrelated fix: it left **two
`runner.py --bot mpc_sos_fade_demo` processes** four minutes apart, and killed and rebuilt the
Telegram bot. Nothing anywhere reported either.

⚠ **Two copies of one bot is the worst duplicate available here.** They share an account, a magic
number and a strategy, so they see the same setup on the same bar and each sizes a FULL position
off it — double the intended risk, from a state neither can see. The bridge filters
`get_open_positions()` by MAGIC, so each finds the other's position and reads it as its own; only
`adopt_broker_state`'s HALT-on-unknown-position makes this survivable rather than an immediate
double book. In dry run it cost nothing. Live, it is the single most expensive bug in this file.

**Fixed with three guards, because they cover different launch paths:** the coordinator skips a
bot already running on **both** of its paths — full startup, and `--bot` single-bot mode — and
`runner.already_running()` refuses to be a second copy at all, covering the watchdog and a
hand-typed command. All match on `--bot <key>` rather than the script name, since every live bot
is `runner.py`.

⚠ **The single-bot path was MISSED on the first pass of this fix, and it is the dangerous one** —
it is what the command center's per-bot Start button drives, and pressing Start on a bot that is
already running is a completely reasonable thing for a person to do. The runner's own guard would
have refused the second copy, but it would have said so in a boot log nobody opens, and
`set_started` would already have reset the uptime of the bot that was genuinely running. A test
now asserts that `main()` contains exactly two `bot_is_running` checks, so a third launch path
cannot be added without one.

⚠ **The two guards default in OPPOSITE directions when the process list cannot be read**, and that
asymmetry is deliberate: the coordinator assumes RUNNING and leaves the bot alone (a duplicate is
two positions), the runner assumes NOT RUNNING and starts (an unstartable bot is silence). Neither
default is "safe" in the abstract — each is safe against the failure that path actually causes.

✅ Verified by re-firing the task with both fixes live: one bot, one Telegram, no new processes.

⚠ **The general shape, and it is worth carrying into the multi-bot work (G10/G11): a start command
that is not idempotent is a duplicate generator.** Every automatic recovery mechanism here — the
boot task, the watchdog, the supervisor — works by re-issuing a start. If "start" is not safe to
call on something already running, then every one of those is a way to double the book.

---

## 4. Design decisions

Made here so the build does not re-litigate them.

### D1 — The bot runs on the Windows VPS

The MetaTrader5 Python package is Windows-only, and MT5 must be running for the API to attach. The
Mac runs the command center and drives the VPS over SSH, exactly as it does for the backtest agents.

### D2 — Which MT5 instance = a config field

`mt5_path` in the instance `config.json` binds the terminal, and `BotMT5.connect()` already refuses to
fall back to "any open terminal" when it is set — it also verifies the connected account number
matches and shuts down if not. This requirement is already satisfied by existing code; it just needs
Aaron's values.

```json
{
  "bot_key": "mpc_sos_fade_demo",
  "mt5_path": "C:\\MT5_PUPrime_Demo\\terminal64.exe",
  "symbol":   "XAUUSD.s",
  "timeframe": "M15",
  "magic": 770115,
  "broker_tz_offsets": "2,3"
}
```

`magic` is what separates this bot's orders from every other bot's in the same terminal. One magic per
bot, never reused.

### D3 — The strategy is authoritative; the bridge mirrors

See G2. The bridge never decides anything. It only makes MT5 match the strategy and reports reality
back. Any place where the bridge would need to make a trading judgement is a bug in the split.

### D4 — Always attach a hard stop at the broker

The stop goes on the MT5 position, not held in the bot's memory. If the bot crashes, the VPS reboots,
or the network drops, the position is still protected. The bot then *ratchets* that stop each bar
close via `move_sl`. This is a deliberate deviation from the emulator (which holds stops in memory)
and it is the safe direction.

### D5 — Version isolation: freeze the params, pin the code

Two different things need protecting and they need different mechanisms.

**Params** — the live bot reads every strategy parameter from its instance `config.json`, never from
`config.py` defaults. Changing a default in the lab therefore cannot reach the bot at all. Promoting a
new setting is an explicit write to that file.

**Code** — the instance config also pins `strategy_source_hash` (the same whole-package md5 the lab
scanner computes, `strategy_scanner._python_source_hash`) and the `commit` it was promoted from. At
startup the bot recomputes the hash of the strategy package on disk and **refuses to start on a
mismatch**, with a loud Telegram message. A code change that reaches the VPS through a routine
`git pull` cannot silently start trading; it stops the bot instead.

This gives Aaron the exact property he asked for: at any moment, the answer to "which version is
trading" is a hash plus a commit, recorded in the config, echoed in the startup log, reported in
`bot_state.json`, and shown on the Bots page.

**Rejected alternative:** pinning the VPS to a release tag instead of `main`. Stronger isolation, but
it freezes the *whole monorepo* — including the command-center agents and engines that the lab needs
current — so a routine agent fix would require a re-tag. The hash guard gets the same safety at the
level that matters.

### D6 — Log cadence: two streams, two cadences

| Stream | What | Where | Cadence |
|---|---|---|---|
| **Trade ledger** | One JSONL record per signal: confluences, every gate verdict, sizing, entry, exit, P&L, R | `instances/<bot>/decisions.jsonl` | Written live; **committed to git daily** — it is small, non-secret, and this is what makes "why did this trade not work" answerable from a clone with no VPS |
| **Raw runtime log** | stdout, MT5 return codes, reconnects, order retcodes | `instances/<bot>/<bot>.log` | Rotated daily on the VPS, 90-day retention, zipped; pulled to the Mac by the command center whenever it runs |

The trade ledger is the one that must never be lost, and it is the one small enough to commit. The
raw log is bulky and mostly matters within days of an incident.

### D7 — Telegram: two messages, nothing else

Per Aaron, 2026-07-30. No daily summaries, no cap/limit alerts for now.

```
🟢 ENTRY  MPC SOS Fade
XAUUSD.s  LONG  0.42 lots
Entry 3,318.40   Stop 3,301.15
2026-08-04 14:15 UTC
```

```
🔴 EXIT  MPC SOS Fade
XAUUSD.s  LONG  closed @ 3,377.90
P&L  +$1,842.60   (+3.41R)
Reason: trail stop
2026-08-05 09:45 UTC
```

Crash alerts from the existing `monitor.py` stay on — they are not trade notifications and losing
them would mean a dead bot goes unnoticed.

**Routing is per bot, decided 2026-07-30 on Aaron's question.** Everything else about a deployment
is already per instance — terminal, account, server, symbol, magic, strategy version — and the
notification destination is the same kind of fact, not a global one. Different bots trade different
pairs on different accounts, and a demo gold bot sharing a feed with a funded FX bot means the
message that matters is the one you scroll past. So `LiveConfig` carries two optional fields:

| Field | What it decides | Empty means |
|---|---|---|
| `telegram_chat_id` | WHERE this bot's messages go | the shared group in `credentials.json` |
| `telegram_token_key` | WHICH Telegram bot they come from | the shared bot |

`telegram_token_key` **names a key** in `algos/credentials.json` (`telegram_token_bleg`) rather than
carrying the token. An instance config is an ordinary JSON file on the VPS; the rule that no secret
goes in a config file does not get an exception for convenience. `credentials.get()` resolves any
key, so a second identity is one new entry in that file and no code change (env name is always
`LWG_<KEY IN CAPS>`).

A named token that is absent falls back to the default one and warns once, rather than going mute —
a wrong sender identity is recoverable, a silently missing trade alert is not. It will usually then
be rejected by Telegram, because **a bot can only post to a chat it has been added to**; that is the
failure surfacing loudly instead of a message quietly vanishing.

---

## 5. The build plan

Nine steps. Steps 1–3 can be done before Aaron provides any account details.

### Step 1 — Close the money hazard (G6) — **DONE 2026-07-30**

`exec_min_stop_mode` / `exec_min_stop_val` in `SosFadeConfig`, the floor applied at order placement
in `_place_entries`, block reason **code 7** so a refusal on price is countable, `cfg_min_stop` /
`cfg_min_stop_val` in a REGENERATED `mpc_strategy_export.pine` (its body is byte-identical to the
parent again — the export had drifted behind the min-stop input, which is why the parent could refuse
setups the Python took while the comparator reported green), the decode in `compare_strategy.py`
(absent column ⇒ `"Off"`, never the Python default), and both fields in the meta so the lab shows
them. Default `"Off"` ⇒ byte-identical to the previous build ⇒ no historical result moves. 11 new
tests; 111 green.

✅ **CLOSED 2026-08-05 — parity proven with the guard FIRING, and shipped as the DEFAULT at
`"% of price"` 0.08** (strategy `config.py`, both A+ Pine files, the lab meta, the instance template
and the live bot). ⚠ **It shipped at 0.10 for a few hours first and that was wrong: 0.10 costs 7
trades and 1.84R over 7.9 years, while 0.08 gains 2.00R.** The correction is written up under
*What the value costs* below; the short version is that **a green parity gate says the two
implementations agree about a setting and nothing about whether the setting is a good one.**
The value that shipped had passed the gate. `compare_strategy.py` is **exit 0 at
warmups 100 / 500 / 1000 / 2000** on a 21,899-bar `VANTAGE_XAUUSD, 15m` export taken with the guard
enabled at `"% of price"` 0.30, and **block code 7 ("Stop too tight") fires 213 times in it** — 49
long, 164 short.

🔴 **It took TWO exports, and the first one is the lesson.** The 2026-08-05 morning export
(21,897 bars) was also green at three warmups, and proved nothing about the guard. Its own config
columns read `cfg_min_stop = 2`, and **mode 2 is `"Fixed $"`, not `"% of price"`** (`_MIN_STOP =
{0: "Off", 1: "% of price", 2: "Fixed $", 3: "x ATR(14)"}`) — a **10-cent** floor on a $4,000
instrument. **Code 7 appeared zero times in 21,897 bars**, and the tightest stop on any filled entry
was **$6.76**, 67× the floor in force. The gate was green on a branch neither side ever entered.

**The standing lesson, and it is aimed at this repo's own gates rather than at any bug: a green
parity run says the two implementations AGREE, never that either is RIGHT — and it cannot say even
that about a branch neither one entered. Before trusting a gate on a feature, check the feature was
EXERCISED.** The check is cheap and mechanical: this one is a block-code histogram over the export.

**WHAT THE VALUE COSTS — MEASURED 2026-08-05, and it moved the shipped number.** 23 configs over
186,220 M15 bars (2018-09-13 → 2026-08-04), **one real replay each**:

| mode | value | trades | total R | vs Off |
|---|---|---|---|---|
| Off | — | 183 | +134.75 | — |
| % of price | 0.05 | 183 | +134.75 | +0.00 |
| **% of price** | **0.08** | **181** | **+136.75** | **+2.00** ← shipped |
| % of price | 0.10 | 176 | +132.92 | −1.84 |
| % of price | 0.15 | 165 | +109.47 | −25.28 |
| % of price | 0.30 | 130 | +87.10 | −47.65 |
| Fixed $ | 1.25 | 180 | +137.75 | +3.00 |
| Fixed $ | 5 | 139 | +109.41 | −25.34 |
| x ATR(14) | 0.30 / 0.35 | 183 | +134.75 | +0.00 |
| x ATR(14) | 0.50 | 180 | +130.03 | −4.72 |

⚠ **Every row is a REPLAY, and the cheap alternative gets the SIGN wrong.** One position slot means
a refused setup frees the slot and the trade list reshuffles downstream, so deleting the refused
rows from a finished trade list scores 0.10 at **+1.84R** where the replay gives **−1.84R**.
⚠ **A small floor GAINS R mechanically: the three tightest stops in 7.9 years — $1.03, $1.06,
$1.18 — were all full −1.00R losers.** `Fixed $` 1.25 refuses exactly those three for exactly
+3.00R. Median stop distance is **$8.88**, so they are genuine outliers, not a cluster.
⚠ **Do NOT read +2R as an edge.** `backtest/tools/jitter_audit.py` measured this strategy's
run-to-run spread at **sd 15.06R**, so 0.05 through 0.08 are statistically indistinguishable.
**0.08 is the HIGHEST value that does not start costing — the most protection for nothing.** A
safety choice, which is the standing this guard has had since Run 7.
⚠ 🔴 **`x ATR(14)` was measured and REJECTED, against intuition.** It is the only mode that adapts
to volatility and it was cheapest on R — and at 0.35 and 0.40 **it never refuses the $1.03 stop**,
because that bar was quiet so $1.03 was not tight *relative to ATR*. **The hazard is
`qty = risk / stop_distance`: pure price units, volatility nowhere in it.** ATR blocks a different
set of trades from the one at risk — cheapness, not safety.
⚠ **Parity was proven at 0.30 and the live config ships 0.08.** Same code path, same floor formula
(`px * val / 100`), same refusal and the same block code — only the constant differs. State it that
way rather than claiming 0.08 was itself diffed.
⚠ **This CHANGES which trades the bot takes** versus every result measured at `"Off"`, and the A+
baseline moves with it: **183 trades / +134.75R → 181 / +136.75R**. `exec_min_stop_mode` defaulted
`"Off"` precisely so no historical result moved; that protection is now spent, deliberately. **Pin
the mode explicitly when reproducing an older run.**
⚠ **It does not replace the two independent backstops** and must not be read as doing so: the
broker's own 20-point `SYMBOL_TRADE_STOPS_LEVEL` rejects a degenerate stop at the terminal, and
`place_pending_limit` refuses one before it is sent. This guard is the one acting on OUR side of the
wire — which is where `qty = risk / stop_distance` is computed, and therefore the only one that can
stop the position being SIZED off a collapsed stop in the first place.

**WHAT IT COSTS — MEASURED 2026-08-05, and the answer is NOTHING.** Aaron's question, and the right
one to ask of any filter switched on live. Two replays of `mpc_sos_fade` over the SAME 70,867 M15
bars (2023-08-04 → 2026-08-04), identical but for the guard:

| | trades | total R |
|---|---|---|
| `exec_min_stop_mode = "Off"` | 73 | +68.76R |
| `"% of price"` 0.10 | 73 | +68.76R |

**Zero trades refused, zero gained, the trade lists identical.** Over three years no setup produced
a stop tighter than 0.10% of price (~$4 on gold at $4,000), so the floor never engaged once.

⚠ **Read this as "it did not fire in three years", NOT as "it cannot fire".** It is the same shape
as the note above about `exec_sl_level = "0.886"` never detonating across 6.5 years — **evidence of
absence, not a guarantee** — and the guard exists precisely for the tail it has not yet seen: the
0.786 measurement was a $0.20 stop, a 39,033 oz position and ~180% of equity gone in one bar. **A
filter that costs 0.00R and insures against that is free insurance**, which is the only reason it is
defensible to have switched it on without a prior measurement.
⚠ **Three years, 73 trades — not the full 7.9-year window.** Chosen deliberately after a full-history
attempt was abandoned; a longer window would raise the chance of catching a rare tight stop and can
only make the cost side worse than 0.00R by a small amount. Re-run it over full history if the number
ever needs to be quoted as a bound rather than as a sanity check.
⚠ **The tooling lesson is worth more than the number.** The first two attempts at this measurement
burned ~2h of CPU and produced nothing, because the scratch script walked up from `__file__` looking
for the repo and lived OUTSIDE it — `Path("/").parent` is `/`, so it spun at the filesystem root
before printing anything. Rising CPU was read as progress. **A process consuming CPU is evidence it
is running, never evidence it is working**, and the cheap way to tell them apart is output the
process emits on its own — which a `| tail` in front of it will hide completely.

### Step 2 — Secrets out of git (G7) — **DONE 2026-07-30**

`algos/shared/credentials.py` (env → git-ignored `algos/credentials.json`) +
`algos/credentials.template.json` in git. All six hardcoded copies removed;
`algos/shared/notify.py` is the VPS sender, `command-center/backend/services/notify.py` the Mac one
(reading the same file, not importing the other app), and `routers/bots.py` delegates instead of
carrying its own token and urllib call. `command-center/CLAUDE.md`'s "keep the two token constants
in sync" rule is retired — neither file holds a value.

**Outstanding:** Aaron creates the new BotFather bot + group and fills in `algos/credentials.json`
on both machines.

### Step 3 — Pending-limit orders in `mt5_ops.py` (G3, G4) — **DONE 2026-07-30**

`place_pending_limit` / `modify_pending` / `cancel_pending` / `cancel_all_pending` /
`get_pending_orders` / `get_open_positions` / `min_stop_distance` / `normalize_volume`. Orders and
positions are filtered by MAGIC, so one terminal can host several bots and a human without any of
them touching each other's orders.

Three refusals are explicit rather than left to MT5's retcodes: a limit on the wrong side of the
market, a price or stop inside `SYMBOL_TRADE_STOPS_LEVEL` (the floor applies twice —
market-to-limit AND limit-to-stop), and a size that rounds below `volume_min` (**refused, never
rounded up** — the minimum would be a bigger bet than the one that was risk-checked).

`get_candles` now converts broker-server time to true UTC through `broker_clock`. **This was a live
bug, not a precaution**: the old `pd.to_datetime(..., utc=True)` labelled broker-local seconds as
UTC, putting every bar 2-3 hours out with a perfectly valid-looking timestamp, and the engines it
would have broken — sessions, liquidity, VWAP — are exactly the ones A+ trades off.

16 offline tests against a faked terminal (`algos/tests/test_mt5_ops_pending.py`), including the
DST switch in both directions.

### Step 4 — The live runner (G1, G2) — **DONE 2026-07-30**

```
algos/live/
├── runner.py           the loop: connect → verify the pin → warm → poll → step → reconcile
├── bridge.py           strategy intent ⇄ MT5 orders (the mirror; G2)
├── feed.py             MT5 rates → canonical UTC frame, CLOSED bars only, gap detection
├── ledger.py           the append-only JSONL trade + decision log
├── live_config.py      one bot's instance configuration
├── version.py          the content pin (D5)
└── instance.template.json
```

Named `live_config.py`, not `config.py`: these modules are imported by bare name (the runner is a
script), and a `config` here shadows the backend's and the strategies' — which it did, once.

Behaviours worth knowing before reading the code:

- **`--dry-run` is the default; `--live` must be typed.** Arming a bot that sends real orders is
  not reachable by forgetting a flag.
- **A position the emulator opened during WARMUP is never placed live.** Its entry is in the past at
  a price that is gone, so the bridge sits in `WARMING` until the emulator flattens. Every live
  trade is one whose entry decision was made on a live bar.
- **A size change is CANCEL + RE-PLACE.** MT5's MODIFY accepts a volume and ignores it, and this
  strategy re-sizes every bar off live equity.
- **A real emulator-vs-broker disagreement HALTS the bot** — not "log and continue", not "adopt the
  broker's view". Positions keep their broker-side stop (D4), Telegram fires, a human decides.
- **An unknown position at startup halts too.** Silently adopting one is how a restart doubles a
  book: the strategy would size a fresh entry with no idea it is already exposed.
- **A gap in the bar stream re-warms rather than resumes.** The engines are state machines; a hole
  is a different market history, not a recoverable lag.
- **`assert_supported` refuses to start** on non-zero TP rungs, `exec_secondary`, or
  `fill_model="tick"` — configurations the bridge would silently mis-execute.

51 offline tests (`algos/tests/`), including one that hashes the strategy package with BOTH
`algos/live/version.py` and the lab's scanner and requires the same answer — the pin is worthless if
the two disagree.

**Not built yet:** the daily log-backup job (step 8) and the Bots-page registry (step 5).

### Step 5 — Register the bot in the command center (2.5)

Fill in the six registry dicts in `routers/bots.py` and point `_BOT_INSTANCE_MAP` at the new instance
config. Add a `BOT_MPC_SOS_FADE` scheduler XML modelled on the retired ones. Verify per-bot
start/stop/restart end to end.

This is where Aaron's "wake up and say start or stop" requirement is actually delivered, and it is a
few hours of work because the hard part was built a year ago.

### Step 6 — Version pinning + promote-to-live (G8, D5)

- Extend the instance config with `strategy_source_hash`, `strategy_version`, `commit`,
  `promoted_at`.
- Startup guard in `runner.py` that refuses on hash mismatch.
- New `bot_deployments` table in `lab.db`: `(bot_key, strategy_id, version, commit, promoted_at)` —
  the roadmap already anticipated exactly this shape ("deploy version N to target X records
  `(strategy_id, target, version)` in its own table without touching the registry").
- A **Promote to live** action on the Strategies page: takes the current param set + source hash,
  writes the instance config, commits, pushes, VPS pull, restart that one bot.
- `bot_state.json` reports the running version; the Bots page shows `v7 (a439f5e) · running 6h`, and
  flags `latest v8 — promote to apply` when the lab has moved on.

### Step 7 — Trade log + Telegram (G9, D6, D7)

`ledger.py` writes one `TradeDecision` record per signal — including the setups that were **blocked**
and **missed**, which `execution.blocks` / `execution.misses` already produce with full reasons. Entry
and exit fire the two Telegram messages. Daily git commit of the ledger via a small scheduled task
(commit + push only when the file changed; never commit the raw log or anything under
`credentials.json`).

### Step 8 — Log backup (G9, D6)

`SYS_LOGBACKUP` scheduled task on the VPS: rotate + zip yesterday's runtime logs, prune past 90 days,
commit the trade ledger. Command-center side: a small pull that copies the zipped archive into a
git-ignored local folder whenever the app starts. Both idempotent.

### Step 9 — Go live, carefully

1. **Dry run, one week minimum.** Bot runs, logs every decision, sends nothing to the broker.
2. **Shadow diff.** ✅ **RUN 2026-08-04 — `algos/tools/shadow_diff.py`, and it did its job** (G17).
   148 live bars: clock perfect (148/148 timestamps align), 10 of 11 decision fields bar-for-bar
   identical, and the eleventh exposed a knife-edge in rule 3 that nothing had measured — 4 cents of
   broker quote difference moved a resting entry by $10.12 by flipping which fib rung it chose.
   Re-run it after any live session, and after any entry-logic change.
3. **Feed parity.** `compare_feeds.py` against the live terminal — clock offset must read a flat 0h.
4. **Arm at reduced risk.** Not `exec_risk_pct = 10`. See the open question below.
   ⚠ **Superseded 2026-08-05: armed at 10%, Aaron's explicit call, on a DEMO account.** Recorded in
   the open-questions table below with the −54.9% drawdown it measured.
5. **One bot only.** B-LEG waits for the allocator and the overlap audit (G10).

🟢 **ARMED 2026-08-05 — `--live` is in `startup_coordinator.py`'s `STARTUP_SEQUENCE` argv.**

**Step 1 was completed and then deliberately cut short, and the reason matters more than the
timing.** The bot ran three days in dry run — **274 bars across 2026-07-31, 08-04 and 08-05** — and
in that entire record `long_armed` and `short_armed` are false on **every single bar**, the stage
never rose above **1**, no stop or target was ever set, and **not one order was suppressed**. The
dry run blocked nothing because nothing arrived. That is not a fault: A+ takes **~161 trades over
6.5 years**, about **two a month**, so three empty days is the expected result and a fourth week
would most likely have been the same. **A waiting period only buys confidence if the thing being
waited for can happen in it.**

⚠ **The flag belongs in `STARTUP_SEQUENCE`, and only there, because that tuple is the single source
for all three start paths** — `SYS_STARTUP` at boot, the `SYS_MONITOR` watchdog restarting a dead
bot, and the command center's Start/Restart buttons (which use the coordinator's `--bot` single
mode). Arming one caller instead would mean **a watchdog restart silently returning a live bot to
dry run**: the ledger would keep filling, the Bots page would keep saying RUNNING, and nothing would
report that orders had stopped. That is the "two paths, one drifts" defect this repo keeps meeting,
in the one place where the quiet direction is the dangerous one.

⚠ **Consequence: live is now this bot's DEFAULT on this box.** Every automatic recovery brings it
back armed. **Disarming means deleting the flag and restarting — not stopping the process,** which
the watchdog will simply undo within ~60s.

⚠ **What is still true and unproven:** the strategy's parity with Pine is green, but the
**minimum-stop guard has never fired in any validated export** (see Step 1), and the guard is what
stands between a collapsed stop distance and a position sized off it. The broker's own
`SYMBOL_TRADE_STOPS_LEVEL` (20 points) is an independent backstop and is enforced by the terminal,
not by us — which is the only reason arming ahead of that export is defensible, and it is defensible
**because the account is a demo**.

---

## 5b. First VPS startup — 2026-07-31

The first bot is configured and deployed: `mpc_sos_fade_demo`, on the **MT5_FFT** terminal
(`C:\MT5_FFT\terminal64.exe`), PU Prime demo **700107749** / `PUPrime-Demo` / **XAUUSD.s**.

> ⚠ **SUPERSEDED 2026-08-12 — this section describes the STANDARD demo, which this bot has left.**
> It now trades **700152905** / `PUPrime-Demo` / **`XAUUSD.p`** (ECN); see G5a above. The section is
> kept because everything it says about *how the facts were probed* still stands and is the method
> to repeat, but do not read any account number or measurement below as current. The symbol spec
> re-read on `XAUUSD.p` is identical (2 digits, 0.01 point, 100 oz, $1.00 tick value, 20-point stops
> level); the **filling mode** has NOT been re-read there and is the one that bites — a wrong one is
> retcode 10030 and the order simply does not go on.
Instance config at `algos/markets/fx/instances/mpc_sos_fade_demo/config.json`; the MT5 password
lives in the VPS-only `algos/credentials.json`, which git cannot see.

**Every broker fact in that config was probed off the running terminal, not typed.** Contract 100 oz,
tick value $1.00, volume 0.01–100.00 step 0.01, spread 33 points, trade mode FULL, balance $2,000,
leverage 500, hedging. Two that would have bitten silently:

- **`SYMBOL_TRADE_STOPS_LEVEL` = 20 points ($0.20).** The broker refuses a stop closer than that to
  the entry — the same hazard the minimum-stop guard exists for, enforced independently.
- **The symbol supports IOC but NOT FOK.** Market orders send IOC and pendings send RETURN, so we
  are fine; an FOK would have been rejected order by order with nothing obviously wrong.

The clock read **+3.00h vs UTC**, confirming the DST half of `"2,3"`. The winter half is still
inferred — re-measure after the November changeover.

**A full dry-run startup was executed on the VPS** — verify pin → connect → build strategy → feed →
bridge → adopt broker state → warm 5,000 bars (2026-05-15 → 2026-07-31 01:15 UTC, 4.1s) → go live.
It ended in `WARMING`, correctly: warmup finished with the emulator holding a position whose entry
is in the past, so the bridge places nothing until it closes (D3). The ledger recorded both events.

**That run found three bugs a fully green offline suite had not, and each would have stopped the
bot dead.** They are worth remembering as a class, not as three incidents:

| # | Bug | Why the suite missed it |
|---|---|---|
| 1 | The **version pin could never match**. The hash was over raw bytes and the VPS has `core.autocrlf = true`, so git rewrote every newline on checkout and one commit hashed two ways | Every test ran on the Mac, where both sides already see LF. Fixed in `live/version.py` **and** the lab scanner — they must stay in step |
| 2 | **`LiveRunner` could not be constructed** — `_make_logger` imported `bot_utils` from a dir that was never on its path | Every test covered a PIECE; nothing built the object that wires them together |
| 3 | **The log silently dropped lines** — a cp1252 console cannot encode the arrows and em-dashes, and `logging` discards the record rather than raising | Nothing asserted on log CONTENT, and macOS consoles are UTF-8 |

Bug 1 is the one to keep in mind: a pin that always fires is a pin that gets switched off, which
leaves nothing at all guarding what trades. **Standing rule from this: run it on the VPS before
believing it works.** Offline green means the logic is right, not that the bot starts.

---

## 6. Open items needing Aaron

| # | Item | Why it blocks |
|---|---|---|
| 1 | ~~**Which MT5 instance**~~ — **ANSWERED 2026-07-31**: MT5_FFT, 700107749, PUPrime-Demo, XAUUSD.s. Configured, deployed, startup proven (§5b) | — |
| 2 | **New Telegram bot token + group chat id** | Step 2. One pair is enough to start — routing is per bot (D7), so a second bot can later get its own group, or its own Telegram identity, by adding a key to `credentials.json` and naming it in that bot's instance config. No code change, and nothing to decide now |
| 3 | ~~**Live `exec_risk_pct`**~~ — **ANSWERED 2026-08-05: 10%, Aaron's explicit call.** No config change was needed; the live instance already carries `exec_risk_pct = 10.0`, so this is the decision being RECORDED rather than applied. ⚠ **It is a deliberate acceptance, not an unexamined default** — 10% measured **−54.9% max drawdown** over 6.5 years, and Run 12 established that the drawdown is a losing STREAK at that risk rather than give-back, so risk % is the only lever that moves it. Nothing further is owed here; re-open it only if the account purpose changes from demo | — |
| 4 | **A+ only, or A+ and B-LEG?** | **RE-OPENED 2026-08-09 — the 2026-08-04 "A+ only" answer rested on a number that is now dead.** The overlap audit re-ran again on 2026-09-01 and B-LEG passes it more cleanly still — **0 same-side bars in 6.6 years**, one same-break cluster (G14). And B-LEG at today's defaults is **99 trades / +17.87R** over the same bars, not the 50 / −0.94R that produced the original refusal (G15). It is a candidate again. Before it deploys: a **jitter audit** so its total has an error bar, a **re-export + `compare_bleg.py`** at the new defaults, the allocator (G10), the fleet halt and the multi-bot Bots page (G11) |

---

## 7. Standing reminders this plan touches

- ~~**The overlap audit**~~ — **RE-RUN 2026-09-01 and it still passes** (G14). 45 shared bars in
  157,004, **none of them same-side**; one same-direction entry cluster in 6.6 years.
  `backtest/tools/overlap_audit.py` is the tool; re-run it after any entry-logic change on either
  bot, because the result is a fact about today's config. ⚠ It has gone stale TWICE by not being
  re-run at the moment the inputs moved — do it in the same change, not afterwards.
- **Risk is budgeted per account and never layered** (`CLAUDE.md`). `exec_risk_pct` today is per-trade
  with nothing above it. The allocator is a prerequisite for bot #2, not a nice-to-have.
- **The Bots page needs a multi-bot shape before bot #2** (G11, raised 2026-08-04). It is already
  correct for many bots — per-bot cards, per-bot endpoints — but both tabs are flat stacks with no
  selector, so the promote and stop controls of bots you do not want to touch sit adjacent to the one
  you do. Layout work over endpoints that already exist; do it before there is a live position behind
  the wrong row, not after.
- **Never commit** `credentials.json`, `users.json`, `.env`, or tokens. Step 2 exists to make the repo
  actually obey this.
- **Never hardcode a broker fact** — history depth, symbol suffix, clock offset. Measure it, or refuse
  to run and ask. The live pipeline adds a new one to the list: the broker's minimum stop distance
  (`SYMBOL_TRADE_STOPS_LEVEL`), which must be read off the terminal, never typed.

---

### G18 — The live runner drives ONE timeframe, so no re-entry can ever run live — **STAGE 1 DONE 2026-09-01, stages 2-4 OPEN**

**The gap in one line:** every re-entry this repo has is priced and filled on a FASTER clock than
the 15-minute one the strategy arms on, and `algos/live/runner.py::_loop` polls exactly one
timeframe. So the live bot cannot take a re-entry, and `algos/live/bridge.py::assert_supported`
refuses to start rather than trade a configuration it would silently mis-execute.

🔴 **PROVEN THE EXPENSIVE WAY ON 2026-08-28.** The re-entry was switched on for
`mpc_sos_fade_demo` and the bot **would not start** — down until the setting was reverted:

> `bridge.UnsupportedStrategyConfig: exec_secondary needs a 1-minute bar stream alongside the 15m
> one (run_dual). The live runner drives a single timeframe. Turn it off, or build the dual feed.`

⚠ **Nothing before the restart catches it, and that is the trap this gap must close.** The config
CONSTRUCTS, and `promote.py` printed *"verified: the snapshot imports and builds with the promoted
parameters"* — because importing and building is not running. The refusal lives in the runner, so
the first thing that exercises it is the restart, by which point the bot is down.
**A promote's "verified" line means IMPORTS AND BUILDS, never RUNS. Read it that way.**

⚠ **The same single-feed limitation is why `compare_strategy.py` can never gate a re-entry**
(measured, not argued: the harness exercised **0** re-entries on a 21,357-bar export) **and why
`mpc_bleg` and `mpc_bos` both pin the setting off.** Three places had already recorded this shape.
Nobody had asked the live runner, which is the fourth.

**What it costs today:** the reclaim re-entry is measured at **+32.50R over 44 trades**
(2020-01-01 → 2026-08-23, `run_dual`, primaries unchanged at 156, so it adds rather than
displaces). All of it is unreachable live.

#### Why it is tractable — the fact that makes this a feed problem, not an allocator problem

**A reclaim only arms after the primary on that leg has CLOSED** (`exec_rec_require` =
*Stopped only*), and primary and secondary share ONE position slot. **So the two are never in the
market together, and the bridge's one-position model still holds.** What changes is where an entry
order's price and stop come from, and how often the resting order is re-decided — not how many
positions exist. That is why this is nothing like G10 (the account-level allocator), and must not
be bundled with it.

#### The plan — four stages, each shippable and provable on its own

**Stage 1 — a second feed into the runner, placing NO orders.**
Add a second `BarFeed` on `exec_sec_fill_tf_min` (5 minutes by default, and the caller's choice —
`run_dual`'s second frame is deliberately not a minute). Merge the two on one clock exactly as
`MpcSosFadeStrategy.run_dual` does: bars are timestamped at OPEN, so a faster bar reads the 15m
context of the bar that has already CLOSED at its open time. Step the secondary path and **LOG
what it would have done. Place nothing.**
🔴 **THIS PARAGRAPH IS WRONG ABOUT WHERE THAT PROOF RUNS AND IS CORRECTED BELOW — read the
correction before acting on it.** There is no "run it beside the live bot and watch" step; the
proof is offline and has to be.
✅ **Proof, and it is the whole point of doing this stage alone:** replay one window through
`run_dual` and through the live merge and require **identical secondary decisions, bar for bar**.
The merge ORDER is the part that is easy to get wrong and impossible to see later.
⚠ The bar-hole recovery in `_loop` (a raised bar advances the bookmark) has to cover BOTH feeds, or
the faster stream desyncs silently — the same defect that cost a re-warm rewrite on 2026-08-05.

#### ✅ STAGE 1 LANDED 2026-09-01 — and what it cost to get the merge right

**What shipped.** `LiveRunner` opens a second `BarFeed` on `exec_sec_fill_tf_min`, warms it, and
steps the re-entry through the SAME object the lab drives — `strategies/python/mpc_sos_fade/
dual_clock.DualClock`, which `run_dual` was refactored onto in the same change. **The bridge
still places nothing**: a would-be fill is written to the decision ledger as
`secondary_shadow_fill` and logged, and `assert_supported` still refuses the config outright.

✅ **THE PROOF, and it is the one stage 1 was defined by.** Replays driven through the REAL
`LiveRunner` methods (`_on_bar`, `_pump_fast`, `_warm_fast`, `_check_fast_feed`) against fake feeds
that hand bars out in wall-clock ARRIVAL order, diffed field by field against `run_dual` on the
identical frames.

| window | bars | trades | re-entries | total R | decision fields differing |
|---|---|---|---|---|---|
| 2025-01-01 → 2025-04-01 | 5,875 M15 / 17,625 M5 | 7 = 7 | 1 = 1 | +7.0248 = +7.0248 | **0 of 26** |
| **2020-01-01 → 2026-08-23** | **157,004 M15 / 470,995 M5** | **185 = 185** | **29 = 29** | **+126.0985 = +126.0985** | **0** |

**On the full 6.6 years every decision field is identical on all 185 trades** — direction, entry
and exit price, entry and exit time, R, exit reason, kind, stop distance, costs, both excursion
PRICES, the target ladder and the fib leg. **29 re-entries either side worth +22.0000R either
side.**

⚠ **Six DOLLAR columns do differ, and the reason is a harness artefact rather than the merge.**
`qty`, `risk_usd`, `pnl_usd`, the two excursion DOLLAR figures and the leg size are all higher live
by a ratio that is **constant to six decimals across all 185 trades (1.052632)** — and a constant
ratio is the signature of an equity offset, never of a decision. MEASURED cause: the lab takes a
re-entry inside the harness's warm-up window that loses $498.41, while the live warm-up replays
the fast feed for STRUCTURE ONLY and never arms one, so the two emulator balances part company at
the boundary and every later size scales by the same figure. (Predicted 1.052484 against the
observed 1.052632; the 0.014% residual is the warm-up's own primaries being sized on the two
different paths.)

🔴 **AND IT CANNOT HAPPEN ON A REAL BOT, which is the part worth keeping.** `warm()` ends with
`reanchor_equity("after warm-up")` — the emulator's balance is thrown away and replaced with the
BROKER's, and it is re-anchored again on every flat bar. **The warm-up equity path reaches nothing
live.** The harness has no broker to re-anchor against, which is exactly why a live-vs-lab
comparison is made on DECISIONS and not on dollars — the same restriction
`algos/tools/shadow_diff.py` already carries.

⚠ **Driving the runner rather than re-creating its poll order is load-bearing** — the first version
of that harness reimplemented the loop and spent its time finding its own bugs instead of the
runner's.

🔴 **THE PLAN ABOVE IS WRONG ON ONE POINT AND IT IS CORRECTED HERE RATHER THAN QUIETLY EDITED:
STAGE 1 CANNOT BE RUN ON A LIVE BOT "PLACING NOTHING". THE PROOF IS OFFLINE, AND HAS TO BE.**
Stage 1 was written as *a second feed into the runner, placing NO orders* — run it beside the live
bot for a while and watch. **That is not possible, because the primary and the re-entry share ONE
position slot in the same `Execution` object.** A shadow re-entry does not sit beside the book, it
FILLS in the emulator and occupies that slot; the bridge then reconciles on the next 15m bar,
finds *the strategy believes it is in a position but MT5 has none*, and **HALTS** — correctly, and
by the design that makes every other guard here work.

⚠ So there is no "observe it live" step. **The order is: stage 2 (the bridge can mirror a
re-entry) and stage 3 (the refusal becomes a capability check) BOTH land before anything runs on a
bot at all.** ✅ Nothing is lost by that: the claim stage 1 exists to prove is about the MERGE, and
the merge is proved better offline than live — against `run_dual` on the same bars, where a
disagreement is a diff rather than something to be spotted in a log.

⚠ **The shadow ledger records are still worth having** (`secondary_shadow_fill` /
`secondary_shadow_stop`) — they are what a dry run reports once stage 2 exists, and `shadow` is in
the NAME rather than a field, because a field can be dropped by a consumer that never heard of it
and a shadow fill read as a real one would put a trade in the book that never happened.

🔴 **FIVE DEFECTS, AND NOT ONE WAS FOUND BY READING THE CODE.** Every one surfaced by running the
merge over real bars or by a test going red.

1. **The steppable gate DEADLOCKED two thirds of the fast stream.** It asked *has the 15m stream
   reached this bar* as `open <= newest primary close`, where the real question is *have all 15m
   bars CLOSING at or before this bar been pushed* — which is `open < newest close + one primary
   bar`. The strict form made a fast bar wait for a 15m bar that closes AFTER it, which then
   advanced the context past it and made it permanently unsteppable.
2. 🔴 **A SESSION BREAK STRANDED A FAST BAR, ONCE PER TRADING DAY.** Even corrected, that gate
   assumes primary bars are CONTIGUOUS. Gold breaks daily. MEASURED before the fix: **13 forced
   re-warms on a three-month replay, one per day.** ✅ `flush_fast_before` fixes it by asking the
   merge rule directly — *does this bar open before the primary I am about to push* — which needs
   no assumption about spacing and is exact across a break, a weekend and an outage alike.
3. **The warm-up bookmark dropped one fast bar on every restart.** It was set AT the 15m context's
   close, and `new_bars` hands out bars strictly newer — but a fast bar opening exactly at that
   instant is the next one DUE, not a late one. One silent hole in a streaming state machine per
   start. Caught by the merge pairing being short by exactly one entry.
4. **A tz-aware timestamp compared against a tz-naive feed index.** The guard built an aware
   timestamp unconditionally, and pandas refuses to compare the two. ⚠ **CORRECTED 2026-09-01, and
   the correction matters more than the defect did: this file first recorded the reason backwards.**
   It said `feed.to_canonical` builds a NAIVE index and that the raise would have happened ON THE
   BOX. Both are false — `mt5_ops.get_candles` stamps its time column `utc=True` and `to_canonical`
   passes it straight through, so **the live frame is tz-AWARE**; it is the LAB bar cache that is
   naive, which is where the raise actually happened. The shipped guard branches on the frame's own
   timezone and is right either way. **A guard whose recorded reason names the wrong side is the
   next person's wrong mental model** — and the wrong version also overstated the defect as a live
   outage.
5. **The fast frame numbered from 1 where the lab numbers from 0.** No decision moves (every
   comparison on that feed is between two of its own indices) and it made a re-entry's recorded
   `entry_index` disagree with the lab's for ever — **the B-LEG harness trap**, which
   `strategies/python/mpc_bleg/CLAUDE.md` records as 2,409 comparisons failing at one flat offset
   while the logic was identical.

🔴 **AND ONE IN THE PROOF ITSELF, WHICH IS THE MOST TRANSFERABLE.** The first trade-comparison
script read its fields with `getattr(t, name, default)` and asked for `entry`, `exit` and
`entry_src` — **none of which `Trade` has**, so three of its nine columns compared nothing to
nothing and would have called two different books identical. The field list is now DERIVED from
the dataclass, so a rename breaks the script and a new field is compared from the day it exists.
**This repo already records the same failure** (`entry_time` against a record whose field is
`entry_ms`); it recurred inside the tool written to check a live-path change.

**Two design rules this stage fixed in place, both about the same asymmetry:**

- 🔴 **THE PRIMARY IS NEVER HELD UP BY THE RE-ENTRY'S FEED.** A 15m bar is stepped the moment it
  closes; a fast bar that turns up after that has missed its slot and is REFUSED rather than
  stepped against a context from its own future. The fast pump also has its OWN exception handler
  — unguarded, anything raising in it fell through to the loop's handler and **the primary bars
  were never read at all**, so a fault in the re-entry's feed would have stopped the bot managing
  a live trade. Found by `test_a_healthy_loop_reads_bars_and_reports_the_link_up` going red with
  `bar_calls == 0`.
- ⚠ **A bot with the re-entry OFF keeps the primary path it has always had, byte for byte.**
  `_make_clock` hands it a `_SingleFeedClock` that holds no ordering rule at all. Turning the
  re-entry on is the change that moves a live bot onto the merged path, once, on purpose.

⚠ **`assert_supported`'s message was WRONG and is fixed in the same change** — it said *"a
1-minute bar stream"* when the fill clock has been FIVE minutes by default since 2026-08-21 and is
configurable either way. **A refusal that names the wrong feed is worse than a vague one: it sends
the next reader to build the wrong thing, confidently.** The refusal itself is unchanged and must
not be softened until stage 2 lands.

**TESTED:** `algos/tests/test_dual_feed_merge.py` — 11 tests driving the real runner methods, six
mutations each reddening its own named test. 1,355 tests green across `algos/` and the strategy.

**Stage 2 — the bridge places a second entry.**
`assert_supported`'s three refusals all trace to one sentence: the bridge *"mirrors ONE entry limit
and one ratcheting stop"*. A re-entry needs an entry limit at its own price with its own stop, rested
on the faster clock and cancellable (`exec_sec_max_wait_bars`, `exec_sec_rest_and_leave`).
⚠ **Dry run first — the runner already defaults to it and requires `--live` to be typed.** Run it
alongside the live bot for a week and diff intended orders against what the lab says.

**Stage 3 — turn the refusal into a CAPABILITY check.**
`assert_supported` should stop asking *"is this setting on"* and start asking *"do I have the feed
this configuration needs"*. Until stage 2 lands it must keep refusing — **the refusal is correct
and must not be softened to get a bot started.**
✅ **And the check has to run BEFORE the restart.** `promote_preview` should exercise the same
startup path it claims to verify, so a configuration that cannot start is refused while the bot is
still happily running. That is the fix for the trap at the top of this gap.

**Stage 4 — enable on demo, measure, then decide.**
Demo only, one bot, and compare live decisions against the lab on the same bars before it goes near
anything else.

#### What must stay true throughout

- ⚠ **No parity gate covers any of this** — the Pine has no re-entry at all. The `run_dual` replay
  is the only evidence there will ever be, so it is a LAB finding on the live side and should be
  described that way.
- ⚠ **Do not soften `assert_supported` to make a bot start.** It exists because a silently
  mis-executed strategy diverges from every backtest with nothing saying why.
- ⚠ **`exec_tp1_pct` / `exec_tp2_pct` and `exec_scale_in` are refused for the SAME underlying
  reason** (one entry limit, one stop). Stage 2 is the shared unlock; whoever does it should read
  all three refusals together rather than fixing one.
