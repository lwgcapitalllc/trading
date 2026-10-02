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
| **Signals** | A setup forming, before you know if it becomes a trade | `live/alerts.py`'s `format_watching` / `format_entry_zone` / `format_order_moved` / `format_blocked` / `format_resolved`, via `live/setup_alerts.py` |
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
| 🔁 | A re-entry is possible (its own thread), or a waiting order moved |

**A message that could not be delivered the first time** (no answer from Telegram, HTTP 429 or 5xx)
is re-sent by the every-minute monitor for up to 24 hours, with one extra last line (2026-09-26):
```
⛔ TRADING OFF · Account 34957946 · LIVE
The broker has made this account read-only, so it cannot trade.
No bot on this account can place orders. …
(delayed, first tried 3:04 PM CDT)
```
Every send, delivered or not, is also one line in the box's send log — see
`notes/telegram-and-notifications.md` → *The health room's noise*.

**Every message in every room is plain text — no Markdown, ever.** A bot label, a symbol or a
traceback path is full of underscores, and Telegram's Markdown parser opens an italic on a lone
underscore and either eats the rest of the name silently (even count) or rejects the whole
message (odd count). Nothing here relies on bold, italic or color, because Telegram's Bot API
does not support text color at all, and its only other formatting options route through the
same fragile parser.

---

## Health room

