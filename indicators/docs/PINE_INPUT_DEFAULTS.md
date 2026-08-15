# Pine strategy input defaults — snapshot

**Taken 2026-08-11, BEFORE the annotation standardisation and the Phase 2 input reorder.**

## Why this file exists

TradingView keys a chart's saved input values off **declaration order within each
type**, not off the input's name. Phase 2 moves the trade-execution knobs to the top
of every strategy, which changes that order — so every chart running these scripts
must be reset to defaults after the paste, and the values below are what it will
reset TO.

This is the record that lets the reorder be **proven cosmetic rather than argued
cosmetic**: re-generate this table after the change and diff it. A default that
moved shows up as a changed row. Nothing else in the repo can catch that — the
parity gates compare decision streams under whatever config the export carried, so
a silently-moved default reads as a legitimately different run.

⚠ **This records the FILE defaults, not Aaron's chart.** If a chart is running a
tuned value that is not the default below, the reset reverts it silently and
nothing errors. Only Aaron can say whether any chart differs.

⚠ **"Reset settings to defaults" resets the STYLE tab too, so it re-ticks
"Trades on chart" — untick it again in the same visit.** It cannot be defaulted
from Pine (no `strategy()` argument exists), it survives ordinary code saves once
unticked, and the strategies here draw their own position boxes precisely so the
built-in markers can be off. Applies to all six strategy files, the session sweep
(`smc_session_sweep_strategy.pine`, called `mpc_m15_playbook_strategy.pine` until
2026-08-15) included. Full note: `indicators/CLAUDE.md` → *"Trades on chart" CANNOT be
defaulted from code*.

`ord` is the per-type declaration index — the number TradingView actually keys on,
and the only column the reorder is expected to change.


## mpc_strategy.pine — 156 inputs

