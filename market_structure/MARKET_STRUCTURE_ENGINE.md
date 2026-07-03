# Market Structure Engine — Algorithm Reference

Plain-English description of what the structure engine does, how it works, and what its
lag and confirmation caveats are.

---

## What it does

The engine reads a stream of closed candles and tracks market structure: where the current
swing high and swing low are, whether price is trending up or down, and the moment price
breaks through one of those levels. It answers three questions a trading bot needs for entries,
take-profits, and stop losses:

- **Where is the active swing high/low right now?** (used for stop placement and target levels)
- **Did price just break structure, and was that break a continuation or a trend flip?**
  (used for entries)
- **Is there a smaller, faster-confirming swing inside the current move?** (the internal engine —
  used for tighter entries and earlier signals than the external engine alone provides)

There are two engines running side by side: **external** (the primary swing structure) and
**internal** (a faster, nested structure inside whatever leg the external engine is currently in).

---

## Key terms

**ASH / ASL — Active Swing High / Active Swing Low.** The current external structure's reference
levels. A body-close beyond either one is a break.

**BOS — Break of Structure.** A body close beyond the ASH (bullish BOS) or ASL (bearish BOS) that
continues the existing trend. Trend direction (`dir`) does not flip.

**SOS / CHoCH — Change of Character.** A body close beyond the ASH/ASL that goes *against* the
current trend direction, flipping it. Internally this is the same break detection as BOS — the
difference is purely which side of `dir` the break falls on. A `bull_sos` firing while `dir` was
bearish means the trend just flipped bullish (and vice versa for `bear_sos`).

**HH / HL / LH / LL — Higher High, Higher Low, Lower High, Lower Low.** Classification labels
applied to a swing level the moment it gets broken (i.e., the moment it becomes "confirmed" and is
compared against the previous confirmed level on the same side). These labels describe swing
history, not future structure.

**iSH / iSL / iHH / iLH / iLL — internal equivalents.** Same concepts, computed by the internal
engine at a finer grain, scoped to the swing leg the external engine is currently in.

**iBOS / iSOS — internal break of structure / internal change of character.** Same distinction as
BOS/SOS, applied to internal swing levels.

---

## External structure: how a swing becomes "active", then "confirmed"

1. **Seeding.** The very first ASH/ASL pair is seeded from `ta.pivothigh`/`ta.pivotlow` — see
   "Pivot lag" below — plus a one-time bounded backward scan (up to 500 bars) to find the
   opposite side once one side is known. This only happens once, at the start of the bar series.

2. **Floating before any break.** Until the first break ever happens (`last_conf_high` and
   `last_conf_low` are both still unset), a freshly confirmed pivot on the same side as ASH/ASL
   can push that level further out (a bigger pivot high raises ASH, a smaller pivot low lowers
   ASL) without needing a break. This only applies pre-first-break; once structure has broken at
   least once, ASH/ASL only move by breaking or by pullback-lock (below).

3. **Break.** When a body close moves beyond ASH or ASL, that break fires (BOS or SOS depending
   on trend direction), the broken level is stamped as "confirmed" and classified HH/LH or HL/LL
   against whatever was last confirmed on that side, and a new pullback-tracking cycle starts to
   find the *next* candidate level on the broken side.

4. **Pullback-lock.** After a break, the engine watches for **3 consecutive qualifying candles**
   pulling back against the new trend direction. Each qualifying candle must close further past a
   running threshold than the last qualifying candle (or past the tracked extreme, for the first
   qualifying candle) — see "3-candle pullback confirmation" below. Once 3 qualify, the tracked
   extreme price locks in as the new ASH or ASL (`locked=True` on the `SwingLevel`), and a
   `new_swing_high` / `new_swing_low` event fires. This is the *only* path that produces a
   `new_swing_high`/`new_swing_low` event. The other three paths that set ASH/ASL — the initial
   seed, the post-break bounded rescan (below), and the mid-pullback break-promotion (step 3,
   when a break locks an unfinished opposing pullback) — all set (and, for the promotion, lock)
   the level but do **not** fire the event, matching the Pine source exactly. This matters
   because `new_swing_high`/`new_swing_low` is the signal that seeds the internal engine, and the
   internal engine must seed only off clean 3-candle pullback-confirmed swings.

