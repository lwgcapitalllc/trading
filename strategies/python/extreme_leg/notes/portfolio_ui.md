# Notes — Strategies page placement, account sharing, and display labels

Why this bot is a top-level row rather than nested under SOS Fade, how it was wired to share a portfolio account, its XLEG chart tag, and the short display names given to its minute settings. Moved VERBATIM out of `strategies/python/extreme_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## It is a TOP-LEVEL row on the Strategies page, not a child of the SOS Fade bot (2026-09-02)

**Aaron's call, and the reasoning is worth keeping because the version it replaced was not wrong.**
This package declared `display_under: "sos_fade"` until today, on the grounds that the suite is
carved up by LEG off one structure stream and this is the leg BEFORE the one SOS Fade trades. That is
still true. It is still the wrong thing to draw as an indent.

🔴 **AN INDENT READS AS "CHILD OF", AND THIS BOT IS A SIBLING.** It has its own Pine source, its own
parity gate, its own config, and it runs standalone, in any stack, on any instrument. Measured over
6.6 years it holds ZERO same-side overlap with SOS Fade, correlates −0.038 month to month, and on one
shared account the two refuse each other essentially never.

🔴 **What made it misread is that ONE VISUAL LEVEL WAS CARRYING TWO RELATIONSHIPS.** `loss_recovery`
sits under SOS Fade as well and genuinely cannot run without it — it arms off that bot's closed losses and
declares `requires_source`, so the page refuses to run it alone. A row that cannot exist without its
parent and a row that competes with it as an equal were drawn identically, and nothing on screen
separated them.

⚠ **Do not re-add the field without recording why.** Its failure mode is silent in BOTH directions —
a dropped declaration and a typo'd parent both render at the top level, so reversing this decision by
accident would show up nowhere. `command-center/backend/tests/test_strategy_nesting.py` pins it, and
a second check pins that the move took nothing else away (the row must still be standalone-runnable).
Both watched RED by mutation.

⚠ **B-LEG still nests, and that was NOT changed here.** Only the row Aaron asked about moved.
Whether the same argument applies to it is an open question, not something this change decided.

---

## It can share an account now (2026-09-02)

**`backtest/portfolio/run_stack` REFUSED this bot outright until today**, and the refusal was the
right one: its execution layer owned a private balance and entered whenever its own ladder said
yes, so replaying it as a leg would have given it an uncapped account **while the run reported the
risk budget enforced.** Nothing would have raised. The seam is now the same one `sos_fade` has
— `account=None, leg="strat"`, defaulting to an uncapped solo account.

⚠ **Solo behaviour is unchanged and that was PROVEN, not reasoned.** The parity gate was re-run on
the same export after the wiring: still green on all 20,327 compared bars, so not one decision
moved. Every 6.6-year figure in this file still describes the same strategy.

**Five points carry the seam, and each one fails silently if it is dropped:**

| | what it does | what breaking it looks like |
|---|---|---|
| the balance is a PROPERTY, never a stored number | solo → own ledger; stacked → the shared one | solo run fine, every stacked run quietly sizes off a stale balance |
| the entry asks before it opens | the account scales the size down to the room | the position appears, the cap is breached, nothing reports it |
| breakeven reports the new stop | risk is reserved to the CURRENT stop, so the room comes back | the cap binds on risk nobody carries and the other leg is refused affordable entries |
| close books P&L **and** frees the reservation | two calls, because money and budget are separate | balance right, budget permanently spent, the account slowly grants nothing |
| it can say whether it is flat | the simulator steps a holding leg FIRST, so closing frees room before the other is sized | room that just came free is silently denied |

🔴 **AN ACCOUNT REFUSAL IS DELIBERATELY NOT A REFUSAL CODE.** Those codes are the decision stream
the parity gate compares against the chart, and a portfolio refusal is a decision made ABOUT this
strategy rather than BY it. Writing one there would put a Pine-less value in the one stream that
has to stay comparable, and the gate would then report a divergence at a real bar and send the
reader hunting a porting bug that does not exist. The account's own contention log is where a stack
reader looks — it timestamps every refusal and every shrink.

⚠ **8 mutations watched RED, each on exactly its own test** (the balance one reddens two, correctly
— solo and stacked). A stub account that granted whatever it was asked would have passed all ten
tests while describing an account nobody has, so they are written against the real
`PortfolioAccount`.

### What it does stacked against the live SOS Fade bot — MEASURED 2026-09-02

470,995 PU Prime `XAUUSD.p` M5 bars + 157,004 M15, one $10,000 account, 10% cap.
**At a matched 5% per trade each: +190.30R together, and every leg posts the SAME R shared as solo
— zero contention, not one decision moved.** At the two configs' own defaults (10% and 1%) it is
+191.30R with the budget binding twice in 6.6 years.

🔴 **READ THE RISK COLUMN BEFORE THE R COLUMN. The first mixed stack ran SOS Fade at 10% against this bot
at 1% — a 10:1 gap that came from each config's default and that the tool printed NOWHERE.** The
bigger leg then fills the budget alone and the smaller one reads as harmless, which is a fact about
the SETTINGS and not about the strategies. `stack_run.py` prints per-leg risk now and `--risk-pct`
matches them. 🔴 **THE PLACEHOLDER IS GONE: `exec_risk_pct` is 5.0 as of 2026-09-02, Aaron's
explicit call.** This line read *"1.0 is a placeholder, not a measurement — nothing here has chosen
it"*, and now something has.

⚠ **What that change moves, and what it does not — CHECKED against the code path rather than
assumed.** `_qty` scales the lot and the only size refusal beside it tests finite-and-positive, so
**solo it cannot change a single decision**: every trade count and every R figure in this file
stands, and so does the clash audit, which replays each bot off its OWN equity. **Every STACKED
figure moves**, because a shared account grants `granted` rather than `qty`. ⚠ **At the two
defaults the mixed stack is 5% + 5% against a 10% cap since 2026-09-13**, when SOS Fade's default
moved 10 → 5 — the basis the "zero contention" row was measured on, which saturates that cap
exactly. For eleven days before that it was 10 + 5, which does not fit at all.
⚠ **The parity gate is unaffected and that was checked, not reasoned**:
`compare_extreme_leg.config_from_export` builds the port's config from the export's own `cfg_*`
columns and never reads this side's defaults.

⚠ **Two legs at 5% each SATURATE a 10% cap exactly**, so "no contention" above sits on a knife
edge rather than describing headroom. Anything higher and they start refusing each other.

⚠ **A shrunk entry is INVISIBLE IN R.** R is measured against each trade's own risk, so a trade cut
to half size reports the same R — the SOS Fade leg's shared and solo R are identical despite being
shrunk once. This repo's standing rule is to compare R rather than dollars, and this is the one
place R cannot see what the cap did. Read the contention log for that.

⚠ **The SOS Fade leg in ANY stack is not the live SOS Fade**: its 1-minute re-entry is pinned off, because a
leg is one bar frame. Its figures here sit below the live bot's by construction.

---

## Its chips say XLEG, not SOS Fade (2026-09-02)

`LAB_STRATEGY["chart_tag"]`. 🔴 **The price chart hard-coded `SOS Fade` — the SOS Fade bot's own word for ITS
setup — onto every strategy's primary trades**, so this bot's trades wore a label belonging to a
different bot. The panel's own comment had named the cost and the fix since it was written; this is
that fix. ⚠ **A LABEL and nothing else** — no run, no cost and no decision reads it, so changing it
repaints chips and moves no trade. ⚠ **Keep it SHORT**: it is drawn in a chip beside the entry price
and a long word pushes the price off the marker. ⚠ **Undeclared is still `SOS Fade`**, because a package
that has not declared one must not lose its chip entirely — so a chart reading `SOS Fade` now means
EITHER the SOS Fade bot or a strategy that has yet to declare its own word.

---

## Two minute settings carry a SHORT name (2026-09-13)

`swept_minutes` and `extreme_minutes` gained `short` (*Swept within*, *Extreme lookback*) in
`extreme_leg.meta.json`. Without one the finished-run panel prints the `label`, and a label ending
*(minutes)* beside a value reading *180 min* says the unit twice. ⚠ **The labels did not move**:
each is the Pine input's title word for word (`strategies/tradingview/tools/build_extreme_leg.py`),
and Pine has no other place to show a unit. ⚠ Display keys only — no setting, default or decision
changed, so no gate is owed.
