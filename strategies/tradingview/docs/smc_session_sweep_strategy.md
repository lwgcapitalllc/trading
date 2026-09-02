# smc_session_sweep_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `smc_session_sweep_strategy.pine`

---

## [1] SMC SESSION SWEEP STRATEGY — five-step session-sweep continuation model,

```
// SMC SESSION SWEEP STRATEGY — five-step session-sweep continuation model,
// ported from Lewis Kelly's "This SMC Strategy Is Too Simple to Ignore".
//
// 🔴 THE REASONING LIVES IN `strategies/tradingview/CLAUDE.md`, NOT HERE.
// This file carried ~670 lines of explanation until 2026-08-16 — 45% of it, and
// every byte loaded on every read. Aaron: "realistically I will never read these
// comments." Read the doc before changing anything: what each rule is FOR, which
// numbers were measured against what, and the defects each guard exists to stop
// are all there, and several of them are not recoverable from the code.
//
// Before any edit: `python3 indicators/tools/check_active_order.py <this file>`.
// Before trusting a number: this file has NO parity gate and NO Python twin.
// After adding an input: TradingView keys saved values off declaration order per
// type, so inserting one resets every later input of that type on a live chart.
```

