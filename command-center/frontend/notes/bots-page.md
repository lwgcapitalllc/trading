# Notes — The Bots page

The bot list/drawer, bot rows, add/remove/move a bot, sync from the VPS, risk shares, and every defect found auditing it. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## A settings GROUP must not hardcode a number one of its rows owns (2026-08-21)

The strategy editor renders its accordions from the `group` string in a strategy's meta file, so a
group name is a claim like any other label. The re-entry block read **`Secondary re-entries (1m)`**
until the re-entry's fill clock became a setting (5 minutes by default). Renaming it `(5m)` was the
obvious move and would have been the same defect one turn later — **the heading now names no
timeframe at all**, and the one row that owns the number is the only place it appears.

`tests/param-gates.spec.ts` pins the ABSENCE (`Secondary re-entries (\d+m)` must not render)
rather than the presence of a particular figure, so the test cannot go stale the next time the
default moves. ⚠ **Playwright is not in `scripts/run_all_tests.sh`** — it needs the app up — so
this one is only as good as somebody running it.

## The Bots page: one list, one drawer, no tabs (2026-09-05)

**Accounts are headings, bots are rows, and clicking either opens a drawer holding only what you
can change.** It was four tabs, then two — both the same mistake, several views of the same three
objects. Aaron: *"too much information, too much duplication … make it very, very simple."*

🔴 **Every number is stated ONCE, on the thing it belongs to.** Balance, cap and account number
belong to the account and live on its heading; version, risk and uptime belong to the bot and live
on its row (uptime on the status's hover since 2026-09-12). **Nothing is repeated to make a row look
complete** — that habit is what put one account's balance on every row of a stack and let the fleet
total add it twice.

⚠ **State is one coloured pill, not a shouted word.** `RUNNING` was written on every row of every
tab. Since 2026-09-13 every list of bots draws the same pill — see *One status per row*.

🔴 **A control's own prose does not go on the surface.** The risk editor printed `row.note` — the
`_`-prefixed paragraph from the instance config, ~1,500 words on `exec_risk_pct` — directly beside
the one input on the page, and buried it. It is now behind `hideNote` and shown under the drawer's
Details, where somebody asking *why is it 5%* will look. **Hidden, never deleted**: that prose is
the measured reasoning behind a live risk number.

⚠ **The drawers reuse `VersionBanner` unchanged** — it deploys code to a live account with its own
confirm, and rewriting it to make a drawer tidier would put a fresh implementation on the money path.
The risk editor WAS rebuilt (2026-09-11, `BotRiskEditor.tsx`) because it had to save through the
account's budget — see *The two panels: one budget* below.

⚠ **Fleet controls and scheduled jobs moved to Overview** (`components/FleetControls.tsx`, one
component, not a copy). This page manages bots one at a time; those act on all of them.

✅ **`bots-accounts.spec.ts` and `bots-version.spec.ts` were re-pointed and now run OFFLINE
(2026-09-10)** — no read reaches the backend or the box. See *Offline specs* under *Browser tests*.

## A bot row names what it is DOING — Stopping / Starting / Restarting (2026-09-10)

The row used to replace its actions with a pulsing `…` while a start/stop/restart ran. It is now a
pill naming the action (`BotActionPill`, shared by the row and the bot drawer) — Aaron: *"I should be
seeing the pill saying stopping not three dots."* ⚠ **Held until the snapshot is RE-READ**: the
mutation returns the invalidation's promise, because the request returns before the page knows the
bot's new state, and a row offering Stop again on a stopped bot invites a second press. ⚠ **Logs is
hidden while the pill shows** — MEASURED at 1280px the actions column is 190px and a pill 72–84px,
which does not fit beside Logs.

## "Backtest these bots" opens the builder FILLED IN by the server (2026-09-10)

🔴 **The account panel's *Backtest the stack* linked to `/backtests?stack=<n>` and nothing read it**
— it opened the Runs tab and did nothing else. It now goes to `?tab=stacks&account=<n>`, where the
Stacks tab reads `useAccountStackBasis` and opens `StackConfigModal` with what those bots RUN — each
bot's own complete settings, chart and risk, the account's cap, instrument and cost profile — with a
`notice` saying where the values came from. ⚠ **The page decides nothing**; the plan and every
refusal are `backend/services/account_stack_basis.py`'s. ⚠ **Not the strategies' defaults, and not
the Strategies page**: on the live pairing the defaults ask for 15% under a 10% cap, which the
builder refuses. ⚠ **Its key is outside `['bots','accounts']` with `gcTime: 0`**, so an account
write cannot reshape an open form and every open is a fresh read. ⚠ **A refusal is a banner with the
server's sentence and a Dismiss**; the button is disabled, never hidden, under two bots. ✅ Driven in
a browser with the launch intercepted: 26 + 116 settings, 5% each, 5m/15m, `XAUUSD.p`, ECN, cap 10.
🔴 **Drawn only on a DEMO account since 2026-09-11** — Aaron: *"backtest these bots should only be
on demo accounts, not live accounts."* Demo is where a set is tried; live runs what was tested
there. Take live's rule: an account whose kind is not known yet gets no button.

## "Sync VPS" — scan first, then a Sync button (2026-09-10)

**Sync VPS** in the Bots header opens `VpsSyncDrawer` and does nothing else. The drawer SCANS
(`GET /bots/accounts/scan`, a read) and lists exactly what Sync would change; **Sync N changes** in
its pinned footer applies that list (`POST /bots/accounts/registry/sync`, sending the plan's id).
It exists because the account list is hand-typed and nothing checked it — a terminal sat on a LIVE
account for a day with this page unable to see it.

🔴 **Reversed twice in one day, and the second is the shape to keep.** "Scan VPS" only reported;
*"not a scan, a sync"* made the press write at once; then *"it doesn't show me what it is going to
do before I do it… scan first… then a sync button."* **The drawer decides nothing** — never an
account a bot trades, never a terminal set, nothing removed are SERVER rules
(`../backend/CLAUDE.md`); a copy here would be two answers about live accounts.

🔴 **The scan is a query that exists only while the drawer is open; the write is a mutation only
the Sync button fires** (*"100% manually triggered by me only"*). `useSyncPreview` is mounted inside
the open drawer with `gcTime: 0`, so every open is a fresh scan and never a plan read an hour ago;
`staleTime: Infinity` stops it re-asking by itself. ⚠ **Its key is OUTSIDE `['bots','accounts']`** —
a sync that wrote invalidates that prefix, and a preview under it would re-scan the box straight
after the sync returned `now`. ⚠ **The sync lives on the always-mounted shell**, so one still
running when the drawer closes is still reported when it reopens.

🔴 **The press sends the plan it approves, and a plan that moved writes NOTHING.** The server
re-scans; if the plan changed it returns the new one in `now`, which replaces the old one on screen
under a banner, and the next press approves THAT plan. ⚠ **A refused press is not a receipt** — the
drawer goes back to review, never "saved".

🔴 **Order: Scan → Review → Sync steps → one hero card that IS the outcome → the plan, field by field
(struck-out old value → new value, the evidence under it) → what needs you → the terminals on the box
→ how your saved list checks out against them.** *(The last two used to be one Section plus a
trailing paragraph; 2026-09-14 split them — see below.)* ⚠ **An ADD draws no old value** — *not in
your list yet* is not a blank field. ⚠ **Real money is said in words.** ⚠ **Nothing to change = no
Sync button** (Done instead); **a blocked plan = a disabled one with the reason.** ⚠ **After a sync
the same cards read "Saved"**, a push that never reached the VPS gets its own banner, and the list
shown is `now` — no second scan.

🔴 **This drawer is the ONLY way to add an account (Aaron's call)** — a quiet "Add it by hand" link
at its foot (`data-testid="add-account"`), for a terminal that is not running. ⚠ **Rendered under
EVERY state**, or that account has no way onto the list.

🔴 **Editing an account with NO terminal asks the box, and the field starts on its answer
(2026-09-13).** `useTerminalSuggestion` reads the same scan, narrowed to that account; the path and
the sentence under the field (`f-path-note`) are the server's (`_suggest_terminal`). ⚠ **Only the
reader's edit is state**, so a late answer fills an untouched field and never replaces a typed one.
⚠ **An account that has a terminal never scans.** ⚠ The placeholder was the demo bots' real path —
the one typed onto the new live account — and is words now. Tests: 4 in `bots-accounts.spec.ts`;
4 bugs planted in a throwaway worktree, 4 caught.

🔴 **Each failure looks different**: the scan could not run (nothing changed; Scan again leads), the
box refused, the plan moved, a terminal could not be asked (`not_running` / `owned_by_bot` —
nothing is wrong). ⚠ **A failed SYNC keeps the plan on screen and reads "didn't finish", never
"nothing saved"** — a 409 or 502 writes nothing, but an unexpected failure mid-save can have. The
first scan shimmers only the terminal list; the plan is never guessed at. Tests:
`tests/bots-accounts.spec.ts` (10 sync checks, each COUNTING scans and syncs); **20 mutations run,
20 killed**, each confirmed served by the dev server before its check ran.

⚠ **Where an account number came from is on screen.** It can come from the scan asking the terminal
or from the bot trading through it ("account reported by the bot") — different strengths of
evidence, so the row says which.

⚠ **Demo/live has TWO unknowns and they look different.** A bot reports only the account NUMBER, so
a bot-sourced row says "demo/live not reported" in grey — the first build painted it a yellow "mode
unknown", a false alarm on the terminal that matters most. A terminal the scan asked that answered
with an unrecognised flag IS an anomaly and keeps the warning.

⚠ **No bot COUNT on a terminal.** Ownership comes from which configs name it, and a benched bot
still does — the first wording said "3 bots trade here" with one trading nothing.

🔴 **The terminal list and the registry check are two different questions, and the 2026-09-14 redesign
gave each its own titled Section instead of one block.** Aaron: *"the on the VPS section... super
confusing... I don't even know what that section is... why some couldn't be checked, what is it?"*
The terminal list (`TerminalRow`) answers "what's on the box"; the registry check (`scan.registry`,
`confirmed`/`contradicted`/`unverified`) answers "does MY SAVED LIST agree with what the box just
said" — a different axis (per ACCOUNT, not per terminal) that a trailing sentence plus a `<details>`
accordion did not explain was even a different question. Now: **"Terminals on the VPS"** lists only
running terminals — a `not_running` one carries no information beyond a dash, so all of them collapse
into one line (`OfflineTerminalsRow`, name-only) instead of N rows that each say nothing. **"Your
saved accounts"** is its own Section, rendered only when there is something to read: a `confirmed`
match is still quiet (one count line — it is not a finding against a row), but `contradicted` and
`unverified` now render `RegistryCheckRow`s with the reason ON the row, not behind a click — there are
only ever a handful, so hiding the reason cost a click and answered nothing about what "checked"
even meant. Tests: `bots-accounts.spec.ts` (existing 10 sync checks updated and passing); `tsc --noEmit`
clean. `RegistrySummary` / `RegistryCheckRow` / `OfflineTerminalsRow` in `VpsSyncDrawer.tsx`.

⚠ **`unverified` is still deliberately not treated as a fault** (no warning colour, `Info` not
`AlertTriangle`) — it is a QUESTION the scan could not ask, not a finding against a row. That is
narrower than before: it used to also mean HIDDEN, which is the part Aaron could not read.

⚠ **`components/Drawer.tsx` is the shared slide-out shell** (and closes on Escape), with a pinned
`footer` slot since 2026-09-10 for the one action a panel builds up to — the Sync button would
otherwise be the first thing a long plan scrolls out of reach. **`AccountDrawer` and `BotDrawer`
adopted it on 2026-09-11**, so a drawer's look lives in one place.

🔴 **`AccountsTab` rendered nothing from the 2026-09-05 rebuild until it was DELETED on 2026-09-11**,
with `ConfigureTab`'s `BotPanel`, `DeployCard` and fleet strip (Aaron's go). The live pieces are
`pages/Bots/AccountForm.tsx` (`AccountForm`, `emptyGroup`, `nameOf`). It had been wired into its rail,
typechecked, linted and passed every gate — and **could not have appeared on screen**. ⚠ Sections
below that describe the rail, the tabs, `DeployCard` or the fleet strip are HISTORY: rule 9 in the
frontend, a feature nobody has RUN is not a feature.

Story: `command-center/docs/FRONTEND_BUILD_NOTES.md`.

## "Add a bot" lists FREE bots only, and an empty account asks for its cap there (2026-09-11)

`pages/Bots/AddBotPanel.tsx` (moved out of the dead `AccountsTab`). Aaron: *"it should just show
available bots that is it … why is XAUUSD.p showing … the account doesn't care."*

- 🔴 **Only bots on NO account are offered.** It listed every bot not already here, so the demo
  account offered both LIVE bots — greyed while running, one click from real money once stopped.
  Moving a bot between accounts is the bot panel's own account selector.
- ⚠ **A row is the bot's name and its risk per trade** — the one number the account's cap budgets.
  No symbol, no "not on an account" label.
- 🔴 **An EMPTY account asks for its cap in the panel** (default 10%, typed digits; unticked sends
  `null` = uncapped CHOSEN). The cap lives in each bot's config, so the first bot used to start
  uncapped and the watchdog started it within a minute; a cap saved after could not reach it. An
  account WITH bots sends no cap — the joining bot adopts theirs on the server. ⚠ **The drawer's
  Risk cap section on an empty account is a sentence, not an editor** — saving there answered 404.
- ⚠ **The panel stays open after an add**, so a second bot is one more click; the added bot leaves
  the list when the accounts re-read. Its row reads *Adding…* while the write runs.
- 🔴 **A bot is NAMED, never keyed**: the move's toast takes the name from the caller (the server
  answers with the key), and "recorded by" reads the name off the account's earnings
  (`lib/accountEarnings.ts`). It printed `sos_fade_demo` on screen.
- Tests: `bots-accounts.spec.ts` (4 new, 3 re-pointed); 9 mutations run, 9 killed, in a THROWAWAY WORKTREE —
  offline specs build the checkout from disk, and a bug planted in the shared clone is one the other
  session's run can pick up.

## "Remove from account" is a button in the bot panel (2026-09-11)

Aaron: *"we can stop but we can't remove."* Removing was the last option in the bot panel's
account selector, and nobody found it.

- 🔴 **Its own button beside the selector** (`remove-<key>`). It sends the same write with no
  account, so the bot is BENCHED: still registered, listed under Unassigned, and never started by
  the watchdog. The selector now only MOVES; "Not on an account" appears only as a benched bot's
  value — two controls for one write is two places for its guard to drift.
- ⚠ **A running bot is STOPPED FIRST** (it read its account at startup) — *A running bot is
  stopped first, never locked*. And **a second click on the same button**, disarming after 6s: the
  live deploy's pattern. ⚠ **It reads "Take off" since 2026-09-13** — one control with the account
  panel's rows, see *Take off is ONE button on both panels*.
- 🔴 **Decided off the CONFIG's account (`configAccount`), never `bot.account`.** That field is what
  the bot last REPORTED and stays on the old account until its next start, so a bot just removed
  would still offer Remove. `undefined` until the configs are read: Remove waits, the selector shows
  the report.
- Tests: `bots-accounts.spec.ts` (6 new — 4 for Remove, 2 for the demo-only backtest button — and
  1 re-pointed); 8 mutations run, 8 killed, in a throwaway worktree.

## The demo account after its bots went live — five things it got wrong (2026-09-11)

Off Aaron's screenshots of adding two demo copies back to the demo account.

- 🔴 **The Risk cap box FOLLOWS the account (`AccountDrawer`).** It was `useState(stated)`, copied
  once when the panel opened, so a panel opened on an empty account and then given bots at 10% read
  "Capped" UNTICKED with Save live — and Save would have sent "no cap". Only the reader's EDIT is
  state now, bound to the cap it was made against (`from`); when the account's cap changes the edit
  is dropped rather than saved over a change nobody saw.
- 🔴 **The fleet read is `silent` (`useBotSnapshot`).** Adding a bot re-reads the fleet, so the add's
  green toast arrived with a red 502 over a page that already says it in its error line. ⚠ **It keeps
  the default retry**, unlike other polls: the failure is a connection the box turned away, which a
  second ask usually gets through, and silent means a retry no longer doubles a toast.
- **A move's `info` is never raised.** Only `notes` are warnings; the server serves them apart
  (backend CLAUDE.md). It was a yellow toast naming a config field on every add.
- 🔴 **`balanceAt` is the ONE balance for the card, the panel and the header count.** It fell back to
  the last reading only with NO bot on the account, so the first bot added blanked the balance until
  its first report. ⚠ The wording says which case it is: *before it left* with no bot on it, *no bot
  here has reported one since it started* with one.
- 🔴 **A bot carrying on a strategy's record says whose trades its row includes** (the P&L tooltip,
  `carriedNote`). The server folds a departed bot's trades here into the one bot running the same
  strategy now (*"they should just pick up where they left off"*); the page only names them.

