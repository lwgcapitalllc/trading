# Notes — Signal watching, naming history and refusal reporting

The A+/SOS Fade name collapse, the two price refusals that now report themselves, and the RETRACE a miss was waiting on. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### 🔴 "A+" AND "SOS Fade" WERE THE SAME STRATEGY UNDER TWO NAMES. THE DISPLAY NAME COLLAPSED 2026-09-04; THE IDENTIFIERS DELIBERATELY DID NOT

Aaron, reading the two side by side: *"but A+ and sos fade is the same thing not so?"* They were —
the Pine was titled `A+ Strategy` while this package, the lab row and the bot were all SOS Fade.
Every human-visible mention is now **SOS Fade**: the chart chip (`SOS FADE`, joining the short
uppercase family beside `REALIGN` and `XLEG`), the confirmation-table row, the input labels, the
alert text and all prose.

🔴 **THE CODE IDENTIFIERS AND CONFIG FIELDS WERE LEFT ALONE, AND THAT IS A MEASUREMENT RATHER THAN
LAZINESS.** `exec_aplus` and `aplus_window` are not internal names — they are a stored CONTRACT:
**48 saved backtest runs carry them inside their `params`, 4 strategy rows carry them in their
schema, and the LIVE bot's own `config.json` states both.** Renaming them orphans the parameters of
every one of those runs, and **a config key the running code has never heard of fails its parse
every 10 seconds and buries the log** (`algos/CLAUDE.md`). It would buy a reader nothing.

⚠ **So `aplusL_sosBar` and friends still say A+ and are the same thing as SOS Fade.** That is the
one place the two names still meet, it is invisible from every screen, and it is cheaper than the
run history.

⚠ **`education/` kept its A+ too, and for the opposite reason** — there it is the SMC course's
generic word for a top-grade setup, not this strategy. Same call as the Bank of England's
"MPC Vote" surviving the de-brand: the letters match and the meaning does not.

⚠ **A bare `A+` replacement is UNSAFE and the guard is a word boundary.** npm integrity hashes
carry base64 like `aA+f`, and a real TradingView export is named `MPC_A+_Strategy_FX_...csv`.
Both were caught by requiring a non-alphanumeric on each side — rewriting either corrupts a file
nobody would think to check.

## `live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *`live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)*.

⚠ **REPORTING ONLY, PROVEN BY REPLAY.** HEAD vs the working tree over 155,807 M15 bars →
byte-identical 159-trade list, SHA-256 `b52816e7…`, sum R **+142.177389**. **No figure in this
file moves.** 244 strategy tests green.

⚠ **The context is captured AFTER the accumulate block in `_record_misses`, not before.** Before
it, `m.zone` had not yet been set on the bar price first tags the band, so the alert reported a
setup as still waiting on a retrace on the very bar it got one. It also has to live there rather
than in `live_setups()` because that is the one place the per-side gates are already resolved
through the enable-toggles exactly as `_armed` reads them — so "armed" means the same thing in an
alert as it does in a decision.

⚠ **`live_setups()` must be called AFTER `step()` returns.** The resting order is rebuilt in
`_place_entries`, which runs after `_record_misses`, so reading `_pend_*` any earlier reports the
PREVIOUS bar's price beside this bar's confluences.

🔴 **A `Confluence.detail` has to stand ALONE, because the alert prints the detail and drops the
name.** `Confluence("Shift of structure", True, "confirmed")` rendered in Telegram as a bare
`confirmed` next to `Swept Day Low`; it says `SOS confirmed` now. **The strategy owns what its own
confluences are called** — `algos/live/alerts.py` must never learn what an SOS is, which is the
whole reason the contract carries text rather than codes.

⚠ **`_MISS_REASON` is read in TWO places** — the Telegram `NO TRADE` reply and the lab's miss
report — and both render it UNDER its `_MISS_LABEL`, so a sentence that restates the label says it
twice. Trimmed 2026-08-13 on Aaron's *"less verbose"*; the facts are unchanged and no code branches
on the text. ⚠ **Both of these are in the version-pinned tree, so a wording change here needs a
`promote.py`** where the same change in `algos/live/alerts.py` needs only a restart.
✅ **Reporting-only re-proven after both edits**: the same replay script over 155,807 M15 bars at
HEAD and on the working tree gives an identical 159-trade list, SHA-256
`30dc1c5b25f39ef795077ac990e9622e846a66e2a038c42ef816224082d31fe6`. ⚠ **That digest is NOT
comparable to the `b52816e7…` in `backtest/docs/BACKTEST_BUILD_NOTES.md`** — it is a different
serialisation of the same trades. The proof is the before/after pair, not the constant.

