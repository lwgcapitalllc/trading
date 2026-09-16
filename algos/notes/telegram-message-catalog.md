# Telegram message catalog — every message this suite can send, by room

Every message rendered below is real: pulled from the current source and, where the body is
built from a template, filled with realistic values so the shape is exactly what a phone would
show. This file is the reference for "what could land in my phone" — the reasoning for the
shape and the four severity icons lives in `shared/alert_format.py`'s own docstring; this file
does not repeat it, only shows every example.

**Built 2026-09-14, after the health room's icons were collapsed from 14 ad hoc glyphs down to
four named severity levels and the two off-shape watchers (re-entry checks, overnight-financing
drift) were rebuilt onto the same shape as everything else.** Re-generate this file's examples
by hand whenever a message's WORDING changes — nothing here is executable, and a stale catalog
that still reads as current is worse than no catalog.

---

## The three rooms

| Room | Carries | Who sends it |
|---|---|---|
| **Trades** | The two messages you actually act on — a fill opening, a fill closing | `live/alerts.py`'s `format_entry` / `format_exit`, via the bridge only |
| **Signals** | A setup forming, before you know if it becomes a trade | `live/alerts.py`'s `format_watching` / `format_entry_zone` / `format_blocked` / `format_resolved`, via `live/setup_alerts.py` |
| **Health** | Everything about the machinery — starts, stops, halts, link outages, review findings, the two watcher tools | every other sender in the repo, through `shared/alert_format.py`'s `alert()` |

An account with its own rooms gets its trades/signals there; health falls back to the shared
room when an account names none. Full routing rules: `notes/telegram-and-notifications.md`.

## The icon vocabulary — closed, on purpose

**Health** uses exactly four icons and they mean SEVERITY, never the event:

| Icon | Name | Means |
|---|---|---|
| ⛔ | `CRITICAL` | Trading has stopped, or cannot start — act now |
| ⚠️ | `WARNING` | Nothing has stopped, but this is worth reading |
| ✅ | `OK` | A CRITICAL or WARNING state just resolved — nothing to do |
| ℹ️ | `INFO` | A neutral fact — a deliberate stop, a status reply — no concern either way |

**Signals and trades** use a separate, small set that answers a different question — WHAT this
message is about, not how severe it is — and is not part of the severity system above:

| Icon | Means |
|---|---|
| 📈 / 📉 | Long / short entry |
| ✅ / ❌ / ➖ | Win / loss / breakeven exit |
| 👀 | A setup is forming |
| 🎯 | A limit order is resting |
| 🚫 | A setup was blocked by one of your own rules |
| 👋 | A setup died with no trade |

**Every message in every room is plain text — no Markdown, ever.** A bot label, a symbol or a
traceback path is full of underscores, and Telegram's Markdown parser opens an italic on a lone
underscore and either eats the rest of the name silently (even count) or rejects the whole
message (odd count). Nothing here relies on bold, italic or color, because Telegram's Bot API
does not support text color at all, and its only other formatting options route through the
same fragile parser.

---

## Health room

### ⛔ CRITICAL — trading has stopped, or cannot start

**HALTED** — the bridge's position and the broker's disagree.
```
⛔ HALTED · SOS Fade · LIVE
Position and broker disagree on price.
Anything open keeps its broker stop. Check the account, then restart it.
```

**FLEET HALT** — the box-wide kill switch tripped.
```
⛔ FLEET HALT · SOS Fade · LIVE
risk cap exceeded across the account
It keeps running and keeps its open positions and their stops. Clear the flag and restart the bots to resume — clearing it alone will not.
```

**ACCOUNT MISMATCH** — the terminal is logged into an account this bot does not trade.
```
⛔ ACCOUNT MISMATCH · SOS Fade · LIVE
Terminal is on #700119432; this bot trades #34957946.
It placed nothing and kept its open positions and their stops. Log the terminal back, or move the bot properly in its instance config, then restart it.
```

**NO MT5 LINK** — lost its connection to the terminal. *(Reclassified up from its own icon
2026-09-14 — a blind bot is the single costliest failure in this repo's history: 50 minutes
blind with every dashboard green.)*
```
⛔ NO MT5 LINK · SOS Fade · LIVE
Lost its connection to the terminal — still running, but seeing no market at all.
Retrying every 30s. If it does not come back, check MetaTrader on the VPS.
```

**WILL NOT START** — three different reasons a bot refuses to boot, same label each time:
```
⛔ WILL NOT START · SOS Fade · LIVE
Live account 34957946 names no signal channel, so there is nowhere to report real money.
It is down and will stay down. Enter the channel on Bots → Accounts, then start it.
```
```
⛔ WILL NOT START · SOS Fade · LIVE
The code on disk is not the version this bot was promoted to run, so it refused to start.
It is down and will stay down. Promote it again, or restore the snapshot.
```
```
⛔ WILL NOT START · SOS Fade · LIVE
Startup failed: <the exception>
It is down and will stay down until someone looks at it.
```

