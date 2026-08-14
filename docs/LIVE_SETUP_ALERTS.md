# Live Setup Alerts — a signals channel that says WHY, before the outcome is known

**Purpose:** The build plan for Telegram alerts that announce a setup while it is still forming —
the confluences a strategy has so far, where it would enter, where the stop would sit — and then
report what became of it, including the setups that never became trades.
**Scope:** The alert layer only: a contract strategies fill in, and the routing/formatting that
reads it. It does NOT change strategy logic, engines, the order bridge, or the backtest lab.
**Nothing here may move a trade decision.**
**Status:** SPEC — rewritten 2026-08-13 around a STRATEGY-AGNOSTIC contract at Aaron's request.
The 2026-08-03 version specced this for the A+ bot alone and is superseded; what it measured is
kept below, corrected.
**Created:** 2026-08-03. **Rewritten:** 2026-08-13.
**Parent:** `docs/LIVE_TRADING_PIPELINE.md` — this extends its step 7 (Telegram alerts), which
today specifies entry and exit only.

---

## 1. What Aaron asked for

**2026-08-03:** *"a template of saying potential trade — here are the confluences, here is possible
entry with SL, that way when we enter a trade we know why. Also it will say if a trade was spiked
after a while… if a trade left us and we did not get in for some reason."*

**2026-08-13, and this is the part that changed the design:** *"this should work generically for
any strategy; so it should know how to identify the confluences needed to signal a strategy and
tell me when one is upcoming"* and *"any bot I create … this should be scalable"*.

Plus the earlier framing: alert at **2 of 3** — a sweep and a shift of structure are in, and the
setup is now waiting on a retracement — not at the moment an order is placed. The channel is a new
Telegram group, **LWG Capital Signals**.

**Decisions taken 2026-08-13:**

| Question | Answer |
|---|---|
| Re-announce when the planned entry price moves mid-setup | **No.** One message per setup; the fill message carries the real price |
| Send setups one of your own rules refused | **Yes** |
| Which bots | Any bot, present or future — hence the contract |

---

## 2. What "generic" can and cannot mean

**The alert layer cannot work out a strategy's confluences by itself.** That knowledge lives inside
each strategy; a layer that inferred it would be inventing setups. What it CAN do is define one
contract that every strategy fills in, and never know which strategy it is talking to.

So each strategy answers one question — *what am I watching right now?* — and the answer is a list
of `SetupSnapshot`s (§4). "2 of 3" stops being hardcoded and becomes `len(met) of len(confluences)`,
so a four-confluence strategy reports 3 of 4 with no change to the alert layer.

🔴 **A strategy that has not implemented the contract gets NO alerts and must SAY SO, loudly, at
startup.** It must never go quiet instead. This repo has been bitten three times by a feature
resolving through an empty registry and answering confidently — root `CLAUDE.md` rule 8. An absent
implementation is a fact worth reporting, not a default worth guessing.

⚠ **The implementation is per strategy and is written by whoever knows that strategy.** `mpc_bleg`
and `mpc_bos` get theirs when they are actually run. Do not stub them: a stub is exactly the empty
registry above.

---

## 3. How noisy — MEASURED, and the old estimate was wrong

**The 2026-08-03 version of this document INFERRED ~3/month for the "limit is resting" message and
flagged the guess as the thing most likely to make the channel unreadable. It was measured
2026-08-13 and the guess was low by 2-4x, in the noisy direction.**

One replay, `mpc_sos_fade` at shipped defaults, **155,807 M15 bars, 2020-01-01 → 2026-08-06**
(79.1 months), `exec_secondary=False`, warm-up records dropped:

| message | count | per month |
|---|---|---|
| **WATCHING** — armed + SOS in, awaiting the retrace | 609 | **7.7** |
| **RESTING** — raw `None → _Pending` transitions | 665 | 8.4 |
| **RESTING** — deduped per setup `(side, sos_bar)` | 332 | **4.2** |
| **ENTERED** | 159 | 2.0 |
| **NEVER FILLED** (miss code 7) | 10 | 0.1 |
| **BLOCKED** | 321 | 4.1 |

Three findings, all load-bearing on the design:

🔴 **The resting-limit message must be deduped per SETUP, not per transition.** `_pend_long` /
`_pend_short` are rebuilt every bar and set to `None` when not armed, so one setup flickers in and
out of `_Pending` repeatedly — 665 transitions across 332 setups. An edge-triggered alert on the
raw transition announces the same setup two or three times. This is §7.1 of the old spec being
correct about the mechanism and still not going far enough: edge-triggering is necessary and not
sufficient.

