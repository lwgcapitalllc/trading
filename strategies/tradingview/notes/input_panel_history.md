# Notes — The input panel contract — build history

The dated build history behind the input panel contract's fixed groups: why section 2's four toggles are fixed, why longs/shorts and the confirmation table were added to files that lacked them, why a `strategy()` argument like `pyramiding` cannot be an input, and the three passes that gave the scale-in adds a take-profit, a mode, and finally a resting limit instead of a market order. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### Section 2 is FIXED — four toggles, same order, same defaults, every file

Aaron, 2026-08-12: *"On all of my strategies, the market structure should be the exact same…
There should always be four toggles… the only thing that should be on by default is show
external structure, nothing else."*

```
Show External Structure            ON
Show Internal Structure            off
Show Historic Internal Structure   off
Show Swing Point Labels            off
```

🔴 **`d_strategy.pine` HAD TWO OF THE FOUR, AND THE MISSING PAIR WAS A MISSING ENGINE
RATHER THAN A MISSING INPUT.** That file embeds only the EXTERNAL half of
`structure_engine.pine`, so there was nothing for an internal toggle to switch. Adding the
two checkboxes alone would have shipped exactly the hazard the deleted `REQUIRED` toggles
were: a control that looks like it does something. **The internal engine is ported in
instead** — 452 lines, taken from `structure_engine.pine` rather than from a sibling
STRATEGY, because the strategies' copy also seeds the External Fib (`i_confirmed_*`) and D
has no fibs. ✅ **Proven the right source rather than assumed: the two blocks were diffed
comment-free, and the only difference is those four fib-anchor writes plus `IFIB_GREY` and
`extBreakThisBar`.** ⚠ **It draws and decides nothing** — D reads no internal swing, so this
is annotation only and cannot move a trade. ⚠ `showSwingLabels` also shipped **ON** in D
against every sibling's off.

🟢 **`h4_sweep_strategy.pine` GOT THE SECTION TOO (Aaron's call, 2026-08-12), AND IT IS
THE ONE FILE WHERE THE ENGINE DECIDES NOTHING.** That file had no structure engine at all —
it trades an H4 liquidity sweep confirmed by a candlestick pattern, consuming no swing, no BOS
and no SOS — so honouring "the exact same" there meant porting ~1,000 lines of engine purely to
draw with. It was recorded as an open decision rather than skipped, and answered *do it*.

**Lifted from `d_strategy.pine`, not from `structure_engine.pine`**, on purpose: D's copy is
the STANDARDISED one (external half + the fib-free internal port above), so taking it means all
five files share one block rather than four sharing one and H4 sharing a fifth. 880 → 1,921
lines. ✅ **Checked mechanically rather than by eye — zero duplicate top-level declarations and
zero name collisions with H4's own identifiers** (`st`, `ph`, `pl`, `bullColor`, `majorLength`,
`f_swingCol`, every `i_*`), and the block was confirmed self-contained first by grepping it for
`exec*` / `d[A-Z]*` references, which returned nothing.

⚠ **It draws and decides nothing, and the file says so at the block AND at the section.** Flip
any of the four toggles and H4's trade list is unchanged. **The comment names the condition that
would end that**: if a future rule in this file starts reading `st`, it stops being a drawing
block and the toggles stop being free — say so at the rule, because nothing else will.

⚠ **The compile-token cost is real and unmeasured.** H4 more than doubled; only a paste can say
whether it clears CE10117. If it does not, this block is the first thing to cut, and cutting it
costs a chart annotation rather than a trade.

### Trade longs / Trade shorts — every file, both ON

🔴 **`h4_sweep_strategy.pine` had NEITHER.** Added, and the wiring is the interesting
half: a refused side is **block code 5, numbered last and ranked FIRST** (a code is a wire
format `px_blk` carries into exports already on disk, so an existing number can never be
renumbered — only its place in the chain moves).

⚠ **A DISABLED SIDE DOES NOT CONSUME THE H4 WINDOW, unlike every other refusal in that
file, and the asymmetry is deliberate.** H4 allows one setup per H4 window and burns it on
any trigger, refused or not — which is right for a stop-too-tight refusal (about that
setup) and wrong for a direction switch (about every trade on that side). Burning it would
have removed LONGS that happened to share a window with a short, so "longs only" would not
have been the long book. **That is the trap this repo keeps meeting: a filter that quietly
changes the population it was not aimed at.**

