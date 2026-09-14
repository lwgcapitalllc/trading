# Notes — The Run modal and stack-form settings

The Run modal's costs switch and broker defaults, the re-price control, and the stack form's per-leg timeframe, broker and account-first redesign. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The Run modal's Costs section is ONE SWITCH, on by default (2026-08-24)

Five tickboxes with everything off became one toggle. **The switch sits OUTSIDE the collapsible
fold** — a run's single most important physical fact must not be one click away behind a collapsed
heading, which is how every run ended up frictionless without anybody deciding to.

- ⚠ **It sends a BOOLEAN (`charge_costs`), never a layer list.** The policy lives on the side that
  charges it (`python_runner.charged_layers`), or the page and the run can describe different
  physics — rule 7, a label is a claim about code somewhere else. `cost_layers` is sent as `null`.
- ⚠ **`chargedRows` is a DISPLAY of that policy, not a second copy of it.** If `CHARGED_LAYERS`
  gains a layer, this list gains a line. Every figure on it is read off the served broker profile
  and never retyped.
- ⚠ **Costs OFF renders a warning, not a neutral state.** *"A diagnostic only — it answers how much
  of the edge is friction, never whether the strategy works"*, plus a line saying real fills change
  which setups exist, not just what they pay. The summary reads `GROSS — no costs charged`.
- ⚠ **A tier with no measured spread DISABLES the Run button and says why before the click.**
  The backend refuses it with a 400; a refusal arriving after a click is the answer in the wrong
  place. `brokerUnpriced` is `spread < 0` — the profile's refusal sentinel.
- ⚠ **Slippage keeps its own typed opt-in and its "a guess" tag inside the fold.** It is the only
  cost here nobody has measured, and folding a guess in beside three measurements makes them
  indistinguishable on the page.


## The Run modal's broker DEFAULTS to the attached terminal (2026-08-24)

🔴 **`useState('vantage_demo')` was the defect.** The bar cache is partitioned per broker, so bars
can no longer mix — but a hardcoded cost profile meant pointing the lab at PU Prime charged Vantage's
spread over PU Prime's bars. Same mixed basis one level up, and just as quiet.

- ⚠ **The state starts `null` and an effect fills it once**, so nothing is submitted against a
  guess and the reader's own choice is never overwritten. Submit is blocked while it is null on a
  charged python run — omitting the field would fall through to the request model's default, which
  is a broker nobody picked.
- ⚠ **`brokerMatches` is THREE-state.** `null` means the agent could not be asked, and must render
  as *cannot tell* rather than as a mismatch — the same rule the MT5 health dot follows.
- ⚠ **It warns and never blocks.** Comparing against a broker you are not pointed at is a
  legitimate deliberate act.
- ⚠ **No fallback picks a broker when nothing is attached** — it takes the first profile only so
  the select has a value, and the *cannot tell* note is what the reader acts on.

## The Run modal: BROKER first, and it rewrites the symbol (2026-08-26)

A strategy suggests a bare `XAUUSD`; PU Prime quotes gold as `XAUUSD.p`. Switching broker and not
the symbol produced an empty bar frame minutes into the run. **Switching broker now rewrites the
instrument field itself**, and the broker select moved to the TOP of the form.

- 🔴 **The broker select is the FIRST control, above Instrument.** It used to sit inside the Costs
  block, which read as though it only decided what a run was CHARGED — while it also decides which
  broker's bars are replayed and now how the symbol is spelled. **A control that silently rewrites
  a field ABOVE it makes no sense to anybody**; cause before effect and the rewrite explains
  itself.
- 🔴 **It rewrites the FIELD, never captions it.** The first version left `XAUUSD` in the box with
  *"puprime_ecn quotes this as XAUUSD.p"* beneath — rule 7 in miniature, a label claiming what some
  other code will do. **The box is what the reader believes, so the box is what has to be right.**
- ⚠ **Keyed on the BROKER only, not the symbol** — rebasing per keystroke would append a suffix
  before somebody had finished typing the base. Switch broker and it rewrites; type and it leaves
  you alone.
