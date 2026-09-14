# Notes — Chart rendering and going live

How this bot's trades draw on the price chart (entry, drawdown, best, exit) and the seams that let it satisfy live_contract.py, including why entering at market is declared. Moved VERBATIM out of `strategies/python/extreme_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## What the CHART draws: entry, DD, best, exit (2026-09-02)

🔴 **THIS BOT'S TRADES DREW AS A FLAT BOX WITH NOTHING ON IT, AND NOTHING ANYWHERE REPORTED THAT.**
`backtest/output.py` reads the chart's rich fields off the trade with a `getattr` DEFAULT, so a
strategy that records none ships zeros and the price chart **degrades in silence** to a plain
entry→exit rectangle. Its own comment says so out loud — *"All optional — a runner/trade that
doesn't carry them degrades to the plain entry→exit box"* — and this bot was the one hitting it.
Aaron, looking at two of its trades beside the SOS Fade bot's: *"they should be the exact same style as
sos fade trades and annotations where applicable."*

**MEASURED on all 115 trades of run `29444bb4cbea` before the fix**: the best price, the deepest
price, the exit-fill ledger and the target ladder were empty on **every single one**; only the stop
was recorded. So the chips built from them — best, deepest, the exit marker, the target lines — had
nothing to draw from, and the faint bands that make an SOS Fade trade read as layered had no extremes to
span.

⚠ **It is the ONLY strategy here that was affected, and that was CHECKED rather than assumed.**
`b_leg`, `bos` and `realign` all SUBCLASS `sos_fade`'s execution layer and inherit
its recording; `loss_recovery` records its own. This bot is the only one with an execution layer of
its own, which is exactly why it is the only one that had to be taught separately — **a fact worth
carrying forward: the next strategy with its own execution layer starts here too.**

**What it records now, all of it REPORTING ONLY:** the best and worst price of the hold
(`mfe_price` / `mae_price`, plus their dollar twins), the exit as a real FILL rather than as an
average, and its single target as a rung that banks 100%.

✅ **PROVEN NOT TO HAVE MOVED A TRADE, rather than argued.** The decision stream was digested over
**189,331 M5 bars** (PU Prime `XAUUSD.p`, 2024-01-01 → 2026-09-01) before and after: **51 trades and
174 refusals, byte-identical sha both sides.** ⚠ **The digest is `sha256` over the serialised
stream, NOT python's `hash()`** — string hashing is randomised per process, so two `hash()` values
disagree on identical code, and the first attempt here did exactly that and read as a real
difference.

### The three rules that decide what those numbers MEAN

🔴 **NEITHER EXTREME MAY SIT BEYOND A LEVEL THAT CLOSED THE TRADE.** The widen runs before the
bar's exits resolve, so the raw range includes price *after* the position is flat — and the chart
draws these as its `DD` and `Best` chips, so an unbounded extreme puts a marker outside the trade's
own stop or target line. **MEASURED on the SOS Fade bot when it hit this: 77 of 77 stopped-out trades
reported a deepest price beyond their stop, one of them 2.22R against a 1.0R loss.** It is not an
intrabar-ordering guess — a bracket is triggered BY the move that reaches it.

⚠ **BOTH sides are bounded here, and that is the one place this differs from the SOS Fade bot.** There the
favourable side is deliberately left alone, because its first target is PARTIAL and the runner stays
open, so price beyond it is still the trade's move. **This bot's target closes the whole position**,
which makes the favourable side determinate in exactly the way the adverse side is. ⚠ **Copying
either bot's shape onto the other is wrong in both directions.**

⚠ **The bound is the bracket AS IT STOOD ON EACH BAR, never the price the trade finally exited at.**
A trade that sits deep, recovers far enough to arm breakeven and then scratches really did trade
down there, and that is the single most useful thing its chart can show. Clamping at close instead
collapses that drawdown to the exit and the trade reads as though it never went against you.

⚠ **The entry bar contributes NOTHING, and that is a fact about this entry rather than a
simplification.** This bot enters at market on the bar's CLOSE, so no part of that bar's range
happens after the fill — none of it is the trade's move, and both extremes seed AT the fill. The SOS Fade
bot seeds asymmetrically for the opposite reason: its entry is a resting limit filled mid-bar, so
the rest of that bar IS its move.

⚠ **Best and worst are resolved by DIRECTION, not by which number is larger** — a short's best price
is its low. Getting it inverted puts both chips on the wrong side of the entry and nothing raises.

⚠ **Recording the exit fill matters even though it equals the average here.** This bot closes in one
piece, so the two are the same number — but a leg list is how the chart is told the fills are
KNOWN, which is a different statement from having none, and it draws the exit at a fill rather than
at an average of one.

⚠ **The target's 100% is not decoration.** `backtest/output.py` uses it to tell a real profit target
from a level that banks nothing and only steps a stop; a rung reported without it is drawn as an
unknown rather than as a target.

⚠ **A run finished before this landed carries none of it, and there is no backfill** — recovering
the numbers means replaying the strategy. Re-run it. A run that HAS them but a cached `chart_spec.json`
needs **Reload charts**.

## It can be a LIVE bot now — the seams, and why they cost the replay nothing (2026-09-03)

**This package satisfies `strategies/python/live_contract.py`.** `verify_live_ready()` returns an
empty list; before today it named four missing things and this strategy could not be a bot at all.

