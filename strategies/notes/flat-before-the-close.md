# Flat before the close — the shared switch, and what it costs

**Owner:** `strategies/python/time_flat.py`, plus each bot's `flat_mode` setting.
**Read this before** turning the switch on anywhere, quoting a number from it, or adding a
fourth strategy that wants one.

---

## The question Aaron asked (2026-09-19)

> *"We don't hold trades over the weekend. So 15 minutes before the market closes for the
> weekend, we just close all the trades, winners or losers. And then we don't hold between days
> … and that includes bank holidays."*

His stated motive is not statistical: *"I don't think I could mentally watch trades being held
over the weekend."* That is a legitimate requirement and it is his to set. What this note owns
is the PRICE, measured rather than argued.

---

## The answer: it is expensive on all three bots, and it does not reliably buy drawdown

2020-01-02 → 2026-08-06, XAUUSD, `VantageMarkets_Demo` bars, **costs charged** at
`puprime_standard` (spread, swap, commission). Each bot on its own shipped defaults with one
axis moved. Every row is `backtest/tools/axis_sweep.py`, and each run's control row reproduced
the shipped baseline before any other row was read.

| bot | mode | trades | sum R | max DD | R per R of DD |
|---|---|---|---|---|---|
| **SOS Fade** (15m) | Off *(shipped)* | 155 | **+196.88** | 10.34 | **19.0** |
| | Friday only | 155 | +105.40 | 8.02 | 13.1 |
| | Every day | 155 | +65.04 | **5.76** | 11.3 |
| **Extreme leg** (5m) | Off *(shipped)* | 125 | **+50.93** | **7.40** | **6.9** |
| | Friday only | 125 | +46.16 | 8.15 | 5.7 |
| | Every day | 127 | +26.83 | 10.37 | 2.6 |
| **Realign** (5m) | Off *(shipped)* | 113 | **+82.41** | **6.19** | **13.3** |
| | Friday only | 114 | +58.34 | 6.43 | 9.1 |
| | Every day | 115 | +36.26 | 6.41 | 5.7 |

**Across the three books: +330.2R shipped, +209.9R on Friday only (−36%), +128.1R on Every day
(−61%).**

🔴 **The drawdown argument only works on ONE bot and it is not free there either.** SOS Fade's
drawdown does fall — 10.34R → 5.76R on the daily rule — but its return falls further, so return
per unit of drawdown drops from 19.0 to 11.3. **On the other two bots the drawdown gets DEEPER**:
the extreme leg goes 7.40R → 10.37R, realign 6.19R → 6.43R. Cutting winners short does not make
an equity curve smoother; it removes the winners that were paying for the losers, and the losers
are still there.

⚠ **The mechanism, and it is the same one Run 12 recorded for loosening an entry.** These bots
have ONE position slot. A trade closed at 16:45 does not free capacity for a better trade — it
just books a partial result on a move that had not finished. The p90 hold on SOS Fade is 64
hours; the rule is asking the strategy to stop being the strategy.

## What it would buy, measured on raw price

Every session break in the XAUUSD M1 tape 2020-01-01 → 2026-09-16, classified by the length of
the hole and sized by the jump through it:

| break | n | median | p90 | p99 | worst |
|---|---|---|---|---|---|
| nightly | 1,384 | $0.43 | $2.24 | $9.67 | $33.76 |
| weekend | 336 | $1.38 | $13.52 | $61.87 | **$118.26** |
| holiday, extending a weekend | 14 | $3.19 | $14.30 | $28.24 | $29.87 |
| holiday, mid-week | 4 | $7.39 | $20.66 | $23.18 | $23.46 |

**The weekend tail is real and the overnight one is not.** That is the honest case for "Friday
only" and the case against "Every day": a nightly gap clears a typical stop 0.3% of the time,
a weekend gap 11.1% (the stop-distance scaling is in `sos_fade_optimization.md` → Run 24).

⚠ **And the protection is already priced in.** 44% of SOS Fade's book already sits through a
nightly break and 9% through a weekend, and the measured result of closing them is the table
above. The gap risk is not free money being thrown away — it is the cost of the hold that the
returns are made of.

