"""An engine a strategy never reads is never RUN — and a gated one may not be read.

Two different questions, and only the second one costs money.

The first is arithmetic: a stack built without an engine must not construct it, must not step
it, and must hand back `None` rather than a blank events object (`EngineConfig`'s switches say
why). The second is rule 7 — a switch here is a CLAIM about what a strategy reads somewhere
else, and the failure it protects against is silent: a strategy that starts reading a gated
engine gets `None`, and `None` read as *nothing happened this bar* is a bot that refuses every
setup while every dashboard stays green.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _synth import synth_bars  # noqa: E402

from backtest.replay import EngineConfig, EngineStack, iter_bars  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
# The strategy packages import by BARE NAME off this root, the repo-wide dir-on-path convention.
if str(_ROOT / "strategies" / "python") not in sys.path:
    sys.path.insert(0, str(_ROOT / "strategies" / "python"))

# The BarState field each switch decides, which is also the switch's own name. Read off the
# dataclass rather than typed out, so a ninth gated engine cannot be added without joining this.
_GATED = (
    "fib",
    "sniper",
    "macro",
    "internal",
    "fvg",
    "rsi",
    "liquidity",
    "sessions",
)


def _states(config, n=3):
    stack = EngineStack(config)
    return [stack.step(bar) for bar in iter_bars(synth_bars(n))]


def test_the_switches_and_the_BarState_fields_are_the_SAME_NAMES():
    """A switch named differently from the field it decides is a switch nobody can trace."""
    from backtest.replay.stack import BarState

    fields = set(BarState.__annotations__)
    cfg = set(EngineConfig.__annotations__)
    for name in _GATED:
        assert name in fields, f"{name} is not a BarState field"
        assert name in cfg, f"{name} is not an EngineConfig switch"


def test_the_DEFAULT_stack_still_runs_every_gated_engine():
    """Every existing caller builds the default config, so nothing may move for them."""
    state = _states(EngineConfig())[-1]
    missing = [n for n in _GATED if getattr(state, n) is None]
    assert missing == [], f"the default stack skipped {missing}"


@pytest.mark.parametrize("gate", _GATED)
def test_switching_ONE_engine_off_nulls_ITS_field_and_no_other(gate):
    off = _states(EngineConfig(**{gate: False}))[-1]
    assert getattr(off, gate) is None, f"{gate} was switched off and still reported events"
    for other in _GATED:
        if other != gate:
            assert getattr(off, other) is not None, f"switching {gate} off also killed {other}"


@pytest.mark.parametrize("gate", _GATED)
def test_a_skipped_engine_is_never_CONSTRUCTED_either(gate):
    """`None` on the state with a live engine behind it is the cost still being paid."""
    assert getattr(EngineStack(EngineConfig(**{gate: False})), gate) is None


def test_gating_cannot_move_the_STRUCTURE_stream_every_strategy_reads():
    """The base engine has no switch, and nothing downstream may feed back into it."""
    all_off = EngineConfig(**{g: False for g in _GATED})
    a = _states(EngineConfig())
    b = _states(all_off)
    assert [repr(s.structure) for s in a] == [repr(s.structure) for s in b]
    assert [repr(s.snapshot) for s in a] == [repr(s.snapshot) for s in b]


def test_asking_for_the_EQ_exemption_without_the_gaps_REFUSES():
    """The EQ engine is read by the FVG cap and by nothing else, so this pair is incoherent —
    and resolving it either way leaves a config saying one thing beside a replay doing another."""
    with pytest.raises(ValueError, match="eq_exempt_fvg"):
        EngineStack(EngineConfig(eq_exempt_fvg=True, fvg=False))


# ------------------------------------------------------- the claim about the strategies ----
_PACKAGES = {
    "sos_fade": ("sos_fade.strategy", "SosFadeStrategy"),
    "extreme_leg": ("extreme_leg.strategy", "ExtremeLegStrategy"),
}


def _package_sources(pkg: str):
    """Every module a REPLAY of this package executes. `tests/` is excluded because a test may
    legitimately build its own full stack; `tools/` is included, because a parity harness ships
    with its strategy and drives the same code."""
    root = _ROOT / "strategies" / "python" / pkg
    return [p for p in root.rglob("*.py") if "tests" not in p.parts]


def _reads_of(field: str, sources) -> list[str]:
    """Every textual read of `<something>.<field>` in these files, comments and strings aside.

    ⚠ **Deliberately conservative: it does not ask WHAT the something is.** A false positive
    here says *enable this engine*, which costs time; a false negative says *this engine is safe
    to skip* about one that is read, which is the failure this test exists to stop. It reads the
    parsed AST rather than the raw text so a mention inside a comment or a docstring — of which
    these packages have thousands of lines — cannot make an engine look needed.
    """
    hits = []
    for path in sources:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == field:
                base = node.value
                # `self.fib` is the strategy's own attribute, never the bar state's.
                if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
                    if base.value.id == "self":
                        continue
                if isinstance(base, ast.Name) and base.id == "self":
                    continue
                hits.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    return hits


@pytest.mark.parametrize("pkg", sorted(_PACKAGES))
def test_no_strategy_READS_an_engine_it_has_switched_OFF(pkg):
    """The one that would cost money. A gated engine hands back `None`, and `None` read as
    *nothing happened this bar* is a bot that refuses everything and reports nothing wrong."""
    module, cls_name = _PACKAGES[pkg]
    cls = getattr(__import__(module, fromlist=[cls_name]), cls_name)
    cfg = cls.engine_config()
    sources = _package_sources(pkg)
    assert sources, f"found no source files for {pkg} — this test would pass on nothing"

    broken = {}
    for gate in _GATED:
        if getattr(cfg, gate) is False:
            hits = _reads_of(gate, sources)
            if hits:
                broken[gate] = hits
    assert not broken, (
        f"{pkg} switches these engines OFF and still reads them: {broken}. Either turn the "
        f"switch back on in engine_config() or stop reading the field."
    )


@pytest.mark.parametrize("pkg", sorted(_PACKAGES))
def test_the_probe_can_SEE_a_read_so_a_pass_means_something(pkg):
    """Without this, *nobody reads it* and *the scanner is broken* are the same green.

    It asserts the scanner finds the engines each bot genuinely DOES read — the same mechanism,
    pointed at a case whose answer is known.
    """
    sources = _package_sources(pkg)
    assert _reads_of("liquidity", sources), "both bots read the liquidity levels"
    if pkg == "sos_fade":
        assert _reads_of("rsi", sources), "sos_fade reads the RSI divergence"
        assert _reads_of("fvg", sources), "sos_fade reads the gaps"


def test_the_LIVE_bots_between_them_switch_something_off():
    """A pin on the CLAIM, not on a value: if every engine goes back on, the measured saving is
    gone and whoever did it should have to say so here rather than watch a phase get slower."""
    off = set()
    for module, cls_name in _PACKAGES.values():
        cfg = getattr(__import__(module, fromlist=[cls_name]), cls_name).engine_config()
        off |= {g for g in _GATED if getattr(cfg, g) is False}
    assert off, "no live strategy gates any engine — the 1.52x measured on the stack is gone"