🔴 **NOT ONE TRADE MOVED, AND THAT IS MEASURED RATHER THAN ARGUED.** 470,995 PU Prime `XAUUSD.p`
M5 bars, 2020-01-01 → 2026-08-23, default config: **113 trades, digest `e4183861407c6b1e`, before
and after.** Every 6.6-year figure in this file still describes this strategy. ✅ **Parity gate
re-run and GREEN** on `engines/VANTAGE_XAUUSD, 5_29058.csv` with the seams in place.

⚠ **The replay cannot reach any of it, and that is the design rather than a happy accident.** The
per-bar `step`, the position snapshot and the commanded close are only ever called by `algos/live/`;
the one flag that could change an exit is set exclusively by `request_close`, which nothing in the
backtest path calls. **A test asserts that flag starts `None`, and the digest proves the rest.**

**What was added, and the rule each one carries:**

| seam | the rule |
|---|---|
| `signals` / `sequence` | Honest EMPTY stages. The runner drives three; this strategy decides in one. **Splitting its logic to suit the caller would be rewriting the strategy.** |
| `step(sig, seq)` | DELEGATES to `strategy.step` and adds nothing but a report. The four calls per bar are sequenced there, in an order that is part of the strategy — re-sequencing here would be a second implementation of what the gate checks. |
| `request_close` | ARMS a request; `resolve` exits on the next bar through the path a stop or target already takes. **No second closing path.** Refuses while flat rather than latching onto a trade nobody had an opinion about. |
| `snapshot_position` / `restore_position` | Via `LivePositionMixin`. Restore REFUSES an incomplete record — a record missing a field is not a position at the default. |
| `_pos_dir` / `_entry` / `_pend_*` | Read DIRECTLY by the bridge. `_entry` is `None` while flat, never 0.0 — that is a price. |

🔴 **`_EXIT_TAGS` IS A LIVE-BEHAVIOUR DECISION WEARING A NAMING TABLE'S CLOTHES.** The tag's SUFFIX
decides whether the bridge acts. **A target MUST be owned** — this bot sends no broker take-profit
and manages its own target, so nothing else would ever close the position. **A stop must NOT be** —
it is already an order resting at the broker, and mirroring it sends a market close on top of a
stop that is already filling. Both directions are pinned by tests that read the bridge's own list
from source. ⚠ **An exit reason this table has never heard of falls back to a tag the bridge OWNS**,
which is the safe direction: a halt at worst, rather than a position nobody closes.

⚠ **The account-budget seam was ALREADY here and is untouched** — `enter()` has asked the account
before opening since 2026-09-02, and it clamps at the DECISION, before any order exists. That is
the coherent side of the rule the SOS Fade bot had to be moved onto.

⚠ **`_POSITION_FIELDS` is one entry today because the whole position is one object.** A latch added
BESIDE `_Open` rather than inside it would be dropped by a restart in silence. The test compares the
record against `_Open`'s own fields so that day fails loudly.

🔴 **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9.** What changed is that the blockers are gone,
not that it is deployed. ⚠ **It HAS an instance directory since 2026-09-03** —
`algos/markets/fx/instances/extreme_leg_demo/`, registered and BENCHED (`account: null`), so it
trades nothing and the runner refuses to start it. The rules for that file live beside it in
`algos/CLAUDE.md`; the two that reach back into this package are the frame (**M5** — on M15 the
trigger and the target collapse into one series and it never fires) and the fact that
`skip_transitioning` is ON in its params, which is the half no parity gate can ever check.

### It DECLARES that it enters at market, and without that it could not open a position at all

`entry_style = "market"`, read by `algos/live/` and by nothing else — no replay, no cost and no
decision reads it, and the digest above is unchanged with it in place.

🔴 **IT IS THE ONE THING THAT SEPARATES THIS BOT FROM A BROKEN ONE, AND NOTHING OBSERVABLE COULD
HAVE TOLD THEM APART.** `enter()` fills inside this emulator DURING the step, so by the time the
bridge reconciles, the position exists here and the broker holds nothing. For a strategy that rests
a limit, that state means the limit filled in one book and not the other — the 2026-08-07
divergence — and the bridge must HALT. Here it is one instant old and the bridge must place the
order. **Same position, same direction, same entry fill on the decision, same empty broker book.**
So the bridge asks; it does not guess. Rules: `strategies/CLAUDE.md` → *Every order layer DECLARES
how it opens a position*.

⚠ **The bridge's own fallback is `"resting"`, i.e. the HALTING one.** A typo here does not disable
a feature — it stops the bot on its first setup. `verify_live_ready` refuses an unrecognised value
by name at startup so that fallback stays a backstop.

⚠ **It does NOT mean this strategy sizes its own live order.** The broker's lot count still comes
from the live sizing seam, off the BROKER's balance and under the account's remaining risk. What
this decides is which ORDER is sent.

🔴 **THE BOT MUST NOT BE GIVEN A SECOND BAR STREAM.** The bridge mirrors a market entry on the
primary clock only; a fill clock would reach the same disagreement with no path to open it and
halt. It has no re-entry to ask for one, and the bridge REFUSES the combination rather than
running one clock inert.

**Tests: 18 in `tests/test_live_seams.py`, 9 mutations watched RED.** ⚠ **They parse
`BRIDGE_OWNED_EXITS` out of the bridge's source rather than importing it** — importing
`algos.live.bridge` from a strategy test drags in the whole live import graph, and this repo already
forbids the reverse coupling for the same reason.
