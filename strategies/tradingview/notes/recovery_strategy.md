# Notes — recovery_strategy.pine — the SOS Fade book plus a loss-recovery leg

The full write-up of `recovery_strategy.pine`: what differs from `sos_fade_strategy.pine` line by line, the rule the recovery leg adds, and the divergences from the Python twin still open at parity time. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## `recovery_strategy.pine` — the SOS Fade book plus a LOSS RECOVERY leg (new 2026-08-19)

**A FORK of `sos_fade_strategy.pine`, not an edit to it, and the reason is mechanical.** A recovery
trade is open AT THE SAME TIME as a primary. That file's bookkeeping assumes one position:
`strategy.position_size == 0` means *"the trade closed"* at **13 arming gates** and at the
WIN/LOSS grader (`closedR`), while `strategy.netprofit`, `strategy.position_avg_price` and
`math.abs(strategy.position_size)` are all TOTALS feeding `openRiskUsd` — the divisor every trade
is graded in. Open a second position there and **the primary silently stops grading its own
trades**; nothing errors and no plot changes shape. Forking is also what this directory already
does for variants (`b_leg_strategy.pine`, `bos_strategy.pine`).

⚠ **NOT COMPILED.** Written against the Pine v6 reference and never run on a chart. Expect syntax
fixes on first paste. **Nothing here has been verified by anything.**

### What differs from `sos_fade_strategy.pine` — 294 changed lines, every one marked `[REC]`

| | |
|---|---|
| `pyramiding` 5 → 8 | primary + 4 adds already fills 5; the recovery needs its own slot |
| `f_isRec` / `f_primarySize` / `f_primaryEntryPx` / `f_recSize` / `f_recEntryPx` | a recovery order is any entry id starting `Rec`; every global that was a TOTAL now has a primary-only twin |
| `posPrimary` replaces `strategy.position_size` | **30 sites** below the helpers, including all 13 arming gates, both open-transition detectors, the position box and the scale-in blocks |
| `primaryNet` replaces `strategy.netprofit` | in `netAtEntry` and `closedR`, so the two legs cannot credit each other |
| `f_primaryEntryPx()` replaces `strategy.position_avg_price` | it would blend the recovery's fill into `lEntry`/`sEntry` and therefore into `openRiskUsd` |
| group **11** inputs | `recEnabled` (**default OFF**), size %, both-directions, lock-at / lock-to, trail, day cap, scratch band |

🔴 **THE FIRST PASTE FAILED ON `CE10095: "G9" is already defined`, and the cause is worth keeping.**
The recovery group was numbered 9 because the panel contract's own table lists 9 as *Drawing: Fibs*
and this file has no fibs — so 9 read as free. It was not: `sos_fade_strategy.pine` declares **both**
`G9 = "9 · Drawing: fibs"` and `G10 = "10 · Drawing: sessions"`, and the new declaration was
inserted directly above the existing one. ⚠ **The contract's numbering is the ADDRESS, not an
inventory of what a given file uses** — read the file's own `var string G*` block before claiming a
number. The recovery group is **G11 / "11 · Loss recovery"**; renumbering the two drawing groups
instead would have moved every existing input to a new group in anyone's saved chart settings.
✅ Checked afterwards rather than assumed: all 24 new identifiers (`f_isRec`, `posPrimary`,
`primaryNet`, `f_recSize`, every `rec*`) are absent from `sos_fade_strategy.pine`, and
`indicators/tools/check_active_order.py` passes.

✅ **That acceptance test PASSED on 2026-08-19** — identical book with `recEnabled` off, so all
30 `posPrimary` substitutions are right.

🔴 **THE SECOND PASTE — recovery ON — DIED MID-RUN ON A DRAWING CALL, AND A HALT IS NOT A DRAWING
BUG.** `Error on bar 70887: Bar index value of the 'left' argument (58907) in 'box.new()' is too
far from the current bar index.` TradingView refuses a `bar_index` anchor past ~10,000 bars and
**stops the script there**, so the trade list silently ENDS at that bar — the numbers under it are
a partial run that looks like a finished one. ⚠ **Read a Pine "Caution!" as a truncated result,
never as a cosmetic complaint.**

The anchor was `PosBox.entryBar`, reached by elimination: with the defaults, sessions and the
sniper zone draw nothing and every FVG box anchors at `bar_index - 1`, so the position box owns the
only `box.new` in the file whose left edge can travel. Two fixes landed together, and the second is
the real one:

| | fix |
|---|---|
| `POSBOX_ORIGIN_CAP = 9000` | every left anchor is clamped, the same guard and the same reason as `EQ_ORIGIN_CAP`. A trade longer than the cap draws from the cap. Cosmetic loss; the alternative is the script dying. |
| the STRANDED HANDLE | a primary can close and reopen on ONE bar — a stop and a resting limit filling together. Neither *flat now* nor *flat last bar* held, so **neither** the open branch nor the close branch fired: the box handle and `entryBar` stayed pinned to a dead trade, and each further same-bar flip pushed the anchor further back. `pbFlip` now makes a flip an explicit close **then** open, in that order. |
| `f_isRec` in the fill loop | a recovery exit was being banked against the PRIMARY's `p.t1`, so a recovery closing in profit painted the primary green — the same blend `f_primarySize` exists to prevent. |

⚠ **The stranded handle is a LATENT BUG IN `sos_fade_strategy.pine` TOO** — it is the shared drawing
code, not anything the recovery leg added; the recovery leg only perturbed the run into reaching
it. It has not been fixed there, because that file is LIVE-adjacent and the change deserves its own
pass. ⚠ **The ordering inside `f_posBox` is now bank → close → open → grow, and that order is
load-bearing**: with open running first, a same-bar exit was banked as a fill on the trade that had
just replaced it.

🔴 **AND THEN THE ANSWER TO THAT CHECK CHANGED WHAT THIS FILE IS FOR. TRADINGVIEW CANNOT RUN THE
RECOVERY RULE, AND ITS P&L IS NOT THE RULE'S P&L.** A Pine strategy holds **one net position** and
has no hedge mode: an entry opposite the open position REVERSES it. So when a recovery is open and
the primary enters the other way, Pine closes the recovery to make room. ⚠ **The direction of the
damage is the opposite of what it sounds like — the PRIMARY is never blocked; the RECOVERY is the
leg that dies**, cut at the primary's entry price instead of at its own stop or trail. That was the
first thing asked and the first thing checked.

MEASURED on Aaron's Sept-2025 → Aug-2026 M15 chart, from the two chart-data exports in `engines/`
(`VANTAGE_XAUUSD, 15_09390.csv` recovery off, `…_adf26.csv` on): **25 primary entries on identical
bars in both runs** (7 long, 18 short — the leg disturbs nothing), **8 recovery trades**, and **5
of the 8 meet an opposite primary entry — two of them inside 2 days, against a 4-day median hold.**

🔴 **The design error was mine and it was an ASSUMPTION, not a slip: this file's header asserted the
two legs could be open at once, and nobody checked the platform before the work was commissioned.**
The Python twin runs the recovery as its own independent book (`LossRecoveryEngine.run()` takes the
bars and the loss list and never asks whether the primary is in a trade), which is why its numbers
are better and why they are the ones to quote. ⚠ **MT5 does NOT have this limit** — separate OS
processes, separate magic numbers — so the Python model is the one that matches the live path.
**TradingView is the odd one out, not the reference.**

⚠ **A multi-year chart also cannot SHOW you an old trade.** Pine caps labels, lines and boxes at
500 each and deletes the oldest, so over ~20,000 bars of structure annotation everything older than
a few weeks is gone — primary trades included. Two consequences, both acted on 2026-08-19: the
recovery's entry markers and its stop are now **plots**, which are not drawings and are never
collected, so they survive across all history; and the reliable way to inspect any old trade is the
Strategy Tester's **List of Trades** tab, where clicking a row makes TradingView mark that trade
itself at no cost to the drawing budget.