Tests: 5 new checks in `bots-accounts.spec.ts`; 8 bugs planted in a throwaway worktree, 8 caught.

## The two panels: one budget, and no dead end on add, move or risk (2026-09-11)

Aaron: *"add bots to demo and live accounts … take bots off … increase or lower the percentage risk
on the bot … increase or lower the max percentage traded on the account … seamlessly, with no
issues."* Each had a way to end in a refusal nobody could act on. Backend half: `../backend/CLAUDE.md`
→ *An account's risk budget is ONE planner*.

- 🔴 **The account panel edits the whole budget and saves it ONCE.** Each bot's share is a box on
  its row (`share-<key>`), the cap a box under them; the pinned footer lists what Save will write
  (`budget-changes`), the server's verdict and when it applies, then sends one
  `PATCH /bots/accounts/{a}/risk`. It was a cap box with its own Save beside read-only shares, and
  its toast said *restart them to apply* — false since a running bot adopts a cap when it is flat.
- ⚠ **The verdict and both fixes are the SERVER's** (`useAccountRiskPlan`, debounced 250ms).
  `fix-cap` / `fix-shares` fill the DRAFT, never save. Save waits for a FRESH plan —
  `isPlaceholderData` is the previous body's answer — and is disabled on `refused`; a plan that
  could not be asked does not block (the save is checked again).
- ⚠ **A plan is asked only when there is something to ask** — an edit, or an account already over
  its cap (that plan carries the fixes). Opening a panel fires nothing, which keeps
  `bots-version.spec.ts` free of unrouted requests.
- 🔴 **A bot that does not fit is offered the ways to make room where it is added**
  (`JoinChoices.tsx`): join at the room left, raise the cap to `fit_cap`, or scale every bot to
  `fit_shares`. ONE function carries them out, `useJoinAccount` (`joinAccount.ts`) — the budget write
  FIRST, then the move — for the Add bot list AND the bot panel's account selector.
- 🔴 **A LIVE destination is confirmed on screen before anything is sent** (`LiveConfirm`), and only
  then does the move carry `confirm_live` — the server refuses a live move without it (409). Until
  this, nothing on the page could add a bot to live.
- 🔴 **The bot panel's risk goes through the account's budget** (`BotRiskEditor.tsx`): the line
  under the box says whether the new share fits, a refused raise offers *also raise the account cap*
  in the same save, and a bot on no account keeps `/runtime`. The confirm is a STEP with the
  numbers, never a modal; on a live account its button says real money. `RuntimeEditor` is deleted.
- ⚠ **Taking a bot off is on the account panel too** (`take-off-<key>`, second click; a running
  one is stopped first, an unanswered one waits); a bot's name there opens its panel. Add bot is disabled, with the reason,
  on a definite *no password*, and that chip is a button into the account form.
- ⚠ **Both panels use `components/Drawer.tsx` and `drawerParts.tsx`**, so they read as one. Editing
  the account is a STEP of its panel, like demo → live.
- ⚠ **The move and runtime hooks lost their `onError` toast** — `api.*` already toasts the server's
  reason. `api.post` gained `opts`, so a plan (a question) can be `silent`.
- ⚠ **The password field asks for the TRADING password, not a read-only "investor" one** — with
  that a bot logs in and every order is refused (10017). 🔴 **It did NOT cause the live account's
  10017 on 2026-09-11** (this bullet said it did): right password, right server, and the broker
  reporting trading not allowed on the account — readable at login, and nothing reads it yet.
- Tests: `bots-accounts.spec.ts` — 8 new, 2 re-pointed to `/risk`; `mock()` answers a plan "fits"
  by default. 13 bugs planted in a throwaway worktree, 13 caught. ⚠ **The re-pointed save check
  reads the TOAST** — the footer states the same sentence while the edit is on screen, so a
  page-wide match passes on the footer whatever the save said.

## Two copies share a NAME, so the bot panel says LIVE or demo (2026-09-11)

The demo copies carry the live bots' display names ("SOS Fade", "Extreme Leg") — Aaron: *"it's a
generic strategy, not a demo specific strategy"*; demo or live belongs to the ACCOUNT
(`algos/CLAUDE.md` → *One strategy, two bots*). The page groups bots by account, so rows need no
tag. Where a name appears WITHOUT its account — the bot panel's title, its risk-change
confirmation, its deploy lines, the log window — `lib/botLabel.ts` writes `SOS Fade · LIVE` /
`SOS Fade · demo`, the same words every Telegram message uses.

- ⚠ **A bot on NO account keeps the plain name.** Its `account_type` is then the registry's
  hardcoded fallback, a guess about an account it is not on.
- ⚠ **The panel's aria-label stays the plain name** — checks find the panel by it.
- ⚠ The Overview's bot list carries its own tag (the other session's, 2026-09-11).

Tests: 2 in `bots-version.spec.ts`; 3 bugs planted in a throwaway worktree, 3 caught.

## 🔴 Never sum a number across bots that SHARE it (2026-09-04)

**The Bots header added every bot's balance.** Each bot on a stack reports the SAME account
balance — one pot of money, not one each — so a two-bot stack showed **$29,077.76** for an account
holding **$14,538.88**. It is summed per ACCOUNT now.

🔴 **It read correctly for as long as every bot had its own account, which is exactly why nobody
caught it.** The defect arrived with the first stack this app has ever had, not with the code.

⚠ **This is the repo's compare-R-never-dollars rule arriving in a header tile**: the moment two
things share a balance, anything summed across them is wrong by whatever they share. **Before
totalling a column, ask what the rows SHARE** — balance, account, terminal, risk budget.

⚠ **An account whose balance could not be read counts as UNKNOWN, never as zero**, and the tile's
caption says how many accounts it added and how many it could not. A total quietly missing a box's
worth of money is the reassuring direction, which is the wrong one.

## Shares past the cap SHARE the room, and the account panel has a PRIORITY list (2026-09-15)

Aaron, 2026-09-15: the cap limits the risk open at any moment, not the sum of the shares — any
number of bots may share an account. Backend rules: `backend/notes/accounts-risk.md` → *Shares may
add up past the cap, and an account has a PRIORITY order*.

- **The amber refusal line (`cap-overflow`) now appears only for a bot above the whole cap or a
  share nobody can read.** Shares that add up past the cap show the server's `share_note` in grey
  (`cap-sharing`). The old "take turns" line is gone — the note is its general case (*Say it once*).
- **The account band** gained a `shared` state: grey "15% shared", the note on hover. Red
  "a bot is over it" is kept for the refusal only — colour means a fault.
- **The budget verdict and the bot risk editor** print the server's note in place of "Fits — …"
  when the shares go past the cap. Nothing here decides it; `note` is served.
- **Add a bot** judges "needs room" against the CAP, not the room: a bot that only fills the account
  joins and shares; the server stays the gate.
- **The stack form** prints the stack's note in grey under the total.
- **The Priority section** (account panel, two or more bots): the bots in the served order, dragged
  with native HTML5 drag events (no library) or moved with the up/down arrows for keyboard use.
  ⚠ The draft is bound to the served order it was made against (`from`), like the budget edits —
  a changed served order drops it. ⚠ Save order is offered when a bot has no saved rank even with no
  edit, because the list is then only the by-name fallback. Save → `useSaveAccountPriority` → the
  accounts list re-reads, so the panel shows the order as saved.
- `tests/bots-accounts.spec.ts`: fixtures carry `share_note`, the take-turns check became the sharing
  check, the over-cap banner check uses a bot above the cap, and a new check drags a row and asserts
  the saved body.

## The bot ROWS are the priority order, and you drag them there (2026-09-16)

Aaron, 2026-09-16: *"after I click an account… it shows the account on the right with the bots
listed, I should be able to drag those bots either up or down under the account, and the highest
bot on the account is the highest prioritized bot."*

🔴 **The rows were ALREADY rendering in the saved order and gave no way to change it.** The
backend sorts an account's bots by rank (`services/bot_accounts.py::group_by_account`), so the
detail column has always been a ranking on screen — with the only control for it one click away in
the account panel. A list that looks like a ranking and does not act like one is the defect.

- **Every bot row in the detail panel is draggable**, native HTML5 drag events, no library — the
  same mechanism the account panel's list uses. A grip appears in the row's left gutter on hover.
- ⚠ **The grip KEEPS ITS SPACE on every row and is only revealed on hover** — the rail pin's idiom,
  for the rail pin's reason: a box that collapses would twitch every bot name sideways as the
  pointer crosses the list. An account with one bot gets the space and no grip.
- **One draft, and it names its account.** Several detail panels may be open; only one can be
  dragged at a time. ⚠ Bound to the served order it was made against (`from`), like the account
  panel's list and the budget edits — this page refetches in the background, so a draft made
  against an order that has since moved is DROPPED rather than saved over a change nobody saw.
- **The bar under the rows appears only when it has something to say**: an order dragged and not
  saved (`data-state="dirty"`, Discard + Save order), or an account with no saved rank at all
  (`data-state="unsaved"`). An account already ranked and untouched says nothing — the row order IS
  the answer, and a permanent bar repeating it is the redundancy this page has a rule against.
- 🔴 **`orderUnsaved` is rule 1 on screen.** With no rank saved the rows are only the by-name
  fallback and NOBODY waits for anybody, so the bar says exactly that. A ranked-looking list that
  said nothing would be the page asserting a ranking it does not have.
