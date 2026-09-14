# Notes — fvg/eq export parity fixes and the f_rev15 defect

Dated fixes to fvg_export.pine and eq_export.pine parity coverage, plus the f_rev15 kill-condition defect write-up. Moved VERBATIM out of `indicators/engines/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 🔴 `fvg_export.pine` was under-checking half its own bars (2026-09-10)

It plotted 10 slots per array while the live gap list reaches **17**, exceeding 10 on **52.2%** of
bars on the committed golden export — all reported green. Now **18 slots**, direction packed into ONE
column, plus whole-array aggregates so a longer list is still compared. The measurement, the expired
guard behind it and the tolerance rules live in `engines/fair_value_gaps/CLAUDE.md` and are not
restated here.

⚠ **The `fvgMaxCount` maxval, the plotted slots and `compare_fvg.py`'s slot count still move
together** — but the aggregates are what make a mismatch between them VISIBLE rather than silent.

## 🔴 `fvg_export.pine` embeds the equal-level block, and that copy was missed (fixed 2026-09-09)

The gap harness embeds the equal-level block ONLY to reproduce the cap exemption — its own detection
is gated by `eq_export.pine`. That embedded copy kept the old CLOSE mitigation and the old 0.1/6
settings when everything else moved, so the next gap export would have put `compare_fvg.py` red
against a correct Python engine.

⚠ **A harness that embeds another engine's block OWNS a copy of that engine's rules, and nothing in
the owning engine's directory points at it.** That is why it was missed twice: once when the rule
moved, and once when the settings did. It is the seventh and eighth copy of things whose recorded
count was three.

✅ Found by `scripts/check_pine_blocks.py`, which DISCOVERS the copies rather than listing them.

## 🔴 `eq_export.pine` claimed its defaults matched mpc and they never did (fixed 2026-09-09)

The equal-highs/lows parity harness carried a comment saying *defaults == mpc_jarvis.pine* while its
tolerance sat at **0.1 against mpc's 0.25** and its level cap at **6 against mpc's 14**. Its
mitigation was also still a CLOSE where mpc moved to a WICK on 2026-08-04. Both are fixed and the
gate is green on two fresh exports.

⚠ **A harness that misdescribes its own settings sends the next reader at the ENGINE.** That is
what makes this worse than an ordinary stale comment: the harness is one half of the gate, so when
it disagrees with the engine the output looks like an engine bug, and the engine is where people go
looking.

⚠ **The six plot slots per side are a HARNESS limit, not the cap.** They are the FIRST six of an
up-to-14 array, so `compare_eq.py` must run at `--max-levels 14`; at 6 every slot mismatches on
about half the bars — a six-cap engine keeps the NEWEST six while the export shows the OLDEST six.
**That red is the tool being misconfigured and it is indistinguishable from a broken engine.**

⚠ **Engine and harness move in the SAME commit, always** — fixing one alone turns the gate red and
blames the other.

## 🔴 The one real defect: `f_rev15` had three ways to die and the chart-side SOS Fade engine has four

The missing one is the one that fires on a WIN — `fibo7Touched`, price back at the leg origin. So on the 15m chart the REV row read `Pass` the moment TP3 printed, while the **1m chart kept the same leg alive at stage 4 saying TAKE PROFIT** until an opposite SOS or a continuation BOS happened along, which can be hours. Two charts, two answers, one setup. Worse than a stale row: the RE-ENTRY round trip clears the TP latches when price returns to 0.618, so a finished trade could hand the 1m a fresh AWAIT and ask for a 1m SOS on a leg the 15m had closed the book on. Fixed with `or L_tp0` / `or S_tp0` on the two death conditions — `L_tp0` **is** TP3, since `p0` is `L_high`, the leg origin, the same 0.0 the drawn fib labels TP3. ⚠ **It kills one bar LATE**: the death block runs before the fib block that sets the latch, where the 15m side kills on the bar itself. Left as is — every other value this engine ships crosses the security boundary a bar late in the same way. ⚠ **It retires the whole 1m stack together, not just the row** — `rStage` falling below 3 drops `_m15Retraced`, which is what `fiboShowAligned`, the 1m External Fib, the 1m Sniper Zone and the 1m ENTRY row all hang off. ⚠ **Nothing on the 15m moves**: every consumer of `rStage`/`rTp50`/`rDeepCode`/`rZoneLo` sits behind `_fibOneMin`, `_sn1m`, `revOn1m` or the non-15m branch of the table, checked one by one; `f_rev15` exists only in `mpc_jarvis.pine` and `m15_playbook.pine`, so **no bot and no parity gate can see this.**
