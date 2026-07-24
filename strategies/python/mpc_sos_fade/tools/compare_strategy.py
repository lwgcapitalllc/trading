"""compare_strategy.py — the A+ LOGIC-PARITY check.

Reads a TradingView "Export chart data" CSV of `mpc_strategy_export.pine` — the
instrumented strategy that plots its per-bar DECISION STREAM (armed / edge / stage /
veto / stop / fills / R) plus every input toggle as a column — replays the export's
OWN bars through the Python bot configured to the SAME toggles, and diffs the two
decision streams bar by bar.

Exit 0 = the Python makes the identical decisions as the Pine. On a mismatch it names
the FIRST bar and field that diverged, so you know exactly where they parted. This is
the standing regression harness: run it whenever the Pine changes (see the build plan).

This is LOGIC parity (same decisions on the SAME candles), NOT feed parity (do MT5's
candles match TradingView's — that's backtest/tools/compare_feeds.py). They never mix:
logic parity replays TradingView's own bars, so the broker feed is irrelevant here.

Usage:
    python compare_strategy.py <export.csv> [--warmup N] [--price-tol 0.01] [--r-tol 0.02]

Stdlib + pandas (matches backtest/tools/compare_feeds.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ── make the bot importable standalone (CLI / CI), same shim as strategy.py ──
_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

from mpc_sos_fade import SosFadeConfig, MpcSosFadeStrategy  # noqa: E402
from mpc_sos_fade.execution import Decision  # noqa: E402


# ── packed-column decoders — MUST match mpc_strategy_export.pine's plot scheme ──
# The base strategy sits under Pine's main-body statement cap, so the export packs many
# values into few plots. Strings can't be plot()ed either, so the string dropdowns are
# int codes. Every scheme below is mirrored exactly in the Pine's PARITY EXPORT block.
_SL_LEVEL = {0: "0.618", 1: "0.702", 2: "0.786", 3: "0.886", 4: "1.0"}
_HTF_SRC = {0: "Weekly", 1: "Daily", 2: "Either"}
_HTF_REQ = {0: "Ignore", 1: "Must agree", 2: "Must not oppose", 3: "Must oppose (reversal)"}

# decision columns compared, after _expand_packed() has unpacked cfg_bits/px_dec_bits/etc.
_DEC_BOOL = ["px_long_armed", "px_short_armed", "px_long_veto", "px_short_veto"]
_DEC_INT = ["px_l_stage", "px_s_stage"]
_DEC_PRICE = ["px_edge", "px_stop", "px_entry_price",
              "px_exit_tp1", "px_exit_tp2", "px_exit_run"]


def config_from_export(df: pd.DataFrame, base: Optional[SosFadeConfig] = None) -> SosFadeConfig:
    """Build an SosFadeConfig from the export's packed cfg_* columns (constant per run —
    read from the first row). Columns absent from the export keep the base default, so
    the numeric toggles the Pine doesn't export (tp %, buffers, trail, scratch) stay at
    their shared defaults."""
    vals = dict(base.__dict__) if base else dict(SosFadeConfig().__dict__)
    if len(df) == 0:
        return SosFadeConfig(**vals)
    row = df.iloc[0]

    def get(col):
        return None if col not in df.columns or pd.isna(row[col]) else row[col]

    bits = get("cfg_bits")
    if bits is not None:
        b = int(round(bits))
        vals.update(
            exec_longs=bool(b & 1), exec_shorts=bool(b & 2), exec_arm_sweep=bool(b & 4),
            exec_arm_div=bool(b & 8), exec_req_fvg=bool(b & 16), exec_fvg_deep_only=bool(b & 32),
            exec_respect_veto=bool(b & 64), exec_close_opp_sos=bool(b & 128),
            exec_htf_exhaust_only=bool(b & 256), exec_no_late_day=bool(b & 512),
            show_div=bool(b & 1024), div_veto=bool(b & 2048),
            exec_conf_sz=bool(b & 4096), exec_deep_fib=bool(b & 8192),
        )
        # Bit 4096 (Pine execConfSZ, added 2026-07-21) turns the Sniper Zone into a second
        # accepted entry confirmation. The Python bot has NOT ported that path yet, so an
        # export made with it on would diff against logic this bot does not have — refuse
        # rather than report a meaningless mismatch (or a meaningless green).
        if vals.get("exec_conf_sz"):
            raise SystemExit(
                "This export was taken with 'Allow Sniper Zone as entry confirmation' ON "
                "(cfg_bits bit 4096). That Pine path is not ported to the Python bot yet, so "
                "the comparison would be meaningless. Re-export with it OFF, or port it first."
            )
    sc = get("cfg_strcodes")
    if sc is not None:
        s = int(round(sc))
        vals["exec_sl_level"] = _SL_LEVEL.get(s // 1000, vals["exec_sl_level"])
        vals["exec_htf_source"] = _HTF_SRC.get((s // 100) % 10, vals["exec_htf_source"])
        vals["exec_htf_weekly"] = _HTF_REQ.get((s // 10) % 10, vals["exec_htf_weekly"])
        vals["exec_htf_daily"] = _HTF_REQ.get(s % 10, vals["exec_htf_daily"])
    di = get("cfg_divints")
    if di is not None:
        d = int(round(di))
        vals["div_extreme_os"] = d % 1000
        vals["div_extreme_ob"] = (d // 1000) % 1000
        vals["div_rsi_len"] = (d // 1_000_000) % 1000
        vals["div_pivot_len"] = (d // 1_000_000_000) % 1000
        vals["div_valid_bars"] = (d // 1_000_000_000_000) % 1000
    w = get("cfg_window")
    if w is not None:
        vals["aplus_window"] = int(round(w))
    r = get("cfg_risk_pct")
    if r is not None:
        vals["exec_risk_pct"] = float(r)
    return SosFadeConfig(**vals)


def _expand_packed(df: pd.DataFrame) -> pd.DataFrame:
    """Unpack the export's packed decision columns into the flat px_* names the compare
    loop reads. cfg_* are handled separately in config_from_export."""
    if "px_dec_bits" in df.columns:
        b = df["px_dec_bits"].fillna(0).round().astype("int64")
        df["px_long_armed"] = (b & 1) != 0
        df["px_short_armed"] = (b & 2) != 0
        df["px_long_veto"] = (b & 4) != 0
        df["px_short_veto"] = (b & 8) != 0
        df["px_entry_dir"] = b.map(lambda x: 1 if x & 16 else (-1 if x & 32 else 0))
    if "px_stages" in df.columns:
        s = df["px_stages"].fillna(0).round().astype("int64")
        df["px_l_stage"] = s // 10
        df["px_s_stage"] = s % 10
    # TradingView leaves the final (still-forming) bar's plotted series blank, so its packed
    # decision columns export as NaN. That is a non-bar, not a decision of 0 — mark it so the
    # compare loop skips it instead of reading a fillna(0) as a real "no arm / stage 0".
    if "px_dec_bits" in df.columns and "px_stages" in df.columns:
        df["_px_present"] = df["px_dec_bits"].notna() & df["px_stages"].notna()
    else:
        df["_px_present"] = True
    return df


def load_export(path: Path) -> pd.DataFrame:
    """Read the export CSV into a canonical frame: DatetimeIndex 'time' (UTC) + OHLC +
    whatever px_* / cfg_* columns are present, with packed columns expanded."""
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get("time")
    if tcol is None:
        raise ValueError("export has no 'time' column")
    t = df[tcol]
    if pd.api.types.is_numeric_dtype(t):
        idx = pd.to_datetime(t, unit="s", utc=True)          # TradingView unix seconds
    else:
        idx = pd.to_datetime(t, utc=True)
    df.index = idx.dt.tz_convert("UTC").dt.tz_localize(None)
    df.index.name = "time"
    for src, dst in (("open", "open"), ("high", "high"), ("low", "low"), ("close", "close")):
        if src in cols:
            df[dst] = pd.to_numeric(df[cols[src]], errors="coerce")
    return _expand_packed(df)


def _decision_row(dec: Decision) -> Dict[str, object]:
    """Flatten a Python Decision to the export's column shape for comparison. The entry
    edge is a single `px_edge`: long_edge and short_edge are mutually exclusive (fibo_dir
    is either +1 or -1), matching the Pine's `na(longEdge) ? shortEdge : longEdge`."""
    entry = next((f for f in dec.fills if f.kind == "entry"), None)
    def exit_px(suffix):
        f = next((f for f in dec.fills if f.kind == "exit" and f.order_id.endswith(suffix)), None)
        return f.price if f else None
    run_px = exit_px("RUN")
    if run_px is None:  # a force-close (opp-SOS / flat-by-close) exits the runner slot
        f = next((f for f in dec.fills
                  if f.kind == "exit" and (f.order_id.endswith("CLOSE"))), None)
        run_px = f.price if f else None
    edge = dec.long_edge if dec.long_edge is not None else dec.short_edge
    return {
        "px_long_armed": dec.long_armed, "px_short_armed": dec.short_armed,
        "px_long_veto": dec.long_veto, "px_short_veto": dec.short_veto,
        "px_l_stage": dec.l_stage, "px_s_stage": dec.s_stage,
        "px_edge": edge, "px_stop": dec.stop,
        "px_entry_price": entry.price if entry else None,
        "px_entry_dir": (entry.dir if entry else 0),
        "px_exit_tp1": exit_px("TP1"), "px_exit_tp2": exit_px("TP2"), "px_exit_run": run_px,
        "px_closed_r": dec.closed_r,
    }


