# Stacking the Extreme Leg bot on the demo account — plan

**Written 2026-09-03. Nothing here is built yet.** This is the survey and the instruction set for
the session that does the work.

**Goal:** `extreme_leg` runs as a second LIVE bot on PU Prime ECN demo **700152905**, alongside
`sos_fade_demo`, sharing one 10% account risk cap at 5% each.

> ## ⚠ READ THIS FIRST — THE NAMES IN HERE WILL MOVE
>
> `docs/DEBRAND_RENAME_PLAN.md` runs BEFORE this and renames every strategy package, class and bot
> key. After it, `extreme_leg` is `extreme_leg`, `ExtremeLegStrategy` is
> `ExtremeLegStrategy`, and `sos_fade_demo` is `sos_fade_demo`.
>
> 🔴 **The rename plan's §2.1 does NOT list this package** — it renames the Pine file and forgets
> the Python folder and class. Fix that there, not here.
>
> **Re-grep every path in this file before acting on one.** The substance is unaffected; the names
> are not.

---

## 0. Why this is not a config file — MEASURED, not assumed

**A bot is an instance directory plus a strategy that implements what `algos/live/` drives.** This
strategy implements almost none of it. Read off `runner.py`, `bridge.py` and the two strategy
packages on 2026-09-03:

### 0.1 The strategy-level pipeline does not exist

`runner.py:193-195` drives **three stages**:

```python
sig = self._st.signals.update(state)
seq = self._st.sequence.update(sig)
dec = self._st.execution.step(sig, seq)
```

| | `sos_fade` | `extreme_leg` |
|---|---|---|
| `.signals` | ✅ `SignalAdapter` | ❌ absent |
| `.sequence` | ✅ `SosFadeSequence` | ❌ absent |
| `.execution.step(sig, seq)` | ✅ returns `Decision` | ❌ absent |
| `.engine_config()` | ✅ | ✅ **the one thing it has** |

🔴 **The extreme leg does all of its deciding inside its own `strategy.step(bar_state)`,** which
calls `execution.resolve` → `_build_setup` → `execution.enter` → `execution.arm_breakeven` →
`execution.record_blocks` and returns a `LegState`. **There is nothing for the runner's three lines
to call.** This is a different pipeline shape, not a missing method.

### 0.2 The execution object is missing what the order layer reads

`bridge.py` reads **four private fields, 13 times**:

| Field | Reads | What it is |
|---|---|---|
| `_ex._pos_dir` | 10 | 0 flat / +1 long / −1 short |
| `_ex._pend_long` | 1 | pending order, synced to a broker slot |
| `_ex._pend_short` | 1 | same |
| `_ex._entry` | 1 | fill price |

Plus these methods:

| What the live path calls | `sos_fade` | `extreme_leg` |
|---|---|---|
| `step(sig, seq) -> Decision` | ✅ | ❌ |
| `request_close(reason) -> bool` | ✅ | ❌ **absent** |
| `snapshot_position()` / `restore_position(snap)` | ✅ | ❌ **absent** |
| `bar_ms` (settable) | ✅ | ✅ |
| `blocks` / `misses` (cleared each bar) | ✅ | ⚠ has `record_blocks`, shape unverified |
| account-budget clamp at the sizing seam | ✅ `_fit_to_budget` | ❌ sizes in its own `_qty(risk)` |

🔴 **`request_close` is the dangerous absence.** The fleet kill switch, the Command Center Stop
button and flat-by-close all resolve through it. **A bot without it can be started and cannot be
told to flatten.**

🔴 **`snapshot_position` / `restore_position` is the expensive absence.** `bridge.py` calls them at
**three** sites (`711`, `736`, `824`) and they are what lets a bot come back from a restart still
holding a position. Building this means serialising the open position **and every latch that
decides its exit** — the breakeven arm, the widened hold, the ladder state.

⚠ **The private-field coupling is the part to decide about, not just implement.** The order layer
is bound to one class's internal layout. Either the adapter reproduces those four names exactly, or
`bridge.py` is refactored to a real interface first. **Reproducing them is faster and lies less** —
a refactor of the order layer touches the LIVE bot and needs its own proof.

---

## 1. What gets built

**One adapter, in `strategies/python/extreme_leg/`, presenting this strategy through the
interface the live path drives.** Not a change to `algos/live/`, and not a rewrite of the strategy's
own logic — the replay path stays exactly as it is, because every number this bot has was measured
through it.

