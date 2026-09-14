# Notes — Parity gate history

Every run of compare_extreme_leg.py — the RED-then-GREEN 2026-09-02 session, the weekly-sweep timing bug it found, the 2026-09-03 warm-up fix, how to re-run the gate by hand, the deliberate Python/Pine behaviour differences (na handling, refusal code 7, bid_ask_fills), the missing-column refusal, and the fresh export now committed as the golden. Moved VERBATIM out of `strategies/python/extreme_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The parity gate — GREEN on a fresh export, and the warm-up was the fault (2026-09-03)

🟢 **GREEN on `engines/VANTAGE_XAUUSD, 5_821a8.csv` — 18,248 bars compared, exit 0**, at the
derived warm-up of 2,016 bars.

🔴 **IT READ AS FOUR DIVERGED FIELDS AND IT WAS ONE COLD-START BAR.** The tool's `--warmup` default
was a flat **1000**, which on a 5-minute chart is ~3.5 days — **less than a week**. The weekly
level had therefore not formed on the Python side, while the chart carries history from before the
export window and already had one. MEASURED family by family over 19,265 compared bars: **exactly
ONE disagreement, in the weekly-high family; h4, session, daily and weekly-low were all 0.** The
other three fields (`px_high_age` for 375 bars, the arming and the family count) all cascade from
that single bar.

⚠ **The `--warmup` help text had predicted this exact failure in writing — *"the weekly level needs
a completed week… too LOW is the failure that wastes a day: it reports a cold start as a logic
bug"* — while its own default was too low to satisfy it.** A warning next to a wrong default is
worth nothing; the default is now DERIVED (`derived_warmup`): one calendar week at the export's own
timeframe, floored at the 1000 that seeds the 15m structure, and only widened when the weekly
family is on. ⚠ **A typed number cannot be right for both frames** — 1000 bars is over a week on
15m and a third of one on 5m.

🔴 **THE DERIVATION WAS INSIDE `main()`, WHERE NO TEST COULD REACH IT, AND ALL THREE OF ITS FIRST
MUTATIONS SURVIVED THE WHOLE SUITE** — two were caught only by one real export on one machine and
the third by nothing at all. It is a function now, with four tests, each watched RED. Same lesson
as the trade box and the period window: **logic with no seam a test can grab is logic nobody
checks.**

⚠ **This does NOT widen what the gate covers.** The export still spans 2026-05-24 → 2026-09-03 with
7 entries, and refusal codes 2, 4, 5 and 7 are still never reached. A green run here is a NARROW
green, and the warm-up growing by 1,016 bars made it slightly narrower still.

## The parity gate — RED, then GREEN the same day (2026-09-02)

✅ **THE SECOND RUN IS GREEN.** `engines/VANTAGE_XAUUSD, 5_29058.csv`, 21,328 M5 bars, 20,327
compared: *the Python made the same decisions as the Pine on every compared bar.* The export was
taken off the regenerated twin, so it is the first one that carries the weekly-level fix below —
**the same window, the same shape, and the ten disagreements gone. That is what confirms the fix,
rather than the argument for it.**

⚠ **WHAT A GREEN RUN HERE DOES NOT SAY, stated before the number gets quoted without it:**
**7 entries, 3.5 months, and refusal codes 2, 4, 5 and 7 never reached once.** Everything this
package has measured over 6.6 years — the trade counts, the R, the two cuts, the clash audit — sits
on bars this gate has never seen. **It proves the port, not the numbers.**

🔴 **THAT COVERAGE IS A CEILING, NOT A FIRST ATTEMPT — STOP CHASING A WIDER EXPORT**
(Aaron, 2026-09-02: *"I gave you as much export as TV allows"*). Both exports taken for this gate
came back at ~21,300 M5 bars over the same ~3.5 months, and scrolling further loads no more history
on that account. ⚠ **Earlier revisions of this very file called a wider export the single most
valuable thing anyone could add to this strategy, which sends the next reader at a door that does
not open.** ⚠ **It does not retire the warning above — it makes the warning PERMANENT.** The
only two routes to wider gate coverage are a COARSER frame (the same Pine on 15m reaches three
times the calendar for the same bar count, but that is no longer the strategy that ships) or a
fresh export taken months from now and read as a NEW window rather than a longer one.

### The first run, and why it was worth reading rather than explaining away

Export: `engines/VANTAGE_XAUUSD, 5_2b302.csv`, 21,320 M5 bars **2026-05-17 → 2026-09-02**,
20,319 compared after warm-up.

```
✗ 7 field(s) diverged — px_high_age, px_swept, high_armed, px_high_fam,
                        px_low_fam, low_armed, px_low_age
