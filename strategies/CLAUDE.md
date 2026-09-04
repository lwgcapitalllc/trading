# CLAUDE.md — Strategies

**Purpose:** Generic trading strategy implementations, organized by runner platform.
**Scope:** Strategy source files (`.cs` for NT8, `.mq5` for MT5, `.pine` for TradingView, Python packages for the local Python runner). Does NOT cover backtest infrastructure (see `command-center/` and top-level `backtest/`), live bot runtime logic (see `algos/`), or regime classification (see `engines/regime/`).
**Status:** Production. NT8 has one strategy (ORB.cs), deployed via the command center. MT5 has one strategy (LondonBreakout.mq5). Python has **five** strategies (`python/sos_fade/`, `python/b_leg/`, `python/bos/`, `python/realign/` and `python/extreme_leg/`, run locally — no deploy), plus `python/loss_recovery/`, which is a RULE rather than a strategy. ⚠ **Count them with `ls strategies/python/`, never from this line** — it read "four" while there were five. 🔴 **`realign` (new 2026-08-13) is the one that is NOT parity-validated** — it has no export twin, no real CSV and no `compare_realign.py`, so stages 3, 4 and 6 of `docs/STRATEGY_WORKFLOW.md` are outstanding and every number it has produced is a lab finding. It is also the first fork here to enter at MARKET rather than resting a fib-priced limit. Read `python/realign/CLAUDE.md` before quoting it. ✅ **`extreme_leg` (new 2026-09-01) went parity GREEN on 2026-09-02**, on its second export — the first was red and named one cause, the weekly-level rule, which turned out to be the PINE disagreeing with its own parent. ⚠ **Its gate is NARROW: 3.5 months, 7 entries, and four of eight refusal codes never reached.** Its 6.6-year figures sit on bars the gate has never seen. Read `python/extreme_leg/CLAUDE.md` → *The parity gate* before quoting one. 🔴 **It is also the first strategy here whose SHIPPED form the gate can never check**: a market-condition refusal that reads `engines/regime/` was switched ON on 2026-09-02, Pine has no such engine, so the gate forces it off, compares the shared logic, and prints a verdict saying the shipped bot takes fewer trades than the run just compared. A green gate here is a narrower claim than a green gate anywhere else in this folder. **The other three are parity-validated; `bos` went green 2026-08-07 on its first real export** — ⚠ but only at the SHIPPED defaults, which have the gap entry OFF, so its whole FVG ladder is still unverified. Read its own CLAUDE.md → *The parity run* before quoting a number from it. 🔴 **`tradingview/` STOPPED BEING SCRATCH ON 2026-09-02** — the 14 Pine `strategy()` files moved in from `indicators/strategies/`, so it now holds the source Aaron actually runs in the TradingView Strategy Tester, six of them export twins that are half of a parity gate. The two research files went down one level into `tradingview/research/`. **Nothing under `tradingview/` is scanned or deployed by the command center** — the scanner globs `.cs` and `.mq5` only and has never globbed `.pine`.

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `strategies/docs/STRATEGY_BUILD_NOTES.md`. **Nothing was deleted.** It was 42,571 bytes in 1 paragraph(s), the largest 42,571 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

## Key paths

```
strategies/
├── ninjatrader/    ← NT8 NinjaScript strategies (.cs files, C#)
│   └── ORB.cs            (VWAP_MR.cs, Momentum.cs deleted 2026-06-21 — see below)
├── mt5/            ← MT5 expert advisors (.mq5, MQL5)
│   └── LondonBreakout.mq5
├── python/         ← Python strategy packages — run LOCALLY by the lab's python runner (no VPS)
│   ├── sos_fade/        (SOS Fade bot; own CLAUDE.md inside)
│   ├── b_leg/            (B-LEG bot — the late-retrace setup, split out to run parallel to SOS Fade; own CLAUDE.md)
│   └── loss_recovery/       (NOT a strategy — a RULE that replays a counter-trade over another
│                             strategy's losses. LAB ONLY, `enabled` defaults False, no Pine twin
│                             and therefore no parity gate. Own CLAUDE.md)
└── tradingview/    ← Pine v6 `strategy()` source — TradingView Strategy Tester only
    ├── CLAUDE.md            (the panel contract, the annotations, the palette — read it first)
    ├── sos_fade_strategy.pine + sos_fade_strategy_export.pine        (SOS Fade SOS Fade; the LIVE bot's twin)
    ├── b_leg_strategy.pine + _export                   (B-LEG)
    ├── bos_strategy.pine + _export                     (BOS continuation)
    ├── extreme_leg_strategy.pine + _export             (extreme leg)
    ├── h4_sweep_strategy.pine + _export                (H4 sweep)
    ├── smc_session_sweep_strategy.pine + _export           (session sweep)
    ├── realign_strategy.pine, recovery_strategy.pine   (no export twin — see below)
    ├── docs/                (one <family>.md per strategy — the prose lifted out of the Pine)
    ├── tools/               (build_extreme_leg.py, derive_htf_structure.py)
    └── research/            ← scratch: hand-tested only, no twin, no gate, no port
        ├── london_breakout.pine
        └── ny_orb.pine
```

