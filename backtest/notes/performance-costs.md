# Notes — Replay performance and the scale-in cost defect

Why the bar loop reads column arrays instead of df.iterrows(), and the Costs pill under-charging every trade that scaled in. Moved VERBATIM out of `backtest/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The bar loop reads COLUMN ARRAYS, never `df.iterrows()` (2026-08-26)

`iter_bars` is the hot loop of the whole lab — every replay, every optimizer cell and every
portfolio leg goes through it once per bar. It walked `df.iterrows()`, which builds a fresh pandas
Series **per bar** (block manager, dtype resolution, `__finalize__`) so that five numbers can be
read off it and thrown away.

**MEASURED, the two implementations A/B'd ALTERNATELY in one process over 62,468 real M15 bars:
615 µs/bar → 60 µs/bar, ~10x, saving ~35s on a 2.5-year window.** ⚠ **The RATIO is the
measurement and the absolute figures are an upper bound** — this machine was under load from a
second session, identical end-to-end runs came back at 201s and 382s, and that is why the two were
interleaved and scored on the BEST pass rather than benchmarked one after the other. **Two
sequential benchmarks on a loaded machine each measure a different amount of the load.**

🔴 **The conversion is deliberately IDENTICAL rather than merely equivalent.** `.to_numpy()` is
called with NO dtype coercion and every element still goes through `float(...)` — the same call on
the same stored value `row["open"]` produced. Forcing `dtype="float64"` is faster again and is
REFUSED: on an object column it converts by a different route, and *slightly faster and
occasionally a different float* is not a trade anybody asked for.

⚠ **`pd.isna` on the raw volume element STAYS.** It is what keeps an absent volume `None` rather
than `0.0` — rule 1, and `ReplayBar.volume`'s own docstring says why that distinction is
load-bearing. A NaN test written as `raw != raw` is equivalent for floats and WRONG for an object
column carrying `None`.

✅ **PROVEN ON REAL BARS RATHER THAN ARGUED** — `replay_fingerprint.py` (below, same commit)
replayed 2.5 years before and after: bar-stream digest identical, all 66 trades identical on every
field. 539 strategy tests green.

### `tools/replay_fingerprint.py` — how a speed change proves it moved nothing

`capture` before the change, `compare` after. It hashes the BAR STREAM — by replaying the
iterator, never by hashing the frame, so it measures the thing under test — and every field of
every closed trade.

⚠ **A totals check is not this.** Two different books post the same net, so a change that merely
SWAPPED two trades passes a totals check in silence.

🔴 **It fingerprints the STRATEGY SOURCE and the resolved config into the basis, and REFUSES to
compare across a change in either.** Without that it reported a real difference that belonged to
somebody else: a second session edited `sos_fade.meta.json` between a capture and its
comparison, and the tool duly said the trades had moved. **They had — the strategy had.** *A
comparison harness that cannot see the thing underneath it changing will blame whichever change
you happen to be holding.*

⚠ **It REFUSES an empty trade book.** The first version read `strategy.trades`, a field that does
not exist (`strategy.execution.trades` is the real one), captured ZERO trades, and would have
compared equal to everything forever. ⚠ **And `_trade_rows` builds LISTS, not tuples** — JSON has
no tuple, so a reloaded baseline never equalled a freshly-built one and every trade read as
changed with no differing field to show for it. **Both failures are the same shape: a comparison
tool that is broken says EQUAL or says DIFFERENT, and neither answer looks like an error.**

### `--allow-strategy-change` — the door in the basis wall (2026-08-26)

A speed change INSIDE a strategy moves its source digest, so the basis guard refuses and the one
comparison the tool exists to make becomes the one it will not run. The flag waives
`strategy_source` **and nothing else**: `strategy_settings`, window, instrument, timeframe and
server still refuse, so a moved DEFAULT can never ride in under a performance claim.

⚠ **Passing it is a CLAIM — *I changed the code and assert it is inert* — and it prints a line
saying so above the verdict.** A CHANGED result underneath it is that claim being refuted, never
a tool malfunction. Same reasoning as `compare_strategy.py`'s `--allow-fast-timeframe`: a wall
with no door gets routed around in ways that leave no trace.

🔴 **Where a strategy exposes BOTH algorithms behind a flag, prefer forcing the flag over running
the tool twice** — one process, one binary, nothing else able to differ. That is how the bar-time
map's prune was proved (`strategies/python/sos_fade/CLAUDE.md`), and it needs no waiver at
all. ⚠ **Patch `type(strategy.execution)`, never the class imported by package path — the lab
loads that module twice and they are different class objects.** A patch on the wrong one hits
nothing and the comparison silently becomes a run against itself.

### Where the replay's time goes NOW, and why the optimisation stopped (2026-08-27)

After the four fixes above, a 23,539-bar profile is **8.7s and FLAT** — the largest single entry is
7.5% and everything else is under 4%. That is the signal to stop, and the reasoning is recorded so
the next person does not re-derive it:

| what is left | share | why it was not taken |
|---|---|---|
| the strategy's signal adapter | 7.5% | it is 71 dataclass field assignments per bar; making it faster means `__slots__` or a namedtuple, i.e. a wide refactor of a money path for ~4% |
| timezone conversion (10 `astimezone` per bar) | ~4.6% | spread across `sessions/`, `liquidity/`, `vwap/` and the strategy — **four canonical engines, four parity gates**, for a few percent |
| everything else | <4% each | no single item worth a gate |

🔴 **THE BAR IS NOT "IS THERE ANY TIME LEFT" — IT IS "WHAT DOES CLAIMING IT COST TO VERIFY".** Every
remaining candidate lives in a canonical engine, so rule 22 applies to each one: a real export, a
gate run before and after, and a byte-identical trade book. **A 3% gain that needs a TradingView
export somebody has to sit down and take is not a 3% gain, it is a 3% gain plus a human.**

⚠ **The four that WERE taken are not counter-examples to that bar, they are the reason it exists.**
Three of them were defects — work with no purpose, removable with the comparisons untouched — and
the fourth was a cache. **None of them required reading a strategy differently.** When the next
candidate does, the answer is no.

⚠ **Re-measure before re-opening this.** The table is one profile on one window, and cProfile
charges allocation pressure to whoever is running — the pivot fix returned four times its own
profile share for exactly that reason, so a small entry here is not proof a change would be small.

## 🔴 The Costs pill UNDER-CHARGED every trade that scaled in (2026-09-07)

`reprice.py` rebuilds a finished run's book at a different cost profile, and it rests on one
identity: a cost's size in **R** does not depend on position size, so `qty` cancels. That holds.
What did not hold was the **size it read**.

**A scale-in lot is a lot of its own.** It is not in the trade's `size` and it is not in `legs` —
`legs` records the BASE position's exit rungs and its quantities sum to `size` exactly — so
nothing in either field says a trade grew. The model charged one round turn on the base and
stopped, while the replay charges the add commission and half the spread when it fills and the
same again when it banks. **Every add was free.**

**MEASURED** on the reference window (PU Prime `XAUUSD.p` M15, 42 trades, 15 of them scaled): the
rebuilt book came out **0.4328R** light against a real charged replay — spread `-1.0500R` against
the replay's `-1.4827R` — on a check whose bound is **1e-5**. It is fixed by reading `adds` and
charging each lot its own round turn, and it reproduces the replay exactly again.

🔴 **IT WAS INVISIBLE UNTIL A DEFAULT MOVED.** Scale-in shipped OFF, so no run had adds and the
model was right by accident for as long as it existed. `SosFadeConfig.exec_scale_in` went off →
on on 2026-09-06 and `test_reprice.py` — which builds the SHIPPED config — went red the same day.
**A model that is correct only while a feature is switched off is a model nobody has tested**, and
the thing that caught it was a test constructing real defaults rather than a stub.

🔴 **SWAP IS NOW CHARGED ON ADDS TOO, ON BOTH SIDES, AND UNTIL 2026-09-07 IT WAS CHARGED ON
NEITHER.** A broker finances the POSITION, not the order that opened it, so a lot bought on the
way up costs exactly what the base costs to carry through the same night. The replay billed
`self._qty - self._filled_qty` — the base alone — and this module mirrored it, so **the two
AGREED while both under-charged every scaled trade held overnight.**

🔴 **That is rule 14 arriving as a bill, and it is the transferable part: a green reproduction
check says the model MATCHES the run, never that either is RIGHT.** This check has a 1e-5 bound on
the exact layers and 0.05R on swap, it ran on every commit, and it was green throughout — because
both sides were wrong in the same direction. **When two implementations are written to agree, ask
what they agree ABOUT.**

**MEASURED** on the reference window (PU Prime `XAUUSD.p` M15, 42 trades, 15 of them scaled): the
correction is **0.2024R**, four times the swap bound. The charged replay's swap layer moves
`-1.6920R` → `-1.8945R`. ⚠ **Every stored number on a run that scaled in moves by roughly this
much, in the expensive direction.** Runs with no adds are byte-identical — scale-in shipped OFF
until 2026-09-06, so the whole published history predating that date is untouched.

⚠ **Each lot's nights are its OWN.** A trade may open one night, add on the second and bank the
add on the third, and only the middle night is financed on the larger size — so `_qty_open_at`
reads each add's own fill and exit times rather than the trade's window. Charging every add for
the whole hold would over-bill a late add by however long the trade ran before it.

⚠ **The boundary rules are INHERITED from the replay, not chosen here.** `_charge_swap` runs
before the bar's fills and before its exits, so a lot bought at the rollover pays nothing and a
lot sold at it still pays — the same treatment the base already gets.

⚠ **Proven by MUTATION IN BOTH DIRECTIONS, which is what says the two are genuinely coupled.**
Reverting only the replay reddens the swap case at `-1.8945` vs `-1.6920`; reverting only this
module reddens it at `-1.6920` vs `-1.8945` — the same gap, mirrored. A one-sided fix cannot pass.

⚠ **THE PARITY GATE CANNOT COVER ANY OF THIS, and it was checked rather than assumed.** The gate
replays COST-FREE (`compare_strategy.py` builds the strategy with no profile, so `_charge_swap`
returns at its first line), and **every TradingView export on this machine ran with
`cfg_scale_in = 0`** — so it says nothing about adds either. It was run and is green
(`VANTAGE_XAUUSD, 15_b5eda.csv`, 20,841 bars from 500 on), which establishes that the change did
not move the entry/exit logic and nothing more. **Financing on adds is covered by this
reproduction check and by three unit tests in `test_execution_ticks.py`, not by the gate.**

⚠ **Commission is charged per ADD, never on their total.** It is billed per LOT and the profile
rounds lots, so summing first and charging once rounds a different number.

⚠ Both halves proven by MUTATION: dropping the adds from the spread charge reddens the spread
case, dropping them from the commission charge reddens the commission case, and neither touches
the other.
