# CLAUDE.md — Extreme Leg (Python port)

**Purpose:** The Python side of `strategies/tradingview/extreme_leg_strategy.pine` — the leg
that runs INTO the shift of structure, which is the move the SOS Fade bot's setup begins after.
**Scope:** This package only. The strategy's design and the evidence behind each default live in
`strategies/tradingview/docs/extreme_leg_strategy.md`; the porting process lives in
`docs/STRATEGY_WORKFLOW.md`. Neither is restated here.
**Every sweep run on this bot is `extreme_leg_optimization.md`, next to this file — read it
BEFORE proposing a tuning idea.** Four searches have each landed back on the shipped settings, and
a cut is scored on the setup pool BEFORE the one-position rule or its number is fiction.
**Status:** ✅ **PARITY GREEN — `compare_extreme_leg.py` exits 0 (2026-09-02).** Stage 6 of six is
done: the Python makes the same decisions as the Pine on every one of 20,327 compared bars.
✅ **Re-run green on a fresh export 2026-09-10, now committed as step 15's golden** — last section.
⚠ **READ THE COVERAGE BEFORE QUOTING THAT.** The export is **3.5 months with 7 entries**, and
**four of the eight refusal codes were never reached at all** — a green gate says the two
implementations AGREE, never that either is RIGHT, and says nothing about a branch neither entered.
The 6.6-year figures in this file were measured on the Python alone and are **not** covered by it.
**Last reviewed:** 2026-09-01

---

## Registering in the lab — and what running the scanner found

`LAB_STRATEGY` in `__init__.py` is the whole opt-in; the scanner imports the package and reads it.
MEASURED by actually calling `services.strategy_scanner._parse_python_package` on it rather than by
reading the dict and agreeing with it: **22 settings, 20 of them labelled from
`extreme_leg.meta.json`, 12 marked core, 4 steps, `display_under` honoured.**

🔴 **IT WAS 25 SETTINGS UNTIL THAT CALL, AND THREE OF THEM SHOULD NEVER HAVE BEEN THERE.** The
structure length, the 15-minute aggregation and the ATR length are HARDCODED in the Pine — no
input, therefore no `cfg_*` column, therefore nothing a parity gate could ever check. As config
fields each drew a row on the strategy page under its raw field name, and a run that moved one
would have diverged from the chart with nothing anywhere to say so. They are keyword arguments on
the strategy now: a test can pass one, the lab cannot see one. ⚠ **This is `config.py`'s own
opening rule catching `config.py`** — and the only reason it was caught is that the registration
was RUN. A dict that looks right is rule 7 exactly: a label is a claim about code somewhere else.

⚠ **The two remaining unlabelled settings are deliberate** — what a lot is worth and which
instrument. TradingView puts both on the Strategy Properties tab rather than in an input, so no
export column can carry them; the SOS Fade bot exposes the same pair the same way.

## The tests, and what they are worth

```bash
python3 -m pytest strategies/python/extreme_leg/tests -q       # 54 tests
# ~2 min serial. Under the suite's own `-n auto --dist load` it MEASURED 24s on an idle machine and
# 52s on a busy one — quoted as a range because both readings are real and a single number here
# would be the tighter one, which is the reading nobody reproduces.
```

`tests/test_extreme_leg.py` — 39 hand-traced rules, ~2s. **Every one was watched RED, and each
docstring names the mutation that does it**, so the next reader can repeat it in ten seconds
instead of trusting a sentence.

`tests/test_compare_extreme_leg.py` — does the GATE work. 🔴 **It cannot prove Pine parity and must
never be read as if it did**: it builds a synthetic export from this side's own decisions and feeds
it back, so it only checks the gate's plumbing — column names, the two bit schemes, settings
decoding, row alignment — and that a disagreement is DETECTED AND NAMED. Each case moves one column
or flips one bit and asserts the gate fails and says which.

⚠ **Each distinct gate replay runs ONCE per file (2026-09-10), keyed on the settings the gate
DECODED plus the bars byte for byte** — most cases change only a Pine-side column the replay never
reads. The undisturbed export still runs as a separate process, the command a person runs. 🔴 **The
key is the decoded config, never the file's**: a gate that stopped reading a setting would decode
the defaults and replay the default book, and go red exactly as it would with nothing remembered.
🔴 **One hole was found on the way and SURVIVED the committed file too**: no case moved an on/off
setting, so a gate ignoring every switch stayed green. `test_gate_reads_the_ON_OFF_settings_off_the_
export_too` closes it; mutation map in the file.

⚠ **The twenty column checks are ONE process, not twenty, and that is a stronger test rather than a
cheaper one.** Each case re-runs the strategy in a subprocess; twenty of those cost more wall clock
than everything else here put together, on a suite whose speed is a standing rule. Moving every
column at once also proves the gate's reporting is neither capped nor first-only, which a
per-column loop cannot show at all. Three columns keep an isolated case, one per KIND that fails
differently: a price carried through the whole ladder, a bit-packed column, and a refusal code.

