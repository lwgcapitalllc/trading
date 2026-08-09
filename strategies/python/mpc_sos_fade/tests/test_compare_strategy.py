"""compare_strategy.py plumbing test — offline, no TradingView needed.

We can't diff against real Pine here (that needs an export). Instead we round-trip the
TOOL: run the bot, serialise its OWN decisions into an export-shaped CSV using the SAME
packed-column scheme mpc_strategy_export.pine plots, then feed that back through
compare_strategy and require exit 0 (identity). Then we perturb one packed cell and
require the tool to catch it at the right bar. This proves parse / unpack / config-decode
/ align / diff all work; the real Pine diff is the live run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))
sys.path.insert(0, str(_ROOT / "strategies" / "python" / "mpc_sos_fade" / "tools"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402
from mpc_sos_fade import SosFadeConfig, MpcSosFadeStrategy  # noqa: E402
import compare_strategy as cs  # noqa: E402

# reverse of the tool's string decoders, so the fake export encodes toggles the way the
# Pine would.
_SL = {v: k for k, v in cs._SL_LEVEL.items()}
_SRC = {v: k for k, v in cs._HTF_SRC.items()}
_REQ = {v: k for k, v in cs._HTF_REQ.items()}
_TRAIL = {v: k for k, v in cs._RUNNER_TRAIL.items()}
_TP2 = {v: k for k, v in cs._TP2_STOP.items()}
_MINSTOP = {v: k for k, v in cs._MIN_STOP.items()}
_TIMESTOP = {v: k for k, v in cs._TIME_STOP.items()}
_POI = {v: k for k, v in cs._POI_SOURCE.items()}


def _encode_cfg(cfg: SosFadeConfig) -> dict:
    """Pack an SosFadeConfig the way mpc_strategy_export.pine's cfg_* plots do."""
    b = (int(cfg.exec_longs) + int(cfg.exec_shorts) * 2 + int(cfg.exec_arm_sweep) * 4
         + int(cfg.exec_arm_div) * 8 + int(cfg.exec_req_fvg) * 16
         + int(cfg.exec_fvg_deep_only) * 32 + int(cfg.exec_respect_veto) * 64
         + int(cfg.exec_close_opp_sos) * 128 + int(cfg.exec_htf_exhaust_only) * 256
         + int(cfg.exec_no_late_day) * 512 + int(cfg.show_div) * 1024 + int(cfg.div_veto) * 2048
         + int(cfg.exec_conf_sz) * 4096 + int(cfg.exec_deep_fib) * 8192
         + int(cfg.exec_aplus) * 16384 + int(cfg.exec_bleg) * 32768
         # the 2026-08-02 entry model; 65536 is skipped because it is RETIRED, not free
         + int(cfg.exec_fib_overlap) * 131072 + int(cfg.exec_fib_deep_edge) * 262144
         + int(cfg.exec_fib_nearest) * 524288 + int(cfg.exec_fvg_pre_zone) * 1048576
         + int(cfg.exec_sl_deep) * 2097152)
    # bit 65536 (execFvg50) is retired — see compare_strategy._toggles_from_export
    sc = (_SL[cfg.exec_sl_level] * 1000 + _SRC[cfg.exec_htf_source] * 100
          + _REQ[cfg.exec_htf_weekly] * 10 + _REQ[cfg.exec_htf_daily])
    di = (cfg.div_extreme_os + cfg.div_extreme_ob * 1000 + cfg.div_rsi_len * 1_000_000
          + cfg.div_pivot_len * 1_000_000_000 + cfg.div_valid_bars * 1_000_000_000_000)
    em = _TRAIL[cfg.exec_runner_trail] * 10 + _TP2[cfg.exec_tp2_stop_mode]
    return {"cfg_bits": b, "cfg_strcodes": sc, "cfg_divints": di,
            "cfg_window": cfg.aplus_window, "cfg_risk_pct": cfg.exec_risk_pct,
            "cfg_exitmode": em,
            "cfg_struct_buf": cfg.exec_struct_trail_buf_tk,
            "cfg_trail_pct": cfg.exec_trail_pct,
            "cfg_trail_step": cfg.exec_trail_step,
            "cfg_tp1_pct": cfg.exec_tp1_pct, "cfg_tp2_pct": cfg.exec_tp2_pct,
            "cfg_be_buf": cfg.exec_be_buf_tk, "cfg_sl_buf": cfg.exec_sl_buf_tk,
            "cfg_scratch_r": cfg.exec_scratch_r,
            "cfg_min_stop": _MINSTOP[cfg.exec_min_stop_mode],
            "cfg_min_stop_val": cfg.exec_min_stop_val,
            "cfg_time_stop": _TIMESTOP[cfg.exec_time_stop_mode],
            "cfg_time_stop_hrs": cfg.exec_time_stop_hrs,
            "cfg_poi_source": _POI[cfg.exec_poi_source],
            # An ENGINE setting, not a strategy one — so it is read off the bot's own
            # engine_config() rather than off `cfg`, which is what stops this encoder and the
            # pin drifting apart. It is here at all because the Pine plots it: this encoder
            # mirrors the export's plot block, and a column missing here is a column the
            # round trip silently never exercises.
            "cfg_eq_exempt": int(MpcSosFadeStrategy.engine_config().eq_exempt_fvg)}


