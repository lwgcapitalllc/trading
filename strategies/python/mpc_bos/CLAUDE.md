# CLAUDE.md — mpc_bos (MPC BOS, the break-of-structure continuation bot)

**Purpose:** Standing instructions for this strategy package.
**Scope:** This package only. It does NOT cover the engines it replays (`engines/`), the
backtest infrastructure (`backtest/`), the lab that runs it (`command-center/`), or the A+ bot
it subclasses (`strategies/python/mpc_sos_fade/` — read that one's `## The exit ladder` before
touching an exit).
**Status:** 🔴 **PORTED, RUNNING, AND NOT PARITY-VALIDATED.** Built 2026-08-07 from
`indicators/mpc_bos_strategy_export.pine`. `tools/compare_bos.py` exists and **has never been
run**, because no TradingView CSV export of that Pine is on disk. Until it is green, every
number this bot produces is a LAB FINDING — read the direction, never the decimals.
**Last reviewed:** 2026-08-07 — the rebuild, plus the volume fix below.

🔴 **The first real export was REFUSED by the gate, and the refusal was right.** Aaron took a
7,154-bar CSV off the export Pine on 2026-08-07; every decision and config column was present,
and `compare_bos.py` stopped before comparing a bar because there was **no volume column**, which
F10 needs. The docstring had said "TradingView exports it" — false: `Export chart data` ships a
Volume column only when the Volume STUDY is on the chart, so it describes a chart layout rather
than the export format. **Measured across ~40 exports in `engines/`: exactly one has volume, and
it is the one whose Pine plots it.** Fixed by making `mpc_bos_strategy_export.pine` plot
`px_volume` itself (the convention `vwap_export.pine` and `svp_export.pine` have always used),
and by making this tool resolve `px_volume` → `volume` → `Volume` the way `compare_vwap.py` does
— it looked for `volume` alone, so an export taken *with* the study on would have been refused
too, since TradingView capitalises it. An all-NaN column counts as no column. ⚠ **The fixture is
what hid it: it wrote a `volume` column no real export has ever carried, so the guard was written
against a name production does not produce.** **Re-export off the current Pine before running the
gate — the 2026-08-07 CSV cannot drive it.**

---

## What it trades

A shift of structure (SOS) tells you the trend has turned. What comes after it is where the
money is: the market prints one or more BREAK OF STRUCTURE events in that same direction until
another SOS ends the run, and each BOS is a fresh continuation leg giving a retracement you can
buy or sell into. **A+ fades the shift; this rides what the shift started.**

At the 2026-08-07 defaults: every BOS in the regime arms a leg, a limit rests at fib **0.786**
of that leg's retrace, the stop is **1.3 × ATR(14)**, price must be closing on the trend's own
side of the **session VWAP**, and the whole position leaves at **TP3** (the leg extreme) or at
the ratcheting stop. No gap requirement, no displacement floor.

```
BarState --SignalAdapter--> Signals --SosFadeSequence--> SeqState
         --BosTracker--> BosState --BosExecution--> Decision
```

| file | what it owns |
|---|---|
| `config.py` | every input, one field per Pine input and **nothing else** |
| `bos.py` | Stage 0/1, the anchor fib ladder, death, and F10 (session VWAP) |
| `execution.py` | the entry ladder, the stop models, the TP tiers, TP3, the divergence kill |
| `strategy.py` | the driver + the engine pins |
| `tools/compare_bos.py` | the parity gate — **the thing that makes any of this trustworthy** |

---

## 🔴 Read this before quoting any number from this bot

**No `compare_bos.py` run has ever been green.** The gate needs a TradingView "Export chart
data" CSV of `indicators/mpc_bos_strategy_export.pine`, which is a five-minute human step
nobody has done. Everything downstream is unverified until it is:

- `docs/MPC_BOS_OPTIMIZATION.md` — every run in it, Runs 1–8.
- `backtest/tools/bos_sweep.py` — **actively falsified.** On the same symbol, timeframe, window
  and config it reported 20 trades / PF 2.97 / +102.5% where the TradingView Strategy Tester
  reported 24 / PF 1.043 / +5.01%. Entries roughly agreed; the exit ladder did not.
- Anything this package prints.

**The previous port was DELETED on 2026-08-04** (commit `1946f8b`) for exactly this: an
82-configuration sweep produced by a port nobody could check. This one exists to not repeat
that, and the gate is the whole difference.

### What to do with the export when it arrives

```bash
python strategies/python/mpc_bos/tools/compare_bos.py '<export>.csv' --warmup 500
```

