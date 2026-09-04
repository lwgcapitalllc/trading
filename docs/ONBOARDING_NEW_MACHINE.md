# Onboarding a second machine — running the Command Center

**Who this is for:** someone who has cloned the repo and nothing else. No VPS, no MT5,
no data, no accounts.

**What you end up with:** the Command Center running locally in a browser, showing the
same runs, charts, trades, blocked setups and stress tests the first machine shows.

**Time:** about 20 minutes of setup, plus however long the data copy takes.

---

## Read this first — the repo is not the whole picture

Cloning the repo gives you all the *code*. It gives you almost none of the *data*.

Everything the Command Center actually displays is deliberately git-ignored, because it
is regenerable output, not source:

| What | Where | Size | In git? |
|---|---|---|---|
| Backtest runs, evaluations, stress tests | `command-center/backend/data/lab.db` | ~51 MB | no |
| Per-run output (equity curves, trades, charts) | `command-center/backend/reports/lab/` | ~28 MB | no |
| Broker bar history (what backtests replay) | `backtest/cache/*.csv` | ~17 MB | no |
| Tick history (only for tick-mode fills) | `backtest/cache/ticks/` | ~968 MB | no |
| Economic calendar (news filter) | `engines/news/data/events.json` | ~6 MB | no |

So a fresh clone starts the app with an empty database and an empty chart. That is
correct behaviour, not a broken install. **Step 3 is the step that fixes it.**

