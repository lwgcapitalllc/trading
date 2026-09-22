"""A Combo must survive being shipped to a worker AFTER its strategy package was re-imported.

🔴 THE BUG THIS PINS (measured 2026-09-20, grid `opt_2d74db78e9`, 108 combos, dead on arrival with
`Can't pickle <class ...SosFadeConfig>: it's not the same object as ...SosFadeConfig`).

The backend drops and re-imports `strategies.python.*` before every scan and every run, on purpose
— see `services/strategy_import.py`, which exists because a long-running process otherwise pins
whatever was on disk when it booted. A sweep builds its configs from ONE such import and then
spends minutes loading bars. Any scan or run that lands in that window replaces the class object in
`sys.modules`, and pickle-by-reference — which is what a dataclass instance does — then refuses,
because the name no longer resolves to the object it holds.

The window is wide (two multi-year frames), the failure is total (nothing runs), and it is a RACE,
so a green suite says nothing about it. Hence: the config crosses the process boundary as its
FIELD VALUES plus its class's NAME, and the worker rebuilds it from its own import. Two processes
never shared a class object in the first place; the old behaviour only worked when both happened
to be looking at the same one.

Watched RED 2026-09-20: without `Combo.__reduce__` both `test_combo_survives_a_reimport` and
`test_config_is_rebuilt_not_referenced` raise the exact message above.
"""

from __future__ import annotations

import dataclasses
import pickle
import sys
import types

import pytest

from backtest.optimizer import Combo

_MOD = "_fake_strategy_pkg_for_pickle_test"


def _install_module():
    """Create a throwaway module holding a frozen config dataclass, as a strategy package does."""
    mod = types.ModuleType(_MOD)
    # Registered BEFORE the class is defined: @dataclass resolves annotations through
    # `sys.modules[cls.__module__]`, so a module that is not there yet raises during the exec.
    sys.modules[_MOD] = mod
    exec(
        "import dataclasses\n"
        "@dataclasses.dataclass(frozen=True)\n"
        "class Cfg:\n"
        "    a: int = 1\n"
        "    b: str = 'x'\n",
        mod.__dict__,
    )
    mod.Cfg.__module__ = _MOD
    return mod


@pytest.fixture
def fresh_module():
    old = sys.modules.pop(_MOD, None)
    yield _install_module()
    sys.modules.pop(_MOD, None)
    if old is not None:
        sys.modules[_MOD] = old


def test_combo_survives_a_reimport(fresh_module):
    combo = Combo(params={"a": 2}, config=fresh_module.Cfg(a=2))
    _install_module()  # the purge-and-reimport the backend does between scans and runs
    back = pickle.loads(pickle.dumps(combo))
    assert back.params == {"a": 2}
    assert back.config.a == 2
    assert back.config.b == "x"


def test_config_is_rebuilt_not_referenced(fresh_module):
    """The round-tripped config is an instance of whatever the NAME resolves to NOW.

    That is the whole point: a worker process imports the package itself, and the config it runs
    must be the worker's class, not a stowaway from the parent.
    """
    combo = Combo(params={}, config=fresh_module.Cfg())
    current = _install_module().Cfg
    back = pickle.loads(pickle.dumps(combo))
    assert type(back.config) is current
    assert type(back.config) is not fresh_module.Cfg


def test_a_config_that_is_not_a_dataclass_still_pickles(fresh_module):
    """Plain pickling stays the path for anything this cannot take apart. The optimizer is
    strategy-agnostic and a config is only conventionally a dataclass."""

    class Plain:
        def __init__(self):
            self.a = 3

        def __eq__(self, other):
            return isinstance(other, Plain) and other.a == self.a

    # Module-level lookup is what pickle needs; give it one.
    fresh_module.Plain = Plain
    Plain.__module__ = _MOD
    Plain.__qualname__ = "Plain"
    back = pickle.loads(pickle.dumps(Combo(params={}, config=Plain())))
    assert back.config.a == 3


def test_non_init_fields_are_not_passed_to_the_constructor(fresh_module):
    """A derived field is recomputed by the class, never smuggled across as a keyword — passing it
    would raise TypeError, and dropping it silently would be worse."""
    mod = fresh_module

    @dataclasses.dataclass(frozen=True)
    class Derived:
        a: int = 2
        doubled: int = dataclasses.field(init=False, default=0)

        def __post_init__(self):
            object.__setattr__(self, "doubled", self.a * 2)

    Derived.__module__ = _MOD
    Derived.__qualname__ = "Derived"
    mod.Derived = Derived
    back = pickle.loads(pickle.dumps(Combo(params={}, config=Derived(a=5))))
    assert back.config.a == 5
    assert back.config.doubled == 10


def test_a_config_whose_class_vanished_says_so(fresh_module):
    """If the name cannot be resolved the failure must NAME the class. A sweep that dies with an
    AttributeError deep in a worker is the kind of thing that gets blamed on the grid."""
    combo = Combo(params={}, config=fresh_module.Cfg())
    blob = pickle.dumps(combo)
    del sys.modules[_MOD]
    with pytest.raises(Exception) as err:
        pickle.loads(blob)
    assert _MOD in str(err.value)
