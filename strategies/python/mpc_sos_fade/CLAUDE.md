# CLAUDE.md — strategies/python/mpc_sos_fade/ (the MPC SOS Fade bot)

**Purpose:** The MPC SOS Fade strategy in Python — a line-for-line port of the A+ block +
execution layer in `indicators/mpc_strategy.pine` (Aaron's brother's "MPC-JARVIS" script). It reads
the canonical engine stack's per-bar output and turns the A+ sequence into trades.
**Scope:** This strategy only — its state machine, order logic, config, and parity harness. It does
NOT own the engines (`engines/`), the replay runner (`backtest/`), or the lab (`command-center/`).
**Status:** Built + unit-tested + **logic-parity GREEN (exit 0) 2026-07-16** on a full-history
`VANTAGE_XAUUSD, 5m` export (20,076 bars, `compare_strategy.py` with no warmup — the export starts at
bar 0). Bar-for-bar identical decision stream vs `mpc_strategy.pine`. Runs real-tick fills + costs
(`fill_model="tick"`), and is registered in the command-center lab as `runner="python"` (see
`LAB_STRATEGY` in `__init__.py`) — risk % is editable in the Run modal. 51 offline tests green.
**RE-VALIDATED GREEN 2026-07-22** after the Pine changed (SOS-aware veto + `execConfSZ` + CONT
removal): the export was regenerated, the veto was ported, and `compare_strategy.py` matches Pine's
decision stream on a fresh 19,863-bar `VANTAGE_XAUUSD, 15m` grand export — every `px_dec_bits` /
`px_stages` / `px_edge` / `px_entry_price` bar-for-bar, one lone 25-cent `px_exit_run` difference on
a single Nov-2025 runner (an intrabar trail-fill guess, not a decision). See `## The 2026-07-22 re-sync`.
**Open question — sample size, NOT correctness:** the validated 365d 15m run is only 22 trades (2yr:
40), and the runners alone make >100% of the net in both windows. Read `## The 2026-07-16 year run`
below before trusting any tuning done against it.
**Last reviewed:** 2026-07-22

---

## The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)

`MPC` = Mental Peak Consulting (Aaron's brother's company) and prefixes every strategy in the
house. The suffix names the **narrative** the strategy trades off the shared `engines/` — here:
a **shift of structure (SOS)**, faded. The old name described the *grade filter* it happens to
use, not what it does, and "A+" would collide the moment a second MPC bot also traded A+ setups.

**"A+" is still correct vocabulary and is deliberately kept** wherever it names the brother's own
Pine concept — the A+/B/C/D grade dropdown, the "A+ SETUP SEQUENCE" block this ports, and the
`aplus_window` config field (which mirrors the Pine input "Max Time: Sweep → SOS (minutes)" and is
a lab param-grid key). Renaming those would break the line-for-line traceability to the Pine, and
`aplus_window` is also an optimizer grid key. The Pine files themselves are NEVER renamed: they are
the brother's source and the parity reference.

## Sizing — this bot sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True`, so the command-center lab does NOT run its dynamic
sizing engine over this bot's trades. `exec_risk_pct` (Pine default **10%** per trade) IS the risk
knob: it is a normal strategy param, so it is editable in the Run modal and sweepable in the
optimizer grid — that is the "manual %" for this strategy, and the SIZING MODE control is hidden
because there is nothing for it to decide. Pair a run with the **Unconstrained (No Limits)**
ruleset to see the raw behaviour with no halts and no drawdown floor cutting a day short.

## The portfolio-account seam (2026-07-17)

`Execution.__init__` takes an injected `account` (default `SoloAccount`) and a `leg` name — the seam
for stacking this bot with others on ONE shared account (`backtest/portfolio/`). What changed:
`self.equity` now reads `account.balance` (the shared balance the bot sizes against); the leg-local
`_equity_realized` is kept for R. The fill gate in `_open_position` calls `account.request_fill`,
which **scales** the bot's own desired qty to the shared room (solo → full size); partial exits and
costs `book_pnl` onto the shared balance; the full close frees the reservation; each bar reports the
live stop via `update_stop`. **Parity is unchanged:** a `SoloAccount` grants full size always, so
`compare_strategy.py` stays exit 0 — re-verified on the 20,076-bar export after the seam landed. The
account scales the bot's qty rather than recomputing it precisely so parity holds (the bot sizes off
the limit price at placement, not the fill). Do not route qty computation through the account.

