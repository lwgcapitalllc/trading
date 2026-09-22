# Notes — The inherited exit ladder and the recorded-fib convention

How the B-LEG fork inherits the SOS Fade exit ladder unchanged (with its own re-defaulted flags and pinned-off guards), and how it builds and records its OWN fib ladder off the frozen band using the drawing convention rather than the fork's own vocabulary. Moved VERBATIM out of `strategies/python/b_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The exit ladder is inherited (2026-07-26)

The structure runner trail, the TP2 stop-floor dropdown and the two setup toggles were ported into
`sos_fade`, and this bot picks up ALL of them for free — `BLegConfig` subclasses `SosFadeConfig`
and `BLegExecution` subclasses `Execution`, and the exit ladder lives entirely in the parent. The
full register is `sos_fade/CLAUDE.md` → `## The exit ladder`. What is specific here:

- **`exec_bleg` is re-defaulted to True.** `b_leg_strategy.pine` ships `execBLeg = true` (the
  SOS Fade file ships it false), so `BLegConfig` overrides the inherited default to match. It gates the
  B-LEG arm in `_place_entries`; OFF the bot trades nothing, which is its only real use.
- **`exec_aplus` controls the PRIORITY GATE here, not entries.** SOS Fade never places an order in this
  fork, so `exec_aplus=False` doesn't disable an entry path — it drops the "SOS Fade stands the B leg
  down" gate entirely. That is the tuning experiment this file's own notes have called for since
  2026-07-24, now a one-flag run instead of a code edit. The same input was added to
  `strategies/tradingview/b_leg_strategy.pine` under the label "SOS Fade has priority (stand the B-leg down)".
- **This bot OVERRIDES TP1 / TP2 / SL** with its band prices (SL = band origin, TP1 = the broken
  swing extreme, TP2 = the expansion extreme). Everything from the stop staging down — the floor,
  the trail, both dropdowns — is the parent's, unchanged.
