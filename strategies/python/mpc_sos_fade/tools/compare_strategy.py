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
# Slot 2 landed 2026-07-28 with "Structure + % ratchet", which also became the DEFAULT.
# An export taken before that date encodes the old binary `Fixed step?0:1`, and its 1 still
# decodes to "Structure (swing)" — correct, because that is what those exports ran. Only 2
# is new, so older exports stay readable rather than silently mapping to the new default.
_RUNNER_TRAIL = {0: "Fixed step", 1: "Structure (swing)", 2: "Structure + % ratchet"}
_TP2_STOP = {0: "TP1 price", 1: "Breakeven", 2: "One trail step behind"}
_MIN_STOP = {0: "Off", 1: "% of price", 2: "Fixed $", 3: "x ATR(14)"}
_TIME_STOP = {0: "Off", 1: "Before TP1 only", 2: "Always"}
_POI_SOURCE = {0: "FVG", 1: "Order block", 2: "Either"}

# decision columns compared, after _expand_packed() has unpacked cfg_bits/px_dec_bits/etc.
_DEC_BOOL = ["px_long_armed", "px_short_armed", "px_long_veto", "px_short_veto"]
_DEC_INT = ["px_l_stage", "px_s_stage"]
_DEC_PRICE = ["px_edge", "px_stop", "px_entry_price",
              "px_exit_tp1", "px_exit_tp2", "px_exit_run"]


