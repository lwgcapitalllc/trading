# Notes — Broker accounts, risk shares and bot P&L

The account registry, risk shares under a cap, the budget planner, box terminal scan, what a bot made. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The shares may not add up to more than the ceiling (2026-09-03)

Aaron: *"the risk per trade cannot add up to more than that cap"*. `bot_accounts.share_overflow`
is the rule; it returns the reason to refuse, or `None` when the shares fit.

🔴 **`AccountGroup.cap_takes_turns` had STATED this since 2026-08-09 — *a cap that lets both hold
has to exceed the sum* — and nothing enforced it.** A fact a module computes and reports is not a
rule; three separate writes could each produce an over-subscribed account and every one of them
saved cleanly.

⚠ **It is about the CONFIGURATION being coherent, not about safety, and the message says so.** The
live cap already stops an account exceeding its ceiling — it does that by making whoever asks LAST
take less, or nothing. So an over-subscribed account is not unsafe; it is a set of bots that
quietly stop being the bots that were backtested, because each only gets its full size when it
happens to ask first. **Refusing prevents a silent demotion, not a loss.**

🔴 **THREE write points, because there are three ways into the same broken state**, and guarding
one would have read as a rule while leaving two doors open: lower the ceiling under the shares
(`set_account_risk_cap`), add a bot (`set_bot_account`), or raise one bot's share
(`save_bot_runtime`).

⚠ **`share_overflow` is checked with the HYPOTHETICAL account assembled** — the joining bot counted
in, or the changed share substituted — never against what is on disk today. Checking the current
state would pass every write that creates the problem.

⚠ **`risk_pct_of` is the ONE definition of what a bot risks per trade**, used by
`group_by_account` and by the router assembling that hypothetical. Two ways of reading the number
is two answers, and the hypothetical is the one that drifts.

⚠ **An unreadable or unstated share REFUSES rather than counting as zero** (rule 1). A bot whose
risk cannot be read is not a bot risking nothing, and scoring it 0.0 would let a genuinely
over-subscribed account save cleanly — the one outcome the rule exists to prevent.

⚠ **No cap means nothing to check.** Uncapped is deliberate and supported; it is not a cap of zero.

⚠ **`_SHARE_EPS` exists because the INTENDED configuration is an exact fit.** Two bots at 5.0
against a ceiling of 10.0 must pass, and so must today's single bot at 5.0 under 10.0. A strict
comparison reddens both — measured, not reasoned.

⚠ **Benching is never refused, and neither is lowering a share or raising the cap** — freeing room
cannot over-subscribe anything, and a guard that blocked it makes an over-subscribed account
unfixable. 🔴 **This line said so from 2026-09-03 while the code refused a lowering whenever the
account stayed over afterwards** — fixed 2026-09-11; see *An account's risk budget is ONE planner*.

⚠ **A bot whose account has DISAGREEING caps is skipped rather than refused.** There is no account
cap to check against, and `live_config._assert_account_cap_agrees` already refuses to start it;
reporting a share overflow there names the wrong fault.

✅ **THE PAGE SHOWS THE RUNNING TOTAL SINCE 2026-09-04, AND THE FIX IS SMALLER THAN WHAT IT
FOUND.** `AccountGroup.share_total_pct` and `.share_overflow_reason` are served on
`GET /bots/accounts` and rendered under the cap editor: the shares added up, the ceiling beside
them, and — when they do not fit — the same sentence the save is refused with, before anybody
saves.

🔴 **THE PAGE ALREADY HAD A TOTAL AND IT WAS THE LENIENT COPY.** `AccountsTab.tsx` reduced the
shares with `?? 0`, so a bot whose risk could not be READ counted as a bot risking nothing — the
one leniency `share_overflow` refuses by name, three paragraphs up. **The browser could therefore
print a total that fitted under the ceiling on an account the save would refuse**, and the
take-turns sentence beside it said *"together they risk N%"* short by a whole bot's share with
nothing on screen to say so. Rule 1 arriving where it is quietest: nothing errors, and the
reassuring number is the wrong one.

⚠ **And that total only ever appeared inside the take-turns note**, which needs the cap to be at
or under the largest single share — **so the INTENDED configuration (two bots at 5% under a 10%
cap) never displayed it at all.** The way to find out the shares did not fit was to type a number
and be refused.

⚠ **SERVED, never re-derived in the browser.** Deciding *does it fit* from two numbers on the page
is the same rule written twice in two languages, which this repo gates against elsewhere and which
had already drifted here. `share_overflow_reason` is the SAME call the write path makes.

⚠ **`share_total_pct` is `None` when ANY share is unreadable — never a partial sum**, and the page
renders that as *cannot be totalled* rather than as a number. A partial total is worse than no
total, because it is a number and gets believed.

⚠ **A group with no bots totals `0.0`, not `None`.** `None` means a share could not be read; an
empty account has none at all, and 0% really has been handed out. The page builds exactly that
group for a registered account nobody is trading yet.

🔴 **THE ENDPOINT CHECK FOR THE TWO SERVED FIELDS SURVIVED ITS OWN MUTATION TWICE, FOR TWO
DIFFERENT REASONS, AND BOTH ARE RECORDED IN ITS DOCSTRING.** The first version asserted the KEY
was in the JSON — but the response model declares both with a default of `None`, so the key is
there whether or not the router assigns it (the `python` lock-scope trap, one section down: *ask
not only whether the model declares a field, but whether anything actually assigns it*). The
second compared the served values against the router's own grouping on the REAL configs — and
still could not catch the reason, because today's account holds one bot at 10% under a 10% cap,
so its shares FIT and the honest answer is `None`, **the same value an unassigned field defaults
to.** It drives a STUBBED over-subscribed group now, where the total is a distinctive number and
the reason is a sentence. **A comparison whose two sides agree by accident is not a comparison.**

**Tests:** 15 in `tests/test_bot_accounts.py` — 10 on the rule, 5 driving the three endpoints.
⚠ **A fail-watch is vacuous for a rule that did not exist**, so non-vacuity is by MUTATION: six
were run and each turned its own named test red — a strict comparison (which reddens BOTH exact-fit
cases), an unreadable share counted as zero, uncapped read as a cap of zero, and each of the three
endpoint checks deleted in turn. ⚠ **One mutation did NOT APPLY on its first attempt and proved
nothing** — the pattern did not match, the suite stayed green, and that reads exactly like a
surviving mutation. Assert the edit landed before believing the result.

