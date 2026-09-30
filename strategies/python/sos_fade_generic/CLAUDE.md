# CLAUDE.md — strategies/python/sos_fade_generic/ (SOS Fade Generic)

**Purpose:** SOS Fade stripped to its core — arm, shift, fib pullback, 1.0 stop, one target — so it
can be run on other instruments and read plainly. Spec and measurements: `docs/SOS_FADE_GENERIC_SPEC.md`.
**Scope:** the settings panel and how it maps onto SOS Fade. It owns NO trading logic — that is
`../sos_fade/`, and its CLAUDE.md governs every decision this bot makes.
**Status:** built 2026-09-27, lab-registered, 24 tests. ⚠ **Stage 6 is NOT green** — no TradingView
export has been taken at its settings yet, so every lab figure is unverified.

## The rules

- 🔴 **Never put trading logic here.** This bot IS `SosFadeStrategy` built from
  `SosFadeGenericConfig.to_sos_fade()`. A rule this bot needs and SOS Fade lacks goes into SOS Fade
  behind a setting that defaults OFF, with its Pine input — otherwise it is a second implementation
  with no parity gate.
- 🔴 **Every SOS Fade feature that ships ON is named in `to_sos_fade()` and switched off.** A new SOS
  Fade feature that ships ON reaches this bot silently unless it is added there AND to `_OFF` in
  `tests/test_generic.py`. Check both whenever SOS Fade gains a setting.
- **A new pinned setting that the export carries also goes into `_PINNED_LABELS` in
  `tools/compare_generic.py`**, or the gate will accept an export taken with it on.
- **"Enter on a 1m SOS then BOS" replaces the zone limit** (SOS Fade's `exec_shift_entry`, rules in
  `../sos_fade/notes/shift_entry.md`). It pins the fill clock to 1 minute and needs the 1-minute
  feed, which the lab loads when it is on. ⚠ The export gate can never check it — no Pine input.
- **`self.config` is the SOS Fade config**; the generic settings are `self.generic_config`.
- **The tick size comes from the run's cost profile** when it has one (gold's 0.01 would charge a
  GBPJPY run 10x its slippage).
- ⚠ **It has no Pine file by design.** In TradingView it is `sos_fade_strategy.pine` at the settings
  listed in the spec. Its gate is `tools/compare_generic.py`, which refuses an export taken at any
  other settings and then runs SOS Fade's own check.
- ⚠ **Two size floors are a share of price and were set for gold** (minimum gap 0.1%, an engine pin
  in `SosFadeStrategy.engine_config`; minimum stop 0.08%). Read a low FX trade count against them
  before reading it as "no setups on this pair".
