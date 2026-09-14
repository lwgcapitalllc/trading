# Notes — Account anchor, scale-in add path and the travelling target

The RENAME-orphans-the-account-anchor incident and its full scale-in add-path story (ratcheted stops, exits across every ticket, the bridge buying the scale-in lot, hedging), plus the target-travels-with-the-order feature and its own sub-stories, and the two G18 clocks / re-entry-switch stories lifted from Shared MT5 Architecture. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### The two clocks — `sync` and `sync_fast` (G18 stage 2, 2026-09-02)

**`sync` owns the primary's two slots and any position the PRIMARY opened. `sync_fast` owns the
re-entry's two slots and any position the RE-ENTRY opened. Neither reaches across.** The primary
is decided on 15-minute closes; the re-entry is priced and filled on the fill clock (5 minutes by
default), so one reconcile on one clock cannot serve both.

**Why the split is a rule and not tidiness — two reasons, both measured in the code:**

- **A stop belongs to the clock that computes it.** `execution.step` only writes a stop onto the
  15-minute decision while the open trade is a primary, so the 15-minute path is *already* inert
  on a re-entry's stop. The fill clock has to be equally inert on a primary's, or it ratchets to
  a value the primary's own leg has not decided yet. ⚠ **That property is guarded TWICE** — once
  where the stop is read (`_fast_decision`) and once where it is applied (`sync_fast`) — and
  MEASURED: mutating either guard alone does not redden its test. Do not weaken one and read the
  green suite as cover.
- **A hold length is an index into ONE clock's bar numbering.** `_pos_opened_bar` is stamped by
  whichever clock opened the trade, so booking a close on the other one measures its life in the
  wrong frame — and these two frames differ by 3x. `_pos_intent` records which leg opened it and
  `_observe_close` takes an `owner`, so exactly one clock books each trade.

🔴 **`sync_fast` runs the WHOLE reconcile cycle, and the reason is the cancel rather than the
placement.** The primary's limits are placed while the bot is flat — which is exactly when a
re-entry can fill. Left resting until the next 15-minute close they are a second position waiting
to happen, for up to fifteen minutes. On the fill clock that window is one fast bar.

⚠ **`_observe_open` no longer knows which order filled from the position's side alone**, because
both legs can have a limit resting on the same side. `_slot_that_filled` asks the TICKET first
and falls back to the strategy's own `entry_kind`. **Nothing depends on the ticket matching** —
where a triggered pending order carries its ticket through it settles the question outright, and
where it does not, `entry_kind` is the only other thing that knows.

⚠ **The shadow records are now a DRY-RUN report.** `secondary_shadow_fill` says *nothing was sent
to the broker*, which was true of every run while the bridge placed nothing. It places now, so on
a live bot that sentence is false — and the record would sit beside the real `trade_opened` the
bridge writes from the broker's answer, putting one trade in the book twice.

✅ **A LIVE BOT CAN REACH ALL OF IT SINCE 2026-09-02 — see *The re-entry can be switched on*
below.** A bot with the re-entry off is still handed a clock with no fast path at all, so
`sync_fast` is never called and that bot's behaviour is unchanged byte for byte.
⚠ **It has NEVER RUN against a broker.** Tests and their mutations are not a run; rule 9 stands.

⚠ **`get_pending_orders` still flattens "empty" and "unreadable" into `[]`, deliberately.** Its
callers only ask *is this ticket still there*, where a failed read costs one wasted cycle.
**Anything that ACTS on the answer uses `pending_orders_strict`, which returns `None` for "could
not ask".** The two are pinned apart by a test so they cannot quietly converge.

⚠ **A side whose placement outcome is UNKNOWN is BLOCKED, not refused** — no placement, no
cancel, nothing, until a sweep manages to read the book. It is not a latch: one readable bar
clears it, or a single bad minute would stop the bot trading for good.

**Tests: 13 in `tests/test_order_reconciliation.py` (bridge) and 9 in `tests/test_mt5_ops_pending.py`
(broker layer). Ten mutations watched RED**, including both directions of rule 4 — count our own
recorded order and the bot refuses its own re-size; exclude by magic and the incident returns.

🔴 **Two of the fixtures were lying, and both were found by the new code rather than by a test.**
The bridge's broker fake carried an order as resting AND filled at once, which MT5 cannot do — a
triggered order leaves the book for good and comes back as a position under the same ticket. And
its `cancel_pending` could only ever answer True, **which is exactly why a discarded cancel result
went unnoticed for as long as it did: no test could produce an answer worth keeping.** ⚠ **A fake
that cannot produce a failure mode is a fake that certifies the code against a system you do not
have.**

⚠ **One test in the new file names NO mutation on purpose and says so.** Its fake returns the
failure directly and never reaches the broker layer, so mutating the reconciliation does not turn
it red — the sweep saves it instead. **A test naming the wrong mutation is worse than one naming
none: it reports coverage that is not there.** The first draft did exactly that and it was only
caught by running the mutation.

### The re-entry can be switched on (G18 stage 3, 2026-09-02)

**`assert_supported` no longer refuses the re-entry.** Its two stated grounds — no second bar
stream, no path that places the re-entry's order — both stopped being true, so the refusal went.
⚠ **A refusal is retired when the capability it stood in for EXISTS, never to get a bot started.**
That is the only test it has to pass, and it is why the force-close on an opposite structure
break and the add-to-a-winner path are still refused.

🔴 **WHAT REPLACES IT ASKS A DIFFERENT QUESTION, AND MISSING THAT IS HOW THE LIFT NEARLY LEFT A
SILENT HOLE.** The setting is mirrorable now, so it is no longer a reason to refuse. What still is:
a configuration asking for a re-entry the runner will never deliver. **The runner builds the second
feed by ASKING THE STRATEGY, not by reading the setting** — `algos/live/` holds no trading logic
and does not know what a re-entry is — so a strategy that answers *no fill clock* while its config
says *re-enter* got no second stream, and the bot would have started, traded the primary alone and
re-entered never, with nothing in any log. `bridge.assert_secondary_wired` refuses that.

⚠ **`None` from the strategy means two things and only the config beside it can separate them** —
*declines a second feed* and *cannot offer one*. Rule 1 says do not destroy that distinction at
the bottom; here it is reconstructed at the top, in the one place that holds both facts.

⚠ **The merge half is NOT gated on the re-entry setting, and gating it was the near-miss.** A
strategy can want a fast feed for another reason; what it may never do is want one and provide no
merge rule. Two questions, deliberately different: *did the config order something the strategy
cannot supply*, and *did the strategy order something it cannot itself handle*.

⚠ **ONE function, asked by the runner and by `promote.py --dry-run`.** The preview cannot import
the strategy (the staged snapshot carries no `algos/` tree) so it passes shipped VALUES — the
`feed.fast_feed_timeframe` shape, for the same reason: a copy in the promote tool drifts the first
time either moves. **The preview's own version had a hole the runner's did not** — it ran its
merge check only when a fill clock existed — and that is what one shared function ends.

🔴 **A RESTART PUT A RESTORED RE-ENTRY ON THE WRONG CLOCK, and it was found by asking what stage 3
made reachable rather than by a test.** Which leg owns a trade is stamped at the FILL and defaults
to the primary, so a restart holding a re-entry picked it up as a primary: the 15-minute clock
would have ratcheted its stop and booked its close, in a bar frame 3x the one that opened it. The
emulator was never the problem — it restores that field from the record and refuses an incomplete
one. **The bridge simply did not ask.** ⚠ **The generalisation is worth more than the fix: lifting
a refusal makes a whole region of state reachable for the first time, so the question to ask is
not "does the new path work" but "what defaults has nothing ever exercised".**

⚠ **Nothing here has run against a broker. Rule 9 stands** — and the first one to watch is a
re-entry ORDER, not a re-entry decision; the decision half has been shadow-recorded since stage 1.

✅ **AND "WATCH IT" IS NOT A PLAN, SO IT IS A TOOL: `tools/audit_reentry.py`** (Aaron's call,
2026-09-02 — *"I'm not gonna go check that. You check it."*). It reads the bot's own decision
ledger and grades ONE trade against the settings it was supposed to follow: size, stop side, stop
ratchet direction, banking against the configured rungs, the exit reason, R recomputed from the
prices rather than read back, and whether the costs were recorded at all.
🔴 **Its three-verdict design is the whole point: a check that cannot run reports NOT CHECKED,
never PASS.** The failure being guarded against is a clean report on a trade nobody verified, and
this repo has already shipped one — `check_tradingbox.py` certified two tools that had NEVER
worked, because every case asserted what a tool REFUSES and a tool that always fails passes those
beautifully. So every check here is driven BOTH ways in `tests/test_audit_reentry.py`, and the
whole set was watched red by one mutation that makes the tool incapable of failing anything.
⚠ **It grades against TODAY'S config**, so a setting that moved between the trade and the audit
makes the comparison wrong with no symptom — pass `--config` an older copy.
⚠ **Exit 2 means NOTHING TO AUDIT**, deliberately not 0: *nothing to check* and *everything
passed* must not be the same answer.

