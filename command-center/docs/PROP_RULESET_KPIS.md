# Prop Ruleset KPIs — Seeded Challenges Reference

**Status:** 📘 **LIVING REFERENCE — the source of truth for what is seeded in `lab.db` → `rulesets`.** It goes stale the moment a firm changes its rules, and **nothing detects that automatically** — `/prop-firm-rules-audit` re-checks these rows against each firm's published docs, and is the only thing that will.

**What this is:** the single source of truth for the prop-firm challenges seeded in our ruleset engine
(`command-center/backend/data/lab.db`, table `rulesets`). It captures the core KPIs we trade against —
account size, profit target, drawdown type + amount, consistency, minimum trading days, and contract
scaling — for every **eval** and **funded** row, with the firm documentation links.

**How to use it:**
- Hand the snapshot tables below to Claude chat so it knows exactly which challenges we run against.
- Run the **verification prompt** (bottom of this doc) periodically to re-check the firm docs and
  confirm our DB still matches them.
- The **saved sync query** lets any agent dump the live DB without rebuilding the query each time.

**Last verified against firm docs:** 2026-06-17
**Rows in DB:** 14 prop rulesets (Lucid ×4, FundedNext ×4, Tradeify ×4, Apex ×2). All futures, all
`drawdown_type = trailing_eod`, all `drawdown_unit = usd`.

> Snapshot caveat: the tables here are a point-in-time copy. The **DB is authoritative** — run the saved
> query (below) to get current values. If the query and this doc disagree, the doc is stale: fix the doc.

---

## Snapshot — all 14 prop rulesets

Money values in USD. "MLL" = the trailing end-of-day max-loss (our `max_loss_eod`), the drawdown amount.
"Lock" = balance at which the trailing floor stops trailing (`mll_lock_balance`). "—" = not set / not published.

| Ruleset ID | Tier | Acct | Profit Target | MLL (drawdown) | Lock @ | Consistency | Min Days | DLL | Split | Flat (ET) |
|---|---|---|---|---|---|---|---|---|---|---|
| `lucidflex_50k_eval` | eval | 50,000 | 3,000 | 2,000 | 50,100 | ≤50% | — | — | — | 16:45 |
| `lucidflex_100k_eval` | eval | 100,000 | 6,000 | 3,000 | 100,100 | ≤50% | — | — | — | 16:45 |
| `lucidflex_50k_funded` | funded | 50,000 | — | 2,000 | — | — | — | 2,000 | — | 16:45 |
| `lucidflex_100k_funded` | funded | 100,000 | — | 3,000 | — | — | — | 3,000 | — | 16:45 |
| `fundednext_flex_50k_eval` | eval | 50,000 | 2,500 | 1,500 | 50,100 | ≤40% → raises target | — | — | — | 16:10 |
| `fundednext_flex_100k_eval` | eval | 100,000 | 5,000 | 2,500 | 100,100 | ≤40% → raises target | — | — | — | 16:10 |
| `fundednext_flex_50k_funded` | funded | 50,000 | — | 1,500 | — | — | — | 1,500 | 80% | 16:10 |
| `fundednext_flex_100k_funded` | funded | 100,000 | — | 2,500 | — | — | — | 2,500 | 80% | 16:10 |
| `tradeify_50k_eval` | eval | 50,000 | 3,000 | 2,000 | 50,100 | ≤40% | 3 | — | — | 16:59 |
| `tradeify_100k_eval` | eval | 100,000 | 6,000 | 3,000 | 100,100 | ≤40% | 3 | — | — | 16:59 |
| `tradeify_50k_funded` | funded | 50,000 | — | 2,000 | — | — | — | 2,000 | 90% | 16:59 |
| `tradeify_100k_funded` | funded | 100,000 | — | 3,000 | — | — | — | 3,000 | 90% | 16:59 |
| `apex_eod_50k_eval` | eval | 50,000 | 3,000 | 2,000 | 53,000 | — | — | 1,000 | — | — |
| `apex_eod_100k_eval` | eval | 100,000 | 6,000 | 3,000 | 106,000 | — | — | 1,500 | — | — |

### Contract limits & scaling

