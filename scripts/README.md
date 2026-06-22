# scripts/ — Cross-subsystem ops & recovery

Root-level operational scripts that span more than one subsystem. Subsystem-specific
scripts stay in their own subsystem (e.g. `algos/scripts/deploy.py`); these live here
because they rebuild or recover the whole VPS.

| Script | Covers | Run as |
|---|---|---|
| `bootstrap_vps.ps1` | MT5 / algos side — clone, deps, MT5 check, secrets, Task Scheduler, start | elevated PowerShell |
| `bootstrap_ninjatrader.ps1` | Futures side — NT8 + .NET check, user-folder restore, deploy `.cs`, nt8_agent deps + task, health | PowerShell as `trader` (elevated for task creation) |

Both are **idempotent** — safe to re-run. Each runs in independent phases; a failed
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
   ```bash
   algo            # control panel — all 4 MT5 bots RUNNING
   ```
   Telegram: `/status` (4 bots green), `/balance` (correct balances).
   Command-center sidebar: API / SSH / NT8 / MT5 Agent dots green.

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

- `algos/scripts/deploy.py` — pushes algo changes to the VPS. Stays in `algos/` (algos-specific).
- `algos/docs/ARCHITECTURE.md` — multi-instrument system design (scanner, risk engine, learning gate).