🔴 **IT READ THE LEDGER TWICE FOR ITS FIRST DAY, AND THE CAUSE IS A RULE ABOUT THE SYNC RATHER THAN
ABOUT THIS TOOL (fixed 2026-09-03).** It reads two roots on purpose — the committed archive for
history, the bot's own directory for what closed an hour ago — and `ledger_sync.py` **COPIES** a day
into the archive rather than moving it. So every synced day existed in both places and all of its
rows were loaded twice: MEASURED on the trading box, 25 files in both roots, **2,177 of 4,865 rows
duplicated**. ⚠ **The trade records survived it and the EVENT rows did not** — a stop that ratcheted
eleven times would have been reported as twenty-two, in a message written to be trusted, and the
watcher's health record over-counted the ledger by nearly half. ✅ One file per day now, keyed on the
DAY, and **the live copy wins because the archive is only a snapshot** — preferring it would silently
drop everything since the last sync, which is exactly the trade somebody is asking about. ⚠ **A day
that exists only in the archive is still read**; de-duplicating must not become *only read the live
directory*. **The standing point: when one writer COPIES into a second location, every reader of both
is now responsible for the overlap — and the symptom is a doubled count, which reads as a fact.**
Three tests in `test_audit_reentry.py`, each watched RED under its own mutation.

🔴 **BUILDING IT FOUND TWO DEFECTS IN THE RECORD IT READS, AND THAT IS THE PART WORTH KEEPING.**
The trade record could not tell a re-entry from a primary — one field, missing, in the only file
meant to answer *what did this bot do* — and the risk it recorded was the PRIMARY's percentage for
a trade sized at half of it, in the ledger AND in the Telegram message a person reads. Both had
been "obviously fine" for as long as one leg existed. **A record is only as good as the question
somebody actually puts to it; nobody had put one.** The fix records the leg on both halves of a
trade, and records the risk MEASURED off the position the broker really opened (`risk_usd`,
`risk_pct_realised`) beside the setting that was asked for — rule 3, and the measurement is the
half that can catch a sizing bug. ⚠ **`risk_pct_realised` is `None` when the balance could not be
read**, never 0 and never the setting.
⚠ **A test double hid the second half of this**: every bridge test records the kwargs it was
handed, so hardcoding the leg inside the ledger's own writer reddened nothing. `test_ledger_streams.py`
now drives the REAL writer to a real file. **Passed in and written out are two claims, and only
the second is what an audit reads.**

✅ **AND `SYS_REENTRYWATCH` IS WHAT NOTICES (2026-09-03).** `tools/watch_reentry.py`, hourly on the
box beside the other watchdogs. It imports the audit rather than restating it, and reports TWICE
per trade — on the open and on the close — because the exit reason, R against the prices and the
costs cannot be answered while a position is still on, so one message at the open would file a
verdict on the half that had happened.
🔴 **IT REPLACED A WATCH THAT LIVED INSIDE ONE CLAUDE SESSION**, which is to say a watch that died
when a window closed and would have gone on reading as armed. **A durable job is not a nicety here
— the thing being watched for happens once.**
🔴 **ITS NORMAL STATE IS SILENCE, AND THAT IS THE HAZARD THE DESIGN IS BUILT AROUND.** Most days
there is no re-entry, so a working watcher and a dead one look identical for weeks. Three things
follow, and none is optional: it **announces its own failure** rather than dying into a log; it
writes a health-ledger record on **every** run including the quiet ones, so a GAP in that file is
the evidence exactly as `pulse` is; and it sends **nothing** on a quiet run, because an hourly
message nobody needs is how a channel gets muted before the day it matters.
⚠ **A corrupt state file reads as *nothing reported yet*, deliberately.** The two failure
directions are not equal — a repeat message is an annoyance, and treating an unreadable file as
*all reported* swallows the one message the tool exists to send.
⚠ **14 tests, each driving a path that is invisible in ordinary operation**, and one of them was a
docstring with no body for about a minute — passing for free while its name claimed the case was
covered. **Worse than no test.** Mutations watched red, including the one that stops it announcing
its own failure.

## 🔴 A RENAME orphans the account anchor, and the symptom is a confident 0.0% (2026-09-05)

`ensure_starting_balance` re-anchors on the ACCOUNT changing and never on the balance moving —
which is right, and which cannot see a bot key changing under it. The 2026-09-03 de-brand
(`mpc_sos_fade_demo` → `sos_fade_demo`) created a NEW state entry with no anchor, so the next
heartbeat anchored it at the balance the account had already grown to.

**MEASURED 2026-09-05:** the retired entry still held `starting_balance 9996.99`, `total_pnl_pct
45.43` for account **700152905**; the live entry held `starting_balance 14538.88`, `total_pnl_pct
**0.0**` on the same account, same magic **770115**. The account was up **$4,541.89 / 45.4%** and
every screen reading that field said flat. **Nothing errored, no test went red, and the number is
the most reassuring one available.**

✅ **REPAIRED by ADOPTING the retired identity's anchor** — same bot, same account, same magic,
documented in `ledger_archive/sos_fade_demo/RENAMED.md`. Written through `bot_state.write_bot` so
it took the same atomic-publish path the runner uses, and CONFIRMED by the bot's own next
heartbeat recomputing **45.43**. That is exactly what the field's own *"adopt, do not reset"* rule
does for a pre-field anchor; the rule simply has no way to fire across a key change.

⚠ **The write was safe to make on a running bot because `total_pnl_pct` and `starting_balance`
are REPORTING ONLY** — CHECKED rather than assumed: `runner.py` writes them, `telegram_bot.py` and
the Bots page read them, and no sizing, entry or exit path reads either. Do not extend this
precedent to a field a trade decides on.

🔴 **THE GENERAL RULE: renaming a bot key silently discards every per-key measurement that has no
other home.** The ledger survived because it is found by PATH and the folder was moved with it.
The anchor did not, because it lives inside a state file keyed by name. **Before a rename, list
what is keyed on the old name and carry each one across in the same change** — and prefer keying a
measurement on the thing that does not move, which here is the account number and the magic.

✅ **A GUARD LANDED 2026-09-05: `bot_state.suspect_anchors`.** When a bot writes a FRESH anchor it
scans its own instance file for any other entry — retired keys included, which is the whole point —
already anchoring the SAME account at a DIFFERENT balance, and records them under
`starting_balance_suspect` beside the number it just wrote.

🔴 **IT REPORTS AND DOES NOT ADOPT, and that is the design rather than a shortcut.** A rename and
an ordinary second bot joining a grown account are **the same signature**: the extreme leg joined
700152905 on 2026-09-04 and its `14538.88` is CORRECT, so adopting `9996.99` there would credit a
bot that has never traded with 45% of somebody else's growth. **Two causes, one signature; guessing
between them fabricates a percentage** — so it raises the question and a person answers it, which
is this file's own rule that a guard firing is a QUESTION, not an answer.

⚠ **It is scoped three ways, each because the unscoped version is noise.** Only the SAME account
(another account's opening says nothing about this one); only a DIFFERENT value (two bots arriving
at one balance is the ordinary case, and flagging it fires on every second bot ever added); and
only on a FRESH anchor (the flag is a fact about the moment the number was written, so re-deciding
it every poll would raise it the first time any neighbour anchors differently).

✅ **IT IS AN ALARM SINCE 2026-09-06 — `log_review._suspect_anchor` reads it.** This paragraph said
*"today this guard is a record, not an alarm"* for a day, which is the honest version of a gap and
still a gap: **a guard whose finding reaches nobody fires into an empty room, and that is worth less
than no guard, because the next reader takes the silence for a checked account.** It now reaches
Telegram once per occurrence and stands as a chip on the Bots page until it is dealt with.

🔴 **IT REPORTS THE QUESTION AND NEVER A VERDICT, for the same reason the guard adopts nothing.**
A rename and an ordinary second bot joining a grown account are the SAME signature, and the second
is CORRECT — so a message reading *this is wrong* would send somebody to break a good number. It
names both readings and says which action each calls for.

⚠ **The key carries both figures, so a re-anchor at a DIFFERENT value announces itself again.**
Keying on the bot alone reports the first orphaning and then stays silent through every later one —
the de-duplicating-alerter bug `log_review.Finding` already warns about in its own docstring.

⚠ **Raised for a STOPPED bot too, and BEFORE the health record is read.** It is a fact about the
state file rather than about the record, so the *do not cry wolf over a deliberately stopped bot*
rule does not apply — the number is wrong on screen either way — and `review_bot` returns early when
the record cannot be read, which would otherwise swallow it for exactly the bot most worth a look.

