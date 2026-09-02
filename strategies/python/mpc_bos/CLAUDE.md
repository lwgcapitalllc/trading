# CLAUDE.md — mpc_bos (MPC BOS, the break-of-structure continuation bot)

**Purpose:** Standing instructions for this strategy package.
**Scope:** This package only. It does NOT cover the engines it replays (`engines/`), the
backtest infrastructure (`backtest/`), the lab that runs it (`command-center/`), or the A+ bot
it subclasses (`strategies/python/mpc_sos_fade/` — read that one's `## The exit ladder` before
touching an exit).
**Status:** 🟢 **PARITY GREEN 2026-08-07 — and read the coverage caveat below before quoting
anything.** Built 2026-08-07 from `strategies/tradingview/mpc_bos_strategy_export.pine`, and
`tools/compare_bos.py` now exits 0 on a real export: **6,300 bars compared, no divergence**,
at warmups 900 / 1000 / 2000 / 3000. ⚠ **It is green about the SHIPPED defaults only** — the
run had `bos_use_fvg` OFF, so the entire gap-entry ladder is still unverified, and 6 trades
closed inside the window. See *The parity run* below.
**Last reviewed:** 2026-08-16 (latest) — 38 of the 40 `desc` fields moved again when every input tooltip in all 29 Pine files was cut to one or two plain sentences (rule: `strategies/tradingview/CLAUDE.md` → *TOOLTIPS ARE PLAIN ENGLISH*). ⚠ **This bot had ALREADY had the pass described below on 2026-08-10 and still moved 38 fields, which is the point worth keeping: a one-off tidy of one file drifts again the moment the standard is set repo-wide.** The rule now lives in one place and the Pine is its source. Strings only — no name, type, default or order changed. Earlier: 2026-08-10 — 🟢 **THE STRATEGY DETAIL PAGE COPY IS SHORT AND PLAIN NOW.** All 40 `desc` fields in `mpc_bos.meta.json`, plus `edge` and `steps`, rewritten to *what it does, what each choice means, and the one fact that changes the decision*; the measurement dumps are gone from the UI and stay in this file and `docs/MPC_BOS_OPTIMIZATION.md`. **The warnings that change a decision are KEPT in plain words** — the ATR stop is the default because a level-based one shrinks with the move and lands inside the spread, a deep entry must not be paired with a tighter stop, and nothing here is parity-checked yet. ⚠ **A desc is byte-identical to its Pine tooltip, so `mpc_bos_strategy.pine` and its export changed in the same commit — strings only; every input's name, type, title, default and order is unchanged against HEAD.** Earlier: 2026-08-10 — 🔴 **THIS FORK WOULD HAVE DIED ON ITS FIRST BAR, AND ITS OWN PARITY TEST IS WHAT CAUGHT IT.** The parent's `_entry_edges` gained a required `seq` parameter on 2026-08-10 (for `exec_nogap_arm`, which gates the A+ no-FVG fallback). `BosExecution` OVERRIDES `_entry_edges`, and the parent calls it BY NAME from `step()` — so the 2-arg override raised `TypeError: _entry_edges() takes 2 positional arguments but 3 were given` on the first bar of every run. The signature is matched now and **`seq` is deliberately UNREAD here**: this fork's setup has no SOS arm at all, so honouring that lever would gate a BOS entry on a confluence its own Pine never looks for. ⚠ **The parameter is kept rather than dropped** — dropping it is the failure that just happened. ⚠ **The transferable half is about how it surfaced: nothing in the A+ change mentioned this package, and no amount of reading the diff would have named it. `test_compare_bos.py` failed the moment the suite ran.** A fork that subclasses a bot under active development inherits its SIGNATURES as well as its defaults, and only a test that actually drives a bar can see the difference. Earlier: 2026-08-07 — the rebuild, the volume fix, and the first real gate run.

---

## The parity run — what is proven and what is not

