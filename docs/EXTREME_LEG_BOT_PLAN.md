# Stacking the Extreme Leg bot on the demo account — plan

**Written 2026-09-03. Nothing here is built yet.** This is the survey and the instruction set for
the session that does the work.

**Goal:** `extreme_leg` runs as a second LIVE bot on PU Prime ECN demo **700152905**, alongside
`sos_fade_demo`, sharing one 10% account risk cap at 5% each.

> ## ✅ NAMES UPDATED 2026-09-03 — the de-brand rename has LANDED
>
> Verified after the rename: the package is `strategies/python/extreme_leg/`, the class is
> `ExtremeLegStrategy`, and the live bots are `sos_fade_demo` and `b_leg_demo`. The rename session
> caught this package, so the gap flagged in its own plan was handled.
>
> ⚠ **Every path below was re-grepped against the renamed tree.** Re-check before acting anyway.

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

### 0.3 The decision contract — MAPPED 2026-09-03, and it hides a silent failure

`execution.step` returns one object, consumed in exactly two places: `ledger.bar(dec, sig, seq)`
and `bridge.sync(dec, sig)`. Between them they read **eleven fields, every one through
`getattr(dec, ..., default)`**:

| Field | Read by | Weight |
|---|---|---|
| `stop` | bridge | 🔴 **moves the broker's stop** — the only field that touches money |
| `fills` | bridge | 🔴 **books the trade** |
| `exit_reason` | bridge | reporting |
| `tp1`, `tp2` | both | reporting |
| `long_armed`, `short_armed` | ledger | reporting |
| `long_edge`, `short_edge` | ledger | reporting |
| `l_stage`, `s_stage` | ledger | reporting |
| `long_veto`, `short_veto` | ledger | reporting |

✅ **Good news: only two of the eleven carry weight.** The decision object does not have to be a
copy of the SOS Fade one.

🔴 **BAD NEWS, AND IT IS THE MOST DANGEROUS THING IN THIS PLAN: every read is defensive, so a
field this adapter forgets to set is INDISTINGUISHABLE from a field with nothing to report.**
Forget `stop` and the bridge simply never ratchets the broker's stop — no error, no halt, no log
line, and a position that rides its original stop all the way down while every dashboard looks
healthy. **This is rule 1 arriving in a new place: "nothing to report" and "never implemented"
must not be the same value.**

⚠ **So the adapter's tests must assert these fields are POPULATED on a bar that should populate
them** — not merely that `step` returns an object. A test that only checks the object's type
passes against an adapter that sets nothing.

### 0.4 A wrapper class is NOT available — the runner pins the class through the lab entry

`runner._build_strategy` reads `LAB_STRATEGY["strategy"]` and then **refuses unless its
`__name__` equals the instance config's `strategy_class`.** It does not look the name up in the
module. So a separate `LiveExtremeLegStrategy` cannot be pointed at without either changing
`LAB_STRATEGY["strategy"]` — which changes what the LAB replays — or changing the runner.

**Decision: build the live seams ONTO the existing classes.** The alternative touches
`algos/live/`, which is the code the running bot executes, and would need its own proof.

⚠ **What makes this safe is the baseline, not the argument.** New methods nothing existing calls
cannot move the replay; the one existing line that must change is the sizing seam, and that is a
no-op unless a capped account is attached. **Both facts are checked by re-running the baseline,
never assumed.**

### 0.5 🔴 THE REAL BLOCKER, FOUND 2026-09-03: the order layer cannot OPEN at market

**This strategy enters at market on the bar's close. `algos/live/bridge.py` can only rest a limit
order.** Its one placement path, `_place`, calls `place_pending_limit` and nothing else.

⚠ **This falsifies §1's opening assumption** ("not a change to `algos/live/`"). It was written
before the placement path was read. **The extreme leg cannot go live without a market-entry route
in the order layer**, and that is the code the running bot executes.

✅ **The terminal layer already has the call** — `mt5_ops.place_order` sends a market order, with a
broker minimum-stop guard. 🔴 **But NOTHING in the live path calls it.** Its only caller in the
whole repo is one test. Rule 9: it has never placed a real order.

### 0.6 A LATENT DEFECT in the SOS Fade bot, found on the way — not active, worth recording

**A pending entry carries a `market` flag meaning "do not wait for price, fill at the next open".**

- ✅ The EMULATOR honours it (`sos_fade/execution.py:1089-1096` — it fills at the open).
- 🔴 **No file under `algos/live/` reads it.** Grepped for `.market` and `market=` across the whole
  folder: nothing. The bridge would rest a limit for an order the strategy marked as market.

