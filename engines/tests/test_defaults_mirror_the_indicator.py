"""Does every Python engine default equal the Pine value it mirrors?

🔴 On 2026-09-09 the indicator had moved three equal-level numbers (0.1/6 -> 0.25/14) and the Python
engine was still on the old ones while the chart ran the new ones; the fix had to land in seven
places, and an eighth copy turned up a day later. Each engine now types its defaults ONCE, and every
Python consumer imports them. This file is the other half: it holds each engine default to the Pine
it claims to mirror, so the next number the indicator moves turns THIS red, instead of the chart and
the engine quietly disagreeing.

⚠ The two tables are the one place the PAIRING is written down — which Python value mirrors which
Pine name. A default with no Pine counterpart (regime, news, the trading-day rollover) is not listed.
⚠ A Pine value split by timeframe is read one branch at a time: an engine takes one value per run,
so its default is the sub-15m row. The gap engine also carries the indicator's 15m row as module
constants, for the one consumer that draws what the chart draws; those are in the second table.
⚠ For a parameter it reads the engine's SIGNATURE default, never a constant by name — so it checks
the value the engine actually uses, whether or not somebody routes it through a constant.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

_ENGINES = Path(__file__).resolve().parents[1]
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from candlesticks.engine import CandlestickEngine  # noqa: E402
from equal_highs_lows import EqualHighsLowsEngine  # noqa: E402
from fair_value_gaps import FairValueGapEngine  # noqa: E402
from fair_value_gaps import engine as fvg_module  # noqa: E402
from market_structure import StructureEngine  # noqa: E402
from order_blocks import OrderBlockEngine  # noqa: E402
from pine_constants import MPC, REPO, pine_value  # noqa: E402
from rsi_divergence import RsiDivergenceEngine  # noqa: E402
from session_volume_profile import engine as svp_module  # noqa: E402
from session_volume_profile.engine import SvpEngine  # noqa: E402

RSI_EXPORT = REPO / "indicators" / "engines" / "rsi_div_export.pine"
CANDLES = REPO / "indicators" / "engines" / "candle_sticks.pine"
BELOW_15M = 0  # the first branch of a `timeframe < 15m ? a : b` split
FROM_15M = 1  # the second

# (engine, parameter, Pine name, Pine file, branch of a split or None)
PAIRS = [
    (EqualHighsLowsEngine, "pivot_len", "eqPivotLen", MPC, None),
    (EqualHighsLowsEngine, "atr_mult", "eqAtrMult", MPC, None),
    (EqualHighsLowsEngine, "max_levels", "eqMax", MPC, None),
    (FairValueGapEngine, "max_count", "fvgMaxCount", MPC, None),
    (FairValueGapEngine, "threshold_pct", "fvgThreshLTF", MPC, None),
    (FairValueGapEngine, "require_close", "fvgRequireClose", MPC, BELOW_15M),
    (RsiDivergenceEngine, "rsi_len", "divRsiLen", MPC, None),
    (RsiDivergenceEngine, "pivot_len", "divPivotLen", MPC, None),
    (RsiDivergenceEngine, "oversold", "divOS", MPC, None),
    (RsiDivergenceEngine, "overbought", "divOB", MPC, None),
    (RsiDivergenceEngine, "valid_bars", "divValidBars", RSI_EXPORT, None),
    (StructureEngine, "major_length", "majorLength", MPC, None),
    (OrderBlockEngine, "max_active", "maxActiveOB", MPC, None),
    (OrderBlockEngine, "body_only", "obBodyOnly", MPC, None),
    (OrderBlockEngine, "max_age", "OB_MAX_AGE", MPC, None),
    (OrderBlockEngine, "min_back", "OB_MIN_BACK", MPC, None),
    (OrderBlockEngine, "max_atr", "OB_MAX_ATR", MPC, None),
    (OrderBlockEngine, "dupe_overlap", "OB_DUPE_OVERLAP", MPC, None),
    (OrderBlockEngine, "disp_mult", "OB_DISP_MULT", MPC, None),
    (OrderBlockEngine, "turn_len", "OB_TURN_LEN", MPC, None),
    (OrderBlockEngine, "turn_scan", "OB_TURN_SCAN", MPC, None),
    (OrderBlockEngine, "turn_wait", "OB_TURN_WAIT", MPC, None),
    (OrderBlockEngine, "push_look", "OB_PUSH_LOOK", MPC, None),
    (OrderBlockEngine, "push_wait", "OB_PUSH_WAIT", MPC, None),
    (OrderBlockEngine, "push_mult", "OB_PUSH_MULT", MPC, None),
    (SvpEngine, "history", "svpHistory", MPC, None),
    (CandlestickEngine, "trend", "trend", CANDLES, None),
    (CandlestickEngine, "doji_size", "dojiSize", CANDLES, None),
]

# Module constants rather than parameters: the profile takes no row count, and the gap engine never
# reads its 15m row — the Command Center's gap layer does, to draw what the chart draws.
# (module, constant, Pine name, Pine file, branch of a split or None)
MODULE_PAIRS = [
    (svp_module, "_SVP_ROWS", "svpRows", MPC, None),
    (fvg_module, "FROM_15M_THRESHOLD_PCT", "fvgThreshHTF", MPC, None),
    (fvg_module, "FROM_15M_REQUIRE_CLOSE", "fvgRequireClose", MPC, FROM_15M),
]


def _want(pine_name, source, branch):
    want = pine_value(pine_name, source)
    if branch is None:
        assert not isinstance(want, tuple), f"{pine_name} became a timeframe split - pick a branch"
        return want
    assert isinstance(want, tuple), f"{pine_name} is no longer split - re-read this pair"
    return want[branch]


def _default(cls, param):
    p = inspect.signature(cls.__init__).parameters[param]
    assert p.default is not inspect.Parameter.empty, f"{cls.__name__}.{param} has no default"
    return p.default


@pytest.mark.parametrize(
    "cls,param,pine_name,source,branch",
    PAIRS,
    ids=[f"{c.__name__}.{p}~{n}" for c, p, n, _s, _b in PAIRS],
)
def test_the_engine_default_equals_the_pine_value_it_mirrors(cls, param, pine_name, source, branch):
    """Watched RED by moving one engine default, and by moving the Pine value it mirrors."""
    want = _want(pine_name, source, branch)
    got = _default(cls, param)
    assert got == want, (
        f"{cls.__name__}({param}={got!r}) but {source.name} says {pine_name} = {want!r}"
    )


@pytest.mark.parametrize(
    "module,name,pine_name,source,branch",
    MODULE_PAIRS,
    ids=[f"{m.__name__}.{n}~{p}" for m, n, p, _s, _b in MODULE_PAIRS],
)
def test_the_engine_constant_equals_the_pine_value_it_mirrors(
    module, name, pine_name, source, branch
):
    """Watched RED by moving the constant, and by moving the Pine value it mirrors."""
    want = _want(pine_name, source, branch)
    got = getattr(module, name)
    assert got == want, (
        f"{module.__name__}.{name} = {got!r} but {source.name} says {pine_name} = {want!r}"
    )


def test_the_gap_timeframe_split_is_the_pines():
    """The one value no reader shape covers — a comparison, not a declaration.

    Watched RED by moving the split to 1800 on either side.
    """
    m = re.search(
        r"^\s*bool\s+fvgIsLTF\s*=\s*timeframe\.in_seconds\(\)\s*<\s*(\d+)\s*$",
        MPC.read_text(encoding="utf-8"),
        re.M,
    )
    assert m, "fvgIsLTF is no longer a timeframe.in_seconds() comparison - re-read this pair"
    assert fvg_module.SPLIT_SECONDS == int(m.group(1))


def test_the_reader_refuses_a_name_it_cannot_find_exactly_once(tmp_path):
    """Watched RED by returning the first of several declarations instead of refusing."""
    pine = tmp_path / "x.pine"
    pine.write_text("int a = 1\nint a = 2\nfloat b = 0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="2 declarations"):
        pine_value("a", pine)
    with pytest.raises(ValueError, match="0 declarations"):
        pine_value("c", pine)
    assert pine_value("b", pine) == 0.5


def test_the_reader_follows_a_split_and_an_input_and_never_reads_a_reassignment(tmp_path):
    """The three shapes the Pine files use, and the one it must ignore.

    Watched RED by dropping the `(?!=)` guard and by reading the first branch of a split only.
    """
    pine = tmp_path / "y.pine"
    pine.write_text(
        "float lo = 0.0\nfloat hi = 0.1\n"
        "float pct = isLTF ? lo : hi\n"
        "bool gate = isLTF ? false : true  // split by timeframe\n"
        'int n = input.int(100, "N", minval = 1)\n'
        "n := 5\n"
        "n == 7\n",
        encoding="utf-8",
    )
    assert pine_value("pct", pine) == (0.0, 0.1)
    assert pine_value("gate", pine) == (False, True)
    assert pine_value("n", pine) == 100
