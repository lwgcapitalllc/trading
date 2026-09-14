# CLAUDE.md — indicators/

**Purpose:** The Pine Script INDICATOR sources — the charting engines the 13 canonical Python
engines were ported from, the from-scratch `smc_engine_v2` rebuild, and the instrumented `_export`
twins that are half of every ENGINE parity gate.
🔴 **The `strategy()` half LEFT ON 2026-09-02 AND IS NOT IN THIS TREE ANY MORE.** Those files are
strategy source for the TradingView runner platform, so they now sit beside the MT5, NinjaTrader
and Python strategies at [`strategies/tradingview/`](../strategies/tradingview/CLAUDE.md) — the
numbered input-panel contract, the trade annotations, the colour palette and the per-family prose
rule all travelled with them, along with `docs/` and `tools/`. Why, and what else moved:
`docs/TRADINGVIEW_STRATEGY_MOVE_PLAN.md`.
**Scope:** This file ROUTES and keeps the dated build narrative. The RULES live in
[`engines/CLAUDE.md`](engines/CLAUDE.md), next to the code they describe. It does not cover any
Python port — those live under `engines/` and `strategies/python/`, each owning its own CLAUDE.md.
**Last reviewed:** 2026-09-02 — the `strategy()` half moved out to `strategies/tradingview/`.
2026-08-15: `tools/check_active_order.py` landed (see above). 2026-08-13: the 28 `.pine` files were
split into `strategies/` and `engines/` on their declaration, and the rules that applied to only
one half moved into that half's CLAUDE.md.

## The split — where a `.pine` file goes, and the one thing that decides it

**The Pine DECLARATION decides it, not the filename.** A file declaring `indicator()` goes in
`engines/`, here; a file declaring `strategy(` goes in `strategies/tradingview/` and is NOT in
this tree at all. Nothing else is consulted, which is the point — `structure_engine.pine` reads
like a strategy component and is an indicator. ⚠ **`m15_playbook.pine` / `m15_playbook_strategy.pine` used to be the
textbook example of this — a near-identical pair split across both folders on the declaration
alone. On 2026-08-15 the indicator was DELETED and the strategy renamed to
`smc_session_sweep_strategy.pine`**; the note that says why is in
[`engines/CLAUDE.md`](engines/CLAUDE.md). Several paragraphs below still name the deleted file in
the present tense, deliberately — each records a decision applied across many files that is still
binding on the survivors.

| folder | declaration | count | owns |
|---|---|---|---|
| [`strategies/tradingview/`](../strategies/tradingview/CLAUDE.md) — **not here since 2026-09-02** | `strategy(` | 16 | the numbered input-panel contract, the trade annotations, the colour palette, and the `docs/<family>.md` prose rule |
| [`engines/`](engines/CLAUDE.md) | `indicator()` | 17 | the `mpc_jarvis` extraction track, the `smc_engine_v2` rebuild and its detection rules, and the third-party reference files |

⚠ **Count both with `ls`, never off this table** — the `strategy(` column read 12 for weeks while
there were 16, and the row above is the third place in this repo that number has been wrong.

⚠ **Ask the folder, then read that folder's CLAUDE.md — not this one.** A fact lives in exactly
ONE CLAUDE.md, the one next to the code. This file keeping its own copy of the panel contract is
how three files in this repo came to disagree about whether a bot was live.

⚠ **`CLAUDE.md` is the only file left at this level, and that is structural rather than tidy** —
the commit hook finds a changed file's OWNING doc by walking up from its folder, so this file has
to sit above `engines/` to be the thing it falls back to. ⚠ **It kept that job when the strategy
half left**, because `docs/` and `tools/` still sit here and both need an owner.

## `tools/` — the panel checks, run by hand

**`check_active_order.py` (2026-08-15).** An input's `active =` may only name inputs declared
ABOVE it; Pine resolves top-down and a violation is `CE10272`, which **only appears on the paste**.
`bos_strategy.pine` shipped exactly that in the 2026-08-12 panel reorder, and its export twin
carried the same defect because a twin is a copy. Run it after ANY panel edit:

```bash
python3 indicators/tools/check_active_order.py strategies/tradingview/*.pine
```

