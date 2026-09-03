"""compare_extreme_leg.py — the EXTREME LEG logic-parity gate.

The fourth of the family, beside `mpc_sos_fade/tools/compare_strategy.py`,
`mpc_bleg/tools/compare_bleg.py` and `mpc_bos/tools/compare_bos.py`. It reads a TradingView
"Export chart data" CSV of `strategies/tradingview/mpc_extreme_leg_strategy_export.pine`, replays
the export's OWN bars through the Python port CONFIGURED FROM THE EXPORT's own `cfg_*` columns,
and diffs the two decision streams bar by bar.

    python compare_extreme_leg.py <export.csv> [--warmup N] [--price-tol 0.01]

Exit 0 = the Python makes the same decisions as the Pine, on the same candles.

🔴 **UNTIL THIS EXITS 0 ON A REAL EXPORT, NOTHING IN `strategies/python/mpc_extreme_leg/` IS
VALIDATED, AND THAT IS NOT BOILERPLATE.** Every measurement this strategy has — the grid, the
timeframe answer, the two filters, the cost bill — came out of `backtest/tools/pre_sos_leg.py`,
which is a STUDY of the idea rather than a replay of the file being traded. A study and a strategy
can agree on the shape of an edge and disagree about a trade. `mpc_realign` in this repo has no
gate at all and every number it has produced is a lab finding for exactly this reason.

⚠ **THIS IS LOGIC PARITY, NOT FEED PARITY.** It replays TradingView's own candles, so the broker's
feed is irrelevant here. Whether MT5's candles match TradingView's is a different question and a
different tool (`backtest/tools/compare_feeds.py`).

✅ **THE FIRST REAL RUN HAPPENED ON 2026-09-02 AND BOTH PREDICTIONS BELOW WERE RIGHT — one still
open, one already gone.** #1 was the ONLY cause of all 7 diverged fields: ten weekly-sweep bars in
20,319, every other family agreeing exactly. #2 had already been fixed the day before and this
export confirms it — the session families agree on every compared bar. **Writing them down before
the run is what made a red gate readable in one pass instead of a day in the ladder.** The Pine
turned out to be the wrong half of #1 and has been fixed; full record in this package's CLAUDE.md.

🔴 **TWO DISAGREEMENTS WERE EXPECTED ON THE FIRST RUN AND WERE WRITTEN DOWN BEFORE IT, so that a red
gate is read rather than explained away.** Both are in the LIQUIDITY layer, and both are real
differences of rule rather than bugs on either side:

  1. **The previous WEEK's level.** The Pine's own sweep tracking treats every family the same way
     — a wick through the level takes it. The canonical `engines/liquidity/` engine, which this
     port consumes and which is 100% Pine-parity-validated against `mpc_assistant.pine`, wants a
     CLOSE through a weekly level and a wick through the others. Weekly sweeps are rare (the study
     measured 8 in the whole cached history), so the practical impact is small and the principle is
     not: one of the two has to change, and the port may not fork the engine to make itself right.
  2. **The session windows.** The Pine hardcodes three fixed clock strings; `engines/sessions/`,
     which the liquidity engine composes, is daylight-saving aware. They agree for part of the year
     and are an hour apart for the rest.

⚠ **A GREEN RUN IS ONLY GREEN ABOUT THE BRANCHES BOTH SIDES ENTERED.** This repo has shipped a
setting on a parity run that never exercised it. So this prints a COVERAGE table — how many bars
each refusal code, each family and each side actually reached — and says so out loud when a branch
was never taken. Read it before believing the exit code.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

import pandas as pd

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_extreme_leg import ExtremeLegConfig, MpcExtremeLegStrategy  # noqa: E402
from mpc_sos_fade.tools.compare_strategy import load_export  # noqa: E402

# ⚠ These MUST match the export block's own bit scheme, which is documented at `[doc 15]` and
# `[doc 16]` of `mpc_extreme_leg_strategy_export.pine`. Written as literal dicts rather than
# derived from anything, so a scheme change fails loudly here instead of shifting silently.
SEQ_BITS = {
    "period_closed": 1, "bull_sos": 2, "bear_sos": 4, "low_armed": 8, "high_armed": 16,
    "raw_long": 32, "raw_short": 64, "took_long": 128, "took_short": 256, "went_flat": 512,
}
CFG_BITS = {
    "exec_longs": 1, "exec_shorts": 2, "req_counter_trend": 4, "use_h4_level": 8,
    "use_session_level": 16, "use_daily_level": 32, "use_weekly_level": 64,
    "skip_friday": 128, "use_breakeven": 256,
}
CFG_NUM = {
    "cfg_swept_min": "swept_minutes", "cfg_min_fam": "min_families",
    "cfg_extreme_min": "extreme_minutes", "cfg_stop_buf": "stop_buffer_atr",
    "cfg_tp_frac": "tp_frac", "cfg_be_arm": "be_arm_frac", "cfg_min_r": "min_r",
    "cfg_min_stop": "min_stop_usd", "cfg_risk_pct": "exec_risk_pct",
    "cfg_fixed_qty": "fixed_qty",
}
_INT_FIELDS = {"swept_minutes", "min_families", "extreme_minutes"}


def config_from_export(df: pd.DataFrame) -> Tuple[ExtremeLegConfig, List[str]]:
    """Build the port's config from the export's OWN settings columns.

    ⚠ **Never from this side's defaults.** A port replayed at its defaults against an export taken
    at somebody else's is comparing two different strategies, and the day gets spent looking for
    the bug in the wrong half. A column the export does not carry is REPORTED rather than
    defaulted silently — an older export missing a setting is a narrower gate, and the reader has
    to be told which one.
    """
    cfg = ExtremeLegConfig()
    # 🔴 FORCED OFF, ALWAYS, WHATEVER THIS SIDE'S DEFAULT SAYS. This config describes THE EXPORT,
    # and the Pine cannot make either cut — there is no input, so no `cfg_*` column, so an export
    # taken with them "on" cannot exist. Reading them off this side's defaults would configure the
    # Python differently from the chart it is being compared against, which is the one thing this
    # function's own docstring forbids. See `config.py` → section 8.
    cfg.skip_transitioning = False
    cfg.skip_news = False
    missing: List[str] = []
    if "cfg_flags" in df.columns and df["cfg_flags"].notna().any():
        bits = int(round(float(df["cfg_flags"].dropna().iloc[0])))
        for name, bit in CFG_BITS.items():
            setattr(cfg, name, bool(bits & bit))
    else:
        missing.append("cfg_flags (every on/off setting)")
    for col, field in CFG_NUM.items():
        if col in df.columns and df[col].notna().any():
            v = float(df[col].dropna().iloc[0])
            setattr(cfg, field, int(round(v)) if field in _INT_FIELDS else v)
        else:
            missing.append(col)
    if "cfg_size_mode" in df.columns and df["cfg_size_mode"].notna().any():
        cfg.size_mode = ("Risk % of equity"
                         if int(round(float(df["cfg_size_mode"].dropna().iloc[0]))) == 0
                         else "Fixed contracts")
    else:
        missing.append("cfg_size_mode")
    cfg.__post_init__()
    return cfg, missing


def _f(v) -> float:
    """A CSV cell as a float, with a blank cell reading as Pine's `na`."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x


