"""compare_strategy.py plumbing test — offline, no TradingView needed.

We can't diff against real Pine here (that needs an export). Instead we round-trip the
TOOL: run the bot, serialise its OWN decisions into an export-shaped CSV using the SAME
packed-column scheme sos_fade_strategy_export.pine plots, then feed that back through
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
sys.path.insert(0, str(_ROOT / "strategies" / "python" / "sos_fade" / "tools"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402
from sos_fade import SosFadeConfig, SosFadeStrategy  # noqa: E402
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
_NOGAP = {v: k for k, v in cs._NOGAP_ARM.items()}


def _encode_cfg(cfg: SosFadeConfig) -> dict:
    """Pack an SosFadeConfig the way sos_fade_strategy_export.pine's cfg_* plots do."""
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
            # The dead-market floor. It has to be here for the same reason every other
            # trade-affecting field is: the decode reads an ABSENT column as 0.0 (correct for a
            # real export predating the input), so a synthetic export that omits it round-trips
            # the shipped 0.08 back as "off" and the replay disagrees with itself. That is the
            # failure this whole file exists to catch, and it caught it.
            "cfg_min_atr": cfg.exec_min_atr_pct,
            "cfg_time_stop": _TIMESTOP[cfg.exec_time_stop_mode],
            "cfg_time_stop_hrs": cfg.exec_time_stop_hrs,
            "cfg_poi_source": _POI[cfg.exec_poi_source],
            "cfg_nogap_arm": _NOGAP[cfg.exec_nogap_arm],
            # An ENGINE setting, not a strategy one — so it is read off the bot's own
            # engine_config() rather than off `cfg`, which is what stops this encoder and the
            # pin drifting apart. It is here at all because the Pine plots it: this encoder
            # mirrors the export's plot block, and a column missing here is a column the
            # round trip silently never exercises.
            "cfg_eq_exempt": int(SosFadeStrategy.engine_config().eq_exempt_fvg)}


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
    strat = SosFadeStrategy(cfg).run(df, warmup=0)
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
    # ⚠ The planted bar must land INSIDE the compared window, or this test stops testing anything
    # and says so by passing. `run_parity` drops the export's final calendar day (bars that cannot
    # have settled on a live chart), so a fixture whose first armed bar drifted into that day would
    # plant a mismatch nothing looks at. Asserted against the tool's own rule rather than a
    # hardcoded 96, so it stays true if that rule changes.
    _tail = cs.unsettled_tail(cs.load_export(p))
    assert target < len(df) - _tail, (
        f"planted bar {target} sits inside the unsettled tail (last {_tail} bars) — it would not "
        f"be compared, and this test would pass without detecting anything")
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
        cs.engine_config_from_export(export, SosFadeStrategy.engine_config())


def test_the_export_column_OVERRIDES_the_bot_pin_in_both_directions():
    """The point of the column is that it beats the pin — including when it says OFF.

    The bot pins the coupling ON. An archived export taken with it off must replay with it off,
    or the harness re-configures history to a setting it was never taken at. And the caller's
    explicit `--eq-exempt` must win over the column's absence, which is what makes an archived
    export runnable at all.
    """
    base = SosFadeStrategy.engine_config()
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
    for source in ("FVG", "Order block", "Either", "FVG first"):
        cfg = SosFadeConfig(exec_poi_source=source)
        got = cs.config_from_export(pd.DataFrame([_encode_cfg(cfg)]))
        assert got.exec_poi_source == source, source


def test_the_poi_source_codes_are_a_WIRE_FORMAT_and_are_never_renumbered():
    """An export on disk carries the NUMBER, so re-pointing one is silent: the file still reads
    and now claims a mode it never ran. "FVG first" was appended as 3 in 2026-08-09 for exactly
    that reason, and this pins the three that predate it rather than the count."""
    assert cs._POI_SOURCE[0] == "FVG"
    assert cs._POI_SOURCE[1] == "Order block"
    assert cs._POI_SOURCE[2] == "Either"


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


def test_roundtrip_parity_on_the_FVG_FIRST_precedence_mode(tmp_path):
    """The precedence mode has to survive the round trip like the other three — it is the one
    whose zone list is identical to "Either" and whose CHOICE among them is not, so a harness
    that decoded it as "Either" would go green while diffing a different entry price.

    NON-VACUITY, and it had to be measured against "Either" specifically rather than against the
    default: over this 960-bar synth frame both modes price an edge on the SAME 833 bars (the
    union is identical by construction) and rest a DIFFERENT limit on 111 of them. So the ranking
    really is steering the stream, and a green here is worth something.
    """
    cfg = SosFadeConfig(exec_poi_source="FVG first")
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


# ── the no-FVG arm gate (2026-08-10) ────────────────────────────────────────────
def test_nogap_arm_column_decodes_both_options():
    import pandas as pd
    for code, want in cs._NOGAP_ARM.items():
        df = pd.DataFrame({"cfg_nogap_arm": [code]})
        assert cs.config_from_export(df).exec_nogap_arm == want


