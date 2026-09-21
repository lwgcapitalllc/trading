# CLAUDE.md — FFT (First Fib Touch)

**Purpose:** the user's hand-traded FFT setup as a bot. Rules: `docs/FFT_SPEC.md`. Version 1 and
every measurement behind it: `backtest/notes/fft_ledger.md`.
**Status (2026-09-21):** lab-ready and matched to the study; NOT yet deployed. No instance config,
never promoted, never run against a broker.

## The rules that are easy to break

- **1-minute bars only.** The 1m trend is a rule, and the 5m and 15m are built from the 1m in
  `frames.py`. `set_timeframe_minutes` refuses anything else.
- **Every decision is made at a 1m close, for the next minute.** The order decided at 10:03's close
  is the one that meets 10:04's prices. Never decide and fill inside one minute.
- **A 5m/15m candle is handed out the moment it is known closed** — on its last minute, or when a
  later window's bar arrives — and always before that later bar is used.
- **A touch spends the leg whether or not it was traded.** That is what "first touch" means in the
  study. Every spent leg is in `strategy.touches` with the rule that refused it.
- **The fib adopts internal swings** (MPC Jarvis's default). The 5m stack is built with the study's
  exact switches; do not "tidy" them to match other bots.
- **A buy limit the bid reached but the ask did not keeps resting** until it fills or TP1 prints —
  only with bid/ask fills on. That is how the study's costed run priced it.
- **No order rests into a weekend or an early-close holiday break** (`_next_minute_shut`). ⚠ The
  shared calendar marks Thanksgiving Day closed; PU Prime trades it until ~13:00 New York. So a plain
  "tomorrow is a holiday" is NOT refused here — only a weekend-length break, or an early close
  followed by a shut day.

## How it is proven — there is no Pine twin, by decision

The user cannot export 1-minute data from TradingView, so the Pine parity gate cannot exist.

- **The engines** (structure, the Structure fib) are gated against MPC Jarvis exports already.
- **The rule layer:** `tools/compare_study.py` runs the bot and
  `backtest/tools/fft_first_touch_study.py` over the same cleaned PU Prime 1m bars and matches every
  trade, outcome and first touch. EXIT 0 needs ≥95% of study trades, ≤5% extra, ≥98% outcomes,
  ≥95% touches both ways. ⚠ The extra-trade limit exists because the gate was mutated (15m rule
  forced on) and first exited 0 anyway.
- **MEASURED 2026-09-21:** 2020-01 → 2025-09: 157/157 trades, 157/157 outcomes, 2,644/2,644 first
  touches. 2025-08 → 2026-09: 34/34, 34/34, 494/494. Through PU Prime ECN with bid/ask fills:
  +0.149R a trade over 152 (2020-25), +0.136R over 34 (last year).
- ⚠ Both share the engines, so an engine defect passes both. **The user's chart check of recent bot
  trades is the step that checks the rule is right** — not yet done.

## Before demo

- The instance config needs `warmup_bars` of about **45,000** — the study warmed 31 days; the
  template's 5,000 is 3.5 days of 1m bars, and the 15m trend would start half-cold.
- The single-run form in the lab offers no 1-minute bar size (hard-coded presets); a lab run needs
  the frame set by hand until that form reads `suggested_bar_value`.
- Run `/live-safety` before anything under `algos/`.