## What it is (one paragraph)

A counter-trend reversal that fades exhaustion at HTF liquidity. Three-stage A+ sequence: **Arm**
(liquidity sweep by default, or an RSI divergence) → **SOS** (a same-side external structure break in
the trade direction, inside a staleness window) → **Zone+FVG** (price retraces into the 0.5–0.886 fib
band and a live FVG overlaps it; default requires the gap fully past 0.5). Entry is a resting limit — a
deep gap re-prices to the nearest shallower fib (Method 3), else the FVG's near edge, clamped into the
band; stop = fib 1.0 (leg origin) + buffer; exit = the fib TP ladder (30/40/runner) with stop→BE on
TP1, stop→TP1 on TP2, and a ratcheting trail on the runner. Full rules: `docs/MPC_SOS_FADE_SPEC.md`.

## The five modules (the data flow)

```
BarState  --SignalAdapter-->  Signals  --SosFadeSequence-->  SeqState  --Execution-->  Decision
(backtest.replay)             (Pine-named inputs)          (A+ stages)               (orders + fills + R)
```

- **`config.py`** — `SosFadeConfig`: every trade-affecting Pine input toggle, same name + default
  (**toggle parity is a hard requirement**). Instrument facts (mintick, point value, close time) are
  Layer-B injections, also here. Cosmetic Pine inputs (debug labels, boxes, table styling) are
  deliberately absent — they don't touch a trade decision.
- **`signals.py`** — `SignalAdapter`: turns a replay `BarState` into the exact Pine-named globals the
  A+ block reads. Two reconstructions are non-trivial and must stay faithful:
  1. `recentSSL` / `recentBSL` — the most-recent swept pool per side, from ten per-source slots
     (H4 / Day / Asia / London / NY high & low) resolved by latest sweep bar, sessions suppressed
     once Day is filled. Rebuilt from the liquidity engine's `mitigated` / `evicted` events.
  2. `bullDivActive` / `longVeto` — recomputed WITH the structure-break staleness (`lastExtBreakBar`)
     the standalone RSI engine can't see. **Do NOT use the RSI engine's convenience `bull_active`** —
     it omits the stale check and would diverge from the Pine.
- **`sequence.py`** — `SosFadeSequence`: the Stage 1→4 state machine, retro-link (a late-confirming
  divergence adopting an SOS that already fired), sequence death (opposite SOS / TP3 / invalidation /
  continuation BOS), and the arm-source snapshot (which Stage-1 source was live at the SOS).
- **`execution.py`** — `Execution`: entry edge → resting limit → TP1/TP2/runner ladder → staged stop
  + ratchet → %-risk sizing → graded R, on a small broker emulator (`_Broker`-style) that reproduces
  the two TradingView fill assumptions logic parity depends on:
  1. **calc-on-close, one-bar delay** — an order placed at a bar's close is active only next bar (a
     resting limit never fills the bar it was placed; an exit never fills the bar the entry filled).
  2. **intrabar path** — when a bar covers both a TP and the stop, the open's proximity to the
     extremes decides which fills first (open nearer high ⇒ price travels open→high→low→close ⇒
     targets first; nearer low ⇒ stop first). **This is the single most parity-sensitive assumption
     — it is a GUESS until `compare_strategy.py` is exit 0.**
  Each closed `Trade` also carries **reporting-only excursion** — `mfe_usd` (favorable: the most it
  ever showed in profit) and `mae_usd` (adverse: the deepest it sat against us), tracked across the
  whole hold on bar high/low (`_ext_high`/`_ext_low`) and converted to USD at close. NO decision
  reads them, so they are parity-safe (`compare_strategy.py` diffs the `px_*` decision stream, not
  `Trade`); they flow through `backtest/output.py` to the lab's equity-chart excursion overlay.
- **`strategy.py`** — `MpcSosFadeStrategy`: the driver. `run(df, warmup=…)` replays a canonical frame
  end-to-end; `step(bar_state)` does one bar. Collects `.decisions` (the per-bar stream) and
  `.execution.trades`.
