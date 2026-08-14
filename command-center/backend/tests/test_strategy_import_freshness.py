"""The scanner must read the DEFAULTS and the HASH from the same version of a strategy.

🔴 The defect these guard (measured 2026-08-06): `_python_source_hash` reads the FILES while
`_py_param_schema` reads the imported MODULE, and `importlib.import_module` returns whatever this
long-running backend cached at boot. So a scan after an edit wrote the NEW hash beside the OLD
defaults — and `needs_rescan` compares only the hash, so the row was satisfied for ever and could
never be corrected by scanning again. Nothing reported anything: the pill cleared, the scan said
`updated`, and the Run modal kept offering a default the strategy no longer had.

The mixed-reading test below is the one that matters. It builds a real package, imports it (the
boot), edits it on disk, scans, and demands that the stored default is the edited one.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from services import strategy_import


def _write_pkg(root: Path, name: str, default: str) -> Path:
    """A minimal but REAL lab strategy package — split across two modules on purpose, because the
    stale-config case is a submodule (`config.py`) and a single-file package would not reproduce it.
    """
    pkg = root / "strategies" / "python" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (root / "strategies" / "__init__.py").touch()
    (root / "strategies" / "python" / "__init__.py").touch()
    (pkg / "config.py").write_text(
        textwrap.dedent(f"""
        from dataclasses import dataclass

        @dataclass
        class Cfg:
            mode: str = {default!r}
    """)
    )
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
        from .config import Cfg

        class Strat:
            pass

        LAB_STRATEGY = {{"name": "{name}", "config": Cfg, "strategy": Strat}}
    """)
    )
    return pkg


@pytest.fixture(autouse=True)
def _clean_modules():
    """Isolate `sys.modules` around each test, and leave it exactly as it was found.

    ⚠ The `strategies` ROOT has to be dropped on the way IN, not just restored on the way out.
    Another test in the suite imports the real `strategies` package first, which pins
    `strategies.__path__` to the monorepo — and `strategies.python.<probe>` then resolves inside
    that path and is never found in `tmp_path`. Production is unaffected: there the root and the
    packages under it are the same tree, so purging `strategies.python` alone is enough.
    """
    before = dict(sys.modules)
    for name in [n for n in sys.modules if n == "strategies" or n.startswith("strategies.")]:
        del sys.modules[name]
    path_before = list(sys.path)
    yield
    for name in [n for n in sys.modules if n not in before]:
        del sys.modules[name]
    sys.modules.update(before)
    # import_strategy_package leaves its root on sys.path deliberately; a tmp_path left there
    # would SHADOW the real strategies package for every test that runs after this file.
    sys.path[:] = path_before


def test_an_edited_default_reaches_the_scan_even_though_the_module_was_already_imported(
    tmp_path, monkeypatch
):
    """THE REGRESSION. Watched red against the cached-import version, where the stored default came
    back "Off" — the exact symptom Aaron reported: the Run modal offering a value config.py no
    longer contained."""
    from services import strategy_scanner

    pkg = _write_pkg(tmp_path, "probe_strat", "Off")

    # Boot: something imports the strategy and the process caches it.
    strategy_import.import_strategy_package("probe_strat", tmp_path)
    assert sys.modules["strategies.python.probe_strat.config"].Cfg().mode == "Off"

    # The edit on disk that must reach the lab.
    (pkg / "config.py").write_text(
        (pkg / "config.py").read_text().replace("'Off'", "'Before TP1 only'")
    )

    strategy_import.purge_strategy_modules()
    row, err = strategy_scanner._parse_python_package(pkg, tmp_path)

    assert err is None
    assert row["default_params"]["mode"] == "Before TP1 only"


def test_the_hash_and_the_defaults_describe_the_same_version(tmp_path):
    """The self-sealing half, stated directly: a NEW hash beside OLD defaults is what makes the row
    permanently uncorrectable, because needs_rescan only ever compares the hash."""
    from services import strategy_scanner

    pkg = _write_pkg(tmp_path, "probe_pair", "Off")
    strategy_import.import_strategy_package("probe_pair", tmp_path)
    before, _ = strategy_scanner._parse_python_package(pkg, tmp_path)

    (pkg / "config.py").write_text((pkg / "config.py").read_text().replace("'Off'", "'On'"))
    strategy_import.purge_strategy_modules()
    after, _ = strategy_scanner._parse_python_package(pkg, tmp_path)

    assert after["source_hash"] != before["source_hash"], "the hash must move when the file does"
    assert after["default_params"]["mode"] != before["default_params"]["mode"], (
        "and so must the defaults — a moved hash beside a frozen default is the self-sealing bug"
    )


def test_purge_drops_the_whole_namespace_not_one_package(tmp_path):
    """mpc_bleg imports mpc_sos_fade and sorts BEFORE it, so a per-package purge would re-import the
    dependent against a still-stale dependency — a mixed reading, which is what this is preventing.
    """
    _write_pkg(tmp_path, "aaa_dependent", "x")
    _write_pkg(tmp_path, "zzz_dependency", "y")
    strategy_import.import_strategy_package("aaa_dependent", tmp_path)
    strategy_import.import_strategy_package("zzz_dependency", tmp_path)

    dropped = strategy_import.purge_strategy_modules()

    # both packages, both config submodules, and the `strategies.python` namespace itself.
    assert dropped == 5
    assert not [n for n in sys.modules if n.startswith("strategies.python")]
    # `strategies` stays — it is an empty namespace package carrying no strategy source, and
    # dropping it would only force a needless re-import of the two lines in its __init__.
    assert "strategies" in sys.modules


def test_purging_does_not_break_references_already_held(tmp_path):
    """This is what makes it safe to call from a request handler while a backtest is in flight: an
    in-flight run keeps the classes it was built with and finishes on them."""
    _write_pkg(tmp_path, "probe_live", "Off")
    mod = strategy_import.import_strategy_package("probe_live", tmp_path)
    held = mod.LAB_STRATEGY["config"]

    strategy_import.purge_strategy_modules()

    assert held().mode == "Off"  # the object still works
    fresh = strategy_import.import_strategy_package("probe_live", tmp_path)
    assert fresh.LAB_STRATEGY["config"] is not held  # and the next import is genuinely new


def test_purging_an_unimported_namespace_is_a_no_op():
    """⚠ Weak by construction and kept deliberately — it pins idempotency and passes against the
    broken version too. The four tests above are the ones that were watched red."""
    assert strategy_import.purge_strategy_modules() >= 0
    assert strategy_import.purge_strategy_modules() == 0
