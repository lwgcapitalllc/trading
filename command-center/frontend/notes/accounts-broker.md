# Notes — Accounts and broker connections

The Accounts tab, adding a broker account, dragging a bot onto an account, and how an account is named. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The Accounts tab is a RAIL + DETAIL, not a stack of cards (2026-08-12)

`AccountsTab` was a card per account, stacked down the page. Aaron's report is the spec for what
replaced it: *"the more accounts I add, it's just gonna keep scrolling up and down… the first thing
that I'm looking at is what is the broker? Then what's the account number? And then the account
type? Those things don't stand out to me at all… I can't tell easily what bot is trading on what
account… I don't see an easy way to add bots or remove bots from accounts."*

Three separate faults, and only the first is about layout:

- **It grew downward for ever.** With five accounts the page was a scroll and a memory test, and
  the answer to *what is trading where* was never on one screen.
- **Identity did not stand out from description.** Broker, number and tier were three
  interchangeable pieces of grey `text-micro`, sitting beside the server, the suffix and the cap in
  the same treatment — so nothing on a card told you WHICH account you were looking at faster than
  anything else did.
- **Moving a bot was drag-only**, which nothing on screen advertised.

⚠ **The rail is the selector and the ONLY thing that grows; the detail pane is fixed.** Same shape
as `ConfigureTab`, deliberately — two tabs that both pick one thing out of a list and configure it
should not be two different interactions, and that tab's own note already argues the case (only the
selected subject's controls exist in the DOM, so a control for something you did not pick is not
there to be hit).

⚠ **Selection lives in `?account=` and MERGES the existing params.** `setSearchParams({account})`
would drop `?tab=accounts` and throw the reader back to Monitor. It is also why a reload keeps the
account you were reading — a selection that dies on refresh is one you re-make every visit.

⚠ **The default lands on an account that is TRADING.** The registry is ordered by account number,
so the first row is whichever login is numerically lowest — on this box a retired Standard demo —
and opening on it made the page's first answer to *what is running* an account with nothing on it.

⚠ **`data-kind` is on BOTH the rail row and the detail pane**, so a bare `[data-kind="bench"]`
matches two elements; every check scopes to `account-rail-item` or `account-card` first. The
strict-mode violation that follows reads as a MISSING card rather than a duplicated one, which is
the wrong direction to be sent in.

### Both panes are the height of the PAGE, and the height is measured

⚠ **`usePaneHeight` measures, and a `calc()` here is the trap.** `100vh - 148px` is right for the
top bar, the page padding and the tab row — and wrong the moment anything else is above the pane,
which really happens: the VPS-failure banner appears on a poll and a hardcoded height then runs the
pane's bottom edge off the screen. One `getBoundingClientRect` per render, guarded so it converges
in a pass, cannot be wrong about what is actually above it.

⚠ **The effect has NO dependency array on purpose.** A banner appearing above this pane moves its
top without any state in here changing, so the measurement has to run on every render.

⚠ **The detail pane is header / scrolling body / pinned footer**, and each part is where it is for a
reason: the identity stays put while the bot list scrolls (you are never reading a table whose
subject has scrolled away), and the risk cap is a footer rather than something you scroll to find.
`AccountForm` takes the same shape, so switching between reading an account and editing one does
not resize the page under the reader — and its Save is pinned for the same reason Add account is.

🔴 **The Monitor tab's loading skeleton rendered over every tab** until 2026-08-12, so opening
Accounts drew ~400px of fake Monitor cards above it for the four seconds the VPS snapshot takes and
then snapped away. **Neither Accounts nor Users reads that snapshot to render** — Accounts joins it
only for the State column, which honestly says `—` — so both were blocked by a fetch neither needs.
⚠ **The error banner is deliberately still ungated**: a dead VPS is why the State column cannot
answer, and that is worth saying on this tab. The measured height is what absorbs it.

### Whether anything is TRADING an account — three states, one definition