⚠ **NOT active today, and that was CHECKED rather than assumed**: the live config has the reclaim
entry mode on `Retest` and the recovery feature `false`, so the flag is never set. **It is latent.**

🔴 **If anyone switches that mode to `Market`, the emulator and the broker do different things and
nothing says so** — the emulator books a fill at the open while a limit rests at a price that may
never come back. **This is rule 7 exactly: a label is a claim about code somewhere else, and this
one has no consumer.** Fix it in the same change as the market-entry route above, or delete the
flag; leaving a setting that silently does nothing is the worse of the two.

---

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

**Target: extreme leg 5%, SOS Fade 5%, account cap 10%.** Aaron's split.

Today SOS Fade is at **10%** and the cap is **10%** (moved back 2026-09-03 — holding 5% for a bot that
could not start was costing half the account's return for nothing; see
`algos/CLAUDE.md` → *The extreme leg cannot be a bot yet*).

🔴 **Order matters and it fails loudly the wrong way round:**

```
1. Move sos_fade_demo to 5%.      <- FIRST
2. Assign the extreme leg at 5%.      <- SECOND
```

The Command Center refuses any write where the shares on an account sum past its cap. **Assigning
first is refused**, because 10 + 5 > 10.

⚠ **SOS Fade's risk is the ONE runtime-reloadable field** — it reaches the running bot on the next VPS
`git pull`, no promote, no restart, applied at the next moment it is flat.

⚠ **Halving SOS Fade halves its return and its drawdown together.** Every published figure for it — the
−54.9% max drawdown over 6.5 years, Run 12's finding that the drawdown is a losing streak rather
than give-back — was measured at 10% and describes neither bot after this.

⚠ **`b_leg_demo` is benched and still states 10.0.** It cannot join this account until that
moves.

### What the stack is expected to do

MEASURED 2026-09-03, 470,995 M5 bars, PU Prime `XAUUSD.p`, 2020-01-01 → 2026-08-23:

- Shared bars: **1,049** — 3.1% of SOS Fade's hold time, 6.0% of the extreme leg's.
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

1. ✅ **DONE 2026-09-03 — baseline locked.** `470,995` M5 bars of PU Prime `XAUUSD.p`,
   2020-01-01 → 2026-08-23, default config, no costs, no account: **113 trades**, digest
   `e4183861407c6b1e`. ✅ **It reproduces the published figures exactly** (470,995 bars / 113
   trades), so the baseline is the same experiment those numbers came from. ✅ **Determinism was
   proven rather than assumed** — a repeated six-month run gave an identical digest. **Re-run and
   diff after every later step.**
2. **Build the adapter** (§1). Owning CLAUDE.md in the same commit; the message names its proof.
3. **Diff the replay against step 1.** Byte-identical, or stop and find out why.
4. **Run its parity gate on a real export.** Rule 22 — no strategy change is committed before its
   `compare_*.py` has run and passed. See §4 for what that gate does and does not cover.
5. **Unit-test the four new seams, and watch every test go RED first** (rule 12). The restart path
   and the commanded close are the two that matter; neither can be proven live before it runs.
6. **`scripts/run_all_tests.sh` green end to end.** A person runs it; no hook does.
7. **Create the instance directory** from `algos/live/instance.template.json` — key, display name,
   package, class, symbol, timeframe (**M5 — see below**), magic (a NEW number, never SOS Fade's 770115),
   account 700152905, cap 10.0, risk 5.0.

   🔴 **The frame is not a preference and getting it wrong FAILS SILENTLY.** This strategy measures
   its trigger on **5-minute** bars and builds its 15-minute half **in code**. Hand it a 15-minute
   frame and the trigger and the target become the same series, so **there is no trade left to
   take** — the bot runs, logs cleanly, and simply never fires. ⚠ **That looks exactly like a quiet
   market.** Verified in `backtest/tools/overlap_audit.py`, which carries the same warning because
   it had to override the shared frame for this bot.
8. **Register the bot** in the Command Center and assign it to the account — **after** step 9's
   first line.
9. **Move SOS Fade to 5% first, then assign** (§2). Confirm from the bot's own log that it applied the
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
2. **Watch the first refusal.** Force the budget full with SOS Fade open and confirm the extreme leg is
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

**Whether SOS Fade should be at 5% at all.** The split assumes two bots deserve equal shares. Nothing has
measured that. The overlap audit says they rarely collide and never same-side, which argues the cap
is doing little work — **and if the cap rarely binds, the split is costing SOS Fade half its size to buy
protection it does not often need.** Worth measuring on the stack replay before accepting 5/5 as
permanent.