## The recommendation

**Do not switch it on for return. Switch it on for sleep, knowing the bill.** If it is going on,
**"Friday only" on SOS Fade is the least-bad version** — it is the bot whose drawdown actually
falls, and the weekend is the only break whose tail justifies the rule. It still costs 46% of
that book's return over 6.6 years, so it is a preference purchase and must never be written up
as a risk improvement.

⚠ **Every figure here has the 1-minute re-entry pinned OFF on SOS Fade**, because the sweep
harness replays one frame and refuses to run that feature. Both sides of every SOS Fade row are
matched, so the comparison stands; the absolute R does not describe the shipped bot.

---

## The code — what was built, and the two defects it caught

`strategies/python/time_flat.py` is the ONE clock. Before it there were three answers to
"is the market about to close" and they disagreed:

| | before | now |
|---|---|---|
| SOS Fade | a DAILY window, closing at this bar's close | `flat_mode`, closing at this bar's close |
| Realign | a FRIDAY window of its own, next bar's open | `flat_mode`, next bar's open |
| Extreme leg | **nothing** — an independent implementation | `flat_mode`, next bar's open |
| Holiday closes | nobody had heard of them | the generated calendar |
| the Pine | `realign_strategy.pine` had had the three-position input all along | Python now spells it the same |

**The switch is `flat_mode`: `"Off"` / `"Friday only"` / `"Every day"`, shipped Off everywhere.**
The strings are copied from the Pine input, not improved on — a nicer Python name is a red parity
gate. `flat_by_close` still works and is promoted to `"Every day"`; setting both is refused,
because that is a config with two opinions about one switch.

**The holiday calendar is GENERATED, never listed.** Good Friday by the computus, Christmas and
New Year observed-shifted with an early close on the eve, Thanksgiving and the Friday after. It
is validated against all **18** extended breaks in the measured tape and keeps generating past
them — a typed list would stop protecting in a year nobody is watching.

### Two defects this build produced, both caught before anything shipped

1. 🔴 **"Friday only" fired every weekday.** The rule asked the calendar for a date's close HOUR
   and treated any answer as "this is a holiday"; an ordinary day answers 17. It was invisible
   in isolation and showed up as **two sweep rows agreeing to four decimal places across 127
   trades** — the negative result a healthy system also produces, rule 2, in a new place. The
   calendar now answers `is_early_close`, which is the question the caller meant.
2. 🔴 **The "window must exceed one bar" guard refused a shipped configuration.** SOS Fade is a
   15m bot with a 15-minute window, and its flat closes at THIS bar's close, so it needs no lead
   bar at all. The guard now takes `exit_delay_bars` from the caller — the lead required is the
   CALLER's timing, not the module's.

### How to re-run any number here

```
python3 backtest/tools/axis_sweep.py --strategy <sos_fade|extreme_leg|realign> \
    --symbol XAUUSD --tf <15|5|5> --server VantageMarkets_Demo \
    --start 2020-01-02 --end 2026-08-06 --split 2023-05-01 --profile puprime_standard \
    --axis "flat_mode=Off,Friday only,Every day" [--pin exec_secondary=False]   # sos_fade only
```

The break table comes from a throwaway script over `backtest/cache/PUPrime_Demo/XAUUSD_p__M1.csv`
that classifies every hole longer than five minutes; no repo file was modified to take it.

## What is NOT measured

- **No Pine twin exists for SOS Fade or the extreme leg**, so a run with the switch on is
  compared against nothing. Only realign's gate can check it, and only at the settings an export
  carried.
- **No live bot has ever run it.** Rule 9 applies in full.
- **Refusing a new ENTRY inside the window** is done by the SOS Fade family and not by the
  extreme leg, which enters at the bar's close and would therefore open a trade at 16:50 and
  close it at the next open for a spread. Open question, not an oversight.
- **Whether the rule interacts with the account risk cap.** Two bots flattening into the same
  minute is a different book from two bots holding; nothing here measured the stack.
