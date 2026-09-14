# Notes — The instrument picker

The broker-driven instrument search and recents list, and the defects found building it. Moved VERBATIM out of `command-center/frontend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The instrument picker — the broker's OWN list, searchable, with recents (2026-09-07)

`components/InstrumentPicker.tsx`, driven by `useBrokerSymbols`, over the pure
`lib/instrumentSearch.ts` + `lib/instrumentRecents.ts`. Used by the Run modal AND the stack builder.
Backend rules and the three-state: `../backend/CLAUDE.md` → *The broker's own instrument universe*.

🔴 **IT REPLACED TEN SYMBOL NAMES TYPED INTO `RunBacktestModal`, AND THEY WERE THE WRONG BROKER'S** —
Vantage's spellings while the lab sat attached to PU Prime and its **1,085 instruments**. Every
share, ETF, index, bond and crypto pair that terminal carries was unreachable from the form. The
stack builder had no suggestions at all.

⚠ **Still an INPUT, never a select.** A dropdown is the right way to browse 1,085 names and the
wrong way to enter the one you already know.

🔴 **NO HARDCODED DEFAULT ANY MORE** (Aaron, 2026-09-07: *"no default, just a recents"*). The gold
fallback is gone; the STRATEGY'S own suggestion stays, because that is data about the strategy rather
than a guess. Empty is legitimate and the Run button already refuses it.

🔴 **THE BROKER REWRITE STANDS DOWN FOR A NAME THE TERMINAL ITSELF QUOTES, and that fixes a defect
the rewrite had for its whole life.** It strips at the first dot and appends the profile's suffix
unconditionally — right for the 64 forex and metal names PU Prime spells with one, WRONG for the
other 1,021: `AAPL` became `AAPL.p`, `TSLA.24H` became `TSLA.p`. Nobody had hit it because the form
only ever offered ten currency-and-metal names, **so opening the broker's real universe would have
walked straight into it.** ⚠ **The test is a MEASUREMENT (`isQuotedVerbatim`), not a memory of what
the reader clicked** — a "they picked it" flag is right until somebody types, pastes or returns to a
restored form. ⚠ **An unavailable universe falls back to rewriting**, so an unreachable terminal
changes nothing rather than quietly switching the form to a second set of rules.

🔴 **RECENTS ARE BUCKETED BY SERVER.** A recent is a click that FILLS THE BOX, so one from another
broker fills it with a name this terminal does not quote — the hardcoded-list failure arriving
through a convenience. ⚠ **An unknown server reads back NOTHING, never the last bucket.**
⚠ **De-duplication is case-insensitive but STORES what was passed** — `Nikkei225.s` is not
`NIKKEI225.S` to MT5.

🔴 **THE BOX ONLY BLANKS ITSELF WHEN THERE IS A LIST TO FILTER, and that was found by focusing the
real field during a real agent outage.** Focusing swaps the value for the query so you can search
over it — fine while the dropdown is open, because the current pick is on screen with a tick beside
it. With the terminal unreachable there IS no dropdown, so the same blanking left an empty box with
nothing anywhere saying what the run was set to. ⚠ **The value was never lost either way**, which is
what makes it the dangerous kind of wrong: it looks cleared and it is not.

🔴 **AN EMPTY QUERY KEEPS THE SERVER'S ORDER AND IS NOT RANKED — FOUND BY OPENING THE THING.** The
backend orders the universe liquid class first; ranking an empty query flattened every symbol to one
tier and handed the list to the length tie-break, so the panel opened on `A`, `AA`, `AC`, `ABT` —
the shortest US share tickers on the terminal — for somebody running a gold strategy. **Every rule
involved was individually correct and the composition was useless.**

⚠ **A restricted symbol is listed and marked, never hidden** — its history is still replayable.
⚠ **A truncated list says how many it hid**, because that and a genuinely short one look identical
and only one means keep typing.

✅ **`scripts/check_instrument_search.mjs` — 31 cases, step 11 of `../../scripts/run_all_tests.sh`,
needs nothing running.** 🔴 **SIX mutations survived across two passes and every one was FIXED
rather than documented away** — three because the fixture had no symbol of the shape that separates
two tiers (it does now: `TSLA` / `TSLAUSD` / `TSLA.24H`, and a disabled `EURUSD` beside a tradable
`EURUSD.p`), and three because a later fix REROUTED their cases onto a path the mutation could no
longer reach. **A fix that reroutes a case can silently un-cover the branch that case used to
exercise, and re-running the whole map is the only thing that shows it.** ⚠ **One branch was DELETED
rather than covered** — a ranking tier that was unreachable by construction, which reads to the next
reader as a covered branch. ⚠ **The fixture is cut from the live terminal and sorted exactly as the
backend serves it**; in any other order it would pin an order the server never sends.

🔴 **ONE DROPPED REQUEST BLANKED THE WHOLE PICKER, AND IT WAS REPORTED FROM THE SCREEN OVER A
TERMINAL THAT WAS CONNECTED THE ENTIRE TIME (2026-09-07).** The form showed *"Could not read the
broker's instrument list"* plus *"nobody has recorded how this account spells its symbols"*, and the
broker had fallen back to the cent account — three faults reading as three problems, all caused by
one blip on the identity probe. The cause and the fix are the backend's; what this file owes is the
rendering rule. ⚠ **A remembered list must never pass as a fresh one**: when the served universe is
`stale`, the caption names the TIME it was read and the ACCOUNT it came from, both inside the
dropdown's footer and under the input, because the one real hazard is that the terminal moved during
the gap and an account number in front of the reader is what lets them notice.

⚠ **The broker's fallback when nothing is attached is the FIRST profile, which is a pre-existing
behaviour this feature made loud.** It lands on the cent account — a different contract size, and
the one profile with no recorded symbol spelling, so it produces a second warning that looks like an
independent fault. **Worth fixing at the source rather than captioning here.**

⚠ **The populated dropdown was driven in a browser with the real payload injected** (12 chips with
real counts, the 60-row cap, the footer naming the terminal) **and the unavailable path was driven
against a real outage.** Story: `../docs/FRONTEND_BUILD_NOTES.md`.

### 🔴 The dropdown had NO BACKGROUND, because a colour that does not exist is a colour that is transparent (2026-09-07)

Reported from the screen — *"the ui has bugs"* — with a screenshot of sixty instrument rows drawn
straight over the form underneath, every line tangled with the settings behind it.

**The panel read `bg-bg-raised`. There is no such colour in this theme** — the palette is
base / sunken / surface / surface-2 — and **Tailwind DROPS a class it cannot resolve without a
word**: no build error, no console warning, no failing test. The same file also carried
`hover:text-danger-text` (the colour is `neg-text`), which did nothing and read as a hover somebody
chose not to style.

⚠ **A colour that does not exist and a colour deliberately set to transparent are THE SAME THING on
screen**, so nothing in the running app can tell you which one you wrote. That is rule 7 arriving in
CSS: a class name is a CLAIM about a definition somewhere else, and nothing was checking.

✅ **Gated: `scripts/check_theme_tokens.mjs`, step 12 of `../../scripts/run_all_tests.sh`, needs
nothing running.** It reads the palette out of `tailwind.config.js` rather than from a list typed
into the check — a second copy of the colour names would go stale in the direction that matters, so
a colour ADDED to the theme would start failing. ⚠ **It judges only classes unambiguously naming a
theme colour** (first or last segment matching the palette's own naming), so `text-left`,
`border-t`, `bg-black/60` and `text-[11px]` are never candidates; a check that fires on healthy code
is one people learn to dismiss. ⚠ **It carries a SELF-TEST** — without one, "no findings" means *the
app is clean* and *the scanner is broken* at the same time, which is the exact defect it exists to
stop.

🔴 **It found THREE MORE, live, in pages nobody suspected**: `bg-bg-elevated` (BacktestDetail ×3,
ConfigureTab), `text-gold-bright` (ConfigureTab ×2) and `bg-bg-surface2` — a missing hyphen — on
StrategyDetail. **Every one had been invisible for as long as it existed.**

⚠ **Nine mutations, nine killed, and the map was RE-RUN after a tenth was deleted.** One guard
(rejecting arbitrary values like `text-[11px]`) **no mutation could kill** — the single-word rule
already rejects every one of them and removing it changed not one finding across all 108 files — so
it was DELETED rather than left in. **A branch nothing can kill reads to the next person as a
covered branch**, the same call made for the ranking tier in `check_instrument_search.mjs`.

### 🔴 The recents row moved BELOW the input, because it shares a grid row (2026-09-07)

Reported in the same pass: *"after selecting everything goes out of sync."* Instrument, bar size and
period are three columns of ONE grid aligned at the top, so a chip row appearing ABOVE the input
shoved this field's box ~30px down while its two neighbours stayed put. **Picking a symbol knocked
the row out of line, at the exact moment of the pick, so it read as the form breaking on the click.**

⚠ **A control that CHANGES HEIGHT must grow DOWNWARD when it shares a row.** Anything added above it
moves the control itself, and the reader's eye is on the control. ✅ MEASURED after the fix: all
three controls at `top: 225`, the chip at 265.

⚠ **And the box now shows the current pick as its PLACEHOLDER while filtering.** Focusing blanks the
field so you can search over it; with the pick only visible as a tick on a row scrolled out of view,
the field read as empty. The value was never lost either way, which is what made it the dangerous
kind of wrong.

### The Stress Test button asks BEFORE it offers itself (2026-09-07)

It was offered on stacks that cannot be graded, and **the page had no way to know**: the stack
reported 272 combined trades and its contention data as available, so every check available here
PASSED. What was missing was a file only the backend can see. The reader clicked, waited, and got
a 400 — the exact failure the modal's own sample-floor check exists to avoid, arriving through a
precondition the modal never knew about.

✅ `useGradable` asks the server, and the button disables itself carrying **the server's own
sentence**, verbatim. A reason invented here would be a second opinion about a stack somebody is
about to spend an hour on, and the copy that goes stale is always the one the button reads.

⚠ **Asked only of a shared stack that has FINISHED.** A running one is not gradable yet for a
reason that stops being true on its own, and saying so mid-replay reads as a verdict on the stack
rather than on the clock.

⚠ **`staleTime: 0`** — a stack becomes gradable when its replay lands, so a cached "no" would
outlive its reason.

⚠ **It was checked in BOTH directions**, and that is the half that matters: disabled with the real
reason on a stack with no combined book, **enabled with no reason on one that has it**. An
always-disabled button passes the first check on its own and looks identical.

### A stack's setting nudges can be SKIPPED, and the page says so (2026-09-10)

The server skips a stack's setting nudges when its bots cannot compete for risk (rule and evidence:
`../backend/CLAUDE.md` → *A stack's setting nudges run ONLY when its bots can compete for risk*).

⚠ **`RunStackStressTestModal` still SENDS `include_sensitivity: true`** and states the rule in
words; it carries no copy of the check. The evidence lives on the server, and a second copy here is
how the page and the run come to describe different tests.

🔴 **A skipped phase is never simply absent.** Dropped from the pipeline, it would draw exactly like
a test where nobody asked — so `StressTestDetail` shows a Sensitivity step marked *Not needed* (its
own icon: a tick says it ran, an empty circle says it is still to come) with the server's sentence
under it (`sens-skipped`). ⚠ **A graded test already carries that sentence in its grade reasons**,
so the reasons card adds it (`sens-skipped-reason`) only when there are none — a test graded against
no ruleset would otherwise say nothing, and a second line would say it twice. ⚠ **And only once the
test has STOPPED running**: mid-run the line under the steps already says it, and a card headed
*Why this test is not graded* over a test that has not reached its grade reads as a verdict.

⚠ **No Playwright check** — out of the gate by design. Typecheck, lint and the theme check are
green; the backend half is pinned by 22 tests and 26 killed mutations.
