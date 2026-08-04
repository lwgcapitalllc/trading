# Live Setup Alerts — Telegram messages that say WHY, before the outcome is known

**Purpose:** The build plan for Telegram alerts that announce a setup while it is still forming —
the confluences the bot has, the entry it is resting a limit at, and the stop — and then report what
became of it, including the setups that never became trades.
**Scope:** The alert layer only: what is sent, when, and where the text comes from. It does NOT
change strategy logic, engines, the order bridge, or the backtest lab. Nothing here may move a trade
decision.
**Status:** NOT STARTED — specced only. Deferred by Aaron 2026-08-03 ("I won't build it now").
**Created:** 2026-08-03.
**Parent:** `docs/LIVE_TRADING_PIPELINE.md` — this extends its step 7 (Telegram alerts), which today
specifies entry and exit only.

**Aaron's requirement (2026-08-03):** *"a template of saying potential trade — here are the
confluences, here is possible entry with SL, that way when we enter a trade we know why. Also it will
say if a trade was spiked after a while… if a trade left us and we did not get in for some reason."*

---

## 1. The one-paragraph answer

**Roughly 80% of this already exists and is already running.** The live bot steps the full strategy
on every closed 15m bar, and it already records — every bar, to disk — the setups its own rules
refused (`BlockedSetup`) and the setups that reached 2-of-3 or better and died (`MissedSetup`). Both
carry the confluence breakdown **already written out in English**, because the backtest chart needed
it. "Price left without us" is not a new question: it is miss reason **code 7, "Never filled"**, with
a sentence already attached. What is missing is small: those records go to a log file and nothing
sends them anywhere; there is no alert at the moment a limit is *placed* (only after the fact); and
the entry alert does not carry the reason it fired. **This is a routing and formatting job, not a
detection job.**

---

## 2. What already exists

| Piece | Where | State |
|---|---|---|
| The live bar loop | `algos/live/runner.py::_on_bar` | Steps signals → sequence → execution every closed bar |
| Block/miss recording, live | `algos/live/runner.py::_drain_records` | Drains `execution.blocks` / `.misses` to the ledger each bar, then clears them |
| The confluence text | `strategies/python/mpc_sos_fade/execution.py::MissedSetup.met_lines` | Already produces `Arm — Sweep · Day Low` / `SOS — confirmed` / `Zone — 0.5-0.886 tagged, FVG live` |
| The seven miss reasons | same file, `_MISS_LABEL` / `_MISS_REASON` | Label + full sentence per code, incl. **7 "Never filled"** |
| The seven block reasons | same file, `_BLOCK_LABEL` / `_BLOCK_REASON`, `_block_codes` | Every rule refusing a setup, in the Pine's precedence |
| The resting order | same file, `_Pending` | `dir`, `edge` (entry), `sl`, `tp1`, `tp2`, `qty`, `sos_bar`, `fib` |
| The fib ladder, frozen | same file, `_freeze_fib` → `TradeFib` | Eight `(ratio, price)` pairs snapshotted at placement |
| Which source armed it | `sequence.py::SeqState.l_arm_src` / `.s_arm_src` | `"SWP"` / `"DIV"` / `""` |
| The swept pool's name | `signals.py::Signals.recent_bsl` / `.recent_ssl` | `"Day Low"`, `"Asia High"`, … |
| Telegram send | `algos/shared/notify.py` | `send_telegram_id` returns the message id, and takes `reply_to` — threading is already built |
| Per-bot routing | `algos/live/runner.py::_notify` | Each bot can post to its own chat as its own bot |
| Message formatting | `algos/live/alerts.py` | Pure functions, no network, no state — `format_entry` / `format_exit` today |

**The point of the table:** every fact the messages need is already computed on the live box. The
build adds no new market analysis.

---

## 3. What is missing

1. **No alert when a limit is placed.** Blocks and misses are recorded when a setup is *refused* or
   *dies*. There is nothing at the forward-looking moment — "we are resting an order here, this is
   why, this is the stop."
2. **The entry alert does not say why.** `format_entry` sends direction, entry, stop, stop distance
   and lot size. No confluences.
3. **Nothing reaches Telegram.** `_drain_records` writes blocks and misses to the ledger file and
   forgets them.
4. **`_Pending` does not carry its own reason.** It has the prices and the fib ladder, not the arm
   source or the zone state. That is the one real code addition (§6).

---

## 4. The four messages

One Telegram **thread per setup**. Message 1 is the root; every outcome replies to it, so a setup and
what became of it are never read apart. `send_telegram_id` + `reply_to` already does this — it is the
same mechanism that makes a trade exit reply to its entry.

### 4.1 Potential trade (the root)

Fires when the bot places a resting limit — i.e. all three confluences are in and no rule refused it.