✅ **11 tests in `algos/tests/test_log_review.py`, 9/9 mutations RUN and every one red.** 🔴 **One
survived first and the fix is the lesson: the *a stopped bot still reports it* test called the
helper DIRECTLY, so a gate added in the CALLER could not fail it.** It drives `review_bot` now.
**A test aimed one layer below the thing it names is green against its own defect.**

✅ 5 tests in `algos/tests/test_starting_balance_anchor.py`, **5/5 mutations RUN and every one
red** — including both directions of the report-don't-adopt rule.

### 🔴 …and until 2026-09-07 that refusal had NO TEST, while the shipped default started tripping it

Two things landed together, and the second is the finding.

**The refusal is now pinned** (`test_live_bridge.py` →
`test_SCALE_IN_is_refused_because_the_bridge_has_no_second_entry`). It had none for three weeks:
the rule that stops a bot trading a base position while the backtest shows a scaled book rested on
nobody deleting it. Watched RED by mutation — disabling the branch reddens it.

🔴 **`SosFadeConfig.exec_scale_in` moved off → on on 2026-09-06, so the strategy's OWN defaults now
describe a mode this bridge refuses.** `test_dual_feed_merge.py` →
`test_the_REAL_shipped_strategy_config_cannot_go_live_until_scale_in_is_turned_off` states that as
a pin rather than leaving it to be rediscovered: build the real config, assert it is refused, and
assert that turning the one setting off makes it supported. ⚠ **It is meant to go red when the
default moves back, or when the bridge learns to place an add** — either is a change somebody has
to come here and re-state.

✅ **THE LIVE BOT IS UNAFFECTED, AND THE REASON IS THE 2026-08-26 PINNING.** `sos_fade_demo`'s
instance config **STATES** `exec_scale_in: false` rather than inheriting it, which is exactly the
hazard those 53 pinned settings were written against — *a setting the config does not state takes
whatever the CODE defaults to, so a future version can move a default and change what this bot
trades with nothing anywhere announcing it.* That is the first time the pinning has actually paid.
⚠ `extreme_leg_demo` has no such field (its config class is standalone, not a SOS Fade subclass).
⚠ **`b_leg_demo` does NOT state it and therefore inherits ON** — it is benched, so nothing is
trading, but as configured it would be refused at startup. Pin it before arming it.

🔴 **A test NAMED for a subject it does not build is how this went unseen.**
`test_the_shipped_config_is_supported` asserted on a four-field stub, so it stayed green through a
default change that made the real shipped config unsupported. It is
`test_a_minimal_mirrorable_config_is_supported` now, and the real one is built by the two pins
above. **The stub answers only the questions the test thought to ask.**

### 🔴 A dumped config is complete only on the DAY it is dumped — `b_leg_demo` was 57 fields short (2026-09-07)

An instance config states what a bot trades. `b_leg_demo`'s was **dumped from its strategy
dataclass on 2026-08-09 rather than transcribed**, which is the right method and the file's own
note said so: *"a hand-copied set is how a live bot ends up trading a value nobody chose."*

🔴 **The method was right and the artefact still rotted, because a dump is a SNAPSHOT and the
dataclass kept growing.** 57 fields were added after that date, and every one of them resolved to
whatever the dataclass defaulted to on the day somebody armed the bot. **The note went on saying
"Every field of `BLegConfig` … DUMPED" throughout, so the file asserted a completeness it had
quietly lost, and nothing could fail.**

🔴 **THE ONE THAT BIT: the add-size setting arrived 2026-08-16 and its default moved off → on on
2026-09-06.** Arming this bot would have started it scaling in — a behaviour never measured on
B-LEG, and one its Pine parity gate **cannot** check, because the B-LEG export scheme has no
column for it. It is pinned **off** now, which is the only value in the re-dump that is not simply
the current default.

⚠ **The next one was already queued**: the recovery feature is unpinned too and is inert today
*only because its default is still False*. That is the same sentence this incident is made of.

✅ **Every setting is pinned now on all three bots** — checked, not assumed: `sos_fade_demo`
116/116, `extreme_leg_demo` 26/26, `b_leg_demo` 117/117, with zero undeclared keys anywhere.
`sos_fade_demo` was already complete because it was pinned deliberately on 2026-08-26 against
exactly this hazard; **B-LEG was the bot nobody was watching, which is the point — the bench is
precisely where drift accumulates unseen.**

⚠ **Nothing already-pinned was touched, and that was verified semantically rather than by reading
a diff**: all 60 previous values compare equal to `HEAD`, and of the 57 added, exactly one differs
from its dataclass default. **A pin equal to the default changes nothing, which is why pinning
everything is cheap** — the cost of pinning is one line per setting; the cost of not pinning is
that a default somebody else moves becomes a live behaviour change nobody decided.

✅ **`test_every_bot_pins_every_setting_its_strategy_declares` (`tests/test_bot_bench.py`) now
enforces it, and it reads each bot's OWN declared strategy rather than a hardcoded list** — so a
bot added tomorrow is covered without editing the test, and a benched bot is checked too. It
asserts both directions: an unstated field (drift), and an undeclared key (which the runner
refuses at startup, so that one is a bot that will not boot). **Watched RED both ways** — removing
the add-size pin, and adding a made-up key.

⚠ **The standing rule: re-dump and DIFF before assigning any bot.** A field that appears in that
diff carrying a default nobody chose is this failure, caught at the one moment it is free.

### 🔴 A snapshot carries what the package imports — INCLUDING a new TOP-LEVEL package (2026-09-07)

**`sos_fade/execution.py` gained `from execution.intents import ...` at module scope, and
`repo_trees` did not copy it — so every promote failed with `ModuleNotFoundError: No module named
'execution'`.** No bot could be deployed for the hours it was missing.

✅ **The safety net held and is worth naming: `verify` refused, and a failed verify leaves the
running bot untouched.** Nothing live was harmed; the two armed bots kept trading their frozen
snapshots throughout. **A promote that cannot import is exactly what that subprocess exists to
catch, and it caught it.**

🔴 **THE 2026-09-04 FIX DOES NOT COVER THIS, AND THE DIFFERENCE IS THE FINDING.**
`package_deps.local_dependencies` walks imports rooted at `strategies/python`, so it sees a
strategy borrowing a SIBLING and is structurally blind to one borrowing a new TOP-LEVEL package.
`engines/` and `backtest/` are hardcoded for the same reason and always have been: they are
universal, so there is nothing per-bot to derive. **A derived list is only derived within its own
root.**

⚠ **THE RULE: a new top-level package a strategy imports goes in `repo_trees` in the SAME change.**
Nothing derives it and nothing will tell you — except a promote, which is the last place to find
out.

🔴 **IT WAS MISSED BECAUSE THE STRATEGY SUITES WERE RUN AND THIS ONE WAS NOT.** 898 strategy tests
were green while the deploy was broken. **The suite that fails is the one for the subsystem you did
not think you had touched** — a strategy import is an `algos/` fact.

### 🔴 …and the test guarding this could not see the half that mattered

`test_the_counted_trees_ARE_the_trees_promote_copies` **never read the counting side.** It pinned
the copier's own list against a literal, so `promote.repo_trees` and the Command Center's
`bot_versions._SHARED_TREES` could disagree with it green — and they nearly did today, which would
have deployed a tree the Configure tab does not count. **That is the promoted-but-not-counted
failure the module's own docstring warns about, with the guard pointing the wrong way.**

⚠ **Only the STRATEGY half of the two shares a resolver.** The shared trees are a hand-mirrored
tuple in another package, and the docstring's *"calls the SAME resolver"* is true of one half and
was read as true of both.

✅ Split in two: a PIN on the copier's roster (re-stated on purpose when a tree is added), and a
real cross-check that PARSES the other package's tuple — parsed, not imported, because it lives in
a venv that pulls in FastAPI and wiring two trees together to read a tuple of strings is worse.
**It refuses on an empty parse**, or a renamed tuple would compare equal to nothing and pass.
**Three mutations RUN and all red**: either side dropping the tree, and the tuple made unparseable.

⚠ **The pin covers what SHIPS, never what is HASHED.** `LiveConfig.source_roots` still hashes three
roots, so `execution/` now deploys and is not pinned — the same stated gap the 2026-09-04 entry
records for borrowed packages, one tree wider. Unchanged by this work and still open.

### The live bot's two settings moved to the shipped defaults (2026-09-07)

`sos_fade_demo` — **re-entry trigger `FVG in zone` → `FVG in zone + Reclaim Entry`**, and
**`exec_sl_deep` ON → OFF**. Aaron's call, both confirmed against their measurements first. The
evidence, the warnings and what does NOT change are in that bot's own `config.json`
(`_reclaim_trigger_on_2026_09_07`, `_exec_sl_deep`) — **not restated here**, because a second copy
of a decision is how two files come to disagree.

