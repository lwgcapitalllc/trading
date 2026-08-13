Mandatory checklist before anything under `algos/live/`, `algos/shared/mt5_ops.py`, order sizing, or a deployed bot.

**Why this exists:** this is where mistakes cost money instead of time. Both incidents below
ran for hours on a green suite, and neither raised anything.

- **A 54.82-lot order on a $2,000 account — 221x the intended size.** Two faults multiplied.
  `Execution` sizes in OUNCES and the bridge handed that to MT5 as LOTS (gold is 100 oz/lot, so
  every order this bot ever placed was 100x). And the strategy was sizing off its emulator's
  compounded imaginary balance, ~$4,423 against a real $2,000. It rested eight hours looking
  perfectly healthy, and the broker deleted it at the fill.
- **The terminal switched accounts under a running bot.** It re-anchored position sizing from
  $1,992.21 to $9,996.99 — five times the money, off an account it had never been told about —
  and logged it as the ordinary event it looks like. `connect()`'s account check was correct,
  well-placed, and ran ONCE.

---

## Answer every question. Do not skip one because it looks unrelated.

### Units — rule 15

1. Does any value cross a system boundary here? (strategy → bridge → MT5, price → money,
   ounces → lots, R → dollars, broker clock → UTC)
2. For each: **what is its unit on each side, and which single line converts it?** Name the
   line. If no line owns the conversion, that is the defect — there is no place a reviewer
   could look to find it missing.
3. Is the conversion instrument-agnostic? Lots must come from the MONEY
   (`(stop_distance / tick_size) × tick_value`), so gold, a JPY pair and an index are one
   arithmetic and nothing is gold-shaped.

### Three states, never two — rule 1

4. Can any field here mean *no*, *zero*, and *could not ask*? List them.
5. Is "cannot ask" stored as `None` and read `is False` / `is None` — never falsy, never `0.0`?
6. Would writing a fabricated zero here be indistinguishable from a real measurement? (`deals: 0`
   from an unreachable terminal is not "charged nothing".)

### What re-checks, and what only checked once — rule 16

7. What facts does this path establish at STARTUP? (account, symbol, balance anchor, config hash)
8. **For each: what could move it afterwards, and who would notice?** A terminal can be relogged,
   a symbol unwatched, a config edited, a balance re-anchored.
9. If it can move, does something re-check it every poll — and does it HALT rather than adapt?
10. Is the identity read off the SAME call as the value it qualifies? (login and balance from one
    `account_info()`, not two.)

### Refusal — rule 17

11. What does this do when the broker says no? Does it log the RETCODE and the broker's own
    sentence, or does it log `last_error()` — which describes the API call, not the order, and
    says "Success" on a rejection?
12. Does anything round, clamp, or shrink to fit? It must not. Below minimum, above maximum and
    unaffordable all mean NO TRADE — a resized order is not the trade the emulator is holding,
    and the two drift apart silently.
13. Is there a causeless backstop? The margin check would have stopped the 54-lot order eight
    hours early on its own.

### Silence

14. What here fails by returning an ABSENCE rather than raising? (`None`, `[]`, an empty
    DataFrame, a missing file, zero deals)
15. For each: is that absence distinguishable from the healthy case? If a quiet market and a
    dead link produce the same value, it is not a probe.
16. Does every deliberate exit write a record? The absence of a shutdown record is only evidence
    of a hard kill if the ordinary endings all write one.

### Blast radius

17. Does this reach a bot that is RUNNING right now? Check first:
    `ssh forexvps "wmic process where \"name='python.exe'\" get commandline"`
18. Is the change reaching live code, or only the repo? A pull does not move a deployment —
    `promote.py` does. Say which you are doing.
19. Are the magic numbers still unique per account? Is the fleet halt reachable?
20. Would a watchdog restart undo, or re-apply, what you just did? Every recovery path here works
    by re-issuing a start, so a non-idempotent start is a duplicate generator.

### Then

21. Run the algos suite. Report the count.
22. Say plainly which of the 20 above you could NOT answer. An unanswered question is the finding.
