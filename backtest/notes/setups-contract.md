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

## `paused_by` — the rules keeping a live setup's order off the book (2026-09-16)

A tuple of rule names, empty by default. It is not `blocked_by`: that one is reported only for a
fully ready setup, and a resting limit can be pulled from a setup whose zone is still untagged.
The live alert layer uses it to post one `LIMIT WITHDRAWN` reply. **Reporting only; no stored run
moves** — `replay_fingerprint.py` 2024-01 → 2026-08 on sos_fade: 62,468 bars and 66 trades
identical. Detail: `algos/notes/telegram-and-notifications.md`.

## `alert_rate.py` measures the extreme-leg bot too (2026-09-16)

- `--strategy extreme_leg` is listed; a config with no fill-model field is built without one, and
  a strategy that takes its frame is told it (`--tf 5`).
- `--server PUPrime-Demo` reads that broker's cached bars without the agent.
- The extreme-leg figures and why its root waits for the shift:
  `strategies/python/extreme_leg/notes/setup_alerts.md`.

## `touched` and `leg` — what a research study needs to see a setup at the right bar (2026-09-28)

Two optional fields, both **reporting only**, added so `backtest/setup_feed.py` can hand a study
each setup at the bar the strategy learns of it.

- **`touched`** — price has reached the setup's entry zone at least once (a latch). **`None` means
  the strategy does not say, never "no".** ⚠ **It is not the zone confluence**: SOS Fade's zone
  confluence also wants a gap in the zone, and its 1-minute SOS-then-BOS entry starts watching at
  the touch alone. SOS Fade fills it from the same latch that entry reads (0.5 or 0.618 tagged).
- **`leg`** — `(extreme, origin)`, fib 0.0 and 1.0, copied from the strategy on this bar. `None`
  while no fib is live, the same rule `zone` follows. The extreme extends while a setup lives, so a
  study freezes it at the bar it chose.
- 🔴 **Why: the Generic FX studies anchored each setup on its MISS record**, whose zone time
  brackets the deepest visit to the zone and is known only once the setup is over. A study said
  +0.26R a trade and the lab made -0.06R. Detail: `backtest/notes/study-reconciliation.md`.
- **No stored run moves — proven by replay, not argued.** SOS Fade Generic GBPJPY with lab run
  `8bcf06ffa418`'s settings, 15m + 1m, 2020-01-01 → 2026-09-26: 213 trades, SHA-1
  `ca7dd57e…` before and after, the same count as the lab run. SOS Fade (defaults, XAUUSD.p, 15m
  + 1m, same window): 252 trades, SHA-1 `4a4485d2…` before and after.

## `setup_feed.py` — the point-in-time setup feed a study reads (2026-09-28)

`replay_setups(strategy, df, warmup)` runs the strategy through its OWN `run()`, drains its setup
snapshots after every bar, and returns each one stamped with the bar that reported it (`bar_ms`,
the open) and when the strategy knew it (`known_ms`, the close). `episodes(rows, condition)` groups
them into unbroken runs of bars per setup — a setup that stops qualifying and comes back is a NEW
episode, which is how the 1-minute entry treats it too.

- **It builds nothing new about a setup.** Every row is the snapshot the live alert channel reads.
- **It REFUSES a strategy that cannot answer**, and a `run()` that does not step once per bar —
  the bar stamp comes from counting steps, so a strategy that steps any other way would be
  stamped wrong rather than fail.
- **A study must not act on a row before `known_ms`.**
- Tests: `tests/test_setup_feed.py` (7; 4 watched RED by mutation — grouping, restoring the
  execution, the close stamp, and the refusals).

## `reentry_of`, `origin_ms`, `planned_entry` — a re-entry reported as one more setup (2026-10-02)

🔴 **Why: on 2026-10-01 the live SOS Fade bot re-entered with no warning.** A setup's thread closes
when its first trade fills, so nothing said a second chance was open (first trade closed at
breakeven 08:15 UTC, re-entry filled 08:17).

- `reentry_of` — the key of the setup this is a second chance at; `None` on every ordinary setup.
  The alert layer opens a NEW thread in re-entry wording for one, and never learns what makes a
  re-entry possible — those words are the strategy's confluence details.
- `origin_ms` — when that setup formed, so the message can name it. `None` names no time.
- `planned_entry` — a price the strategy has already decided, before any order exists (the reclaim's
  level, or the live gap edge). Deliberately NOT `entry`, which means an order IS resting there.
- ⚠ **Reporting only, like every field here.** All three default to `None`, so no existing strategy,
  snapshot or stored record changes. The SOS Fade side is `strategies/python/sos_fade/reentry_watch.py`.