**Added 2026-08-12.** Aaron: *"make more obvious that the account has a bot running against it or
not."*

🔴 **The rail's last line read `2 bots`, which is a fact about the CONFIG and reads as a fact about
the account being live.** Two bots assigned and stopped rendered identically to two bots trading,
so the rail — the one place every account is on screen together — could not answer *which of these
is running right now*, and getting the answer meant selecting each account in turn and reading the
State column. The rail row now carries a green dot + `1 of 2 trading`, and the detail pane a
`running-chip` reading `Trading · 1 of 2`.

⚠ **`liveOf` is ONE derivation, read by the rail row and by the chip.** Two hand-written readings
is how a green dot in the list ends up beside *nothing running* on the pane it opens — the same
argument that made `useAccountCount` exported and `BotStatusPill` a shared file.

⚠ **THREE answers, and the third is the whole reason it is a function.** `known` counts the bots
the VPS snapshot actually came back for, so `running: 0` with `known: 0` means **nobody asked**,
not *nothing is trading*. `/bots/accounts` deliberately never touches the VPS, so this tab renders
in full while the box is unreachable — and reading that silence as `idle` would report the fleet as
stopped at exactly the moment nothing can be checked. It says `Running state unknown` / `unknown`
instead. Same rule as `has_password`'s `null`, and as `mt5_link` before it.

⚠ **`running > 0` wins even when some bots are unanswered.** A bot SEEN running is a measurement;
the unknowns can only add to it.

⚠ **An idle account says `Nothing running` rather than drawing no marker.** An absent green dot is
indistinguishable from an account nobody could ask about — which is the same collapse the plain
count was guilty of.

⚠ **The dot is STEADY, never `animate-pulse`.** A bot runs for weeks, and permanent motion in a
list is read as an alert on day one and as background by day two; the row already has a warning
triangle that genuinely wants the eye.

⚠ **The chip is FIRST in the readiness row.** Everything else there — password, terminal, cap — is
about whether the account COULD trade. This one says whether anything IS, which is the question the
page is opened with.

⚠ **The default SELECTION was deliberately not changed to prefer a trading account.** It is
`busiest` by bot count, which is answerable from the accounts payload alone; keying it on the
snapshot would move the reader's selection ~4s after load, when the VPS answers.

3 new browser checks (41 in the file), **each proven by MUTATION** — the rail falling back to the
plain count, the chip rendering only when something runs, and `state` collapsed to `running > 0`
each turn their own named check red and leave the others green.

### The counts are on the TAB CHIPS, from one definition each

Aaron: *"accounts on the left navigation as account four — just put that count inside the accounts
tab where I could see it. Users should have a count for how many users we have."*

⚠ **A count on the chip is readable from a tab you have not opened**, which is the whole point; the
same number inside the panel only answers the question once you are already there. So the rail's
own header carries no number — two places is two claims about one set.

⚠ **`useAccountCount` is exported and is the ONE definition**, and it counts registered accounts
plus any account a bot names that nobody registered — exactly the set the rail draws as accounts.
The bench and the unreadable-configs rows are states, not accounts.

⚠ **An unanswered query renders NO chip, never `0`.** *No accounts registered* is a claim, and it is
never the true one here. ⚠ **Monitor and Configure carry no count on purpose** — the fleet size is a
stat card on Monitor, and Configure lists the same bots.

### Accounts vs Configure — and the row that says so

The question came up as a question (*"what's the difference between accounts and configure?"*),
which is the tell that nothing on the page answered it. **This tab decides WHICH account a bot
trades; Configure decides HOW it trades there.** They are two different writes — one rewrites the
login, server, terminal, symbol and cap together, the other edits a runtime parameter — so they stay
two tabs, and every bot row now carries a **Configure** link that jumps straight to that bot on the
other tab. ⚠ It MERGES the query string (`tab` + `bot`), like every other navigation on this page.

### Two defects that only a real render could show

