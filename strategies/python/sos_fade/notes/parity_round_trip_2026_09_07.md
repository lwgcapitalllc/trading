# Notes — The 2026-09-07 parity round trip

The full postmortem of the parity fixture pinned to a moved default, and everything it re-confirmed on the way (financing on scale-in lots, the re-entry trigger pin, the strategy's own stated intent, the add's order shape, and the deep-entry stop). Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 The parity round trip disagreed with ITSELF, because a fixture was pinned to a moved default (2026-09-07)

`test_compare_strategy.py` runs the bot, serialises its own decisions into an export-shaped CSV,
and feeds that back through the tool demanding identity. It went red on **8 of its 32 cases** —
`px_closed_r: py=2.2408 pine=2.8783` at bar 241, which reads exactly like a logic bug and was not
one.

**The encoder omitted the five scale-in columns the export Pine plots.** The decoder reads an
absent `cfg_scale_in` as OFF — deliberately, and explicitly NOT as a fall-back on the base config,
because the Pine shipped the feature off — so the fixture replayed a scaled book while the tool
replayed an unscaled one, and the diff blamed the strategy for the harness's own configuration.
It was harmless for as long as the Python default was also off; `exec_scale_in` moved off → on on
2026-09-06 and the file started contradicting itself the same day.

⚠ **The rule is the one the export Pine states about itself, and it cuts both ways: a
trade-affecting input with no `cfg_` column is invisible to the tool BY CONSTRUCTION — the gate
does not go quiet, it goes WRONG.** A fixture missing a column the Pine DOES plot fails in the
same direction. **A default that moves has to move every fixture pinned to it, and an encoder is a
fixture.**

✅ The five columns are encoded now, the round trip is clean on every config field, and the replay
genuinely places adds (2 across 6 closed trades on the synthetic window), so the gate walks the
scaled path rather than being green over an unexercised one. Watched RED by mutation.

✅ **`config.py`'s stale note is FIXED (2026-09-07).** It read *`exec_scale_in` OFF (the default)*
beside a line that says `True`. 🔴 **The reason it survived a day is worth more than the typo: the
pass that found it recorded *"no TradingView export is present on this machine"* and deferred on
rule 22 — and that was FALSE.** Four exports here carry all 26 `cfg_` columns including the five
scale-in ones; the gate is **exit 0 at warmups 100 / 500 / 1000 / 2000** on
`VANTAGE_XAUUSD, 15_b5eda.csv` (21,241 bars from 100 on). **An unchecked claim about what a
machine HAS is the cheapest kind to test and reads exactly like a constraint — one `find` settled
it.** That is rule 4 in the shape it actually appears: not a guessed number, a guessed capability.

⚠ **A comment naming another field's default is a SECOND COPY of that default**, and it goes stale
the moment the first one moves with nothing to fail. The note now says what the setting DOES and
lets the field declare its own value.

### Financing is charged on scale-in lots (2026-09-07)

🔴 **Every add rode overnight FREE until this date.** `_charge_swap` billed
`self._qty - self._filled_qty` — the BASE position — and an add is a separate lot that never
enters that number. A broker finances the POSITION, not the order that opened it, so a lot bought
on the way up costs exactly what the base costs to carry through the same night.

🔴 **The model that re-prices a finished run mirrored the bug, so the two AGREED while both
under-charged.** `backtest/reprice.py` reproduces a charged replay to 1e-5 on the exact layers and
0.05R on swap, it runs on every commit, and it was green throughout. **That is rule 14: a green
agreement check says the two MATCH, never that either is RIGHT.** Both sides were fixed in one
change; the reasoning and the mutation evidence live in `backtest/CLAUDE.md`.

**MEASURED**: the correction is **0.2024R** on the reference window (42 trades, 15 scaled) — the
swap layer moves `-1.6920R` → `-1.8945R`. ⚠ **Every stored number on a run that scaled in moves by
about that much, in the expensive direction.** Runs with no adds are byte-identical, so the whole
published history before scale-in shipped on (2026-09-06) is untouched.

⚠ **`_adds` is the LIVE ledger and `_add_lots` is what was BOUGHT.** A spent lot is zeroed IN
PLACE rather than dropped, so the ladder's cap keeps counting — which means summing `_add_lots`
finances lots that were already sold. `test_a_BANKED_scale_in_lot_is_financed_nothing` populates
both lists with DIFFERENT totals precisely so that mistake fails, and it was watched red by making
it.

⚠ **The timing is inherited, not re-decided.** `_charge_swap` runs before this bar's fills and
before its exits, so a lot bought this bar pays nothing for a night it did not hold and a lot sold
this bar pays for the night it did — the same rule `_qty - _filled_qty` already applies to the
base.