The one exception is `backtest/archive/` — that IS committed. It holds a frozen CSV
export of 7.9 years of trades for both strategies, readable with nothing installed at
all. If all you want to do today is analyse trades with Claude, skip to
[the archive](#shortcut-analyse-trades-with-zero-setup) at the bottom.

---

## Step 1 — Get the machine ready

macOS. Three things, and you probably have two of them.

```bash
git --version        # anything recent
python3 --version    # 3.9 or newer
node --version       # 18 or newer
```

If `git` prompts to install the Xcode Command Line Tools, let it — that also gets you a
working `python3`.

If `node` is missing:

```bash
brew install node
```

Notes on versions:

- **Python 3.9 is proven.** The first machine runs the macOS system Python 3.9.6 and
  everything passes on it. Newer is fine. Older will not work — the engines use
  `zoneinfo`, which landed in 3.9.
- **Node 18+ is required** by Vite 5. Node 20 is what the first machine runs.
- You do **not** need a virtualenv tool, Docker, MT5, NinjaTrader, or a broker account.
  The app creates its own Python venv on first launch.

---

## Step 2 — Point the config at your machine

One file has absolute paths in it, and they are the first machine's paths.

Open `command-center/backend/config.json` and replace every `/Users/alwg/trading` with
wherever you cloned the repo:

```json
{
  "monorepo_root": "/Users/YOURNAME/trading",
  "smart_money_root": "/Users/YOURNAME/trading/smart-money",
  "smart_money_config_path": "/Users/YOURNAME/trading/smart-money/config/config.json",
  "smart_money_reports_dir": "/Users/YOURNAME/trading/smart-money/reports",
  "instances_dir": "/Users/YOURNAME/trading/algos/markets/fx/instances",
  "ssh_alias": "forexvps",
  "nt8_agent_tunnel": "http://127.0.0.1:8765",
  "mt5_agent_tunnel": "http://127.0.0.1:8766"
}
```

Get this wrong and the Strategies page finds nothing — the scanner walks
`monorepo_root/strategies/` to discover them.

**Do not commit this change.** The file is tracked, so your edit will show up in
`git status` forever and will collide on the next pull. Tell git to ignore your local
version:

```bash
git update-index --skip-worktree command-center/backend/config.json
```

To undo that later: same command with `--no-skip-worktree`.

---

## Step 3 — Get the data

This is the step that makes the app show something. Ask the first machine's owner to
zip these four things and send them over (AirDrop, Dropbox, a USB stick — anything but
git):

| Copy this | Into this |
|---|---|
| `command-center/backend/data/lab.db` | same path |
| `command-center/backend/reports/lab/` | same path |
| `backtest/cache/` **without the `ticks/` subfolder** | same path |
| `engines/news/data/events.json` | same path |

That is roughly **100 MB**. Skip `backtest/cache/ticks/` — it is 968 MB and only matters
if you re-run a backtest in tick-fill mode. Bar mode, which is the default and the only
mode that gets compared against TradingView, does not touch it.

The command to produce that zip, run on the first machine from the repo root:

```bash
zip -r cc-data.zip \
  command-center/backend/data/lab.db \
  command-center/backend/reports/lab \
  engines/news/data/events.json \
  backtest/cache -x "backtest/cache/ticks/*"
```

Unzip it at the root of your clone. The paths inside already match.

**If you skip a piece, here is exactly what you lose:**

- No `lab.db` → the app boots, creates an empty database, seeds the prop-firm and
  personal rulesets, and shows zero runs. Everything else works; there is just nothing
  to look at.
- No `reports/lab/` → runs appear in the list, but opening one shows no equity curve,
  no trades and no charts. The DB row stores a path; the numbers live on disk.
- No `backtest/cache/` → price charts cannot draw and no new backtest can run, because
  there are no bars to replay.
- No `events.json` → the News & Holiday filter on each run goes inert and honestly
  reports that it has no calendar coverage. It is not broken. You can rebuild it
  yourself with internet and no VPS:
  ```bash
  command-center/backend/.venv/bin/python engines/news/tools/backfill.py --from 2021-01
  ```
  (Run that *after* Step 4, since it needs the venv to exist. It takes a few minutes for
  five years and only has to be done once — after that `./go` keeps it current by itself,
  and refuses to guess a start date if it ever finds the cache empty.)

---

## Step 4 — Launch it

```bash
cd command-center
./start.sh
```

First launch takes a few minutes: it creates the Python venv, installs the backend
requirements, and runs `npm install` for the frontend. Later launches are seconds.

Then open **http://localhost:5173**.

The backend's API docs are at **http://localhost:8000/docs** if you ever want to poke at
it directly.

Ctrl-C in that terminal stops everything.

### What you will see, and what is normal

`start.sh` also tries to open an SSH tunnel to the trading VPS. **You do not have VPS
access yet, so that will fail**, and it fails quietly in the background. This is
expected. It does not stop the app.

The consequence shows up in the sidebar, which has four health dots:

| Dot | Yours will be | Why |
|---|---|---|
| **API** | green | your own backend, on port 8000 |
| **SSH** | red | no tunnel to the VPS |
| **NT8** | red | NinjaTrader agent lives on the VPS |
| **MT5 Agent** | red | MT5 agent lives on the VPS |

Three red dots is the correct state for a machine without VPS access. Ignore them.

---

## Step 5 — Know what works and what does not

With the data drop and no VPS, **everything that reads is fully live**:

- Every backtest run, its KPIs, equity curve, daily P&L, per-ruleset PASS/DISCARD verdict
  and worthiness tier
- The full price chart — candles, sessions, market-structure overlays, trade markers, the
  fib and measurement tools, the Go-to-date jump. (Drilling down to a finer timeframe
  works only where the cache has those bars — see the coverage table below. M1 is not
  cached at all, so that drill-down needs the VPS.)
- Blocked setups and missed setups (the trades that never happened, and how close the
  dead ones came)
- Stress tests, Monte Carlo distributions, walk-forward, sensitivity, the A–F grade
- Portfolio stacks
- Rulesets, and editing the personal ones
- The News & Holiday filter on each run, once the calendar is in place
- The live News Calendar tab — that one only needs internet, not the VPS

**Running NEW backtests** is the split:

| Runner | Works without the VPS? |
|---|---|
| **Python** (`strategies/python/` — the SOS Fade and B-LEG bots) | **Yes**, as long as the window you pick is inside the bars already in `backtest/cache/`. The runner is cache-first and never phones home when the cache already covers the window. |
| **NinjaTrader** | No. Needs the NT8 agent and a real Strategy Analyzer on the VPS. |
| **MT5** | No. Needs the MT5 agent and a real Strategy Tester on the VPS. |

The cached bars are XAUUSD only, and the depth is **not** the same at every timeframe.
What the first machine has as of 2026-07-29:

| Symbol | Timeframe | Cached window |
|---|---|---|
| XAUUSD | **M15** | 2018-09-13 → 2026-07-29 (the full 7.9 years — this is the one the strategies trade) |
| XAUUSD | H1, H4 | 2019-11-12 → 2026-07-28 |
| XAUUSD | M5 | 2025-07-24 → 2026-07-27 (one year only) |
| XAUUSD.s | M15, H1, H4 | roughly mid-2025 → 2026-07-23 |

Ask for anything outside those windows and the run tries to fetch, which needs the VPS.
M15 is the designed timeframe for both strategies, so in practice you have the whole
history for the work that matters.

One quirk worth knowing: history-floor enforcement — the guard that refuses a window
starting before the broker really has bars — identifies the broker by asking the live
MT5 terminal. With no tunnel it cannot identify anything, so it reports "unknown" and
refuses nothing. Nothing lies to you; the bar-spacing backstop still catches substituted
bars downstream. It just means you should stay inside the cached window on your own
judgement.

### Running the test suites

Both are green on the first machine and should be green on yours.

```bash
command-center/backend/.venv/bin/python -m pytest backtest/tests/ -q
cd command-center/backend && .venv/bin/python -m pytest tests/ --ignore=tests/test_integration.py -q
```

**Never run a bare `pytest tests/` in the backend.** It includes `test_integration.py`, a
live suite that fires a real VPS backtest and runs `taskkill /f /im python.exe` on the
VPS — which kills both backtest agents and any run in flight. The tell that you got it
wrong: it takes 15 minutes instead of 5 seconds.

---

## Step 6 (optional, later) — VPS access

Only needed to run NinjaTrader/MT5 backtests, pull bar history you don't have, or
monitor the live bots. Skip until you need it.

It is a two-side job:

**Your side** — make a key and add the host:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/forexvps -C "yourname-macbook"
```

Then add this block to `~/.ssh/config`:

```
Host forexvps
    HostName <ask for the IP>
    User trader
    Port 22
    IdentityFile ~/.ssh/forexvps
    LocalForward 8765 127.0.0.1:8765
```

Send `~/.ssh/forexvps.pub` (the `.pub` one — never the other file) to whoever administers
the VPS.

**Their side** — append that public key to `authorized_keys` for the `trader` user on the
VPS. Nothing you can do from here.

Test it with `ssh forexvps` before relaunching the app.

**One trap, already solved in this repo, that will bite you if you hand-roll a tunnel:**
the `-L` forwards must target `127.0.0.1`, not `localhost`. The VPS resolves `localhost`
to IPv6 `::1`, and the agents bind IPv4 only. A tunnel built with `localhost` looks
perfectly healthy and forwards to nothing. `start.sh` already does this correctly — this
only matters if you open one by hand.

---

## Shortcut: analyse trades with zero setup

If today's goal is just "look at the trades with Claude", you do not need any of the
above. The repo already carries a committed export:

```
backtest/archive/2026-07-29_xauusd_15m_full_history/
├── README.md                    ← read this first; full column glossary + caveats
├── sos_fade/                ← SOS Fade SOS Fade: 188 trades, +109.5R
│   ├── trades.csv               ← every trade, winners and losers
│   ├── setups.csv               ← every setup that reached SOS, including the 512 that never traded
│   └── summary.txt              ← totals by year, regime, session, direction
└── b_leg/                    ← B-LEG: 58 trades, +3.5R
```

XAUUSD 15m, 2018-09-13 → 2026-07-29, both strategies, winners and losers. Point Claude at
the folder and start asking. The README explains every column and lists the caveats that
matter before you draw a conclusion from any of it.

---

## Troubleshooting

**"Port already in use" on launch** — `start.sh` clears ports 8000 and 5173 itself, so
this usually means a second copy is running. Ctrl-C the other terminal.

**Strategies page is empty** — `monorepo_root` in `config.json` is wrong. Step 2.

**A run opens but every chart is blank** — you copied `lab.db` but not
`reports/lab/`. The database stores paths; the numbers are on disk.

**The News filter says it has no coverage** — no `events.json`, or the run's dates fall
outside the months that were backfilled. Backfill more months (Step 3) and reopen.

**A run says "Reload charts"** — the cached chart spec predates a change. Click it.

**A run is stuck at "running" after a crash** — restart the backend. Startup
automatically marks stale runs and stress tests as failed and releases the platform lock.

**A backtest fails with "MT5 agent unreachable"** — you asked for a window that isn't in
the cache, so it tried to fetch. Either narrow the window to what's cached, or get VPS
access (Step 6).

---

## The 60-second version

```bash
# 1. prerequisites
python3 --version && node --version          # 3.9+, 18+

# 2. point config.json at your clone, then:
git update-index --skip-worktree command-center/backend/config.json

# 3. unzip the data drop at the repo root (lab.db, reports/lab, backtest/cache, events.json)

# 4. run it
cd command-center && ./start.sh              # → http://localhost:5173
```

Three red dots in the sidebar are expected without VPS access. Everything you read is
live; only new NT8/MT5 backtests need the VPS.
