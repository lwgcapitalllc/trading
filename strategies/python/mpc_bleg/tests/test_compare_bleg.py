"""compare_bleg.py plumbing test — offline, no TradingView needed.

Same round-trip trick as the A+ harness's test: we can't diff against real Pine here (that
needs an export), so we round-trip the TOOL. Run the B-LEG bot, serialise its OWN decisions
+ tracker state into an export-shaped CSV using the SAME packed-column scheme
`mpc_b_leg_strategy_export.pine` plots, feed that back through `compare_bleg` and require
exit 0 (identity). Then perturb one packed cell and require the tool to catch it at the
right bar.

This proves parse / unpack / config-decode / align / diff all work, and — because the
encoder below is written from the Pine's plot expressions rather than from the tool's
decoder — it also catches the encoder and decoder drifting apart. It does NOT prove the
Python matches the Pine; only a real export does that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python"), str(_ROOT / "backtest" / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _synth import synth_bars  # noqa: E402
from mpc_sos_fade.tools import compare_strategy as cs  # noqa: E402

from mpc_bleg import BLegConfig, MpcBLegStrategy  # noqa: E402
from mpc_bleg.tools import compare_bleg as cb  # noqa: E402

_SRC = {v: k for k, v in cs._HTF_SRC.items()}
_REQ = {v: k for k, v in cs._HTF_REQ.items()}
_TRAIL = {v: k for k, v in cs._RUNNER_TRAIL.items()}
_TP2 = {v: k for k, v in cs._TP2_STOP.items()}


def _nan(v):
    return float("nan") if v is None else v


def _encode_cfg(cfg: BLegConfig) -> dict:
    """Pack a BLegConfig the way mpc_b_leg_strategy_export.pine's cfg_* plots do. Note the
    SL slot of cfg_strcodes is pinned to 4 ("1.0") — the B-LEG fork has no execSlLevel
    input, because its stop is the band ORIGIN, not a fib on the A+ leg."""
    b = (
        int(cfg.exec_longs)
        + int(cfg.exec_shorts) * 2
        + int(cfg.exec_arm_sweep) * 4
        + int(cfg.exec_arm_div) * 8
        + int(cfg.exec_req_fvg) * 16
        + int(cfg.exec_fvg_deep_only) * 32
        + int(cfg.exec_respect_veto) * 64
        + int(cfg.exec_close_opp_sos) * 128
        + int(cfg.exec_htf_exhaust_only) * 256
        + int(cfg.exec_no_late_day) * 512
        + int(cfg.show_div) * 1024
        + int(cfg.div_veto) * 2048
        + int(cfg.exec_conf_sz) * 4096
        + int(cfg.exec_deep_fib) * 8192
        + int(cfg.exec_aplus) * 16384
        + int(cfg.exec_bleg) * 32768
    )  # bit 65536 (execFvg50) is retired — see compare_strategy._toggles_from_export
    sc = (
        4 * 1000
        + _SRC[cfg.exec_htf_source] * 100
        + _REQ[cfg.exec_htf_weekly] * 10
        + _REQ[cfg.exec_htf_daily]
    )
    di = (
        cfg.div_extreme_os
        + cfg.div_extreme_ob * 1000
        + cfg.div_rsi_len * 1_000_000
        + cfg.div_pivot_len * 1_000_000_000
        + cfg.div_valid_bars * 1_000_000_000_000
    )
    em = _TRAIL[cfg.exec_runner_trail] * 10 + _TP2[cfg.exec_tp2_stop_mode]
    return {
        "cfg_bits": b,
        "cfg_strcodes": sc,
        "cfg_divints": di,
        "cfg_window": cfg.aplus_window,
        "cfg_risk_pct": cfg.exec_risk_pct,
        "cfg_exitmode": em,
        "cfg_struct_buf": cfg.exec_struct_trail_buf_tk,
        "cfg_trail_pct": cfg.exec_trail_pct,
        "cfg_trail_step": cfg.exec_trail_step,
        "cfg_tp1_pct": cfg.exec_tp1_pct,
        "cfg_tp2_pct": cfg.exec_tp2_pct,
        "cfg_be_buf": cfg.exec_be_buf_tk,
        "cfg_sl_buf": cfg.exec_sl_buf_tk,
        "cfg_scratch_r": cfg.exec_scratch_r,
        "cfg_bleg_days": cfg.bleg_max_days,
        # Read off this fork's OWN engine_config(), which pins the coupling OFF where the
        # A+ pins it on. Hardcoding a 0 here would pass just as well today and would stop
        # catching the day the fork's Pine catches up.
        "cfg_eq_exempt": int(MpcBLegStrategy.engine_config().eq_exempt_fvg),
    }


def _pack_bar(dec, bleg) -> dict:
    """Pack one bar the way the Pine's px_* / bl_* plots do."""
    entry_dir = next((f.dir for f in dec.fills if f.kind == "entry"), 0)
    dec_bits = (
        (1 if dec.long_armed else 0)
        + (2 if dec.short_armed else 0)
        + (4 if entry_dir == 1 else 8 if entry_dir == -1 else 0)
    )
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
    bl_bits = (
        (1 if bleg.l_on else 0)
        + (2 if bleg.l_tap else 0)
        + (4 if bleg.s_on else 0)
        + (8 if bleg.s_tap else 0)
    )
    bl_bars = (0 if bleg.l_bar is None else bleg.l_bar + 1) * 1_000_000 + (
        0 if bleg.s_bar is None else bleg.s_bar + 1
    )
    return {
        "px_dec_bits": dec_bits,
        "px_stages": dec.l_stage * 10 + dec.s_stage,
        "px_edge": _nan(edge),
        "px_stop": _nan(dec.stop),
        "px_entry_price": _nan(next((f.price for f in dec.fills if f.kind == "entry"), None)),
        "px_tp1": _nan(dec.tp1),
        "px_tp2": _nan(dec.tp2),
        "px_exit_tp1": _nan(exits["px_exit_tp1"]),
        "px_exit_tp2": _nan(exits["px_exit_tp2"]),
        "px_exit_run": _nan(exits["px_exit_run"]),
        "px_closed_r": _nan(dec.closed_r),
        "bl_bits": bl_bits,
        "bl_bars": bl_bars,
        "bl_l_top": _nan(bleg.l_top),
        "bl_l_bot": _nan(bleg.l_bot),
        "bl_l_inv": _nan(bleg.l_inv),
        "bl_l_tgt": _nan(bleg.l_tgt),
        "bl_s_top": _nan(bleg.s_top),
        "bl_s_bot": _nan(bleg.s_bot),
        "bl_s_inv": _nan(bleg.s_inv),
        "bl_s_tgt": _nan(bleg.s_tgt),
    }