⚠ **Roughly 3 of every 4 "upcoming trade" messages will not become a trade** — 609 setups reach
2-of-3, 159 fill. That is the strategy behaving as designed (a selective entry refuses most of what
it looks at), and it means the WORDING must say *setup forming*, never *trade incoming*. A channel
whose headline is wrong 74% of the time reads as broken.

🔴 **A third "finding" stood here and it was WRONG. It is recorded as wrong rather than deleted,
because it was quoted to Aaron before it was checked.** The claim was: *"220 of the 609 are
divergence-armed and this bot trades sweep-only, so they can never fill — filter them and the rate
drops to 4.9/month."*

**False, by two orders of magnitude.** `arm_src` records which source reached stage 1 **first**.
Tradeability is a different question — `sos_l_swp`, *was a sweep live at the SOS* — and nearly
every divergence-armed setup carries one too, so it is tradeable and most of them trade.
**Measured two independent ways after the filter was built: it suppresses ONE setup in 6.5 years,
and `miss_audit.py` reports ZERO misses with code 1 ("arm source off") over the same window.**

⚠ **The lesson is one this repo keeps meeting from new directions: a count that is easy to obtain
is not the count you asked for.** The 220 was real, measured, and about something else. **Ask what
a field MEANS before reading a rate off it** — and the tell was available immediately, because
code 1 exists precisely to count this and answered zero.

**MEASURED END-TO-END once the thing was built** — `backtest/tools/alert_rate.py`, same window,
driving the real contract, the real transition layer and the real formatters with the sender
replaced by a collector:

| message | count | per month |
|---|---|---|
| 👀 SETUP FORMING | 608 | 7.7 |
| 👋 NO TRADE | 449 | 5.7 |
| 🎯 BUY/SELL LIMIT RESTING | 301 | 3.8 |
| ✅ ENTERED | 158 | 2.0 |
| 🚫 BLOCKED | 55 | 0.7 |
| **total** | **1,571** | **19.9** |

**608 threads, one per setup. Roughly one message every 1.5 days. 26% of announced setups became
trades.**

⚠ **Re-measured 2026-08-14 after the retrace gate landed** (§5.2): the resting alert went 332 → 301
and the total 1,602 → 1,571. The 31 suppressed messages are setups where price never retraced to
0.236, i.e. never came close to filling — the invariant below is unchanged at 159 / 158.

✅ **THE INVARIANT HOLDS, and it is checked by the tool rather than asserted here.** Aaron's
requirement, 2026-08-13: *"the same trade signals that are going to the LWG Capital Algo trades
group will originate from the signals that are going to this new group."* **159 trades closed, 158
announced as ENTERED.** The one is the warm-up boundary — a setup that opened before the window
began is discarded rather than posted, which is also what stops the first live bar dumping years of
history into Telegram. `alert_rate.py` prints this check every run and says 🔴 BROKEN if more than
one trade arrives unannounced, because that is the failure mode of the `tradeable` filter:
suppress one setup too many and a real trade reaches the broker having never been signalled, with
nothing anywhere reporting a skipped message.

⚠ **BLOCKED came in at 0.7/month, not the 4.1 the transition counts above predicted, and the gap
is a FIX rather than a discrepancy.** `BlockedSetup` counts a refusal each time a *ready* setup is
turned down; the first version of this alert reported any veto, final-hour or HTF rule that was
live while a setup was merely FORMING. That announced setups as blocked which then went on to rest
and fill — under a sentence reading "the setup was ready and this rule stopped it". It now asks the
same readiness question `BlockedSetup` does. **Found by rendering the messages against real bars,
not by reading the code.**

⚠ **158 ENTERED against 159 trades is correct.** One trade's setup opened during warm-up, and
warm-up snapshots are discarded rather than announced — otherwise the first live bar would post
years of history in one burst.

⚠ **`SetupSnapshot.tradeable` IS implemented and it changes almost nothing** — see the correction
in §3. It exists to enforce Aaron's rule (*"I should only be getting signals for the trades
originating from my default settings"*) whatever the strategy or the config, not because it trims
volume on this one. **Set it False only for a decision the strategy has ALREADY made and cannot
revisit.** A merely-unmet confluence is not untradeable — it is the normal state of every setup
before it fills — and getting that wrong hides real signals silently. A veto or the final hour can
lift while a setup is alive, so those stay reportable and travel as `blocked_by` instead.