⚠ **Read the COVERAGE table before believing the exit code.** The tool prints how many bars each
branch actually reached and warns when one was never taken — because a green run is only green
about the branches BOTH sides entered. This repo shipped a setting on a parity run that never
exercised it (the min-stop guard, 2026-08-04: block code 7 raised **zero** times in 21,897
bars, green on a branch neither side entered).

⚠ **A gap-entry run is only partly checkable today.** The export carries no `px_sz_top` /
`px_sz_bot`, so with `bos_use_fvg` ON the Sniper Zone branch of the ladder is unverified and the
tool says so. Re-add those two plots to the Pine before trusting a gap-priced parity run.

---

## The three things that differ from the A+ bot, and nothing else

The Pine's own header states them, and they are the only reason this is not just a config of
`mpc_sos_fade`:

1. **The arm is a BOS after an SOS** — no sweep arming, no sweep confluence.
2. **Divergence is a KILL, not a veto-with-exemption.** The A+ veto is judged at the SOS and
   carries an exemption, so a divergence that armed the fade cannot then refuse it. A
   continuation setup has the opposite relationship to divergence — an opposing one is the
   fakeout signature — so it is LIVE, re-read on every bar the limit rests. A divergence
   appearing during the retrace PULLS the order; one going stale lets it be placed again.
3. **The stop model is a dropdown** (`bos_sl_model`), not a fib-level dropdown.

Plus one thing the A+ ladder does not have at all: **a THIRD take-profit rung.** The A+ is
TP1 / TP2 / runner; this adds TP3 at fib 0.000 and defaults it to 100%, so at the shipped
settings there is **no runner**. `_remaining_brackets` is overridden for exactly that.

Everything else — fills, staging, the trail, %-risk sizing, R grading — is the parent's, unchanged.

---

## ⚠ The config pins, and why each one exists

`BosConfig` is a `SosFadeConfig` superset, so **every A+ default it does not re-declare is
inherited** — including ones added to the A+ after this fork's Pine was written. Four pins are
load-bearing:

| pin | inherited value | what would happen |
|---|---|---|
| `exec_fib_nearest=False` | `True` | the parent's 2026-08-02 entry model rests a gap on a DIFFERENT fib from Method 3. `mpc_bos_strategy.pine` has no such input, so every gap entry would sit at a level the Pine never chose — **and the export has no column to catch it with** |
| `exec_deep_fib=True` | `False` | the parent turned Method 3 off when its new model replaced it; this fork's Pine still ships it ON and has none of those rules |
| `exec_secondary=False` | `True` | the 1-minute re-entry needs a second bar stream through `run_dual`, which this fork does not have and `backtest.optimizer.run_sweep` cannot supply — **every BOS sweep would refuse** |
| `exec_time_stop_mode="Off"` | `"Before TP1 only"` | the 36h plateau was measured on A+ trades; a continuation trade is a different hold |

**The standing rule: a default is read by every caller, including the ones that cannot honour
it.** Before changing anything in `SosFadeConfig`, check what this fork inherits.

⚠ **Nothing in `config.py` may exist without a Pine input behind it.** The deleted port carried
eight research dials with no counterpart (`bos_entry_source`, `bos_exit_mode`, `bos_rr_tp1/2`,
three ATR-regime filters, `bos_no_ny_pm`) and a sixth stop model. **A field the export cannot
carry is a field `compare_bos.py` can never check**, so a run using one is unverifiable by
construction. Recover them from `1946f8b^` if the Pine ever grows the inputs — do not re-add
them here first.

⚠ **`bos_move_stop` / `bos_move_stop_val` are NEW fields, not inherited** — `SosFadeConfig` has
no moving stop at all. They exist because the EXPORT carries `execMoveStop`, and a Pine input
the Python cannot express is a setting the comparator would decode into nothing.

---

## ⚠ This is the only strategy in the repo that needs VOLUME

F10 (the session VWAP filter) is a volume-weighted mean, so it cannot be computed from OHLC.
Three consequences:

- **`ReplayBar` gained an optional `volume`** (2026-08-07, `backtest/replay/loop.py`). `None`
  means the feed carried none — **never 0.0**, because a zero-volume bar is a real thing MT5
  reports on a dead session, and filling the unknown with one puts a measurement where there is
  none.
- **It reads the canonical `engines/vwap/`**, never a private VWAP. A VWAP anchored at the break
  would be a second implementation (forbidden) AND would not be the line anyone is looking at on
  the chart.
- **A frame with no volume REFUSES** (`VolumeUnavailable`), at `run()` rather than 100,000 bars
  in. Both ways of guessing are silent: block everything → an empty book that reads exactly like
  a strategy with no signals; pass everything → a filter reported as ON and doing nothing. The
  Pine cannot hit this (TradingView always has tick volume on XAUUSD), so there is no Pine
  behaviour to mirror and refusing is the honest third answer.

