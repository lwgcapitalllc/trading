"""The selector, one rule at a time, on throwaway in-memory repos.

🔴 **A selector is wrong in exactly one dangerous direction: a test it never picks goes red on main
while every fast run stays green.** So nearly every case here pairs a SELECTED test with one that
must NOT be selected, and each rule was watched red by mutating it out of graph.py (the map is
at the bottom of this file).
"""

from __future__ import annotations

from scripts.testing.graph import Graph, Suite, is_conftest, parse
from scripts.testing.rules import Action, Step, matches
from scripts.testing.selection import select


def _graph(files: dict, roots=("",)):
    facts = {
        p: parse(src, conftest=is_conftest(p)) for p, src in files.items() if p.endswith(".py")
    }
    return Graph(files.keys(), facts, roots)


class _Rules:
    """A throwaway rule set with the real rules module's shape."""

    SUITES = (Suite("unit", root="", dirs=("tests", "pkg", "lib", "engines")),)
    STEPS = (Step(4, "a checker", ("x",), script="tools/check.py"),)
    TABLE = (
        ("*/exports/golden/*", Action(gate=True, package=False)),
        ("*.md", Action(by_name=False, package=False)),
    )
    INERT = ("*.md", "docs/*")
    CODE_TREES = ("lib/", "pkg/", "tools/")
    GATE_RUNNER = "tools/run_gates.py"
    matches = staticmethod(matches)

    @staticmethod
    def gates():
        return [("engines/eng", "engines/eng/tools/compare_eng.py")]

    @staticmethod
    def component_of_golden(path):
        return path.split("/exports/golden/", 1)[0]


def _picked(files, changed, roots=("",)):
    sel = select(_graph(files, roots), _Rules, changed)
    return set(sel.tests.get("unit", {})), sel


def test_a_direct_import_selects_the_test_and_nothing_else():
    files = {
        "lib/a.py": "X = 1\n",
        "lib/b.py": "Y = 1\n",
        "tests/test_a.py": "import lib.a\n",
        "tests/test_b.py": "import lib.b\n",
    }
    picked, _ = _picked(files, {"lib/a.py": "modified"})
    assert picked == {"tests/test_a.py"}


def test_a_transitive_import_is_followed():
    files = {
        "lib/a.py": "X = 1\n",
        "lib/b.py": "from lib.a import X\n",
        "tests/test_b.py": "from lib import b\n",
    }
    picked, _ = _picked(files, {"lib/a.py": "modified"})
    assert picked == {"tests/test_b.py"}


def test_a_bare_name_resolves_only_through_a_declared_search_root():
    files = {
        "engines/eng/__init__.py": "V = 1\n",
        "tests/test_eng.py": "from eng import V\n",
    }
    with_root, _ = _picked(files, {"engines/eng/__init__.py": "modified"}, roots=("", "engines"))
    without, _ = _picked(files, {"engines/eng/__init__.py": "modified"}, roots=("",))
    assert with_root == {"tests/test_eng.py"}
    assert without == set()  # the root is what makes the edge - proven, not assumed


def test_a_relative_import_is_resolved_against_the_package():
    files = {
        "pkg/__init__.py": "",
        "pkg/m.py": "def f(): pass\n",
        "pkg/tests/__init__.py": "",
        "pkg/tests/test_m.py": "from ..m import f\n",
    }
    picked, _ = _picked(files, {"pkg/m.py": "modified"})
    assert picked == {"pkg/tests/test_m.py"}


def test_an_import_inside_a_function_still_counts():
    files = {"lib/a.py": "", "tests/test_lazy.py": "def test_x():\n    import lib.a\n"}
    picked, _ = _picked(files, {"lib/a.py": "modified"})
    assert picked == {"tests/test_lazy.py"}


_CONFTEST = """
import pytest

@pytest.fixture
def client():
    import app
    return app

@pytest.fixture
def seeded(client):
    return client

@pytest.fixture
def db():
    return 1
"""


def test_a_fixture_import_reaches_only_the_tests_using_that_fixture():
    files = {
        "app.py": "",
        "tests/conftest.py": _CONFTEST,
        "tests/test_client.py": "def test_x(client):\n    pass\n",
        "tests/test_seeded.py": "def test_x(seeded):\n    pass\n",
        "tests/test_db.py": "def test_x(db):\n    pass\n",
    }
    picked, _ = _picked(files, {"app.py": "modified"})
    # `seeded` is built on `client`, so it reaches app.py too; `db` never touches it.
    assert picked == {"tests/test_client.py", "tests/test_seeded.py"}