**All FOURTEEN gated strategy files pass, re-run 2026-09-02 at the new paths** (it read twelve on 2026-08-15 and two more have landed since). ⚠ **The two files under `strategies/tradingview/research/` are deliberately outside that glob** — they carry no numbered panel, so the check has nothing to say about them. ⚠ **Its first two versions each reported four
false failures and the shape of that is the warning, not a footnote.** Version one ran the
`active =` expression past its own argument and swallowed the next one, so `step = 0.05` read as a
dependency on an identifier called `step` — which a local 4,900 lines away happened to be. Version
two stopped at the argument boundary and still failed, because `active = execRunnerTrail != "Fixed
step"` puts the word inside a STRING. **A checker that flags the four biggest files while passing
the small ones is one you conclude is broken and stop running**, and version two would have been
"right" for entirely the wrong reason since those files really were clean. Strings are stripped
before identifiers are extracted now. ✅ **Watched RED by mutation rather than trusted** — swapping
an input with its own `active =` dependant in a throwaway copy reddens exactly that pair and
nothing else. ⚠ **It is a PROMPT, not enforcement**: nothing runs it for you, and it reads Pine
with regular expressions rather than parsing it, so a novel formatting of `active =` could slip
past. It is a cheap check for a defect that otherwise costs a round trip to TradingView.

**`check_scope.py` (2026-08-25).** Asserts that every `_`-prefixed identifier read inside a
function or method body is a parameter of it or assigned in it. Pine calls the failure `CE10272`
and **it only appears on the paste**, so a file can look finished in the repo for days.

```bash
python3 indicators/tools/check_scope.py strategies/tradingview/*.pine
```

**All thirteen strategy files pass as of 2026-08-25.** It exists because
`extreme_leg_strategy.pine` builds its higher-timeframe engine by GENERATING a second copy of
the chart-frame one, swapping the bar globals for passed-in values — and two helper methods got
the swap without getting the parameter. ⚠ **It is deliberately narrow: the underscore prefix is
this repo's convention for a value handed IN to a derived engine instance, so the check covers the
whole class that generator can produce and nothing else.** Finding an undeclared identifier with
no underscore needs Pine's own builtin list, which we do not have — **so its silence is one
specific question answered, not a clean bill of health.** ✅ Watched RED by mutation rather than
trusted, on the exact line the first paste failed at. ⚠ **It is a PROMPT, not enforcement**, same
as its neighbour.

🔴 **`check_flat_reset.py` (2026-08-25). This one is here because a strategy blew an account on its
first run.** Orders are processed on the bar's close, which happens AFTER the script has finished
running for that bar — so on the bar an entry is placed, `strategy.position_size` still reads flat
everywhere below it. `extreme_leg_strategy.pine` cleared its stop and target under a bare flat
test, which therefore fired on the entry bar and wiped both three lines after the entry set them.
**The bracket then went out empty, and because a new entry needs a flat book the position could
never close: one unprotected trade held to the end of the chart.** The check flags any value an
entry block sets and a bare flat test clears.

```bash
python3 indicators/tools/check_flat_reset.py strategies/tradingview/*.pine
```

**All thirteen strategy files pass as of 2026-08-25.** ✅ Watched RED against the exact file that
blew the account, naming both cleared values at their own lines. ⚠ **It knows this one shape and
nothing else — it cannot tell you a bracket is correct**, only that this specific way of destroying
one is absent. ⚠ **Nothing else in this repo tests whether a position is protected.** A Python
study measures in R with the stop assumed live, so an absent stop is not a shape it can express;
that lives only in the Pine file. ⚠ **It is a PROMPT, not enforcement.**

**Everything else that is prose lives in [`docs/`](docs/):** `PINE_INPUT_DEFAULTS.md`,
`BUG_exit_fill_price_mismatch.md`, `MARKET_STRUCTURE_GLOSSARY.md`, `STRUCTURE_OS_BUILD.md` and
`INDICATORS_BUILD_NOTES.md`. They were NOT split across the two children: each describes both
halves, and splitting them would have made two half-true copies.

⚠ **Not to be confused with [`strategies/tradingview/docs/`](../strategies/tradingview/CLAUDE.md),
which is a different thing with a different job:** one `<family>.md` per strategy holding the
commentary that used to sit inline in that Pine, anchored from the source by `// [doc N]`. Prose
ABOUT a strategy file goes there; prose about the indicators subsystem goes here. ⚠ **That folder
left this tree on 2026-09-02 with the strategies it describes** — it used to be `strategies/docs/`
one level down from here.

---


## The build narrative

Everything below this line is the dated story of how these files got here — what a pass found,
what it measured, and what it cost. It is kept rather than summarised, because a rule with no
incident behind it reads as arbitrary and gets "tidied up" by the next reader.

⚠ **An earlier drain (2026-08-12) moved 129,018 bytes of narrative VERBATIM to
`indicators/docs/INDICATORS_BUILD_NOTES.md` and nothing was deleted; the entries below
accumulated after it.** They are the next thing to drain, and this file is still ~100 KB —
over the 40 KB ceiling the editor guard watches. Draining is deliberately SILENT to that
guard, so nothing will remind you.

## Guides & references