1. **A signals stage and a sequence stage** — even if one is a pass-through. The runner's three
   lines must have something to call, and the seams are where blocked/missed setups get recorded.
2. **`step(sig, seq) -> Decision`** — one call per bar that internally sequences the existing four
   (`resolve` → `enter` → `arm_breakeven` → `record_blocks`) in the order `strategy.step` already
   uses, and returns the decision object the order layer consumes.
3. **`request_close(reason)`** — a commanded flatten that the emulator honours on the next bar.
4. **`snapshot_position()` / `restore_position(snap)`** — the open position and every exit latch.
5. **`_pos_dir`, `_entry`, `_pend_long`, `_pend_short`** — matching what the order layer reads.
6. **The account-budget clamp at its sizing seam**, so the cap actually binds this bot. Without it
   the second bot is exactly the thing the cap exists to prevent.

⚠ **The replay path must be byte-identical after this.** Re-run the strategy's own backtest before
and after and diff the trade list. **If a single trade moves, the adapter changed the strategy** —
and every published figure for this bot describes the old one.

---

## 2. The risk split, and the ordering trap

**Target: extreme leg 5%, A+ 5%, account cap 10%.** Aaron's split.

Today A+ is at **10%** and the cap is **10%** (moved back 2026-09-03 — holding 5% for a bot that
could not start was costing half the account's return for nothing; see
`algos/CLAUDE.md` → *The extreme leg cannot be a bot yet*).

🔴 **Order matters and it fails loudly the wrong way round:**

```
1. Move sos_fade_demo to 5%.      <- FIRST
2. Assign the extreme leg at 5%.      <- SECOND
```

The Command Center refuses any write where the shares on an account sum past its cap. **Assigning
first is refused**, because 10 + 5 > 10.

⚠ **A+'s risk is the ONE runtime-reloadable field** — it reaches the running bot on the next VPS
`git pull`, no promote, no restart, applied at the next moment it is flat.

⚠ **Halving A+ halves its return and its drawdown together.** Every published figure for it — the
−54.9% max drawdown over 6.5 years, Run 12's finding that the drawdown is a losing streak rather
than give-back — was measured at 10% and describes neither bot after this.

⚠ **`b_leg_demo` is benched and still states 10.0.** It cannot join this account until that
moves.

### What the stack is expected to do

MEASURED 2026-09-03, 470,995 M5 bars, PU Prime `XAUUSD.p`, 2020-01-01 → 2026-08-23:

- Shared bars: **1,049** — 3.1% of A+'s hold time, 6.0% of the extreme leg's.
- Same-side: **ZERO**. All 1,049 are opposite-direction, i.e. partly hedged.
- Trade pairs touching at all: 6, **none same-direction**. No same-direction entry within four hours
  in 6.6 years.
- Monthly R correlation **+0.035** over 79 months — a floor, not a figure.
- Extreme leg alone: **113 trades / +58.53R**.

⚠ **Peak concurrent positions is still 2**, so one account carries both legs' risk on those 1,049
bars. **That is what the cap is for.** It does not make them independent — one structure stream, one
instrument.

⚠ **Re-run `backtest/tools/overlap_audit.py` after any entry-logic change on either bot**, and pass
`--server`. A run on the wrong broker's cache disagrees with every figure here while looking
perfectly healthy.

---

## 3. Order of work

Each stage is committable and leaves the repo working.

1. **Baseline the replay.** Run the extreme leg's backtest and save the trade list. This is the
   thing every later step is diffed against.
2. **Build the adapter** (§1). Owning CLAUDE.md in the same commit; the message names its proof.
3. **Diff the replay against step 1.** Byte-identical, or stop and find out why.
4. **Run its parity gate on a real export.** Rule 22 — no strategy change is committed before its
   `compare_*.py` has run and passed. See §4 for what that gate does and does not cover.
5. **Unit-test the four new seams, and watch every test go RED first** (rule 12). The restart path
   and the commanded close are the two that matter; neither can be proven live before it runs.
