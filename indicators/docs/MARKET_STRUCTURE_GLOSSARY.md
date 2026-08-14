# Market Structure — Student Reference Guide

**For:** reading market structure on MPC-JARVIS.
**What this is:** a glossary of every label and line the indicator draws, and what each one is
telling you. Reference sheet, not a course.

---

## The idea in four sentences

The indicator watches two levels at all times: the **active swing high (ASH)** and the **active
swing low (ASL)**.

When a candle **closes** beyond one of them, structure has **broken**.

- Broke **with** the trend → **BOS**. The trend continues.
- Broke **against** the trend → **SOS**. The trend has flipped.

The level that broke then gets its permanent name — **HH, HL, LH or LL** — and the indicator moves
on to watch the next one.

---

## Labels — main structure

| Label | Name | What it's telling you |
|---|---|---|
| **ASH** | Active Swing High | The high being watched right now. A close above it breaks structure. |
| **ASL** | Active Swing Low | The low being watched right now. A close below it breaks structure. |
| **BOS** | Break of Structure | Structure broke **with** the trend. Continuation. |
| **SOS** | Shift of Structure | Structure broke **against** the trend. The trend just changed. Your course calls this a **CHoCH**. |
| **HH** | Higher High | A broken high that sat **above** the last confirmed high. |
| **LH** | Lower High | A broken high that sat **below** the last confirmed high. |
| **HL** | Higher Low | A broken low that sat **above** the last confirmed low. |
| **LL** | Lower Low | A broken low that sat **below** the last confirmed low. |

**Reading the sequence:** HH + HL repeating = healthy uptrend. LH + LL repeating = healthy
downtrend. The moment that pattern breaks, you get an SOS.

---

## Labels — internal structure

Internal is the **smaller structure inside the current move**. Same ideas, one grain finer. Every
internal label starts with **i** and is drawn in a fainter, dotted style.

| Label | Name | What it's telling you |
|---|---|---|
| **iSH / iSL** | internal Swing High / Low | An internal swing point. |
| **iHH / iLL** | internal Higher High / Lower Low | Further internal swing points as the move develops. |
| **iHL / iLH** | internal Higher Low / Lower High | The pullback point named at an internal break. |
| **iBOS** | internal Break of Structure | The internal move is continuing. |
| **iSOS** | internal Shift of Structure | The internal move has flipped. |

**Internal disappears on every main break.** That is normal and intended. Internal only ever
describes what is happening *inside* the current leg — once the main structure breaks, that leg is
over and the internal labels go with it.

Use internal for **earlier** signals inside a move. Use external for the **actual** trend.

---

## Reading the chart without labels

You can turn the swing labels off and still read everything from the lines.

| What you see | What it is |
|---|---|
| **Thin dashed line** | An early swing level, not yet settled. |
| **Thin solid line** | The **live ASH / ASL** — the level currently being watched. |
| **Thick solid line** | A level that has **been broken**. The historical record. |
| **Dotted, faint line** | **Internal** structure. |

**Colours:** blue = bullish, red = bearish.

**Where labels sit:** highs are labelled above the candle, lows below. BOS/SOS text sits in the
middle of the move, on the level that broke.

---

## Terms you'll hear

**Break** — a candle **body close** beyond the level. A wick through it is not a break.

**Active swing (ASH/ASL)** — the level being watched. Not yet judged.

**Confirmed swing (HH/HL/LH/LL)** — a level that has broken and now has its permanent name.

**Trend direction** — set by the **last break**, nothing else. A bull break makes it bullish, a bear
break makes it bearish.

**Leg** — one impulse move, from where it launched to where it broke. Fibs are drawn across legs.

**Pullback** — a move back against the current direction.

**Strong side / weak side** — in an uptrend the swing **low** is the protected side and the **high**
is the side expected to break. Reverse it in a downtrend. This is why stops go behind swing lows on
longs.

---

## The table rows

The 4H / 15m / 1m rows tell you each timeframe's latest structural event:

| Term | Meaning |
|---|---|
| **Shift** | That timeframe just **reversed** (an SOS). |
| **Expansion** | The **first** continuation after a reversal. |
| **Continuation** | The trend is **extending** further. |

**Bullish / Bearish** on those rows is that timeframe's current direction.

**EXT / INT** rows show the most recent main and internal break.

---

## Display settings

| Setting | What it does |
|---|---|
| **Show External Structure** | Shows/hides the main structure. |
| **Show Internal Structure** | Shows/hides the internal layer. |
| **Show Swing Point Labels** | Off (default) hides ASH/ASL/HH/HL/LH/LL text, leaving **only BOS/SOS and iBOS/iSOS**. |
| **Structure Label Size** | Text size. |
| **Market Structure mode** | Turn off *Show Chart Tools* and *Show Fibs* for a clean structure-only chart. |

Display settings only change what you **see**. They never change what the indicator detects.

---

## Course language vs chart language

| Course says | Chart prints |
|---|---|
| CHoCH | **SOS** |
| BOS | **BOS** |
| I-CHoCH | **iSOS** |
| I-BOS | **iBOS** |
| Unconfirmed swing | **ASH / ASL** |
| Confirmed swing | **HH / HL / LH / LL** |

---

## Four things people get wrong

1. **"A wick through the level is a break."** No — it takes a **body close**.
2. **"HH/LL appear when the swing forms."** No — they appear when the swing **breaks**. Until then
   it is just ASH/ASL.
3. **"An SOS immediately names the new swing HH or HL."** No — after a reversal the new level shows
   as **ASH/ASL** until the next break names it.
4. **"Internal structure vanishing is a glitch."** No — it clears on every main break, by design.
