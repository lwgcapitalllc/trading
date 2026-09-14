# Notes — The repo-wide checks — parity gates, golden exports and Pine drift

How the cross-file checks work: the Pine copy-drift check, committed golden exports so a gate can always run, the shared export-format rules, engine defaults held to the Pine, and the generated Pine harnesses. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### `scripts/check_pine_blocks.py` — the drift check the parity gates cannot do

**Step 14 of `scripts/run_all_tests.sh`.** Pine has no import, so every engine block is copy-pasted
into the indicator, into that engine's own parity harness, into any OTHER harness embedding it for a
coupling, and into each strategy plus that strategy's export twin — **~10 files per rule, with
nothing asserting they matched.**

🔴 **A `compare_*.py` is structurally blind to this.** It asks whether the PYTHON agrees with ONE
Pine file, on ONE export, on ONE machine. Two PINE files disagreeing with each other is outside the
question. On 2026-09-09 the equal-level mitigation rule moved close → wick in the indicator, the
Python engine and two harnesses while SEVEN strategy files stayed on close — and every gate that
could run stayed green. This step went red on 28 findings the moment it existed.

⚠ **It compares each copy against the INDICATOR, never against a value typed into the checker.**
Hardcoding the answer would make the checker one more place the rule is written down, and then a
rule change has to edit it too — which is the disease, not the cure. Move the indicator, move the
copies, and this stays green with no edit.

⚠ **It DISCOVERS copies rather than listing them.** The engine's own doc said the rule lived in
three files; it lived in eight. That was not carelessness — the true count lived nowhere, so anyone
checking checked the files they knew about. **A count that exists only in prose is a count that is
wrong.**

⚠ **Every spec declares a minimum number of copies and finding fewer is a FAILURE**, because a
regex that stops matching after somebody reformats a file would otherwise report a clean repo.
Watched RED by mutation, and the mutant exits 1 rather than passing quietly.

⚠ **It cannot tell you the INDICATOR is right** — only that the copies match it. That is rule 14
arriving in a new place.

⚠ **Seven rules as of 2026-09-10** — the five equal-level ones plus the gap cap's counting basis and
the gap mitigation rule. The cap spec went red the moment it existed: four strategy files were
counting EVERY gap against the cap while their drop scan skipped the protected ones, which makes the
exemption a swap rather than an addition. **It was DORMANT — those files ship the exemption off, and
the two forms are then identical by construction — so it could only ever have been found by a tool
that compares Pine against Pine.** Story: `strategies/tradingview/CLAUDE.md`.

### `scripts/check_engine_gates.py` — golden exports, so a gate can always run

**Step 15 of `scripts/run_all_tests.sh`.** Runs each engine's `compare_*.py` against a COMMITTED
export under `engines/<name>/exports/golden/`.

🔴 **Rule 22 was unsatisfiable for most of this repo, and that is what this fixes.** *"No engine
change without a green gate"* is right, but exports were git-ignored scratch — so whether a gate
could run depended on which CSVs sat on one laptop. Measured 2026-09-09: **nine of fourteen gates
could not answer**, and those that could were red against two-month-old exports from a Pine that no
longer existed. **A rule that cannot be satisfied stops being a rule** — it blocked work instead of
gating it, and both stalling and routing around it happened that day.

⚠ **Two different jobs, and you need both.** A golden export is REGRESSION — it catches the PYTHON
drifting from a known-good answer, on every clone, in seconds, with no human. A fresh export is
ACCEPTANCE — it catches the Pine and the Python disagreeing after a Pine edit, and still needs a
person with TradingView open. **A green golden run says nothing about a Pine change made after the
file was taken.**

⚠ **It prints its COVERAGE FRACTION and names the engines that lack an export**, because a bare
green tick on this step would read as *the engine gates pass* when it means *the one engine with a
committed export passes*. Coverage: **11 of 11** gateable engines, from **thirteen** committed exports — the gap engine carries two (2026-09-10) because the fib entry-band exemption is a separate branch with its own harness, and the fib engine two frames (5m and 15m), each at its own measured warm-up: `golden.json` may key the warm-up per file.

