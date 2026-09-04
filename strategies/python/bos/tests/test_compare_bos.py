"""Tests for the parity harness itself.

A comparator nobody has checked is worth less than no comparator, because a green run from it
gets believed. These pin the two ways it can lie: decoding a config WRONG (so the Python
replays settings the Pine never ran, and agreement means nothing) and SKIPPING a column it
cannot find (so it reports green on a narrower question than the one asked).

They do NOT and cannot substitute for a real export — see the module docstring in
`compare_bos.py`. Nothing here proves the port matches the Pine; it proves the tool that will
ask that question is capable of getting a wrong answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bos.config import BosConfig  # noqa: E402
from bos.tools import compare_bos as cb  # noqa: E402


def _row(**over):
    """A cfg-only export row carrying the SHIPPED defaults, encoded the way the Pine does."""
    bits = (cb._CFG_BITS["exec_longs"] | cb._CFG_BITS["exec_shorts"]
            | cb._CFG_BITS["exec_req_fvg"] | cb._CFG_BITS["exec_fvg_deep_only"]
            | cb._CFG_BITS["exec_deep_fib"] | cb._CFG_BITS["exec_conf_sz2"]
            | cb._CFG_BITS["exec_no_late_day"] | cb._CFG_BITS["fvg_keep_until_broken"]
            | cb._CFG_BITS["bos_vwap_on"] | cb._CFG_BITS["use_struct_trail"])
    base = {
        "cfg_bits": bits,
        # entryFib 0.786 (4) + which "All" (2*10) + slModel ATR (4*100)
        # + minStop "% of price" (1*1000) + moveStop Off (0*10000)
        "cfg_enum1": 4 + 20 + 400 + 1000,
        "cfg_enum2": 0,           # tp2Stop "TP1 price", both HTF "Ignore"
        "cfg_min_disp": 0.0, "cfg_min_leg": 0.0, "cfg_max_days": 3.0,
        "cfg_max_regime": 10, "cfg_sl_atr": 1.3, "cfg_sl_buf": 0.0,
        "cfg_min_stop_val": 0.10, "cfg_move_stop_val": 5.0,
        "cfg_tp1_pct": 0.0, "cfg_tp2_pct": 0.0, "cfg_tp3_pct": 100.0,
        "cfg_be_buf": 30.0, "cfg_struct_buf": 20.0, "cfg_trail_step": 5.0,
        "cfg_risk_pct": 10.0, "cfg_fvg_thresh": 0.04, "cfg_fvg_max": 8,
    }
    base.update(over)
    return pd.DataFrame([base])


def test_the_shipped_defaults_round_trip_through_the_export_encoding():
    """The decoder against the Pine's own packing, field by field.

    If this drifts, a parity run silently configures the Python differently from the Pine and
    reports agreement about two different strategies — the single most dangerous failure this
    tool has, because it fails GREEN.
    """
    cfg = cb.config_from_export(_row())
    shipped = BosConfig()
    for field in ("bos_which", "bos_entry_fib", "bos_sl_model", "bos_fib_anchor",
                  "bos_entry_top", "bos_vwap_req", "bos_use_fvg", "exec_req_fvg",
                  "exec_deep_fib", "exec_conf_sz2", "exec_fvg_50", "bos_req_hold",
                  "exec_min_stop_mode", "bos_move_stop", "exec_tp2_stop_mode",
                  "exec_htf_weekly", "exec_htf_daily", "exec_runner_trail",
                  "bos_sl_atr", "bos_max_days", "exec_tp3_pct", "exec_risk_pct"):
        assert getattr(cfg, field) == getattr(shipped, field), field


def test_each_enum_digit_decodes_independently():
    """The decimal-digit packing is only safe while every field stays under 10 — a scheme that
    quietly overflowed would shift every field above it."""
    cfg = cb.config_from_export(_row(cfg_enum1=5 + 0 * 10 + 2 * 100 + 3 * 1000 + 2 * 10000,
                                     cfg_enum2=1 + 2 * 10 + 3 * 100))
    assert cfg.bos_entry_fib == "0.886"
    assert cfg.bos_which == "1st only"
    assert cfg.bos_sl_model == "Fib 0.886"
    assert cfg.exec_min_stop_mode == "x ATR(14)"
    assert cfg.bos_move_stop == "Structure (swing)"
    assert cfg.exec_tp2_stop_mode == "Breakeven"
    assert cfg.exec_htf_weekly == "Must not oppose"
    assert cfg.exec_htf_daily == "Must oppose (reversal)"


def test_the_two_enums_wearing_a_bit_decode_to_the_non_default_side():
    cfg = cb.config_from_export(_row(
        cfg_bits=cb._CFG_BITS["bos_shallow"] | cb._CFG_BITS["bos_expansion_anchor"]))
    assert cfg.bos_entry_top == "0.382"
    assert cfg.bos_fib_anchor == "Expansion leg"
    assert cfg.bos_vwap_req == "Off", "the vwap bit is clear here, so the filter must read Off"


def test_the_engine_pins_come_off_the_export_not_off_the_strategy():
    """`fvg_max_count` / `fvg_threshold_pct` / `fvg_require_close` are not in the decision
    stream, so an unpinned one is a silent parity trap — and this fork disagrees with the A+
    bot on all three. Taking them from the export is what makes a tweaked run checkable."""
    eng = cb.engine_config_from_export(_row(cfg_fvg_max=5, cfg_fvg_thresh=0.2))
    assert eng.fvg_max_count == 5
    assert eng.fvg_threshold_pct == 0.2
    assert eng.fvg_require_close is False        # the bit is clear in the shipped row
    assert eng.eq_exempt_fvg is False

    eng = cb.engine_config_from_export(_row(
        cfg_bits=cb._CFG_BITS["fvg_require_close"] | cb._CFG_BITS["eq_exempt_fvg"]))
    assert eng.fvg_require_close is True and eng.eq_exempt_fvg is True


def test_a_missing_cfg_column_REFUSES_rather_than_defaulting():
    """The whole point of the harness. Quietly defaulting one field would produce a green run
    about a setting the Pine never had — and the export would not record which."""
    df = _row().drop(columns=["cfg_sl_atr"])
    with pytest.raises(cb.ExportIncomplete, match="cfg_sl_atr"):
        cb.config_from_export(df)


# The BITFIELDS are never `na` in the Pine — they are built from ternaries, so a bar with
# nothing happening plots a real 0. Everything else is `na` on most bars, which reaches the
# CSV as an empty cell and pandas as NaN. Getting this split wrong in the FIXTURE is what a
# vacuous parity test looks like: fill the price columns with 0.0 and the tool must report a
# divergence against Python's None, which is correct behaviour being called a bug.
_PX_BITFIELDS = ("px_struct", "px_arm", "px_ready", "px_gate", "px_src")
_PX_NULLABLE = ("px_edge_l", "px_edge_s", "px_l_ext", "px_l_org", "px_s_ext", "px_s_org",
                "px_ord_l", "px_ord_s", "px_tier_l", "px_tier_s", "px_blk_l", "px_blk_s",
                "px_stage", "px_vwap", "px_closed_r")


def _write_export(tmp_path: Path, rows: int = 3, *, volume: bool = True,
                  volume_col: str = "px_volume", **over) -> Path:
    """A minimal but STRUCTURALLY REAL export CSV — every column `compare()` requires.

    ⚠ The volume column defaults to `px_volume` because that is what the export Pine PLOTS.
    This fixture wrote `volume` until 2026-08-07, which no real BOS export has ever carried —
    a fixture inventing a column name production does not produce, so the guard it exercised
    was written against the wrong one and refused the first genuine export. Pass `volume_col`
    only to prove the fallbacks work.
    """
    df = pd.concat([_row(**over)] * rows, ignore_index=True)
    df["time"] = [1_704_067_200 + i * 900 for i in range(rows)]      # unix seconds, as TV ships
    for i, col in enumerate(("open", "high", "low", "close")):
        df[col] = [2000.0 + i for _ in range(rows)]
    for col in _PX_BITFIELDS:
        df[col] = 0
    for col in _PX_NULLABLE:
        df[col] = float("nan")
    if volume:
        df[volume_col] = 1000.0
    path = tmp_path / "export.csv"
    df.to_csv(path, index=False)
    return path


def test_an_export_with_the_vwap_filter_on_and_no_volume_is_refused(tmp_path):
    """Replaying F10 against an absent VWAP blocks every setup, and an empty book matching an
    empty book is agreement about nothing.

    ⚠ This drives the REAL `compare()` through a real file. The first version of this test
    re-implemented the guard in the test body and would have passed against a tool that had
    none — the vacuous-check trap this repo has hit three times.
    """
    with pytest.raises(cb.ExportIncomplete, match="volume"):
        cb.compare(_write_export(tmp_path, volume=False), warmup=0,
                   price_tol=0.01, r_tol=0.02)


def test_the_same_export_is_accepted_once_the_filter_is_off(tmp_path):
    """The other half of the rule, and it is what proves the refusal above is about VOLUME
    rather than about the file being unreadable."""
    off = cb._CFG_BITS["exec_longs"] | cb._CFG_BITS["exec_shorts"]      # vwap bit clear
    rc = cb.compare(_write_export(tmp_path, volume=False, cfg_bits=off),
                    warmup=0, price_tol=0.01, r_tol=0.02)
    assert rc == 0


@pytest.mark.parametrize("col", ["px_volume", "volume", "Volume"])
def test_the_volume_column_is_found_under_every_name_an_export_can_ship_it_as(tmp_path, col):
    """`px_volume` is what the export Pine plots; `volume`/`Volume` is what TradingView's own
    Volume study emits if somebody has it on the chart. All three are the same fact, and
    `compare_vwap.py` has resolved them in this order since it was written.

    ⚠ This is the half that was actually broken: the tool looked for `volume` ONLY, so the
    first real export — which carries neither, because the Pine did not plot it — was refused,
    and an export taken with the study on would have been refused too, since TradingView
    capitalises it.
    """
    path = _write_export(tmp_path, volume_col=col)
    df = cb.load_export(path)
    assert cb._volume_col(df) == col
    assert "volume" in cb._bars_from(df).columns


def test_a_volume_column_with_nothing_under_it_counts_as_no_volume(tmp_path):
    """A header with an empty column is not a measurement. Accepting it would feed NaNs to the
    VWAP engine and answer F10's question with a number nobody took — the same 'no' vs
    'cannot ask' rule the price comparison below enforces, one layer earlier."""
    path = _write_export(tmp_path)
    df = pd.read_csv(path)
    df["px_volume"] = float("nan")
    df.to_csv(path, index=False)
    with pytest.raises(cb.ExportIncomplete, match="volume"):
        cb.compare(path, warmup=0, price_tol=0.01, r_tol=0.02)


def test_a_missing_px_column_refuses_instead_of_comparing_what_is_left(tmp_path):
    path = _write_export(tmp_path)
    df = pd.read_csv(path).drop(columns=["px_tier_l"])
    df.to_csv(path, index=False)
    with pytest.raises(cb.ExportIncomplete, match="px_tier_l"):
        cb.compare(path, warmup=0, price_tol=0.01, r_tol=0.02)


def test_a_none_on_one_side_and_a_price_on_the_other_IS_a_divergence():
    """`_price_differs` is where the 'no' vs 'cannot ask' rule lands in this tool. Treating a
    Pine `na` as equal to a Python number (or the reverse) would hide the exact class of bug
    that this family of harnesses keeps finding."""
    assert cb._price_differs(None, 100.0, 0.01)
    assert cb._price_differs(100.0, float("nan"), 0.01)
    assert not cb._price_differs(None, float("nan"), 0.01)
    assert not cb._price_differs(100.0, 100.005, 0.01)
    assert cb._price_differs(100.0, 100.05, 0.01)


def test_a_pine_na_int_column_reads_as_zero_not_as_a_match():
    assert not cb._int_differs(0, float("nan"))
    assert cb._int_differs(2, float("nan"))
    assert cb._int_differs(1, 2)


# ── the still-forming last bar ───────────────────────────────────────────────────
def test_the_still_forming_last_bar_is_dropped_rather_than_replayed(tmp_path):
    """TradingView appends the LIVE bar to every export and leaves its plotted series blank —
    `px_struct`, `px_arm`, `px_volume`, all of them. That is a NON-BAR, not a bar on which the
    Pine decided nothing.

    🔴 It has to be dropped rather than skipped in the compare loop, because `px_volume` feeds
    the REPLAY: a NaN reaches the VWAP engine long before the loop could ignore the row, and
    the run dies with `VolumeUnavailable` naming the feed — which sends the reader at the
    innocent half of the system. Measured on the first real export: exactly 1 trailing blank.
    """
    path = _write_export(tmp_path, rows=4)
    df = pd.read_csv(path)
    for col in list(_PX_BITFIELDS) + ["px_volume"]:
        df.loc[df.index[-1], col] = float("nan")
    df.to_csv(path, index=False)

    out = cb._drop_forming_tail(cb.load_export(path))
    assert len(out) == 3
    assert cb._bars_from(out)["volume"].notna().all()


def test_a_blank_row_in_the_MIDDLE_refuses_instead_of_being_trimmed_around(tmp_path):
    """Only a TRAILING run is a live bar. A hole in the middle is a truncated or edited CSV,
    and quietly trimming around it is how a harness ends up answering a narrower question than
    the one asked — this repo's most-repeated defect."""
    path = _write_export(tmp_path, rows=5)
    df = pd.read_csv(path)
    df.loc[df.index[2], "px_struct"] = float("nan")
    df.to_csv(path, index=False)

    with pytest.raises(cb.ExportIncomplete, match="INSIDE"):
        cb._drop_forming_tail(cb.load_export(path))


def test_an_export_with_no_blank_tail_is_returned_untouched(tmp_path):
    """The half that keeps the trim honest: a complete export must lose no bars."""
    df = cb.load_export(_write_export(tmp_path, rows=4))
    assert len(cb._drop_forming_tail(df)) == 4
