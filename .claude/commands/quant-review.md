Review the last set of changes through a quant developer lens before committing.

Check:
1. **Risk integrity** — Did any change touch position sizing, stop logic, daily/weekly caps,
   or P&L tracking? If so, trace the logic end-to-end and confirm numbers are correct.
2. **Bot state consistency** — Does bot_state.json stay consistent? Are all new fields
   added to `_default_state` in bot_state.py?
3. **MT5 error handling** — Are all MT5 calls checked for None/failure?
4. **Loop safety** — Could any new code block the main trading loop indefinitely?
5. **Config coverage** — Are new parameters exposed in config.json so they can be tuned
   without code changes?
6. **Doc coverage** — Are all affected guide files updated?

Report findings. Fix anything critical before flagging as done.
