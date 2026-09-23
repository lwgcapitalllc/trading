# Notes — Telegram rooms and notification format

The two/three Telegram rooms, deploy-as-one-thread, bot version reporting, the resting-message lot size, the shared alert format, the even-underscore bot-name bug, and the six lost Telegram commands. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### Two rooms — every message declares its KIND

🔴 **Splitting the reviewer's findings out was the small half of this, and shipping it that way would
have missed the point.** Aaron's rule is that the chat he reads for entries and exits carries nothing
else. A sweep of every Telegram sender in the repo found **32 messages going to that chat and only 2
of them were trades**: the live runner's twelve lifecycle messages (link lost, link restored,
re-warming, startup banner, clean stop, config refused, and the bridge's **HALTED**), the watchdog's
nine (offline, restarted, stalled, recovered, two CRITICALs), the command center's nine buttons
(start/stop/restart/promote/runtime params), the Telegram bot's own startup ping, and every finished
stress test. **The reviewer had a routing config; nothing else did** — which is the shape of fix that
looks complete and leaves the problem where it was.

So a message now states what it IS and the kind picks the room:

| kind | goes to | who sends it |
|---|---|---|
| `TRADE` | `telegram_chat_id` | `live/bridge.py` only — the entry alert and the exit that replies to it |
| `HEALTH` | `telegram_health_chat` → falls back to `telegram_chat_id` | everything else in the repo |
| `SIGNAL` | `telegram_signal_chat` → falls back to `telegram_chat_id` | `live/setup_alerts.py` only — a setup forming, its entry zone going live, a rule blocking it, and what became of it. See *A THIRD room* below |

⚠ **`kind` is a REQUIRED argument, not a defaulted one.** A default routes silently, and "the wrong
room, quietly" is the exact failure this ends — the same reasoning behind the ledger's stream routing
being a table rather than a guess. ⚠ **And a required argument alone is not the guard**: a forgotten
one is a `TypeError` raised at 3am inside the very alert that was trying to tell you something, so
`tests/test_notification_routing.py` **greps every call site in `algos/` and `command-center/`** and
fails in the suite instead. Same shape as `test_ledger_streams.py`, for the same reason. Both grep
tests also assert they MATCHED something — a sweep that finds nothing passes for ever.

⚠ **The fallback is deliberately asymmetric.** HEALTH with no room of its own borrows the trades chat
and warns once; TRADE never borrows the health chat. Health in the wrong room is a nuisance you can
see, a fill buried in re-warm chatter is the thing being prevented.

### The live rooms — each ACCOUNT names its own channels (2026-09-13)

**Superseded the 2026-09-11 design** (one live trades room and one live signals room for every live
account, in `shared/telegram_rooms.json`). Aaron's rule the day a second person's live account
(35710389) joined the box: two owners, two lots of real money, and neither may read the other's
fills. So a room is a property of the ACCOUNT — `telegram_trade_chat`, `telegram_signal_chat` and
`telegram_health_chat` on its row in `markets/fx/accounts.json` — and `notify.chat_for(kind,
override, account)` routes by the account a message is ABOUT. 34957946 carries the two channels that
were in the retired file; 35710389's owner entered its own trades and signals channels on
2026-09-14, so no live account is waiting for its rooms now.

- 🔴 **A LIVE account never borrows a room.** A trade or signal for a live account that names no
  room of its own is NOT SENT (empty chat id) and says so once per account and kind. Until
  2026-09-13 it fell back to the shared room — right with one owner, a privacy failure with two.
- 🔴 **A bot on a live account with no trades or signals channel REFUSES TO START**
  (`runner._unnamed_channels`, placed after the already-running check and before the version pin):
  exit 5, ledger `startup_failed`, and a WILL NOT START health alert into the room that still works.
  ⚠ **An UNREADABLE registry lets it start — a decision, not a fallthrough.** A bot that does not
  trade because a JSON file will not parse costs setups nobody gets back; a message in the shared
  room is a privacy failure somebody can see and correct. The notifier says so on every send.
- ⚠ **Health is optional**, and falls back to the shared room: most of it is about the one box every
  account shares. Health ABOUT a bot (the monitor, the log review, both watchers) goes to that bot's
  account's health room when it names one; box-level alerts (chat bot down, unreadable registry)
  name no account.
- ⚠ **Three answers, never two** (rule 1): `bot_state.account_row` returns the row, `{}` when the
  registry was read and the account is not in it, and `None` when it could not be read.
  `notify.account_rooms` and `notify.missing_rooms` mirror it.
- 🔴 **`bot_state._account_rows` answers the LAST GOOD rows on a failed read, and that is
  load-bearing.** The box's hourly ledger sync runs `git pull`, which rewrites this file; a fill
  composed inside that window would otherwise read "unreadable" and go to the shared room.
- The room still follows the ACCOUNT, never the bot — move a bot and its next fill reports in the new
  account's room with no edit. A per-bot room in an instance config still wins outright; nothing sets
  one today.
- Channels are entered on the Command Center (Bots → the account → Edit), which refuses every move
  that would put a bot on a live account with none. Its **Send test** runs `tools/verify_channel.py`
  on the box, because the token lives only there. Exit codes: 0 posted, 1 refused or unexpected,
  2 bad arguments, 3 registry unreadable, 4 the account names no channel of that kind.
- **`shared/telegram_rooms.json` was DELETED on 2026-09-14**, once both live bots had restarted
  onto this code. The older code only ever opened it for a live account and treated a missing
  file as "no live room", so the demo copies still on that code were unaffected.
- 🔴 **The start-up log names the room signals actually go to** (`runner._signal_room`). Until
  2026-09-14 it printed "the shared telegram_signal_chat" for every bot without a per-bot room,
  while the live bot's signals were going to its account's channel — a label that never asked.
- Proof: `tests/test_notification_routing.py`, `test_live_rooms_runner.py` (the runner through the
  REAL router, the start gate driven through `_run`), `test_verify_channel.py`, plus the monitor,
  log-review and watcher tests; 12 bugs planted by `scripts.testing.mutate`, 12 caught.

⚠ **The HALT is HEALTH, and it is the call worth defending** — it is the most consequential message
here, which is precisely why it must not sit in a room only checked when a fill arrives. It is also
why `log_review.py` raises it AGAIN as a standing chip on the Bots page: one Telegram line, in any
room, was never enough for that one.

⚠ **Telegram command REPLIES are not routed at all** (`telegram_bot.send_to`) — an answer belongs
where the question was asked. A `/balance` typed in the trades group replying somewhere else would be
baffling, and it is not an unsolicited message competing for attention.