🔴 **THE DEEP-STOP CHANGE REVERSES AARON'S OWN 2026-08-15 DECISION AND THE OLD REASONING IS KEPT
RATHER THAN OVERWRITTEN.** It was a deliberate trade of return for a smaller ride, not a mistake:
+140.0R at 45.6% drawdown against +117.0R at 41.1%. **The deciding number was already in that
file** — re-levered to equal drawdown it returns 3,830x against 4,868x, so the drawdown it bought
could have been bought more cheaply on the risk dial. **A toggle that is worse at matched drawdown
is not a drawdown tool.** ⚠ This gives back ~4.5 points of drawdown at the current risk setting.

🔴 **THE TRIGGER CHANGE MOVES THIS BOT ONTO AN ORDER PATH NOTHING HAS EVER RUN.** Until today it
banked **nothing** at a price — its three banking percentages are all 0 — so every trade rode its
stop and the bridge's partial-bank and full-exit paths stayed unproven, as that config said in as
many words. **The reclaim banks 100% at its first target, which is a full exit at a price.** Rule 9
applies to the first one; watch it.

⚠ **Neither field is runtime-reloadable, so the bot keeps trading the old rules until RESTARTED**
and reports one blocked-config message meanwhile. ⚠ **PARAM changes, not code: no promote is needed
and none should be run for them.** ⚠ **The add-size setting is still REFUSED at startup**, so the
stack this is being matched to cannot be fully mirrored until the bridge has an add path.

### 🔴 The bridge would have BANKED AWAY every scale-in lot, and the checklist found it (2026-09-07)

**`_intended_open_lots` fed `_sync_partials`, which closes the difference between what the broker
holds and what the strategy still wants. It counted `_qty` alone.**

🔴 **`_qty` NEVER CONTAINED THE ADDS.** It is assigned in exactly three places — zero, the base
entry fill, and the reset — and **no line anywhere adds a scale-in lot to it.** Adds live in
`_adds`, their own ledger, which is why `_charge_swap` already adds them as a separate term. **The
docstring claimed the opposite in as many words**, and had done since it was written.

🔴 **THE CONSEQUENCE: with scale-in on, the bridge would have CLOSED EVERY ADD moments after
buying it** — understating the position by exactly the add size, banking the difference, and
leaving both sides' own checks passing. MEASURED as the mutation: 0.5 wanted against 1.5 held
closes 1.0, which is the add.

⚠ **It was inert only because `assert_supported` refuses scale-in**, so the ledger is always empty
on a live bot. **It becomes reachable the moment that refusal is retired — which is the entire
point of the add path.** ⚠ **Nothing was ever going to go red**: no test scaled in, because the
feature is refused. **It was found by working the `/live-safety` checklist before writing code,
which is the one thing that would have found it.**

⚠ **A wrong answer here is destructive in ONE direction only.** Too small closes real size; too
large banks nothing and halts loudly on the next disagreement. **The asymmetry is why this is
arithmetic rather than a judgement.**

⚠ **An absent ledger is CANNOT ASK, never *no adds*** — the function's own `None` contract already
says a strategy this bridge cannot interrogate must stop it acting rather than licence it to close
everything.

🔴 **THE TEST DOUBLE DID NOT HAVE THE LEDGER AT ALL, AND THAT IS RULE 13 EXACTLY.** The real
`Execution` sets `_adds = []` in its constructor, so a fake without it models a strategy that does
not exist — survivable only while the bridge read `_qty` alone. **The fixture was fixed, not the
bridge loosened.**

**Tests: 3 in `test_live_bridge.py`, each watched RED under its own mutation — and the first
mutation IS the behaviour at HEAD**, so this is a real defect watched red rather than a test
written to pass. Counting lot COUNT instead of size, and reading a missing ledger as empty, redden
their own named tests.

### 🔴 The account is HEDGING, and nothing in the repo had ever recorded that (2026-09-07)

**MEASURED on the live terminal, `broker_facts.py --bot sos_fade_demo --sample 0`: PU Prime demo
700152905 reports `margin_mode 2` — RETAIL HEDGING.** Volume band 0.01–100.00, step 0.01, contract
100 oz.

🔴 **IT DECIDES THE WHOLE SHAPE OF AN ADD AND IT WAS AN ASSUMPTION NOBODY HAD WRITTEN DOWN.** On a
NETTING account a second buy merges into one position and the venue's own stop covers the combined
volume. On a HEDGING account **every add is a SEPARATE POSITION with its own ticket and its own
stop** — so the add path is not *place one more order*, it is *the bridge stops holding one
position*.

🔴 **`_agrees` HALTS ON MORE THAN ONE POSITION TODAY** — *"this strategy takes one at a time"* —
so on this account the halt fires the instant an add fills. **That halt is correct for every
configuration that exists now**, and retiring the scale-in refusal without changing it would take
a bot down on its first scaled trade.

⚠ **What the add path therefore needs, and it is more than an order call**: a placement route for
the add, an agreement check that compares total VOLUME rather than counting positions, a stop
ratchet that moves EVERY ticket rather than one, and exits that close across tickets. **The
refusal comes off last, when the capability it stands in for exists — never to get a bot started.**

⚠ **Re-measure `margin_mode` before assuming this of any other account.** It is a property of the
account, not of the broker, and this repo has already twice quoted one account's readings for
another.

### The agreement check can now tell a SCALED TRADE from a duplicate-order incident (2026-09-07)

`_agrees` halted on more than one position outright. On a hedging account that is the same
observable state as a legitimate scale-in, so the count alone cannot separate them — and the halt
it must keep producing is the 2026-08-25 incident, five copies of one limit filling inside 69
milliseconds.

🔴 **THE DEFAULT IS REFUSAL AND `_why_not_scaled` IS WRITTEN THAT WAY ROUND.** It returns a
SENTENCE unless it can positively establish a scaled trade, so a state nobody anticipated halts
rather than being waved through as an add. **A permission written as *"halt unless X"* lets every
unimagined case through; this one is *"refuse unless all of these hold"*.**

⚠ **Three causes, three sentences, because they call for different work**: a strategy holding no
adds is a duplicate-order incident; an unreadable ledger is a strategy this bridge cannot
interrogate; a position on the other side is a hedge nobody asked for. **A test asserts all three
render differently** — this file has already paid for two failures sharing one message.

⚠ **`None` from the ledger REFUSES** (rule 1). *Could not ask* may not buy the permissive answer,
because that is precisely how a duplicate-order incident would be read as a scale-in.

⚠ **Behaviour is UNCHANGED for every configuration that exists today** — no bot can scale in, so
the ledger is always empty and the refusal fires exactly as before, with a clearer sentence.

🔴 **THE MULTI-POSITION HALT HAD NO TEST AT ALL, AND THE WHOLE SUITE STAYED GREEN WHILE IT WAS
REWRITTEN.** 150 tests passed on the rewrite before a single one of them was about it. **The check
that catches this repo's most expensive order incident was resting on nobody deleting it** — the
same shape as the scale-in refusal, which had no test for three weeks. **When you touch a halt,
ask what covers it before you trust the green.**

**Tests: 5 in `test_live_bridge.py`, 4 mutations RUN and every one red**, with every test killed by
at least one — permitting N positions unconditionally, refusing them unconditionally, reading a
missing ledger as empty, and dropping the side check. ⚠ **The first two are COARSE by nature and
are labelled so**: they break every refusal at once and prove no single claim. The ledger and side
checks are the ones killed precisely.

⚠ **This is one piece of four.** The placement route, the stop ratchet across every ticket and the
exits across tickets are still missing, and **the scale-in refusal stays up until they exist** —
retired when the capability is real, never to get a bot started.

### Every scale-in lot's stop is ratcheted, and it is a RECONCILIATION (2026-09-07, add path 2/4)

On a hedging account each add is its own position with its own stop, so the existing ratchet
protects the BASE alone. Without this, every add rides its original stop for the life of the trade
— **under-protected, silently, while the base's own record reads perfectly correct.**

🔴 **`_sync_add_stops` DERIVES the lots from the broker each bar rather than remembering them, and
that is the load-bearing choice.** A tracked list would be EMPTY after a restart while the broker
still held the adds — so their stops would never move again, and nothing would say so, because the
base's record would still be right. **Same shape as `_sync_partials`, for the same reason.**

🔴 **EACH LOT IS COMPARED AGAINST ITS OWN STOP, NEVER THE BASE'S RECORDED ONE.** Gating the loop on
*the base moved this bar* is how an add that filled at a moment the stop was still keeps its
original stop for the whole trade: the base is already correct, the outer check returns early, and
the lot is never looked at. **That case has its own test, and it is the one that makes this a
reconciliation rather than an event.**

⚠ **A FAILED move is ALERTED and RECORDED, never retried into a log.** The strategy goes on
managing size whose broker stop is further away than it believes — the one direction that costs
money — and an add whose stop simply never moves is indistinguishable from a trade with nothing to
ratchet (rule 1).

⚠ **An absent position list is CANNOT ASK: nothing is moved and nothing is claimed.** Reading it as
*there are no adds* is the same collapse rule 1 exists to prevent, and every caller that has the
list passes it.