5. **Post-break rescan (no active opposing pullback).** If a break happens while there was *no*
   active pullback cycle running on the opposite side, the engine falls back to scanning backward
   (bounded to 1490 bars, or fewer bars since the last confirmed level on that side) for the most
   extreme price and uses that as the provisional new ASH/ASL — without waiting for pullback
   confirmation. This keeps the structure from stalling when there's no pullback data to promote.

6. **CHoCH lock.** Once a CHoCH (SOS) fires, no second CHoCH can fire in the same direction-run
   until a pivot appears on the *opposite* side. This prevents the trend flipping back and forth
   repeatedly off the same pivot noise — a genuine opposite-side pivot has to show up first.

---

## Pivot-seeding and its lag — read this before wiring up a bot

The engine uses `ta.pivothigh`/`ta.pivotlow`-equivalent logic (a centered local-extreme window)
to seed **brand-new swing candidates only at the start of the series**, and to let an unconfirmed
ASH/ASL float wider pre-first-break (step 2 above). A pivot at bar N can only be confirmed once
`majorLength` (15, by default) bars have printed *after* bar N — the window needs bars on both
sides to know it's a local extreme. That is real lag: the engine cannot know "bar N was a pivot"
until bar N+15.

**This lag does not apply to BOS/CHoCH break events.** A break is a body-close comparison against
whatever ASH/ASL is active *right now* — it is evaluated same-bar, in real time, with zero added
delay. The lag only affects how quickly a brand-new swing candidate gets identified in the first
place (via the seed/float mechanism), not how fast a break against an already-known level fires.

**Internal structure has no such lag.** The internal engine's swing candidates come entirely from
3-candle pullback confirmation, seeded the moment the external engine confirms a new swing
(`new_swing_high`/`new_swing_low`) — no pivot window, no 15-bar wait. This is one reason the
internal engine exists: it gives faster-confirming structure than waiting on the external pivot
mechanism.

---

## 3-candle pullback confirmation — the mechanism, precisely

Both engines (external, after a break; internal, continuously while tracking a leg) use the same
mechanism to confirm a swing extreme, ported exactly from the Pine source rather than simplified:

- While tracking (say, upward, watching for a swing high), the engine keeps a running `extreme`
  (the highest high seen since tracking started) and its bar location.
- Any bar that prints a *new* extreme resets the qualifying-candle count to zero and restarts the
  threshold at that new extreme — the pullback has to restart against the new high.