⚠ **`command-center/backend/services/notify.py` carries a SECOND copy of this table**, because the two
subsystems may read each other's files and never import each other's code. What holds them together is
that both route on the same credential KEYS, pinned by a backend test that READS `shared/notify.py`.
That app also refuses to use `TRADE` at all, by test: it has no way to know a trade happened.

⚠ **`log_review.py` read `credentials.json` directly until this pass**, which silently ignored
`LWG_TELEGRAM_HEALTH_CHAT` — an env override this repo's own template documented and nothing honoured.
It goes through `notify.chat_for` now. **A second reader of one credential is a second answer.**

### A THIRD room — `SIGNAL`, the pre-trade setup channel (2026-08-13)

Aaron's ask: know a setup is coming *before* it trades — the confluences so far, the entry ZONE
(shallow to deep), the projected stop — then have the outcome reply to that same message, whether
it filled, was blocked by one of his own rules, or died. New Telegram group, **LWG Capital
Signals**.

`SIGNAL` → `telegram_signal_chat`, per-bot overridable exactly like the other two. **A third room
because it is a third reflex** — read when you have time, not the moment it arrives — and because
it is MEASURED at ~10x the volume of fills (**20.2 messages/month against 2 fills**, one every 1.5
days, on `sos_fade` over 6.5 years). Putting that in the trades chat would bury the fills under
setups that mostly do not become trades, which is the failure the split already exists to prevent,
arriving from a new direction. Fallback stays asymmetric: SIGNAL borrows the trades chat and warns
once; **TRADE never borrows another kind's room.**

**`live/setup_alerts.py`** is the transition layer and knows NOTHING about any strategy — it reads
`backtest.setups.SetupSnapshot`, so a new bot gets alerts by implementing `live_setups()` and
nothing here changes. Formatting is in `live/alerts.py` (pure, no network, so wording is
unit-testable and can never move a trade). Sending goes through `runner._notify`, so per-bot chat
and token routing come free.

⚠ **Per SETUP, not per transition, and that is a MEASURED failure rather than a preference.** A
resting limit is rebuilt every bar and cleared when not armed — 665 raw transitions across 332
setups over 6.5 years. Edge-triggering alone still announces one setup two or three times.

**The messages are FOUR lines, and they were eight** (Aaron, 2026-08-13, on the first real renders:
*"can you make them less verbose?"*). Confluences collapsed onto one line as the strategy's own
`detail`; `Waiting on a retrace into that zone` went because it sat directly under
`Retrace zone — not tagged yet`; `(the zone's deep edge)` went because it explained a number rather
than giving one. 🔴 **The resting message names only what is OUTSTANDING, and that one line is a
safety property, not a nicety** — an order can rest at 2 of 3 (the gap can exist before price gets
there), so a message carrying a price must not read as *everything is met*. ⚠ **The `display` name
comes from the RUNNER**, because a strategy only knows its class name and `SosFadeStrategy` is
not what the same bot is called in every other message.

🔴 **AND THE SAME TRIM CAUSED THE NEXT DAY'S DEFECT, so the rule it produced is the one to keep:
when trimming a message, a word that explains a NUMBER is decoration and a word that names the
STATE of something is not.** `(the zone's deep edge)` tells you how a price was derived and a
reader can live without it; `(limit resting)` — deleted in the same pass, as the same kind of
parenthetical — was the only word saying no position existed, and the message was read as a fill
the next day. The header is the MT5 order type now (`BUY LIMIT RESTING` / `SELL LIMIT RESTING`) so
the message and the terminal call one thing by one name, and the price line says `Limit`, never
`Entry`. Four tests pin it, all watched RED. Story: `docs/ALGOS_BUILD_NOTES.md` → *The limit that
read as a fill*.

🔴 **`algos/tests/test_setup_alert_wording.py` exists because there was NOTHING there — every one
of these four formatters was rewritten and 643 tests stayed green.** `test_setup_alerts.py` covers
which message fires and in which thread, and asserted not one word of what any of them SAY.
**A message is not a side effect of this system, it is the product**: nobody sees a `SetupSnapshot`.
12 tests, all 7 mutations reddening their own named test. It pins the CLAIMS a message makes that
could be false, never the wording — renaming a label must not redden it.

⚠ **A wording change needs a PROMOTE and a restart** since 2026-09-17: `algos/live/` is in the
frozen tree now (`notes/bot-registries-and-lifecycle.md`). A change to a strategy's confluence `detail` or death sentence is the other way round — that is
`strategies/python/`, so it needs `promote.py`, and the death sentences are shared with the lab's
miss report.

**`tools/signal_samples.py` sends one example of every thread shape** — eight of them, covering
both directions, all three retrace wordings, an order resting at 2 of 3, one blocking rule and
three, a block that LIFTS, and every death the strategy has a sentence for. `--dry-run` prints and
sends nothing. ⚠ **It builds real `SetupSnapshot`s and calls the real `alerts.format_*`**, so a
sample cannot drift from what the bot sends; hand-typed samples would review wording that does not
exist. ⚠ **Its `render()` duplicates `SetupAlerts._handle`'s routing** and is the one thing here
that CAN drift — if the order of the checks in `_handle` changes, change it here too.
🔴 **Telegram's group ceiling is ~20 messages a minute and a burst tool is the only thing here that
can reach it** — the first run sent at 1.2s and lost four of twenty-four to `429`, orphaning the
replies under them. 3.5s now, with one retry after a 30s pause. ⚠ **It reports what LANDED and
exits non-zero on any failure**: it printed `sent: 24` while four had been refused, which is the
requested-vs-received rule inside the tool written to check the messages. **The pacing belongs to
the tool, not to `notify.py`** — a bot sending a handful an hour must not pay for a burst sender.

⚠ **NEVER RAISES, and it binds harder here than anywhere else in the package**: `on_bar` runs
inside `_on_bar`, between the strategy stepping and the broker being reconciled.

🔴 **A strategy without the contract gets no alerts and the runner SAYS SO by name at startup** —
never a silent skip. Same rule as `_log_risk_cap` beside it: an absent reporter and a quiet market
look identical from outside. The `setup_alerts` ledger event records ON or OFF, and OFF carries
why.

🔴 **Warm-up snapshots are DISCARDED in `warm()`, and this is louder than the stale-record rule it
sits beside.** `drain_setups()` returns everything resolved since the last drain, so without the
discard the FIRST live bar would post years of history into Telegram in one burst — and again on
every restart.

🔴 **NOTHING IN `algos/live/` MAY IMPORT `backtest`, `engines` OR THE STRATEGY PACKAGE AT MODULE
SCOPE, AND THIS TOOK THE LIVE BOT DOWN ON 2026-08-13.** `alerts.py` grew a module-level
`from backtest.setups import FILLED`; `bridge.py` imports `alerts` and `runner.py` imports
`bridge`, all before `_bind_code()` binds the frozen snapshot. Every start died with
`Cannot freeze this deployment: … was already imported from the repo before the snapshot was
bound`, exit 2, uptime 1 second, on a ~60s watchdog loop until the import moved into its function.

