# Notes — Trade box geometry and the pinned readout

The fixes behind what a trade box draws — how far its adverse band reaches, whether an exit is drawn, and what the pinned readout says. Moved VERBATIM out of `command-center/frontend/src/components/ChartPanel/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## `Deepest` → `DD`, `Furthest` → `Best` (2026-08-21)

Aaron's ask, and the second half was left to me. Both were the widest chips a trade draws, both
land in the cluster the de-collider is already pushing apart, and neither word carried more than
its short form. **`DD` is his; `Best` was chosen over `Reached` and `Peak`** — the favourable
extreme of a SHORT is the LOWEST price on the chart, so `Peak` points the reader at the wrong half
and `Reached` leaves *reached what?* unanswered, while `Best` reads the same on either side.

⚠ **They are DISPLAY strings and nothing keys off them** — the fields are still `mfePrice` /
`maePrice` end to end, and `services/candle_overlays.py` still calls the adverse extreme "deepest"
in its own reasoning, which is correct there and is not this chip.

## 🔴 Nothing adverse is drawn past the stop on a trade the stop closed (2026-08-22)

Aaron's call: *"if my stop loss stopped me out, no need to show the drawdown. I was stopped out.
There's no drawdown. I lost."* Three marks are suppressed together — the faint tail band beyond the
stop, the `DD` dot and label, and the **win/loss chip's parking height**, which was the loudest of
the three: on a 1.0R stopped-out short it sat a full 1.2R above that trade's own `SL` line, reading
as a trade that kept losing after it was closed.

⚠ **It is also not a preference — the number was wrong.** The bot widened the hold's worst price
with the whole closing bar before resolving that bar's exits, so a stop-out kept the bar's far end.
Fixed at source (`strategies/python/sos_fade/execution.py` → `_widen_hold`), where 77 of 77
stopped-out trades on run `976aff9ec279` were affected. **This guard is what makes every run STORED
BEFORE that fix read right too, because nothing backfills them.**

🔴 **Detected from the PRICES, never the exit reason.** An exit's reason string here is the
BRACKET that closed, not the trigger — a trade that lost exactly 1.0R at its stop is labelled
`S-TP1`, and on run `976aff9ec279` **not one of the 78 stop-outs carried a stop-shaped reason at
all**. Keying on the label would have silently missed every one of them.

⚠ The arithmetic it mirrors is tested on the python side (`tests/test_excursion_bounds.py`,
7 tests, 5 mutations); the drawing rule itself is now in `tradeGeometry.ts` and in the suite —
see the next section.

## 🔴 The adverse band ends where price WENT, and every trade draws its exit (2026-08-25)

Both rules live in **`tradeGeometry.ts`** — pure arithmetic, no imports — and are checked by
`scripts/check_trade_geometry.mjs`, **step 8 of `scripts/run_all_tests.sh`**, which needs nothing
running. Read that file's header for the mutation map; it was RUN, not reasoned.

**The band's floor is the worst price the trade actually traded, and it reaches the stop only when
the stop actually filled.** It used to run entry→stop for anything with a negative net P&L, and
the premise — *a loser lost at its stop* — is false for the commonest small loser this strategy
makes: one that comes off at its **staged breakeven stop a few ticks ABOVE the entry** and goes
negative on **costs alone**. On the long of 2020-10-13 (entry 1901.71, exit 1902.01, stop
1879.72306) price bottomed at 1882.36 and the band was painted 2.64 further, to a level the trade
never traded — **contradicting the `DD` marker printed inside it**.

⚠ **The floor is clamped to the stop even when the stop did NOT close the trade** — a worst price
beyond an unhit stop is a defect, not a measurement, and nothing backfills a stored run.
⚠ **A stop FILL is stronger evidence than the recorded worst price**, so that branch is not
redundant with the clamp. ⚠ **An absent worst price draws NO band** — rule 1.

**Every FILL is drawn, and the trade's `exitPrice` is NOT one of them.** That price is the
size-weighted AVERAGE of the fills: on a one-fill exit it IS the fill, and on a two-fill exit it is
a price nothing ever traded at. Drawing it as an `Exit` line put a third chip between two real ones
32 cents apart on the re-entry short of 2020-11-04 (run `6b18811e25d5`, fills 1895.40058 and
1895.72498, average 1895.56278) and shoved both real chips off their own levels.

🔴 **So the fix belongs in `chart_spec.py`, which now emits every fill with a `banked` flag instead
of DROPPING the ones that made no money.** A rung used to have to clear a tenth of the entry risk
to reach the chart at all, so the breakeven-stop trade above had no exit anywhere on it — the one
trade a reader most needs it on. `exitMarker` now returns `leg` whenever any fill is on record, and
only draws the average when the run recorded no fills at all.

⚠ **`banked` ABSENT reads as TRUE, never as false.** A run stored before the flag carried only the
profitable rungs; defaulting to false would repaint every historical profit-take as a plain exit.
⚠ **A banked fill is mint; an unbanked one is coloured by PRICE against the entry, never by P&L** —
which disagree on exactly that trade: 0.30 above a long's entry and still a loss on costs.
⚠ **The green band is measured off the BANKED fills only.** Now that every fill reaches the chart,
taking the extreme of all of them would let a breakeven-stop exit set the top of the band.
⚠ **No separate line for the staged breakeven stop** (Aaron's call) — the exit fill already sits on
it whenever that is where the trade came off. When there are no fills and the exit is at the stop,
the `SL` chip becomes `SL / Exit` rather than stacking a second red line on one pixel row.

⚠ **Chips are DE-COLLIDED and a chip's height is therefore not its price.** Three levels inside 32
cents get spread 15px apart; the dots and dotted lines stay on the true price. Reported as a bug
twice — read the dot.

## The pinned readout follows the WINDOW, and carries no date (2026-08-23)

🔴 **THE READOUT ACROSS THE TOP DESCRIBED A BAR THAT WAS NOT ON SCREEN, AND THE DATE IT PRINTED
WAS READ AS THE DATE OF THE TRADE BELOW IT.** With the readout pinned on and the pointer off the
chart, klinecharts falls back to `dataList[dataList.length - 1]` — the newest bar in the loaded
run, wherever you have scrolled to. On a chart parked on August 2025 around 3,330 it printed
`2026-08-21 15:45 … 4,603.31`, and the year on it was taken for the year of the trade on screen.
**Nothing was wrong with the data. The chart was showing two different moments at once with no
sign that it was doing it** — the same failure shape as a probe whose negative answer a healthy
system also produces. TradingView does not do this: its legend follows the visible window and
carries no timestamp at all.

Three rules, all TradingView's, and the third is the one nobody asks for until they hit it:

1. **The readout names the RIGHT-MOST VISIBLE bar** — never the end of the dataset. While the
   pointer is on a bar the crosshair's bar wins, because that is the bar being asked about.
2. **No date in it.** The date lives in exactly one place, the crosshair's own tag on the time
   axis, so a date you can see is always the bar you are pointing at.
3. **The current-price line goes quiet when its bar is off screen.** Left on, klinecharts clamps
   it to the top of the scale, where a bright line and a price tag read as a level in the market
   you are looking at. It is not one.

🔴 **THERE IS DELIBERATELY NO "IS THE POINTER ON THE CHART" FLAG, AND THE FIRST VERSION HAD ONE
AND WAS WRONG.** klinecharts clears its crosshair through more than one path and at least one of
them updates it without firing the change action, so a flag fed by that action sticks at
*hovering* — and the readout goes on naming the newest bar, i.e. **the defect surviving its own
fix**. MEASURED in a real browser: after the pointer left the chart the action never fired again.
**`resolveTipBar` needs no such flag**: the library hands us the crosshair's bar while the pointer
is on one and the LAST bar when it is not, so the only ambiguous case is the last bar itself — and
if that bar is on screen it IS the right-most visible bar, so both readings agree. Substitute only
when the last bar is off screen and it is the bar we were handed.

⚠ **Both readings format through ONE branch** (`makeCandleTooltip`, `chartStyles.ts`), so the
hovered and the pinned readout cannot drift into disagreeing about how a price is written — which
is why the `{open}`-style templates are not used for the hover path even though they work there.
⚠ **The price-line toggle is guarded on CHANGE**: `setStyles` redraws the whole chart and the
visible-range action runs on every frame of a drag.
⚠ **The edge bar is read off `chart.getDataList()`, not `displayCandles`** — the indices are
klinecharts' own, and the two lists differ for a frame during a page.
⚠ **`to` is EXCLUSIVE and already clamped**, so the right-most bar is `to - 1` and "the newest bar
is on screen" is `to >= length`.

⚠ **No automated check.** The readout is canvas-drawn with no DOM, so what was done instead was
driving the real page: hover a bar mid-chart, scroll back, take the pointer off, and read the
numbers off the screenshot against the candles under them. **Re-do that by hand after touching
either file** — a unit test here would be asserting on the resolver, which is not the half that
broke.

## 🔴 An add is drawn from the bar it was BOUGHT on, not from the entry (2026-09-24)

Every `Add` used to put its dot on the trade's ENTRY column and its dotted line across the whole
box, so an add bought hours into a trade looked as if it had been held from the open. On run
e2295f909180, 2026-06-17 short, the first add filled at 4221.90 — a wick through TP2 at 4219.12
closed back above it, and the market add bought the next open — and drawn from the entry it read
as an add taken BEFORE the target that allowed it (Aaron, 2026-09-24).

- **The add's time reaches the overlay as extra overlay POINTS** (points 3.., in `adds` order),
  so the chart library converts each time to an x the same way it does the entry and exit. No
  second time→pixel mapping.
- **The dot and the line start at that x, and the `Add` chip sits at the line's RIGHT end** (just
  past the box edge; just inside it when that would leave the pane). It sat in the left label
  column until 2026-09-26, naming a line that never reached it — Aaron: *"why is the dash for the
  add only from the right … move the add pill to the right."* Adds de-collide among themselves;
  it carries its price like the other chips (`Add 4204.10`) and hides with them when labels are off.
- ⚠ **An add the chart cannot place falls back to the entry column** rather than vanishing.
- ⚠ **The `Scale-in detail` layer was already right** — each lot's own box runs from its own fill
  time. Only the default drawing was wrong.
- ⚠ **No automated check**, same as the rest of this canvas: checked by driving the real page to
  that trade and reading the screenshot.
