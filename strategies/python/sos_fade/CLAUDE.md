# CLAUDE.md — strategies/python/sos_fade/ (the SOS Fade bot)

> 🔴 **THIS FILE HOLDS THE RULES. THE EVIDENCE IS IN `docs/SOS_FADE_BUILD_NOTES.md` (2026-08-27).**
> Every section here keeps its ⚠ / 🔴 / ✅ rules and a pointer; the prose, the tables and the run
> numbers behind them moved there VERBATIM under the SAME heading. **Nothing was deleted** — a
> line that used to be here is in one of the two files, and that was checked rather than assumed
> (463 rule lines and 2,478 other lines, 0 lost).
>
> ⚠ **So a rule here may quote a figure whose table is now in the build notes.** Follow the
> pointer under the heading rather than assuming the number is unsupported.
> ⚠ **When you add to this file, add the RULE here and the working out there.** That is the repo
> rule — parents route, children explain — applied one level down, and it is the only thing that
> keeps this file from growing back.

**Purpose:** The SOS Fade strategy in Python — a line-for-line port of the SOS Fade block +
execution layer in `strategies/tradingview/sos_fade_strategy.pine` (Aaron's brother's "MPC-JARVIS" script). It reads
the canonical engine stack's per-bar output and turns the SOS Fade sequence into trades.
**Scope:** This strategy only — its state machine, order logic, config, and parity harness. It does
NOT own the engines (`engines/`), the replay runner (`backtest/`), or the lab (`command-center/`).
**Status:** Built + unit-tested + **logic-parity GREEN (exit 0) 2026-07-16** on a full-history
`VANTAGE_XAUUSD, 5m` export (20,076 bars, `compare_strategy.py` with no warmup — the export starts at
bar 0). Bar-for-bar identical decision stream vs `sos_fade_strategy.pine`. Runs real-tick fills + costs
(`fill_model="tick"`), and is registered in the command-center lab as `runner="python"` (see
`LAB_STRATEGY` in `__init__.py`) — risk % is editable in the Run modal. 51 offline tests green.
**RE-VALIDATED GREEN 2026-07-22** after the Pine changed (SOS-aware veto + `execConfSZ` + CONT
removal): the export was regenerated, the veto was ported, and `compare_strategy.py` matches Pine's
decision stream on a fresh 19,863-bar `VANTAGE_XAUUSD, 15m` grand export — every `px_dec_bits` /
`px_stages` / `px_edge` / `px_entry_price` bar-for-bar, one lone 25-cent `px_exit_run` difference on
a single Nov-2025 runner (an intrabar trail-fill guess, not a decision). See `## The 2026-07-22 re-sync`.
**RE-VALIDATED GREEN 2026-07-29** on a fresh 21,494-bar `VANTAGE_XAUUSD, 15m` export taken at the
shipped `exec_tp1_pct = exec_tp2_pct = 0` and carrying the swing ratchet through `cfg_exitmode`/
`cfg_trail_pct` — exit 0 at warmup 100 and at every warmup up to 2000. See
`### PARITY GREEN 2026-07-29`.
**RE-VALIDATED GREEN 2026-08-02** on a fresh 21,710-bar `VANTAGE_XAUUSD, 15m` export carrying the
new ENTRY MODEL through `cfg_bits` (decoded 544375, **bit 524288 set** = rule 3 live on both sides)
— exit 0 at warmups 100 / 500 / 1000 / 2000. That is the run that validates the port; an export
taken before 2026-08-02 has every new bit clear and proves nothing about it.
**RE-RUN GREEN 2026-08-02 after the label/tooltip sync**, on a FRESH 21,715-bar export taken off the
renamed file (2025-08-31 → 2026-08-02, `cfg_bits` 544375) — exit 0 at warmups 100 / 500 / 1000 /
2000. That change touched Pine input TITLES and tooltips, `config.py` comments and one display
string, so a green run on an export from the NEW file is the evidence it was cosmetic, rather than
an argument that it must have been. The same run is the compile proof: a title is a string literal,
so a mangled one fails to compile, it does not quietly change a trade.
**RE-VALIDATED GREEN 2026-08-23** on a fresh 21,060-bar `VANTAGE_XAUUSD, 15m` export
(2025-09-30 → 2026-08-23, shipped defaults, `exec_risk_pct` 10, stop fib 0.886, swing ratchet,
scale-in OFF) — exit 0 at warmups 100 / 500 / 1000 / 2000. **This is the run that clears the
2026-08-21 structure fix**, the refused-wick guard, whose only previous evidence was a red gate
against a twin that predated it. ⚠ **Non-vacuous, and it was checked rather than assumed:**
25 entries, 25 closes summing +29.05R, 2,470 armed bars and 267 blocked-setup tags, all
bar-for-bar. ⚠ **Rule 14 still stands** — green says the two AGREE, never that either is right,
and nothing about a branch neither entered; the harness itself reports that the no-gap fallback
was not exercised on this run.

