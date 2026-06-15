# Claude Code seed — spec-driven backtest chart panel (KLineChart)

Build a chart panel for the backtest page. Run context is AUDJPY London Breakout, but the
panel must be **strategy-agnostic**: it renders whatever a run spec declares and contains zero
strategy-specific logic. No instrument names, no "Asian", no "London Breakout" anywhere in the
chart component. Adding a new strategy later means its spec lists different overlays — the chart
code does not change.

Library: **klinecharts v9** (`npm install klinecharts@9`, UMD at `dist/umd/klinecharts.min.js`).

## The contract: a chart spec the lab emits per run

The chart reads a spec written next to each backtest. Define it as a typed contract:

```
ChartSpec {
  instrument            // e.g. "AUDJPY.s"
  baseTimeframe         // finest TF the strategy used, e.g. "M5"
  brokerGmtOffsetHours  // for correct session placement
  candles               // base-TF OHLC array (or a file ref): {time, open, high, low, close}
  sessions[]            // market sessions: {name, tz, start, end, color}
  trades[]              // {id, dir:"long"|"short", entryTime, entryPrice, exitTime, exitPrice, exitReason}
  overlays[]            // generic strategy structure, each tagged with a group:
                        //   {type:"box",   group, t0, t1, top, bottom, style}
                        //   {type:"hline", group, t0, t1, price, label, style}
                        //   {type:"vline", group, t, style}
  indicators[]          // {name, params, pane:"main"|"sub", series:[{time, value}]}
}
```

Times are epoch milliseconds (KLineChart's unit) — state this in the type and convert at the emitter.
Indicator series are **shipped from the run, not recomputed in the browser**, so the chart shows what
the strategy actually saw. Session boxes, the range box, and breakout levels all arrive as generic
`overlays`/`sessions` — the chart never computes strategy structure itself.

## Build in numbered steps. Stop after each, report, update the panel's CLAUDE.md in the same session.

1. **Scaffold.** A lazy-mounted `ChartPanel` on the backtest page (mounts only when its tab/section
   opens). Load klinecharts, render candles from a hand-written spec fixture for AUDJPY. Theme from
   the app's existing design tokens (background, up/down candle, accent) — do **not** hardcode colors,
   pull the app theme. Grid off. Stop and report.

2. **Timeframe switch.** M5/M15/M30/H1 segmented control. Resample the base-TF candles up for display
   (note in code: higher-TF candles are display aggregations of base bars; the strategy's own TF is the
   source of truth). Overlays must stay anchored across switches. Stop and report.

3. **Sessions.** Register a generic `sessionBox` overlay (a rect hugging the candles inside a session
   window). Place each session from `tz` + `brokerGmtOffsetHours` so DST stays correct year-round.
   Per-session toggle. Stop and report.

4. **Trades.** Register a generic `trade` overlay: blue up-arrow for long / down-arrow for short at
   entry, a dashed line from entry to exit (the trade's length), a dot at the exit. No exit-reason text
   on the chart. Toggle for all trades. Clicking a row in the existing trade table selects and zooms
   that trade on the chart. Stop and report.

5. **Generic overlays.** Render `spec.overlays` (box / hline / vline) grouped by `group`, each group
   toggleable. This is what carries strategy structure — e.g. the range box plus buy/sell levels —
   without the chart knowing which strategy produced them. Stop and report.

6. **Indicators + breaks.** Render `spec.indicators` as main-pane overlays or sub-panes from the shipped
   series values, each toggleable. Draw daily session breaks as `vline`s. Stop and report.

7. **Spec emitter.** In the lab/backtest pipeline, write the ChartSpec to the run's output dir from the
   real run: base-TF candles, trades, the sessions config, the strategy's structural overlays, and any
   strategy-relevant indicator series (e.g. ATR used by the range filter). Point the panel at the real
   spec instead of the fixture. Stop and report.

## Constraints

- Smallest viable change per step; run nothing past the step you're on.
- Overlays must be generic and data-driven — `box`/`hline`/`vline`/`trade`/`sessionBox`, nothing
  named after a strategy.
- No instrument or strategy names in the chart component.
- Lazy-mount the panel for page performance.
- Update the panel's CLAUDE.md in the same session as approved changes.
