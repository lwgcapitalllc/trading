# Notes — Risk sizing, account budget and halts

Dated stories on the 10% risk cap split, the account budget refusing per bar, the halt latch not holding, promote-time halts, and a windfall defect that kept sizing later trades. Moved VERBATIM out of `algos/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 THE HALT DID NOT HOLD — a reconnect, a bar gap or a settings edit put a halted bot back to trading (2026-09-02)

**`begin_live` was written as a once-per-start call and is not one.** Three paths call it again on
a bot that has been trading for weeks — the reconnect after a link outage, the bar-gap re-warm, and
a runtime settings change applied while flat — and **every branch of it ASSIGNED the state.** So
any of the three lifted a halt, and **nothing re-halted the bot afterwards**: both runner-side
latches return early forever once they have fired, exactly as designed.

🔴 **The account-identity case is the one that costs money.** That halt fires *because the terminal
is logged into an account this bot was not pointed at* — the thing that happened under a running
bot on 2026-08-12 — and a reconnect put the bot straight back to placing orders on that account.
The fleet kill switch was equally undone: flip the switch, wait for one blip, and the fleet is
trading again.

✅ **Fixed in `bridge.begin_live`, not at the three call sites**, and the placement is the rule: a
constraint enforced at every caller is one the fourth caller has never heard of. `_halt` already
refuses to re-halt an already-halted bridge; this is that same latch arriving from the other side.
**Only a restart clears it.**

✅ **The refusal is RECORDED** (`begin_live_refused_while_halted`, HEALTH). Rule 1: without it the
only trace of a suppressed re-warm is a MISSING `went_live`, which is also what an ordinary healthy
bar looks like.

🔴 **The two all-clears were lying, and that half is not cosmetic.** The reconnect said
*"Nothing to do."* and the settings change said *"Applied straight away."* — on a bot that is
halted and will place nothing. **A message that stops somebody looking is worse than no message**,
which is this file's own standing rule about alarms arriving from the other direction. Both now say
the bot is still halted and name the reason; a healthy one still reads as a plain all-clear,
because an alert that always warns is one nobody reads.

⚠ **The settings values really ARE loaded** — the change is not refused, it simply cannot reach an
order until somebody restarts the bot. Saying *refused* there would send the reader to re-edit a
file that is already correct.

**Tests: 6 in `test_live_bridge.py`, 4 in `test_mt5_link.py` / `test_runtime_reload.py`.** Five
watched RED against HEAD; the two "a healthy bot still goes live / still reads as an all-clear"
controls pass both ways by design and are non-vacuous by MUTATION — always-refuse reddens them.

🔴 **Two tests were WRITTEN, MEASURED VACUOUS AND DELETED, and that is the transferable half.**
A runner-level test asserting *the bridge is still halted after a reconnect* passed against the
bug: the bridge DOUBLE latches, so the fixture was enforcing the property, not the code. **When
the fix lives in a collaborator, a test one layer up proves the double, never the fix.** What the
runner level can honestly pin is what it SAYS afterwards — and those two went red.

⚠ **Both bridge doubles were upgraded to carry a REAL `BridgeState`** rather than a look-alike
with a `.value`. The check is an identity test, which is False for every stand-in — so a fake that
merely quacked would pass the halted case without ever entering the branch.

## ⚠ Before splitting the 10% cap between two strategies — three live-side facts the lab cannot show you (2026-08-20)

`backtest/tools/recovery_stack.py` now replays the loss-recovery rule as a LEG sharing this bot's
balance and its account budget. The measured sweep lives in
`strategies/python/loss_recovery/CLAUDE.md` and is not restated here. **What belongs here is that
adopting any such split is a LIVE change to an ARMED bot, and the live cap differs from the lab cap
in three ways that all push the same direction — live contention is MORE frequent and MORE
punishing than any stack backtest predicts.**

🔴 **1. The cap comparison here carries NO ROUNDING TOLERANCE.** `shared/account_risk.py`
(`check_account_cap`) tests the new order's risk against the remaining room on a bare `>`. **That is
the same defect shape found and fixed in `backtest/portfolio/account.py` on 2026-08-20**, where an
entry floor set equal to a leg's own risk rate refused **3,650 entries over 7.9 years** — because a
granted amount and a threshold were reached by different arithmetic (one side divides by the stop
distance to get a quantity, the other re-multiplies) and disagreed in the last bit. **A split
summing EXACTLY to the cap — 8% + 2% against a 10% cap — puts the second order on precisely that
edge.** ⚠ **Live it is strictly worse than the lab, and the lab CANNOT reproduce it**: the lab's
arithmetic is exact, while real open risk here is computed from the broker's ROUNDED lot size and
its actual stop, so an "8%" position is never 8.000%.

✅ **MEASURED 2026-09-03 AND THE EDGE IS NOT REACHABLE — DO NOT BUILD THE TOLERANCE.** Two findings,
and the second retires the concern. **First, `>` already ALLOWS an order exactly equal to the room**
— equality is not greater — so the *"8% + 2% against a 10% cap"* case the paragraph above names is
permitted, not refused; only an order exceeding the room refuses. **Second, the quantisation dwarfs
the noise.** Risk here moves in whole lot steps: on `XAUUSD.p` at 0.01 lots × 100 oz, one step is
one dollar per dollar of stop distance — $10 on a $10 stop — while one float ulp of a $999.70 room
is ~2e-13. The grid is **9 trillion to 227 trillion times coarser** than the noise a tolerance would
absorb, and the nearest order a broker can actually accept sits **97% of a lot step below the
edge** ($990.00 against $999.70). **The rounding this paragraph cites as making it "strictly worse
than the lab" is the very thing that makes the boundary unreachable.**

⚠ **So the lab's defect does NOT transfer, and the reason is worth keeping.** There the two sides
were continuous and genuinely met; here one side is quantised at a step ~1e13 times the disagreement
a tolerance guards against. **Same comparison, same operator, different reachability — a defect
shape is not a defect.** ⚠ **Leave slack in a split anyway**, for the ordinary reason that a cap
equal to the sum of its parts leaves the second bot refused whenever the first is on, which is
arithmetic rather than floating point.

⚠ **2. This side REFUSES; the lab side SHRINKS.** Refusing is correct (rule 17 — a resized order is
not the trade the strategy is holding) and it is not changing. But it means every lab cell reporting
*0 refused, 0 shrunk* is describing an allocator that WOULD have shrunk had it needed to. **The live
book of a split config is a SUBSET of the lab's book, never a rescaled copy of it**, so a lab result
does not transfer trade-for-trade.

⚠ **3. A RESTING order counts against this budget; the lab reserves at FILL.** SOS Fade places a limit and
waits, sometimes for a long time. So live contention starts EARLIER and lasts LONGER than the
replay. **A stack backtest is a FLOOR on how often a split contends, never an estimate of it.**

⚠ **The starting point is also not what a split assumes.** `exec_risk_pct` is **10.0** in both
`config.json` and `deployed.json` today, so this bot's per-trade risk already equals the entire
account cap and there is no room to give a second strategy without lowering it first.
⚠ **`account_risk_cap_pct` IS runtime-reloadable since 2026-09-11** — it lands the next time the
bot is flat, with no restart (see *Runtime config reload*). Until then a cap-only change was dropped
as cosmetic, and this line said it needed a restart.

### 🔴 A windfall from a defect keeps sizing every later trade (2026-08-26)

**Marking the trades in the record was not enough.** Five copies of one order filled on
2026-08-25 and left **$3,344.80 the strategy did not earn**. The four extras were closed and
marked `counts_as_strategy_performance=false` the same night — and the very next entry still went
out at **0.53 lots where the risk percentage called for 0.40**, a third too big, because the
balance they left behind is what everything sizes off. **A label fixes the accounting; it does
nothing about the compounding.**

✅ **`sizing_basis_adjustment` in the instance config** is ADDED to the broker balance before
anything sizes off it, so an amount to EXCLUDE is written NEGATIVE. Addition is unambiguous
arithmetic — an "amount to exclude" invites a sign error, and a sign error here makes every
position BIGGER rather than smaller.

🔴 **One seam, and it is the point.** Three places read the balance — startup capital, the
flat-moment equity re-anchor, and the account-level risk cap — and all three go through
`algos/shared/sizing_basis.py`. **A cap measured against the broker's balance while the strategy
sizes against an adjusted one is a cap quietly looser than it says**, and the difference would
only surface in a month nobody is checking. That is the shape of 2026-08-07, where the units
conversion lived in no single place and was wrong by 221x with every artefact reading as correct.

⚠ **The link PROBE returns the broker's raw figure, deliberately.** `probe_link` answers one
question — is the link up — and an early draft applied the adjustment inside it, which made a
liveness probe depend on strategy configuration. A test building a bare runner caught it at once.
**Ask what a function is FOR before adding a concern to it.**

⚠ **It REFUSES, never clamps.** An adjustment leaving nothing to trade on makes the basis
unreadable and every order is refused — the same call `order_sizing` makes for an order below the
broker minimum. A floor would be a size nobody chose.

⚠ **`None` in, `None` out.** An unreadable balance must never become a number.

⚠ **NOT runtime-reloadable** — read at startup and at every flat-moment re-anchor, so it needs a
restart. ⚠ **It is a CLAIM and it goes stale**: state the reason and the date beside it in
`config.json`, and revisit whenever the account is reconciled.

**Tests: 11 in `tests/test_sizing_basis.py`, three mutations watched RED.** ⚠ **The first pass
missed the one that matters** — making the cap ignore the adjustment left the whole suite green,
because the one-seam property was claimed in three docstrings and asserted nowhere. **A property
stated only in prose is not a property the code has.**

### 🔴 Promoting with a position OPEN halts the bot (2026-08-26)

**It happened the same night as the promote fix.** A bot was promoted v168 -> v241 while holding
a real trade. The newer strategy persists 13 more position fields (scale-in and reclaim state),
the record had been written minutes earlier by the old version, and the restore **refused** —
correctly, because a record it cannot fully read means it does not know what it is holding. The
trade sat with only its broker stop, nothing ratcheting it and no time exit.

✅ **The promote now ASKS, and REFUSES (2026-08-26).** `open_position_gap()` compares the open
position's record against the `_POSITION_FIELDS` the STAGED snapshot declares — read from the
snapshot, because only the new version knows what the new version needs. A real promote stops and
names the migration tool; `--allow-open-position` overrides it; a dry run reports and carries on,
which is the whole point of a preview.

⚠ **An unreadable record counts as a gap, never as "no position"** — a record that will not parse
is one the restore would refuse anyway, and reporting it as absent is the shape of error this file
exists to stop. ⚠ **A version declaring no position fields asks nothing** rather than treating
every field as missing, or it would refuse every promote for a strategy that holds no state.

⚠ **It is silent on the ordinary case.** A complete record, or no position at all, prints nothing
— a warning that fires when it should not is one people learn to scroll past, and this repo has
already measured that to be worth less than no warning at all.

✅ **`tools/migrate_position_record.py` is the repair.** It ADDS the missing fields and never
touches an existing one, and **every value is read off a freshly BUILT deployed strategy rather
than typed into the tool** — a default written here would be a guess that goes stale the next
time the strategy changes, and it would look exactly like a measurement. It refuses unless the
broker really holds the recorded ticket, keeps a timestamped backup, and leaves fields the
current version does not know about in place so a rollback is not lossy.

⚠ **The bot must be STOPPED** — a running bot rewrites that file whenever the stop moves.

⚠ **It repairs ONE shape of damage.** A record disagreeing with the broker about direction, size,
entry or stop is a different problem and this will not touch it.

### 🔴 A promote must never leave a bot with NO deployed code (2026-08-26)

**It happened.** `activate()` deleted the live snapshot and then renamed the staged one into its
place. On Windows that rename can fail outright — the running bot, an indexer or a virus scanner
holding a handle is enough — and when it did, the instance directory was left with **no
`deployed/` at all**. The bot kept trading only because Python already had its modules in memory;
a restart would have found nothing to import, and `SYS_MONITOR` would have restarted it into that.

🔴 **`stage()`'s own docstring promised exactly what `activate()` broke** — *"a failed promote must
leave the previous deployment exactly as it was, still importable, still matching its pin."* It
was true of staging and false of activation, and the two are three functions apart. **A safety
property is only as strong as its LAST step. Check the whole path, not the part that documents
itself.**

✅ **The old snapshot is now MOVED ASIDE, never deleted first**: `deployed` → `deployed.old`, then
the staged tree into place, then the backup is removed. Any failure rolls the backup back, and the
rollback is itself wrapped so it cannot mask the original error. At every moment at least one
complete snapshot exists — pinned by a test that asserts the ORDER, not just the outcome, because
an outcome test can be satisfied by a lucky retry while the dangerous window is still open.

✅ **`recover_interrupted()` runs at the START of every promote** and puts `deployed.old` back if a
previous run died mid-swap. ⚠ **It only ever restores and never chooses**: if both directories
exist the swap already succeeded and the backup is litter, and preferring one would roll a good
promote back. ⚠ **It is silent when there is nothing to do** — a tool that announces a recovery on
every ordinary run is one people stop reading.

✅ **`_remove_tree()` retries.** A transient Windows lock on a leftover staging directory stopped a
promote dead the same day, before anything had been swapped. The lock is transient; one attempt
turned it into a failure. It never raises — every caller is clearing litter, and none of it is
worth failing a promote over.

⚠ **A `--dry-run` really does stage and verify**, by design — the two things worth knowing before
you deploy are *does it import* and *which settings will change*, and both need the snapshot to
exist. It writes only to `deployed.new` and never calls `activate()`.

⚠ **The trading box's promote-PREVIEW tool is broken** — it sends no request body and the Command
Center answers HTTP 422. Use `promote.py --dry-run` until that is fixed.

**Tests: 8 in `tests/test_promote_swap.py`. The incident is reproduced directly** — the rename is
made to fail and the test asserts the bot still has its old code; it goes RED against the previous
body.

### 🔴 The account budget is now MEASURED per bar — and it REFUSES, because a live shrink is incoherent (2026-09-03)

**Aaron's split: extreme leg 5%, SOS Fade 5%, account cap 10%.** *"If at any time a bot is occupying more
than 5% then the other bot(s) will need to shrink accordingly. If no risk is available then we will
refuse trades and send a telegram messaging saying why."*

🔴 **THE SPLIT IS THE INTENT AND IT IS NOT IN FORCE — SOS Fade WENT BACK TO 10% ON 2026-09-03, HOURS AFTER
MOVING TO 5%.** The 5% was making room for a second bot that **cannot be created as a config
change**, so the split was buying nothing: one bot at 5% with the other 5% unclaimed, i.e. this
account earning half its measured return with nothing taking the other half, for as long as the
adapter took. **A share reserved for a bot that cannot start is not a split, it is an idle half.**
⚠ **The cap stays 10% throughout** — only the per-trade share moved, and one bot at 10% under a 10%
cap is an exact fit that the Command Center's share rule allows. ⚠ **Restore the 5/5 BEFORE
assigning the second bot**, never after: the share rule refuses the assignment while the numbers
still sum past the cap. ⚠ **The reason the split was buying nothing ENDED on 2026-09-03** — the
second bot is registered and benched, and what is left is the ordering above rather than a project.
Do not restore the 5/5 until it is genuinely ready to be armed, or the idle half comes straight
back. See *`extreme_leg_demo` — REGISTERED AND BENCHED* below.

🔴 **THE SHRINK HALF WAS BUILT, AUDITED THE SAME DAY, AND BACKED OUT. Read this before rebuilding
it.** A live bot's order is **already resting at the broker** by the time the account seam runs:
`sos_fade.execution` sizes a pending order from `equity * exec_risk_pct / dist` at PLACEMENT
and never consults the account, while `request_fill` runs at the FILL. So shrinking there books a
smaller position in the emulator than the one the broker just filled — **and `_agrees` compares
DIRECTION and PRESENCE, not size, so it does not even halt.** Two books, silently different, with
every stop move, R and partial afterwards computed against the wrong one. MEASURED: a $0.50 room
granted 0.0005 lots, below the 0.01 broker minimum, against a full-size order already resting.

✅ **So a stated room REFUSES** (`SoloAccount.all_or_nothing`, derived from the room being stated
so no solo replay moves). That matches `bridge._account_cap_check`, which has refused at PLACEMENT
with a Telegram message naming the reason since the cap landed — one answer, not two.

✅ **BUILT 2026-09-03 — the size is now decided where the ORDER is decided.** The strategy asks
the account what it can afford at PLACEMENT (`Execution._fit_to_budget` →
`PortfolioAccount.affordable_qty`), so the bridge sends the already-shrunk order and both sides
book the same quantity. Rule 22 satisfied: `compare_strategy.py` on `VANTAGE_XAUUSD, 15_af500.csv`
GREEN before and after, 21,302 bars each time. ⚠ **The gate proves only that nothing MOVED** — the
Pine has no account budget, so no export can exercise the shrink itself.

⚠ **It was not live-reachable WHILE THE DEFECT EXISTED** — the frozen `deployed/` snapshot carried
no `external_room`, so `refresh_account_room` returned early and the fill-time shrink never ran on
a live bot. That stopped being true with the **2026-09-03 19:32 UTC promote from `904a432c`**,
which is also the first snapshot to carry the budget seam at all.

🔴 **THE SHRINK IS NOT LIVE UNTIL THE NEXT PROMOTE, AND THE TWO HALVES ARRIVE BY DIFFERENT ROUTES.**
`algos/` reaches the box by `git pull`; `strategies/`, `engines/` and `backtest/` reach it only by
`promote.py`. So the bridge half of this can be current while the sizing half is a snapshot behind
— which is exactly the state that produces a *refusing* bot that every doc describes as *shrinking*.
**Check `bot_version`'s built-from commit before believing either behaviour is live.**

**Three pieces and the order is the design.** `bridge.refresh_account_room()` reads the broker and
works out the dollars still free under the cap → the runner calls it at the TOP of every bar →
the strategy sizes against it at PLACEMENT, so the order the bridge sends is already the size the
emulator holds.

🔴 **THE RULE IS NOT "REFUSE, NEVER SHRINK" — IT IS "DECIDE AT THE PLACEMENT, NEVER AT THE FILL",
and getting that wrong is what made the first attempt refuse.** Clamping at the account seam was
justified by the argument the venue lot ceiling rests on, and the argument is sound; what was
wrong was the MOMENT. The lot ceiling is applied before the order is placed, so the bridge sends
the capped size. The account room was applied at the FILL, by which time a full-size order was
already resting, and shrinking there books a position the broker never filled. **Same seam, same
operator, different moment — and the moment is the whole property.** Moving the decision to
placement is what made the shrink legitimate; nothing about the seam changed.

⚠ **A residual case is named rather than papered over**: if the budget shrinks BETWEEN placement
and fill, the emulator's side is still refused while the broker's resting order may fill. Rare
rather than routine now, and unfixable except by deciding the budget once — which is what
placement-time sizing does.

🔴 **IT MUST RUN BEFORE THE STRATEGY STEPS, WHICH IS WHY THE RUNNER CALLS IT AND NOT `_plan`.**
`request_fill` happens *inside* the step; by the time the bridge reconciles, the fill is already
sized. The lot ceiling can lag a bar because a venue's volume band is a standing broker property —
an account's remaining risk is not, and a bar-old figure is exactly the window another bot fills.

⚠ **EVERY unreadable input means NO ROOM, never unlimited** — an unreadable balance, an unreadable
book, a position carrying no stop. A budget that opens itself when the account is least healthy is
not a budget.

⚠ **The refusal half already existed and was NOT rebuilt.** `_record_refusal` has sent a HEALTH
Telegram message naming the reason since the cap landed, loud once per slot and reason then quiet.
What is new is the message for the account budget itself running out — **and its RECOVERY message
is what makes the silence safe**, because without it quiet means either *there is room again* or
*still full, not worth repeating*.

⚠ **`account_room_exhausted` / `account_room_restored` are HEALTH, not decisions**, for the same
reason `halted` is: they answer *why no trading at all right now*, never *why not this setup*. Most
of the time the budget is full while no setup exists, and a decision record there would record a
decision nobody made. A setup actually turned away still lands in the decisions stream.

⚠ **The live bot's own risk moved 10% → 5% in the same change, and then straight back to 10% the
same day once the second bot turned out to need building rather than configuring — it is the ONE
runtime-reloadable field**, so both moves reached the RUNNING bot on the next VPS `git pull`, with
no promote and no restart, applied at the next moment it is FLAT. ⚠ **That bot was BUILT later the
same day and is benched**, so this number moves back to 5.0 when it is ready to be armed — and
before it is assigned, never after. 🔴 **10% is where it waits, and that is a decision
about which number is DESCRIBED rather than about appetite: every published figure for this bot —
the -54.9% max drawdown over 6.5 years, Run 12's finding that the drawdown is a losing STREAK at
this risk rather than give-back — was measured at 10%. At 5% not one of them described the running
bot.** ⚠ **`b_leg_demo` is benched and still states 10.0** — if it is ever put on this account
that number has to move first or the shares no longer sum to the cap.

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9** — and the first thing to watch is a bot being
SHRUNK rather than refused, which no test can prove and no bot has ever done.

**Tests: 6 in `backtest/tests/test_account.py`, 13 in `tests/test_live_bridge.py`. 14 mutations
watched RED with a surviving control each.** Three findings came out of running those mutations
rather than out of writing the code, and all three are the same lesson — *a test that cannot fail
is not a test*:
🔴 **A second floor at zero made the negative-room case untestable** — no single mutation could
produce a negative room, so the test asserting one cannot happen passed for free. One guard now.
🔴 **The exclusion rule was written TWICE**, here and in `_account_cap_check`, and it was caught by
two mutation anchors matching in two places. The premise inside it has already been wrong once
(2026-08-25, five copies of one order read as an empty account), and a premise in two copies is one
that gets corrected in one of them. `_others_risk` is the single definition now.
🔴 **A test named for a RESTING order was setting the position ticket**, so it exercised the wrong
half of a two-line exclusion and survived a mutation that emptied the other. Split in two, plus a
third pinning that an orphan under our own magic is still COUNTED.
⚠ **And deduplicating them briefly collapsed two refusal codes into one** — *the terminal would not
answer* and *the book carries something unmeasurable* call for different work, and a pre-existing
test caught it. Two failures must never share one message.

### 🔴 The shrink above could NEVER reach a broker — and the pool, the half-share minimum and the priority order (2026-09-15)

**Aaron's rule:** the cap bounds the risk OPEN at any moment, not the sum of the bots' shares, so
any number of bots may share an account. A bot short of room trades what is left, down to HALF its
own size; below that it is refused. When two signal together, the one higher in the account's
priority order goes first.

🔴 **FOUND: every shrunk entry was refused at the order check.** `order_sizing.plan_order` compared
the strategy's risk against `balance x exec_risk_pct` in BOTH directions, so an entry the strategy
had deliberately fitted to the room failed as `risk_not_authorised` — *"sizing off a balance the
account does not have"*. From 2026-09-03 to today a bot short of room was refused exactly as before
the shrink existed, under a reason that sent the reader to the warm-up equity. **That is the
paragraph above saying "nothing here has run against a broker", arriving.** ✅ The bridge now hands
the check the room the strategy was sized against; below a full share only MORE than the share is
refused, and with room for a full share the check stays two-sided.

🔴 **FOUND: a MARKET bot could never shrink at all.** A stated room refused every shrink at the FILL
(the resting-order rule above), and a market bot's fill IS its placement — so the extreme leg could
only ever be refused. ✅ The bridge now tells the account whether this bot's fill is its placement,
from the strategy's declared entry style (`SoloAccount.fills_at_placement`).

✅ **The half minimum** is `SHARED_MIN_GRANT_FRAC` in `backtest/portfolio/account.py`, applied only
once a room is STATED — a solo replay and every parity gate are untouched. ⚠ **Aaron's own example
(3% + 5% open, a 5% bot, 2% left) is REFUSED under it** — his call, made knowing that.

✅ **The priority order** is `account_priority` in each instance config (1 = first), written from
Bots → Accounts, read FRESH off disk every bar by `shared/account_priority.py`, so a re-order needs
no restart. A lower bot waits one poll plus 10s per tier ahead, **timed from the bar's close**, and
only on closes a higher bot also has. No shared file and no lock — a crashed bot can hold nothing.
⚠ An unreadable roster waits as if every better rank were there (rule 1). ⚠ Capped at 120s.
⚠ **"Share the room" between same-bar signals was NOT built** — it needs every strategy to announce
a trade before sizing it. Priority only.

🔴 **ROLLOUT ORDER MATTERS.** The order-check fix is in `algos/` and arrives by `git pull`; the half
minimum and the market shrink are in `backtest/` and arrive only by `promote.py`. Pulled BEFORE the
promote, a live bot could place a shrunk entry of ANY size above dust. **Promote first, then pull.**

⚠ **NOTHING HERE HAS RUN AGAINST A BROKER — rule 9.** Watch the first SHRUNK entry on demo 700152905.

**Tests:** `algos/tests/test_live_bridge.py` (shrunk entry placed — RED before the fix; oversized
and undersized still refused; market flag), `algos/tests/test_account_priority.py` (16),
`backtest/tests/test_account_share_floor.py` (8). Every guard watched RED by mutation.