⚠ **Behaviour is UNCHANGED with no adds** — the loop has nothing to iterate, and the base's path is
byte-identical to before.

🔴 **THE FAKE BROKER'S STOP MOVE COULD ONLY EVER SUCCEED**, so the failure branch was unreachable
by any test. It can refuse per-ticket now — one lot failing while another succeeds is the case that
matters, and a single global flag could not express it. **A fixture that cannot fail the way
production fails certifies the code against a system you do not have** — the third time this file
has recorded that shape.

🔴 **THE EVENT ROUTING GUARD CAUGHT THE NEW RECORD, WHICH IS THE GUARD EARNING ITS KEEP.** An
unclassified event falls into the health stream and reads as a process fault. It is a DECISION by
the same reasoning as `partial_refused` and `secondary_stop_unreadable`: it says why a live trade
will not match its backtest, so it belongs beside the trade.

**Tests: 5 in `test_live_bridge.py`, 5 mutations RUN and every one red, with every test — the
success CONTROL included — killed by at least one.** ⚠ **The control needed its own mutation
(alert on every move) and would otherwise have been decoration**: it survived all four of the
others, which is exactly what a case that cannot fail looks like.

### Exits close across EVERY ticket, and a banked add is reconciled (2026-09-08, add path 3/4)

On a hedging account the strategy exits ONE position and the broker holds several. Two sites had
to learn that, and they are different questions.

**1. A commanded exit sweeps the adds.** `_mirror_strategy_exit` closed `_pos_ticket` alone, so a
time stop, a target taking the lot or an operator's close left every scale-in lot live, unmanaged,
with nothing but its own stop. 🔴 **The sweep runs BEFORE the "base already gone" early return** —
put after it, the whole sweep is skipped in exactly the case that strands them, a base that filled
its own stop in the same instant with the adds still open.

**2. A banked add is CLOSED by reconciliation.** `_bank_adds` closes every open add lot in one step
and leaves the base; nothing on the live side could mirror that, because every other exit path
knows only the base ticket. `_sync_add_size` asks how many add units the strategy still holds and
closes what is over — so a bank missed by a restart, a dropped link or a skipped bar is taken on
the next sync, and one already done is a no-op.

🔴 **IT RUNS AFTER `_observe_open` AND BEFORE `_agrees`, AND BOTH HALVES ARE LOAD-BEARING — the
first ordering shipped was wrong and the tests caught it.** After the adoption, because an add is
defined as *a position under our magic that is not the base*, and with no base adopted yet there is
nothing for it to be "not". Before the agreement check, because banked adds leave the emulator
holding a bare base against N broker positions, which `_agrees` reads as orders nobody intended and
halts on — the bot would have halted on a state it caused itself.

🔴 **THE 2026-09-07 SIZE FIX WAS A MIS-FIX IN THE OTHER DIRECTION AND IS CORRECTED HERE, ALSO
BEFORE IT COULD FIRE.** It added the open add units to `_intended_open_lots`. But `_sync_partials`
compares that against the BASE TICKET'S OWN VOLUME, and on a hedging account the adds are not in
that number — so the sum was always larger than what it was compared against, the difference always
negative, and **the reconciliation would have banked NOTHING for the whole life of any scaled
trade**, silently riding every rung the strategy took off in its own book. It is base-to-base now,
with the add tickets answered separately.

⚠ **The rule worth more than either fix: a quantity is only additive with another when both are
measured over the SAME set of tickets.** The defect being guarded against — adds counted as excess
and closed — is real, and it belongs to a NETTING account.

🔴 **THE FIXTURE MODELLED THE WRONG BROKER, AND PRODUCTION WAS CHANGED TO AGREE WITH IT.** The
piece-2 test put a 1.0 add INSIDE the base ticket — one position of 1.5 lots, which is netting.
**Rule 13 with the sign flipped: a fixture LESS capable than production hides just as much**, because
one position cannot express the thing every check here turns on, which is *which ticket a lot
belongs to*. Every test written against it was answering an easier question than the live one.

⚠ **A PARTIAL bank is REFUSED rather than guessed at** (rule 9). The strategy banks its adds
all-or-nothing, so a broker holding more than zero and less than it should is a state nothing
produces. Closing whole tickets toward it would mean inventing a policy — which lot, and why that
one — and picking wrong books the wrong lot's P&L with nothing in the output to say so.

⚠ **A REFUSED close NAMES ITSELF in the halt** (`_add_close_failed`, read first by
`_why_not_scaled`). Without it that state falls through to the *duplicate placements* sentence,
which sends the reader hunting an order-placement bug the bridge has already recorded the broker
refusing. ⚠ **It is not cleared on a later bar** — the lot is still open until somebody closes it.

⚠ **When a lot refuses, the BASE IS LEFT OPEN.** Closing it would strand the leg whose stop this
bridge is no longer ratcheting, which is the more dangerous half; `_agrees` halts either way.

⚠ **Three new ledger events, all DECISIONS** (`add_closed`, `add_close_failed`,
`add_partial_bank`) — they answer *what happened to this trade's size*, never *is the machinery
working*. Per-lot price and P&L are written separately because a netted figure cannot be taken
apart afterwards.

⚠ **Behaviour is UNCHANGED with no adds** — every new path returns early, and the base's route is
byte-identical to before.

🔴 **`mt5_ops.hedging_account` MEASURES THE PREMISE ALL OF THIS RESTS ON, AND NOTHING READS IT
YET — a stated gap, not an oversight.** It answers `None` for *cannot ask* (rule 1: `False` would
refuse a scale-in on an account that would take it, `True` would run the add path against a book
whose volumes do not mean what it thinks). **It is wired beside the retirement of the scale-in
refusal**, which is the moment any of this becomes reachable; wiring it earlier is a check on a
path no bot can enter.

**Tests: 8 new in `test_live_bridge.py`, 4 in `test_mt5_ops_pending.py`. 13 mutations RUN and every
one RED on its own named test**, including a CONTROL that closing every extra ticket
unconditionally reddens the never-bank-away case. ⚠ **The harness asserts each test was SELECTED
and green at baseline before mutating** — a `-k` filter that matches nothing reads exactly like a
vacuous test, which this file has already recorded once.

⚠ **The fake broker's close could only ever fail ALL-OR-NOTHING**, so the case that matters — one
lot refusing while another succeeds — was unreachable. It refuses per-ticket now, the same fix
`move_sl` needed in piece 2. **Fourth time this file has recorded a fixture that cannot fail the
way production fails.**

⚠ **This is three pieces of four. The placement route that actually BUYS the add is still missing,
so the scale-in refusal stays up** — retired when the capability is real, never to get a bot
started.

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9** — and no bot can reach any of it today.

### The bridge BUYS the scale-in lot, and the refusal is retired (2026-09-08, add path 4/4)

**`_mirror_strategy_add` places the add at market, on the bar the strategy bought it.** With the
placement route, the stop ratchet across every ticket, the exits across tickets and an agreement
check that can tell a scaled trade from duplicate orders, the capability the blanket refusal stood
in for exists — so `assert_supported` no longer refuses `exec_scale_in`. **A refusal is retired
when the thing it refuses can be done, never to get a bot started.**

🔴 **IT IS THE FIRST CONSUMER OF THE ORDER-INTENT STREAM, and that is the whole reason the stream
exists.** An add leaves NO `Fill` record — it is separate lots, so it never reaches `dec.fills` —
so a bridge reading fills alone trades the base position and says nothing. Every other mirror here
reads a fill; this one reads what the strategy ASKED FOR.

🔴 **THE SIZE STILL COMES FROM `_plan`, and exactly one argument differs.** `plan_order`'s
authorisation check asks whether the intended risk equals `balance x exec_risk_pct` — right for an
entry, which is sized that way by construction, and **wrong for an add, which is sized off the
PROFIT THE STOP HAS ALREADY LOCKED.** Passing the percentage anyway would not be a stricter bridge;
it would be a bridge whose scale-in never happens. `risk_authorised=False` switches that one check
off and **nothing else** — units-to-lots, the two independent routes to a lot count, the venue's
volume band, margin and the account-wide cap all still run.

🔴 **REMOVING A CHECK MEANS PUTTING ONE BACK, and `_add_size_fault` is it.** What bounds an add is
not a percentage of the account but a multiple of the BASE position (`exec_scale_cap_x`, 0.5
shipped). A lot larger than that did not come from the affordability arithmetic, whatever produced
it. ⚠ An unreadable base size or cap REFUSES (rule 1).

🔴 **THE STOP IS THIS BAR'S POSITION STOP AND THE INTENT CARRIES NONE.** Every lot shares the
position's one ratcheting stop, and a market order's stop goes out WITH it, so the bridge supplies
`dec.stop` — the value the ratchet is about to move every other ticket to on the same bar, so the
new lot lands already in step rather than waiting a bar to be found.

