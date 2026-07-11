# LWG Capital — Trading Operations

## Repo map

Dirs fall into four groups. Only the **Engines** group grows — each new engine
extracted from the SMC indicator (see `docs/ENGINE_EXTRACTION_ROADMAP.md`) is a
new peer dir here. Apps, Tooling, and Docs are fixed.

```
trading/
│
│  ── APPS (deployables) ──────────────────────────────────────────
├── algos/               ← Algo trading suite (Windows VPS, PU Prime demo — no live bots, rebuilding backtest-first)
├── smart-money/         ← Crypto/forex trader scanner and copy-trading candidate pool
├── command-center/      ← Local ops platform: bot monitor, smart money UI, backtests lab
├── strategies/          ← Generic strategy source files organized by runner platform
│
│  ── ENGINES (canonical shared libraries — the growing group) ─────
├── engines/
│   ├── regime/          ← Market regime classifier (live bots + backtest lab)
│   ├── market_structure/← BOS/CHoCH/swing detection engine (base engine)
│   ├── fibonacci/       ← Fib level-event engine, downstream of market_structure/
│   ├── order_blocks/    ← Order-block (supply/demand zone) engine, sibling of fibonacci/
│   ├── sessions/        ← Time-driven sessions / kill-zones / NY-range engine (standalone)
│   ├── liquidity/       ← Liquidity-levels engine (prev D/W/M H·L, PWC, H4 sweep, session H·L); consumes sessions/
│   ├── vwap/            ← Session VWAP engine (volume-weighted hlc3, trading-day anchor + cross); needs volume
│   ├── session_volume_profile/  ← Session Volume Profile engine (Asia POC / MV line + sweep); consumes sessions/, needs volume
│   ├── fair_value_gaps/ ← Fair-value-gap engine (3-candle displacement voids + mitigation); standalone, OHLC-only
│   │                       (SMC extraction COMPLETE — see ENGINE_EXTRACTION_ROADMAP.md)
│   └── news/            ← Economic-calendar (news + holiday) blackout engine (off-roadmap, not a Pine port; standalone)
│
│  ── TOOLING / SOURCE ────────────────────────────────────────────
├── indicators/          ← Pine Script market-structure indicator rebuild + parity-export harnesses
├── scripts/             ← Cross-subsystem VPS recovery and bootstrap scripts
│
│  ── DOCS ─────────────────────────────────────────────────────────
└── docs/                ← Cross-subsystem reference docs and audit tools
```

Engines live under `engines/` but are imported by bare top-level name
(`from market_structure import …`) — `engines/` is placed on `sys.path` by the
consumers' shims and the root `conftest.py`, matching the repo-wide
"dir-on-path, import bare" convention. Bots consume them through thin shims in
`algos/shared/`.

## Start here

Read these in order for full context:
1. `README.md` (this file) — repo map
2. `CLAUDE.md` — monorepo standing instructions and VPS workflow
3. `algos/CLAUDE.md` — bot table, risk rules, current phase
4. `command-center/CLAUDE.md` — what's built, design decisions
5. `smart-money/CLAUDE.md` — pipeline status, thresholds, where we left off
6. `engines/regime/CLAUDE.md` — shared classifier, public API, consumers
7. `engines/market_structure/CLAUDE.md` — canonical structure engine, parity rules, consumers
8. `engines/fibonacci/CLAUDE.md` — fib level-event engine, the three fibs, parity rules
9. `engines/order_blocks/CLAUDE.md` — order-block (supply/demand zone) engine, parity rules
10. `engines/sessions/CLAUDE.md` — time-driven sessions/kill-zones/NY-range engine, parity rules
11. `engines/liquidity/CLAUDE.md` — liquidity-levels engine (non-repainting), parity rules
12. `engines/vwap/CLAUDE.md` — session VWAP engine (volume-weighted, trading-day anchor), parity rules
13. `engines/session_volume_profile/CLAUDE.md` — Session Volume Profile engine (Asia POC / MV line), parity rules
14. `engines/fair_value_gaps/CLAUDE.md` — fair-value-gap engine (displacement voids + mitigation), parity rules
15. `engines/news/CLAUDE.md` — news/economic-calendar blackout engine, data paths, validation (no Pine source)
16. `strategies/CLAUDE.md` — strategy source files, runner layout, deployment flow
17. `indicators/CLAUDE.md` — Pine Script indicator rebuild, design decisions, build status
18. `docs/LWG_Project_State_Snapshot.md` — current platform state across all subsystems
19. `docs/LWG_Roadmap_And_Open_Questions.md` — forward plan and open questions

