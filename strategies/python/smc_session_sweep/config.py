"""Every input of `smc_session_sweep_strategy.pine` that can MOVE A TRADE, and nothing else.

🔴 **Nothing may exist here without a Pine input behind it.** A field the export twin cannot
carry is a field the parity gate can never check, and that is most of why the previous BOS port
was deleted. Each field below names its Pine input in the comment; the display-only toggles
(`execShowPosBox`, `showSetups`, `showBlockTag`, `pbShowSess`, `showSosMark`, `sosCmpTf`,
`execShowLabels`, `execBeBandR`, `debugDays`) are deliberately ABSENT — they cannot change the
trade list, so carrying them would invite a parity failure over a chart drawing.

⚠ **This dataclass subclasses nothing**, on purpose. Every parent default you do not re-declare
arrives uninvited; two of those cost the BOS port its gate.

⚠ `exec_fixed_qty` has no `cfg_*` column in the export twin, by that file's own decision: a
sweep never leaves "Risk % of equity". It is declared here because the Pine input exists and the
strategy reads it, and `from_export()` REFUSES a CSV taken in fixed-contracts mode rather than
gating on a size it cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SessionSweepConfig", "TP1_MODES", "SIZE_MODES", "CONF_WHEN", "ZONE_ENTRY",
           "STOP_FROM", "MIN_STOP_MODES"]

TP1_MODES = ("Fixed R", "Nearest liquidity level")
SIZE_MODES = ("Risk % of equity", "Fixed contracts")
CONF_WHEN = ("Before the zone (rest a limit)", "At the zone (enter at market)")
ZONE_ENTRY = ("Proximal edge", "Midpoint", "Distal edge")
STOP_FROM = ("The gap", "The sweep extreme")
MIN_STOP_MODES = ("Off", "% of price", "Fixed $", "x ATR(14)")


@dataclass
class SessionSweepConfig:
    """Defaults are the Pine file's shipped defaults, verbatim, as of 2026-08-17.

    ⚠ Five of the six shipped defaults are Aaron's own chart settings and are NOT a measurement.
    Only `exec_min_stop_val = 4.00` in `Fixed $` was measured. `docs/SMC_SESSION_SWEEP_SPEC.md`
    -> *The shipped defaults*.
    """

    # 1 · HIS MODEL — what arms the trade
    pb_dir_tf: str = "15"                       # pbDirTf
    pb_trade_ldn: bool = True                   # pbTradeLdn
    pb_trade_ny: bool = True                    # pbTradeNy

    # 2 · THE SHIFT OF STRUCTURE
    pb_require_conf: bool = False               # pbRequireConf
    pb_conf_tf: str = "1"                       # pbConfTf
    pb_conf_when: str = CONF_WHEN[0]            # pbConfWhen
    exec_be_on_shift: bool = True               # execBeOnShift

    # 3 · HIS MODEL — the entry zone
    pb_poi_tf: str = "5"                        # pbPoiTf ("Off" allowed)
    pb_poi_untouched: bool = True               # pbPoiUntouched

    # 4 · HIS MODEL — targets
    exec_tp1_mode: str = TP1_MODES[0]           # execTp1Mode
    exec_tp1_r: float = 3.5                     # execTp1R
    exec_tp1_pct: float = 80.0                  # execTp1Pct
    exec_use_tp1: bool = True                   # execUseTp1  (previous day)
    exec_use_tp2: bool = True                   # execUseTp2  (previous week)

    # 5 · HIS MODEL — execution hours (New York clock)
    exec_use_windows: bool = True               # execUseWindows
    exec_win_ldn: str = "0200-0500"             # execWinLdn
    exec_win_ny: str = "0700-1000"              # execWinNy

    # 6 · OURS — what trades, and how big
    pb_trade_longs: bool = True                 # pbTradeLongs
    pb_trade_shorts: bool = True                # pbTradeShorts
    exec_size_mode: str = SIZE_MODES[0]         # execSizeMode
    exec_risk_pct: float = 4.0                  # execRiskPct
    exec_fixed_qty: float = 1.0                 # execFixedQty — no cfg_* column, see module docstring

    # 7 · OURS — choices his method leaves open
    pb_struct_len: int = 15                     # pbStructLen
    exec_zone_entry: str = ZONE_ENTRY[0]        # execZoneEntry
    exec_stop_from: str = STOP_FROM[0]          # execStopFrom
    exec_sl_buf_tk: int = 20                    # execSlBufTk
    exec_cancel_bars: int = 0                   # execCancelBars
    exec_cancel_flip: bool = True               # execCancelFlip
    exec_be_at_tp1: bool = True                 # execBeAtTp1
    exec_be_buf_tk: int = 20                    # execBeBufTk
    exec_tp_fallback_r: float = 3.0             # execTpFallbackR
    exec_min_rr: float = 1.0                    # execMinRr

    # 8 · OURS — safety filters that REFUSE a setup
    exec_min_stop_mode: str = MIN_STOP_MODES[2]  # execMinStopMode — "Fixed $"
    exec_min_stop_val: float = 4.0              # execMinStopVal
    pb_poi_max_atr: float = 0.0                 # pbPoiMaxAtr
    exec_time_stop_hrs: float = 0.0             # execTimeStopHrs

    # ── platform facts the Pine reads off the symbol, not inputs. They belong to the RUN.
    tick_size: float = 0.01                     # syminfo.mintick — gold is one cent
    #: The venue's quantity step. TradingView's broker emulator TRUNCATES a computed size down to
    #: it — 82.4928 is sent as 82.4, never 82.5 — so a port that keeps the full float books a
    #: slightly larger position than the chart on every single trade. MEASURED off all ten fills
    #: in the 2026-09-20 export, floor in every one.
    qty_step: float = 0.1
    initial_capital: float = 10_000.0           # strategy() header

    # ── decoding the export twin's packed config columns ──────────────────────────────

    @classmethod
    def from_export(cls, row: dict) -> "SessionSweepConfig":
        """Build the config FROM the CSV's own `cfg_*` columns, never from today's defaults.

        Configuring the Python from its defaults instead would make both sides agree about a
        model neither of them had enabled — the exact failure step 5 of `/port` names.
        """
        def num(key: str) -> float:
            v = row.get(key, "")
            if v in ("", None):
                raise ValueError(f"the export has no value for {key}")
            return float(v)

        bits = int(num("cfg_bits"))
        e1 = int(num("cfg_enum1"))
        i1 = int(num("cfg_int1"))
        i2 = int(num("cfg_int2"))
        poi_tf = num("cfg_poi_tf")

        size_mode = SIZE_MODES[e1 // 10 % 10]
        if size_mode != SIZE_MODES[0]:
            # The twin exports no `cfg_fixed_qty`, so a fixed-contracts CSV cannot be gated.
            # Detectable and REFUSED, which is the whole reason the mode is in `cfg_enum1`.
            raise ValueError(
                "this export was taken in Fixed-contracts mode; the twin carries no size column, "
                "so the gate cannot check position size. Re-export in 'Risk % of equity'."
            )

        return cls(
            pb_dir_tf=str(int(num("cfg_dir_tf"))),
            pb_trade_ldn=bool(bits >> 0 & 1),
            pb_trade_ny=bool(bits >> 1 & 1),
            pb_require_conf=bool(bits >> 2 & 1),
            pb_conf_tf=str(int(num("cfg_conf_tf"))),
            pb_conf_when=CONF_WHEN[e1 // 100 % 10],
            exec_be_on_shift=bool(bits >> 6 & 1),
            pb_poi_tf="Off" if poi_tf == 0 else str(int(poi_tf)),
            pb_poi_untouched=bool(bits >> 3 & 1),
            exec_tp1_mode=TP1_MODES[e1 % 10],
            exec_tp1_r=num("cfg_tp1_r"),
            exec_tp1_pct=float(i2 % 1000),
            exec_use_tp1=bool(bits >> 4 & 1),
            exec_use_tp2=bool(bits >> 5 & 1),
            exec_use_windows=bool(bits >> 7 & 1),
            pb_trade_longs=bool(bits >> 8 & 1),
            pb_trade_shorts=bool(bits >> 9 & 1),
            exec_size_mode=size_mode,
            exec_risk_pct=num("cfg_risk_pct"),
            pb_struct_len=i1 % 100,
            exec_zone_entry=ZONE_ENTRY[e1 // 1000 % 10],
            exec_stop_from=STOP_FROM[e1 // 10000 % 10],
            exec_sl_buf_tk=i1 // 100 % 1000,
            exec_cancel_bars=i2 // 1000,
            exec_cancel_flip=bool(bits >> 10 & 1),
            exec_be_at_tp1=bool(bits >> 11 & 1),
            exec_be_buf_tk=i1 // 100000,
            exec_tp_fallback_r=num("cfg_tp_fallback"),
            exec_min_rr=num("cfg_min_rr"),
            exec_min_stop_mode=MIN_STOP_MODES[e1 // 100000 % 10],
            exec_min_stop_val=num("cfg_min_stop_val"),
            pb_poi_max_atr=num("cfg_poi_max_atr"),
            exec_time_stop_hrs=num("cfg_time_stop"),
        )

    # ⚠ The execution-hour STRINGS have no `cfg_*` column — a string cannot cross a CSV. The twin
    # exports what the window DECIDED (`inWinLdn`, `inWinNy`) instead, so the gate checks the
    # decision rather than the parse. `from_export` therefore leaves these at their Pine defaults
    # and the window bits in `px_state` are what proves they agree.