| # | type | ord | group | title | default | var | line |
|---|---|---|---|---|---|---|---|
| 1 | bool | 1 | Confirmation Table | Show Confirmation Table | `false` | `showConfTable` | 34 |
| 2 | string | 1 | Confirmation Table | Table Position | `"Top Right"` | `tablePositionInput` | 39 |
| 3 | string | 2 | Confirmation Table | Table Text Size | `"Small"` | `tableSizeInput` | 40 |
| 4 | bool | 2 | Market Structure | Hide Everything Except Market Structure | `false` | `marketStructureOnly` | 76 |
| 5 | string | 3 | Market Structure | Structure Label Size | `"Small"` | `structLabelSize` | 77 |
| 6 | bool | 3 | Market Structure | Show External Structure | `true` | `showExternal` | 78 |
| 7 | bool | 4 | Market Structure | Show Internal Structure | `false` | `showInternal` | 79 |
| 8 | bool | 5 | Market Structure | Show Historic Internal Structure | `false` | `showHistoricalInternal` | 80 |
| 9 | bool | 6 | Market Structure | Show Swing Point Labels | `false` | `showSwingLabels` | 81 |
| 10 | bool | 7 | Fair Value Gaps | Show FVG (REQUIRED — feeds entries) | `true` | `showFVGInput` | 105 |
| 11 | bool | 8 | Fair Value Gaps | Directional FVGs Only | `false` | `fvgDirOnly` | 107 |
| 12 | color | 1 | Fair Value Gaps | Bullish FVG | `color.new(color.gray, 80)` | `fvgBullColor` | 108 |
| 13 | color | 2 | Fair Value Gaps | Bearish FVG | `color.new(color.gray, 80)` | `fvgBearColor` | 109 |
| 14 | float | 1 | Fair Value Gaps | FVG Min Gap - below 15m (% of price) | `0.0` | `fvgThreshLTF` | 121 |
| 15 | float | 2 | Fair Value Gaps | FVG Min Gap - 15m and above (% of price) | `0.1` | `fvgThreshHTF` | 122 |
| 16 | bool | 9 | Fair Value Gaps | FVG: middle bar must close past the gap (15m+) | `true` | `fvgReqCloseHTF` | 129 |
| 17 | int | 1 | Fair Value Gaps | Max Active FVGs | `7` | `fvgMaxCount` | 131 |
| 18 | bool | 10 | Fair Value Gaps | FVG: keep until broken through (not on tap) | `true` | `fvgKeepUntilBroken` | 132 |
| 19 | int | 2 | A+ Setup | Max time: sweep → SOS (minutes) | `4320` | `aplusWindow` | 143 |
| 20 | bool | 11 | A+ Debug | Show missed setups (2 of 3 or better) | `true` | `debugShow23` | 149 |
| 21 | bool | 12 | A+ Debug | …include ones armed by a disabled source | `false` | `debugShow23Disarmed` | 150 |
| 22 | string | 4 | A+ Debug | Which misses to draw | `"Near misses only"` | `debug23Filter` | 151 |
| 23 | int | 3 | A+ Debug | Only draw debug callouts from the last N days (0 = all) | `3` | `debugDays` | 152 |
| 24 | bool | 13 | RSI Divergence | Track RSI divergence (REQUIRED — arms setups + veto) | `true` | `showDivInput` | 158 |
| 25 | bool | 14 | RSI Divergence | Show divergence history | `true` | `showDivHistory` | 160 |
| 26 | int | 4 | RSI Divergence | RSI length | `14` | `divRsiLen` | 162 |
| 27 | int | 5 | RSI Divergence | Pivot width (bars) | `5` | `divPivotLen` | 163 |
| 28 | int | 6 | RSI Divergence | Oversold level | `25` | `divOS` | 164 |
| 29 | int | 7 | RSI Divergence | Overbought level | `75` | `divOB` | 165 |
| 30 | int | 8 | RSI Divergence | Divergence valid for (bars) | `100` | `divValidBars` | 166 |
| 31 | bool | 15 | RSI Divergence | Veto setups on extreme/divergence | `true` | `divVeto` | 167 |
| 32 | int | 9 | RSI Divergence | Extreme overbought | `80` | `divExtremeOB` | 168 |
| 33 | int | 10 | RSI Divergence | Extreme oversold | `20` | `divExtremeOS` | 169 |
| 34 | bool | 16 | Trading Sessions | Show Sessions | `false` | `showSessionsInput` | 175 |
| 35 | bool | 17 | Trading Sessions | Show session names | `false` | `showSessionNames` | 177 |
| 36 | bool | 18 | Trading Sessions | Show All History | `false` | `showHistoricSessions` | 178 |
| 37 | bool | 19 | FIRST_SESSION_GROUP | Show session | `true` | `showFirst` | 188 |
| 38 | string | 5 | FIRST_SESSION_GROUP | Displayed name | `"Tokyo"` | `firstSessionName` | 189 |
| 39 | session | 1 | FIRST_SESSION_GROUP | Session time | `"0900-1800"` | `firstSessionTime` | 190 |
| 40 | string | 6 | FIRST_SESSION_GROUP | Session timezone | `"Asia/Tokyo"` | `firstSessionTZ` | 191 |
| 41 | color | 3 | FIRST_SESSION_GROUP | Session color | `color.new(#FF5252, 92)` | `firstSessionColor` | 192 |
| 42 | bool | 20 | SECOND_SESSION_GROUP | Show session | `true` | `showSecond` | 195 |
| 43 | string | 7 | SECOND_SESSION_GROUP | Displayed name | `"London"` | `secondSessionName` | 196 |
| 44 | session | 2 | SECOND_SESSION_GROUP | Session time | `"0800-1700"` | `secondSessionTime` | 197 |
| 45 | string | 8 | SECOND_SESSION_GROUP | Session timezone | `"Europe/London"` | `secondSessionTZ` | 198 |
| 46 | color | 4 | SECOND_SESSION_GROUP | Session color | `color.new(#2962FF, 92)` | `secondSessionColor` | 199 |
| 47 | bool | 21 | THIRD_SESSION_GROUP | Show session | `true` | `showThird` | 202 |
| 48 | string | 9 | THIRD_SESSION_GROUP | Displayed name | `"New York"` | `thirdSessionName` | 203 |
| 49 | session | 3 | THIRD_SESSION_GROUP | Session time | `"0800-1700"` | `thirdSessionTime` | 204 |
| 50 | string | 10 | THIRD_SESSION_GROUP | Session timezone | `"America/New_York"` | `thirdSessionTZ` | 205 |
| 51 | color | 5 | THIRD_SESSION_GROUP | Session color | `color.new(#FFEB3B, 90)` | `thirdSessionColor` | 206 |
| 52 | bool | 22 | Liquidity Levels | Show All Liquidity Levels (REQUIRED — arms sweeps) | `true` | `i_showLiquidityInput` | 217 |
| 53 | bool | 23 | Liquidity Levels | Show Labels | `true` | `i_showLabels` | 219 |
| 54 | string | 11 | Liquidity Levels | Liquidity Label Size | `"Small"` | `liqLabelSize` | 220 |
| 55 | bool | 24 | Liquidity Levels | Previous Day H/L | `true` | `i_isDailyEnabled` | 227 |
| 56 | bool | 25 | Liquidity Levels | Previous Week H/L | `true` | `i_isWeeklyEnabled` | 228 |
| 57 | bool | 26 | Liquidity Levels | Sessions H/L | `true` | `i_showSessionHL` | 229 |
| 58 | bool | 27 | Liquidity Levels | Previous Week Close (PWC) | `true` | `i_showPWC` | 236 |
| 59 | bool | 28 | Liquidity Levels | H4 High/Low Sweep (SSH/BSL) | `true` | `i_showH4Sweep` | 237 |
| 60 | int | 11 | Liquidity Levels | Label Y Offset (ticks) | `300` | `i_lblOffset` | 238 |
| 61 | int | 12 | Liquidity Levels | Line Extension (bars) | `50` | `i_lineExtend` | 239 |
| 62 | bool | 29 | Internal Fib | Show Internal Fib | `false` | `showIFibInput` | 251 |
| 63 | int | 13 | Internal Fib | Line Extension (bars) | `30` | `iFibExtend` | 253 |
| 64 | color | 6 | Internal Fib | TP2 / 0.382 | `#4caf50` | `iFibo1Color` | 255 |
| 65 | string | 12 | Internal Fib |  | `"┈"` | `iFibo1Style` | 256 |
| 66 | color | 7 | Internal Fib | TP1 / 0.500 | `#4caf50` | `iFibo2Color` | 258 |
| 67 | string | 13 | Internal Fib |  | `"┈"` | `iFibo2Style` | 259 |
| 68 | color | 8 | Internal Fib | E1 / 0.618 | `#FF9800` | `iFibo3Color` | 261 |
| 69 | string | 14 | Internal Fib |  | `"┈"` | `iFibo3Style` | 262 |
| 70 | color | 9 | Internal Fib | E2 / 0.702 | `#FF9800` | `iFibo4Color` | 264 |
| 71 | string | 15 | Internal Fib |  | `"┈"` | `iFibo4Style` | 265 |
| 72 | color | 10 | Internal Fib | E3 / 0.786 | `#FF9800` | `iFibo5Color` | 267 |
| 73 | string | 16 | Internal Fib |  | `"┈"` | `iFibo5Style` | 268 |
| 74 | color | 11 | Internal Fib | E4 / 0.886 | `#FF9800` | `iFibo6Color` | 270 |
| 75 | string | 17 | Internal Fib |  | `"┈"` | `iFibo6Style` | 271 |
| 76 | color | 12 | Internal Fib | TP3 / 0.000 | `#4caf50` | `iFibo0Color` | 273 |
| 77 | string | 18 | Internal Fib |  | `"─"` | `iFibo0Style` | 274 |
| 78 | color | 13 | Internal Fib | 1.000 | `#4caf50` | `iFibo100Color` | 276 |
| 79 | string | 19 | Internal Fib |  | `"─"` | `iFibo100Style` | 277 |
| 80 | bool | 30 | External Fib | Show External Fib (REQUIRED — SL/TP/entry levels) | `true` | `showFiboInput` | 283 |
| 81 | string | 20 | External Fib | Label Style | `"TP/Entry"` | `sharedLabelMode` | 285 |
| 82 | int | 14 | External Fib | Line Extension (bars) | `80` | `fiboLineExtend` | 286 |
| 83 | bool | 31 | External Fib | TP2 / 0.382 | `true` | `isFibo1ToShow` | 288 |
| 84 | color | 14 | External Fib |  | `#4caf50` | `fibo1Color` | 290 |
| 85 | string | 21 | External Fib |  | `"┈"` | `fibo1Style` | 291 |
| 86 | bool | 32 | External Fib | TP1 / 0.500 | `true` | `isFibo2ToShow` | 293 |
| 87 | color | 15 | External Fib |  | `#4caf50` | `fibo2Color` | 295 |
| 88 | string | 22 | External Fib |  | `"┈"` | `fibo2Style` | 296 |
| 89 | bool | 33 | External Fib | E1 / 0.618 | `true` | `isFibo3ToShow` | 298 |
| 90 | color | 16 | External Fib |  | `#2196F3` | `fibo3Color` | 300 |
| 91 | string | 23 | External Fib |  | `"┈"` | `fibo3Style` | 301 |
| 92 | bool | 34 | External Fib | E2 / 0.702 | `true` | `isFibo4ToShow` | 303 |
| 93 | color | 17 | External Fib |  | `#2196F3` | `fibo4Color` | 305 |
| 94 | string | 24 | External Fib |  | `"┈"` | `fibo4Style` | 306 |
| 95 | bool | 35 | External Fib | E3 / 0.786 | `true` | `isFibo5ToShow` | 308 |
| 96 | color | 18 | External Fib |  | `#2196F3` | `fibo5Color` | 310 |
| 97 | string | 25 | External Fib |  | `"┈"` | `fibo5Style` | 311 |
| 98 | bool | 36 | External Fib | E4 / 0.886 | `true` | `isFibo6ToShow` | 313 |
| 99 | color | 19 | External Fib |  | `#2196F3` | `fibo6Color` | 315 |
| 100 | string | 26 | External Fib |  | `"┈"` | `fibo6Style` | 316 |
| 101 | bool | 37 | External Fib | 1.000 | `true` | `isFibo10ToShow` | 318 |
| 102 | color | 20 | External Fib |  | `#2196F3` | `fibo10Color` | 320 |
| 103 | string | 27 | External Fib |  | `"┈"` | `fibo10Style` | 321 |
| 104 | bool | 38 | External Fib | TP3 / 0.000 | `true` | `isFibo7ToShow` | 323 |
| 105 | color | 21 | External Fib |  | `#4caf50` | `fibo7Color` | 325 |
| 106 | string | 28 | External Fib |  | `"┈"` | `fibo7Style` | 326 |
| 107 | bool | 39 | Sniper Fib | Sniper Zone | `false` | `showSniperFib` | 352 |
| 108 | bool | 40 | Strategy Execution | Trade longs | `true` | `execLongs` | 389 |
| 109 | bool | 41 | Strategy Execution | Trade shorts | `true` | `execShorts` | 390 |
| 110 | bool | 42 | Strategy Execution | Trade A+ setups | `true` | `execAplus` | 391 |
| 111 | bool | 43 | Strategy Execution | Trade B-Leg setups | `false` | `execBLeg` | 392 |
| 112 | float | 3 | Strategy Execution |    ↳ B-Leg: days to watch for the late retrace | `1.25` | `bLegMaxDays` | 393 |
| 113 | bool | 44 | Strategy Execution | Arm on liquidity sweep | `true` | `execArmSweep` | 396 |
| 114 | bool | 45 | Strategy Execution | Arm on RSI divergence | `false` | `execArmDiv` | 397 |
| 115 | bool | 46 | Strategy Execution | Respect divergence/extreme veto | `true` | `execRespectVeto` | 398 |
| 116 | bool | 47 | Strategy Execution | Require an FVG in the zone | `true` | `execReqFVG` | 405 |
| 117 | bool | 48 | Strategy Execution | Gap must sit fully past 0.5 | `true` | `execFvgDeepOnly` | 406 |
| 118 | bool | 49 | Strategy Execution | Gap must pre-date the zone | `false` | `execFvgPreZone` | 407 |
| 119 | bool | 50 | Strategy Execution | Gap on a fib → enter on the fib | `false` | `execFibOverlap` | 408 |
| 120 | bool | 51 | Strategy Execution | Floating gap → its own deep edge | `false` | `execFibDeepEdge` | 409 |
| 121 | bool | 52 | Strategy Execution | Floating gap → nearest fib (either side) | `true` | `execFibNearest` | 410 |
| 122 | bool | 53 | Strategy Execution | Floating gap → nearest fib shallower | `false` | `execDeepFib` | 411 |
| 123 | bool | 54 | Strategy Execution | Allow Sniper Zone as entry confirmation | `false` | `execConfSZ` | 417 |
| 124 | bool | 55 | Strategy Execution | Only fade HTF exhaustion, not breakouts | `false` | `execHtfExhaustOnly` | 420 |
| 125 | string | 29 | Strategy Execution |    ↳ HTF exhaustion source | `"Weekly"` | `execHtfSource` | 421 |
| 126 | string | 30 | Strategy Execution | Weekly bias requirement | `"Ignore"` | `execHtfWeekly` | 422 |
| 127 | string | 31 | Strategy Execution | Daily bias requirement | `"Ignore"` | `execHtfDaily` | 423 |
| 128 | bool | 56 | Strategy Execution | No entries in the final hour (16:00-17:00 NY) | `true` | `execNoLateDay` | 424 |
| 129 | float | 4 | Strategy Execution | Risk % per trade | `10` | `execRiskPct` | 427 |
| 130 | string | 32 | Strategy Execution | Stop fib level (deep side of 0.5) | `"0.886"` | `execSlLevel` | 434 |
| 131 | bool | 57 | Strategy Execution |    ↳ Entries at 0.786 or deeper stop at 1.0 | `false` | `execSlDeep` | 449 |
| 132 | float | 5 | Strategy Execution | Stop buffer beyond the level (ticks) | `0.0` | `execSlBufTk` | 450 |
| 133 | string | 33 | Strategy Execution | Minimum stop distance | `"% of price"` | `execMinStopMode` | 459 |
| 134 | float | 6 | Strategy Execution |    ↳ Minimum stop floor (unit = mode above) | `0.08` | `execMinStopVal` | 460 |
| 135 | float | 7 | Strategy Execution | TP1 size % | `0` | `execTp1Pct` | 463 |
| 136 | float | 8 | Strategy Execution | TP2 size % | `0` | `execTp2Pct` | 464 |
| 137 | float | 9 | Strategy Execution | Breakeven buffer (ticks) | `30` | `execBeBufTk` | 471 |
| 138 | string | 34 | Strategy Execution | Runner trail method | `"Structure + % ratchet"` | `execRunnerTrail` | 474 |
| 139 | float | 10 | Strategy Execution |    ↳ Structure trail buffer (ticks) | `20` | `execStructTrailBufTk` | 475 |
| 140 | float | 11 | Strategy Execution |    ↳ Runner ratchet step (% of price) | `1.0` | `execTrailPct` | 476 |
| 141 | string | 35 | Strategy Execution | TP2 → stop floor | `"TP1 price"` | `execTp2StopMode` | 477 |
| 142 | float | 12 | Strategy Execution | Runner trail step ($ of price) | `5.0` | `execTrailStep` | 481 |
| 143 | bool | 58 | Strategy Execution | Close on opposite SOS | `false` | `execCloseOppSOS` | 482 |
| 144 | bool | 59 | Strategy Execution | Show entry confluence label | `true` | `execShowConfLabel` | 485 |
| 145 | string | 36 | Strategy Execution |    ↳ keep labels for which results | `"All"` | `execLabelWhich` | 486 |
| 146 | string | 37 | Strategy Execution |    ↳ No-FVG entries need | `"Any"` | `execNoGapArm` | 495 |
| 147 | float | 13 | Strategy Execution |    ↳ label distance from price (ATR) | `6` | `execLabelOff` | 497 |
| 148 | bool | 60 | Strategy Execution | Show position box (result) | `true` | `execShowPosBox` | 498 |
| 149 | bool | 61 | Strategy Execution |    ↳ Label the TP bands (TP1/TP2/TP3) | `true` | `execShowExitLines` | 499 |
| 150 | bool | 62 | Liquidity Levels | Equal Highs/Lows (EQH/EQL) | `true` | `eqShowInput` | 1823 |
| 151 | bool | 63 | Liquidity Levels |    ↳ A gap on an EQ level survives the FVG cap | `true` | `eqExemptFvg` | 1824 |
| 152 | float | 14 | Result Stats | Breakeven band (R) | `0.15` | `execBeBandR` | 4113 |
| 153 | bool | 64 | A+ Debug | Mark blocked trades on chart (pink) | `true` | `showBlockTag` | 4595 |
| 154 | string | 38 | Strategy Execution | Time stop | `"Before TP1 only"` | `execTimeStopMode` | 5048 |
| 155 | float | 15 | Strategy Execution |    ↳ Time stop (hours) | `36.0` | `execTimeStopHrs` | 5049 |
| 156 | bool | 65 | Diagnostic Log | Log every trade + miss to Pine Logs | `true` | `execDiagLog` | 5115 |

