"""SosFadeConfig — every input toggle the A+ strategy trades on, with the SAME name
and SAME default as `indicators/mpc_strategy.pine`.

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


@dataclass(frozen=True)
class SosFadeConfig:
    # ── GRP_EXEC — Strategy Execution (mpc_strategy.pine 4159-4183) ──────────────
    exec_longs: bool = True            # "Trade Longs"
    exec_shorts: bool = True           # "Trade Shorts"
    exec_aplus: bool = True            # "Trade A+ setups" (Pine execAplus)
    #   On (default) = the A+ reversal sequence arms normally. Off = no A+ entry ever fires —
    #   pair with `exec_bleg` ON in the B-LEG bot to read that setup's results in isolation.
    exec_bleg: bool = False            # "Trade B-Leg setups" (Pine execBLeg)
    #   The A+ bot never trades a B leg, so this stays False here; `mpc_bleg.BLegConfig`
    #   overrides it to True to match `indicators/mpc_b_leg_strategy.pine`'s own default.
    exec_arm_sweep: bool = True        # "Arm on liquidity sweep"  (Stage-1 trigger)
    exec_arm_div: bool = False         # "Arm on RSI divergence"   (Stage-1 trigger)
    exec_req_fvg: bool = True          # "Require FVG overlap in zone"
    exec_fvg_deep_only: bool = True    # "Entry: FVG must sit fully past 0.5"
    exec_deep_fib: bool = True         # "Entry: deep gap enters on nearest fib (not gap edge)"
    #   Method 3 (Pine execDeepFib). OFF (default) = rest the limit at the gap's own edge (current
    #   behaviour, keeps compare_strategy.py parity). ON = when a qualifying gap's NEAR edge sits
    #   deeper than 0.618, rest at the nearest fib just SHALLOWER (0.618/0.702/0.786) — the level
    #   price reaches first — instead of chasing an edge price may never tap. See execution._entry_edges.
    exec_fvg_50: bool = False          # "Entry (least favorable): FVG must touch the 0.5 line"
    #   Added to `mpc_strategy.pine` 2026-07-24. NOT PORTED YET — same pattern as `exec_conf_sz`:
    #   the field exists so `compare_strategy.py` can REFUSE an export taken with it on rather than
    #   silently diffing against logic this bot does not have. Porting it means qualifying a gap
    #   that STRADDLES 0.5 (bottom <= 0.5 <= top) and resting the limit AT 0.5, ranked LAST behind
    #   the deep-FVG edge, deep-fib and Sniper Zone — see execution._entry_edges.
    exec_respect_veto: bool = True     # "Respect divergence/extreme veto"
    exec_close_opp_sos: bool = False   # "Close on opposite SOS"
    exec_htf_exhaust_only: bool = False  # "Only fade HTF exhaustion, not breakouts"
    exec_htf_source: str = "Weekly"    # "HTF exhaustion source"  ∈ {Weekly, Daily, Either}
    exec_htf_weekly: str = "Ignore"    # "Weekly bias requirement"
    exec_htf_daily: str = "Ignore"     # "Daily bias requirement"
    #   HTF-bias options: Ignore | Must agree | Must not oppose | Must oppose (reversal)
    exec_risk_pct: float = 10.0        # "Risk % per trade"
    exec_sl_level: str = "1.0"         # "SL fib level"  ∈ {0.618, 0.702, 0.786, 0.886, 1.0}
    exec_sl_buf_tk: float = 0.0        # "SL buffer beyond chosen level (ticks)"
    exec_tp1_pct: float = 30.0         # "TP1 size %"
    exec_tp2_pct: float = 40.0         # "TP2 size %"
    exec_be_buf_tk: float = 30.0       # "Breakeven buffer (ticks)"
    exec_trail_step: float = 5.0       # "Runner trail step ($ of price)" — Fixed-step mode only
    exec_runner_trail: str = "Structure (swing)"   # "Runner trail method"
    #   ∈ {"Fixed step", "Structure (swing)"}. How the TP3 runner is trailed once TP2 fills.
    #   "Fixed step" = the `exec_trail_step` grid ratchet off TP2 (the pre-2026-07-25 behaviour).
    #   "Structure (swing)" (DEFAULT, matching the Pine) = trail behind the structure engine's
    #   last CONFIRMED swing low (longs) / high (shorts), offset by `exec_struct_trail_buf_tk`.
    #   Breathes with the trend and rides further, but gives back more at the turn.
    exec_struct_trail_buf_tk: float = 20.0  # "Structure trail buffer (ticks)"
    #   Structure mode only. The runner stop sits this many ticks BELOW the confirmed swing low
    #   (long) / ABOVE the swing high (short), so a wick through the swing doesn't clip it.
    exec_tp2_stop_mode: str = "TP1 price"   # "TP2 → stop floor (delay the jump)"
    #   ∈ {"TP1 price", "Breakeven", "One trail step behind"}. What the stop FLOOR becomes the
    #   moment TP2 fills, before the runner trail takes over. "TP1 price" (default) snaps the stop
    #   up to TP1; "Breakeven" holds at entry ± the BE buffer (most room); "One trail step behind"
    #   keeps it one `exec_trail_step` under the high-water mark, never below breakeven.
    exec_no_late_day: bool = True      # "No entries in final hour (16:00-17:00 NY)"
    exec_conf_sz: bool = False         # "Allow Sniper Zone as entry confirmation" (Pine execConfSZ)
    #   Added to `mpc_strategy.pine` 2026-07-21. NOT PORTED YET — the field exists so the toggle is
    #   readable from the export's cfg_bits and `compare_strategy.py` can REFUSE a run made with it
    #   on, rather than silently diffing against logic this bot does not have. Porting it means
    #   reading the Sniper fib (already in the replay stack as `BarState.sniper`) and using its
    #   0.5-0.618 pocket as an entry edge on any leg with no qualifying FVG.
    exec_secondary: bool = False       # "Secondary re-entries (1m SOS)" — the 1m sniper re-entry
    #   OFF (default) = primary only, one entry per 15m A+ leg (keeps compare_strategy.py parity).
    #   ON = also re-enter on the same 15m leg from the 1m chart (needs run_dual + a 1m feed).
    #   Full rules: docs/MPC_SOS_FADE_SECONDARY.md. There is NO Pine parity gate for it — the Pine
    #   is only the approximate version — so it is verified visually, not by compare_strategy.py.

    # ── GRP_STATS — the one decision-affecting stats input (4194) ───────────────
    exec_scratch_r: float = 0.15       # "Scratch band (R)" — grades a closed trade WIN/LOSS/SCRATCH

    # ── GRP_APLUS — A+ sequence (156) ───────────────────────────────────────────
    aplus_window: int = 4320           # "Max Time: Sweep → SOS (minutes)" — staleness backstop

    # ── GRP_DIV — RSI divergence: feeds the veto + the live DIV confluence (169-180) ─
    show_div: bool = True              # "Track RSI Divergence" (showDivInput; marketStructureOnly off)
    div_rsi_len: int = 14              # "RSI Length"
    div_pivot_len: int = 5             # "Pivot Width (bars)"
    div_valid_bars: int = 100          # "Divergence Valid For (bars)"
    div_veto: bool = True              # "Veto Setups on Extreme/Divergence"
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
