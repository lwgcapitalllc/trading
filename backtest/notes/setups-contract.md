# Notes — The setups.py contract

The contract a strategy fills in to report what it is watching. Moved VERBATIM out of `backtest/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## `setups.py` — the contract a strategy fills in to report what it is WATCHING (2026-08-13)

The SHAPE of a pre-trade setup alert, so `algos/live/setup_alerts.py` never knows which strategy
it is talking to. A strategy answers `live_setups()` / `drain_setups()`; nothing else changes when
a new bot wants alerts. Messages, wording and volume: `docs/LIVE_SETUP_ALERTS.md`. The build
narrative is in `docs/BACKTEST_BUILD_NOTES.md`.

- **`met`/`of` are DERIVED from the confluence list, never stored.** That is what stops "2 of 3"
  being a hardcoded number: a four-confluence strategy reports 3 of 4 with no change downstream.
- **It lives HERE because it is the one layer both `algos/live/` and `strategies/python/` already
  import, and a strategy must NEVER import `algos/`** — that points the deployable at the
  deployment.
- **`zone` and `entry` are different questions; neither substitutes for the other.** `zone` is
  `(shallow, deep)`, the whole tradeable range, known as soon as the setup arms — the thing worth
  saying BEFORE an order exists. `entry` is the one price an order rests at, `None` until there is
  one. No meaningful range ⇒ `zone=None`, never collapsed onto `entry`.
- **REPORTING ONLY, and proven by REPLAY rather than argued.** Adding it to a strategy means
  replaying full history at HEAD and at the working tree and requiring a byte-identical trade
  list. For `sos_fade`: 155,807 M15 bars, **159 trades / sum R +142.177389, SHA-256
  `b52816e7…` identical both sides** — the documented baseline to six decimals. **No stored run is
  re-priced and no documented baseline moves.**
- **`implements_contract` must not CALL the method.** A question about SHAPE may not execute
  strategy code, and a `try/except AttributeError` around a call swallows a genuine error inside a
  real implementation as "not implemented".
- 🔴 **`reports_setups = False` opts a subclass out, and it exists because INHERITANCE produced the
  empty-registry failure by itself.** `b_leg` and `bos` subclass `sos_fade`'s
  `Execution` and both set `_records_misses = False` — the flag gating the one method that
  populates the setup context — so they inherited a `live_setups()` returning `[]` on every bar
  forever. A method-presence check called them supported. **An empty registry answering
  confidently, arriving through a base class rather than a literal `{}`.** It is DERIVED from
  `_records_misses`, so a new fork cannot acquire a silent, empty channel by forgetting a line.
- **`announce_resting` (2026-08-14) gates the "limit resting" MESSAGE and nothing else** — not the
  root, not the outcome, never a trade; the order is still placed the moment the setup arms.
  **The STRATEGY decides when its own resting order is worth announcing**, because only it knows its
  geometry — this layer has no price and must never learn what a fib is. ⚠ **Defaults True**, so a
  strategy that does not implement it announces as before; the opposite default would make a
  forgotten line look like a quiet market. 🔴 **Setting it False owes a guarantee that it goes True
  before any fill it would suppress**, or a real trade reaches the trades room unannounced —
  `alert_rate.py` checks exactly that, and it is `tradeable`'s failure mode one field along. For
  `sos_fade` the guarantee is geometric, not measured: the threshold is shallower than the 0.5
  entry band, so price cannot fill without crossing it. **No baseline moves — 155,807 M15 bars at
  HEAD and on the working tree give an identical 159-trade list, sum R +142.177389.**
- **`tradeable=False` means the strategy has ALREADY decided no price path reaches a fill**, and
  the alert layer suppresses those (Aaron: *"I should only be getting signals for the trades
  originating from my default settings"*). ⚠ **A merely-unmet confluence is NOT untradeable** — it
  is the normal state of every setup before it fills, and getting this wrong hides real signals
  silently. A rule that can lift while the setup is alive belongs in `blocked_by` instead.
- **`alert_rate.py` CHECKS the invariant that every trade was announced first** — 159 trades
  closed, 158 ENTERED, the one gap being the warm-up boundary. It prints 🔴 BROKEN above one,
  because that is precisely how `tradeable` fails: suppress one setup too many and a real trade
  reaches the broker never having been signalled, with nothing reporting a skipped message.
- 🔴 **A strategy that has not implemented it gets NO alerts and the runner SAYS SO by name at
  startup — never a silent `[]`.** That is the empty-registry shape that had three jobs here
  running for weeks reporting success; *no setups* and *cannot ask for setups* must not be the
  same value. **Do not stub it to make a bot "supported".**
- **`tools/alert_rate.py` measures the volume, and it drives the REAL pipeline** with the sender
  replaced by a collector — so it counts messages SENT, not transitions underneath them. 🔴 **Those
  differ by 2x and the spec's guess was wrong**: it inferred ~3/month for the resting-limit alert
  where raw transitions give 665 over 6.5 years and per SETUP it is 332 (4.2/month), because a
  limit is rebuilt every bar and flickers. End-to-end: **20.2 messages/month, one every 1.5 days,
  26% of announced setups became trades.** It also CHECKS the invariant that every trade was
  announced first (159 closed, 158 ENTERED — the one gap is the warm-up boundary) and prints
  🔴 BROKEN if more than one trade arrives unannounced. ⚠ **Re-run it per strategy and after any entry-logic
  change** — same standing as `overlap_audit.py`. It **REFUSES** for a strategy without the
  contract rather than printing a rate of zero, and it accepts EVERY Python strategy including
  those — an honest refusal naming why beats argparse rejecting the name as though the strategy
  did not exist.
