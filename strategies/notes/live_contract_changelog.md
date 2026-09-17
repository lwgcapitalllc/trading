# Notes — Live contract changelog — intents, full_exit_price, planned_full_exit_price

The three dated additions to `DECISION_FIELDS`/`EXECUTION_ATTRS` — `intents`, `full_exit_price`, and `planned_full_exit_price` — what each closes and why each is required rather than optional. Moved VERBATIM out of `strategies/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The live contract gained `intents`, and it is LOAD-BEARING (2026-09-08)

`DECISION_FIELDS` now declares `intents` — what a bar ASKED FOR, as `execution.intents.OrderIntent`
values — and `LOAD_BEARING` is three fields rather than two.

🔴 **EVERY OTHER FIELD IN THAT CONTRACT DESCRIBES WHAT THE STRATEGY DID; THIS ONE IS THE ONLY
CHANNEL FOR SOMETHING IT WANTS DONE THAT LEAVES NO OTHER TRACE.** A scale-in lot is separate lots,
so it never reaches `fills` at all — a live path reading fills alone trades the base position and
says nothing, which is the divergence the whole add path exists to close.

🔴 **IT IS LOAD-BEARING BECAUSE ITS VALUE BECOMES A LIVE ORDER**, the same test `stop` passes. A
strategy that adds size and leaves this empty produces a bot that scales in on paper and not at the
broker; the read is a defensive `getattr`, so nothing fails loudly and the only clue is a halt
naming a lot nobody sent.

⚠ **Its "should populate" is NARROWER than the other two.** Most bars ask for no order, so empty is
the ordinary answer and cannot be asserted blanket-fashion. What an adopter must pin is a bar that
DOES add size.

⚠ **`LiveDecision` declares it as a LIST with a per-instance default, while the contract declares
the empty tuple.** They are deliberately different and the difference is not sloppiness: the
contract states what the live path READS WITH (an absent field must be safely iterable), and the
dataclass states what a PRODUCER appends to — one shared mutable default would grow without bound
and hand each bar the previous bars' orders. The two agree on emptiness, which is the only property
either side uses.

🔴 **NOBODY DECLARED IT FOR AS LONG AS IT EXISTED, AND THE GUARD IS WHAT FOUND IT.**
`test_live_contract.py` greps `algos/live/` for decision reads and requires each to be declared —
it went red the moment the bridge started reading `intents`, then red again on `LiveDecision` for
the same field. **Two links of one chain, each catching the next.** ⚠ `sos_fade.execution.Decision`
satisfies the contract independently and is still not being migrated onto `LiveDecision`; the test
asserts the two agree, it does not merge them.

## The contract gained `full_exit_price`, and it is REQUIRED (2026-09-09)

**`EXECUTION_ATTRS` now asks one more question: at what price do you close the WHOLE position, or
`None`.** The live bridge hands the answer to the broker so a target fills AT its price instead of
at market on the next bar close.

🔴 **REQUIRED RATHER THAN OPTIONAL, AND THAT IS THE WHOLE REASON IT IS IN THE CONTRACT.** Read
defensively, *never implemented* and *this trade has no price target* are the same answer — and the
first means a bot closing at market for its whole life with nothing anywhere saying so. Requiring
it makes a strategy SAY none. Rule 1, in the place this module exists for.

⚠ **A WHOLE-position price, never a partial rung's.** A venue take-profit closes the entire
position, so a strategy banking half at a price answers `None` and lets the bridge reconcile that
rung at market. Answering the rung's price deletes a runner the strategy is still managing.

⚠ **Two implementations cover every live bot, and they decide it differently** — which is why this
is a question rather than a shared helper. `sos_fade.Execution` branches on what KIND of trade is
open (on the live bot a re-entry after a stop-out banks 100% and one into a gap banks 0);
`ExtremeLegExecution` has one target that always takes the lot. `b_leg`, `bos` and `realign`
inherit the first. **Neither strategy can answer for the other.**

🔴 **`verify_live_ready` IS NOT WIRED, so this contract is not enforced at startup.** Four
docstrings in `algos/live/` describe it as the gate that refuses a non-conforming bot by name; its
only caller anywhere is `extreme_leg/tests/test_live_seams.py` (grepped, not assumed, 2026-09-09).
**So adding a required attribute does NOT produce a startup refusal today** — the bridge halts at
the moment of use instead, and that is a workaround rather than the design. Wiring it is its own
change: it would refuse bots that currently start, so it needs its own measurement.

## The contract gained `planned_full_exit_price`, and it is REQUIRED (2026-09-09)

**`EXECUTION_ATTRS` now asks the whole-position-target question TWICE, about two different things.**
`full_exit_price` answers for the trade that is OPEN. This one answers for an order being PLACED:
*if this resting order filled at its own price, where would the whole position come off?*

🔴 **IT EXISTS BECAUSE THE STOP TRAVELLED WITH THE ORDER AND THE TARGET DID NOT.** Both placement
branches in `algos/live/` sent a hardcoded zero, so every trade was open at the broker with no
target until the next reconciliation pass — and a trade that reached its price inside that window
closed at MARKET instead, which is the drift the 2026-09-09 work exists to remove.

🔴 **THE ANSWER IS AN ESTIMATE AND IT IS SAFE IN EXACTLY ONE DIRECTION — THAT PROPERTY IS THE WHOLE
JUSTIFICATION, AND IT WAS WORKED RATHER THAN REASONED.** A rung priced in R depends on the FILL,
which is not known when the order is placed. But a limit fills at its price **or better**, a better
fill is a **smaller** risk, and a smaller risk puts the rung **nearer** the entry — so the estimate
always sits at or BEYOND the price the strategy will bank at, and the broker's target cannot fire
before the strategy's own trigger. ⚠ **It reads backwards for a short and the first pass through it
here got it backwards**: for a short, *nearer* means HIGHER. Both directions are pinned by a test.

🔴 **A MARKET entry is REFUSED rather than estimated, and that is the case the property does not
cover.** A market order fills at the next bar's open, which can be worse as easily as better — and
a worse fill puts the real rung FURTHER out, leaving the estimate NEARER, which closes a trade
early at a price the strategy never chose.

⚠ **REQUIRED, for the reason `full_exit_price` is.** Read defensively, *never implemented* and
*this order has no target* are one value, and the first is a bot that silently never sends one.
Rule 1. ⚠ **`verify_live_ready` is still not wired**, so the refusal happens at the moment of use
in the bridge, not at startup — see the note under `full_exit_price` above.

⚠ **A strategy that never rests an order answers `None` and loses NOTHING.** `extreme_leg` declares
it enters at market, so it has already filled by the time the bridge sends anything and the bridge
asks `full_exit_price` — the exact price, no forecast. **The constant answer is a fact about that
bot, not a stub**, and it is pinned by a test so the next reader does not read it as a gap.

🔴 **THE ORDER NOW CARRIES ITS OWN TRADE KIND (`_Pending.kind`) AND DERIVING IT WAS A RULE-1 BUG
WAITING TO HAPPEN.** Which share the first rung takes depends on whether the trade is a primary or
a re-entry — but `src` is `None` on every primary AND on a re-entry whose trigger did not name
itself, so the two were genuinely one value. The fill path was never exposed to this (it is TOLD
the kind by its caller); the planned answer is asked before the fill and has only the order to go
on. **Pinned by a pair of tests on one config where only the kind differs and it flips the answer.**

## The stop check follows the value through one helper (2026-09-16)

The bridge now passes the strategy's stop through the owner's hand-stop helper before moving the
broker's stop. The structural test lost the trail and went red on a correct bridge. It now follows
ONE wrapping helper on the bridge, and accepts it only if the helper can return its argument
unchanged. **Mutations run, all red:** the stop read replaced by the bridge's own value; the
helper's pass-through return replaced; the stop-move call handed the old stop instead.