- **`secondary.py`** — the 1m sniper re-entry (below). `Structure1m` (1m structure feed, port of Pine
  `f_struct1m`) + `SecondaryArm` (the latch/arm, port of Pine `f_secArm`). Consumed by `run_dual`.

## Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, NOT committed)

The 1-minute re-entry Aaron prototyped in Pine, built as the *exact* version here (Pine can only
sample the 1m engine once per 15m bar — its own tooltip says "the exact version is the Python port").
**Full rules + design: `docs/MPC_SOS_FADE_SECONDARY.md`.** One paragraph: after the **primary** 15m
A+ trade on a leg has traded and gone flat, while the 15m div + SOS are still live and price is back
in the 0.618-0.886 zone, a **1m shift of structure** in the trade direction rests a limit at a 38.2%
retrace of that tight 1m leg (stop = 1m leg origin; TP1/TP2 = 15m 0.5/0.382; runner = TP3). One
re-entry per 1m leg; a re-entry is never the first trade on a leg.

- **`run_dual(df15, df1m)`** merges the two streams on a close-time clock: the **primary** is stepped
  on 15m bars exactly as `run(df15)` (so parity is untouched); the **secondary** latches/arms/fills/
  manages on real **1m** bars — the sniper "in and out fast" a 15m bar can't express.
- **Execution** grows an `_entry_kind` tag + `step_secondary(bar1m, arm)`. A 15m bar only ever
  touches a `primary` position; a 1m bar only a `secondary`. They share the one position slot but
  never the same trade (the secondary arms only when flat), so the tag is all that separates them.
  With `exec_secondary` OFF, no secondary ever opens, so `step()` is byte-identical to before.
- **NO Pine parity gate** — the Pine is only the approximate version, so this is verified **visually**
  (the lab price chart + the 15m→1m drill-down). The offline guard is
  `test_run_dual_primary_is_identical_to_run_when_secondary_off` + the hand-traced arm/exec tests in
  `tests/test_secondary.py`, and OFF parity was re-confirmed on the real M15/M1 cache (`run` ==
  `run_dual`, 40 trades byte-identical). `compare_strategy.py` (which runs `run`, not `run_dual`)
  stays the primary's gate.
- **Sparse-data note:** the secondary is rare (a live leg + zone + a 1m SOS + div, all at once). Over
  the ~4 days of local 1m cache it fired 0 times — expected, not a bug (see the arm trace). A real
  visual verification needs a longer 1m window (broker serves ~35d direct; older via ticks).

## Deliberate deviations from the Pine (per the framework)

All OFF for the parity check (to match the Pine); each is a real-run choice:
1. **Flat-by-close** — force-flat + no new entries N minutes before the daily close (`flat_by_close`).
   **Default False, and measured 2026-07-16: leave it that way.** A/B over 6.5 months: OFF $39,454 /
   PF 1.444 vs ON $19,813 / PF 1.253 on the same 32 trades. Only 4 trades ever held overnight, they
   were all winners, and they made 70% of the profit; total swap for the period was −$36.80. Flatting
   early buys a smaller drawdown for half the profit. (This param was DEAD CODE until 2026-07-16 —
   `_in_flat_window` read only `sig.ny_hour`, so "minutes left" was always a multiple of 60 and never
   hit the ≤15 window. Any A/B run before that date compared a flag against itself.)
2. ~~**Sizing** — real runs swap in the dynamic sizing engine under a ruleset.~~ **No longer true
   as of 2026-07-16:** the bot declares `self_sizing: True`, so real runs keep the Pine's own fixed-%
   sizing (`exec_risk_pct`) and the engine never re-sizes them — this is NOT a deviation any more,
   parity and real runs size identically. See `## Sizing — this bot sizes ITSELF` above.