Both were invisible in the diff, and this folder has recorded that lesson twice before (the 22px
sticky trap; the 6px grid bleed).

🔴 **Add account sat below the fold.** It was under the list, which put it 10px off the bottom of a
940px viewport with five accounts registered — so the one control that makes this tab work would
have been the first thing to disappear as the fleet grew, which is precisely the failure the
rebuild was for. It is above the list now, and the LIST scrolls (`max-h-[calc(100vh-150px)]` with
its own `overflow-y-auto`) rather than the page.

🔴 **The Move `<select>` rendered ~320px wide.** A native select sizes itself to its WIDEST OPTION,
and an option here is a whole account identity (`PU Prime #700152905 · ECN · demo`) — a string only
ever shown in the open popup. It takes an explicit `w-[104px]`.

### The Move menu — drag is the fast path, not the only one

⚠ **It fires the SAME mutation the drop and the Add bot list fire.** Three gestures, one write; a
private write on any of them would be a second place for the six-field move to drift out of step
with `assign_plan`.

⚠ **An unassignable account is LISTED and DISABLED with the reason in the option itself.** Hiding it
makes an account that exists look like one that does not — the same rule the Add bot list follows
for a running bot, and the same rule the `no-terminal` chip states one panel up.

⚠ **A RUNNING bot is refused on all three controls in the same words.** It read its config at
startup, so a write cannot reach the live process and the page would show it under one account
while it traded another. A second control that is not guarded is a way round the guard rather than
a convenience — which is also the answer to *"do I have to stop it first? I don't know"*: the reason
is on the disabled control's own title, not somewhere else on the page.

## Adding a broker account — the control that did not exist (2026-08-12)

`AccountsTab` renders a card per REGISTERED account now, whether or not a bot is on it yet, plus an
**Add account** form. Backend and the reasoning: `../backend/CLAUDE.md` → *The account REGISTRY*.

🔴 **The tab could only ever show accounts a bot was ALREADY on**, because the grouping is derived
from the instance configs — which is right, and which meant the first bot onto a new account had
nothing on this page to be moved to. That is why the live bot's move to the PU Prime ECN demo was a
hand-edited config on the VPS.

- **`emptyGroup(reg)` synthesizes the card for an account with no bots.** ⚠ It sets
  `cap_agrees: true` with `risk_cap_pct: null` — the honest reading of an empty account, since no
  bot states a cap so there is nothing to disagree about. `cap_agrees: false` would draw the
  disagreement banner over an account nobody is trading.
- **An account a bot names but nobody registered still renders**, with a `Not registered` chip
  saying what this page cannot do with it. Hiding it would be the defect the registry exists to
  end, in reverse.
- **`targets` excludes an unassignable account**, so the Add-bot list on every card can only offer
  a move the backend will accept.

### Three chips, and the middle one is the three-state rule again

- **`password-chip`** — `Password set` / `No password` / **`Password unknown`**. ⚠ `has_password`
  is `boolean | null` and `null` means the VPS could not be asked. Rendering it as *No password*
  sends the reader to re-enter a credential that is already there and refuses a move that would
  have worked. Same rule as `mt5_link` and `mt5_connected`.
- **`no-terminal`** — the account has no terminal on the box, so **Add bot is DISABLED with the
  reason on its title.** The refusal exists server-side; this is it stated before the click rather
  than as a 409 after the reader has committed to the move.
- **`live-chip`** — a live account is tinted, the same treatment the Configure tab gives one.

### The form, and the field it puts front and centre

⚠ **The symbol suffix has its own block, its own sentence and a live example** (`XAUUSD.s` becomes
`XAUUSD.p`), rather than sitting in the grid with the display fields. It is the field the 2026-08-12
move forgot, and forgetting it produces a bot that connects, warms up and receives no bars — which
looks exactly like a quiet market rather than like a misconfiguration.

