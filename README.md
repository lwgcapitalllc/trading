# LWG Capital — Trading Operations

## Repo map

Dirs fall into four groups. Only the **Engines** group grows — each new engine
extracted from the SMC indicator (see `docs/ENGINE_EXTRACTION_ROADMAP.md`) is a
new peer dir here. Apps, Tooling, and Docs are fixed.

```
trading/
│
│  ── APPS (deployables) ──────────────────────────────────────────
├── algos/               ← Algo trading suite (Windows VPS demo accounts). ONE BOT LIVE AND ARMED since 2026-08-05;
│                          `algos/live/` is the runtime that takes a validated strategies/python/ bot to real
│                          MT5 orders (docs/LIVE_TRADING_PIPELINE.md)
├── smart-money/         ← Crypto/forex trader scanner and copy-trading candidate pool
├── command-center/      ← Local ops platform: bot monitor, smart money UI, backtests lab
├── strategies/          ← Generic strategy source files organized by runner platform (incl. python/ for the Python runner)
│
│  ── BACKTEST (Python runner — shared infra, like engines/) ────────
├── backtest/            ← Python bar-replay backtest runner: data layer, replay, fills, optimizer (consumed by the lab as runner="python")
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
│   ├── rsi_divergence/  ← RSI-divergence engine (regular divergence at the extremes + live confluence); standalone
│   ├── equal_highs_lows/← Equal Highs/Lows (EQH/EQL) liquidity-level engine; standalone, price-driven
│   ├── candlesticks/    ← Candlestick-pattern engine (15 classic patterns); standalone, OHLC-only — the one engine
│   │                       ported from a THIRD-PARTY indicator rather than from mpc_assistant.pine
│   │                       (SMC extraction COMPLETE — FVG, RSI-div, EQH/EQL and candlesticks pulled later; see ENGINE_EXTRACTION_ROADMAP.md)
│   └── news/            ← Economic-calendar (news + holiday) blackout engine (off-roadmap, not a Pine port; standalone)
│
│  ── TOOLING / SOURCE ────────────────────────────────────────────
├── indicators/          ← Pine Script source — strategies/ (12 strategy() files) + engines/ (16 indicator() files)
├── scripts/             ← Cross-subsystem VPS recovery and bootstrap scripts
├── tools/               ← Standalone utilities (e.g. skool-transcript — rips course video transcripts)
├── education/           ← Course libraries: transcripts, summaries + visual playbooks (e.g. smc/ — the source material behind the engines); learned/ holds one-off video notes from /learn
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
15. `engines/rsi_divergence/CLAUDE.md` — RSI-divergence engine (regular divergence + live confluence), parity rules
16. `engines/equal_highs_lows/CLAUDE.md` — EQH/EQL liquidity-level engine, parity rules
17. `engines/candlesticks/CLAUDE.md` — candlestick-pattern engine, the boundary-tie rule, measured frequencies
18. `engines/news/CLAUDE.md` — news/economic-calendar blackout engine, data paths, validation (no Pine source)
19. `strategies/CLAUDE.md` — strategy source files, runner layout, deployment flow
20. `indicators/CLAUDE.md` — Pine source map + build narrative. The RULES live in `strategies/tradingview/CLAUDE.md` (input-panel contract, annotations, palette) and `indicators/engines/CLAUDE.md` (extraction track + `smc_engine_v2` detection rules)
21. `docs/LWG_Project_State_Snapshot.md` — current platform state across all subsystems
22. `docs/LWG_Roadmap_And_Open_Questions.md` — forward plan and open questions

## Subsystems

| Subsystem | Purpose | Status | Rules |
|---|---|---|---|
| `algos/` | Live algo trading on Windows VPS | **One bot LIVE and ARMED** — `mpc_sos_fade_demo` on a PU Prime ECN **demo** account since 2026-07-31, placing real orders since 2026-08-05. `mpc_bleg_demo` is registered and BENCHED (`account: null`) | `algos/CLAUDE.md` |
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
| `engines/rsi_divergence/` | RSI-divergence engine (regular divergence at the extremes + live confluence; standalone) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/rsi_divergence/CLAUDE.md` |
| `engines/equal_highs_lows/` | Equal Highs/Lows (EQH/EQL) liquidity-level engine (standalone) | Production — 100% Pine parity (VANTAGE_XAUUSD 5m) | `engines/equal_highs_lows/CLAUDE.md` |
| `engines/candlesticks/` | Candlestick-pattern engine, 15 patterns (standalone; ported from a third-party Pine) | Production — 100% Pine parity (VANTAGE_XAUUSD 15m, 14 of 15 patterns fired) | `engines/candlesticks/CLAUDE.md` |
| `engines/news/` | Economic-calendar (news + holiday) blackout engine | Production — 29 tests + live checks (no Pine source) | `engines/news/CLAUDE.md` |
| `strategies/` | Generic strategy source files (NT8 + MT5 + TradingView research) | Production | `strategies/CLAUDE.md` |
| `indicators/` | Pine Script source, split by declaration into `strategies/` + `engines/` | Under construction — Stage 2b (~95% validated) | `indicators/CLAUDE.md` |
| `scripts/` | VPS bootstrap and full-recovery scripts | Stable | `scripts/README.md` |