```
python strategies/python/mpc_bos/tools/compare_bos.py 'engines/VANTAGE_XAUUSD, 15_ee770.csv' --warmup 900
```

**GREEN, 6,300 bars, 2026-08-07.** The export is 7,200 closed M15 bars, 2026-04-21 → 2026-08-07,
taken off `mpc_bos_strategy_export.pine` at the shipped defaults, and the Python was configured
FROM the export's own `cfg_*` columns: `sl=ATR(1.3) · entry=0.786 · anchor=Break leg ·
useFvg=False · vwap=Trend's side · which=All · tp=0/0/100 · minStop=% of price 0.10`.

✅ **What the run exercised:** 1,220 armed bars · 1,932 priced bars · 6,040 VWAP refusals
(block code 7) · 520 final-hour refusals (code 2) · 6 trades, entry / stop / all three TP
prices / stage / closed R agreeing on every one.

🔴 **What it did NOT exercise, and none of this is green:**

- **The whole gap ladder.** `bos_use_fvg` is OFF at the defaults, so rules 1–5, Method 3 and
  the Sniper Zone branch never ran on either side. A green gate says nothing about a branch
  neither side entered — and the Sniper Zone half **cannot** be checked at all until the Pine
  re-adds `px_sz_top` / `px_sz_bot`, which it says so itself.
- **Block codes 1, 3, 4, 5 and 6 never fired.** The minimum-stop floor is ON and refused
  nothing; the tool says so out loud, and that is the exact shape of the 2026-08-04 min-stop
  incident.
- **Six trades.** The arming and pricing evidence is thousands of bars deep; the exit ladder's
  is six trades in one 3½-month window.

⚠ **Below warmup 900 it is RED, on the BOS ordinal alone, and that is genuine engine cold
start rather than a mask.** The two sides disagree about how many breaks printed before the
structure engine had converged; an SOS at bar 856 resets both counters, which is exactly where
the disagreement ends. Verified by reading the SOS bars out of the export, not assumed.

⚠ **Re-run the gate after ANY change here, and re-run it on an export taken with
`bosUseFvg` ON before trusting a gap-priced result.**

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

**The gate is green as of 2026-08-07, and that does NOT retroactively validate anything
measured before it.** The port changed in three places to GET green (see below), so every
figure produced by an earlier build describes different code:

- `docs/MPC_BOS_OPTIMIZATION.md` — every run in it, Runs 1–8. **Re-run anything that still
  matters.**
- `backtest/tools/bos_sweep.py` — **actively falsified and still is.** On the same symbol,
  timeframe, window and config it reported 20 trades / PF 2.97 / +102.5% where the TradingView
  Strategy Tester reported 24 / PF 1.043 / +5.01%. Entries roughly agreed; the exit ladder did
  not. Nothing in this pass re-checked it.
- Anything this package printed before today.

**The previous port was DELETED on 2026-08-04** (commit `1946f8b`) for exactly this: an
82-configuration sweep produced by a port nobody could check. This one exists to not repeat
that, and the gate is the whole difference.

### Running the gate