3. **Fill model** — parity REQUIRES `fill_model="bar"` (the Pine's own intrabar guess, zero costs).
   Real runs set `fill_model="tick"` + `account_profile` + `symbol` for real bid/ask fills and costs.
   See `backtest/CLAUDE.md` A2 — tick mode disagreeing with the Pine is correct, not drift.

## Engine-construction pins (`MpcSosFadeStrategy.engine_config`)

Two engine inputs are NOT in the decision stream, so the bot pins them to the Pine STRATEGY's own
input defaults rather than the shared engine defaults — miss either and the fib the bot reads drifts:
1. **`fvg_max_count=7`** — `mpc_strategy.pine` sets Max Active FVGs to 7 (the FVG engine default is 6);
   a smaller cap evicts the oldest gap one bar sooner and drops an entry edge Pine still holds.
2. **`show_internal=False`** — the Pine's "Show Internal Structure" input defaults OFF, and Pine gates
   the ENTIRE internal block behind it (`internalActive = showInternal`), so `i_confirmed_*` is never
   set and the **Structure fib never adopts a more-extreme internal swing** as its anchor. The
   `market_structure` engine ALWAYS computes internal structure, so the `EngineStack` must be told to
   suppress the internal-derived snapshot fields (it blanks `i_confirmed_*` + `ifib_seed_*` when this
   is off). This is a real "a drawing toggle changes trade logic" coupling in the Pine — do not drop it.

## The three parity fixes (2026-07-16) — read before touching signals/fib

The port went green after fixing three faithful-translation gaps; each is a class of bug to watch for:
1. **Internal-swing adoption** (the `show_internal` pin above) — the engine's always-on internal
   structure fed the fib an anchor the Pine strategy never had (internal display off).
2. **Sweep double-count at the daily/session rollover** — Pine records a sweep on `d_lMit and not
   d_lMit[1]` (a bar-to-bar edge of a persistent VARIABLE). When a daily/session/H4 level rolls at
   18:00 and is re-taken on its own creation bar, `d_lMit[1]` (the old level, already swept) is still
   true, so no edge fires. The engine models levels (create / mitigate / EVICT) and the naive
   reconstruction latched on every `mitigated` event, re-recording the rollover sweep — which made a
   stale sweep look fresh and armed a trade Pine didn't. `signals.py` now reconstructs the Pine
   variable: reset on `created`, set on `mitigated`, **left alone on `evicted`**, edge vs the prior bar.
3. **The forming last bar** — TradingView exports the final (still-forming) bar's plotted series as
   NaN. `compare_strategy.py` now marks that bar `_px_present=False` and skips it, instead of reading
   `fillna(0)` as a real "stage 0" and flagging a phantom mismatch.

## The parity gate — `tools/compare_strategy.py` + `/audit-strategy`

The standing regression harness (same pattern as the engines' `compare_*.py`). `mpc_strategy_export.pine`
(in `indicators/`) = `mpc_strategy.pine` + an appended block that plots the per-bar decision stream
(`px_*`) and every toggle (`cfg_*`). Export it to CSV on a 5m XAUUSD chart; `compare_strategy.py` reads
the toggles, configures the bot identically, replays the same bars, and diffs the decision stream. Exit
0 = bar-for-bar identical. On a mismatch it names the first diverging bar + field. Run it via
`/audit-strategy`, or:
```
command-center/backend/.venv/bin/python strategies/python/mpc_sos_fade/tools/compare_strategy.py <export.csv> --warmup N
```

### The 2026-07-22 re-sync (the export was 7 days stale)

`mpc_strategy_export.pine` was last regenerated 2026-07-15 and had drifted on three trade-affecting
Pine changes, so any diff it produced was July-15 drift, not a bug. Regenerated from
`mpc_strategy.pine` @ `361f007`:

1. **The veto is now SOS-aware** (Pine `longVetoA`/`shortVetoA`, ~3701). A divergence printing AFTER
   the SOS no longer vetoes its own setup — once stage 2 is live the setup is waiting on a retrace,
   and an opposing divergence formed during that retrace IS the pullback. Only one already live at
   or before the SOS bar still blocks. Extreme RSI keeps blocking LIVE. **Ported here**: the veto
   moved out of `SignalAdapter.update()` (which has no sequence state) into `signals.sos_aware_veto()`,
   which `execution.py` and `secondary.py` both call. `Signals` now carries the veto PARTS
   (`veto_on`, `veto_rsi_ob`, `veto_rsi_os`) instead of the finished `long_veto`/`short_veto`.
   The old, stricter rule is why a lab run can miss a long TradingView took.
2. **`execConfSZ`** — "Allow Sniper Zone as entry confirmation", a second accepted entry
   confirmation alongside the FVG. **NOT ported.** `config.exec_conf_sz` exists (default False) and
   the export packs it as `cfg_bits` bit 4096, so `compare_strategy.py` REFUSES an export taken with
   it on rather than diffing against logic this bot lacks. Port = read `BarState.sniper`'s
   0.5-0.618 pocket as an entry edge on any leg with no qualifying FVG.
3. **CONT trades removed** from the Pine — the export used to carry `contL_ok`/`contS_ok`.
4. **`execDeepFib`** (Method 3, added 2026-07-23) — "Entry: deep gap enters on nearest fib (not gap
   edge)". A qualifying FVG whose NEAR edge (long = gap top, short = gap bottom) sits deeper than
   0.618 rests its limit at the nearest fib just SHALLOWER (0.618/0.702/0.786) — the level price
   reaches first — instead of chasing a gap edge price may never tap. **PORTED here**: `config.exec_deep_fib`
   (default **True** as of 2026-07-23 — see the prime-combo defaults note below), `execution._deep_fib_edge()`
   + the override in `_entry_edges()`, the export packs it as `cfg_bits` bit 8192, and `compare_strategy.py`
   reads it (no refusal — it is fully ported). ONLY the near edge's position decides it; what the gap body
   crosses is irrelevant (an earlier "body contains a level" gate was WRONG and dropped exactly the deep
   multi-level gaps this targets).

**Prime-combo defaults (2026-07-23).** Aaron's TradingView-tested "prime" settings are now the shipped
defaults in BOTH Pine files and `config.py`, in lockstep so `compare_strategy.py` parity holds:
`exec_arm_sweep` False→**True**, `exec_arm_div` True→**False** (arm on liquidity sweeps, not divergence),
`exec_fvg_deep_only` False→**True**, `exec_deep_fib` (new) → **True**. `exec_req_fvg` stays True. Combo
result on Aaron's Strategy Tester: ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2yr gold at 84 trades.
This SUPERSEDES the old divergence-armed default — the "2-year run" analysis further down was measured
under that old default and predates Method 3 + deep-only; keep it as the historical baseline only.

**Slippage pinned to 0 in the Pine (2026-07-23).** Both `mpc_strategy.pine` and `mpc_strategy_export.pine`
now declare `slippage = 0` in the `strategy()` call, so the TradingView Properties tab defaults to zero
instead of Aaron's old 25-tick setting. Reason: for HONEST parity the Pine's `fill_model="bar"` (zero
costs) must line up with a TV run that also charges nothing, so `compare_strategy.py` and a hand
trade-diff compare like-for-like. Real costs belong in the LAB's `fill_model="tick"` run (real bid/ask +
spread + slippage + commission + swap), not smeared as a flat 25-tick charge on every TV fill. The
breakeven buffer (`execBeBufTk`, default 30) is a STRATEGY input and is unchanged — it is signal logic,
not a cost. So the old note that TV's number is "slightly PESSIMISTIC because TV charges 25 ticks" no
longer applies to a fresh export: at slippage 0 the TV bar-mode number and our bar-mode number are the
honest apples-to-apples pair; the tick-mode lab run is the real tradeable number.

