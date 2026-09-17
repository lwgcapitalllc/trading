#!/usr/bin/env python3
"""compare_realign.py — the REALIGN logic-parity gate.

The fifth of the family, beside `sos_fade/tools/compare_strategy.py`, `b_leg/tools/compare_bleg.py`,
`bos/tools/compare_bos.py` and `extreme_leg/tools/compare_extreme_leg.py`. It reads a TradingView
"Export chart data" CSV of `strategies/tradingview/realign_strategy_export.pine`, replays the
export's OWN bars through this port CONFIGURED FROM THE EXPORT's own `cfg_*` columns, and diffs the
two decision streams bar by bar.

    python compare_realign.py <export.csv> [--warmup N] [--price-tol 0.01]

Exit 0 = this port makes the same decisions as the Pine, on the same candles.

🔴 **UNTIL THIS EXITS 0 ON A REAL EXPORT, EVERY REALIGN NUMBER IN THIS REPO IS A LAB FINDING, AND
THERE ARE A LOT OF THEM NOW.** Six runs of measurements, a random-entry control at z +2.36, a
retest entry that survived a holdout — all of it measured against a Python program with nothing
checking it against the file Aaron reads on a chart. This strategy is the repo's own worked example
of how that happens: it had no row in `docs/STRATEGY_WORKFLOW.md` until 2026-09-16.

⚠ **THIS IS LOGIC PARITY, NOT FEED PARITY.** It replays TradingView's own candles, so the broker's
feed is irrelevant here. Whether MT5's candles match TradingView's is a different question and a
different tool (`backtest/tools/compare_feeds.py`).

🔴 **THREE DISAGREEMENTS ARE EXPECTED ON THE FIRST RUN AND ARE WRITTEN DOWN BEFORE IT, so a red gate
is read rather than explained away.** Two are real differences of rule; the third is this tool's own
choice and is stated so nobody mistakes it for agreement.

  1. **THE TRAIL FRAME — the big one, and it is worth tens of R.** `realign_strategy.pine` has
     always anchored its runner trail on `hConfLo`/`hConfHi`, the **EXTERNAL** frame; this port has
     always used `sig.last_conf_low`, the **CHART** frame. The Pine's own comment on that line said
     "the chart frame's", describing the PORT, which is almost certainly how it happened. Measured
     in the port: chart/5m +45.14R over 162 trades, external/15m **−15.68R over 99**. Both frames'
     swings are exported (`px_htf_conf*`, `px_cht_conf*`) and the frame is now an input
     (`trailFrame`, in `cfg_enum1`), so this gate configures the port from the CSV and reports the
     anchor comparison separately — it can say *wrong frame* instead of *numbers differ*.
     ⚠ **The Pine's own Strategy Tester run was PROFITABLE (+41.35%), which the port's emulation of
     the external frame is not.** So a second difference may live in how `f_frameStructPrev`'s `[1]`
     shift and `lookahead_on` actually deliver those swings. **This gate is the instrument that
     settles it, and it is the reason the anchors are exported rather than only the trade.**

  2. **THE REWARD-TO-RISK GUARD.** The Pine guards entry with `tgtLong > close` (and the short
     mirror) and has no input for it. This Python has never had that check: `realign_min_rr`
     defaults `None`, and 7 of its 162 trades enter with the target already BEHIND the entry —
     which are not junk, they make +5.67R between them. **This gate therefore pins
     `realign_min_rr = 0.0`, which is the value that reproduces the Pine**, because a config must
     describe the EXPORT and not this side's defaults. ⚠ A green run here says nothing about
     whether `None` or `0.0` is the better rule — only that both sides agree when the port is set
     the Pine's way.

  3. **THE FRIDAY CLOCK.** The Pine reads the weekday in New York; this port reads it in UTC. They
     agree for the 16:45 NY window this rule is used at, and would NOT agree for a window near
     midnight NY. Expected to be invisible here, recorded so a future window change is not
     debugged from scratch.

⚠ **A GREEN RUN IS ONLY GREEN ABOUT THE BRANCHES BOTH SIDES ENTERED.** This repo has shipped a
setting on a parity run that never exercised it. So this prints a COVERAGE table — how many bars
each field was actually non-trivial on — and says so out loud when a branch was never taken. Read
it before believing the exit code.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python"), str(_ROOT / "engines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gate_common import drop_live_final_bar  # noqa: E402
from sos_fade.tools.compare_strategy import load_export, missing_columns_refusal  # noqa: E402

from realign.config import RealignConfig  # noqa: E402
from realign.strategy import RealignStrategy  # noqa: E402

# ⚠ These MUST match the export block's own bit scheme in
#   `strategies/tradingview/export_blocks/realign_strategy.pine`. A test holds them to it.
_STRUCT_BITS = {
    "bull_bos": 1, "bear_bos": 2, "bull_sos": 4, "bear_sos": 8,
    "h_bull_bos": 16, "h_bear_bos": 32, "h_bull_sos": 64, "h_bear_sos": 128,
    "htf_closed": 256,
}
_ARM_BITS = {
    "long_armed": 1, "short_armed": 2, "step_long": 4, "step_short": 8,
    "trig_long": 16, "trig_short": 32, "pos_long": 64, "pos_short": 128,
    "opened": 256, "closed": 512, "trend_up": 1024, "trend_dn": 2048,
}

# cfg_enum1, packed as decimal digits — each field < 10, so decoding is division and modulo.
_ENUM_ORDER = [
    ("exec_min_stop_mode", ["Off", "% of price", "Fixed $"]),
    ("exec_tp2_stop_mode", ["TP1 price", "Breakeven", "One trail step behind"]),
    ("exec_runner_trail", ["Fixed step", "Structure (swing)", "Structure + % ratchet"]),
    ("exec_time_stop_mode", ["Off", "Before TP1 only", "Always"]),
    ("realign_entry_mode", ["market", "retest"]),
    ("realign_retest_at", ["level", "mid"]),
    ("__flat_mode", ["Off", "Friday only", "Every day"]),
    ("realign_trail_frame", ["external", "chart"]),
]

_CFG_NUM = {
    "cfg_htf_min": ("realign_htf_minutes", int),
    "cfg_window_hrs": ("realign_window_hrs", float),
    "cfg_risk_pct": ("exec_risk_pct", float),
    "cfg_sl_buf": ("realign_sl_buf_tk", int),
    "cfg_min_stop": ("exec_min_stop_val", float),
    "cfg_tp1_pct": ("exec_tp1_pct", float),
    "cfg_tp2_pct": ("exec_tp2_pct", float),
    "cfg_be_buf": ("exec_be_buf_tk", float),
    "cfg_trail_pct": ("exec_trail_pct", float),
    "cfg_trail_step": ("exec_trail_step", float),
    "cfg_struct_buf": ("exec_struct_trail_buf_tk", float),
    "cfg_time_hrs": ("exec_time_stop_hrs", float),
    "cfg_retest_bars": ("realign_retest_bars", int),
    "cfg_flat_min": ("flat_by_close_min", int),
    "cfg_close_hr": ("daily_close_hour_ny", int),
}

# The N-day momentum filter (added 2026-09-16). Read OUTSIDE `_CFG_NUM` because the Pine's
# 0 means off and must become `None`, never a 0-day filter.
MOM_CFG = "cfg_mom_days"
# Its per-bar direction. Compared, and REQUIRED, only on an export that carries `MOM_CFG` —
# an export older than the filter ran with it off and has nothing to compare. That is scoping
# by what the export's own Pine could do, not a per-column skip: an export that states the
# setting and lacks the column is refused like any other.
MOM_PX = "px_mom_dir"

# EVERY column the diff reads, by its UNPACKED name. `missing_columns_refusal` is checked
# against this list, so "the decision stream" means one thing here and cannot drift from the
# loop. 🔴 An export missing a column compares LESS than "PARITY OK" claims — the defect that
# passed a file that was not the twin at all. Refuse, never narrow.
_COMPARED = [
    "px_struct", "px_arm",
    "px_tgt_l", "px_tgt_s", "px_ctr_l", "px_ctr_s", "px_lvl_l", "px_lvl_s",
    "px_htf_confhi", "px_htf_conflo", "px_cht_confhi", "px_cht_conflo",
    "px_pend_px", "px_pend_sl", "px_pend_age",
    "px_stop_live", "px_tp1", "px_tp2", "px_stage",
]


def _digit(v: int, place: int) -> int:
    return (v // (10 ** place)) % 10


def config_from_export(df: pd.DataFrame) -> Tuple[RealignConfig, List[str]]:
    """Build the port's config from the export's OWN settings columns.

    ⚠ **Never from this side's defaults.** A port replayed at its defaults against an export
    taken at somebody else's is comparing two different strategies, and the day gets spent
    looking for the bug in the wrong half. A column the export does not carry is REPORTED
    rather than defaulted silently — an older export missing a setting is a narrower gate, and
    the reader has to be told which one.
    """
    vals = dict(RealignConfig().__dict__)
    missing: List[str] = []
    if len(df) == 0:
        return RealignConfig(**vals), ["the export has no rows"]
    row = df.iloc[0]

    def get(col):
        return None if col not in df.columns or pd.isna(row[col]) else float(row[col])

    bits = get("cfg_bits")
    if bits is None:
        missing.append("cfg_bits (trade longs / trade shorts)")
    else:
        b = int(round(bits))
        vals["realign_longs"] = bool(b & 1)
        vals["realign_shorts"] = bool(b & 2)

    enum = get("cfg_enum1")
    if enum is None:
        missing.append("cfg_enum1 (every dropdown)")
    else:
        e = int(round(enum))
        for place, (field, options) in enumerate(_ENUM_ORDER):
            idx = _digit(e, place)
            if idx >= len(options):
                missing.append(f"cfg_enum1 digit {place} = {idx}, which names no option")
                continue
            if field == "__flat_mode":
                # One Pine dropdown, two Python flags — Friday-only lives on this fork and the
                # daily one is inherited. Both are set explicitly so neither can be left at a
                # default the export never chose.
                vals["realign_flat_before_weekend"] = options[idx] == "Friday only"
                vals["flat_by_close"] = options[idx] == "Every day"
            else:
                vals[field] = options[idx]

    for col, (field, cast) in _CFG_NUM.items():
        v = get(col)
        if v is None:
            missing.append(col)
        else:
            vals[field] = cast(round(v)) if cast is int else cast(v)

    # The momentum filter: the Pine's 0 is "off", which is `None` here. 🔴 An export older than
    # the filter carries no column, and its Pine could not run the filter — so it is set OFF
    # explicitly, never left at this side's default. The default is ON (20) since 2026-09-16;
    # inheriting it would replay the older exports WITH a filter their chart never had.
    mom = get(MOM_CFG)
    if mom is None:
        missing.append(MOM_CFG)
        vals["realign_mom_days"] = None
    else:
        vals["realign_mom_days"] = int(round(mom)) or None

    # 🔴 PINNED, and it is this tool's own choice rather than something the export states.
    # The Pine guards entry with `tgtLong > close` and has no input for it, so no `cfg_*`
    # column can carry it; `0.0` is the value that reproduces that guard and `None` — this
    # side's default — is the value that does not. A config must describe the EXPORT.
    # See disagreement 2 at the top of this file.
    vals["realign_min_rr"] = 0.0
    return RealignConfig(**vals), missing


def _f(v) -> float:
    """A CSV cell as a float, with a blank cell reading as Pine's `na`."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _n(v) -> float:
    """A Python Optional as a float, with `None` reading as `na`."""
    return float("nan") if v is None else float(v)