⚠ **A scale-in lot has its own SLOT** (`ADD_LONG`/`ADD_SHORT`), so one placement path, one refusal
vocabulary and one unknown-outcome latch serve every order this bridge sends. Nothing ever rests
there today — the only supported mode enters at market — and the slot earns its keep through
`_refused`, which is what lets `_agrees` name a refused add in the halt. ⚠ **`slot_label` is a
MAPPING now**: the conditional it replaced answered "primary" for every kind it had not heard of,
and a scale-in refusal reported as a primary one sends the reader to the entry logic for an order
the entry logic never placed.

⚠ **The coherence checks are ONE copy** (`_market_order_fault`). An entry and an add are the same
order shape — both fill on arrival carrying their own stop — and this file has already paid for the
same rule written twice. ⚠ **The CODES differ by kind**: a count of `entry_stop_wrong_side` says
the entry logic is broken, `add_stop_wrong_side` says the trail and the add level have crossed.

### 🔴 A refused add was SILENT, and `_agrees` was never going to catch it

**The agreement check compares DIRECTION and PRESENCE, never SIZE.** So an add that never reached
the broker leaves one position on each side and passes every check, while the strategy ratchets,
banks and grades a position bigger than the account carries. `_add_shortfall` is the only thing
that notices, and it halts.

🔴 **A SHORTFALL IS NOT AUTOMATICALLY A DIVERGENCE.** `plan_order` rounds a lot count DOWN to the
venue's step and never up (rule 17), so **every add that has ever been placed holds slightly less
than the units the strategy booked.** Reading that as a divergence would halt the bot on its own
arithmetic, on every scaled trade. So it is judged two ways, the first exact: **a refusal recorded
on the add slot settles it outright** — the bridge asked and was told no — and otherwise a rounding
budget of one volume step per lot held, plus one for a lot that may be missing entirely.

⚠ **An unreadable volume step ALERTS and does NOT halt** (rule 1): without it there is no way to
tell this bridge's own rounding from a real divergence, and halting a live bot on a number nobody
could read is acting on an answer that was never obtained.

🔴 **THE SHORTFALL IS TESTED BEFORE "are there any add tickets", AND THE FIRST VERSION HAD THAT
ORDER WRONG — found by writing the test, not by reading.** The case worth catching is an add that
reached NO ticket at all, and that case has an empty list by definition; returning early on *no add
tickets* reads the most complete failure available as nothing to do.

### The account must HEDGE, and that is asked of the terminal

**`assert_hedging_for_scale_in` refuses scale-in unless a second order on the same side opens its
OWN position.** On a netting account an add MERGES into the position already held — one ticket, one
stop, one volume that silently includes the adds — and every read in the add path means something
else. **The size reconciliation would see the added lots as excess on the base ticket and bank away
the position the strategy is still managing.**

⚠ **`None` REFUSES** (rule 1). ⚠ **It takes the fact as an ARGUMENT rather than reading a
terminal**, the same shape as `assert_secondary_wired`: this module is imported by the promote
preview, which has no terminal to ask. ⚠ **The runner asks it in `_build_strategy`**, the one place
every caller shares, and RE-asks on every rebuild rather than caching the first answer (rule 16) —
this terminal has already been observed switching accounts under a running bot. ⚠ **A bot with
scale-in OFF is never asked**, so nothing running today changes.

### What this changed about the tests, and two findings from doing it

**Tests: 15 new in `test_live_bridge.py` and one re-stated in `test_dual_feed_merge.py`. 12
mutations RUN, every one RED on its own named test**, including a control that refusing every add
reddens the at-the-ceiling case.

🔴 **THE TWO PINS ON THE OLD REFUSAL WENT RED, WHICH IS THEM WORKING.** Both were written on
2026-09-07 to go red *"the day the default moves back, or the day the bridge learns to place an
add"*. They are RE-STATED, not loosened: one now pins that a market add is supported and a resting
one is still refused by name, the other that the shipped mode is the one this bridge can mirror.

🔴 **ONE MUTATION SURVIVED FIRST, AND THE REASON IS WORTH MORE THAN THE FIX.** The test asserting an
add is not recorded as a resting order passed under the mutation that makes every order rest —
because under that mutation nothing was placed at all (the order became a limit the fake refused),
so `_rest` was empty for a reason the test did not name. **It now establishes that the order really
happened before saying where it was not recorded.** A test whose premise is not established is
green against its own defect.

🔴 **THE FAKE STRATEGY ANSWERED `None` WHERE PRODUCTION ANSWERS A CONFIG OBJECT.** The bridge reads
both `cfg` and `_cfg`; on the real `Execution` they are one object behind a property and cannot
disagree, and this double had them as two independent attributes — so `_plan` saw `None` for the
config on every test that passed one. Survivable for a base entry, whose sizing then falls back to
its own defaults; **not survivable for a scale-in lot, whose ceiling is read straight off it.**
Fixed as a property with a setter, so the two cannot be made to differ here either. **Fifth time
this file has recorded a fixture less capable than production.**

⚠ **`intents` had to be declared in the live contract, and the guard chain found it in two
links** — `test_live_contract.py` went red on the bridge reading an undeclared field, then again on
`LiveDecision` not carrying it. Rules: `strategies/CLAUDE.md`.

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9.** ⚠ **`sos_fade_demo` pinned scale-in OFF until
2026-09-08 — see the section below, which is the change that makes all of it reachable.**

### Scale-in is ON for `sos_fade_demo` (2026-09-08) — and this one needs a PROMOTE

Aaron's call, bringing the live bot onto the strategy default that moved 2026-09-06. **The
measurement, every warning and what does NOT change are in that bot's own `config.json`
(`_scale_in_on_2026_09_08`) — not restated here**, because a second copy of a decision is how two
files come to disagree.

🔴 **A PROMOTE IS REQUIRED, WHICH IS THE OPPOSITE OF THE THREE PARAM CHANGES BEFORE IT.** Every
setting change on this bot since 2026-09-02 has carried *"no promote is needed and none should be
run"* — true, because the code they needed was in `algos/`, which arrives by `git pull`. **This one
is not.** `sos_fade/execution.py` imports the shared order vocabulary in `execution/` at module
scope, that tree only joined `promote.py`'s copy list on 2026-09-07, and this bot's snapshot was
built **2026-09-05** — so it predates the tree and cannot import the new strategy. ⚠ **The failure
would be loud rather than silent** (the promote's own verify subprocess refuses, and a bot that
cannot import does not start), but the ordering is still promote → restart, never the other way.

🔴 **THE RESTART ALSO LANDS THE TWO SETTINGS FROM 2026-09-07, WHICH HAVE NEVER TAKEN EFFECT.**
Neither the deeper-entry stop nor the widened re-entry trigger is runtime-reloadable, and no restart
happened on the day they were written — MEASURED on the box 2026-09-08, the running snapshot still
carries the deep stop ON and the gap trigger alone. **So one restart arms three decisions, not one,
and two of them are three days old.** ⚠ **A param change that needs a restart is not applied when it
is committed; it is applied when somebody restarts the bot** — and nothing schedules that, so the
gap is however long it takes for the next deploy.

⚠ **RULE 9 IS NOT CLOSED BY SWITCHING IT ON.** No add has ever reached a broker and no parity gate
covers the path. **Watch the first one.**

### The whole-position target goes to the BROKER, so it fills at the target (2026-09-08)

**`_sync_take_profit` puts the price on the position.** A rung that takes the whole position off
reached the broker as `_mirror_strategy_exit` closing at MARKET on the next bar close — so the lab
booked the rung's own price and the live bot booked whatever the market was when the bar shut. On a
15-minute clock that is up to a whole bar of drift, in whichever direction the bar happened to run.

🔴 **THE MARKET CLOSE IS NOW THE SAFETY NET RATHER THAN THE MECHANISM, and `_mirror_strategy_exit`
is UNCHANGED.** If the broker's target fills, the position is simply gone by the next sync and the
mirror's own *"already gone — the ordinary path books it"* branch takes it; `_observe_close` then
books the REAL fill price off the deal, net of swap and commission, exactly as it does a stop-out.
**That is not a new path — it is the path every stop-out has always taken.** If the target never
went on, or the broker refused it, the mirror closes at market as before.

🔴 **ONLY A RUNG THAT TAKES 100%, AND THAT IS WHAT A POSITION-LEVEL TARGET CAN EXPRESS — not
caution.** MT5's `tp` closes the WHOLE position, so pointing it at a rung banking half would delete
a runner the strategy is still managing. `_sync_partials` keeps that case, still at market on bar
close, still naming `fill="market_on_bar_close"` on every record. **A partial bank needs its own
resting limit order and this bridge does not have one.**

🔴 **IT ASKS THE STRATEGY (`_tp1_pct`), NEVER THE CONFIG, AND THAT IS THE WHOLE REASON NO STRATEGY
FILE CHANGED.** `bank_ladders` mirrors the same rule for the startup refusal and **cannot answer it
for an OPEN trade**: a re-entry after a stop-out and a re-entry into a gap read different fields,
and on the armed bot those are **100 and 0**. Reading the config here would hang a target on a
trade the strategy rides. ⚠ **Rule 22 is satisfied by not being triggered** — `strategies/` is
untouched, so no parity gate is owed.

