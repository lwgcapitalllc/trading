# Notes — Command Center integration

How this rule became a real leg in the stack builder, how it was first wired as a post-pass switch on sos_fade, and how it is listed on the Strategies page. Moved VERBATIM out of `strategies/python/loss_recovery/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 It is a real LEG in the Command Center's stack builder (2026-08-21)

The section below describes the strategy-page SWITCH, which is a post-pass and cannot compete for
a budget. This is the other one: the rule now runs as a proper leg of a shared-account stack —
one balance, one risk budget, and it really can shrink or block the leg it recovers.

**`lab.py` is the seam, and it exists because there are two configs for one thing.**
`RecoveryLegConfig` is what the LEG needs: the rule plus the instrument's contract size, the
parent's full-size risk, the structure length and the frame's bar rate. **Four of those five are
not the user's to choose** — they are facts about the parent and the bars. So `RecoveryLabConfig`
is the flat, user-facing half the scanner builds a form from, and `leg_config()` is the ONE place
that joins it to the parent's facts. ⚠ **Nothing else may assemble a `RecoveryLegConfig` from lab
input**, or the parent's risk and the recovery's fraction stop moving together.

🔴 **`LAB_STRATEGY` declares `requires_source`, and that flag is the whole design.** This rule has
no setups — run it alone and it is handed nothing, which returns an empty book **indistinguishable
from a rule that found no setups**. The flag lets the lab state that as a FACT rather than leaving
each picker to remember it: the Strategies page AND this rule's own detail page both grey their Run
button (*Needs a parent*), the stack builder filters it out of the list, and the only thing that can
create one is a tick box under a parent. 🔴 **The detail page was MISSED at first and is the lesson:
a strategy is reachable from more than one place, and guarding the list is not guarding the
strategy.** Both buttons are only LABELS — the gate is `command-center/backend/routers/_source_guard.py`,
which refuses every endpoint that starts a job from a strategy id. ⚠ **It is registered as a strategy ROW anyway** — a stack leg's run row references one, so
without it the leg could carry no params, no KPIs and no chart.

⚠ **Only THREE stop placements are offered** (`STOP_MODES`): structural, the losing trade's entry,
and a fraction of the break leg. The three ATR-based ones are absent because a shared-account stack
has no canonical volatility reading and a private copy would be a second implementation of an
indicator this repo keeps exactly one of — `RecoveryLeg.__init__` refuses them, and offering a
setting the run cannot honour is worse than not offering it. Use `recovery_report.py` for those.

⚠ **A zero size is REFUSED rather than clamped.** A zero lot fills, closes and lands in the trade
list at 0R — a trade that looks taken and moved nothing. The way to stop taking recoveries is to
remove the leg.

⚠ **`soft_stop_r` is 0-means-off on the form and None-means-off in the engine**, translated in one
place — and `sos_fade/recovery.py` translates it identically. The two adapters must agree or
the same setting means two things.

⚠ **The defaults ARE the measured configuration**, so selecting the leg and touching nothing
reproduces the runs recorded in this file. ⚠ **Which is just as well, because the stack builder does
not offer these settings yet** — the request field exists and the backend honours it, but the page
never sends it, so a recovery leg ticked on a parent always runs on its defaults. Anything else
needs the API. Named in `docs/RECOVERY_LEG_IN_COMMAND_CENTER.md` → stage 4.

✅ **The verdict is UNCHANGED by the new path and that is the point of running it: uncosted, at a
10% cap, the leg still costs 28.1% — the same direction as the costed −29.9% below.** SOS Fade was shrunk
22 times, nothing was refused, peak open risk touched 10.0% against the cap, and **both legs post
identical R shared and solo**, which is the check that says only the sizing moved. Numbers, the
five build stages and what each refusal is for: `docs/RECOVERY_LEG_IN_COMMAND_CENTER.md`.

## It is drivable from the Command Center (2026-08-20)

Until now this package could only be run from `backtest/tools/recovery_report.py`, a terminal tool
— there was no config field, so the lab's form (built from `dataclasses.fields` of a strategy's
config) had nothing to render, and `build_results` reads `strategy.execution.trades`, which never
contained a recovery row.

`sos_fade` now carries seven `exec_recovery_*` inputs and a `recovery.py` adapter that maps
them onto `RecoveryConfig`, runs this engine over that bot's finished losses, and appends the
result as `Trade(kind="recovery")`. Everything downstream — KPIs, equity curve, trades table,
chart — then works with no change. **Defaults are unchanged and `exec_recovery` is OFF**; nothing
measured in this file moved.

⚠ **The wiring's facts live in `strategies/python/sos_fade/CLAUDE.md`**, not here — including
the one that matters (turning it on cannot move an SOS Fade trade) and the one approximation it buys
(the two share a balance in one direction only). This file stays the owner of the RULE.

**A resolved trade now reports how far it went AGAINST as well as how far it ran** — `max_adverse_r`
beside `max_favourable_r`, both non-negative magnitudes in the trade's own R, both reporting-only.
Added 2026-08-20 because the lab's price chart draws a trade's deepest point and had nothing to draw
it from.

🔴 **`max_adverse_r` is CAPPED at the exit on the closing bar, and that cap is the whole care in
it.** The stop check runs before the range is read, so the bar that stops a trade out can trade far
past the stop — but the position was already gone at the stop. Measuring the full bar would report a
drawdown the trade never lived through, and a chart would then draw its deepest point BEYOND its own
stop, which is not a thing that can happen. ⚠ **It is only testable on a SYNTHETIC frame**: every
recovery in the real fixture exits locked and in profit, so the reordered walk returns identical
numbers there. A wiring-level version of the test was written, watched still-green, and deleted —
same trap as the five vacuous tests above, found the same way.

## It is LISTED under the SOS Fade bot on the Strategies page (2026-08-21)

`LAB_STRATEGY["display_under"] = "sos_fade"`. Display grouping only — a flat alphabetical list
put a rule that cannot run alone beside four that can.

⚠ **It does NOT pin which parent it may recover.** The stack builder still offers the tick box
under any ticked parent; `recovery_parent` is read off the request and this field is never
consulted for it. The declaration says only where the row is drawn.
