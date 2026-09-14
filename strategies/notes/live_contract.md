# Notes — The live-capable strategy contract

How `strategies/python/live_contract.py` defines what makes any strategy live-capable — why it exists, what `verify_live_ready` does and does not check, how a package borrows from its siblings via `package_deps.py`, and how a strategy declares its `entry_style`. Moved VERBATIM out of `strategies/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## What makes a strategy LIVE-capable — the contract, not one bot's wiring

**`strategies/python/live_contract.py` (new 2026-09-03).** Read it before trying to make any
strategy a bot.

🔴 **Until this existed the live contract had no definition.** It was whatever
`sos_fade.execution.Execution` happened to implement, and a strategy became live-capable by
SUBCLASSING that class — which `b_leg`, `bos` and `realign` all do. That works for a strategy
shaped like SOS Fade and offers nothing to one that is not: `extreme_leg` is an independent
implementation, so it inherited none of it and could not be a bot at all.

🔴 **THE FAILURE MODE THAT HIDES IS THE REASON THIS IS A RULE.** `algos/live/` reads almost every
decision field through `getattr(dec, name, default)`, so **a field a strategy never sets is
indistinguishable from a field with nothing to report.** Omit the stop and the bridge never
ratchets the broker's stop — no error, no halt, no log line, and a position rides its original
stop while every dashboard stays green. **That is rule 1 in a new place, and a defensive read
cannot tell the two apart, so the distinction has to be made before the bot starts.**

⚠ **Of the thirteen decision fields, exactly TWO move money** — the stop the bridge ratchets and
the fills that book the trade. The other eleven are reporting. **An adopter's tests must assert
those two are POPULATED on a bar that should populate them**; asserting that a decision comes back
passes against an adapter that sets nothing.

⚠ **The contract lists are MEASURED off `algos/live/`, never remembered.**
`python/tests/test_live_contract.py` re-derives them from that source, so a live path that starts
reading something new goes RED here instead of going silent in a bot. **A hand-maintained list of
what the live path needs is a second implementation of the live path.**

⚠ **`verify_live_ready(strategy)` checks PRESENCE, never correctness.** It turns "AttributeError
somewhere in the bar loop at 3am" into "refused at startup, by name". That is worth having and is
not the same as being proven — rule 9 still applies to every adopter.

⚠ **SOS Fade satisfies the contract WITHOUT importing it, and a test asserts exactly that.** It is
the independent witness that keeps this module honest: anything the contract demands that the live
bot does not provide is something the live path demonstrably does not need. **It is deliberately
NOT being migrated onto the shared decision class** — that would change the strategy currently
trading, for tidiness.

⚠ **`_POSITION_FIELDS` is the WHOLE open-trade state and a missing entry is SILENT.** The record
round-trips, the bot restarts, and the omitted latch returns at its class default — so a trade
already moved to breakeven is managed as though it never was. Pin it with a test comparing the
list against what the class actually assigns while a position is open. **Restore REFUSES an
incomplete record rather than defaulting, and that refusal is the safety property.**

### A package may BORROW from its siblings, and `package_deps.py` is what makes that survive a deploy

**`strategies/python/package_deps.py` (new 2026-09-04).** Borrowing is normal here — `b_leg`,
`bos` and `realign` all build on `sos_fade`, `extreme_leg` takes one class from it plus the shared
live contract, and `sos_fade` itself takes `loss_recovery`. The imports are BARE NAMES resolved by
a `sys.path.insert` pointing at `python/`, so in the repo they simply work and **nothing anywhere
recorded that a dependency existed.**

🔴 **A live bot does not run from the repo — it runs from a frozen snapshot built out of ONE
strategy directory, so a snapshot for any borrowing bot could not import.** This module walks the
imports and answers with the closure; the deploy tool and the lab's version count both call it.
The deploy story, the pin gap it exposes, and what it does to a bot's version number are in
`algos/CLAUDE.md` → *A snapshot carries what the package IMPORTS* — not restated here.

**What it means when you write a strategy:**

- **Borrow freely from a sibling package or a loose module here.** It ships now.
- ⚠ **A file that will not PARSE stops a promote**, by name. That is deliberate: the alternative
  is a partial answer and a snapshot that does not import.
- ⚠ **`tests/` is not scanned and not copied**, so a test's imports cannot widen a live bot's
  deployment. `tools/` IS both — a parity harness ships with its strategy.
- ⚠ **A borrowing is a REAL coupling and the closure makes it visible rather than acceptable.**
  Every bot that borrows `sos_fade` now carries it, which is honest and is also a reason to think
  before adding one: the snapshot, the version count and the parity surface all grow with it.
- 🔴 **It also owns what a VERSION counts (`version_pathspecs`, 2026-09-10): a commit counts only
  when it changes a file `snapshot_sources` ships.** Counting every commit touching the trees made
  a notes edit a new version for every bot. The deploy tool and the Command Center both call it,
  so an edit to a CLAUDE.md, a test, a meta file or a golden export here is never a version.

### Every order layer DECLARES how it opens a position (`entry_style`, 2026-09-03)

🔴 **ONE OBSERVABLE STATE, TWO OPPOSITE CORRECT ANSWERS — WHICH IS WHY THIS IS DECLARED AND NEVER
INFERRED.** *Emulator holding a position, broker holding none, an entry fill on this bar's
decision* is exactly what a **resting** strategy looks like when its limit filled in one book and
not the other — the 2026-08-07 divergence, where the bot must HALT. It is also exactly what a
**market** strategy looks like one instant after its own fill, where the bot must place the
matching order. **The position, the direction, the fill record and the empty broker book are
identical in both cases**, so `algos/live/` asks the strategy instead of guessing.

⚠ **A strategy that enters at market CANNOT be a live bot without this.** It fills inside its own
emulator during the step, so there is nothing left to place ahead of the fill and the bridge's
order-placing branch — which requires the emulator to be FLAT — is never reached. Before the
declaration existed, such a bot halted on its first setup, every time.

⚠ **The value is the one field the contract checks rather than merely counts.** A typo is not a
missing feature: the bridge falls back to `"resting"` and the bot halts on trade one, so
`verify_live_ready` refuses an unrecognised value BY NAME at startup. The fallback is the
backstop, never the thing anything relies on — and it is the halting one on purpose.

⚠ **It does NOT mean the strategy sizes its own live order.** The broker's lot count still comes
from the single live sizing seam, against the BROKER's balance; the declaration decides which
ORDER is sent, nothing else.
