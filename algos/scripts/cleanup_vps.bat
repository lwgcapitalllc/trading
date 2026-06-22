@echo off
REM cleanup_vps.bat — Remove old files replaced by bot_state.json
REM Run once after deploying the new architecture
REM RDP into VPS and run: C:\trading\algos\cleanup_vps.bat

echo Cleaning up old data files...

REM Old state files (replaced by bot_state.json alert fields)
del "C:\trading\algos\monitor_state.json" 2>nul
del "C:\trading\algos\pnl_state.json" 2>nul

echo No bots registered — nothing to clean.
