"""compare_bos.py — the BOS LOGIC-PARITY check.

The third of the family, beside `mpc_sos_fade/tools/compare_strategy.py` and
`mpc_bleg/tools/compare_bleg.py`. Reads a TradingView "Export chart data" CSV of
`indicators/strategies/mpc_bos_strategy_export.pine` — the instrumented strategy that plots its per-bar
DECISION STREAM plus the tracker's own state plus every input as a column — replays the
export's OWN bars through the Python bot CONFIGURED FROM THE EXPORT, and diffs the two streams
bar by bar.

Exit 0 = the Python makes the identical decisions as the Pine. On a mismatch it names the FIRST
bar and field that diverged, so you know exactly where they parted.

This is LOGIC parity (same decisions on the SAME candles), NOT feed parity (whether MT5's
candles match TradingView's — that is `backtest/tools/compare_feeds.py`). Logic parity replays
TradingView's own bars, so the broker feed is irrelevant here.

    python compare_bos.py <export.csv> [--warmup N] [--price-tol 0.01] [--r-tol 0.02]

🔴 **UNTIL THIS EXITS 0 ON A REAL EXPORT, NOTHING IN `strategies/python/mpc_bos/` IS
VALIDATED.** That is not boilerplate: the previous port was deleted on 2026-08-04 for having
produced an 82-configuration sweep nobody could check, and `backtest/tools/bos_sweep.py` was
falsified by a single Strategy Tester run the day it was written. Take the export first.

⚠ **THE VOLUME COLUMN, AND THE CLAIM THIS DOCSTRING USED TO MAKE ABOUT IT WAS FALSE.** It said
"TradingView exports it". It does not: "Export chart data" carries a Volume column only if the
Volume STUDY is on the reader's chart, so it is a fact about somebody's layout rather than about
the export. Measured 2026-08-07 across ~40 exports in `engines/` — exactly ONE has volume, and it
is the one whose Pine plots it. The first real BOS export arrived with none, and this tool refused.
The fix is that `mpc_bos_strategy_export.pine` now plots `px_volume` itself, which is the same
convention `vwap_export.pine` and `svp_export.pine` have carried since they were written; the
column is resolved here as px_volume → volume → Volume, exactly as `compare_vwap.py` resolves it.
The session-VWAP filter (F10, default ON) is the only rule that needs it, and the tool REFUSES
rather than replaying the filter against nothing — a gate that silently blocks every setup is
green about an empty book.

⚠ **A GREEN RUN IS ONLY GREEN ABOUT THE BRANCHES BOTH SIDES ENTERED.** This repo has shipped a
setting on a parity run that never exercised it (the min-stop guard, 2026-08-04: block code 7
raised ZERO times in 21,897 bars). So this tool prints a COVERAGE table — how many bars each
side of the entry ladder, each block code and each stop model actually reached — and says so
out loud when a branch was never taken. Read it before believing the exit code.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import List, Optional

import pandas as pd

# ── make the bot importable standalone (CLI / CI), same shim as strategy.py ──
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_sos_fade.tools.compare_strategy import load_export  # noqa: E402

from mpc_bos import BosConfig, MpcBosStrategy  # noqa: E402

# ── the packed decoders — MUST match mpc_bos_strategy_export.pine's plot scheme ──
# Each is mirrored in the Pine's own PARITY EXPORT header comment. Kept as literal dicts
# rather than derived, so a scheme change here fails loudly instead of shifting silently.
_CFG_BITS = {
    "exec_longs": 1,
    "exec_shorts": 2,
    "bos_use_fvg": 4,
    "exec_req_fvg": 8,
    "exec_fvg_deep_only": 16,
    "exec_deep_fib": 32,
    "exec_conf_sz2": 64,
    "exec_fvg_50": 128,
    "bos_req_hold": 256,
    "bos_respect_veto": 512,
    "exec_no_late_day": 1024,
    "bos_tp3_measured": 2048,
    "bos_close_opp_div": 4096,
    # engine-side, decoded into EngineConfig rather than BosConfig
    "fvg_require_close": 8192,
    "fvg_keep_until_broken": 16384,
    "eq_exempt_fvg": 32768,
    # these two are enums wearing a bit, because each has exactly two states
    "bos_shallow": 65536,
    "bos_expansion_anchor": 131072,
    "bos_vwap_on": 262144,
    "use_struct_trail": 524288,
}
_ENTRY_FIB = {0: "0.382", 1: "0.5", 2: "0.618", 3: "0.702", 4: "0.786", 5: "0.886"}
_WHICH = {0: "1st only", 1: "1st + 2nd", 2: "All"}
_SL_MODEL = {
    0: "Fib 1.0 (leg origin)",
    1: "Broken swing level",
    2: "Fib 0.886",
    3: "Last confirmed swing",
    4: "ATR",
}
_MIN_STOP = {0: "Off", 1: "% of price", 2: "Fixed $", 3: "x ATR(14)"}
_MOVE_STOP = {0: "Off", 1: "$ of price", 2: "Structure (swing)"}
_TP2_STOP = {0: "TP1 price", 1: "Breakeven", 2: "One trail step behind"}
_HTF_REQ = {0: "Ignore", 1: "Must agree", 2: "Must not oppose", 3: "Must oppose (reversal)"}

# px_struct / px_arm / px_ready / px_gate / px_src bit maps.
_STRUCT = {
    "bull_bos": 1,
    "bear_bos": 2,
    "bull_sos": 4,
    "bear_sos": 8,
    "session_gap": 16,
    "fired_l": 32,
    "fired_s": 64,
}
_ARM = {
    "l_on": 1,
    "s_on": 2,
    "reg_l": 4,
    "reg_s": 8,
    "long_armed": 16,
    "short_armed": 32,
    "pos_long": 64,
    "pos_short": 128,
    "fill_bar": 256,
    "close_bar": 512,
}
_READY = {"l_ready": 1, "s_ready": 2, "l_half": 4, "s_half": 8}
_GATE = {
    "late": 1,
    "htf_l": 2,
    "htf_s": 4,
    "vwap_l": 8,
    "vwap_s": 16,
    "veto_l": 32,
    "veto_s": 64,
    "blk_ready_l": 128,
    "blk_ready_s": 256,
}


class ExportIncomplete(RuntimeError):
    """The CSV cannot drive this check — a missing column, not a mismatch.

    Raised rather than skipped, because a check that quietly drops a column reports GREEN on a
    narrower question than the one asked, which is this repo's most-repeated defect.
    """


def _bit(value: float, mask: int) -> bool:
    return bool(int(value) & mask)


def _require(df: pd.DataFrame, columns) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ExportIncomplete(
            f"export is missing {missing}. Re-export from the CURRENT "
            "indicators/strategies/mpc_bos_strategy_export.pine — a column added to the Pine after an "
            "export was taken is not in that CSV, and diffing without it would check less "
            "than this tool claims to."
        )


def config_from_export(df: pd.DataFrame, base: Optional[BosConfig] = None) -> BosConfig:
    """Decode a `BosConfig` from the export's own `cfg_*` columns.

    THIS IS THE POINT OF THE WHOLE HARNESS. A parity run taken with the two sides on different
    settings is green about nothing — so nothing here defaults quietly: every field comes off a
    column, and a missing column raises.
    """
    _require(
        df,
        (
            "cfg_bits",
            "cfg_enum1",
            "cfg_enum2",
            "cfg_min_disp",
            "cfg_min_leg",
            "cfg_max_days",
            "cfg_max_regime",
            "cfg_sl_atr",
            "cfg_sl_buf",
            "cfg_min_stop_val",
            "cfg_move_stop_val",
            "cfg_tp1_pct",
            "cfg_tp2_pct",
            "cfg_tp3_pct",
            "cfg_be_buf",
            "cfg_struct_buf",
            "cfg_trail_step",
            "cfg_risk_pct",
        ),
    )
    row = df.iloc[0]
    bits = int(row["cfg_bits"])
    e1, e2 = int(row["cfg_enum1"]), int(row["cfg_enum2"])

    cfg = base or BosConfig()
    cfg = replace(
        cfg,
        exec_longs=_bit(bits, _CFG_BITS["exec_longs"]),
        exec_shorts=_bit(bits, _CFG_BITS["exec_shorts"]),
        bos_use_fvg=_bit(bits, _CFG_BITS["bos_use_fvg"]),
        exec_req_fvg=_bit(bits, _CFG_BITS["exec_req_fvg"]),
        exec_fvg_deep_only=_bit(bits, _CFG_BITS["exec_fvg_deep_only"]),
        exec_deep_fib=_bit(bits, _CFG_BITS["exec_deep_fib"]),
        exec_conf_sz2=_bit(bits, _CFG_BITS["exec_conf_sz2"]),
        exec_fvg_50=_bit(bits, _CFG_BITS["exec_fvg_50"]),
        bos_req_hold=_bit(bits, _CFG_BITS["bos_req_hold"]),
        bos_respect_veto=_bit(bits, _CFG_BITS["bos_respect_veto"]),
        exec_no_late_day=_bit(bits, _CFG_BITS["exec_no_late_day"]),
        bos_tp3_measured=_bit(bits, _CFG_BITS["bos_tp3_measured"]),
        bos_close_opp_div=_bit(bits, _CFG_BITS["bos_close_opp_div"]),
        bos_entry_top="0.382" if _bit(bits, _CFG_BITS["bos_shallow"]) else "0.5",
        bos_fib_anchor=(
            "Expansion leg" if _bit(bits, _CFG_BITS["bos_expansion_anchor"]) else "Break leg"
        ),
        bos_vwap_req="Trend's side" if _bit(bits, _CFG_BITS["bos_vwap_on"]) else "Off",
        exec_runner_trail=(
            "Structure (swing)" if _bit(bits, _CFG_BITS["use_struct_trail"]) else "Fixed step"
        ),
        bos_entry_fib=_ENTRY_FIB[e1 % 10],
        bos_which=_WHICH[(e1 // 10) % 10],
        bos_sl_model=_SL_MODEL[(e1 // 100) % 10],
        exec_min_stop_mode=_MIN_STOP[(e1 // 1000) % 10],
        bos_move_stop=_MOVE_STOP[(e1 // 10000) % 10],
        exec_tp2_stop_mode=_TP2_STOP[e2 % 10],
        exec_htf_weekly=_HTF_REQ[(e2 // 10) % 10],
        exec_htf_daily=_HTF_REQ[(e2 // 100) % 10],
        bos_min_disp_atr=float(row["cfg_min_disp"]),
        bos_min_leg_atr=float(row["cfg_min_leg"]),
        bos_max_days=float(row["cfg_max_days"]),
        bos_max_per_regime=int(row["cfg_max_regime"]),
        bos_sl_atr=float(row["cfg_sl_atr"]),
        exec_sl_buf_tk=float(row["cfg_sl_buf"]),
        exec_min_stop_val=float(row["cfg_min_stop_val"]),
        bos_move_stop_val=float(row["cfg_move_stop_val"]),
        exec_tp1_pct=float(row["cfg_tp1_pct"]),
        exec_tp2_pct=float(row["cfg_tp2_pct"]),
        exec_tp3_pct=float(row["cfg_tp3_pct"]),
        exec_be_buf_tk=float(row["cfg_be_buf"]),
        exec_struct_trail_buf_tk=float(row["cfg_struct_buf"]),
        exec_trail_step=float(row["cfg_trail_step"]),
        exec_risk_pct=float(row["cfg_risk_pct"]),
    )
    return cfg


def engine_config_from_export(df: pd.DataFrame):
    """The ENGINE-construction inputs, off the same columns.

    They are not part of the decision stream, so an unpinned one is a silent parity trap — and
    this fork disagrees with the A+ bot on three of them (`fvg_max_count`, `fvg_threshold_pct`,
    `fvg_require_close`). Taking them from the export rather than from
    `MpcBosStrategy.engine_config()` is what makes a run with a tweaked FVG setting checkable.
    """
    from backtest.replay import EngineConfig

    _require(df, ("cfg_bits", "cfg_fvg_thresh", "cfg_fvg_max"))
    row = df.iloc[0]
    bits = int(row["cfg_bits"])
    return EngineConfig(
        fvg_max_count=int(row["cfg_fvg_max"]),
        fvg_threshold_pct=float(row["cfg_fvg_thresh"]),
        fvg_require_close=_bit(bits, _CFG_BITS["fvg_require_close"]),
        eq_exempt_fvg=_bit(bits, _CFG_BITS["eq_exempt_fvg"]),
        show_internal=False,  # this Pine's "Show Internal Structure" input defaults off
    )


# ── the diff ─────────────────────────────────────────────────────────────────────
_BOOL_FIELDS = (
    ("l_on", "px_arm", _ARM["l_on"]),
    ("s_on", "px_arm", _ARM["s_on"]),
    ("reg_l", "px_arm", _ARM["reg_l"]),
    ("reg_s", "px_arm", _ARM["reg_s"]),
    ("long_armed", "px_arm", _ARM["long_armed"]),
    ("short_armed", "px_arm", _ARM["short_armed"]),
    ("l_ready", "px_ready", _READY["l_ready"]),
    ("s_ready", "px_ready", _READY["s_ready"]),
    ("l_half", "px_ready", _READY["l_half"]),
    ("s_half", "px_ready", _READY["s_half"]),
    ("vwap_block_l", "px_gate", _GATE["vwap_l"]),
    ("vwap_block_s", "px_gate", _GATE["vwap_s"]),
    ("veto_l", "px_gate", _GATE["veto_l"]),
    ("veto_s", "px_gate", _GATE["veto_s"]),
    ("fired_l", "px_struct", _STRUCT["fired_l"]),
    ("fired_s", "px_struct", _STRUCT["fired_s"]),
)
_PRICE_FIELDS = (
    ("long_edge", "px_edge_l"),
    ("short_edge", "px_edge_s"),
    ("l_ext", "px_l_ext"),
    ("l_org", "px_l_org"),
    ("s_ext", "px_s_ext"),
    ("s_org", "px_s_org"),
    ("vwap", "px_vwap"),
)
_INT_FIELDS = (
    ("ordinal_l", "px_ord_l"),
    ("ordinal_s", "px_ord_s"),
    ("tier_l", "px_tier_l"),
    ("tier_s", "px_tier_s"),
    ("blk_l", "px_blk_l"),
    ("blk_s", "px_blk_s"),
    ("stage", "px_stage"),
)


def _py_row(dec, bos, stage: int) -> dict:
    """One bar of the PYTHON stream, in the export's own vocabulary."""
    lv, sv = bos.l_levels, bos.s_levels
    return {
        "l_on": bos.long.on,
        "s_on": bos.short.on,
        "reg_l": bos.regime_l,
        "reg_s": bos.regime_s,
        "long_armed": dec.long_armed,
        "short_armed": dec.short_armed,
        "l_ready": bos.l_ready,
        "s_ready": bos.s_ready,
        "l_half": bos.long.half,
        "s_half": bos.short.half,
        "vwap_block_l": bos.vwap_block_l,
        "vwap_block_s": bos.vwap_block_s,
        "veto_l": dec.long_veto,
        "veto_s": dec.short_veto,
        "fired_l": bos.fired_l,
        "fired_s": bos.fired_s,
        "long_edge": dec.long_edge,
        "short_edge": dec.short_edge,
        "l_ext": lv.get(0.0),
        "l_org": lv.get(1.0),
        "s_ext": sv.get(0.0),
        "s_org": sv.get(1.0),
        "vwap": bos.vwap,
        # RAW, not zeroed when disarmed. Pine plots `bosL_n` unconditionally and that var keeps
        # the last armed leg's ordinal after a death — this used to read `... if bos.long.on
        # else 0`, which was the harness quietly agreeing with a port that cleared its legs.
        "ordinal_l": bos.long.ordinal,
        "ordinal_s": bos.short.ordinal,
        # 🔴 The stage RECORDED on this bar, never `execution._stage`. This loop runs after the
        # replay, so reading the live object gave every bar the run's FINAL stage — a constant,
        # 0 because the run ends flat, which is why this column diffed clean for its whole life
        # and then failed only where the Pine said 1 or 2. A harness reading live state after
        # the fact is not reading the bar it names.
        "stage": stage,
        "closed_r": dec.closed_r,
    }


