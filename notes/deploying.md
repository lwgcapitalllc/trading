# Notes — Deploying to the trading box

The commands that pull, promote, stop and restart a bot, and why a bot is asked to stop rather than killed. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Before you promote — prove the change is INERT (2026-09-17)

**A promote is the only thing that changes what a live bot trades, so it is the only moment where
"I think this is safe" is worth nothing.** `backtest/tools/replay_fingerprint.py` settles it in
**22 seconds** (MEASURED 2026-09-17, 2.5 years / 62,468 M15 bars — two runs, so under a minute).

```bash
# 1. BEFORE the change (or on a clean checkout of what is currently deployed)
python3 backtest/tools/replay_fingerprint.py capture /tmp/pre.json \
    --start 2024-01-01 --end 2026-08-23

# 2. AFTER the change
python3 backtest/tools/replay_fingerprint.py compare /tmp/pre.json \
    --start 2024-01-01 --end 2026-08-23
```

`bars ... IDENTICAL` **and** `trades ... IDENTICAL` is the only green. Anything else means the
promote WILL move what the bot does — which may be exactly what you intended, but you now know it
instead of finding out live.

🔴 **IT FINGERPRINTS EVERY TRADE, NOT A TOTAL.** Two different books post the same net P&L, so a
totals check is not a check. It also fingerprints the BAR STREAM, which a trade list cannot see: a
run producing identical trades off a subtly different bar sequence is still a changed run, and the
next strategy through that loop is the one that finds out.

⚠ **It catches what the unit tests structurally cannot.** They run on small synthetic frames; the
defects that reach a live bot are the ones that only appear over years of real bars — a float that
rounds differently, a bar boundary off by one, a volume that becomes 0.0 instead of None.

⚠ **`--allow-strategy-change` waives a REFUSAL, so only pass it when proving a strategy edit
inert** — which is the whole point here. The tool then says so in its own output, and everything
after that line is a claim rather than a guarantee. Read it that way.

⚠ **Compare only against a fingerprint taken on the SAME window, instrument and settings.** The
file records all three and `compare` refuses a mismatch, because a green comparison across two
different bases is exactly the false reassurance this exists to prevent.

**Worked example — the 2026-09-17 currency fix.** Four sizing lines and one swap call changed in
`strategies/python/sos_fade/execution.py`. Both fingerprints came back identical over 62,468 bars,
66 trades each side, which is what made that promote safe to recommend. The argument that it
*should* be inert (gold's conversion factor is 1.0) was available the whole time and was not the
evidence; this was.

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

🔴 **STARTING ONE BOT OVER SSH DIRECTLY DOES NOT WORK, AND IT REPORTS SUCCESS (2026-09-15).**
`ssh forexvps "python ... startup_coordinator.py --bot <key>"` prints `OK <name> launched` and the
bot is dead seconds later — **nothing reaches its log at all**, not even the version banner, so the
only symptom is a bot that is simply absent. SSH tears its children down by job object when the
session closes, which `CREATE_NEW_PROCESS_GROUP` does not prevent. ✅ **Launch it the way the
Command Center's Start button does — through WMI, which is not under the SSH job object:**

```bash
ssh forexvps "wmic process call create \"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe C:\trading\algos\bots\startup_coordinator.py --bot sos_fade_1\""
```

⚠ **`ReturnValue = 0` is a statement about the WMI CALL, never about a running bot** (rule 5). Confirm
with the process list, and confirm again in the bot's own log — its banner names the commit it loaded.
⚠ **`schtasks /run /tn SYS_STARTUP` is BOX-WIDE**: it starts every bot assigned to an account,
including ones on another live account that were deliberately left stopped. It is the wrong tool for
restarting one bot.
⚠ **A graceful stop does NOT come back on its own.** The monitor revives a bot that DIED; a bot that
was asked to stop stays stopped until something starts it.

🔴 **A DRY-RUN DEPLOY PULLS THE BOX (2026-09-15).** `promote.py`'s preview runs `git pull` before it
stages anything, so "changes nothing" is true of the DEPLOYMENT and false of the repo. Everything
under `algos/` — the runner, the bridge, order sizing — is then one restart away from being live for
every bot on the box, while `strategies/`, `engines/` and `backtest/` stay frozen until a real
promote. **Never preview a deploy while a pull would be unsafe to take.**

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

---

## 🔴 A deploy with nothing to deploy no longer restarts the bot (2026-09-23)

`algos/tools/promote.py` had computed and printed *code is UNCHANGED from the running deployment*
since the day it was written, and then deployed and asked for a restart regardless. On 2026-09-23
that cost a real order: `fft_1` was deployed twice inside three minutes, the second run staged
byte-identical code, and the restart cancelled the sell limit the bot had placed ninety seconds
earlier — fifty-one seconds with nothing resting, for nothing.

It now **refuses**, prints `##NOTHING-NEW` for its caller, and says so. `--redeploy` forces it.

🔴 **THE FIRST VERSION OF THAT FIX WAS INERT, AND THAT IS THE MORE USEFUL HALF OF THIS STORY.**
It compared the STAGED hash with the RECORDED one — and those two are taken over **different root
sets**. `deployment_hash` folds each root's NAME into the digest; the staged hash covers every tree
the tool copies (**11 roots** for `fft_1` — the strategy's whole dependency closure, `engines`,
`backtest`, `execution` and the order path), while the pinned hash covers `cfg.source_roots`
(**3**). They can never be equal. So the refusal could not fire — **and the `code is UNCHANGED from
the running deployment` line this tool has printed since it was written has never once been true.**

**It now compares the STAGED tree against the DEPLOYED tree**, same relative destinations, same
root names, same hash function. Like for like. That also subsumes the *snapshot edited in place*
case for free, because it hashes what is actually there rather than what a record claims.

⚠ **The first tests passed anyway, because they stubbed `deployment_hash`** — a double more
capable than production, describing a system we do not have. Rule 13, inside the tests written to
prove rule 9 had been answered. They use real files on disk now.

⚠ **The PARAMETERS are the second half** (the record pins the settings a version was deployed with,
and `config.json` is edited between promotes — the Bots page writes the per-trade risk to it live).
Cannot-read is never "the same", and a bot that has never been deployed is never a no-op.

⚠ **The COMMIT is deliberately not one of the three, and the pin is STILL written on the no-op.**
A commit touching no file the bot loads is not worth restarting a live bot for — but the Command
Center measures *how far behind* against the recorded commit, so skipping the write would leave its
badge asking for a deploy that can never satisfy it, which is the stale-badge failure made
permanent.

**The other half of that incident was the badge itself**, which was drawing a reading taken before
the deploy and so asked for a second one. Both, and why they compound:
`command-center/backend/notes/bots-deploys.md`.