## mpc_b_leg_strategy.pine — 172 inputs

| # | type | ord | group | title | default | var | line |
|---|---|---|---|---|---|---|---|
| 1 | bool | 1 | Confirmation Table | Show Confirmation Table | `false` | `showConfTable` | 42 |
| 2 | string | 1 | Confirmation Table | Table Position | `"Top Center"` | `tablePositionInput` | 43 |
| 3 | string | 2 | Confirmation Table | Table Text Size | `"Tiny"` | `tableSizeInput` | 44 |
| 4 | bool | 2 | Market Structure | Hide Everything Except Market Structure | `false` | `marketStructureOnly` | 82 |
| 5 | string | 3 | Market Structure | Structure Label Size | `"Small"` | `structLabelSize` | 83 |
| 6 | bool | 3 | Market Structure | Show External Structure | `true` | `showExternal` | 84 |
| 7 | bool | 4 | Market Structure | Show Internal Structure | `false` | `showInternal` | 85 |
| 8 | bool | 5 | Market Structure | Show Historic Internal Structure | `false` | `showHistoricalInternal` | 86 |
| 9 | bool | 6 | Market Structure | Show Swing Point Labels | `false` | `showSwingLabels` | 87 |
| 10 | bool | 7 | Fair Value Gaps | Show FVG (REQUIRED — feeds entries) | `true` | `showFVGInput` | 103 |
| 11 | bool | 8 | Fair Value Gaps | Directional FVGs Only | `false` | `fvgDirOnly` | 105 |
| 12 | color | 1 | Fair Value Gaps | Bullish FVG | `color.new(color.gray, 80)` | `fvgBullColor` | 106 |
| 13 | color | 2 | Fair Value Gaps | Bearish FVG | `color.new(color.gray, 80)` | `fvgBearColor` | 107 |
| 14 | float | 1 | Fair Value Gaps | FVG Min Gap (% of price) | `0.1` | `fvgThreshPct` | 110 |
| 15 | int | 1 | Fair Value Gaps | Max Active FVGs | `7` | `fvgMaxCount` | 111 |
| 16 | bool | 9 | Fair Value Gaps | FVG: keep until broken through (not on tap) | `true` | `fvgKeepUntilBroken` | 112 |
| 17 | int | 2 | A+ Setup | Max time: sweep → SOS (minutes) | `4320` | `aplusWindow` | 123 |
| 18 | bool | 10 | A+ Debug | Show missed setups (2 of 3 or better) | `true` | `debugShow23` | 129 |
| 19 | bool | 11 | A+ Debug | …include ones armed by a disabled source | `false` | `debugShow23Disarmed` | 130 |
| 20 | string | 4 | A+ Debug | Which misses to draw | `"Near misses only"` | `debug23Filter` | 131 |
| 21 | int | 3 | A+ Debug | Only draw debug callouts from the last N days (0 = all) | `3` | `debugDays` | 132 |
| 22 | bool | 12 | RSI Divergence | Track RSI divergence (REQUIRED — arms setups + veto) | `true` | `showDivInput` | 138 |
| 23 | bool | 13 | RSI Divergence | Show divergence history | `true` | `showDivHistory` | 140 |
| 24 | int | 4 | RSI Divergence | RSI length | `14` | `divRsiLen` | 142 |
| 25 | int | 5 | RSI Divergence | Pivot width (bars) | `5` | `divPivotLen` | 143 |
| 26 | int | 6 | RSI Divergence | Oversold level | `25` | `divOS` | 144 |
| 27 | int | 7 | RSI Divergence | Overbought level | `75` | `divOB` | 145 |
| 28 | int | 8 | RSI Divergence | Divergence valid for (bars) | `100` | `divValidBars` | 146 |
| 29 | bool | 14 | RSI Divergence | Veto setups on extreme/divergence | `true` | `divVeto` | 147 |
| 30 | int | 9 | RSI Divergence | Extreme overbought | `80` | `divExtremeOB` | 148 |
| 31 | int | 10 | RSI Divergence | Extreme oversold | `20` | `divExtremeOS` | 149 |
| 32 | bool | 15 | Trading Sessions | Show Sessions | `false` | `showSessionsInput` | 155 |
| 33 | bool | 16 | Trading Sessions | Show session names | `false` | `showSessionNames` | 157 |
| 34 | bool | 17 | Trading Sessions | Show All History | `false` | `showHistoricSessions` | 158 |
| 35 | bool | 18 | FIRST_SESSION_GROUP | Show session | `true` | `showFirst` | 168 |
| 36 | string | 5 | FIRST_SESSION_GROUP | Displayed name | `"Tokyo"` | `firstSessionName` | 169 |
| 37 | session | 1 | FIRST_SESSION_GROUP | Session time | `"0900-1800"` | `firstSessionTime` | 170 |
| 38 | string | 6 | FIRST_SESSION_GROUP | Session timezone | `"Asia/Tokyo"` | `firstSessionTZ` | 171 |
| 39 | color | 3 | FIRST_SESSION_GROUP | Session color | `color.new(#FF5252, 92)` | `firstSessionColor` | 172 |
| 40 | bool | 19 | SECOND_SESSION_GROUP | Show session | `true` | `showSecond` | 175 |
| 41 | string | 7 | SECOND_SESSION_GROUP | Displayed name | `"London"` | `secondSessionName` | 176 |
| 42 | session | 2 | SECOND_SESSION_GROUP | Session time | `"0800-1700"` | `secondSessionTime` | 177 |
| 43 | string | 8 | SECOND_SESSION_GROUP | Session timezone | `"Europe/London"` | `secondSessionTZ` | 178 |
| 44 | color | 4 | SECOND_SESSION_GROUP | Session color | `color.new(#2962FF, 92)` | `secondSessionColor` | 179 |
| 45 | bool | 20 | THIRD_SESSION_GROUP | Show session | `true` | `showThird` | 182 |
| 46 | string | 9 | THIRD_SESSION_GROUP | Displayed name | `"New York"` | `thirdSessionName` | 183 |
| 47 | session | 3 | THIRD_SESSION_GROUP | Session time | `"0800-1700"` | `thirdSessionTime` | 184 |
| 48 | string | 10 | THIRD_SESSION_GROUP | Session timezone | `"America/New_York"` | `thirdSessionTZ` | 185 |
| 49 | color | 5 | THIRD_SESSION_GROUP | Session color | `color.new(#FFEB3B, 90)` | `thirdSessionColor` | 186 |
| 50 | bool | 21 | Liquidity Levels | Show All Liquidity Levels (REQUIRED — arms sweeps) | `true` | `i_showLiquidityInput` | 197 |
| 51 | bool | 22 | Liquidity Levels | Show Labels | `true` | `i_showLabels` | 199 |
| 52 | string | 11 | Liquidity Levels | Liquidity Label Size | `"Small"` | `liqLabelSize` | 200 |
| 53 | bool | 23 | Liquidity Levels | Previous Day H/L | `true` | `i_isDailyEnabled` | 207 |
| 54 | bool | 24 | Liquidity Levels | Previous Week H/L | `true` | `i_isWeeklyEnabled` | 208 |
| 55 | bool | 25 | Liquidity Levels | Sessions H/L | `true` | `i_showSessionHL` | 209 |
| 56 | bool | 26 | Liquidity Levels | Previous Week Close (PWC) | `true` | `i_showPWC` | 216 |
| 57 | bool | 27 | Liquidity Levels | H4 High/Low Sweep (SSH/BSL) | `true` | `i_showH4Sweep` | 217 |
| 58 | int | 11 | Liquidity Levels | Label Y Offset (ticks) | `300` | `i_lblOffset` | 218 |
| 59 | int | 12 | Liquidity Levels | Line Extension (bars) | `50` | `i_lineExtend` | 219 |
| 60 | bool | 28 | Internal Fib | Show Internal Fib | `false` | `showIFibInput` | 231 |
| 61 | int | 13 | Internal Fib | Line Extension (bars) | `30` | `iFibExtend` | 233 |
| 62 | color | 6 | Internal Fib | TP2 / 0.382 | `#4caf50` | `iFibo1Color` | 235 |
| 63 | string | 12 | Internal Fib |  | `"┈"` | `iFibo1Style` | 236 |
| 64 | color | 7 | Internal Fib | TP1 / 0.500 | `#4caf50` | `iFibo2Color` | 238 |
| 65 | string | 13 | Internal Fib |  | `"┈"` | `iFibo2Style` | 239 |
| 66 | color | 8 | Internal Fib | E1 / 0.618 | `#FF9800` | `iFibo3Color` | 241 |
| 67 | string | 14 | Internal Fib |  | `"┈"` | `iFibo3Style` | 242 |
| 68 | color | 9 | Internal Fib | E2 / 0.702 | `#FF9800` | `iFibo4Color` | 244 |
| 69 | string | 15 | Internal Fib |  | `"┈"` | `iFibo4Style` | 245 |
| 70 | color | 10 | Internal Fib | E3 / 0.786 | `#FF9800` | `iFibo5Color` | 247 |
| 71 | string | 16 | Internal Fib |  | `"┈"` | `iFibo5Style` | 248 |
| 72 | color | 11 | Internal Fib | E4 / 0.886 | `#FF9800` | `iFibo6Color` | 250 |
| 73 | string | 17 | Internal Fib |  | `"┈"` | `iFibo6Style` | 251 |
| 74 | color | 12 | Internal Fib | TP3 / 0.000 | `#4caf50` | `iFibo0Color` | 253 |
| 75 | string | 18 | Internal Fib |  | `"─"` | `iFibo0Style` | 254 |
| 76 | color | 13 | Internal Fib | 1.000 | `#4caf50` | `iFibo100Color` | 256 |
| 77 | string | 19 | Internal Fib |  | `"─"` | `iFibo100Style` | 257 |
| 78 | bool | 29 | External Fib | Show External Fib (REQUIRED — SL/TP/entry levels) | `true` | `showFiboInput` | 263 |
| 79 | string | 20 | External Fib | Label Style | `"TP/Entry"` | `sharedLabelMode` | 265 |
| 80 | int | 14 | External Fib | Line Extension (bars) | `80` | `fiboLineExtend` | 266 |
| 81 | bool | 30 | External Fib | TP2 / 0.382 | `true` | `isFibo1ToShow` | 268 |
| 82 | color | 14 | External Fib |  | `#4caf50` | `fibo1Color` | 270 |
| 83 | string | 21 | External Fib |  | `"┈"` | `fibo1Style` | 271 |
| 84 | bool | 31 | External Fib | TP1 / 0.500 | `true` | `isFibo2ToShow` | 273 |
| 85 | color | 15 | External Fib |  | `#4caf50` | `fibo2Color` | 275 |
| 86 | string | 22 | External Fib |  | `"┈"` | `fibo2Style` | 276 |
| 87 | bool | 32 | External Fib | E1 / 0.618 | `true` | `isFibo3ToShow` | 278 |
| 88 | color | 16 | External Fib |  | `#2196F3` | `fibo3Color` | 280 |
| 89 | string | 23 | External Fib |  | `"┈"` | `fibo3Style` | 281 |
| 90 | bool | 33 | External Fib | E2 / 0.702 | `true` | `isFibo4ToShow` | 283 |
| 91 | color | 17 | External Fib |  | `#2196F3` | `fibo4Color` | 285 |
| 92 | string | 24 | External Fib |  | `"┈"` | `fibo4Style` | 286 |
| 93 | bool | 34 | External Fib | E3 / 0.786 | `true` | `isFibo5ToShow` | 288 |
| 94 | color | 18 | External Fib |  | `#2196F3` | `fibo5Color` | 290 |
| 95 | string | 25 | External Fib |  | `"┈"` | `fibo5Style` | 291 |
| 96 | bool | 35 | External Fib | E4 / 0.886 | `true` | `isFibo6ToShow` | 293 |
| 97 | color | 19 | External Fib |  | `#2196F3` | `fibo6Color` | 295 |
| 98 | string | 26 | External Fib |  | `"┈"` | `fibo6Style` | 296 |
| 99 | bool | 36 | External Fib | 1.000 | `true` | `isFibo10ToShow` | 298 |
| 100 | color | 20 | External Fib |  | `#2196F3` | `fibo10Color` | 300 |
| 101 | string | 27 | External Fib |  | `"┈"` | `fibo10Style` | 301 |
| 102 | bool | 37 | External Fib | TP3 / 0.000 | `true` | `isFibo7ToShow` | 303 |
| 103 | color | 21 | External Fib |  | `#4caf50` | `fibo7Color` | 305 |
| 104 | string | 28 | External Fib |  | `"┈"` | `fibo7Style` | 306 |
| 105 | bool | 38 | Cycle Fib | Show Cycle Fib | `false` | `showMacroFibInput` | 315 |
| 106 | int | 15 | Cycle Fib | Line Extension (bars) | `180` | `macroLineExtend` | 317 |
| 107 | int | 16 | Cycle Fib | Draw Up To Timeframe (min) | `30` | `macroMaxTfMin` | 318 |
| 108 | bool | 39 | Cycle Fib | TP3 / 0.000 | `true` | `showMacro0` | 320 |
| 109 | color | 22 | Cycle Fib |  | `#4caf50` | `macro0Color` | 321 |
| 110 | string | 29 | Cycle Fib |  | `"─"` | `macro0Style` | 322 |
| 111 | bool | 40 | Cycle Fib | TP2 / 0.382 | `true` | `showMacro382` | 324 |
| 112 | color | 23 | Cycle Fib |  | `#4caf50` | `macro382Color` | 325 |
| 113 | string | 30 | Cycle Fib |  | `"┈"` | `macro382Style` | 326 |
| 114 | bool | 41 | Cycle Fib | TP1 / 0.500 | `true` | `showMacro50` | 328 |
| 115 | color | 24 | Cycle Fib |  | `#4caf50` | `macro50Color` | 329 |
| 116 | string | 31 | Cycle Fib |  | `"┈"` | `macro50Style` | 330 |
| 117 | bool | 42 | Cycle Fib | E1 / 0.618 | `true` | `showMacro618` | 332 |
| 118 | color | 25 | Cycle Fib |  | `#2196F3` | `macro618Color` | 333 |
| 119 | string | 32 | Cycle Fib |  | `"┈"` | `macro618Style` | 334 |
| 120 | bool | 43 | Cycle Fib | E2 / 0.702 | `true` | `showMacro702` | 336 |
| 121 | color | 26 | Cycle Fib |  | `#2196F3` | `macro702Color` | 337 |
| 122 | string | 33 | Cycle Fib |  | `"┈"` | `macro702Style` | 338 |
| 123 | bool | 44 | Cycle Fib | E3 / 0.786 | `true` | `showMacro786` | 340 |
| 124 | color | 27 | Cycle Fib |  | `#2196F3` | `macro786Color` | 341 |
| 125 | string | 34 | Cycle Fib |  | `"┈"` | `macro786Style` | 342 |
| 126 | bool | 45 | Cycle Fib | E4 / 0.886 | `true` | `showMacro886` | 344 |
| 127 | color | 28 | Cycle Fib |  | `#2196F3` | `macro886Color` | 345 |
| 128 | string | 35 | Cycle Fib |  | `"┈"` | `macro886Style` | 346 |
| 129 | bool | 46 | Cycle Fib | 1.000 | `true` | `showMacro100` | 348 |
| 130 | color | 29 | Cycle Fib |  | `#2196F3` | `macro100Color` | 349 |
| 131 | string | 36 | Cycle Fib |  | `"─"` | `macro100Style` | 350 |
| 132 | bool | 47 | Sniper Fib | Sniper Zone | `false` | `showSniperFib` | 356 |
| 133 | bool | 48 | Strategy Execution | Trade longs | `true` | `execLongs` | 395 |
| 134 | bool | 49 | Strategy Execution | Trade shorts | `true` | `execShorts` | 396 |
| 135 | bool | 50 | Strategy Execution | A+ has priority (stand the B-leg down) | `true` | `execAplus` | 397 |
| 136 | bool | 51 | Strategy Execution | Trade B-Leg setups | `true` | `execBLeg` | 398 |
| 137 | float | 2 | Strategy Execution |    ↳ Days to watch for the late retrace | `4.0` | `bLegMaxDays` | 399 |
| 138 | bool | 52 | Strategy Execution | Arm on liquidity sweep | `true` | `execArmSweep` | 402 |
| 139 | bool | 53 | Strategy Execution | Arm on RSI divergence | `false` | `execArmDiv` | 403 |
| 140 | bool | 54 | Strategy Execution | Respect divergence/extreme veto | `true` | `execRespectVeto` | 404 |
| 141 | bool | 55 | Strategy Execution | Require an FVG in the zone | `true` | `execReqFVG` | 411 |
| 142 | bool | 56 | Strategy Execution | Gap must sit fully past 0.5 | `true` | `execFvgDeepOnly` | 412 |
| 143 | bool | 57 | Strategy Execution | Floating gap → nearest fib shallower | `true` | `execDeepFib` | 413 |
| 144 | bool | 58 | Strategy Execution | Entry (least favorable): FVG must touch the 0.5 line | `false` | `execFvg50` | 414 |
| 145 | bool | 59 | Strategy Execution | Allow Sniper Zone as entry confirmation | `false` | `execConfSZ` | 415 |
| 146 | bool | 60 | Strategy Execution | Only fade HTF exhaustion, not breakouts | `false` | `execHtfExhaustOnly` | 418 |
| 147 | string | 37 | Strategy Execution |    ↳ HTF exhaustion source | `"Weekly"` | `execHtfSource` | 419 |
| 148 | string | 38 | Strategy Execution | Weekly bias requirement | `"Ignore"` | `execHtfWeekly` | 420 |
| 149 | string | 39 | Strategy Execution | Daily bias requirement | `"Ignore"` | `execHtfDaily` | 421 |
| 150 | bool | 61 | Strategy Execution | No entries in the final hour (16:00-17:00 NY) | `true` | `execNoLateDay` | 422 |
| 151 | float | 3 | Strategy Execution | Risk % per trade | `10` | `execRiskPct` | 425 |
| 152 | float | 4 | Strategy Execution | Stop buffer beyond fib 1.0 (ticks) | `0.0` | `execSlBufTk` | 426 |
| 153 | float | 5 | Strategy Execution | TP1 size % | `0` | `execTp1Pct` | 429 |
| 154 | float | 6 | Strategy Execution | TP2 size % | `0` | `execTp2Pct` | 430 |
| 155 | float | 7 | Strategy Execution | Breakeven buffer (ticks) | `30` | `execBeBufTk` | 431 |
| 156 | string | 40 | Strategy Execution | Runner trail method | `"Structure + % ratchet"` | `execRunnerTrail` | 434 |
| 157 | float | 8 | Strategy Execution |    ↳ Structure trail buffer (ticks) | `20` | `execStructTrailBufTk` | 435 |
| 158 | float | 9 | Strategy Execution |    ↳ Runner ratchet step (% of price) | `0.05` | `execTrailPct` | 436 |
| 159 | string | 41 | Strategy Execution | TP2 → stop floor | `"TP1 price"` | `execTp2StopMode` | 437 |
| 160 | float | 10 | Strategy Execution | Runner trail step ($ of price) | `5.0` | `execTrailStep` | 441 |
| 161 | bool | 62 | Strategy Execution | Close on opposite SOS | `false` | `execCloseOppSOS` | 442 |
| 162 | bool | 63 | Strategy Execution | Show entry confluence label | `true` | `execShowConfLabel` | 445 |
| 163 | string | 42 | Strategy Execution |    ↳ keep labels for which results | `"All"` | `execLabelWhich` | 446 |
| 164 | float | 11 | Strategy Execution |    ↳ label distance from price (ATR) | `6` | `execLabelOff` | 447 |
| 165 | bool | 64 | Strategy Execution | Show position box (result) | `true` | `execShowPosBox` | 448 |
| 166 | bool | 65 | Strategy Execution |    ↳ Label the TP bands (TP1/TP2/TP3) | `true` | `execShowExitLines` | 449 |
| 167 | bool | 66 | Liquidity Levels | Equal Highs/Lows (EQH/EQL) | `true` | `eqShowInput` | 1773 |
| 168 | bool | 67 | Liquidity Levels |    ↳ A gap on an EQ level survives the FVG cap | `false` | `eqExemptFvg` | 1774 |
| 169 | float | 12 | Result Stats | Breakeven band (R) | `0.15` | `execBeBandR` | 4081 |
| 170 | string | 43 | Strategy Execution | Time stop | `"Before TP1 only"` | `execTimeStopMode` | 4783 |
| 171 | float | 13 | Strategy Execution |    ↳ Time stop (hours) | `8.0` | `execTimeStopHrs` | 4784 |
| 172 | bool | 68 | Diagnostic Log | Log every trade + miss to Pine Logs | `true` | `execDiagLog` | 4850 |