✅ **The guard worked exactly as designed** — it named the module, named the cause and said what
to do, and it refused to run rather than silently half-applying the freeze. ⚠ **What it could not
do is fire before the code reached a live bot**: `is_frozen` is false in every test and every dry
run, so the ONLY configuration that trips it is the one with real money behind it.
`_bind_code`'s docstring said *"Nothing in `algos/live/` imports these at module scope
(checked)"* — checked by a human, once, and no longer true by the time it mattered.
**`tests/test_no_frozen_imports_at_module_scope.py` now imports each entry module in a SUBPROCESS
and fails by name**, so this fails in the suite instead of on the box. **The fix is always to move
the import inside the function, never to add an allow-list.**

⚠ **`setup_alert_categories` distinguishes ABSENT from EMPTY.** Absent = all four; `[]` = the
reader switched them all off. Collapsing them would make a config typo look deliberate.

🔴 **The resting-limit message waits for `snap.announce_resting`, and the CHECK ORDER is the whole
point.** It is tested BEFORE `_sent` is marked — marking first would burn the setup's one
resting-message slot on a bar the message was suppressed, so the announcement would never arrive.
Same bookkeeping-before-the-guard trap the `tradeable` check beside it is written to avoid, and
silent in the same way. ⚠ **The STRATEGY owns when a resting order is worth announcing**
(`backtest/setups.py`); this layer has no price and must never learn what a fib is. Aaron, on a live
message: *"I only want to know a limit is pending when price gets back to 23.6% of the
retracement."*

⚠ **A setup the strategy has already refused is never announced** (`SetupSnapshot.tradeable`) —
Aaron's rule: *"I should only be getting signals for the trades originating from my default
settings."* The guard is checked BEFORE any bookkeeping, so a suppressed setup leaves no thread
entry behind and can still be announced later if it becomes tradeable.

✅ **The paired invariant — every trade in the TRADES room originated from a thread in the SIGNALS
room — is CHECKED, by `backtest/tools/alert_rate.py`, not asserted.** 159 trades closed, 158
announced as ENTERED over 6.5 years; the one gap is the warm-up boundary. **Re-run it after any
entry-logic change**, because that check is how the `tradeable` filter fails: suppress one setup
too many and a real trade arrives in the trades group having never been signalled, with nothing
anywhere reporting a skipped message.

**The credential is `telegram_signal_chat`** (`algos/credentials.json`, git-ignored, per machine;
env `LWG_TELEGRAM_SIGNAL_CHAT`). ⚠ **Aaron's group is a BASIC group, not a supergroup** — id
`-5572666026`, no `-100` prefix. **Telegram silently CHANGES that id if the group is ever upgraded
to a supergroup** (which happens on its own when enough members join, or it is made public), and
the sends then fail into the log rather than erroring anywhere visible. A signals channel that has
gone quiet for days is that, until proven otherwise.

### 🔴 A SETUP THREAD DID NOT SURVIVE A RESTART — four identical alerts for one setup (2026-09-16)

**Aaron, 2026-09-15:** *"I have got the same alert 4 times about the same entry over the past 24 hrs
… why not just get it once and why did it not ever invalidate?"*

**MEASURED on `sos_fade_1`** (demo, 700152905). One long setup, alive from 08:00 on 2026-09-15 and
still alive when this was found, produced **four `SETUP FORMING` roots inside 24 hours** and **not
one of the first three could ever be closed**. Two independent causes, one symptom — and fixing
either alone still leaves the alert duplicating.

**Cause 1 — the bookkeeping lived in memory.** `SetupAlerts` held which messages a setup had been
sent, and the Telegram message id its outcome must reply to, in two plain dicts on the instance. A
stop, a start, a redeploy or a mid-session re-warm therefore wiped both: every open setup was
announced again from scratch, and the id of the message the reader was actually looking at was
gone, so the outcome could never be posted as a reply to it. That bot restarted or re-warmed three
times in the window (03:48, 22:15, 01:48) — plus the original start, which is the four.

**Cause 2 — the setup's IDENTITY was a bar POSITION.** `_setup_key` was
`f"{name}:{side}:{sos_bar}"`, and `sos_bar` is an offset into the warm-up window, which slides every
time the engines re-warm. Measured: the same live setup's number slid **4958 → 4888** on
`sos_fade_1` and **5050 → 4980** on `sos_fade_2`, both by exactly **70 bars**, which is the window
moving rather than new structure. Each slide RENAMED a setup that had not changed, so even a
persisted record would have re-announced it. ⚠ **The old docstring said the key was keyed on the SOS
bar "rather than on anything that moves".** `_same_leg`, forty lines above it in the same file,
already carried a time fallback for exactly this — the two answers to one question disagreed for the
life of the feature.

**Why it never invalidated, which is the second half of the question.** It never invalidated because
the setup was genuinely still alive: a setup resolves when it fills, when another position takes the
slot, or when its structure leg dies, and none had happened. The three ORPHANS, though, could never
resolve on any future bar, by construction — `_book_setup_end` drops a death whose context this
process never built, and its docstring justified that with *"there is no setup the reader was ever
told about to close"*, which stopped being true the moment threads outlived the process.

**The fix, 2026-09-16 — three parts, and the third is the one that is easy to leave out.**

1. **`_setup_key` keys on the SOS bar's TIME**, snapshotted onto `_MissWatch.sos_ms` when the watch
   opens, with the bar number as a prefixed (`t` / `b`) fallback for a bar older than the
   20,000-entry time map. ⚠ The prefixes are load-bearing: a timestamp and a bar index are both bare
   integers and an unprefixed key could call two different setups one thread.
2. **`SetupAlerts` persists** both dicts plus each thread's side and symbol to
   `<instance>/setup_threads.json`, written atomically (`os.replace`) because this runs inside the
   bar loop and a truncated file would throw away every open thread on the next start — the very
   failure, arriving through its own fix. An unreadable file costs the de-duplication for one
   restart and never the start.
3. **`SetupAlerts.reconcile`, at the end of every `warm()`**, closes what can no longer be open.
   `warm()` already drained the strategy's replayed setups and binned them wholesale; it now keeps
   them, and reconcile picks out only the ones matching a thread this bot actually announced, so a
   setup that died during the outage is closed with the **strategy's own sentence**. One with no
   replayed death and no live setup gets `🧹 THREAD CLOSED`, which deliberately does **not** say
   `NO TRADE`: the bot does not know whether it filled or died, and a confident outcome on a setup
   that might have traded is a label with no code behind it.

