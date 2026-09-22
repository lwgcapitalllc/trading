# Notes — Strategies page and multi-leg stacks

The Strategies page audit, how a stack's run panel and leg toggles work, shared-account stacks, and the running-stack progress readout. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The Strategies page — audited 2026-08-06

Aaron asked for a full audit of the page (Strategies tab, Deployed tab, Scan) with one reported
symptom: **"if the NT8 agent is down I get this annoying error about remote end closed connection
without response, every couple of seconds."** He was describing a toast storm, and the storm turned
out to be the visible edge of a page that could not distinguish *the VPS says no* from *nobody
asked the VPS*. The backend half is in `backend/CLAUDE.md` → *The Strategies page — the 2026-08-06
audit*.

🔴 **A toast is an EVENT; a dependency being down is a STATE.** `api.get` toasts on every non-ok
response, and both strategy-file queries are on a `refetchInterval` — so one unreachable agent
produced roughly **six error toasts a minute for as long as the page was open**, plus a burst on
every window focus, each one duplicated by an `onError` handler that toasted the same failure a
second time. `request()` now takes `RequestOpts { silent }`, both polling hooks pass
`{ silent: true }` with `retry: false`, seven duplicate `onError` toasts are gone, and the failure
is **rendered** — `AgentDownBanner` on both tabs, driven by the `nt8_error` / `mt5_error` fields on
the new envelopes. ⚠ **`silent` suppresses the TOAST, never the error** — `isError` and the payload
both still reach the caller, and using it anywhere the caller does not render the failure would be
converting a loud bug into a quiet one.

🔴 **With sync-status down, a strategy that needed deploying offered a Run button.** The endpoint
502'd, every row lost its `sync` object, and `sync === undefined` fell through every pill and every
guard to the default action. **An absent answer took the shape of a healthy one.** The action cell
is now gated — `isPython || sync !== undefined` — and renders a plain `unknown` otherwise.

🔴 **The version chip named the wrong version.** `liveVer` read `needs_compile ? deployed_version :
(compiled_version ?? deployed_version)`, so on a strategy deployed but not yet compiled it reported
the DEPLOYED version as what was running — while NT8 and MT5 both execute the **compiled**
artefact. It is `sync.compiled_version` full stop now, and the tooltip says *compiled vN is what
runs*.

⚠ **`file_exists_on_vps` was returned by the backend and rendered by nothing**, so a deployment
whose file had been deleted off the box read green **In sync**. It draws **Missing on VPS** now,
with the action reading **Redeploy** — and 🔴 **my first fix reintroduced the exact contradiction
it existed to remove**, adding the red chip BESIDE the hash-derived pill so the row showed green
*In sync* next to red *Missing on VPS*. **The browser check caught it; reading the diff had not.**
The status is one ordered-exclusive chain: `Needs deploy → Missing on VPS → Needs compile → VPS
unknown → In sync`.

**Also:** the compile modal had **no way out while a job ran** (footer Close renders only on
completion, and a hung poll never completes) — it now has a header X, an Escape handler, and reads
`isError` so a failed status poll ends the spinner instead of spinning for ever. The Reconcile
button reads `strategy.is_orphan` off the row rather than `scan.data?.orphans`, so a deleted source
file is visible on load instead of only after somebody presses Scan. The market filter moved into
`?market=`, and both `setSearchParams` calls **merge** rather than replace — `setSearchParams({tab})`
drops every other param, which is how the tab switch would have silently cleared the filter.

