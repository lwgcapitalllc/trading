# Notes — Account accounting and status reporting

Deposit-vs-return accounting off the deal history, the account-may-trade poll, and the heartbeat/status-file stories. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 The status file is REPLACED, never emptied and refilled (2026-08-24)

`algos/shared/bot_state.py::_save_instance_state` writes a temp file and `os.replace`s it, the same
idiom `algos/live/position_state.py` uses. It was `open(path, "w")` until this date — which TRUNCATES
first — so any of the four readers landing in that window got an unparseable file.

**Measured cost.** 2026-08-22 03:50 UTC the dead-man's switch read it mid-write and sent `/fail`
saying *"bot_state.json cannot be read"*; it cleared on its next pass five minutes later. The bot
never missed a beat — `health-2026-08-22.jsonl` has pulses at 03:41 and 03:56, exactly on schedule.

⚠ **The false alarm was the SMALL half.** `_load_instance_state` swallows the parse error and returns
`{}`, so a `write_bot` landing there rebuilds the entry from defaults and saves — **wiping the other
bot's entry and this bot's own fields.** A reader that can only ever see a COMPLETE file cannot start
that chain, which is why the fix is at the writer rather than a retry in each reader.

⚠ **It does NOT make a read-modify-write atomic, and is not meant to.** Two writers can still lose a
field update; the loser is re-stamped within a poll. Benign. Reading a half-written file was not.

⚠ **The temp name carries the PID** — two processes sharing one scratch path is the same defect one
level down, where A's `os.replace` publishes B's half-written bytes.

⚠ **No trade was ever at risk and the watchdog was never fooled.** `monitor.py` reads the heartbeat
through the swallowing loader, gets `0`, and its own guard turns that into `stale_secs = 0` — so it
neither alarmed nor restarted. Nothing in the trading loop reads this file to decide anything.

**Tests:** `algos/tests/test_bot_state_atomic.py` (4). Three watched RED against HEAD (1,195
unreadable reads of 6,965; the good record overwritten; no scratch-path separation). The litter check
passed at HEAD by construction and is pinned by MUTATION — removing the temp cleanup reddens it.

## 🔴 A deposit is not a return — the return comes off the broker's deal history (2026-09-12)

**`total_pnl_pct` was `(balance - starting_balance) / starting_balance`, so every dollar arriving
after the anchor read as profit** — a $9,860.51 transfer into live account 34957946 showed
**+2,181.67%** on the Bots page, the Overview and `/balance`, over two bots that had not traded. A
withdrawal read as a loss the same way. Aaron: *"if I deposit money that should not show as the
account return, same thing if I withdraw."*

✅ **The runner reads the account's whole deal history (`BotMT5.account_deals`) and
`shared/account_flows.py` splits it.** MT5 books a deposit or a withdrawal as a deal of its own
(BALANCE), so nothing is inferred. The heartbeat writes `capital_in` (deposits less withdrawals),
`pnl_usd` (balance less that) and `total_pnl_pct`, now **time-weighted** — each stretch between money
moving is measured on its own and the stretches chained, so a deposit neither counts as a return nor
dilutes one. The pulse carries `capital_in` and `return_pct` too, so an account a bot LEFT is still
read net of deposits.

- ⚠ **Not "return on the balance before any trades"**: that keeps a deposit out of the bottom as
  well as the top — after this deposit one 5% trade would read +114% of the $451.97 it opened at.
- 🔴 **The deals must rebuild the broker's balance to the cent, or nothing is written** (all three
  `None`, one warning per cause) — **and never the anchor formula as a fallback**, the number known
  to be wrong the day anyone deposits. MEASURED read-only 2026-09-12: live 2 BALANCE deals rebuilt
  10,312.48 = 10,312.48; demo one +10,000 deposit and 22 trades rebuilt 15,844.46 = 15,844.46.
- ⚠ **CREDIT is skipped** (kept outside the balance); **a BONUS is money put in**; everything else
  that moves the balance is trading — so a withdrawal FEE booked as a charge reads as a small
  trading loss. Unmeasured here; read it off the first real withdrawal.
- ⚠ **Only for the account the terminal reported off the same call as the balance** (rule 16);
  re-read when the balance moves or every 15 minutes; **it never raises**, because it runs before
  the heartbeat write and a display figure must never cost the stamp SYS_MONITOR runs on.
- ⚠ **Emptying an account and refilling it is fine**; a trade booked while it held nothing refuses.
- ⚠ **`starting_balance` is still written** — the rename guard reads it and the Command Center falls
  back to it for a bot on an older runner — but nothing on this box reads it as a return.
- ⚠ **Reaches a bot by `git pull` plus a restart** (`algos/`, no promote).

Tests: `test_account_flows.py` (15), `test_watchdog.py` → *Overall P&L* (10),
`test_mt5_ops_pending.py` (4). **27 mutations RUN, 27 killed**; a no-op control survived, so the
harness can report a survivor.