def _write(tmp_path, cfg=None):
    cfg = cfg or BLegConfig()
    # 30 days, not 10: on 10 the synthetic bars never ARM a leg (l_on = 0 on every bar), so
    # the bl_* columns would all be "no live leg" and the tracker diff would prove nothing.
    # 30 gives 56 armed bars and one completed trade, i.e. the harness is exercised on the
    # states it exists to check.
    df = synth_bars(30)
    strat = MpcBLegStrategy(cfg).run(df, warmup=0)
    times = df.index.view("int64") // 1_000_000_000
    cfg_cols = _encode_cfg(cfg)
    rows = []
    for i, (_, bar) in enumerate(df.iterrows()):
        row = {
            "time": int(times[i]),
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
        }
        row.update(_pack_bar(strat.decisions[i], strat.bleg_states[i]))
        row.update(cfg_cols)
        rows.append(row)
    p = tmp_path / "bleg_export.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p, strat


def test_roundtrip_is_parity(tmp_path):
    p, _ = _write(tmp_path)
    msgs = cb.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_roundtrip_parity_under_nondefault_toggles(tmp_path):
    """A different config must still round-trip — proves the cfg_* decode drives the bot
    rather than the defaults quietly agreeing. Includes `bleg_max_days`, this fork's only
    extra input, and the exit levers."""
    cfg = BLegConfig(
        bleg_max_days=2.5,
        exec_risk_pct=1.0,
        exec_runner_trail="Fixed step",
        exec_tp2_stop_mode="Breakeven",
        exec_trail_step=2.5,
        exec_tp1_pct=50.0,
        exec_tp2_pct=25.0,
        aplus_window=1440,
    )
    p, _ = _write(tmp_path, cfg)
    assert cb.config_from_export(cb.load_export(p)).bleg_max_days == 2.5
    msgs = cb.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_config_decode_accepts_exec_bleg_on(tmp_path):
    """The A+ decoder REFUSES an export with execBLeg on (the A+ bot can't make those
    trades). The B-LEG export always ships it on, so this harness must pass
    `allow_bleg=True` — if that ever regresses, every B-LEG run dies with SystemExit."""
    p, _ = _write(tmp_path, BLegConfig(exec_bleg=True))
    cfg = cb.config_from_export(cb.load_export(p))
    assert cfg.exec_bleg is True
    assert isinstance(cfg, BLegConfig)  # the decoder returned OUR class, not the base
    with pytest.raises(SystemExit):
        cs.config_from_export(cb.load_export(p))  # the A+ decoder still refuses it


def test_detects_a_planted_tracker_mismatch(tmp_path):
    """Perturb the TRACKER's own band price and require the tool to catch it. This is the
    column set that exists only in this harness — if `bl_*` were silently dropped from the
    diff the tool would look green while the band maths drifted."""
    p, _ = _write(tmp_path)
    df = pd.read_csv(p)
    live = df.index[(df["bl_bits"] & 1) != 0]
    if len(live) == 0:
        pytest.skip("no live long B-LEG on the synthetic bars — nothing to perturb")
    i = int(live[live > 100][0]) if any(live > 100) else int(live[-1])
    df.loc[i, "bl_l_top"] = float(df.loc[i, "bl_l_top"]) + 5.0
    p2 = tmp_path / "planted.csv"
    df.to_csv(p2, index=False)
    msgs = cb.run_parity(p2, warmup=100)
    assert msgs, "tool did not catch a planted bl_l_top mismatch"
    assert f"bar {i} " in msgs[0] and "bl_l_top" in msgs[0], msgs[0]