🔴 **THE TOP LEVEL AND `research/` ARE TWO DIFFERENT KINDS OF FILE AND THE FOLDER SPLIT IS HOW THAT
IS SAID ONCE INSTEAD OF PER FILE.** A file at the top level is Aaron's real strategy source: it
carries the numbered input-panel contract, most have an instrumented `_export` twin, and six of
them are half of a Pine↔Python parity gate — a default moved there invalidates every baseline
measured before today. A file in `research/` is an idea being hand-tested in the Strategy Tester:
no twin, no gate, no Python port, nothing depends on it. **A new Pine strategy starts in
`research/` and is moved up when it earns an export twin.**

⚠ **Neither half is scanned or deployed by the command center.** The scanner rglobs `.cs` and
`.mq5` only, plus directories under `python/`, and has never globbed `.pine` — moving 16 Pine files
in here did not register a single new strategy in the lab, which was CHECKED before the move rather
than hoped for afterwards.

⚠ **They moved here on 2026-09-02 from `indicators/strategies/`.** `indicators/` is organised by
LANGUAGE, this folder by RUNNER PLATFORM, and Pine runs only on TradingView — so the tie was broken
by what actually depends on what: the parity gates that consume these files live one folder over in
`python/`. The engines the strategies INLINE stay under `indicators/engines/`. Full survey:
`docs/TRADINGVIEW_STRATEGY_MOVE_PLAN.md`.

---

## Standing instructions

**Do**
- Keep strategy logic generic — no firm-specific defaults baked in
- All foundational parameters (account size, daily loss, hours, commission, etc.) come from the active ruleset at runtime, injected by the command center dispatcher
- Use `[Category("Strategy Logic")]` on tunable parameters (visible to optimizer) and `[Category("Foundational")]` on injected parameters (hidden in UI)
- New strategies go in the appropriate runner subfolder
- After adding a strategy, run the scanner from the command center (`POST /strategies/scan`) to register it in the database

**Rescued from the moved narrative 2026-08-12 — these were BURIED in a 42,571-byte single line, which is to say they were not findable, which is to say they were not working as rules.** Evidence for each is in `strategies/docs/STRATEGY_BUILD_NOTES.md`.
- **A field the export cannot carry is a field the parity gate can never check.** Do not add a Python-side dial without the matching Pine input and `cfg_*` column — `compare_*.py` is blind to it forever.
- **A green parity run says the two implementations AGREE — never that either is RIGHT**, and says nothing about a branch neither side entered. Read the comparator's COVERAGE table before believing its exit code.
- **Fix a parity mismatch in the FIXTURE, never with a `getattr(..., None)` default in the tracker.** A fixture that writes `0` for `na` is how a harness gets "fixed" into ignoring the no-vs-cannot-ask distinction it exists to protect.
- **A parameter's label and its Pine input change in the SAME commit.** One parameter, one name, two UIs; a lab row disagreeing with the chart is how a rule gets read backwards.
- **Pine inputs declared beside their own block must NOT be tidied up into the shared panel.** TradingView keys saved chart values off declaration order within each type, so reordering silently resets every later input on a live chart.

**Never do**
- Hardcode firm-specific values (account size, max daily loss, commission) as defaults in strategy files
- Name a strategy file with a firm name in it (`ORB_PropFirm.cs` is wrong — `ORB.cs` is right)
- Mix strategy trading logic with risk-management mechanics that belong in foundational config