**TRADING OFF** — the account itself can no longer trade (margin call, broker restriction).
```
⛔ TRADING OFF · SOS Fade · LIVE
Margin call on the account.
Every order it sends will be refused. If a trade triggers meanwhile it halts and needs a restart. It keeps watching and will say when trading is back.
```

**STILL HALTED** — trading came back on the account, but this bot had already halted.
```
⛔ STILL HALTED · SOS Fade · LIVE
Trading is allowed on the account again, but this bot halted while it was not (emulator and broker disagree).
Restart it to trade again.
```

**RECONNECTED — STILL HALTED** — the terminal link came back, but the bot is still halted.
```
⛔ RECONNECTED — STILL HALTED · SOS Fade · LIVE
Back on the terminal after 4 minutes. It re-warmed on the bars it missed.
It is still halted (emulator and broker disagree) and will place nothing. Check the account, then restart it.
```

**SETTINGS LOADED — STILL HALTED** — a config reload landed on an already-halted bot.
```
⛔ SETTINGS LOADED — STILL HALTED · SOS Fade · LIVE
exec_risk_pct 5.0 -> 4.0
Loaded, but this bot is halted (emulator and broker disagree) and will place nothing. Restart it.
```

**STOPPING** — the bot is shutting itself down after repeated failures (two triggers, same label):
```
⛔ STOPPING · SOS Fade · LIVE
Ten bars in a row failed to process and re-warming is not fixing it, so it is shutting itself down.
Last error: <the exception>
```
```
⛔ STOPPING · SOS Fade · LIVE
Ten passes of its main loop failed in a row, so it is shutting itself down rather than running blind.
Last error: <the exception>
```

**CLOSE FAILED** / **SCALE-IN CLOSE FAILED** — the bridge asked the broker to close and was refused.
```
⛔ CLOSE FAILED · SOS Fade · LIVE
It was asked to close the open trade and the broker refused.
The position is STILL OPEN and the bot will halt. Close it by hand.
```
```
⛔ SCALE-IN CLOSE FAILED · SOS Fade · LIVE
It was asked to close scale-in lot T5551234 and the broker refused.
That lot is STILL OPEN and the bot will halt. Close it by hand.
```

**OFFLINE** — the watchdog can no longer see the process.
```
⛔ OFFLINE · SOS Fade · LIVE
The process is gone. Restarting it now.
```

**WILL NOT START** (watchdog gave up restarting a bot, or the command bot):
```
⛔ WILL NOT START · SOS Fade · LIVE
3 restart attempts have failed. It is not trading and will not retry.
It will stay down until someone looks. Usually a version pin or the MT5 login — check its log.
```
```
⛔ WILL NOT START · Telegram bot
3 restart attempts have failed, so commands are unavailable.
RDP into the VPS and run: schtasks /run /tn SYS_TELEGRAM
```

**CANNOT SEE THE BOTS** — the bot folder list itself could not be read.
```
⛔ CANNOT SEE THE BOTS · Watchdog
The bot folders could not be read (<the error>), so no bot is being watched.
Check the box's disk and the algos folder.
```

**REVIEW** (alert level) — the hourly reviewer found something no live alert caught.
```
⛔ REVIEW · SOS Fade · LIVE
It refused to start — the code is not the promoted version
At 6:06 PM CDT: <the recorded detail>
```

**RE-ENTRY FAILED** — the re-entry watcher graded a trade and something did not check out.
```
⛔ RE-ENTRY FAILED · SOS Fade · LIVE · trade 901
Now closed.
risk sized correctly — used 10.0% of account, config caps at 5.0%
1 passed · 1 failed · 1 could not be checked
Not checked: R matches the prices
Read the failed check(s) above.
```

**RE-ENTRY WATCH DOWN** / **OVERNIGHT COST WATCH DOWN** — one of the two watcher tools crashed.
```
⛔ RE-ENTRY WATCH DOWN · SOS Fade · LIVE
The hourly check failed: RuntimeError: ledger is unreadable
Nothing is watching for a re-entry until this is fixed — silence does NOT mean nothing happened.
```
```
⛔ OVERNIGHT COST WATCH DOWN · SOS Fade · LIVE
The check failed: SystemExit: could not attach to C:\MT5_FFT: terminal not running
Until this is fixed, a change in the broker's overnight cost will pass unnoticed.
```

### ⚠️ WARNING — nothing has stopped, worth reading

**STALLED** — the process is alive but has not moved through bars.
```
⚠️ STALLED · SOS Fade · LIVE
The process is alive but has not stamped its heartbeat for 7 minutes, so it is not working through bars.
Restart it from the command center, or check its log.
```