🔴 **THE RECOVERY LEG IS DRAWN BY THE SAME CODE AS THE PRIMARY, NOT BY A PARALLEL COPY (2026-08-19,
Aaron: *"I want it to show just like how we show winning and losing trades... nothing should be
different"*).** `f_posBox` now takes the leg's size, its own running closed P&L and an `isRec` flag,
and is CALLED TWICE. Same bands, same drawdown shading, same entry triangles, same by-result
recolouring on close. ⚠ **The two legs are told apart by the LABEL'S HEAD TEXT (`▲ RECOVERY LONG`),
not by a different marker** — the same convention a B-Leg trade already follows. The recovery's
`t1` is its **lock price**, because "did it get back to +1R" is the question TP1 asks on a primary.

🔴 **THAT REWRITE ALSO CHANGED THE PRIMARY'S CHART, AND THE BUG IT FIXED WAS ALWAYS THERE: A WINNER
THAT NEVER CLEARED TP1 PAINTED AS A FLAT ORANGE LINE — i.e. it read as a SCRATCH.** Nothing banks a
band unless an exit price clears `p.t1`, and with `execTp1Pct`/`execTp2Pct` both at 0 (the shipped
default) the only exit is the runner stop, so any trade the trail caught below TP1 was drawn as
though it made nothing. It now paints green to its real exit. ⚠ **Expect the primary's chart to look
different after this even though no trade changed** — the drawing was wrong, not the book.

⚠ **A multi-year chart still cannot SHOW you an old trade, and giving the recovery the full
treatment means it INHERITS that.** Pine caps labels, lines and boxes at 500 each and deletes the
oldest, so over ~20,000 bars everything older than a few weeks is gone — primary trades included.
Two ways through it, and they are the answer to *"I'm not seeing any trades on the chart"*: the
Strategy Tester's **List of Trades** tab, where clicking a row makes TradingView mark that trade
itself at no cost to the budget; and turning OFF the drawing hogs (external structure, missed
setups, blocked-trade tags), which is what is consuming the 500. **The recovery's STOP is the one
exception and is deliberately a `plot`** — plots are not drawings and are never collected, so it is
the only thing that still shows where an old recovery locked and how far the trail carried it.

🔴 **THE FIRST THING TO CHECK ON A CHART, BEFORE ANY RECOVERY NUMBER IS BELIEVED: with
`recEnabled` OFF this file must reproduce `sos_fade_strategy.pine`'s book EXACTLY** — same trade count,
same net, same list. If it does not, one of those 30 substitutions is wrong and every recovery
figure is measured on a primary that is no longer the primary.

### The rule itself

Loss → wait for the opposing external CHoCH → market in (fills next open) → stop at the far end of
the break leg → **at +1R move the stop TO +1R** → trail each new confirmed swing → no target →
30-day backstop. Sized at 25% of a normal trade.

⚠ **`st.asl` / `st.ash` ARE the new swing's price on the bar `st.new_swing_low` / `new_swing_high`
fires** — that is how the trail reads a level without a second engine.

### Known divergences from the Python twin, to settle at parity time

1. **Overlapping recoveries.** `loss_recovery` in Python processes each loss independently, so two
   recovery trades CAN overlap. Pine has one `Rec` entry id, so a second loss while one is open is
   dropped. Count how often that happens before treating the two as equivalent.
2. **Fill model.** Python enters at the next bar's OPEN explicitly; Pine gets that from
   `process_orders_on_close = false`. Same intent, and it needs to be confirmed rather than assumed.
3. **`recWant` never expires**, matching Python. An arm with no CHoCH yet is a visible state, not
   a trade that fires late on stale intent.

**Everything measured about this rule, including that it does NOT reduce drawdown and does NOT
smooth the equity curve, is in `strategies/python/loss_recovery/CLAUDE.md`.** Read that before
quoting any figure off this chart.


🔴 **THE RULE THIS FORK DRAWS WAS SEARCHED ON 2026-08-19 AND NOTHING CHANGED — so the fork's
inputs are still the measured ones.** Nine stop placements and six exit ladders were replayed over
SOS Fade's 62 real losses on 186,910 M15 bars, both legs costed. The shipped rule (break-leg stop, lock
+1R at +1R, trail confirmed swings) won. ⚠ **The one challenger that beat it on the headline — a
stop on the CHoCH BAR's own extreme, +24.4R against +16.2R on a 7x tighter stop — goes to −7.4R
once its five best trades are deleted, and holds for four bars.** ⚠ **Aaron's own idea (rest the
stop on the LOSING trade's entry) is 2.4x tighter and resolves in 43 bars instead of 294, exactly
as predicted, and loses 14R** — the primary's entry is a price the market has just been trading
around, so the stop sits in fresh congestion; median MFE falls 1.01R → 0.89R, which a 2.4x smaller
R should have RAISED. Full grid: `strategies/python/sos_fade/sos_fade_optimization.md` →
Run 24; the rule itself: `strategies/python/loss_recovery/CLAUDE.md`.