def _pack_decision(drow: dict) -> dict:
    """Pack one flat decision row the way the Pine's px_* plots do."""
    ed = drow["px_entry_dir"]
    dec_bits = ((1 if drow["px_long_armed"] else 0) + (2 if drow["px_short_armed"] else 0)
                + (4 if drow["px_long_veto"] else 0) + (8 if drow["px_short_veto"] else 0)
                + (16 if ed == 1 else 32 if ed == -1 else 0))
    stages = drow["px_l_stage"] * 10 + drow["px_s_stage"]

    def nan(v):
        return float("nan") if v is None else v

    return {
        "px_dec_bits": dec_bits, "px_stages": stages,
        "px_edge": nan(drow["px_edge"]), "px_stop": nan(drow["px_stop"]),
        "px_entry_price": nan(drow["px_entry_price"]),
        "px_exit_tp1": nan(drow["px_exit_tp1"]), "px_exit_tp2": nan(drow["px_exit_tp2"]),
        "px_exit_run": nan(drow["px_exit_run"]), "px_closed_r": nan(drow["px_closed_r"]),
    }


def _fake_export(df, decisions, cfg) -> pd.DataFrame:
    times = (df.index.view("int64") // 1_000_000_000)
    cfg_cols = _encode_cfg(cfg)
    rows = []
    for i, (_, bar) in enumerate(df.iterrows()):
        row = {"time": int(times[i]), "open": bar["open"], "high": bar["high"],
               "low": bar["low"], "close": bar["close"]}
        row.update(_pack_decision(cs._decision_row(decisions[i])))
        row.update(cfg_cols)
        rows.append(row)
    return pd.DataFrame(rows)


def _write(tmp_path, cfg=None):
    cfg = cfg or SosFadeConfig()
    df = synth_bars(10)
    strat = MpcSosFadeStrategy(cfg).run(df, warmup=0)
    export = _fake_export(df, strat.decisions, cfg)
    p = tmp_path / "export.csv"
    export.to_csv(p, index=False)
    return p, strat


def test_roundtrip_is_parity(tmp_path):
    p, _ = _write(tmp_path)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_roundtrip_parity_under_nondefault_toggles(tmp_path):
    # a different config must still round-trip (proves cfg_* decode drives the bot)
    cfg = SosFadeConfig(exec_arm_sweep=True, exec_req_fvg=False, exec_risk_pct=1.0,
                      exec_sl_level="0.786", div_valid_bars=250, aplus_window=1440)
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_roundtrip_parity_under_nondefault_exit_levers(tmp_path):
    """The 2026-07-26 exit columns must drive the bot too. Every lever is off its default:
    the fixed-step trail instead of structure, a breakeven TP2 floor, and moved buffers —
    a run whose px_stop stream is only reproducible if cfg_exitmode + the raw exit columns
    are actually read back."""
    cfg = SosFadeConfig(exec_runner_trail="Fixed step", exec_tp2_stop_mode="Breakeven",
                        exec_struct_trail_buf_tk=5.0, exec_trail_step=2.5,
                        exec_tp1_pct=50.0, exec_tp2_pct=25.0,
                        exec_be_buf_tk=10.0, exec_sl_buf_tk=4.0)
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_roundtrip_parity_with_the_minimum_stop_guard_on(tmp_path):
    """The guard is an ENTRY filter, so a decode failure shows up as trades the two sides
    disagree about — the same class of silent drift `cfg_exitmode` had before it existed. A
    floor big enough to refuse setups is used deliberately: at a floor nothing ever hits, the
    column could be ignored entirely and this would still pass."""
    cfg = SosFadeConfig(exec_min_stop_mode="% of price", exec_min_stop_val=2.0)
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_min_stop_columns_decode():
    cfg = SosFadeConfig(exec_min_stop_mode="x ATR(14)", exec_min_stop_val=0.5)
    got = cs.config_from_export(pd.DataFrame([_encode_cfg(cfg)]))
    assert got.exec_min_stop_mode == "x ATR(14)"
    assert got.exec_min_stop_val == 0.5


def test_an_export_without_the_min_stop_column_reads_as_off():
    """Absent ⇒ Off is a FACT about pre-2026-07-30 exports (the Pine shipped the mode Off from
    the day it was added), not a guess — so it must NOT fall back to the Python default. If it
    did, the day that default changes every historical export would silently start refusing
    setups the Pine actually took."""
    base = SosFadeConfig(exec_min_stop_mode="Fixed $", exec_min_stop_val=1.5)
    export = pd.DataFrame([{k: v for k, v in _encode_cfg(SosFadeConfig()).items()
                            if not k.startswith("cfg_min_stop")}])
    got = cs.config_from_export(export, base=base)
    assert got.exec_min_stop_mode == "Off"


def test_config_decode_roundtrips():
    cfg = SosFadeConfig(exec_arm_sweep=True, exec_close_opp_sos=True, exec_sl_level="0.886",
                      exec_htf_source="Either", exec_htf_weekly="Must agree",
                      div_extreme_ob=85, div_extreme_os=15, div_rsi_len=21,
                      div_pivot_len=7, div_valid_bars=300, aplus_window=720, exec_risk_pct=2.5)
    export = pd.DataFrame([_encode_cfg(cfg)])
    got = cs.config_from_export(export)
    for f in ("exec_arm_sweep", "exec_close_opp_sos", "exec_sl_level", "exec_htf_source",
              "exec_htf_weekly", "div_extreme_ob", "div_extreme_os", "div_rsi_len",
              "div_pivot_len", "div_valid_bars", "aplus_window", "exec_risk_pct"):
        assert getattr(got, f) == getattr(cfg, f), f


def test_detects_a_planted_mismatch(tmp_path):
    p, strat = _write(tmp_path)
    df = pd.read_csv(p)
    # find a bar where the bot armed a long (px_dec_bits bit 0 set), clear it -> caught
    armed = df.index[(df["px_dec_bits"].astype(int) & 1) == 1].tolist()
    target = next((r for r in armed if r >= 100), None)
    assert target is not None, "synthetic run never armed a long — adjust the fixture"
    df.loc[target, "px_dec_bits"] = int(df.loc[target, "px_dec_bits"]) & ~1  # clear armed bit
    df.to_csv(p, index=False)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs
    assert f"bar {target} " in msgs[0]
    assert "px_long_armed" in msgs[0]


# ── the EQ/FVG coupling column (2026-08-06) ────────────────────────────────────

def test_an_export_with_no_eq_exempt_column_is_REFUSED_not_guessed():
    """A column-less export cannot say what `eqExemptFvg` ran at, so the harness must not guess.

    🔴 This is the whole lesson of the three-day red. Every OTHER "absent ⇒ Off" decoder in this
    tool is honest because the Pine INPUT and its COLUMN landed together, so a column-less export
    provably ran that lever off. `eqExemptFvg` broke the pattern: the input shipped 2026-08-01,
    defaulted ON 2026-08-03, and the column landed 2026-08-06 — so an export from that window ran
    it ON while an older one ran it OFF, and the file cannot tell you which.

    Defaulting either way produces a CONFIDENT GREEN over two different strategies, which is worse
    than the red it replaces. Refuse, and name the flag that states it.
    """
    export = pd.DataFrame([_encode_cfg(SosFadeConfig())]).drop(columns=["cfg_eq_exempt"])
    with pytest.raises(cs.EqExemptUnknown):
        cs.engine_config_from_export(export, MpcSosFadeStrategy.engine_config())


def test_the_export_column_OVERRIDES_the_bot_pin_in_both_directions():
    """The point of the column is that it beats the pin — including when it says OFF.

    The bot pins the coupling ON. An archived export taken with it off must replay with it off,
    or the harness re-configures history to a setting it was never taken at. And the caller's
    explicit `--eq-exempt` must win over the column's absence, which is what makes an archived
    export runnable at all.
    """
    base = MpcSosFadeStrategy.engine_config()
    assert base.eq_exempt_fvg is True

    export = pd.DataFrame([{**_encode_cfg(SosFadeConfig()), "cfg_eq_exempt": 0}])
    assert cs.engine_config_from_export(export, base).eq_exempt_fvg is False

    export_on = pd.DataFrame([{**_encode_cfg(SosFadeConfig()), "cfg_eq_exempt": 1}])
    assert cs.engine_config_from_export(export_on, base).eq_exempt_fvg is True

    # explicit override, on an export that carries no column at all
    bare = pd.DataFrame([_encode_cfg(SosFadeConfig())]).drop(columns=["cfg_eq_exempt"])
    assert cs.engine_config_from_export(bare, base, eq_exempt=True).eq_exempt_fvg is True
    assert cs.engine_config_from_export(bare, base, eq_exempt=False).eq_exempt_fvg is False


# ── cfg_poi_source — WHICH ZONE the entry reads (2026-08-09) ──────────────────────
# This is the widest-blast-radius column in the export: it decides which zones exist, so it
# decides which setups arm, where the limit rests, and which trades happen. A decode failure
# here does not shift a price by a tick — it diffs two different strategies and blames the
# entry rule. These tests are therefore weighted toward the ways it can be silently wrong.


def test_poi_source_column_decodes_every_option():
    for source in ("FVG", "Order block", "Either"):
        cfg = SosFadeConfig(exec_poi_source=source)
        got = cs.config_from_export(pd.DataFrame([_encode_cfg(cfg)]))
        assert got.exec_poi_source == source, source


def test_an_export_without_the_poi_source_column_reads_as_FVG():
    """Absent ⇒ FVG is a FACT about every export predating 2026-08-09 — the Pine shipped the
    input defaulting to FVG on the day it was added, so there is no window of exports that ran
    something else without a column to say so. That is precisely why the default had to be the
    OLD behaviour and not "Either".

    It must NOT fall back to the base config. The day someone flips the Python default, every
    archived export would silently decode as a run it never made — which is `cfg_eq_exempt`'s
    three-day hole, reproduced deliberately instead of by accident.
    """
    base = SosFadeConfig(exec_poi_source="Either")
    bare = pd.DataFrame([_encode_cfg(SosFadeConfig())]).drop(columns=["cfg_poi_source"])
    assert cs.config_from_export(bare, base).exec_poi_source == "FVG"


def test_roundtrip_parity_reading_ORDER_BLOCKS_instead_of_gaps(tmp_path):
    """The harness must be able to DRIVE an order-block run end to end, not merely decode the
    string. That means `stack_config()` has to build the order-block engine off the decoded
    config — if it did not, the replay would raise PoiSourceUnavailable rather than quietly
    diffing against an empty zone list, which is the failure this whole seam is shaped around.

    NON-VACUITY, measured rather than assumed: over this 960-bar synth frame the three sources
    price an entry edge on 824 (FVG) / 404 (Order block) / 833 (Either) bars. So the column is
    steering a materially different decision stream and the round trip still reproduces it — a
    green here would be worth nothing if all three modes produced the same run.
    """
    cfg = SosFadeConfig(exec_poi_source="Order block")
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_roundtrip_parity_reading_EITHER_zone(tmp_path):
    cfg = SosFadeConfig(exec_poi_source="Either")
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]
