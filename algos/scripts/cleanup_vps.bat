@echo off
REM cleanup_vps.bat — Remove old files replaced by bot_state.json
REM Run once after deploying the new architecture
REM RDP into VPS and run: C:\trading\algos\cleanup_vps.bat

echo Cleaning up old data files...

REM Old equity files (replaced by balance in bot_state.json)
del "C:\trading\algos\markets\fx\instances\gold_main\gold_main_equity.json" 2>nul

REM Old weekly files (replaced by weekly fields in bot_state.json)
del "C:\trading\algos\markets\fx\instances\gold_main\mean_reversion_weekly.json" 2>nul

REM Old state files (replaced by bot_state.json alert fields)
del "C:\trading\algos\monitor_state.json" 2>nul
del "C:\trading\algos\pnl_state.json" 2>nul

REM Old startup time files (replaced by started field in bot_state.json)
del "C:\trading\algos\markets\fx\instances\gold_main\startup_time.json" 2>nul

REM Truncate stdout logs (keep files but clear old content)
echo. > "C:\trading\algos\markets\fx\instances\gold_main\mean_reversion_stdout.log"

echo Done. Deploy bot_state.json initial values with correct balances before restarting.
