# LWG Capital — Trading Operations

## Repo map

```
trading/
├── algos/           ← Live algo trading (XAUUSD, Windows VPS, PU Prime demo)
├── smart-money/     ← Crypto/forex trader scanner and copy-trading candidate pool
├── command-center/  ← Local ops platform: bot monitor, smart money UI, backtests lab
├── regime/          ← Shared market regime classifier (live bots + backtest lab)
├── strategies/      ← Generic strategy source files organized by runner platform
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
6. `regime/CLAUDE.md` — shared classifier, public API, consumers
7. `strategies/CLAUDE.md` — strategy source files, runner layout, deployment flow
8. `docs/LWG_Project_State_Snapshot.md` — current platform state across all subsystems
9. `docs/LWG_Roadmap_And_Open_Questions.md` — forward plan and open questions

## Subsystems

| Subsystem | Purpose | Status | Rules |
|---|---|---|---|
| `algos/` | Live algo trading — 4 bots on Windows VPS | Demo trading | `algos/CLAUDE.md` |
| `smart-money/` | Trader scanner for copy-trading candidates | Stages 1–2, 5 live | `smart-money/CLAUDE.md` |
| `command-center/` | React + FastAPI ops platform | Live (Stress Tests stub) | `command-center/CLAUDE.md` |
| `regime/` | Shared regime classifier for live bots and backtest lab | Production | `regime/CLAUDE.md` |
| `strategies/` | Generic strategy source files (NT8, MT5 placeholder) | Production | `strategies/CLAUDE.md` |
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
- `docs/Command_Center_Backtest_Engine_Design.md` — Original design doc for the backtests lab (historical reference)
- `docs/LWG_Project_State_Snapshot.md` — Current platform state; hand to new Claude.ai chats
- `docs/LWG_Roadmap_And_Open_Questions.md` — Forward plan and open questions; hand to new Claude.ai chats
- `docs/audit/` — Audit and snapshot prompt templates
- `docs/archive/` — Shipped build specs (historical record)