🔴 **A GATE'S OWN WARNINGS NOW SURVIVE ITS GREEN, and they did not until 2026-09-10.** Each gate's
stdout was captured and DISCARDED on success, so a caveat the gate printed on every run reached
nobody. Two were hiding behind ticks: `compare_fvg.py` reporting that it could only see **48%** of
its export's bars, and `compare_candles.py` naming a pattern that **never fired on either side** —
i.e. rule 14's *says nothing about a branch neither one entered*, printed and swallowed. Any 🔴/⚠
line a gate prints is now echoed under its tick. ⚠ **Generic on purpose** — any gate can raise a
caveat this way and none of them needs an if-statement in the runner.

🔴 **The fibonacci gate excludes its MACRO half deliberately, and that is a decision rather than
a gap.** The macro fib diverges on 11,356 of 13,304 bars because the engine matches the STRATEGY
file the bot replays, not the assistant's 2026-07-31 rework — porting that would manufacture drift
in the bot. Nothing trades on it: the strategy computes the zone and reports it, execution never
reads it. **A gate that can never pass is worse than none**, so the other three fibs are gated for
real and the exclusion prints in the tool's scope line on every run.

⚠ **`golden.json` carries an `extra_args` list** — a generic seam so any gate can take a per-engine
flag without this runner growing an if-statement per engine. Anything it carries must justify itself
in the manifest, as fib's does.

⚠ **Each golden folder carries a `golden.json`** holding the MEASURED warm-up and the provenance
(broker, symbol, timeframe, bar count, harness). Provenance is recorded because a cross-cutting run
on 2026-09-01 recorded NEITHER broker nor symbol and cost three replays — two brokers disagree on
the bar count for the same window while both look perfectly healthy.

🔴 **A warm-up is MEASURED, never guessed, and never raised to bury a LATE mismatch.** The export
starts warm and the Python starts cold, so an opening prefix of mismatches is expected; the number
is set past the last mismatching bar with the whole remaining tail confirmed clean. Mismatches that
RECUR after a clean stretch are real divergence — raising the warm-up to swallow them turns the gate
into decoration. Two of the ten were diagnosed that way on landing: the gaps engine looked 100%
divergent and was a window too short (seven gaps born before the export began, and a gap only dies
when price closes past it), while fibonacci's macro half is genuine.

⚠ **Cost: ~25 MB raw, ~4 MB compressed in git, once.** That is the price of every gate being
runnable on every machine forever, and it is worth stating so nobody re-litigates it later.

⚠ **Engines are DISCOVERED, never listed** — drop a CSV in the golden folder and it is wired in
with no edit. ⚠ **Finding zero golden exports is a FAILURE**, not a quiet pass.

⚠ **`--jobs auto` (the full run: 75s → 18.6s) and `--only` (the fast tier) change WHICH gates run
and WHEN, never how** — same command per gate, same pass rule, results in discovery order. The
self-test still counts every export first, and an unknown `--only` name is refused.

✅ **STRATEGIES JOINED ON 2026-09-10 — all four**, from `strategies/python/*/exports/golden/`, so
every strategy's parity gate, both LIVE bots' included, runs on every clone. 🔴 **BOS's was RED on
arrival**: every fork had inherited SOS Fade's 2026-09-06 adding-to-winners default, which no
fork's Pine can do, and nothing had run BOS's gate since. **A fork inherits its parent's DEFAULTS as
well as its code** — pinned off in all three (`strategies/python/bos/CLAUDE.md`). ⚠ **A folder with two
compare scripts must NAME its gate in `golden.json`** — SOS Fade has two, and the runner took the
first alphabetically, right by luck; unnamed ambiguity is now refused. ⚠ **A Pine twin that gains
a compared column makes its golden REFUSED rather than stale** — the step goes red and the answer
is a re-export. ⚠ Each manifest says what the chart's settings did NOT exercise, and a passing
gate's ⚠ lines print under its tick, so read them before quoting a green. Both paths watched
RED by mutation: reverting the engine's rule turns the gate red through this runner, and raising the
minimum makes the self-test fire and exit 1.

### `engines/gate_common.py` — the export-format rules every parity gate needs

🔴 **It exists because the live-bar rule was written three times before it was written once.**
`compare_bos.py` had it, `compare_candles.py` copied it with a comment saying so, and a third copy
was about to land in `compare_fvg.py`. Eleven copies of a three-line rule is the disease this repo
pays for in Pine *because Pine has no import* — Python has one, so not using it is a choice.

🔴 **The rule: the final row of a TradingView export is the LIVE bar, and every gate was feeding it
as a closed one.** Most Pine blocks gate detection on `barstate.isconfirmed`, so they do not run on
that bar, while the CSV carries its current OHLC. It fired on the gap gate on 2026-09-10 — one bar
in 20,188 — and **all twelve golden exports end on a row carrying values, so every gate carried the
exposure** and was green only because its last bar happened not to matter.