```
🔍 POTENTIAL · SHORT
mpc_sos_fade — XAUUSD

Arm — Sweep · Day High
SOS — confirmed
Zone — 0.5-0.886 tagged, FVG live

Entry: 3,412.55   (limit resting)
Stop: 3,428.90
Stop distance: 1,635 pips
TP1: 3,389.20   TP2: 3,371.05

Sat 03 Aug 2026, 14:15 UTC
```

### 4.2 Entered — replies to 4.1

The existing entry alert, plus the confluence block, so the message says why it fired. Where there
was no root message (a fill on a setup the bot never announced), it carries the header itself.

### 4.3 Never filled — replies to 4.1

Miss code 7. This is Aaron's "a trade left us and we did not get in".

```
👋 NEVER FILLED

All three confluences met and the limit rested —
price never came back to touch it.

Setup died: Sat 03 Aug 2026, 19:45 UTC
```

### 4.4 Blocked — replies to 4.1 if one exists, else standalone

A setup that was fully ready and one of *your own rules* refused. This is the message that tells you
whether a rule is protecting the account or costing it. Carries every refusing rule, not just the
first — `BlockedSetup.reasons` already returns the full list in precedence order.

**Also worth carrying, and cheap:** the *near* misses that never got as far as an order — a setup
that reached the zone and found no gap to enter from (code 3). `MissedSetup.near` is the strategy's
own built-in filter for "worth looking at", ported from the Pine's default view. Use it. Do not
invent a second definition.

---

## 5. How noisy — measured

From `strategies/python/mpc_sos_fade/CLAUDE.md`, on XAUUSD M15, 2025-03-04 → 2026-07-27 (33,041
bars, shipped defaults):

| | count over ~17 months | ≈ per month |
|---|---|---|
| Trades | 46 | 2.7 |
| Blocked setups | 80 | 4.7 |
| Missed setups | 93 | 5.5 |
| — of which "No retrace" (routine, none near) | 50 | 2.9 |
| — of which "No FVG in zone" (all near) | 35 | 2.1 |
| — of which **"Never filled"** | **4** | 0.2 |
| — of which "Final hour" | 4 | 0.2 |

⚠ **The "Potential trade" count is INFERRED, not measured.** A setup that places an order becomes
either a trade (46) or a never-fill (4), so ≈50 over the window ≈ **3/month**. Measure it properly
before shipping — replay the window and count `_Pending` transitions — because that is the message
that fires most often and the one that would make the group unreadable if the estimate is wrong.

Recommendation: send **potential / entered / never-filled / blocked** by default and leave the
routine "No retrace" misses OFF. That is roughly one message every two or three days.

---

## 6. The one real code change — `_Pending` must carry its own reason

`_Pending` holds the prices and the frozen fib. It does not hold the arm source, the swept pool name,
or the zone/FVG state. Add them the same way the fib was added: an all-or-nothing snapshot taken in
`_place_entries`, on the bar the order is placed.

```python
@dataclass
class ArmContext:
    """Why this order exists, frozen on the bar it was placed. REPORTING ONLY."""
    arm_src: str      # "SWP" / "DIV" / "SWP+DIV"
    swept: str        # "Day High" — empty when divergence-armed
    zone: bool
    fvg: bool
    sos_bar: Optional[int]
```

**Three rules, all of them load-bearing:**

⚠ **Snapshot at PLACEMENT and read it back from the ORDER — never re-read `sig` at the fill.** A fib
keeps extending and a sweep keeps being superseded while a limit rests. Re-reading at the fill would
describe a setup the order was never priced against, while the stop and targets beside it in the same
message are frozen at placement. This is the identical trap already recorded for `TradeFib`
(`mpc_sos_fade/CLAUDE.md` → the ⚠ on `Trade.fib`), and it has a test there worth copying.

⚠ **REPORTING ONLY.** Nothing may read an `ArmContext` back into a decision. That is what keeps
`compare_strategy.py` a valid parity gate — it diffs the `px_*` decision stream, and this touches
none of it. Same standing as `mfe_usd`, `tp1`/`tp2` and `Trade.fib`.

⚠ **Compose the arm text with the EXISTING helper, do not write a second one.** `_record_misses`
already builds `"Sweep + RSI div · Day High"` (execution.py ~866-871). Extract that into a function
and call it from both places. Two functions producing the confluence sentence is two claims about one
setup, which is this repo's most-repeated failure.

---

## 7. Where the alerting lives

A new module beside the bot: **`algos/live/setup_alerts.py`**.

- **Formatting is pure**, in `algos/live/alerts.py` beside `format_entry` / `format_exit` — no
  network, no state, so the exact wording is unit-testable and changing it can never change a trade.
