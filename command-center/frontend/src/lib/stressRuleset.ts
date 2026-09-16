/** The ruleset a FOREX stress test is graded against unless the reader picks another (Aaron,
 *  2026-09-16: "we should always default to the 55% one"). "Personal Forex — 55% Drawdown".
 *
 *  ⚠ The server applies the same default when a request names none — `DEFAULT_FOREX_RULESET_ID`
 *  in `backend/routers/stress_tests.py`. This copy only decides what the picker SHOWS first. */
export const DEFAULT_FOREX_RULESET_ID = 'personal_forex_risk'
