"""compare_generic.py — the SOS Fade Generic parity gate.

SOS Fade Generic has no Pine file of its own: in TradingView it IS `sos_fade_strategy.pine` with
the settings in `docs/SOS_FADE_GENERIC_SPEC.md` → *TradingView settings*. So its gate is SOS
Fade's own (`sos_fade/tools/compare_strategy.py`), run on an export of
`sos_fade_strategy_export.pine` taken at those settings, with two things added here:

  1. **It refuses an export taken at the wrong settings, and names each one.** SOS Fade's harness
     happily diffs any configuration, so a green run on an export with the time stop still on
     would be a green run of a different strategy.
  2. **It runs the replay on the Generic bot's own config**, so every Python-only feature (the
     re-entries, the loss recovery, the rest) is pinned the way the lab runs it, not the way
     SOS Fade ships.

Usage:
    python strategies/python/sos_fade_generic/tools/compare_generic.py <export.csv> [--warmup N]

Exit 0 = parity; 1 = mismatch; 2 = cannot compare (wrong settings, wrong chart, short export).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if p not in sys.path:
        sys.path.insert(0, p)

from sos_fade.tools.compare_strategy import (  # noqa: E402
    EqExemptUnknown, NothingToCompare, config_from_export, export_truncation, load_export,
    run_parity, timeframe_refusal)
from sos_fade_generic.config import TARGETS, SosFadeGenericConfig  # noqa: E402

#: The settings the Generic bot EXPOSES — read from the export, whatever they are.
_EXPOSED = ("exec_longs", "exec_shorts", "exec_risk_pct", "exec_arm_sweep", "exec_arm_div",
            "aplus_window", "exec_req_fvg", "exec_min_stop_mode", "exec_min_stop_val")

#: Every setting the export carries that the Generic bot PINS, with its TradingView label.
#: Each must match `SosFadeGenericConfig.to_sos_fade()` or the export is refused.
#: The target fields are absent on purpose — they are decoded into `gen_target` below.
_PINNED_LABELS = {
    "exec_aplus": "Trade SOS Fade setups",
    "exec_bleg": "Trade B-Leg setups",
    "exec_nogap_arm": "No-FVG entries need",
    "exec_poi_source": "the entry zone source (FVG)",
    "exec_fvg_deep_only": "Gap must sit fully past 0.5",
    "exec_fvg_pre_zone": "Gap must pre-date the zone",
    "exec_fib_overlap": "Gap on a fib → enter on the fib",
    "exec_fib_deep_edge": "Floating gap → its own deep edge",
    "exec_fib_nearest": "Floating gap → nearest fib (either side)",
    "exec_deep_fib": "Floating gap → nearest fib shallower",
    "exec_conf_sz": "Allow Sniper Zone as entry confirmation",
    "exec_sl_level": "Stop fib level (deep side of 0.5)",
    "exec_sl_deep": "Entries at 0.786 or deeper stop at 1.0",
    "exec_sl_buf_tk": "Stop buffer beyond the level (ticks)",
    "exec_tp1_pct": "TP1 size %",
    "exec_close_opp_sos": "Close on opposite SOS",
    "exec_time_stop_mode": "Time stop",
    "exec_respect_veto": "Respect divergence/extreme veto",
    "exec_htf_exhaust_only": "Only fade HTF exhaustion, not breakouts",
    "exec_htf_weekly": "Weekly bias requirement",
    "exec_htf_daily": "Daily bias requirement",
    "exec_no_late_day": "No entries in the final hour (16:00-17:00 NY)",
    "exec_min_atr_pct": "Minimum market volatility (% of price)",
    "exec_scale_in": "Add to the runner (scale in)",
}


def _target_of(decoded) -> Optional[str]:
    """The `gen_target` choice this export's first rung spells, or None if it spells none."""
    for name, (level, r) in TARGETS.items():
        if r > 0 and abs(decoded.exec_tp1_r - r) < 1e-9:
            return name
        if r <= 0 and decoded.exec_tp1_r <= 0 and decoded.exec_tp1_level == level:
            return name
    return None


def generic_from_export(df) -> Tuple[Optional[SosFadeGenericConfig], List[str]]:
    """The Generic config this export was taken at, and every setting that rules it out.

    An empty list means the export is a valid SOS Fade Generic run. Each entry otherwise names
    the TradingView label, what the export had, and what the Generic bot needs.
    """
    decoded = config_from_export(df)
    problems: List[str] = []
    target = _target_of(decoded)
    if target is None:
        problems.append(
            f"'Target 1 level' / 'First target, in R' = {decoded.exec_tp1_level} / "
            f"{decoded.exec_tp1_r}: the Generic bot needs Target 1 level 0.0 with First target "
            f"-1, or First target 1, 2 or 3")
    exposed = {f: getattr(decoded, f) for f in _EXPOSED}
    if not (exposed["exec_arm_sweep"] or exposed["exec_arm_div"]):
        problems.append("both arm triggers are off, so nothing can trade")
        return None, problems
    generic = SosFadeGenericConfig(gen_target=target or "Swing high/low", **exposed)
    want = generic.to_sos_fade()
    for field, label in _PINNED_LABELS.items():
        have, need = getattr(decoded, field), getattr(want, field)
        if have != need:
            problems.append(f"'{label}' = {have!r}, the Generic bot needs {need!r}")
    return (generic if not problems else None), problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SOS Fade Generic parity check (Python vs Pine export)")
    ap.add_argument("csv", type=Path, help="sos_fade_strategy_export.pine chart-data CSV, "
                                           "taken at the Generic settings")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars (engine cold-start)")
    ap.add_argument("--tail", type=int, default=None,
                    help="skip the last N bars (default: the export's final calendar day)")
    args = ap.parse_args(argv)

    df = load_export(args.csv)
    why = timeframe_refusal(df)
    if why is not None:
        print(f"CANNOT DIFF - {why}")
        return 2
    generic, problems = generic_from_export(df)
    if problems:
        print("CANNOT DIFF - this export was not taken at the SOS Fade Generic settings:")
        for p in problems:
            print(f"  - {p}")
        print("  Fix those in the strategy's Settings, re-export, and run this again.")
        return 2
    gap = export_truncation(df)
    if gap is None:
        print("CANNOT MEASURE TRUNCATION — no dbg_* columns; a PARITY OK rests on --warmup.")
    elif gap > args.warmup:
        print(f"PARTIAL EXPORT — ~{gap} warmup bars are missing. Re-run with --warmup {gap} or more.")
        return 2

    base = generic.to_sos_fade()
    try:
        msgs = run_parity(args.csv, args.warmup, base_config=base, tail=args.tail)
    except (EqExemptUnknown, NothingToCompare) as exc:
        print(f"CANNOT DIFF — {exc}")
        return 2
    if not msgs:
        print(f"PARITY OK — SOS Fade Generic ({generic.gen_target} target, gap "
              f"{'required' if generic.exec_req_fvg else 'optional'}) == Pine on every bar "
              f"from {args.warmup} on.")
        return 0
    print("PARITY MISMATCH — first diverging bar:")
    print("  " + msgs[0])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

