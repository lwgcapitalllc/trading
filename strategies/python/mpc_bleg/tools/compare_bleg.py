"""compare_bleg.py — the B-LEG LOGIC-PARITY check.

The B-LEG twin of `mpc_sos_fade/tools/compare_strategy.py`. Reads a TradingView
"Export chart data" CSV of `indicators/mpc_b_leg_strategy_export.pine` — the instrumented
B-LEG strategy that plots its per-bar DECISION STREAM plus the B-LEG TRACKER's own state
plus every input toggle as a column — replays the export's OWN bars through the Python bot
configured to the SAME toggles, and diffs the two streams bar by bar.

Exit 0 = the Python makes the identical decisions as the Pine. On a mismatch it names the
FIRST bar and field that diverged.

This is LOGIC parity (same decisions on the SAME candles), NOT feed parity (whether MT5's
candles match TradingView's — that is `backtest/tools/compare_feeds.py`). Logic parity
replays TradingView's own bars, so the broker feed is irrelevant here.

WHY IT IS A SEPARATE TOOL rather than a flag on compare_strategy.py: the two bots diff
DIFFERENT fields. In the B-LEG fork A+ never places an order (it only holds priority), so
`px_dec_bits`'s arm bits are the B-LEG arm, `px_edge` is the frozen band's 0.5 edge rather
than an FVG edge, and TP1/TP2 are computed off the band instead of read from fib levels.
Diffing `long_armed` here would test a decision that never happens. What IS shared — the
packed cfg_* decoding — is imported, not duplicated.

Usage:
    python compare_bleg.py <export.csv> [--warmup N] [--price-tol 0.01] [--r-tol 0.02]

Stdlib + pandas, same as the A+ harness.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd

# ── make the bot importable standalone (CLI / CI), same shim as strategy.py ──
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_bleg import BLegConfig, MpcBLegStrategy  # noqa: E402
from mpc_sos_fade.tools.compare_strategy import (  # noqa: E402
    config_from_export as _config_from_export,
    load_export,
)


def config_from_export(df: pd.DataFrame, base: Optional[BLegConfig] = None) -> BLegConfig:
    """Decode a BLegConfig from the export's cfg_* columns.

    Delegates every shared column to the A+ decoder (one packing scheme, one decoder —
    both export Pines plot cfg_* identically on purpose), then reads this fork's only
    extra input. `allow_bleg=True` because the B-LEG export always ships execBLeg ON:
    the A+ decoder refuses that, correctly, since the A+ bot cannot make those trades.
    """
    cfg = _config_from_export(df, base or BLegConfig(), allow_bleg=True)
    if len(df) == 0:
        return cfg
    row = df.iloc[0]
    if "cfg_bleg_days" in df.columns and not pd.isna(row["cfg_bleg_days"]):
        from dataclasses import replace
        cfg = replace(cfg, bleg_max_days=float(row["cfg_bleg_days"]))
    else:
        print("WARNING: no cfg_bleg_days column — the B-LEG staleness cap is assumed to be at "
              "its default. Re-export off the current mpc_b_leg_strategy_export.pine.")
    return cfg


def _expand(df: pd.DataFrame) -> pd.DataFrame:
    """Unpack the export's packed columns into the flat names the diff loop reads.
    Mirrors mpc_b_leg_strategy_export.pine's PARITY EXPORT scheme exactly."""
    df = df.copy()
    if "px_dec_bits" in df.columns:
        b = df["px_dec_bits"].fillna(0).round().astype("int64")
        df["px_long_armed"] = (b & 1) != 0
        df["px_short_armed"] = (b & 2) != 0
        df["px_entry_dir"] = b.map(lambda x: 1 if x & 4 else (-1 if x & 8 else 0))
    if "px_stages" in df.columns:
        s = df["px_stages"].fillna(0).round().astype("int64")
        df["px_l_stage"] = s // 10
        df["px_s_stage"] = s % 10
    if "bl_bits" in df.columns:
        b = df["bl_bits"].fillna(0).round().astype("int64")
        df["bl_l_on"] = (b & 1) != 0
        df["bl_l_tap"] = (b & 2) != 0
        df["bl_s_on"] = (b & 4) != 0
        df["bl_s_tap"] = (b & 8) != 0
    if "bl_bars" in df.columns:
        b = df["bl_bars"].fillna(0).round().astype("int64")
        # stored as (bar+1) per slot so 0 means "none" and the packing never goes negative
        df["bl_l_bar"] = (b // 1_000_000).map(lambda x: None if x == 0 else x - 1)
        df["bl_s_bar"] = (b % 1_000_000).map(lambda x: None if x == 0 else x - 1)
    # TradingView leaves the final (still-forming) bar's plotted series blank, so its packed
    # columns read as 0 and would look like a real "nothing armed / no leg live". Mark it and
    # skip it, rather than reporting a phantom mismatch on the last row.
    marker = "px_dec_bits" if "px_dec_bits" in df.columns else "bl_bits"
    df["_px_present"] = df[marker].notna()
    return df


# What gets diffed. The B-LEG's own arm + band prices, the shared trade stream, and the A+
# stages (the B leg arms off the A+ sequence's death, so an A+ stage drift is where a B-LEG
# mismatch USUALLY originates — diffing it turns "a trade differs" into "the upstream moved").
_BOOL = ["px_long_armed", "px_short_armed", "bl_l_on", "bl_l_tap", "bl_s_on", "bl_s_tap"]
_INT = ["px_l_stage", "px_s_stage", "px_entry_dir", "bl_l_bar", "bl_s_bar"]
_PRICE = ["px_edge", "px_stop", "px_entry_price", "px_tp1", "px_tp2",
          "px_exit_tp1", "px_exit_tp2", "px_exit_run",
          "bl_l_top", "bl_l_bot", "bl_l_inv", "bl_l_tgt",
          "bl_s_top", "bl_s_bot", "bl_s_inv", "bl_s_tgt"]


def _py_row(dec, bleg) -> dict:
    """One bar of the Python side, in the export's column names."""
    # `Fill.dir` is the signed direction; `Fill.qty` is NOT signed. Reading qty's sign here
    # made every short look like a long — caught by the first real export, and NOT by the
    # round-trip test, because the test's encoder had the identical bug so the two agreed.
    entry_dir = next((f.dir for f in dec.fills if f.kind == "entry"), 0)
    exits = {"px_exit_tp1": None, "px_exit_tp2": None, "px_exit_run": None}
    for f in dec.fills:
        if f.kind != "exit":
            continue
        oid = f.order_id or ""
        if "TP1" in oid:
            exits["px_exit_tp1"] = f.price
        elif "TP2" in oid:
            exits["px_exit_tp2"] = f.price
        else:
            exits["px_exit_run"] = f.price
    edge = dec.long_edge if dec.long_armed else (dec.short_edge if dec.short_armed else None)
    return dict(
        px_long_armed=bool(dec.long_armed), px_short_armed=bool(dec.short_armed),
        px_entry_dir=entry_dir, px_l_stage=dec.l_stage, px_s_stage=dec.s_stage,
        px_edge=edge, px_stop=dec.stop,
        px_entry_price=next((f.price for f in dec.fills if f.kind == "entry"), None),
        px_tp1=dec.tp1, px_tp2=dec.tp2,
        px_closed_r=dec.closed_r,
        bl_l_on=bleg.l_on, bl_l_tap=bleg.l_tap, bl_l_bar=bleg.l_bar,
        bl_s_on=bleg.s_on, bl_s_tap=bleg.s_tap, bl_s_bar=bleg.s_bar,
        bl_l_top=bleg.l_top, bl_l_bot=bleg.l_bot, bl_l_inv=bleg.l_inv, bl_l_tgt=bleg.l_tgt,
        bl_s_top=bleg.s_top, bl_s_bot=bleg.s_bot, bl_s_inv=bleg.s_inv, bl_s_tgt=bleg.s_tgt,
        **exits,
    )


def compare(df: pd.DataFrame, decisions, bleg_states, warmup: int = 0,
            price_tol: float = 0.01, r_tol: float = 0.02) -> List[str]:
    """Diff the Pine export against the Python stream. Returns the mismatch list (empty
    = exit 0). Bars are aligned by POSITION — `run(bars, warmup=0)` keeps one decision per
    CSV row, and `warmup` only suppresses REPORTING, so a cold-start engine cannot mask a
    late drift by shifting the alignment."""
    ex = _expand(df)
    msgs: List[str] = []
    n = min(len(ex), len(decisions), len(bleg_states))
    for i in range(warmup, n):
        row = ex.iloc[i]
        if not row["_px_present"]:
            continue
        py = _py_row(decisions[i], bleg_states[i])
        when = pd.to_datetime(row["time"], unit="s") if "time" in ex.columns else i
        for col in _BOOL:
            if col not in ex.columns:
                continue
            if bool(row[col]) != bool(py[col]):
                msgs.append(f"bar {i} {when} {col}: py={py[col]} pine={row[col]}")
        for col in _INT:
            if col not in ex.columns:
                continue
            a, b = py[col], row[col]
            if (a is None) != (b is None or pd.isna(b)):
                msgs.append(f"bar {i} {when} {col}: py={a} pine={b}")
            elif a is not None and b is not None and not pd.isna(b) and int(a) != int(b):
                msgs.append(f"bar {i} {when} {col}: py={a} pine={int(b)}")
        for col in _PRICE:
            if col not in ex.columns:
                continue
            a, b = py[col], row[col]
            b = None if b is None or pd.isna(b) else float(b)
            if (a is None) != (b is None):
                msgs.append(f"bar {i} {when} {col}: py={a} pine={b}")
            elif a is not None and abs(a - b) > price_tol:
                msgs.append(f"bar {i} {when} {col}: py={a} pine={b}")
        if "px_closed_r" in ex.columns:
            a = py["px_closed_r"]
            b = row["px_closed_r"]
            b = None if b is None or pd.isna(b) else float(b)
            if (a is None) != (b is None):
                msgs.append(f"bar {i} {when} px_closed_r: py={a} pine={b}")
            elif a is not None and abs(a - b) > r_tol:
                msgs.append(f"bar {i} {when} px_closed_r: py={a} pine={b}")
        if msgs:
            break        # first divergence is the only useful one — everything after it is downstream
    return msgs


def run_parity(path, warmup: int = 0, price_tol: float = 0.01, r_tol: float = 0.02,
               base_config: Optional[BLegConfig] = None) -> List[str]:
    """Load, configure, replay, diff. Returns the mismatch list (empty = exit 0)."""
    df = load_export(path)
    cfg = config_from_export(df, base_config)
    bars = df[["open", "high", "low", "close"]].copy()
    strat = MpcBLegStrategy(cfg).run(bars, warmup=0)   # keep all bars aligned to CSV rows
    return compare(df, strat.decisions, strat.bleg_states, warmup, price_tol, r_tol)


def main() -> int:
    ap = argparse.ArgumentParser(description="B-LEG strategy logic-parity check (Python vs Pine export)")
    ap.add_argument("csv", help="mpc_b_leg_strategy_export.pine chart-data CSV")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars (engine cold-start)")
    ap.add_argument("--price-tol", type=float, default=0.01, help="price match tolerance (default 1 tick)")
    ap.add_argument("--r-tol", type=float, default=0.02, help="R match tolerance")
    a = ap.parse_args()
    msgs = run_parity(Path(a.csv), a.warmup, a.price_tol, a.r_tol)
    if not msgs:
        print(f"PARITY OK — Python == Pine on every bar from {a.warmup} on.")
        return 0
    print("PARITY MISMATCH — first diverging bar:")
    for m in msgs[:10]:
        print(" ", m)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