```

✅ **EVERY ONE IS THE SAME SINGLE CAUSE, AND IT IS PREDICTED DISAGREEMENT #1 IN THE TABLE BELOW.**
Decoding the sweep column family by family over the 20,319 compared bars:

| family | only the CHART saw it | only PYTHON saw it |
|---|---|---|
| H4 low / high | 0 | 0 |
| session low / high | 0 | 0 |
| daily low / high | 0 | 0 |
| **weekly low** | **3** | **3** |
| **weekly high** | **2** | **2** |

**Ten bars in 20,319, all weekly, and each appears on both sides because the sweep is TIMED
differently rather than missed.** Everything downstream — the ages, the family counts, the two
armings — cascades from those ten.

✅ **PREDICTED DISAGREEMENT #2 IS GONE, WHICH CONFIRMS THE SESSION FIX.** The session families
agree on every one of the 20,319 bars. That fix was made on 2026-09-01 against a cross-map, with no
export to check it; this export checks it.

🔴 **THE PINE WAS THE ONE THAT WAS WRONG, AND IT DISAGREED WITH ITS OWN PARENT.** Its sweep tracker
took EVERY family on a wick. `engines/liquidity/` takes a weekly level only on a **CLOSE** through
it (`engine.py:228`, citing `mpc_jarvis.pine` line 1427) and the lower families on a wick — so
the house engine and the parent indicator agreed with each other and this strategy file was the odd
one out. ✅ **Fixed in `strategies/tradingview/tools/build_extreme_leg.py`** (`f_track` gained a
close-through mode, passed only for weekly). ⚠ **The direction was decided by the house standard,
not by which rule made more money** — same call as the session clock. Do not re-optimise around it.

⚠ **NO PYTHON BASELINE MOVES.** This side already followed the engine; only the chart changed.
Every figure in this file and in `strategies/tradingview/docs/extreme_leg_strategy.md` stands.

🔴 **NOT ONE TRADE DIVERGED — AND THAT IS A NARROWER CLAIM THAN IT SOUNDS.** No entry, stop,
target, fill, R or equity column appears in the diff, so on this window the ten weekly-sweep
differences never reached a position. But the window is **3.5 months, not 6.6 years**, and it
contains only **7 entries**. **Refusal codes 2, 4, 5 and 7 were never reached at all**, so this run
says nothing whatever about them. A green re-run on this same export would still be a narrow gate.

⚠ **The next export must come from the REGENERATED twin.** The one above predates the weekly fix,
so re-running the gate against it will reproduce the same ten bars for ever.

---

## Re-running the gate (stage 4 is the one step only a human can do)

✅ **Done once, green, 2026-09-02** — but it must be re-run after ANY change to either side, and
the export cannot be regenerated by anything here. A human opens
`strategies/tradingview/extreme_leg_strategy_export.pine` on a XAUUSD **5-minute** chart, scrolls
LEFT until the chart stops loading history (the export only holds what the chart has loaded — this
is the lever that widens the narrow coverage above), and takes *⋮ → Export chart data → Bar data and
indicator values*. Then:

```bash
python3 strategies/python/extreme_leg/tools/compare_extreme_leg.py '<export>.csv' --warmup 1000
```

🔴 **A TRADE LIST IS NOT AN EXPORT, and the refusal that says so was UNREACHABLE until 2026-09-02.**
The first real file handed to this gate was a trade list (Strategy Tester → List of Trades), and it
did not refuse — it died with a traceback out of `sos_fade`'s loader saying *export has no
'time' column*, which points the reader at a different strategy's module. The check ran AFTER the
shared loader, and the loader raises first. It now reads the HEADER before anything else and names
the exact menu to use instead.

🔴 **Its test passed the whole time, and that is the part to keep.** The fixture was a bar CSV with
a `time` column and no sequence column — a shape TradingView never produces. **A fixture more
capable than the real thing describes a system you do not have**, and the assertion happened to
match text in the old message, so nothing looked wrong. The fixture is now the real header from the
file that arrived, BOM included, and there is a second case for a wrong-script export that is *not*
a trade list, because naming a fault a file does not have sends somebody to the wrong menu.

The twin plots 62 per-bar columns so a disagreement lands on a named column at a named bar; a trade
list says two runs disagree and nothing about where.

⚠ **The twin and the strategy are GENERATED FROM ONE BODY** by
`strategies/tradingview/tools/build_extreme_leg.py`, so they cannot drift. Edit the generator, never
either `.pine`. The build asserts the bodies are identical apart from the title and the appended
export block.

---

## The one known disagreement left, and the two that were fixed

Found 2026-09-01 by diffing the Pine against the study that measured this strategy. Three root
causes; the port inherits only the first, and it was fixed on the Pine side.

| | What differed | Where it is now |
|---|---|---|
| **Session clocks** | The Pine read three fixed session strings with **no timezone**, so all three resolved in the symbol's EXCHANGE clock (New York). Two windows tracked no real session; the one labelled "London" was the New York session under a wrong name — its high and low equalled the house NY session's on **100.0%** of 38,747 M15 bars, while the other eight pairings agreed on 0.0–8.0%. | ✅ **FIXED IN THE PINE.** Each window now names its own city, matching `indicators/engines/mpc_jarvis.pine` — which always passed the timezone — and `engines/sessions/`. |
| **When a sweep is stamped** | The study dates a sweep at the 15-minute bar's CLOSE; the strategy dates it on the 5-minute bar that crossed. The study's freshness window reaches 5–15 minutes further back. | ⚠ **STUDY ONLY.** This port runs the liquidity engine on the chart's own bars, so it stamps where the Pine does. Recorded in `backtest/tools/pre_sos_leg.py`. |
| **What freshness is counted in** | The study counts wall-clock MINUTES; the strategy counts BARS. They part company across a weekend. | ⚠ **STUDY ONLY.** This port counts bars. Same record. |

🔴 **THE CONSEQUENCE FOR EVERY NUMBER THIS STRATEGY HAS: the grid, the timeframe answer, the two
filters and the cost bill were all taken through the study, so they describe an arming rule
marginally LOOSER than the file being traded.** They are not wrong and they are not re-measured
here — the gate is what settles it.

⚠ **The session fix CHANGES WHAT THE STRATEGY TRADES.** It is a correction, not a tuning: the
direction was decided by the house standard and by the Pine's own parent, never by which clock made
more money. **Do not re-optimise around it** — picking a session clock for its P&L is picking a
result and calling it a rule.

---

## What this side does that the Pine does not, and why

🔴 **Pine's `na` is a float NaN here, not `None`.** Every refusal in the ladder is a comparison
against a value that may not exist — no swing, no average range for the first 49 bars. Pine reads
`na < 2.0` as false; Python's `None < 2.0` raises and `nan < 2.0` is **False**, the same answer for
the same reason with no guard anywhere. ⚠ **Adding an `isnan` check to any branch of
`_ladder` makes this side refuse where the chart does not** — there is a test that goes red on
exactly that. It is a parity device and nothing else; the repo's "no answer vs measured zero" rule
still uses `None`, which is why the sweep ages do.

🔴 **Refusal code 7 has no Pine counterpart, deliberately.** With no average range yet the stop is
`na`, every refusal above declines to fire, and the Pine reaches its entry call with an `na`
quantity. That is a warm-up bug, not a trade. This side refuses and records why, loudly, into the
blocked list — a divergence nobody can see is the worse half. It can only fire inside the ATR
warm-up, which every gate run excludes anyway.

⚠ **The 15-minute half instantiates the canonical structure engine a second time** rather than
copying it, and reads one private field (`_ext.ash` / `_ext.asl`) behind a guard, because the
public event stream fires on CHANGE and a target is a live STATE. Same call, same reason, as
`backtest/tools/pre_sos_leg.py`. A rename upstream fails on construction rather than scoring
nothing.

⚠ **A profile with `bid_ask_fills` on is REFUSED, not approximated.** That flag moves fills rather
than charging a cost, so honouring half of it would report a trade list neither model produces.
It is one of TWO models of the same cost — flat round-trip charge, or moved fills — never a layer
on top, so a run that asks for both is billing the spread twice.

🔴 **THE REFUSAL NAMED THE WRONG DIAL FOR ITS WHOLE LIFE, AND THAT COST A READER A SESSION
(2026-09-02).** It read *"account profile 'lab:puprime_ecn' has bid_ask_fills on … Use a profile
with bid_ask_fills off"*, so the reader went looking at the BROKER. The broker supplies only the
spread's SIZE; the flag is switched on by the run's own cost options
(`python_runner._profile_for`), which means **every account fails identically and no amount of
changing brokers can clear it.** The message now names the run's cost options, says which box to
untick, and says plainly that the spread is still charged — because *"it refuses costs"* was the
other conclusion a reader reasonably drew from it. ⚠ **The generalisation is worth more than the
wording: a refusal that names the wrong dial is WORSE than a bare stack trace, because the reader
trusts it and searches where it points.** A refusal must name the control the reader can actually
move. Pinned by `test_the_refusal_points_at_the_run_option_and_not_at_the_broker_account`, watched
RED by restoring the old string.

---

## 🔴 An export missing a compared column is REFUSED (2026-09-10)

The wrong-FILE refusal above held, but the diff skipped any table column the export lacked, so a
partial export passed over the rest. **Now exit 2, naming the missing columns**, through the SOS Fade
gate's shared `missing_columns_refusal` (`strategies/python/sos_fade/CLAUDE.md`). ⚠ **The test holding
this file's synthetic export to the twin's own plot titles caught a real misread on its first run**:
the settings-flags plot wraps across two lines and the reader took one line at a time.

## A fresh export, green, and now COMMITTED as a golden (2026-09-10)

`compare_extreme_leg.py` exits 0 on a fresh export of the twin — 20,288 M5 bars, 2026-05-31 →
2026-09-10, all 18,271 bars after the gate's derived one-week warm-up matching. It overlaps the
first export (2026-05-24 → 2026-09-03) and adds a week, so the coverage is the SAME narrow shape:
**7 entries, refusal codes 2, 4, 5 and 7 never reached.** ✅ Committed at `exports/golden/`, so
step 15 runs this gate on every clone.
🔴 **Its two caveats would have vanished under that step's tick**, because the runner keeps only
a passing gate's 🔴/⚠ lines. The not-the-shipped-strategy qualifier now prints as two ⚠ lines that
read alone, and the unreached codes as one ⚠ line naming them.
`test_the_caveats_survive_a_runner_that_keeps_only_warning_lines`, three mutations watched RED.