⚠ **`None` is *no such rung, or the strategy has not said* — never `0.0`**, which reaches MT5 as
*no target at all*. 🔴 **A STATED GAP: the extreme-leg bot has no `_tp1_pct` and its target really
IS 100%** (`extreme_leg.execution` publishes `tp_rungs=((take_profit, 100.0),)`), so it keeps
closing at market and nothing announces that. Wiring it needs that strategy to DECLARE the rung —
**this layer must not assume one**, because absence and *banks nothing* are the same value here and
only the strategy can separate them.

⚠ **A RECONCILIATION, not an event** — it reads the broker's own `tp` and brings it into line, the
same shape as `_sync_add_stops`. A remembered flag would be empty after a restart while the broker
still held the position, so the target would never be re-stated.

⚠ **Every position under our magic, not just the base.** On a hedging account an add is its own
position; a target on the base alone banks part of the trade at the rung and leaves the adds riding.

⚠ **It SETS and never CLEARS.** Clearing needs this layer to tell a target IT set from one a person
set by hand, and it holds no record surviving a restart — so it would eventually delete somebody's
own exit. A target belongs to ONE ticket, so a rung that stops applying cannot strand a stale one.

⚠ **The stop travels with it** (`TRADE_ACTION_SLTP` sends both fields), so it runs AFTER
`_sync_stop` and passes the stop that call has just staged. ⚠ **`move_sl(tp=None)` PRESERVES an
existing target**, checked in `mt5_ops`, so the ordinary ratchet cannot wipe one.

⚠ **A refusal is ALERTED and does NOT halt.** The broker rejects a target on the wrong side or
inside its stop level; the honest consequence is that one trade exits the old way.

🔴 **IT IS WIRED INTO BOTH CLOCKS AND `sync_fast` IS THE ONE THAT MATTERS TODAY** — the armed bot's
only price-triggered rung belongs to the re-entry after a stop-out, which is managed on the fill
clock. Wired only into `sync` it would never fire on the single trade this exists for.

**Tests: 11 in `test_live_bridge.py`, 11 mutations RUN and every one RED on its own named test** —
and the harness asserts each test was SELECTED and green at baseline first, because a `-k` filter
matching nothing reads exactly like a vacuous test.

🔴 **THE FAKE BROKER DISCARDED THE ARGUMENT UNDER TEST, AND THE FAKE POSITION HAD NO `tp` AT ALL.**
`move_sl` accepted a target and threw it away, so a call setting the strategy's target and one
clearing it were indistinguishable; and nothing was APPLIED to the position, so a reconciliation
re-sending the same instruction every bar for the life of a trade looked identical to one that
converged. **Sixth time this file has recorded a fixture less capable than production.**

🔴 **A PRE-EXISTING TEST WAS POISONING EVERY TEST THAT RAN AFTER IT, AND THIS IS THE FINDING WORTH
MORE THAN THE FEATURE.** `test_a_strategy_that_cannot_report_its_stop_SAYS_SO` did
`del type(ex)._current_stop` — deleting the method from the CLASS, for the rest of the session.
Nothing downstream had ever needed it, so it was invisible; the first test that did **failed in the
SUITE while passing alone**, which is the worst failure shape a suite has. It is `monkeypatch.delattr`
now, so the restore cannot be forgotten. ⚠ **Ask what a `del` in a test is deleting FROM** — an
instance is local, a class is global and permanent.

⚠ **Two new ledger events, both DECISIONS** (`target_set`, `target_set_failed`) — they answer
*where will this trade exit*, never *is the machinery working*. The routing guard caught them, which
is that guard earning its keep. ⚠ **`target_set` matters because the alternative evidence is an
ABSENCE** — no `partial_banked` carrying `market_on_bar_close` — and an absence is not a record.

⚠ **It reaches the running bot by `git pull` plus a RESTART** (`algos/` is not in the frozen
snapshot). No promote is needed for it.

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9** — and the first target to watch is a reclaim
re-entry's, on a bot that has never banked anything at a price.

### The target now comes from a DECLARED contract, not from one strategy's internals (2026-09-09)

`_wanted_take_profit` asked SOS Fade's own `_tp1_pct` and read `dec.tp1`. It now asks
`full_exit_price()` — a required entry in the live contract's `EXECUTION_ATTRS` — so the rule about
which share a rung takes lives in the strategy that books the fills, and every bot answers.

🔴 **THAT MOVED THE PERCENTAGE RULE OUT OF THIS PACKAGE, WHICH IS THE POINT.** `algos/live/` holds
no trading logic. `bank_ladders` still mirrors the same rule for the STARTUP refusal and cannot
answer it for an OPEN trade — a re-entry after a stop-out and one into a gap read different fields,
100 and 0 on the armed bot. **Reading the config here hangs a target on a trade the strategy rides.**

🔴 **A STRATEGY THAT CANNOT ANSWER HALTS THE BOT, AND IT HALTS HERE BECAUSE THE STARTUP GATE IS NOT
WIRED.** Four docstrings in this package call `verify_live_ready` the check that refuses a
non-conforming strategy by name; **nothing in `algos/live/` calls it** — grepped 2026-09-09, its
only caller anywhere is one strategy's own test. **The state is reachable and ordinary:** `algos/`
arrives by `git pull` and a strategy only by `promote.py`, so a box pulled before it is promoted
runs this bridge against a frozen strategy that has never heard of the seam. Left as a bare
attribute read, that is an exception mid-bar on a live position; the halt names the promote.

⚠ **The guard is a `getattr` and the CALL is a plain attribute read, deliberately.**
`test_live_contract.py` derives what this package needs by grepping `self._ex.<name>` out of this
source, so a purely defensive read would drop the seam out of the contract and the requirement
would stop being one with nothing failing.

🔴 **DEPLOY ORDER: PROMOTE, THEN PULL, THEN RESTART — the reverse takes a bot down.** This is the
first change here whose two halves are split across the two delivery routes and cannot be applied
in either order. ⚠ **A bot holding an open position cannot be promoted** (`promote.py` refuses), so
a bot with a live trade waits.

⚠ **Placement-time targeting was SPECCED AND NOT BUILT, and the reason is a measurement.** SOS Fade
enters on a RESTING order, so it is flat when the order is placed and its own rule returns no
target there — the placement half could only ever help the extreme leg, buying one bar, while
adding a way for an ENTRY to be refused. A refused entry costs a whole trade; a late target costs
one bar of drift on the exit. The reconcile covers both bots within a bar of the fill.

**Tests: 11 in `test_live_bridge.py`; 16 mutations RUN across the bridge, both strategies and the
contract, every one red on its own named test.**

## The target now travels WITH the order, the way the stop always has (2026-09-09)

**Both placement branches in `bridge._place` sent a hardcoded `tp=0.0` until this date.** So every
trade was open at the broker with NO target until the next reconciliation pass — up to a whole
fill-clock bar — and a trade that reached its price inside that window closed at MARKET instead, at
whatever the bar had run to. **That is the last of the close-at-target drift.**

⚠ **`0.0` is MT5's *no take-profit*, which is a real instruction rather than an absence**, so it is
still what an untargeted order sends. Tests assert the value in both directions, never merely that
a target appeared.

🔴 **WHICH QUESTION THE BRIDGE ASKS DEPENDS ON WHETHER THE STRATEGY HAS ALREADY FILLED, AND GETTING
IT BACKWARDS IS SILENT EITHER WAY.** A MARKET order is sent after the strategy opened its own
position — the bridge is catching the broker up — so `_wanted_take_profit` reads the exact price. A
RESTING limit is placed before anything fills, so the strategy is asked what that order WOULD close
at (`_order_take_profit`). ⚠ **Asking the open-position question about an unfilled order returns
`None` for every trade** — a feature that never sends a target and looks implemented. ⚠ **Asking
the planned question on the market path returns `None` for every trade too**, and the extreme-leg
bot would never carry one. Both directions are pinned by tests that would pass if only one were.

🔴 **A STRATEGY THAT CANNOT ANSWER HALTS THE BOT AND THE HALT NAMES THE PROMOTE.** `algos/` arrives
by `git pull`; a strategy arrives only by `promote.py`. **A box pulled before it is promoted runs
this bridge against a frozen strategy that has never heard of the seam** — so the state is
reachable, not theoretical. A defensive read would make *never implemented* and *this order has no
target* one value (rule 1), whose first meaning is a bot quietly closing at market for its whole
life. ✅ **IT NOW ALSO REFUSES AT STARTUP — see *The startup contract check is WIRED* below.** The
mid-bar halt STAYS as the backstop: the startup check reports PRESENCE only, so a strategy can
satisfy every name and still answer nonsense, and the halt is what catches that.