⚠ **`entry` is read from the ORDER, never recomputed from `sig`** — the identical trap already
recorded for `Trade.fib`: a fib keeps extending while a limit rests.

🔴 **`alert_resting_fib` (2026-08-14, default 0.236) decides WHEN a pending limit is announced, and
it changes no trade.** The order is still placed the instant the setup arms; only the Telegram
message waits. Aaron, on a live send: *"I only want to know a limit is pending when price gets back
to 23.6% of the retracement."* `_announce_ready` latches per leg on the SOS bar once the bar's
extreme tags `fib_level(0.236)` — priced through the canonical helper off the same anchors the fib
engine used, never interpolated from the zone edges.
⚠ **The ratio MUST stay under 0.5 and `__post_init__` refuses otherwise.** Every fill is at 0.5 or
deeper, so price cannot fill without crossing a shallower level first — **that is what makes a
suppressed message provably a setup that never traded**, a guarantee rather than a measurement. At
0.5 the guarantee is gone and a real trade could reach the trades room unannounced.
⚠ **The two event families mirror the trade DIFFERENTLY and one of them was measured wrong first**
— see `_announce_ready`'s docstring. It is deliberately outside the `exec_` namespace and has no
Pine counterpart, so `compare_strategy.py` is structurally unaffected.
✅ **REPORTING ONLY, proven by replay: 155,807 M15 bars at HEAD and on the working tree give an
identical 159-trade list, sum R +142.177389. No figure in this file moves.** Message volume
332 → 301 resting alerts over 6.5 years, and `alert_rate.py` still reports 159 trades / 158
announced — the one gap being the warm-up boundary it always was.

🔴 **Only a READY setup can be reported as BLOCKED, and getting this wrong made the message lie.**
A veto, the final hour or an HTF filter can be live while a setup is merely forming; reporting
that announced setups as blocked which then rested and filled, under a sentence reading "the setup
was ready and this rule stopped it". It now asks the same readiness question `BlockedSetup` does,
and of the CURRENT bar rather than of `m.blk_*`, which latch true for the setup's remaining life.
**Found by rendering the messages against real bars — no test saw it.**

⚠ **`strategy_name` is set by the STRATEGY, not by `Execution`.** `b_leg` and `bos` share
this execution layer, so its own class name labelled all three "Execution" in Telegram.

🔴 **`b_leg` and `bos` INHERIT `live_setups()` and would have claimed a channel they can
never fill.** Both set `_records_misses = False`, which gates the only method populating the setup
context — so they inherited a `live_setups()` returning `[]` on every bar forever, a
method-presence check called them supported, and the runner would have logged "Setup alerts: ON"
for a channel that can send nothing. **The empty-registry failure arriving through a base class
rather than a literal `{}`.** `reports_setups` is therefore DERIVED from `_records_misses`, so a
new fork cannot acquire a silent, empty channel by forgetting a line — and `True` is still not a
claim that a fork's confluences are right: turning the watch back on would report SOS Fade's three
confluences for a setup it does not trade. Each fork needs its own `_setup_context` first.

✅ **The derivation was validated by an event rather than by an argument: `realign` landed on
main WHILE this was being built**, subclasses this layer, sets `_records_misses = False` like its
siblings, and declined the channel correctly with nobody editing anything and nobody aware of a
rule that did not exist when they started. **A per-fork flag would have needed its author to know
that rule.** The test ENUMERATES the forks rather than naming them, so the next one is covered
before it is written, and fails by NAME on whichever starts claiming a channel it cannot fill.

⚠ **`tradeable` is `arm_met` and NOTHING ELSE, deliberately.** The arm source is snapshotted at
the SOS, so a setup armed by a disabled source can never acquire a different one — that is a
decision the strategy has already made. A veto or the final hour can LIFT while a setup is alive,
so those stay reportable and travel as `blocked_by`. 🔴 **The estimate that justified this filter
was wrong by two orders of magnitude**: "220 of 609 are divergence-armed and cannot trade" read
`arm_src` (which source reached stage 1 FIRST), not `sos_l_swp` (was a sweep live at the SOS).
**It fires on ONE setup in 6.5 years, and `miss_audit.py` reports ZERO code-1 misses over the same
window** — the counter that settles it existed the whole time. **A count that is easy to obtain is
not the count you asked for.**