**When the Pine changes:** brother re-pastes `mpc_strategy.pine` → regenerate `mpc_strategy_export.pine`
(re-copy + re-append the parity block) → re-export → re-run until exit 0. A new trade-affecting input =
a new `config.py` field + a new `cfg_*` plot + a new `compare_strategy._TOGGLE_COLS` entry.

**One-shot sync check:** `backtest/tools/verify_parity.py <export.csv> [more.csv ...]` runs EVERY parity
check (all nine engines + this strategy) whose columns are present in the CSV(s) and prints one
GREEN/RED/SKIP table with auto-detected cold-start warmup. It is the "is everything in sync?" command
to run after any re-paste; it reports drift, it does not fix it (a real logic change is still a hand
port). Engines are the foundation — sync them first (`/audit-engines`), then this strategy.

## LOGIC parity vs RESULT parity — two different tools, two different questions

`compare_strategy.py` answers "is our CODE the Pine's code?" — it replays TradingView's OWN bars and
diffs the per-bar `px_*` decision stream, so the data feed is out of the equation. That is the gate.

`tools/compare_trades.py` answers a different question: "why does a LAB RUN's finished trade list
differ from what I got in the TradingView Strategy Tester?" It pairs the two trade lists by entry TIME
(not price — different brokers legitimately differ by cents on the same bar) and reports matched /
TV-only / ours-only. **It is a diagnosis tool, not a parity gate** — a diff here is usually the DATA
FEED, not the code (proven 2026-07-22: run `f455b21faabe` came in ~110% vs TradingView's 142%; the whole
gap was two longs Vantage's wick swept a level our PU-Prime feed's wick fell ~10 cents short of, so the
sweep never armed. `compare_strategy.py` was green on TradingView's bars, i.e. our code took both those
longs on Vantage data — the lab missed them purely on the feed). Two counting conventions also confuse
the comparison and are NOT bugs: TradingView counts each TP rung as its own "trade" (41 positions × 3
rungs = 123) and its max-DD % is vs peak equity where ours is vs starting capital. Usage:
`compare_trades.py <tv_trades.csv> <run_id>` — `--tz` defaults to `Etc/GMT+4` (the Vantage XAUUSD chart
is a FIXED UTC-4, no US DST); it prints a hint if the median pairing offset says otherwise.