## An account's risk budget is ONE planner, and a change that frees room is always allowed (2026-09-11)

Aaron: *"add bots to demo and live accounts … take bots off … increase or lower the percentage risk
on the bot … increase or lower the max percentage traded on the account … seamlessly."*
`bot_accounts.risk_plan` is the one planner: the runtime save, the cap save, the budget endpoints
and the Add bot preview all go through it.

🔴 **Every copy of the check refused an IMPROVEMENT.** Each asked *does the RESULT fit*, so lowering a
share on an account already over — 5+5+5 under 10%, one bot to 4% — was refused because 14% is still
over. **Now a write is refused only when the result does not fit AND the write adds risk** (a share
rises, a bot joins, the cap comes down or appears). Watched RED against HEAD on both endpoints.

- `PATCH /bots/accounts/{account}/risk` saves the cap and any shares in ONE commit
  (`BotAccountRiskRequest`; `risk_cap_pct` read through `model_fields_set`). ⚠ 404 on an account no
  bot is on — nothing to write the cap into; the first bot added sets it.
- `POST /bots/accounts/{account}/risk-plan` — the same plan, written nowhere, and it takes `joining`
  so Add bot can say whether a bot fits before the move. ⚠ `fits: false` is a 200. ⚠ `reason` (does
  not fit) and `refused` (a save would be refused) are different answers.
- ⚠ **The two one-click fixes are computed HERE, never on the page**: `fit_cap` (smallest cap the
  shares fit, rounded UP) and `fit_shares` (the shares scaled to fit, rounded DOWN; withheld when one
  falls under the runtime editor's 0.1% floor or the cap would pass 100).
- `AccountGroup.room_pct` is served on `GET /bots/accounts` — negative when over, `None` with no cap,
  never floored at zero, or an over-subscribed account reads as a full one.
- **The move carries the joining bot's share** (`BotAccountAssign.risk_pct`, the runtime bounds) and
  counts it in the join check. ⚠ **A move onto a registry-`live` account needs `confirm_live`** (409
  without) — the one-bot move was the unguarded second door to real money.
- 🔴 **A move asks whether the bot runs in THREE states** (`_bot_running_state`): *could not ask*
  read as running told the reader to stop a stopped bot; it answers 503 now. ⚠ The STOP path still
  reads it as running (`_bot_is_running`), which there is the safe wrong answer.
- 🔴 **Start and restart refuse a bot on no account** (409). They answered 200 and sent STARTING to
  Telegram over a bot the box then refused.
- ✅ **A cap change needs no restart** — the bot adopts it the next time it is flat
  (`algos/CLAUDE.md`); `restart_required` is False and `applies` says so. ⚠ Pinned by a test that
  READS `algos/live/live_config.py`. ⚠ **A bot started on the older runner drops a cap-only change**
  until its next restart.
- ⚠ The browser guard refuses all three risk writes and allows the plan.

**Tests:** `tests/test_account_risk.py` (31). **21 mutations planted in memory, 21 killed** — each
named in its test's docstring.

## A shared stack's legs may not add up past its cap (2026-09-10)

Aaron: *"if I put ten percent cap, then the strategies that I choose cannot trade more than the
cap… they cannot add up to more than the risk cap."* `services/stack_risk_budget.py`; the launch
refuses (400) and `POST /backtests/stacks/risk-budget` serves the same answer to the form.

🔴 **The decision is `share_overflow`, the rule above — never a second comparison.** Only the
sentence is the stack's own. Over the cap the legs take turns, which is an account the Bots page
refuses to assign, so the stack would measure something nobody can deploy.

- ⚠ **A leg's share is its per-trade risk setting** (`risk_pct_of`, the Bots page's reader): one
  position per leg, a re-entry risks less and only follows a closed primary, an add only spends
  locked profit. **An unreadable one refuses** (rule 1).
- ⚠ **The loss-recovery leg COUNTS** — it can hold while its parent opens the next trade. Share =
  parent risk × the rule's fraction: the request's, else the rule's stored default. A stated but
  unreadable fraction refuses rather than falling back.
- ⚠ **Checked before the history floor**, which can reach the box. **Screens are never checked** —
  no shared account to cap.
- ⚠ **`fits=false` is a 200** from the check — a legitimate question, not an error.
- 🔴 **The shipped defaults did not fit until 2026-09-13**: SOS Fade 10% + extreme leg 5% = 15%
  under the 10% default cap, so that pair was blocked. SOS Fade's default is 5% since then — the
  live bots' own 5 + 5 — so the pair fits exactly. A rerun of an older over-cap stack is still
  refused.
- ⚠ **Nine existing launch tests went red and none was a defect**: their fixtures stated no risk. Each
  now states one that fits and says why; none had risk as its subject.

**Tests:** `tests/test_stack_risk_budget.py` (13), **8 mutations run, 8 killed** — a private sum
with no tolerance (0.1 + 0.2 under 0.3, premise asserted), an unreadable share read as zero, the
recovery left out, the launch refusal dropped, the refusal applied to screens, a malformed fraction
falling back, the check ignoring overrides, an over-cap total reported as fitting.

## The account REGISTRY — the gap that made moving a bot a manual afternoon (2026-08-12)

`services/bot_account_registry.py` + `algos/markets/fx/accounts.json` + four endpoints under
`/bots/accounts/registry`.

🔴 **`bot_accounts.group_by_account` DERIVES which bots share an account, and that derivation is
correct and must stay — but it can only ever see accounts a bot is ALREADY on.** So the first bot
onto a new account had nothing to be moved to, and `set_bot_account` said so out loud: *"No
registered bot trades account N, so there is no account here to join — its server, terminal and
risk cap are read off the bots already on it. Assign the first bot to an account by editing its
instance config."* That refusal was honest and it was a wall: the 2026-08-12 move of
`sos_fade_demo` from the PU Prime Standard demo to the ECN one was a hand-edited config on the
VPS **because of this sentence**.

The registry holds the facts about an ACCOUNT that a bot must adopt to trade it, and nothing a bot
is authoritative about.