### 🔴 THE TWO PRICE REFUSALS NOW REPORT THEMSELVES — THEY COULD SKIP A LIVE TRADE IN SILENCE (2026-09-03)

**The minimum stop floor and the dead-market gate are both ON in the live bot's promoted params
(`exec_min_stop_mode` "% of price" 0.08, `exec_min_atr_pct` 0.08), and until this date neither
could produce a message a human would ever see.** Every other rule that refuses a ready setup —
the veto, the final hour, the HTF filter — sent a `🚫 BLOCKED` reply. These two sent nothing, so
a skipped trade was indistinguishable from a quiet market. Aaron asked which skip reasons reach
Telegram, and this was the honest answer to *"which ones do not"*.

🔴 **The dead-market gate was WORSE than unreported: it had no code anywhere.** It rides INSIDE
`_stop_clears_floor`, so `_record_blocks` never saw it — no block record, no miss code, no lab
row, no message. The floor at least booked block code 7. **A rule with no vocabulary cannot be
under-reported, because there is nothing to report** — that is why this was silence rather than
an omission, and it is the shape to look for in the next gate that hides inside another one.

🔴 **A SECOND DEFECT FELL OUT OF IT, AND IT WAS THE ONE ACTUALLY LYING TO THE READER.** When
either price rule refused a setup, the `👋 NO TRADE` reply that closes its thread booked miss
code 7 — *"All three met and the limit rested — price never came back to touch it."* **No limit
had ever been placed.** The message named a resting order that did not exist, on the one line
whose whole job is to say why a setup died. Miss codes 8 and 9 are carved OUT of 7 for exactly
this, and `_MISS_REASON` for both says *no limit was placed*.

⚠ **One implementation, three readers — `_price_blocks`.** The blocked record, the miss record
and the Telegram snapshot all ask it, so a message can never describe a refusal the strategy did
not make. It asks the SAME two helpers the placement path asks, with the same edge; it does not
re-derive either rule. A second copy is how two claims about one setup disagree.

⚠ **No edge means BOTH answer False, and that is *not applicable*, never *passed*.** With nothing
to rest a limit on, neither rule has been reached — the setup is stopped a step earlier by
something else, and the reader is not told a dead market cleared a test it was never given.

⚠ **An unseeded ATR still REFUSES the entry but is not reportable as a quiet market.** "Cannot
measure the range yet" and "the range is too small" are different sentences and only the second
is true in those words — the convention `_stop_is_tight` already follows for a missing floor.

⚠ **`tight` / `quiet` carry NO DEFAULT on `_setup_context`.** A default of False makes a caller
that forgot them indistinguishable from a setup nothing is refusing — a declared field standing
in for a measured one. There is one caller; a second that forgets fails loudly at the call.

⚠ **The readiness guard is UNCHANGED and the new rules obey it.** A price rule live while a setup
is merely forming is not what stopped it, and reporting that is the defect recorded two sections
up — setups announced as blocked which then rested and filled.

⚠ **Block code 10 is APPENDED, so `codes[0]` still equals what the Pine's `f_blkCode` would have
returned** and a per-reason count off the primary still reconciles with TradingView. Unlike its
neighbours 8 and 9 (short-hold only, never seen by a shipped run), **10 is SHIPPED AND ON** — it
changes what a real run reports the day it lands.

✅ **REPORTING ONLY, PROVED BY REPLAY, not by argument.** `replay_fingerprint.py` over
157,004 M15 bars + M5 (PU Prime `XAUUSD.p`, 2020-01-01 → 2026-08-23, dual-frame so the re-entry
path is covered): **bars IDENTICAL, trades 200 → 200 IDENTICAL.** ⚠ **The baseline had to be
captured in a scratch worktree with its `monorepo_root` REPOINTED AT ITSELF** — `python_runner`
resolves the strategy through that absolute path, so a worktree left alone loads the MAIN repo's
modified code and the comparison certifies anything at all. It was verified to load HEAD (no code
10, no helper) before the capture was trusted.