def _same(a: float, b: float, tol: float) -> bool:
    """Two numbers agree, with `na == na` and `na != a number`.

    ⚠ A missing value and a value are DIFFERENT, and collapsing them is the failure this repo
    keeps re-learning. `nan == nan` is False in IEEE arithmetic, so it has to be said.
    """
    an, bn = math.isnan(a), math.isnan(b)
    if an or bn:
        return an and bn
    return abs(a - b) <= tol


def _wrong_export(path: Path) -> Optional[str]:
    """Refuse a CSV that is not an export of THIS twin, reading the header and nothing else.

    🔴 A gate that skips the columns an export lacks reported `PARITY OK` over an export of a
    different script entirely — every bar skipped every comparison. Refuse first.
    """
    try:
        head = pd.read_csv(path, nrows=0)
    except Exception as exc:  # noqa: BLE001 — the message matters more than the class
        return f"cannot read {path.name}: {exc}"
    cols = {c.strip().lower() for c in head.columns}
    if "px_arm" not in cols or "px_struct" not in cols:
        return (f"{path.name} carries neither px_arm nor px_struct, so it is not an export of "
                f"realign_strategy_export.pine. Re-export off that twin — it plots every column "
                f"this gate reads.")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--warmup", type=int, default=None,
                    help="bars to let the engines warm before anything is compared. Default: "
                         "DERIVED — enough chart bars for the aggregated external frame to seed "
                         "its own structure. Too LOW is the failure that wastes a day: it reports "
                         "a cold start as a logic bug.")
    ap.add_argument("--price-tol", type=float, default=0.01)
    ap.add_argument("--max-report", type=int, default=8)
    a = ap.parse_args(argv)

    wrong = _wrong_export(a.csv)
    if wrong:
        print(wrong)
        return 2

    # The shared export-format rule: the final row is TradingView's live bar. Dropped BEFORE the
    # replay, so neither side is handed a bar that was still forming when the file was taken.
    df = drop_live_final_bar(load_export(a.csv))
    cfg, missing = config_from_export(df)

    # Unpack the two packed decision columns into the flat names the loop reads.
    for col, scheme in (("px_struct", _STRUCT_BITS), ("px_arm", _ARM_BITS)):
        if col in df.columns:
            b = df[col].fillna(0).round().astype("int64")
            for name, bit in scheme.items():
                df[f"_{name}"] = (b & bit) != 0

    tf = int(pd.Series(df.index).diff().dropna().dt.total_seconds().min() // 60)
    print(f"{a.csv.name}: {len(df):,} bars  {df.index[0]} → {df.index[-1]}  ({tf}m)")
    print(f"config from the export: {cfg.realign_htf_minutes}m external / {tf}m trigger, "
          f"entry {cfg.realign_entry_mode}, trail on the {cfg.realign_trail_frame} frame, "
          f"time stop {cfg.exec_time_stop_mode} {cfg.exec_time_stop_hrs:g}h")
    if cfg.realign_trail_frame != RealignConfig().realign_trail_frame:
        print(f"⚠ the export ran the '{cfg.realign_trail_frame}' trail frame and this port ships "
              f"'{RealignConfig().realign_trail_frame}'. The port is configured from the CSV, as "
              f"it must be — but every published Realign figure used the shipped one.")
    has_mom = MOM_CFG in df.columns
    required = _COMPARED + ([MOM_PX] if has_mom else [])
    refusal = missing_columns_refusal(df, required, "realign_strategy_export.pine", f"{tf}m")
    if refusal:
        print(refusal)
        return 2
    if missing:
        print("⚠ the export does not carry: " + ", ".join(missing))
        print("  those settings stay at this side's defaults, so the gate is NARROWER than it "
              "looks — it cannot see a disagreement about them.")

    if a.warmup is None:
        # The external frame is aggregated from the chart frame, so it needs
        # `major_length` HTF bars before it can confirm a swing, each of which is
        # `htf_minutes / tf` chart bars — plus the engine's own seeding. Floored generously.
        per_htf = max(1, cfg.realign_htf_minutes // max(1, tf))
        a.warmup = max(1000, per_htf * 60)
        print(f"warm-up {a.warmup:,} bars (derived: {per_htf} chart bars per external bar)")

    ohlc = df[["open", "high", "low", "close"]].copy()
    s = RealignStrategy(cfg, initial_capital=10_000.0)
    s.run(ohlc)
    states = list(s.states)
    if len(states) != len(df):
        print(f"the replay produced {len(states):,} states for {len(df):,} bars — refusing rather "
              f"than aligning two streams of different length by guessing.")
        return 2

    checks = [
        ("_long_armed", lambda st: float(st.long_armed), 0.0),
        ("_short_armed", lambda st: float(st.short_armed), 0.0),
        ("_trig_long", lambda st: float(st.trigger_dir > 0), 0.0),
        ("_trig_short", lambda st: float(st.trigger_dir < 0), 0.0),
        ("_step_long", lambda st: float(st.step_long == 1), 0.0),
        ("_step_short", lambda st: float(st.step_short == 1), 0.0),
        ("_trend_up", lambda st: float(st.htf_trend > 0), 0.0),
        ("_trend_dn", lambda st: float(st.htf_trend < 0), 0.0),
        ("_pos_long", lambda st: float(st.pos_dir > 0), 0.0),
        ("_pos_short", lambda st: float(st.pos_dir < 0), 0.0),
        ("px_tgt_l", lambda st: _n(st.tgt_long), a.price_tol),
        ("px_tgt_s", lambda st: _n(st.tgt_short), a.price_tol),
        ("px_ctr_l", lambda st: _n(st.ctr_low), a.price_tol),
        ("px_ctr_s", lambda st: _n(st.ctr_high), a.price_tol),
        ("px_lvl_l", lambda st: _n(st.trigger_level if st.trigger_dir > 0 else None),
         a.price_tol),
        ("px_lvl_s", lambda st: _n(st.trigger_level if st.trigger_dir < 0 else None),
         a.price_tol),
        ("px_htf_confhi", lambda st: _n(st.htf_conf_high), a.price_tol),
        ("px_htf_conflo", lambda st: _n(st.htf_conf_low), a.price_tol),
        ("px_cht_confhi", lambda st: _n(st.cht_conf_high), a.price_tol),
        ("px_cht_conflo", lambda st: _n(st.cht_conf_low), a.price_tol),
        ("px_pend_px", lambda st: _n(st.pend_px), a.price_tol),
        ("px_pend_sl", lambda st: _n(st.pend_sl), a.price_tol),
        ("px_pend_age", lambda st: _n(st.pend_age), 0.0),
        ("px_stop_live", lambda st: _n(st.pos_stop), a.price_tol),
        ("px_stage", lambda st: float(st.pos_stage) if st.pos_dir != 0 else float("nan"), 0.0),
    ]
    if has_mom:
        checks.append((MOM_PX, lambda st: _n(st.mom_dir), 0.0))

    # 🔴 A LATCHED FIELD IS COMPARED ONLY WHILE ITS SETUP IS ARMED ON BOTH SIDES. The Pine keeps
    #    its target, counter extreme and step in `var`s that are never cleared on disarm, so
    #    they read the LAST setup's values for ever; this port reports them only while a setup
    #    is live. Compared on every bar, that difference is 18,000 red rows about a value no
    #    decision reads once the setup is gone — and it buried the real disagreements under
    #    them on the first export (2026-09-16). Whether a side is armed at all is its own row,
    #    so nothing is hidden by the scope: an arming disagreement still goes red, once.
    def _armed(side):
        return lambda row, st: bool(row[f"_{side}_armed"]) and bool(getattr(st, f"{side}_armed"))

    # The resting limit's price and stop are latched the same way — the Pine never clears them —
    # so they are compared only while EITHER side has an order resting. `px_pend_age` is blank
    # whenever nothing rests and is compared everywhere, so a limit one side placed and the other
    # did not still goes red. Found on the first Retest export: 20,296 stale rows.
    def _resting(row, st):
        return not math.isnan(_f(row["px_pend_age"])) or st.pend_px is not None

    scope = {
        "_step_long": _armed("long"), "px_tgt_l": _armed("long"), "px_ctr_l": _armed("long"),
        "_step_short": _armed("short"), "px_tgt_s": _armed("short"), "px_ctr_s": _armed("short"),
        "px_pend_px": _resting, "px_pend_sl": _resting,
    }


    # ⚠ THE MARKET ENTRY BAR IS ONE BAR APART BY CONSTRUCTION, NOT BY DISAGREEMENT. This port
    #   opens at the close of the bar the realignment confirms on; the Pine's market order
    #   fills at the NEXT bar's open, so its position reads flat on the trigger bar. Every
    #   market trade therefore showed as one red row on each position field (8 on the first
    #   export, one per trade). A bar is excused ONLY when this port opened on it AND the Pine
    #   opened on the very next bar — a trade the Pine never takes stays red.
    pos_fields = {"_pos_long", "_pos_short", "px_stop_live", "px_stage"}

    def _entry_offset(i: int) -> bool:
        st, prev = states[i], states[i - 1] if i > 0 else None
        opened_here = st.pos_dir != 0 and (prev is None or prev.pos_dir == 0)
        return opened_here and i + 1 < len(df) and bool(df["_opened"].iloc[i + 1])

    bad: dict = {}
    seen: dict = {}
    excused = 0
    compared = 0
    for i in range(a.warmup, len(df)):
        row = df.iloc[i]
        st = states[i]
        compared += 1
        offset = cfg.realign_entry_mode == "market" and _entry_offset(i)
        excused += offset
        for col, read, tol in checks:
            if col not in df.columns:
                continue
            if col in scope and not scope[col](row, st):
                continue
            if offset and col in pos_fields:
                continue
            pine = _f(row[col])
            py = read(st)
            # COVERAGE: a field that is blank or zero on every bar was never exercised, and a
            # gate green about a branch nobody entered is the failure this table exists for.
            if not math.isnan(pine) and pine != 0.0:
                seen[col] = seen.get(col, 0) + 1
            if not _same(pine, py, tol):
                bad.setdefault(col, []).append((df.index[i], pine, py))

    print(f"\ncompared {compared:,} bars after warm-up "
          f"({excused} market-entry bars excused on the position fields — one per trade)")
    print(f"{'field':<16} {'exercised':>10}   verdict")
    print("-" * 56)
    ok = True
    for col, _read, _tol in checks:
        if col not in df.columns:
            print(f"{col:<16} {'—':>10}   NOT IN EXPORT")
            continue
        n = seen.get(col, 0)
        diffs = bad.get(col, [])
        if diffs:
            ok = False
            verdict = f"✗ {len(diffs):,} bars differ"
        elif n == 0:
            verdict = "⚠ never exercised — green proves nothing here"
        else:
            verdict = "✓"
        print(f"{col:<16} {n:>10,}   {verdict}")

    if bad:
        print("\nfirst disagreements:")
        for col, diffs in bad.items():
            for when, pine, py in diffs[: a.max_report]:
                print(f"  {col:<16} {when}  pine={pine!r}  python={py!r}")
            if len(diffs) > a.max_report:
                print(f"  {col:<16} ... and {len(diffs) - a.max_report:,} more")

        anchors = {"px_htf_confhi", "px_htf_conflo", "px_cht_confhi", "px_cht_conflo"}
        if anchors & set(bad) and not (set(bad) - anchors):
            print("\n🔴 ONLY THE TRAIL ANCHORS DIFFER — read disagreement 1 at the top of this "
                  "file. That is the frame divergence, not a bug in the setup logic.")
        print("\nPARITY FAILED")
        return 1

    never = [c for c, _r, _t in checks if c in df.columns and seen.get(c, 0) == 0]
    print("\nPARITY OK")
    if never:
        print(f"⚠ but {len(never)} field(s) were never exercised on any compared bar: "
              f"{', '.join(never)}. The gate is green about the branches both sides ENTERED, "
              f"and says nothing about these.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
