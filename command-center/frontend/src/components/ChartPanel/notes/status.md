# Notes — Status

What was built and what was in progress when this was last touched. Moved VERBATIM out of `command-center/frontend/src/components/ChartPanel/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Status

All build steps complete (1–6, 7a, 7b, 8). The panel renders real per-run specs end-to-end:
candles, timeframe switch, sessions, trades, generic structure overlays (box/hline/vline),
shipped indicators (EMA main-pane / ATR sub-pane), daily breaks, the TradingView-style measurement
tool, a draggable Fibonacci tool (Aaron's levels/colours, price labels), and a right-click menu
(Reset chart view / remove fibs). Backend emitter is `services/chart_spec.py`. Build history is in git.
ly menu with
  just **"Delete this fib"** (deletes that one; no reset, no bulk-remove — clean up one at a time);
  right-click **on empty chart** → a chart-only menu with **"Reset chart view"** (restores the
  zoom/scroll — `setBarSpace` / `setOffsetRightDistance` / `scrollToRealTime` — captured into refs at
  init) and **Show/Hide trades**. The menu closes on Escape or any outside mousedown (it
  `stopPropagation`s its own mousedown so a click on an item isn't swallowed).
- **Decision (2026-06-14):** no per-trade trade table exists on the backtest page yet (trades
  are collapsed into `equity_curve` points — no per-trade entry/exit). Per Aaron, the clickable
  trade list + row→zoom is **deferred to Step 7**, when the real spec emitter provides per-trade
  data. Step 4 ships the chart overlay + toggle only.
- **Lifecycle.** Chart is `init()`-ed once on mount and `dispose()`-ed on unmount; a
  `ResizeObserver` calls `chart.resize()`. Data is (re)applied in a `spec`-keyed effect so the
  spec can change without re-initialising.

---

## Status

All build steps complete (1–6, 7a, 7b, 8). The panel renders real per-run specs end-to-end:
candles, timeframe switch, sessions, trades, generic structure overlays (box/hline/vline),
shipped indicators (EMA main-pane / ATR sub-pane), daily breaks, the TradingView-style measurement
tool, a draggable Fibonacci tool (Aaron's levels/colours, price labels), and a right-click menu
(Reset chart view / remove fibs). Backend emitter is `services/chart_spec.py`. Build history is in git.