## mpc_bos_strategy.pine — 176 inputs

| # | type | ord | group | title | default | var | line |
|---|---|---|---|---|---|---|---|
| 1 | bool | 1 | Market Structure | Hide Everything Except Market Structure | `false` | `marketStructureOnly` | 161 |
| 2 | string | 1 | Market Structure | Structure Label Size | `"Small"` | `structLabelSize` | 162 |
| 3 | bool | 2 | Market Structure | Show External Structure | `true` | `showExternal` | 163 |
| 4 | bool | 3 | Market Structure | Show Internal Structure | `false` | `showInternal` | 164 |
| 5 | bool | 4 | Market Structure | Show Historic Internal Structure | `false` | `showHistoricalInternal` | 165 |
| 6 | bool | 5 | Market Structure | Show Swing Point Labels | `false` | `showSwingLabels` | 166 |
| 7 | bool | 6 | Fair Value Gaps | Show FVG (REQUIRED — feeds entries) | `true` | `showFVGInput` | 196 |
| 8 | bool | 7 | Fair Value Gaps | Directional FVGs Only | `false` | `fvgDirOnly` | 198 |
| 9 | color | 1 | Fair Value Gaps | Bullish FVG | `color.new(color.gray, 80)` | `fvgBullColor` | 199 |
| 10 | color | 2 | Fair Value Gaps | Bearish FVG | `color.new(color.gray, 80)` | `fvgBearColor` | 200 |
| 11 | float | 1 | Fair Value Gaps | FVG Min Gap - below 15m (% of price) | `0.0` | `fvgThreshLTF` | 219 |
| 12 | float | 2 | Fair Value Gaps | FVG Min Gap - 15m and above (% of price) | `0.04` | `fvgThreshHTF` | 220 |
| 13 | bool | 8 | Fair Value Gaps | FVG: middle bar must close past the gap (15m+) | `false` | `fvgReqCloseHTF` | 228 |
| 14 | int | 1 | Fair Value Gaps | Max Active FVGs | `8` | `fvgMaxCount` | 230 |
| 15 | bool | 9 | Fair Value Gaps | FVG: keep until broken through (not on tap) | `true` | `fvgKeepUntilBroken` | 231 |
| 16 | bool | 10 | RSI Divergence | Track RSI divergence (REQUIRED — arms setups + veto) | `true` | `showDivInput` | 246 |
| 17 | bool | 11 | RSI Divergence | Show divergence history | `true` | `showDivHistory` | 248 |
| 18 | int | 2 | RSI Divergence | RSI length | `14` | `divRsiLen` | 250 |
| 19 | int | 3 | RSI Divergence | Pivot width (bars) | `5` | `divPivotLen` | 251 |
| 20 | int | 4 | RSI Divergence | Oversold level | `25` | `divOS` | 252 |
| 21 | int | 5 | RSI Divergence | Overbought level | `75` | `divOB` | 253 |
| 22 | int | 6 | RSI Divergence | Divergence valid for (bars) | `100` | `divValidBars` | 254 |
| 23 | int | 7 | RSI Divergence | Extreme overbought | `80` | `divExtremeOB` | 258 |
| 24 | int | 8 | RSI Divergence | Extreme oversold | `20` | `divExtremeOS` | 259 |
| 25 | bool | 12 | Trading Sessions | Show Sessions | `false` | `showSessionsInput` | 265 |
| 26 | bool | 13 | Trading Sessions | Show session names | `false` | `showSessionNames` | 267 |
| 27 | bool | 14 | Trading Sessions | Show All History | `false` | `showHistoricSessions` | 268 |
| 28 | bool | 15 | FIRST_SESSION_GROUP | Show session | `true` | `showFirst` | 278 |
| 29 | string | 2 | FIRST_SESSION_GROUP | Displayed name | `"Tokyo"` | `firstSessionName` | 279 |
| 30 | session | 1 | FIRST_SESSION_GROUP | Session time | `"0900-1800"` | `firstSessionTime` | 280 |
| 31 | string | 3 | FIRST_SESSION_GROUP | Session timezone | `"Asia/Tokyo"` | `firstSessionTZ` | 281 |
| 32 | color | 3 | FIRST_SESSION_GROUP | Session color | `color.new(#FF5252, 92)` | `firstSessionColor` | 282 |
| 33 | bool | 16 | SECOND_SESSION_GROUP | Show session | `true` | `showSecond` | 285 |
| 34 | string | 4 | SECOND_SESSION_GROUP | Displayed name | `"London"` | `secondSessionName` | 286 |
| 35 | session | 2 | SECOND_SESSION_GROUP | Session time | `"0800-1700"` | `secondSessionTime` | 287 |
| 36 | string | 5 | SECOND_SESSION_GROUP | Session timezone | `"Europe/London"` | `secondSessionTZ` | 288 |
| 37 | color | 4 | SECOND_SESSION_GROUP | Session color | `color.new(#2962FF, 92)` | `secondSessionColor` | 289 |
| 38 | bool | 17 | THIRD_SESSION_GROUP | Show session | `true` | `showThird` | 292 |
| 39 | string | 6 | THIRD_SESSION_GROUP | Displayed name | `"New York"` | `thirdSessionName` | 293 |
| 40 | session | 3 | THIRD_SESSION_GROUP | Session time | `"0800-1700"` | `thirdSessionTime` | 294 |
| 41 | string | 7 | THIRD_SESSION_GROUP | Session timezone | `"America/New_York"` | `thirdSessionTZ` | 295 |
| 42 | color | 5 | THIRD_SESSION_GROUP | Session color | `color.new(#FFEB3B, 90)` | `thirdSessionColor` | 296 |
| 43 | bool | 18 | Liquidity Levels | Show All Liquidity Levels (REQUIRED — arms sweeps) | `true` | `i_showLiquidityInput` | 307 |
| 44 | bool | 19 | Liquidity Levels | Show Labels | `true` | `i_showLabels` | 309 |
| 45 | string | 8 | Liquidity Levels | Liquidity Label Size | `"Small"` | `liqLabelSize` | 310 |
| 46 | bool | 20 | Liquidity Levels | Previous Day H/L | `true` | `i_isDailyEnabled` | 317 |
| 47 | bool | 21 | Liquidity Levels | Previous Week H/L | `true` | `i_isWeeklyEnabled` | 318 |
| 48 | bool | 22 | Liquidity Levels | Sessions H/L | `true` | `i_showSessionHL` | 319 |
| 49 | bool | 23 | Liquidity Levels | Previous Week Close (PWC) | `true` | `i_showPWC` | 326 |
| 50 | bool | 24 | Liquidity Levels | H4 High/Low Sweep (SSH/BSL) | `true` | `i_showH4Sweep` | 327 |
| 51 | int | 9 | Liquidity Levels | Label Y Offset (ticks) | `300` | `i_lblOffset` | 328 |
| 52 | int | 10 | Liquidity Levels | Line Extension (bars) | `50` | `i_lineExtend` | 329 |
| 53 | bool | 25 | Internal Fib | Show Internal Fib | `false` | `showIFibInput` | 341 |
| 54 | int | 11 | Internal Fib | Line Extension (bars) | `30` | `iFibExtend` | 343 |
| 55 | color | 6 | Internal Fib | TP2 / 0.382 | `#4caf50` | `iFibo1Color` | 345 |
| 56 | string | 9 | Internal Fib |  | `"┈"` | `iFibo1Style` | 346 |
| 57 | color | 7 | Internal Fib | TP1 / 0.500 | `#4caf50` | `iFibo2Color` | 348 |
| 58 | string | 10 | Internal Fib |  | `"┈"` | `iFibo2Style` | 349 |
| 59 | color | 8 | Internal Fib | E1 / 0.618 | `#FF9800` | `iFibo3Color` | 351 |
| 60 | string | 11 | Internal Fib |  | `"┈"` | `iFibo3Style` | 352 |
| 61 | color | 9 | Internal Fib | E2 / 0.702 | `#FF9800` | `iFibo4Color` | 354 |
| 62 | string | 12 | Internal Fib |  | `"┈"` | `iFibo4Style` | 355 |
| 63 | color | 10 | Internal Fib | E3 / 0.786 | `#FF9800` | `iFibo5Color` | 357 |
| 64 | string | 13 | Internal Fib |  | `"┈"` | `iFibo5Style` | 358 |
| 65 | color | 11 | Internal Fib | E4 / 0.886 | `#FF9800` | `iFibo6Color` | 360 |
| 66 | string | 14 | Internal Fib |  | `"┈"` | `iFibo6Style` | 361 |
| 67 | color | 12 | Internal Fib | TP3 / 0.000 | `#4caf50` | `iFibo0Color` | 363 |
| 68 | string | 15 | Internal Fib |  | `"─"` | `iFibo0Style` | 364 |
| 69 | color | 13 | Internal Fib | 1.000 | `#4caf50` | `iFibo100Color` | 366 |
| 70 | string | 16 | Internal Fib |  | `"─"` | `iFibo100Style` | 367 |
| 71 | bool | 26 | External Fib | Show External Fib (REQUIRED — SL/TP/entry levels) | `true` | `showFiboInput` | 373 |
| 72 | string | 17 | External Fib | Label Style | `"TP/Entry"` | `sharedLabelMode` | 375 |
| 73 | int | 12 | External Fib | Line Extension (bars) | `80` | `fiboLineExtend` | 376 |
| 74 | bool | 27 | External Fib | TP2 / 0.382 | `true` | `isFibo1ToShow` | 378 |
| 75 | color | 14 | External Fib |  | `#4caf50` | `fibo1Color` | 380 |
| 76 | string | 18 | External Fib |  | `"┈"` | `fibo1Style` | 381 |
| 77 | bool | 28 | External Fib | TP1 / 0.500 | `true` | `isFibo2ToShow` | 383 |
| 78 | color | 15 | External Fib |  | `#4caf50` | `fibo2Color` | 385 |
| 79 | string | 19 | External Fib |  | `"┈"` | `fibo2Style` | 386 |
| 80 | bool | 29 | External Fib | E1 / 0.618 | `true` | `isFibo3ToShow` | 388 |
| 81 | color | 16 | External Fib |  | `#2196F3` | `fibo3Color` | 390 |
| 82 | string | 20 | External Fib |  | `"┈"` | `fibo3Style` | 391 |
| 83 | bool | 30 | External Fib | E2 / 0.702 | `true` | `isFibo4ToShow` | 393 |
| 84 | color | 17 | External Fib |  | `#2196F3` | `fibo4Color` | 395 |
| 85 | string | 21 | External Fib |  | `"┈"` | `fibo4Style` | 396 |
| 86 | bool | 31 | External Fib | E3 / 0.786 | `true` | `isFibo5ToShow` | 398 |
| 87 | color | 18 | External Fib |  | `#2196F3` | `fibo5Color` | 400 |
| 88 | string | 22 | External Fib |  | `"┈"` | `fibo5Style` | 401 |
| 89 | bool | 32 | External Fib | E4 / 0.886 | `true` | `isFibo6ToShow` | 403 |
| 90 | color | 19 | External Fib |  | `#2196F3` | `fibo6Color` | 405 |
| 91 | string | 23 | External Fib |  | `"┈"` | `fibo6Style` | 406 |
| 92 | bool | 33 | External Fib | 1.000 | `true` | `isFibo10ToShow` | 408 |
| 93 | color | 20 | External Fib |  | `#2196F3` | `fibo10Color` | 410 |
| 94 | string | 24 | External Fib |  | `"┈"` | `fibo10Style` | 411 |
| 95 | bool | 34 | External Fib | TP3 / 0.000 | `true` | `isFibo7ToShow` | 413 |
| 96 | color | 21 | External Fib |  | `#4caf50` | `fibo7Color` | 415 |
| 97 | string | 25 | External Fib |  | `"┈"` | `fibo7Style` | 416 |
| 98 | bool | 35 | Cycle Fib | Show Cycle Fib | `false` | `showMacroFibInput` | 425 |
| 99 | int | 13 | Cycle Fib | Line Extension (bars) | `180` | `macroLineExtend` | 427 |
| 100 | int | 14 | Cycle Fib | Draw Up To Timeframe (min) | `30` | `macroMaxTfMin` | 428 |
| 101 | bool | 36 | Cycle Fib | TP3 / 0.000 | `true` | `showMacro0` | 430 |
| 102 | color | 22 | Cycle Fib |  | `#4caf50` | `macro0Color` | 431 |
| 103 | string | 26 | Cycle Fib |  | `"─"` | `macro0Style` | 432 |
| 104 | bool | 37 | Cycle Fib | TP2 / 0.382 | `true` | `showMacro382` | 434 |
| 105 | color | 23 | Cycle Fib |  | `#4caf50` | `macro382Color` | 435 |
| 106 | string | 27 | Cycle Fib |  | `"┈"` | `macro382Style` | 436 |
| 107 | bool | 38 | Cycle Fib | TP1 / 0.500 | `true` | `showMacro50` | 438 |
| 108 | color | 24 | Cycle Fib |  | `#4caf50` | `macro50Color` | 439 |
| 109 | string | 28 | Cycle Fib |  | `"┈"` | `macro50Style` | 440 |
| 110 | bool | 39 | Cycle Fib | E1 / 0.618 | `true` | `showMacro618` | 442 |
| 111 | color | 25 | Cycle Fib |  | `#2196F3` | `macro618Color` | 443 |
| 112 | string | 29 | Cycle Fib |  | `"┈"` | `macro618Style` | 444 |
| 113 | bool | 40 | Cycle Fib | E2 / 0.702 | `true` | `showMacro702` | 446 |
| 114 | color | 26 | Cycle Fib |  | `#2196F3` | `macro702Color` | 447 |
| 115 | string | 30 | Cycle Fib |  | `"┈"` | `macro702Style` | 448 |
| 116 | bool | 41 | Cycle Fib | E3 / 0.786 | `true` | `showMacro786` | 450 |
| 117 | color | 27 | Cycle Fib |  | `#2196F3` | `macro786Color` | 451 |
| 118 | string | 31 | Cycle Fib |  | `"┈"` | `macro786Style` | 452 |
| 119 | bool | 42 | Cycle Fib | E4 / 0.886 | `true` | `showMacro886` | 454 |
| 120 | color | 28 | Cycle Fib |  | `#2196F3` | `macro886Color` | 455 |
| 121 | string | 32 | Cycle Fib |  | `"┈"` | `macro886Style` | 456 |
| 122 | bool | 43 | Cycle Fib | 1.000 | `true` | `showMacro100` | 458 |
| 123 | color | 29 | Cycle Fib |  | `#2196F3` | `macro100Color` | 459 |
| 124 | string | 33 | Cycle Fib |  | `"─"` | `macro100Style` | 460 |
| 125 | bool | 44 | Sniper Fib | Sniper Zone | `false` | `showSniperFib` | 466 |
| 126 | bool | 45 | Strategy Execution | Compute the Sniper Zone | `true` | `execConfSZ` | 473 |
| 127 | bool | 46 | Liquidity Levels | Equal Highs/Lows (EQH/EQL) | `true` | `eqShowInput` | 1797 |
| 128 | bool | 47 | Liquidity Levels |    ↳ A gap on an EQ level survives the FVG cap | `false` | `eqExemptFvg` | 1798 |
| 129 | bool | 48 | Strategy Execution | Trade longs | `true` | `execLongs` | 3405 |
| 130 | bool | 49 | Strategy Execution | Trade shorts | `true` | `execShorts` | 3406 |
| 131 | string | 34 | Strategy Execution | Which break after the shift | `"All"` | `bosWhich` | 3411 |
| 132 | float | 3 | Strategy Execution |    Break must clear the swing by (x ATR) | `0.0` | `bosMinDispAtr` | 3412 |
| 133 | float | 4 | Strategy Execution |    Break leg must be at least (x ATR) | `0.0` | `bosMinLegAtr` | 3413 |
| 134 | float | 5 | Strategy Execution |    Drop an armed break after (days) | `3.0` | `bosMaxDays` | 3414 |
| 135 | int | 15 | Strategy Execution |    Max trades between shifts | `10` | `bosMaxPerRegime` | 3415 |
| 136 | bool | 50 | Strategy Execution |    Broken level must hold | `false` | `bosReqHold` | 3416 |
| 137 | string | 35 | Strategy Execution | Measure levels on | `"Break leg"` | `bosFibAnchor` | 3425 |
| 138 | string | 36 | Strategy Execution | Shallowest the entry may rest | `"0.5"` | `bosEntryTop` | 3426 |
| 139 | bool | 51 | Strategy Execution | Price the entry off a gap | `false` | `bosUseFvg` | 3427 |
| 140 | bool | 52 | Strategy Execution |    ↳ ...and require one (no gap = no trade) | `true` | `execReqFVG` | 3428 |
| 141 | bool | 53 | Strategy Execution |    ↳ ...gap must sit fully past the shallow end | `true` | `execFvgDeepOnly` | 3429 |
| 142 | bool | 54 | Strategy Execution |    ↳ ...deep gap enters at the nearest fib | `true` | `execDeepFib` | 3430 |
| 143 | bool | 55 | Strategy Execution |    ↳ ...Sniper Zone counts as a gap | `true` | `execConfSZ2` | 3431 |
| 144 | bool | 56 | Strategy Execution |    ↳ ...gap across the shallow end enters at it | `false` | `execFvg50` | 3432 |
| 145 | string | 37 | Strategy Execution | Fallback entry level | `"0.786"` | `bosEntryFib` | 3433 |
| 146 | bool | 57 | Strategy Execution | Divergence blocks a new entry | `false` | `bosRespectVeto` | 3436 |
| 147 | bool | 58 | Strategy Execution | No entries in the final hour (16:00-18:00 NY) | `true` | `execNoLateDay` | 3437 |
| 148 | string | 38 | Strategy Execution | Weekly bias requirement | `"Ignore"` | `execHtfWeekly` | 3438 |
| 149 | string | 39 | Strategy Execution | Daily bias requirement | `"Ignore"` | `execHtfDaily` | 3439 |
| 150 | float | 6 | Strategy Execution | Risk % per trade | `10` | `execRiskPct` | 3442 |
| 151 | string | 40 | Strategy Execution | Stop model | `"ATR"` | `bosSlModel` | 3443 |
| 152 | float | 7 | Strategy Execution |    ↳ ATR multiple | `1.3` | `bosSlAtr` | 3444 |
| 153 | float | 8 | Strategy Execution | Extra room beyond the stop (ticks) | `0.0` | `execSlBufTk` | 3445 |
| 154 | string | 41 | Strategy Execution | Minimum stop distance | `"% of price"` | `execMinStopMode` | 3446 |
| 155 | float | 9 | Strategy Execution |    ↳ Minimum stop floor (unit = mode above) | `0.10` | `execMinStopVal` | 3447 |
| 156 | string | 42 | Strategy Execution | Moving stop (trails from entry) | `"Off"` | `execMoveStop` | 3448 |
| 157 | float | 10 | Strategy Execution |    ↳ trail distance (unit = mode above) | `5.0` | `execMoveStopVal` | 3449 |
| 158 | float | 11 | Strategy Execution | TP1 size % | `0` | `execTp1Pct` | 3452 |
| 159 | float | 12 | Strategy Execution | TP2 size % | `0` | `execTp2Pct` | 3453 |
| 160 | float | 13 | Strategy Execution | TP3 size % | `100` | `execTp3Pct` | 3454 |
| 161 | bool | 59 | Strategy Execution | TP3 = measured move | `false` | `bosTp3Measured` | 3455 |
| 162 | float | 14 | Strategy Execution | Breakeven buffer (ticks) | `30` | `execBeBufTk` | 3456 |
| 163 | string | 43 | Strategy Execution | Runner trail method | `"Structure (swing)"` | `execRunnerTrail` | 3459 |
| 164 | float | 15 | Strategy Execution |    ↳ Structure trail buffer (ticks) | `20` | `execStructTrailBufTk` | 3460 |
| 165 | float | 16 | Strategy Execution | Runner trail step ($ of price) | `5.0` | `execTrailStep` | 3461 |
| 166 | string | 44 | Strategy Execution | TP2 → stop floor | `"TP1 price"` | `execTp2StopMode` | 3462 |
| 167 | bool | 60 | Strategy Execution | Close an open trade on opposing divergence | `false` | `bosCloseOppDiv` | 3463 |
| 168 | bool | 61 | Strategy Execution | Show entry label | `false` | `execShowConfLabel` | 3466 |
| 169 | string | 45 | Strategy Execution |    ↳ keep labels for which results | `"All"` | `execLabelWhich` | 3467 |
| 170 | float | 17 | Strategy Execution |    ↳ label distance from price (ATR) | `6` | `execLabelOff` | 3468 |
| 171 | bool | 62 | Strategy Execution | Show position box (result) | `false` | `execShowPosBox` | 3469 |
| 172 | bool | 63 | Strategy Execution |    ↳ Label the TP bands (TP1/TP2/TP3) | `false` | `execShowExitLines` | 3470 |
| 173 | bool | 64 | Strategy Execution | Mark blocked trades (pink) | `false` | `showBlockTag` | 3471 |
| 174 | string | 46 | Strategy Execution | Session VWAP filter | `"Trend's side"` | `bosVwapReq` | 3479 |
| 175 | float | 18 | Result Stats | Breakeven band (R) | `0.15` | `execBeBandR` | 3482 |
| 176 | bool | 65 | Diagnostic Log | Write a text log of every trade | `true` | `execDiagLog` | 4358 |