- **The EXPORT must carry it too, and it does not come for free.** `mpc_bos_strategy_export.pine`
  plots `px_volume`; TradingView's own Volume column only appears when the reader has the Volume
  study on the chart, so an export cannot be assumed to have one. `compare_bos.py` resolves
  `px_volume` → `volume` → `Volume` and REFUSES when none of them holds data — replaying F10
  against an absent VWAP blocks every setup, and an empty book matching an empty book is
  agreement about nothing.

⚠ A `na` VWAP (the session's first bar, before any volume) **BLOCKS both sides**. "Cannot ask"
and "no" must not be the same value, and of the two answers available to a gate about to place
money the safe one is the refusal. It costs at most one bar a day.

---

## Rules with teeth (each one is a bug someone will otherwise reintroduce)

- **A shift bar is not its own first continuation.** The structure engine sets `bull_bos = True`
  on every `bull_sos` bar too, so every BOS test reads `bull_bos and not bull_sos`.
- **Opening and closing a regime are gated DIFFERENTLY, and that asymmetry is a fix.** OPEN is
  gap-guarded; CLOSE fires always. Both used to sit behind `not sessionGapBar`, and the half
  that mattered was the close: a bear SOS on a gap bar left the long armed, so its buy limit
  rested straight into the new bearish regime and could still fill on the way down. Killing on a
  possible artifact costs one setup; keeping it costs a wrong-way trade.
- **The cycle latch is PER ANCHOR, not global.** The engine's `fibo7Touched` is keyed to the fib
  ORIGIN, which does not change across a run of breaks — so break #1's round trip would kill
  breaks #2 and #3 on their own arm bar and every continuation after the first would be
  untradeable.
- **The ordinal counts refused breaks**, so the number a trade reports is its true position in
  the run. And a refused newer break still CANCELS the older arm — the newest break owns the leg.
- **Entry depth is DERIVED, never chosen.** The tier rule exists to guarantee TP1 is never a
  level the entry already rests at, or the trade "hits TP1" on its own fill bar, stages to
  breakeven and dies a scratch.
- **The ATR is computed ONCE per bar** (`prime_atr`, guarded on the bar index) and read by both
  the tracker and the order layer. Two Wilder steps on one bar advance the average at double
  rate and silently produce a different ATR from the Pine's on every bar afterwards.
- **F4 (`bos_req_hold`) is off by MEASUREMENT, not by omission.** The 0.5–0.886 band sits BELOW
  the broken swing on almost every leg, so price cannot reach the limit without first closing
  back through the level — F4 killed setups a few bars before their own order would have filled
  (13 trades in a year). It is only coherent alongside a much shallower entry.
- **`"Broken swing level"` is largely inoperable and that is not a bug to fix.** For a long that
  level sits ABOVE the entry, so `dist` is negative and the order is refused. It is kept only
  because the Pine has it.
- **A rung sized 0% is skipped, never placed.** In the Pine `qty_percent = 0` falls back to
  closing the WHOLE position at that limit — the opposite of "bank nothing here".
- **The moving stop is dead on the fill bar.** `_max_fav` is seeded from the entry price, and
  the fill bar's favourable extreme is where price was on its way INTO the resting limit —
  before the trade existed. This is `BUG_exit_fill_price_mismatch` arriving through a second door.

---

## What is deliberately NOT here

- **No missed-setup watch.** The parent's answers "how far did this **A+** setup get" — it
  counts the sweep arm, the SOS and the 0.5–0.886 zone, none of which this setup has. A BOS
  version is new design work; the tracker's per-leg death REASON is the raw material.
- **No `run_dual`.** There is no BOS 1-minute leg in any Pine.
- **No live-bot instance.** This bot is not deployed and must not be until the gate is green —
  `docs/LIVE_TRADING_PIPELINE.md` is the path.

---

## Engine pins — and this fork disagrees with the A+ on three of five

`MpcBosStrategy.engine_config()` pins `fvg_max_count=8`, `fvg_threshold_pct=0.04`,
`fvg_require_close=False`, `show_internal=False`, `eq_exempt_fvg=False`.

The first three differ from the A+ bot's (7 / 0.1 / True) because the two Pines genuinely
disagree — this fork keeps the same gap set `mpc_assistant.pine` DRAWS, so a gap on the chart is
a gap the strategy holds. **All three make this fork hold MORE gaps**, so inheriting the
parent's pins would silently narrow the set — and at the shipped defaults (`bos_use_fvg` off)
nothing would move at all, which is worse: the pin would look correct right up until somebody
switched the gap entry back on.

They vary per run and ARE exported, so `compare_bos.py` configures the engines FROM the export
rather than trusting that function.