def test_detects_a_planted_decision_mismatch(tmp_path):
    """Mirror of the A+ harness's planted-mismatch test, on the shared trade stream."""
    p, _ = _write(tmp_path)
    df = pd.read_csv(p)
    i = 150
    df.loc[i, "px_dec_bits"] = int(df.loc[i, "px_dec_bits"]) ^ 1  # flip the long-arm bit
    p2 = tmp_path / "planted2.csv"
    df.to_csv(p2, index=False)
    msgs = cb.run_parity(p2, warmup=100)
    assert msgs, "tool did not catch a planted px_dec_bits mismatch"
    assert f"bar {i} " in msgs[0] and "px_long_armed" in msgs[0], msgs[0]


def _shift_bar_indices(df: pd.DataFrame, offset: int) -> None:
    """Re-pack `bl_bars` as if the CHART had `offset` bars of history before the export's
    first row — which is what Pine's `bar_index` counts from. Mutates in place."""
    packed = df["bl_bars"].fillna(0).round().astype("int64")
    lo = packed // 1_000_000
    so = packed % 1_000_000
    lo = lo.map(lambda x: 0 if x == 0 else x + offset)
    so = so.map(lambda x: 0 if x == 0 else x + offset)
    df["bl_bars"] = lo * 1_000_000 + so


def test_partial_chart_export_still_parity(tmp_path):
    """TradingView exports the VISIBLE range, but Pine's `bar_index` counts from the first
    bar the CHART loaded. Export a subset of a scrolled-back chart and every `bl_*_bar` is
    off by one constant while the logic is bar-for-bar identical. The tool must MEASURE
    that origin, not assume it is zero — before 2026-07-31 it assumed, and a real 6,329-bar
    export off a 21k-bar chart failed on all 2,409 armed bars at a flat offset of 15,362."""
    p, _ = _write(tmp_path)
    df = pd.read_csv(p)
    _shift_bar_indices(df, 15_362)
    p2 = tmp_path / "partial.csv"
    df.to_csv(p2, index=False)
    msgs = cb.run_parity(p2, warmup=100)
    assert msgs == [], msgs[:3]


def test_offset_normalisation_still_catches_a_real_armed_bar_drift(tmp_path):
    """The guard on the test above: normalising the origin must not become "ignore the bar
    index". Shift every armed bar by the same constant EXCEPT one, and the odd one out must
    still be reported — a genuine drift in WHICH bar armed is a minority offset, so it fails
    the diff while the majority sets the origin."""
    p, _ = _write(tmp_path)
    df = pd.read_csv(p)
    _shift_bar_indices(df, 15_362)
    packed = df["bl_bars"].fillna(0).round().astype("int64")
    live = df.index[(packed // 1_000_000) != 0]
    live = [i for i in live if i > 100]
    if not live:
        pytest.skip("no armed long bar past warmup on the synthetic bars")
    i = int(live[len(live) // 2])
    df.loc[i, "bl_bars"] = int(packed[i]) + 7 * 1_000_000  # this bar alone claims +7
    p2 = tmp_path / "drift.csv"
    df.to_csv(p2, index=False)
    msgs = cb.run_parity(p2, warmup=100)
    assert msgs, "offset normalisation swallowed a real armed-bar drift"
    assert f"bar {i} " in msgs[0] and "bl_l_bar" in msgs[0], msgs[0]


def test_entry_direction_comes_from_fill_dir_not_qty_sign():
    """`Fill.dir` is the signed direction; `Fill.qty` is not signed. Deriving the direction
    from qty's sign made every SHORT report as a long — and the round-trip test above could
    never catch it, because its encoder shared the same wrong derivation so the two agreed.
    Only the first real Pine export exposed it (bar 680: py=1 pine=-1).

    This asserts against the FIELD rather than against a round trip, which is the only way
    a shared-mistake bug like that gets caught offline."""
    from mpc_sos_fade.execution import Decision, Fill

    from mpc_bleg.bleg import BLegState

    flat = BLegState(
        l_top=None,
        l_bot=None,
        l_inv=None,
        l_tgt=None,
        l_on=False,
        l_tap=False,
        l_bar=None,
        s_top=None,
        s_bot=None,
        s_inv=None,
        s_tgt=None,
        s_on=False,
        s_tap=False,
        s_bar=None,
    )
    short = Decision(
        index=1, fills=[Fill(kind="entry", order_id="Short", price=100.0, qty=7.0, dir=-1)]
    )  # qty POSITIVE, dir negative
    long_ = Decision(
        index=2, fills=[Fill(kind="entry", order_id="Long", price=100.0, qty=7.0, dir=1)]
    )
    assert cb._py_row(short, flat)["px_entry_dir"] == -1
    assert cb._py_row(long_, flat)["px_entry_dir"] == 1
    assert cb._py_row(Decision(index=3), flat)["px_entry_dir"] == 0