**RE-ENTRY FEED GAP** — the re-entry's own fast clock missed bars and re-warmed.
```
⚠️ RE-ENTRY FEED GAP · SOS Fade · LIVE
Missed 3 5m bars on the re-entry's fill clock, so it re-warmed that feed. The 15-minute stream and any open trade are unaffected.
Nothing to do unless it repeats.
```

**DROPPED A BAR** — one bar failed to process; the bot is re-warming from it.
```
⚠️ DROPPED A BAR · SOS Fade · LIVE
Failed to process the 2026-09-14 09:15:00 bar, so it is re-warming the engines on the history it missed.
Reason: <the exception>
```

**SETTINGS NOT APPLIED** — a config change on disk was refused.
```
⚠️ SETTINGS NOT APPLIED · SOS Fade · LIVE
Its config changed on disk but the new values were refused, so it is still trading the ones it started with.
Refused: <the field(s) and why>
Restart it to take them.
```

**ORPHAN ORDERS** — resting orders at the broker under this bot's magic with no record here.
```
⚠️ ORPHAN ORDERS · SOS Fade · LIVE
2 resting order(s) were at the broker under this bot's magic with no record of being placed. They have been cancelled.
Nothing was opened. The usual cause is a broker request whose reply never came back. Worth reading the log for why.
```

**ORDER GONE** — an order the bridge expects to see is missing from the broker.
```
⚠️ ORDER GONE · SOS Fade · LIVE
<why it is gone — e.g. cancelled at the broker, not found on reconcile>
The strategy still expects it. Check the account's free margin.
```

**NO ACCOUNT RISK LEFT** — the shared account risk budget is fully committed.
```
⚠️ NO ACCOUNT RISK LEFT · SOS Fade · LIVE
This bot cannot open a trade: the account's 10% risk budget is fully committed.
Setups will be refused until room comes back — which happens as another bot's stop moves up or its trade closes. Nothing is wrong with this bot.
```

**ORDER REFUSED** — a setup was ready and the broker or a guard refused the order.
```
⚠️ ORDER REFUSED · SOS Fade · LIVE
A primary setup was ready and no order was placed.
Minimum stop distance not met.
No position was opened. The strategy will keep re-offering it while the setup lives, and this will not alert again for the same reason.
```

**PARTIAL NOT BANKED** — a scheduled partial close did not go through.
```
⚠️ PARTIAL NOT BANKED · SOS Fade · LIVE
<which rung, and why the broker refused it>
The position keeps its broker stop and the strategy keeps managing it. This will not alert again for the same reason.
```

**SYMBOL NOT FOUND** — a watchlist symbol is not on the broker.
```
⚠️ SYMBOL NOT FOUND · SOS Fade · LIVE
The broker does not list XAUUSD.p, so it was skipped this cycle.
Fix the watchlist in config.json.
```

**REVIEW** (warning level) — same finding mechanism, a lower-severity finding.
```
⚠️ REVIEW · SOS Fade · LIVE
<finding title>
<finding detail>
```

**OVERNIGHT COST MOVED** — the broker re-quoted its overnight financing.
```
⚠️ OVERNIGHT COST MOVED · SOS Fade · LIVE · XAUUSD.p
Per lot, per night.
Changed since the last reading — long -81.18 → -80.54 (+0.64)
Broker now: long -80.54 · short +32.67
Backtests (puprime_ecn) — long: lab holds -79.60, 1.2% away · short: lab holds +31.29, 4.2% away
Nothing changed here — re-pricing the lab is a separate, deliberate commit.
```

### ✅ OK — a CRITICAL or WARNING state just resolved

```
✅ BACK ONLINE · SOS Fade · LIVE
It is running again. Nothing to do.

✅ RESTARTED · SOS Fade · LIVE
It was offline and has been restarted automatically.
Worth checking the log for why it stopped.

✅ RECOVERED · SOS Fade · LIVE
The heartbeat resumed and it is working through bars again.
Nothing to do.

✅ RECONNECTED · SOS Fade · LIVE
Back on the terminal after 4 minutes. It re-warmed on the bars it missed.
Nothing to do.

✅ TRADING BACK ON · SOS Fade · LIVE
The account can trade again.
Nothing to do.

✅ ACCOUNT RISK AVAILABLE · SOS Fade · LIVE
$500.00 of account risk budget is free again.
This bot can take setups again. Nothing to do.

✅ TRADE RESUMED · SOS Fade · LIVE
LONG 0.25 lots @ 3300.0 · stop 3280.0
The bot restarted and picked its open trade back up. It manages it from the next bar. Nothing to do.

✅ SETTINGS APPLIED · SOS Fade · LIVE
exec_risk_pct 5.0 -> 4.0
Applied straight away — the bot was flat. Nothing to do.

✅ COMMANDS ONLINE · Telegram bot
It is listening again. Send /help for the list.

✅ REVIEW · SOS Fade · LIVE
<finding title>
<finding detail>
Nothing to do: <what healed it, e.g. "it started at 6:12 PM CDT">

✅ RE-ENTRY CHECKED · SOS Fade · LIVE · trade 902
Still open.
2 passed · 0 failed · 0 could not be checked
Nothing to do.
```