## Conventions

- **Branch model:** `main`, for everything. There is no second working branch. ⚠ A `backups` branch survives on the old `algos-origin` remote only — it held VPS runtime data, the data-backup-to-GitHub feature was removed 2026-06-21, and nothing writes to it. Do not treat it as live.
- **Deploy:** edit on Mac → `git push` → `ssh forexvps "git pull"` → restart bots. Never SCP/rsync.
- **Secrets:** never commit tokens, API keys, passwords, or `.env` to any branch. See each subsystem's CLAUDE.md Never-Do section.
- **Subsystem independence:** `algos/`, `smart-money/`, and `command-center/` are fully independent. A change to one never touches the others.
- **VPS:** ForexVPS Windows Server. SSH alias: `forexvps`. Repo at `C:\trading\`.

## docs/

Cross-subsystem reference documents:
- `docs/ONBOARDING_NEW_MACHINE.md` — **start here on a fresh machine.** Everything needed to run the Command Center from a bare clone: prerequisites, the per-machine config, the data drop (the DB, run output, bar cache and calendar are all git-ignored, so a clone alone shows an empty app), what works with and without VPS access
- `docs/LIVE_TRADING_PIPELINE.md` — **the plan that takes a validated `strategies/python/` bot to real MT5 orders**: what already exists, what does not, the design decisions (the strategy stays authoritative and the bridge only mirrors; version isolation is frozen params + a source-hash pin), and the build order. Steps 1–4 done 2026-07-30 (`algos/live/`); read it before touching `algos/live/`, `algos/shared/mt5_ops.py` or the Bots page
- `docs/BOT_DEVELOPMENT_METHOD.md` — S.Y.S.T.E.M. six-step process for building and validating any trading bot
- `docs/LWG_Strategy_Framework.md` — Standing reference for how strategies are designed, layered, built, and graded
- `docs/market_structure_engine_spec.md` — Spec for the BOS/SOS market-structure detection engine
- `docs/dynamic_sizing_engine.md` — Design doc for the dynamic sizing & risk engine (sizing, gating, decision log)
- `docs/LWG_Project_State_Snapshot.md` — Current platform state; hand to new Claude.ai chats
- `docs/LWG_Roadmap_And_Open_Questions.md` — Forward plan and open questions; hand to new Claude.ai chats
- `docs/ENGINE_EXTRACTION_ROADMAP.md` — Which SMC-indicator blocks became their own Python engines (SMC extraction COMPLETE — the 8 core blocks plus the later fair-value-gap engine done and Pine-parity-validated; plus 1 off-roadmap news engine)
- `docs/audit/TRADER_MIGRATION_AUDIT.md` — Findings report from the Administrator→trader VPS migration audit
- `.claude/commands/` — Repo slash commands, in two groups. **Build-time** (run BEFORE and DURING the work): `/spec`, `/wire-check`, `/prove`, `/measure`, `/live-safety`, `/port`. **Audits** (look backwards at code already written): `/audit-engines`, `/audit-strategy`, `/doc-audit`, `/dead-code-audit`, `/prop-firm-rules-audit`, `/quant-review`, `/regenerate-snapshots`, `/session-start`. The table in `CLAUDE.md` → *The skills that enforce these* maps each one to the rules it covers
- `.claude/skills/` — Repo slash skills, available on clone: `/learn <video-url>` watches a video and files a note to `education/learned/` (one-time machine setup: `scripts/setup_learning_mode.sh`)