## mpc_d_strategy.pine — 49 inputs

| # | type | ord | group | title | default | var | line |
|---|---|---|---|---|---|---|---|
| 1 | string | 1 | Market Structure | Structure Label Size | `"Small"` | `structLabelSize` | 86 |
| 2 | bool | 1 | Market Structure | Show External Structure | `true` | `showExternal` | 87 |
| 3 | bool | 2 | Market Structure | Show Swing Point Labels | `true` | `showSwingLabels` | 88 |
| 4 | int | 1 | D Setup | Trend must have printed at least N BOS | `1` | `dTrendBosMin` | 647 |
| 5 | int | 2 | D Setup | Shakeout may print at most N BOS | `1` | `dCtrBosMax` | 650 |
| 6 | int | 3 | D Setup | Shakeout max length (bars) | `133` | `dCtrBarsMax` | 653 |
| 7 | bool | 3 | Strategy Execution | Trade longs | `true` | `execLongs` | 664 |
| 8 | bool | 4 | Strategy Execution | Trade shorts | `true` | `execShorts` | 665 |
| 9 | string | 2 | Strategy Execution | Entry | `"VWAP side"` | `execEntryMode` | 667 |
| 10 | float | 1 | Strategy Execution |    ↳ Retrace level | `0.5` | `execRetraceFib` | 668 |
| 11 | int | 4 | Strategy Execution |    ↳ Cancel an unfilled limit after N bars | `20` | `execLimitBars` | 669 |
| 12 | string | 3 | Strategy Execution | Stop anchor | `"Sweep extreme"` | `execSlMode` | 685 |
| 13 | float | 2 | Strategy Execution |    ↳ Stop percent | `50` | `execSlPct` | 686 |
| 14 | float | 3 | Strategy Execution | Stop buffer beyond the anchor (ticks) | `0` | `execSlBufTk` | 687 |
| 15 | string | 4 | Strategy Execution | Minimum stop distance | `"% of price"` | `execMinStopMode` | 695 |
| 16 | float | 4 | Strategy Execution |    ↳ Minimum stop floor (unit = mode above) | `0.08` | `execMinStopVal` | 696 |
| 17 | string | 5 | Strategy Execution | Position sizing | `"Risk % of equity"` | `execSizeMode` | 698 |
| 18 | float | 5 | Strategy Execution |    ↳ Risk % per trade | `1.0` | `execRiskPct` | 699 |
| 19 | float | 6 | Strategy Execution |    ↳ Contracts | `1.0` | `execFixedQty` | 700 |
| 20 | float | 7 | Strategy Execution | TP1 distance (R) | `1.0` | `execTp1R` | 702 |
| 21 | float | 8 | Strategy Execution | TP2 distance (R) | `2.0` | `execTp2R` | 703 |
| 22 | float | 9 | Strategy Execution | TP3 distance (R) | `0` | `execTp3R` | 704 |
| 23 | float | 10 | Strategy Execution |    ↳ TP1 size % | `0` | `execTp1Pct` | 718 |
| 24 | float | 11 | Strategy Execution |    ↳ TP2 size % | `0` | `execTp2Pct` | 719 |
| 25 | float | 12 | Strategy Execution | Breakeven buffer (ticks) | `30` | `execBeBufTk` | 720 |
| 26 | string | 6 | Strategy Execution | TP2 → stop floor | `"TP1 price"` | `execTp2StopMode` | 721 |
| 27 | string | 7 | Strategy Execution | Runner trail method | `"Structure + % ratchet"` | `execRunnerTrail` | 729 |
| 28 | float | 13 | Strategy Execution |    ↳ Structure trail buffer (ticks) | `20` | `execStructTrailBufTk` | 730 |
| 29 | float | 14 | Strategy Execution |    ↳ Runner ratchet step (% of price) | `1.0` | `execTrailPct` | 731 |
| 30 | float | 15 | Strategy Execution | Runner trail step ($ of price) | `5.0` | `execTrailStep` | 732 |
| 31 | bool | 5 | Strategy Execution | Close on opposite SOS | `false` | `execCloseOppSOS` | 734 |
| 32 | string | 8 | Strategy Execution | Time stop | `"Before TP1 only"` | `execTimeStopMode` | 735 |
| 33 | float | 16 | Strategy Execution |    ↳ Time stop (hours) | `36.0` | `execTimeStopHrs` | 736 |
| 34 | bool | 6 | Strategy Execution | Show entry callout | `true` | `execShowConfLabel` | 738 |
| 35 | string | 9 | Strategy Execution |    ↳ keep callouts for which results | `"All"` | `execLabelWhich` | 739 |
| 36 | float | 17 | Strategy Execution |    ↳ callout distance from price (ATR) | `6` | `execLabelOff` | 740 |
| 37 | bool | 7 | Strategy Execution | Show position blocks | `true` | `execShowPosBox` | 741 |
| 38 | bool | 8 | Strategy Execution |    ↳ Tag the targets when reached | `true` | `execShowExitLines` | 742 |
| 39 | bool | 9 | Strategy Execution |    ↳ Shade the shakeout | `true` | `execShowShakeout` | 743 |
| 40 | bool | 10 | D Debug | Mark blocked setups on chart (pink) | `false` | `showBlockTag` | 749 |
| 41 | int | 5 | D Debug |    ↳ only tag the last N days (0 = all) | `0` | `debugDays` | 750 |
| 42 | bool | 11 | D Debug | Show state panel | `true` | `showStatePanel` | 751 |
| 43 | float | 18 | Result Stats | Breakeven band (R) | `0.15` | `execBeBandR` | 757 |
| 44 | bool | 12 | Diagnostic Log | Log every trade + block to Pine Logs | `true` | `execDiagLog` | 763 |
| 45 | bool | 13 | Strategy Execution | Require close on the pro-trend side of VWAP | `false` | `execVwapReq` | 792 |
| 46 | bool | 14 | Strategy Execution |    ↳ and VWAP itself sloping with the trend | `false` | `execVwapSlope` | 793 |
| 47 | int | 6 | Strategy Execution |    ↳ slope measured over N bars | `4` | `execVwapSlopeBars` | 794 |
| 48 | bool | 15 | Strategy Execution | Draw the VWAP line | `true` | `execShowVwap` | 799 |
| 49 | bool | 16 | Strategy Execution |    ↳ VWAP side: require the RECLAIM, not just the side | `true` | `execVwapReclaim` | 822 |

