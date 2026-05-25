# Smart Money Replication System — Full Execution Steps for Claude Code

---

## Objective
Build a scanner, profiler, and ranking system that identifies the most consistent crypto and forex traders across Hyperliquid, Solana, Ethereum, and Myfxbook/FX Blue. Output is a ranked, profiled candidate pool report. No trading. Research and discovery only.

---

## Technical Requirements

- **Language:** Python preferred for data pipeline and API calls
- **Storage:** Local SQLite database or structured JSON files for all raw and processed data
- **Libraries needed:** requests, pandas, numpy, sqlite3, json, datetime
- **API rate limiting:** Build in rate limit handling and retry logic for all API calls
- **Error handling:** Log all API failures, data gaps, and anomalies without stopping the pipeline
- **Modularity:** Each stage and step should be a separate callable module so any stage can be rerun independently
- **Config file:** All thresholds (80% win rate, 20% drawdown, 100 trades, 90 days) stored in a single config file so they can be adjusted without touching the code
- **Logging:** Full run log generated every time pipeline executes showing how many wallets passed and failed each filter at every step

---

## Qualification Criteria (Global — Applies to All Sources)

A wallet or account must meet **all** of the following to enter the candidate pool:

- 100+ trades within the lookback period
- ≥ 80% win rate measured month over month — not aggregate
- Win rate must hold across every 30-day window in the period
- No single trade > 40% of total PnL
- Active across at least 3 separate weeks per month
- Peak drawdown never exceeds 20% across the full period
- Minimum account/wallet age of 90 days

**Strike system:**
- 1 month below 80% → yellow flag, still studied but noted
- 2 consecutive months below 80% → disqualified
- Returns to 80%+ for 2 consecutive months → reinstated

---

## Lookback Period Structure

| Tier | Lookback | Purpose |
|---|---|---|
| Minimum qualification | 90 days | Must pass to enter candidate pool |
| Preferred | 180 days | Must maintain consistency to reach top 20 |
| Elite designation | 365 days | Bonus weight in ranking — proven across full market cycle |

Win rate must hold ≥ 80% in each 30-day window across whichever tier the wallet qualifies for — not just the overall average.

---

## Scoring Model (1–100 Composite Score)

| Factor | Weight | What It Measures |
|---|---|---|
| Month over month win rate consistency | 25% | Does 80%+ hold every single month |
| Risk-adjusted return | 25% | PnL relative to drawdown taken |
| Exit efficiency | 20% | Do they exit before full reversals |
| Trade frequency | 15% | Enough signals to be useful for copying |
| Instrument and day consistency | 15% | Do they have a repeatable pattern |

---

## Stage 1 — Hyperliquid Scanner & Profiler

### Step 1.1 — Connect to Hyperliquid API
- Connect to Hyperliquid public REST API
- No API key required — fully public
- Base URL: `https://api.hyperliquid.xyz`
- Confirm endpoints for leaderboard, trade history, and account data

### Step 1.2 — Pull Leaderboard
- Fetch full public leaderboard
- Extract wallet addresses, total PnL, trade count, account age
- Filter immediately for wallets with 100+ trades
- Filter for wallet age ≥ 90 days
- Store raw results in local database or structured JSON

### Step 1.3 — Pull Trade History Per Wallet
- For each wallet passing Step 1.2 filters pull full trade history
- Extract per trade: entry price, exit price, size, instrument, timestamp, PnL, win or loss
- Calculate starting balance and ending balance across each lookback window
- Calculate peak balance and lowest balance during each window
- Store per wallet trade log

### Step 1.4 — Calculate Monthly Win Rate
- Segment each wallet's trade history into 30-day windows
- Calculate win rate for each 30-day window separately
- Flag any wallet with a window below 80% — apply strike system
- Only wallets with ≥ 80% in every window proceed

### Step 1.5 — Apply Disqualification Filters
- Remove any wallet where a single trade accounts for > 40% of total PnL
- Remove any wallet trading fewer than 3 separate weeks per month
- Remove any wallet with peak drawdown exceeding 20%
- Remove any wallet with average hold time exceeding 72 hours
- Remove any wallet whose PnL is concentrated in one instrument only
- Log reason for every disqualification

### Step 1.6 — Score Each Qualifying Wallet
- Apply composite scoring model above
- Calculate composite score and rank all qualifying wallets