🔴 **THE PARITY GATE CANNOT SEE THIS, TWICE OVER, AND BOTH HALVES WERE CHECKED RATHER THAN
ASSUMED.** The gate builds the strategy with no cost profile, so `_charge_swap` returns at its
first line and no export can ever exercise a financing change; and **every export on this machine
ran `cfg_scale_in = 0`**, so it does not walk the add path either. It was run and is green at four
warmups, which establishes that the change did not move the entry or exit logic — nothing more.
**Financing on adds is covered by three unit tests in `tests/test_execution_ticks.py` and by the
reproduction check in `backtest/tests/test_reprice.py`.**

⚠ **Gating the scale-in path at all needs a fresh export taken with the feature ON.** That is a
TradingView action only a person can do, and until it exists the adds are covered by unit tests
and the lab, never by Pine parity.

### The re-entry trigger default moved too, and its pin had to move with it

`test_secondary.py` asserted the trigger ships as the reclaim alone. Both triggers ship together
since 2026-09-06 (Aaron's call, the same change). ⚠ **That test is a PIN on a default, so going red
is its whole job** — the answer is to read why it moved and re-state it, never to loosen it.

### The strategy now SAYS what it wants, as well as booking it (2026-09-07)

Every decision carries the orders it would place — an entry, the banking of added lots, a partial
exit, and the stop — in the shared vocabulary in `execution/`. **Nothing reads them yet.** The
inline booking is untouched and is still the thing that decides the book.

⚠ **This is an ADDITION, not a replacement, and the distinction is the whole safety argument.**
The emission appends to a reporting field and reads nothing back, so it cannot change a fill.
Retiring the inline booking is a separate change with its own proof; until then, calling this
"the emulator runs on intents" would be a label claiming code that does not exist — rule 7.

🔴 **The stop is emitted only when it MOVES, and that filter belongs HERE rather than on the
executor.** This strategy re-states its stop every bar, which a backtest absorbs silently and a
broker turns into an order-modify on the wire every bar for the life of the trade. Putting the
filter on the live side would mean the executor remembering the last stop — a second copy of
position state, which is precisely what this work exists to delete. ⚠ **The remembered value is
cleared where the position is cleared**, not on a timer: a stale one would swallow the first real
stop move of the NEXT trade, silently and only sometimes.

**PARITY: byte-identical to HEAD, which is a stronger statement than green.**
`compare_strategy.py` output matches HEAD character for character on all four full-config exports
— including each one's cold-start divergence, the part that would have shifted had anything real
moved. Exit 0 on all four at `--warmup 100` and `1000` (`2a817` also at 200 / 500). **Book
unmoved:** stack `st_631986bbd9` replays 272 trades / 223.3339464065 R, sha256 identical.

🔴 **RUNNING THE GATE AT ITS DEFAULT IS RUNNING IT WRONG, and it cost a detour to re-learn.**
With no warm-up all four exports diverge at bar 16 — `px_s_stage`, py=1 pine=0 — which reads
exactly like a regression and is cold start, true on HEAD as much as here. It is already written
down under the commanded-close section; it was found again the hard way because the bare command
looks like the honest one. **The warm-up ladder IS the invocation.** ⚠ **And a gate piped into
`tail` reports the pipe's exit code, not the gate's** — the first run of this looked like exit 0
on a mismatch.

**Tests: 3 in `tests/test_intent_stream.py`**, plus the whole existing suite as the regression
(623 green). ⚠ **Two more were written and DELETED for being unable to fail** — the note saying so
is in the file, because a test count is not evidence and a vacuous test is worse than a missing one.

🔴 **The shared test double for a decision was replaced with the REAL object, and that is the
durable half of this change.** It was a hand-rolled stand-in carrying two fields; production grew a
third and 51 tests broke at once. **They broke in the lucky direction** — an attribute error, not a
wrong number — but the same drift on a field the double happened to have would have passed. Rule 13,
arriving as a bill: the double was less capable than production, so it described a system nobody runs.

### The add is the fourth order shape, and it had no fill record to be found by

`_fill_pending_add` now states the lot it bought, in the same shared vocabulary as the entry, the
partial exit and the stop. It takes the bar's decision to say it on, which is why its signature
grew a second argument.

🔴 **IT WAS MISSED ON THE FIRST PASS, AND THE REASON GENERALISES.** The other three emission sites
were found by reading what the strategy appends to `dec.fills`. **An add is separate LOTS and never
appears there** — so anything built by counting fills concludes this bot does not scale in. A live
path built that way would trade the base position, place no adds, and report success. **That is
exactly the divergence the bridge's scale-in refusal is written against**, and it would have been
rebuilt one layer up.

⚠ **`dec` is REQUIRED on that call, never defaulted.** An optional one would let a future caller
drop the add from the stream in silence — the same failure, one level down.

🔴 **NO STOP TRAVELS WITH AN ADD, AND THE CONSEQUENCE IS A TRAP FOR WHOEVER CONSUMES THIS.** The lot
shares the position's one ratcheting stop, so attaching a stop here would be a second source of
truth for it. **But the stop is emitted on CHANGE only — so an add that fills while the stop price
is unmoved emits nothing at all, and a broker's stop order then covers less volume than the position
holds.** Every number a reconciler compares still agrees: same stop price, same position size. The
protective order's VOLUME is the one thing nothing is comparing. **Reconcile stop volume on an add.**

**Tests: 3 more in `tests/test_intent_stream.py` (626 total).** Each watched RED by its own
mutation — deleting the emission, attaching a stop to it, and instructing an add that never filled.
🔴 **The first mutation pass was MIS-ANCHORED and still looked clean**: it was aimed below the check
it claimed to test, so the unfilled-add case survived every mutation while the report said three of
three killed something. **A mutation map is worth exactly what its anchors are.**

**PARITY: byte-identical to the previous commit on all four exports at `--warmup 100`.** ⚠ **The
gate cannot see this change at all** — every export ran with scale-in off, so no export walks the
add path. What the green run establishes is that threading the decision through did not move the
entry or exit logic; the add emission itself is covered by unit tests and the lab, never by Pine.

### "Re-entries should bank nothing" is true of ONE half and expensive on the other (2026-09-07)

Aaron asked for two defaults to be confirmed before being made the rule. **One was confirmed, one
was half right, and the half that was wrong would have cost two thirds of a leg's edge.**

- ✅ **Bank nothing on the FAIR-VALUE-GAP re-entry.** Confirmed and shipped: the default moved
  50 → 0. Banking half returns +12.62R of re-entry contribution against +20.11R letting it run, on
  the same 205 trades and the same 47 re-entries — the bank COSTS 7.49R. Its target is near
  (1.25R), so half off caps the trades that were going much further and does nothing for the ones
  that fail.
- 🔴 **NOT true of the RECLAIM re-entry, which is measured the OTHER way.** Banking nothing there
  costs −13.84R of a +21.00R contribution. Its target is far out (3.25R) and the trade does not
  survive the retrace back from it. `exec_rec_tp1_pct` stays **100**.

🔴 **THE TWO HALVES READ SEPARATE FIELDS AND BOTH ARE LIVE UNDER THE COMBINED TRIGGER**, so a
sentence beginning *"re-entries should…"* cannot be executed as written — it names a behaviour that
has two independent settings with opposite best values. ⚠ **The pin now asserts BOTH**, so a future
edit tidying them into agreement goes red rather than costing the reclaim quietly.

⚠ **THE COST OF LETTING IT RUN IS CONCENTRATION, AND THAT IS WORTH SAYING OUT LOUD RATHER THAN
BURYING UNDER A BIGGER TOTAL.** With nothing banked, 15 of 54 re-entries finish flat. An earlier run
found banking half took a leg from −0.4R to +7.2R once its single best trade was removed — **but
that run was measured on the RECLAIM while the bot stated the gap**, which is exactly how the wrong
value came to be shipped. Read every pre-2026-09-07 robustness figure as the reclaim's.

🔴 **THE DRIFT RAN BACKWARDS ON THIS ONE, AND IT IS THE REASON TO CHECK BOTH SIDES RATHER THAN
ASSUME THE BOT IS BEHIND.** The live bot was ALREADY at 0 and correct; the DEFAULT was the stale
half. Every other setting on that bot was behind the defaults, so "sync the bot to the defaults"
would have made this one worse while fixing the rest.

**PARITY: byte-identical to the previous commit on all four exports at `--warmup 100`.** ⚠ **The
gate is structurally blind to this** — the exports carry no re-entry columns at all, because the
Pine has no re-entry, so neither side ever enters the branch. Rule 14 in its exact stated form.

### The deep-entry stop rule was confirmed too, and it was already right

Default **OFF**, and it stays off. Measured 2026-08-16: switching it on costs **24.0R with the
re-entry live and 23.0R without**, over a full 2×2 on one window. ⚠ **It does hold a shallower
drawdown** (−4.8R vs −5.5R), so it is expensive rather than worthless if drawdown ever becomes the
objective. **No code change was needed — but the LIVE BOT has it ON**, which is the single most
expensive drift found on that bot.