⚠ **NOT decided from the clock.** *Is this bar still open?* is a question about when the export was
TAKEN, not when the gate is RUN, so a committed golden file would answer it wrong for ever. The
final row is treated as suspect unconditionally: one bar in twenty thousand, and it cannot rot.

⚠ **Deliberately NARROW and it must not grow into a parity-gate framework.** Each engine's
comparison is genuinely its own; a shared base class would be the over-engineering this repo counts
as a corner cut in its own right. What lives here is a fact about the EXPORT FORMAT — the one thing
all eleven demonstrably share.

⚠ **Its message says `note:`, not `⚠`, on purpose.** `check_engine_gates.py` echoes 🔴/⚠ lines under
a passing tick because those are caveats about that RUN; this one is a constant of the format and
would print identically twelve times, which is how a reader learns to skip the marker that matters.

### `engines/pine_constants.py` + `engines/tests/` — every engine default is held to the Pine (2026-09-10)

🔴 **On 2026-09-09 three equal-level numbers moved in the indicator and had to move in SEVEN Python
places; an eighth copy turned up a day later.** Now each engine declares its defaults ONCE
(`DEFAULT_*` in its `engine.py`), every Python consumer imports them — the gates, the lab's
`backtest/replay/stack.py` — and `engines/tests/test_defaults_mirror_the_indicator.py` READS each
paired value out of the Pine and goes red when the engine disagrees. 28 pairs across seven engines,
plus the profile's row count and the gap engine's 15m row — the one the Command Center's gap layer
draws with; watched RED from both sides and on the reader's three shapes.

⚠ **The table in that test is the one place the PAIRING is written** — which Python default mirrors
which Pine name. A default with no Pine counterpart (the trading-day rollover, regime, news) is not in
it, and a Pine value split by timeframe is held to its below-15m branch, because an engine takes one
value per run. ⚠ **A strategy's own pin is deliberately NOT routed through these** — it mirrors its
own Pine file. ⚠ `pine_constants.py` refuses unless exactly ONE declaration matches, and it is
tests-only: nothing deployed imports it.

### `scripts/build_fvg_zone_harness.py` — a Pine harness that is a BUILD ARTIFACT

**Step 16 of `scripts/run_all_tests.sh`.** Generates `indicators/engines/fvg_zone_export.pine` by
slicing blocks verbatim out of `fib_export.pine` and `fvg_export.pine`; `--check` regenerates and
diffs.

🔴 **It exists because that harness has to be a TENTH copy of the gap block.** The cap's entry-band
exemption needs four engine blocks in one script — the band is the live fib recomputed every bar, so
it cannot be an input — and step 14 exists precisely because copies drift with nothing asserting they
match. **A generated harness cannot drift from its sources without this step going red**, which is
the one thing a hand-maintained copy could never offer.

⚠ **It slices on TEXT ANCHORS, never line numbers** — the first version used line numbers and they
were stale within the hour; a numeric slice would have cut a block in half while still producing a
file that looks fine.

⚠ **A red here means the harness is validating Python against a Pine block the repo no longer has.**
Regenerate, then RE-EXPORT before trusting its gate: a regenerated harness is a changed harness, and
the committed CSV was taken from the old one.

⚠ **It does not prove the harness is RIGHT**, only that it matches its sources — rule 14 again. What
proves it right is `compare_fvg.py` going green on a real export.

🔴 **It — and steps 6 and 13 — read `/Users/alwg/trading` from ANY clone until 2026-09-10.** A
typed repo path: on another machine all three fail to start, and in a second clone on this one
they certify the WRONG checkout. **Proven in a worktree elsewhere — each passed with its own subject
broken**, and goes red once it reads its own clone. All three derive the repo from their own file
now. ⚠ **Never type a repo path into a check.** ⚠ The guard itself still finds its place in the
repo by the `/trading/` in a path, so a clone must keep that folder name — a default clone does.

### Step 18 — the Pine export twins are build artifacts too (2026-09-10)

`strategies/tradingview/tools/build_export_twins.py --check`: each `_export.pine` twin must be its
parent with " Export" on the title plus its block from `strategies/tradingview/export_blocks/`. 🔴
**Five of the six twins were kept by hand until this step existed.** Rules:
`strategies/tradingview/CLAUDE.md`.