✅ **MEASURED message volume, both sides on ONE window** (`alert_rate.py`, same 157,004 bars):
`🚫 BLOCKED` **58 → 67**, i.e. 0.7 → 0.8 per month — **nine extra messages in 79.7 months.**
Every other line is unmoved (599 setups, 444 no-trade, 155 entered, 293 resting), which is the
independent read on the same claim the fingerprint makes. ⚠ **Do not compare against the 55 in
`docs/LIVE_SETUP_ALERTS.md`** — that was measured to 2026-08-06 and predates the dead-market gate
entirely, so the delta across it spans a config change rather than this one.

⚠ **NONE OF THIS REACHES THE LIVE BOT UNTIL A PROMOTE.** `sos_fade_demo` is frozen on
`de9ecafa` (promoted 2026-09-02); a pull cannot move it.

### The RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08)*.

🔴 **`MissedSetup.time_ms` is the bar the setup DIED, and something downstream read it as "where
the setup was".** The lab's Candlestick Reversals layer anchored its marks there and painted them in
a part of the chart the setup had nothing to do with — Aaron, off the screen: *"the reversal candle
printed on the opposite side, which doesn't make sense … I'm expecting it to be that price got into
the zone for the trade and there was a reversal candle."*

✅ **MEASURED on the reference run (2020-01-01 → 2026-08-06, 155,807 M15 bars, 35 three-of-three
misses): on 32 of the 35, price sits a median $22 and up to $205 from the setup's own `edge` on the
death bar, which is a median 17 and up to 717 bars after the retrace.** That is correct for a marker
saying *this setup is now over* and useless for anything asking *where was price when it was live*.

🔴 **IT CANNOT BE DERIVED DOWNSTREAM, which is the reason this had to change here rather than in the
consumer.** The cheap fix — scan back from the death bar for a bar that traded through `edge` —
finds one for **all 35**, including the ten whose whole reason for existing is that price never
reached the limit, because price crosses that level at unrelated moments. It would have been
confidently wrong and silent.

🔴 **It must NOT be driven off the caller's `zone_hit`, and that is the subtle half.** `zone_hit` is
`l_half or l_618` — a **LATCH**: once price tags 0.5 it stays true until the leg resets, so every bar
to the death reads as "in the zone" and the visit measures 717 bars. `_MissWatch.visit()` asks the
BAR instead — does its range overlap `[fibo_p2, fibo_p6]` — which is the question the latch answered
once and then remembered. ✅ **That one change took the median span 17 bars → 3.**

⚠ **The DEEPEST visit is reported, not the first or the last.** A setup can tag the zone, leave, and
come back — those are different retraces, and the one worth reporting is the one that came closest to
filling.

⚠ **REPORTING ONLY, and proven so rather than argued**: the strategy replayed at HEAD and at the
working tree over the full **155,807 M15 bars** produces a byte-identical 159-trade list (same
SHA-256 over every entry time, direction, entry price, exit price, R and exit reason).

✅ **6 new tests in `tests/test_execution.py`, three MUTATION-proven** — dropping the band test (the
latch bug restored), reporting the first visit instead of the deepest, and flipping the direction
each turn a different one red. `_seq_short_ready` / `_seq_short_dead` were added for the last of
those: the adverse extreme is the highest high on a short, and a long-only fixture cannot see it
being backwards.

⚠ **"No FVG in zone" is a DIAGNOSTIC, not a to-do list — corrected 2026-07-29 (Run 12).** This
section used to call that bucket "the actionable number this whole layer exists to produce". It was
then measured over 6.5 years (2020-01-01 → 2026-07-29, 155,186 M15 bars) by replaying the same bars
with `exec_req_fvg` off, and **taking those setups is not worth it**: 180 no-FVG misses, 173 fill at
the 0.618 fallback, **50 win / 54 loss / 69 breakeven** (median +0.04R) for +34.0R gross — of which
**40% is one January-2020 trade**, and they crowd out 17 real trades worth +21.0R, so the net is
+13.0R on a 110.6R book while max drawdown goes **54.9% → 77.1%**. The sign also flips with the
counterfactual entry price (+13.0R at fib 0.618, **−6.7R at 0.5**), which is the signature of noise
rather than an edge. Deepening the entry and loosening which gaps qualify are both worse still.
**Read the layer as "why didn't this trade", never as "here is missed money"** — full record and the
three other routes in `sos_fade_optimization.md` → Run 12 / 12b.
