"""ExtremeLegConfig — every input on `mpc_extreme_leg_strategy.pine`, as a dataclass.

⚠ **NOTHING MAY EXIST HERE WITHOUT A PINE INPUT BEHIND IT.** A field with no input is a setting
the parity gate can never check, because no `cfg_*` column can carry it — the harness would
configure this side from the export and leave that one field at whatever this file happens to say.
The house learned this on `BosConfig` (2026-08-07) and it is the reason the field order below
follows the Pine's own numbered sections rather than any tidier grouping: the two files are read
side by side when one of them changes.

The last block is the exception and is marked as such — those are platform facts (what a lot is
worth, which instrument) that TradingView expresses through the Strategy Properties tab rather than
through an input, so they cannot come from a `cfg_*` column and must not be expected to. Anything
the Pine merely HARDCODES is not in that category and does not belong here at all; see the block
at the bottom for the three that had to be taken back out.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtremeLegConfig:
    # ── 3 · What trades ──────────────────────────────────────────────────────
    exec_longs: bool = True
    exec_shorts: bool = True
    # "Risk % of equity" | "Fixed contracts" — the Pine's `sizeMode`, spelled the same way so the
    # lab's dropdown and the chart's read identically.
    size_mode: str = "Risk % of equity"
    # 🔴 **5.0 SINCE 2026-09-02 — Aaron's explicit call, and it replaces a PLACEHOLDER rather than
    # a measurement.** It read 1.0, the Pine's default, and this package's own notes already said
    # so: *"a per-trade risk of 1.0 in `config.py` is a placeholder, not a measurement — every
    # stacked figure moves with it, and nothing here has chosen it."* Now something has.
    #
    # ⚠ **THE OLD COMMENT'S STATED REASON WAS ALREADY FALSE and that is why this could move.** It
    # said a default disagreeing with the chart would configure the two sides of a parity run
    # differently. It cannot: `compare_extreme_leg.config_from_export` builds the port's config
    # from the export's OWN `cfg_*` columns and says in its docstring that it never reads this
    # side's defaults. So the gate sets this field from whatever the chart was exported at, and
    # this number never participates in it. **A comment that outlives the mechanism it describes
    # is how a free change comes to look expensive.**
    #
    # ⚠ **What it does and does not move.** `_qty` divides by the stop distance with no
    # affordability refusal anywhere, so this scales the LOT and nothing else — the trade list and
    # every R figure in this package's CLAUDE.md are unchanged. What DOES move is every dollar and
    # drawdown-percentage figure, and every STACKED result: the shared-account run that reported
    # zero contention was measured at 5% for BOTH legs against a 10% cap, and the live A+ bot runs
    # at 10%. Two legs at 5% saturate that cap exactly; 10 + 5 does not fit it at all.
    exec_risk_pct: float = 5.0
    fixed_qty: float = 1.0

    # ── 4 · What arms it ─────────────────────────────────────────────────────
    swept_minutes: int = 180
    req_counter_trend: bool = True
    use_h4_level: bool = True
    use_session_level: bool = True
    use_daily_level: bool = True
    use_weekly_level: bool = True
    min_families: int = 1
    skip_friday: bool = True

    # ── 6 · Stop & targets ───────────────────────────────────────────────────
    extreme_minutes: int = 120
    stop_buffer_atr: float = 0.20
    tp_frac: float = 0.5
    use_breakeven: bool = False
    be_arm_frac: float = 0.7

    # ── 7 · Filters ──────────────────────────────────────────────────────────
    min_r: float = 2.0
    min_stop_usd: float = 0.0

    # ── 8 · The two cuts TradingView cannot make (2026-09-02, Aaron's call) ──────────────────
    # 🔴 **THE MARKET CUT SHIPS ON; THE NEWS CUT SHIPS OFF.** They read `engines/regime/` and
    # `engines/news/`, and NEITHER ENGINE HAS A PINE SOURCE — by construction, not by omission.
    # So no `cfg_*` column can carry them and the parity gate can never check them. That is
    # exactly the thing this file's opening rule forbids, and it is allowed here only because the
    # hole is closed at the other end: **`compare_extreme_leg.py` forces both OFF for its
    # comparison** — the configuration every TradingView export is necessarily taken at — and
    # then prints a verdict naming the cut it could not check. A gate that quietly compared a
    # filtered Python against an unfiltered Pine would report a disagreement per refused setup and
    # blame the wrong code.
    #
    # ⚠ **With both off, this side's decision stream is bit-identical to the chart's** — the two
    # checks sit at the END of the refusal ladder, after everything the Pine can also refuse, so
    # a setup the Pine accepts still records the same code here. **That property is what makes
    # forcing them off a valid comparison rather than a convenient one.**
    #
    # ⚠ **Turning one on makes the bot and the chart different strategies.** That is a real cost,
    # not a caveat: the chart stops being a picture of what the bot does.
    #
    # 🔴 **THE MARKET CUT IS ON AS OF 2026-09-02 (Aaron's call), SO THE PARAGRAPH ABOVE IS A LIVE
    # COST RATHER THAN A WARNING: the chart takes 19 trades this side refuses.** MEASURED over
    # 470,995 PU Prime M5 bars 2020-01-01 → 2026-08-23:
    #     132 trades / +57.10R / worst losing run 8.13R   →   113 / +58.53R / worst run 6.00R
    # Better on BOTH counts, which is rare and is the whole reason it was worth the cost. The news
    # cut stays OFF: worse on both (+51.45R, worst run 8.87R) and it could not answer on 51 of the
    # 550 setups it was asked about.
    #
    # ⚠ **YOU DO NOT NEED TO TOGGLE THIS TO RUN THE PARITY GATE, AND YOU MUST NOT.**
    # `compare_extreme_leg.py` forces both cuts OFF for its own comparison — that IS the
    # configuration a TradingView export is taken at, so it is the only correct one — and then
    # prints a verdict naming the cut it could not check. An earlier version REFUSED to run while
    # either was on; it had been written while both were off, so it had never run in the state it
    # existed for, and the minute this line became True it walled all 14 of the gate's own tests
    # and made parity of the shared logic unprovable too. A guard that blocks the work gets
    # bypassed. Story: `CLAUDE.md` → *The two cuts TradingView cannot make*.
    skip_transitioning: bool = True
    skip_news: bool = False
    news_before_min: int = 30
    news_after_min: int = 30

    # ── Platform facts — NOT Pine inputs, and no `cfg_*` column carries them ──
    # These are the Strategy Properties tab and the account behind it. The parity harness leaves
    # every one of them alone; a run that changed one would be comparing two different accounts.
    point_value: float = 1.0
    symbol: str = "XAUUSD"

    # 🔴 THREE CONSTANTS WERE HERE UNTIL THE LAB WAS ACTUALLY ASKED WHAT IT WOULD RENDER, AND THAT
    # IS THE ONLY REASON THEY ARE NOT STILL HERE. `majorLength`, the 15-minute aggregation and
    # `ta.atr(50)` are HARDCODED in the Pine — no input, so no `cfg_*` column and nothing a parity
    # gate could ever check. As config fields they picked up a row on the strategy page each, under
    # their raw field names, and a run that moved one would have diverged from the chart with
    # nothing anywhere to say so. They are now keyword arguments on `MpcExtremeLegStrategy`, which
    # a test can pass and the lab cannot. ⚠ This is the file's own opening rule catching the file:
    # a field with no Pine input behind it is a control the gate is blind to, and the way to find
    # out was to run the scanner rather than to read the registration and agree with it.

    def __post_init__(self) -> None:
        if self.size_mode not in ("Risk % of equity", "Fixed contracts"):
            raise ValueError(
                f"size_mode must be 'Risk % of equity' or 'Fixed contracts', "
                f"got {self.size_mode!r} — spelled exactly as the Pine dropdown spells it"
            )
        # Refuse rather than clamp. A minimum-families setting above the number of families
        # actually switched on can never be satisfied, so the strategy would run, take nothing,
        # and look like a market with no setups in it — the failure shape this repo calls a
        # feature nobody has RUN.
        enabled = sum(
            (self.use_h4_level, self.use_session_level, self.use_daily_level, self.use_weekly_level)
        )
        if self.min_families > enabled:
            raise ValueError(
                f"'Levels that must agree' is {self.min_families} but only {enabled} level "
                f"families are switched on, so nothing can ever arm. Turn a family on or lower "
                f"the requirement — this refuses instead of running silently empty."
            )
        # A blackout window of zero minutes on both sides is a news filter that is switched on and
        # blacks out nothing — it would report as ACTIVE on the strategy page and refuse no setup
        # in eight years. Refuse it: "on but inert" is the shape this repo keeps mistaking for
        # "on and finding nothing".
        if self.skip_news and self.news_before_min <= 0 and self.news_after_min <= 0:
            raise ValueError(
                "the news cut is switched on but its window is zero minutes on both sides, so it "
                "can never refuse anything. Give it a window, or turn it off."
            )