def compare(df: pd.DataFrame, decisions: List[Decision], warmup: int,
            price_tol: float, r_tol: float) -> List[str]:
    """Diff the Python decision stream against the export's px_* columns from `warmup`
    on. Returns a list of human-readable mismatch messages (empty = parity)."""
    msgs: List[str] = []
    n = min(len(df), len(decisions))
    for i in range(warmup, n):
        row = df.iloc[i]
        if "_px_present" in df.columns and not bool(row["_px_present"]):
            continue  # TradingView exported no decision values for this bar (the forming bar)
        py = _decision_row(decisions[i])
        when = df.index[i]

        # booleans + ints — exact
        for col in _DEC_BOOL:
            if col not in df.columns:
                continue
            pine = _as_bool(row[col])
            if bool(py[col]) != pine:
                msgs.append(f"bar {i} {when} {col}: py={py[col]} pine={pine}")
        for col in _DEC_INT:
            if col not in df.columns:
                continue
            pine = int(round(row[col])) if not pd.isna(row[col]) else 0
            if int(py[col]) != pine:
                msgs.append(f"bar {i} {when} {col}: py={py[col]} pine={pine}")

        # prices — tolerance; na on both sides is a match
        for col in _DEC_PRICE:
            if col not in df.columns:
                continue
            pine = None if pd.isna(row[col]) else float(row[col])
            got = py[col]
            if not _num_match(got, pine, price_tol):
                msgs.append(f"bar {i} {when} {col}: py={got} pine={pine}")

        # entry direction + R
        if "px_entry_dir" in df.columns:
            pine = int(round(row["px_entry_dir"])) if not pd.isna(row["px_entry_dir"]) else 0
            if int(py["px_entry_dir"]) != pine:
                msgs.append(f"bar {i} {when} px_entry_dir: py={py['px_entry_dir']} pine={pine}")
        if "px_closed_r" in df.columns:
            pine = None if pd.isna(row["px_closed_r"]) else float(row["px_closed_r"])
            if not _num_match(py["px_closed_r"], pine, r_tol):
                msgs.append(f"bar {i} {when} px_closed_r: py={py['px_closed_r']} pine={pine}")

        if msgs:  # stop at the FIRST diverging bar — that's the actionable one
            break
    return msgs