🔴 **The fixture's WINDOW IS MEASURED, and the first version of it was wrong in the way this repo
keeps meeting.** Bars 0–6,000 of the cache contain armings and refusals but **not one accepted
setup**, so the test that raises the minimum-target setting passed against a gate that could not
have failed. Bars 12,000–20,000 carry 6 acceptances and refusal codes 0/1/3/6, and the fixture now
ASSERTS an acceptance, a refusal and an opened trade rather than hoping for them. Re-measure before
moving those numbers.

---

## Never do

- Quote a number from this package as a measurement before `compare_extreme_leg.py` exits 0.
- ⚠ **Or read the green run of 2026-09-02 as covering the 6.6-year figures.** It compared 3.5 months
  and 7 entries; every headline number here was measured on bars it never saw. The gate proves the
  PORT, not the numbers, and those are different claims.
- Allow a second concurrent position. Every result this strategy has was measured with one slot,
  and the reason a filter pays here is that refusing a setup genuinely buys the next one.
- Fork `engines/liquidity/` or `engines/sessions/` to make this side agree with a Pine. When they
  disagree, one of them is wrong and the gate says which — see the table above for how that went.
- Add a field to `ExtremeLegConfig` that has no Pine input behind it. No `cfg_*` column can carry
  it, so the gate would leave it at this side's default and never see a disagreement about it.

## The frame it is measured on is DECLARED (2026-09-03)

`LAB_STRATEGY["suggested_bar_value"] = 5` — its Pine is exported from a 5-minute chart and its gate is 21,328 M5 bars. The lab reads it and every form fills a leg's
timeframe box from it, so nobody has to remember which bot runs on which frame.

⚠ **It is a DEFAULT, never a refusal.** Nothing rejects a run on another frame — sweeping a bot
across frames is a real question — so a figure quoted off a different frame is a DIFFERENT
EXPERIMENT from every number in this file, and has to say so.

🔴 **Why it had to be declared: the stack page had ONE timeframe for the whole stack**, so a 5m
bot and a 15m bot on one account meant one of the two was replayed on a frame nobody has ever
measured it on — and the combined table said *portfolio*. Rules for the lab side:
`command-center/backend/CLAUDE.md` → *A stack leg runs on its own frame*.