def _drop_forming_tail(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the still-forming bars TradingView appends at the end of an export.

    A bar that has not closed has no plotted values — `px_struct`, `px_arm`, `px_volume`,
    every one of them exports as blank — so it is a NON-BAR, not a bar on which the Pine
    decided nothing. `compare_strategy.py` has flagged the same rows since it was written;
    this drops them instead, because the volume column feeds the REPLAY here and a NaN
    reaches the VWAP engine long before the compare loop could skip it.

    ⚠ Only a TRAILING run is dropped, and the count is printed. A blank row in the MIDDLE
    is a different animal — a truncated or edited CSV — and silently trimming around it is
    how a harness ends up answering a narrower question than the one asked.
    """
    present = (df["px_struct"].notna() & df["px_arm"].notna()).to_numpy()
    if present.all():
        return df
    tail = 0
    while tail < len(present) and not present[len(present) - 1 - tail]:
        tail += 1
    keep = len(present) - tail
    if keep == 0 or not present[:keep].all():
        blanks = [int(i) for i in (~present[:keep]).nonzero()[0][:5]]
        raise ExportIncomplete(
            f"the export has {len(present) - keep} blank trailing rows and "
            f"{len(blanks)} blank rows INSIDE it (e.g. {blanks or 'all of them'}). Only a "
            "still-forming tail is expected to be blank, so this is a truncated or edited CSV "
            "rather than a live last bar. Re-export rather than letting the tool guess which "
            "rows are real."
        )
    print(f"dropping {tail} still-forming bar(s) from the end of the export")
    return df.iloc[:keep]


def compare(csv_path: Path, warmup: int, price_tol: float, r_tol: float) -> int:
    df = load_export(csv_path)
    _require(
        df,
        (
            "px_struct",
            "px_arm",
            "px_ready",
            "px_gate",
            "px_edge_l",
            "px_edge_s",
            "px_l_ext",
            "px_l_org",
            "px_s_ext",
            "px_s_org",
            "px_ord_l",
            "px_ord_s",
            "px_tier_l",
            "px_tier_s",
            "px_blk_l",
            "px_blk_s",
            "px_stage",
            "px_vwap",
            "px_closed_r",
            "px_src",
        ),
    )
    df = _drop_forming_tail(df)
    cfg = config_from_export(df)
    eng = engine_config_from_export(df)

    if cfg.bos_vwap_req != "Off" and _volume_col(df) is None:
        raise ExportIncomplete(
            "the export has bosVwapReq ON but carries no usable volume column, so the Python "
            "side cannot compute the session VWAP. The export Pine must plot `px_volume` — "
            "TradingView only ships a native Volume column when the Volume STUDY is on the "
            "chart, so it is not something an export can be assumed to carry. Re-export from a "
            "current mpc_bos_strategy_export.pine, or take the export with the filter Off — "
            "replaying it against an absent VWAP would block every setup and call the "
            "resulting empty book agreement."
        )

    print(
        f"config from export: sl={cfg.bos_sl_model} entry={cfg.bos_entry_fib} "
        f"anchor={cfg.bos_fib_anchor} useFvg={cfg.bos_use_fvg} vwap={cfg.bos_vwap_req} "
        f"which={cfg.bos_which} tp={cfg.exec_tp1_pct}/{cfg.exec_tp2_pct}/{cfg.exec_tp3_pct}"
    )
    print(
        f"engines from export: fvg_max={eng.fvg_max_count} thresh={eng.fvg_threshold_pct} "
        f"req_close={eng.fvg_require_close} eq_exempt={eng.eq_exempt_fvg}"
    )

    strat = MpcBosStrategy(cfg).run(_bars_from(df), engine_config=eng)

    mismatches: List[str] = []
    coverage = Counter()
    compared = 0

    for i, (dec, bos, stage) in enumerate(
        zip(strat.decisions, strat.bos_states, strat.exit_stages)
    ):
        if i < warmup:
            continue
        row = df.iloc[i]
        py = _py_row(dec, bos, stage)
        compared += 1

        _tally(coverage, py, row)

        for name, col, mask in _BOOL_FIELDS:
            pine = _bit(row[col], mask)
            if bool(py[name]) != pine:
                mismatches.append(f"bar {i} {name}: py={py[name]} pine={pine}")
        for name, col in _PRICE_FIELDS:
            if _price_differs(py[name], row[col], price_tol):
                mismatches.append(f"bar {i} {name}: py={py[name]} pine={row[col]}")
        for name, col in _INT_FIELDS:
            if name in py and _int_differs(py[name], row[col]):
                mismatches.append(f"bar {i} {name}: py={py[name]} pine={row[col]}")
        if _price_differs(py["closed_r"], row["px_closed_r"], r_tol):
            mismatches.append(f"bar {i} closed_r: py={py['closed_r']} pine={row['px_closed_r']}")

        if mismatches:
            break  # the FIRST divergence is the only informative one

    _report_coverage(coverage, compared, cfg)

    if mismatches:
        print("\nRED — first divergence:")
        for m in mismatches[:8]:
            print("  " + m)
        return 1
    print(f"\nGREEN — {compared} bars compared, no divergence.")
    return 0


def _volume_col(df: pd.DataFrame) -> Optional[str]:
    """The export's volume column, or None if it has none worth using.

    Order is the one `compare_vwap.py` and `compare_svp.py` already use: the Pine's own
    `px_volume` first, then a native column under either casing. An all-empty column counts
    as NO column — a header with nothing under it is the shape TradingView produces when the
    Volume study was toggled on after the range was drawn, and feeding those NaNs to the VWAP
    engine would answer the gate's question with a number nobody measured.
    """
    for name in ("px_volume", "volume", "Volume"):
        if name in df.columns and pd.to_numeric(df[name], errors="coerce").notna().any():
            return name
    return None


def _bars_from(df: pd.DataFrame) -> pd.DataFrame:
    """The export's own OHLC(+volume), as a canonical bar frame."""
    cols = ["open", "high", "low", "close"]
    vcol = _volume_col(df)
    if vcol is not None:
        cols.append(vcol)
    # `load_export` has already parsed the time column into the INDEX (TradingView ships unix
    # seconds, which re-parsing as a datetime string would silently mangle), so the index is
    # taken as-is rather than rebuilt from a column that may still hold the raw integers.
    out = df[cols].copy()
    if vcol is not None:
        # Renamed, never left as `px_volume` — `ReplayBar` reads a column called `volume`, and a
        # frame carrying the data under the export's own name would look exactly like a feed with
        # no volume at all: the tracker would REFUSE, and the refusal would blame the feed.
        out = out.rename(columns={vcol: "volume"})
    out.index.name = "time"
    return out


def _price_differs(py, pine, tol: float) -> bool:
    """`na` on one side and a value on the other IS a divergence — that is the whole
    'no' vs 'cannot ask' rule, and it is the shape most of this family's real bugs took."""
    pine_na = pine is None or (isinstance(pine, float) and pd.isna(pine))
    if py is None and pine_na:
        return False
    if (py is None) != pine_na:
        return True
    return abs(float(py) - float(pine)) > tol


def _int_differs(py, pine) -> bool:
    if pine is None or (isinstance(pine, float) and pd.isna(pine)):
        return int(py or 0) != 0
    return int(py or 0) != int(pine)


def _tally(coverage: Counter, py: dict, row) -> None:
    """Which BRANCHES this run actually reached — the answer to 'green about what?'."""
    if py["long_armed"] or py["short_armed"]:
        coverage["armed"] += 1
    if py["long_edge"] is not None or py["short_edge"] is not None:
        coverage["priced"] += 1
    for col in ("px_blk_l", "px_blk_s"):
        code = row[col]
        if code is not None and not pd.isna(code) and int(code) != 0:
            coverage[f"block_{int(code)}"] += 1
    if _bit(row["px_src"], 1) or _bit(row["px_src"], 4):
        coverage["gap_priced"] += 1
    if _bit(row["px_src"], 2) or _bit(row["px_src"], 8):
        coverage["zone_priced"] += 1
    for tier_col, key in (("px_tier_l", "tier_l"), ("px_tier_s", "tier_s")):
        t = row[tier_col]
        if t is not None and not pd.isna(t):
            coverage[f"tier_{int(t)}"] += 1


def _report_coverage(coverage: Counter, compared: int, cfg: BosConfig) -> None:
    print(f"\ncoverage over {compared} compared bars:")
    for key in sorted(coverage):
        print(f"  {key:<16} {coverage[key]}")
    # The warnings are the point: a green run on a branch neither side entered proves nothing
    # about that branch, and this repo has shipped exactly that (see the module docstring).
    if not coverage["armed"]:
        print("  ⚠ NOTHING EVER ARMED — this run proves nothing about the entry ladder.")
    if cfg.bos_use_fvg and not coverage["zone_priced"]:
        print(
            "  ⚠ the Sniper Zone never priced an entry, and the export carries no "
            "px_sz_top/px_sz_bot either — that branch is UNVERIFIED."
        )
    if cfg.exec_min_stop_mode != "Off" and not coverage["block_6"]:
        print(
            "  ⚠ the minimum-stop floor is ON and refused NOTHING — it is untested here. "
            "This is the exact shape of the 2026-08-04 min-stop incident."
        )
    if cfg.bos_vwap_req != "Off" and not coverage["block_7"]:
        print("  ⚠ the session VWAP filter is ON and refused NOTHING — it is untested here.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv", type=Path)
    ap.add_argument(
        "--warmup",
        type=int,
        default=100,
        help="bars to skip before comparing — the engines are streaming state "
        "machines and a cold one legitimately disagrees with a Pine that "
        "loaded more history. Raise it until the run is green from a stable "
        "point, then check it stays green when raised further: a mismatch "
        "that only disappears at a HIGH warmup is warmup; one that persists "
        "is drift.",
    )
    ap.add_argument("--price-tol", type=float, default=0.01)
    ap.add_argument("--r-tol", type=float, default=0.02)
    args = ap.parse_args()
    try:
        return compare(args.csv, args.warmup, args.price_tol, args.r_tol)
    except ExportIncomplete as exc:
        print(f"CANNOT CHECK: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