def test_the_nogap_arm_codes_are_a_WIRE_FORMAT_and_are_never_renumbered():
    """Pinned by VALUE, not by iterating the dict — the Pine plots these integers and every
    export ever taken carries them. Renumbering silently re-reads old exports as a run they
    never made, which is the `cfg_eq_exempt` incident's exact shape."""
    assert cs._NOGAP_ARM == {0: "Any", 1: "Sweep + RSI div"}


def test_an_export_without_the_nogap_arm_column_reads_as_Any():
    """"Absent ⇒ Any" is a FACT about those exports — before the gate existed the Pine's fallback
    took every no-gap setup. It must NOT fall back on the base config: the day the Python default
    changes, every older export would decode as a run it never made.

    ⚠ Built by DROPPING the column from a real encoded row, never as an empty frame: an empty
    frame short-circuits `config_from_export` and returns the base untouched, so it would pass
    against a decoder that had no rule at all. That was this test's first draft."""
    base = SosFadeConfig(exec_nogap_arm="Sweep + RSI div")
    bare = pd.DataFrame([_encode_cfg(SosFadeConfig())]).drop(columns=["cfg_nogap_arm"])
    assert cs.config_from_export(bare, base).exec_nogap_arm == "Any"


def test_roundtrip_parity_with_the_nogap_gate_on(tmp_path):
    """The gate only bites with Require-FVG OFF, so the round trip has to run it that way — at
    the shipped default the branch is entered on neither side and a green means nothing.

    NON-VACUITY, measured rather than assumed: over this 960-bar synth frame the two arm modes
    price a DIFFERENT entry edge on 59 bars, so the column is genuinely steering the decision
    stream the round trip reproduces.

    ⚠ And the honest other half — on this frame both modes close the SAME 6 trades. The synth
    bars are not a market and were never chosen to make this lever bite; the trade-level evidence
    is the 155,531-bar replay in `config.py`'s own note (159 / 315 / 230), not this test. What
    this test proves is that the harness can DRIVE and REPRODUCE a gated run, which is the thing
    a real export will depend on."""
    cfg = SosFadeConfig(exec_req_fvg=False, exec_nogap_arm="Sweep + RSI div")
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_roundtrip_parity_with_the_fallback_open_to_ANY_arm(tmp_path):
    """The other side of the same branch, so the pair proves the COLUMN is steering the run
    rather than both modes happening to agree."""
    cfg = SosFadeConfig(exec_req_fvg=False, exec_nogap_arm="Any")
    p, _ = _write(tmp_path, cfg)
    msgs = cs.run_parity(p, warmup=100)
    assert msgs == [], msgs[:3]


def test_a_run_with_require_fvg_ON_is_reported_as_NOT_exercising_the_gate():
    """The min-stop guard shipped live on a green run that never entered its own branch. A gate
    is only evidence about code that RAN, and this is what says so out loud."""
    import pandas as pd
    warn = cs.warn_unexercised(SosFadeConfig(), pd.DataFrame())
    assert any("exec_nogap_arm" in w and "NOT exercised" in w for w in warn)


def test_a_run_that_DOES_enter_the_branch_is_not_warned_about():
    """The other direction, so the warning cannot be "simplified" into always firing — which
    would make it noise, and noise is ignored."""
    import dataclasses
    import pandas as pd
    cfg = dataclasses.replace(SosFadeConfig(), exec_req_fvg=False)
    assert cs.warn_unexercised(cfg, pd.DataFrame({"cfg_nogap_arm": [1]})) == []


# ── the chart-timeframe refusal ───────────────────────────────────────────────────
# 🔴 A sub-15m export is not a harder parity run, it is a DIFFERENT run: the Pine reads
# the minimum-gap floor and the middle-bar-close test off the chart, the Python pins both
# to their 15m values. MEASURED on a real M5 export: 13,759 of 20,477 bars diverge as
# shipped, 0 with the sub-15m pair. So this must never surface as a mismatch list.


def _frame(minutes: int, rows: int = 40) -> pd.DataFrame:
    """A bar frame at a given spacing — only the index matters to the check."""
    idx = pd.date_range("2026-01-01", periods=rows, freq=f"{minutes}min")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)


def test_a_five_minute_export_is_REFUSED_and_the_message_names_the_cause():
    """Watched RED by returning None from timeframe_refusal for every frame."""
    msg = cs.timeframe_refusal(_frame(5))
    assert msg is not None
    assert "5-minute chart" in msg
    assert "15-minute" in msg


def test_a_fifteen_minute_export_passes_the_check_in_silence():
    """Watched RED by comparing with `>` instead of `>=` — 15m is the pinned timeframe
    itself and must not be refused by its own guard."""
    assert cs.timeframe_refusal(_frame(15)) is None