- **Sending** goes through `runner._notify`, so per-bot chat and token routing come for free.
- **Never raise.** `notify.py`'s standing rule: a notifier that can take down a trading loop is worse
  than a missed message. Every failure path prints and returns.
- **Thread ids are held in memory** on the runner, keyed by side + `sos_bar`, and dropped when the
  setup resolves. A lost id is cosmetic — `send_telegram_id` already retries as a standalone message
  when a reply target is gone.

---

## 8. Two implementation traps

**8.1 `_pend_long` / `_pend_short` are rebuilt EVERY bar.** `_place_entries` recomputes both from
scratch and sets them to `None` when not armed. So the alert must be **edge-triggered** on the
`None → _Pending` transition. A level-triggered alert fires every 15 minutes for as long as the setup
is live.

**8.2 The entry price can MOVE while the setup is live.** `_entry_edges` is recomputed each bar, so a
new gap or an extended fib can shift the resting price. Decision needed (§10) — the default
recommendation is not to re-alert, and to let the "Entered" message carry the real fill price.

---

## 9. Build order

1. Extract the arm-text helper in `execution.py`; add `ArmContext` and snapshot it in
   `_place_entries`. Test that it is the context the ORDER rested on, not the one at the fill (copy
   `test_the_recorded_fib_is_the_one_the_ORDER_rested_on_not_the_one_at_the_fill`).
2. Re-run `compare_strategy.py` to exit 0. It must be unmoved — this is reporting-only.
3. Add `sendPhoto`-free message builders to `alerts.py`: `format_potential`, `format_never_filled`,
   `format_blocked`, and the confluence block appended to `format_entry`. Unit-test the strings.
4. Add `algos/live/setup_alerts.py` — transition detection, thread-id bookkeeping, which categories
   are enabled.
5. Wire it into `runner._on_bar` / `_drain_records`. Keep writing the ledger; the alert is additive.
6. Config per bot: which categories to send, in the bot's own instance config (so two bots can be
   noisy and quiet independently, like `telegram_chat_id` already is).
7. Measure the real "Potential trade" rate over the historical window before turning it on live.
8. Run it in dry-run for a week and read the volume before trusting it.

---

## 10. Open questions for Aaron

1. **Blocked setups — in or out?** ~5/month. They are the most *useful* messages (is a rule earning
   its keep?) and the least *actionable* in the moment.
2. **The routine "No retrace" misses — in or out?** ~3/month, and they are the ordinary way a setup
   dies. Recommendation: out.
3. **Re-alert if the resting entry price moves?** Recommendation: no (§8.2).
4. **One thread per setup, or flat messages?** Recommendation: threads.
5. **Same Telegram group as the trade alerts, or its own?** A separate group keeps the trade record
   clean; one group keeps the story together.

---

## 11. Rejected: sending a chart IMAGE

Considered first and dropped on 2026-08-03, on a measurement rather than an argument. Recording it so
it is not re-proposed blind.

The idea was to send the chart drawn up — fibs, entry zone, stop — as a picture. Two of the three
pieces already exist: the backtest chart already renders itself to a PNG
(`ChartPanel/index.tsx::copyChartImage`, klinecharts `getConvertPictureUrl`), and Telegram's
`sendPhoto` is a small addition to `notify.py`. **The missing piece is that nothing anywhere draws a
LIVE chart** — every chart in the command center is built from a finished run directory
(`chart_spec.build_chart_spec(run_id)`).

Aaron's constraint is that it cannot depend on his laptop, which means it runs on the VPS. **Measured
on the VPS, 2026-08-03: 2 logical processors, 4 GB RAM, ~920 MB free** (NinjaTrader alone is holding
630 MB, beside two MT5 terminals, five Python processes and Defender). A headless Chromium with a
30k-candle chart loaded is 300 MB–1 GB, and the command center's backtest runner and optimizer are
built to spread across cores — on two cores, next to a live trading bot, that is a hazard, not a
feature. So the browser-screenshot route is out on that box, and drawing the chart in Python is a
few hundred lines of new drawing code plus a second thing in this repo that draws charts.

**The text version delivers the actual requirement — knowing why, before the outcome — at a fraction
of the cost, and it fits on the VPS with room to spare.** Revisit the image only if the lab ever
moves to its own hardware.

---

## 12. The standing rule for this feature

**Every number and every sentence in these messages must be the one the bot used — copied, never
re-derived.** The entry price, the stop, the targets, the fib ladder, the arm source, the swept
pool's name: all of them already exist in the running strategy. A message that recomputes any of them
is a second claim about one setup, and two claims can disagree — which is exactly how this repo has
already been bitten five times (the Run modal's costs, the Optimize modal's params, the SSH health
dot, the lab-vs-Pine parameter names, the fib the chart nearly rebuilt itself).

An alert that names a level the bot never traded is worse than no alert, because you would act on it.
