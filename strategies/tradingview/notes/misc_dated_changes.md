# Notes — Other dated changes — deleted files and per-file defaults

The D strategy's deletion and the lessons it left behind, the dead-market floor added to `sos_fade_strategy.pine`, and the 2026-09-13 risk-per-trade default change. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## DELETED 2026-08-15 — the D strategy, and the lessons that outlive the file

`d_strategy.pine`, `d_strategy_export.pine` and `docs/D_STRATEGY_SPEC.md` were
removed at Aaron's instruction. Recover any of them from git history.

**Two reasons, and the second is the one worth recording.**

1. **It never earned its place.** `docs/STRATEGY_WORKFLOW.md` had it at stage 3 of 6 with the
   verdict already written: its one measurement was *indistinguishable from zero*, and nothing
   had moved on it since 2026-08-06.
2. 🔴 **Its VOCABULARY was colliding.** D described its middle leg as a "shakeout"
   (`dCtrBosMax` = "how much the shakeout may break before it stops being a shakeout"), and the
   Retail Shake Out (RSO) model now owns that word. **Two setups sharing one term in one repo is
   how a rule gets read backwards** — the same failure this file's palette and side-recording
   sections were both written about. One word, one meaning.

⚠ **Deleting the file does NOT delete what it taught, and three of its lessons are load-bearing
elsewhere in this repo.** They are kept in place deliberately:

- **The margin trap.** D's own tooltip said "10 BUSTS THE ACCOUNT". `realign_strategy.pine`
  then had to learn it again from an empty Strategy Tester report — see its entry below.
- **The palette rule.** D applied the TABLE palette to its TRADES, so a winner drew in the wrong
  colour. That is why `## THE ANNOTATION PALETTE` exists.
- **Record the side, never infer it.** `h4_sweep_strategy.pine` carries the block D paid for,
  lifted byte-for-byte, and it stands on its own now.

Every comment that pointed at the file was retargeted rather than left dangling.

## `execMinAtrPct` — the dead-market floor (2026-08-26, ON at 0.08)

`sos_fade_strategy.pine` and its export twin gained one input and one helper (`f_marketHasRange`),
ANDed into both entry placements. It refuses a setup when ATR(14) is smaller than the given share
of price. Rules, measurement and why it exists live where the code that consumes it lives:
`strategies/python/sos_fade/CLAUDE.md` → *The DEAD-MARKET floor*.

⚠ **It is DECLARED after the last `input.float` in the file, nowhere near the minimum-stop floor it
belongs beside.** That reads badly and it is correct: TradingView keys a saved chart's input values
off DECLARATION ORDER within each type, so putting it where a reader would look for it silently
resets every later float on every chart running the script. **Do not tidy it into place.**

⚠ **An UNSEEDED ATR must REFUSE, not pass, and it is written out rather than left to `na >= x`
being falsy** — Pine gets the right answer either way, and the intent has to survive the next edit.

✅ **The export twin moved with its parent in the same commit**, including a `cfg_min_atr` column,
so `compare_strategy.py` configures the Python from the export rather than from its own default.
🔴 **That column is the guard, not the comment beside the input.** A trade-affecting input with no
export column is invisible to the parity gate BY CONSTRUCTION — and the gate does not go quiet, it
goes WRONG, accusing whichever code the symptom lands in. This repo has met that four times.

⚠ **Pine has ONE entry path here and the Python has two** — the re-entry is Python-only — so a
green gate on this input says the 15m setup path agrees and nothing about the other door.

🔴 **IT SHIPPED AT 0.0 AND WAS SWITCHED ON AT 0.08 THE SAME DAY (Aaron's call), AND THAT CHANGED
WHAT AN UNVERIFIED PASTE COSTS.** At 0.0 the gate could not fire, so the file traded exactly as
before and landing it without a paste was cheap. At 0.08 it refuses setups in the DEFAULT
configuration — so a fresh paste of this file is a strategy nobody has run on a chart, and no
export carries `cfg_min_atr` yet. **Paste it, export it, and run the gate before any number taken
off it is believed.**

## SOS Fade's risk per trade defaults to 5 (2026-09-13)

"Risk % per trade" moved 10 → 5 in `sos_fade_strategy.pine`, in lockstep with the Python default
(Aaron's call: the default is now the share the live bot runs). The export twin was regenerated,
and `recovery_strategy.pine` moved too — with recovery off it must reproduce SOS Fade's book
exactly, and a different risk default puts a different net under the same trades.
⚠ **A chart that already has the script keeps its SAVED value** — only a fresh add, or "Reset
settings to defaults", picks up 5. ⚠ **No declaration moved**, so no other saved input shifts.
⚠ `b_leg_strategy.pine` and `bos_strategy.pine` still ship 10, and their Python ports pin 10.

## `realign_strategy.pine` — "Skip trades with the N-day move" (2026-09-16, default 20)

A new `7 · Filters` input, **declared as the LAST `int`** so no saved chart value shifts. It
refuses a trade that points the same way as price's N-day move, and any trade before N + 1
completed New York days exist (refusal code 7, tagged on the chart). The twin exports
`cfg_mom_days` and `px_mom_dir`; realign's twin is now 52 plots of 64. Doc entry `[22]` in
`docs/realign_strategy.md`. **Parity green the same day on an export taken at 20** (now the third
realign golden); the default moved 0 → 20 after it. ⚠ A chart already running the script keeps its
saved 0 until "Reset settings to defaults".