| Ruleset ID | Base (mini/micro) | Scaling |
|---|---|---|
| `lucidflex_50k_eval` | 4 / 40 | none (full size day one) |
| `lucidflex_100k_eval` | 6 / 60 | none |
| `lucidflex_50k_funded` | 2 / 20 | bidirectional band (EOD simulated profit): $0–999 → 2/20 · $1k–1,999 → 3/30 · $2k+ → 4/40 (ceiling 4/40) |
| `lucidflex_100k_funded` | 3 / 30 | bidirectional band: $0–999 → 3/30 · $1k–1,999 → 4/40 · $2k–2,999 → 5/50 · $3k+ → 6/60 (ceiling 6/60) |
| `fundednext_flex_50k_eval` | 3 / 30 | none · minis+micros mixable at 1 mini = 10 micros (excess-contract profit voided, not a breach) |
| `fundednext_flex_100k_eval` | 5 / 50 | none · mixable 1:10 |
| `fundednext_flex_50k_funded` | 3 / 30 | none · mixable 1:10 |
| `fundednext_flex_100k_funded` | 5 / 50 | none · mixable 1:10 |
| `tradeify_50k_eval` | 4 / 40 | none · cannot hold minis + micros simultaneously |
| `tradeify_100k_eval` | 8 / 80 | none |
| `tradeify_50k_funded` | 2 / 20 | cumulative ratchet (EOD profit above start, retained once reached): start 2/20 · +$1,500 → 3/30 · +$2,000 → 4/40 (ceiling 4/40) |
| `tradeify_100k_funded` | 3 / 30 | cumulative ratchet: start 3/30 · +$1,500 → 4/40 · +$2,000 → 5/50 · +$3,000 → 8/80 (ceiling 8/80) |
| `apex_eod_50k_eval` | 6 / 60 | none |
| `apex_eod_100k_eval` | 8 / 80 | none |

---

## Per-firm detail + documentation links

### Lucid — LucidFlex (futures · EOD trailing drawdown)
The firm is **Lucid (Lucid Trading)**; **LucidFlex** is the program name.
- Evaluation account: https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account
- Drawdown: https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown
- Consistency %: https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage
- Scaling plan: https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan
- Funded account: https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account

Key points: EOD trailing MLL, trails up never down, locks $100 above start once cleared. Eval consistency
50%. **No minimum trading days** (verified — Lucid publishes none for LucidFlex evals). Funded scaling is
bidirectional (limits rise *and* fall with the EOD simulated-profit band). Auto-flat 16:45 ET, no overnight.

### FundedNext — Futures Flex (futures · EOD trailing drawdown)
- What is the Flex challenge: https://helpfutures.fundednext.com/en/articles/14878751-what-is-fundednext-futures-flex-challenge
- How to pass: https://helpfutures.fundednext.com/en/articles/14878830-how-do-i-pass-fundednext-futures-flex-challenge

Key points: EOD trailing MLL, locks at $100 above start. **40% consistency is challenge-phase only and is
unusual** — breaching it does **not** fail the account, it **raises the profit target** (`consistency_breach_action = raise_target`).
**No minimum trading days in the challenge.** Funded stage needs **5 benchmark (winning) days for withdrawal
eligibility** — that's a payout rule, not an eval-pass rule, so it is not stored as `min_trading_days`.
Contracts mixable 1 mini = 10 micros; excess voided. Auto-flat 16:10 ET. Funded split 80%.

### Tradeify — Select (futures · EOD trailing drawdown)
- Select Evaluation accounts: https://help.tradeify.co/en/articles/12853921-select-evaluation-accounts
- Select Flex & daily payout policies (funded): https://help.tradeify.co/en/articles/12853966-select-flex-and-select-daily-payout-policies

Key points: EOD trailing MLL, no lock during eval. **40% consistency rule → minimum 3 trading days** (the 3 is
the mathematical floor of the 40% rule, which Tradeify states; not a separate published min-days field). Cannot
hold minis and micros at the same time. Funded contracts scale on a **cumulative ratchet** (retained once
reached). >10-second activity rule. Auto-flat 16:59 ET. Funded split 90%.

### Apex — EOD trailing (futures) — **eval rows only seeded**
- EOD Evaluations: https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/
- EOD drawdown explained: https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/
- Intraday trailing evals (reference — **NOT seeded**, a possible future addition): https://apextraderfunding.com/help-center/evaluation-accounts-ea/intraday-trailing-drawdown-evaluations/

Key points: Apex **4.0 (launched 2026-03-01) removed the legacy 7-day minimum** — EOD evals have **no minimum
trading days**; pass as soon as the target is hit. EOD trailing MLL locks at start + $3,000/$6,000 (50k/100k).
Apex carries an informational daily-loss reference (`daily_loss_cap` 1,000 / 1,500). Funded (PA) accounts are
**not yet seeded** — only the EOD eval. We seed EOD, not Intraday.

---

## KPI → DB column map (what the verifier edits)

All seeded values live in `rulesets` rows in `command-center/backend/data/lab.db`. The seed code is in
`backend/services/lab_db.py` (`_PROP_SEED_ROWS` + `_APEX_EOD_EVAL_ROWS`); edits to the seed reproduce on a
fresh DB, but **existing DBs keep their stored values** (seeding is idempotent per-id and never overwrites).

