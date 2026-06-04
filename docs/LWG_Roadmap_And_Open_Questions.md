# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-04

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

1. **Finish Pass 2.5 — E2E test** (platform task, nearly complete)
   Doc and code cleanup is done. One remaining step: E2E test — click Deploy on each of the three strategies from `/strategies`, click Compile All, run a small backtest with each to confirm the full one-click deploy flow works end-to-end.

2. **Strategy improvements pass — ORB first** (strategy task)
   ORB is the primary strategy. All 13 baseline runs are Tier 3. The improvement pass adds: regime filter (only trade in TRENDING/TRANSITIONING), trailing stop (move SL to breakeven after 1R), daily P&L circuit breaker (stop trading after hitting a daily target), optional re-entry logic. Goal is to reach Tier 1 on at least MES or MNQ. This pass was explicitly deferred during Pass 2 and Pass 2.5.

3. **First Tier 1 run → stress test** (strategy task)
   Once any ORB variant reaches Tier 1, the MC stress test auto-triggers. Walk-forward and sensitivity are manual. Goal: grade A or B (A = funded-ready, B = eval-purchase-ready).

4. **Expand rulesets** (platform task, lower priority)
   Apex Trader Funding is not yet seeded. FundedNext and Tradeify rules need periodic verification against their published docs (rules drift). A prop firm rules audit prompt exists at `docs/audit/PROP_FIRM_RULES_AUDIT_PROMPT.md`.

---

## Future platform milestones (in order, not yet started)

### M5 — Live strategy deployment and execution (future)
Wire NT8 live trading to the command center. Monitor active positions and daily P&L in real time via the Bots page. Risk cap deployment for NT8 (similar to MT5 bot caps). Prerequisites: at least one strategy grading B+ on stress tests against the target firm's rules.

### M6 — Multi-account management (future)
Track multiple simultaneous eval accounts (e.g. three LucidFlex $50k evals running in parallel on different NT8 accounts). Aggregate daily P&L view. Per-account status and reset history. Prerequisites: at least one passing eval to establish the workflow.

### M7 — MT5 strategy integration (future)
Extend the `strategies/mt5/` placeholder into a real subsystem. The runner dispatcher in `vps_client.py` already has a `NotImplementedError` stub for `"mt5"`. Strategy deployment would upload `.ex5` files to MT5's `Experts/` folder instead of NT8's strategy folder. The Deployed tab's platform filter (All / NT8 / MT5) is already built and will show MT5 files automatically once the data source is wired.

---

## Smaller items raised but deferred

- **NT8 auto-start after VPS reboot.** NT8 and the Strategy Analyzer need a scheduled task so strategies resume without manual RDP. Documented at `memory/project_nt8_autostart.md`. Not blocking anything today but will matter once live.

- **Apex Trader Funding ruleset seeding.** Apex is a major prop firm not yet in the DB. Needs rules research and a seeded row before any Apex evaluation can run.

- **Hash-based sync detection.** Current sync-status only checks file presence on VPS, not content. A future improvement would compare MD5 of the local `.cs` file against the VPS copy to detect drift after edits. The `source_hash` field already exists in the strategies DB table.

- **Instrument-specific regime thresholds.** The classifier uses ADX/ATR/RSI thresholds tuned for XAUUSD on H1/H4. NAS100, bonds, and other instruments may need different values. Noted in `regime/REGIME_CLASSIFIER.md` as a future improvement.

- **Regime persistence filter.** Prevent rapid label flips by requiring two consecutive identical classifications before committing a change. Mentioned in regime docs as a future enhancement.

- **`tradovate/` strategy placeholder.** Created as a gitkeep in Pass 2.5. No plan to use it in the near term.

- **Smart Money pipeline Stages 3–4.** The smart-money subsystem needs API keys to run stages 3 and 4. Stages 1, 2, and 5 are live. Not a priority while the prop firm path is the focus.

---

## Parallel tracks Aaron is running separately

- **Prop firm research workshop** (separate Claude.ai chat). Researching and comparing LucidFlex, Apex, Tradeify, and FundedNext rules, pricing, and payout structures. Output feeds into which rulesets to prioritize and which account sizes to target first.

---

## Open architectural questions

**Deploy endpoint is synchronous — is that OK long-term?** The `POST /strategies/{id}/deploy` handler reads the file, uploads to VPS, and returns 202 with the completed result before the response goes back to the client. This works because the upload is fast (~1-2s over the SSH tunnel). If NT8 file locking or a slow VPS ever makes uploads take longer, this should be moved to a true background task. For now it's fine — the job_id polling pattern is wired up on both ends so the switch is easy later.

**Scanner discovers all `.cs` files in `strategies/` recursively.** If MT5 ever adds `.cs` files (unlikely — MT5 uses MQL5/`.mq5`), the scanner would try to parse them as NinjaScript and skip them on the class regex check. Not a problem in practice but worth knowing.

**Compiler success detection via DLL mtime is fragile if NT8 has a background activity** that rewrites `NinjaTrader.Custom.dll` for other reasons. In 10+ compile runs this has not been an issue, but it's not a guaranteed-correct signal. A more robust approach would parse the NT8 output window for error/success text — not implemented.

**NT8 SA lock is in-memory only (lab_progress.json + DB status).** If the backend restarts mid-run, the lock can be stale. The startup hook resets stale locks automatically, but a run that was genuinely active when the backend died will show as abandoned. The Stop button (which resets the lock manually) and the startup hook reset handle the practical cases.

---

## Communication rules for new chats

(Repeated here so a chat that only received this document gets the rules.)

- Plain English replies. No code blocks unless explicitly asked.
- One clear question with concrete options when input is needed.
- Stop and report after each numbered step in any build spec.
- Smallest viable change first — no speculative abstractions, no premature cleanup.
- Update CLAUDE.md files in the same session as the changes that made them stale.
- No comments in code explaining what it does — only non-obvious constraints or invariants.
