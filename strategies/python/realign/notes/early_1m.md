# The early 1m trigger (`realign_early_1m`) — built 2026-09-27, measured, FAILED, shipped OFF

- **What:** inside the 5m trigger's window, after the 5m has gone counter, a closed 1m bar that
  completes a trade-way shift then a trade-way break enters at market on its close. Stop = the dip
  extreme known then + `realign_sl_buf_tk`. Same gates, target and exits; a refused 1m trigger
  leaves the setup for the 5m trigger. Code: `early.py`, `dual.py`, `enter_early` in `execution.py`.
- 🔴 **Result (Run 16):** fails every pre-declared test but one half. The earlier price is real
  (+14.83R over 45 setups) and is swamped by 19 setups the 5m never confirms (−16.69R, 16 stops).
- 🔴 **Needs a second bar stream.** `run()` / `step()` REFUSE it, so the lab's single run, sweep
  and a stack leg all refuse it today: the lab's feed loader (`command-center/backend/services/
  run_feeds.py`) keys the second stream on SOS Fade's flag and was NOT generalised in this change.
  Run it through `RealignStrategy.run_dual(df5, df1)` or `make_dual_clock`.
- ⚠ The 5m bar an early entry fills inside is managed on its post-entry minutes only
  (`_AfterEntry`); an entry on the bar's last minute leaves that bar untouched. Pinned by test.
- ⚠ No Pine counterpart; any figure is a lab finding. Tests: `tests/test_early_1m.py`, each
  watched red by mutation.