⚠ **It is a CHECKBOX plus a text field, because `null` is a real value.** Unticked sends `null`
("nobody recorded it" — the move leaves the symbol alone and says so); ticked-and-empty sends `""`
("this broker quotes bare symbols" — the move really does strip the suffix). A single text input
would collapse them, and the empty string is the one that silently rewrites a live instrument.

⚠ **There is NO risk cap field on this form and there must not be one.** The cap is set on the card
above — one write, N instance configs — and reported from what the bots actually state.

⚠ **The password field is WRITE-ONLY and blank on an edit.** Nothing returns it, so the form shows
whether one is stored and never what it is; leaving it blank changes nothing. It is sent on the
same request as the registry row, so the credential lands BEFORE the row is committed and pushed —
a registered account with no password is a visible, fixable state the list reports, while a pushed
row whose password write failed afterwards reads as complete.

### The move's `notes` are raised as WARNINGS, not folded into the success line

`useAssignBotAccount` toasts each entry of `BotAccountAssignResult.notes` separately.
**They describe a failure that is silent on the box** — an unregistered account whose symbol and
cost profile could not be carried, or one with no recorded suffix — so burying them in the success
sentence would put the one thing worth acting on inside the message that says it worked.

**`tests/bots-accounts.spec.ts` — 8 new checks (27 in the file).** ⚠ **`mock()` now routes
`/api/bots/accounts/registry` and it MUST**: that endpoint asks the VPS whether a password is
stored, so an unmocked one reaches the live box from a unit check. It defaults to an EMPTY
registry, which is what leaves every pre-registry check unchanged. Non-vacuity is by MUTATION —
five run here, each turning its named check red (registry cards dropped, `assignable` ignored, the
suffix dropped from the submit body, the suffix sent unconditionally instead of `null`, and the
in-use guard dropped from Remove).

## Dragging a bot onto an account in the RAIL — a second GESTURE, never a second path (2026-08-12)

A bot's row in the detail pane is draggable and every row in the ACCOUNT RAIL is a drop target.
Aaron's words: *"if I wanna switch a bot between accounts, I could, like, drag and drop bot from one
account to the next and hit, like, a deploy button."*

⚠ **The rail is the target since the tab became master–detail, and it had to be** — only one
account's card is on screen at a time, so a card-to-card drag can no longer reach a destination.
The rail is the one surface that always shows every account.

🔴 **A drop fires the SAME `useAssignBotAccount` mutation the Add bot list fires.** The move writes
four config fields plus two inside `strategy_params`, and a private write here would be a second
place for that to drift out of step with `assign_plan`. What is new is the gesture; nothing about
what a move DOES is duplicated.

⚠ **THERE IS NO STAGED "pending moves, then hit Deploy" STEP, and adding one would be the defect.**
It would be a stored intention able to disagree with what the bots are actually configured to do —
the exact shape this tab exists to avoid, and the reason the grouping is DERIVED rather than
stored. A drop writes, commits, pushes and pulls in one action, which is already *click, click,
done*; the toast still says a restart is needed, because neither `account` nor the cap is
runtime-reloadable.

⚠ **The GRIP is the only thing on screen that says a row can be dragged.** A `draggable`
attribute is invisible, and the gesture shipped with nothing advertising it but a sentence under the
rail — which reads as an instruction for a feature nobody can find, and was reported in exactly
those words (*"that drag feature doesn't even work. I don't even know what that does"*). Every
movable row carries one, with the destination in its hover text; the sentence is gone. ⚠ **It is a
MARKER, not a handle** — the whole row is still the drag source, so grabbing anywhere works, and a
grip that only worked when grabbed by its 13 pixels would be worse than none.

⚠ **Refusing a drop is `preventDefault` NOT being called on `dragover`.** That is what makes an
element a valid drop target, so declining it is how an account with no terminal says no **while the
reader is still holding the row** — a cursor rather than a toast after they have let go. It is also
why the check for it asserts on `data-dropping`: the refusal has no other observable.