## The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)*.

## Sizing — this bot sizes ITSELF

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Sizing — this bot sizes ITSELF*.

## Sizing against the ACCOUNT's budget, at PLACEMENT (2026-09-03)

🔴 **`_fit_to_budget` shrinks a size to what the account can still afford, BEFORE the order is
placed.** Aaron's rule: a bot occupying more than its share makes the others shrink to what is
left; with nothing left they place nothing and say why. The arithmetic is
`PortfolioAccount.affordable_qty` — deliberately NOT a second copy here, because the fill gate
uses the same one and a placement sized by one rule and a fill judged by another is two answers
to one question.

🔴 **The MOMENT is the whole point, and the first attempt got it wrong.** The clamp originally
ran at the FILL, which is right for a shared backtest and wrong for a live bot: the order is
already resting at the broker by then, so shrinking the emulator's copy leaves the two holding
different books that grade different R — and the live bridge compares direction and presence,
**not size**, so nothing halts on it. Same seam, same operator, one step too late.

⚠ **All FOUR placement sites are fitted** — both primary sides and both re-entry sides. ⚠ **An
unaffordable re-entry long falls THROUGH to the short check** rather than dropping the pair.

⚠ **Inert without a stated budget, which is the parity guarantee**: a solo account has infinite
room, so the fit is the identity function and no stored result moves. `compare_strategy.py` was
run GREEN before and after on the same export, 21,302 bars each time. ⚠ **And a green gate says
nothing about the shrink** — the Pine has no account budget, so no export can enter this branch.
The unit tests and their mutations are the only evidence it will ever have.

Detail, numbers and the audit that backed out the first version: `backtest/CLAUDE.md` →
*`SoloAccount.external_room`*.

## The account is told what TIME it is (2026-09-03)

🔴 **`_stamp_account_clock`, because every venue-ceiling clamp on a standalone run carried a null
time.** That log is the only trace a resized entry leaves — the trade list and the equity curve
are identical either way — so a record nobody can date is most of the evidence gone. ⚠ **It does
NOT stamp when a shared stack's simulator owns the clock**, or the legs would report their own
bar opens into one shared log. ⚠ **The re-entry stamps from its own faster feed.** ⚠ **A bar time
of zero is a time.** Found by running the feature, not by reading it.

## This order layer DECLARES that it rests a limit — `entry_style` (2026-09-03)

One class constant, read by `algos/live/` and by nothing else. **No replay, no cost and no
decision reads it**, so it cannot move a trade and the parity gate is structurally blind to it —
it was still run, and is exit 0 at `--warmup 100` on `VANTAGE_XAUUSD, 15_2a817.csv` (21,610 bars
compared).

🔴 **IT IS WHAT KEEPS THIS BOT'S DIVERGENCE HALT ALIVE.** *Emulator in a position, broker flat* is
the 2026-08-07 fault here and the bridge must stop; for a bot that enters at MARKET the identical
state is one instant of latency and the bridge must place the order. Nothing observable separates
the two, so the bridge asks rather than guessing. Rules: `strategies/CLAUDE.md` → *Every order
layer DECLARES how it opens a position*.

⚠ **`b_leg` and `bos` inherit it**, which is correct — both rest a fib-priced limit.
✅ **`realign` enters at MARKET and OVERRIDES it (2026-09-16)** — see its CLAUDE.md → *Live-capable
wiring*. ⚠ **`b_leg`'s order layer takes a THIRD argument the live runner never passes**, so it
cannot run live as wired either — the same gap realign had; unfixed, and its demo bot is benched.

