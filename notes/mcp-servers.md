# Notes — The three servers Claude drives instead of a shell

The browser, trading-box and lab servers: what each refuses on purpose, and the checks that prove it. Moved VERBATIM out of `CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The MCP servers — what Claude is handed instead of a shell

**Added 2026-08-20/21.** `.mcp.json` at the repo root wires up three servers, so they arrive
with a clone and behave the same on both machines. Each of us approves them once, on the first
session after pulling. Full build story, measurements and one fix that was backed out:
`HISTORY.md` → *The MCP servers arrive*.

| Server | What it is for |
|---|---|
| **browser** | Opens the Command Center in a real browser — the answer to rules 7 and 9, which are about features nobody ever RAN |
| **tradingbox** | Seven named trading-box operations instead of an open SSH prompt |
| **lab** | Backtests, and a comparison that refuses when the two runs were not measured the same way |

**The one idea behind all three: a rule that lives in somebody's memory is a rule that gets
broken on a Friday.** Each server moves a rule this repo keeps re-learning into something that
cannot be talked out of it.

🔴 **browser — the page can be clicked, and the live buttons cannot.** The backend talks to the
trading box, so a click is a real action. `.claude/mcp/browser_guard.js` is injected ahead of
the app's own scripts and rejects bot start/stop/restart, promote (and, since 2026-09-10, the
same deploy started as a background job — `POST …/promote/job`), strategy deploy and delete,
account writes, moving bots onto another account or demo → live (added 2026-09-10 — the go-live
write had shipped three days earlier with no rule here), risk writes — a bot's risk per trade and an
account's cap or budget (added 2026-09-11; the budget PLAN stays allowed) — and agent starts INSIDE
the browser; they never reach the backend. Promote
PREVIEW and every lab write stay allowed — those cost compute, never money, and a guard that
blocks the useful half gets switched off. ✅ **A missing guard file makes the server refuse to
start**, so there is no unguarded state. ⚠ **Not a security boundary** — it makes an accident
impossible, not an attack. ⚠ **It runs headless, which MEASURED costs nothing** except being
able to watch. ⚠ **Google's font hosts are allowed deliberately**: blocked, the page still
rendered and screenshotted happily in the wrong typeface with one console error as the only
sign, and a screenshot that looks plausible and is subtly wrong is worse than one that fails.

🔴 **tradingbox — the point is what is ABSENT.** No hard kill, no fleet kill, no lock deletion,
no account edit, no password change, no user management, no agent start, no restart.
`taskkill /f /im python.exe` killed the live bot for three days; it is not on the menu, so a
typo or a bad quote cannot reach it. ⚠ **The two writes take a phrase naming the bot and the
action** — a speed bump against a slip, not a wall against intent, and it refuses *before* the
network. ⚠ **Every reply says whether the question was ASKED**: unreachable returns no payload,
never a `running: false`. That is rule 1.

🔴 **lab — the comparison refuses when the basis differs.** Rule 11 has been broken four times
in this app, always the same way: the difference column becomes the thing that lies. Window,
timeframe, instrument, costs, broker, sizing — if any of them moved, the tool refuses and names
the field. ⚠ **The basis is READ OFF the request contract, not chosen** — `check_lab.py` parses
`BacktestRunRequest` out of this repo, so adding an input to a run turns red until somebody
decides whether it changes what the run is measured on. ✅ **It caught a real one on
2026-08-25**: a run input that OVERWRITES a basis field is request-time, not basis, and a tool
handing over the resolved field must PIN it or the lab re-resolves it and a copied basis is
silently measured differently. Story: `HISTORY.md` → *The switch that overwrote the basis*. ⚠ **Net dollars are reported under the
unit-free numbers, never above** (rule 6), and the breakeven-scratch count always travels with
the win rate. ✅ **The VENUE LOT CEILING joined the basis on 2026-09-03, and it is the case that
shows why the check is read off the contract rather than curated by hand: R is IDENTICAL either
side of a ceiling** — profit and risk both scale with the quantity — **so every instinct says it
cannot matter, while balance, drawdown and CAGR all move.** MEASURED on the live SOS Fade bot over 6.6
years: same 205 trades, same +107.36R, closing balance $11,528,822 uncapped against $10,752,175 at
100 lots. Nobody would have added it from memory.

⚠ **All three are FRONT DOORS onto the Command Center backend, never second implementations** —
so the app must be running, and each says so plainly when it is not. The one exception is the
trading box's ledger tool, which reads committed files and keeps working regardless.

⚠ **The MCP wire is hand-rolled on the standard library**, because the official SDK needs Python
3.10 and every interpreter here is 3.9.6. Adding a tool must not mean adding a runtime.

**Prove them rather than trusting them** — they are steps 4, 5 and 7 of `scripts/run_all_tests.sh`,
and every one was watched RED by mutation:

```
node   .claude/mcp/check_browser_guard.js
python3 .claude/mcp/check_tradingbox.py
python3 .claude/mcp/check_lab.py
```

🔴 **BOTH PROMOTE TOOLS ON THE TRADING BOX HAD NEVER WORKED, and the check passed the whole
time (2026-08-26).** They POSTed with no body to an endpoint whose body is required, so the
Command Center answered HTTP 422 every single call. `check_tradingbox.py` was green because
every case it had asserted what a tool REFUSES, or how it reports a dead backend — **and a tool
that always fails passes both of those beautifully. A check that only tests the sad paths
certifies a tool with no working happy path.** It now records the request and asserts the body,
field by field. ⚠ **The Command Center's own button was never affected** — it sends
`{pull, restart}` and was verified end to end the same day. ⚠ **The MCP sends `restart: false`
on purpose**: this server's whole design is what it does NOT offer, so a promote from here moves
the code and stops, and a human restarts the bot.

⚠ **When a new route touches money or the live box, it goes in the browser guard and the trading
box in the SAME change.** Both are deny-lists by design — a route they have never heard of is
allowed. That is the honest trade for not blocking the lab, and it is the part that goes stale.