```bash
python strategies/python/mpc_bos/tools/compare_bos.py '<export>.csv' --warmup 900
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
| `exec_secondary=False` | `True` | the re-entry needs a second bar stream through `run_dual`, which this fork does not have and `backtest.optimizer.run_sweep` cannot supply — **every BOS sweep would refuse** |
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

## The three defects the first real gate run found

All three were invisible to 54 green unit tests, and each one is a different way of being
wrong.

**1. A DEAD LEG KEEPS ITS NUMBERS. The port cleared them.** Pine's `bosL_on := false` touches
nothing else — `bosL_high` / `bosL_low` / `bosL_bar` / `bosL_n` / `bosL_half` are `var` and are
reassigned only when a NEW break arms, so `px_l_ext`, `px_ord_l` and `lFibsReady` all carry the
last leg's values after a death. `BosLeg` was rebuilt blank instead, and the run went red on the
FIRST compared bar with `l_ext: py=None pine=4584.26`. It is behaviour-neutral on both sides —
every consumer ANDs with `.on` first — which is the only thing that makes stale numbers safe,
and also the reason nothing in the strategy's own behaviour would ever have told you.

**2. THE HARNESS COMPARED A CONSTANT FOR ITS WHOLE LIFE.** `compare_bos.py` read
`strat.execution._stage` inside its compare loop, which runs AFTER the replay — so every bar was
diffed against the run's FINAL stage. The run ends flat, so that constant was 0, and the column
checked nothing at all until a Pine bar happened to report 1 or 2. The stage is sampled per bar
into `MpcBosStrategy.exit_stages` now. ⚠ **This is the sharper lesson of the three: a harness
that reads live state after the fact is not reading the bar it names, and the failure mode is a
column that looks like it is passing.**

**3. THE STILL-FORMING LAST BAR KILLED THE RUN AND BLAMED THE FEED.** TradingView appends the
live bar to every export with all its plotted series blank — including `px_volume` — so the NaN
reached the VWAP engine and raised `VolumeUnavailable`, whose message points at the bar feed.
`_drop_forming_tail` trims it and says how many, and REFUSES on a blank row in the middle,
because only a trailing run is a live bar.

⚠ **And one shape worth naming on its own: the harness had an accommodation written to match
the PORT rather than the Pine** — `ordinal_l` read `bos.long.ordinal if bos.long.on else 0`,
which is exactly the zeroing defect #1 introduced. A comparator that agrees with the thing it is
checking is not a comparator. Before trusting a parity column, ask what it is compared AGAINST.

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
  ⚠ **`count_l` and `leg.ordinal` legitimately disagree after a refusal**: the Pine bumps
  `bosCntL` outside the filter block and assigns `bosL_n` inside it, so a turned-down break
  advances the counter and leaves the armed leg's number where it was.
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
- **No `run_dual`.** There is no BOS fast-feed leg in any Pine.
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

## 🔴 The parent's re-entry ships ON again — this fork's pin is LOAD-BEARING (2026-08-27)

`mpc_sos_fade` has now flipped `exec_secondary` THREE times: ON 2026-08-07, OFF 2026-08-21, and ON
again 2026-08-27, this time as the **reclaim** re-entry banking all-out at 3.25x (Aaron's call).
**This fork's own pin is unchanged and still False**, so nothing this bot trades has moved.

🔴 **The pin is LOAD-BEARING again, not redundant — that is the change.** A fork that leans on its
parent's default is one flip away from breaking, and this field has now flipped three times.
The fork's own value is asserted first because that is what protects this bot; the parent's value is
pinned after it so a flip back to True surfaces in BOS's own test rather than as a
refused sweep.


## 🔴 `exec_min_atr_pct` is PINNED off, and the pin here is LOAD-BEARING (2026-08-26)

The parent gained a dead-market entry floor
(`strategies/python/mpc_sos_fade/CLAUDE.md` → *The DEAD-MARKET floor*). This fork pins it to 0.0,
and unlike the sibling forks **the pin is what stops it acquiring the filter**, not a precaution.

🔴 **This fork defines its own `_place_entries`, which reads as "it cannot reach the parent's entry
gates" — and it is wrong.** The gate rides inside the shared `_stop_clears_floor`, and this fork
calls that check from inside its own placer (`execution.py:401`). Without the pin it would have
acquired a volatility filter with **no error, no failing test and no Pine input to catch it** —
this package's own suite passed the whole time while inheriting it.

**The rule, and it is bigger than this field: "it overrides the method" is a claim about ONE call
site. Find the line that consumes the value.** A fork is only insulated from a parent's gate where
it stops calling the code the gate lives in, and a shared helper is exactly where a gate gets hung.