---

## Adding a new NinjaTrader strategy

1. Create `<StrategyName>.cs` in `strategies/ninjatrader/`
2. Tag every `[NinjaScriptProperty]` with `[Category("Strategy Logic")]` or `[Category("Foundational")]`
3. Foundational params must default to sentinel values (e.g. -1 or empty string) so the strategy refuses to trade if injection fails
4. From the command center, click "Scan Strategies" to register it in the database
5. Click "Deploy" next to the strategy on the Strategies tab to upload to VPS
6. Click "Compile NT8" on the Deployed tab
7. Run a backtest to verify

## Adding a new MT5 strategy

1. Create `<StrategyName>.mq5` in `strategies/mt5/`
2. The strategy's class name must match the filename (MetaEditor requirement)
3. **Add the optimizer frame callbacks** (`OnTesterInit`/`OnTester`/`OnTesterPass`/`OnTesterDeinit`) if the strategy should be usable with the native MT5 optimizer. Without them single backtests and walk-forward work, but optimization runs every pass and harvests nothing — `opt_results.csv` is never written and the job fails with "OnTesterPass may not have fired". Copy the block from `LondonBreakout.mq5`: `OnTesterInit` writes the header, `OnTester` `FrameAdd`s each combo's params + KPIs, `OnTesterPass` `FrameNext`s them into `opt_results.csv`. Column names must match the backend parser — KPI columns `net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe` (`gross_profit/gross_loss` optional) and param columns equal to the optimization grid keys.
4. From the command center, click "Scan Strategies" to register it in the database (scanner picks up `.mq5` via `strategies/mt5/` rglob)
5. Click "Deploy" next to the strategy on the Strategies tab — routes to the MT5 agent (port 8766) automatically based on `.mq5` extension
6. Click "Compile MT5" on the Deployed tab — compiles each `.mq5` explicitly (`metaeditor64.exe /compile:<file> /log`) and verifies success by the produced `.ex5` mtime advancing (MetaEditor's exit code is unreliable; the directory form `/compile:<dir>` could silently no-op and report a stale binary as success). A file whose `.ex5` mtime does not move is a hard failure with the compiler log surfaced — same mtime-polling check the NT8 agent uses on `NinjaTrader.Custom.dll`. The button only appears when MT5 files are present. **The VPS MT5 agent must be running the post-`509d16c` `mt5_agent.py` for this check to apply** — older deployed agents reported compile success without rebuilding; redeploy (`git pull` + agent restart) if `compiled_version` won't advance.
7. Run a backtest to verify (requires MT5 terminal running on VPS; strategy Tester ini+set approach)
8. **(Optional) Add a `<Strategy>.meta.json` next to the `.mq5`** to drive the friendly lab param editor (`ParamEditor`). It overlays editor metadata onto the scanned `param_schema`: per-param `label`, `desc`, `unit`, `group`, `core` (shown in the Essentials card), `widget` (`toggle`/`switch`/`time`), `options` `{off,on}` for bool toggles, `show_if` `{param: value}` for conditional visibility (the value may be an ARRAY = "any of these", which is what an enum with one OFF state and several ON states needs — see `python/sos_fade/sos_fade.meta.json` → `exec_min_stop_val`), `guide` `[lower, higher]`, `step`, and **`choices`** (a closed list of legal values for a string param → renders a DROPDOWN instead of a text box; use it for every enum, because strategies match enum strings exactly and silently no-op on anything else, so a typo disables the setting with no error). Param order in the file = UI order. Two **top-level** keys also drive the StrategyDetail overview: `edge` (one-paragraph "where the edge is") and `steps` (`[{label, title, detail}]` flow diagram). Both are optional and UI-only (stored on `strategies.edge`/`steps`); the page falls back to the editable description alone when absent. It affects the lab UI only — never the compiled `.ex5` or `source_hash`, so editing it needs no redeploy. The scanner re-reads it when its mtime is newer than the last scan, so **click Scan Strategies after editing it**. Missing meta = graceful fallback to the raw scanned schema. See `mt5/LondonBreakout.meta.json` for the reference.

## Adding a new Python strategy

1. Create a package `strategies/python/<name>/` with an `__init__.py` that declares `LAB_STRATEGY = {"strategy": <StrategyClass>, "config": <ConfigDataclass>, ...}` — declaring it is how a package opts in to the lab (see `python/sos_fade/__init__.py` for the reference).
2. The lab identifies the strategy by the **class's `__name__`** (stored as `class_name` by the scanner, sent as `strategy_class` in every job spec) — the package folder name is NOT the contract.
3. Click "Scan Strategies" to register it. No deploy, no compile — it runs in the backend process via the top-level `backtest/` package.
4. **Add `strategies/python/<name>/<name>.meta.json`** — same overlay the `.mq5` strategies use
   (`label`, `desc`, `unit`, `group`, `core`, `widget`, `options`, `show_if`, `guide`, `step`, plus
   top-level `edge`/`steps`). Without it the detail page is a bare list of raw field names in one
   "Strategy Logic" group. **Note the filename differs from the MT5 convention**: it is
   `<package>.meta.json` inside the package dir (`sos_fade/sos_fade.meta.json`), not
   `<ClassName>.meta.json`. UI-only, so editing it needs no re-parity — but re-scan after editing.
   **Every non-foundational config field needs a `desc`, and a test enforces it** —
   `command-center/backend/tests/test_python_runner.py::test_every_tunable_param_is_documented`
   fails by NAME on any that lack one, because a param with no description renders as `—` on the
   strategy page and the reader has no way to find out what it does. Add a config field and its
   meta entry in the same commit. A field that is deliberately not ported yet still gets one — say
   so in the text (`exec_conf_sz` and `exec_fvg_50` are the reference wording: "Pine-only for now …
   NOT ported to this bot — leave it OFF").
4. Strategy logic must consume the canonical `engines/` through `backtest/replay` — never a second engine implementation.
5. **Declare who sizes it.** Default (omit) = the strategy proposes UNIT-size trades and the lab's
   dynamic sizing engine sizes them per ruleset — the gated-layer rule that NT8/MT5 strategies
   follow. Add `"self_sizing": True` ONLY if the strategy computes its own position size from its
   own risk % (like `sos_fade`'s `exec_risk_pct`). It makes the lab leave the results alone;
   without it the engine re-sizes the run, throwing the strategy's real size away and leaving the
   KPI cards disagreeing with the equity chart. A self-sizing strategy's risk knob is a normal
   strategy param, so it stays editable per run and sweepable in the optimizer.
6. **The scanner reads NINE keys off `LAB_STRATEGY`, and this step exists because it listed one.**
   Everything a package can declare is opt-in and its ABSENCE is a silent default — so a key you
   have never heard of is a behaviour you get without choosing it. ⚠ **Read this list from the
   SCANNER, never from this line** (`command-center/backend/services/strategy_scanner.py`, the row
   dict): the same trap as counting engines from memory, and four of these were undocumented here
   until 2026-09-02 — and the ninth was missed the very next day. Each is explained next to the code
   that consumes it — do not restate it here.

   | key | what declaring it does | explained in |
   |---|---|---|
   | `name`, `category`, `suggested_instrument` | how the row reads on the Strategies page | — |
   | `self_sizing` | step 5 above | — |
   | `requires_source` | this rule CANNOT run alone; every endpoint that starts a job refuses it | `command-center/backend/CLAUDE.md` |
   | `display_under` | which row it is LISTED under — display only, restricts nothing | `command-center/backend/CLAUDE.md` |
   | `supports_bid_ask_fills` | `False` = it prices the spread FLAT, so a charged run bills the flat spread instead of moving fills | `command-center/backend/CLAUDE.md` |
   | `chart_tag` | the word its trades wear on the price chart; undeclared falls back to the SOS Fade bot's | `command-center/backend/CLAUDE.md` |
   | `suggested_bar_value` | the bar frame in minutes this bot was MEASURED on. It fills the frame box on the run form and each LEG's own frame in a stack; undeclared leaves that leg on whatever frame the reader picked, so a 5-minute bot can silently replay on 15 | `command-center/backend/CLAUDE.md` |

   🔴 **A key the scanner does not read is dropped in SILENCE** — the package states a rule, the
   scan reports success, and the lab behaves as though nobody wrote it. Adding a new one means
   adding it to the scanner's row dict AND the `strategies` table in the same change.

---

## What makes a strategy LIVE-capable — the contract, not one bot's wiring

**`strategies/python/live_contract.py` (new 2026-09-03).** Read it before trying to make any
strategy a bot.

🔴 **Until this existed the live contract had no definition.** It was whatever
`sos_fade.execution.Execution` happened to implement, and a strategy became live-capable by
SUBCLASSING that class — which `b_leg`, `bos` and `realign` all do. That works for a strategy
shaped like SOS Fade and offers nothing to one that is not: `extreme_leg` is an independent
implementation, so it inherited none of it and could not be a bot at all.

🔴 **THE FAILURE MODE THAT HIDES IS THE REASON THIS IS A RULE.** `algos/live/` reads almost every
decision field through `getattr(dec, name, default)`, so **a field a strategy never sets is
indistinguishable from a field with nothing to report.** Omit the stop and the bridge never
ratchets the broker's stop — no error, no halt, no log line, and a position rides its original
stop while every dashboard stays green. **That is rule 1 in a new place, and a defensive read
cannot tell the two apart, so the distinction has to be made before the bot starts.**

⚠ **Of the thirteen decision fields, exactly TWO move money** — the stop the bridge ratchets and
the fills that book the trade. The other eleven are reporting. **An adopter's tests must assert
those two are POPULATED on a bar that should populate them**; asserting that a decision comes back
passes against an adapter that sets nothing.

⚠ **The contract lists are MEASURED off `algos/live/`, never remembered.**
`python/tests/test_live_contract.py` re-derives them from that source, so a live path that starts
reading something new goes RED here instead of going silent in a bot. **A hand-maintained list of
what the live path needs is a second implementation of the live path.**

⚠ **`verify_live_ready(strategy)` checks PRESENCE, never correctness.** It turns "AttributeError
somewhere in the bar loop at 3am" into "refused at startup, by name". That is worth having and is
not the same as being proven — rule 9 still applies to every adopter.

⚠ **SOS Fade satisfies the contract WITHOUT importing it, and a test asserts exactly that.** It is
the independent witness that keeps this module honest: anything the contract demands that the live
bot does not provide is something the live path demonstrably does not need. **It is deliberately
NOT being migrated onto the shared decision class** — that would change the strategy currently
trading, for tidiness.

⚠ **`_POSITION_FIELDS` is the WHOLE open-trade state and a missing entry is SILENT.** The record
round-trips, the bot restarts, and the omitted latch returns at its class default — so a trade
already moved to breakeven is managed as though it never was. Pin it with a test comparing the
list against what the class actually assigns while a position is open. **Restore REFUSES an
incomplete record rather than defaulting, and that refusal is the safety property.**

### Every order layer DECLARES how it opens a position (`entry_style`, 2026-09-03)

🔴 **ONE OBSERVABLE STATE, TWO OPPOSITE CORRECT ANSWERS — WHICH IS WHY THIS IS DECLARED AND NEVER
INFERRED.** *Emulator holding a position, broker holding none, an entry fill on this bar's
decision* is exactly what a **resting** strategy looks like when its limit filled in one book and
not the other — the 2026-08-07 divergence, where the bot must HALT. It is also exactly what a
**market** strategy looks like one instant after its own fill, where the bot must place the
matching order. **The position, the direction, the fill record and the empty broker book are
identical in both cases**, so `algos/live/` asks the strategy instead of guessing.

⚠ **A strategy that enters at market CANNOT be a live bot without this.** It fills inside its own
emulator during the step, so there is nothing left to place ahead of the fill and the bridge's
order-placing branch — which requires the emulator to be FLAT — is never reached. Before the
declaration existed, such a bot halted on its first setup, every time.

⚠ **The value is the one field the contract checks rather than merely counts.** A typo is not a
missing feature: the bridge falls back to `"resting"` and the bot halts on trade one, so
`verify_live_ready` refuses an unrecognised value BY NAME at startup. The fallback is the
backstop, never the thing anything relies on — and it is the halting one on purpose.

⚠ **It does NOT mean the strategy sizes its own live order.** The broker's lot count still comes
from the single live sizing seam, against the BROKER's balance; the declaration decides which
ORDER is sent, nothing else.

---

## Adding a new TradingView strategy

1. **Write it into `tradingview/research/`.** It has no panel contract to honour there, nothing
   imports it, and no gate can go red because of it.
2. **Read `tradingview/CLAUDE.md` before it graduates.** The numbered input panel, the trade
   annotations and the colour palette are a contract shared across every file at the top level, and
   a new file that ignores them is a file the next reader cannot compare against its siblings.
3. 🔴 **The declaration decides where a Pine file lives, never the filename.** `strategy(` belongs
   here; `indicator()` belongs in `indicators/engines/` and is not a strategy at all. A file called
   `..._strategy.pine` that declares `indicator()` is in the wrong tree.
4. **Move it up to `tradingview/` only when it has an instrumented `_export` twin.** The twin is
   what makes a Python port checkable, and the top level is where a reader is entitled to assume
   one exists. ⚠ **A twin moves, lands and changes in the SAME commit as its parent** — a gate
   whose two halves arrive separately was red in between.
5. **Run the three panel checks** — they take seconds and each catches a defect that only shows up
   when Aaron pastes the file into TradingView:

   ```bash
   python3 indicators/tools/check_active_order.py strategies/tradingview/*.pine
   python3 indicators/tools/check_scope.py        strategies/tradingview/*.pine
   python3 indicators/tools/check_flat_reset.py   strategies/tradingview/*.pine
   ```

   ⚠ **The tools stayed in `indicators/tools/` when the strategies left** — they read Pine as
   Pine, so they are about the language rather than about this folder.
6. **Do NOT run the scanner for it.** Nothing here is registered in the lab or deployed anywhere;
   a Pine strategy reaches the lab only by being PORTED to `python/`, and that route is
   `docs/STRATEGY_WORKFLOW.md`, gate and all.

---

## Current strategies

**Deleted 2026-06-21:** `VWAP_MR.cs` and `Momentum.cs`. They embedded their own
account-governance (daily-loss halt, profit-target stop, consecutive-loss halt, profit
lock-in) — risk management that now belongs in the dynamic sizing & gating engine, not the
strategy. Rather than refactor strategies that were against the gated-layer rules, they were
removed. `ORB.cs` is the one NT8 strategy carried forward and re-shaped to the engine. Any
lingering DB rows/runs clear on the next **Scan Strategies** (the scanner warns on a missing
`source_path`, never auto-deletes); remove the deployed `.cs` from the VPS via the Deployed tab.

| File | Class | Runner | Description |
|---|---|---|---|
| `ORB.cs` | ORB | ninjatrader | Opening Range Breakout — entry on ORB high/low break. The only live NT8 strategy. **Reshaped to the gated-layer rules 2026-06-21:** trades unit size (1 contract), self-policing halts removed (moved to the engine), keeps only signal + stop/target + time rules; emits the per-trade record to `engine_trades.csv` (the runner→engine contract). Needs VPS compile + backtest to verify. |
| `LondonBreakout.mq5` | LondonBreakout | mt5 | Asian-range → London breakout, instrument-agnostic. Reshaped to the gated-layer rules 2026-06-22 (v3). Needs VPS compile + backtest to verify — cannot be tested locally. See `mt5/LONDON_BREAKOUT.md` for design + reshape detail and backtest record. |
| `python/sos_fade/` | SosFadeStrategy | python | SOS Fade bot (XAUUSD 15m) — Python port of the brother's MPC-JARVIS SOS Fade grade, replaying the canonical `engines/` via `backtest/`. **Logic-parity GREEN vs the Pine 2026-07-16** (bar-for-bar, exit 0). Runs locally in the lab (backtests + optimizer). **Parity RE-VALIDATED GREEN 2026-07-26** (exit 0) on a fresh 21,230-bar 15m export after the exit levers landed — the run caught an unpinned FVG engine input. **Re-validated again 2026-07-27** (exit 0, 21,320 bars) at the settings Aaron actually trades — SL fib 0.886 + the new 0/0 TP rungs — which was the first run of the whole-position-on-the-runner exit path against the Pine. Full rules in `python/sos_fade/CLAUDE.md`, exit levers in its `## The exit ladder` register. |
| `python/b_leg/` | BLegStrategy | python | B-LEG bot (XAUUSD) — the late-retrace setup (the SOS whose retrace arrived late), split out of `sos_fade_strategy.pine` to run PARALLEL to SOS Fade (2026-07-24). Port of `strategies/tradingview/b_leg_strategy.pine`; REUSES `sos_fade`'s engine + SOS Fade sequence + fill machinery, adds only the B-LEG tracker + a thin execution subclass. Built + 19 unit tests green. **Pine-parity GREEN (exit 0), latest 2026-07-31** on a fresh 6,329-bar 15m export off the session-window build (`--warmup 800`; the longer skip is a partial chart export, not a mask) — harness is `tools/compare_bleg.py` + `strategies/tradingview/b_leg_strategy_export.pine`, wired into `verify_parity.py`. ⚠ **STILL NO ESTABLISHED EDGE, but the DEFAULTS MOVED 2026-08-06 and the old figures no longer describe this bot.** Shipped now: **112 trades / +12.02R / PF 1.23 / maxDD −8.89R over 7.9 years with spread and swap charged**, against **59 / −1.73R / PF 0.94 / maxDD −16.00R** on the same bars and charges before the change — and both halves of the history are positive where the old defaults lost 8R in the first. **Two defaults did it: `exec_trail_pct` 1.0 → 0.05 and `bleg_max_days` 1.25 → 4.0 (Pine `maxval` 3 → 6).** 🔴 **Neither was a tuning miss. The trail step is a percent of PRICE while a B leg's whole 1R is 0.13%–1.25% of price, so the inherited 1.0 made one step larger than the entire risk and the ratchet was INERT — the runner banked exactly +1.00R (a B leg's TP1 is 1R by construction) and handed back the rest, on 9 of 50 measured trades, one after running +6.82R. And the staleness `maxval` of 3 was cutting off the best region, so 1.25 was a cap nobody had checked rather than a value anybody chose.** ⚠ **The 95% CI on mean R is −0.140 → +0.355 and still contains zero** — the measurement moved up and narrowed, it did not become an edge. ⚠ **Four levers were measured and REJECTED** (the minimum-stop guard does nothing here; the deeper 0.618 entry is a 28-trade first-half mirage at PF 2.43; shorts-only is the same mirage in the other half; and dropping the SOS Fade priority gate — this bot's own documented first tuning candidate — adds one trade and it loses), and **one unshipped lead is recorded** (no Asia/late-day entries: 79 trades / PF 1.37 / maxDD −4.98R, positive in both halves, but it is new code on both sides rather than a default). **Still not a candidate for bot #2.** ✅ It DID pass the SOS Fade/B-LEG overlap audit comfortably — **45 shared bars in 157,004 and ZERO of them same-side, re-run 2026-09-01** (the 27-bar figure this line carried was the 2026-08-04 run, measured on a B-LEG that no longer existed and superseded twice since). Figures: root `CLAUDE.md` → *Trading Philosophy*; gate record: `docs/LIVE_TRADING_PIPELINE.md` → G14. ⚠ Re-run `backtest/tools/overlap_audit.py` INSIDE any change that moves either bot's entry logic — it has gone stale twice by being left until afterwards. Full rules in `python/b_leg/CLAUDE.md`. |
| `ny_orb.pine` | — | tradingview | **In TradingView research/tuning (2026-06-20), not yet promoted.** NY Opening Range Breakout, instrument-agnostic (FX + futures). Built on `london_breakout.pine`'s skeleton. Range = wick-to-wick high/low of the opening window; sessions anchored to `America/New_York` (DST-safe). Entry = break candle (excluded from count) + N direction-filtered confirmation closes (`confirmCloses`, 0 = enter on the break candle itself; bullish closes for longs, bearish for shorts). Two entry methods: **Breakout Close** (market) and **Retest** (limit at the broken box edge). Far-side stop, RR target, optional partial + step-trail. Win/loss boxes recolour like London Breakout (no labels). Guards: forced `orderQty` (futures otherwise round to 0 contracts — see notes), weekend skip, and a volume-based thin/holiday-day filter (Pine has no calendar; OR volume < % of lookback average ⇒ skip). |

---

## Operational gap — NT8 auto-start on VPS reboot

NT8 does NOT need active RDP to keep running — strategies execute fine after disconnect. The gap is restarts: if the VPS reboots or NT8 crashes, nothing brings it back automatically.

MT5 bots use `SYS_STARTUP` (Windows scheduled task, "run whether logged on or not"). NT8 has no equivalent. Until it's built, a VPS reboot requires manual RDP to restart NT8 and reload strategies.

To fix: add a Windows scheduled task (trigger: At startup, run whether user is logged on or not) that launches NT8 and loads the active strategy set. Model it on `SYS_STARTUP` in `algos/`.

---

## TradingView (Pine) gotchas — learned on `ny_orb.pine`

- **No trades on futures = order-size/margin, not the script.** TV's Properties "order size" defaults to a cash/% value; one expensive futures contract (NQ ≈ $420k notional, MES ≈ $27k) divided by that rounds to **0 contracts**, or fails the 100% margin check against a small initial capital → every order rejected. FX fills because one unit is tiny. Fixes: pass an explicit `qty` (the script forces `orderQty`), set Properties order size to **Contracts**, raise initial capital, or lower margin %. Use the `SYMBOL1!` continuous contract (e.g. `MNQ1!`) and prefer micros for eval-sized accounts.
- **OR window ≠ chart timeframe.** A 15-min opening range on a 15-min chart is one candle and barely trades; run it on 1–5 min bars.
- **The volume thin/holiday filter is a backtest-only proxy.** Pine has no holiday/economic calendar. Live, the correct pattern is a shared calendar/event-gate service (like the regime classifier) that every bot checks before trading — it's proactive and also covers high-impact news (which is high-volume, so the volume filter misses it). Keep the volume proxy for TV research only.
- **Pin `slippage = 0` AND `margin_long/short = 0.2` in the `strategy()` call, not the Properties UI.** The `.pine` strategy files (`sos_fade_strategy`, `sos_fade_strategy_export`, `b_leg_strategy`, `ny_orb`, `london_breakout`) declare `slippage = 0` (2026-07-23) and `margin_long = 0.2, margin_short = 0.2` (2026-07-24), so the Strategy Tester Properties tab defaults to zero slippage and 500x leverage (margin % = 100 / leverage) to match Aaron's demo account. Both are broker-emulator SETTINGS, not signal logic: TV slippage is a flat per-fill cost (in ticks; 25 ticks = $0.25 on gold) that is neither honest (a resting limit never slips) nor comparable to a zero-cost Python bar-mode run, and margin only sets the leverage the tester assumes. Model real costs in the LAB's tick fill model instead. The breakeven buffer is a strategy INPUT (signal logic), not a cost — leave it alone.

- **"Trades on chart" (Style tab) CANNOT be pinned from code, and it is the cousin of the bullet above rather than another instance of it.** `slippage` and `margin_long/short` ARE `strategy()` arguments, so the Properties tab can be defaulted; the Style tab's trade markers are not. Checked 2026-08-12 against TradingView's Pine reference and its Strategies FAQ, which says trade-marker visibility is chart-side UI with no Pine equivalent — `display = display.none` works on a `plot`, and the markers are not a plot. **It is a per-INSTANCE setting: it survives ordinary code saves and returns only on a fresh add or a "Reset settings to defaults"**, so untick it in the same visit as any reset. ⚠ **On the `indicators/` strategies it is not cosmetic — it DOUBLE-DRAWS.** Those files draw their own position box, entry triangles, TP tags and result label, and `execShowPosBox` says it *replaces* the built-in markers, which it only does if they are off; leaving both on puts two renderings of one trade on the same candles, at two different exit prices whenever a partial filled. Full note: `indicators/CLAUDE.md`.

## References

- `mt5/LONDON_BREAKOUT.md` — LondonBreakout design notes, v3 reshape detail, and backtest record
- Build history (foundational config rules, NT8/MT5 deployment manager, this directory's creation) is in git history.
- `command-center/backend/CLAUDE.md` — scanner, deploy endpoint, sync-status logic, MT5 agent client
- `command-center/frontend/CLAUDE.md` — Strategies page, Deployed tab, Deploy button, MT5 compile button
- `algos/markets/fx/tools/mt5_agent.py` — MT5 agent on VPS (port 8766); owns the Experts folder write path