- ⚠ **An EFFECT, not the select's `onChange`, and it must stay one.** onChange would silence the
  `set-state-in-effect` warning it trips (one of five here; the rule is at warn on purpose) but
  only fires when a HUMAN picks a broker. The broker also arrives on its own when the profiles load
  and the default lands on the attached terminal — the common case, open and press Run — and an
  onChange-only version leaves a bare `XAUUSD` under a PU Prime selection, which is the bug.
- ⚠ **Display only — the BACKEND binds.** `python_runner.run_symbol` resolves again at run creation
  and stores the result, so a hand-typed bare name is still corrected. This half makes the answer
  VISIBLE; it is not what guarantees it.
- ⚠ **A null suffix is UNRECORDED, never bare.** The symbol is left as typed and a note says nobody
  recorded that broker's naming — silence there would read as "bare", which is a guess.
- ⚠ NT8 keeps its own `Submits as:` line and contract-month logic, untouched.

Story: `HISTORY.md` → *The broker that spelled gold differently*.

## The re-price control dies on a charged run, and a PAIRED RE-RUN replaces it (2026-08-24)

🔴 **Re-pricing is strictly ADDITIVE — the server can only charge a layer the run did not.** Since
the charged default an ordinary run already carries every re-priceable layer, so every row renders
already-on and priced at zero and the pill's only possible outcome is *no change*. **A control that
can never change anything is indistinguishable from a broken one**, and the reader has no way to
tell which they are looking at. It renders only while `costs.spent` is false.

🔴 **And no arithmetic could bring it back.** The charged default transacts at the bid/ask, which
changes WHICH setups fill — 161 trades → 159, with four setups that never existed on the free path.
No pass over a stored trade list can invent a trade the list does not contain, so **the free twin of
a charged run is a RUN, not a subtraction.** That is why `CostPairButton` is a button.

- ⚠ **It fires a NEW run** (`useTriggerBacktest`), never `useRetryBacktest` — the retry path clears
  the run directory and discards the result, and the pair has to sit side by side to be worth
  anything. `source_run_id` links them.
- ⚠ **Everything except the cost switch is carried across** — rule 11. A twin differing in a second
  field turns the difference column into the thing that lies.
- ⚠ **`cost_layers === null` gets NO twin.** It means the run predates the layer contract, which is
  not `[]` and is not a claim about what it charged that a twin could be built on.
- ⚠ **`costs.spent` is derived from the SERVER's `already_charged`, never from what a layer set
  implies.** `bid_ask_fills` pays the spread inside the fills and never names it, so a page-side
  guess would call a fully charged run half-charged and offer a row that DOUBLE-BILLS. The backend
  closes the same hole from its end — see `../backend/CLAUDE.md`.
- ⚠ **Two captions on the Made card moved with the default and had to.** "That is the default" over
  a frictionless run became false the moment charged became the default, and the fees tooltip
  pointed at a pill that is now hidden on the runs it described. **If a default changes, every
  caption asserting it changes in the same commit** — this folder already records that exact defect
  on the news filter's own control.

`tests/cost-switch.spec.ts` — 4 checks, all proven by mutation, and **two were VACUOUS first**: one
fixture carried two guards so a mutation of either left it green, and both no-twin checks passed
against a deleted guard because the Performance header had not rendered yet. **An absent header is
indistinguishable from a withheld button.** Positive control first, one guard per fixture.


## The stack form: one timeframe PER LEG, and the broker's own symbol (2026-09-03)

Both reported off one screen, both looked like display faults and neither was. The backend half —
what is stored, what is replayed, and why a dependent leg is pinned — is in
`../backend/CLAUDE.md` → *A stack leg runs on its own frame*, and is not restated here.

🔴 **THE TIMEFRAME BOX IS PER LEG, PREFILLED FROM THE FRAME EACH STRATEGY STATES IT WAS MEASURED
ON.** One box for the whole stack put a 5-minute bot on 15-minute bars beside a 15-minute one and
called the combined table a portfolio result.

- ⚠ **`legBar` holds only the reader's EDITS, never a seeded copy of the declarations** — the same
  shape as the per-leg risk box beside it. Seeded, it would go stale the moment a package's declared
  frame moved, and a rerun would then carry a frame from a strategy that has since been re-measured.
- ⚠ **`barByLeg` is the ONE expression that resolves a leg's frame** (edit → declaration →stack
  fallback), so the picker, the window check and the request cannot disagree about what a leg is
  about to be measured on.