6. **`scripts/run_all_tests.sh` green end to end.** A person runs it; no hook does.
7. **Create the instance directory** from `algos/live/instance.template.json` — key, display name,
   package, class, symbol, timeframe (**M5 — see below**), magic (a NEW number, never A+'s 770115),
   account 700152905, cap 10.0, risk 5.0.

   🔴 **The frame is not a preference and getting it wrong FAILS SILENTLY.** This strategy measures
   its trigger on **5-minute** bars and builds its 15-minute half **in code**. Hand it a 15-minute
   frame and the trigger and the target become the same series, so **there is no trade left to
   take** — the bot runs, logs cleanly, and simply never fires. ⚠ **That looks exactly like a quiet
   market.** Verified in `backtest/tools/overlap_audit.py`, which carries the same warning because
   it had to override the shared frame for this bot.
8. **Register the bot** in the Command Center and assign it to the account — **after** step 9's
   first line.
9. **Move A+ to 5% first, then assign** (§2). Confirm from the bot's own log that it applied the
   change while flat.
10. **Promote and start**, per the deploy workflow in the root CLAUDE.md. Stop by ASKING, never by
    killing. Never `taskkill /f /im python.exe`.
11. **Prove it live** (§4.3). This is the part that cannot be skipped or shortened.

---

## 4. How you know it works — and what cannot be proven

**Aaron asked for total confidence. Here is what is actually available, split by what each check
proves, because the difference is the whole point.**

### 4.1 What the checks genuinely prove

| Check | What it proves |
|---|---|
| Replay diff (§3.3) | The adapter did not change the strategy. **Strong** — it is the same code path every published number came from. |
| Unit tests, watched red | The four new seams do what their names say. **Strong for the seams, silent about the whole.** |
| `run_all_tests.sh` | The code agrees with itself. **Says nothing about the broker, the VPS, the database or Telegram.** |
| Restart-with-position test | Save/restore round-trips. **Proves the shape, not the broker's agreement with it.** |

### 4.2 What CANNOT be proven before it runs — state these, do not paper over them

🔴 **The parity gate covers 3.5 months and 7 entries, and it cannot cover this bot's shipped
form at all.** The chart has no engine for the market-condition refusal that produces its current
numbers. **So the gate speaks for the Python port, and the half carrying the money is the half no
gate reaches.** Rule 14: a green gate says two implementations AGREE, never that either is RIGHT.

🔴 **No order from this strategy has ever reached a broker.** Rule 9 — a feature nobody has run is
not a feature. Everything above is the code agreeing with itself.

🔴 **The account cap has never refused a real second bot,** because there has never been one. Its
live half is tested but unexercised in the only situation it exists for.

⚠ **Two bots on one terminal is new.** Process locks, magic-number reconciliation and the shared
MT5 connection have all only ever run with one bot on this box.

### 4.3 The live proving period — the only thing that closes the gap

**Do not go from green tests to armed.** Staged, and each stage answers one question:

1. **Watch it flat.** Started, reporting the right version, not saying *"the previous run ended
   without shutting down."* Confirm both bots hold their own locks and neither sees the other's.
2. **Watch the first refusal.** Force the budget full with A+ open and confirm the extreme leg is
   refused, with a Telegram message saying why. **This is the cap's first real exercise.**
3. **Watch the first order.** Read the comment string off the BROKER, not off our log. Confirm the
   magic number is its own and reconciliation does not cross the two bots.
4. **Watch a restart while it holds a position.** The riskiest path in the whole build, and no test
   reaches it. Do it deliberately, at a chosen moment, not by accident at 3am.
5. **Watch the first full trade close** and reconcile its R against what the emulator booked.

⚠ **Until step 5, treat every number this bot reports as unproven.**

### 4.4 The honest answer on "no bugs"

**Certainty is not on the menu and claiming it would be the exact failure this repo keeps
recording.** What §4.1–4.3 buys is: the strategy provably unchanged, the new seams individually
proven, the suite green, and every live path walked once under supervision before it is trusted.
**The residual risk sits in three named places** — the un-gated shipped form, the restart-with-
position path, and two bots sharing one terminal — **and each is watched deliberately rather than
hoped about.**

---

## 5. The decision that is still open

**Whether A+ should be at 5% at all.** The split assumes two bots deserve equal shares. Nothing has
measured that. The overlap audit says they rarely collide and never same-side, which argues the cap
is doing little work — **and if the cap rarely binds, the split is costing A+ half its size to buy
protection it does not often need.** Worth measuring on the stack replay before accepting 5/5 as
permanent.
