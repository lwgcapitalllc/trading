# `execution/` — the one vocabulary a strategy and a broker both speak

**Purpose:** so a trading feature is built ONCE and both the backtest and the live bot get it.
**Status:** stage 2 of 3. The contract exists and the strategy SPEAKS it; **nothing consumes it yet.**

---

## Why it exists

The strategy logic in this repo was already shared — the live bot imports the same package the
lab replays, and the engines are canonical. **Execution was the layer that never got that
treatment.** The strategy decided AND booked its own fill in one step, and
`algos/live/bridge.py` separately re-derived what the position ought to look like so it could
make the broker match.

🔴 **That mirror is why a new order shape was two builds**, and it is measurable rather than a
matter of taste: the bridge carries **six refusals**, each one *"the strategy can do this and the
live path was never taught it"*. Scale-in is one of them — which is why a stack measured with
add-size on cannot be put on a bot without either building the add path or turning the setting
off.

## The split

  * the **strategy** decides — what to open, where the stop goes, how much to bank;
  * an **executor** carries it out — a simulator against bars, or a broker over the wire;
  * an **account** sizes it, and may refuse.

Nothing in `intents.py` knows what a bar is, what MetaTrader is, or what a lot is.

⚠ **Quantity is in the STRATEGY's units, never lots.** Converting to a venue's lot count needs the
broker's balance, its volume band and the account's remaining risk — none of which a strategy can
see. That conversion stays at the one sizing seam it already lives at, on the executor's side.

## The two halves, and why they are separate types

🔴 **An intent is what was ASKED FOR; a fill report is what HAPPENED.** A backtest fills what it
asks for, so the old design let the strategy assume its own fill and move on. A broker can refuse
or partly fill — **and the old design had nowhere to put those two answers**, which is most of
what the live layer existed to paper over. With the answer travelling back through the same seam
the request went out on, both sides say it the same way and the strategy handles it once.

⚠ **A partial fill is not an error.** It is the honest answer to a request the venue could only
partly meet, and a strategy must be able to hold less than it asked for.

⚠ **`filled_qty = 0` with no reason REFUSES AT CONSTRUCTION** — rule 1 where it matters most.
A silent zero is indistinguishable from a refusal nobody recorded.

## The vocabulary was MEASURED, not designed

Four kinds: open, add, close-portion, move-stop. **That list came from counting what the shipped
strategy actually produces** — three fill sites (an entry, a partial exit, the banking of its
added lots) plus a stop it re-states each bar. A vocabulary invented from imagination would be
wrong in both directions: kinds nobody implements, and the one real case missed.

⚠ **`ADD` is deliberately not `OPEN`.** An add is more size on a position that is still open,
sharing one ratcheting stop; an open starts a trade. Collapsing them is the confusion that made
the live path look as though a re-entry's slot could serve a scale-in. It cannot.

## Where this is going

1. ✅ **The contract** — this module. Tested, 15 cases, three watched RED by mutation
   (the rule-1 guard, the frozen intent, the direction check), each killing exactly one test.
2. ✅ **The strategy SPEAKS it** — every decision now carries the orders it would place,
   alongside the booking it already did, **all four kinds including the add**. Nothing reads
   them yet, by design.
3. ⬜ **The live bridge consumes it** — refusals retire one at a time, add-size first.

🔴 **Stage 2 was deliberately made SMALLER than first written down, and the reason is worth
keeping.** The plan said *the simulator consumes it — the strategy stops booking inline*. That
is a rewrite of a working emulator, and its failure mode is a moved book. **Emitting alongside
cannot move a book at all** — the emission adds to a reporting field and reads nothing back —
so it makes the stream REAL and provably free before anything depends on it. It also unblocks
stage 3 without putting the shipped emulator through a rewrite first, which matters because
stage 3 is the one that pays: it is what lets a stack measured with add-size on reach a bot.
⚠ **The inline booking is therefore still there and still authoritative.** Retiring it is a
separate change with its own proof, and calling stage 2 "the simulator consumes it" would be a
label claiming code somewhere else — rule 7, in a doc.

## What "speaks it" means, precisely

The strategy appends its orders to the decision it already returns. Four sites, and they were
found by reading the code rather than by listing what a strategy ought to do: an entry, the
banking of added lots, a partial exit, and the stop.