⚠ **THE RISK CAP IS NOT IN IT AND MUST NEVER BE.** The cap is an account-level number stored per
INSTANCE, because an instance config is the only file a bot reads — so the account's cap is
whatever its bots say it is, and `group_by_account` reports it and refuses when they disagree. A
copy on a registry row would be a second answer able to drift from the bots actually running,
which is the one shape this whole subsystem exists to avoid. **The registry says what an account
IS; the bots say what they are doing on it.**

🔴 **So an account with NO bot has no cap, and the FIRST bot is where one is chosen (2026-09-11).** It
used to start UNCAPPED with a note — then the watchdog started it within a minute, and a cap saved
after could not reach the running process (and saving a cap on an empty account answered 404: no
config to write it into). `BotAccountAssign.risk_cap_pct` now carries the page's choice into
`assign_plan(first_cap_chosen=, first_cap=)`. ⚠ **Read through `model_fields_set`, never the value**:
absent = not chosen (the old uncapped-and-say-so path), `null` = chose uncapped, no note. ⚠ **On an
account that already has bots a chosen cap must MATCH theirs or it is refused (409)** — the page
offers it only for an empty account, so a mismatch means the account gained a bot since. ⚠ The share
check reads the cap the plan writes, so a first cap under the bot's own risk is refused like any
overflow. Tests: 7 in `tests/test_bot_accounts.py`; 5 mutations run, 5 killed.

### The field the ECN move forgot

🔴 **`assign_plan` wrote FOUR fields and the symbol was not one of them.** PU Prime quotes gold as
`XAUUSD.s` on its Standard book and `XAUUSD.p` on Prime and ECN, so a move that writes the login
and leaves the symbol produces a bot pointed at a symbol its terminal does not quote — **and
nothing errors**: it connects, warms up, and receives no bars, which reads exactly like a quiet
market. `strategy_params.account_profile` had the same hole, one level quieter (inert live, and a
file claiming one broker's costs while trading another's).

`AssignPlan` gained `param_fields` (keys inside `strategy_params`, which a flat dict cannot
express) and `notes`. **The symbol is REBASED, never copied from a peer** — the instrument is the
bot's and only the suffix is the account's, so two bots on one account can trade gold and a
currency pair without either being rewritten onto the other's market.

⚠ **A fact the registry does not carry is REPORTED in `notes`, never guessed.** An account with no
recorded suffix leaves the symbol alone and the endpoint returns the sentence saying so. `null` and
`""` on `symbol_suffix` are DIFFERENT: `""` means this broker quotes bare symbols and really does
rewrite `XAUUSD.s` → `XAUUSD`; `null` means nobody recorded it. Collapsing them is what silently
strips a suffix off a live instrument.

🔴 **A SEVENTH FIELD, AND IT TOOK A LIVE BOT OUT ON THE FIRST MOVE TO REAL MONEY (2026-09-11).**
`sizing_basis_adjustment` shrinks the balance a bot sizes from by an amount MEASURED on one
account. The go-live move carried SOS Fade's -4518.23 (the demo account's duplicate-fill windfall)
onto a $451.97 live account, where it left nothing to size on and the bot refused to start. A move
to a DIFFERENT account now clears a non-zero one to 0 and says so; the same account keeps it; the
bench leaves it; a bot with none gets no write. `assign_plan` takes `current_account` and
`current_adjustment` from both callers. Tests in `test_bot_accounts.py` / `test_go_live.py`, 4/4
mutations killed.

### The refusals, and which of them is a "definite no"

- **An account with no terminal (`mt5_path: ""`) is UNASSIGNABLE.** A bot connects by attaching to
  a running terminal already logged into the account it claims to trade; without one the move is
  written, committed, pushed and pulled and then fails at `connect()` **with a message about
  CREDENTIALS**, pointing the reader at the password rather than at the missing terminal. It is a
  real state, not a hypothetical: the two tier-probe accounts were logged into MT5_Lab for minutes
  to read a spread, and MT5_Lab drives the backtest agent.
- **A move onto an account with no stored password is refused (409) — on a DEFINITE no only.**
  `_accounts_with_a_password()` returns `None` when the VPS could not be asked, and refusing on
  that would send the reader to re-enter a credential that is already there. Same three-state rule
  as `mt5_link`, applied to a pre-condition rather than to a reading.
- 🔴 **A bot HOLDING A TRADE is not moved or benched (409); an unanswered check is 503
  (2026-09-13).** Stopped, its trade stays open on the account it leaves with nothing managing it,
  and on a new account it halts at its next start, holding a record of a trade that terminal lacks.
  `_holds_position` reads the bot's own `position.json` on the box (written on the fill, deleted on
  the close), so a STOPPED bot is covered — the heartbeat is not. The whole-set go-live asks it of
  every bot. ⚠ Two explicit words, `HELD` / `FLAT`; an empty reply is *could not ask*. ⚠ Asked only
  when the account CHANGES. Tests in `test_bot_accounts.py` / `test_go_live.py`; 8 mutations, 8
  killed.
- **Unregistering an account a bot still names is refused (409).** That bot would go on trading an
  account this page can no longer describe.
- 🔴 **A terminal another account already holds is refused (409), before the password is written
  (2026-09-13).** A terminal holds one login, so two accounts on one terminal means a bot on either
  logs it off the other, under its bots — the demo bots' terminal was nearly saved onto the new live
  account. Compared as the scan's join key, so a different spelling cannot slip past; an empty
  terminal and an account's own terminal are never a clash. ⚠ `check_entry` runs every refusal
  before the VPS password write, so any refused save leaves nothing behind.
- 🔴 **The lab's backtest terminal is refused outright (400, 2026-09-13).** The backtest agent
  drives it, so a bot there would trade through the terminal the backtests run on. Same key the
  scan uses (`terminal_scan._LAB_KEYS`, held to `mt5_agent.py` by test).
- **An account that is neither registered nor traded by any bot is a 404** with the fix named.

### The password path

`PUT /bots/accounts/registry/{account}/password`, and `BotAccountRegistrationWrite.password` on the
same write.

⚠ **The secret goes over STDIN, never in argv.** An argument is visible in the process list on the
VPS and on this machine — base64 does not help, since it is an encoding rather than a secret.
`_write_users_vps` next door may use argv because a Telegram chat id is not a credential; this
cannot.

⚠ **There is NO read counterpart and there must not be one.** The page needs one bit — will this
move be able to connect — and `GET /bots/accounts/registry` answers it as `has_password`, a
boolean, without the secret leaving the box.