### ℹ️ INFO — a neutral fact, no concern either way

```
ℹ️ STOPPED · SOS Fade · LIVE
Shut down cleanly. It will not come back on its own.

ℹ️ CLOSE REQUESTED · SOS Fade · LIVE
Close requested (operator) — the open trade will close on the next bar.
It closes on the next bar and the bot keeps looking for setups.

ℹ️ NOTHING TO CLOSE · SOS Fade · LIVE
Close requested (operator) — nothing open to close.
It was asked to close a trade and is not in one. Nothing changed.

ℹ️ ONLINE · SOS Fade · LIVE
Trading live · XAUUSD.p M15 · $10,752.18

ℹ️ OVERNIGHT COST — FIRST READING · SOS Fade · LIVE · XAUUSD.p
Per lot, per night.
First reading on record — nothing to compare it against yet.
Broker now: long -80.54 · short +32.67
Backtests (puprime_cent) — long: lab refuses this tier — unmeasured · short: lab refuses this tier — unmeasured
Nothing changed here — re-pricing the lab is a separate, deliberate commit.
```

---

## Signals room

```
👀 SETUP FORMING · LONG
SOS Fade · XAUUSD.p · 2 of 3
Swept Day Low · 0.5-0.886 tagged, FVG live · not tagged yet
Zone 3,405.10 – 3,418.60 · stop 3,418.60

🎯 0.25 lots · BUY LIMIT RESTING
2 of 3
Limit 3,410.00 · stop 3,418.60
TP1 3,396.10 · TP2 3,389.75
Still missing: Momentum shift

🚫 BLOCKED · SHORT
news blackout · final-hour cutoff

✅ ENTERED · LONG
Size and risk are in the trade alert.

👋 NO TRADE · SHORT
Price closed back inside the range before the retrace tagged.

🧹 THREAD CLOSED · LONG
XAUUSD.p · no longer being watched
The bot restarted while this setup was open, so its outcome was not recorded. It is not a trade and not a refusal — it is an answer this bot no longer has.
```

⚠ **`🧹 THREAD CLOSED` is deliberately NOT `👋 NO TRADE`** (2026-09-16). `NO TRADE` is a
CLAIM — it says the bot looked at this setup and refused it, and it carries the strategy's own
sentence for why. This one is sent on a start, for a setup announced before the bot stopped that it
is no longer watching: the outage swallowed the bar that knew the reason, so the bot does not know
whether it filled, died or aged out. Wording it as a refusal would tell a reader a live trade was
declined. See `notes/telegram-and-notifications.md` → *A SETUP THREAD DID NOT SURVIVE A RESTART*.

## Trades room

```
📈 ENTRY · LONG XAUUSD.p
Entry 3,300.00 · Stop 3,280.00
Size 0.25 lots · Risking $500.00 (5%)
SOS Fade

✅ WIN
Made $500.00 · +2.50R
Exit 3,320.00 (target)

❌ LOSS
Lost $200.00 · -1.00R
Exit 3,280.00 (stop)

➖ BREAKEVEN
Lost $12.50 · -0.02R
Exit 3,299.50 (stop moved to entry)

❌ LOSS · XAUUSD.p
Lost $200.00 · -1.00R
Exit 3,280.00 (stop)
```
(the last one is the exit when its entry alert never sent — it names the symbol instead of
riding a reply thread, so a bare "LOSS" never floats with no trade attached)

---

## Consistency check, run 2026-09-14

- Every `alert(` call site in `algos/` outside `live/alerts.py` passes one of the four named
  severity constants — swept mechanically, zero literal icons left.
- `live/alerts.py`'s direction/outcome icons are the one deliberate exception, and are a
  different question (what, not how severe) — left untouched.
- Two senders (`notifications/monitor.py`'s watchdog alert, `notifications/telegram_bot.py`'s
  broadcast) built their own Telegram request with Markdown parsing forced on, bypassing
  `shared/notify.py` entirely. Both were sending plain `alert()`-built text through it — fixed
  to send plain, matching the "no Markdown, ever" rule everywhere else.
- `notifications/telegram_bot.py`'s command-reply path (`send_to`, e.g. `/users`) is NOT part of
  this catalog and was not touched — it answers a command a person just typed, in the same chat
  they typed it in, and deliberately uses bold/italic for that interactive reply. It is not one
  of the three broadcast rooms.