- **The drag is refused, not attempted, when it would build a request the server rejects**: one bot
  (nobody to go ahead of), or any bot whose config will not read (the server refuses an order that
  is not exactly the account's bots).
- ⚠ **The account panel's Priority list STAYS** — its up/down arrows are the only keyboard route to
  this order. The two read and write the same served order and the same hook.
- `tests/bots-accounts.spec.ts`: five checks, each naming its own mutation — the saved body is the
  draft not the served order, the drop actually moves the row, the unsaved bar, Discard, a lone bot,
  an unreadable config.

## 🔴 The page may NOT add the risk shares up itself (2026-09-04)

`AccountsTab` renders `group.share_total_pct` and `group.share_overflow_reason` straight off the
API. **It used to reduce the shares locally, with `?? 0` in it** — so a bot whose risk could not be
READ counted as a bot risking nothing, and the browser printed a total that fitted under the cap on
an account the save would refuse. The backend's own check refuses that leniency by name.

⚠ **A number is not the same as a rule, and only the rule is served.** The sum, and whether it
fits, are both computed server-side; this page draws them. Deciding *does it fit* from two numbers
here is the same rule written twice in two languages — the shape steps 9 and 10 of
`scripts/run_all_tests.sh` exist to catch — and it had already drifted.

⚠ **`share_total_pct` of `null` means the shares CANNOT be totalled, never zero**, and it renders
as that sentence. The guard is `typeof x !== 'number'`, not `=== null`, so a payload missing the
field (an older cached response) says *cannot be totalled* rather than printing `undefined%`.

⚠ **The total is shown for ANY account with bots on it, not only when something is wrong.**
Splitting a ceiling between two bots is what this panel is for, and until this landed the number
being split appeared only inside the take-turns note — which needs the cap to be at or under the
largest single share, **so the intended two-bots-at-5%-under-10% configuration never showed it at
all.**

⚠ **The take-turns note no longer states the total itself**, so the page holds one copy of the
number rather than two that can disagree.

**`tests/bots-accounts.spec.ts` — 3 new checks.** ⚠ **`group()`'s default is
`share_total_pct: null`**: a number in the fixture would be a second statement of the sum the
backend computes and would go stale the moment a check changed its bots. ⚠ **The `STACKED` fixture
carries an overflow reason**, because two bots at 10% under a 10% ceiling really IS
over-subscribed — a fixture stating only the shares would describe an account the backend cannot
produce.

## A blank cell is not a diagnosis — the Bots page's `No MT5 link` chip

**Added 2026-08-04, and this page was the ONLY place the incident was visible.** MetaTrader
auto-updated itself on the VPS and restarted, taking the running bot's connection with it. The bot
stayed alive and kept stamping its heartbeat — so the watchdog saw a healthy bot, the process list
still had it, and this row said **RUNNING** — while it received no bars for 50 minutes across an
open session. The one thing on screen that reflected any of it was **an em-dash in the Balance
column**, which is also what a bot that has simply not reported yet looks like.

`BotStatus.mt5_link` is the fix, and the rendering rules are the interesting part:

- **The chip sits BESIDE the Running pill, it does not replace it.** Both facts are true at the same
  time and they are different questions: the process is ALIVE (so restarting it is the fix, and the
  watchdog was right not to fire) and it is BLIND (so it is taking no trades and managing none).
  Collapsing them into one word loses whichever half the reader came for.
- **`=== false`, never falsy** — same rule as `mt5_connected` above, in the same file. `null` means
  the bot has not stamped a link state (stopped, or predating the field), which is not the claim
  "disconnected", and painting a healthy bot as disconnected is the identical mistake in reverse.
- **The balance cell says `no link` in `warn` rather than the em-dash**, so the two causes of a
  missing number can never look the same again. The em-dash survives for the genuinely-unknown case.
- **The tooltip states what happens next** ("retries every 30s; if this persists, restart the bot"),
  because the runner self-heals and a warning with no action reads as something the reader must fix.

**The transferable rule, and it is not this folder's usual label-vs-code one:** every layer under
this cell behaved defensibly on its own — an empty bar frame is a fine thing for a data call to
return, and a null balance is a fine thing to write when you have no balance. The defect was that
*"no data"* and *"cannot ask"* were the SAME VALUE at every hop, so by the time it reached the
browser the distinction did not exist to render. When a cell can be empty for two reasons, the API
has to say which.

## The affirmation ribbon, and why it holds still

**Built 2026-08-03, Aaron's request.** Six affirmations rotate in the top bar, one every 20 seconds.
The list is the `AFFIRMATIONS` array in `components/TopBar.tsx` — edit that and nothing else, since
the rotation reads its own length. They render uppercase on one line that never wraps, so roughly 40
characters is the ceiling before a narrow window clips one.

**The Refresh button moved to the sidebar footer to make room** (`Sidebar.tsx` → `RefreshAll`, styled
as a peer of Settings and collapsing to an icon like every other row). Refresh-everything is a global
action, so the global nav is an honest home for it, and the top bar's width was the only space in the
shell wide enough to hold a sentence.

**The animation is deliberately front-loaded, and the brief is the reason.** These are meant to
register subconsciously, which rules out the obvious treatment: a looping shimmer or a pulsing glow
stops being SEEN within minutes — the eye adapts to steady motion and files it as background — and
until it does, it competes with the numbers the page is actually for. Looping motion reads as
decoration; motion that finishes reads as intent. So the whole budget goes on the ARRIVAL — words
fade up 75ms apart, so the line assembles at the pace of a voice saying it and the eye travels along
and READS it rather than glancing at a block that appeared — and then it holds perfectly still for
its full turn. Still, bright and identical every time round is what repetition needs in order to
encode. The exit is a plain fade, duller than the entrance on purpose: two ends competing for
attention would make the change feel like an effect.

Four things that will break it if they are changed back:

- **`-webkit-background-clip: text` is not usable here, although the wordmark beside it uses exactly
  that.** The clip silently stops working when the same element also carries a `transform` — and this
  line moves on every change — at which point the gradient floods the whole box and the transparent
  letters vanish inside it. What you see is a solid gradient BAR where the text should be, which is
  how it shipped twice during the build. The ribbon paints a flat colour instead, and the word-by-word
  entrance would have forced that anyway: a gradient can span the whole line or restart per word, and
  neither survives animating each word on its own.
- **The rAF that starts the entrance needs the timer beside it.** `requestAnimationFrame` does not
  fire in a BACKGROUND tab while the timers driving the rest of the cycle keep running, so on rAF
  alone the ribbon parks in `enter` — fully transparent — until the tab is looked at again. The 80ms
  fallback is the fix for a real stall, not belt-and-braces.
- **It is `absolute inset-0` across the whole bar, not a flex child.** Laid out in the row it centres
  in the space LEFT OVER beside the wordmark, which is visibly right of centre. The two therefore
  overlap at narrow widths: the wordmark carries `z-10`, and the type steps down from 22px to 17px
  below 1280px so the longest line still clears it.
- **One node shows one affirmation.** The three phases (`enter` → `in` → `out`) reuse a single
  element rather than crossfading two copies, so a stalled timer can never leave the bar reading two
  things at once.

Verified in headless Chrome at 2.5s and at 25s — message 1 then message 2, which is what proves the
rotation advances rather than the first line simply sitting there. That check is also what caught the
background-tab stall.

## Key UI decisions

**Platform-based job lock** — `GET /backtests/running-job` returns `{ nt8, mt5, python }: RunningJobInfo` (polled at 5s via `useRunningVpsJob()`). All three lock independently. **Never branch on `runner === 'mt5'`** — that conflated two different questions (which lock scope? is this NT8-only UI?) and silently gave Python jobs the NT8 badge and the NT8 lock. Resolve both through `lib/runner.ts`: `runningJobFor(runningJob, runner)` for the lock (`jobBlocked = !!runningJobFor(runningJob, run.runner)?.running`), `isNt8Runner(runner)` for NT8-only UI (futures contract months, prop-challenge rulesets, injected foundational params, the NT8 chart export), `runnerMarket(runner)` for forex-vs-futures ruleset filtering (MT5 and Python are both forex), and `runnerScope`/`RUNNER_LABEL`/`RUNNER_FULL_LABEL` for display. It mirrors the backend's `_SCOPE_RUNNER_SQL`, including NT8 as the fallback for unknown runners. Lock surfaces: `RunBacktestModal`, `OptimizeButton`, `Tier3WarningModal`, `RunRow` retry, `BacktestDetail` retry/rerun. `Strategies.tsx` calls `useRunningVpsJob()` at page level (result unused) to keep the cache warm — without this, the first modal render sees `runningJob = undefined` and treats the lock as clear. All six job-lifecycle mutations invalidate `['lab', 'running-job']` on success. `BacktestSummary.runner` must be mapped in `_row_to_summary` or `run.runner` is undefined on the frontend. The backend `get_running_job()` correctly routes MT5 optimizations to the `mt5` bucket (joins `strategies` on runner) — a running MT5 optimization does NOT set `nt8.running`.

**Optimization running indicator** — `OptimizationNestRow` shows a pulsing gold dot (`w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse`) when `opt.status === 'running'`. The parent `RunRow` does NOT show an "OPTIMIZING" badge — the dot on the sub-row is the only running indicator. MT5 optimizations emit live `completed_count`/`total_count` per combo; the sub-row counter (e.g. "35/36 runs") reads these from the optimization record's `completed_runs`/`estimated_runs`.

**Tab-specific active dots** — each Backtests tab has its own pulsing dot logic (not "any job running"): `runsActive = allRuns?.some(r => !r.sweep_id && r.status === 'running')` (includes opt-combo full backtests while running). `sweepsActive = allSweeps?.some(s => s.status === 'running')`. `optsActive = allOpts?.some(o => o.status === 'running')` — only fires when an actual optimization grid is running, NOT during a single-combo full backtest (`retry_single_optimization_run` uses `set_running=False` so the optimization stays `complete`). Running opt-combo full backtests appear in the Runs tab filter (`!r.optimization_id || r.status === 'running'`) with their OPT chip visible, then disappear once complete.

**Runs table columns** — "Score" = WorthinessBadge (Tier 1/2/3, the quality verdict; the `WorthinessLegend` "Score key" above the table explains the tiers). "Trades" = `run.trade_count` for at-a-glance volume. "Challenge" = firm name chip(s) showing which challenges the run was evaluated against. Score and Challenge are intentionally separated: score = how good, challenge = under what rules. Per-firm PASS/WARN/DISCARD detail lives only on BacktestDetail. There is **no Status column** — run status is a small `RunStatusIcon` glyph after the strategy name (running = pulsing accent dot, failed = red ✕, complete = green dot); a finished run is otherwise self-evident from its populated metrics. Nested rows (optimization/sweep/tune) keep their own status pill and still span `colSpan={12}` (column count is unchanged: Status removed, Trades added).

---

## One status per row (2026-09-12)

🔴 **A row carried up to five tags beside the bot's name** — no link, trading off, halted, review,
trade open, each its own colour and shape. On the live account two wrapped and cut the name to
"SOS …"; on the demo every pill was green. Aaron: *"my eyes don't know where to go."*
`src/lib/botCondition.ts` reads a bot ONCE for every list of bots — the Bots rows, the bot panel's
header, the account panel, the Overview — and `src/components/BotStatus.tsx` draws it: one pill, a
count.

- 🔴 **No dot, since the same day.** One sat before every name and said what the Status column
  says — Aaron: *"the status column is redundant … remove the dots and just use the status column
  solely since you put other statuses there."* The word is the one kept: it says what a dot cannot.
  The account panel's bot list lost its dot too, and since 2026-09-13 draws the same pill.
- **The word is a RUNNING bot's worst problem, else what it is doing** — "Running", or the trade it
  holds ("Long 0.40 lots · +1.2R", only the R coloured). Worst first: halted, a review alert,
  trading off, no MT5 link, a review warning, locked for the day. The rest are counted beside the
  word ("Halted +1") and spelled out on hover with the uptime, whose column went.
- ⚠ **A stopped, errored or benched bot keeps its own word** and counts its problems: they explain
  the stop, "Needs review" alone reads as a running bot, and on the Overview "Benched" is the only
  thing saying a bot is benched.
- ⚠ **The count carries the colour of the worst thing it hides** (a "+1" hiding a halt is red); the
  word carries only its own, so "Benched" is never red for a problem it does not name. With no dot,
  the count is what carries the row's worst.
- 🔴 **The word is a PILL in its state's colour (2026-09-13)** — green running, amber worth a look,
  red stopped / halted / error, grey benched, dashed grey unknown. Aaron: *"the status for running
  or stopped should be color coded … make it consistent."* Grey words for a healthy bot read as no
  status, and the panel header and the account panel each drew it their own way. ⚠ Nothing else
  took colour: P&L keeps its sign colour, Return % and Per trade stay neutral, the net is text.
- ⚠ **Every flag is read `=== false` / `=== true`** — `null` is could-not-ask and raises nothing
  (rule 1). ⚠ **The page decides nothing**: every reason on the hover is the bot's own sentence
  (`algos/CLAUDE.md` → *Whether the account may TRADE*, *The heartbeat says what the bot holds at
  the broker*). ⚠ **No R when it is `null`** (a trade picked back up from an older record), never
  one off a stop that has moved.
- 🔴 **The panel header drew a green "Running" over a halted bot** until it read the same condition.

**The version pill is calm when current, amber when it needs you.** Up to date is a plain outline —
green on every row was most of why the demo read "everything is green". 🔴 **RESTART: the bot runs
older code than the box holds.** The version counts the strategy only and the runner moves only on
a restart, so both live bots read "up to date" eight fixes behind. `restartReason`
(`src/lib/botVersion.ts`) turns the backend's count into a sentence: the pill reads `v174 · restart`
and the deploy panel *"… is running older code"* with a gold **Re-deploy & restart**.
- ⚠ **RUNNING only** — a stopped bot loads the new code when it starts.
- ⚠ **The reading must describe THIS process**: one that began more than 10 minutes after the
  recorded start is a newer run and is not asked again. Measured on the SNAPSHOT's clock
  (`fetched_at` less uptime) on the row AND the panel — the panel on this machine's clock disagreed
  with the row.
- ⚠ **Re-deploy, never Restart**: a plain restart starts whatever the box's checkout holds.
- ⚠ **Pill order: deploying, loading, unread, unknown, behind, restart, not pushed, current** — a
  deploy restarts too, and restart is something the bot needs where not pushed is something this
  machine needs.

Pinned by nine offline checks — five in `tests/bots-accounts.spec.ts` (one word per row, a benched
bot keeps its word, trading off, in a trade or halted, no R when unknown) and four in
`tests/bots-version.spec.ts` (RESTART on row and panel, a newer run is not asked again, a stopped
bot is not asked, the panel header) — plus `tests/overview.spec.ts` on the running app, 22 of 22.
16 mutations planted in a throwaway worktree, 16 killed. *No dot*: the row and panel-header checks
assert none is drawn, and a dot put back fails both.

Backend half: `../backend/CLAUDE.md` → *The RUNNER is counted too*.

## The bot panel says each thing once (2026-09-12)

Aaron, on the live panel: *"Risk % per trade it is shown twice … a lot of redundancy."* The *One
status per row* rule, applied to `BotDrawer.tsx`:

- **Risk** (`BotRiskEditor.tsx`): the value lives in its box, the dollars beside it follow what is
  typed, and Save with "was 5%" appears once it changes. The setting's own name prints only when a
  panel has more than one — the heading already names the one it has.
- **Account:** the selector, the account's name and Take off — for a running bot too since 2026-09-13
  (*A running bot is stopped first, never locked*). From 2026-09-12 a running bot got one line and no
  controls, because a greyed selector and Remove beside it said one thing three times.
- **Version:** what a deploy does is the heading's hover (`SectionTitle`'s `hint`), not a paragraph
  on every open. ⚠ The deploy card keeps the bot's name: on a live deploy it says which bot moves.
- **Record:** one line — "2 won · 0 lost · record …", or "No closed trades yet", never "0 / 0".
- ⚠ **Section headings are grey, not gold** (`drawerParts.tsx`), in both panels.
- 🔴 **What is wrong comes FIRST, in words** (`Attention`, the same day) — Aaron: *"Review what?
  nothing is telling me what to act on."* Each problem the row counts gets its own sentence, and a
  review's findings are listed one by one with the time that hourly review ran. The words are
  `botCondition`'s; nothing is decided here.
- 🔴 **What the platform closed on its own is one grey line under it** (`ResolvedOnItsOwn`,
  2026-09-13) — Aaron: *"I don't want to manually mark anything as reviewed."* The review files what
  is over apart from what is open (`../backend/CLAUDE.md` → *Open, or over*); `botCondition` raises
  *Needs review* off the open list only, and the rest is a collapsed "N resolved on its own ·
  nothing to do", each with why it is over. Never counted, never coloured.
- 🔴 **The header is the status and nothing else.** The account's number sat beside it as a link
  into the account's panel, so "Needs review · account N ›" read as one thing and the click meant
  to explain the review opened the account. The account is named in its own section, with **Open
  account ›** on its heading (`bot-account-link`).

Pinned by three new checks and three re-pointed in `tests/bots-accounts.spec.ts` — the panel says
each thing once, the running-bot move and remove (re-pointed 2026-09-13 to stop first), the
record's one line including a bot with no closed trade, what needs attention in words with the
account on its own line (the halt, each review finding and its time, **Open account ›** landing on
that account, the badge reading *Live*), and a review with nothing left open reading as no status
with its history one click away. 17 mutations in a throwaway worktree, 17 killed.

## A running bot is stopped first, never locked (2026-09-13)

Aaron: *"it is not intuitive that you have to stop a bot to remove from account … maybe the remove
button should always be there and when we click then it says are you sure bot will be stopped
first?"* Remove, Move and the account panel's Take off are offered on a RUNNING bot; the confirm
says it is stopped first, and `pages/Bots/stopFirst.ts` carries it out.

- 🔴 **The rule under it stands**: a bot reads its account at startup, so the server refuses the
  write while it runs (409). What moved is who does the stop — the page, not the reader.
- 🔴 **The server's stop only ASKS** (`stop.request`; the bot exits within ~30s), so the page
  re-reads the fleet every 5s until the box says the bot is not RUNNING, and only then writes. A
  write sent on the stop call alone is one the server refuses.
- 🔴 **Nothing on a guess**: 90s without the box saying stopped writes NOTHING, and the toast says
  it was asked to stop and not moved.