⚠ **It needs a PROMOTE to reach the running bot**, like everything else in this package.

## The restart seam — `snapshot_position()` / `restore_position()` (2026-08-10)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The restart seam — `snapshot_position()` / `restore_position()` (2026-08-10)*.

⚠ **`_POSITION_FIELDS` is the whole open-trade state and a missing entry is SILENT.** Leave one out
and the restored trade manages against a constructor default — a zero `_max_fav` un-ratchets the
trail, a zero `_stage` puts a breakeven stop back to the full stop, a missing `_entry_ms` resets the
time stop's clock. Nothing raises.
`test_the_snapshot_covers_every_field_open_position_assigns` therefore **DERIVES the required set by
reading `_open_position`'s own source**, because a hand-written list would re-freeze exactly the
assumption that fails — the same guard `run_dual`'s fill-clock signal needed after it shipped missing two
fields that three weeks of green tests never saw.

⚠ **`_traded_sos_l` / `_traded_sos_s` are carried even though `_open_position` does not assign
them there.** They are the one-trade-per-15m-leg latch, and without them a restored bot could
re-enter the very setup it is already holding, the moment that trade closes.

⚠ **`restore_position` REFUSES an incomplete record rather than filling defaults**, and that is the
safety property. A record missing `_stage` is not "a trade at stage 0", it is a record that cannot
be trusted; the caller halts, which is what the bot did in every case before this existed.

✅ **Parity is structurally unaffected and it is CHECKED rather than asserted**: a test reads the
source of `step`, `step_secondary` and `_manage_open` and fails if either method is ever called
from the bar path. A lab replay only ever holds a position it filled itself.

⚠ **`b_leg` and `bos` inherit both methods**, which is correct — they share this exit ladder
and this emulator — but neither has been driven live, so treat the inheritance as untested there.

⚠ **It needs a PROMOTE to reach the live bot.** This package is version-pinned, so the running bot
keeps the old code until `algos/tools/promote.py` runs.

## The portfolio-account seam (2026-07-17)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The portfolio-account seam (2026-07-17)*.

## What it is (one paragraph)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *What it is (one paragraph)*.

## The five modules (the data flow)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The five modules (the data flow)*.

## The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused*.

## A miss carries the RETRACE LEG it was priced off (2026-09-15)

⚠ **Capture-only. Nothing in the strategy reads `leg_extreme` / `leg_origin` back**, so no
decision can depend on them and no stored result moves — the same additive pattern the structure
engine's own break-location fields use. 651 tests green before and after.

🔴 **The LEG is captured, not a handful of finished levels, and that is the rule.** Every price a
later reader wants — the 0.5 and 0.886 band edges, the 0.886 stop, any entry fib — is
`extreme + (origin - extreme) * ratio` off this one pair. Capturing three or four cooked levels
instead would let a consumer derive a fifth its own way and disagree with the record about where
the zone was, which is the defect `_zone_edges` already exists to prevent one level up.

⚠ **They come off the signal's own `fibo_p7` / `fibo_p10`** — the identical anchor pair the
re-entry's zone edges read — so a consumer can never be describing a different leg from the one
the setup actually had. `None` when the signal published no leg.