| KPI | Column | Notes |
|---|---|---|
| Account size | `account_size` | |
| Profit target | `profit_target` | `0` on funded (no target) |
| Drawdown type | `drawdown_type` | `trailing_eod` for every current row |
| Drawdown amount | `max_loss_eod` | the trailing EOD max-loss $ (the "MLL") |
| Drawdown lock point | `mll_lock_balance` | balance where the floor stops trailing; `NULL` = never / funded |
| Drawdown unit | `drawdown_unit` | `usd` |
| Consistency | `consistency_pct` + `consistency_breach_action` | `raise_target` = breach raises target instead of failing |
| Min trading days | `min_trading_days` | `NULL` = none published |
| Daily loss limit | `daily_loss_cap` | where a firm enforces one (mostly funded) |
| Contract limits + scaling | `max_contracts` (JSON) | `mini_max` / `micro_max` + `scaling` ladder (band or ratchet) |
| Funded split | `profit_split_pct` | |
| Auto-flat time | `force_flat_time_et` | |
| Doc links | `docs_url` + `reference_urls` (JSON array) | |

---

## Saved sync query

Don't rebuild this from scratch — it's saved as a runnable script:

```
backend/scripts/prop_kpi_audit.py
```

Run it (read-only, no deps beyond stdlib):

```bash
# markdown table of every prop ruleset's core KPIs
python3 command-center/backend/scripts/prop_kpi_audit.py

# raw JSON (one object per row) — easiest for diffing against this doc
python3 command-center/backend/scripts/prop_kpi_audit.py --json
```

The exact SQL it runs (also kept inline in the script as the `QUERY` constant):

```sql
SELECT id, name, ruleset_type, account_tier, account_size, profit_target,
       drawdown_type, max_loss_eod, mll_lock_balance, drawdown_unit,
       consistency_pct, consistency_breach_action, min_trading_days,
       daily_loss_cap, profit_split_pct, force_flat_time_et,
       max_contracts, docs_url, reference_urls
FROM rulesets
WHERE ruleset_type IN ('prop_eval', 'prop_funded')
ORDER BY id;
```

---

## Verification prompt (hand this to an agent that can run the query + fetch the links)

> Copy everything in the block below. The **DB-sync step needs Claude Code** (it runs the query); a
> browser-only Claude can still do the docs-verification half and report diffs against the snapshot above.

```
You are auditing our seeded prop-firm ruleset KPIs in command-center/docs/PROP_RULESET_KPIS.md
against the firms' live documentation AND against our ruleset engine. Do all of:

1. SYNC CHECK (ruleset engine = source of truth):
   Run:  python3 command-center/backend/scripts/prop_kpi_audit.py --json
   This dumps every prop ruleset (eval + funded) straight from lab.db. Treat its output as the
   current state of our engine. Confirm the "Snapshot" tables in the doc match it exactly. Flag any
   field where the doc and the DB disagree (the DB wins — fix the doc, not the DB).

2. DOC VERIFICATION (firms = source of truth for the rules themselves):
   Fetch each link below and verify, per challenge, these KPIs: account size, profit target,
   drawdown TYPE and AMOUNT (+ where the trailing floor locks), consistency % and what a breach does,
   MINIMUM TRADING DAYS, daily loss limit, contract base size + scaling rules, funded profit split,
   and daily auto-flat time. Verify eval AND funded for each firm.
   - Do NOT assume a minimum-trading-days value. If a firm publishes none, it must be "none" (NULL),
     not 1. If a minimum is only implied by a consistency rule (e.g. Tradeify's 40% → 3 days), say so
     explicitly and note it's derived, not a standalone published field.
   - Note any rule that has changed since the "Last verified" date at the top of the doc.

   Lucid (LucidFlex):
     https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account
     https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown
     https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage
     https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan
     https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account
   FundedNext (Futures Flex):
     https://helpfutures.fundednext.com/en/articles/14878751-what-is-fundednext-futures-flex-challenge
     https://helpfutures.fundednext.com/en/articles/14878830-how-do-i-pass-fundednext-futures-flex-challenge
   Tradeify (Select):
     https://help.tradeify.co/en/articles/12853921-select-evaluation-accounts
     https://help.tradeify.co/en/articles/12853966-select-flex-and-select-daily-payout-policies
   Apex (EOD trailing — we seed EOD eval only; Intraday is reference for a possible future add):
     https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/
     https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/
     https://apextraderfunding.com/help-center/evaluation-accounts-ea/intraday-trailing-drawdown-evaluations/

3. REPORT a per-firm diff with three buckets:
   (a) DB ≠ firm docs  — our engine value is wrong; give the correct value + the column to change
       (see the "KPI → DB column map" section) and the exact source URL.
   (b) doc ≠ DB  — the markdown snapshot is stale; update the doc tables to match the query output.
   (c) firm rule changed since last verification — call it out with the URL and date.
   If everything matches, say so plainly and bump the "Last verified against firm docs" date.

4. After making corrections, re-run the query to confirm doc and DB agree, and update the
   "Last verified" date at the top. Never edit lab.db values to match a firm without explicit
   sign-off — propose the seed/DB change, don't silently apply it.
```