⚠ **All of the above is `mpc_sos_fade` on XAUUSD M15 over one 6.5-year window.** It is not a
prediction for any other strategy, and a new bot's rate must be measured the same way before its
alerts are switched on.

**The measuring script is `backtest/tools/alert_rate.py`.** Re-run it after any entry-logic change,
and for every new strategy that implements the contract — same standing as `overlap_audit.py`.

---

## 4. The contract — `backtest/setups.py`

Two frozen dataclasses and one method. Reporting only.

```python
@dataclass(frozen=True)
class Confluence:
    name: str            # "Sweep", "Shift of structure", "Retrace zone"
    met: bool
    detail: str = ""     # "Day High" / "confirmed" / "0.5-0.886 tagged, no FVG yet"

@dataclass(frozen=True)
class SetupSnapshot:
    key: str                            # stable for this setup's whole life — the thread id
    strategy: str
    symbol: str
    side: int                           # +1 long, -1 short
    state: str                          # WATCHING / RESTING / FILLED / DEAD
    confluences: tuple[Confluence, ...]
    zone: tuple[float, float] | None    # (shallow, deep) — the whole valid entry range
    entry: float | None                 # the ONE resting price; None until there is one
    stop: float | None                  # projected from the deep edge before an order exists
    targets: tuple[float, ...]
    blocked_by: tuple[str, ...]         # rules currently refusing it
    reason: str = ""                    # why it ended — FILLED / DEAD only
```

