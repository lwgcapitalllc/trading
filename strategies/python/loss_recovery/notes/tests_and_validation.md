# Notes — Tests and the vacuous-test lessons

How to run the test suite, and the mutation-testing pass that found vacuous tests plus how each was fixed. Moved VERBATIM out of `strategies/python/loss_recovery/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Tests

`command-center/backend/.venv/bin/python -m pytest strategies/python/loss_recovery/tests/ -q`
→ **32 passed.**

🔴 **Every one was watched RED by a named mutation, and the harness earned its keep: 5 of the
first 15 were VACUOUS.** They passed against their own bugs. What the mutation pass found, kept
here because each is a general trap:

| Vacuous because | Fix |
|---|---|
| `if t.locked:` never entered — the counter-LONG fixture has no trade that reaches +1R | run the counter-SHORT set, and `assert locked` first |
| deleting the lock made the trade book MORE (+1.457 vs +1.000) — the swing trail rescued it | switch trailing OFF so the assertion is about the lock |
| `r >= -1` still holds when a mutation books +3R | assert the exit reason is in the closed set, and `r <= mfe` |
| `mfe >= r` is trivially true when every trade books exactly −1R | assert `mfe > 0` — the mutation leaves unarmed trades at 0.0 |
| re-running the SAME frame cannot fail (StructureEngine tolerates a re-feed), and real-then-FLAT cannot either (a second guard refuses it) | two DIFFERENT real slices |

⚠ **One assertion could not be made red at all and was replaced rather than kept.** Reordering
the stop check against the arm block returns **byte-identical** results over 2,400 real bars,
because no bar there both arms and stops. It is now a direct two-bar test of `_manage` where the
ordering is observable. **A test that cannot go red is decoration, and the honest move is to say
so in the docstring or delete it.**

✅ **The five tests added 2026-08-19 for the tighter exits were watched RED the same way, and the pass caught a FALSE GREEN in its own harness**: the first mutation was written against a multi-line `if/else` that `ruff format` had already collapsed onto one line, so the string replacement silently matched nothing and the suite stayed green. ⚠ **A mutation that does not apply is indistinguishable from a test that survived it** — assert the replacement landed before believing the red.

🔴 **The 2026-08-19 stop-search pass produced another VACUOUS test and it is the same shape as the original five.** `swing`'s refusal branch was tested by running the mode over the real fixture — where every signal HAS a usable swing, so the branch was never reached and a mutation making it borrow the structural stop passed. **A refusal is only testable by constructing the state that triggers it**; it is now a direct `_stop_for` call with an empty swing book.

⚠ **The price fixture is 2,400 REAL XAUUSD M15 bars** (`tests/fixture_xauusd_m15.csv`, committed
so the tests need no bar cache). Hand-built ramps and sawtooths were tried first and the canonical
structure engine emitted **zero** events on every one — pivot seeding plus 3-candle pullback
confirmation needs price action a straight line does not contain, and a fixture the engine cannot
read would have let every assertion pass on an empty list.