def _as_bool(v) -> bool:
    """Read a plotted boolean back from the CSV — the Pine writes 1/0, but a
    round-tripped Python bool can arrive as 'True'/'False' or True; handle all."""
    if pd.isna(v):
        return False
    if isinstance(v, str):
        return v.strip().lower() in ("1", "1.0", "true", "yes")
    return bool(round(float(v)))


def _num_match(a: Optional[float], b: Optional[float], tol: float) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def run_parity(path: Path, warmup: int = 0, price_tol: float = 0.01,
               r_tol: float = 0.02, base_config: Optional[SosFadeConfig] = None) -> List[str]:
    """Load, configure, replay, diff. Returns the mismatch list (empty = exit 0)."""
    df = load_export(path)
    cfg = config_from_export(df, base_config)
    bars = df[["open", "high", "low", "close"]].copy()
    strat = MpcSosFadeStrategy(cfg).run(bars, warmup=0)   # keep all bars aligned to CSV rows
    return compare(df, strat.decisions, warmup, price_tol, r_tol)


# ── arming-diagnostic mode (needs the export's dbg_* columns) ─────────────────────
# The final decision stream (px_*) tells you a mismatch happened; these dbg_* columns
# tell you WHY by exposing the arming block's INPUTS + arm-state, so a recentSSL /
# session-gap reconstruction gap can be located directly instead of inferred.
_SSL_CODE = {"": 0, "H4 Low": 1, "Day Low": 2, "Asia Low": 3, "Ldn Low": 4, "NY Low": 5}
_BSL_CODE = {"": 0, "H4 High": 1, "Day High": 2, "Asia High": 3, "Ldn High": 4, "NY High": 5}
# the arming fields compared, in report order
_ARM_FIELDS = ["ssl_bar", "bsl_bar", "ssl_code", "bsl_code", "session_gap",
               "l_sweep_bar", "l_sos_bar", "s_sweep_bar", "s_sos_bar"]


