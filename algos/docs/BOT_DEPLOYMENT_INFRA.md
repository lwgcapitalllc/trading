# Bot Deployment Infrastructure — Reusable Learnings

**Purpose:** Capture what was learned from the first algo attempt (the four bots
SMC Trend, Scalper, FFT, Mean Reversion — all deleted 2026-06-22) so the *deployment
plumbing* survives even though the bots are gone.

**Why this doc exists:** The first attempt did it backwards — strategy logic and risk
management were baked straight into a bot and pushed to a demo account with no backtesting.
That approach failed and the bots were deleted. But the *infrastructure* learned along the
way is genuinely reusable. The new process is in `docs/BOT_DEVELOPMENT_METHOD.md` (S.Y.S.T.E.M.);
this infrastructure only comes into play at the **E (Evaluate / demo)** and **M (Master / deploy)**
steps — never before a strategy has passed backtest + robustness.

**Scope:** Everything below is **MT5 / PU Prime** learning. There is **no NinjaTrader (NT8)
live-bot runtime** — see "The NT8 gap" at the end.

---

## The reusable pieces (and where each lives)

All of this code was **kept** when the bots were deleted. It is generic scaffold, not
bot-specific. The bots were just the example consumers.

### 1. MT5 connection — `algos/shared/mt5_ops.py`
The `BotMT5` class: log into an MT5 terminal, confirm the connected account number matches
the config (refuse to trade on the wrong account), and place / modify / close orders.
Symbol-parameterized, one shared instance per bot. This is the "how a bot talks to MT5" layer.

### 2. Config-driven instances — `config.json` per instance + `algos/bots/bot_utils.py`
Account number, symbol, risk %, dead-zone hours, and strategy params live in a per-instance
`config.json`, never hardcoded. `bot_utils.py` is the loader + logger + path resolver. To stand
up a new bot you write a config, not new code paths. (Instance dirs lived under
`algos/markets/fx/instances/<name>/`.)

### 3. Credentials pattern — `credentials.template.json` (git) + `credentials.json` (VPS-only)
A template with placeholder fields lives in git; the real `credentials.json` is gitignored and
exists only on the VPS. This is how account logins stay off GitHub. (The template file was
deleted with the bot suite — recreate it when the first new bot is stood up.)

### 4. Task Scheduler boot — `algos/scheduler/*.xml` + `algos/bots/launcher.py` + `startup_coordinator.py`
How bots auto-start on VPS boot:
- A per-bot Task Scheduler XML (e.g. the old `mean_reversion_task.xml`) registered as a `BOT_*`
  task, kicked by the `SYS_STARTUP` task at logon.
- `startup_coordinator.py` starts bots **one at a time**, and waits for each to print its
  "Connected | #<account>" line in its stdout log before moving on — so two bots never race the
  MT5 connection at boot. It clears a stale lock first and marks each bot's state.
- `launcher.py` is the universal launcher Task Scheduler calls: takes `--bot` + `--config`,
  resolves the script, writes the stdout log next to the config, and detaches the process so it
  survives the launching session closing.

### 5. MT5 connection lock — `algos/mt5_connect.lock`
A lock file that prevents two bots from initializing the same MT5 terminal connection at the same
moment during a simultaneous boot. Cleared by the coordinator at startup.

### 6. Liveness + control layer
- `algos/shared/bot_state.py` — single source of truth (`bot_state.json` per instance): heartbeat,
  status (running/stalled/stopped/offline), balance, daily/weekly P&L.
- `algos/notifications/monitor.py` — watches for stale logs / crashes and sends Telegram alerts.
- `algos/notifications/reporter.py` + `pnl_tracker.py` — daily report + P&L tracking.
- `algos/notifications/telegram_bot.py` — remote start / stop / restart of a bot from Telegram;
  the command-center Bots page drives the same actions over SSH.

### Supporting shared logic — four of these were DELETED 2026-07-31
Still present: `shared/shared_regime.py` (regime classifier shim) and `shared/structure_engine.py`
(swing/BOS detection) — both thin shims over the canonical `engines/`.

**Gone (commit `e92304a`, restorable — see [`DELETED_CODE.md`](DELETED_CODE.md)):**
`shared_risk.py` (portfolio risk budget), `shared_scanner.py` (multi-instrument watchlist scan),
`shared_ai_brain.py` (AI gate + trade logger), `shared_calmar.py` (Calmar tracker). They had no
importers for five weeks after the bots were deleted. The ideas are worth revisiting — the risk
budget especially — but read the real code out of git rather than rebuilding from this line.

---

## The lesson — what NOT to carry forward

The strategy signal logic **and the risk management** were baked inside each bot file
(daily-loss halts, profit-target stops, lock-in, consecutive-loss caps, position sizing). That is
the backwards part. Under the gated-layer model (`command-center/.../services/sizing_engine.py`,
`docs/dynamic_sizing_engine.md`): **a strategy only signals a setup; gates decide whether it's
allowed; the engine decides size.** A future bot should be **thin** — it connects, scans, signals,
and hands sizing/halts to the engine. Do not copy a bot's in-strategy risk logic.

---

## The NT8 gap (the known unknown)

Everything above is MT5/PU Prime. For NinjaTrader / futures there is currently **no live-bot
runtime at all** — the only NT8 process on the VPS is the *backtest agent* (`algos/nt8/nt8_agent.py`),
which drives Strategy Analyzer for the command-center lab. It is not a bot that trades.

So when a **futures** strategy reaches the E/M steps, these pieces have no NT8 equivalent yet and
are new ground:
- NT8 live order connection + account guard (the `mt5_ops.py` equivalent).
- NT8 strategy hosting / auto-start (NT8 runs strategies inside the platform, not as standalone
  Python processes — a different model from the Task Scheduler + launcher approach above).
- Liveness/state/alerting wired to an NT8-hosted strategy.

Treat the MT5 learnings as the *concepts* to reproduce, not code to port.