## The 2026-07-16 year run — what the numbers actually say

365d, 15m, XAUUSD.s, `exec_risk_pct=10`, $10k start. Both fill models, same 22 trades:

| | bar (Pine guess, no costs) | tick (real bid/ask + costs) |
|---|---|---|
| net | $11,525.41 (115.25%) | **$11,374.78 (113.75%)** |
| PF | 4.426 | 4.228 |
| win% | 72.73% | 72.73% |

Real fills cost 1.3%; **0 bars fell back to the guess**, so every fill is a real tick. TradingView's
110.19% on the same setup is slightly PESSIMISTIC, not optimistic — TV charges a flat 25 ticks of
slippage on every fill, and the real broker is better than that (the entry is a resting limit, which
never slips; only stops pay).

**TradingView's 66 trades = our 22.** Each `strategy.exit` leg (TP1/TP2/runner) is a separate closed
trade in TV's stats: 22 × 3 = 66 exactly, and the filtered 16 winners × 3 = 48 exactly. Net / return /
drawdown mean the same thing in both; **profit factor and average-trade do NOT** — splitting one
winner into three legs changes the ratio (TV 4.155 vs the real 4.426). Don't compare those two.

**The distribution is the real story** (`|R| < 0.25` = scratch):

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner (TP1+TP2 banked) | 8 | +12,510 | **110%** | 1.19 |
| TP1 only, rest stopped at BE | 8 | +2,389 | 21% | 0.19 |
| never reached TP1 | 6 | −3,524 | −31% | −0.42 |

The 72.73% win rate is arithmetically right and analytically misleading: **10 of the 22 trades are
near-scratch** (together +$749), six of the eight "TP1 only" winners made under $300, only 2 trades
lost a full R (the stop→BE rule converts most losses to scratches), and the **top 3 trades are 57% of
net**. The edge is the runner. Treat the win rate as a byproduct of the BE stop, not as the edge.

### The 2-year run (2024-07-16 → 2026-07-16, tick mode) — the shape HOLDS

> **⚠️ Pre-combo baseline (superseded 2026-07-23).** Everything in this subsection was measured under
> the OLD default (divergence-armed, gap-edge entry, no deep-only). The shipped default is now the
> deep-entry combo (sweep-arm + deep-only + deep-fib → ≈+237%/PF6.2/85%/13%DD at 84 trades). The
> numbers below still stand as the divergence-only baseline, but they are no longer the default's
> results. Read them as history, not as what the bot does out of the box today.

40 trades, net **$21,536.60** on $10k. The distribution is the same story with a bigger sample:

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner | 15 | +26,565 | **123%** | 1.13 |
| TP1 only | 12 | +4,032 | 19% | 0.16 |
| never reached TP1 | 13 | −9,060 | −42% | −0.45 |

What the second year of data changed, and what it didn't:
- **Win rate fell 72.73% → 67.5%** (27/40) and losers went 6→13 — the 1-year window was the kinder half.
- **Concentration improved**: top 3 = 45% of net (was 57%) — still above the framework's <60% floor
  but no longer resting on three trades.
- **Still 17 of 40 near-scratch**, and still exactly the runner carrying everything (123% of net).
- **Full-R losses scale with the sample** (2 → 5), i.e. the stop→BE rule keeps converting most losses
  to scratches; that behaviour is stable, not a one-year artifact.