## mpc_h4_sweep_strategy.pine — 47 inputs

| # | type | ord | group | title | default | var | line |
|---|---|---|---|---|---|---|---|
| 1 | timeframe | 1 | 1 · The sequence | Liquidity timeframe | `"240"` | `tfLiq` | 175 |
| 2 | timeframe | 2 | 1 · The sequence | Confirmation timeframe | `"15"` | `tfConf` | 176 |
| 3 | bool | 1 | 1 · The sequence | Require an H4 sweep first | `true` | `reqSweep` | 189 |
| 4 | bool | 2 | 1 · The sequence | Enter on the confirmation close (skip the trigger line) | `false` | `entryAtConf` | 190 |
| 5 | bool | 3 | 1 · The sequence | Read the confirmation bar as it closes (no 1-bar delay) | `false` | `confLive` | 191 |
| 6 | bool | 4 | 1 · The sequence | Invert (trade the opposite direction) | `false` | `invertTrade` | 192 |
| 7 | float | 1 | 2 · Confirmation candles | Doji size | `0.05` | `dojiSize` | 205 |
| 8 | bool | 5 | 2 · Confirmation candles | SELL · Sweep + Engulf | `true` | `patBearSwpEng` | 207 |
| 9 | bool | 6 | 2 · Confirmation candles | SELL · Bearish Harami | `true` | `patBearHarami` | 208 |
| 10 | bool | 7 | 2 · Confirmation candles | SELL · Bearish Engulfing | `true` | `patBearEng` | 209 |
| 11 | bool | 8 | 2 · Confirmation candles | SELL · Inverted Hammer (upper wick) | `true` | `patInvHammer` | 210 |
| 12 | bool | 9 | 2 · Confirmation candles | SELL · Doji | `true` | `patBearDoji` | 211 |
| 13 | bool | 10 | 2 · Confirmation candles | SELL · Hanging Man (needs a gap) | `false` | `patHangingMan` | 212 |
| 14 | bool | 11 | 2 · Confirmation candles | SELL · Evening Star (needs a gap) | `false` | `patEveningStar` | 213 |
| 15 | bool | 12 | 2 · Confirmation candles | SELL · Shooting Star (needs a gap) | `false` | `patShootStar` | 214 |
| 16 | bool | 13 | 2 · Confirmation candles | SELL · Bearish Kicker (needs a gap) | `false` | `patBearKick` | 215 |
| 17 | bool | 14 | 2 · Confirmation candles | BUY · Sweep + Engulf | `true` | `patBullSwpEng` | 217 |
| 18 | bool | 15 | 2 · Confirmation candles | BUY · Bullish Harami | `true` | `patBullHarami` | 218 |
| 19 | bool | 16 | 2 · Confirmation candles | BUY · Bullish Engulfing | `true` | `patBullEng` | 219 |
| 20 | bool | 17 | 2 · Confirmation candles | BUY · Hammer (lower wick) | `true` | `patHammer` | 220 |
| 21 | bool | 18 | 2 · Confirmation candles | BUY · Doji | `true` | `patBullDoji` | 221 |
| 22 | bool | 19 | 2 · Confirmation candles | BUY · Morning Star (needs a gap) | `false` | `patMornStar` | 222 |
| 23 | bool | 20 | 2 · Confirmation candles | BUY · Piercing Line (needs a gap) | `false` | `patPiercing` | 223 |
| 24 | bool | 21 | 2 · Confirmation candles | BUY · Bullish Belt (needs a gap) | `false` | `patBullBelt` | 224 |
| 25 | bool | 22 | 2 · Confirmation candles | BUY · Bullish Kicker (needs a gap) | `false` | `patBullKick` | 225 |
| 26 | string | 1 | 3 · Risk | Position sizing | `"Risk % of equity"` | `sizeMode` | 231 |
| 27 | float | 2 | 3 · Risk |    ↳ Contracts | `1.0` | `fixedQty` | 232 |
| 28 | float | 3 | 3 · Risk |    ↳ Risk % per trade | `1.0` | `riskPct` | 233 |
| 29 | float | 4 | 3 · Risk | TP1 distance (R) | `1.0` | `tp1R` | 234 |
| 30 | float | 5 | 3 · Risk | TP1 size % | `50` | `tp1Pct` | 235 |
| 31 | float | 6 | 3 · Risk | Breakeven buffer (ticks) | `0.0` | `beBufTk` | 236 |
| 32 | float | 7 | 3 · Risk | Runner ratchet step (% of price) | `1.0` | `trailPct` | 237 |
| 33 | string | 2 | 3 · Risk | Stop placement | `"Pattern extreme"` | `slMode` | 238 |
| 34 | int | 1 | 3 · Risk |    ↳ ATR length | `14` | `atrLen` | 239 |
| 35 | float | 8 | 3 · Risk |    ↳ ATR multiplier | `1.5` | `slMult` | 240 |
| 36 | float | 9 | 3 · Risk | Stop buffer beyond the pattern (ticks) | `0.0` | `stopBufTk` | 241 |
| 37 | float | 10 | 3 · Risk | Minimum stop distance (% of price, 0 = off) | `0.0` | `minStopPct` | 242 |
| 38 | string | 3 | 4 · Filters (all off by default) | Candle before the confirmation | `"Any"` | `prevDir` | 251 |
| 39 | bool | 23 | 4 · Filters (all off by default) | Only trade with a higher-timeframe EMA | `false` | `useEma` | 252 |
| 40 | timeframe | 3 | 4 · Filters (all off by default) |    ↳ EMA timeframe | `"240"` | `emaTf` | 253 |
| 41 | int | 2 | 4 · Filters (all off by default) |    ↳ EMA length | `200` | `emaLen` | 254 |
| 42 | float | 11 | 4 · Filters (all off by default) | Cap the trigger candle (% of stop distance, 0 = off) | `0.0` | `maxTrigPct` | 255 |
| 43 | bool | 24 | 5 · Drawing | Show the liquidity levels | `true` | `showLevels` | 261 |
| 44 | bool | 25 | 5 · Drawing | Show the confirmation-close line | `true` | `showCC` | 262 |
| 45 | bool | 26 | 5 · Drawing | Label the confirmation candle | `true` | `showConfLabel` | 263 |
| 46 | bool | 27 | 5 · Drawing | Show the risk / reward boxes | `true` | `showTrade` | 264 |
| 47 | bool | 28 | 5 · Drawing | Log every trade to Pine Logs | `true` | `logTrades` | 265 |
