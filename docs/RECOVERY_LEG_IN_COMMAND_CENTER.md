# Building the loss-recovery leg into the Command Center

**Status:** planned 2026-08-21, shape approved by Aaron. Not built yet.
**Owner of the rule:** `strategies/python/loss_recovery/CLAUDE.md`.
**Owner of the shared account:** `backtest/portfolio/`.

---

## Why this exists

There are two ways to run the loss-recovery rule today and **neither is the one worth having.**

| | what it does | what it cannot do |
|---|---|---|
| `exec_recovery` on the strategy page | runs the rule over A+'s FINISHED book | never competes for the budget — cannot shrink or block an A+ trade |
| `backtest/tools/recovery_stack.py` | two real legs, one balance, one budget | terminal only, no chart, no stored run, no KPIs |

The stack page already does one balance and one risk budget — but it builds a leg from a
**registered strategy** you pick off a list, and the recovery rule is not a strategy. It has no
setups. It fires off another leg's losses, so it must be handed that leg's live trade list as the
run goes.

🔴 **The gap is not cosmetic and the numbers say so.** MEASURED 2026-08-21, XAUUSD 15m,
2020-01-01 → 2026-08-21, 156,802 bars, no costs, 10% cap:

```
A+ alone            160 trades   $49,214,856   maxDD 45.6%   +141.18R
recovery alone       50 trades   $     15,605  maxDD  7.5%   + 19.07R
both, one account   210 trades   $35,397,735   maxDD 40.4%   (-28.1%)
```

**A+ was shrunk 22 times and nothing was refused; peak open risk 10.0% against a 10% cap; both
legs' R identical shared vs solo.** The strategy page's own switch reports none of that, because
under it the recovery cannot touch A+ at all.

---

## The shape (Aaron's call, 2026-08-21)

**A recovery leg is a TICK BOX ON ITS PARENT, never an item in the strategy list.**

```
  [x] MPC SOS Fade            risk 10%
        └ [x] Loss recovery      size 0.25x
  [ ] MPC B-Leg
```

The alternative — listing it beside the real strategies with a "recovers:" dropdown — was
rejected. It lets you build a stack with a recovery and no parent, or pointed at the wrong parent,
and the run then has to refuse after the work of setting it up. **A dependency the UI cannot
express becomes a runtime refusal, and a runtime refusal is a worse version of the same rule.**

⚠ It is still a full LEG underneath: its own key in the account, its own reservation, its own
trade list, its own row and KPIs. Only how it is CREATED changes.

---

## The five stages

### 1. A leg may declare a SOURCE

`LegSpec` gains one field naming the leg whose losses this one reads. `run_stack` then orders the
build so a source exists before its dependent, hands over the source's **live trade list object**,
and gives the leg the frame's last bar and its bars-per-day for the time stop.

🔴 **It must be the list OBJECT, not a copy.** The recovery arms when a primary trade closes, so it
reads a list that grows under it. A copy taken at build time is empty forever, and a leg that arms
on nothing produces an empty book that reads exactly like a rule that found no setups.

⚠ A source that names a leg not in the stack must refuse at build, not at the first bar.

### 2. The solo control needs a private source

`run_stack` replays every leg alone as a control — that is what makes the shared/solo delta
attributable. **A recovery leg alone has nothing to recover.** It needs a private copy of its
parent running beside it on a SEPARATE account, generating losses, with only the recovery booking
onto the account being measured. `recovery_stack.solo()` already does exactly this; the runner
needs the same.

⚠ Without this the control is an empty book, and an empty control makes the shared result look
like the whole of the leg's worth.

### 3. Three refusals, all loud

1. **The parent's own `exec_recovery` must be OFF.** Left on, the run books recovery trades TWICE
   — once bolted onto the finished book, once as a real leg — and nothing errors. Same shape as
   the existing `exec_secondary` refusal in `backtest/portfolio/legs.py`.
2. **ATR-based stop modes refuse**, as `RecoveryLeg.__init__` already does: a stack has no
   canonical volatility source and a private copy would be a second implementation of an
   indicator this repo keeps exactly one of.
3. **A recovery leg with no source refuses**, so the tick box cannot be routed round via the API.

### 4. The settings and the screen

The rule has ~20 settings; the seven that matter already have plain-English descriptions written
for the strategy-page switch. Reuse that wording, add a description file for the leg, and it
renders like any other leg.

⚠ **Do NOT reuse the `exec_recovery_*` field names for the leg.** The same seven names would mean
*bolted on afterwards* in one place and *a real competing leg* in the other, which is how somebody
compares two runs that were never measured the same way.

### 5. Retire the old switch

Once the leg works, the strategy-page switch is the worse answer to the same question. Hide it
from the editor (`hidden`, the existing mechanism — the field stays, still settable, one flag
brings it back) and keep its corrected warning.

---

## Already built — needs nothing

The shared balance, the risk budget and its reservations, the refusal log, the contention markers
on the chart, and the chart's handling of a recovery trade (its excursion, and correctly drawing
no target ladder). All of it landed 2026-08-20/21.

---

## What must be true at the end

- A stack of A+ + recovery reproduces `recovery_stack.py` on the same window **to the cent**. That
  is the acceptance test, and it is the only one that proves the wiring did not become a second
  implementation.
- Both legs' R is **identical shared vs solo**. R is normalised to each trade's own risk, so a
  pure sizing change must leave it byte-identical — a moved R is a decision that moved, which is a
  bug wearing a sizing change's clothes.
- A stack of A+ alone is **unchanged** from before this work.