🔴 **Only a FINISHED setup counts as an outcome, and never one that is still live (fixed
2026-09-16).** The warm-up drain holds every setup the strategy reports, open ones included.
Reconcile read an open short as "resolved" and posted `👋 NO TRADE · SHORT` with no reason on the
demo bot's 18:41 UTC restart; the bot placed that short at 18:45. Reconcile now skips anything not
finished or still live, `format_resolved` refuses an unfinished setup, and a `NO TRADE` with no
strategy sentence says so rather than going blank. ⚠ The older "still live" test passed an empty
drain, which the runner never sends — that is why it never caught this.

🔴 **The thread follows the order the BROKER holds (2026-09-16).** After the first `🎯 RESTING`,
any change visible to the reader — price, stop, or lots, compared at display precision — gets one
`🔁 LIMIT MOVED` reply showing old → new. **A cancelled order posts nothing** (Aaron: *"I don't
need the cancel messages"*); the last-described order is kept, so the replacement is compared
against what the reader last saw and an identical re-placement stays silent. The numbers come
from the bridge's record of what was SENT (`resting_order`), never recomputed, and the
last-described order is persisted with the thread, so a promote that cancels and re-places is
covered. Aaron's reason: a fill must never land under a message quoting a price and size the
account is not trading. ⚠ This reverses the 2026-08-13 "announce once" call. **MEASURED**
(`backtest/tools/alert_rate.py --symbol XAUUSD.p`, sos_fade, 2020-01 → 2026-09, no broker so lots
not compared): 439 moved, total volume 19.6 → 25.0 a month. Live compares lots as well, so it can run slightly higher.

🔴 **A PROMOTE THAT RENAMES SETUPS CLOSED A LIVE SHORT'S THREAD (2026-09-16, fixed same day).**
`sos_fade_demo` ran snapshot v182 (hash `11351a74e708`, tree of `4f87809d`), which keyed setups by
bar POSITION — the 18:00 UTC short was stored as `SosFadeStrategy:S:5018`. The 20:17 UTC promote to
v195 keys by TIME (`…:S:t1789581600000`). The warm-up still watched the setup (the next ledger bar
shows stage 2 on the same shift bar), but no stored key matched, so reconcile posted `🧹 THREAD
CLOSED` — and the setup would be announced again as new on the next bar. **MEASURED** by replaying
the old snapshot 13:30 → 20:00, then the new code's real `warm()` on the state it wrote: 1 closed
before the fix, 0 after. ⚠ The version line said `commit c8cdd64e`, but the snapshot hash matched
`4f87809d` — **the label is not the code; hash the tree** (`version.deployment_hash`).
The fix: a strategy declares `setup_key_scheme` (sos_fade: `time-v1`), the state file records the
scheme its keys were written in, and when the two differ reconcile **carries** an unmatched thread
onto the one unannounced live setup with the same side and symbol — root, messages sent and last
order move with it. Two old threads on a side, or none live there, is ambiguous and still closes.
⚠ Residual risk: an old setup that died AND a new same-side one that formed inside the restart gap
would inherit the old thread. ⚠ **Change the scheme string whenever the key format changes.**

🔴 **An order the STRATEGY withdraws says so, once (2026-09-16).** The final-hour rule pulled that
same sell limit at 20:15 UTC while the setup stayed open, and the thread's last word was still
`🎯 SELL LIMIT RESTING`. The setup's zone was untagged, so `BLOCKED` (ready setups only) had nothing
to say. A snapshot now carries `paused_by` — the rules keeping its order off the book (veto, final
hour, HTF filter) — and the thread posts `⏸ LIMIT WITHDRAWN` with the rule, once. The next order
is always reported as `🔁 LIMIT MOVED`, even at the same price, because the reader was told it was
gone; the marker rides the saved `sent` set, so a restart keeps it. ⚠ **A pull with no named rule
stays silent** — the cancel-and-replace churn Aaron asked to hear nothing about.
✅ **Every named pull is covered since the same evening** (Aaron kept WITHDRAWN and asked for the
rest). sos_fade names: divergence veto, final hour, short-hold hour window (its own label, no longer
read as the final hour), HTF breakout / bias filter, flat-by-close window, stop too tight, market
too quiet, limit deeper than the short-hold maximum, and no room under the account risk cap (at
placement and at the fill). The reasons are set in `_place_entries` from the same booleans that
removed the order, not recomputed. ⚠ **Still silent, by design:** no edge to rest on (no gap in the
zone), an arm source switched off, a wrong-way fib, an already-traded leg — none is a rule to wait
out — and a broker-side cancel. ⚠ `b_leg`, `bos` and `realign` replace `_place_entries` and name
nothing. ⚠ **The extreme leg has no setup alerts at all** (its log says "Setup alerts: OFF"), so it
has no thread to withdraw. ⚠ **Reaches a bot only on promote**
(the field lives in `backtest/` and the strategy); the runner half reaches it by pull and is inert
until then. **MEASURED** trades unchanged: `replay_fingerprint.py` 2024-01 → 2026-08, 66 trades
identical.

🔴 **`live_keys=None` means *could not ask* and closes nothing; `[]` means *watching nothing* and
closes everything.** Root `CLAUDE.md` rule 1, in the signals channel — collapsing them would post
"no longer being watched" onto setups the bot is watching right now. ⚠ An early version of that test
went green against the collapse by accident: `None` fed into `set()` raised, the never-raises guard
swallowed it, nothing was sent, and the assertion passed for a reason unrelated to the rule. The
test now asserts the log is silent too, so silence has to be deliberate.

⚠ **Reconcile runs at the end of `warm()`, not next to the alert construction.** `_start_setup_alerts`
runs BEFORE the warm-up, where the strategy has replayed nothing and would answer "watching no
setups" — which would close every thread it is still watching. Putting it in `warm()` also means the
mid-session re-warm gets it for free; at a call site, the one that got forgotten would silently stop
closing threads.

⚠ **The stored threads are BOUND to their Telegram chat.** A message id means something only
inside one chat, and a bot moved to another account writes to that account's signals channel —
`sos_fade_2` was moved exactly that way on 2026-09-15. The state file records which room it was
written for; when that changes, every stored thread is dropped and the change is LOGGED, because a
silent drop looks identical to the bug this whole file fixes. Any still-open setup is then announced
once more, in the new room, which is the only honest option available.

⚠ **A redeploy does NOT lose the threads.** `promote.py` replaces `deployed/` and never the instance
folder, so `setup_threads.json` sits beside `bot_state.json` and survives.

⚠ **Nothing here can move a trade**, and the parity gate cannot prove that for you: `compare_strategy.py`
on the golden export is RED on `px_s_stage` at bar 16 and was RED identically before this change.
What it rests on is that `_setup_key` and `_MissWatch.sos_ms` are read only by `_setup_context`, and
no method in that block is called from `step`, `step_secondary` or `_manage_open`.

---

### A deploy is ONE event — its three messages are now a THREAD (2026-08-14)

Aaron: *"Look at the messages every time I promote also; can this be a thread instead of
individual messages?"* A promote produces **STOPPED, PROMOTED and ONLINE** — and the middle one
comes from the command center on a laptop while the other two come from this bot on the VPS, so
they arrived as three unrelated bubbles with nothing saying they were one action.

The command center sends the PROMOTED **root**, then writes its Telegram message id into
`<instance>/alert_thread.json`. `runner.py` reads it and REPLIES with STOPPED and ONLINE. The
instance directory is the channel those two processes already share (`stop.request`,
`bot_state.json`, `review.json`), so nothing new had to exist to carry it.

🔴 **The one way this could be WORSE than not threading is a STALE id**, and it is the
`stop.request` hazard exactly: a file in an instance directory that outlives what it describes.
There a leftover request stopped a healthy bot; here a leftover id quietly parents every future
lifecycle message under an ancient deploy — in the channel whose whole job is saying what is
happening NOW. **Two guards and neither alone is enough:**

* an **EXPIRY** (15 min, written by the sender) covers a restart that never completed, where
  nobody is left to delete the file. A record with no expiry at all is ignored — defaulting that
  field to *forever* would make the missing value the most dangerous one in the file;
* the **ONLINE alert CONSUMES it**, covering a bot that restarts twice inside the window.

⚠ **STOPPED must NOT consume it** — the ONLINE that follows a promote is sent by a DIFFERENT
PROCESS, so deleting the file there orphans the message the reader is actually waiting for.
Pinned by a test that READS `runner.py` and counts call sites, because the behavioural version
of that check was **measured vacuous**: adding `clear_alert_thread()` beside the STOPPED alert
left every test green.

⚠ **Only the two lifecycle messages a promote causes are threaded** (`_notify_health(...,
thread=True)`). Threading everything would file an unrelated 3am reconnect under that morning's
deploy.

⚠ **Every failure answers "no thread"**, which is the behaviour every bot had before this
existed — a missing file, an unreadable one, an expired one, a message id of 0. A notifier
convenience must never be able to cost a lifecycle message.

⚠ **The ROOT is sent BEFORE the bot is stopped**, and the ordering is the feature: this bot
writes STOPPED the moment it notices its stop file, seconds later, and a root sent afterwards is
not the root of anything. So the root states the INTENT (*"Restarting it now"*) and the two
replies report what happened.

### The version a bot reports — it was `v0` for the life of the field (2026-08-14)

🔴 **`LiveConfig.strategy_version` was declared `int = 0` and NOTHING assigned it**, so every
bot's ONLINE banner read `v0 (e4137dbb)` on every start, and so did the log banner, the ledger's
startup record and `bot_state.json`. Aaron, off the health channel: *"the last message say V0? Is
it missing the version deployed."* **A declared field with a default is indistinguishable from a
measurement** — the same defect as `running=False` in the lab and `is_compiled` defaulting to 1.

**`algos/tools/promote.py::version_at` measures it and stamps it into `deployed.json`** (which
overrides `config.json` for the version fields, as `promoted_commit` already did). A version is
the **count of commits that changed a file this bot's deploy COPIES**, derived from `repo_trees` —
the same function that decides what is COPIED, so a tree that deploys is a tree that counts. It
moves when and only when the code this bot runs moves, and subtracting two of them is the work
between two deployments.

🔴 **It counted every commit TOUCHING those trees until 2026-09-10**, so a CLAUDE.md edit inside
`engines/` stamped a new version on every bot. The file rule is `package_deps.version_pathspecs`,
shared with the Command Center. ⚠ **Every number dropped once, and a running bot keeps its OLD
stamp until its next promote** — the deploy message stays coherent because it recounts the "from"
side off the previous commit with the new rule rather than reading the old stamp.

⚠ **`None`, never 0, and it renders `v?` through the single `LiveConfig.version_label`.** 0 is a
version somebody could genuinely be on, and it is precisely the value that was lying. Four
readers share that one rendering because `f"v{None}"` prints `vNone` in every one of them.

⚠ **The count is stamped at PROMOTE time and that is the whole point.** `command-center`'s
`bot_versions.version_at` runs the same command over the same trees, so the two agree by
construction rather than by being kept in step — the difference is WHEN. The bot has no git and
no backend; the stamp is what lets it state its own version.

⚠ **A bot promoted before this has no stamp and reads `v?`** until its next promote. That is the
honest answer, and it is why nothing back-fills a number onto a deployment nobody measured.

⚠ **`promote.py` also prints `##VERSIONS <from> <to>`** — a machine-readable line for the caller
that has to put those in a message, parsed and stripped by the command center's promote route.
The prose line beside it is for a human; **scraping the prose is what the OK/FAIL markers already
exist to avoid**, and a reworded `print` must not change what anything reads.

### 🔴 THE RESTING MESSAGE CARRIES ITS LOT SIZE, AND THE BAR ORDERING HAD TO MOVE FOR IT (2026-09-03)

Aaron: *"I need to see how much lots are going to be traded."* The message announcing a resting
limit could not say, and the reason was ORDERING rather than a missing field.

🔴 **THE ALERT WAS COMPOSED BEFORE THE ORDER WAS PLACED, SO IT WAS A PREDICTION.**
`runner._settle_primary` ran the alerts first and `bridge.sync` second — deliberately, so that an
alert never depended on a network round trip. But this message's whole job is to say **an order
EXISTS AT THE BROKER**, and it was written before the broker had been asked. Two consequences, and
the second is worse than the missing size: **a limit the bridge then REFUSED outright was still
announced as resting**, naming an order nobody held.

✅ **The alerts now run AFTER `bridge.sync`, and the property the old order bought is kept by
`finally` rather than by sequence.** `sync` makes live MT5 calls and an exception there breaks the
bar stream, so a bare reorder would let a broker wobble silence the signals channel — trading one
defect for a quieter one, which is the worse direction every time. ⚠ **The bridge's exception is
NOT swallowed**; it still propagates, because the stream break is how a broken bridge gets noticed.

🔴 **THE SIZE IS READ OFF THE PLACED ORDER AND IS NEVER DERIVED IN THE ALERT PATH.** The strategy
sizes in INSTRUMENT UNITS (ounces for gold); MT5 takes LOTS. A message converting for itself would
be a second answer competing with `shared/order_sizing.py`'s one seam — **the defect that rested
54.82 lots on a $2,000 account, 221x the intent.** `bridge.resting_lots(direction)` returns what
`_rest` holds, i.e. what was sent and is showing in the terminal. ⚠ **`alerts.py` still knows
nothing about lots** — it renders a number it is handed, and the unit is NAMED in the message
because a bare figure here is the one place a reader could take ounces for lots.

🔴 **THREE STATES, and flattening any two breaks a different message** — rule 1 arriving in the
signals channel:

| `lots_for` | means | the message |
|---|---|---|
| absent | there is no broker to ask — a backtest, `alert_rate.py` | sends, with NO size |
| returns a float | an order of that size is live | sends, with the size |
| returns `None` | ASKED, and nothing is resting (refused/cancelled) | is not sent at all |

⚠ **The lookup happens BEFORE the message is marked sent**, for the same reason `announce_resting`
does: an order refused on one bar can rest on the next, and consuming the setup's one resting-message
slot early would mean the announcement never arrives. **This layer has now made the
bookkeeping-before-the-guard mistake twice and been written against it three times.**

⚠ **Absence of the callable is how *cannot ask* is expressed**, so a bot with no bridge renders
exactly as it always did — that path is what `alert_rate.py` measures the channel's volume on, and
silencing it would delete the measurement the channel is tuned by.

### One shape for every message — `shared/alert_format.py`

**Aaron's brief, 2026-08-05, after picking from rendered samples in the health chat:** concise, but
never so concise you cannot diagnose it; facts that belong together on one line, facts that do not
on the next; and it must be obvious what to act on.

    <icon> <LABEL> · <subject>
    <the facts, grouped>
    <what to do about it>

Every sender in the repo renders through `alert()` — the runner's twelve, the bridge's three, the
watchdog's nine, the reviewer's findings, the Telegram bot's ping, and the command center's ten
through its own mirror. Before this they were five different voices, and each buried the actionable
part somewhere different.

⚠ **The LABEL is the whole message in two words**, because that is what a lock screen shows. It names
the STATE, not the event: `WILL NOT START` rather than `CRITICAL`, because the first says what is
true now. A test caps the header at 45 characters.

⚠ **A health message ends with the consequence, and "Nothing to do" counts as one.** `RECONNECTED …
Nothing to do` is the difference between a glance and an investigation at 3am. The old messages
stated a fact and left the reader to work out whether it mattered.

⚠ **NO TIMESTAMP on a message about now.** Telegram already prints the send time in each reader's own
local clock, directly above the message, and a bot cannot do better — it sends one string to a group
and cannot know where anyone is reading it. A second clock in UTC beside Telegram's local one invites
the reader to reconcile two times for one event. **The one exception is a message about the PAST** —
the hourly reviewer at 21:20 reporting a restart at 18:06 — and `alert_format.when()` renders that in
the box's clock *with the zone named*, because the ledger and the logs are UTC and a bare "6:06" is an
hour of arithmetic away from the record it points at.

⚠ **`log_review._ts` and `_at` are deliberately separate.** `_ts` builds the dedup KEY and `_at`
renders for a human. They were one function, and changing its output would have re-announced every
outstanding finding exactly once — so the wording can never be improved without waking the channel up
unless the two are split. **Cashed in on 2026-08-13**: `when()` gained a date and not one outstanding
finding re-announced.

🔴 **`when()` prints the DATE once the moment is not today, and today still renders bare.** The
reviewer looks back TWO days and fires its findings in one hourly burst, so a bare "11:12 AM CDT" put
yesterday's events and this afternoon's in the same block with nothing to tell them apart — nine
messages at once, five of them from the day before, all correct and all misread. ⚠ **"Another day" is
decided in the READING zone, never in UTC**: they disagree for five hours out of twenty-four, and
stamping an 8pm Chicago event with tomorrow's date is worse than the bare time it replaced.
Story: `docs/ALGOS_BUILD_NOTES.md` → *The burst of nine*.

⚠ **The entry states the risk; the exit does not restate it.** The exit posts as a Telegram reply to
the entry, so "on $200.00 risked" there repeats what is one tap above (Aaron's call). That makes the
ENTRY the only place it is said, which is what `test_the_entry_states_the_risk_because_the_exit_will_not`
exists to protect. **"Risking", never "losing if stopped"** — a gap can fill worse than the stop.

⚠ **The stop distance in pips is gone, and `pip_size` with it.** 1,725 pips on gold answered a
question nobody asks; `Entry 3,290.00 · Stop 3,280.00` says the same thing in the reader's units.

⚠ **`_VERDICT_LABEL` renders `LOSS` while `verdict()` still returns `LOSE`.** The bridge, the ledger
and the tests compare against the value; the label is what a human reads. Merging them would make a
wording change a behaviour change.

🔴 **`when()` shipped with `%-I` and crashed `log_review.py` on its first run on the VPS**, against a
fully green suite on the Mac. `%-I` strips the leading zero on glibc and macOS; on Windows it raises
`ValueError: Invalid format string` (the equivalent there is `%#I`). It formats with the portable
`%I` and strips the zero in Python now. ⚠ **This is the SECOND Windows-only crash in two days to
reach a scheduled task through a passing test run**, the first being cp1252 in this same module — so
the rule is now general: **anything that runs on the VPS is running on a platform the tests are not,
and `strftime`, console encoding and path separators are where that shows up.** Run it on the box.

⚠ **`command-center/backend/services/alert_format.py` is a MIRROR**, for the same boundary reason as
the routing table. `algos/tests/test_alert_format.py` loads it BY PATH and asserts both that the
contract strings match and that the two render byte-identical output on the cases where hand-written
copies diverge first — an absent fact and a whitespace-only one.

### 🔴 A BOT NAME WITH AN EVEN NUMBER OF UNDERSCORES IS EATEN BY TELEGRAM, SILENTLY (2026-09-03)

**Found by the de-branding rename, and it is the whole reason that rename needed a live-path pass.**
`notify.send_telegram_id` asked Telegram to parse every message as Markdown and rescued the message
on a 400. **The rescue only fires when the entity is UNBALANCED.** An EVEN number of underscores
parses perfectly and Telegram applies the italics: `sos_fade_demo` arrives as `sosfadedemo`, HTTP
200, nothing retried, nothing logged, nothing to notice.

🔴 **THE OLD NAME WAS SAFE BY ACCIDENT.** `mpc_sos_fade_demo` carried THREE underscores — odd, so
Telegram rejected it and the plain-text rescue delivered it intact. **Dropping one word turned a
loud failure into a silent one**, in the entry and exit alerts, which are the two messages in this
system a person actually acts on.

✅ **Fixed at the seam, not on the name.** `send_telegram`/`send_telegram_id` take `markdown=True`,
and `runner._notify` — the ONE call every bot message passes through — passes `markdown=False`.
Everything `algos/live/alerts.py` builds is plain text BY DESIGN (its own *"Plain text, no Markdown,
ever"* rule), so asking Telegram to parse it could only ever corrupt it. **No future bot name can
be eaten, whatever it is called.**

⚠ **The default stays `True`** — `watch_broker_costs.py` and the other watchers send real `*bold*`
headers through this same function, so a global switch to plain text would have quietly stripped
their formatting. **The fix belongs to the caller that knows its own text is plain.**

⚠ **Escaping the name was the other candidate and is worse**: a backslash shows up literally
whenever a message does fall back to plain text, and it leaves the next underscore-bearing field —
a symbol, a traceback path — still exposed.

**Tests: 3 in `tests/test_notify_routing.py`, both halves watched RED by mutation** (the wiring
removed from the runner; the plain-text mode forced back to Markdown). One of them asserts the
HAZARD rather than the fix — Telegram accepting an even count with no rescue — because the rescue
passing is what made this invisible for as long as it existed.

### The Telegram bot lost six commands, because none of them could do anything

🔴 **`/restart` and `/stop` asked you to confirm, acted on an EMPTY LIST, and reported success.**
`BOTS` and `TASK_NAMES` had been `{}` since the four first-attempt bots were deleted on 2026-06-22 —
the same empty-registry rot that made `pnl_tracker.py` and `reporter.py` deletable. Aaron asked which
commands were still in use; the answer was that six of them could not have worked.

| gone | why it could not work |
|---|---|
| `/restart`, `/stop` | iterated `BOTS` / `TASK_NAMES`, both empty — **and reported success** |
| `/emergency` | same empty registry |
| `/trades` | read a per-bot trades file `live/runner.py` has never written; always answered 0 |
| `/resume`, `/resetweek` | drove `day_locked` and the weekly counters, written by the deleted `pnl_tracker.py` |
| `/confirm` | nothing can create a pending action once the control commands are gone |

⚠ **`/confirm` is the subtle one.** It works perfectly and can only ever reply "No pending action" —
which is the same defect as the others, one level quieter. A command that cannot do its job is not
harmless just because it fails honestly.

⚠ **Control lives in the command center, and that is not an admission of laziness.** The Bots page can
see how many copies of a bot are running; a phone command cannot. The guard against creating a
duplicate bot had to live with the PROCESS (`startup_coordinator.py`, 2026-08-04) precisely because a
confirmation step cannot make an uncounted start safe.

🔴 **`/status` was itself broken and is now wired to something that cannot go stale.** It looped over a
`BOT_SCRIPTS = {}` literal declared two lines above the loop, so it printed a "Trading Bots" heading
with nothing under it. It reads `bot_state.read_all()` now — written by the runner every poll — so a
bot appears by RUNNING. It reports the process, the heartbeat and the MT5 link as THREE facts, because
a bot can be alive and blind.

🔴 **`telegram_bot.py` was not importable on a Mac at all** (`str | None`, which needs 3.10; the VPS
runs 3.11). It had no tests, and that is why: **a module nothing imports cannot be tested, and nothing
says so.** 30 tests now, 27 of them watched RED against HEAD.

**ARMED 2026-08-05** — `telegram_health_chat` is set on the VPS to the "LWG Captial Bot Health"
group, proven by a `--all` run reporting 2 findings into it. ⚠ **Getting a group's chat id took four
failed attempts and both causes are worth writing down, because the symptom of each is an EMPTY
`getUpdates` and they are indistinguishable from outside.** (1) **BotFather privacy mode is ON**
(`getMe` → `can_read_all_group_messages: false`), so the bot never receives a plain group message —
only a SLASH COMMAND or an @mention — and the update you are waiting for was never delivered rather
than lost. (2) **The running Telegram bot long-polls with an offset, which DELETES each update as it
confirms it**, so a message sent while it is alive is gone before you can read it; killing it is not
enough either, because `SYS_MONITOR` restarts it inside ~60s and eats the next one too. The sequence
that works: `schtasks /change /tn SYS_TELEGRAM /disable`, terminate the process by scoped commandline,
send `/status` in the group, read `chat.id`, then re-enable and `schtasks /run`. ⚠ **Re-enable it** —
disabling that task silences every fill alert on the box, and nothing else reports that it is off.
⚠ **Read `getUpdates` WITHOUT an `offset` parameter while diagnosing**: passing one confirms the
updates and destroys the evidence you are hunting for.

🔴 **Its first real run on the VPS crashed while PRINTING a finding.** A Windows console is cp1252
and cannot encode the arrows, dashes and icons a finding is written with, and Python does not
degrade — it raises `UnicodeEncodeError`. So a scheduled task that detects a halted bridge dies on
its way to telling you. `live/runner._make_logger` carries the identical fix for the identical
reason, so this is now a rule for **anything that prints on that box**: reconfigure stdout/stderr to
UTF-8 with `errors="replace"`, because an unencodable character must cost a glyph, never the message.
⚠ **It was found by RUNNING it, not by reading it** — the module's own tests all passed on the Mac.

Tests: `tests/test_log_review.py` (**77** — this line read 23 while there were 27, so count them
with `pytest --collect-only`). The six added on 2026-09-03 for the deploy-noise fix: **3 watched
RED** against HEAD, and the other 3 proven by MUTATION because HEAD could not fail them; the two
added the same day for the always-write flag were both watched RED, and of the six for the halt
tense **2 were watched RED** with the other four proven by MUTATION (one of those "fails" at HEAD
with an AttributeError, which is a vacuous red and is labelled as one).
🔴 **One PRE-EXISTING test went red on the tense change and the FIXTURE was what was wrong.** It
wrote its heartbeats once and moved the clock an hour — a halted bot that stopped heartbeating,
which is a different incident with its own alarm. A halted bot is still turning its loop, so it
keeps beating every 15 minutes; satisfying the old fixture would have meant claiming *right now* off
a stale row. **A fixture LESS capable than production hides the fix exactly as an over-capable one
hides the defect** — it never
suppressed anything, so a test asserting *this case is still reported* passes against the bug it was
written for. Each mutation was run alone and each took down exactly its own test. Weighted toward the ways a checker wrongly says "fine" — the
same reason `test_deadman.py` is. **A bug in this module is silent by construction: every other alarm
here fails loudly and gets reported, this one fails by having nothing to say, and having nothing to
say is also what a healthy day looks like.**

---

## Setup messages are ON for every bot — and a bot that cannot give them says so (2026-09-16)

**Aaron's requirement:** every bot added gets setup messages by default, and nothing about the
channel is SOS-Fade-specific. The live extreme-leg bot logged "Setup alerts: OFF" for days.

- **Why it was off:** not a setting. No bot config lists categories, and "absent" already means all
  four. The extreme-leg strategy simply never implemented the setup contract
  (`backtest/setups.py`), so the runner switched the channel off and said so only in its log.
- **Fixed at the seam:** a bot whose strategy cannot report setups now also sends ONE health message
  per start ("no setup messages … the signals room will stay silent for this bot"), so a silent
  signals room can no longer pass for a quiet market.
- **Fixed for the bot:** the extreme-leg strategy implements the contract
  (`strategies/python/extreme_leg/setups.py`; detail in that package's
  `notes/setup_alerts.md`). One thread per armed sweep, announced on the 5m shift.
- **Still without setup messages:** `b_leg`, `bos`, `realign`. Each subclasses the SOS Fade
  execution layer with the setup watch switched off, so the inherited contract answers nothing
  and is deliberately reported as unsupported. Each needs its own description of what its setup
  IS (its own confluences, key and end reasons) plus an `alert_rate.py` volume check — real work
  per strategy, not a flag. Until then, any of them started live sends the health message above.

Tests: `algos/tests/test_setup_alerts_every_bot.py` (2, both watched RED at HEAD).

---

## ✅ A trade's thread now says how it is being MANAGED, and every bot gets it (2026-09-22)

**Aaron's ask, in his words:** *"right now we are only told when we enter a trade and whether we
won or lost but nothing about break even and nothing about how the trade is being managed... if a
trade moves to break even I should get an alert saying move to break even... it should alert me all
the way of how the trade is being managed... I need that to be consistently applied as a rule of
thumb to any bots I create. So if I create a bot, I shouldn't have to go say, hey, create telegram
messages for it. It should be part of how we do work."*

**What was true before.** The trades room carried exactly two messages per trade: the fill, and the
outcome hours later. Everything in between was recorded in the decision ledger — `stop_moved`,
`partial_banked` — and the ledger is not something anyone reads on a phone. A trade could move out
of risk, trail up through a point of profit, bank half its size and add to its runner, and the
thread would say nothing at all until it closed.

**What sends them.** `live/bridge.py`, at the three seams that already wrote those ledger events:
`_sync_stop`, `_sync_partials` and `_mirror_strategy_add`. Formatters in `live/alerts.py`; every
message rendered as a phone shows it is in `notes/telegram-message-catalog.md`.

### 🔴 Why this is a RULE and not a feature

**The bridge is the one layer every bot's runner builds.** `live/runner.py` constructs exactly one
`OrderBridge` per bot whatever the strategy is, so a bot written next year inherits the whole set
with no wiring, no config key and nobody remembering to ask for it. That is what makes Aaron's
"it should be part of how we do work" true structurally rather than by discipline.

**The classification is from PRICES, never from a strategy's own stage number.** SOS Fade counts
stages 0/1/2; the other strategies do not count at all. A message keyed off a stage would be a
message ONE bot could send, and the next bot built would start silent again — the identical shape
as the extreme-leg bot logging "Setup alerts: OFF" for days in 2026-09-16. The entry price and the
two stops are facts the bridge holds for any strategy, so `alerts.stop_move_kind` already works for
a strategy nobody has written.

⚠ **Anything a strategy does that the BRIDGE cannot see is still silent**, and that is the honest
boundary of this. What the bridge sees is what it mirrors onto the broker: stop moves, banked size,
added size. A strategy that changes something internal without the broker learning about it sends
nothing, correctly — there is nothing in the account to report.

### The throttle is the feature, not a limitation of it

A structure trail ratchets on most bars a winner runs. Unthrottled, one trade would carry a dozen
near-identical messages, and `shared/notify.py`'s own docstring already names where that ends: *"a
chat that pings nine times a day for routine chatter is one you learn to ignore, and the day you
mute it you mute your fills with it."*

- A stop-move message is sent when the locked R has **improved by at least 0.5R since the last one
  was sent** — not since the last MOVE, so three 0.3R ratchets in a row do report themselves.
- **The breakeven crossing ignores the throttle and always sends.** Once per trade, it is the move
  that changes what the trade can still cost, and it is the one Aaron asked for by name.
- The pace is `trail_alert_step_r` in `live/live_config.py`. **No instance config states it and
  none should yet** — a live bot runs a frozen `deployed/` snapshot and REFUSES a key that snapshot
  has never heard of, so the default reaches every bot on its next promote with no config edit.

### Two things a restart used to lose, and no longer does

Both are optional fields on `position.json` (`live/position_state.py`), and **`VERSION` was
deliberately NOT bumped for either** — a bump reads every open trade's record as NO record, which
halts the bot holding it.

- **`alert_id`** — Telegram's id for the trade's ENTRY message. Without it the bot went on managing
  a restored trade while every message about it landed loose in the room, the exit included.
- **`broker.stop_opened`** — the stop the trade OPENED with, which is the 1R yardstick every
  stop-move message is measured against. `broker.stop` is rewritten on every ratchet, so it cannot
  serve: measuring against it would divide each later move by the distance the stop had LOCKED, the
  identical defect `risk_usd` was fixed for on 2026-09-12.

⚠ **A trade restored from a record written before 2026-09-22 has neither.** It prints no R rather
than `0.00R` (rule 1), and it gets ONE stop-move message and then goes quiet — there is no
yardstick, so there is nothing to throttle on. Transitional: every trade opened from here records
both.


### Read the thread BEFORE it ships — `tools/signal_samples.py --trades`

A live bot runs a frozen `deployed/` snapshot, so new wording does not reach a phone until a
promote — and promoting two live bots in order to look at a message is the wrong way round.

```
python C:\trading\algos\tools\signal_samples.py --trades --dry-run   # prints, sends nothing
python C:\trading\algos\tools\signal_samples.py --trades             # into the trades room
```

Three threads, 14 messages: a winner managed the whole way (breakeven → add → trail → rung banked
→ win), a loser whose stop only ever came closer, and the scratch. **Every string comes out of the
real `alerts.format_*` functions**, so what lands is byte-identical to what the bridge will send —
hand-typed samples would show wording that does not exist, which is the whole point of the tool.

⚠ **It posts into the room that carries real fills.** The header says none of it is live and the
footer closes it; both are meant to be deleted afterwards. The existing no-flag mode is unchanged
and still sends the eight SETUP threads to the signals room.

⚠ **Each send names its room LITERALLY on its own branch**, not through a variable.
`tests/test_notification_routing.py` greps every send in the repo for a stated kind, and a
variable would route correctly while being invisible to that guard — which is the same silence
the guard exists to catch, wearing a green tick.