- 🔴 **A move onto a DEMO account starts it again** (Aaron, the same day: *"let them automatically
  start"*) — a move changes where a bot trades, not whether. Stop, write, start, in that order,
  and the start only once the write went through; a write that failed leaves it stopped and says
  so. ⚠ **Onto a LIVE account it stays stopped** — the first real-money start is a click (Aaron,
  2026-09-13: *"I will start the live bot manually"*). A
  removal leaves it stopped by definition.
- 🔴 **A bot HOLDING A TRADE is not moved or taken off.** Stopped, its trade stays on the old
  account with nothing managing it, and it halts on the new one. The controls say so while the
  heartbeat reports the trade; the server refuses the write off the bot's own trade record, which
  also covers a stopped bot and the whole-set go-live (`../backend/CLAUDE.md`).
- ⚠ **The wait lives on the PAGE** (`useStopFirst` in `index.tsx`), so closing a panel mid-wait
  does not drop the write; the row shows *Stopping*, then *Starting*.
- ⚠ **A demo move of a running bot never goes out on the pick** — a card says it is stopped, moved
  and started again (`move-stop-first`); a live move says it is left stopped, inside the confirm.
- ⚠ Start and stop toasts NAME the bot (`SOS Fade · demo stopped`); they printed its key.

Pinned, with the one pill and the shared column width, by `tests/bots-accounts.spec.ts`: 4 new
checks (Remove waits for STOPPED, a bot that never stops is not taken off, one pill on the row, bot
panel and account panel, the columns' width) and 3 re-pointed (a running bot's Remove, Move and Take
off). 15 mutations in a throwaway worktree, 15 killed. The restart and the trade guard: 3 new (a
live move is not started, a failed move is left stopped, a bot holding a trade offers no move) and
2 re-pointed (Move starts it again and names the bot in its toasts; Remove never starts it); 14
mutations, 14 killed, each red on its own assertion.

## Take off is ONE button on both panels (2026-09-13)

Aaron: *"there should just be one button going from take off -> stop and take off -> removing then
modal close … keep it consistent whether I am on the account removing a bot or I clicked on the
bot."* Each panel had its own copy in its own words: the bot panel's fell back to its idle label
mid-flow with a sentence beside it, the account row showed a Stopping pill beside a greyed button,
and neither closed.

- **While a row is Starting / Stopping / Restarting, its pill is the ONLY control** — Remove is hidden, not greyed (Aaron, 2026-09-16).
- 🔴 **One flow, one control**: `useTakeOff` (`pages/Bots/takeOff.ts`) runs it and `TakeOffButton`
  draws it, for the bot panel (`remove-<key>`) and every account-panel row (`take-off-<key>`).
- **Take off → Stop and take off (Confirm take off for a stopped bot) → Removing…**, then the bot
  panel closes; the account panel STAYS OPEN (Aaron's call, the same day) and the bot leaves its
  row. No text beside it; while armed or at work it is the row's only control — no Stopping pill,
  no Start or Stop. A refusal, or a bot that would not stop in time, gives the button back.
- ⚠ **The close is an EFFECT, never the flow's own callback** — that closure holds the URL as it was
  at the press, so it would also close whatever the reader opened since. It never fires once the
  panel is gone.
- ⚠ **Removing… keeps the confirm's colours at full strength** — faded like a disabled control, it
  read as dead.
- ⚠ **One take-off at a time per panel** — the page holds a single stop-first wait.
- ⚠ **On the account panel the button holds Removing… until the account list has re-read** and the
  bot has left its row; letting go at the write would flash Take off on a bot already off.
- ⚠ `stopThen` now resolves once the write has answered, so the page stays busy through a
  removal's write, as it already did through a move's.
- Tests: `bots-accounts.spec.ts` — 3 new (Removing… then the bot panel closes; a refused take-off
  gives the button back; a running bot's account row, one button with nothing beside it) and 6
  re-pointed, the account panel's now held open with Removing… until the list re-reads; both Bots
  specs 143 of 143. 16 bugs planted in a throwaway worktree, 16 caught. 🔴 **A "nothing
  beside it" count is taken at an instant, never retried**: the take-off ends by itself, and a
  retried count of 0 waited for that and passed against a planted bug.

## The Bots page shows what each BOT made, and colour means one thing (2026-09-05)

🔴 **Earnings are keyed by ACCOUNT AND BOT, never by bot alone (2026-09-11).** A bot that moved has a
row on each account it traded, and a bot-keyed map handed every row whichever entry came last — the
demo trades under the live heading. ⚠ **An account its bots LEFT is an ordinary account card on
Trading** — Aaron: *"what if I wanted to test out more bots on a demo account while the live bot is
also trade … it shouldnt matter."* It shows the balance its bots last read, with the time
(`balance_read_at`), its net and Return %, no cap chip while it is empty, a "No bot is on this
account now" row whose **Add a bot** opens the panel on the picker (`add=1`), and a past row per
departed bot ("Moved to live account N", its own P&L and Return %). A new bot of ANOTHER strategy
joining keeps those rows; one of the SAME strategy carries them on in its own row (next section),
and the side score counts departed bots' records on EVERY account — the demo record is what
live-against-demo compares with. ⚠ **One place per account**: on Trading means never also on
Unassigned. ⚠ The bot panel reads the record of the account its CONFIG names, the same source the
rows are laid out by. Pinned by three tests in `bots-accounts.spec.ts`, 11 mutations run, 11 killed.


Aaron: *"the page bots looks very boring now … how much percent each bot made on the account thus
far … how much is the account up net-wise? … you don't need to put two trading, I could see two is
trading … you don't need to put two bots."* Plus the blocker: *"there's no more edit button. I
don't see a way to configure anything."*

🔴 **THE ROW'S MONEY IS THE BOT'S OWN, NEVER THE ACCOUNT'S.** Every figure comes off
`snapshot.earnings`, computed server-side in `services/bot_earnings.py`; **this page derives none
of it.** What an account made and what its bots made are two measurements and whether they agree
is the finding — deriving either here is the same rule written twice in two languages, which is
how the risk-share total already drifted on this very page.

🔴 **`NetSplit` is one bar per account, one segment per source, and the last segment is the money
NO BOT RECORDED MAKING.** MEASURED live 2026-09-05: SOS Fade 26%, not-from-these-bots 74%. That
segment is the point of the chart, not a rounding strip. ⚠ **Widths are absolute magnitudes and
colour carries the sign** — a bar shrinking as a bot loses more would read as a bot doing less.
⚠ **A segment under 1.5% still draws at 1.5%**, so a real contribution cannot vanish into a
hairline that reads as *made nothing*; the LEGEND carries the true figures so nothing is read off
pixels. ⚠ **Withheld entirely when the account's net is unmeasured** — a bar with no total behind
it is a shape with no scale.

⚠ **`tintByKey` is ONE map per account, read by the row's rail AND the bar's segments.** Two
lookups is how a segment ends up a different colour from the row it names, on the one chart whose
job is saying which bot is which. **`BOT_TINTS` is explicit, never `series.filter(c => c !== pos)`**
— the shared palette holds near-misses (`#00ff7f` against pos `#00ff82`), the trap that already
made a stack leg draw in the portfolio's colour. Green and red are absent by construction: on this
page they mean up and down.

⚠ **Colour is reserved for P&L.** Everything else stays neutral, so a green figure always means
the same thing rather than meaning *this row rendered*.

🔴 **AND THE REMAINDER LINE NAMED THREE CAUSES WHILE A FOURTH WAS PRODUCING IT (2026-09-09).**
*"a manual fill, a deposit, or a trade older than the record"* are all real — and it said exactly
that for a trade that had simply **not synced yet**. The bots' figures were read off this machine's
committed archive and the balance over SSH, so anything closed since the last sync sat in the
balance and in no bot's row: the bot under-reported by its profit and this line over-reported by the
same amount. MEASURED: the extreme leg's **$1,305.58** target, and a **66-minute** lag with no upper
bound. **A stale read and a real attribution gap were the same pixel.** The backend reads the box's
own ledger on the snapshot's connection now and, when it cannot, says the split is provisional —
rules in `../backend/CLAUDE.md`. ⚠ **`records_live === false`, never falsy**: an older payload
carries no such field, and reading a missing one as *the record is behind* puts a caveat on every
split that never needed one. ⚠ **The sentence is SERVED, not composed here** — it carries a measured
lag, and rebuilding it in the browser is the same rule written twice in two languages that this very
page has already been bitten by.

🔴 **A row is a `<div>` whose NAME is the button — never a `<button>` holding buttons.** That is
invalid markup, React said so at runtime, and the unassigned rows had been saying it since the
rewrite. The row now carries four controls and a row-wide click behind them makes every miss open
a drawer over the thing you were aiming at.

🔴 **Every row carries an explicit Configure control.** The drawer always held the settings; a row
you have to GUESS is clickable is a feature nobody has, and that is exactly how it was reported.

⚠ **The cap is the only count left on the account header.** `2 bots · 2 trading` went — the rows
below state both, and a number restating what is already on screen is the duplication this page
was rebuilt to remove.

⚠ **The money sits NEXT TO THE NAME**, not out with the machinery. 400px of empty grid between the
two made the row read as a name with some settings after it.

⚠ **A percentage carries its DENOMINATOR** — the drawer says *% of the account's opening balance*
and the account's net names the balance and the bot that recorded it. The backtest page's own
*1439.7x of what* lesson, and it bites harder here because two bots legitimately anchor differently.

⚠ **The header sums net across ACCOUNTS, never across bots**, and an account whose net nobody
could measure is LEFT OUT and said, never added in as zero.

### The second pass, after Aaron read it (2026-09-05)

🔴 **"WHERE IS CONFIGURE?" WAS ASKED TWICE, AND THE SECOND TIME THE CONTROL EXISTED.** First it was
only the row itself; then it was an ICON beside three other icons and he still asked *"where is
configure? We used to have a Configure tab. That's gone completely now."* **It says the word now.**
An icon is a rebus for anybody who has not already learned it, and the whole reason this control
kept going missing is that the tab it replaced had a NAME. Stop/Restart/Logs stay icons because
they are verbs you can guess from a shape; *configure* is not a shape.

⚠ **It is the same target as clicking the bot's name — one drawer, one route in.** A second way in
is fine; a second IMPLEMENTATION is what this page keeps being rebuilt to remove.

🔴 **The rows are a TABLE and were unlabelled.** Four numeric columns with no heading means the
reader decodes them from their own shape, and `5%` beside `+12.0% of account` is exactly the pair
that gets read as the same kind of thing. ⚠ **ONE grid template (`GRID`), shared by the heading row
and every row under it** — a hand-copied column list is how a heading ends up confidently over the
wrong number, which is worse than no heading.

🔴 **The cap is a CHIP, not grey prose.** As tertiary text beside the account number it read as
another piece of identity — *"the cap is missing. Well, not missing. It's just not obvious."* It is
the one number on this card that can refuse a trade, so it takes a border and the gold this app
reserves for a limit. ⚠ **NO CAP is the LOUD state, in warn.** An account with no ceiling is the
condition worth noticing, and rendering it quieter than a set cap is backwards.

🔴 **`VersionPill` carries a BORDER in every state.** It was `bg-bg-surface-2 text-text-secondary`
— the same grey as the surface behind it — so on a page where every other column is grey the
version stopped registering as a claim. ⚠ **Up to date was GREEN until 2026-09-12 and is a quiet
outline now** — a green tick on every row was noise (*One status per row*). ⚠ The unknown
state stays NEUTRAL and still gets a border, or it is the one state that looks like a rendering
failure rather than a finding. ⚠ **It never wraps and sizes to its text (2026-09-10)** — in a 92px
column the behind state broke onto two lines; the column is 136px, and the widest state
(`v218 · not pushed`) MEASURED 134px. Re-measure before adding a longer one.

⚠ **The per-bot identity rail was REMOVED from the rows** — Aaron read it as decoration, which on a
row that already names the bot is what it was. **The split bar keeps its segment tints**, because
two segments have no other way to be told apart, and its legend spells out which is which.

### `refuseLiveWrites` — the browser suites were allow-by-default

🔴 **Both bot suites end their catch-all with `route.fallback()`.** Every write they trigger today
is routed in its own test — CHECKED, not assumed — but that is a property of how the tests happen
to be written rather than of the harness, and this backend PATCHes an instance config, pushes it
and pulls it **on the live trading box**. A check that reaches that path once has already spent the
thing it was protecting.

⚠ **Register it BEFORE a spec's own `mock()`.** Playwright matches the most recently registered
handler first and `fallback()` walks backwards, so it only ever sees what the spec did not answer.
⚠ **It ABORTS rather than fulfilling a plausible success** — a fake 200 lets a test pass while
proving nothing about the request it meant to make. ⚠ **Reads pass through**; they are what makes
these suites worth running against a real backend, and the worst a read costs is a slow test.

### The third pass — subtraction, mostly (2026-09-06)

Aaron read the second pass control by control. Most of what came back was *take this away*, and the
two removals below are the ones with a rule under them.

🔴 **THE SPLIT BAR IS GONE, AND ITS SEGMENTS WERE THE PROBLEM.** It drew one segment per bot plus
the unattributed remainder — *"is the purpose of it to show the breakdown of which strategy added
how much equity per account? because if that's the case, I thought that's what the P&L column is
for."* He was right, and the fix is not a better explanation: **only ONE segment was saying
something the row above it could not**, so only that one survives, as a line of text. ⚠ **It still
has to survive** — the remainder on the live account is $3,344.80 of duplicate positions a
broker-timeout defect opened, and folding that into "the bots" would report a fixed bug as a
strategy result. ⚠ **It renders only when there IS a remainder**: a permanent row reading `$0.00`
is a green tick nobody reads by the second day.

🔴 **THE FLEET TOTAL CAME OFF THE HEADER.** It carried the fleet balance and the fleet net, both
already stated on the account they belong to — *"I don't know if that information is necessary.
Like, I could just look and see."* ⚠ **The RUNNING COUNT stays**, because it is the one thing on
that line you cannot read off the rows without counting them yourself. ⚠ **And the unread-balance
warning stays**, because it is a FAULT and a fault has no other home. **A number restating what is
already on screen is not a summary; it is a second copy that can disagree.**

⚠ **The per-bot colour palette went with them** — both its consumers are gone. If one comes back:
the list must be EXPLICIT, never `series.filter(c => c !== pos)`, because the shared palette holds
near-misses (`#00ff7f` against pos `#00ff82`) and that is how a stack leg once drew in the
portfolio's own colour.

🔴 **THE ACCOUNT NUMBER LEADS ITS HEADING** — *"the account number should be the thing prefix in
the account."* The login is what the broker, the terminal, the instance config and every refusal
message name it by; the label is a nickname somebody typed here. **When the two disagree the number
is the one that is right**, so it is the one the eye lands on.

⚠ **A live/demo filter, as TWO chips and no third.** He asked for live-vs-demo and said he does not
care about an "all" — so ALL is the state with neither chip pressed, reached by pressing the active
one again. ⚠ **The default is ALL anyway**: every account on this box is a demo today, so defaulting
to LIVE opens the page empty, which is indistinguishable from a page that failed to load. ⚠ **It
lives in `?kind=`**, and **filtering happens LAST on the assembled lists** — `assigned` decides which
bots count as unassigned, and computing it against a filtered set invents bots with no account
whenever a filter is on. ⚠ **An emptied page SAYS what it is hiding and offers the way back**; a
blank list and an empty fleet look identical, and only one is a finding.

🔴 **`AccountForm` gained a LABELLED exit at the top.** Cancel had always been at the BOTTOM, past a
dozen fields, so the only exit a reader finds is a 12px `X` glyph — *"there's no back button. That
sucks. Maybe there's a little x."* ⚠ **The bottom Cancel STAYS**: in a scrolling pane you cannot see
both ends of, deciding not to START and deciding not to FINISH are different moments.

⚠ **Both drawers went 440px → 620px** — *"make this side panel a little wider so it could fit more
information in, so there's less up and down scrolling."* Capped, never a fraction of the viewport:
a panel wide enough to hide the list it was opened from is a page you navigated away from without
meaning to. ⚠ **The account drawer is 720px since 2026-09-10**, so Take live can run inside it (see
*Demo → live*).

🔴 **THE DEPLOY SECTION SAYS "DEPLOY".** He opened with *"you're still not telling me how do I
promote a bot"* and then found it himself under a heading reading **Version**. The control was
reachable; the heading named the NOUN when the reader is looking for the VERB. **Third time a
control on this page has been reported missing while present** — the row, then the icon, now the
heading — and every time the fix was a word rather than a position.

### 🔴 The tab collapse dropped four SAFETY WARNINGS, and 44 red tests were the finding (2026-09-06)

**`AccountsTab()` is DEAD — nothing renders it.** The rewrite that collapsed the tabs kept three
small exports from that file (`AccountForm`, `AddBotRow`, `nameOf`) and left 1,775 lines
unreachable. The cap EDITOR moved to `AccountDrawer`; **the things telling you the number is wrong
did not**, so the one screen that can over-allocate an account lost every check on it:

| gone | what it says |
|---|---|
| `cap-shares` | what the per-trade shares actually add up to against the ceiling |
| `cap-overflow` | they do NOT fit — the same sentence the save is refused with |
| `cap-disagreement` | the bots state different ceilings, so none of them will start |
| `magic-clash` | two bots share an order tag and would read each other's orders as their own |

🔴 **IT WAS FOUND BY ASKING WHY 44 BROWSER TESTS WERE RED INSTEAD OF DELETING THEM.** They were
written against a page that still had these, so **the red WAS the finding** — exactly what they
exist for. Re-pointing them without looking would have deleted the evidence and left the gap.

⚠ **The share total is SERVED, never summed here.** `AccountDrawer` had grown its own `reduce`
back — safer than the original (null when any share is unreadable rather than counting it as zero)
and still a SECOND answer to a question the server already answers. `BotAccountGroup.share_total_pct`
carries that warning in its own type, and this file's own *never sum the shares* rule is one section
up. **A rule stated in a type is not a rule the next file inherits.**

🔴 **AND A CAP DISAGREEMENT RENDERED AS `no cap` ON THE ACCOUNT HEADING — a live defect, not test
rot.** That chip's tooltip read *"nothing here refuses a trade for being too large"*, which is the
OPPOSITE of what a disagreement means: the bots do state ceilings, they cannot agree, and the
consequence is that **none of them will start**. Rule 1 in a chip — *nobody set one* and *they
cannot agree* are different facts and only one is safe to read as quiet. Three states now, and the
disagreement is the loud one.

⚠ **`cap` was ALREADY forced to null on a disagreement** and the drawer's comment said why — so the
figure was correctly withheld on both surfaces and **neither said what had happened**. Withholding a
number without naming the reason hides the fault instead of reporting it.

⚠ **Each warning renders only when TRUE.** A healthy account gets one plain sentence; a warning on
every account is one nobody reads on the day it means something.

⚠ **`openAccount()` goes to `?account=` directly rather than clicking the heading**, so a check
about the CEILING does not also depend on the heading button's markup — a layout change reddening a
dozen checks that are not about layout is most of how this file came to be red.

⚠ **`?tab=accounts` is IGNORED by the page and every one of these checks navigated to it**, landing
on the default view and failing on a control one click away. **A URL parameter nothing reads is
indistinguishable from one that works.**

### 🔴 …and the REST of the red was ELEVEN more live defects, not a pile of removed widgets (2026-09-06)

The 37 still red named the RAIL, the drag-and-drop, the Move menu, the tab chips and a fleet
summary — all genuinely removed. **The rules inside them were not, and asking that question one
check at a time is what found these.** Every one was on the page before anybody touched a test.

| the check named | what was actually broken |
|---|---|
| a running bot cannot be DRAGGED / MOVED | the drawer's account selector had **no running guard at all**. It reads its account at startup, so the write cannot reach the process — the page would show it under the new account while it traded the old one. The server 409s it; the page offered the control anyway |
| an unassignable account is listed DISABLED | every account was offered as an ordinary enabled choice. The write is committed, pushed and pulled before failing at `connect()` with a message about **credentials**, which points the reader at the password rather than at the missing terminal |
| the Move menu lists every account | the destinations were read off the GROUPING, which is derived from the instance configs — **so a registered account no bot was on yet was not offered**, which is the exact gap the registry query exists to close, re-opened |
| the Accounts tab renders while the snapshot loads | a row WAS the snapshot row and was dropped when the snapshot lacked it, so **while the trading box was unreachable this page showed no accounts at all** |
| an unanswered snapshot reads as unknown | the dot was `running ? green : red`, so a bot nobody had asked about drew *stopped* — **and the row handed it a START button**, which is the one mistake there that costs money |
| a benched bot is not the unreadable one | the no-account list came off the snapshot alone, so a bot whose config could not be PARSED sat under *trades nothing until you give it one* — an instruction that cannot fix a broken file |
| a password the VPS could not be asked about reads UNKNOWN | the chip was gone entirely, so all THREE answers rendered as nothing at all — which reads as *no problem here*. `has_password` is `boolean \| null` and the null branch is the whole point |
| an account with no terminal cannot be added to | the chip AND the guard both went, so the drawer offered Add bot on an account no terminal is logged into |
| an account nobody registered still says so | the *not registered* chip went with them, so this page silently had no broker, tier or symbol suffix for that account and nothing said why |
| a registered account with NO bots is one you can add to | the drawer rendered only for an account in the GROUPING, so **the one account that most needs Add bot could not be opened at all** — the registry's whole purpose, re-broken |
| adding a bot sends its key and the account | 🔴 **the picker was DEAD and looked like it worked.** `AddBotRow` does not write — it hands the chosen bot back through `onPick`, and the card that used to own it fired the move there. The drawer's `onPick` only closed the panel, so picking a bot dismissed the list and sent nothing. **The panel closing IS the feedback a successful pick gives**, so it was indistinguishable from a working control |
| an account a bot still trades cannot be unregistered | the guard survived; nothing could reach it, so it was never exercised |

⚠ **The version spec's three fleet-strip checks were the same shape.** `ConfigureTab()` is dead too
(only `VersionBanner` / `RuntimeEditor` / `ParamGroup` are imported from it), so `DeployCard` and
the strip went with it — **and with them the three warnings that say the banner's headline is
FALSE**: restart pending, snapshot modified, and settings changed since deploy. A bot promoted and
never restarted showed a green *up to date* over a process still trading the old code. All four are
in the banner now, derived from `versionFlags` and never re-derived.

⚠ **Six checks were DELETED, each with its reason left where it stood** — the rail's layout, the two
panes' matched height, the tab count chips, the `Stacked · 2` chip twice, and a fleet count that
navigated to the bot it counted. 🔴 **One had already gone VACUOUS rather than redundant**: it
asserted a count of ZERO for two testids nothing renders, so it passed against any page at all. **A
test whose subject no longer exists does not fail — it goes quietly green and reads as coverage.**

⚠ **The rule: never delete a red check as rot without asking what it was PROTECTING.** Of the 44,
eleven reported a live loss and six were genuinely removed layout. That ratio is the whole argument.

✅ **59 of 59 green, and non-vacuity is by MUTATION — eleven RUN, each red on its own named check**
(the running guard, the disabled option, the registry destinations, the snapshot gate, the row's
third state, the bench/unreadable split, the dead Add bot picker, the drawer's grouping
requirement, both banner warnings, and the served share total). ⚠ **Each mutation gets its OWN
shell call**: restoring and re-mutating in one leaves Vite serving the previous module, and a
mutation that silently no-ops looks exactly like a test doing its job — recorded here once already.
🔴 **And `git checkout -- <file>` is NOT a mutation restore.** It reverts to HEAD, which wipes every
uncommitted fix in that file alongside the one-line mutation; it did exactly that here and the work
had to be rewritten. **Restore by replacing the mutated string back.**

🔴 **One check failed against a page that was behaving perfectly, and the locator was the bug:**
`getByTitle('Start')` is a CASE-INSENSITIVE SUBSTRING by default, so it matched the uptime cell's
own *"how long it has been running without a re**start**"*. **A locator loose enough to match its
own neighbours reports the opposite of the truth** — the mirror image of the vacuous-locator trap
this file records six times. `{ exact: true }`.

### Two tabs, live and demo split, and scored against each other (2026-09-10)

Aaron: *"when I click on this page… I just only wanna focus on the accounts that have bots on them.
If an account has no bots on them, then I don't care"*, and *"I want live and demo split… easily
identify the winner."*

- 🔴 **TWO TABS: *Trading* (the default) holds only accounts with a bot on them; *Unassigned* holds
  accounts with no bot and bots on no account.** The one scroll mixed all three and read as
  scattered. ⚠ **Not the tab mistake above** — those tabs showed the SAME objects several ways;
  these hold DISJOINT sets. ⚠ **An unreadable config stays on Trading**: a fault may not sit behind
  a tab, and nothing says that bot is not running. ⚠ In the URL (`?show=unassigned`).
- **On Trading, accounts sit under *Live* then *Demo*.** (*Live · real money* until 2026-09-12 —
  Aaron: *"we know it is live"*; the words guarding real money are on the controls that spend it,
  and the switches check fails if they come back to the heading.) ⚠ An account whose type is still
  being asked waits under a shimmering heading, never under "neither", or it jumps on arrival.
- 🔴 **ONE colour per kind — amber live, cyan demo** (`KIND_TINT`): the switches, the headings and
  the chips on the Unassigned list. ⚠ Never green or red — those mean P&L here. ⚠ A kind nobody
  stated stays grey.
- 🔴 **Live and Demo are two SWITCHES, both on at first; each turns its own side off, and the last
  one on stays on** (*"both look selected by default but they are not"*, then *"I should be able to
  turn on both live and demo at the same time"*). On is filled in the colour, off is grey with its
  dot coloured, so a pill looks exactly as on as it is. ⚠ It was a pick-one filter where no pill
  pressed meant both. ⚠ `?kind=` still holds one of three states (absent = both), so nothing
  downstream moved.
- 🔴 **Nothing on the page says a fact twice** (*"we don't need to be redundant on data anywhere on
  this page"*): no live/demo chip on a card (its heading says it), no up/down edge colour (the net
  figure carries the sign), no "no bots" tag under *Accounts with no bots*, and the bot panel keeps
  only won/lost and the record's dates — its dollars, % of the account, trade count and R are all on
  the row. ⚠ **A figure DERIVED from the rows is withheld when it can only restate one of them; an
  independent MEASUREMENT stays even when it agrees** — the account's net and a lone bot's P&L are
  two readings, and their agreement is what keeps the *Not from these bots* line away.
- 🔴 **The winner is judged in R PER TRADE — never dollars, share of the account, or total R.** A
  live account is smaller, runs lower risk and started later than the demo beside it, so each of
  those three crowns demo by default. MEASURED the day it landed: the two demo bots read $1,305.58
  against $1,197.09 — near a tie — and +2.10R against +0.46R a trade.
- 🔴 **The side ahead reads *Leading* on its heading, and a side's POOLED score sits there only when
  it pools two or more scored bots** — a pool of one is that bot's own row. It was a pair of tiles
  above the page and they went the same day (*"what is the purpose of this section? If I select
  demo only then it goes away"*): a comparison block has to vanish under a filter. ⚠ **Scored off
  EVERY account, never the filtered ones**, so a filter never changes a side's number or who leads.
- 🔴 **One value per cell: P&L | Return % | Trades | Per trade** (*"I don't want anything stacked
  on top of each other"*). Stacked, the % under the dollars and the R read as one thing; they are
  not — Return % is the bot's dollars over the account's opening balance, and R per trade has no
  account size in it. The best bot holds the ONE trophy. ⚠ **Different icons on purpose** — the
  best bot can sit on the side that is behind. ⚠ A record with no closed trade reads `$0.00` and
  `0`; a missing record reads `no record yet` and dashes. 🔴 **Every column has a FIXED floor —
  never `auto` — and the actions a fixed width**: each row is its own grid, and a content-sized
  actions column put every value ~50px left of its heading on a 1280px screen. ⚠ **The spare width
  is SHARED (`minmax(floor, Nfr)`, 2026-09-13)**, never parked in one blank track — that left P&L to
  Version crowded at their floors (*"the columns 3-8 are all crowded"*).
- ⚠ **Nothing is awarded without a contest**: a side with no closed trade is not "behind" (a
  default is not a result), a lone scored bot gets no trophy, a tie within 0.005R gets neither, and
  a side missing a bot's record is PARTIAL and cannot lead. ⚠ **Summed from the bots' own records,
  never the account's growth.** ⚠ **The trade count is the caveat, beside the number, never a reason
  to hide it** (root `CLAUDE.md` → Trading Philosophy).

Tests: `tests/bots-accounts.spec.ts` (12 checks; the fixture gives demo more dollars AND more total
R while live wins per trade, and lists the demo spare before the live one, so every wrong rule goes
red); **47 mutations run across three passes, 47 killed**, each confirmed served by the dev server
before its check. 🔴 **One first SURVIVED: a check matched the text "R a trade", but the number and
the words are separate spans, so the page's text reads "+1.48Ra trade" and the match could never
fail.** It asserts the pooled block's own testid now, with demo's block as the positive control.

## Copying a stress test's settings onto a bot — the list IS the change (2026-09-06)

`components/SettingsImportModal.tsx`, opened from a FINISHED stress test's header, driven by
`useSettingsImportPreview` / `useApplySettingsImport`. Backend rules and the refusals:
`../backend/CLAUDE.md` → *A stress test's settings can be copied onto a DEMO bot*.

🔴 **NOTHING IN THIS COMPONENT DECIDES ANYTHING.** The change list, the warnings, the dropped
settings and the refusal all arrive from the backend, which builds them ONCE and returns the same
shape to both verbs. **Do not sort, filter, re-label or re-derive** — a browser-side list beside a
server-side one is two answers about a live bot, and only one of them was approved. Same rule the
risk-share total is under one section up, and that one had already drifted.

⚠ **The preview query is `staleTime: 0, gcTime: 0`.** It describes a LIVE bot's current settings,
and a cached preview is a list that no longer matches what an apply would write — the one thing
this flow exists to prevent.

⚠ **A LIVE bot is listed and DISABLED with the reason on it, never hidden.** A bot that vanishes
from a picker reads as a bug, and the reader needs to see that demo→live is a stage rather than
wonder where their bot went.

⚠ **The Apply button reflects the PLAN** (`!blocked && changes.length > 0`), never a guess made
here. A button whose only outcome is an error toast is the defect this folder records twice.

⚠ **`show()` renders `null`/absent as `not set`, never as `Off`.** A setting the bot does not state
is a different fact from one it states as off, and this is the panel where that distinction decides
whether somebody presses the button.

⚠ **The apply hook has NO `onError` toast** — `api.request` already surfaces the server's own
`detail`, which carries the reason (running bot, live bot). A second generic toast buries it.

⚠ **`applied: false` on a 200 is a real outcome, not a failure** — the bot already matched — and it
is toasted as such rather than as a success that wrote something.

⚠ **The button renders only on `status === 'complete'`.** A running test's settings are the same,
but a control that appears mid-run invites copying a result nobody has read. **Grade is NOT a
gate** — the backend warns on a weak or absent one and still allows it.

⚠ **NO automated check.** Playwright is out of the gate by design and this needs the app and the
backend up. The behaviour is pinned backend-side by 27 tests and 20 killed mutations; what is
unverified here is the rendering.

## The account header — a stat cluster instead of a boring row (2026-09-14)

Aaron: *"I feel like when I look at it, it's just kinda boring"* — the header was one flat baseline
row (account number, nickname, cap pill, then balance and net mashed together at the far edge) with
nothing saying what any of the two numbers on the right were.

- 🔴 **Split into two clusters.** An identity cluster (account number, nickname) that can wrap onto
  its own line at a narrow width, and a right-aligned stat cluster that cannot be mistaken for plain
  text: each figure gets a small uppercase label above it (`StatLabel`, the same "word over a
  number" grammar `ColumnHeadings` already teaches two inches below), divided by hairlines.
- **Added an average return across the bots on the account** (`AvgBotReturn`) — the MEAN of each
  current bot's own Return %, never their sum (root CLAUDE.md's "never sum a number across bots
  that share it" — a mean is a different, legitimate question). Counts only bots on the account now
  (`former` excluded) that have actually closed a trade; `null` renders a dash. ⚠ **Only rendered
  once there are 2+ bots on the account** — with one bot the mean is the exact figure the Return %
  column already states for that bot, and a second label on the same number is the duplication this
  page keeps getting rebuilt to remove. It returns the moment a second bot lands.
- 🔴 **The risk-cap chip split by WHETHER IT IS A FAULT, not just moved (2026-09-14, Aaron: *"the
  10% cap feels out of place"*).** A pill is an alarm shape — border, background, uppercase — and a
  disagreement or an unset ceiling stays exactly that, beside the account name where the account's
  own faults live. A cap that is simply SET has nothing to warn about, so that case left the
  identity row and became one more calm gold figure in the stat cluster. Moving the whole chip in
  either direction would have been wrong: keeping the alarm shape for the common case is noise,
  and quieting the fault states into the stat row would bury the one condition here that stops
  every bot on the account from starting.
  ⚠ **Never both** — the stat-cluster Cap figure is gated on `!idle && group.cap_agrees && cap != null`,
  the exact complement of the pill's own condition, so an account can never show a calm cap number
  and a fault pill at the same time.
- **Order is Cap → Return → Avg / bot → Equity, Equity rightmost** (Aaron's call, 2026-09-14) — the
  outer edge is where a row of figures conventionally puts its headline number, and equity is the
  one every other figure here is read against.
- **The settings-icon button went back to icon-only** (`IconBtn` gained an optional `testId` prop so
  `data-testid="configure-bot"` survives the change) in both places it appears — the account card's
  bot rows and the Unassigned tab's rows. ⚠ **Read the comment on it before re-adding the word**: it
  carried the word since 2026-09-06 because Aaron lost the control twice when it was icon-only and
  asked for it back in words both times. Reverted anyway on his direct 2026-09-14 instruction, made
  knowing that history — if it goes missing a third time, that is the failure to have checked first.
- `BotsPageSkeleton` mirrors the new header (including the Cap slot, shimmering the common
  set-and-agreed case rather than the rare fault pill) so the swap from skeleton to a real card does
  not move a pixel.
- Tests: all 132 `bots-accounts.spec.ts` + 36 `bots-version.spec.ts` pass unchanged (the tests target
  `data-testid`s, not button text or DOM shape) — verified visually with four temporary Playwright
  screenshots (two-bot accounts, a 1280px width, a single-bot account, and a cap-disagreement
  account) that were removed before commit, never landed as fixtures.
- 🔴 **FOUR FIXED-WIDTH SLOTS, ALWAYS DRAWN, EVEN WHEN THE FIGURE DOESN'T APPLY (2026-09-15, Aaron:
  *"the header values have to line up identical vertically between the demo and live account"*).**
  Letting Cap or Avg / bot disappear when an account had no cap, or fewer than two bots, was the
  defect: whichever card was missing a slot drew one fewer column, and everything after it landed
  under the wrong header on the card beside it. Cap and Avg / bot now always render their label and
  a fixed-width box (`52px` / `82px`; Return `148px`; Equity `min-w-[118px]`, since its rare
  "read at HH:MM" annotation needs room to grow past the common case without shrinking anything to
  its left) — when the figure doesn't apply the box holds a dash, titled with why (no bot on the
  account, a cap disagreement, only one bot), the same "nothing to measure" mark the rest of the
  page already uses, never a narrower column. Verified with a throwaway fixture pairing a normal
  two-bot account against a one-bot, no-cap account side by side — all four labels landed on the
  same pixel between the two cards.
  🔴 **That fixture did not cover the one pairing that actually broke — see the next entry
  (2026-09-15).** Equity is the LAST slot in a cluster anchored by `ml-auto`; growing it has
  nowhere to expand INTO, so it pushes the whole cluster's left edge, and everything before it,
  further left instead of "growing past the common case without shrinking anything to its left."
  The fixture never paired a live balance against a past-reading one, which is the one pairing
  where Equity actually grows past 118px.

## The equity is what MT5 gave — a figure, its read time, or a dash (2026-09-14)

Aaron: *"read exactly what's on the MT5. Don't create your own phrases."* The live card said
`balance unread` in amber over two bots that had refused to start on an account MT5 reported as
$0.00, and the account panel said `not reported — no bot here is answering`.

- **No reading → `—`**, on the card and in the panel — on the card the same small grey dash the
  header's other three slots hold. `balance unread`, `balance not read` and `not reported…` are gone.
- 🔴 **A STOPPED bot's figure carries its read time** (`last_updated`) — it is what MT5 said then, and
  shown as current it would read $0.00 on an account funded since. A running bot's reading wins;
  else the newest a stopped one took. The time sits UNDER the figure, and on an account with no bot
  only in the hover — see *The Equity slot's real fix* below, which landed alongside.
- **The header's `N balances unread` count is gone.** A bot that cannot read MT5 says so on its own
  row (`No MT5 link`) and the card shows a dash — the count was a third copy nobody could act on.
- The equity figure carries `data-testid="account-equity"`.

Test: *an account shows only what MT5 gave* in `tests/bots-accounts.spec.ts`. Two mutations — a
stopped reading shown as live, the phrase back — each went red. The panel test's expected sentence
moved with the panel's wording.

## The bot panel: one action row, Remove instead of Take off, issues that stand out (2026-09-14)

Three of Aaron's asks the same day, all touching the same panel, so they land together.

- 🔴 **"Take off" is "Remove" everywhere** — the button, its tooltips, and the account-panel row's
  control (`TakeOffButton`, shared by both). The word predates the account panel gaining the same
  control (2026-09-13); once both panels said it, "take off" read as jargon "remove" does not.
- 🔴 **Every action on the bot panel is now ONE ROW** (Aaron: *"figure out all the action buttons
  should be together … it just seems a little bit all over the place"*). Start / Stop / Restart on
  the left; Logs, Move, and Remove — each previously stranded in its own section — grouped on the
  right. The Account section below is now INFORMATION ONLY: which account, its name, the link to
  open it; the paragraph explaining what a move or a removal does to a running bot stays put.
- 🔴 **Move is now a labelled button, not a select that shows the CURRENT account** (Aaron: *"I
  don't understand what that dropdown is for … maybe that should be like a move button"*). It
  always reads "Move to…" (or "Put on account…" with none), never the account it is already on, so
  picking an option is the only thing the control can mean. Same destinations, same plan fetch —
  only the trigger changed.
- 🔴 **A live issue is tinted and full-bleed, not plain text** (Aaron: *"the issues should stand out
  a little bit more"*) — red for a `bad`-toned issue, amber for `warn`, following the same tone
  `botCondition` already assigned rather than inventing a new one.
- Also fixes a gap left by the VPS sync drawer redesign above: that commit shipped the drawer's new
  "Your list now matches N accounts the scan could check" wording but not the test asserting the
  old text, so `bots-accounts.spec.ts` was red on `main` between that commit and this one.
- Tests: all 132 `bots-accounts.spec.ts` pass, five re-pointed to "Remove" (two test names, three
  in-body assertions); tsc --noEmit clean.

## The Equity slot's real fix, and an explicit "no bot" status (2026-09-15)

Aaron, from a screenshot of the account he had just promoted off demo: *"it added some new values
which have them misaligned now"* and *"why is it still here"* (the demo account, with its bots
just moved to live).

- 🔴 **The Equity slot was never actually a fixed width — it was `min-w`, the one exception to
  "FOUR FIXED-WIDTH SLOTS, ALWAYS" two entries up, and the one case that broke it.** A past-reading
  balance appends "read `<time>`" BESIDE the figure, on one line — wider than any plain balance —
  and a `min-w` box grows to fit it. Because the whole cluster hangs off `ml-auto`, growing the
  LAST slot pushes every slot before it (Cap, Return, Avg / bot) left with it. That is exactly what
  happened the moment Aaron's two bots left the PU Prime demo account for the live one beside it:
  its header drew a full column short of the live card's. Measured in a real browser
  (`getBoundingClientRect` on both cards' `Cap`/`Return`/`Avg / bot`/`Equity` labels): before the
  fix the demo card's three left labels sat 105px left of the live cards'; after, all three cards'
  four labels land at the same x on screen.
- **Fix is the stat, not the box.** The "read `<time>`" note now sits UNDER the balance instead of
  beside it, so the slot's content is the WIDER of the two lines, not their sum — 118px (already
  enough for either line alone) holds, and `min-w-[118px]` became a true `w-[118px]`, matching its
  three neighbours. `balance-read-at` is unchanged for the case that still needs it on screen (a
  bot IS on the account, has just not reported a balance of its own yet — nothing else on the card
  says that figure is stale, so the time stays visible there).
- 🔴 **Added an explicit status pill for an idle account** (`idle-chip`, Aaron: *"we need some kind
  of indicator showing that there's no bots on it right now"*) — grey, not warn/gold, since an idle
  account (a demo a set was just promoted off) is a normal resting state, not a fault like the cap
  pills beside it. It sits in the same identity-line slot the cap chip leaves empty while idle.
- 🔴 **Removed the departed-bots' per-bot rows from the card** ("Moved to live account…", each
  bot's own P&L / return / trades / per-trade — Aaron: *"the history of the bots don't really need
  to be there… I don't care where the bots will move to"*). Once the idle pill says the one fact
  that matters at a glance, the per-bot destination detail was never that.
  ⚠ **The account's own equity and return above are untouched** — they read the whole account
  record, not this list. ⚠ **The departed bots' share of the SIDE's pooled score is untouched
  too** (`scoreOf` folds `former` bots in on purpose) — that is a different reader (the DEMO/LIVE
  section heading), never this list. ⚠ **A returning bot still carries the score forward**
  (`carried_from`) — also unrelated to this list, already covered by its own test.
  ⚠ **The account still shows on Trading rather than dropping to Unassigned once its bots
  leave** — that is the 2026-09-11 decision above, not revisited today. Aaron asked "why is it
  still here" against that same decision; today's change is what he asked for once he saw the
  trade-off spelled out — keep the card, drop the per-bot clutter, add the pill.
- Tests: `bots-accounts.spec.ts` — two tests rewritten (`idle-chip` visible + `balance-read-at`
  and `past-row` both absent on an idle account; the new-bot-returns test now asserts `past-row`
  count 0 instead of 2, since the rows are gone, while `score-demo` still reads `+1.00R`
  unchanged). All 132 pass. tsc --noEmit clean on this file. Verified visually in a real browser
  against the live dev server (live + demo accounts side by side, one idle).

## Every strategy is a standing placeholder — "Add a bot" offers ALL of them, forever (2026-09-14)

Aaron: *"I could have infinite amount of demo or live accounts and I want my bots on all."* The
2026-09-11 redesign above (**"Add a bot" lists FREE bots only**) was right as far as it went, but
it had a ceiling nobody had hit yet: once both of a strategy's copies were on real accounts — one
live, one demo — there was nothing free left to offer a third account, ever, for that strategy.
The only route past it was a person hand-editing a new instance file on the VPS.

- **A row is now the STRATEGY, never a specific running copy, and it is never used up by being
  placed.** `lib/botTemplates.ts` derives one row per strategy from data the page already holds —
  `useBotAccounts` (every bot, grouped by account) and `useRegisteredAccounts` (which account is
  demo or live) — so the list needed no new fetch of its own. Picking the row either hands over a
  real idle copy that happens to be sitting free (`existingBenchKey`, the ordinary case for a
  strategy nobody has placed anywhere yet) or clones one first (`useCloneBot`, `POST
  /bots/{key}/clone`) with no separate step the reader ever sees — the clone is invisible on
  success, and cancelling a live confirmation after one leaves at most one idle spare bot behind,
  the same harmless resting state benching a real bot already produces.
- 🔴 **Which bot to clone from is picked HERE, client-side, not by the backend.** A strategy's live
  copy outranks its demo copy, which outranks a benched one — "its live share" is the most current,
  most deliberately tuned configuration, and a demo copy sometimes trials a change the live bot has
  not taken yet. The backend endpoint needed no template concept of its own because of this: it
  clones exactly the bot key it is called on.
- ⚠ **A strategy already on the account being viewed is not offered again.** This panel fills a
  gap; it does not suggest piling a second copy of one strategy onto a balance that already runs
  it. The empty state now says which of two different things is true — "no strategy is built yet"
  (nothing exists anywhere) versus "every strategy is already on this account" (they exist, this
  account just has them all) — collapsing those into one "no bot is free" message would have hidden
  which is true.
- ⚠ **Only a real, already-idle bot gets the server's full room-fit plan** (`useJoinPlans`, and
  every fix `JoinChoices` can offer — raising the cap, rescaling every share). A strategy with
  nothing idle yet has no bot key for the server to plan a join for, so it gets the one fix
  computable from what the panel already knows — join at the room still free (`SimpleMakeRoom`).
  Raising the cap or rescaling every bot is still a click away on the account's own risk budget;
  it is not invented here for a bot that does not exist yet.
- Tests: `bots-accounts.spec.ts` — the two 2026-09-11 checks this superseded (`add-extreme` count
  0 once elsewhere; "No bot is free") are replaced with four: a bench bot's row is still named by
  its risk and never its symbol; a strategy with no free copy is still offered and placing it
  clones its running bot (asserts the clone call fires, then the ordinary account move, in order);
  an account already running every known strategy says so by name; a strategy not yet on that
  account is still offered even once every other one is. All 134 pass. tsc --noEmit and eslint
  clean on every changed file.

## Accounts are a RAIL + DETAIL, and one per kind can be PINNED open (2026-09-15)

Every account on Trading rendered its full bot table, always open. That reads fine at two or three
accounts; it stops being a list and starts being a wall the moment the fleet grows past a handful —
the exact growth this whole page keeps getting rebuilt to survive (*one list, one drawer, no tabs*,
above).

🔴 **A fold/unfold accordion shipped first, same day, and was replaced before it was ever
committed.** Aaron reviewed three layout mockups (built outside this codebase) and picked
**rail + detail** over the accordion — a compact line per account on the left, full content for
every OPEN account stacked on the right. Nothing about the accordion's rendering survives below;
where it matters, this entry says what replaced it rather than describing code that is gone.

- 🔴 **The RAIL** (`renderRailRow`, `w-[248px]` — reusing the width of this app's one other
  rail+detail precedent, the deleted `AccountsTab.tsx`'s own rail, matched from git history since
  Aaron asked this to look like that one rather than invent a third rail idiom in the same app).
  One compact line per account: the pin star, the worst-status marker, the account's identity
  (number leads, nickname else broker — unchanged rule), one headline figure, and the open/closed
  state itself as the row's own highlight (`bg-accent-muted border-accent/30` open, matching this
  app's own colour rule that accent marks the thing selected). Clicking a row toggles that account
  in the shared open set; **not single-select** — any number from zero to all can be open at once.
  ⚠ **Long nicknames truncate in the rail** (`PU Prime ECN demo` → `PU Prime EC…` at 248px) — the
  account NUMBER stays whole either way and is this app's own tie-breaker when a name and a number
  would otherwise disagree, so a truncated name never costs identification. The historical rail
  this width came from truncated names the same way; it is the accepted shape for a compact list,
  not a defect introduced here.
- **The headline figure is Return %, not Equity** — one number, never both crammed into a ~230px
  row (the detail panel beside it states the same figure in full, plus the other three stats; that
  is a preview and a detail view of the SAME fact, not two different facts). `AccountNet` grew a
  `compact` prop for this rather than forking a second component — hide the dollar span, keep the
  `title` (the full sentence, including what it is measured from, is one hover away either way).
- 🔴 **THE DETAIL COLUMN holds every account currently OPEN, stacked in RAIL ORDER** — Live
  section's pinned-first order, then Demo's — **never click order**, so toggling one account never
  reshuffles a panel that is already open. Each panel (`renderDetailPanel`, `account-detail`) is
  the account's full content unchanged from the old card: the identity + stat cluster header (Cap
  / Return / Avg per bot / Equity, the idle/cap-disagreement chip), the bot table, Configure
  access, and the Unattributed line. **No worst-status marker here** — the rail states it once;
  drawing it again in the open panel would be the exact duplication this page keeps getting
  rebuilt to remove. **No pin here either** — it moved into the rail row, one control, not a copy
  in every open panel.
- **Nothing open → an `EmptyState`** ("No account open — Pick one or more accounts on the left…"),
  this app's existing component rather than a hand-rolled placeholder. In practice this is rare:
  the default (below) guarantees something is open the moment there is anything to show, so it is
  only ever seen after a reader has deliberately closed every account they had open.
- 🔴 **`prepareAccountView` computes an account's cap, balance, bot rows and worst condition
  ONCE**, read by both the rail row and its detail panel, so the two surfaces can never disagree
  about what an account IS — only about how much of it is currently on screen. Both are keyed off
  the same `accountKey`, and `accountViews` (a `Map`) holds one entry per account for the whole
  render pass rather than recomputing per surface.
- **The open/selected state itself is UNCHANGED and layout-agnostic** — `expandedAccounts` (a
  `Set<string>`), `toggleAccount`, and the default-expand effect (`defaultExpandKeys` /
  `defaultExpandSignature`, frozen forever once `userTouchedExpand` flips) all carry over exactly
  as they were. That effect took two rounds to get right — it recomputes off whatever Live/Demo
  classification is currently best-available (including the provisional `pending` bucket before
  the box or the registry has answered) so something is always open from the very first paint, and
  freezes the moment a reader touches a toggle so a later refetch or pin write can never silently
  override a manual choice. A real regression shipped here once, on the accordion's watch: an
  earlier version of this same effect fired only once and waited for the box to answer first,
  which left every account collapsed with nothing on screen for as long as the VPS was slow or
  down — `bots-accounts.spec.ts` caught it the same day (`the accounts render while the VPS
  snapshot is still unanswered`, `a bot the box has not answered for reads UNKNOWN, never
  stopped`). The fix (recompute continuously, stop forever on the first manual touch) is what
  ships now, under either rendering — this page's rule-1 lesson one layer up from where it usually
  bites: not a bot's STATUS value, but the ROW ITSELF staying visible while nobody has answered yet.
- 🔴 **One pin per demo/live KIND, never a free ranking — the backend's rule, this page just draws
  it.** `PATCH /bots/accounts/{account}/pin` states what ONE account should now be; setting one
  un-pins whatever else of the same kind held it, entirely server-side, so the page never counts or
  reconciles pins itself (the same discipline as the risk-share total three sections up). A pin
  never crosses Live and Demo — `withPinnedFirst` reorders each section independently and the two
  sections are never merged before it runs. The pinned account is also the one the default-expand
  effect opens, since it reads the same pinned-first list the rail renders.
- ⚠ **The pin is a ★, gold only while held** (root CLAUDE.md's colour rule: gold is for ★ markers
  and limits). `bench`/`unknown` kind groups and the client-synthesized `emptyGroup` (an account
  with no bots on `/bots/accounts` at all) report `pinned: false` and are never reordered — there is
  no account number for a pin to mean anything about.
- ⚠ **The rail costs the detail table real width, and one test's threshold moved to say so
  honestly.** A persistent 248px rail sits beside the detail column at every viewport now, which
  the table never had to share room with in the full-width accordion. MEASURED at 1600px: the
  P&L column (96px floor) renders 102.86px — real sharing still happens (Aaron's original "give
  the columns some space" fix is intact), just against a smaller pool than a single full-width
  card ever had. `bots-accounts.spec.ts`'s width check moved its bar from 110px to 100px with the
  measurement and the reason written beside it, rather than describing a page width this layout no
  longer has.
- 🔴 **The pin itself had three rounds of live-testing against the real backend and ZERO automated
  coverage until this line** — a gap named directly (a feature nobody has watched fail for the
  right reason is not proven, this repo's own rule 12) rather than left standing because the manual
  checks all happened to pass. Four new tests, fixtured with `mock()`/`group()`/`reg()` exactly
  like every other check in this file — never against the live server: a pinned account leads its
  section over a lower-numbered unpinned one (watched red with `withPinnedFirst` neutered to a
  no-op, so the fixture/array order won instead); the pinned account is the one open by default,
  untouched (same mutation, same red); pinning is scoped to its own demo/live KIND — a live pin
  cannot reorder or open the demo side or the reverse (four accounts, two per side, the pinned one
  on each side deliberately listed second and numbered higher so a cross-side leak or an
  array-order fallback would both show); and clicking the pin star sends the account and the
  OPPOSITE of its current state (fixture starts PINNED specifically, so a hardcoded `pinned: true`
  click handler — which would pass by coincidence against an unpinned fixture — is caught; watched
  red with the click wired to send `true` unconditionally).
- Verified: `tsc --noEmit`, `npm run build`, and eslint all clean. `npx playwright test
  tests/bots-accounts.spec.ts` (138/138) and `tests/bots-version.spec.ts` (36/36) — every test in
  the first file that touched the Trading tab's account rendering was watched red against the new
  DOM (missing `account-card`/`account-toggle`, or a locator now finding TWO matches because the
  same fact legitimately renders twice — once compact in the rail, once in full in the detail
  panel) before being re-pointed to `account-rail-row` / `account-detail`, scoped to whichever one
  actually holds what each test protects. A full unscoped `npx playwright test` (all 381, every
  project — file-scoping earlier is exactly what let the rule-1 regression above slip past a
  narrower run) comes back with only the same pre-existing, unrelated failures already confirmed
  by `git stash`-ing this pass's files and re-running against bare `main`
  (`backtests.spec.ts`, `overview.spec.ts` ×2, `strategies.spec.ts` flaked once and passed clean on
  a rerun, `tuning.spec.ts`) — none in `bots-accounts`/`bots-version`.
  Live-tested against the real backend in a real browser throughout: the rail renders and its
  worst-status marker shows before the VPS answers, pinning moves an account to the top of its
  section and opens it by default on reload, multiple accounts open and close independently in
  rail order, the empty state appears once every account is closed by hand, and Configure still
  reaches the same account settings panel it always did.

### The rail, actually looked at (2026-09-15, second pass)

The rail+detail decision above was verified by code and tests alone, and it shipped looking rough
— Aaron on the running page: row heights inconsistent, Live and Demo blending together, the side's
own score line reading as one account's number, and a rail that stops wherever the list ends
rather than looking like a sidebar. Four fixes, all visual, none touching the rail+detail decision:

- 🔴 **The status marker is a DOT, never `StatusText`'s pill (the actual bug behind "different
  heights").** `StatusText` is built for a full-width card header — its word ("Stopped") plus a
  "+1" badge wrapped onto its own line in a ~230px row, so a troubled account's rail row was
  visibly taller than a healthy one's. A `w-[6px] h-[6px] rounded-full` dot can never wrap or grow
  a row; the same `bad`/`warn`-only restraint stays (a new `TONE_DOT` map beside `BotStatus.tsx`'s
  existing `PILL`/`TONE_TEXT`, same solid-fill convention this page already uses for a kind's own
  dot in `kind.tsx`), and the worst bot's own sentence is still one hover away via `title`. The
  full pill still draws in the detail panel, where there is room for it.
- **Live and Demo get real separation** — `divide-y` between the rail's sections plus a bigger
  gap either side of the line (26px), not just a small coloured dot and a label.
- 🔴 **The pooled score line moved to sit BESIDE its own section's label, not floating above the
  account list.** `SideScoreLine` sums a whole SIDE across every account on it — Aaron: *"this...
  for demo — live doesn't have that, so why does demo have it?"* — and with exactly one Demo
  account currently registered, the figure sitting on its own line right above that one row read
  as if it belonged to it. It is still the side's total (`scoreOf`, unchanged, still needs 2+
  scored bots to show a pooled figure) — this did not reopen "should this exist", only where it
  reads as attached: `SideSection`'s heading is one `flex-wrap` row again (dot, label, hint, then
  `aside`), so the score sits right after the label when there is room and wraps directly under it
  — never a line of its own further down — when there is not.
- **The rail is a real panel, stretched to the row's full height** — Aaron: *"have it show it's
  the height of the page."* The outer row is `items-stretch` with a `min-h-[420px]` floor (this
  app's own rail+detail precedent, the deleted `AccountsTab.tsx`'s shell, reused exactly) instead
  of `items-start`; the rail's own `bg-bg-surface border rounded-lg` panel then fills that stretched
  height. ⚠ **The flex item that stretches must NOT also carry an explicit height itself** — the
  first attempt put `h-full` on that item, which computes to `auto` against a container whose own
  height is merely min-height-bounded (not a definite value CSS percentage-resolution accepts),
  and an explicit-but-invalid height silently overrides the default `stretch` behaviour the same
  as a valid one would. MEASURED: with `h-full` on that item its rendered height was 250px against
  a 439px row; removing it (and leaving only `h-full` one level DOWN, on that item's own child,
  which now inherits a genuinely definite height from the stretch) fixed it to the full 420px.
- Verified the same way every other round should have been from the start: the dev server up,
  `/bots` loaded in a real browser, screenshots taken at both a normal width and a realistic narrow
  one (1024px, not a phone width this desktop ops tool was never built for) with a fixture carrying
  a halted bot specifically to see the dot. All four fixes confirmed by eye, not just by locator.
  `tsc --noEmit`, `npm run build`, eslint clean (one more pre-existing-shaped warning on the new
  `TONE_DOT` export, same as `TONE_TEXT` beside it — this file already trades fast-refresh purity
  for one shared tone vocabulary). `bots-accounts.spec.ts` + `bots-version.spec.ts` 172/172
  (unchanged from the pin-test pass — this round touched no test, only markup and classes) and a
  full unscoped `npx playwright test` with only the same pre-existing, unrelated failures.

### The rail, locked to an exact spec (2026-09-15, third pass)

The second pass above was still open-ended ("distinguish Live/Demo better", "make rows
consistent"). Aaron picked between real mockups over two more rounds and this pass is that exact,
now-locked design — it REPLACES the dot-plus-label heading and the one-line row above, not a tweak
on top of them.

- 🔴 **ONE bordered panel holds the whole rail — Live then Demo INSIDE it, not two panels.** The
  outer `bg-bg-surface border border-border-subtle rounded-lg` shell is unchanged (same element
  that already stretched full height in the second pass); what moved inside it is the `p-[8px]`
  wrapper and the per-section `gap-[26px] divide-y` spacing, both gone. Live and Demo now butt
  directly against each other with no gap of their own — the colour change between one group's
  last row and the next group's filled bar is the only separation, which is also why there is no
  hairline between groups: `divide-y` is scoped to each group's OWN row list, so it draws lines
  between rows within a group and never after the last one or before the first (see `RailGroupBar`
  usage in `index.tsx`). `pending` (still classifying) and `other` (kind nobody stated) are not
  real live/demo kinds, so they keep `SideSection`'s existing subtle dot-and-label heading with its
  own small inset — only Live and Demo get the treatment below.
- 🔴 **Live and Demo are FULL-WIDTH FILLED COLOUR BARS now, not a small dot-plus-label** — a new
  `RailGroupBar` component, used only for `key === 'live' || key === 'demo'`. Live is
  `bg-gold-muted` / `text-gold-text` / `bg-gold` dot; Demo keeps the page's usual
  `bg-accent-muted` / `text-accent-text` / `bg-accent` (cyan). ⚠ **Live's gold is a DELIBERATE,
  SCOPED exception to `KIND_TINT`** (`kind.tsx`, amber for live everywhere else — the filter pill,
  every chip, every badge) — this one bar is the mockup Aaron approved; `KIND_TINT` itself was not
  touched, and MEASURED via `getComputedStyle`: the bar's fill (`rgb(45,36,16)`) and its text
  (`rgb(231,191,107)`) are visibly distinct from the live filter pill's own amber fill
  (`rgba(255,179,0,.15)`) and text (`rgb(255,214,78)`) — a real second colour, not a same-value
  rename. The pooled side score (`SideScoreLine`, unchanged, still needs 2+ scored bots to draw a
  figure) folds INTO this same bar, right-aligned via `ml-auto` — MEASURED at 1440px: the score
  span's right edge sits 8px inside the bar's own right edge, same inset as the bar's own left
  padding, i.e. genuinely right-aligned rather than merely "on the right some of the time." A bar
  with nothing to score (fewer than 2 scored bots, or asking) still draws — the dot and the label
  are the group's name and are never conditional; only the number is.
  ⚠ **A test that used to assert the "Live" heading's colour equals the live filter pill's colour
  is now WRONG BY DESIGN** (`bots-accounts.spec.ts`, "live and demo are two switches..." — that
  coupling was true when both read off one `KIND_TINT`, and stopped being true the moment this
  bar's gold shipped) — rewritten to check what is actually still invariant: the pill is genuinely
  filled while on and reverts to a different, unfilled look once off, no longer anchored to the
  rail heading's own colour.
- 🔴 **Each rail row is now TWO LINES, laid out on a CSS grid** (`grid-cols-[auto_minmax(0,1fr)]`)
  so line 2 always lands under the NAME column, not a hand-guessed padding value that would drift
  every time the account number's digit count changed. Line 1: account number (bold mono, now
  13px/700 — bumped a full step, see below) then the name (12px/600, `text-text-primary` in both
  open and closed states — previously only brightened on open, which shrank the gap to line 2 in
  the more common closed state), pin star as a flex SIBLING of the row's toggle button (never
  nested — this file's own established rule) aligned to the row's TOP via `items-start` on the
  outer flex container, not centred across both lines. Line 2, in the same grid column as the
  name: return % (still `AccountNet` with `compact`, hiding only the dollar half), the account's
  own EQUITY (its real balance — `money(balance, false)`, the same figure the detail panel's own
  Equity stat shows — NOT the net dollar change `AccountNet` already states as a %, a different
  question), then the worst-status dot, unchanged from the second pass.
- 🔴 **Line 1 is the DOMINANT element, line 2 deliberately quieter — Aaron on the mockup, a
  correction on top of the two-line spec itself**: the return %/equity line at its original size
  (13px, the same weight the full stat-cluster uses) competed with the identity line instead of
  sitting under it. Fixed on both ends: line 1's number moved 12px→13px and semibold→bold, the name
  11px→12px and now always full-strength `text-text-primary` (was secondary/muted while closed);
  `AccountNet`'s own `compact` mode gained a real size drop (13px→11px) so the SAME component
  reads authoritative in the full stat cluster and quiet in the rail, off one prop rather than two
  copies of the return-% renderer. MEASURED via `getComputedStyle` at 1440px: line 1 is
  13px/700 + 12px/600 in `text-text-primary`; line 2 is 11px/600 (coloured, since sign is a
  finding) then 10.5px/400 in `text-text-tertiary` — a real, visible step down, not just a
  technically-different class.
  ⚠ **Line 2 sits LEFT-aligned under the name, not right or centred** — a second correction on the
  same mockup pass. The grid placement already put line 2's content in the name's own column; what
  needed checking was that nothing inside that column pushed right (no stray `ml-auto`/`justify-*`
  survived from the old one-line row's right-aligned net figure). MEASURED: line 1's name and line
  2's content share the exact same `getBoundingClientRect().x` (confirmed identical to sub-pixel
  precision on a real row), so the two lines' left edges genuinely align rather than only
  approximately lining up.
- Verified the same way as every pass before it: dev server up, `/bots` loaded in a real browser,
  screenshots at 1440px (normal desktop) and 1024px (the realistic narrow window this pass in the
  second round already established, not a phone width) with real account data, not a fixture —
  both groups' bars, the two-line rows, the divider-within-a-group-only rule, the full-height
  stretch and the left-aligned line 2 all confirmed by eye and by direct DOM measurement, not just
  by locator. `tsc --noEmit` clean, eslint clean (same one pre-existing warning as every prior
  pass, unrelated to this file's own changes), `npm run build` clean. `bots-accounts.spec.ts`
  (138/138, including all four pin tests from the previous pass) and `bots-version.spec.ts`
  (36/36) both green with one test's assertion rewritten (the live-heading-colour coupling above)
  and no other locator changes — every `data-testid` this round's markup rewrite depends on
  (`section-live`, `section-demo`, `account-rail-row`, `pin-account`) was kept exactly where the
  existing suite already expects it.

### The pooled side score is DELETED, not reskinned a fourth time (2026-09-15, fourth pass)

🔴 **Three strikes, same idea, three different shapes — removed rather than restyled again.**
A live-vs-demo comparison figure has now failed to justify itself to Aaron three separate times:

1. **2026-09-10, a pair of tiles above the page.** *"What is the purpose of this section? If I
   select demo only then it goes away."* Moved into each side's own section heading so it would
   survive a filter.
2. **One round later, on the section heading.** Live doesn't get one — *"why does demo have it…
   should it not be specific to the account."* Moved again, this time folded into the new
   `RailGroupBar` (the gold/accent bar built the same day), right-aligned on the bar's own row.
3. **2026-09-15, on the bar, hours after it shipped.** *"The plus one return a trade from 3 trades
   from two bots… I don't know what was the purpose of it, it looks kind of out of place and it
   does nothing for me to be honest."*

Three different homes, three different objections, the same underlying idea each time. That is a
signal the FEATURE is wrong, not that it has not yet found the right container — restyling it a
fourth time would be the same mistake with better CSS. **Deleted outright**, not hidden behind a
flag: `SideScoreLine`, `scoreOf`, `leadOf`, the `SideScore` interface, `liveScore`/`demoScore`/
`lead`, the `Leading` chip, and `RailGroupBar`'s `score`/`leading` props (it now takes only `kind`
and `label` — a dot and a name, nothing pooled or compared). `PerTrade`'s own trophy — which BOT
is best on R per trade, a different and unproblematic question — is untouched; that one has never
drawn an objection and this removal does not relitigate it.

⚠ **If anyone is tempted to re-add a live-vs-demo comparison figure here, read this section
first** — three different presentations of the same idea have each been read and rejected by the
person who has to look at this page every day. The rows underneath already state each bot's own
R-per-trade and trade count; that is apparently enough, and a pooled subtotal on top of it has
never once landed as useful.

Test fallout: the whole dedicated test block for the feature is gone (`score-live`/`score-demo`/
`side-pooled`/`leading` testids) — four tests deleted outright (the side-leads test, the
partial-score test, the filter-keeps-its-score test, and the score half of a fifth), one narrowed
to keep only its still-valid half (renamed **"no trophy is awarded until there is a contest"** —
the trophy assertion stayed, the "no side leads" assertions did not), and two more had a single
stray score assertion removed from an otherwise-still-valid test (the demo-trades-stay-on-demo
regression test, and the new-bot-replaces-the-idle-view test, retitled since "keeps the departed
bots in its score" is no longer a thing that happens). `bots-accounts.spec.ts` + `bots-version.spec.ts`: 169/169.

### The rail + detail area fills the real page, not a content-sized floor (2026-09-15, same pass)

Aaron, on the running page with nothing open: *"I want the accounts side panel to stretch the
entire height of the page"* and *"when there's no accounts open… just fill the whole page, this
cropping behaviour… I don't like it."* The `min-h-[420px]` floor from the second pass was a
**guessed number**, not a real answer to "how tall is the page" — it looked fine near 420–700px of
real content and left a visible gap under both the rail and the "No account open" placeholder on
anything taller.

- 🔴 **Root cause: the row's height was never tied to the viewport at all.** The app shell's
  `<main>` (`App.tsx`) is the actual scroll container, sized to `flex-1` inside a `h-screen` shell
  — a genuinely DEFINITE height. But the Bots page's own root was a plain `<div>` (ordinary block
  flow), so nothing below it had any relationship to that height; the rail+detail row's only
  height signal was its own `min-h-[420px]`, a content-based constant with no idea how tall the
  browser window actually is.
- Fix, three levels, each chained off the one before: the page root is now `min-h-full flex
  flex-col` (NOT a hard `h-full`, see the CSS trap below); the Trading tab's own top-level wrapper
  is `flex-1 min-h-0` inside that column, so it claims whatever height the header and tab strip
  above it do not use; the rail+detail row itself is `flex-1 min-h-0` in place of `min-h-[420px]`,
  so it is genuinely "whatever is left of the viewport" rather than a guess.
- 🔴 **`min-h-full`, not `h-full`, on the page root — a deliberate difference from the coordinator's
  own suggested wording, and the reason is safety.** This is the standard "sticky footer" flexbox
  pattern (`min-height:100%; display:flex; flex-direction:column` on the outer box, `flex:1` on the
  growing child): when real content — many accounts open, long bot tables — needs MORE height than
  the viewport, the column simply grows past `min-h-full` and `main`'s own `overflow-y-auto` scrolls
  the whole taller page, exactly like it already does everywhere else in this app. A hard `h-full`
  would have fixed the page root at exactly `main`'s content height regardless of content, risking
  either clipped content or a fragile reliance on how a browser scores overflow:visible content
  toward an ancestor's scrollable area. MEASURED at a squeezed 500px-tall viewport with three
  accounts open: `main.scrollHeight` (827px) exceeds `main.clientHeight` (444px) and the page
  scrolls — no clipping.
- 🔴 **The "No account open" empty state needed a second, separate fix — it does not get a tall box
  for free just because its flex parent is now tall.** `EmptyState` pads itself to a fixed height
  (`py-[90px]`) and has no idea how tall the panel around it is, so left alone it kept stopping
  wherever that padding ended even after the row itself grew — a shorter box next to the (now
  genuinely full-height) rail, the exact "cropping" complaint in a new spot. Fixed by making its
  wrapper `flex-1` (grow to the row's full height, same as the rail panel) plus its own `flex
  items-center justify-center` (centre `EmptyState`'s content inside that full height, rather than
  pinning it to the top with the extra space sitting empty below). MEASURED at 1440×900 with
  nothing open: both the rail panel and this wrapper's `getBoundingClientRect().bottom` land at
  exactly 878px — `main`'s own content-box bottom (900px viewport − 22px padding) — so neither
  panel undershoots the page by even a pixel.
- ⚠ **Individual account detail cards, when one or more IS open, are deliberately NOT stretched to
  fill any leftover space** — that was never part of what was asked (only the rail panel and the
  empty-state placeholder were named), and stretching a real data card to fill arbitrary empty
  space would look like a broken layout, not a feature. The space below a short stack of open
  account cards is just page background, same as before this pass.
- ⚠ **Re-read before touching this again**: a flex item that STRETCHES must never carry an
  explicit `height` itself (only `min-`/`flex-` sizing) — an explicit-but-unresolvable percentage
  height computes to `auto` and silently cancels the stretch, which is exactly what broke the rail
  in the second pass (documented above) and is why this pass's three new containers all use
  `min-h-full`/`flex-1`/`min-h-0` rather than `h-full` anywhere in the new chain. The rail panel's
  own long-standing `h-full` (on its INNER child only, per the second pass's fix) was left
  untouched and still works, now against an even more genuinely definite ancestor chain than before.
- Verified: dev server up, `/bots` loaded in a real browser, screenshot at 1440×900 with both
  accounts closed (Aaron's exact scenario) — no score line anywhere, both the rail and the empty
  state reach the same bottom edge with no visible gap. `tsc --noEmit` clean, eslint clean (the
  same one pre-existing warning), `npm run build` clean.

### The rail reads as a ledger, not a stack of cards (2026-09-15, fourth pass)

Aaron, on the running page: *"the account list design looks ugly in my opinion. Redesign it for
better UX."* No structural change — rail + detail stands, and so does every rule the passes above
settled (one fact once, no pooled score, no worst-status pill in the rail). This pass is about
where the COLOUR and the ALIGNMENT go inside the rail's own 248px column.

🔴 **Root cause of "ugly": the column had no quiet ground left in it.** A full-bleed filled bar
per group (gold for Live, accent for Demo) plus a fully filled `bg-accent-muted` row for every OPEN
account meant that with two groups and two accounts open, roughly every pixel of the rail was a
saturated fill. Nothing in a column like that can be emphasis, because emphasis is a difference
from a ground and there was no ground. It also mis-states importance: a group heading over one or
two rows is the LEAST important thing in the rail and was the loudest, while a fill that strong
reads as an alarm when all it means is "this one is showing on the right".

Three changes, each answering a specific defect:

- **The group heading recedes.** `RailGroupBar` is now a sticky header on `bg-bg-sunken` with a
  coloured dot, its label in its kind's text colour, and the number of accounts under it —
  the one figure a heading legitimately owns, since it counts its own rows rather than pooling
  anything the rows state (the three-times-rejected score is NOT coming back; see the section
  above). Gold still means Live here, so the scoped `KIND_TINT` exception documented in `kind.tsx`
  is unchanged. ⚠ Sunken, deliberately — a heading and an OPEN row may not share a surface, or
  "which account is open" stops being readable at a glance.
- **The open row rises instead of filling.** `bg-bg-surface-2` plus a 2px left edge in the
  ACCOUNT's own kind colour (gold for real money, accent for demo, off `reg.kind` — an unstated
  kind keeps accent rather than guessing live). The edge is an absolutely-positioned sibling, not a
  border, so opening an account never shifts its text sideways by 2px.
- **The figures got their own right-aligned column.** The row is a three-track grid: a fixed 9px
  status gutter, identity (number over name, one left edge), then return % over equity, both mono
  and tabular, right-aligned. They used to run inline after the name at two sizes, which is why a
  column of money read as wrapped prose — the thing anyone scans an account list FOR is the odd one
  out, and that needs a shared right edge to be visible at all. The status gutter is always there
  whether or not this account has a finding, so a row with a problem never shifts its number
  relative to a row without one (the marker rule itself is unchanged: only `bad`/`warn` draw a dot,
  and it is a dot, never the pill).

⚠ **The pin is revealed on hover/focus and keeps its box always.** A ★ outline in the corner of
every row was per-row noise in a 248px column; collapsing the box on hover instead of the ink would
make every row twitch as the pointer crossed it. A PINNED account shows its star permanently —
that one is a state, not a control waiting to be found.

⚠ **The rail stays 248px wide and that is a MEASURED constraint, not a preference.** It was widened
to 270px mid-pass for a little more name room and that took the detail table's P&L column from
102.86px to just under the 100px the column-sharing test guards (floor 96px) — the rail's width is
spent out of the same pool those nine columns share. Reverted to 248; the longest real nickname
(`PU Prime ECN demo`) still fits beside its equity figure at that width. If the rail ever needs to
be wider, the detail table's own thresholds have to be re-measured in the same pass.

Verified: `tsc --noEmit` clean; `bots-accounts.spec.ts` 135/135 against the offline build; loaded
in a real browser against the live backend at 1600×1000 — both groups, three accounts, one open per
kind, the hover-revealed pin, and the red worst-status dot on the account whose bot is troubled.

### The detail column is ONE fleet table (2026-09-15, fifth pass)

Aaron, on the running page: *"does it feel too busy? How would you improve the UX for simplicity
yet effectiveness to manage these bots?"* Two mockups followed. He found the first *"still busy"*,
rejected the second (no rail, no headings, hover-only buttons) outright, and said *"build the design
from before"* — so this is the FIRST mockup, built. The rail is untouched.

What the page did wrong, each measured off his screenshot with three accounts open:

- **Nine column headings drawn three times.** Each open account was its own card with its own
  heading row. → One `fleet-table` container, `ColumnHeadings` drawn once, each account a BAND
  section inside it (`renderDetailPanel(view, index)` — no card, no headings of its own).
- **Nine tracks, most of them nothing.** Four of six bots printed `$0.00`, `0.0%`, `0` and `—`
  across four cells. → FIVE tracks: Bot, Status, Performance, Version, Actions. `Performance` is
  one LINE — money · trades · R per trade, the trophy still on the R, the count still beside it —
  and a record holding no closed trade says **"no trades yet"** once (a measured zero, distinct
  from `Contribution`'s "no record yet"). ⚠ Aaron's 2026-09-10 rule *"nothing stacked on top of
  each other"* still holds and a test pins it: the cell is one line, never a column.
- **Return % per bot and Risk per bot left the row.** The bot panel states both. The band shows
  the risk BUDGET instead (`RiskBudget`: "10% of 10% risk" and a thin gold bar, red with the
  server's overflow reason) — the number that decides whether another bot fits. 🔴 Both figures
  come off the server (`share_total_pct`, `share_overflow_reason`); the page adds nothing up, per
  *The page may NOT add the risk shares up itself* above. Only the bar's width is a local ratio,
  and it decides nothing. **Avg per bot went** — a mean of per-bot returns the rows no longer show.
- **Four unlabelled icons per bot — 24 on screen.** → One primary action in WORDS (`PrimaryBtn`,
  Start or Stop, neutral until hovered), Configure's icon, and a "···" (`components/OverflowMenu.tsx`,
  new, reusable) holding Restart and Logs. ⚠ **Configure deliberately stayed OUT of the menu** —
  it was lost twice as something you had to find, and the mockup that put it in the menu was
  overruled on that history.
- **Nothing said what needed you.** → A "needs you" line over the table, AMBER (the colour rule's
  "needs your attention" — the mockup drew it gold, which is limits). 🔴 **It invents no rule**:
  a bot counts when its own Status is `bad`/`warn` (`botCondition`) or its version pill is amber —
  and the pill's amber states now come off one function, `versionNeed` in `lib/botVersion.ts`, read
  by the pill AND this line, so they can never disagree. Grouped by the row's own word. Empty while
  the box is still being asked.
- **The equity shows MT5's figure or a dash** — the rail row's "not read"/"unread" words went too,
  matching origin's 2026-09-14 rule (*"read exactly what's on the MT5"*).

⚠ **No `overflow-hidden` on the fleet table** — the last row's "···" menu opens past its edge.

MEASURED at 1600px on the live backend: Bot 205px, Status 189px, Performance 316px (floor 230),
Version 158px, Actions 150px. The column-sharing test now asserts Performance > 230px.

Test fallout, each watched red first against the old nine-column shape: the column-sharing test
reads five headings off `fleet-table`; *"one value per cell"* became *"a bot's performance reads as
one line"* (Return % assertion dropped, the idle bot's zero reads `data-count="0"` + "no trades
yet"); the heading-alignment test lines Performance up with its cell; the live-rows-start-at-zero
test reads "no trades yet" for `$0.00`.

### The cap on the band says the ceiling and the ROOM, not "10% of 10%" (2026-09-15, same day)

Aaron, on the fleet table: *"only thing I don't like is the 10 of 10 risks display — improve that."*
It read like a typo, and its bar was FULL on both accounts — two bots at 5% under a 10% cap is the
setup he chose, so the loudest mark on the band sat over the normal state. The two things a reader
wants from that spot are the ceiling and whether another bot fits, so `RiskBudget` now says exactly
that, with no bar: **"Cap 10% · full"**, **"Cap 10% · 5% free"**, **"Cap 10% · over by 3%"** (red,
the server's overflow sentence on hover). Quiet grey for full and free — only over is coloured.

🔴 **The room is the server's `room_pct`, never cap minus total worked out here** — verified
assigned in `routers/bots.py` and pinned in `test_account_risk.py` before the page read it. A payload
without it (cached before the field existed) shows the cap alone. An unreadable share still says
so ("shares unreadable") rather than reading as zero.

Four tests pin it: full / room left / over each state their `data-state` and words and never the
old "of 10%"; a payload with no room figure shows no room. **Watched red by mutation**: reading
`room <= 0` as `room < 0` turned the full case red ("Expected: full, Received: free"), then reverted.
Live at 1600px: both accounts read "Cap 10% · full".

## The stop-protection switch, with what it COSTS beside it (2026-09-16)

Aaron asked for an on/off for the 1R breakeven, per bot, from this page. It is a runtime row like
the risk share, so it saves the same way and the bot picks it up while flat, with no restart.

🔴 **THE MEASUREMENT IS RENDERED BESIDE THE CONTROL, IN BOTH STATES, AND THAT IS THE WHOLE POINT
OF `BotSwitchEditor.tsx`.** Both switches this surface offers have been measured and both lose
money. *"Protect the stop"* is a sentence nobody argues with, so a bare toggle would be turned on
for exactly the reason the measurement says not to. The sentence comes from the SERVER
(`bot_params.RUNTIME_SWITCHES`) and the page refuses to draw a switch without one — a second copy
here would drift, and the on-screen copy is the one nobody re-measures.

⚠ **Turning it ON confirms; turning it OFF does not.** Off is where the measurement points, and a
confirmation on the safe direction trains a yes on the unsafe one.
⚠ **Off is stated as a CHOICE, not as blank** — "Off — the stop stays where the trade started".
A reader who cannot tell "off" from "unset" flips it to make the row look configured.
⚠ **The row's SHAPE is the server's, never a name matched in the page.** `row.switch` decides
whether a runtime row is a switch or a number box; the two live bots' switches are different
fields with different types, and a page that matched on either name would be wrong on the other.
⚠ **The value written is the server's declared `on`/`off`, never `true` or `1`** — see the type
trap in `algos/notes/shared-and-live-runtime-reference.md`.

## The account band sits on the bots' grid (2026-09-16)

Aaron: the band's figures staggered with their lengths, and its configure icon did not line up
with the bots'. The band now uses the rows' own five columns: the return under Performance, the
cap under Version, the equity under Actions. ⚠ **The band's configure icon is GONE and the whole
band opens the account** — a bot row hides its "···" while a deploy pill shows, so its configure
icon moves and nothing could line up with it. **Stop is red at rest** (his call); Start stays
neutral until hover.

## The bot panel: risk as setting rows, the account as a card, the record as tiles (2026-09-16)

Aaron: risk read repetitive, account and record read boring. **Risk & exits** replaces the heading
that repeated the risk row's own label; each setting is a row with its name on the left, and the
breakeven measurement sits in a tinted box under its switch (still on screen in both states).
**The account is one clickable card** — number, live/demo, name, balance, and this bot's share of
the cap, all server figures; what a move does went to the heading's hover. **The record is four
tiles** (trades, won · lost, net dollars, net R) with its period beside the heading; nothing closed
shows dashes, never a measured zero.

## An account's Results page — `/bots/accounts/:account` (2026-09-17)

`pages/Bots/AccountResults.tsx`, opened by **Results** in the account panel (every account, demo or
live — it only reads). Backend: `backend/notes/accounts-risk.md` → *An account's REAL record*.

- 🔴 **Where the record came from is always on screen** — grey strip for the box, amber for the git
  backup, with the newest deal's time and the read time.
- 🔴 **Nothing recorded is its own state** — the server's sentence, no chart.
- ⚠ **The balance chart is the backtest's equity chart**: the broker balance as the main line,
  growth with deposits removed as a second line, and each deposit or withdrawal as a grey mark
  (the chart's new optional `markers`; a backtest passes none).
- ⚠ **Every analysis panel reads the trades with money moves removed**, re-based on the money put
  in (`runAnalysis/bookRun.ts`) — a withdrawal would otherwise draw as a drawdown.
- ⚠ **The R distribution counts trades with no recorded stop beside the chart**, never at 0.
- ⚠ Price chart is the unchanged panel; drill-down goes to the account's own candles route.
- ⚠ Not yet driven in a browser: the test browser refused the private port. Checked by typecheck
  and by the route's JSON against a fixture archive built from real cached gold prices.