**`zone` and `entry` are different questions and both are wanted** (Aaron, 2026-08-13: *"you have a
valid entry zone anywhere between the most shallow area to the deepest area and the potential stop
loss is this"*). `zone` is the range price must reach for this setup to be tradeable at all — known
the moment the setup arms, which is what makes the WATCHING message useful. `entry` is the single
price an order is actually resting at, and does not exist until one is. For `mpc_sos_fade` the zone
is the 0.5 → 0.886 fib band (`fibo_p2` → `fibo_p6`) and the stop projects off the deep edge, so
both are answerable a long time before a limit is placed.

⚠ **A strategy with no meaningful pre-entry range reports `zone=None`** rather than collapsing it
onto `entry`. Two facts, two fields; a range and a price are not the same claim.

Strategies implement `live_setups() -> list[SetupSnapshot]`.

**Why the state machine lives in the SNAPSHOT rather than in the alert layer.** The alternative was
for the alert layer to notice a setup disappear and then cross-reference the strategy's `misses` /
`blocks` records to find out why. That needs a shared join key those records do not carry, and a
join that matches too little invents drift while one that matches too much invents parity — the
trap already recorded for `shadow_diff.py`. A strategy reports its own setup one last time carrying
its own resolution, and the alert layer never has to correlate anything.

**Rules, all load-bearing:**

⚠ **`key` must be stable for the setup's whole life and unique across sides and strategies.** It is
the Telegram thread id and the dedupe key. For `mpc_sos_fade` that is strategy + side + the SOS bar
— the same identity `_MissWatch` already keys on.

⚠ **Prices are COPIED from what the strategy is holding, never recomputed.** §9.

⚠ **REPORTING ONLY.** Nothing may read a `SetupSnapshot` back into a decision. That is what keeps
`compare_strategy.py` a valid parity gate — it diffs the `px_*` decision stream and this touches
none of it. Same standing as `mfe_usd`, `tp1`/`tp2`, `Trade.fib` and `MissedSetup`.

⚠ **Prove reporting-only by REPLAY, not by argument.** Replay the full history at HEAD and at the
working tree and require a byte-identical trade list, the way the `zone_time_ms` work did. A green
parity gate says the two implementations agree, never that either is right (rule 14).

---

## 5. The five messages

One Telegram **thread per setup**, keyed on `SetupSnapshot.key`. Every outcome replies to the root,
so a setup and what became of it are never read apart. `send_telegram_id` + `reply_to` already does
this — the same mechanism that makes a trade exit reply to its entry.

### 5.1 Watching (the root) — Aaron's 2-of-3

Fires when a setup first appears. **7.7/month on A+** — not the 4.9 an earlier draft claimed; see the correction in §3.

```
👀 SETUP FORMING · SHORT
mpc_sos_fade — XAUUSD.p   (2 of 3)

Sweep — Day High
Shift of structure — confirmed
Retrace zone — not tagged yet

Entry zone 3,405.10 – 3,418.60
Stop if it fills 3,428.90

Waiting on a retrace into that zone.
```

⚠ **"SETUP FORMING", never "POTENTIAL TRADE".** Three of four of these do not trade.

⚠ **"Stop IF IT FILLS", never "Stop".** The stop is projected off the deep edge of the zone and no
order exists yet. Stating it flat would be a price the bot is not holding — §9.

### 5.2 Limit resting — replies to 5.1

A real order exists at a price and has NOT filled. ~4.2/month. **Deduped per setup** (§3) — one of
these per setup, ever, whatever the order does afterwards.

```
🎯 SELL LIMIT RESTING
2 of 3
Limit 3,412.55 · stop 3,428.90
TP1 3,389.20 · TP2 3,371.05
Still missing: Retrace zone
```

🔴 **It was headed `ENTRY ZONE LIVE` for one day and was read as a FILL by the only person who
reads this channel** (Aaron, 2026-08-14: *"I thought the trade entered when you just did a limit
order"*). It had not: price was 41 points above the limit and never came back that day. The header
is now the MT5 order type he sees in the terminal, so the message and the platform call one thing
by one name, and `RESTING` says the part the old header said nowhere.

🔴 **THE FINDING IS THAT THE VERBOSITY TRIM CAUSED IT, AND IT IS THE MORE USEFUL HALF.** The
version above this one — shipped 2026-08-13, `29661b1` — read
`Entry 3,412.55   (limit resting)` and numbered its targets. The trim later that day (`6bcae0e`,
eight lines down to four) deleted **both**: `(limit resting)` went out with `(the zone's deep
edge)` as an explainer, and `TP1`/`TP2` collapsed to a bare `TP`. One of those two really was an
explainer. **The other was the only word on the message saying nothing had been bought**, and
removing it left a header naming a ZONE over a body naming a PRICE, with no verb anywhere.
⚠ **The transferable rule: when trimming a message, a word that explains a NUMBER is decoration
and a word that names the STATE of something is not** — `(the zone's deep edge)` tells you how
4,317.71 was derived, which the reader can live without; `(limit resting)` tells you no position
exists, which they cannot. Both looked like the same kind of parenthetical.

🔴 **An order can rest at 2 of 3, and the message must not imply otherwise — found by rendering
this against real bars rather than by reading the code.** The entry edge comes from a gap
overlapping the 0.5-0.886 band, and the gap can be there before PRICE is, so the limit is placed
in advance while the retrace confluence is still outstanding. The first version listed only the
MET confluences and so hid the one fact a reader needs: the order is real, and price has not come
to it yet.

The FVG line is what carries Aaron's *"stop loss could be there because I see a fair value gap in
this zone"* — and its absence carries the other half, *"no fair value gap in this zone, but this is
a valid entry zone"*. Both sentences come from the strategy's own zone state; neither is composed
by the alert layer.

⚠ **The entry price can move while the limit rests and this message is NOT re-sent** (Aaron's call,
2026-08-13). `_entry_edges` is recomputed every bar and a new gap can shift the resting price. The
"Entered" message carries the real fill.

🔴 **AND THAT ONE-MESSAGE RULE IS WHY THIS MESSAGE NOW WAITS FOR A RETRACE.** Measured on the live
bot 2026-08-14: one setup went through **four broker tickets in 45 minutes** — 4,323.55 / 4,330.63 /
4,331.81 / 4,333.66, size falling 1.71 → 0.71 lots as the stop widened — and only the first was ever
announced. So the phone said 4,323.55 while the broker held 4,333.66. Announcing once was the right
call and it was made without noticing it leaves the one message that IS sent quietly wrong.
✅ **Fixed by sending LATER rather than more often** (`announce_resting`, `backtest/setups.py`): the
strategy holds the message until price retraces to its `alert_resting_fib` (0.236 for
`mpc_sos_fade`), which is both nearer the action and a fresher price. **The order is unchanged — it
still rests the moment the setup arms.** ⚠ **The threshold must stay SHALLOWER than the entry band**,
which is what makes a suppressed message provably a setup that never traded. Volume over 6.5 years:
332 → 301 resting alerts, invariant unchanged at 159 trades / 158 announced.

### 5.3 Entered — replies to 5.1

The short version. The trades chat still gets its own full entry alert from the bridge — different
room, different job (`algos/CLAUDE.md` → *Two rooms*). This is not a duplicate of it.

### 5.4 Didn't fill / setup died — replies to 5.1

Aaron's *"a trade left us and we did not get in"*. Carries the strategy's own reason string.

```
👋 NO TRADE

All three confluences met and the limit rested —
price never came back to touch it.
```

### 5.5 Blocked by a rule — replies to 5.1

A setup that was fully ready and one of your own rules refused. ~4.1/month. This is the message
that tells you whether a rule is protecting the account or costing it. Carries **every** refusing
rule, not just the first — `BlockedSetup.reasons` already returns the full list in precedence
order.

---

## 6. Where it lives

| Piece | Where | Why there |
|---|---|---|
| The contract | `backtest/setups.py` | The one layer both `algos/live/` and `strategies/python/` already import. Strategies must never import `algos/` |
| Per-strategy implementation | `Execution.live_setups()` in each strategy | Only the strategy knows its own confluences |
| Transition detection + threads | `algos/live/setup_alerts.py` | New module beside the bot |
| Formatting | `algos/live/alerts.py` | Pure, beside `format_entry` / `format_exit` — no network, no state, so wording is unit-testable and changing it can never change a trade |
| Sending | `runner._notify` | Per-bot chat and token routing come for free |
| The room | a third `kind`, `SIGNAL` → `telegram_signal_chat` | See below |

**A third room, not a third use of an existing one.** `algos/CLAUDE.md` → *Two rooms* is explicit
that the chat carrying fills carries nothing else, and that a `kind` is REQUIRED so nothing routes
silently. Signals are a third reflex: read when you have time, not the moment they arrive, and far
more frequent than fills. It follows the same fallback rule as HEALTH — unset falls back to the
trades chat and says so once, because an alert in the wrong room beats no alert.

**Never raise.** `notify.py`'s standing rule: a notifier that can take down a trading loop is worse
than a missed message. Every failure path prints and returns.

**Thread ids are held in memory** on the runner, keyed by `SetupSnapshot.key`, dropped when the
setup resolves. A lost id is cosmetic — `send_telegram_id` already retries as a standalone message
when a reply target is gone.

---

## 7. Build order

1. `backtest/setups.py` — the contract, with tests.
2. `Execution.live_setups()` for `mpc_sos_fade`, snapshotting from `_MissWatch` and `_pend_*`.
   Prove reporting-only by full-history replay (byte-identical trade list).
3. Re-run `compare_strategy.py` to exit 0. It must be unmoved.
4. `format_watching` / `format_entry_zone` / `format_entered` / `format_no_trade` /
   `format_blocked` in `alerts.py`. Unit-test the strings.
5. `algos/live/setup_alerts.py` — transitions, per-setup dedupe, thread bookkeeping, which
   categories are enabled.
6. `SIGNAL` kind in `notify.py` + `telegram_signal_chat` + the per-instance override.
7. Wire into `runner._on_bar`. Keep writing the ledger; the alert is additive.
8. Startup: say which strategies implement the contract and which do not. Never silent.
9. Dry-run for a week and read the volume before trusting it.

---

## 8. Rejected: sending a chart IMAGE

Considered first and dropped 2026-08-03, on a measurement rather than an argument. Recorded so it
is not re-proposed blind.

The idea was to send the chart drawn up — fibs, entry zone, stop — as a picture. Two of the three
pieces already exist: the backtest chart renders itself to a PNG
(`ChartPanel/index.tsx::copyChartImage`), and Telegram's `sendPhoto` is a small addition to
`notify.py`. **The missing piece is that nothing anywhere draws a LIVE chart** — every chart in the
command center is built from a finished run directory.

Aaron's constraint is that it cannot depend on his laptop, which means it runs on the VPS.
**Measured on the VPS, 2026-08-03: 2 logical processors, 4 GB RAM, ~920 MB free.** A headless
Chromium with a 30k-candle chart loaded is 300 MB–1 GB, next to a live trading bot on two cores.
Drawing it in Python instead is a few hundred lines plus a second thing in this repo that draws
charts.

**The text version delivers the actual requirement — knowing why, before the outcome — at a
fraction of the cost.** Revisit only if the lab moves to its own hardware.

---

## 9. The standing rule for this feature

**Every number and every sentence in these messages must be the one the strategy used — copied,
never re-derived.** The entry price, the stop, the targets, the arm source, the swept pool's name,
whether a gap is live in the zone: all of them already exist in the running strategy. A message that
recomputes any of them is a second claim about one setup, and two claims can disagree — which is how
this repo has already been bitten five times (the Run modal's costs, the Optimize modal's params,
the SSH health dot, the lab-vs-Pine parameter names, the fib the chart nearly rebuilt itself).

**An alert that names a level the bot never traded is worse than no alert, because you would act on
it.**
