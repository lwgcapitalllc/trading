# Portfolio Stacking — design

**Status:** Design only. Nothing built yet.
**Author:** drafted 2026-07-17.
**Problem:** Aaron is building more MPC strategies (independent narratives, e.g. SOS Fade + future
ones). He wants to run several of them **as one shared account** — one balance, one live risk budget
they compete for — and see the combined equity curve and drawdown, then backtest, forward test,
optimize, and stress test the whole account, not each bot alone.

This is **not** a set of sliced sub-accounts. The strategies genuinely share the same money and the
same risk limit. If two want to trade at once, they share the room; if the account is already near
its risk cap, the next strategy is shrunk or blocked; and when an open trade moves to breakeven, the
risk it was holding is freed for the others. All of that has to be simulated.

---

## 1. The mental model — one account, one live risk budget

A **portfolio** is **one account**. Each strategy is a **leg** that trades into it. There is one
balance, one open-risk budget, and one prop-firm ruleset for the whole thing. The legs do not own
money — the account does. A leg *asks* the account to enter; the account decides the size, or refuses.

```
Portfolio "Gold Stack"   account $40k · cap = 10% open risk · LucidFlex $50k Eval
├── leg 1  MPC SOS Fade   XAUUSD 15m   wants 10% per trade
├── leg 2  MPC <next>     XAUUSD 5m    wants  5% per trade
└── leg 3  MPC <next>     EURUSD 1h    wants  5% per trade
        every leg asks ONE account to size its trades against ONE live risk budget
        one balance · one open-risk total · one drawdown · one PASS/DISCARD verdict
```

"Each strategy is a separate bot, all sharing one account" is exactly right. In a backtest we
*simulate* that account: all legs run on one clock, all P&L lands on one balance, and one risk
manager gates every entry against the room left at that instant.

**The unit of truth is the account, not the strategy.** Every number (return, drawdown, open risk,
prop-firm verdict) is computed on the shared account, never by averaging the legs.

---

## 2. The three policies (locked 2026-07-17)

These are the trading-policy calls that shape the gate:

- **Not enough room → shrink to fit, with a floor.** If a leg's full requested size doesn't fit the
  remaining budget, it takes a smaller position using the room left, and is skipped only if that room
  is below a minimum worth trading.
- **Same-time tie → split by weight.** If two legs fill at the same instant and both can't fit, the
  free room is divided in proportion to the risk each asked for.
- **Cap base → % of live balance.** The open-risk cap is a percentage of the current account balance,
  so it grows as the account grows and shrinks as it draws down.

---

## 3. Core mechanism — the account is the broker

Standalone, a strategy like `mpc_sos_fade` sizes itself (`qty = equity × risk% / stop_distance`) and
always fills. In a shared account it stops doing both. A central **`PortfolioAccount`** owns the
money and the risk, and every entry goes through it.

### 3.1 One balance
All realized P&L from every leg accrues to one balance. Every leg sizes off *this* balance at the
moment it trades — so as the account grows or bleeds, all legs scale together.

### 3.2 Risk is reserved, then released automatically
Each open trade **reserves** risk:

```
reserved = position_size × point_value × max(0, entry − current_stop)        (long)
         = position_size × point_value × max(0, current_stop − entry)        (short)
```

measured in account dollars (so different instruments add up). The key word is **current_stop** —
this is recomputed **every bar** from the trade's live stop, so:

- Fresh trade, stop at 1R away → it reserves a full 1R.
- Trade hits TP1 and moves stop to **breakeven** → `entry − stop = 0` → **reservation drops to zero**,
  and that room is instantly free for another leg. This is your "at breakeven the risk is up for
  grabs," and it falls straight out of measuring risk to the stop, not to entry.
- Trade trails into profit (stop above entry for a long) → reservation is zero (locked profit isn't
  risk).
- Partial close (TP1 banks 30%) → smaller size → smaller reservation.
- Full close → reservation gone.

### 3.3 The cap
`cap = risk_pct × current_balance` (e.g. 10% of a live $40k = $4k of open risk allowed at once).

### 3.4 The entry gate (runs at FILL, not at order placement)
A resting limit that never fills should never hold room, so the gate runs when a trade actually
**fills**. The leg has already sized itself (its own risk % against the shared balance, off the
limit price); the account **scales that desired qty to the room** — it does not re-derive it, so a
leg run alone is untouched. At the fill bar:

```
desired_risk = |desired_qty| × stop_distance × point_value   # the leg's own size, in $ at risk
room         = cap − reserved_now
granted_risk = min(desired_risk, room)
if granted_risk < floor:  block (no trade)
else:                     qty = desired_qty × (granted_risk / desired_risk)   # shrink to fit
```

(Built this way in `account.py::request_fill` — scaling the bot's qty rather than recomputing it
is what keeps `compare_strategy.py` exit 0: the bot sizes off the limit price at placement, and the
account must not silently re-size off the fill price.)

- **Ties (same fill bar, both can't fit):** split `room` across the tied legs in proportion to each
  `desired`, then floor-check each. (A refinement — re-splitting a floored leg's share to the
  survivors — is possible later; v1 splits once.)
- A shrunk or blocked entry keeps the leg's own stop and TP plan; only the size changes.

### 3.5 Account-level halts
The ruleset's daily-loss cap and trailing max-loss apply to the **combined** balance, so a halt stops
**every** leg (this is one shared account — one leg can't keep trading after the account is halted).
This reuses the rules the `sizing_engine` / evaluator already encode, applied to the shared balance.

---

## 4. One clock

The legs can be different instruments and timeframes, but the account's balance and open-risk total
must be correct at every instant a leg asks to trade. So all legs run on **one merged timeline**:

- Merge every leg's bar stream into one event stream ordered by UTC timestamp.
- At each timestamp, process in this order: **(1) position updates first** — exits, stop moves,
  partial closes — so freed room is released *before* anyone tries to enter; **(2) then entry
  requests**, sized and gated against the now-current room.
- A 5m leg simply steps three times per 15m leg's bar; risk is in dollars, so different instruments
  compose on one budget.

Fills within a bar stay each strategy's own concern (its existing intrabar-path model); the account
only sees the resulting entry/exit/stop events, in timestamp order.

---

## 5. The strategy seam (and how parity is preserved)

Each strategy's execution layer gives up three things to the account, and keeps the rest:

| Moves to the account | Stays in the strategy |
|---|---|
| the balance | signal → trade intent |
| sizing (`grant`) | stop / TP ladder / breakeven / trail logic |
| entry permission | intrabar fill mechanics |
| open-risk reservation + halts | reporting its current stop each bar |

Concretely the strategy calls: `qty = account.request_fill(leg, dir, stop_distance, risk_pct)` where
it used to compute its own qty; `account.update_stop(leg, current_stop, qty)` each bar; and
`account.on_close(leg, pnl)` on exit.

**Standalone is a portfolio of one.** A `SoloAccount` — one leg, no cap, sizes off its own balance —
reproduces today's behaviour exactly, so `mpc_sos_fade` run alone is unchanged and still matches the
Pine. The **parity harness (`compare_strategy.py`) staying exit 0 after this refactor is the gate**
that proves the seam didn't change standalone behaviour. Same code, two accounts: one leg unconstrained
= today; N legs with a cap = the shared portfolio.

---

## 6. Where the code lives

**`backtest/portfolio/` — the shared-account simulator (app-agnostic, importable standalone).**
- `account.py` — `PortfolioAccount`: balance, reservations, the cap, the `request_fill` gate
  (shrink-to-floor + split-by-weight), halts. Plus `SoloAccount` for standalone/parity.
- `clock.py` — the merged event stream over N legs (§4).
- `simulator.py` — drives the legs on the clock through the account; collects the combined trade
  stream, each leg's trades, and the **contention log** (every entry the cap shrunk or blocked, and
  what it would have made).
- Reuses `backtest/output.py::build_results` for the combined `{equity_curve, daily_pnl, kpis}` — the
  simulator produces one merged trade stream, so the whole existing lens layer (Sharpe, evaluator,
  worthiness, the equity panel) consumes it unchanged.

**`command-center/` — orchestration, storage, UI** (§8): `services/portfolio_runner.py`,
`routers/portfolios.py`, `models.py`, `lab_db.py` tables, and a Portfolios page.

**Relationship to the existing `sizing_engine`.** That engine already sizes against "room left" and
reserves open-trade risk — but *post-hoc, for one strategy's finished trade list, per ruleset*. The
portfolio account is the **live, cross-leg** version of the same idea: room and reservation evaluated
every bar across all legs, with stops that move. Share the pure risk-room helper where practical;
don't fork the concept into two silently-different implementations.

---

## 7. Outputs — the account view

The combined equity curve is the headline, but the reason to share an account is to see the
interaction, so the run produces:

- **Combined equity curve + drawdown** — one account, coloured by leg. Reuses the TradingView equity
  panel; each point still carries its own run-up/drawdown excursion.
- **Open-risk-over-time** — the account's used risk vs the cap, through the run. Shows how often you
  were near the ceiling.
- **Contention log** — every entry the cap **shrank or blocked**, when, which leg, and the P&L it
  missed or gave up. This is what tells you the strategies are colliding, so you can tune them to
  trade different regimes/times (your goal) — and what it costs when they don't.
- **Per-leg contribution** — each leg's net, its share of account net, its own drawdowns.
- **Correlation matrix** — pairwise correlation of the legs' daily P&L. Low/negative is the point.
- **Diversification drawdown** — the account's max DD vs the sum of the legs' — the benefit, or the
  warning that they bleed together.

Everything except the combined curve and contention log is arithmetic over the per-leg trade streams;
the contention log comes straight from the gate.

---

## 8. Backtest / optimize / stress / forward

- **Backtest** — §3–§7. The core.
- **Optimize** — per-leg param tuning already exists (tune a bot alone, then add it). New: search
  over the account knobs — the risk cap, per-leg risk %, which legs are on, tie priority — to
  maximise an account objective (return ÷ max-DD, or account Sharpe). Reuses `expand_grid` +
  `objectives.py`.
- **Stress test** — the combined trade stream feeds the existing Monte Carlo / walk-forward /
  sensitivity, which already work on a trade list. **Caveat:** resample by **day-block** (keep each
  day's trades together), not by individual trade, or you destroy the cross-leg co-movement that is
  the whole reason to share an account.
- **Forward test** — same portfolio definition, live trade source: each leg deployed as a bot on one
  demo account, the account view reading the real account's fills through the same aggregator. Later
  phase — needs the live-bot deploy path (currently empty) and each leg backtest-proven first
  (`docs/BOT_DEVELOPMENT_METHOD.md`).

---

## 8b. Two views — the screen vs the truth

There are two ways to look at a stack, and they answer different questions:

- **Combine screen (cheap, idealized).** Run each strategy alone, then add the results. Answers *"do
  these smooth each other out?"* — correlation, combined drawdown, diversification. Nearly free
  (reuses stored runs). But it assumes every leg trades a full account and never gets blocked, so it
  **overstates** the stack. It's a candidate screen, not the demo result.
- **Shared-account simulation (§3–§7, the truth).** The legs fight for one live risk budget — shrunk,
  blocked, sharing freed breakeven room. This is what the demo will actually do, and the number to
  trust before running the stack for real.

The less the legs overlap (the design goal), the closer the two converge — and the simulation's
contention log is what tells you *how much* they collided. Build the screen first (Phase 0), the
simulation second (Phase 1).

---

## 9. Build phases

0. **Combine screen** (`backtest/portfolio/combine.py`) — add stored single-run results; correlation +
   diversification drawdown. The cheap candidate screen. *Idealized — no contention.*
1. **Shared-account simulator** (`backtest/portfolio/`) — the account, the clock, the strategy seam,
   the simulator, the contention log. Parity harness green with `SoloAccount`. *This is the real work.*
2. **Lab integration** — tables, `portfolio_runner`, router, Portfolios page; combined curve +
   verdict + open-risk chart + contention log.
3. **Analytics + portfolio optimize + stress** — contribution/correlation/diversification; account-knob
   search; day-block stress resampling.
4. **Forward test** — deploy legs to one demo account; same view, live trades.

---

## 10. Open items (recommendations in bold)

- **Cap base = realized balance, not equity.** "% of live balance" reads the **realized** balance, not
  balance + open profit, so open winners don't inflate the cap and reflexively grow every size.
  **Recommend realized**; revisit if you want unrealized profit to expand the budget.
- **Tie re-split** — v1 splits the room once and floors; a leg dropped by the floor doesn't hand its
  share back. **Fine for v1**; add re-splitting only if ties turn out common.
- **Same strategy as multiple legs** — allowed; the leg id, not the strategy id, is the unit.
- **Halt granularity** — a hard account halt stops all legs mid-day. Confirm that's desired vs a
  softer "no new entries, let open trades run." **Recommend hard halt** to match a real prop account.
- **Execution refactor risk** — routing sizing/permission/balance through the account touches
  `mpc_sos_fade/execution.py`; the parity harness is the guard, but budget for it.
```
