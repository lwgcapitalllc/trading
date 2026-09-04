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
`extreme_leg_strategy_export.pine` in TradingView. Nothing here substitutes for it.
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

from extreme_leg import ExtremeLegConfig, ExtremeLegStrategy  # noqa: E402
from extreme_leg.tools.compare_extreme_leg import CFG_BITS, SEQ_BITS  # noqa: E402

TOOL = _ROOT / "strategies/python/extreme_leg/tools/compare_extreme_leg.py"
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
    # 🔴 BOTH PINE-LESS CUTS OFF, EXPLICITLY, WHATEVER SHIPS. This fixture stands in for a
    # TradingView export, and the chart cannot make either cut — an export taken with one on
    # cannot exist. Reading today's shipped default here made the fixture record refusal code 8,
    # which the gate (correctly replaying with the cuts off) then reported as a divergence: a
    # test failing because the FIXTURE described a system nobody has.
    cfg = ExtremeLegConfig(skip_transitioning=False, skip_news=False)
    s = ExtremeLegStrategy(cfg, initial_capital=10_000.0)
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
    assert "extreme_leg_strategy_export.pine" in r.stdout
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
    assert "extreme_leg_strategy_export.pine" in r.stdout


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


def test_gate_QUALIFIES_its_verdict_when_a_pine_less_cut_ships_on(export, tmp_path, capsys):
    """A green run must say so on the VERDICT LINE when the shipped strategy is not what it checked.

    🔴 **THIS WAS A HARD REFUSAL UNTIL 2026-09-02 AND THE REFUSAL WAS WRONG.** It was written while
    both cuts were off — untested against the state it existed for — and the first time one was
    actually switched on it walled the whole gate: 14 of this file's cases could no longer run, and
    parity of the SHARED logic became unprovable too. **A guard that blocks the work gets bypassed,
    and this repo has paid for that lesson twice already.**

    The comparison now forces both cuts off, which is the CORRECT configuration rather than a
    workaround: no export can carry them, so the config describing the export must have them off.
    What is left to say is that the green covers less than what ships — and it is said on the
    verdict line, because a reader who meets the caveat after the conclusion has already formed it.
    """
    import dataclasses

    csv = tmp_path / "export.csv"
    export.to_csv(csv, index=False)

    for field, phrase in (("skip_transitioning", "transitioning"), ("skip_news", "news")):
        tool = _load_tool()
        real = tool.ExtremeLegConfig

        def shipped(_f=field, _r=real, **kw):
            return dataclasses.replace(_r(**kw), **{_f: True})

        tool.ExtremeLegConfig = shipped
        code = tool.main([str(csv)])
        out = capsys.readouterr().out
        assert code == 0, f"the gate must still RUN with {field} on:\n{out}"
        assert "PARITY OF THE SHARED LOGIC" in out, out
        assert phrase in out.lower(), out
        assert "NOT a check of the shipped strategy" in out, out


def test_gate_gives_an_UNQUALIFIED_verdict_when_nothing_pine_less_ships_on(export, tmp_path,
                                                                          capsys):
    """The other half. A qualifier that is always printed carries no information.

    ⚠ It patches the shipped config to have BOTH cuts off, rather than reading today's default —
    the shipped default is a decision that moves, and this case is about the gate's wording.
    """
    import dataclasses

    csv = tmp_path / "export.csv"
    export.to_csv(csv, index=False)
    tool = _load_tool()
    real = tool.ExtremeLegConfig
    tool.ExtremeLegConfig = lambda **kw: dataclasses.replace(
        real(**kw), skip_transitioning=False, skip_news=False)
    code = tool.main([str(csv)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "PARITY OF THE SHARED LOGIC" not in out, out
    assert "✓ PARITY —" in out, out


def test_the_gate_configures_the_python_with_both_cuts_OFF_whatever_ships(export):
    """The config built from an export describes THE EXPORT, and no export can carry these.

    Mutation: delete the two forced assignments in `config_from_export`. With the market cut
    shipping ON, the gate would then replay a filtered Python against an unfiltered Pine and
    report a disagreement per refused setup — on a real column, at a real bar, blaming the ladder.
    """
    tool = _load_tool()
    cfg, _ = tool.config_from_export(export)
    assert cfg.skip_transitioning is False
    assert cfg.skip_news is False




# ── the DERIVED warm-up (2026-09-03) ──────────────────────────────────────────
#
# 🔴 THESE EXIST BECAUSE THREE MUTATIONS SURVIVED THE WHOLE SUITE. Reverting the warm-up to a flat
# 1000, computing the week for the wrong timeframe, and dropping the structure floor all passed
# every test in this package; two were caught only by one real export on one machine and the third
# by nothing at all. The derivation lived inside `main()`, reachable only by running the tool
# end to end — the same "no seam a test can grab" shape this repo keeps paying for.


def _dw():
    from extreme_leg.tools.compare_extreme_leg import derived_warmup, STRUCTURE_WARMUP
    return derived_warmup, STRUCTURE_WARMUP


def test_the_warmup_covers_a_full_week_at_the_EXPORT_S_timeframe():
    """🔴 The bug this replaces: 1000 bars is ~3.5 days on a 5m chart, so the weekly level had not
    formed on the Python side while the chart already had one, and the gate called a cold start a
    logic bug — 4 fields, cascading 375 bars, from ONE disagreeing bar in 19,265.

    RED when the week is computed for a fixed timeframe instead of the export's.
    """
    derived_warmup, _ = _dw()
    cfg = ExtremeLegConfig()
    assert getattr(cfg, "use_weekly_level", False), "fixture assumes the weekly family ships ON"
    assert derived_warmup(5, cfg) == 7 * 24 * 60 // 5      # 2016
    assert derived_warmup(1, cfg) == 7 * 24 * 60           # 10080 — finer frame, longer warm-up
    # The 5m case is the one that bit, and it must be strictly more than the old flat constant.
    assert derived_warmup(5, cfg) > 1000
    # ⚠ A 15m week is 672, BELOW the floor, so it returns the floor instead — that case belongs to
    # `test_a_coarse_export_still_gets_the_structure_floor` and asserting 672 here was simply wrong.


def test_a_coarse_export_still_gets_the_structure_floor():
    """RED when the floor is dropped: one week of 15m bars is 672, which would leave the 15-minute
    structure under-seeded and trade a cold-start bug for a different one."""
    derived_warmup, floor = _dw()
    cfg = ExtremeLegConfig()
    assert 7 * 24 * 60 // 15 < floor, "fixture assumes a 15m week is under the floor"
    assert derived_warmup(15, cfg) == floor


def test_the_week_is_NOT_waited_for_when_the_weekly_family_is_off():
    """⚠ Warming past what the engines need silently shrinks the compared window, which is the
    quiet half of this trade-off. A config with no weekly level has no week to wait for.

    RED when the derivation ignores the config and always widens.
    """
    derived_warmup, floor = _dw()
    cfg = ExtremeLegConfig()
    object.__setattr__(cfg, "use_weekly_level", False) if hasattr(cfg, "__dataclass_fields__") \
        else setattr(cfg, "use_weekly_level", False)
    assert derived_warmup(5, cfg) == floor