- **`exec_min_stop_mode` is PINNED `"Off"` (2026-07-30) and is INERT here.** The parent's
  minimum-stop guard runs inside `_place_entries`, which this fork overrides, so the floor is never
  applied on this path — and there is no `execMinStopMode` in `b_leg_strategy.pine` to be
  parity-checked against. The pin exists so a future parent default change cannot make this config
  claim a guard the code does not run. Structurally the hazard is absent too: a B leg's stop is the
  band ORIGIN, a full band away from the 0.5 entry edge, so it cannot collapse onto the entry the
  way a fib stop can. Porting it is three edits in one commit (Pine input, floor check in this
  fork's `_place_entries`, `cfg_min_stop` export column) followed by `compare_bleg.py`.

`strategies/tradingview/b_leg_strategy.pine` was ported in the same pass and now matches: `execRunnerTrail`,
`execStructTrailBufTk`, `execTp2StopMode`, `execAplus`, and the `lStage2Floor` / structure-trail
exit block copied line-for-line from `sos_fade_strategy.pine`. **Completed 2026-07-28** — that Pine had
fallen a lever behind: it lacked the `"Structure + % ratchet"` trail method (+ `f_swingRatchet` and
`execTrailPct`), still defaulted the TP rungs 30/40, and still called `strategy.exit()` on a 0% rung.
All three were ported, so the two forks are back on ONE ladder with nothing pinned around a gap. **Not ported, deliberately:** `execSlLevel`
(the SL fib dropdown) is meaningless here because the B leg's stop is its band origin, not a fib; and
the pink blocked-trade markers, whose codes describe why an **SOS Fade** setup was refused — in this fork
SOS Fade never trades, so those tags would report the opposite of what a reader would assume. A B-LEG
block tag would need its own code set, which is new design work, not a port.

**That non-port now also holds on the PYTHON side (2026-07-27).** `sos_fade`'s `Execution` gained
`blocks` (the same six codes, feeding the lab price chart's Blocked layer). This fork records none by
CONSTRUCTION: the recording hangs off the parent's `_place_entries`, which `BLegExecution` overrides.
`test_this_fork_records_no_blocked_setups` pins it, so restoring the parent's entry path here can't
quietly switch on tags that would mean the opposite of what they say.

**Same call for the MISSED-setup markers (2026-07-27), but this one is NOT free.** The parent's miss
watch scores how far an **SOS Fade** setup got before it died (2 of 3 / 3 of 3) — meaningless in a fork
where SOS Fade never places an order. Unlike the blocks it runs from `step()`, which this fork delegates
straight to the parent, so it takes an explicit class-level opt-out: `BLegExecution._records_misses
= False`. `test_this_fork_records_no_missed_setups` pins it — a flag is far easier to flip by
accident than an overridden method. A B-LEG version of either marker needs its own code set (what
would "2 of 3" even mean for a frozen band?), which is new design work, not a port.

## The recorded fib (2026-08-11) — this fork records its OWN, and the convention is the design

**Unlike the blocked and missed markers above, this one IS ported — and it had to be built rather
than inherited.** The lab's price chart draws a `Fibs` layer from `Trade.fib`, a ladder the strategy
snapshots when it places the order. That snapshot lives in the parent's `_place_entries`, which this
fork overrides, so **every B-LEG trade carried `fib=None` and the chart offered no Fibs row at all**
— on the bot whose entry, stop and first target are all fib levels of one leg.

**`execution._band_fib(ext, inv, direction, leg_ms)` builds it from the frozen band's own anchors.**
Not from `sig` — the parent's `_freeze_fib` reads the live **Structure** fib, which is a different
leg on a different bar, so inheriting it would have attached a real, fully populated, entirely
plausible ladder describing something the trade was never priced against.

🔴 **THE CONVENTION IS THE WHOLE OF IT, BECAUSE THIS FORK SPEAKS THE OTHER ONE.**

| | measured from | entry | band far edge | stop | TP1 |
|---|---|---|---|---|---|
| this fork's own vocabulary (`bleg.py`, the Pine) | leg ORIGIN | 0.5 | **0.382** | — | — |
| what is RECORDED (`fib_level`, the SOS Fade bot's) | leg EXTREME | 0.5 | **0.618** | 1.0 | 0.0 |

Same two prices, two namings — and `BLegState`'s own docstring already assumed the second one when
it called `*_inv` *the leg origin (fib 1.0)*. The record uses the DRAWING convention so a ratio
means one thing on a chart showing both bots' fibs. **The one visible consequence is that the band's
far edge draws as 0.618**, which reads as wrong until you know it is the same line named from the
other end. `tests/test_bleg_fib.py::test_the_band_far_edge_is_recorded_as_0_618_not_0_382` pins it
in both directions.

Rules that hold it together:

- **All eight rungs, and four are COMPUTED** — through the canonical
  `engines.fibonacci.geometry.fib_level()`, never inline arithmetic. A four-rung ladder reads as
  *this trade had no 0.786* when the level exists on that leg and the bot merely did not act on it;
  the SOS Fade ladder has the identical all-or-nothing rule.
- **The ratios are byte-identical to the SOS Fade bot's, asserted by test.** That also keeps every rung on
  a named factory colour in the browser rather than falling through to grey.
- **`*_ext` / `*_leg_ms` are frozen WITH the band and re-frozen on a migration.** The deepest-band
  rule can replace a band mid-watch, and a kept leg beside a moved band would draw one leg's fib
  around another leg's entry.
- ⚠ **`*_ext` is NOT `*_tgt`.** The target keeps tracking the expansion extreme after the freeze and
  runs past the leg, so reusing it would stretch the ladder to wherever price went.
- **An undatable leg records NOTHING.** A swing predating the replay window has no honest x-anchor,
  and drawing from the entry bar would hide the retracement the fib exists to show.
- **Reporting only** — no rule reads `*_ext`, `*_leg_ms` or `Trade.fib`, so `compare_bleg.py` is
  structurally unaffected (exit 0 at warmup 800, and the baseline reproduces at 99 / +17.8674R).

⚠ **It needed four reporting-only fields on `Signals`** (`bull_bos_high_ms` and its three siblings),
read straight off the structure engine's long-published `bull_bos_h_loc` etc. **Nothing in the
engine changed** — the leg's bar positions were there the whole time and nobody had threaded them
through.

⚠ **EXISTING B-LEG RUNS NEED A RERUN.** The ladder is written into the run's own equity curve at
replay time, so *Rebuild chart* cannot supply it.

## SOS Fade target-level settings inherited (2026-09-20)

This strategy builds on the SOS Fade config, so it inherits three new exit-ladder settings: "Target 1 level", "Target 2 level" and "First target, in R". They are off by default and change nothing here. They are listed in this meta file so the lab page shows them rather than silently accepting them. They have not been measured for this strategy. SOS Fade results: `strategies/python/sos_fade/sos_fade_optimization.md` Run 40.