def _decode_dbg(row) -> Optional[Dict[str, int]]:
    """Unpack one export row's dbg_* columns into the Pine-side arming state. Returns
    None if the export has no diagnostic columns (old export — re-export needed)."""
    if "dbg_recent_bars" in row and not pd.isna(row["dbg_recent_bars"]):
        rb = int(round(row["dbg_recent_bars"]))
        src = int(round(row["dbg_recent_src"])) if not pd.isna(row.get("dbg_recent_src")) else 0
        bits = int(round(row["dbg_sweep_bits"])) if not pd.isna(row.get("dbg_sweep_bits")) else 0
        aL = int(round(row["dbg_armL_bars"])) if not pd.isna(row.get("dbg_armL_bars")) else 0
        aS = int(round(row["dbg_armS_bars"])) if not pd.isna(row.get("dbg_armS_bars")) else 0
        return {
            "ssl_bar": rb // 1_000_000 - 1, "bsl_bar": rb % 1_000_000 - 1,
            "ssl_code": src // 10, "bsl_code": src % 10,
            "session_gap": 1 if bits & 16 else 0,
            "new_sweep_l": 1 if bits & 1 else 0, "new_sweep_s": 1 if bits & 2 else 0,
            "too_old_l": 1 if bits & 4 else 0, "too_old_s": 1 if bits & 8 else 0,
            "l_sweep_bar": aL // 1_000_000 - 1, "l_sos_bar": aL % 1_000_000 - 1,
            "s_sweep_bar": aS // 1_000_000 - 1, "s_sos_bar": aS % 1_000_000 - 1,
        }
    return None


def _capture_arm(df: pd.DataFrame, cfg: SosFadeConfig) -> List[Dict[str, int]]:
    """Replay the bot capturing each bar's arming INPUTS + post-update arm-state, in the
    same encoding _decode_dbg produces for the Pine side (-1 = none/na)."""
    import sys as _sys
    from pathlib import Path as _P
    _r = _P(__file__).resolve().parents[4]
    if str(_r) not in _sys.path:
        _sys.path.insert(0, str(_r))
    from backtest.replay import EngineStack, iter_bars

    bars = df[["open", "high", "low", "close"]].copy()
    strat = MpcSosFadeStrategy(cfg)
    stack = EngineStack(strat.engine_config())   # same fvgMaxCount=7 the bot runs with
    seq = strat.sequence
    rows: List[Dict[str, int]] = []

    def b(x):  # None -> -1
        return -1 if x is None else int(x)

    for bar in iter_bars(bars):
        state = stack.step(bar)
        sig = strat.signals.update(state)
        seq_state = seq.update(sig)                 # SeqState, returned by update()
        strat.execution.step(sig, seq_state)        # advance execution so nothing drifts
        rows.append({
            "ssl_bar": b(sig.recent_ssl_bar), "bsl_bar": b(sig.recent_bsl_bar),
            "ssl_code": _SSL_CODE.get(sig.recent_ssl, 0),
            "bsl_code": _BSL_CODE.get(sig.recent_bsl, 0),
            "session_gap": 1 if sig.session_gap_bar else 0,
            "l_sweep_bar": b(seq._l_sweep_bar), "l_sos_bar": b(seq._l_sos_bar),
            "s_sweep_bar": b(seq._s_sweep_bar), "s_sos_bar": b(seq._s_sos_bar),
        })
    return rows


