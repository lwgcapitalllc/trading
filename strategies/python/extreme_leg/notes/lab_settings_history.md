# Notes — A lab setting that was probed but never read

The 2026-09-07 fix that gave the fixed-quantity setting a show_if so the lab's stress tester stops wasting replays on a setting this bot never reads. Moved VERBATIM out of `strategies/python/extreme_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

### 🔴 The fixed-quantity setting had no `show_if`, so the lab kept probing a setting it never reads (2026-09-07)

This bot sizes by `size_mode`, and `execution.py` reads `fixed_qty` in exactly one branch —
`if cfg.size_mode == "Fixed contracts" or risk <= 0`. Its schema entry SAID so, in prose:
*"Ignored otherwise."* **A sentence is not something the lab can read.**

🔴 **So the stress test's sensitivity phase spent 4 whole-stack replays — about 14 minutes —
nudging a number the strategy never looks at, and reported it as ROCK SOLID.** That is the worst
possible answer: not a wasted quarter hour, a *false reassurance* about a setting that cannot move
anything. It is the precise failure `param_is_reachable` exists to prevent, and it slipped through
because the setting is numeric, present and not foundational — technically live, actually inert.

✅ Fixed with `"show_if": {"size_mode": "Fixed contracts"}` in `extreme_leg.meta.json`, which is
the same mechanism `sos_fade` already uses **67 times**. This bot had **two**. ⚠ **That gap is the
thing to act on, not this one entry** — a bot whose conditions are mostly unwritten will keep
donating replays to settings nobody reads.

✅ **MEASURED after the fix**: the setting leaves the probe list, skipped rises 20 → 27, and the
freed budget goes to a real setting (`sos_fade.exec_trail_pct`) that had previously never been
reached at all. ⚠ **It did NOT make the phase faster** — the budget is a cap and there were nine
settings queued behind it. It made those four replays MEAN something.

⚠ **The strict claim is narrower than "never read", and say it that way**: the `or risk <= 0`
fallback means `fixed_qty` IS read when risk sizing yields nothing. With `exec_risk_pct = 5` that
cannot happen, so it is unreachable in practice — not by construction.

⚠ **The lab reads its stored copy, not this file.** The condition changes nothing until the
strategy is rescanned; a scan reported `updated: 1` and only then did the probe list move.
