# Market Structure Rule Engine — Spec

Derived from the SMC Engine training (Modules 1–4). Platform-agnostic rules, mapped to the LWG build and a LuxAlgo (Price Action Concepts) implementation path. This is the conceptual skeleton — your own engine, not a copy of his indicator.

---

## Core principle

Structure is mechanical, not subjective. Every swing point must be confirmed by a valid pullback. No valid pullback = no confirmed point. Without a pullback rule, 100 people mark the same chart differently — the rule is what makes the markup deterministic.

---

## 1. Swing points: definition & confirmation

- Two structure layers run on the **same timeframe**: SWING (external) and INTERNAL (inside the swing range). Swing vs internal is NOT a timeframe distinction — that is the most common misconception.
- A candidate swing high/low is **UNCONFIRMED** (drawn dashed) until a valid pullback occurs. Once validated it becomes **CONFIRMED** (solid).
- A swing high is confirmed only once the prior swing low is broken by body close (and vice versa). A pullback alone does not confirm it — price could pull back then continue.
- **Break = candle BODY close beyond the level. A wick through does NOT count.** This is the rule that keeps the prior level intact when price only whips it.
- After a confirmed break, the swing point = the extreme reached before the break: highest high before a downside break (→ swing high), lowest low before an upside break (→ swing low).

## 2. BOS vs CHoCH

- **BOS (Break of Structure) = continuation.** Body-close break of the prior swing high in an uptrend / prior swing low in a downtrend.
- **CHoCH (Change of Character) = reversal.** Body-close break of the prior swing low in an uptrend / prior swing high in a downtrend. Flips the trend state; fires once per direction before the opposite must occur.
- LuxAlgo convention (worth adopting): a BOS is only valid *after* a CHoCH. Ben doesn't state this explicitly but his examples follow it. Successive BOS's are normal within one trend.
- Optional stricter filter: LuxAlgo's **CHoCH+** ("supported CHoCH") fires only when there was an early reversal sign first (a failed higher high / lower low). Useful as a higher-quality reversal gate if you want two confidence tiers.

## 3. Strong / weak sides

- After a CHoCH, the extreme that produced it is the **STRONG (protected)** side; the opposite is **WEAK (expected to break)**.
- Bullish trend: swing low strong, swing high weak → expect the high to break.
- Bearish trend: swing high strong, swing low weak → expect the low to break.
- Bias your entries toward taking out the weak side.

## 4. Internal structure

- Internal = all structure inside the current swing range (swing low → swing high "box").
- Labelled with an **I-** prefix: I-HH, I-HL, I-BOS, I-CHoCH.
- Internal structure **resets/clears** when price breaks the swing range and new swing points form. It only exists while a range is live.
- Use: a deep pullback into the range followed by an **internal CHoCH** signals internal realigning with the swing direction — this is the trigger to target the swing extreme.

## 5. Multi-timeframe stack

- **4H / Daily** → directional bias.
- **15m** → operative structure / the shift.
- **1m** → entry only. ("1 minute is where we always enter.")
- Sequence: 15m shifts direction (e.g. bearish during London) → drop to 1m → wait for a 1m CHoCH in that same direction → 1m now aligned with 15m → enter.

## 6. Session liquidity (killzones)

- Times in **UTC−4**: Asia 20:00–00:00 (blue) | London 02:00–05:00 (green) | New York 07:00–10:00 (orange).
  - NOTE: transcript said London "2am till 5pm" — almost certainly 5am given killzone logic. Verify against the video before hardcoding.
- **Don't trade Asia. Trade London + New York.**
- Each session's high and low are liquidity targets.
- Logic: whichever side (high or low) is swept FIRST, the **unswept side is the target** for the rest of the session.
- Frankfurt (pre-London) sweeps count — the sweep can happen before London open.

---

## Mapping to existing LWG rules

- **CONFIRMS** — your body-close requirement for BOS/SOS matches Ben's body-close break rule exactly. Aligned, no change needed.
- **CONFIRMS** — wick-through-doesn't-count handling matches.
- **TERMINOLOGY** — your "SOS = body close below prior HL (trend failure)" is the same thing as Ben's bearish CHoCH. Same concept, different label. Pick one vocabulary for the engine so the code isn't ambiguous.
- **DIVERGES (entry model)** — your FFT uses the first fib touch into the 61.8–88.6% zone as the primary entry. Ben uses internal-CHoCH realignment inside the swing range as the trigger. These are different entry layers sitting on the *same* structural skeleton. Decision: run them as alternatives, or stack them as a confluence gate (structure engine defines the skeleton → fib-zone AND/OR internal-CHoCH fires the entry).
- **GAP** — the pullback-validity rule is the core of the whole engine and Ben never fully specifies it. You must define it. See below.

---

## The one decision that determines everything: the pullback rule

LuxAlgo detects swings via a **lookback** (configurable 5–49 bars) — fundamentally different from Ben's fixed wave rule. Because of that, LuxAlgo's markup shifts when you change the lookback, which is exactly the subjectivity Ben claims to eliminate. Two paths:

- **(a) Use LuxAlgo's lookback detection as-is.** Fastest to ship. Downside: structure is only as fixed as your chosen lookback number; it's not the timeframe-independent markup Ben implies.
- **(b) Replicate a fractal/wave pullback.** A confirmed pullback = price prints a swing extreme, then a defined fractal forms against it (e.g. a 3-bar fractal: a high with a lower high on both sides), confirmed by a body close. This is the closest mechanical analogue to "a certain order of candles as waves" and gives the deterministic, lookback-free markup that is Ben's actual selling point.

**Recommendation: (b).** It's more work but it's the thing that makes your engine behave like his rather than like a generic SMC indicator. The exact fractal/wave definition is the single variable that decides whether your output matches his — pin that down first, before any backtesting, because (per your own governing principle) wrong structure detection produces false passes that only fail live.

---

## LuxAlgo build path (practical)

Most of Sections 1–4 already exist in Price Action Concepts: swing/internal BOS/CHoCH, HH/HL/LH/LL labels, EQH/EQL, dashed-unconfirmed vs solid-confirmed lines. Your real build work is:

1. Decide the pullback rule (above) — and if going with (b), this likely means custom Pine on top of, or instead of, PAC's lookback engine.
2. Add the strong/weak side tagging if PAC doesn't expose it directly.
3. Add the session killzone boxes with the UTC−4 times (PAC's liquidity tools may not match these exact windows — likely a separate session-box script).
4. Wire the 4H/15m/1m alignment logic as your signal layer on top of the structure layer.
