"""SosFadeConfig — every input toggle the A+ strategy trades on, with the SAME name
and SAME default as `indicators/strategies/mpc_strategy.pine`.

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
    #   overrides it to True to match `indicators/strategies/mpc_b_leg_strategy.pine`'s own default.
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
    exec_secondary: bool = True        # "Secondary re-entries (1m SOS)" — the 1m sniper re-entry
    #   OFF = primary only, one entry per 15m A+ leg (keeps compare_strategy.py parity).
    #   ON (default since 2026-08-07) = also re-enter on the same 15m leg from the 1m chart. It
    #   NEEDS run_dual and a 1m feed, which is the whole reason the default matters — see the
    #   "not every path can run it" warning below before assuming a number came from this book.
    #   Full rules: docs/MPC_SOS_FADE_SECONDARY.md. There is NO Pine parity gate for it — the Pine
    #   is only the approximate version — so it is verified visually, not by compare_strategy.py.
    #   ⚠ LAB ONLY. algos/live/bridge.py REFUSES this config: the live runner drives one timeframe
    #   and this needs the 1m stream beside the 15m. Turning it on for a live bot is an error, by
    #   design, rather than a silently-ignored setting.
    #   🔴 MEASURED 2026-08-06 over the FULL history and it does NOT earn its place — the entire
    #   case is one trade. 186,274 M15 + 2,744,333 M1 bars (2018-09-14 → 2026-08-05): baseline 180
    #   trades / +139.90R / maxDD 45.6%, secondary ON 190 / +165.46R / maxDD 50.7%. Ten re-entries
    #   in 7.9 years, and 2023-04-03 alone is +27.33R — DELETE IT AND THE OTHER NINE ARE −1.77R,
    #   with the book's average falling BELOW baseline (+0.777 → +0.731 R/trade). It is bought with
    #   drawdown (45.6% → 50.7%). ✅ Zero primaries displaced, and the 1m clock is inert with it off
    #   (a control run of run_dual reproduced the baseline's 180 trades exactly) — so those numbers
    #   are the re-entries and nothing else.
    #   ⚠ DEFAULTED ON 2026-08-07 AT AARON'S REQUEST, against that measurement, which is recorded
    #   here rather than quietly reversed: the case for the feature is still one trade. With the
    #   per-setup cap below it is 188 trades / +165.46R / maxDD 45.3%. PIN IT OFF to reproduce any
    #   figure in this repo measured before that date — every one of them is a primary-only book.
    #   🔴 NOT EVERY PATH CAN RUN IT, AND THAT IS THE COST OF THE DEFAULT. `run_dual` has exactly
    #   one caller (`python_runner`'s single-backtest path). `backtest/optimizer.run_sweep` replays
    #   ONE frame, so the optimizer, a sweep and the stress test's pooled sensitivity have no 1m
    #   stream to give it. Those paths now REFUSE rather than silently replaying a primary-only
    #   book and ranking it beside a baseline that has re-entries — the same call `reprice.py`
    #   makes about `bid_ask_fills`. Turn it off for that run, or wire a 1m frame through the sweep.
    #   ⚠ Until 2026-08-06 this had never opened a position on real data at all: run_dual built a 1m
    #   signal missing `last_conf_high`/`last_conf_low`, so the first 1m bar after any fill raised
    #   AttributeError. Any figure predating that fix describes a feature that could not run.
    #   ⚠ It was believed to be un-measurable because this repo's own docs said the broker served
    #   ~35 days of 1m. That was a guess and it is FALSE — real M1 runs back to 2018-09-14.

    exec_sec_retrace: float = 0.382    # "Secondary entry retrace" — where the 1m limit rests
    #   How far back into the 1m leg the re-entry's resting limit sits, as a fib ratio of that leg.
    #   0.382 (default) = the shipped behaviour, byte-identical to the hardcoded constant it replaced.
    #   0.0 = rest AT the leg extreme, i.e. enter ON the 1m SOS itself rather than waiting for a
    #   pullback. Read ONLY when exec_secondary is on (see __post_init__).
    #   ⚠ IT IS A TRADE-OFF, NOT A FREE KNOB, AND THE TWO HALVES PULL OPPOSITE WAYS. The stop is the
    #   1m leg ORIGIN, so a shallower retrace is a WIDER stop: at 0.382 the stop distance is 0.618
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
        if self.exec_secondary and not (0.0 <= self.exec_sec_retrace < 1.0):
            # 1.0 is the leg ORIGIN, which is where the stop sits — an entry there has a zero stop
            # distance, so the order is cancelled and the feature silently does nothing. Past 1.0
            # the stop is on the wrong side of the entry entirely. Refusing states that; letting it
            # through would report "the secondary took no trades" as though that were a finding.
            raise ValueError(
                f"exec_sec_retrace must be a fib ratio in [0, 1.0), got "
                f"{self.exec_sec_retrace!r}. 0 rests at the 1m leg extreme (enter on the SOS "
                "itself); 1.0 is the leg origin, where the stop is."
            )
        if self.exec_sl_level != "Custom":
            return
        v = self.exec_sl_custom
        if not (0.0 < v <= 1.0):
            raise ValueError(
                f"exec_sl_custom must be a fib ratio in (0, 1.0], got {v!r}. "
                "0 is the swing extreme (the TP3 side of the entry, so no stop exists there) "
                "and 1.0 is the leg origin, the deepest level the ladder defines."
            )
