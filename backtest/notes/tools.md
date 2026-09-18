# Notes — Tools

Every standalone tool under backtest/tools/ and what each one found — internal-break audits, loss-recovery replays, RSO/loaded-level scans, the overlap audit, and more. Moved VERBATIM out of `backtest/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Tools

- **`tools/internal_break_audit.py`** (2026-08-23) — does an INTERNAL break against the trade
  predict a bad entry? Aaron's observation from the price chart on a losing re-entry, asked two
  ways because it is really two rules: **refuse the setup**, or **take it and leave at flat**.
  ⚠ **Committed 2026-08-24 having sat untracked for a day, and the reason is worth more than the
  tool**: it was about to be deleted as unattributable cruft because it was blocking a repo-wide
  format check, and it exists nowhere else — an untracked file has no history to recover from.
  **A tool nobody has committed is a tool one tidy-up away from never having existed.**
  ⚠ **The numbers in its docstring are its author's, not re-run here.** It was committed unchanged
  apart from formatting; whoever next trusts a figure from it runs it first.
  ⚠ **It is a STATIC RE-SCORE of one book, not a replay** (its own docstring says so at length):
  with one position slot, refusing a setup does not merely remove its R, it lets whatever queued
  behind it trade instead — the effect this repo has already MEASURED running the other way in
  Run 12. `--replay` is the honest mode; the default is the cheap one.

- **`tools/recovery_report.py`** (new 2026-08-19) — replays a strategy, then replays the
  **loss-recovery** rule over its losses and prices the addition against the only honest
  alternative: turning `exec_risk_pct` up on the strategy you already own. The rule itself lives
  in `strategies/python/loss_recovery/` and that CLAUDE.md is the one that explains it.
  🔴 **It charges costs to BOTH sides, and that is load-bearing rather than tidy** — charging the
  recovery leg alone is rule 11 broken, and it FLIPS the verdict: uncosted-primary said the risk
  dial won, costing both says the recovery wins by 1.3–1.7x. The primary holds a median 0.3 days
  and 100 of its 181 trades are SHORTS, which gold pays a swap CREDIT to hold, so it loses only
  7% of gross to costs while the recovery leg loses far more.
  ⚠ **Read the drawdown column, never the balance alone.** The rule buys RETURN, not safety —
  MEASURED, max drawdown is 48.3% at 25% size against the primary's 48.8%, and it goes UP to
  57.2% at full size. `--sweep` prints the whole size curve.
  🔴 **`--exits` and `--soft-curve` (2026-08-19) grid the EXIT rules, and three of the four
  candidates LOSE** — structural invalidation on the opposing CHoCH +16.2R → +9.7R, an early
  breakeven step → +4.2R, and splitting the lock's trigger from its destination → −2.3R at 2R→1R.
  The one that survives is `soft_stop_r`, which cuts at a fraction of R **without moving the
  distance the trade was SIZED on** — the whole point, since a nearer stop otherwise just buys a
  bigger position and costs the same money.
  ⚠ **Its curve is a PLATEAU and the tool prints it as one.** Everything from −0.25R to the
  structural stop lands between +12.9R and +18.5R against a measured run-to-run sd of 15.06R, so
  the finding is that cutting early is FREE, not that it earns more; what moves monotonically is
  the loss SIZE (−1.01R → −0.30R) bought with win rate (58% → 37%).
  ⚠ **Read `--soft-curve`'s `less top 5` column, not its ranking** — below −0.25R the rule goes
  negative once its five best trades are deleted, which is the only place the cliff is visible.
  🔴 **`--stops` (2026-08-19) answers WHERE the stop goes, and killed the strongest-sounding
  idea yet**: resting it on the LOSING trade's entry price. It is 2.4x tighter ($38.18 → $16.05
  median), so the same risk buys 2.4x the position and the trade resolves in 43 bars against 294
  — every step of the mechanism works — and net R goes **+16.2R → +1.8R** with max drawdown UP.
  The primary's entry is a price the market has just been trading around, so the stop sits in
  fresh congestion; **median MFE falls 1.01R → 0.89R, which a 2.4x smaller R should have RAISED.**
  ⚠ **That excursion column is the diagnostic, not the P&L** — it is what distinguishes "the stop
  was unlucky" from "the trades are dying before their move".
  ⚠ **A percent ratchet loses to the confirmed-swing trail on both stops**, and flatly across a
  20x range of steps: at 1% one step is $40 against a $38 median stop (inert — the `b_leg`
  trap), at 0.05% it binds constantly and hands back the runners.
  🔴 **`--search` (2026-08-19) is the stop sweep, and its best row is a trap worth knowing.**
  A stop on the CHoCH BAR's own extreme scores **+24.4R against the shipped +16.2R** on a stop 7x
  tighter with a LOWER drawdown — and **−7.4R once its five best trades are deleted**, where the
  shipped stop survives the same deletion at +2.3R. Median hold 4 bars: a different, hour-long
  rule that caught five big moves, not a better version of this one.
  ⚠ **Every stop row is scored against a structure-BLIND ATR control at a matched distance**, and
  that is what makes the table readable — the last confirmed swing scores −12.3R at almost exactly
  the same stop SIZE as the signal bar's +24.4R. **Size is not the variable; where the level came
  from is.**
  🔴 **It also settles "the +1R lock gives up the runners": the runners are not reachable.** Of the
  35 trades that lock, only **3 ever saw +2R while still open** (median MFE +1.06R), yet the median
  trade was offered **+2.33R more within 30 days of closing**. Price tags +1R, takes the stop, then
  runs — so every wider trail pays 32 trades of given-back R to catch 3, which is what the measured
  alternatives all do. **That gap is a RE-ENTRY signal, not a trailing-stop problem.**
  ⚠ Everything it prints is a LAB finding: no Pine twin, no parity gate, `enabled` defaults False.

- **`tools/recovery_smoothness.py`** (new 2026-08-19) — the companion question to the one above:
  loss recovery does not reduce MAX drawdown, so does it at least smooth the curve? **No.** Average
  drawdown 16.6% → 17.2%, median 11.4% → 12.2%, time under water 75% → 79%, longest underwater
  stretch identical at 612 days, monthly mean/std unchanged at 0.314 → 0.318.
  🔴 **It exists because max drawdown is ONE MOMENT and a single-number verdict hid the rest of the
  curve.** The equal-drawdown comparison in `recovery_report.py` is matched on the max, so it can
  read 1.53x while every broader measure is a wash — which it is.
  ⚠ **Per-trade R volatility falls 3.32R → 2.88R and that is NOT smoothing**, it is dilution from
  adding quarter-size trades; return per unit of it goes 0.215 → 0.190. Never quote a volatility
  drop without the return beside it.

- **`tools/rso_scan.py`** (new 2026-08-16) — finds RETAIL SHAKE OUT (RSO) setups and draws them.
  Drives the canonical `engines/market_structure/` rather than hand-rolled pivots: A = `bull_sos`,
  B = a wick under the level that break left behind, C = the next aggressive `bull_sos`. Shorts
  come from `invert()`, and 🟢 **the sign-symmetry that trick assumes is now CHECKED rather than
  assumed** — `--verify-mirror` counts `bear_sos` on real bars against `bull_sos` on inverted bars
  and they matched exactly (424 = 424). 🔴 **FIRST RUN, 186,759 M15 bars 2018-09-13 → 2026-08-13:
  ZERO ENTRIES, and the tool exists to have found that.** Funnel: 847 A-breaks → 16 shake outs →
  **0** real breaks. **The binding constraint is C**, which needs TWO `bull_sos` inside ~32 bars,
  against a measured density of **one SOS per 220 bars** (external 847 / internal 575 over the same
  frame — the internal stream is RARER, so the obvious fix makes it worse). ⚠ **`docs/FB_SPEC.md`
  §4.6 has to be re-specified before any RSO code is written: Aaron's own
  `indicators/engines/mss_sweeps.pine` fires on a RECLAIM — price wicks the level and closes
  back — not on a second structure break, and that one substitution is the difference between an
  indicator that signals and this scan's zero.** ⚠ **A trigger that never fires has not been
  measured, it has been mis-specified** — do not read the zero as "RSO has no edge". ⚠ Trigger only:
  no 4H bias and no discount filter, because `run_sweep` replays a single frame. No baseline moves —
  this is a new tool and nothing consumed it before today.
- **`tools/loaded_level_study.py`** (new 2026-09-14) — the Loaded Level setup as the user's OWN
  trades define it (Examples 3–9 in `docs/DAVINCI_MODEL_SPEC.md`), detected on the canonical
  structure, liquidity and equal-highs engines, replayed with ONE position slot and real costs, and
  graded over 3,888 cells: reward floor × target ("4" / nearest untaken pool / nearest named pool
  below 4) × entry (stab / reclaim) × min stop × min top-to-4 range × touches × SOS × direction.
  **It supersedes `loaded_level_scan.py` for this model** — that scanner never found the user's
  trades; this one finds all seven (`--recall-only`).
  **MEASURED 2026-09-14, PU Prime `XAUUSD.p` M5, 475,081 bars (2020-01-01 → 2026-09-11),
  `puprime_ecn`: sized like the user's trades (stop ≥ 2 ATR(50), top-to-4 ≥ 10 ATR) all 108
  floor × target × entry × direction cells LOSE net.** Best: short, stab, named target, floor 2.0 —
  1,108 trades, 26.5% win at 2.80R, −28.7R. Reclaim entry: 0 of 54 positive. The named pool past
  "4" beats "4" in every row (that same cell: −28.7R vs −69.8R) and no floor rescues it — the win
  rate falls as fast as the reward rises.
  ✅ **The structure carries real information, and too little of it.** Against random STABS of any
  lower high with the same stop and target distances, the user-sized shorts win +3.8 to +4.4
  points (z +3.1 to +3.3) — smaller than what shorting gold's 2020–26 rise costs, plus spread and swap.
  ⚠ **One family is positive in both halves and every year** — both directions, stab, named target,
  NO floor (avg R:R 0.84), loaded (2 touches), bearish SOS required, user-sized: +45.9R over 1,219
  trades (+0.038R, t +1.46, z +5.6 vs random stabs) on ECN, **+13.7R (t +0.45) on Standard**; each
  side ALONE is negative (short −11.6R, long −5.7R) and floor 1.0 is −41.6R. **A search winner —
  cost-sensitive and path-dependent. A forward-test candidate at most, never a baseline.**
  🔴 **ITS FIRST TWO GRIDS WERE CONTAMINATED BY ITS OWN CACHE, AND THE NUMBERS LOOKED FINE.** The walk
  cache was keyed on a side's POSITION in the list of sides, and a long-only run puts the long book
  at the index where "both" and "short" keep the short one — so directions read each other's cached
  trades, by grid order. Found only because one cell re-scored alone gave 1,108 trades against the
  grid's 1,089. Now keyed on the side's NAME, the owner is checked on every read, and five cells
  re-scored in reverse order with a fresh cache match the grid exactly.
  🔴 **R without a minimum stop measures the stop.** Swap is charged per LOT, so in R it scales with
  1/stop — one cents-wide long carried −408R of swap in the first grid. Min stop is a grid axis.
  🔴 **PU Prime's daily REOPEN bar can print a spike no chart shows** (22 Jul 2026: open 19.20 below
  both neighbours, through the user's target three hours before their entry). 2 of 139 reopen bars
  in 2026 do this against 2 of 49,299 others. Detection clips it; fills, stops and targets use the
  RAW bars. ⚠ Mirror symmetry was CHECKED, not assumed: on 73,294 bars every bullish/bearish
  structure count and every high/low liquidity count equals its mirror. ⚠ No Pine twin and no
  parity gate — every number is a lab finding. No documented baseline moves: nothing consumed
  this tool before today.
- **`tools/loaded_level_scalp.py`** (new 2026-09-14) — `loaded_level_study.py`'s setup as a SCALP
  on 5m / 15m / 30m / 1h (30m and 1h resampled UP from M15, time constants rescaled to mean the
  same hours), adding a halfway-to-4 target and a half-off-at-+0.5R-then-breakeven exit. It replaces
  the study's walk and target function **in its own process only**, so the study's figures cannot
  move. Four modes, in a fixed order: `explore` (bars before 2025-09-01 only), `pick` (both halves
  positive with ≥ 30 trades each → ranked by the worse half → most one-setting neighbours positive),
  `check` (random entries matched on direction, stop, target and exit; z ≥ 2), `holdout` (one cell).
  **MEASURED 2026-09-14, PU Prime `XAUUSD.p`, `puprime_ecn`:** 3,456 cells; 44 / 29 / 24 / 8 positive
  in both halves on 5m / 15m / 30m / 1h. The pick — 5m, both directions, SOS after the sweep, 2-touch
  level, stop ≥ 2 ATR, top-to-4 ≥ 10 ATR, named pool past 4, no floor — made +48.1R over 1,126 trades
  in-sample at z +2.52 against random, then **−1.5R over 222 trades on the holdout, its entries no
  better than random.** Full write-up: `docs/DAVINCI_MODEL_SPEC.md` → *Scalp sweet spot*.
  ✅ **It reproduces the scratch run that made the choice exactly** — all 864 1h cells identical in
  every column, and the pick, check and holdout figures to the printed digit.
  🔴 **The holdout is SPENT** — the docstring says so and `holdout` prints it on every run; another
  cell tested on those months is in-sample. ⚠ No Pine twin, no parity gate — lab findings. No
  documented baseline moves: it imports the study and edits nothing in it, and nothing consumed
  this tool before today.
- **`tools/rso_realign_study.py`** (new 2026-09-14) — the user's own 1-minute sequence (trend BOS →
  counter SOS → one or more counter BOS → realign SOS, stop beyond the counter push), detected on
  the canonical structure engine on 1m / 5m / 15m and walked on raw PU Prime M1 bars whatever the
  frame. 384 cells declared before any result: counter BOS × entry (realign close / fib 0.5 limit /
  0.382 pullback then a next-frame-up close / half and half) × stop (structure / 2 × ATR) × 8 exits
  including breakeven and two trails. `--recall` finds the user's trades; `--holdout` runs ONE cell.
  **MEASURED 2026-09-14, PU Prime `XAUUSD.p` M1, 2,371,706 bars (2020-01-01 → 2026-09-11),
  `puprime_ecn`: the user's rule on 1m loses in every exit (−0.002 to −0.082 R a trade); on 15m it
  makes +0.04 to +0.13 R a trade but random entries at the same month and hour make the same.** The
  pick, 15m c2+ fib50 atr2 t3 (122 trades, +61.9R, z +3.31, a ridge on three settings), then made
  **−5.5R over 14 trades on its one holdout run, 2018-09-14 → 2019-12-31, z −0.65 — abandoned.**
  Recall 4 of 5 on 1m within 0–10 minutes; the fifth is not a 1m realign. `--sl` (added after the
  results, exploration only) tests the user's "$$" structural-liquidity ENTRY — a limit back at the
  counter push's high, stop past the lower high before it: **0 of 96 cells qualify, and on 1m it
  loses in all 16 of the user's rows.** Full write-up:
  `docs/RSO_REALIGN_SPEC.md`. 🔴 **Its holdout is SPENT for this pattern.** ⚠ That is the SAME
  window `structure_patterns.py` reserves as its test set (below) — its entries were not tested, but
  the window is no longer untouched for structure-sequence ideas. ⚠ No Pine twin, no parity gate —
  lab findings. No documented baseline moves: it imports four helpers from `loaded_level_study.py`
  and edits nothing there, and nothing consumed this tool before today.
- **`tools/structure_patterns.py`** (new 2026-09-14) — asks whether ANY specific market-structure
  event sequence on gold has an edge that survives a correction for how many were tried. Twelve
  tokens from the canonical structure and liquidity engines only (swing labels, external BOS/CHoCH,
  internal breaks, named-level sweeps), each stamped at its confirmation bar; every 2- and 3-token
  sequence, long and short, 1R and 2R, under ONE trade rule (stop past the last swing ± 0.25 ATR,
  1–8 ATR wide, 48-hour time exit, the study's walk and ECN costs). Gates fixed before any result:
  ≥ 25 trades and positive in each half; beat the 95th percentile of the best t from 200
  random-entry re-runs of the WHOLE search (the luck bar); beat matched random entries at z ≥ 2.
  **MEASURED 2026-09-14, PU Prime `XAUUSD.p` M5, 2020-01-01 → 2025-08-31 (401,787 bars),
  `puprime_ecn`: 1,424 strategies, 38 pass the sample gate, 0 beat the luck bar (t > 3.29; a random
  search's best has median t +2.35).** The best real one — a named low taken, then an internal
  bullish break, long, 1R: 325 trades, +0.135R, t 2.48 — sits at the null's 63rd percentile and
  falls to t 0.58 when same-bar events are ordered the other way. Random searches pass the sample
  gate as often as the real one (median 37 against 38). The top 5 do not carry to 15m or 1h.
  ✅ Its fast walk matches the study's on all 18,274 real walks; 8 trades priced through the study's
  own simulation give identical net R; its control reproduces the study's to six decimals; the
  seeded run reproduced byte-for-byte when re-run by a second session (~15 s).
  🔴 **Its test set — gold 2018-09-14 → 2019-12-31 — is UNSPENT, because nothing earned it.** The
  `test` mode has never been run; run it once, only on a strategy that passes all three gates.
  ⚠ **`rso_realign_study.py` ran ONE holdout on that same window the same day** (a 15m realign pick
  — it lost). None of this tool's strategies was tested there, but the window has now been looked at
  for a structure-sequence idea; say so beside any result it produces.
  ⚠ Same-bar token order moves results (only 4 of the top 20 survive reversing it) — a pattern
  that depends on it is an ordering artefact, not a finding. ⚠ Tuning the best pattern with a
  filter, stop or target is a NEW search and needs its own luck bar. ⚠ No Pine twin, no parity
  gate — lab findings. No documented baseline moves: new standalone tool, nothing edited.
- **`tools/killzone_study.py`** (new 2026-09-15) — asks whether gold's three MPC-JARVIS kill
  zones (10:00–10:59, 11:45–12:14, 13:00–13:30 New York, read off `engines/sessions/` and checked
  against every bar) carry a tradeable edge once the rules tried AND the time of day are paid for.
  The user's claim was "the market always reverses or continues around those times" — that is every
  outcome there is, so the test is whether the move INTO a zone is faded or followed better than at
  any other clock. Part 1 describes each zone against every other clock of its length (busy =
  range / ATR, follow% = same sign as the prior 60 minutes, turn% = the New York session's high or
  low prints inside). Part 2 is 648 rules declared before any result: 3 zones × fade / follow /
  sweep-and-close-back / break × lookback 30 / 60 / 120 × size 0 / 0.5 / 1 ATR × stop 0.5 / 1
  ATR(14, 1-hour) × 1R / 2R / no target, out after 120 M1 bars, the studies' walk and ECN costs.
  Gates: both halves positive with ≥ 25 trades each; beat the 95th percentile of the best t from
  200 re-runs with every zone moved to a random clock (the luck bar); beat 95% of clocks for that
  same rule.
  **MEASURED 2026-09-15, PU Prime `XAUUSD.p` M1, 2,005,828 bars 2020-01-01 → 2025-08-31,
  `puprime_ecn`: 0 rules pass. 42 of 648 pass the sample gate (random clocks: median 29); the best
  real t is +1.84 against a luck bar of +2.57 — 41% of random-clock runs beat it.** Part 1: the
  prior hour does not predict any zone's direction (follow% 48.7 / 50.0 / 49.0; other clocks
  41–54). The 10:00 zone is busy (range 1.74 ATR, 87th percentile) and holds the New York session's
  high or low on 27.9% of days (a typical hour 11.4%) — but 08:00–09:25 starts beat it on both
  (2.1 ATR; the 08:00 hour 60.5%). 11:45 and 13:00 are ordinary on all three. Across the rulebook
  the 10:00 clock is better than usual (40 of 216 rules beat 95% of clocks; a random clock scores
  8, its 95th percentile 35), but no single rule is strong enough; 11:45 and 13:00 score 3 each.
  The best rule (10:00, follow the last 30 minutes' move if ≥ 0.5 ATR, stop 0.5 ATR, no target:
  777 trades, +0.146R net) is longs (+96.9R against +16.6R short) in 2022–23; 2021 and 2024 lose,
  and the same rule at 08:30 does better (t +2.35).
  ✅ SessionEngine's zones match the tool's minute windows on all 2,005,828 bars; `FastWalk`
  matches `Book.walk` on all 252,654 real walks; one trade hand-traced (2020-01-02 short, −1.016R
  net). Seeded, ~20 s.
  🔴 **The test set (2018-09-14 → 2019-12-31) is UNSPENT for kill-zone rules — nothing earned it.**
  ⚠ More rules, filters or other clocks is a NEW search and needs its own luck bar. ⚠ No Pine twin,
  no parity gate — lab findings. No documented baseline moves: new standalone tool; it imports
  helpers from `loaded_level_study.py` and `structure_patterns.py` and edits nothing there.
  ⚠ **It was built without checking for prior art, and there was some**: `killzone_profile.py` and
  `killzone_sweep.py` (2026-08-04, further down) had already found no clock or level edge at 10:00.
  This one agrees, and adds real costs, the other two zones, sweep and break entries, and a
  random-clock luck bar. Search this file before building the next study.
  ⚠ **Five more kill-zone tools landed the SAME DAY from the other machine and were pulled in on
  2026-09-16** — `killzone_reversal.py`, `killzone_features.py`, `killzone_edge_search.py`,
  `killzone_followups.py`, `killzone_vwap_retest.py`, all further down. **Two independent searches,
  one answer**: the turn at 10:00 is real and is not a kill-zone property (their all-window control
  ranks it sixth of 23 and the whole 07:30-10:30 block beats it — this tool's 08:00-09:25 finding
  from the other side), and ~340 more pre-registered tests there find nothing that knows the
  direction. Neither search moves the other's numbers; they were run on the same broker feed from
  different code. ⚠ **That makes the clock question ANSWERED, not open** — a third kill-zone search
  on 2020-2025 would be the same data for the third time.
- **`tools/ny_open_scalp_study.py`** (new 2026-09-15) — a New York-morning scalping search on the
  MPC-JARVIS indicator's own levels: the 09:30–09:35 opening range (`engines/sessions/`), the
  08:00–09:30 pre-open range and the session VWAP (`engines/vwap/`), each traded as a break, a
  break-and-retest or a failed break, with and without a VWAP-side filter. 84 rules declared first
  (14 entries × 0.5 / 1 ATR(14, 1-hour) stop × 1R / 2R / no target, out after 60 M1 bars), the
  kill-zone study's walk and ECN costs. Gates: both halves positive; a luck bar that moves every
  trade to a random bar inside its own rule's window (200 runs); matched random entries at z ≥ 2.
  **MEASURED 2026-09-15, PU Prime `XAUUSD.p` M1, 2020-01-01 → 2025-08-31: 0 rules pass all three.**
  The best — fade a failed opening-range break when VWAP sits on the fade side, 0.5 ATR stop, no
  target: 529 trades, +0.203R net, t +2.25, every year positive — sat under the luck bar (+2.45;
  9.5% of random runs beat it), and its ten best trades made 84% of its profit. As a FAMILY it
  looked real — 26 rules through gate 1 against a maximum of 14 in 200 random runs — and trades on
  VWAP's side beat trades against it by +0.179R (z +2.57, clustered by day).
  🔴 **Both leads FAILED on the test set, 2018-09-14 → 2019-12-31, spent ONCE on a plan written
  into the tool before any test bar was loaded:** the VWAP-side difference REVERSED (−0.121R,
  z −0.95 — an explore-sized real effect lands that far the wrong way about 1 time in 100) and the
  best rule lost −22.5R over 125 trades (t −1.30). The set was spent without a gate survivor
  because the family result was the strongest lead any study here had produced; the plan states
  the power beforehand (a real effect would have shown z ~1.2), so read it as a screen that
  returned a clear no. ✅ SessionEngine's opening range equals the grid's on all 1,462 usable days;
  `FastWalk` matches `Book.walk` on all 70,164 real walks; the seeded run reproduced exactly.
  ⚠ **`killzone_vwap_retest.py` (further down, pulled in 2026-09-16) asked the VWAP half of this
  question inside the kill zones and got the same answer** — the bounce off VWAP is a coin flip
  (50.7% at equal stop and target in the 10:00 zone against an all-day median near 47%), and its
  one lift, higher-timeframe trend agreement, falls apart out of sample. This tool's VWAP-side
  effect reversed on the test set. **Two tools, two windows, no VWAP edge.**
  🔴 **The test set is SPENT for opening-range, pre-open-range and VWAP-side ideas.** ⚠ No Pine
  twin, no parity gate — lab findings. No documented baseline moves: new standalone tool.
- **`tools/bot_confluence_study.py`** (new 2026-09-15) — would a kill-zone, 08:00–09:30, VWAP-side
  or opening-range filter have improved the two LIVE bots? Replays `sos_fade_demo` (M15 + its M5
  re-entry feed) and `extreme_leg_demo` (M5) with their live instance configs through
  `build_strategy`, PU Prime bars with the server pinned (no MT5 needed) and `puprime_ecn` costs.
  11 filters per bot declared first; gates: the removed trades lose in both halves, then a
  5,000-shuffle luck bar.
  **MEASURED 2026-09-15, 2020-01-01 → 2025-08-31: no filter passes even the first gate — every
  window and both VWAP sides hold net-winning trades for both bots, so cutting any of them loses
  money.** SOS Fade 203 trades / +178.5R; extreme leg 97 / +38.1R. ⚠ **A VWAP-side filter would
  gut SOS Fade**: 189 of its 203 trades enter against VWAP, and those made +171.3R — the scalp
  study's VWAP effect does not transfer to a fade bot.
  The one lead was a SIZING idea found by looking: SOS Fade trades entered 08:00–10:59 NY averaged
  +1.85R (71) against +0.36R (132), z +1.64. 🔴 **It failed its one test-set check** (declared
  first as C3): on 2018-09-14 → 2019-12-31 the morning trades made −0.74R each (10) against −0.33R
  (17). ⚠ **On that window the live SOS Fade config LOST −13.0R over 27 trades** (M15/M5 rebuilt
  from M1 — identical to the broker's own on all 535,720 bars checked in 2020–25 — ECN costs).
  Not new: 2018 is one of its two documented losing years (`sos_fade_optimization.md`).
  ✅ The replays land near the documented figures — 246 / +232.1R against 244 / +248.6R for SOS
  Fade, 115 / +53.6R against 113 / +58.5R for the extreme leg — not exactly, because the documented
  runs used other windows or cost settings. No documented baseline moves: a standalone tool that
  changes neither bot.
- **`tools/loaded_level_scan.py`** (new 2026-08-13) — counts the LOADED LEVEL / "Da Vinci" setup
  (`docs/DAVINCI_MODEL_SPEC.md`, extracted from 16 Inter Equity Trading videos into
  `education/learned/`) and scores it against a matched random control. A level is *loaded* when
  price returned to it, respected it and moved away; the entry is the sweep of that level, the stop
  sits past an already-swept "empty" level, the target is the opposing pool. **MEASURED 2026-08-13
  on XAUUSD M15, 186,759 bars (2018-09-13 → 2026-08-13): long 49 trades, 34.7% vs a matched random
  22.9% — +11.8 points, z +1.96, +0.751R/trade (+0.633R net of spread). Short 80 trades, 21.2% vs
  20.9% — z +0.09 and −0.137R net of spread.** Funnel across both sides: armed 2,198 → loaded 2,151
  → inducement 1,879 → target built 1,444 → 129 entries; the three biggest drop causes are `rr below
  floor` 819, `block broken` 717, `expired` 531, and they are instrumented rather than inferred.
  ⚠ **`--away-mult` (added 2026-08-18) is the "and MOVES AWAY" half of the loaded rule, which the
  first cut silently dropped** — ATR(50) × this that price must TRAVEL from a level before it counts
  as loaded. **It DEFAULTS TO 0.0 and is provably inert there**: `need` is zero and both tests
  reduce to `max(highs) − low ≥ 0` and `high − min(lows) ≥ 0`, which always hold — so the shipped
  baseline above reproduces exactly and nothing in this entry moves. **It is a knob to SWEEP, not a
  value to ship**: raising it tightens what counts as loaded and every number here would have to be
  re-measured at the new setting. Same reasoning as an unmeasured cost tier — a plausible default is
  a hardcode with better manners.
  ⚠ The setup DIAGRAM renderer is now direction-aware. It drew a short with the long layout, which
  put "LOADED LOW" on a high and stacked four markers on one line — **the same class of error
  `invert()` exists to prevent one level up, and silent both times.** Right-edge labels are also
  stacked apart on purpose: entry, block and stop are a tight cluster BY CONSTRUCTION (the model
  puts the stop just past the block), and an unreadable label is the same as no label.
  🔴 **Two defects were found and fixed the day it was measured, and both are this repo's own
  standing rules restating themselves.** `Setup.dir` was documented as `"long" | "short"` and
  `dir="short"` was constructed **nowhere** — a declared field that was never assigned (root rule
  10), so the tool was long-only while reporting both sides. The short side now comes from
  `invert()`, which negates prices and swaps high/low so the *same* long code detects shorts, rather
  than from a hand-written bearish branch where a sign error is invisible; `unmirror()` maps the
  setup back. And it had **no control at all** — on an instrument that went 1,200 → 4,300 any
  long-biased rule looks profitable, so `control()` matches direction, stop distance and target
  distance and prints a z-score beside every row. The long baseline reproduced exactly after both
  fixes. ⚠ **The z-score peaks at `min_rr = 2.0`, which is the tool's own pre-existing default**
  (1.0 → +1.3 points z +0.29, i.e. NO edge; 1.5 → z +0.77; 2.0 → z +1.96; 2.5 → z +1.64; 3.0 → z
  +1.02). A peak sitting exactly on the shipped default is a selection-effect candidate and stays
  suspect until a walk-forward separates the two. ⚠ **H1 (n=13) and H4 (n=3) are too thin to
  score**, which is awkward — the source videos teach the model on H4/H1 and above, so the only
  frame with a usable sample is the one the author uses least. ⚠ **No parity gate and no Pine twin.
  Every number here is a lab finding.**
- **`tools/session_relay_scan.py`** + **`tools/sweep_confluence.py`** (new 2026-08-08) — the session
  relay playbook (London sweeps Asia's low, NY sweeps London's, then structure flips back) and the
  broader question underneath it: does a liquidity sweep carry a directional bias at all, and do
  session + daily sweeps landing together carry more? Both compose `market_structure/`, `liquidity/`
  and `sessions/`; neither invents an engine. ⚠ **`session_relay_scan.py` deliberately produces no
  entry, stop or R** — it answers "how many are there", and a P&L number there would smuggle in a
  dozen decisions nobody has made. `sweep_confluence.py` does take the crudest tradeable framing
  (enter at the sweep bar's close, stop past the swept extreme, fixed-multiple target, a bar holding
  both books the stop) **and prints a non-sweep `control` row in the same table** — every bucket is
  read against that row, never on its own.
- **`tools/internal_realign_scan.py`** (new 2026-08-13) — counts the INTERNAL REALIGNMENT setup in
  history and scores its geometry against a matched random control. A bullish 15m external trend is
  broken by a bearish SOS (a false break / structural liquidity grab); on a lower frame the internal
  structure turns counter and back with-trend to realign, and the scan asks how often that happens
  and whether the realignment carries information. Both directions. Feeds
  `strategies/python/realign/` and `docs/REALIGN_SPEC.md`.
  🔴 **ITS SHORT-SIDE RESULT WAS WRONG IN SIGN, AND THAT IS THE STANDING WARNING ON THIS TOOL.** It
  reported the internal-events stream at **+9.6% over control (+2.1σ)** for shorts — its strongest
  row — and a real replay through the exit ladder gives **−13.26R against +20.22R** on the other
  stream. The scan is not broken: it scores every setup **independently, at a FIXED target, with no
  exit ladder, no staged stop and no position slot**, and that short edge lived entirely in the tail
  (+0.1σ at 1R, +2.1σ at 4R). The real ladder banks at the structural target and stages the stop to
  breakeven long before 4R, so **the edge it measured is one the strategy never collects.**
  ⚠ **Take COUNTS from this tool; take the direction of anything exit-sensitive from a REPLAY.** A
  trigger prior is not a strategy result, and disagreeing in SIGN is the one disagreement that no
  amount of care about magnitude protects you from.
  🔴 **It prefers resampling from contiguous M1 over a cached lower frame, and the reason generalises
  to every streaming-engine tool here.** The M5 cache held 26,886 bars over 3.5 years; feeding a
  streaming state machine across holes that size silently builds structure over bars that never
  traded, and the frame comes back clean. `_gap_report` prints the density so the hole is visible
  rather than inferred.
  ⚠ **Two of its filters were VACUOUS on their first attempt and each failed in the reassuring
  direction.** A lookback slice rejected every `bear_sos` by its own twin `bear_bos` (a CHoCH bar
  raises both), reporting **ZERO occurrences** — indistinguishable from "the setup never happens";
  and a forward "did it reclaim" scan stopped only on `bear_sos`, so it walked through entire
  downtrends until some bull break appeared and returned **101/101**. Both are now bounded so that
  each outcome is reachable. **A pattern counter that returns 0 or 100% is reporting on its own
  bounds, not on the market.**
  🔴 **ITS PATTERN RANKING ALSO FAILED TO SURVIVE A REPLAY — THE SECOND FAILURE, AND THE ONE THAT
  MAKES THIS A PROPERTY OF THE TOOL RATHER THAN A ONE-OFF.** It ranks the strict three-step sequence
  LAST of three, and a replay over the same history puts it **FIRST on average R, profit factor and
  drawdown simultaneously** on a free book — it only falls behind once costs are charged. So the
  tool has now been overturned once in SIGN (the short trigger stream) and once in ORDER. **What it
  measures is TRIGGER quality; what a strategy is ranked on is what its exits bank. Do not choose a
  default from this tool.** Tables: `strategies/python/realign/CLAUDE.md` → *The pattern rule*.
  `internal_realign_scan.py --pattern any|opposing|strict --frame 5` · defaults to `strict`, the
  sequence that was DRAWN.
- **`tools/scratch_audit.py`** + **`tools/swap_audit.py`** (new 2026-08-11) — is a "breakeven" exit
  actually breakeven on a real account, and what does overnight swap cost. Written for Aaron's
  theory that `exec_be_buf_tk` (30 ticks = $0.30) cannot cover a $0.32 spread; full record in
  `strategies/python/sos_fade/sos_fade_optimization.md` → **Run 17**.
  ⚠ **A scratch is classified on the PRICE MOVE, never on the money, and that is the whole design.**
  Sorting the cohort by profit would put every negative scratch in the loss bucket and return "all
  scratches are positive" by construction. The cohort has to be defined by what the strategy DID and
  then measured on what it got.
  🔴 **`Trade.costs_usd` does NOT contain the spread under `bid_ask_fills`** — that model moves the
  FILL PRICES rather than charging a fee, so its effect is already inside `entry_price` /
  `exit_price` and appears in no cost field. Reading `costs_usd` alone would report a scratch as
  free. The two are printed separately for that reason.
  ⚠ **`swap_audit.py` runs on `puprime_standard` deliberately**: $0.00 commission and 0 bar-mode
  slippage make `costs_usd` **pure swap** with nothing to disentangle, and the swap is identical on
  all three PU Prime tiers (measured 2026-08-08), so nothing is lost by reading it off that one.
  ⚠ **Its "ceiling on a stop ratchet" figure is an UPPER BOUND and says so in its own output** —
  moving a stop changes when it triggers, and this repo has two records of that arithmetic getting
  the SIGN wrong (`bos_sweep.py`, the minimum-stop guard). If the number is small, do not build the
  thing; if it is large, replay it.

  ✅ **THE FOURTH READING OF THIS SYMBOL'S OVERNIGHT FINANCING LANDED 2026-09-02, AND IT IS NOISE —
  MEASURED BOTH WAYS RATHER THAN ARGUED.** The live terminal read **-80.54 long / +32.67 short**
  against the **-79.60 / +30.25** this module has held since 2026-08-06 (1.2% and 8.0% adrift).
  Replayed on 157,004 M15 bars of PU Prime `XAUUSD.p` (2020-01-01 → 2026-08-23, `puprime_standard`,
  the same 156 trades either way): **+125.79R on the stale number, +125.89R on the live one — a
  +0.09R difference, against this strategy's own run-to-run spread of sd 15.06R.** The entire
  overnight bill is **5.97R of +125.79R net**, so an 8% move on one side of it cannot reach a
  conclusion.
  ✅ **THE NUMBER WAS DELIBERATELY NOT UPDATED (2026-09-02).** Re-pricing re-bases every figure this
  repo has published on a charged book, and rule 11 says a comparison carries forward everything
  that decides what it was measured on — **paying that for a 0.09R correction buys an inconsistency,
  not accuracy.** Update it when a reading moves something, and re-run the two-way replay to say so.
  ✅ **THE MONITORING LANDED 2026-09-03 AND THIS LINE STILL SAID IT HAD NOT.** `SYS_BROKERCOSTS`
  (`algos/tools/watch_broker_costs.py`, daily 06:40 UTC) reads the rate off the live terminal and
  reports on Telegram when the broker MOVES it; it changes nothing here, by design. 🔴 **WHAT IS
  STILL OPEN IS THIS NUMBER, NOT THE MONITORING — and the two are not the same job.** A watcher
  tells you the broker moved; re-pricing the lab's constant re-bases every charged figure the repo
  has published, and that stays a deliberate decision. ⚠ **A drift is no longer silent, so the
  reason this number lags is now a CHOICE rather than a blind spot** — say which one you mean.
  ⚠ **Before the watcher, a move large enough to matter arrived exactly as silently as this one
  did, and the four readings are why it was built** — **−78.29 (2026-07-16), −79.60 (2026-08-06),
  −81.18 (2026-08-14), −80.54 (2026-09-02)**, four in seven weeks, every one found by somebody who
  happened to look. A broker re-quotes swaps whenever it likes; this module still cannot tell, and
  that has not changed — what changed is that something else now asks on a schedule. ⚠ **The drift is NOT monotonic** (it came back down), so *"it only ever goes
  one way"* is not available as a shortcut, and the gap to the lab's constant is not a running
  total. 🔴 **The four readings are recorded in THREE different places and no two of them agree on
  the series** — `fills.py`'s own comments hold the first two, the live bot's instance config
  (`_measured`) holds the third, and the fourth was in a chat log until this paragraph. **An
  earlier revision of this line listed the third as −79.60 because it reconstructed the sequence
  from the two places it happened to read.** A number that lives nowhere in particular gets
  restated wrongly; that is the case for collecting them, not just for watching them.
  ⚠ **Read the SHORT side before assuming a drift is small.** Gold PAYS shorts, and this strategy's
  scratch arithmetic rests on that credit — the credit moved 8.0% here while the charge moved 1.2%,
  and a single netted percentage would have hidden it.
- **`tools/cost_tiers.py`** (new 2026-08-10) — replays one strategy under several BROKER ACCOUNT
  TIERS and prints trades / total R / delta-vs-free, one real replay per row. It exists because
  `docs/LIVE_TRADING_PIPELINE.md` → G5a answers *which PU Prime account type* with exactly that
  table, and the table was built by hand on 2026-08-06 and had to be rebuilt on 2026-08-10 when the
  raw tiers' spread and commission stopped being marketing figures and became measurements.
  **A measurement nobody can re-run in one command is a claim.**
  `cost_tiers.py --spread puprime_ecn=0.12` · defaults to the three PU Prime tiers over
  2020-01-01 → 2026-08-03, which is the window every G5a figure is quoted on.
  ⚠ **`--spread TIER=VALUE` is a WHAT-IF and the output labels it `stated`, never `measured`.**
  `fills.py` carries `SPREAD_UNMEASURED` on any tier nobody has read a spread off and REFUSES
  rather than borrowing a sibling's — this flag overrides for one run and **writes nothing back**.
  It is per TIER and not one global number on purpose: a single spread applied to every row would
  hand Standard the raw tiers' quote and flatten the one difference the table is about.
  ⚠ **It charges `bid_ask_fills`, which REPLACES the flat spread charge rather than adding to it**,
  and it is the only cost model here that can change WHICH trades exist. That is why a tier
  comparison has to be replayed and cannot be re-priced: the cost acts by removing trades, and a
  trade that never happened has no P&L to charge.
  ⚠ **It deliberately does NOT report "setups never filled"**, the most informative column in the
  G5a table. Nothing in `Execution` counts a resting order that expired — that figure came from
  hand instrumentation nobody kept — and deriving a proxy from the trade list would answer a
  different question under the same heading, because with one position slot a refused setup lets a
  DIFFERENT setup take the slot. Add the counter to `Execution` if the column is wanted again.
  ⚠ Reads the R column only. Costs are size-independent in R while dollars compound, and this
  strategy's run-to-run spread is **sd 15.06R** (`jitter_audit.py`) — a smaller gap is noise.
- **`tools/axis_sweep.py`** (2026-09-07) — move ONE setting at a time off a strategy's shipped
  defaults and score every value in R, with its neighbours, both calendar halves and a control
  beside it. Strategy-agnostic: it reads `LAB_STRATEGY` off any package under
  `strategies/python/`.
  🔴 **It ENFORCES four rules rather than reminding you of them, and each is one somebody here has
  broken.** `--split` is REQUIRED and echoed above the table, so the out-of-sample boundary cannot
  be chosen after seeing the grid. A CONTROL row at the shipped defaults always runs first, and
  with `--expect-trades` / `--expect-r` it REFUSES the whole sweep when it misses — if the control
  moved, the harness moved and no row under it is readable. Everything is scored in R. `--server`
  names the broker whose cached bars were replayed, because two brokers' gold histories differ in
  LENGTH and a re-run on the other cache disagrees with every figure while looking healthy.
  ⚠ **An UNASSERTED control prints a loud line saying so** — a control nobody can check is
  decoration, and staying silent about it would let the next reader take it for a verified one.
  🔴 **`--axis` / `--pin` on a field whose current value is `None` passed the RAW STRING through
  until 2026-09-15, so EVERY `Optional` lever in the repo was unsweepable** — `_coerce` reads the
  type off the CURRENT value and `None` has none, so `--axis realign_tp_r=2` handed the config the
  string `"2"` while the table labelled the row `2`. A config with a validator crashes (which is
  how it was found); one without would have REPLAYED the string and scored a row against a value
  it never held. Rule 1's shape exactly: *unset* and *set to this* collapsing into one value. It
  now falls back to the field's declared ANNOTATION (`Optional[int|float|str]`), accepts
  `none`/`off`/`null` as `None`, and REFUSES a field it cannot type rather than guessing.
  🔴 **THAT FIX WAS HALF OF THE PROBLEM AND THE OTHER HALF SURVIVED UNTIL 2026-09-17: an optional
  lever that has shipped ON could not be pinned back OFF.** `_coerce` asked the CURRENT value
  first, so once the Realign momentum filter shipped at 20 its field answered "integer" and `=none`
  died on `could not convert string to float: 'none'`. **The moment a filter ships on, turning it
  off stops being sweepable — which is the one comparison anybody would want**, and it is what
  blocked reproducing that bot's previous book for a day. The `None` branch now runs FIRST, keyed
  on the declared annotation rather than the held value.
  ⚠ **No stored result moves** — the old paths could only produce a crash or a string-valued
  config, so no published figure was ever produced through them.
  ⚠ **One axis at a time, never a cartesian product, and that is the point rather than a
  limitation.** A grid over a ~100-trade book returns a winner whether or not one exists; sweeping
  an axis puts every winner's NEIGHBOURS in the table by construction, which is the only thing
  that tells a hill from a spike. Combine survivors deliberately afterwards and re-check both
  halves — **a one-at-a-time sweep cannot see an interaction, so its winners are candidates.**
  ⚠ **It reads each row's TRADE LIST through `run_sweep`'s `extract` hook and does NOT reproduce
  the bar loop** — see the `extract` section below for why that matters.
  ⚠ **`--pin` states a BASIS for every row including the control. It is not a second axis**; a
  value that varies belongs in `--axis` where its neighbours are printed.
- **`tools/verify_parity.py`** — the one "is everything in sync?" command. Point it at the TradingView
  export CSV(s) you just pulled; it runs every parity check (all nine engine `compare_*.py` + the
  sos_fade `compare_strategy.py` + the b_leg `compare_bleg.py`) whose MARKER column is present in the CSV, and prints one
  GREEN/RED/SKIP table. Cold-start warmup is auto-detected by walking a capped ladder (≤25% of the
  file), so a genuine LATE drift can never be skipped away as warmup. It reports drift; it does not fix
  it (a real logic change is still a hand port, per drift). Run it after any `mpc_jarvis.pine` /
  `sos_fade_strategy.pine` / `b_leg_strategy.pine` re-paste + re-export. Stdlib only.
  `verify_parity.py <csv> [csv ...]`, or no args = newest CSV in `backtest/`.
  Each registry row carries a MARKER column and a **VETO** column (added 2026-07-26): a check runs
  when its marker is present and its veto is absent. The veto exists because the two STRATEGY exports
  overlap — `b_leg_strategy_export.pine` plots `px_stages` too (the B leg arms off the SOS Fade
  sequence), so marker-alone would run the SOS Fade check against a B-LEG export and produce a red that
  means nothing. `bl_bits` exists only in the B-LEG export, so it is the SOS Fade check's veto and the
  B-LEG check's marker. Deliberately NOT solved by re-marking SOS Fade on an SOS Fade-only column like
  `px_block`: that column landed 2026-07-25, so every older SOS Fade export would silently stop being
  checked.
- **`tools/run_report.py`** — the "WHY did it make/lose money" run. Replays a `strategies/python/`
  bot over YEARS of broker bars and writes `trades.csv` (one row per trade, tagged with the
  `engines/regime/` label at entry, NY session/hour, and excursion in R) plus `setups.csv` (one row
  per SOS Fade leg that reached SOS, traded or not, with the FIRST thing that stopped it). The second file
  is the point: a blocked or skipped setup places no order, so it leaves NO trace in any broker trade
  list — this is the only place it is countable. Reports in **R, never dollars** (a fixed-%-risk
  strategy earns exponentially more dollars at the same edge, so a dollar curve makes a flat early
  year look like a broken edge). `--set FIELD=VALUE` overrides any config field for A/B tests
  (frozen dataclass, applied via `replace`); `--no-regime` skips the tagging. Everything it adds is
  reporting-only — no tag feeds back into the strategy, so results are identical with or without it.
  Carries the timeframe-substitution guard described under *history depth* below.
  **`--start` defaults to the MEASURED floor** (`_default_start` → `history.floor_for`), fixed
  2026-07-29. It had been hardcoded to `2022-01-01` while the help text claimed "broker's earliest",
  so every default run silently reported 4.6 of the available 7.9 years — the quiet direction of the
  substitution trap: nothing errors, the equity curve looks fine, and the run just answers a
  narrower question than the one asked. When the agent is down the broker cannot be identified, so
  it refuses and asks for an explicit `--start` rather than guess. **Same rule as everywhere else in
  this package: never type a history depth, measure it.**
  🔴 **A CONFIG THIS TOOL CANNOT REPLAY IS REFUSED, NEVER SILENTLY DOWNGRADED (2026-08-16).**
  `exec_secondary` needs `run_dual(df15, df1m)`; calling `run(df15)` with the flag on produces a
  primary-only book that looks exactly like a run where the feature never fired — `optimizer.py`
  and `portfolio/legs.py` had already met this and refuse it. The tool now loads the 1m frame and
  calls `run_dual`, refuses when there is no `run_dual` or no fill-clock bars, and always PRINTS the
  secondary trade count so *0 secondaries* is a stated answer. ⚠ **`--no-secondary` SETS the flag
  False rather than only picking the fast path** — the config that is reported must be the config
  that RAN. ⚠ **THIS MOVED DOCUMENTED BASELINES**: every `sos_fade` figure this tool produced
  at the default config before that date is primary-only, valid as a MATCHED SET (rankings stand)
  but understating absolute totals — **MEASURED 2018-09-14 → 2026-08-14, bar fills, ONE window both sides: 189 trades /
  +164.4R with the secondary against 181 / +138.9R without — the gap being 8 secondary trades
  worth exactly +25.5R**. ⚠ **Dual costs ~50 min a
  full-history replay against ~3 min.** ✅ **BOTH FIGURES ARE SUPERSEDED — RE-MEASURED 2026-08-27:
  a full 6.6-year replay is 59.9s single-feed and 94.1s DUAL** (157,004 M15 + 471,830 M5 bars,
  200 trades). **The 471,830 extra bars cost 34 seconds.** ⚠ **Two separate reasons the old pair
  no longer applies, and they must not be collapsed**: the fill clock defaulted 1m → 5m on
  2026-08-21 (a fifth of the bars for 1.3% of accuracy), and the replay path itself got ~9x faster
  on 2026-08-26/27 (`HISTORY.md`). **So the ~50 min was a 1-minute clock on the old code and is
  not comparable to either number here.** 🔴 **The standing point is the one this file keeps
  making: a TIMING in a doc goes stale exactly like a measurement, and this one had been quoted as
  the reason not to run a dual replay.** Pinned by `tests/test_run_report_secondary.py` (7; 3
  watched RED against HEAD, the behavioural pair killed by 2 mutations). Story:
  `docs/BACKTEST_BUILD_NOTES.md` → *The secondary that never ran*.
- **`archive/`** — committed, frozen `run_report.py` output. `backtest/reports/` is git-ignored
  per-run scratch, which meant multi-year trade data existed only on the machine with a warm cache
  and a live agent; `archive/<date>_<symbol>_<tf>_<scope>/` is the copy that travels with a clone, so
  someone with no VPS and no MT5 can still analyse real trades. It is a SNAPSHOT, not a build
  artefact — nothing regenerates it, so any config change makes it stale. Each folder carries a
  README stating the window, fill model, config levers at run time, and open caveats; keep that
  honest or the numbers get quoted without them. Current: `2026-07-29_xauusd_15m_full_history/`
  (SOS Fade and B-LEG, 2018-09-13 → 2026-07-29, bar fills).
- **`tools/overlap_audit.py`** — do two strategies actually trade DIFFERENT legs of the move? Replays
  two `strategies/python/` bots and reports the bars both held a position (split
  same-side vs opposite), which trades pair up, how far apart same-direction ENTRIES land (the direct
  test of "both fired on one structure break"), what a single account would have carried, and the
  monthly R correlation. **Built 2026-08-04 to close the standing SOS Fade/B-LEG overlap question**, which
  had been design intent in three CLAUDE.md files for a year and never measured; it passed —
  27 shared bars in 155,453, one same-direction cluster in 6.5 years. ⚠ **It deliberately does NOT
  net the two into a combined equity curve**: both bots are `self_sizing`, so running them on one
  account changes both bots' sizes from the first shared trade and the result is a third thing
  neither bot is. That question belongs to the allocator (G10); this tool measures how often
  the allocator would have had anything to arbitrate. ⚠ **Re-run it after any entry-logic change on
  either bot** — the output is a fact about today's config. The bar arithmetic is unit-tested
  (`tests/test_overlap_audit.py`), because a slip in it would report "the legs never overlap" exactly
  as cleanly as the truth does.

  🔴 **IT REPLAYED A BOT NOBODY RUNS FOR ITS ENTIRE LIFE, AND EVERY FIGURE IT PUBLISHED BEFORE
  2026-09-02 IS A PRIMARY-ONLY NUMBER.** It always called the one-frame `run()`, while
  `sos_fade`'s re-entries need two frames — and that switch is ON in the strategy's DEFAULT
  config *and* in the live bot's own instance config. So the tool built a config saying re-entries
  were on, ran a path that cannot fire one, and printed a clean report. **Nothing failed and nothing
  was empty**: SOS Fade simply arrived with a third of its trades missing, which looks exactly like a bot
  whose re-entries never triggered. ⚠ **Only SOS Fade was affected** — `b_leg` sets the switch False and
  `extreme_leg` has no such field, both checked rather than assumed. ✅ Fixed by loading each
  bot's own fill clock as a THIRD frame and calling `run_dual`; it **refuses** rather than
  downgrading when a bot wants a fill clock it cannot supply, and `--no-secondary` SETS the flag
  False so the config reported is the config that ran. ⚠ **`_choose_replay` is IMPORTED from
  `run_report.py`, never re-implemented** — that tool met this identical defect on 2026-08-16, and
  a second copy of *which replay path does this config need* is how the two tools come to disagree
  about what a bot is.

  🔴 **A TRADE IS PLACED BY ITS OWN RECORDED MILLISECOND, NEVER BY A BAR NUMBER — A BOT WITH
  RE-ENTRIES NUMBERS ITS TRADES IN TWO FRAMES.** A re-entry is stepped on the fill clock, so its
  bar number counts 5-minute bars while its primaries count 15-minute ones, in ONE trade list with
  no field saying which. `_holds` and `_monthly_r` both looked every number up in the primary frame
  until 2026-09-03, which put re-entries weeks or months from where they happened and clamped the
  ones running past the end of the frame onto the last bars. MEASURED on 2024: 7 of 24 trades
  misplaced, worst by 5,355 hours. **A bar number is meaningless without the frame it counts.**
  `Grid.unit_ms` is the only placement now; `kind` chooses the WIDTH alone.

  🔴 **`_occupancy` REFUSES two positions in one bot, AND ITS REFUSAL WAS ONCE DELETED FOR BEING
  RIGHT.** The guard fired on the misplaced holds above and was read as a discovery — *SOS Fade holds two
  at once* — so the cell was widened to counts, the tests rewritten, and a doubled-risk warning put
  in the root `CLAUDE.md`. All of it was the placement bug. Placed by timestamp the same replay
  reports **0** doubled bars, and the strategy fills a re-entry only while flat
  (`Execution.step_secondary`, `_pos_dir == 0`). **A guard firing is a question, not an answer;
  widening it answers nothing.** Its message now names the placement as the first suspect, because
  the last reader of that raise did not have that sentence.

  ⚠ **SAME and OPPOSITE PARTITION the overlap** — they briefly did not, as a consequence of the
  wrong model. ⚠ **The grid stays the finer PRIMARY frame and must** — `frames` also holds fill
  clocks, and reading the minimum off the whole dict would re-base the SOS Fade/B-LEG audit from 15m onto
  5m purely because SOS Fade fills re-entries there. ⚠ **`overlap_counts` is PUBLIC and the test suite
  CALLS it** rather than mirroring it.

  🔴 **EVERY CLASH FIGURE PUBLISHED 2026-09-02 → 2026-09-03 CARRIES THE PLACEMENT BUG** — shared
  bars, the same/opposite split, trade pairs, entry clusters, both correlations. **Trade COUNTS and
  R totals do NOT**: those come from the replay, which was already right. Root `CLAUDE.md` was
  re-measured after the fix. Story: `HISTORY.md` → *The guard that was deleted for being right*.

  🔴 **IT TAKES TWO BAR FRAMES SINCE 2026-09-01, AND BAR INDICES CANNOT EXPRESS THAT.** Bar 400 of a
  15-minute frame and bar 400 of a 5-minute frame are eleven hours apart, so the one-frame version
  would have compared two different afternoons **in exactly the same confident format as the truth**.
  Both bots' holds are now converted to their own bars' TIMESTAMPS and located on the FINER frame's
  own index. ⚠ **A regular clock grid was the obvious alternative and is wrong**: it counts the
  weekend as bars, so every `% of all bars` already recorded against this tool would move by a third.
  ⚠ **A coarse bar occupies its WHOLE width on the grid**, or a 15-minute bot reports a third of its
  real exposure against a 5-minute one — and that error only ever runs one way, understating overlap.
  ✅ **The same-frame case is the IDENTITY and that was proven, not argued**: the pre-change tool and
  this one give byte-identical output on the same bars, and `test_the_same_frame_maps_every_trade_onto_its_own_bar_index`
  pins it, because the SOS Fade/B-LEG figures quoted in the root `CLAUDE.md` were measured before the grid
  existed. **No documented baseline moves.**

  ⚠ **The cluster window is a DURATION now, not a bar count.** It was 16 bars, which meant four hours
  only while both bots shared a 15-minute frame; on 5-minute bars that same number silently becomes
  80 minutes — a stricter test reported under the old test's name. 15m still resolves to exactly 16.

  🔴 **A bar the fine feed is MISSING falls forward to the next one that exists, and the count is
  PRINTED above the numbers.** Dying on one absent candle would throw away an eight-year replay, but
  the silent version is this repo's oldest trap: a gappy feed and a clean feed would produce the same
  confident output with no way to tell which you got. MEASURED on the two caches here — PU Prime is
  missing **4** of 157,004, Vantage **15** of 156,819.

  🔴 **`--server` exists because the audit could not be RE-RUN without the app up.** Without it the
  bar source asks whichever MT5 terminal is attached, so a re-run offline dies at the fetch while a
  complete cache sits on disk. ⚠ **Name the server every audit was measured on** — the 2026-09-01
  re-measurement of SOS Fade/B-LEG recorded neither the broker nor the symbol, and reproducing it took
  three replays to work out that 157,004 bars is PU Prime and 156,819 is Vantage. **A basis nobody
  wrote down is a number nobody can check.**

  ⚠ **The account line reads each config's own risk (2026-09-10)** — it printed a typed *10% → 20%*,
  wrong for the extreme-leg pairing since 2026-09-02. It states the STRATEGY defaults it replayed,
  never a deployment. Tests use UNEQUAL risks: a matched pair prints the same figure under the
  typed line, a doubling and the true sum.

  🔴 **`--record` / `--check-baseline` (2026-09-10): the clash figures can no longer outlive the
  settings they were measured on.** They went stale three times and each time a DEFAULT had moved
  — the last inside a Command Center commit where nothing read as an entry-logic change.
  `--record` writes a pair's full settings (strategy AND engine config, read off what the replay
  builds, through `_build`), its basis and its headline results to `tools/overlap_baseline.json`
  at the end of a finished run. `--check-baseline` is step 17 of `scripts/run_all_tests.sh`: red
  on any moved, NEW or REMOVED setting, naming each one and printing the re-measure command.
  ⚠ **Settings, not code** — a rule changed inside a strategy still needs a re-run by hand.
  ⚠ **Clearing it means measuring**; a hand-edited record is decoration. ⚠ **No recorded pair
  FAILS.** ⚠ `--record` refuses without `--server`, because the record is the basis a re-run
  reproduces. ✅ **First caught one the same day**: B-LEG's adding-to-winners pin moved one setting
  on `sos_fade|b_leg`, step 17 named it, and the re-record read +20.07R → +20.20R, clashes unchanged.
  ⚠ **Risk per trade is fingerprinted too**, so moving it re-records a pair although it moves no
  trade here (each bot replays off its own equity): SOS Fade's default went 10 → 5 on 2026-09-13
  and both SOS Fade pairs re-recorded with every figure unchanged.

  Its results are facts about the BOTS, so they live in root `CLAUDE.md`; story and full numbers in
  `HISTORY.md`.
- **`tools/jitter_audit.py`** — how much of a backtest survives a few cents of feed difference?
  Replays a `strategies/python/` bot over the same bars N times with a small random offset added to
  each BAR's four prices, and classifies every jittered trade against the baseline: **flipped** (the
  entry moved further than the noise can account for — a `exec_fib_nearest` rung change),
  **retimed** (same setup, filled within 16 bars), **lost** / **gained** (no twin at all), and
  **shifted** (moved by about the noise, which is expected). **Built 2026-08-05 to close G17**, the
  half of the shadow-diff finding that one live window could not answer. ⚠ **The offset varies per
  BAR and is applied to all four prices at once** — a constant offset translates the whole fib ladder
  and flips nothing, and independent per-price noise builds candles no feed can produce. ⚠ **The flip
  threshold is `2 * amp`, derived from the noise rather than picked.** ⚠ **`--amp` defaults to the
  MEASURED broker gap** (0.05; the shadow diff found Vantage above PU Prime by 0.04–0.05 on every one
  of 148 live bars), not a round number — raising it measures a broker nobody trades. ⚠ **Read the
  spread across seeds, never one seed**: the answer is a distribution, and a single jittered run is
  one draw from it. The classification is unit-tested (`tests/test_jitter_audit.py`) because a slip
  in it would report "the trade list is perfectly stable" exactly as cleanly as the truth would.
- **`tools/compare_feeds.py`** — feed-parity check: MT5 pull vs a TradingView export of the same
  symbol/TF/window. Reports **clock offset** (0 = aligned; non-zero = the broker-server-time bug
  that shifts every session — fix before demo), coverage, and OHLC drift. This is *data* parity, not
  *logic* parity (that's the strategy's `compare_strategy.py`) — MT5 and TradingView are different
  feeds and never match exactly; the tool measures the gap. **Not a per-backtest check.** Run it:
  once as a baseline, whenever the agent's time handling or the broker/terminal changes, at the start
  of each demo campaign then ~monthly, and any time trades look off vs the chart. Needs the MT5 agent
  + tunnel; the alignment math is unit-tested offline. Full rationale + cadence: `docs/SOS_FADE_BUILD_PLAN.md`.

- **`tools/trigger_edge.py`** — **does a TRIGGER carry edge, before any strategy is built?** Added
  2026-08-06 to answer "which of the two continuation setups is worth pursuing" when NEITHER has a
  Python port, so neither could reach `optimizer.py`. It replays the canonical `market_structure` +
  `vwap` engines, finds the bar a trigger would actually be IN on, and asks only whether price reaches
  `+NR` before `-1R`. No sizing, no ladder, no costs; R is each trigger's own structural stop.
  🔴 **THE CONTROL IS THE TOOL.** Gold went 1,200 → 4,300 across the cached window, so a long-side
  "edge" is free and any harness without a control will find one. Every set is scored against random
  entries **matched on direction AND stop distance**, and the control landing on the theoretical
  breakeven with expectancy ~0.000 is what certifies the harness before any result is read off it.
  **If you add a trigger here, add its control in the same commit.**
  ✅ **Findings 2026-08-06** (186,384 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-07): the with-trend
  BOS → 0.5 retrace trigger is **+4.4% over control (+2.5σ, n=778)**; adding the **pro-trend session
  VWAP side** takes it to **+6.8% (+2.8σ, n=404)** with the median stop **38% tighter** (1.80 → 1.11
  ATR); the D strategy's counter-SOS → VWAP-reclaim trigger is **−0.4% (−0.3σ, n=833)**, i.e.
  indistinguishable from random, and goes significantly negative at long targets (−2.8%, −2.1σ at 4R).
  That is what put VWAP into `bos_strategy.pine` (F10) rather than leaving it in the D file.
  ⚠ **It measures SKELETONS, not the shipped strategies** — no FVG requirement, no Sniper Zone, no
  session filter, no min-stop guard, no real exit ladder. A result here is a prior for a TRIGGER,
  never a strategy's own number.
  🔴 **The look-ahead trap it already fell into, recorded because the symptom was being TOO GOOD
  rather than erroring:** reading the VWAP side off the close of the bar its limit FILLS on selects
  bars that recovered by their close, and reported the filter at **+15.9% / +5.0σ**; reading the
  PREVIOUS closed bar gives +6.8%. **Anything evaluated on the bar it acts on is look-ahead until
  proven otherwise** — see `prev_side`.
  ⚠ **It drops the coarse head of the cache before measuring.** `XAUUSD__M15.csv` opens with
  HOURLY bars — MT5 serving coarser data where it has no M15 history, exactly the silent-substitution
  trap this file documents below — so `drop_coarse()` keeps only the contiguous tail whose median
  spacing really is 15 minutes. Measuring the raw file would score eight years of one trigger against
  a different bar size.
  ⚠ **Stdlib only, on purpose** — it drives the engines directly and needs no pandas, so it runs on a
  bare interpreter. Run it: `python3 backtest/tools/trigger_edge.py` (~5s).

- **`tools/intraday_edge.py`** — **is there a SECOND, intraday strategy worth building?** The sibling
  of `trigger_edge.py`, same method (matched random control on direction AND stop distance, hard 8h
  horizon, nothing scored on the bar it acts on), eight intraday triggers. Added 2026-08-07.
  🔴 **Its headline finding is a REFUSAL and it is the useful half: there is no intraday edge to
  harvest on GOLD, and the reason is structural.** All eight triggers are NET NEGATIVE after cost over
  186,384 M15 bars; the best (`ORB_BREAK`, +2.6% / +2.4σ over control) lands at **−0.008R** — a real,
  statistically detectable effect almost exactly the size of the spread. **An intraday stop on gold is
  $1–7 against a ~$0.30 round trip, so cost is 4–37% of every R before the signal says anything.**
  That is why the SOS fade works and an intraday sibling does not: a median $8.88 stop puts cost at ~3%.
  ✅ **The same trigger clears cost comfortably on NAS100** (+4.0% / +3.6σ, cost 1.2% of R,
  **+0.049R**), which is the prediction the cost hypothesis makes and it holds — both sides positive
  with the SHORT side stronger, both halves positive, positive in 6 of 9 years, and the MIRROR
  (`ORB_FADE`) catastrophic at −15.2% / −18.9σ. ⚠ **Read it as a prior on a TRIGGER, never as a
  strategy's number** — no ladder, no staged stop, no position slot, no swap, and NAS100 has no
  history floor, no Pine parity and no strategy package here. Full record: `docs/INTRADAY_EDGE_STUDY.md`.
  ⚠ **Two triggers are significantly NEGATIVE on gold and that is knowledge worth keeping**: fading a
  VWAP stretch and fading the opening-range break both lose to random in 9 years out of 9. Gold does
  not mean-revert intraday. Do not build either. Stdlib only, runs off `backtest/cache/`.

- **`tools/sweep_edge.py`** — **the sweep-and-reclaim is one trigger. Which LEVEL should it sweep?**
  Added 2026-08-14 to settle structure-vs-session-vs-both with a number instead of a chart. Holds
  the trigger fixed and varies only the level across five families — `structure` (the protected
  iHL/iLH `mss_sweeps.pine` arms), `session`, `day`, `week`, and `h4` as an internal BASELINE.
  Stdlib only, runs off `backtest/cache/`. Full record: `docs/SWEEP_LEVEL_STUDY.md`.
  🔴 **ITS FINDING IS ABOUT THE TRIGGER, NOT THE LEVEL, WHICH IS NOT THE QUESTION IT WAS ASKED.**
  `--trigger wick` drops only the close-back requirement, and **every family goes negative — h4 at
  −2.2% / −5.3σ over 11,541 events.** Adding the reclaim is worth ~2 points of win rate to all five
  families alike. The ranking between levels (structure +5.3% / +2.1σ, session +1.6%, day +1.9%,
  week −0.6%, h4 +0.3%) is worth a fraction of that, falls to +1.5σ under `--min-risk-atr 0.5`,
  is negative in 2023, and peaks at exactly the 2R the table was scored on. **Keep the reclaim; do
  not add session levels to the MSS trigger on this evidence.**
  ⚠ **Confluence made it WORSE**: structure alone +7.2%, structure ∧ session +4.3%. "Both" is not
  the answer. ⚠ **The video's own headline rule — Asia high taken in London — is the WORST of the
  six session pairings** (−0.8%, and −3.9% under the stop guard) while Asia-in-NY is the best.
  That measures his LOCATION rule stripped of his M1 confirmation and his OB entry; it says the
  location carries no information alone, not that his book is fake.
  🔴 **The control is matched on THREE axes, not `trigger_edge.py`'s two.** Session sweeps land at
  specific HOURS and gold does not drift uniformly around the clock, so a control drawn from all
  hours would hand the session rows an edge made entirely of what time of day it is. Built by
  post-stratification over cached (direction, hour, 0.25-ATR stop) cells — resampling per table row
  was ~200M bar steps and the first draft did exactly that.
  🔴 **CONFLUENCE IS READ OFF A PRE-SWEEP SNAPSHOT, and the first version was ORDER-DEPENDENT.**
  Several families routinely hold a level at one price — a session low that is also PDL is one line
  on the chart — and scoring off the mutated live-level dict meant whichever fired first was the
  only one the next could still see: the four levels swept at 1192.89 reported four DIFFERENT
  confluence sets, descending as they were popped. The structure-vs-session-vs-both answer is
  decided entirely by that set.
  ⚠ **The engines own the LEVELS; this tool owns the TRIGGER.** `ev.mitigated` is deliberately NOT
  read — day/session/H4 mitigate on a bare wick while week mitigates on a close-through, so it
  would score five families on three different triggers and call the difference a level effect.
  Only `ev.created` / `ev.evicted` are consumed.
  ⚠ **Median stop is 0.69 ATR — a few dollars on gold against a $0.12–0.33 round trip.** The tool
  prints that warning itself and names `--min-risk-atr 0.5`. No costs, no ladder, no position slot:
  a prior for a LEVEL, never a strategy's number.
  ⚠ **`--min-risk-atr` defaults to 0** (honest for a study, wrong for a strategy) and it is the
  cut that decides whether structure's edge clears 2σ. Quote both.

- **`tools/pre_sos_leg_queued.py` and `tools/pre_sos_leg_tune.py`** (2026-08-25) — the one-position
  version of the study below, and the settings sweep built on it. Both IMPORT the study rather than
  restating any rule, so they cannot drift from it.
  🔴 **A STUDY WITH NO POSITION SLOT REPORTS AN UPPER BOUND, AND THE TOOL BELOW SAYS SO IN ITS OWN
  DOCSTRING WHILE ITS NUMBERS WERE QUOTED AS THE STRATEGY'S.** Measured: 228 setups → **200** a
  one-position strategy can reach, and the 28 it cannot are BETTER than average. **Ask what a study
  assumes about concurrency before quoting it at a strategy that holds one trade.**
  🔴 **SWEEP WITH THE SLOT ON — it changes which setting WINS, not just the score.** An exit that
  ends a trade sooner hands the slot back and buys the next setup, so it is worth more than its
  average outcome says: the winning exit here rates +0.349R against +0.310R with no slot (marginal)
  and +0.400R against +0.276R with one (decisive).
  🔴 **A ONE-AT-A-TIME SWEEP CANNOT SEE AN INTERACTION, SO ITS WINNERS ARE CANDIDATES.** The single
  best change measured alone — two liquidity levels agreeing — cut the return by more than half once
  the winning exit was also in, and its two time-halves fell apart. **Run the combination before
  believing any of it**, and re-check on both halves of the history.
  ⚠ The exit walks return the bar a trade was let go on, which is what the slot needs; that value
  was always computed and thrown away. Adding it moved no number the study reports — verified by
  re-running and diffing the whole report.
- **`tools/pre_sos_leg_grid.py`** (2026-09-01) — the cartesian product, the timeframe question, and
  the search for a rule that removes losers. Imports the study and the one-position rule; restates
  neither. 509,000 configurations run through it so far.
  🔴 **A SEARCH THIS SIZE HANDS BACK A WINNER WHATEVER THE DATA IS, so the tool is built around
  refusing to report the top row alone.** Three defences, and the middle one earned its keep on the
  first run: every configuration is scored on both calendar halves and ranked by the WORSE one; the
  winner's NEIGHBOURS are printed on every axis; and the shipped configuration is printed beside
  each ranking so "is this actually better" needs no arithmetic.
  🔴 **PRINTING THE NEIGHBOURS IS THE PART THAT CHANGED AN ANSWER.** A fine pass named a setting 4%
  better than shipped; its neighbours across single steps ran 74 / 87 / 83 / 75 / 77 / 74, so the
  axis moves 10R between adjacent values and the winner was a coin. **A hill and a spike look
  identical from the top — the only way to tell is to step sideways.**
  🔴 **A CHALLENGER MUST BE RE-TUNED BEFORE IT IS DISMISSED.** Holding one chart's settings and
  applying them to another only proves settings do not transfer, which nobody doubted. The
  30-minute chart got its own full 252,000 and still lost by more than half.
  🔴 **A CUT IS APPLIED BEFORE THE POSITION SLOT, NEVER BY DELETING ROWS FROM A RESULT.** Refusing a
  setup has to genuinely buy whatever came next; scoring it the other way measures a strategy that
  could see the future, and it flatters every cut ever tried.
  ⚠ **The loser-hunting stage is the most overfittable thing in the file and says so** — it searches
  for a NEW rule using the losses it is trying to remove as the thing that suggests it. Its axes are
  deliberately restricted to cuts a trader can state a reason for; an hour-by-hour cut is not
  offered, because it would win and it would mean nothing.
  ⚠ **The whole product finishes only because the exit re-walk is shared**: a filter cannot change
  when a trade ended, only which trades are looked at, so each pool is re-walked once per exit rule
  and every filter underneath reads the same answers. 252,000 configurations in 291 seconds.
  ⚠ **One real bug found and fixed here**: a target that lands a rounding error from the entry price
  divided by zero in the walk. It only reaches that state on same-frame pairs; the shipped pair
  re-ran byte-identical afterwards, so no documented baseline moves.
  ⚠ `MINUTES` in the study gained a 4-hour entry so the timeframe question could be ASKED. Additive
  only — every existing default names its own frame, so nothing that ran before runs differently.
  🔴 **`--stage ladder` GOT ITS ANSWER WRONG THE FIRST TIME, PURELY FROM ITS AXES.** It offered
  only two-stage exits whose second leg ran FURTHER than the shipped one; every one lost, by up to
  5.5R, because with a single slot the runner holds 625 minutes against 400 and blocks ten setups
  doing it. Widening the axes so a ladder could also finish SOONER moved the best from −5.5R to
  +1.8R. **A search that can only move a setting one way has decided the answer before it runs —
  ask which direction an axis is allowed to go before believing what it reports.** (The +1.8R was
  then refused anyway: its four nearest neighbours span +81.8R to +85.8R around a shipped +84.0R.)
  🔴 **`--stage costs` EXISTS BECAUSE THE PARENT STUDY CHARGES HALF THE SPREAD AT ENTRY AND NOTHING
  ELSE**, and that model was quoted at a strategy about to trade money. Measured on the live tier:
  the whole bill is 4.0R over eight years, ~4.6% of gross, and **financing is the largest part of it
  (2.46R) rather than commission (0.63R)**. ⚠ **The live account is CHEAPER than the feed every
  number was measured on** — half the spread beats the commission it charges — so the honest
  correction went the good way for once, and it also clears two extra setups because a tighter entry
  leaves the target further away in stops.
  ⚠ **The tier's spread goes into the COLLECTION, never on top of the result.** It moves the entry
  price, which moves how far the target is in stops, which moves what qualifies — re-pricing a
  finished trade list would miss all of that.
  ⚠ **The spread is charged twice for a loser and once for a winner**: entry is a market fill, the
  target is a resting limit that fills at its own price, the stop is a market order that pays again.
  ⚠ **Costs are in R and that makes a TIGHT stop expensive** — one lot risks the stop distance times
  the contract size, so a fixed commission is a far larger slice of a small risk.
  ⚠ **The cost constants are COPIED from `fills.py` rather than imported**, because that module
  needs the whole replay stack and this tool is stdlib-only by design. Each is quoted with its
  source. **Re-read them before quoting the table again — this symbol's overnight financing has now
  been read FOUR times in seven weeks and moved on three of them, with nothing to announce it.**
  ⚠ **A drift is not automatically worth re-pricing** — the 2026-09-02 reading was replayed both
  ways and came to +0.09R. See `tools/swap_audit.py` above for the measurement and the decision.
- **`tools/pre_sos_leg.py`** — **the leg BEFORE the shift of structure. The SOS Fade bot waits for the
  shift and fades the retracement; this asks whether the move that CREATES it is tradeable.** Added
  2026-08-24 on Aaron's question. Stdlib only, runs off `backtest/cache/`. Full record:
  `docs/PRE_SOS_LEG_STUDY.md`.
  🔴 **THE EXTREME IS ONLY KNOWABLE AFTERWARDS, so the whole tool is about finding a REAL-TIME
  proxy for it.** The prize is real — measured over 811 external breaks, the extreme-to-break leg
  is a median **$20.55 / 7.7× ATR(50) / 36 bars, ~106 a year**. Getting on it is the entire problem.
  🔴 **CONFIRMING ON THE BASE FRAME IS DEAD, AND THE NUMBER THAT KILLS IT IS `medR 0.87`, NOT THE
  EDGE.** By the time the M15 changes character internally, the target sits CLOSER than the stop —
  the setup arrives having already spent its own reward. **A confirmation that is late is not a
  weak signal, it is an absent trade**, and a tool that only reported win rate would have scored it
  50.9% and looked fine. Report the R AVAILABLE beside every hit rate.
  ✅ **What survives: a 15m level swept, then a change of character on the 5m within 3h, the 15m
  trend still opposing, target ≥2 stops away.** n=228 over 9 years, hit 28.1% at medR 3.67,
  **+0.296R against a matched control at 21.6% (+2.2σ)**; two level families agreeing n=112,
  +0.386R (+2.4σ). ≈25 trades a year.
  🔴 **ITS ARMING RULE IS LOOSER THAN THE STRATEGY IT MEASURED, MEASURED 2026-09-01 BY DIFFING THE
  TWO, AND EVERY NUMBER ABOVE CARRIES IT.** Two differences, both in when a sweep counts as fresh:
  this tool dates a sweep at the BASE frame's bar CLOSE while the strategy dates it on the 5-minute
  bar that crossed (so the window reaches 5–15 minutes further back here), and this tool counts
  wall-clock MINUTES while the strategy counts BARS (they agree while bars are contiguous and part
  company across a weekend). ⚠ **Neither invalidates a result and both change what one DESCRIBES.**
  ⚠ **Do not "fix" this tool to match** — that silently re-bases every number already recorded
  against it. A study is allowed to be a study; what it may not be is undocumented. The thing that
  settles the question is the port's parity gate
  (`strategies/python/extreme_leg/tools/compare_extreme_leg.py`), not another run of this.
  🔴 **The SWEEP is the ingredient and it is not close: the identical trigger with no level under
  it is 18.2% and −0.186R.** Session (+14.4%) and daily (+16.7%) are the strong families, h4
  (+5.7%) the weak one that still works, weekly n=8 and unanswerable.
  ⚠ **Its confluence result CONTRADICTS `sweep_edge.py`'s** (stacking families helps here,
  monotonically; there it hurt) and neither is wrong — that study scored a fixed 2R target off a
  wick stop, this one a structural target off a faster-frame confirmation. **Confluence is not a
  property of the levels alone.** Re-quote either number only with the target it was measured on.
  ⚠ **Banking early buys nothing** — exiting anywhere from 0.5 to 1.0 of the way pays +0.31 to
  +0.35R, flat. And the failure shape is early: most losers die under 30% of the way, while a trade
  80% there finishes 87.8% of the time.
  🔴 **AN EARLY MOVE TO BREAKEVEN COSTS −0.217R A TRADE, AND THE BEST ARM POINT IS WORTH A
  ROUNDING ERROR.** Measured by re-walking every qualifying trade with the stop moving to entry at
  a given fraction: arming at 30% takes the win rate 28.1% → 16.2% while losses only fall
  71.9% → 50.9%, so **the trades a breakeven stop "saves" are overwhelmingly ones that were going
  to win** — this setup's retracements happen INSIDE the leg, not before it. The peak is ~70%
  (+0.024R) and 90% is +0.000R. **Leaving the stop alone entirely is within noise of the best
  setting and is one less thing to get wrong live.** ⚠ A scratch is booked at −(half spread)/risk,
  never at zero — the entry carries half the spread and exiting at entry returns the other half.
  ⚠ **The arm is decided on a BAR CLOSE, never intrabar**: nothing in a bar says which extreme came
  first, and arming intrabar exits at a price the model could not have known to place. That
  flatters the breakeven rows and they still lose.
  ⚠ **It reads ONE private field of the structure engine** (`_ext.ash`/`_ext.asl`) — the swing that
  is live RIGHT NOW, which the public stream cannot give because events fire on CHANGE, not on
  STATE. The alternative was rebuilding that state here, which is the second implementation rule 21
  exists to prevent. **Guarded: a rename raises on the first bar rather than quietly scoring zero.**
  🔴 **A FASTER CONFIRMATION FRAME IS NOT A CHEAPER VERSION OF THE SAME IDEA — `--confirm M1`
  gets the stop down $7.24 -> $4.35 and takes expectancy +0.296R -> +0.032R.** The hit rate falls
  faster than the payoff rises. ⚠ **And the M1 row carries the HIGHER SIGMA (+3.2σ vs +2.2σ),
  which is the trap**: σ scales with √n and M1 fires 12× as often, so ranking rows by significance
  picks the worse trigger. **Read the expectancy; sigma only says whether it is real.** ⚠ Per YEAR
  they look close (≈+7.5R vs ≈+9.9R gross) and COST is what separates them — `--spread 0.44`
  charges the whole round trip at entry and takes M1 to **+0.002R** while M5 is unmoved at
  +0.307R, because a full spread is ~1.5% of a $7.24 stop and ~5% of a $4.46 one. 🔴 **M1's edge
  over the control SURVIVES this (+2.3% / +3.1σ) — it really is detecting something, and it is
  still not worth trading, because what it detects is smaller than the cost of acting on it.
  "Beats random" and "worth trading" are different questions and only the second has a broker in
  it.** ⚠ Level-stacking helps M5 monotonically and does
  NOTHING on M1 — **a filter that works on one frame and not the other says the two triggers are
  not detecting the same event.**
  🔴 **`--trigger reclaim` AND `--entry-on-base-close` EXIST TO SETTLE AN ARCHITECTURE QUESTION
  BEFORE A LINE OF PINE IS WRITTEN, and both answers were needed.** The single-frame stand-in (a bar
  closing back beyond the sweep bar's extreme, no second engine) scores **+0.082R against the 5m
  change of character's +0.296R**, and filling on the next base close instead of the confirmation
  close costs about a quarter of the edge (**+0.223R, +3.1σ**). **So the faster engine is not a
  convenience somebody could skip — it is what carries the result**, and the Pine has to embed a
  second state-machine instance. ⚠ **Measure the cheap architecture before building the expensive
  one**; the reverse order is how a file gets written twice.
  ⚠ **228 trades, three losing years inside them** (2021, 2023, 2024) against a 2025-26 that carries
  half the result. Found on PU Prime, reproduced on Vantage; costs are half a spread on entry and
  **no commission, so the live ECN account is not modelled.** A study, never a backtest.

- **`tools/killzone_profile.py`** + **`tools/killzone_sweep.py`** — **is the New York kill zone
  special, or does it just look special because we watch it?** Added 2026-08-04, stdlib only, runs
  off `backtest/cache/`. The profile tool measures what price DOES in a window and reports the same
  statistics for every other NY hour, so nothing can look remarkable until you have seen the base
  rate. The sweep tool then replaces its crude "took out the last seven hours" proxy with the real
  `engines/liquidity/` levels — PDH/PDL, PWH/PWL, H4 sweep targets, each finished session's high and
  low — and asks which level, when taken, actually precedes a reversal.
  🔴 **The answer is a REFUSAL and it is unambiguous. There is no clock edge and no level edge in
  KZ1** (2,031 days, 2018-09-21 → 2026-08-11, re-run 2026-08-13). At +2h the 10:00–11:00 window
  reverses the leg into it **49.0% of the time — a coin flip, and the LOWEST rate of the twelve
  hours measured**, i.e. the hour everyone watches is the least reversal-prone one on the board.
  The naive fade is **−0.087R over 2,026 trades** and loses in eight of nine years.
  ⚠ **The interesting half is that REAL levels did not rescue it, and that is the whole point of
  the second tool.** A real level is swept in this window on 63.2% of days, and **every single level
  is negative** when you trade the sweep's own direction — H4 highs −0.083R, H4 lows −0.071R, and
  the "classic" ones are the worst of the lot (PDH **−0.264R**, Asia H −0.238R, London H −0.191R).
  The crude proxy's apparent lift (a losing fade −0.117R → −0.011R on swept days) does **not**
  survive being given actual liquidity levels. ⚠ **One cut is positive — "sweep OPPOSES the fade",
  +0.076R on 189 trades — and it is the only positive number in three tables of dozens. Treat it as
  what a search over many cuts produces by construction, not as a finding.** ⚠ These are two
  STUDIES, not strategies: no costs, no ladder, no confluence, stop wins any ambiguous bar. They say
  the trigger carries no information; they do not price a finished system.

- 🔴 **All three study tools above were BRICKED from the day `FEED_VERSION` went to 3 until
  2026-08-13, and the fix is a standing lesson about version pins.** `killzone_profile.py`,
  `killzone_sweep.py` and `h4_sweep_profile.py` each guard their clock arithmetic with a cache
  version check, because v1 bars are stamped in broker-local time and every session boundary would
  be silently wrong. Correct instinct. But all three wrote it as `if version != 2` — an EQUALITY —
  when what they meant was a FLOOR. **v2 → v3 added the VOLUME column and did not touch a single
  timestamp** (`backtest/data/cache.py`), and these three tools read price and the clock only, so v3
  is strictly better input than the v2 they demanded. They refused it. ⚠ **The refusal MESSAGE was
  worse than the refusal**: it said "version 1 bars are stamped in broker-local time", sending the
  reader off to re-pull 186k bars to fix a bug in one line — a diagnostic reporting on a hypothesis
  rather than on what it actually found. ✅ **The fix is proved, not assumed: `h4_sweep_profile.py`
  re-run on the v3 cache reproduces `docs/H4_SWEEP_STUDY.md` EXACTLY** — pivot reversal @2R, n=145,
  +0.210R gross, $5.75 median stop, **+0.151R net**, every figure identical to the v2-era run the
  doc records. That is the evidence the bump was orthogonal to the clock. **Pin a floor when you
  mean a floor, and ask what a version bump actually CHANGED before refusing on it.**

- ⚠ **`killzone_profile.py` and `killzone_sweep.py` could not find their bars AT ALL from
  2026-08-24 until 2026-09-15.** The bar cache was partitioned by broker server on that date
  (`backtest/data/cache.py::broker_cache_dir`) and neither tool was updated, so both kept
  resolving `backtest/cache/XAUUSD__M15.csv` — a path that stopped existing. ✅ **It failed
  LOUDLY** (`SystemExit: no cached bars at ...`), which is the only reason this is a footnote
  and not an incident: a tool that had instead defaulted to *some* broker's folder would have
  re-reported the KZ1 study against prices that were never involved, cleanly and confidently.
  Both now take `--server` (default `VantageMarkets-Demo`, the backtest-only feed). ⚠ **No
  documented number moves** — the 2026-08-13 KZ1 finding re-runs at **49.0% reversal at +2h,
  −0.088R over 2,034 trades** against the recorded 49.0% / −0.087R / 2,026, the whole difference
  being the ten days of bars the cache has picked up since.

- **`tools/killzone_reversal.py`** — **does price TURN INSIDE a kill zone, and is the turn
  special?** Added 2026-09-15 at Aaron's request: *"price is running in one direction, as soon as
  those time zones come into play, price reverses... it's not directly the candle after, it could
  be somewhere within the zone."*
  🔴 **`killzone_profile.py` COULD NOT ANSWER THIS, and the reason is a lesson about where a
  definition puts its boundary.** That tool measures the leg from 03:00 to the window's **CLOSE**
  and then looks forward, so a turn inside the zone is averaged INTO the leg it fades —
  structurally invisible rather than merely unmeasured. This tool ends the leg at the zone's
  **OPEN** and measures what happened inside it. M5 by default, because the 11:45 zone is 30
  minutes and on M15 that is two candles; the bar count per zone is printed on every run.
  🔴 **THE TURN IS REAL AND IT IS NOT A KILL-ZONE PATTERN.** In the 10:00 hour the 2-hour leg
  into the zone gives back half or more **74.6%** of the time (1,498 qualifying days,
  2018-09-21 → 2026-08-21) — which reads as the pattern until the same measurement runs on every
  other 60-minute window of the day: **08:00-09:00 does it 87.2%, 07:30-08:30 86.5%,
  08:30-09:30 84.8%, 09:00-10:00 81.9%, 09:30-10:30 81.2%.** The kill zone ranks **sixth of 23**
  and is beaten by the entire 07:30-10:30 block. ⚠ **The statistic tracks VOLATILITY, not a
  clock**: the give-back rate peaks where the session is most active, the stop it implies widens
  with it, and that is why the most reversal-prone hour on the board (08:00-09:00) is also the
  **worst** to fade (−0.088R). "Price turns here" was true and load-bearing on nothing.
  ⚠ **At equal distance the reversal is the LESS likely side in every window of the day.** Taking
  the zone's extreme as the stop and asking whether the turn pays one unit of that same risk
  first: **39.2%** in the 10:00 zone, and **no window clears 50%** (range 30.4-48.7%). Both
  mechanical entries sit inside the all-day noise — fading at the zone's close **−0.011R** against
  an all-window median of −0.023R, a reclaim inside the zone **+0.042R** against −0.016R — and the
  reclaim's positive total is **2 of 9 years** (2022 +0.155R, 2025 +0.204R) with five negative. The
  45-minute 13:00 zone is dead centre (−0.025R / −0.004R against medians −0.034R / −0.018R).
  🔴 **ONE METRIC IN THIS TOOL WAS A RULER, AND IT READ 62% BEFORE IT WAS CAUGHT.** "Which came
  first — the leg resumed, or the turn ran on" was first written as *retook the zone's extreme*
  versus *ran past the in-zone counter-extreme*: two thresholds at **different distances** from
  the zone's close. After a deep turn the counter side sits inches away and wins on geometry
  alone, so it reported **62.2% "real reversal"** where the equal-distance version reports
  **39.2%**. ⚠ **A "which happened first" test is a measurement only when both sides are the same
  distance away** — otherwise it measures the ruler, and it will do it confidently.
  ⚠ **No costs, and that is decisive here rather than a formality.** Every figure is gross, and
  the largest of them is the same order as gold's round-trip spread plus commission, so nothing
  in this study survives being charged. A study, never a backtest. Per-day CSVs:
  `backtest/reports/kz_reversal/`.
  🔴 **`--pivots` SETTLES WHY IT LOOKS CRYSTAL CLEAR, AND IT IS THE MOST USEFUL NUMBER HERE.** A
  local swing extreme (6 M5 bars each side) forms inside the 10:00 hour on **85.0%** of days —
  and inside **every** hour of the day at **82.0-87.7%**. Price makes a turn in essentially every
  hour it trades. ⚠ **The claim "price turns at these times" is TRUE, reliable, and carries no
  information**, which is a different and more slippery failure than a claim being false: eyes
  confirm it every single day. ⚠ The 11:45 (55.9%) and 13:00 (76.1%) rows are LOWER only because
  they are 30- and 45-minute windows with fewer bars to contain a pivot — do not read them
  against the 60-minute rows.
  ⚠ **`--grid` exists because a null resting on ONE lookback is weak, and checking Aaron's
  2026-09-08 example by hand proved the point** — the 120-minute leg called the second zone an UP
  move on a day trending plainly DOWN, having caught the first zone's bounce instead of the
  trend. Re-priced at 30/60/120/240-minute legs, 12 cells: 🔴 **the 10:00 zone's reclaim entry is
  the ONE survivor — it beats its own all-day median at every one of the four leg definitions
  (+0.042, +0.022, +0.064, +0.063R above median)**, while the 11:45 zone, one of the two Aaron
  watches hardest, is consistently **worse** than base rate (−0.036 to −0.065R) and 13:00 fades
  as the leg lengthens (+0.045 → +0.004R). ⚠ **Four lookbacks are NOT four independent
  confirmations** — they score largely the same days through the same entry and differ only in
  how the leg is labelled, so read it as one observation that is insensitive to that parameter,
  not as replication. ⚠ **And the absolute number is still ≤ +0.042R gross**, i.e. inside the
  round trip, which is the whole reason this stayed a study: *beats the base rate* and *worth
  trading* are different questions and only the second has a broker in it.
  🔴 **`--scalp` PRICES A DIFFERENT TRADE AND IT MOVED THE ANSWER — the earlier null did not
  apply to it.** Aaron's actual idea (2026-09-15) is a time exit: in at the zone's open, OUT at
  its close, flat inside the hour. Everything above stops at the zone's extreme, targets 2R and
  holds to 16:00. **A null on one exit says nothing about another**, and this one cannot be
  stopped out, so the round-trip cost that was a third of the edge on a tight stop is a rounding
  error against an $8 move. ⚠ **This is rule 11's shape in a study rather than a run**: change
  what a trade is measured on and the number is answering a new question.
  🔴 **THE MOVE IS REAL AND THE SIGN IS NOT KNOWABLE — THAT IS THE WHOLE RESULT.** In the 10:00
  hour (2,039 days): range **median $8.37 / mean $11.93**, reach from the open **median $6.57**,
  open-to-close **median $3.37**. **Knowing the direction is worth +$5.81 a day** ($11,847 over
  the sample). The 2-hour leg predicts it at **±$0.27**. So the problem is 100% the sign.
  ⚠ **"At least 100 pips, majority of the time" does not survive the unit being named** — at
  $0.10/pip that is $10.00, reached by the RANGE on **39.9%** of days and by the open-to-close
  move on **14.8%**. At $1.00 per 100 points it is nearly every day. **Ask which unit before
  quoting this figure** (rule 15); the honest statement is the median range, $8.37.
  🔴 **NINE DIRECTION RULES, ALL REPORTED, NONE WORKS.** Best is *follow* the day's range
  position at **+$0.49/day** (+$0.52 against the same rule's median at every other hour) — which
  captures **8% of the $5.81 on the table at a 50.0% win rate**. ⚠ **Every FADE rule loses and
  every FOLLOW rule wins, monotonically**, so the reversal premise is not merely unprofitable, it
  is **backwards**: at these times gold continues more often than it turns, and fading an
  overextended leg is the single worst cell on the board (**−$0.74/day**). ⚠ The rules read clock
  and price only — no engine — so a negative cannot be blamed on the structure stack, and
  `killzone_sweep.py` has already shown real liquidity levels make KZ1 **worse**, not better.
  ⚠ **What this cannot rule out, and it should be said rather than buried**: Aaron trades this by
  eye in real time. A discretionary read of momentum and candle shape is not in an OHLC bar, so
  bars cannot falsify it — and equally cannot be automated into a bot. That is a statement about
  the limits of the measurement, not evidence for the pattern.

- **`tools/killzone_features.py`** + **`tools/killzone_edge_search.py`** +
  **`tools/killzone_followups.py`** — **does ANY engine, or any rule, know which way the 10:00
  zone will go?** Added 2026-09-15 after Aaron: *"If the money is genuinely there, figure out a
  way to capture it... use all the tools you have... don't come back until you find the pattern."*
  The builder snapshots **12 engines** at 10:00 NY every day (2,038 days) — structure on
  M5/M15/H1, order blocks, liquidity, VWAP, Asia POC, gaps, RSI and divergence, equal highs/lows,
  candlesticks, news — beside the prices that followed. The search tests each as FOLLOW and as
  FADE at six exits. Discovery 2018-2023, confirmation 2024-2026, **$0.14/oz round trip on every
  trade** (ECN: $0.12 spread + $1/side/lot). Pass line fixed before any number was read:
  discovery t ≥ 2.5 AND unseen t ≥ 2.0.
  🔴 **THE ANSWER IS NO, FROM ~340 PRE-REGISTERED TESTS.** Engines: **0 of 240 cells reach the
  bar** — the best discovery t in the whole table is +2.0 (fade the last candle pattern, out at
  11:00), about what six cells clear by luck, and it goes **−0.6** on the unseen years. The
  date-seeded coin flip ranks **#53 of 240**. Followups: **0 of 36** clock-and-price rules
  (`dayturn`), **0 of 24** early-momentum cells (`news`), **0 of 18** daily-trend-filtered cells
  (`trend`). ⚠ 10:00 prints **11.1%** of the day's highs and lows against 10.4% at 08:00 and
  11.6% at 09:00 — **it is not the day's turning point.**
  ✅ **No lookahead, PROVED rather than argued**: the price anchors re-computed from raw bars on
  40 random days, **40 exact**. The snapshot is taken BEFORE the 10:00 bar reaches the M5 engines;
  swapping those two lines is the one edit that would let every feature peek at the move it
  predicts, and nothing else in the table would look wrong.
  🔴 **THE ONE RECURRING SIGNATURE IS A REGIME, NOT AN EDGE.** Every positive cell anywhere in
  this study is a FOLLOW rule that pays on 2024-2026 only — session VWAP followed into 13:00
  (unseen t **+2.7**, discovery +0.5), the first 30 minutes followed with the daily trend into
  11:00 (unseen **+3.2**, discovery **−0.9**). That is gold's trending years. Conditioning on a
  daily trend learned on 2018-2023 — which holds both the 2019-20 trend and the 2021-22 chop —
  **did not recover it.** ⚠ **Never select these off the unseen table**: that is choosing on the
  answers, and it turns the one honest check in the protocol into a second discovery set. **The
  only valid test of a regime hypothesis is FORWARD, on data that does not exist yet.**
  ✅ **What IS real: 10:00 ET USD release days carry the zone's SIZE** — median range **$11.25
  vs $8.85** on quiet days (37.4% vs 32.2% of ADR20; 520 release days, calendar covers
  2021-01-04 on). Size, never sign.
  ⚠ **A significant NEGATIVE on one side of a symmetric bet is usually reading the COST.** Fading
  the first 30 minutes into 11:00 is t −2.5 / −3.3 in both periods while following it is −0.9 /
  +2.1 — both sides pay $0.14 on a 30-minute hold, so the pair sums to two costs, not to a
  momentum effect.
  ⚠ **The feature table is git-ignored** (`backtest/reports/`): rebuild it with
  `python3 backtest/tools/killzone_features.py` (~4 min) before `killzone_edge_search.py` or the
  `news`/`trend` followups. `killzone_followups.py` reproduces the session's scratch figures
  exactly (ported 2026-09-15, every quoted number re-run).

- **`tools/killzone_vwap_retest.py`** — **price retests the session VWAP inside a kill zone: does
  it trade AWAY from it, does higher-timeframe trend help, and which target is best?** Added
  2026-09-15 at Aaron's request. Entry is a resting limit AT the VWAP as it stood after the
  previous bar closed (so no lookahead), direction is the side price came from, stop is `--stop`
  xADR20 THROUGH the VWAP, and the target is swept 0.05-0.50xADR20 plus "no target, out at the
  zone's end". Trend comes from the canonical structure engine on M15/H1/H4/D1, read only from
  higher-timeframe candles that had already closed.
  🔴 **THE BOUNCE ALONE IS A COIN FLIP.** In the 10:00 zone, 801 retests across 2,039 days:
  **50.7%** at equal stop and target (−0.044R), 52.4% out at the zone's end. The 11:45 zone is
  **45.5%**, 13:00 is 47.0%, 10:30-11:00 is 48.3% — against an all-day median near **47%** for the
  same rule. ⚠ **The win% here is deliberately pessimistic** (inside the trigger bar only the stop
  can count, because an excursion toward the target may predate the fill), which is exactly why a
  zone is read against the all-day column and **never against 50%**.
  🔴 **WIN RATE AND MONEY POINT IN OPPOSITE DIRECTIONS — THIS IS THE ROW TO REMEMBER.** Tightening
  the target to 0.05xADR against a 0.10xADR stop wins **60.2%** and is the WORST cell on the board
  (**−0.140R**): it needs 67% just to break even. Expectancy improves as the target widens, to
  0.50xADR, and "out at the zone's end" scores the same. **A hit rate is not an edge — the pair
  (hit rate, payoff) is, and a tight target buys the first by selling the second.**
  ⚠ **Trend confluence does lift it, and the MIDDLE frames carry it.** H1+H4 agreement takes the
  10:00 bounce from −0.040R to **+0.089R** (260 trades, 41.9% win); H1 alone +0.053R, H4 alone
  +0.026R — while **D1 makes it worse (−0.047R)** and M15 adds nothing.
  🔴 **It still fails the protocol.** H1+H4 wins **46.0%** in 2018-2023 and **31.5%** in 2024-2026;
  "all four agree" goes 51.5% → **20.6%** on 131 trades. The all-day control holds hours that beat
  the zone outright (**14:00-15:00 +0.214R** against the zone's +0.089R), and the other three kill
  zones are all negative on the same rule (−0.068R, −0.138R, −0.112R). ⚠ **56 cells were searched
  in one window**, so the best of them is what a search that wide produces by construction.
  ⚠ **The stop is quoted in DOLLARS as well as in ADR, because the same rule is not the same stop:**
  median **$2.31** over the sample, **$0.98 in 2018** and **$8.27 in 2026**. The $0.14 round trip is
  ~14% of the 2018 stop and ~1.7% of the 2026 one — a cost that is negligible today was material at
  the start of the sample, and an R figure averaged across both hides that.
  ⚠ **It contradicts `killzone_edge_search.py`'s regime note in DIRECTION** — there the follow rules
  paid only in 2024-2026, here the trend-aligned bounce paid only before it. **Two tests disagreeing
  about the same years is a reason to trust neither.**
  🔴 **`--sweep-stops` SWEEPS THE STOP TOO, AND IT IS SCORED IN ADR RATHER THAN IN R — that unit
  change IS the reason the flag exists.** Added 2026-09-15 because everything above assumed ONE stop
  size, which made the whole table a claim about a stop nobody had tested. **One R *is* the stop, so
  reading R down a column of seven different stops compares seven different units and hands the
  widest stop a better number for free.** A share of the day's range is one unit in every cell and
  in every year of a sample where gold tripled. ⚠ **No figure recorded above moves** — every
  committed number re-ran identically (801 retests, 38.6%/60.2%/50.7%, −0.044R, H1+H4 +0.089R), and
  the flag only adds a grid. R is still reported for a single stop against its own targets, and is
  **`None` without a stop** rather than 0.0.
  ⚠ **THE 0.10xADR STOP THIS STUDY USED THROUGHOUT WAS TOO TIGHT, AND THAT IS THE ONE ACTIONABLE
  RESULT.** Win% rises monotonically with stop width and the extremes are far apart: at a 0.5xADR
  target the 0.05xADR stop wins **24.6%**, 0.10 wins 38.6%, 0.20 wins 47.9%, 0.50 wins **52.3%** —
  and no stop at all wins 52.4%. A 0.05xADR stop is ~**$1.16** at the sample's median ADR (median
  scales linearly off the measured $2.31 at 0.10xADR), which is inside gold's 5-minute noise, so it
  is not risk control — it is a coin flip charged $0.14 a go.
  🔴 **WITHOUT A TREND FILTER ALL 49 STOP x TARGET COMBINATIONS LOSE**, from −0.31% to −1.47% of a
  day's range. It is the cleanest negative this study produced: the bounce does not become tradeable
  at any stop, at any target.
  ⚠ **With H1+H4 agreement the widest corner goes positive — and it fails both protocol checks.**
  Best cell is stop 0.5xADR + target 0.5xADR: **57.7% win, +1.30% of a day's range, +$0.25/trade**
  on 260 trades. It scores **+2.81% in 2018-23 and −2.56% in 2024-26**, and all EIGHT top cells flip
  the same way without exception. The all-day control on that same cell is median 51.2% / +0.04%
  over 22 windows, **but its BEST window scores +1.57% — beating the zone's +1.30%.** The other
  three kill zones are −0.52%, −1.03% and −0.36%.
  ⚠ **Those top cells are also the SAME TRADE wearing different labels, and the table says so
  itself:** the 0.5xADR stop column reads within 0.4pp of the no-stop column and the 0.5xADR target
  column equals the zone-end column, because a half-ADR excursion is rarely reached inside a
  one-hour window. Four of the top eight are therefore one strategy — in at the VWAP, out at the
  zone's end — counted four times. **A leaderboard whose top rows are aliases of each other looks
  like corroboration and is not.**
  🔴 **THE ROW TO SHOW SOMEONE SELLING A WIN RATE: no stop + a 0.05xADR target wins 79.2% and
  LOSES money (−0.22%).** Same window, same trades, same filter as the +1.30% cell. **154 cells were
  searched in this one window**, ~550 across the whole kill zone study, so the best of them is what
  a search that wide produces by construction. **Recorded NEGATIVE — nothing here is tradeable.**

- **`tools/bos_sweep.py`** — ⚠ The Pine it is measured against is `strategies/tradingview/bos_strategy.pine`.
  It has moved TWICE and a path from before either date is stale: on 2026-08-13 the `.pine` sources
  were split by their DECLARATION into `indicators/strategies/` and `indicators/engines/`, and on
  2026-09-02 the `strategy(` half left `indicators/` altogether for `strategies/tradingview/`.
  **Comment-only — no documented baseline in this file moves and no stored run re-prices.**
  🔴 **DO NOT QUOTE ITS NUMBERS. FALSIFIED 2026-08-07, the day it was
  written.** On the same symbol, timeframe and window, with the config confirmed identical by the
  Pine's own `[CFG]` echo, this tool reports **20 trades / 80% win / PF 2.97 / +102.5%** where the
  TradingView Strategy Tester reports **24 trades / 66.67% win / PF 1.043 / +5.01%**. The Tester is
  the ground truth. **Entries roughly agree; the EXIT LADDER does not** — this model extracts far
  more from its winners than the Pine does. It is kept because its METHOD is sound and reusable
  (matched drawdown budgets, paired jitter, resolvable-stop screening, matched random controls) and
  because fixing it is cheaper than rewriting it. **Every result must be treated as unverified
  until `compare_bos.py` is green.** See `docs/BOS_OPTIMIZATION.md` → Run 8.
  ⚠ **Its own docstring warned it was a model rather than the strategy, and that was not enough** —
  a table of numbers reads as a finding whatever caveat sits under it. The check that falsified it
  was ONE Strategy Tester run, available the entire day it went unrun.
  Added 2026-08-07; it chose that file's current defaults (Run 7 in `docs/BOS_OPTIMIZATION.md`), and it
  exists so that answer is reproducible rather than asserted. Stdlib only, same as `trigger_edge.py`,
  and it reuses that tool's `drop_coarse()` reasoning. Modes: `sensitivity` (one lever at a time),
  `frontier` (the cartesian, ranked at a matched drawdown budget), `settle` (paired jitter
  head-to-head). ~35,000 configurations over 186,384 M15 bars; `frontier` takes ~40s on 12 cores.
  ⚠ **It models ONE POSITION SLOT, because the Pine is a `strategy()`.** Scoring setups
  independently counts trades the strategy could never have taken and lets a winner and the trade it
  would have blocked BOTH score — the queue effect this repo has now measured three times, and twice
  the cheap estimate had the SIGN wrong.
  ⚠ **It charges spread AND swap per night held**, and swap keeps MT5's sign, so gold's short-side
  CREDIT stays a credit. A strategy that holds overnight cannot be ranked without it.
  🔴 **Its load-bearing output is not the R column — it is the TIGHTEST-TENTH STOP printed beside
  every row.** R = profit / stop, so a stop model that produces small stops inflates every R in the
  book without one extra dollar being made. The first leaderboard this tool ever produced was
  entirely configurations with a **median 74-cent stop** reading +250R to +450R, on an instrument
  whose spread is $0.22 — numbers a 15-minute bar cannot even resolve, since inside one bar price
  crosses that spread constantly. **Ranking on R alone cannot see this. Never rank a stop model on R.**
  ⚠ **Configurations are compared at a MATCHED DRAWDOWN BUDGET** (`risk_for_dd`), not at equal risk:
  summing R treats a 25R drawdown as three times worse than an 8R one, when at 10% risk it is the
  difference between giving back 30% and giving back 93%. It is the only way a 55-trade book and a
  600-trade one can be ranked together.
  ⚠ **That budget metric is NOISY — a factor of two across jitter seeds on one configuration** — so
  `settle` scores every finalist on the SAME jittered series and compares pairwise. Unpaired medians
  had the old and new defaults tied (42.8x vs 42.3x) purely because the real price series is unlucky
  for one and lucky for the other; pairing separated them 32-8.
  ⚠ **Two look-ahead traps are deliberately avoided and both were made and caught here**: the VWAP
  side is read off the PREVIOUS closed bar (reading it off the fill bar's own close selects bars that
  recovered — worth a fake +9%), and the FILL BAR MAY NOT STAGE THE STOP, which is
  `BUG_exit_fill_price_mismatch`.
  ⚠ **It is a MODEL of the Pine, not the Pine.** No `compare_bos.py` exists yet, so nothing here has
  been diffed against the strategy's own decision stream. Read its results as a strong prior.

- **`tools/realign_control.py`** (2026-09-15) — is the Realign SETUP better than entering at a
  random moment? Every other Realign figure says what the strategy made; none of them says whether
  the PATTERN did it. A ladder, a stop geometry and a drifting instrument can make money from almost
  any entry — Run 1 of `realign_optimization.md` found exactly that on the 5-minute-only arm, where
  random entries at the same months and hours BEAT the pattern's own.
  🔴 **It replays the REAL `RealignStrategy` through the REAL `RealignExecution` and swaps only the
  TRIGGER**, via a scripted tracker injected at `strategy.tracker`. Entry placement, %-risk sizing,
  the three-stage stop, the runner trail, the time stop, flat-by-close, the cost profile and the one
  position slot are all the shipped code, so the two arms differ in exactly one thing. **The obvious
  build — walk the finished trade list and re-simulate random entries — has to re-derive the exit
  ladder, and then the arms differ in TWO things and the comparison is worthless.**
  ⚠ **Each control trigger keeps the real one's side, calendar month, New York hour, stop distance,
  target distance and retest offset. Only the MOMENT is random.**
  ⚠ **Geometry is captured from the run's own state stream, not from its trades** — a control
  matched only on TAKEN trades never faces the triggers the position slot was busy for, which is an
  easier problem than the strategy solves.
  ⚠ **Control trade counts are REPORTED, never assumed equal**: with one slot a randomly-timed setup
  displaces whatever real setup came next, so the counts legitimately differ.
  ⚠ **`z` here measures distance from the spread of the CONTROL REPS** (does the pattern beat random
  timing), which is NOT the strategy's own standard error (is the edge distinguishable from zero).
  Both are printed so they cannot be confused. Read-only: it writes nothing and moves no baseline.

- **`tools/realign_inverse.py`** (2026-09-17) — Aaron's question: Realign loses most of its trades,
  so why not take the OPPOSITE side? **Answered: no, and the free-book mirror WINS 74.7% of its
  trades while losing money**, which is the whole lesson. Flipping the trade flips the PAYOFF too —
  the inverse risks the old target distance to win the old stop distance, so it wins small and often
  and loses big and rarely.
  🔴 **It reuses `realign_control.py`'s scripted tracker at the same `strategy.tracker` seam**, for
  the same reason that tool gives: every mirrored trigger goes through the shipped sizing, ladder,
  trail, time stop, costs and one position slot, so the arms differ in exactly one thing. Do not
  build a second exit ladder here.
  ⚠ **Two arms answering two different questions.** MIRROR is the honest inverse — same bar, side
  flipped, **stop where the target was and target where the stop was** — so its R is measured
  against a different risk distance and is NOT the real book's R negated. SIGN-FLIP is `sum(-R)`
  over the real book: untradeable, but it is the CEILING of the idea, so its losing settles every
  weaker version.
  ⚠ **Mirrored trade counts are lower than real ones** (83 against 113 of 219 triggers): the flipped
  stop is far away, the trade holds far longer, and the single slot refuses more triggers.
  ⚠ **Market entry only** — a mirrored trigger has no retest level to rest at, and the tool REFUSES
  a retest config rather than inventing one. Read-only; it moves no baseline and is wired to no bot.
  Numbers and the asserted control: `strategies/python/realign/realign_optimization.md` → Run 14.

- **`tools/realign_trade_profile.py`** (2026-09-16) — do the Realign losers have anything in common?
  Buckets the trades by every feature knowable AT ENTRY (side, New York hour, weekday, reward:risk,
  stop size, retest depth) and by exit reason, with win/loss/scratch counts. **Answered: no.** Median
  reward:risk is 2.20 for winners and **2.25 for losers**; stop size, stop %, and retest depth do not
  separate them either.
  🔴 **It reprints every table with the SINGLE BIGGEST TRADE REMOVED, and that half is the point.**
  This book has 3-5 trades carrying 5.5 years, so one trade lands in one bucket of every table and
  makes that bucket look like a rule. MEASURED: shorts (+28.36R vs longs +9.67R), Mondays (best day,
  avg +1.076), the 3-5 R:R bucket (best, +1.206) and sub-$5 stops (best, +1.538) ALL looked like
  strong signals and were **all the same +22.56R trade** — a Monday 01:00 NY short, 4.66 R:R, $4.50
  stop. Without it, shorts fall behind longs and Monday goes from best day to WORST (-2.13R).
  ⚠ **A bucketed claim on any fat-tailed book here is not believable until it survives that
  removal** — the generalisation, not a Realign quirk.
  ⚠ Read-only; writes nothing and moves no baseline. Anything it surfaces is a hypothesis needing a
  REPLAY and its own pre-declared window, never a filter applied by dropping rows.

## `gbpjpy_travel_test.py` — does a strategy TRAVEL to another instrument? (2026-09-17)

Runs one config on two instruments with costs ON and OFF, and prints the four-way table. Written
for Run 37 (`strategies/python/sos_fade/sos_fade_optimization.md`) and kept so that result can be
re-run rather than believed.

🔴 **The two controls are the point, and a run without them answers nothing.**

1. **The same untuned config on the ORIGINAL instrument.** Without it, a loss on the new pair is
   indistinguishable from a broken baseline. Run 37's baseline makes +72.30R on gold, which is
   what turns "it loses on GBPJPY" into "the setup does not travel".
2. **Costs OFF.** Without it, a loss is indistinguishable from a cost-model problem. GBPJPY lost
   18.73R on a frictionless book, so no broker, spread or swap change could rescue it.

⚠ **An in-sample loss needs no walk-forward** — you cannot overfit your way *to* a loss. Reach for
out-of-sample when a result is POSITIVE.