def _same(a: float, b: float, tol: float) -> bool:
    """Two numbers agree, with `na == na` and `na != a number`.

    ⚠ A missing value and a value are DIFFERENT, and collapsing them is the whole failure this
    repo keeps re-learning. `nan == nan` is False in IEEE arithmetic, so it has to be said.
    """
    an, bn = math.isnan(a), math.isnan(b)
    if an or bn:
        return an and bn
    return abs(a - b) <= tol


def _wrong_export(path: Path) -> "str | None":
    """Refuse a CSV that is not an export of the twin, reading the HEADER and nothing else.

    🔴 **THIS RAN AFTER `load_export` UNTIL 2026-09-02 AND WAS THEREFORE UNREACHABLE.** The shared
    loader raises `export has no 'time' column` on a trade list, so the first real trade list handed
    to this gate produced a raw traceback out of another strategy's module — a message that sends
    the reader at the wrong file — and the careful refusal below never ran. It passed its own test
    because that fixture had a time column and only lacked the sequence column: **a fixture more
    capable than the real thing, which is the exact failure mode this repo has caught four times.**

    ⚠ Header only, on purpose. Whatever is wrong with the file, the answer is the same sentence, and
    parsing a bad file further just picks a different way to fail.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        header = fh.readline()
    cols = {c.strip().strip('"').lower() for c in header.split(",")}

    if "px_seq" in cols:
        return None

    if "trade number" in cols:
        what = "a TRADE LIST (Strategy Tester → List of Trades)"
        why = (
            "  It says two runs disagree and nothing about WHERE, which is the one thing a\n"
            "  parity gate is for — this gate diffs a decision per bar, not a total.\n"
        )
    else:
        # ⚠ Deliberately does NOT mention a trade list. Naming a fault the file does not have
        # sends the reader to the wrong menu, and a wrong-script bar export parses perfectly.
        what = "not an export of mpc_extreme_leg_strategy_export.pine"
        why = "  It carries no per-bar decision column, so there is nothing here to diff.\n"

    return (
        f"✗ {path.name} is {what}.\n"
        f"{why}"
        f"  Take the export off the TWIN, not off the strategy:\n"
        f"    1. Paste strategies/tradingview/mpc_extreme_leg_strategy_export.pine onto XAUUSD 5m\n"
        f"    2. ⋮ (top right of the chart) → Export chart data\n"
        f"    3. Choose 'Bar data and indicator values' — NOT 'List of trades'\n"
        f"  The file that comes back has hundreds of columns and one row per candle."
    )


STRUCTURE_WARMUP = 1000
"""The floor: enough bars to seed the 15m structure however the export is sliced."""


def derived_warmup(tf_minutes: int, cfg) -> int:
    """Bars to warm before anything is compared, DERIVED from the export.

    🔴 IT WAS A FLAT 1000 AND THAT COST A DAY, EXACTLY AS THE `--warmup` HELP TEXT PREDICTED.
    On a 5-minute chart 1000 bars is ~3.5 days — LESS THAN A WEEK — so the weekly level had not
    formed on the Python side while the chart, carrying history from before the export window,
    already had one. The gate reported a cold start as a logic bug: 4 diverged fields, the first
    at 2026-05-29, cascading 375 bars. MEASURED 2026-09-03: exactly ONE bar of 19,265 disagreed
    and it was the weekly-high family, every other family 0; at a full week's warm-up the same
    export is GREEN over 18,248 bars.

    ⚠ A number typed here goes stale the moment somebody exports a different timeframe — 1000 bars
    is over a week on 15m and a third of one on 5m, so no one constant is right for both.

    ⚠ Floored at `STRUCTURE_WARMUP` so a coarse export still gets its structure seeding, and only
    widened when the weekly family is ON: a config with it off has no week to wait for, and warming
    past what the engines need silently shrinks the compared window.
    """
    if not getattr(cfg, "use_weekly_level", False):
        return STRUCTURE_WARMUP
    week_bars = int(7 * 24 * 60 / tf_minutes) if tf_minutes > 0 else 0
    return max(STRUCTURE_WARMUP, week_bars)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--warmup", type=int, default=None,
                    help="bars to let the engines warm before anything is compared. Default: "
                         "DERIVED from the export — one calendar week at its timeframe when the "
                         "weekly level family is on, floored at 1000. The 15-minute structure "
                         "needs ~31 completed 15m candles plus its own seeding, and the weekly "
                         "level needs a completed week. Too LOW is the failure that wastes a day: "
                         "it reports a cold start as a logic bug.")
    ap.add_argument("--price-tol", type=float, default=0.01)
    ap.add_argument("--max-report", type=int, default=8)
    a = ap.parse_args(argv)

    wrong = _wrong_export(a.csv)
    if wrong:
        print(wrong)
        return 2

    df = load_export(a.csv)
    cfg, missing = config_from_export(df)

    # 🔴 THE TWO CUTS THE PINE CANNOT MAKE. `engines/regime/` and `engines/news/` have no Pine
    # source, so no export column carries them and this gate can never check them.
    #
    # 🔴 THIS WAS A HARD REFUSAL UNTIL 2026-09-02 AND THE REFUSAL WAS WRONG — it was written while
    # both cuts were off, and the first time one was actually switched on it walled the entire gate:
    # 14 of this tool's own tests could no longer run, and nobody could prove parity of the SHARED
    # logic either. **A guard that blocks the work gets bypassed, and this repo has already paid for
    # that lesson twice.** The comparison above now forces both cuts OFF, which is not a workaround
    # — it is the correct configuration, because it is the one the export was taken at.
    #
    # What remains true is that a green run then covers LESS than the shipped strategy. That is said
    # on the verdict line itself rather than in a footnote, because a reader who meets the caveat
    # after the conclusion has already formed the conclusion.
    shipped = ExtremeLegConfig()
    unchecked = [lbl for name, lbl in (("skip_transitioning", "the transitioning-market cut"),
                                       ("skip_news", "the news blackout cut"))
                 if getattr(shipped, name, False)]

    tf = int(pd.Series(df.index).diff().dropna().dt.total_seconds().min() // 60)
    print(f"{a.csv.name}: {len(df):,} bars  {df.index[0]} → {df.index[-1]}  ({tf}m)")
    if tf != 5:
        print(f"⚠ this export is a {tf}-minute chart. The strategy's trigger is measured on the "
              f"5-minute frame and its 15-minute half is aggregated from it, so a gate run on "
              f"another frame checks a strategy nobody trades.")
    if missing:
        print("⚠ the export does not carry: " + ", ".join(missing))
        print("  those settings are left at this side's defaults, so the gate is NARROWER than it "
              "looks — it cannot see a disagreement about them.")

    # ── The WARM-UP, derived rather than typed ───────────────────────────────────────────────
    #
    # 🔴 THIS DEFAULT WAS 1000 AND IT COST A DAY, EXACTLY AS ITS OWN HELP TEXT PREDICTED. On a
    # 5-minute chart 1000 bars is ~3.5 days — LESS THAN A WEEK — so the weekly level had not formed
    # on the Python side while the chart, which carries history from before the export window,
    # already had one. The gate reported it as a logic bug: 4 diverged fields, the first at
    # 2026-05-29, cascading 375 bars. MEASURED 2026-09-03: exactly ONE bar of 19,265 disagreed and
    # it was the weekly-high family; every other family was 0. At a warm-up covering a full week
    # the same export is GREEN over 18,264 bars.
    #
    # ⚠ **A number typed here goes stale the moment somebody exports a different timeframe** — 1000
    # bars is over a week on 15m and a third of one on 5m, so one constant cannot be right for both.
    # It is computed from the export's own spacing.
    #
    # ⚠ Floored at the old 1000 so a coarse export still gets the structure seeding, and only
    # widened when the weekly family is actually ON — a config with it off has no week to wait for,
    # and warming past what the engines need would silently shrink the compared window.
    if a.warmup is None:
        a.warmup = derived_warmup(tf, cfg)
        print(f"warm-up {a.warmup:,} bars (derived: "
              f"{'one week at ' + str(tf) + 'm' if cfg.use_weekly_level else 'weekly level off'})")

    ohlc = df[["open", "high", "low", "close"]].copy()
    s = MpcExtremeLegStrategy(cfg, initial_capital=10_000.0)
    s.set_timeframe_minutes(tf)
    s.run(ohlc)
    states = {st.index: st for st in s.states}

    # ── the comparison table. One line per field; adding a column is one entry. ──
    # (export column, how to read it off the Python state, tolerance, kind)
    def bit(name):
        return lambda st: bool(getattr(st, name))

    checks = [
        ("px_dir15", lambda st: float(st.dir15), 0.0, "num"),
        ("px_swing_hi", lambda st: st.swing_high, a.price_tol, "num"),
        ("px_swing_lo", lambda st: st.swing_low, a.price_tol, "num"),
        ("px_extreme_lo", lambda st: st.extreme_low, a.price_tol, "num"),
        ("px_extreme_hi", lambda st: st.extreme_high, a.price_tol, "num"),
        ("px_atr", lambda st: st.atr, a.price_tol, "num"),
        ("px_low_fam", lambda st: float(st.low_families), 0.0, "num"),
        ("px_high_fam", lambda st: float(st.high_families), 0.0, "num"),
        ("px_low_age", lambda st: float("nan") if st.low_age is None else float(st.low_age),
         0.0, "num"),
        ("px_high_age", lambda st: float("nan") if st.high_age is None else float(st.high_age),
         0.0, "num"),
        ("px_swept", lambda st: float(st.swept_now), 0.0, "num"),
        ("px_bars_back", None, 0.0, "skip"),
        ("px_lookback", None, 0.0, "skip"),
        ("px_cand_stop", lambda st: st.stop_long if st.raw_long else (
            st.stop_short if st.raw_short else float("nan")), a.price_tol, "num"),
        ("px_cand_tgt", lambda st: st.tgt_long if st.raw_long else (
            st.tgt_short if st.raw_short else float("nan")), a.price_tol, "num"),
        ("px_cand_tp", lambda st: st.tp_long if st.raw_long else (
            st.tp_short if st.raw_short else float("nan")), a.price_tol, "num"),
        ("px_cand_r", lambda st: st.r_long if st.raw_long else (
            st.r_short if st.raw_short else float("nan")), 0.02, "num"),
        ("px_blk", lambda st: float(st.blk_long) if st.raw_long else (
            float(st.blk_short) if st.raw_short else float("nan")), 0.0, "num"),
        ("px_agg_o", lambda st: st.htf_bar[0] if st.htf_bar else float("nan"), a.price_tol, "num"),
        ("px_agg_h", lambda st: st.htf_bar[1] if st.htf_bar else float("nan"), a.price_tol, "num"),
        ("px_agg_l", lambda st: st.htf_bar[2] if st.htf_bar else float("nan"), a.price_tol, "num"),
        ("px_agg_c", lambda st: st.htf_bar[3] if st.htf_bar else float("nan"), a.price_tol, "num"),
    ]
    seq_checks = [
        ("period_closed", bit("period_closed")),
        ("low_armed", bit("low_armed")),
        ("high_armed", bit("high_armed")),
        ("raw_long", bit("raw_long")),
        ("raw_short", bit("raw_short")),
        ("took_long", lambda st: st.entered == 1),
        ("took_short", lambda st: st.entered == -1),
    ]

    first: dict = {}
    counts: Counter = Counter()
    compared = 0
    seq_col = df["px_seq"].to_numpy()
    for row, (ts, _) in enumerate(df.iterrows()):
        if row < a.warmup or row not in states:
            continue
        raw_seq = _f(seq_col[row])
        if math.isnan(raw_seq):
            continue                      # the still-forming last bar plots nothing
        compared += 1
        st = states[row]
        seq = int(round(raw_seq))
        for name, read in seq_checks:
            pine = bool(seq & SEQ_BITS[name])
            if read(st) != pine:
                counts[name] += 1
                first.setdefault(name, (row, ts, read(st), pine))
        for col, read, tol, kind in checks:
            if kind == "skip" or col not in df.columns:
                continue
            pine = _f(df[col].iat[row])
            py = read(st)
            if not _same(py, pine, tol):
                counts[col] += 1
                first.setdefault(col, (row, ts, py, pine))
        counts["_taken"] += 1 if st.entered else 0
        if st.raw_long or st.raw_short:
            counts[f"blk{st.blk_long or st.blk_short}"] += 1
        counts["_swept"] += 1 if st.swept_now else 0

    # ── the two conversions, checked once rather than per bar ─────────────────
    for col, want in (("px_bars_back", max(1, round(cfg.swept_minutes / tf))),
                      ("px_lookback", max(1, round(cfg.extreme_minutes / tf)))):
        if col in df.columns and df[col].notna().any():
            got = int(round(float(df[col].dropna().iloc[0])))
            if got != want:
                counts[col] += 1
                first.setdefault(col, (0, df.index[0], want, got))

    print(f"\ncompared {compared:,} bars (warm-up {a.warmup:,})")
    print("\ncoverage — a branch nothing reached is a branch this run says nothing about:")
    print(f"  entries taken            {counts['_taken']:>7,}")
    print(f"  bars with a sweep        {counts['_swept']:>7,}")
    for code in range(0, 8):
        n = counts.get(f"blk{code}", 0)
        flag = "   ← never reached" if n == 0 else ""
        print(f"  refusal code {code}           {n:>7,}{flag}")

    bad = {k: v for k, v in counts.items() if not k.startswith(("_", "blk"))}
    if not bad:
        if unchecked:
            # On the verdict line, not under it. "✓ PARITY" read alone is exactly the sentence
            # somebody quotes six weeks later.
            print("\n✓ PARITY OF THE SHARED LOGIC — the Python made the same decisions as the "
                  "Pine on every compared bar,\n"
                  "  but this is NOT a check of the shipped strategy: " + " and ".join(unchecked) +
                  " is switched ON\n"
                  "  in config.py, the chart cannot make it, and this run was necessarily "
                  "measured with it OFF.\n"
                  "  What ships takes FEWER trades than what was just compared.")
        else:
            print("\n✓ PARITY — the Python made the same decisions as the Pine on every compared "
                  "bar.")
        return 0
    print(f"\n✗ {len(bad)} field(s) diverged. The FIRST bar of each, so a cascade reads as one "
          f"cause rather than many:")
    for name in sorted(bad, key=lambda k: first[k][0])[: a.max_report]:
        row, ts, py, pine = first[name]
        print(f"  {name:<16} bar {row:>7,}  {ts}   py={py!r}  pine={pine!r}   "
              f"({bad[name]:,} bars)")
    if len(bad) > a.max_report:
        print(f"  … and {len(bad) - a.max_report} more field(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
