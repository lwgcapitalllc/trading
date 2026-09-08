# `execution/` — the one vocabulary a strategy and a broker both speak

**Purpose:** so a trading feature is built ONCE and both the backtest and the live bot get it.
**Status:** stage 1 of 3. The contract exists and is tested; **nothing consumes it yet.**

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
2. ⬜ **The simulator consumes it** — the strategy stops booking inline. The book must not move.
3. ⬜ **The live bridge consumes it** — refusals retire one at a time, add-size first.

🔴 **The bar for every stage is the same and it is absolute: the stored book does not move.**
Baseline captured before any of this began — stack `st_631986bbd9`, **272 trades,
223.3339464065 R**, with a sha256 over the full trade list, in `.baseline/`. A stage that cannot
reproduce it exactly is reverted, not explained.