def test_an_autouse_fixture_import_reaches_every_test_beneath_it():
    conf = "import pytest\n\n@pytest.fixture(autouse=True)\ndef guard():\n    import app\n"
    files = {
        "app.py": "",
        "tests/conftest.py": conf,
        "tests/test_one.py": "def test_x():\n    pass\n",
        "other/test_far.py": "def test_x():\n    pass\n",
    }
    picked, _ = _picked(files, {"app.py": "modified"})
    assert picked == {"tests/test_one.py"}  # a conftest governs its own directory only


def test_a_module_level_conftest_import_and_the_conftest_itself_reach_every_test():
    files = {
        "lib/a.py": "",
        "tests/conftest.py": "import lib.a\n",
        "tests/test_one.py": "def test_x():\n    pass\n",
    }
    assert _picked(files, {"lib/a.py": "modified"})[0] == {"tests/test_one.py"}
    assert _picked(files, {"tests/conftest.py": "modified"})[0] == {"tests/test_one.py"}


def test_a_data_file_reaches_the_code_that_names_it_by_path():
    files = {
        "lib/data/thing.json": "{}",
        "lib/reader.py": "PATH = 'lib/data/thing.json'\n",
        "tests/test_reader.py": "import lib.reader\n",
        "tests/test_other.py": "X = 'nothing here'\n",
    }
    picked, _ = _picked(files, {"lib/data/thing.json": "modified"})
    assert picked == {"tests/test_reader.py"}


def test_a_specific_glob_names_a_file_and_a_generic_one_does_not():
    files = {
        "lib/x.pine": "",
        "scratch/y.json": "",
        "tests/test_pine.py": "PATTERN = '*.pine'\n",
        "tests/test_json.py": "PATTERN = '*.json'\n",
    }
    assert _picked(files, {"lib/x.pine": "modified"})[0] == {"tests/test_pine.py"}
    # "*.json" reads whatever sits in ITS directory - a bare tail cannot say which file. (Outside
    # the code trees, so an unmatched file is noted rather than escalated to everything.)
    picked, sel = _picked(files, {"scratch/y.json": "modified"})
    assert picked == set() and not sel.everything


def test_a_data_file_inside_a_package_reaches_that_package():
    files = {
        "pkg/__init__.py": "",
        "pkg/strategy.meta.json": "{}",
        "lib/a.py": "",
        "tests/test_pkg.py": "import pkg\n",
        "tests/test_a.py": "import lib.a\n",
    }
    picked, sel = _picked(files, {"pkg/strategy.meta.json": "modified"})
    # Not by escalation: an unmapped file in a code tree would also pick test_pkg, with test_a.
    assert picked == {"tests/test_pkg.py"} and not sel.everything


def test_a_deleted_module_selects_whatever_still_imports_it():
    files = {"tests/test_gone.py": "import lib.gone\n", "tests/test_fine.py": "import os\n"}
    picked, _ = _picked(files, {"lib/gone.py": "deleted"})
    assert picked == {"tests/test_gone.py"}


def test_an_fstring_import_reaches_every_package_one_level_under_its_prefix():
    files = {
        "lib/loader.py": "import importlib\ndef load(n):\n    importlib.import_module(f'plugins.{n}')\n",
        "plugins/p1/__init__.py": "",
        "plugins/p1/deep/__init__.py": "",
        "tests/test_loader.py": "import lib.loader\n",
    }
    assert _picked(files, {"plugins/p1/__init__.py": "modified"})[0] == {"tests/test_loader.py"}


def test_a_mock_patch_target_is_a_dependency_even_without_an_import():
    files = {"lib/a.py": "", "tests/test_patch.py": "TARGET = 'lib.a.func'\n"}
    assert _picked(files, {"lib/a.py": "modified"})[0] == {"tests/test_patch.py"}


def test_a_script_named_by_path_is_a_dependency():
    files = {"tools/run_me.py": "", "tests/test_script.py": "SCRIPT = 'tools/run_me.py'\n"}
    assert _picked(files, {"tools/run_me.py": "modified"})[0] == {"tests/test_script.py"}


def test_a_bare_name_shared_by_many_files_names_none_of_them():
    files = {f"lib/p{i}/config.py": "" for i in range(4)}
    files["tests/test_scan.py"] = "NAME = 'config.py'\n"
    assert _picked(files, {"lib/p0/config.py": "modified"})[0] == set()


def test_a_docstring_mentioning_a_file_is_not_a_dependency():
    # The docstring is EXACTLY a path, so it would be an edge if docstrings were read as strings.
    files = {"tools/run_me.py": "", "tests/test_doc.py": '"""tools/run_me.py"""\n'}
    assert _picked(files, {"tools/run_me.py": "modified"})[0] == set()