## 🔴 Whether the account may TRADE is read every poll, and said once (2026-09-12)

**On 2026-09-11 PU Prime put live account 34957946 on read-only until it held the ECN minimum.
Every order from 12:45 AM to 7:30 AM CDT came back refused (10017), and nothing on any screen said
trading was off until the bridge halted at 7:45** — while the terminal could report it all along.

`runner._check_trading_allowed` runs each poll right after the identity check and asks
`runner.trading_block` four questions: the account's `trade_allowed` (read-only) and `trade_expert`
(automated trading barred), the terminal's `trade_allowed` (the AutoTrading button), and the
symbol's `trade_mode` (disabled / long only / short only / close only).

- 🔴 **It REPORTS and changes nothing.** A setup still fires, the broker still refuses, the bridge
  still halts. Refusing here would be a second place deciding whether an order goes out, on a flag
  nobody has watched this broker flip — **which of the four read-only moves is unmeasured**, so all
  four are read and the first poll on an affected account measures it.
- ⚠ **Three answers** (rule 1): off, on, could-not-ask. A missing or unreadable flag is UNKNOWN,
  never yes, and a no outranks an unknown. Could-not-ask says nothing and keeps what was said.
- ⚠ **Only for the account this bot trades**, off the same `account_info()` call as the balance —
  `probe_link` keeps the whole reading now (`_observed_info`), `None` on a dead link. On another
  account the identity halt owns it (rule 16).
- ⚠ **Said once per REASON, and recovery speaks** (TRADING OFF / TRADING BACK ON, HEALTH), so the
  silence between is safe; a different reason is said again. Ledger: `trading_disabled` (with the
  reason) and `trading_restored`, both HEALTH.
- 🔴 **Recovery over a HALTED bot says STILL HALTED and "Restart it", never "Nothing to do."** A
  halt latches, and a trade triggering while orders were refused is what halts one — so an
  all-clear there stops somebody looking (the RECONNECTED rule, again). The OFF message says so.
- ⚠ **The heartbeat carries `trade_allowed` / `trade_block`** for the Command Center's chip, `None`
  on a dead link. **Never raises** — it runs ahead of the bars.
- ⚠ **Reaches a bot by `git pull` plus a restart** (`algos/live/`, no promote).

Tests: `test_trading_allowed.py` (22) + one loop test in `test_mt5_link.py`. **26 mutations RUN, 26
killed** — the loop's own call first SURVIVED, because every other test drove the check directly.

## The heartbeat says what the bot holds at the broker, and why it halted (2026-09-12)

For the Command Center's two row tags — **trade open** ("LONG 0.40 lots · +1.2R") and **halted**.
Until this date the row read RUNNING through every halt (the hourly review chip was the only sign,
up to an hour late), and nothing said a bot held a trade at all.

- 🔴 **The trade is read off the BROKER every poll** (`runner._position_reading` →
  `BotMT5.open_positions_strict`), never off the bridge's record, which learns of a stop-out on its
  next bar. `runner.position_summary` sums every ticket (added lots included), averages the entry,
  and takes the stop off the bridge's own ticket. Both sides at once reads `mixed`, with no R.
- ⚠ **Three answers** (rule 1): `in_trade` True / False (flat) / None (could not ask; a dead link is
  not even asked). `open_positions_strict` is `pending_orders_strict`'s twin: `None`, never `[]`.
- 🔴 **R = open profit after swap over the risk the trade OPENED with, for the bridge's own ticket
  only.** That risk is now SAVED in `position.json` (`BrokerFacts.risk_usd`): the restore used to
  recompute it off the record's stop, which is rewritten on every move — so every R after a
  mid-trade restart, the exit message's included, was divided by the distance the stop had LOCKED
  (and dropped at breakeven). ⚠ **Optional, and `VERSION` NOT bumped** — a bump reads every open
  trade's record as NO record, which halts. A record from before this date restores with the R
  unknown (`0.0`), never one off the moved stop.
- ⚠ **`bridge_state` has its own key.** The heartbeat has always written the bridge's state into
  `status`, but the watchdog and the launcher write running / stalled / stopped / offline into that
  same key (`bot_state.set_status`). `halt_reason` rides only while halted.
- ⚠ **The exit message's R counts the trade's own ticket; the tag counts every lot.** With scale-in
  lots open the two differ, by design — the tag describes the money at the broker.
- ⚠ **Never raises** — it runs ahead of the heartbeat write, whose failure mode is no stamp.
- ⚠ **Reaches a bot by `git pull` plus a restart** (`algos/`, no promote).

Tests: `test_heartbeat_position.py` (15), 2 in `test_mt5_ops_pending.py`, 6 in
`test_position_restore.py`. **19 mutations RUN, 19 killed.**
