"""SosFadeConfig — every input toggle the A+ strategy trades on, with the SAME name
and SAME default as `strategies/tradingview/mpc_strategy.pine`.

**Toggle parity is a hard requirement** (see docs/MPC_SOS_FADE_SPEC.md): the regression
harness reads the toggle columns out of a TradingView export and configures this
dataclass to the exact settings the Pine ran under, so any config you and your
brother pick reproduces bar-for-bar. A new toggle in the Pine is a new field here.

Scope: this carries the toggles that change a TRADE DECISION or the divergence
veto/active state — the execution group (`GRP_EXEC`), the divergence group
(`GRP_DIV`) that feeds the veto, and the A+ staleness window (`GRP_APLUS`). Purely
cosmetic Pine inputs (debug labels, position boxes, the stats table styling) do not
touch the decision stream and are deliberately not declared. `exec_scratch_r` is the
one Result-Stats input kept, because it classifies a closed trade's R as WIN / LOSS
/ SCRATCH — part of the decision stream the parity check diffs.

Instrument facts (mintick, point value, the daily-close time) are Layer-B injections,
not Pine inputs — they live here too so the strategy stays instrument-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

# The legal `exec_time_stop_mode` values, named once so `__post_init__`, the parity
# harness and the meta file cannot drift into three different opinions about them.
_TIME_STOP_MODES = frozenset({"Off", "Before TP1 only", "Always"})
_NOGAP_ARMS = frozenset({"Any", "Sweep + RSI div"})


@dataclass(frozen=True)
class SosFadeConfig:
    # ── GRP_EXEC — Strategy Execution (mpc_strategy.pine 4159-4183) ──────────────
    exec_longs: bool = True            # "Trade longs"
    exec_shorts: bool = True           # "Trade Shorts"
    exec_aplus: bool = True            # "Trade A+ setups" (Pine execAplus)
    #   On (default) = the A+ reversal sequence arms normally. Off = no A+ entry ever fires —
    #   pair with `exec_bleg` ON in the B-LEG bot to read that setup's results in isolation.
    exec_bleg: bool = False            # "Trade B-Leg setups" (Pine execBLeg)
    #   The A+ bot never trades a B leg, so this stays False here; `mpc_bleg.BLegConfig`
    #   overrides it to True to match `strategies/tradingview/mpc_b_leg_strategy.pine`'s own default.
    exec_arm_sweep: bool = True        # "Arm on liquidity sweep"  (Stage-1 trigger)
    exec_arm_div: bool = False         # "Arm on RSI divergence"   (Stage-1 trigger)
    exec_req_fvg: bool = True          # "Require an FVG in the zone"
    exec_nogap_arm: str = "Any"        # "↳ No-FVG entries need" ∈ {Any, Sweep + RSI div}
    #   PYTHON-ONLY, NO PINE COUNTERPART (2026-08-10). `mpc_strategy.pine` has `execReqFVG` and
    #   nothing beside it, so `compare_strategy.py` can never configure a non-default run and a
    #   result taken with one is a LAB FINDING, not a validated one. No live bot may run it.
    #
    #   ⚠ **READ ONLY WHEN `exec_req_fvg` IS FALSE**, so at the shipped defaults it is INERT and
    #   no historical result moves. It is deliberately a refinement of the existing fallback
    #   rather than a second field answering the same question: `exec_req_fvg` decides WHETHER a
    #   setup with no zone may still trade, and this decides WHICH of those setups may. Two
    #   independent booleans would let a reader switch one on and read the other's answer.
    #
    #   "Any"            — every no-zone setup rests at the 0.618. This is BYTE-IDENTICAL to what
    #                      `exec_req_fvg = False` did before this field existed, which is what
    #                      makes the default safe and what a test pins.
    #   "Sweep + RSI div"— only when the SOS carried BOTH arm sources. `SeqState.sos_l_swp` /
    #                      `sos_l_div` are the RAW arm flags (before the enable toggles), which is
    #                      correct here: the question is what the market did at the SOS, not which
    #                      triggers the operator left switched on. It is therefore independent of
    #                      `exec_arm_sweep` / `exec_arm_div`, and NOT a way of saying "arm on both".
    #
    #   MEASURED 2026-08-10, 155,531 M15 bars (2020-01-01 → 2026-08-03), one real replay per row,
    #   `exec_secondary` off. Baseline 159 trades / +142.18R:
    #       "Any"             315 trades / +149.55R  maxDD 12.70R
    #       "Sweep + RSI div" 230 trades / +155.89R  maxDD  9.54R
    #   Charged at the live account (PU Prime ECN, spread 0.12 STATED): 159 / +132.23R ·
    #   315 / +134.78R · 230 / +144.78R — costs are what SEPARATE the two, because "Any" adds 156
    #   trades to earn +7R and pays spread on all of them. Jittered ±$0.05/bar over 8 seeds the
    #   gated book beat the shipped book on 8 of 8 and was never negative.
    #   ⚠ Read the R as "not worse": the +13.71R gain sits inside this strategy's own run-to-run
    #   spread of 15.06R. **The FREQUENCY is the measured gain** — median gap between trades
    #   9.5 → 7.3 days, worst drought 99.7 → 54.5 days, months with no trade at all 8 of 80 → 4.
    #   ⚠ And it is bought with drawdown: 5.61R → 9.54R free, 6.03R → 11.12R charged.
    exec_poi_source: str = "FVG"       # ∈ {FVG, Order block, Either, FVG first, Order block (no FVG)}
    #   THE PINE SIDE EXISTS (2026-08-09, later the same day). This comment previously read
    #   "PYTHON-ONLY, NO PINE COUNTERPART" and that is now FALSE — it is corrected in place
    #   rather than left to be read as current. `mpc_strategy.pine` and its export mirror carry
    #   `execPoiSource` and the ported OB engine, and the export plots `cfg_poi_source`, which
    #   `compare_strategy.py` decodes. ⚠ **The gate has still not RUN on a non-FVG export**, so
    #   any non-default result is a LAB finding until it does, and no live bot may run one.
    #
    #   WHAT IT SWITCHES, and what it deliberately does NOT. It changes only WHICH zones count as
    #   the "point of interest" the setup needs in the 0.5-0.886 band. Every rule downstream is
    #   untouched: the deep-only filter, the pre-zone gate, the four entry rules (`_fib_snap`), the
    #   stop anchor and the whole exit ladder all read the chosen zones through the SAME code, because
    #   an order block is adapted into the gap's own `(top, bottom, is_bullish, born)` shape rather
    #   than getting a parallel path. That is what makes "order blocks obey the same rules as a gap"
    #   true by construction instead of by two implementations agreeing.
    #
    #   ⚠ `born` for a block is its **created_index**, NOT its origin candle. The block's anchor
    #   candle can be ~10 bars older than the bar the engine can first report it on, and the
    #   pre-zone gate asks "was this ALREADY THERE when price arrived" — answering that with the
    #   anchor bar would credit the setup with a zone nothing could have seen yet, which is
    #   look-ahead wearing a reasonable-looking field name.
    #
    #   ⚠ "Either" is a UNION, so it can only ever ADD zones — but more zones is not more trades in
    #   one direction: a nearer qualifying zone re-prices the resting limit, so a setup that filled
    #   before can miss, and with one position slot an added trade DISPLACES a later one. Read the
    #   trade count as changed, never as increased.
    #
    #   ── "FVG first" — the PRECEDENCE mode (2026-08-09, Aaron: "could I add, like, a precedence
    #   order? If there is fair value gaps, take those preferentially over order blocks") ────────
    #   The same union of zones as "Either", RANKED instead of pooled. Three tiers, and the entry
    #   takes the best tier that has a qualifying zone on the leg:
    #       a gap an order block sits on  >  a plain gap  >  an order block
    #   Nearest-first only decides WITHIN a tier, so a higher tier wins however much further away
    #   its limit rests. See `signals.POI_RANK_*`.
    #
    #   ⚠ "Either" and "FVG first" hold the SAME zones and differ only in which one prices the
    #   entry, so a difference between them is entirely an ENTRY-PRICE effect. That is the pair to
    #   run if you want the half of the order-block result this bot's CLAUDE.md says the first run
    #   could not separate — which setups qualify, versus where the limit rests.
    #
    #   ⚠ It is NOT "FVG" with a fallback bolted on, and the trade counts will show it: a leg whose
    #   only zone is a block still trades, so this takes strictly more setups than "FVG" does. The
    #   measured warning stands — requiring a block was worse than requiring nothing — and the
    #   fallback tier is exactly the population that measured badly.
    #
    #   ⚠ The confirming block must point the SAME WAY as the gap. Aaron's rule named no direction;
    #   this is the reading taken, because in a long setup a bearish (supply) block on a bullish
    #   gap is the opposite of confirmation, and ranking that gap TOP would promote the worst
    #   candidate on the leg. One predicate in `signals.pois_for` to flip if the undirected
    #   version is wanted — and it must be flipped in `mpc_strategy.pine` in the same commit.
    exec_fvg_deep_only: bool = True    # "Gap must sit fully past 0.5"
    exec_fvg_pre_zone: bool = False    # "Gap must pre-date the zone"
    #   Pine execFvgPreZone (2026-08-02). ON = a gap only counts if it was already alive on the bar
    #   price first tagged 0.5. A gap BORN inside the 0.5-0.886 band, printed by the flip once price
    #   is already there, is the retrace manufacturing the confluence it is judged on. It gates BOTH
    #   gap consumers — the confluence flag in `sequence.py` and the entry-edge loop here — so a gap
    #   the entry may not use can never be labelled as the confluence that armed the setup.
    #
    #   ── The 2026-08-02 entry model: WHERE a qualifying gap's limit rests ──────────────────────
    #   Four toggles, and the shape matters. Rule 1 is INDEPENDENT (it fires only on a gap whose
    #   BODY holds a level). Rules 2 / 3 / Method 3 all answer the SAME question — where does a
    #   FLOATING gap rest? — so they CASCADE, each overriding the one below it. Every level scan
    #   stops at 0.786: 0.886 is the stop, so an entry resting there is a zero stop distance and a
    #   cancelled order. Ported from Pine `f_fibEntry`.
    exec_fib_overlap: bool = False     # "Gap on a fib → enter on the fib"
    exec_fib_deep_edge: bool = False   # "Floating gap → its own deep edge"
    #   Rule 2, MEASURED WORSE than rule 3 alone over 2020-2026, hence OFF. The only deep rule that
    #   ALWAYS fills (the limit sits INSIDE the gap). Overrides rule 3 and Method 3.
    exec_fib_nearest: bool = True      # "Floating gap → nearest fib (either side)"
    #   Rule 3, the SHIPPED default. Measures the near edge up to the level above and the far edge
    #   down to the level below, and rests on whichever is closer (ties go to the shallower). Not
    #   free: when the deeper level wins the limit rests PAST the gap, so a setup that only tags the
    #   gap and turns never fills. Deeper entry and a tighter stop, bought with fill rate.
    exec_ob_deepen: bool = False       # "Order block deeper than the entry → rest on the block"
    #   Aaron's confluence question, 2026-08-09: a same-direction order block sitting DEEPER than
    #   the chosen entry edge re-prices the limit onto that block's near edge (clamped into the
    #   0.5-0.886 band). The stop is a fib and does not move, so a deeper fill is a TIGHTER stop —
    #   a bigger position for the same risk and more room to the targets — bought with FILL RATE.
    #   ⚠ MEASURED FIRST, and the selection is brutal: over 159 baseline trades a deeper block
    #   existed on 113, and price actually reached it on 4 of 40 winners, 11 of 36 scratches and
    #   35 of 37 LOSERS. A winner leaves and never comes back; a loser grinds down through the
    #   block to the stop. So this rule fills almost exclusively on the trades that were going to
    #   lose — which is why it is a REPLAY question and not an arithmetic one, and why it is OFF.
    #   🔴 REPLAYED and REFUTED, 155,807 M15 bars: 159 trades / +142.18R / maxDD 5.61R becomes
    #   102 / +73.41R / maxDD 15.20R. The theory it was built to test — a deeper fill reaches TP1
    #   more often, stages to breakeven and scratches instead of losing — runs BACKWARDS, and the
    #   mechanism is geometry rather than luck: TP1 is a fib ABOVE a long, so entering deeper puts
    #   it FURTHER away. TP1 hit rate 65.4% → 47.1%, LOSERS 52 → 52 (unchanged) and their R
    #   −50.86 → −71.30, scratches 44 → 15. See `### The deeper-entry test` in CLAUDE.md.
    #   ⚠ The average loss exceeding 1R (−0.98R → −1.37R) is the min-stop hazard arriving by a new
    #   route: a stop a median 79% tighter sits inside ordinary bar noise, so price runs through it
    #   and the exit no longer happens at the stop price. A risk % is only the real risk if it does.
    #   ⚠ NO PINE COUNTERPART, so `compare_strategy.py` can never configure it and any result is a
    #   LAB finding. Python-first, the same standing as `exec_sl_custom`.
    exec_deep_fib: bool = False        # "Floating gap → nearest fib shallower"
    #   Method 3 (Pine execDeepFib) — the original one-sided form of rules 2 and 3, kept so any
    #   historical result reproduces. Reachable only with rules 2 AND 3 both off. It never looks at
    #   the level BELOW the gap however much closer that one is, which is the bug rule 3 fixes.
    #   ⚠ Defaulted True → False on 2026-08-02 in lockstep with the Pine: rule 3 replaced it.
    #   (`exec_fvg_50` lived here from 2026-07-24 to 2026-08-02 — the Pine's "Entry (least
    #   favorable): FVG must touch the 0.5 line". It was never ported and never used, and Aaron
    #   had the Pine input DELETED, so the field went with it. `compare_strategy.py` still
    #   refuses an ARCHIVED export carrying cfg_bits bit 65536, reading the bit directly.)
    exec_respect_veto: bool = True     # "Respect divergence/extreme veto"
    exec_close_opp_sos: bool = False   # "Close on opposite SOS"
    exec_htf_exhaust_only: bool = False  # "Only fade HTF exhaustion, not breakouts"
    exec_htf_source: str = "Weekly"    # "HTF exhaustion source"  ∈ {Weekly, Daily, Either}
    exec_htf_weekly: str = "Ignore"    # "Weekly bias requirement"
    exec_htf_daily: str = "Ignore"     # "Daily bias requirement"
    #   HTF-bias options: Ignore | Must agree | Must not oppose | Must oppose (reversal)
    exec_risk_pct: float = 10.0        # "Risk % per trade"
    exec_sl_level: str = "0.886"       # "Stop fib level"  ∈ {0.618, 0.702, 0.786, 0.886, 1.0, Custom}
    #   **Defaulted "1.0" → "0.886" on 2026-07-27** (Aaron's call, and how his TradingView chart is
    #   configured), in lockstep with both A+ Pine files. 0.886 is the DEEP EDGE of the 0.5-0.886
    #   entry band, so the stop sits just past the deepest price a limit may rest at. Evidence: the
    #   2026-07-27 parity run went GREEN at it, and Run 6 rode it over the broker's whole intraday
    #   history — 188 trades, 107.7R, 293x, −54.9% maxDD, no degenerate stop.
    #   ⚠ It is still one of the four levels INSIDE the entry band, so Run 4's structural hazard is
    #   not gone, only unobserved at this level: nothing validates that the stop lands on the far
    #   side of the entry, and a near-zero stop distance balloons `qty = risk / dist`. The three
    #   SHALLOWER levels (0.618 / 0.702 / 0.786) remain unsupported — 0.786 detonated an account to
    #   −$63k in Run 4. See the ⚠ block in CLAUDE.md before changing this.
    #   **"Custom" (added 2026-08-02, Aaron's request)** frees the level from the five-value dropdown
    #   and reads `exec_sl_custom` instead — the ladder never had a 0.90, and a stop is a price, not
    #   a member of a set. It is the ONE value here with no Pine counterpart; see the field below.
    exec_sl_custom: float = 0.886      # "Custom stop fib level", read ONLY when exec_sl_level == "Custom"
    #   The retracement ratio of the SOS leg, priced through the canonical `engines.fibonacci`
    #   `fib_level()` off the leg anchors the fiboP* were built from — so 0.886 here is the SAME
    #   price to the last bit as picking "0.886" from the dropdown, and the two are interchangeable.
    #   That is why the default is 0.886 and not Aaron's 0.9: switching the mode to Custom changes
    #   nothing until the number is moved, so the change is always deliberate.
    #   Legal range 0 < v <= 1.0, enforced in __post_init__ and ONLY when the mode reads it (a swept
    #   value sitting behind a non-Custom mode is inert, not an error). The bound is Aaron's stated
    #   spec, and 1.0 is where the ladder ends — the leg origin, past which the leg is invalidated.
    #   ⚠ SHALLOWER IS NOT SAFER. Below ~0.886 this walks straight into Run 4's hazard: the entry is
    #   a resting limit inside the 0.5-0.886 band, so a stop shallower than the fill sits ON or PAST
    #   the entry. `dist <= 0` refuses the order outright (no trade, no tag), and a merely TINY dist
    #   is the dangerous one — `qty = risk / dist` balloons the position. Turn `exec_min_stop_mode`
    #   on before going below 0.886. DEEPER (0.886 → 1.0) is the safe direction and is the reason
    #   this exists: it is the half of the range the dropdown never covered.
    #   ⚠ NO PINE COUNTERPART. `mpc_strategy.pine`'s `execSlLevel` is an `input.string` with five
    #   options, so a Custom run has nothing to diff against and `compare_strategy.py` can never
    #   configure one (it decodes `cfg_strcodes` into those five). A Custom result is a LAB finding,
    #   not a validated one — port the input to the Pine before trading it.
    exec_sl_deep: bool = False         # "↳ entries at 0.786 or deeper stop at 1.0 instead"
    #   Pine execSlDeep (2026-08-02). OFF = every trade's stop is `exec_sl_level`, whatever the fill.
    #   ON = an entry that fills AT OR DEEPER THAN the 0.786 fib puts its stop at the leg origin (1.0)
    #   instead; 0.702 and shallower keeps the chosen level. It exists because the entry band and the
    #   stop share the 0.886 line, so the band's deep end is priced against a stop it is nearly
    #   touching — 0.100 of the leg at a 0.786 entry, and nothing at all at 0.886.
    #   ⚠ IT COSTS R ON EVERY TRADE IT TOUCHES: a 0.786 entry goes from a 0.100 stop to a 0.214 stop,
    #   so the runner falls 7.86R to 3.67R and the position is less than half the size. You buy a stop
    #   that survives spread and noise, and pay for it in reward. Measure it, do not assume it.
    #   The test is INCLUSIVE (<= / >=) because 0.786 is a SNAP TARGET — rule 3 assigns fiboP5 to the
    #   edge directly with no arithmetic in between, so the comparison is exact.
    exec_sl_buf_tk: float = 0.0        # "Stop buffer beyond the level (ticks)"
    exec_min_stop_mode: str = "% of price"  # "Minimum stop distance" (Pine execMinStopMode)
    #   ∈ {"Off", "% of price", "Fixed $", "x ATR(14)"}. An ENTRY filter, nothing to do with the
    #   runner trail: refuse a setup whose stop lands closer to the entry than this floor.
    #   **This is the guard for the hazard the `exec_sl_level` warning describes.** The dollar risk
    #   is nominally unchanged, but `qty = risk / dist` means a collapsing stop distance balloons
    #   SIZE — and once the stop is narrower than an ordinary bar, price travels straight through
    #   it and the realised loss is no longer the 1R that was agreed. Measured at `0.786`: a $0.20
    #   stop, a 39,033 oz position, ~180% of equity lost in a single bar (Run 4).
    #
    #   🔴 **DEFAULT CHANGED 2026-08-05: "Off" → "% of price" at 0.08** (Aaron's call, after the
    #   sweep below). It had been "Off" so that the shipped baseline and every historical result
    #   stayed unchanged — **that is no longer true, and it is the cost of this change**: a run
    #   replayed at defaults from today refuses trades that older runs took, so every figure in
    #   this folder measured at "Off" describes a different configuration. The A+ baseline moves
    #   from **183 trades / +134.75R** to **181 / +136.75R** over 7.9 years.
    #
    #   **MEASURED over 186,220 M15 bars (2018-09-13 → 2026-08-04), 23 configs, one real replay
    #   each — refusing a setup frees the single position slot, so the trade list reshuffles and
    #   no arithmetic over a finished list can stand in for a replay:**
    #     % of price  0.05 → 183 tr  +134.75R  (+0.00, refuses nothing)
    #     % of price  0.08 → 181 tr  +136.75R  (+2.00)   ← SHIPPED
    #     % of price  0.10 → 176 tr  +132.92R  (−1.84)
    #     % of price  0.15 → 165 tr  +109.47R  (−25.28)
    #     % of price  0.30 → 130 tr   +87.10R  (−47.65)
    #     Fixed $     1.25 → 180 tr  +137.75R  (+3.00)
    #     x ATR(14)   0.35 → 183 tr  +134.75R  (+0.00, and see the ⚠ below)
    #
    #   ⚠ **A small floor GAINS R, and the reason is mechanical rather than lucky: the three
    #   tightest stops in 7.9 years ($1.03, $1.06, $1.18) were all full −1.00R losers.** Fixed
    #   $1.25 refuses exactly those three and gains exactly +3.00R.
    #   ⚠ **DO NOT read +2R as an edge.** The jitter audit measured this strategy's run-to-run
    #   spread at **sd 15.06R**, so every value from 0.05 to 0.08 is statistically indistinguishable
    #   from zero and from each other. 0.08 is chosen as the HIGHEST value that does not start
    #   costing, i.e. the most protection for nothing — a SAFETY choice, not a profit one.
    #   ⚠ **"x ATR(14)" is the WRONG TOOL for this hazard, measured rather than assumed.** At 0.35
    #   and 0.40 it never refuses the $1.03 stop at all, because that bar was quiet and $1.03 was
    #   not tight *relative to ATR*. The hazard is `qty = risk / dist`, which is pure price units —
    #   volatility does not enter it. ATR blocks a different set of trades than the one at risk.
    exec_min_stop_val: float = 0.08    # "Minimum stop floor (unit = mode above)"
    #   A PERCENT in "% of price", DOLLARS of price in "Fixed $", a MULTIPLE in "x ATR(14)".
    #   Read only when the mode is not "Off". See the sweep table above for every measured rung;
    #   below 0.05 the floor refuses nothing at all, and 0.09 upward starts costing.
    # ── the DEAD-MARKET floor (2026-08-26) ───────────────────────────────────────
    #   Refuse a setup when ATR(14) at the fill is below this % of price. A fade needs range to
    #   travel into; in a market this quiet the setup has nowhere to go and the trade is decided
    #   by spread and noise.
    #   ⚠ This is NOT `exec_min_stop_val`, which floors the STOP DISTANCE. That one asks "is this
    #   leg long enough to size against"; this one asks "is the market moving at all". A wide stop
    #   in a dead market clears the stop floor comfortably and is still the trade refused here —
    #   the two gates share a unit and answer different questions.
    #   MEASURED over 245 trades on run c868358c5177 (2020-01-01 -> 2026-08-23, priced):
    #     0.08 -> refuses 11 trades worth -10.0R, hurts 0 of 7 years, refuses NO trade above 3R
    #     0.10 -> refuses 36 trades worth -13.7R, hurts 1 of 7 (-0.3R), refuses NO trade above 3R
    #     0.11 -> starts refusing winners (+3.0R of them)
    #     0.14 -> refuses +17.9R and hurts 6 of 7 years
    #   ⚠ **The decay above 0.11 is the reason to believe the floor AND to fear it.** A fitted
    #   spike would not degrade in order; this one does, which also means the usable band is
    #   NARROW. Do not creep it upward because a quiet-market loss annoyed you.
    #   ⚠ Measured on a REPLAY of finished trades, which cannot see that refusing an entry frees
    #   the one position slot — Run 12's lesson is that trades QUEUE rather than add. Only a full
    #   lab run settles the real number.
    #   MEASURED by full replay (2026-08-26), not by the trade-list estimate above — the driver in
    #   `scratchpad/sweep.py` reproduced lab run 5c35fc4081bf to the cent (245 trades, 119.0R,
    #   $4,855,242.72) before any of these were believed:
    #     off  -> 245 trades, 119.0R      0.09 -> 235 trades, 111.5R
    #     0.08 -> 240 trades, 127.9R      0.10 -> 227 trades, 114.4R  (lab run ee2b70e3c738)
    #   🔴 **THOSE FOUR NUMBERS ARE NOISE AND MUST NOT BE READ AS A CURVE.** R swings ±8 on a 0.01
    #   nudge with no order to it, and the ENDING BALANCE swings 2x ($4.86M / $9.77M / $9.92M /
    #   $4.92M) because refusing one setup reshuffles which later trade gets the single position
    #   slot. 0.09 books LESS R than 0.08 and MORE money, which is rule 6 demonstrating itself.
    #   **The value of this floor is not measurable at this sample size — only its DIRECTION is.**
    #   Do not tune it on the R column.
    #   ✅ **THE DRAWDOWN COLUMN IS THE ONE THAT HOLDS ITS ORDER, and it is what this was built
    #   for.** Same replays, equity path ordered by EXIT TIMESTAMP:
    #     off  -> max DD 55.5%   ulcer 20.8%
    #     0.08 -> max DD 47.9%   ulcer 17.2%
    #     0.10 -> max DD 41.5%   ulcer 18.6%
    #   Worst drawdown falls in order with the floor, and the SMOOTHNESS measure bottoms at 0.08 —
    #   the shipped value, and the thing Aaron actually asked for.
    #   🔴 **An earlier pass reported 51.5% / 51.2% here and BOTH WERE WRONG: the equity path was
    #   ordered by BAR INDEX and the trade list mixes two clocks** — a 15m setup carries a 15m
    #   index, a 5m re-entry carries a 5m one, so a 2026 setup sorted ahead of a 2021 re-entry.
    #   ⚠ The failure shape is the transferable part: **a SUM is order-independent, so the ending
    #   balance and the R total came out byte-identical either way and gave no signal at all.**
    #   Only the path-dependent numbers were wrong, and they are the only ones anybody was
    #   reading. `scratchpad/sweep.py` now REFUSES when an exit timestamp is unpopulated rather
    #   than falling back to the index.
    #   ✅ **PORTED to `mpc_strategy.pine` the same day** as `execMinAtrPct` + `f_marketHasRange`,
    #   so the two sides are no longer asymmetric. ⚠ The Pine input is APPENDED after the last
    #   `input.float` rather than sitting beside the stop floor it belongs with — TradingView keys
    #   a saved chart's values off declaration order within each type, so inserting it in the
    #   readable place silently resets every later float on Aaron's live charts.
    #   ⚠ **Pine gates the 15m setup path only, because that is the only entry path Pine HAS.**
    #   The re-entry is Python-only, so it is gated here and has nothing to be compared against.
    #   🔴 **ON at 0.08 ON BOTH SIDES since 2026-08-26 (Aaron's call, taken off the drawdown table
    #   above and not off the R one). THE SHIPPED BOOK IS NOW 240 TRADES, NOT 245.** It landed OFF
    #   earlier the same day and was switched on once the run was read — the switch and the value
    #   are two separate decisions and the history is kept that way on purpose.
    #   ⚠ **EVERY BASELINE IN THIS PACKAGE MEASURED BEFORE TODAY IS A 245-TRADE BOOK.** Pin this to
    #   0.0 to reproduce one. That is not a formality here: the floor removes 5 entries, and with
    #   one position slot a removed entry changes which LATER setup gets the slot, so a stored
    #   figure does not merely shift by the refused trades' R.
    #   ⚠ **The A+/B-LEG overlap audit is STALE until `backtest/tools/overlap_audit.py` is re-run** —
    #   it was measured on the entry logic that took 245.
    #   ⚠ **The live bot does not have this until somebody PROMOTES.** A pull cannot move it.
    #   ⚠ **An export taken before today has no `cfg_min_atr` column, and the comparator reads an
    #   absent column as 0.0 rather than as this default** — which is the only thing keeping an
    #   archived export replayable now that the shipped value is non-zero.
    exec_min_atr_pct: float = 0.08     # "Minimum market volatility (% of price)"
    exec_tp1_pct: float = 0.0          # "TP1 size %"
    exec_tp2_pct: float = 0.0          # "TP2 size %"
    #   **Both defaulted 30/40 → 0/0 on 2026-07-27** (Aaron's call, and how his TradingView chart
    #   has actually been configured). 0 = bank NOTHING at the target: the whole position rides to
    #   the runner. The targets still MATTER at 0 — `_advance_stage` stages the stop off price
    #   touching TP1/TP2 (→ breakeven, → the TP2 floor) regardless of how much size the rung takes.
    #   Zero is handled without a guard: `_remaining_brackets` computes p1 = p2 = 0, so neither
    #   bracket is emitted and only the runner is left. The Pine needs an explicit guard (a
    #   `strategy.exit` with qty_percent = 0 closes the WHOLE position) — see mpc_strategy.pine.
    #   Measured: `mpc_sos_fade_optimization.md` Run 1 — 0/0 = 70.7R vs 47.9R at 30/40, monotonic
    #   across all 21 combos (~−2R for every 10% moved off the runner). The runner is the edge.
    #   NOTE this is `BLegConfig`'s parent, so the B-LEG bot inherits 0/0 too — intended, both bots
    #   share one exit ladder.
    exec_be_buf_tk: float = 30.0       # "Breakeven buffer (ticks)"
    #   ⚠ A FIXED price offset, applied identically whatever the trade is risking. That is what
    #   `exec_be_buf_mode` exists to replace — see below.
    exec_be_arm_r: float = -1.0        # "Protect the stop after a move of (R)"
    #   MOVE THE STOP ON HOW FAR THE TRADE HAS GONE, not on whether it touched a target. -1.0
    #   (default) is OFF and nothing moves. A positive number arms once the trade's favourable
    #   excursion reaches that multiple of its FROZEN entry risk, whatever the ladder did.
    #
    #   🔴 IT EXISTS BECAUSE THE STOP HAS EXACTLY ONE TRIGGER TODAY AND IT IS A TARGET TOUCH. A
    #   trade can run a full R in profit and, as far as the stop is concerned, nothing has
    #   happened. MEASURED on the re-entry short of 2020-11-04 (run `ed21fca08a91`: entry 1902.97,
    #   stop 1912.55354, risk 9.58354, first rung 1.25R): its best price was 1893.23 — **1.016R in
    #   profit** — and its nearest rung sat at 1.25R, so the stop never left 1912.55354 and the
    #   trade finished at a full loss. It only survived in the shipped configuration because the
    #   FLIPPED ladder happened to put a rung at 0.757R; it was protected by an accident of
    #   geometry rather than by a rule. Aaron, 2026-08-25: *"we were up so much money and we just
    #   leave SL at its original SL? that is dumb."*
    #
    #   ⚠ EVERY trade, primary and re-entry alike — `exec_rec_be_r` is the reclaim-only ancestor of
    #   this and is left exactly as it was, because its numbers were measured on it.
    #   ⚠ Read against `_sl`, the FROZEN entry stop, so "1R" keeps meaning the risk the trade was
    #   SIZED against. Reading the managed stop would shrink the trigger as the stop ratchets.
    #   ⚠ It can only ever TIGHTEN. A touched rung already outranks it (`_current_stop` reaches this
    #   branch only while no stage has fired), and `exec_be_keep_r` is clamped below 1.0 so the
    #   armed stop always sits between the entry and the original stop.
    #   ⚠ Off by default, so `compare_strategy.py` sees the same primary decisions it always did.
    exec_be_keep_r: float = 0.0        # "   ↳ Risk left in the market (R)"
    #   HOW FAR THE ARMED STOP MOVES. 0.0 (default) is breakeven — the stop goes to the entry plus
    #   the usual `exec_be_buf_mode` cushion, so the trade cannot lose. A positive number instead
    #   leaves that share of the trade's own entry risk in the market, so the loss is CUT rather
    #   than erased and the trade keeps room to breathe.
    #   ⚠ A stop exactly at entry sits inside the noise the trade has to survive, which is what
    #   turns winners into scratches — that is the whole trade-off this dial exposes, and where to
    #   set it is a MEASUREMENT rather than a preference.
    #   ⚠ No buffer is added on a partial move: the cushion exists to clear the ENTRY price, and
    #   adding it here would make the kept risk something other than the number configured.
    #   ⚠ Must stay below 1.0 — at 1.0 the "protected" stop is the original stop, i.e. the feature
    #   silently does nothing while reading as switched on.
    #   ⚠ Read ONLY when `exec_be_arm_r` is positive.

    exec_be_buf_mode: str = "Ticks"    # "Breakeven buffer mode"
    #   ∈ {"Ticks", "Fraction of stop", "Fraction of stop + cost"}. WHAT the breakeven buffer is
    #   measured in. "Ticks" (DEFAULT) is the shipped behaviour and reads `exec_be_buf_tk` alone,
    #   so nothing moves until this is changed deliberately.
    #
    #   🔴 The problem the other two modes exist for. `exec_be_buf_tk` is one distance for every
    #   trade, and this strategy's entry stop is not one distance — MEASURED on run 5a5e2174d095
    #   (243 trades, XAUUSD.p M15 2020-01-01..2026-08-23, PU Prime ECN costs charged) the first
    #   target sits a median 1.098R from entry but as little as 0.310R. So the SAME buffer is a
    #   rounding error on a wide-stop trade and most of the way to the target on a tight one.
    #   Both ends of that are wrong, and they fail in opposite directions:
    #     * too small — the exit does not clear the trade's own costs, so a "breakeven" is a small
    #       LOSS. 10 of that run's 46 scratches were losses at the shipped 30 ticks.
    #     * too large — the stop lands at or PAST the target that staged it, so the next bar closes
    #       the trade at a fixed small profit instead of protecting a runner. MEASURED across the
    #       buffer sweep: 0% of trades at 30 ticks, 10% (24 of 243) at 300, 29% (70 of 243) at 600.
    #       That is why the 600-tick rung lost R (136.5R vs 159.1R) while removing 35 scratches —
    #       it stopped being a breakeven stop and became an exit.
    #   "Fraction of stop" replaces the fixed distance with `exec_be_buf_r` × the trade's own entry
    #   risk, so the cushion scales with what the trade is actually risking. "Fraction of stop +
    #   cost" additionally floors it at what this trade has COST so far plus `exec_be_cost_margin_r`
    #   — the only mode that can promise a staged exit is not a loss.
    #   ⚠ Both new modes are clamped by `exec_be_cap_pct` so neither can reach the target.
    exec_be_buf_r: float = 0.20        # "Breakeven buffer (fraction of stop)"
    #   `exec_be_buf_mode` != "Ticks" only. The buffer as a share of the FROZEN entry risk
    #   (|entry − initial stop|), so 0.20 = one fifth of what the trade risked.
    #   ⚠ Measured ceiling on the run above: at 0.20 the staged stop never once landed at or past
    #   the first target across all 243 trades; at 0.35 it did on 5%; at 0.50 on 24%. Above ~0.35
    #   `exec_be_cap_pct` starts doing real work rather than sitting as a backstop.
    exec_be_cost_margin_r: float = 0.05    # "Breakeven cost margin (fraction of stop)"
    #   "Fraction of stop + cost" only. How much the cost FLOOR clears the trade's accrued costs
    #   by, as a share of entry risk. 0 = exactly flat after costs; positive = a staged exit banks
    #   something. This is the "capture a little profit instead of a breakeven" dial.
    exec_be_cap_pct: float = 75.0      # "Breakeven buffer cap (% of the way to the target)"
    #   `exec_be_buf_mode` != "Ticks" only. The staged stop may never sit further than this share
    #   of the entry → staging-target distance. 100 would put the stop ON the rung price just
    #   touched and close the trade there; the cap is what keeps a breakeven stop a PROTECTION
    #   rather than an exit. Measured against the nearer rung (`_stage_rungs()[0]`), so a flipped
    #   re-entry ladder caps against the rung that actually staged the stop.
    exec_be_cost_conflict: str = "Hold stop"   # "When cost exceeds the cap"
    #   ∈ {"Hold stop", "Clamp to cap"}. "Fraction of stop + cost" only, and it decides the one
    #   case where the two rules genuinely disagree: a trade held long enough that its accrued
    #   financing alone is further from entry than `exec_be_cap_pct` allows. MEASURED on the run
    #   above, cost reaches 1.289R of entry risk at the worst — well past any sane cap — driven by
    #   overnight financing (correlation 0.727 with hold time; median $0.020/oz under a day,
    #   $1.704 at 3–7 days, max $5.592).
    #   "Hold stop" (DEFAULT) keeps the PREVIOUS stop and does not stage. No stop position both
    #   covers cost and stays below the target, so the honest answer is that this trade cannot be
    #   protected profitably — say so by leaving the stop where it is rather than moving it to a
    #   price that guarantees a loss.
    #   ⚠ It is re-tested every bar, but do NOT read that as "it will resolve": the cap is fixed
    #   (frozen rung, frozen entry risk) while accrued cost only grows on a LONG, so a conflicted
    #   long stays conflicted for the rest of its life. A SHORT can recover, because gold's swap is
    #   a credit to the short side and its accrued cost can fall back under the cap.
    #   ⚠ The trade is NOT left unprotected either way — stage 2 is untouched, so touching the
    #   second rung still lifts the stop to `exec_tp2_stop_mode`'s floor and hands it to the trail.
    #   "Clamp to cap" stages anyway at the cap, accepting a KNOWN small loss. Cheaper than the
    #   full stop, but it is a stop labelled breakeven that guarantees a loss, which is the exact
    #   thing this whole change exists to remove. Left configurable because it is measurable, not
    #   because it is recommended.
    exec_trail_step: float = 5.0       # "Runner trail step ($ of price)" — Fixed-step mode only
    exec_runner_trail: str = "Structure + % ratchet"   # "Runner trail method"
    #   ∈ {"Fixed step", "Structure (swing)", "Structure + % ratchet"}. How the TP3 runner is
    #   trailed once TP2 fills.
    #   "Fixed step" = the `exec_trail_step` grid ratchet off TP2 (the pre-2026-07-25 behaviour).
    #   "Structure (swing)" = park the stop at the structure engine's last CONFIRMED swing low
    #   (longs) / high (shorts), offset by `exec_struct_trail_buf_tk`. Breathes with the trend,
    #   but the swing is a LAGGING anchor — in a strong leg it ends up far behind, and that gap
    #   IS the runner's give-back.
    #   "Structure + % ratchet" (DEFAULT since 2026-07-28) = the same swing anchor, but the stop
    #   then climbs one `exec_trail_pct`-of-price step per step of favourable move instead of
    #   sitting still. Never LOOSER than the plain structure trail — only equal or tighter.
    exec_struct_trail_buf_tk: float = 20.0  # "Structure trail buffer (ticks)"
    #   Structure mode only. The runner stop sits this many ticks BELOW the confirmed swing low
    #   (long) / ABOVE the swing high (short), so a wick through the swing doesn't clip it.
    exec_trail_pct: float = 1.0        # "Runner ratchet step (% of price)"
    #   "Structure + % ratchet" mode only. A PERCENT of price, not a dollar figure, and that is
    #   the whole point: gold ran 1,500 → 3,400 over the backtest window, so no fixed $ step is
    #   right at both ends ($20 is a 1.3% trail at 1,500 and a 0.6% trail at 3,400 — the dollar
    #   version tops out ~8R below the percent one for exactly this reason).
    #   Measured over 6.6y XAUUSD 15m, vs the plain structure trail: the share of each run actually
    #   banked went 43% → 53% on the SAME 164 trades, same entries, same % max drawdown (54.7%,
    #   identical to the bar). Only 11 exits change — 8 better, 3 worse, net +1.7R, i.e. the EDGE
    #   is unchanged within noise and what improves is how much of each run survives to the close.
    #   Below ~0.5 it starts clipping runners and costs real edge (0.25% → 43.6R vs 109.3R at 1.0).
    exec_tp2_stop_mode: str = "TP1 price"   # "TP2 → stop floor"
    #   ∈ {"TP1 price", "Breakeven", "One trail step behind"}. What the stop FLOOR becomes the
    #   moment TP2 fills, before the runner trail takes over. "TP1 price" (default) snaps the stop
    #   up to TP1; "Breakeven" holds at entry ± the BE buffer (most room); "One trail step behind"
    #   keeps it one `exec_trail_step` under the high-water mark, never below breakeven.
    exec_scale_in: bool = False        # "Add to the runner (scale in)" (Pine execScaleIn)
    #   Add SIZE to a trade the runner trail is already protecting. Every family ever swept on
    #   this strategy before 2026-08-16 was PROTECTIVE (Run 8 alone killed ~50 tightening
    #   variants); this is the first additive one, and a grep for pyramid/scale_in across the
    #   repo returned nothing before it, so there is no prior art here to inherit.
    #   THE RULE, and it is a SIZING rule rather than a timing one:
    #       locked  = (stop - entry) * base_qty     profit the stop already guarantees
    #       per_unit = (price - stop)               what one extra unit risks to that SAME stop
    #       add_qty = locked / per_unit             worst case == the locked profit
    #   Stop out right after adding and the two cancel: the base banks `locked`, the add gives
    #   back at most `locked`, the trade closes at worst flat. An add can shrink a winner; it
    #   cannot manufacture a loser.
    #   🔴 THE TRIGGER IS THE TRAIL (stage 2), NOT A TARGET. At TP2 the stop is only at TP1, so
    #   `locked` is small while `price - stop` is large and the affordable add is a rounding
    #   error. Once the trail ratchets up near price the same arithmetic permits a LARGE add —
    #   so a trending runner buys size and a stalling one buys nothing, with no extra test.
    #   ⚠ ONE STOP FOR THE WHOLE POSITION. Adds are separate LOTS sharing the base's trail, and
    #   `_exit_portion` closes them pro-rata with it. They are lots rather than extra `_qty`
    #   because that method prices the whole position off ONE `_entry`, so growing `_qty` would
    #   value the added units as if bought at the original entry and invent profit.
    #   ⚠ `_entry`, `_risk_usd` and `stop_distance` stay anchored to the BASE fill, so R is still
    #   measured against the original 1R and every row stays comparable to a run with this off.
    #   A scaled trade's "3R" is therefore not 3x the capital an unscaled 3R had at work.
    #   ⚠ THE GUARANTEE HOLDS TO THE STOP, NOT THROUGH A GAP. Price that jumps past the stop
    #   fills the whole combined size at the open, and 3x the size loses 3x. Nothing here
    #   protects against that.
    #   ⚠ NO ACCOUNT-LEVEL CAP EXISTS. Net risk-to-stop is <= 0 by construction, but margin and
    #   `run_stack`'s risk budget both see the FULL position. See docs/LIVE_TRADING_PIPELINE.md
    #   → G10 — the live allocator is unbuilt, so this must not go live before it does.
    #   MEASURED 2026-08-16, XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN costs charged
    #   (`backtest/fills.py` PROFILES["puprime_ecn"], commission $1.00/side/lot, spread $0.12):
    #       off              128.26R  maxDD 6.03R  65 losers  worst -2.06R  ret/DD 21.27
    #       2 adds, cap 1.0x 211.59R  maxDD 8.72R  67 losers  worst -2.06R  ret/DD 24.26
    #   Dropping the affordability test and adding a flat 1x instead cost 11 extra LOSING
    #   trades — that difference is what the `locked / per_unit` line buys.
    exec_scale_mode: str = "Trail"     # "↳ Where it adds" (Pine execScaleMode)
    #   ∈ {"Trail", "BOS retest"}. WHERE the add happens. The SIZE rule above is unchanged by
    #   this — only the moment and the price move.
    #   "Trail" adds at MARKET on the bar the trail ratchets. "BOS retest" waits for the next
    #   confirmed break of structure our way and RESTS A LIMIT at the level that break cleared.
    #
    #   🔴 EVERY RUN 20 NUMBER THAT ONCE STOOD HERE IS VOID, AND THE REASON IS THE ONE WORTH
    #   KEEPING. Run 20 booked each add at the price its RULE TRIGGERED on. Pine buys it
    #   somewhere else — a market order fills at the NEXT BAR'S OPEN, and a resting limit fills
    #   when price comes back. So the harness credited "BOS retest" with the retest level itself
    #   on every fill, which is exactly the price that mode has to WAIT for and often never
    #   gets. It ranked first on that. The parity gate caught it on 2025-10-21 (py 27.07R vs
    #   pine 22.03R) and the ranking INVERTED once the fill was modelled properly.
    #   ⚠ The lesson is not about scaling: A BACKTEST THAT PRICES A FILL AT THE MOMENT ITS RULE
    #   FIRED IS MEASURING A DECISION, NOT A TRADE. Nothing in the output looked wrong — the
    #   equity curve, the trade list and the R figures were all internally consistent.
    #
    #   🔴 RE-MEASURED 2026-08-18 on the corrected fill, 32-cell grid, XAUUSD 15m
    #   2018-09-13 → 2026-08-14, PU Prime ECN costs. Scored on the 2020-FREE book because 2020
    #   is ~1/3 of the all-period figure and scaling roughly TRIPLES its contribution:
    #       no scaling         ALL 128.26R dd 6.03  ret/DD 21.27   EX20  92.51R ret/DD 15.34
    #       Trail 3 x 0.5x     ALL 194.15R dd 7.24  ret/DD 26.81   EX20 124.05R ret/DD 11.99
    #       BOS retest 4 x 2.0 ALL 180.44R dd 9.20  ret/DD 19.61   EX20  80.90R ret/DD  8.79
    #   ⚠ "BOS retest" LOSES MONEY outside 2020 at every budget above one add — down to -14.15R
    #   against not scaling at all. It is kept as an option because it is implemented, gated and
    #   parity-green, NOT because any measurement supports it.
    #   ⚠ NO CELL IN THE GRID BEATS NOT-SCALING'S 2020-FREE ret/DD OF 15.34. Scaling reliably
    #   buys raw return and reliably pays for it in drawdown. "Trail 3 x 0.5x" is the cell where
    #   that trade is closest to fair and the only one better than baseline on BOTH axes over the
    #   full book. Say that plainly rather than quoting the ALL column alone.
    exec_scale_max_adds: int = 3       # "↳ How many times it may add" (Pine execScaleAdds)
    #   A ceiling, not a schedule: the next add is refused until the trail has ratcheted PAST
    #   the stop the last one was sized against. Without that a stalling runner re-adds every
    #   bar against the same locked profit and spends the guarantee several times over.
    #   🔴 IT IS 3 RATHER THAN 4 FOR A SAFETY REASON, NOT A RETURN ONE. At 4 adds the worst
    #   trade goes -2.24R and -2.73R against an un-scaled worst of -2.06R — i.e. the add turned
    #   winners into losers, which is the one thing the affordability rule promises cannot
    #   happen. "Trail" is a MARKET rule, so it still carries the trigger-to-fill gap that the
    #   resting limit closed for "BOS retest". At 3 and below the worst trade never moves.
    exec_scale_cap_x: float = 0.5      # "↳ Biggest add, as a multiple of the original size"
    #   Per-add ceiling as a multiple of the BASE quantity. The affordability rule alone would
    #   sometimes permit 4x or more.
    #   🔴 THIS IS THE DRAWDOWN LEVER, AND IT IS NOT THE ADD COUNT. Same 3 adds, cap alone:
    #       0.5x  EX20 dd 10.34  ret/DD 11.99      2.0x  EX20 dd 22.99  ret/DD 7.21
    #       1.0x  EX20 dd 17.02  ret/DD  8.55      3.0x  EX20 dd 24.56  ret/DD 6.78
    #   Adds are nearly free; SIZE is what hurts. ⚠ Raising it raises margin and gap exposure,
    #   and the profit rule protects against neither — it guarantees only down to the STOP.
    #   ⚠ THE LADDER SHAPE DOES NOT MATTER AND WAS MEASURED RATHER THAN ARGUED (2026-08-18).
    #   At a fixed 1.5x total, big-first (0.75/0.5/0.25) made 199.27R, flat 194.15R, small-first
    #   183.96R — a spread inside this strategy's 15.06R jitter. ⚠ And the intuition that a
    #   later add is riskier because it is further from the ENTRY is wrong here: risk is measured
    #   to the STOP, which trails up behind price, so the LAST add is the cheapest one. Small-
    #   first in fact had the lowest drawdown (9.05 vs 11.04). Flat is kept because it is simpler
    #   and nothing measured argues against it.
    exec_scale_tp_mode: str = "Ride"   # "↳ Where the adds take profit" (execScaleTpMode)
    #   ∈ {"Ride", "Prev week H/L", "Prev day H/L", "H4 H/L"}. WHERE the scale-in lots bank.
    #   "Ride" leaves them on the trailing stop, closing pro-rata with the base ladder — the
    #   behaviour every measurement before 2026-08-19 was taken on. The other three rest the adds
    #   on the nearest STANDING (unmitigated) level of that family beyond the NEWEST add — which
    #   is beyond EVERY add, since scale-ins only fill as price moves in favour, so the newest
    #   lot is always the extreme one. Every lot it closes is therefore closed in profit;
    #   banking one lot at a loss to bank another at a gain is not what this is for.
    #   ⚠ It moves the ADDS ONLY. The base position's stop, TP1 and TP2 are untouched, so with
    #   `exec_scale_in` OFF (the default) this input cannot change a single trade.
    #
    #   🔴 MEASURED 2026-08-19 (Run 22), RE-MEASURED the same day after the resting-order fix
    #   below. XAUUSD 15m 2018-09-13 → 2026-08-14, PU Prime ECN costs, Trail 3 x 0.5x, 182
    #   trades. EVERY TARGET LOSES TO RIDING, in order of how OFTEN the target fires:
    #                       ALL trades       banks    excluding the top 20 trades
    #       scale OFF       128.26R dd 6.03     --     92.51R dd  6.03  ret/dd 15.34
    #       Ride            194.15R dd 7.24      0    124.05R dd 10.34  ret/dd 11.99
    #       Prev week H/L   168.51R dd 7.24     16    114.12R dd  9.73  ret/dd 11.73
    #       Prev day H/L    157.57R dd 7.51     25    111.91R dd  7.72  ret/dd 14.49
    #       H4 H/L          146.09R dd 7.15     47    104.38R dd  7.15  ret/dd 14.60
    #   ⚠ THAT ORDERING IS THE FINDING, not any single row. A control run banking at a flat
    #   multiple of base risk (1R … 8R) produced the same monotonic curve independently, and
    #   banking at 1R (126.76R) came out BELOW never scaling at all. ⚠ The control is UNAFFECTED
    #   by the bug below and still stands: its target is a fixed price off the base entry, with
    #   no level and therefore nothing to mitigate.
    #   🔴 THE TAIL IS THE WHOLE ARGUMENT, and the right-hand column is where you can see it.
    #   Strip the top 20 trades and banking IMPROVES risk-adjusted return — ret/dd 14.49 (day)
    #   and 14.60 (H4) against 11.99 for Ride. So a target really does smooth the ride; it just
    #   pays for that out of the tail, and the tail is where this strategy makes its money.
    #   ⚠ The worst trade is -2.06R in EVERY configuration, target or none. The affordability
    #   rule already prevents an add turning a winner into a loser, so there is no giveback left
    #   for a target to prevent — which was the reason one was asked for in the first place.
    #
    #   🔴 THE TARGET IS RESTED AT THE BAR'S CLOSE AND FILLS ON THE NEXT BAR. That is load-
    #   bearing, not a detail. Resolved from the LIVE bar instead, "Prev day H/L" and "H4 H/L"
    #   banked ZERO times in eight years while resolving 1,804 and 2,438 perfectly valid
    #   targets — because a daily/H4 level dies on a WICK (SWEEP_HIGH/SWEEP_LOW) and the engine
    #   steps BEFORE the strategy sees the bar, so the level was already flagged mitigated on
    #   the exact bar the order would have filled. The target vanished precisely when it was
    #   needed. ⚠ WEEKLY HID IT COMPLETELY: a week level dies on a CLOSE through (BREAK_HIGH/
    #   BREAK_LOW), so it survives the spike that fills it and banked normally throughout — the
    #   one family anybody was looking at was the one family that worked.
    #   ⚠ This is the same one-bar order delay the base ladder already honoured: TradingView
    #   places `strategy.exit(limit=)` at a bar's close and it is live on the NEXT bar. The adds
    #   were the single path that skipped it. See `execution.py::_add_tp_level`.
    #
    #   ✅ SETTLED 2026-08-19: "Ride" (Aaron). It shipped as "Prev week H/L" for one day and the
    #   reversal is the part worth keeping. Aaron picked the target deliberately, wanting certain
    #   money off the runners, and at the cost he was quoted — 4.38R, INSIDE this strategy's
    #   15.06R jitter — "certainty for no measurable cost" was a sound trade. The 4.38R came from
    #   the run with the live-bar bug in it. The true cost is 25.64R, OUTSIDE the jitter, and on
    #   the real number he chose the other way within a minute.
    #
    #   🔴 THE LESSON IS ABOUT THE DECISION, NOT THE DIAL. A wrong measurement does not announce
    #   itself as wrong — it arrives as a REASONABLE-LOOKING NUMBER and quietly buys a decision.
    #   Nothing about "4.38R" looked suspicious; it was small, it was plausible, and it made a
    #   preference cheap. The defect was two layers away in a mitigation flag, and the only
    #   symptom it ever produced at this level was a default nobody would otherwise have picked.
    #   ⚠ So when a measurement is what tips a judgement call, the judgement is only as settled
    #   as the measurement — go back and re-ask it when the number moves, rather than treating
    #   the earlier answer as a decision already made.
    #   ⚠ Session H/L is deliberately NOT an option: it measured worst, and it would need six
    #   more mirrored Pine variables to add. See `signals.py::_TGT_SLOT`.
    #   ⚠ VOID — NEVER RE-MEASURED after the fix: session H/L 159.39R and the daily+wk+H4
    #   combination 161.00R. Both came off the throwaway harness, which carried the same
    #   live-bar flaw. Do not quote them; re-measure if they are ever needed.
    exec_time_stop_mode: str = "Before TP1 only"   # "Time stop" (Pine execTimeStopMode)
    #   ∈ {"Off", "Before TP1 only", "Always"}. Close a position that has been open for
    #   `exec_time_stop_hrs` CALENDAR hours. An EXIT lever, and the only one here driven by the
    #   clock rather than by price.
    #   "Before TP1 only" (the measured shape) fires ONLY while the trade is still at stage 0 —
    #   TP1 has never been touched, so the stop has never staged to breakeven. Touching TP1 makes
    #   the trade immune for the rest of its life, whatever the clock says.
    #   "Always" ignores the stage and closes on the clock alone. Measured DESTRUCTIVE at every
    #   cutoff tested and kept only so the two can be compared; see the ⚠ below.
    #   🔴 **Default "Before TP1 only" at 36h since 2026-08-06 (Aaron's call), so THE BASELINE
    #   MOVED: 159 trades / +137.94R / maxDD 7.99R → 159 / +142.17R / maxDD 5.62R.** It shipped
    #   "Off" for exactly one day, on the standing rule that a stored run must reproduce at
    #   defaults; that protection is now spent, deliberately, exactly as the minimum-stop guard
    #   spent its own the day before. **Pin `exec_time_stop_mode="Off"` explicitly when
    #   reproducing any run measured before 2026-08-06**, or you are replaying a different bot.
    #   ⚠ The drawdown is the case for it, not the R. +4.23R is a quarter of one standard
    #   deviation on this strategy (jitter audit: sd 15.06R), so read the R as flat and the
    #   30% drawdown cut as the result — bought with 6 trades over 6.5 years.
    #
    #   ⚠ **The stage gate is the whole lever, and the data says why.** Over 161 trades
    #   (2020-01-01 → 2026-08-03, run `75ccc776d10c`) the TP1 line splits the book perfectly:
    #   **105 trades reached TP1 and not one of them lost; all 56 that never reached it lost.**
    #   That is structural rather than lucky — touching TP1 stages the stop to breakeven, so a
    #   trade past that line cannot take a full loss. The clock is therefore only ever asked about
    #   trades that are still genuinely at risk.
    #   ⚠ **Do NOT reach for breakeven as the milestone instead. It was measured and it is inert:**
    #   the entry is a RESTING LIMIT, so price is sitting at the entry when it fills and the very
    #   next bar's wick crosses back over it — 161 of 161 trades touch breakeven, median 0.25h
    #   (one bar). By hour 8 the share of losers that have not returned to breakeven is **0%**, so
    #   a breakeven-gated time stop fires on nothing at any usable cutoff.
    #   ⚠ **"Always" cuts winners and losers at nearly the same rate below ~16h**, because losers
    #   die FASTER than winners here (median hold: losers 2.0h, winners 17.8h). The stop is already
    #   the fast exit; the clock can only ever catch the tail that lingers.
    exec_time_stop_hrs: float = 36.0   # "Time stop (hours)"
    #   Calendar hours since the FILL, weekends included — the same clock a swap is charged on, and
    #   the one a reader can check against a chart. Read only when the mode is not "Off".
    #   **MEASURED BY REAL REPLAY over 155,440 M15 bars (2020-01-01 → 2026-08-03), one full
    #   replay per row, at today's shipped defaults** (baseline 159 trades / +137.94R — the
    #   min-stop guard moved it off the 161 / +135.94R of run `75ccc776d10c`):
    #     Off (shipped)          → 159 tr  +137.94R  maxDD 7.99R
    #     Before TP1 only  24h   → 159 tr  +140.21R  maxDD 5.55R  (10 cut)
    #     Before TP1 only  30h   → 159 tr  +142.03R  maxDD 5.38R  ( 7 cut)
    #     Before TP1 only  36h   → 159 tr  +142.17R  maxDD 5.62R  ( 6 cut)  ← this default
    #     Before TP1 only  40h   → 159 tr  +142.58R  maxDD 5.61R  ( 6 cut)
    #     Before TP1 only  48h   → 159 tr  +140.09R  maxDD 7.35R  ( 4 cut)
    #     Always           36h   → 159 tr   +97.32R  maxDD 5.92R  (26 cut)
    #   ⚠ **24h-40h is a PLATEAU, not a spike, and that is the only reason 36 is defensible** —
    #   roughly the same R and drawdown across a 16-hour band describes the trade population
    #   rather than fitting it. 36 sits mid-plateau deliberately.
    #   🔴 **The "Always" row is why the stage gate is the lever and the clock is not: same 36
    #   hours, a THIRD of the edge gone (+137.94R → +97.32R).** It cuts 26 trades where the gated
    #   version cuts 6, and the 20 extra are the winners.
    #   ✅ **The queue effect did NOT materialise, and it was CHECKED rather than assumed — the
    #   trade count is 159 in every row, including the "Always" run that cut 26 trades.** So the
    #   naive re-pricing and the real replay agree to the cent here. ⚠ **That is a fact about THIS
    #   window, not a licence to re-price instead of replaying**: A+ takes ~2 trades a month, so a
    #   slot freed 60 hours early usually contains no setup — whereas an ENTRY-side filter frees
    #   the slot exactly when a setup exists, which is how the min-stop guard's cheap estimate got
    #   its sign wrong (+1.84R estimated, −1.84R replayed).
    #   ⚠ **Do NOT read the +4.23R as edge.** `backtest/tools/jitter_audit.py` measured this
    #   strategy's run-to-run spread at **sd 15.06R**, so it is a quarter of one standard
    #   deviation. **The case for this lever is the DRAWDOWN — 7.99R → 5.62R at 36h (30%), 5.38R
    #   at 30h — bought for R that is indistinguishable from noise, and resting on 6 trades in
    #   6.5 years.** It is not a profit lever.
    exec_no_late_day: bool = True      # "No entries in final hour (16:00-17:00 NY)"
    exec_conf_sz: bool = False         # "Allow Sniper Zone as entry confirmation" (Pine execConfSZ)
    #   Added to `mpc_strategy.pine` 2026-07-21. NOT PORTED YET — the field exists so the toggle is
    #   readable from the export's cfg_bits and `compare_strategy.py` can REFUSE a run made with it
    #   on, rather than silently diffing against logic this bot does not have. Porting it means
    #   reading the Sniper fib (already in the replay stack as `BarState.sniper`) and using its
    #   0.5-0.618 pocket as an entry edge on any leg with no qualifying FVG.
    exec_secondary: bool = True        # "Secondary re-entries" — the fast-feed sniper re-entry
    #   OFF = primary only, one entry per 15m A+ leg (keeps compare_strategy.py parity).
    #   ON (default since 2026-08-07) = also re-enter on the same 15m leg from a faster one. It
    #   NEEDS run_dual and a second, faster feed, which is the whole reason the default matters — see the
    #   "not every path can run it" warning below before assuming a number came from this book.
    #   Full rules: docs/MPC_SOS_FADE_SECONDARY.md. There is NO Pine parity gate for it — the Pine
    #   is only the approximate version — so it is verified visually, not by compare_strategy.py.
    #   ⚠ LAB ONLY. algos/live/bridge.py REFUSES this config: the live runner drives one timeframe
    #   and this needs the fill-clock stream beside the 15m. Turning it on for a live bot is an error, by
    #   design, rather than a silently-ignored setting.
    #   🔴 MEASURED 2026-08-06 over the FULL history and it does NOT earn its place — the entire
    #   case is one trade. 186,274 M15 + 2,744,333 M1 bars (2018-09-14 → 2026-08-05): baseline 180
    #   trades / +139.90R / maxDD 45.6%, secondary ON 190 / +165.46R / maxDD 50.7%. Ten re-entries
    #   in 7.9 years, and 2023-04-03 alone is +27.33R — DELETE IT AND THE OTHER NINE ARE −1.77R,
    #   with the book's average falling BELOW baseline (+0.777 → +0.731 R/trade). It is bought with
    #   drawdown (45.6% → 50.7%). ✅ Zero primaries displaced, and the fill clock is inert with it off
    #   (a control run of run_dual reproduced the baseline's 180 trades exactly) — so those numbers
    #   are the re-entries and nothing else.
    #   ⚠ DEFAULTED ON 2026-08-07 AT AARON'S REQUEST, against that measurement, which is recorded
    #   here rather than quietly reversed: the case for the feature is still one trade. With the
    #   per-setup cap below it is 188 trades / +165.46R / maxDD 45.3%. PIN IT OFF to reproduce any
    #   figure in this repo measured before that date — every one of them is a primary-only book.
    #   🔴 NOT EVERY PATH CAN RUN IT, AND THAT IS THE COST OF THE DEFAULT. `run_dual` has exactly
    #   one caller (`python_runner`'s single-backtest path). `backtest/optimizer.run_sweep` replays
    #   ONE frame, so the optimizer, a sweep and the stress test's pooled sensitivity have no second
    #   stream to give it. Those paths now REFUSE rather than silently replaying a primary-only
    #   book and ranking it beside a baseline that has re-entries — the same call `reprice.py`
    #   makes about `bid_ask_fills`. Turn it off for that run, or wire the fill-clock frame through the sweep.
    #   ⚠ Until 2026-08-06 this had never opened a position on real data at all: run_dual built a 1m
    #   signal missing `last_conf_high`/`last_conf_low`, so the first 1m bar after any fill raised
    #   AttributeError. Any figure predating that fix describes a feature that could not run.
    #   ⚠ It was believed to be un-measurable because this repo's own docs said the broker served
    #   ~35 days of 1m. That was a guess and it is FALSE — real M1 runs back to 2018-09-14.
    #
    #   ✅ RE-MEASURED 2026-08-20 AND THE "ONE TRADE" VERDICT ABOVE NO LONGER DESCRIBES THE SHIPPED
    #   FEATURE — leave it standing, because it describes the shape that was shipped between
    #   2026-08-07 and 2026-08-20 and every figure from that fortnight came off it. Five defaults
    #   moved on 2026-08-20 (`exec_sec_req_div` OFF, `exec_sec_trigger` to the gap, `exec_sec_stop`
    #   to 0.886, `exec_sec_tp_r` 1.25, `exec_sec_tp1_pct` 50, `exec_sec_risk_pct` 50) and the leg
    #   went from 10 re-entries to 54 over the same 7.9 years. 235 trades, primaries +206.20R
    #   unchanged to the decimal, re-entries +27.84R at full weight and +13.92R at the shipped half
    #   weight — and less its single best trade the leg is +7.16R rather than −1.77R. It is STILL
    #   bought with drawdown (51.8% → 60.4% at half weight) and it is still concentrated. What
    #   changed is that it is no longer one trade and a rounding error.
    #   🔴 THE OLD DEFAULT COULD NOT FIRE ON THE BOOK IT SHIPS WITH, which is why it read as
    #   marginal. It demanded a live 15m divergence while the primary arms on a SWEEP — over the
    #   most recent year that produced 0 re-entries in 12 months, not 10 in 7.9 years.

    exec_sec_retrace: float = 0.382    # "Secondary entry retrace" — where the shift limit rests
    #   How far back into the shift leg the re-entry's resting limit sits, as a fib ratio of that leg.
    #   0.382 (default) = the shipped behaviour, byte-identical to the hardcoded constant it replaced.
    #   0.0 = rest AT the leg extreme, i.e. enter ON the structure shift itself rather than waiting for a
    #   pullback. Read ONLY when exec_secondary is on (see __post_init__).
    #   ⚠ IT IS A TRADE-OFF, NOT A FREE KNOB, AND THE TWO HALVES PULL OPPOSITE WAYS. The stop is the
    #   shift leg ORIGIN, so a shallower retrace is a WIDER stop: at 0.382 the stop distance is 0.618
    #   of the leg, at 0.0 it is the whole leg. Smaller number = more setups actually fill (no
    #   pullback required) and every one of them is sized SMALLER for the same risk, with less room
    #   between the entry and the 15m targets it is aiming at. So expect more trades worth less each,
    #   and do not read a change in trade COUNT as the answer.
    #   ⚠ A number rather than a two-way switch on purpose — that is what lets the optimizer sweep
    #   it, the same reasoning as exec_sl_custom.

    exec_sec_once_per_setup: bool = True   # "One re-entry per primary" — cap the cascade
    #   ON (default) = a 15m setup hands out AT MOST ONE re-entry. OFF = the original rule, one per
    #   1-MINUTE leg, which is what let 2024-12-02 take two re-entries off a single structure break
    #   (~100 minutes apart, the second two minutes after the first closed).
    #   ⚠ THE CAP IS PER SETUP, NOT PER LIFETIME. A new break of structure gives a new 15m SOS bar
    #   and re-opens the door, so this limits a cascade rather than retiring the feature.
    #   ✅ MEASURED over the full history (186,366 M15 + 2,745,711 M1 bars), one real replay each:
    #   OFF 190 trades / +165.46R / maxDD 6.53R (50.7%) · ON 188 / +165.46R / maxDD 5.53R (45.3%).
    #   It fires on exactly TWO setups in 7.9 years and removes two trades — 2024-01-16 18:44
    #   (−1.000R) and 2024-12-03 01:51 (+1.000R). ⚠ **The total R is identical to fourteen decimal
    #   places by COINCIDENCE — those two happen to be exactly ∓1R and cancel.** Do not read that as
    #   "capping is free by construction"; on another history the second re-entry could be the big
    #   one. What is not luck is the drawdown: the −1R came out of the middle of the worst losing
    #   stretch, so maxDD improves 6.53R → 5.53R and the capped book is now marginally BETTER than
    #   the primary-only baseline (5.61R) where the uncapped one was clearly worse.
    #   ✅ Zero primaries moved either direction, so this touches re-entries and nothing else.
    #   ⚠ It does NOT rescue the feature. Eight re-entries instead of ten, 2023-04-03 is still
    #   +27.33R of the +25.56R total, and the book's average excluding it is 0.739R against the
    #   baseline's 0.777R. The case for `exec_secondary` is unchanged and is still one trade.
    #   ⚠ Read ONLY when exec_secondary is on — a cap on a feature that never fires is inert, so
    #   the optimizer may sweep it behind an OFF secondary. That is a wasted grid, not an error.

    exec_sec_max_per_setup: int = 1    # "Re-entries allowed per setup"
    #   HOW DEEP THE CASCADE MAY GO on one 15m setup. Read ONLY when `exec_sec_once_per_setup` is
    #   ON — that switch still decides whether there is a per-setup cap at all, and OFF is still
    #   the original "one per 1-MINUTE leg" rule with no ceiling. 1 (default) is byte-identical to
    #   the shipped cap.
    #   ⚠ THE DEAD-LEG RULE SITS UNDER THIS AND IS NOT A COUNT. A re-entry that hits its own
    #   initial stop kills the leg outright whatever this is set to, so raising it lets a cascade
    #   run through SCRATCHES (a re-entry that touched TP1 and was ticked out at breakeven), never
    #   through losses. That is the distinction Aaron asked about: coming back after a scratch and
    #   coming back after a stop-out are different events and only one of them continues.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_be_at: str = "TP1"        # "Secondary moves to breakeven at" ∈ {TP1, TP2}
    #   WHEN A SECONDARY'S STOP JUMPS TO BREAKEVEN. "TP1" (default) is the shared ladder and is
    #   byte-identical to it. "TP2" holds the trade's INITIAL stop until TP2, so a re-entry that
    #   pokes TP1 and pulls back is not ticked out of its own trade at `exec_be_buf_tk`.
    #   ⚠ IT AFFECTS SECONDARIES ONLY — the primary's ladder is untouched, which is what keeps
    #   every stored primary figure and the Pine parity gate valid.
    #   ⚠ MEASURED because three of the seven shipped re-entries exited at EXACTLY +$0.30, the
    #   30-tick breakeven buffer, after touching TP1 — one of them $2.65 past it.

    exec_sec_tp1_pct: float = 50.0     # "Secondary banks at TP1 (%)"
    #   A SECONDARY-ONLY take-profit percentage at TP1. 50.0 (default since 2026-08-20) banks half
    #   the re-entry at `exec_sec_tp_r` and runs the rest. -1.0 restores the pre-2026-08-20 rule,
    #   which inherited `exec_tp1_pct` — shipped at 0, i.e. bank NOTHING and only ratchet the stop
    #   to breakeven.
    #
    #   🔴 THIS IS THE HALF OF THE PAIR THAT TURNS SCRATCHES INTO SOMETHING. MEASURED 2026-08-20,
    #   7.9 years, rung at 1.25R: banking nothing left 15 of 54 re-entries finishing inside the
    #   ±0.15R scratch band; banking half left ZERO scratches, 30 wins and 24 losses, and took the
    #   leg less-its-best-trade from −0.36R to +7.16R. Aaron, same day: *"I read [the scratches]
    #   altogether as wins — price went in my favour and came back. I don't want to make big money
    #   on these. I just want to make something."*
    #   ⚠ READ IT WITH `exec_sec_tp_r`, NEVER ALONE — one sets where the rung is and the other how
    #   much comes off it, and at 0.5R banking half was the WORST run in the sweep (+0.14R).
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_req_m1_dir: bool = False  # "Fill-clock trend must agree"
    #   OFF (default) = the shipped rule, which reads the fill-clock engine's SOS events and ignores its
    #   direction. ON = the fill-clock structure engine's own direction must also match the trade.
    #   It is the fast-feed half of Aaron's question about which chart says "stop taking these" — the 15m
    #   half is already covered, because a 15m shift of structure retires the setup and the arm
    #   dies with it.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_tp_r: float = 1.25        # "Re-entry's first target, in R"
    #   WHERE A RE-ENTRY'S FIRST TARGET SITS, as a multiple of its OWN risk (entry → its stop).
    #   1.25 (default since 2026-08-20) puts the rung at `entry + dir * 1.25 * stop_distance` and
    #   leaves TP2 and the runner exactly where they were. -1.0 restores the pre-2026-08-20 rule,
    #   the 15m 0.5 fib — the same rung the primary uses. How MUCH banks there is `exec_sec_tp1_pct`.
    #
    #   🔴 1.25 WAS PICKED BY A SWEEP, NOT BY EYE, AND THE BEST FIGURE IS NOT THE HEADLINE ONE.
    #   MEASURED 2026-08-20, 7.9 years, gap trigger + 0.886 stop, banking 50% at the rung. Re-entry
    #   R, and the same total with its single best trade removed — the second column is the one that
    #   chose it, because one trade is +20.7R of the whole leg:
    #     rung   0.50R  +0.14R  (less best −5.35R)   |   1.25R  +27.84R  (less best +7.16R)  ← ship
    #     rung   0.75R +22.03R  (less best +4.83R)   |   1.50R  +22.82R  (less best +1.32R)
    #     rung   1.00R +24.43R  (less best +5.63R)   |   2.00R  +22.54R  (less best +0.79R)
    #   Banking NOTHING at the rung (the old shape) scored +29.50R and −0.36R less its best trade —
    #   i.e. the entire leg was one trade, which is the shape this pair of defaults exists to fix.
    #
    #   🔴 THIS EXISTS BECAUSE THE RE-ENTRIES SCRATCH RATHER THAN LOSE, WHICH IS A DIFFERENT
    #   PROBLEM FROM A BAD ENTRY. MEASURED 2026-08-20 over 7.9 years with the gap trigger on: of 54
    #   re-entries, 28 finished inside the ±0.15R scratch band at the 0.886 stop and 34 at the leg
    #   origin — the biggest bucket in every configuration tried. A fast-feed entry gets a fast-feed
    #   stop and is then handed a target set for a 15-minute position, so price moves in its favour
    #   and the breakeven ratchet takes it out before the rung is reached. Aaron, same day: *"I read
    #   [the scratches] altogether as wins — price went in my favour and came back. I don't want to
    #   make big money on these. I just want to make something."* The lever turns a favourable
    #   excursion into a booked one; where to set it is a MEASUREMENT, not a preference.
    #   ⚠ It also moves the BREAKEVEN trigger, because the ratchet fires at stage 1 and stage 1 is
    #   this rung. A nearer target therefore means an earlier breakeven on whatever is left, which
    #   is the opposite of what a runner wants — read it with `exec_sec_tp1_pct` rather than alone.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_tp2_min_x: float = -1.0   # "Re-entry's second target, minimum multiple of the first"
    #   THE SECOND TARGET MAY NEVER SIT NEARER THE ENTRY THAN THIS MULTIPLE OF THE FIRST ONE'S
    #   DISTANCE. -1.0 (default) is OFF and nothing moves. A positive number floors the second rung
    #   at `entry + dir * x * (tp1 - entry)`; the structure level still WINS whenever it is further
    #   out, so this only ever pushes a rung away from the entry, never pulls one in.
    #
    #   🔴 IT EXISTS BECAUSE THE RE-ENTRY LADDER CAN COME OUT BACKWARDS, AND DOES. The first rung
    #   is priced off the trade's OWN risk (`exec_sec_tp_r`) while the second stays the 15m fib it
    #   was armed on — two different rulers, and nothing makes the first the nearer one. MEASURED
    #   2026-08-25 on run `cab44579d74b`, 93 re-entries: **36 came out flipped (39%)**, the fib rung
    #   landed anywhere from 0.198R to 6.732R (median 2.077R), and **32 of 93 sat inside the 1.25R
    #   first rung**. At 0.2R that rung is not a "the move extended" signal at all.
    #
    #   ⚠ WHAT MOVES IS THE TRAIL HAND-OVER, NOT WHERE PROFIT BANKS. The second rung banks
    #   `exec_tp2_pct` — 0 on the shipped ladder — so its only job is to lift the stop floor to the
    #   first rung's price and hand the rest to the runner trail. `exec_sec_tp1_pct` still comes off
    #   at `exec_sec_tp_r` wherever this is set.
    #   ⚠ SECONDARIES ONLY, and that is a parity decision rather than caution: the flip is created
    #   by `exec_sec_tp_r`, which exists nowhere in `mpc_strategy.pine` — the Pine has no re-entry
    #   at all — so `compare_strategy.py` sees the same primary decisions it always did.
    #   ⚠ It does NOT retire `_stage_rungs()`. That sorts the stop LADDER and is what keeps a
    #   flipped trade arming breakeven before the trail; this stops the flip being created. Fixing
    #   the input does not license removing the guard that survived it.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_tp2_x: float = -1.0       # "Re-entry's second target, multiple of the first"
    #   THE SECOND TARGET IS REPLACED OUTRIGHT by this multiple of the FIRST rung's distance.
    #   -1.0 (default) is OFF and the 15m fib stands. A positive number puts the second rung at
    #   `entry + dir * x * (tp1 - entry)` on EVERY re-entry, so the two are in order by
    #   construction and the second one means the same thing on every trade.
    #
    #   🔴 IT IS NOT `exec_sec_tp2_min_x` UNDER A NEW NAME. That one is a FLOOR: the fib WINS
    #   whenever it already sits further out, so it can only ever push a rung away. MEASURED
    #   2026-08-25 and it was noise — 139.09R control against 140.64 / 140.29 / 139.79 / 137.10
    #   at 1.5x / 2.0x / 2.5x / 3.0x, with only 13 of 246 trades moving at all. This one
    #   overrides the fib in BOTH directions, so it also pulls IN the rung that extended to
    #   6.732R, which is the half a floor can never touch.
    #
    #   ⚠ WHAT MOVES IS THE TRAIL HAND-OVER, NOT WHERE PROFIT BANKS. The second rung banks
    #   `exec_tp2_pct` — 0 on the shipped ladder — so its only job is to lift the stop floor to
    #   the first rung's price and hand the rest to the runner trail. `exec_sec_tp1_pct` still
    #   comes off at `exec_sec_tp_r` wherever this is set.
    #   🔴 IT DELAYS BREAKEVEN ON A FLIPPED TRADE, and that is the cost the sweep has to price.
    #   The stop arms stage 1 at whichever rung is NEARER, and on a flipped re-entry that is the
    #   fib — measured as near as 0.198R. Replacing it with a multiple of the first rung moves
    #   stage 1 out to `exec_sec_tp_r`. 2020-11-04 is the worked example: its flipped rung at
    #   0.757R was the only breakeven trigger that trade ever reached, and pushing the second
    #   target away took it from +0.348R to -0.907R.
    #   ⚠ SECONDARIES ONLY, and that is a parity decision rather than caution: the flip is created
    #   by `exec_sec_tp_r`, which exists nowhere in `mpc_strategy.pine` — the Pine has no re-entry
    #   at all — so `compare_strategy.py` sees the same primary decisions it always did.
    #   ⚠ Applied BEFORE `exec_sec_tp2_min_x`, so with both on the floor still floors the REPLACED
    #   level instead of being silently overwritten by it.
    #
    #   MEASURED 2026-08-25, XAUUSD.p M15, 2020-01-01..2026-08-23, PU Prime ECN bid/ask fills +
    #   commission 1.0/side + swap, consistent sizing. Control `34ffef240698` = 139.09R at 53.68%
    #   max drawdown, and it reproduced the earlier control to the penny with this field off.
    #
    #     multiple    totR     maxDD%   trades   note
    #     off        139.09     53.68     246    control
    #     1.10x      142.83     47.95     246    15 moved
    #     1.25x      142.87     47.95     246    15 moved  <- best
    #     1.50x      141.09     49.02     246    14 moved
    #     2.00x      140.29     50.67     246    16 moved
    #     2.50x      139.79     51.11     246    17 moved
    #     3.00x      137.10     51.11     237    book DIVERGES at trade 18
    #     4.00x      136.55     52.85     235    book DIVERGES at trade 18
    #
    #   🔴 THE LAST TWO ROWS ARE NOT TRADE-FOR-TRADE COMPARISONS AND MUST NOT BE READ AS ONE. At
    #   3.0x a re-entry on 2020-09-28 holds long enough to block the setups behind it, so the book
    #   after trade 18 is a DIFFERENT SET OF TRADES — 9 and 11 fewer. With one position slot an
    #   extra hold does not add to the book, it queues in front of it. The 1.1x-2.5x rows all keep
    #   the same 246 entries and are clean.
    #
    #   ⚠ THE GAIN IS SMALL AND THE DRAWDOWN IS THE INTERESTING HALF. +3.78R over 6.5 years off 15
    #   trades is the same order as the floor above, which was called noise for the same reason.
    #   What is NOT noise is that every single arm improved max drawdown, monotonically as the
    #   multiple tightened — 53.68% down to 47.95%. Read it as a drawdown lever that pays for
    #   itself, not as a way to make more money.
    #   🔴 IT COSTS THE 2020-11-04 RE-ENTRY, AT EVERY SETTING TESTED: +0.348R -> -0.907R, and two
    #   others do the same (2021-02-11, 2020-12-28). Those are trades whose swing level was the
    #   NEARER of the two rungs and therefore the only thing that ever armed their breakeven.
    #   Ordering the ladder removes that, which is the honest cost of ordering the ladder.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_fill_tf_min: int = 5      # "Re-entry fill clock (minutes)"
    #   WHICH BAR STREAM THE RE-ENTRY'S RESTING ORDER IS FILLED AGAINST in a backtest. The primary
    #   always replays on 15m; this is the second feed `run_dual` walks alongside it.
    #
    #   🔴 IT IS A MEASUREMENT-ACCURACY KNOB, NOT A STRATEGY ONE. Live, the broker fills a resting
    #   limit at the price that trades — there is no 15-minute anything. A coarser feed simply
    #   fills the order at a worse price than really traded, so it UNDERSTATES, which is the safe
    #   direction. MEASURED 2026-08-21, XAUUSD 2018-09-14 → 2026-08-20, matched basis:
    #     1m  2,804,720 bars  234 trades  +147.56R   (the most faithful)
    #     5m    561,795 bars  234 trades  +145.61R   ← default: 1/5 the data, 1.3% off
    #     15m   187,286 bars  233 trades  +136.36R   (7.6% off — this is where it starts to hurt)
    #   ⚠ **Do not read the 5m default as "the strategy trades on 5m".** Nothing about the setup,
    #   the entry price or the stop is 5-minute; only the simulated fill is.
    #   ⚠ A finer feed also bounds the WINDOW by that timeframe's measured history floor, which is
    #   why 1m is not free even when the machine can afford the bars.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_rest_and_leave: bool = True    # "Rest the re-entry order and leave it"
    #   ON (default since 2026-08-21, Aaron's rule) = once the side arms, the order stays where it
    #   was placed, at the price it was placed at, until the setup that placed it dies (a new break
    #   of structure), the leg is traded or goes dead, or a position opens. *"Once we broke even,
    #   just put the limit there. You don't have to recheck every one minute. What are you
    #   re-checking for?"*
    #   OFF = the pre-2026-08-21 rule: the arm is recomputed from scratch on every bar, so any one
    #   of a dozen gates closing pulls the resting order back off the book.
    #
    #   🔴 THE RE-DECIDING WAS WORTH NOTHING, AND IT IS THE REASON THE 1-MINUTE FEED WAS THERE.
    #   MEASURED 2026-08-21, 7.9 years, gap trigger, matched basis — the ONLY thing that differs
    #   between each pair is this switch:
    #     fill clock 1m :  re-decided 235 trades +147.57R  ·  rested 234 trades +147.56R
    #     fill clock 15m:  re-decided 234 trades +136.38R  ·  rested 233 trades +136.36R
    #   0.02R over 7.9 years, both ways. ⚠ **The 11R between the two ROWS is a different thing and
    #   is not this switch** — it is fill PRECISION (a 15m bar fills a limit at a worse price than
    #   the minute price actually traded at), and it is a measurement-accuracy question, not a
    #   strategy one. Live, the broker fills the resting order at the price that trades; there is
    #   no 15-minute anything. See `exec_secondary`.
    #
    #   ⚠ It freezes the PRICES, not just the flag — the fibs keep extending, and a re-read edge
    #   would slide a resting order to a level it was never placed at, so the trade's own record
    #   would name a price that was never live.
    #   ⚠ NOT byte-identical to OFF: 2 re-entries move and 1 is lost over 7.9 years, so a stored
    #   figure from before this date reproduces only with it set False.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_max_wait_bars: int = 0     # "Cancel a resting re-entry after (fill-clock bars)"
    #   0 (default) = OFF, the shipped rule: once the side arms, the order rests at the price it
    #   was placed at until the setup dies, the leg retires or a position opens — however long that
    #   takes. A positive number cancels it after that many FILL-CLOCK bars without a fill, and the
    #   side may not re-arm on that setup afterwards.
    #
    #   🔴 IT EXISTS BECAUSE THE WAIT IS ITSELF A RISK, AND NOTHING MEASURED IT BEFORE.
    #   Aaron, 2026-08-23, on the 2025-08-19 reclaim: *"the limit was just there held on at the
    #   0.886 — that gave price enough time to break structure internally."* The order is priced on
    #   the setup that armed it, and every bar it waits is a bar that setup gets older while the
    #   price it rests at does not move.
    #   ⚠ **The unit is FILL-CLOCK bars, so it moves with `exec_sec_fill_tf_min`** — 12 is one hour
    #   at the 5-minute default and five hours at 25. It is counted in bars rather than minutes
    #   because that is what the re-entry path is stepped on; a minutes field would silently mean
    #   something different on every fill clock.
    #   ⚠ **It counts bars the order was ALIVE, never bars since the primary closed.** A run's
    #   stored trade list records when an order FILLED and never when it was placed, so the wait
    #   cannot be reconstructed after the fact — which is why this had to be built to be measured.
    #   ⚠ **Read ONLY when `exec_sec_rest_and_leave` is on.** With the order re-decided every bar
    #   there is no single placement to age, and a cancel-after-N would be counting something else.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_risk_pct: float = 50.0    # "Re-entry risk (% of the primary's)"
    #   HOW MUCH A RE-ENTRY RISKS, as a percentage of `exec_risk_pct`. 50.0 (default since
    #   2026-08-20) risks HALF what the primary risks; 100.0 is parity with it, 200.0 double. Sizing is `equity * (exec_risk_pct * this/100) / 100 /
    #   stop_distance`, so it scales the LOT only — entry, stop, targets and every R figure are
    #   untouched, because R is measured against the trade's own risk.
    #
    #   🔴 THIS EXISTS BECAUSE THE RE-ENTRIES DEEPEN THE PRIMARY'S OWN DRAWDOWN RATHER THAN
    #   DIVERSIFYING IT. MEASURED 2026-08-20 over 7.9 years, gap trigger, 0.886 stop, first target
    #   at 1.25R banking 50%: adding 54 re-entries took the worst closed-trade drawdown from
    #   51.8% to 68.1% for +27.8R — return +13%, drawdown +31%, i.e. WORSE per unit of pain
    #   (4.0 R-per-point becomes 3.4). It is the SAME drawdown made deeper, not a new one: both
    #   versions trough in the same 2023-04 → 2024-10 stretch, where the primaries lose 6.3R and
    #   the re-entries lose a further 4.7R. They come off the same setups the primaries just lost
    #   on, so they fail together — the first hard number this repo has on the correlation the
    #   trading-philosophy section has warned about in words.
    #   ⚠ IT SIZES ONLY, IT DOES NOT SELECT. A smaller re-entry still enters and exits on exactly
    #   the same bars, so it cannot fix a bad entry — read a change here as buying drawdown down,
    #   never as improving the edge. The R column is deliberately unchanged for that reason.
    #
    #   🔴 50 WAS NOT CHOSEN OFF THE DRAWDOWN CURVE — THERE IS NO KNEE IN IT. MEASURED 2026-08-20,
    #   same 7.9 years; the R total is IDENTICAL at every size (27.84R) because R is per-trade, so
    #   the account-weighted contribution and the worst closed-trade drawdown are the only columns
    #   that move:
    #     off  —      206.20R  51.8%   |   half   +13.92R  220.12R  60.4%  ← ship
    #     ¼    +6.96R 213.16R  56.2%   |   ¾      +20.88R  227.08R  64.4%
    #     ⅓    +9.19R 215.39R  57.6%   |   full   +27.84R  234.04R  68.1%
    #   Every step buys ~1.6R per extra drawdown point, at a near-constant rate — a straight line
    #   with no natural stopping place, against ~4.0R per point for the primaries alone. So the
    #   size was chosen on CONCENTRATION instead: one trade is +20.68R of the leg's +27.84R, the
    #   next is +6.06R, and the whole thing less its best trade is +7.16R over 54 trades. A leg
    #   leaning that hard on one trade earns a place on the book but not a full weight, because the
    #   day that trade does not arrive you have paid full price for it.
    #   ⚠ THE R FIGURES ABOVE ARE NOT COMPARABLE ACROSS SIZES WITHOUT THE WEIGHTING. A backtest
    #   summary will report the same 27.84R at a quarter size as at full — halving the lot halves
    #   the win and the loss together. Multiply by this field before comparing to a primary's R.
    #   ⚠ Refuses 0 or a negative: zero risk is a trade nobody is in, and the honest way to stop
    #   taking re-entries is `exec_secondary = False`, which also stops the arm doing the work.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_trigger: str = "Reclaim Entry"   # "What triggers a re-entry"
    #   ∈ {Structure shift, Reclaim Entry, FVG in zone, FVG in zone + Reclaim Entry}
    #   WHAT HAS TO HAPPEN before a re-entry rests its order. Four values:
    #     "Structure shift"    — a break of structure on the fill clock inside the zone, then a limit at
    #                   `exec_sec_retrace` of that shift leg. The only rule that existed before
    #                   2026-08-20, and the default until that date.
    #     "FVG in zone" (default since 2026-08-20) — no structure event at all. While the setup
    #                   is alive and price is back in the zone, rest the limit at the PRIMARY's own
    #                   point-of-interest price
    #                   (`Execution._poi_edge_l/_s`, i.e. whatever `_entry_edges` computed for this
    #                   setup under `exec_poi_source` / `exec_fvg_deep_only` / `exec_fib_nearest`).
    #   🔴 THE SECOND MODE RE-USES THE PRIMARY'S EDGE RATHER THAN RE-DERIVING IT. Aaron's rule was
    #   *"follow the rules of fair value gap entry that we would take on a primary trade"* — two
    #   implementations of those rules is how they silently diverge, and this repo has paid for that
    #   four times. It also means every gap toggle keeps ONE meaning across both entries.
    #   ⚠ MEASURED 2026-08-20, the case that prompted it (2025-10-29 long, primary scratched at
    #   breakeven 02:00 on the 30th): the Structure shift did not confirm until 04:10, by which time price
    #   had left; its limit rested at 3931.84 and the lowest price for the next 19 hours was 3939.86,
    #   so it missed by $8.02 while price ran to 4046.22. A gap sat at 3916.47–3922.66, INSIDE the
    #   zone, and price traded into it at 02:59.
    #     "Reclaim Entry" (added 2026-08-20) — the SWEPT-STOP case, and the only trigger of the
    #                   three built for a primary that LOST. The primary is stopped at the deep edge
    #                   (`exec_sec_zone_deep`, the 0.886 by default); price does not go on to break
    #                   the leg but instead trades back up through that level; a limit then rests AT
    #                   the deep edge for the retest. Risk is the deep-edge-to-stop gap, not the
    #                   primary's full stop distance — a median 0.43R of it, so the same cash risk
    #                   buys a ~2.3x position.
    #     "FVG in zone + Reclaim Entry" (added 2026-08-21) — BOTH of the above, live at once.
    #                   See the block below on why that is safe and what it measured.
    #   🔴 THE RECLAIM HALF READS ITS OWN SETTINGS — `exec_rec_*`, NOT `exec_sec_*`. It reads them
    #   under the combined value and under the plain "Reclaim Entry" value alike, so the trigger
    #   means one thing in both. That is what makes the combined mode possible at all: the two
    #   halves want different preconditions, different stops and different ladders, and a single
    #   set of fields can only hold one of each. ⚠ It also means `exec_sec_stop`, `exec_sec_tp_r`,
    #   `exec_sec_tp1_pct` and `exec_sec_require` are DEAD under the plain reclaim value — setting
    #   them there changes nothing, which is why validation refuses the pairing that used to be
    #   required rather than leaving it to look effective.
    #   🔴 THE THIRD MODE WAITS FOR A RETEST AND THAT WAIT IS THE ENTIRE EDGE. MEASURED 2026-08-20
    #   over 7.9 years on the 1m stream, offline against the primary's own stop-outs: a resting
    #   limit back at the level earned +43.0R over 53 re-entries; entering at the reclaim bar's
    #   CLOSE instead earned +0.0R over 56. Same setups, same stop, same target — only the wait
    #   differs. It is not a fill-quality refinement and must not be relaxed into a market entry.
    #   ⚠ IT IGNORES THE ZONE GATE ON PURPOSE. The zone reads the last-closed 15m bar's CLOSE, and a
    #   primary is stopped at the deep edge precisely BY a 15m bar closing through it — so the zone
    #   is usually false at the only moment this trigger could fire. The reclaim is itself the
    #   statement that price is back at the zone's deep edge, which is what the zone was asking.
    #   ⚠ IT NEEDS THE FILL-CLOCK BAR'S HIGH/LOW, which the other two triggers do not. `SecondaryArm.update`
    #   takes them as optional arguments and a caller that omits them gets NO re-entries rather than
    #   a different rule — see the driver in `strategy.py`.
    #   ⚠ Read ONLY when exec_secondary is on.

    # ── The RECLAIM half's own settings ────────────────────────────────────────────────────────
    # Read whenever `exec_sec_trigger` names the reclaim — alone or combined — and ignored
    # otherwise. Their defaults ARE the configuration measured on 2026-08-21 (below), so selecting
    # the trigger and touching nothing else reproduces that book exactly; that equivalence is a
    # test in `tests/test_secondary.py` rather than a claim.
    #
    # 🔴 WHY THE TWO TRIGGERS MAY SHARE ONE POSITION SLOT AND ONE LATCH, WHICH IS THE ONLY REASON
    # THE COMBINED MODE IS NOT A REWRITE: they fire on DISJOINT setups, structurally rather than by
    # luck. A primary either reaches TP1 — which stamps the breakeven latch and can never stamp the
    # loss latch — or closes at stage 0, which does the reverse (`execution.py`, `_finalise_trade`
    # and the stage-1 latch). No setup can satisfy both gates, so at most one half can arm on a
    # side and the shared `_l_leg` / `_traded` / `_dead` / `_used` machinery keeps working untouched.
    # ⚠ THAT ARGUMENT DEPENDS ENTIRELY ON THE TWO PRECONDITIONS BEING DISJOINT, so validation
    # REFUSES any other pairing under the combined value rather than letting the halves race for the
    # latch — a race whose symptom would be a plausible re-entry at the wrong price, not an error.
    # ⚠ MEASURED 2026-08-21 and it is 0 rather than "rare": across the 108 re-entries the two
    # triggers produce over 187,102 M15 bars, ZERO overlap in time, ZERO share an entry stamp, and
    # neither ever blocks a primary. Re-run `overlap.py`-style checks if either gate is loosened.

    exec_rec_require: str = "Stopped only"   # "Reclaim needs the primary to have…"
    #   ∈ {Any close, Breakeven, None, Stopped only} — the same four as `exec_sec_require`, read by
    #   the RECLAIM half only. "Stopped only" is the whole point of the trigger: it re-enters a
    #   setup whose primary was stopped at the deep edge. ⚠ Under the combined value this must stay
    #   "Stopped only" while the gap half stays "Breakeven", or the halves are refused (above).

    exec_rec_stop: str = "1.0"         # "Reclaim stop sits at" ∈ {0.886, 1.0}
    #   ONLY the two 15m fib anchors, and `Shift leg` / `swing low` are refused rather than accepted
    #   and quietly reinterpreted. The reclaim latches no shift leg and its entry is a FIXED price
    #   (the deep edge), so a fill-clock swing can land on either side of the entry — a stop that is
    #   sometimes above and sometimes below the thing it protects is not a stop.
    #   ⚠ "1.0" is the default because the geometry is the reason the trigger exists: the leg origin
    #   sits a median 0.43R past the deep edge, so this is a much tighter stop than the primary's.
    #   ⚠ It is also what lets the arm read this anchor BEFORE the shift leg latch — both legal values
    #   are pure reads of the 15m fib. Do not widen this set without reading that note in
    #   `secondary.py` section 2c.

    exec_rec_tp_r: float = 3.25        # "Reclaim's first target, in R"
    #   -1 = use the 15m 0.5 fib like the primary; a positive number is a multiple of the RECLAIM's
    #   own (much tighter) risk. ⚠ The LADDER below matters as much as the number: MEASURED
    #   2026-08-21 over 7.9 years, all-out at 3x made 6,740x while the shipped bank-half-at-1.25x
    #   ladder made 3,111x — WORSE than taking no re-entry at all (3,582x). A re-entry this tight
    #   has to be allowed to pay for the ones that fail.
    #
    #   🔴 3.0 → 3.25 ON 2026-08-27, and the reason it is not a tuning nudge: the SAME 18 winners
    #   reach both. MEASURED over 47 reclaims (XAUUSD.p M15+M5, 2020-01-01 → 2026-08-23, the live
    #   bot's own stance with every stop rule at never-move), nine targets replayed on one frozen
    #   checkout:
    #     2.00x 13.00R | 2.25x 14.75R | 2.50x 19.50R | 2.75x 24.25R | 3.00x 25.00R
    #     3.25x 29.50R | 3.50x 29.50R | 3.75x 14.75R | 4.00x 13.95R
    #   Going 3.00 → 3.25 changed NO trade's outcome — 18 winners and 29 losers either way, each
    #   winner simply carried 0.25R further, so the +4.50R is not bought from anywhere.
    #   ⚠ 3.50x ties it at 29.50R and is NOT chosen: it has one fewer winner and sits one 0.25x
    #   step from a cliff where four winners vanish and the leg halves. 3.25x keeps twice that
    #   margin for the same money.
    #   ⚠ THE CLIFF RESTS ON FOUR TRADES, so treat its exact position as soft. That it exists is
    #   not soft — 3.75x and 4.00x are both down there.
    #   ⚠ Every losing reclaim in all nine runs came back at exactly -1.0R (one exception at
    #   4.00x). The leg is BINARY — target or full stop, nothing between — which is what lets each
    #   row's total be reconciled from its win count alone. All nine do.

    exec_rec_tp1_pct: float = 100.0    # "Reclaim banks at its first target (%)"
    #   -1 = inherit `exec_tp1_pct`. 100 = the whole position comes off at `exec_rec_tp_r`, which is
    #   the measured configuration and leaves NO runner. ⚠ See the R figures on the field above
    #   before reducing it — half-off measured strictly worse, twice.

    exec_rec_entry_mode: str = "Retest"   # "Reclaim enters" ∈ {Retest, Market}
    #   HOW a reclaim gets in. "Retest" (default) is the shipped path: price sweeps the primary's
    #   stop, trades back through that level, and a limit then RESTS at the level waiting for price
    #   to come back to it. "Market" takes the next fill-clock bar's open instead — worse price,
    #   wider stop, smaller position, but it cannot miss the move.
    #
    #   🔴 IT EXISTS BECAUSE THE WAIT IS WHERE THE SETUP GOES STALE. Aaron, 2026-08-24: "why can't
    #   we re-enter as soon as we lose, like a market execution? It doesn't matter if we get in a
    #   little later." MEASURED 2026-08-23 on run `6e029942cb29`: 29 of 90 re-entry orders waited
    #   over 30 minutes for that return and 8 waited over 12 hours; every one of the 8 lost, and
    #   the 2025-08-19 reclaim that ran +2.98R and missed its target by 7.5 cents is one of them.
    #   ⚠ **THE TRADE-OFF RUNS BOTH WAYS AND MUST BE MEASURED, NOT REASONED.** The stop does NOT
    #   move, so the entry-to-stop distance grows — the position is smaller AND the target, a
    #   multiple of that risk, sits further away in price. A market entry can therefore MISS a
    #   target the retest entry would have banked, on the very same price path.
    #   ⚠ It also changes the trade COUNT, which nothing else tried on this leg does: a reclaim
    #   that arms and runs away without a retest never fills today, and fills every time here.
    #   ⚠ RECLAIMS ONLY. The gap half keeps its resting limit.
    #   ⚠ Read ONLY when exec_secondary is on and the trigger names the reclaim.

    exec_rec_be_r: float = -1.0        # "Reclaim moves to breakeven at (R)"
    #   -1 (default) = OFF, the shipped behaviour: a reclaim's stop does not move at all until its
    #   first target is touched, and because `exec_rec_tp1_pct` is 100 the whole position comes off
    #   there. So a reclaim that runs most of the way to a 3R target and turns around pays the FULL
    #   loss. A positive number moves the stop to breakeven (plus `exec_be_buf_tk`) once the
    #   trade's favourable excursion reaches that multiple of its OWN entry risk, leaving the
    #   target where it is.
    #
    #   🔴 IT EXISTS BECAUSE THE GIVE-BACK IS THE RECLAIM BOOK'S DOMINANT FAILURE, NOT THE ENTRY.
    #   MEASURED 2026-08-23 on run `6e029942cb29` (XAUUSD M15, 2020-01-01 → 2026-08-23, no costs):
    #   of 46 reclaims only 19 ever reach the 3R target, yet the book still makes +30.00R because
    #   each of those pays 3R. Aaron's 2025-08-19 reclaim ran +2.98R and finished −1R, missing its
    #   target by 7.5 cents on gold.
    #   ⚠ **The static estimates below are an UPPER BOUND and must not be quoted as results** — a
    #   breakeven stop sitting at 0.75R can be knocked out by a dip that would have gone on to pay
    #   3R, which a re-score off each trade's favourable extreme cannot see. Replay before trusting:
    #     off (today) +30.00R  |  1.50R +35.00R  |  1.00R +40.00R  |  0.75R +43.00R
    #   ⚠ Read with `exec_rec_tp_r`: pulling the TARGET in was measured strictly worse (a real
    #   replay took the reclaim book 30.00R → 10.25R at 1.25x), so this is the lever that protects
    #   the trade WITHOUT capping the winners that carry the leg.
    #   ⚠ RECLAIMS ONLY. The gap re-entry keeps `exec_sec_be_at`, and the primary's ladder — the
    #   one the Pine parity gate checks — is untouched, which is what keeps every stored primary
    #   figure valid.
    #   ⚠ Read ONLY when exec_secondary is on and the trigger names the reclaim.

    exec_rec_be_keep_r: float = 0.0    # "Reclaim protected stop keeps (R) of risk"
    #   HOW FAR the stop moves when `exec_rec_be_r` arms. 0.0 (default) = all the way to breakeven,
    #   which is the behaviour that field was measured with. A positive number leaves that multiple
    #   of the trade's OWN entry risk still in the market: 0.5 halves the loss instead of erasing
    #   it, so a trade that arms and then turns around pays 0.5R rather than 1R or 0R.
    #
    #   🔴 IT EXISTS BECAUSE ERASING THE RISK ENTIRELY COSTS MORE THAN IT SAVES. Moving a reclaim
    #   to breakeven was replayed on 2026-08-23 and took the reclaim book 30.00R → 20.88R at 0.75R,
    #   20.43R at 1.00R and 23.77R at 1.50R — every one of them WORSE, because a stop sitting
    #   exactly at entry is inside the noise the trade has to survive to reach a 3R target. Keeping
    #   part of the risk moves the stop out of that noise while still cutting the loss.
    #   ⚠ The BUFFER is deliberately not applied to a partial move. `exec_be_buf_tk` is a cushion
    #   around the entry price; a stop already parked a fraction of R away does not need one, and
    #   adding it would make the kept risk something other than the number typed here.
    #   ⚠ Must be under 1.0 — at 1.0 the stop lands on the entry stop and the ratchet does nothing
    #   while reading as switched on, which is the failure shape this repo keeps re-learning.
    #   ⚠ Read ONLY when `exec_rec_be_r` is on. On its own it does nothing at all.

    # ── Each entry method OWNS its pre-rung stop rule (2026-08-27) ──────────────
    # 🔴 THE RULE USED TO BE A LIST WITH A PRECEDENCE ORDER, AND THAT IS WHAT THESE FOUR PAIRS
    # REPLACE. `_current_stop` walked its branches and took the first that matched, so the
    # reclaim's pair — which sits earlier — could OVERWRITE a stop `exec_be_arm_r` had already
    # tightened. MEASURED with `stopwalk.py` on 2026-08-26: entry 100.00, stop 98.00, the general
    # rule arming at 1R and keeping half. At 2.25R in front the stop was 99.00; at 2.50R the
    # reclaim's rule armed and put it back to 98.50. **A protective stop that RETREATS on a
    # winning trade**, which is a defect shape rather than a setting anyone would choose.
    #
    # Aaron, 2026-08-27: *"For all my different entry types, they should have their own take
    # profit and stop loss rules. They shouldn't be, like, a list of stop loss rules, and now I
    # need to go figure out which one has precedence over the other."* So there is now exactly ONE
    # pair per entry method, the trade reads the pair belonging to the method that opened it, and
    # nothing can override anything because nothing else is consulted.
    #
    # ⚠ **The pair is not switchable — its VALUE is.** -1 does not mean "this method has no rule";
    # it means "this method's rule is never move the stop". That distinction is the whole model:
    # switching an entry method on brings its exit rules with it, and they cannot be detached.
    # ⚠ **All four ship at -1 / 0.0, so the ladder is byte-identical to what it was.** Nothing can
    # arm, so `compare_strategy.py` sees exactly the decisions it always did.
    # ⚠ The primary's pair is `exec_be_arm_r` / `exec_be_keep_r`, up in the shared exit block where
    # it has always been. It is the PRIMARY's now, not everyone's — that is the behaviour change.

    exec_gap_be_r: float = -1.0        # "Gap re-entry moves to breakeven at (R)"
    #   -1 (default) = never move the stop, which is what a gap re-entry did before this existed:
    #   it kept its entry stop until a rung was touched. A positive number moves the stop once the
    #   trade's favourable excursion reaches that multiple of its OWN frozen entry risk.
    #   ⚠ GAP RE-ENTRIES ONLY. Before 2026-08-27 this trade read the primary's pair; it no longer
    #   does, so turning the primary's rule on no longer reaches it.
    #   ⚠ NEVER MEASURED ON. No replay has been run with this positive — see the reclaim's numbers
    #   below for how badly a breakeven stop can read before it is measured.
    #   ⚠ Read ONLY when exec_secondary is on and the trigger names the gap.
    exec_gap_be_keep_r: float = 0.0    # "Gap re-entry protected stop keeps (R) of risk"
    #   HOW FAR that stop moves. 0.0 (default) = all the way to breakeven plus the usual cushion.
    #   A positive number leaves that share of the trade's own entry risk in the market, so the
    #   loss is CUT rather than erased and the trade keeps room to breathe.
    #   ⚠ Must stay below 1.0 — at 1.0 the "protected" stop is the original stop, i.e. the rule
    #   silently does nothing while reading as switched on.
    #   ⚠ Read ONLY when `exec_gap_be_r` is positive.

    exec_shift_be_r: float = -1.0      # "Shift re-entry moves to breakeven at (R)"
    #   The same rule, owned by the re-entry that arms off a STRUCTURE SHIFT. -1 (default) = never
    #   move the stop, which is what this trade did before this existed.
    #   ⚠ SHIFT RE-ENTRIES ONLY, and never measured on — same caveat as the gap's.
    #   ⚠ Read ONLY when exec_secondary is on and the trigger is the structure shift.
    exec_shift_be_keep_r: float = 0.0  # "Shift re-entry protected stop keeps (R) of risk"
    #   HOW FAR that stop moves, on the same terms as the gap's.
    #   ⚠ Must stay below 1.0, for the reason given there.
    #   ⚠ Read ONLY when `exec_shift_be_r` is positive.

    exec_sec_stop: str = "0.886"       # "Re-entry stop sits at" ∈ {Shift leg, swing low, 0.886, 1.0}
    #   WHERE THE RE-ENTRY'S STOP GOES. Four values:
    #     "0.886"      (default since 2026-08-20) — the same level the primary stops at (`fibo_p6`).
    #     "Shift leg"     — the shift leg's origin. The default until 2026-08-20, and it only EXISTS
    #                   under the "Structure shift" trigger; pairing it with the gap trigger is refused
    #                   outright below rather than silently falling back.
    #     "swing low"  — the fill-clock engine's last CONFIRMED swing (low for a long, high for a short).
    #     "1.0"        — the 15m leg origin (`fibo_p10`).
    #   ⚠ THE DEFAULT MOVED BECAUSE THE TRIGGER DID, and the two must be read together. The gap
    #   trigger has no shift leg to stop behind, so it needs a 15m anchor; 0.886 is the one the primary
    #   already uses, which keeps one answer to "where does this setup stop out" across both entries.
    #   🔴 STOP PLACEMENT IS NOT A DETAIL HERE AND IT FLIPPED THE SIGN ON THE FIRST CASE MEASURED.
    #   On the 2025-10-29 long, a gap entry at 3922.66 stopped UNDER THE GAP (3916.47) was taken out
    #   two minutes later for a loss; the same entry stopped under the swing low (3915.00 — 98 cents
    #   further) ran to both targets, +16.1R. ⚠ A deeper entry at the gap's far edge measured +88R
    #   on a $1.47 stop and is refused by the minimum-stop floor, which is the floor doing its job.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_req_div: bool = False     # "Re-entry needs a live 15m divergence"
    #   WHETHER A RE-ENTRY ALSO DEMANDS A LIVE 15m RSI DIVERGENCE, on top of the setup being alive
    #   and price being back in the zone. OFF (default since 2026-08-20). ON is the pre-2026-08-20
    #   rule and is byte-identical to the hardcoded `sig.*_div_active` test it replaced — it gates
    #   BOTH the shift leg latch and the arm, because the Pine WIP `f_secArm` tested it in both places
    #   and the port copied it.
    #
    #   🔴 IT IS A DIFFERENT QUESTION FROM `exec_arm_div`, AND THAT IS THE TRAP. The PRIMARY arms
    #   on a sweep or a divergence, whichever `exec_arm_sweep` / `exec_arm_div` allow — shipped, it
    #   is sweep-armed and `exec_arm_div` is OFF. The re-entry then asked for a divergence the
    #   primary was never required to have, so on a sweep-armed book it could not fire at all.
    #   MEASURED 2026-08-20 on run `4fb168fe354f`'s params (XAUUSD 15m, 2025-08-20 → 2026-08-18,
    #   23,530 M15 + 352,348 M1 bars): with `exec_secondary` forced ON and nothing else changed,
    #   **0 re-entries in the year**. On the 2025-12-09 short every other gate passed — the primary
    #   reached breakeven, price closed back in the zone for 433 one-minute bars, the account was
    #   flat, and a bear SOS fired on the fill clock inside the zone at 2025-12-11 01:15 — and the divergence test
    #   alone refused it. Aaron, same day: *"Secondary trades, I don't care about divergence."*
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_require: str = "Breakeven"   # "Secondary needs the primary to have…"
    #   WHAT THE PRIMARY ON THAT 15m LEG MUST HAVE DONE before a re-entry is allowed. Four values:
    #     "Breakeven"   (default) — the primary reached TP1 (the 0.5 fib). The shipped rule, and
    #                   byte-identical to the hardcoded `be_sos == *_sos_bar` test it replaced.
    #     "Any close"   — the primary traded this leg and is now closed, whatever the outcome.
    #     "Stopped only"— the primary traded and closed WITHOUT reaching TP1 (the swept-stop case:
    #                   in at 0.618, stop taken at 0.886, price reclaims and runs without you).
    #     "None"        — no primary required; a live 15m setup is enough.
    #   ⚠ MEASURED before it was shipped, and the four are NOT interchangeable — each changes what
    #   the feature IS, not just how often it fires. See `mpc_sos_fade_optimization.md` → the
    #   secondary loosening grid. The dead-leg rule and `exec_sec_once_per_setup` still bound every
    #   one of them, so a looser gate widens the door rather than removing the cap behind it.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_zone_deep: float = 0.886   # "Secondary zone — deep edge"
    #   The DEEP edge of the 15m retrace zone the re-entry may arm in, as a fib ratio of the 15m
    #   leg. 0.886 (default) reads `fibo_p6` itself, so the shipped path cannot move by a float
    #   rounding step. 1.0 is the leg ORIGIN — it lets the setup arm while the 15m bar has closed
    #   BEYOND the entry band, which is exactly the state a swept stop leaves behind.
    #   ⚠ A deeper edge does NOT move the secondary's stop, which is the shift leg origin either way.
    #   ⚠ Read ONLY when exec_secondary is on.

    exec_sec_zone_shallow: float = 0.618   # "Secondary zone — shallow edge"
    #   The SHALLOW edge of that same zone. 0.618 (default) reads `fibo_p3` itself, same reasoning.
    #   A smaller number (0.5) lets the re-entry arm after price has already reclaimed part of the
    #   move — more door time, and a worse price relative to the 15m targets.
    #   ⚠ Read ONLY when exec_secondary is on.

    # ── GRP_STATS — the one decision-affecting stats input (4194) ───────────────
    exec_scratch_r: float = 0.15       # "Scratch band (R)" — grades a closed trade WIN/LOSS/SCRATCH

    # ── Alerts only — NOT a Pine input and NOT a trade decision (2026-08-14) ────────
    alert_resting_fib: float = 0.236   # "Announce a resting limit at fib"
    #   How far price must retrace before the signals channel announces that a limit is
    #   PENDING. Aaron, on a live message: *"I only want to know a limit is pending when price
    #   gets back to 23.6% of the retracement."* The order itself is placed the moment the setup
    #   arms — this changes only WHEN a human is told about it.
    #
    #   ⚠ **REPORTING ONLY, and there is no Pine counterpart on purpose.** It is read by
    #   `Execution._announce_ready` and by nothing that places, prices or cancels an order, so
    #   `compare_strategy.py` is structurally unaffected — the same standing as `Trade.mfe_usd`
    #   and the whole missed-setup layer. It is deliberately NOT in the `exec_` namespace, so a
    #   reader scanning for trade-affecting dials does not have to check it.
    #
    #   🔴 **It MUST stay shallower than the 0.5 entry band, and `__post_init__` enforces it.**
    #   Any fill is at 0.5 or deeper, so price cannot reach a fill without crossing this level
    #   first — which is what guarantees a suppressed message always belongs to a setup that
    #   never traded. At 0.5 or deeper that guarantee is gone and a real trade could reach the
    #   trades room having never been signalled, with nothing anywhere reporting the gap.
    #   `backtest/tools/alert_rate.py` is the end-to-end check; re-run it after moving this.

    # ── GRP_APLUS — A+ sequence (156) ───────────────────────────────────────────
    aplus_window: int = 4320           # "Max time: sweep → SOS (minutes)" — staleness backstop

    # ── GRP_DIV — RSI divergence: feeds the veto + the live DIV confluence (169-180) ─
    show_div: bool = True              # "Track RSI Divergence" (Pine showDivInput)
    div_rsi_len: int = 14              # "RSI Length"
    div_pivot_len: int = 5             # "Pivot Width (bars)"
    div_valid_bars: int = 100          # "Divergence valid for (bars)"
    div_veto: bool = True              # "Veto setups on extreme/divergence"
    div_extreme_ob: int = 80           # "Extreme Overbought"
    div_extreme_os: int = 20           # "Extreme Oversold"

    # ── Instrument facts (Layer-B injection, not Pine inputs) ───────────────────
    mintick: float = 0.01              # syminfo.mintick — XAUUSD price tick
    point_value: float = 1.0           # 1.0 of price = 1 unit quote/contract (XAUUSD/most CFDs)

    # ── Deliberate deviations from the Pine (docs/MPC_SOS_FADE_SPEC.md) ─────────────
    # OFF for the parity check (to match the Pine, which holds the runner overnight);
    # ON for real runs. Force-flat all trades `flat_by_close_min` before the daily close.
    flat_by_close: bool = False
    flat_by_close_min: int = 15
    daily_close_hour_ny: int = 17      # gold closes 17:00 New York

    # ── Fill & cost model (A2) — the other deliberate deviation ──────────────────
    # "bar"  = the Pine's own intrabar GUESS, zero costs. The parity harness MUST run this:
    #          compare_strategy.py is only meaningful when both sides see the same information.
    # "tick" = real bid/ask fills (spread + measured slippage) + commission + swap from
    #          `account_profile`. This is what a real backtest runs, and it WILL disagree with
    #          the Pine on ambiguous bars — that is the model improving, not drifting.
    # See backtest/fills.py's module docstring for why both must exist.
    fill_model: str = "bar"            # ∈ {"bar", "tick"}. Parity REQUIRES "bar"; real runs pick "tick".
    # Defaults are the BACKTEST broker — Vantage demo — so a tick run matches the VANTAGE_XAUUSD
    # TradingView feed the strategy is designed against (Aaron: backtest on Vantage, trade live on PU
    # Prime). "vantage_demo" is zero-commission (a demo) with the account's real swap; see
    # backtest/fills.py. The old PU Prime values were "XAUUSD.s" / "puprime_standard".
    account_profile: str = "vantage_demo"   # a key of backtest.fills.PROFILES; used only for "tick"
    symbol: str = "XAUUSD"                   # Vantage broker symbol for the tick pull (no ".s" suffix)

    # ── Loss recovery — a counter-trade after THIS bot loses (LAB ONLY, off by default) ──────
    #
    # The rule, the measurements behind every default here, and the reasons it is NOT a strategy
    # of its own live in `strategies/python/loss_recovery/CLAUDE.md`. This block is the wiring
    # that lets the lab and the Command Center turn it on; the engine is that package.
    #
    # 🔴 **Turning this ON cannot change one A+ trade.** The recovery reads A+'s finished losses
    # and appends its own trades tagged `kind="recovery"`; it never gates, delays or re-sizes an
    # A+ entry. That is deliberate — a lab-only feature that could move the shipped book would
    # put every parity number at the mercy of a toggle. The cost of that choice is stated on
    # `recovery.py::apply` and must not be quietly forgotten: A+ sizes as though the recovery did
    # not exist, so the two share a balance in ONE direction only.
    #
    # ⚠ **No Pine twin exists for this**, so `compare_strategy.py` can never gate it. With the
    # toggle OFF the bot is byte-identical to the gated one — which is why it defaults OFF and
    # why an export made with it ON is not a parity input.
    exec_recovery: bool = False        # "Loss recovery trades"
    #   MEASURED over mpc_sos_fade's 62 real losses, XAUUSD M15 2018-09-14 → 2026-08-14, both
    #   sides charged at puprime_ecn: +18.9R gross to the recovery's own risk, +4.8R scaled onto
    #   the account. It is a SMALL addition, not a second strategy — see the CLAUDE.md before
    #   reading anything into it.
    exec_recovery_risk_frac: float = 0.25   # "  ↳ Size vs a normal trade"
    #   MEASURED by a 5% sweep: 0.25 is the largest size that does not raise max drawdown above
    #   what A+ already runs (48.3% vs 48.8%) and sits at the peak of the efficiency curve. The
    #   curve is flat from 0.20 to 0.55, so this is a plateau rather than a knife edge.
    exec_recovery_lock_at_r: float = 1.0    # "  ↳ Secure the trade at (R)"
    exec_recovery_lock_to_r: float = 1.0    # "  ↳ Move the stop to (R)"
    #   Locking to +1R nets +18.9R at a 70% win rate; moving to plain breakeven instead nets
    #   +9.5R at 54%. Breakeven protects you from losing, it does not bank the thing you entered
    #   for. +1R is the moment the original loss is paid back, which is the whole idea.
    exec_recovery_soft_stop_r: float = 0.0  # "  ↳ Cut early at (R against), 0 = off"
    #   0 keeps the structural stop, which is what every number above was measured on. Anything
    #   from 0.25 to 1.0 lands inside a measured plateau (+12.9R to +18.5R against a run-to-run
    #   jitter of 15.06R), so cutting early is FREE rather than better: what it actually buys is
    #   a smaller average loss (-1.01R → -0.30R), paid for in win rate (58% → 37%).
    #   ⚠ Below 0.25 it collapses. This is a float because it is a fraction of R, not a switch.
    exec_recovery_both_dirs: bool = True    # "  ↳ Take both directions"
    #   🔴 Setting this False is a FITTED choice, not a tuning one: counter-longs made +18.9R and
    #   counter-shorts -2.9R on this exact record, so "longs only" is a rule picked after seeing
    #   the answer. Leaving it True is what removes that.
    exec_recovery_max_days: float = 30.0    # "  ↳ Give up after (days)"
    #   A BACKSTOP, not a working rule — 30/60/90 days return the identical book because the
    #   median hold is 4 days. It exists because an earlier version left trades open 130+ days
    #   and paid -8.66R of swap on one that made +1.25R.


    # ── the SHORT-HOLD variant (2026-08-24) ──────────────────────────────────────
    # A second way of trading the SAME A+ setups: take them for a fixed, small number of R and
    # close, instead of banking a little and riding the rest. It exists because the runner's whole
    # result lives in a tail — MEASURED 2026-08-24, the setups that reach the 0.5-0.886 band with
    # every confluence but a gap need an 8R-to-12R target before any rule on them turns positive,
    # and every fixed target from 0.5R to 2R loses. The three fields below are the three pieces of
    # a short-hold rule that were NOT already settings.
    #
    # 🔴 **EVERY FIELD HERE IS READ ONLY WHEN `exec_short_hold` IS ON, and the shipped run is
    # byte-identical with it off** — 158 trades, +130.8R over 2020-01-01 → 2026-08-06 on the ECN
    # tier, diffed on every decision field rather than on the count and the total (a run that
    # RESHUFFLES which setups it took agrees with the old one on both of those).
    #
    # ⚠ **The variant was measured as MARGINAL and is off for that reason, not because it is
    # unfinished.** The best real replay of this pool made +22.5R over 109 trades in 6.6 years at
    # +0.207R each, against A+'s +130.8R over 158 — and it was NEGATIVE from 2024 onward (+34.6R
    # over 2020-2023, -12.0R over 2024-2026). Stacking it under A+ on one account raised the end
    # balance and made the drawdown DEEPER (-50% → -56% at 2.5%), with days-under-water no better
    # at any weight. **It is a switch to experiment with, not a leg to deploy.** Full numbers:
    # `backtest/tools/nogap_scalp_audit.py`, `ob_leg_replay.py`, `drawdown_fill.py`.
    exec_short_hold: bool = False      # "Short-hold variant"

    exec_sh_max_depth: float = 1.0     # "↳ Refuse an entry deeper than this fib"
    #   WHERE THE LIMIT MAY NOT REST. A setup whose entry edge sits deeper into the retrace than
    #   this fib is REFUSED — not moved shallower. Moving it would be a different trade with a
    #   different stop distance and a different R, and this repo has the standing rule that a
    #   resized order is not the trade the strategy is holding. 1.0 is the leg origin, i.e. refuse
    #   nothing, so the field ships INERT.
    #
    #   🔴 **IT SHIPS INERT BECAUSE THE CAP MEASURED NEGATIVE, AND THAT REVERSED THE
    #   RECOMMENDATION THIS FIELD WAS BUILT ON. Read this before setting it.**
    #
    #   The case FOR a 0.702 cap was strong and came from three independent readings. In the real
    #   replay of this pool under the A+ exit rules (2026-08-24, 2020-01-01 → 2026-08-06, ECN):
    #       0.5  - 0.618   74 trades   +0.31R each
    #       0.618- 0.702   14 trades   +0.97R each
    #       0.702- 0.786   10 trades   -0.53R each
    #       deeper          6 trades   -1.42R each
    #   The same dead band shows in the SHIPPED A+ book, which nothing here fitted: A+'s own 28
    #   trades resting in 0.702-0.786 make +0.23R each against +1.50 and +2.42 either side.
    #
    #   Then the cap was APPLIED, on a matched basis, and it cost money:
    #       cap 0.702   104 trades   +10.4R   -10.2R worst drawdown
    #       cap 1.0     109 trades   +12.5R    -9.6R worst drawdown
    #   Five trades removed, 2.1R and a slightly worse drawdown for it.
    #
    #   ⚠ **The split was measured under one exit rule and the cap was applied under another, and
    #   that is the whole lesson.** Deep entries lose when they are ridden — a deep entry has a
    #   short stop distance and the fib ladder's breakeven ratchet takes it out. Closed at a fixed
    #   2R they are fine. **A finding is scoped to the regime it was measured in, and carrying it
    #   across an exit change is a new claim that needs its own run.** Nothing here was wrong when
    #   it was measured; it was generalised one step too far.
    #   ⚠ **It is a FIB RATIO, not a price**, judged against the same leg the stop is priced off,
    #   so it travels with the leg instead of meaning something different on every setup.
    #   ⚠ Read ONLY when exec_short_hold is on.

    exec_sh_tp_r: float = 2.0          # "↳ Close the position at this many R"
    #   THE WHOLE POSITION COMES OFF HERE, replacing the fib TP ladder for this trade. Priced off
    #   the entry's own risk at the fill, the same way the re-entry path prices its first rung —
    #   one convention for "a target in R", not two.
    #
    #   ⚠ **The fib ladder is what makes the runner scratch on this pool, which is why a short-hold
    #   rule cannot simply reuse it.** MEASURED 2026-08-24: of 134 block-leg trades under the A+
    #   exits, 37 reached the first rung, moved the stop to entry and came back for nothing.
    #   ⚠ 2.0 is the measured best of 0.5/0.75/1.0/1.25/1.5/2.0/2.5/3.0R on the filtered pool, and
    #   the first target on the unfiltered pool that is not a loss. Below 1.5R nothing works: the
    #   hit rate never clears the 50% a 1:1 needs.
    #   ⚠ Read ONLY when exec_short_hold is on.

    exec_sh_tp1_pct: float = 100.0     # "↳ How much comes off at that target"
    #   100 = the whole position, no runner, which is the point of the variant. Below 100 leaves a
    #   remainder to the existing runner machinery and the trade stops being short-hold.
    #   ⚠ Read ONLY when exec_short_hold is on.

    exec_sh_block_from: int = -1       # "↳ Block entries from this New York hour"
    exec_sh_block_to: int = -1         # "↳ ...until this one"
    #   A SECOND time window, on top of the final-hour rule, half-open [from, to) in New York
    #   hours. Both -1 means off, which is the default.
    #
    #   🔴 **OFF BY DEFAULT BECAUSE IT IS THE ONE FINDING HERE WITH NO MECHANISM BEHIND IT.** The
    #   hour-by-hour table put 10:00 and 11:00 New York at 15.4% and 8.3% reaching 1R against a
    #   37.7% base, and excluding 10:00-12:00 was worth roughly a third of the filtered pool's
    #   result — but that is a bucket of 25 setups picked out of a table of 24 hours AFTER looking
    #   at it, which is the shape of an artefact. The order-block filter beside it has a reason
    #   that predates the data; this one does not. **Set it deliberately or leave it alone.**
    #   ⚠ Read ONLY when exec_short_hold is on.

    def __post_init__(self) -> None:
        """Refuse a Custom SL ratio outside (0, 1.0], and a time stop of 0 hours — LOUDLY,
        at construction.

        The alternative was the shape `_sl_anchor` already had for an unrecognised level: fall
        through to fib 1.0. That is the wrong answer for a number a human typed. A silent
        substitution here would run a full backtest against a stop the operator did not choose
        and report it as theirs — the same class of defect as the lab charging costs it never
        applied. Failing the run states the problem instead.

        Both are validated ONLY when the mode reads the field. The optimizer can sweep
        `exec_sl_custom` while `exec_sl_level` is a fixed level, or `exec_time_stop_hrs` while
        the time stop is Off; every combo is then identical and inert, which is a wasted sweep
        but not an error, and raising on it would kill an otherwise valid grid.
        """
        if self.exec_short_hold:
            # Validated ONLY when the variant is on, the same way the re-entry and recovery knobs
            # are: an optimizer may sweep one of these while the toggle is fixed off, and every
            # combination is then inert — a wasted sweep, not an error.
            if not 0.0 < self.exec_sh_max_depth <= 1.0:
                raise ValueError(
                    f"exec_sh_max_depth is a fib RATIO on the entry's own leg and must sit in "
                    f"(0, 1], got {self.exec_sh_max_depth!r}. 1.0 is the leg origin, i.e. refuse "
                    "nothing; there is no 'off' value because exec_short_hold=False is that.")
            if not self.exec_sh_tp_r > 0:
                raise ValueError(
                    f"exec_sh_tp_r must be a positive R multiple, got {self.exec_sh_tp_r!r}. "
                    "Zero would put the target ON the entry, which fills instantly for nothing.")
            if not 0.0 < self.exec_sh_tp1_pct <= 100.0:
                raise ValueError(
                    f"exec_sh_tp1_pct must sit in (0, 100], got {self.exec_sh_tp1_pct!r}. Zero "
                    "banks nothing at the target, which is the runner this variant replaces.")
            hours = (self.exec_sh_block_from, self.exec_sh_block_to)
            if hours != (-1, -1):
                # Refuse a HALF-set window rather than reading the set half. One hour filled in
                # and the other left at -1 is somebody who meant to configure this and stopped,
                # and silently blocking 10:00 to -1 is a window nobody asked for.
                if not all(0 <= h <= 23 for h in hours):
                    raise ValueError(
                        f"exec_sh_block_from / exec_sh_block_to must both be -1 (off) or both be "
                        f"New York hours in 0-23, got {hours!r}.")
                if self.exec_sh_block_from == self.exec_sh_block_to:
                    raise ValueError(
                        f"exec_sh_block_from and exec_sh_block_to are both {hours[0]!r}, which is "
                        "an empty window. Set them to -1 to mean off — one way to say a thing.")
        if self.exec_recovery:
            # Validated ONLY when the feature is on, matching how `exec_sl_custom` and
            # `exec_time_stop_hrs` are treated here: an optimizer may sweep a recovery knob
            # while the toggle is fixed off, and every combo is then inert — a wasted sweep,
            # not an error. Refusing there would kill an otherwise valid grid.
            if not self.exec_recovery_risk_frac > 0.0:
                raise ValueError(
                    f"exec_recovery_risk_frac must be positive, got "
                    f"{self.exec_recovery_risk_frac!r}. 0 means 'do not trade it', which is what "
                    "exec_recovery=False says — one way to express a thing, not two."
                )
            if self.exec_recovery_lock_to_r > self.exec_recovery_lock_at_r:
                raise ValueError(
                    f"exec_recovery_lock_to_r ({self.exec_recovery_lock_to_r}) cannot exceed "
                    f"exec_recovery_lock_at_r ({self.exec_recovery_lock_at_r}) — the stop cannot "
                    "be placed beyond a price the trade has not reached."
                )
            if not 0.0 <= self.exec_recovery_soft_stop_r <= 1.0:
                raise ValueError(
                    f"exec_recovery_soft_stop_r must be in [0, 1.0], got "
                    f"{self.exec_recovery_soft_stop_r!r}. 0 is off (keep the structural stop); "
                    "above 1.0 it sits BEYOND that stop and can never fire, which is a knob that "
                    "reads as set and does nothing."
                )
            if not self.exec_recovery_max_days > 0.0:
                raise ValueError(
                    f"exec_recovery_max_days must be positive, got "
                    f"{self.exec_recovery_max_days!r}. 0 would close every recovery trade on the "
                    "bar after its fill, which is not 'no time limit'."
                )
        if not 0.0 < self.alert_resting_fib < 0.5:
            # 🔴 Not a style rule. The whole safety property of this gate is that 0.236 is
            # SHALLOWER than the 0.5 entry band, so every fill must cross it — which is what
            # makes a suppressed message provably a setup that never traded. At 0.5 or deeper a
            # real trade could arrive in the trades room having never been announced, and
            # nothing anywhere would report the missing message. Refuse rather than clamp: a
            # silently adjusted value would run under a rule the operator did not choose.
            raise ValueError(
                f"alert_resting_fib must be in (0, 0.5) — shallower than the 0.5 entry band, so "
                f"that price cannot fill without crossing it first. Got "
                f"{self.alert_resting_fib!r}."
            )
        if self.exec_time_stop_mode not in _TIME_STOP_MODES:
            raise ValueError(
                f"exec_time_stop_mode must be one of {sorted(_TIME_STOP_MODES)!r}, "
                f"got {self.exec_time_stop_mode!r}. An unrecognised mode would fall through to "
                "no time stop at all, which is a different backtest wearing the operator's label."
            )
        if self.exec_time_stop_mode != "Off" and not self.exec_time_stop_hrs > 0.0:
            # 0 hours is not "off" — it would close every position on the bar after its fill.
            # "Off" is a MODE, deliberately, so that turning the lever off and setting its
            # threshold to nothing can never be the same keystroke.
            raise ValueError(
                f"exec_time_stop_hrs must be > 0 when exec_time_stop_mode is "
                f"{self.exec_time_stop_mode!r}, got {self.exec_time_stop_hrs!r}. "
                "Set exec_time_stop_mode='Off' to disable the time stop."
            )
        if self.exec_nogap_arm not in _NOGAP_ARMS:
            # Validated ALWAYS, not only when `exec_req_fvg` is False — unlike the two below.
            # Those are numbers whose mode may legitimately be off during a sweep; this is a
            # closed set of strings, and an unrecognised one has no inert reading: the gate would
            # match nothing and refuse every no-FVG setup, which is indistinguishable on the page
            # from the feature being switched off. A typo would silently be the safest-looking
            # answer available.
            raise ValueError(
                f"exec_nogap_arm must be one of {sorted(_NOGAP_ARMS)!r}, got "
                f"{self.exec_nogap_arm!r}. It gates the no-FVG fallback entry and is read only "
                "when exec_req_fvg is False."
            )
        if self.exec_secondary and self.exec_sec_max_per_setup < 1:
            # 0 would be "a cap of none", which reads as unlimited and means the opposite. The
            # switch for no cap is `exec_sec_once_per_setup = False`, and having two ways to say it
            # is how the two drift apart.
            raise ValueError(
                f"exec_sec_max_per_setup must be >= 1, got {self.exec_sec_max_per_setup!r}. "
                "Switch exec_sec_once_per_setup OFF for an uncapped cascade.")
        if not (self.exec_be_arm_r == -1.0 or self.exec_be_arm_r > 0):
            # Refuse rather than clamp. Zero would arm the moment the trade opened, before price
            # had moved at all, and a negative multiple is a stop on the losing side of the entry.
            raise ValueError(
                f"exec_be_arm_r must be -1 (off) or a positive R multiple, got "
                f"{self.exec_be_arm_r!r}. Zero would protect a trade that has not moved.")
        if not 0.0 <= self.exec_be_keep_r < 1.0:
            raise ValueError(
                f"exec_be_keep_r must sit in [0, 1), got {self.exec_be_keep_r!r}. At 1.0 the "
                f"'protected' stop IS the original stop, so the feature would read as switched "
                f"on and change nothing.")
        if self.exec_secondary and not (self.exec_sec_tp_r == -1.0 or self.exec_sec_tp_r > 0):
            raise ValueError(
                f"exec_sec_tp_r must be -1 (use the 15m 0.5 fib) or a positive R multiple, got "
                f"{self.exec_sec_tp_r!r}. Zero would put the first target ON the entry.")
        if self.exec_secondary and not (
                self.exec_sec_tp2_min_x == -1.0 or self.exec_sec_tp2_min_x > 1.0):
            # Refuse rather than clamp. At or below 1.0 the floor is at or INSIDE the first rung,
            # so it either does nothing or permits the very flip it exists to stop — and a setting
            # that silently accepts a value it cannot honour is how a run gets measured on a
            # configuration nobody chose.
            raise ValueError(
                f"exec_sec_tp2_min_x must be -1 (off) or greater than 1.0, got "
                f"{self.exec_sec_tp2_min_x!r}. A multiple of 1.0 or less would put the second "
                f"target at or inside the first, which is the flip this setting exists to stop.")
        if self.exec_secondary and not (
                self.exec_sec_tp2_x == -1.0 or self.exec_sec_tp2_x > 1.0):
            # Refuse rather than clamp, same reasoning as the floor above. At or below 1.0 the
            # replacement puts the second rung ON or INSIDE the first, which is the very flip the
            # setting exists to remove — and a setting that quietly accepts a value it cannot
            # honour is how a run gets measured on a configuration nobody chose.
            raise ValueError(
                f"exec_sec_tp2_x must be -1 (off, keep the 15m fib) or greater than 1.0, got "
                f"{self.exec_sec_tp2_x!r}. A multiple of 1.0 or less would put the second target "
                f"at or inside the first, which is the flip this setting exists to remove.")
        if self.exec_secondary and not self.exec_sec_risk_pct > 0:
            # Refuse rather than clamp to a floor. Zero (or negative) risk sizes a lot of zero,
            # which fills, closes and lands in the trade list at 0R — a trade that looks taken and
            # moved nothing. "Stop taking re-entries" is exec_secondary = False.
            raise ValueError(
                f"exec_sec_risk_pct must be a positive percentage of the primary's risk, got "
                f"{self.exec_sec_risk_pct!r}. Switch exec_secondary OFF to stop taking re-entries.")
        if self.exec_secondary and self.exec_sec_trigger not in (
                "Structure shift", "FVG in zone", "Reclaim Entry",
                "FVG in zone + Reclaim Entry"):
            # Refuse rather than fall through to the shipped trigger: a typo that silently ran the
            # Structure shift would be indistinguishable, on the page, from the gap trigger finding nothing.
            raise ValueError(
                f"exec_sec_trigger must be one of ['Structure shift', 'Reclaim Entry', "
                f"'FVG in zone', 'FVG in zone + Reclaim Entry'], got "
                f"{self.exec_sec_trigger!r}.")
        if self.exec_secondary and self.exec_sec_stop not in ("Shift leg", "swing low", "0.886", "1.0"):
            raise ValueError(
                f"exec_sec_stop must be one of ['0.886', '1.0', 'Shift leg', 'swing low'], got "
                f"{self.exec_sec_stop!r}.")
        # ── the RECLAIM half's own fields, checked whenever the trigger names it ──────────────
        rec_on = self.exec_secondary and self.exec_sec_trigger in (
            "Reclaim Entry", "FVG in zone + Reclaim Entry")
        gap_on = self.exec_secondary and self.exec_sec_trigger in (
            "FVG in zone", "FVG in zone + Reclaim Entry")
        shift_on = self.exec_secondary and self.exec_sec_trigger == "Structure shift"
        if rec_on and self.exec_rec_stop not in ("0.886", "1.0"):
            # The reclaim latches no shift leg, so "Shift leg" has nothing to read; and it is stricter
            # than the gap trigger about "swing low" because its entry is a FIXED price (the deep
            # edge) — a fill-clock swing can sit on either side of it, and a stop on the wrong side of the
            # entry is a position sized off a negative distance. Refusing names the pair; a
            # fallback would price the trade off an anchor nobody chose.
            raise ValueError(
                f"exec_rec_stop must be '0.886' or '1.0', got {self.exec_rec_stop!r}. The reclaim "
                "latches no shift leg and its entry is a fixed price, so a fill-clock anchor has nothing to "
                "read and could land on either side of the entry.")
        if rec_on and self.exec_rec_require not in (
                "Any close", "Breakeven", "None", "Stopped only"):
            raise ValueError(
                f"exec_rec_require must be one of ['Any close', 'Breakeven', 'None', "
                f"'Stopped only'], got {self.exec_rec_require!r}.")
        if rec_on and not (self.exec_rec_tp_r == -1.0 or self.exec_rec_tp_r > 0):
            raise ValueError(
                f"exec_rec_tp_r must be -1 (use the 15m 0.5 fib) or a positive R multiple, got "
                f"{self.exec_rec_tp_r!r}. Zero would put the first target ON the entry.")
        if rec_on and not (self.exec_rec_tp1_pct == -1.0
                           or 0.0 <= self.exec_rec_tp1_pct <= 100.0):
            raise ValueError(
                f"exec_rec_tp1_pct must be -1 (inherit exec_tp1_pct) or a percentage in [0, 100], "
                f"got {self.exec_rec_tp1_pct!r}.")
        if self.exec_secondary and self.exec_sec_max_wait_bars < 0:
            raise ValueError(
                f"exec_sec_max_wait_bars must be 0 (never cancel) or a positive number of "
                f"fill-clock bars, got {self.exec_sec_max_wait_bars!r}.")
        if (self.exec_secondary and self.exec_sec_max_wait_bars > 0
                and not self.exec_sec_rest_and_leave):
            raise ValueError(
                "exec_sec_max_wait_bars needs exec_sec_rest_and_leave on. With the order "
                "re-decided every bar there is no single placement to age, so the cancel would "
                "read as working while counting something else.")
        if rec_on and not (self.exec_rec_be_r == -1.0 or self.exec_rec_be_r > 0):
            raise ValueError(
                f"exec_rec_be_r must be -1 (off) or a positive R multiple, got "
                f"{self.exec_rec_be_r!r}. Zero would arm breakeven at the entry price, which is "
                f"already where the stop would go.")
        if rec_on and self.exec_rec_entry_mode not in ("Retest", "Market"):
            raise ValueError(
                f"exec_rec_entry_mode must be 'Retest' or 'Market', got "
                f"{self.exec_rec_entry_mode!r}.")
        if rec_on and not (0.0 <= self.exec_rec_be_keep_r < 1.0):
            raise ValueError(
                f"exec_rec_be_keep_r must be at least 0 and under 1, got "
                f"{self.exec_rec_be_keep_r!r}. At 1 the protected stop lands back on the entry "
                f"stop and the ratchet does nothing while reading as switched on; above 1 it "
                f"would LOOSEN the stop.")
        if rec_on and self.exec_rec_be_keep_r > 0 and self.exec_rec_be_r <= 0:
            raise ValueError(
                f"exec_rec_be_keep_r ({self.exec_rec_be_keep_r!r}) needs exec_rec_be_r on. "
                f"Nothing arms the protected stop, so the number would sit in the run's params "
                f"looking like a setting that was tested.")
        if (rec_on and self.exec_rec_be_r > 0 and self.exec_rec_tp_r > 0
                and self.exec_rec_be_r >= self.exec_rec_tp_r):
            raise ValueError(
                f"exec_rec_be_r ({self.exec_rec_be_r!r}) must be nearer than exec_rec_tp_r "
                f"({self.exec_rec_tp_r!r}). At or beyond the target the trade has already banked, "
                f"so the breakeven ratchet could never fire and would read as working.")
        # ── the GAP and SHIFT re-entries' own pairs, on the same terms as the reclaim's ────
        # Each is checked only when its own trigger is the one selected: a number left sitting on
        # a method that cannot fire is not a setting anybody tested, and refusing it here is what
        # stops it reading as one in a run's stored params.
        for _label, _on, _arm, _keep in (
                ("gap", gap_on, self.exec_gap_be_r, self.exec_gap_be_keep_r),
                ("shift", shift_on, self.exec_shift_be_r, self.exec_shift_be_keep_r)):
            if not _on:
                continue
            if not (_arm == -1.0 or _arm > 0):
                raise ValueError(
                    f"exec_{_label}_be_r must be -1 (never move the stop) or a positive R "
                    f"multiple, got {_arm!r}. Zero would arm at the entry price, which is already "
                    f"where the stop would go.")
            if not 0.0 <= _keep < 1.0:
                raise ValueError(
                    f"exec_{_label}_be_keep_r must be at least 0 and under 1, got {_keep!r}. At 1 "
                    f"the protected stop lands back on the entry stop and the rule does nothing "
                    f"while reading as switched on; above 1 it would LOOSEN the stop.")
            if _keep > 0 and _arm <= 0:
                raise ValueError(
                    f"exec_{_label}_be_keep_r ({_keep!r}) needs exec_{_label}_be_r on. Nothing "
                    f"arms the protected stop, so the number would sit in the run's params "
                    f"looking like a setting that was tested.")
        if rec_on and gap_on and not (self.exec_sec_require == "Breakeven"
                                      and self.exec_rec_require == "Stopped only"):
            # 🔴 THE ONLY THING KEEPING THE TWO HALVES OUT OF EACH OTHER'S WAY. They share one
            # position slot and one per-side latch, and that is safe ONLY because no setup can
            # satisfy both gates — a primary either reaches TP1 (breakeven latch) or closes at
            # stage 0 (loss latch), never both. Any other pairing lets them race for the latch,
            # and the symptom is not an error: it is a re-entry resting at the other half's price
            # with the other half's stop, which looks entirely plausible on the page.
            raise ValueError(
                "exec_sec_trigger='FVG in zone + Reclaim Entry' requires "
                "exec_sec_require='Breakeven' (the gap half) and exec_rec_require='Stopped only' "
                f"(the reclaim half), got {self.exec_sec_require!r} and "
                f"{self.exec_rec_require!r}. Those are the only two preconditions that cannot both "
                "be true of one setup, and the halves share a latch.")
        if gap_on and self.exec_sec_stop == "Shift leg":
            # The gap trigger never latches a shift leg, so this pair has no stop at all. Refusing is
            # the only honest answer — a fallback would price the trade off an anchor the operator
            # did not choose, and a silent no-trade would read as "the gap trigger found nothing".
            # ⚠ Reads `gap_on`, so it covers the COMBINED value too: under it the gap half is still
            # the gap trigger and still has no leg to stop behind.
            raise ValueError(
                f"exec_sec_stop='Shift leg' has no meaning under exec_sec_trigger="
                f"{self.exec_sec_trigger!r} — that trigger latches no shift leg. Pick 'swing low', "
                "'0.886' or '1.0'.")
        if self.exec_secondary and self.exec_sec_be_at not in ("TP1", "TP2"):
            raise ValueError(
                f"exec_sec_be_at must be 'TP1' or 'TP2', got {self.exec_sec_be_at!r}.")
        if self.exec_secondary and not (
                self.exec_sec_tp1_pct == -1.0 or 0.0 <= self.exec_sec_tp1_pct <= 100.0):
            raise ValueError(
                f"exec_sec_tp1_pct must be -1 (inherit exec_tp1_pct) or a percentage in "
                f"[0, 100], got {self.exec_sec_tp1_pct!r}.")
        if self.exec_secondary and not (0.0 <= self.exec_sec_retrace < 1.0):
            # 1.0 is the leg ORIGIN, which is where the stop sits — an entry there has a zero stop
            # distance, so the order is cancelled and the feature silently does nothing. Past 1.0
            # the stop is on the wrong side of the entry entirely. Refusing states that; letting it
            # through would report "the secondary took no trades" as though that were a finding.
            raise ValueError(
                f"exec_sec_retrace must be a fib ratio in [0, 1.0), got "
                f"{self.exec_sec_retrace!r}. 0 rests at the shift leg extreme (enter on the SOS "
                "itself); 1.0 is the leg origin, where the stop is."
            )
        # ── breakeven buffer mode ───────────────────────────────────────────────────
        be_modes = ("Ticks", "Fraction of stop", "Fraction of stop + cost")
        if self.exec_be_buf_mode not in be_modes:
            raise ValueError(
                f"exec_be_buf_mode must be one of {be_modes}, got {self.exec_be_buf_mode!r}.")
        if self.exec_be_buf_mode != "Ticks":
            if not (0.0 < self.exec_be_buf_r < 1.0):
                # 0 is a bare breakeven stop, which this mode exists to stop being; 1.0 puts the
                # staged stop a full R past entry, which is past the median first target (1.098R)
                # — i.e. an exit dressed as a protection. Refusing states that rather than letting
                # the cap silently swallow every trade.
                raise ValueError(
                    f"exec_be_buf_r must be above 0 and under 1, got {self.exec_be_buf_r!r}. "
                    f"0 is a bare breakeven (use exec_be_buf_mode='Ticks' with exec_be_buf_tk=0 "
                    f"if that is what you want); 1.0 is a full R past entry, further than the "
                    f"median first target sits.")
            if not (0.0 < self.exec_be_cap_pct < 100.0):
                # 100 puts the stop ON the rung price just touched, which closes the trade there.
                raise ValueError(
                    f"exec_be_cap_pct must be above 0 and under 100, got "
                    f"{self.exec_be_cap_pct!r}. At 100 the staged stop sits on the rung price "
                    f"just touched, so the next bar closes the trade at the target instead of "
                    f"protecting it.")
        if self.exec_be_buf_mode == "Fraction of stop + cost":
            if self.exec_be_cost_margin_r < 0.0:
                # Negative would floor the stop BELOW the trade's costs on purpose — a staged exit
                # that is knowingly a loss, which is the defect this mode exists to remove.
                raise ValueError(
                    f"exec_be_cost_margin_r must be at least 0, got "
                    f"{self.exec_be_cost_margin_r!r}. Negative floors the staged stop below the "
                    f"trade's own costs, i.e. a deliberate loss labelled breakeven.")
            conflicts = ("Hold stop", "Clamp to cap")
            if self.exec_be_cost_conflict not in conflicts:
                raise ValueError(
                    f"exec_be_cost_conflict must be one of {conflicts}, got "
                    f"{self.exec_be_cost_conflict!r}.")

        if self.exec_sl_level != "Custom":
            return
        v = self.exec_sl_custom
        if not (0.0 < v <= 1.0):
            raise ValueError(
                f"exec_sl_custom must be a fib ratio in (0, 1.0], got {v!r}. "
                "0 is the swing extreme (the TP3 side of the entry, so no stop exists there) "
                "and 1.0 is the leg origin, the deepest level the ladder defines."
            )