- A bar "qualifies" as one of the 3 pullback candles only if: it isn't an inside bar relative to
  the previous bar (unless it's the very first qualifying candle after a reset), and it closes
  further past the running threshold than the previous qualifying candle did (or past the extreme
  itself, if this is the first qualifying candle). The threshold ratchets tighter with each
  qualifying candle — each one must out-pull the last.
- Once 3 candles qualify in a row (without an extreme reset breaking the streak), the tracked
  extreme locks in as the new swing level.

This is intentionally strict and stateful — it is not "3 candles in a row closing beyond a fixed
level." Read `engine.py`'s `_process_external` pullback-mode branches and `_process_internal`'s
mode 1/-1 branches for the exact bar-by-bar mechanics; they are commented against the Pine source
line-by-line rather than re-derived from this description.

---

## Internal structure: scope and reset

The internal engine only runs inside whatever leg the external engine currently considers active.
It is seeded the instant the external engine confirms a new swing (`new_swing_high` or
`new_swing_low`), and it is fully reset (all internal state cleared, tracking stops) the instant
the external engine fires a CHoCH (`bull_sos`/`bear_sos`). This means internal structure never
persists across an external trend flip — it always restarts from scratch once the bigger picture
changes direction.

Internally, once the engine has confirmed at least one internal swing, it also watches for an
**internal CHoCH (iSOS)**: a close back through the last confirmed internal higher-low (bullish
cycle) or lower-high (bearish cycle). This can flip the internal tracking direction independently
of the external engine, as long as the external engine hasn't already reset it via its own CHoCH.

---

## Label → event field mapping

Every `label.new(...)` the Pine source draws has a matching field on the per-bar event objects,
carrying the label's price and (where it anchors to a historical bar) its bar index. Nothing the
indicator draws on the chart is dropped from the engine output. Fields are `None`/`False` on bars
where that label didn't fire.

**External (`events.external`, an `ExternalEvents`):**

| Pine label text | Event field(s) |
|---|---|
| "BOS" (bullish) | `bull_bos` + `bull_bos_price` |
| "BOS" (bearish) | `bear_bos` + `bear_bos_price` |
| "SOS" (CHoCH, bullish flip) | `bull_sos` (fires alongside `bull_bos`) |
| "SOS" (CHoCH, bearish flip) | `bear_sos` (fires alongside `bear_bos`) |
| "ASH", solid line (locked, pullback-confirmed) | `new_swing_high` + `new_swing_high_price` + `new_swing_high_index` |
| "ASL", solid line (locked, pullback-confirmed) | `new_swing_low` + `new_swing_low_price` + `new_swing_low_index` |
| "ASH", dashed line (unconfirmed candidate) | `unconfirmed_high_set` + `unconfirmed_high_price` + `unconfirmed_high_index` |
| "ASL", dashed line (unconfirmed candidate) | `unconfirmed_low_set` + `unconfirmed_low_price` + `unconfirmed_low_index` |
| "HH" / "LH" on a broken high | `broken_high_label` + `broken_high_price` + `broken_high_index` |
| "HL" / "LL" on a broken low | `broken_low_label` + `broken_low_price` + `broken_low_index` |

Note: a break bar typically fires several of these at once — e.g. a bullish BOS also stamps the
broken high with `broken_high_label`, and if a bearish pullback was mid-flight it promotes that
partial pullback straight to a **locked** ASL (stamping `broken_low_label` HL/LL), with no
3-candle wait. The Pine source draws that promoted level's line and label identically to a normal
confirmed swing — but it does **not** raise `new_swing_high`/`new_swing_low` on the promotion.
That event is reserved for the clean 3-candle pullback confirmation only (see the note under step
4). Detect a break-promotion off `broken_high_label`/`broken_low_label` plus
`active_swing_high`/`active_swing_low`, not off the `new_swing_*` events.

**Break-leg geometry (not a label — extra fields on `ExternalEvents`):** on a BOS bar the event
also carries the full impulse leg that broke, not just the broken level:

| Field(s) | Meaning |
|---|---|
| `bull_bos_high` + `bull_bos_h_loc` | on a bull BOS: the ASH price that broke and its bar (same value as `bull_bos_price`) |
| `bull_bos_low` + `bull_bos_l_loc` | on a bull BOS: the low the impulse launched from (a promoted pullback extreme, or the lowest low back to the prior confirmed high) and its bar |
| `bear_bos_low` + `bear_bos_l_loc` | on a bear BOS: the ASL price that broke and its bar (same value as `bear_bos_price`) |
| `bear_bos_high` + `bear_bos_h_loc` | on a bear BOS: the high the impulse launched from and its bar |

All eight are `None` except on the break bar. This is the leg a Sniper-fib anchor draws its
0.382–0.5 zone across — the plain `*_bos_price` fields give only the broken level, which is not
enough to place a fib. The low can sit at an earlier *or* later bar than the broken high (the low
comes from a backward rescan since the previous confirmed high), so do not assume a chronological
low→high ordering. These fields exist in `structure_engine.pine` but were dropped by the original
port; re-added and carried through the shim to `algos/`.

**Internal (`events.internal`, an `InternalEvents`):**

| Pine label text | Event field(s) |
|---|---|
| "iSH" / "iHH" | `new_swing_high` + `swing_high_label` + `new_swing_high_price` + `new_swing_high_index` |
| "iSL" / "iLL" | `new_swing_low` + `swing_low_label` + `new_swing_low_price` + `new_swing_low_index` |
| "iBOS" (bullish) | `bull_bos` + `bull_bos_price` |
| "iBOS" (bearish) | `bear_bos` + `bear_bos_price` |
| "iSOS" (bullish flip) | `bull_sos` + `bull_sos_price` |
| "iSOS" (bearish flip) | `bear_sos` + `bear_sos_price` |
| "iHL" (pullback low demoted at a bullish iBOS) | `demoted_low_label` + `demoted_low_price` + `demoted_low_index` |
| "iLH" (pullback high demoted at a bearish iBOS) | `demoted_high_label` + `demoted_high_price` + `demoted_high_index` |

**Two caveats carried over from the Pine source (see `# NOTE:` in `engine.py`):**

1. `swing_high_label` is only ever `"iSH"` (first internal swing since seeding) or `"iHH"` (every
   one after) — it never becomes `"iLH"`, and `swing_low_label` never becomes `"iHL"`, despite the
   source's own comments implying a price comparison that the code never actually performs. The
   only place `"iHL"`/`"iLH"` labels come from is the demote-at-iBOS path above (`demoted_*`).
2. The internal engine's inside-bar filter is a silent no-op in the Pine source (it compares the
   current bar against itself due to statement ordering), so it never actually suppresses a
   qualifying candle. Preserved as-is.