⚠ **The test asserts the DERIVATION, never the two numbers**: it reproduces the signal's own
published 0.886 off the captured pair. Watched RED by mutation (the two anchors swapped at the
record site puts the derived 0.886 at 108.86 against the signal's 101.14), which is what makes it
non-vacuous — a pair of `None`s would otherwise read to every consumer as "this setup had no leg".

**Why it was added:** the no-gap study (2026-09-15) needs the band each dead setup actually had, and
the miss record published where the limit would have rested and nothing else. Rule 11 — anything
recreating a run for comparison must carry forward everything that decides what it is measured on.

## The fast-frame INTERNAL shift feed — `InternalShift1m` (2026-09-15)

⚠ **NOTHING IN THE BOT READS IT YET, and no live bot may run it.** It was built for the no-gap
study: when price reaches the band and no gap is there to rest on, Aaron's rule is that a
fast-frame internal change of character in the trade direction is the last confirmation
available. Whether that is an edge is being MEASURED. It has no Pine counterpart either, so the
parity gate is structurally blind to it — a result taken with it is a lab finding.

🔴 **IT IS NOT `Structure1m` WITH A FLAG.** That class latches the EXTERNAL change of character
and the break leg the re-entry sniper rests a limit on; this one watches the INTERNAL event on
the same bars. Two classes rather than one with a switch, because reading one where the other was
meant produces an ordinary-looking trade at the wrong moment and nothing downstream shows you.

✅ **MEASURED that they are genuinely different populations, and the direction was a surprise:**
over 82,074 real 1m gold bars (2026-06-01 → 2026-08-21) the external feed fired **416** times and
the internal one **317** — the internal event is RARER here, not more frequent. That is what makes
it a candidate filter rather than a rubber stamp. On the seeded walk the two test streams use,
17 external against 12 internal with **no bar in common**.

🔴 **`*_price` and `*_loc` are REPORTING ONLY and one of them is KNOWN WRONG.** The engine's bear
iSOS bar lands on the level that actually broke **3 times in 25** (measured over 169 internal
breaks), off by up to \$18.47. The bools are unaffected and are the whole of what this study
needs, because the entry is the PRINT and the stop is the 15m 0.886. ⚠ **The later tight-stop
variant — stopping under the fast-frame shift leg — CANNOT use these fields**: it would place
roughly one short stop in eight at a price nothing broke at. That is a fix owed in
`engines/market_structure/` before that variant is measured, not something to work around here.

⚠ **It does not latch, unlike `Structure1m`** — the study asks whether a shift printed on THIS
bar, so a stale flag from an earlier bar would be a different question silently answered.

⚠ **The frame is the caller's choice and nothing in it assumes a minute.** The name follows
`Structure1m`'s, which `dual_clock.py` already documents as untrustworthy.

**Tests:** `tests/test_internal_shift.py`, on a SEEDED random walk rather than a hand-built
fixture — a fixture shaped to make one event fire proves only that it can. Watched RED by
mutation: pointing the feed at the external events makes the two streams identical and fails the
disagreement assertion on exactly that line.

## Engine-construction pins (`SosFadeStrategy.engine_config`)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Engine-construction pins (`SosFadeStrategy.engine_config`)*.

## The three parity fixes (2026-07-16) — read before touching signals/fib

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The three parity fixes (2026-07-16) — read before touching signals/fib*.

## The parity gate — `tools/compare_strategy.py` + `/audit-strategy`

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The parity gate — `tools/compare_strategy.py` + `/audit-strategy`*.

## LOGIC parity vs RESULT parity — two different tools, two different questions

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *LOGIC parity vs RESULT parity — two different tools, two different questions*.

## The 2026-07-16 year run

⚠ **SUPERSEDED 2026-07-23.** Every figure in it was measured on the pre-combo baseline, so it
describes a bot that no longer exists — read it as history, never as a current number.
See `docs/SOS_FADE_BUILD_NOTES.md` → *The 2026-07-16 year run*.

## This bot's LOSSES are another package's population — `strategies/python/loss_recovery/`

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *This bot's LOSSES are another package's population — `strategies/python/loss_recovery/`*.

`loss_recovery` replays a **25%-size counter-trade after every SOS Fade stop-out**. It is not a config
of this bot and changes nothing here — but its entire trade population is **this bot's 62 real
losses**, so it is coupled in one direction: ⚠ **any change to SOS Fade's entry rule re-populates it and
every figure it has produced goes stale**, the same standing `overlap_audit.py` has. Re-run
`backtest/tools/recovery_report.py` after one.

## 🔴 The gate REFUSES an export from a chart faster than 15m (2026-08-23)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The gate REFUSES an export from a chart faster than 15m (2026-08-23)*.

⚠ **MEASURED, because "it would differ a bit" was not good enough:** on a 20,574-bar M5
export, **13,759 of 20,477 compared bars diverge as shipped and 0 diverge with the sub-15m
pair.** `px_edge` on 13,401 of them. The whole file was noise about the chart's timeframe.

🔴 **It REFUSES rather than warning, and that is the point.** The run above did not look
like a configuration problem — it looked like a broken entry rule, at a named bar, with a
price on each side. That is the shape of a real defect, and it sends the next reader into
the strategy. **Never let *cannot compare* and *compared and disagreed* be the same
outcome** — the same rule as the terminal that answered "quiet market" when it was dead.

⚠ **The spacing is read as the SMALLEST gap between rows**, matching how the bot infers its
own bar duration. A real export has weekends in it, and a reading that lets a session break
raise the apparent timeframe would walk a fast chart straight past this check.

⚠ **`--allow-fast-timeframe` exists on purpose.** The pins CAN be changed; a wall with no
door gets routed around in ways that leave no trace, which is strictly worse.

⚠ **It is a floor, not an equality** — H1 and H4 exports are legitimate, because the Pine
runs the same two values everywhere at or above 15m.

**Tests:** 5 in `tests/test_compare_strategy.py`, each watched RED by mutation. 🔴 **One of
them was WRONG on its first pass and is kept as the record**: it claimed a median reading
would break on a weekend gap, and it passed against that mutation, because weekends are a
minority of the gaps. **A test whose mutation passes is not evidence — it is a second
opinion from the same mistake.** It is written against the reading that genuinely fails.

## Tests

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Tests*.

## The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)*.

## Do / Never

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Do / Never*.

## References

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *References*.

## Its chips say `SOS Fade` on the price chart (2026-09-02)

`LAB_STRATEGY["chart_tag"] = "SOS Fade"` — the grade its own Pine calls this setup. ⚠ **A LABEL: no run, no cost and no decision reads
it**, so changing it repaints chips and moves no trade. ⚠ **Keep it SHORT** — it is drawn beside the
entry price. Why it exists, what it does on a STACK, and why rule 22 is silent for it:
`command-center/backend/CLAUDE.md` → *A strategy names its own setup on the chart*.

## The frame it is measured on is DECLARED (2026-09-03)

`LAB_STRATEGY["suggested_bar_value"] = 15` — every parity export and every shipped figure in this file is M15. The lab reads it and every form fills a leg's
timeframe box from it, so nobody has to remember which bot runs on which frame.

⚠ **It is a DEFAULT, never a refusal.** Nothing rejects a run on another frame — sweeping a bot
across frames is a real question — so a figure quoted off a different frame is a DIFFERENT
EXPERIMENT from every number in this file, and has to say so.

🔴 **Why it had to be declared: the stack page had ONE timeframe for the whole stack**, so a 5m
bot and a 15m bot on one account meant one of the two was replayed on a frame nobody has ever
measured it on — and the combined table said *portfolio*. Rules for the lab side:
`command-center/backend/CLAUDE.md` → *A stack leg runs on its own frame*.

## ⚠ Two divergence settings reach NO engine (found 2026-09-10, NOT fixed)

The divergence RSI length and pivot width live on the config and are read by nothing: the RSI
engine is built from the stack's own config, which `engine_config()` never maps them onto. So a
run at any other value replays exactly the defaults. **Harmless today only because both sides are
14 / 5** — the Pine locks them as constants, and the editor hides them. 🔴 **The stress test's
sensitivity pass still perturbs them** (stress test 630cefbebd8347db did), and every such shift is
a replay that CANNOT move, reported as a measured shift — which reads as *insensitive to this
setting* rather than *never consulted*. The parity gate reads both from an export's settings
columns and still cannot catch it at 14 / 5. The fix is to map them in `engine_config()`'s caller —
value-neutral at the defaults.

## The default risk per trade is 5%, the share the live bot runs (2026-09-13)

`exec_risk_pct` defaults to **5.0** (was 10.0), in `config.py` and `sos_fade_strategy.pine` together —
Aaron: *"lower the default to 5% so we always in sync."* The strategy page and every lab run on the
defaults now describe the bot that trades.

- ⚠ **The live bot never read the default** — its instance config states 5.0 — so nothing live moved.
- ✅ **The trade list and R do not depend on it, MEASURED on this window**: the re-recorded overlap
  audit replays this bot at 5% to **244 trades / +248.59R**, identical to the 10% reading.
- ⚠ **A dollar, balance or drawdown-% figure measured on the defaults before today assumed 10%** —
  pin `exec_risk_pct=10` to reproduce one. A figure that names its own risk is unaffected.
- ⚠ **`b_leg`, `bos` and `realign` inherit this field and PIN 10.0**, so none of them moved.
- ⚠ **The golden export ran at 10** and the gate reads risk off it, so parity is untouched.


## A re-entry when the GAP IS GONE — measured, and it ships OFF (2026-09-22)

`exec_sec_poi_fallback` ∈ {Off, **Primary entry**}, **default Off and inert**. On, a gap re-entry
whose gap no longer qualifies rests at the price the setup already published as its entry edge —
the level the primary itself entered at, remembered per SETUP and cleared on a new break.

- ⚠ **MEASURED AND IT IS NOT AN EDGE. Run 41** (`sos_fade_optimization.md`), 2020-01-01 →
  2026-08-06, puprime_ecn charged: shipped **242 trades / +267.86R / 8.37R max drawdown**, on
  **250 / +281.56R / 8.14R**. 🔴 **One trade is +10.64R of the +13.69R** — drop it and the other 11
  are worth +0.04R, which is +3.05R over six and a half years. Negative in 2021 and 2026.
- ✅ **No displacement, checked trade by trade: all 155 primaries are IDENTICAL in both runs.** A
  re-entry arms only while flat and only after its primary has closed, so it cannot queue in front
  of one the way Run 12's loosenings did.
- 🔴 **It is NOT the no-gap pool of Runs 27–36 and must not be read as it.** Those are setups the
  primary never traded; this is setups it did trade, where the primary's own fill mitigated the gap.
- ⚠ **No Pine counterpart, so the parity gate is structurally blind to it** — lab finding only.

## A close a PERSON asked for is not a stop-out, and the setup is still watched (2026-09-22)

Aaron, 2026-09-22: *"if I manually close a trade and price comes back to entry I am disqualified
for a secondary trade."* Two defects behind that, both fixed here, both keyed on the `-CMD` tag
every commanded exit carries — including the hand close `algos/live/bridge.py` adopts as
`closed_by_you`.

- 🔴 **A hand close before TP1 was stamped into the STOPPED latch**, so the RECLAIM re-entry —
  built and measured for primaries the market stopped at the deep edge — could arm on a trade
  nothing stopped, at a price nothing was stopped at. It is now recorded as CLOSED only, which is
  what the looser "Any close" door reads and is true.
- 🔴 **The bot stopped following the trade the moment the person closed it**, so a first target
  reached an hour later was never seen and the re-entry's breakeven door never opened.
  `_check_cmd_watch` keeps watching the setup and opens that door when price reaches **that
  trade's own first target** — the question the trade would have asked if left alone.
- ⚠ **It opens a door price actually REACHED; it never invents one.** If price never gets there
  the watch expires with the setup, and it only ever arms from stage 0 (a trade already past TP1
  stamped the door open before the person touched it).
- ⚠ **NOT carried across a restart.** The bot re-warms from bars, which cannot know a person
  closed anything — so a restart loses the watch and the door stays shut. A missed re-entry, never
  an extra one.
- ⚠ **No parity gate covers any of this** — the Pine has no commanded close and no re-entry.
  `tests/test_commanded_close.py` is the whole of the evidence; 5 tests, 2 mutations.
- ⚠ **It needs a PROMOTE to reach the live bot**, like everything else in this package.

## Flat before the close — `flat_mode`, and it is NOT `flat_by_close` any more

**`flat_mode` is the setting: `"Off"` / `"Friday only"` / `"Every day"`, shipped Off.** The clock
behind it is `strategies/python/time_flat.py`, shared with the extreme leg and realign, so "flat
before the close" means ONE thing in this repo rather than three. It also covers the early and
holiday closes the old rule had never heard of.

- **`flat_by_close` still works and is promoted to `"Every day"`** — every stored run, sweep and
  `--set` keeps reproducing its recorded number. ⚠ **Setting BOTH is refused**, never merged.
- 🔴 **This class closes at THIS bar's CLOSE, and that is the one exit here that does not wait for
  the next bar's open.** It is `_flat_closes_now`, a seam a fork may override — realign does, and
  arms a market order instead. The two grade different R, which is why the timing is a seam and
  not a shared assumption.
- ⚠ **MEASURED 2026-09-19, and both modes lose**: 2020-01-02 → 2026-08-06, charged
  `puprime_standard`, 1m re-entry pinned off on both sides — Off 155tr **+196.88R** maxDD 10.34R;
  Friday only 155tr +105.40R maxDD 8.02R; Every day 155tr +65.04R maxDD 5.76R. **This is the one
  bot whose drawdown actually falls**, and its return falls further: R per R of drawdown goes
  19.0 → 13.1 → 11.3. Detail and the cross-bot table: `strategies/notes/flat-before-the-close.md`.
- ⚠ **No Pine input backs it on this bot**, so a run with it on is compared against nothing.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 273 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/secondary_reentry.md` — Secondary (1m sniper) re-entry — build story

**Read before touching:** `exec_secondary`, `run_dual`, or anything about the 1m fill clock.
Most-cited code: `compare_strategy.py`, `tests/test_secondary.py`, `algos/live/bridge.py`, `config.json`, `backtest/data/history.py`, `backtest/tools/overlap_audit.py`.

- Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, committed `c962601`)

### `notes/exit_ladder_history.md` — Exit ladder — dated build and measurement history

🔵 **MEASURED 2026-09-21, not adopted:** banking half the trade at the first fib target beats the shipped ladder on return per drawdown in R (33.6 against 31.8) by cutting the worst drawdown from 7.39R to 5.69R. Pinning either target to another fib level loses, across all 108 combinations. Run 40 in `sos_fade_optimization.md`; the default is unchanged and the parity gate has not run on it.

**Read before touching:** changing any exit-ladder lever and needing the measurement that set its default.
Most-cited code: `compare_strategy.py`, `sos_fade_strategy.pine`, `backtest/output.py`, `promote.py`, `execution.py`, `config.py`.

- The 2026-07-26 exit-lever sync
- The exit ladder — every TP/SL lever, and which ones are switchable
- Every entry method OWNS its stop rule — the precedence list is gone (2026-08-27)

### `notes/reentry_ladder_mechanics.md` — Re-entry ladder mechanics — dated fixes and measurements

**Read before touching:** re-entry ordering, the reclaim, the short-hold variant, or the leg latch.
Most-cited code: `compare_strategy.py`, `algos/tools/migrate_position_record.py`, `sos_fade_strategy.pine`, `secondary.py`, `sos_fade.meta.json`.

- 🔴 A BAR NUMBER IS LOCAL TO ONE RUN. THE ONE-TRADE-PER-LEG LATCH NOW KEYS ON TIME (2026-08-26)
- `Trade.tp_rungs` — the closed record says how much each rung TAKES OFF (2026-08-21)
- 🔴 THE MERGE MOVED OUT OF `run_dual` INTO `dual_clock.DualClock` (2026-09-01)
- The re-entry rests its order and LEAVES it — and what the 1m feed is actually for (2026-08-21)
- The re-entry's FILL CLOCK is 5 minutes, and it is an accuracy knob (2026-08-21)
- What the 1-minute STRUCTURE engine contributes at the shipped trigger (2026-08-21)
- 🔴 The worst price a trade reports is bounded by its STOP — `_widen_hold` (2026-08-22)
- The SHORT-HOLD variant — `exec_short_hold` (2026-08-24, ships OFF)
- 🔴 THE RE-ENTRY LADDER COMES OUT BACKWARDS ON ONE HALF, AND THE FLIP IS PROTECTIVE (2026-08-25)
- 🔴 THE TWO RE-ENTRY HALVES ARE TWO FEATURES, AND ONLY ONE OF THEM EARNS (2026-08-23)
- Where the reclaim banks: 3.0R → 3.25R, and the 0.25R that costs nothing (2026-08-27)
- 🔴 THE RECLAIM'S GIVE-BACK — FIVE FIXES REPLAYED, FOUR LOSE, AND THE EXCHANGE RATE SAYS WHY (2026-08-24)
- 🔴 The minimum stop distance permits a stop a normal gap can double (2026-08-23)

### `notes/loss_recovery_and_dead_market.md` — Loss recovery and the dead-market floor

**Read before touching:** `loss_recovery`, `exec_min_atr_pct`, or the leg-latch bar-time map.
Most-cited code: `compare_strategy.py`, `recovery.py`, `backtest/tools/recovery_stack.py`, `tests/test_recovery.py`, `loss_recovery/tests/test_engine.py`, `tests/test_dead_market.py`.

- Loss recovery — the toggle, and the one property it must never break
- The DEAD-MARKET floor — `exec_min_atr_pct` (2026-08-26, ON at 0.08)
- 🔴 The leg latch's bar-time map was re-sorting 20,000 keys EVERY BAR (fixed 2026-08-26)

### `notes/sizing_and_risk_history.md` — Sizing and risk — the venue ceiling and the 2026-09-06 default move

**Read before touching:** changing a sizing or risk default, or reading an old figure measured before 2026-09-06.
Most-cited code: `backtest/portfolio/account.py`, `execution.py`, `compare_strategy.py`.

- The venue ceiling reaches THIS bot's default account too (2026-09-03)
- 🔴 THREE DEFAULTS MOVED 2026-09-06 — SCALE-INS ON, AND BOTH RE-ENTRY TRIGGERS AT ONCE

### `notes/parity_round_trip_2026_09_07.md` — The 2026-09-07 parity round trip

**Read before touching:** a parity fixture, `exec_secondary`'s pin, or the add order shape.
Most-cited code: `tests/test_intent_stream.py`, `test_compare_strategy.py`, `config.py`, `backtest/reprice.py`, `tests/test_execution_ticks.py`, `backtest/tests/test_reprice.py`.

- 🔴 The parity round trip disagreed with ITSELF, because a fixture was pinned to a moved default (2026-09-07)

### `notes/live_contract_and_engine_gating.md` — Live contract, exit pricing and engine gating (2026-09-09/10)

**Read before touching:** the live contract, the first-rung price, engine gating, or the parity gate's export handling.
Most-cited code: `compare_strategy.py`, `tests/test_commanded_close.py`, `strategies/python/live_contract.py`, `tests/test_full_exit_price.py`, `backtest/tests/test_replay_engine_gates.py`, `tests/test_compare_strategy.py`.

- `full_exit_price()` — where this bot closes the WHOLE position (2026-09-09)
- The first rung's price has ONE implementation, and the live bridge asks it too (2026-09-09)
- Two engines this bot never reads are no longer RUN (2026-09-10)
- The gate says "cannot measure truncation" instead of "not truncated" (2026-09-10)
- 🔴 The gate REFUSES an export missing a column it compares (2026-09-10)
- Its gap pins follow ITS Pine, and the engine default now happens to agree (2026-09-10)
- The gate ran on a fresh export, and that export is now COMMITTED (2026-09-10)
- Closing a trade because a PERSON asked — `request_close()` (2026-09-02)

### `notes/signals_naming_and_refusals.md` — Signal watching, naming history and refusal reporting

**Read before touching:** `live_setups()`, the missed-setup watch, or the strategy's display name/identifiers.
Most-cited code: `algos/live/alerts.py`, `alert_rate.py`, `config.json`, `promote.py`, `compare_strategy.py`, `miss_audit.py`.

- `live_setups()` — what this bot is WATCHING, for the pre-trade signals channel (2026-08-13)

### `notes/parity_gate_history.md` — Parity gate — dated fixes

**Read before touching:** debugging a parity-gate run against a real export.
Most-cited code: `compare_strategy.py`, `compare_bleg.py`.

- Deliberate deviations from the Pine (per the framework)

### `notes/config_meta_and_labels.md` — The meta file — labels shared with the Pine

**Read before touching:** the strategy meta file, a setting label, or a description shown on a lab page.
Most-cited code: `compare_strategy.py`, `sos_fade.meta.json`, `sos_fade_strategy.pine`, `compare_bleg.py`, `config.py`, `sequence.py`.
