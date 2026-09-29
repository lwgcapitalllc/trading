# Notes — Reconciling a study against the lab

The rule, why it exists, and the one reconciliation that proved the harness. The one-line rule is in
`backtest/CLAUDE.md` → `## Rules`; the detail lives here.

---

## The rule (2026-09-28)

**No study number is quoted until it is reconciled against a lab run — or it is labelled "not
reconciled".** A study is a screen: every setup, no position slot, no sizing, no minimum stop. The
lab is the strategy. When they disagree, the study is describing a trade the strategy does not take.

**Reconciled means:** `backtest/tools/study_vs_lab.py` has matched the study's trades against a lab
run of the same idea, and every unmatched trade is explained by a NAMED, deliberate difference (the
study takes every setup where the lab holds one position; the study has no minimum stop). "Lab was
flat" with no note, or a lab trade with no study setup, is unexplained, and the number is not
reconciled.

**How:** a study reads its setups through `backtest/setup_feed.py` (never miss records or any other
summary written after a setup ends), writes its trades in the tool's JSON format, and the tool is
run against the lab run id.

## Why — the anchor that looked ahead

A study said the 1-minute SOS-then-BOS entry on SOS Fade Generic made **+0.26R** a trade on GBPJPY
after costs. Built into the strategy and run in the lab (`8bcf06ffa418`) it made **−0.06R**. The
trade-by-trade match-up:

| group | trades | lab R/trade | study R/trade |
|---|---|---|---|
| both, same minute | 108 | +0.21 | +0.26 (107 same outcome) |
| lab only | 105 | −0.34 | — |
| study only | 76 | — | +0.35 |

100 of the 105 lab-only trades entered **before** the study's start point. The study took each
setup's start from its MISS record, whose zone time brackets the setup's DEEPEST visit to the zone —
known only once the setup is over. It skipped the early visits that went on to the 1.0 and started
at the dip that held. **When the two took the same trade they agreed; the edge was the anchor.**
Every Generic FX screen in `docs/SOS_FADE_GENERIC_SPEC.md` used that same collector.

## What the rebuilt study mirrors, and what each fix was worth

`generic_ltf_trigger.py` on the point-in-time feed, GBPJPY 1m, 2020-01-01 → 2026-09-26, against
`8bcf06ffa418`. Each row was found by running the match-up, not by reading code:

| fix | matched | same outcome | study only | lab only | matched R, lab / study |
|---|---|---|---|---|---|
| old study (miss-record anchor) | 108 | 107 | 76 | 105 | +0.21 / +0.26 |
| point-in-time feed, lab's window, one continuous 1m structure feed | 212 | 209 | 1 | 1 | −0.055 / −0.044 |
| + no time limit on a trade (the lab has none; one ran 66 days) and a short's stop and target on the ASK | 213 | 212 | 1 | 0 | −0.062 / −0.077 |
| + a short's spread not charged again as a cost | 213 | 212 | 1 | 0 | **−0.062 / −0.064** |

- **The ask:** two shorts the bid walk called wins were lab losses — one touched its target exactly
  on the bid, one missed its stop by 0.011 where the ask (bid + 0.015) reached it. The lab fills a
  short's buy on the ask.
- **The spread, once:** after the ask fix, matched longs agreed to 0.001R a trade and shorts were
  0.029R worse — the study charged a short's spread twice, once in its exits and once as a cost.
- **Left over, all named:** one study-only trade, a stop of 0.067% of price under the lab's 0.08%
  minimum (the study NOTES it via `--min-stop-pct`); one outcome difference, a scratch (−0.006R
  study, +0.014R lab). No trade was lost to the lab holding a position on this run.

⚠ **A fresh replay of the lab's settings differs from the STORED run on 60 of 213 trades**, all but
two by a few hundredths of an R, and those two are the spread cases above — most likely the
bid/ask fills that replay did not model (not checked further). Compare a study against the stored run the tool fetches, never against a
different replay.

⚠ **Not re-run:** GBPUSD (`0c4b00e3325f`), and the zone-turn, POC and FX-pattern screens. Their
numbers in the spec stay labelled not reconciled.
