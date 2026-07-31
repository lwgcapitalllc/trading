# Deleted Code — what it was, and how to get it back

**Purpose:** A recovery index. When code is deleted from `algos/` because nothing uses it any
more, this file records **the commit that removed it**, **what it actually did**, and **the exact
command to restore it** — so a future need is a two-minute `git checkout`, not a rewrite from
memory.

**Why a file and not just git history:** git remembers everything and surfaces none of it. Nobody
greps a deleted file, because greps only search what exists. Six months from now the question is
"did we ever build a risk allocator?", and the honest answer lives here or nowhere.

**Rule when deleting code from `algos/`:** delete it, commit that deletion ON ITS OWN, then add a
row here with the commit hash. One deletion per commit, so `git show <hash>` restores exactly one
idea.

---

## How to bring something back

```bash
# See it without touching the working tree
git show <commit>^:algos/shared/<file>.py

# Restore it to where it was
git checkout <commit>^ -- algos/shared/<file>.py

# See everything that commit removed
git show --stat <commit>
```

`<commit>^` is the parent — the last commit where the file still existed. Restoring from the
deletion commit itself gets you nothing, which is the classic mistake.

---

## 2026-07-31 — the four first-attempt-bot shared modules

**Commit: `e92304a`** · restore with `git checkout e92304a^ -- algos/shared/<file>.py`

All four were written for the SMC Trend / Scalper / FFT / Mean Reversion bots deleted on
2026-06-22. They had **zero importers** for five weeks; only documentation still mentioned them.

### `shared_risk.py` (251 lines) — **the most likely one to want back**

A portfolio-level **dynamic risk / capacity engine**, `RiskEngine`. It replaced "X% per trade, Y%
daily cap" with a continuously recalculated budget:

```
available_risk = daily_budget − used_risk − realized_daily_loss
```

`used_risk` was the summed live stop-to-price distance across every open trade, so a trade moved to
breakeven contributed ~0 and a trade trailing in profit contributed a **negative** value — locking
in gains actually *opened* capacity above the baseline budget. The daily hard cap stayed as a
separate floor: once realised loss hit the budget, new entries were blocked regardless. Default
budget equalled the old static cap, so day-one behaviour was unchanged.

**Why this matters now.** The root `CLAUDE.md` names an **account-level allocator as UNBUILT and a
prerequisite for running more than one bot live** — one risk pool that concurrent setups either
share or are blocked by, never stacked. That is close to what this file already did, for a single
bot instance. It is not a drop-in (it budgets per bot, not per account, and it predates the
`algos/live/` design), but it is a real starting point and a set of decisions already thought
through. **Read it before designing the allocator from scratch.**

### `shared_scanner.py` (228 lines) — multi-instrument watchlist scanner

Ran a bot-supplied `detect_fn(symbol)` across a watchlist and returned setups ranked best-first by
confluence score. No strategy logic of its own. Three things in it are worth stealing if a
multi-symbol bot is ever built:

- **Unresolved symbols failed LOUDLY** — a warning log, an append to `symbol_errors.log`, and an
  `unresolved_symbols` list written to `bot_state` so `monitor.py` could Telegram once per bad
  symbol per day. A silently wrong symbol name is the exact failure that looks like "no setups".
- **A volatility floor** — `H1 ATR(5) / H1 ATR(20)`, skipping compressed instruments.
- **Sitting out** — when the whole watchlist was below the floor it traded nothing rather than
  taking the least-bad setup.

### `shared_ai_brain.py` (525 lines) — ML trade classifier + trade/performance logger

A scikit-learn (`RandomForestClassifier` / `GradientBoostingClassifier`) model over closed trades,
gated so it could not act on noise: **100 trades minimum before activating**, an **AUC ≥ 0.55**
gate, retrain every 20 new closed trades. Also carried a daily performance logger (drawdown, trade
count, simultaneous positions), a drawdown-awareness feature, and re-entry outcome tracking.

**Treat with care if revived.** The gates were the good part; the premise — that a few hundred
trades can train a useful classifier — is unproven here, and the repo's trading philosophy is
explicitly *few high-quality setups*, which is the sample-size regime ML is worst in. The trade and
daily-performance LOGGING is the reusable half, and `algos/live/ledger.py` now covers that ground.

### `shared_calmar.py` (105 lines) — live Calmar ratio tracker

`CalmarTracker`: recorded equity after every trade close, tracked peak and max drawdown, and
printed a performance report at each daily reset. Calmar = annualised return / max drawdown, with
the bands it shipped with (2.0 okay · 3.0 prop-firm ready · 5.0+ generational).

**Superseded.** The command-center backtest lab computes Calmar over full runs, and
`command-center/frontend/src/pages/BacktestDetail.tsx` already surfaces it. A live tracker only
becomes interesting again if a bot needs to *act* on its own rolling Calmar.

---

## What was NOT deleted, and why

`algos/shared/shared_regime.py` and `algos/shared/structure_engine.py` also have zero importers
today, but they are **thin shims over the canonical `engines/`**, named in the root `CLAUDE.md` as
the seam through which `algos/` consumes them. `algos/live/` currently reaches the engines through
`backtest/replay` instead, so the shims are unused rather than obsolete. Deleting them is an
architecture decision, not a cleanup — leave them until that decision is actually made.