⚠ **The remote script REFUSES on a parse failure rather than starting from `{}`.** Every write is a
read-modify-write of the whole credentials file, so a failed read that answered "empty" would
delete every other credential on the box — the `users.json` defect of 2026-08-04 with far worse
consequences. The write is confirmed by a MARKER, because a remote Python traceback exits non-zero
with empty stdout, which `_ssh` correctly does not read as a connection failure.

### The registry file itself

⚠ **`_read_raw` treats a MISSING file as empty and an UNREADABLE one as an ERROR.** Same reasoning:
a write rewrites the whole file, so collapsing those two is destructive rather than merely wrong.

⚠ **`upsert_account` REPLACES a row rather than merging into it**, so a field cleared on the page is
cleared on disk — a merge makes removing a symbol suffix inexpressible, because the absent value
and the unchanged value become one request. It preserves any `_`-prefixed PROSE key a human wrote
on that row, because the page cannot express one and a write from it must not delete an explanation
left for the next reader.

⚠ **`account_profile` is validated against `backtest.fills.PROFILES`**, and `known_profiles=None`
means the caller could not supply the roster so the check is SKIPPED — the caller's decision to
state, never a silent pass. A name nothing can price is a backtest that refuses and a live config
claiming a broker it cannot name.

**Tests:** `tests/test_bot_account_registry.py` (27). ⚠ **A fail-watch against HEAD is vacuous —
the module did not exist** — so non-vacuity is by MUTATION and each docstring names its own; twelve
were run, each turning its named test red.

🔴 **One of those mutations wrote the REAL `b_leg_demo` instance config, in the working tree, on
the machine running the suite.** Neutering the password pre-check let the refusal test fall through
to the write and move a live bot off the bench onto the ECN account; nothing errored, and it was
caught only because `git status` was checked afterwards. `tests/conftest.py` gained
**`_no_live_bot_config`**, the local twin of `_no_live_vps`: the VPS interlock covers HTTP and SSH
because those are how a test reaches the box, and **an instance config is a plain file in this
repo, so a test reaches a live bot's settings with no network at all.** `deploy: False` is exactly
the shape somebody writing a refusal test reaches for, and it is the shape that leaves the change
on disk unnoticed until it is committed with something else.

**The standing lesson is about what a DERIVED answer cannot cover: deriving the grouping from the
bots was right, and it left a hole shaped exactly like the first bot on a new account — a case that
looks like a missing feature and is really the derivation being asked a question it has no input
for. When a value is derived, ask what it answers before the thing it derives from exists.**

## "Backtest these bots" — `GET /bots/accounts/{account}/stack-basis` (2026-09-10)

What an account's bots RUN, as the stack builder's starting point. Read only; the planner is
`services/account_stack_basis.py`, pure. 🔴 **The bot's own settings, never the strategy's
defaults** — MEASURED on 700152905: SOS Fade's lab default risked 10% (5% since 2026-09-13), the bot 5%, so the old
Accounts-tab pre-fill asked for 10 + 5 = 15% under a 10% cap and the budget check refused it (the
bots' own settings fit exactly). ⚠ **Each leg is sent COMPLETE** (stored defaults with the bot's
pins over them), because a stack's per-leg settings replace the defaults rather than merge.
⚠ **Imports its rules, never restates them**: `group_by_account` (who shares the balance),
`_only_declared` (a setting the strategy no longer has is left out and COUNTED), `_bot_tf_minutes`
(the chart), `risk_pct_of`. ⚠ **Refuses, with a sentence, as a 200**: an unreadable config ANYWHERE
(it might be on this account, and a backtest without it is one bot short), fewer than two bots,
disagreeing ceilings, a strategy the lab cannot run or that needs a parent, two bots on one
strategy, two instruments. **A refusal carries no half-built plan.** ⚠ **It cannot carry the CODE**:
the lab replays this machine's strategy while a bot runs its deployed snapshot, and the page says so.
⚠ **Gap, stated**: a bot pinning `exec_recovery` on would be backtested with it pinned off (shared
stacks run recovery as its own leg) and nothing here says so yet — no bot has it on today.
Tests: `tests/test_account_stack_basis.py` (19); **10 mutations run, 10 killed**.

## Checking the account list against the BOX — `services/terminal_scan.py` (2026-09-10)

`GET /bots/accounts/scan` asks the VPS which account each MT5 terminal is logged into
(`algos/tools/scan_terminals.py`) and joins it against the registry. Until this existed **nothing
ever compared the account list with the machine**, and a terminal had been sitting on a LIVE
account (34957946, PUPrime-Live) for a day with this app unable to see it.

