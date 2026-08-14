# CLAUDE.md — SVP (Session Volume Profile) Engine Subsystem

**Purpose:** Turn the bar stream into the Asia session POINT-OF-CONTROL — the "MV" line — plus its
confirmation. On each Asia session close the engine builds a volume profile over the session's range
and reports the price of the highest-volume row (the POC), then tracks whether price has since tapped
it. The signal is the POC value + the form/sweep edges ("Asia POC = 4486.6", "price just tapped it"),
not the drawn histogram.
**Scope:** The Asia POC price + a form edge + the MV sweep (confirmation) only. No trading decisions,
no MT5 ops, no UI, no chart rendering (no histogram, POC line or label). Like VWAP it needs a
**volume** column in the feed.
**Status:** Production — ported from the SESSION VOLUME PROFILE block in `mpc_assistant.pine`, unit-
tested (12 hand-traced tests, green), and **100% Pine-parity-validated on a real `VANTAGE_XAUUSD, 5m`
export** (13,147 bars). **Row count re-synced 100 → 50 on 2026-07-09** (mpc line 317) and re-validated
on a fresh 50-row export (`--warmup 251`, exit 0). The one canonical implementation — no consumer builds its own.
**Pine:** ported from `indicators/engines/mpc_assistant.pine` — the SVP block (line ~2554) + its
confirmation-table "MV slot" (line ~2772); parity harness is `indicators/engines/svp_export.pine`, diffed
against this Python by `tools/compare_svp.py`. Pine stays in `indicators/` (shared source,
TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-07-31 — ✅ **UNAFFECTED by the session re-sync, and now MEASURED rather than argued.** The 2026-07-31 mpc paste moved all three session windows into their own cities' clocks, which made `engines/sessions/` and `engines/liquidity/` stale (see those files). **This engine is not**, because it composes the **Asia** window only and Asia is the one window that did not move: `2000-0500` GMT-4 and `0900-1800` Asia/Tokyo are both 00:00–09:00 UTC in every season (a fixed offset on one side, no DST in Japan on the other). `_ASIA_SPEC` and `SVP_SESSION`/`SVP_TZ` were restated in the Pine's new words — **a re-expression, not a behaviour change** — and `engines/sessions/`'s `test_asia_session_is_utc_stable_year_round` pins the equivalence in both seasons so a genuine future move fails loudly instead of silently repricing every POC. **PARITY RE-VALIDATED the same day on a fresh export off the restated Pine:** `compare_svp.py "VANTAGE_XAUUSD, 5_2c023.csv" --warmup 317` → **exit 0**, 12,117 bars. That run also demonstrates this engine's cold start, which is longer than the tick-level engines' and worth budgeting for: the first POC cannot exist until a WHOLE Asia session has closed inside the export (bar 201 here), and `mv_swept` needs longer still (bar 317) because Pine carries a True flag in from a session before the export and only resets it on the next Asia **open**. At `--warmup 202` the POC itself matches on every bar and the only residue is that carried boolean — so the warm-up is entirely cold start, not a mask. 12 unit tests green. Earlier: 2026-07-09

---

## What this engine is (ported semantics)

While the **Asia session** (0900-1800 Asia/Tokyo — the same window as the sessions engine's Asia) is open,
the source tracks the running session high/low. When it closes it builds a 50-row volume profile over
`[low, high]`: each session bar's volume is spread evenly across the price rows the bar's high/low
span, and the row that accumulated the most volume is the **POINT OF CONTROL**. Its mid-price is the
"MV" line.

    range      = sessionHigh - sessionLow
    per bar b: rLo = clamp(floor((low_b  - sessionLow)/range*50), 0, 49)
               rHi = clamp(ceil ((high_b - sessionLow)/range*50) - 1, 0, 49)
               span = max(1, rHi - rLo + 1);  add volume_b / span to every row in [rLo, rHi]
    POC row    = argmax over rows of (bull volume + bear volume), first max wins (strict >)
    POC price  = sessionLow + (pocRow + 0.5) * (range / 50)

The **MV slot** (confirmation table) then marks the most recent POC `swept` / "Confirmed" the first
time a bar straddles it (`high >= poc and low <= poc`), and resets on the next Asia **open**
(Pine `svpNew`). The reset moved from the Asia close (`svpEnd`) to the next Asia open on 2026-07-06
to match a re-pasted `mpc_assistant.pine` — so a confirmed POC now stays confirmed all day until the
next session opens, instead of being wiped the moment its own session closes.

### Two Pine quirks ported exactly

1. **The session-close bar is folded into the profile.** Pine's `svp_sLen = bar_index - svp_startBar
   + 1` and its loop `for b = 0 to svp_sLen-1` reach from the close bar (the first OUT-of-session bar,
   b=0) back to the session's first bar, so the bar the session closes ON is binned into the profile
   even though it is outside the Asia window. The engine replicates this by appending the current
   (close) bar to the buffered session bars before binning.
2. **Newest-first, two-array summation is kept.** Pine walks b=0 (newest) → older and keeps bull
   (`close>=open`) and bear volume in SEPARATE arrays, summed into the row total only at the end. The
   engine keeps that exact structure and order — **not** to draw the up/down colours (that drawing is
   dropped) but because float addition is not associative: collapsing the two arrays or reversing the
   order could flip a near-tie POC row and break the exact-price parity.

### One deliberate deviation (= "emit events, not visuals")

All drawing is dropped — the POC line/label arrays, their FIFO of lines, and the up/down histogram.
Only the POC-price FIFO (`svp_poc_px`, capped at `svpHistory`=2) survives, since `mv_pocPrice` reads
its most recent entry. The bull/bear split is retained (see quirk #2) but only as summation structure.

---

## The anchor = the Asia session (no calibration knob)

Unlike VWAP / liquidity, the SVP anchor is the **Asia session** (0900-1800 **Asia/Tokyo** — Japan has no DST, so
season-independent), NOT the trading-day boundary. So there is no `--htf-rollover` to sweep. The Asia
window, its running high/low and its open/close edges come from the composed, already-Pine-validated
`engines/sessions/` engine (see below).

---

## Volume + timeframe

Like VWAP, this engine needs the bar's **volume** (for XAUUSD, tick volume — what Pine's `volume`
reads; the parity export feeds `px_volume` back so both sides use the identical series). A bar with na
volume contributes nothing. It is an **intraday** feature: Pine gates the whole block on
`timeframe.isintraday` and the Asia window is a sub-day session, so feed intraday bars (the parity run
is 5m).

---

## Key paths

```
engines/session_volume_profile/
├── engine.py       ← SvpEngine: the streaming state machine (composes engines/sessions/)
├── types.py        ← SvpEvents (poc + formed + swept + confirmed)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py       ← 12 hand-traced tests
└── tools/
    └── compare_svp.py       ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `indicators/engines/mpc_assistant.pine` — SVP block (2554-2659), MV slot (2772-2786).
Parity export build: `indicators/engines/svp_export.pine`.

---

## Public API

```python
from session_volume_profile import SvpEngine, SvpEvents

sv = SvpEngine()  # Pine defaults: Asia 0900-1800 Asia/Tokyo, 50 rows, keep 2 POCs

# Each closed intraday bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
ev = sv.update(bar.index, bar.timestamp_ms, bar.open, bar.high, bar.low, bar.close, bar.volume)

ev.poc  # current Asia POC / MV line (None until the first session closes) — Pine-validated
ev.formed  # did a fresh POC form this bar (Asia just closed, range>0)? (edge)
ev.swept  # has the current POC been tapped since it formed? (state)
ev.confirmed  # did price tap the POC for the first time this bar? (edge)
sv.poc()  # current POC (read)
```

`history` (FIFO cap on kept POCs) and an injectable `session_engine` are the two constructor knobs.

---

## Relationship to the other engines

- **Composes `engines/sessions/`** for the Asia window/edges + running H/L — the same pattern
  `engines/liquidity/` uses. Pine's own svp_hi/svp_lo/svp_startBar are exactly the sessions engine's
  Asia `SessionRange` (Pine-parity-validated there), so the session bookkeeping is not re-derived.
- **Time-driven + volume**, like `engines/vwap/`. It needs the bar's UTC timestamp (for the Asia
  window, via the sessions engine) plus open/high/low/close **and volume**. Not downstream of
  `engines/market_structure/`.
- Downstream of nothing. A bot consuming it will get an `algos/shared/` shim (none built yet).

---

## Do

- Port any change to `mpc_assistant.pine`'s SVP / MV-slot blocks back here. Keep the 50 rows, the
  `floor`/`ceil` row-binning with the clamps, the `span = max(1, …)` even-spread, the strict-`>`
  first-wins POC, the close-bar inclusion and the newest-first two-array summation EXACT.
- Keep the Asia window in step with the sessions engine — both read 0900-1800 Asia/Tokyo.
- When adding a field, update this file's Public API and the tests in the same commit.

## Never do

- Do not collapse the bull/bear arrays into one total or reverse the replay order — it can flip a
  near-tie POC row and break the exact-price parity (see quirk #2).
- Do not drop the close-bar-in-profile behaviour (quirk #1) — it is Pine-faithful and validated.
- Do not bake in the histogram, POC line, colours or labels — this layer emits a value + events.
- Do not build a second SVP implementation elsewhere. This is the canonical one.
- Do not let this engine or the SVP blocks in `mpc_assistant.pine` drift; re-run the parity check
  after any change to either.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/session_volume_profile/tests/ -q` (12 hand-traced tests pinning the
50-row profile + POC, the close-bar-in-profile quirk, the na/zero-volume guard, the degenerate-range
skip, the FIFO history, and the MV sweep state/edge).

**Full Pine↔Python parity — GREEN (2026-07-09, 50-row build).** After the `svpRows` **100 → 50** re-sync,
100% match on a fresh real `VANTAGE_XAUUSD, 5m` export (13,147 bars): all three fields — the POC price,
the form pulse and the sweep state — matched on every warm bar (`--warmup 251`, exit 0, 12,896 bars
compared). The POC uses an **exact** price tolerance (1e-6), NOT the relative
tolerance VWAP needs: the POC is a deterministic formula on the (copied) session H/L + integer volume,
so it is bit-identical — a whole-row jump (~range/50 on gold) would mean the POC ROW diverged, not
float noise. The 251-bar warm-up is because the chart carried a POC from an Asia session that closed
BEFORE the export window (Pine shows it from bar 0 with its sweep already set), while Python starts
cold; both sides form and agree from the first in-window Asia close (bar 251) on. The `formed` pulse
matched on every bar, warm-up included. (The prior 100-row build passed the same way on a separate 7,608-bar
export, `--warmup 116`.) The harness mirrors the other engines:

1. `indicators/engines/svp_export.pine` — the SVP block + MV slot lifted from `mpc_assistant.pine` (drawing
   removed) with `px_volume`, `px_svp_poc`, `px_svp_formed` and `px_svp_swept` columns. Put it on a
   **5-minute** `VANTAGE_XAUUSD` chart (SVP is intraday), Export chart data → CSV, drop it in
   `engines/session_volume_profile/exports/` (git-ignored).
2. `python3 engines/session_volume_profile/tools/compare_svp.py <that.csv> --warmup N` — feeds each bar (timestamp +
   OHLC + volume) through `SvpEngine` and diffs the three columns, bar by bar. Exit 0 = parity. If the
   export opens mid-Asia (or carries a pre-window POC), the tool prints the last mismatching bar; set
   `--warmup` past it. Standard library only.

Re-run `compare_svp.py` after any change to the SVP blocks in `mpc_assistant.pine` or here.

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` (SVP 2554-2659, MV slot 2772-2786).
- Parity export build: `indicators/engines/svp_export.pine`.
- Composed dependency (Asia window/edges): `engines/sessions/CLAUDE.md`.
- Sibling volume engine / the shared porting pattern: `engines/vwap/CLAUDE.md`,
  `engines/liquidity/CLAUDE.md`.
- Roadmap: `docs/ENGINE_EXTRACTION_ROADMAP.md` (SVP was the last SMC-port engine).
- Monorepo context: `../CLAUDE.md`.
