# scripts/ — Cross-subsystem ops & recovery

Root-level operational scripts that span more than one subsystem. Subsystem-specific
scripts stay in their own subsystem; these live here because they rebuild or recover
the whole VPS.

| Script | Covers | Run as |
|---|---|---|
| `bootstrap_vps.ps1` | MT5 / algos side — clone, deps, MT5 check, secrets, Task Scheduler, start | elevated PowerShell |
| `bootstrap_ninjatrader.ps1` | Futures side — NT8 + .NET check, user-folder restore, deploy `.cs`, nt8_agent deps + task, health | PowerShell as `trader` (elevated for task creation) |
| `install_hooks.sh` | This clone's git hooks — points `core.hooksPath` at the tracked `.githooks/` | any shell, on a dev machine |
| `install_ledger_sync.sh` | 12-hourly backup of the live bot's daily record (launchd, 00:05 + 12:05) | any shell, **on the Mac only** |
| `setup_learning_mode.sh` | This clone's `/learn` skill — installs `ffmpeg`/`yt-dlp` and the third-party `watch` skill | any shell, on a dev machine |

`install_ledger_sync.sh` is Mac-only by necessity, not by preference: the VPS holds the data but
cannot push, because its tasks run as SYSTEM and SYSTEM's Git Credential Manager makes `git push`
BLOCK rather than fail. Fixing that means a GitHub write token on a box already holding a live MT5
password. ⚠ **So the backup only runs while the Mac is on** — launchd fires a missed calendar job
on the next wake, so a closed laptop delays it rather than skipping it. Check with
`scripts/install_ledger_sync.sh --status`. Detail in `algos/CLAUDE.md` → *The daily record*.

`install_hooks.sh` exists because `core.hooksPath` is per-clone local config that `git clone`
does not carry, so a fresh clone commits with no checks and looks exactly like one that has
them. `./go` runs it for you; run it by hand on a clone that never runs `./go`. What the hook
enforces is in the root `CLAUDE.md` → `## Committing`.

`setup_learning_mode.sh` is what makes `/learn <video-url>` work on a machine. The skill itself
ships in this repo (`.claude/skills/learn/SKILL.md`) and is available on clone; what does NOT ship
is the third-party `watch` skill it drives (MIT, `bradautomates/claude-video`) and the `ffmpeg` /
`yt-dlp` binaries under it. ⚠ **The watch skill is deliberately NOT vendored into this repo** — it
is cloned to `~/.claude/vendor/claude-video` and symlinked into `~/.claude/skills/watch`, so it
updates on its own and 2,300 lines of somebody else's Python stay out of a trading repo. The
honest cost is that a clone alone is not enough: run the script once per machine. Re-running it
is also how the watch skill is UPDATED, which matters more than it sounds — `yt-dlp` breaks
whenever a video site changes, so a stale copy fails on real URLs while looking installed.

All four are **idempotent** — safe to re-run. Each runs in independent phases; a failed
phase reports and the run continues, ending with a status summary.

---

## Full VPS recovery — run order

After a wipe or move to a new VPS, do these in order. The manual GUI/account steps
cannot be scripted; the scripts detect them and tell you what's outstanding.

1. **Prerequisites (manual, one time per box)**
   - Windows VPS, logged in as `trader` (admin).
   - Install Git for Windows and Python 3.11.
   - Install **MT5** (PU Prime) — needed by the command-center MT5 backtest agent. No live-bot terminals are required yet (no bots registered); add one per bot account when you deploy a bot.
   - Install **NinjaTrader 8** + .NET Framework 4.8; log into your data/broker connection.

2. **MT5 / algos side**
   ```powershell
   # From an ELEVATED prompt.
   .\scripts\bootstrap_vps.ps1
   ```
   Then fill real passwords into `algos\credentials.json` (replace every `REPLACE_ME`)
   and verify the Telegram admin ID in `algos\users.json`. Re-run to finish startup
   once secrets are in place.

3. **Register the nt8_agent task (from your Mac, one time)**
   The `NT8Agent` task has no XML in the repo — it's created from the Mac:
   ```bash
   python3 algos/nt8/setup_agent_task.py
   ```

4. **Futures / NinjaTrader side**
   ```powershell
   # Restore the NT8 user folder from a backup, deploy strategies, start the agent.
   .\scripts\bootstrap_ninjatrader.ps1 -RestoreUserData -UserDataBackup '<path-to-NinjaTrader 8 backup>'
   ```
   Point `-UserDataBackup` at a NinjaTrader 8 user-folder backup you supply.

5. **Launch NinjaTrader (manual)**
   Open NT8, confirm NinjaScript compiled with no errors (Editor → F5), open Strategy
   Analyzer. The command-center NT8 health dot needs SA open.

6. **Verify**
   No bots are currently deployed — the suite was deleted 2026-06-22 and is being rebuilt
   backtest-first (see `algos/CLAUDE.md`). Verify infrastructure instead:
   ```bash
   algo            # control panel loads, no bots listed
   ```
   Telegram: `/status` responds (even with zero bots registered).
   Command-center sidebar: API / SSH / NT8 / MT5 Agent dots green.
   Once a bot is redeployed, confirm it shows RUNNING in `algo` and green in Telegram `/status`.

---

## What the scripts do NOT do (by design)

- Install MT5 / NinjaTrader / Python / Git — GUI installers, done by hand.
- Enter real account passwords — scaffolded as placeholders; you fill them in.
- Log into broker/data connections or accept licenses/2FA.
- Compile NinjaScript — NT8 does this on launch / F5.
- Restore live data without being asked — restore phases are opt-in and refuse to
  overwrite a running system.

---

## Related (not in this folder)

- `algos/docs/ARCHITECTURE.md` — multi-instrument system design (scanner, risk engine, learning gate).