**Reworded 2026-09-30 so anyone can read it at a glance and every bot says it the same way.** Plain
words: "the bot", never the code's own names for its parts; LONG/SHORT; "stop"; "0.14 lots at
4,316.98"; real plurals; one short last line saying what to do. A setting is named by the label
the Command Center shows (`shared/param_labels.py`, which reads each strategy's meta.json), never
by its field name. An error's own text may still follow "Reason:" or "Last error:".

### ⛔ CRITICAL — trading has stopped, or cannot start

**HALTED** — the bot's record and the broker's disagree, or something it cannot manage appeared.
The middle line is the reason, and each reason is its own plain sentence (a ticket appears as
"trade #123" only where you need it to find the trade in MetaTrader).
```
⛔ HALTED · SOS Fade · LIVE
The bot thinks it has a trade open, but the broker has none. Its order filled in the bot's record and not at the broker, or the trade was closed outside the bot.
Any open trade keeps its stop. Check the account, then restart the bot.
```

**FLEET HALT** — the box-wide stop switch is on, or cannot be read.
```
⛔ FLEET HALT · SOS Fade · LIVE
Spread blew out.
Open trades keep their stops. To resume, switch the fleet stop off and restart the bots.
```

**ACCOUNT MISMATCH** — MetaTrader is logged into an account this bot does not trade.
```
⛔ ACCOUNT MISMATCH · SOS Fade · LIVE
MetaTrader is logged into account 700119432, but this bot trades 34957946.
Nothing was placed and open trades keep their stops. Log MetaTrader back in, or move the bot on the Command Center's Accounts page, then restart it.
```

**NO MT5 LINK** — lost its connection to MetaTrader. *(Critical since 2026-09-14 — a blind bot is
the single costliest failure in this repo's history.)*
```
⛔ NO MT5 LINK · SOS Fade · LIVE
Lost its connection to MetaTrader. It is still running but cannot see the market.
Retrying every 30 seconds. If it doesn't come back, check MetaTrader on the server.
```

**WILL NOT START** — the reasons a bot refuses to boot, same label each time:
```
⛔ WILL NOT START · SOS Fade · LIVE
Live account 34957946 has no trades channel set, so the bot has nowhere to report real-money trades.
Set the channel on the Command Center's Accounts page, then start it.
```
```
⛔ WILL NOT START · SOS Fade · LIVE
It has never been deployed, so it has no approved code version of its own.
Deploy it from the Command Center's Configure tab, then start it.
```
```
⛔ WILL NOT START · SOS Fade · LIVE
The code on the server is not the approved code version for this bot, so it refused to start.
Deploy it again from the Command Center.
```
```
⛔ WILL NOT START · SOS Fade · LIVE
It failed while starting up and is not trading.
Reason: <the error>
Check its log, then start it again.
```

**TRADING OFF** — the ACCOUNT can no longer trade (MetaTrader lost the broker, the broker made it
read-only, automated trading not allowed, the Algo Trading button off, or the symbol set to close
only). The subject is the account, not a bot. **Held 15 minutes and sent once per account**
(2026-09-26): if trading comes back inside that, neither this nor its BACK ON is sent. The hold
adds the last line.
```
⛔ TRADING OFF · Account 34957946 · LIVE
MetaTrader has lost its connection to the broker.
No bot on this account can place orders. You'll get a message when it's back.
Still happening 15 minutes later (first seen 9:55 PM CDT).
```

**NOT BACK ONLINE** — a Command Center deploy, start or restart, three minutes on, and the bot has
not come back (the watchdog, 2026-09-26). Never held.
```
⛔ NOT BACK ONLINE · SOS Fade · LIVE
The Command Center deployed and restarted it at 2:02 PM CDT and it is still not back after 3 minutes. It is not trading.
Check its log. The usual causes are the approved code version, the MetaTrader login or a startup error.
```

**STILL HALTED** — trading came back on the account, but this bot had already halted.
```
⛔ STILL HALTED · SOS Fade · LIVE
The account can trade again, but this bot stopped trading while it couldn't (the bot thinks it has a trade open, but the broker has none. …).
Restart it to trade again.
```

**RECONNECTED — STILL HALTED** — the MetaTrader link came back, but the bot is still halted.
```
⛔ RECONNECTED — STILL HALTED · SOS Fade · LIVE
Back on MetaTrader after 4 minutes. It caught up on the bars it missed.
It is still halted (<the halt reason>) and places nothing. Check the account, then restart it.
```

**SETTINGS LOADED — STILL HALTED** — a settings change landed on an already-halted bot.
```
⛔ SETTINGS LOADED — STILL HALTED · SOS Fade · LIVE
Risk % per trade 5 → 4
Loaded, but this bot is halted (<the halt reason>) and places nothing. Restart it.
```

**STOPPING** — the bot is shutting itself down after repeated failures (two triggers, same label):
```
⛔ STOPPING · SOS Fade · LIVE
Ten bars in a row failed and reloading didn't fix it, so it is shutting itself down.
Last error: <the error>
Check its log, then start it again.
```
```
⛔ STOPPING · SOS Fade · LIVE
Ten checks in a row failed, so it is shutting itself down rather than trade blind.
Last error: <the error>
Check its log, then start it again.
```

**CLOSE FAILED** / **SCALE-IN CLOSE FAILED** — the bot asked the broker to close and was refused.
```
⛔ CLOSE FAILED · SOS Fade · LIVE
The bot tried to close its open trade and the broker refused.
The trade is STILL OPEN and the bot will stop trading. Close it by hand.
```
```
⛔ SCALE-IN CLOSE FAILED · SOS Fade · LIVE
The bot tried to close scale-in trade #5551234 and the broker refused.
It is STILL OPEN and the bot will stop trading. Close it by hand.
```

**OFFLINE** — the watchdog can no longer see the process.
```
⛔ OFFLINE · SOS Fade · LIVE
The bot has stopped running. Restarting it now.
```

**WILL NOT START** (the watchdog gave up restarting a bot, or the Telegram bot):
```
⛔ WILL NOT START · SOS Fade · LIVE
3 restart attempts failed, so it is not trading and has stopped retrying.
Check its log. The usual causes are the approved code version or the MetaTrader login.
```
```
⛔ WILL NOT START · Telegram bot
3 restart attempts failed, so commands are unavailable.
Log into the trading server and start the Telegram bot task.
```

**CANNOT SEE THE BOTS** — the bot folder list itself could not be read.
```
⛔ CANNOT SEE THE BOTS · Watchdog
The bots' folders couldn't be read, so no bot is being watched. Reason: <the error>
Check the trading server's disk.
```

**STUDENT FEED DOWN** — the REV SETUP student feed cannot run (health room only; the students'
channel never hears about machinery).
```
⛔ STUDENT FEED DOWN · REV SETUP
The student setup feed cannot run, so students get no setups until it's fixed.
Reason: <the error>
Check its log on the trading server.
```

**REVIEW** (alert level) — the hourly reviewer found something no live alert caught. ⚠ Since
2026-09-26 it is NOT sent when the send log shows the real-time alert for the same event already
reached the room (or was held on purpose) — it still shows on the Bots page.
```
⛔ REVIEW · SOS Fade · LIVE
It refused to start — the code is not the approved version
At 6:06 PM CDT: <the recorded detail>
```
A live halt is ONE finding:
```
⛔ REVIEW · SOS Fade · LIVE
Halted right now — the bot is placing nothing
It stopped placing orders at 3:00 AM CDT: <the halt reason>
It still says halted at 3:55 AM CDT, though the Bots page shows it running. Check the account, then restart it.
```

**REMINDER — HALTED / REMINDER — DOWN** — a bot on a LIVE account, once an hour until it clears
(2026-09-26). Demo accounts get none. Never held.
```
⛔ REMINDER — HALTED · SOS Fade · LIVE
Halted for 2 hours: <the halt reason>. It is placing nothing.
Check the account, then restart it. Repeats hourly until fixed.
```
```
⛔ REMINDER — DOWN · SOS Fade · LIVE
Down for 1 hour, and nobody stopped it. It is not trading.
Start it from the Command Center, or check its log. Repeats hourly until fixed.
```

**RE-ENTRY FAILED** — the re-entry watcher graded a trade and something did not check out.
```
⛔ RE-ENTRY FAILED · SOS Fade · LIVE · trade 901
Now closed.
risk sized correctly — used 10.0% of account, config caps at 5.0%
1 passed · 1 failed · 1 could not be checked
Not checked: R matches the prices
Read the failed check above.
```

**RE-ENTRY WATCH DOWN** / **OVERNIGHT COST WATCH DOWN** — one of the two watcher tools crashed.
```
⛔ RE-ENTRY WATCH DOWN · SOS Fade · LIVE
The hourly re-entry check failed, so nothing is checking re-entry trades.
Reason: RuntimeError: ledger is unreadable
Until it's fixed, silence doesn't mean nothing happened. Check its log.
```
```
⛔ OVERNIGHT COST WATCH DOWN · SOS Fade · LIVE
The overnight cost check failed.
Reason: SystemExit: could not attach to C:\MT5_FFT: terminal not running
Until it's fixed, a change in the broker's overnight cost goes unnoticed.
```

### ⚠️ WARNING — nothing has stopped, worth reading

**RE-ENTRY WARNINGS OFF** — the part of the strategy that reports a possible re-entry raised an
error and stopped (2026-10-02). Once per process. Trading is unaffected; only the signals room's
re-entry threads stop until a restart.
```
⚠️ RE-ENTRY WARNINGS OFF · SOS Fade · LIVE
The signals room will not warn before a re-entry until this bot restarts. Trading is unaffected.
Reason: RuntimeError: bad snapshot
```

**ORDER REJECTED** — the BROKER refused an order we sent (2026-09-16). Once per cause per side. The
reason is the broker's code in plain words (`shared/broker_result.plain_reason`), or the broker's
own comment when the code is not in the table — never the bare number. A temporary cause (no
connection, requote, prices changed, no prices, too many requests, busy) is re-sent on the poll
loop; anything else is not.
```
⚠️ ORDER REJECTED · SOS Fade · LIVE
The broker refused a 0.14-lot SHORT order at 4,316.98 (stop 4,352.44).
Reason: No connection to the broker.
Retrying in 10 seconds, up to 5 times. You'll get one more message either way.
```
The last line otherwise reads — permanent cause: *Not retried, because the same order would be
refused again. The bot offers it again at the next bar if the setup is still valid.* Five failed
retries: *Gave up after 5 tries. No order is waiting. The bot offers it again at the next bar if the
setup is still valid.* A market order: *Not retried: the bot already counts this trade as open, so
it will stop trading at the next check. Look at the account.*

**NO SETUP MESSAGES** — a bot whose strategy cannot report setups (2026-09-16). Sent **once per bot
per strategy version**.
```
⚠️ NO SETUP MESSAGES · Realign · demo
This strategy (v12) can't report its setups yet, so the signals room stays silent for this bot.
Trade and health messages still arrive. Said once per version.
```

**STALLED** — the process is alive but has not checked in.
```
⚠️ STALLED · SOS Fade · LIVE
It is running but hasn't checked in for 7 minutes, so it is not reading the market.
Restart it from the Command Center, or check its log.
```

**RE-ENTRY FEED GAP** — the faster feed the re-entry uses missed bars and was reloaded.
```
⚠️ RE-ENTRY FEED GAP · SOS Fade · LIVE
Missed 3 bars on the M5 feed the re-entry uses, so it reloaded that feed. The main chart and any open trade are fine.
Nothing to do unless it repeats.
```

**DROPPED A BAR** — one bar failed to process; the bot is reloading recent history.
```
⚠️ DROPPED A BAR · SOS Fade · LIVE
Couldn't process the 9:15 AM CDT bar, so it is reloading recent history to catch up.
Reason: <the error>
Nothing to do unless it repeats.
```

**SETTINGS NOT APPLIED** — a settings change that a running bot cannot take.
```
⚠️ SETTINGS NOT APPLIED · SOS Fade · LIVE
Still trading its old settings. 25 changes need a restart: Trade longs, Trade shorts, Trade SOS Fade setups and 22 more.
Restart it when flat to apply them.
```

**ORPHAN ORDERS** — orders at the broker belonging to this bot that it never placed.
```
⚠️ ORPHAN ORDERS · SOS Fade · LIVE
2 orders were at the broker that this bot never placed. They were cancelled. Nothing was opened.
Worth reading the log for why.
```

**ORDER GONE** — an order the bot expects is missing from the broker.
```
⚠️ ORDER GONE · SOS Fade · LIVE
The SHORT order (0.14 lots at 4,316.98) disappeared from the broker without filling. The usual cause is not enough free margin.
The bot still expects it. Check the account's free margin.
```

**NO ACCOUNT RISK LEFT** — the account's risk limit is fully used.
```
⚠️ NO ACCOUNT RISK LEFT · SOS Fade · LIVE
This bot can't open a trade: the account already has $1,075.22 at risk, against a limit of $1,075.22 (10% of $10,752.18).
Setups are skipped until room frees up. Nothing is wrong with this bot.
```

**SETUP REFUSED — NO ROOM** / **TRADE SHRUNK** / **ORDER SHRUNK** — see the shared-account section
below.

**ORDER REFUSED** — a setup was ready and a guard refused the order before it reached the broker.
```
⚠️ ORDER REFUSED · SOS Fade · LIVE
A LONG setup was ready but no order was placed.
The trade needs 0.004000 lots, under XAUUSD.p's minimum of 0.01. Not rounding up, because the minimum would risk 25.00 instead of 10.00. The account is too small for this setup's stop distance.
The bot offers it again while the setup is valid.
```

**PARTIAL NOT BANKED** — a planned partial close did not go through.
```
⚠️ PARTIAL NOT BANKED · SOS Fade · LIVE
Couldn't take profit on 0.07 lots: the broker doesn't allow that size. The trade is still 0.14 lots where the bot expects 0.07, so this trade's result will differ from the backtest.
The trade keeps its stop and the bot keeps managing it.
```

**SYMBOL NOT FOUND** — a watchlist symbol is not on the broker.
```
⚠️ SYMBOL NOT FOUND · SOS Fade · LIVE
The broker doesn't list XAUUSD.p, so it was skipped this time.
Fix the symbol in the bot's settings.
```

**REVIEW** (warning level) — same finding mechanism, a lower-severity finding.
```
⚠️ REVIEW · SOS Fade · LIVE
<finding title>
<finding detail>
```

**BACKUP FAILING** — the bots' records did not reach GitHub (the hourly ledger sync). Repeats at
most daily for the same reason, with how long it has lasted on the first line.
```
⚠️ BACKUP FAILING · Trade records
Still failing after 25 hours, for the same reason.
The bots' records saved on the server but did not reach GitHub, so there is only one copy.
Reason: <why>
```

**OVERNIGHT COST MOVED** — the broker re-quoted its overnight financing.
```
⚠️ OVERNIGHT COST MOVED · SOS Fade · LIVE · XAUUSD.p
Per lot, per night.
Changed since the last reading: long -81.18 → -80.54 (+0.64)
Broker now: long -80.54 · short +32.67
Backtests use long -79.60 (1.2% off) · short +31.29 (4.2% off)
Nothing to do unless the gap grows.
```

**GONE LIVE** — the Command Center moved bots from a demo account to a live one.
```
⚠️ GONE LIVE · SOS Fade, Extreme Leg
Moved from demo 700152905 to LIVE 34957946 (PU Prime, account risk limit 10%).
Not trading yet. Every bot is stopped until you start it.
```

### One message per Command Center action (2026-09-26)

The Command Center sends one ℹ️ message BEFORE it touches the bot, and the bot EDITS it into the
outcome once it is online — no STOPPED, no separate ONLINE. If it does not come back in three
minutes the watchdog sends NOT BACK ONLINE (above).
```
ℹ️ PROMOTED · SOS Fade · LIVE          →   ✅ DEPLOYED · SOS Fade · LIVE
v397 → v399 · deployed                     v397 → v399, back online
Restarting it now.                         Trading live · XAUUSD.p M15 · $10,752.18
                                           v399 · account 34957946

ℹ️ STARTING · SOS Fade · LIVE          →   ✅ ONLINE · SOS Fade · LIVE
Requested from the Command Center.         Started from the Command Center.
This message will say when it is online.   Trading live · XAUUSD.p M15 · $10,752.18 …

ℹ️ RESTARTING · SOS Fade · LIVE        →   ✅ RESTARTED · SOS Fade · LIVE
Requested from the Command Center.         Restarted from the Command Center and back online. …
```
A Command Center STOP is one ℹ️ STOPPED — the bot's own when it shut down cleanly, the Command
Center's when it had to be terminated. **The Command Center uses only the four severity icons
(2026-09-30)** — its own ⚙️ ▶️ ⏹ 🔄 📦 🔴 are gone:

| Command Center message | Icon |
|---|---|
| SETTINGS CHANGED, RISK CHANGED, PRIORITY CHANGED, ACCOUNT RISK CAP, BOT MOVED | ℹ️ |
| STARTING, RESTARTING, RESTARTING ONTO DEPLOYED CODE, STOPPED, PROMOTED, NOTHING TO DEPLOY | ℹ️ |
| DEPLOYED (the bot's edit of PROMOTED) | ✅ |
| GONE LIVE | ⚠️ |

```
ℹ️ SETTINGS CHANGED · SOS Fade · LIVE
Risk % per trade 5 → 4
It applies the next time the bot has no open trade.
```

### What is HELD rather than sent (2026-09-26)

Nothing below is lost: each is one `held` line in the box's send log, and the daily summary counts
it. The rules and the reasoning are in `notes/telegram-and-notifications.md` → *Stage 2*.

- A repeat of the same fault about the same bot (the 17 Sep startup loop: 17 WILL NOT START → 1).
- OFFLINE / STALLED / NO MT5 LINK that recover inside 5 minutes, with their RESTARTED / BACK ONLINE /
  RECOVERED / RECONNECTED, and the bot's own ONLINE after such a restart.
- TRADING OFF that comes back inside 15 minutes, with its BACK ON; the other bots' copies of an
  account's OFF; any BACK ON whose OFF was never sent.
- The chat bot's own RESTARTED and COMMANDS ONLINE.
- A bot's STOPPED during a Command Center deploy or restart.
- NO SETUP MESSAGES after the first for a version; TRADE SHRUNK at 100% (not sent at all).

**Never held:** HALTED and anything with HALT in it, FLEET HALT, ACCOUNT MISMATCH, CLOSE FAILED,
ORDER REFUSED / REJECTED, NOT BACK ONLINE, CANNOT SEE THE BOTS, every REMINDER.

### ✅ OK — a CRITICAL or WARNING state just resolved

```
✅ ORDER PLACED AFTER REJECTION · SOS Fade · LIVE
The SHORT order is now at the broker: 0.14 lots at 4,316.98 (after 1 retry).

✅ BACK ONLINE · SOS Fade · LIVE
It is running again. Nothing to do.

✅ RESTARTED · SOS Fade · LIVE
It had stopped running and was restarted automatically.
Worth checking the log for why it stopped.

✅ RECOVERED · SOS Fade · LIVE
It is checking in and reading the market again.
Nothing to do.

✅ RECONNECTED · SOS Fade · LIVE
Back on MetaTrader after 4 minutes. It caught up on the bars it missed.
Nothing to do.

✅ TRADING BACK ON · Account 34957946 · LIVE
The account can trade again.
Nothing to do.

✅ ACCOUNT RISK AVAILABLE · SOS Fade · LIVE
$500 of the account's risk limit is free again.
This bot can take setups again. Nothing to do.

✅ ORDER BACK TO FULL SIZE · FFT · demo
Room freed up, so the LONG order is back to full size (0.3 → 0.45 lots). Not filled yet.

✅ TRADE RESUMED · SOS Fade · LIVE
LONG 0.25 lots at 3,300.00 · stop 3,280.00
The bot restarted and picked its open trade back up. Nothing to do.

✅ TRADE ADOPTED · SOS Fade · LIVE
LONG 0.25 lots at 3,300.00 · stop 3,280.00
The bot restarted without a saved record, found the same trade at the broker and picked it back up. Nothing to do.

✅ SETTINGS APPLIED · SOS Fade · LIVE
Risk % per trade 5 → 4
Applied straight away because the bot was flat. Nothing to do.

✅ BACKUP WORKING · Trade records
The bots' records are reaching GitHub again. Nothing to do.

✅ COMMANDS ONLINE · Telegram bot
It is listening again. Send /help for the list.

✅ REVIEW · SOS Fade · LIVE
<finding title>
<finding detail>
Nothing to do: <what healed it, e.g. "It started at 6:12 PM CDT.">

✅ RE-ENTRY CHECKED · SOS Fade · LIVE · trade 902
Still open.
2 passed · 0 failed · 0 could not be checked
Nothing to do.
```

### ℹ️ INFO — a neutral fact, no concern either way

```
ℹ️ STOPPED · SOS Fade · LIVE
Shut down cleanly. It won't come back on its own.

ℹ️ CLOSE REQUESTED · SOS Fade · LIVE
Asked to close its trade (operator). It closes on the next bar.
The bot keeps looking for setups. Nothing to do.

ℹ️ NOTHING TO CLOSE · SOS Fade · LIVE
Asked to close its trade (operator), but it has none open.
Nothing changed.

ℹ️ DAILY SUMMARY · Health room
The 24 hours to 8:00 AM CDT, Sep 26.
Held back 21: WILL NOT START 16 (SOS Fade · LIVE 16); OFFLINE 5 (SOS Fade · LIVE 3, Extreme Leg · LIVE 2).
Longest time trading was off: 7 minutes (account 34957946).
Auto-restarts: 2 (SOS Fade · LIVE 2).
Delivered late: 1 · Given up after 24 hours: 0.

ℹ️ OVERNIGHT COST — FIRST READING · SOS Fade · LIVE · XAUUSD.p
Per lot, per night.
First reading on record, so nothing to compare it with yet.
Broker now: long -80.54 · short +32.67
Backtests have no figure for this account type.
Nothing to do unless the gap grows.

ℹ️ TEST MESSAGE · trade channel
This channel was entered as the trade channel for account 34957946 (chat -1009999999999).
Nothing is trading because of this message. If you didn't expect it, tell whoever set the account up.
```

The bot's own start banner, when no Command Center action is waiting to be edited, is
`✅ ONLINE · SOS Fade · LIVE` / `Trading live · XAUUSD.p M15 · $10,752.18` / `v399 · account 34957946`.

---

## Signals room

Rendered by the real formatters, 2026-09-30 — the house rules are in `notes/telegram-and-notifications.md` → *One voice for every bot*.

```
👀 SETUP FORMING · LONG
SOS Fade · XAUUSD.p · 2 of 3 checks
✓ Took out the daily low · ✓ Trend turned · ✗ Pullback to entry zone
Entry zone 3,405.10 – 3,418.60 · Stop 3,404.60

👀 SETUP FORMING · LONG
Realign · XAUUSD.p · 1 of 3 checks
✓ Uptrend dipped on the 15-min · ✗ 5-min dip · ✗ 5-min turn back up
Target 3,331.20

🎯 LIMIT ORDER WAITING · LONG
SOS Fade · XAUUSD.p · 0.25 lots
Buy at 3,410.00 · Stop 3,404.60
Targets 3,425.10 · 3,431.75
Not filled yet. Still missing: pullback to entry zone.

🔁 LIMIT ORDER MOVED · LONG
SOS Fade · XAUUSD.p · 0.25 → 0.22 lots
Buy at 3,410.00 → 3,407.20 · Stop 3,404.60 → 3,403.90
Not filled yet. Still missing: pullback to entry zone.

⏸ LIMIT ORDER PAUSED · SHORT
SOS Fade · XAUUSD.p
Too close to the daily close (4–6 pm New York).
The order comes back if this changes while the setup is still valid.

🚫 BLOCKED · LONG
Extreme Leg · XAUUSD.p
Price already passed the target before the entry signal.
Still watching in case this changes.

🚫 BLOCKED · SHORT
SOS Fade · XAUUSD.p
Big news release due. Too close to the daily close (4–6 pm New York).
Still watching in case this changes.

✅ ENTERED · LONG
SOS Fade · XAUUSD.p
Filled. Details in the trades room.

👋 NO TRADE · SHORT
SOS Fade · XAUUSD.p
Price never pulled back to the entry zone.

👋 NO TRADE · LONG
Extreme Leg · XAUUSD.p
Ran out of time after 180 minutes. Last block: price already passed the target before the entry signal.

🧹 NO LONGER TRACKED · LONG
SOS Fade · XAUUSD.p
The bot restarted while this setup was open, so how it ended is unknown.
```

### Re-entry threads (2026-10-02)

A setup's own thread closes when its first trade fills, so a re-entry gets a NEW thread — it never
replies to the first one. Sent after every 1-minute bar as well as every 15-minute bar, because a
re-entry arms and fills between two 15-minute bars. Written by hand from real replay output; the
time line is the box's clock (`alert_format.when`).

```
🔁 RE-ENTRY POSSIBLE · LONG
SOS Fade · XAUUSD.p
From the setup of Sep 30, 10:00 PM CDT.
✓ First trade reached its first target, then closed · ✓ A close in the re-entry zone · ✓ A gap to rest the order on
Buy at 4,159.79 · Stop 4,145.40

🔁 RE-ENTRY POSSIBLE · SHORT
SOS Fade · XAUUSD.p
From the setup of Sep 16, 1:00 PM CDT.
✓ First trade reached its first target, then closed · ✗ A close in the re-entry zone · ✓ A gap to rest the order on
Re-entry zone 4,316.98 – 4,352.44 · Stop 4,352.44
Exact price not known yet.

🔁 RE-ENTRY POSSIBLE · SHORT
SOS Fade · XAUUSD.p
From the setup of Aug 6, 8:00 AM CDT.
✓ First trade was stopped at its original stop · ✗ Price back below the entry level · ✗ A retest of the entry level
Sell at 4,294.92 · Stop 4,304.12

🎯 RE-ENTRY ORDER WAITING · LONG
SOS Fade · XAUUSD.p · 0.12 lots
Buy at 4,159.79 · Stop 4,145.40
Not filled yet.

🔁 RE-ENTRY ORDER MOVED · SHORT
SOS Fade · XAUUSD.p · 0.12 → 0.10 lots
Sell at 4,294.92 · Stop 4,304.12
Not filled yet. Still missing: a retest of the entry level.

✅ RE-ENTERED · LONG
SOS Fade · XAUUSD.p
Filled. Details in the trades room.

👋 NO RE-ENTRY · SHORT
SOS Fade · XAUUSD.p
Price reached the stop level before it came back.

👋 NO RE-ENTRY · LONG
SOS Fade · XAUUSD.p
A new break of structure ended the setup.
```

⚠ **The other NO RE-ENTRY reasons**, each the strategy's own sentence: *Structure broke the other
way, which ends the setup.* · *Price reached the setup's final target, which ends it.* · *Price
closed past where the move started, which cancels the setup.* · *The setup expired.* · *This
setup's one re-entry was already used.* · *A re-entry on this setup was already stopped out.* ·
*The re-entry order waited too long and was cancelled.* · *The setup no longer allows a re-entry.*

⚠ **The gap re-entry does NOT wait for a fresh pullback** — once the setup has had a 15-minute close
in the zone with a gap, it rests at the live gap edge the moment the first trade closes. That is why
its warning usually carries a price, and why the lead can be a minute or two (2026-10-01: first
trade closed 08:15 UTC, re-entry filled 08:17).

⚠ **`🔁` is shared with LIMIT ORDER MOVED**, which is also a change to a waiting order. The label
tells them apart.

⚠ **`🧹 NO LONGER TRACKED` is deliberately NOT `👋 NO TRADE`** (2026-09-16). `NO TRADE` is a
CLAIM — it says the bot looked at this setup and refused it, and it carries the strategy's own
sentence for why. This one is sent on a start, for a setup announced before the bot stopped that it
is no longer watching: the outage swallowed the bar that knew the reason, so the bot does not know
whether it filled, died or aged out. Wording it as a refusal would tell a reader a live trade was
declined. See `notes/telegram-and-notifications.md` → *A SETUP THREAD DID NOT SURVIVE A RESTART*.

## Trades room

Rendered by the real formatters, 2026-09-30. Every message after the entry REPLIES to it, and every one carries the bot · symbol line.

```
📈 ENTERED · LONG
SOS Fade · XAUUSD.p · 0.25 lots
Entry 3,300.00 · Stop 3,280.00
Risking $500.00 (5% of the account)

✅ WIN
SOS Fade · XAUUSD.p
Made $500.00 · +2.50R
Closed at 3,320.00 (hit target)

❌ LOSS
SOS Fade · XAUUSD.p
Lost $200.00 · -1.00R
Closed at 3,280.00 (hit stop)

➖ BREAKEVEN
SOS Fade · XAUUSD.p
Lost $12.50 · -0.02R
Closed at 3,299.50 (stopped at entry)

🛡 STOP MOVED TO ENTRY
SOS Fade · XAUUSD.p
Stop 3,280.00 → 3,290.00
This trade can no longer lose, unless price jumps past the stop.

🪜 PROFIT LOCKED IN
SOS Fade · XAUUSD.p
Stop 3,290.00 → 3,301.50 · locks in +1.15R

🔒 RISK REDUCED
SOS Fade · XAUUSD.p
Stop 3,280.00 → 3,290.00 · now risking 0.50R

💰 PROFIT TAKEN
SOS Fade · XAUUSD.p
Closed 0.17 of 0.42 lots · 0.25 still open
Taken at market price, so it can differ slightly from the target.

➕ ADDED TO TRADE
SOS Fade · XAUUSD.p
Added 0.20 lots at about 3,305.00
0.62 lots open now · all on one stop at 3,296.00

✋ CLOSED BY YOU · +0.70R
SOS Fade · XAUUSD.p
Made $348.60
Closed at 4,291.98
The bot keeps trading.

✋ STOP MOVED BY YOU
SOS Fade · XAUUSD.p
Stop now 4,301.37. The bot keeps it.
```

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

## SETUP REFUSED — NO ROOM, and TRADE SHRUNK — SHARED ACCOUNT (2026-09-15)

**Aaron asked for these in the original shared-account requirements** — *"Telegram would tell us
hey, this bot trade got rejected because of XYZ"* — and until now they did not exist.

**What was silent.** A bot sharing an account sizes every entry against the room left under the
account cap. The account answers with a number, and that is the whole conversation: a shrink comes
back as a smaller quantity, a refusal as `0.0` and no order at all. Nothing downstream could tell
the difference between *refused for lack of room* and *no setup today* — not the text log, not the
ledger, not the Bots page, not Telegram. `ORDER REFUSED` never fires for these, because no order
ever reaches the broker to be refused.

**Where they come from.** `backtest/portfolio/account.py` is the only object that knows both the
size asked for and the size granted, so it carries an optional observer (`on_contention`) that the
live bridge installs and nothing else ever sets. `OrderBridge._on_contention` writes the ledger
record and sends the message. The observer is a TAP on the same row the contention log holds, never
a second record, and an observer that throws is swallowed — sizing must not share a failure with
telling somebody about it.

**What they say.**

- *SETUP REFUSED — NO ROOM* — the setup was ready and no order was placed. Names the side, the
  risk dollars it wanted, and WHICH of the three rules refused it: under half its own size, under
  the account's entry floor, or essentially nothing free. The reason is the "XYZ" half of the ask;
  "refused" alone is what Aaron already had.
- *TRADE SHRUNK — SHARED ACCOUNT* (market-entry bot) / *ORDER SHRUNK — SHARED ACCOUNT*
  (resting-order bot) — the entry went on at a reduced size, with the risk it wanted, the room that
  was free and the percentage of its size it took. The ask is also stated as a percentage of the
  balance, and when that differs from the bot's usual share the message says so (FFT sizes sweep
  setups at 1.5x, so a "5% bot" asks 7.5%). No percentage is printed when the balance cannot be
  read. 🔴 **Rewritten 2026-09-30:** it said "the trade is on" for every bot, and on FFT
  (2026-09-29) it was a limit order that never filled, was put back to full size an hour later
  without a word, and was then cancelled. Resting bots shrink at placement too — the old line here
  saying only a market bot could be shrunk was wrong.

```
⚠️ ORDER SHRUNK — SHARED ACCOUNT · FFT · demo
Other bots were using most of the account's risk limit, so this LONG order went in at 67% size ($748 of the $1,115 risk it wanted, 7.5% of the balance, above its usual 5%).
Not filled yet. If room frees up first, it goes back to full size.
```
```
⚠️ SETUP REFUSED — NO ROOM · SOS Fade · LIVE
A LONG setup was ready, but the account's risk limit had only $100 free of the $500 it needed, under half, which is too small to take (other bots are using it).
No order placed. Nothing is wrong with this bot.
```

- *ORDER BACK TO FULL SIZE* (2026-09-30) — a resting order that was announced as shrunk has been
  re-placed at its full size. Sent once, only for a side that was told it shrank, and only when
  nothing cut the sizing on that bar — a bigger but still-trimmed order is not full size, and a
  re-size from a balance change on an order never shrunk says nothing.

```
✅ ORDER BACK TO FULL SIZE · FFT · demo
Room freed up, so the LONG order is back to full size (0.3 → 0.45 lots). Not filled yet.
```

**How often they speak.** One message per side per EPISODE. A setup that cannot be afforded is
re-offered on every bar it lives, so a message per occurrence mutes the channel before the day it
matters — the same reasoning as `ORDER REFUSED`. A side that goes a whole bar without being cut
ends its episode, and the next cut on that side speaks again.

⚠ **Apart from ORDER BACK TO FULL SIZE, there is no "room is back" message here, deliberately.** `NO ACCOUNT RISK LEFT` /
`ACCOUNT RISK AVAILABLE` already cover the account running dry and recovering. These two are about
one specific setup, and the follow-up is visible either way: the trade appears, or the next
episode speaks.

**Ledger:** `budget_cut`, `budget_shrunk` and (2026-09-30) `budget_restored`, all in the DECISION stream — they answer "why was
there no trade, or why was that trade small", and nothing is wrong with the machinery.
⚠ Both names are written as literals in two separate calls. `test_ledger_streams` greps this
folder for the names it must route, and a name built inline is a name the guard cannot see — it
caught exactly that here.

### Trades room — a hand close of the bot's own trade (2026-09-17)

⚠ **The wording below is as it shipped on that date and was rewritten 2026-09-30** — the current text is in *Trades room* above.


Replied under the trade's ENTRY message:

```
✋ CLOSED BY YOU · +0.7R
Made $348.60
Exit 4291.98
The bot has flattened its own record and keeps trading.
```

### Trades room — a stop the owner tightened (2026-09-17)

⚠ **The wording below is as it shipped on that date and was rewritten 2026-09-30** — the current text is in *Trades room* above.


Replied under the trade's ENTRY message, once per level:

```
✋ STOP MOVED BY YOU · 4301.37
```

### Trades room — how a trade is MANAGED, between the fill and the outcome (2026-09-22)

⚠ **The wording below is as it shipped on that date and was rewritten 2026-09-30** — the current text is in *Trades room* above.


Aaron: *"if a trade moves to break even I should get an alert saying move to break even... it
should alert me all the way of how the trade is being managed... I need that to be consistently
applied as a rule of thumb to any bots I create."* Until this date the thread said ENTRY and then,
hours later, WIN or LOSS, and everything in between happened in silence.

**Every one of these REPLIES to the trade's ENTRY message**, not to the one before it — one root
per trade, so a reader tapping any of them lands on the fill that started it.

**Every bot sends them, including one nobody has written yet**, because they are classified from
the entry price and the two stops — facts `live/bridge.py` holds for any strategy — and never from
a strategy's own stage numbering. Formatters: `live/alerts.py`.

```
🛡 STOP AT BREAKEVEN
Stop 3,280.00 → 3,290.00 (entry)
Out of risk on this trade now, unless price gaps through the stop.

🛡 STOP AT BREAKEVEN
Stop 3,280.00 → 3,294.00 · locking +0.40R
Out of risk on this trade now, unless price gaps through the stop.

🪜 STOP TRAILED
Stop 3,290.00 → 3,301.50 · locking +1.15R

🔒 STOP TIGHTENED
Stop 3,300.00 → 3,296.00 · risk now 0.50R

💰 PART BANKED
Took 0.17 of 0.42 lots off · 0.25 still running
Banked at market on the bar's close, not at the rung's own price.

➕ ADDED TO POSITION
Added 0.20 lots at about 3,305.00
0.62 lots now open · every lot on the same stop 3,296.00
```

The second breakeven example is the one worth reading twice: a buffered breakeven lands PAST the
entry, and it is still reported as the breakeven crossing rather than as a trail, because the
crossing is the event — the moment the trade stopped being able to lose — and it is the one Aaron
named. Every later move in profit is a trail.

⚠ **`locking … R` above the entry, `risk now … R` below it.** The same signed number read two
ways, because "locking -0.50R" is a sentence the reader has to translate.

⚠ **A trade whose opening stop was never recorded prints NO R at all** — not `0.00R`. The
yardstick is the distance from the entry to the stop the trade OPENED with, and the stop on a
record written before 2026-09-22 has already moved. Rule 1.

⚠ **Three new icons in this room** — 🛡 breakeven, 🪜 trail, 🔒 tighten — plus 💰 for size banked
and ➕ for size added. They answer WHAT the message is about, which is this room's question; the
health room's four severity icons are a separate, closed set and are not touched.


---

## Sizes shown, in BOTH rooms, under ONE switch (2026-09-27) — supersedes the section below

⚠ **The wording below is as it shipped on that date and was rewritten 2026-09-30** — the current text is in *Trades room* above.


**Aaron's call:** *"make lot sizes show equally ... and yes show when we scale in ... make sure all
messages are as equal as possible."* `alerts.SHOW_SIZE` is now **True**, and it governs the signals
room too: the setup thread passes it at both of its sized messages (the resting limit's header and
the moved-order lots line), so the two rooms can never again disagree about whether a size is stated.

- **The add is announced either way.** With sizes on it is the sized message (`Added 0.20 lots at
  about 3,300.00 · 1.20 lots now open · every lot on the same stop …`); with sizes off it says
  `Added to the position at about 3,300.00 · Every lot on the same stop …`. Silence was wrong: a
  follower whose thread never says the bot added is copying a trade the thread does not describe.
- **One spelling per figure.** Lots are always two places (the entry printed `0.5 lots` while the
  rest of its own thread printed `0.50`), and R is always two places (the hand-close header printed
  `+0.7R` where WIN/LOSS prints `+0.70R`).
- ⚠ **This reverses Kelly's 2026-09-24 request** for the rooms people follow. Hiding size again is
  the one line — and now hides it in both rooms at once.
- Proof: `test_follower_mode.py` (the OFF rendering of every message, and a structural pin that
  both rooms read the switch — mutation-checked), `test_live_bridge.py` (an add is still announced
  with sizes off — mutation-checked by restoring the old gate).

## Follower mode — the trades room states no sizes and no dollars (2026-09-24) — SUPERSEDED above

**Kelly's call:** *"I don't want the lot size to be shared, just details to follow the bot how it
trades."* The trades room is read by people following the bot, so it now carries prices, stop moves
and R, and nothing that states the account's size.

**One switch: `alerts.SHOW_SIZE`** (default **False**). The formatters each take `show_size`
EXPLICITLY and default it True, so the existing tests keep covering both renderings rather than only
whichever is current; the bridge passes the constant at its four call sites.

| message | before | after |
|---|---|---|
| ENTRY | `Size 0.25 lots · Risking $250.00 (5%)` | the line is dropped whole |
| PART BANKED | `Took 0.12 of 0.37 lots off · 0.25 still running` | `Took part of the position off · the rest is still running` |
| WIN / LOSS | `Made $712.50 · +2.85R` | `+2.85R` |
| CLOSED BY YOU | `Lost $50.00` | the money line is dropped; the R already leads |
| ADDED TO POSITION | a message per add | **nothing — the bridge skips the call** |

**Why the add message could go.** Its docstring called it "not a nicety" because an add makes the
entry's stated size and risk stale. With no size stated there is nothing to correct, so the reason it
existed is gone rather than overruled.

**Why the size line is dropped WHOLE.** A bucketed "small / medium / large" still leaks the account,
and an approximate dollar figure is a number nobody measured (rule 4). **R stays** — it is the result
in units of the trade's own risk, so it says how well the bot traded without saying what the account
stands to make.

🔴 **THE SIGNALS ROOM STILL PRINTS LOTS, AND THAT IS AN OPEN DECISION, NOT AN OVERSIGHT.**
`format_entry_zone`'s header carries `0.25 lots · BUY LIMIT RESTING`, and `format_order_moved` carries
a lots line. Both now accept `show_size` and **neither caller passes it**, because those lots exist at
AARON's explicit request — the code quotes him (*"how many lots are going to be traded"*) and
`test_setup_alert_size.py` asserts them in three tests. **Two owners want opposite things about the
same message.** Flipping it is one argument at each call site in `setup_alerts.py`; it needs their
agreement first, and those three tests then assert the opposite of what they assert today.

⚠ **Wording reaches a phone only through a PROMOTE.** A live bot imports from a frozen `deployed/`
snapshot, so a pushed commit changes nothing until each bot is promoted — and a promote ships
everything else that landed since that bot's last one, not just this.

**Proof:** `algos/tests/test_follower_mode.py`, 8 tests. The behaviour shipped with the change so
there was no red state to watch; it is proven by MUTATION instead — `test_mutation_turning_sizes_back_on_reintroduces_the_leak` flips `show_size` True and asserts every leak reappears (rule 12).