### Step 1.7 — Build Wallet Intelligence Report
For each wallet in the top 20 generate a full profile containing:

**Balance & Growth Metrics:**
- Starting balance at the beginning of the lookback period
- Ending balance at the end of the lookback period
- Net growth % across the full period
- Peak balance during the period
- Lowest balance during the period
- Month over month balance progression

**Performance Metrics:**
- Average win size vs average loss size
- Average risk/reward ratio per trade
- Average drawdown per trade and peak drawdown
- Month over month win % trend — improving, stable, or declining

**Behavioral Patterns:**
- Preferred trading days ranked by frequency
- Preferred instruments ranked by frequency and win rate
- Typical entry time of day
- Average hold time per trade
- Exit efficiency score

### Step 1.8 — Output Stage 1 Results
- Export top 20 wallet profiles to structured report (JSON + CSV)
- Flag top 5 candidates with highest composite scores
- Log all disqualified wallets with reasons for future reference
- Validate results manually before proceeding to Stage 2

---

## Stage 2 — Validate & Calibrate

### Step 2.1 — Review Stage 1 Output
- Check how many wallets qualified
- If pool is too thin (fewer than 20) consider relaxing 80% threshold to 75% and rerun
- If pool is too large (more than 100) tighten drawdown filter to 15% and rerun
- Document any threshold adjustments made

### Step 2.2 — Spot Check Top 5 Wallets Manually
- Pull raw trade logs for top 5 wallets
- Manually verify win rate calculations are correct
- Verify starting and ending balances are accurate
- Verify no data gaps or anomalies in trade history
- Confirm composite scores reflect actual performance

### Step 2.3 — Calibrate Scoring Weights if Needed
- Review if any scoring factor is producing unexpected rankings
- Adjust weights if necessary and document changes
- Rerun scoring with adjusted weights if changed
- Lock in final scoring model before Stage 3

---

## Stage 3 — Expand to Solana & Ethereum On-Chain

### Step 3.1 — Connect to Dune Analytics
- Set up Dune Analytics free account
- Use existing public queries for Drift Protocol, Mango Markets, GMX, dYdX wallet PnL
- Extract wallet addresses, trade counts, PnL history
- Apply same 100+ trade and 90-day age filters immediately

### Step 3.2 — Connect to Flipside Crypto
- Set up Flipside free account
- Query Solana and Ethereum DEX trade histories
- Focus on Drift Protocol (Solana), GMX (Ethereum), dYdX (Ethereum)
- Extract same data fields as Hyperliquid — entry, exit, size, instrument, timestamp, PnL

### Step 3.3 — Connect to Birdeye API (Solana)
- Set up Birdeye free API key
- Pull Solana wallet trade histories for wallets surfaced in Step 3.1
- Cross-reference with Flipside data for same wallets
- Fill any data gaps between sources

### Step 3.4 — Connect to DeBank / Zerion (Ethereum)
- Set up DeBank or Zerion free API access
- Pull Ethereum wallet PnL snapshots and trade history
- Cross-reference with Dune and Flipside data for same wallets
- Resolve any discrepancies between sources

### Step 3.5 — Apply Full Qualification Criteria
- Run all Solana and Ethereum wallets through same Steps 1.4 and 1.5 filters
- Monthly win rate ≥ 80% in every window
- All disqualification filters applied identically
- Strike system applied identically

### Step 3.6 — Score and Profile Solana & Ethereum Wallets
- Apply same 1–100 composite scoring
- Build full intelligence reports for top wallets
- Export to same structured format as Stage 1

### Step 3.7 — Merge Crypto Candidate Pool
- Combine Hyperliquid, Solana, and Ethereum qualifying wallets into one unified pool
- Re-rank all wallets together by composite score
- Select overall top 20 crypto wallets
- Flag overall top 10 crypto candidates

---

## Stage 4 — Forex Expansion via Myfxbook & FX Blue

### Step 4.1 — Connect to Myfxbook API
- Set up free Myfxbook developer account
- Authenticate with API credentials
- Pull list of public verified accounts
- Filter for accounts with 100+ trades and 90+ days history

### Step 4.2 — Pull Myfxbook Account Data
For each qualifying account extract:
- Starting and ending balance
- Monthly win rate per 30-day window
- Average win and loss sizes
- Drawdown history
- Preferred pairs and trading sessions
- Trade frequency and hold times