### The confirmation table

Present and **default OFF** where the strategy reads one — `sos_fade_strategy.pine` and
`b_leg_strategy.pine`. **Absent from BOS, D and H4 by Aaron's own instruction**, because
none of them has a table for it to show; already the case in all three, so nothing was
removed.

---

### A `strategy()` ARGUMENT CANNOT BE AN INPUT — raise it permanently and gate it in code

**2026-08-16, `sos_fade_strategy.pine` + its export twin.** The scale-in toggle (`execScaleIn`, default
OFF) needs `pyramiding > 0` to place a second entry on an open position. `strategy()` is evaluated
**once at compile time**, so `pyramiding` can never read an input — the only options are to raise it
permanently or not to have the feature. It is **0 → 4** in both files (the base entry plus
`execScaleAdds`, whose `maxval` is 3).

🔴 **A RAISED CEILING IS SAFE ONLY IF SOMETHING ELSE REFUSES THE STACK, AND THAT WAS CHECKED RATHER
THAN ASSUMED.** All four `strategy.entry` calls that OPEN a trade in that file (two SOS Fade, two B-LEG)
are gated on `strategy.position_size == 0`, so the base entry cannot stack on itself whatever
`pyramiding` says; the only other entries are the `L-ADD*` / `S-ADD*` ids, each gated on
`execScaleIn`. **With the toggle off the file trades exactly as before** — verified on the Python
side as a bit-identical OFF path, which is the half a paste cannot show you.

⚠ **`strategy.exit` and `strategy.close` MATCH ONE ENTRY ID.** A pyramided position is N entries, so
`from_entry = "Long"` protects the base and nothing else — every add needs its own exit AND its own
close on each force-close path, or an add sits in the book with no stop while the base leaves on an
opposite SOS. That is a naked pyramid against fresh opposite structure, and it is the worst state
this class of feature can produce.

⚠ **The three inputs are appended after the LAST input in the file and carry `group = G6`.** The
group decides which panel BOX they display in; DECLARATION ORDER decides which saved chart value
they inherit. Putting them beside the other stop settings would have re-keyed every later bool, int
and float on Aaron's live chart. Prose: `docs/sos_fade_strategy.md` → `## [174]`–`## [178]`.

⚠ **NOT COMPILED, and there is no `cfg_*` column for any of the three**, so `compare_strategy.py`
cannot configure a scale-in run — the gate would go green while comparing two different strategies.
Measured result and the open design question (the add trigger is arithmetic only — no BOS, no
retest): `strategies/python/sos_fade/sos_fade_optimization.md` → Run 19.

---

### The adds got a TAKE PROFIT, and it is the one default here set AGAINST its measurement (2026-08-19)

`execScaleTpMode` ∈ {`"Ride"`, `"Prev week H/L"`, `"Prev day H/L"`, `"H4 H/L"`}, default
**`"Ride"`** — i.e. no target, which is what the measurement says. Until now the scale-in lots had no exit of their own — they rode `lStop` with
the base trade and closed pro-rata with its ladder.

**It rides the EXISTING per-add exits rather than adding new orders**, which is what keeps the
change small:

```
strategy.exit("L-AX1", from_entry = "L-ADD1", stop = lStop, limit = lAddTp)
```

One extra argument makes each add a proper OCO bracket — stop or target, whichever price reaches
first. **A `na` limit is no limit**, so `"Ride"` leaves all eight of those calls byte-identical to
what they were.

`lAddTp` / `sAddTp` require the level to be **unmitigated** (`not w_hMit` / `not d_hMit` /
`not h4HighSwept` — a swept level is not somewhere to aim at, it is a price we are past) **and**
beyond `lAddLastPx`, the price the newest add was bought at, so every lot it closes is closed in
profit. `lAddLastPx` is latched from `strategy.opentrades.entry_price()` on the bar the add fills.

⚠ **The NEWEST add, not the worst-priced one.** In `Trail` mode adds fill at successively higher
prices because the ratchet only moves one way, so the two are the same level — and Pine can name the
newest fill without keeping a running extreme. Measured equal on the full book rather than argued.

🔴 **`lAddN` IS NOT DECREMENTED WHEN THE ADDS BANK.** The ladder is capped on adds BOUGHT, so
handing the slot back would let a trade add again after banking — "scale in and out repeatedly",
a different strategy that nothing has measured. The Python mirror zeroes its lots in place rather
than emptying its list, for exactly this reason, and has a test pinning it.