## Subsystems

| Subsystem | Purpose | Status | Rules |
|---|---|---|---|
| `algos/` | Live algo trading on Windows VPS | No live bots — rebuilding backtest-first | `algos/CLAUDE.md` |
| `smart-money/` | Trader scanner for copy-trading candidates | Stages 1–2, 5 live | `smart-money/CLAUDE.md` |
| `command-center/` | React + FastAPI ops platform | Live | `command-center/CLAUDE.md` |
| `engines/regime/` | Shared regime classifier for live bots and backtest lab | Production | `engines/regime/CLAUDE.md` |
| `engines/market_structure/` | Canonical structure detection engine (BOS/CHoCH/swings) | Production — 100% Pine parity | `engines/market_structure/CLAUDE.md` |
| `engines/fibonacci/` | Fib level-event engine (downstream of market_structure) | Production — all 3 fibs (Structure/Sniper/Macro) 100% Pine parity | `engines/fibonacci/CLAUDE.md` |
| `engines/order_blocks/` | Order-block engine (supply/demand zones; sibling of fibonacci) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/order_blocks/CLAUDE.md` |
| `engines/sessions/` | Time-driven sessions / kill-zones / NY-range engine (standalone) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/sessions/CLAUDE.md` |
| `engines/liquidity/` | Liquidity-levels engine (prev D/W/M H·L, PWC, H4 sweep, session H·L; non-repainting) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/liquidity/CLAUDE.md` |
| `engines/vwap/` | Session VWAP engine (volume-weighted hlc3, trading-day anchor + cross) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/vwap/CLAUDE.md` |
| `engines/session_volume_profile/` | Session Volume Profile engine (Asia POC / MV line + sweep) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/session_volume_profile/CLAUDE.md` |
| `engines/fair_value_gaps/` | Fair-value-gap engine (3-candle displacement voids + mitigation; standalone) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/fair_value_gaps/CLAUDE.md` |
| `engines/news/` | Economic-calendar (news + holiday) blackout engine | Production — 29 tests + live checks (no Pine source) | `engines/news/CLAUDE.md` |
| `strategies/` | Generic strategy source files (NT8 + MT5 + TradingView research) | Production | `strategies/CLAUDE.md` |
| `indicators/` | Pine Script market-structure indicator rebuild | Under construction — Stage 2b (~95% validated) | `indicators/CLAUDE.md` |
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
- `docs/LWG_Strategy_Framework.md` — Standing reference for how strategies are designed, layered, built, and graded
- `docs/market_structure_engine_spec.md` — Spec for the BOS/SOS market-structure detection engine
- `docs/dynamic_sizing_engine.md` — Design doc for the dynamic sizing & risk engine (sizing, gating, decision log)
- `docs/LWG_Project_State_Snapshot.md` — Current platform state; hand to new Claude.ai chats
- `docs/LWG_Roadmap_And_Open_Questions.md` — Forward plan and open questions; hand to new Claude.ai chats
- `docs/ENGINE_EXTRACTION_ROADMAP.md` — Which SMC-indicator blocks became their own Python engines (SMC extraction COMPLETE — the 8 core blocks plus the later fair-value-gap engine done and Pine-parity-validated; plus 1 off-roadmap news engine)
- `docs/audit/TRADER_MIGRATION_AUDIT.md` — Findings report from the Administrator→trader VPS migration audit
- `.claude/commands/` — Repo slash commands: `/audit-engines`, `/doc-audit`, `/dead-code-audit`, `/regenerate-snapshots`, `/prop-firm-rules-audit` (the former `docs/audit/` prompt templates)
