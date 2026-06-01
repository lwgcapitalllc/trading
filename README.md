# LWG Capital — Trading Operations

## Repo map

```
trading/
├── algos/           ← Live algo trading (XAUUSD, Windows VPS, PU Prime demo)
├── smart-money/     ← Crypto/forex trader scanner and copy-trading candidate pool
├── command-center/  ← Local ops platform: bot monitor, smart money UI, backtests lab
├── scripts/         ← Cross-subsystem VPS recovery and bootstrap scripts
└── docs/            ← Cross-subsystem reference docs and audit tools
```

## Start here

Read these in order for full context:
1. `README.md` (this file) — repo map
2. `CLAUDE.md` — monorepo standing instructions and VPS workflow
3. `algos/CLAUDE.md` — bot table, risk rules, current phase
4. `command-center/CLAUDE.md` — what's built, design decisions
5. `smart-money/CLAUDE.md` — pipeline status, thresholds, where we left off

## Subsystems

| Subsystem | Purpose | Status | Rules |
|---|---|---|---|
| `algos/` | Live algo trading — 4 bots on Windows VPS | Demo trading | `algos/CLAUDE.md` |
| `smart-money/` | Trader scanner for copy-trading candidates | Stages 1–2, 5 live | `smart-money/CLAUDE.md` |
| `command-center/` | React + FastAPI ops platform | Live (Stress Tests stub) | `command-center/CLAUDE.md` |
| `scripts/` | VPS bootstrap and full-recovery scripts | Stable | `scripts/README.md` |

## Conventions

- **Branch model:** `main` for all active development; `backups` (orphan) for VPS runtime data only — never merges to main.
- **Deploy:** edit on Mac → `git push` → `ssh forexvps "git pull"` → restart bots. Never SCP/rsync.
- **Secrets:** never commit tokens, API keys, passwords, or `.env` to any branch. See each subsystem's CLAUDE.md Never-Do section.
- **Subsystem independence:** `algos/`, `smart-money/`, and `command-center/` are fully independent. A change to one never touches the others.
- **VPS:** ForexVPS Windows Server. SSH alias: `forexvps`. Repo at `C:\trading\`.

## docs/

Cross-subsystem reference documents:
- `docs/BOT_DEVELOPMENT_METHOD.md` — S.Y.S.T.E.M. six-step process for building and validating any trading bot
- `docs/Command_Center_Backtest_Engine_Design.md` — Original design spec for the backtests lab (Lab module now built)
- `docs/audit/` — Doc and dead-code audit prompt templates