🔴 **EVERY TARGET LOST TO RIDING, AND IT SHIPS ON ONE ANYWAY.** Ride **194.15R**, prev week
168.51R, prev day 157.57R, H4 146.09R — an ordering that tracks how OFTEN the target fires (0, 16,
25 and 47 banks), reproduced independently by a flat-risk-multiple control. ✅ **It shipped for ONE DAY on
`"Prev week H/L"` and was reversed to `"Ride"` on 2026-08-19 (Aaron).** He picked the target
deliberately, wanting certain money off the runners, and on the number he was given — a 4.38R gap,
INSIDE this strategy's 15.06R jitter — that was a sound trade. That number came from the run with
the live-bar bug in it; **the true gap is 25.64R, OUTSIDE the jitter**, and on the real figure he
reversed within a minute. ⚠ **A wrong measurement does not arrive looking wrong — it arrives as a
reasonable-looking number and quietly buys a judgement call, and the decision outlives the
correction unless somebody goes back for it.** Full numbers:
`strategies/python/sos_fade/CLAUDE.md` → *The adds got a TAKE PROFIT*.

🔴 **THE `limit` MUST BE COMPUTED AT THE BAR'S CLOSE, NOT RE-RESOLVED AS PRICE TOUCHES IT.** Pine
gets this right for free — `strategy.exit(..., limit=)` rests an order that is live on the NEXT bar
— and the Python mirror did not, which made `"Prev day H/L"` and `"H4 H/L"` bank **zero times in
eight years** while resolving 1,804 and 2,438 valid targets. Day and H4 levels die on a **WICK**,
the engine steps before the strategy sees the bar, so the level was already mitigated on the exact
bar the order would have filled. ⚠ **Week levels die on a CLOSE through, so weekly was immune and
the defect was invisible on the only mode anybody was watching.**

⚠ **A FIFTH `cfg_*` COLUMN LANDED WITH IT** (`cfg_scale_tp`), for the reason the four before it
exist: a trade-affecting input with no column is invisible to `compare_strategy.py` **by
construction** — the gate does not go quiet, it goes WRONG. ⚠ **The comparator decodes ABSENT as
`"Ride"`, which is the opposite of how `cfg_scale_in` is read.** "Absent ⇒ off" is safe there
because that feature shipped OFF; this one ships ACTIVE, so a config-default fallback would replay
every older export with its adds banking at a weekly level the exported Pine never looked at.

🔴 **NOT GATED YET.** No export carries `cfg_scale_tp`, so `compare_strategy.py` has never checked
this path. Rule 22 is unsatisfied until a fresh export lands with the column and the gate passes.

### The scale-in gained a MODE, and the export gained the columns it should have had first

**2026-08-17.** `execScaleMode` ∈ {`Trail`, `BOS retest`}, defaulting **`BOS retest`**;
`execScaleAdds` 2 → 4 (maxval 3 → 4) and `execScaleCapX` 1.0 → 2.0. `pyramiding` 4 → **5** (base
entry + 4 adds), which is still compile-time and still cannot be an input. `L-ADD4`/`S-ADD4` carry
their own `strategy.exit` AND their own `strategy.close` on both force-close paths — `from_entry`
matches ONE id, so a missed close leaves a naked pyramid against fresh opposite structure.

🔴 **THE FOUR `cfg_*` COLUMNS ARE THE POINT OF THIS PASS, NOT THE MODE.** The feature shipped on
2026-08-16 with NO export column at all, so `compare_strategy.py` could not configure a scale-in run
— and a trade-affecting input with no column does not make the gate quiet, it makes it **WRONG**,
diffing two different strategies and blaming whichever code the symptom lands in. Three prior
instances: `execRunnerTrail` (2026-07-26), `cfg_min_stop` (2026-07-30), `eqExemptFvg` (2026-08-06,
three days and a misdiagnosis). All four inputs are carried, not just the on/off switch.
⚠ **`cfg_scale_adds` / `cfg_scale_cap` are plotted RAW, never packed** — any pack has to round, and
a silently rounded cap mis-sizes every add.

⚠ **The new `input.string` is appended AFTER the last input of any type.** The file's last
`input.string` is ~line 95, so nothing already saved is re-keyed and no chart needs a settings
reset. ✅ `check_active_order.py` passes on all twelve strategy files; the export twin re-diffs to
exactly line 5's title.