🔴 **The box is authoritative about what is LOGGED IN; the repo stays authoritative about INTENT.**
The scan writes nothing. **`POST /bots/accounts/registry/sync` (`services/account_sync.py`,
2026-09-10) applies its findings BY RULE, and only when a person presses Sync** (Aaron: *"not a
scan, a sync"*, *"100% manually triggered by me only"* — so no timer, no page-load call).

🔴 **SCAN FIRST, THEN SYNC — and the press names the plan it approves** (Aaron, same day: *"it
doesn't show me what it is going to do before I do it"*). `GET /bots/accounts/scan` returns the
PLAN (`AccountSyncPreview`: every change field by field — what the list says, what it will say,
and how the scan knows — plus `plan_id`). The POST **requires** `expect_plan`, re-scans, re-plans,
and when the fingerprint moved **writes nothing** and returns `plan_changed` with the new plan in
`now`. ⚠ **Re-planned at the write, never a cached plan replayed** — the never-change-a-bot's-account
rule is only true when it is checked at the moment of the write. ⚠ **The fingerprint covers only
what would be WRITTEN** (account, add/update, each field's was → value): the note is out because it
carries a date and a midnight rollover would refuse a valid press; attention is out because nothing
is written from it. ⚠ **A diff is words**, never a field name or a path: `before` is `None` on an
add (*not in your list yet* is not *blank*), and the instrument ending reads `not recorded` /
`none` / the ending — three states, never two.

The rules, each because the alternative fails silently:

- 🔴 **An account a bot's config names is NEVER changed** — `runner._check_account_identity` halts
  a bot because a terminal's login can move under it, and writing the box's answer there would
  resolve that alarm by agreeing with it. It comes back as ATTENTION instead, and a bots' terminal
  on the wrong account is ONE alarm, not also a wrong row.
- 🔴 **A terminal is only ever CLEARED, never SET, and an empty one is never filled.** Clearing a
  contradicted claim makes the account unassignable (the safe direction); setting one is intent.
  The tier probes were logged into the lab's terminal and deliberately left with none — a sync
  that filled it would point a bot at the terminal the backtests run on. An ADDED account arrives
  with no terminal and no password.
- ⚠ **Nothing is removed**; unverified is not gone. ⚠ **Only server, demo-or-live and the symbol
  ending are written**, and demo-or-live only as `demo`/`live` — `contest` or nothing is attention.
  ⚠ **Two terminals disagreeing about one account resolve to nothing**, never a pick.
- ⚠ **One unreadable bot config BLOCKS the whole sync** (rule 1 — no way to show an account is
  untraded). ⚠ **Writes land on the row as it is on disk NOW** (field deltas, adds skipped if
  somebody added it meanwhile) — the scan takes minutes. ⚠ **One lock, one commit**; a push that
  fails keeps the local write and reports `deploy_error` rather than a 500 that hides it.
- ⚠ **Under `/registry/` on purpose**: the browser guard's account-write rule already refuses it.

Tests: `tests/test_account_sync.py`; **29 mutations run, 29 killed** (12 of them on the
scan-first half, incl. a malformed one re-written because a TypeError is not the rule going red).

🔴 **AN ACCOUNT CAN BE LOGGED IN ON MORE THAN ONE TERMINAL, and the first version assumed it could
not.** On this box the demo account is open in the bots' terminal AND the lab's at the same time,
which is normal. Comparing a row's terminal against wherever the account was found reported **the
one entirely correct row in the list as wrong** on the first live run. A row's terminal claim is
judged by asking THAT terminal what it is logged into; nothing else can contradict it. Broker facts
(server, demo-or-live, suffix) belong to the ACCOUNT and any terminal on it is evidence about them.

🔴 **`asked=false` is not an empty box.** A scan that could not RUN is a **502 carrying why**; a
scan the box REFUSED is a **200 saying so** — the channel worked and the answer was "I will not",
so a 502 there would send the reader at the network instead of at the script. A payload that is
not readable JSON raises rather than defaulting: a truncated pipe or an SSH banner would otherwise
read as a healthy scan of zero terminals.

⚠ **"Could not be asked" is UNVERIFIED, never contradicted.** A stopped terminal, or one a bot
trades through and is deliberately not attached to, produces no reading. Grading those as findings
fills the page with false alarms and teaches everyone to scroll past the real one.

⚠ **A registry field that is UNSET is not a conflict.** Only a field that is set and different
counts, or incomplete rows bury the real disagreements.

⚠ **A discovered account pre-fills only what the box MEASURED** (`suggested_registration`). Label,
tier, cost profile and note stay empty for a person — a guessed cost profile prices every backtest
on that account, and this repo refuses an unmeasured cost rather than borrowing a sibling's.

⚠ **There is no password and there cannot be** — the terminal encrypts it at rest, so a discovered
account arrives unusable by a bot until somebody stores one. That is the honest state rather than a
surprise at connect time, and a present-but-empty field would read as "this account has no
password", which is a different claim.

🔴 **A row with NO terminal is OFFERED one, never given one (2026-09-13).** Aaron: *"When I hit
scan VPS, you already know all the information. Why do I have to put it in?"* — and the path typed
by hand was the demo bots' terminal. `_suggest_terminal` fills `RegistryCheck.suggested_terminal`
(the exe path) and `terminal_note` (why, or why not); the account form fills an EMPTY field with it
and the person's Save records it, so Sync still never SETS a terminal. ⚠ **Only a terminal nothing
depends on**: never one a bot's config names, one another account claims, or the lab's
(`_LAB_KEYS`, a copy of `mt5_agent.py`'s path, held to it by test). ⚠ **Two free terminals offer
neither** — which one is the person's call. ⚠ Declared on `models.RegistryCheck`, or Pydantic drops
both. Tests: 11 in `test_terminal_scan.py`, 1 in `test_terminal_scan_endpoint.py`.

⚠ **It is NOT on the 60-second poll, deliberately** — a scan can take minutes when several
installed terminals are stopped, so polling would stack slow requests against the box. `_ssh`'s 30s
timeout is wrong here for the same reason and this call has its own.

✅ **A row pointing at a BOT'S terminal is checked through the bots on it (closed 2026-09-10).**
The scan never attaches there, so until then every such row came back UNVERIFIED — exactly where
700107749's stale claim sat. The live runner now writes the account its terminal is ACTUALLY on
(`observed_account`, off the same `account_info()` call it halts on) beside the configured one, and
the box-side scan attaches each bot's own reading to the terminal it owns (`reported_by_bots`). ⚠ **The OBSERVED number, never the configured one**
— the configured account lives in the same repo as the list, so checking one against the other
proves nothing. ⚠ **A bot that could not ask contributes nothing, and bots that disagree resolve to
unknown**, since one terminal holds one login. ⚠ **`account_source` says which evidence it was**
(`terminal` = the scan asked, `bot` = a bot reported) and it must stay in the response model: a
dataclass field the model does not declare is DROPPED without a word, and this one was.
⚠ **It lights up only once a bot restarts onto the new runner** — until then the bots report
nothing and the row stays unverified, which is the honest answer.

⚠ **Every `detail` and conflict string is a sentence a PERSON reads** in the Scan VPS drawer, so
it names a terminal by its folder (`_short`: `C:\\MT5_FFT\\terminal64.exe` → `MT5_FFT`) and never
carries a path. A test fails on `terminal64.exe` in any of them.

⚠ **A scan briefly slows the lab's MT5 agent, and the sidebar reads slow as DOWN — MEASURED, and
mostly not this feature's doing.** Polled every second: 22/22 answers with nothing running, 3
missed during a scan, and **the page's own 60s fleet refresh alone misses one too**. The agent's
terminal link never dropped; its `/status` answered past the health check's timeout while the box
was busy. So the "MT5 Agent down" flicker predates this and is the health light reading a slow
answer as a dead one (rule 2) — fixed in `_agent_state`, see *A SLOW agent is not a DEAD agent*.
✅ **The scan asks the box ONCE (2026-09-10).** It used to fetch the whole fleet snapshot over a
second SSH call just to read each bot's observed account; the box script now reads those itself and
sends them inside the scan, taken at the same moment as the terminals.

Story and the false alarm: `command-center/docs/BACKEND_BUILD_NOTES.md`.

## 🔴 An assignment may only write a param the RECEIVING strategy declares (2026-09-04)

**`runner._build_strategy` refuses to start on any `strategy_params` key the strategy's config
class does not declare** — *"they would be ignored, so the bot would trade settings you did not
choose."* ✅ **That refusal is right and stays.** 🔴 **`assign_plan` wrote the account's
`account_profile` into every bot it moved without asking whether that strategy has the field**, so
assigning `extreme_leg_demo` produced a bot that connected to the broker and refused to start on
every attempt.

🔴 **THE SHAPE: a write that is correct for every EXISTING receiver is not a correct write.** Both
strategies that had ever been assigned declare that field, so the rule had a 100% pass rate right up
to the first one that did not. **Rule 7 pointed the other way — the WRITER made a claim about a
receiver it never read.**

✅ **Filtered ONCE at the end of `assign_plan` (`_only_declared`), never at each write site**, so a
param this function learns to carry tomorrow is covered without anyone remembering the rule, and
✅ **the declared set is read off the same dataclass the bot constructs** (`LAB_STRATEGY["config"]`)
— a second statement of what a strategy accepts is the one that drifts.

⚠ **`declared_params=None` means COULD NOT ASK and it writes anyway, deliberately** — the one place
here that does not refuse on an unanswered question. Writing gives a bot that refuses to start and
names the field; skipping gives a bot that starts and trades an account with another broker's costs
recorded against it. **A note says it was unchecked.** ⚠ **This fails LOUDLY; the symbol-suffix trap
in the same function does not** — a wrong suffix gives a bot that runs and receives no bars.

## The account's net is measured off what went IN (2026-09-12)

`account_earnings` takes `net_basis = "deposits"` whenever a bot on the account reports
`capital_in` beside its balance (or, for an account its bots left, when their last pulse carried
it): **net = balance − capital_in, and `net_pct` is the bot's own time-weighted figure, passed
through and never re-derived here.** The live account read +2,181.67% because a $9,860.51 transfer
counted as growth. Rules and evidence: `algos/CLAUDE.md` → *A deposit is not a return*.

- 🔴 **The balance and `capital_in` come from ONE reading** — the bot row carrying `capital_in`
  supplies the balance too, and a past reading's figures come off one pulse — or a net is one poll's
  balance less another poll's deposits.
- ⚠ **The deposits basis covers the account's WHOLE life**, so departed bots' trades count toward
  `attributed_usd` and get a share, exactly as on the account's own opening (`whole`).
- ⚠ **A bot's `pct_of_opening` divides by `capital_in` on that basis** — the name predates it; a
  share of an opening a deposit has dwarfed is the same bug one column over. Nothing once
  `capital_in` ≤ 0.
- ⚠ **No `capital_in` keeps the `opening` basis** — an older runner, no link, or a history that did
  not add up. Never read that absence as nothing put in; `_num` refuses a bool.
- ⚠ **`capital_in` and `net_basis` are declared on `AccountEarnings`**, or Pydantic drops them.
- ⚠ **An account switches basis only once its bots restart onto the new runner**, so the page can
  show one basis for one account and the other for the next; `net_basis` is what tells them apart.

Tests: 10 in `tests/test_bot_earnings.py` (one over three bad values), the fleet endpoint's hand-off
included. **16 bugs planted in memory, 16 caught** — one survived first: the only departed-bot case
had an opening reading from before its trade, so it counted either way and could not tell the two
bases apart. It has a case with no such reading now.

## A balance is an account's only if it was READ on that account (2026-09-14)

🔴 **Taking a set live showed the demo's equity on the live account.** Measured the night
`extreme_leg_2` and `sos_fade_2` went from demo 700152905 to live 35710389: both connected to the
live terminal, read **$0.00** and refused to start — yet the live card showed **$15,844.46**, the
demo's balance, and **+$5,844.46 "not from these bots"**, that balance less the demo's $10,000 in.

**The pairing is made on the box and refused here.** `bot_state.set_started` re-stamps a record's
`account` from the config on every launch and leaves the last `balance`, `capital_in` and
`total_pnl_pct` in place, so a stopped bot's record paired the NEW account's number with the OLD
account's reading. The snapshot passed that pair on, and the page took it as the account's equity.

- 🔴 **`get_snapshot` passes a bot's balance, `capital_in` and `total_pnl_pct` on only when its
  `observed_account` — the account the terminal reported off the same `account_info()` call — equals
  the account the bot's CONFIG names** (`_read_on`). One reading, so the three stand or fall together.
- ⚠ **Against the CONFIG, never the record's own `account`.** The page lays a row by its config, and
  between a move and the restart the record names the old account in both fields.
- ⚠ **`starting_balance` is gated the same way on `starting_balance_account`** — an anchor for the
  account a bot left is not this one's opening.
- ⚠ **A reading that does not say where it was read is refused**, never assumed to be here. Every
  runner since 70af8458 (2026-09-10) writes `observed_account`; both live bots' frozen code has it.
- ⚠ **What the card shows instead:** only what MT5 gave — a running bot's balance; else the newest
  reading a bot took THERE, with its time; with none, a dash. A move never carries a number across.
  Since the same day the bot writes MT5's reading the moment it connects, so a bot that then
  refuses to start still leaves the account's real figure (`algos/notes/account-accounting-and-status.md`).
- ⚠ **Every door is covered** — take live, a single move, a hand edit — because it is checked where
  the balance is READ, not where the move is made.

Tests: 4 in `tests/test_bot_registry.py`. Three went red on the unfixed code with the demo's
$15,844.46 on the row; the fourth is the control. Five in-memory mutants, each caught by at least one:
the record's own account instead of the config's, the anchor ungated, the balance ungated, everything
blanked, a missing read-on account let through. The deposit hand-off test in `test_bot_earnings.py`
now states where its reading was taken — it had a balance on a benched bot that named no account.

⚠ **Open on the box, not fixed here** (`algos/`, a promote to take effect): Telegram's `/balance`
prints each record's `balance` beside a LIVE/demo label off its config, so it shows the same stale
pairing. And the runner's startup refusal on a $0.00 balance says *Could not read the account
balance* — it did read it; the balance is zero, which is rule 1 inside an error message.

## What a BOT made, and why it may not be the account's growth (2026-09-05)

🔴 **A TRADE BELONGS TO THE ACCOUNT IT WAS MADE ON, NEVER THE ONE THE BOT IS ON NOW (2026-09-11).**
The day the demo set went live, the live account showed the bots' demo trades as its own (+264% on
a $451.97 account with no trades). A trade row names no account, but each run's `startup` does
(`health-*.jsonl` since 2026-08-05, `decisions-*.jsonl` before), so `bot_earnings` places a trade on
the account of the latest startup at or before it — the box's live read now fetches those startups
too, or a run begun since the last sync lands on the account before it. ⚠ **An account a bot LEFT
keeps its trades** as `former` rows with `moved_to`, and a departed bot is never given a share of a
CURRENT bot's anchor. ⚠ **A trade no startup precedes is counted (`unplaced_trades`), never
credited.** ⚠ `former`/`moved_to`/`unplaced_trades` are declared on `BotEarnings` — undeclared,
Pydantic dropped them and a departed bot read as current. Go-live's demo record is scoped to the
account being left. Tests: 8 mutations run, 8 killed.

🔴 **AN ACCOUNT ITS BOTS LEFT IS STILL AN ACCOUNT (2026-09-11).** Aaron: *"moving bots to a live bot
doesnt mean we dont trade on the demo still."* It had no balance, net or Return % because nothing
read its balance once no bot was on it — but every bot's 15-minute `pulse` in `health-*.jsonl`
carries `account` and `balance`, so `balance_readings` recovers it. The account's LAST reading is
its balance, served with `balance_read_at`; its FIRST is its opening, **valid only if taken before
the first trade there** (a later one already holds a trade's money, so it refuses). The remainder
comes off that opening only when the balance is live or the last reading is at or after the last
trade; departed bots' Return % counts on it too. With no such reading a current bot's anchor is
used and the remainder is REFUSED rather than guessing its window. ⚠ A pulse with no numeric balance
is skipped — a link down is not a reading of zero. ⚠ `balance_read_at` is declared on
`AccountEarnings`, same Pydantic reason. MEASURED on 700152905 with both bots on live: $15,844.46
read 2026-09-10 23:51 UTC, opening $9,996.99, net +$5,847.47 (58.49%), remainder $3,344.80. 7 new
tests, 10 mutations run, 10 killed.

🔴 **A STRATEGY'S RECORD ON AN ACCOUNT CARRIES ON WHEN A NEW BOT TAKES OVER (2026-09-11).** Two demo
copies put back on the demo account after its bots went live drew at $0, beside two rows holding the
account's whole demo record under "moved to live". Aaron: *"if I add back bots on the demo they
should just pick up where they left off."* `_carry_on` folds a departed bot's trades on an account
into the ONE current bot running the same strategy there (`strategy_package`, off the configs in the
repo — the snapshot passes it as `strategy`), and the row names whose they are (`carried_from`,
declared on `BotEarnings` or Pydantic drops it). ⚠ **Display only**: the opening, the attributed
total, the remainder and the no-record list are all taken BEFORE the fold, so no account figure
moves. ⚠ **No heir, no fold**: two copies of one strategy on an account, or a strategy that could
not be read, leave the departed row standing. ⚠ Carried dollars get a Return % only on the account's
own opening, the same rule a departed row follows. ⚠ Go-live's demo record is still per BOT — this
is the page's view, not the promotion's evidence.

🔴 **A bot that has not REPORTED yet no longer blanks the balance (2026-09-11).** The last reading
was served only for an account NO bot is on, so adding the first bot to the demo account read
"balance unread · net unknown" until the new bot reported. It is served whenever nothing on the
account reports one, with `balance_read_at`. ⚠ That lets a past reading reach the anchor branch for
the first time, so the remainder's covered-window check (a trade closed after the reading is not in
it) is asked there too. Tests: 14 new across this file and `test_bot_accounts.py`; 14 mutations run
in memory, 14 killed.


`services/bot_earnings.py`, served on `GET /bots/snapshot` as `earnings`. Aaron: *"how much
percent each bot made on the account thus far … that 45% increase was only from the SOS Fade.
That should still be showing zero percent from the extreme leg."*

🔴 **The only P&L this app had was a fact about the ACCOUNT wearing a bot's name.**
`total_pnl_pct` is `(balance − starting_balance) / starting_balance` and `balance` is the
ACCOUNT's, so every bot on a stack reported the same figure — a bot deployed yesterday claimed
credit for everything the account had ever done, in green, beside its name. Nothing errored.

**The one honest source is each bot's own ledger**, `algos/ledger_archive/<bot>/ledger/
decisions-*.jsonl`, where a closed trade carries `pnl_usd` and `r`. That is a record of what THIS
bot did, so it cannot pick up a neighbour's trade, a manual fill or a deposit.

🔴 **THE SUM DOES NOT RECONCILE TO THE ACCOUNT, AND THAT GAP IS THE FINDING.** MEASURED on PU
Prime ECN demo 700152905, 2026-09-05: the account is up **$4,541.89** from its $9,996.99 opening,
of which SOS Fade's two closed trades are **$1,197.09** and the extreme leg has closed none. **74%
of what this page used to credit to "the bots" was not theirs.** `unattributed_usd` is therefore
REPORTED, always, and is not an error path — dividing it between the bots would credit a strategy
with money it did not make.

⚠ **An account's OPENING is not any one bot's anchor.** Each bot anchors what the account held
when IT arrived, so a bot joining a grown account states a much higher number and both are right.
`_pick_opening` takes the anchor of the bot with the EARLIEST ledger record and **serves
`opening_from` so the pick is checkable**. A bot with no record can never be chosen while one with
a record exists. Nothing anchored ⇒ it REFUSES and states why, never `opening = balance` (an
account that doubled would read flat) and never 0 (a division by nothing).

⚠ **`traded: False` means NO RECORD WAS READ, never "it made nothing"** — every figure is `None`
there. A bot running a month having taken nothing is a MEASUREMENT and reads `traded: True,
closed_trades: 0`. Collapsing the two is rule 1 in a table cell.

⚠ **`bots_without_record` is named, never folded into the unattributed figure.** While it is
non-empty the split is a FLOOR, and a page that cannot say so shows an incomplete split as a
complete one.

⚠ **It rides on the snapshot rather than an endpoint of its own** — the balances and anchors it
joins to have just been fetched over SSH, and a second endpoint would pay that round trip again
to answer half a question. The ledger half is LOCAL (the committed archive), so it answers with
the box unreachable, and it is wrapped so it can never take the snapshot down.

⚠ **Cached on a FINGERPRINT of the record** (file count + newest file's name/size/mtime), not on
an interval — a live bot appends to today's file, so the cache turns over on its own and there is
no window to be stale inside. MEASURED: 4.7–5.4ms warm, 19.6ms on a cold disk, 61 files.

🔴 **The pre-filter rejects on the KIND only, and narrowing it is what made the test real.**
Filtering `"closed"` there too made the structured `event == "closed"` check INERT — a mutation
deleting it changed nothing, so the test covering it passed against its own defect. MEASURED: it
cost nothing, because exactly **4** of 2,872 lines reach the parser either way.

✅ `tests/test_bot_earnings.py` — 13 checks, **14/14 mutations RUN and every one red**. Two of my own
tests could not catch their mutation first time: one gave a bot `balance=None` so *"summed"* and
*"read once"* were the same assertion, and one targeted a branch that never runs when the opening
is `None`. **Check that a test's inputs can distinguish the behaviours it names.**

## A LIVE account names its own Telegram channels, and no door puts a bot on one that does not (2026-09-13)

**Aaron's rule, the day a second person's live account (35710389) joined the box.** Two owners,
two lots of real money, and neither may read the other's fills. A Telegram room is therefore a
property of the **account** — three fields on its registry row (trades, signals, health) — and
never of the bot. The bot refuses to start on a live account that names no trades or signals
channel (`algos/live/runner.py`, exit 5); this app is the other half and refuses to PUT one there.

**The four doors, each refused with the same sentence (`RegisteredAccount.channels_reason`):**

- **Moving one bot** onto a live account with no channels — `set_bot_account`, 409. A bot already
  on that account is not "moving onto it" and is not asked.
- **Taking a proven set live** — `services/go_live.py`, blocked. A separate refusal from the
  missing-terminal one, because each needs different work.
- **Clearing a live account's channels while bots are on it** — `register_account`, 409. ⚠ It
  refuses the STATE, not the change: a row with no bots saves with no channels, because that is
  how a live account gets registered before its owner has been asked for one.
- **The Add bot button** on the account panel — disabled with the reason, before the click.

⚠ **Health is optional by decision.** Most of it is about the one box every account shares, so an
account naming none falls back to the shared room. A demo account owes nothing and may name its
own.

**A chat id is validated when typed** (`_CHAT_ID`: a number of 5–20 digits with an optional
leading minus, or a public `@name`). A wrong id otherwise fails at the moment a real fill is sent.

### This app's own alerts land in the account's health channel

`_notify_telegram(text, bot_key=…, account=…)` names what a message is ABOUT, and
`_account_health_chat` looks that account's health channel up in the registry, per call, never
raising. 🔴 **The deploy thread is why this matters:** the PROMOTED root is sent from here and the
bot's STOPPED and ONLINE are REPLIES sent from the box into its account's channel — a reply only
threads inside one chat. The three **All bots** alerts (start, stop, restart) are about the box and
deliberately name no account. `tests/test_account_channels.py` reads the router and refuses any
new `_notify_telegram(...)` that names neither, so a route added later cannot quietly land in the
shared room.

### Send test — `POST /bots/accounts/registry/{account}/test-channel`

Runs `algos/tools/verify_channel.py` **on the box**, because the Telegram token lives only in the
box's credentials file and a Telegram bot can only post where it is a member — a message sent from
a laptop tests a different sender. It writes nothing.

- `ok` is the tool's **exit code**, never a word read out of its text.
- ssh's own failure (255, nothing printed) is a **502**, never `ok: false` — "the channel is
  wrong" and "nobody could ask" need different work.
- A typed id goes as `--chat-id="…"`: every channel id starts with a minus, which argparse reads
  as a flag after a space unless the value is all digits.
- Refused by the browser guard (`.claude/mcp/browser_guard.js`) — it posts a real message.

**TESTED:** `tests/test_account_channels.py` (39), plus routing checks added to
`test_bot_label.py`, `test_bot_promote.py`, `test_account_risk.py` and `test_go_live.py`. Full
backend suite 2194 passed, 8 skipped.

## An account's demo/live field is LOCKED on the page — and now on the save route too (2026-09-14)

The frontend locked `kind` on an existing account's settings the same day it split the form into
three cards (`../frontend/notes/accounts-broker.md` → *The account settings*), because nothing
server-side stopped a save from flipping it. `_refuse_a_kind_flip` closes that: `check_entry`
refuses a save where an account already recorded as `demo` or `live` would be stored as the other
one. **Going live is a MOVE, never a flip** — `services/go_live.py` moves a demo account's bots
onto a separate, already-live account, with its own confirm and its own channel checks. Flipping
the field in place instead would drop the live tint, the fleet-action warning and the Telegram
channel requirement in one write, with nothing on screen to say so.

🔴 **The guard lives in `check_entry` ONLY, never in `upsert_account`** — the one real conflict
this needed resolving before it shipped. `account_sync.plan_sync` corrects this exact field from
the broker's own MEASURED reading, for an account no bot trades, and previews it before anything
is written (*"only what the box MEASURED is written: server, demo-or-live, the symbol ending"*).
`apply_sync` writes that correction through `upsert_account` **directly**, never through
`check_entry` — so a guard in the shared writer would have silently refused the sync doing exactly
the job it exists for, on the same account, the same field. `check_entry` is the route only a
person's typed Save crosses; `upsert_account` stays the "write what you're given, once validated"
primitive both callers share.

⚠ **Only refused once the account already holds a VALID `demo`/`live` kind.** A row a stale file
left with anything else (the one case `_validate` never let a normal write create) is a
correction, not a flip — the same case the form's own kind picker exists for on a scanned reading
the broker never called demo or live.

**TESTED:** `tests/test_bot_account_registry.py` — six new checks, each watched RED by a named
mutation, including one proving a guard placed back in `upsert_account` breaks sync's own
correction. Full suite here plus `test_account_sync.py` and `test_go_live.py`: 141 passed.