⚠ **A RUNNING bot carries `draggable={false}`**, matching the Remove button beside it. It read its
config at startup, so a write cannot reach the live process and the page would show it under one
account while it traded another. The backend refuses it with a 409 regardless; this is the same
fact stated before the gesture rather than after it.

⚠ **`text/bot-key` is a custom MIME type on purpose.** `onDragOver` checks
`dataTransfer.types.includes(...)`, so dragging text, a file or a link over a card does nothing —
a card that highlights for anything is a card that will eventually accept something it should not.

3 browser checks (30 in the file), **each proven by MUTATION**: removing `onDrop`, making
`draggable` unconditional, and dropping the `assignable` early return from `onDragOver` each turn
their own named check red. ⚠ **The drag events are dispatched by hand rather than with
`dragTo`** — Playwright's helper is unreliable across the mouse-move heuristics, and what these
check is the DATA the drop carries, which the manual events model exactly.

## The account net is measured off what went IN, and the page says which (2026-09-12)

`AccountNet`, the account drawer and the *Not from these bots* line read `AccountEarnings.net_basis`.
On `'deposits'` the net is the balance less `capital_in` (deposits less withdrawals) and the % is
time-weighted, so the tooltip and the drawer name **what went in** as the referent, never the
opening, and the remainder line stops offering *a deposit* as a cause — it is already out of the
net. On `'opening'` (a bot on an older runner) everything reads as before. ⚠ **Both fields are
optional** — recordings predate them — and **the page decides nothing**: the basis is the server's.
Rules: `../backend/CLAUDE.md` → *The account's net is measured off what went IN*. Pinned by one
offline check in `tests/bots-accounts.spec.ts`, watched RED in a throwaway worktree against HEAD's
page and again with the remainder still naming a deposit.

## An account is named by its NICKNAME, else its broker (2026-09-13)

Aaron: *"PU Prime Ltd doesn't help me differentiate accounts."* `accountName`
(`pages/Bots/AccountForm.tsx`) is the one rule — the account form's Name, else the broker, else
`null` — and every place that names an account calls it: the card heading and the account panel's
title (through `nameOf`), the bot panel's account line, the unassigned list and the go-live panel.

- 🔴 **Three of those five put the BROKER first** while the form's own Name field says it is "used
  instead of the broker when it is set" — one rule written five times, two copies the other way round.
- ⚠ **Instead of the broker, never beside it**; the account number still leads the heading.
- Tests: 1 new and 1 re-pointed in `bots-accounts.spec.ts`, both watched RED against HEAD. The broker
  fallback passes at HEAD and was not mutation-run.

## A broker account is printed in words — `lib/brokerName.ts` (2026-09-13)

Every form, caption and tooltip that names a cost profile prints `brokerName(id)` — `PU Prime ECN`,
not `puprime_ecn`. The id stays the value every request sends. ⚠ A brand the table does not know is
capitalised rather than refused. ⚠ Never print a raw profile id on a page.

Same pass: the cost-layer names moved to `lib/costLayers.ts` (the run page and the tuning page each
carried a copy; the optimize form printed raw ids); the tuning page names a sizing mode only for a
strategy the lab sizes — a self-sizing one never reaches the engine, so a mode there described code
the iteration does not touch (it is still SENT); the stack form's *could not check* line and its
unmeasured-spread banner are amber (a question and a block, not a loss); and the score key says
which unit a drawdown is judged in (`../backend/CLAUDE.md` → *Worthiness scoring*).

## A LIVE account's Telegram channels — entered on the form, tested from the box (2026-09-13)

**Aaron's rule, the day a second person's live account joined the box:** each live account names
its own trades and signals channels, and a bot on one without them refuses to start. The server
refuses every move that would put a bot there (`backend/notes/accounts-risk.md`); the page says so
**before** the click.

- **The form** (`AccountForm.tsx`) has a *Telegram channels* block with one row per channel. On a
  live account it warns which are still owed as they are typed; a demo account owes none.
