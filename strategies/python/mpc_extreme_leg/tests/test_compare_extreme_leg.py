"""Does the parity gate WORK? — proven by making it go red, one field at a time.

🔴 **THIS DOES NOT PROVE PINE PARITY AND MUST NEVER BE READ AS IF IT DID.** It builds a synthetic
export out of the Python port's own decisions and feeds it back to the gate, so the only thing it
can check is the gate's PLUMBING: that every column name in `compare_extreme_leg.py` matches one
the export twin actually plots, that the two bit schemes agree, that the settings decode, that the
rows line up, and — the part that matters — that a disagreement is DETECTED and NAMED rather than
passed over.

⚠ **A parity harness that cannot go red is the failure this repo has met at least eight times**: a
tool whose every case asserted a refusal or a dead backend, green for its whole life against two
promote tools that had never once worked. So each case below mutates ONE column of an otherwise
identical export and asserts the gate fails AND names that column. A gate that always passed and a
gate that always failed would both fail this file.

⚠ The real gate needs stage 4 of `docs/STRATEGY_WORKFLOW.md` — a CSV a human takes off
`mpc_extreme_leg_strategy_export.pine` in TradingView. Nothing here substitutes for it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_extreme_leg import ExtremeLegConfig, MpcExtremeLegStrategy  # noqa: E402
from mpc_extreme_leg.tools.compare_extreme_leg import CFG_BITS, SEQ_BITS  # noqa: E402

TOOL = _ROOT / "strategies/python/mpc_extreme_leg/tools/compare_extreme_leg.py"
BARS = _ROOT / "backtest/cache/VantageMarkets_Demo/XAUUSD__M5.csv"
WARMUP = 400
# 🔴 THE WINDOW IS MEASURED, NOT PICKED. The first 6,000 bars of this cache contain armings and
# refusals but NOT ONE ACCEPTED SETUP, and the first version of this file used them — so the
# settings test below passed a gate that could not have failed, because raising the minimum-target
# setting changed nothing when nothing had been accepted at the old one. Bars 12,000-20,000 carry
# 6 acceptances and refusal codes 0/1/3/6, and the fixture now ASSERTS all of that rather than
# hoping. Re-measure before moving these numbers.
SLICE = (12_000, 20_000)


def _nan(x):
    return float("nan") if x is None else float(x)


def _synthetic_export(cfg: ExtremeLegConfig, df: pd.DataFrame, states) -> pd.DataFrame:
    """The port's own decisions, in the exact column shape the export twin plots."""
    by_index = {s.index: s for s in states}
    rows = []
    tf = int(pd.Series(df.index).diff().dropna().dt.total_seconds().min() // 60)
    flags = sum(bit for name, bit in CFG_BITS.items() if getattr(cfg, name))
    for i, (ts, bar) in enumerate(df.iterrows()):
        s = by_index.get(i)
        seq = 0
        if s is not None:
            for name, bit in (("period_closed", SEQ_BITS["period_closed"]),
                              ("low_armed", SEQ_BITS["low_armed"]),
                              ("high_armed", SEQ_BITS["high_armed"]),
                              ("raw_long", SEQ_BITS["raw_long"]),
                              ("raw_short", SEQ_BITS["raw_short"])):
                if getattr(s, name):
                    seq |= bit
            if s.entered == 1:
                seq |= SEQ_BITS["took_long"]
            if s.entered == -1:
                seq |= SEQ_BITS["took_short"]
        raw = s.raw_long if s else False
        rows.append({
            "time": ts.isoformat(),
            "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
            "px_seq": seq,
            "px_swept": s.swept_now if s else 0,
            "px_low_age": _nan(s.low_age if s else None),
            "px_high_age": _nan(s.high_age if s else None),
            "px_low_fam": s.low_families if s else 0,
            "px_high_fam": s.high_families if s else 0,
            "px_dir15": s.dir15 if s else 0,
            "px_swing_hi": s.swing_high if s else float("nan"),
            "px_swing_lo": s.swing_low if s else float("nan"),
            "px_extreme_lo": s.extreme_low if s else float("nan"),
            "px_extreme_hi": s.extreme_high if s else float("nan"),
            "px_atr": s.atr if s else float("nan"),
            "px_cand_stop": (s.stop_long if raw else s.stop_short) if s and (s.raw_long or s.raw_short) else float("nan"),
            "px_cand_tgt": (s.tgt_long if raw else s.tgt_short) if s and (s.raw_long or s.raw_short) else float("nan"),
            "px_cand_tp": (s.tp_long if raw else s.tp_short) if s and (s.raw_long or s.raw_short) else float("nan"),
            "px_cand_r": (s.r_long if raw else s.r_short) if s and (s.raw_long or s.raw_short) else float("nan"),
            "px_blk": (s.blk_long if raw else s.blk_short) if s and (s.raw_long or s.raw_short) else float("nan"),
            "px_agg_o": s.htf_bar[0] if s and s.htf_bar else float("nan"),
            "px_agg_h": s.htf_bar[1] if s and s.htf_bar else float("nan"),
            "px_agg_l": s.htf_bar[2] if s and s.htf_bar else float("nan"),
            "px_agg_c": s.htf_bar[3] if s and s.htf_bar else float("nan"),
            "px_bars_back": max(1, round(cfg.swept_minutes / tf)),
            "px_lookback": max(1, round(cfg.extreme_minutes / tf)),
            "cfg_flags": flags,
            "cfg_swept_min": cfg.swept_minutes, "cfg_min_fam": cfg.min_families,
            "cfg_extreme_min": cfg.extreme_minutes, "cfg_stop_buf": cfg.stop_buffer_atr,
            "cfg_tp_frac": cfg.tp_frac, "cfg_be_arm": cfg.be_arm_frac,
            "cfg_min_r": cfg.min_r, "cfg_min_stop": cfg.min_stop_usd,
            "cfg_risk_pct": cfg.exec_risk_pct, "cfg_fixed_qty": cfg.fixed_qty,
            "cfg_size_mode": 0 if cfg.size_mode == "Risk % of equity" else 1,
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def export() -> pd.DataFrame:
    if not BARS.exists():
        pytest.skip(f"no cached bars at {BARS}")
    df = pd.read_csv(BARS, parse_dates=["time"]).set_index("time").iloc[SLICE[0]:SLICE[1]]
    df = df[["open", "high", "low", "close"]]
    cfg = ExtremeLegConfig()
    s = MpcExtremeLegStrategy(cfg, initial_capital=10_000.0)
    s.run(df)
    out = _synthetic_export(cfg, df, s.states)
    # The gate is worth nothing if the run it is checking never armed or never refused anything.
    armed = (out["px_seq"] & SEQ_BITS["raw_long"] | out["px_seq"] & SEQ_BITS["raw_short"]).any()
    assert armed, "no setup fired in the slice — this fixture would certify an empty run"
    codes = set(out["px_blk"].dropna().astype(int))
    # BOTH halves, and the acceptance is the one that was missing. A window where every setup was
    # refused cannot notice a change to a refusal THRESHOLD, so a gate validated on one is a gate
    # validated on nothing — which is precisely how this file's first version passed.
    assert 0 in codes, f"no setup was ACCEPTED in the slice (codes seen: {sorted(codes)})"
    assert codes - {0}, f"no setup was REFUSED in the slice (codes seen: {sorted(codes)})"
    assert (out["px_seq"] & (SEQ_BITS["took_long"] | SEQ_BITS["took_short"])).any(), \
        "no trade was opened in the slice — the order layer is unexercised"
    return out


def _load_tool():
    """Import the gate as a module so a case can drive `main()` in this process.

    ⚠ Only for the cases that must patch something the subprocess cannot see. Everything else
    stays on the subprocess path, which is what actually gets run by a person.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("compare_extreme_leg_inproc", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(df: pd.DataFrame, tmp_path: Path, extra=()) -> subprocess.CompletedProcess:
    p = tmp_path / "export.csv"
    df.to_csv(p, index=False)
    return subprocess.run(
        [sys.executable, str(TOOL), str(p), "--warmup", str(WARMUP), *extra],
        capture_output=True, text=True,
    )


def test_gate_is_green_on_an_undisturbed_export(export, tmp_path):
    """The control. Without it, every red below could be the gate failing on everything."""
    r = _run(export, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PARITY" in r.stdout


# The real header TradingView writes for Strategy Tester → List of Trades, byte for byte from
# the first one that arrived (2026-09-01), leading BOM included. Hand-written fixtures are how
# this refusal came to be untested: see `test_gate_refuses_a_REAL_trade_list`.
_REAL_TRADE_LIST_HEADER = (
    "\ufeffTrade number,Type,Date and time,Signal,Price USD,Size (qty),Size (value),"
    "Net PnL USD,Return %,Commission USD,Favorable excursion USD,Favorable excursion %,"
    "Adverse excursion USD,Adverse excursion %,Cumulative PnL USD,Cumulative PnL %,"
    "Duration (bars)\n"
)


def test_gate_refuses_a_REAL_trade_list(tmp_path):
    """The gate must REFUSE a trade list, and refuse it in its own words.

    🔴 **THIS TEST EXISTED AND PASSED WHILE THE REFUSAL WAS UNREACHABLE (fixed 2026-09-02).** Its
    fixture was a bar CSV with a `time` column and no sequence column. A real trade list has no
    `time` column at all, so the shared loader raised first and the gate died with a traceback
    pointing at a DIFFERENT strategy's module — while this test went on passing, because the old
    refusal text happened to contain the words it asserted.

    ⚠ **A fixture more capable than the real thing describes a system you do not have.** The
    header below is copied from the file that actually arrived rather than composed here, and the
    BOM is part of it — strip it and the first column name silently stops matching.
    """
    p = tmp_path / "MPC_Extreme_Leg_VANTAGE_XAUUSD_2026-09-01_bca53.csv"
    p.write_text(_REAL_TRADE_LIST_HEADER + "1,Exit short,2025-09-10 15:35,S-x,3635.29,107.7,"
                 "393224.547,1703.81,0.43,0,1703.81,0.43,-666.66,-0.17,1703.81,17.04,103\n",
                 encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOL), str(p)], capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "TRADE LIST" in r.stdout.upper()
    # The message has to name the fix, not just the fault. A gate that says "wrong file" sends
    # somebody back to TradingView to guess which of two export menus they wanted.
    assert "mpc_extreme_leg_strategy_export.pine" in r.stdout
    assert "Bar data and indicator values" in r.stdout
    assert "Traceback" not in r.stderr


def test_gate_refuses_a_wrong_csv_that_is_not_a_trade_list_either(tmp_path):
    """Anything without the per-bar sequence column is refused, not only a trade list.

    The other half of the refusal, and the one that keeps the message honest: a bar export of the
    WRONG script parses perfectly and would otherwise be compared against nothing.
    """
    p = tmp_path / "some_other_indicator.csv"
    pd.DataFrame({"time": ["2026-01-01T00:00:00"], "open": [1], "high": [1],
                  "low": [1], "close": [1]}).to_csv(p, index=False)
    r = subprocess.run([sys.executable, str(TOOL), str(p)], capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "TRADE LIST" not in r.stdout.upper(), "it is not one, and saying so misdirects the fix"
    assert "mpc_extreme_leg_strategy_export.pine" in r.stdout


# Every compared column, so a name this side reads but the twin never plots is caught here rather
# than by a green gate that silently compared nothing.
ALL_COLUMNS = ["px_swing_hi", "px_swing_lo", "px_extreme_lo", "px_extreme_hi", "px_atr",
               "px_low_fam", "px_high_fam", "px_low_age", "px_high_age", "px_swept",
               "px_dir15", "px_agg_o", "px_agg_h", "px_agg_l", "px_agg_c",
               "px_cand_stop", "px_cand_tgt", "px_cand_tp", "px_cand_r", "px_blk"]


def test_gate_names_every_column_it_compares(export, tmp_path):
    """Move ALL of them at once and the gate must name ALL of them.

    ⚠ One process rather than twenty. Each case here re-runs the strategy in a subprocess, and
    twenty of those cost more wall clock than the rest of this package's tests put together — on a
    suite whose speed is a standing rule, that is a real cost for a weaker assertion than this one.
    Moving every column together is STRICTER: it proves the gate's reporting is not capped or
    first-only, which a per-column loop cannot show at all. The three cases below keep the
    isolation argument for the three column KINDS that could each fail their own way.
    """
    bad = export.copy()
    for c in ALL_COLUMNS:
        bad[c] = bad[c].astype(float) + 5.0
    r = _run(bad, tmp_path, extra=["--max-report", "99"])
    assert r.returncode == 1, f"every column moved and the gate stayed green:\n{r.stdout}"
    missed = [c for c in ALL_COLUMNS if c not in r.stdout]
    assert not missed, f"the gate failed but never named: {missed}\n{r.stdout}"


@pytest.mark.parametrize("column", ["px_atr", "px_swept", "px_blk"])
def test_gate_goes_red_when_ONE_column_moves(export, tmp_path, column):
    """One column at a time, for the three kinds that fail differently: a price carried through
    the whole ladder, a bit-packed column, and a refusal code.

    The value is shifted rather than blanked: a blank reads as Pine's `na`, which is a different
    disagreement, and a gate that only noticed missing data would pass a wrong number.
    """
    bad = export.copy()
    bad[column] = bad[column].astype(float) + 5.0
    r = _run(bad, tmp_path)
    assert r.returncode == 1, f"{column} moved by 5 and the gate stayed green:\n{r.stdout}"
    assert column in r.stdout, f"the gate failed but never named {column}:\n{r.stdout}"


@pytest.mark.parametrize("bitname", ["raw_long", "raw_short", "low_armed", "period_closed"])
def test_gate_goes_red_when_one_decision_bit_flips(export, tmp_path, bitname):
    """The packed column is one number carrying ten facts. A scheme that decoded the wrong bit
    would still look like a number, so each bit is flipped on its own."""
    bad = export.copy()
    bit = SEQ_BITS[bitname]
    hit = (bad["px_seq"].astype(int) & bit) != 0
    if not hit.any():
        pytest.skip(f"{bitname} never set in this slice — nothing to flip")
    bad.loc[hit, "px_seq"] = bad.loc[hit, "px_seq"].astype(int) & ~bit
    r = _run(bad, tmp_path)
    assert r.returncode == 1, f"{bitname} cleared everywhere and the gate stayed green"
    assert bitname in r.stdout, f"the gate failed but never named {bitname}:\n{r.stdout}"


def test_gate_reads_the_settings_off_the_export_not_its_own_defaults(export, tmp_path):
    """The whole point of the `cfg_*` columns. An export taken with a different setting must
    reconfigure THIS side, or the gate compares two different strategies and blames the code."""
    bad = export.copy()
    bad["cfg_min_r"] = 9.9      # far above the shipped 2.0 — most setups should now be refused
    r = _run(bad, tmp_path)
    # Reconfigured, the Python refuses far more, so its decisions no longer match an export whose
    # per-bar columns were produced at min_r = 2. Red is the CORRECT answer here.
    assert r.returncode == 1
    assert "px_blk" in r.stdout or "raw_long" in r.stdout or "took_long" in r.stdout


def test_gate_says_so_when_the_export_carries_no_settings(export, tmp_path):
    """A narrower gate has to announce itself. Silently defaulting is how a run gets believed."""
    bad = export.drop(columns=["cfg_flags", "cfg_min_r"])
    r = _run(bad, tmp_path)
    assert "cfg_flags" in r.stdout and "NARROWER" in r.stdout.upper()


def test_gate_REFUSES_to_run_when_a_pine_less_cut_is_switched_on(export, tmp_path, capsys):
    """The gate must refuse while either Python-only cut is on, and name which.

    🔴 **This refusal is the only reason those two settings are allowed to exist.** They read
    engines with no Pine source, so no export column carries them and this gate can never check
    them. Run with one on, the Python refuses setups the Pine took, and every one surfaces as a
    disagreement on a real column at a real bar — a red gate that reads exactly like a porting bug
    and sends the reader into the ladder to hunt for one that is not there.

    ⚠ **Called IN-PROCESS, unlike every other case in this file, and that is the point rather than
    a shortcut.** The gate builds its config, then decides. A subprocess reads `config.py` off the
    disk, so nothing this test can patch reaches it — the first version patched the dataclass field
    and passed a GREEN run through while asserting a refusal, twice over: a subprocess cannot see
    the patch, and **a dataclass bakes its defaults into `__init__` at decoration time**, so even
    in-process the field object is not what the constructor reads.

    ⚠ So it patches what the gate actually RECEIVES — the config that comes back from the export
    reader. That is one step downstream of how it will really happen (somebody edits a default),
    and it pins the half that matters: given a config with a cut on, this gate refuses.
    """
    import dataclasses

    csv = tmp_path / "export.csv"
    export.to_csv(csv, index=False)

    for field, phrase in (("skip_transitioning", "transitioning"), ("skip_news", "news")):
        tool = _load_tool()
        real = tool.config_from_export

        def patched(df, _f=field, _r=real):
            cfg, missing = _r(df)
            return dataclasses.replace(cfg, **{_f: True}), missing

        tool.config_from_export = patched
        code = tool.main([str(csv)])
        out = capsys.readouterr().out
        assert code == 2, f"{field} on and the gate still ran:\n{out}"
        assert phrase in out.lower(), out
        # It must say what to DO. A gate that only says no gets switched off.
        assert "turn them off" in out.lower(), out


def test_gate_RUNS_normally_while_both_pine_less_cuts_are_off(export, tmp_path):
    """The other half, and the one that stops the refusal above from being a wall.

    A guard that fires on the ordinary case is a guard people learn to route around. Both cuts
    default off, so the everyday run must be untouched by any of this.
    """
    r = _run(export, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cannot check it" not in r.stdout