**`tests/strategies.spec.ts` — 11 new checks.** ⚠ **A clean fail-watch against `HEAD` was
impossible and was NOT done**: the two endpoints changed shape from a bare list to an envelope, so
the old page fails against the new backend for unrelated reasons. Non-vacuity was established by
**mutation** — each fix removed in turn, the naming test confirmed red. 🔴 **That found a test of
mine that could not fail on the defect it named**: deleting the Run-button guard left *"a strategy
that needs deploying still says so with the agent down"* green, because that mock sets
`needs_deploy: true` and Deploy renders either way. A separate test (*"a whole sync failure never
leaves a deploying strategy offering Run"*) fails the entire sync request and **does** go red
without the guard. **A green new test proves nothing until you have seen it red — and "I watched
the suite go red" is not the same claim as "I watched THIS test go red for THIS reason."**
⚠ **Locators here key off the platform badge `img`, not the name** — the Name column renders the
display name (*Opening Range Breakout*), not the class name (*ORB*).

## A stack renders a RUN's panel — same four cards, and the legs are the Verdict card's rows

**Rebuilt 2026-08-10, Aaron's call, in his words: *"it should look exactly like a single run
backtest page… I don't want stack stuff here and a regular backtest details page to look two
different. Unless there's some cumulative thing that I need to watch."*** Plus: *"the strategies on
your stack could be toggled from within the verdict section, and the KPIs and everything should
change as you toggle them."*

`StackDetail` already reused `PerformancePanel`, so the numbers were computed identically — and the
page still read as a different feature, because everything AROUND the numbers differed. It had a
full-width strategy ribbon where a run has a Verdict card, three cards where a run has four, a
plain `<h2>Performance</h2>` where a run has a collapse control, and the leg toggles in a section of
their own two scrolls down. Now:

- **Four cards, Verdict first**, via the panel's `verdict` slot. A stack has no ruleset to grade
  against, so that card answers the question that IS a stack's own — what is this made of — with
  the same hero a run puts there (the trade count) and the same cadence line under it.
- **The legs are `PanelRow`s inside it, and each row is the toggle.** That is the point of moving
  them: the control that decides what Made / Risked / Trusted count now sits in the same row as the
  numbers it recomputes. A leg that cannot be toggled — still replaying, failed, or the last one
  left on — is still LISTED, dimmed, with the reason on its ⓘ: *not finished* and *not in this
  stack* are different answers, and hiding the first makes a stack look smaller than it is.
- ⚠ **`PanelRow` gained `onClick` / `lead` / `muted` rather than the card forking its own row
  markup.** A second private copy of that anatomy is exactly how the fourth card drifts out of line
  with the three beside it — the same argument that moved `panelCardCls` / `CardHead` / `CardHero`
  to module scope when the verdict became a card.
- ⚠ **The Verdict card passes `collapsed: false` ALWAYS.** The panel's collapse means *hero numbers
  only*; the leg rows are a CONTROL, not a supporting metric, and hiding them would put the toggles
  behind a preference the reader last set on a different page.
- ⚠ **`usePerfCollapsed` is ONE hook behind ONE key, exported and shared.** A second copy of that
  state would mean the same control on the same panel remembering two answers depending on which
  page you pressed it on last.

## A leg toggle swaps in the SOLO CONTROL — it does not slice the shared book

**2026-08-10, and this is the rule that makes the toggles trustworthy.** `composeCombined` takes
the stack's `mode` and returns a `basis` naming which book produced the numbers:

| basis | when | what it shows |
|---|---|---|
| `screen` | the stack is a screen | every leg had its own full account, so any subset is honestly additive |
| `shared` | every leg on | the shared replay, exactly as it ran |
| `solo` | one leg on, and it has a stored control | that leg's SOLO replay — genuinely *if the others never existed* |
| `unmeasured` | anything else | nobody replayed it, so there is nothing to show |

🔴 **Before this, a subset was composed from the SHARED trades**, which answers *what did this leg
contribute to an account the others built* and reads as *what this leg made*. Measured on
`st_94aeb25f0c`: B-LEG posts **99 trades and +17.8674R either way, at identical entry and stop
prices**, and reads **$47,758,999 shared against $21,064 alone**, because inside the stack its last
trade risks $16,925,791 of a balance SOS Fade grew rather than $3,102 of its own.

- ⚠ **`unmeasured` still renders the Verdict card.** The leg toggles live inside it, so hiding the
  Performance panel would leave the reader in a state they cannot click their way out of. The three
  KPI cards are replaced by `UnmeasuredCard`, which states what DOES exist and offers the way back.
- ⚠ **A subset of a SCREEN is never refused.** There nothing could block anything, so removing a leg
  removes only its own trades; a screen needs no control book and must not ask for one.
- ⚠ **The per-leg row value is R.** It is the only per-trade figure a change of position size cannot
  touch, so it is identical shared or solo — which is exactly why the row leads with it. The row used
  to print a trade count with *"It made `<net_pnl>` on its own account"* on its tooltip, and on a
  shared stack `net_pnl` is the leg's dollars INSIDE the portfolio, so that sentence was false by
  2,266x on the measured stack. The tooltip now names BOTH figures and says which is which.
- ⚠ **`legTrades` and `legR` cover every COMPLETE leg, not only the enabled ones.** They are facts
  about a leg, and falling back to a different unit when the reader switches it off made one row read
  `+17.87R` and the other `160` on the same card. The duration weighting reads the book directly for
  the opposite reason — averaging in legs that are switched off describes a portfolio nobody is
  looking at.
- ⚠ **`BasisChip` is beside the Performance heading, not in a tooltip.** It changes what every number
  under it MEANS, and the figures jump by orders of magnitude between bases, so a silent swap is its
  own defect even when each number is right.
- ⚠ **`EquityPoint.r` had to be declared on the BACKEND model to reach here** — the fifth field that
  model has dropped while it sat on disk. See `../backend/CLAUDE.md`.
- ⚠ **A shared stack replayed before 2026-08-10 has no control book**, so it lands on `unmeasured`
  rather than inventing one. `backend/scripts/backfill_stack_solo.py` re-derives it.

## A loss-recovery leg is a TICK BOX ON ITS PARENT, never a row in the picker (2026-08-21)

`StackConfigModal` nests one checkbox under the selected strategies: *Also run loss recovery on
&lt;leg&gt;'s losses*. It sends `recovery_parent`. Backend rules: `../backend/CLAUDE.md` →
*A stack leg may READ ANOTHER LEG'S LOSSES*.

🔴 **The rule is FILTERED OUT of every picker on `Strategy.requires_source`** — the stack builder's
list and the Strategies page's stackable set. It has no setups of its own, so picking it as an
ordinary leg builds a stack with nothing to read, and **an empty book is indistinguishable from a
rule that found no setups**. The alternative shape — listing it beside the real strategies with a
"recovers:" dropdown — was rejected: it lets you build a stack with no parent, or the wrong one,
and the run then refuses AFTER the reader has filled in the form. **A dependency the UI cannot
express becomes a runtime refusal, which is a worse version of the same rule.**

🔴 **THE STRATEGIES LIST IS A TREE (2026-08-21).** `ordered` groups each row under the strategy
its own package declares (`Strategy.display_under`), so the loss-recovery rule sits directly beneath
the bot it recovers instead of wherever the alphabet put it. ⚠ **The indent lives INSIDE the name
cell**, never on the `td` and never as a spacer column — padding the cell shifts every column to
its right out of line with the header, and the table's own column widths are what keep
Platform/Params/Runs/Status aligned. ⚠ **A child whose parent is not in the visible list renders at
the TOP level rather than disappearing** — the market filter hides rows, and a strategy vanishing
from this page is how somebody concludes it was deleted. ⚠ **A cycle appends the unemitted rows
instead of dropping them**, same reason. ⚠ **Display only** — nesting changes nothing about how a
strategy runs, stacks or deploys.

🔴 **THE STACK BUILDER COUNTS LEGS, NOT TICKED STRATEGIES (2026-08-21).** `settingsReady` required
two ticked strategies and the Strategies page's Stack button required two before it would even
open — so **SOS Fade with a recovery on SOS Fade, the stack this whole leg exists to make possible, was greyed
out at both doors and refused by the backend behind them.** The count is now
`selected.size + (shared && recoveryFor ? 1 : 0)`, matching `_validate_stack_strategies`, and the
list-page button opens at ONE ticked strategy because the recovery is ticked inside the builder,
where that button cannot see it. ⚠ **Opening is not running** — the builder still refuses to submit
under two legs. **Nothing here was broken; the path just could not be walked, and every piece of it
had been tested on its own.**

⚠ **`recoveryFor` holds the PARENT's id, not a boolean and not a set** — at most one recovery leg
per stack, because two would share a name on the shared account. Unticking a parent clears it, or
the request names a leg that is not in the stack.

⚠ **`recovery_params` is NEVER SENT and the recovery leg has no settings editor here.** Per-leg
overrides hang off the leg list, and the rule is filtered out of that list — so the backend field
exists, is honoured, and no page fills it. The leg runs on its defaults, which are the measured
configuration. Written down rather than left for somebody to look for a control that was never
built.

⚠ **Never sent on a SCREEN.** There every leg trades its own full account, so the recovery could
never take room off its parent — the only question it exists to answer. The backend refuses it;
this never sends it.

⚠ **The Strategies page GREYS its Run button (*Needs a parent*) rather than hiding it**, with the
reason on the title. Same rule as an unassignable account on the Accounts tab: a control that
vanishes reads as a feature that does not exist, and a reader who came looking for the rule needs
to be told where it went.

🔴 **AND SO DOES `StrategyDetail.tsx`, WHICH WAS MISSED AND IS THE WHOLE LESSON HERE (2026-08-21).**
Filtering the pickers and greying the LIST page's Run left the rule's own detail page with an
unconditional Run Backtest button and a full Run modal — so it could still be run alone, from the
UI, in two clicks. **A strategy is reachable from more than one place, and guarding the list is not
guarding the strategy.** Both pages now read the same flag and render the same disabled button with
the same title. ⚠ **The button is a LABEL either way** — the gate is `routers/_source_guard.py`,
which refuses every endpoint that starts a job from a strategy id; see `backend/CLAUDE.md`. There
is no automated test on either button, because Playwright is out of the suite by design.

## The stack form gained a BROKER, a COST SWITCH and PER-LEG RISK (2026-09-02)

🔴 **The single-run form has carried all three for weeks and this one had none of them, so every
stack this lab has produced is a GROSS number sitting where the answer goes.** With no broker and
no cost switch the request fell through to the two typed cost figures, which default to zero.
Aaron: *"too many options are missing compared to when you actually try to run a backtest of a
single strategy… stacking should have all the same things."* Backend contract and the measured
size of the gap: `../backend/CLAUDE.md` → *A stack is CHARGED like a single run*.

⚠ **All three MIRROR the Run modal rather than being invented here** — the broker select is first
because everything under it depends on it, the cost switch is one toggle outside any fold and
defaults ON, and an unpriced tier disables the run and says why before the click. **Two forms that
default differently is how one of them starts lying**, so the defaults are copied deliberately.

⚠ **`charge_costs` is a BOOLEAN and the page sends no layer list.** The policy lives on the side
that charges it. Same rule as the Run modal, and it is rule 7 — a label is a claim about code
somewhere else.

⚠ **The broker starts `null` and an effect fills it once**, defaulting to the ATTACHED terminal and
never overwriting a choice the reader has made. `broker_profile` is OMITTED while it is null rather
than sent as one: the request model defaults it, and a null refuses the whole stack with a message
about an unknown broker — a contract mismatch reported as a broker fault.

🔴 **AN OVERRIDE REPLACES A LEG'S WHOLE SETTINGS — IT DOES NOT MERGE WITH THEM.** The backend reads
`params_by_strategy[id] OR the strategy's stored defaults`, never both, so a risk box sending only
the field it edited would run that leg with ONE setting and silently drop every other. **Nothing
fails**: the leg replays, produces trades, and lands in the table looking ordinary. So an edited leg
sends its COMPLETE set with the one field swapped in.

⚠ **An untouched leg sends NO override at all, and an edit back to the leg's own baseline sends
nothing either.** Any override disables reuse for that leg, so pre-filling every one would silently
turn every screen rerun into a full replay, and typing the number that was already there would cost
a reuse for no change.

⚠ **The risk box is resolved against each leg's OWN schema and is absent for a strategy that does
not declare the field** — a control writing a setting the strategy has never heard of is worse than
no control. The field is named ONCE (`RISK_FIELD`); a second copy of the name is how two surfaces
come to disagree.

⚠ **It renders OUTSIDE the leg row's button.** An input inside a button is invalid markup and every
keystroke would toggle the leg off.

⚠ **The broker select carries no tight `max-w`.** A native select sizes to its WIDEST option and an
option here is a whole account identity plus its attached suffix — clipped it read
`puprime_ecn — connected n`, which looks like a rendering fault rather than a long label. **Second
instance of this trap in this folder** (the Accounts tab's Move menu was the first, in the other
direction).

✅ **`tests/stack-config.spec.ts` — 6 checks, and they need NO BACKEND** (every response is
intercepted, so no SSH tunnel and no live MT5 box; booting the backend is a person's decision
because it can start things on the trading box). ⚠ **A fail-watch against HEAD is VACUOUS** — none
of these controls existed, so every check would go red on an element being absent. **Non-vacuity is
by MUTATION, one named per check, and all six were RUN**: the partial-override mutation reddens the
sibling-settings assertions while the risk assertion above it stays green, which is exactly the
shape of the defect. ⚠ **The fixture's ATTACHED profile is SECOND in the list on purpose** — one
whose attached profile is also first cannot tell a working default from `useState(profiles[0])`.

## A NEW stack is always a SHARED ACCOUNT — the mode picker is gone

**2026-08-10, Aaron's call:** *"I would never ever ever wanna do a screen. I would always wanna do
a shared account, because that's what a stack IS — we're sharing the same resource. I wanna know
how two strategies affect each other and where some trades are dropped because others have taken up
all the capacity."*

A `screen` runs each leg on its own full account and adds the results up, so nothing can ever block
anything. Offering it beside `shared` as an equal choice in `StackConfigModal` made the one mode he
wants a coin flip — **and it was the mode a `?? 'screen'` default silently picked.**

- ⚠ **This is NOT a removal of screen support, deliberately.** Three stacks in the lab are screens,
  `StackDetail` still renders them with their `Screen · upper bound` chip, and a RERUN carries its
  own mode forward through `initial.mode` — so rerunning a stored screen does not silently turn it
  into a different experiment. What is gone is the way to make a NEW one. Deleting the mode
  outright would rewrite what those stored rows mean.
- The mode paragraph is derived from `shared` rather than removed, so a screen's own rerun modal
  explains what it is and says new stacks are shared accounts.

## The shared account is two rows in the Verdict card (2026-09-13)

Aaron: *"what is the purpose of this shared account section? it is taking up space."* On the live
pair the cap cost nothing in 6.7 years — one entry trimmed by $8.61 — and the section spent ~250px
saying so, under an amber `1 REFUSED` chip over a trade that was trimmed, not refused.

- **`readCap` is the one reading.** The Verdict card's `Peak risk` / `Cap cost` rows and the table
  below the panel take the same object, so they cannot disagree about one run.
- **Peak risk is stated WITH the cap** (`10.06% of 10%`). A peak above the cap is explained on its
  ⓘ: the cap is checked when a trade opens, and a loss or overnight charge on an open trade lifts
  the peak past it. It is not a breach.
- **Cap cost reads `none` in words** when nothing was made smaller or blocked, with the
  measurement sentence on its ⓘ; else `1 trade smaller` or `1 trade blocked`. 🔴 **No dollar
  figure in the row**: `1 trimmed · $9` read as the cap COSTING $9 (*"what does 1 trimmed $9
  mean?"*) — it was risk the trade did not take, and its R did not move. The dollars are on the ⓘ,
  per strategy. Never "refused" for a trade made smaller. Amber only for a block or a moved R.
- 🔴 **The per-strategy table appears only when the cap COST something** (`costly`): a blocked
  entry, a strategy whose R or trade count differs from alone, or a failed seam check. A trim that
  left every R unchanged is one row, not a section.
- ⚠ **The rows sit only beside the shared book as it ran** — not with a leg switched off, not under
  a period window, not collapsed (supporting rows fold; the leg rows stay, they are the control).
  They go FIRST, so the leg toggles do not move. The section's replaying / failed / cancelled /
  abandoned states are unchanged.
- ⚠ **The together/apart dollars line is gone, not moved.** It compared closing dollars across one
  shared balance — root rule 6 — and its own tooltip had to tell the reader to ignore it.
- ✅ **Proof: six checks in `tests/stacks.spec.ts` plus the kept seam-failure check; 15 bugs planted
  one at a time in a throwaway worktree, 15 killed, each on the assertion written for it.** ⚠ The
  dollars-back-in-the-row plant is caught ONLY by the no-`$` assertion — `1 trade smaller · $9`
  still contains `1 trade smaller`.

## A running stack has ONE progress readout (2026-09-03)

🔴 **TWO LIVE READOUTS OF ONE JOB, STACKED, SAYING DIFFERENT NUMBERS** — the banner counting
finished STRATEGIES, the shared-account panel under its own heading counting BARS inside the current
leg. Nothing said they were the same replay, so the honest reading was that two things were running.
Measured record: `../docs/FRONTEND_BUILD_NOTES.md` → *The stack page's two progress readouts*.

- ⚠ **`sharedInBanner` is the ONE expression deciding who owns the readout**, read by the banner AND
  by the shared-account section's render guard. Two hand-written conditions is how the page draws
  both again, or neither.
- 🔴 **No STOPPED replay is folded in, and ONE list decides which those are** — read by the
  banner's ownership test AND by the panel's own branch, because they are two halves of one
  decision. Each stopped state has a SENTENCE to show, not a percentage, and **folding one into a
  progress bar is how a dead job comes to look like a slow one.**
- 🔴 **That list held FAILURES ONLY until 2026-09-03, and in the gap the two halves disagreed.**
  The panel showed its cancelled sentence only once nothing was running, so a cancellation arriving
  mid-replay was drawn by NEITHER and fell through to raw machine text — the backend's own word
  beside a spinner at 100%. ✅ **A cancellation is a fact about the shared replay whoever else is
  still going**, so that branch is no longer gated on the stack running. ⚠ **The ABANDONED half
  still is, and the two read alike while asking different questions**: silence while the legs run is
  *a beat behind*, and the same silence once nothing runs is *this will not arrive*.
- ⚠ **An UNRECOGNISED phase IS absorbed, deliberately — the one judgement in this merge.** Absorbing
  only the known phases hands an unknown one to the panel, which draws its own spinner and puts the
  page back to TWO readouts, the defect this exists to fix. **One readout a beat coarse beats two
  that disagree.** The cost is real and is the thing to remember: **a STOPPED phase added to the
  backend must join the list in the SAME change**, or it arrives here wearing a progress bar.
- 🔴 **Every phase the backend can emit is named in WORDS.** `solo:b_leg` / `shared` is the
  backend's vocabulary — **a progress line the reader has to decode only reports to its author** —
  and ⚠ **the log MESSAGE is not a fallback worth relying on**, since it is written for a log line
  and repeats the phase before the part worth reading. An unnamed phase degrades to that message's
  first segment. Vocabulary: `backend/services/portfolio_runner.py`. The bar counter is kept after
  the words; the finer measurement drives the bar and the leg count becomes its caption.
- 🔴 **A section with nothing to show is NOT a section.** The *"Waiting for the first strategy to
  finish…"* card was a chart-sized box restating the bar at the top of the page, in the slot where
  the reader expects the charts. Gone; the charts appear there when there is a book.
- ⚠ **`shared-account-panel`'s own still-replaying branch is untouched and still tested** — it
  renders whenever the STACK is not running. **Do not read the merge as that branch being deleted.**
- ⚠ **The bar carries a 2% floor** so it is visible from the first frame, which is why the checks
  assert its CONTENT and never its width — the run page's own trap.

### The Settings section is ONE card, not N floating bars

🔴 **An unframed column of detached pills, last on a page built out of framed sections.** It is one
bordered card with the legs as divided rows — the anatomy the per-strategy table above it uses.

- ⚠ **Every rule underneath is unchanged**: per LEG rather than one merged list (two strategies can
  hold one key at different values, and a merged view would have to pick), still a disclosure, and
  still rendering `false` as the word — **a boolean dropped as falsy hides exactly the pinned value
  this section exists to show.**
- ⚠ **The heading carries the sentence saying what it IS.** "Settings" names a category, not a fact,
  and this section's job is a value that exists nowhere else on the page — a param the STACK pinned.
- ⚠ **Suppressing the native disclosure marker means ADDING one** (`list-none` +
  `[&::-webkit-details-marker]:hidden`, with a `group-open` chevron), or a row opens with nothing
  saying it could be opened.

🔴 **IT PRINTED FIELD NAMES FOR ITS WHOLE LIFE, AND THE SINGLE-RUN PAGE HAD NOT SINCE 2026-08-20
(fixed 2026-09-06).** One question — *what settings produced this book?* — answered in two
vocabularies six inches apart, and Aaron could not read this one: *"these settings show the actual
code variable names. So when I look at them, I don't know what's on or what's off."*

- 🔴 **`components/runSettings.ts` is the ONE classification, read by BOTH surfaces.** The words,
  the group ORDER and both folds come out of `buildRunSettingsView`; each page owns only its
  LAYOUT — a 248px rail stacks a label over its value, a full-width card puts groups side by side.
  **A second copy of this is how one surface starts teaching a different name for one setting**,
  which is the drift this file already records for the Sharpe formula and the condition evaluator.
- ⚠ **The fold HEADINGS and CAPTIONS are shared constants too.** A reader who learns what
  *Already decided* means on one page has learned it; two wordings is two folds.
- ⚠ **Nothing is DROPPED — a settled param and one whose parent is off both fold, never vanish.**
  This card is the RECORD of what each leg was handed, and a report that silently omits inputs is
  a worse defect than a long list. Same rule, same code, as the run page's panel.
- ⚠ **A missing schema degrades to a tidied field name and the raw value, never to a blank row.**
  A strategy scanned before its metadata existed still has to render every setting it was sent.
- ⚠ **The schema is read off the STRATEGY LIST (`useStrategies`), which the app already holds
  warm — never one request per leg.** A stack takes as many legs as it likes, and a fan-out that
  grows with them is the shape this repo has paid for once already.
- ⚠ **An open leg tints its own header and takes a 2px rule in ITS chart colour.** Two open legs
  ran straight into each other (*"the two strategies kinda start on top of each other"*) — a body
  ended in rows and the next leg began with a row-sized line, with nothing between them saying a
  new strategy had started.
- 🔴 **ONE ROW PER LEG IS THE SHAPE THAT SCALES, and an account takes more than two strategies.**
  Rows grow the card LINEARLY and collapse to one line each; side-by-side columns halve their own
  width with every leg added and take the group grid inside them down to one column with it. Aaron
  left the call open (*"I can stack more than 2 strategies on an account so you decide"*) — this is
  the decision, and the reason is the third leg rather than the second.
- ⚠ **ONE bulk control, stating which way it will go** (`stack-settings-toggle-all`, shown at two
  legs and up). Two buttons leave a dead one on screen at each extreme. It says the WORDS, not an
  icon: the header has room, and an icon is a rebus for anybody who has not already learned it.
- ⚠ **The legs are CONTROLLED (`open` / `onToggle`), never left to the native disclosure** — a
  `<details>` owning its own state and a parent deciding which are open are two owners of one fact,
  and they disagree the first time somebody presses Expand all with a leg already open.
- 🔴 **The tracked set is what is OPEN — the OPPOSITE polarity to the run page's parameters rail,
  and deliberately.** That rail exists to show at a glance what a run charged, so it must arrive
  expanded and track what is SHUT. This card holds N strategies' full settings at the bottom of a
  long page; opening them all on arrival buries the page it sits under.

✅ **`tests/stacks.spec.ts` (34 → 36), and the settings checks now SERVE their own param schema**
— these legs carry real strategy ids, so an unrouted `/strategies` hands the page whichever labels
those packages happen to carry today and every assertion moves when somebody edits a meta file.
**What is under test is that the card reads the metadata AT ALL**, never what a particular strategy
calls a setting. All three are watched RED by mutation: names reverted to field names reddens the
words check, a fold that DROPS instead of folding reddens the second, and letting each leg own its
own disclosure again reddens the bulk control's.

✅ **`tests/stacks.spec.ts` (29 → 34).** ⚠ **A fail-watch against HEAD is vacuous** — the merged
block did not exist, so a red proves the locator only. **Non-vacuity is by MUTATION, seven named and
all seven RUN**, and two of them are ONE defect: the stopped-phase list and the panel's own branch
have to be mutated separately, because neither alone is what went wrong. ⚠ **The panel-count assertion waits on the progress block FIRST** —
`toHaveCount(0)` is satisfied while the page is still loading, so asserting it straight after `goto`
passes against its own mutation. **Fifth instance of that trap in this folder.**

## The regime overlay is OFF by default, from ONE hook

**2026-08-10.** Aaron: *"Regimes, take it off by default. I don't wanna see the regimes on the
equity curve — that's the same thing whether I'm on a backtest, a stack, an optimization, a tune,
all those pages that have equity curves."*

🔴 **There were THREE definitions of this preference and only one of them persisted anything.**
`BacktestDetail` had `getOverlayPref`/`setOverlayPref` (stored, defaulting ON); `StackDetail` and
`TuningWorkbench` each had a bare `useState(true)`. So switching it off on two of the three
surfaces did not survive a navigation, let alone a reload — the same shape as the Sharpe formula
this folder already records three private copies of.

`useRegimeOverlay()` in `components/RegimeOverlayToggle.tsx` is the single one, and it lives with
its CONTROL rather than in whichever page wanted it first.

⚠ **The default is expressed as the polarity of the stored check** — `localStorage.getItem(_KEY)
=== 'true'`, so an unset key reads OFF. The old `!== 'false'` spelling is what made it default ON;
flipping the default means flipping that comparison, **never adding a second key**, or a reader
who already answered gets asked again under a different name.

## The portfolio line is green and no leg may be confusable with it

🔴 **`LEG_COLORS` was `C.series.filter(c => c !== C.pos && c !== C.neg)`, and exact string
inequality cannot express "not confusable with".** The palette holds near-misses: `series[1]` is
`#00ff7f` against `C.pos`'s `#00ff82` — three units apart in one channel, the same green to any eye
— and `series[5]` is `#ff3b5c` against `C.neg`'s `#ff496b`. Both passed the filter, so the second
leg of every two-strategy stack drew in the PORTFOLIO's own colour and the legend showed two green
swatches. Reported off the screen (2026-08-10).

It is an explicit list now — cyan / amber / violet / blue. ⚠ **Keep it explicit rather than a
filter over `C.series`:** a filter is a rule that silently re-breaks the day somebody adds a colour
to the shared palette.

🔴 **One of the three new browser checks was VACUOUS on its first run and passed against its own
mutation.** `panel.locator('table')).toHaveCount(0)` asserted straight after `goto` is satisfied
while the PANEL is absent too, so it was green against a build that renders the table
unconditionally. It waits on the panel's own disclosure button first now. **Fourth instance of this
trap recorded in this folder** (`svg.first()` being the sidebar logo; a page-wide Retry matching the
page header's; a page-wide Rebuild matching the host's chrome behind a fullscreen overlay) — and the
only reason it was caught is that the mutation was actually run rather than reasoned about.

## Shared-account stacks — the mode has to be on screen before any number is

**Landed 2026-08-09.** `StackConfigModal` (mode toggle + account fields), `StackDetail`
(`SharedAccountPanel` + the header chip), the Stacks list's **Mode** column, `useStackContention`.
Backend and the measured first run: `../backend/CLAUDE.md` → *Shared-account stacks*.

**A stack is one of two DIFFERENT experiments over the same legs**, and everything here follows
from that. A `screen` adds up N standalone runs — every leg sized as if it owned the account and
nothing could block anything, so it is an UPPER BOUND. A `shared` stack replays them together on
one balance with one risk budget. Two rows in the list, over the same legs and window, reporting
different numbers, with nothing to tell them apart, is a comparison the reader cannot make.

- **The mode chip is in the HEADER, beside the window** — before the performance panel, because it
  changes what every number below it means.
- **A screen's chip says `upper bound`**, which is the entire reason it carries a chip at all
  rather than the shared one carrying the only badge. *This is a screen* is not the useful half;
  *nothing here could ever block anything* is.
- **The Rerun modal carries the mode and its knobs forward.** A rerun that silently reverted to a
  screen would be a different experiment under the word "rerun", reporting different numbers with
  nothing on screen accounting for it.

### The panel, and the three things it must not render as blanks

- ⚠ **An empty contention log is rendered as a MEASUREMENT, in words** — the Verdict card's
  `Cap cost: none` since 2026-09-13. It is the EXPECTED state: open risk is measured to each
  trade's CURRENT stop, so a stop at breakeven frees its room before the other strategy asks. A
  row that goes blank there is pixel-identical to one that failed to load.
- ⚠ **`available: false` is THREE answers** — this is a screen, it is still replaying, or it
  failed — and the panel renders a different thing for each. `progress` separates the second;
  `stack.mode` separates the first. The **test seam is on all three branches**, not only the
  finished one. 🔴 **Since 2026-09-03 the still-replaying branch renders only while the STACK is
  NOT running** — the banner at the top of the page owns that readout — so a check for "it says what
  it is doing while running" belongs on the banner and can never find it here.
- **The seam check is rendered.** With a full budget a leg must post the same R shared as solo (R
  is normalised to the trade's own risk), so a difference is the shared account moving a decision
  it must not touch. That is invisible in a table of numbers unless something says it.

⚠ **The section ignores the leg toggles** — the budget is a property of the run as it happened.

⚠ **Contention MARKERS on the price chart are deferred and named** (`docs/SHARED_RISK_STACK.md`).
Every measured run so far refuses nothing, so a marker layer would be a generic mechanism nobody
has ever exercised — the trap this folder already records for the `BOX` template's label path,
whose first real user was its first test. The events are served and rendered as a table instead.

### `tests/stacks.spec.ts` — the first 10 checks, and three of them were vacuous first

Non-vacuity here is by **MUTATION** and could not be anything else: none of this existed at HEAD,
so every check would go red on an element being absent, which proves the locator and nothing more.
Each check names its mutation in a comment. The three that passed when they should not have are
worth more than the seven that worked:

- 🔴 **Every route mock keyed on `http://localhost:8000` and matched NOTHING.** The app fetches
  through the Vite proxy — `api/client.ts` is `const BASE = '/api'` — so three checks silently read
  the LIVE lab and asserted on whichever stacks happened to be in the database that day. **Route on
  `u.pathname` against the `/api` prefix**, the idiom `tuning.spec.ts` already uses.
- 🔴 **"A screen renders no shared panel" passed against its own mutation.** The hook is disabled
  on a screen, so the report is `undefined` and the panel cannot render whichever way the render
  guard is written — **the render guard and the fetch guard are not separable from the DOM.** It
  counts the FETCH now, which is the real guard: a poll enabled on a screen gets `available: false`
  back and leaves a finished screen showing a permanent "replaying the strategies…" spinner.
- 🔴 **The counter that fixed it was registered BEFORE the mock, and was shadowed.** Playwright
  matches the most recently registered route first, so the counter never incremented and the
  assertion was trivially true a third time.

**The standing lesson is this folder's fail-watch rule one notch further.** It already says it is
not enough to watch the SUITE go red — you have to watch THIS test go red for THIS reason. These
three add: you also have to know the OBSERVATION the test makes is one the mutation can change. All
three were green, well-named, and asserting on something the defect could not move.

## A whole strategy SET gets the same three hops one strategy gets (2026-09-07)

Backtest → stress test → demo → live had a control for each hop for a single run, and **the
endpoints for a stack's version of all three had existed for a day with nothing calling them.**
`RunStackStressTestModal`, `StackSettingsImportModal` and `Bots/GoLivePanel`. Backend rules and the
refusals: `../backend/CLAUDE.md`.

🔴 **NONE OF THE THREE DECIDES ANYTHING.** Every list, every warning, every refusal and the
confirmation phrase arrive from the backend, which plans ONCE and returns the same shape to the
preview and the apply. A list assembled here beside one assembled there is two answers about live
bots, and only one of them was read. Same rule the single-bot import is under, and the same rule the
risk-share total had already drifted out of on the Bots page.

⚠ **All three are ALL OR NOTHING, and none offers a per-leg or per-bot tick box.** A shared account
is several strategies measured competing for one balance; writing three of its four legs produces a
set nobody has measured and reads on every later screen as a completed copy. A control per leg would
make that the easy mistake rather than an impossible one.

### Stress testing a stack

⚠ **The button is SHARED-ONLY and is not rendered on a screen.** There every leg traded its own full
account with nothing able to block anything, so the combined figure is an upper bound and a letter on
it would grade a result no account can produce. The server refuses it in those words; a button whose
only outcome is an error toast is the defect this folder records twice.

⚠ **The trade count is the COMBINED book's, off the shared report — never summed from the legs.** Two
legs on one account can hold a position at the same time, so adding their counts answers a different
question from the one the sample floor asks.

⚠ **`trades: null` is *nobody could tell me*, never zero**, and the modal says so rather than
refusing. Rendering it as 0 would state that the account never traded, which reads as a refusal the
reader cannot act on — and the server holds the real gate and names the figure it measured.

⚠ **A stack carries no stored evaluations**, so the ruleset choice is over the FOREX rulesets rather
than over what the subject was scored against. ⚠ **The default is DERIVED, not filled by an effect**
(`chosen === undefined ? default : chosen`): three states, because *not chosen yet* and
*chosen to grade against nothing* are different answers, and an effect that filled the first would
overwrite the second the moment the list arrived.

🔴 **The default is the ruleset this stack was LAST stress tested against (2026-09-10)**, off
`useStressTests({ stackId })`, falling back to the first forex ruleset only for a stack never
tested. The first forex ruleset is the 15% prop-firm figure, so every re-test of a stack graded on
55% silently switched limits and graded it D — a grade against a different limit is not comparable
to the last one (rule 11). ⚠ **The newest test naming a ruleset still on offer wins, whatever its
outcome** — a cancelled test still records what the reader meant. ⚠ **Run is disabled until that
history lands**, or a quick click grades against the fallback while the select is about to change.
⚠ **The hint (`stack-ruleset-from-last`) renders only when the SELECTED ruleset is that one** — tied
to the value, not to the history existing, or it claims "last graded" beside a different ruleset.
Driven in a browser: real history, empty history, a slow history and an explicit "No ruleset"; the
old default and the dropped Run guard each watched red. ⚠ `useStressTests` takes a FILTER OBJECT now
and keys under `'list'`, so slot 1 of the key stays free for a detail's own id — the delete refresh
excludes the deleted test by comparing that slot.

### The stress test page routes on the ROW, not on a missing run

⚠ **`isStack` is read off `stack_id`.** A run that failed to load is not a stack, and inferring the
kind from an absent run is how a transport failure comes to render as a different feature.

⚠ **A stack-targeted row gets its own source card.** Without one the page states nothing at all about
what it graded — `sourceCard` is null with no run. ⚠ **It quotes NO net and no trade count**: those
live on the stack's own combined book, and restating a figure this page has not read is how two
surfaces come to disagree about one account.

⚠ **Two modals, routed here rather than branched inside one.** A stack writes every leg's bot and the
account's ceiling in one commit; a single run writes one bot the reader picks. Neither knows how to
do the other's job, and keeping them apart is what keeps each refusal readable.

### Demo → live

🔴 **A STEP INSIDE THE ACCOUNT PANEL, NOT A MODAL (2026-09-10).** Aaron, on the modal: *"look how
confusing this modal is make it dam simple … no technical code variable names … I rather not go
from a side draw to a modal."* `GoLivePanel` replaced `GoLiveModal`; the panel's body swaps to it,
with a Back link. ⚠ **Plain words only**: a setting is named by `WRITE_LABEL` (an unlisted one gets
a tidied name, never the raw one), a cap reads as a %, a terminal as its folder, a cost profile as
broker and tier. ⚠ **The bots and the cap are frozen when the panel opens**, so a poll mid-review
cannot change what is being confirmed. ⚠ **Nothing is started after the move** — the success line
says to start each bot, never to restart one.

⚠ **It lives in the ACCOUNT drawer, because the set it promotes is *every bot on this account*.** The
account heading is a single `<button>` and a control there would be a button inside a button — the
invalid markup this page has already been bitten by.

🔴 **The button exists ONLY on a demo account (2026-09-11).** It was drawn, disabled, on the live
account the day the first set went live — Aaron: *"this should only be present for demo accounts."*
An account whose kind is not known yet gets none. Pinned by two checks in `bots-accounts.spec.ts`,
the live one killed by mutation.

⚠ **On a demo account every refusal is stated ON the control, before the click** — a running bot,
no live destination — and `goLiveBlock` is a REASON rather than a boolean, because a control that only knows
"no" cannot say which rule said no. ⚠ **A bot the box has not answered for is NOT counted as
stopped**: `statusByKey` holds only what the snapshot reported, and reading that silence as
*not running* is how a live-money write gets offered on a bot that is trading.

⚠ **The confirmation phrase is the SERVER's and is never built here.** It names the destination
account, so it cannot be typed from memory or pasted from a different preview — which is the whole
reason it is a phrase and not a checkbox. The server rebuilds the plan on apply and compares against
that plan's own phrase, so a confirmation typed against a stale preview no longer matches.

⚠ **The literal writes are one click away, never summarised away** — behind *Exactly what changes
on each bot*, listed once when every bot shares them and per bot where they differ. This is the
last screen before real money.

⚠ **A bot's demo record is REPORTED and refuses nothing** (Aaron's call: no minimum). `traded: false`
with a reason means no record reached this machine, which is NOT zero trades and is never drawn as
one — a number nobody measured under a decision about real money is worse than a sentence saying so.

⚠ **An unassignable live account is LISTED and DISABLED with its reason**, never hidden. Same rule the
Add-bot list follows: a destination that silently vanishes reads as a bug.

⚠ **`applied: false` on a 200 is a real outcome** on both applies — the bots already matched, or were
already on that account — and is toasted as that rather than as a write that happened.

⚠ **NO automated check on any of the three.** Playwright is out of the gate by design and these need
the app and the backend up; the backend talks to the live trading box, so booting it stays a person's
decision. Typecheck, lint, build and the three node checks are green. **What is unverified is the
RENDERING** — the behaviour is pinned backend-side. Drive them once with the app up.

### The three new screens were DRIVEN IN A BROWSER (2026-09-07) — and two are only half-covered

Rule 9 says a feature nobody has RUN is not a feature. These three shipped on 2026-09-07 without
anyone opening them, so they were driven against the real backend and the real trading box. **Zero
console errors on every page.** What was actually reached, and what was not:

✅ **Stack stress test — FULLY EXERCISED on a real shared stack.** The modal opens, and the
arithmetic it does before spending an hour is live: at 5 windows it read *"≈16 unseen trades
each"* and raised its own warning that under 20 the walk-forward returns no number and the grade
caps at B, *"Use 4 windows or fewer."* ✅ **The refusal was checked as a separate case and it
holds — the button is ABSENT on a screen stack**, which is the whole point: a screen is N
standalone runs added up and a letter grade on it would describe a result no account can produce.
✅ **The ruleset control's three-state was confirmed by USE**: choosing *"No ruleset"* stuck
rather than snapping back to the first option. That state is DERIVED rather than filled by an
effect precisely so nothing can overwrite an explicit choice, and this is the check that says so.

⚠ **Copy a graded stack's settings — THE STACK BRANCH RENDERED NOTHING, because no stack stress
test exists yet.** Only one stress test is stored on this machine and it came from a single run,
so the page took the run-sourced path. **What that DOES establish is the regression: the existing
single-run flow is unchanged** — the button still reads *"Copy settings to a bot"*, the modal
opens, all three bots list, and Apply stays disabled until one is picked. 🔴 **The stack half is
UNSEEN and must not be written up as working.** Reaching it needs a stress test actually run on a
shared stack, which is an hour of compute and needs the platform idle.

⚠ **Take live — the refusal was verified 2026-09-07; the PANEL BODY on 2026-09-10**, with both bots
mocked stopped and the preview served in the browser only (the apply was aborted in the page):
picker, from/to, moving list, details and phrase all render, and *Move to live* enables only on the
exact phrase. 🔴 **The real move has still never run** (rule 9) — that needs both demo bots stopped,
which is Aaron's call.

⚠ **The honest generalisation: opening a page proves the page, not the branch.** Two of these
three have a second path that only appears when data or state this machine does not have exists,
and a green first path says nothing about them — the same rule the parity gates state about a
branch neither side entered.

⚠ **The browser MCP is pinned to port 5173 by an explicit origin allowlist** (`.mcp.json`), so a
dev server that lands on 5174 because 5173 is taken is unreachable and fails as
`ERR_BLOCKED_BY_CLIENT` — which reads like the guard refusing the app rather than the port being
wrong. ⚠ **And Vite binds `localhost` as IPv6 here**, so `curl 127.0.0.1:5173` answers nothing
while the server is up and serving; probe `http://[::1]:5173`. **Both of those cost time and
neither is a defect** — write them down rather than rediscovering them.

## Both run forms offer 1 minute, and the single run opens on the measured frame (2026-09-22)

The single-run form's bar list for a python or MT5 strategy was 5m and up, so FFT (1m only) could
not be asked for its own frame and every run of it read 0 trades. It now offers 1m, opens on the
frame the strategy states it was measured on, marks that option "· measured", and always lists it
even when it is not a preset. A strategy that states none keeps the old default. The stack form's
list gained 1m too: FFT's leg already defaulted to 1, but with no 1m option the select DREW 5m
while the leg sent 1. Pinned in `tests/run-bar-size.spec.ts` (real backend, never presses Run),
both tests watched red against the old form.