### Step 4.3 — Connect to FX Blue
- Set up FX Blue free account access
- Pull verified public account performance data
- Extract same fields as Step 4.2

### Step 4.4 — Cross-Reference Forex Accounts
- Identify any accounts appearing on both Myfxbook and FX Blue
- Accounts on both platforms get survivorship bias flag removed
- Accounts on only one platform keep survivorship bias flag
- Weight double-verified accounts higher in scoring

### Step 4.5 — Apply Full Qualification Criteria to Forex
- Run all forex accounts through same monthly win rate and disqualification filters
- Additional forex-specific disqualification rules:
  - Accounts created within 6 months of best performance window — disqualify
  - Accounts appearing on only one platform — yellow flag, not disqualified
- Apply strike system identically

### Step 4.6 — Score and Profile Forex Accounts
- Apply same 1–100 composite scoring
- Add forex-specific behavioral fields to intelligence report:
  - Preferred session — London, New York, Asian
  - Preferred pairs ranked by frequency and win rate
- Build full intelligence reports for top forex accounts

### Step 4.7 — Output Forex Results
- Export top 10 forex account profiles
- Flag top 5 forex candidates
- Merge into unified candidate pool alongside crypto wallets

---

## Stage 5 — Unified Candidate Pool & Final Report

### Step 5.1 — Merge All Sources Into One Pool
- Combine top crypto wallets and top forex accounts into single unified pool
- Apply market transparency weighting:
  - Crypto wallets weighted higher due to forced blockchain transparency
  - Forex accounts weighted slightly lower due to opt-in survivorship bias risk
- Re-rank entire unified pool by adjusted composite score

### Step 5.2 — Generate Final Candidate Pool Report
Produce a structured report containing:

**Summary Section:**
- Total wallets and accounts scanned
- Total qualifying candidates
- Breakdown by market and source

**Top 20 Unified Rankings:**
- Rank, wallet/account ID, market, source, composite score
- Starting balance, ending balance, net growth %
- Peak and lowest balance
- Overall win rate and month over month consistency rating
- Average win/loss, average RR, peak drawdown
- Preferred instruments and days summary

**Full Intelligence Report Per Candidate:**
- Complete behavioral and performance profile
- All balance and performance metrics
- Strike flags and any yellow flags noted

**Final Shortlist:**
- Top 5 overall candidates across both markets
- Ranked with reasoning for each selection
- Noted strengths and any flagged concerns per candidate

**Market Breakdown:**
- Top 10 crypto wallets
- Top 10 forex accounts
- Overall top 5 across both markets combined

### Step 5.3 — Export All Outputs
- Full report exported as JSON
- Full report exported as CSV
- Summary report exported as readable markdown or PDF
- All disqualified candidates logged separately with disqualification reasons
- All raw data retained for future reference and recalibration

---

## Free Data Sources Summary

| Tool | Market | Purpose |
|---|---|---|
| Hyperliquid API | Crypto | Live leaderboard + full trade history |
| Dune Analytics | Crypto | On-chain SQL queries across wallets |
| Flipside Crypto | Crypto | Historical trade data + PnL queries |
| Birdeye API | Crypto/Solana | Wallet + token trade history |
| DeBank / Zerion | Crypto/Ethereum | Wallet PnL snapshots and history |
| Whale Alert | Crypto | Large movement detection and flagging |
| Myfxbook API | Forex | Verified account performance data |
| FX Blue | Forex | Cross-reference verified forex accounts |

---

## Build Sequence Summary

| Stage | Action |
|---|---|
| Stage 1 | Build Hyperliquid scanner and profiler |
| Stage 2 | Validate criteria and scoring on first results |
| Stage 3 | Expand to Solana and Ethereum on-chain |
| Stage 4 | Layer in Myfxbook and FX Blue for forex |
| Stage 5 | Consolidate into unified ranked candidate pool and deliver final report |

---

## Important Notes for Claude Code

- No trading or execution of any kind — this is research and discovery only
- All thresholds stored in config file and adjustable without touching core code
- Each stage must be independently rerunnable
- If Stage 1 returns fewer than 20 qualifying wallets adjust the 80% threshold to 75% in config and rerun before escalating
- Crypto candidates weighted higher than forex in final unified ranking due to blockchain transparency advantage
- Survivorship bias in forex must be actively managed through dual-platform cross-referencing
- All disqualified candidates must be logged with reasons — never silently dropped