---

## Source and validation

This engine is ported line-by-line from `indicators/structure_engine.pine`, a Pine Script v6
indicator that is itself a market-structure-only extraction from `indicators/mpc_assistant.pine`
(all non-structure features — order blocks, sessions, kill zones, VWAP, liquidity levels,
Fibonacci, SVP — stripped out; the structure detection logic itself is byte-for-byte identical to
`mpc_assistant.pine`). Aaron validated `mpc_assistant.pine` on a live chart at ~99.99% parity
against the original private "Structure OS" TradingView indicator it was sourced to match.

This Python port carries the same detection logic forward. It does not re-derive or "clean up"
any of the rules — see `CLAUDE.md` and the `# NOTE:` comments in `engine.py` for the handful of
places where the Pine source's behavior looked slightly inconsistent with its own comments and was
preserved as-is rather than corrected.

**Pine ↔ Python parity is confirmed empirically, not just by construction.** Running
`tools/compare_tradingview.py` on the `OANDA_XAUUSD, 15m` export (21,729 bars, `--major-length
15`) matches on every field of every bar (exit 0). Getting there closed one real porting gap: the
port had been raising external `new_swing_high`/`new_swing_low` on the mid-pullback
break-promotion path, which the Pine source never does — that false signal seeded the internal
engine early and drifted `internal_mode` for ~22 bars before an SOS resynced it. Fixed 2026-07-02.
Re-run the tool after any change to `engine.py` to keep this at 100%.

A **second** port gap was found later the same day: the eight break-leg fields
(`bull_bos_high`/`h_loc`/`low`/`l_loc` + bear mirror) existed in `structure_engine.pine` but were
never carried into the Python port, so the Sniper-fib anchor had nothing to attach to. They were
added to `engine.py` and to the export/compare tooling (the `px_bull_bos_high` /
`px_bull_bos_h_ago` columns, with `_loc` exported as "bars ago" so it survives Pine's absolute
`bar_index` vs the engine's 0-based index). Their Pine↔Python parity was then **confirmed
2026-07-02** on a fresh `VANTAGE_XAUUSD, 15m` export (9,721 bars, a second independent dataset from
the original OANDA run): all eight fields match on every one of the 9,494 warm bars (exit 0 with
`--warmup 227`). Only the first 227 bars differ, because the Pine export begins at a non-zero
`bar_index` — TradingView had history before the export window, so its engine was already warm
while the Python engine starts cold; both converge once the structure re-establishes in-window.
