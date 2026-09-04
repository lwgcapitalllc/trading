---
description: Run the SOS Fade strategy logic-parity check — prove the Python bot trades bar-for-bar identically to sos_fade_strategy.pine, under whatever toggles the export carried
---

Run the SOS Fade strategy LOGIC-PARITY check: prove the Python bot in `strategies/python/sos_fade/` makes the exact same per-bar decisions as `strategies/tradingview/sos_fade_strategy.pine`, on the Pine's own bars, under the exact toggles the export was run with. Nothing about the strategy is trusted until this is exit 0 — the same discipline as every engine's `compare_*.py`.

This is LOGIC parity (same decisions on the SAME candles), NOT feed parity (do MT5's candles match TradingView's — that is `backtest/tools/compare_feeds.py`, a separate check). They never mix: this replays TradingView's own exported bars, so the broker feed is irrelevant here.

## What you need first

A CSV exported from `strategies/tradingview/sos_fade_strategy_export.pine` (that file = `sos_fade_strategy.pine` + an appended decision-stream plot block; its trade logic is byte-identical to the strategy). Aaron/his brother puts it on a **5m XAUUSD** chart (5m exercises the Macro fib), sets whatever toggles they want to test, and uses **Export chart data → CSV**. If there is no export yet, say so and stop — this check cannot run without one. The CSV lives wherever Aaron dropped it (commonly `strategies/python/sos_fade/exports/`, git-ignored, or the repo root).

## Steps

1. **Locate the export CSV.** Ask Aaron for the path if it is not obvious. Confirm it has the `px_*` decision columns and the `cfg_*` toggle columns (a plain price export won't work — it must be from `sos_fade_strategy_export.pine`).

2. **Check for Pine drift first.** If `strategies/tradingview/sos_fade_strategy.pine` changed since `sos_fade_strategy_export.pine` was last regenerated, the export's trade logic is stale. Regenerate it: re-copy `sos_fade_strategy.pine` to `sos_fade_strategy_export.pine` and re-append the parity block (the block is self-marked at the end of the file). Tell Aaron his brother must re-run the export from the fresh file. Same re-paste discipline as the engine export harnesses.

3. **Run the check:**
   ```
   command-center/backend/.venv/bin/python strategies/python/sos_fade/tools/compare_strategy.py <export.csv> --warmup N
   ```
   Pick `--warmup N` the way the engine harnesses do: the Python engines start cold while the Pine export begins warm (chart history before the window), so the first bars always differ. Start with a few hundred; the tool prints the first diverging bar, so raise N until the only diffs left are genuine (the Macro fib needs the longest warm-up — a cycle can span thousands of bars).

4. **Report the result. Plain English, concise.**
   - **Exit 0** → parity holds. State it plainly: the Python bot is a bar-for-bar copy under those toggles. If this is the first green, note that the intrabar fill assumption in `execution.py` (open nearer high ⇒ targets fill before the stop) is now CONFIRMED, not assumed.
   - **Exit 1** → the tool names the FIRST diverging bar and field (e.g. `px_long_edge`, `px_l_stage`, `px_exit_tp1`). That is the actionable clue. Read the Pine around that behaviour and the matching Python (`signals.py` for inputs, `sequence.py` for the SOS Fade stages, `execution.py` for edges/fills/stops), find the divergence, and report it. A parity failure is the harness doing its job — it caught a Pine behaviour the Python doesn't match yet.

5. **Fixing a divergence (only if asked to fix, not just report):** change the Python to match the Pine, re-run until exit 0. Never change the Pine to match the Python — the Pine is the source of truth. Add a unit test in `strategies/python/sos_fade/tests/` capturing the rule you just fixed, so it can't regress. Then remind Aaron that a real fix isn't done until `compare_strategy.py` is exit 0 on the fresh export.

## The toggle columns

The export carries its own config: the tool reads the `cfg_*` columns and configures the bot to the exact same settings before replaying, so any toggle combo Aaron and his brother pick reproduces. If they add a NEW input to the strategy that changes a trade decision, it needs: a new field in `config.py` (same name + default), a new `cfg_*` plot in `sos_fade_strategy_export.pine`, and a new entry in `compare_strategy.py`'s `_TOGGLE_COLS`. Flag that if the export has a `cfg_*` column the tool doesn't know, or vice versa.
