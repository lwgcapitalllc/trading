# Notes — Liquidity levels: which charts each tier shows on, and when PWC rolls

Why each liquidity-level tier in `mpc_jarvis.pine` draws only up to its own timeframe, and why PWC
rolls on the live bar. **New detail on this topic goes HERE**, and the CLAUDE.md gets at most one
index line.

---

## 🔴 Each level tier shows only up to its own timeframe (2026-09-14)

A tier draws only on charts whose candle is no longer than the level's own period — H4 on 4H and
below, sessions on intraday charts (where the session boxes draw), daily on D and below, weekly and
PWC on W and below. The rule is written once, in the comment at `canShowDaily`.

Above that the level is read from inside ONE candle, and its taken state cannot update until that
candle closes. H4 on the daily showed the last 4-hour candle's range, but its sweep test waits for
a closed chart bar, so it sat solid all day after price took it. The weekly chart labelled the prior
week's range "Asia H / Ldn H / NY H". PWC drew on the monthly. Daily and weekly already followed the
rule; H4, sessions and PWC were the tiers missing it.

⚠ The LIQ table rows and the SOS Fade arm read the same switches, so those tiers drop out of them on
the bigger charts too. The SOS Fade row and its alerts run on 15m/1m only, where every tier is still
on, so no signal moves.

## 🔴 PWC rolls at the week's open, with PWH/PWL (2026-09-14)

Below a weekly chart PWC could not roll until the week's first chart bar CLOSED, so on the daily it
showed the week-before-last's close for all of Monday — while PWH/PWL, given the live-roll gate on
2026-07-13, had already moved. It now shares their gate: it rolls on the week's first live tick, and
still waits for the close on the weekly chart, where the value IS the live close.

⚠ **Live bar only** — on history every bar is closed, so no historical drawing and no parity gate can
move. It only ever showed on a live chart; a reload after the week's first bar closed hid it.

⚠ **The strategy Pines were deliberately left alone.** They carry the older weekly block, where
PWH/PWL wait for the close too and feed the sweep pools SOS Fade arms on. Rolling PWC alone there
puts it ahead of its neighbours; porting the whole block is a trade-affecting change. The delay never
shows in a backtest.