- **Send test** beside each field posts a real message **from the trading box** (the token lives
  only there) and shows what the box said. ⚠ **A verdict belongs to the VALUE it tested** — edit
  the field and it goes, so no mark ever sits beside an untested id. 🔴 **Three outcomes:** arrived,
  did not arrive (Telegram's reason, unreworded), and **not tested** when the box could not be
  reached — rendered neutral, never as a failed channel.
- **The account panel** (`AccountDrawer.tsx`) marks each owed channel *missing* in the heading's
  setup checklist (see the next section; this was a *no … channel · add* chip until later the same
  day), and Add bot is disabled with the reason. Checked after the terminal, before the password.
- **Take live** (`GoLivePanel.tsx`) LISTS a channel-less live account, disabled and marked *needs
  its Telegram channels* — never hidden, since a destination that vanishes reads as a bug.

⚠ **Read the new fields null-safe.** A recorded answer from before 2026-09-13 carries none of
them; a browser check drives exactly that row.

**TESTED:** `tests/bots-accounts.spec.ts`, the checks under *A LIVE account names its own Telegram
channels*.

## The account settings: a setup checklist, the MT5 facts locked, three cards (2026-09-13)

Aaron: *"some of these fields I should NOT be able to edit — they are read directly off the VPS mt5
instance … find a way to separate mt5 level info from telegram channel stuff … in the heading I
can't tell what is missing and what is not missing."*

- **The heading's chips are a fixed four-step checklist** (`pages/Bots/readiness.tsx`): Terminal,
  Password, Trades channel, Signals channel — all four every time, each *done*, *missing*,
  *unknown* or *shared room*. The old chips drew only some states, and `password set` and `no
  trades or signals channel · add` were the same pill shape. A missing step is a button that opens
  the settings on its fix, cursor in the first empty channel. ⚠ Every state is the server's field;
  a blank channel on an account that owes none is *shared room*, never missing. This replaces the
  three chips described under *Adding a broker account* above.
- **Edit became Settings, in three cards** (`AccountForm.tsx`): *MT5 account* — broker, terminal,
  symbol ending and the password, as TEXT under *Locked · Sync VPS updates these*; *In this app* —
  name, cost model, tier; *Telegram* — the three channels, each with Send test.
- ⚠ **Login, server and demo-or-live are not repeated in the card** — the heading carries them
  (*Say it once*). The by-hand add (Sync VPS → add by hand) has no such heading and still types
  every fact.
- ⚠ **Three locked facts can still be filled, each only when the box left it empty:** a terminal
  nobody recorded (the VPS is asked first; *Enter the path by hand* appears only when it offers
  none), a symbol ending nobody recorded (*Set by hand*), and a demo-or-live the broker never stated
  (a picker).
- 🔴 **The symbol ending is a three-way choice, not a checkbox.** The checkbox's own sentence said
  *unticked means bare symbols* while unticked SENT `null`, and a ticked empty box sent `""` — the
  value that strips a live instrument's suffix. Now `""` is sent only by picking *Bare names*,
  *End in a suffix* with an empty box cannot be saved, and a new account starts on *Not recorded*.
- **Cost model is a list** of the measured profiles (`useBrokerProfiles`), so a name the server
  would refuse cannot be typed. ⚠ A list that could not be read falls back to a text box.
- **The Save row is the drawer's pinned footer** — the form hands its body and footer to a `frame`
  from whichever drawer hosts it, instead of drawing a bordered box with its own scroll inside the
  drawer's. It lists every pending change with the risk budget's `Change` chip (moved to
  `drawerParts.tsx`) and is off until something changes. **A password on its own goes to the
  password endpoint** — the account list is not committed for a row that did not change.
- ⚠ **The lock is on the PAGE.** The form sends the saved values back unchanged, but the server's
  save still accepts a different server or demo-or-live.

**TESTED:** `tests/bots-accounts.spec.ts` — the checks under *The account settings*, plus the
terminal, password, channel and suffix checks re-pointed at the checklist and the locked card.