### The venue's opinion of a target DROPS the target — the stop's REFUSES the order

`mt5_ops.usable_take_profit` is the one place a target is checked before it leaves for the venue.

🔴 **THE ASYMMETRY IS THE DESIGN, NOT AN OVERSIGHT.** An unacceptable STOP refuses the whole order —
a trade with no stop is unbounded risk. An unacceptable TARGET is dropped and the order still goes:
a trade with no venue target is exactly what every trade here had before this date, the bridge sets
one on its next pass, and the strategy still closes it at market. **Losing a whole setup to a target
the broker disliked is a far worse trade than being a bar late with the target.**

⚠ **Two different faults, two different sentences.** Inside the venue's minimum distance is a BROKER
limit and says nothing about the strategy. On the wrong side of the entry is a STRATEGY fault — a
target already passed, which a venue would either refuse the order over or fill on the spot.

⚠ **A DROP IS NEVER SILENT, and that is rule 1 in the record.** `0.0` reaches the venue as *no
target*, identical to an order that never asked for one — so without a line in the log, *asked for
none* and *asked and was refused* read the same forever after. ⚠ **The success line reports the
target SENT, never the one asked for** (rule 3, same rule that makes it report normalised lots).

### DEPLOY ORDER: PULL, THEN PROMOTE, THEN RESTART — and the RESTART is the one that must be last

🔴 **THIS SECTION SAID *PROMOTE, THEN PULL* FOR THE FIRST HALF-DAY OF ITS LIFE AND THAT ORDER IS
IMPOSSIBLE.** `promote.py` copies out of the box's OWN checkout, so there is nothing new to promote
until the box has pulled. Written from the hazard rather than from the tool, and caught only by
reading `promote.py` before running it. ⚠ **A deploy order is a claim about what a tool READS —
check the tool, not the story you are telling about the risk.**

Both halves must land before either bot comes back up. `algos/` (the bridge, the broker layer)
arrives by `git pull` and is picked up on RESTART; `strategies/` (the seam both bots implement)
arrives ONLY by `promote.py`.

1. **`git pull` on the box.** Safe while both bots run — a running process keeps the modules it
   already imported, so nothing changes underneath it.
2. **`promote.py` for each bot.** Also safe while running: it swaps the frozen snapshot on disk and
   never touches the process.
3. **Restart each bot.**

⚠ **THE REAL CONSTRAINT IS THAT NOTHING MAY RESTART BETWEEN 1 AND 2.** A bot that restarts after the
pull and before its promote runs the new bridge against a frozen strategy that has never heard of
the seam — which HALTS, by design. ⚠ **`SYS_MONITOR` restarts a dead bot on its own within ~60s**,
so the window is not only about what you type: do not leave a bot stopped between those two steps.

⚠ **A bot holding an open position cannot be promoted** (`promote.py` refuses), so a bot with a live
trade waits for it to close.

✅ **RUN 2026-09-09, both bots, and every step probed rather than assumed.** Pull reported *Already
up to date* while the fetch showed the range moving — read as a QUESTION, not an answer, and the
box's HEAD, the commit's presence and the seam's presence in the working tree were each checked
separately. `sos_fade_demo` v199 → **v201** (`7ce428cc1d74`), `extreme_leg_demo` v193 → **v206**
(`1b6665f322e3`), both hashes matched back against the promote output. Both stopped by REQUEST and
both cleared their own stop file (checked — a leftover would stop the bot the instant it came up).
`schtasks` said SUCCESS, which proves nothing, so the processes and both startup banners were read.
Neither halted. ⚠ **The reversal bot carried ONLY the two target commits; the extreme leg carried
12**, of which the other ten are `sos_fade`/`backtest` code it holds solely through its dependency
closure. **That gap is read per bot before promoting, never assumed from the version jump.**

⚠ **19 new tests here, every one watched RED by mutation** (15 mutations across four files, all
killed). Gates re-run and green: `compare_strategy.py` exit 0 at warmups 500/1000 with a
byte-identical HEAD control, `compare_extreme_leg.py` exit 0 on 18,248 bars. **Rule 9 still stands:
no order carrying a target placed at send time has reached a broker.**

### ✅ The startup contract check is WIRED, and it was described as the gate for weeks (2026-09-09)

**`verify_live_ready` is called by `runner._assert_live_ready`, on every strategy build.** Four
docstrings in this package called it the startup gate that refuses a non-conforming strategy by
name; **nothing in `algos/live/` called it** — grepped, not assumed, and its only caller anywhere
was one strategy's own test. **A comment promising a safety net that is not there is worse than no
comment, because the next reader stops looking** — this file has now recorded that shape four
times, and this is the fourth.

⚠ **MEASURED BEFORE WIRING IT, because a check that refuses a bot which starts today is a bot
down.** Both live bots were run through it — the REPO's contract against the DEPLOYED snapshot each
one is actually running, on the box, at a moment when it had pulled and not yet promoted: **both
conformant.** So this refuses nothing today.

⚠ **It REFUSES rather than warning.** A bot missing a seam runs normally until the first setup and
then throws or halts **with a live position open**, which is the worst moment available. The
failure lands in `run()`'s startup handler — logged, written to the ledger, announced as **WILL NOT
START** with the reason.

⚠ **PRESENCE, never correctness** — the contract's own stated limit. It turns *crashes somewhere in
the bar loop* into *refused at startup, by name*; it is not a proof that the strategy is right, and
every mid-bar halt stays.

⚠ **Re-run on every REBUILD, not cached from the first start** (rule 16). A re-warm and a reconnect
both reconstruct the strategy, and an edit inside a live `deployed/` snapshot changes what the next
rebuild loads with no promote and no restart.

⚠ **The refusal names `promote.py` and prints the bot key**, because that is the fix: `algos/`
arrives by `git pull` and a strategy only by `promote.py`, so the overwhelmingly likely cause is a
box pulled ahead of its promote.

### 🔴 …and wiring it walked straight through a hole in BOTH freeze guards

**The obvious implementation — `from live_contract import verify_live_ready` at module scope — is
the one that had to be used** (the REPO's contract is the one that binds, because the seam list is
derived from what `algos/live/` reads and the bridge is what the bot runs). **It silently
half-applies the freeze.**

🔴 **`strategies/python` is on `sys.path` as a ROOT, so that module imports as the BARE name
`live_contract` — never as `strategies.something`.** `_bind_code` refuses a leak of the strategy
package, `engines` or `backtest` **by name**; `test_no_frozen_imports_at_module_scope.py` matched
the same three top-level names. **A bare name from that tree is invisible to both.**

**MEASURED, all four parts:** the import resolves to the repo copy; `_bind_code` does not refuse;
the suite guard does not catch it; and a later import from a bound snapshot returns **the repo
object**. `extreme_leg` inherits `LiveDecision` and `LivePositionMixin` from that module at module
scope, so a promoted bot would have run repo classes inside a frozen strategy **while its banner
said *frozen*** — the exact failure `_bind_code`'s own docstring calls the worst outcome available.

✅ **`runner._repo_live_contract` loads the repo's copy BY PATH under a private name**, so
`live_contract` stays free for the snapshot's own copy and the freeze is whole. ⚠ **Not cached
across rebuilds by accident** — it is registered under that private name so the file is read once.

✅ **The suite guard's shadowable set is DERIVED from `strategies/python/` rather than typed**, so a
shared module added beside the strategies is covered without anybody remembering. ⚠ **It needed its
own non-vacuity case**: with nothing in `algos/live/` importing a bare name any more, reverting the
widening left every test green — **a branch nothing can kill reads as a covered branch**, which
this repo has now recorded three times. A case drives the probe with `live_contract` directly.

🔴 **`_bind_code`'s OWN predicate still has the hole and that is a STATED GAP.** Nothing in
`algos/live/` imports a bare name from that tree today, and the suite guard now fails in CI the
moment one appears — but no hook runs the tests, so CI here means *somebody ran it*. Closing it
means matching on a module's FILE rather than its name, on the live startup path, and it is worth
doing on its own rather than inside a change that also moves a live check.

**Tests: 9 in `test_live_runner_startup.py`, 1 in `test_no_frozen_imports_at_module_scope.py`;
9 mutations RUN and every one RED, re-run after `ruff format` because a reformat invalidates a
patch string and a BADPATCH reads exactly like a survivor.**

🔴 **ONE MUTATION SURVIVED FIRST AND IT WAS THE DEFECT BEING FIXED, ONE LEVEL UP: deleting the CALL
from `_build_strategy` left every test green**, because all of them drove `_assert_live_ready`
directly. **A guard is only as real as its call site, and a test that drives the guard rather than
the thing that should invoke it proves the guard works and nothing about whether it runs** — rule
7, reproduced inside the change written to fix rule 7. Two tests now drive `_build_strategy` itself,
one for the refusal and one for the pass, because a wiring test that only ever asserts a refusal
passes against a build path that refuses everything.