def test_a_SLOWER_chart_is_not_refused_either():
    """The pin is a FLOOR, not an equality. The Pine runs the same two values at every
    timeframe at or above 15m, so an H1 or H4 export is a legitimate run.

    Watched RED by testing `ms != _MIN_TF_MS`.
    """
    assert cs.timeframe_refusal(_frame(60)) is None
    assert cs.timeframe_refusal(_frame(240)) is None


def test_a_weekend_gap_does_not_make_a_fast_chart_read_as_a_slow_one():
    """🔴 A real export is not evenly spaced — a weekend is a 48-hour hole between two
    5-minute bars. The spacing has to be read as the SMALLEST gap, which is what the bot
    itself does when it infers its own bar duration, or a session break can present a fast
    chart as a slow one and walk straight past this check.

    ⚠ The first version of this test claimed a MEDIAN would break here and was WRONG —
    weekends are a small minority of the gaps, so the median reads 5 minutes too and the
    test passed against its own mutation. It is written against `.max()` instead, which is
    the reading that genuinely fails, and it is watched RED there. **A test whose mutation
    passes is not evidence; it is a second opinion from the same mistake.**
    """
    idx = list(pd.date_range("2026-01-01", periods=4, freq="5min"))
    idx += [idx[-1] + pd.Timedelta(days=2) + pd.Timedelta(minutes=5 * i) for i in range(1, 12)]
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                      index=pd.DatetimeIndex(idx))
    assert cs.export_bar_ms(df) == 300_000
    assert cs.timeframe_refusal(df) is not None


def test_a_frame_too_short_to_measure_is_not_refused():
    """One row carries no spacing at all. Refusing it would report a timeframe problem
    for a file whose real problem is that it is empty.

    Watched RED by returning 0 instead of None from export_bar_ms.
    """
    assert cs.export_bar_ms(_frame(5, rows=1)) is None
    assert cs.timeframe_refusal(_frame(5, rows=1)) is None


# ── the UNSETTLED TAIL (2026-09-03) ───────────────────────────────────────────
#
# 🔴 THESE EXIST BECAUSE A MUTATION SURVIVED. Deleting the tail entirely — making the gate diff the
# export's still-forming final day again, which is the exact state it was RED in for a day — broke
# nothing in this file. The synthetic fixtures cannot reproduce the divergence that motivated the
# guard (a day-high liquidity line that had not settled), so without these the guard's whole
# purpose rested on one real export sitting on one machine.


def _day_frame(days: int, bars_last_day: int = 96):
    """`days` full 96-bar days, then a partial final day of `bars_last_day` bars."""
    n = days * 96 + bars_last_day
    idx = pd.date_range(start="2025-01-06", periods=n, freq="15min")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)


def test_the_tail_is_the_final_calendar_day_not_a_fixed_bar_count():
    # The number differs per export by construction — that is the whole reason it is computed
    # rather than copied from the sibling gate, whose tail is a fixed structure lookahead.
    assert cs.unsettled_tail(_day_frame(3, bars_last_day=40)) == 40
    assert cs.unsettled_tail(_day_frame(5, bars_last_day=96)) == 96
    # ⚠ With no engine config there is no lookahead to floor with, so the day stands alone.
    assert cs.unsettled_tail(_day_frame(3, bars_last_day=7)) == 7


def test_a_short_final_day_is_floored_by_the_structure_lookahead():
    # ⚠ The daily cut subsumes the swing lookahead on any normal export (69 bars against 15 on the
    # export this was built from), but a file ending minutes into a new day would leave unconfirmed
    # swings compared. `max`, never the day alone.
    look = SosFadeStrategy.engine_config().major_length
    assert cs.unsettled_tail(_day_frame(3, bars_last_day=2), SosFadeStrategy.engine_config()) == look


def test_comparing_nothing_REFUSES_instead_of_reporting_parity(tmp_path):
    # 🔴 The failure this refusal was written for: `--tail 99999` compared ZERO bars and printed
    # `PARITY OK`. *Could not run* and *ran and passed* must never be the same outcome.
    p, _ = _write(tmp_path)
    with pytest.raises(cs.NothingToCompare):
        cs.run_parity(p, warmup=100, tail=99_999)


def test_a_defaulted_tail_and_an_explicit_zero_agree_on_a_clean_export(tmp_path):
    """Both settings report parity on a fixture that has none of the settling problem.

    ⚠ NAMED FOR WHAT IT CHECKS. It was first written as "the tail narrows the COMPARISON and never
    the REPLAY" and it does NOT prove that: truncating the replay was mutated in and SURVIVED.
    That is a fact about the property rather than a weak test — the tail sits at the very end, so
    removing those bars from the replay changes no decision the diff ever reads. The difference
    only shows on the NEXT export, where a drift that began inside the old tail must still be
    there; no single-run test can observe it. The invariant is enforced by reading `run_parity`,
    which passes the full frame to `.run()` and applies the tail only to the diff.
    """
    p, _ = _write(tmp_path)
    assert cs.run_parity(p, warmup=100, tail=0) == []
    assert cs.run_parity(p, warmup=100) == []