def export_truncation(df: pd.DataFrame) -> int:
    """How many warmup bars the export is MISSING. Pine's bar_index counts from the
    chart's first loaded bar; if TradingView truncated the CSV to the most recent N
    rows, the dbg_* columns reference bar indices far past the row count. Returns the
    gap (max referenced Pine bar - last row index); >0 means the export starts mid-
    history and NO bot can match it — Pine warmed on bars that aren't in the file.
    Returns 0 when there are no dbg_* columns to measure."""
    if "dbg_recent_bars" not in df.columns:
        return 0
    n = len(df)
    max_bar = 0
    for col in ("dbg_recent_bars", "dbg_armL_bars", "dbg_armS_bars"):
        if col not in df.columns:
            continue
        s = df[col].fillna(0).round().astype("int64")
        # each packs two (value+1) fields base-1e6; the high field is the larger bar
        hi = (s // 1_000_000 - 1).max()
        lo = (s % 1_000_000 - 1).max()
        max_bar = max(max_bar, int(hi), int(lo))
    return max(0, max_bar - (n - 1))


def debug_arm(path: Path, warmup: int = 0,
              base_config: Optional[SosFadeConfig] = None) -> List[str]:
    """Diff the arming INPUTS + arm-state (Python vs the export's dbg_* columns) from
    `warmup` on. Returns messages; the first names the earliest diverging bar + field
    with a small context window so the liquidity/gap reconstruction gap is pinpointed."""
    df = load_export(path)
    if _decode_dbg(df.iloc[0]) is None:
        return ["export has no dbg_* columns — re-export mpc_strategy_export.pine "
                "(the diagnostic block was just added)."]
    cfg = config_from_export(df, base_config)
    py = _capture_arm(df, cfg)
    n = min(len(df), len(py))
    for i in range(warmup, n):
        pine = _decode_dbg(df.iloc[i])
        if pine is None:
            continue
        diffs = [f for f in _ARM_FIELDS if py[i][f] != pine[f]]
        if diffs:
            msgs = [f"ARM MISMATCH at bar {i} {df.index[i]} — fields: {', '.join(diffs)}"]
            lo, hi = max(0, i - 3), min(n, i + 2)
            for j in range(lo, hi):
                pj = _decode_dbg(df.iloc[j])
                mark = "  <<" if j == i else ""
                msgs.append(f"  bar {j} {df.index[j]}{mark}")
                for f in _ARM_FIELDS:
                    flag = " *" if py[j][f] != pj[f] else ""
                    msgs.append(f"      {f:14s} py={py[j][f]:>7} pine={pj[f]:>7}{flag}")
                msgs.append(f"      pine newSweepL={pj['new_sweep_l']} newSweepS={pj['new_sweep_s']}"
                            f" tooOldL={pj['too_old_l']} tooOldS={pj['too_old_s']}")
            return msgs
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A+ strategy logic-parity check (Python vs Pine export)")
    ap.add_argument("csv", type=Path, help="mpc_strategy_export.pine chart-data CSV")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars (engine cold-start)")
    ap.add_argument("--price-tol", type=float, default=0.01, help="price match tolerance (default 1 tick)")
    ap.add_argument("--r-tol", type=float, default=0.02, help="R match tolerance")
    ap.add_argument("--debug-arm", action="store_true",
                    help="diff the A+ arming INPUTS (recentSSL / session-gap / arm-state) "
                         "against the export's dbg_* columns, to locate an arming gap")
    args = ap.parse_args(argv)

    # A truncated export (Pine's bar_index runs past the CSV row count) can't be matched
    # by any bot — Pine warmed on history the file doesn't contain. Catch it up front.
    _df = load_export(args.csv)
    _gap = export_truncation(_df)
    if _gap > 0:
        print(f"TRUNCATED EXPORT — the CSV is missing ~{_gap} warmup bars.")
        print(f"  Pine's bar_index runs past the {len(_df)} exported rows, so its engine state was")
        print(f"  built on ~{_gap} bars that aren't in this file. Re-export the FULL history:")
        print(f"  scroll the chart all the way left (load the oldest bar) before Export chart data,")
        print(f"  so row 0 is the chart's first bar. Then re-run.")
        return 2

    if args.debug_arm:
        msgs = debug_arm(args.csv, args.warmup)
        if not msgs:
            print(f"ARM OK — arming inputs + state match the Pine on every bar from {args.warmup} on.")
            return 0
        print("\n".join(msgs))
        return 1

    msgs = run_parity(args.csv, args.warmup, args.price_tol, args.r_tol)
    if not msgs:
        print(f"PARITY OK — Python == Pine on every bar from {args.warmup} on.")
        return 0
    print("PARITY MISMATCH — first diverging bar:")
    print("  " + msgs[0])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
