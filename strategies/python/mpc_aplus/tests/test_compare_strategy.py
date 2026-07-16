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

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))
sys.path.insert(0, str(_ROOT / "strategies" / "python" / "mpc_aplus" / "tools"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402
from mpc_aplus import AplusConfig, MpcAplusStrategy  # noqa: E402
import compare_strategy as cs  # noqa: E402

# reverse of the tool's string decoders, so the fake export encodes toggles the way the
# Pine would.
_SL = {v: k for k, v in cs._SL_LEVEL.items()}
_SRC = {v: k for k, v in cs._HTF_SRC.items()}
_REQ = {v: k for k, v in cs._HTF_REQ.items()}


def _encode_cfg(cfg: AplusConfig) -> dict:
    """Pack an AplusConfig the way mpc_strategy_export.pine's cfg_* plots do."""
    b = (int(cfg.exec_longs) + int(cfg.exec_shorts) * 2 + int(cfg.exec_arm_sweep) * 4
         + int(cfg.exec_arm_div) * 8 + int(cfg.exec_req_fvg) * 16
         + int(cfg.exec_fvg_deep_only) * 32 + int(cfg.exec_respect_veto) * 64
         + int(cfg.exec_close_opp_sos) * 128 + int(cfg.exec_htf_exhaust_only) * 256
         + int(cfg.exec_no_late_day) * 512 + int(cfg.show_div) * 1024 + int(cfg.div_veto) * 2048)
    sc = (_SL[cfg.exec_sl_level] * 1000 + _SRC[cfg.exec_htf_source] * 100
          + _REQ[cfg.exec_htf_weekly] * 10 + _REQ[cfg.exec_htf_daily])
    di = (cfg.div_extreme_os + cfg.div_extreme_ob * 1000 + cfg.div_rsi_len * 1_000_000
          + cfg.div_pivot_len * 1_000_000_000 + cfg.div_valid_bars * 1_000_000_000_000)
    return {"cfg_bits": b, "cfg_strcodes": sc, "cfg_divints": di,
            "cfg_window": cfg.aplus_window, "cfg_risk_pct": cfg.exec_risk_pct}


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
    cfg = cfg or AplusConfig()
    df = synth_bars(10)
    strat = MpcAplusStrategy(cfg).run(df, warmup=0)
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
    cfg = AplusConfig(exec_arm_sweep=True, exec_req_fvg=False, exec_risk_pct=1.0,
                      exec_sl_level="0.786", div_valid_bars=250, aplus_window=1440)
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_config_decode_roundtrips():
    cfg = AplusConfig(exec_arm_sweep=True, exec_close_opp_sos=True, exec_sl_level="0.886",
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
