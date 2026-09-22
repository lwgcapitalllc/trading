# CLAUDE.md — FFT (First Fib Touch)

**Purpose:** the user's hand-traded FFT setup as a bot. Rules: `docs/FFT_SPEC.md`. Version 1 and
every measurement behind it: `backtest/notes/fft_ledger.md`.
**Status (2026-09-21):** lab-ready and matched to the study; NOT yet deployed. No instance config,
never promoted, never run against a broker.

## The rules that are easy to break

- **1-minute bars only.** The 1m trend is a rule, and the 5m and 15m are built from the 1m in
  `frames.py`. `set_timeframe_minutes` refuses anything else — and since 2026-09-22 every lab path
  reaches it: `build_strategy(..., timeframe_minutes=frame_minutes(df))` (the single run, the sweep,
  the stack leg). Before that, a run on 5m or 15m bars finished green with zero trades.
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
- **"Skip after 4+ 15m BOS" is a setting, OFF by the user's decision** (2026-09-21). The count is
  the study's `n15` — a shift resets it to 0 — and only the 15m trend BEHIND the trade is read. It is
  an unproven lead; `tools/forward_log.py` grades it (and the other two leads) on demo trades.
- **"Only sweep setups" is a setting, OFF** (2026-09-22). It asks the sweep label at PLACEMENT: at
  the touch the minute is clamped to the 61.8, so the label depends only on the 5m row the order was
  decided on. Checked on 2020-26 real bars: 53/53 traded touches labelled sweep, 0/525 refusals.
  Measured result: `backtest/notes/fft_ledger.md` → *Sweep-only*.
- 🔴 **A sweep setup trades at 1.5x by default — the user's call, 2026-09-22** ("Sweep setup size",
  1.0 = off, refused above 2.0). Sized at PLACEMENT from the same label, so it moves no trade and no
  R, only size: every dollar, drawdown % and profit-factor figure measured before it is at 1x.
  ⚠ In-sample lead. ⚠ The account's half-size floor is half of the BIGGER size (3.75% of room).
- **The equal-level label (`eq_target`, 2026-09-22) is REPORTING ONLY**: an active 5m equal high
  (buy) / low (sell) between the 61.8 and TP2 at the touch, from MPC Jarvis's default engine. It is
  the study's EQT exactly (`tests/test_fft.py` checks it against `fft_confluence_study.feat_5m`);
  lead 4 in the forward log. Unproven: 11/11 on gold, not confirmed on EURUSD or NAS100.
- **The A+ sweep label reads live levels only, and the touch minute only to the 61.8.** Until
  2026-09-21 it counted levels already taken and still drawn, and the touch minute past the fill —
  copied faithfully from the study, which had the same defect (rule 14). Reporting only; no trade moves.
- 🔴 **Live, the bot must be told its broker — "Broker for live fills".** The runner builds every
  strategy with NO cost profile, so without the setting a buy limit fills on the chart's bid while
  the broker fills on the ask: 23 of 76 buys 2020-25 (0 of 16 last year) touched the 61.8 on the bid
  in a minute the ask did not, the emulator held a trade the broker never filled, and the bridge
  halts on exactly that. With it the live bot books the costed gate's trades exactly (checked by
  `compare_study.py --costs`). Blank in the lab — a run's own costs win.
- 🔴 **The shared account's budget sizes the order at PLACEMENT** (`FftExecution.size`, SOS Fade's
  `_fit_to_budget` reasoning). Sized only at the fill, a live order already resting full-size at the
  broker would be refused or shrunk in the emulator alone, and the bridge halts. No room = the touch
  is refused as `room`. Inert with no budget stated, so no backtest moves.
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
  ≥95% touches both ways, and ≥98% agreement on the 15m BOS count and the sweep label; `--overextended`
  also proves the skip removes exactly the 4+ trades. ⚠ The extra-trade limit exists because the gate
  was mutated (15m rule forced on) and first exited 0 anyway; the 15m-count check was mutated too (the
  count never reset on a shift → 211 / 494, exit 1).
- **MEASURED 2026-09-21:** 2020-01 → 2025-09: 157/157 trades, 157/157 outcomes, 2,644/2,644 first
  touches, 15m BOS count and sweep label. 2025-08 → 2026-09: 34/34, 34/34, 494/494. Skip on: 146
  and 26 trades, exactly the study's 157 − 11 and 34 − 8. Through PU Prime ECN with bid/ask fills:
  +0.149R a trade over 152 (2020-25), +0.136R over 34 (last year). Re-run after the two live
  fixes: unchanged, and the bot built as the runner builds it books those runs exactly.
- ⚠ Both share the engines, so an engine defect passes both. **The user's chart check of recent bot
  trades is the step that checks the rule is right** — not yet done.

## Before demo

- **The instance is `algos/markets/fx/instances/fft_1/`** (2026-09-21): demo 700152905, 5%, magic
  770131, priority 4, "Broker for live fills" = puprime_ecn, `warmup_bars` **45,000** — the study
  warmed 31 days; 5,000 is 3.5 days of 1m bars and the 15m trend would start half-cold. ⚠ The
  warm-up is ONE unpaginated MT5 fetch and only fewer than 200 bars refuses, so a short answer
  passes silently: read the bot's `Warmed N bars (first → last)` line on its first start.
- ⚠ **That account's shares already sum past its 10% cap before FFT** (5 + 5 + 2.5; 17.5 with FFT).
  First come first served is the user's call: FFT is shrunk to the room left, down to half its own
  size, and refused below that.
- The lab's run forms offer 1 minute and open on it for FFT (2026-09-22). A run on any other frame
  now FAILS with FFT's own reason; until then it finished "complete, 0 trades" (run 2db0e08a8ccc),
  because the lab never called the frame check. See `backtest/notes/architecture.md`.
  ✅ **The lab run, ECN costs, 5%, sweeps at 1x, 2020-01-01 → 2026-09-22 (run 08c84d0de04f): 187
  trades, PF 1.375, max drawdown 19.19%** — in line with the gate's 152 + 34 costed trades.
- Run `/live-safety` before anything under `algos/`.
- Once it trades: `tools/forward_log.py --start <first demo day>` grades the three leads by replay.
  Check its trade list against the account's history first — a fill the replay does not see is the
  one thing it cannot know. ⚠ It replays RAW bars (as the lab and live bot see them), so it can
  differ from the gate, which feeds both sides cleaned bars.
