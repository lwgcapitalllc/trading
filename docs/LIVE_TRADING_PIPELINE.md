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

### G10 — No account-level risk allocator

`CLAUDE.md` is explicit: `exec_risk_pct` is per-trade with nothing above it, the account-level cap is
**unbuilt, and is a prerequisite for running more than one bot live**. Also standing and unmeasured:
the A+ vs B-LEG overlap audit (do the two legs actually stay out of each other's way, or do they fire
on the same structure break?).

**Consequence for this plan: start with ONE bot.** A+ alone needs no allocator. Adding B-LEG needs
the allocator plus the overlap audit first.

### G11 — The Bots page is CORRECT for many bots and unreadable with them — raised 2026-08-04

Aaron's question, and the answer is yes on the part that matters: `ConfigureTab` maps over
`snapshot.bots` and renders a full section per bot — its own Deployed version card, its own promote
button, its own risk editor — and every endpoint is keyed by bot name, so promoting or restarting one
cannot reach another. Nothing here is single-bot by construction.

**What does not scale is the READING of it, and it gets worse exactly when it matters most.** Both
tabs are flat vertical stacks with no bot selector, no filter and no collapse:

- **Configure** is roughly a full screen per bot (risk editor + Account + Deployed version + a 47-row
  parameter accordion). Three bots is a scroll hunt; the promote button you want is somewhere in the
  middle of it, and the promote controls of the two bots you do NOT want to touch are identical and
  adjacent. That is a misclick surface, not just a layout complaint.
- **Monitor** already has a table, so it scales further, but the per-bot start/stop/restart buttons
  sit in rows that look alike, and the page-level Start / Stop / Restart act on ALL bots — a
  distinction that is easy to miss with one bot registered and expensive to miss with four.
- **The version card is per bot with nothing comparing them.** The question that will actually be
  asked once there are several — *which bots are behind the repo, which have a restart pending* — has
  no single place that answers it, even though `GET /bots/{name}/version` already returns everything
  needed.

**Fix before the second bot goes live, not after.** Sketch: a bot selector (or per-bot collapse,
defaulting to collapsed past one) on Configure; a fleet-level version summary row; and the global
Start/Stop/Restart visually separated from the per-bot ones. None of it is hard — it is layout over
endpoints that already exist per bot — which is precisely why it should not be left until the day
there is a live position on the line.

⚠ **This pairs with G10 and neither is sufficient alone.** G10 stops two bots overdrawing one
account; G11 stops a human doing the same thing by clicking the wrong row. Both are prerequisites for
running more than one bot live.

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

**Outstanding:** ship at `"% of price"` 0.10 (Run 7's measured best) **after** a fresh TradingView
export re-runs `compare_strategy.py` to exit 0 with the filter ON. Unit tests prove our two halves
agree; only an export proves we agree with TradingView.

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
2. **Shadow diff.** Replay the same window through the lab's python runner and diff the decision
   streams. They should be identical — the strategy is the same object. Any difference is a live-feed
   or clock problem, which is exactly what this step exists to catch.
3. **Feed parity.** `compare_feeds.py` against the live terminal — clock offset must read a flat 0h.
4. **Arm at reduced risk.** Not `exec_risk_pct = 10`. See the open question below.
5. **One bot only.** B-LEG waits for the allocator and the overlap audit (G10).

---

## 5b. First VPS startup — 2026-07-31

The first bot is configured and deployed: `mpc_sos_fade_demo`, on the **MT5_FFT** terminal
(`C:\MT5_FFT\terminal64.exe`), PU Prime demo **700107749** / `PUPrime-Demo` / **XAUUSD.s**.
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
| 3 | **Live `exec_risk_pct`** | 10% was measured at **−54.9% max drawdown** over 6.5 years, and Run 12 found the drawdown is a losing streak at that risk, not give-back — risk % is the only lever that moves it. On a demo this is a choice about what you want to learn, not a survival question, but it should be a deliberate number |
| 4 | **A+ only, or A+ and B-LEG?** | Recommendation: **A+ only.** Two bots need the account-level allocator (unbuilt), the A+/B-LEG overlap audit (never run), and the multi-bot Bots page (G11). All three are real work and none is on this plan |

---

## 7. Standing reminders this plan touches

- **The overlap audit** (`CLAUDE.md`, Aaron asked to be reminded): "the legs don't overlap" is design
  intent, never measured. A+ and B-LEG are the pair most likely to break it, because both can be
  triggered by the *same* structure break. Cheap to measure — run both over one window and count bars
  where both hold a position. Must happen before any two-bot live setup.
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