def config_from_export(df: pd.DataFrame, base: Optional[SosFadeConfig] = None,
                       allow_bleg: bool = False) -> SosFadeConfig:
    """Build a config from the export's packed cfg_* columns (constant per run — read from
    the first row). Columns absent from the export keep the base default, so a toggle the
    Pine doesn't export stays where the caller put it.

    The returned config is the SAME CLASS as `base`, which is what lets the B-LEG harness
    (`mpc_bleg/tools/compare_bleg.py`) reuse this decoder: it passes a `BLegConfig` and gets
    one back, subclass-only fields (`bleg_max_days`) untouched. Both exports pack cfg_* with
    one scheme deliberately — one decoder, two bots."""
    cls = type(base) if base is not None else SosFadeConfig
    vals = dict(base.__dict__) if base else dict(SosFadeConfig().__dict__)
    if len(df) == 0:
        return cls(**vals)
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
            exec_aplus=bool(b & 16384), exec_bleg=bool(b & 32768),
            # The 2026-08-02 entry model. Bit 65536 is RETIRED (execFvg50) — see the guard
            # below — so these start at 131072. An export taken BEFORE that date has all five
            # clear, which decodes to Method 3 alone with the pre-zone gate off: exactly the
            # build it was taken from, so an archived export still replays correctly.
            exec_fib_overlap=bool(b & 131072), exec_fib_deep_edge=bool(b & 262144),
            exec_fib_nearest=bool(b & 524288), exec_fvg_pre_zone=bool(b & 1048576),
            exec_sl_deep=bool(b & 2097152),
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
        # Bit 65536 carried Pine execFvg50 (a gap STRADDLING 0.5, limit resting at 0.5) from
        # 2026-07-24 until that input was DELETED from mpc_strategy.pine on 2026-08-02 — it was
        # never ported here, and never used. A fresh export cannot set the bit any more, so this
        # guard only fires on an ARCHIVED export taken while the input still existed and was on.
        # That is exactly why it is kept, and why it is read straight off the bit rather than
        # through a config field the bot no longer has: without it an old export would be
        # diffed against logic this bot has never had, and report a meaningless mismatch.
        if b & 65536:
            raise SystemExit(
                "This export was taken with 'Entry (least favorable): FVG must touch the 0.5 "
                "line' ON (cfg_bits bit 65536). That Pine input was removed on 2026-08-02 and "
                "was never ported to the Python bot, so this export predates the current build "
                "and the comparison would be meaningless. Re-export from the current "
                "mpc_strategy_export.pine."
            )
        # Bit 32768 (Pine execBLeg) turns on a SECOND setup type the A+ bot does not implement
        # at all — those trades live in `strategies/python/mpc_bleg/`. An export with it on
        # carries B-leg entries the A+ decision stream can never reproduce.
        # `allow_bleg=True` is the B-LEG harness saying "that bot IS the B leg" — its export
        # always ships execBLeg on, so the refusal would block the only run that matters there.
        # The execConfSZ / execFvg50 refusals above are NOT opt-out: both change `longEdge` /
        # `shortEdge`, which feed `longArmed` / `shortArmed`, which is the B leg's priority gate
        # — so an unported entry path corrupts the B-LEG decision stream too.
        if vals.get("exec_bleg") and not allow_bleg:
            raise SystemExit(
                "This export was taken with 'Trade B-Leg setups' ON (cfg_bits bit 32768). The "
                "B LEG is a separate bot (strategies/python/mpc_bleg/), so this A+ comparison "
                "would diff against trades it never makes. Re-export with it OFF."
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
    # Exit ladder (added 2026-07-26 alongside the structure runner trail). cfg_exitmode packs
    # the two dropdowns; the numerics are raw columns. An OLDER export has none of these, so
    # each one falls back to the base default — and for `exec_runner_trail` that fallback is
    # now "Structure (swing)", i.e. an export predating the columns would be read as structure
    # even if the Pine ran fixed-step. Warn loudly rather than diff on a guess.
    em = get("cfg_exitmode")
    if em is None:
        # Do NOT fall back to the config default here. Since 2026-07-28 that default is
        # "Structure + % ratchet", which NO export predating the column ever ran — so the
        # silent fallback would diff a ratcheted Python against a non-ratcheted Pine and
        # report pure drift as a bug. "Structure (swing)" is the least-wrong assumption
        # (it is what the 2026-07-25 → 2026-07-28 window ran); anything older ran fixed
        # step and is not recoverable from this file at all.
        vals["exec_runner_trail"] = "Structure (swing)"
        print("WARNING: no cfg_exitmode column — this export predates 2026-07-26 and does not "
              "record the runner trail or the TP2 stop floor. Assuming the runner trail was "
              "'Structure (swing)' (NOT the current default) and the rest at their defaults; "
              "re-export to compare them honestly.")
    else:
        e = int(round(em))
        vals["exec_runner_trail"] = _RUNNER_TRAIL.get(e // 10, vals["exec_runner_trail"])
        vals["exec_tp2_stop_mode"] = _TP2_STOP.get(e % 10, vals["exec_tp2_stop_mode"])
    for col, field in (("cfg_struct_buf", "exec_struct_trail_buf_tk"),
                       ("cfg_trail_pct", "exec_trail_pct"),
                       ("cfg_trail_step", "exec_trail_step"),
                       ("cfg_tp1_pct", "exec_tp1_pct"),
                       ("cfg_tp2_pct", "exec_tp2_pct"),
                       ("cfg_be_buf", "exec_be_buf_tk"),
                       ("cfg_sl_buf", "exec_sl_buf_tk"),
                       ("cfg_scratch_r", "exec_scratch_r")):
        v = get(col)
        if v is not None:
            vals[field] = float(v)
    # Minimum stop distance (added 2026-07-30) — an ENTRY filter that can refuse a setup on
    # PRICE. An export with no column predates it, and the parent shipped the mode "Off" from
    # the day it was added, so "absent ⇒ Off" is a FACT about those exports rather than a
    # guess — which is why this needs no warning, unlike cfg_exitmode above (whose default
    # moved under it). Do not "improve" this to fall back on the base config: the moment the
    # Python default is anything but Off, that would refuse setups the exported Pine took.
    ms = get("cfg_min_stop")
    vals["exec_min_stop_mode"] = "Off" if ms is None else \
        _MIN_STOP.get(int(round(ms)), vals["exec_min_stop_mode"])
    msv = get("cfg_min_stop_val")
    if msv is not None:
        vals["exec_min_stop_val"] = float(msv)
    # Time stop (added 2026-08-05) — same shape and same reasoning as the minimum-stop guard
    # directly above: an export with no column predates the lever, and the parent shipped it
    # "Off" from the day it was added, so "absent ⇒ Off" is a FACT about those exports rather
    # than a guess. Do NOT fall back on the base config here — the moment the Python default is
    # anything but Off, that would close positions the exported Pine held to the end, and the
    # diff would report the harness's own configuration as a logic bug.
    tsm = get("cfg_time_stop")
    vals["exec_time_stop_mode"] = "Off" if tsm is None else \
        _TIME_STOP.get(int(round(tsm)), vals["exec_time_stop_mode"])
    tsh = get("cfg_time_stop_hrs")
    if tsh is not None and float(tsh) > 0:
        # Guarded because the config REFUSES 0 hours behind a live mode (it would close every
        # position one bar after its fill). A 0 in this column can only come from an export
        # taken with the lever Off, where the value is never read anyway.
        vals["exec_time_stop_hrs"] = float(tsh)
    # POI source (added 2026-08-09) — WHICH ZONE the entry may read: fair value gaps, order
    # blocks, or both. Same shape and same reasoning as the two decoders directly above: an
    # export with no column predates the lever, and the parent shipped "FVG" from the day it
    # was added, so "absent ⇒ FVG" is a FACT about those exports rather than a guess.
    #
    # ⚠ This is the most trade-changing column in the file and the one most worth being strict
    # about. It decides which zones EXIST, so it decides which setups arm, where the limit
    # rests and which trades happen at all — a wrong value here does not shift a price by a
    # tick, it diffs two different strategies and reports the difference as an entry-rule bug.
    # Do NOT fall back on the base config: the moment the Python default is anything but FVG,
    # every older export silently decodes as a run it never made. That is exactly how
    # cfg_eq_exempt produced a three-day window of exports that cannot say what they ran.
    #
    # Nothing needs to switch the order-block ENGINE on here — MpcSosFadeStrategy.stack_config()
    # reads this field and adds `order_blocks=True` to whatever EngineConfig it is handed, so
    # the engine follows the config rather than the harness having to remember. If it did not,
    # the blind stack would raise PoiSourceUnavailable rather than quietly finding no blocks.
    ps = get("cfg_poi_source")
    vals["exec_poi_source"] = "FVG" if ps is None else \
        _POI_SOURCE.get(int(round(ps)), vals["exec_poi_source"])
    return cls(**vals)


class EqExemptUnknown(RuntimeError):
    """The export cannot say whether the EQ/FVG coupling was on, and neither can we."""


def engine_config_from_export(df: pd.DataFrame, base, eq_exempt: Optional[bool] = None):
    """Overlay the export's ENGINE settings onto the bot's pins.

    Everything in `engine_config()` mirrors a Pine CONSTANT and so is pinned rather than exported —
    except `eqExemptFvg`, which is an INPUT, and which decides whether a gap sitting on an EQH/EQL
    survives the FVG cap. That changes which gaps exist, hence which entries fire, so a run
    configured off the wrong value is diffing two different strategies.

    🔴 It had no column until 2026-08-06 and that is what made the failure unreadable: the Pine
    defaulted it ON on 2026-08-03, the Python side wired no EQ engine into the FVG engine at all,
    and the harness reported the resulting gap-SET difference as an entry-RULE mismatch at one bar.

    ⚠ AN ABSENT COLUMN IS REFUSED, NOT DEFAULTED, AND THAT IS THE WHOLE POINT OF THIS FUNCTION.
    Every other "absent ⇒ Off" decoder in this file is honest because the INPUT and its COLUMN
    landed together, so a column-less export provably ran the lever off. Not here: the input
    shipped on 2026-08-01 and defaulted ON on 2026-08-03, three days before the column, so an
    export from that window ran it ON while an older one ran it OFF and **the file cannot tell you
    which**. Guessing either way produces a confident green over two different strategies — the
    exact failure this column exists to end. Re-export, or state it with `--eq-exempt`.
    """
    import dataclasses
    col = "cfg_eq_exempt"
    if eq_exempt is None:
        if col not in df.columns:
            raise EqExemptUnknown(
                "This export has no `cfg_eq_exempt` column, so it cannot say whether "
                "`eqExemptFvg` (a gap on an EQ level surviving the FVG cap) was on — and that "
                "input decides WHICH GAPS EXIST, so it decides which entries fire.\n"
                "  It defaulted ON in mpc_strategy.pine on 2026-08-03 and the column landed "
                "2026-08-06, so exports from that window ran it ON and older ones ran it OFF.\n"
                "  Re-export off the current export Pine, or state what the chart ran with "
                "`--eq-exempt on|off`."
            )
        s = df[col].dropna()
        eq_exempt = bool(s.iloc[0]) if len(s) else False
    return dataclasses.replace(base, eq_exempt_fvg=eq_exempt)


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
    if run_px is None:
        # Anything that is not a TP rung closes the RUNNER slot, which is the slot Pine plots
        # `px_exit_run` from. Stated as "not a rung" rather than as a list of force-close leg
        # names on purpose: this used to read `endswith("CLOSE")`, so when the time stop added an
        # `L-TIME` / `S-TIME` leg the harness silently reported NO EXIT and blamed the strategy —
        # a clock exit that matched Pine to the cent showed as `py=None pine=3855.13`. A parity
        # tool that has to be taught every new leg name will keep failing this way, and it fails
        # in the worst direction: it manufactures a mismatch in code that is correct.
        f = next((f for f in dec.fills if f.kind == "exit"
                  and not f.order_id.endswith(("TP1", "TP2"))), None)
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
               r_tol: float = 0.02, base_config: Optional[SosFadeConfig] = None,
               eq_exempt: Optional[bool] = None) -> List[str]:
    """Load, configure, replay, diff. Returns the mismatch list (empty = exit 0)."""
    df = load_export(path)
    cfg = config_from_export(df, base_config)
    bars = df[["open", "high", "low", "close"]].copy()
    eng = engine_config_from_export(df, MpcSosFadeStrategy.engine_config(), eq_exempt)
    # keep all bars aligned to CSV rows
    strat = MpcSosFadeStrategy(cfg).run(bars, engine_config=eng, warmup=0)
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
    ap.add_argument("--eq-exempt", choices=("on", "off"), default=None,
                    help="state whether the chart ran `eqExemptFvg` (a gap on an EQ level "
                         "surviving the FVG cap). Only needed for an export with no "
                         "cfg_eq_exempt column — i.e. taken before 2026-08-06.")
    ap.add_argument("--debug-arm", action="store_true",
                    help="diff the A+ arming INPUTS (recentSSL / session-gap / arm-state) "
                         "against the export's dbg_* columns, to locate an arming gap")
    args = ap.parse_args(argv)

    # A truncated export (Pine's bar_index runs past the CSV row count) means Pine warmed its
    # engine on history the file does not contain, so row 0 can never match. It does NOT mean
    # the export is unusable: replay far enough and the Python engine converges on the same
    # state, which is exactly how `compare_bleg.py` handles the same situation. So warn, and
    # require a warmup at least as deep as the missing history rather than refusing outright.
    # (The `px_*` decision stream carries no bar-index column, so nothing in the main diff is
    # in chart coordinates — unlike `--debug-arm` below, which reads the `dbg_*` bar indices
    # directly and genuinely cannot be corrected for. See the standing rule in
    # strategies/CLAUDE.md: a parity column holding a Pine bar index is export-window-relative.)
    _df = load_export(args.csv)
    _gap = export_truncation(_df)
    if _gap > 0:
        print(f"PARTIAL EXPORT — the CSV is missing ~{_gap} warmup bars.")
        print(f"  Pine's bar_index runs past the {len(_df)} exported rows, so its engine state was")
        print(f"  built on ~{_gap} bars that aren't in this file. For a clean run, re-export the")
        print(f"  FULL history: scroll the chart all the way left (load the oldest bar) before")
        print(f"  Export chart data, so row 0 is the chart's first bar.")
        if args.debug_arm:
            print("  --debug-arm compares dbg_* BAR INDICES, which are chart-relative here and")
            print("  cannot be corrected for. Re-export the full history and re-run.")
            return 2
        if args.warmup < _gap:
            print(f"  Refusing to diff at --warmup {args.warmup}: the Python engine is still cold.")
            print(f"  Re-run with --warmup {_gap} or more ({len(_df) - _gap} bars would remain).")
            return 2
        print(f"  Proceeding at --warmup {args.warmup} (>= the missing {_gap}); "
              f"{len(_df) - args.warmup} bars compared.")

    if args.debug_arm:
        msgs = debug_arm(args.csv, args.warmup)
        if not msgs:
            print(f"ARM OK — arming inputs + state match the Pine on every bar from {args.warmup} on.")
            return 0
        print("\n".join(msgs))
        return 1

    eq = None if args.eq_exempt is None else (args.eq_exempt == "on")
    try:
        msgs = run_parity(args.csv, args.warmup, args.price_tol, args.r_tol, eq_exempt=eq)
    except EqExemptUnknown as exc:
        print(f"CANNOT DIFF — {exc}")
        return 2
    if not msgs:
        print(f"PARITY OK — Python == Pine on every bar from {args.warmup} on.")
        return 0
    print("PARITY MISMATCH — first diverging bar:")
    print("  " + msgs[0])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