### The add is a RESTING LIMIT now, and the market order it replaced broke the guarantee

🔴 **2026-08-18. The 2026-08-17 defaults above are REVERSED and Run 20 is VOID.** The add was
issued as a plain `strategy.entry(qty = ...)` — **a market order, which TradingView fills at the
NEXT bar's open** — while the Python booked it at the price its rule triggered on. The parity gate
caught it on `px_closed_r` at bar 1356 (2025-10-21): py **27.07R** vs pine **22.03R**, one trade,
the largest runner in the book, every decision field before it agreeing.

**What changed in both Pine files:**

| | before | after |
|---|---|---|
| `BOS retest` | detected the touch, fired a MARKET order | `strategy.entry(..., limit = _lim)` — a real resting limit |
| `Trail` | market (correct, it has no level to rest at) | unchanged |
| `lAddN` | incremented at PLACEMENT | incremented on the **FILL**, detected by `strategy.position_size` growing |
| `L-AX*` / `S-AX*` | gated on `lAddN >= n` | placed **unconditionally**, so a limit filling mid-bar is never unprotected |
| stale orders | — | **`strategy.cancel` on every add id once flat** ([doc 182]) |

🔴 **A LIMIT ORDER OUTLIVES THE POSITION THAT PLACED IT**, which is why the cancel block is a
positive check on being flat rather than a hook on each exit path — this strategy closes on a stop,
three ladder rungs, an opposite SOS and a time stop, and an ignore-list of exits is one new exit
away from being wrong.

🔴 **The order TYPE was the guarantee.** The affordability rule sizes an add against the price it is
BOUGHT at; a market order is sized at one price and filled at another. **MEASURED: as a market
order the adds turned winners of +3.41R and +1.34R into losses of −2.50R and −2.15R, against an
un-scaled worst of −2.06R over the same 182 trades.** A resting limit closes it — the fill price is
known before the order is sent, and price that gaps through a buy limit fills BETTER.

**Defaults now: `execScaleMode` `"Trail"`, `execScaleAdds` **3**, `execScaleCapX` **0.5**.** ⚠ The
add count is 3 rather than 4 for a SAFETY reason — `Trail` is a market rule by nature and still
carries a small trigger-to-fill gap, measuring zero breaches at 3 and −2.24R/−2.73R at 4. ⚠
`execScaleAdds` keeps `maxval = 4` and `pyramiding` stays 5, so the ceiling is unchanged and only
the default moved.

✅ **PARITY GREEN, exit 0** on a fresh 20,799-bar export taken at `cfg_scale_in=1 /
cfg_scale_mode=1 / cfg_scale_adds=4 / cfg_scale_cap=2` — one that genuinely exercises the feature
rather than reading all zeros. **The same gate on the same schema was RED before the fix**, which is
what makes the green worth something. Full grid and the void banner:
`strategies/python/sos_fade/sos_fade_optimization.md` → Run 21.

## 🔴 Two mid-list inserts in a week scrambled a saved chart, and the trade count fell 159 → 48 (2026-09-24)

TradingView restores a saved chart's inputs by DECLARATION ORDER within each type. On 2026-09-21
three inputs (target 1 level, target 2 level, first target in R) were inserted in the middle of
section 6, and on 2026-09-23 a fourth ("When it may add again") went between the add cap and the
add mode. **Aaron pasted the updated `sos_fade_strategy.pine` onto his saved chart and the Strategy
Tester fell from 159 trades to 48** — every input below the inserts had taken its neighbour's
value. Nothing errored and nothing on the chart said why. A "Reset settings to defaults" and
re-entering his values put it back.

- **The rule already existed** (`strategies/CLAUDE.md` → standing instructions) and was broken
  twice in three days, once by a session that had read it. **Append a new input after the LAST
  input of its type** and accept the panel reading slightly out of order.
- The fourth insert was moved to the end on 2026-09-24. The three from 2026-09-21 were **left
  where they are on purpose**: moving them now would shuffle every chart a second time, including
  the one Aaron just repaired.
- ⚠ **An export chart can look untouched while the regular chart is scrambled.** The export twin's
  settings matched its 10 Sep golden exactly, so the gate said nothing — the damage was on the
  chart nobody exports.