## `full_exit_price()` — this bot's target always takes the lot (2026-09-09)

Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`). The bridge
hands the answer to the broker so the exit fills AT its price rather than at market when the
5-minute bar shuts.

🔴 **TWO LINES HERE WHERE SOS Fade NEEDS A BRANCH PER TRADE KIND**, and that asymmetry is why this is
a question each strategy answers rather than a shared helper. There is no rung ladder in this bot:
`_close` books the whole position at `take_profit` and the trade record says so
(`tp_rungs=((take_profit, 100.0),)`). **Neither strategy can answer for the other.**

⚠ **An INFINITE target means there is none, and it is a real state this strategy produces** —
`_close` and the trade record both test `math.isfinite` for exactly it. Passed through, the bridge
would hand a venue an infinity and the refusal would name a number nobody chose. ⚠ **Zero likewise**:
it reaches MT5 as *no take-profit at all*, which is an instruction rather than a price.

⚠ **`None` while FLAT**, or the last trade's target lands on whatever opens next.

🔴 **THIS BOT WAS THE REASON THE WORK WAS NEEDED AND IS THE SECOND TO GET IT.** Its live trade on
2026-09-09 (T367577331, long, target 4406.895) opened with **`TP=0.00` at the broker**, so it would
have closed at market on a 5-minute bar close. The target was put on that position BY HAND; this is
the mechanism that makes the next one automatic.

**Tests: 4 in `tests/test_full_exit_price.py`, 2 mutations RUN and both red.**

✅ **PARITY GREEN after the change** — `compare_extreme_leg.py` on `VANTAGE_XAUUSD, 5_821a8.csv`,
exit 0 at the DERIVED warm-up. ⚠ **Let the gate compute its own warm-up.** Passing `--warmup 500`
or `1000` by hand OVERRIDES a larger derived value and reports a cold start as four diverged
fields — that happened twice on 2026-09-09 and read as a red gate both times.

## `planned_full_exit_price` is always `None` here, and that is a FACT rather than a stub (2026-09-09)

The live contract asks every strategy where an order it is PLACING would close a whole position, so
the target reaches the broker in the same message as the stop. **This bot answers `None`, always.**

🔴 **NOTHING IS LOST BY IT, AND SAYING SO IS THE POINT OF THE ENTRY.** This strategy declares it
enters at MARKET: it fills inside its own emulator on the bar's close, so by the time the bridge
sends an order the position is already open and the bridge asks `full_exit_price` instead — the
EXACT price, not a forecast. **A resting strategy is the one that has to estimate; this one never
does.** A future reader meeting a constant `None` will otherwise read it as a missing feature.

⚠ **Two tests pin it**, and the second is the one that matters: it holds a trade with a perfectly
good target and still asserts `None`. Returning the open trade's target here would put a target
meant for the position already held onto the next order placed — and because this bot is always
already open when an order goes out, **that would read as correct in every log**. Watched red.

⚠ **PARITY RE-RUN AND GREEN.** `compare_extreme_leg.py` on `VANTAGE_XAUUSD, 5_821a8.csv` — 20,265
bars, 2026-05-24 → 2026-09-03, warm-up 2,016 derived, **18,248 bars compared, exit 0**. ⚠ Coverage
unchanged and still narrow: **6 entries, and four refusal codes never reached**. ⚠ The gate still
cannot see the shipped form — the market-condition cut is ON in config and the chart cannot make it.

## This bot reads TWO engines, so only two are RUN (2026-09-10)

`engine_config()` now declares `fib`, `sniper`, `macro`, `internal`, `fvg`, `rsi` and `sessions`
all **False**. `step()` is the whole of what this strategy sees of the engine stack and it reads
exactly `bar_state.bar`, `bar_state.structure.external` and `bar_state.liquidity.mitigated`. The
other seven engines produced output nothing looked at, on every bar of every replay, optimizer
combo and sweep this bot has ever run.

🔴 **THIS BOT IS THE EXPENSIVE HALF OF THE STACK AND THE ONE THAT READS THE LEAST.** It runs on
5-minute bars — three for every one the 15m leg sees — so its engine stack is stepped 471,000 times
over the full window against the other leg's 157,000. **MEASURED on 190,159 real M5 bars, best of
three interleaved runs: the two engines it reads cost 11.89s against the full stack's 26.91s —
44.2%.**

✅ **PROVEN RESULT-IDENTICAL.** The live two-bot stack replayed twice in one process — every engine
on, then gated — over 2020-01-01 → 2026-09-06: **361 trades either way, identical on every field of
every record**, 277.5s → 182.6s for the whole stack.

🔴 **NO PARITY GATE HAS RUN FOR THIS, AND IT IS NOT A FORMALITY.**
`compare_extreme_leg.py` needs an export and **no extreme-leg export is on this machine** — the
`VANTAGE_XAUUSD, 5_821a8.csv` this file names elsewhere is not here. That is the "9 of 14 gates
could not answer" condition the root doc records. **The A/B replay above is this bot's evidence and
it is a different claim: it says the gated stack produces the same book as the ungated one, never
that either agrees with the Pine.** Re-run the gate on the next export.

⚠ **A switch is a CLAIM about what this package reads.**
`backtest/tests/test_replay_engine_gates.py` parses every module here and fails by name if one
starts reading a gated engine — because the failure is otherwise silent: a gated engine hands back
`None`, and `None` read as *nothing happened this bar* is a bot refusing every setup with every
dashboard green. Rules and the measurement: `backtest/CLAUDE.md` → *An engine a strategy never
READS is never RUN*.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 59 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/parity_gate.md` — Parity gate history

**Read before touching:** compare_extreme_leg.py, re-running the parity gate, or wondering why the Python disagrees with the Pine on a specific field.
Most-cited code: `extreme_leg_strategy`, `compare_extreme_leg.py`.

- The parity gate — GREEN on a fresh export, and the warm-up was the fault (2026-09-03)
- The parity gate — RED, then GREEN the same day (2026-09-02)
- Re-running the gate (stage 4 is the one step only a human can do)
- The one known disagreement left, and the two that were fixed
- What this side does that the Pine does not, and why
- 🔴 An export missing a compared column is REFUSED (2026-09-10)
- A fresh export, green, and now COMMITTED as a golden (2026-09-10)

### `notes/portfolio_ui.md` — Strategies page placement, account sharing, and display labels

**Read before touching:** the Strategies page nesting, running this bot in a shared-account stack, or its chart/label text.
Most-cited code: `extreme_leg.meta.json`.

- It is a TOP-LEVEL row on the Strategies page, not a child of the SOS Fade bot (2026-09-02)
- It can share an account now (2026-09-02)
- Its chips say XLEG, not SOS Fade (2026-09-02)
- Two minute settings carry a SHORT name (2026-09-13)

### `notes/market_news_cuts.md` — The market and news cuts, and the cached-history study

**Read before touching:** the regime/news cuts on this bot, or citing its trade-count/R figures.
Most-cited code: `extreme_leg_strategy`.

- The two cuts TradingView cannot make (2026-09-02, Aaron's call)
- What it does over the cached history — and what that is and is not

### `notes/chart_and_live.md` — Chart rendering and going live

**Read before touching:** the backtest chart drawing this bot's trades oddly, or wiring/debugging it as a live bot.

- What the CHART draws: entry, DD, best, exit (2026-09-02)
- It can be a LIVE bot now — the seams, and why they cost the replay nothing (2026-09-03)

### `notes/lab_settings_history.md` — A lab setting that was probed but never read

**Read before touching:** adding a new setting to extreme_leg.meta.json or wondering why the stress tester probes a setting with no effect.
Most-cited code: `extreme_leg.meta.json`.
