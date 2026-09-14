# Notes — Deploying to the trading box

The commands that pull, promote, stop and restart a bot, and why a bot is asked to stop rather than killed. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## VPS Deploy Workflow

**Pulling does NOT change what a bot trades — promoting does.** Since 2026-08-03 a live bot
imports from a frozen snapshot in `algos/markets/fx/instances/<bot>/deployed/`, not from the
repo, so a pull is safe at any time and a restart still comes back on the SAME version. See
`algos/live/version.py`.

```bash
# Push changes
git add . && git commit -m "..." && git push

# Pull on the VPS — safe while a bot is running; it will not move the deployment
ssh forexvps "cd C:\trading && git pull origin main"

# Deploy the code to a bot (the ONLY thing that changes what it trades).
# Stages, verifies it imports, then swaps; a failure leaves the running bot untouched.
ssh forexvps "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe C:\trading\algos\tools\promote.py --bot sos_fade_demo"

# Stop the running bot by ASKING, never by killing. It polls its instance dir every 10s,
# writes a shutdown record, and clears the file. Give it ~30s, then confirm it is gone.
ssh forexvps "echo stop > C:\trading\algos\markets\fx\instances\sos_fade_demo\stop.request"
ssh forexvps "wmic process where \"name='python.exe'\" get commandline"

# Restart onto the new version. SYS_MONITOR also brings a dead bot back on its own within
# ~60s — but this is the deliberate path.
ssh forexvps "schtasks /run /tn SYS_STARTUP"
```

🔴 **Ask, do not kill — and it is not politeness.** A hard kill gives the bot no chance to
write its `shutdown` record, so the next startup reports *"the previous run ended without
shutting down."* That sentence is the **silent-death detector**, and while this workflow said
to kill, it fired on every restart anybody performed on purpose. **An alarm that fires when
you press the button is one you learn to scroll past**, and the thing it catches is the one
failure here that leaves no other trace. `stop.request` is the graceful path (`runner.py` →
`STOP_FILE`); the Command Center's Stop button has used it since 2026-08-07 and the CLI was
the half left behind. Story: `HISTORY.md`, the 2026-08-13 deploy that alarmed on itself.

⚠ **Escalate only for a bot that ignored the request** — wedged, blocked in an MT5 call, or
running code that predates the file. Delete the request afterwards, since nothing consumed it:

```bash
ssh forexvps "wmic process where \"name='python.exe' and commandline like '%--bot sos_fade_demo%'\" call terminate"
ssh forexvps "del C:\trading\algos\markets\fx\instances\sos_fade_demo\stop.request"
```

⚠ **NEVER `taskkill /f /im python.exe`.** It kills every Python process on the box — the
trading bot, the Telegram bot, the MT5 backtest agent and the NT8 agent — and it is what
killed the live bot on 2026-07-31 (dead for three days; nothing restarted it then). This
workflow told you to run it, which is how it kept happening. Kill ONE bot by its commandline,
as above.

VPS path: `C:\trading\algos\` (main)