- **The ~83% short skew (33 shorts / 7 longs) is EXPLAINED as of 2026-07-16 — it is not a bug.**
  The port is parity-green, so the Pine skews identically. Measured per-side over the same 2yr
  window (48,246 bars, gold +75%):
  - **Root cause — the arm-source filter.** The sequence arms on a sweep OR a divergence, but
    `exec_arm_sweep` defaults **False**: only DIVERGENCE-armed setups may enter. Bearish
    divergences outnumber bullish **142:73 (66%)** in an uptrend — price keeps making higher
    highs on weakening RSI, while bullish divergences need lower lows a bull market rarely gives.
    The skew is inherited almost entirely from that 2:1. Sweeps, by contrast, are near-symmetric
    (1,505 S / 1,308 L), and the raw structure is *dead even* — external SOS is **125/125**. So
    nothing upstream of the arm filter is asymmetric.
  - **Amplified by fib geometry.** Episodes reaching Stage 4 READY: **37 L vs 67 S**. After a bull
    SOS a long waits for a retrace to 0.5/0.618 — in a strong uptrend the pullback is too shallow
    to reach it (51 long episodes die at peak stage 2, vs 25 short), while the deep counter-trend
    rallies a short setup needs arrive reliably.
  - **The default filter is the profitable subset, and it is a strict SUBSET.** Every
    divergence-armed trade is also sweep-armed, so `both` is bit-identical to `sweep only`.
    Arm source → trades / short% / net / PF (bar mode, 2yr, no costs):
    divergence-only (OLD default) 40 / 82.5% / +190% / **3.27** · sweep-only (= both) 79 / 69.6% /
    +144% / **1.87**. Enabling sweeps adds 39 trades that lose money net and drags PF down ~43%.
  - **Longs are not broken, just rare** — 7 trades, **86% win**, profitable (+21% of capital).
    Nothing is blocking longs incorrectly; there simply are few bullish divergences up here.
  - **What to actually worry about is concentration, not the count.** Shorts carry **89% of net**.
    Every HTF bias filter is `Ignore` (`exec_htf_weekly`/`exec_htf_daily`), so this is an
    unfiltered counter-trend fade that shorted a +75% bull market and won at 70%. That is the
    claim needing a second regime to confirm — the direction split itself is now accounted for.

Open threads (Aaron is on the edge work as of 2026-07-16): whether stop→BE on TP1 caps runners; and
why 15m is reportedly the only winning timeframe (a real edge usually survives on neighbouring
timeframes — if 5m and 30m lose, suspect luck). 40 trades is still a thin sample; treat the KPIs as
directional, not settled. (Superseded note: an earlier version warned "do not flip `exec_arm_sweep` — it
breaks parity". That was wrong on the mechanism — parity is driven by the export's `cfg_bits`, not the
default — and moot now: the default flipped to sweep-arm on 2026-07-23, in lockstep across both Pine
files and `config.py`, so parity holds. Flip toggles freely per run; just keep the two Pine files and
`config.py` defaults identical when you change a DEFAULT.)

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_sos_fade/tests/ -q
```
Offline, no network, no TradingView. `test_sequence.py` (state machine on the real engine stack +
hand-checked Pine rules), `test_execution.py` (fills / ladder / stop-out / sizing, hand-checked),
`test_strategy_driver.py` (end-to-end), `test_compare_strategy.py` (the parity tool round-trips its
own output). These prove the plumbing; the Pine diff is the live gate.

## Do / Never

- **Do** port any change to `mpc_strategy.pine`'s A+ block or execution layer here line-for-line, then
  re-run `compare_strategy.py`. Keep the Pine the source of truth — never edit it to match the Python.
- **Do** read engine OUTPUT only (`backtest.replay` `BarState`) — never reach into an engine's internals.
- **Never** build a second copy of any engine here — this consumes the canonical `engines/`.
- **Never** trust a backtest number until `compare_strategy.py` is exit 0 on a fresh export.
- **Never** commit a real TradingView export or backtest cache into git.

## References

- Spec: `docs/MPC_SOS_FADE_SPEC.md`; build plan + order: `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
- Pine source of truth: `indicators/mpc_strategy.pine` (A+ block ~3708-3972, execution ~4112-4735).
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