- ⚠ **The window question asks about the FINEST frame in the stack**, because a broker holds less
  history the finer the bars. Asking about the coarsest clears a window the fine leg cannot reach,
  where the coarse leg compounds alone and sizes every later trade off a balance it built unopposed.
- ⚠ **A leg whose package declares no frame keeps the stack fallback** rather than being handed an
  invented number, and a leg running on something other than what it was measured on says so beside
  its name. **It is a DEFAULT, not a lock** — another frame is a legal run and simply a different
  experiment.
- ⚠ **A RERUN reads each leg's OWN stored frame** (`StackStrategyLeg.bar_value`), never the stack's
  single number — otherwise it quietly puts a 5-minute leg back on 15-minute bars and still says
  *rerun*. A leg stored before the column contributes nothing and correctly falls back to what its
  package declares.

🔴 **SWITCHING BROKER REWRITES THE SYMBOL IN THE BOX, and this form was the half left behind.** The
Run modal has done it since 2026-08-26; this form got its broker picker on 2026-09-02 and never got
the rewrite, so a stack under PU Prime carried a bare gold name that broker does not quote. The
rules are the Run modal's, for the same reasons, and are worth repeating only as pointers: keyed on
the BROKER and not the symbol (or it appends a suffix while somebody is still typing the base); an
EFFECT and not the select's `onChange` (the broker also arrives on its own once the profiles load,
which is the common case — open the modal, press Run); and **a null suffix is UNRECORDED, never
bare**, so the symbol is left exactly as typed and the form says nobody has recorded that broker's
naming. **The backend binds** — this is the half that makes the answer visible, never the half that
guarantees it.

### The redesign, and the control that changed nothing (2026-09-03)

Aaron, on the form above: *"the layout is really, really bad… things are not logically grouped…
make it the same size as the run strategy one… that way the two models don't feel dramatically
different."* It was 520px with every control stacked in one column, so nothing could sit beside
what it belongs with.

- **Same shell as the run modal** — 1180px, 92vh, header / scrolling body / footer — and the mode
  is a header BADGE rather than a sentence buried in a paragraph.
- **`ModalKit.tsx` is the shared kit** (`SectionHead`, `InfoTooltip`, `Divider`, `inputCls`,
  `labelCls`), extracted from the run modal and imported by both. ⚠ **Mirroring the styles by hand
  is what made them drift in the first place**, so a second copy is not the cheaper option here.
  ⚠ **Presentational only** — the moment one of these takes a run, a broker or a cost it stops
  being shareable and the copy comes back.
- **Broker, instrument and period sit on ONE row**, in that order, because the broker decides
  which bars are replayed, what is charged, AND how the instrument beside it is spelled. Those
  three were four sections apart with the strategy list between them.
- 🔴 **ONE LEG IS ONE ROW, carrying everything true of that leg** — its timeframe and its risk per
  trade, inline. The timeframe had its own section further down while the risk sat under the row:
  **the same leg's two settings in two places is how you end up reading a stack you did not
  configure.** ⚠ **The row is a `div` and only the NAME is the button** — an input inside a button
  is invalid markup and every keystroke would toggle the leg off, which is why those controls were
  exiled in the first place.
- ~~**The account and the costs are side by side**~~ — **superseded 2026-09-10**: the account moved
  above the strategy list and the costs sit alone at the bottom. See *The stack form: the account
  first* below.

🔴 **THE COMMISSION BOX IS GONE, AND IT HAD NEVER DONE ANYTHING.** `routers/_costs.py` reads
commission off the BROKER ACCOUNT and has ignored whatever was typed here since the cost switch
landed — so the field asked the reader for a number, showed it back to them, and changed nothing.
**That is rule 7 in miniature: a control is a CLAIM about code somewhere else, and this one was
false.** ⚠ **The value is still SENT**, because a rerun of a stack stored before that has to
reproduce the figure it was stored with. ⚠ **Slippage KEEPS its box** and now sits inside Costs
tagged *a guess*, exactly as on the run modal — it is the one cost nobody has measured, so charging
it is somebody saying a guess out loud, and folding it in beside three measurements would make them
indistinguishable.

