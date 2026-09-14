# CLAUDE.md — Loss Recovery

**Purpose:** After a strategy takes a real stop-out, take one counter-trade on the opposing
external CHoCH, secure the loss back at +1R, and trail the rest.
**Sweeps:** `loss_recovery_optimization.md`, next to this file — the size sweep and the nine-stop /
six-ladder search, plus the standing rule that both sides must be COSTED or the verdict flips.
**Scope:** Signal + trade management + R accounting. No sizing in lots, no broker calls, no UI,
no structure detection of its own.
**Status:** 🔴 **LAB ONLY.** `enabled` defaults False. No Pine twin exists, so there is no
`compare_*.py` parity gate and there never will be until one is written. Nothing imports this
package outside its own tests and `backtest/tools/recovery_report.py`. It has never been traded.
**Last reviewed:** 2026-08-18 — built this session from Aaron's question "when I lose, can I get
back in the other way and win the loss back?"

---

## The rule

1. A primary trade takes a real stop-out (`r < -scratch_r`; a scratch is not a loss).
2. Wait for an **external CHoCH** on the same timeframe in the **opposite** direction. Median
   wait ~13 hours. No CHoCH, no trade — and `pending()` reports the losses still waiting.
3. Either direction. See *Why both directions* below; this is not a preference.
4. Enter at the **next bar's open** after the CHoCH bar closes.
5. Stop at the **far end of the break leg** — `bull_bos_low` / `bear_bos_high`. That distance is
   this trade's 1R.
6. Size at **25%** of a normal trade's risk.
7. At **+1R**, move the stop **to +1R**. The loss is now paid back and cannot be given away.
8. Then trail the stop to each new confirmed swing level. **No target.**
9. Hard close at 30 days — a backstop against swap, not a working rule.

---

## Why this is a package and not a flag on `sos_fade`

The trigger is "a primary trade lost", which every strategy in this repo can state. Wiring it to
one strategy's concrete `Trade` class would make the second consumer a rewrite, so the engine is
defined against the `LossEvent` **Protocol** (`dir`, `exit_index`, `r`).
`sos_fade.execution.Trade` satisfies it unchanged.

⚠ **`scaled_r`, never `r`.** A recovery trade is taken at a FRACTION of normal size, so `r` (its
outcome in its own risk units) and `scaled_r` (`r * risk_fraction`, what the account sees) are
different units. A journal adds up `scaled_r`. Booking `r` overstates the contribution 4x at the
default size — the same class of error as handing MT5 ounces where it wanted lots.

---

## Why both directions

**`both_directions=False` is the one FITTED choice available here, and it is off by default.**
"Longs only" was picked after seeing that longs beat shorts on this exact record.

The earlier finding that counter-shorts lose −11.8R was measured with a **10R target**, and that
was the wrong test: gold drifts up over this record, so a counter-short almost never travels ten
times its risk. Re-run with the lock-and-trail exit, counter-shorts are **−2.9R over 25 trades**
with no era pattern (−2.6R first half, −0.4R second) — noise around zero, not a losing edge. And
both directions together score **1.49x** against the risk dial where longs alone score **1.48x**.

The shorts are free, they lower the drawdown slightly (the two directions do not lose at the same
moments), and taking them removes the only fitted element in the rule. Take both.

---

## What would have to happen before this trades

1. A Pine implementation and a green parity gate. **It cannot be bolted onto
   `sos_fade_strategy.pine`** — that file assumes one position at a time (`closedR` at line 3869,
   `openRiskUsd`, `netAtEntry` and 13 separate `strategy.position_size == 0` arming gates), so a
   concurrent recovery position makes the primary mis-grade its own trades. It needs a fork, the
   same shape as `b_leg_strategy.pine`.
2. `/live-safety`, in full.
3. **The account-level risk cap.** A recovery trade can open while a primary is still on — that
   is the point of it — and the live allocator that would refuse the second one does not exist
   (root CLAUDE.md → *Risk is budgeted per ACCOUNT*; `docs/LIVE_TRADING_PIPELINE.md` → G10).
4. Re-run `backtest/tools/overlap_audit.py`. This adds a third source of concurrent positions on
   one instrument off one structure stream, and that audit's conclusion is about today's config.

## Key paths

| | |
|---|---|
| `config.py` | every knob, with the measured default and why |
| `--exits` / `--soft-curve` | the exit grid and the soft-stop curve on `recovery_report.py` |
| `types.py` | `LossEvent` protocol, `RecoveryTrade`, `ArmedSignal` |
| `engine.py` | the state machine; consumes `engines/market_structure` public events only |
| `tests/` | 32 tests + the real-bar fixture |
| `backtest/tools/recovery_report.py` | the runner that produced every number above |

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 46 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/drawdown_and_return.md` — Drawdown and compounding — measured effects

**Read before touching:** before quoting the 1.53x figure, or any drawdown/balance number for this leg.
Most-cited code: `recovery_report.py`, `sos_fade/recovery.py`, `leg.py`, `backtest/tools/recovery_stack.py`.

- MEASURED
- 🔴 It does NOT reduce max drawdown. It buys RETURN.
- 🔴 It does not smooth the equity curve either — and this qualifies the 1.53x headline

### `notes/stop_and_exit_search.md` — Stop and exit search

**Read before touching:** before proposing a different stop or exit for the recovery trade.
Most-cited code: `jitter_audit.py`.

- 🔴 A tighter stop does not make the loss smaller. Holding 1R FIXED is what does.
- 🔴 The stop on the LOSING TRADE'S ENTRY — Aaron's idea, and it loses 14R
- The stop search — six placements, and the one that beat the default was five trades
- 🔴 The +1R exit is not what costs the runners — and the money after it is a RE-ENTRY, not a trail
- Why the exit is the whole thing

### `notes/tests_and_validation.md` — Tests and the vacuous-test lessons

**Read before touching:** before adding a new test to this package, or trusting a green run of it.

- Tests

### `notes/command_center_integration.md` — Command Center integration

**Read before touching:** before touching how this package is driven from, or displayed in, the Command Center.
Most-cited code: `lab.py`, `command-center/backend/routers/_source_guard.py`, `recovery_report.py`, `sos_fade/recovery.py`, `backtest/tools/recovery_report.py`, `recovery.py`.

- 🔴 It is a real LEG in the Command Center's stack builder (2026-08-21)
- It is drivable from the Command Center (2026-08-20)
- It is LISTED under the SOS Fade bot on the Strategies page (2026-08-21)
