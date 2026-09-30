# The New York opening range — length, and why it is a three-part swap

**Owner:** `indicators/engines/mpc_jarvis.pine`, the opening-range block and the panel setting
declared last in the file.
**Read this before:** changing the opening-range length, adding a length to the list, or touching
the box that draws it.

---

## What it is

The high and low of the window straight off the 09:30 New York bell, frozen for the rest of the
day and drawn as a box with a dotted mid-line. It rides the same on/off switch as the kill-zone
boxes, so one tick hides both.

## 2026-09-29 — the length became a choice (Kelly)

It was five minutes and only five minutes since the file was written. Students who trade a slower
open asked for the fifteen-minute range, so the panel now offers **5 Min** and **15 Min**, and the
default is 5 — no chart already running this moves.

### Three parts, one setting, and they may never be changed apart

| Setting | Range window | Follow-on window | Feed it is read from |
|---|---|---|---|
| 5 Min | 0930-0935 | 0935-1600 | five-minute candles |
| 15 Min | 0930-0945 | 0945-1600 | fifteen-minute candles |

- Leave the **follow-on window** behind and the range freezes while price is still inside it —
  the box stops growing part-way through its own window.
- Leave the **feed** behind and the box is a different length from the window that drew it.

### Why 5 and 15, and nothing else, without a rewrite

The range is read as ONE candle of a feed its own length, and that candle has to open on the bell.
Five and fifteen both divide the hour, so they do. Ten, twenty and fifty do not — on a 24-hour
instrument those candles are laid out from the session open, not from 09:30, so the candle
straddling the bell starts somewhere else and the range is the wrong window entirely.

**A length that does not divide the hour has to be accumulated bar by bar from the chart's own
candles instead**, which costs the range on any chart whose candle is longer than the range
itself. That is a different build, not another entry in the list.

### The setting is declared LAST in the file, on purpose

TradingView keys a chart's saved values off declaration order **within each type**. A text-choice
setting added up in the Chart Tools block would silently re-point the fib label style — and every
text choice after it — on every chart already running this script. `group =` is what puts it on
the panel beside the kill-zone toggle; the declaration stays at the bottom. Same rule as the
level-tag size setting, and the reason that one is pinned where it is.

---

## Known, not fixed — the range is read with look-ahead

The feed is read with look-ahead ON, so **on history the box draws at its full width from the
first bar of the window**: a student scrolling back sees a range that was complete before it
could have been. Live it cannot leak — there is no future bar to read.

⚠ **It scales with the length.** At five minutes the box is up to five minutes early; at fifteen
it is up to fifteen. So the new option makes an existing display defect three times larger for
anyone who picks it.

The fix is to accumulate the high and low from the chart's own candles inside the window instead
of reading a feed. That also drops a data request, which is worth having on a file at Pine's
compile ceiling. **The cost is that the range can then only be drawn on charts whose candle is no
longer than the range** — the five-minute range would stop drawing on 15m and above, where today
it is a look-ahead read anyway. Not done: it is a behaviour change on charts nobody has been
asked about.

---

## What did NOT change, and where it now differs

- **`engines/sessions/`** — the canonical Python engine — is still pinned to `0930-0935`. It
  already accumulates the range from whatever bars it is fed, so it would follow a 15-minute
  window without a rewrite; it simply has no setting yet.
- **`indicators/engines/sessions_export.pine`**, the parity export, is still pinned to five
  minutes too. That is correct as long as the indicator's default is five — the export exports
  the default — but it means **a chart on 15 Min is showing a range nothing on the Python side
  reproduces**, and the parity gate cannot see the difference.
- Nothing trades off the opening range. Two research tools read it
  (`backtest/tools/intraday_edge.py`, `backtest/tools/ny_open_scalp_study.py`); no bot and no
  strategy does. So this change moves what is drawn and never a trade.