def test_an_unmapped_file_in_a_code_tree_runs_everything():
    files = {"lib/a.py": "", "lib/mystery.bin": "", "tests/test_a.py": "import lib.a\n"}
    _, sel = _picked(files, {"lib/mystery.bin": "added"})
    assert sel.everything and sel.escalated[0][0] == "lib/mystery.bin"


def test_an_unmapped_file_outside_the_code_trees_is_only_noted():
    files = {"lib/a.py": "", "scratch/notes.bin": "", "tests/test_a.py": "import lib.a\n"}
    picked, sel = _picked(files, {"scratch/notes.bin": "added"})
    assert not sel.everything and picked == set() and sel.notes


def test_a_doc_reaches_only_code_naming_its_full_path_and_never_escalates():
    files = {
        "lib/CLAUDE.md": "",
        "tests/test_a.py": "X = 'CLAUDE.md'\n",  # the bare name: a throwaway repo, reads nothing
        "tests/test_guard.py": "BIG = '/repo/lib/CLAUDE.md'\n",  # a real file, by path
    }
    picked, sel = _picked(files, {"lib/CLAUDE.md": "modified"})
    assert picked == {"tests/test_guard.py"} and not sel.everything


def test_a_sibling_import_resolves_from_the_files_own_directory():
    files = {"lib/tools/helper.py": "", "lib/tools/test_helper.py": "import helper\n"}
    assert _picked(files, {"lib/tools/helper.py": "modified"})[0] == {"lib/tools/test_helper.py"}


def test_a_golden_export_runs_its_own_components_gate():
    files = {"engines/eng/exports/golden/X.csv": "", "engines/eng/tools/compare_eng.py": ""}
    _, sel = _picked(files, {"engines/eng/exports/golden/X.csv": "modified"})
    assert sel.gates == {"engines/eng"}


def test_code_under_a_gate_runs_that_gate_and_the_gate_runner_runs_all_of_them():
    files = {
        "engines/eng/engine.py": "",
        "engines/eng/tools/compare_eng.py": "import engines.eng.engine\n",
        "tools/run_gates.py": "",
    }
    assert _picked(files, {"engines/eng/engine.py": "modified"})[1].gates == {"engines/eng"}
    assert _picked(files, {"tools/run_gates.py": "modified"})[1].gates == {"engines/eng"}


def test_a_step_runs_when_its_script_can_reach_the_change():
    files = {"lib/a.py": "", "lib/b.py": "", "tools/check.py": "import lib.a\n"}
    assert _picked(files, {"lib/a.py": "modified"})[1].steps == {4}
    assert _picked(files, {"lib/b.py": "modified"})[1].steps == set()


def test_changed_code_no_test_reaches_is_said_out_loud():
    files = {"lib/lonely.py": "", "tests/test_a.py": "import os\n"}
    _, sel = _picked(files, {"lib/lonely.py": "modified"})
    assert sel.unreached == ["lib/lonely.py"]


# ── mutation map, RUN 2026-09-10 through scripts/testing/mutate.py (in memory, no file edits) ───
# 20 planted, 20 killed, each reddening exactly the named case:
# fixture imports treated as module-level            -> only_the_tests_using_that_fixture
# fixture closure not expanded over fixture params     -> only_the_tests_using_that_fixture
# autouse fixtures dropped                             -> every_test_beneath_it
# search roots ignored                                 -> only_through_a_declared_search_root
# relative imports return nothing                      -> resolved_against_the_package
# path-substring readers dropped                       -> naming_its_full_path
# generic-glob filter removed                          -> a_generic_one_does_not
# package_of finds nothing                             -> reaches_that_package
# deleted-module importers dropped                     -> still_imports_it
# f-string prefix dropped                              -> one_level_under_its_prefix
# dotted-string rule removed                           -> mock_patch_target
# .py path rule removed                                -> script_named_by_path
# namesake cap removed                                 -> shared_by_many_files
# docstrings kept as strings                           -> docstring_mentioning_a_file
# own-directory resolution removed                     -> files_own_directory
# code-tree escalation removed                         -> runs_everything
# golden table action ignored                          -> own_components_gate
# gate runner reach ignored                            -> runner_runs_all_of_them
# step script reach ignored                            -> step_runs_when
# unreached report removed                             -> said_out_loud
# 🔴 TWO SURVIVED THE FIRST PASS, and both were these tests being vacuous, not the selector being
# right: the package case was satisfied by the run-everything fallback (it now asserts that did
# NOT fire, beside a test that must stay unpicked), and the docstring case's text never looked like
# a path, so keeping docstrings could not have made an edge. A green test proves nothing until it
# has been seen red.