🔴 **The stop is the one that is NOT a mirror of an existing fill, and it is emitted only when
it MOVES.** The strategy re-states its stop every bar because a backtest is happy to be told
the same number forever. A broker is not: restating it is a real order-modify on the wire every
bar, for the life of the trade. **The change is on this side of the seam on purpose** — if the
live executor had to remember the last stop to filter repeats, that memory would be a second
copy of position state, which is the exact thing this whole exercise is removing.

⚠ **The remembered stop is cleared where the position is cleared**, not on a timer. A stale one
would swallow the first real move of the NEXT trade — silently, and only sometimes.

## The add was the one kind nothing produced, and it took a hunt to notice

🔴 **`ADD` sat in the vocabulary unemitted, and the reason is structural rather than an
oversight.** The emission sites were found by reading what the strategy appends to its FILL
list — three of them. **An add is separate LOTS and never reaches that list**, so a reader
counting fills concludes this strategy does not scale in, and a live path built from fills
alone would trade the base position and say nothing. That is the precise divergence the
bridge's scale-in refusal exists to prevent, and it would have been rebuilt here.

⚠ **The vocabulary being MEASURED is what saved it.** `ADD` existed because the config has a
scale-in setting, not because a fill site produced one — so the gap showed up as a kind with no
producer. **A vocabulary derived only from what the code emits would have had no `ADD` at all,
and nothing would have looked wrong.**

## 🔴 The hazard stage 3 must not walk into: a stop that is right and too small

**An add fills. The stop price has not moved. No `MOVE_STOP` is emitted** — correctly, because
the stop is emitted on change and it did not change. **The broker's stop order now covers less
volume than the position holds**, and nothing in the stream says so.

⚠ **Every symptom points the wrong way.** The stop price matches, the position size matches the
strategy's, and the two books agree on every number a reconciler compares. The only thing wrong
is the protective order's VOLUME, which is not a number either side is currently comparing.

**Whoever consumes this must reconcile the stop's volume on an `ADD`, not just its price.** It
is written at the emission site as well, because a rule that lives only in a design doc is a
rule the next person does not read.

## The evidence stage 2 actually stands on

  * **The book did not move.** Stack `st_631986bbd9` replayed: 272 trades, 223.3339464065 R,
    sha256 identical to `.baseline/`.
  * **The decision stream did not move.** `compare_strategy.py` output is **byte-identical to
    HEAD** on all four full-config exports — including each one's cold-start divergence, which
    is the part that would have shifted had anything real changed.
  * **Green where it is meant to be green:** exit 0 on all four exports at `--warmup 100` and
    `1000` (`2a817` also at 200 / 500). 626 tests pass.
  * **Each new test was watched RED by mutation, one mutation per claim.** Deleting the add
    emission, attaching a stop to it, and instructing an add that never filled each redden their
    own named test.

🔴 **One of those mutations was MIS-ANCHORED on the first pass and the whole set looked fine
anyway.** It was aimed below the check it claimed to test, so the unfilled-add case survived
every mutation in the run — **unproven, while sitting in a report that said three of three
killed something.** A mutation map is only worth what its anchors are: check that each one can
actually reach the branch its test names.

⚠ **Read those three as one claim with rule 14 attached: they say the new stream costs nothing,
never that it is RIGHT.** Nothing consumes it, so nothing can yet prove it useful — that is
what stage 3 is for.

🔴 **Running the gate at its DEFAULT is running it wrong, and it cost a detour here.** With no
warm-up all four exports diverge at bar 16, which reads exactly like a regression and is cold
start — documented, and true before this change as much as after. **The warm-up ladder is the
invocation; the bare command is not a weaker version of it, it is a different question.**

🔴 **The bar for every stage is the same and it is absolute: the stored book does not move.**
Baseline captured before any of this began — stack `st_631986bbd9`, **272 trades,
223.3339464065 R**, sha256 `92e08806eff5a915…` over the full trade list. A stage that cannot
reproduce it exactly is reverted, not explained.

⚠ **The baseline file itself is machine-local and deliberately NOT committed** — it is a derived
275 KB replay of one stack, and a stored copy would rot silently the first time that stack's
settings were edited. **The three numbers above are the claim; the file is only a convenience.**
Rebuild it by replaying the stack and hashing its trade list — resolve the stack's settings and
legs, run the portfolio replay with the solo control off, then hash the trades sorted by field.
⚠ **It is reproducible only while stack `st_631986bbd9` still holds the settings it held on
2026-09-07.** If it has been edited since, this baseline describes a stack you no longer have,
and the honest move is to re-cut it and say so — never to compare against it anyway.