- `indicators/docs/STRUCTURE_OS_BUILD.md` — full build log: settings-panel parity, architecture (two engines/one shared type), design decisions, open questions, and per-stage validation status against the original TradingView indicator.
- `docs/market_structure_engine_spec.md` — plain-language spec of the detection rules (swing points, HH/HL/LH/LL, BOS/CHoCH, internal engine) derived from the TradingView indicator's public description.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 110 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/bos-strategy-build.md` — BOS strategy — build, defaults and the false-break defect

**Read before touching:** `bos_strategy.pine`, its FVG floor, or its export twin.
Most-cited code: `sos_fade_strategy.pine`, `bos_strategy.pine`, `sos_fade_strategy_export.pine`, `mpc_jarvis.pine`, `b_leg_strategy.pine`, `b_leg_strategy_export.pine`.

- 2026-08-13 — 🟢 A FALSE BREAK BECAME A STRATEGY, AND THE TOOL THAT COUNTED IT GOT THE SHORT SIDE'S SIGN WRONG
- 2026-08-07 — 🟢 `bos_strategy.pine` COMPILES, AND ITS DEFAULTS MOVED OFF THE SPEC BECAUSE THE FVG ENTRY IS THE LOSING HALF
- 2026-07-31 — `bos_strategy.pine` defaults now ENCODE the spec, not the bare baseline
- 2026-07-29 — the FVG floor is now SPLIT BY TIMEFRAME (SOS Fade, its export, and BOS)
- 2026-07-29 — `bos_strategy.pine`, the third strategy off the shared engine

### `notes/d-strategy-vwap.md` — d_strategy.pine and the VWAP experiments

**Read before touching:** `d_strategy.pine`, or the VWAP entry/exit logic in any strategy file.
Most-cited code: `sos_fade_strategy.pine`, `d_strategy.pine`, `bos_strategy.pine`, `mpc_jarvis.pine`, `structure_engine.pine`, `b_leg_strategy.pine`.

- 2026-08-06 — 🟢 THE VWAP WENT INTO THE BOS STRATEGY INSTEAD, BECAUSE THE MEASUREMENT SAID D'S TRIGGER HAS NO EDGE
- 2026-08-06 — `d_strategy.pine`, and why "an SOS then an opposite SOS" is not a signal

### `notes/session-liquidity-ties.md` — PDH/PDL vs session high/low — the tie-break and label bugs

**Read before touching:** liquidity levels, session high/low drawing, or level-mitigation dedupe.
Most-cited code: `mpc_jarvis.pine`, `m15_playbook.pine`, `sos_fade_strategy.pine`, `b_leg_strategy.pine`, `bos_strategy.pine`.

- 2026-08-07 — PDH/PDL WIN A TIE AGAINST A SESSION HIGH/LOW AT THE SAME PRICE

### `notes/harness-export-validation.md` — The 2026-07-31 harness pass — four exports validated

**Read before touching:** building or trusting a `_export.pine` harness.
Most-cited code: `b_leg_strategy.pine`, `b_leg_strategy_export.pine`, `svp_export.pine`, `sos_fade_strategy.pine`, `mpc_jarvis.pine`, `m15_playbook.pine`.

- 2026-07-31 — the harness pass: four exports validated, one file deleted, session windows finally forked back together

### `notes/structure-sos-fade-early.md` — The 2026-07-12 structure re-sync and SOS Fade divergence link

**Read before touching:** the structure break decision or the SOS Fade divergence link.
Most-cited code: `mpc_jarvis.pine`, `sos_fade_strategy.pine`, `ob_export.pine`, `fib_export.pine`, `structure_engine_export.pine`, `structure_engine.pine`.

- The 2026-07-12 structure re-sync (`choch_lock` removed from the break decision)
- The 2026-07-12 SOS Fade divergence retro-link

### `notes/sos-fade-b-leg-build.md` — SOS Fade / B-LEG build — July 2026

**Read before touching:** `sos_fade_strategy.pine`, its export twin, or `b_leg_strategy.pine`.
Most-cited code: `sos_fade_strategy.pine`, `sos_fade_strategy_export.pine`, `b_leg_strategy.pine`, `mpc_jarvis.pine`, `strategies/tradingview/b_leg_strategy.pine`, `ny_orb.pine`.

- 2026-07-22 — `sos_fade_strategy.pine` readability pass + compile-budget cuts
- 2026-07-23 — `sos_fade_strategy.pine` Method 3 (deep-fib entry) + prime-combo defaults
- 2026-07-24 — the B-LEG fork + 500x leverage pin
- 2026-07-25 — blocked-trade marker (`sos_fade_strategy.pine` + `sos_fade_strategy_export.pine`)
- 2026-07-26 — orphaned-SVP compile fix + `sos_fade_strategy_export.pine` regenerated
- 2026-07-26 — the exit levers ported to the B-leg fork + the export's config columns completed
- 2026-07-27 — TP1/TP2 default 30/40 → 0/0, and the `qty_percent = 0` trap
