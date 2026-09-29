# The 1-minute SOS-then-BOS entry — `exec_shift_entry` (built 2026-09-28, ships OFF)

Aaron, 2026-09-28: *"lets keep going can you prove it?"* — the screen
(`backtest/tools/generic_ltf_trigger.py`, `docs/SOS_FADE_GENERIC_SPEC.md` → *With costs, and
GBPUSD on 1-minute*) found that a zone touch entered only after a 1-minute SOS and then a BOS made
+0.26R a trade net on GBPJPY and +0.19R on GBPUSD, with the structure-blind control flat. A screen
takes every setup and has no position slot, no sizing and no minimum stop. This is that trade built
into the strategy so a lab run can price those.

## The trade

- **Setup:** a live 15m setup — armed by an enabled source, SOS'd, pullback tagged the 0.5, the 15m
  fib still pointing its way. Its 1.0 and 0.0 are FROZEN at the first 15m close that reports the tag.
- **Signal:** on the fill-clock structure feed (1 minute, refused otherwise), an external SOS its
  way, then a later external BOS on a bar that is not itself an SOS.
- **Entry:** market, next 1-minute open, through the re-entry's order path. Full `exec_risk_pct`.
- **Exits:** stop at the 15m 1.0, never moved before the target (it follows the PRIMARY's
  breakeven rule, which Generic pins off); the whole position off at the first target — the 15m 0.0,
  or `exec_tp1_r` off the real fill.
- **Retire:** on the first 1-minute wick to the 1.0 or the 0.0, and on its first SOS-then-BOS
  whether or not the slot was free.
- **With it on, no first-trade limit rests at all** — `_place_entries` is handed no edges.

## Rules

- 🔴 **The fast feed is decided by `dual_clock.FAST_CLOCK_FLAGS`, never one flag.** The lab's
  `run_feeds.py` keeps a pinned copy. Before this the lab loaded the fast feed for the re-entry
  only, so the level memory was silently dead in every lab-app run with the re-entry off — fixed in
  the same change (the command-line `run_report.py` already knew about it).
- ⚠ **`_OWN_TRADE_SRCS`** — the level memory and this entry borrow the re-entry's order path but
  are not re-entries: no `exec_sec_*` override reaches them and their stop-out kills no re-entry leg.
- ⚠ **The tag is only known at the 15m close**, so a BOS inside the tag bar is missed; an SOS
  inside it still counts. The screen saw both.
- ⚠ **A closed trade records `kind = "secondary"`**, because it uses that path. In a Generic run it
  is the only fast-clock trigger on, so every secondary trade is this entry.
- ⚠ No Pine counterpart. The parity gate is structurally blind to it.

## Tests

`tests/test_shift_entry.py`, 19 tests. Each rule test was run against a mutation of its rule and
went red; one (*BOS on the SOS bar*) went GREEN on its first draft because the scenario had no
earlier SOS, and was rewritten until its mutation failed it.

## Measured

**Reject — not proven** (2026-09-28): −0.078R a trade over 438 trades on GBPJPY and GBPUSD, losing in every date half, minimum stop on or off. Detail: `docs/SOS_FADE_GENERIC_SPEC.md` → *The lab run*. Ships OFF and stays OFF.
