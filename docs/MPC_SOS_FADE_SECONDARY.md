# MPC SOS Fade — Secondary (1m sniper) re-entry

**Status:** Design + build in progress (2026-07-19). The Python is the *exact* version of a
feature Aaron prototyped in `mpc_strategy.pine` (that Pine WIP is stashed:
`git stash list` → "secondary-trade pine WIP"). Pine can only sample the 1m engine once per
15m bar via `request.security`, so its timing is approximate; the Pine tooltip itself says
**"the exact version is the Python port."** This doc is the source of truth for that port.

---

## What it is (one paragraph)

After the **primary** 15m A+ trade on a leg has already traded and gone flat (back to
breakeven), keep re-entering on that *same* 15m leg from the 1-minute chart. While the 15m
divergence **and** SOS are still live and price is back inside the **0.618–0.886** zone of the
15m fib, watch the 1m chart (same structure engine) for a **1m shift of structure** in the
trade direction. When one fires, rest a limit at a **38.2% retrace of that 1m leg**. The tight
1m leg is what makes it a *sniper* entry — small stop, fast to breakeven. Multiple re-entries
per 15m leg are allowed (always flat first), but **each distinct 1m leg fires at most one**.

A re-entry is **never the first trade on a leg** — the primary must have traded that leg first.

---

## The rules (ported line-for-line from the Pine WIP `f_secArm`)

Config toggle: **`exec_secondary`** (Pine `execSecondary`, default **False**). Off = primary
only, one entry per 15m leg (today's behaviour, unchanged).

### 1m leg latch (records the leg a re-entry will trade)
- The 1m structure engine runs continuously on 1m bars. Its **latched** state per side is: the
  bar of the most recent 1m SOS, and the leg that SOS defined — `legHi` = 1m fib **0.0**,
  `legLo` = 1m fib **1.0** (= the stop anchor). A "new 1m SOS" = that latched bar advanced.
- Clear the long 1m leg the instant the 15m long setup dies (`aplusL_sosBar` is `None`); mirror
  for shorts. A stale 1m leg can never arm a fresh 15m leg.
- **Latch a long leg** when: `exec_secondary` ON, a new 1m **bull** SOS fired, the 15m long
  setup is live (`aplusL_sosBar` not None), `bullDivActive`, price is in the zone
  (`zoneL`), and `legHi > legLo`. Mirror for shorts (bear SOS, `bearDivActive`, `zoneS`).
- **Zone** (`zoneL`): `fibo_dir == 1` and price in `[fiboP6, fiboP3]` (0.886…0.618).
  Mirror `zoneS`: `fibo_dir == -1` and price in `[fiboP3, fiboP6]`.

### Arm (rest the limit)
`lArmed` is true only when **all** hold:
- `exec_secondary` and `exec_longs`,
- **flat** (no open position),
- 15m long setup live (`aplusL_sosBar` not None),
- **the primary already traded this leg**: `tradedSosL == aplusL_sosBar`,
- `bullDivActive`, `fibo_dir == 1`, `fibsReady` (all 15m fib levels present),
- the latched 1m leg is valid (`legHi/legLo` set, `legHi > legLo`),
- this 1m leg hasn't already re-entered (`lLegTraded is None or lLeg != lLegTraded`),
- not in the late-day block, and (`not longVeto` or `not exec_respect_veto`).

Mirror for `sArmed`.

### The trade, on arm
| | Long | Short |
|---|---|---|
| entry (resting limit) | `legHi − (legHi−legLo)·0.382` | `legLo + (legHi−legLo)·0.382` |
| stop | `legLo − slBuf` (1m 100%) | `legHi + slBuf` |
| TP1 | 15m `fiboP2` (0.5) | 15m `fiboP2` |
| TP2 | 15m `fiboP1` (0.382) | 15m `fiboP1` |
| TP3 | runner (ratchet trail, same as primary) | runner |

Sizing = the same `exec_risk_pct` / stop-distance as the primary. On fill, **retire that 1m
leg** (`lLegTraded := lLeg`) so it can't re-enter twice.

---

## The one deliberate deviation from the Pine — exact 1m timing

The Pine samples the 1m engine at the 15m close, so its re-entry fill is approximate. **The
Python runs the 1m bars for real:**

- **Primary** (the 15m A+ trade) stays exactly as today — armed, filled and managed on **15m**
  bars. This is what keeps `compare_strategy.py` parity **green** (`exec_secondary` defaults
  off, so with it off the whole strategy is bit-identical to the validated port).
- **Secondary** is the 1m improvement — the 1m leg latch, the arm, the limit **fill**, and the
  TP1/TP2/stop management all happen on real **1m** bars. This is the sniper entry Aaron wants
  ("get in and out with profit, or move to breakeven as soon as possible") that a 15m bar
  cannot express.

**Zone check uses the live 1m close** (not the 15m close the Pine used) — "price is back in the
zone right now," faithful to the exact-timing intent.

**Consequence: there is NO Pine parity gate for the secondary.** The Pine is only the
approximate version. So the secondary is verified **visually** — the command-center price chart
with the 15m→1m drill-down, trade markers landing on the 1m candles at the 1m SOS + retrace.
That drill-down is why the chart work happened first.

---

## Python architecture

```
1m df ─┐
       ├─ DualClock ─┬─ on 15m bar close: EngineStack → Signals → Sequence → Execution (PRIMARY, 15m)
15m df ┘             │       └─ updates the "15m context" the secondary reads
                     └─ on each 1m bar:   Structure1m → Secondary latch/arm → Execution (SECONDARY, 1m)
```

- Bars are timestamped at **open** (UTC). A 15m bar at `t` covers `[t, t+15m)`; its 1m bars are
  `t … t+14m`. Calc-on-close: the 15m context for `[t, t+15m)` is only known at `t+15m`, so a
  secondary forming inside that window reads the **previously closed** 15m context — correct,
  non-repainting, and matches Pine's `lookahead_off`.
- **`Structure1m`** — a lean feed: `StructureEngine` + `StructureFib` on 1m (same `show_internal`
  pin as the primary), exposing latched `m1_bull_sos_bar` / `m1_bear_sos_bar` + leg hi/lo and
  the `new_bull_sos` / `new_bear_sos` edges. It does NOT run fvg/rsi/liquidity/sessions — the
  secondary needs only 1m structure.
- **Execution** grows a secondary path: an `_entry_kind` tag on the open position, a
  `step_secondary(bar1m, arm)` entry point that reuses the existing bar-fill primitives
  (`_try_entry_fill_bar`, `_manage_open_bar`, `_advance_stage`, `_current_stop`). 15m bars only
  touch a **primary** position; 1m bars only touch a **secondary** position — they share the one
  position slot but never the same trade, because the secondary only arms when flat.

## Verification

1. **Unit** — `Structure1m` (SOS latch + leg + edge), the arm/latch truth table, one hand-traced
   end-to-end re-entry.
2. **Visual** — a real run with `exec_secondary=True`, opened in the lab's price chart, drilled to
   1m at a re-entry: the 1m SOS, the retrace to 38.2%, the fill marker, the 15m TP levels.
3. **Parity guard** — `compare_strategy.py` stays exit 0 with `exec_secondary` OFF (the default),
   proving the secondary is purely additive and the primary never moved.