⚠ **The Playwright checks for this form were NOT run** — they need the app and the backend up, and
they are deliberately outside the gate. The hooks they grab were preserved deliberately
(`stack-mode-blurb` and its two phrases, `stack-broker` with its select, `stack-costs` with its
switch and three messages, `stack-account-fields`, `recovery-toggle`, the `e.g. XAUUSD`
placeholder, and each leg's name still being a button). ⚠ **`openModal`'s
`ancestor::div[3]` locator in `stack-config.spec.ts` is dead** — nothing reads its return value —
so the new nesting cannot break it, but **a positional locator that survives only because nobody
uses it is one edit away from failing**, and a `data-testid="stack-modal"` now exists to replace it.

## The stack form: the account first, every number typed, a list that holds still (2026-09-10)

Aaron: *"the shared account's risk cap, the balance and the entry floor… should be at the top…
right after the broker information, but before the strategies… I don't like the browser default
thing with an arrow up and an arrow down. Just let me freeform enter digits… if I selected
strategies before I hit stack, let those be at the top… after that, if I start toggling, everything
stays where it is… the percentage field is not wide enough."*

- 🔴 **The shared account sits between the broker row and the strategy list**
  (`stack-account-fields`, shared mode only), because the cap is the budget every leg's risk is read
  against — setting it after the legs asks the reader to budget backwards. The costs sit alone at
  the bottom.
- 🔴 **Every number on this form is a `DecimalInput`, never `type="number"`.** The spinner ate the
  room the digits needed, and a mouse wheel over a focused box silently moved a risk figure. It
  shows exactly what was typed while focused and the committed value otherwise (grouped for the
  balance) — derived on render, so a rerun's prefill always reaches the screen.
- ⚠ **An empty box is `null`, never 0, and it BLOCKS Run with its reason under the box** — a
  cleared risk box read as 0 would run a leg that can trade nothing, with nothing on screen saying
  so. Same for the balance, the cap, the floor and slippage (*0 charges none* is typed, never
  assumed).
- ⚠ **The list order is frozen at OPEN** (`arrivedWith`, read once from the prefill — a rerun, or
  the rows ticked on the Strategies page): those legs go first, and ticking afterwards never moves a
  row. Sorting on the live selection makes a row jump out from under the pointer mid-click.
- The risk box is 128px — room for `12.5` and its `%`.
- 🔴 **The legs' risk may not add up past the cap, and the TOTAL is the backend's**
  (`useStackRiskBudget` → `POST /backtests/stacks/risk-budget`, shared only). A row under the risk
  column reads *N% of M% cap*, the backend's sentence goes under it when the legs do not fit, and
  it counts the loss recovery (a quarter of its parent by default). ⚠ **Never summed here** — the
  Bots page once added its shares in the browser with `?? 0` and printed a total that fitted while
  the save was refused. The launch refuses with the same function, so page and 400 cannot disagree.
- 🔴 **Run needs a CURRENT "fits".** An answer counts only while its body matches the numbers on
  screen (`budgetFresh`): inside the debounce the cached answer describes the PREVIOUS numbers, so
  a "fits" for 5% would enable Run on a box just typed to 50. Pending, stale and failed all block
  — *could not ask* is not *fits* (rule 1).

✅ **`stack-config.spec.ts` ran 10/10 against the running app**, and each of the three new specs
was watched RED by mutation — the order sorted on the live selection, the keystroke filter removed,
the empty-risk-box block removed. **The budget added four more (14/14), each red by mutation**: the
gate dropped from Run, the check asked without the leg overrides, the freshness check dropped, and
a failed check read as fitting. ⚠ **The fixture's SOS Fade default is 5%, not 10%** — the mock
answers "fits" by default, and a fixture whose own legs do not fit would describe a rule that is
not there. 🔴 **The stale check first released its held answer before the request existed** —
*checking…* also shows during the debounce — so it now waits for the request to arrive. 🔴 **Seven of that file's specs could not have passed since
2026-09-07**: `fillForm` typed into the `e.g. XAUUSD` placeholder, which died with the instrument
picker. It now finds the picker's own placeholder and asserts a PREFIX (`/^XAUUSD/`), because in
the fixture the broker's suffix is not re-applied when the default instrument arrives after the
broker — the backend binds the suffix, per *the broker's own symbol* above.
